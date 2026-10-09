# voice-typing

Fully-local voice typing for Linux. Speak into your mic and the recognized text is
typed into whatever window has focus. Built on RealtimeSTT
(faster-whisper / CTranslate2 on CUDA). Intended for an Arch + Wayland / Hyprland
desktop. The recognizer runs 100% on your machine; nothing is sent to a cloud.
Offline mode is enforced: the launch wrapper (`launch_daemon.sh`) sets `HF_HUB_OFFLINE=1`,
so models load from the local cache with zero runtime network calls (the install prefetches
them).

This README is for two readers: dustin, six months from now, and anyone who clones
the repo. It assumes a Linux power user who wants exact commands, not hand-holding.

## Requirements

- Arch-ish Linux with a working systemd user session (`systemctl --user` works).
- NVIDIA GPU with CUDA drivers. Optional: the daemon auto-falls-back to CPU (slower).
- Wayland / Hyprland, for the default `wtype` typing backend and `hyprctl notify`.
- PipeWire (the daemon records the system default source).
- `portaudio` (PyAudio build dep). Check it with `pacman -Q portaudio`.

## Install

From the repo root:

```
./install.sh
```

The script is idempotent and re-runnable. It does, in order:

1. Checks that `portaudio` (PyAudio's system dependency) is installed. On Arch it runs
   `pacman -Q portaudio`; if that fails it aborts with the exact
   `sudo pacman -S --noconfirm portaudio` command and asks you to re-run `./install.sh`.
   Hosts without `pacman` get a warning and continue (install portaudio yourself).
2. `uv sync` (creates or refreshes `.venv/`).
3. A CUDA smoke that prints `VERDICT=cuda-ok` or `VERDICT=cpu-fallback-required`.
4. Prefetches the whisper models into `~/.cache/huggingface` (warn-only on miss).
5. Installs, daemon-reloads, enables, and restarts the systemd user unit.
6. Copies `config.toml` to `~/.config/voice-typing/config.toml` if absent (never
   overwrites an existing one).
7. Prints the usage line, the Hyprland source line, and the logs command.

When install.sh finishes, the daemon is **running, NOT listening, and NOT loaded**
(~0 VRAM). It never hot-mics on boot and loads no models until the first
`voicectl toggle` (~1-3s). Run `voicectl toggle` (or the hotkey) to arm the mic.

## First run

A real-microphone smoke you run by hand. Full paths are used because the desktop zsh
aliases `python3` and `pip`.

The first `voicectl toggle` (or `start`) each session takes ~1-3s to load the model —
`voicectl` prints `loading models… (first arm, ~1–3 s)` to stderr while it loads.
Subsequent arms are instant (the model stays resident until `quit` or 30 min disarmed;
see [Model lifecycle & VRAM](#model-lifecycle--vram)).

```
systemctl --user start voice-typing
/home/<you>/projects/voice-typing/.venv/bin/voicectl toggle   # arms the mic
# speak. Words are typed into the focused window LIVE, revised in place as you talk.
# Watch the hyprctl toasts, or poll `voicectl status` / `state.json` for the live tail:
#   the first arm shows "Loading…" then "Recording"; later arms just "Recording";
#   disarming shows "Recording Stopped" (the ✔ final popup is optional — see feedback.notify_on_final).
/home/<you>/projects/voice-typing/.venv/bin/voicectl toggle   # disarms
```

Expected behavior while listening: hyprctl toasts track Recording / Recording Stopped,
and stabilized text is typed into the focused window **as you speak** and revised in
place (see [Streaming dictation](#streaming-dictation)). A pause triggers the
commit/correction pass on the typed tail (plus the trailing space) but does **not** end
the session — the recognizer keeps listening; only `voicectl stop` (or toggle off)
disarms the mic. **Backspace** while a fragment is in flight cancels it.

If the mic never arms or no text appears, the two knobs to reach for are the
microphone default source (Troubleshooting) and `asr.lite_post_speech_silence_duration`
(Configuration).

## Hotkey (Hyprland)

Bind **Ctrl+Alt+Super+D** to arm/disarm dictation, and **Super+Alt+Backspace** to
cancel the in-flight fragment. Add this one line to `~/.config/hypr/hyprland.conf`
(install.sh prints it; the repo never edits your hyprland.conf):

```
source = /home/<you>/projects/voice-typing/hypr-binds.conf
```

Then reload:

```
hyprctl reload
```

The sourced file is `hypr-binds.conf` at the repo root. Its binds invoke voicectl via the
`$HOME/.local/bin/voicectl` launcher that `install.sh` maintains (Hyprland runs every `bind exec`
through `/bin/sh -c`, so `$HOME` expands), so they work regardless of user / repo location:

```
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle
bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel
```

The first bind arms the mic; pressing it again disarms it (the graceful drain lets the
in-flight commit land first). The second runs the same cancel path as the daemon's
physical-Backspace listener — see
[Backspace-cancel](#backspace-cancel-erase-the-in-flight-fragment).

Hyprland uses the last matching bind for a given MODS+key. Source this file LAST
(at the bottom of `hyprland.conf`) so its binds win. If a bind is inert, your config may
already bind that MODS+key elsewhere. Check `~/.config/hypr/custom/keybinds.conf`,
or rebind to a free combo in `hypr-binds.conf`.

## Upgrading from Rev 1 (two-mode builds)

Rev 2 collapsed the two ASR modes into one streaming model, and the CLI shrank to six
commands: `toggle`, `start`, `stop`, `status`, `cancel`, `quit`. If you are upgrading a
machine whose Hyprland config (e.g. `~/.config/hypr/custom/keybinds.lua` or
`keybinds.conf`) predates the change:

- A bind ending in `voicectl toggle-lite` still works — `toggle-lite` is accepted as a
  deprecated migration alias for `toggle`. Rebind it to plain `voicectl toggle` when
  convenient; the alias is undocumented and may be removed in a future release.
- A bind ending in `voicectl start-lite` now fails with exit 64 (usage error) and must be
  changed to `voicectl start` (or `toggle`).
- `state.json` and `voicectl status` always report `mode: lite`; there is no normal mode
  any more.

## Streaming dictation

Rev 2 has exactly one dictation mode: a single resident model (`asr.lite_model`, default
`small.en`) produces BOTH the live text and the committed finals. Dictation is
phone-style: **words are typed into the focused window as they are spoken, revised in
place, and the mic never pauses for decoding.**

While you speak:

- **Partials are typed live, revised with minimal diffs.** Each stabilized partial
  is diffed against what is on screen: an extension types only the delta; a
  revision backspaces only the diverging suffix — the text after the longest
  common prefix, matched case-insensitively (so a casing-corrected fragment
  still extends by clean deltas) and counted on the original characters — then
  retypes just the corrected remainder. Only a genuinely prefix-free rewrite
  ever rewinds the whole tail. Revision cycles that include a backspace are
  rate-limited (≥300 ms apart — a code constant, not a config key) so a wobbling
  decode cannot flicker.
- **Silence trips the commit/correction pass.** After `asr.lite_post_speech_silence_duration`
  (default `0.8` s) of silence, the model re-decodes the complete utterance; if the
  correction differs from what is on screen, the tail is revised with the same
  minimal-diff rule (only the diverging suffix is rewound and retyped), then the
  trailing space is appended (`output.append_space`). Under streaming, the silence
  gate only delays this commit — the words are already visible.
- **Continuations read coherently.** Every decode is conditioned on the rolling committed
  context (`asr.context_prompt`, back to the last sentence boundary, ~200-token cap), so
  a mid-paragraph fragment doesn't start capitalized or gain a spurious trailing period.
- **A pause never ends the session.** Only `voicectl stop` (or toggle off) disarms the
  mic — and while disarmed, nothing is ever typed: stale partials are gated exactly like
  finals; the graceful drain lets the in-flight commit land first.

Safety rails:

- **Stranded tails freeze, never auto-delete.** If a commit can never land (a crash, an
  aborted teardown), the typed tail stays on screen exactly as last shown. The only thing
  that ever deletes typed text is an explicit cancel (below).
- **Rejected finals recover.** A hallucination caught by `filter.blocklist` (or a final
  below `filter.min_chars`) is not typed: that utterance's fragment freezes on screen as
  last shown, a journal warning (and, if notifications are on, a brief toast) says
  `filtered hallucination — not typed; keep dictating`, and live typing resumes with
  your next words.
- **Your keystrokes win.** Any non-Backspace keypress while a fragment is pending freezes
  it immediately and stops revising that utterance — the daemon never types over your
  cursor.
- **Rollback hatch:** `output.streaming = false` restores append-only behavior (only
  finalized text typed, one append per utterance).

### Backspace-cancel (erase the in-flight fragment)

While dictating — a tentative fragment on screen — a physical **Backspace** press cancels
it: the fragment is erased (by subtraction: the rewind compensates `len(tail) − 1`,
because the keystroke itself already deleted one character), the buffered audio of the
in-flight utterance is dropped, and the mic stays hot — just say the sentence again;
the re-said words type live again from their first words (the post-cancel pause lifts
as soon as you speak).

- **Idempotent:** Backspace presses with no pending fragment are plain user edits and are
  never compensated; `voicectl cancel` with nothing in flight is a no-op.
- **Stop after a cancel is instant.** `voicectl stop` right after a cancel disarms
  immediately — the cancelled utterance's audio is already gone, so the graceful drain
  has nothing to wait for.
- The listener is a passive, read-only evdev watcher over keyboard nodes exposing
  KEY_BACKSPACE. `[cancel].devices` overrides the auto-detection (e.g.
  `["/dev/input/event3"]`); virtual uinput/ydotool devices are always excluded, so the
  daemon's own typing can never self-cancel.
- If no keyboard node is readable, the daemon logs ONE journal warning at the first arm
  and stays silent after that.
- Fallback: the **Super+Alt+Backspace** bind (`voicectl cancel`) runs the identical
  cancel path regardless of evdev, and doubles as the automated-test seam.

## Feedback surfaces

The daemon publishes its live state to a JSON file, written atomically on every change:

- **State file** — `$XDG_RUNTIME_DIR/voice-typing/state.json` (override with
  `feedback.state_file`). Fields: `listening`, `phase` (`unloaded`/`loading`/`idle`/
  `listening`/`speaking`), `models_loaded`, `mode` (always `"lite"` — a fixed constant;
  Rev 2 has a single dictation mode), `partial` (mirrors the live typed tail; overwritten
  with the committed text when an utterance finalizes), `last_final`, and `ts`. Poll it
  with `jq` for your own UI (waybar, conky, …).
- **`voicectl status`** — human-readable one-shot of the same state (adds the resolved
  device/compute type, mic health, and the context-prompt line).
- **hyprctl toasts** — `Loading…` on a cold first arm, `Recording` / `Recording
  Stopped` on arm/disarm, and (optional, `feedback.notify_on_final`) `✔ <text>` per final.

## Configuration

The config file lives at `~/.config/voice-typing/config.toml` (install.sh copies
the repo default there if it is missing). Edit it, then restart the daemon:

```
systemctl --user restart voice-typing
```

Real tunable keys (every key below is a real field in `voice_typing/config.py`):

| Section.key | Default | Effect |
| --- | --- | --- |
| `asr.lite_model` | `"small.en"` | the SINGLE transcription model (Rev 2): loaded once, used for BOTH the live typed partials AND the committed finals. |
| `asr.lite_post_speech_silence_duration` | `0.8` | THE silence gate — seconds of silence before the commit/correction pass. Under streaming this only delays the commit (words are already typed live), so 0.8 halves mid-thought cuts for +0.3 s commit latency. `0.5` = razor-snappy (may split a brief pause); `1.0` = near-zero cuts. |
| `asr.context_prompt` | `true` | condition every decode on the rolling committed context (back to the last sentence boundary, ~200-token cap) so continuations read coherently. `false` = decode each utterance blind. |
| `asr.realtime_processing_pause` | `0.15` | cadence of the live partial previews. Lower is more responsive; higher uses less CPU. |
| `asr.auto_stop_idle_seconds` | `30.0` | auto-disarm (stop listening) after this many seconds with no recognized speech — partials reset the clock while you talk, so it only fires when you truly go silent (a forgotten hot-mic guard, not a mid-thought cut). `0` disables. Fires the normal `Recording Stopped` toast + a journal line. |
| `asr.auto_unload_idle_seconds` | `1800.0` | after this many seconds DISARMED (models loaded, not listening), tear down the recorder to free VRAM (~0). The clock starts on disarm (manual stop, toggle-off, or the 30s auto-stop) and resets on any arm; time listening doesn't count. `0` disables (models then stay resident until `quit`). The next arm reloads (~1-3s). See Model lifecycle. |
| `asr.device` | `"cuda"` | `"cuda"` or `"cpu"`. Auto-falls-back to `cpu` if no CUDA device is visible. |
| `asr.language` | `"en"` | ISO-639-1 code. |
| `output.backend` | `"wtype"` | `"wtype"` (Wayland virtual keyboard), `"ydotool"` (uinput), or `"null"` (types nothing; used by the headless E2E tests). `wtype` auto-falls-back to `ydotool`. |
| `output.append_space` | `true` | append one trailing space after each commit. |
| `output.streaming` | `true` | type stabilized partials live + revise in place as the utterance grows. `false` = append-only finals (rollback hatch to the pre-Rev-2 typing behavior). |
| `cancel.on_backspace` | `true` | enable the physical-Backspace cancel gesture while a fragment is pending. Any other keypress freezes the fragment instead (never typed over). |
| `cancel.devices` | `[]` | keyboard device node(s) to watch for the Backspace gesture, e.g. `["/dev/input/event3"]`. Empty list = auto-detect keyboards exposing KEY_BACKSPACE (uinput/ydotool virtual devices always excluded). Nothing readable → one journal warning at the first arm; the Super+Alt+Backspace bind still works. |
| `feedback.notify_on_final` | `true` | also pop a hyprctl popup with each commit's text (`✔ <text>`). Set `false` to keep only the brief `Recording` / `Recording Stopped` toasts — the text is already typed into the focused window, so the popup is redundant. |
| `feedback.notify_ms` | `2500` | how long hyprctl popups stay on screen (ms). Lower for a brief start/stop flash. |
| `feedback.hypr_notify` | `true` | master on/off for ALL hyprctl popups. `false` suppresses the start/stop toasts too (`notify_on_final` only adds the per-final ✔ popup; this is the global kill switch). |
| `filter.min_chars` | `2` | commits shorter than this are dropped. |
| `filter.blocklist` | list | exact, case-insensitive phrases dropped (classic Whisper silence hallucinations). |
| `log.level` | `"INFO"` | `"INFO"` (per-utterance latency line) or `"DEBUG"` (raw timestamps). |

`asr.post_speech_silence_duration` still exists in `config.toml`/`config.py`, but the
daemon does not consume it — the `lite_` key above is THE silence gate. Tuning the base
key changes nothing.

### Voice-activity constants are NOT config keys

`silero_sensitivity`, `webrtc_sensitivity`, `min_length_of_recording`,
`min_gap_between_recordings`, and `silero_backend` are **not** config keys. They are
constants in `voice_typing/daemon.py` (the `_FIXED_KWARGS` dict). `compute_type` is
also not a config key; it is derived from `device` (`float32` on cuda, `int8` on
cpu — float32 because the target GPU is a Maxwell-based 940MX, which has no
usable fp16/int8 GEMM path).

To change VAD sensitivity, edit `daemon.py` and restart the daemon. Do **not** add
these names to `config.toml`. The config loader (`config.py`) rejects unknown keys —
and unknown top-level tables — with `TypeError`, so a stray key *or a mistyped section
name* makes the daemon fail to load and systemd's `Restart=on-failure` loops it
forever. A value of the **wrong type** is rejected the same way: `auto_stop_idle_seconds = "thirty"` (a string where a number is expected)
or `device = 123` (a number where a string is expected) raises `TypeError` at load
with a message naming the field, rather than loading silently and breaking the
feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`
bool is not. A value outside a field's allowed set is rejected the same way — for
example `output.backend = "wtyp"` or `asr.device = "gpu"` raises `ValueError` at
load (the type is valid, the value is not), so a typo fails fast at startup instead
of crash-looping later.

## CPU-only mode

There are three ways the daemon ends up on CPU.

1. You force it. Set `[asr] device = "cpu"` in `config.toml` and restart. The daemon
   derives `compute_type="int8"` and runs your configured `asr.lite_model` (the single
   model) on CPU with int8 quantization.
2. Auto-fallback. When `ctranslate2` sees zero CUDA devices at startup, the daemon
   overrides to `device="cpu"`, `compute_type="int8"`, and the smaller CPU-substitute
   model `tiny.en` (the single model, substituted in one place), regardless of config.
3. Construction-failure fallback. The check in #2 only asks whether `ctranslate2` can
   *see* a GPU; it does not load cuDNN. If a GPU is visible but CUDA/cuDNN init then fails
   while building the recorder (for example a missing `libcudnn_ops.so.9` after a stale
   `uv sync`), the daemon retries once on the same CPU config as #2 and keeps running
   instead of crash-looping. `journalctl --user -u voice-typing` shows
   `CUDA recorder construction failed (...); falling back to CPU ... — degraded but
   functional` then `daemon started in degraded CPU mode`, and `voicectl status` reports
   `device: cpu (int8)`. Fix the library path (see the cuDNN section under Troubleshooting)
   and restart to return to the GPU.

`voicectl status` reports the resolved device and compute type (see Logs below), so you
can tell which path you are on:

```
/home/<you>/projects/voice-typing/.venv/bin/voicectl status
```

## Troubleshooting

### cuDNN load error (`libcudnn_ops.so.9`)

Symptom: the daemon log shows `cannot open shared object file: libcudnn_ops.so.9`
(or `libcudnn.so.9`, `libcublas.so.12`). cuDNN 9 ships split sub-libs with no
`RUNPATH`, so the dynamic linker needs them on `LD_LIBRARY_PATH` at process start.
The daemon's `ExecStart` runs `voice_typing/launch_daemon.sh`, which exports
`LD_LIBRARY_PATH` from the live nvidia wheels before exec'ing python. Do not bake
`Environment=LD_LIBRARY_PATH=` into the systemd unit; it goes stale on `uv sync`.

Triage, fastest first:

```
journalctl --user -u voice-typing -e
LD_DEBUG=libs /home/<you>/projects/voice-typing/voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
ldd /home/<you>/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9
systemctl --user restart voice-typing
```

After any fix, restart with `systemctl --user restart voice-typing` so the wrapper
recomputes the library paths.

If cuDNN still cannot be loaded at daemon startup, the daemon now degrades to CPU
automatically instead of crash-looping under `Restart=on-failure`: the journal shows the
`falling back to CPU ... degraded but functional` line and `voicectl status` reports
`device: cpu (int8)`. Transcription keeps working (slower); fix the library path above and
restart to get back on the GPU.

### Wrong microphone

The daemon records the PipeWire / PulseAudio **default source**. There is no config
key for the input device. List sources, set the default, and restart:

```
pactl list short sources
pactl set-default-source <source_name>
systemctl --user restart voice-typing
```

If speech yields nothing, check the mic health line FIRST — `voicectl status` prints a `mic:`
line (`mic: ok` when the default source is reachable, `mic: unavailable (<reason>)` when the
daemon's PyAudio probe found no input device). This surfaces a dead or changed default source
immediately, without digging into `journalctl`. After fixing the source, arm again with
`voicectl toggle`. The mic-health probe is cached for ~30 s to keep arming instant, so for an
immediate re-probe restart the daemon (`systemctl --user restart voice-typing`).

### wtype vs ydotool

`wtype` is the default backend (Wayland virtual keyboard, full Unicode). If `wtype`
fails on a given window, the daemon logs a warning and retries once with `ydotool`
(uinput). `ydotool` needs `ydotoold` running; on this machine it is an enabled user
service.

To force a single backend, set `[output] backend = "ydotool"` (or `"null"` to disable
typing entirely — finals still appear in the state file). Restart the daemon after editing.

## Logs, status, stopping

Follow the daemon log:

```
journalctl --user -u voice-typing -f
```

At `log.level = "INFO"`, each typed utterance prints one structured latency line.
At `"DEBUG"`, the raw monotonic timestamps are also logged.

If the configured mic is unreachable, RealtimeSTT retries it roughly every 3 seconds. The
daemon rate-limits that `Microphone connection failed ... Retrying` ERROR so the journal
shows the full traceback once, then a single `WARNING` summary roughly once per minute
(`Microphone still unavailable after N retry attempts (last error: ...)`). The retry itself
still happens; only the repeated traceback log line is throttled. See
[Wrong microphone](#wrong-microphone) and `voicectl status`'s `mic:` line to fix the source.

Check live state and the resolved device:

```
/home/<you>/projects/voice-typing/.venv/bin/voicectl status
```

Typical CUDA output while dictating:

```
listening: on
mode: lite
phase: speaking
partial: this is what i am say
last: Previous sentence.
uptime: 42.3s
device: cuda (float32)
mic: ok
context-prompt: on
```

`mode:` is always `lite` — a fixed daemon constant; Rev 2 has exactly one dictation mode.
`phase:` is `unloaded` at boot (nothing loaded), `loading` on the first arm, then
`idle`/`listening` (`speaking` while a fragment is pending). On CPU fallback, `device`
shows `cpu (int8)` and the journal's `voice-typing device resolved:` line names the
substituted model (`tiny.en`). `context-prompt:` is `on`, or one of:
`off (disabled by config)` (you set `asr.context_prompt = false`),
`off (models not loaded)` (before the first arm),
`off (degraded — context-free decoding)` (the rolling-context arm failed; decoding
continues without it), or `unknown` (an older daemon without the field).
If the mic is unavailable, the mic line reads `mic: unavailable (<reason>)`
instead.

### Model lifecycle & VRAM

At boot the daemon is **unloaded**: no recorder, no CUDA context, **~0 VRAM** — nothing
loads at boot. The first `voicectl start`/`toggle` (or hotkey) each session loads the
single model (`small.en` on CUDA; `tiny.en` after a CPU fallback) onto the GPU (~1-3s);
`voicectl` prints `loading models… (first arm, ~1–3 s)` to stderr while it loads. After
that first arm the recorder stays **resident** (~0.5-3 GB VRAM) so later arms are
instant. It is torn down on `quit`/shutdown AND after `asr.auto_unload_idle_seconds`
(default 1800s = 30 min) DISARMED — so the load cost is paid once per ~30 min of actual
use, not once per boot. The clock starts on disarm (manual stop, toggle-off, or the 30s
auto-stop) and resets on any arm; time listening doesn't count. The next arm then
reloads (~1-3s) like a session's first arm.

`voicectl status` surfaces the lifecycle: `phase:` is `unloaded` (boot /
idle-unloaded), `loading` (first arm), `idle` (loaded, disarmed), or `listening`
(armed). Disarming the mic — a manual `stop`, a `toggle` off, or the 30 s auto-stop —
transitions `phase` back to **`idle`** (loaded, not listening), so a stopped daemon never
reports a stale `listening`/`speaking` while `listening:` is off. The journal logs
`voice-typing device resolved: device=… compute_type=… model=…` at startup,
`voice-typing models loaded (recorder-host child ready); resident` on load, and
`voice-typing idle-unload: 1800.0s disarmed; unloading models` on idle teardown.

Check VRAM by state:

```
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

At boot / after idle-unload this lists nothing (~0 VRAM); while loaded it shows
the daemon's process tree (~0.5-3 GB).

Stop or disable the daemon:

```
systemctl --user stop voice-typing
systemctl --user disable voice-typing
```

`voicectl quit` and `systemctl --user stop` (and any session logout, which systemd
signals with SIGTERM) complete in seconds. Teardown is **single-flight and
bounded**: `RecorderHost.stop()` joins the recorder-host child for up to 5 s, then
SIGKILLs its process group, so VRAM is force-released even when
`recorder.shutdown()` wedges in RealtimeSTT's thread joins. One teardown therefore
takes a few seconds — comfortably under the unit's `TimeoutStopSec=15`, so there is
no systemd `Failed with result 'timeout'` / SIGKILL. The teardown is single-flight
under a lock, so the SIGTERM signal-handler thread and the main-thread `finally`
block no longer race a second, parallel teardown (that double-teardown was what blew
the 15 s budget on `systemctl stop` while armed).
