# PRP — P1.M1.T1.S1: Run and record the G1 baseline suite numbers

## Goal

**Feature Goal**: Produce the durable **G1 regression baseline** (PRD §4.2sexies R.7 G1) by re-running the **15 pure test suites** at pre-change HEAD and recording counts + failure names + one-line reasons to `tests/G1_BASELINE.md`. This is the reference every later change in this plan is diffed against — it must exist, be accurate, and be committed **before any code change**.

**Deliverable**: One new file, `tests/G1_BASELINE.md` (bounded — the results table, failure inventory, totals, commit hash; NO transcripts), plus a git commit containing only that file.

**Success Definition**: (a) all 15 suites ran, one file per call, each under `timeout 300` with the bash-tool timeout above it; (b) the recorded numbers **match the research record** (`plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md` Part A: **379 passed / 20 failed total**); (c) any drift is RECORDED and investigated as a finding — never "fixed" by a code change in this subtask; (d) only `tests/G1_BASELINE.md` is added; zero code/config changes; (e) the doc is committed alone.

## User Persona

**Target User**: The implementing agents of every later subtask in this plan (P1.M1.T2 onward) who must distinguish pre-existing legacy reds from NEW regressions — and the G1/G2 gates in PRD R.7 that require exactly this record.

**Use Case**: A later change touches `streaming.py`; the agent re-runs `test_streaming_commit.py`, sees 10 failures, and consults `tests/G1_BASELINE.md` to learn those 10 are pre-existing lazy-separator contract reds — not its regression.

**Pain Points Addressed**: No durable, in-repo baseline existed (the numbers lived only in a plan/ research doc) — later rounds couldn't separate legacy reds from new damage without re-deriving everything.

## Why

- **PRD R.7 G1 mandates it**: "record pre-change results of `test_streaming_commit`, `test_zero_diff_rewind`, key-listener, control-socket, and config suites; reconcile the legacy separator failures at HEAD … against the lazy-separator contract and separate them from NEW failures."
- **The research record already measured it** (at code-state 2335a9e): 379P/20F across 15 pure suites. This subtask re-runs, verifies reproducibility, and lands the numbers as an in-repo artifact.
- **Record-only by design**: this subtask changes NO code — the baseline must reflect pre-change truth. Classification of the 20 reds (legacy lazy-separator contract vs new) is the NEXT subtask (S2), not this one.
- **Safety discipline**: the excluded suites (real CUDA/model loads, shell E2E) are exactly the ones the repo AGENTS.md warns hang sessions — they are out of scope and must not be run untimed or at all here.

## What

Preflight (verify code state == 2335a9e), re-run the 15 suites exactly as the research doc did, compare against Part A, write `tests/G1_BASELINE.md` (bounded), commit only that file. No code, no config, no test edits.

### Success Criteria

- [ ] Preflight: `git diff 2335a9e --stat -- voice_typing/ tests/ config.toml` is EMPTY (HEAD `d78ff95` is plan-docs-only on top of `2335a9e`).
- [ ] All 15 files from the research doc's Part A table ran, one per call, `timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q` (+ `--tb=line` for reasons), bash-tool timeout ≥ 360.
- [ ] The EXCLUDED files were NOT run: `test_feed_audio.py`, `test_daemon.py`, `test_recorder_host.py`, `test_cuda_check.py` (contract-forbidden) and `test_systemd_unit.py` (not in the G1 15 — do not improvise it in).
- [ ] Recorded numbers match Part A (379P/20F; per-suite per the table); any drift recorded verbatim as a finding with investigation notes.
- [ ] `tests/G1_BASELINE.md` contains: commit hash, run date, the 15-row table (Passed/Failed/Runtime), totals, and the per-failure inventory (name + one-line reason) — bounded, no transcripts.
- [ ] Only `tests/G1_BASELINE.md` committed.

## All Needed Context

### Context Completeness Check

_Pass._ The 15-suite list, expected per-suite numbers, command template, exclusion list, and the drift rule are all below (transcribed from the verified research record). The implementing agent reads the research doc for the full failure inventory (items 1–20) rather than this PRP duplicating all 20 one-liners.

### Verified Current State (re-verified this session)

**Repo state:** HEAD = `d78ff95` ("Add task breakdown and architecture research") on top of `2335a9e` ("Add im-lab spike; resolve route to input-method-v2") — the plan-docs commit added NO code, so **the code state equals 2335a9e** (verify with the preflight diff). Tree noise under `plan/008_…` (orchestrator files) is expected and irrelevant.

**The 15 suites + expected numbers** (`plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md` Part A):

| # | File | Passed | Failed | Runtime |
|---|------|-------:|-------:|---------|
| 1 | tests/test_streaming_commit.py | 22 | **10** | ~0.1 s |
| 2 | tests/test_streaming_core.py | 32 | **2** | ~0.02 s |
| 3 | tests/test_streaming_freeze.py | 22 | **4** | ~0.02 s |
| 4 | tests/test_streaming.py | 3 | **4** | ~106 s (real small.en on wav fixtures) |
| 5 | tests/test_zero_diff_rewind.py | 3 | 0 | ~0.01 s |
| 6 | tests/test_key_listener.py | 32 | 0 | ~0.03 s |
| 7 | tests/test_control_socket.py | 27 | 0 | ~3.4 s |
| 8 | tests/test_config.py | 54 | 0 | ~0.03 s |
| 9 | tests/test_config_repo_default.py | 3 | 0 | ~0.01 s |
| 10 | tests/test_textproc.py | 31 | 0 | ~0.01 s |
| 11 | tests/test_typing_backends.py | 36 | 0 | ~0.8 s |
| 12 | tests/test_voicectl.py | 36 | 0 | ~2.9 s |
| 13 | tests/test_feedback.py | 38 | 0 | ~0.05 s |
| 14 | tests/test_prompt_engine.py | 28 | 0 | ~0.05 s |
| 15 | tests/test_context_prompt_refresh.py | 12 | 0 | ~0.02 s |
| | **Total** | **379** | **20** | |

**tests/ has 20 .py files** — the other 5 (`test_cuda_check.py`, `test_daemon.py`, `test_feed_audio.py`, `test_recorder_host.py`, `test_systemd_unit.py`) are NOT in the G1 15. The first four are contract-forbidden (real CUDA/model loads / hang vectors per repo AGENTS.md); `test_systemd_unit.py` is simply not part of the G1 set — do not run it either.

**Failure inventory:** research doc Part A.1 lists all 20 with name/line/one-line-reason/classification — (i) = known legacy lazy-separator contract red (tests encode the eager-separator contract; HEAD since `26d570b` defers it), (ii) = new/unclassified. **Classification analysis is S2's job** — this subtask RECORDS names+reasons only, using the doc's one-liners (or fresh `--tb=line` output where it agrees).

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: THE authority — Part A table (the 15 suites + expected numbers), Part A.1 (the failure
       inventory with one-line reasons), and the exact run methodology (command template, timeouts).
  critical: "Numbers must match this record. Drift = record + investigate + STOP (no code change)."
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: §4.2sexies R.7 gate G1 mandates this baseline; R.1-R.8 context for why separation of legacy
        reds from new failures matters for every later gate.
- file: AGENTS.md (repo root)
  why: The two-timeout discipline (inner `timeout` + bash-tool timeout above it) and the hang vectors
        (never run the daemon/voicectl/E2E untimed; CUDA suites load models for minutes).
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/          # HEAD d78ff95 == code-state 2335a9e
├── tests/                                    # 20 .py files; 15 are the G1 set (list above)
└── (tests/G1_BASELINE.md does NOT exist yet) # ← CREATE (the deliverable)
```

### Desired Codebase tree with files to be added

```bash
tests/G1_BASELINE.md    # NEW — the committed G1 baseline (table + totals + failure inventory)
# NOTHING ELSE. No code, no config, no test edits.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TWO TIMEOUTS ON EVERY RUN (repo AGENTS.md): inner `timeout 300` + bash-tool
# timeout ABOVE it (the research runs used 360). test_streaming.py alone takes ~106 s (real
# small.en on wav fixtures) — 300 s is the budget; do NOT lower it for that file.

# CRITICAL #2 — RUN EXACTLY THE 15. The excluded five: test_feed_audio/test_daemon/
# test_recorder_host/test_cuda_check (contract-forbidden, real CUDA/model loads) and
# test_systemd_unit (not in the G1 set). One FILE per call — no combined runs, no -k filters.

# CRITICAL #3 — RECORD-ONLY. Any drift from Part A (counts or failure names) is a FINDING:
# record it verbatim with your investigation notes in the doc, and STOP. Do not edit code,
# tests, or fixtures to "make numbers match" — S2 owns classification, later tasks own fixes.

# CRITICAL #4 — THE BASELINE IS PRE-CHANGE BY DEFINITION. If the preflight diff shows
# voice_typing/ tests/ config.toml changed since 2335a9e, STOP and report — the baseline would
# not be the pre-change record the plan needs.

# GOTCHA #5 — COMMIT DISCIPLINE. Stage ONLY tests/G1_BASELINE.md (the tree has expected
# plan/008_… noise from the orchestrator — never include it). The contract's OUTPUT explicitly
# requires a committed doc: `git add tests/G1_BASELINE.md && git commit -m "..."` with nothing
# else staged.

# GOTCHA #6 — BOUNDED DOC. Counts + names + one-line reasons + commit + date ONLY. No pytest
# transcripts, no full tracebacks (that is exactly the /tmp bloat discipline the repo mandates).

# GOTCHA #7 — FULL-PATH INVOCATION: /home/dustin/.local/bin/uv (zsh aliases python3/pip/uv).
# --tb=line gives the one-line reason per failure (the research methodology); -q keeps output small.
```

## Implementation Blueprint

### Data models and structure

None — this subtask adds a markdown artifact, no code.

### Implementation Tasks (ordered)

```yaml
Task 0: PREFLIGHT — verify the baseline is being taken at pre-change state.
  - RUN: git rev-parse HEAD && git diff 2335a9e --stat -- voice_typing/ tests/ config.toml
  - EXPECT: HEAD d78ff95 (or later plan-docs-only commit) and an EMPTY diff (code == 2335a9e).
    NON-EMPTY diff → STOP and report (Critical #4).

Task 1: RUN the 15 suites — one file per call, identical methodology to the research doc:
  - TEMPLATE: timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q --tb=line
    (bash-tool timeout >= 360 on every call).
  - RUN IN THIS ORDER (cheap first, the 106 s real-model file last):
    test_streaming_commit, test_streaming_core, test_streaming_freeze,
    test_zero_diff_rewind, test_key_listener, test_control_socket, test_config,
    test_config_repo_default, test_textproc, test_typing_backends, test_voicectl,
    test_feedback, test_prompt_engine, test_context_prompt_refresh, test_streaming.
  - CAPTURE per file: passed / failed counts, wall runtime, and (for failures) the test name
    + the --tb=line reason. Scratch notes only (do not write transcripts into the repo).

Task 2: COMPARE against the research record (Part A table + A.1 inventory).
  - EXPECT: 379 passed / 20 failed total; per-suite exactly as the table above.
  - MATCH → proceed to Task 3. DRIFT (any count or failure-name difference) → record it
    verbatim in the doc under a "Drift vs research record" heading with investigation notes
    (e.g. flaky test? environment? genuinely moved code?), and STOP after Task 3 (no fixes).

Task 3: WRITE tests/G1_BASELINE.md (bounded):
  - Header: "G1 regression baseline (PRD §4.2sexies R.7) — code-state <2335a9e> at HEAD <hash>,
    recorded <date>, methodology: timeout 300 uv run pytest <file> -q --tb=line, one file per call."
  - The 15-row results table (File | Passed | Failed | Runtime) + totals row (379 / 20).
  - Failure inventory: per failing file, each failure as `name (:line) — one-line reason`.
    Take one-liners from the research doc A.1 (they were captured with --tb=line); where your
    fresh output differs, prefer the fresh line and note it.
  - (If drift) the Drift section from Task 2. (If none) one line: "Matches
    plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md Part A exactly."
  - Footer: "Classification of these reds (legacy lazy-separator contract vs new) = P1.M1.T1.S2."

Task 4: COMMIT — stage and commit ONLY the doc:
  - git add tests/G1_BASELINE.md
  - git commit -m "P1.M1.T1.S1: record G1 regression baseline (15 suites, 379P/20F at 2335a9e code state)"
  - VERIFY: git show --stat HEAD lists exactly tests/G1_BASELINE.md.

Task 5: VALIDATE (gates below).
```

### Implementation Patterns & Key Details

```bash
# The whole task is a disciplined re-run + bounded transcription. The invariants:
#  (1) methodology parity with the research doc (same command, same per-file isolation) so the
#      numbers are comparable;
#  (2) pre-change state verified BEFORE running (Task 0);
#  (3) drift is a finding, never a fix;
#  (4) the commit contains exactly one file.
# One-off runtime note: only test_streaming.py is slow (~106 s, real small.en). Everything else
# is <4 s. Total wall time ~2.5 min of pytest.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS:
  - P1.M1.T1.S2 ("Classify reds vs the lazy-separator contract") works from THIS doc's failure
    inventory (the (i)/(ii) classification is its deliverable, recorded later).
  - P1.M1.T2/T3/T4 (merge + fixes) and P1.M3 (bulk controller) diff their post-change suite
    results against THIS baseline to prove "no new failures beyond the known 20".
  - P1.M7 graduation evidence references this doc as the G1 artifact.
NO CODE SURFACE CHANGES: nothing in voice_typing/, config.toml, or existing tests is touched.
```

## Validation Loop

> AGENTS.md two-timeout rule on every pytest invocation. `.venv` untouched; no daemon, no voicectl, no *.sh, no CUDA suites.

### Level 1: Preflight held (pre-change state)

```bash
cd /home/dustin/projects/voice-typing
git rev-parse --short HEAD
git diff 2335a9e --stat -- voice_typing/ tests/ config.toml | wc -l   # EXPECT: 0
# Also confirm tests/G1_BASELINE.md did not exist before this subtask: git log --oneline -- tests/G1_BASELINE.md | wc -l  # EXPECT: 0 (pre) / 1 (post-commit)
```

### Level 2: The doc exists and the numbers match the record

```bash
cd /home/dustin/projects/voice-typing
test -f tests/G1_BASELINE.md && echo "L2a PASS: doc exists"
grep -q "379" tests/G1_BASELINE.md && grep -q "20" tests/G1_BASELINE.md && echo "L2b PASS: totals present"
for f in test_streaming_commit test_streaming_core test_streaming_freeze test_streaming test_zero_diff_rewind test_key_listener test_control_socket test_config.py test_config_repo_default test_textproc test_typing_backends test_voicectl test_feedback test_prompt_engine test_context_prompt_refresh; do
  grep -q "$f" tests/G1_BASELINE.md || echo "L2 FAIL: $f missing from the doc"
done; echo "L2c checked all 15 files listed"
grep -qE "Drift|Matches .*d3_defects_g1_baseline" tests/G1_BASELINE.md && echo "L2d PASS: match/drift statement present"
# Expected: all PASS/checks silent. Cross-check at least the three known-red suites' counts:
grep -A2 "test_streaming_commit" tests/G1_BASELINE.md | head -5
```

### Level 3: Reproducibility spot-check (re-run one cheap suite, diff the count)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_zero_diff_rewind.py -q 2>&1 | tail -2
# Expected: "3 passed" — matches the doc row (0 failed). If it differs, the doc is stale or the
# tree moved mid-task: re-verify Task 0 before trusting anything.
```

### Level 4: Scope — only the doc added and committed

```bash
cd /home/dustin/projects/voice-typing
git show --stat HEAD | tail -3          # EXPECT: exactly tests/G1_BASELINE.md, 1 file changed
git diff --name-only HEAD~1 HEAD        # EXPECT: tests/G1_BASELINE.md only
git status --short | grep -vE 'plan/'   # EXPECT: empty (no code/config/test residue)
# Expected: all three hold. Any code/test/config file in the commit → L4 FAIL (record-only violated).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: HEAD is plan-docs-only over 2335a9e; `git diff 2335a9e -- voice_typing/ tests/ config.toml` empty.
- [ ] L2: doc exists; totals 379/20 present; all 15 files listed; match-or-drift statement present.
- [ ] L3: spot-check re-run of a cheap suite reproduces its recorded count.
- [ ] L4: the commit contains exactly `tests/G1_BASELINE.md`; no other file changed.

### Feature Validation
- [ ] Every suite ran under `timeout 300` with the bash-tool timeout above it; one file per call.
- [ ] The 5 excluded suites were not run (4 forbidden + systemd_unit not in the G1 set).
- [ ] Failure inventory has name + one-line reason for all 20 reds.
- [ ] Drift (if any) recorded verbatim with investigation notes — and NO code change made.

### Code Quality Validation
- [ ] Doc is bounded (no transcripts/tracebacks); methodology stated in the header.
- [ ] One-liners sourced from A.1 / fresh `--tb=line` where they agree.

### Scope Boundary Validation
- [ ] Zero changes to `voice_typing/`, `tests/*.py`, `config.toml`, scripts.
- [ ] Classification (S2), fixes (T2+), and ACCEPTANCE/README (P1.M7) untouched.

---

## Anti-Patterns to Avoid

- ❌ Don't run the forbidden suites (`test_feed_audio`/`test_daemon`/`test_recorder_host`/`test_cuda_check`) or any `tests/*.sh`, the daemon, or `voicectl` — hang vectors (repo AGENTS.md).
- ❌ Don't improvise `test_systemd_unit.py` into the set — the G1 15 is fixed by the research doc.
- ❌ Don't combine suites in one pytest call or use `-k` filters — one FILE per call, methodology parity with the research record.
- ❌ Don't "fix" drift with code/test edits — drift is a recorded finding; classification is S2, fixes are later tasks.
- ❌ Don't write transcripts or full tracebacks into the doc — bounded counts/names/reasons only.
- ❌ Don't skip the preflight — a baseline taken over changed code is worthless for the whole plan.
- ❌ Don't commit anything except `tests/G1_BASELINE.md` (the tree's `plan/008_…` noise is the orchestrator's).
- ❌ Don't drop the inner `timeout 300` or set the bash-tool timeout at/below it — the two-timeout rule is non-negotiable.

---

## Confidence Score

**9.5/10** for one-pass success. The task is a mechanical re-run + bounded transcription with the exact 15-file list, expected per-suite numbers, command template, and exclusion list all transcribed from the verified research record; the only slow file (test_streaming.py, ~106 s) is identified with its budget. The gates enforce pre-change state (L1), record parity (L2), reproducibility (L3), and the one-file commit (L4). The −0.5 is inherent flakiness risk in re-running suites (a count drift would be a legitimate finding, handled by Critical #3's record-and-stop path rather than failure).
