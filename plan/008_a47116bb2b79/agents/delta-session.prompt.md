# Generate Delta PRD from Changes

You are analyzing changes between two versions of a PRD to create a focused delta PRD.

## CRITICAL: PROPORTIONAL SIZING

**The delta PRD size MUST be proportional to the actual change size.**

- 1-line change → 1-2 paragraph PRD, 1 task with 1-2 subtasks
- Small tweak (few lines) → Short PRD, 1 phase, 1 milestone, 1-3 tasks
- Medium feature addition → Medium PRD, 1 phase, 1-2 milestones
- Large new feature → Full PRD structure

**If you produce a 9-phase PRD for a 3-line change, you have FAILED.**

Count the actual lines/words changed. Match your output complexity to input complexity.

## Previous PRD (Completed Session):
# PRD: Fully-Local Voice Typing for Linux/Wayland — "voice-typing"

**Status:** Approved for implementation. No further user input will be given — this document is the complete spec.

**Rev 2 (streaming dictation):** adds §4.2quater — phone-style typed partials revised in place, rolling context prompting, deterministic casing/punctuation guards, and Backspace-cancel. The small model (`small.en`) is the ONLY mode — the former big-model normal mode is REMOVED (user decision; §1). This revokes the Rev 1 decision that only finalized text is typed (§1).

Where it says MUST, do it; where it says SHOULD, do it unless it demonstrably fails on this machine; where a decision is left open, the default stated here is the decision.

---

## 1. Problem statement (user's own framing)

The user wants to dictate text into the focused window of their Wayland desktop with a fully-local speech-to-text system. Previous attempt (WhisperX-based) failed in two specific ways that this project MUST fix:

1. **It stopped listening as soon as it thought the user was done talking.** A short pause in speech ended the session and the next few words were lost. → In this system, silence/VAD may only be used to *segment utterances*, never to *end the listening session*. The session ends only on explicit stop/toggle — and an explicit stop first lets the final model finish the in-flight utterance (drain) before disarming, so pressing the hotkey mid-sentence does NOT drop the words already spoken (§4.2 #2).
2. **No feedback while speaking.** The user couldn't tell whether recognition was on track. → This system MUST surface live partial transcriptions (~phone-dictation feel) while only committing finalized text to the target window.

Additional requirements:
- 100% local. No network calls at runtime (model downloads at install time are fine).
- Lag/stutter/buffering reduced to imperceptible levels: partials updating every ~200 ms; finalized text landing well under ~1.5 s after end of utterance.
- Primary consumer is the focused Wayland window (Hyprland); typing works into any focused window.

Decisions already made with the user (do not revisit):
- **Activation:** toggle (start/stop via a control command; hotkey binding is Phase 2). Never auto-stops on silence.
- **Feedback (Rev 1 — SUPERSEDED on the small-model path by §4.2quater):** live partials go to a status display (state file + `hyprctl notify`). Only finalized text is typed. Do NOT backspace-correct inside the target window. *This was the experiment the user disliked: no visible output while talking, and silence-triggered appends felt like the recording kept stopping. Fully superseded — streaming replaces it everywhere.*
- **Streaming output (Rev 2, §4.2quater):** on the small-model path, stabilized partial text is TYPED into the focused window as it is spoken and revised in place (delete-and-retype only the changed tail). The mic never pauses for decoding; silence only triggers the commit/correction pass. One model (`small.en`) is the product.
- **Stranded text (Rev 2):** if a commit can never land (drain timeout, child death), the on-screen tail FREEZES as committed — typed text is never auto-deleted. The only deliberate deletion is an explicit cancel.
- **Cancel (Rev 2):** Backspace while a fragment is in flight cancels it — rewind that fragment's typed text (minus the one character the keystroke itself deleted), drop its buffered audio, keep listening. Any other user keypress freezes the tail (never type over the user's cursor).
- **One mode (user decision):** normal mode (`distil-large-v3`, two-model construction, mode switching) is REMOVED — one model, one keybind. The implementing revision collapses §4.2ter's lite machinery into the single path and deletes the normal-mode surface (`final_model` config, `toggle` vs `toggle-lite` distinction, T7's mode-switching, acceptance #10). No re-addition is planned.
- **Output scope:** type into whatever window has focus (uinput/virtual-keyboard), plus an inert `null` backend (types nothing) for headless tests.
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
| Shell/tooling | zsh; **`python3` is aliased to `uv run` and `pip` is aliased in the interactive shell** — in scripts and in Bash tool calls always use explicit paths: `uv` at `/home/dustin/.local/bin/uv`, or `.venv/bin/python`. `cargo`, `go`, `ffmpeg`, `sox`, `espeak-ng`, `pw-cat`, `pw-loopback`, `jq` all present. |
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
                       │   ├─ realtime model small.en ──► partials ─┼──► state file (JSON) ──► voicectl status / anything
                       │   │                                        ├──► hyprctl notify (replaceable one-liner)
                       │   └─ final model distil-large-v3 ─► final ─┼──► typing backend:
                       │                                            │      wtype (default) | ydotool | null
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
│   ├── daemon.py               # main loop, control socket, lifecycle orchestration
│   ├── recorder_host.py        # owns AudioToTextRecorder in a spawn child subprocess (VRAM reclamation, §4.2bis)
│   ├── cuda_check.py           # ctranslate2 CUDA probe + CPU-fallback resolution (§4.4)
│   ├── config.py               # dataclass + TOML loader (see §4.5)
│   ├── typing_backends.py      # wtype / ydotool / null implementations
│   ├── feedback.py             # state file writer + hyprctl notify
│   ├── textproc.py             # normalization + hallucination filter
│   ├── ctl.py                  # voicectl client CLI
│   ├── prefetch.py             # install-time model prefetch into the HF cache
│   ├── launch_daemon.sh        # ExecStart wrapper: LD_LIBRARY_PATH + HF_HUB_OFFLINE + WAYLAND_DISPLAY import
├── config.toml                 # default config, self-documenting comments
├── hypr-binds.conf             # Hyprland keybinds, sourced from hyprland.conf (§4.10)
├── systemd/voice-typing.service# user service (installed by install.sh)
├── install.sh                  # idempotent: uv sync, model prefetch, service install
├── tests/
│   ├── make_test_audio.sh      # espeak-ng → WAVs incl. pause-laden ones
│   ├── test_feed_audio.py      # offline pipeline test via feed_audio (no mic)
│   ├── e2e_virtual_mic.sh      # PipeWire null-sink + pw-cat E2E, asserts finals via state.json
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
  - `{"cmd":"cancel"}` → §4.2quater: rewind + drop the in-flight fragment, keep listening (`{"ok":true,"listening":true}`); no-op when nothing is in flight.
   - `{"cmd":"quit"}` → clean shutdown.
   Unknown cmd → `{"ok":false,"error":"..."}`. Remove stale socket file on startup.

Partial callbacks: wire `on_realtime_transcription_stabilized` (preferred; falls back to `on_realtime_transcription_update` if stabilized proves too laggy) → `feedback.update_partial(text)`. Also wire `on_recording_start`/`on_vad_detect_start` etc. to feedback state transitions (`idle`/`listening`/`speaking`) if available.

Logging: python `logging` to stderr (journald picks it up under systemd) at INFO; DEBUG via config. Log per-utterance: t_speech_end (when VAD closed), t_final_ready, t_typed, and the text. These timestamps are what the latency test reads.

### 4.2bis Model lifecycle — lazy load on first arm

Models MUST NOT load at daemon boot. The daemon starts with no recorder, no CUDA context, and ~0 VRAM. Construction of the `AudioToTextRecorder` — which loads `small.en` + `distil-large-v3` onto the GPU (§4.4 kwargs; ~1–3 s, ~1.5–3 GB VRAM in float16) — is deferred to the **first** `start`/`toggle` that arms the mic. After that first arm the recorder stays resident so the *second* and later arms are instant. It is torn down on `quit` / daemon shutdown, AND after `auto_unload_idle_seconds` (default 30 min) of sitting disarmed (see **Idle unload** below) — so the load cost is paid once per ~30 min of *actual use*, not once per boot. The goal: stop taxing the GPU both on boots where the feature is never used AND after a one-off use.

**Implementation note (recorder-host subprocess):** the `AudioToTextRecorder` is NOT constructed in the daemon process. On the first arm the daemon spawns a managed **child subprocess** (`voice_typing/recorder_host.py`, `RecorderHost`); that child owns the recorder and ALL CUDA contexts. Arm/disarm/text/abort/shutdown are proxied over multiprocessing queues, and partials/finals/VAD events stream back to a daemon reader thread. Rationale: RealtimeSTT's realtime model runs on an in-process thread whose CUDA primary context is unreleasable until the owning process exits, so idle-unload (below) and `quit` can only reach ~0 VRAM by **terminating the child's process group** (`os.setsid` in the child + `os.killpg` in the daemon). The daemon process is therefore *intended* to never import `RealtimeSTT`/`torch`/`ctranslate2` and never create a CUDA context — **caveat: `voicectl status` currently violates this; see BUGS.md VT-001.** RealtimeSTT's ~90 s `recorder.shutdown()` wedge is sidestepped entirely: teardown = `proc.join(5s)` then `SIGKILL` the group.

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

**Idle unload.** A background watchdog reclaims VRAM after a one-off use: when the recorder has sat in `loaded / not listening` for `asr.auto_unload_idle_seconds` (default `1800.0` = 30 min; `0` disables), it tears the recorder down, logs `voice-typing idle-unload: 1800.0s disarmed; unloading models`, transitions to `unloaded`, and frees the ~1.5–3 GB VRAM. The clock starts when the mic disarms (manual stop, toggle-off, or the §4.5 idle auto-stop) and resets on any arm; time spent listening does not count. The next arm then pays the ~1–3 s reload, same as a session's first arm. **Hard requirement — bounded teardown:** the `recorder.shutdown()` call invoked here MUST be non-blocking and complete in well under the arm-latency budget. It MUST NOT reproduce the ~90 s teardown hang currently seen on every `quit` (journal: `run() loop exiting` → 90 s → systemd `SIGKILL` / `Failed with result 'timeout'`), because idle-unload would trigger that hang every 30 min AND block any re-arm that races it under the single-flight lock. If `recorder.shutdown()` cannot be made to complete promptly, guard it with a hard timeout plus force-cleanup of the recorder's worker threads / `transcript_process` so VRAM is actually released. Making teardown bounded is therefore a **prerequisite** for this feature (risk row, §8). **(Resolved by the recorder-host subprocess model above: the daemon `killpg`s the child group after a 5 s join, so VRAM is force-released regardless of `recorder.shutdown()`'s behavior.)**

### 4.2ter Lite mode — small-model-only quick dictation

A second arming mode for short, speed-critical snippets (URLs, shell commands, short replies) where latency matters more than accuracy. Lite mode loads **only** the small realtime model and uses it as both the partials source AND the final-pass model — the large `distil-large-v3` never loads, never runs. Result: ~half the VRAM and markedly faster finals, at lower accuracy. It is entered via a **separate keybind / command**, never by the normal toggle.

**Configuration** (`[asr]`):
- `lite_model` (default `"small.en"`): the single model loaded in lite mode, used for BOTH realtime partials and final transcription. On CPU fallback it auto-downgrades via cuda_check like the normal models; the approved CPU lite substitute is `tiny.en`.

**Recorder construction (lite):** the recorder-host child builds the recorder with `model = lite_model`, `realtime_model_type = lite_model`, and `use_main_model_for_realtime = True`. Verified against RealtimeSTT v1.0.2: with `use_main_model_for_realtime=True` the separate realtime engine is NOT initialized (`_initialize_realtime_transcription_model` early-returns), so exactly ONE model (`lite_model`) is resident — the large final model is never constructed. All other kwargs (device, compute_type, language, silero) are identical to normal mode EXCEPT `post_speech_silence_duration`, which lite overrides with its own snugger threshold (`lite_post_speech_silence_duration`, §4.5) — see the latency note below for why this is load-bearing. `on_final` therefore yields `lite_model` finals — fast, lower-accuracy — over the SAME clean→type→record path as normal mode (§4.2).

**The silence gate, not the model, is the perceived-latency bottleneck (latency-log finding).** The per-utterance latency line clocks `speech_end_to_final_ms` from `on_vad_stop`, which fires only AFTER `post_speech_silence_duration` of trailing silence. On this GPU the small model's final pass is ~80 ms vs the large model's ~130 ms — a ~50 ms win that is SWAMPED by the silence wait, which is identical across modes unless lite overrides it. (Observed live: a 1.5 s `post_speech_silence_duration` made lite feel "no faster than the big model" even though the small model was in fact ~1.6× faster at transcription.) Therefore lite MUST use its own shorter `post_speech_silence_duration` (default `0.5` — the small model is fast and quips are short, so the big model's thinking-pause cushion isn't needed); that is what makes lite actually FEEL instant, cutting stop→text latency from ~1.6 s to ~0.6 s. Tunable: ~0.3 = razor-snappy (may split a brief pause into two finals), ~0.6 = safe. **Rev 2 (§4.2quater):** under streaming the endpointer no longer gates *visible* output — words are typed as they are spoken — it only delays the commit/correction pass, so the default rises to `0.8` (halving mid-thought cuts for +0.3 s commit latency). The "must be snug" rationale above applied to the Rev 1 output model, where finals were the only visible output; `0.5` remains the razor-snappy setting.

**Mode is a spawn-time property of the recorder-host child; the daemon tracks `self._mode` (`"normal"` | `"lite"`).** The resident child is always in exactly one mode. Arming rules:
- Arm in mode X while resident child is mode X → instant arm (models already resident in the right mode).
- Arm in mode X while resident child is the OTHER mode → tear the child down and respawn it in mode X (~1–3 s reload, same bounded teardown as idle-unload, "Loading…" toast). I.e. **switching modes costs one reload.**
- Arm in mode X while unloaded → spawn in mode X (same as a session's first arm).
Idle-unload (§4.2bis) tears down whichever mode is resident; the next arm reloads in whatever mode that arm requests. The graceful drain (§4.2 #2) and idle auto-stop (§4.5) apply identically in lite mode.

**Commands / keybind:** `voicectl toggle-lite` / `voicectl start-lite` arm in lite mode (a clean toggle independent of the normal toggle, so each keybind is unambiguous); `voicectl toggle` / `start` arm in normal mode; `voicectl stop` disarms either. Two Hyprland binds (§4.10): `Ctrl+Alt+Super+D` → `toggle` (big/normal model) and `Alt+Super+D` → `toggle-lite` (little/lite model).

**State / status:** `state.json` gains `"mode": "normal" | "lite"` (written on every arm/disarm alongside the existing fields); `voicectl status` reports `mode:` and prefixes lite with `⚡` so the user can see at a glance which mode is armed. Start/stop toasts stay `"Recording"` / `"Recording Stopped"` in either mode (the keybind itself disambiguates); finals still toast `✔ <text>` per `notify_on_final`.

**Why a reload on switch is accepted:** it is the same ~1–3 s cost already paid on first-arm and after idle-unload, and a user picks a mode for a stretch of use rather than toggling per utterance. A no-reload alternative — committing the realtime partial from the resident two-model recorder — was REJECTED: it keeps the large model loaded, still spins its final pass per utterance, and so delivers neither the VRAM nor the latency benefit that motivates lite mode.

### 4.2quater Streaming dictation — typed partials, in-place revision, Backspace-cancel (Rev 2; small-model/lite path only)

The Rev 1 output model — partials visible only in the status display, one append per silence-triggered final, and a snug endpointer existing largely to force frequent visible output — is REPLACED on this path by phone-style dictation: **words are typed into the focused window as they are spoken, revised in place, and the mic never pauses for decoding.** Scope: the small-model recorder — the ONLY mode (normal mode removed, §1).

**Output state machine (daemon process).** The daemon tracks two strings per armed session:
- `committed` — finalized text, ending at the last commit checkpoint;
- `tail` — everything typed since that checkpoint (the current utterance: tentative, revisable, no trailing space while tentative).

1. **Partial typing.** On each stabilized-partial event (existing IPC): diff against the currently typed `tail`. Extends it → type only the delta. Revises it → `press_backspace(len(revised_chars))` then type the corrected tail. Full rewinds are rate-limited (≥300 ms apart — code constant, not config) so a wobbling decode cannot flicker.
2. **Commit (silence trips).** The child's small.en re-decodes the complete utterance (the old "final", now a *correction pass*): if it differs from the typed `tail`, rewind + retype; append the trailing space (`output.append_space`); advance the checkpoint; refresh the rolling context prompt (below). Existing gates unchanged: `textproc.clean` (blocklist/min_chars) and the `listening` gate; a rejected final freezes the `tail` as-is.
3. **Drain unchanged** (§4.2 #2) — an explicit stop mid-speech still lets the correction pass land before disarming.
4. **Stranded tail → FREEZE, never delete** (user decision). If no commit can ever land (drain-watchdog abort, child death), the tail stays on screen exactly as last shown. The ONLY thing that deletes typed text is an explicit cancel (below).
5. **User-typing protection.** Any non-Backspace keypress observed while a `tail` is pending → immediately freeze the tail and stop revising that utterance entirely (suppress further partial typing until the next utterance boundary). The user took the cursor; never type over them.

**Typing backend additions.** `press_backspace(n)` MUST delete exactly n characters in an ordinary text field (wtype: repeat `-k Backspace`; ydotool: repeat the backspace keycode; batched so ~80 chars rewind in <150 ms). Revision correctness assumes the cursor sits at the end of our typed text and one keystroke deletes one character — the window where that can be false is narrowed to "the user has typed nothing since our last keystroke" by rule 5.

**Backspace-cancel.**
- **Listener:** a passive, read-only (never `EVIOCGRAB`) evdev listener thread in the daemon process over every keyboard `/dev/input/event*` node (auto-enumerate: EV_KEY devices that expose KEY_BACKSPACE; `[cancel].devices` overrides). The user is in the `input` group (§2) — no permission changes. `python-evdev` is the implementation dep.
- **Trigger:** KEY_BACKSPACE press while armed AND a `tail` is pending → cancel: rewind `max(len(tail)−1, 0)` characters (the physical keystroke itself already deleted one — compensate by subtraction, never by re-typing), drop the child's in-flight utterance (host abort discards its buffered audio), keep listening — just say the sentence again. **Idempotent:** further Backspaces with no pending tail are plain user edits and are never compensated.
- **Fallback:** `voicectl cancel` (control-socket cmd, §4.2 #3) runs the identical path — keybind-able when no keyboard node is readable (log once at arm; §4.10) and the automated-test seam (T8e).

**Rolling context prompt.** Every decode is conditioned on the committed text **back to the last sentence boundary** (last `.`/`!`/`?`), capped at ~200 tokens (Whisper's ~224-token prompt budget — code constant): partial decodes via `initial_prompt_realtime`, commit decodes via `initial_prompt`. Both kwargs exist in the installed RealtimeSTT 1.0.2 but are constructor-static — the child MUST make them dynamic (update between utterances); if that fails, degrade to context-free decoding and log (never crash). This is the primary fix for mid-paragraph fragments starting capitalized or acquiring spurious trailing periods: the decoder is told it is *continuing*, not starting.

**Deterministic guards (textproc, Rev 2).** Applied at typing time (pure, unit-tested):
- **Casing:** if `committed` does not end a sentence (no terminal `. ! ?`), lowercase the fragment's first word.
- **Period:** if the casing guard fired (we joined mid-sentence), strip one trailing `.` from the committed fragment — a decoder closing a sentence it was just told it was continuing is spurious by definition.
Rev 1 `clean()` rules (blocklist, min_chars, whitespace) are unchanged.

**Unchanged:** VAD segmentation (it now only triggers commits); feedback/state file/toasts (the `partial` field mirrors the live tail; `record_final` records the committed text); lazy load, idle unload, idle auto-stop, and the lite recorder construction (§4.2ter) including single-model `use_main_model_for_realtime=True`; `output.streaming=false` restores Rev 1 append-only behavior as a rollback hatch (§4.5).

### 4.3 Typing backends (`typing_backends.py`)

Interface: `type_text(text: str) -> None` (append committed text) plus `press_backspace(n: int) -> None` (Rev 2, §4.2quater — delete exactly n characters for in-place revision). Selected by config `output.backend`, default **`wtype`**.

- **wtype** (default): `subprocess.run(["wtype", "--", text])`. Uses Wayland `virtual-keyboard-v1` — supported by Hyprland, full Unicode, no layout issues. Types into the focused window.
- **ydotool**: `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text])`. uinput-level, works even for XWayland apps; known weakness: non-ASCII/layout quirks. Keep as fallback; daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit), logging a warning.
- **null**: types NOTHING. For the headless E2E test (which asserts finals via the state file instead of real keystrokes, so an automated run can never type into the developer's focused window) and for output-disabled setups. No subprocess is spawned.

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
    silero_backend="auto",              # item correction: modern control (prefers bundled CPU ONNX → avoids the torch-hub download). Supersedes the legacy silero_use_onnx=True.
    spinner=False,
    use_microphone=True,                # False + feed_audio() in tests
    ensure_sentence_starting_uppercase=False,  # item correction: textproc owns casing/punctuation cleanup
    ensure_sentence_ends_with_period=False,    # item correction (same reason)
    no_log_file=True,                   # suppress RealtimeSTT's unbounded realtimesst.log (sole log path = stderr → journald)
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
  must happen via os.execv re-exec or in a launcher wrapper, because LD_LIBRARY_PATH is read at process start. **Realized approach:** `voice_typing/launch_daemon.sh` (the ExecStart, §4.9) recomputes the cuBLAS/cuDNN lib dirs from the *live installed* `nvidia-*-cu12` wheels on every launch and exports `LD_LIBRARY_PATH` before exec'ing python — so no baked `Environment=LD_LIBRARY_PATH=` is used in the unit (it would go stale on `uv sync`). If `libcudnn_ops*.so` errors still appear, check the wrapper (`LD_DEBUG=libs launch_daemon.sh`).
- If CUDA init fails entirely, daemon MUST log clearly and fall back to `device="cpu", compute_type="int8"` with `realtime_model_type="tiny.en"`, model `small.en` — degraded but functional — and say so in `status`.
- **Lite mode (§4.2ter):** the lite recorder is constructed with `model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True` (verified: only ONE model initializes; the large final model is never constructed), AND a snugger `post_speech_silence_duration = lite_post_speech_silence_duration` — the silence gate, not the model, is the perceived-latency bottleneck, so lite MUST shorten it to actually feel faster (see §4.2ter).
- **Streaming path (Rev 2, §4.2quater):** the lite recorder additionally runs with a dynamic `initial_prompt` / `initial_prompt_realtime` (rolling committed context; both kwargs exist in installed v1.0.2 but are constructor-static — the child updates them between utterances) and `lite_post_speech_silence_duration = 0.8` default.

### 4.5 Config (`config.toml`, parsed with stdlib `tomllib` into dataclasses)

```toml
[asr]
final_model = "distil-large-v3"
realtime_model = "small.en"
lite_model = "small.en"             # the SINGLE model loaded in lite mode (used for both partials + finals); §4.2ter
language = "en"
device = "cuda"                       # "cuda" | "cpu"
post_speech_silence_duration = 0.6
lite_post_speech_silence_duration = 0.8  # Rev 2 §4.2quater: the endpointer only delays COMMIT under streaming (words are already typed live) — 0.8 halves mid-thought cuts for +0.3 s commit latency. 0.5 = razor-snappy; 1.0 = near-zero cuts.
context_prompt = true                  # Rev 2 §4.2quater: condition every decode on the rolling committed context (back to the last sentence boundary, ~200-token cap)
realtime_processing_pause = 0.15
auto_stop_idle_seconds = 30.0          # auto-disarm after this many seconds of no speech; 0 disables
auto_unload_idle_seconds = 1800.0     # after this many seconds disarmed (loaded, not listening), tear down models to free VRAM; 0 disables (§4.2bis Idle unload)

[output]
backend = "wtype"                     # "wtype" | "ydotool" | "null"
append_space = true
streaming = true                     # Rev 2 §4.2quater: type stabilized partials live + revise in place; false = Rev 1 append-only finals (rollback hatch)

[cancel]                              # Rev 2 §4.2quater: Backspace-cancel
on_backspace = true                  # evdev listener: Backspace while a fragment is in flight cancels it (rewind + drop audio, keep listening)
devices = []                         # empty → auto-enumerate keyboard /dev/input/event* nodes; else explicit path list override

[feedback]
state_file = ""                       # empty → $XDG_RUNTIME_DIR/voice-typing/state.json
hypr_notify = true                    # master switch for hyprctl popups (start/final/stop)
notify_on_final = true                # also pop “✔ <text>” per final? (redundant: text is typed into the focused window)
notify_ms = 2500

[filter]
min_chars = 2
blocklist = ["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]  # case-insensitive exact matches — classic whisper silence hallucinations


[log]   # daemon logging verbosity (stderr → journald under systemd)

level = "INFO"            # "INFO" = one structured per-utterance latency line + the startup device/models line; "DEBUG" = also the raw monotonic timestamps. Read live with `journalctl --user -u voice-typing -f`.
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
- **hyprctl notify**: `hyprctl notify -1 <notify_ms> "rgb(88c0d0)" "<msg>"` — fire-and-forget, swallow errors. Hyprland notifications are not replaceable by ID; to avoid stacking spam, only notify on: listening-start ("Recording"; the FIRST arm of a session is preceded by a one-shot "Loading…" toast while the models load — §4.2bis), each *final* ("✔ <text>" — gated by `notify_on_final`, since the text is already typed into the focused window), listening-stop ("Recording Stopped" — for ANY disarm: manual stop, toggle-off, idle auto-stop, or the drain completing). Partials go to the state file only. `record_final` ALSO writes the finalized text back into the `partial` field so status consumers see what was actually typed (otherwise `voicectl status` would keep showing the last trailing realtime partial, which usually drops the final word or two).

Status consumers (all read the state file above): `voicectl status`, the state-file fields themselves (`jq`-able for any custom UI), and the transient hyprctl toasts.

### 4.7 Text processing (`textproc.py`)

`clean(text) -> str | None`:
1. `text.strip()`; strip trailing newlines; collapse internal whitespace runs to single spaces.
2. Reject if `len < filter.min_chars`.
3. Reject if lowercase-stripped-of-trailing-punctuation form is in blocklist.
4. Return cleaned text. Caller appends a single space when `append_space`.

Unit-test this module (pure python, fast).

### 4.8 `voicectl` (`ctl.py`)

`uv run voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite|cancel>` and an installed console-script entry point (`[project.scripts] voicectl = "voice_typing.ctl:main"`, plus `voice-typing-daemon = "voice_typing.daemon:main"`). Connects to the socket, sends one JSON line, prints human-readable result (`listening: on`), exit code 0/1. `status` pretty-prints the state incl. partial, `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`), `models_loaded` (§4.2bis), and `mode` (`normal`/`lite`, §4.2ter). `toggle-lite`/`start-lite` arm in lite mode; `stop` disarms either. If daemon not running: clear message + exit 2.

### 4.9 systemd user service (`systemd/voice-typing.service`)

```ini
[Unit]
Description=Local voice typing daemon (RealtimeSTT)
# VT-004: order after + bind the lifecycle to graphical-session.target so the daemon starts AFTER
# the compositor exported WAYLAND_DISPLAY/DISPLAY (making the ExecStartPre import meaningful, not a
# cold-boot no-op). launch_daemon.sh still re-fetches the vars as belt-and-suspenders.
After=pipewire.service ydotool.service graphical-session.target
PartOf=graphical-session.target

[Service]
# wtype (default backend) is a Wayland client and needs WAYLAND_DISPLAY/DISPLAY; import them
# from the user manager (populated at graphical-session launch). Ordering after
# graphical-session.target (VT-004) makes this meaningful instead of a cold-boot no-op;
# launch_daemon.sh re-fetches the vars as the real workaround regardless.
ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY
# ExecStart is the LD_LIBRARY_PATH wrapper (voice_typing/launch_daemon.sh), NOT python directly.
# The wrapper recomputes the cuBLAS/cuDNN 9 lib dirs from the LIVE installed nvidia wheels on every
# launch, so this unit survives `uv sync` reinstalls without edits. Do NOT bake
# Environment=LD_LIBRARY_PATH= here (it goes stale). The wrapper also sets HF_HUB_OFFLINE=1.
# VT-003: __REPO__ is a PLACEHOLDER install.sh substitutes with the actual repo path when it
# copies the unit into ~/.config/systemd/user/ (portable across users / repo locations).
ExecStart=__REPO__/voice_typing/launch_daemon.sh
Restart=on-failure
RestartSec=2
# KillMode=mixed: deliver SIGTERM to the MAIN daemon only (let its single-flight host.stop()
# killpg its own recorder-host child), then SIGKILL the whole group only after TimeoutStopSec.
KillMode=mixed
TimeoutStopSec=15

[Install]
# VT-004: a Wayland client daemon starts/stops with the graphical session (not default.target,
# which raced the compositor on cold boot). install.sh removes a stale default.target.wants
# symlink from prior installs when it enables the unit.
WantedBy=graphical-session.target
```
`install.sh`: `uv sync`, prefetch models, run a 5-second CUDA smoke test, install+`daemon-reload`+enable+start the unit, print usage and the Hyprland keybind instruction. Idempotent. The daemon starts **not-listening** and **not-loaded** — it must never hot-mic on boot and loads no models until the first arm (§4.2bis, ~0 VRAM at idle); `voicectl start`/`toggle` arms it (the first arm each session also loads the models, ~1–3 s).

### 4.10 Phase 2 (implement after all tests pass — small, do it in the same run)

Hyprland keybinding: append to nothing — instead create `hypr-binds.conf` in the repo containing
```
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle
bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite
bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel   # fallback when the evdev Backspace listener can't open a keyboard (§4.2quater)
```
(`Ctrl+Alt+Super+D` = big/normal model; `Alt+Super+D` = little/lite model, §4.2ter.) Print an instruction to `source` it from `~/.config/hypr/hyprland.conf`. Do NOT modify the user's Hyprland config automatically. (Richer overlay UI is out of scope; state file + toasts are the UI for now.)

---

## 5. Installation steps (for the implementing agent)

1. `cd /home/dustin/projects/voice-typing`
2. Ensure portaudio: `pacman -Q portaudio || sudo pacman -S --noconfirm portaudio` (PyAudio dep of RealtimeSTT).
3. `/home/dustin/.local/bin/uv init --bare --python 3.12` (already a git repo; keep name `voice-typing`).
4. `uv add "realtimestt[faster-whisper,silero-vad]" nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" "huggingface_hub>=0.23" evdev` — the extras pull torch, faster-whisper, pyaudio, webrtcvad, and Silero; the `nvidia-*-cu12` wheels provide the cuBLAS/cuDNN 9 shared objects CTranslate2 loads; `huggingface_hub` is used by `prefetch.py`. If torch arrives CPU-only, add the CUDA wheel explicitly (`uv add torch --index https://download.pytorch.org/whl/cu126` or current cu12x index). Torch is needed for Silero VAD, not the whisper inference itself (that's CTranslate2), so `torch.cuda` availability is nice-to-have; **`ctranslate2` CUDA is the must-have**: `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` → ≥1.
5. Write all source files per §4.
6. Prefetch models; run tests (§6); install service.
7. Commit everything to git on `main` with a sensible message. (User's git identity is already configured.)

Beware the shell aliases (§2): always invoke `/home/dustin/.local/bin/uv`, `.venv/bin/python` with full paths in Bash calls.

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

**T3 — Full E2E with virtual mic (`e2e_virtual_mic.sh`):**
1. `pactl load-module module-null-sink sink_name=vt_test media.class=Audio/Sink` → play into it with `pw-cat --playback --target vt_test`, and point the daemon at the monitor: run daemon with config override `input device = monitor of vt_test` (RealtimeSTT `input_device_index` — resolve the PyAudio index of `vt_test.monitor`; a helper that lists PyAudio devices and greps is required). Alternatively `pactl set-default-source vt_test.monitor` for the test and restore the original default after (record it first!).
2. Start daemon with `backend="null"` (types nothing, spawns no subprocess — an automated run can never keystroke into the developer's focused window); finals are verified through the state file instead.
3. `voicectl start`; play `utt_pause.wav` then `utt_multi.wav`; wait; `voicectl stop`.
4. Poll `state.json` (`last_final`) and fuzzy-match ALL segments incl. post-pause half; assert state.json showed partials (poll it during playback and record snapshots); assert the in-flight utterance's final IS recorded after `voicectl stop` (the graceful drain lets the final model finish — §4.2 #2), then assert no FURTHER final appears while playing one more WAV after the drain completes (toggle-off gates output once disarmed).
5. Cleanup: unload module, restore default source. Use `trap` — the test MUST NOT leave the user's default source switched.

**T4 — Idle stability:** with daemon listening and silence (no playback) for 120 s, assert: no new final in `state.json` (hallucination guard works — this catches Whisper's silence-hallucination), no crash, CPU of daemon process < 25% of one core on average (`pidstat` or /proc sampling).

**T5 — Real-hardware smoke (cannot be automated — leave to user):** README's "First run" section tells the user exactly: `systemctl --user start voice-typing`, `voicectl toggle`, speak (watch the hyprctl toasts / `voicectl status`), `voicectl toggle`. List expected behavior and the two tunables that matter (`post_speech_silence_duration`, `silero_sensitivity`).

**T6 — GPU lifecycle (lazy load):** (a) **idle, never armed:** right after daemon boot with no arm, `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` MUST NOT list the daemon PID at all (~0 VRAM — the lazy-load guarantee of §4.2bis). (b) **armed:** after `voicectl start`, the daemon PID appears with used_memory ~1–5 GB. (c) **disarmed (not quit):** after `voicectl stop`, the PID + memory REMAIN resident (instant re-arm). (d) **disarmed then idle ≥ `auto_unload_idle_seconds`:** the PID disappears from `nvidia-smi` again (~0 VRAM reclaimed); a later `voicectl start` reloads (~1–3 s) and the PID reappears.

Latency targets (log-derived, from T1/T3): partial cadence ≤ 300 ms while speaking; final-typed ≤ 1.5 s after end-of-utterance (0.6 s of that is the deliberate segmentation pause). If finals exceed target on GPU, first check that both models are actually on CUDA (log it), then try `large-v3-turbo`. The ~1–3 s model load on the first arm of a session (§4.2bis) is a one-time startup cost and does NOT count against utterance latency.

**T7 — Lite mode (`test_feed_audio.py` lite variant + `voicectl`):** construct the lite recorder (`model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True`, `post_speech_silence_duration = lite_post_speech_silence_duration`) and feed `utt_simple.wav`: assert (a) exactly ONE model is resident (no `distil-large-v3` / large-model worker — grep the child log / check VRAM ≈ half of normal); (b) finals still arrive over the normal clean→type path and fuzzy-accuracy ≥70% (lower bar than normal mode's 80%, since `small.en` is the final model); (c) the lite kwargs carry the SHORTER `post_speech_silence_duration` (the silence gate — not the model — is the perceived bottleneck; without this lite feels no faster than normal — §4.2ter), and end-to-end stop→text latency is materially lower than normal mode on the same utterance. Then over the socket: `toggle-lite` arms with `mode:"lite"` in the response; `toggle-lite` again disarms; a subsequent `toggle` reloads into `mode:"normal"` (one reload); `status` reports the current `mode`.

**T8 — Streaming dictation (Rev 2 §4.2quater, `test_streaming.py`, no mic):** lite recorder child + a RecordingTypingBackend (records `type_text`/`press_backspace` calls; no real keystrokes). Feed WAVs via `feed_audio`.
Assert: (a) while speech streams, typing deltas arrive at least every 500 ms and only the delta when a partial extends the tail; (b) a differing commit rewinds exactly the tail length then types the final text (+ trailing space); (c) a single sentence split by a 3 s pause joins into ONE coherent commit — no mid-sentence capital, no spurious trailing period (context prompt + textproc guards); (d) the child's decodes carry `initial_prompt` = committed text back to the last sentence boundary, capped (assert via child log/kwargs); (e) `cancel` while a tail is pending → `press_backspace(len(tail)−1)`, the buffered audio is dropped (no commit for it later), listening stays on; a second cancel is a no-op; (f) a non-Backspace user key while a tail is pending → tail frozen, no further revision keystrokes for that utterance; (g) the stranded-tail path (forced drain-timeout) → text frozen on screen, not rewound. The evdev key-event parser is unit-tested separately with synthetic events (no real keyboard); real-Backspace behavior stays in the T5 manual smoke (add: press Backspace mid-fragment → the fragment disappears, dictation continues armed).

---

## 7. Acceptance criteria (definition of done)

1. T1–T4, T6 pass, demonstrated by actual command output (not claimed).
2. A pause mid-dictation of ≥3 s loses zero words and does not end the session (T1b, T3).
3. Live partials observable in `state.json` while audio plays (T3).
4. Only the daemon's typed output reaches the target — Rev 2: live partial text plus commits (§4.2quater); nothing typed while toggled off (the `listening` gates on partial and commit paths are unchanged).
5. Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use.
6. `voicectl toggle/start/stop/status/quit` all work; daemon runs as a systemd user service, starts un-armed (not listening) and **un-loaded** (~0 VRAM until first arm, §4.2bis), auto-restarts on failure.
7. Everything committed to git; README documents: install, hotkey snippet, feedback surfaces, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode.
8. No network access needed at runtime (models cached by install).
9. After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM, verified via `nvidia-smi`) and a later arm reloads it; the teardown is bounded (completes in seconds, no 90 s hang).
10. **Lite mode (§4.2ter):** `voicectl toggle-lite` arms in lite mode using ONLY `lite_model` (the large model never loads — verified ~half the VRAM of normal mode on `nvidia-smi`); `voicectl toggle` arms in normal mode; switching between them costs one bounded reload; `status` and `state.json` report `mode`; lite uses its own shorter `post_speech_silence_duration` (the silence gate is the perceived bottleneck — §4.2ter) so it is observably snappier end-to-end, not just faster at transcription; both modes honor the graceful drain (§4.2 #2).
11. **Streaming (§4.2quater):** while speaking, words are typed into the focused window continuously (≥1 update/500 ms, T8a); commits revise in place (T8b); a mid-paragraph fragment never starts with a capital nor ends with a spurious period (T8c); Backspace mid-fragment cancels it — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only behavior.
12. **Cancel fallback:** with evdev unavailable, `voicectl cancel` performs the same rewind over the socket (T8e) and the daemon logs the listener failure once at arm.

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
| Streaming revision corrupts text if the user moves the cursor mid-utterance | any non-Backspace keypress freezes the tail (§4.2quater rule 5); rewind assumes 1 char/keystroke with cursor at end of typed text — documented assumption, window narrowed by the freeze rule |
| `initial_prompt`/`initial_prompt_realtime` are constructor-static in RealtimeSTT 1.0.2 (verified) | child updates them between utterances (small local patch); on failure degrade to context-free decoding + log, never crash |
| Backspace semantics differ per app (terminals, editors) | cancel fires only while armed AND a tail is pending; idempotent; compensation is by subtraction; falls back to `voicectl cancel` keybind |
| Revision flicker (rewind/retype storms) | type deltas by default; full rewinds rate-limited (≥300 ms); no trailing space while tentative |
| evdev listener misses keyboards / permission loss | fail-safe: log once at arm, keybind (`voicectl cancel`) keeps working; `[cancel].devices` override for odd setups |

## 9. Future work (explicitly out of scope now)

- Moonshine Streaming (medium, 107 ms, beats large-v3 WER) or Voxtral-Mini-4B-Realtime as a single-model true-streaming engine once tooling matures — engine layer is isolated in `daemon.py` to keep this swap cheap.
- Waybar/eww overlay UI; per-app profiles; voice commands ("new line", "scratch that"); punctuation-command mode.
- Better microphone (hardware) — webcam mic is the current accuracy ceiling.

## Current PRD:
# PRD: Fully-Local Voice Typing for Linux/Wayland — "voice-typing"

**Status:** Implementation requirements, not a record of release acceptance. No further product interview is required.

**Rev 4 — bulk text delivery (§4.2sexies) is the normative specification for the new output path.** Paste is the policy: show each available recognition update as text at the insertion point; replace a changed, verified dictation range in one visible edit; emit no edit when unchanged. No simulated character typing or Backspace fallback. A caption, terminal byte receipt, or `state.json` update does not establish that words appeared in the user's field. **Real-field insertion, correction, and speech-to-screen latency are not yet verified.** The 2026-11 planning drafts were research input and have been deleted; §4.2sexies is the single source. **Route capability is RESOLVED (2026-11-22 `tools/im-lab/` spike; evidence in the R.2 table): input-method-v2 is the primary route, the pi chat-prompt milestone rides its documented extension seam, and no route-discovery work remains in scope.**

**Precedence:** For `output.delivery="bulk-text"`, §4.2sexies supersedes conflicting output, keyboard, fallback, logging, and acceptance instructions below, including §4.2quater, §4.3, T8, and §7 items 11–12. Earlier revisions govern the explicit legacy path; Rev 3 takes precedence there. Recorder lifecycle, installation safety, local processing, and unrelated requirements still apply.

**Rev 2 (streaming dictation):** adds §4.2quater — phone-style typed partials revised in place, rolling context prompting, deterministic casing/punctuation guards, and Backspace-cancel. The small model (`small.en`) is the ONLY mode — the former big-model normal mode is REMOVED (user decision; §1). This revokes the Rev 1 decision that only finalized text is typed (§1).

**Rev 3 (halt + accounting hardening, 2026-10 — supersedes conflicting statements below):** four user decisions after the October mass-deletion/wedge reports: (1) **any real user keypress while armed DISARMS dictation entirely** ("HALT") — the Rev 2 per-utterance freeze is demoted to opt-in legacy (`cancel.keypress_action = "freeze"`); modifier-only presses are not keypresses, and a 1.5 s grace after arming ignores the hotkey's own chord. (2) **Stop is IMMEDIATE by default** — disarm now, drop the racing final, never wait on the decoder ("all the way, no exceptions"); the Rev 2 graceful drain is opt-in (`asr.graceful_stop = true`). (3) **Rewind accounting is a hard invariant**: a rewind may never delete more characters than the engine typed since the checkpoint (clamped + journaled per rewind); dropped finals inside the cancel-suppression window reset the utterance boundary so the tail can never accumulate across utterances (the "backspaces way farther than it ever typed" bug). (3b) **Session-boundary audio purge**: the child's buffered audio MUST be cleared at EVERY disarm AND at every arm — the stop's abort unblocks the decoder after the disarm clear, and whatever the aborted decode re-stashes (frames/last_frames) must not survive into the next session's first decode (the stale-replay "previous utterance types itself after re-arm" bug). (3c) **Continuation separator**: an interrupted session (immediate stop, keypress-disarm — the commit that types the inter-utterance space never ran) strands its tail mid-screen with no trailing space; the NEXT typed fragment MUST lead with exactly one space, typed lazily (only when dictation actually resumes — never left dangling), and that synthesized separator is invisible to prefix-diffing (decoder partials never contain it) while still being deleted by any rewind that covers it. Without this, every interrupted session fuses its continuation onto the stranded text (the "skipped spaces" bug). (3d) **Injector pacing**: synthesized keystrokes MUST be spaced (~12 ms/char) and every injector process spawn MUST be serialized behind a single lock with a minimum inter-spawn floor (~25 ms), on BOTH backends — the injector always exits 0 while the compositor's input path silently coalesces/drops sub-2 ms press/release bursts under sustained dictation (the "missing characters, worse the longer I use it" report; single-keystroke payloads like a lone space are dropped first, so separators MUST ride inside the next text payload, never as their own spawn). On this machine the primary backend is ydotool (persistent ydotoold uinput device — no per-spawn virtual-keyboard/keymap churn, which loses events the same way). (4) **Robustness invariants promoted to spec**: the child abort handler MUST be supervised (a dead one wedged every later stop/cancel into timeouts — the missing-`import time` crash); `voicectl` commands MUST be bounded by a socket timeout (default 10 s, `VOICECTL_TIMEOUT`); the evdev listener MUST survive device death (WARN + periodic re-enumeration); SUPER+ALT+Escape is a documented hard-kill panic bind. Streaming live partials remain the ONLY mode (reaffirmed).

Where it says MUST, do it; where it says SHOULD, do it unless it demonstrably fails on this machine; where a decision is left open, the default stated here is the decision.

---

## 1. Problem statement (user's own framing)

The user wants to dictate text into the focused window of their Wayland desktop with a fully-local speech-to-text system. Previous attempt (WhisperX-based) failed in two specific ways that this project MUST fix:

1. **It stopped listening as soon as it thought the user was done talking.** A short pause in speech ended the session and the next few words were lost. → In this system, silence/VAD may only be used to *segment utterances*, never to *end the listening session*. The session ends only on explicit stop/toggle — and an explicit stop first lets the final model finish the in-flight utterance (drain) before disarming, so pressing the hotkey mid-sentence does NOT drop the words already spoken (§4.2 #2).
2. **No feedback while speaking.** The user couldn't tell whether recognition was on track. → This system MUST surface live partial transcriptions (~phone-dictation feel) while only committing finalized text to the target window.

Additional requirements:
- 100% local. No network calls at runtime (model downloads at install time are fine).
- Lag/stutter/buffering reduced to imperceptible levels: partials updating every ~200 ms; finalized text landing well under ~1.5 s after end of utterance.
- Primary consumer is the focused Wayland window (Hyprland); typing works into any focused window.

Decisions already made with the user (do not revisit):
- **Activation:** toggle (start/stop via a control command; hotkey binding is Phase 2). Never auto-stops on silence.
- **Feedback (Rev 1 — SUPERSEDED on the small-model path by §4.2quater):** live partials go to a status display (state file + `hyprctl notify`). Only finalized text is typed. Do NOT backspace-correct inside the target window. *This was the experiment the user disliked: no visible output while talking, and silence-triggered appends felt like the recording kept stopping. Fully superseded — streaming replaces it everywhere.*
- **Streaming output (Rev 2, §4.2quater):** on the small-model path, stabilized partial text is TYPED into the focused window as it is spoken and revised in place (delete-and-retype only the changed tail). The mic never pauses for decoding; silence only triggers the commit/correction pass. One model (`small.en`) is the product.
- **Stranded text (Rev 2):** if a commit can never land (drain timeout, child death), the on-screen tail FREEZES as committed — typed text is never auto-deleted. The only deliberate deletion is an explicit cancel.
- **Cancel (Rev 2):** Backspace while a fragment is in flight cancels it — rewind that fragment's typed text (minus the one character the keystroke itself deleted), drop its buffered audio, keep listening. Any other user keypress DISARMS dictation entirely (Rev 3; was: freezes the tail).
- **One mode (user decision):** normal mode (`distil-large-v3`, two-model construction, mode switching) is REMOVED — one model, one keybind. The implementing revision collapses §4.2ter's lite machinery into the single path and deletes the normal-mode surface (`final_model` config, `toggle` vs `toggle-lite` distinction, T7's mode-switching, acceptance #10). No re-addition is planned.
- **Output scope:** type into whatever window has focus (uinput/virtual-keyboard), plus an inert `null` backend (types nothing) for headless tests.
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
| Shell/tooling | zsh; **`python3` is aliased to `uv run` and `pip` is aliased in the interactive shell** — in scripts and in Bash tool calls always use explicit paths: `uv` at `/home/dustin/.local/bin/uv`, or `.venv/bin/python`. `cargo`, `go`, `ffmpeg`, `sox`, `espeak-ng`, `pw-cat`, `pw-loopback`, `jq` all present. |
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
                       │   ├─ realtime model small.en ──► partials ─┼──► state file (JSON) ──► voicectl status / anything
                       │   │                                        ├──► hyprctl notify (replaceable one-liner)
                       │   └─ final model distil-large-v3 ─► final ─┼──► typing backend:
                       │                                            │      wtype (default) | ydotool | null
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
│   ├── daemon.py               # main loop, control socket, lifecycle orchestration
│   ├── recorder_host.py        # owns AudioToTextRecorder in a spawn child subprocess (VRAM reclamation, §4.2bis)
│   ├── cuda_check.py           # ctranslate2 CUDA probe + CPU-fallback resolution (§4.4)
│   ├── config.py               # dataclass + TOML loader (see §4.5)
│   ├── typing_backends.py      # wtype / ydotool / null implementations
│   ├── feedback.py             # state file writer + hyprctl notify
│   ├── textproc.py             # normalization + hallucination filter
│   ├── ctl.py                  # voicectl client CLI
│   ├── prefetch.py             # install-time model prefetch into the HF cache
│   ├── launch_daemon.sh        # ExecStart wrapper: LD_LIBRARY_PATH + HF_HUB_OFFLINE + WAYLAND_DISPLAY import
├── config.toml                 # default config, self-documenting comments
├── hypr-binds.conf             # Hyprland keybinds, sourced from hyprland.conf (§4.10)
├── systemd/voice-typing.service# user service (installed by install.sh)
├── install.sh                  # idempotent: uv sync, model prefetch, service install
├── tests/
│   ├── make_test_audio.sh      # espeak-ng → WAVs incl. pause-laden ones
│   ├── test_feed_audio.py      # offline pipeline test via feed_audio (no mic)
│   ├── e2e_virtual_mic.sh      # PipeWire null-sink + pw-cat E2E, asserts finals via state.json
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

2. **Listening gate.** A `threading.Event` (`listening`). Toggle/start/stop flips it. **Stop is IMMEDIATE by default (Rev 3):** an explicit stop/toggle-off disarms NOW — mic off, listen gate cleared, racing final dropped by the `on_final` gate, tail stays typed as-is; it never waits on the child's decoder ("all the way, no exceptions"). The Rev 2 graceful drain (let the in-flight `text()` return its natural final, bounded by a few-seconds watchdog, then disarm) is OPT-IN via `asr.graceful_stop = true`. Either way a stop can never hang, and any final arriving after disarm is dropped. Prefer constructing the recorder once (on first arm, per §4.2bis) and keeping it resident afterward = instant re-toggle.

3. **Control socket (background thread).** `SOCK_STREAM` unix socket at `$XDG_RUNTIME_DIR/voice-typing/control.sock` (mkdir 0700). Protocol: one JSON object per line in, one per line out.
   - `{"cmd":"toggle"}` → `{"ok":true,"listening":true}`
   - `{"cmd":"start"}` / `{"cmd":"stop"}` / `{"cmd":"status"}` → `{"ok":true,"listening":...,"partial":"...","uptime_s":...,"mode":"normal"|"lite"}`
   - `{"cmd":"toggle-lite"}` / `{"cmd":"start-lite"}` → arm in lite mode (§4.2ter); same payload with `mode` reflecting the requested mode.
  - `{"cmd":"cancel"}` → §4.2quater: rewind + drop the in-flight fragment, keep listening (`{"ok":true,"listening":true}`); no-op when nothing is in flight.
   - `{"cmd":"quit"}` → clean shutdown.
   Unknown cmd → `{"ok":false,"error":"..."}`. Remove stale socket file on startup.

Partial callbacks: wire `on_realtime_transcription_stabilized` (preferred; falls back to `on_realtime_transcription_update` if stabilized proves too laggy) → `feedback.update_partial(text)`. Also wire `on_recording_start`/`on_vad_detect_start` etc. to feedback state transitions (`idle`/`listening`/`speaking`) if available.

Logging: python `logging` to stderr (journald picks it up under systemd) at INFO; DEBUG via config. Log per-utterance: t_speech_end (when VAD closed), t_final_ready, t_typed, and the text. These timestamps are what the latency test reads.

### 4.2bis Model lifecycle — lazy load on first arm

Models MUST NOT load at daemon boot. The daemon starts with no recorder, no CUDA context, and ~0 VRAM. Construction of the `AudioToTextRecorder` — which loads `small.en` + `distil-large-v3` onto the GPU (§4.4 kwargs; ~1–3 s, ~1.5–3 GB VRAM in float16) — is deferred to the **first** `start`/`toggle` that arms the mic. After that first arm the recorder stays resident so the *second* and later arms are instant. It is torn down on `quit` / daemon shutdown, AND after `auto_unload_idle_seconds` (default 30 min) of sitting disarmed (see **Idle unload** below) — so the load cost is paid once per ~30 min of *actual use*, not once per boot. The goal: stop taxing the GPU both on boots where the feature is never used AND after a one-off use.

**Implementation note (recorder-host subprocess):** the `AudioToTextRecorder` is NOT constructed in the daemon process. On the first arm the daemon spawns a managed **child subprocess** (`voice_typing/recorder_host.py`, `RecorderHost`); that child owns the recorder and ALL CUDA contexts. Arm/disarm/text/abort/shutdown are proxied over multiprocessing queues, and partials/finals/VAD events stream back to a daemon reader thread. Rationale: RealtimeSTT's realtime model runs on an in-process thread whose CUDA primary context is unreleasable until the owning process exits, so idle-unload (below) and `quit` can only reach ~0 VRAM by **terminating the child's process group** (`os.setsid` in the child + `os.killpg` in the daemon). The daemon process is therefore *intended* to never import `RealtimeSTT`/`torch`/`ctranslate2` and never create a CUDA context — **caveat: `voicectl status` currently violates this; see BUGS.md VT-001.** RealtimeSTT's ~90 s `recorder.shutdown()` wedge is sidestepped entirely: teardown = `proc.join(5s)` then `SIGKILL` the group.

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

**Idle unload.** A background watchdog reclaims VRAM after a one-off use: when the recorder has sat in `loaded / not listening` for `asr.auto_unload_idle_seconds` (default `1800.0` = 30 min; `0` disables), it tears the recorder down, logs `voice-typing idle-unload: 1800.0s disarmed; unloading models`, transitions to `unloaded`, and frees the ~1.5–3 GB VRAM. The clock starts when the mic disarms (manual stop, toggle-off, or the §4.5 idle auto-stop) and resets on any arm; time spent listening does not count. The next arm then pays the ~1–3 s reload, same as a session's first arm. **Hard requirement — bounded teardown:** the `recorder.shutdown()` call invoked here MUST be non-blocking and complete in well under the arm-latency budget. It MUST NOT reproduce the ~90 s teardown hang currently seen on every `quit` (journal: `run() loop exiting` → 90 s → systemd `SIGKILL` / `Failed with result 'timeout'`), because idle-unload would trigger that hang every 30 min AND block any re-arm that races it under the single-flight lock. If `recorder.shutdown()` cannot be made to complete promptly, guard it with a hard timeout plus force-cleanup of the recorder's worker threads / `transcript_process` so VRAM is actually released. Making teardown bounded is therefore a **prerequisite** for this feature (risk row, §8). **(Resolved by the recorder-host subprocess model above: the daemon `killpg`s the child group after a 5 s join, so VRAM is force-released regardless of `recorder.shutdown()`'s behavior.)**

### 4.2ter Lite mode — small-model-only quick dictation

A second arming mode for short, speed-critical snippets (URLs, shell commands, short replies) where latency matters more than accuracy. Lite mode loads **only** the small realtime model and uses it as both the partials source AND the final-pass model — the large `distil-large-v3` never loads, never runs. Result: ~half the VRAM and markedly faster finals, at lower accuracy. It is entered via a **separate keybind / command**, never by the normal toggle.

**Configuration** (`[asr]`):
- `lite_model` (default `"small.en"`): the single model loaded in lite mode, used for BOTH realtime partials and final transcription. On CPU fallback it auto-downgrades via cuda_check like the normal models; the approved CPU lite substitute is `tiny.en`.

**Recorder construction (lite):** the recorder-host child builds the recorder with `model = lite_model`, `realtime_model_type = lite_model`, and `use_main_model_for_realtime = True`. Verified against RealtimeSTT v1.0.2: with `use_main_model_for_realtime=True` the separate realtime engine is NOT initialized (`_initialize_realtime_transcription_model` early-returns), so exactly ONE model (`lite_model`) is resident — the large final model is never constructed. All other kwargs (device, compute_type, language, silero) are identical to normal mode EXCEPT `post_speech_silence_duration`, which lite overrides with its own snugger threshold (`lite_post_speech_silence_duration`, §4.5) — see the latency note below for why this is load-bearing. `on_final` therefore yields `lite_model` finals — fast, lower-accuracy — over the SAME clean→type→record path as normal mode (§4.2).

**The silence gate, not the model, is the perceived-latency bottleneck (latency-log finding).** The per-utterance latency line clocks `speech_end_to_final_ms` from `on_vad_stop`, which fires only AFTER `post_speech_silence_duration` of trailing silence. On this GPU the small model's final pass is ~80 ms vs the large model's ~130 ms — a ~50 ms win that is SWAMPED by the silence wait, which is identical across modes unless lite overrides it. (Observed live: a 1.5 s `post_speech_silence_duration` made lite feel "no faster than the big model" even though the small model was in fact ~1.6× faster at transcription.) Therefore lite MUST use its own shorter `post_speech_silence_duration` (default `0.5` — the small model is fast and quips are short, so the big model's thinking-pause cushion isn't needed); that is what makes lite actually FEEL instant, cutting stop→text latency from ~1.6 s to ~0.6 s. Tunable: ~0.3 = razor-snappy (may split a brief pause into two finals), ~0.6 = safe. **Rev 2 (§4.2quater):** under streaming the endpointer no longer gates *visible* output — words are typed as they are spoken — it only delays the commit/correction pass, so the default rises to `0.8` (halving mid-thought cuts for +0.3 s commit latency). The "must be snug" rationale above applied to the Rev 1 output model, where finals were the only visible output; `0.5` remains the razor-snappy setting.

**Mode is a spawn-time property of the recorder-host child; the daemon tracks `self._mode` (`"normal"` | `"lite"`).** The resident child is always in exactly one mode. Arming rules:
- Arm in mode X while resident child is mode X → instant arm (models already resident in the right mode).
- Arm in mode X while resident child is the OTHER mode → tear the child down and respawn it in mode X (~1–3 s reload, same bounded teardown as idle-unload, "Loading…" toast). I.e. **switching modes costs one reload.**
- Arm in mode X while unloaded → spawn in mode X (same as a session's first arm).
Idle-unload (§4.2bis) tears down whichever mode is resident; the next arm reloads in whatever mode that arm requests. The graceful drain (§4.2 #2) and idle auto-stop (§4.5) apply identically in lite mode.

**Commands / keybind:** `voicectl toggle-lite` / `voicectl start-lite` arm in lite mode (a clean toggle independent of the normal toggle, so each keybind is unambiguous); `voicectl toggle` / `start` arm in normal mode; `voicectl stop` disarms either. Two Hyprland binds (§4.10): `Ctrl+Alt+Super+D` → `toggle` (big/normal model) and `Alt+Super+D` → `toggle-lite` (little/lite model).

**State / status:** `state.json` gains `"mode": "normal" | "lite"` (written on every arm/disarm alongside the existing fields); `voicectl status` reports `mode:` and prefixes lite with `⚡` so the user can see at a glance which mode is armed. Start/stop toasts stay `"Recording"` / `"Recording Stopped"` in either mode (the keybind itself disambiguates); finals still toast `✔ <text>` per `notify_on_final`.

**Why a reload on switch is accepted:** it is the same ~1–3 s cost already paid on first-arm and after idle-unload, and a user picks a mode for a stretch of use rather than toggling per utterance. A no-reload alternative — committing the realtime partial from the resident two-model recorder — was REJECTED: it keeps the large model loaded, still spins its final pass per utterance, and so delivers neither the VRAM nor the latency benefit that motivates lite mode.

### 4.2quater Streaming dictation — typed partials, in-place revision, Backspace-cancel (Rev 2; small-model/lite path only)

The Rev 1 output model — partials visible only in the status display, one append per silence-triggered final, and a snug endpointer existing largely to force frequent visible output — is REPLACED on this path by phone-style dictation: **words are typed into the focused window as they are spoken, revised in place, and the mic never pauses for decoding.** Scope: the small-model recorder — the ONLY mode (normal mode removed, §1).

**Output state machine (daemon process).** The daemon tracks two strings per armed session:
- `committed` — finalized text, ending at the last commit checkpoint;
- `tail` — everything typed since that checkpoint (the current utterance: tentative, revisable, no trailing space while tentative).

1. **Partial typing (minimal-diff revision).** On each stabilized-partial event (existing IPC): compare the new partial against the currently typed `tail` and touch ONLY what changed. Compute `k` = length of the longest common prefix of the typed `tail` and the new partial (per-character, case-insensitive — the casing guard lowercases mid-sentence fragments while decoder partials stay capitalized — but counted and sliced on the ORIGINAL characters, so a casefold-length change can never desync the indices). Then `press_backspace(len(tail) − k)` — exactly the diverging suffix, NEVER the whole string — and type the corrected suffix (the new partial from offset `k`, through the deterministic guards with the on-screen prefix as casing context). Degenerate cases: pure extension (`k = len(tail)`) → type only the delta with ZERO backspaces; identical text → full no-op; a whole-tail rewind is correct ONLY when the partial genuinely shares no prefix with the tail (fresh start / total rewrite). Backspacing the entire string on every revision is a defect, not the design (user-reported against the first Rev 2 build; pinned by T8a/T8b). Mid-utterance revision is DEBOUNCED for smoothness (code constant, not config): partial typing is extend-only while divergence is fresh — momentary decoder wobble that grows back past the tail re-converges as a pure extension with zero backspaces — and a rewind fires only after the divergence has persisted ≥2 s, using the latest partial (one minimal-diff correction per sustained divergence; the window re-arms after each). The commit's correction is authoritative and never debounced; the common case is zero mid-utterance rewinds and exactly one correction, at the end of the utterance.
2. **Commit (silence trips).** The child's small.en re-decodes the complete utterance (the old "final", now a *correction pass*): if it differs from the typed `tail`, revise with the SAME minimal-diff rule as partial typing (backspace exactly `len(tail) − k` for common-prefix `k`, type only the corrected suffix — a commit that confirms most of the typed tail rewinds only the diverging suffix, and a commit that extends it rewinds nothing); append the trailing space (`output.append_space`); advance the checkpoint; refresh the rolling context prompt (below). Existing gates unchanged: `textproc.clean` (blocklist/min_chars) and the `listening` gate; a rejected final freezes the `tail` as-is.
3. **Drain unchanged** (§4.2 #2) — an explicit stop mid-speech still lets the correction pass land before disarming.
4. **Stranded tail → FREEZE, never delete** (user decision). If no commit can ever land (drain-watchdog abort, child death), the tail stays on screen exactly as last shown. The ONLY thing that deletes typed text is an explicit cancel (below).
5. **User-typing protection (Rev 3 — HALT).** Any non-Backspace keypress observed while armed → DISARM dictation entirely: mic off, engine session reset, no drain, no late keystrokes; the tail stays typed as-is (re-arm with the hotkey). Modifier-only presses (Ctrl/Super/Alt/Shift/Caps etc. — they insert no text and are the arm chord's own keys) do not count, and a 1.5 s grace after arming absorbs the hotkey's own keystrokes. Legacy per-utterance freeze (lift at the next boundary) remains available as `cancel.keypress_action = "freeze"`.

**Typing backend additions.** `press_backspace(n)` MUST delete exactly n characters in an ordinary text field (wtype: repeat `-k Backspace`; ydotool: repeat the backspace keycode; batched so ~80 chars rewind in <150 ms). Revision correctness assumes the cursor sits at the end of our typed text and one keystroke deletes one character — the window where that can be false is closed by the Rev 3 HALT rule. **Accounting invariant (Rev 3):** a rewind MUST be clamped to the engine's own pending tail (never more chars than the engine typed since the checkpoint), every rewind is journaled (count + tail length), and every DROPPED final (cancel-suppression window, sentinel loss) MUST reset the utterance boundary — the tail never accumulates across dropped finals.

**Backspace-cancel.**
- **Listener:** a passive, read-only (never `EVIOCGRAB`) evdev listener thread in the daemon process over every keyboard `/dev/input/event*` node (auto-enumerate: EV_KEY devices that expose KEY_BACKSPACE; `[cancel].devices` overrides). The user is in the `input` group (§2) — no permission changes. `python-evdev` is the implementation dep.
- **Trigger:** KEY_BACKSPACE press while armed AND a `tail` is pending → cancel: rewind `max(len(tail)−1, 0)` characters (the physical keystroke itself already deleted one — compensate by subtraction, never by re-typing), drop the child's in-flight utterance (host abort discards its buffered audio), keep listening — just say the sentence again. **Idempotent:** further Backspaces with no pending tail are plain user edits and are never compensated.
- **Fallback:** `voicectl cancel` (control-socket cmd, §4.2 #3) runs the identical path — keybind-able when no keyboard node is readable (log once at arm; §4.10) and the automated-test seam (T8e).

**Rolling context prompt.** Every decode is conditioned on the committed text **back to the last sentence boundary** (last `.`/`!`/`?`), capped at ~200 tokens (Whisper's ~224-token prompt budget — code constant): partial decodes via `initial_prompt_realtime`, commit decodes via `initial_prompt`. Both kwargs exist in the installed RealtimeSTT 1.0.2 but are constructor-static — the child MUST make them dynamic (update between utterances); if that fails, degrade to context-free decoding and log (never crash). This is the primary fix for mid-paragraph fragments starting capitalized or acquiring spurious trailing periods: the decoder is told it is *continuing*, not starting.

**Deterministic guards (textproc, Rev 2).** Applied at typing time (pure, unit-tested):
- **Casing:** if `committed` does not end a sentence (no terminal `. ! ?`), lowercase the fragment's first word.
- **Period:** if the casing guard fired (we joined mid-sentence), strip one trailing `.` from the committed fragment — a decoder closing a sentence it was just told it was continuing is spurious by definition.
Rev 1 `clean()` rules (blocklist, min_chars, whitespace) are unchanged.

**Unchanged:** VAD segmentation (it now only triggers commits); feedback/state file/toasts (the `partial` field mirrors the live tail; `record_final` records the committed text); lazy load, idle unload, idle auto-stop, and the lite recorder construction (§4.2ter) including single-model `use_main_model_for_realtime=True`; `output.streaming=false` restores Rev 1 append-only behavior as a rollback hatch (§4.5).

### 4.2quinquies Media ducking while listening — pause/duck speakers at arm (spec'd 2026-11-18; implement next round)

**Problem.** The mic has no acoustic echo cancellation: anything the speakers play during dictation is transcribed as speech (music, video, notification dings). Every second of media bleed is pure WER — it is a leading source of "wrong words that change meaning" when dictating on a machine that is also playing audio. The tool should get media out of the way for exactly as long as the mic is hot, and put it back EXACTLY as it found it.

**Mechanism — two tiers, strictly best-effort (verified on this machine 2026-11-18: PipeWire 1.6.9 with PulseAudio compatibility, `playerctl`/`wpctl`/`pactl` installed, 4 live MPRIS endpoints):**

1. **MPRIS pause (primary, default).** At arm: enumerate MPRIS players; for each whose `PlaybackStatus` is `Playing`, record its bus name and pause it (`playerctl --all-players pause` or direct D-Bus; subprocess under a hard timeout). At disarm: resume ONLY players (a) that WE paused, (b) that were `Playing` before we paused them, and (c) that are still `Paused` now. Rule (c) is the user-sovereignty guard: if the user resumed a player themselves mid-dictation, or paused a different one, we never fight them — restore is additive, never destructive.
2. **Sink-volume duck (fallback / non-MPRIS audio).** At arm: read and store the default sink's current volume (`wpctl get-volume @DEFAULT_AUDIO_SINK@`), then set `duck_volume_pct`. At disarm: restore the stored value ONLY if the current volume still equals what we last set — if the user touched the volume mid-dictation, THEIR value wins and we do nothing. This comparison-before-restore is the whole point: a restore that clobbers a user's manual change is worse than not ducking.

NOT chosen: PipeWire `module-role-ducking` (module availability varies across PipeWire versions and it requires a live duck-role stream we do not otherwise need — the classic Linux crapshoot; revisit if WirePlumber grows first-class ducking).

**Lifecycle wiring.** Engage where the arm toast fires; release on EVERY disarm path: manual stop/toggle-off, idle auto-stop, Rev 3 HALT keypress disarm, daemon quit — but NOT on Backspace-cancel (the mic stays hot). Crash-safety: a `ducked` field in the feedback state file lets a post-crash restart self-heal (best-effort release at startup when set), and the systemd unit gets an `ExecStopPost` best-effort restore.

**Failure discipline (non-negotiable, mirrors the PRD §8 philosophy).** Ducking is an enhancement, NEVER a gate: every audio call is subprocess/bounded (`timeout` ≤1 s), failures journal ONE line and are otherwise invisible, and arm latency must not measurably change (engage runs concurrently with recorder arming; the arm does not wait for it). Engage/release are idempotent — repeated arms must not stack pauses or volume writes, and release without a prior engage is a no-op.

**Config (`[audio]` section — add to config.py + config.toml in lockstep with the key-set test, 24 → 26 keys).**
- `duck_mode = "off"` — `"mpris"` | `"volume"` | `"off"`. Ships `"off"` until implemented; default flips to `"mpris"` the round this lands.
- `duck_volume_pct = 15` — target volume for the `"volume"` tier.

**Tests (unit, no real audio — an `AudioDucker` protocol with engage()/release() and a mocked backend):** (a) resume-only-what-we-paused (a player the user paused mid-dictation stays paused); (b) volume restore skipped when the user changed volume mid-dictation; (c) release fires on every disarm path incl. HALT and auto-stop; (d) a hung backend call (mocked 5 s sleep) does not delay arm beyond bound; (e) engage/release idempotence; (f) crash-recovery: `ducked` flag in state → release at next daemon start.

**Acceptance.** Music playing → arm → music pauses within ~1 s and resumes at stop; video in a non-MPRIS app with `duck_mode="volume"` → volume ducks to 15% and restores exactly; the user changing volume or player state mid-dictation is never overridden; `journalctl` shows the engage/release lines; with `duck_mode="off"` behavior is byte-identical to today.

### 4.2sexies Bulk text delivery — paste as policy (Rev 4; active when `output.delivery="bulk-text"`)

**Status: normative specification; NOT implemented and NOT verified in any real field.** Everything in this subsection uses MUST in the PRD sense. Labels R.1–R.8 are referenced from §6/§7/§8.

**R.1 The experience (binding user requirements).**
- Words MUST become visible in the **focused editable field** as recognition updates arrive — the operator reads the newest words at the insertion point while still speaking. No wait-for-silence, no "survived N partials / one word behind the frontier" batching (the 2026-11-18 draft's stability gate is REVOKED — it violates this), no minimum batch size or flush timer before the first words, never a sentence-end dump. A caption bar, notification, state-file field, or session transcript is NOT a substitute; no caption window is required by this spec.
- A correction MUST land as ONE visible edit that replaces only the tool's OWN verified range — no erase animation, no blank frame, no per-character retype, no caret walk. An unchanged result MUST emit ZERO visible edits (zero-diff guard, generalized: compare RENDERED text after the existing language/spacing guards; two strings that render identically ⇒ zero events; real case/punctuation/word differences are never declared equal).
- **Event-count law:** judge every delivery primitive by operations-per-change — insertion = 1, correction = 1, zero-diff = 0. Pacing is not a lever. Synthesized per-character typing and Backspace chains are FORBIDDEN in this mode; there is no fallback to the §4.3 typing backends.
- Correction reach is NOT bounded by utterance (user decision 2026-11-19: proposed scope limits were rejected). Replacement may reach any OWNED dictation text provided it is imperceptible; the safety boundary is OWNERSHIP, never size.
- The bar: beat the operator's ~110 wpm type-then-proofread effective throughput, counting corrections, recovery, and rereading time.

**R.2 Evidence and provenance (2026-11-20; do not re-derive, do not over-claim).**

| Observation | Witness and limits |
|---|---|
| 951-byte Unicode payload delivered intact as ONE bracketed paste; 153 ms and 175 ms in two runs from shortcut-trigger to bytes-received (clipboard pre-staged; includes test overhead; NOT speech, render, or end-to-end timing) | A Python byte reader inside disposable Ghostty 1.3.1 under a private headless Sway (`tools/paste-lab/ghostty_probe.py`). NOT the operator, NOT pi's editor, NOT the real desktop. An earlier synthetic-keyboard variant FAILED to deliver — process success is not acceptance. |
| Two pasted Backspace bytes (0x08 0x08) arrived as two SPACES followed by "end" | Same probe, raw payload. Bulk-Backspace-over-paste is DEAD on this route; range replacement must come from a real editing mechanism. |
| Engine facts: large-v3-turbo@float16 polled = 382 ms median word lag, WER 0.021; streaming transducers = 42–52% wrong words on the operator's real voice (transducer migration DEAD) | `tools/asr-lab/` bake-off + real-voice clips. |
| Input-method-v2 route is LIVE and capable on GTK-class fields (2026-11-22): insert 26–40 ms command→visible-field with exact cursor; ONE atomic commit (`delete_surrounding_text(before,0)` + `commit_string` + `commit(serial)`) corrects a whole 1024-byte span byte-exactly — GTK fires 1–2 internal `changed` signals within one commit cycle, frame-level single-edit still unverified; preedit carries live updates with ZERO document edits and a matching final lands as one atomic preedit→commit transition; `surrounding_text` returns byte-exact cursor/anchor (target-CONFIRMED text, R.5's third value); `grab_keyboard` key events reach the adapter while the field stays untouched and IM commits generate ZERO key events (delivery cannot self-trigger takeover) | `tools/im-lab/` (wlwire/im_probe/fields/imlab_run) in a disposable Xvfb+Sway desktop; GTK4 `Gtk.Entry` asserting its own text/caret/edit-count; 29-row run, 24 pass. NOT the operator's desktop, NOT Hyprland, NOT speech — mechanism evidence only. |
| Field-class matrix (same lab): foot 1.28 and kitty 0.49 = INSERT-ONLY over IM (both silently ignore `delete_surrounding_text`; neither ever sends `surrounding_text`; foot renders preedit, kitty app-side only); ghostty 1.3.1 = IM route DEAD (text-input activates, no byte ever reaches the pty; matches ghostty's own IME tracker — retest on version bump); live Hyprland 0.56.2 ADVERTISES `zwp_input_method_manager_v2 v1` + `zwp_text_input_v3 v1` (passive read-only registry listing via `tools/im-lab/globals.py`); sway 1.12 advertises the same set | Terminals that never send `surrounding_text` cannot be ownership-verified over IM — terminal verification MUST come from the app side (R.3 units rule). |
| pi's TUI editor has a DOCUMENTED extension seam (no fork): `ctx.ui.setEditorComponent()` installs a custom editor component; `ctx.fork({position:"before"})` restores a prompt into the editor — the cooperating-editor TargetAdapter for the chat-prompt milestone can be an extension + local control socket | pi `docs/extensions.md` read 2026-11-22; the API's exact write/caret control is not yet exercised by code — prove at G3. |
| Old incident mechanisms pinned: equality guard already exists; a k=0 final orders a full-tail rewind BY DESIGN; one silently dropped insertion desyncs belief and the next rewind eats committed text | `tests/test_zero_diff_rewind.py` T1–T3 (3/3 pass at handoff). |
| NOT VERIFIED anywhere: insert+correct in the real chat prompt; speech-to-visible latency; desktop coverage; throughput; Hyprland relay behavior (nested Hyprland cannot boot under the lab's software rendering — aquamarine `CBackend::create()` fails) | No operator acceptance on record. A passing transport probe NEVER flips any of these to "passed". |

Protocol facts (upstream-verified): `wl_data_offer.receive` serves bytes to ANY requester — a clipboard-history manager can be that requester, and the protocol carries NO acceptance acknowledgement; `wl-copy` cannot restore an offer that had multiple formats; `input-method-v2` provides `commit_string`/`set_preedit_string`/`delete_surrounding_text` plus an atomic `commit(serial)` whose evaluation order is preedit-replace → delete-surrounding → insert-commit (wire format per the XML Hyprland itself vendors); compositor advertisement verified on live Hyprland 0.56.2 and sway 1.12, per-field support MEASURED (R.2 matrix) — Hyprland relay behavior remains untested.

**R.3 Delivery model.** A new bulk-delivery controller plus a TargetAdapter, SEPARATE from `StreamingOutput`/`typing_backends.py` (legacy code stays for `stream-edit`; the bulk adapter MUST NOT expose `type_character`/`press_backspace` or any typing fallback):
- `acquire`: bind the SPECIFIC editable field — not merely a window, terminal process, or screen position. Return an opaque target handle + revision. Fail BEFORE delivery for non-editable, password/secret, selected, or unidentified fields; never replace a pre-existing user selection by default. A pane, tab, or inner editor can change without the window changing.
- `show(session, utterance, seq, expected_revision, complete rendered span)`: one insert-or-replace executed ON the target's event loop, only if focus, caret, selection, and ownership still match. Returns `applied | unchanged | refused | unknown`. Bytes sent is not "applied"; "unknown" is not "delivered".
- `finalize`: a final matching the visible text ⇒ NO further edit (ownership ends; composition-protocol commit side effects must not visibly change or duplicate the text). A differing final ⇒ ONE replacement of verified owned text. A final with no preceding partial inserts once and counts as a missed live update in latency evidence.
- `leave`/`cancel`: stop preserves the last visible words where they are — no post-stop writes anywhere, including a newly focused field. Deliberate cancel may remove the owned fragment in ONE operation, drop its buffered audio, and keep listening.
- Ownership and units: the adapter maps text positions to the target's own units (UTF-8 bytes, characters, UTF-16 units, or editor markers); never slice via a lowercased/normalized copy. Adjacent user text, whitespace, and formatting are never touched. No control bytes, tabs, newlines, escape sequences, paste delimiters, or Enter as input — recognized prose line breaks normalize to a space. The lazy continuation space applies only on the SAME verified target.
- The terminal chat prompt is the first milestone: prove pi's real input editor inside isolated Ghostty. An adapter for that editor is in scope (a documented extension/input seam preferred over a fork; the seam exists — R.2: `ctx.ui.setEditorComponent()` / fork prompt-restore). No tmux requirement, no terminal reconfiguration, no disabling of paste safeguards.

**R.4 Implementation order and stopping rules.** (1) Field FIRST: an isolated instance of the real prompt, scripted partials/finals, asserting exact editor text + caret + the VISIBLE prompt — a byte reader, scrollback, or fake editor never substitutes; missing visibility instrumentation means "not verified", not "passed". (2) Route assignment is DECIDED (2026-11-22, R.2): the `zwp_input_method_v2` adapter is the PRIMARY route — insert = `commit_string`+`commit`; correction = `delete_surrounding_text(before,0)`+`commit_string`+`commit` in ONE atomic commit; zero-diff = no request; verification via `surrounding_text`; takeover via keyboard-grab key events. Coverage per the R.2 matrix: full on GTK-class fields, insert-only on foot/kitty, UNAVAILABLE on ghostty 1.3.1. The terminal chat-prompt milestone uses the cooperating-editor extension seam (R.2); clipboard paste remains an insert fallback for ghostty-class terminals only, under the R.6 contract. Do NOT re-run route discovery. (3) Prove insert AND correct before any mic integration. (4) Integrate recognition and keep the first working route runnable. If no safe route exists in a field, record the missing capability — NEVER fall back to typing, and a blocked matrix row is a legitimate result. Development MUST NOT change the operator's service, config, or bindings as a side effect.

**R.5 Ordering, takeover, and failure.**
- New session generation at every arm; utterance identities assigned at the decode source and carried through `recorder_host`'s event relay (extend the `partial`/`final` payloads — a late event keeps its own identity, never relabeled as newer); keep the existing arm/disarm audio purges. Discard late post-final partials, duplicate finals, and canceled-utterance events; a dropped or filtered final still closes its utterance boundary; a rejected final never auto-erases visible words.
- `RecorderHost._dispatch` invokes `_on_partial`/`on_final` on the reader thread: bulk mode MUST enqueue and return — no subprocess, editor wait, or display polling there or under the daemon control lock. One writer per target; one operation in flight; newest partial wins for the current utterance; finals and boundaries are ordered barriers, never overwritten (bounded queue, default 32; overflow stops delivery rather than dropping a barrier).
- Takeover: any ordinary physical key, caret move, selection change, mouse click, focus change, tab/pane switch, or target death revokes the handle AT THE TARGET (daemon-side flags alone do not suffice); queued operations re-check at mutation time. Stop/toggle-off/idle-stop disarm immediately with no late flush. The arming chord is ignored (not a blanket grace window). Synthetic delivery events cannot self-trigger HALT or leave modifiers held. Pointer motion alone is not an edit.
- Bare Backspace keeps cancel semantics ONLY where the target can consume the gesture on an owned live fragment before performing an ordinary deletion (test tap, hold, auto-repeat, release). Otherwise the real key is an ordinary user edit ⇒ HALT ⇒ inject nothing. `voicectl cancel` in bulk mode performs NO `len(tail)-1` physical-character compensation (route bulk cancel BEFORE `daemon.cancel`'s legacy backspace call): it discards the fragment's recognition, removes only a verified owned range, and leaves the mic armed on success; nothing pending ⇒ no edit; uncertain range ⇒ stop, never attempt repair.
- Any `unknown`/`refused`/stalled operation (250 ms engineering deadline) disarms bulk delivery AND recording, retains recoverable recognition, and reports one concise reason via status and the configured fault surface. NEVER retry an operation that may already have landed. Validate deadlines and takeover in the RECEIVER so a late operation cannot mutate after the daemon has given up.
- Keep three values distinct: latest recognized text; filter-accepted final; last target-CONFIRMED visible text. `feedback.record_final` keeps its recognition meaning for existing clients; `state.json`/status gain `delivery_mode`, `delivery_state` (`inactive|active|unsupported|fault`), `delivery_reason`, and last confirmed op — never the surrounding user document. New bulk-path logs carry counts and times, not recognition text.

**R.6 Clipboard and recovery.**
- Routine delivery prefers a CLIPBOARD-FREE route. If an adapter must use the ordinary clipboard it MUST preserve all prior formats and bytes, distinguish original ownership from a later copy with identical text, protect a simultaneous user paste, and keep partials out of the configured clipboard-history watcher. Compare-before-restore, sleep-before-restore, `--paste-once`, and "first reader = the editor" are INSUFFICIENT. If this cannot be proven with the local manager, that adapter is unavailable — never disable the manager. The PRIMARY selection stays untouched.
- Recovery (both delivery modes): daemon memory holds the last nonempty arm→disarm session — accepted final per utterance plus the last visible/recognized unfinished tail, exactly once each; a rejected final retains only the shown tail; deliberate cancels and late finals are excluded; the previous completed session survives empty or failed arms; at most two sessions × 1 MiB UTF-8 (on overflow keep the newest complete text that fits and report truncation); cleared at daemon exit; no crash persistence, audio archive, or new transcript-bearing logs. `voicectl session` prints the most recent COMPLETED session (never a moving draft); `voicectl session --copy` copies exactly that text — no added newline, never types/erases/submits, exit 1 with the clipboard untouched when none exists; truncation is reported on stderr and in the reply. Any bind for it is user-assigned, never installed over an existing one.

**R.7 Verification and graduation gates.** All under the repo's timeout discipline; automation MUST NOT exercise the live desktop, real clipboard, default microphone, or active service — private compositor + synthetic input + isolated app instances; evidence stays bounded, only fixtures enter version control.
- **G1 regression baseline:** record pre-change results of `test_streaming_commit`, `test_zero_diff_rewind`, key-listener, control-socket, and config suites; reconcile the legacy separator failures at HEAD (measured at the 2026-11 handoff: `test_streaming_commit.py` 10 failed / 22 passed; `test_zero_diff_rewind.py` 3/3 passes) against the lazy-separator contract and separate them from NEW failures (no blanket skips, no legacy behavior changes to fake parity).
- **G2 controller, fake target:** deterministic traces — append; first-word change; identical update and final; retraction; Unicode; rejected/lost final; repeated cancel; timeout-after-apply; held key; out-of-order results; stop + immediate re-arm; child death; focus change mid-operation. Assert exact text/caret, bounded queue, zero legacy-backend calls, no duplicates, no extra writes, no post-takeover mutations. Necessary, never sufficient.
- **G3 real-field matrix** (per claimed field, starting with text on both sides of the caret): short updates; a 20-sentence first-word correction; repeated identical finals; long and Unicode payloads; pane/tab/window switches; a refusing target. Assert editor contents + cursor + the visible prompt; no transient delete/retype frames, no folded-paste placeholders, no neighbor changes, no shortcut execution or submission. Rows report `untested | insert-only | blocked (reason) | verified (versions + evidence links)`. A G2 pass never marks a row verified.
- **G4 clipboard (only if used):** private manager with text+image watchers; simultaneous copies incl. identical bytes; user paste during transfer; empty, rich-text, and image offers; failure before and after the data request; process death — verify contents, history, all original formats, and the target, never exit codes.
- **G5 timing** (warm GPU, monotonic clocks, word-aligned replay of real voice — callback cadence and the silence detector are NOT the speech clock): speech-end→word-visible median ≤ 500 ms, p95 < 1 s; update-ready→first-changed-frame p95 ≤ 100 ms (insertion) / ≤ 50 ms (correction); unchanged ⇒ no edit; ≥ 100 insertions and ≥ 100 corrections per claimed route; publish counts, median, p95, worst gap, max words outstanding. Missing words are misses, not zero-latency samples. A sustained five-word backlog or a sentence-end dump fails regardless of medians.
- **G6 graduation to default:** verified G3 rows for the pi prompt in Ghostty, a graphical editor, and a browser text field; zero observed integrity failures; and ≥ 3 representative completed writing sessions where usable proofread words per minute — counting corrections, recovery, and rereading — beats 110 wpm. Otherwise report that and stay opt-in. Never claim "works on Wayland" from one row; never fabricate user acceptance.

**R.8 Recognition quality is separate work.** Keep the configured large-v3-turbo@float16 path and its lifecycle guarantees (lazy load, idle unload, segmentation without session end). Compare the earliest usable update callback against the currently wired stabilized callback on the same recordings and choose by VISIBLE word lag and correctness; never interleave two streams as one hypothesis chain. A second LOCAL model for a preview/final split is a permitted experiment (one utterance identity, one displayed hypothesis, one authoritative final; keep only if measurably better); external/offload processing is NOT enabled here. Unrelated-phrase reports: replay known speech, silence, a pause, media bleed, and stop/re-arm against recognition-vs-delivered text — already-in-recognition ⇒ audio/model/stale-audio investigation; only-in-field ⇒ delivery/stale-state investigation; no origin claims without evidence, no phrase suppression to pass tests. Media ducking (§4.2quinquies) and the legacy §8 bugfixes (datagram merge `33321c6`, cancel auto-repeat) are NOT prerequisites for a clipboard-free bulk adapter.

### 4.3 Typing backends (`typing_backends.py`)

Interface: `type_text(text: str) -> None` (append committed text) plus `press_backspace(n: int) -> None` (Rev 2, §4.2quater — delete exactly n characters for in-place revision). Selected by config `output.backend`, default **`wtype`**.

- **wtype** (default): `subprocess.run(["wtype", "--", text])`. Uses Wayland `virtual-keyboard-v1` — supported by Hyprland, full Unicode, no layout issues. Types into the focused window.
- **ydotool**: `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text])`. uinput-level, works even for XWayland apps; known weakness: non-ASCII/layout quirks. Keep as fallback; daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit), logging a warning.
- **null**: types NOTHING. For the headless E2E test (which asserts finals via the state file instead of real keystrokes, so an automated run can never type into the developer's focused window) and for output-disabled setups. No subprocess is spawned.

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
    silero_backend="auto",              # item correction: modern control (prefers bundled CPU ONNX → avoids the torch-hub download). Supersedes the legacy silero_use_onnx=True.
    spinner=False,
    use_microphone=True,                # False + feed_audio() in tests
    ensure_sentence_starting_uppercase=False,  # item correction: textproc owns casing/punctuation cleanup
    ensure_sentence_ends_with_period=False,    # item correction (same reason)
    no_log_file=True,                   # suppress RealtimeSTT's unbounded realtimesst.log (sole log path = stderr → journald)
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
  must happen via os.execv re-exec or in a launcher wrapper, because LD_LIBRARY_PATH is read at process start. **Realized approach:** `voice_typing/launch_daemon.sh` (the ExecStart, §4.9) recomputes the cuBLAS/cuDNN lib dirs from the *live installed* `nvidia-*-cu12` wheels on every launch and exports `LD_LIBRARY_PATH` before exec'ing python — so no baked `Environment=LD_LIBRARY_PATH=` is used in the unit (it would go stale on `uv sync`). If `libcudnn_ops*.so` errors still appear, check the wrapper (`LD_DEBUG=libs launch_daemon.sh`).
- If CUDA init fails entirely, daemon MUST log clearly and fall back to `device="cpu", compute_type="int8"` with `realtime_model_type="tiny.en"`, model `small.en` — degraded but functional — and say so in `status`.
- **Lite mode (§4.2ter):** the lite recorder is constructed with `model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True` (verified: only ONE model initializes; the large final model is never constructed), AND a snugger `post_speech_silence_duration = lite_post_speech_silence_duration` — the silence gate, not the model, is the perceived-latency bottleneck, so lite MUST shorten it to actually feel faster (see §4.2ter).
- **Streaming path (Rev 2, §4.2quater):** the lite recorder additionally runs with a dynamic `initial_prompt` / `initial_prompt_realtime` (rolling committed context; both kwargs exist in installed v1.0.2 but are constructor-static — the child updates them between utterances) and `lite_post_speech_silence_duration = 0.8` default.

### 4.5 Config (`config.toml`, parsed with stdlib `tomllib` into dataclasses)

```toml
[asr]
final_model = "distil-large-v3"
realtime_model = "small.en"
lite_model = "small.en"             # the SINGLE model loaded in lite mode (used for both partials + finals); §4.2ter
language = "en"
device = "cuda"                       # "cuda" | "cpu"
compute_type = "float16"              # ctranslate2 compute type on the CUDA path (2026-11-18: now a config key, config.py + config.toml in lockstep). "float16" = Ampere+ native — measured ~2x faster decode (the ASR-lab bake-off: turbo polled at float16 = 382 ms median word lag vs 2667 ms at float32); "float32" = legacy cards without usable fp16. Ignored on the CPU paths (always int8).
post_speech_silence_duration = 0.6
lite_post_speech_silence_duration = 0.8  # Rev 2 §4.2quater: the endpointer only delays COMMIT under streaming (words are already typed live) — 0.8 halves mid-thought cuts for +0.3 s commit latency. 0.5 = razor-snappy; 1.0 = near-zero cuts.
context_prompt = true                  # Rev 2 §4.2quater: condition every decode on the rolling committed context (back to the last sentence boundary, ~200-token cap)
realtime_processing_pause = 0.15
auto_stop_idle_seconds = 30.0          # auto-disarm after this many seconds of no speech; 0 disables
auto_unload_idle_seconds = 1800.0     # after this many seconds disarmed (loaded, not listening), tear down models to free VRAM; 0 disables (§4.2bis Idle unload)

[output]
backend = "wtype"                     # "wtype" | "ydotool" | "null"
append_space = true
graceful_stop = false                # Rev 3: stop = IMMEDIATE disarm (racing final dropped, tail stays typed). true = Rev 2 drain (wait ~5 s for the in-flight final) first.
streaming = true                     # Rev 2 §4.2quater: type stabilized partials live + revise in place; false = Rev 1 append-only finals (rollback hatch)
delivery = "stream-edit"             # Rev 4 §4.2sexies: "bulk-text" = paste-as-policy output path (show each update in the field; one-edit corrections; NO typing/backspace fallback). "stream-edit" = today's behavior (default until G6 graduation). bulk-text requires streaming=true, graceful_stop=false, keypress_action="disarm".

[cancel]                              # Rev 2 §4.2quater: Backspace-cancel
keypress_action = "disarm"           # Rev 3: any real keypress while armed halts dictation entirely; "freeze" = legacy per-utterance freeze
on_backspace = true                  # evdev listener: Backspace while a fragment is in flight cancels it (rewind + drop audio, keep listening)
devices = []                         # empty → auto-enumerate keyboard /dev/input/event* nodes; else explicit path list override

[feedback]
state_file = ""                       # empty → $XDG_RUNTIME_DIR/voice-typing/state.json
hypr_notify = true                    # master switch for hyprctl popups (start/final/stop)
notify_on_final = true                # also pop “✔ <text>” per final? (redundant: text is typed into the focused window)
notify_ms = 2500

[filter]
min_chars = 2
blocklist = ["thank you.", "thanks for watching.", "you", "bye.", "thank you for watching"]  # case-insensitive exact matches — classic whisper silence hallucinations


[log]   # daemon logging verbosity (stderr → journald under systemd)

level = "INFO"            # "INFO" = one structured per-utterance latency line + the startup device/models line; "DEBUG" = also the raw monotonic timestamps. Read live with `journalctl --user -u voice-typing -f`.
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
- **hyprctl notify**: `hyprctl notify -1 <notify_ms> "rgb(88c0d0)" "<msg>"` — fire-and-forget, swallow errors. Hyprland notifications are not replaceable by ID; to avoid stacking spam, only notify on: listening-start ("Recording"; the FIRST arm of a session is preceded by a one-shot "Loading…" toast while the models load — §4.2bis), each *final* ("✔ <text>" — gated by `notify_on_final`, since the text is already typed into the focused window), listening-stop ("Recording Stopped" — for ANY disarm: manual stop, toggle-off, idle auto-stop, or the drain completing). Partials go to the state file only. `record_final` ALSO writes the finalized text back into the `partial` field so status consumers see what was actually typed (otherwise `voicectl status` would keep showing the last trailing realtime partial, which usually drops the final word or two).

Status consumers (all read the state file above): `voicectl status`, the state-file fields themselves (`jq`-able for any custom UI), and the transient hyprctl toasts.

### 4.7 Text processing (`textproc.py`)

`clean(text) -> str | None`:
1. `text.strip()`; strip trailing newlines; collapse internal whitespace runs to single spaces.
2. Reject if `len < filter.min_chars`.
3. Reject if lowercase-stripped-of-trailing-punctuation form is in blocklist.
4. Return cleaned text. Caller appends a single space when `append_space`.

Unit-test this module (pure python, fast).

### 4.8 `voicectl` (`ctl.py`)

`uv run voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite|cancel>` and an installed console-script entry point (`[project.scripts] voicectl = "voice_typing.ctl:main"`, plus `voice-typing-daemon = "voice_typing.daemon:main"`). Connects to the socket, sends one JSON line, prints human-readable result (`listening: on`), exit code 0/1. `status` pretty-prints the state incl. partial, `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`), `models_loaded` (§4.2bis), and `mode` (`normal`/`lite`, §4.2ter). `toggle-lite`/`start-lite` arm in lite mode; `stop` disarms either. If daemon not running: clear message + exit 2.

### 4.9 systemd user service (`systemd/voice-typing.service`)

```ini
[Unit]
Description=Local voice typing daemon (RealtimeSTT)
# VT-004: order after + bind the lifecycle to graphical-session.target so the daemon starts AFTER
# the compositor exported WAYLAND_DISPLAY/DISPLAY (making the ExecStartPre import meaningful, not a
# cold-boot no-op). launch_daemon.sh still re-fetches the vars as belt-and-suspenders.
After=pipewire.service ydotool.service graphical-session.target
PartOf=graphical-session.target

[Service]
# wtype (default backend) is a Wayland client and needs WAYLAND_DISPLAY/DISPLAY; import them
# from the user manager (populated at graphical-session launch). Ordering after
# graphical-session.target (VT-004) makes this meaningful instead of a cold-boot no-op;
# launch_daemon.sh re-fetches the vars as the real workaround regardless.
ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY
# ExecStart is the LD_LIBRARY_PATH wrapper (voice_typing/launch_daemon.sh), NOT python directly.
# The wrapper recomputes the cuBLAS/cuDNN 9 lib dirs from the LIVE installed nvidia wheels on every
# launch, so this unit survives `uv sync` reinstalls without edits. Do NOT bake
# Environment=LD_LIBRARY_PATH= here (it goes stale). The wrapper also sets HF_HUB_OFFLINE=1.
# VT-003: __REPO__ is a PLACEHOLDER install.sh substitutes with the actual repo path when it
# copies the unit into ~/.config/systemd/user/ (portable across users / repo locations).
ExecStart=__REPO__/voice_typing/launch_daemon.sh
Restart=on-failure
RestartSec=2
# KillMode=mixed: deliver SIGTERM to the MAIN daemon only (let its single-flight host.stop()
# killpg its own recorder-host child), then SIGKILL the whole group only after TimeoutStopSec.
KillMode=mixed
TimeoutStopSec=15

[Install]
# VT-004: a Wayland client daemon starts/stops with the graphical session (not default.target,
# which raced the compositor on cold boot). install.sh removes a stale default.target.wants
# symlink from prior installs when it enables the unit.
WantedBy=graphical-session.target
```
`install.sh`: `uv sync`, prefetch models, run a 5-second CUDA smoke test, install+`daemon-reload`+enable+start the unit, print usage and the Hyprland keybind instruction. Idempotent. The daemon starts **not-listening** and **not-loaded** — it must never hot-mic on boot and loads no models until the first arm (§4.2bis, ~0 VRAM at idle); `voicectl start`/`toggle` arms it (the first arm each session also loads the models, ~1–3 s).

### 4.10 Phase 2 (implement after all tests pass — small, do it in the same run)

Hyprland keybinding: append to nothing — instead create `hypr-binds.conf` in the repo containing
```
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle
bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite
bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel   # fallback when the evdev Backspace listener can't open a keyboard (§4.2quater)
```
(`Ctrl+Alt+Super+D` = big/normal model; `Alt+Super+D` = little/lite model, §4.2ter.) Print an instruction to `source` it from `~/.config/hypr/hyprland.conf`. Do NOT modify the user's Hyprland config automatically. (Richer overlay UI is out of scope; state file + toasts are the UI for now.)

---

## 5. Installation steps (for the implementing agent)

1. `cd /home/dustin/projects/voice-typing`
2. Ensure portaudio: `pacman -Q portaudio || sudo pacman -S --noconfirm portaudio` (PyAudio dep of RealtimeSTT).
3. `/home/dustin/.local/bin/uv init --bare --python 3.12` (already a git repo; keep name `voice-typing`).
4. `uv add "realtimestt[faster-whisper,silero-vad]" nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" "huggingface_hub>=0.23" evdev` — the extras pull torch, faster-whisper, pyaudio, webrtcvad, and Silero; the `nvidia-*-cu12` wheels provide the cuBLAS/cuDNN 9 shared objects CTranslate2 loads; `huggingface_hub` is used by `prefetch.py`. If torch arrives CPU-only, add the CUDA wheel explicitly (`uv add torch --index https://download.pytorch.org/whl/cu126` or current cu12x index). Torch is needed for Silero VAD, not the whisper inference itself (that's CTranslate2), so `torch.cuda` availability is nice-to-have; **`ctranslate2` CUDA is the must-have**: `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` → ≥1.
5. Write all source files per §4.
6. Prefetch models; run tests (§6); install service.
7. Commit everything to git on `main` with a sensible message. (User's git identity is already configured.)

Beware the shell aliases (§2): always invoke `/home/dustin/.local/bin/uv`, `.venv/bin/python` with full paths in Bash calls.

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

**T3 — Full E2E with virtual mic (`e2e_virtual_mic.sh`):**
1. `pactl load-module module-null-sink sink_name=vt_test media.class=Audio/Sink` → play into it with `pw-cat --playback --target vt_test`, and point the daemon at the monitor: run daemon with config override `input device = monitor of vt_test` (RealtimeSTT `input_device_index` — resolve the PyAudio index of `vt_test.monitor`; a helper that lists PyAudio devices and greps is required). Alternatively `pactl set-default-source vt_test.monitor` for the test and restore the original default after (record it first!).
2. Start daemon with `backend="null"` (types nothing, spawns no subprocess — an automated run can never keystroke into the developer's focused window); finals are verified through the state file instead.
3. `voicectl start`; play `utt_pause.wav` then `utt_multi.wav`; wait; `voicectl stop`.
4. Poll `state.json` (`last_final`) and fuzzy-match ALL segments incl. post-pause half; assert state.json showed partials (poll it during playback and record snapshots); assert the in-flight utterance's final IS recorded after `voicectl stop` (the graceful drain lets the final model finish — §4.2 #2), then assert no FURTHER final appears while playing one more WAV after the drain completes (toggle-off gates output once disarmed).
5. Cleanup: unload module, restore default source. Use `trap` — the test MUST NOT leave the user's default source switched.

**T4 — Idle stability:** with daemon listening and silence (no playback) for 120 s, assert: no new final in `state.json` (hallucination guard works — this catches Whisper's silence-hallucination), no crash, CPU of daemon process < 25% of one core on average (`pidstat` or /proc sampling).

**T5 — Real-hardware smoke (cannot be automated — leave to user):** README's "First run" section tells the user exactly: `systemctl --user start voice-typing`, `voicectl toggle`, speak (watch the hyprctl toasts / `voicectl status`), `voicectl toggle`. List expected behavior and the two tunables that matter (`post_speech_silence_duration`, `silero_sensitivity`).

**T6 — GPU lifecycle (lazy load):** (a) **idle, never armed:** right after daemon boot with no arm, `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` MUST NOT list the daemon PID at all (~0 VRAM — the lazy-load guarantee of §4.2bis). (b) **armed:** after `voicectl start`, the daemon PID appears with used_memory ~1–5 GB. (c) **disarmed (not quit):** after `voicectl stop`, the PID + memory REMAIN resident (instant re-arm). (d) **disarmed then idle ≥ `auto_unload_idle_seconds`:** the PID disappears from `nvidia-smi` again (~0 VRAM reclaimed); a later `voicectl start` reloads (~1–3 s) and the PID reappears.

Latency targets (log-derived, from T1/T3): partial cadence ≤ 300 ms while speaking; final-typed ≤ 1.5 s after end-of-utterance (0.6 s of that is the deliberate segmentation pause). If finals exceed target on GPU, first check that both models are actually on CUDA (log it), then try `large-v3-turbo`. The ~1–3 s model load on the first arm of a session (§4.2bis) is a one-time startup cost and does NOT count against utterance latency.

**T7 — Lite mode (`test_feed_audio.py` lite variant + `voicectl`):** construct the lite recorder (`model = lite_model`, `realtime_model_type = lite_model`, `use_main_model_for_realtime = True`, `post_speech_silence_duration = lite_post_speech_silence_duration`) and feed `utt_simple.wav`: assert (a) exactly ONE model is resident (no `distil-large-v3` / large-model worker — grep the child log / check VRAM ≈ half of normal); (b) finals still arrive over the normal clean→type path and fuzzy-accuracy ≥70% (lower bar than normal mode's 80%, since `small.en` is the final model); (c) the lite kwargs carry the SHORTER `post_speech_silence_duration` (the silence gate — not the model — is the perceived bottleneck; without this lite feels no faster than normal — §4.2ter), and end-to-end stop→text latency is materially lower than normal mode on the same utterance. Then over the socket: `toggle-lite` arms with `mode:"lite"` in the response; `toggle-lite` again disarms; a subsequent `toggle` reloads into `mode:"normal"` (one reload); `status` reports the current `mode`.

**T8 — Streaming dictation (Rev 2 §4.2quater, `test_streaming.py`, no mic):** lite recorder child + a RecordingTypingBackend (records `type_text`/`press_backspace` calls; no real keystrokes). Feed WAVs via `feed_audio`.
Assert: (a) while speech streams, typing deltas arrive at least every 500 ms; a partial that extends the tail types ONLY the delta (zero backspaces), and a partial that revises the tail backspaces EXACTLY `len(tail) − k` (k = common-prefix length with the new partial) then types only the corrected suffix — a whole-tail rewind for a tail-only edit is a test FAILURE; (b) a differing commit backspaces exactly the non-common suffix (`len(tail) − k`) then types only the corrected final text (+ trailing space), and a commit that extends the tail rewinds nothing; (c) a single sentence split by a 3 s pause joins into ONE coherent commit — no mid-sentence capital, no spurious trailing period (context prompt + textproc guards); (d) the child's decodes carry `initial_prompt` = committed text back to the last sentence boundary, capped (assert via child log/kwargs); (e) `cancel` while a tail is pending → `press_backspace(len(tail)−1)`, the buffered audio is dropped (no commit for it later), listening stays on; a second cancel is a no-op; (f) a non-Backspace user key while a tail is pending → tail frozen, no further revision keystrokes for that utterance; (g) the stranded-tail path (forced drain-timeout) → text frozen on screen, not rewound. The evdev key-event parser is unit-tested separately with synthetic events (no real keyboard); real-Backspace behavior stays in the T5 manual smoke (add: press Backspace mid-fragment → the fragment disappears, dictation continues armed).

**T9 — Bulk text delivery (Rev 4 §4.2sexies; runs only with `output.delivery="bulk-text"`):** execute gates G1–G5 of §4.2sexies R.7 in order — G2 fake-target controller traces first, then the G3 real-field matrix (pi prompt in isolated Ghostty, a graphical editor, a browser field), G4 clipboard contract if a clipboard route is used, G5 timing on word-aligned real-voice replay. G6 (graduation/default flip) additionally requires the writing-session throughput evidence. Transport probes (`tools/paste-lab/`) support evidence but never substitute for G3/G5. No keystroke-fallback assertions from T8 apply in this mode.

---

## 7. Acceptance criteria (definition of done)

1. T1–T4, T6 pass, demonstrated by actual command output (not claimed).
2. A pause mid-dictation of ≥3 s loses zero words and does not end the session (T1b, T3).
3. Live partials observable in `state.json` while audio plays (T3).
4. Only the daemon's typed output reaches the target — Rev 2: live partial text plus commits (§4.2quater); nothing typed while toggled off (the `listening` gates on partial and commit paths are unchanged).
5. Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use.
6. `voicectl toggle/start/stop/status/quit` all work; daemon runs as a systemd user service, starts un-armed (not listening) and **un-loaded** (~0 VRAM until first arm, §4.2bis), auto-restarts on failure.
7. Everything committed to git; README documents: install, hotkey snippet, feedback surfaces, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode.
8. No network access needed at runtime (models cached by install).
9. After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM, verified via `nvidia-smi`) and a later arm reloads it; the teardown is bounded (completes in seconds, no 90 s hang).
10. **Lite mode (§4.2ter):** `voicectl toggle-lite` arms in lite mode using ONLY `lite_model` (the large model never loads — verified ~half the VRAM of normal mode on `nvidia-smi`); `voicectl toggle` arms in normal mode; switching between them costs one bounded reload; `status` and `state.json` report `mode`; lite uses its own shorter `post_speech_silence_duration` (the silence gate is the perceived bottleneck — §4.2ter) so it is observably snappier end-to-end, not just faster at transcription; both modes honor the graceful drain (§4.2 #2).
11. **Streaming (§4.2quater):** while speaking, words are typed into the focused window continuously (≥1 update/500 ms, T8a); partials and commits revise in place with MINIMAL backspacing — only the diverging suffix after the longest common prefix is ever rewound, never the whole tail (T8a/T8b); a mid-paragraph fragment never starts with a capital nor ends with a spurious period (T8c); Backspace mid-fragment cancels it — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only behavior.
12. **Cancel fallback:** with evdev unavailable, `voicectl cancel` performs the same rewind over the socket (T8e) and the daemon logs the listener failure once at arm.
13. **Bulk text (§4.2sexies):** with `delivery="bulk-text"`, every recognition update is visible in the focused field with no character-typing fallback; corrections replace verified owned text in one visible edit and unchanged results emit zero edits; any takeover, refusal, or unknown outcome stops delivery without retries or post-stop writes; `voicectl session [--copy]` recovers the last nonempty session; graduation to the shipped default requires the G3 verified matrix plus the G6 throughput evidence — until then the mode is opt-in and its claims are reported as unverified.

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
| Streaming revision corrupts text if the user moves the cursor mid-utterance | any non-Backspace keypress freezes the tail (§4.2quater rule 5); rewind assumes 1 char/keystroke with cursor at end of typed text — documented assumption, window narrowed by the freeze rule |
| `initial_prompt`/`initial_prompt_realtime` are constructor-static in RealtimeSTT 1.0.2 (verified) | child updates them between utterances (small local patch); on failure degrade to context-free decoding + log, never crash |
| Backspace semantics differ per app (terminals, editors) | cancel fires only while armed AND a tail is pending; idempotent; compensation is by subtraction; falls back to `voicectl cancel` keybind |
| Revision flicker (rewind/retype storms) | minimal-diff (longest-common-prefix) revision: backspace only the diverging suffix, never the whole tail (§4.2quater rule 1); rewinds persistence-debounced (≥2 s of sustained divergence; otherwise extend-only); no trailing space while tentative |
| evdev listener misses keyboards / permission loss | fail-safe: log once at arm, keybind (`voicectl cancel`) keeps working; `[cancel].devices` override for odd setups |
| Bulk paste silently refused/transformed by a target (terminals escape bytes; chat editors fold large pastes into placeholders) | §4.2sexies: acceptance is never inferred from transport success; `refused`/`unknown` disarms with one reason; G3 per-field matrix; `insert-only` rows never run as full dictation |
| Clipboard-manager interference (history watchers, multi-format offers, PRIMARY selection) | §4.2sexies R.6: clipboard-free routes preferred; strict preservation contract; adapter unavailable rather than clobbering; G4 gate |
| "Pasted Backspace bytes as bulk delete" assumption | DISPROVEN 2026-11-20 (paste-lab: 0x08 arrives as a space in Ghostty) — range replacement must use a real editing mechanism (§4.2sexies R.2/R.3) |
| Terminal IM support is insert-only at best (foot/kitty silently drop `delete_surrounding_text` and never send `surrounding_text`; ghostty 1.3.1 delivers nothing over IM at all) | §4.2sexies R.2 matrix: corrections in terminals ride the cooperating-editor seam, NEVER IM delete; `insert-only` rows never run as full dictation; retest ghostty on version bump |
| Seat IM slot is exclusive (`zwp_input_method_v2`): voice-typing and a user IME (fcitx5) cannot both hold the seat | handle the `unavailable` event by reporting `delivery_state=unsupported` with one reason — never displace or disable the user's IME |
| Protocol caps a single commit at 4000 bytes (`commit_string`) | corrections larger than one commit must chunk without violating the one-edit rule, else refuse with `delivery_reason`; covered at G2 |

**Known defects (2026-11-18 triage — bugs, no spec change needed; pipeline bugfix candidates):**
- `ydotoold_client` opened SOCK_STREAM against ydotoold's SOCK_DGRAM socket → EVERY connection since f0d8d0a (2026-10-31) failed with Errno 91 and degraded to per-burst CLI spawns (56 journal warnings/week). Fix exists: branch `fix/ydotoold-datagram` (commit 33321c6, 11 tests; packing proven byte-identical to the real CLI by two independent captures). MERGE + add the 6 ms press→release contact gap (protocol finding: CLI gaps every event; socket path currently does not).
- Cancel compensation assumes one physical Backspace = one character (auto-repeat violates it) → under-compensation manufactures belief-desync.
- Cancel-suppression window latched and dropped finals 4× in the week of 2026-11-12..18 ("missing/repeated sections") — window latch timing needs investigation.

## 9. Future work (explicitly out of scope now)

- Moonshine Streaming (medium, 107 ms, beats large-v3 WER) or Voxtral-Mini-4B-Realtime as a single-model true-streaming engine once tooling matures — engine layer is isolated in `daemon.py` to keep this swap cheap.
- Hybrid engine behind the `recorder_host` event protocol: a true-streaming transducer (near-zero wobble live words) + a big batch model (large-v3 at float16) for authoritative finals — the two-tier design done right on the desktop GPU (3080 Ti). Offline bake-off harness + findings: `tools/asr-lab/` (2026-01: turbo@float16 dominates polled whisper arms; streaming transducers wobble ~10× less but trail on WER — pending real-voice clips in `tools/asr-lab/voice/`).
- Personal vocabulary biasing (hotwords / prompt seeding from a user word list) — targeted at wrong-but-plausible-word errors; pending real-voice error taxonomy from the lab clips.
- Waybar/eww overlay UI; per-app profiles; voice commands ("new line", "scratch that"); punctuation-command mode.
- Better microphone (hardware) — webcam mic is the current accuracy ceiling.

## Previous Session's Completed Tasks:
{
  "backlog": [
    {
      "type": "Phase",
      "id": "P1",
      "title": "Rev 2 — Streaming dictation + single-mode collapse",
      "status": "Complete",
      "description": "Land the Rev 2 delta on the mature Rev 1 codebase (HEAD 6b61db1): collapse to a single small.en mode (no distil-large-v3 anywhere), add phone-style streaming output (typed partials revised in place via a committed/tail state machine), Backspace-cancel with an evdev listener + voicectl fallback, rolling context prompts, deterministic textproc guards, the config/dep plumbing for all of it, and the verification + changeset-level docs. Everything outside this delta is implemented and verified (plan/006) — do not rebuild it. Read plan/007_cfc245548aec/architecture/system_context.md first: it lists PRD-vs-reality corrections (abort() does NOT discard audio; neither prompt kwarg is live-pokable in the single-model construction without a local patch) that override PRD prose.",
      "milestones": [
        {
          "type": "Milestone",
          "id": "P1.M1",
          "title": "Substrate — single-mode collapse, config schema, backspace primitive",
          "status": "Complete",
          "description": "Make the repo safe to build the streaming engine on: one recorder construction everywhere (config, cuda_check, daemon, recorder_host, ctl, prefetch, binds), the full config schema delta in one coherent edit, the evdev dependency, and the press_backspace(n) typing primitive with batched backends.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M1.T1",
              "title": "Config schema delta + evdev dependency",
              "status": "Complete",
              "description": "One coherent edit of the config surface (PRD R7): remove asr.final_model / asr.realtime_model, change lite_post_speech_silence_duration default to 0.8, add asr.context_prompt, output.streaming, and the [cancel] section; keep config.toml the self-documenting user-facing reference. Add the evdev dependency (R8).",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T1.S1",
                  "title": "config.py + config.toml schema delta (R1/R3/R4/R5/R7 fields)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: plan/007_cfc245548aec/architecture/substrate_map.md §1: AsrConfig fields at config.py:48-116 (final_model:52, realtime_model:53, lite_model:54, lite_post_speech_silence_duration:61); __post_init__ patterns — bool-for-numeric rejection config.py:86-95, string-field guard 96-102 (remove final_model/realtime_model from that tuple at :99), value validation 103-114; from_toml _overlay unknown-key rejection config.py:249-271. config.toml keys at L31-40. tests/test_config_repo_default.py:26-46 pins the EXACT key set and :53-72 asserts comment text (lite_model line mentions SUPER+ALT+D — the bind set changes in P1.M1.T2.S4, so write comments for the END state: one CTRL SUPER ALT, D toggle bind + one SUPER ALT, Backspace cancel bind).\n2. INPUT: none (leaf subtask). Target schema per PRD §4.5.\n3. LOGIC: Remove final_model/realtime_model from AsrConfig and its validation tuple. lite_post_speech_silence_duration default 0.5 -> 0.8. Add asr.context_prompt: bool = True; output.streaming: bool = True; new CancelConfig dataclass (on_backspace: bool = True, devices: list[str] = field(default_factory=list)) + VoiceTypingConfig.cancel field + _overlay(CancelConfig, 'cancel') in from_toml. Extend __post_init__ validation to new fields following the existing patterns exactly (bools reject non-bool; devices must be a list of str; numeric pattern for none — no new numerics). Update config.toml: delete the two removed keys, set 0.8 with the comment from PRD §4.5 (endpointer only delays COMMIT under streaming; 0.5 razor-snappy, 1.0 near-zero cuts), add context_prompt / streaming / [cancel] each with a self-documenting comment. Update tests/test_config.py (removed-field asserts 43-44/75-76/109; new cases: type guards, partial-table overlay, unknown-key rejection for new fields) and tests/test_config_repo_default.py (key set, 0.8 default, comment assertions aligned to the end-state binds).\n4. OUTPUT: VoiceTypingConfig exposing cfg.asr.context_prompt, cfg.output.streaming, cfg.cancel.on_backspace, cfg.cancel.devices, with final_model/realtime_model gone — consumed by P1.M1.T2.S2 (kwargs), P1.M2.T5 (context_prompt), P1.M2.T6 (streaming flag), P1.M2.T7.S2 ([cancel]).\n5. DOCS: [Mode A] config.toml IS the user-facing reference — every new/removed/default-changed key gets its comment updated in this subtask. Do not create separate docs work.",
                  "prd_selectors": [
                    "h2.3/h3.7",
                    "h2.3/h3.4",
                    "h2.3/h3.3"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T1.S2",
                  "title": "Add evdev dependency (uv add + lock)",
                  "status": "Complete",
                  "story_points": 0.5,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §6: pyproject [project] dependencies at :9-13; uv.lock exists; venv Python 3.12.10. external_deps.md §1: PyPI 'evdev' 1.9.3, requires-python >=3.11 — compatible. evdev NOT currently importable in .venv (probe).\n2. INPUT: current pyproject.toml dependency list.\n3. LOGIC: Run `/home/dustin/.local/bin/uv add evdev` (full path per PRD §5 alias warning; wrap in timeout 120). Verify: uv.lock diff contains evdev; `timeout 30 .venv/bin/python -c 'import evdev; print(evdev.__version__)'` succeeds. No source imports yet — the import lands with the listener in P1.M2.T7.S2. AGENTS.md: no daemon runs, no pytest needed for this subtask.\n4. OUTPUT: pyproject.toml + uv.lock with evdev; import evdev available to P1.M2.T7.S2.\n5. DOCS: none — dependency manifest only (README surface handled by the final docs task P1.M3.T10.S1).",
                  "prd_selectors": [
                    "h2.4",
                    "h2.3/h3.4"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M1.T2",
              "title": "Single-mode collapse across cuda_check, daemon, recorder_host, ctl, prefetch, binds",
              "status": "Complete",
              "description": "Delete the normal/two-model construction everywhere (PRD R1): the former lite construction (single lite_model, use_main_model_for_realtime=True, lite silence duration) becomes THE path. Decision recorded in system_context.md: status/state.json keep 'mode' as constant 'lite'.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S1",
                  "title": "cuda_check single-model contract",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §2: cuda_check.py CUDA_DEFAULTS:46-52 (device/compute_type/final_model=distil-large-v3/realtime_model=small.en), CPU_FALLBACK:54-59 (final=small.en, realtime=tiny.en), resolve_device_and_models:114-130 returns the 4-key dict; _main() VERDICT print :135-165. Consumers of the dict keys (daemon.py:144-197, recorder_host.py:681-714 ready payload, ctl.py status) are rewritten in P1.M1.T2.S2 — between the two subtasks those consumers reference removed keys: intended transient, do not paper over it; keep THIS subtask's own tests green (focused: `timeout 600 .venv/bin/pytest tests/test_config.py -k 'defaults or cuda' -q` plus new focused cuda_check tests).\n2. INPUT: P1.M1.T1.S1 schema (lite_model is the only model field).\n3. LOGIC: Collapse to a single-model contract: resolve_device_and_models returns {device, compute_type, model} — CUDA: {cuda, float16, 'small.en'} (the cfg default lite_model); CPU fallback: {cpu, int8, 'tiny.en'} (existing lite fallback logic). Update CUDA_DEFAULTS/CPU_FALLBACK dicts, docstrings, and the _main() CLI VERDICT print (it names the models — user-facing CLI output). Update tests that pin the old dict shape (test_daemon.py:2747/2813-2849 CPU_FALLBACK mapping asserts, test_config.py:66-77 defaults-parity test) — the parity test pins AsrConfig defaults == CUDA_DEFAULTS, so update it to pin lite_model + the new 3-key shape.\n4. OUTPUT: resolve_device_and_models() -> {device, compute_type, model}, consumed by P1.M1.T2.S2 (daemon._resolve_device_config + cfg_to_kwargs + recorder_host ready payload + ctl display).\n5. DOCS: [Mode A] cuda_check.py module docstring + _main() printed output (CLI is user-facing). Rides with the work.",
                  "prd_selectors": [
                    "h2.3/h3.6",
                    "h2.3/h3.3"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S2",
                  "title": "daemon.py + recorder_host.py mode collapse",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S1",
                    "P1.M1.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: daemon_control_map.md §1 (full map): cfg_to_kwargs daemon.py:158-215 (lite pre-kwargs 184-193, common kwargs 194-203, _FIXED_KWARGS:100-114 with use_main_model_for_realtime:False @101, lite overrides 205-214 incl. lite_post_speech_silence_duration @213); _load_host:710-805 (switch_mode branch 748-754); self._mode:656/778/1039/1632; start_lite:1441-1451; toggle/toggle_lite:1458-1516; _load_recorder alias:700-708; dispatch start-lite/toggle-lite:1989-2013; status_snapshot model keys:1641-1642; build_recorder/_construct lite= daemon.py:285-345 + recorder_host.py:458-478; RecorderHost mode param recorder_host.py:103-125/427. Test doubles to reuse: test_daemon.py:466-632 (_FakeHost/_fake_host_factory), 2859-2867 (_make_lazy_daemon).\n2. INPUT: P1.M1.T1.S1 schema; P1.M1.T2.S1 {device, compute_type, model} resolve contract.\n3. LOGIC: cfg_to_kwargs: the current lite branch becomes the ONLY branch — model=realtime_model_type=resolved['model'], use_main_model_for_realtime=True, post_speech_silence_duration=cfg.asr.lite_post_speech_silence_duration; delete the normal branch, the lite pre-kwargs override block, and the use_main_model_for_realtime entry in _FIXED_KWARGS. Delete self._mode, the mode-switch reload logic, _load_recorder alias, start_lite/toggle_lite methods, and the start-lite/toggle-lite dispatch cases; _load_host() builds the single construction unconditionally; toggle/start arm it, stop disarms. RecorderHost: drop the mode param (spawn-time single construction). status/state.json DECISION: keep 'mode' as constant 'lite' (feedback.set_mode('lite') at arm; §4.6 schema stays stable; ctl.py rendering untouched). status_snapshot: replace final_model/realtime_model keys with the single model. Rewrite/delete the mode/toggle_lite/start_lite/switch test family (full list in daemon_control_map.md §6: test_daemon.py ~25 tests incl. cfg_to_kwargs lite variants 138-313 and mode-switch 2964-4060; test_control_socket.py:131; test_recorder_host.py lite-flag tests; test_voicectl.py:75) into single-path equivalents (single kwargs test, toggle arms single construction, status mode constant). Implicit TDD: rewrite tests first.\n4. OUTPUT: single-path daemon+host — toggle/start arm the small.en single-model recorder; status {'ok':true,...,'mode':'lite'}; consumed by P1.M1.T2.S3/S4, P1.M2.T5/T6/T7, P1.M3.\n5. DOCS: [Mode A] voice_typing/daemon.py + voice_typing/recorder_host.py module docstrings — drop all two-mode prose. Rides with the work.",
                  "prd_selectors": [
                    "h2.3/h3.1",
                    "h2.3/h3.2",
                    "h2.3/h3.3",
                    "h2.3/h3.6",
                    "h2.3/h3.8"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S3",
                  "title": "ctl.py command surface (drop lite commands)",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: daemon_control_map.md §4: ctl.py:37 _COMMANDS = (toggle, start, stop, status, quit, toggle-lite, start-lite); _EX_USAGE=64 :39; _build_parser epilog ~:158-165 lists all subcommands; main() validates cmd not in _COMMANDS -> exit 64 :174-183; arm cmds routed via _send_command_with_loading_hint; format_result prints 'mode: {mode}' :69/:90 and 'models: {final} + {realtime}' :96 (the models line dies with the removed status keys from P1.M1.T2.S2).\n2. INPUT: P1.M1.T2.S2 daemon dispatch (start-lite/toggle-lite gone server-side; status_snapshot without final_model/realtime_model).\n3. LOGIC: _COMMANDS -> ('toggle','start','stop','status','quit') (cancel is ADDED by P1.M2.T7.S1 — do not add it here); update module docstring, epilog, and the positional help string; format_result: drop the models line, keep the mode line. Update tests/test_voicectl.py (command-list tests :62/:75, format tests) and tests/test_control_socket.py lite-command tests (:131/:143 — rewrite to single-path + keep mode-in-status assert).\n4. OUTPUT: voicectl surface = 5 commands; consumed by P1.M2.T7.S1 which appends 'cancel' (final list 6).\n5. DOCS: [Mode A] ctl.py module docstring + --help/epilog text (explicitly named in PRD R1). Rides with the work.",
                  "prd_selectors": [
                    "h2.3/h3.10",
                    "h2.3/h3.3"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S4",
                  "title": "Prefetch slim-down, bind collapse, ACCEPTANCE #10 rewrite",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T1.S1",
                    "P1.M1.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §3/§8/§10: prefetch.py CORE_REPOS:36-40 (distil-large-v3 + small.en + tiny.en) and OPTIONAL_REPOS turbo :43-47, invoked only by install.sh:100-104; hypr-binds.conf binds :57 (CTRL SUPER ALT, D -> toggle) and :59 (SUPER ALT, D -> toggle-lite) with header docs :1-55; tests/ACCEPTANCE.md row 10 hardcodes the 0.5 default and two-mode claims; install.sh usage lines 205-210 mention toggle-lite.\n2. INPUT: P1.M1.T1.S1 (config.toml comments describe the end-state binds); P1.M1.T2.S2 (single-mode daemon).\n3. LOGIC: prefetch.py: CORE_REPOS = small.en + tiny.en ONLY (tiny.en stays — it is the CPU fallback), delete the distil entry and the OPTIONAL turbo entry + its _main() handling; update module docstring. hypr-binds.conf: delete :59, keep the single toggle bind :57; rewrite header comments to the end state (one mode; the SUPER ALT, Backspace cancel bind is ADDED by P1.M2.T7.S1 — leave a placeholder comment). install.sh: printed usage drops toggle-lite/start-lite and the lite bind mention (prefetch output shrinks automatically via prefetch.py). tests/ACCEPTANCE.md: rewrite row #10 to the PRD §5 form (single-model arming only — small.en sole model, no large-model worker, ~half old VRAM, drain unchanged) and amend row #4 (typed output = live partials plus commits). Keep rows #1-#3, #5-#9.\n4. OUTPUT: prefetch = 2 models; one toggle bind; acceptance table matches Rev 2 for rows #4/#10 (rows #11/#12 land with P1.M3.T9.S1).\n5. DOCS: [Mode A] prefetch.py docstring, hypr-binds.conf comments, install.sh usage lines, tests/ACCEPTANCE.md rows #4/#10 — all named in PRD §7 Mode A list. Rides with the work.",
                  "prd_selectors": [
                    "h2.4",
                    "h2.3/h3.12",
                    "h2.3/h3.3",
                    "h2.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M1.T3",
              "title": "press_backspace(n) typing primitive (R2)",
              "status": "Complete",
              "description": "Add press_backspace(n: int) -> None to the TypingBackend ABC and every backend, batched so ~80 chars rewind in <150 ms, with the same auto-fallback contract as type_text on the wtype wrapper.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T3.S1",
                  "title": "ABC + batched wtype/ydotool/null implementations + fallback",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §5: TypingBackend ABC :45-60 (single abstract type_text); WtypeBackend :63-72 (subprocess.run(['wtype','--',text], check=True)); YdotoolBackend :75-83 (['ydotool','type','--key-delay','2','--',text]); NullBackend :86-89; _WtypeWithFallback :92-127 (catches (CalledProcessError, OSError), retries ONCE on fallback); make_backend :130-148. external_deps.md §2-§4: wtype -k repeats within ONE invocation (man synopsis + env -i parse probe — no usage error, fails only at Wayland connect); ydotool key takes repeated '14:1 14:0' pairs with -d ms; KEY_BACKSPACE=14. Tests pin exact argv (test_typing_backends.py:89/:122) with a no-real-subprocess guard :274.\n2. INPUT: the existing ABC and backend classes above.\n3. LOGIC: Add abstract press_backspace(n: int) -> None. WtypeBackend: ONE subprocess.run(['wtype'] + ['-k','Backspace']*n, check=True) — never spawn per keystroke (80 spawns blows the <150 ms budget); n<=0 returns immediately without spawning. YdotoolBackend: ONE subprocess.run(['ydotool','key','-d','1'] + ['14:1','14:0']*n, check=True). NullBackend: no-op. _WtypeWithFallback.press_backspace: same catch/retry-once-fallback contract as type_text. Update tests/test_typing_backends.py: exact argv pins for both backends, n=0/negative no-op (no subprocess), single-invocation batching for n=80 (assert ONE subprocess.run call), fallback ordering, abstract-ness. Mock subprocess as the existing _Recorder fake does — no real keystrokes ever.\n4. OUTPUT: TypingBackend.press_backspace contract consumed by P1.M2.T6 (revise/commit rewinds), P1.M2.T7.S1 (cancel rewind), and mirrored by the T8 RecordingTypingBackend double.\n5. DOCS: none beyond docstrings — internal primitive (README streaming section lands with P1.M3.T10.S1).",
                  "prd_selectors": [
                    "h2.3/h3.5",
                    "h2.3/h3.4"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M2",
          "title": "Streaming engine — state machine, cancel, context prompt, guards",
          "status": "Complete",
          "description": "The core Rev 2 feature work on top of the substrate: textproc guards, the committed/tail streaming state machine with freeze rules and the rollback hatch, the Backspace-cancel path (socket + evdev), and the rolling context prompt made dynamic in the recorder child.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M2.T4",
              "title": "Deterministic textproc guards (R6)",
              "status": "Complete",
              "description": "New pure functions alongside clean() (unchanged): casing guard and period guard applied at typing time on the streaming path.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T4.S1",
                  "title": "Casing + period guard pure functions",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §6: textproc.py clean():26-69 (pure; _TRAILING_PUNCT :19; returns None for min_chars/blocklist rejections; never appends space); 21 existing tests in tests/test_textproc.py — clean() must remain byte-identical in behavior.\n2. INPUT: none (leaf, pure functions).\n3. LOGIC: Add a pure function alongside clean(), e.g. apply_streaming_guards(committed: str, fragment: str) -> str: (a) casing guard — if committed (rstripped of whitespace) does not end with a terminal '.' '!' '?', lowercase the fragment's first alphabetic character's word (first word's first cased char); (b) period guard — if the casing guard fired (we joined mid-sentence) and the fragment (rstripped) ends with '.', strip exactly one trailing '.'. Signature naming is a suggestion; it must stay pure and unit-testable. Unit tests: mid-sentence vs after-terminal cases, fragment already lowercase, fragment ending '...', only-one-period-stripped, empty/edge inputs.\n4. OUTPUT: apply_streaming_guards consumed by P1.M2.T6.S1 — applied to every typed fragment (partial deltas AND commit retypes).\n5. DOCS: none — internal (README tuning notes land with P1.M3.T10.S1 per PRD R6).",
                  "prd_selectors": [
                    "h2.3/h3.9",
                    "h2.3/h3.4"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M2.T5",
              "title": "Rolling context prompt (R5)",
              "status": "Complete",
              "description": "Condition every decode on the committed text back to the last sentence boundary (~200-token cap): child-side dynamic prompt mechanism (RealtimeSTT 1.0.2's prompts are constructor-static — see research), plus daemon-side computation and shipping over cmd_q.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T5.S1",
                  "title": "Child-side dynamic prompt mechanism + capability probe + degrade",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S1",
                    "P1.M1.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE (CRITICAL — overrides PRD prose): realtimestt_internals.md: installed RealtimeSTT 1.0.2 confirmed. initial_prompt (finals) is baked into TranscriptionEngineConfig in the WORKER SUBPROCESS at worker start (installed core/transcription.py:93-107); the worker pipe protocol (audio, language, use_prompt) carries no prompt updates. initial_prompt_realtime is live-pokable ONLY via recorder.realtime_transcription_model.config.initial_prompt (base.py:163-166 reads per call) — but our single-model construction (use_main_model_for_realtime=True, from P1.M1.T2.S2) routes realtime through that SAME worker, so NEITHER plain attribute poke works. recorder_host.py seams: child command loop :549-554 (blocks in text(); the _abort_handler side-thread :517-524 is the pattern for a prompt watcher); build_recorder :458-478.\n2. INPUT: P1.M1.T1.S1 cfg.asr.context_prompt flag; P1.M1.T2.S2 single-mode child (build_recorder signature without lite).\n3. LOGIC: Add ('prompt', {'text': str}) to the child's cmd_q handling, applied between utterances (mirror the _abort_handler watcher-thread pattern if the main loop is blocked in text()). Dynamic mechanism, in preference order: (a) a fork-inherited shared value (multiprocessing.Array ~2 KB) + a monkeypatch applied in the child BEFORE AudioToTextRecorder construction that wraps the worker-side engine's transcribe (installed transcription_engines/base.py — prompt is read from self.config per call) to read from the shared value; Linux fork start method carries both the patch and the shared value into the worker process. (b) startup capability probe verifies the patch actually took effect (e.g. a sentinel round-trip or engine-config inspection); if the probe FAILS: degrade to context-free decoding and log ONCE — never crash, never wedge the child. Gate everything on cfg.asr.context_prompt (false = never patch, never ship). Report dynamic-vs-degraded status to the daemon via evt_q (new event, e.g. ('prompt_mode', {'dynamic': bool})). Unit tests with a fake recorder (copy tests/test_recorder_host.py patterns): prompt command applied to the poke seam, degrade path logs once and keeps decoding, context_prompt=false disables entirely. No CUDA loads in unit tests (monkeypatch build_recorder).\n4. OUTPUT: recorder_host applies a prompt string to BOTH partial and final decodes when dynamic mode is active, else degrades+logs; consumed by P1.M2.T5.S2 (daemon ships prompts) and asserted by P1.M3.T8.S1 (assert d).\n5. DOCS: none beyond code comments/docstrings — config.toml context_prompt comment already landed in P1.M1.T1.S1.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.6",
                    "h2.7"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T5.S2",
                  "title": "Daemon-side prompt computation + commit-time refresh",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M2.T5.S1",
                    "P1.M2.T6.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: daemon_control_map.md §2: daemon->child commands ride cmd_q via RecorderHost methods (recorder_host.py:19-22: arm/disarm/text/shutdown — P1.M2.T5.S1 adds 'prompt'); the daemon owns the committed string once P1.M2.T6.S2's engine advances it at commits.\n2. INPUT: P1.M2.T5.S1's ('prompt', {'text'}) mechanism + ('prompt_mode', {'dynamic'}) status; P1.M2.T6.S2's engine commit checkpoint (engine.committed + its on_commit hook).\n3. LOGIC: Daemon computes the prompt from engine.committed: take the text after the LAST '.'/'!'/'?'; cap at ~200 tokens (Whisper's ~224-token budget — code constant, approximate tokens by whitespace words). Ship to the child on arm and refresh after every commit advance (subscribe to the engine's on_commit hook from P1.M2.T6.S2). If the child reported dynamic=false (or degraded), skip shipping entirely and log once at arm. Unit tests with the _FakeHost double: prompt shipped at arm and after each commit; cap enforced; degrade skips shipping.\n4. OUTPUT: end-to-end rolling context prompt; asserted by P1.M3.T8.S1 (assert d — child decodes carry committed context back to the last sentence boundary).\n5. DOCS: none beyond docstrings — config.toml comment landed in P1.M1.T1.S1.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M2.T6",
              "title": "Streaming output state machine in the daemon (R3 — the heavy task)",
              "status": "Complete",
              "description": "While armed with output.streaming=true (default), type partials live and revise in place: per-session committed/tail state, delta typing with rate-limited rewinds, the commit correction pass, stranded-tail and user-typing freezes, and the output.streaming=false rollback hatch (Rev 1 path kept intact).",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T6.S1",
                  "title": "StreamingOutput core — partial path (diff/extend/revise, rate limit, guards, feedback mirror)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S1",
                    "P1.M1.T3.S1",
                    "P1.M2.T4.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: daemon_control_map.md §2: partials are delivered on the evt_q reader thread to VoiceTypingDaemon._on_partial daemon.py:1094-1103 (today: feedback.update_partial + latency only — this is THE seam); feedback.update_partial is already throttled >=10 Hz (feedback.py:74-76/:109-120). Test-double pattern: test_daemon.py:466-632 _FakeHost/_StubRecorder/_FakeBackend + _make_lazy_daemon :2859-2867 with mic_prober=_ok_probe.\n2. INPUT: P1.M1.T3.S1 backend.press_backspace(n); P1.M2.T4.S1 apply_streaming_guards(committed, fragment); P1.M1.T1.S1 cfg.output.streaming.\n3. LOGIC: New engine (daemon process — e.g. class StreamingOutput in daemon.py or a small sibling module): state committed:str='', tail:str='', frozen:bool, _last_full_rewind_ts. API: on_partial(text) -> None, freeze(reason), reset_boundary(), plus accessors for tail/committed (consumed by cancel + prompt). on_partial: if frozen or streaming disabled -> current behavior (feedback mirror only). Else diff against tail: text extends tail -> type only the delta (guards applied to the delta fragment; NO trailing space while tentative); text revises it -> press_backspace(len(revised_chars)) then type the corrected tail, with FULL rewinds rate-limited >=300 ms apart (code constant, not config — a wobble cannot flicker; if rate-limited, keep the current tail this cycle). Mirror tail into feedback.update_partial on every event. Pure-python unit tests with _FakeBackend (copy the daemon test-double pattern; no CUDA, no mic): extend types delta-only, revise rewinds+retypes, rate-limit suppresses the second full rewind inside 300 ms, no trailing space while tentative, frozen suppresses typing but keeps the mirror.\n4. OUTPUT: StreamingOutput.on_partial + tail/committed accessors — wired into the daemon by P1.M2.T6.S2; freeze API extended by P1.M2.T6.S3; tail consumed by P1.M2.T7.S1 (cancel rewind max(len(tail)-1,0)).\n5. DOCS: none beyond docstrings — the daemon docstring streaming section lands with P1.M2.T6.S2; config.toml streaming comment landed in P1.M1.T1.S1.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.8",
                    "h2.3/h3.9"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T6.S2",
                  "title": "Commit correction pass + rollback hatch + daemon wiring",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M2.T6.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: daemon_control_map.md §2: on_final daemon.py:980-1040 — listening gate :982, _on_final_lock serialization :988, textproc.clean :989 (None => rejected), payload = cleaned + ' ' if append_space :994, backend.type_text(payload) :996, feedback.record_final :1000. §3: the drain machinery (_request_stop:1105-1130, _begin_drain:1131-1140, _complete_drain:1142-1160) lets a final land before disarm — DO NOT regress it; it is consumed as-is by the streaming commit path.\n2. INPUT: P1.M2.T6.S1 StreamingOutput (tail/committed/frozen); P1.M2.T5.S1 prompt mechanism availability (hook called, wiring by P1.M2.T5.S2).\n3. LOGIC: Branch on_final on cfg.output.streaming. TRUE (default): correction pass — cleaned = textproc.clean(text); listening gate unchanged (:982); if rejected (None): FREEZE the tail as-is (no rewind, no typing; next utterance starts a fresh tail at the next boundary — committed unchanged); else: if cleaned differs from the typed tail -> press_backspace(len(tail)) + type(guarded final); apply append_space per config; committed += final + (space if append_space); tail = ''; fire an on_commit callback (engine API — P1.M2.T5.S2 subscribes to refresh the context prompt). feedback.record_final(cleaned) unchanged (existing behavior of writing finals back into 'partial' carries over). FALSE (rollback hatch): the EXACT current path (type_text(cleaned + ' ') once per final, partials to state file only) — keep the Rev 1 code intact behind the branch; this is the regression escape hatch, not dead code. Wire _on_partial daemon.py:1094-1103 -> engine.on_partial. Unit tests (fake backend + fake final stream, pure-python): differing commit rewinds exactly len(tail) then types final + trailing space; identical commit advances checkpoint silently; rejected final freezes tail; streaming=false exercises the Rev 1 path verbatim; drain mid-speech still lets the commit land. Daemon docstring gains the streaming section.\n4. OUTPUT: end-to-end streaming daemon on partials+finals with the rollback hatch; consumed by P1.M2.T5.S2 (commit hook), P1.M2.T6.S3, P1.M2.T7, P1.M3.T8.\n5. DOCS: [Mode A] daemon.py module docstring gains the §4.2quater streaming section (config.toml streaming comment landed in P1.M1.T1.S1). Rides with the work.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.1",
                    "h2.3/h3.7",
                    "h2.3/h3.9"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T6.S3",
                  "title": "Freeze rules — stranded tail, user typing, utterance boundary",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M2.T6.S1",
                    "P1.M2.T6.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: daemon_control_map.md §3: _drain_timeout watchdog daemon.py:1162-1176 (fires _safe_abort when a final is stuck in text(); _safe_abort skips abort unless _text_in_flight :1400-1428); _handle_dead_host daemon.py:893-940 (child death -> host None, listening cleared, phase 'unloaded'). PRD R3 rules 4-5: a stranded tail FREEZES (stays on screen, never deleted — the only deliberate deletion is cancel); any non-Backspace keypress freezes the tail and suppresses revision until the next utterance boundary (boundary = a commit landing, a cancel completing, or disarm).\n2. INPUT: P1.M2.T6.S1 engine frozen flag/reset_boundary; P1.M2.T6.S2 commit path (boundary events).\n3. LOGIC: (1) Stranded tail: hook _drain_timeout and _handle_dead_host to engine.freeze_stranded() — stop revising, NEVER rewind (typed text stays exactly as last shown). (2) User typing: engine.on_user_key() — freeze the pending tail + suppress all further partial typing for that utterance (feedback mirror keeps showing the frozen tail); un-freeze at the next boundary (commit / cancel reset / disarm — rearm engine state at each _arm). Unit tests: drain-timeout -> tail frozen not rewound; dead-host -> same; synthetic non-Backspace key mid-tail -> subsequent partials type nothing until a commit lands; boundary resets cleanly.\n4. OUTPUT: freeze API (freeze_stranded, on_user_key, reset semantics) consumed by P1.M2.T7.S2 (evdev feeds key events here); asserted by P1.M3.T8.S2 (asserts f/g).\n5. DOCS: none beyond docstrings — internal rules; README assumption note lands with P1.M3.T10.S1.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.1",
                    "h2.7"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M2.T7",
              "title": "Backspace-cancel — socket command, daemon semantics, evdev listener (R4)",
              "status": "Complete",
              "description": "The only path that deliberately deletes typed text: control-socket cancel + voicectl cancel + a passive evdev listener that triggers on physical Backspace presses while a tail is pending, with the keybind fallback and log-once failure handling.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T7.S1",
                  "title": "cancel: control socket + recorder abort/discard + ctl + keybind + install usage",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T2.S3",
                    "P1.M1.T3.S1",
                    "P1.M2.T6.S1",
                    "P1.M2.T6.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE (overrides PRD R4 prose): daemon_control_map.md §3 — RecorderHost.abort() (recorder_host.py:237-246) does NOT discard buffered audio; discard is _clear_recorder_audio (:586-620), currently called only on DISARM (:549-554); the abort path emits a SENTINEL ('final', ...) via _run_text_and_emit_final (~:623) so host.text() never wedges. daemon_control_map.md §4 — ControlServer._dispatch daemon.py:1957-2020 ('stop' @2014 is the template; _arm_response shapes :1940-1955); ctl.py:37 _COMMANDS + epilog (post P1.M1.T2.S3: five commands).\n2. INPUT: P1.M2.T6.S1 tail state (rewind max(len(tail)-1, 0)); P1.M2.T6.S3 freeze semantics; P1.M1.T2.S3 command surface.\n3. LOGIC: (a) recorder_host: a cancel-flavored abort that (i) sets abort_event (unblocks text()), (ii) clears the child's buffered audio via _clear_recorder_audio so NO late commit can land, and (iii) marks the sentinel final so the daemon can recognize and DROP it (no typing, no record_final) — extend the abort path or add a ('cancel',{}) child command; keep the plain abort path (drain watchdog) behavior unchanged. (b) daemon cancel(): if a tail is pending -> backend.press_backspace(max(len(tail)-1, 0)) (the physical keystroke already deleted one — compensate by subtraction, never re-type), trigger the child cancel/abort+discard, reset the engine to a fresh tail at the current cursor (committed unchanged — the fragment is GONE, not committed), keep listening; response {'ok':true,'listening':true}. No pending tail -> no-op response (idempotent — further Backspaces are plain user edits, never compensated). (c) daemon _dispatch: add 'cancel' case. (d) ctl.py: add 'cancel' to _COMMANDS/epilog/help (final list: toggle, start, stop, status, quit, cancel). (e) hypr-binds.conf: add `bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel` + comment (fallback when evdev cannot open a keyboard). (f) install.sh: usage line gains cancel + the Backspace bind mention (R8). Tests: control-socket cancel dispatch + response shape, idempotence, sentinel-final suppression, buffered-audio discard (fake recorder), ctl command list.\n4. OUTPUT: socket-level cancel consumed by P1.M2.T7.S2 (evdev trigger) and asserted by P1.M3.T8.S2 (assert e).\n5. DOCS: [Mode A] ctl.py docstring/--help, hypr-binds.conf comment for the new bind, install.sh printed usage — all named in PRD §7. Rides with the work.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.10",
                    "h2.3/h3.12"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T7.S2",
                  "title": "evdev passive listener thread + synthetic parser tests",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S2",
                    "P1.M2.T7.S1",
                    "P1.M2.T6.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: external_deps.md §1: evdev 1.9.3 (py>=3.11; installed by P1.M1.T1.S2); API — list_devices(), InputDevice(path) (O_RDWR|O_NONBLOCK; PermissionError/FileNotFoundError on bad nodes), capabilities() EV_KEY+KEY_BACKSPACE filter, read_loop() InputEvent (EV_KEY value 1=press, 0=release, 2=autorepeat — ignore 2), read_loop does NOT grab (EVIOCGRAB is opt-in via grab() — NEVER call it), one-reader-thread-per-device or selectors on fileno(); user already in group input (verified) — no permission changes. PRD R4/§4.2quater: gated by [cancel].on_backspace; [cancel].devices overrides enumeration; failure logged ONCE at arm, not per retry.\n2. INPUT: P1.M1.T1.S2 (import evdev available); P1.M1.T1.S1 cfg.cancel.{on_backspace, devices}; P1.M2.T7.S1 daemon cancel action; P1.M2.T6.S3 engine.on_user_key freeze hook.\n3. LOGIC: Daemon-process listener, started at arm when cfg.cancel.on_backspace (false -> never started; socket cancel still works): enumerate target nodes — explicit cfg.cancel.devices if non-empty else auto (list_devices() filtered by capabilities exposing KEY_BACKSPACE); open each passively (no grab); per-device reader threads: KEY_BACKSPACE press (value==1) while armed AND tail pending -> trigger the cancel path from P1.M2.T7.S1; ANY other key press -> engine.on_user_key() (user-typing freeze). Failure to open/enumerate -> log ONCE at arm with the voicectl-cancel fallback pointer. Structure the event interpretation as a PURE function over synthetic InputEvent-like values so unit tests need no real keyboard: parse press vs release vs autorepeat, Backspace vs non-Backspace, multi-device dispatch, device-enumeration filter (fake device list). Real-Backspace behavior stays in the T5 manual smoke (README first-run, P1.M3.T10.S1). AGENTS.md: any probe of /dev/input under timeout; never run the daemon foreground — unit tests use synthetic events only.\n4. OUTPUT: passive cancel trigger wired to cancel + freeze; asserted by P1.M3.T8.S2 (asserts e/f via synthetic events).\n5. DOCS: none beyond code comments — config.toml [cancel] comments landed in P1.M1.T1.S1; hypr-binds comment landed in P1.M2.T7.S1.",
                  "prd_selectors": [
                    "h2.3/h3.4",
                    "h2.3/h3.12",
                    "h2.7"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M3",
          "title": "Verification & changeset-level documentation",
          "status": "Complete",
          "description": "Prove the delta: the new T8 streaming E2E suite, the existing-suite adjustments (idle/GPU shell tests, acceptance evidence rows), and the final Mode B documentation sweep that makes README + install usage describe the Rev 2 product.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M3.T8",
              "title": "T8 — tests/test_streaming.py streaming E2E (no mic, no real keystrokes)",
              "status": "Complete",
              "description": "Heavy CUDA suite (AGENTS.md: inner timeout 600, harness timeout above it; run the single file, never the whole suite) with a RecordingTypingBackend double and WAV fixtures, asserting PRD §6 T8 (a)-(g).",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M3.T8.S1",
                  "title": "Harness + RecordingTypingBackend + asserts a/b/d",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M2.T6.S2",
                    "P1.M2.T5.S2",
                    "P1.M1.T3.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: PRD §6 T8 + tests inventory in substrate_map.md §13: tests/test_feed_audio.py is the model for real-model offline feeding (use_microphone=False + feed_audio with real-time pacing, fuzzy >=80% token matching for espeak fixtures); WAV fixtures generated by tests/make_test_audio.sh into tests/out/ (utt_simple/pause/punct/multi). AGENTS.md: heavy CUDA — `timeout 600 .venv/bin/pytest tests/test_streaming.py -q` with the harness timeout set ABOVE 600; never foreground the daemon; skip cleanly when fixtures/deps absent (copy test_feed_audio.py's skip guards).\n2. INPUT: P1.M2.T6.S2 streaming daemon (partial + commit paths); P1.M2.T5.S2 prompt shipping (+ P1.M2.T5.S1's dynamic/degraded report); P1.M1.T3.S1 backend ABC (type_text + press_backspace).\n3. LOGIC: Build tests/test_streaming.py: a RecordingTypingBackend test double recording (method, arg, timestamp) for type_text/press_backspace — no real keystrokes ever; drive the daemon (or daemon-equivalent wiring) with the lite-style single-model recorder child fed WAVs via feed_audio. Asserts: (a) typing deltas arrive >=1 per 500 ms while speech streams, and ONLY the delta when a partial extends the tail; (b) a differing commit rewinds exactly the tail length then types the final text + trailing space; (d) the child's decodes carry initial_prompt = committed text back to the last sentence boundary, capped — assert via the child log/kwargs report from P1.M2.T5.S1's mechanism; when the child reported degraded, assert the degrade-log instead (per system_context.md correction 2).\n4. OUTPUT: the reusable harness (double + feeding + timing capture) consumed by P1.M3.T8.S2.\n5. DOCS: none — test code.",
                  "prd_selectors": [
                    "h2.5",
                    "h2.3/h3.4",
                    "h2.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M3.T8.S2",
                  "title": "Asserts c/e/f/g — pause-join, cancel, key-freeze, stranded tail",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T8.S1",
                    "P1.M2.T7.S1",
                    "P1.M2.T7.S2",
                    "P1.M2.T6.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: PRD §6 T8 (c)/(e)/(f)/(g); system_context.md corrections 1-2 (cancel must drop buffered audio + suppress the sentinel final; prompt asserts conditional on dynamic mode). AGENTS.md heavy-CUDA discipline as in P1.M3.T8.S1.\n2. INPUT: P1.M3.T8.S1 harness; P1.M2.T7.S1 socket cancel + child discard; P1.M2.T7.S2 evdev parser (synthetic events); P1.M2.T6.S3 freeze rules; utt_pause.wav fixture (3 s internal silence).\n3. LOGIC: Extend tests/test_streaming.py: (c) a sentence split by a 3 s pause joins into ONE coherent commit — no mid-sentence capital, no spurious trailing period (context prompt + P1.M2.T4.S1 guards); (e) cancel with a pending tail -> press_backspace(len(tail)-1), buffered audio dropped (NO late commit lands afterwards), listening stays on; a second cancel is a no-op; (f) a synthetic non-Backspace key with a pending tail -> tail frozen, no further revision keystrokes that utterance; (g) forced drain-timeout -> tail frozen on screen, not rewound.\n4. OUTPUT: T8 complete — the evidence for acceptance row #11 (recorded into tests/ACCEPTANCE.md by P1.M3.T9.S1).\n5. DOCS: none — test code.",
                  "prd_selectors": [
                    "h2.5",
                    "h2.3/h3.4",
                    "h2.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M3.T9",
              "title": "Existing-suite adjustments + acceptance evidence rows",
              "status": "Complete",
              "description": "Fold the old T7 mode assertions into the single-model world, widen the VRAM expectation, update the shell GPU suite, and write acceptance rows #4/#10/#11/#12 against actual evidence (PRD §4/§5).",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M3.T9.S1",
                  "title": "test_idle_and_gpu.sh + test_feed_audio.py adjustments + ACCEPTANCE.md rows",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T2.S2",
                    "P1.M2.T7.S1",
                    "P1.M3.T8.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §10/§13: tests/test_idle_and_gpu.sh T7 mode-switch roundtrip at :535-578 (polls `voicectl status | grep '^mode: lite'`); T6 armed VRAM assertion ~1-5 GB (single small.en is ~0.5-3 GB — PRD §4 says widen accordingly); tests/test_feed_audio.py lite-vs-normal comparative tests at :653/:679 (normal mode is gone); tests/ACCEPTANCE.md rows listed in substrate_map.md §10. AGENTS.md: the shell suite takes 5-8 min and refuses to start if the unit is running — give the harness timeout 900, stop the unit first, never interrupt mid-run.\n2. INPUT: P1.M1.T2.S2 (single-mode paths everywhere); P1.M2.T7.S1 (cancel in the voicectl surface); P1.M3.T8.S2 (T8 evidence to point rows at).\n3. LOGIC: test_idle_and_gpu.sh: delete the mode-switch roundtrip section (:535-578); single-model assertions in its place — exactly ONE model resident (no large-model worker), armed VRAM widened to ~0.5-3 GB, drain still honored; the old T7 >=70% fuzzy-accuracy assertion now lives in tests/test_streaming.py (verify it exists from P1.M3.T8, else add). test_feed_audio.py: rewrite the lite-vs-normal comparisons (:653/:679) as single-construction asserts (one model resident; finals still >=70% fuzzy). tests/ACCEPTANCE.md: amend #4 (typed = live partials + commits; nothing typed while off), rewrite #10 (single-model arming only — small.en sole model, ~half old VRAM via nvidia-smi, drain unchanged), ADD #11 (streaming: >=1 update/500 ms; in-place commits; no mid-paragraph capitals/spurious periods; Backspace-cancel; stranded fragments freeze; streaming=false restores Rev 1) and #12 (evdev-unavailable fallback: voicectl cancel performs the same rewind; listener failure logged once at arm), each pointing at its T8/shell evidence.\n4. OUTPUT: all suites green under the single-mode + streaming world; acceptance table rows #4/#10/#11/#12 match the PRD §5 delta.\n5. DOCS: [Mode A] tests/ACCEPTANCE.md rows — named in PRD §7 Mode A list. Rides with the work.",
                  "prd_selectors": [
                    "h2.5",
                    "h2.6",
                    "h2.3/h3.3"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M3.T10",
              "title": "Sync changeset-level documentation",
              "status": "Complete",
              "description": "Mode B final sweep (PRD §7): make README.md and install.sh printed usage describe the Rev 2 product end-to-end — one mode + streaming as THE behavior, Backspace-cancel + fallback bind, updated config tuning table, troubleshooting additions, first-run Backspace check, and zero residual two-mode/tmux prose.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M3.T10.S1",
                  "title": "README end-to-end Rev 2 sync + residual-reference sweep",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S1",
                    "P1.M1.T1.S2",
                    "P1.M1.T2.S1",
                    "P1.M1.T2.S2",
                    "P1.M1.T2.S3",
                    "P1.M1.T2.S4",
                    "P1.M1.T3.S1",
                    "P1.M2.T4.S1",
                    "P1.M2.T5.S1",
                    "P1.M2.T5.S2",
                    "P1.M2.T6.S1",
                    "P1.M2.T6.S2",
                    "P1.M2.T6.S3",
                    "P1.M2.T7.S1",
                    "P1.M2.T7.S2",
                    "P1.M3.T8.S1",
                    "P1.M3.T8.S2",
                    "P1.M3.T9.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: substrate_map.md §12 README inventory (380 lines): two-mode/lite/toggle-lite hits at L79, L100, L104, L109, L116, L119, L123-125 (lite_post_speech_silence_duration 0.5 text — now 0.8), L125, L139, L143, L161, L168, L322, L337; tmux/status.sh: ZERO grep hits (verify again, do not assume); section heads at Requirements L14 / Install L22 / First run L48 / Hotkey L77 / Lite mode L116 / Feedback surfaces L133 / Configuration L147 / Troubleshooting L227 / Logs L284 / Model lifecycle L330. install.sh usage lines 205-210 (final state after P1.M2.T7.S1: toggle|start|stop|status|quit|cancel + both binds).\n2. INPUT: ALL implementing subtasks (see dependencies) — the shipped behavior: single small.en mode, streaming typed partials + in-place commits, streaming=false hatch, Backspace-cancel (evdev + SUPER ALT,Backspace fallback bind), [cancel]/streaming/context_prompt config, 0.8 silence default, prefetch = small.en + tiny.en.\n3. LOGIC: README.md end-to-end rewrite of the affected sections: one mode + streaming output as THE behavior (not a mode); delete the Lite-mode section + ⚡ prefix semantics + all toggle-lite/two-model prose; Hotkey section = single toggle bind + Backspace-cancel bind (+ note evdev fallback); First run gains the T5 manual Backspace check (press Backspace mid-fragment -> fragment disappears, dictation stays armed); Feedback surfaces section matches state.json/toasts/voicectl status (mode constant 'lite'); Configuration table updated (lite_post_speech_silence_duration 0.8 semantics, streaming, context_prompt, [cancel] on_backspace/devices); Troubleshooting additions: backspace-in-terminals caveat (per-app Backspace semantics), evdev permission (input group / [cancel].devices override); Model lifecycle VRAM numbers halved. Sweep install.sh printed usage to the final command list; sweep any residual tmux/status.sh/final_model/realtime_model/toggle-lite references repo-wide (grep; expected none — verify). Verify every README claim against the code as landed; no new features.\n4. OUTPUT: README.md + install.sh docs consistent with the shipped Rev 2 changeset; closes the breakdown.\n5. DOCS: this IS the Mode B changeset-level docs task (PRD §7) — it depends on every implementing subtask by design.",
                  "prd_selectors": [
                    "h2.6",
                    "h2.0",
                    "h2.1",
                    "h2.3",
                    "h2.3/h3.7",
                    "h2.3/h3.8",
                    "h2.3/h3.10",
                    "h2.3/h3.12",
                    "h2.4",
                    "h2.7"
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}

## Previous Session's Architecture Research:
Check plan/007_cfc245548aec/architecture/ for existing research that may still apply.

## Instructions:
1. **DIFF ANALYSIS**: Identify what ACTUALLY changed (count lines/words)
2. **SIZE CHECK**: Small diff = small PRD. Do NOT inflate scope.
3. **SCOPE DELTA**: Create a PRD focusing ONLY on:
   - New features/requirements added
   - Modified requirements (note what changed from original)
   - Removed requirements (note for awareness, but don't create tasks)
   - **DOCUMENTATION IMPACT (two modes, mirror the breakdown agent):**
     - **Mode A — doc-with-work:** For each new/modified requirement, name the specific doc file(s) it touches (e.g. `docs/CONFIGURATION.md`, JSDoc on the exported symbol). These updates ride WITH the implementing work — note them as a sub-bullet under the requirement, do NOT make them standalone tasks.
     - **Mode B — changeset-level docs:** If the delta has cross-cutting doc implications (e.g. `README.md` feature blurbs, top-level capability lists, architecture overviews that only make sense once the whole change is in place), call this out explicitly as a final "Sync changeset-level documentation" requirement depending on all the above. The breakdown agent will turn it into a final Task.
     - **Do NOT silently omit docs.** Even if a change looks small, state the Mode A docs it touches (or explicitly \"none\") and decide whether Mode B applies. A delta that ships coherent code with a stale README has failed.
4. **REFERENCE COMPLETED WORK**: The previous session implemented the original PRD.
   - Reference existing implementations rather than re-implementing
   - If a modification affects completed work, note which files/functions need updates
5. **LEVERAGE PRIOR RESEARCH**: Check plan/007_cfc245548aec/architecture/ for research that applies
   - Don't duplicate research that's already been done
6. **OUTPUT**: Write the delta PRD to `plan/008_a47116bb2b79/delta_prd.md`

**Remember: Minimal change = minimal PRD. Do NOT over-engineer.**

### PREVIOUS SESSION AWARENESS
**CRITICAL**: Documentation from previous sessions exists and takes PRIORITY over web searches.

Previous session directory: plan/007_cfc245548aec

When researching for this delta session:
1. **FIRST** check `plan/007_cfc245548aec/architecture/` for existing research
2. **FIRST** check `plan/007_cfc245548aec/docs/` for implementation notes
3. Reference completed work from previous sessions instead of re-researching
4. Build upon existing patterns and decisions
5. Only do web searches for genuinely NEW topics not covered in prior sessions
