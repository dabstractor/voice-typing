# PRP — P1.M7.T3.S1: `tests/e2e_virtual_mic.sh` — full E2E with virtual mic + tmux (PRD §6 T3)

## Goal

**Feature Goal**: Create **`tests/e2e_virtual_mic.sh`** — the full end‑to‑end test the PRD calls
**T3** (§6). It stands up a real **PipeWire null‑sink** (`vt_test`) + its monitor, points the
system default input at the monitor (`pactl set-default-source vt_test.monitor`), launches the
**real daemon** with the **tmux** typing backend pointed at a `voicetest` tmux pane, drives it with
**`voicectl`** (`start` → play `utt_pause.wav` then `utt_multi.wav` via **`pw-cat -p --target
vt_test`** → poll live partials in `state.json` → wait for finals → `stop`), and **asserts** the
three PRD acceptance criteria that only a real‑audio E2E can prove:

- **Criterion 2** — a ≥3 s mid‑dictation pause loses zero words (both halves of `utt_pause.wav`
  transcribe through the real mic path).
- **Criterion 3** — live partials are observable in `state.json` while audio plays.
- **Criterion 4** — nothing is typed while toggled off (after `voicectl stop`, playing one more WAV
  types nothing new — `on_final` gate + disarmed mic).

A **`trap`** guarantees cleanup on any exit: restore the original default source, unload the null‑
sink module, kill the tmux session, quit/kill the daemon, remove temp files. **The test MUST NOT
leave the user's default source switched** (PRD §6 T3 step 5, verbatim).

**Deliverable** (1 file — 1 ADD; **NO** edit to anything else):
1. `tests/e2e_virtual_mic.sh` — NEW. A `set -euo pipefail` bash script (POSIX/bash‑portable; bash
   ≥4) that performs the setup → run → assert → teardown sequence above. It invokes a tiny
   `.venv/bin/python` one‑liner for the fuzzy token‑overlap assertion (stdlib only) and `jq` for
   reading `state.json`; everything else is `pactl` / `pw-cat` / `/usr/bin/tmux` / `voicectl`.

**Success Definition**:
- (a) `tests/e2e_virtual_mic.sh` exists, is `+x`, and `bash -n` + `shellcheck` (if present) are
  clean.
- (b) `./tests/e2e_virtual_mic.sh` **passes** on this CUDA box (models prefetched, WAVs present),
  printing per‑criterion PASS lines and exiting 0.
- (c) **Criterion 2**: the tmux‑captured typed text fuzzy‑matches (≥80 % token overlap)
  **both** `PAUSE_A` ("I want to test whether this system") **and** `PAUSE_B` ("keeps listening
  after a pause.") — the post‑3 s‑pause half is present (the WhisperX‑flaw regression through the
  real mic path).
- (d) **Typed text of ALL segments**: the captured text fuzzy‑matches all 5 canonical refs
  (`PAUSE_A`, `PAUSE_B`, `MULTI_TEXTS[0..2]`).
- (e) **Criterion 3**: at least one `state.json` snapshot taken **during** playback had a non‑empty
  `partial` field.
- (f) **Criterion 4**: after `voicectl stop`, playing one more WAV leaves the captured text
  **unchanged** (toggle‑off gates output).
- (g) **Cleanup is bulletproof**: after a PASS, an error, or Ctrl‑C, `pactl get-default-source`
  equals the pre‑test value, `vt_test` is gone from `pactl list short sources`, the `voicetest` tmux
  session is gone, and the daemon process is gone (no orphaned GPU workers).
- (h) **Preflight safety**: if a real `voice-typing` daemon is already running, the script refuses
  to start (exit non‑zero, clear message) rather than hijack the default source / fight for the
  control socket.
- (i) No out‑of‑scope edits: NO change to `voice_typing/*`, `pyproject.toml`, `config.toml`,
  `tests/make_test_audio.sh`, `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`; NO README;
  NO `test_feed_audio.py` edit (that is P1.M7.T2.S1).

## User Persona

**Target User**: **dustin / the test‑running developer** who runs `./tests/e2e_virtual_mic.sh` to
prove the whole product works through the real audio stack before declaring the daemon done (PRD §7
acceptance criterion 1: "T1–T4, T6 pass, demonstrated by actual command output"). Secondary: **a
fresh clone** that regenerates `tests/out/*.wav` via `make_test_audio.sh` then runs this script.

**Use Case**: `cd /home/dustin/projects/voice-typing && ./tests/make_test_audio.sh &&
./tests/e2e_virtual_mic.sh` → the script prints its setup steps, the daemon's resolved device/models
(via `voicectl status`), per‑criterion PASS lines, and exits 0. The transcript is the evidence
attached to PRD §7.

**Pain Points Addressed**: (1) PRD §6 T3 mandates this exact test and it does not exist yet. (2) The
offline test (P1.M7.T2.S1) proves the ASR pipeline in‑process; it does NOT prove the real mic path
(null‑sink → monitor → PyAudio default → RealtimeSTT), the tmux typing backend end‑to‑end, the
`voicectl`→daemon control loop, or the toggle‑off gate under real audio. Only this E2E does. (3) The
two non‑obvious traps — (a) **`cat > file` stays empty mid‑stream** because the daemon types with no
newline (pty canonical mode buffers `cat`'s input), so capture must use `tmux capture-pane -p`; and
(b) **moving `XDG_RUNTIME_DIR` to a temp dir breaks PyAudio's PulseAudio backend** (it falls back to
ALSA → the monitor is invisible → silence) — are derived in the research note and encoded here so
the script is correct on the first pass.

## Why

- **This is the only automated test of the real audio path + the typing backend + the control
  loop together.** Unit tests mock the recorder, the socket, and `subprocess`. The offline
  feed_audio test feeds WAVs in‑process (no mic, no typing). PRD §7 criterion 1 requires T3 pass "by
  actual command output" — this script is that output.
- **It proves criterion 4 (toggle‑off gates) under real audio**, which is a safety property: a
  misbehaving gate would type hallucinated/stray text while the user believes the mic is off. The
  `on_final` gate (`if not self._listening.is_set(): return`) + the disarmed mic are only exercised
  end‑to‑end here.
- **It blocks the acceptance milestone.** P1.M7.T4.S1 (idle/GPU tests + the acceptance checklist)
  consumes the conventions this script validates (real daemon launch, `voicectl` control, tmux
  capture, cleanup trap).
- **Scope discipline.** This item is a TEST only (a bash script). It consumes `tests/out/*.wav`
  (P1.M7.T1.S1), the daemon's production seams (`launch_daemon.sh`, `voicectl`, the tmux backend,
  the control socket, `state.json`), and PipeWire/tmux. It does NOT touch any module, config, or
  the audio generator.

## What

A single bash script at `tests/e2e_virtual_mic.sh`. It is a **heavy, real‑stack integration test**
(real PipeWire + real Whisper models on CUDA + real tmux), explicitly run (`./tests/e2e_virtual_mic.sh`),
never part of the fast pytest unit suite.

Phases (see Implementation Blueprint for the pinned pseudocode):

1. **Preflight** — refuse if WAVs are missing, if required tools are absent, or if a daemon is
   already running (`voicectl status` exits 0 / `systemctl --user is-active voice-typing` = active).
2. **Setup (before daemon)** — record `ORIG_SRC`; install the `trap`; create the `vt_test` null‑sink
   (capture module index); `set-default-source vt_test.monitor`; start the `voicetest` tmux pane
   running `cat > "$CAPFILE"`; write the temp `XDG_CONFIG_HOME` config (tmux backend + isolated
   `state_file`).
3. **Launch + ready** — start `launch_daemon.sh` (real `XDG_RUNTIME_DIR` + temp `XDG_CONFIG_HOME`)
   in the background; poll `voicectl status` to ready (≤ ~180 s).
4. **Run** — `voicectl start`; play `utt_pause.wav` then `utt_multi.wav` (`pw-cat -p --target
   vt_test`); poll `state.json` for partials (snapshot non‑empty partials); poll `capture-pane`
   until all 5 canonical refs fuzzy‑match (or timeout).
5. **Toggle‑off** — `capture-pane` snapshot → `voicectl stop` → play `utt_simple.wav` → wait →
   `capture-pane` again → assert unchanged.
6. **Assert + report** — per‑criterion PASS/FAIL lines; exit 0 iff all pass.
7. **Teardown** — the `trap` runs on EXIT: `voicectl quit` → restore source → unload module → kill
   tmux → kill daemon → rm temp.

### Success Criteria

- [ ] `tests/e2e_virtual_mic.sh` exists, `+x`, `bash -n` clean, `shellcheck` clean (if installed).
- [ ] `./tests/e2e_virtual_mic.sh` passes on this CUDA box (WAVs + prefetched models).
- [ ] Criterion 2: typed text fuzzy‑matches BOTH `PAUSE_A` and `PAUSE_B` (≥0.80 each).
- [ ] Typed text fuzzy‑matches all 5 canonical refs.
- [ ] Criterion 3: ≥1 `state.json` snapshot during playback had non‑empty `partial`.
- [ ] Criterion 4: after `voicectl stop` + one more WAV, captured text is unchanged.
- [ ] Cleanup: default source restored, `vt_test` gone, `voicetest` session gone, daemon gone — on
      PASS, error, and Ctrl‑C.
- [ ] Preflight refuses to start if a daemon is already running.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the **exact PipeWire/pactl/pw‑cat
semantics** (commands, return values, the module‑index capture, the monitor naming) are derived in
the research note from a verified transcript; the **two non‑obvious traps** (capture‑pane vs
`cat > file`; real `XDG_RUNTIME_DIR` required for PyAudio) are proven empirically and encoded as
gotchas; the **daemon seams** the script drives (`launch_daemon.sh`, `voicectl`, the tmux backend's
`send-keys -l`, the control‑socket path, `state.json`) are cited with line‑level detail; the
**canonical fuzzy targets** are pinned verbatim (and cross‑checked against `make_test_audio.sh` in
L4); and every validation command is executable as written.

### Documentation & References

```yaml
# MUST READ #1 — THE spec for this test (read FIRST; every claim is backed by a verified command
#                transcript on this exact machine).
- file: plan/001_be48c74bc590/P1M7T3S1/research/e2e_pipewire_tmux_capture.md
  why: "§1 the verified pactl null-sink lifecycle (load-module returns the MODULE INDEX; monitor is
        '<sink>.monitor'; unload by INDEX not name — name unloads ALL null-sinks, destructive). §2 the
        verified pw-cat round-trip (pw-cat -p --target <sink> plays; the full path carries non-silent
        audio, RMS 0.084). §3 the core routing fact: RealtimeSTT uses PyAudio's DEFAULT input when
        input_device_index is None (audio_input.py:136), and PyAudio's default follows
        set-default-source -> the unmodified daemon reads from vt_test.monitor. The monitor is visible
        to PyAudio as name 'vt_test Audio/Sink sink' (helper greps 'vt_test', NOT 'vt_test.monitor').
        Device opens at daemon STARTUP -> create sink + set-default-source BEFORE launching the daemon.
        §4 THE #1 GOTCHA: 'cat > file' is EMPTY mid-stream (pty canonical mode buffers cat's input
        because the daemon types with NO newline); use 'tmux capture-pane -p' (reads tty echo, live).
        §5 isolation: XDG_RUNTIME_DIR CANNOT be temp (PyAudio falls back to ALSA -> monitor invisible);
        the control socket is pinned to the real path -> PREFLIGHT for a running daemon; state.json CAN
        be isolated via config. §6 config override (XDG_CONFIG_HOME temp config.toml; [asr]/[filter]/[log]
        inherit production defaults identical to repo config.toml). §7 daemon lifecycle. §8 assertions."
  critical: "G-CAPTURE: read typed text via 'tmux capture-pane -p -S -' (NOT cat the file mid-stream).
             G-RUNTIME: keep the REAL XDG_RUNTIME_DIR for the daemon + pactl/pw-cat (temp breaks PyAudio).
             G-SOURCE: record ORIG_SRC BEFORE load-module; restore it + unload-module by INDEX in the trap.
             G-TARGET: pw-cat --target takes the SINK NAME (vt_test), not the monitor; capture-pane target
             is the SESSION (voicetest). G-PREFLIGHT: refuse if voicectl status already answers."

# MUST READ #2 — the typing backend the E2E exercises (the tmux send-keys -l contract).
- file: voice_typing/typing_backends.py
  why: "TmuxBackend.type_text runs ['/usr/bin/tmux','send-keys','-t',cfg.output.tmux_target,'-l','--',text]
        — LITERAL keys, NO trailing Enter. This is WHY 'cat > file' buffers (canonical mode) and WHY
        capture-pane (tty echo) is the working capture. _TMUX='/usr/bin/tmux' (zsh aliases tmux; always
        the full path). make_backend(cfg.output) selects tmux when cfg.output.backend=='tmux'. The daemon
        appends a trailing SPACE (cfg.output.append_space) per final — NOT a newline."
  critical: "The daemon NEVER sends Enter/newline. Do not expect 'cat > file' to flush per-final. The
             test's capture-pane read is the only mid-stream source of truth."

# MUST READ #3 — the daemon seams + control protocol + state.json shape the script drives.
- file: voice_typing/daemon.py
  why: "_default_control_socket_path() = $XDG_RUNTIME_DIR/voice-typing/control.sock (REAL path, pinned;
        no override without editing daemon.py -> preflight). VoiceTypingDaemon starts NOT-listening
        (PRD 4.9) -> the script must 'voicectl start' to arm. on_final gates on self._listening (line
        ~267: 'if not self._listening.is_set(): return') -> criterion 4's guard. status_snapshot() ->
        {listening, partial, last_final, device, compute_type, final_model, realtime_model} (voicectl
        status prints these). main() = the lifecycle launch_daemon.sh execs."
  critical: "The daemon binds the REAL control socket; a second daemon cannot bind (RuntimeError) ->
        preflight. 'voicectl quit' -> request_shutdown -> on_quit=daemon.shutdown (releases GPU VRAM)."
- file: voice_typing/ctl.py
  why: "voicectl main() exits 0 (daemon ok) / 1 (logical fail) / 2 (daemon not running). 'status' prints
        the multi-line snapshot; 'start'/'stop' arm/disarm; 'quit' shuts down. Resolves the socket via
        _default_control_socket_path() (real XDG_RUNTIME_DIR)."
  critical: "Use the venv's voicectl: '.venv/bin/voicectl' (or '.venv/bin/python -m voice_typing.ctl').
             exit 0 from 'status' = a daemon is ALREADY running (preflight refusal signal)."

# MUST READ #4 — state.json (the criterion-3 partial source) + the config override surface.
- file: voice_typing/feedback.py
  why: "Feedback writes {listening, phase, partial, last_final, ts} atomically (tempfile+os.replace) to
        cfg.feedback.resolved_state_file(). update_partial is throttled to >=10 Hz disk writes but the
        in-memory partial is always current -> polling state.json DURING playback catches non-empty
        'partial'. The path is OVERRIDABLE via feedback.state_file (config) -> isolate it to a temp path."
  critical: "Read state.json with 'jq -r .partial <file>' (atomic write -> safe concurrent read). The test
             config sets feedback.state_file=<tmp>/state.json so it reads the TEST daemon's partials, not
             a real daemon's."
- file: voice_typing/config.py
  why: "VoiceTypingConfig.load() search: $XDG_CONFIG_HOME/voice-typing/config.toml -> <repo>/config.toml
        -> dataclass defaults. FeedbackConfig.state_file='' -> resolved_state_file() = $XDG_RUNTIME_DIR/
        voice-typing/state.json (RAISES if XDG_RUNTIME_DIR unset). AsrConfig/FilterConfig/LogConfig
        defaults == repo config.toml values (verified)."
  critical: "Set XDG_CONFIG_HOME=<tmp>/config with a minimal config.toml overriding ONLY [output]+[feedback];
             [asr]/[filter]/[log] inherit production defaults. Do NOT edit the repo config.toml."

# MUST READ #5 — the daemon launcher (LD_LIBRARY_PATH for cuDNN/cuBLAS) the script execs.
- file: voice_typing/launch_daemon.sh
  why: "Computes LD_LIBRARY_PATH from the live nvidia-cublas/cudnn wheels then 'exec .venv/bin/python -m
        voice_typing.daemon'. Because it 'exec's, the backgrounded PID ($!) IS the python PID -> kill it on
        trap. Without this wrapper, ctranslate2 fails to load libcudnn_ops.so.9 (PRD 8 risk #1)."
  critical: "Launch 'voice_typing/launch_daemon.sh' (NOT raw python) so CUDA libs resolve. Pass
             XDG_CONFIG_HOME=<tmp>/config + the REAL XDG_RUNTIME_DIR in its env."

# MUST READ #6 — the canonical fuzzy targets (PINNED in make_test_audio.sh; single source).
- file: tests/make_test_audio.sh
  why: "PAUSE_A/PAUSE_B/MULTI_TEXTS are PINNED here. The script's expected strings MUST equal these
        verbatim (PRD 6). Documents the fuzzy >=80% rule + the 3.0 s embedded silence in utt_pause.wav."
  critical: "Copy the 5 canonical strings verbatim into the script (see Implementation Blueprint). L4
             cross-checks them against the generator."

# MUST READ #7 — PRD 6 T3 (the contract) + 7 acceptance (why this test matters).
- file: PRD.md
  why: "6 T3 enumerates the 5 steps verbatim (null-sink; tmux cat>file; voicectl start; play pause+multi;
        assert all segments incl post-pause half + partials observed + nothing typed after stop; trap
        cleanup). 7 criteria 1 (T1-T4/T6 pass by output), 2 (>=3s pause loses zero words), 3 (live
        partials), 4 (nothing typed while off)."
  critical: "The PRD sanctions BOTH 'cat > file' AND 'capture-pane'; this PRP uses capture-pane as primary
        (it is the one that works mid-stream for newline-free typing) and cat>file as an end-of-run
        cross-check. The trap MUST restore the default source (PRD 6 T3 step 5)."

# External — PipeWire/pactl/pw-cat reference (corroborates research §1/§2).
- url: https://gitlab.freedesktop.org/pipewire/pipewire/-/blob/master/doc/man/pw-cat.1.rst
  why: "pw-cat man page: '-p/--playback', '-r/--record', '--target' (node name or serial), the output
        file is positional, '--container' selects the container. Corroborates the verified invocation."
- url: https://wiki.archlinux.org/title/PipeWire#Audio
  why: "pactl load-module module-null-sink + the .monitor source convention under pipewire-pulse."
```

### Current Codebase tree (state at P1.M7.T3.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── .gitignore                 # READ-ONLY (tests/out/ ignored via tests/out/.gitignore — do NOT touch root)
├── PRD.md                     # READ-ONLY (§6 T3 contract; §7 acceptance)
├── pyproject.toml uv.lock     # DO NOT touch ([project.scripts] voicectl + voice-typing-daemon present)
├── config.toml                # DO NOT touch (the test overrides via XDG_CONFIG_HOME, NOT by editing this)
├── voice_typing/              # READ-ONLY (daemon.py/ctl.py/feedback.py/config.py/typing_backends.py = seams;
│   ├── launch_daemon.sh       #   the LD_LIBRARY_PATH wrapper the script execs)
│   └── ...
├── tests/                     # ← the script lands HERE
│   ├── make_test_audio.sh     # P1.M7.T1.S1 (DONE) — generator; canonical texts PINNED here (+x)
│   ├── test_*.py              # unit tests (fast; read-only; house style)
│   ├── test_feed_audio.py     # P1.M7.T2.S1 (PARALLEL) — offline feed_audio; DIFFERENT file, no conflict
│   ├── e2e_virtual_mic.sh     # ← CREATE (this task; the ONLY committed artifact)
│   └── out/{utt_simple,utt_pause,utt_multi,utt_punct}.wav   # consumed (regenerable; 16000 Hz/1ch/16-bit)
# venv: .venv/bin/voicectl, .venv/bin/python (fuzzy-match one-liner). System: pactl/pw-cat/jq/tmux.
```

### Desired Codebase tree with files to be added

```bash
tests/
├── e2e_virtual_mic.sh         # NEW — this task's sole artifact (the real-stack PRD-T3 E2E test, +x)
├── make_test_audio.sh         # unchanged (P1.M7.T1.S1)
└── out/*.wav                  # consumed (regenerated by make_test_audio.sh)
# NOTHING ELSE is committed. No temp files (the script mktemp -d's its work under /tmp and trap-rm's it).
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G-CAPTURE) — 'cat > file' is EMPTY mid-stream; use 'tmux capture-pane -p'.
#   The daemon's TmuxBackend sends LITERAL keys with NO trailing newline (typing_backends.py -l flag;
#   textproc strips newlines; output.append_space adds a SPACE). The pane's pty is in CANONICAL mode
#   (cat does not set raw mode) -> the line-discipline buffers input until a newline/EOF -> cat's read()
#   never returns -> the file is not written. 'stdbuf -o0 cat > file' does NOT fix it (stdbuf affects
#   cat's STDOUT, but the block is at the PTY INPUT layer).
#   => Read typed text via '/usr/bin/tmux capture-pane -t voicetest -p -S -' (reads the tty ECHO, which
#      renders each typed char to the screen LIVE, independent of delivery to cat). Verified: capture-pane
#      shows the text mid-stream; the file matches only after a C-d flush. Strip trailing blank lines and
#      join wrapped lines (collapse newlines -> spaces) before fuzzy-matching.
#   => Keep the pane running 'cat > "$CAPFILE"' (honoring the contract); at the very end send 'C-d' to
#      flush and assert $CAPFILE == the capture-pane text (belt-and-suspenders; not relied on mid-stream).

# CRITICAL #2 (G-RUNTIME) — keep the REAL XDG_RUNTIME_DIR; do NOT move it to a temp dir.
#   The daemon's control socket + state.json resolve from $XDG_RUNTIME_DIR, so isolating them by setting
#   XDG_RUNTIME_DIR=<tmp> is tempting — but it BREAKS PyAudio's PulseAudio backend: PortAudio falls back
#   to ALSA hardware devices, vt_test.monitor becomes INVISIBLE, and the daemon records silence.
#   PULSE_SERVER alone and a symlinked pulse/native socket do NOT re-engage the PA backend (verified).
#   => Run the daemon + pactl/pw-cat with the inherited (real) XDG_RUNTIME_DIR.
#   => Isolate state.json via the CONFIG override (feedback.state_file=<tmp>/state.json), NOT via XDG.
#   => The control socket is pinned to the REAL path (/run/user/1000/voice-typing/control.sock); there is
#      no override without editing daemon.py (off-limits) -> PREFLIGHT for a running daemon (G-PREFLIGHT).

# CRITICAL #3 (G-SOURCE) — record ORIG_SRC BEFORE load-module; restore + unload by INDEX in the trap.
#   'pactl set-default-source vt_test.monitor' is GLOBAL (any app recording during the test uses the
#   monitor). The trap MUST restore the original on EVERY exit (PASS, error, Ctrl-C) — the PRD's hard
#   rule ("MUST NOT leave the user's default source switched").
#   => ORIG_SRC="$(pactl get-default-source)" as the FIRST setup step.
#   => 'pactl load-module ...' returns the MODULE INDEX on stdout (e.g. 536870916) — capture it.
#   => 'pactl unload-module "$MODIDX"' (by INDEX). NEVER unload by the module NAME 'module-null-sink'
#      (pactl unloads ALL instances -> destroys the user's own loopbacks/null-sinks).

# CRITICAL #4 (G-TARGET) — pw-cat --target is the SINK NAME; capture-pane target is the SESSION.
#   pw-cat -p --target vt_test file.wav   (--target = node name 'vt_test', NOT 'vt_test.monitor').
#   /usr/bin/tmux capture-pane -t voicetest -p   (target = session 'voicetest' = its active pane; the
#   daemon's tmux_target 'voicetest:0.0' also resolves here).

# CRITICAL #5 (G-PREFLIGHT) — refuse if a daemon is already running.
#   'voicectl status' (real env) exiting 0 means a daemon holds the real control socket; the test's
#   daemon could not bind (RuntimeError) AND the real daemon would be hijacked by set-default-source.
#   => Preflight: if voicectl status returns 0, OR systemctl --user is-active voice-typing = active,
#      print "stop voice-typing first: systemctl --user stop voice-typing" and exit non-zero.

# CRITICAL #6 (G-CONFIG) — override via XDG_CONFIG_HOME, NOT by editing config.toml.
#   Set XDG_CONFIG_HOME=<tmp>/config and write voice-typing/config.toml overriding [output] (backend=tmux,
#   tmux_target='voicetest:0.0') + [feedback] (state_file=<tmp>/state.json, hypr_notify=false). [asr]/
#   [filter]/[log] inherit dataclass defaults == repo config.toml values (verified) -> same production ASR.
#   => launch_daemon.sh with BOTH XDG_CONFIG_HOME=<tmp>/config AND the real XDG_RUNTIME_DIR in its env.

# CRITICAL #7 (G-TMUX-PATH) — ALWAYS use /usr/bin/tmux (zsh aliases tmux; system_context.md 1).
#   Both the daemon (typing_backends._TMUX) and this script invoke '/usr/bin/tmux'.

# CRITICAL #8 (G-ORDERING) — create sink + set-default-source BEFORE launching the daemon.
#   RealtimeSTT opens the PyAudio stream ONCE at recorder construction (daemon startup:
#   core/audio_input_worker.py:253 setup_audio() before the worker loop) on the default input device AT
#   THAT MOMENT. set_microphone only flips a flag (does not re-open). => The null-sink + set-default-source
#   must precede daemon launch so the default input is vt_test.monitor at open time.

# CRITICAL #9 (G-FUZZY) — fuzzy token overlap (>=80%, case/punct-insensitive) is the script's job.
#   Implement as a '.venv/bin/python - <<PY ... PY' one-liner: tokenize (strip punctuation, lowercase),
#   multiset intersection / ref-length. Pass the captured text + the 5 refs; exit 0 iff all >=0.80.
#   espeak is robotic -> exact match is brittle (PRD 6); the 80% floor is the contract.

# CRITICAL #10 (G-POLL-TIMEOUTS) — generous timeouts; model load is the long pole.
#   Daemon ready: poll voicectl status up to ~180 s (cuDNN/cuBLAS cold init + 2 model loads).
#   Typed text: poll capture-pane until all 5 refs fuzzy-match, up to ~90 s after playback ends
#   (finals land after post_speech_silence_duration=0.6 s each; 5 finals; plus Whisper time).
#   state.json partials: poll every ~0.2 s DURING playback; require >=1 non-empty snapshot.

# CRITICAL #11 (G-CLEANUP-IDEMPOTENT) — the trap must be idempotent + best-effort.
#   Each cleanup step (voicectl quit, kill PID, restore source, unload module, kill tmux session, rm tmp)
#   can fail if a prior step already ran or never started -> wrap each in '|| true' / '2>/dev/null'. The
#   trap fires on EXIT (set -e aborts on error -> EXIT still runs the trap -> cleanup always happens).

# CRITICAL #12 (G-CAPTURE-PANE-FILTER) — strip noise from capture-pane output.
#   capture-pane -p may include trailing blank lines and (if text wraps past pane width) multiple lines.
#   => grep -v '^[[:space:]]*$' | paste -sd ' ' (drop blank lines, join the rest with single spaces)
#      before fuzzy-matching. Optionally set the pane wide (tmux resize-window -x 1000) to avoid wrapping.

# CRITICAL #13 (G-DEPS) — required tools; fail clearly if absent.
#   pactl, pw-cat, /usr/bin/tmux, jq, .venv/bin/python, .venv/bin/voicectl, tests/out/*.wav. Preflight
#   'command -v' each + test the WAV files exist; print what is missing and exit non-zero.

# CRITICAL #14 (G-DAEMON-LOG) — redirect daemon stdout/stderr to a log for triage.
#   launch_daemon.sh > "$TMP/daemon.log" 2>&1 & ; DAEMON_PID=$!. On a criterion failure, print the tail
#   of the log (it has the 'voice-typing device resolved:' line + per-utterance 'voice-typing latency:'
#   lines) so the failure is diagnosable without a separate journalctl.
```

## Implementation Blueprint

### Data models and structure

No ORM/pydantic. The script's "schema" is (1) the **canonical fuzzy targets** (pinned verbatim from
`tests/make_test_audio.sh`), (2) the **temp work directory** layout, and (3) the **fuzzy token‑overlap
helper** (a python one‑liner).

```bash
# (1) Canonical fuzzy targets — PINNED VERBATIM from tests/make_test_audio.sh (PRD §6). Do NOT paraphrase.
PAUSE_A="I want to test whether this system"     # first half of utt_pause.wav
PAUSE_B="keeps listening after a pause."         # second half (AFTER the 3.0 s gap) — THE regression
MULTI_1="The weather looks good today."          # utt_multi.wav sentence 1
MULTI_2="I need to buy some groceries."          # utt_multi.wav sentence 2
MULTI_3="Let us meet at the cafe."               # utt_multi.wav sentence 3
# (a 5-element array of the refs the typed text must fuzzy-match)
REFS=("$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3")

# (2) Temp work dir (mktemp -d; trap-rm'd). Layout:
#   $WORK/config/voice-typing/config.toml  # XDG_CONFIG_HOME override (tmux backend + isolated state_file)
#   $WORK/state.json                      # the daemon's isolated state file (criterion-3 partials)
#   $WORK/vt_out.txt                      # the tmux pane's 'cat > file' target (end-of-run cross-check)
#   $WORK/daemon.log                      # daemon stdout/stderr (device-resolved + latency lines)
#   $WORK/partials.log                    # snapshots of state.json 'partial' during playback

# (3) Fuzzy token overlap (PRD §6: >=80%, case/punct-insensitive). python one-liner over stdlib.
#   Reads the captured text from stdin, the 5 refs as argv; prints one "PASS"/"FAIL <ref> <overlap>"
#   line per ref; exits 0 iff all >=0.80.
fuzzy_check() {
  local captured="$1"
  printf '%s' "$captured" | .venv/bin/python - "$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3"
}
```

### `tests/e2e_virtual_mic.sh` reference structure (research §1–§8 + G‑* gotchas — implement close to this)

> The implementer writes ONE bash script. Below is the pinned scaffold. Adapt names/details as
> needed but KEEP the trap discipline (G‑SOURCE/G‑CLEANUP‑IDEMPOTENT), the capture‑pane capture
> (G‑CAPTURE), the real XDG_RUNTIME_DIR + temp XDG_CONFIG_HOME (G‑RUNTIME/G‑CONFIG), the preflight
> (G‑PREFLIGHT), the ordering (G‑ORDERING), and the generous timeouts (G‑POLL‑TIMEOUTS).

```bash
#!/usr/bin/env bash
# tests/e2e_virtual_mic.sh — full E2E with virtual mic + tmux (PRD §6 T3; work item P1.M7.T3.S1).
#
# Stands up a real PipeWire null-sink (vt_test) + monitor, points the system default input at it,
# launches the real daemon with the tmux backend, drives it with voicectl, plays utt_pause.wav +
# utt_multi.wav via pw-cat, and asserts PRD criteria 2 (>=3s pause loses zero words), 3 (live
# partials in state.json), 4 (nothing typed while toggled off). A trap restores the default source,
# unloads the sink, kills the tmux session + daemon, and removes temp files on ANY exit.
#
# Real stack: PipeWire + CUDA Whisper + tmux. Heavy (model load). Run explicitly:
#   cd /home/dustin/projects/voice-typing
#   ./tests/make_test_audio.sh          # ensure tests/out/*.wav exist
#   ./tests/e2e_virtual_mic.sh
# Refuses to start if a voice-typing daemon is already running (preflight).
set -euo pipefail

# --- paths + canonical fuzzy targets (PINNED VERBATIM from tests/make_test_audio.sh) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"
VOICECTL="$REPO/.venv/bin/voicectl"
PY="$REPO/.venv/bin/python"
LAUNCH="$REPO/voice_typing/launch_daemon.sh"
WAV_DIR="$REPO/tests/out"
PAUSE_WAV="$WAV_DIR/utt_pause.wav"; MULTI_WAV="$WAV_DIR/utt_multi.wav"; SIMPLE_WAV="$WAV_DIR/utt_simple.wav"
TMUX=/usr/bin/tmux
SINK=vt_test; TMUX_SESS=voicetest; TMUX_TARGET="voicetest:0.0"
PAUSE_A="I want to test whether this system"; PAUSE_B="keeps listening after a pause."
MULTI_1="The weather looks good today."; MULTI_2="I need to buy some groceries."; MULTI_3="Let us meet at the cafe."
REFS=("$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3")

# --- state (populated by setup; used by the trap) ---
WORK=""; ORIG_SRC=""; MODIDX=""; DAEMON_PID=""

# --- cleanup (G-SOURCE/G-CLEANUP-IDEMPOTENT): idempotent + best-effort; fires on ANY exit ---
cleanup() {
  set +e
  echo "--- cleanup ---"
  [ -n "${DAEMON_PID:-}" ] && { "$VOICECTL" quit >/dev/null 2>&1; sleep 2; kill -TERM "$DAEMON_PID" 2>/dev/null; wait "$DAEMON_PID" 2>/dev/null; }
  [ -n "${ORIG_SRC:-}" ]  && pactl set-default-source "$ORIG_SRC" 2>/dev/null && echo "restored default source: $ORIG_SRC"
  [ -n "${MODIDX:-}" ]    && pactl unload-module "$MODIDX" 2>/dev/null && echo "unloaded module $MODIDX"
  "$TMUX" kill-session -t "$TMUX_SESS" 2>/dev/null && echo "killed tmux session $TMUX_SESS"
  [ -n "${WORK:-}" ]      && rm -rf "$WORK"
  # verify no trace (G-SOURCE hard rule)
  if pactl list short sources 2>/dev/null | grep -q "vt_test"; then echo "WARN: vt_test still present"; fi
}
trap cleanup EXIT

# --- helpers ---
die() { echo "FAIL: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- preflight (G-PREFLIGHT/G-DEPS) ---
have pactl   || die "missing pactl (PipeWire pulse compat)"
have pw-cat  || die "missing pw-cat (PipeWire)"
[ -x "$TMUX" ] || die "missing $TMUX"
have jq      || die "missing jq"
[ -x "$VOICECTL" ] || die "missing $VOICECTL (run install/uv sync)"
[ -x "$PY" ]       || die "missing $PY"
for w in "$PAUSE_WAV" "$MULTI_WAV" "$SIMPLE_WAV"; do [ -f "$w" ] || die "missing $w (run ./tests/make_test_audio.sh)"; done
# refuse if a daemon is already running (real control socket is pinned; G-RUNTIME/G-PREFLIGHT)
if "$VOICECTL" status >/dev/null 2>&1; then
  die "a voice-typing daemon is already running (voicectl status answered). Stop it first: systemctl --user stop voice-typing"
fi
systemctl --user is-active voice-typing >/dev/null 2>&1 \
  && die "voice-typing systemd service is active; stop it first: systemctl --user stop voice-typing" || true

# --- setup (G-SOURCE/G-ORDERING/G-CONFIG/G-RUNTIME) ---
ORIG_SRC="$(pactl get-default-source)" || die "pactl get-default-source failed"
echo "original default source: $ORIG_SRC"
MODIDX="$(pactl load-module module-null-sink sink_name="$SINK" media.class=Audio/Sink)" \
  || die "load-module module-null-sink failed"
echo "loaded null-sink module index: $MODIDX"
pactl set-default-source "$SINK.monitor" || die "set-default-source $SINK.monitor failed"
echo "default source -> $SINK.monitor"

WORK="$(mktemp -d)"
mkdir -p "$WORK/config/voice-typing"
cat > "$WORK/config/voice-typing/config.toml" <<EOF
[output]
backend     = "tmux"
tmux_target = "$TMUX_TARGET"

[feedback]
state_file  = "$WORK/state.json"
hypr_notify = false
EOF
CAPFILE="$WORK/vt_out.txt"; rm -f "$CAPFILE"
# pane runs 'cat > file' (contract); capture-pane reads the tty echo mid-stream (G-CAPTURE)
"$TMUX" new-session -d -s "$TMUX_SESS" "cat > '$CAPFILE'" || die "tmux new-session failed"
"$TMUX" resize-window -t "$TMUX_SESS" -x 1000 2>/dev/null || true   # avoid line-wrap in capture (G-CAPTURE-PANE-FILTER)

# --- launch daemon (G-RUNTIME: real XDG_RUNTIME_DIR; G-CONFIG: temp XDG_CONFIG_HOME) ---
# NOTE: do NOT override XDG_RUNTIME_DIR here (PyAudio needs the real one; G-RUNTIME).
XDG_CONFIG_HOME="$WORK/config" "$LAUNCH" > "$WORK/daemon.log" 2>&1 &
DAEMON_PID=$!
echo "daemon launched (pid=$DAEMON_PID); waiting for ready (models load, up to 180s)..."

# --- wait for ready (G-POLL-TIMEOUTS) ---
ready=0
for _ in $(seq 1 360); do            # 360 x 0.5s = 180s
  if "$VOICECTL" status >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited during startup; see $WORK/daemon.log"
  sleep 0.5
done
[ "$ready" = 1 ] || die "daemon not ready in 180s; see $WORK/daemon.log"
echo "daemon ready:"; "$VOICECTL" status || true

# --- RUN: arm, play, poll partials + typed text (criteria 2,3 + all-segments) ---
"$VOICECTL" start >/dev/null || die "voicectl start failed"
echo "listening armed; playing utt_pause.wav then utt_multi.wav..."

# poll state.json partials DURING playback (criterion 3; G-POLL-TIMEOUTS)
( for _ in $(seq 1 150); do                       # 150 x 0.2s = 30s poll window
    p="$(jq -r .partial "$WORK/state.json" 2>/dev/null || true)"
    [ -n "$p" ] && [ "$p" != "null" ] && echo "$p" >> "$WORK/partials.log"
    sleep 0.2
  done ) &
PARTIALS_POLL=$!

# play utt_pause.wav (2 finals: PAUSE_A + PAUSE_B) then utt_multi.wav (3 finals)
pw-cat -p --target "$SINK" "$PAUSE_WAV" || die "pw-cat playback pause failed"
sleep 1
pw-cat -p --target "$SINK" "$MULTI_WAV" || die "pw-cat playback multi failed"
wait "$PARTIALS_POLL" 2>/dev/null || true

# poll capture-pane until all 5 refs fuzzy-match (G-CAPTURE/G-POLL-TIMEOUTS)
capture_pane() { "$TMUX" capture-pane -t "$TMUX_SESS" -p -S - | grep -v '^[[:space:]]*$' | paste -sd ' '; }
typed=""
for _ in $(seq 1 180); do                          # 180 x 0.5s = 90s
  typed="$(capture_pane)"
  if printf '%s' "$typed" | "$PY" - "$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3" <<'PY' >/dev/null 2>&1
import re, string, sys
capt=sys.stdin.read(); refs=sys.argv[1:]
def toks(s): return re.sub(rf"[{re.escape(string.punctuation)}]"," ",s.lower()).split()
def overlap(h,r):
    from collections import Counter
    hc,rc=Counter(toks(h)),Counter(toks(r))
    return (sum((hc&rc).values())/len(rc)) if rc else 0.0
sys.exit(0 if all(overlap(capt,r)>=0.80 for r in refs) else 1)
PY
  then break; fi
  sleep 0.5
done

# --- ASSERT criteria 2 + all-segments ---
echo "--- assertions ---"
printf '%s' "$typed" | "$PY" - "$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3" <<'PY'
import re, string, sys
capt=sys.stdin.read(); refs=sys.argv[1:]
def toks(s): return re.sub(rf"[{re.escape(string.punctuation)}]"," ",s.lower()).split()
def overlap(h,r):
    from collections import Counter
    hc,rc=Counter(toks(h)),Counter(toks(r))
    return round((sum((hc&rc).values())/len(rc)) if rc else 0.0, 3)
ok=True
for r in refs:
    o=overlap(capt,r); status="PASS" if o>=0.80 else "FAIL"
    if o<0.80: ok=False
    print(f"  [{status}] fuzzy {o:.2f} vs {r!r}")
print(f"  captured text: {capt!r}")
sys.exit(0 if ok else 1)
PY
CRIT2_OK=$?

# --- criterion 3: live partials observed ---
PARTIALS_OBSERVED=0
[ -s "$WORK/partials.log" ] && PARTIALS_OBSERVED=1
[ "$PARTIALS_OBSERVED" = 1 ] && echo "  [PASS] criterion 3: live partials observed in state.json" \
                              || { echo "  [FAIL] criterion 3: no non-empty partial snapshot"; CRIT2_OK=1; }

# --- criterion 4: toggle-off gates output (G-CAPTURE diff) ---
before="$typed"
"$VOICECTL" stop >/dev/null || die "voicectl stop failed"
echo "listening disarmed; playing utt_simple.wav (must type NOTHING)..."
pw-cat -p --target "$SINK" "$SIMPLE_WAV" || die "pw-cat playback simple (toggle-off) failed"
sleep 4                                     # let any in-flight final (if gate failed) appear
after="$(capture_pane)"
if [ "$before" = "$after" ]; then
  echo "  [PASS] criterion 4: nothing typed after voicectl stop (toggle-off gates)"
else
  echo "  [FAIL] criterion 4: text changed after stop (gate leaked): before=${before!r} after=${after!r}"; CRIT2_OK=1
fi

# --- belt-and-suspenders: flush cat>file + cross-check (G-CAPTURE) ---
"$TMUX" send-keys -t "$TMUX_SESS" C-d 2>/dev/null || true
sleep 0.5
echo "  cat>file cross-check: $(cat "$CAPFILE" 2>/dev/null | tr '\n' ' ')"

# --- result ---
if [ "$CRIT2_OK" = 0 ]; then
  echo "=== E2E PASS (criteria 2,3,4) ==="
  exit 0
else
  echo "=== E2E FAIL (see above; daemon log: $WORK/daemon.log) ==="
  tail -n 20 "$WORK/daemon.log" 2>/dev/null || true
  exit 1
fi
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm prereqs WITHOUT mutation.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f tests/out/utt_pause.wav && echo "WAVs present" || echo "run ./tests/make_test_audio.sh first"
      command -v pactl pw-cat jq && test -x /usr/bin/tmux && echo "system tools OK" || echo "MISSING tools"
      test -x .venv/bin/voicectl && .venv/bin/python -c "import RealtimeSTT" && echo "venv OK" || echo "venv/deps missing"
      test ! -e tests/e2e_virtual_mic.sh && echo "ok: not yet created" || echo "PREFLIGHT FAIL: already exists"
      .venv/bin/voicectl status >/dev/null 2>&1 && echo "WARN: a daemon is running (preflight will refuse)" || echo "no daemon running (ok)"
  - EXPECTED: WAVs present; pactl/pw-cat/jq/tmux present; venv OK; script absent; no daemon running.
  - DO NOT: create/edit any file, run the E2E, touch .gitignore, or any module.

Task 1: CREATE tests/e2e_virtual_mic.sh — the reference scaffold above (adapt as needed).
  - FILE: tests/e2e_virtual_mic.sh (NEW). chmod +x.
  - KEEP (the load-bearing invariants — each maps to a CRITICAL gotcha):
      * G-CAPTURE: read typed text via 'tmux capture-pane -p -S -' (NOT cat the file mid-stream);
        keep 'cat > $CAPFILE' as an end-of-run cross-check after a C-d flush.
      * G-RUNTIME: keep the REAL XDG_RUNTIME_DIR for the daemon + pactl/pw-cat (do NOT move it to temp).
      * G-SOURCE: record ORIG_SRC before load-module; restore it + unload-module by INDEX in the trap.
      * G-TARGET: pw-cat --target = sink name (vt_test); capture-pane -t = session (voicetest).
      * G-PREFLIGHT: refuse if voicectl status answers / systemctl is-active.
      * G-CONFIG: XDG_CONFIG_HOME=<tmp>/config with a minimal config.toml ([output]+[feedback] only).
      * G-TMUX-PATH: always /usr/bin/tmux.
      * G-ORDERING: create sink + set-default-source BEFORE launching the daemon.
      * G-FUZZY: >=80% token overlap via the python one-liner (case/punct-insensitive).
      * G-POLL-TIMEOUTS: 180s daemon-ready; 90s typed-text; 0.2s partial-poll.
      * G-CLEANUP-IDEMPOTENT: every trap step wrapped in '|| true'/2>/dev/null; trap on EXIT.
      * The 5 canonical fuzzy targets VERBATIM (match tests/make_test_audio.sh).
  - DO NOT: edit any voice_typing/ module, pyproject.toml, config.toml, make_test_audio.sh, .gitignore;
    edit test_feed_audio.py (P1.M7.T2.S1); create a README; set a temp XDG_RUNTIME_DIR.

Task 2: VALIDATE — run the Validation Loop L1-L4. Iterate until all gates pass.
  - EXPECTED on this box (CUDA, WAVs present, no daemon running): PASS; the trap restores the source.
  - If a criterion fails: READ the assertion output (it prints the captured text + per-ref overlaps) +
    the daemon.log tail (device-resolved line + latency lines). Common causes:
      - captured text empty       -> capture-pane target wrong (use the session name) OR the daemon did
                                     not type (check daemon.log: did voicectl start arm it? models on cuda?).
      - partials.log empty        -> state_file override wrong (daemon wrote to the real XDG path, not
                                     $WORK/state.json) OR playback did not route (did set-default-source
                                     precede daemon launch? G-ORDERING).
      - criterion 4 text changed  -> the on_final gate raced (should not — but check voicectl stop returned
                                     before the WAV played).
  - No git commit unless the orchestrator directs it. If asked, message:
    "P1.M7.T3.S1: tests/e2e_virtual_mic.sh — full E2E virtual-mic + tmux (PRD T3): criteria 2,3,4".
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — null-sink lifecycle + trap restore (G-SOURCE/G-CLEANUP-IDEMPOTENT). load-module returns
#   the MODULE INDEX on stdout; unload by INDEX (name unloads ALL null-sinks -> destructive).
ORIG_SRC="$(pactl get-default-source)"                                    # FIRST setup step
MODIDX="$(pactl load-module module-null-sink sink_name=vt_test media.class=Audio/Sink)"
pactl set-default-source vt_test.monitor
# ... run ...
# trap (idempotent): pactl set-default-source "$ORIG_SRC"; pactl unload-module "$MODIDX"

# PATTERN 2 — read typed text via capture-pane (G-CAPTURE). The daemon types literal keys with NO
#   newline -> 'cat > file' is empty mid-stream (pty canonical mode). capture-pane reads the tty ECHO.
capture_pane() { /usr/bin/tmux capture-pane -t voicetest -p -S - | grep -v '^[[:space:]]*$' | paste -sd ' '; }

# PATTERN 3 — daemon launch (G-RUNTIME/G-CONFIG). Real XDG_RUNTIME_DIR (PyAudio needs it); temp
#   XDG_CONFIG_HOME (the tmux-backend + isolated-state override). launch_daemon.sh execs python -> $! is
#   the python PID.
XDG_CONFIG_HOME="$WORK/config" voice_typing/launch_daemon.sh > "$WORK/daemon.log" 2>&1 &
DAEMON_PID=$!

# PATTERN 4 — fuzzy token overlap (G-FUZZY; PRD §6 >=80%, case/punct-insensitive). python one-liner.
printf '%s' "$TYPED" | .venv/bin/python - "$REF1" "$REF2" ... <<'PY'
import re,string,sys
capt=sys.stdin.read()
def toks(s): return re.sub(rf"[{re.escape(string.punctuation)}]"," ",s.lower()).split()
def ov(h,r):
    from collections import Counter; hc,rc=Counter(toks(h)),Counter(toks(r))
    return (sum((hc&rc).values())/len(rc)) if rc else 0.0
sys.exit(0 if all(ov(capt,r)>=0.80 for r in sys.argv[1:]) else 1)
PY

# PATTERN 5 — criterion-4 diff (G-CAPTURE). Snapshot capture-pane, voicectl stop, play one more WAV,
#   re-capture, assert UNCHANGED. The on_final gate + the disarmed mic (set_microphone False -> the audio
#   worker stops reading) double-protect: nothing types after stop.
before="$(capture_pane)"; voicectl stop; pw-cat -p --target vt_test utt_simple.wav; sleep 4
[ "$before" = "$(capture_pane)" ] || die "toggle-off leaked text"
```

### Integration Points

```yaml
CONSUMES — tests/out/{utt_pause,utt_multi,utt_simple}.wav (P1.M7.T1.S1, DONE):
  - format:  16000 Hz / 1 ch / 16-bit signed-integer PCM; played by pw-cat -p --target vt_test
  - texts:   fuzzy-match (>=80%) the PINNED canonical strings (single source: tests/make_test_audio.sh)

CONSUMES — voice_typing production seams (READ-ONLY reuse; do NOT modify):
  - voice_typing/launch_daemon.sh        -> LD_LIBRARY_PATH wrapper; exec python -m voice_typing.daemon
  - voice_typing/ctl.py (voicectl)       -> start/stop/status/quit; exit 0/1/2
  - voice_typing/typing_backends.TmuxBackend -> /usr/bin/tmux send-keys -t <target> -l -- text (NO newline)
  - voice_typing/daemon._default_control_socket_path -> $XDG_RUNTIME_DIR/voice-typing/control.sock (REAL path)
  - voice_typing/feedback.Feedback       -> writes state.json {listening,phase,partial,last_final,ts} (>=10 Hz)

CONSUMES — system tooling (verified present): pactl, pw-cat, /usr/bin/tmux, jq, .venv/bin/{python,voicectl}.
  - PipeWire 1.6.6 (pipewire-pulse compat); null-sink monitor = <sink>.monitor; PyAudio uses PulseAudio
    backend under the real XDG_RUNTIME_DIR and follows set-default-source.

ISOLATION:
  - null-sink + monitor:      created + unloaded per-run (G-SOURCE); global default-source swapped + restored.
  - state.json:               overridden to $WORK/state.json via config (G-CONFIG) -> no clobber of a real daemon.
  - control socket:           REAL path (cannot be moved without editing daemon.py) -> PREFLIGHT refusal (G-PREFLIGHT).
  - tmux session 'voicetest': created + killed per-run; uses a real node in the user's tmux server (G-TMUX-PATH).

NO database. NO pyproject/uv.lock change. NO module edit. NO root .gitignore edit. NO config.toml edit.
```

## Validation Loop

> Run from `/home/dustin/projects/voice-typing`. The fast pytest unit suite is UNAFFECTED (this is a
> standalone bash script, not collected by pytest). Requires: no voice-typing daemon running,
> `tests/out/*.wav` present, models prefetched, a CUDA GPU (or it runs degraded/slowly).

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
bash -n tests/e2e_virtual_mic.sh && echo "L1 syntax OK" || echo "L1 FAIL: syntax error"
shellcheck tests/e2e_virtual_mic.sh 2>/dev/null && echo "L1 shellcheck OK" || echo "L1 note: shellcheck not installed or warnings (review)"
test -x tests/e2e_virtual_mic.sh || { chmod +x tests/e2e_virtual_mic.sh && echo "L1 chmod +x"; }
# Expected: bash -n clean (zero errors). shellcheck clean if installed (warnings acceptable if the
# flagged construct is intentional, e.g. the 'for _ in $(seq ...)' poll loops — document why).
```

### Level 2: Dry-Run Sanity (no daemon, no audio — fast pre-checks)

```bash
cd /home/dustin/projects/voice-typing
# preflight refusal path (no daemon running -> should pass preflight; with a daemon -> should refuse):
.venv/bin/voicectl status >/dev/null 2>&1 && echo "a daemon IS running (script would refuse)" \
                                          || echo "no daemon (preflight would proceed)"
# the canonical strings match the generator (single source; G-FUZZY):
for s in 'I want to test whether this system' 'keeps listening after a pause.' \
         'The weather looks good today.' 'I need to buy some groceries.' 'Let us meet at the cafe.'; do
  grep -qF "$s" tests/e2e_virtual_mic.sh && grep -qF "$s" tests/make_test_audio.sh \
    && echo "L2 pinned OK: $s" || echo "L2 DRIFT: '$s' differs between script and generator"
done
# Expected: either 'no daemon' (preflight proceeds) or a clear refusal if a daemon runs; all 5 strings pinned.
```

### Level 3: The Full E2E (the real validation — criteria 2,3,4)

```bash
cd /home/dustin/projects/voice-typing
# ensure no real daemon is running first (the script will refuse otherwise):
systemctl --user stop voice-typing 2>/dev/null || true
./tests/make_test_audio.sh                       # ensure tests/out/*.wav exist (idempotent)
./tests/e2e_virtual_mic.sh
# Expected: prints setup steps, the daemon status (device: cuda (float16) + models), per-criterion
# PASS lines, and "=== E2E PASS (criteria 2,3,4) ==="; exit 0. The trap restores the default source.
# If a criterion fails: the script prints the captured text + per-ref overlaps + daemon.log tail; exit 1.
```

### Level 4: Cleanup Verification (the G-SOURCE hard rule — MUST NOT leave the user's source switched)

```bash
cd /home/dustin/projects/voice-typing
# capture the default source BEFORE running, then verify it is UNCHANGED after (pass OR fail):
BEFORE="$(pactl get-default-source)"
./tests/e2e_virtual_mic.sh; RC=$?
AFTER="$(pactl get-default-source)"
[ "$BEFORE" = "$AFTER" ] && echo "L4 default source restored OK ($AFTER)" || echo "L4 FAIL: source changed ($BEFORE -> $AFTER)"
pactl list short sources | grep -q vt_test && echo "L4 FAIL: vt_test leaked" || echo "L4 vt_test unloaded OK"
/usr/bin/tmux has-session -t voicetest 2>/dev/null && echo "L4 FAIL: voicetest session leaked" || echo "L4 voicetest session killed OK"
pgrep -af "voice_typing.daemon" >/dev/null && echo "L4 FAIL: daemon still running" || echo "L4 daemon gone OK"
# Also verify after a Ctrl-C: run the script, Ctrl-C it mid-run, then re-run the 4 checks above.
# Expected on every exit path: source restored, vt_test gone, voicetest gone, daemon gone.
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: `bash -n` clean; `shellcheck` clean (if installed); `+x` set.
- [ ] L3: `./tests/e2e_virtual_mic.sh` passes (CUDA + WAVs + no daemon running).
- [ ] L4: default source restored, `vt_test` unloaded, `voicetest` killed, daemon gone — on PASS, error,
      AND Ctrl‑C (run the Ctrl‑C case explicitly).
- [ ] L2: the 5 canonical strings are pinned verbatim (script == `make_test_audio.sh`).

### Feature Validation

- [ ] Criterion 2: typed text fuzzy‑matches BOTH `PAUSE_A` and `PAUSE_B` (≥0.80 each).
- [ ] Typed text fuzzy‑matches all 5 canonical refs.
- [ ] Criterion 3: ≥1 `state.json` snapshot during playback had non‑empty `partial`.
- [ ] Criterion 4: after `voicectl stop` + one more WAV, captured text is unchanged.
- [ ] Preflight refuses to start if a daemon is already running.

### Code Quality Validation

- [ ] File placement: `tests/e2e_virtual_mic.sh` per PRD §4.1 layout; `+x`.
- [ ] Follows house shell style (`set -euo pipefail`, `command -v` checks, `mktemp -d` + `trap rm`) —
      compare `install.sh` (P1.M6.T1.S1) and `tests/make_test_audio.sh` (P1.M7.T1.S1).
- [ ] The load‑bearing invariants upheld: G‑CAPTURE, G‑RUNTIME, G‑SOURCE, G‑TARGET, G‑PREFLIGHT,
      G‑CONFIG, G‑TMUX‑PATH, G‑ORDERING, G‑FUZZY, G‑POLL‑TIMEOUTS, G‑CLEANUP‑IDEMPOTENT.
- [ ] No edit to `voice_typing/*`, `pyproject.toml`, `config.toml`, `tests/make_test_audio.sh`,
      `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`; no README; no `test_feed_audio.py` edit.

### Documentation & Deployment

- [ ] Script header documents: PRD §6 T3, the three criteria, the capture‑pane rationale (G‑CAPTURE),
      the run command, the preflight refusal, and the cleanup guarantee.
- [ ] No new env vars required beyond the per‑process `XDG_CONFIG_HOME` (the real `XDG_RUNTIME_DIR` is
      inherited, not changed). No config change.

---

## Anti-Patterns to Avoid

- ❌ Don't read typed text from `cat > file` mid‑stream — the daemon types literal keys with **no
  newline**, so the pty canonical‑mode buffers `cat`'s input and the file stays empty (G‑CAPTURE). Use
  `tmux capture-pane -p -S -` (reads the tty echo). `cat > file` is only an end‑of‑run cross‑check
  after a `C-d` flush.
- ❌ Don't move `XDG_RUNTIME_DIR` to a temp dir to isolate the control socket / state.json — it breaks
  PyAudio's PulseAudio backend (falls back to ALSA → `vt_test.monitor` invisible → the daemon records
  silence) (G‑RUNTIME). Isolate state.json via the **config override** instead; accept the real control
  socket path and preflight for a running daemon.
- ❌ Don't unload the null‑sink by the module **name** (`module-null-sink`) — `pactl` unloads **all**
  instances, destroying the user's own loopbacks. Unload by the captured **index** (G‑SOURCE).
- ❌ Don't skip the preflight — if a real daemon holds the real control socket, the test's daemon can't
  bind (RuntimeError) and the real daemon gets hijacked by `set-default-source` (G‑PREFLIGHT).
- ❌ Don't create the null‑sink / `set-default-source` AFTER launching the daemon — RealtimeSTT opens the
  PyAudio stream ONCE at construction on the default input AT THAT MOMENT (G‑ORDERING).
- ❌ Don't pass `--target vt_test.monitor` to `pw-cat -p` (playback targets the **sink**, not the
  monitor) or `capture-pane -t voicetest:0.0` when the session has one pane (target the **session**)
  (G‑TARGET).
- ❌ Don't skimp on poll timeouts — cuDNN/cuBLAS cold init + 2 Whisper model loads can take well over a
  minute; a too‑short ready‑poll makes a healthy daemon look dead (G‑POLL‑TIMEOUTS).
- ❌ Don't make the trap fragile — every cleanup step must be idempotent + best‑effort (`|| true` /
  `2>/dev/null`) and fire on `EXIT` so it runs on PASS, error, and Ctrl‑C (G‑CLEANUP‑IDEMPOTENT). The
  PRD's hard rule: **the user's default source must never be left switched.**
- ❌ Don't exact‑match the typed text — espeak is robotic; fuzzy ≥80 % token overlap is the contract
  (G‑FUZZY). Don't chase 100 %.
- ❌ Don't use `tmux` (zsh aliases it) — always `/usr/bin/tmux` (G‑TMUX‑PATH; the daemon uses the same).
- ❌ Don't edit `config.toml` to set `backend="tmux"` — override via `XDG_CONFIG_HOME` (G‑CONFIG); editing
  the repo file is off‑limits and would be clobbered by reinstalls.

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a single bash script whose **entire
PipeWire/pactl/pw‑cat/tmux interaction model is derived in the cited research note from a verified
command transcript on this exact machine**: the null‑sink lifecycle (load‑module returns the module
index; monitor = `<sink>.monitor`; unload by index); the full audio round‑trip (RMS 0.084 non‑silent);
the core routing fact (RealtimeSTT uses PyAudio's default input when `input_device_index` is None
[audio_input.py:136], and PyAudio's default follows `set-default-source`); and the two non‑obvious
traps — **capture‑pane, not `cat > file` reads, works mid‑stream** (pty canonical‑mode buffering), and
**the real `XDG_RUNTIME_DIR` is mandatory** (temp breaks PyAudio). The **daemon seams** the script
drives (`launch_daemon.sh`, `voicectl`, the tmux `send-keys -l` backend, the pinned control‑socket
path, the `state.json` shape) are read from `voice_typing/*.py` with line‑level detail. The **canonical
fuzzy targets** are pinned verbatim (cross‑checked against `make_test_audio.sh` in L2). All system tools
(pactl/pw‑cat/tmux/jq) are confirmed present. The −1 residual risk is **measured Whisper latency /
accuracy on the real audio path** (espeak drift below the 80 % floor on a specific clip) — recoverable
via `make_test_audio.sh FORCE=1` (a fixture problem, not a test bug), and the fuzzy floor is the PRD's
own non‑determinism allowance. A second residual is the **preflight/control‑socket reality**: the test
cannot fully isolate the daemon (it binds the real socket + swaps the global default source), so it
depends on no other daemon running — the preflight + trap make this safe and explicit.
