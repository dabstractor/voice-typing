"""voice_typing.streaming — phone-style streaming output engine (PRD §4.2quater R1).

Turns stabilized realtime partials from the recorder-host child into live typed
dictation. On every stabilized partial, diff it against the tentatively typed
tail:

  - EXTEND (old tail is a prefix of the new partial): type ONLY the delta, with
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
§4.2quater), so the safest S1 response is to stop revising that utterance. The
feedback mirror keeps updating. T6.S3 formalizes freeze triggers.

THREAD CONTEXT: on_partial is called from the host reader (daemon) thread; commit
will come from the on_final thread (T6.S2); cancel()/pending_tail_len() from the
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


class StreamingOutput:
    """Per-armed-session streaming output state machine (PRD §4.2quater R1).

    State (all under self._lock):
        committed: finalized text through the last commit checkpoint (S1 only
            maintains the field + a read-only property; T6.S2 advances it on
            commit). Read by the guards as the casing context.
        tail: everything typed since that checkpoint — tentative, revisable,
            NEVER ending with a space. Length == exactly the chars a rewind
            must delete.
        frozen: True -> on_partial does NO backend calls, mirror-only (set by
            freeze() or by a backend failure). NOT auto-cleared by
            reset_boundary() — T6.S3 owns the freeze lifecycle.
        suppressed: True after reset_after_cancel() -> mirror-only until the
            next utterance boundary, so a stale late partial from the cancelled
            utterance cannot re-type text right after a cancel.
    """

    def __init__(
        self,
        backend,
        feedback,
        streaming: bool,
        *,
        rate_limit_s: float = _FULL_REWIND_RATE_LIMIT_S,
        clock=time.monotonic,
    ) -> None:
        """Args:
        backend: a TypingBackend (type_text / press_backspace).
        feedback: object exposing update_partial(text) (voice_typing.feedback.Feedback
            or a test double). Called once per on_partial event.
        streaming: the cfg.output.streaming flag; False = mirror-only Rev 1
            behavior (tail stays "", raw partial mirrored verbatim).
        rate_limit_s: minimum spacing between full rewinds (override only in tests).
        clock: monotonic time source (injectable for deterministic rate-limit tests).
        """
        self._backend = backend
        self._feedback = feedback
        self._streaming = bool(streaming)
        self._rate_limit_s = float(rate_limit_s)
        self._clock = clock
        self._lock = threading.Lock()
        self._committed: str = ""
        self._tail: str = ""
        self._frozen: bool = False
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

    # --- lifecycle (daemon.cancel() seam — exact names are load-bearing) ---

    def pending_tail_len(self) -> int:
        """Chars of tentative tail typed since the last checkpoint. 0 = nothing pending."""
        with self._lock:
            return len(self._tail)

    def reset_after_cancel(self) -> None:
        """Fresh tail at the current cursor after a Backspace-cancel; committed UNCHANGED.

        Also sets `suppressed`: until the next reset_boundary(), on_partial mirrors
        only — a stale late partial from the cancelled utterance must not re-type
        the fragment the user just deleted.
        """
        with self._lock:
            self._tail = ""
            self._suppressed = True

    def reset_boundary(self) -> None:
        """New utterance boundary: clear the tail and lift the post-cancel suppression.

        `frozen` is deliberately NOT cleared here — the freeze lifecycle (stranded
        tail, user keypress, ...) is P1.M2.T6.S3's concern.
        """
        with self._lock:
            self._tail = ""
            self._suppressed = False

    def freeze(self, reason: str = "") -> None:
        """Stop typing (mirror-only) for the rest of this utterance; log why."""
        with self._lock:
            if self._frozen:
                return
            self._frozen = True
        logger.warning("streaming output frozen (%s)", reason or "unspecified")

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
                # Frozen (freeze() or a backend failure): mirror the typed tail only.
                self._feedback.update_partial(self._tail)
                return

            # Stable normalization: collapse any whitespace run to single spaces and
            # strip the ends — the same shape textproc.clean produces, so prefix
            # diffing is stable and a trailing-space waffle is a no-op.
            text = " ".join(text.split())

            if self._tail and text.startswith(self._tail):
                # EXTEND: tail is a prefix -> type only the guarded delta.
                delta = text[len(self._tail) :]
                if not delta:
                    self._feedback.update_partial(self._tail)
                    return
                guarded = textproc.apply_streaming_guards(self._guard_context_delta(), delta)
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
            logger.warning(
                "streaming type_text(%r) failed (%s); freezing tail", s, exc
            )
            self._frozen = True
            return False

    def _safe_backspace(self, n: int) -> bool:
        """press_backspace that fails SAFE. n <= 0 is a no-op success (backend contract)."""
        if n <= 0:
            return True
        try:
            self._backend.press_backspace(n)
            return True
        except Exception as exc:  # noqa: BLE001 — the reader thread must survive
            logger.warning("streaming press_backspace(%d) failed (%s); freezing", n, exc)
            self._frozen = True
            return False
