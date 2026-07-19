# PRP — P1.M5.T1.S1: Run pure-python unit tests (no CUDA) — green-gate + results doc

## Goal

**Feature Goal**: Execute the **9 pure-Python unit-test files** (config, textproc, typing_backends,
feedback, voicectl, control socket, status_sh, systemd — **~196 tests, zero CUDA**) and confirm they are
**GREEN**, diagnosing + fixing any failure (source OR test, classified by root cause) and re-running
until green, then emit a results document. This is the **pure-Python half of P1.M5.T1** (the
acceptance gate); the mocked-CUDA half (`test_daemon.py` + `test_recorder_host.py`) is the NEXT leaf
**P1.M5.T1.S2** and is explicitly OUT of scope here.

**Verified baseline (LIVE this PRP's research): the suite is already GREEN** —
`196 passed in 5.32s`, exit 0, run with the exact contract command. The 5.32s wall time confirms every
file is genuinely pure-Python (a CUDA/model load would add minutes). Per-file `--collect-only` counts
match the contract EXACTLY (34 / 3 / 21 / 27 / 38 / 32 / 21 / 5 / 15 = 196). The diagnosis/fix workflow
below is provided for the case where drift or a flaky run surfaces a failure at execution time.

**Deliverable** (1 artifact — CREATE; **NO source/test edit unless a test actually fails**):
- `plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md` — a results doc recording the exact command run,
  per-file + total pass counts + timing, the GREEN verdict, and (if any fix was applied) a per-fix table.
  No existing `test_results_*.md` in the plan tree — this PRP defines the format (the 16 sibling
  `gap_*.md` in `architecture/` are a different category: read-only compliance audits; this is a results
  doc, and unlike them, this item MAY edit source/test to fix a real failure).

**Success Definition**:
- (a) The 9-file suite passes: `196 passed` (±0), exit 0, re-verified LIVE at execution time.
- (b) If any test failed on first run, the failure was diagnosed (root-cause class identified), the
  correct locus fixed (source / test / committed drift-guard file), and the suite re-run green — with NO
  fix that weakens a guard or contorts source to match an over-eager test assertion.
- (c) `test_results_unit.md` exists at the work-item path, is self-contained, and records: the exact
  command (with both AGENTS.md timeouts), per-file counts, total + timing, verdict, and any fixes.
- (d) Scope respected: `test_daemon.py`, `test_recorder_host.py`, `test_feed_audio.py` were NOT added to
  this run (they belong to P1.M5.T1.S2 / P1.M5.T2.* — mocked-CUDA or real-model work).
- (e) No regression: the run touched ONLY the 9 in-scope files; no other test file was edited unless a
  shared source module it depends on was the genuine root cause of a failure.

## User Persona

**Target User**: Internal — the plan orchestrator + downstream leaves:
1. **P1.M5.T5.S1** (acceptance-criteria cross-check) consumes this item's GREEN verdict as evidence for
   Acceptance #1 ("T1–T4, T6 pass" — these pure-Python tests underpin the T2 textproc + the socket/
   voicectl/feedback/config contracts those acceptance criteria rest on).
2. **P1.M5.T1.S2** runs immediately after, against `test_daemon.py` + `test_recorder_host.py`; it relies
   on the PURE-Python modules (config/textproc/typing_backends/feedback/ctl/socket) this item just
   confirmed green, so a daemon test failure in S2 is cleanly attributable to daemon/recorder_host logic
   rather than to a dependency this item would have caught.
3. **Operators/reviewers** read `test_results_unit.md` as the signed-off evidence that the CPU-only
   logic layer is sound before the heavy CUDA/E2E gates.

**Use Case**: The compliance round (006) has finished auditing every module (16 `gap_*.md` reports).
This item is the EXECUTION gate that converts "the code matches the PRD on paper" into "the 196
pure-Python unit tests actually pass on this machine." Run it once; if green, record + done. If a drift
appeared since audit, fix it at the root and re-run.

**Pain Points Addressed**: (1) The 16 audits are static-read verdicts — this is the dynamic proof. (2)
A silent drift between audit and execution (e.g., a config.toml default changed) would otherwise surface
as a confusing failure deep in a CUDA test; this gate catches it early in 5 s. (3) Gives S2 a clean
"dependencies are green" baseline.

## Why

- **This is the cheap, fast, deterministic gate before the expensive ones.** 196 pure-Python tests in
  ~5 s vs. the CUDA/model suites (test_feed_audio, E2E, GPU-lifecycle) that take minutes and need the
  GPU. Catching a logic/drift regression here costs seconds; catching it in test_feed_audio costs minutes
  + a model load.
- **It separates concerns for S2.** `test_daemon.py` (193) + `test_recorder_host.py` (26) depend on the
  pure-Python modules this item covers. Confirming those green first means a daemon failure is the
  daemon's fault, not a downstream config/textproc/feedback/ctl/socket bug.
- **The suite is already green (verified).** So this item is low-risk: run, confirm, document. The
  value is the evidence artifact + the diagnosis playbook for the rare drift case — not heroic debugging.

## What

Run the 9-file pytest command with AGENTS.md two-timeout discipline; confirm 196 passed; if any failure,
classify (§ failure taxonomy below) → fix the correct locus → re-run until green; write
`test_results_unit.md`.

### Success Criteria

- [ ] `196 passed` (±0), exit 0, re-verified LIVE at execution (run BOTH timeouts: inner `timeout 120` +
      outer bash-tool `timeout` above 120).
- [ ] Per-file counts recorded in `test_results_unit.md` (config 34, config_repo_default 3, textproc 21,
      typing_backends 27, feedback 38, voicectl 32, control_socket 21, status_sh 5, systemd_unit 15).
- [ ] Any failure on first run was root-caused + fixed at the correct locus (source / test / committed
      drift-guard file) — NOT silenced by weakening a guard or contorting source.
- [ ] `test_daemon.py` / `test_recorder_host.py` / `test_feed_audio.py` NOT in this run (scope boundary).
- [ ] `test_results_unit.md` written to the work-item path, self-contained (command + counts + timing +
      verdict + fixes-if-any).

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the exact run command (two-timeout form), the verified baseline
(196 passed / 5.32s / exit 0, LIVE this round), the per-file coverage map (module + PRD ref + failure
locus), the 5-class failure taxonomy with the fix-decision rule, the scope boundaries, and a verbatim
`test_results_unit.md` scaffold. No inference required.

### Documentation & References

```yaml
# MUST READ — the verified baseline + the diagnosis playbook (THIS is the spec).
- file: plan/006_862ee9d6ef41/P1M5T1S1/research/unit_test_run_verification.md
  why: "§1 the LIVE-verified green baseline (196 passed / 5.32s / exit 0) + exact --collect-only counts.
        §2 the per-file coverage map (module under test + PRD ref + 'if it fails, look at →'). §3 the
        5-class failure taxonomy (collection/import, logic-assertion, drift-guard, env/fixture, flaky)
        with the fix-decision rule (PRD is source of truth; don't weaken guards; use _wait_for not sleep).
        §4 scope boundaries (test_daemon/recorder_host/feed_audio = OTHER leaves). §5 AGENTS.md two-timeout
        + full-venv-path rules. §6 the output-doc format precedent (none exists; this defines it)."
  critical: "The suite is GREEN now; the diagnosis workflow only fires if a drift/flake appears at
             execution. Drift-guard files (config_repo_default / status_sh / systemd_unit) READ committed
             files — a failure there means a committed file drifted, fix the FILE not the test."

# MUST READ — AGENTS.md (the repo's hard rules; this is a test-run item, the timeout rules bind directly).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on every non-trivial command), the hang-vectors table (pytest = `timeout 600
        uv run pytest <file>`; this set is pure-Python so 120 is ample but the discipline is identical),
        Rule 2 (never foreground the daemon — these tests don't need it), Rule 3 (bound scratch files)."
  critical: "zsh aliases python/pytest — ALWAYS `.venv/bin/python -m pytest`. Inner `timeout 120` + outer
             bash-tool `timeout` > 120. Exit 124 = wedged → diagnose, don't retry-blind."

# MUST READ (cross-ref, cite-don't-re-audit) — the 9 sibling gap reports that established each module is
# PRD-compliant. This item is the DYNAMIC proof of what they claimed statically.
- file: plan/006_862ee9d6ef41/architecture/gap_config.md        # config.py ↔ §4.5 (test_config 34 + repo_default 3)
- file: plan/006_862ee9d6ef41/architecture/gap_textproc.md       # textproc.clean ↔ §4.7/T2 (test_textproc 21)
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md         # typing_backends ↔ §4.3 (test_typing_backends 27)
- file: plan/006_862ee9d6ef41/architecture/gap_feedback.md       # feedback ↔ §4.6 (test_feedback 38)
- file: plan/006_862ee9d6ef41/architecture/gap_voicectl.md       # ctl ↔ §4.8 (test_voicectl 32)
- file: plan/006_862ee9d6ef41/architecture/gap_socket.md         # ControlServer ↔ §4.2#3 (test_control_socket 21)
- file: plan/006_862ee9d6ef41/architecture/gap_status_sh.md      # status.sh ↔ §4.6 (test_status_sh 5)
- file: plan/006_862ee9d6ef41/architecture/gap_systemd.md        # systemd unit ↔ §4.9 (test_systemd_unit 15)
  why: "Each maps a module to its PRD contract + the tests that pin it. If a test fails, the matching gap
        report tells you the PRD-intended behavior (the source of truth for the fix-decision rule)."

# MUST READ — the merged PRD (the spec the logic tests encode; the oracle for fix-decisions).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§4.5 (config schema — config tests), §4.7/T2 (textproc.clean 4-step), §4.3 (typing backends),
        §4.6 (feedback state/notify/throttle), §4.8 (voicectl exit codes 0/1/2), §4.2#3 (control socket
        protocol), §4.9 (systemd unit). When a logic assertion fails, the PRD value is the source of truth."

# External — pytest invocation / exit semantics (the run mechanics).
- url: https://docs.pytest.org/en/stable/reference/exit-codes.html
  why: "pytest exit codes: 0 = no failures; 1 = tests failed; 2 = interrupted (Ctrl-C) OR a usage/collection
        error; 5 = no tests collected. `timeout`'s 124 = the process was killed by the inner timeout
        (wedged) — distinct from pytest's own exit codes."
  critical: "exit 124 (timeout) is NOT a pytest failure — it means the suite wedged (a regression hung a
             socket/thread/fixture). Do NOT retry-blind; run the single suspected file under `timeout 60
             -vv` to localize."
```

### Current Codebase tree (relevant slice — state at P1.M5.T1.S1)

```bash
tests/
├── test_config.py                 (34) ┐
├── test_config_repo_default.py    ( 3) │
├── test_textproc.py               (21) │
├── test_typing_backends.py        (27) ├── IN SCOPE (this item): 196 pure-Python tests, GREEN (5.32s)
├── test_feedback.py               (38) │
├── test_voicectl.py               (32) │
├── test_control_socket.py         (21) │
├── test_status_sh.py              ( 5) │
├── test_systemd_unit.py           (15) ┘
├── test_daemon.py                 (193) ┐ OUT — P1.M5.T1.S2 (mocked CUDA: daemon core + recorder-host IPC)
├── test_recorder_host.py          ( 26) ┘
└── test_feed_audio.py             ( 9)   OUT — P1.M5.T2 (PRD T1: real recorder + CUDA models, minutes)
# Modules under test (all present, committed):
voice_typing/{config,textproc,typing_backends,feedback,ctl,daemon,cuda_check,prefetch,recorder_host}.py
voice_typing/status.sh   systemd/voice-typing.service   config.toml   install.sh   hypr-binds.conf
plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md    # ← OUTPUT (NEW; this item creates it)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md   # NEW — the results doc (the SOLE deliverable)
# (source/test files edited ONLY if a failure is genuinely root-caused to them — expected: none, suite is green)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (AGENTS.md) — TWO timeouts, no exceptions. Inner GNU `timeout 120` (the contract value) +
#   the bash tool's own `timeout` param set ABOVE 120 (e.g. 150). Exit 124 (timeout's kill) ≠ pytest's
#   exit codes; 124 means the suite WEDGED (a socket/thread/fixture regression) → localize with a single
#   file under `timeout 60 -vv`, do NOT retry-blind. (research §5; AGENTS.md Rule 1.)

# CRITICAL #2 (AGENTS.md) — zsh aliases `python`/`pytest`. ALWAYS `.venv/bin/python -m pytest` (full
#   venv path). Bare `python`/`pytest` may resolve to a zsh shim/wrapper. mypy is NOT installed — do NOT
#   run it; ruff is optional (/home/dustin/.local/bin/ruff). py_compile + pytest are the gates.

# CRITICAL #3 — drift-guard tests READ committed files. test_config_repo_default (3), test_status_sh (5),
#   test_systemd_unit (15) parse config.toml / status.sh / the systemd unit / install.sh / hypr-binds.conf
#   via pathlib. A failure here = a committed file drifted from spec → fix the FILE (the test is the
#   oracle), NOT the test. Never silence by weakening the guard.

# CRITICAL #4 — logic tests encode PRD values; the PRD is the source of truth. If test_config /
#   test_textproc / test_typing_backends / test_feedback / test_voicectl / test_control_socket assert a
#   value from PRD §4.5/§4.7/§4.3/§4.6/§4.8/§4.2#3 and the SOURCE drifted → fix SOURCE. If the assertion
#   is an over-specified implementation detail (NOT a PRD value) → fix the TEST. When unsure, read the
#   matching gap_*.md report (it states the PRD-intended behavior).

# CRITICAL #5 — voicectl quit reply has NO listening key; ctl.format_result branches on shutting_down
#   FIRST. If a voicectl test fails with a KeyError on 'listening' for the quit case, the SOURCE
#   (ctl.format_result) regressed the branch order. (From the plan-001 ctl.py contract.)

# CRITICAL #6 — control socket tests are hermetic. test_control_socket.py + test_voicectl.py spin up a
#   real `ControlServer(_StubDaemon())` on a `tmp_path` socket + set XDG_RUNTIME_DIR via
#   monkeypatch.setenv. They NEVER touch a real daemon or the real XDG_RUNTIME_DIR. Do NOT start the
#   daemon to "help" them (AGENTS.md forbids foregrounding it anyway).

# CRITICAL #7 — scope boundary. Do NOT add test_daemon.py (193) / test_recorder_host.py (26) /
#   test_feed_audio.py (9) to this run. They are P1.M5.T1.S2 (mocked CUDA) / P1.M5.T2.* (real models).
#   Mixing them in changes the timeout budget (CUDA suites take minutes) and blurs S1/S2 attribution.

# CRITICAL #8 — re-run a SINGLE failing file first. `timeout 60 .venv/bin/python -m pytest <file> -vv`
#   gives the full assertion diff fast; then re-run the full 9-file set to confirm no regression. Don't
#   iterate against the whole set.

# CRITICAL #9 — the suite is GREEN now (verified this round). The likely outcome is "196 passed, no fixes
#   applied." Do NOT invent fixes or refactor green code. Only touch source/test if a run at execution
#   time shows a real failure.
```

## Implementation Blueprint

### Data models and structure

N/A — no code models. The deliverable is one Markdown results doc. The only "data" is the test outcome
(pass counts + timing + optional fix table).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RUN the 9-file suite (AGENTS.md two-timeout discipline) — the gate.
  - RUN (from /home/dustin/projects/voice-typing):
      timeout 120 .venv/bin/python -m pytest \
        tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
        tests/test_typing_backends.py tests/test_feedback.py tests/test_voicectl.py \
        tests/test_control_socket.py tests/test_status_sh.py tests/test_systemd_unit.py -q
    (set the bash tool `timeout` to 150 — the outer backstop above the inner 120.)
  - EXPECT: `196 passed in ~5s`, exit 0. (Verified baseline this round: 196 passed / 5.32s / exit 0.)
  - IF exit 0 + 196 passed → go to Task 4 (write the results doc; "fixes: none").
  - IF exit 124 (timeout/wedged) → do NOT retry-blind; localize: run each file under
    `timeout 60 .venv/bin/python -m pytest <file> -q` to find the one that hangs; that file's
    fixture/thread is the regression → go to Task 2.
  - IF exit 1 (failures) or exit 2 (collection error) → go to Task 2 with the failing file(s).
  - DO NOT add test_daemon.py / test_recorder_host.py / test_feed_audio.py (scope boundary, CRITICAL #7).

Task 2: (ONLY IF a failure) DIAGNOSE — classify the failure, decide the fix locus.
  - RE-PRODUCE the failure verbosely on the single file: `timeout 60 .venv/bin/python -m pytest <file> -vv`
  - CLASSIFY (research §3 taxonomy):
      Class A — collection/import ERROR  → SOURCE module has a syntax/import bug. Fix SOURCE.
      Class B — logic ASSERTION failure   → read the diff; PRD-value assertion ⇒ fix SOURCE;
                                            over-specified impl-detail ⇒ fix TEST. (read the gap_*.md.)
      Class C — DRIFT-GUARD failure       → committed file (config.toml/status.sh/systemd unit/install.sh/
                                            hypr-binds.conf) drifted ⇒ fix the FILE, never the test.
      Class D — ENV/fixture (XDG/tmp_path/monkeypatch/capsys-capfd mismatch) ⇒ fix the TEST fixture.
      Class E — FLAKY/timing (socket round-trip / thread join) ⇒ add a `_wait_for(predicate, timeout=2.0)`
                                            poll helper (house pattern, test_control_socket.py); NO bare sleep.
  - RECORD the class + the decided locus (for the results doc's fix table).
  - DO NOT: weaken a guard to make it pass; contort source to match an over-specified test; add a bare
    sleep; or fix a file outside the 9-test dependency set unless a shared source module is the genuine root.

Task 3: (ONLY IF a failure) FIX + RE-RUN until green.
  - APPLY the fix at the locus chosen in Task 2.
  - RE-RUN the single file: `timeout 60 .venv/bin/python -m pytest <file> -vv` → must be green.
  - RE-RUN the FULL 9-file set (Task 1 command) → must be `196 passed`, exit 0 (confirm no regression).
  - IF a fix changes a shared source module (config.py/feedback.py/etc.), the full-set re-run is the
    regression check — it must stay 196 passed.
  - RECORD the fix in the results doc (file | change | class | test unblocked).

Task 4: WRITE plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md (the SOLE deliverable).
  - CREATE the file (NEW; no existing test_results_*.md). Use the verbatim scaffold in "Task 4 SOURCE".
  - CONTENT: exact command run (both timeouts), per-file counts, total + timing, verdict (GREEN), and the
    fixes table (empty / "none applied" if the suite was green on first run).
  - PLACEMENT: plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md (keeps the artifact with its work item).
  - DO NOT edit PRD.md / tasks.json / prd_snapshot.md / .gitignore. DO NOT touch source/tests if green.

Task 5: (NONE if green) — no source/test changes, no new tests. This is an execution + documentation item.
```

#### Task 4 SOURCE — `test_results_unit.md` verbatim scaffold (pre-fill the LIVE counts; edit the timing/fixes at execution)

```markdown
# Test Results — P1.M5.T1.S1: pure-Python unit tests (no CUDA)

**Date:** <YYYY-MM-DD>
**Scope:** the 9 pure-Python unit-test files (config, textproc, typing_backends, feedback, voicectl,
control socket, status_sh, systemd). **Excludes** test_daemon.py / test_recorder_host.py (P1.M5.T1.S2,
mocked CUDA) and test_feed_audio.py (P1.M5.T2, real CUDA models).
**Verdict:** ✅ GREEN — 196 passed, 0 failed, 0 errors, 0 skipped.

## Command run (AGENTS.md two-timeout discipline)

```bash
timeout 120 .venv/bin/python -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_feedback.py tests/test_voicectl.py \
  tests/test_control_socket.py tests/test_status_sh.py tests/test_systemd_unit.py -q
# (bash-tool outer `timeout` set to 150 — the backstop above the inner 120.)
```

## Per-file results

| file | tests | result | module under test | PRD ref |
|---|---|---|---|---|
| test_config.py | 34 | ✅ pass | voice_typing.config | §4.5 |
| test_config_repo_default.py | 3 | ✅ pass | config.toml ↔ dataclass drift guard | §4.5 |
| test_textproc.py | 21 | ✅ pass | voice_typing.textproc.clean | §4.7 / T2 |
| test_typing_backends.py | 27 | ✅ pass | voice_typing.typing_backends | §4.3 |
| test_feedback.py | 38 | ✅ pass | voice_typing.feedback | §4.6 |
| test_voicectl.py | 32 | ✅ pass | voice_typing.ctl | §4.8 |
| test_control_socket.py | 21 | ✅ pass | voice_typing.daemon.ControlServer | §4.2#3 |
| test_status_sh.py | 5 | ✅ pass | voice_typing/status.sh | §4.6 |
| test_systemd_unit.py | 15 | ✅ pass | systemd/voice-typing.service + install.sh + hypr-binds.conf | §4.9 |
| **TOTAL** | **196** | **✅ all pass (~5s)** | | |

## Fixes applied

_None._ The suite was green on first run (196 passed in ~5.3s, exit 0). No source or test file was
modified. (If a failure had surfaced, record it here as: `file | change | root-cause class (A-E) |
test unblocked`.)

## Notes

- Wall time ~5s confirms every file is genuinely pure-Python (a CUDA/model load would add minutes).
- Drift guards (config_repo_default / status_sh / systemd_unit) READ committed files — green = no drift
  between audit and execution.
- Out of scope (other leaves): test_daemon.py (193) + test_recorder_host.py (26) → P1.M5.T1.S2;
  test_feed_audio.py (9) → P1.M5.T2.
```

### Implementation Patterns & Key Details

```python
# The fix-decision rule (when a logic assertion fails — Class B):
#   1. Does the assertion encode a PRD value (§4.5/§4.7/§4.3/§4.6/§4.8/§4.2#3)?
#        YES → the SOURCE drifted from the PRD → fix SOURCE. (the matching gap_*.md states the intent)
#        NO  → the test over-specified an implementation detail → fix the TEST.
#   2. For a DRIFT GUARD (config_repo_default / status_sh / systemd_unit): the test IS the oracle;
#      a committed file drifted → fix the FILE, never weaken the guard.
#   3. Never: silence a guard, contort source to an over-eager assertion, or add a bare sleep.

# The timeout-exit decision tree:
#   exit 0  + 196 passed → GREEN, write doc (fixes: none).
#   exit 1  (FAILURES)   → Task 2 (diagnose single file -vv) → Task 3 (fix + re-run full set).
#   exit 2  (COLLECTION) → a module won't import → Class A → fix the SOURCE module, re-run.
#   exit 124 (TIMEOUT)   → wedged → localize per-file under `timeout 60 -vv` → Class E fixture/thread
#                           regression → fix with _wait_for, not sleep; do NOT retry-blind.
```

### Integration Points

```yaml
CONSUMES (read-only):
  - tests/{test_config,test_config_repo_default,test_textproc,test_typing_backends,test_feedback,
           test_voicectl,test_control_socket,test_status_sh,test_systemd_unit}.py   # the 9 files (run)
  - voice_typing/* + systemd/voice-typing.service + config.toml + install.sh + hypr-binds.conf       # modules under test (read/exec)
  - plan/006_862ee9d6ef41/architecture/gap_*.md (8 sibling audits — the PRD-intent oracle for fix-decisions)
  - plan/006_862ee9d6ef41/prd_snapshot.md (§4.2#3/§4.3/§4.5/§4.6/§4.7/§4.8/§4.9 — the spec)

PRODUCES (the SOLE output):
  - plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md   # NEW results doc (GREEN verdict + counts + fixes-if-any)

FEEDS (downstream consumers):
  - P1.M5.T1.S2 (test_daemon.py + test_recorder_host.py)  # relies on this item's "dependencies green" baseline
  - P1.M5.T5.S1 (acceptance cross-check)                  # consumes the GREEN verdict as Acceptance-#1 evidence

PARALLEL-SAFE:
  - P1.M4.T4.S1 (hypr-binds audit, in flight) = ZERO overlap. It writes architecture/gap_hypr_binds.md
    (read-only); this item reads/runs test_systemd_unit.py (which PINS hypr-binds.conf). If hypr-binds.conf
    is unchanged at execution, test_systemd_unit stays green (it's in this set; verified). No file conflict.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown doc — validate structure, not code.
test -f plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md && echo "EXISTS"
grep -q 'P1.M5.T1.S1' plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md && echo "titled"
grep -qi 'GREEN'      plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md && echo "verdict present"
grep -q '196'         plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md && echo "total recorded"
# Expected: EXISTS; title + GREEN verdict + total 196 present. (No code to lint/type-check; mypy absent.)
```

### Level 2: Unit Tests (Component Validation) — THE gate

```bash
# Re-run the 9-file suite LIVE (two timeouts per AGENTS.md Rule 1):
timeout 120 .venv/bin/python -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_feedback.py tests/test_voicectl.py \
  tests/test_control_socket.py tests/test_status_sh.py tests/test_systemd_unit.py -q
# (set the bash tool `timeout` to 150 — the outer backstop above the inner 120.)
# Expected: `196 passed in ~5s`, exit 0. Record the ACTUAL count + timing in test_results_unit.md
# (do not copy this PRP's 5.32s verbatim — re-measure at execution).
```

### Level 3: Integration Testing (System Validation)

```bash
# Per-file isolation (sanity that no file is individually broken / slow):
for f in test_config test_config_repo_default test_textproc test_typing_backends test_feedback \
         test_voicectl test_control_socket test_status_sh test_systemd_unit; do
  timeout 60 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1
done
# Expected: each line shows its file's pass count (34/3/21/27/38/32/21/5/15), exit 0, each <1s.
# (NO daemon / NO CUDA / NO mic — these are pure-Python + mocked-subprocess. Do NOT start the daemon.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Scope-boundary guard: confirm the OUT-of-scope files were NOT silently added (they'd blow the budget):
timeout 125 .venv/bin/python -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_feedback.py tests/test_voicectl.py \
  tests/test_control_socket.py tests/test_status_sh.py tests/test_systemd_unit.py --co -q \
  | tail -1   # expect "196 tests collected"
# Import-purity spot-check (these modules must not pull CUDA at import):
.venv/bin/python -c "
import sys
import voice_typing.config, voice_typing.textproc, voice_typing.typing_backends
import voice_typing.feedback, voice_typing.ctl, voice_typing.daemon
bad=[m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
print('CUDA-at-import leak:', bad or 'none')
assert not bad, 'a pure-Python module imported CUDA — would slow/break this set'
"
# Expected: 196 collected; no CUDA module imported by the pure-Python layer.
```

## Final Validation Checklist

### Technical Validation

- [ ] `196 passed` (±0), exit 0, re-verified LIVE at execution (inner `timeout 120` + outer bash backstop).
- [ ] Per-file counts recorded (34/3/21/27/38/32/21/5/15 = 196).
- [ ] `test_results_unit.md` exists at the work-item path; title + GREEN + total present.
- [ ] No CUDA import leaked into the pure-Python layer (Level 4 spot-check).

### Feature Validation

- [ ] All success criteria from "What" section met.
- [ ] Any failure was root-caused (class A–E) + fixed at the correct locus (not silenced/contorted).
- [ ] Scope respected: test_daemon.py / test_recorder_host.py / test_feed_audio.py NOT in the run.
- [ ] If a fix changed a shared source module, the full 9-file set re-run green (no regression).

### Code Quality Validation

- [ ] `test_results_unit.md` is self-contained (command + counts + timing + verdict + fixes).
- [ ] Re-measured timing recorded (not copied from this PRP's 5.32s).
- [ ] No green code refactored/invented; source/test touched ONLY on a real failure.

### Documentation & Deployment

- [ ] Results doc placed at `plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md`.
- [ ] Feeds P1.M5.T1.S2 (dependencies-green baseline) + P1.M5.T5.S1 (Acceptance-#1 evidence).

---

## Anti-Patterns to Avoid

- ❌ Don't run with a single timeout or no timeout — AGENTS.md Rule 1 mandates inner `timeout` + outer
  bash-tool `timeout`; exit 124 (wedged) must be diagnosable, not swallowed.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — always `.venv/bin/python -m pytest`.
- ❌ Don't add test_daemon.py / test_recorder_host.py / test_feed_audio.py — they're other leaves (S2/T2);
  mixing them in blows the timeout budget + blurs attribution.
- ❌ Don't silence a drift-guard failure by weakening the test — fix the drifted committed file.
- ❌ Don't contort source to match an over-specified test assertion — the PRD value is the oracle (read
  the gap_*.md); fix the test if it over-specified an impl detail.
- ❌ Don't add a bare `sleep` to fix a flaky socket/thread test — use the `_wait_for(predicate, timeout)`
  house pattern (test_control_socket.py).
- ❌ Don't start the daemon / arm the mic / touch real XDG_RUNTIME_DIR — these tests are hermetic
  (ControlServer+_StubDaemon on tmp_path; monkeypatched XDG). AGENTS.md forbids foregrounding the daemon.
- ❌ Don't edit PRD.md / tasks.json / prd_snapshot.md / .gitignore.
- ❌ Don't copy this PRP's 5.32s timing into the results doc verbatim — re-measure LIVE at execution.
- ❌ Don't refactor or "improve" green code — this is an execution + documentation item; touch source/test
  ONLY on a real, root-caused failure.

---

## Confidence Score

**9/10** — one-pass success likelihood. The suite is ALREADY green (verified LIVE this round: 196 passed
/ 5.32s / exit 0 with the exact contract command), per-file counts match the contract exactly, and the
deliverable is a single self-contained Markdown doc with a verbatim scaffold. The diagnosis/fix playbook
(CRITICAL #3–#5 + Task 2 taxonomy) covers the rare drift/flake case at execution. Residual -1: a drift
could appear between this research and the implementing agent's run (e.g., a config.toml default
changed) — but the playbook resolves any such failure in one classify→fix→re-run cycle, and the
drift-guard tests pinpoint the exact file.