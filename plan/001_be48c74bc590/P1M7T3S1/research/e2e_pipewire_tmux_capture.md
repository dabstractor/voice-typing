# Research — P1.M7.T3.S1 `e2e_virtual_mic.sh` (PRD §6 T3)

End-to-end test: real PipeWire null-sink + `pw-cat` playback + the real daemon (tmux backend) +
`voicectl` control, validating PRD acceptance criteria **2** (≥3 s pause loses zero words),
**3** (live partials observable), and **4** (nothing typed while toggled off).

Every claim below was **verified empirically on this exact machine** (2026-07-07) by running the
commands. The command transcripts are summarized; the pinning is what the bash script must rely on.

---

## §1. PipeWire null-sink lifecycle (VERIFIED — `pactl` via the pipewire-pulse compat daemon)

The machine runs **PipeWire 1.6.6** with a `pipewire-pulse` PulseAudio-compat server. `pactl` talks
to it. All of the following were run and confirmed:

```bash
# record the user's REAL default source FIRST (must restore on exit via trap)
ORIG_SRC="$(pactl get-default-source)"        # -> alsa_input.usb-Sonix...mono-fallback (the webcam mic)
# create the virtual sink (returns the MODULE INDEX on stdout — capture it!)
MODIDX="$(pactl load-module module-null-sink sink_name=vt_test media.class=Audio/Sink)"   # -> 536870916
# a monitor SOURCE now exists, named "<sink_name>.monitor"
pactl list short sources | grep vt_test        # -> "<n>  vt_test.monitor  PipeWire  float32le 2ch 48000Hz  SUSPENDED"
# point the system default input at the monitor
pactl set-default-source vt_test.monitor
pactl get-default-source                       # -> "vt_test.monitor"
# ... run the daemon + play WAVs here ...
# cleanup (in the trap, idempotent + best-effort)
pactl set-default-source "$ORIG_SRC"           # restore the user's mic
pactl unload-module "$MODIDX"                  # unload by the INDEX (NOT by name — see §1 gotcha)
pactl list short sources | grep vt_test || echo "gone"   # confirm the monitor source disappeared
```

**Verified facts:**
- `pactl get-default-source` → prints the current default source name (one token). Record it. ✓
- `pactl load-module module-null-sink sink_name=vt_test media.class=Audio/Sink` → prints the module
  **index** (a large integer, e.g. `536870916`) to stdout. **Capture it** for unloading. ✓
- The monitor source is named exactly **`vt_test.monitor`** (sink name + `.monitor`). ✓
- `pactl set-default-source vt_test.monitor` works; `pactl get-default-source` reflects it. ✓
- `pactl unload-module "$MODIDX"` removes the sink + its monitor; restore + unload leave no trace. ✓

**§1 GOTCHA (unload by INDEX, not name):** `pactl help` shows `unload-module NAME|#N`. Unloading by
the **module name** `module-null-sink` would unload **ALL** null-sink instances the user may have
(their own loopbacks, etc.) — destructive. **Always unload by the captured index.** (Verified the
index unloads exactly our sink + monitor.)

---

## §2. Audio routing into the monitor (VERIFIED end-to-end — non-silent capture)

`pw-cat` (PipeWire's native player/recorder) drives the path. **Verified a full round-trip**:
play a WAV into the sink while recording its monitor to a file → the recording is non-silent
(RMS 0.084), proving `pw-cat → null-sink → monitor` carries real audio.

```bash
# PLAY a WAV into the sink (background; --target = the sink NAME, not the monitor)
pw-cat -p --target vt_test tests/out/utt_pause.wav &

# (for a pure round-trip proof — RECORD the monitor to a wav file)
pw-cat -r --target vt_test.monitor --container wav /tmp/rec.wav
```

**Verified facts:**
- `pw-cat -p --target <sink_name> <file.wav>` plays into the sink. The `--target` is the **node
  name** (the sink name `vt_test`), NOT the `.monitor`. (`pw-cat --help`: "`--target` Set node
  target serial or name".) ✓
- `pw-cat -r --target vt_test.monitor --container wav <out.wav>` records the monitor. The output
  file is a positional arg; `--container wav` selects the WAV container (inferred from extension
  too). ✓
- Round-trip RMS 0.084 (non-silent) → the audio path carries speech. ✓
- `pw-cat --version` → "Compiled with libpipewire 1.6.6". ✓

**§2 GOTCHA (pw-cat record invocation):** `pw-cat --record` does NOT write raw samples to stdout,
and `--output FILE`/`-o` is NOT a flag. The output file is a **positional** argument and you must
give `--container wav` (or a `.wav` extension) for a WAV. Plain `pw-cat -r ... > file` exits with a
usage error (prints help). (The E2E test itself only **plays** WAVs; recording is unnecessary — the
daemon is the consumer. This is documented in case a round-trip self-check is wanted.)

**§2 fallbacks (also present on this machine):** `paplay` / `parecord` (PulseAudio-utils) respect
`set-default-source`/`set-default-sink` too and are simpler (`paplay file.wav` plays to the default
sink). `pw-cat` is the PRD-mandated player; `paplay` is a fallback if `pw-cat --target` misbehaves.

---

## §3. How the (unmodified) daemon reads from the monitor (VERIFIED — this is the core routing fact)

The daemon constructs its RealtimeSTT recorder via `voice_typing/daemon.py::cfg_to_kwargs`, which
does **NOT** set `input_device_index`. Confirmed in the **installed RealtimeSTT 1.0.2 source**:

`audio_input.py:136-137`:
```python
actual_device_index = (self.input_device_index if self.input_device_index is not None
                    else self.audio_interface.get_default_input_device_info()['index'])
```
→ when `input_device_index` is `None` (the daemon's case), RealtimeSTT opens **PyAudio's default
input device**.

**Verified PyAudio follows `set-default-source`:** after `pactl set-default-source vt_test.monitor`,
`pyaudio.PyAudio().get_default_input_device_info()` returns a device literally named **`'default'`**
(the PulseAudio virtual default = whatever the default source is) → routes to `vt_test.monitor`. ✓

**Verified the monitor is visible to PyAudio** (the required "list PyAudio devices + grep" helper):
enumerating input devices shows `idx=33 name='vt_test Audio/Sink sink'` (PipeWire exposes the
monitor under this mangled PulseAudio name). ✓ **§3 GOTCHA:** the PyAudio device **name** is
`'vt_test Audio/Sink sink'`, NOT `'vt_test.monitor'` — the helper greps for **`vt_test`**
(case-insensitive substring), not the exact pactl source name. The helper is a **diagnostic**
(proves the monitor is visible + logs its index); the actual routing is `set-default-source`
(the daemon cannot accept `input_device_index`).

**§3 device-open timing:** the PyAudio stream opens once in `audio_input.py::AudioInput.setup()`,
called by the audio-input worker thread **when the recorder is constructed** (daemon startup) —
`core/audio_input_worker.py:253` `if not setup_audio():` runs before the worker loop. `set_microphone`
only flips the `use_microphone` flag (does NOT re-open the device). ⇒ **Create the null-sink +
`set-default-source vt_test.monitor` BEFORE launching the daemon** so the default input is the
monitor at device-open time. (Doing it before `voicectl start` also suffices, but before daemon
launch is the safe, unambiguous ordering.)

---

## §4. tmux capture — capture-pane, NOT `cat > file` reads (VERIFIED — the #1 gotcha)

The daemon's tmux backend (`typing_backends.py::TmuxBackend.type_text`) runs:
`/usr/bin/tmux send-keys -t <target> -l -- <text>`. With `-l` the keys are **literal** (no
key-name interpretation) and, per PRD §4.3 / `textproc`, the daemon **never sends Enter/newline**
(it appends a single space when `output.append_space`).

**Verified the consequence** (dedicated tmux socket, pane running `cat > file`, `send-keys -l`
without a newline):

| when | `cat > file` content | `tmux capture-pane -p` content |
|---|---|---|
| mid-stream (after 2 `send-keys -l`) | **`''` (EMPTY)** | `"the quick brown fox jumps over"` ✓ |
| after `send-keys C-d` (EOF flush) | `"the quick brown fox jumps over"` ✓ | (same) |

**Why `cat > file` is empty mid-stream:** the pane's pty is in **canonical (cooked) mode** (the
default; `cat` does not set raw mode). The line discipline buffers typed input until a **newline**
or **EOF**, so `cat`'s `read()` never returns → the file is not written. `stdbuf -o0 cat > file`
does NOT fix this — `stdbuf` affects `cat`'s **stdout** buffering, but the input is blocked at the
**pty line-discipline** layer before `cat` ever sees it. Only flushing (newline / `C-d` / pane kill)
delivers the buffered chars to `cat`.

**Why `capture-pane -p` works mid-stream:** the tty line-discipline **echoes** each typed char to
the pane's screen as it arrives (ECHO is on), independent of delivery to `cat`. `capture-pane -p`
dumps the rendered screen → it sees the echoed typed text **live, incrementally, with no flush.**

**Design decision (the PRD sanctions both; capture-pane is the one that works):**
- **Primary capture = `tmux capture-pane -t voicetest -p -S -`** (incremental; `-S -` = full
  scrollback in case text wraps past the pane height). Used for (a) polling until all expected
  finals are typed, (b) the fuzzy-match assertion, and (c) the toggle-off "nothing new typed"
  before/after diff.
- The pane still runs `cat > "$CAPFILE"` (honoring the contract) as a **belt-and-suspenders
  cross-check**: at the very end, `send-keys C-d` flushes `cat`, and `$CAPFILE` must equal the
  capture-pane text. (Not relied upon mid-stream.)
- `capture-pane -p` output may contain trailing blank lines and (if text wraps) multiple lines →
  **strip trailing blank lines, join remaining lines with a space**, then fuzzy-match.

**§4 tmux invocation (VERIFIED on this machine):**
- `/usr/bin/tmux` is the real binary (zsh aliases `tmux`; ALWAYS use the full path — PRD §4.3,
  system_context.md §1). ✓
- A pane running `cat` captures typed text via its tty echo. `capture-pane -p` reads it. ✓
- `tmux 3.6b`. ✓

---

## §5. Isolation constraints (VERIFIED — these shape the test's env setup)

**§5a — XDG_RUNTIME_DIR CANNOT be moved to a temp dir.** The daemon's control socket + state.json
resolve from `$XDG_RUNTIME_DIR` (`voice_typing/daemon.py::_default_control_socket_path`,
`config.py::FeedbackConfig.resolved_state_file`). Naïvely isolating them by setting
`XDG_RUNTIME_DIR=<tmp>` **breaks PyAudio's PulseAudio backend**:

| env for PyAudio probe | default input device | vt_test.monitor visible? |
|---|---|---|
| real `XDG_RUNTIME_DIR=/run/user/1000` | `'default'` (PulseAudio) → routes to monitor | yes (`vt_test Audio/Sink sink`) ✓ |
| temp XDG + `PULSE_SERVER=unix:/run/user/1000/pulse/native` | `'HDA Intel PCH …'` (**ALSA fallback**) | **no** ✗ |
| temp XDG + symlinked `pulse/native` socket | `'HDA Intel PCH …'` (**ALSA fallback**) | **no** ✗ |

PortAudio's PulseAudio backend only engages when the **real** `$XDG_RUNTIME_DIR` (with its real
`pulse/` runtime dir) is in place. `PULSE_SERVER` alone, and a symlinked socket, do NOT re-engage
it → PyAudio falls back to ALSA hardware devices → the monitor is invisible → the daemon records
silence. **So the daemon + pactl/pw-cat MUST run with the real `XDG_RUNTIME_DIR`.**

**§5b — Consequence: the control socket is pinned to the real path**
`/run/user/1000/voice-typing/control.sock`. The daemon's `main()` constructs `ControlServer` with
**no** `socket_path=` override → there is no way (without editing `daemon.py`, off-limits) to move
it. `voicectl` resolves the same real path. So:
- **Preflight REQUIRED:** if a real voice-typing daemon is already running (and bound to that
  socket), the test's daemon cannot bind → `RuntimeError` → daemon exits, AND the real daemon would
  be hijacked by the `set-default-source` change. The test must **detect and refuse**:
  `voicectl status` (real env) → if it exits 0, bail with
  `"stop the voice-typing service first: systemctl --user stop voice-typing"`.
  Belt-and-suspenders: `systemctl --user is-active voice-typing`.

**§5c — state.json isolation IS possible (and should be done) via config override.** Unlike the
control socket, `feedback.state_file` IS configurable. So the test points the daemon's state.json at
a temp path so it (a) does not clobber a real daemon's state, and (b) the partial-polling reads the
TEST daemon's partials. (See §6.)

**§5d — global side effects the test MUST own (trap-restored):** `set-default-source vt_test.monitor`
is GLOBAL — during the test, any other app recording audio would use the monitor. This is inherent
(PRD §6 T3 mandates `set-default-source`) and acceptable; the `trap` restores `ORIG_SRC` on exit.

---

## §6. Config override for the daemon (tmux backend + isolated state.json)

The daemon loads config via `VoiceTypingConfig.load()` (search: `$XDG_CONFIG_HOME/voice-typing/
config.toml` → `<repo>/config.toml` → dataclass defaults). The repo `config.toml` ships
`backend="wtype"`; the test needs `backend="tmux"`, `tmux_target="voicetest:0.0"`, and an isolated
`state_file`. **Set `XDG_CONFIG_HOME=<tmp>/config`** and write a minimal `voice-typing/config.toml`
there overriding ONLY `[output]` + `[feedback]`; the daemon inherits `[asr]`/`[filter]`/`[log]`
from the **dataclass defaults**, which are byte-for-byte identical to the repo `config.toml`'s
values (verified: `final_model="distil-large-v3"`, `device="cuda"`,
`post_speech_silence_duration=0.6`, `silero`-via-fixed-kwargs, blocklist, `level="INFO"`). So the
test daemon runs the SAME production ASR as a real run.

Minimal temp config:
```toml
[output]
backend    = "tmux"
tmux_target = "voicetest:0.0"

[feedback]
state_file  = "/ABS/PATH/TO/TMP/state.json"   # isolated (§5c); real XDG_RUNTIME_DIR untouched
hypr_notify = false                            # silence test-run popups (fire-and-forget; harmless)
```
Launch the daemon with **both** `XDG_CONFIG_HOME=<tmp>/config` (this override) and the **real**
`XDG_RUNTIME_DIR` (so the control socket binds + PyAudio works, §5a).

**§6 GOTCHA (config search picks the temp file over the repo file):** the FIRST existing candidate
wins, and `$XDG_CONFIG_HOME/voice-typing/config.toml` is searched before `<repo>/config.toml`. So
the temp file takes priority. Do NOT edit the repo `config.toml` (off-limits + fragile).

---

## §7. Daemon lifecycle for the test (launch + ready-poll + control + teardown)

- **Launch:** `voice_typing/launch_daemon.sh` (P1.M1.T2.S1) computes LD_LIBRARY_PATH for the
  cuBLAS/cuDNN wheels then `exec`s `.venv/bin/python -m voice_typing.daemon`. Launch it in the
  background with `XDG_CONFIG_HOME=<tmp>/config` + real `XDG_RUNTIME_DIR`, redirecting stdout/stderr
  to a log file. `launch_daemon.sh` `exec`s python, so `$!` is the **python PID** (kill it on trap).
- **Ready-poll:** the daemon loads both Whisper models at startup (seconds to tens of seconds with
  cuDNN init). Poll `voicectl status` (exit 0) up to **~180 s** (generous; cuDNN/cuBLAS cold init is
  the long pole). On ready, `status` prints `device: cuda (float16)` + the models.
- **Control:** `voicectl start` (arm; the daemon starts NOT-listening per PRD §4.9), play WAVs,
  poll state.json for partials, poll capture-pane for typed finals, `voicectl stop` (disarm +
  `abort()`). `voicectl quit` for clean shutdown (releases GPU VRAM) at the end.
- **Teardown (trap, idempotent + best-effort, §1 + §5):** `voicectl quit` → wait → `kill -TERM
  $DAEMON_PID` fallback → `pactl set-default-source "$ORIG_SRC"` → `pactl unload-module "$MODIDX"`
  → `tmux kill-session -t voicetest` → `rm -rf <tmp>`. Order is not load-bearing (all idempotent);
  the trap fires on EXIT (covers success + error + Ctrl-C).

---

## §8. Assertion strategy → PRD acceptance criteria 2 / 3 / 4

**Canonical fuzzy targets** (PINNED in `tests/make_test_audio.sh`, single source; the test
hardcodes the same values + L4 cross-checks them against the generator, mirroring P1.M7.T2.S1):
```
PAUSE_A="I want to test whether this system"   PAUSE_B="keeps listening after a pause."
MULTI_TEXTS=("The weather looks good today." "I need to buy some groceries." "Let us meet at the cafe.")
```

**Fuzzy match (PRD §6 ≥80 % token overlap, case/punct-insensitive):** implemented as a python
one-liner invoked from bash (uses the venv's stdlib only): multiset token intersection / ref-length.
The test joins the capture-pane text, then for each canonical ref asserts overlap ≥ 0.80.

- **Criterion 2 (≥3 s pause loses zero words):** play `utt_pause.wav` → the typed text fuzzy-matches
  BOTH `PAUSE_A` and `PAUSE_B` (≥0.80 each). The post-3 s-silence half being present is THE
  WhisperX-flaw regression proof (same as P1.M7.T2.S1 criterion b, but here through the real mic
  path). ✓
- **Criterion (typed text of ALL segments):** play `utt_pause.wav` then `utt_multi.wav`; the typed
  text fuzzy-matches all 5 refs (`PAUSE_A`, `PAUSE_B`, `MULTI_TEXTS[0..2]`). ✓
- **Criterion 3 (live partials observable):** poll `<tmp>/state.json` (the config-overridden path)
  DURING playback (`jq -r .partial`), snapshot it; assert at least one snapshot had a **non-empty**
  `partial`. (feedback.py writes partials at ≥10 Hz, throttled; `jq` reads the atomic write safely.)
  ✓
- **Criterion 4 (toggle-off gates output):** `capture-pane` snapshot → `voicectl stop` → play one
  more WAV (e.g. `utt_simple.wav`) → wait → `capture-pane` again → assert **unchanged** (nothing
  new typed). The daemon's `on_final` gate (`if not self._listening.is_set(): return`, §4.2/§8 risk)
  + the disarmed mic (`set_microphone False` → audio worker stops reading) double-protect this. ✓

---

## §9. Tooling presence (VERIFIED on this machine)

`pactl` `/usr/bin/pactl` ✓ · `pw-cat` `/usr/bin/pw-cat` (libpipewire 1.6.6) ✓ · `pw-cli` ✓ ·
`/usr/bin/tmux` 3.6b ✓ · `jq` ✓ · `stdbuf` (coreutils) ✓ · `paplay`/`parecord` (fallback) ✓.
PipeWire server: `/run/user/1000/pulse/native` (srwxrwxrwx). PyAudio (via realtimestt) uses the
PulseAudio backend under the real `XDG_RUNTIME_DIR`. WAV fixtures `tests/out/*.wav` exist
(generated by P1.M7.T1.S1).

---

## §10. Relationship to the parallel item P1.M7.T2.S1 (no conflict)

P1.M7.T2.S1 creates `tests/test_feed_audio.py` (a pytest module, offline feed_audio). This item
creates `tests/e2e_virtual_mic.sh` (a **bash** script, real PipeWire). **Different files, no
conflict.** Both consume `tests/out/*.wav` + the daemon seams, and both use the SAME canonical
fuzzy strings (pinned in `make_test_audio.sh`) and the same `voice-typing latency:` log prefix
(daemon._LATENCY_LOG_PREFIX). This E2E additionally exercises the real audio path + tmux backend +
voicectl, which the offline test deliberately does not.
