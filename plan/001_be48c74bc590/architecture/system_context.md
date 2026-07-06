# System Context — voice-typing

**Project:** Fully-local voice typing for Linux terminal (tmux) / Wayland, via RealtimeSTT.
**Repo:** `/home/dustin/projects/voice-typing` — empty git repo (only `.git`, `PRD.md`, `.venv`, `plan/`).
**Engine:** RealtimeSTT v1.0.2 (faster-whisper/CTranslate2 on CUDA). 100% local at runtime.

---

## 1. Verified machine facts (do not re-derive)

| Fact | Value | Implication |
|---|---|---|
| OS | Arch Linux, kernel 7.0.12-arch1-1 | systemd user units, pacman |
| GPU | NVIDIA RTX 3080 Ti, **12 GiB VRAM**, driver 610.43.02, CUDA UMD 13.3 | cu12 wheels run fine (driver backward-compat). Budget ~2-4 GB VRAM for both models in float16. |
| Display | **Wayland / Hyprland** (uwsm/SDDM), XWayland present (`DISPLAY=:1`), `HYPRLAND_INSTANCE_SIGNATURE` set | wtype (virtual-keyboard-v1) is the primary typing backend. `hyprctl notify` works (no dunst/mako/waybar). |
| Audio | **PipeWire 1.6.6** (pipewire-pulse compat). Default source: webcam mono mic 48kHz s16le. | RealtimeSTT resamples to 16kHz internally. Use default source; don't fight the webcam mic. |
| Typing tools | `wtype` ✓, `ydotool` 1.x ✓, `xdotool` ✓. `ydotoold` running as enabled user systemd service. `/dev/uinput` is `crw-rw-rw-`, user in `input` group. | wtype default; ydotool fallback (auto-fallback on wtype failure); tmux backend for E2E test/SSH. |
| portaudio | **INSTALLED** (`portaudio 1:19.7.0-4`) — verified, do NOT try to install. | PyAudio dep satisfied. |
| Python/uv | `/home/dustin/.local/bin/uv` 0.7.11. `.venv` exists, **Python 3.12.10, NO packages installed yet**, NO `pyproject.toml` yet. | `uv init --bare --python 3.12` then `uv add`. |
| ctranslate2 | NOT installed (will arrive via realtimestt → faster-whisper). | Must verify CUDA after install: `ctranslate2.get_cuda_device_count() ≥ 1`. |
| tmux | `/usr/bin/tmux` (zsh aliases it — ALWAYS use full path in scripts). | E2E test backend. |
| Shell aliases | `python3`→`uv run`, `pip`→alias, `tmux`→zsh plugin. | In ALL scripts/bash use explicit paths: `/home/dustin/.local/bin/uv`, `.venv/bin/python`, `/usr/bin/tmux`. |

---

## 2. Target file map (from PRD §4.1 — to be created)

```
voice_typing/
├── __init__.py
├── daemon.py            # main loop (while: recorder.text(on_final)), listening.Event gate, control socket server, LD_LIBRARY_PATH-safe entry
├── config.py            # @dataclass + tomllib loader (XDG_CONFIG_HOME → repo → defaults)
├── typing_backends.py   # WtypeBackend / YdotoolBackend / TmuxBackend; type_text(text)
├── feedback.py          # atomic state.json writer + hyprctl notify + status.sh helper
├── textproc.py          # clean(text) -> str|None  (strip, min_chars, blocklist, whitespace)
├── ctl.py               # voicectl client CLI (JSON-lines over unix socket)
├── status.sh            # tmux status snippet helper (jq on state.json)
└── launch_daemon.sh     # sets LD_LIBRARY_PATH (cublas+cudnn) then execs python -m voice_typing.daemon
config.toml              # self-documenting defaults
systemd/voice-typing.service  # ExecStart → launch_daemon.sh
install.sh               # uv sync, prefetch models, CUDA smoke, service install, print snippets
hypr-binds.conf          # SUPER+ALT+D → voicectl toggle (Phase 2; user sources manually)
tests/                   # make_test_audio.sh, test_feed_audio.py, e2e_virtual_mic.sh, test_textproc.py
pyproject.toml           # [project.scripts] voicectl + voice-typing-daemon
```

---

## 3. Architecture data-flow (PRD §4)

```
PipeWire default mic → RealtimeSTT AudioToTextRecorder (constructed ONCE, models resident on GPU)
  ├─ VAD (webrtc + silero auto/onnx): SEGMENTS utterances only (post_speech_silence_duration=0.6s), NEVER ends session
  ├─ realtime model small.en → on_realtime_transcription_stabilized(str) → feedback.update_partial → state.json (tmux status reads it)
  └─ final model distil-large-v3 → on_final(text) → textproc.clean() → typing backend types text+" "
Control: unix socket $XDG_RUNTIME_DIR/voice-typing/control.sock (JSON lines): toggle/start/stop/status/quit
State:   $XDG_RUNTIME_DIR/voice-typing/state.json (atomic): {listening, phase, partial, last_final, ts}
```

---

## 4. Key corrected decisions (from research briefs — authoritatively verified)

1. **cuDNN 9 (not unpinned):** `nvidia-cudnn-cu12==9.*` (faster-whisper requires CUDA 12 + cuDNN 9). PRD left it unpinned.
2. **LD_LIBRARY_PATH via launcher wrapper** (`launch_daemon.sh`), NOT os.execv in-process. systemd ExecStart → wrapper. Must be set BEFORE python starts.
3. **`silero_backend="auto"` (default)** replaces PRD's legacy `silero_use_onnx=True` — already avoids torch-hub download. Drop the legacy kwarg.
4. **`compute_type="float16"` + `device="cuda"`** ARE valid kwargs — use directly.
5. **`ensure_sentence_starting_uppercase=False`, `ensure_sentence_ends_with_period=False`** — textproc owns cleanup; disable RealtimeSTT's built-in post-proc to avoid double-processing.
6. **Toggle-off = `set_microphone(False)` + `abort()` + in-callback gate** — models stay resident, instant toggle-on. `shutdown()` only on quit.
7. **`if __name__ == "__main__":` guard REQUIRED** in daemon.py (RealtimeSTT multiprocessing).
8. **Model repo IDs for prefetch:** `Systran/faster-distil-whisper-large-v3`, `Systran/faster-whisper-small.en`, `Systran/faster-whisper-tiny.en` (CPU fallback), `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (substitute final — different owner).
9. **torch CUDA is optional** (only Silero VAD, runs fine on CPU). ctranslate2 CUDA is the must-have. Don't block install on torch CUDA.
10. **No system ffmpeg needed** for whisper (PyAV bundles it); sox/espeak-ng still needed for test assets.

---

## 5. Phase / scope summary (drives the breakdown)

- **Phase 1 (MVP):** project bootstrap (uv, deps, CUDA bootstrap) → config → textproc → typing backends → feedback → daemon (recorder + control socket + listen-forever + toggle) → voicectl → install.sh + systemd → test assets → offline + unit + E2E + idle + GPU tests → README.
- **Phase 2:** Hyprland keybinding (`hypr-binds.conf`, print source instruction).
- **Final:** changeset-level documentation sync (README + overview).

All of Phase 1 + Phase 2 are "implement in the same run" per PRD §4.10/§7.

See `research_realtimestt_api.md` and `research_faster_whisper_cuda.md` for full API/deps detail.
