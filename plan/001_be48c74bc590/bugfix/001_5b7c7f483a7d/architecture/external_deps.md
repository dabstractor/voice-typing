# External Dependencies: RealtimeSTT v1.0.2 API Surface

## Verified API (installed in .venv/lib/python3.12/site-packages/RealtimeSTT/)

### AudioToTextRecorder.__init__
- Located in `audio_recorder.py`, ~85 parameters.
- Key accepted kwargs relevant to this bugfix:
  - `no_log_file: bool = False` (line 180) — **Issue 1 fix point**. When True, no FileHandler.
  - `device: str` — "cuda" or "cpu".
  - `compute_type: str` — "float16" (CUDA) or "int8" (CPU).
  - `model: str` — final model name.
  - `realtime_model_type: str` — partials model name.
  - `use_microphone: bool` — True for live mic, False for feed_audio() tests.
  - `on_realtime_transcription_stabilized` — partial callback.
  - `on_transcription_finished` — final callback (via `text()` method).

### AudioToTextRecorder.set_microphone(microphone_on=True)
- Located in `audio_recorder.py:718-723`.
- Sets `self.use_microphone.value = microphone_on` (a ctypes shared value).
- **No I/O check, no return value.** Cannot detect mic failure.
- Called by daemon's `_arm()`/`_disarm()`.

### AudioToTextRecorder.text(on_transcription_finished=None)
- Located in `audio_recorder.py:663-673`, delegates to `core/transcription_api.py:22-43`.
- Blocks until one utterance finalizes (`wait_audio()`).
- Then: `threading.Thread(target=on_transcription_finished, args=(recorder.transcribe(),)).start()`
- **Fire-and-forget**: returns immediately after thread.start(), no join.
- The callback thread is NOT serialized with subsequent callbacks.

### Logger Configuration (_configure_logger)
- Located in `core/initialization.py:305-335`.
- When `no_log_file=False` (default): opens `logging.FileHandler('realtimesst.log')` at DEBUG.
  - Relative path → CWD of the process (under systemd = $HOME if no WorkingDirectory=).
  - No rotation, no maxBytes, no cap. Appends across daemon lifetime.
- Also adds a `StreamHandler()` (→ stderr) at recorder.level (default WARNING).
- Both handlers added to `logging.getLogger("realtimestt")`.

### Audio Input Worker (mic capture)
- Located in `core/audio_input_worker.py`.
- On Linux, runs as `threading.Thread` (daemon=True) — NOT a subprocess.
  - See `core/runtime.py:17-37` (`start_recorder_worker`).
- `initialize_audio_stream()` retry loop (lines ~100-177):
  - `while not shutdown_event.is_set():` — infinite loop.
  - On failure: `logger.error("Microphone connection failed: {e}. Retrying...", exc_info=True)`,
    `input_device_index = None`, `time.sleep(3)`, `continue`.
  - No max-retries, no backoff, no callback to daemon.

### Internal Logger Name
- `logging.getLogger("realtimestt")` — used by audio_input_worker.py, audio_recorder.py, etc.
- This is the logger that receives the mic-retry errors (at ERROR level).
- The daemon can attach a `logging.Filter` or custom Handler to this logger to rate-limit
  the traceback spam (Issue 2 fix point).

## PyAudio (system dependency)
- Required by RealtimeSTT for mic capture. Imported lazily inside `run_audio_data_worker`.
- System package: `portaudio` (Arch Linux: `pacman -S portaudio`).
- The daemon does NOT import pyaudio at module level. It can probe it for Issue 2's mic health
  detection, but must do so lazily (inside a function) to preserve `voice_typing.ctl` import purity.

## ctranslate2 (CUDA probe)
- `cuda_check.py` imports `ctranslate2` to call `get_cuda_device_count()`.
- `ctranslate2` imports `torch` transitively.
- Both pollute `sys.modules` — this is the root cause of Issue 4 (test isolation failure).

## systemd user service
- Unit: `systemd/voice-typing.service`.
- `ExecStart=launch_daemon.sh` (LD_LIBRARY_PATH wrapper, not python directly).
- `Restart=on-failure`, `RestartSec=2`.
- No `WorkingDirectory=` — CWD defaults to $HOME.
- stderr captured by journald automatically.
