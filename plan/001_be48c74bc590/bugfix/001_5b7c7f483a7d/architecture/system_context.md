# System Context: Voice-Typing Bugfix

## Project Overview
A fully-local voice-typing daemon for Linux (tmux/Hyprland) built on RealtimeSTT.
Runs as a systemd user service. Core functionality is solid (T1 offline suite 7/7 passes).
This bugfix targets 7 defects found by creative end-to-end QA against PRD §4–§7.

## Key Architecture Components

### daemon.py (voice_typing/daemon.py — ~960 lines)
- `_FIXED_KWARGS` (lines 96-108): 10 device-independent kwargs for AudioToTextRecorder.
  **Missing `no_log_file: True`** → root cause of Issue 1.
- `_resolve_device_config(cfg)` (lines 116-131): resolves device/compute_type/models via
  `cuda_check.resolve_device_and_models()`. Single chokepoint for device selection.
- `cfg_to_kwargs(cfg)` (lines 133-156): builds recorder kwargs from config + `_FIXED_KWARGS`.
- `_filter_kwargs_to_signature()` (lines 191-217): drops kwargs not in AudioToTextRecorder.__init__.
- `_construct()` (lines 209-223): builds kwargs + callbacks + filtered → recorder_cls(**filtered).
- `build_recorder()` (lines 226-237): lazy-imports AudioToTextRecorder, calls _construct.
- `VoiceTypingDaemon.__init__` (~300-326): constructs recorder via build_recorder if not injected.
- `on_final(text)` (lines 450-489): gate → clean → type → record + log. **No lock** → Issue 5.
- `_arm()`/`_disarm()` (lines 490-502): set_microphone(True/False) — flag flip only, no I/O check.
- `status_snapshot()` (lines 538-559): returns 8 fields. **No mic health field** → Issue 2.
- `_log_resolved_device()` (lines 430-443): calls real resolver → pollutes sys.modules → Issue 4.
- `_setup_logging()` (lines 867-886): basicConfig(stream=sys.stderr) → journald.
- `main()` (lines 887-960): construction at line 927, bare except at 936. **No CPU retry** → Issue 3.

### cuda_check.py (voice_typing/cuda_check.py — ~170 lines)
- `CUDA_DEFAULTS` (lines 45-52): cuda/float16/distil-large-v3/small.en.
- `CPU_FALLBACK` (lines 53-59): cpu/int8/small.en/tiny.en.
- `_cuda_device_count()` (lines 61-79): wraps ctranslate2.get_cuda_device_count(). **Driver-only probe.**
- `resolve_device_and_models()` (lines 114-132): returns CUDA_DEFAULTS or CPU_FALLBACK.

### ctl.py (voice_typing/ctl.py — ~140 lines)
- `_COMMANDS = ("toggle", "start", "stop", "status", "quit")` (line 30).
- `_build_parser()` (lines 78-94): argparse with `choices=_COMMANDS`.
- `main()` (lines 98-128): argparse SystemExit(2) overlaps "daemon not running" exit 2 → Issue 7.
- `format_result()` (lines 42-73): returns (text, code) with code ∈ {0, 1}.

### typing_backends.py (voice_typing/typing_backends.py — ~200 lines)
- Module docstring lines 19-23: false claim "daemon serializes on_final calls" → Issue 5.
- WtypeBackend/YdotoolBackend/TmuxBackend: all stateless, subprocess.run per call.

### feedback.py (voice_typing/feedback.py — ~150 lines)
- Module docstring lines 31-35: false claim "daemon serializes on_final anyway" → Issue 5.
- State file + hyprctl notify. Lock-free via CPython atomic dict ops + os.replace.

### config.py (voice_typing/config.py — ~180 lines)
- `AsrConfig` (lines 49-55): no `compute_type` field (derived in daemon).
- `LogConfig` (lines 117-127): only `level` field. No `no_log_file` config field.

### External: RealtimeSTT v1.0.2 (installed in .venv)
- `AudioToTextRecorder.__init__` accepts `no_log_file: bool = False` (audio_recorder.py:180).
- `_configure_logger()` (core/initialization.py:305-335): opens 'realtimesst.log' FileHandler
  at DEBUG level with relative path (CWD) when `no_log_file=False`. No rotation.
- `text()` / `transcribe_text()` (core/transcription_api.py:22-43): fires on_final callback
  via `threading.Thread(...).start()` — unserialized, fire-and-forget.
- `set_microphone()` (audio_recorder.py:718-723): flips `use_microphone` flag only. No I/O check.
- `audio_input_worker.py` retry loop (lines ~100-177): infinite loop, sleep(3), exc_info=True
  traceback on every mic connection failure. No backoff, no max-retries.
- Audio worker is a `threading.Thread` on Linux (core/runtime.py:17-37), not a subprocess.

### install.sh (~154 lines)
- Preflight checks (lines 36-42): XDG_RUNTIME_DIR, uv, systemctl. **No portaudio check** → Issue 6.
- `set -euo pipefail` at line 25.

### systemd/voice-typing.service
- `Restart=on-failure`, `RestartSec=2`. ExecStart=launch_daemon.sh (not python directly).
- No WorkingDirectory= → CWD is $HOME → realtimesst.log written to $HOME.

### launch_daemon.sh
- Sets LD_LIBRARY_PATH from nvidia-*-cu12 wheels, then `exec python -m voice_typing.daemon`.
- Primary cuDNN fix. Issue 3's retry is defense-in-depth.

## Test Infrastructure
- `tests/test_daemon.py`: ~44KB, uses `_cuda_resolve(monkeypatch, mapping)` helper and
  `_StubRecorder` for hermetic testing. Some tests do NOT monkeypatch → pollute sys.modules.
- `tests/test_voicectl.py`: ~7KB, includes `test_ctl_module_present_and_imports_pure` (Issue 4).
- `tests/test_feed_audio.py`: ~28KB, offline pipeline test. Passes `no_log_file=True` at line 275.
- pytest uses default alphabetical collection order (no [tool.pytest.ini_options] in pyproject.toml).
