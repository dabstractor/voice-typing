# System Context: Voice-Typing Bug Fix Architecture

## Project Overview
A fully-local voice-typing daemon for Linux (Hyprland/Wayland) using RealtimeSTT
(faster-whisper/CTranslate2) for speech-to-text. Managed by systemd as a user service.
The daemon communicates with a `voicectl` CLI over a Unix domain socket (JSON lines protocol).

## Architecture — Key Components

### Process Model
- **Main daemon process** (`voice_typing/daemon.py`): The `VoiceTypingDaemon` class runs a
  listen-forever loop on the main thread. It owns a `ControlServer` (socket listener) and
  signal handlers for SIGTERM/SIGINT.
- **Recorder-host child subprocess** (`voice_typing/recorder_host.py`): The
  `AudioToTextRecorder` (RealtimeSTT) runs in a SEPARATE child process (spawn), managed by
  the `RecorderHost` class. This is critical: ALL CUDA/VRAM lives in the child, so terminating
  the child's process group releases ALL VRAM. The daemon process never touches CUDA.
- **IPC**: Two `multiprocessing.Queue` objects (cmd_q: daemon→child, evt_q: child→daemon)
  plus a `multiprocessing.Event` (abort_event). A daemon reader thread drains evt_q.

### Threading Model
- **Main thread**: runs `VoiceTypingDaemon.run()` (the listen-forever loop). Also runs
  `main()`'s finally block for teardown.
- **Control server accept thread** + per-connection **worker threads**: handle socket commands.
- **Signal handler**: runs in the MAIN thread (CPython signal semantics), spawns a daemon
  thread to call `request_shutdown()`.
- **Idle watchdog threads**: `_idle_watchdog` (auto-stop) and `_idle_unload_watchdog` (VRAM
  reclaim), both daemon threads.
- **Recorder host reader thread**: daemon thread draining evt_q.

### Concurrency Primitives
- `self._lock` (threading.Lock): protects _listening, _models_loaded, _loading, phase transitions.
  Acquired by start/stop/toggle/_arm/_disarm/_load_host/_unload_host.
- `self._load_cond` (threading.Condition over self._lock): single-flight load wait.
- `self._on_final_lock` (threading.Lock): serializes on_final callbacks (separate from _lock).
- `self._listening` (threading.Event): the master listening gate.
- `self._shutdown` (threading.Event): signals run() to exit.
- `self._text_in_flight` (threading.Event): set while run() loop is inside host.text().
- `self._shutdown_done` (getattr-guarded bool): idempotency flag for daemon.shutdown().
- `RecorderHost._stop_lock`: **DOES NOT EXIST** — this is the root cause of Issue 1.

### Test Infrastructure (tests/test_daemon.py)
- `_StubRecorder`: legacy stub with text/set_microphone/abort/shutdown. Wrapped in
  `_LegacyRecorderHostAdapter` when injected via `recorder=`.
- `_FakeHost`: mirrors RecorderHost's surface (spawn/set_microphone/abort/text/stop/device/
  is_alive). Has configurable `spawn_result` and `_alive` flag. Used when injected via
  `host_factory=`.
- `_make_daemon()`: convenience constructor returning (daemon, feedback, recorder, backend).
- `_make_daemon_with_feedback()`: variant with real Feedback + tmp_path state file.
- Integration pattern: `threading.Thread(target=d.run, daemon=True).start()` + `_wait_for()`
  for async assertions. Teardown via `d.request_shutdown()` + join.
- All tests are CUDA-free, GPU-free, fast (no real subprocess spawn for the recorder).

## PRD Acceptance Criteria (relevant to bugs)
- §7.9: "the teardown is bounded (completes in seconds, no 90s hang)"
- §4.2bis: bounded teardown is a HARD prerequisite for idle-unload
- §4.6: "once loaded, phase cycles idle/listening/speaking"
- §4.2bis: "If the load fails, daemon returns to unloaded... MUST NOT leave a half-constructed recorder"
- §7.6: "voicectl status must accurately report state"
- §4.5: config schema; "Unknown keys raise TypeError... a typo'd config key surfaces loudly"
- systemd TimeoutStopSec=15 (systemd/voice-typing.service)

## Files Modified by This Bug Fix
| Issue | Primary File | Key Methods/Locations |
|-------|-------------|----------------------|
| 1 (Critical) | `voice_typing/recorder_host.py` | `RecorderHost.__init__`, `RecorderHost.stop()` |
| 1 (Critical) | `voice_typing/daemon.py` | `request_shutdown()`, `_bounded_shutdown()`, `shutdown()` |
| 2 (Major) | `voice_typing/daemon.py` | `_disarm()` |
| 3 (Major) | `voice_typing/daemon.py` | `run()`, `_load_host()` |
| 4 (Minor) | `voice_typing/config.py` | `VoiceTypingConfig.from_toml()` |
| All | `tests/test_daemon.py`, `tests/test_recorder_host.py`, `tests/test_config.py` | New tests |
