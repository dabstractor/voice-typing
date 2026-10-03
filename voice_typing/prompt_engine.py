"""voice_typing.prompt_engine — child-side dynamic context-prompt transcription executor.

P1.M2.T5.S1 (PRD §4.2quater "Rolling context prompt"): Whisper decodes each utterance as a
fresh sentence, so mid-paragraph fragments come out capitalized with spurious trailing
punctuation. The fix is conditioning EVERY decode (realtime partials AND commit/final passes)
on the rolling committed context — a runtime-mutable `initial_prompt`.

WHY AN EXECUTOR (verified line-by-line against the installed RealtimeSTT 1.0.2):
  - `initial_prompt` / `initial_prompt_realtime` are constructor-STATIC in RealtimeSTT (its
    transcription worker copies them at spawn), and on our single-model path
    (use_main_model_for_realtime=True) even the realtime-engine attribute poke is unavailable —
    post-construction attribute assignment is inert. BUT RealtimeSTT accepts EXTERNAL
    transcription executors: AudioToTextRecorder(transcription_executor=...,
    realtime_transcription_executor=...) — and BOTH decode paths route through it:
      * finals: core/transcription.py call_transcription_executor() calls
        executor.transcribe(audio, language=..., use_prompt=...) on an in-process thread;
      * realtime partials: core/realtime.py _transcribe_with_main_model() checks
        _uses_external_transcription_executor FIRST, even under use_main_model_for_realtime=True.
    With an executor set, RealtimeSTT never spawns its TranscriptionWorker process
    (core/initialization.py sets transcript_process = None) — so ONE PromptedExecutor owns the
    ONE faster-whisper model for partials AND finals (PRD §4.2quater single-mode; the built-in
    warmup lives in that skipped worker, so executor warmup is OUR job — hence the probe).
  - Executor call contract: transcribe(audio, language=None, use_prompt=True) returning an
    object with .text and .info; the consumer reads .info.language /
    .info.language_probability (core/transcription_api.py:113-115).

IMPORT PURITY: this module is importable ANYWHERE — module scope is stdlib-only (dataclasses,
logging, threading); faster_whisper + numpy are imported LAZILY inside methods, so importing
the module never touches CUDA. The executor OBJECTS, however, own CUDA contexts and are not
picklable: they are CONSTRUCTED only inside the recorder-host child process (P1.M2.T5.S1
wiring in recorder_host.augment_kwargs_with_executor) and never cross the spawn IPC.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Defensive prompt cap (PRD §4.2quater): Whisper accepts an initial_prompt of up to ~224
# tokens; 200 whitespace words is a cheap conservative proxy (a CODE CONSTANT per the PRP —
# tuning it is a deliberate change, not a config knob). Keeps prompt + audio inside the
# decoder window on even long utterances.
_PROMPT_TOKEN_CAP = 200

# Sentence terminators that end the rolling context window (P1.M2.T5.S2). Pinned
# verbatim to textproc._SENTENCE_TERMINALS (repo convention — streaming.py pins
# the same copy for its slicer); the three sets must never drift apart.
_CONTEXT_BOUNDARY_CHARS = ".!?"

# Capability-probe warmup: 1 s of 16 kHz float32 zeros — enough to force the model build +
# CUDA context init + one full encode/decode pass, so probe failures surface at READY time
# instead of on the first arm.
_WARMUP_SAMPLE_RATE = 16000
_WARMUP_SECONDS = 1.0


@dataclass
class TranscriptionInfo:
    """Duck-typed stand-in for RealtimeSTT's transcription_engines.base.TranscriptionInfo.

    Upstream reads result.info.language / result.info.language_probability only. A local copy
    (NOT an import: `import RealtimeSTT` pulls torch/CUDA into the importing process, which
    would break the daemon's import purity) so the empty-result degrade path always has an
    info object. When faster_whisper runs for real, its own richer info object passes
    straight through this field (structural typing — consumers only read attributes).
    """

    language: str | None = None
    language_probability: float = 0.0


@dataclass
class TranscriptionResult:
    """Duck-typed stand-in for RealtimeSTT's transcription_engines.base.TranscriptionResult.

    call_transcription_executor accepts ANY object from executor.transcribe(); the finals
    consumer reads .text (and .info per above). Structurally identical to the upstream
    dataclass (text: str, info with a default).
    """

    text: str
    info: Any = field(default_factory=TranscriptionInfo)


@dataclass(frozen=True)
class PromptProbeResult:
    """Startup capability-probe outcome — drives arm-vs-degrade in recorder_host.

    ok=True  -> the executor is warm; arm it into the recorder kwargs.
    ok=False -> `error` carries repr(exc); recorder_host logs ONE INFO degrade line and
                builds the recorder with stock (context-free) kwargs — never a crash.
    """

    ok: bool
    error: str | None = None


def trim_prompt(text: str, cap: int = _PROMPT_TOKEN_CAP) -> str:
    """Whitespace-normalize `text` and keep only the NEWEST `cap` whitespace tokens.

    Pure function (unit-tested). Split on whitespace; when more than `cap` tokens, keep the
    TAIL — the newest words are the live sentence context ("continuing, not starting"), the
    oldest words are the first to go. Rejoined with single spaces (canonical form). Non-str
    input or cap <= 0 degrades safely: "" (tokens[-0:] would wrongly keep everything, so the
    guard is explicit).
    """
    if cap <= 0:
        return ""
    tokens = (text or "").split()
    if len(tokens) <= cap:
        return " ".join(tokens)
    return " ".join(tokens[-cap:])


def rolling_context_prompt(committed: str) -> str:
    """The formal daemon-side rolling context prompt (PRD §4.2quater; P1.M2.T5.S2).

    The committed text back to the last sentence boundary, whitespace-normalized,
    capped to the NEWEST _PROMPT_TOKEN_CAP tokens (via trim_prompt — the child
    caps again in set_prompt: defense in depth, same constant):
      - terminator mid-string       -> the text after it (the in-progress sentence);
      - committed ENDS with one     -> "" (fresh sentence — decoder may capitalize);
      - NO terminator anywhere      -> the WHOLE committed text (capped). This is
        the T8c pause-join case: a long unpunctuated run still conditions the
        next decode (the old thin-seam slicer returned "" here — superseded).

    PURE: no I/O, no state, deterministic, stdlib-only. Never raises — None or
    empty input degrades to "". The rfind lives HERE, not in the caller: the
    composition `context_after_last_boundary(c) or trim_prompt(c)` is WRONG
    because "" is ambiguous between the ends-with-terminator case (prompt stays
    empty) and the no-boundary case (prompt must be everything).
    """
    committed = committed or ""
    last = max(committed.rfind(ch) for ch in _CONTEXT_BOUNDARY_CHARS)
    source = committed[last + 1 :] if last >= 0 else committed
    return trim_prompt(source)


class PromptedExecutor:
    """Object-style RealtimeSTT executor: ONE faster-whisper model + a thread-safe mutable prompt.

    The child passes the SAME instance as BOTH transcription_executor and
    realtime_transcription_executor (one object == one model instance serving partials and
    finals; RealtimeSTT skips its TranscriptionWorker process entirely).

    Threading: RealtimeSTT calls transcribe() from the realtime-partial thread AND from the
    external-final threads concurrently — every model access holds self._lock. Prompt updates
    (set_prompt) happen between utterances from the child's command loop; the decode reads the
    current value under the lock, so no decode ever sees a half-updated prompt.

    Failure contract (PRD §8 "degrade to context-free decoding + log, never crash"):
    transcribe() NEVER raises — any failure is logged (WARNING + traceback) and an empty
    result is returned. warmup() is the deliberate exception: it RAISES so the startup
    capability probe can distinguish healthy from broken and degrade BEFORE the recorder is
    built.
    """

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        beam_size: int = 5,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._model: Any = (
            None  # faster_whisper.WhisperModel — built lazily (CUDA import)
        )
        self._prompt: str | None = None
        self._lock = threading.Lock()

    # --- prompt management (child cmd ("prompt", {"text": ...}) -> set_prompt) -----------

    def set_prompt(self, text: str | None) -> None:
        """Replace the rolling context prompt (whitespace-trimmed to the cap). None/"" clears.

        Never raises (a bad update is logged and the previous prompt kept) and never logs the
        prompt TEXT above DEBUG — it is user dictation content.
        """
        try:
            trimmed = trim_prompt(text) if text else None
            self._prompt = trimmed
            logger.debug(
                "context-prompt: set (%d words)",
                0 if trimmed is None else len(trimmed.split()),
            )
        except Exception:  # noqa: BLE001 — prompt updates must never break the cmd loop
            logger.exception("context-prompt: set_prompt failed (previous prompt kept)")

    @property
    def prompt(self) -> str | None:
        """The current (trimmed) prompt, or None when cleared."""
        return self._prompt

    # --- capability probe ----------------------------------------------------------------

    def warmup(self) -> None:
        """CAPABILITY PROBE: build the model + transcribe 1 s of 16 kHz float32 zeros.

        RAISES on any failure (model build, CUDA init, decode) — recorder_host's
        augment_kwargs_with_executor folds that into a degrade. Exercising a REAL transcribe
        (not just the constructor) is the point: it surfaces CUDA/encoder failures at READY
        time instead of on the first arm.
        """
        import numpy as np  # lazy: keeps the module import CUDA-free

        audio = np.zeros(int(_WARMUP_SECONDS * _WARMUP_SAMPLE_RATE), dtype="float32")
        self._transcribe_locked(audio, language=None, use_prompt=True)

    # --- RealtimeSTT executor entry point -------------------------------------------------

    def transcribe(
        self,
        audio: Any,
        language: str | None = None,
        use_prompt: bool = True,
        **_kwargs: Any,
    ) -> TranscriptionResult:
        """Transcribe `audio` conditioned on the current prompt. NEVER raises.

        Signature mirrors RealtimeSTT's call_transcription_executor call shape
        (audio positional; language/use_prompt keyword; **_kwargs accepted defensively so a
        future RealtimeSTT that adds args cannot crash us). use_prompt=False (or a cleared
        prompt) sends initial_prompt=None — the context-free decode.

        On ANY failure: log WARNING + return an EMPTY result (degrade-not-fail); RealtimeSTT's
        partial/final paths just see no text for that pass.
        """
        try:
            return self._transcribe_locked(audio, language, use_prompt)
        except Exception:  # noqa: BLE001 — deliberate: executor errors must never crash the child
            logger.warning(
                "context-prompt: transcribe failed; returning empty result",
                exc_info=True,
            )
            return TranscriptionResult(text="")

    # --- internals -------------------------------------------------------------------------

    def _build_model(self) -> Any:
        """Lazily construct the faster_whisper.WhisperModel (lazy import: child-only CUDA)."""
        import faster_whisper  # lazy: module import must stay CUDA-free (IMPORT PURITY)

        logger.debug(
            "context-prompt: building WhisperModel (model=%s device=%s compute_type=%s)",
            self._model_name,
            self._device,
            self._compute_type,
        )
        return faster_whisper.WhisperModel(
            model_size_or_path=self._model_name,
            device=self._device,
            compute_type=self._compute_type,
        )

    def _transcribe_locked(
        self, audio: Any, language: str | None, use_prompt: bool
    ) -> TranscriptionResult:
        """One model call under self._lock. RAISES on failure — transcribe() swallows, warmup() propagates.

        The call shape mirrors RealtimeSTT's faster_whisper_engine (language, initial_prompt,
        beam_size, vad_filter) with ONE deliberate difference: condition_on_previous_text=False
        — WE own the cross-utterance context via initial_prompt; whisper's own previous-window
        conditioning would double-condition and drift.
        """
        with self._lock:
            if self._model is None:
                self._model = self._build_model()
            segments, info = self._model.transcribe(
                audio,
                language=language or None,
                initial_prompt=self._prompt if use_prompt else None,
                beam_size=self._beam_size,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            # Text assembly mirrors faster_whisper_engine.py: join segment texts, strip.
            text = " ".join(segment.text for segment in segments).strip()
            return TranscriptionResult(text=text, info=info)


def probe_prompt_executor(executor: PromptedExecutor) -> PromptProbeResult:
    """Run the executor's warmup and fold ANY exception into a PromptProbeResult.

    This is the startup capability probe recorder_host consumes: ok=True -> arm the executor
    into the recorder kwargs; ok=False -> stock kwargs + ONE INFO degrade line. Never raises.
    """
    try:
        executor.warmup()
    except Exception as exc:  # noqa: BLE001 — the probe's whole point is catching anything
        return PromptProbeResult(ok=False, error=repr(exc))
    return PromptProbeResult(ok=True)
