# PRP — P1.M5.T3.S2: Audit T6 GPU lifecycle script (`tests/test_idle_and_gpu.sh`) — nvidia-smi idle/armed/disarmed/unload assertions

## Goal

**Feature Goal**: Produce a **complete static audit** of `tests/test_idle_and_gpu.sh` (779 lines)
against **PRD §6 T6** (GPU lifecycle — lazy-load 4-part lifecycle) and the work-item's **8 sub-checks
(a)–(h)**, by reading the script + cross-checking every claim against the LIVE source it drives
(ctl.py / config.py / daemon.py — and the sibling `e2e_virtual_mic.sh` for the timeout-discipline
comparison inherited from P1.M5.T3.S1), then recording a per-check PASS/OBSERVATION matrix, the one
minor (g) finding, the correct-design notes (test-time threshold compression, ISSUE-3/auto_stop
interaction, daemon-tree matching), and an explicit **safe-to-run verdict**. **The script is NOT
executed** — it loads CUDA models for ~5–8 min (2 cold inits + 120 s armed idle + idle-unload waits)
per AGENTS.md + the work-item's explicit "do NOT run it unless explicitly required." The audit is
STATIC.

**Verified baseline (research, this round — NO CUDA load, NO script run):**
- **7 of 8 checks PASS clean (a,b,c,d,e,f,h).** The T6 4-part lifecycle (idle→armed→disarmed-resident
  →idle-unload-gone→re-arm-reload) is correctly implemented end-to-end: `nvidia-smi
  --query-compute-apps=pid,used_memory` query (L229/489/716), `assert_vram_absent`/`assert_vram_present`
  helpers (L253/263), polling `wait_vram_*` (L278/286), the T6(a) boot-absent assertion BEFORE first
  arm (L447), T6(b) armed-present [1024,5120] MiB = ~1–5 GB (L481-484), T6(c) disarmed-still-present
  (L546), T6(d-gone) idle-unload→~0 VRAM on the 5s-override run (L707-709), T6(d-reload) re-arm→present
  again (L727-730). All cross-checked against LIVE source (daemon.py:1233-1239 `_bounded_shutdown
  (timeout=5.0)` killpg → releases ALL VRAM while daemon LIVES; config.py:67 default 1800.0).
- **MINOR OBSERVATION (g) [LOW] — `status` calls deliberately unwrapped:** `VOICECTL_TIMEOUT=30`
  (L156) + `voicectl() { timeout … }` wrapper fn (L357) wrap **all control calls** (start/stop/toggle
  /toggle-lite/quit — the actual hang vectors). But **13 `"$VOICECTL" status` callsites are bare**
  (L306,379,461,536,549,605,615,631,635,643,653,658,720) by deliberate design ("status is lock-free
  + needs full output, never hangs"). Mostly-correct, but AGENTS.md Rule 1 contradicts ("Always wrap:
  `timeout 15 .venv/bin/voicectl status` … a dead daemon still wedges it") — ctl.py:111-118 confirms
  status has NO socket read timeout. **Most-exposed callsite:** `wait_daemon_ready` L304-312 — the
  180s budget is an iteration COUNT, not a per-call timeout; the `kill -0` liveness check is AFTER the
  status call, so a single hung status defeats it. **Practical risk LOW** (cold-start = connection-
  refused fast-fail; the wedge is a narrow regression). This is the timeout-discipline PRECEDENT the
  sibling e2e script (P1.M5.T3.S1) cites — correctly, for control calls.
- **Safe-to-run verdict: YES (operator-present).** Preflight refuses if a daemon runs (L379-382 — both
  voicectl-answers AND systemd-active). **No global audio mutation** (G-NOSOURCE — no null-sink, no
  `pactl set-default-source`; listens to ambient silence on the real mic, so there's NOTHING to
  restore on crash → simpler + safer trap than e2e). Cleanup trap is robust + idempotent (quit→SIGTERM
  →8s→SIGKILL, kill tmux `vtidle`, rm temp). **Caveat:** the (g) status gap means a wedged daemon's
  control thread could hang `wait_daemon_ready`/preflight — safe-but-not-unattended-safe until the §3
  fix. Heavy (~5–8 min); AGENTS.md bash-tool `timeout` **900**; `systemctl --user stop voice-typing`
  first.

**Deliverable** (1 artifact — CREATE; **NO source/test/script edit** — this is a REPORT item):
- `plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md` — a self-contained audit report with: the 8-check
  (a–h) PASS/OBSERVATION matrix (each row = check → script line → LIVE-source evidence → verdict),
  the PRD §6 T6 4-part lifecycle map, the one minor (g) finding with PRD/AGENTS citation + recommended
  fix, the correct-design notes (NOT gaps), and the safe-to-run verdict. No existing `gap_gpu_test.md`
  at that path. (Source-side `architecture/gap_*.md` reports already exist for the modules — this is
  the TEST-SCRIPT-side audit.)

**Success Definition**:
- (a) The full `tests/test_idle_and_gpu.sh` is read + every T6 claim cross-checked against the LIVE
  source modules it drives (ctl.py:111-118 no-socket-timeout, config.py:65/67 auto_stop/auto_unload
  defaults, daemon.py:733-739+1233-1239 bounded teardown + idle-unload watchdog, e2e_virtual_mic.sh
  for the timeout comparison). Findings recorded with exact script line numbers + source citations.
- (b) The 8-check matrix (a–h) is COMPLETE; each row has a verdict (PASS/MINOR-OBSERVATION) + the
  script line + the LIVE-source evidence that proves the verdict (no inference, no hand-waving).
- (c) The (g) minor finding is recorded with: the VOICECTL_TIMEOUT=30 + voicectl() fn citation (the
  PASS half), the 13 bare-status callsite table + the AGENTS.md Rule 1 / ctl.py:111-118 contradiction
  (the OBSERVATION half), the most-exposed callsite (wait_daemon_ready), the recommended fix (for a
  downstream REMEDIATION task — NOT applied here).
- (d) The safe-to-run verdict is explicit: YES (operator-present) + the (g) caveat + the fact the trap
  is robust + NO audio-source swap (so nothing to restore). The script is NOT run during this item.
- (e) Scope respected: ONLY the T6 GPU-lifecycle slice (a–f) + (g) timeout + (h) preflight are
  audited. T4 (criterion 5), criterion 6 (un-armed boot/toggle/unit grep), criterion 8 (offline
  grep), T7 (lite mode-switch) are present in the script but are owned by sibling items
  (P1.M5.T4.* / P1.M5.T5.*) — noted, NOT deep-audited. NO source/test/script file is edited.

## User Persona

**Target User**: Internal — the plan orchestrator + downstream leaves:
1. **P1.M5.T5.S1** (acceptance-criteria cross-check) consumes this audit as the **evidence-quality
   gate** for Acceptance **#9** (idle-unload reclaims ~0 VRAM via nvidia-smi + a later arm reloads):
   this script is the ONLY artifact that can prove #9 against real CUDA, so the cross-check must
   credit it precisely (T6(d) lifecycle = #9). The (g) status caveat is also relevant to the
   timeout-discipline credit.
2. **P1.M5.T3.S1** (the sibling e2e script audit, currently implementing) — that PRP cites THIS
   script (`test_idle_and_gpu.sh:156,357` VOICECTL_TIMEOUT=30 + voicectl() fn) as the timeout
   precedent e2e SHOULD follow. This item CONFIRMS that precedent holds for control calls (the
   inheritance is valid) + refines it: status is deliberately unwrapped here too, so e2e's gap (5/6
   unwrapped control calls) is the real divergence, not a shared blind spot.
3. **A downstream REMEDIATION task** (if opened for the (g) finding) reads this report as the spec:
   the `voicectl_status()` helper shape + the 2 most-exposed callsites (wait_daemon_ready, preflight).
4. **Operators/reviewers** read `gap_gpu_test.md` to decide whether the GPU test is safe to run for
   real-CUDA acceptance evidence (criterion 5/#9), and what to fix first for unattended/CI safety.

**Use Case**: The compliance round (006) audited every module (the `architecture/gap_*.md` reports) +
converted the unit audits into "tests pass" (P1.M5.T1.*). THIS item audits the **real-CUDA GPU
lifecycle shell script** — the only artifact that can prove Acceptance #9 (the §4.2bis idle-unload
reclaims ~0 VRAM + reloads) against a real GPU. The audit determines: (1) does the script correctly
assert the 4-part T6 lifecycle (idle→armed→disarmed-resident→unload-gone→rearm-reload)? (2) does it
match the right daemon TREE (not an arbitrary nvidia-smi row)? (3) is its timeout discipline sound?
(4) is its preflight + cleanup safe? (5) is it safe to run, or does the (g) status gap need fixing
first for unattended runs?

**Pain Points Addressed**: (1) The GPU test is the only real-CUDA proof for Acceptance #9 — the
riskiest clause in the PRD (the idle-unload must release the realtime-model CUDA primary context,
which the old in-process recorder couldn't). An audit confirms the script asserts the right thing
(daemon-tree ABSENT vs PRESENT, ~0 vs ~1–5 GB) BEFORE anyone burns 5–8 min running it. (2) It surfaces
the (g) status-unwrap nuance as an explicit finding so the timeout-discipline credit is honest
(control ✅; status ✅-with-caveat) rather than treating the script as fully timeout-safe. (3) It
confirms the script does NOT mutate the global audio source (unlike e2e) → safer to run → lowers the
bar for a later authorized run.

## Why

- **The GPU test is the ONLY real-CUDA proof for Acceptance #9** (the idle-unload reclaims ~0 VRAM +
  a later arm reloads). The mocked daemon tests (P1.M5.T1.S2) prove the lifecycle LOGIC; only this
  script proves the ACTUAL VRAM release against `nvidia-smi` on a real GPU — including the subprocess
  recorder-host model's claim that `killpg` releases the realtime-model CUDA primary context. Auditing
  it (not running it) is the safe way to validate it before a later, explicitly-authorized run.
- **It does NOT mutate the global audio source — the lowest-stakes heavy test.** Unlike e2e_virtual_
  mic.sh (which rebinds `pactl set-default-source`), this test listens to ambient silence on the real
  mic (G-NOSOURCE) → there's NOTHING to restore on a crash → the trap is simpler + the test is
  strictly safer to run. Recording this lowers the bar for a later authorized run.
- **It surfaces the (g) status-unwrap nuance as a timeout-discipline finding.** AGENTS.md Rule 1 exists
  because voicectl's control socket has no read timeout (ctl.py:111-118). This script wraps all
  CONTROL calls (the hang vectors) via the voicectl() fn — correctly. But its 13 status callsites are
  bare, and `wait_daemon_ready`'s 180s budget is an iteration count (a single hung status defeats it).
  Finding this NOW (before a run) refines the timeout-credit picture + flags the one callsite to fix
  for unattended/CI safety; finding it LATER (after a hang) is exactly the "session hangs forever"
  scenario AGENTS.md was written to prevent.
- **It corrects the acceptance evidence picture.** PRD §6 T6 is a 4-part lifecycle (a/b/c/d). The
  script covers all 4 (T6(a) boot-absent, T6(b) armed-present, T6(c) disarmed-resident, T6(d) gone-
  then-reload) on a 2-run design (default 1800s threshold for a/b/c + the 120s T4 window; 5s override
  for d). Recording this lets P1.M5.T5.S1 credit the script for **#9** fully (all 4 lifecycle states
  proven against real CUDA), plus criterion 5 (T4) + criterion 8 (offline grep) + criterion 6
  (un-armed boot/unit grep) as side coverage.
- **The findings are already in place** (research this round). So this item is low-risk: re-verify the
  8 checks + the (g) finding against LIVE source, write the report. The value is the evidence artifact
  + the explicit (g) flag — not heroic debugging.

## What

Three phases, in order: **(1) read the script + LIVE-source cross-check**, **(2) the 8-check (a–h)
matrix + the (g) finding + the correct-design notes**, **(3) the safe-to-run verdict**. Output =
`gap_gpu_test.md`. **The script is NOT executed** (AGENTS.md + work-item: ~5–8 min, CUDA, heavy).

### Success Criteria

- [ ] `tests/test_idle_and_gpu.sh` read end-to-end (779 lines); every T6 claim cross-checked against
      the LIVE source it drives (ctl.py:111-118 makefile/no-settimeout, config.py:65 auto_stop=30.0 +
      config.py:67 auto_unload=1800.0, daemon.py:733-739 resident teardown + 1233-1239 idle-unload
      watchdog → `_bounded_shutdown(timeout=5.0)` killpg, e2e_virtual_mic.sh for the timeout comparison).
- [ ] 8-check matrix (a–h) COMPLETE; each row = check → script line(s) → LIVE-source evidence → verdict.
- [ ] T6 4-part lifecycle map (PRD §6 T6 a/b/c/d ↔ checks b/c/d/e+f) recorded with verdicts.
- [ ] MINOR OBSERVATION (g) [LOW] recorded: the VOICECTL_TIMEOUT=30 + voicectl() fn (PASS half); the
      13 bare-status callsite table + AGENTS.md Rule 1 / ctl.py:111-118 contradiction (OBSERVATION
      half); the most-exposed callsite (wait_daemon_ready L304-312: 180s is an iteration count, kill-0
      is AFTER status); the recommended fix (voicectl_status() helper / wrap loop calls) for a
      downstream REMEDIATION task.
- [ ] Correct-design notes recorded (NOT gaps): test-time threshold compression (1800s→5s 2-run
      design), ISSUE-3/auto_stop interaction (T6(c) may run against already-disarmed daemon),
      daemon-tree matching (G-VRAM-ATTRIBUTION), polling-not-sleeping (G-TIMEOUTS), robust idempotent
      trap (G-CLEANUP-IDEMPOTENT), no-audio-swap (G-NOSOURCE).
- [ ] Safe-to-run verdict explicit (YES operator-present; preflight + robust trap + NO audio swap;
      caveat = (g) status gap → not unattended-safe); the script NOT run during this item.
- [ ] `gap_gpu_test.md` written to `plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md`, self-contained,
      with a clear VERDICT ("7/8 checks PASS; 1 minor observation (g status-unwrap LOW); safe-to-run =
      YES operator-present (caveat: not unattended-safe until (g) fix)").
- [ ] Scope respected: ONLY the T6 slice (a–f) + (g) + (h) audited; T4/criterion-6/criterion-8/T7
      noted as present-but-out-of-scope (sibling items); NO source/test/script edited (REPORT item).

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the full per-check matrix (a–h) pre-verified with script line
numbers + LIVE-source citations, the (g) finding fully analyzed (PASS half + OBSERVATION half + most-
exposed callsite + fix), the correct-design notes, the safe-to-run verdict, the exact source-line
references to re-confirm, the verbatim `gap_gpu_test.md` scaffold, and the hard constraint (do NOT run
the script). No inference required.

### Documentation & References

```yaml
# MUST READ — the audit SUBJECT (read it; it is what you are auditing, not running).
- file: tests/test_idle_and_gpu.sh
  why: "The 779-line GPU/idle script. Its G-* load-bearing invariants: G-VRAM-ATTRIBUTION (match the
        daemon DESCENDANT TREE vs nvidia-smi PIDs, NOT an arbitrary row — PID presence/absence is the
        hard signal; used_memory is secondary corroboration; the CUDA context lives on the CHILD
        recorder-host PID, not the daemon PID, so tree-matching is essential); G-VRAM-COMMAS (query
        ONLY pid,used_memory — process_name can contain commas → breaks CSV); G-TIMEOUTS (POLL every
        0.5s with a deadline ceiling ~25s/15s, NEVER a fixed sleep; the contract's literal '7s' is
        under-budgeted); G-CONFIG (2-run design: Run 1 default 1800s threshold so T4's 120s window +
        T6(c) are unaffected; Run 2 [asr] auto_unload_idle_seconds=5.0 override via a 2nd
        XDG_CONFIG_HOME so T6(d) fires in bounded time); G-PREFLIGHT (refuse if voicectl answers OR
        systemd-active); G-CLEANUP-IDEMPOTENT (quit→SIGTERM→8s→SIGKILL, idempotent; kill tmux; rm
        temp; every step || true); G-NOSOURCE (do NOT swap the default audio source — simpler trap,
        nothing to restore); G-CPU-SAMPLING/G-CPU-TREE (/proc utime+stime over the process tree,
        pidstat NOT installed). These encode the 'correct' verdict on checks a–f,h."
  critical: "NOTE the script wraps ALL CONTROL voicectl calls via the voicectl() fn (L357,
             VOICECTL_TIMEOUT=30 L156) but leaves 13 status callsites BARE (deliberate). That is the
             (g) minor observation. Also NOTE the 2-run design (Run 1 = default threshold for a/b/c
             + T4; Run 2 = 5s override for d) — the threshold compression is CORRECT, not a gap."

# MUST READ — the LIVE source the script drives (cross-check every claim here, don't infer).
- file: voice_typing/ctl.py
  why: "Lines 111-118: send_command 'Uses makefile(\"r\") (NOT settimeout — makefile raises if the
        socket has a timeout …)'. CONFIRMS voicectl has NO socket read timeout → a wedged control
        thread hangs ANY voicectl command (incl. status) FOREVER. This is the root of the (g) nuance:
        status is lock-free but a non-responsive control thread still blocks it."
  critical: "The control socket will NEVER time out on its own — AGENTS.md Rule 1 /
             VOICECTL_TIMEOUT=30 exist for exactly this reason. The voicectl() wrapper bounds control
             calls; status is deliberately unbounded (the (g) observation)."

- file: voice_typing/config.py
  why: "Line 67 `auto_unload_idle_seconds: float = 1800.0` (PRD §4.2bis default; Run 2 overrides to
        5.0 via XDG_CONFIG_HOME). Line 65 `auto_stop_idle_seconds: float = 30.0` (the ISSUE-3 /
        T4-T6(c) interaction: auto-stop disarms at 30s during T4's 120s window, so T6(c) may run
        against an already-disarmed daemon). CONFIRMS the 2-run threshold-compression design + the
        auto_stop subtlety."
  critical: "The 5s override on Run 2 is the ONLY way to test idle-unload in bounded time — the
             default 1800s (30 min) would be impractical AND would corrupt T4's 120s armed window on
             Run 1. This is correct test design, not a shortcut."

- file: voice_typing/daemon.py
  why: "(1) Lines 733-739: resident teardown under _lock → `_bounded_shutdown(timeout=5.0)` (the
        bounded killpg-after-join(5s) — NO 90s hang). (2) Lines 831-833: the idle-unload watchdog
        thread ('voice-typing-idle-unload'). (3) Lines 1184/1222: `threshold =
        self._cfg.asr.auto_unload_idle_seconds`. (4) Lines 1233-1239: logs 'voice-typing idle-unload:
        %.1fs disarmed; unloading models' → `_bounded_shutdown(timeout=5.0)` = terminate the child
        PROCESS GROUP → ALL VRAM released (incl. the realtime-model CUDA primary context) while the
        daemon LIVES. CONFIRMS T6(d)'s VRAM release is bounded + complete (PRD §7.9 + §4.2bis)."
  critical: "This is the §7.9 crux: the daemon NEVER touches CUDA (the recorder lives in the child);
             killpg releases ALL VRAM. T6(d-gone) passing proves this end-to-end on a real GPU. A FAIL
             would mean a grandchild orphaned — a PRODUCTION bug, NOT a test bug (the script's FAIL
             block says so explicitly)."

# MUST READ — AGENTS.md (the hard rules; the timeout rule binds this audit directly).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on EVERY non-trivial command; 'voicectl always under timeout 30. The
        control socket will never time out on its own' + the status row: 'Always wrap: timeout 15
        .venv/bin/voicectl status … a dead daemon still wedges it'). The hang-vectors table rows for
        voicectl status + the test_idle_and_gpu.sh row ('~5–8 min: two cold inits + 120 s armed-idle +
        idle-unload waits … give the bash tool a timeout of 900 … preflight refuses to start if the
        unit is already running — systemctl --user stop voice-typing first')."
  critical: "Do NOT run the script. If you did run it and it wedged, the AGENTS.md Cleanup block
             (timeout 30 voicectl quit; systemctl --user stop; pkill) is the recovery — but you should
             not need it. The audit is STATIC. Note AGENTS.md says status SHOULD be wrapped in
             timeout 15 — this script's bare status calls are the (g) observation."

# MUST READ — the merged PRD (the spec the script encodes; the oracle for each verdict).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§6 T6 (GPU lifecycle — lazy load) = the 4-part a/b/c/d spec being audited; §4.2bis (Model
        lifecycle — lazy load on first arm + Idle unload + the recorder-host subprocess model) = WHY
        T6(a) boot is ~0 VRAM, WHY T6(c) stays resident, WHY T6(d) killpg releases ALL VRAM; §7 #9 =
        the acceptance clause this script is the sole real-CUDA proof for. When judging whether the
        script 'covers' a clause, the PRD wording is the source of truth."

# MUST READ — the sibling PRP (P1.M5.T3.S1, the e2e script audit) — establishes the inheritance.
- file: plan/006_862ee9d6ef41/P1M5T3S1/PRP.md
  why: "That PRP cites THIS script (test_idle_and_gpu.sh:156,357 VOICECTL_TIMEOUT=30 + voicectl() fn)
        as the timeout-discipline PRECEDENT that e2e_virtual_mic.sh SHOULD follow but doesn't (5/6
        unwrapped control calls there). This item CONFIRMS the inheritance is valid for CONTROL calls.
        Read it to (a) reuse the ctl.py:111-118 no-socket-timeout fact (don't re-derive it), and (b)
        align the (g) framing: e2e's gap is real control-call divergence; THIS script's gap is status-
        only (a strictly smaller, lower-risk observation)."
  critical: "Do NOT re-audit e2e_virtual_mic.sh here (S1 owns it). Cite its voicectl-timeout GAP for
             contrast only — 'the sibling e2e script does NOT wrap control calls; this script DOES;
             the shared blind spot is bare status calls, which both scripts have.'"

# External — the nvidia-smi compute-apps query semantics (validates the 'correct' verdict on check a).
- url: https://developer.nvidia.com/system-management-interface
  why: "`nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader` lists ONLY processes
        with an active CUDA COMPUTE context on the GPU, with their per-process used VRAM. A process
        that never created a CUDA context (e.g. the daemon process itself, which defers all CUDA to
        the recorder-host child) does NOT appear. This is WHY T6(a) boot = daemon tree ABSENT is the
        lazy-load guarantee, and WHY daemon-tree matching (not the daemon PID alone) is required (the
        child holds the context)."
- url: https://man7.org/linux/man-pages/man5/proc.5.html
  why: "/proc/<pid>/stat field 14 (utime) + field 15 (stime) in clock ticks; /proc/<pid>/task/<pid>/
        children lists direct children (recursive walk for the tree). Confirms the script's
        G-CPU-SAMPLING + daemon_tree_pids() /proc-based approach is the zero-dep correct path
        (pidstat/sysstat NOT installed). (Check a corroboration + the CPU tree-sum for T4.)"

# Cross-ref — the source-side audits (this is the TEST-SCRIPT-side audit; don't re-audit source).
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md   # lazy load + idle-unload + bounded teardown (source side)
- file: plan/006_862ee9d6ef41/architecture/gap_socket.md       # control-socket no-timeout (source side)
- file: plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md  # the 2-model kwargs the VRAM range reflects
  why: "These already audited the SOURCE. This item audits the TEST SCRIPT that DRIVES that source.
        Cite them (e.g. 'per gap_lifecycle.md, the idle-unload teardown is _bounded_shutdown(timeout=
        5.0) = killpg, bounded by design') rather than re-deriving. Don't duplicate their findings
        into gap_gpu_test.md beyond the one-line citations."
```

### Current Codebase tree (relevant slice — state at P1.M5.T3.S2)

```bash
tests/
├── test_idle_and_gpu.sh         (779 lines) ← IN SCOPE: the AUDIT SUBJECT (READ ONLY; do NOT run)
│                                   covers T6 (GPU lifecycle) + T4 (idle) + criterion 6/8 + T7 (lite)
├── e2e_virtual_mic.sh           (364 lines) ← comparison-only read (sibling P1.M5.T3.S1 audits it fully);
│                                   cite ITS voicectl-timeout GAP for contrast (it does NOT wrap control calls;
│                                   this script DOES — the inheritance S1 relies on is valid for control calls)
├── make_test_audio.sh           (generator) OUT — T1/E2E asset generator (not used by this script; it uses real mic)
└── (unit tests)                           OUT — P1.M5.T1.* (mocked) + P1.M5.T2.S1 (T1 offline)
voice_typing/
├── ctl.py                       # L111-118 makefile('r'), NO settimeout ← root of the (g) observation
├── config.py                    # L65 auto_stop=30.0; L67 auto_unload=1800.0 (Run 2 overrides to 5.0)
├── daemon.py                    # L733-739 resident teardown; L831-833 idle-unload thread; L1233-1239 idle-unload fire → _bounded_shutdown(timeout=5.0) killpg
└── launch_daemon.sh             # production-path launch (offline exports; $! = python PID)
plan/006_862ee9d6ef41/
├── P1M5T3S2/gap_gpu_test.md                    # ← OUTPUT (NEW; this item creates it)
├── P1M5T3S2/research/gpu_script_audit.md      # ← this PRP's research (already written; feed into the report)
├── P1M5T3S1/PRP.md                            # sibling e2e audit PRP (cite its voicectl-timeout GAP for contrast)
├── architecture/gap_{lifecycle,socket,recorder_kwargs}.md  # source-side audits (cite, don't re-derive)
└── prd_snapshot.md                            # §6 T6 + §4.2bis + §7 #9
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md   # NEW — the audit report (the SOLE deliverable)
# (NO source/test/script files edited. This is a REPORT item — audit only, no run, no edit.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT RUN test_idle_and_gpu.sh during this item. It loads CUDA models for ~5–8 min
#   (2 cold cuDNN/cuBLAS inits + a 120 s armed-idle window + idle-unload waits). AGENTS.md + the
#   work-item explicitly say "do NOT run unless explicitly required." The audit is STATIC: read the
#   script + the LIVE source it drives, record findings. If you accidentally started it, hit Ctrl-C
#   IMMEDIATELY (its EXIT trap stops the daemon + kills tmux + rm temp — and it does NOT swap the
#   audio source, so nothing to restore) and run the AGENTS.md Cleanup block.

# CRITICAL #2 — voicectl has NO socket read timeout (ctl.py:111-118). This is the root of the (g)
#   observation. The script's voicectl() wrapper fn (L357) bounds CONTROL calls (start/stop/toggle/
#   toggle-lite/quit — the actual hang vectors) with VOICECTL_TIMEOUT=30 (L156). But 13 status
#   callsites are BARE (deliberate: "status is lock-free, never hangs"). AGENTS.md Rule 1 contradicts
#   ("Always wrap: timeout 15 voicectl status … a dead daemon still wedges it"). Frame (g) as: PASS
#   for control calls + a LOW minor observation for status (the most-exposed callsite is
#   wait_daemon_ready L304-312, where the 180s budget is an iteration count + kill-0 is AFTER status).
#   Any voicectl command YOU run during the audit (e.g. to check a daemon ISN'T running) MUST be
#   wrapped: `timeout 15 .venv/bin/voicectl status`. AGENTS.md Rule 1 is non-negotiable.

# CRITICAL #3 — the script's 2-run design (default 1800s threshold for Run 1 + 5s override for Run 2)
#   is CORRECT, not a gap. T6(d) idle-unload on the default 1800s would take 30 min (impractical) AND
#   would corrupt T4's 120s armed window on Run 1 (the idle-unload clock runs only DISARMED, but 120s
#   << 1800s is the explicit reason T6(c) stays resident). Run 2's [asr] auto_unload_idle_seconds=5.0
#   override via a 2nd XDG_CONFIG_HOME isolates ONLY the threshold; every other [asr] field inherits
#   the SAME dataclass defaults (config.py:67) → identical ASR pipeline. Record this as correct design.

# CRITICAL #4 — the ISSUE-3 / auto_stop interaction is a T6(c) SUBTLETY, not a gap. auto_stop_idle_
#   seconds default = 30.0 (config.py:65) disarms the mic ~30s into T4's 120s silence window. So by
#   T6(c)'s assertion the mic may ALREADY be disarmed. The script handles this correctly (L531-542:
#   re-checks status, only issues `voicectl stop` if still armed, else notes auto-stop already
#   disarmed). T6(c)'s assertion (disarmed+resident) is valid EITHER way (auto_stop "disarms but does
#   NOT unload"). The comment cites commit 81d2ad8 making a redundant stop safe. Record as correct.

# CRITICAL #5 — T6(d) is the §7.9 CRUX + the riskiest clause. The daemon NEVER touches CUDA (the
#   recorder lives in the recorder-host CHILD subprocess); idle-unload = killpg the child group → ALL
#   VRAM released (incl. the realtime-model CUDA primary context that the OLD in-process recorder
#   couldn't release). daemon.py:1233-1239 (`_bounded_shutdown(timeout=5.0)`) confirms the teardown is
#   BOUNDED (no 90s hang). T6(d-gone) PASSING is the sole real-CUDA proof of Acceptance #9. A FAIL
#   there = a PRODUCTION bug (a grandchild orphaned), NOT a test bug — the script's FAIL block says so.

# CRITICAL #6 — distinguish the work-item's 8 checks (a–h) from the PRD §6 T6 4-part lifecycle. The
#   work-item's (a) = the nvidia-smi QUERY; (b)-(f) = the 5 ASSERTIONS (boot-absent, armed-present,
#   disarmed-resident, unload-gone, rearm-reload); (g) = timeout discipline; (h) = preflight. The PRD
#   §6 T6 4-part lifecycle = a/b/c/d which map to checks (b)/(c)/(d)/(e+f). Record BOTH framings (the
#   a–h matrix AND the PRD §6 T6 lifecycle map) so the acceptance cross-check (P1.M5.T5.S1) can credit
#   Acceptance #9 precisely (T6(d) lifecycle = all 4 states proven on real CUDA).

# CRITICAL #7 — this is a REPORT item. It does NOT fix the script or any source. The (g) finding gets
#   a "recommended fix (for a downstream remediation task)" note; you do NOT apply it. The ONLY edit
#   you make is to `plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md` (CREATE). Do NOT touch
#   tests/test_idle_and_gpu.sh, tests/e2e_virtual_mic.sh, any voice_typing/*.py, PRD.md, tasks.json,
#   prd_snapshot.md, .gitignore.

# CRITICAL #8 — scope boundary. Audit ONLY the T6 GPU-lifecycle slice (a–f) + (g) timeout + (h)
#   preflight. T4 (criterion 5: no-hallucination/no-crash/CPU<25%), criterion 6 (un-armed boot /
#   toggle / unit ExecStart+Restart grep), criterion 8 (no-network offline log grep), and T7 (lite
#   mode-switch roundtrip) are PRESENT in the script but owned by sibling items (P1.M5.T4.* /
#   P1.M5.T5.S1). NOTE their presence (so the report's scope section is accurate) but do NOT deep-
#   audit them. Read e2e_virtual_mic.sh ONLY for the voicectl-timeout comparison (cite its GAP for
#   contrast; don't re-audit it).
```

## Implementation Blueprint

### Data models and structure

N/A — no code models. The deliverable is one Markdown audit report. The "data" is the 8-check matrix +
the (g) finding + the correct-design notes + the safe-to-run verdict.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: READ the audit subject + cross-check against LIVE source (NO run, NO CUDA load).
  - READ tests/test_idle_and_gpu.sh end-to-end (779 lines). Note its G-* invariants (G-VRAM-
    ATTRIBUTION, G-VRAM-COMMAS, G-TIMEOUTS, G-CONFIG, G-PREFLIGHT, G-CLEANUP-IDEMPOTENT, G-NOSOURCE,
    G-CPU-SAMPLING, G-CPU-TREE) — these encode the 'correct' verdicts on checks a–f,h.
  - CROSS-CHECK the (g) finding against LIVE source (confirm, don't infer):
      ctl.py:111-118 (makefile('r'); NO settimeout → status has NO read timeout → a non-responsive
        control thread hangs it). The voicectl() fn (L357) wraps CONTROL calls (L469/470/476/538/592/
        602/630/640/667/687/700/727); the 13 bare status callsites (L306,379,461,536,549,605,615,
        631,635,643,653,658,720). The wait_daemon_ready loop L304-312 (180s = iteration count; kill-0
        AFTER status).
  - CROSS-CHECK the T6 lifecycle 'correct' verdicts against LIVE source: config.py:65 (auto_stop=30.0
    → the ISSUE-3/T6(c) interaction) + config.py:67 (auto_unload=1800.0 → Run 2 overrides to 5.0);
    daemon.py:733-739 (resident teardown _bounded_shutdown(timeout=5.0)) + 1233-1239 (idle-unload
    fire → _bounded_shutdown → killpg → ALL VRAM released while daemon LIVES).
  - CROSS-CHECK the nvidia-smi query (check a): --query-compute-apps=pid,used_memory --format=csv,
    noheader at L229/489/716; the 2-col choice (G-VRAM-COMMAS) + the daemon-TREE matching
    (daemon_tree_pids() recursive /proc walk, G-VRAM-ATTRIBUTION — the CUDA context lives on the
    CHILD PID, not the daemon PID).
  - DO NOT run the script, do NOT load CUDA, do NOT arm the mic. (If `timeout 15 .venv/bin/voicectl
    status` is needed to confirm a daemon ISN'T running, it's fine — but it's not required.)
  - GO to Task 2.

Task 2: BUILD the 8-check (a–h) matrix + the PRD §6 T6 4-part lifecycle map.
  - For EACH of the 8 work-item checks (a–h), record: check → script line(s) → LIVE-source evidence →
    verdict (PASS/MINOR-OBSERVATION). The research §1 matrix is the pre-filled answer — CONFIRM line
    numbers against the live file (they may have drifted) and copy into the report. The 8 verdicts:
      (a) queries nvidia-smi --query-compute-apps=pid,used_memory → PASS (L229/489/716; G-VRAM-COMMAS)
      (b) asserts PID absent at boot (before first arm) → PASS (L447, after wait_daemon_ready L442,
          before start L476; daemon.py lazy-load §4.2bis)
      (c) asserts PID present after arm → PASS (L481-484 wait_vram_present 15 + assert_vram_present;
          [1024,5120] MiB = ~1–5 GB)
      (d) asserts PID remains after stop → PASS (L546 assert_vram_present; stop doesn't unload;
          ISSUE-3/auto_stop handled L531-542)
      (e) asserts PID gone after idle-unload wait → PASS (Run 2 L707-709 wait_vram_absent 25 +
          assert_vram_absent; daemon.py:1233-1239 _bounded_shutdown(timeout=5.0) killpg)
      (f) asserts re-arm reloads → PASS (L727-730 start + wait_vram_present 15 + assert_vram_present)
      (g) VOICECTL_TIMEOUT=30 wrapping all voicectl → PASS (control calls via voicectl() fn L357;
          VOICECTL_TIMEOUT=30 L156) + MINOR-OBSERVATION (status deliberately unwrapped, 13 sites) — Task 3
      (h) preflight refuses if unit running → PASS (L379-382 both voicectl-answers AND systemd-active)
  - BUILD the PRD §6 T6 4-part lifecycle map (a/b/c/d ↔ checks b/c/d/e+f):
      T6(a) idle never armed → ~0 VRAM → check (b) L447 → COVERED
      T6(b) armed → ~1–5 GB → check (c) L481-484 → COVERED
      T6(c) disarmed not quit → REMAIN → check (d) L546 → COVERED
      T6(d) disarmed ≥ threshold → gone; later arm reloads → check (e)+(f) L707-709 + L727-730 → COVERED
  - RECORD the correct-design notes (research §4 — NOT gaps): test-time threshold compression (2-run
    1800s→5s), ISSUE-3/auto_stop interaction, daemon-tree matching (G-VRAM-ATTRIBUTION), polling-not-
    sleeping (G-TIMEOUTS), robust idempotent trap (G-CLEANUP-IDEMPOTENT), no-audio-swap (G-NOSOURCE).
  - GO to Task 3.

Task 3: WRITE the (g) MINOR-OBSERVATION section + the recommended fix (for a downstream remediation).
  - (g) PASS half: VOICECTL_TIMEOUT=30 (L156) + voicectl() { timeout … } wrapper fn (L357) wrap ALL
    CONTROL calls (start/stop/toggle/toggle-lite/quit — the actual hang vectors). This satisfies the
    spirit + primary intent of AGENTS.md Rule 1. Cite the 12 wrapped control-call linesites.
  - (g) OBSERVATION half [LOW]: 13 "$VOICECTL" status callsites are BARE (L306,379,461,536,549,605,
    615,631,635,643,653,658,720) by deliberate design ("status is lock-free + needs full output,
    never hangs"). AGENTS.md Rule 1 contradicts ("Always wrap: timeout 15 voicectl status … a dead
    daemon still wedges it"); ctl.py:111-118 confirms status has NO socket read timeout → a non-
    responsive control thread still blocks it (lock-free ≠ thread-can't-wedge).
  - most-exposed callsite: wait_daemon_ready L304-312 — the 180s budget is an iteration COUNT (360×
    0.5s), not a per-call timeout; the kill-0 liveness check is AFTER the status call, so a single
    hung status defeats the loop. Same shape in preflight L379.
  - practical risk: LOW (cold-start = connection-refused fast-fail, not hang; the wedge is a narrow
    regression; post-ready status captures are against a known-healthy daemon).
  - recommended fix (for a downstream REMEDIATION task — NOT applied here): add a voicectl_status()
    helper `timeout 15 "$VOICECTL" status "$@"` (shorter timeout than control calls — status is sub-
    second when healthy) + use it at the loop callsites (L306, L379) + the captures, OR at minimum
    wrap the wait_daemon_ready + preflight loop calls (the two with no fallback). The voicectl()
    wrapper already proves the pattern.
  - severity framing: MINOR OBSERVATION / LOW, NOT a GAP. The control calls (the demonstrated hang
    vectors) ARE wrapped → the AGENTS.md Rule 1 headline is honored. Record honestly so P1.M5.T5.S1
    credits the timeout discipline correctly (control ✅; status ✅-with-caveat).
  - GO to Task 4.

Task 4: WRITE the safe-to-run verdict + plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md (the SOLE deliverable).
  - VERDICT: YES (operator-present). Preflight refuses if a daemon runs (L379-382 — both voicectl-
    answers AND systemd-active). NO global audio mutation (G-NOSOURCE — no null-sink, no pactl set-
    default-source; listens to ambient silence on the real mic → NOTHING to restore on crash → simpler
    + safer trap than e2e). Cleanup trap is robust + idempotent (quit→SIGTERM→8s→SIGKILL, kill tmux
    vtidle, rm temp; fires on ANY exit). Distinct tmux session vtidle (≠ e2e's voicetest) so the two
    heavy parallel tests never collide.
  - CAVEAT: the (g) status gap means a wedged daemon's control thread could hang wait_daemon_ready /
    preflight (no per-call timeout). So safe-but-not-unattended-safe — an operator must be able to
    Ctrl-C it. Apply the §3 status-timeout fix before any unattended/CI run.
  - HEAVY: ~5–8 min (2 cold inits + 120s armed idle + idle-unload waits). Run explicitly; NOT in the
    fast pytest suite. AGENTS.md: bash-tool timeout 900; `systemctl --user stop voice-typing` first
    (preflight will refuse if it's running). PRECONDITION: QUIET room (ambient speech could spuriously
    fail T4's no-finals assertion — but that's T4's concern, out of this item's T6 scope).
  - CREATE plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md (NEW). Use the verbatim scaffold in "Task 4
    SOURCE". Fill the LIVE-confirmed line numbers + the (g) section + the verdict.
  - DO NOT edit the script, any source, PRD.md, tasks.json, prd_snapshot.md, .gitignore. REPORT item only.

Task 5: (NONE) — no source/test/script changes, no run. This is a static audit + documentation item.
```

#### Task 4 SOURCE — `gap_gpu_test.md` verbatim scaffold (pre-fill the static parts; confirm line numbers LIVE)

```markdown
# Audit — P1.M5.T3.S2: `tests/test_idle_and_gpu.sh` (PRD §6 T6 — GPU lifecycle, lazy load)

**Date:** <YYYY-MM-DD>
**Method:** STATIC audit (read-only). NOT run — the script loads CUDA models for ~5–8 min (2 cold
inits + 120 s armed idle + idle-unload waits) (AGENTS.md + work-item: "do NOT run unless explicitly
required"). Findings cross-checked against the LIVE source the script drives.
**Verdict:** 7/8 checks PASS; **1 minor observation** — (g) `status` calls deliberately unwrapped
[LOW] (control calls ARE wrapped via the `voicectl()` fn). **No hard GAP** in the T6 GPU-lifecycle
logic. **Safe to run: YES (operator-present)** (preflight + robust trap + NO audio-source swap; caveat
= (g) status gap → not unattended-safe until fixed). The script is the **sole real-CUDA proof for
Acceptance #9** (T6(d) idle-unload reclaims ~0 VRAM + a later arm reloads).

## 1. The 8-check matrix (work-item contract a–h)

| # | check | script line(s) | LIVE-source evidence | verdict |
|---|---|---|---|---|
| (a) | queries `nvidia-smi --query-compute-apps=pid,used_memory` | `vram_tree_state()` L229; diagnostics L489, L716 | G-VRAM-COMMAS: 2-col query (process_name can contain commas → breaks CSV); `--format=csv,noheader`. Matches PRD §6 T6 wording. nvidia-smi compute-apps lists ONLY procs with an active CUDA context. | ✅ PASS |
| (b) | asserts daemon PID **absent** at boot (before first arm) | L447 `assert_vram_absent "(a) boot"`; after `wait_daemon_ready` L442, before `voicectl start` L476 | daemon.py lazy-load (§4.2bis): recorder-host child spawned on FIRST arm → boot = no child = no CUDA = tree ABSENT. `assert_vram_absent` checks `total==0`. | ✅ PASS |
| (c) | asserts PID **present** after arm | L476 start → L481 `wait_vram_present 15` → L483 `assert_vram_present "(b) armed"` | total ∈ [VRAM_MIN=1024, VRAM_MAX=5120] MiB = ~1–5 GB (PRD §6 T6 b). Poll ceiling 15s (cold load ~1–3s). | ✅ PASS |
| (d) | asserts PID **remains** after stop | L538 stop (conditional, ISSUE-3) → L546 `assert_vram_present "(c) disarmed: still resident"` | stop disarms but does NOT unload (only idle-unload does); Run 1 threshold 1800s ≫ 120s → no unload fires. auto_stop=30.0 may pre-disarm (handled L531-542). | ✅ PASS |
| (e) | asserts PID **gone** after idle-unload wait | RUN 2 (5s override): L700 stop → L707 `wait_vram_absent 25` → L709 `assert_vram_absent "(d) idle-unload"` | daemon.py:1233-1239 idle-unload watchdog → `_bounded_shutdown(timeout=5.0)` (L1239/L739) = killpg child group → ALL VRAM released while daemon LIVES. config.py:67 default 1800.0; Run 2 overrides to 5.0. | ✅ PASS — §7.9 crux |
| (f) | asserts **re-arm reloads** | L727 start (re-arm) → L728 `wait_vram_present 15` → L730 `assert_vram_present "(d) re-arm reloads"` | daemon.py `_load_host` rebuilds the recorder-host child on a fresh arm after unload (~1–3s single-flight). | ✅ PASS |
| (g) | `VOICECTL_TIMEOUT=30` wrapping **all** voicectl calls | L156 `VOICECTL_TIMEOUT=30`; L357 `voicectl() { timeout … }` wraps ALL control calls (start/stop/toggle/toggle-lite/quit — L469/470/476/538/592/602/630/640/667/687/700/727) | ctl.py:111-118: `makefile('r')` incompatible w/ `settimeout` → NO socket read timeout; control calls can hang FOREVER → the wrapper bounds them. **BUT 13 status callsites BARE** (L306,379,461,536,549,605,615,631,635,643,653,658,720) by deliberate design. | ✅ PASS (control) / ⚠️ MINOR (status) — §3 |
| (h) | preflight refuses if unit already running | L379-380 (`voicectl status` answers → die) + L382 (`systemctl --user is-active voice-typing` → die) | G-PREFLIGHT: real control socket pinned to `$XDG_RUNTIME_DIR`; 2nd daemon can't bind. Checks BOTH socket AND systemd unit. | ✅ PASS |

## 2. PRD §6 T6 4-part lifecycle map (the oracle)

| PRD §6 T6 clause | script block | work-item check | verdict |
|---|---|---|---|
| (a) idle never armed → PID NOT listed (~0 VRAM) | T6(a) L447 | (b) | ✅ COVERED |
| (b) armed → PID appears ~1–5 GB | T6(b) L481-484 | (c) | ✅ COVERED |
| (c) disarmed not quit → PID+memory REMAIN | T6(c) L546 | (d) | ✅ COVERED |
| (d) disarmed ≥ threshold → PID gone; later arm reloads | T6(d-gone) L707-709 + T6(d-reload) L728-730 | (e)+(f) | ✅ COVERED |

**Acceptance impact:** this script is the SOLE real-CUDA proof for Acceptance **#9** (idle-unload
reclaims ~0 VRAM via nvidia-smi + a later arm reloads). P1.M5.T5.S1 should credit it for #9 (T6(d)
lifecycle, all 4 states proven on real CUDA) + criterion 5 (T4) + criterion 8 (offline grep) +
criterion 6 (un-armed boot/unit grep) as side coverage.

## 3. MINOR OBSERVATION (g) — `status` calls deliberately unwrapped [LOW]

**PASS half (control calls):** `VOICECTL_TIMEOUT=30` (L156) + the `voicectl()` wrapper fn (L357)
`voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }` wrap **ALL control calls** (start/stop/
toggle/toggle-lite/quit — L469/470/476/538/592/602/630/640/667/687/700/727). These are the actual hang
vectors (`voicectl start` blocks on the cold model load; stop/toggle touch the control lock). This
satisfies the spirit + primary intent of AGENTS.md Rule 1. This script is the timeout-discipline
**PRECEDENT** the sibling `e2e_virtual_mic.sh` (P1.M5.T3.S1) cites — correctly, for control calls.

**OBSERVATION half (status, [LOW]):** 13 `"$VOICECTL" status` callsites are invoked **bare** (L306,
379, 461, 536, 549, 605, 615, 631, 635, 643, 653, 658, 720). The script documents the rationale
(L352-356): "`status` is lock-free + needs the full output, so callers invoke it directly (it never
hangs)."

**Why mostly-correct:** `status` is lock-free (the daemon's status handler doesn't acquire `_lock`),
so it can't wedge on the operation lock. Bare status against a just-launched daemon (wait_daemon_ready)
or a known-healthy daemon (post-ready captures) sees connection-refused (fast fail) when the socket
isn't bound — NOT a hang.

**Why technically incomplete (AGENTS.md contradicts):** AGENTS.md Rule 1 — *"Always wrap: `timeout 15
.venv/bin/voicectl status` … Lock-free and fast when healthy, but still has no socket timeout — a dead
daemon still wedges it."* ctl.py:111-118 confirms status uses `makefile('r')` with **NO read timeout**
→ a daemon whose **control thread** is non-responsive (not just the lock) still blocks status.
"Lock-free" ≠ "the thread can't be wedged on something else."

**Most-exposed callsite — `wait_daemon_ready` (L304-312):**
```bash
for _ in $(seq 1 360); do            # 360 x 0.5s = 180s budget
  if "$VOICECTL" status >/dev/null 2>&1; then return 0; fi   # ← bare; if THIS hangs, loop never advances
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited ..."   # ← liveness check is AFTER status
  sleep 0.5
done
```
The 180s "budget" is a **count of iterations**, not a per-call timeout. A single hung `status` call
defeats it (the `kill -0` liveness check comes AFTER, so it never runs). Same shape in preflight (L379).

**Practical risk: LOW.** At `wait_daemon_ready` the daemon was just launched: socket-not-bound =
connection-refused (fast fail, NOT a hang); socket-bound = responsive. A wedged control thread mid-
cold-start is a narrow regression. Post-ready status captures are against a known-healthy daemon.
Diagnostic status calls inside FAIL blocks are non-critical (already failing).

**Recommended fix (for a downstream REMEDIATION task — NOT applied here; REPORT item):** add a
`voicectl_status()` helper `timeout 15 "$VOICECTL" status "$@"` (shorter timeout than control calls —
status is sub-second when healthy) and use it at the loop callsites (L306, L379) + the captures, OR at
minimum wrap the `wait_daemon_ready` + preflight loop calls (the two with no fallback). The existing
`voicectl()` wrapper already proves the pattern.

**Severity:** MINOR OBSERVATION / LOW — NOT a GAP. The control calls (the demonstrated hang vectors)
ARE wrapped → the AGENTS.md Rule 1 headline is honored. Contrast with the sibling e2e_virtual_mic.sh
(P1.M5.T3.S1): THAT script does NOT wrap its control calls (5/6 unwrapped — a real HIGH gap); THIS
script DOES. The shared blind spot between both is bare status calls — a strictly smaller, lower-risk
observation than e2e's control-call gap.

## 4. Correct-design notes (NOT gaps — recorded for completeness)

1. **Test-time threshold compression (1800s → 5s 2-run design):** T6(d) idle-unload on the default
   1800s threshold would take 30 min — impractical AND would corrupt T4's 120s armed window on Run 1.
   The script uses 2 runs: Run 1 = default 1800s (so T4's 120s + T6(c)'s disarmed-resident assertion
   are unaffected — 120s ≪ 1800s); Run 2 = `[asr] auto_unload_idle_seconds=5.0` override via a 2nd
   `XDG_CONFIG_HOME` (`$WORK/config_short`) so idle-unload fires in bounded time. Correct isolation:
   every other [asr] field inherits the SAME dataclass defaults (config.py:67) → identical ASR
   pipeline except the threshold. (G-CONFIG.) ✅
2. **ISSUE-3 / auto_stop interaction (T6(c) subtlety):** `auto_stop_idle_seconds` default = 30.0
   (config.py:65) disarms the mic ~30s into T4's 120s silence window → T6(c) may run against an
   already-disarmed daemon. The script handles this correctly (L531-542: re-checks status, only issues
   `voicectl stop` if still armed, else notes auto-stop already disarmed). T6(c)'s assertion (disarmed
   +resident) is valid EITHER way (auto_stop "disarms but does NOT unload"). The comment cites commit
   81d2ad8 making a redundant stop safe. ✅
3. **Daemon-tree matching, not arbitrary nvidia-smi row (G-VRAM-ATTRIBUTION):** `daemon_tree_pids()`
   walks `/proc/<pid>/task/<pid>/children` recursively + matches against nvidia-smi PIDs. The GPU hosts
   unrelated compute apps (Chrome, a parallel test daemon) → strict tree filtering is essential. PID
   presence/absence is the HARD signal; used_memory (can lag/underreport) is secondary corroboration.
   The subprocess recorder-host model means the CUDA context lives on the CHILD PID — so tree-matching
   (not just the daemon PID) is what catches it. ✅ essential
4. **Polling, never fixed sleeps (G-TIMEOUTS):** `wait_vram_absent`/`wait_vram_present` POLL every 0.5s
   with a deadline ceiling (~25s absent / ~15s present). The contract's literal "7s" is explicitly
   noted as under-budgeted (1s tick + threshold + ≤7s `_bounded_shutdown` + driver-accounting lag);
   the ceilings absorb the variance. A fixed `sleep 7` would flake. ✅
5. **Robust idempotent cleanup trap (G-CLEANUP-IDEMPOTENT):** `trap cleanup EXIT` → `stop_daemon_run`
   (quit→SIGTERM→8s poll→SIGKILL, idempotent) → kill tmux `vtidle` → rm `$WORK`. Every step `|| true`.
   Distinct tmux session `vtidle` (≠ e2e's `voicetest`) so the two heavy parallel tests never collide.
   ✅
6. **No global audio mutation (G-NOSOURCE):** this test does NOT swap the default audio source (no
   null-sink, no `pactl set-default-source`) — listens to ambient silence on the REAL default mic. So
   there's NOTHING to restore on a crash → simpler + safer trap than e2e (no source-restore step). ✅
7. **No-network / offline proof (criterion 8, NON-CIRCULAR — out of scope, noted):** the script does
   NOT pre-set `HF_HUB_OFFLINE` (that masked a past bug); relies on `launch_daemon.sh`'s exports +
   greps the daemon log for ZERO `HTTP Request: GET https://huggingface.co` lines (L455-458). (Audited
   by P1.M5.T5.S1.) ✅

## 5. Scope — what is IN vs OUT of this audit

- **IN scope (this item):** T6 GPU lifecycle (checks a–f) + (g) timeout discipline + (h) preflight —
  the work-item's 8 checks.
- **OUT of scope (present in the script, audited by sibling items — noted, NOT deep-audited):**
  - T4 idle stability (criterion 5: no hallucination / no crash / CPU<25%) → **P1.M5.T4.\***
  - criterion 6 (un-armed boot / toggle / unit ExecStart+Restart grep) → **P1.M5.T5.S1**
  - criterion 8 (no-network / offline log grep) → **P1.M5.T5.S1**
  - T7 lite mode-switch roundtrip (acceptance #10: toggle-lite reload + VRAM≈half + toggle back) →
    note it drives the REAL daemon mode-switch; full audit is P1.M5.T5 / the lite-mode item.

## 6. Safe-to-run verdict

**YES (operator-present)**, with the (g) status caveat.

- ✅ **Preflight refuses** if a daemon is already running (`voicectl status` answers OR systemd-active,
  L379-382) — won't collide with the user's real daemon. AGENTS.md: "`systemctl --user stop
  voice-typing` first."
- ✅ **No global audio mutation (G-NOSOURCE):** this test does NOT swap the default audio source. It
  listens to ambient silence on the REAL default mic. So there is NOTHING to restore on a crash → the
  trap is simpler + safer than e2e's (no source-restore step). This is the **lowest-stakes heavy test
  in the repo.**
- ✅ **Cleanup trap is robust + idempotent:** `trap cleanup EXIT` fires on ANY exit (pass, fail,
  Ctrl-C). It stops the daemon bounded (quit→SIGTERM→8s→SIGKILL), kills the `vtidle` tmux session,
  removes temp files. Every step `|| true`; `stop_daemon_run` is idempotent (safe when DAEMON_PID is
  empty/dead).
- ⚠️ **(g) caveat:** a wedged daemon's control thread could hang a bare `status` call in
  `wait_daemon_ready` (L306) or preflight (L379) — no per-call timeout; the loop's `kill -0` liveness
  check is AFTER the status call, so the 180s budget is a count not a bound. **Low practical risk**
  (cold-start = connection-refused fast-fail; the wedge is a narrow regression) but an operator must
  be able to Ctrl-C it → **safe-but-not-unattended-safe** until the §3 status-timeout fix is applied.
- ⚠️ **Heavy:** ~5–8 min (2 cold cuDNN/cuBLAS inits + 120s armed idle + idle-unload waits). Run
  explicitly; NOT collected by the fast pytest suite. AGENTS.md: bash-tool `timeout` **900** (15 min);
  `systemctl --user stop voice-typing` first (preflight will refuse if it's running).
- 📌 **Precondition:** QUIET room (ambient speech could produce a real final + spuriously fail the
  "no finals" T4 assertion — T4's concern, out of this item's T6 scope).

**Do NOT run during this audit item** (AGENTS.md: ~5–8 min CUDA load). If a later task is explicitly
authorized to run it, apply the §3 status-timeout fix first for unattended/CI safety.

## 7. Cross-references

- Source-side audits (cite, don't re-derive): `architecture/gap_lifecycle.md` (lazy load + idle-unload
  + `_bounded_shutdown(timeout=5.0)` killpg), `architecture/gap_socket.md` (no socket timeout),
  `architecture/gap_recorder_kwargs.md` (the 2-model kwargs the VRAM range reflects).
- Sibling e2e script audit: `P1M5T3S1/PRP.md` + `P1M5T3S1/gap_e2e.md` (cites THIS script's
  VOICECTL_TIMEOUT=30 + voicectl() fn as the timeout precedent e2e SHOULD follow; e2e's GAP is the
  UNWRAPPED control calls — THIS script's only blind spot is bare status, strictly smaller).
- Acceptance evidence consumer: `P1.M5.T5.S1` (#9 T6(d) lifecycle = sole real-CUDA proof; (g) status
  caveat refines the timeout-credit picture).
```

### Implementation Patterns & Key Details

```python
# The verdict logic (Task 2): for each of the 8 checks (a–h), does the script DO it correctly?
#   a–f,h → YES → PASS (record the script line + LIVE-source evidence).
#   g → PASS for control calls (voicectl() fn) + MINOR OBSERVATION for status (13 bare sites) — Task 3.
# Don't invent gaps: the 7 passes ARE correct (verified against LIVE source). The (g) observation IS
# real (verified against ctl.py:111-118 + AGENTS.md Rule 1) but LOW (control calls ARE wrapped).

# The 2-run design (Task 2 correct-design notes): Run 1 = default 1800s threshold (so T4's 120s armed
#   window + T6(c)'s disarmed-resident assertion are unaffected); Run 2 = [asr]
#   auto_unload_idle_seconds=5.0 override (so T6(d) fires in bounded time). The threshold compression
#   is CORRECT — the default 1800s would take 30 min AND would corrupt T4's window on Run 1. Don't
#   flag it as a gap; it's a clever, correct test-time technique.

# The ISSUE-3 / auto_stop interaction (Task 2 correct-design notes): auto_stop_idle_seconds default =
#   30.0 (config.py:65) disarms the mic ~30s into T4's 120s window → T6(c) may run against an
#   already-disarmed daemon. The script handles this (L531-542: re-check status, stop only if armed).
#   T6(c)'s assertion (disarmed+resident) is valid EITHER way. Not a gap — a subtlety.

# The (g) finding (Task 3): the root cause is ONE fact — ctl.py:111-118 has no socket read timeout.
#   Everything else follows: control calls can hang forever (the voicectl() fn bounds them ✅); status
#   can hang on a non-responsive control thread (13 bare sites, the OBSERVATION ⚠️). The most-exposed
#   callsite is wait_daemon_ready (180s = iteration count, kill-0 AFTER status). Cite ctl.py:111-118 +
#   AGENTS.md Rule 1 + the voicectl() fn as the twin pillars. Frame as MINOR/LOW, NOT a GAP.

# What "safe to run" means (Task 4): the script does NOT swap the default audio source (G-NOSOURCE) →
#   NOTHING to restore on crash → simpler + safer trap than e2e → the LOWEST-STAKES heavy test in the
#   repo. The preflight + robust idempotent trap make it safe for an operator-present run. The (g)
#   status gap means it's NOT unattended-safe (a wedged control thread could hang wait_daemon_ready).
#   The fix (§3) makes it unattended-safe. Do NOT overstate: the script is NOT dangerous to run (no
#   audio mutation; trap cleans up); it just has the shared bare-status blind spot.

# Scope discipline: read e2e_virtual_mic.sh ONLY for the voicectl-timeout comparison (cite its GAP for
#   contrast — e2e's unwrapped control calls are a real HIGH gap; THIS script wraps them, so its only
#   blind spot is bare status). Do NOT audit e2e's T3 assertions (S1 owns it). Do NOT deep-audit T4 /
#   criterion 6 / criterion 8 / T7 in THIS script (sibling items own them) — note their presence.
```

### Integration Points

```yaml
CONSUMES (read-only):
  - tests/test_idle_and_gpu.sh                                   # the audit SUBJECT (read; do NOT run)
  - tests/e2e_virtual_mic.sh                                     # comparison-only (cite its voicectl-timeout GAP for contrast)
  - voice_typing/{ctl,config,daemon}.py                          # LIVE source the script drives (cross-check the verdicts)
  - voice_typing/launch_daemon.sh                                # production-path launch (offline exports; $! = python PID)
  - plan/006_862ee9d6ef41/prd_snapshot.md                        # §6 T6 (the spec) + §4.2bis (lazy load/idle-unload/subprocess host) + §7 #9
  - plan/006_862ee9d6ef41/architecture/gap_{lifecycle,socket,recorder_kwargs}.md  # source-side audits (cite)
  - plan/006_862ee9d6ef41/P1M5T3S1/PRP.md                        # sibling e2e PRP (cite its voicectl-timeout GAP; reuse ctl.py:111-118 fact)
  - plan/006_862ee9d6ef41/P1M5T3S2/research/gpu_script_audit.md  # THIS PRP's research (feed into the report)

PRODUCES (the SOLE output):
  - plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md               # NEW audit report (8-check matrix + (g) finding + correct-design notes + safe-to-run verdict)

FEEDS (downstream consumers):
  - P1.M5.T5.S1 (acceptance cross-check)                         # #9 (T6(d) lifecycle = sole real-CUDA proof); (g) status caveat refines timeout credit
  - a downstream REMEDIATION task (if opened)                    # the (g) status-timeout fix (voicectl_status() helper; wrap wait_daemon_ready + preflight)

PARALLEL-SAFE:
  - P1.M5.T3.S1 (e2e script audit, in flight) = ZERO file overlap (different subject; report goes to P1M5T3S2/).
  - Shared surface = the SOURCE modules (ctl.py/config.py/daemon.py) — both items READ them (read-only); no edit conflict possible (REPORT items).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown audit report — validate structure + content, not code.
test -f plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "EXISTS"
grep -q 'P1.M5.T3.S2'             plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "titled"
grep -qi '8-check\|8 checks\|a–h\|a-h' plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "8-check matrix present"
grep -qi 'T6.*lifecycle\|4-part'  plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "T6 lifecycle map present"
grep -qi 'status.*unwrapp\|bare.*status\|MINOR.*OBSERVATION\|LOW' plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "(g) status observation flagged"
grep -qi 'safe.to.run\|YES (operator' plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "safe-to-run verdict present"
grep -qi 'G-NOSOURCE\|no.*audio.*source\|nothing to restore' plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md && echo "no-audio-swap noted"
# Expected: EXISTS; title + 8-check matrix + T6 lifecycle map + (g) observation + safe-to-run verdict + no-audio-swap present.
```

### Level 2: LIVE-source re-confirmation (NO run, NO CUDA load — read-only greps)

```bash
# Re-confirm the verdicts' root facts against the LIVE source (the agent should cite these line ranges).
cd /home/dustin/projects/voice-typing

# check (a) — the nvidia-smi query fields.
grep -n "query-compute-apps" tests/test_idle_and_gpu.sh
#   expect: L229 + L489 + L716: --query-compute-apps=pid,used_memory --format=csv,noheader

# check (b)-(f) — the T6 assertion labels + helpers.
grep -n 'assert_vram_absent\|assert_vram_present\|wait_vram_absent\|wait_vram_present\|"(a) boot\|"(b) armed\|"(c) disarmed\|"(d) ' tests/test_idle_and_gpu.sh

# (g) PASS half — the control-call wrapper.
grep -n 'VOICECTL_TIMEOUT=\|^voicectl() {' tests/test_idle_and_gpu.sh
#   expect: L156 VOICECTL_TIMEOUT=30 ; L357 voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }

# (g) OBSERVATION half — the bare status callsites (13 of them).
grep -cn '"\$VOICECTL" status' tests/test_idle_and_gpu.sh
#   expect: 13

# (g) root — voicectl has NO socket read timeout.
grep -n "makefile" voice_typing/ctl.py | head -3
#   expect: L111-118 "Uses makefile(\"r\") (NOT settimeout — makefile raises if the socket has a timeout …)"

# check (e) crux — the bounded idle-unload teardown (killpg after join(5s)).
grep -n '_bounded_shutdown(timeout=5.0\|idle-unload:.*unloading\|killpg' voice_typing/daemon.py | head

# check (d)/(e) config — the thresholds.
grep -n 'auto_unload_idle_seconds: float\|auto_stop_idle_seconds: float' voice_typing/config.py
#   expect: L65 auto_stop=30.0 ; L67 auto_unload=1800.0

# check (h) — preflight refuse.
grep -n 'already running\|is-active voice-typing' tests/test_idle_and_gpu.sh
#   expect: L380 (voicectl answers) + L382 (systemctl is-active)
```

### Level 3: Integration Testing (System Validation)

```bash
# N/A — this is a REPORT item (no code, no run). The "integration" is the report's self-consistency:
# every script line number cited in gap_gpu_test.md must resolve in the LIVE file (re-confirm with the
# Level 2 greps). The script is NOT run during this item (5–8 min CUDA load; AGENTS.md + work-item).
```

### Level 4: Creative & Domain-Specific Validation

```bash
# N/A — no code to run. The one domain-specific check: confirm the T6(d) "daemon tree ABSENT while
# daemon LIVES" claim is physically possible — i.e. the daemon process itself NEVER creates a CUDA
# context (the recorder lives in the child). Cite daemon.py:1233-1239 (_bounded_shutdown killpg the
# child group) + §4.2bis (the recorder-host subprocess model). A FAIL of T6(d) in a later authorized
# run would mean a grandchild orphaned — a PRODUCTION bug, not a test bug (the script's FAIL block
# says so). Do NOT run nvidia-smi during this item (it would show YOUR machine's current GPU state,
# not the test's; and the daemon isn't running under this audit).
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1 structural greps pass (EXISTS; title; 8-check matrix; T6 lifecycle map; (g) observation; safe-to-run verdict; no-audio-swap).
- [ ] Level 2 LIVE-source re-confirmation: every cited script line resolves; ctl.py:111-118 makefile; daemon.py `_bounded_shutdown(timeout=5.0)`; config.py L65/67 defaults; 13 bare status sites.
- [ ] Levels 3–4 N/A (REPORT item; script NOT run).

### Feature Validation
- [ ] All success criteria from "What" met (8-check matrix; T6 lifecycle map; (g) finding; correct-design notes; safe-to-run verdict).
- [ ] Manual cross-check: the 7 PASS verdicts each have a script line + LIVE-source citation; the (g) MINOR OBSERVATION has the PASS half + OBSERVATION half + most-exposed callsite + fix.
- [ ] Scope respected: ONLY T6 (a–f) + (g) + (h) audited; T4/criterion-6/criterion-8/T7 noted as out-of-scope; NO source/test/script edited.

### Code Quality Validation
- [ ] Report follows the sibling `gap_e2e.md` structure (matrix → lifecycle map → finding → correct-design notes → scope → safe-to-run → cross-refs).
- [ ] Citations are specific (exact line numbers, not hand-waving); LIVE-source facts re-confirmed, not inferred.
- [ ] Verdict is honest: 7/8 PASS + 1 LOW observation (not overstated as a GAP; not understated as fully-safe).

### Documentation & Deployment
- [ ] `gap_gpu_test.md` is self-contained (a reader can verify every claim against the LIVE script + source).
- [ ] The safe-to-run verdict gives an operator a clear YES/NO + the one caveat + the fix.

---

## Anti-Patterns to Avoid

- ❌ Don't RUN the script during this item (5–8 min CUDA load; AGENTS.md + work-item forbid it). STATIC read-only audit.
- ❌ Don't invent gaps. The 7 PASS verdicts ARE correct (verified against LIVE source). The (g) status-unwrap is the ONE real finding — frame it honestly as LOW (control calls ARE wrapped), not as a HIGH GAP.
- ❌ Don't flag the 2-run threshold compression (1800s→5s) or the ISSUE-3/auto_stop handling as gaps — they're CORRECT design. Record them as correct-design notes.
- ❌ Don't deep-audit T4 / criterion 6 / criterion 8 / T7 — sibling items own them. Note their presence; don't duplicate their audits.
- ❌ Don't re-derive the ctl.py:111-118 no-socket-timeout fact — reuse it from the sibling S1 PRP / cite it.
- ❌ Don't conflate THIS script's (g) status-only observation with e2e's (g) control-call GAP — they're different (e2e's is HIGH; this is LOW). Contrast them, don't equate.
- ❌ Don't edit the script, any source, PRD.md, tasks.json, prd_snapshot.md, .gitignore. REPORT item — the ONLY output is `gap_gpu_test.md`.

---

**Confidence Score: 9/10** — the findings are pre-verified against LIVE source (script line numbers +
ctl.py/config.py/daemon.py citations locked down); the deliverable is a single self-contained report
with a verbatim scaffold; the only residual risk is minor line-number drift if the script is edited
between this PRP and implementation (the Level 2 greps catch that). One-pass implementation success is
highly likely: read the script, re-confirm the cited lines, fill the scaffold.