# voice-typing

Fully-local voice typing for Linux. Speak into your mic and the recognized text is
typed into whatever window or tmux pane has focus. Built on RealtimeSTT
(faster-whisper / CTranslate2 on CUDA). Intended for an Arch + Wayland / Hyprland +
tmux desktop. The recognizer runs 100% on your machine; nothing is sent to a cloud.
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
- `tmux`, optional, only for the live partials in the status line.
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
7. Prints the usage line, the tmux snippet, the Hyprland source line, and the logs
   command.

When install.sh finishes, the daemon is **running, NOT listening, and NOT loaded**
(~0 VRAM). It never hot-mics on boot and loads no models until the first
`voicectl toggle` (~1-3s). Run `voicectl toggle` (or the hotkey) to arm the mic.

## First run

A real-microphone smoke you run by hand. Full paths are used because the desktop zsh
aliases `tmux`, `python3`, and `pip`.

The first `voicectl toggle` (or `start`) each session takes ~1-3s to load the
models — `voicectl` prints `loading models… (first arm, ~1–3 s)` to stderr while
it loads. Subsequent arms are instant (models stay resident until `quit` or 30 min
disarmed; see [Model lifecycle & VRAM](#model-lifecycle--vram)).

```
systemctl --user start voice-typing
/home/<you>/projects/voice-typing/.venv/bin/voicectl toggle   # arms the mic
# speak. Watch the tmux status line for live partials, or the hyprctl toasts:
#   the first arm shows "Loading…" then "Recording"; later arms just "Recording";
#   disarming shows "Recording Stopped" (the ✔ final popup is optional — see feedback.notify_on_final).
/home/<you>/projects/voice-typing/.venv/bin/voicectl toggle   # disarms
```

Expected behavior while listening: live partial words appear in the tmux status
line as you speak; shortly after you pause, the finalized text is typed into the
focused window. A pause does **not** end the session. The recognizer segments
utterances and keeps listening; only `voicectl stop` (or toggle off) disarms the
mic.

If the mic never arms or finals never appear, the two knobs to reach for are the
microphone default source (Troubleshooting) and `post_speech_silence_duration`
(Configuration).

## Hotkey (Hyprland)

Bind **Ctrl+Alt+Super+D** for the big model (normal mode) and **Alt+Super+D** for **lite mode**
(small model only — faster, lower accuracy, for short quips). Add this one line to
`~/.config/hypr/hyprland.conf` (install.sh prints it; the repo never edits your
hyprland.conf):

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
bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite
```

**Normal / big mode** (`Ctrl+Alt+Super+D`) loads `distil-large-v3` + `small.en` — high accuracy,
slower finals. **Lite / little mode** (`Alt+Super+D`) loads ONLY `small.en` (the large model never
runs) — ~half the VRAM and markedly faster finals, at lower accuracy. Good for short snippets
(URLs, shell commands, quick replies) where the big model's latency isn't worth it. Each key
toggles its own mode on/off; to switch modes, press the active key to stop, then the other key to
start in its mode (switching reloads the model set, ~1–3 s, same as a cold first arm). The mode is
shown in `voicectl status` and the tmux status line (a `⚡` prefix in lite).

Hyprland uses the last matching bind for a given MODS+key. Source this file LAST
(at the bottom of `hyprland.conf`) so its binds win. If a bind is inert, your config may
already bind that MODS+key elsewhere. Check `~/.config/hypr/custom/keybinds.conf`,
or rebind to a free combo in `hypr-binds.conf`.

## Lite mode

A second arming mode for short, speed-critical snippets (URLs, shell commands, quick
replies) where latency matters more than accuracy. Lite mode loads **only** `asr.lite_model`
(default `small.en`) and uses it for both live partials AND finals — the large
`distil-large-v3` never loads — so it takes ~half the VRAM and produces markedly faster
finals, at lower accuracy. It also uses its own shorter silence threshold
(`asr.lite_post_speech_silence_duration`, default `0.5` s vs the normal `0.6`) — the silence
gate, not the model, is the perceived-latency bottleneck, so shortening it is what makes lite
feel instant rather than merely transcribing a little faster. Arm it with `voicectl toggle-lite` / `start-lite`, or the
**Alt+Super+D** keybind (`voicectl stop` disarms either mode). Arming the *other* mode while
one is resident tears the recorder down and respawns it (~1–3 s reload, same as a cold first
arm) — so switching modes costs one reload. Both modes share the graceful drain on stop
(§4.2 #2), the 30 s auto-stop, and idle-unload. The armed mode shows in `voicectl status`
(`mode:`), `state.json` (`mode`), and the tmux status line (a `⚡` prefix in lite). See
[Hotkey](#hotkey-hyprland) for the binds and [Model lifecycle & VRAM](#model-lifecycle--vram).

## tmux status line

Add these two lines to `~/.tmux.conf` (install.sh prints them; the repo never edits
your tmux.conf):

```
set -g status-interval 1
set -g status-right "#(/home/<you>/projects/voice-typing/voice_typing/status.sh)"
```

Result: while listening, `status-right` shows the current text (live partials while you
speak, then the finalized text once it's typed) preceded by a microphone emoji,
truncated to 60 characters with a trailing `…` on overflow (widen it with
`tmux set-environment VOICE_TYPING_STATUS_MAX 80`). When idle it is blank. The text
comes from the daemon's atomic writes to a state file at
`$XDG_RUNTIME_DIR/voice-typing/state.json`, which `status.sh` reads each second.

## Configuration

The config file lives at `~/.config/voice-typing/config.toml` (install.sh copies
the repo default there if it is missing). Edit it, then restart the daemon:

```
systemctl --user restart voice-typing
```

Real tunable keys (every key below is a real field in `voice_typing/config.py`):

| Section.key | Default | Effect |
| --- | --- | --- |
| `asr.post_speech_silence_duration` | `0.6` | seconds of silence before a final is emitted. Lower is snappier but can cut deliberate pauses. |
| `asr.lite_post_speech_silence_duration` | `0.5` | lite-mode silence threshold — seconds of silence before a final in **lite mode**. Lower is snappier (0.3 = razor-snappy, may split a brief pause; 0.6 = safe). The silence gate, not the model size, is the perceived-latency bottleneck — this is what makes lite **feel** instant. |
| `asr.realtime_processing_pause` | `0.15` | cadence of the live partial previews. Lower is more responsive; higher uses less CPU. |
| `asr.auto_stop_idle_seconds` | `30.0` | auto-disarm (stop listening) after this many seconds with no recognized speech — partials reset the clock while you talk, so it only fires when you truly go silent (a forgotten hot-mic guard, not a mid-thought cut). `0` disables. Fires the normal `Recording Stopped` toast + a journal line. |
| `asr.auto_unload_idle_seconds` | `1800.0` | after this many seconds DISARMED (models loaded, not listening), tear down the recorder to free VRAM (~0). The clock starts on disarm (manual stop, toggle-off, or the 30s auto-stop) and resets on any arm; time listening doesn't count. `0` disables (models then stay resident until `quit`). The next arm reloads (~1-3s). See Model lifecycle. |
| `asr.device` | `"cuda"` | `"cuda"` or `"cpu"`. Auto-falls-back to `cpu` if no CUDA device is visible. |
| `asr.final_model` | `"distil-large-v3"` | the model whose output gets typed. |
| `asr.realtime_model` | `"small.en"` | the fast model that produces live partials. |
| `asr.lite_model` | `"small.en"` | the SINGLE model loaded in **lite mode** (`toggle-lite` / Alt+Super+D) — used for both partials AND finals, so the large model never loads. ~half VRAM + faster finals, lower accuracy. |
| `asr.language` | `"en"` | ISO-639-1 code. |
| `output.backend` | `"wtype"` | `"wtype"` (Wayland virtual keyboard), `"ydotool"` (uinput), or `"tmux"`. `wtype` auto-falls-back to `ydotool`. |
| `output.tmux_target` | `""` | pane target, used only when `backend="tmux"`, e.g. `"voicetest:0.0"`. |
| `output.append_space` | `true` | append one trailing space after each final. |
| `feedback.notify_on_final` | `true` | also pop a hyprctl popup with each final's text (`✔ <text>`). Set `false` to keep only the brief `Recording` / `Recording Stopped` toasts — the text is already typed into the focused window and shown in the tmux status line, so the final popup is redundant. |
| `feedback.notify_ms` | `2500` | how long hyprctl popups stay on screen (ms). Lower for a brief start/stop flash. |
| `feedback.hypr_notify` | `true` | master on/off for ALL hyprctl popups. `false` suppresses the start/stop toasts too (`notify_on_final` only adds the per-final ✔ popup; this is the global kill switch). |
| `filter.min_chars` | `2` | finals shorter than this are dropped. |
| `filter.blocklist` | list | exact, case-insensitive phrases dropped (classic Whisper silence hallucinations). |
| `log.level` | `"INFO"` | `"INFO"` (per-utterance latency line) or `"DEBUG"` (raw timestamps). |

### Voice-activity constants are NOT config keys

`silero_sensitivity`, `webrtc_sensitivity`, `min_length_of_recording`,
`min_gap_between_recordings`, and `silero_backend` are **not** config keys. They are
constants in `voice_typing/daemon.py` (the `_FIXED_KWARGS` dict). `compute_type` is
also not a config key; it is derived from `device` (`float16` on cuda, `int8` on
cpu).

To change VAD sensitivity, edit `daemon.py` and restart the daemon. Do **not** add
these names to `config.toml`. The config loader (`config.py`) rejects unknown keys
with `TypeError`, so a stray key makes the daemon fail to load and systemd's
`Restart=on-failure` loops it forever. A value of the **wrong type** is rejected the
same way: `auto_stop_idle_seconds = "thirty"` (a string where a number is expected)
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
   derives `compute_type="int8"`. If a GPU is present, it still uses your configured
   `final_model` and `realtime_model`, just on CPU with int8 quantization.
2. Auto-fallback. When `ctranslate2` sees zero CUDA devices at startup, the daemon
   overrides to `device="cpu"`, `compute_type="int8"`, and the smaller models
   `small.en` (final) and `tiny.en` (realtime), regardless of config.
3. Construction-failure fallback. The check in #2 only asks whether `ctranslate2` can
   *see* a GPU; it does not load cuDNN. If a GPU is visible but CUDA/cuDNN init then fails
   while building the recorder (for example a missing `libcudnn_ops.so.9` after a stale
   `uv sync`), the daemon retries once on the same CPU config as #2 and keeps running
   instead of crash-looping. `journalctl --user -u voice-typing` shows
   `CUDA recorder construction failed (...); falling back to CPU ... — degraded but
   functional` then `daemon started in degraded CPU mode`, and `voicectl status` reports
   `device: cpu (int8)`. Fix the library path (see the cuDNN section under Troubleshooting)
   and restart to return to the GPU.

`voicectl status` reports the resolved device and models (see Logs below), so you
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

To force a single backend, set `[output] backend = "ydotool"` (or `"tmux"` for a
specific pane). Restart the daemon after editing.

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

Typical CUDA output:

```
listening: on
mode: normal
phase: listening
partial: this is what i am say
last: Previous sentence.
uptime: 42.3s
device: cuda (float16)
models: distil-large-v3 + small.en (loaded)
mic: ok
```

`mode:` is `normal` (the two-model high-accuracy set) or `lite` (the single small model — see
[Hotkey](#hotkey-hyprland)); `phase:` is `unloaded` at boot (no models), `loading` on the first arm, then
`idle`/`listening`; the `(loaded)`/`(not loaded)` marker on the `models:` line
tells you whether models are resident. On CPU fallback, `device` shows `cpu (int8)`
and `models` shows `small.en + tiny.en (loaded)` once the CPU recorder is built.
If the mic is unavailable, the last line reads `mic: unavailable (<reason>)`
instead.

### Model lifecycle & VRAM

At boot the daemon is **unloaded**: no recorder, no CUDA context, **~0 VRAM** —
models do NOT load at boot. The first `voicectl start`/`toggle` (or hotkey) each
session loads `small.en` + `distil-large-v3` onto the GPU (~1-3s); `voicectl`
prints `loading models… (first arm, ~1–3 s)` to stderr while it loads. After that
first arm the recorder stays **resident** (~1.5-3 GB VRAM) so later arms are
instant. In **lite mode** the resident set is just `small.en` (~half the VRAM of normal);
idle-unload tears down whichever mode is resident, and the next arm reloads in whatever mode
that arm requests. It is torn down on `quit`/shutdown AND after
`asr.auto_unload_idle_seconds` (default 1800s = 30 min) DISARMED — so the load cost
is paid once per ~30 min of actual use, not once per boot. The clock starts on
disarm (manual stop, toggle-off, or the 30s auto-stop) and resets on any arm; time
listening doesn't count. The next arm then reloads (~1-3s) like a session's first
arm.

`voicectl status` surfaces the lifecycle: `phase:` is `unloaded` (boot /
idle-unloaded), `loading` (first arm), `idle` (loaded, disarmed), or `listening`
(armed); the `models:` line ends in `(loaded)` or `(not loaded)`. Disarming the mic
— a manual `stop`, a `toggle` off, or the 30 s auto-stop — transitions `phase` back
to **`idle`** (loaded, not listening), so a stopped daemon never reports a stale
`listening`/`speaking` while `listening:` is off. The journal logs
`voice-typing models loaded (lazy load complete); recorder resident` on load and
`voice-typing idle-unload: 1800.0s disarmed; unloading models` on idle teardown.

Check VRAM by state:

```
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

At boot / after idle-unload this lists nothing (~0 VRAM); while loaded it shows
the daemon's process tree (~1.5-3 GB).

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
