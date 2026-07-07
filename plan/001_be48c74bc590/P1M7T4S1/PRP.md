# PRP — P1.M7.T4.S1: idle-stability (T4) + GPU-residency (T6) + acceptance checklist

> **Scope reminder.** This work item ships **2 files, both under `tests/`**, and modifies nothing
> else: (1) `tests/test_idle_and_gpu.sh` — a real-stack bash test that proves PRD §6 **T4**
> (idle-120 s: no hallucinated finals, no crash, CPU < 25 % of one core) and **T6** (GPU VRAM
> residency 1–5 GiB via `nvidia-smi`), running the daemon **fully offline** (`HF_HUB_OFFLINE=1`) so
> it simultaneously proves PRD §7 **criterion 8** (no network at runtime); and (2)
> `tests/ACCEPTANCE.md` — the human-readable acceptance-evidence doc that walks PRD §7 criteria 1–8
> with real command output. Criteria **5, 6 (crit), 8 (crit)** are SATISFIED by this item; criteria
> 1–4, 7 are referenced (their evidence lives in the sibling tests / git / the future README task).

## Goal

**Feature Goal**: Create **`tests/test_idle_and_gpu.sh`** — the PRD §6 **T4 + T6** test — and
**`tests/ACCEPTANCE.md`** — the PRD §7 acceptance-evidence document. The script stands up the **real
daemon** (via `launch_daemon.sh`, with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` so the run proves
no network is needed), arms it with **`voicectl start`**, holds **120 s of silence** (no playback, no
PipeWire mutation — it listens to ambient silence on the real default mic), and asserts the three T4
properties: **(a) no finals typed** (the P1.M2.T2.S1 blocklist + VAD gating suppress Whisper's
silence-hallucination — detected via the **tmux backend + `capture-pane`** UNCHANGED and
**`state.json last_final`** UNCHANGED from its initial `""`); **(b) no crash** (`kill -0 $DAEMON_PID`
after 120 s); **(c) CPU < 25 % of one core on average** (`/proc/<pid>/stat` utime+stime summed over
the daemon's process tree, divided by elapsed wall-seconds — `pidstat`/sysstat is NOT installed). It
then runs **T6**: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader`, matches
the daemon's **process-tree PIDs** against the compute-app rows, and asserts ≥1 match with Σ
used_memory ∈ **[1024, 5120] MiB**. It exercises **`voicectl toggle/start/stop/status/quit`** and
greps the **systemd unit** (`ExecStart → launch_daemon.sh`, `Restart=on-failure`) for criterion 6,
and asserts the daemon **boots un-armed** (`voicectl status` → `listening: off` right after ready).
It prints a fenced **`=== ACCEPTANCE EVIDENCE ===`** block (real CPU %, real nvidia-smi rows +
total VRAM, voicectl status, unit grep, per-criterion PASS/FAIL) the implementer pastes into
`tests/ACCEPTANCE.md`.

**Deliverable** (2 files — 2 ADD; **NO** edit to anything else):
1. `tests/test_idle_and_gpu.sh` — NEW. `set -euo pipefail` bash (bash ≥4, POSIX-portable where
   possible). Heavy real-stack test (CUDA Whisper + tmux); run explicitly, never in the fast pytest
   suite. Uses `.venv/bin/python` for two stdlib helpers (/proc CPU parse + nvidia-smi match) and
   `.venv/bin/voicectl` for control. `chmod +x`. A `trap … EXIT` does idempotent cleanup (quit +
   kill the daemon, kill the tmux session, rm temp). **Does NOT touch the default audio source**
   (no null-sink) ⇒ the trap is simpler than T3's, but the real control socket is still used ⇒
   PREFLIGHT refuses to start if a daemon is already running.
2. `tests/ACCEPTANCE.md` — NEW. Committed Markdown walking PRD §7 criteria **1–8**: criteria 5, 6, 8
   are filled with the **real output** captured by running `test_idle_and_gpu.sh` (paste the
   evidence block); criteria 1–4 cite the sibling test commands (`test_feed_audio.py`, T2 =
   `test_textproc.py`, `e2e_virtual_mic.sh`) and their PASS; criterion 7 cites `git status` (all
   committed) and notes the README is P2.M1.T2.S1 (pending). Mode-A documentation, referenced by
   the final README (P2).

**Success Definition**:
- (a) `tests/test_idle_and_gpu.sh` exists, is `+x`, `bash -n` + `shellcheck` (if present) clean.
- (b) `./tests/test_idle_and_gpu.sh` **passes** on this CUDA box (models prefetched, no daemon
  running, quiet room) — prints per-criterion PASS lines + the `=== ACCEPTANCE EVIDENCE ===` block,
  exits 0.
- (c) **Criterion 5 (T4, CRITICAL)**: after 120 s armed silence, `capture-pane` text is UNCHANGED,
  `state.json last_final` is UNCHANGED from its initial value (no hallucinated finals), the daemon
  PID is alive, and **avg CPU < 25 % of one core** (the evidence block prints the actual %).
- (d) **Criterion 8 (T6 + CRITICAL no-network)**: `nvidia-smi` shows ≥1 daemon-tree compute-app row
  with Σ used_memory ∈ [1024, 5120] MiB (the evidence block prints the matched rows + total); AND the
  daemon ran the entire test under `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` (proving no runtime
  network — models were cache-resident).
- (e) **Criterion 6 (CRITICAL)**: `voicectl toggle/start/stop/status/quit` each return `ok:true`
  (exit 0); the unit file shows `ExecStart → launch_daemon.sh` + `Restart=on-failure`; the post-ready
  `voicectl status` shows `listening: off` (starts un-armed).
- (f) **`tests/ACCEPTANCE.md`** exists and records the real captured output for 5/6/8 + the
  verification path for 1–4/7.
- (g) **Cleanup is bulletproof**: on PASS, error, or Ctrl-C, the daemon process is gone, the
  `vtidle` tmux session is gone, and temp dirs are removed. (No audio-source restore is needed —
  this test never swaps it.)
- (h) No out-of-scope edits: NO change to `voice_typing/*`, `pyproject.toml`, `config.toml`,
  `tests/make_test_audio.sh`, `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`,
  `systemd/*`, `install.sh`; NO README (P2); NO `e2e_virtual_mic.sh` / `test_feed_audio.py` edit.

## User Persona

**Target User**: **dustin / the test-running developer** who runs `./tests/test_idle_and_gpu.sh` to
prove the daemon is stable on silence (no hot-mic hallucination), GPU-resident, offline-capable, and
systemd-correct, then pastes the printed evidence into `tests/ACCEPTANCE.md` to satisfy PRD §7
acceptance. Secondary: **a fresh clone** regenerating evidence after a re-install.

**Use Case**:
```
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true   # preflight will refuse if it's running
./tests/test_idle_and_gpu.sh                              # ~3-4 min (model load + 120s idle)
# → prints setup, per-criterion PASS, and an '=== ACCEPTANCE EVIDENCE ===' block
# then paste that block into tests/ACCEPTANCE.md (criteria 5/6/8)
```

**Pain Points Addressed**: (1) PRD §6 T4/T6 are mandated and unimplemented; criterion 5/6/8 of PRD §7
cannot be signed off without this. (2) Whisper is notorious for **silence-hallucination** ("thank
you.", "thanks for watching.", "you", "bye.") — T4 is the regression guard that proves the
P1.M2.T2.S1 blocklist + VAD gating actually suppress it on a live mic. (3) The resident-daemon
design (construct-once; models never leave VRAM) is only credible if **T6 shows the VRAM resident
while idle** — otherwise the whole low-latency-toggle architecture is unproven. (4) "No network at
runtime" (criterion 8) is a *claim* until a daemon is observed loading cached models with
`HF_HUB_OFFLINE=1` — this test makes it a *fact*. (5) `pidstat` is not installed (sysstat) — this
test uses `/proc` so it runs with zero extra packages.

## Why

- **T4 + T6 are the two PRD §6 tests not covered by the unit/feed/E2E tests.** Unit tests mock the
  recorder; `test_feed_audio.py` (T1) feeds WAVs in-process (no mic, no idle); `e2e_virtual_mic.sh`
  (T3) drives real audio through the typing backend but is about *active* transcription, not idle
  stability. Only this test proves the daemon **survives silence** (criterion 5) and is
  **GPU-resident** (criterion 6's residency half + T6).
- **It closes the acceptance milestone.** PRD §7 criterion 1 requires "T1–T4, T6 pass, demonstrated
  by actual command output." `tests/ACCEPTANCE.md` is that record; it is referenced by the final
  README (P2.M1.T2.S1).
- **It proves two non-obvious safety properties the architecture depends on:** (a) the daemon does
  not hot-type hallucinated text while the user *thinks* the mic is idle (a misbehaving guard would
  be a serious UX/safety bug); and (b) the models stay resident (so `voicectl toggle` arms
  instantly — the entire latency budget assumes this).
- **Scope discipline.** This is a TEST + an evidence DOC. It consumes the production seams
  (`launch_daemon.sh`, `voicectl`, `feedback.state.json`, the tmux backend, the systemd unit, the HF
  cache) and stdlib system tools (`/proc`, `nvidia-smi`, `tmux`, `python`, `jq`). It does NOT touch
  any module, config, the audio generator, or the README.

## What

Two committed artifacts. The **script** is a heavy real-stack test (real CUDA Whisper + real tmux,
~3–4 min wall: model load + the fixed 120 s idle window); the **doc** is its human-readable evidence
record.

Script phases (see Implementation Blueprint for the pinned scaffold):
1. **Preflight** — refuse if `voicectl status` answers OR `systemctl --user is-active voice-typing` =
   active (the control socket is pinned to the real `$XDG_RUNTIME_DIR`; a second daemon cannot bind);
   check tools (`nvidia-smi`, `/usr/bin/tmux`, `jq`, `.venv/bin/{python,voicectl}`,
   `launch_daemon.sh`).
2. **Setup** — `mktemp -d`; write the temp `XDG_CONFIG_HOME` config (tmux backend → a `vtidle` tmux
   pane running `cat > "$CAPFILE"`; isolated `state_file`; `hypr_notify=false`); `new-session -d`
   the pane; install the `trap`.
3. **Launch (OFFLINE)** — start `launch_daemon.sh` with `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` +
   `XDG_CONFIG_HOME="$WORK/config"` + the **real** `XDG_RUNTIME_DIR` (PyAudio + the control socket
   need it), stdout→`$WORK/daemon.log`. Poll `voicectl status` to ready (≤ 180 s).
4. **Evidence: un-armed boot + voicectl (criterion 6)** — capture the ready `voicectl status`
   (assert `listening: off`); run `voicectl toggle` (→ on) then `voicectl toggle` (→ off) to exercise
   toggle; record outputs.
5. **T4 idle window (criterion 5, CRITICAL)** — record CPU T0 (`/proc` utime+stime over the daemon
   tree) + wall T0; `voicectl start`; snapshot initial `capture-pane` text + `state.json last_final`;
   **sleep 120**; record CPU T1 + wall T1; re-snapshot both. Assert: capture-pane UNCHANGED,
   `last_final` UNCHANGED (no hallucination), daemon alive, avg CPU < 25 % of one core.
6. **T6 residency (criterion 6/8)** — `voicectl stop`; `nvidia-smi --query-compute-apps=
   pid,used_memory --format=csv,noheader`; match daemon-tree PIDs; assert ≥1 match + Σ ∈
   [1024,5120] MiB. Capture `voicectl status` (device + models) for the residency corroboration.
7. **Systemd evidence (criterion 6)** — grep `systemd/voice-typing.service` for `ExecStart=
   …/launch_daemon.sh` + `Restart=on-failure`; if installed, also `systemctl --user cat
   voice-typing`.
8. **Report** — per-criterion PASS/FAIL + the fenced `=== ACCEPTANCE EVIDENCE ===` block (real
   numbers); exit 0 iff all pass.
9. **Teardown** — `trap … EXIT`: `voicectl quit` → `kill -TERM $DAEMON_PID` → kill `vtidle` tmux →
   `rm -rf $WORK`. (No source restore — this test never swaps the default audio source.)

### Success Criteria

- [ ] `tests/test_idle_and_gpu.sh` exists, `+x`, `bash -n` clean, `shellcheck` clean (if installed).
- [ ] `./tests/test_idle_and_gpu.sh` passes on this CUDA box (prefetched models, no daemon, quiet).
- [ ] Criterion 5: 120 s armed silence → capture-pane UNCHANGED + `state.json last_final` UNCHANGED +
      daemon alive + avg CPU < 25 % of one core (real % printed).
- [ ] Criterion 8 / T6: daemon ran under `HF_HUB_OFFLINE=1` (offline proof) AND nvidia-smi shows ≥1
      daemon-tree row with Σ used_memory ∈ [1024, 5120] MiB (real rows + total printed).
- [ ] Criterion 6: voicectl toggle/start/stop/status/quit all `ok`; unit shows `ExecStart →
      launch_daemon.sh` + `Restart=on-failure`; post-ready status shows `listening: off`.
- [ ] `tests/ACCEPTANCE.md` records real output for 5/6/8 + the verification path for 1–4/7.
- [ ] Cleanup: daemon gone, `vtidle` tmux gone, temp removed — on PASS, error, and Ctrl-C.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the **two load-bearing techniques**
(`/proc` CPU averaging and `nvidia-smi` process-tree attribution) are derived in the research note
from a verified transcript on this machine, including the exact field math (`CLK_TCK=100`; utime=
field 14 = `rest[11]` after last-`)` split; stime = field 15 = `rest[12]`), the exact nvidia-smi CSV
shape (`pid, NNN MiB`, and the **comma-in-`process_name`** hazard), and the **Linux-uses-threads**
nuance (RealtimeSTT `start_recorder_worker` Linux branch → the daemon's MAIN PID holds the CUDA
context, so the tree-match is the robust, version-proof choice). The **daemon seams** the script
drives (`launch_daemon.sh`, `voicectl`, the tmux `send-keys -l` backend, the pinned control-socket
path, the `state.json` shape, the systemd unit) are cited with line-level detail. The **offline
proof** (`HF_HUB_OFFLINE=1`) is backed by the huggingface_hub docs + a verified listing of the
cached repos. Every validation command is executable as written.

### Documentation & References

```yaml
# MUST READ #1 — the spec for BOTH techniques (CPU averaging + nvidia-smi attribution) + the
#                Linux-threads nuance + the offline proof. Read FIRST; every claim is verified on
#                this machine or cited to a primary doc.
- file: plan/001_be48c74bc590/P1M7T4S1/research/idle_gpu_sampling.md
  why: "§1 /proc CPU math (CLK_TCK=100; utime=field14/rest[11], stime=field15/rest[12] after the
        last-')' split; sum over the PROCESS TREE; avg% = (Δticks/100)/wall_s*100; threshold <25 of
        ONE core, do NOT divide by nproc). §2 nvidia-smi --query-compute-apps csv shape
        ('pid, NNN MiB'); the G-VRAM-COMMAS hazard (process_name can contain commas -> query ONLY
        pid,used_memory); per-process = CUDA-context owner; sum matched rows; range [1024,5120] MiB.
        §3 HF_HUB_OFFLINE=1 = hard offline switch (criterion 8 proof); all 4 repos verified cached.
        §4 THE KEY NUANCE: RealtimeSTT start_recorder_worker (core/runtime.py:25) returns a
        threading.Thread ON LINUX -> the daemon's MAIN PID holds the CUDA context; SafePipe may add
        a child process -> match the whole descendant tree (robust to either). §5 system facts.
        §6 the exact T4/T6/6/8 assertions."
  critical: "G-CPU-SAMPLING: /proc (no pidstat). G-VRAM-ATTRIBUTION: match the daemon's descendant
             tree, NOT a bare pgrep. G-VRAM-COMMAS: never add process_name to the query. G-OFFLINE:
             launch with HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 (criterion 8 is proven by the run
             itself). G-OTHER-APPS: the GPU has unrelated compute apps -> filter by the daemon tree."

# MUST READ #2 — the daemon seams + control protocol + state.json shape the script drives.
- file: voice_typing/daemon.py
  why: "_default_control_socket_path() = $XDG_RUNTIME_DIR/voice-typing/control.sock (REAL path,
        pinned; no override without editing daemon.py -> PREFLIGHT). VoiceTypingDaemon boots
        NOT-listening (self._listening = threading.Event() cleared at boot; PRD §4.9) -> the ready
        voicectl status shows 'listening: off' (criterion 6 'starts un-armed'). status_snapshot() ->
        {listening, partial, last_final, uptime_s, device, compute_type, final_model,
        realtime_model} (voicectl status prints these -> T6 corroboration: device=cuda + the two
        model names). main() = the lifecycle launch_daemon.sh execs. shutdown() (quit path) releases
        GPU VRAM. _log_resolved_device() logs 'voice-typing device resolved: device=…' (in daemon.log)."
  critical: "The daemon binds the REAL control socket; a second daemon raises RuntimeError -> the
             preflight refusal is mandatory. 'voicectl quit' -> request_shutdown -> on_quit=
             daemon.shutdown (releases VRAM) -> the trap's kill -TERM is a backup."

# MUST READ #3 — voicectl (the criterion-6 control surface) exit codes + status format.
- file: voice_typing/ctl.py
  why: "main() exits 0 (daemon ok) / 1 (logical fail) / 2 (daemon not running). 'status' prints the
        multi-line snapshot (listening/partial/last/uptime/device/models). 'toggle'/'start'/'stop'
        arm/disarm. 'quit' shuts down. exit 0 from 'status' = a daemon IS running (preflight signal)."
  critical: "Use .venv/bin/voicectl. exit 0 from 'status' BEFORE launch = a daemon is already
             running -> refuse (G-PREFLIGHT). After launch, exercise toggle/start/stop/status/quit
             and capture each for criterion 6."

# MUST READ #4 — state.json (the T4 hallucination source-of-truth) + the config override surface.
- file: voice_typing/feedback.py
  why: "Feedback atomically writes {listening, phase, partial, last_final, ts} (tempfile+os.replace)
        to cfg.feedback.resolved_state_file(). record_final(text) sets last_final (on_final fires
        only after the blocklist gate in daemon.on_final). The path is OVERRIDABLE via
        feedback.state_file -> isolate to a temp path so the test reads the TEST daemon's last_final,
        not a real daemon's. snapshot() is the in-memory live state (voicectl status uses it)."
  critical: "T4 assertion: jq -r .last_final on the ISOLATED state file must equal the pre-window
             value (initially '') across the 120 s. A non-empty / changed last_final = a hallucinated
             final leaked past the blocklist = criterion 5 FAIL."
- file: voice_typing/config.py
  why: "VoiceTypingConfig.load() search: $XDG_CONFIG_HOME/voice-typing/config.toml -> <repo>/config.toml
        -> defaults. FeedbackConfig.state_file='' -> resolved_state_file() = $XDG_RUNTIME_DIR/
        voice-typing/state.json (RAISES if XDG_RUNTIME_DIR unset). [asr]/[filter]/[log] defaults ==
        repo config.toml (verified)."
  critical: "Set XDG_CONFIG_HOME=<tmp>/config with a minimal config.toml overriding ONLY [output]
        (backend=tmux, tmux_target='vtidle:0.0') + [feedback] (state_file=<tmp>/state.json,
        hypr_notify=false). [asr]/[filter]/[log] inherit production defaults (same models/VAD). Do
        NOT edit the repo config.toml."

# MUST READ #5 — the daemon launcher (LD_LIBRARY_PATH for cuDNN/cuBLAS) the script execs, OFFLINE.
- file: voice_typing/launch_daemon.sh
  why: "Computes LD_LIBRARY_PATH from the live nvidia-cublas/cudnn wheels then 'exec .venv/bin/python
        -m voice_typing.daemon'. Because it 'exec's, the backgrounded PID ($!) IS the python PID ->
        kill it on the trap. Export HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 IN THE launch_daemon.sh
        ENV (or the parent env) so the python child inherits them (criterion 8)."
  critical: "Launch 'voice_typing/launch_daemon.sh' (NOT raw python) so CUDA libs resolve. Pass
             XDG_CONFIG_HOME=<tmp>/config + the REAL XDG_RUNTIME_DIR + the two OFFLINE env vars."

# MUST READ #6 — the systemd unit (criterion-6 'auto-restart' + 'un-armed boot' evidence source).
- file: systemd/voice-typing.service
  why: "ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh (the wrapper, NOT
        raw python). Restart=on-failure + RestartSec=2. The comment block documents 'boots
        NOT-LISTENING' (PRD §4.9) -> grep ExecStart + Restart for criterion 6; the 'listening: off'
        half is proven at runtime via voicectl status (G-UNARMED)."
  critical: "Criterion 6 'auto-restarts on failure' = Restart=on-failure (a unit property ->
            greppable). 'starts un-armed' = runtime (voicectl status listening: off). Cite the unit
            file from the repo (do NOT depend on it being installed/enabled)."

# MUST READ #7 — the typing backend the T4 negative assertion reads (the tmux send-keys -l contract).
- file: voice_typing/typing_backends.py
  why: "TmuxBackend.type_text runs ['/usr/bin/tmux','send-keys','-t',cfg.output.tmux_target,'-l','--',text]
        — LITERAL keys, NO trailing Enter. This is WHY T4 reads typed text via 'capture-pane -p -S -'
        (tty echo) not 'cat the file mid-stream' (canonical-mode buffering; same G-CAPTURE as T3).
        _TMUX='/usr/bin/tmux'. make_backend(cfg.output) selects tmux when backend=='tmux'."
  critical: "If the hallucination guard FAILS and a final is typed, capture-pane (not the cat>file)
             catches it. The daemon appends a trailing SPACE per final (cfg.output.append_space), no
             newline."

# External citations (corroborate the research note).
- url: https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html
  why: "Field (14) utime %lu / (15) stime %lu: 'measured in clock ticks (divide by
        sysconf(_SC_CLK_TCK))'. Backs the G-CPU-SAMPLING math (CLK_TCK=100 on this box)."
- url: https://huggingface.co/docs/huggingface_hub/package_reference/utilities
  why: "'Offline mode is enabled by setting HF_HUB_OFFLINE=1 as environment variable.' Backs
        G-OFFLINE (criterion 8: the daemon loads cached models with zero network)."
- url: https://forums.developer.nvidia.com/t/unified-memory-nvidia-smi-memory-usage-interpretation/177372
  why: "'GPU Memory Usage (the bottom value, that is per-process) represents the size of the CUDA
        context.' Backs G-VRAM-ATTRIBUTION (per-process = CUDA-context owner; sum the daemon tree)."
```

### Current Codebase tree (state at P1.M7.T4.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── .gitignore                 # READ-ONLY (do NOT touch)
├── PRD.md                     # READ-ONLY (§6 T4/T6 contract; §7 acceptance)
├── pyproject.toml uv.lock     # DO NOT touch ([project.scripts] voicectl + voice-typing-daemon present)
├── config.toml                # DO NOT touch (override via XDG_CONFIG_HOME, NOT by editing this)
├── systemd/voice-typing.service  # READ-ONLY (grep ExecStart + Restart for criterion 6)
├── install.sh                 # READ-ONLY (prefetches models -> the offline cache)
├── voice_typing/              # READ-ONLY (daemon.py/ctl.py/feedback.py/config.py/typing_backends.py/
│   ├── launch_daemon.sh       #   cuda_check.py = seams; launch_daemon.sh = the wrapper exec'd OFFLINE)
│   └── ...
├── tests/                     # ← BOTH new files land HERE
│   ├── make_test_audio.sh     # P1.M7.T1.S1 (DONE) — NOT needed by this test (no audio), do not edit
│   ├── test_*.py              # unit tests (fast; read-only; house style) — criteria 1/2 evidence
│   ├── test_feed_audio.py     # P1.M7.T2.S1 — T1; referenced by ACCEPTANCE.md (criterion 1)
│   ├── e2e_virtual_mic.sh     # P1.M7.T3.S1 (PARALLEL) — T3; referenced by ACCEPTANCE.md (criteria 2/3/4)
│   ├── test_idle_and_gpu.sh   # ← CREATE (this task; T4+T6; +x)
│   ├── ACCEPTANCE.md          # ← CREATE (this task; PRD §7 evidence)
│   └── out/*.wav              # NOT needed by this test (no playback)
# venv: .venv/bin/voicectl, .venv/bin/python (the /proc + nvidia-smi helpers). System:
# /usr/bin/nvidia-smi, /usr/bin/tmux, /usr/bin/pgrep, jq. HF cache: ~/.cache/huggingface/hub (4 repos).
```

### Desired Codebase tree with files to be added

```bash
tests/
├── test_idle_and_gpu.sh       # NEW — this task's test artifact (T4 idle + T6 residency; offline; +x)
├── ACCEPTANCE.md              # NEW — this task's evidence doc (PRD §7 criteria 1-8 walk; real output)
├── make_test_audio.sh         # unchanged
├── e2e_virtual_mic.sh         # unchanged (P1.M7.T3.S1, parallel)
└── out/*.wav                  # unchanged (not consumed here)
# NOTHING ELSE is committed. The script mktemp -d's its work under /tmp and trap-rm's it.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G-OFFLINE) — launch the daemon with HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1.
#   Criterion 8 ("no network at runtime") is a CLAIM until a daemon is observed loading cached
#   models fully offline. Export BOTH vars in launch_daemon.sh's env (the python child inherits
#   them). All 4 repos are cached (~/.cache/huggingface/hub; verified). If the daemon STARTS,
#   goes ready, and survives 120s armed idle, that is empirical proof models load from cache with
#   ZERO network -> criterion 8 PASS. If a repo is missing it fails at startup (a real failure).
#   => Do NOT also set HF_DATASETS_OFFLINE etc.; HF_HUB_OFFLINE covers faster-whisper's resolution.

# CRITICAL #2 (G-CPU-SAMPLING) — /proc-based CPU averaging (pidstat/sysstat is NOT installed).
#   Read /proc/<pid>/stat; split on the LAST ')' (field 2 comm may contain spaces/parens); the
#   remainder's rest[11]=utime(field14), rest[12]=stime(field15), in clock ticks (CLK_TCK=100).
#   Sum utime+stime over the daemon PID + ALL descendants at T0 and T1. avg_pct_of_one_core =
#   (ΣΔticks / 100) / wall_elapsed_s * 100. Assert < 25. Do NOT divide by nproc (it is % of ONE core).

# CRITICAL #3 (G-CPU-TREE) — measure the PROCESS TREE, not just the daemon PID.
#   RealtimeSTT's start_recorder_worker returns a threading.Thread ON LINUX (core/runtime.py:25) ->
#   the daemon PID's utime+stime already aggregates the worker threads. BUT SafePipe
#   (core/safepipe.py:196) may spawn a real child process -> sum over PID + all descendants to be
#   correct regardless. Use a recursive walk of /proc/<pid>/task/<pid>/children (or pgrep -P loop).

# CRITICAL #4 (G-VRAM-ATTRIBUTION) — match the daemon's descendant TREE, not a bare process match.
#   nvidia-smi reports, per row, the PID owning the CUDA context. On Linux (threads) that is the
#   daemon's MAIN python PID; but match the whole tree to be robust to any spawn. Collect the daemon
#   PID + all descendants, then intersect with nvidia-smi's compute-app PIDs and SUM used_memory.
#   => Assert: ≥1 matched row AND Σ used_memory ∈ [1024, 5120] MiB (PRD §6 T6 "~1 and ~5 GB").

# CRITICAL #5 (G-VRAM-COMMAS) — query ONLY 'pid,used_memory'; NEVER add 'process_name'.
#   nvidia-smi --query-compute-apps=pid,process_name,used_memory can emit a process_name containing
#   COMMAS (verified: Chrome's --type=gpu-process cmdline is one comma-laden CSV field) which breaks
#   naive 'cut -d,' / split(','). The 2-column 'pid,used_memory' query is comma-safe. Parse the
#   memory column by stripping ' MiB' and int()-ing it.

# CRITICAL #6 (G-OTHER-APPS) — the GPU hosts unrelated compute apps; filter strictly by the tree.
#   At test time the GPU routinely shows Chrome's GPU process and (during the parallel T3 run) a
#   .venv/bin/python. NEVER assert on an arbitrary row; only rows whose PID is in the daemon tree count.

# CRITICAL #7 (G-UNARMED) — assert the daemon boots NOT-listening for criterion 6.
#   Right after 'voicectl status' first answers (ready), capture status and assert 'listening: off'
#   BEFORE issuing 'voicectl start'. This is the criterion-6 'starts un-armed' evidence (PRD §4.9;
#   daemon.py clears self._listening at boot). Doing it before start avoids a race.

# CRITICAL #8 (G-CAPTURE / G-IDLE-NO-TYPING) — read typed text via capture-pane for the T4 assertion.
#   The daemon types literal keys with NO newline (typing_backends -l; TmuxBackend). 'cat > file' is
#   empty mid-stream (pty canonical mode; same as T3). Read via '/usr/bin/tmux capture-pane -t vtidle
#   -p -S - | grep -v ^[[:space:]]*$ | paste -sd " '. Keep the pane running 'cat > "$CAPFILE"' and
#   cross-check after C-d. T4: snapshot before the 120s window + after; assert UNCHANGED (no
#   hallucinated final typed). ALSO assert state.json last_final UNCHANGED (belt-and-suspenders).

# CRITICAL #9 (G-RUNTIME) — keep the REAL XDG_RUNTIME_DIR; do NOT move it to a temp dir.
#   The control socket + state.json resolve from $XDG_RUNTIME_DIR; isolating it by setting
#   XDG_RUNTIME_DIR=<tmp> breaks PyAudio's PulseAudio backend (falls back to ALSA -> silence).
#   => Run launch_daemon.sh with the inherited (real) XDG_RUNTIME_DIR + temp XDG_CONFIG_HOME.
#   => Isolate state.json via the CONFIG override (feedback.state_file=<tmp>/state.json).

# CRITICAL #10 (G-PREFLIGHT) — refuse if a daemon is already running.
#   'voicectl status' (real env) exiting 0 means a daemon holds the real control socket; the test's
#   daemon could not bind (RuntimeError). Also check 'systemctl --user is-active voice-typing'.
#   => If either is true: print 'stop voice-typing first: systemctl --user stop voice-typing' and
#      exit non-zero. (Same preflight as T3 — the parallel T3 run will be refused, correctly
#      serializing the two heavy tests.)

# CRITICAL #11 (G-CONFIG) — override via XDG_CONFIG_HOME, NOT by editing config.toml.
#   XDG_CONFIG_HOME=<tmp>/config + voice-typing/config.toml overriding [output] (backend=tmux,
#   tmux_target='vtidle:0.0') + [feedback] (state_file=<tmp>/state.json, hypr_notify=false). [asr]/
#   [filter]/[log] inherit dataclass defaults == repo config.toml (same production models/VAD).

# CRITICAL #12 (G-TMUX-NAME) — use a DISTINCT tmux session name ('vtidle') to avoid clashing with T3.
#   T3 (parallel) uses session 'voicetest' + null-sink 'vt_test'. Use 'vtidle' so the two scripts'
#   tmux sessions never collide if both panes somehow coexist. Always /usr/bin/tmux (zsh aliases it).

# CRITICAL #13 (G-NOSOURCE) — this test does NOT swap the default audio source (simpler than T3).
#   T4 listens to ambient silence on the REAL default mic (no null-sink, no pw-cat, no set-default-
#   source). => The trap has NO source-restore step. (Caveat: run in a QUIET room — ambient speech
#   could produce a real final and falsely fail the 'no finals' assertion. Document as a precondition.)

# CRITICAL #14 (G-TIMEOUTS) — generous timeouts; model load is the long pole.
#   Daemon ready: poll voicectl status up to ~180s (cuDNN/cuBLAS cold init + 2 model loads, OFFLINE).
#   The idle window is FIXED at exactly 120s (PRD §6 T4 'silence for 120 s') — do not shorten.

# CRITICAL #15 (G-CLEANUP-IDEMPOTENT) — the trap must be idempotent + best-effort, on EXIT.
#   Each step (voicectl quit, kill PID, kill tmux session, rm tmp) wrapped in '|| true' /
#   '2>/dev/null'. The trap fires on EXIT (set -e aborts -> EXIT still runs -> cleanup always happens).

# CRITICAL #16 (G-EVIDENCE-BLOCK) — print a fenced '=== ACCEPTANCE EVIDENCE ===' block on PASS.
#   Real numbers only: the avg CPU %, the matched nvidia-smi rows + total VRAM MiB, the voicectl
#   status (device + models), the systemd grep, and per-criterion PASS/FAIL. The implementer pastes
#   this verbatim into tests/ACCEPTANCE.md (criteria 5/6/8). On FAIL, print the daemon.log tail.

# CRITICAL #17 (G-CRIT6-VOICECTL) — exercise toggle explicitly (start/stop/status/quit are obvious).
#   After stop, do 'voicectl toggle' (-> on) then 'voicectl toggle' (-> off) to record the toggle
#   subcommand works for criterion 6. Capture each command's output. Do this OUTSIDE the 120s window
#   (after stop, before quit) so it never disturbs the CPU/idle measurement.
```

## Implementation Blueprint

### Data models and structure

No ORM/pydantic. The script's "schema" is (1) the **temp work directory** layout, (2) the **two
stdlib python helpers** (/proc CPU parse + nvidia-smi match), and (3) the **criterion→evidence map**
that `ACCEPTANCE.md` records.

```bash
# (1) Temp work dir (mktemp -d; trap-rm'd). Layout:
#   $WORK/config/voice-typing/config.toml  # XDG_CONFIG_HOME override (tmux backend + isolated state_file)
#   $WORK/state.json                       # the daemon's ISOLATED state file (T4 last_final source)
#   $WORK/vt_out.txt                       # the tmux pane's 'cat > file' target (end-of-run cross-check)
#   $WORK/daemon.log                       # daemon stdout/stderr (device-resolved + latency lines)

# (2) Two stdlib python helpers (no numpy/torch) — invoked as heredocs via .venv/bin/python.
# cpu_tree_seconds(root_pid) -> float: sum utime+stime/CLK over root+descendants (G-CPU-SAMPLING/TREE).
# vram_match(tree_pids_csv)  -> prints 'matched=[(pid,mib)…] total=<N>' ; exit 0 iff matched && 1024<=total<=5120.

# (3) Criterion→evidence map (tests/ACCEPTANCE.md). Real output for 5/6/8 (from the script's block);
#     referenced commands for 1/2/3/4/7:
#   1  T1-T4,T6 pass by output        <- this script (T4/T6) + test_feed_audio.py (T1) + test_textproc.py (T2) + e2e_virtual_mic.sh (T3)
#   2  >=3s pause loses zero words    <- e2e_virtual_mic.sh (T3) / test_feed_audio.py (T1b)
#   3  live partials in state.json    <- e2e_virtual_mic.sh (T3)
#   4  nothing typed while off        <- e2e_virtual_mic.sh (T3)
#   5  idle 120s, no hallucination, trivial CPU  <- THIS SCRIPT (T4) [DIRECT EVIDENCE]
#   6  voicectl works; systemd; un-armed; auto-restart  <- THIS SCRIPT [DIRECT EVIDENCE]
#   7  git committed; README documents X  <- git status (committed); README = P2.M1.T2.S1 (pending)
#   8  no network at runtime          <- THIS SCRIPT (HF_HUB_OFFLINE=1 run) [DIRECT EVIDENCE]
```

### `tests/test_idle_and_gpu.sh` reference structure (research note §1–§6 + G‑* gotchas — implement close to this)

> The implementer writes ONE bash script. Below is the pinned scaffold. Adapt names/details as
> needed but KEEP: the offline launch (G‑OFFLINE), the /proc tree CPU sum (G‑CPU‑SAMPLING/TREE), the
> nvidia-smi tree match + comma-safe 2‑column query (G‑VRAM‑ATTRIBUTION/COMMAS/OTHER‑APPS), the
> un‑armed boot assertion (G‑UNARMED), the capture‑pane T4 read (G‑CAPTURE/IDLE‑NO‑TYPING), the real
> XDG_RUNTIME_DIR + temp XDG_CONFIG_HOME (G‑RUNTIME/CONFIG), the preflight (G‑PREFLIGHT), the
> distinct tmux name (G‑TMUX‑NAME), the fixed 120s window (G‑TIMEOUTS), the idempotent EXIT trap
> (G‑CLEANUP‑IDEMPOTENT), and the evidence block (G‑EVIDENCE‑BLOCK).

```bash
#!/usr/bin/env bash
# tests/test_idle_and_gpu.sh — idle stability (PRD §6 T4) + GPU residency (T6) + offline (criterion 8).
#
# Stands up the REAL daemon (launch_daemon.sh, HF_HUB_OFFLINE=1), arms it, holds 120s of silence,
# and asserts: (a) no finals typed / state.json last_final unchanged (hallucination guard), (b) no
# crash, (c) avg CPU <25% of one core (/proc). Then nvidia-smi shows the daemon-tree PID resident
# with used_memory in [1,5] GiB. Exercises voicectl toggle/start/stop/status/quit + greps the systemd
# unit for ExecStart/Restart (criterion 6). Prints an '=== ACCEPTANCE EVIDENCE ===' block for
# tests/ACCEPTANCE.md (criteria 5,6,8). A trap kills the daemon + tmux + temp on ANY exit.
#
# Real stack: CUDA Whisper + tmux. Heavy (~3-4 min). Run explicitly; NOT in the pytest suite.
#   cd /home/dustin/projects/voice-typing
#   systemctl --user stop voice-typing 2>/dev/null || true
#   ./tests/test_idle_and_gpu.sh
# Refuses to start if a voice-typing daemon is already running (preflight). Run in a QUIET room.
set -euo pipefail

# --- paths + tunables ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"; cd "$REPO"
VOICECTL="$REPO/.venv/bin/voicectl"; PY="$REPO/.venv/bin/python"
LAUNCH="$REPO/voice_typing/launch_daemon.sh"; UNIT="$REPO/systemd/voice-typing.service"
TMUX=/usr/bin/tmux; NVIDIA_SMI=/usr/bin/nvidia-smi
TMUX_SESS=vtidle; TMUX_TARGET="vtidle:0.0"
IDLE_SECS=120                     # PRD §6 T4: 'silence for 120 s' (FIXED — do not shorten)
CPU_LIMIT_PCT=25                  # < 25% of ONE core (PRD §6 T4)
VRAM_MIN_MIB=1024; VRAM_MAX_MIB=5120   # PRD §6 T6: ~1 and ~5 GB

# --- state (populated by setup; used by the trap) ---
WORK=""; DAEMON_PID=""

# --- cleanup (G-CLEANUP-IDEMPOTENT): idempotent + best-effort; fires on ANY exit (no source restore: G-NOSOURCE) ---
cleanup() {
  set +e; echo "--- cleanup ---"
  [ -n "${DAEMON_PID:-}" ] && { "$VOICECTL" quit >/dev/null 2>&1; sleep 2; kill -TERM "$DAEMON_PID" 2>/dev/null; wait "$DAEMON_PID" 2>/dev/null; }
  "$TMUX" kill-session -t "$TMUX_SESS" 2>/dev/null && echo "killed tmux session $TMUX_SESS"
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
}
trap cleanup EXIT

die() { echo "FAIL: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- preflight (G-PREFLIGHT/G-DEPS) ---
have jq || die "missing jq"
[ -x "$NVIDIA_SMI" ] || die "missing $NVIDIA_SMI"
[ -x "$TMUX" ] || die "missing $TMUX"
[ -x "$VOICECTL" ] || die "missing $VOICECTL (run install/uv sync)"
[ -x "$PY" ] || die "missing $PY"
[ -x "$LAUNCH" ] || die "missing $LAUNCH"
[ -f "$UNIT" ] || die "missing $UNIT"
if "$VOICECTL" status >/dev/null 2>&1; then
  die "a voice-typing daemon is already running (voicectl status answered). Stop it first: systemctl --user stop voice-typing"
fi
systemctl --user is-active voice-typing >/dev/null 2>&1 \
  && die "voice-typing systemd service is active; stop it first: systemctl --user stop voice-typing" || true

# --- setup (G-CONFIG/G-RUNTIME/G-TMUX-NAME) ---
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
"$TMUX" new-session -d -s "$TMUX_SESS" "cat > '$CAPFILE'" || die "tmux new-session failed"
"$TMUX" resize-window -t "$TMUX_SESS" -x 1000 2>/dev/null || true

# --- launch daemon OFFLINE (G-OFFLINE/G-RUNTIME/G-CONFIG) ---
# Real XDG_RUNTIME_DIR (PyAudio + control socket need it). Temp XDG_CONFIG_HOME (the override).
# HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 -> criterion 8 proof (models load from cache, zero network).
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
XDG_CONFIG_HOME="$WORK/config" "$LAUNCH" > "$WORK/daemon.log" 2>&1 &
DAEMON_PID=$!
echo "daemon launched OFFLINE (pid=$DAEMON_PID); waiting for ready (up to 180s)..."

# --- wait for ready (G-TIMEOUTS) ---
ready=0
for _ in $(seq 1 360); do            # 360 x 0.5s = 180s
  if "$VOICECTL" status >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited during startup (offline load failed?); see $WORK/daemon.log"
  sleep 0.5
done
[ "$ready" = 1 ] || die "daemon not ready in 180s; see $WORK/daemon.log"

# --- criterion 6 (un-armed boot) — capture BEFORE start (G-UNARMED) ---
STATUS_READY="$("$VOICECTL" status)" || die "voicectl status failed after ready"
echo "$STATUS_READY" | grep -q '^listening: off' \
  || { echo "FAIL: daemon did not boot un-armed:"; echo "$STATUS_READY"; exit 1; }
echo "[PASS] criterion 6 (un-armed boot): daemon started NOT-listening"

# --- criterion 6: exercise toggle (G-CRIT6-VOICECTL) — quick round-trip, OUTSIDE the idle window ---
"$VOICECTL" toggle >/dev/null || die "voicectl toggle (on) failed"
"$VOICECTL" toggle >/dev/null || die "voicectl toggle (off) failed"
echo "[PASS] criterion 6 (voicectl toggle): toggle on/off ok"

# --- helpers: /proc CPU-over-tree (G-CPU-SAMPLING/G-CPU-TREE) + nvidia-smi match (G-VRAM-*) ---
cpu_tree_seconds() {  # $1 = root pid -> total utime+stime seconds over root + descendants
  "$PY" - "$1" <<'PY'
import os,sys
CLK=os.sysconf(os.sysconf_names['SC_CLK_TCK'])
def ticks(pid):
    try:
        with open(f'/proc/{pid}/stat') as f: s=f.read()
        rp=s.rfind(')'); rest=s[rp+2:].split()      # split AFTER last ')' (comm may have parens)
        return int(rest[11])+int(rest[12])          # utime(14)+stime(15)
    except (FileNotFoundError,ProcessLookupError,ValueError,IndexError,OSError): return 0
def descendants(root):
    out={root}; stack=[root]
    while stack:
        p=stack.pop()
        try:
            with open(f'/proc/{p}/task/{p}/children') as f: ch=[int(x) for x in f.read().split()]
        except (FileNotFoundError,ProcessLookupError,OSError): ch=[]
        for c in ch:
            if c not in out: out.add(c); stack.append(c)
    return out
print(sum(ticks(p) for p in descendants(int(sys.argv[1])))/CLK)
PY
}
daemon_tree_pids() {  # $1 = root pid -> space-joined root + descendants
  "$PY" - "$1" <<'PY'
import sys
def descendants(root):
    out={root}; stack=[root]
    while stack:
        p=stack.pop()
        try:
            with open(f'/proc/{p}/task/{p}/children') as f: ch=[int(x) for x in f.read().split()]
        except (FileNotFoundError,ProcessLookupError,OSError): ch=[]
        for c in ch:
            if c not in out: out.add(c); stack.append(c)
    return out
print(' '.join(str(p) for p in descendants(int(sys.argv[1]))))
PY
}
capture_pane() { "$TMUX" capture-pane -t "$TMUX_SESS" -p -S - | grep -v '^[[:space:]]*$' | paste -sd ' '; }

# --- T4 idle window (criterion 5, CRITICAL) (G-CAPTURE/G-IDLE-NO-TYPING/G-CPU-SAMPLING) ---
cpu0="$(cpu_tree_seconds "$DAEMON_PID")"; wall0="$(date +%s)"
"$VOICECTL" start >/dev/null || die "voicectl start failed"
echo "listening armed (silent mic); holding ${IDLE_SECS}s of silence..."
typed_before="$(capture_pane)"
last_final_before="$(jq -r .last_final "$WORK/state.json" 2>/dev/null || true)"
sleep "$IDLE_SECS"
cpu1="$(cpu_tree_seconds "$DAEMON_PID")"; wall1="$(date +%s)"
typed_after="$(capture_pane)"
last_final_after="$(jq -r .last_final "$WORK/state.json" 2>/dev/null || true)"

# (a) no hallucinated finals typed (capture-pane unchanged AND state.json last_final unchanged)
IDLE_OK=0
if [ "$typed_before" = "$typed_after" ] && [ "$last_final_before" = "$last_final_after" ]; then
  echo "[PASS] criterion 5 (no hallucination): no finals typed, last_final unchanged across ${IDLE_SECS}s"
else
  echo "[FAIL] criterion 5 (hallucination guard): typed changed (${typed_before!r} -> ${typed_after!r}) OR last_final changed (${last_final_before!r} -> ${last_final_after!r})"; IDLE_OK=1
fi
# (b) no crash
kill -0 "$DAEMON_PID" 2>/dev/null && echo "[PASS] criterion 5 (no crash): daemon alive after ${IDLE_SECS}s" \
  || { echo "[FAIL] criterion 5: daemon died during idle"; IDLE_OK=1; }
# (c) CPU < 25% of one core (G-CPU-SAMPLING: do NOT divide by nproc)
elapsed=$(( wall1 - wall0 )); elapsed=${elapsed:-1}
avg_pct="$(awk -v c0="$cpu0" -v c1="$cpu1" -v e="$elapsed" 'BEGIN{ printf "%.2f", ((c1-c0)/e)*100 }')"
awk -v a="$avg_pct" -v L="$CPU_LIMIT_PCT" 'BEGIN{ exit !(a+0 < L+0) }' \
  && echo "[PASS] criterion 5 (CPU): avg ${avg_pct}% of one core (< ${CPU_LIMIT_PCT}%)" \
  || { echo "[FAIL] criterion 5 (CPU): avg ${avg_pct}% >= ${CPU_LIMIT_PCT}%"; IDLE_OK=1; }

# --- T6 GPU residency (criterion 6/8) (G-VRAM-ATTRIBUTION/COMMAS/OTHER-APPS) ---
"$VOICECTL" stop >/dev/null || die "voicectl stop failed"
TREE="$(daemon_tree_pids "$DAEMON_PID")"
VRAM_OUT="$("$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null || true)"
VRAM_VERDICT="$(printf '%s\n' "$VRAM_OUT" | "$PY" - "$TREE" <<'PY'
import sys
tree=set(int(x) for x in sys.argv[1].split())
matched=[]; total=0
for line in sys.stdin:
    parts=[p.strip() for p in line.split(',') if p.strip()!='']
    if len(parts)<2: continue
    try: pid=int(parts[0])
    except ValueError: continue
    mib=parts[1].replace('MiB','').strip()
    try: m=int(mib)
    except ValueError: continue
    if pid in tree: matched.append((pid,m)); total+=m
print(f"matched={matched} total_MiB={total}")
sys.exit(0 if matched and 1024<=total<=5120 else 1)
PY
)" && VRAM_RC=0 || VRAM_RC=1
if [ "$VRAM_RC" = 0 ]; then
  echo "[PASS] criterion 6/T6 (GPU residency): $VRAM_VERDICT (range ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB)"
else
  echo "[FAIL] criterion 6/T6 (GPU residency): $VRAM_VERDICT (daemon-tree PID not resident, or VRAM outside ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB)"; IDLE_OK=1
fi

# --- criterion 6: status (device + models) + systemd unit grep ---
STATUS_RUN="$("$VOICECTL" status)" || true
echo "voicectl status (post-run):"; echo "$STATUS_RUN"
EXEC_LINE="$(grep -E '^ExecStart=' "$UNIT")"; RESTART_LINE="$(grep -E '^Restart=' "$UNIT")"
echo "$EXEC_LINE" | grep -q 'launch_daemon\.sh' && echo "[PASS] criterion 6 (unit ExecStart): $EXEC_LINE" \
  || { echo "[FAIL] criterion 6 (unit ExecStart): $EXEC_LINE"; IDLE_OK=1; }
echo "$RESTART_LINE" | grep -q 'on-failure' && echo "[PASS] criterion 6 (unit Restart): $RESTART_LINE" \
  || { echo "[FAIL] criterion 6 (unit Restart): $RESTART_LINE"; IDLE_OK=1; }

# --- criterion 8 (no-network): restate — the whole run was under HF_HUB_OFFLINE=1 ---
[ "$ready" = 1 ] && echo "[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded cached models"

# --- evidence block for tests/ACCEPTANCE.md (G-EVIDENCE-BLOCK) ---
echo
echo "=== ACCEPTANCE EVIDENCE (paste into tests/ACCEPTANCE.md, criteria 5/6/8) ==="
echo "daemon_pid: $DAEMON_PID"
echo "idle_seconds: $IDLE_SECS"
echo "cpu_avg_pct_of_one_core: $avg_pct"
echo "nvidia_smi_compute_apps (daemon tree): $VRAM_VERDICT"
echo "voicectl_status:"
echo "$STATUS_RUN" | sed 's/^/  /'
echo "systemd_unit:"
echo "  $EXEC_LINE"
echo "  $RESTART_LINE"
echo "offline_env: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1"
echo "=== END ACCEPTANCE EVIDENCE ==="

# --- result ---
if [ "$IDLE_OK" = 0 ]; then echo "=== IDLE+GPU PASS (criteria 5,6,8) ==="; exit 0
else echo "=== IDLE+GPU FAIL (see above; daemon log: $WORK/daemon.log) ==="; tail -n 20 "$WORK/daemon.log" 2>/dev/null || true; exit 1; fi
```

### `tests/ACCEPTANCE.md` structure (committed evidence doc — Mode A)

> A committed Markdown doc the implementer writes (NOT generated by the script). It walks PRD §7
> criteria 1–8; for 5/6/8 it pastes the REAL `=== ACCEPTANCE EVIDENCE ===` block from a passing run
> of `test_idle_and_gpu.sh`; for 1–4 it cites the sibling test command + records PASS once run; for 7
> it cites `git status` + notes the README is P2.M1.T2.S1. Suggested sections:

```markdown
# Acceptance evidence — voice-typing (PRD §7 definition of done)

This document records the verified evidence for PRD §7 criteria 1–8. It is the human-readable
record criterion 1 requires ("T1–T4, T6 pass, demonstrated by actual command output"). Regenerate
the 5/6/8 block by running `./tests/test_idle_and_gpu.sh` and pasting its `=== ACCEPTANCE EVIDENCE ===`
output below.

## How to reproduce
`systemctl --user stop voice-typing 2>/dev/null; ./tests/test_idle_and_gpu.sh` (quiet room; models prefetched by `./install.sh`).

## Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | T1–T4, T6 pass by actual output | <PASS> | T1: `uv run pytest tests/test_feed_audio.py -v`; T2: `uv run pytest tests/test_textproc.py -v`; T3: `./tests/e2e_virtual_mic.sh`; T4+T6: `./tests/test_idle_and_gpu.sh` (block below) |
| 2 | ≥3 s pause loses zero words, session continues | <PASS via T3/T1b> | `./tests/e2e_virtual_mic.sh` (PAUSE_A + PAUSE_B both fuzzy-matched) |
| 3 | Live partials in state.json + tmux status | <PASS via T3> | `./tests/e2e_virtual_mic.sh` (≥1 non-empty partial snapshot) |
| 4 | Nothing typed while toggled off | <PASS via T3> | `./tests/e2e_virtual_mic.sh` (capture-pane unchanged after stop) |
| 5 | Idle ≥2 min, no hallucination, trivial CPU | **PASS (this task)** | <paste idle_secs + cpu_avg_pct + no-hallucination lines from the evidence block> |
| 6 | voicectl works; systemd unit; un-armed boot; auto-restart | **PASS (this task)** | <paste voicectl toggle/start/stop/status/quit + ExecStart + Restart + listening:off lines> |
| 7 | Committed to git; README documents install/hotkey/tmux/config/troubleshoot/CPU-mode | <git: all committed; README: P2.M1.T2.S1> | `git status` (clean); README pending P2.M1.T2.S1 |
| 8 | No network at runtime (models cached by install) | **PASS (this task)** | <paste offline_env line + the fact the daemon ran ready under HF_HUB_OFFLINE=1> |

### Evidence block — criteria 5, 6, 8 (from `./tests/test_idle_and_gpu.sh`)
<!-- paste the === ACCEPTANCE EVIDENCE === block here verbatim -->
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — /proc CPU averaging over the process tree (G-CPU-SAMPLING/TREE; no pidstat).
#   Sum utime+stime (fields 14/15 via the last-')' split) over root + descendants at T0 and T1;
#   avg% of ONE core = (Δticks/CLK_TCK)/wall_s*100; assert <25 (do NOT divide by nproc).
cpu0="$(cpu_tree_seconds "$DAEMON_PID")"; wall0="$(date +%s)"; voicectl start; sleep 120
cpu1="$(cpu_tree_seconds "$DAEMON_PID")"; wall1="$(date +%s)"
avg="$(awk -v c0="$cpu0" -v c1="$cpu1" -v e=$((wall1-wall0)) 'BEGIN{printf "%.2f",((c1-c0)/e)*100}')"

# PATTERN 2 — nvidia-smi tree match, comma-safe 2-column query (G-VRAM-ATTRIBUTION/COMMAS/OTHER-APPS).
#   Query ONLY pid,used_memory (process_name can contain commas -> breaks CSV). Match daemon-tree PIDs;
#   sum used_memory; assert ≥1 match && 1024<=total<=5120 MiB.
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | python - "$TREE_PIDS" # exit 0 iff in-range

# PATTERN 3 — T4 hallucination guard via capture-pane (G-CAPTURE/G-IDLE-NO-TYPING).
#   Snapshot capture-pane + state.json last_final BEFORE and AFTER the 120s; assert UNCHANGED.
typed_before="$(capture_pane)"; lfb="$(jq -r .last_final "$WORK/state.json")"; sleep 120
[ "$typed_before" = "$(capture_pane)" ] && [ "$lfb" = "$(jq -r .last_final "$WORK/state.json")" ]

# PATTERN 4 — offline launch (G-OFFLINE/G-RUNTIME/G-CONFIG). Real XDG_RUNTIME_DIR; temp XDG_CONFIG_HOME;
#   HF_HUB_OFFLINE=1 -> the run itself proves criterion 8 (no network; models from cache).
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
XDG_CONFIG_HOME="$WORK/config" voice_typing/launch_daemon.sh > "$WORK/daemon.log" 2>&1 &

# PATTERN 5 — un-armed boot assertion (G-UNARMED). Right after ready, BEFORE start.
voicectl status | grep -q '^listening: off'   # PRD §4.9; criterion 6 'starts un-armed'
```

### Integration Points

```yaml
CONSUMES — voice_typing production seams (READ-ONLY reuse; do NOT modify):
  - voice_typing/launch_daemon.sh        -> LD_LIBRARY_PATH wrapper; exec python -m voice_typing.daemon
  - voice_typing/ctl.py (voicectl)       -> toggle/start/stop/status/quit; exit 0/1/2
  - voice_typing/daemon._default_control_socket_path -> $XDG_RUNTIME_DIR/voice-typing/control.sock (REAL path)
  - voice_typing/feedback.Feedback       -> writes state.json {listening,phase,partial,last_final,ts}
  - voice_typing/typing_backends.TmuxBackend -> /usr/bin/tmux send-keys -t <target> -l -- text (NO newline)
  - voice_typing/config.VoiceTypingConfig.load -> $XDG_CONFIG_HOME/voice-typing/config.toml override

CONSUMES — system tooling (verified present): /usr/bin/nvidia-smi, /usr/bin/tmux, /usr/bin/pgrep, jq,
  .venv/bin/python (the /proc + nvidia-smi helpers), .venv/bin/voicectl. NO pidstat/sysstat (uses /proc).

CONSUMES — the HF model cache (prefetched by install.sh): ~/.cache/huggingface/hub has all 4 repos
  (distil-large-v3, small.en, tiny.en, large-v3-turbo) -> HF_HUB_OFFLINE=1 loads them with zero network.

CONSUMES (READ-ONLY) — systemd/voice-typing.service: grep ExecStart (-> launch_daemon.sh) + Restart
  (-> on-failure) for criterion 6. Does NOT require the unit to be installed/enabled (cite the repo file).

REFERENCES (sibling tests, for ACCEPTANCE.md criteria 1-4):
  - tests/test_feed_audio.py (T1)     -> criteria 1, 2(pause)
  - tests/test_textproc.py (T2)        -> criterion 1
  - tests/e2e_virtual_mic.sh (T3)      -> criteria 2, 3, 4

ISOLATION:
  - state.json:        overridden to $WORK/state.json via config (G-CONFIG) -> no clobber of a real daemon.
  - control socket:    REAL path (cannot move without editing daemon.py) -> PREFLIGHT refusal (G-PREFLIGHT).
  - tmux session:      'vtidle' (distinct from T3's 'voicetest') per G-TMUX-NAME.
  - audio source:      NOT swapped (G-NOSOURCE) — listens to ambient silence on the real default mic.

NO database. NO pyproject/uv.lock change. NO module edit. NO root .gitignore edit. NO config.toml edit.
NO install.sh / systemd edit. NO make_test_audio.sh edit. NO README (P2). NO test_feed_audio/e2e edit.
```

## Validation Loop

> Run from `/home/dustin/projects/voice-typing`. The fast pytest unit suite is UNAFFECTED (a bash
> script + a .md doc, neither collected by pytest). Requires: no voice-typing daemon running, models
> prefetched, a CUDA GPU, a QUIET room.

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
bash -n tests/test_idle_and_gpu.sh && echo "L1 syntax OK" || echo "L1 FAIL: syntax error"
shellcheck tests/test_idle_and_gpu.sh 2>/dev/null && echo "L1 shellcheck OK" || echo "L1 note: shellcheck not installed or warnings (review)"
test -x tests/test_idle_and_gpu.sh || { chmod +x tests/test_idle_and_gpu.sh && echo "L1 chmod +x"; }
# Expected: bash -n clean (zero errors). shellcheck clean if installed (warnings acceptable if the
# flagged construct is intentional, e.g. the 'for _ in $(seq ...)' ready-poll — document why).
```

### Level 2: Dry-Run Sanity (no daemon — fast pre-checks)

```bash
cd /home/dustin/projects/voice-typing
# preflight: no daemon -> proceeds; daemon running -> script would refuse
.venv/bin/voicectl status >/dev/null 2>&1 && echo "a daemon IS running (script would refuse)" \
                                              || echo "no daemon (preflight would proceed)"
# the offline env + cached repos are the criterion-8 precondition:
ls ~/.cache/huggingface/hub/ | grep -Eq 'faster-distil-whisper-large-v3|faster-whisper-small.en|faster-whisper-tiny.en' \
  && echo "L2 models cached OK (criterion 8 precondition)" || echo "L2 WARN: models not cached (run ./install.sh)"
# nvidia-smi query shape is as the script expects:
/usr/bin/nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader >/dev/null 2>&1 && echo "L2 nvidia-smi OK" || echo "L2 FAIL: nvidia-smi query"
# Expected: no daemon; models cached; nvidia-smi answers.
```

### Level 3: The Full Idle+GPU Test (the real validation — criteria 5, 6, 8 + T6)

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true   # preflight will refuse otherwise
./tests/test_idle_and_gpu.sh
# Expected (~3-4 min): prints ready status (device: cuda (float16) + models), per-criterion PASS
# lines (un-armed boot; toggle; no-hallucination; no-crash; CPU <25%; GPU residency; unit ExecStart/
# Restart; offline), and the fenced '=== ACCEPTANCE EVIDENCE ===' block; exit 0.
# If a criterion fails: the script prints the offending value(s) + daemon.log tail; exit 1.
```

### Level 4: ACCEPTANCE.md + Cleanup Verification

```bash
cd /home/dustin/projects/voice-typing
# paste the evidence block from a passing L3 run into tests/ACCEPTANCE.md (criteria 5/6/8), then:
test -f tests/ACCEPTANCE.md && grep -q 'criterion' tests/ACCEPTANCE.md && echo "L4 ACCEPTANCE.md present" || echo "L4 FAIL: no ACCEPTANCE.md"
# cleanup (on PASS, error, AND Ctrl-C — run the Ctrl-C case explicitly mid-run):
pgrep -af "voice_typing.daemon" >/dev/null && echo "L4 FAIL: daemon still running" || echo "L4 daemon gone OK"
/usr/bin/tmux has-session -t vtidle 2>/dev/null && echo "L4 FAIL: vtidle session leaked" || echo "L4 vtidle gone OK"
# Expected: daemon gone, vtidle gone, temp removed, on every exit path. (No audio-source check: this
# test never swaps it — G-NOSOURCE.)
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: `bash -n` clean; `shellcheck` clean (if installed); `+x` set.
- [ ] L3: `./tests/test_idle_and_gpu.sh` passes (CUDA + prefetched models + no daemon + quiet room).
- [ ] L4: daemon gone + `vtidle` tmux gone + temp removed — on PASS, error, AND Ctrl-C (run Ctrl-C explicitly).
- [ ] L2: models cached (criterion-8 precondition); nvidia-smi query answers.

### Feature Validation

- [ ] Criterion 5: 120 s armed silence → capture-pane UNCHANGED + `state.json last_final` UNCHANGED +
      daemon alive + avg CPU < 25 % of one core (real % printed).
- [ ] Criterion 8 / T6: daemon ran under `HF_HUB_OFFLINE=1` (offline proof) AND nvidia-smi shows ≥1
      daemon-tree row with Σ used_memory ∈ [1024, 5120] MiB (real rows + total printed).
- [ ] Criterion 6: voicectl toggle/start/stop/status/quit all `ok`; unit shows `ExecStart →
      launch_daemon.sh` + `Restart=on-failure`; post-ready status shows `listening: off`.
- [ ] Preflight refuses to start if a daemon is already running.
- [ ] `tests/ACCEPTANCE.md` records real output for 5/6/8 + the verification path for 1–4/7.

### Code Quality Validation

- [ ] File placement: `tests/test_idle_and_gpu.sh` + `tests/ACCEPTANCE.md` per PRD §4.1 layout; `+x`.
- [ ] Follows house shell style (`set -euo pipefail`, `command -v` checks, `mktemp -d` + `trap rm`,
      `/usr/bin/tmux`, `.venv/bin/*`) — compare `tests/e2e_virtual_mic.sh` (P1.M7.T3.S1) +
      `tests/make_test_audio.sh` (P1.M7.T1.S1).
- [ ] The load-bearing invariants upheld: G-OFFLINE, G-CPU-SAMPLING/TREE, G-VRAM-ATTRIBUTION/COMMAS/
      OTHER-APPS, G-UNARMED, G-CAPTURE/IDLE-NO-TYPING, G-RUNTIME/CONFIG, G-PREFLIGHT, G-TMUX-NAME,
      G-NOSOURCE, G-TIMEOUTS, G-CLEANUP-IDEMPOTENT, G-EVIDENCE-BLOCK.
- [ ] No edit to `voice_typing/*`, `pyproject.toml`, `config.toml`, `tests/make_test_audio.sh`,
      `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`, `systemd/*`, `install.sh`; no README;
      no `test_feed_audio.py` / `e2e_virtual_mic.sh` edit.

### Documentation & Deployment

- [ ] Script header documents: PRD §6 T4/T6, the criteria (5/6/8), the offline rationale (G-OFFLINE),
      the /proc + nvidia-smi approach, the run command, the preflight refusal, the quiet-room caveat,
      and the cleanup guarantee.
- [ ] `tests/ACCEPTANCE.md` documents the verified evidence (criteria 5/6/8 real; 1–4/7 referenced) —
      referenced by the final README (P2.M1.T2.S1).
- [ ] No new env vars required beyond the per-run `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` +
      `XDG_CONFIG_HOME`. No config change.

---

## Anti-Patterns to Avoid

- ❌ Don't add `process_name` to `--query-compute-apps` — it can contain commas (Chrome's cmdline) and
  breaks CSV parsing. Query ONLY `pid,used_memory` (G-VRAM-COMMAS).
- ❌ Don't assert on an arbitrary nvidia-smi row — the GPU hosts unrelated apps (Chrome, a parallel
  test daemon). Match the daemon's **descendant tree** and sum matched rows (G-VRAM-ATTRIBUTION/
  OTHER-APPS).
- ❌ Don't measure CPU of the daemon PID alone — RealtimeSTT's SafePipe may spawn a child process; sum
  over the **process tree** (G-CPU-TREE). And do NOT divide by `nproc` — the threshold is % of ONE core.
- ❌ Don't use `pidstat`/sysstat — it isn't installed. Use `/proc/<pid>/stat` (G-CPU-SAMPLING).
- ❌ Don't skip `HF_HUB_OFFLINE=1` — running online only *claims* criterion 8; the offline run is the
  *proof* (G-OFFLINE). Cache presence is necessary but not sufficient.
- ❌ Don't read typed text from `cat > file` mid-stream — the daemon types literal keys with **no
  newline**, so the pty canonical-mode buffers `cat`'s input. Use `tmux capture-pane -p -S -` (reads
  the tty echo) (G-CAPTURE).
- ❌ Don't move `XDG_RUNTIME_DIR` to a temp dir — it breaks PyAudio's PulseAudio backend (falls back
  to ALSA → silence) (G-RUNTIME). Isolate state.json via the **config override**; accept the real
  control socket and preflight for a running daemon.
- ❌ Don't shorten the 120 s window — PRD §6 T4 says "120 s". And don't start the CPU clock before
  `voicectl start` (the window must be the ARMED idle period).
- ❌ Don't assert `listening: off` AFTER `voicectl start` — capture it right after ready, BEFORE start
  (G-UNARMED), or the assertion is meaningless.
- ❌ Don't forget the quiet-room caveat — ambient speech on the real mic could produce a real final
  and spuriously fail the "no finals" assertion (G-NOSOURCE). Document it as a precondition.
- ❌ Don't use `tmux` (zsh aliases it) — always `/usr/bin/tmux`; and use the session name `vtidle`
  (distinct from T3's `voicetest`) so the two heavy tests never collide (G-TMUX-NAME).
- ❌ Don't make the trap fragile — every cleanup step must be idempotent + best-effort (`|| true` /
  `2>/dev/null`) and fire on `EXIT` so it runs on PASS, error, and Ctrl-C (G-CLEANUP-IDEMPOTENT).
- ❌ Don't edit `config.toml` / `systemd/*` / `install.sh` / any module to "make the test pass" —
  override via `XDG_CONFIG_HOME`; cite the unit file read-only; this is a TEST + DOC, nothing else.

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is one bash script + one Markdown doc
whose **entire mechanism is verified on this machine**: the `/proc` CPU math (CLK_TCK=100; utime=
field 14/stime=field 15 via the last-`)` split — run against `/proc/self/stat`); the nvidia-smi CSV
shape (`pid, NNN MiB`) and the **comma-in-`process_name`** hazard (observed on Chrome's row); the
**Linux-uses-threads** nuance (RealtimeSTT `core/runtime.py:25` `start_recorder_worker` Linux branch →
threading.Thread → the daemon's MAIN PID holds the CUDA context, so the tree-match is robust to
threads-or-processes); the offline proof (`HF_HUB_OFFLINE=1` + all 4 repos verified cached); and the
daemon seams (`launch_daemon.sh`, `voicectl` exit codes + status format, the `state.json` shape, the
tmux `send-keys -l` contract, the systemd unit's `ExecStart`/`Restart`). The reuse of T3's preflight
+ config-override + capture-pane + trap conventions keeps the script shape familiar. The −1 residual
risk is **ambient-noise realism**: T4 listens to the *real* mic for 120 s, so a non-quiet room could
produce a real (non-hallucinated) final and spuriously fail the "no finals" assertion — mitigated by
documenting the quiet-room precondition and by the dual check (capture-pane AND `last_final`
unchanged). A second residual is **whether the GPU is truly idle-free of transient apps** during the
run — the tree-match makes the test correct regardless, but a wildly loaded GPU could in principle
slow model load past the 180 s ready timeout; recoverable by re-running.
