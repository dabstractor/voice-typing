# PRP — P1.M1.T1.S2: Test concurrent stop() calls share ONE teardown

## Goal

**Feature Goal**: Add a fast, hermetic pytest **regression test** proving `RecorderHost.stop()` is **single-flight under `_stop_lock`**: two concurrent callers share exactly ONE process-group teardown (one `os.killpg`), not two. This is the committed proof for S1's fix (P1.M1.T1.S1) and the `RecorderHost`-level piece of bugfix **Issue 1** — the SIGTERM race where `request_shutdown()` (signal thread) + `shutdown()` (main-thread finally) both call `host.stop()` concurrently and, without serialization, each runs its own multi-second join+SIGKILL, blowing systemd's 15s `TimeoutStopSec`.

**Deliverable**: One new test function — `test_concurrent_stop_calls_share_one_teardown(monkeypatch)` — plus its inner `_SlowProc` fake, appended to `tests/test_recorder_host.py` (currently 317 lines / 20 tests → becomes 21). No other file is touched (the S1 mutation-validation is transient + git-restored, never committed). This is a **test-only** subtask: no CUDA, no models, no real child process, no network — it runs in ~0.6s.

**Success Definition**:
- (a) `.venv/bin/python -m pytest tests/test_recorder_host.py -v` collects **21 tests** (20 existing + the 1 new) and **all pass** against the current S1-applied `recorder_host.py`.
- (b) The new test drives two concurrent `host.stop()` callers (via `threading.Thread` ×2 + a `Barrier`) with a `_SlowProc` fake that forces the join→`_terminate_group` path, and asserts: both threads finish within `< 2.0s`; `os.killpg` is called **exactly once** (the single-flight proof); `host._proc is None`; `host._dead is True`; no thread raised.
- (c) `os.getpgid` and `os.killpg` are monkeypatched (`recorder_host.os.*`) so no real process is signaled and no `ProcessLookupError` escapes.
- (d) **The test actually guards**: a transient one-line mutation defeating `_stop_lock` (`with self._stop_lock:` → `if True:`) turns the new test RED (`killpg` called twice), verified then restored via `git checkout`. The test is NOT a vacuous pass.
- (e) `git diff --name-only` == `tests/test_recorder_host.py` (the mutation left no trace).

## User Persona

**Target User**: The maintainer (human or AI agent) of `RecorderHost`/the daemon shutdown path — anyone who might later refactor `stop()`, remove or move the `_stop_lock`, or change the guard placement. The test fails the build before such a change can re-open the SIGTERM double-teardown race.

**Use Case**: A future edit to `recorder_host.py` (e.g. "cleaning up" the lock, moving the `if self._proc is None` guard back outside the with-block, or swapping `Lock` for something non-serializing). The test runs in the normal pytest suite and fails, forcing a conscious decision rather than a silent regression.

**Pain Points Addressed**: Issue 1 shipped precisely because no test exercised CONCURRENT `host.stop()` callers — the existing stop tests (`test_stop_is_noop_when_no_process`, `test_stop_with_dead_process_is_noop`) are single-caller. This test removes that blind spot and locks in S1's invariant.

## Why

- **Closes the coverage gap that let Issue 1 ship.** The architecture note (`test_infrastructure.md`) explicitly lists "SIGTERM concurrent teardown" as a gap: only single-threaded `request_shutdown_*`/`shutdown_*` tests existed. S1 added the lock; S2 adds the proof. Without S2, S1's correctness is an unverified claim.
- **Concurrency tests are notoriously vacuous.** A naive two-thread test can pass whether or not the lock works (e.g. if threads don't actually contend, or if the assertion is too weak). S2 is designed so the `_SlowProc.join(0.3s)` + `Barrier` make contention deterministic, AND the `killpg == 1` assertion is the precise single-flight signal (2 without the lock). The L3 mutation proves it isn't vacuous.
- **Fast + hermetic.** No real child, no `os.killpg` on real PIDs, no GPU. The `_SlowProc` fake's 0.3s sleep makes the whole test ~0.6s — it belongs in the fast pytest suite, not a slow integration script.
- **Scope discipline.** S2 only adds the `RecorderHost`-level concurrency test. It does NOT add the daemon-side `request_shutdown`+`shutdown` concurrency test (that is **T2.S3** — "Test concurrent request_shutdown + shutdown (SIGTERM path simulation)"), does NOT reduce the `_bounded_shutdown` timeout (T2.S2), and does NOT touch `recorder_host.py` source (S1 owns it; the L3 mutation is transient + restored).

## What

Append to `tests/test_recorder_host.py`: one test `test_concurrent_stop_calls_share_one_teardown(monkeypatch)` containing an inner `_SlowProc` fake. The test builds a host via `_make_host()`, injects `host._proc = _SlowProc()`, monkeypatches `recorder_host.os.getpgid` (→ fake pgid) and `recorder_host.os.killpg` (→ list recorder), spawns two threads that (after a `Barrier`) both call `host.stop()`, and asserts single-flight: `len(killpg_calls) == 1`, bounded time, `_proc is None`, `_dead is True`, no errors. No runtime behavior change, no config, no API.

### Success Criteria

- [ ] `tests/test_recorder_host.py` contains `test_concurrent_stop_calls_share_one_teardown(monkeypatch)` with a docstring citing bugfix Issue 1 + P1.M1.T1.S1 + the SIGTERM double-caller rationale.
- [ ] The test defines a `_SlowProc` (inner) with `is_alive()→True` and `join(timeout=None)→time.sleep(0.3)`, and a `.pid` attribute.
- [ ] The test monkeypatches `recorder_host.os.getpgid` (→ e.g. `99999`) and `recorder_host.os.killpg` (→ appends to a list).
- [ ] The test spawns two `threading.Thread`s (coordinated by a `threading.Barrier(2)`) both calling `host.stop()`.
- [ ] Assertions: no thread raised; both threads finished; `elapsed < 2.0`; `len(killpg_calls) == 1`; `host._proc is None`; `host._dead is True`.
- [ ] The test PASSES on S1-applied code and FAILS when `_stop_lock` is defeated (L3 mutation).
- [ ] `.venv/bin/python -m pytest tests/test_recorder_host.py -v` → 21 passed.
- [ ] `git diff --name-only` == `tests/test_recorder_host.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact `stop()`/`_terminate_group` flow (with line numbers), the test-fake contracts (`_make_host`, `_DeadProc`), the monkeypatch targets (`recorder_host.os.getpgid`/`os.killpg`), the deterministic single-flight proof (killpg 1 vs 2), the timing budget, and a copy-ready reference implementation are all specified below. An agent new to this repo can implement S2 from this PRP alone. No live process/GPU is needed.

### Documentation & References

```yaml
# THE INPUT CONTRACT — what stop() must do (S1's deliverable, ALREADY APPLIED)
- file: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T1S1/PRP.md
  why: Defines _stop_lock: threading.Lock() in __init__ + the WHOLE stop() body (guard included)
       under `with self._stop_lock:`. S1's invariant: the 2nd concurrent caller blocks on the lock,
       then sees _proc is None, and no-ops → exactly ONE join+killpg. S2 is the committed proof.
  critical: "S1 is ALREADY APPLIED in the live file (_stop_lock L140, with L274, guard L275). So the
       new test PASSES on first run. Treat S1's PRP as the source of truth for the invariant tested."

# THE METHOD UNDER TEST
- file: voice_typing/recorder_host.py
  why: stop() @ L255-296 (body under `with self._stop_lock:` L274; guard L275). Flow: abort_event.set
       -> cmd_q.put("shutdown") -> proc.join(timeout) -> if is_alive: _terminate_group + join(2.0) ->
       _dead=True, _proc=None. _terminate_group() @ L356-374: os.getpgid(pid) + os.killpg(pgid,SIGKILL).
       `os` imported as a module (L63) -> monkeypatch recorder_host.os.getpgid / recorder_host.os.killpg.
  pattern: "A fake proc with is_alive()->True + a sleeping join() forces stop() into the join->
           _terminate_group path (not the early-return) so killpg is actually invoked."
  gotcha: "os.getpgid(fake_pid) raises ProcessLookupError on a real OS call -> the monkeypatch is
           MANDATORY. Both getpgid AND killpg must be patched (getpgid runs first in _terminate_group)."

# THE FILE BEING EDITED — the pattern to mirror
- file: tests/test_recorder_host.py
  why: _make_host() @ L48 (builds host, no child); _DeadProc INNER fake @ L221-226 (pid=12345,
       is_alive->False, join->pass); test_stop_is_noop_when_no_process @ L213; test_stop_with_dead_
       process_is_noop @ L218. Imports threading (L18) + time (L19) already present.
  pattern: "Define _SlowProc INNER to the test (mirrors _DeadProc). Inject host._proc = _SlowProc().
            Mirror the _make_host() + monkeypatch + threading patterns already in this file."
  gotcha: "Do NOT change _make_host / _DeadProc / the 20 existing tests. The new test is ADDITIVE,
           placed after test_stop_with_dead_process_is_noop (~L227). No new imports needed."

# THE DEFECT (root cause this guard protects against)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: §Issue 1 documents the SIGTERM double-host.stop() race (request_shutdown signal thread +
       shutdown main-thread finally). S1 (single-flight lock) is the RecorderHost-side fix; S2 is its
       committed proof. (Daemon-side coordination _shutdown_done/_teardown_done is T2.S1, NOT S2.)
  critical: "S2 tests ONLY the RecorderHost boundary (two host.stop() calls). The daemon-level SIGTERM
       simulation (concurrent request_shutdown + shutdown) is T2.S3 — do not build it here."

# TEST INFRASTRUCTURE NOTE
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/test_infrastructure.md
  why: Documents pytest + monkeypatch/caplog/tmp_path fixtures; the SIGTERM-concurrent-teardown gap
       in the coverage table; _make_host() / _FakeFeedback / _FakeLatency stubs. Confirms the file's
       hermetic (no CUDA/spawn) philosophy.
  section: "'Existing Test Coverage Gaps' table — SIGTERM concurrent teardown row — is the gap S2 closes."

# THIS SUBTASK'S OWN RESEARCH NOTE — exact flow + the deterministic proof + mutation
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T1S2/research/concurrent_stop_test_findings.md
  why: §1 confirms S1 applied (line numbers); §2 the verbatim stop()/_terminate_group flow; §3 the
       existing patterns; §4 the killpg 1-vs-2 proof; §5 the timing budget; §6 the mutation validation.
  section: "§4 (killpg proof) and §6 (mutation) are load-bearing."

# PRD CONTEXT (READ-ONLY) — why single-flight matters
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: §4.2bis / §8 / §7.9 make bounded teardown a hard prerequisite; the SIGTERM double-teardown is
       the Critical Issue 1. Cite in the test docstring.
```

### Current Codebase tree (relevant slice — S1 already applied)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── recorder_host.py     # S1 APPLIED: _stop_lock L140; stop() body under `with self._stop_lock:` L274-296; _terminate_group L356-374. READ-ONLY for S2.
└── tests/
    └── test_recorder_host.py # 317 lines / 20 tests — the ONLY file S2 edits (append 1 test + _SlowProc). threading L18, time L19.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_recorder_host.py   # MODIFY: +test_concurrent_stop_calls_share_one_teardown (with inner _SlowProc). NO new files.
# NOTHING ELSE. No recorder_host.py, no daemon.py, no config, no systemd. (The L3 mutation edits
# recorder_host.py TRANSIENTLY and restores it via git checkout — never committed.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — MONKEYPATCH BOTH os.getpgid AND os.killpg. _terminate_group() does
# `pgid = os.getpgid(pid)` FIRST, then `os.killpg(pgid, SIGKILL)`. A real os.getpgid(4242) on a
# fake PID raises ProcessLookupError (caught inside _terminate_group, but then killpg never runs and
# the test's killpg counter stays 0 — a false/vacuous result). Patch BOTH:
#     monkeypatch.setattr(recorder_host.os, "getpgid", lambda _pid: 99999)
#     monkeypatch.setattr(recorder_host.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))
# `os` is imported as a module in recorder_host.py (L63), so `recorder_host.os` IS the os module.

# CRITICAL #2 — _SlowProc.is_alive() MUST STAY True. stop() only calls _terminate_group (→killpg)
# inside `if self._proc.is_alive():`. If is_alive()->False (like _DeadProc), stop() skips
# terminate_group and killpg is never called — the test would assert killpg==0, not ==1, and would
# NOT prove single-flight. _SlowProc.is_alive()->True forces the join->terminate_group path.

# CRITICAL #3 — _SlowProc.join MUST SLEEP LONG ENOUGH FOR DETERMINISTIC CONTENTION. A 0.3s sleep
# guarantees both threads (released together by the Barrier) are inside join() simultaneously, so
# without the lock both reach terminate_group (killpg==2) reliably — the test is NOT flaky. A
# near-zero join would let one caller finish + null _proc before the other starts, masking the race.
# (The fake ignores the `timeout` arg and always sleeps 0.3s — that's intentional.)

# CRITICAL #4 — THE PROOF IS killpg COUNT, NOT TIMING. With the lock, caller A ≈ 0.6s (0.3 join +
# terminate_group + 0.3 second join), caller B no-ops after A. `elapsed < 2.0` is a CI-safe sanity
# bound, NOT the distinguishing signal. `len(killpg_calls) == 1` is. Don't over-assert on timing.

# CRITICAL #5 — BARRIER(2) FOR DETERMINISTIC CONTENTION. Starting two threads sequentially can let
# the first finish before the second starts (still killpg==1, but it doesn't EXERCISE contention).
# A threading.Barrier(2) makes both call host.stop() at the same instant, maximizing the chance both
# reach the lock together. barrier.wait(timeout=2.0) prevents a hang if a thread errors pre-barrier.

# GOTCHA #6 — NO REAL PROCESS, NO REAL SIGNAL. _make_host() builds a host with NO child. The test
# injects host._proc = _SlowProc() (a plain object, NOT mp.Process). os.getpgid/os.killpg are patched
# so nothing is signaled. The _cmd_q.put(("shutdown",{})) and _abort_event.set() hits real mp.Queue/
# mp.Event but are harmless (queue accumulates one item; the existing _DeadProc test does the same
# and passes). Do NOT drain/cleanup the queue — the file's existing tests don't.

# GOTCHA #7 — list.append IS THREAD-SAFE under the GIL. Both threads may (without the lock) append to
# killpg_calls; CPython's GIL makes list.append atomic, so no corruption. The count is the signal.

# GOTCHA #8 — DON'T TOUCH recorder_host.py AS A COMMITTED CHANGE. S1 owns it. S2 only READS it. The
# Validation L3 mutation temporarily edits it to prove the test isn't vacuous, then RESTORES via
# `git checkout voice_typing/recorder_host.py`. Final git diff = test file only.

# GOTCHA #9 — DON'T BUILD THE DAEMON-SIDE SIGTERM TEST HERE. T2.S3 owns "concurrent request_shutdown +
# shutdown (SIGTERM path simulation)". S2 is the RecorderHost-level proof (two host.stop() calls).
# Keep them separate so each guard is independently auditable.

# GOTCHA #10 — FULL-PATH DISCIPLINE. `.venv/bin/python -m pytest ...` (machine aliases python3→uv run).
# No ruff/mypy configured in this project — don't invoke them. `git`/`sed` are fine as-is.
```

## Implementation Blueprint

### Data models and structure

None (no ORM/pydantic). The only "structure" is the `_SlowProc` fake's contract and the killpg-counter control flow:

```python
# _SlowProc forces stop() into the join->_terminate_group path (killpg actually fires):
class _SlowProc:
    pid = 4242
    def is_alive(self): return True        # CRITICAL: stay alive -> terminate_group runs
    def join(self, timeout=None): time.sleep(0.3)  # CRITICAL: 0.3s -> deterministic contention

# The single-flight signal: killpg is invoked exactly once (caller A) vs twice (no lock).
# Monkeypatch BOTH getpgid (runs first) and killpg (the counter).
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD test_concurrent_stop_calls_share_one_teardown to tests/test_recorder_host.py
  - PLACE: directly after test_stop_with_dead_process_is_noop (ends ~L227), in the existing
    "set_microphone / abort / stop" region (or a new "# concurrent stop" subsection right after it).
  - CODE (reference implementation — copy-ready):
        def test_concurrent_stop_calls_share_one_teardown(monkeypatch):
            """Two concurrent stop() callers share ONE teardown (single-flight under _stop_lock).

            Regression guard for bugfix Issue 1 (P1.M1.T1.S1): on the SIGTERM path request_shutdown()
            (signal-handler thread) + shutdown() (main-thread finally) both call host.stop() at once.
            Without serialization each caller passes the `self._proc is None` guard and runs its own
            join+killpg, so os.killpg fires TWICE and two parallel multi-second teardowns blow
            systemd's 15s TimeoutStopSec. _stop_lock makes check-then-teardown atomic: the second
            caller blocks on the lock, then sees _proc is None and no-ops — exactly ONE killpg.

            Hermetic + fast (~0.6s): a _SlowProc whose join() sleeps 0.3s + is_alive() stays True
            forces stop() into the join->_terminate_group path (not the early-return), and
            os.getpgid/os.killpg are monkeypatched so no real process is signaled. Two threads +
            a Barrier maximize contention. The PROOF is the killpg call count (1 with the lock,
            2 without) — see the L3 mutation in this subtask's PRP.
            """

            class _SlowProc:
                pid = 4242

                def is_alive(self):
                    return True

                def join(self, timeout=None):
                    time.sleep(0.3)  # wedge long enough that both callers overlap inside stop()

            host = _make_host()
            host._proc = _SlowProc()

            killpg_calls: list[tuple] = []
            monkeypatch.setattr(recorder_host.os, "getpgid", lambda _pid: 99999)
            monkeypatch.setattr(
                recorder_host.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig))
            )

            barrier = threading.Barrier(2)
            errors: list[BaseException] = []

            def _call_stop() -> None:
                try:
                    barrier.wait(timeout=2.0)
                    host.stop()
                except BaseException as exc:  # noqa: BLE001 — capture, re-assert below
                    errors.append(exc)

            t1 = threading.Thread(target=_call_stop, name="stop-A")
            t2 = threading.Thread(target=_call_stop, name="stop-B")
            start = time.monotonic()
            t1.start()
            t2.start()
            t1.join(timeout=5.0)
            t2.join(timeout=5.0)
            elapsed = time.monotonic() - start

            assert not errors, f"a stop() caller raised: {errors!r}"
            assert not t1.is_alive() and not t2.is_alive(), "a stop() thread did not finish"
            assert elapsed < 2.0, f"concurrent stop took {elapsed:.2f}s (single-flight ~0.6s expected)"
            assert len(killpg_calls) == 1, (
                f"os.killpg called {len(killpg_calls)}x (expected 1) — _stop_lock single-flight is "
                "broken: two concurrent callers must share ONE teardown"
            )
            assert host._proc is None, "host._proc not cleared after teardown"
            assert host._dead is True, "host._dead not set after teardown"
  - CONSTRAINTS:
      * Define _SlowProc INNER to the test (mirrors _DeadProc style). is_alive()->True, join sleeps 0.3.
      * Monkeypatch BOTH recorder_host.os.getpgid AND recorder_host.os.killpg (Gotcha #1).
      * Use threading.Barrier(2) (Gotcha #5). barrier.wait(timeout=2.0) to avoid hangs.
      * The load-bearing assertion is `len(killpg_calls) == 1` (Gotcha #4).
      * Do NOT modify _make_host / _DeadProc / any existing test. No new imports (threading L18, time L19).

Task 2: VALIDATE — run the Validation Loop L1–L4. No git commit unless the orchestrator directs it.
  If asked to commit, message:
  "P1.M1.T1.S2: regression test — concurrent RecorderHost.stop() calls share ONE teardown (Issue 1)".
```

### Implementation Patterns & Key Details

```python
# The single load-bearing design decision: the killpg-call COUNT distinguishes single-flight from the
# race, and the _SlowProc's 0.3s join + the Barrier make that count DETERMINISTIC.

# WITH _stop_lock (S1 applied): caller A acquires, runs join(0.3)+terminate_group(killpg)+join(0.3),
#   sets _proc=None, releases. Caller B blocks on the lock, acquires, sees _proc is None, returns.
#   -> len(killpg_calls) == 1.
# WITHOUT _stop_lock (the bug / the mutation): both callers pass the guard, both sleep 0.3s in join
#   concurrently, both see is_alive() True, both call _terminate_group -> killpg.
#   -> len(killpg_calls) == 2.

# Why it's not flaky: the 0.3s sleep makes the race window ~300ms — orders of magnitude larger than
# thread-scheduling jitter — so without the lock BOTH callers reliably reach _terminate_group.
# With the lock, caller B provably no-ops (guard-inside-the-lock invariant from S1).

# Why getpgid MUST be patched: _terminate_group does `os.getpgid(pid)` BEFORE `os.killpg`. A real
# getpgid(4242) raises ProcessLookupError, which _terminate_group catches -> killpg never runs ->
# killpg_calls stays empty -> the test would assert ==1 against 0 (wrong/vacuous). Patch both.
```

### Integration Points

```yaml
TEST SUITE:
  - The new test joins the 20 existing in tests/test_recorder_host.py. `.venv/bin/python -m pytest
    tests/test_recorder_host.py -v` -> 21 passed. S2 only ADDS a test, so no existing test can regress.

DEPENDS ON (S1 — P1.M1.T1.S1):
  - S2's test PASSES only because S1 wraps stop()'s body (guard included) in _stop_lock. S1 is
    already applied. If a future change reverts S1 (or moves the guard outside the lock), S2's test
    goes RED — exactly the intended behavior. S1 (fix) + S2 (proof) form a pair.

DOWNSTREAM (T2.S3 — daemon-level SIGTERM simulation):
  - S2 is the RecorderHost-LEVEL proof (two host.stop() calls). T2.S3 is the daemon-LEVEL proof
    (concurrent request_shutdown + shutdown -> the actual SIGTERM path). Together they cover the
    race end-to-end. S2 does not depend on T2.S3 and vice versa; they are independently auditable.

FILES NOT TOUCHED (scope boundary):
  - voice_typing/recorder_host.py (S1 owns; S2 reads only — the L3 mutation is transient + restored).
  - voice_typing/daemon.py (T2 owns daemon-side _shutdown_done/_teardown_done + 10s->5s + T2.S3 test).
  - No config/systemd/install.sh/README/ACCEPTANCE edits.
```

## Validation Loop

> All commands use FULL PATHS (machine aliases python3→uv run). Run from `/home/dustin/projects/voice-typing`.
> All gates are FAST unit tests with fakes — NO GPU/models/network/real-process. No ruff/mypy in this project.

### Level 1: Syntax + the new test is discovered

```bash
cd /home/dustin/projects/voice-typing
echo "--- test_recorder_host.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('tests/test_recorder_host.py').read()); print('L1a PASS: parses')"
echo "--- pytest discovers 21 tests incl. the new one ---"
.venv/bin/python -m pytest tests/test_recorder_host.py --collect-only -q | tail -3
grep -q 'test_concurrent_stop_calls_share_one_teardown' <(.venv/bin/python -m pytest tests/test_recorder_host.py --collect-only -q) \
  && echo "L1b PASS: new test collected" || echo "L1b FAIL: new test missing"
# Expected: parses; collection lists 21 items incl. test_concurrent_stop_calls_share_one_teardown.
```

### Level 2: The new test PASSES + the existing 20 stay green (compat)

```bash
cd /home/dustin/projects/voice-typing
echo "--- full recorder_host suite ---"
.venv/bin/python -m pytest tests/test_recorder_host.py -v 2>&1 | tail -6
echo "--- the new test alone (verbose) ---"
.venv/bin/python -m pytest tests/test_recorder_host.py::test_concurrent_stop_calls_share_one_teardown -v 2>&1 | tail -6
echo "--- the two existing stop() tests still pass (unchanged) ---"
.venv/bin/python -m pytest tests/test_recorder_host.py -k "stop" -v 2>&1 | tail -8
# Expected: 21 passed (incl. test_concurrent_stop_calls_share_one_teardown PASSED). The two existing
# stop tests (test_stop_is_noop_when_no_process, test_stop_with_dead_process_is_noop) UNCHANGED.
# If the new test FAILS on killpg count: S1's _stop_lock is missing/mis-placed (re-check recorder_host.py
# L140/L274/L275) OR getpgid wasn't patched (Gotcha #1 — a ProcessLookupError swallowed before killpg).
```

### Level 3: The guard ACTUALLY guards — mutation proof (the load-bearing validation)

> Proves the test is NOT vacuous (a real risk for concurrency tests). Temporarily defeats `_stop_lock`
> in recorder_host.py (S1's file) with a one-line, no-import swap, confirms the test goes RED, then
> RESTORES. The final diff must be clean (test file only).

```bash
cd /home/dustin/projects/voice-typing
cp voice_typing/recorder_host.py /tmp/recorder_host.py.bak   # safety backup

echo "--- 3a: defeat single-flight (swap the lock for a no-op 'if True:') ---"
sed -i 's/^        with self\._stop_lock:/        if True:  # MUTATION: defeat single-flight/' voice_typing/recorder_host.py
echo "    (verify the swap landed on stop()'s body, not a comment):"
grep -n 'if True:  # MUTATION' voice_typing/recorder_host.py
.venv/bin/python -m pytest tests/test_recorder_host.py::test_concurrent_stop_calls_share_one_teardown -v 2>&1 | tail -8
echo "    exit after mutation: $? (expect NON-zero / FAILED — killpg called 2x, assert ==1 fails)"
# Expected: the test FAILS (len(killpg_calls) == 2, not 1). If it still PASSES, the test is vacuous
# (Gotcha #3 — _SlowProc.join may be too short, or the Barrier isn't forcing contention) — fix before
# proceeding.

echo "--- 3b: RESTORE recorder_host.py to S1 state ---"
git checkout voice_typing/recorder_host.py
git diff --quiet voice_typing/recorder_host.py && echo "L3b PASS: recorder_host.py restored to S1 state" \
  || { cp /tmp/recorder_host.py.bak voice_typing/recorder_host.py; echo "L3b: restored via backup"; }
.venv/bin/python -m pytest tests/test_recorder_host.py -q 2>&1 | tail -3
# Expected: 21 passed again; recorder_host.py byte-identical to git (S1 state). Mutation left no trace.

echo "--- 3c (optional, anti-flake): run the restored test 20x in a loop ---"
for i in $(seq 1 20); do
  .venv/bin/python -m pytest -q tests/test_recorder_host.py::test_concurrent_stop_calls_share_one_teardown >/dev/null 2>&1 || { echo "L3c FAIL on run $i"; break; }
done && echo "L3c PASS: 20/20 runs green (no flakiness)"
rm -f /tmp/recorder_host.py.bak
```

### Level 4: Scope — only tests/test_recorder_host.py changed; broader suite green

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY tests/test_recorder_host.py ---"
git diff --name-only | grep -vxE 'tests/test_recorder_host.py' && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only tests/test_recorder_host.py changed"
echo "--- sibling/scope files UNTOUCHED (esp. recorder_host.py after the L3 mutation+restore) ---"
git diff --quiet voice_typing/recorder_host.py voice_typing/daemon.py systemd/voice-typing.service install.sh \
  && echo "L4 PASS: recorder_host.py/daemon.py/unit/install.sh unchanged" \
  || echo "L4 FAIL: a source/scope file was modified"
echo "--- broader pytest (recorder_host + daemon) still green ---"
.venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q 2>&1 | tail -4
# Expected: all pass; only the test file in the diff; no source/scope file modified.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `tests/test_recorder_host.py` parses; pytest collects 21 tests incl. `test_concurrent_stop_calls_share_one_teardown`.
- [ ] L2: full `test_recorder_host.py` → 21 passed; new test green; the two existing `stop()` tests unchanged.
- [ ] L3: mutation — defeating `_stop_lock` (`with self._stop_lock:` → `if True:`) turns the new test RED (`killpg` 2x); `recorder_host.py` restored to S1 state (clean git diff); optional 20× loop shows no flakiness.
- [ ] L4: `git diff --name-only` == `tests/test_recorder_host.py`; `recorder_host.py`/`daemon.py`/unit/install.sh unchanged; broader pytest green.

### Feature Validation
- [ ] The test drives TWO concurrent `host.stop()` callers (Barrier-coordinated) and asserts `len(killpg_calls) == 1`.
- [ ] Both `os.getpgid` AND `os.killpg` are monkeypatched (so no real signal + killpg actually fires).
- [ ] `_SlowProc` (`is_alive` True, `join` sleeps 0.3s) forces the join→`_terminate_group` path.
- [ ] Assertions: no thread raised; both finished; `elapsed < 2.0`; `_proc is None`; `_dead is True`.
- [ ] Docstring cites bugfix Issue 1 + P1.M1.T1.S1 + the SIGTERM double-caller rationale.

### Code Quality Validation
- [ ] `_SlowProc` defined INNER to the test (mirrors `_DeadProc` style).
- [ ] Reuses `_make_host()` + the file's existing `threading`/`time` imports (no new imports).
- [ ] No mutation of `_make_host`/`_DeadProc`/the 20 existing tests (append-only).
- [ ] Load-bearing assertion is `len(killpg_calls) == 1` (precise single-flight signal; not a weak timing check).

### Scope Boundary Validation
- [ ] `voice_typing/recorder_host.py` unmodified as a committed change (read-only; L3 mutation restored).
- [ ] `voice_typing/daemon.py` unmodified (T2 owns daemon-side coordination + 10s→5s + the SIGTERM-simulation test T2.S3).
- [ ] No config/systemd/install.sh/README/ACCEPTANCE edits.
- [ ] No bare `python`/`pytest` (full-pathed `.venv/bin/python -m pytest`); no ruff/mypy invoked.

### Documentation & Deployment
- [ ] (No user-facing docs — test-only subtask.) The test docstring is the durable explanation.
- [ ] If asked to commit: message references bugfix Issue 1 + single-flight for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't forget to monkeypatch `os.getpgid` (not just `os.killpg`) — `_terminate_group` calls `getpgid` FIRST; a real `getpgid(fake_pid)` raises `ProcessLookupError` that gets swallowed, so `killpg` never runs and the test becomes vacuous (killpg==0). Patch both. (Gotcha #1.)
- ❌ Don't make `_SlowProc.is_alive()` return `False` — `stop()` only calls `_terminate_group` (→killpg) inside `if is_alive()`. False → killpg never fires → the test asserts against 0, not 1, and proves nothing. (Gotcha #2.)
- ❌ Don't make `_SlowProc.join()` near-zero — too short and one caller can finish + null `_proc` before the other starts, masking the race (killpg==1 even without the lock → vacuous pass). 0.3s makes contention deterministic. (Gotcha #3.)
- ❌ Don't treat timing as the proof — `elapsed < 2.0` is a sanity bound; `len(killpg_calls) == 1` is the single-flight signal. (Gotcha #4.)
- ❌ Don't start the two threads without a `Barrier` — sequential start can skip contention entirely. `Barrier(2)` forces simultaneous entry. (Gotcha #5.)
- ❌ Don't edit `recorder_host.py` as a committed change — S1 owns it. The L3 mutation is transient and must be `git checkout`-restored. (Gotcha #8.)
- ❌ Don't build the daemon-level SIGTERM test (`request_shutdown` + `shutdown`) here — that's T2.S3. S2 is the RecorderHost-level proof (two `host.stop()` calls). (Gotcha #9.)
- ❌ Don't modify `_make_host`/`_DeadProc`/the 20 existing tests — S2 is append-only.
- ❌ Don't drain/cleanup the `_cmd_q` — the existing `_DeadProc` test leaves an item and passes; match it. (Gotcha #6.)
- ❌ Don't use bare `python`/`pytest` or invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest`. (Gotcha #10.)

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a small, fully-specified test addition with a copy-ready reference implementation. Every load-bearing fact is empirically verified against the live repo: S1 is already applied (`_stop_lock` L140, `with` L274, guard L275 — so the test passes first run); the exact `stop()`/`_terminate_group` flow and the `recorder_host.os.getpgid`/`os.killpg` monkeypatch targets are confirmed; the existing `_make_host`/`_DeadProc` patterns and the `threading`/`time` imports are read in full; and the deterministic single-flight proof (killpg 1-vs-2) is grounded in the 0.3s `_SlowProc.join` + `Barrier` design. The L1/L2 gates prove the test is well-formed and green; the L3 mutation gate proves it actually catches the regression (killpg→2 when the lock is defeated) and is not a vacuous pass — the single most important property for a concurrency test. The −0.5 is solely that L3's mutation step temporarily edits the S1-owned `recorder_host.py` and must be meticulously restored; a careless restore would leave a stray diff (mitigated by the explicit `cp` backup + the `git diff --quiet` check in L3b/L4).
