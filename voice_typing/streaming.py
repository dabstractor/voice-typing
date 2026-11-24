"""voice_typing.streaming — phone-style streaming output engine (PRD §4.2quater R1).

Turns stabilized realtime partials from the recorder-host child into live typed
dictation. On every stabilized partial, diff it against the tentatively typed
tail:

  - EXTEND (old tail is a prefix of the new partial, compared case-insensitively
    — the casing guard lowercases a fresh mid-sentence fragment while decoder
    partials stay capitalized; BUG-008): type ONLY the delta, with
    textproc.apply_streaming_guards() applied (mid-sentence casing + one spurious
    '.' stripped). Additive and flicker-free by construction — never debounced.
  - REVISE (anything else — RealtimeSTT may re-capitalize, retract or rewrite
    words): DEBOUNCED MINIMAL-DIFF REWIND (PRD §4.2quater rule 1, as amended for
    smoothness): partial typing is EXTEND-ONLY while the divergence is fresh —
    a mid-word retract that grows back past the tail re-converges as an EXTEND
    and types only its delta with ZERO backspaces. A rewind fires only after
    the divergence has PERSISTED for _REVISION_DEBOUNCE_S (a code constant,
    NOT config), and it is then ONE minimal-diff rewind: backspace ONLY the
    suffix past the longest common prefix of tail and the LATEST divergent
    partial — never the whole tail — then type the guarded corrected suffix
    (the guards see the KEPT on-screen prefix as their casing context). While
    the window is open the current tail stays on screen (mirror-only). The
    upshot: most utterances see ZERO mid-utterance revisions and exactly ONE
    authoritative correction — the commit's; a persistent mid-utterance
    rewrite is corrected at most once per debounce window.
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

# How long a partial must PERSISTently diverge from the typed tail before a
# mid-utterance revision (a rewind+retype) is allowed (PRD §4.2quater rule 1,
# as amended for smoothness: "one or two revisions per statement, ideally one
# authoritative one at the commit"). While the window is open, partial typing
# is EXTEND-ONLY — momentary decoder wobble (a mid-word retract that grows
# back past the tail) re-converges as an extend and types only its delta with
# ZERO backspaces; the divergent partials are mirrored (screen truth) and the
# latest is remembered. Once divergence has persisted this long, ONE
# minimal-diff rewind+retype lands with the LATEST partial, and the window
# re-arms (a further divergence opens a fresh one). The commit's correction is
# NEVER debounced — it is the authoritative end-of-utterance pass. Deliberately
# a code constant, NOT config: the >=300 ms rate limit this replaces still
# churned up to ~3 rewinds/sec on sustained divergence, and a wobbly decoder
# must never be tuned back into that flicker.
_REVISION_DEBOUNCE_S = 2.0

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


def _ci_common_prefix_len(a: str, b: str) -> int:
    """Length of the longest common prefix of `a` and `b`, case-insensitively.

    The minimal-diff rewind count (PRD §4.2quater rule 1): k matched chars ->
    press_backspace(len(typed) - k) + type the corrected suffix from offset k —
    never a whole-tail rewind for a tail-only edit. Per-character casefold
    comparison over the ORIGINAL strings, so k counts original characters and a
    length-changing casefold ('ß'.casefold() == 'ss') can never desync callers'
    slicing (same discipline as _ci_startswith). PURE: no I/O, no state.
    """
    n = min(len(a), len(b))
    k = 0
    while k < n and a[k].casefold() == b[k].casefold():
        k += 1
    return k


def _word_flush_point(s: str) -> int:
    """Index of the LAST chunk-boundary char in `s` (-1 if none) — word chunking.

    A boundary char is anything that is neither alphanumeric nor an apostrophe
    (spaces, punctuation): a flush point ENDS a word (the \\W-to-\\W rule).
    "hello world" -> 5 (the space); "world" -> -1 (word still growing — nothing
    flushes yet). PURE: no I/O, no state.
    """
    for i in range(len(s) - 1, -1, -1):
        ch = s[i]
        if not (ch.isalnum() or ch == "'"):
            return i
    return -1


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
        stream_chunks: str = "char",
        revision_debounce_s: float = _REVISION_DEBOUNCE_S,
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
        revision_debounce_s: how long divergence must persist before a
            mid-utterance revision is allowed (override only in tests; 0.0 =
            revise on the first divergent partial, the pre-debounce behavior).
        clock: monotonic time source (injectable for deterministic debounce tests).
        """
        self._backend = backend
        self._feedback = feedback
        self._streaming = bool(streaming)
        self._append_space = bool(append_space)
        self._chunk_words = str(stream_chunks) == "word"
        self._revision_debounce_s = float(revision_debounce_s)
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
        # Divergence debounce (the smoothness fix): _diverged_since is the clock
        # stamp of the FIRST partial that diverged from the current tail (None =
        # no open window); _diverged_text is the LATEST divergent partial. Closed
        # when a partial re-converges (an EXTEND — the divergence was momentary
        # wobble), when the debounced revision lands, and at every
        # boundary/session/cancel reset. None (not a 0.0 sentinel) so a fake
        # clock starting at 0.0 cannot alias "window open since t=0".
        self._diverged_since: float | None = None
        self._diverged_text: str = ""
        # CONTINUATION SEPARATOR (Rev 3): set when a session ends with a stranded tail
        # (immediate stop / keypress-disarm — the commit that would have typed the
        # inter-utterance space never ran). The screen continues mid-text with NO
        # trailing space, so the NEXT typed fragment must lead with exactly one space
        # or it fuses onto the stranded words (the "skipped spaces" bug). Typed
        # LAZILY — at the first fragment that actually lands — so a session that just
        # ends never leaves a dangling trailing space. Survives reset_session()
        # (it is a fact about the SCREEN, not the engine session); consumed only by
        # typing. append_space=false disables it entirely.
        self._pending_leading_space = False
        # True while tail[0] is a SYNTHESIZED separator (typed by us, never produced by
        # the decoder): prefix-diffing must use tail[1:] so decoder partials (which never
        # contain the space) still EXTEND cleanly instead of perpetually "diverging".
        # Accounting (backspace counts, len(tail)) always uses the REAL tail — the space
        # is on screen and a rewind must delete it. Only meaningful while tail non-empty.
        self._lead_sep = False

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
            had_tail = bool(self._tail)
            self._tail = ""
            self._lead_sep = False
            self._suppressed = True
            # The cursor now sits one char into the erased fragment (the physical
            # backspace's compensation) — the next fragment must not fuse onto it.
            # (Only when a REAL fragment was erased: a tail-less cancel is plain
            # user editing — the screen state is the user's business, not ours.)
            if self._append_space and had_tail:
                self._pending_leading_space = True
            self._diverged_since = None  # the cancelled fragment's divergence dies with it
            self._diverged_text = ""

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
                had_tail = bool(self._tail)
                self._committed = " ".join(
                    p for p in (self._committed.rstrip(), self._tail) if p
                )
                if had_tail and self._append_space:
                    # CONTINUATION SEPARATOR (Rev 3c): the join above put a separator
                    # into the ENGINE string, but NOTHING typed one on screen — the
                    # next fragment (first non-echo partial / next utterance) must
                    # lead with the synthesized space or it fuses onto the absorbed
                    # tail (the remaining "skipped spaces" hole — the rejected-final
                    # path fires the freeze+boundary pair on every filtered
                    # hallucination, so this hole was hit constantly).
                    self._pending_leading_space = True
            self._tail = ""
            self._lead_sep = False
            self._suppressed = False
            self._diverged_since = None  # a new utterance starts with a closed window
            self._diverged_text = ""
            if self._frozen and not self._frozen_session:
                self._frozen = False
                self._frozen_session = False

    def reset_session(self) -> None:
        """A NEW armed session (P1.M2.T6.S2): clear committed + tail + suppressed + FROZEN.

        Session-lifecycle counterpart of reset_boundary(): a fresh arm legitimately
        unfreezes — whatever stranded the previous session's tail (a backend failure,
        a rejected final) must not carry into the next one, and the revision-debounce
        budget starts fresh. reset_boundary() lifts only PER-UTTERANCE freezes;
        session-class freezes (backend failure, stranded tail) survive every boundary
        and are cleared ONLY here. On disarm the pending tail simply stays typed on
        screen FOREVER (PRD rule 4: a stranded tail is never rewound — reset_session()
        sends NO keystrokes, it resets the engine strings only); the engine strings
        reset for the next session. Called from daemon._arm()/_disarm() (defensive
        getattr seam, matching daemon.cancel()'s style).
        """
        with self._lock:
            if self._tail:
                # INTERRUPTED SESSION (Rev 3): a tail is stranded on screen with no
                # separator after it ("no trailing space while tentative"; the commit
                # that would have appended it never ran). Flag the continuation instead
                # of wiping: the next typed fragment leads with one space, and the
                # absorbed text stays as the casing/context source ("…long" lowercases
                # the continuation's first word).
                self._committed = " ".join(
                    p for p in (self._committed.rstrip(), self._tail) if p
                )
                self._pending_leading_space = True
            self._tail = ""
            self._lead_sep = False
            self._suppressed = False
            self._frozen = False
            self._frozen_session = False
            self._echo_guard = None  # a fresh arm clears the rejected-final guard too
            self._frozen_backend_failure = False  # we just unfroze; the origin tag must not outlive it
            self._diverged_since = None  # fresh session: revision window closed
            self._diverged_text = ""
            if not self._pending_leading_space:
                # GENUINELY fresh session (clean stop or first arm): full wipe — the
                # original reset_session contract. With a continuation pending, the
                # absorbed committed text above is deliberately KEPT.
                self._committed = ""

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
        the divergence-debounce state.
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

            # DIFF BASE (lead-sep): when tail[0] is our synthesized separator, decoder
            # partials never contain it — diff against tail[1:] so extends stay extends.
            vtail = self._tail[1:] if self._lead_sep else self._tail

            if vtail and _ci_startswith(text, vtail):
                # EXTEND: diff-base is a case-insensitive prefix -> type only the
                # guarded delta (sliced from the ORIGINALS, not folded text).
                # Re-convergence also CLOSES any open divergence window: the
                # divergence was momentary wobble (typing stays smooth), and a
                # LATER divergence opens a fresh window of its own.
                self._diverged_since = None
                self._diverged_text = ""
                delta = text[len(vtail) :]
                if self._chunk_words and _word_flush_point(delta) < 0:
                    # WORD CHUNKING: the delta is still mid-word (no boundary char
                    # yet) — hold it off the screen. Partials are cumulative, so the
                    # next event recomputes the full excess from the LATEST text;
                    # nothing is lost and no extra state is needed (the untyped
                    # remainder lives only BETWEEN events, never in engine state).
                    self._feedback.update_partial(self._tail)
                    return
                if self._chunk_words:
                    delta = delta[: _word_flush_point(delta) + 1]
                if not delta:
                    self._feedback.update_partial(self._tail)
                    return
                guarded = textproc.apply_streaming_guards(
                    self._guard_context_delta(), delta
                )
                if guarded:
                    # Never debounced: additive, flicker-free by construction.
                    if not self._safe_type(guarded):
                        self._feedback.update_partial(self._tail)
                        return
                    self._tail += guarded
                self._feedback.update_partial(self._tail)
                return

            # REVISE (the partial diverges from the typed tail — retraction,
            # rewrite or re-capitalization; the fresh start when tail == "" is
            # split out below). SMOOTHNESS (revision debounce): a mid-utterance
            # rewind is the jarring part of live dictation, so it fires ONLY
            # after the divergence has PERSISTED for _REVISION_DEBOUNCE_S —
            # momentary wobble re-converges as an EXTEND above (zero backspaces),
            # and while the window is open the tail stays on screen (mirror-only)
            # while the latest divergent partial is remembered. The commit's
            # authoritative correction still lands exactly once, at the end: the
            # common case is ZERO mid-utterance revisions.
            if not self._tail:
                # Fresh start: not a revision — type the guarded partial now. No
                # clock sample (nothing on screen to rewind, no window to open).
                fresh = text
                if self._chunk_words:
                    cut = _word_flush_point(fresh)
                    if cut < 0:
                        # WORD CHUNKING: first word still growing — hold off screen.
                        self._feedback.update_partial(self._tail)
                        return
                    fresh = fresh[: cut + 1]
                guarded = textproc.apply_streaming_guards(
                    self._guard_context(""), fresh
                )
                piece = guarded
                if piece and self._pending_leading_space and self._append_space:
                    # CONTINUATION SEPARATOR: the screen ends with stranded text and
                    # no trailing space — lead with exactly one (typed lazily).
                    piece = " " + piece
                    self._pending_leading_space = False
                if piece:
                    # Never debounced: additive, flicker-free by construction.
                    if not self._safe_type(piece):
                        self._feedback.update_partial(self._tail)
                        return
                    self._tail += piece
                    if piece.startswith(" ") and not self._lead_sep:
                        self._lead_sep = True  # synthesized separator now at tail[0]
                self._feedback.update_partial(self._tail)
                return
            now = self._clock()
            self._diverged_text = text  # the LATEST divergent partial (never stale)
            if self._diverged_since is None:
                self._diverged_since = now  # first divergent partial opens the window
            if now - self._diverged_since < self._revision_debounce_s:
                # Transient (so far) divergence: keep the current tail on screen,
                # type nothing this cycle — if the decoder grows back past the
                # tail the next cycle is a pure EXTEND (zero backspaces).
                self._feedback.update_partial(self._tail)
                return
            # PERSISTENT divergence (>= debounce): ONE minimal-diff rewind +
            # retype with the LATEST partial (PRD §4.2quater rule 1): backspace
            # ONLY the suffix past the longest common prefix of the diff base and
            # partial — never the whole tail. A last-word wobble rewinds just that
            # word; a retract rewinds only the retracted chars; only a genuinely
            # prefix-free rewrite rewinds all. (k is measured against the diff base;
            # a synthesized leading separator is KEPT by keep_n below — it is on
            # screen before the fragment and must survive the rewind.)
            vtail = self._tail[1:] if self._lead_sep else self._tail
            k = _ci_common_prefix_len(vtail, text)
            keep_n = k + (1 if self._lead_sep else 0)
            guarded = textproc.apply_streaming_guards(
                self._guard_context(self._tail[:keep_n]), text[k:]
            )
            # press_backspace(0) is a backend no-op; _safe_backspace also guards it.
            if not self._safe_backspace(len(self._tail) - k):
                self._feedback.update_partial(self._tail)
                return  # freeze already recorded by _safe_backspace
            if guarded and not self._safe_type(guarded):
                # Rewind landed, retype did not: the screen now ends at tail[:keep_n] —
                # keep the engine string on screen truth (frozen either way).
                self._tail = self._tail[:keep_n]
                self._feedback.update_partial(self._tail)
                return
            self._tail = self._tail[:keep_n] + guarded
            # Re-arm the window: a further divergence must persist a FRESH full
            # debounce before another revision (bounded revisions per utterance).
            self._diverged_since = None
            self._diverged_text = ""
            self._feedback.update_partial(self._tail)
            return

    def _repeats_last_sentence(self, text: str) -> bool:
        """True iff `text` is a verbatim (normalized) repeat of the last COMMITTED
        sentence AND shares no common prefix with the typed tail.

        The hallucination signature from the field report: the decoder re-emits
        the PREVIOUS sentence as the final while the user's real words are already
        on screen as the tail. Narrow on purpose — BOTH conditions must hold:
        k == 0 means the normal revise path would rewind the ENTIRE tail, and the
        normalized equality (case/punctuation-insensitive, >= 8 chars) means the
        retype payload would be a duplicate of committed text. A short repeat
        ("yes." twice) never trips the >= 8-char floor; a legitimately re-dictated
        long sentence still types (it would normally share a prefix with the tail
        anyway). PURE over engine state; caller holds the lock.
        """
        prev = context_after_last_boundary(self._committed)
        if not prev:
            prev = self._committed  # no terminator yet: the whole committed text is "the last sentence"
        n_prev = _echo_norm(prev)
        if len(n_prev) < 8:
            return False
        vtail = self._tail[1:] if self._lead_sep else self._tail
        return _ci_common_prefix_len(vtail, text) == 0 and _echo_norm(text) == n_prev

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
            as _guard_context_delta). NOT debounced: commits are authoritative,
            never wobble (the revision debounce exists only for partial cycles).
          - final DIFFERS (revise/rewrite/shorter/fresh): MINIMAL-DIFF rewind (the
            same common-prefix rule as partial typing): press_backspace(len(tail) −
            k), type only the guarded corrected suffix. NOT debounced: a commit
            is once per utterance — the ONE authoritative end-of-utterance
            correction the debounced partial path defers to.
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
            if (
                not self._tail
                and self._pending_leading_space
                and self._append_space
                and text
            ):
                # CONTINUATION SEPARATOR (fresh-tail commit): same lazy-space rule as
                # on_partial — the stranded screen text needs one space before this
                # final. Applied to `text` BEFORE the extend/revise split so both
                # commit paths (an empty tail always takes the extend path) carry it.
                text = " " + text
                self._pending_leading_space = False
            space = " " if self._append_space else ""
            if self._frozen:
                # BUG-003 successor (Rev 3c): absorb WITHOUT revision keystrokes and
                # WITHOUT typing the separator either — a lone-space type_text is its
                # own tiny wtype spawn, and browsers drop those short bursts (the
                # app-dependent half of the missing-spaces report). The space is
                # carried lazily (flag) and lands glued to the next fragment's payload.
                _base = self._committed.rstrip()
                _glue = "" if (not _base or self._tail.startswith(" ")) else " "
                self._committed = _base + _glue + self._tail + space
                if space:
                    self._pending_leading_space = True
                self._tail = ""
                self._lead_sep = False
                self._suppressed = False
                self._feedback.update_partial(self._committed)
                return
            if self._tail and self._repeats_last_sentence(text):
                # SENTENCE-EATER GUARD (user report 2026-11-24): a final that is a
                # verbatim repeat of the last COMMITTED sentence while the tail
                # holds the live utterance is a context-prompt hallucination, not
                # a correction. The revise path would backspace the WHOLE tail and
                # retype the duplicate — deleting the user's real sentence and
                # replacing it with a copy of the previous one (the filed report).
                # Absorb the tail WITHOUT keystrokes instead: the screen keeps the
                # user's words, exactly like the frozen path.
                logger.warning(
                    "commit: final is a repeat of the last committed sentence "
                    "(hallucination guard) — absorbing tail, no rewind"
                )
                _base = self._committed.rstrip()
                _glue = "" if (not _base or self._tail.startswith(" ")) else " "
                self._committed = _base + _glue + self._tail + space
                if space:
                    self._pending_leading_space = True
                self._tail = ""
                self._lead_sep = False
                self._suppressed = False
                self._feedback.update_partial(self._committed)
                return
            if self._tail and _ci_startswith(text, self._tail[1:] if self._lead_sep else self._tail):
                # EXTEND: the final confirms the tail (case-insensitively, against the
                # diff base — a synthesized leading separator is not decoder text) —
                # type only the guarded delta (sliced from the ORIGINALS), with the
                # inter-final space GLUED into the same payload (never a lone spawn).
                delta = text[(len(self._tail) - (1 if self._lead_sep else 0)) :]
                guarded = ""
                if delta:
                    guarded = textproc.apply_streaming_guards(
                        self._guard_context_delta(), delta
                    )
                    if guarded:
                        if not self._safe_type(guarded + space):
                            return  # frozen by the fail-safe; tail frozen on screen
                        self._tail += guarded
                if not guarded and space:
                    # Final confirmed the tail exactly — carry the separator lazily
                    # instead of a lone-space spawn (browser-safe).
                    self._pending_leading_space = True
                typed = self._tail
            else:
                # REVISE / fresh start: minimal-diff rewind + guarded suffix retype
                # (PRD §4.2quater rule 2 — the same common-prefix rule as partial
                # typing, against the diff base; a synthesized separator is kept by
                # keep_n). A commit is authoritative — never debounced.
                _vt = self._tail[1:] if self._lead_sep else self._tail
                k = _ci_common_prefix_len(_vt, text)
                keep_n = k + (1 if self._lead_sep else 0)
                guarded = textproc.apply_streaming_guards(
                    self._guard_context(self._tail[:keep_n]), text[k:]
                )
                if not self._safe_backspace(len(self._tail) - k):
                    return  # frozen; on-screen state unknown — touch nothing further
                if guarded:
                    # Space GLUED into the retype payload (never a lone spawn).
                    if not self._safe_type(guarded + space):
                        self._tail = self._tail[:keep_n]  # screen truth after the landed rewind
                        return  # frozen mid-retype: the rewind landed, the retype did not
                elif space:
                    # Nothing to retype after the rewind — carry the separator lazily.
                    self._pending_leading_space = True
                self._tail = self._tail[:keep_n] + guarded
                self._lead_sep = self._tail.startswith(
                    " "
                )  # a synthesized separator is the only way tail[0] is a space
                typed = self._tail
            _base = self._committed.rstrip()
            _glue = "" if (not _base or typed.startswith(" ")) else " "
            self._committed = _base + _glue + typed + space
            self._tail = ""
            self._lead_sep = False
            self._suppressed = False
            self._feedback.update_partial(self._committed)

    # --- internals ---

    def _guard_context(self, tail: str) -> str:
        """Casing context for a fragment continuing `tail`: committed + " " + tail.

        The fragment continues what is already on screen — the full tail for an
        extend delta, or the KEPT tail prefix for a minimal-diff revise suffix —
        so the text preceding it, not `committed` alone, decides mid-sentence vs
        sentence-start.
        """
        parts = [p for p in (self._committed.strip(), tail) if p]
        return " ".join(parts)

    def _guard_context_delta(self) -> str:
        """Casing context for an extend delta: committed + " " + tail."""
        return self._guard_context(self._tail)

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
        """press_backspace that fails SAFE. n <= 0 is a no-op success (backend contract).

        ACCOUNTING CLAMP (the "backspaces WAY farther than it ever typed" bug): a rewind may
        NEVER delete more characters than THIS engine typed since the checkpoint — clamped
        to len(tail) with a WARNING when a caller's arithmetic exceeds it. Every rewind is
        logged at INFO (n + tail length) so the journal is an audit trail for accounting
        regressions."""
        if n > len(self._tail):
            logger.warning(
                "streaming rewind CLAMPED: asked %d, tail is only %d — deleting only ours",
                n,
                len(self._tail),
            )
            n = len(self._tail)
        if n > 0:
            logger.info("streaming rewind: %d char(s) (tail was %d)", n, len(self._tail))
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
