# PRP — P1.M3.T1.S1: Audit `state.json` schema — all fields, phase lifecycle, mode field (feedback.py vs PRD §4.6)

## Goal

**Feature Goal**: Produce the authoritative **state.json schema audit** for `voice_typing/feedback.py` against PRD §4.6 — verifying the 6 contract checks (a)–(f): the 7 PRD fields, the boot lifecycle state, the `set_phase` values, the `mode` field, the `record_final` write-back-to-`partial`, and the `ts` wall-epoch clock. This is a **READ-ONLY AUDIT**: the deliverable is a gap report; NO source code is modified (the code is compliant — this PRP's research verified it; the audit re-confirms live).

**Deliverable** (ONE new artifact — a report, not code):
- `plan/006_862ee9d6ef41/architecture/gap_feedback.md` — a NEW standalone file in the established `gap_*.md` series (siblings: `gap_config.md`, `gap_textproc.md`, `gap_typing.md`, `gap_cuda_check.md`, `gap_daemon_loop.md`, `gap_lifecycle.md`, `gap_lite.md`, + the in-flight `gap_recorder_kwargs.md`). **Format mirrors `gap_lifecycle.md`** (title + date + scope + audited artifacts + bottom line + per-check findings w/ file:line evidence + non-defect nuances + "no source modified" closing).

**Success Definition**:
- (a) The report verifies all 6 contract checks against the LIVE `voice_typing/feedback.py` (re-grep + re-read — not trusting this PRP's verdict blindly) and records a ✅/❌ verdict + file:line evidence for each.
- (b) `.venv/bin/python -m pytest tests/test_feedback.py -q` is re-run live and the pass count is recorded in the report (the contract's mandated run command).
- (c) The 2 test-coverage nuances (record_final partial-write-back not asserted; boot phase/models_loaded values not explicitly asserted) are recorded as NON-DEFECTS so they are not mistaken for code gaps.
- (d) **No source files are modified** — `feedback.py` is compliant; the only new artifact is `gap_feedback.md`. `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_feedback.md` (new).
- (e) The report's scope is the SCHEMA only (the 6 checks) — NOT atomic-write/throttle/hyprctl-notify (that is P1.M3.T1.S2) and NOT the daemon's call sites (P1.M2.*, Complete).

> **VERIFIED VERDICT (this PRP's research): the feedback.py state.json schema is COMPLIANT — no code fix needed.** The audit's job is to re-confirm this live and document it with evidence + the 2 non-defect test-coverage nuances. If a check surprisingly fails on re-read, the report documents it as a real gap for a SEPARATE remediation task (this audit does not fix code).

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance-criteria cross-check) who needs an authoritative, file:line-evidenced record that `state.json` matches PRD §4.6 — so the external consumers (`status.sh`, `voicectl status`, the tmux status line) can trust the schema.

**Use Case**: A reviewer asks "does feedback.py emit all 7 PRD fields, with the right boot state + the record_final→partial write-back?" The report answers yes/no per check with the exact source lines.

**Pain Points Addressed**: Without this audit, a schema drift (a missing field, a boot state regression, a lost record_final→partial write-back) would be invisible until a consumer (tmux status line showing a stale partial) breaks. The audit pins the schema to PRD §4.6 with evidence.

## Why

- **PRD §4.6 is the contract for every external consumer.** `status.sh` reads `state.json` via jq (`listening`, `partial`); `voicectl status` renders `phase`/`models_loaded`/`mode`/`load_error`; the tmux status line depends on `partial` matching the screen (the record_final→partial write-back). A schema gap breaks all three. This audit proves compliance (or surfaces a gap) against the authoritative spec.
- **Closes the feedback audit area** (P1.M3.T1) the way the sibling audits closed theirs (gap_config/gap_textproc/gap_typing/gap_lifecycle/gap_lite). The verification round (006) produces one gap report per audit area; this is the feedback-schema one. P1.M3.T1.S2 (atomic-write/throttle/notify) is the OTHER half — this task is the SCHEMA only.
- **Read-only + parallel-safe.** The audit reads `feedback.py` + `tests/test_feedback.py` and writes one report under `architecture/`. The parallel P1.M2.T4.S1 (recorder kwargs) reads `daemon.py`/`config.py` and writes `gap_recorder_kwargs.md` — different files, different report, zero overlap. No source edits, so no conflict with any in-flight implementation task.
- **The research already did the work.** This PRP's research note pre-maps every check to its file:line + verdict, so the implementing agent re-verifies + writes the report in one pass (the value of a PRP: curated context, not open-ended exploration).

## What

A read-only verification of `voice_typing/feedback.py`'s `Feedback._state` schema + the 6 write-method semantics, re-confirmed live, then documented in `architecture/gap_feedback.md` (mirroring `gap_lifecycle.md`'s format). The 6 checks: (a) `_state` has the 7 PRD fields; (b) boot `phase='unloaded'` + `models_loaded=False`; (c) `set_phase` accepts the 5 lifecycle values; (d) `set_mode` publishes `normal`|`lite`; (e) `record_final` writes BOTH `last_final` AND `partial`; (f) `ts` uses `time.time()` (wall epoch). Plus the live test run + the 2 non-defect test-coverage nuances.

### Success Criteria

- [ ] `architecture/gap_feedback.md` exists with the title `# Gap Report — P1.M3.T1.S1: Feedback state.json schema vs PRD §4.6`.
- [ ] The report records a ✅/❌ verdict + `feedback.py` file:line evidence for each of the 6 checks (a–f).
- [ ] `.venv/bin/python -m pytest tests/test_feedback.py -q` is re-run live; its pass count is recorded in the report.
- [ ] The 2 test-coverage nuances (record_final partial-write-back not asserted; boot phase/models_loaded values not asserted) are documented as NON-DEFECTS.
- [ ] The report's scope is the schema (6 checks) ONLY — not atomic-write/throttle/notify (S2), not daemon call-sites (P1.M2.*).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_feedback.md` (new) — NO source files modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task nature (read-only audit → gap report), the deliverable path + the `gap_lifecycle.md` format template, the verified verdict (compliant) + the file:line evidence for all 6 checks, the 2 non-defect test-coverage nuances, the exact test command, and the scope boundaries (schema only; S2 owns throttle/notify; P1.M2.* owns daemon call-sites) are all pinned. The audit re-verifies live (re-grep + re-read + re-run) rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the 2 nuances + the format + scope
- docfile: plan/006_862ee9d6ef41/P1M3T1S1/research/feedback_schema_audit.md
  why: "§1 the deliverable location + the gap_lifecycle.md FORMAT template + 're-verify live' rule.
        §2 THE VERIFIED VERDICT: a 6-row table mapping each check (a-f) to its feedback.py file:line +
        ✅ COMPLIANT. §3 the 2 TEST-COVERAGE nuances (record_final partial-write-back not asserted;
        boot phase/models_loaded values not asserted) — NON-DEFECTS to record. §4 the test command.
        §5 scope (schema only; S2 = throttle/notify; P1.M2.* = daemon call-sites; read-only)."
  section: "ALL load-bearing. §2 (the verdict table), §3 (nuances), §1 (format/path)."

# MUST READ — the file being audited (the _state schema + the 6 write methods)
- file: voice_typing/feedback.py
  why: "AUDIT TARGET (read-only). _state dict L95-103 (7 fields). Boot: phase='unloaded'@97,
        models_loaded=False@98, mode='normal'@99. set_phase L122→@130. set_models_loaded L133→@142.
        set_mode L145→@150. record_final L153 (last_final@165 AND partial@166). set_listening L171.
        _write L219 (ts=time.time()@227; throttle clock=time.monotonic@116). snapshot L193→@202."
  critical: "RE-VERIFY by grep + read — do NOT trust the line numbers blindly (re-locate them live).
             The audit READS this file; it does NOT edit it (compliant code = no modification)."

# MUST READ — the test file (coverage to characterize in the 'non-defect nuances' section)
- file: tests/test_feedback.py
  why: "test_state_shape_has_the_documented_fields (125) — the 7-key set [covers (a)]. test_set_phase_round_trip
        (132) [covers (c)]. test_set_mode_writes_mode_field (138) — boot mode 'normal' + write [covers (d)].
        test_record_final_sets_last_final (146) — asserts last_final but NOT partial [the (e) nuance].
        test_update_partial_round_trip (117) — ts is a positive float [covers (f)]. test_initial_state_not_written_until_first_call
        (110) — lazy write. NO test explicitly asserts boot phase='unloaded'/models_loaded=False [the (b) nuance]."
  critical: "Characterize coverage as NON-DEFECTS (the code is correct; the tests could be stronger). Do NOT
             add tests in this audit (it only reports). Read-only."

# MUST READ — the gap-report FORMAT template (mirror its structure)
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "The format template. Structure: title (`# Gap Report — P1.Mx.Tx.S1: <area> vs PRD §X`) + Date +
        Scope (audited regions w/ file:line) + 'Audited artifacts (all read-only)' + 'Bottom line' (✅/❌)
        + §1 Method + per-property findings w/ file:line evidence + a 'non-defect nuances' section + the
        closing 'No source files were modified — the only new artifact is this report.' Mirror it."
  critical: "Mirror the structure EXACTLY (the verification round's reports are uniform). Cite feedback.py
             file:line for each check. Record the live pytest pass count. Re-verify live ('re-verified
             against the live tree')."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.6 Feedback: the state.json schema (`{listening, phase, models_loaded, mode, partial, last_final, ts}`)
        + 'record_final ALSO writes the finalized text back into the partial field' + the boot phases
        (unloaded/loading, models_loaded false) + mode (normal|lite, written on every arm/disarm). This is
        the authoritative spec each check is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.6 as the contract."

# CONTEXT — the parallel task (DISJOINT; confirms the gap-report convention)
- file: plan/006_862ee9d6ef41/P1M2T4S1/PRP.md
  why: "P1.M2.T4.S1 (IN PARALLEL) audits recorder kwargs (daemon.py/config.py) → architecture/gap_recorder_kwargs.md.
        It CONFIRMS the convention: 'a NEW standalone file... Format mirrors gap_lifecycle.md.' Different
        audited file + different report → zero overlap with this task."
  critical: "No conflict. This task = feedback.py → gap_feedback.md; P1.M2.T4.S1 = daemon.py/config.py →
             gap_recorder_kwargs.md."

# CONTEXT — the NEXT subtask (S2 owns throttle/notify; do NOT audit them here)
- docfile: plan/006_862ee9d6ef41/P1M3T1S2/PRP.md
  why: "P1.M3.T1.S2 audits atomic writes, throttling (>=10 Hz), and hyprctl notify events. This task (S1)
        is the SCHEMA only (the 6 checks). Do not duplicate S2's scope."
  critical: "Scope: schema (fields + write semantics) ONLY. Throttle/atomic/notify = S2."
```

### Current Codebase tree (state at P1.M3.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/feedback.py          # AUDIT TARGET (read-only — _state schema + 6 write methods)
├── tests/test_feedback.py            # AUDIT (characterize coverage; read-only)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_lifecycle.md              # FORMAT TEMPLATE (mirror its structure)
    └── gap_feedback.md               # <-- CREATE (the report; NEW file in the gap_*.md series)
# NO source files modified. The only new artifact is architecture/gap_feedback.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_feedback.md   # CREATE: the schema-audit gap report (mirrors gap_lifecycle.md).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT. The code is COMPLIANT (research §2). Do NOT modify feedback.py
#   or any source file. The ONLY new artifact is architecture/gap_feedback.md. If a check fails on
#   re-read, DOCUMENT it as a gap for a separate remediation task — do not fix it here. (Research §5.)

# CRITICAL #2 — RE-VERIFY LIVE; DON'T TRUST THE LINE NUMBERS BLINDLY. The research pre-maps each check
#   to feedback.py file:line, but the audit must re-grep + re-read the live tree (mirrors gap_lifecycle.md
#   "re-verified against the live tree"). Line numbers drift; the verdict must reflect the CURRENT file.
#   Re-run `grep -nE 'self\._state|def set_phase|def record_final|time\.time' voice_typing/feedback.py`.

# CRITICAL #3 — THE record_final→partial WRITE-BACK IS THE LOAD-BEARING CHECK (e). PRD §4.6: "record_final
#   ALSO writes the finalized text back into the partial field so the tmux status line matches the screen."
#   feedback.py record_final does BOTH (last_final @165 AND partial @166) — VERIFIED COMPLIANT. But the
#   test test_record_final_sets_last_final (146) only asserts last_final. Record the partial-write-back as
#   CODE-COMPLIANT + the missing test assertion as a NON-DEFECT nuance. (Research §2 check (e), §3 nuance 1.)

# CRITICAL #4 — ts IS time.time() (wall epoch), NOT time.monotonic(). feedback.py:227 `self._state["ts"] =
#   time.time()`. The THROTTLE clock is time.monotonic() (@116) — a SEPARATE mechanism. Do NOT conflate them
#   in check (f): ts=wall-epoch is correct (PRD §4.6 + feedback.py:75-76 comment). (Research §2 check (f).)

# CRITICAL #5 — SCOPE = SCHEMA ONLY. The 6 checks (fields + write semantics). Do NOT audit atomic-write
#   (tempfile+rename), throttling (>=10 Hz), or hyprctl notify events — that is P1.M3.T1.S2. Do NOT audit
#   whether the daemon CALLS set_phase/set_mode at the right moments — that is P1.M2.* (Complete).
#   feedback.py just PUBLISHES what it's told; this audit verifies the schema + the methods' write semantics.
#   (Research §5.)

# CRITICAL #6 — MIRROR gap_lifecycle.md's FORMAT. The verification round's gap reports are uniform: title +
#   Date + Scope + Audited artifacts (read-only) + Bottom line + §1 Method + per-check findings w/ file:line
#   + non-defect nuances + "No source files were modified." Do not invent a different structure. (Research §1.)

# GOTCHA #7 — THE 2 NON-DEFECT NUANCES MUST BE RECORDED (not hidden). gap_lifecycle.md records "non-defect
#   nuances so they are not mistaken for gaps." This audit's 2: (1) record_final partial-write-back not
#   asserted by test; (2) boot phase='unloaded'/models_loaded=False values not explicitly asserted. Both are
#   TEST-COVERAGE observations (code is correct). Recording them prevents a future auditor from re-flagging.
#   (Research §3.)

# GOTCHA #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest tests/test_feedback.py -q (never
#   bare python/pytest). mypy NOT installed — do NOT run it. ruff optional (/home/dustin/.local/bin/ruff).
#   The test suite is GPU-free (subprocess.run monkeypatched; time.monotonic mocked) — fast.
```

## Implementation Blueprint

### Data models and structure

Not applicable — no code, no data models. The "data" is the audit's findings table (6 checks → verdict + file:line), recorded in `gap_feedback.md`.

### Audit Tasks (ordered — read → verify → run → report)

```yaml
Task 1: RE-VERIFY the 6 checks against the LIVE feedback.py (read-only; re-grep + re-read)
  - RUN (from /home/dustin/projects/voice-typing):
      grep -nE 'self\._state|^    "(listening|phase|models_loaded|mode|partial|last_final|ts)"' voice_typing/feedback.py
      grep -nE 'def set_phase|def set_models_loaded|def set_mode|def record_final|def set_listening|def _write|def snapshot|time\.time\(\)|time\.monotonic\(\)' voice_typing/feedback.py
  - For each check (a)-(f), confirm the verdict + capture the CURRENT file:line (re-locate; do not trust
    this PRP's numbers blindly — Critical #2). Expected findings (research §2):
      (a) _state L95-103 has exactly the 7 PRD fields. ✅
      (b) boot phase='unloaded' + models_loaded=False (mode='normal'). ✅
      (c) set_phase(phase: str) writes _state['phase']; accepts any string (daemon-driven). ✅
      (d) set_mode(mode: str) writes _state['mode']; default 'normal'. ✅
      (e) record_final writes BOTH last_final AND partial. ✅ (the load-bearing one — Critical #3)
      (f) _write sets ts=time.time() (wall epoch); throttle clock is time.monotonic() (separate). ✅
  - DO NOT edit feedback.py. This is read-only.

Task 2: RUN the test suite (the contract's run command; record the pass count)
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q
  - EXPECTED: all pass (GPU-free; subprocess + monotonic mocked). Record the pass count + time in the report.
  - CHARACTERIZE coverage for the 2 nuances (read tests/test_feedback.py): test_record_final_sets_last_final
    (asserts last_final, NOT partial); no test explicitly asserts boot phase='unloaded'/models_loaded=False.
    (Research §3.) These are NON-DEFECTS (code is correct).

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_feedback.md (mirror gap_lifecycle.md's format)
  - FILE: plan/006_862ee9d6ef41/architecture/gap_feedback.md (NEW).
  - STRUCTURE (mirror gap_lifecycle.md — Critical #6):
      # Gap Report — P1.M3.T1.S1: Feedback state.json schema vs PRD §4.6
      **Date:** <today> (audit re-verified against the live tree)
      **Scope:** Audit voice_typing/feedback.py's Feedback._state schema + the 6 write-method semantics
      against PRD §4.6 on the 6 item checks (a)-(f). Audited regions: _state dict, set_phase, set_models_loaded,
      set_mode, record_final, set_listening, _write, snapshot (cite file:line). Subtask P1.M3.T1.S1 of round 006.
      **Audited artifacts (all read-only):** voice_typing/feedback.py + tests/test_feedback.py.
      **Bottom line:** ✅ All 6 checks (a)-(f) COMPLIANT (each w/ file:line evidence below). <N> passed in
      tests/test_feedback.py (re-ran live). Two non-defect test-coverage nuances recorded (§<nuances>).
      No source files modified — the only new artifact is this report.
      ## 1. Method  (grep + read + live re-run; cite the commands)
      ## 2. Findings — check (a)..(f)  (each: PRD clause → feedback.py file:line → ✅ verdict)
      ## 3. Non-defect nuances  (record_final partial-write-back not asserted; boot values not asserted)
      ## 4. Closing  (no source modified; schema is PRD §4.6-compliant)
  - ACCURACY: cite the LIVE file:line (from Task 1), not this PRP's numbers. Record the actual pytest count.
  - DO NOT: modify feedback.py/tests/PRD.md/any source; audit throttle/notify (S2); audit daemon call-sites (P1.M2.*).

Task 4: VALIDATE (no further file change — see Validation Loop)
  - gap_feedback.md exists w/ the right title + the 6-check table + the live pytest count + the 2 nuances.
  - git status --short shows ONLY the new report (no source modified). No git commit unless directed.
```

### Implementation Patterns & Key Details

```python
# PATTERN: each check → PRD clause → feedback.py file:line → ✅/❌ verdict (mirror gap_lifecycle.md's
# per-property findings). Example for check (e):
#   "(e) record_final writes BOTH last_final AND partial — PRD §4.6 'record_final ALSO writes the finalized
#   text back into the partial field.' feedback.py record_final (L153): self._state['last_final'] = text
#   (L165) AND self._state['partial'] = text (L166). ✅ COMPLIANT."
# (Use the LIVE line numbers from Task 1's grep.)

# PATTERN: non-defect nuances are recorded explicitly (gap_lifecycle.md §4 style) so they are not re-flagged:
#   "Nuance 1 (test coverage, NON-DEFECT): test_record_final_sets_last_final (test_feedback.py:146) asserts
#   last_final but not the partial write-back. The CODE is compliant (feedback.py:166 writes partial); only
#   the test assertion is thin. A future test task may add the assertion."

# GOTCHA: ts=time.time() @227 (wall epoch) is NOT the throttle clock (time.monotonic @116). Check (f) is
# about ts ONLY. Do not conflate. (Critical #4.)

# GOTCHA: re-verify live; line numbers drift. The report cites the CURRENT file:line. (Critical #2.)
```

### Integration Points

```yaml
AUDIT (read-only):
  - voice_typing/feedback.py: "READ — _state schema + 6 write methods (the audit target)"
  - tests/test_feedback.py: "READ — characterize coverage (the 2 non-defect nuances)"
REPORT (the deliverable):
  - create: "plan/006_862ee9d6ef41/architecture/gap_feedback.md (NEW; format mirrors gap_lifecycle.md)"
NO code/test/config changes:
  - feedback.py: UNCHANGED (compliant — read-only audit)
  - tests/test_feedback.py: UNCHANGED (characterized, not edited)
  - PRD.md: READ-ONLY (forbidden)
DOWNSTREAM:
  - P1.M5.T5 (acceptance cross-check): "consumes this report as the evidence that state.json matches PRD §4.6"
  - P1.M3.T1.S2 (next): "audits atomic-write/throttle/notify — disjoint from this schema audit"
```

## Validation Loop

> The audit's validation = re-run the test suite + verify the report exists w/ the right structure + git
> status shows only the new report. No code is compiled/edited (read-only). FULL PATHS (zsh aliases).

### Level 1: The audited file is unchanged (read-only guard)

```bash
cd /home/dustin/projects/voice-typing
echo "--- feedback.py NOT modified by this audit ---"
git status --porcelain voice_typing/feedback.py tests/test_feedback.py   # expect: empty (no modification)
```

### Level 2: The contract's test command (re-run live; record the count)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q
# Expected: all pass (GPU-free). Record the pass count + time in gap_feedback.md's Bottom line + §1.
```

### Level 3: The report exists with the required structure

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_feedback.md && echo "L3 report exists" || echo "L3 FAIL"
head -1 plan/006_862ee9d6ef41/architecture/gap_feedback.md   # expect: "# Gap Report — P1.M3.T1.S1: Feedback state.json schema vs PRD §4.6"
grep -cE '✅|COMPLIANT' plan/006_862ee9d6ef41/architecture/gap_feedback.md   # expect: >=6 (one per check (a)-(f))
grep -nE 'record_final.*partial|partial.*write-back|non-defect|nuance' plan/006_862ee9d6ef41/architecture/gap_feedback.md  # the (e) nuance recorded
grep -nE 'phase=.unloaded.|models_loaded.*False|boot.*not.*asserted' plan/006_862ee9d6ef41/architecture/gap_feedback.md    # the (b) nuance recorded
grep -nE 'time\.time|wall.epoch|ts ' plan/006_862ee9d6ef41/architecture/gap_feedback.md   # check (f) evidence
# Expected: the report has the title, a ✅ verdict for each of the 6 checks, both nuances, and the ts evidence.
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY the new report; no source modified ---"
git status --porcelain
# Expected: "?? plan/006_862ee9d6ef41/architecture/gap_feedback.md" (new) and NOTHING ELSE from this task.
#   Any M to voice_typing/feedback.py / tests/test_feedback.py / PRD.md = SCOPE VIOLATION (read-only audit).
echo "--- report scope = schema only (no throttle/notify/daemon-call-site audit) ---"
grep -cE 'throttle|atomic|hyprctl|notify|daemon.*call' plan/006_862ee9d6ef41/architecture/gap_feedback.md
# Expected: 0 (or only incidental mentions in the Scope's "out of scope" note) — throttle/notify = S2,
#   daemon call-sites = P1.M2.*. This audit is the SCHEMA (6 checks) only.
```

## Final Validation Checklist

### Technical Validation
- [ ] `git status --porcelain voice_typing/feedback.py tests/test_feedback.py` → empty (read-only).
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_feedback.py -q` → all pass; count recorded in the report.
- [ ] `architecture/gap_feedback.md` exists with the title `# Gap Report — P1.M3.T1.S1: Feedback state.json schema vs PRD §4.6`.
- [ ] The report has a ✅/❌ verdict + `feedback.py` file:line for each of the 6 checks (a)–(f).

### Feature Validation
- [ ] Check (a) 7 fields; (b) boot phase/models_loaded; (c) set_phase; (d) set_mode; (e) record_final→partial; (f) ts=time.time() — each verified live with evidence.
- [ ] The 2 non-defect nuances (record_final partial assertion; boot values assertion) are documented.
- [ ] The report cites the LIVE file:line (re-verified, not this PRP's numbers).

### Code Quality Validation
- [ ] The report mirrors `gap_lifecycle.md`'s structure (title + date + scope + audited artifacts + bottom line + method + findings + nuances + closing).
- [ ] Scope is the schema (6 checks) only — no throttle/notify (S2), no daemon call-sites (P1.M2.*).
- [ ] Read-only — no source modified.

### Documentation & Deployment
- [ ] `gap_feedback.md` is the only new artifact; it lands in the `architecture/gap_*.md` series.
- [ ] No README/ACCEPTANCE edits (item DOCS: none — internal schema).

---

## Anti-Patterns to Avoid

- ❌ Don't modify `feedback.py` or ANY source file — this is a READ-ONLY audit; the code is compliant (Critical #1).
- ❌ Don't trust this PRP's file:line numbers blindly — re-grep + re-read the live tree; cite the CURRENT lines (Critical #2).
- ❌ Don't conflate `ts` (time.time, wall epoch) with the throttle clock (time.monotonic) — check (f) is about `ts` ONLY (Critical #4).
- ❌ Don't audit throttle / atomic-write / hyprctl-notify — that's P1.M3.T1.S2 (Critical #5). This task is the SCHEMA (6 checks).
- ❌ Don't audit whether the daemon CALLS set_phase/set_mode at the right moments — that's P1.M2.* (Complete) (Critical #5).
- ❌ Don't hide the 2 test-coverage nuances — record them as NON-DEFECTS so they aren't re-flagged (Gotcha #7).
- ❌ Don't invent a report structure — mirror `gap_lifecycle.md` (the verification round's reports are uniform) (Critical #6).
- ❌ Don't write the report anywhere except `plan/006_862ee9d6ef41/architecture/gap_feedback.md` (the `gap_*.md` convention).
- ❌ Don't run `mypy` — not installed; pytest is the gate (Gotcha #8).
- ❌ Don't add tests in this audit — it only REPORTS coverage gaps; adding tests is a separate task (read-only).

---

**Confidence Score: 9.5/10** for one-pass success. The audit is read-only and the verdict is pre-established (compliant on all 6 checks, with file:line evidence in the research note); the deliverable's path + format are pinned to the established `gap_*.md` convention (confirmed by the parallel P1.M2.T4.S1 PRP's `gap_recorder_kwargs.md` instruction + the 7 existing siblings); the 2 non-defect nuances are identified; and the test command + validation greps are executable as written. The −0.5 reserves: the audit must re-verify live (line numbers can drift) and exercise judgment on the nuance wording — but the grep gates (6 ✅ verdicts; both nuances present; only the new report in git status; no source modified) catch structural/verdict regressions deterministically.