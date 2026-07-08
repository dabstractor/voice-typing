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

import collections
import inspect
import json
import logging
import os
import select
import signal
import socket
import sys
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
    "no_log_file": True,  # bugfix Issue 1: suppress RealtimeSTT's unbounded realtimesst.log (PRD §4.2 sole path = stderr→journald)
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


def cfg_to_kwargs(
    cfg: VoiceTypingConfig, *, resolved: dict[str, str] | None = None
) -> dict[str, Any]:
    """Build the AudioToTextRecorder kwargs from cfg (CPU fallback already applied).

    Returns the NON-callback kwargs (model/device/timing/VAD/silero). The on_* callbacks are wired
    separately in build_recorder() (they need the Feedback instance).

    `resolved` ({device,compute_type,final_model,realtime_model} | None): when given, use it
    INSTEAD of calling _resolve_device_config(cfg). The force_cpu path (bugfix Issue 3 /
    P1.M1.T3.S1) passes dict(cuda_check.CPU_FALLBACK) here so the cuda_check driver probe is
    SKIPPED entirely and kwargs are built straight from the PRD §4.4 CPU config (no ctranslate2
    import / no driver probe during a CPU retry). Default None resolves via cuda_check (the
    normal path — the only side effect is cuda_check.resolve_device_and_models() probing CUDA;
    tests monkeypatch it to force a path deterministically).
    """
    if resolved is None:
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


def _build_callbacks(
    feedback: "Feedback", latency: "LatencyLog | None" = None
) -> dict[str, Callable[..., None]]:
    """Wire RealtimeSTT callbacks -> Feedback (+ optional LatencyLog; PRD §4.2; P1.M4.T1.S3).

      on_realtime_transcription_stabilized(str) -> feedback.update_partial(text) [+ latency.note_partial]
      on_vad_detect_start() -> feedback.set_phase("listening")   # system starts listening for VAD
      on_vad_start()        -> feedback.set_phase("speaking")    # voice activity detected
      on_vad_stop()         -> feedback.set_phase("listening")   # voice ended -> back to listening
                           [+ latency.note_speech_end  (t_speech_end for the latency log)]

    `latency` is OPTIONAL (default None) so S1's callers (1-arg) keep working unchanged: when None,
    the partial/on_vad_stop callbacks behave exactly as S1 (no extra side effect). VoiceTypingDaemon
    passes its LatencyLog so the per-utterance latency log gets t_speech_end + partial count.
    """
    def _partial(text: str) -> None:
        feedback.update_partial(text)
        if latency is not None:
            latency.note_partial(text)

    def _vad_stop() -> None:
        feedback.set_phase("listening")
        if latency is not None:
            latency.note_speech_end()

    return {
        _PARTIAL_CALLBACK_ATTR: _partial,
        "on_vad_detect_start": lambda: feedback.set_phase("listening"),
        "on_vad_start": lambda: feedback.set_phase("speaking"),
        "on_vad_stop": _vad_stop,
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
    cfg: VoiceTypingConfig,
    feedback: "Feedback",
    recorder_cls: type,
    latency: "LatencyLog | None" = None,
    force_cpu: bool = False,
) -> Any:
    """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

    Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
    RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
    supplies the real AudioToTextRecorder via a lazy import. `latency` (optional, default None) is
    threaded into _build_callbacks so on_vad_stop/partial feed the per-utterance latency log.

    force_cpu (bugfix Issue 3 / P1.M1.T3.S1, default False): when True, replace the resolved
    device dict with dict(cuda_check.CPU_FALLBACK) BEFORE building kwargs — this SKIPS the
    _resolve_device_config / cuda_check path entirely (no driver probe, no ctranslate2 import)
    so the CPU retry in main() (P1.M1.T3.S2) never re-touches a GPU whose construction just
    failed. The recorder is then built with the exact PRD §4.4 degraded config (device=cpu,
    compute_type=int8, final_model=small.en, realtime_model=tiny.en). The NON-device kwargs
    (language, timing, _FIXED_KWARGS) still come from cfg as usual; only device/compute_type/
    models are overridden. Consumed via build_recorder(..., force_cpu=True).
    """
    resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None
    kwargs = cfg_to_kwargs(cfg, resolved=resolved)
    kwargs.update(_build_callbacks(feedback, latency))
    filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
    return recorder_cls(**filtered)


def build_recorder(
    cfg: VoiceTypingConfig,
    feedback: "Feedback",
    latency: "LatencyLog | None" = None,
    force_cpu: bool = False,
) -> Any:
    """Construct ONE AudioToTextRecorder wired to feedback (+ optional latency) (PRD §4.2, §4.4).

    Resolves device/models (CPU fallback), builds kwargs + callbacks, defensively filters to the
    installed RealtimeSTT signature, then constructs the recorder. Model load happens HERE (in
    __init__) and stays resident — the main loop (P1.M4.T1.S2) reuses this single recorder for the
    daemon's lifetime. `latency` (optional) threads the per-utterance collector into on_vad_stop/
    partial. Returns the constructed AudioToTextRecorder.

    Heavy: imports RealtimeSTT + loads models on first call (seconds). Unit tests call _construct()
    with a fake class instead; this function is exercised by the feed_audio test (P1.M7.T2.S1) and
    the real daemon startup (P1.M4.T1.S2).

    `force_cpu=True` (bugfix Issue 3 / P1.M1.T3.S1) builds a CPU-only recorder from
    cuda_check.CPU_FALLBACK without probing CUDA — the construction-failure retry hook for
    main() (P1.M1.T3.S2). Default False (the normal CUDA/CPU-fallback path).
    """
    from RealtimeSTT import AudioToTextRecorder  # lazy: keeps `import voice_typing.daemon` cheap

    return _construct(cfg, feedback, AudioToTextRecorder, latency, force_cpu=force_cpu)


# --- Control socket path resolution (P1.M4.T2.S1; PRD §4.2(3)) -------------------------------
# The voicectl<->daemon control socket lives at $XDG_RUNTIME_DIR/voice-typing/control.sock
# (AF_UNIX SOCK_STREAM; owner-only — dir 0700 + socket file 0600 enforced by ControlServer).
# Mirrors FeedbackConfig.resolved_state_file(): raise if XDG_RUNTIME_DIR is unset (no safe
# default — fail clearly rather than bind a socket to a wrong path). Tests pass socket_path=.
_CONTROL_SOCKET_SUBPATH = ("voice-typing", "control.sock")  # under $XDG_RUNTIME_DIR


def _default_control_socket_path() -> str:
    """Resolve $XDG_RUNTIME_DIR/voice-typing/control.sock (PRD §4.2(3)).

    Mirrors FeedbackConfig.resolved_state_file(): raises RuntimeError if XDG_RUNTIME_DIR is
    unset/empty (no safe default — fail clearly rather than bind a socket to a wrong path).
    Production runs under a systemd user session (XDG_RUNTIME_DIR=/run/user/$UID, 0700). Tests
    pass an explicit socket_path so they never hit this.
    """
    xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if not xdg:
        raise RuntimeError(
            "XDG_RUNTIME_DIR is not set; cannot resolve the control socket path. "
            "Pass socket_path= explicitly, or run under a session that exports "
            "XDG_RUNTIME_DIR (systemd user sessions set it)."
        )
    return os.path.join(xdg, *_CONTROL_SOCKET_SUBPATH)


# --- Per-utterance latency logging (P1.M4.T1.S3; PRD §4.2 logging, §6 latency targets) ---------
# A bounded ring buffer of recent utterance records + a structured log line the latency tests parse.
# t_speech_end comes from the on_vad_stop callback (threaded in via _build_callbacks); t_final_ready
# / t_typed come from on_final. All delta timestamps are time.monotonic() (NTP-safe); ts is wall epoch.
_LATENCY_LOG_PREFIX = "voice-typing latency:"   # STABLE prefix — T1 greps this (do not rename)
_LATENCY_RING_SIZE = 64


def _ms(seconds: float) -> float:
    """Seconds → milliseconds, rounded to 0.1 ms (log readability + stable parse)."""
    return round(seconds * 1000.0, 1)


class LatencyLog:
    """Per-utterance latency capture for the latency tests (PRD §6 T1/T3; PRD §4.2 logging).

    Fed by RealtimeSTT callbacks (note_partial/note_speech_end — wired via _build_callbacks) and by
    VoiceTypingDaemon.on_final (finalize_utterance). Timestamps are time.monotonic() (delta-safe vs
    NTP); a wall epoch `ts` is added for journal correlation. A bounded ring buffer (deque maxlen) of
    recent records is queryable via snapshot() (future status cmd, P1.M4.T2.S1) + by tests.

    Thread-safe: note_partial fires on the realtime thread, note_speech_end on the VAD thread,
    finalize_utterance on the on_final worker thread, snapshot() on the socket thread — all short,
    guarded by self._lock.
    """

    def __init__(self, *, ring_size: int = _LATENCY_RING_SIZE) -> None:
        self._lock = threading.Lock()
        self._records: collections.deque = collections.deque(maxlen=ring_size)
        self._partial_count = 0
        self._t_speech_end: float | None = None

    def note_partial(self, _text: str) -> None:
        """Count a realtime partial (partial CADENCE is T1's own measurement; we just count)."""
        with self._lock:
            self._partial_count += 1

    def note_speech_end(self) -> None:
        """Record t_speech_end (on_vad_stop — VAD closed = speech ended)."""
        with self._lock:
            self._t_speech_end = time.monotonic()

    def finalize_utterance(self, *, text: str, t_final_ready: float, t_typed: float) -> dict:
        """Build + store the per-utterance record; reset counters; return the record for logging.

        t_speech_end may be None (no on_vad_stop seen) → the two *_ms fields derived from it are None
        (rendered 'n/a' in the log line); final_to_typed_ms is always numeric.
        """
        with self._lock:
            t_speech_end = self._t_speech_end
            partials = self._partial_count
            self._partial_count = 0
            self._t_speech_end = None
        record = {
            "event": "utterance_final",
            "t_speech_end": t_speech_end,
            "t_final_ready": t_final_ready,
            "t_typed": t_typed,
            "speech_end_to_final_ms": _ms(t_final_ready - t_speech_end)
                if t_speech_end is not None else None,
            "final_to_typed_ms": _ms(t_typed - t_final_ready),
            "total_ms": _ms(t_typed - t_speech_end) if t_speech_end is not None else None,
            "partials": partials,
            "text": text,
            "ts": time.time(),
        }
        with self._lock:
            self._records.append(record)
        return record

    def snapshot(self) -> list[dict]:
        """Newest-last copy of the ring buffer (for status + tests)."""
        with self._lock:
            return list(self._records)


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
        latency: "LatencyLog | None" = None,
        mic_prober: Callable[[], tuple[bool, str | None]] | None = None,
    ) -> None:
        self._cfg = cfg
        self._feedback = feedback
        self._lock = threading.Lock()
        # Serializes on_final callbacks (bugfix Issue 5 / P1.M2.T2.S1). RealtimeSTT fires each
        # on_final in a NEW thread without joining, so a second final can arrive while a slow
        # type_text is still running. SEPARATE from _lock: a slow type_text must not stall
        # toggle/start/stop (which take _lock via _arm/_disarm), and on_final never takes _lock
        # (nor do _arm/_disarm call on_final) -> no lock-ordering deadlock. Held across clean→
        # type→record→log; the gate check stays OUTSIDE (read-only race guard).
        self._on_final_lock = threading.Lock()
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
        self._shutdown = threading.Event()    # cleared → keep looping
        self._start_monotonic: float | None = None
        # Per-utterance latency collector (P1.M4.T1.S3): fed by on_vad_stop/partial (via
        # build_recorder→_build_callbacks) + on_final. Injectable for tests; a real one otherwise.
        self._latency = latency if latency is not None else LatencyLog()
        # construct-once (PRD §4.2): build recorder ONCE so models stay resident + toggle/start/stop
        # can arm the mic immediately. Injectable for unit tests (fakes → cheap, no RealtimeSTT).
        # Pass self._latency so on_vad_stop/partial feed the latency log (PRD §4.2; P1.M4.T1.S3).
        self._recorder = (
            recorder if recorder is not None else build_recorder(cfg, feedback, self._latency)
        )
        self._backend = (
            backend if backend is not None else typing_backends.make_backend(cfg.output)
        )
        # Mic health probe (bugfix Issue 2 / P1.M1.T2.S1): detect a dead/missing mic so status
        # (P1.M1.T2.S2) can surface it instead of silently reporting "listening: on". Injectable
        # (mic_prober=) so unit tests stay hermetic — NO real PyAudio/CUDA in the test suite
        # (production leaves mic_prober=None -> self._probe_mic, which imports pyaudio LAZILY).
        self._mic_ok: bool = True            # default True: never-probed != broken (PRD §4.4 spirit)
        self._mic_error: str | None = None
        self._mic_prober = mic_prober
        self._refresh_mic_status()

    def run(self) -> None:
        """The listen-forever loop (main thread, BLOCKS until shutdown)."""
        self._start_monotonic = time.monotonic()
        self._configure_log_level()           # PRD §4.2: DEBUG via config (namespace logger; T3 adds handler)
        self._log_resolved_device()           # PRD §4.2/acceptance T6: prove CUDA residency at startup
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

    def _configure_log_level(self) -> None:
        """Apply cfg.log.level to the `voice_typing` namespace logger (PRD §4.2 'DEBUG via config').

        Namespace-scoped only — NOT basicConfig (handler/root config is P1.M4.T3.S1's job). An invalid
        level string is ignored (leave the default). Tests use pytest caplog (own handler).
        """
        log_cfg = getattr(self._cfg, "log", None)
        level_name = log_cfg.level.upper() if log_cfg is not None else "INFO"
        try:
            logging.getLogger("voice_typing").setLevel(level_name)
        except (ValueError, TypeError):
            logger.warning("invalid log level %r; leaving default", getattr(log_cfg, "level", None))

    def _log_resolved_device(self) -> None:
        """Log the resolved device/models once at startup (CUDA residency proof; PRD acceptance T6).

        Reads self._resolved_device() — the SAME cached resolution status_snapshot() reports — so
        the startup log and voicectl status always agree. After a construction-failure CPU fallback
        (bugfix Issue 3 / P1.M1.T3.S2), main() seeds _resolved_device_cache with
        cuda_check.CPU_FALLBACK, so this logs the ACTUAL cpu recorder (not the driver probe, which
        still sees the GPU). _resolved_device() never raises (it degrades to 'unknown' on probe
        failure); the try/except is retained as a defensive guard.
        """
        try:
            resolved = self._resolved_device()
            logger.info(
                "voice-typing device resolved: device=%s compute_type=%s final_model=%s "
                "realtime_model=%s",
                resolved["device"],
                resolved["compute_type"],
                resolved["final_model"],
                resolved["realtime_model"],
            )
        except Exception:
            logger.info("voice-typing device resolved: (resolution failed; see cuda_check logs)")

    def on_final(self, text: str) -> None:
        """Gate → clean → type → record + log latency. Fired by RealtimeSTT in a NEW thread."""
        t_final_ready = time.monotonic()       # entry stamp (PRD §4.2 latency logging)
        if not self._listening.is_set():       # GATE: race guard (PRD §4.2/§8 — utterance may
            return                             #   complete right after stop)
        # Serialize clean→type→record→log across concurrent on_final worker threads (bugfix Issue 5 /
        # P1.M2.T2.S1). The gate above stays OUTSIDE the lock (read-only race guard); the lock is
        # SEPARATE from _lock (see __init__) so this never stalls toggle/start/stop and never deadlocks.
        with self._on_final_lock:
            cleaned = textproc.clean(text, self._cfg.filter)
            if not cleaned:                    # rejected: blocklist hallucination / below min_chars
                return
            payload = cleaned + (" " if self._cfg.output.append_space else "")
            try:
                self._backend.type_text(payload)   # may raise → caught so the on_final thread survives
            except Exception:
                logger.exception("typing backend failed for final %r", cleaned)
            t_typed = time.monotonic()             # right after type_text (PRD §4.2 latency logging)
            self._feedback.record_final(cleaned)   # recognition is final regardless of typing success
            record = self._latency.finalize_utterance(
                text=cleaned, t_final_ready=t_final_ready, t_typed=t_typed
            )
            # Structured per-utterance latency line — T1 (test_feed_audio) parses this. Stable prefix +
            # key=value tokens; text=<repr> is LAST (repr may contain spaces). *_ms are 'n/a' when no
            # on_vad_stop preceded this final (t_speech_end is None). (PRD §6 latency targets.)
            logger.info(
                "%s event=%s speech_end_to_final_ms=%s final_to_typed_ms=%s total_ms=%s "
                "partials=%d ts_epoch=%.3f text=%r",
                _LATENCY_LOG_PREFIX,
                record["event"],
                record["speech_end_to_final_ms"] if record["speech_end_to_final_ms"] is not None else "n/a",
                record["final_to_typed_ms"],
                record["total_ms"] if record["total_ms"] is not None else "n/a",
                record["partials"],
                record["ts"],
                cleaned,
            )
            logger.debug(
                "voice-typing latency debug: t_speech_end=%s t_final_ready=%.4f t_typed=%.4f",
                record["t_speech_end"] if record["t_speech_end"] is not None else "n/a",
                record["t_final_ready"],
                record["t_typed"],
            )

    def _arm(self) -> None:
        """Private: arm mic + set listening + notify. Called under the lock by start/toggle."""
        self._listening.set()
        self._recorder.set_microphone(True)
        self._feedback.set_listening(True)
        self._refresh_mic_status()  # bugfix Issue 2 / P1.M1.T2.S1: re-probe mic health on each arm

    def _disarm(self) -> None:
        """Private: disarm mic + abort blocked text() + clear listening + notify. Called under lock."""
        self._listening.clear()
        self._recorder.set_microphone(False)
        self._recorder.abort()      # breaks any blocked text() so the loop re-checks the cleared gate
        self._feedback.set_listening(False)

    def _refresh_mic_status(self) -> None:
        """Run the mic probe (real or injected) and store ok/error. NEVER raises.

        Sanctioned caller of the probe (bugfix Issue 2 / P1.M1.T2.S1): both __init__ and _arm()
        route through here so the try/except + attribute update live in ONE place. A probe failure
        (pyaudio missing, no devices, any exception) degrades to _mic_ok=False + _mic_error=str(exc)
        — the daemon stays runnable (degraded mode is acceptable; PRD §4.4 spirit). Tests inject
        mic_prober to stay hermetic; production leaves it None -> self._probe_mic.
        """
        prober = self._probe_mic if self._mic_prober is None else self._mic_prober
        try:
            ok, error = prober()
        except Exception as exc:  # defensive: a probe must never break startup or arm
            ok, error = False, str(exc)
        self._mic_ok = bool(ok)
        self._mic_error = error

    def _probe_mic(self) -> tuple[bool, str | None]:
        """Lazy PyAudio probe: is at least one input device available? Returns (ok, error|None).

        Mirrors RealtimeSTT's own AudioInputWorker device discovery (core/audio_input_worker.py:
        enumerate devices, keep those with maxInputChannels > 0). pyaudio is imported INSIDE this
        method (NOT at module top) so `import voice_typing.daemon` / `voice_typing.ctl` stay pure
        (bugfix Issue 4 invariant). Opens a SEPARATE, short-lived PyAudio instance only to ENUMERATE
        (no stream opened) — does not disturb the recorder's own capture stream. May RAISE on
        pyaudio-not-installed / no audio subsystem; _refresh_mic_status converts that to (False, str).
        """
        import pyaudio  # lazy: preserve ctl import purity (bugfix Issue 4)

        pa = pyaudio.PyAudio()
        try:
            inputs = [
                i for i in range(pa.get_device_count())
                if (pa.get_device_info_by_index(i).get("maxInputChannels") or 0) > 0
            ]
        finally:
            pa.terminate()
        if not inputs:
            return False, "no PyAudio input devices available"
        return True, None

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

    # --- control-socket status surface (P1.M4.T2.S1; additive — no existing-method edit) ---

    def status_snapshot(self) -> dict:
        """The status payload for the control socket `status`/`toggle`/`start`/`stop` cmds.

        Returns {listening, partial, last_final, uptime_s, device, compute_type, final_model,
        realtime_model, mic_ok, mic_error}. mic_ok/mic_error come from S1's PyAudio probe
        (self._mic_ok/self._mic_error), refreshed in __init__/_arm — lets voicectl status + JSON
        consumers see a dead mic without journalctl. partial/last_final come from the LIVE in-memory Feedback state (NOT the
        throttled state.json, which lags >=10 Hz); device/models come from _resolve_device_config
        (the SAME resolution build_recorder used -> status matches the actually-loaded models),
        cached on first call. Safe to call from the socket thread; never raises (device probe
        failures degrade to 'unknown').
        """
        snap = self._feedback.snapshot()
        dev = self._resolved_device()
        return {
            "listening": self.is_listening(),
            "partial": snap.get("partial", ""),
            "last_final": snap.get("last_final", ""),
            "uptime_s": round(self.uptime_s, 3),
            "device": dev.get("device", "unknown"),
            "compute_type": dev.get("compute_type", "unknown"),
            "final_model": dev.get("final_model", "unknown"),
            "realtime_model": dev.get("realtime_model", "unknown"),
            "mic_ok": self._mic_ok,            # bugfix Issue 2 / P1.M1.T2.S2: surface mic health (S1 detects)
            "mic_error": self._mic_error or "",  # None -> "" so JSON always carries a string
        }

    def _resolved_device(self) -> dict[str, str]:
        """Resolved {device,compute_type,final_model,realtime_model}, cached on first call.

        Lazily cached via getattr (no __init__ edit) so S1/S3's __init__ is untouched. The
        cuda_check probe (inside _resolve_device_config) imports ctranslate2 + calls
        get_cuda_device_count() — run AT MOST ONCE. Any failure degrades to 'unknown' (a status
        call must never crash the daemon). In tests, monkeypatch daemon._resolve_device_config.
        """
        resolved = getattr(self, "_resolved_device_cache", None)
        if resolved is None:
            try:
                resolved = _resolve_device_config(self._cfg)
            except Exception as exc:
                logger.warning("status: device resolution failed (%s); reporting 'unknown'", exc)
                resolved = {
                    "device": "unknown",
                    "compute_type": "unknown",
                    "final_model": "unknown",
                    "realtime_model": "unknown",
                }
            self._resolved_device_cache = resolved
        return resolved

    def shutdown(self) -> None:
        """Full recorder teardown (PRD §4.2; P1.M4.T2.S2). Idempotent + defensive.

        Calls self._recorder.shutdown(), which terminates the spawn-started transcript_process +
        reader_process (releases GPU VRAM + the mic device — the "no orphaned model worker
        processes" guarantee). IDEMPOTENT: a getattr-guarded flag (no __init__ edit) plus
        RealtimeSTT's own is_shut_down guard make a double call (quit on_quit + main() finally) a
        no-op the second time. DEFENSIVE: a recorder.shutdown() failure is logged, NOT re-raised —
        the daemon is exiting and teardown is best-effort (a broken teardown must not mask the
        original shutdown reason).

        NEVER call this on toggle/stop (models must stay resident — those use set_microphone+
        abort). The sanctioned callers are the quit on_quit hook (after request_shutdown() broke
        text()) and main()'s finally block (after run() returns; covers the signal path). Must NOT
        run while the main thread is inside recorder.text() — request_shutdown()/abort() guarantees
        it has exited text() before this is reached.
        """
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return
            self._shutdown_done = True
        try:
            self._recorder.shutdown()
            logger.info("recorder shutdown complete (GPU workers released)")
        except Exception:
            logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")


# --- ControlServer (P1.M4.T2.S1; PRD §4.2(3), §4.8) -----------------------------------------
# The voicectl<->daemon wire surface: an AF_UNIX SOCK_STREAM socket speaking one-JSON-object-
# per-line, dispatched to the running VoiceTypingDaemon. Constructed + started by main()
# (P1.M4.T3.S1) AFTER the daemon is built; stop()'d after run() returns. Pure stdlib (json/os/
# select/socket/threading) — keeps import purity. The accept loop uses select() polling + a stop
# Event (NOT close-to-unblock — unreliable on Linux, close(7) NOTES — and NOT settimeout, which
# breaks makefile()). See plan/.../P1M4T2S1/research/control_socket_design.md §3/§6 for the
# empirical proof.


class ControlServer:
    """AF_UNIX SOCK_STREAM control socket speaking one-JSON-object-per-line (PRD §4.2(3), §4.8).

    A background daemon thread accepts connections (one daemon worker per connection); each worker
    reads newline-delimited JSON requests, dispatches cmd to the daemon, and writes one JSON line
    per request. Robust to malformed JSON, stale socket files, and clean shutdown.

    Lifecycle: construct with the daemon (and optional socket_path + on_quit hook); start() binds
    + listens + launches the accept thread; stop() sets a stop Event (the accept loop uses
    select() polling, NOT close-to-unblock, which is unreliable on Linux) and joins the thread.
    The daemon does NOT own a ControlServer — the entry point (P1.M4.T3.S1 main()) constructs +
    starts one and calls stop() after run() returns.

    Protocol (PRD §4.2(3); research §2 — uniform status payload):
      {"cmd":"toggle"|"start"|"stop"|"status"} -> {"ok":true, **daemon.status_snapshot()}
      {"cmd":"quit"}                           -> {"ok":true,"shutting_down":true}  (+ request_shutdown)
      malformed JSON                           -> {"ok":false,"error":"malformed JSON: ..."}
      non-dict JSON                            -> {"ok":false,"error":"request must be a JSON object"}
      unknown/missing cmd                      -> {"ok":false,"error":"unknown command: ..."}
    """

    def __init__(
        self,
        daemon: "VoiceTypingDaemon",
        *,
        socket_path: str | None = None,
        on_quit: "Callable[[], None] | None" = None,
        accept_timeout: float = 0.3,
    ) -> None:
        self._daemon = daemon
        self._socket_path = (
            socket_path if socket_path is not None else _default_control_socket_path()
        )
        self._on_quit = on_quit
        self._accept_timeout = accept_timeout
        self._sock: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Bind + listen + launch the accept thread. Idempotent (no-op if already running).

        Creates the parent dir 0700; unlinks a stale .sock (EADDRINUSE prevention, PRD §4.2(3));
        binds; chmod 0600; listen(8). Raises RuntimeError if bind still fails (a live daemon
        holds the path — a real misconfiguration the operator must see).
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return  # already running
            directory = os.path.dirname(self._socket_path) or "."
            os.makedirs(directory, exist_ok=True, mode=0o700)
            # stale socket: unlink before bind (SO_REUSEADDR is meaningless for AF_UNIX path sockets)
            try:
                os.unlink(self._socket_path)
            except FileNotFoundError:
                pass
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(self._socket_path)
            except OSError as exc:
                sock.close()
                raise RuntimeError(
                    f"cannot bind control socket {self._socket_path!r}: {exc}"
                ) from exc
            os.chmod(self._socket_path, 0o600)   # owner-only (belt-and-suspenders on the 0700 dir)
            sock.listen(8)
            self._sock = sock
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._accept_loop,
                name="voice-typing-control",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Signal the accept loop to exit + close the listening socket + join the thread.

        Uses the stop Event (the accept loop polls via select(), so it notices within
        accept_timeout) and ALSO closes the socket (belt-and-suspenders: any blocked select/
        accept raises immediately). Joins up to 2 s. Unlinks the socket file (next start() also
        unlinks, but a clean quit leaves no stale .sock).
        """
        with self._lock:
            self._stop.set()
            sock = self._sock
            self._sock = None
            thread = self._thread
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=2.0)
        try:
            os.unlink(self._socket_path)
        except (FileNotFoundError, OSError):
            pass

    def _accept_loop(self) -> None:
        """Accept connections until stop(). Uses select() polling (NOT close-to-unblock)."""
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([sock], [], [], self._accept_timeout)
            except (OSError, ValueError):
                break  # listening socket closed (stop()) -> select raises
            if not ready:
                continue  # poll timeout -> re-check the stop Event
            try:
                conn, _addr = sock.accept()
            except OSError:
                break  # socket closed between select and accept
            # one daemon worker per connection (voicectl is one-shot; a persistent client also works)
            threading.Thread(
                target=self._handle, args=(conn,), daemon=True
            ).start()

    def _handle(self, conn: Any) -> None:
        """Per-connection readline loop: parse JSON, dispatch, write one JSON line per request."""
        rfile = wfile = None
        try:
            rfile = conn.makefile("r", encoding="utf-8", newline="\n")
            wfile = conn.makefile("w", encoding="utf-8", newline="\n")
            try:
                for line in rfile:                 # one JSON object per line (PRD §4.2(3))
                    line = line.strip()
                    if not line:
                        continue                   # empty line -> skip (no response)
                    response = self._dispatch(line)
                    wfile.write(json.dumps(response) + "\n")
                    wfile.flush()                  # CRITICAL: makefile("w") buffers; flush every reply
                    if response.get("shutting_down"):
                        break                      # quit -> reply sent, then close this connection
            finally:
                for f in (rfile, wfile):
                    if f is not None:
                        try:
                            f.close()
                        except OSError:
                            pass
        except OSError:
            pass  # client gone mid-line; worker exits cleanly
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch(self, line: str) -> dict:
        """Parse one request line -> dispatch cmd -> response dict. Never raises (robustness)."""
        try:
            msg = json.loads(line)
        except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
            return {"ok": False, "error": f"malformed JSON: {exc}"}
        if not isinstance(msg, dict):
            return {"ok": False, "error": "request must be a JSON object"}
        cmd = msg.get("cmd")
        if cmd == "toggle":
            self._daemon.toggle()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "start":
            self._daemon.start()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "stop":
            self._daemon.stop()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "status":
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "quit":
            self._daemon.request_shutdown()
            if self._on_quit is not None:
                try:
                    self._on_quit()
                except Exception:
                    logger.exception("on_quit callback failed")
            return {"ok": True, "shutting_down": True}
        return {"ok": False, "error": f"unknown command: {cmd!r}"}


def install_shutdown_signal_handlers(
    daemon: "VoiceTypingDaemon",
    *,
    signals: "tuple[int, ...] | None" = None,
) -> "Callable[[], None]":
    """Install SIGTERM/SIGINT handlers that request clean daemon shutdown (PRD §4.2/§4.9; P1.M4.T2.S2).

    systemd stop/restart sends SIGTERM (Python's default = immediate process death, NO Python
    cleanup -> the spawn-started model workers orphan + VRAM leaks). Ctrl-C sends SIGINT. Both
    route to the SAME clean path. The handler runs in the MAIN thread (CPython signal semantics)
    and therefore MUST NOT call recorder.abort() or recorder.shutdown() directly: abort() blocks
    on was_interrupted.wait(), set only by text() in the main thread -> deadlock (CPython #121649);
    shutdown() joins the very worker threads the main thread is still inside. Instead the handler
    spawns a daemon THREAD that calls daemon.request_shutdown() (abort OFF the main thread = safe);
    the handler returns at once. The spawned thread breaks text(); run() exits; main()'s finally
    calls daemon.shutdown() + ControlServer.stop() (T3.S1 wires; T2.S2 provides this fn).

    Must be called from the MAIN thread (signal.signal() requires it; raises ValueError otherwise).
    Returns a restore() callable that reinstalls the previous handlers (tests + clean uninstall).
    Idempotent-vs-reentry: a signal received while _shutdown is already set is ignored (no thread
    spam).
    """
    sigs = signals if signals is not None else (signal.SIGTERM, signal.SIGINT)
    previous: dict[int, Any] = {}

    def _handler(signum: int, frame: Any) -> None:
        # Runs in the MAIN thread. Do NOT call abort()/shutdown() here (deadlock, research §3).
        if daemon._shutdown.is_set():
            return  # already tearing down — ignore further signals
        logger.info("received signal %s; requesting clean shutdown", signum)
        threading.Thread(
            target=daemon.request_shutdown,
            name="voice-typing-signal-shutdown",
            daemon=True,
        ).start()

    for s in sigs:
        previous[s] = signal.signal(s, _handler)

    def restore() -> None:
        for s, prev in previous.items():
            signal.signal(s, prev)

    return restore


def _resolve_log_level(level_name: object) -> int:
    """Resolve a config log-level name to a logging int (INFO default; PRD §4.2 'DEBUG via config').

    `logging.getLevelName(name)` returns an int for a valid level name ("INFO"->20, "DEBUG"->10)
    but returns the STRING 'Level <name>' for an unknown one (it does NOT raise) -> the isinstance
    guard turns any typo/garbage into INFO. Mirrors VoiceTypingDaemon._configure_log_level's
    defensive posture (an invalid level is ignored, not crashed on). A non-str input (None, int)
    -> INFO.
    """
    if not isinstance(level_name, str):
        return logging.INFO
    level = logging.getLevelName(level_name.strip().upper())
    return level if isinstance(level, int) else logging.INFO


def _extract_mic_retry_error(message: str) -> str:
    """Pull <e> out of 'Microphone connection failed: <e>. Retrying...'.

    Returns <e> (or the whole message as a fallback). Keeps the periodic mic-retry summary
    actionable (bugfix Issue 2 / P1.M1.T2.S3): it names the most recent failure instead of
    just counting attempts. Strips the known prefix + suffix; falls back to the full message
    if the shape differs.
    """
    prefix = "Microphone connection failed: "
    suffix = ". Retrying..."
    text = message
    if text.startswith(prefix):
        text = text[len(prefix):]
    if text.endswith(suffix):
        text = text[: -len(suffix)]
    return text


def _summarize_mic_retry(record: logging.LogRecord, count: int, message: str) -> None:
    """Rewrite a mic-retry LogRecord IN PLACE into a single WARNING summary (no traceback).

    Bugfix Issue 2 / P1.M1.T2.S3. CPython Formatter.format appends record.exc_text (a CACHE of
    the traceback) if truthy, so BOTH exc_info and exc_text must be cleared to fully strip the
    traceback. getMessage() is not cached, so rewriting record.msg + record.args changes the
    formatted text. Runs inside a logging.Filter (documented: 'the record may be modified
    in-place'), before callHandlers -> handler.emit -> Formatter.format.
    """
    record.levelno = logging.WARNING
    record.levelname = "WARNING"
    record.exc_info = None
    record.exc_text = None
    record.msg = (
        f"Microphone still unavailable after {count} retry attempts "
        f"(last error: {_extract_mic_retry_error(message)})"
    )
    record.args = ()


class MicRetryRateLimitFilter(logging.Filter):
    """Rate-limit RealtimeSTT's per-retry 'Microphone connection failed' ERROR+traceback spam.

    Bugfix Issue 2 / P1.M1.T2.S3. RealtimeSTT's AudioInputWorker retries the mic in an
    infinite ~3-second loop (core/audio_input_worker.py:162), logging a full traceback
    (exc_info=True) on EVERY attempt -> thousands of identical errors in journald (2822+
    observed on the live daemon). Attached to the 'realtimestt' logger via
    _install_mic_retry_rate_limiter (called from _setup_logging) so a SINGLE filter gates
    records in Logger.handle BEFORE callHandlers -> it suppresses BOTH the library's own
    console handler AND propagation to the root stderr/journald handler (CPython:
    Filterer.filter runs before callHandlers; RealtimeSTT leaves propagate=True).

    Behavior:
      - first occurrence (count==1): pass through unchanged (the full ERROR+traceback logs ONCE);
      - subsequent within `dedup_seconds` of the last emitted record, not on a summary tick:
        SUPPRESSED (return False);
      - on every `summary_every`-th occurrence OR once `dedup_seconds` elapsed since the last
        emitted record: rewrite the record in place to a WARNING summary WITHOUT a traceback
        ('Microphone still unavailable after N retry attempts (last error: <e>)'), pass through.

    This throttles the LOG line only — it does NOT stop the actual ~3s mic retry (that loop
    lives in the spawned worker thread). Match key: record.getMessage() contains
    'Microphone connection failed' (robust for f-string and %-style call sites). Non-matching
    records pass through untouched and do NOT increment the counter.
    """

    def __init__(self, dedup_seconds: float = 60.0, summary_every: int = 20) -> None:
        super().__init__()
        self.dedup_seconds = float(dedup_seconds)
        self.summary_every = max(1, int(summary_every))
        self._count = 0
        self._last_seen = 0.0  # time.monotonic() of the last EMITTED record; 0.0 == never

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "Microphone connection failed" not in message:
            return True  # unrelated record — never touch it (counter stays clean)
        self._count += 1
        now = time.monotonic()
        if self._count == 1:
            self._last_seen = now  # first ever: let the full ERROR + traceback through once
            return True
        if (
            now - self._last_seen >= self.dedup_seconds
            or self._count % self.summary_every == 0
        ):
            _summarize_mic_retry(record, self._count, message)
            self._last_seen = now
            return True
        return False  # within the window and not a summary tick — drop the per-attempt spam


def _install_mic_retry_rate_limiter(logger_name: str = "realtimestt") -> None:
    """Attach the mic-retry rate-limit filter to the named logger, IDEMPOTENTLY.

    Bugfix Issue 2 / P1.M1.T2.S3. Removes any already-attached MicRetryRateLimitFilter first,
    so repeated _setup_logging calls (main() may invoke it on the config-load-fail fallback
    path AND the normal path) never double-register. CPython addFilter/removeFilter are NOT
    lock-protected and use __eq__ (distinct instances both register), so this reset-then-add
    is the safe pattern; it is called once per _setup_logging from the MAIN thread (never
    concurrently). A fresh instance also resets the dedup counter, so re-calling _setup_logging
    cannot leave stale state from a prior run.
    """
    target = logging.getLogger(logger_name)
    for existing in [f for f in target.filters if isinstance(f, MicRetryRateLimitFilter)]:
        target.removeFilter(existing)
    target.addFilter(MicRetryRateLimitFilter())


def _setup_logging(level_name: object) -> None:
    """Configure stderr logging at the resolved level (PRD §4.2; P1.M4.T3.S1).

    Closes the gap VoiceTypingDaemon._configure_log_level deliberately left open: that fn sets
    ONLY the 'voice_typing' namespace logger LEVEL (no handler) -> without this, records pass the
    logger gate but have nowhere to emit (silent daemon). logging.basicConfig is IDEMPOTENT: a
    no-op if the root logger already has a handler (e.g. under pytest caplog -> tests keep using
    caplog, the desired non-intrusive behavior); in a fresh process (systemd, console script,
    `python -m`) it installs a single StreamHandler on stderr (journald captures unit stderr) at
    the resolved level. The SAME cfg.log.level is read by run()'s _configure_log_level -> root
    handler + namespace logger agree, so 'DEBUG' actually shows debug records (not just passes the
    namespace gate).

    Also attaches (idempotently) a MicRetryRateLimitFilter to the 'realtimestt' logger so the
    library's per-~3s 'Microphone connection failed' ERROR+traceback spam logs once then degrades
    to periodic WARNING summaries (bugfix Issue 2 / P1.M1.T2.S3).
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=_resolve_log_level(level_name),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # bugfix Issue 2 / P1.M1.T2.S3: rate-limit RealtimeSTT's per-retry mic traceback spam.
    _install_mic_retry_rate_limiter("realtimestt")


def main() -> int:
    """Daemon process entry point: logging + config + daemon/server + signals + run + teardown.

    (PRD §4.2/§4.9; P1.M4.T3.S1.) Wires together the components built by every prior subtask into
    the single sanctioned lifecycle. Guarded by `if __name__ == "__main__": sys.exit(main())`
    (RealtimeSTT uses spawn-started multiprocessing workers that re-import __main__ -> ALL heavy
    work must live in main(), never at module top; the guard + this invariant keep spawn children
    clean).

    Lifecycle (the teardown order is the P1.M4.T2.S2 contract):
      cfg = VoiceTypingConfig.load(); _setup_logging(cfg.log.level)
      Feedback(cfg.feedback) -> VoiceTypingDaemon(cfg, fb) -> ControlServer(d, on_quit=d.shutdown)
      srv.start(); restore = install_shutdown_signal_handlers(d);   (both main-thread)
      try: d.run()                                            # BLOCKS until quit/signal
      finally: restore(); d.shutdown(); srv.stop()            # idempotent; srv.stop main-thread only
      return 0
    Returns 0 on clean shutdown, 1 on a fatal error (config/recorder/server init) so systemd
    Restart=on-failure restarts the unit. NEVER raises (all fatal paths caught + logged).
    """
    # 1. Config first (needed for the logging level). A load failure is fatal + unrecoverable;
    #    set up a fallback stderr INFO handler so the traceback is visible (logging may not yet
    #    be configured).
    try:
        cfg = VoiceTypingConfig.load()
    except Exception:
        _setup_logging("INFO")
        logger.exception("failed to load config; exiting")
        return 1
    # 2. Logging to stderr (journald) at cfg.log.level (PRD §4.2). Closes the gap above.
    _setup_logging(cfg.log.level)
    logger.info("voice-typing daemon starting (pid=%s)", os.getpid())

    daemon = None        # type: VoiceTypingDaemon | None
    server = None        # type: ControlServer | None
    restore = None       # type: Callable[[], None] | None
    try:
        # Lazy import: keeps the module-top change to just `import sys`, and stays monkeypatchable
        # (tests patch voice_typing.feedback.Feedback; `from X import Y` resolves the live attr).
        from voice_typing.feedback import Feedback

        feedback = Feedback(cfg.feedback)
        # One LatencyLog shared by the recorder callbacks (on_vad_stop/partial, wired in build_recorder)
        # and the daemon's on_final.finalize_utterance. Created here (not left to __init__) so the
        # construction-failure CPU retry below can build a forced-CPU recorder wired to this SAME
        # collector before re-constructing the daemon. (bugfix Issue 3 / P1.M1.T3.S2.)
        latency = LatencyLog()

        # bugfix Issue 3 / P1.M1.T3.S2 (PRD §4.4): the cuda_check driver probe can say "cuda-ok" while
        # cuDNN/cuBLAS then fails to load INSIDE AudioToTextRecorder.__init__ (e.g. a missing
        # libcudnn_ops.so.9). Without a retry that is `return 1` -> systemd Restart=on-failure crash-loop.
        # So: if construction fails AND the originally-resolved device was cuda, retry ONCE on the PRD
        # §4.4 CPU config via build_recorder(force_cpu=True) (which SKIPS the cuda_check probe entirely
        # — S1) and inject the recorder through the existing recorder= kwarg (no __init__ change). Any
        # failure here (probe raises, CPU build raises, re-construction raises) propagates to the outer
        # `except Exception` -> "fatal error" -> return 1, preserving total-failure semantics.
        try:
            daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)
        except Exception as exc:
            if _resolve_device_config(cfg).get("device") != "cuda":
                raise  # first attempt was already CPU (or the probe failed) — nothing to fall back to
            cpu_fb = cuda_check.CPU_FALLBACK
            logger.warning(
                "CUDA recorder construction failed (%s); falling back to CPU "
                "(device=%s, compute_type=%s, models=%s/%s) — degraded but functional",
                exc, cpu_fb["device"], cpu_fb["compute_type"],
                cpu_fb["final_model"], cpu_fb["realtime_model"],
            )
            cpu_recorder = build_recorder(cfg, feedback, latency, force_cpu=True)
            daemon = VoiceTypingDaemon(cfg, feedback, latency=latency, recorder=cpu_recorder)
            # Make the daemon's self-reported device reflect the ACTUAL cpu recorder, not the driver
            # probe (which still sees the GPU). _resolved_device() (read by status_snapshot) caches via
            # this attribute; seeding it here means voicectl status reports device=cpu after the
            # fallback (PRD §4.4 "say so in status"). _log_resolved_device (refactored in Task 2) also
            # reads this cache, so the startup log agrees.
            daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)
            logger.info("daemon started in degraded CPU mode (construction-failure fallback)")
        # quit path: ControlServer._dispatch("quit") -> request_shutdown() (blocks until text()
        #   returns) -> on_quit=daemon.shutdown() -> recorder.shutdown() (release VRAM).
        server = ControlServer(daemon, on_quit=daemon.shutdown)
        # SIGTERM/SIGINT -> a spawned daemon thread calls daemon.request_shutdown() (NOT abort()
        #   from the handler — that deadlocks; T2.S2). Returns restore() reinstating prior handlers.
        restore = install_shutdown_signal_handlers(daemon)
        server.start()
        daemon.run()  # BLOCKS until quit/signal; starts NOT-LISTENING (PRD §4.9; no hot-mic).
    except Exception:
        logger.exception("fatal error during daemon lifecycle; exiting")
        return 1
    finally:
        # Teardown order (P1.M4.T2.S2 contract): stop diverting signals -> release GPU workers ->
        # close the control socket. Each step is NULL-SAFE + best-effort (a failure here must not
        # mask the original reason). server.stop() runs ONLY here (main thread): it joins the
        # accept thread, and on_quit runs on a worker OF that thread -> calling server.stop() from
        # on_quit would self-join.
        if restore is not None:
            try:
                restore()
            except Exception:
                logger.exception("signal handler restore failed (ignored)")
        if daemon is not None:
            try:
                daemon.shutdown()  # idempotent: no-op if on_quit (quit path) already shut recorder.
            except Exception:
                logger.exception("daemon.shutdown() failed during teardown (ignored)")
        if server is not None:
            try:
                server.stop()  # close socket + unlink + join accept thread (main thread only).
            except Exception:
                logger.exception("ControlServer.stop() failed during teardown (ignored)")
    return 0


if __name__ == "__main__":
    # The guard RealtimeSTT's spawn-based multiprocessing requires (re-import of __main__ in
    # children skips this body). sys.exit propagates main()'s exit code to systemd (Restart=on-
    # failure).
    sys.exit(main())
