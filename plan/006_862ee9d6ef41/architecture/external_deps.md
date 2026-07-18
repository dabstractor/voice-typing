# External Dependencies & Integration Points — voice-typing (plan/006)

## Runtime Dependencies (pyproject.toml)
- `realtimesttt[faster-whisper,silero-vad]` — core STT engine, pulls faster-whisper (CTranslate2), torch (for Silero VAD), pyaudio, webrtcvad
- `nvidia-cublas-cu12` — cuBLAS shared objects for CTranslate2 CUDA inference
- `nvidia-cudnn-cu12==9.*` — cuDNN 9 shared objects (must be v9 for current CTranslate2)
- `huggingface_hub>=0.23` — model prefetch via snapshot_download
- Python >=3.12,<3.13

## System Dependencies (machine-verified in PRD §2)
- **NVIDIA driver 610.43.02**, CUDA UMD 13.3, cuda 13.3.0-1 (no system cuDNN — use pip wheels)
- **ctranslate2 CUDA is the must-have**: `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` → ≥1
- **PipeWire 1.6.6** with PulseAudio compat (pipewire-pulse)
- **Hyprland** (Wayland compositor) with XWayland (DISPLAY=:1)
- **ydotool 1.x** (ydotoold running as systemd user service), wtype, xdotool
- **espeak-ng, sox, ffmpeg** for test audio generation
- **tmux** — MUST call `/usr/bin/tmux` in scripts (zsh alias wraps it)
- **uv** at `/home/dustin/.local/bin/uv` — NEVER use bare `python3` or `pip` (shell aliases)

## Key Integration Patterns
1. **RealtimeSTT v1.x API**: `recorder.text(on_final_cb)` blocks per utterance; `feed_audio()` for offline tests;
   callbacks: `on_realtime_transcription_stabilized`, `on_vad_detect_start`, `on_vad_stop`
2. **cuDNN/cuBLAS lib path**: `launch_daemon.sh` recomputes from live nvidia-*-cu12 wheels on every launch,
   exports LD_LIBRARY_PATH before exec'ing python. No baked Environment= in systemd unit (goes stale on uv sync).
3. **Recorder-host subprocess**: daemon NEVER imports RealtimeSTT/torch/ctranslate2 directly.
   All CUDA lives in the child. Teardown = proc.join(5s) then SIGKILL the process group.
4. **State file IPC**: `$XDG_RUNTIME_DIR/voice-typing/state.json` (atomic write via tempfile+rename),
   consumed by tmux status.sh and any external UI.
5. **Control socket**: `$XDG_RUNTIME_DIR/voice-typing/control.sock` (SOCK_STREAM, JSON lines protocol).
   **WARNING (AGENTS.md)**: ctl.py send_command uses sock.makefile("r") — NO socket timeout.
   Always wrap voicectl calls in `timeout 30`.

## Known Architecture Decisions (from git history)
- VT-001: `voicectl status` was reported as importing CUDA in the daemon process (PRD §4.2bis caveat)
- VT-003: `__REPO__` placeholder in systemd unit, substituted by install.sh
- VT-004: graphical-session.target wiring (was default.target, caused cold-boot race)
- VT-006: bare "you" removed from blocklist (common word, not a hallucination)
- Recorder-host subprocess model resolves the 90s shutdown hang (killpg instead of recorder.shutdown())
- Lite mode silence gate override is load-bearing (silence gate, not model speed, is the latency bottleneck)

## HuggingFace Model Cache
- `Systran/faster-distil-whisper-large-v3` (final model)
- `Systran/faster-whisper-small.en` (realtime + lite model)
- Cached at `~/.cache/huggingface`, prefetched by install.sh/prefetch.py
- HF_HUB_OFFLINE=1 set by launch_daemon.sh at runtime (no network at runtime)