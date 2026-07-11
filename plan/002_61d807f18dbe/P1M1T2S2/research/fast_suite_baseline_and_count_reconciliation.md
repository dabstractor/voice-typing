# Research Note — P1.M1.T2.S2: Full pytest fast suite regression

**Task type:** verification / regression gate. No code changes expected. Deliverable = the pytest
summary line as evidence. This note records the verified run + the one load-bearing discrepancy.

## 1. The command (from the contract) — VERIFIED WORKING

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/ \
  --ignore=tests/test_feed_audio.py \
  --ignore=tests/e2e_virtual_mic.sh \
  --ignore=tests/test_idle_and_gpu.sh \
  -v --tb=short
```

All three `--ignore` targets EXIST (confirmed). They are the heavy GPU/mic tests run separately:
- `test_feed_audio.py` — T1 offline pipeline (GPU cold init, model load).
- `e2e_virtual_mic.sh` — T3 E2E (null-sink + tmux + real daemon).
- `test_idle_and_gpu.sh` — T4/T6 idle + GPU residency (120 s silence + nvidia-smi).

The fast suite = the 8 Python test modules NOT ignored.

## 2. CRITICAL DISCREPANCY — the count is 265, NOT the contract's 197

The contract research note says "197 tests … 1.59s". That figure is **STALE** — it predates the
bugfix changeset (001: mic probe tests, on_final serialization tests, exit-code remap tests, etc.)
and this delta's own test growth. `pytest --collect-only` today:

| test module | count |
|---|---|
| tests/test_config.py | 21 |
| tests/test_config_repo_default.py | 2 |
| tests/test_control_socket.py | 19 |
| tests/test_daemon.py | 116 |
| tests/test_feedback.py | 37 |
| tests/test_textproc.py | 21 |
| tests/test_typing_backends.py | 27 |
| tests/test_voicectl.py | 22 |
| **TOTAL** | **265** |

⇒ The PRP's success definition is "ALL collected tests pass (currently 265)", NOT "197". If the
implementer expects 197 and sees 265 they may wrongly suspect test pollution. The contract's "197"
must be explicitly superseded. (If the count differs from 265 at run time, a parallel task added/
removed tests — investigate, don't panic.)

## 3. Verified passing run (the evidence baseline) — 2026-07-11, post P1.M1.T1.S1 commit

```
$ .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py \
    --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh --tb=short -q
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 81%]
.............................................                            [100%]
265 passed in 5.31s
$ echo $?
0
```

**Result: 265 passed, exit 0.** Timing (~5.3s) is larger than the stale "1.59s" because the suite
nearly doubled in size; the PASS/FAIL status (not the exact seconds) is what matters.

## 4. Why the comment-only change (P1.M1.T1.S1) cannot break these tests

The only delta change is commit `05fa62e` — removing `partial/` from the `hypr_notify` COMMENT at
config.toml:49. TOML comments are discarded by `tomllib` at parse time, so parsed KEY VALUES are
byte-identical. `test_config_repo_default.py` asserts parsed values (not comment text), so it is
unaffected — and the green run confirms this (both of its tests pass). A comment-only change has
no code path to break.

## 5. Parallel-task coordination — NO conflict

`P1.M1.T2.S1` (parallel) is a **verification-only** task (certify `test_idle_and_gpu.sh` tolerates
auto-stop) that produces **ZERO file changes** (its verdict is "T4 passes, no modification needed").
It edits no test files, no daemon/config/ctl. ⇒ It cannot change the pytest count or outcome. The
two tasks are fully independent: S1 = bash T4 verification; S2 = pytest fast-suite regression.

## 6. Triage if a test FAILS (should not happen)

A failure here would indicate one of:
- (a) **Test-isolation / order dependence** (bugfix changeset Issue 4 territory). The suite is
  currently green in default order, so this would be a new pollution — re-run the failing test in
  isolation (`pytest tests/<file>::<test> -v`); if it passes alone, it's an ordering bug (report it,
  do not "fix" by reordering here — that's P1.M2.T1's scope in the bugfix changeset).
- (b) **The comment fix accidentally altered a config.toml VALUE** (not just a comment). Verify with
  `git show 05fa62e -- config.toml` — the diff must touch ONLY the comment line. If a value changed,
  that's the root cause (but it's already committed; the green run proves it didn't).
- (c) **A parallel task touched a test/source file** (S1 doesn't; but check `git status`).
- (d) **Environment flake** (e.g., a real audio device leaked into a hermetic test). Re-run.

In ALL failure cases: **investigate and report — do NOT edit tests to force green.** This subtask's
charter is regression EVIDENCE; a real failure must be surfaced, not hidden. The only "fix" within
scope would be if the comment fix itself broke something (it didn't — proven by the green run).
