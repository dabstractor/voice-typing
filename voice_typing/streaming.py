"""voice_typing.streaming — phone-style streaming output engine (PRD §4.2quater R1).

Turns stabilized realtime partials from the recorder-host child into live typed
dictation. On every stabilized partial, diff it against the tentatively typed
tail:

  - EXTEND (old tail is a prefix of the new partial, compared case-insensitively
    — the casing guard lowercases a fresh mid-sentence fragment while decoder
    partials stay capitalized; BUG-008): type ONLY the delta, with
    textproc.apply_streaming_guards() applied (mid-sentence casing + one spurious
    '.' stripped). Additive and flicker-free by construction — never rate-limited.
  - REVISE (anything else — RealtimeSTT may re-capitalize, retract or rewrite
    earlier words): press_backspace(len(tail)) then type the guarded corrected
    tail. FULL REWINDS ARE RATE-LIMITED: at most one per
    _FULL_REWIND_RATE_LIMIT_S (a code constant, NOT config — PRD §4.2quater ">=300
    ms so a wobbling decode cannot flicker"). A suppressed cycle mirrors the
    current tail and touches nothing.
  - Every event — extend, revise, suppressed, frozen, disabled — mirrors the
    appropriate string into feedback.update_partial() so voicectl status / the
    state file always show what the user sees.

TAIL TRACKS TYPED TEXT, not the raw partial: the tail stores the guarded strings
actually sent to the backend, so len(tail) is always exactly the number of
characters a rewind must delete and prefix-diffing stays consistent. No trailing
space is ever typed while the tail is tentative — only the commit path
(P1.M2.T6.S2) appends the inter-final space.

FAILURE POLICY: a backend exception inside on_partial NEVER propagates (it would
kill the host reader thread and streaming would silently stop). It is logged as a
WARNING and the engine FREEZES itself (frozen=True): a failed rewind+retype
leaves the on-screen state unknown ("typed text is never auto-deleted", PRD
§4.2quater), so the safest response is to stop touching the text. The feedback
mirror keeps updating. P1.M2.T6.S3 landed the freeze lifecycle: freezes come in
two classes — SESSION (backend failure; stranded tail from a drain-timeout abort
or a recorder-host child death; survives reset_boundary(), lifted only by
reset_session()) and PER-UTTERANCE (a non-Backspace user keypress over a pending
tail — note_user_keypress(); lifted at the next utterance boundary).

THREAD CONTEXT: on_partial is called from the host reader (daemon) thread; commit()
from the daemon's on_final thread INSIDE _on_final_lock (landed P1.M2.T6.S2);
cancel()/pending_tail_len() from the
control-socket thread via daemon._pending_tail_len/_reset_stream_after_cancel.
One internal threading.Lock guards all state. Backend calls happen WHILE HOLDING
it — deliberate, matching the daemon's _on_final_lock style: partial events are
serialized on one thread anyway, and cancel() (which holds the daemon _lock and
then wants this lock) can only ever wait for one in-flight type/backspace
(~150 ms), never deadlock (this code never takes the daemon _lock back).

CONSUMES: typing_backends.TypingBackend (type_text / press_backspace, P1.M1.T3.S1);
  a Feedback-like object exposing update_partial(text) (already >=10 Hz throttled —
  this engine adds NO throttle of its own); the cfg.output.streaming bool
  (P1.M1.T1.S1); textproc.apply_streaming_guards (this subtask, textproc.py).
CONSUMED BY: daemon.VoiceTypingDaemon — constructed in __init__ as self._stream
  (P1.M2.T6.S1); partial routing + commit path land in P1.M2.T6.S2 via
  on_partial/reset_boundary; daemon.cancel() (P1.M2.T7.S1) already calls
  pending_tail_len() / reset_after_cancel() — those names are LOAD-BEARING.
  T5.S2 consumes the `committed` property for the context-prompt refresh.

PURE STDLIB (logging, threading, time + textproc). No torch / ctranslate2 /
realtimestt / pyaudio — imports cleanly in CPU-only and unit-test contexts.
Nothing typed at import time; the engine starts no threads.
"""

from __future__ import annotations

import logging
import threading
import time

import voice_typing.textproc as textproc

logger = logging.getLogger(__name__)

# Minimum spacing between FULL rewind-and-retype cycles (PRD §4.2quater rule 1:
# ">=300 ms" — a code constant by design, deliberately NOT a config key, so a
# wobbling decoder can never be tuned into flicker).
_FULL_REWIND_RATE_LIMIT_S = 0.3

# Sentence terminators that end the rolling context sentence (PRD §4.2quater rule 2:
# the child's context prompt carries the text since the last sentence boundary). Same
# set as textproc's casing guard — pinned verbatim.
_CONTEXT_BOUNDARY_CHARS = ".!?"


def context_after_last_boundary(committed: str) -> str:
    """Text after the last sentence terminator in `committed` (casing-guard slicer).

    P1.M2.T6.S2 thin-seam helper. SUPERSEDED for prompt computation (P1.M2.T5.S2):
    the formal daemon-side rolling-context computation now lives in
    prompt_engine.rolling_context_prompt — which does its OWN rfind because this
    slicer's ""-on-no-boundary contract is ambiguous for prompts ("" means both
    'committed ends with a terminator' and 'no terminator anywhere'). This slicer
    KEEPS that contract — it is pinned by tests and used for casing-guard context,
    not prompts. Returns "" when `committed` has no '.', '!' or '?' at all, or when
    the last terminator sits at the very end (nothing after it). Surrounding
    whitespace is stripped. PURE: no I/O, no state, deterministic.
    """
    last = max(committed.rfind(ch) for ch in _CONTEXT_BOUNDARY_CHARS)
    return committed[last + 1 :].strip() if last >= 0 else ""


def _ci_startswith(text: str, prefix: str) -> bool:
    """True iff `prefix` is a case-insensitive prefix of `text` (BUG-008).

    Per-character casefold comparison over the ORIGINAL strings — never builds a
    folded string, so a length-changing casefold ('ß'.casefold() == 'ss') cannot
    desynchronize the comparison from the original lengths. Callers slice deltas
    from the originals: delta = text[len(prefix):]. PURE: no I/O, no state.
    """
    return len(text) >= len(prefix) and all(
        a.casefold() == b.casefold() for a, b in zip(text, prefix)
    )


def _echo_norm(text: str) -> str:
    """Normalize for the stray-echo comparison (ISSUE-002 fix): lowercase, drop
    non-alphanumerics, collapse runs to single spaces, strip the ends. "Thank you."
    and "thank  you" fold to the same key. PURE: no I/O, no state."""
    out: list[str] = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != " ":
            out.append(" ")
    return "".join(out).strip()


def _is_stray_echo(partial: str, rejected: str) -> bool:
    """True iff `partial` looks like a stray of the REJECTED decode `rejected` (ISSUE-002).

    Echo iff the normalized partial is non-empty and contained in the normalized
    rejected text with no extra words — a Whisper hallucination cycle repeats the
    dead utterance's own words (often truncated mid-word: "ank you"), while
    genuinely-new speech grows past the rejected decode ("the next real sentence"
    shares nothing, or is LONGER). A contentless (silence) partial always counts as
    an echo: it must never lift a freeze. PURE: no I/O, no state."""
    p = _echo_norm(partial)
    r = _echo_norm(rejected)
    if not p:
        return True
    return len(p) <= len(r) and p in r


class StreamingOutput:
    """Per-armed-session streaming output state machine (PRD §4.2quater R1).

    State (all under self._lock):
        committed: finalized text through the last commit checkpoint (commit()
            advances it by the text ACTUALLY TYPED + the trailing space; read by
            the guards as the casing context and by the daemon's context-prompt
            seam via the `committed` property).
        tail: everything typed since that checkpoint — tentative, revisable,
            NEVER ending with a space. Length == exactly the chars a rewind
            must delete.
        frozen: True -> on_partial does NO backend calls, mirror-only (set by
            freeze() or a backend failure). Comes in two classes (P1.M2.T6.S3):
            per-utterance (_frozen_session False) is lifted by the next
            reset_boundary(); session (_frozen_session True) survives every
            reset_boundary() and is cleared by reset_session() or — for NON-backend
            origin freezes only — resume() (BUG-001).
        frozen_session: the class of the current freeze (False when not frozen
            or per-utterance).
        suppressed: True after reset_after_cancel() -> mirror-only until resume()
            (the daemon's next-speech seam) or the next reset_boundary(), so a
            stale late partial from the cancelled utterance cannot re-type text
            right after a cancel.
    """

    def __init__(
        self,
        backend,
        feedback,
        streaming: bool,
        *,
        append_space: bool = True,
        rate_limit_s: float = _FULL_REWIND_RATE_LIMIT_S,
        clock=time.monotonic,
    ) -> None:
        """Args:
        backend: a TypingBackend (type_text / press_backspace).
        feedback: object exposing update_partial(text) (voice_typing.feedback.Feedback
            or a test double). Called once per on_partial event.
        streaming: the cfg.output.streaming flag; False = mirror-only Rev 1
            behavior (tail stays "", raw partial mirrored verbatim).
        append_space: the cfg.output.append_space flag; commit() appends the
            inter-final trailing space IFF true (the ONLY code that ever types a
            space while the engine is live — P1.M2.T6.S2).
        rate_limit_s: minimum spacing between full rewinds (override only in tests).
        clock: monotonic time source (injectable for deterministic rate-limit tests).
        """
        self._backend = backend
        self._feedback = feedback
        self._streaming = bool(streaming)
        self._append_space = bool(append_space)
        self._rate_limit_s = float(rate_limit_s)
        self._clock = clock
        self._lock = threading.Lock()
        self._committed: str = ""
        self._tail: str = ""
        self._frozen: bool = False
        self._frozen_session: bool = (
            False  # True = survives reset_boundary() (P1.M2.T6.S3)
        )
        # Freeze ORIGIN tag: True only while the CURRENT freeze was raised by a
        # backend failure inside _safe_type/_safe_backspace (engine-internal), so
        # resume() can refuse to lift it (after a backend failure the on-screen
        # state cannot be trusted). A fresh freeze()/reset_session() clears it;
        # the promote-only path never touches it.
        self._frozen_backend_failure: bool = False
        # Stray-echo guard (ISSUE-002): the RAW rejected decode, armed by the daemon
        # right after a rejected final's freeze(session=True). While set, resume()
        # refuses to lift the freeze (every partial fires the per-partial speech seam
        # the daemon calls resume() from, so strays of the dead utterance reach it
        # too), and on_partial holds echo partials mirror-only until the first
        # NON-echo partial — genuinely-new speech — lifts the freeze and streams.
        # Cleared exactly with the freeze it guards: the on_partial lift and
        # reset_session(); a later reject overwrites it.
        self._echo_guard: str | None = None
        self._suppressed: bool = False
        # None = no full rewind has happened yet (first revise is always allowed).
        # A plain 0.0 sentinel would break a fake clock starting at 0.0 (and read
        # as "rewound 50 years ago" on the real clock) — None says it cleanly.
        self._last_full_rewind: float | None = None

    # --- read-only accessors (T5.S2 + T6.S2 consume; tests may poke _committed) ---

    @property
    def committed(self) -> str:
        """Finalized text through the last commit checkpoint (empty until T6.S2 commits)."""
        return self._committed

    @property
    def tail(self) -> str:
        """Tentative typed tail since the checkpoint ("" when idle/disabled; no trailing space)."""
        return self._tail

    @property
    def frozen(self) -> bool:
        """True once freeze()d or after a backend failure — mirror-only until unfrozen."""
        return self._frozen

    @property
    def frozen_session(self) -> bool:
        """Class of the current freeze: True = session freeze (survives reset_boundary()).

        False both for a per-utterance freeze and when not frozen at all; callers
        combine it with `frozen` to tell the two states apart.
        """
        return self._frozen_session

    # --- lifecycle (daemon.cancel() seam — exact names are load-bearing) ---

    def pending_tail_len(self) -> int:
        """Chars of tentative tail typed since the last checkpoint. 0 = nothing pending."""
        with self._lock:
            return len(self._tail)

    def reset_after_cancel(self) -> None:
        """Fresh tail at the current cursor after a Backspace-cancel; committed UNCHANGED.

        Also sets `suppressed`: on_partial mirrors only while suppressed — a stale
        late partial from the cancelled utterance must not re-type the fragment the
        user just deleted. Suppression lifts at resume() (the daemon's next-speech
        seam — P1.M1.T1.S2 wiring) or the next reset_boundary(); in practice it is
        resume(): the daemon fires NO boundary between a cancel and the next real
        final (the sentinel final is dropped pre-commit, BUG-002).
        """
        with self._lock:
            self._tail = ""
            self._suppressed = True

    def reset_boundary(self) -> None:
        """New utterance boundary: clear the tail, lift post-cancel suppression, and
        lift a PER-UTTERANCE freeze.

        While FROZEN, the tail is first ABSORBED into `committed` — commit()'s
        frozen-path join, verbatim (BUG-001 companion fix): a rejected final (the
        daemon's freeze(session=True) + reset_boundary() pair) leaves a real typed
        fragment on screen, and dropping it without absorbing would orphan it from
        the checkpoint, staling the casing guard, the rolling context prompt and
        the mirror. Keystroke-free — the absorb only moves the engine string.

        The daemon calls this once per utterance, right after commit() (or a rejected
        final), so a user-keypress freeze (P1.M2.T6.S3, PRD rule 5) is lifted exactly
        here: the frozen commit has already absorbed the tail without keystrokes and
        the next utterance streams normally. SESSION-class freezes (backend failure,
        stranded tail, rejected final — PRD rule 4) deliberately SURVIVE this
        boundary: only reset_session() or resume() (non-backend origin) may clear
        them.
        """
        with self._lock:
            if self._frozen:
                # Same join commit()'s frozen path uses: rstrip the base so the
                # previous commit's inter-final space (already on screen) is not
                # doubled, and drop empty parts.
                self._committed = " ".join(
                    p for p in (self._committed.rstrip(), self._tail) if p
                )
            self._tail = ""
            self._suppressed = False
            if self._frozen and not self._frozen_session:
                self._frozen = False
                self._frozen_session = False

    def reset_session(self) -> None:
        """A NEW armed session (P1.M2.T6.S2): clear committed + tail + suppressed + FROZEN.

        Session-lifecycle counterpart of reset_boundary(): a fresh arm legitimately
        unfreezes — whatever stranded the previous session's tail (a backend failure,
        a rejected final) must not carry into the next one, and the full-rewind
        budget starts fresh. reset_boundary() lifts only PER-UTTERANCE freezes;
        session-class freezes (backend failure, stranded tail) survive every boundary
        and are cleared ONLY here. On disarm the pending tail simply stays typed on
        screen FOREVER (PRD rule 4: a stranded tail is never rewound — reset_session()
        sends NO keystrokes, it resets the engine strings only); the engine strings
        reset for the next session. Called from daemon._arm()/_disarm() (defensive
        getattr seam, matching daemon.cancel()'s style).
        """
        with self._lock:
            self._committed = ""
            self._tail = ""
            self._suppressed = False
            self._frozen = False
            self._frozen_session = False
            self._echo_guard = None  # a fresh arm clears the rejected-final guard too
            # A fresh arm trusts the screen again: clear the backend-failure origin
            # tag too, so a later non-backend freeze in the new session is liftable
            # by resume() (the tag must imply frozen; this unfreeze clears it).
            self._frozen_backend_failure = False
            self._last_full_rewind = None

    def resume(self) -> None:
        """Class-aware lift: clears suppression ALWAYS; lifts ONLY a stranded
        (session-class, non-backend, non-echo) freeze (BUG-001, re-scoped by the Rev-2
        validation, ISSUE-001/ISSUE-002).

        The daemon fires this from the PER-PARTIAL speech seam (_touch_speech — the
        child's on_speech hook fires on EVERY stabilized partial, because that is how
        the idle auto-stop clock resets), so it must be stray-safe by contract, not
        by event ordering:
          - `_suppressed` = False ALWAYS (also the post-cancel seam; P1.M1.T2.S1 /
            BUG-002 reuses exactly this).
          - frozen AND NOT backend-failure-origin AND NOT echo-guarded AND
            session-class: lift (a stranded-tail freeze recovers at new speech).
          - frozen WITH backend-failure origin (tagged internally by _safe_type/
            _safe_backspace): leave frozen, log at INFO — after a backend failure
            the on-screen state cannot be trusted, so only reset_session() (fresh
            arm) may recover.
          - frozen WITH the stray-echo guard armed (a rejected final — ISSUE-002):
            leave frozen, log at INFO. Every partial — a stray of the dead utterance
            included — reaches this seam via its paired speech event, so lifting
            here would let hallucination text type (the exact filed regression).
            That freeze lifts at the first NON-echo partial (see on_partial) or at
            reset_session().
          - frozen PER-UTTERANCE (a user keypress — ISSUE-001): leave frozen, log
            at INFO. The keypress freeze must hold until reset_boundary() absorbs
            the tail (PRD §4.2quater rule 5: never type over the user's cursor).
        Idempotent; sends NO keystrokes; does not touch _committed/_tail/
        _last_full_rewind.
        """
        with self._lock:
            self._suppressed = False
            if self._frozen:
                if self._frozen_backend_failure:
                    logger.info(
                        "streaming resume(): refusing to lift backend-failure freeze "
                        "(on-screen state untrusted; re-arm to recover)"
                    )
                elif self._echo_guard is not None:
                    logger.info(
                        "streaming resume(): rejected-final freeze survives (stray "
                        "partials of the dead utterance reach this seam; lifts at the "
                        "first non-echo partial or a fresh arm)"
                    )
                elif not self._frozen_session:
                    logger.info(
                        "streaming resume(): per-utterance (user-keypress) freeze "
                        "survives — it lifts only at reset_boundary()"
                    )
                else:
                    self._frozen = False
                    self._frozen_session = False

    def arm_stray_echo_guard(self, rejected_text: str) -> None:
        """Arm the stray-echo guard with the REJECTED decode (ISSUE-002; BUG-001 seam).

        The daemon calls this right after a rejected final's freeze(session=True) +
        reset_boundary() pair, passing the RAW decode text. Until the freeze lifts:
          - on_partial holds an echo of `rejected_text` (same hallucination cycle —
            possibly truncated mid-word) mirror-only WITHOUT lifting, and
          - resume() refuses to lift the freeze (its daemon call site fires on every
            partial's paired speech event).
        The first NON-echo partial — genuinely-new speech — lifts the freeze inside
        on_partial and streams live (BUG-001: the next real utterance types). The
        guard is cleared exactly with the freeze it guards: the on_partial lift and
        reset_session(); arming again overwrites (the newest reject wins). A
        whitespace/punctuation-only decode arms nothing. Sends NO keystrokes.
        """
        if not _echo_norm(rejected_text):
            return
        with self._lock:
            self._echo_guard = rejected_text

    def freeze(self, reason: str = "", *, session: bool = False) -> None:
        """Stop typing (mirror-only); log why. `session=True` freezes survive reset_boundary().

        Two classes (P1.M2.T6.S3 / PRD §4.2quater rules 4-5):
          - per-utterance (default): lifted at the next reset_boundary() — e.g. a user
            keypress over a pending tail must stop revising THIS utterance only.
          - session: on-screen state can no longer be trusted for the rest of the
            armed session (backend failure; stranded tail from a drain-timeout abort
            or a recorder-host child death; a rejected final — BUG-001). It survives
            every reset_boundary() and is lifted by reset_session() (fresh arm) or,
            for NON-backend-origin freezes, by resume() at the next utterance's
            speech (P1.M1.T1.S2); resume() deliberately REFUSES a backend-failure
            freeze.

        Idempotent and PROMOTE-ONLY: freezing while already frozen is a no-op, except
        that a session freeze upgrades a per-utterance one (a later per-utterance
        reason must never weaken a session freeze). The backend-failure origin tag is
        never cleared on that promote path (a rejected-final freeze on top of a
        backend failure stays un-liftable); a FRESH freeze clears it (it describes
        the current freeze only).
        """
        with self._lock:
            if self._frozen:
                if session and not self._frozen_session:
                    self._frozen_session = True
                    logger.warning(
                        "streaming output frozen (session): %s", reason or "unspecified"
                    )
                return
            self._frozen = True
            self._frozen_session = bool(session)
            self._frozen_backend_failure = False  # fresh freeze: no backend origin yet
        logger.warning(
            "streaming output frozen (%s): %s",
            "session" if session else "per-utterance",
            reason or "unspecified",
        )

    def note_user_keypress(self) -> None:
        """PRD §4.2quater rule 5 — never type over the user's cursor (P1.M2.T6.S3).

        Called by daemon.note_user_keypress() (the seam the T7.S2 evdev listener will
        drive) for every NON-Backspace keypress observed while listening. A pending
        tail means the engine's next keystrokes would land ON TOP of the user's edit,
        so the tail freezes PER-UTTERANCE: mirror-only until the next boundary, where
        commit() absorbs it without keystrokes and reset_boundary() lifts the freeze
        (the next utterance streams normally). No pending tail -> plain user editing,
        nothing of ours at risk -> no-op. Idempotent (an existing freeze is never
        weakened) and thread-safe: self._lock serializes with on_partial/commit, so
        the listener thread needs no other coordination.
        """
        with self._lock:
            if not self._streaming or self._frozen or not self._tail:
                return
            self._frozen = True
            self._frozen_session = False
        logger.warning("streaming output frozen (user keypress while tail pending)")

    # --- the engine (PRD §4.2quater rule 1) ---

    def on_partial(self, text: str) -> None:
        """Handle one stabilized partial. Every path ends in a feedback mirror.

        Mirror rules: streaming disabled or post-cancel-suppressed mirrors the RAW
        partial (Rev 1 parity — voicectl status keeps showing the decoder's live
        text); frozen mirrors the TYPED tail (the screen truth); all streaming
        paths mirror the typed tail.
        """
        with self._lock:
            if not self._streaming:
                # Rev 1 parity: mirror the raw partial, type nothing, tail stays "".
                self._feedback.update_partial(text)
                return
            if self._suppressed:
                # Post-cancel: a stale partial from the dead utterance must not type.
                self._feedback.update_partial(text)
                return
            if self._frozen:
                # Frozen (freeze() or a backend failure): mirror the typed tail only —
                # EXCEPT an echo-guarded rejected-final freeze met by genuinely-new
                # speech (ISSUE-002 fix): a partial that is NOT an echo of the
                # rejected decode lifts that freeze right here and falls through to
                # the live streaming path below (BUG-001: the next real utterance
                # types, starting with THIS partial). Strays of the dead utterance
                # (echoes) and all other freezes stay mirror-only.
                if (
                    self._echo_guard is not None
                    and self._frozen_session
                    and not self._frozen_backend_failure
                    and not _is_stray_echo(text, self._echo_guard)
                ):
                    self._frozen = False
                    self._frozen_session = False
                    self._echo_guard = None
                    logger.info(
                        "streaming: partial is not an echo of the rejected decode — "
                        "rejected-final freeze lifted, streaming live again"
                    )
                else:
                    self._feedback.update_partial(self._tail)
                    return

            # Stable normalization: collapse any whitespace run to single spaces and
            # strip the ends — the same shape textproc.clean produces, so prefix
            # diffing is stable and a trailing-space waffle is a no-op.
            text = " ".join(text.split())

            if self._tail and _ci_startswith(text, self._tail):
                # EXTEND: tail is a case-insensitive prefix -> type only the
                # guarded delta (sliced from the ORIGINALS, not folded text).
                delta = text[len(self._tail) :]
                if not delta:
                    self._feedback.update_partial(self._tail)
                    return
                guarded = textproc.apply_streaming_guards(
                    self._guard_context_delta(), delta
                )
                if guarded:
                    # Never rate-limited: additive, flicker-free by construction.
                    if not self._safe_type(guarded):
                        self._feedback.update_partial(self._tail)
                        return
                    self._tail += guarded
                self._feedback.update_partial(self._tail)
                return

            # REVISE (includes the fresh start when tail == ""): rewind + retype.
            # Clock is consulted ONLY for an actual rewind attempt (tail non-empty):
            # a fresh start is not a rewind, consumes no time sample, and stamps
            # nothing — so the rate limiter measures rewind-to-rewind spacing only.
            had_tail = bool(self._tail)
            now = self._clock() if had_tail else None
            if (
                had_tail
                and self._last_full_rewind is not None
                and now - self._last_full_rewind < self._rate_limit_s
            ):
                # Too soon after the last full rewind: keep the current tail on
                # screen, type nothing this cycle — a wobbling decode cannot flicker.
                self._feedback.update_partial(self._tail)
                return
            guarded = textproc.apply_streaming_guards(self._committed, text)
            # press_backspace(0) is a backend no-op; _safe_backspace also guards it.
            if not self._safe_backspace(len(self._tail)):
                self._feedback.update_partial(self._tail)
                return  # freeze already recorded by _safe_backspace
            if guarded and not self._safe_type(guarded):
                self._feedback.update_partial(self._tail)
                return  # tail unchanged: the retype never landed
            self._tail = guarded
            if had_tail:
                # Stamp only ACTUAL rewinds — never fresh starts.
                self._last_full_rewind = now
            self._feedback.update_partial(self._tail)

    # --- the commit (correction pass; PRD §4.2quater rule 2, P1.M2.T6.S2) ---

    def commit(self, final_text: str) -> None:
        """Apply the child's silence-triggered final (the small.en correction pass).

        Called from the daemon's on_final thread while the daemon's _on_final_lock is
        held, so a racing cancel() can never interleave rewind keystrokes with the
        compensation rewind. Serialized with on_partial by self._lock (same discipline
        as on_partial; this code never takes a daemon lock back).

        Paths:
          - streaming disabled: return (the daemon routes Rev 1 finals AROUND the
            engine — the rollback hatch must be provably keystroke-identical).
          - frozen: absorb the typed tail into `committed` WITHOUT keystrokes (typed
            text is never auto-deleted, PRD rule 4) — the on-screen text becomes the
            de-facto committed text for on-screen continuity — then clear the tail,
            lift suppression, mirror, return. Works for BOTH freeze classes
            (P1.M2.T6.S3): a stranded/session-frozen tail whose final races in late
            absorbs and STAYS frozen, and a user-keypress-frozen tail absorbs before
            the daemon's post-commit reset_boundary() lifts the per-utterance freeze.
          - final EXTENDS the tail: type ONLY the guarded delta (same context shape
            as _guard_context_delta). NOT rate-limited: commits are authoritative,
            never wobble (the >=300 ms limiter exists only for partial cycles).
          - final DIFFERS (revise/rewrite/shorter/fresh): press_backspace(len(tail))
            then type the guarded final. NOT rate-limited: a commit is once per
            utterance.
        Then append the trailing space iff append_space, advance the checkpoint
        (`committed` gains the text ACTUALLY TYPED + the space, so future guards and
        the context prompt diff against screen truth), clear the tail, lift
        suppression, and mirror into feedback (matches feedback.record_final's
        final-into-partial behavior).

        Backend failure: _safe_type/_safe_backspace freeze the engine; commit returns
        WITHOUT advancing the checkpoint (the frozen tail stays on screen — PRD
        "stranded tail freezes"; T6.S3 formalizes the cleanup). Never raises.
        """
        with self._lock:
            if not self._streaming:
                return  # Rev 1 rollback hatch: engine is a mirror-only pass-through
            text = " ".join(final_text.split())
            if self._frozen:
                # BUG-003 (P1.M1.T3.S1): absorb WITHOUT revision keystrokes, but still
                # honor append_space — type the separator so the next utterance's first
                # word does not glue onto the absorbed tail once reset_boundary() lifts
                # a per-utterance freeze (PRD §4.2quater rule 2). Space exactly once
                # (rstrip base + " + space"), the non-frozen path's discipline.
                # Fail-safe: a space-type failure freezes SESSION-class (promote-only)
                # — acceptable (the tail is stranded anyway); absorb nothing then.
                space = " " if self._append_space else ""
                if space and not self._safe_type(space):
                    return  # frozen (session); checkpoint stays at the pre-commit boundary
                self._committed = (
                    " ".join(p for p in (self._committed.rstrip(), self._tail) if p)
                    + space
                )
                self._tail = ""
                self._suppressed = False
                self._feedback.update_partial(self._committed)
                return
            if self._tail and _ci_startswith(text, self._tail):
                # EXTEND: the final confirms the tail (case-insensitively) — type
                # only the guarded delta (sliced from the ORIGINALS).
                delta = text[len(self._tail) :]
                guarded = ""
                if delta:
                    guarded = textproc.apply_streaming_guards(
                        self._guard_context_delta(), delta
                    )
                    if guarded and not self._safe_type(guarded):
                        return  # frozen by the fail-safe; tail frozen on screen
                    self._tail += guarded
                typed = self._tail
            else:
                # REVISE / fresh start: exact-length rewind + guarded retype. A commit
                # is authoritative — no rate-limit consult, no _last_full_rewind stamp.
                guarded = textproc.apply_streaming_guards(self._committed, text)
                if not self._safe_backspace(len(self._tail)):
                    return  # frozen; on-screen state unknown — touch nothing further
                if guarded and not self._safe_type(guarded):
                    return  # frozen mid-retype: the rewind landed, the retype did not
                self._tail = guarded
                typed = guarded
            space = " " if self._append_space else ""
            if space and not self._safe_type(space):
                return  # frozen: checkpoint stays at the pre-commit boundary
            # rstrip the base so the join never doubles the previous commit's
            # trailing space (it is already on screen exactly once).
            self._committed = (
                " ".join(p for p in (self._committed.rstrip(), typed) if p) + space
            )
            self._tail = ""
            self._suppressed = False
            self._feedback.update_partial(self._committed)

    # --- internals ---

    def _guard_context_delta(self) -> str:
        """Casing context for an extend delta: committed + " " + tail.

        The delta continues what is already on screen, so the text preceding it —
        not `committed` alone — decides mid-sentence vs sentence-start.
        """
        parts = [p for p in (self._committed.strip(), self._tail) if p]
        return " ".join(parts)

    def _safe_type(self, s: str) -> bool:
        """type_text that fails SAFE: log WARNING + freeze instead of killing the reader."""
        try:
            self._backend.type_text(s)
            return True
        except Exception as exc:  # noqa: BLE001 — the reader thread must survive
            logger.warning("streaming type_text(%r) failed (%s); freezing tail", s, exc)
            # SESSION-class freeze (P1.M2.T6.S3): on-screen state unknown — survives
            # reset_boundary(); only reset_session() (fresh arm) lifts it. Tag the
            # ORIGIN so resume() refuses to lift it (BUG-001 fail-safe).
            self._frozen = True
            self._frozen_session = True
            self._frozen_backend_failure = True
            return False

    def _safe_backspace(self, n: int) -> bool:
        """press_backspace that fails SAFE. n <= 0 is a no-op success (backend contract)."""
        if n <= 0:
            return True
        try:
            self._backend.press_backspace(n)
            return True
        except Exception as exc:  # noqa: BLE001 — the reader thread must survive
            logger.warning(
                "streaming press_backspace(%d) failed (%s); freezing", n, exc
            )
            # SESSION-class freeze (P1.M2.T6.S3): on-screen state unknown — see _safe_type.
            # Origin tagged so resume() refuses to lift it (BUG-001 fail-safe).
            self._frozen = True
            self._frozen_session = True
            self._frozen_backend_failure = True
            return False
