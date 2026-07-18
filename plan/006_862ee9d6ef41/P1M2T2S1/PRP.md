# PRP — P1.M2.T2.S1: Audit lazy-load states — unloaded→loading→loaded, single-flight lock, boot=~0 VRAM

## Goal

**Feature Goal**: Produce the authoritative **lazy-load lifecycle audit** as a new report `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md`, cross-checking `voice_typing/daemon.py`'s lazy-load state machine — `VoiceTypingDaemon.__init__` boot state (648-671), `_load_host` (698-795, single-flight + success/failure + mode-switch), `_handle_dead_host` (874-903), and the `run()` liveness check (840-846) — against **PRD §4.2bis** on the 5 item properties (a)-(e) + the boot-VRAM / teardown-lock / mode-switch points. This is a **verification/audit** subtask (verification round `006_862ee9d6ef41`): the deliverable is the report; **code changes happen ONLY if a real defect is found — none is expected; this PRP's author has already performed the audit and the lifecycle is PRD §4.2bis-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the lazy-load lifecycle is PRD §4.2bis COMPLIANT — no fix needed.** All 5 properties (a-e) pass (daemon.py file:line in the research note); the `-k 'load or spawn or dead or unload or boot or unloaded'` slice = **43 passed, 176 deselected in 1.13s**.

**Deliverable** (ONE new report file; NO source edits, NO test edits): `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` — a gap report in the established `gap_*.md` format (mirror `gap_daemon_loop.md`) containing: (1) scope + audited artifacts (file:line); (2) a per-property compliance table (PRD §4.2bis expected vs code actual, daemon.py file:line) for (a)-(e) + the extra points; (3) the test pass/fail count for the contract's run target; (4) the non-defect nuances (recorder→host naming; `_load_recorder` alias; mode-switch/lite = M2.T3; teardown bound = S3; VT-001/VT-002 status = M3); (5) a conclusion tying the verdict to acceptance criteria **#6** (starts un-loaded, ~0 VRAM) and **#9** (idle-unload → reload). **This PRP's author has already performed the audit** (findings in the research note) — the implementing agent re-verifies, re-runs the tests, and transcribes the report.

**Success Definition**:
- (a) `architecture/gap_lifecycle.md` exists with the 5 sections above (scope/artifacts, compliance table, test evidence, nuances, conclusion).
- (b) The recorded findings match the live re-verification: all 5 item properties (a)-(e) are **compliant** (each with daemon.py file:line).
- (c) `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or spawn or dead or unload or boot or unloaded'` → all pass (record the count; verified baseline: **43 passed, 176 deselected**).
- (d) **No source or test files are modified** (because no defect exists — the lifecycle is PRD §4.2bis-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` (new) — no `voice_typing/*`, no `tests/*`, no `PRD.md`/`tasks.json`/`prd_snapshot.md` change.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that the daemon boots at ~0 VRAM, loads models only on the first arm, serializes concurrent arms via a single-flight lock, recovers from a child crash, and leaves no half-built recorder on failure — before relying on the lazy-load lifecycle (acceptance #6 + #9). Also the downstream P1.M5.T5 acceptance-criteria cross-check (which maps #6/#9 to this audit's evidence).

**Use Case**: A future change to `_load_host` / `_handle_dead_host` / the boot state. The audit + the 43 lifecycle tests are the reference that proves the change keeps (or breaks) PRD §4.2bis compliance.

**Pain Points Addressed**: Closes the "does the daemon REALLY boot unloaded, single-flight concurrent arms, recover from a dead child, and avoid a half-built recorder on failure?" question with recorded, re-runnable evidence — not an assumption. Acceptance #6 (un-loaded boot) + #9 (idle-unload → reload) are certified by (a) + (e)/(b).

## Why

- **§4.2bis is the VRAM-correctness foundation.** The daemon autostarts on every login but is used rarely; lazy load is what keeps it from parking ~2.8 GB on the GPU 24/7. The audit certifies the boot=~0-VRAM claim (acceptance #6) and the load-on-first-arm / single-flight / recovery invariants with recorded evidence.
- **No half-built recorder + recovery are robustness MUSTs.** PRD §4.2bis: a failed load "MUST NOT leave a half-constructed recorder behind"; a crashed child must not silently break transcription. The audit certifies both the failure-cleanup path (d) and the dead-host recovery (e) — the two failure modes that would otherwise leave the daemon stuck or wedged.
- **Single-flight is a hard concurrency requirement.** Two `voicectl` arms can race the ~1-3 s load; the audit certifies the second arm WAITS (never starts a 2nd spawn) and that teardown shares the same lock (an arm never sees a half-torn-down recorder).
- **Scope discipline.** This subtask owns the lazy-load STATE MACHINE + single-flight + boot state + dead-host recovery ONLY. The graceful drain is P1.M2.T1.S2 (parallel, disjoint); the recorder-host IPC is S2; bounded teardown detail is S3; lite/mode-switch is M2.T3; status reporting (VT-001/VT-002) is M3. This audit notes those branches sit correctly relative to the lifecycle but defers their detail to those siblings.

## What

Re-verify the lazy-load lifecycle against PRD §4.2bis by reading the 4 code regions (`__init__` boot state, `_load_host`, `_handle_dead_host`, the `run()` liveness check), re-running the 43-test lifecycle slice, and writing `architecture/gap_lifecycle.md` in the `gap_*.md` format. The audit is expected to confirm full compliance (no defects → no code changes). The report's compliance table maps each of the 5 item properties (a)-(e) + the boot-VRAM/teardown-lock/mode-switch points to PRD §4.2bis expected behavior vs the code's actual behavior (daemon.py file:line).

### Success Criteria

- [ ] `architecture/gap_lifecycle.md` created in the `gap_*.md` format (mirror `gap_daemon_loop.md`).
- [ ] Compliance table covers (a) boot state, (b) single-flight lock, (c) success transitions, (d) failure cleanup, (e) dead-host recovery, + boot-VRAM/teardown-lock/mode-switch — each COMPLIANT with daemon.py file:line.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or spawn or dead or unload or boot or unloaded'` → recorded pass count (baseline 43 passed).
- [ ] No source/test files modified (`git status --short` == the new report only).
- [ ] Conclusion ties the verdict to acceptance #6 (un-loaded boot) + #9 (idle-unload → reload).

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §2: every property mapped to daemon.py file:line with the COMPLIANT verdict + the 43-test evidence). A developer new to this repo can re-verify from the research note + the cited code regions: the exact line ranges (init 648-671, _load_host 698-795, run() check 840-846, _handle_dead_host 874-903), the grep commands to re-locate them, the test command, and the `gap_*.md` report format (sibling `gap_daemon_loop.md`). The non-defect nuances (recorder→host naming, the `_load_recorder` alias, the M2.T3/S3/M3 deferrals) are documented so they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + test evidence)
- docfile: plan/006_862ee9d6ef41/P1M2T2S1/research/lifecycle_audit.md
  why: "§1 the 5 item properties mapped to PRD §4.2bis clauses. §2 THE FINDINGS: each of (a)-(e) + boot-VRAM/
        teardown-lock/mode-switch verified COMPLIANT with exact daemon.py file:line (init 648-671, _load_host
        698-795, _handle_dead_host 874-903, run() check 840) + the test that proves it. §3 test evidence (43 passed).
        §4 non-defect nuances (recorder->host, _load_recorder alias, M2.T3/S3/M3 deferrals). §5 verdict COMPLIANT.
        §6 scope boundary (disjoint from drain-audit P1.M2.T1.S2 + S2/S3/M2.T3/M3)."
  section: "ALL load-bearing. §2 (findings w/ file:line), §3 (test count), §4 (nuances) are the core to transcribe."

# MUST READ — the PRD being audited against (the contract)
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md   # (or PRD.md §4.2bis)
  why: "§4.2bis is the authoritative lifecycle spec: boot=unloaded/~0 VRAM; first arm=loading (blocks ~1-3s);
        loaded/not-listening; loaded/listening; single-flight (2nd arm waits); failure -> unloaded + {ok:false}
        + NO half-built recorder; teardown under the SAME single-flight lock; idle-unload. §7 acceptance #6
        (un-loaded boot) + #9 (idle-unload -> reload) are what this audit certifies."
  critical: "Audit against §4.2bis's WORDING (states, single-flight, no-half-built, recovery). The verified code
             facts (research §2) confirm the implementation matches — so the report states COMPLIANT."

# MUST READ — the file under audit (the 4 lifecycle regions)
- file: voice_typing/daemon.py
  why: "__init__ boot state (648-671: host/loaded/lock/cond/phase/models_loaded); _load_host (698-795: single-flight
        Condition @665/714-724, success @772-773, failure @781-794, mode-switch @716-718/736-741); _handle_dead_host
        (874-903); run() liveness check (840-846). _load_recorder (688) is a back-compat alias for _load_host('normal')."
  critical: "READ-ONLY audit. Do NOT edit daemon.py (no defect exists). Re-locate sites with grep if line numbers drift."

# MUST READ — the sibling audit reports (the gap_*.md format to mirror + scope boundaries)
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
  why: "The format template: title + Date/Scope/Audited-artifacts + 'Bottom line' (✅ compliant + test count) + §1
        Method (grep commands + re-verify) + per-point compliance table + test evidence + nuances + conclusion.
        P1.M2.T1.S1 (§1 main loop) + P1.M2.T1.S2 (§2 graceful drain) live here; this task creates the PARALLEL
        gap_lifecycle.md (not appended — a new file)."
  critical: "Mirror the format. gap_lifecycle.md is a NEW file (do NOT append to gap_daemon_loop.md — that is the
             drain audit's home). This audit DEFERS drain detail to §2 of gap_daemon_loop.md; it DEFERS teardown
             detail to S3, lite/mode-switch to M2.T3, status to M3."

# MUST READ — the parallel task contract (DISJOINT — graceful drain, not lifecycle)
- docfile: plan/006_862ee9d6ef41/P1M2T1S2/PRP.md
  why: "P1.M2.T1.S2 audits the graceful DRAIN (§4.2 #2) and appends §2 to gap_daemon_loop.md. It explicitly defers
        _handle_dead_host to THIS task (P1.M2.T2.S1) and teardown to S3. Disjoint scope — no overlap."
  critical: "Do NOT audit the drain here (P1.M2.T1.S2 owns it). Do NOT append to gap_daemon_loop.md. Your report is
             the standalone gap_lifecycle.md covering §4.2bis lazy-load ONLY."
```

### Current Codebase tree (relevant slice — the 1 report file this task creates)

```bash
/home/dustin/projects/voice-typing/
└── plan/006_862ee9d6ef41/architecture/
    └── gap_lifecycle.md      # CREATE (the audit report — the deliverable). Mirrors gap_daemon_loop.md format.
# voice_typing/daemon.py — READ-ONLY (the 4 audited regions). tests/* — READ-ONLY (re-run, do not edit).
# gap_daemon_loop.md (drain audit), gap_config.md, gap_textproc.md, etc. — existing sibling reports (do not touch).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS AN AUDIT, NOT IMPLEMENTATION. The deliverable is gap_lifecycle.md (a report). Do NOT edit
#   voice_typing/daemon.py or any test unless the re-verification surfaces a REAL defect — none is expected (the
#   lifecycle is PRD §4.2bis-compliant per the pre-verified audit). If you find no defect, record "none — compliant."
# CRITICAL #2 — USE TIMEOUTS (AGENTS.md Rule 1). The repo is a foreground daemon with hang vectors. Wrap the pytest
#   run: `timeout 300 .venv/bin/python -m pytest ...` (inner) + the bash tool timeout (outer). test_daemon.py /
#   test_recorder_host.py are mocked-CUDA (no model load) so the slice is fast (~1-2s), but the timeout is mandatory.
#   NEVER run the daemon in the foreground; NEVER run untimed voicectl/pytest.
# CRITICAL #3 — RECORD file:line EVIDENCE, not assertions. Each compliance-table row must cite the daemon.py line(s)
#   that satisfy the PRD clause (re-locate with grep if line numbers drift). The pre-verified lines: init 648-671,
#   _load_host 698-795, _handle_dead_host 874-903, run() check 840. (Research §2.)
# CRITICAL #4 — DO NOT MISTAKE NUANCES FOR DEFECTS. (i) PRD says `recorder`; code uses `self._host` (RecorderHost
#   subprocess; uniform via _LegacyRecorderHostAdapter @654) — naming drift, not a defect. (ii) `_load_recorder`
#   (688) is a back-compat alias for `_load_host('normal')` — not a defect. (iii) mode-switch/lite reload is §4.2ter
#   (M2.T3); teardown bounded-ness is S3; status VT-001/VT-002 is M3 — this audit CONFIRMS they share the §4.2bis
#   lifecycle path but DEFERS their detail. (Research §4.)
# CRITICAL #5 — gap_lifecycle.md is a NEW STANDALONE FILE. Do NOT append to gap_daemon_loop.md (that is the drain
#   audit's home, owned by P1.M2.T1.S1/S2). Create architecture/gap_lifecycle.md fresh, mirroring the gap_*.md format.
# CRITICAL #6 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest). The
#   architecture/ + plan/ paths are relative to the repo root.
```

## Implementation Blueprint

### Data models and structure

None (audit/report task). The "data" is the verified lifecycle findings (research §2), transcribed into the `gap_*.md` report format. No code, no data models.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the 4 lifecycle regions against PRD §4.2bis (read-only)
  - READ daemon.py: __init__ boot state (648-671), _load_host (698-795), run() liveness check (840-846),
    _handle_dead_host (874-903). Re-confirm each of (a)-(e) + boot-VRAM/teardown-lock/mode-switch matches PRD §4.2bis.
  - RE-LOCATE with grep if line numbers drifted: `grep -nE 'def _load_host|def _handle_dead_host|self._load_cond|
    self._models_loaded|set_phase\("loading"\)|set_phase\("idle"\)|set_phase\("unloaded"\)|not self._host.is_alive'
    voice_typing/daemon.py`.
  - FINDINGS are pre-verified COMPLIANT (research §2) — re-confirm; if a real defect appears, record + fix it.

Task 2: RE-RUN the lifecycle test slice (the audit's test evidence)
  - RUN: `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or
    spawn or dead or unload or boot or unloaded'`. Record the pass count (baseline 43 passed, 176 deselected).
  - Cite the key evidence tests in the report (single-flight, dead-host detection+respawn+status, total-failure-
    stays-unloaded, lazy-boot-unloaded, idle-unload fire/noop, arm-racing-unload). (Research §3.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_lifecycle.md (the deliverable)
  - FORMAT: mirror gap_daemon_loop.md (title + Date/Scope/Audited-artifacts + 'Bottom line' + §1 Method + §2 compliance
    table + §3 test evidence + §4 nuances + §5 conclusion).
  - CONTENT: the pre-verified findings (research §2) transcribed — each property COMPLIANT with daemon.py file:line.
  - VERDICT: ✅ COMPLIANT (no defects, no source changes). Tie to acceptance #6 (un-loaded boot) + #9 (reload).

Task 4: SCOPE GUARD
  - `git status --short` == the new gap_lifecycle.md ONLY. No voice_typing/*, no tests/*, no PRD/tasks/snapshot change.
```

### Implementation Patterns & Key Details

```markdown
<!-- gap_lifecycle.md skeleton (mirror gap_daemon_loop.md): -->
# Gap Report — P1.M2.T2.S1: Lazy-Load Lifecycle vs PRD §4.2bis
**Date:** <re-verify date>  **Scope:** Audit daemon.py __init__ (648-671) + _load_host (698-795) +
_handle_dead_host (874-903) + run() liveness (840-846) vs PRD §4.2bis on (a)-(e) + boot-VRAM/lock/mode-switch.
**Audited artifacts (read-only):** daemon.py <file:line>; tests/test_daemon.py + test_recorder_host.py (-k slice).
**Bottom line:** ✅ All 5 properties COMPLIANT (file:line below). -k slice = 43 passed. No source modified.
## 1. Method  (grep commands; re-verify reads; re-run command)
## 2. Compliance table  (| property | PRD §4.2bis expected | code actual (daemon.py:line) | test | verdict ✅ |)
## 3. Test evidence  (the -k command + count + key test names)
## 4. Non-defect nuances  (recorder→host; _load_recorder alias; mode-switch/lite=M2.T3; teardown=S3; status=M3)
## 5. Conclusion  (COMPLIANT; certifies acceptance #6 un-loaded boot + #9 reload; adjacent concerns deferred)
```

### Integration Points

```yaml
REPORT (the deliverable):
  - create: "plan/006_862ee9d6ef41/architecture/gap_lifecycle.md (NEW, gap_*.md format)"
  - verdict: "✅ COMPLIANT — all 5 properties (a-e) + boot-VRAM/teardown-lock/mode-switch pass (daemon.py file:line)"
  - ties-to: "acceptance #6 (starts un-loaded, ~0 VRAM) + #9 (idle-unload → reload)"
CONSUMERS:
  - P1.M5.T5 (acceptance cross-check): "maps criteria #6/#9 to this audit's evidence"
  - future maintainers: "the reference for any _load_host/_handle_dead_host/boot-state change"
SCOPE GUARD:
  - git status: "ONLY architecture/gap_lifecycle.md (new). No voice_typing/*, no tests/*, no PRD/tasks/snapshot."
```

## Validation Loop

### Level 1: Re-verification (read the code — read-only)

```bash
cd /home/dustin/projects/voice-typing
# Re-locate the 4 lifecycle regions (line numbers may drift — re-grep):
grep -nE 'def _load_host|def _handle_dead_host|def _load_recorder|self._load_cond|self._loading|self._models_loaded = loaded|set_phase\("(loading|idle|unloaded)"\)|set_models_loaded\((True|False|loaded)\)|not self._host.is_alive|self._host = None' voice_typing/daemon.py
# Read each region (init ~648-671, _load_host ~698-795, run check ~840-846, _handle_dead_host ~874-903) and
# confirm (a)-(e) match PRD §4.2bis. Expected: COMPLIANT (research §2).
```

### Level 2: Test evidence (re-run the lifecycle slice — the audit's evidence)

```bash
cd /home/dustin/projects/voice-typing
# AGENTS.md Rule 1: inner timeout (mandatory) + outer bash timeout. Mocked CUDA → fast, but timeout is non-negotiable.
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or spawn or dead or unload or boot or unloaded'
# Expected: 43 passed, 176 deselected (record the actual count in the report).
```

### Level 3: Report well-formedness

```bash
cd /home/dustin/projects/voice-typing
# Confirm the report exists + has the required sections + cites file:line + records the verdict:
grep -nE '^# Gap Report|Bottom line|Compliance|43 passed|COMPLIANT|acceptance #6|acceptance #9' plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
# Expected: the title, the ✅ bottom line, the compliance table, the test count, the #6/#9 tie all present.
```

### Level 4: Scope guard (no unintended edits)

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY plan/006_862ee9d6ef41/architecture/gap_lifecycle.md (new). No voice_typing/*, no tests/*.
```

## Final Validation Checklist

### Technical Validation
- [ ] Re-verified the 4 lifecycle regions (init, _load_host, run check, _handle_dead_host) — all COMPLIANT.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or spawn or dead or unload or boot or unloaded'` → recorded pass count (baseline 43).
- [ ] `gap_lifecycle.md` exists with the 5 sections (scope/artifacts, compliance table, test evidence, nuances, conclusion).

### Feature (Audit) Validation
- [ ] Compliance table covers (a) boot state, (b) single-flight lock, (c) success transitions, (d) failure cleanup, (e) dead-host recovery — each COMPLIANT with daemon.py file:line.
- [ ] Boot-VRAM / teardown-lock / mode-switch points covered (the §4.2bis extras).
- [ ] Verdict ✅ COMPLIANT; conclusion ties to acceptance #6 + #9.
- [ ] If a real defect was found, it is fixed + recorded; otherwise "none — compliant per audit."

### Code Quality Validation
- [ ] Report mirrors the `gap_*.md` format (consistent with gap_daemon_loop.md).
- [ ] Non-defect nuances recorded (recorder→host, `_load_recorder` alias, M2.T3/S3/M3 deferrals) so they aren't mistaken for gaps.
- [ ] Only `architecture/gap_lifecycle.md` created (`git status --short`).

### Documentation & Deployment
- [ ] Report is self-contained (scope, method, evidence, verdict) — a future maintainer can re-run the audit from it.
- [ ] Adjacent concerns correctly deferred (drain → P1.M2.T1.S2; IPC → S2; teardown → S3; lite → M2.T3; status → M3).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/daemon.py` or any test — this is an AUDIT; the lifecycle is COMPLIANT (no defect). Edit ONLY if re-verification surfaces a real defect (Critical #1).
- ❌ Don't run pytest without `timeout 300` (inner) + the bash-tool timeout — AGENTS.md Rule 1 (the repo has hang vectors) (Critical #2).
- ❌ Don't assert compliance without file:line evidence — every table row must cite the daemon.py line(s) (Critical #3).
- ❌ Don't mistake the nuances for defects: `recorder`→`self._host` naming; `_load_recorder` alias; mode-switch/lite (M2.T3); teardown bound (S3); status VT-001/VT-002 (M3) (Critical #4).
- ❌ Don't append to `gap_daemon_loop.md` — that's the drain audit's home. Create the standalone `gap_lifecycle.md` (Critical #5).
- ❌ Don't stray into the drain / IPC / teardown-detail / lite / status audits — they belong to P1.M2.T1.S2 / S2 / S3 / M2.T3 / M3. This task owns §4.2bis lazy-load ONLY.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — `.venv/bin/python -m pytest` (Critical #6).