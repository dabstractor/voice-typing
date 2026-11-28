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

## Current PRD:
# PRD: Fully-Local Voice Typing for Linux/Wayland — "voice-typing"

**Status:** Implementation requirements, not a record of release acceptance. No further product interview is required.

**Current output scope (supersedes Rev 4):** System-wide dictation sends individual keystrokes to the focused window. Stream mode sends partials and finals; block mode sends only accepted finals, still as keystrokes. Do not promise a system-wide atomic paste, probe alternate registers, or select an application-specific output path from compositor, terminal, or tmux focus. The existing `output.backend` key selects only a low-level keyboard injector or disables injection; it is not an application integration mechanism. Legacy `backend="tmux"` loads as `"ydotool"` for compatibility, with no tmux operations.

**Next implementation round:** Pi and Neovim own native insertion through explicit editor sessions (§4.8.1), not daemon-selected application backends. Retire the public `output.delivery="bulk-text"` experiment from the shipped path in that round; for a config explicitly requesting it, report a migration error rather than silently converting a no-keystroke configuration into keyboard injection. Keep the Rev 4 experiments and evidence as lab/reference material, not product requirements. Preserve plain dictation and explicit user-initiated `voicectl session --copy`; routine dictation in either path must not stage transcripts on the system clipboard.

**Rev 2 (streaming dictation):** adds §4.2quater — phone-style typed partials revised in place, rolling context prompting, deterministic casing/punctuation guards, and Backspace-cancel. The small model (`small.en`) is the ONLY mode — the former big-model normal mode is REMOVED (user decision; §1). This revokes the Rev 1 decision that only finalized text is typed (§1).

**Rev 3 (halt + accounting hardening, 2026-10 — supersedes conflicting statements below):** four user decisions after the October mass-deletion/wedge reports: (1) **any real user keypress while armed DISARMS dictation entirely** ("HALT") — the Rev 2 per-utterance freeze is demoted to opt-in legacy (`cancel.keypress_action = "freeze"`); modifier-only presses are not keypresses, and a 1.5 s grace after arming ignores the hotkey's own chord. (2) **Stop is IMMEDIATE by default** — disarm now, drop the racing final, never wait on the decoder ("all the way, no exceptions"); the Rev 2 graceful drain is opt-in (`asr.graceful_stop = true`). (3) **Rewind accounting is a hard invariant**: a rewind may never delete more characters than the engine typed since the checkpoint (clamped + journaled per rewind); dropped finals inside the cancel-suppression window reset the utterance boundary so the tail can never accumulate across utterances (the "backspaces way farther than it ever typed" bug). (3b) **Session-boundary audio purge**: the child's buffered audio MUST be cleared at EVERY disarm AND at every arm — the stop's abort unblocks the decoder after the disarm clear, and whatever the aborted decode re-stashes (frames/last_frames) must not survive into the next session's first decode (the stale-replay "previous utterance types itself after re-arm" bug). (3c) **Continuation separator**: an interrupted session (immediate stop, keypress-disarm — the commit that types the inter-utterance space never ran) strands its tail mid-screen with no trailing space; the NEXT typed fragment MUST lead with exactly one space, typed lazily (only when dictation actually resumes — never left dangling), and that synthesized separator is invisible to prefix-diffing (decoder partials never contain it) while still being deleted by any rewind that covers it. Without this, every interrupted session fuses its continuation onto the stranded text (the "skipped spaces" bug). (3d) **Injector pacing**: synthesized keystrokes MUST be spaced (~12 ms/char) and every injector process spawn MUST be serialized behind a single lock with a minimum inter-spawn floor (~25 ms), on BOTH backends — the injector always exits 0 while the compositor's input path silently coalesces/drops sub-2 ms press/release bursts under sustained dictation (the "missing characters, worse the longer I use it" report; single-keystroke payloads like a lone space are dropped first, so separators MUST ride inside the next text payload, never as their own spawn). On this machine the primary backend is ydotool (persistent ydotoold uinput device — no per-spawn virtual-keyboard/keymap churn, which loses events the same way). (4) **Robustness invariants promoted to spec**: the child abort handler MUST be supervised (a dead one wedged every later stop/cancel into timeouts — the missing-`import time` crash); `voicectl` commands MUST be bounded by a socket timeout (default 10 s, `VOICECTL_TIMEOUT`); the evdev listener MUST survive device death (WARN + periodic re-enumeration); The documented socket-independent stop is `systemctl --user stop voice-typing` for installations using the supplied service; no shortcut is shipped. Streaming is the default; explicit block arms suppress on-screen partials and type only accepted finals.

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
<checkout>/
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

**Historical Rev 1 commands (superseded by §4.2quater):** `voicectl toggle-lite` / `voicectl start-lite` armed in lite mode, `voicectl toggle` / `start` armed in normal mode, and `voicectl stop` disarmed either. Desktop shortcuts are user-owned (§4.10).

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

Ordinary starts use only the daemon's own rolling dictation. An opt-in integration can supply the initial prompt from existing editor text (§4.8.1); later utterances return to the normal rolling source.

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

### 4.2sexies Legacy bulk text delivery experiment (Rev 4 reference, superseded)

**Archived contract for the opt-in experiment.** The requirements below describe the old lab scope only. They do not apply to generic dictation or the supported editor integrations; see the current output scope above and §4.8.1.

**R.1 The intended experience for the experiment.**
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

### 4.3 System-wide keyboard injection (`typing_backends.py`)

Interface: `type_text(text: str) -> None` (send individual keys, including when called once with an entire final) plus `press_backspace(n: int) -> None` (Rev 2, §4.2quater — delete exactly n characters for in-place revision). The existing `output.backend` setting selects the injector, default **`wtype`**. No application detection, pane routing, or paste occurs here.

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
delivery = "stream-edit"             # existing keyboard-delivery default; native editor sessions do not use this selector

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

#### 4.8.1 Editor integrations — contextual dictation with pinned delivery (proposed)

**Product contract.** Pi's built-in prompt and Neovim (including Pi's external-editor draft) get the same three actions: **Start**, **Stop** (finish the current utterance), and **Cancel** (drop pending audio, end dictation, leave completed edits alone). A single already-running `voice-typing` daemon owns mic, VAD, lazy model load, and decoding. The invoking editor supplies a short pre-caret seed and owns **all** insertion for that session. Only accepted finals are inserted in v1, one native undoable edit per utterance. No global typing, clipboard fallback, terminal scraping, paste emulation, draft submission, file save, or automatic handoff. Plain daemon dictation is unchanged when no integration owns the mic.

##### A. Shared context and optional context-only CLI

- At explicit Start, snapshot the actual insertion point and send at most the newest 4 KiB of text **before** it, across lines if needed, truncated on a UTF-8 code-point boundary. Do not read selection contents, text after the caret, chat history, terminal output, or other buffers for the seed. No editor mutation to gather it. Empty/whitespace-only is valid and unseeded. Adapters expose a `send_context` option (default true for eligible targets); false sends an empty seed and still uses pinned delivery. Ineligible/private targets refuse Start visibly; never fall back to global delivery.
- Preserve the context-only API for non-integrated callers: `{"cmd":"start-context","context":"...","mode":"block"}` (optional `mode`: `block`/`stream`; default from config), and `voicectl start|start-block|start-stream --context-stdin` (not argv). This is the existing focus-based delivery mode with a decode seed, **not** a safe editor integration. Reject while arming/listening/draining. Distinct commands ensure an old daemon rejects the request instead of silently arming without context. On timeout/old daemon, report the error; do not retry or fall back.
- Trim the seed to the existing model prompt budget using the newest suffix, **without** cutting it at the last sentence boundary. Apply it to both partial and final decode lanes before capture; use the existing recorder, not an extra model per integration. A `context_seeded:true` response requires a bounded acknowledgement from the child that the prompt was installed on the active lanes (a best-effort queue put is not confirmation). For empty, disabled, or unavailable prompting, start unseeded only when the child is known to have a clear prompt (or no prompt executor), and return `context_seeded:false` plus `context_reason:"empty"|"disabled"|"unavailable"`. If the child state is unknown, fail without arming. Never wait for the child under the daemon control lock, and fence late acknowledgements by reservation/generation.
- Keep the seed through the first accepted utterance (rejected text doesn't advance it), then use normal rolling context from accepted finals; for the context-only command, keep existing delivery-specific commit rules. For native delivery, use only this session's accepted finals as the rolling source; never put the seed into the committed-text or formatting pipeline. On user edit, cursor move, or target change **end the session and require explicit Start** to capture fresh context. No implicit rebase or live reseed in v1. For a legacy context-only session, cancel retains the original seed if no utterance has committed and the existing cancel behavior keeps capture armed. Clear the seed on failed arm or session end, and guarantee a later arm never inherits it. A bounded drain may finish the already-started utterance with its original context.
- Seeds are ephemeral: no echo in errors/replies, logs (including DEBUG), status, state file, recovery, clipboard, or persistent client files. Only recognizer output can become transcript, even if it happens to repeat seed words. Expose fixed reason codes, counts, and ids rather than dumping raw requests or exception data carrying text.

##### B. Native wire protocol v1 (same owner-only Unix socket)

The adapters use the socket directly, not a subprocess per utterance. UTF-8 newline-delimited JSON objects, with a **32 KiB wire limit per request and live event** (including newline); enforce byte limits while reading, before unbounded buffering, and reject invalid UTF-8, malformed frames, invalid types, oversized fields, or unsupported protocol before arming. Every successful native Start reserves an exclusive connection-owned session; status/stop/quit remain available, but all other start/toggle/cancel attempts (including legacy ones) return busy while the native reservation exists. Native Start likewise returns busy if **any** other arm is loading, listening, or draining. `voicectl stop` is an emergency graceful stop of the active session using its existing delivery route; `quit` shuts down. A start rejected as busy never queues for later. Keep existing one-request commands and status/recovery behavior backward-compatible outside native mode.

| Direction | Frame | Meaning |
|---|---|---|
| Editor → daemon, first frame | `{"cmd":"editor-start","version":1,"id":"<UUIDv4>","context":"..."}` | The client generates and remembers the opaque session id before connecting. Reject an id already active or retained. No target name/path, editor buffer contents beyond the seed, or output-mode option. |
| Daemon → editor | `{"ok":true,"event":"starting","id":"..."}` | Reservation acquired; capture not open yet. A failed initial request instead gets `{"ok":false,"error":"<code>"}` and EOF. Native error codes: `invalid_request`, `too_large`, `unsupported_version`, `busy`, `duplicate_id`. An old daemon's unknown-command reply means unsupported. |
| Daemon → editor | `{"event":"listening","id":"...","context_seeded":true}` | Arm succeeded; include `context_reason` if unseeded. Must precede any final. |
| Editor → daemon / reply | `{"cmd":"ping","id":"..."}` / `{"event":"pong","id":"..."}` | Client sends every 2 s while reserved, including during load and drain. No renewal after local invalidation. |
| Daemon → editor | `{"event":"final","id":"...","seq":1,"text":"..."}` | Accepted, cleaned recognition text (no editor padding); start at seq 1, monotonic, one offer outstanding at a time. |
| Editor → daemon | `{"cmd":"applied","id":"...","seq":1}` | Sent only after verifying a native edit and its new caret/checkpoint; no resend of offers or automatic replay on any error. |
| Editor → daemon | `{"cmd":"stop","id":"..."}` (also `cancel` or `lost`) | `stop` drains, retaining the editor as sink; `cancel` invalidates and aborts; `lost` invalidates and drains for recovery only. |
| Daemon → editor | `{"event":"finishing","id":"..."}` | Capture winding down after a graceful stop (including idle auto-stop); ordered before any final accepted during that drain. |
| Daemon → editor | `{"event":"ended","id":"...","reason":"<code>","recoverable":true}` | Last frame then EOF; recoverable means some accepted text is not known applied and is retained. Reasons: `stopped`, `idle`, `cancelled`, `target_lost`, `disconnected`, `timeout`, `delivery_failed`, `load_failed`, `shutdown`. |

- Every post-start frame is scoped to the owner connection and same id. Accept an `applied` only for the outstanding seq, advance the contiguous acknowledgement watermark once, and ignore an exact duplicate of the last ACK; other unexpected ids/seqs/commands terminate safely with `delivery_failed`. Clients never insert duplicate, skipped, stale, or out-of-generation offers. A final outside Listening/Finishing, seq other than the next expected one, unknown event, failed edit, uncertain edit outcome, or timeout invalidates locally first, warns, and abandons delivery, never retries. Cancel/Lost immediately disable local delivery even before the transport processes the command; a transport close or abnormal terminal event invalidates any not-yet-executed UI callback. Terminal transition is idempotent even if Stop, loss, exit, and EOF race.
- Cap Start (including model load/priming) at 30 s; active lease expires at 6 s without valid ping/pong on the respective side; ACK deadline is 5 s from offer write. Use monotonic time and bounded socket writes (at most 2 s). Existing bounded ASR drain applies after Stop/loss; allow up to 5 s for outstanding ACKs **after** the ASR drain, total, then end. Clients close on expired deadline. EOF, client failure, or expired lease is loss, never permission to send text anywhere else. The daemon must be able to service EOF/stop/lost/heartbeat during cold load; a cancelled reservation cannot resume/arm when the worker returns. Check reservation before opening capture and fence every recorder event by arm generation/utterance identity.
- Native sessions bypass `StreamingOutput`, bulk target acquisition, focus injectors, evdev typing/cancel guards, and transcript-bearing desktop/state feedback. Use only lifecycle status/warnings, not native transcript in generic status/state or `voicectl session`. Daemon-side ASR callbacks run the existing final cleaning/filtering, deduplicate by recorder generation/utterance id (reject missing/stale identity), record the accepted final for recovery, and enqueue it without socket I/O under the control lock or on the recorder reader thread. No drain waiting/child abort under that lock. Pending live delivery is capped at 8 finals (including the outstanding offer) and 4 KiB UTF-8 per final; if a limit is exceeded, do not truncate and insert—switch once to recovery-only drain with `delivery_failed`. The daemon may update rolling context from accepted finals without waiting for a socket ACK; app-side checkpoint validation governs all writes.
- Stop (including idle auto-stop) accepts at most the already-in-flight final and allows queued offers to settle **only** while the original target remains valid. Stop during startup aborts the reservation without opening capture. Cancel invalidates before sending and aborts in-flight audio; no new recognition accepted or inserted after cancellation, previously accepted/unconfirmed text may still be recovered. Loss/disconnect first revokes delivery, then gracefully drains at most the already-in-flight utterance into recovery only; loss while starting aborts without capture. Shutdown/host failure clean up without promising a recoverable drain. A successful native session uses the same media duck/un-duck and idle unload policies as other sessions.

##### C. Target validity, edit semantics, and warnings

- The adapter pins an editor instance, draft/buffer identity, insertion point, and edit revision at Start. Observe editor-local input/lifecycle events and invalidate **before** delegating actions that can move/replace/submit/close the draft or enter an external editor. Programmatic changes and lost motion must also be detected by the native events/checkpoint. Immediately before accepting a final, in one synchronous UI-thread operation, recheck the same live target, revision, mode, and caret; insert via native editing API only, verify the expected splice and new caret, and update the checkpoint before ACK. Only the adapter's own successful edit advances the checkpoint; do not suppress unrelated changes made by callbacks/plugins. If verification fails after a possible write, stop with uncertain delivery, never reapply or attempt destructive rollback.
- Moving a caret, making a manual edit (including undo/redo/history completion), switching drafts, losing the invoking editor surface/window, or entering a modal/selection/read-only state invalidates the session even if the user immediately returns. External editor open/close is always a boundary. Local invalidation is sticky for the id and occurs before sending `lost`, `cancel`, or closing the connection; queued callbacks recheck it before editing. Desktop/compositor/tmux focus is neither a routing authority nor proof of target loss: if the logical draft is still valid, output may reach only that draft, never the newly focused target.
- Insert a literal cleaned final at the caret without replacing surrounding text. Add at most one ASCII space at each splice edge: no pad for empty/whitespace adjacency, between an opening delimiter `([{` and text, or before closing punctuation `)]},.!?;:`; otherwise add one space where adjacent text would touch. Use Unicode whitespace consistently in both adapters. Caret ends after the insertion (including any padding). Example: `hello|, world` + `there` → `hello there|, world`; `hello|world` + `there` → `hello there |world`. One ordinary Undo reverses that insertion alone. Never use `setEditorText`, synthetic paste/feedkeys for transcript delivery, or whole-buffer replacement.
- Show nonblocking **Starting / Listening / Finishing** in each editor and clear on termination. Nonempty context that could not seed is a visible notice, not a reason to silently switch sinks. Target loss must show a visible warning (e.g. “Dictation stopped: draft or caret changed. Start again here. Unconfirmed text: `voicectl recover <id>`.”). Alert in the editor whenever its UI is still available, including disconnects. For a suspended/closed editor, the daemon attempts a short transcript-free warning with a recovery hint through a desktop-neutral notification backend (freedesktop notifications, e.g. `notify-send` if available). A configured desktop notifier may also be used as an optional fallback, never as a dependency. Always retain a transcript-free last abnormal end reason and recovery hint in `voicectl status` and log the same diagnostic, even if a notifier succeeds. A closed editor on a bare TTY cannot show a live popup; document that limitation. `hyprctl` is not required for native warnings. Do not claim text was definitely unapplied when an ACK may have been lost. No automatic restart, handoff, focus change, clipboard staging, or draft save. If a new Start in the other editor gets `busy` while the old session is winding down, show that and let the user retry explicitly.
- Keep native recovery in daemon memory only, separately keyed by id (reuse the R.6 bounded store machinery where practical). Retain up to two nonempty ended sessions with unacknowledged finals, at most 1 MiB UTF-8 per session including while active for the unacknowledged suffix; reclaim acknowledged text from this budget. On overflow retain the newest complete finals that fit, mark truncation (a lone oversized final may be safely clipped for recovery **only**). `{"cmd":"editor-recover","id":"..."}` on a separate one-shot connection returns `{"ok":true,"id":"...","text":"...","truncated":false,"possibly_applied":true}` for a retained id (omitting id selects latest). Text is unacknowledged accepted finals in order, joined with a single space; `possibly_applied` is true if an included final's offer write was attempted without verified ACK. A lost ACK must not turn into a second automatic insert. Return `not_found` if absent, `busy` for the active id. Bound the escaped JSON recovery reply separately (7 MiB including newline). `voicectl recover [ID]` prints only text to stdout and warns of truncation/possible duplication on stderr; never auto-inserts. Fully acknowledged or empty endings do not evict previous recovery. No durable recovery promised after daemon restart.

##### D. Required adapters and implementation boundaries

- **Linux portability (required):** Adapters depend on the editor's supported public APIs and a compatible daemon reachable at the same user's `$XDG_RUNTIME_DIR/voice-typing/control.sock`; no compositor, display server, terminal emulator, tmux, GPU vendor, distro, or systemd dependency in the editor path. Use the daemon's canonical XDG socket rule (a missing runtime directory produces a clear setup error, not a guessed `/tmp` path). Document both the actual daemon/audio prerequisites and adapter prerequisites separately. No fixed checkout, username, home/config path, editor launch command, or host-specific extension. The adapters must neither edit desktop configuration (of any syntax) nor require global hotkeys, privileged input access, `wtype`/`ydotool`, or clipboard tools. Expose editor-local actions with opt-in user-chosen mappings; offer documented non-shortcut actions so there is no required key chord. Native delivery must work with unset `DISPLAY`, `WAYLAND_DISPLAY`, and no `hyprctl`/desktop tools when the socket and editor are available.
- **Pi:** `integrations/pi/` is an opt-in TypeScript extension for upstream Pi's interactive TUI and compatible Pi-Bolt builds, not a fork-specific extension. Use the shared public UI/extension APIs and documented package resolution (no private imports or checkout-relative imports); publish the minimum versions actually verified for each. Expose editor-local Start/Stop/Cancel actions and optional `registerShortcut` mappings plus UI status/notifications. A Start invoked by a command must not replace the draft with its command text; expose an editor-native action or UI picker for invocation from a nonempty draft. Wrap the existing editor factory (or use a `CustomEditor` subclass for the stock editor), preserve normal key handling and other extensions, expose the actual editor's `getLines()`/`getCursor()` and native `insertTextAtCursor()` plus verification. Pi columns are JS string offsets; use the real line representation consistently, and fail closed wherever a collapsed paste/marker or custom editor prevents a reliable mapping rather than seed from expanded conversation text or guess the caret. Observe changes plus input/action dispatch so a submit, external-editor action (`app.editor.external`, including remaps), overlay or editor replacement cannot bypass invalidation; revoke before the action runs, not on return from the external process. Use `session_shutdown` for quit/reload/session switch and release all hooks, timers, and socket resources. Incompatible editor/mode (including a modal editor outside insert mode) must report unsupported; prove it works on stock upstream Pi and stock Pi-Bolt without a special patch or terminal-key simulation for delivery. Unsupported versions fail closed with a setup message. Installed docs: `docs/extensions.md`, `docs/keybindings.md`; example `examples/extensions/modal-editor.ts`. The local Pi source, when available, exposes the editor splice/undo in `packages/tui/src/components/editor.ts` and external action in `packages/coding-agent/src/modes/interactive/interactive-mode.ts`; validate the running Pi-Bolt surface, not just this reference checkout.
- **Neovim:** `integrations/neovim/` is an opt-in Lua plugin using a libuv Unix pipe (`vim.uv` / `vim.loop`) and scheduled UI callbacks. Expose Lua Start/Stop/Cancel functions and opt-in insert-mode `<Plug>` actions; document example mappings in standard Lua (no auto-bind and no required plugin manager). Invoke Start from a supported insert-mode action, not a command line that moves or exits the target. Start refuses non-insert mode in v1. Document the minimum Neovim version verified. Pin the current buffer and window handles, UTF-8 byte column/row and `nvim_buf_get_changedtick`; use `nvim_buf_set_text` on that buffer with exact byte offsets, the native caret API and an undo boundary proven by tests. Observe buffer edits, cursor movement, mode/window/buffer exit, and process exit (`nvim_buf_attach` plus appropriate autocmds). Recheck live handles, eligibility and tick immediately before mutation; distinguish own updates from manual/plugin mutations. Support ordinary modifiable file/text buffers including the live unsaved Pi draft; refuse special/terminal/prompt/read-only/nonmodifiable or explicitly excluded buffers. Do not edit Pi's temp file directly, add an external-editor wrapper, or save on the user's behalf. User saves/exits Neovim normally to return the draft to Pi. New dictation in either surface always requires a new Start and fresh seed.
- **Build order and ownership:** (1) `voice_typing/recorder_host.py` / `prompt_engine.py`: confirmed priming, preserve recorder generation/lifecycle; (2) `voice_typing/daemon.py` plus a small native-session/protocol module: exclusive reservation, bounded wire, delivery branch and lease/watchdog; `session_recovery.py` and `ctl.py`: recovery and context-only CLI; (3) the two adapters and shared language-neutral protocol test vectors; (4) README plus each adapter's install/uninstall, mappings, supported modes, privacy opt-out, warning/recovery examples, and version compatibility. Both adapters ship in this repo, independently installable with no daemon installer dependency. Separate repositories only if release/distribution/ownership needs justify it. Live partial writes, seamless handoff, automatic context refresh, and broad app discovery are explicitly out of scope for v1.

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
`install.sh`: `uv sync`, prefetch models, run a 5-second CUDA smoke test, install+`daemon-reload`+enable+start the unit, print CLI usage and troubleshooting commands. Idempotent. The daemon starts **not-listening** and **not-loaded** — it must never hot-mic on boot and loads no models until the first arm (§4.2bis, ~0 VRAM at idle); `voicectl start`/`toggle` arms it (the first arm each session also loads the models, ~1–3 s).

### 4.10 User-owned shortcuts

The project exposes CLI commands and opt-in editor-local actions (§4.8.1). It does not ship, install, or source desktop/compositor bindings. Users who want global shortcuts may map `voicectl toggle`, `toggle-block`, `toggle-stream`, or `cancel` in their own configuration. Document `systemctl --user stop voice-typing` as a socket-independent stop for users of the supplied systemd service, not as a required shortcut.

---

## 5. Installation

Install PortAudio with the host distro's package manager and install `uv`. From the checkout, run `./install.sh` if using the supplied systemd user service (see README for prerequisites). The installer syncs the checked-in project dependencies and prefetches the model files. CUDA is optional; use the documented CPU fallback if CUDA is unavailable. Install each editor adapter separately per §4.8.1; it uses the running daemon and must not install a second service or download a model. The machine notes in §2 are not installation requirements.

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

**Archived T9 — Rev 4 lab qualification (not an editor-integration release gate):** execute gates G1–G5 of §4.2sexies R.7 in order — G2 fake-target controller traces first, then the G3 real-field matrix (pi prompt in isolated Ghostty, a graphical editor, a browser field), G4 clipboard contract if a clipboard route is used, G5 timing on word-aligned real-voice replay. G6 (graduation/default flip) additionally requires the writing-session throughput evidence. Transport probes (`tools/paste-lab/`) support evidence but never substitute for G3/G5. No keystroke-fallback assertions from T8 apply in this mode.

**T10 — Contextual editor dictation (§4.8.1):** Run T10a–d. Use private sockets, fake ASR/events and isolated editors for automated tests; no mic, CUDA, global key injection, systemd changes, or clipboard/device rebinding. Put controllable barriers at load/seed ACK, final acceptance, edit and ACK to test races deterministically rather than with sleeps. Follow `AGENTS.md` timeouts and the daemon-suite baseline set-diff rule.

- **T10a — priming and compatibility:** Warm and cold starts use the same daemon recorder path; assert child ACK then capture, on both decode lanes, complete-sentence and multiline Unicode seeds, rejected first utterance then rolling handoff, empty/disabled/unavailable prompting, lost/late/failed priming with no late arm, and no prompt inheritance on plain re-arm. Cover context-only CLI on new/old daemon, 4 KiB/32 KiB boundaries, invalid UTF-8 and JSON, split/coalesced frames and partial EOF. A distinctive seed and distinct fake transcript prove the seed is absent from replies, logs, state, recovery, and delivery. Plain start/stop/stream/block retain their keyboard behavior outside owner sessions. Assert a plain block arm emits no partials to the injector, while its accepted final goes to the same injector as stream mode.
- **T10b — native lifecycle and recovery:** Competing editor and legacy starts in arming/listening/draining; warm/cold stop and disconnect; blocked receiver, lease/ACK timeout, wrong id/seq, duplicate/stale/identity-less finals, duplicate ACK, late callback after re-arm, exactly one bounded terminal transition, queue/byte caps, and cleanup of media/mic/ownership. Verify ordering of starting/listening/finishing/ended, one observed accepted final per offer, no transcript in general feedback, and **zero** calls to every global delivery path even on error. Verify explicit legacy `delivery="bulk-text"` config produces a migration error rather than keystrokes. Cover graceful Stop, Cancel, loss mid-utterance, loss during drain, shutdown, known acknowledged vs never-offered vs possibly applied recovery, id lookup and latest selection, truncation, and bounded retention. Simulate a native edit that completes just before the socket breaks: recovery may include it with a duplicate warning; replay never occurs.
- **T10c — each real editor with a fake socket server:** Use shared protocol vectors. Test live pre-caret capture (including unsaved/multibyte/multiline and 4 KiB boundary cases), privacy opt-out, status, unsupported targets, multiple finals with spacing and one undo per final, and no modifications outside the exact splice. Inject a final after caret movement, manual edit, undo, an edit-and-return, target switch/close, mode change, reload, and lost/duplicate/out-of-order frame; assert zero further writes and a visible warning. Prove Stop applies an eligible in-flight final while Cancel does not. Use released upstream Pi and stock Pi-Bolt in isolated PTYs to cover the mapped external-editor action (including remap), Pi submit and session switch; headless Neovim suffices for splice/undo tests, with a PTY for Insert controls and window/process exit. On both adapters run Start→final→Stop plus target loss with a non-default XDG runtime directory and without `DISPLAY`, `WAYLAND_DISPLAY`, `TMUX`, compositor helpers, injection/clipboard tools, or project paths on `PATH`. Verify in-editor warning and a transcript-free status hint when desktop notifications are unavailable. Record verified editor versions. A fake warning sink is sufficient for daemon desktop notification tests.
- **T10d — end-to-end smoke (record result, or mark hardware-dependent checks pending user run):** In Pi with real service, dictate at a mid-draft caret, Stop mid-phrase, and Undo. Start again and open Neovim via the external-editor action during a delayed final: expect loss warning, no write in either editor from that session, and recover text if accepted. Start in Neovim after unsaved manual edits, dictate and Stop; verify the insertion stays in that buffer and is not auto-saved. Close Neovim mid-dictation and check that the late final cannot land in Pi; verify warning/recovery. Restart dictation in Pi explicitly. Switch tmux panes while dictating and verify the other pane receives nothing. Verify that Pi and Neovim reused the same resident recorder on a warm sequence. The installed service is used for this opt-in smoke only; no automatic restart of the user's service.

---

## 7. Acceptance criteria (definition of done)

1. T1–T4, T6 pass, demonstrated by actual command output (not claimed).
2. A pause mid-dictation of ≥3 s loses zero words and does not end the session (T1b, T3).
3. Live partials observable in `state.json` while audio plays (T3).
4. Only the daemon's typed output reaches the target — Rev 2: live partial text plus commits (§4.2quater); nothing typed while toggled off (the `listening` gates on partial and commit paths are unchanged).
5. Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use.
6. `voicectl toggle/start/stop/status/quit` all work; daemon runs as a systemd user service, starts un-armed (not listening) and **un-loaded** (~0 VRAM until first arm, §4.2bis), auto-restarts on failure.
7. Everything committed to git; README documents: install, CLI and optional user-owned shortcuts, feedback surfaces, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode.
8. No network access needed at runtime (models cached by install).
9. After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM, verified via `nvidia-smi`) and a later arm reloads it; the teardown is bounded (completes in seconds, no 90 s hang).
10. **Lite mode (§4.2ter):** `voicectl toggle-lite` arms in lite mode using ONLY `lite_model` (the large model never loads — verified ~half the VRAM of normal mode on `nvidia-smi`); `voicectl toggle` arms in normal mode; switching between them costs one bounded reload; `status` and `state.json` report `mode`; lite uses its own shorter `post_speech_silence_duration` (the silence gate is the perceived bottleneck — §4.2ter) so it is observably snappier end-to-end, not just faster at transcription; both modes honor the graceful drain (§4.2 #2).
11. **Streaming (§4.2quater):** while speaking, words are typed into the focused window continuously (≥1 update/500 ms, T8a); partials and commits revise in place with MINIMAL backspacing — only the diverging suffix after the longest common prefix is ever rewound, never the whole tail (T8a/T8b); a mid-paragraph fragment never starts with a capital nor ends with a spurious period (T8c); Backspace mid-fragment cancels it — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only behavior.
12. **Cancel fallback:** with evdev unavailable, `voicectl cancel` performs the same rewind over the socket (T8e) and the daemon logs the listener failure once at arm.
13. **System-wide delivery:** Stream and block use the same generic key injector; block sends no partials to the target. Neither detects the application, routes to tmux, or writes the clipboard. Native one-edit insertion is only offered by explicit application integrations. Rev 4 lab results are not a graduation or release gate.
14. **Editor integrations (§4.8.1):** Both independently installable adapters use the same resident daemon, with one native undoable edit per final and no writes to any other target. Moving or losing the target stops insertion, shows a warning, and makes unconfirmed finals recoverable; a new explicit Start captures fresh context. T10a–c must pass and T10d results (including any unverified hardware acceptance) must be reported before claiming completion.

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
      "title": "Delta Rev 3/4 remainder — media ducking (D1), bulk text delivery (D2), legacy defect pipeline (D3)",
      "status": "Complete",
      "description": "Implement the three unimplemented work packages of PRD Rev 4 at HEAD 2335a9e: D1 media ducking (§4.2quinquies), D2 bulk text delivery over input-method-v2 (§4.2sexies R.1–R.8), D3 legacy defect closure (§8 triage). Everything in the delta PRD's LANDED rows (Rev 3 machinery, minimal-diff revision, compute_type) is DONE — do not re-implement. Research grounding lives in plan/008_a47116bb2b79/architecture/ (d1_ducking_seams.md, d2_bulk_delivery_map.md, d3_defects_g1_baseline.md, external_tech_notes.md). All work obeys AGENTS.md (two timeouts on every non-trivial command; never foreground the daemon; bounded scratch).",
      "milestones": [
        {
          "type": "Milestone",
          "id": "P1.M1",
          "title": "G1 regression baseline + legacy defect closure (D3)",
          "status": "Complete",
          "description": "Record the pre-change G1 baseline, then close the three §8 defects: merge fix/ydotoold-datagram + add the 6 ms socket contact gap, close the cancel auto-repeat audit, and fix the cancel-suppression latch chaining that dropped finals 4×/week.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M1.T1",
              "title": "Record the G1 regression baseline at pre-change HEAD",
              "status": "Complete",
              "description": "Run the protected pure-python suites at HEAD 2335a9e, record exact pass/fail counts and failure reasons, and classify every red against the legacy lazy-separator contract so NEW failures introduced by this delta are separable.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T1.S1",
                  "title": "Run and record the baseline suite numbers",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: numbers already measured at 2335a9e — see plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md Part A: 379 passed / 20 failed across 15 pure suites (commit 10F/22P; core 2F/32P; freeze 4F/22P; test_streaming.py 3P/4F real-model 106 s; zero_diff_rewind 3/3; all others green).\n2. INPUT: repo at 2335a9e, tree clean except plan/.\n3. LOGIC: re-run the 15 suites listed in the research doc, one file per call, `timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q` with bash-tool timeout above it (AGENTS.md discipline; NEVER run test_feed_audio/test_daemon/test_recorder_host/test_cuda_check, tests/*.sh, the daemon, or voicectl untimed). Write the durable baseline (counts + failure names + one-line reasons) to tests/G1_BASELINE.md — bounded, no transcripts.\n4. OUTPUT: committed baseline doc; numbers must match the research record (investigate any drift before any code change).\n5. DOCS: Mode A — tests/G1_BASELINE.md is the doc; nothing else changes.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.5"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T1.S2",
                  "title": "Classify reds vs the lazy-separator contract",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: all 10 commit + 2 core + 4 freeze + streaming f/g failures are legacy lazy-separator contract reds (tests encode the eager separator; HEAD defers it since 26d570b) — d3_defects_g1_baseline.md §A.1 items 1–18. test_streaming.py test_a_delta_cadence + test_b_commit_rewind_exact are NOT separator-shaped (extend/rewind cadence — possible late regression or real-model flake).\n2. INPUT: baseline from P1.M1.T1.S1.\n3. LOGIC: classify each failure (i) legacy-separator vs (ii) new/unexpected; define a pre/post re-run protocol for the two (ii) candidates (re-run before and after every D3 change to disambiguate regression vs flake). NO blanket skips, NO legacy behavior edits to fake parity.\n4. OUTPUT: classification table appended to tests/G1_BASELINE.md; the (ii) list becomes the phase's watch set.\n5. DOCS: none beyond the baseline doc.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.4",
                    "h2.5"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M1.T2",
              "title": "Merge fix/ydotoold-datagram and add the 6 ms socket contact gap",
              "status": "Complete",
              "description": "D3.1: land the SOCK_DGRAM fix (33321c6, 11 tests, clean merge per research), then add the 6 ms press→release contact gap the CLI path has and the socket path lacks, plus a journal-noise regression guard.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S1",
                  "title": "Merge fix/ydotoold-datagram onto main",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T1.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: branch = single commit 33321c6 on merge-base f0d8d0a; touches only voice_typing/ydotoold_client.py (_connect SOCK_STREAM→SOCK_DGRAM; bug site on main is ydotoold_client.py:41) + new tests/test_ydotoold_client.py (11 tests, in-process FakeYdotoold). Zero file overlap with main since f0d8d0a → clean merge (d3_defects_g1_baseline.md Part B).\n2. INPUT: baseline recorded (P1.M1.T1.S2).\n3. LOGIC: `git merge fix/ydotoold-datagram` as a normal reviewable merge (no squash); run `timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py tests/test_key_listener.py -q`; re-run the M1.T1.S2 watch set.\n4. OUTPUT: merged main with the datagram socket live; the Errno-91 CLI fallback path (typing_backends.py:138-149) goes cold.\n5. DOCS: none — commit message carries it.",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.7"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S2",
                  "title": "Add the 6 ms press→release contact gap on the socket path",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: the gap exists in NEITHER socket path — press/release are back-to-back in `_key` (ydotoold_client.py:66-72); only the CLI fallback gaps events (`ydotool key -d 6`, typing_backends.py:148). Pacing constants: _CHAR_GAP_S=0.012 (ydotoold_client.py:25), _MIN_SPAWN_GAP_S=0.025 (typing_backends.py:58).\n2. INPUT: merged socket client from P1.M1.T2.S1.\n3. LOGIC: insert ~6 ms contact time between press and release in the socket path (new constant beside _CHAR_GAP_S), keeping the 12 ms inter-char gap; extend tests/test_ydotoold_client.py to assert per-key press→release spacing ≥6 ms and inter-key ≥12 ms (mirror the existing latency test's measurement-bound style).\n4. OUTPUT: gapped socket path, suite green.\n5. DOCS: Mode A — module docstring note on the gap rationale (rides here).",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.7"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T2.S3",
                  "title": "Journal-noise regression guard (no per-burst fallback storms)",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: while broken, every backspace burst degraded to one CLI spawn + one WARNING (56/week; warning site typing_backends.py:143-144). Delta acceptance #3: assert via tests, not journal scraping.\n2. INPUT: P1.M1.T2.S2.\n3. LOGIC: unit test asserting: with a healthy datagram socket, N consecutive press_backspace calls produce ZERO CLI subprocess spawns and zero warnings; on socket death exactly ONE fallback spawn + one WARNING, then self-heal reconnect (restart coverage already exists — pin the no-storm property).\n4. OUTPUT: D3.1 closed; regression test green against recorded test doubles.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.7"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M1.T3",
              "title": "Close the cancel auto-repeat compensation audit (D3.2)",
              "status": "Complete",
              "description": "Physical Backspace auto-repeat violates one-keystroke=one-character. Listener-level filtering exists; audit the daemon-side accounting against sustained holds and close with a regression test or recorded evidence.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T3.S1",
                  "title": "Replay a sustained-Backspace hold as a regression test + audit trace",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: key_listener.py:81 drops value!=1 (autorepeat invisible by design); compensation is daemon.py:1779 `n=max(tail_len-1,0)` + press_backspace at :1781; during the paced burst OS autorepeat deletes REAL chars the daemon cannot observe (belief-desync). Existing coverage filters value-2 events (test_key_listener.py:61-65, :218-228) but NO test simulates the R extra OS-level deletions of a hold (d3_defects_g1_baseline.md Part C).\n2. INPUT: baseline + merged D3.1.\n3. LOGIC: write the hold-trace test (armed + tail in flight; press(1) + repeats(2)×R + release(0)) asserting: exactly ONE cancel; repeats never re-latch/re-stamp the suppression window; document the residual unobservable-deletion window (repeats landing during the paced burst) with its bound, in the test docstring.\n4. OUTPUT: regression test + written audit finding for S2.\n5. DOCS: Mode A — audit note in the test file docstring.",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.4"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T3.S2",
                  "title": "Mitigate or record the residual desync window",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T3.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: PRD fix rules already hold (cancel fires only while armed AND a tail is pending; idempotent; compensation by subtraction). The open question is only whether the hold window is bounded.\n2. INPUT: audit finding from P1.M1.T3.S1.\n3. LOGIC: if the audit shows unbounded desync, apply the smallest PRD-sanctioned mitigation (e.g. bound the burst so a hold past the burst is provably a user edit, documented); if bounded and correct-by-design, record the evidence and STOP — do not gold-plate (delta D3.2).\n4. OUTPUT: D3.2 closed with test or recorded evidence.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.4"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M1.T4",
              "title": "Fix the cancel-suppression window latch chaining (D3.3)",
              "status": "Complete",
              "description": "The latch re-stamps per Backspace press and drops every final inside the 5 s bound; a cancel→re-speak→cancel chain keeps dropping re-said finals with no bound — the 4×/week 'missing sections' incident. Research says NOT closed at HEAD.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M1.T4.S1",
                  "title": "Bound the suppression-window re-latch chain",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: latch at daemon.py:1788-1792 (`_cancel_suppress_final` + `_cancel_suppress_since`, refreshed per press); within the bound on_final :1158-1217 drops EVERY final; partials do NOT close the daemon latch (_touch_speech :1460-1499 lifts only the engine `_suppressed`); healthy exits: sentinel consume :1194-1197, timeout self-heal :1166-1189, fresh arm :1371-1374; every dropped final still resets the boundary :1213-1216 (KEEP this invariant). Incident occurred WITH 4640041 backstops live (d3_defects_g1_baseline.md Part D).\n2. INPUT: baseline.\n3. LOGIC: implement ONE product decision (log it in a code comment): (a) cap consecutive dropped finals per latch, or (b) close the window on genuinely-fresh speech (partial after latch with no sentinel). Keep all existing healthy-exit paths and the boundary-reset invariant unchanged.\n4. OUTPUT: bounded window; decision recorded.\n5. DOCS: Mode A — daemon cancel docstring notes the bound.",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.4"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M1.T4.S2",
                  "title": "Replay the 4× incident sequence as a regression test",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T4.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: exact 7-step scenario in d3_defects_g1_baseline.md Part D (arm → partials → Backspace#1 → sentinel LOST → re-speak → final <5 s DROPPED → Backspace#2 re-latch → ×4). Mirror the style of tests/test_daemon.py:5142 test_lost_sentinel_self_heals_after_timeout (mock host, no CUDA).\n2. INPUT: bounded window from P1.M1.T4.S1.\n3. LOGIC: daemon-level test replaying the chained sequence; assert the chain terminates (re-said finals land typed/recorded, or the window closes) and the boundary-reset invariant holds on every drop.\n4. OUTPUT: D3.3 closed with the incident pinned green.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.7",
                    "h2.3",
                    "h3.4"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M2",
          "title": "Media ducking while listening (D1, §4.2quinquies)",
          "status": "Complete",
          "description": "Best-effort AudioDucker: MPRIS pause tier + sink-volume duck tier, engaged at arm and released on every disarm path, crash-safe, never a gate on arm. Ships duck_mode=\"off\" then flips default to \"mpris\" once tests pass.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M2.T1",
              "title": "Add the [audio] config surface in lockstep",
              "status": "Complete",
              "description": "duck_mode (\"off\"|\"mpris\"|\"volume\") and duck_volume_pct (15) in config.py + config.toml, with the key-set pinning test updated 24 → 26.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T1.S1",
                  "title": "AudioConfig dataclass + config.toml table + key-set pin 24→26",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: exact recipe in plan/008_a47116bb2b79/architecture/d1_ducking_seams.md §3 — AudioConfig dataclass after CancelConfig (~config.py:216) with duck_mode guard copying keypress_action (config.py:201-206, allowed (\"off\",\"mpris\",\"volume\")) and duck_volume_pct int guard; field on VoiceTypingConfig (:341-346); \"audio\" in _KNOWN_TABLES (:337); audio=_overlay(AudioConfig,\"audio\") in from_toml (:385-391); config.toml [audio] table after [cancel] (~line 55), inline-comment style per config.toml:31-47. Key-set pin lives ONLY in tests/test_config_repo_default.py:37-63 (docstring \"24 schema keys\" line 38; verified 24 at HEAD) → 26.\n2. INPUT: none (first D1 subtask).\n3. LOGIC: TDD — extend the pin test first (audio: {duck_mode, duck_volume_pct}, docstring 24→26), add type/value guard tests beside tests/test_config.py:143-201, then implement; SHIPS duck_mode=\"off\".\n4. OUTPUT: config surface + green test_config_repo_default/test_config (run `timeout 300 .venv/bin/pytest tests/test_config_repo_default.py tests/test_config.py -q`).\n5. DOCS: Mode A — config.toml [audio] comments are the user-facing reference; ride here.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5",
                    "h3.9"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M2.T2",
              "title": "Implement the AudioDucker module (protocol + two tiers + failure discipline)",
              "status": "Complete",
              "description": "New voice_typing/audio_ducking.py: AudioDucker over an injectable backend; MPRIS tracked-pause-set tier and wpctl volume tier; every call a ≤1 s subprocess; engage/release idempotent; never blocks arm.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T2.S1",
                  "title": "AudioDucker core + backend protocol + bookkeeping",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M2.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: new module voice_typing/audio_ducking.py (only feedback.py/typing_backends.py import subprocess today — keeps the third import local); NO subprocess.run(...,timeout=) exists in voice_typing/ — copy the swallow-discipline of feedback.py:247-261 and ADD timeout (d1_ducking_seams.md §1e).\n2. INPUT: config from P1.M2.T1.S1 (duck_mode, duck_volume_pct).\n3. LOGIC: AudioDucker.engage()/release() over an injectable Backend protocol; idempotent both directions; release-without-engage = no-op; bookkeeping state = paused-player ledger (name, was Playing) and volume snapshot, consumed by the tiers. Unit tests with a fake backend in tests/test_ducking.py.\n4. OUTPUT: AudioDucker + Backend protocol for S2/S3.\n5. DOCS: Mode A — module docstring states tiers + sovereignty rules.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T2.S2",
                  "title": "MPRIS tier: tracked pause set via busctl",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M2.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: NO D-Bus libs in .venv (probed) → subprocess busctl only; exact argv forms in plan/008_a47116bb2b79/architecture/external_tech_notes.md §3 (ListNames / get-property PlaybackStatus / Pause / Play). Research FORBIDS `playerctl --all-players pause` + bare `play` (misses late players; bare play targets most-recent only) — use the tracked-pause-set design even if playerctl is used for individual ops.\n2. INPUT: Backend protocol from P1.M2.T2.S1.\n3. LOGIC: engage: enumerate org.mpris.MediaPlayer2.* names, pause each with PlaybackStatus==Playing (respect CanPause), store the exact name set. Release: resume ONLY players (a) we paused, (b) that were Playing before, (c) still Paused now (intersect stored set with fresh ListNames) — a player the user started mid-dictation is never resumed (PRD test case a). Every call `timeout` ≤1 s; failure journals ONE line.\n4. OUTPUT: MPRIS tier green against fakes (case a pinned).\n5. DOCS: none (module docstring covers).",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T2.S3",
                  "title": "Volume tier: wpctl snapshot + conditional restore",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M2.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: wpctl grammar `Volume: <float>[ MUTED]`; bare `15%` = ABSOLUTE set; @DEFAULT_AUDIO_SINK@ re-resolves per invocation → snapshot the CONCRETE sink node id at engage and restore by id (external_tech_notes.md §4).\n2. INPUT: Backend protocol from P1.M2.T2.S1.\n3. LOGIC: engage: read+store node id + float volume + mute state, then set duck_volume_pct absolute. Release: restore stored float + mute ONLY if the current volume still equals what we last set (user sovereignty — PRD test case b); skip gracefully if the node is gone. ≤1 s timeouts; one-line failure logs.\n4. OUTPUT: volume tier green against fakes (case b pinned).\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T2.S4",
                  "title": "Failure discipline: non-blocking, bounded, idempotent",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M2.T2.S2",
                    "P1.M2.T2.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: the arm toast site runs UNDER self._lock — engage must spawn a short-lived daemon thread (precedent: signal-handler spawn daemon.py:2738-2742; abort-out-of-lock discipline NEW-2, _disarm docstring :1422-1436). Ducking is an enhancement, NEVER a gate (PRD failure discipline).\n2. INPUT: both tiers from P1.M2.T2.S2 + P1.M2.T2.S3.\n3. LOGIC: engage/release wrappers that (a) never block the caller (async dispatch), (b) survive a hung backend call — a mocked 5 s sleep must not delay arm beyond bound (PRD case d), (c) stay idempotent under repeated arms (case e).\n4. OUTPUT: discipline tests green; ducker ready to wire.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M2.T3",
              "title": "Wire ducking lifecycle into the daemon + crash safety",
              "status": "Complete",
              "description": "Engage at the single arm choke point; release on every disarm path (manual, drain, idle auto-stop, HALT, quit/SIGTERM, dead-host) but NOT Backspace-cancel; ducked state field with post-crash self-heal and ExecStopPost.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T3.S1",
                  "title": "Engage/release at the arm/disarm seams (spawned, never under _lock)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M2.T2.S4"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: choke points (d1_ducking_seams.md §1): engage at the _arm() toast site daemon.py:1415 (covers every arm); release at _disarm() after :1454 (manual stop/toggle-off, drain completion :1817-1818, idle auto-stop :1871-1872, HALT :1598-1601) AND request_shutdown() after :2177 (quit + SIGTERM); cancel() :1754 must NOT release (mic stays hot); ducker ctor seam mirrors key_listener= (daemon.py:574-576/802-812), default built from cfg.audio when duck_mode!=\"off\". EDGE: _handle_dead_host (:1050) fires the stop toast without _disarm — add release there too (child death while ducked).\n2. INPUT: AudioDucker from P1.M2.T2.S4.\n3. LOGIC: spawn engage/release threads at the sites (never inline under _lock); feedback.set_ducked() from the ducker thread; PRD case (c) — release fires on every disarm path incl HALT and auto-stop — pinned via a _FakeDucker injected through a copy of _make_daemon (tests/test_daemon.py:682-700 pattern).\n4. OUTPUT: wired daemon; lifecycle cases green in tests/test_ducking.py.\n5. DOCS: Mode A — daemon.py module docstring gains the ducking note.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5",
                    "h3.1"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M2.T3.S2",
                  "title": "Crash safety: ducked flag, startup self-heal, ExecStopPost",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M2.T3.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: feedback recipe (d1_ducking_seams.md §2): \"ducked\": False in _state (feedback.py:95-109) + set_ducked() cloning set_models_loaded (:135-145), always-write, never notifies; snapshot() exposes it free. systemd unit has NO ExecStopPost today; tests/test_systemd_unit.py lockstep pattern at :94-96; install.sh seds __REPO__ in ExecStart only — verify substitution coverage before referencing a repo path in ExecStopPost.\n2. INPUT: P1.M2.T3.S1.\n3. LOGIC: state field + setter; at daemon startup, if state.json ducked==true → best-effort release (PRD case f); add ExecStopPost= best-effort restore + a unit-test assertion mirroring :94-96.\n4. OUTPUT: crash-recovery case green; systemd lockstep green.\n5. DOCS: Mode A — ExecStopPost comment in the unit explains the crash-safety rationale.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5",
                    "h3.10",
                    "h3.13"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M2.T4",
              "title": "Flip duck_mode default to mpris with evidence",
              "status": "Complete",
              "description": "PRD: ships \"off\" until implemented; default flips to \"mpris\" the round this lands, once tests pass. Capture the §4.2quinquies acceptance evidence.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M2.T4.S1",
                  "title": "Default flip + acceptance evidence",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M2.T2.S4",
                    "P1.M2.T3.S1",
                    "P1.M2.T3.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: key-set pin stays at 26 (values change, not keys); tests/test_config_repo_default.py test_repo_config_toml_equals_defaults pins the new default automatically once config.toml flips.\n2. INPUT: all D1 tests green (P1.M2.T2.*, P1.M2.T3.*).\n3. LOGIC: flip default to \"mpris\" in config.py + config.toml lockstep; run the §4.2quinquies acceptance scenarios (music→arm→pause ≤1 s→resume at stop; duck_mode=\"volume\" ducks to 15% and restores exactly; user changes never overridden; duck_mode=\"off\" byte-identical to today; journal shows engage/release lines) — scripted where possible against harmless targets, else documented operator checks with expected journal lines.\n4. OUTPUT: default \"mpris\" landed with recorded evidence.\n5. DOCS: Mode A — config.toml comment updated; README section is Mode B (P1.M7.T2), NOT here.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.5",
                    "h2.6"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M3",
          "title": "Bulk delivery controller core + config gate (D2, G2)",
          "status": "Complete",
          "description": "The paste-as-policy controller and TargetAdapter contracts, separate from StreamingOutput/typing_backends: result taxonomy, zero-diff guard, bounded queue with barriers, failure/disarm rules, the G2 fake-target trace gate, the output.delivery config gate, and the delivery status surface.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M3.T1",
              "title": "Define bulk delivery contracts (protocol, results, zero-diff guard)",
              "status": "Complete",
              "description": "New code separate from legacy: DeliveryTarget protocol (acquire/show/finalize/leave/cancel), ShowResult taxonomy, handle+revision types, units mapping, and the generalized rendered-compare zero-diff guard. No typing surface anywhere.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M3.T1.S1",
                  "title": "Contracts module: protocol + result taxonomy + zero-diff guard",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.3 contract; MUST be separate from StreamingOutput (voice_typing/streaming.py:180) and typing_backends.py — the bulk adapter MUST NOT expose type_character/press_backspace or any typing fallback (d2_bulk_delivery_map.md §3 lists the do-not-touch surface). 'Bytes sent is not applied; unknown is not delivered.'\n2. INPUT: none (first D2 code subtask).\n3. LOGIC: new voice_typing/bulk_delivery.py: DeliveryTarget Protocol (acquire → opaque handle + revision; show(session, utterance, seq, expected_revision, complete rendered span) → applied|unchanged|refused|unknown; finalize; leave; cancel), units-mapping contract (map positions to the target's own units; never slice via a lowercased/normalized copy); rendered-span equality guard — strings that render identically after the existing language/spacing guards ⇒ zero events; real case/punctuation/word differences never equal. Pure unit tests incl Unicode.\n4. OUTPUT: contracts consumed by P1.M3.T2.S1 and both adapters (M4/M5).\n5. DOCS: Mode A — module docstring carries the R.2/R.3 contract summary.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M3.T2",
              "title": "Implement the bulk controller (ordering, failure, G2 gate)",
              "status": "Complete",
              "description": "The controller between recognition events and a DeliveryTarget: bounded queue (32) with ordered barriers, newest-partial-wins, one writer/one op in flight, 250 ms deadline, disarm-on-failure with no retries, and the full G2 fake-target trace matrix.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M3.T2.S1",
                  "title": "Ordering core: bounded queue, barriers, one writer",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.5 — RecorderHost._dispatch invokes _on_partial/on_final ON the reader thread; bulk mode MUST enqueue and return (no subprocess/editor wait/display poll there or under the daemon control lock). Bounded queue default 32; overflow STOPS delivery rather than dropping a barrier; finals and boundaries are ordered barriers, never overwritten.\n2. INPUT: contracts from P1.M3.T1.S1.\n3. LOGIC: controller state machine: session generation, utterance ids, seq, expected_revision; one writer per target; one operation in flight; newest partial wins for the current utterance (superseded partials coalesce). Unit tests with an in-process fake target: append; first-word change; identical update (zero events); retraction; Unicode.\n4. OUTPUT: ordering core for P1.M3.T2.S2.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M3.T2.S2",
                  "title": "Failure handling: 250 ms deadline, disarm-on-unknown, no retries",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.5 — any unknown/refused/stalled operation (250 ms engineering deadline) disarms bulk delivery AND recording, retains recoverable recognition, reports ONE concise reason; NEVER retry an operation that may already have landed; validate deadlines in the RECEIVER so a late op cannot mutate after give-up.\n2. INPUT: P1.M3.T2.S1.\n3. LOGIC: implement deadline + result handling; unit-test: timeout-after-apply (treated unknown ⇒ disarm, no retry); held key; out-of-order results; stop + immediate re-arm; child death; focus change mid-operation. Keep three values distinct: latest recognized text, filter-accepted final, last target-CONFIRMED visible text.\n4. OUTPUT: failure-complete controller.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M3.T2.S3",
                  "title": "G2 gate: full fake-target trace matrix green + evidence record",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: G2 list is enumerated in R.7; G2 is necessary, NEVER sufficient — a G2 pass never marks a field row verified.\n2. INPUT: P1.M3.T2.S2.\n3. LOGIC: run + record the complete matrix: append; first-word change; identical update and final; retraction; Unicode; rejected/lost final; repeated cancel; timeout-after-apply; held key; out-of-order results; stop + immediate re-arm; child death; focus change mid-operation. Assert exact text/caret, bounded queue, ZERO legacy-backend calls (no type_text/press_backspace reachable in bulk mode), no duplicates, no extra writes, no post-takeover mutations. Evidence bounded in tests/.\n4. OUTPUT: G2 pass recorded as the gate artifact.\n5. DOCS: gate record file only.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.5"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M3.T3",
              "title": "output.delivery config gate + delivery status surface",
              "status": "Complete",
              "description": "Config key with the precondition triple enforced at load, plus delivery_mode/delivery_state/delivery_reason/last-confirmed-op through feedback state and voicectl status.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M3.T3.S1",
                  "title": "output.delivery key + precondition triple enforcement",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T1.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: OutputConfig is config.py:140-168; key-set pin (tests/test_config_repo_default.py:37-63) goes 26 → 27 after [audio] lands (coordinate with P1.M2.T1.S1's 24→26).\n2. INPUT: baseline P1.M1.T1.S2 (no legacy config behavior change).\n3. LOGIC: add delivery=\"stream-edit\" to OutputConfig + config.toml; enforce at load: \"bulk-text\" requires streaming=true AND graceful_stop=false AND keypress_action=\"disarm\", else a clear ValueError naming all three violated keys; default stays \"stream-edit\" (opt-in until G6); config.toml comment documents opt-in status.\n4. OUTPUT: config gate green; key-set pin at 27.\n5. DOCS: Mode A — config.toml output.delivery comment.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.9"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M3.T3.S2",
                  "title": "Delivery status surface: feedback fields + voicectl status rendering",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M3.T3.S1",
                    "P1.M3.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: additive-key recipe (d2_bulk_delivery_map.md §4): add delivery_mode, delivery_state (inactive|active|unsupported|fault), delivery_reason, last_confirmed_op to feedback _state (:92-105) with set_phase-style setters (always write, never notify; the bulk controller is the ONLY writer — never hijack `partial`); status_snapshot (daemon.py:2275-2318) additive keys (mic_*/context_prompt precedents); ctl format_result status branch (:126-171) renders delivery lines after context-prompt.\n2. INPUT: P1.M3.T3.S1 + P1.M3.T1.S1.\n3. LOGIC: TDD through the existing feedback/ctl test seams; state NEVER carries the surrounding user document; logs on the bulk path carry counts and times, not recognition text.\n4. OUTPUT: status surface consumed by M4/M6 wiring.\n5. DOCS: Mode A — feedback.py state-field docs + ctl.py status help.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.10",
                    "h3.12"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M4",
          "title": "IM-v2 primary adapter: transport, acquire, show, takeover, real-field proof",
          "status": "Complete",
          "description": "Productize the proven tools/im-lab wire client into a daemon-owned input-method-v2 adapter subprocess; implement acquire/verification, atomic insert+correct, takeover revocation; prove insert AND correct in real fields (G3 core) and refresh the field-class matrix at installed versions. Route is DECIDED — no discovery work.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M4.T1",
              "title": "Productize the IM-v2 wire transport into a daemon-owned subprocess",
              "status": "Complete",
              "description": "Evolve tools/im-lab wlwire.py + im_probe.py into voice_typing/ime/ (stdlib wire client — pywayland is NOT in the venv and stays out), with a JSONL protocol to the daemon and managed lifecycle incl. the exclusive-seat unavailable event.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M4.T1.S1",
                  "title": "Wire transport package + JSONL protocol",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: tools/im-lab/wlwire.py is a stdlib-only hand-rolled Wayland wire client (core + zwp_input_method_v2 + keyboard grab); pywayland NOT importable in the daemon .venv — wlwire lineage is the decided transport; opcode tables must match the vendored input-method-unstable-v2.xml (im-lab README:29-33); im_probe.py already speaks a JSON command socket (insert/replace/preedit/endpreedit/grab) with a 64 KiB-capped event log (d2_bulk_delivery_map.md §5).\n2. INPUT: contracts from P1.M3.T1.S1.\n3. LOGIC: move/evolve wlwire+im_probe into a voice_typing/ime/ package: JSONL request/reply protocol to the daemon (acquire/show/verify/leave + result events), capped event log, tests for opcode tables vs the XML and JSONL framing. Development MUST NOT change the operator's service/config/bindings.\n4. OUTPUT: transport package for P1.M4.T1.S2.\n5. DOCS: Mode A — package docstring carries the R.2 evidence trail (26–40 ms insert; atomic commit order; surrounding_text byte-exact; commit_string generates zero key events).",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M4.T1.S2",
                  "title": "Subprocess lifecycle: spawn/monitor/teardown + unavailable handling",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: subprocess isolation mirrors the recorder_host pattern (bounded join then killpg); the seat IM slot is EXCLUSIVE — a user IME (fcitx5) holding the seat sends `unavailable`; handle it by reporting delivery_state=unsupported with ONE reason, never displace/disable the user's IME, no auto-retry fighting it (stay unsupported until next arm). IM process crash = delivery fault, not daemon death.\n2. INPUT: transport from P1.M4.T1.S1 + status surface from P1.M3.T3.S2.\n3. LOGIC: spawn/monitor/restart policy (no unbounded retry loops), bounded teardown, delivery_state transitions wired to feedback.\n4. OUTPUT: managed ime subprocess consumed by T2/T3.\n5. DOCS: none (package docstring covers).",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.1",
                    "h2.7"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M4.T2",
              "title": "acquire + ownership verification",
              "status": "Complete",
              "description": "Bind the SPECIFIC editable field; verify via surrounding_text; fail BEFORE delivery for non-editable/password/selected/unidentified fields.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M4.T2.S1",
                  "title": "acquire(): field binding, verification, units mapping",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T1.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.3 — bind the editable FIELD, not a window/process/position; a pane/tab/inner editor can change without the window changing; verification via surrounding_text (byte-exact cursor/anchor = target-CONFIRMED text, the third distinct value of R.5); never replace a pre-existing user selection by default; adjacent user text/whitespace/formatting never touched (d2_bulk_delivery_map.md §1/§9).\n2. INPUT: managed subprocess from P1.M4.T1.S2.\n3. LOGIC: acquire() returning opaque handle + revision; per-field units mapping (UTF-8 bytes/chars/UTF-16/markers); mutation-time re-check helpers (focus/caret/selection/ownership) consumed by show(). Test against the fake wire and the GTK harness field.\n4. OUTPUT: verified acquire for P1.M4.T3.S1.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M4.T3",
              "title": "show()/finalize: atomic insert, atomic correction, finalize semantics",
              "status": "Complete",
              "description": "Insert = commit_string+commit; correction = delete_surrounding_text(before,0)+commit_string+commit in ONE atomic commit; >4000-byte chunk-or-refuse; finalize = zero-diff ⇒ zero edits, differing ⇒ one replacement.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M4.T3.S1",
                  "title": "Insert path (commit_string + commit)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: insert proven 26–40 ms cmd→field on GTK4; commit_string generates ZERO key events (delivery cannot self-trigger takeover); payloads >4000 bytes chunk without violating the one-edit rule or refuse with delivery_reason (origin of the cap unresolved in research — treat ≤4000 B/commit as the engineering rule).\n2. INPUT: acquire from P1.M4.T2.S1.\n3. LOGIC: show() executed on the target's event loop; only if focus/caret/selection/ownership still match; result mapping to applied|unchanged|refused|unknown (bytes-sent ≠ applied); 250 ms deadline with receiver-side validation.\n4. OUTPUT: insert-capable adapter.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M4.T3.S2",
                  "title": "Correction path (one atomic range replacement)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T3.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: correction = delete_surrounding_text(before,0) + commit_string + commit(serial) in ONE atomic commit — proven byte-exact on a 1024-byte span; GTK decomposes it internally into 1–2 changed signals within one commit cycle (frame-level single-edit verification is the G3 concern, P1.M4.T5.S1); correction reach is bounded by OWNERSHIP, never size (user decision 2026-11-19).\n2. INPUT: P1.M4.T3.S1.\n3. LOGIC: verified-owned-range replacement; never touches adjacent user text; expected_revision guard; refuse with delivery_reason when a span cannot be corrected atomically (e.g. unchunkable >4000 B).\n4. OUTPUT: full show().\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M4.T3.S3",
                  "title": "finalize/leave/cancel semantics",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T3.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.3 — final matching visible text ⇒ NO further edit (ownership ends; commit side effects must not visibly change/duplicate); differing final ⇒ ONE replacement; final with no preceding partial inserts once AND counts as a missed live update in latency evidence; rejected final never auto-erases visible words; leave: stop preserves last visible words, NO post-stop writes anywhere including a newly focused field; deliberate cancel removes the owned fragment in ONE op, drops buffered audio, keeps listening — bulk cancel performs NO len(tail)−1 physical-character compensation (legacy-only).\n2. INPUT: P1.M4.T3.S2.\n3. LOGIC: implement + unit-test each branch.\n4. OUTPUT: adapter complete for takeover work.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M4.T4",
              "title": "Takeover revocation at the target",
              "status": "Complete",
              "description": "Any ordinary physical key, caret move, selection change, click, focus change, tab/pane switch, or target death revokes the handle AT THE TARGET; queued ops re-check at mutation time.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M4.T4.S1",
                  "title": "Takeover detection + revocation + mutation-time re-checks",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T3.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.5 + im-lab evidence — grab_keyboard key events reach the adapter while the field stays untouched; synthetic delivery events cannot self-trigger HALT or leave modifiers held; the arming chord is ignored (NOT a blanket grace window); pointer motion alone is not an edit; daemon-side flags alone do not suffice — revoke AT THE TARGET.\n2. INPUT: P1.M4.T3.S3.\n3. LOGIC: takeover listeners (key events, surrounding_text caret/selection deltas, focus/deactivate, target death), handle revocation, queued-op re-check hooks at mutation time.\n4. OUTPUT: takeover-complete adapter ready for G3.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M4.T5",
              "title": "Real-field proof + field-class matrix re-run (G3 core)",
              "status": "Complete",
              "description": "R.4 order: prove insert AND correct in real fields BEFORE any mic integration. Productize the isolated-compositor harness, run GTK rows with visibility instrumentation, and refresh the foot/kitty/ghostty matrix at the versions now installed (they drifted).",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M4.T5.S1",
                  "title": "G3 harness + GTK field rows (insert AND correct, visible)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T4.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: reuse the im-lab pattern — imlab_run.py (private Xvfb seat + private D-Bus + Sway x11 backend), field_gtk.py (real GTK4 Gtk.Entry dumping text+cursor+edit-count atomically); gtk4-demo/gtk3-demo are MISSING — hand-written field apps only; system PyGObject Gtk 4.24 verified working (d2_bulk_delivery_map.md §5/§6). A byte reader/scrollback/fake editor never substitutes for visibility; add frame-level single-edit instrumentation (GTK fires 1–2 changed signals per commit cycle; no transient delete/retype frames).\n2. INPUT: adapter from P1.M4.T4.S1.\n3. LOGIC: productize the runner (automation NEVER exercises the live desktop/real clipboard/default mic/active service; private compositor + synthetic input; evidence bounded, only fixtures enter git — AGENTS.md Rule 3). Rows: short updates; a 20-sentence first-word correction; repeated identical finals; long + Unicode payloads; a refusing target. Assert editor contents + cursor + the visible field.\n4. OUTPUT: GTK-class rows reporting verified (versions + evidence) — a G2 pass never marks a row verified.\n5. DOCS: bounded row-report file.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.5"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M4.T5.S2",
                  "title": "Field-class matrix re-run at installed versions (drift!)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T5.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: VERSION DRIFT — installed hyprland 0.57.2 / kitty 0.51.0 / ghostty 1.4.0 vs the measured matrix (0.56.2 / 0.49.1 / 1.3.1): the ghostty version watch has TRIGGERED (a gtk-ime fix may have landed in 1.4.0 — retest before trusting \"ghostty = unavailable\"); kitty 0.49→0.51 may change the delete_surrounding/surrounding-text verdicts; the Hyprland relay row needs an isolated real Hyprland attempt (nested failed: aquamarine CBackend::create under software rendering) — recording blocked(reason) is a legitimate result (d2_bulk_delivery_map.md §6, §9 risks 1–2, 5).\n2. INPUT: harness from P1.M4.T5.S1.\n3. LOGIC: re-run foot/kitty/ghostty rows + attempt a Hyprland row; rows report untested | insert-only | blocked (reason) | verified (versions + evidence); insert-only rows NEVER run as full dictation; terminals never send surrounding_text → terminal verification is app-side only.\n4. OUTPUT: refreshed matrix; the route table that decides whether the P1.M5.T3 clipboard fallback is needed at all.\n5. DOCS: bounded matrix report.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.7"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M5",
          "title": "Cooperating-editor pi-prompt adapter + remaining G3 rows + conditional clipboard fallback",
          "status": "Complete",
          "description": "The terminal chat prompt is the FIRST milestone target (R.3): a pi extension CustomEditor + control socket as a second real TargetAdapter, proven in isolated Ghostty; then graphical-editor and browser-field rows; clipboard insert-fallback only if the refreshed matrix still needs it.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M5.T1",
              "title": "pi chat-prompt cooperating-editor adapter (extension seam)",
              "status": "Complete",
              "description": "A project-local pi extension installs a CustomEditor owning the prompt buffer plus an AF_UNIX control socket; a daemon-side TargetAdapter speaks that socket. Documented seam — no fork.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M5.T1.S1",
                  "title": "pi extension: CustomEditor + AF_UNIX control socket",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: PIN the seam doc copy /home/dustin/.pi/agent/npm/node_modules/@mariozechner/pi-coding-agent-*/docs/extensions.md (a second differing copy exists — d2_bulk_delivery_map.md §7). ctx.ui.setEditorComponent(factory) (:2258-2268): extend CustomEditor (NOT Editor) to keep app keybindings, call super.handleInput(data) for unhandled keys, capture/wrap the previous editor via ctx.ui.getEditorComponent() (single slot), gate installs on ctx.hasUI. ctx.fork(entryId,{position:\"before\"}) is a session-tree restore primitive, NOT a text-injection API — the adapter gets text in via its own editor. The API's exact write/caret control is NOT yet exercised — prove it with a minimal proof FIRST (R.2: \"prove at G3\").\n2. INPUT: contracts from P1.M3.T1.S1.\n3. LOGIC: project-local .pi/extensions/*.ts on session_start: CustomEditor subclass owning the prompt buffer + AF_UNIX control socket speaking one-JSON-line ops (insert/replace/cancel/read) applied as buffer edits on pi's event loop (true range replacement, zero keystrokes).\n4. OUTPUT: extension + socket protocol for P1.M5.T1.S2.\n5. DOCS: Mode A — extension README/JSdoc describing the socket protocol.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M5.T1.S2",
                  "title": "Daemon-side cooperating-editor TargetAdapter",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M5.T1.S1",
                    "P1.M3.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: same contracts as the IM adapter (P1.M4.T2/T3/T4) — acquire/show/finalize/leave/cancel, results taxonomy, takeover (the extension reports editor focus/keystrokes), ops executed on the target's event loop, 250 ms deadline, never retry a may-have-landed op.\n2. INPUT: extension socket from P1.M5.T1.S1 + failure-complete controller from P1.M3.T2.S2.\n3. LOGIC: TargetAdapter speaking the extension's AF_UNIX socket; map editor events to the shared takeover taxonomy.\n4. OUTPUT: second real adapter for G3 rows.\n5. DOCS: Mode A — module docstring carrying the R.3 contract.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M5.T2",
              "title": "G3 rows: pi prompt in isolated Ghostty (first), graphical editor, browser field",
              "status": "Complete",
              "description": "R.3: prove pi's real input editor inside isolated Ghostty with scripted partials/finals, asserting exact editor text + caret + the VISIBLE prompt; then the graphical-editor and browser-field rows G6 requires.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M5.T2.S1",
                  "title": "pi-prompt-in-isolated-Ghostty row",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M5.T1.S2",
                    "P1.M4.T5.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.3 — the terminal chat prompt is the FIRST milestone: assert the editor's own text + caret + the visible prompt (never a byte reader, scrollback, or fake editor); reuse the paste-lab private headless Sway + ghostty launch pattern; the refreshed matrix (P1.M4.T5.S2) decides whether this row rides the cooperating-editor seam or (if ghostty 1.4.0 grew IM support) the IM route — terminal corrections ride the cooperating-editor seam, NEVER IM delete.\n2. INPUT: adapter from P1.M5.T1.S2 + matrix verdict from P1.M4.T5.S2.\n3. LOGIC: scripted partials/finals through the real pi editor in isolated Ghostty; assert no folded-paste placeholders, no shortcut execution/submission, no neighbor changes; missing visibility instrumentation means \"not verified\", not \"passed\".\n4. OUTPUT: pi-prompt row verified | blocked (reason) with evidence links.\n5. DOCS: bounded row report.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.5"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M5.T2.S2",
                  "title": "Graphical editor + browser text field rows",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T5.S1",
                    "P1.M4.T5.S2",
                    "P1.M4.T3.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: G6 requires verified rows for the pi prompt + a graphical editor + a browser field; browser field = a real browser text input in the isolated compositor (not a mock DOM); never claim \"works on Wayland\" from one row.\n2. INPUT: harness from P1.M4.T5.S1 + adapter from P1.M4.T3.S3.\n3. LOGIC: run both rows with the same assertions (contents + cursor + visible field; one-edit corrections; zero-diff ⇒ zero events; takeover revocation); report each field class honestly (verified | insert-only | blocked).\n4. OUTPUT: the remaining G3 rows G6 needs.\n5. DOCS: bounded row report.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.5"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M5.T3",
              "title": "Clipboard insert-fallback adapter (conditional on the refreshed matrix)",
              "status": "Complete",
              "description": "R.6: clipboard ONLY as insert fallback for ghostty-class terminals, ONLY if the re-run matrix still shows ghostty IM-dead AND a row needs it; strict preservation contract or the adapter is unavailable.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M5.T3.S1",
                  "title": "Conditional clipboard insert-fallback + G4 gate (or recorded skip)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M4.T5.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: paste-lab evidence — 951-byte Unicode payload delivered intact as ONE bracketed paste, 153/175 ms (clipboard pre-staged; mechanism only, NOT G5 evidence); pasted 0x08 bytes arrive as SPACES → bulk-Backspace-over-paste is DEAD → insert-only by design; wl-copy cannot restore multi-format offers; clipboard managers snapshot every offer; PRIMARY untouched (external_tech_notes.md §5).\n2. INPUT: matrix verdict from P1.M4.T5.S2 (ghostty row at 1.4.0).\n3. LOGIC: IF the condition holds: implement the insert-only clipboard adapter under the R.6 contract (preserve all prior formats/bytes — if unprovable with the local manager, the adapter is UNAVAILABLE, never disable the manager; distinguish original ownership from a later identical copy; protect a simultaneous user paste; keep partials out of the history watcher) and run the G4 gate (private manager with text+image watchers; simultaneous copies incl identical bytes; user paste during transfer; empty/rich/image offers; failure before/after the data request; process death — verify contents/history/formats/target, never exit codes). ELSE record \"not needed at current versions\" citing the matrix and close.\n4. OUTPUT: conditional adapter + G4 evidence, or a recorded skip decision.\n5. DOCS: Mode A — module docstring carrying the R.6 contract.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.7"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M6",
          "title": "Recognition integration + delivery lifecycle (R.5/R.6 daemon-side) + G5 timing",
          "status": "Complete",
          "description": "Utterance identities through the recorder relay; bulk wiring into the daemon (enqueue-and-return, cancel intercept before legacy compensation, disarm paths, session recovery memory, voicectl session); bulk committed-context decoupling; the G5 timing harness.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M6.T1",
              "title": "Utterance identities + session generation through the recorder relay",
              "status": "Complete",
              "description": "Extend the partial/final payloads with utterance_id + session_gen assigned at the decode source; late events keep their own identity; dropped/filtered finals still close the boundary.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M6.T1.S1",
                  "title": "Payload helper at the five final sites + partial site",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T1.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: exact recipe d2_bulk_delivery_map.md §1 — the FIVE (\"final\",…) puts are recorder_host.py:644, :742, :745, :1052, :1054; partial put at :1100; wrap them in ONE payload helper adding utterance_id + session_gen (additive keys; `cancelled` and `context_prompt` are the precedents); daemon consumes at the single choke point _dispatch :426-479; RecorderHost.text() and the run loop need no change. The child already owns a per-utterance lifecycle (:631-643) the id piggybacks on.\n2. INPUT: baseline (no behavior change to stream-edit).\n3. LOGIC: child assigns ids at the decode source; a late event keeps its own identity (never relabeled as newer); daemon discards late post-final partials, duplicate finals, canceled-utterance events; a dropped or filtered final still closes its utterance boundary; keep the existing arm/disarm audio purges. Unit-test the relay round-trip with the existing recorder-host test doubles.\n4. OUTPUT: identity-carrying events for P1.M6.T2.S1.\n5. DOCS: Mode A — recorder_host.py protocol docstring update.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.1"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M6.T2",
              "title": "Wire bulk delivery into the daemon + session recovery + voicectl session",
              "status": "Complete",
              "description": "Route partial/final to the bulk controller when delivery=bulk-text; intercept bulk cancel BEFORE the legacy backspace compensation; disarm paths with no late flush; R.6 recovery memory; the session CLI.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M6.T2.S1",
                  "title": "Dispatch wiring + bulk cancel intercept",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M3.T2.S3",
                    "P1.M6.T1.S1",
                    "P1.M4.T3.S3"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: on_final daemon.py:1142 / _on_partial :1500 route into StreamingOutput (ctor :780-785; commit :1281; on_partial :1516). Bulk cancel MUST branch at the TOP of VoiceTypingDaemon.cancel() (daemon.py:1754, after the not-armed return :1775-1778) BEFORE the legacy compensation (:1779 n=max(tail_len−1,0); :1781 press_backspace) — keep host.cancel + suppression-window logic shared. Entries: socket cancel :2691-2694 AND evdev _on_cancel_backspace :1621-1630 (d2_bulk_delivery_map.md §2).\n2. INPUT: G2-passed controller (P1.M3.T2.S3), identity events (P1.M6.T1.S1), at least one real adapter (P1.M4.T3.S3 and/or P1.M5.T1.S2).\n3. LOGIC: delivery=bulk-text routes partial/final to the bulk controller enqueue-and-return on the reader thread (no subprocess/editor wait under the daemon control lock); stop/toggle-off/idle-stop disarm immediately, no late flush; takeover/unknown/refused/stall ⇒ disarm bulk delivery AND recording with ONE reason via delivery_reason; stream-edit default behavior byte-identical (G1 watch set green).\n4. OUTPUT: end-to-end bulk path (mic→field) behind the opt-in flag.\n5. DOCS: Mode A — daemon docstring delivery note.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.1"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M6.T2.S2",
                  "title": "Session recovery memory (R.6)",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M6.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: R.6 recovery — daemon MEMORY (no crash persistence, no new transcript-bearing logs; bulk logs carry counts/times, not text).\n2. INPUT: P1.M6.T2.S1.\n3. LOGIC: hold the LAST nonempty arm→disarm session: accepted final per utterance + last visible/recognized unfinished tail, exactly once each; a rejected final retains only the shown tail; deliberate cancels and late finals excluded; the previous completed session survives empty or failed arms; ≤2 sessions × 1 MiB UTF-8 (on overflow keep the newest complete text that fits and report truncation); cleared at daemon exit. Unit-test every exclusion rule.\n4. OUTPUT: recovery store for P1.M6.T2.S3.\n5. DOCS: none.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M6.T2.S3",
                  "title": "voicectl session [--copy]",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M6.T2.S2",
                    "P1.M3.T3.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: ctl recipe d2_bulk_delivery_map.md §4 — add \"session\" to _COMMANDS (ctl.py:42-49); send_command (:167-210) sends {\"cmd\":cmd} only → extend with extra payload keys (daemon _dispatch ignores unknown keys today — old daemons fail safe); format_result session branch; wl-copy staging pattern at tools/paste-lab/ghostty_probe.py:102 with wl-paste --no-newline verify :109; external_tech_notes.md §5.7: `printf %s \"$text\" | wl-copy -t text/plain` (clipboard selection only, PRIMARY untouched, explicit MIME).\n2. INPUT: recovery store from P1.M6.T2.S2 + status surface from P1.M3.T3.S2.\n3. LOGIC: `voicectl session` prints the most recent COMPLETED session (never a moving draft); `--copy` copies exactly that text — no added newline, never types/erases/submits; exit 1 with clipboard untouched when none exists; truncation reported on stderr and in the reply; daemon-side session_reply in _dispatch; the bind is USER-assigned — never install one, never touch hypr-binds.conf.\n4. OUTPUT: session command green (unit + socket tests).\n5. DOCS: Mode A — ctl.py docstring + --help epilog gain session.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.12"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M6.T3",
              "title": "Decouple bulk committed context from StreamingOutput",
              "status": "Complete",
              "description": "The rolling context-prompt push reads _stream.committed today; bulk mode must not silently redefine it — read the bulk controller's last-confirmed text instead.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M6.T3.S1",
                  "title": "Bulk-mode prompt source decision + implementation",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M6.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: risk #7 (d2_bulk_delivery_map.md §9): daemon.py:1735-1747 pushes rolling_context_prompt(self._stream.committed) to the child; prompt_engine.rolling_context_prompt (prompt_engine.py:119, 200-token cap) still applies; in bulk mode the committed checkpoint lives in the bulk controller (last target-CONFIRMED text), not in StreamingOutput.\n2. INPUT: P1.M6.T2.S1.\n3. LOGIC: in bulk mode the prompt push reads the bulk controller's last-confirmed text (its own mirror; read-only from _stream, never writing it); context still trims at the sentence boundary; both modes keep working; no cross-mode state bleed (unit-test both modes' prompt content).\n4. OUTPUT: prompt context correct in both modes.\n5. DOCS: code comment documenting the decision (no user-facing surface).",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h3.4"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M6.T4",
              "title": "G5 timing evidence (word-aligned real-voice replay)",
              "status": "Complete",
              "description": "Warm GPU, monotonic clocks, word-aligned replay of real voice: speech-end→word-visible median ≤500 ms / p95 <1 s; update-ready→first-changed-frame p95 ≤100 ms insert / ≤50 ms correct; ≥100 insertions and ≥100 corrections per claimed route.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M6.T4.S1",
                  "title": "G5 harness + per-route timing evidence",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M6.T2.S1",
                    "P1.M5.T2.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: G5 rules — callback cadence and the silence detector are NOT the speech clock; word-aligned replay of real voice (tools/asr-lab/voice/ clips), warm GPU, monotonic clocks; missing words are misses, not zero-latency samples; a sustained five-word backlog or a sentence-end dump fails regardless of medians; asr-lab context: turbo@float16 = 382 ms median word lag (external timing reference, not the delivery clock).\n2. INPUT: bulk path from P1.M6.T2.S1 + at least one verified route (P1.M5.T2.S1 or P1.M4.T5 rows).\n3. LOGIC: build the bounded measurement harness (private compositor + synthetic input; automation NEVER exercises the live desktop/real clipboard/default mic/active service; only fixtures enter git); publish per-route counts, median, p95, worst gap, max words outstanding; report failures, never average them away.\n4. OUTPUT: G5 evidence per claimed route.\n5. DOCS: bounded timing report.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.5"
                  ]
                }
              ]
            }
          ]
        },
        {
          "type": "Milestone",
          "id": "P1.M7",
          "title": "Graduation assessment + changeset-level documentation sync",
          "status": "Complete",
          "description": "G6 evidence-gated graduation (default flip only with writing-session evidence), then the Mode B changeset documentation sweep (README, ACCEPTANCE.md, install.sh) depending on every implementing subtask.",
          "tasks": [
            {
              "type": "Task",
              "id": "P1.M7.T1",
              "title": "G6 graduation assessment (evidence-gated, no over-claiming)",
              "status": "Complete",
              "description": "Verified G3 rows for pi prompt in Ghostty + a graphical editor + a browser field, zero integrity failures, and ≥3 writing sessions beating 110 wpm effective proofread throughput — else report unmet and stay opt-in.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M7.T1.S1",
                  "title": "Assemble G6 assessment; conditionally flip the default",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M5.T2.S1",
                    "P1.M5.T2.S2",
                    "P1.M6.T4.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: G6 — never claim \"works on Wayland\" from one row; a passing transport probe NEVER flips a NOT VERIFIED claim to passed; graduation requires ≥3 representative completed writing sessions where usable proofread wpm (counting corrections, recovery, rereading) beats 110 — operator-dependent evidence.\n2. INPUT: G3 rows (P1.M5.T2.S1, P1.M5.T2.S2), G5 evidence (P1.M6.T4.S1), integrity-failure log.\n3. LOGIC: assemble the assessment; IF AND ONLY IF all G6 conditions are met, flip output.delivery default to \"bulk-text\" in lockstep (config.py + config.toml + tests; precondition triple still enforced); OTHERWISE record explicitly unmet and stay opt-in. No fabricated user acceptance.\n4. OUTPUT: graduation report + conditional default flip.\n5. DOCS: bounded assessment doc.",
                  "prd_selectors": [
                    "h2.3",
                    "h3.6",
                    "h2.6",
                    "h2.5"
                  ]
                }
              ]
            },
            {
              "type": "Task",
              "id": "P1.M7.T2",
              "title": "Sync changeset-level documentation",
              "status": "Complete",
              "description": "Mode B catch-all: README.md sections/config table/troubleshooting, tests/ACCEPTANCE.md rows with re-measured numbers, install.sh usage — every claim verified against the code as landed.",
              "subtasks": [
                {
                  "type": "Subtask",
                  "id": "P1.M7.T2.S1",
                  "title": "README.md: ducking + bulk delivery sections, config table, troubleshooting",
                  "status": "Complete",
                  "story_points": 2,
                  "dependencies": [
                    "P1.M1.T2.S1",
                    "P1.M1.T2.S2",
                    "P1.M1.T2.S3",
                    "P1.M1.T3.S1",
                    "P1.M1.T3.S2",
                    "P1.M1.T4.S1",
                    "P1.M1.T4.S2",
                    "P1.M2.T1.S1",
                    "P1.M2.T2.S1",
                    "P1.M2.T2.S2",
                    "P1.M2.T2.S3",
                    "P1.M2.T2.S4",
                    "P1.M2.T3.S1",
                    "P1.M2.T3.S2",
                    "P1.M2.T4.S1",
                    "P1.M3.T1.S1",
                    "P1.M3.T2.S1",
                    "P1.M3.T2.S2",
                    "P1.M3.T2.S3",
                    "P1.M3.T3.S1",
                    "P1.M3.T3.S2",
                    "P1.M4.T1.S1",
                    "P1.M4.T1.S2",
                    "P1.M4.T2.S1",
                    "P1.M4.T3.S1",
                    "P1.M4.T3.S2",
                    "P1.M4.T3.S3",
                    "P1.M4.T4.S1",
                    "P1.M4.T5.S1",
                    "P1.M4.T5.S2",
                    "P1.M5.T1.S1",
                    "P1.M5.T1.S2",
                    "P1.M5.T2.S1",
                    "P1.M5.T2.S2",
                    "P1.M5.T3.S1",
                    "P1.M6.T1.S1",
                    "P1.M6.T2.S1",
                    "P1.M6.T2.S2",
                    "P1.M6.T2.S3",
                    "P1.M6.T3.S1",
                    "P1.M6.T4.S1",
                    "P1.M7.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: delta PRD §4 Mode B list — README gains: a Media ducking section (tiers, config, sovereignty guarantees), a Bulk text delivery section (opt-in flag, delivery states, voicectl session, EXPLICIT \"unverified until G3/G6\" framing per R.2's no-over-claim rule), config table rows for [audio] + output.delivery, troubleshooting additions (seat IM exclusivity/fcitx5, terminal field-class matrix, clipboard contract).\n2. INPUT: all implementing subtasks listed in dependencies (their landed behavior + evidence records).\n3. LOGIC: update README.md to describe exactly what landed — no aspirational prose; unverified fields/latencies stay labeled unverified; verify every statement against the code and evidence files.\n4. OUTPUT: README current with the whole changeset.\n5. DOCS: Mode B by definition — this IS the doc task.",
                  "prd_selectors": [
                    "h2.6",
                    "h2.3",
                    "h3.5",
                    "h3.6",
                    "h3.9",
                    "h3.12",
                    "h3.13"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M7.T2.S2",
                  "title": "tests/ACCEPTANCE.md rows + install.sh usage",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M1.T1.S1",
                    "P1.M1.T1.S2",
                    "P1.M1.T2.S3",
                    "P1.M1.T3.S2",
                    "P1.M1.T4.S2",
                    "P1.M2.T4.S1",
                    "P1.M3.T2.S3",
                    "P1.M4.T5.S2",
                    "P1.M5.T2.S1",
                    "P1.M5.T2.S2",
                    "P1.M6.T2.S3",
                    "P1.M6.T4.S1",
                    "P1.M7.T1.S1"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: tests/ACCEPTANCE.md row 11 is STALE (claims test_streaming.py 7/7 and 77 passed across the trio; HEAD measures 3/7 and 76/18) — refresh with re-measured numbers reconciled against the G1 baseline classification (lazy-separator legacy reds separated from NEW failures; no parity faking); row 12 refresh if D3 changed cancel behavior; totals line updated.\n2. INPUT: baseline + all gate/evidence subtasks in dependencies.\n3. LOGIC: add the ducking acceptance row (P1.M2 evidence) and row #13 (§7 item 13) with actual command-output links; refresh rows 11/12; install.sh printed usage gains the `session` command.\n4. OUTPUT: acceptance dossier current; install.sh usage current.\n5. DOCS: Mode B by definition.",
                  "prd_selectors": [
                    "h2.6",
                    "h2.5",
                    "h2.3",
                    "h3.5",
                    "h3.6"
                  ]
                },
                {
                  "type": "Subtask",
                  "id": "P1.M7.T2.S3",
                  "title": "Final consistency sweep + commit discipline",
                  "status": "Complete",
                  "story_points": 1,
                  "dependencies": [
                    "P1.M7.T2.S1",
                    "P1.M7.T2.S2"
                  ],
                  "context_scope": "CONTRACT DEFINITION:\n1. RESEARCH NOTE: delta acceptance #4 — everything committed to main with sensible messages; no over-claiming anywhere.\n2. INPUT: P1.M7.T2.S1 + P1.M7.T2.S2.\n3. LOGIC: walk README/ACCEPTANCE/config.toml comments/voicectl --help against actual landed behavior; confirm every unverified claim stays labeled unverified; confirm the G1 watch set has no unexplained new failures vs tests/G1_BASELINE.md; confirm repo clean and all work committed on main.\n4. OUTPUT: final sign-off note in the acceptance dossier.\n5. DOCS: Mode B (verification of the doc sweep itself).",
                  "prd_selectors": [
                    "h2.6",
                    "h2.3",
                    "h3.5",
                    "h3.6"
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
Check plan/008_a47116bb2b79/architecture/ for existing research that may still apply.

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
5. **LEVERAGE PRIOR RESEARCH**: Check plan/008_a47116bb2b79/architecture/ for research that applies
   - Don't duplicate research that's already been done
6. **OUTPUT**: Write the delta PRD to `plan/009_ef3b49b0fc0d/delta_prd.md`

**Remember: Minimal change = minimal PRD. Do NOT over-engineer.**

### PREVIOUS SESSION AWARENESS
**CRITICAL**: Documentation from previous sessions exists and takes PRIORITY over web searches.

Previous session directory: plan/008_a47116bb2b79

When researching for this delta session:
1. **FIRST** check `plan/008_a47116bb2b79/architecture/` for existing research
2. **FIRST** check `plan/008_a47116bb2b79/docs/` for implementation notes
3. Reference completed work from previous sessions instead of re-researching
4. Build upon existing patterns and decisions
5. Only do web searches for genuinely NEW topics not covered in prior sessions
