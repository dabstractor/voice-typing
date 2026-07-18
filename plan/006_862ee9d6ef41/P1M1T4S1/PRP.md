# PRP — P1.M1.T4.S1: Audit cuda_check probe & CPU fallback resolution against PRD §4.4

## Goal

**Feature Goal**: Produce an authoritative **gap report** (`plan/006_862ee9d6ef41/architecture/gap_cuda_check.md`)
cross-checking `voice_typing/cuda_check.py` (and its daemon consumption) against **PRD §4.4** on the
contract points — (a) the CUDA probe via `ctranslate2.get_cuda_device_count()`, (b) the CPU-fallback
config (`device=cpu`, `compute_type=int8`, `realtime_model_type=tiny.en`, `model=small.en`), (c) the
probe returning a dict with device+compute_type+downgraded model names, (d) lite-mode CPU substitute =
`tiny.en`, (e) daemon `_resolve_device_config`/`cfg_to_kwargs` consume cuda_check output, (f) the
daemon logs the resolved device at startup ("log clearly and fall back"), (g) the daemon surfaces the
device in status ("say so in status") — and verify `ctranslate2.get_cuda_device_count() >= 1` on this
machine (RTX 3080 Ti), and run the `cfg_to_kwargs` path tests (the contract's run target). This is a
**verification/audit** subtask: the deliverable is the report; code changes happen ONLY if a real
defect is found (none is expected — the audit finds `cuda_check.py` + daemon consumption fully
PRD §4.4-compliant).

**Deliverable**: One report at `plan/006_862ee9d6ef41/architecture/gap_cuda_check.md` (mirroring the
`gap_config.md` / `gap_textproc.md` / `gap_typing.md` convention) containing: (a) a per-point
compliance table (PRD §4.4 expected vs code actual, with file:line); (b) the `ctranslate2` live-probe
result + the `cuda_check` CLI verdict; (c) the unit-test pass/fail count; (d) the architectural
nuance (VT-001: the daemon process never probes CUDA — the recorder-host child owns the resolution)
+ the documented cuDNN limitation; (e) a conclusion. **This PRP's author has already performed the
audit** (findings embedded below + in the research note) — the implementing agent re-verifies and
transcribes, then writes the report.

**Success Definition**:
- (a) `plan/006_862ee9d6ef41/architecture/gap_cuda_check.md` exists with the sections above.
- (b) The recorded findings match the live re-verification: all contract points (a)-(g) are
  **compliant** (each with cuda_check.py / daemon.py file:line).
- (c) `timeout 60 .venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"`
  → `1` (≥1, contract satisfied); the `cuda_check` CLI prints `VERDICT=cuda-ok`.
- (d) `.venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or cpu or lite
  or fixed)"` → all pass (record the count; verified baseline: **7 passed**).
- (e) **No source files are modified** (because no defect exists — `cuda_check.py` + daemon
  consumption are fully PRD §4.4-compliant per audit). If — and only if — the re-verification surfaces
  a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (f) The report records the three non-blocking observations (the documented cuDNN limitation; the
  torch-is-diagnostic-not-gate note; the CLI `_main()` being operator-facing not unit-tested) so they
  aren't mistaken for defects.

> **VERIFIED VERDICT (this PRP's research): `cuda_check.py` + daemon consumption are PRD §4.4-COMPLIANT — no fix needed.** All 7 contract points pass (file:line below); `ctranslate2.get_cuda_device_count() == 1`, `VERDICT=cuda-ok`; `tests/test_daemon.py` cfg_to_kwargs path suite = **7 passed in 0.02s**.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that the CUDA probe + CPU
fallback faithfully implement PRD §4.4 before relying on the daemon's device resolution. Also the
downstream P1.M2.T4 (recorder kwargs audit), P1.M2.T2 (recorder-host lifecycle — the child that owns
the resolution), and P1.M4.T2 (launch_daemon.sh cuDNN discovery) which depend on cuda_check's contract.
**Use Case**: A future change to `cuda_check.py` (e.g. altering CPU_FALLBACK values, swapping the
probe, or promoting torch to a gate). The gap report + the path tests are the reference that proves
the change keeps (or breaks) PRD §4.4 compliance.
**Pain Points Addressed**: Closes the "does the probe actually (a) use ctranslate2's device count,
(b) fall back to the exact PRD §4.4 CPU config, (c) hand a complete dict to the daemon, (d) keep
lite CPU at tiny.en, (e) get consumed at startup, (f) get logged, and (g) get surfaced in status?"
question with recorded, re-runnable evidence — not an assumption. (The §4.4 "degraded but functional"
guarantee + the "say so in status" requirement are certified by (b)+(g).)

## Why

- **PRD §4.4 is the spec.** It pins the CPU fallback exactly (`device="cpu", compute_type="int8"`,
  `realtime_model_type="tiny.en"`, `model="small.en"`) and requires the daemon "MUST log clearly and
  fall back ... and say so in `status`." This audit confirms the implementation matches the spec
  before the heavier recorder-kwargs (P1.M2.T4) + recorder-host (P1.M2.T2) audits rely on it.
- **Catch silent drift the unit tests might not pin to the PRD.** The `cfg_to_kwargs` tests pin
  BEHAVIOR (resolved dict → kwargs) but monkeypatch `resolve_device_and_models` — so they do NOT
  exercise the real probe and do NOT explicitly map each assertion to "PRD §4.4 point (a)-(g)." A
  future refactor could pass the tests yet drift from the PRD's exact CPU_FALLBACK values. This audit
  is the check that closes that mapping gap, recorded durably in `gap_cuda_check.md`.
- **Record the VT-001 architectural invariant so it isn't "fixed" into a regression.** The daemon
  PROCESS never probes CUDA (the recorder-host child does). If a future change makes the daemon
  process call `cuda_check` directly (e.g. for status), it re-introduces the VT-001 CUDA-context-in-
  the-daemon-process regression. Recording this prevents it.
- **Lowest-risk outcome.** The live verification (this PRP's author) finds cuda_check fully
  §4.4-compliant → no code changes → zero regression risk. The deliverable is the recorded evidence.
- **Scope discipline.** T4.S1 owns ONLY `cuda_check.py` audit + the daemon consumption points +
  `gap_cuda_check.md`. It does NOT re-audit config (P1.M1.T1), textproc (P1.M1.T2), typing_backends
  (P1.M1.T3), launch_daemon.sh (P1.M4.T2), or the recorder-host lifecycle (P1.M2.T2), and does NOT
  modify source unless a real defect is found.

## What

Re-verify `cuda_check.py` + its daemon consumption against PRD §4.4's contract points, verify
`ctranslate2.get_cuda_device_count() >= 1`, run the `cfg_to_kwargs` path tests, and write
`gap_cuda_check.md`. No code change expected.

### The 7 audit points (the authority — PRD §4.4 + the contract)

| # | PRD §4.4 / contract requirement | how to verify |
|---|---|---|
| (a) | CUDA probe via `ctranslate2.get_cuda_device_count()` | `cuda_check._cuda_device_count()` + `is_cuda_available()` |
| (b) | CPU fallback = `device=cpu, compute_type=int8, realtime=tiny.en, model=small.en` | `CPU_FALLBACK` module dict |
| (c) | probe returns `{device, compute_type, final_model, realtime_model}` | `resolve_device_and_models()` return |
| (d) | lite CPU substitute = `tiny.en` | daemon `cfg_to_kwargs` lite branch + `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` |
| (e) | daemon consumes cuda_check output | daemon `_resolve_device_config` (L141) + `cfg_to_kwargs` (L158) |
| (f) | daemon logs resolved device at startup | daemon `_log_resolved_device()` (L918) |
| (g) | daemon surfaces device in status | daemon `status_snapshot()` (L1558) returns device/compute_type/models |
| (h) | machine: ctranslate2 count ≥ 1 | LIVE probe + `cuda_check` CLI `VERDICT=` |

### Success Criteria

- [ ] `gap_cuda_check.md` records: (a)✅ (b)✅ (c)✅ (d)✅ (e)✅ (f)✅ (g)✅ (h)✅ (each with file:line).
- [ ] `timeout 60 .venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` → `1`.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or cpu or lite or fixed)"` → `<N> passed` (baseline **7**), 0 failed.
- [ ] The report's notes section records the three non-blocking observations (cuDNN limitation; torch-is-diagnostic; CLI not unit-tested) — none is a §4.4 defect.
- [ ] **No source files modified** unless the re-verification surfaces a REAL defect (none expected). If a defect IS found, fix it + record it; otherwise "no source changes — compliant per audit."
- [ ] `git diff --name-only` (excluding `plan/`) is EMPTY on the no-defect path (the report lives under `plan/.../architecture/`).

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim current `cuda_check.py` source (with file:line for every load-bearing statement),
the daemon consumption points (`_resolve_device_config`/`cfg_to_kwargs`/`_log_resolved_device`/
`status_snapshot`/`_resolved_device`/`_unprobed_device_config` — all with file:line), the contract's 7
points mapped to specific code + tests, the live `ctranslate2` probe result (count=1, VERDICT=cuda-ok),
the parallel-sibling no-conflict analysis, the gap-report convention (`gap_<module>.md` under
`architecture/`), and the verified pytest baseline (7 passed) are all below. An agent new to this repo
can re-verify + transcribe from this PRP alone. No daemon/audio/display needed — the audit reads source,
runs monkeypatched tests (no CUDA/driver probe in the tests), and runs the cuda_check CLI smoke once
(imports ctranslate2 + queries the driver — no model load, no daemon).

### Documentation & References

```yaml
# MUST READ — the verified audit findings + the report structure (this task's own research)
- docfile: plan/006_862ee9d6ef41/P1M1T4S1/research/cuda_check_prd44_audit.md
  why: "§0 is the VERIFIED VERDICT (COMPLIANT, no fix). §1 is the per-point evidence table with file:line
        for all 7 requirements + the path tests. §2 is the test-suite result (7 passed) + the _cuda_resolve
        helper explanation. §3 is the live machine probe (count=1, VERDICT=cuda-ok). §4 is config.py
        AsrConfig defaults (the inputs cuda_check receives). §5 is the VT-001 architectural nuance (the
        daemon process never probes CUDA — the child owns the resolution; the cache seeding sites). §6 is
        the three non-blocking observations (cuDNN limitation; torch-is-diagnostic; CLI not unit-tested).
        §7 scope discipline + parallel no-conflict. §8 validation tooling + the timeout rule."
  critical: "§5 (VT-001) is load-bearing: the daemon PROCESS never calls cuda_check — status_snapshot
            reads _resolved_device_cache which the recorder-host CHILD seeds on arm. Do NOT report 'the
            daemon doesn't probe CUDA at startup' as a defect — it is the deliberate VT-001 invariant.
            §6-obs1 (cuDNN limitation) is documented + mitigated by the force_cpu retry — NOT a defect."

# THE FILE UNDER AUDIT — voice_typing/cuda_check.py
- file: voice_typing/cuda_check.py
  why: "The probe + the two configs. CUDA_DEFAULTS (device=cuda,compute_type=float16,final_model=distil-large-v3,
        realtime_model=small.en) + CPU_FALLBACK (device=cpu,compute_type=int8,final_model=small.en,
        realtime_model=tiny.en) are module-level dicts. _cuda_device_count() wraps import+call in try/except
        (count==0 on ANY failure). is_cuda_available() = count>=1. resolve_device_and_models(defaults=None)
        returns dict(defaults) on cuda-ok else dict(CPU_FALLBACK). _main() is the CLI smoke (greppable
        VERDICT= line). The module docstring documents the cuDNN LIMITATION + the VT-001 wiring notes."
  pattern: "resolve_device_and_models() is the SINGLE resolution site (returns a fresh dict). The MUST-HAVE
            gate is ctranslate2 (the whisper engine); torch.cuda is NICE-TO-HAVE diagnostics only (Silero
            VAD uses torch + runs fine on CPU) — it does NOT gate the verdict. CUDA_DEFAULTS/CPU_FALLBACK
            are plain dicts the daemon maps: final_model->model=, realtime_model->realtime_model_type=."
  gotcha: "get_cuda_device_count() queries the DRIVER only — it does NOT load cuDNN. A missing
           libcudnn_ops.so.9 still yields VERDICT=cuda-ok; the failure surfaces later at WhisperModel
           construction. This is DOCUMENTED (module docstring LIMITATION) + mitigated by the daemon's
           force_cpu->CPU_FALLBACK retry — NOT a defect (research §6-obs1). cuda_check MUST NOT set
           LD_LIBRARY_PATH itself (ld.so reads it only at exec) — launch_daemon.sh (P1.M4.T2) does that."

# THE DAEMON CONSUMPTION — voice_typing/daemon.py (the consumers)
- file: voice_typing/daemon.py
  why: "The 5 consumption points: (e) _resolve_device_config(cfg) @141 builds defaults from cfg + calls
        cuda_check.resolve_device_and_models(defaults); cfg_to_kwargs(cfg,resolved,lite) @158 consumes the
        resolved dict (+ lite CPU branch ~L192: lite_model='tiny.en' if device=='cpu'). (f) _log_resolved_device()
        @918 logs 'voice-typing device resolved: device=.. compute_type=..' at startup. (g) status_snapshot()
        @1558 returns device/compute_type/final_model/realtime_model from _resolved_device() @1597 (the cache).
        _unprobed_device_config() @1604 + force_cpu path @302-311 (dict(cuda_check.CPU_FALLBACK)) round it out."
  pattern: "compute_type is NOT a config field — _resolve_device_config DERIVES it: 'float16' if
            cfg.asr.device=='cuda' else 'int8' (@151). The force_cpu path passes dict(cuda_check.CPU_FALLBACK)
            as `resolved` to SKIP the driver probe entirely (the construction-failure CPU retry hook)."
  gotcha: "VT-001 (research §5): the daemon PROCESS never probes CUDA. _resolved_device() @1597 ONLY
           returns _resolved_device_cache (seeded by __init__->_unprobed_device_config, replaced by the
           child's actual device on _load_host, reseeded on host death). So BEFORE the first successful
           arm, status reports the CONFIGURED intent (device=cuda) — qualified by models_loaded=False /
           phase=unloaded. This is CORRECT — do NOT report it as a defect."

# THE TEST SUITE — tests/test_daemon.py (the contract's run target)
- file: tests/test_daemon.py
  why: "No dedicated test_cuda_check.py — cuda_check is covered via the cfg_to_kwargs suite. The
        _cuda_resolve(monkeypatch, mapping) helper @81-99 monkeypatches daemon.cuda_check.resolve_device_and_models
        onto a deterministic path (mapping=CUDA_DEFAULTS -> cuda; mapping=CPU_FALLBACK -> cpu). The
        load-bearing tests: test_cfg_to_kwargs_cuda_path @129, test_cfg_to_kwargs_cpu_fallback @156,
        test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en @165 (point (d)), test_cfg_to_kwargs_lite_mode_uses_one_model
        @138, test_cfg_to_kwargs_fixed_values @234."
  pattern: "Tests are HERMETIC — resolve_device_and_models is mocked, so no real CUDA/driver probe runs.
            The real probe is verified empirically by running the cuda_check CLI (Validation L3). Use the
            contract's -k filter: 'cfg_to_kwargs and (cuda or cpu or lite or fixed)'."
  critical: "The CLI _main() is NOT unit-tested (research §6-obs3) — it is operator-facing diagnostics
             covered indirectly via the cfg_to_kwargs suite + the empirical CLI run. Non-blocking."

# THE GAP-REPORT CONVENTION — mirror the siblings
- file: plan/006_862ee9d6ef41/architecture/gap_config.md
  why: "P1.M1.T1.S1 established the convention: gap_<module>.md under plan/.../architecture/, with a
        per-point compliance table (PRD expected vs code actual + file:line), a test result, a
        mismatches/drift section, and a conclusion. gap_textproc.md + gap_typing.md mirror it.
        gap_cuda_check.md MUST follow the same shape so the reports are consistent + greppable."
  critical: "Write gap_cuda_check.md to plan/006_862ee9d6ef41/architecture/gap_cuda_check.md (NOT under
             P1M1T4S1/ — the architecture/ dir is the reports home). Do NOT append to a sibling report."

# THE SPEC — PRD §4.4 (the authority) + the machine facts
- file: PRD.md
  why: "§4.4 pins the CPU fallback: 'If CUDA init fails entirely, daemon MUST log clearly and fall back to
        device=cpu, compute_type=int8 with realtime_model_type=tiny.en, model small.en — degraded but
        functional — and say so in status.' §2 machine facts: RTX 3080 Ti, driver 610.43.02, CUDA UMD 13.3,
        no system cuDNN (use pip nvidia-cudnn-cu12/cublas-cu12 wheels)."
  critical: "§4.4 is the spec; the audit maps each line to cuda_check.py/daemon.py code. The cuDNN wheels
             are wired by launch_daemon.sh (P1.M4.T2) — OUT of this audit's scope; just cross-reference."

# THE SIBLING (parallel) — confirms no overlap
- docfile: plan/006_862ee9d6ef41/P1M1T3S1/PRP.md
  why: "T3.S1 audits voice_typing/typing_backends.py + runs tests/test_typing_backends.py + writes
        gap_typing.md. T4.S1 audits voice_typing/cuda_check.py + daemon.py consumption + runs the
        test_daemon.py cfg_to_kwargs suite + writes gap_cuda_check.md. DISJOINT files — no merge conflict.
        Both are verification tasks; both follow gap_<module>.md."
  critical: "Do NOT re-audit typing_backends/config/textproc here. daemon.py is READ for the cuda_check
             consumption points ONLY — do NOT re-audit the daemon main loop / recorder-host lifecycle
             (P1.M2.T1/T2 scope)."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── cuda_check.py          # THE FILE UNDER AUDIT. CUDA_DEFAULTS/CPU_FALLBACK module dicts; _cuda_device_count;
│   │                          # is_cuda_available; resolve_device_and_models; _main() CLI. Pure stdlib + ctranslate2(torch) local imports.
│   └── daemon.py              # READ for the 5 consumption points: _resolve_device_config @141, cfg_to_kwargs @158,
│                              # _log_resolved_device @918, status_snapshot @1558, _resolved_device/_unprobed_device_config @1597/1604, force_cpu @302.
└── tests/
    └── test_daemon.py         # cfg_to_kwargs path suite (the contract's run target); _cuda_resolve helper @81 mocks resolve_device_and_models.
plan/006_862ee9d6ef41/architecture/
├── gap_config.md              # P1.M1.T1.S1's report — the convention to MIRROR.
├── gap_textproc.md            # sibling T2.S1's report — also a mirror.
└── gap_cuda_check.md          # ← CREATE (this task's deliverable; same dir + shape as the siblings).
# NOTE: this task is read-only verification. The only new file is gap_cuda_check.md (under architecture/).
# No source change is expected (cuda_check.py + daemon consumption are §4.4-compliant per audit).
```

### Desired Codebase tree with files to be added/changed

```bash
plan/006_862ee9d6ef41/architecture/gap_cuda_check.md   # ← CREATE (the audit report; mirror gap_config.md/gap_textproc.md/gap_typing.md).
# (EXPECTED: NO source changes) — voice_typing/cuda_check.py + voice_typing/daemon.py + tests/test_daemon.py UNCHANGED.
# (CATCH-ALL, only if a REAL defect is found — none expected): a fix in cuda_check.py/daemon.py + a record in the report.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — THE EXPECTED VERDICT IS "COMPLIANT, NO FIX". This PRP's research CONFIRMS all 7 points pass
# + ctranslate2 count=1 + 7 tests pass. The implementing agent re-verifies (the greps + pytest + the probe
# below) and transcribes into gap_cuda_check.md. Do NOT invent a defect to "fix"; a no-change verdict is the
# correct outcome. A source edit is warranted ONLY if the re-verification surfaces a REAL §4.4 violation (it won't).

# CRITICAL #2 — VT-001: THE DAEMON PROCESS NEVER PROBES CUDA (by design). status_snapshot() reads
# _resolved_device_cache, which __init__ seeds to _unprobed_device_config() and the recorder-host CHILD
# replaces on arm. So BEFORE the first successful arm, status reports the CONFIGURED intent (device=cuda)
# qualified by models_loaded=False / phase=unloaded. This is CORRECT + intentional — do NOT report "the
# daemon doesn't probe CUDA at startup" or "status shows cuda before arm" as a defect. cuda_check runs in
# the CHILD, via cfg_to_kwargs->build_recorder. (research §5.)

# CRITICAL #3 — THE cuDNN LIMITATION IS DOCUMENTED + MITIGATED, NOT A DEFECT. get_cuda_device_count() queries
# the CUDA DRIVER only — it does NOT load cuDNN. A missing libcudnn_ops.so.9 still yields VERDICT=cuda-ok;
# the failure surfaces later at WhisperModel construction. cuda_check's module docstring documents this
# (LIMITATION section); the daemon's force_cpu->dict(cuda_check.CPU_FALLBACK) retry (daemon.py:302-311)
# absorbs a construction failure. Record it as a known limitation, do NOT "fix" cuda_check to probe cuDNN
# (that would require importing the heavy whisper stack into the probe). cuDNN discovery is launch_daemon.sh
# (P1.M4.T2). (research §6-obs1.)

# CRITICAL #4 — gap_cuda_check.md GOES UNDER architecture/, NOT P1M1T4S1/. The gap-report convention (from
# P1.M1.T1.S1's gap_config.md + siblings gap_textproc.md/gap_typing.md) puts reports at
# plan/006_862ee9d6ef41/architecture/gap_<module>.md. Write gap_cuda_check.md THERE. Do NOT put it under
# P1M1T4S1/ (that's the PRP/research home) and do NOT append to a sibling report. (research §7.)

# GOTCHA #5 — torch.cuda IS DIAGNOSTICS, NOT A GATE. is_cuda_available() (the verdict gate) checks
# ctranslate2 ONLY. _torch_cuda_available() is a NICE-TO-HAVE probe (only Silero VAD uses torch, and it
# runs fine on CPU); it does NOT gate the verdict. Record this so a future reader doesn't "promote" torch
# to a gate (that would mis-fallback on a torch-only failure). (research §6-obs2.)

# GOTCHA #6 — USE FULL PATHS + WRAP THE PROBE IN A TIMEOUT. This machine aliases python3->uv run, pip->alias.
# Invoke .venv/bin/python explicitly. The ctranslate2 probe is a quick import+count (no model load, ~1s), but
# per repo AGENTS.md Rule 1 EVERY non-trivial command gets an inner `timeout` + the bash-tool `timeout`.
# Use `timeout 60 .venv/bin/python -c ...` (inner) and set the bash-tool `timeout` above it (e.g. 90). Never
# bare python/pytest/uv. (research §8; system_context.md.)

# GOTCHA #7 — THIS PROJECT USES pytest (NO ruff/mypy in pyproject). Validation = pytest + grep + the probe.
# Do NOT invent ruff/mypy commands (the PRP template's ruff/mypy L1 lines are N/A here). (research §8.)

# GOTCHA #8 — DO NOT run/restart the live daemon, voicectl, or the systemd unit. This audit is read-only:
# read cuda_check.py + daemon.py, run the MONKEYPATCHED test suite (no CUDA/driver probe in the tests), and
# run the cuda_check CLI smoke once (imports ctranslate2 + queries the driver — no model load, no daemon).
# No socket, no systemd, no audio. (research §8.)

# GOTCHA #9 — THE CLI _main() IS NOT UNIT-TESTED (non-blocking). cuda_check._main() is operator-facing
# diagnostics (greppable VERDICT= line). Its logic (_cuda_device_count/is_cuda_available/resolve_device_and_models)
# IS exercised via the cfg_to_kwargs suite (mocked). Verify the CLI empirically (Validation L3), not by a test.
# Record this in the report's notes — it is NOT a §4.4 defect. (research §6-obs3.)

# GOTCHA #10 — DO NOT modify PRD.md, tasks.json, prd_snapshot.md, .gitignore, or any test/source file (unless
# a real defect is found — none expected). The only new file is gap_cuda_check.md (under architecture/).
# daemon.py is READ for the cuda_check consumption points — do NOT edit it.
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config. The only "data" is the **audit report**
(`gap_cuda_check.md`) produced by re-running the greps + pytest + the ctranslate2 probe and
transcribing the verified findings.

### Verification Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the files under audit + the report home exist (no mutation)
  - RUN:
      cd /home/dustin/projects/voice-typing
      test -f voice_typing/cuda_check.py && echo "ok: cuda_check.py present" || echo "FAIL: missing"
      test -f voice_typing/daemon.py && echo "ok: daemon.py present" || echo "FAIL: missing"
      test -f tests/test_daemon.py && echo "ok: test file present" || echo "FAIL: missing"
      test -d plan/006_862ee9d6ef41/architecture && echo "ok: architecture/ dir exists (report home)" || echo "FAIL: dir missing"
      ls plan/006_862ee9d6ef41/architecture/gap_*.md   # the convention to mirror (gap_config.md, gap_textproc.md, gap_typing.md)
  - EXPECTED: all files present; the architecture/ dir exists with the sibling gap reports (the shape to mirror).

Task 2: STATIC AUDIT — re-verify the 7 PRD §4.4 points against cuda_check.py + daemon.py (the greps)
  - RUN (each MUST match — these are the file:line evidence for the report):
      cd /home/dustin/projects/voice-typing
      echo "(a) CUDA probe via ctranslate2.get_cuda_device_count:"
      grep -nE 'get_cuda_device_count|def is_cuda_available' voice_typing/cuda_check.py
      echo "(b) CPU_FALLBACK exact values (device=cpu, int8, small.en, tiny.en):"
      grep -nE 'CPU_FALLBACK\s*:|"device":\s*"cpu"|"compute_type":\s*"int8"|"final_model":\s*"small.en"|"realtime_model":\s*"tiny.en"' voice_typing/cuda_check.py
      echo "(c) resolve_device_and_models returns the dict (device/compute_type/final_model/realtime_model):"
      grep -nE 'def resolve_device_and_models|return dict\(defaults\)|return dict\(CPU_FALLBACK\)' voice_typing/cuda_check.py
      echo "(d) lite CPU substitute = tiny.en (daemon cfg_to_kwargs):"
      grep -nE 'lite_model = "tiny.en" if resolved\["device"\] == "cpu"' voice_typing/daemon.py
      echo "(e) daemon consumes cuda_check (_resolve_device_config + cfg_to_kwargs):"
      grep -nE 'def _resolve_device_config|return cuda_check.resolve_device_and_models|def cfg_to_kwargs' voice_typing/daemon.py
      echo "(f) startup device logging (_log_resolved_device):"
      grep -nE 'def _log_resolved_device|voice-typing device resolved' voice_typing/daemon.py
      echo "(g) status surfaces device (status_snapshot + _resolved_device):"
      grep -nE 'def status_snapshot|"device":\s*dev\.get\("device"|def _resolved_device' voice_typing/daemon.py
  - EXPECTED: (a) probe @ _cuda_device_count + is_cuda_available; (b) CPU_FALLBACK dict with the 4 exact values;
    (c) resolve_device_and_models with both return branches; (d) lite branch @~L192; (e) _resolve_device_config @141 +
    cfg_to_kwargs @158; (f) _log_resolved_device @918 + the log line; (g) status_snapshot @1558 + _resolved_device @1597.
    (research §1.) Transcribe these file:line into the report's table.

Task 3: LIVE PROBE — verify ctranslate2.get_cuda_device_count() >= 1 + the cuda_check CLI verdict
  - RUN (WRAP in timeout per AGENTS.md Rule 1; no model load, ~1s):
      cd /home/dustin/projects/voice-typing
      timeout 60 .venv/bin/python -c "import ctranslate2; print('cuda_device_count =', ctranslate2.get_cuda_device_count())"
      echo "exit=$?"
      timeout 60 .venv/bin/python -m voice_typing.cuda_check
      echo "exit=$? (0=cuda-ok, 1=cpu-fallback-required)"
  - EXPECTED: count >= 1 (baseline `1` on this RTX 3080 Ti); CLI prints `VERDICT=cuda-ok` + the resolved cuda
    config (device=cuda, compute_type=float16, final_model=distil-large-v3, realtime_model=small.en). (research §3.)
  - NOTE: this machine HAS CUDA, so the live probe exercises the CUDA path only. The CPU_FALLBACK path is covered
    by the monkeypatched tests (Task 4) — that's WHY the tests mock resolve_device_and_models.

Task 4: RUN the test suite (the contract's run target) — capture the count
  - RUN (hermetic — resolve_device_and_models is mocked; no CUDA/driver probe):
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or cpu or lite or fixed)" 2>&1 | tail -5
  - EXPECTED: "7 passed in 0.02s" (baseline), 0 failed/errors. Record the exact count + timing in the report.
    (research §2.)
  - IF a test fails (it won't): investigate via `pytest tests/test_daemon.py::<test> -v --tb=long`. A failure
    here would indicate a real cuda_check/daemon-consumption defect — classify + report; the only in-scope "fix"
    is a cuda_check.py/daemon.py §4.4 defect, which the audit proves absent.

Task 5: WRITE plan/006_862ee9d6ef41/architecture/gap_cuda_check.md (the deliverable) — mirror the sibling shape
  - STRUCTURE (mirror gap_config.md / gap_textproc.md / gap_typing.md):
      1. Header + verdict: "# cuda_check.py + daemon consumption — PRD §4.4 compliance audit" +
         "VERDICT: COMPLIANT (no fix needed)."
      2. Per-point compliance table: 8 rows (# | PRD §4.4/contract expected | code actual (file:line) | result).
         All PASS. Use the file:line from Task 2. (Rows a-h from the 7-audit-points table + the machine probe (h).)
      3. Live probe result: the exact output from Task 3 (count=1, VERDICT=cuda-ok, resolved cuda config) + a note
         that this machine has CUDA so the fallback is covered by mocked tests.
      4. Test-suite result: the exact line from Task 4 ("7 passed in 0.02s"), + a short coverage summary
         (_cuda_resolve helper mocks resolve_device_and_models; cuda_path/cpu_fallback/lite_cpu_fallback/lite_one_model/fixed).
      5. Architectural note (VT-001): the daemon PROCESS never probes CUDA — the recorder-host CHILD owns the
         resolution; status_snapshot reads _resolved_device_cache seeded by the child on arm; before arm, status
         reports the configured intent qualified by models_loaded=False/phase=unloaded. This is CORRECT (not a defect).
      6. Mismatches / drift / notes: "None — fully §4.4-compliant." + the THREE non-blocking observations:
         - (obs1) cuDNN limitation: get_cuda_device_count() probes the DRIVER only, not cuDNN — a missing
           libcudnn_ops.so.9 still yields cuda-ok; documented in cuda_check.py docstring + mitigated by the
           daemon's force_cpu->CPU_FALLBACK retry. cuDNN discovery is launch_daemon.sh (P1.M4.T2).
         - (obs2) torch.cuda is diagnostics, not a gate: is_cuda_available() checks ctranslate2 only; torch is
           nice-to-have (Silero VAD runs fine on CPU) and does NOT gate the verdict.
         - (obs3) CLI _main() is operator-facing, not unit-tested: verified empirically (Task 3); its logic is
           covered via the cfg_to_kwargs suite (mocked). Non-blocking.
      7. Conclusion: COMPLIANT; no source changes; cuda_check.py + daemon consumption faithfully implement
         PRD §4.4 (probe, exact CPU fallback, lite=tiny.en, daemon consumption, startup logging, status surface).
  - DO NOT: put the report under P1M1T4S1/ (it goes under architecture/ — Gotcha #4); append to a sibling
    report; invent a defect; omit the VT-001 note (Gotcha #2) or the three observations (Gotcha #3/#5/#9).

Task 6: VALIDATE — run the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T4.S1: cuda_check PRD §4.4 audit — COMPLIANT (7/7 points, ctranslate2 count=1,
  7 path tests pass, no fix needed); gap_cuda_check.md recorded." (Or, if a real defect was found+fixed:
  "...fixed <defect> in <file>; recorded in gap_cuda_check.md.")
```

### Implementation Patterns & Key Details

```bash
# This subtask has NO implementation patterns — it is read-only verification + report-writing. The
# load-bearing facts (each verified in this PRP's research note):
#
# FACT 1: cuda_check.py is PRD §4.4-compliant — CUDA_DEFAULTS + CPU_FALLBACK (exact PRD values), probe via
#         ctranslate2.get_cuda_device_count() (count==0 on ANY failure), resolve_device_and_models() the
#         single resolution site (dict(defaults) on cuda-ok else dict(CPU_FALLBACK)).
# FACT 2: daemon consumption is correct — _resolve_device_config @141 + cfg_to_kwargs @158 consume the
#         resolved dict; lite CPU substitute = tiny.en (~L192); _log_resolved_device @918 logs at startup;
#         status_snapshot @1558 surfaces device/compute_type/models.
# FACT 3: tests/test_daemon.py cfg_to_kwargs suite = 7 passed (resolve_device_and_models mocked; hermetic).
# FACT 4: live machine probe = ctranslate2 count 1, VERDICT=cuda-ok (this machine HAS CUDA).
# FACT 5: VT-001 — the daemon process NEVER probes CUDA (the recorder-host child does); status reads the
#         cache the child seeds. This is the deliberate architecture, not a defect.
# FACT 6: cuDNN limitation is documented + mitigated (force_cpu retry); torch is diagnostics-not-gate;
#         CLI _main() is operator-facing not unit-tested — all three NON-BLOCKING.
#
# THE DELIVERABLE (the whole task): gap_cuda_check.md under architecture/, mirroring the sibling shape.
```

### Integration Points

```yaml
DELTA ACCEPTANCE (PRD §4.4 — "log clearly and fall back ... and say so in status"):
  - This subtask produces the §4.4 compliance evidence for the CUDA probe + CPU fallback. The "degraded but
    functional" guarantee is certified by (b) CPU_FALLBACK exact values; "say so in status" by (g) status_snapshot.
  - The gap_cuda_check.md report IS the acceptance evidence. No repo source file is modified (expected).

PARALLEL — P1.M1.T3.S1 (typing_backends audit, in flight):
  - T3.S1 audits voice_typing/typing_backends.py + writes gap_typing.md. T4.S1 audits voice_typing/cuda_check.py
    + daemon.py consumption + writes gap_cuda_check.md. DISJOINT files. Both follow the gap_<module>.md
    convention. No merge conflict.

DOWNSTREAM (consumers of cuda_check):
  - P1.M2.T2 (recorder-host lifecycle): the CHILD that owns the cuda_check resolution + seeds the daemon cache.
    This audit RECORDS the VT-001 invariant; P1.M2.T2 audits the child mechanics.
  - P1.M2.T4 (recorder kwargs): audits cfg_to_kwargs/build_recorder kwargs against §4.4's exact starting values.
    This audit confirms the device/compute_type/models flow INTO those kwargs is correct.
  - P1.M4.T2 (launch_daemon.sh cuDNN): the LD_LIBRARY_PATH wrapper that makes cuDNN findable — cross-referenced
    in the cuDNN-limitation note (§6-obs1), but OUT of this audit's scope.

NO INTERFACE / BEHAVIOR CHANGES:
  - voice_typing/cuda_check.py + voice_typing/daemon.py + tests/test_daemon.py: UNCHANGED (expected). The output
    is the gap_cuda_check.md report. DOCS: none for this subtask (cuda_check is an internal module; CPU-only
    instructions are in README — Mode A, P1.M6.T1).
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy — Gotcha #7). The greps +
> pytest are hermetic (resolve_device_and_models mocked in the tests); the ctranslate2 probe imports
> ctranslate2 + queries the driver (no model load, no daemon) — WRAP it in `timeout` per AGENTS.md Rule 1.

### Level 1: The 7 audit points pass statically (the file:line evidence)

```bash
cd /home/dustin/projects/voice-typing
echo "(a)"; grep -nE 'get_cuda_device_count|def is_cuda_available' voice_typing/cuda_check.py
echo "(b)"; grep -nE 'CPU_FALLBACK\s*:|"device":\s*"cpu"|"compute_type":\s*"int8"|"final_model":\s*"small.en"|"realtime_model":\s*"tiny.en"' voice_typing/cuda_check.py
echo "(c)"; grep -nE 'def resolve_device_and_models|return dict\(defaults\)|return dict\(CPU_FALLBACK\)' voice_typing/cuda_check.py
echo "(d)"; grep -nE 'lite_model = "tiny.en" if resolved\["device"\] == "cpu"' voice_typing/daemon.py
echo "(e)"; grep -nE 'def _resolve_device_config|return cuda_check.resolve_device_and_models|def cfg_to_kwargs' voice_typing/daemon.py
echo "(f)"; grep -nE 'def _log_resolved_device|voice-typing device resolved' voice_typing/daemon.py
echo "(g)"; grep -nE 'def status_snapshot|def _resolved_device' voice_typing/daemon.py
# Expected: all 7 points present with file:line (research §1).
```

### Level 2: The ctranslate2 probe + the unit suite (the contract's verification gate)

```bash
cd /home/dustin/projects/voice-typing
echo "--- LIVE ctranslate2 probe (WRAP in timeout; no model load) ---"
timeout 60 .venv/bin/python -c "import ctranslate2; print('cuda_device_count =', ctranslate2.get_cuda_device_count())"
echo "--- cuda_check CLI verdict ---"
timeout 60 .venv/bin/python -m voice_typing.cuda_check
echo "--- cfg_to_kwargs path tests (hermetic; resolve_device_and_models mocked) ---"
.venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or cpu or lite or fixed)" 2>&1 | tail -5
# Expected: count >= 1 (baseline 1); CLI VERDICT=cuda-ok + resolved cuda config; "7 passed in 0.02s", 0 failed.
```

### Level 3: The gap_cuda_check.md report exists + is faithful (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_cuda_check.md
test -f "$F" && echo "L3 PASS: gap_cuda_check.md exists (under architecture/)" || echo "L3 FAIL: report missing"
grep -qiE 'compliant|PASS' "$F" && echo "L3 PASS: records a compliance verdict" || echo "L3 FAIL: no verdict"
grep -qiE 'cpu_fallback|tiny.en|int8|CPU_FALLBACK|pressing|device.*cpu' "$F" && echo "L3 PASS: covers the CPU fallback" || echo "L3 CHECK: CPU fallback wording"
grep -qiE 'lite.*tiny.en|tiny.en.*lite' "$F" && echo "L3 PASS: records lite CPU = tiny.en" || echo "L3 CHECK: lite wording"
grep -qiE 'status_snapshot|say so in status|surface' "$F" && echo "L3 PASS: covers the status surface" || echo "L3 CHECK: status wording"
grep -qiE 'VT-001|never probes|child|recorder-host' "$F" && echo "L3 PASS: records the VT-001 nuance" || echo "L3 CHECK: VT-001 note"
grep -qiE 'cudnn|cuDNN' "$F" && echo "L3 PASS: records the cuDNN limitation" || echo "L3 CHECK: cuDNN note"
grep -qiE '7 passed|tests? passed' "$F" && echo "L3 PASS: records the test count" || echo "L3 FAIL: no test count"
grep -qiE 'cuda_device_count|ctranslate2.*1|count.*1' "$F" && echo "L3 PASS: records the live probe" || echo "L3 FAIL: no probe result"
# Faithfulness: the report's verdict must match the live audit (COMPLIANT).
grep -qiE 'compliant|no fix|no source change' "$F" && echo "L3 PASS: verdict = compliant (matches live audit)" || echo "L3 CHECK: verdict wording"
# Expected: report exists under architecture/; records COMPLIANT + the 7 points + the probe + the 7-passed
# count + the VT-001 note + the cuDNN limitation note.
```

### Level 4: Scope guards — only gap_cuda_check.md created; no source/test changes (expected)

```bash
cd /home/dustin/projects/voice-typing
echo "--- EXPECTED: only the report is new (under plan/); no source/test changes ---"
git status --short | grep -vE '^\?\? plan/' || echo "(nothing outside plan/)"
git diff --exit-code -- voice_typing/cuda_check.py voice_typing/daemon.py tests/test_daemon.py voice_typing/config.py voice_typing/typing_backends.py voice_typing/textproc.py config.toml README.md pyproject.toml && echo "L4 PASS: no source/test/config changes (no-defect path)" || echo "L4 NOTE: a source file changed — confirm it was a REAL defect fix recorded in gap_cuda_check.md (none expected)"
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/006_862ee9d6ef41/tasks.json plan/006_862ee9d6ef41/prd_snapshot.md .gitignore && echo "L4 PASS: read-only files unchanged" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected (no-defect path): git status shows ONLY plan/ (the new gap_cuda_check.md under architecture/ + this
# PRP/research) + tasks.json (orchestrator); cuda_check.py/daemon.py/test_daemon.py/config.toml unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: all 7 PRD §4.4 points present with file:line (probe; CPU_FALLBACK exact values; resolve dict; lite=tiny.en; daemon _resolve_device_config+cfg_to_kwargs; _log_resolved_device; status_snapshot).
- [ ] L2: `ctranslate2.get_cuda_device_count()` → `1` (≥1); `cuda_check` CLI → `VERDICT=cuda-ok`; `tests/test_daemon.py` cfg_to_kwargs suite → `<N> passed` (baseline 7), 0 failed.
- [ ] L3: `gap_cuda_check.md` exists under `architecture/`, records COMPLIANT + the 7 points + the probe + the test count + the VT-001 note + the cuDNN limitation note.
- [ ] L4: only `gap_cuda_check.md` created (under plan/); no source/test/config/read-only changes (no-defect path).

### Feature Validation
- [ ] Verdict recorded: `cuda_check.py` + daemon consumption are PRD §4.4-compliant (7/7 points) — no fix needed (expected).
- [ ] The 7 points each map to specific cuda_check.py/daemon.py file:line in the report.
- [ ] The VT-001 architectural nuance (daemon process never probes CUDA; the child owns the resolution) is recorded as CORRECT, not a defect.
- [ ] The three non-blocking observations (cuDNN limitation; torch-is-diagnostic; CLI not unit-tested) are recorded so they aren't mistaken for defects.
- [ ] If a REAL defect was found (none expected), it's fixed + recorded in the report.

### Code Quality / Scope Validation
- [ ] (Expected) ZERO source modifications — a no-fix verdict is the correct outcome (not a gap).
- [ ] The report mirrors the `gap_<module>.md` convention (gap_config.md/gap_textproc.md/gap_typing.md shape).
- [ ] No re-audit of config (T1.S1) / textproc (T2.S1) / typing_backends (T3.S1) / launch_daemon.sh (P1.M4.T2) / recorder-host (P1.M2.T2); no test/source edit unless a real defect.
- [ ] No conflict with parallel T3.S1 (disjoint files — cuda_check/daemon vs typing_backends).

### Documentation & Deployment
- [ ] DOCS: none for this subtask (cuda_check is an internal module; CPU-only instructions are in README — Mode A, P1.M6.T1).
- [ ] The gap_cuda_check.md report is the durable acceptance evidence for §4.4 cuda_check compliance.

---

## Anti-Patterns to Avoid

- ❌ Don't invent a defect to "fix" — the audit finds `cuda_check.py` + daemon consumption fully PRD §4.4-compliant (7/7 points + count=1 + 7 tests pass). A no-change verdict is the correct, expected outcome. A source edit is warranted ONLY for a REAL §4.4 violation surfaced by the re-verification (it won't be). (Gotcha #1.)
- ❌ Don't report "the daemon process doesn't probe CUDA at startup" or "status shows cuda before arm" as a defect — that is the deliberate **VT-001** invariant (the recorder-host CHILD owns the cuda_check resolution; status reads the cache the child seeds). Recording it is required; "fixing" it re-introduces a CUDA context in the daemon process. (Gotcha #2.)
- ❌ Don't report the cuDNN limitation as a defect — `get_cuda_device_count()` probes the DRIVER only (documented in cuda_check.py's docstring LIMITATION); the daemon's force_cpu→CPU_FALLBACK retry absorbs a construction failure, and cuDNN discovery is launch_daemon.sh (P1.M4.T2). Do NOT make cuda_check probe cuDNN (that would import the heavy whisper stack into the probe). (Gotcha #3.)
- ❌ Don't put `gap_cuda_check.md` under `P1M1T4S1/` or append it to a sibling report — the convention is `plan/006_862ee9d6ef41/architecture/gap_<module>.md`. Write it there. (Gotcha #4.)
- ❌ Don't "promote" `torch.cuda.is_available()` to a verdict gate — it is diagnostics only (Silero VAD uses torch and runs fine on CPU); `is_cuda_available()` checks ctranslate2 only. (Gotcha #5.)
- ❌ Don't run the ctranslate2 probe without a timeout — per AGENTS.md Rule 1 EVERY non-trivial command gets an inner `timeout` + the bash-tool `timeout`. Use `timeout 60 .venv/bin/python -c ...`. (Gotcha #6.)
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases shadow them) — use `.venv/bin/python -m pytest` / `.venv/bin/python -c`. (Gotcha #6.)
- ❌ Don't invent ruff/mypy gates — this project uses pytest + grep only. (Gotcha #7.)
- ❌ Don't run/restart the live daemon, voicectl, or the systemd unit — this audit is read-only (read source + run mocked tests + run the cuda_check CLI smoke once). No socket/systemd/audio. (Gotcha #8.)
- ❌ Don't omit the three non-blocking notes (cuDNN limitation; torch-is-diagnostic; CLI not unit-tested) — they must be recorded so a future reader doesn't mis-read them as defects (or "fix" the probe to load cuDNN). (Gotcha #9.)
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or any test/source file (unless a real defect is found — none expected). daemon.py is READ for the cuda_check consumption points, not edited. (Gotcha #10.)

---

## Confidence Score

**9.5/10** for one-pass verification success. The verdict is already verified in this PRP's research: **`cuda_check.py` + daemon consumption are PRD §4.4-compliant on all 7 points (each with file:line), `ctranslate2.get_cuda_device_count() == 1` / `VERDICT=cuda-ok`, and `tests/test_daemon.py` cfg_to_kwargs suite = 7 passed.** The 7 audit greps + the probe + the pytest command are given verbatim, the gap-report convention (mirror `gap_config.md`/`gap_textproc.md`/`gap_typing.md` under `architecture/`) is confirmed, and the VT-001 architectural nuance + the three non-blocking observations are documented so they aren't mistaken for defects. The parallel sibling T3.S1 edits disjoint files (typing_backends), so no merge conflict. The −0.5 residual is purely the small chance the implementing agent mis-reads the VT-001 invariant (status shows cuda before arm) or the cuDNN limitation as a defect — which Gotcha #2 + Gotcha #3 + the report's notes sections guard against. No daemon, socket, audio, or display is required (only a one-shot ctranslate2 driver probe, wrapped in a timeout).