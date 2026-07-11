# PRP — P1.M1.T2.S2: Run full pytest fast suite regression (confirm green)

## Goal

**Feature Goal**: **Verify** (not implement) that the fast pytest suite is green on the post-`P1.M1.T1.S1` codebase — i.e., that the comment-only `config.toml` fix (commit `05fa62e`) caused zero regressions — and capture the pytest summary line as regression evidence. This is the pytest half of delta-PRD §6.2 ("the existing test suite still passes"); the bash-T4 half is the sibling `P1.M1.T2.S1`.

**Deliverable**: The pytest summary line (e.g., `265 passed in 5.31s`) as regression evidence, plus exit-code 0. **No code changes expected** — the only delta change was a TOML comment, which `tomllib` discards at parse time.

**Success Definition**:
- (a) The fast-suite command (below) exits 0 with ALL collected tests passing (no failures, no errors, no unexpected skips).
- (b) The summary line is captured as evidence (the task's output).
- (c) Zero source/test/config changes made by this subtask (regression evidence only).
- (d) If any test fails (it should not), the failure is investigated and **reported**, not papered over.

> **VERIFIED BASELINE (this PRP's research, 2026-07-11): `265 passed in 5.31s`, exit 0.** The contract's "197 passed in 1.59s" is a **stale** research-phase figure (it predates the bugfix changeset's + this delta's test growth). The current count is **265** — see Context §"Known Gotcha #1". The implementing agent re-confirms by running the command.

## User Persona

Not applicable. Internal regression gate, no user-facing surface (the contract §5 "DOCS: none — no user-facing/config/API surface change").

## Why

- **Delta-PRD §6.2 is the mandate**: "the existing test suite still passes." This subtask produces the pytest evidence for that criterion. (The `test_idle_and_gpu.sh` evidence is the sibling S1.)
- **A comment-only change is the lowest possible regression risk** — but the delta MUST still be certified, not assumed. TOML comments are discarded by `tomllib`, so parsed values are byte-identical; `test_config_repo_default.py` asserts parsed values, not comment text. The green run (265 passed) confirms this.
- **Cheap, deterministic, no GPU/mic/daemon.** The fast suite runs in ~5 s with no network and no model load. It is the right gate to run after any config/source touch.
- **Scope discipline.** This subtask runs the fast pytest suite ONLY. It does NOT run the heavy GPU tests (`test_feed_audio.py`, `e2e_virtual_mic.sh`, `test_idle_and_gpu.sh` — explicitly `--ignore`d), does NOT verify the bash T4 test (S1), and does NOT sync README (P1.M1.T3.S1).

## What

Run the fast pytest suite (8 modules, ignoring the 3 heavy GPU/shell tests) and confirm it is green. Capture the summary line. Report any failure rather than masking it.

The command (use FULL PATHS — this machine aliases `python3`→`uv run`):

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_feed_audio.py \
  --ignore=tests/e2e_virtual_mic.sh \
  --ignore=tests/test_idle_and_gpu.sh \
  --tb=short -v
```

### Success Criteria

- [ ] The command above exits **0**.
- [ ] pytest reports **`<N> passed`** with **0 failed / 0 errors** (N is the current collected count — **265** as of this PRP; see Gotcha #1).
- [ ] The summary line (`<N> passed in <s>s`) is captured as the regression-evidence output.
- [ ] No file under `voice_typing/`, `tests/`, `config.toml`, `README.md`, or `pyproject.toml` is modified by this subtask.
- [ ] If a failure occurs: root cause is investigated + reported (not hidden). Re-running in isolation (`pytest tests/<file>::<test> -v`) distinguishes order-pollution from a real defect.

## All Needed Context

### Context Completeness Check

_Pass._ This is a verification task. The exact command is given, the `--ignore` targets are confirmed to exist, the baseline (265 passed) is captured in this PRP's research, and the failure-triage decision tree is specified. A developer new to this codebase can run the gate and interpret the result from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the mandate for this regression + the count reconciliation
- docfile: plan/002_61d807f18dbe/P1M1T2S2/research/fast_suite_baseline_and_count_reconciliation.md
  why: "Records the VERIFIED passing run (265 passed in 5.31s, exit 0), the per-file test counts, WHY
        the contract's '197' is stale, why the comment-only change can't break tests (tomllib discards
        comments), the parallel-S1 no-conflict analysis, and the failure-triage decision tree."
  critical: "The '197 → 265' reconciliation is the load-bearing fact. Do NOT expect 197; expect the
            current collected count (~265). A count differing from 265 means a parallel task added/
            removed tests — investigate, don't assume regression."

# MUST READ — the delta mandate (§6.2 "the existing test suite still passes")
- docfile: plan/002_61d807f18dbe/delta_prd.md
  why: "§6.2 is the source: this subtask produces the pytest half of 'the existing test suite still
        passes'. §6.3 caps any permitted edit (none expected for the pytest half)."
  critical: "This is evidence-gathering. A green run = criterion met. No code change."

# The change under test — the comment-only fix (already committed)
- file: config.toml
  why: "Line 49 area: the hypr_notify comment had a stale 'partial/' reference; P1.M1.T1.S1 removed it
        (commit 05fa62e). Confirm with `git show 05fa62e -- config.toml` that the diff touches ONLY a
        comment line — a comment cannot affect parsed values, so it cannot break the fast suite."
  pattern: "test_config_repo_default.py asserts PARSED KEY VALUES (tomllib output), not comment text,
            so a comment edit is invisible to it. (Both of its tests passed in the baseline run.)"

# The sibling task (parallel) — confirms no overlap
- docfile: plan/002_61d807f18dbe/P1M1T2S1/PRP.md
  why: "P1.M1.T2.S1 is a verification-only task (certify test_idle_and_gpu.sh tolerates auto-stop) with
        ZERO file changes. It does NOT touch any pytest module, so it cannot change the count or outcome."
  critical: "S1 = bash T4 verification; S2 = pytest fast-suite regression. Fully independent. If a
            parallel task DID modify a test file, `git status` will show it — that's triage branch (c)."

# The PRD test plan (background — what the fast suite covers vs. the heavy tests)
- file: PRD.md
  why: "§6 defines T1 (test_feed_audio.py, IGNORED — GPU), T2 (textproc, in fast suite), T3
        (e2e_virtual_mic.sh, IGNORED — GPU/mic), T4/T6 (test_idle_and_gpu.sh, IGNORED — 120s+GPU).
        The fast suite = the hermetic, GPU-free modules: config, textproc, feedback, daemon, typing
        backends, voicectl, control socket."
  critical: "Do NOT run the ignored tests here — they need GPU cold init / a quiet room / a free GPU
            and are run explicitly/separately. Mixing them in risks false negatives and minutes of delay."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── config.toml                       # line ~49 hypr_notify COMMENT (the P1.M1.T1.S1 fix; committed 05fa62e)
├── tests/
│   ├── test_config.py                # 21 tests — in fast suite
│   ├── test_config_repo_default.py   #  2 tests — in fast suite (asserts parsed values, not comments)
│   ├── test_control_socket.py        # 19 tests — in fast suite
│   ├── test_daemon.py                # 116 tests — in fast suite (idle watchdog, toggle, CPU fallback, mic probe, ...)
│   ├── test_feedback.py              #  37 tests — in fast suite
│   ├── test_textproc.py              #  21 tests — in fast suite
│   ├── test_typing_backends.py       #  27 tests — in fast suite
│   ├── test_voicectl.py              #  22 tests — in fast suite
│   ├── test_feed_audio.py            # IGNORED (T1, GPU offline pipeline)
│   ├── e2e_virtual_mic.sh            # IGNORED (T3, shell, GPU+mic+tmux)
│   └── test_idle_and_gpu.sh          # IGNORED (T4/T6, shell, 120s+GPU) — sibling S1's subject
# FAST SUITE TOTAL: 265 tests (collected). All 8 in-suite modules are hermetic (no GPU/mic/network).
```

### Desired Codebase tree with files to be added/changed

```bash
# (NO changes) — verification-only subtask. The output is the captured pytest summary line (evidence),
# not a file edit. No file under voice_typing/, tests/, config.toml, README.md, or pyproject.toml is touched.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — THE COUNT IS 265, NOT 197. The contract's "197 passed in 1.59s" is a STALE research-phase
# figure. The bugfix changeset (mic-probe tests, on_final serialization, exit-code remap, ...) + this
# delta's test growth nearly doubled the suite. `pytest --collect-only` TODAY = 265. Expect ~265 (or the
# current count), NOT 197. If the count differs from 265, a parallel task added/removed tests — check
# `git status`; do NOT assume regression. (Verified baseline: 265 passed in 5.31s.)

# CRITICAL #2 — USE FULL PATHS. This machine aliases python3→uv run, pip→alias, tmux→zsh plugin. Invoke
# .venv/bin/python (and .venv/bin/pytest is fine too) explicitly. Never bare `python`/`pytest`/`uv`.

# CRITICAL #3 — IGNORE THE 3 HEAVY TESTS. test_feed_audio.py (T1 GPU), e2e_virtual_mic.sh (T3), and
# test_idle_and_gpu.sh (T4/T6) are explicitly --ignore'd. They need GPU cold init / a quiet room / a free
# GPU and are run separately/explicitly. Running them here risks false negatives + minutes of delay. The
# sibling S1 owns the T4 verification; this subtask owns the pytest fast suite ONLY.

# CRITICAL #4 — A COMMENT-ONLY CHANGE CANNOT BREAK TOML TESTS. tomllib discards comments at parse time, so
# the P1.M1.T1.S1 hypr_notify comment edit leaves all parsed KEY VALUES byte-identical. test_config_repo_
# default.py asserts parsed values → it is unaffected (both its tests passed in the baseline). If a config
# test DID fail, first check `git show 05fa62e -- config.toml` didn't accidentally touch a value (it didn't).

# GOTCHA #5 — TIMING VARIES; STATUS IS WHAT MATTERS. The baseline is ~5.3s (not the stale 1.59s — the suite
# grew). On a loaded machine it may be slower. The PASS/FAIL + count is the signal, not the seconds.

# GOTCHA #6 — IF A TEST FAILS, INVESTIGATE + REPORT; DO NOT "FIX" IT GREEN. This subtask's charter is
# regression EVIDENCE. A real failure must be surfaced. Decision tree (research note §6):
#   (a) order/isolation pollution → re-run the test alone; if green alone, it's an ordering bug (bugfix
#       changeset Issue 4 / P1.M2.T1 territory) — REPORT it, do not reorder here.
#   (b) comment fix altered a value → `git show 05fa62e -- config.toml` (it didn't; baseline is green).
#   (c) a parallel task touched a test/source → `git status` reveals it.
#   (d) env flake (real audio device leaked into a hermetic test) → re-run.
# The ONLY in-scope "fix" would be if the comment fix itself broke something — proven false by the green run.

# GOTCHA #7 — DO NOT run/restart the live systemd daemon or open a real mic. The fast suite is fully
# hermetic (mocked recorder/backend/pyaudio, monkeypatched cuda_check). Any real-audio/real-CUDA noise
# means a hermetic seam leaked — that's a bug to report, not a test environment to set up.

# GOTCHA #8 — `-v` vs `-q`. The contract specifies `-v --tb=short` (verbose: lists every test name — good
# for evidence). For just the clean summary line, `-q` (dots + `<N> passed in <s>s`) is enough. Both are
# acceptable; `-v` is the evidence-rich form, `-q` is the summary form.
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config. The only "structure" is the **regression verdict** (green summary line / exit 0) produced by running an existing command.

### Verification Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the codebase state + the --ignore targets (no mutation)
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- HEAD is the P1.M1.T1.S1 comment fix ---"
      git log --oneline -1
      echo "--- the comment fix touched ONLY a comment (no parsed value changed) ---"
      git show 05fa62e -- config.toml | sed -n '1,30p'
      echo "--- the 3 --ignore targets exist ---"
      for f in tests/test_feed_audio.py tests/e2e_virtual_mic.sh tests/test_idle_and_gpu.sh; do
          test -e "$f" && echo "exists: $f" || echo "MISSING: $f"
      done
      echo "--- no uncommitted source/test changes that would muddy the regression (S1 is zero-change) ---"
      git status --short
  - EXPECTED: HEAD = 05fa62e (the comment fix); the diff touches only the hypr_notify comment line; all
    3 ignore targets exist; git status shows no voice_typing/ or tests/ modifications (only plan/ + tasks.json
    orchestrator bookkeeping). If a tests/ or voice_typing/ file IS modified, a parallel task is in flight —
    note it (triage branch (c)) but the fast suite can still be run against the current tree.

Task 2: COLLECT — confirm the fast-suite count (set the correct expectation)
  - RUN:
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/ \
        --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh \
        --co -q | tail -3
  - EXPECTED: "<N> tests collected" where N is ~265 (this PRP's verified baseline). Per-file counts via:
      ... --co -q | grep -oE 'tests/test_[a-z_]+\.py' | sort | uniq -c
    match the table in Current Codebase tree. If N differs from 265, note it (a parallel task changed the
    suite) — the gate is still "all collected tests pass", whatever N is.

Task 3: RUN the fast suite (the deliverable) — capture the summary line
  - RUN (the contract command, evidence-rich -v form):
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/ \
        --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh \
        --tb=short -v 2>&1 | tee /tmp/vt_fast_suite.log | tail -5
      echo "exit=${PIPESTATUS[0]}"
    # (tee to a temp log so the full -v listing is preserved; only the tail is printed.)
  - EXPECTED: every test prints PASSED; the final line is "<N> passed in <s>s"; exit=0. (Baseline: 265
    passed in ~5.3s.) Capture that final summary line — it IS the deliverable.
  - CLEAN SUMMARY (optional, for a one-line evidence artifact):
      .venv/bin/python -m pytest tests/ \
        --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh \
        -q | tail -1

Task 4: RECORD the verdict
  - IF Task 3 exit=0 AND "<N> passed" with 0 failed/errors:
      Verdict = "FAST SUITE GREEN: <N> passed in <s>s (exit 0). Zero regressions from the P1.M1.T1.S1
      comment fix." Record the summary line as the task's regression-evidence output. ZERO file changes.
  - ELSE (one or more failures — should not happen):
      Run the failing test in isolation: `.venv/bin/python -m pytest tests/<file>::<test> -v --tb=long`.
      Apply the triage decision tree (research note §6 / Gotcha #6) to classify (order-pollution / value
      change / parallel-task edit / env flake). REPORT the failure + classification. DO NOT edit tests to
      force green. The only in-scope fix is a comment-fix-caused breakage, which the green baseline proves
      does not occur.
  - DO NOT: run the heavy GPU/shell tests (S1's job / separate), edit any file, sync README (P1.M1.T3.S1),
    or mask a failure.

Task 5 (OPTIONAL, only if a config test fails unexpectedly): re-confirm the comment fix is comment-only
  - RUN: git show 05fa62e -- config.toml
  - EXPECTED: the diff modifies ONLY the hypr_notify comment (removes "partial/"); no [key] = value line
    changes. tomllib discards comments → parsed config byte-identical → config tests must pass. (They do.)
  - This task is ONLY reached if a config test failed — which the baseline proves it won't.
```

### Implementation Patterns & Key Details

```bash
# This subtask has NO implementation patterns — it is a read-only regression run. The three load-bearing
# facts (each verified in this PRP's research note):
#
# FACT 1: the fast suite is 265 tests today (NOT the contract's stale 197). collect-only confirmed.
# FACT 2: all 265 pass in ~5.3s, exit 0 (baseline run, 2026-07-11, post P1.M1.T1.S1).
# FACT 3: a TOML comment edit cannot change parsed values (tomllib discards comments), so the comment-only
#         P1.M1.T1.S1 fix has no code path to break — the green run is the confirmation.
#
# THE COMMAND (the whole deliverable):
.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh \
  --tb=short -v
# Expect: <N> passed in <s>s, exit 0.
```

### Integration Points

```yaml
DELTA ACCEPTANCE (delta PRD §6.2 — "the existing test suite still passes"):
  - This subtask produces the pytest half of §6.2's evidence (the bash-T4 half is the sibling S1).
  - The captured summary line ("<N> passed", exit 0) IS the acceptance evidence. No repo file is modified.

PARALLEL — P1.M1.T2.S1 (bash T4 verification):
  - S1 is verification-only (ZERO file changes). It cannot change the pytest count or outcome. The two
    tasks are fully independent: S1 = test_idle_and_gpu.sh; S2 = pytest fast suite. No coordination needed
    beyond confirming (via `git status`) that no test/source file was modified in parallel.

DOWNSTREAM — P1.M1.T3.S1 (README changeset-level sync, Mode B):
  - This subtask changes no user-facing/config/API surface (contract §5 "DOCS: none"), so it imposes NO
    README edit. T3.S1's Mode-B sweep is unaffected by a green regression run.

NO INTERFACE / BEHAVIOR CHANGES:
  - voice_typing/, tests/, config.toml, README.md, pyproject.toml: UNCHANGED. The output is evidence.
```

## Validation Loop

> The Validation Loop here IS the task: the gates below are the steps to produce + verify the regression
> evidence. Full paths in every command (zsh aliases). All gates are hermetic (no GPU/mic/network).

### Level 1: The fast suite is green (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh \
  --tb=short -v 2>&1 | tee /tmp/vt_fast_suite.log | tail -6
echo "exit=${PIPESTATUS[0]}"
# Expected: the final line is "<N> passed in <s>s" (N≈265); exit=0; every test PASSED in the -v listing.
# THIS SUMMARY LINE IS THE DELIVERABLE. (Baseline: 265 passed in 5.31s, exit 0.)
```

### Level 2: The count matches the baseline (no surprise growth/shrinkage)

```bash
cd /home/dustin/projects/voice-typing
N=$(.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh \
  --co -q 2>/dev/null | grep -c '::')
echo "collected=$N  (baseline=265)"
[ "$N" -ge 260 ] && [ "$N" -le 270 ] && echo "L2 PASS: count near baseline (265)" || echo "L2 NOTE: count ($N) differs from 265 — a parallel task changed the suite; check 'git status' (not necessarily a regression)"
# Expected: ~265. A small drift is fine if a parallel task legitimately added/removed a test. A large swing
# or a DROP is a red flag — investigate before declaring green.
```

### Level 3: No heavy test ran (the ignores held) + no real GPU/mic was touched

```bash
cd /home/dustin/projects/voice-typing
echo "--- the heavy tests must NOT appear in the run log ---"
grep -cE 'test_feed_audio|e2e_virtual_mic|test_idle_and_gpu' /tmp/vt_fast_suite.log | xargs -I{} echo "heavy-test references in log: {} (expect 0)"
echo "--- exit code was 0 ---"
# (the exit=${PIPESTATUS[0]} from L1 must have printed 0)
# Expected: 0 references to the ignored heavy tests in the log (the --ignore flags held); exit 0.
```

### Level 4: The comment fix is confirmed comment-only (only if any config test failed — otherwise skip)

```bash
cd /home/dustin/projects/voice-typing
git show 05fa62e -- config.toml | grep -E '^[+-]' | grep -vE '^[+-]{3}|^[+-]#|^[+-]\s*#'
# Expected: EMPTY output (no [key] = value lines changed — only comment lines). If this is non-empty, the
# comment fix accidentally altered a value (the root cause of a config-test failure). It will be empty.
# (This gate is only informative if L1 was red; on a green L1, skip it.)
```

### Level 5: Scope guards — zero file changes; no S1/README/heavy-test work

```bash
cd /home/dustin/projects/voice-typing
echo "--- zero source/test/config changes from this subtask ---"
git status --short | grep -vE '^\?\? plan/|tasks\.json' || echo "(nothing outside plan/ + tasks.json)"
git diff --exit-code -- voice_typing/ tests/ config.toml README.md pyproject.toml && echo "L5 PASS: no source/test/config/README/pyproject changes" || echo "L5 FAIL: this subtask edited a file (it must not)"
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/002_61d807f18dbe/tasks.json plan/002_61d807f18dbe/prd_snapshot.md plan/002_61d807f18dbe/delta_prd.md .gitignore && echo "L5 PASS: read-only files unchanged" || echo "L5 NOTE: tasks.json may show orchestrator bookkeeping (M) — that is not this subtask's edit"
rm -f /tmp/vt_fast_suite.log
# Expected: git status shows ONLY plan/ (this subtask's PRP/research) + tasks.json (orchestrator); no
# voice_typing/tests/config/README/pyproject edits; read-only files unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: fast suite exits 0 with `<N> passed` (N≈265), 0 failed/errors — summary line captured (the deliverable).
- [ ] L2: collected count is near the 265 baseline (no unexplained drift).
- [ ] L3: the 3 heavy tests were ignored (no references in the run log); no real GPU/mic touched.
- [ ] L4 (only if L1 red): `git show 05fa62e -- config.toml` confirms comment-only (no value change).
- [ ] L5: zero source/test/config/README/pyproject changes; read-only files unchanged.

### Feature Validation
- [ ] The fast pytest suite is GREEN after the P1.M1.T1.S1 comment fix (the regression gate's purpose).
- [ ] The summary line (e.g., `265 passed in 5.31s`) is recorded as the delta §6.2 pytest evidence.
- [ ] Any failure (none expected) is investigated + reported via the triage tree, not masked.
- [ ] The stale "197" expectation is superseded by the actual count (~265).

### Code Quality / Scope Validation
- [ ] ZERO file modifications (voice_typing/, tests/, config.toml, README.md, pyproject.toml all unchanged).
- [ ] No heavy GPU/shell test run (they are `--ignore`d; T4 is the sibling S1's subject).
- [ ] No README sync (P1.M1.T3.S1); no test reordering/isolation "fixes" (bugfix changeset P1.M2.T1's scope).
- [ ] No conflict with parallel S1 (it is zero-change verification; `git status` confirms).

### Documentation & Deployment
- [ ] No user-facing/config/API surface change (contract §5 "DOCS: none").
- [ ] The regression evidence (summary line) is reflected in the task acceptance record.

---

## Anti-Patterns to Avoid

- ❌ Don't expect "197" — the suite is **265** today (the contract's figure is stale; the bugfix changeset + delta grew it). Use the current collected count. (Gotcha #1.)
- ❌ Don't run the heavy tests (`test_feed_audio.py`, `e2e_virtual_mic.sh`, `test_idle_and_gpu.sh`) — they are `--ignore`d for good reason (GPU cold init / quiet room / free GPU). They are run separately; T4 is the sibling S1's subject. (Gotcha #3.)
- ❌ Don't edit a test (or anything else) to make it green — this is regression EVIDENCE. A real failure must be reported via the triage tree. The only in-scope "fix" (comment-fix-caused breakage) is proven not to occur. (Gotcha #6.)
- ❌ Don't conflate "the suite is larger/slower than the stale 1.59s" with "a regression" — the suite grew to 265 tests; ~5s is the new normal. The PASS/FAIL status is the signal. (Gotcha #5.)
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases shadow them) — use `.venv/bin/python -m pytest`. (Gotcha #2.)
- ❌ Don't restart the live daemon or open a real mic — the fast suite is hermetic; any real-audio/CUDA noise means a hermetic seam leaked (a bug to report). (Gotcha #7.)
- ❌ Don't sync README here (P1.M1.T3.S1) or verify the bash T4 test (P1.M1.T2.S1) — stay in the pytest fast-suite lane.
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `delta_prd.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9.5/10** for one-pass verification success. This is a regression run whose outcome is already verified in this PRP's research: **`265 passed in 5.31s`, exit 0** (captured 2026-07-11 against the post-`05fa62e` tree). The command is the exact contract command with the three heavy tests `--ignore`d (all three targets confirmed to exist); the count is reconciled against the stale contract figure (197 → 265, with the per-file breakdown); and the failure-triage decision tree covers every "what if a test fails" branch without ever masking a real defect. The parallel sibling `P1.M1.T2.S1` is zero-change verification, so it cannot perturb the count or outcome. The −0.5 residual is purely the small chance of an environment flake (e.g., a real audio device leaking into a nominally-hermetic test) or a parallel task landing a test addition between this PRP and the implementer's run — both of which the triage tree + L2 count check handle deterministically (investigate, don't assume). No GPU, mic, daemon, or network is required.
