# voice-typing

Fully-local voice typing for Linux. Speak into your mic and the recognized text is
typed into whatever window or tmux pane has focus. Built on RealtimeSTT
(faster-whisper / CTranslate2 on CUDA). Intended for an Arch + Wayland / Hyprland +
tmux desktop. The recognizer runs 100% on your machine; nothing is sent to a cloud.

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

When install.sh finishes, the daemon is **running and NOT listening**. It never
hot-mics on boot. Run `voicectl toggle` (or the hotkey) to arm the mic.

## First run

A real-microphone smoke you run by hand. Full paths are used because the desktop zsh
aliases `tmux`, `python3`, and `pip`.

```
systemctl --user start voice-typing
/home/dustin/projects/voice-typing/.venv/bin/voicectl toggle   # arms the mic
# speak. Watch the tmux status line for live partials, or the hyprctl popups:
#   a dot means listening, a check mark means a final was typed
#   (the ✔ final popup is optional — see feedback.notify_on_final).
/home/dustin/projects/voice-typing/.venv/bin/voicectl toggle   # disarms
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

Bind SUPER+ALT+D to toggle the mic. Add this one line to
`~/.config/hypr/hyprland.conf` (install.sh prints it; the repo never edits your
hyprland.conf):

```
source = /home/dustin/projects/voice-typing/hypr-binds.conf
```

Then reload:

```
hyprctl reload
```

The sourced file is `hypr-binds.conf` at the repo root. Its bind is:

```
bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle
```

Hyprland uses the last matching bind for a given MODS+key. Source this file LAST
(at the bottom of `hyprland.conf`) so its bind wins. If SUPER+ALT+D is inert, your
config may already bind it elsewhere. Check `~/.config/hypr/custom/keybinds.conf`,
or rebind to a free combo in `hypr-binds.conf`.

## tmux status line

Add these two lines to `~/.tmux.conf` (install.sh prints them; the repo never edits
your tmux.conf):

```
set -g status-interval 1
set -g status-right "#(/home/dustin/projects/voice-typing/voice_typing/status.sh)"
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
| `asr.realtime_processing_pause` | `0.15` | cadence of the live partial previews. Lower is more responsive; higher uses less CPU. |
| `asr.device` | `"cuda"` | `"cuda"` or `"cpu"`. Auto-falls-back to `cpu` if no CUDA device is visible. |
| `asr.final_model` | `"distil-large-v3"` | the model whose output gets typed. |
| `asr.realtime_model` | `"small.en"` | the fast model that produces live partials. |
| `asr.language` | `"en"` | ISO-639-1 code. |
| `output.backend` | `"wtype"` | `"wtype"` (Wayland virtual keyboard), `"ydotool"` (uinput), or `"tmux"`. `wtype` auto-falls-back to `ydotool`. |
| `output.tmux_target` | `""` | pane target, used only when `backend="tmux"`, e.g. `"voicetest:0.0"`. |
| `output.append_space` | `true` | append one trailing space after each final. |
| `feedback.notify_on_final` | `true` | also pop a hyprctl popup with each final's text (`✔ <text>`). Set `false` to keep only the brief `●`/`■` start/stop popups — the text is already typed into the focused window and shown in the tmux status line, so the final popup is redundant. |
| `feedback.notify_ms` | `2500` | how long hyprctl popups stay on screen (ms). Lower for a brief start/stop flash. `hypr_notify` is the master on/off switch. |
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
`Restart=on-failure` loops it forever.

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
/home/dustin/projects/voice-typing/.venv/bin/voicectl status
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
LD_DEBUG=libs /home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
ldd /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9
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
`voicectl toggle` (the probe re-runs on each arm).

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
/home/dustin/projects/voice-typing/.venv/bin/voicectl status
```

Typical CUDA output:

```
listening: on
partial: this is what i am say
last: Previous sentence.
uptime: 42.3s
device: cuda (float16)
models: distil-large-v3 + small.en
mic: ok
```

On CPU fallback, `device` shows `cpu (int8)` and `models` shows
`small.en + tiny.en`. If the mic is unavailable, the last line reads
`mic: unavailable (<reason>)` instead.

Confirm the models are resident in GPU VRAM:

```
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

Stop or disable the daemon:

```
systemctl --user stop voice-typing
systemctl --user disable voice-typing
```
