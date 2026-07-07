"""voice_typing.daemon — recorder construction + callback wiring + listen-forever daemon
(PRD §4.2, §4.4).

SCOPE (P1.M4.T1.S1 + P1.M4.T1.S2):
  - S1: cfg_to_kwargs() + build_recorder() factory + RealtimeSTT→Feedback callback wiring +
    cuda_check-gated CPU fallback. The recorder is constructed ONCE so models stay resident.
  - S2: VoiceTypingDaemon — the listen-forever run() loop (the WhisperX-flaw fix: recorder.text()
    returning is normal SEGMENTATION, never session end), on_final→gate→clean→type→record, the
    listening gate (threading.Event cleared at boot → no hot-mic, PRD §4.9), and start/stop/toggle
    that arm/disarm the mic via set_microphone+abort (models stay resident → instant toggle-on).
  - LATER: control socket (P1.M4.T2.S1), full clean shutdown (P1.M4.T2.S2 — recorder.shutdown()),
    precise per-utterance latency timestamps (P1.M4.T1.S3), and the main()/__main__ entry point +
    signal handlers (P1.M4.T3.S1). These are NOT in this module yet.

CONSTRUCT ONCE (PRD §4.2 "construct once"): AudioToTextRecorder.__init__ loads BOTH whisper
models (final + realtime) into resident memory (GPU VRAM on cuda, RAM on cpu) — seconds of
work. build_recorder() constructs exactly ONE recorder; VoiceTypingDaemon reuses it for the
daemon's lifetime so a later voicectl toggle arms the mic instantly and VRAM stays resident.

CPU FALLBACK (PRD §4.4): cfg_to_kwargs() resolves device/compute_type/models via
voice_typing.cuda_check.resolve_device_and_models(), which returns the cuda config when
ctranslate2 sees a GPU, else the PRD §4.4 CPU_FALLBACK (cpu/int8/small.en/tiny.en). This is
applied BEFORE construction so the recorder is built for the right device the first time.

  KNOWN LIMITATION (not fixed here): resolve_device_and_models() probes the CUDA DRIVER only
  (ctranslate2.get_cuda_device_count) — it does NOT load cuDNN. A missing libcudnn_ops.so.9
  therefore still yields "cuda-ok", and the failure surfaces later at recorder CONSTRUCTION
  (WhisperModel load), not at resolve. A construction-failure→CPU retry is a robustness hook for
  main() (P1.M4.T3.S1) or a future task; S1 applies ONLY the verdict-based fallback above.

DEFENSIVE KWARGS (PRD §4.4 note + §8 risk "API drift"): RealtimeSTT's constructor changes across
versions. _filter_kwargs_to_signature() inspects AudioToTextRecorder.__init__'s signature and
DROPS any kwarg we computed that isn't accepted, logging a WARNING per dropped key — so an
unknown kwarg is logged-and-skipped, never a TypeError crash.

TWO ITEM CORRECTIONS vs PRD §4.4 (verified against installed RealtimeSTT v1.0.2 — see
plan/.../P1M4T1S1/research/daemon_recorder_wiring_verification.md §1):
  (a) silero: pass silero_backend="auto" (modern control; default, prefers a bundled CPU ONNX
      → already avoids the torch-hub download). DROP the legacy silero_use_onnx=True.
  (b) ensure_sentence_starting_uppercase=False + ensure_sentence_ends_with_period=False so
      textproc (P1.M2.T2.S1) owns cleanup (avoid double capitalization/period processing).

CONSUMES:
  - voice_typing.config.VoiceTypingConfig (P1.M2.T1.S1): cfg.asr.* / cfg.output.append_space /
    cfg.filter (READ ONLY — never mutated).
  - voice_typing.cuda_check (P1.M1.T2.S2): resolve_device_and_models(), CUDA_DEFAULTS, CPU_FALLBACK.
  - voice_typing.feedback.Feedback (P1.M3.T2.S1): update_partial(text), set_phase(phase) (wired by
    S1's _build_callbacks) + record_final(text), set_listening(bool) (driven by S2's daemon).
  - voice_typing.textproc (P1.M2.T2.S1): clean(text, cfg.filter) — the gate inside on_final.
  - voice_typing.typing_backends (P1.M3.T1.S1): make_backend(cfg.output).type_text(text).
CONSUMED BY:
  - the daemon main loop (P1.M4.T1.S2): build_recorder(cfg, feedback) once in VoiceTypingDaemon.__init__.
  - the control socket (P1.M4.T2.S1): VoiceTypingDaemon.toggle/start/stop/is_listening/
    uptime_s/request_shutdown.
  - the daemon entry point (P1.M4.T3.S1): VoiceTypingDaemon.run() under `if __name__ == "__main__":`.
  - install.sh CUDA smoke (P1.M6.T1.S1): may import cfg_to_kwargs.
PURE IMPORTS at module top (inspect, logging, threading, time, typing, voice_typing.config,
voice_typing.cuda_check, voice_typing.textproc, voice_typing.typing_backends — all cheap stdlib +
already-landed pure-stdlib modules). RealtimeSTT is imported LAZILY inside build_recorder so
`import voice_typing.daemon` stays cheap and unit tests never touch torch/ctranslate2. Feedback is
imported only under TYPE_CHECKING. The daemon class holds self._recorder as a REFERENCE, never
importing AudioToTextRecorder (so import purity holds).
"""
from __future__ import annotations

import inspect
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable

import voice_typing.textproc as textproc
import voice_typing.typing_backends as typing_backends
from voice_typing import cuda_check
from voice_typing.config import VoiceTypingConfig

if TYPE_CHECKING:
    # Type hint only — never executed at runtime, so importing daemon.py is safe even while
    # feedback.py (P1.M3.T2.S1) is still absent. S1 wires only update_partial + set_phase;
    # S2's VoiceTypingDaemon also calls record_final + set_listening.
    from voice_typing.feedback import Feedback
    from voice_typing.typing_backends import TypingBackend

logger = logging.getLogger(__name__)

# PRD §4.4 — fixed VAD/timing/silero values NOT exposed in config.toml. Tuning these is a
# deliberate code change (they are tightly coupled to the segmentation UX + the torch-hub
# avoidance). Mirrors the PRD §4.4 block with the two item corrections applied.
_FIXED_KWARGS: dict[str, Any] = {
    "enable_realtime_transcription": True,
    "use_main_model_for_realtime": False,   # two models — avoid contention (PRD §4.4)
    "min_length_of_recording": 0.3,
    "min_gap_between_recordings": 0.0,      # resume listening immediately
    "silero_sensitivity": 0.4,
    "webrtc_sensitivity": 3,
    "silero_backend": "auto",               # item correction (a); avoids torch-hub download
    "spinner": False,
    "use_microphone": True,                 # False + feed_audio() in tests (P1.M7.T2.S1)
    "ensure_sentence_starting_uppercase": False,  # item correction (b); textproc owns cleanup
    "ensure_sentence_ends_with_period": False,
}

# Which realtime-partial callback to wire. PREFERRED: stabilized (more accurate, slight delay).
# If stabilized proves too laggy, change this constant to "on_realtime_transcription_update"
# (faster, rougher) — single source so the swap is a one-line change (PRD §4.2; item contract).
_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"


def _resolve_device_config(cfg: VoiceTypingConfig) -> dict[str, str]:
    """Build cuda_check defaults from cfg, then resolve (applies PRD §4.4 CPU fallback).

    Returns {device, compute_type, final_model, realtime_model}. compute_type is DERIVED from
    cfg.asr.device (config.py has no compute_type field — it is a cuda_check concern) before being
    handed to cuda_check. cuda_check.resolve_device_and_models() then either keeps these defaults
    (cuda available) or overrides wholesale with CPU_FALLBACK (no cuda).
    """
    defaults = {
        "device": cfg.asr.device,
        "compute_type": "float16" if cfg.asr.device == "cuda" else "int8",
        "final_model": cfg.asr.final_model,
        "realtime_model": cfg.asr.realtime_model,
    }
    return cuda_check.resolve_device_and_models(defaults)


def cfg_to_kwargs(cfg: VoiceTypingConfig) -> dict[str, Any]:
    """Build the AudioToTextRecorder kwargs from cfg (CPU fallback already applied).

    Returns the NON-callback kwargs (model/device/timing/VAD/silero). The on_* callbacks are wired
    separately in build_recorder() (they need the Feedback instance). The only side effect is
    cuda_check.resolve_device_and_models() probing CUDA; tests monkeypatch
    voice_typing.cuda_check.resolve_device_and_models to force a path deterministically.
    """
    resolved = _resolve_device_config(cfg)
    kwargs: dict[str, Any] = {
        # model identity — cuda_check-resolved (final_model/realtime_model may be the CPU-fallback
        # small.en/tiny.en when no GPU is visible)
        "model": resolved["final_model"],
        "realtime_model_type": resolved["realtime_model"],
        "language": cfg.asr.language,
        "device": resolved["device"],
        "compute_type": resolved["compute_type"],
        # tunables that ARE in config.toml (PRD §4.5 [asr])
        "realtime_processing_pause": cfg.asr.realtime_processing_pause,
        "post_speech_silence_duration": cfg.asr.post_speech_silence_duration,
    }
    kwargs.update(_FIXED_KWARGS)
    return kwargs


def _build_callbacks(feedback: "Feedback") -> dict[str, Callable[..., None]]:
    """Wire RealtimeSTT callbacks -> Feedback (PRD §4.2; item contract point 3).

      on_realtime_transcription_stabilized(str) -> feedback.update_partial(text)
      on_vad_detect_start() -> feedback.set_phase("listening")   # system starts listening for VAD
      on_vad_start()        -> feedback.set_phase("speaking")    # voice activity detected
      on_vad_stop()         -> feedback.set_phase("listening")   # voice ended -> back to listening

    Callbacks are simple direct delegations (no try/except) — Feedback is designed robust and the
    on_final typing-error handling belongs to S2, not these partial/VAD hooks.
    """
    return {
        _PARTIAL_CALLBACK_ATTR: lambda text: feedback.update_partial(text),
        "on_vad_detect_start": lambda: feedback.set_phase("listening"),
        "on_vad_start": lambda: feedback.set_phase("speaking"),
        "on_vad_stop": lambda: feedback.set_phase("listening"),
    }


def _filter_kwargs_to_signature(
    kwargs: dict[str, Any], recorder_cls: type
) -> dict[str, Any]:
    """Drop kwargs not accepted by recorder_cls.__init__ (defensive vs RealtimeSTT API drift).

    PRD §4.4 note + item contract: an unknown kwarg must be logged-and-skipped, never a crash.
    Inspects the constructor signature; logs a WARNING per dropped key. If the class declares
    **kwargs (VAR_KEYWORD) it accepts ANY name -> return everything verbatim (correct, and makes
    fakes trivial). The real AudioToTextRecorder has an explicit 85-param signature (no **kwargs),
    so the strict-drop path applies in production.
    """
    params = inspect.signature(recorder_cls.__init__).parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(kwargs)  # class accepts arbitrary kwargs — nothing to filter
    valid = set(params) - {"self"}
    accepted: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in kwargs.items():
        if key in valid:
            accepted[key] = value
        else:
            dropped.append(key)
    if dropped:
        logger.warning(
            "AudioToTextRecorder: dropping %d unsupported kwarg(s) %r "
            "(not in the installed constructor signature); construction proceeds without them.",
            len(dropped),
            dropped,
        )
    return accepted


def _construct(
    cfg: VoiceTypingConfig, feedback: "Feedback", recorder_cls: type
) -> Any:
    """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

    Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
    RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
    supplies the real AudioToTextRecorder via a lazy import.
    """
    kwargs = cfg_to_kwargs(cfg)
    kwargs.update(_build_callbacks(feedback))
    filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
    return recorder_cls(**filtered)


def build_recorder(cfg: VoiceTypingConfig, feedback: "Feedback") -> Any:
    """Construct ONE AudioToTextRecorder wired to feedback (PRD §4.2, §4.4).

    Resolves device/models (CPU fallback), builds kwargs + callbacks, defensively filters to the
    installed RealtimeSTT signature, then constructs the recorder. Model load happens HERE (in
    __init__) and stays resident — the main loop (P1.M4.T1.S2) reuses this single recorder for the
    daemon's lifetime. Returns the constructed AudioToTextRecorder.

    Heavy: imports RealtimeSTT + loads models on first call (seconds). Unit tests call _construct()
    with a fake class instead; this function is exercised by the feed_audio test (P1.M7.T2.S1) and
    the real daemon startup (P1.M4.T1.S2).
    """
    from RealtimeSTT import AudioToTextRecorder  # lazy: keeps `import voice_typing.daemon` cheap

    return _construct(cfg, feedback, AudioToTextRecorder)


class VoiceTypingDaemon:
    """The listen-forever daemon core: recorder loop + on_final→type + listening gate + toggle.

    PRD §4.2 items 1+2. run() is the main-thread loop that fixes the WhisperX flaw: recorder.text()
    returning is normal SEGMENTATION, never session end (PRD §1 #1). on_final gates→cleans→types→records.
    start/stop/toggle arm/disarm the mic via set_microphone+abort (models stay resident → instant
    toggle-on). NEVER recorder.shutdown() on toggle/stop — only on quit (P1.M4.T2.S2).
    """

    def __init__(
        self,
        cfg: VoiceTypingConfig,
        feedback: "Feedback",
        *,
        recorder: Any = None,
        backend: "TypingBackend | None" = None,
    ) -> None:
        self._cfg = cfg
        self._feedback = feedback
        self._lock = threading.Lock()
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
        self._shutdown = threading.Event()    # cleared → keep looping
        self._start_monotonic: float | None = None
        # construct-once (PRD §4.2): build recorder ONCE so models stay resident + toggle/start/stop
        # can arm the mic immediately. Injectable for unit tests (fakes → cheap, no RealtimeSTT).
        self._recorder = recorder if recorder is not None else build_recorder(cfg, feedback)
        self._backend = (
            backend if backend is not None else typing_backends.make_backend(cfg.output)
        )

    def run(self) -> None:
        """The listen-forever loop (main thread, BLOCKS until shutdown)."""
        self._start_monotonic = time.monotonic()
        self._feedback.set_listening(False)   # PRD §4.9: starts NOT listening (no hot-mic on boot)
        logger.info("voice-typing daemon ready (not listening); recorder resident")
        while not self._shutdown.is_set():
            if self._listening.is_set():
                # blocks until ONE utterance finalizes → on_final in a NEW thread → returns → re-listen.
                # Returning is NORMAL SEGMENTATION, never session end (the WhisperX-flaw fix, PRD §1 #1).
                self._recorder.text(self.on_final)
            else:
                time.sleep(0.05)
        logger.info("shutdown requested; run() loop exiting")

    def on_final(self, text: str) -> None:
        """Gate → clean → type → record. Fired by RealtimeSTT in a NEW thread (never raise)."""
        if not self._listening.is_set():       # GATE: race guard (PRD §4.2/§8 — utterance may
            return                             #   complete right after stop)
        cleaned = textproc.clean(text, self._cfg.filter)
        if not cleaned:                        # rejected: blocklist hallucination / below min_chars
            return
        payload = cleaned + (" " if self._cfg.output.append_space else "")
        try:
            self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
        except Exception:
            logger.exception("typing backend failed for final %r", cleaned)
        self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
        logger.info("final typed: %r", cleaned)
        # NOTE: precise latency timestamps (t_speech_end/t_final_ready/t_typed) land in P1.M4.T1.S3.

    def _arm(self) -> None:
        """Private: arm mic + set listening + notify. Called under the lock by start/toggle."""
        self._listening.set()
        self._recorder.set_microphone(True)
        self._feedback.set_listening(True)

    def _disarm(self) -> None:
        """Private: disarm mic + abort blocked text() + clear listening + notify. Called under lock."""
        self._listening.clear()
        self._recorder.set_microphone(False)
        self._recorder.abort()      # breaks any blocked text() so the loop re-checks the cleared gate
        self._feedback.set_listening(False)

    def start(self) -> None:
        with self._lock:
            self._arm()

    def stop(self) -> None:
        with self._lock:
            self._disarm()

    def toggle(self) -> None:
        with self._lock:
            if self._listening.is_set():
                self._disarm()
            else:
                self._arm()

    def request_shutdown(self) -> None:
        """Signal run() to exit. Sets the event + aborts (breaks a blocked text()). NO shutdown()."""
        self._shutdown.set()
        with self._lock:
            self._recorder.abort()    # break any blocked text() so run() can return
        # recorder.shutdown() (full teardown) is wired by the quit handler in P1.M4.T2.S2, NOT here.

    def is_listening(self) -> bool:
        return self._listening.is_set()

    @property
    def uptime_s(self) -> float:
        return (
            time.monotonic() - self._start_monotonic
            if self._start_monotonic is not None
            else 0.0
        )
