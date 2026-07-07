"""voice_typing.daemon — recorder construction + callback wiring (PRD §4.2, §4.4).

SCOPE (P1.M4.T1.S1): cfg_to_kwargs() + build_recorder() factory + RealtimeSTT→Feedback
callback wiring + cuda_check-gated CPU fallback. The listen-forever loop, on_final→typing,
the listening gate (set_microphone/abort), the control socket, and the main()/__main__ entry
point ALL land in later subtasks (P1.M4.T1.S2 / P1.M4.T2.S1 / P1.M4.T3.S1). This module
currently exposes ONLY the recorder-construction surface the main loop will call.

CONSTRUCT ONCE (PRD §4.2 "construct once"): AudioToTextRecorder.__init__ loads BOTH whisper
models (final + realtime) into resident memory (GPU VRAM on cuda, RAM on cpu) — seconds of
work. build_recorder() constructs exactly ONE recorder; the main loop (S2) reuses it for the
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
  - voice_typing.config.VoiceTypingConfig (P1.M2.T1.S1): cfg.asr.* (READ ONLY — never mutated).
  - voice_typing.cuda_check (P1.M1.T2.S2): resolve_device_and_models(), CUDA_DEFAULTS, CPU_FALLBACK.
  - voice_typing.feedback.Feedback (P1.M3.T2.S1): update_partial(text), set_phase(phase)
    (duck-typed; only these two methods are touched in S1).
CONSUMED BY:
  - the daemon main loop (P1.M4.T1.S2): build_recorder(cfg, feedback) once at startup.
  - install.sh CUDA smoke (P1.M6.T1.S1): may import cfg_to_kwargs.
PURE IMPORTS at module top (inspect, logging, typing, voice_typing.config, voice_typing.cuda_check).
RealtimeSTT is imported LAZILY inside build_recorder so `import voice_typing.daemon` stays cheap and
unit tests never touch torch/ctranslate2. Feedback is imported only under TYPE_CHECKING.
"""
from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable

from voice_typing import cuda_check
from voice_typing.config import VoiceTypingConfig

if TYPE_CHECKING:
    # Type hint only — never executed at runtime, so importing daemon.py is safe even while
    # feedback.py (P1.M3.T2.S1) is still absent. S1 wires only update_partial + set_phase.
    from voice_typing.feedback import Feedback

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
