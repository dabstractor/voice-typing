# PRD: Fully-Local Voice Typing for Linux Terminal (tmux) — "voice-typing"

**Status:** Approved for implementation. No further user input will be given — this document is the complete spec. Where it says MUST, do it; where it says SHOULD, do it unless it demonstrably fails on this machine; where a decision is left open, the default stated here is the decision.

---

## 1. Problem statement (user's own framing)

The user wants to dictate text into their tmux terminal (and generally, any focused window) with a fully-local speech-to-text system. Previous attempt (WhisperX-based) failed in two specific ways that this project MUST fix:

1. **It stopped listening as soon as it thought the user was done talking.** A short pause in speech ended the session and the next few words were lost. → In this system, silence/VAD may only be used to *segment utterances*, never to *end the listening session*. The session ends only on explicit stop/toggle — and an explicit stop first lets the final model finish the in-flight utterance (drain) before disarming, so pressing the hotkey mid-sentence does NOT drop the words already spoken (§4.2 #2).
2. **No feedback while speaking.** The user couldn't tell whether recognition was on track. → This system MUST surface live partial transcriptions (~phone-dictation feel) while only committing finalized text to the target window.

Additional requirements:
- 100% local. No network calls at runtime (model downloads at install time are fine).
- Lag/stutter/buffering reduced to imperceptible levels: partials updating every ~200 ms; finalized text landing well under ~1.5 s after end of utterance.
- Primary consumer is a tmux terminal, but typing should work into any focused Wayland window.

Decisions already made with the user (do not revisit):
- **Activation:** toggle (start/stop via a control command; hotkey binding is Phase 2). Never auto-stops on silence.
- **Feedback:** live partials go to a status display (state file + `hyprctl notify`; tmux status integration provided). Only finalized text is typed. Do NOT backspace-correct inside the target window.
- **Output scope:** type into whatever window has focus (uinput/virtual-keyboard), with an alternative explicit `tmux send-keys` backend.
- **GPU:** models load **lazily on first arm** (`voicectl toggle`/`start`), NOT at daemon boot. A boot where voice typing is never armed consumes ~0 VRAM; after the first arm the models stay resident so re-arms are instant — until 30 min of disarmed idle, when they unload to reclaim VRAM (§4.2bis Idle unload); so the load cost is paid once per ~30 min of actual use, not once per boot. Trade-off accepted: the first arm each session blocks ~1–3 s while faster-whisper loads `distil-large-v3` + `small.en` into VRAM. Rationale: the daemon autostarts on every login but is used rarely — loading at boot parked ~2.8 GB on the GPU 24/7 for nothing. Full lifecycle in §4.2bis.

---

## 2. Verified machine facts (already checked on this exact machine — do not re-derive, but trust these over stale docs)

| Fact | Value |
|---|---|
| OS | Arch Linux, kernel 7.0.12-arch1-1 |
| CPU / RAM | i9-12900K (24 threads) / 62 GiB |
| GPU | NVIDIA RTX 3080 Ti, 12 GiB VRAM, driver 610.43.02, CUDA UMD 13.3; `cuda 13.3.0-1` pacman package installed; **no system cuDNN** (use pip `nvidia-cudnn-cu12`/`nvidia-cublas-cu12` wheels — driver is backward-compatible with cu12 builds) |
| Display | Wayland, **Hyprland** (via uwsm/SDDM), XWayland present (`DISPLAY=:1`) |
| Audio | PipeWire 1.6.6 (PulseAudio compat via pipewire-pulse). Default source: `alsa_input.usb-Sonix_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-02.mono-fallback` ("Webcam Vitade AF Mono", s16le 1ch 48 kHz). Second source: onboard `alsa_input.pci-0000_00_1f.3.analog-stereo`. The webcam mic is the only real mic — it is the accuracy ceiling; do not fight it, just use the default source. |
| Typing tools | `ydotool` 1.x installed, **ydotoold already running as an enabled user systemd service** (`systemctl --user status ydotool` → active). `/dev/uinput` is `crw-rw-rw-`, user is in `input` group. `wtype` and `xdotool` also installed. |
| Notifications | **No notification daemon running** (no dunst/mako/swaync), no waybar/eww. Hyprland's built-in `hyprctl notify` works. |
| Shell/tooling | zsh; **`python3` is aliased to `uv run` and `pip` is aliased in the interactive shell** — in scripts and in Bash tool calls always use explicit paths: `uv` at `/home/dustin/.local/bin/uv`, or `.venv/bin/python`. `tmux` is aliased through a zsh plugin (`_zsh_tmux_plugin_run`) — call `/usr/bin/tmux` explicitly in scripts. `cargo`, `go`, `ffmpeg`, `sox`, `espeak-ng`, `pw-cat`, `pw-loopback`, `jq` all present. |
| Project dir | `/home/dustin/projects/voice-typing` — empty git repo (only `.git`), branch `main`, clean. |
| Preinstalled related software | `epicenter-whispering-bin` (Whispering GUI app — ruled out: transcribes only after stop, clipboard-paste insertion, XWayland-only, its voice-activated mode has the exact auto-stop-on-pause flaw we're escaping. Leave it installed; ignore it.) `python-openai-whisper` pacman package (ignore). `vosk-api 0.3.50` in repos. |
| Possibly missing | `portaudio` may not be installed system-wide (needed by PyAudio). Check `pacman -Q portaudio`; if missing install it (`sudo pacman -S --noconfirm portaudio`). If sudo is unavailable non-interactively, ask the user to run it via `! sudo pacman -S portaudio`. |

---

## 3. Research summary and engine decision (completed July 6, 2026 — a light verification pass is fine, a full re-research is not needed)

A full survey of the 2026 ecosystem was done (RealtimeSTT, nerd-dictation, whisper.cpp stream, sherpa-onnx zipformer, NVIDIA Parakeet TDT, Handy, Whispering, Moonshine Streaming, Voxtral Realtime, Kyutai STT, hyprwhspr, shuvoice, and ~80 AUR packages). Conclusions:

- **Chosen: RealtimeSTT (github.com/KoljaB/RealtimeSTT)** — actively maintained (v1.0.2, May 2026, ~10k stars). It is the only maintained option satisfying all four hard requirements on this hardware: fully local, CUDA-fast via faster-whisper/CTranslate2, live partials every ~200 ms via a small "realtime" model (`on_realtime_transcription_update`/`on_realtime_transcription_stabilized` callbacks), and a listen-forever loop where `post_speech_silence_duration` only finalizes the current sentence — `while running: recorder.text(cb)` keeps the mic open indefinitely.
- Rejected alternatives, for the record: **Parakeet TDT** is confirmed not streamable (sherpa-onnx issue #2918) — superb final-pass model but no live partials. **Handy / hyprwhspr / Whispering** transcribe only after stopping (no partials). **nerd-dictation (Vosk)** streams beautifully but accuracy is clearly below Whisper-tier, no casing/punctuation. **whisper.cpp stream** has known boundary repetition/hallucination issues (issue #1702). **sherpa-onnx zipformer** is lowest-latency (~40–160 ms) but mid accuracy, no punctuation. **Moonshine Streaming / Voxtral Realtime 4B** are the future (accurate AND truly streaming) but have no dictation tooling yet — listed under Future Work.
- Fallback if RealtimeSTT proves unusable on this machine (e.g., unresolvable dependency breakage): **hyprwhspr** (AUR, updated July 2026, Hyprland-first, CUDA whisper.cpp or Parakeet V3, ydotool typing, long-form mode that tolerates pauses) — it sacrifices live partials but meets everything else with near-zero code. Only fall back after a genuine debugging effort.

**Model configuration decision:** realtime/partials model `small.en`, final model `distil-large-v3` (both CTranslate2/faster-whisper, both on CUDA, two separate model instances to avoid contention). If `distil-large-v3` downloads or runs poorly, `large-v3-turbo` is the approved substitute. VRAM budget ≈ 1.5–3 GB total in float16 — fine on 12 GB.

---

## 4. Architecture

```
                       ┌────────────────────────────────────────────┐
                       │  voice-typing daemon (Python, uv project)  │
 PipeWire default mic ─►  RealtimeSTT AudioToTextRecorder           │
                       │   ├─ VAD (webrtc+silero): segments only    │
                       │   ├─ realtime model small.en ──► partials ─┼──► state file (JSON) ──► tmux status / anything
                       │   │                                        ├──► hyprctl notify (replaceable one-liner)
                       │   └─ final model distil-large-v3 ─► final ─┼──► typing backend:
                       │                                            │      wtype (default) | ydotool | tmux send-keys
                       │  control: unix socket (JSON lines)         │
                       └────────────────▲───────────────────────────┘
                                        │
                          voicectl CLI (toggle/start/stop/status/quit)
```

### 4.1 Repository layout

```
/home/dustin/projects/voice-typing/
├── PRD.md                      # this file
├── README.md                   # usage doc (write last, keep short)
├── pyproject.toml              # uv-managed, python >=3.12,<3.13
├── uv.lock
├── voice_typing/
│   ├── __init__.py
│   ├── daemon.py               # main loop, recorder wiring, socket server
│   ├── config.py               # dataclass + TOML loader (see §4.5)
│   ├── typing_backends.py      # wtype / ydotool / tmux implementations
│   ├── feedback.py             # state file writer + hyprctl notify
│   ├── textproc.py             # normalization + hallucination filter
│   └── ctl.py                  # voicectl client CLI
├── config.toml                 # default config, self-documenting comments
├── systemd/voice-typing.service# user service (installed by install.sh)
├── install.sh                  # idempotent: uv sync, model prefetch, service install
├── tests/
│   ├── make_test_audio.sh      # espeak-ng → WAVs incl. pause-laden ones
│   ├── test_feed_audio.py      # offline pipeline test via feed_audio (no mic)
│   ├── e2e_virtual_mic.sh      # PipeWire null-sink + pw-cat E2E, asserts tmux pane content
│   └── test_textproc.py        # pure-python unit tests
└── .gitignore                  # .venv, __pycache__, models/, *.wav under tests/out/
```

### 4.2 The daemon (`daemon.py`)

Single process, three concerns:

1. **Recorder loop (main thread).** The `AudioToTextRecorder` is constructed **lazily on first arm** (§4.2bis), not at daemon boot; until then `recorder is None` and the loop has nothing to transcribe.
   ```python
   recorder = None                      # built on first arm — see §4.2bis (lazy load)
   while not shutdown_requested:
       if recorder is None:
           time.sleep(0.05); continue   # no models loaded yet → idle, ~0 VRAM
       if listening.is_set():
           recorder.text(on_final)      # blocks until one utterance finalizes → on_final types it → returns; if a stop was requested mid-utterance the loop drains here (lets this final land, then disarms) instead of re-listening (#2)
       else:
           time.sleep(0.05)
   if recorder is not None:
       recorder.shutdown()
   ```
   `on_final(text)` → `textproc.clean()` → if non-empty: typing backend types `text + " "`; feedback shows the final; log with timestamps.
   CRITICAL: the loop never exits on silence. `recorder.text()` returning is *normal segmentation*, not session end. Verify RealtimeSTT v1.x API against its README before coding — method names above are from v1.0.x.

2. **Listening gate.** A `threading.Event` (`listening`). Toggle/start/stop flips it. **Stop is graceful (drain):** an explicit stop/toggle-off does NOT abort an in-flight utterance — that would kill the final model mid-transcription and drop its text. If an utterance is in flight (speech occurred since the last final and the loop is blocked in `recorder.text()`), the stop sets a drain flag and lets `text()` return the *natural* final (the final model finishes → `on_final` types the real text), after which the loop disarms (mic off, listen gate cleared). If nothing is in flight (idle, or the last utterance already finalized), it disarms immediately + aborts — responsive when there's nothing to wait for. A bounded drain watchdog (a few seconds) aborts the rare case where no final ever fires, so a stop can never hang. `on_final` is gated on the listen flag so any final arriving *after* disarm is dropped (an utterance may complete right around a stop). Prefer constructing the recorder once (on first arm, per §4.2bis) and keeping it resident afterward = instant re-toggle. RealtimeSTT's `set_microphone(False)`/`use_microphone` toggling (or `abort()`) breaks a blocked `text()` on the immediate/timeout paths; the drain path deliberately uses neither until the final lands.

3. **Control socket (background thread).** `SOCK_STREAM` unix socket at `$XDG_RUNTIME_DIR/voice-typing/control.sock` (mkdir 0700). Protocol: one JSON object per line in, one per line out.
   - `{"cmd":"toggle"}` → `{"ok":true,"listening":true}`
   - `{"cmd":"start"}` / `{"cmd":"stop"}` / `{"cmd":"status"}` → `{"ok":true,"listening":...,"partial":"...","uptime_s":...,"mode":"normal"|"lite"}`
   - `{"cmd":"toggle-lite"}` / `{"cmd":"start-lite"}` → arm in lite mode (§4.2ter); same payload with `mode` reflecting the requested mode.
   - `{"cmd":"quit"}` → clean shutdown.
   Unknown cmd → `{"ok":false,"error":"..."}`. Remove stale socket file on startup.

Partial callbacks: wire `on_realtime_transcription_stabilized` (preferred; falls back to `on_realtime_transcription_update` if stabilized proves too laggy) → `feedback.update_partial(text)`. Also wire `on_recording_start`/`on_vad_detect_start` etc. to feedback state transitions (`idle`/`listening`/`speaking`) if available.

Logging: python `logging` to stderr (journald picks it up under systemd) at INFO; DEBUG via config. Log per-utterance: t_speech_end (when VAD closed), t_final_ready, t_typed, and the text. These timestamps are what the latency test reads.

### 4.2bis Model lifecycle — lazy load on first arm

Models MUST NOT load at daemon boot. The daemon starts with no recorder, no CUDA context, and ~0 VRAM. Construction of the `AudioToTextRecorder` — which loads `small.en` + `distil-large-v3` onto the GPU (§4.4 kwargs; ~1–3 s, ~1.5–3 GB VRAM in float16) — is deferred to the **first** `start`/`toggle` that arms the mic. After that first arm the recorder stays resident so the *second* and later arms are instant. It is torn down on `quit` / daemon shutdown, AND after `auto_unload_idle_seconds` (default 30 min) of sitting disarmed (see **Idle unload** below) — so the load cost is paid once per ~30 min of *actual use*, not once per boot. The goal: stop taxing the GPU both on boots where the feature is never used AND after a one-off use.

Lifecycle states (surfaced via `voicectl status` and the state file, §4.6/§4.8):
- `unloaded` — daemon up, no recorder, ~0 VRAM. This is the boot state.
- `loading` — first arm in progress; constructing recorder + loading models. The arm command blocks here; `voicectl` prints a `loading models…` hint.
- `loaded` / not listening — recorder resident, mic disarmed. Instant arm from here (in the SAME mode it was loaded — switching to the other mode reloads, §4.2ter). After `auto_unload_idle_seconds` in this state with no arm, the watchdog tears the recorder down → back to `unloaded` (see **Idle unload**).
- `loaded` / listening — armed, transcribing.

Concurrency & failure rules:
- A second arm while `loading` MUST NOT start a second load — it waits on the in-flight one (the load is single-flight under a lock).
- If the load fails (CUDA init error, missing model, cuDNN load failure), the daemon returns to `unloaded`, the arm command returns `{"ok":false,"error":"..."}`, and `status` reports the error + the CPU-fallback hint (§4.4). It MUST NOT leave a half-constructed recorder behind.
- The control-socket handlers for `start`/`toggle` (§4.2 #3) acquire/await the single-flight load, then proceed to the existing arm path. `status` reports `models_loaded: bool` so callers/UI can tell `loading` from `armed`.
- The idle auto-stop (§4.5) disarms the mic but does NOT itself unload — it hands off to the slower idle-unload timer (below), which is what eventually frees VRAM.
- Teardown (idle-unload and `quit`) runs under the SAME single-flight lock as load, so an arm that races an in-flight teardown waits for it, then loads fresh — an arm can never see a half-torn-down recorder.

**Idle unload.** A background watchdog reclaims VRAM after a one-off use: when the recorder has sat in `loaded / not listening` for `asr.auto_unload_idle_seconds` (default `1800.0` = 30 min; `0` disables), it tears the recorder down, logs `voice-typing idle-unload: 1800.0s disarmed; unloading models`, transitions to `unloaded`, and frees the ~1.5–3 GB VRAM. The clock starts when the mic disarms (manual stop, toggle-off, or the §4.5 idle auto-stop) and resets on any arm; time spent listening does not count. The next arm then pays the ~1–3 s reload, same as a session's first arm. **Hard requirement — bounded teardown:** the `recorder.shutdown()` call invoked here MUST be non-blocking and complete in well under the arm-latency budget. It MUST NOT reproduce the ~90 s teardown hang currently seen on every `quit` (journal: `run() loop exiting` → 90 s → systemd `SIGKILL` / `Failed with result 'timeout'`), because idle-unload would trigger that hang every 30 min AND block any re-arm that races it under the single-flight lock. If `recorder.shutdown()` cannot be made to complete promptly, guard it with a hard timeout plus force-cleanup of the recorder's worker threads / `transcript_process` so VRAM is actually released. Making teardown bounded is therefore a **prerequisite** for this feature (risk row, §8).

### 4.2ter Lite mode — small-model-only quick dictation

A second arming mode for short, speed-critical snippets (URLs, shell commands, short replies) where latency matters more than accuracy. Lite mode loads **only** the small realtime model and uses it as both the partials source AND the final-pass model — the large `distil-large-v3` never loads, never runs. Result: ~half the VRAM and markedly faster finals, at lower accuracy. It is entered via a **separate keybind / command**, never by the normal toggle.

**Configuration** (`[asr]`):
- `lite_model` (default `"small.en"`): the single model loaded in lite mode, used for BOTH realtime partials and final transcription. On CPU fallback it auto-downgrades via cuda_check like the normal models; the approved CPU lite substitute is `tiny.en`.

**Recorder construction (lite):** the recorder-host child builds the recorder with `model = lite_model`, `realtime_model_type = lite_model`, and `use_main_model_for_realtime = True`. Verified against RealtimeSTT v1.0.2: with `use_main_model_for_realtime=True` the separate realtime engine is NOT initialized (`_initialize_realtime_transcription_model` early-returns), so exactly ONE model (`lite_model`) is resident — the large final model is never constructed. All other kwargs (device, compute_type, language, VAD timing, silero) are identical to normal mode. `on_final` therefore yields `lite_model` finals — fast, lower-accuracy — over the SAME clean→type→record path as normal mode (§4.2).

**Mode is a spawn-time property of the recorder-host child; the daemon tracks `self._mode` (`"normal"` | `"lite"`).** The resident child is always in exactly one mode. Arming rules:
- Arm in mode X while resident child is mode X → instant arm (models already resident in the right mode).
- Arm in mode X while resident child is the OTHER mode → tear the child down and respawn it in mode X (~1–3 s reload, same bounded teardown as idle-unload, "Loading…" toast). I.e. **switching modes costs one reload.**
- Arm in mode X while unloaded → spawn in mode X (same as a session's first arm).
Idle-unload (§4.2bis) tears down whichever mode is resident; the next arm reloads in whatever mode that arm requests. The graceful drain (§4.2 #2) and idle auto-stop (§4.5) apply identically in lite mode.

**Commands / keybind:** `voicectl toggle-lite` / `voicectl start-lite` arm in lite mode (a clean toggle independent of the normal toggle, so each keybind is unambiguous); `voicectl toggle` / `start` arm in normal mode; `voicectl stop` disarms either. A second Hyprland bind (§4.10), e.g. `SUPER ALT, F` (fast), runs `voicectl toggle-lite`.

**State / status:** `state.json` gains `"mode": "normal" | "lite"` (written on every arm/disarm alongside the existing fields); `voicectl status` reports `mode:`. The tmux status line prefixes lite with `⚡` so the user can see at a glance which mode is armed. Start/stop toasts stay `"Recording"` / `"Recording Stopped"` in either mode (the keybind itself disambiguates); finals still toast `✔ <text>` per `notify_on_final`.

**Why a reload on switch is accepted:** it is the same ~1–3 s cost already paid on first-arm and after idle-unload, and a user picks a mode for a stretch of use rather than toggling per utterance. A no-reload alternative — committing the realtime partial from the resident two-model recorder — was REJECTED: it keeps the large model loaded, still spins its final pass per utterance, and so delivers neither the VRAM nor the latency benefit that motivates lite mode.

### 4.3 Typing backends (`typing_backends.py`)

Interface: `type_text(text: str) -> None`. Selected by config `output.backend`, default **`wtype`**.

- **wtype** (default): `subprocess.run(["wtype", "--", text])`. Uses Wayland `virtual-keyboard-v1` — supported by Hyprland, full Unicode, no layout issues. Types into the focused window (including terminals running tmux, so tmux "just works").
- **ydotool**: `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text])`. uinput-level, works even for XWayland apps; known weakness: non-ASCII/layout quirks. Keep as fallback; daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit), logging a warning.
- **tmux**: `subprocess.run(["/usr/bin/tmux", "send-keys", "-t", cfg.output.tmux_target, "-l", "--", text])`. `tmux_target` default `""` (= active pane of most recently attached client... actually empty target means current pane only inside tmux; use explicit default target from config, and document `voicectl` usage `--target`). Used by the automated E2E test; also the right backend for SSH/detached use.

Never send Enter/newline unless the utterance-final text itself demands it — it never should; strip trailing newlines in textproc.

### 4.4 RealtimeSTT recorder configuration (exact starting values — tune only if tests fail)

```python
AudioToTextRecorder(
    model="distil-large-v3",            # final pass; substitute "large-v3-turbo" if needed
    realtime_model_type="small.en",     # partials
    language="en",
    device="cuda", compute_type="float16", # if compute_type is a supported kwarg; verify against v1.x, else set gpu_device_index and rely on default
    enable_realtime_transcription=True,
    realtime_processing_pause=0.15,     # partials cadence ~150ms
    use_main_model_for_realtime=False,  # two models — avoid contention
    post_speech_silence_duration=0.6,   # finalize sentence after 0.6s pause (segmentation ONLY)
    min_length_of_recording=0.3,
    min_gap_between_recordings=0.0,     # resume listening immediately
    silero_sensitivity=0.4,
    webrtc_sensitivity=3,
    silero_use_onnx=True,               # avoids torch-hub download at runtime if supported
    spinner=False,
    use_microphone=True,                # False + feed_audio() in tests
    # input_device_index: leave unset → PipeWire default source
    on_realtime_transcription_stabilized=...,  # → feedback
)
```
Notes:
- Verify each kwarg name against the installed RealtimeSTT version's `audio_recorder.py` signature; drop unknown kwargs rather than crash.
- First construction downloads models to `~/.cache/huggingface`. `install.sh` MUST prefetch (construct recorder once, or `huggingface_hub.snapshot_download` of `Systran/faster-distil-whisper-large-v3` and `Systran/faster-whisper-small.en`) so the first arm never does a network download. ("Instant" applies to arms after the first in a session; the first arm still pays the ~1–3 s load-from-cache-into-VRAM cost per §4.2bis.)
- **cuDNN/cuBLAS:** ship `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` as deps and, in `daemon.py` before importing anything CUDA, prepend their lib dirs to the process's dynamic loader path — standard trick:
  ```python
  import os, pathlib, nvidia.cublas.lib, nvidia.cudnn.lib
  libs = os.pathsep.join(str(pathlib.Path(m.__file__).parent) for m in (nvidia.cublas.lib, nvidia.cudnn.lib))
  os.environ["LD_LIBRARY_PATH"] = libs + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
  ```
  must happen via os.execv re-exec or in a launcher wrapper, because LD_LIBRARY_PATH is read at process start — simplest robust approach: the systemd unit / launcher script sets `Environment=LD_LIBRARY_PATH=...` computed by `install.sh`, OR use `ctranslate2`'s ability to dlopen from `site-packages/nvidia/...` (recent faster-whisper handles this automatically — TEST IT; if `libcudnn_ops*.so` errors appear, apply the wrapper).
- If CUDA init fails entirely, daemon MUST log clearly and fall back to `device="cpu", compute_type="int8"` with `realtime_model_type="tiny.en"`, model `small.en` — degraded but functional — and say so in `status`.
- **Lite mode (§4.2ter):** the lite recorder is constructed with `model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True` (verified: only ONE model initializes; the large final model is never constructed).

### 4.5 Config (`config.toml`, parsed with stdlib `tomllib` into dataclasses)

```toml
[asr]
final_model = "distil-large-v3"
realtime_model = "small.en"
lite_model = "small.en"             # the SINGLE model loaded in lite mode (used for both partials + finals); §4.2ter
language = "en"
device = "cuda"                       # "cuda" | "cpu"
post_speech_silence_duration = 0.6
realtime_processing_pause = 0.15
auto_stop_idle_seconds = 30.0          # auto-disarm after this many seconds of no speech; 0 disables
auto_unload_idle_seconds = 1800.0     # after this many seconds disarmed (loaded, not listening), tear down models to free VRAM; 0 disables (§4.2bis Idle unload)

[output]
backend = "wtype"                     # "wtype" | "ydotool" | "tmux"
tmux_target = ""                      # used when backend = "tmux", e.g. "voicetest:0.0"
append_space = true

[feedback]
state_file = ""                       # empty → $XDG_RUNTIME_DIR/voice-typing/state.json
hypr_notify = true                    # master switch for hyprctl popups (start/final/stop)
notify_on_final = true                # also pop “✔ <text>” per final? (redundant: text is typed + in tmux)
notify_ms = 2500

[filter]
min_chars = 2
blocklist = ["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]  # case-insensitive exact matches — classic whisper silence hallucinations
```

Config file search order: `$XDG_CONFIG_HOME/voice-typing/config.toml`, then repo `config.toml`, then built-in defaults. `install.sh` copies the repo default to XDG if absent.

**Idle auto-stop** (`asr.auto_stop_idle_seconds`, default `30.0`): while listening, if no recognized speech (a realtime partial) arrives for this many seconds, the daemon auto-disarms immediately (no drain — by definition no utterance is in flight after this long silent) — it fires the `Recording Stopped` toast and writes a journal `INFO` line (`voice-typing auto-stop: 30.0s of no recognized speech; disarming`). Partials reset the clock while you talk, so it only triggers when you genuinely go silent (a forgotten hot-mic guard, NOT a mid-thought cut — that is governed by `post_speech_silence_duration`). A background `_idle_watchdog` thread ticks ~1s and re-checks the deadline under the listen lock so a late partial cancels the stop. `0` disables. Auto-stop disarms the mic but does NOT unload models by itself — it starts the slower idle-unload clock (below).

**Idle unload** (`asr.auto_unload_idle_seconds`, default `1800.0` = 30 min): a separate, slower watchdog that tears down the resident recorder to reclaim VRAM once the mic has been disarmed this long with no re-arm. It composes with idle auto-stop — the 30 s auto-stop disarms first, then the 30 min idle-unload frees the models. Full rule + the bounded-teardown requirement in §4.2bis (Idle unload). `0` disables (models then stay resident until `quit`).

### 4.6 Feedback (`feedback.py`)

- **State file** (atomic write via tempfile+rename) at `$XDG_RUNTIME_DIR/voice-typing/state.json`:
  ```json
  {"listening": true, "phase": "speaking", "models_loaded": true, "mode": "normal", "partial": "this is what i am say", "last_final": "Previous sentence.", "ts": 1783718400.123}
  ```
  `mode` is `"normal"` or `"lite"` (§4.2ter); it is written on every arm/disarm. Written on every partial update (throttle to ≥10 Hz max), phase change, final, and model-lifecycle transition. While models are not yet loaded (boot) or mid-load, `phase` is `unloaded` or `loading` and `models_loaded` is false (§4.2bis); once loaded, `phase` cycles `idle`/`listening`/`speaking`.
- **hyprctl notify**: `hyprctl notify -1 <notify_ms> "rgb(88c0d0)" "<msg>"` — fire-and-forget, swallow errors. Hyprland notifications are not replaceable by ID; to avoid stacking spam, only notify on: listening-start ("Recording"; the FIRST arm of a session is preceded by a one-shot "Loading…" toast while the models load — §4.2bis), each *final* ("✔ <text>" — gated by `notify_on_final`, since the text is already typed and shown in the tmux status line), listening-stop ("Recording Stopped" — for ANY disarm: manual stop, toggle-off, idle auto-stop, or the drain completing). Partials go to the state file only (that's what the tmux status consumes). `record_final` ALSO writes the finalized text back into the `partial` field so the tmux status line matches the screen (otherwise it would keep showing the last trailing realtime partial, which usually drops the final word or two).
- **tmux status integration** (document in README, and `install.sh` prints the snippet; do NOT edit the user's tmux.conf):
  ```tmux
  set -g status-interval 1
  set -g status-right '#(jq -r "if .listening then \"🎤 \" + (.partial // \"…\") else \"\" end" $XDG_RUNTIME_DIR/voice-typing/state.json 2>/dev/null | cut -c1-60)'
  ```
  (Provide a small `voice_typing/status.sh` helper script instead of inline jq, and reference that — cleaner quoting.)

### 4.7 Text processing (`textproc.py`)

`clean(text) -> str | None`:
1. `text.strip()`; strip trailing newlines; collapse internal whitespace runs to single spaces.
2. Reject if `len < filter.min_chars`.
3. Reject if lowercase-stripped-of-trailing-punctuation form is in blocklist.
4. Return cleaned text. Caller appends a single space when `append_space`.

Unit-test this module (pure python, fast).

### 4.8 `voicectl` (`ctl.py`)

`uv run voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>` and an installed console-script entry point (`[project.scripts] voicectl = "voice_typing.ctl:main"`, plus `voice-typing-daemon = "voice_typing.daemon:main"`). Connects to the socket, sends one JSON line, prints human-readable result (`listening: on`), exit code 0/1. `status` pretty-prints the state incl. partial, `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`), `models_loaded` (§4.2bis), and `mode` (`normal`/`lite`, §4.2ter). `toggle-lite`/`start-lite` arm in lite mode; `stop` disarms either. If daemon not running: clear message + exit 2.

### 4.9 systemd user service (`systemd/voice-typing.service`)

```ini
[Unit]
Description=Local voice typing daemon (RealtimeSTT)
After=pipewire.service ydotool.service
[Service]
ExecStart=/home/dustin/projects/voice-typing/.venv/bin/python -m voice_typing.daemon
Restart=on-failure
RestartSec=2
# Environment=LD_LIBRARY_PATH=...   ← install.sh fills this in if the cudnn dlopen test requires it
[Install]
WantedBy=default.target
```
`install.sh`: `uv sync`, prefetch models, run a 5-second CUDA smoke test, install+`daemon-reload`+enable+start the unit, print tmux snippet and usage. Idempotent. The daemon starts **not-listening** and **not-loaded** — it must never hot-mic on boot and loads no models until the first arm (§4.2bis, ~0 VRAM at idle); `voicectl start`/`toggle` arms it (the first arm each session also loads the models, ~1–3 s).

### 4.10 Phase 2 (implement after all tests pass — small, do it in the same run)

Hyprland keybinding: append to nothing — instead create `hypr-binds.conf` in the repo containing
```
bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle
bind = SUPER ALT, F, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle-lite
```
(`SUPER ALT, F` = "fast" → lite mode, §4.2ter.) Print an instruction to `source` it from `~/.config/hypr/hyprland.conf`. Do NOT modify the user's Hyprland config automatically. (Richer overlay UI is out of scope; state file + tmux status is the UI for now.)

---

## 5. Installation steps (for the implementing agent)

1. `cd /home/dustin/projects/voice-typing`
2. Ensure portaudio: `pacman -Q portaudio || sudo pacman -S --noconfirm portaudio` (PyAudio dep of RealtimeSTT).
3. `/home/dustin/.local/bin/uv init --bare --python 3.12` (already a git repo; keep name `voice-typing`).
4. `uv add realtimestt nvidia-cublas-cu12 nvidia-cudnn-cu12` — RealtimeSTT pulls torch, faster-whisper, pyaudio, webrtcvad, etc. If torch arrives CPU-only, add the CUDA wheel explicitly (`uv add torch --index https://download.pytorch.org/whl/cu126` or current cu12x index) — verify with `python -c "import torch; print(torch.cuda.is_available())"` → MUST print True. Torch is needed for Silero VAD, not the whisper inference itself (that's CTranslate2), so `torch.cuda` availability is nice-to-have; **`ctranslate2` CUDA is the must-have**: `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` → ≥1.
5. Write all source files per §4.
6. Prefetch models; run tests (§6); install service.
7. Commit everything to git on `main` with a sensible message. (User's git identity is already configured.)

Beware the shell aliases (§2): always invoke `/home/dustin/.local/bin/uv`, `.venv/bin/python`, `/usr/bin/tmux` with full paths in Bash calls.

---

## 6. Test plan — ALL must pass before declaring success

Build test assets with `tests/make_test_audio.sh` using espeak-ng (150 wpm, voice `en-us`), 16 kHz mono via sox/ffmpeg resample:

- `utt_simple.wav`: "The quick brown fox jumps over the lazy dog."
- `utt_pause.wav`: "I want to test whether this system" + **3.0 s of pure silence** + "keeps listening after a pause." (concatenate with sox; the silence must be inside one file)
- `utt_multi.wav`: three sentences separated by 1.5 s silences.
- `utt_punct.wav`: "Hello, world! Does punctuation, like commas, question marks? It should."

Note: espeak-ng is robotic; Whisper handles it but expect imperfect words. Assertions therefore use fuzzy matching: ≥80% token overlap (case/punct-insensitive) for espeak audio. Do not chase 100% on synthetic voices.

**T1 — Offline pipeline test (`test_feed_audio.py`), no mic, no typing:** construct recorder with `use_microphone=False`, feed WAV chunks via `recorder.feed_audio()` in real-time pacing, collect partial-callback events and finals.
Assert: (a) partials start arriving < 1.5 s after speech onset and update at least every 500 ms while speaking; (b) `utt_pause.wav` yields the words *after* the 3 s pause (the exact whisperx failure) — both halves present across the finalized texts; (c) finals for `utt_multi.wav` = 3 non-empty utterances; (d) fuzzy accuracy ≥80% per utterance; (e) latency: final callback ≤ 1.5 s after last speech sample fed.

**T2 — textproc unit tests:** blocklist filtering, whitespace, min-length, punctuation preserved.

**T3 — Full E2E with virtual mic and tmux (`e2e_virtual_mic.sh`):**
1. `pactl load-module module-null-sink sink_name=vt_test media.class=Audio/Sink` → play into it with `pw-cat --playback --target vt_test`, and point the daemon at the monitor: run daemon with config override `input device = monitor of vt_test` (RealtimeSTT `input_device_index` — resolve the PyAudio index of `vt_test.monitor`; a helper that lists PyAudio devices and greps is required). Alternatively `pactl set-default-source vt_test.monitor` for the test and restore the original default after (record it first!).
2. Start daemon with `backend="tmux"`, `tmux_target="voicetest:0.0"`; `/usr/bin/tmux new-session -d -s voicetest 'cat > /tmp/claude-1000/.../vt_out.txt'` — a pane running `cat` so typed keys land in a file (or just capture-pane; `cat >file` is more deterministic).
3. `voicectl start`; play `utt_pause.wav` then `utt_multi.wav`; wait; `voicectl stop`.
4. Assert file/pane contains fuzzy-matched text of ALL segments incl. post-pause half; assert state.json showed partials (poll it during playback and record snapshots); assert the in-flight utterance's final IS typed after `voicectl stop` (the graceful drain lets the final model finish — §4.2 #2), then assert nothing FURTHER is typed while playing one more WAV after the drain completes (toggle-off gates output once disarmed).
5. Cleanup: unload module, restore default source, kill tmux session. Use `trap` — the test MUST NOT leave the user's default source switched.

**T4 — Idle stability:** with daemon listening and silence (no playback) for 120 s, assert: no finals typed (hallucination guard works — this catches Whisper's silence-hallucination), no crash, CPU of daemon process < 25% of one core on average (`pidstat` or /proc sampling).

**T5 — Real-hardware smoke (cannot be automated — leave to user):** README's "First run" section tells the user exactly: `systemctl --user start voice-typing`, `voicectl toggle`, speak, watch tmux status, `voicectl toggle`. List expected behavior and the two tunables that matter (`post_speech_silence_duration`, `silero_sensitivity`).

**T6 — GPU lifecycle (lazy load):** (a) **idle, never armed:** right after daemon boot with no arm, `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` MUST NOT list the daemon PID at all (~0 VRAM — the lazy-load guarantee of §4.2bis). (b) **armed:** after `voicectl start`, the daemon PID appears with used_memory ~1–5 GB. (c) **disarmed (not quit):** after `voicectl stop`, the PID + memory REMAIN resident (instant re-arm). (d) **disarmed then idle ≥ `auto_unload_idle_seconds`:** the PID disappears from `nvidia-smi` again (~0 VRAM reclaimed); a later `voicectl start` reloads (~1–3 s) and the PID reappears.

Latency targets (log-derived, from T1/T3): partial cadence ≤ 300 ms while speaking; final-typed ≤ 1.5 s after end-of-utterance (0.6 s of that is the deliberate segmentation pause). If finals exceed target on GPU, first check that both models are actually on CUDA (log it), then try `large-v3-turbo`. The ~1–3 s model load on the first arm of a session (§4.2bis) is a one-time startup cost and does NOT count against utterance latency.

**T7 — Lite mode (`test_feed_audio.py` lite variant + `voicectl`):** construct the lite recorder (`model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True`) and feed `utt_simple.wav`: assert (a) exactly ONE model is resident (no `distil-large-v3` / large-model worker — grep the child log / check VRAM ≈ half of normal); (b) finals still arrive over the normal clean→type path and fuzzy-accuracy ≥70% (lower bar than normal mode's 80%, since `small.en` is the final model); (c) final-typed latency is materially lower than normal mode on the same utterance (small model is faster). Then over the socket: `toggle-lite` arms with `mode:"lite"` in the response; `toggle-lite` again disarms; a subsequent `toggle` reloads into `mode:"normal"` (one reload); `status` reports the current `mode`.

---

## 7. Acceptance criteria (definition of done)

1. T1–T4, T6 pass, demonstrated by actual command output (not claimed).
2. A pause mid-dictation of ≥3 s loses zero words and does not end the session (T1b, T3).
3. Live partials observable in `state.json` while audio plays (T3) and surfaced in the documented tmux status snippet.
4. Only finalized text reaches the target; nothing typed while toggled off.
5. Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use.
6. `voicectl toggle/start/stop/status/quit` all work; daemon runs as a systemd user service, starts un-armed (not listening) and **un-loaded** (~0 VRAM until first arm, §4.2bis), auto-restarts on failure.
7. Everything committed to git; README documents: install, hotkey snippet, tmux status snippet, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode.
8. No network access needed at runtime (models cached by install).
9. After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM, verified via `nvidia-smi`) and a later arm reloads it; the teardown is bounded (completes in seconds, no 90 s hang).
10. **Lite mode (§4.2ter):** `voicectl toggle-lite` arms in lite mode using ONLY `lite_model` (the large model never loads — verified ~half the VRAM of normal mode on `nvidia-smi`); `voicectl toggle` arms in normal mode; switching between them costs one bounded reload; `status` and `state.json` report `mode`; both modes honor the graceful drain (§4.2 #2).

## 8. Known risks & prescribed mitigations

| Risk | Mitigation |
|---|---|
| cuDNN "cannot load libcudnn_ops" at runtime | LD_LIBRARY_PATH wrapper per §4.4; set in systemd unit |
| PyAudio picks wrong device / 48 kHz mismatch | RealtimeSTT resamples internally; if it errors, set `input_device_index`; helper to list devices required anyway for T3 |
| Whisper hallucinates on silence ("Thank you.") | VAD gating + blocklist filter (§4.7) + T4 asserts it |
| wtype fails on some window (rare) | auto-fallback to ydotool (§4.3) |
| RealtimeSTT API drift vs this doc | Read the installed version's README/source first; kwargs here are v1.0.x-era, adjust names not intent |
| Toggle-off race types one last utterance | gate inside `on_final` too (§4.2) |
| espeak audio too robotic → flaky asserts | fuzzy ≥80% token overlap, not exact match |
| First-run model download stalls tests | install.sh prefetches before any test runs |
| First arm is slow (~1–3 s model load) | Accepted trade-off of lazy load (§4.2bis); `voicectl` prints `loading models…`; only the first arm after a load (or after an idle-unload) pays it |
| Model load fails on first arm (CUDA/cuDNN) | daemon returns to `unloaded`, arm returns `ok:false` with error + CPU-fallback hint; no half-built recorder left behind (§4.2bis) |
| `recorder.shutdown()` hangs ~90 s (seen on every `quit`: `SIGKILL` after systemd `TimeoutStopSec`) | **Prerequisite for idle-unload.** The teardown MUST be bounded/non-blocking (§4.2bis Idle unload): hard timeout + force-cleanup of the recorder's worker threads / `transcript_process` so VRAM is released and a racing arm isn't blocked for 90 s. Root-cause the wedge (likely the `transcript_process` join or the mic stream close) and fix it; until then idle-unload would hang every 30 min. |

## 9. Future work (explicitly out of scope now)

- Moonshine Streaming (medium, 107 ms, beats large-v3 WER) or Voxtral-Mini-4B-Realtime as a single-model true-streaming engine once tooling matures — engine layer is isolated in `daemon.py` to keep this swap cheap.
- Waybar/eww overlay UI; per-app profiles; voice commands ("new line", "scratch that"); punctuation-command mode.
- Better microphone (hardware) — webcam mic is the current accuracy ceiling.
