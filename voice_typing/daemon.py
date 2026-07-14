"""voice_typing.daemon — recorder construction + callback wiring + listen-forever daemon
(PRD §4.2, §4.4).

SCOPE (P1.M4.T1.S1 + P1.M4.T1.S2):
  - S1: cfg_to_kwargs() + build_recorder() factory + RealtimeSTT→Feedback callback wiring +
    cuda_check-gated CPU fallback. The recorder is constructed ONCE so models stay resident.
  - S2: VoiceTypingDaemon — the listen-forever run() loop (the WhisperX-flaw fix: recorder.text()
    returning is normal SEGMENTATION, never session end), on_final→gate→clean→type→record, the
    listening gate (threading.Event cleared at boot → no hot-mic, PRD §4.9), and start/stop/toggle
    that arm/disarm the mic via set_microphone+abort (models stay resident → instant toggle-on).
  - DONE: control socket, bounded recorder teardown (hard timeout + force-cleanup of worker
    processes) — see _bounded_shutdown(). LATER: precise per-utterance latency timestamps
    (P1.M4.T1.S3). These are NOT in this module yet.

LAZY LOAD (PRD §4.2bis): AudioToTextRecorder.__init__ loads BOTH whisper models (final + realtime) into
resident memory (GPU VRAM on cuda, RAM on cpu) — seconds of work + ~1.5-3 GB VRAM. To avoid taxing the GPU on
boots where voice typing is never used, the recorder is NOT built at daemon boot — it is built lazily on the
FIRST arm (start/toggle) via VoiceTypingDaemon._load_recorder() (single-flight). A session that never arms
stays at ~0 VRAM; after the first arm the recorder stays resident so re-arms are instant. _load_recorder() also
owns the construction-failure CPU fallback (migrated from main(), bugfix Issue 3).

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
  - the daemon main loop (P1.M4.T1.S2 + P1.M2.T1.S1): VoiceTypingDaemon builds the recorder LAZILY on first arm via _load_recorder() (§4.2bis), not in __init__.
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
from voice_typing.recorder_host import RecorderHost  # P1.M3.T2.S2: child-subprocess recorder owner

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

# Mic-health probe TTL (bugfix Issue 3 / P1.M2.T2.S1): re-probe at most once every 30s so _arm()
# does NOT pay the ~40ms PyAudio init on every keystroke. _refresh_mic_status() skips the probe
# when the last probe is within this window; __init__ (force=True) and explicit force=True bypass it.
_MIC_PROBE_TTL_S: float = 30.0


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
    feedback: "Feedback", latency: "LatencyLog | None" = None,
    on_speech: "Callable[[], None] | None" = None,
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
        if on_speech is not None:
            on_speech()  # idle auto-stop: recognized words reset the clock

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
    on_speech: "Callable[[], None] | None" = None,
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
    kwargs.update(_build_callbacks(feedback, latency, on_speech=on_speech))
    filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
    return recorder_cls(**filtered)


def build_recorder(
    cfg: VoiceTypingConfig,
    feedback: "Feedback",
    latency: "LatencyLog | None" = None,
    force_cpu: bool = False,
    on_speech: "Callable[[], None] | None" = None,
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

    return _construct(cfg, feedback, AudioToTextRecorder, latency, force_cpu=force_cpu,
                      on_speech=on_speech)


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

# P1.M1.T2.S1 / bugfix Issue 1: bounded wait shutdown() uses for an in-flight teardown claimed
# by request_shutdown() (the SIGTERM signal thread). 8.0s covers a ~7s teardown (5s join +
# 2s second join, post-T2.S2) with margin; a timeout falls back to shutdown()'s OWN teardown
# (safe — RecorderHost._stop_lock serializes host.stop, P1.M1.T1.S1). A named constant (not a
# literal) so the fallback unit test can monkeypatch it to ~0.2s and stay fast.
_TEARDOWN_WAIT_TIMEOUT = 8.0


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


class _LegacyRecorderHostAdapter:
    """Wraps a legacy stub recorder (recorder.text/set_microphone/abort/shutdown) as a host.

    P1.M3.T2.S2 (re-plan): the daemon now talks to a RecorderHost everywhere. The existing test
    suite injects legacy _StubRecorder/_FakeSlowRecorder/_ControllableShutdownRecorder instances
    via the `recorder=` seam; this adapter forwards the host surface to those stubs so the existing
    assertions (rec.mic / rec.aborts / rec.shutdowns / rec.text_calls) keep holding WITHOUT a mass
    rewrite of ~50 tests. Production never uses this (production spawns a real RecorderHost child).

    The callbacks (on_partial/on_speech) are wired by the daemon via _load_host on the REAL host;
    this adapter is only used when a recorder is INJECTED (already loaded), so the daemon's run loop
    drives text() directly and the stub's text(on_final) fires on_final in-process (no IPC).
    """

    def __init__(self, recorder: Any) -> None:
        self._recorder = recorder
        self._device: dict[str, str] = {}

    # host surface
    def spawn(self, timeout: float = 180.0) -> bool:
        return True  # injected -> already "spawned"

    @property
    def device(self) -> dict[str, str]:
        return dict(self._device)

    @property
    def is_alive(self) -> bool:
        return True

    @property
    def pid(self) -> int | None:
        return None

    def set_microphone(self, on: bool) -> None:
        self._recorder.set_microphone(on)

    def abort(self) -> None:
        self._recorder.abort()

    def text(self, on_final: Callable[[str], None]) -> None:
        self._recorder.text(on_final)

    def stop(self, timeout: float = 5.0) -> None:
        # The legacy stub's shutdown() may block (e.g. _FakeSlowRecorder). Mirror the OLD
        # _bounded_shutdown: run shutdown() in a daemon thread under a bounded wait; on timeout
        # force-terminate transcript_process/reader_process + mark is_shut_down + drop the realtime
        # model ref (the force-cleanup the test_bounded_shutdown_force_cleans_on_timeout test pins).
        rec = self._recorder
        done = threading.Event()

        def _do() -> None:
            try:
                rec.shutdown()
                logger.info("recorder shutdown complete (GPU workers released)")
            except Exception:
                logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
            finally:
                done.set()

        t = threading.Thread(target=_do, name="vt-recorder-shutdown", daemon=True)
        t.start()
        if done.wait(timeout=timeout):
            return  # completed within budget
        logger.warning(
            "recorder.shutdown() exceeded %.1fs budget; force-terminating worker processes "
            "(transcript_process, reader_process) to release VRAM",
            timeout,
        )
        for attr in ("transcript_process", "reader_process"):
            proc = getattr(rec, attr, None)
            try:
                if proc is not None and proc.is_alive():
                    proc.terminate()
            except Exception:
                logger.debug("force-terminate of %s failed (best-effort)", attr, exc_info=True)
        try:
            rec.is_shut_down = True
        except Exception:
            pass
        try:
            rec.realtime_transcription_model = None
        except Exception:
            pass


class VoiceTypingDaemon:
    """The listen-forever daemon core: recorder loop + on_final→type + listening gate + toggle.

    PRD §4.2 items 1+2. run() is the main-thread loop that fixes the WhisperX flaw: recorder.text()
    returning is normal SEGMENTATION, never session end (PRD §1 #1). on_final gates→cleans→types→records.
    start/stop/toggle arm/disarm the mic via set_microphone+abort; the FIRST arm lazily loads the models
    via _load_recorder() (§4.2bis) — subsequent arms are instant (resident). NEVER recorder.shutdown() on
    toggle/stop — only on quit (bounded teardown).
    """

    def __init__(
        self,
        cfg: VoiceTypingConfig,
        feedback: "Feedback",
        *,
        recorder: Any = None,
        recorder_host: "RecorderHost | Any | None" = None,
        host_factory: "Callable[..., Any] | None" = None,
        backend: "TypingBackend | None" = None,
        latency: "LatencyLog | None" = None,
        mic_prober: Callable[[], tuple[bool, str | None]] | None = None,
    ) -> None:
        self._cfg = cfg
        self._feedback = feedback
        # P1.M3.T2.S2 (re-plan): the recorder now lives in a CHILD subprocess owned by a
        # RecorderHost. self._host replaces self._recorder. The daemon process NEVER imports
        # RealtimeSTT/torch/ctranslate2 and NEVER creates a CUDA context (all of that lives in
        # the child); idle-unload = host.stop() = terminate the child PROCESS GROUP -> ALL VRAM
        # released -> daemon tree ABSENT on nvidia-smi (PRD §7.9 + §6 T6(d)). See
        # voice_typing/recorder_host.py.
        #
        # host_factory= (default RecorderHost) is what _load_host calls to BUILD a fresh host on
        # the first arm. Tests inject a fake factory (or a pre-built fake host via recorder_host=)
        # so the fast pytest stays CUDA-free. recorder_host= (a pre-built host) short-circuits
        # _load_host ("already loaded" — mirrors the legacy recorder= injection).
        #
        # recorder= (LEGACY test seam, kept for minimal churn in the existing suite): when given,
        # it is wrapped into a host-shaped adapter so the daemon talks to self._host uniformly.
        # The adapter forwards set_microphone/abort/text/stop to the legacy stub recorder, so the
        # existing assertions (rec.mic / rec.aborts / rec.shutdowns / rec.text_calls) still hold.
        self._host_factory = host_factory
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
        # P1.M1.T2.S1 / bugfix Issue 1: signaled when the in-flight _bounded_shutdown() finishes, so
        #   a concurrent shutdown() (main-thread finally, on the SIGTERM path) can WAIT for it
        #   instead of starting a second teardown (SIGTERM double-teardown fix). Set in
        #   request_shutdown()'s finally + shutdown()'s finally.
        self._teardown_done = threading.Event()
        # In-flight text() tracking (validation Issue 1 / abort() deadlock fix): SET while the
        # run() loop is blocked INSIDE recorder.text(), CLEAR otherwise. RealtimeSTT's abort()
        # blocks on was_interrupted.wait(), an event set ONLY inside text() (transcription_api.py
        # L37/L102). When the loop is disarmed/idle (in time.sleep(0.05)) nothing sets that event,
        # so an unconditional abort() blocks FOREVER (the voicectl stop/toggle/quit hang). _safe_abort()
        # gates abort() on this flag so it can NEVER block the control-socket response. Set/cleared
        # ONLY by run() on the single main thread; read by _safe_abort() on control/worker threads
        # (a stale True during the brief teardown window is harmless — abort() is then a valid nudge).
        self._text_in_flight = threading.Event()   # cleared → no thread in text() at boot
        self._start_monotonic: float | None = None
        # Idle auto-stop: timestamp of the last recognized speech; the _idle_watchdog thread disarms
        # when now - this exceeds cfg.asr.auto_stop_idle_seconds. None while NOT listening. Set on
        # _arm, cleared on _disarm, refreshed by the realtime partial callback (on_speech hook).
        # Float store is atomic in CPython (read by the watchdog, written by RealtimeSTT worker +
        # control-socket threads); the disarm re-checks the deadline under _lock (no false stop).
        self._last_speech_monotonic: float | None = None
        # Idle UNLOAD clock (P1.M3.T1.S1 / PRD §4.2bis): time.monotonic() of when the mic was last
        # DISARMED; the _idle_unload_watchdog tears the recorder down after cfg.asr.auto_unload_idle_seconds
        # in this state to reclaim VRAM. None while armed/listening (clock inactive). Set in _disarm,
        # cleared in _arm. Float store is atomic in CPython; _unload_recorder re-checks under _lock.
        self._disarmed_monotonic: float | None = None
        # Per-utterance latency collector (P1.M4.T1.S3): fed by on_vad_stop/partial (via
        # build_recorder→_build_callbacks) + on_final. Injectable for tests; a real one otherwise.
        self._latency = latency if latency is not None else LatencyLog()
        # Lazy load (PRD §4.2bis / delta D1,D2): the recorder (now in a child subprocess owned by a RecorderHost)
        # is NOT built at boot — it is spawned on the FIRST arm (start/toggle) via _load_host(), so a session that
        # never arms stays at ~0 VRAM. recorder_host= injected (unit tests / a pre-built host) → already loaded;
        # recorder= injected (LEGACY) → wrapped into a host adapter, already loaded; None → lazy (self._host is
        # None until the first successful _load_host()).
        if recorder_host is not None:
            self._host: Any = recorder_host
            loaded = True
        elif recorder is not None:
            self._host = _LegacyRecorderHostAdapter(recorder)
            loaded = True
        else:
            self._host = None
            loaded = False
        self._models_loaded = loaded
        self._loading = False
        self._load_error: str | None = None
        # Single-flight load wait (PRD §4.2bis "waits on the in-flight one"): a Condition over the SAME _lock so a
        # second arm while _loading blocks on the in-flight load, then sees its result. Condition(_lock) shares the
        # existing lock; existing `with self._lock:` code is unaffected.
        self._load_cond = threading.Condition(self._lock)
        # Boot lifecycle phase (delta D2/D3): 'idle' if a recorder was injected (loaded), else 'unloaded' (the lazy
        # boot state). _load_recorder() drives loading->idle; a failed load returns to 'unloaded'. (The feedback
        # models_loaded FIELD + status_snapshot/ctl exposure is P1.M2.T2.S1; T1 tracks the daemon-side
        # self._models_loaded + drives phase via the existing set_phase — no feedback.py edit.)
        self._feedback.set_phase("idle" if loaded else "unloaded")
        self._feedback.set_models_loaded(loaded)  # P1.M2.T2.S1: mirror phase at boot
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
        # TTL cache stamp for _refresh_mic_status (bugfix Issue 3 / P1.M2.T2.S1): time.monotonic()
        # of the last probe; 0.0 == never (sentinel matching MicRetryRateLimitFilter._last_seen).
        # Read/written ONLY under self._lock (via _arm) or here in single-threaded __init__.
        self._mic_probe_at: float = 0.0
        self._refresh_mic_status(force=True)   # construction always probes (sets the initial stamp)

    def _load_recorder(self) -> bool:
        """Back-compat alias for _load_host (P1.M3.T2.S2 re-plan renamed the method).

        The recorder now lives in a child subprocess owned by a RecorderHost; "loading" = spawning
        the child + waiting for its 'ready'/'error'. Kept under the old name so start()/toggle()'s
        call sites (and the existing tests' `recorder=` injection seam) are unchanged.
        """
        return self._load_host()

    def _load_host(self) -> bool:
        """Single-flight lazy SPAWN of the recorder-host child on first arm (PRD §4.2bis). True iff ready.

        Called by start()/toggle() BEFORE arming — NOT inside _arm() (which holds self._lock; this method
        acquire-release-reacquires that same lock, so nesting would deadlock). Idempotent once loaded: a
        resident host → immediate True. Single-flight via _load_cond (Condition over self._lock): a second
        caller while _loading WAITS for the in-flight spawn and returns ITS result (never starts a 2nd
        child). The heavy host.spawn() (the child's model load) runs OUTSIDE _lock so concurrent
        status/stop stay responsive during the ~1–3 s load (mirrors the abort()-out-of-_lock discipline).

        CPU fallback (P1.M1.T3.S2): the CHILD retries force_cpu=True on a cuda construction failure
        (see recorder_host._worker_main). On success: install self._host, _models_loaded=True, phase='idle',
        seed _resolved_device_cache from the child's 'ready' device dict (so status reports the child's
        ACTUAL device WITHOUT the daemon probing CUDA), log the resolved device, return True. On total
        failure: _load_error set, host.stop()'d (NO half-built host — §4.2bis), self._host stays None,
        phase='unloaded', return False.
        """
        with self._lock:
            if self._models_loaded:
                return True                       # resident → instant (second+ arm)
            if self._loading:
                while self._loading:               # wait for the in-flight spawn (spurious-wake safe)
                    self._load_cond.wait()
                return self._models_loaded         # its result (True=loaded, False=failed)
            self._loading = True                   # we are the loader
            self._load_error = None
            self._feedback.set_phase("loading")
            self._feedback.set_models_loaded(False)  # P1.M2.T2.S1: models not resident while loading
        # --- heavy spawn OUTSIDE _lock (status/stop stay responsive during the ~1–3 s child load) ---
        factory = self._host_factory or RecorderHost
        host = factory(
            self._cfg, self._feedback, self._latency,
            self.on_final, self._on_partial, self._touch_speech,
        )
        ok = host.spawn()
        # --- re-acquire _lock to publish the result + wake any waiters ---
        with self._lock:
            self._loading = False
            if ok:
                self._host = host
                self._models_loaded = True
                self._load_error = None
                # Seed the status device cache from the CHILD's 'ready' dict (the daemon must NOT probe
                # CUDA itself — the child owns the cuda_check resolution now). Replaces the old in-process
                # _resolved_device() probe at load time.
                self._resolved_device_cache = host.device
                self._feedback.set_phase("idle")
                self._feedback.set_models_loaded(True)  # P1.M2.T2.S1: models now resident
                self._load_cond.notify_all()
                success = True
            else:
                # NO half-built host (§4.2bis): stop the child (best-effort) + drop the handle.
                try:
                    host.stop()
                except Exception:
                    logger.exception("failed to stop a half-spawned host (best-effort; ignored)")
                self._load_error = "recorder host spawn failed"  # child reports the detail in its log
                self._models_loaded = False
                self._host = None
                self._feedback.set_phase("unloaded")
                self._feedback.set_models_loaded(False)  # P1.M2.T2.S1: models not resident
                self._load_cond.notify_all()
                success = False
        # Log OUTSIDE _lock (status/logging is ~ms; don't hold the lock for it).
        if success:
            self._log_resolved_device()   # log the ACTUAL loaded device (CRITICAL #8 — now from the child)
            logger.info("voice-typing models loaded (recorder-host child ready); resident")
        else:
            logger.error("voice-typing model load failed (%s); staying unloaded", self._load_error)
        return success

    def run(self) -> None:
        """The listen-forever loop (main thread, BLOCKS until shutdown)."""
        self._start_monotonic = time.monotonic()
        self._configure_log_level()           # PRD §4.2: DEBUG via config (namespace logger; T3 adds handler)
        if self._host is not None:        # lazy load (§4.2bis): no device to log at boot; _load_host logs it
            self._log_resolved_device()           # PRD §4.2/acceptance T6: prove CUDA residency (at LOAD time now)
        self._feedback.set_listening(False)   # PRD §4.9: starts NOT listening (no hot-mic on boot)
        # Stop queueing captured audio into the VAD pipeline while idle (validation Issue 2). The
        # child's recorder is constructed with use_microphone=True (PRD §4.4 / _FIXED_KWARGS), so at boot the
        # "listening" Event is cleared but that gate only suppresses recorder.text() OUTPUT.
        # set_microphone(False) (proxied to the child as a 'disarm' cmd) makes RealtimeSTT's audio worker
        # skip buffering/queueing captured frames while idle (the worker still does stream.read() but
        # discards the data until armed), so no audio reaches VAD/transcription until the first
        # start()/toggle().
        #
        # KNOWN LIMITATION (verified against RealtimeSTT 1.0.2): set_microphone(False) toggles a
        # shared `use_microphone` flag that gates QUEUEING — it does NOT cork or close the underlying
        # PyAudio capture stream (which lives in a separate worker process and stays uncorked). So
        # PipeWire still lists an active source-output while idle. Truly closing the physical stream
        # would require recorder.shutdown() + full reconstruction on every toggle, which reloads the
        # multi-GB Whisper models (seconds) and directly defeats the PRD §4.2 "construct once, models
        # resident, instant toggle-on" design. The PRD's "never hot-mics on boot" (§4.9) is honored
        # in its intended sense: NO TRANSCRIPTION/OUTPUT happens while idle (the gate + this flag
        # guarantee that). The residual physical-capture-while-idle is the accepted trade-off for
        # instant toggle. Mirrors the existing set_listening(False) line: device state matches the
        # listening gate from boot; the first start()/toggle() re-arms via _arm().
        if self._host is not None:
            self._host.set_microphone(False)
        logger.info(
            "voice-typing daemon ready (not listening); %s",
            "recorder resident" if self._host is not None else "models lazy (not yet loaded)",
        )
        # Idle auto-stop watchdog: disarms after cfg.asr.auto_stop_idle_seconds of no speech.
        threading.Thread(target=self._idle_watchdog, name="voice-typing-idle", daemon=True).start()
        # Idle UNLOAD watchdog (P1.M3.T1.S1 / PRD §4.2bis): reclaims VRAM after cfg.asr.auto_unload_idle_seconds
        # DISARMED. Mirrors the idle-watchdog start above; same _shutdown.wait(1.0) tick + daemon thread.
        threading.Thread(target=self._idle_unload_watchdog, name="voice-typing-idle-unload", daemon=True).start()
        while not self._shutdown.is_set():
            if self._host is None:
                time.sleep(0.05)   # no models loaded yet → idle, ~0 VRAM (PRD §4.2(1)/§4.2bis)
                continue
            if self._listening.is_set():
                # blocks until ONE utterance finalizes → on_final on the host's reader thread → returns → re-listen.
                # Returning is NORMAL SEGMENTATION, never session end (the WhisperX-flaw fix, PRD §1 #1).
                #
                # Track in-flight text() (validation Issue 1): abort() can only safely wake a thread
                # that is blocked HERE. The flag is SET just before entering text() and CLEARED the
                # instant it returns, so _safe_abort() (called by stop/toggle/quit) never invokes
                # abort() when the loop is idle in time.sleep(0.05) — which would block forever on
                # was_interrupted.wait() (set only inside text()). See _safe_abort().
                self._text_in_flight.set()
                try:
                    self._host.text(self.on_final)
                finally:
                    self._text_in_flight.clear()
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
        self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh
        self._disarmed_monotonic = None                  # armed -> idle-UNLOAD clock inactive (P1.M3.T1.S1)
        if self._host is not None:
            self._host.set_microphone(True)
        self._feedback.set_listening(True)
        self._refresh_mic_status()  # TTL-cached (Issue 3 / P1.M2.T2.S1): re-probes at most once / 30s

    def _disarm(self) -> None:
        """Private: disarm mic + clear listening + notify. Called under lock.

        NOTE: host.abort() is deliberately NOT called here (see start/stop/toggle, which call
        it AFTER releasing _lock). Calling abort() under _lock was the root cause of the transient
        control-lock wedge under rapid automated toggling (validation NEW-2): if the abort() (proxied
        to the child) blocks briefly on the recorder's internal state during a fast re-arm, the handler
        thread holds _lock and serializes every later start/stop/toggle (voicectl start/stop/toggle
        then hit `timeout` → exit 124; only the lock-free `status` stays responsive). Moving abort()
        out from under _lock is safe because (a) the listening Event gate in on_final + the run()
        loop already guarantee correctness the instant _listening is cleared (no finals typed, no
        new text() calls), (b) set_microphone(False) (proxied to the child) already halts audio
        queueing, and (c) abort() is merely a nudge to unblock a sleeping text(); called right after
        lock release it still wakes the same sleeping text(), and the loop re-checks _listening
        (already cleared). A fast re-arm races the delayed abort() harmlessly: abort() is a no-op
        when no text() is blocked, and any straggler final is dropped by the on_final gate.
        (bugfix validation NEW-2)
        """
        self._listening.clear()
        self._last_speech_monotonic = None  # not listening → idle clock is inactive
        self._disarmed_monotonic = time.monotonic()  # start the idle-UNLOAD clock (P1.M3.T1.S1)
        if self._host is not None:
            self._host.set_microphone(False)
        self._feedback.set_listening(False)
        self._feedback.set_phase("idle")  # Issue 2 / P1.M2.T1.S1: 'loaded / not listening' ⇒ phase idle (PRD §4.2bis, §4.6)
        # NOTE: caller MUST call self._safe_abort() AFTER releasing _lock (see start/stop/toggle).

    def _touch_speech(self) -> None:
        """Mark 'recognized speech happened now' — resets the idle auto-stop clock.

        Wired into the host's 'speech' event (the child's realtime partial callback fires
        on_speech → ('speech', {}) → the host reader thread calls this). Called from the host's
        reader thread; the float store is atomic in CPython. Finals are always preceded by
        partials, so this single hook covers all active speech.
        """
        self._last_speech_monotonic = time.monotonic()

    def _on_partial(self, text: str) -> None:
        """Handle a realtime partial from the host's reader thread (P1.M3.T2.S2 re-plan).

        Mirrors the in-process _build_callbacks partial callback: update the Feedback partial +
        count it for the latency log. The 'speech' event (fired alongside by the child's on_speech
        hook) drives _touch_speech separately. Called from the host reader thread (daemon thread).
        """
        self._feedback.update_partial(text)
        self._latency.note_partial(text)

    def _maybe_auto_stop(self) -> None:
        """Disarm if listening AND idle beyond cfg.asr.auto_stop_idle_seconds. Thread-safe (_lock).

        Re-checks the idle deadline UNDER the lock so a partial arriving between the watchdog's
        1s tick and here cancels the stop (no false disarm). threshold<=0 disables (no-op). Called
        by _idle_watchdog ~once/second; also safe to call directly (unit tests do).
        """
        threshold = self._cfg.asr.auto_stop_idle_seconds
        if threshold <= 0:
            return
        disarmed = False
        with self._lock:
            if not self._listening.is_set() or self._last_speech_monotonic is None:
                return
            if time.monotonic() - self._last_speech_monotonic < threshold:
                return
            logger.info(
                "voice-typing auto-stop: %.1fs of no recognized speech; disarming "
                "(set [asr] auto_stop_idle_seconds=0 to disable)", threshold,
            )
            self._disarm()
            disarmed = True
        # abort() moved OUT of _lock (validation NEW-2; see _disarm docstring) + gated on
        # _text_in_flight (validation Issue 1; see _safe_abort).
        if disarmed and self._host is not None:
            self._safe_abort()

    def _idle_watchdog(self) -> None:
        """Background thread: periodically call _maybe_auto_stop(). Started by run(); daemon thread.

        Ticks via _shutdown.wait(1.0) so it both sleeps ~1s AND exits promptly on shutdown. The
        check swallows its own exceptions so a transient error never kills the watchdog.
        """
        while not self._shutdown.wait(1.0):
            try:
                self._maybe_auto_stop()
            except Exception:
                logger.exception("idle auto-stop check raised; continuing")

    def _idle_unload_watchdog(self) -> None:
        """Background thread: periodically call _maybe_idle_unload(). Started by run(); daemon thread.

        P1.M3.T1.S1 / PRD §4.2bis Idle unload. Mirrors _idle_watchdog: ticks via _shutdown.wait(1.0)
        (sleeps ~1s AND exits promptly on shutdown) and swallows its own exceptions.
        """
        while not self._shutdown.wait(1.0):
            try:
                self._maybe_idle_unload()
            except Exception:
                logger.exception("idle unload check raised; continuing")

    def _maybe_idle_unload(self) -> None:
        """If the mic has been DISARMED long enough, tear down the recorder to reclaim VRAM.

        P1.M3.T1.S1 / PRD §4.2bis. Lock-free pre-check (atomic bool/float/Event reads are safe in
        CPython) so the common path (not time yet) does NOT acquire _lock every tick. When the
        pre-check passes, delegate to _unload_recorder(), which does the authoritative re-check +
        bounded teardown UNDER _lock (single-flight: a racing arm waits, then loads fresh).

        threshold<=0 disables (short-circuit, never calls _unload_recorder). Composes with idle
        auto-stop: _maybe_auto_stop's _disarm() is what stamps _disarmed_monotonic, so the 30s
        auto-stop starts this 30-min clock for free.
        """
        threshold = self._cfg.asr.auto_unload_idle_seconds
        if threshold <= 0:
            return
        # Lock-free pre-check (avoid hammering _lock every 1s). _unload_recorder re-checks under _lock.
        if (
            not self._models_loaded
            or self._listening.is_set()
            or self._disarmed_monotonic is None
            or time.monotonic() - self._disarmed_monotonic < threshold
        ):
            return
        self._unload_recorder()

    def _unload_recorder(self) -> None:
        """Back-compat alias for _unload_host (P1.M3.T2.S2 re-plan renamed the method).

        Kept under the old name so _maybe_idle_unload's call site is unchanged.
        """
        self._unload_host()

    def _unload_host(self) -> None:
        """Tear down the resident recorder-host child to reclaim VRAM (PRD §4.2bis Idle unload). Single-flight.

        THE line that makes T6(d-gone) pass. Acquires _lock (the SAME lock _load_host uses) and
        re-checks the FULL unload condition UNDER the lock — including self._listening.is_set() — so
        an arm that raced this call (between the watchdog's lock-free pre-check and here) ABORTS the
        unload. self._host.stop() terminates the child PROCESS GROUP UNDER _lock so a concurrent
        arm's _load_host() blocks on this lock, waits for teardown, then spawns fresh (an arm never
        sees a half-torn-down host). host.stop() is bounded (~<=5s join then SIGKILL) + best-effort
        + never touches _lock, so holding _lock across it is safe (no deadlock). threshold<=0 is
        handled by _maybe_idle_unload; this method also guards for safety if called directly.

        After teardown: self._host=None, _models_loaded=False, phase 'unloaded', models_loaded False
        (so voicectl status reports it via P1.M2.T2.S1's surface). The run() loop then sees
        self._host is None -> idle (~0 VRAM); the next arm reloads via _load_host(). Killing the
        child GROUP releases ALL VRAM (including the realtime-model CUDA context) -> daemon tree
        ABSENT on nvidia-smi while the daemon lives (PRD §7.9 + §6 T6(d)).
        """
        threshold = self._cfg.asr.auto_unload_idle_seconds
        with self._lock:
            if (
                not self._models_loaded                     # nothing resident (or a load/unload beat us)
                or self._listening.is_set()                 # user armed — abort the unload (race guard)
                or self._disarmed_monotonic is None         # never disarmed (shouldn't happen here)
                or threshold <= 0                           # disabled
                or time.monotonic() - self._disarmed_monotonic < threshold  # not yet
            ):
                return
            logger.info(
                "voice-typing idle-unload: %.1fs disarmed; unloading models", threshold,
            )
            # _bounded_shutdown terminates the child PROCESS GROUP (releases ALL VRAM) — routed
            # through here so the existing teardown-routing test (test_unload_routes_through_
            # bounded_shutdown_so_arm_wait_is_bounded) still holds. It never touches _lock -> safe
            # to call under _lock. Bounded (~5s join then SIGKILL the group).
            self._bounded_shutdown(timeout=5.0)
            self._host = None
            self._models_loaded = False
            self._feedback.set_phase("unloaded")          # P1.M2.T2.S1 surface (CONSUME, don't re-add)
            self._feedback.set_models_loaded(False)       # P1.M2.T2.S1 surface

    def _refresh_mic_status(self, *, force: bool = False) -> None:
        """Run the mic probe (real or injected) and store ok/error. NEVER raises.

        TTL-cached (bugfix Issue 3 / P1.M2.T2.S1): the probe (~40ms PyAudio init in production) runs
        at most once every _MIC_PROBE_TTL_S (30s). When the last probe is within the TTL window this
        method returns early and the cached _mic_ok/_mic_error stay valid. force=True bypasses the
        gate (used by __init__ so construction always probes and sets the initial stamp; tests that
        swap mic_prober also use force=True to bypass the cache). _mic_probe_at is the
        time.monotonic() stamp of the last probe; 0.0 == never (sentinel matching
        MicRetryRateLimitFilter._last_seen) — in production monotonic is never 0.0, so the sentinel
        is unambiguous.

        Sanctioned caller of the probe (bugfix Issue 2 / P1.M1.T2.S1): both __init__ and _arm()
        route through here so the try/except + attribute update live in ONE place. A probe failure
        (pyaudio missing, no devices, any exception) degrades to _mic_ok=False + _mic_error=str(exc)
        — the daemon stays runnable (degraded mode is acceptable; PRD §4.4 spirit). Tests inject
        mic_prober to stay hermetic; production leaves it None -> self._probe_mic.

        Thread safety: called only under self._lock (via _arm) or in single-threaded __init__, so
        _mic_probe_at/_mic_ok/_mic_error need NO extra locking.
        """
        if not force and self._mic_probe_at != 0.0 and (
            time.monotonic() - self._mic_probe_at
        ) < _MIC_PROBE_TTL_S:
            return  # cached: last probe is within the TTL window -> keep _mic_ok/_mic_error
        prober = self._probe_mic if self._mic_prober is None else self._mic_prober
        try:
            ok, error = prober()
        except Exception as exc:  # defensive: a probe must never break startup or arm
            ok, error = False, str(exc)
        self._mic_ok = bool(ok)
        self._mic_error = error
        self._mic_probe_at = time.monotonic()  # stamp AFTER storing the result

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

    def _safe_abort(self) -> None:
        """Abort the recorder ONLY when a thread is blocked inside text() (validation Issue 1).

        RealtimeSTT's AudioToTextRecorder.abort() blocks on was_interrupted.wait(), an event that
        is set ONLY inside text() (transcription_api.py L37/L102). When the run() loop is NOT inside
        text() — i.e. it is disarmed/idle in time.sleep(0.05) — there is nothing to set that event,
        so an unconditional abort() blocks FOREVER. That deadlocked voicectl stop / toggle(off) /
        quit intermittently (a race between disarm clearing _listening and the subsequent abort()):
        if abort() fired while the loop was still in text() it returned fine; once the loop had
        returned to sleep() it hung indefinitely.

        Fix: gate abort() on the _text_in_flight flag (set by run() around recorder.text()). When no
        thread is in text() abort() is SKIPPED — it would be a no-op anyway (there is nothing to
        wake), so skipping it is correct, not just safe. Correctness does NOT depend on abort(): the
        listening Event gate in on_final + the run() loop + set_microphone(False) already guarantee
        the instant disarm takes effect (no finals typed, no new text() calls); abort() is merely a
        best-effort nudge to unblock a sleeping text() so the loop re-checks _listening/_shutdown
        promptly.

        Never re-raises (a wedged abort() under the rare overlap window must not stall the
        control-socket response). Called by stop()/toggle(off)/_maybe_auto_stop()/request_shutdown()
        AFTER releasing _lock (unchanged from validation NEW-2: abort() stays out of _lock).
        """
        if not self._text_in_flight.is_set():
            return  # no thread blocked in text() -> abort() would hang forever; skip it (no-op anyway)
        try:
            self._host.abort()
        except Exception:
            logger.exception("host.abort() raised (best-effort; ignored)")

    def start(self) -> None:
        # Lazy load (PRD §4.2bis): spawn the recorder-host child on the first arm. _load_host() is a
        # single-flight no-op once resident. Called OUTSIDE _lock (it acquire-release-reacquires that
        # lock; under _lock it would deadlock).
        if not self._load_host():
            return  # load failed → stay unarmed (phase already 'unloaded'; _load_error set)
        with self._lock:
            self._arm()

    def stop(self) -> None:
        with self._lock:
            self._disarm()
        # abort() moved OUT of _lock to avoid the control-lock wedge (validation NEW-2; see
        # _disarm docstring) AND gated on _text_in_flight to avoid the abort()-deadlocks-forever
        # bug when no thread is in text() (validation Issue 1; see _safe_abort).
        if self._host is not None:
            self._safe_abort()

    def toggle(self) -> None:
        # Decide arm vs disarm, then act. Disarm is fast; the ARM path lazy-loads FIRST (outside _lock —
        # _load_host acquire-release-reacquires that lock; calling it under _lock deadlocks). The read/act split
        # is race-tolerant exactly like the abort()-outside-_lock design (the listening Event + on_final gate are
        # the source of truth; toggle is user-paced).
        with self._lock:
            disarmed = self._listening.is_set()
        if disarmed:
            with self._lock:
                self._disarm()
            # abort() moved OUT of _lock (validation NEW-2) + gated on _text_in_flight (validation
            # Issue 1). Only on disarm — arming must not abort a sibling text() that's about to
            # start transcribing.
            if self._host is not None:
                self._safe_abort()
        else:
            if not self._load_host():
                return  # load failed → stay unarmed
            with self._lock:
                self._arm()

    def request_shutdown(self) -> None:
        """Signal run() to exit + tear down the child so a blocked text() unblocks (BUG-1 fix).

        Sets _shutdown (the real signal run() checks on its 0.05s tick) + aborts any in-flight
        text() (a best-effort nudge) + tears down the recorder-host child via _bounded_shutdown().
        The child teardown is REQUIRED for the SIGTERM/systemctl-stop path: while listening the
        run() loop is blocked inside host.text(), whose wait-loop only returns on a "final" event
        OR child death. The child's aborted recorder.text() does NOT always fire a final, so
        _safe_abort() alone leaves the loop stranded ~40% of the time -> SIGKILL after
        TimeoutStopSec. Killing the child (host.stop()) guarantees host.text()'s loop sees a dead
        child and returns within ~0.5s -> run() exits -> main()'s finally runs -> clean exit.

        This mirrors what the voicectl quit path already does (ControlServer._dispatch("quit") ->
        request_shutdown() -> on_quit=daemon.shutdown()). P1.M1.T2.S1: this method CLAIMS
        _shutdown_done under _lock and signals _teardown_done on completion, so a CONCURRENT
        shutdown() (main-thread finally, on the SIGTERM path) WAITS for this teardown instead of
        starting a second one (bugfix Issue 1). The quit path is unaffected (sequential: shutdown()
        sees _teardown_done already set and returns immediately).

        abort() + _bounded_shutdown() are called OUTSIDE _lock (validation NEW-2; see _disarm
        docstring) so a slow teardown can't wedge the shutdown signal or block concurrent
        start/stop/toggle. Only the _shutdown_done claim is under _lock (short critical section).
        _shutdown.set() is the real signal the run() loop checks.
        """
        self._shutdown.set()
        if self._host is None:
            return  # nothing loaded (never armed, or already torn down) -> _shutdown is enough
        # P1.M1.T2.S1 / bugfix Issue 1: CLAIM the teardown so a concurrent shutdown() (main-thread
        # finally, on the SIGTERM path) WAITS on _teardown_done instead of starting a SECOND
        # _bounded_shutdown() (the double-teardown that blew TimeoutStopSec). Under _lock (short
        # critical section); the teardown itself runs OUTSIDE _lock. Idempotent: a second signal /
        # quit+signal overlap sees _shutdown_done already True and returns here.
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return  # another path already claimed/is doing the teardown — don't re-tear-down
            self._shutdown_done = True
        # abort() gated on _text_in_flight (validation Issue 1; see _safe_abort): when no thread is
        # blocked in text() there is nothing to wake — abort() would hang forever.
        self._safe_abort()    # break any blocked text() so run() can return promptly (NOT under _lock)
        # Tear down the child (BUG-1): kills the process group so host.text()'s wait-loop detects
        # child death and returns, unblocking the run() loop for a prompt, bounded SIGTERM exit.
        # _bounded_shutdown() is best-effort + never re-raises; safe to run alongside main()'s
        # finally-block shutdown() (which is a guarded no-op if the child is already gone).
        # P1.M1.T2.S1: wrap in try/finally so _teardown_done ALWAYS fires — a concurrent shutdown()
        # is waiting on it (a missing signal would deadlock it until the wait timeout).
        try:
            self._bounded_shutdown()
        finally:
            self._teardown_done.set()

    def is_listening(self) -> bool:
        return self._listening.is_set()

    @property
    def _recorder(self) -> Any:
        """Back-compat shim for tests that assert on d._recorder (P1.M3.T2.S2 re-plan).

        The daemon now owns self._host (a RecorderHost or a _LegacyRecorderHostAdapter). Tests that
        injected a legacy stub via recorder= and assert d._recorder is <stub> / d._recorder is None
        read this property. It returns the adapter's WRAPPED recorder when a legacy adapter is in
        use, else None (a real RecorderHost child has no in-process recorder object on the daemon
        side; lazy boot has no host at all). Setting it is a no-op kept for test compatibility
        (test_shutdown_is_noop_when_recorder_is_none sets d._recorder = None — mapped to dropping
        the host).
        """
        host = self.__dict__.get("_host")
        if isinstance(host, _LegacyRecorderHostAdapter):
            return host._recorder
        return None

    @_recorder.setter
    def _recorder(self, value: Any) -> None:
        # test_shutdown_is_noop_when_recorder_is_none sets d._recorder = None to simulate "no
        # recorder". Map that to dropping the host so shutdown() is a no-op (the production
        # invariant: a None host = nothing to tear down).
        if value is None:
            self.__dict__["_host"] = None
            self.__dict__["_models_loaded"] = False
        # A non-None set is not used by any test; ignore it (the host is owned via _load_host).

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

        Returns {listening, phase, models_loaded, load_error, partial, last_final, uptime_s, device,
        compute_type, final_model, realtime_model, mic_ok, mic_error}. phase/models_loaded come from
        the LIVE in-memory Feedback state (the lazy-load lifecycle, §4.2bis — unloaded/loading/idle/
        listening/speaking + models resident bool); load_error is the daemon attr _load_recorder sets
        on failure. mic_ok/mic_error come from S1's PyAudio probe
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
            "phase": snap.get("phase", "unloaded"),          # P1.M2.T2.S1: lifecycle phase (§4.2bis)
            "models_loaded": snap.get("models_loaded", False),  # P1.M2.T2.S1: models resident?
            "load_error": self._load_error or "",            # P1.M2.T2.S1: last load failure (None -> "")
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

    def _bounded_shutdown(self, timeout: float = 5.0) -> None:
        """Tear down the recorder-host child with a hard timeout (PRD §4.2; §8 risk row).

        P1.M3.T2.S2 (re-plan): this now routes through self._host.stop() — for a REAL RecorderHost
        that terminates the child PROCESS GROUP (os.killpg, bounded by `timeout` then SIGKILL —
        releases ALL VRAM incl. grandchildren; cannot reproduce RealtimeSTT's ~90 s shutdown wedge).
        For the LEGACY _LegacyRecorderHostAdapter (tests), stop() does the in-process force-cleanup
        (bounded shutdown() + force-terminate transcript_process/reader_process + drop the realtime
        model ref). Both paths are bounded + best-effort + never re-raise.

        Budget (bugfix Issue 1 / Fix 1C, P1.M1.T2.S2): host.stop(timeout=5) -> proc.join(5) +
        _terminate_group() (killpg) + join(2) = ~7s max per call (only if the child wedges the full
        join; normally far less); plus ControlServer.stop() join(2) = ~2s. With daemon single-flight
        (P1.M1.T2.S1: exactly ONE _bounded_shutdown runs on the SIGTERM path) the total is <= ~9s —
        comfortable headroom under systemd TimeoutStopSec=15. The default was 10.0 (-> ~12s/call,
        ~14s total, no margin); 5.0 makes the clean single-teardown path fit.

        Does NOT null self._host (the caller — _unload_host / shutdown — does that after this
        returns). Idempotent-vs-missing-host: a None host is a no-op (a session that never armed).
        """
        if self._host is None:
            return
        try:
            self._host.stop(timeout=timeout)
        except Exception:
            logger.exception("host.stop() raised during teardown (best-effort; ignored)")

    def shutdown(self) -> None:
        """Full recorder teardown — BOUNDED (PRD §4.2; §4.2bis idle-unload prerequisite; §8 risk row).

        Idempotent + defensive. Delegates to _bounded_shutdown(): runs recorder.shutdown() in a
        daemon thread under a hard timeout (default 5s); on timeout it force-terminates the
        spawn-started transcript_process + reader_process (the CUDA/VRAM holders) so VRAM is
        released and a racing re-arm under the single-flight lock is never blocked for the ~90s
        RealtimeSTT wedge (root cause: an unbounded threading.Thread.join() inside
        shutdown_recorder() — confirmed). Keeps the idempotency + defensive guarantees; never
        re-raises.

        IDEMPOTENT + SINGLE-FLIGHT (P1.M1.T2.S1 / bugfix Issue 1): _shutdown_done (under
        _lock) + _teardown_done (Event) coordinate the SIGTERM path, where request_shutdown()
        (signal thread) + this method (main-thread finally) run CONCURRENTLY. The first caller
        claims + does the teardown + signals _teardown_done; a concurrent second caller WAITS on
        _teardown_done (bounded _TEARDOWN_WAIT_TIMEOUT) instead of starting a second
        _bounded_shutdown(). The quit path (sequential) sees _teardown_done already set and
        returns immediately. A wait timeout falls back to this method's own teardown, kept
        single-flight by RecorderHost._stop_lock (P1.M1.T1.S1).
        DEFENSIVE: a recorder.shutdown() failure is logged inside the bounded thread via
        logger.exception, NOT re-raised — the daemon is exiting and teardown is best-effort (a
        broken teardown must not mask the original shutdown reason).

        NEVER call this on toggle/stop (models must stay resident — those use set_microphone+
        abort). The sanctioned callers are the quit on_quit hook (after request_shutdown() broke
        text()) and main()'s finally block (after run() returns; covers the signal path). Must NOT
        run while the main thread is inside recorder.text() — request_shutdown()/abort() guarantees
        it has exited text() before this is reached.
        """
        # P1.M1.T2.S1 / bugfix Issue 1: daemon-level single-flight. If request_shutdown() (the SIGTERM
        # signal thread) already CLAIMED _shutdown_done, a second _bounded_shutdown() here would race
        # it (the double-teardown that blew TimeoutStopSec). Instead WAIT on _teardown_done (bounded,
        # OUTSIDE _lock — a slow teardown must not hold _lock) and return when it finishes. On
        # timeout (signal thread died) fall back to our OWN teardown — safe because
        # RecorderHost._stop_lock (P1.M1.T1.S1) serializes host.stop(), so the fallback cannot
        # reproduce the double-teardown.
        with self._lock:
            already_claimed = getattr(self, "_shutdown_done", False)
            if not already_claimed:
                self._shutdown_done = True        # WE claim the teardown (called-first / normal path)
        if already_claimed:
            # Another path is doing (or did) the teardown — wait for it, do NOT start a second one.
            if self._teardown_done.wait(timeout=_TEARDOWN_WAIT_TIMEOUT):
                return                           # in-flight teardown finished -> done (no second teardown)
            logger.warning(
                "shutdown(): in-flight teardown did not signal within %.1fs; proceeding with fallback",
                _TEARDOWN_WAIT_TIMEOUT,
            )
            # fall through: do our own teardown as the fallback (safe via _stop_lock)
        if self._host is None:
            # M2 lazy-load prep: the recorder-host child is spawned on first arm, so it may never
            # exist (e.g. a session that never armed). Nothing to tear down.
            return
        try:
            self._bounded_shutdown()
        except Exception:
            # Defensive belt-and-suspenders: _bounded_shutdown is already best-effort, but
            # shutdown() itself must NEVER re-raise (a teardown failure must not mask the original
            # shutdown reason).
            logger.exception("bounded teardown failed (best-effort; ignored)")
        finally:
            # P1.M1.T2.S1: signal any waiter (covers the called-first path + the fallback path).
            self._teardown_done.set()


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

    def _arm_response(self) -> dict:
        """Build the response after a start/toggle ARM attempt (PRD §4.2bis / P1.M2.T1.S2).

        After P1.M2.T1.S1, start()/toggle() call _load_recorder() BEFORE arming; on a load failure the arm is
        suppressed (daemon stays not-listening) and self._load_error is set. Per §4.2bis the arm command MUST
        then return {"ok":false,"error":...} (NOT ok:true with listening:false, which voicectl would render as a
        silent 'listening: off'). _load_error is reset by _load_recorder on each fresh attempt and set only on a
        fresh failure, so a set value read on an arm attempt is always THIS attempt's failure (never stale — see
        P1.M2.T1.S2 research §4.1). getattr(..., None) keeps the duck-typed test _StubDaemon (no _load_error) on
        the ok:true path. The 'loading models…' hint itself is printed CLIENT-SIDE by ctl.py during the block;
        this method only shapes the (eventual) post-load response.
        """
        load_error = getattr(self._daemon, "_load_error", None)
        if load_error and not self._daemon.is_listening():
            return {"ok": False, "error": f"model load failed: {load_error}"}
        return {"ok": True, **self._daemon.status_snapshot()}

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
            was_listening = self._daemon.is_listening()
            self._daemon.toggle()
            if not was_listening:            # this toggle attempted to arm -> a load may have failed (§4.2bis)
                return self._arm_response()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "start":
            self._daemon.start()
            return self._arm_response()      # ok:false+error if the first arm's model load failed (§4.2bis)
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
        # One LatencyLog shared by _load_recorder()'s build_recorder (recorder on_vad_stop/partial callbacks) and the
        # daemon's on_final.finalize_utterance. (bugfix Issue 3 CPU-fallback now lives in _load_recorder — P1.M2.T1.S1
        # lazy load — so main() no longer retries here; construction is fast and model-free.)
        latency = LatencyLog()
        daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)   # FAST — no models loaded (lazy, §4.2bis)
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
