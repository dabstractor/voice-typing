# PRP — P1.M1.T1.S1: Add `_stop_lock` to RecorderHost and wrap `stop()` body

## Goal

**Feature Goal**: Make `RecorderHost.stop()` **single-flight / thread-safe** so that concurrent callers share exactly ONE process-group teardown (join + `killpg`), and the second (and any later) caller is a no-op. This is the `RecorderHost`-level piece of the Issue 1 fix: on the SIGTERM path, `request_shutdown()` (signal-handler thread) and `shutdown()` (main-thread `finally`) both reach `host.stop()` concurrently; without serialization each passes the `self._proc is None` guard and runs its own multi-second join+SIGKILL, and the two parallel teardowns blow systemd's 15s `TimeoutStopSec`.

**Deliverable**: Two surgical edits to `voice_typing/recorder_host.py` only — (1) add `self._stop_lock = threading.Lock()` in `__init__`; (2) wrap the **entire** `stop()` body — **including the `if self._proc is None: return` early guard** — in `with self._stop_lock:`, plus a docstring note. No other file changes.

**Success Definition**: (a) `stop()`'s whole body executes under `_stop_lock` (guard included); (b) two concurrent `stop()` callers result in exactly one join+`_terminate_group` sequence (the second blocks on the lock, then sees `_proc is None` and returns); (c) the existing `tests/test_recorder_host.py` suite (20 tests, incl. the two `stop()` idempotency tests) stays green; (d) `_STOP_JOIN_TIMEOUT_S` remains `5.0` (no change); (e) only `recorder_host.py` is modified.

## User Persona

**Target User**: The daemon's own shutdown machinery (two threads converging on `host.stop()` during SIGTERM) and the maintainers of the bounded-teardown guarantee (PRD §4.2bis / §8 / §7.9).

**Use Case**: `systemctl --user stop voice-typing` while the daemon is armed. systemd sends SIGTERM → the daemon's signal handler thread runs `request_shutdown()` → `host.stop()`; meanwhile `main()`'s `finally` runs `daemon.shutdown()` → `host.stop()` on the main thread. Both arrive at `stop()` at once.

**Pain Points Addressed**: Eliminates the doubled teardown that (combined with the 10s timeout in T2.S2's scope) pushed the armed SIGTERM stop past `TimeoutStopSec=15` → SIGKILL → "Failed with result 'timeout'". With single-flight, the two callers share one bounded teardown instead of running two.

## Why

- **Critical regression (bugfix Issue 1):** armed `systemctl --user stop` reproducibly takes the full 15.2s and is SIGKILLed (2/2 runs). The root cause (architecture/bug_analysis.md §Issue 1) is the concurrent double `host.stop()` on the SIGTERM path. This subtask removes the concurrency at the `RecorderHost` boundary.
- **Why the guard must move INSIDE the lock (the load-bearing detail):** the existing `if self._proc is None: return` guard is a check-then-teardown. If it stays *outside* the lock, caller A and caller B can both pass it (both see `_proc` not-None) before either acquires the lock, then both proceed to join+killpg. Wrapping the guard *inside* `with self._stop_lock:` makes check-then-teardown atomic: the second caller blocks until the first has set `self._proc = None`, then re-checks under the lock and returns. This is the single most important correctness property of the change.
- **Minimal, surgical, low-risk:** one `Lock` + one indentation level. `stop()` is never called re-entrantly (verified: no `self.stop`/`host.stop` call anywhere inside `recorder_host.py`), so a plain `threading.Lock()` is correct — no `RLock`, no deadlock surface.
- **Composes cleanly with T2:** S1 collapses two parallel teardowns into one (single-flight). The remaining "comfortably under 15s" margin comes from T2.S2 reducing `_bounded_shutdown`'s default timeout 10s→5s; S1 does not touch that. S1's own success criterion is exactly "only ONE teardown executes regardless of concurrent callers."

## What

Add a `_stop_lock` and wrap `stop()`'s body. No behavior change for a single caller (the lock is uncontended → trivial acquire/release); the change only affects the concurrent-caller case, collapsing N teardowns into 1.

### Success Criteria

- [ ] `voice_typing/recorder_host.py` `__init__` creates `self._stop_lock = threading.Lock()`.
- [ ] `stop()`'s entire body — including `if self._proc is None: return` — is inside `with self._stop_lock:`.
- [ ] `stop()` docstring documents the single-flight guarantee and the SIGTERM double-caller rationale.
- [ ] `_STOP_JOIN_TIMEOUT_S` is still `5.0` (untouched).
- [ ] `tests/test_recorder_host.py` passes 20/20 (incl. `test_stop_is_noop_when_no_process`, `test_stop_with_dead_process_is_noop`).
- [ ] No change to `daemon.py`, tests, or any other file.

## All Needed Context

### Context Completeness Check

_Pass._ The exact current code (with line numbers), the exact two edits, the no-re-entrancy proof, the existing test names that must stay green, and the verified test command are all below. An agent new to this codebase can apply the patch from this PRP alone.

### Documentation & References

```yaml
# THE DEFECT (authoritative root cause)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: §Issue 1 Root Cause documents the SIGTERM double-host.stop() race: request_shutdown()
       (signal thread) + shutdown() (main thread finally) both call host.stop() concurrently;
       each passes the None-guard and runs a ~12s teardown; two in parallel blow TimeoutStopSec=15.
  critical: "S1 fixes the RecorderHost side (single-flight). The daemon-side coordination
            (_shutdown_done + _teardown_done Event) and the 10s->5s timeout reduction are T2's scope."

# THE FIX SITE — the class + method
- file: voice_typing/recorder_host.py
  why: RecorderHost.__init__ (line 103) creates the threading primitives at lines 134-139:
       self._proc (None), self._reader, self._final_evt, self._ready_evt. stop() (line 250)
       has the unguarded `if self._proc is None: return` then abort_event.set / cmd_q.put /
       join(timeout) / is_alive -> _terminate_group + join(2) / _dead=True / _proc=None.
       `threading` is already imported (line 65). `_STOP_JOIN_TIMEOUT_S = 5.0` (line 87).
  pattern: "Group the new self._stop_lock with the existing threading primitives in __init__
            (right after self._proc). Wrap stop()'s WHOLE body in `with self._stop_lock:` and
            indent the body one level (4 spaces). Match the existing docstring/comment style."
  gotcha: "The `if self._proc is None: return` guard MUST move INSIDE the with-block. Leaving it
           outside defeats single-flight (two callers pass it before either acquires the lock)."

# THE TERMINATE PATH (what the 2nd caller must NOT re-run)
- file: voice_typing/recorder_host.py
  why: _terminate_group() (line 340) does os.killpg(os.getpgid(pid), SIGKILL) — the VRAM-releasing
        force kill. It is itself guarded by `if self._proc is None: return`, but that is cold
        comfort if two stop() callers already passed stop()'s guard. Single-flight at stop() is the
        real fix; do NOT add a second lock inside _terminate_group (it is only ever called from
        stop(), which already holds _stop_lock).

# THE CONCURRENT CALLERS (daemon side — NOT edited in S1, but explains the why)
- file: voice_typing/daemon.py
  why: _bounded_shutdown (line 1265) calls self._host.stop(timeout=timeout) at line 1281. It is
        reached from request_shutdown() (signal thread, line ~1167) AND shutdown() (main-thread
        finally, line 1317). On SIGTERM these run concurrently -> two host.stop() calls. S1 makes
        those two calls share one teardown. (T2.S1 adds _shutdown_done + _teardown_done so the
        daemon doesn't even start the second _bounded_shutdown; S1 is defense at the host boundary.)
  critical: "S1 edits ONLY recorder_host.py. Do NOT touch daemon.py — that is T2."

# THE TESTS THAT MUST STAY GREEN (and where S2's new test goes)
- file: tests/test_recorder_host.py
  why: test_stop_is_noop_when_no_process (line 213) and test_stop_with_dead_process_is_noop
        (line 218) pin single-caller idempotency. They use the _make_host() helper + a fake _proc.
        S2 (P1.M1.T1.S2) adds the CONCURRENT-calls test here, following the same _make_host() +
        fake-proc pattern, asserting ONE teardown. S1 does NOT add tests.
  pattern: "_make_host() builds a host without a real child; tests inject host._proc = <fake>.
            A fake proc with a blocking join() lets S2 prove the 2nd caller no-ops under the lock."
  critical: "S1's change must keep these two tests green (it does: lock acquire is uncontended for
            a single caller, then the identical body runs)."

# PRD CONTEXT
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: §4.2bis / §8 / §7.9 make bounded teardown a hard prerequisite for idle-unload. Single-flight
        stop() is part of making teardown bounded under concurrent shutdown.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── recorder_host.py     # RecorderHost.__init__ @103 (primitives @134-139); stop() @250-282; _terminate_group @340  ← EDIT (only file)
│   └── daemon.py            # _bounded_shutdown @1265 -> host.stop() @1281 (CONCURRENT caller; NOT edited in S1)
└── tests/
    └── test_recorder_host.py # stop() idempotency tests @213/@218 (must stay green; S2 adds concurrency test)
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/recorder_host.py   # MODIFY: +1 lock in __init__; wrap stop() body in `with self._stop_lock:`; docstring note. NO new files.
# Nothing else. No daemon.py, no tests, no config, no systemd.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE GUARD GOES INSIDE THE LOCK. This is the whole point. `if self._proc is None:
# return` MUST be the first statement inside `with self._stop_lock:`. If it stays outside, two
# callers pass it concurrently before either acquires the lock -> double teardown -> the bug.
# After the change: caller A acquires lock, passes guard, tears down, sets _proc=None, releases.
# Caller B acquires lock, sees _proc is None, returns. Exactly ONE teardown.

# CRITICAL #2 — PLAIN Lock, NOT RLock. stop() is never called re-entrantly: grep confirms no
# self.stop/host.stop call anywhere in recorder_host.py, and _terminate_group (the only helper
# stop() calls that could loop back) does not call stop(). So threading.Lock() is correct and an
# RLock would be misleading. (Verified: `grep -n 'self\.stop\|host\.stop' recorder_host.py` = empty.)

# CRITICAL #3 — INDENT THE WHOLE BODY. Every line of the current stop() body gains 4 spaces under
# the new `with self._stop_lock:`. Don't accidentally leave a statement (e.g. self._dead=True or
# self._proc=None) outside the with — that would re-open the race.

# CRITICAL #4 — DON'T ADD A LOCK IN _terminate_group. It is only ever called from stop(), which
# already holds _stop_lock. A second lock there is dead code and muddies the single-flight story.

# GOTCHA #5 — DON'T TOUCH _STOP_JOIN_TIMEOUT_S. It is 5.0 (line 87) and stop()'s default. The
# contract's "(d) verify 5.0 remains the per-call default" is a CONFIRMATION, not a change. Leave it.
# (Reducing _bounded_shutdown's 10s default to 5s is T2.S2 — different function, different file.)

# GOTCHA #6 — SCOPE. S1 edits recorder_host.py ONLY. The daemon-side single-flight coordination
# (_shutdown_done + _teardown_done Event in request_shutdown/shutdown) is T2.S1; the 10s->5s timeout
# is T2.S2; the concurrent-calls regression test is S2. Do not pre-empt them.

# GOTCHA #7 — EXISTING TESTS ARE SINGLE-CALLER. test_stop_is_noop_when_no_process and
# test_stop_with_dead_process_is_noop must stay green. They will: for one caller the lock is
# uncontended (instant acquire), then the identical body runs. The concurrency proof is S2's test.

# GOTCHA #8 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# pytest gate (or `uv run pytest` if you prefer). No ruff/mypy in this project — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

None. This adds one `threading.Lock` instance attribute and re-indents one method. No data model, schema, or API change (`stop()`'s signature is unchanged).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/recorder_host.py __init__ — add _stop_lock
  - FIND the threading-primitives block in __init__ (lines ~134-139). Current:
        self._proc: Any = None
        self._reader: threading.Thread | None = None
        self._final_evt = threading.Event()
        self._ready_evt = threading.Event()
  - INSERT the lock immediately after `self._proc: Any = None` (grouped with _proc, which it guards):
        self._proc: Any = None
        # Single-flight lock for stop(): serializes concurrent callers (SIGTERM signal thread +
        # main-thread finally both reach host.stop()) so exactly ONE join+killpg teardown runs; the
        # 2nd caller blocks on the lock, then sees _proc is None and no-ops. See stop() (bugfix
        # Issue 1 / P1.M1.T1.S1). Plain Lock (not RLock): stop() is never re-entered.
        self._stop_lock = threading.Lock()
        self._reader: threading.Thread | None = None
  - `threading` is already imported (line 65) — do NOT add an import.

Task 2: EDIT voice_typing/recorder_host.py stop() — wrap body under _stop_lock + docstring
  - FIND stop() (line 250). Wrap its ENTIRE body in `with self._stop_lock:` and indent the body
    one level (4 spaces). The `if self._proc is None: return` guard MUST be the FIRST statement
    inside the with-block (Gotcha #1). Update the docstring's first line to "Idempotent +
    SINGLE-FLIGHT." and append a SINGLE-FLIGHT paragraph explaining: the whole body (guard
    included) runs under _stop_lock; on SIGTERM two threads call stop() concurrently; the 2nd
    blocks then no-ops on `_proc is None`; exactly one teardown runs; plain Lock (no re-entrancy).
  - RESULT (after edit), verbatim structure:
        def stop(self, timeout: float = _STOP_JOIN_TIMEOUT_S) -> None:
            """Terminate the child PROCESS GROUP. Idempotent + SINGLE-FLIGHT. THE bounded teardown.

            <existing paragraphs: shutdown cmd, join, killpg, VRAM, ~90s wedge, supersedes _bounded_shutdown>

            SINGLE-FLIGHT (thread-safe, bugfix Issue 1 / P1.M1.T1.S1): the ENTIRE body — including
            the `self._proc is None` early guard — runs under `self._stop_lock`. On the SIGTERM path
            two threads call stop() concurrently (request_shutdown() on the signal-handler thread +
            shutdown() on the main-thread finally); without serialization both passed the None-guard
            and ran two parallel teardowns, blowing systemd's 15s TimeoutStopSec. Under the lock the
            second caller blocks until the first finishes the join+killpg and sets `self._proc =
            None`, then acquires the lock, sees `_proc is None`, and returns immediately — so exactly
            ONE process-group teardown ever executes. (Plain Lock, not RLock: stop() is never
            re-entered.)
            """
            with self._stop_lock:
                if self._proc is None:
                    return
                try:
                    self._abort_event.set()
                except (OSError, EOFError):
                    pass
                try:
                    self._cmd_q.put(("shutdown", {}))
                except (BrokenPipeError, OSError, EOFError):
                    pass
                self._proc.join(timeout=timeout)
                if self._proc.is_alive():
                    logger.warning(
                        "recorder host: child did not exit within %.1fs; SIGKILL-ing the process group",
                        timeout,
                    )
                    self._terminate_group()
                    self._proc.join(timeout=2.0)
                self._dead = True
                self._proc = None
  - CONSTRAINTS: preserve every existing statement + the order (abort_event.set BEFORE cmd_q.put
    BEFORE join BEFORE terminate_group). Keep comments. Do NOT change the signature. Do NOT touch
    _terminate_group. Do NOT change _STOP_JOIN_TIMEOUT_S.

Task 3: VALIDATE (run the gates below). No git commit unless the orchestrator directs it. If asked,
  message: "P1.M1.T1.S1: make RecorderHost.stop() single-flight under _stop_lock".
```

### Implementation Patterns & Key Details

```python
# The entire change is: one Lock + one indentation level. Correctness rests on ONE invariant:
# the `if self._proc is None: return` guard is INSIDE `with self._stop_lock:`.
#
# Trace (SIGTERM, two concurrent callers) AFTER the fix:
#   T_signal: request_shutdown() -> _bounded_shutdown() -> host.stop()
#   T_main  : shutdown()         -> _bounded_shutdown() -> host.stop()
#   - One caller acquires _stop_lock first (say T_signal): _proc not None -> join+killpg ->
#     _dead=True, _proc=None, release lock.
#   - The other (T_main) was blocked on _stop_lock; it now acquires, sees _proc is None, returns.
#   Net: ONE teardown. (Before the fix: TWO parallel ~12s teardowns -> SIGKILL at 15s.)
#
# No deadlock: _stop_lock is held only inside stop(); stop() calls no method that re-enters stop()
# or acquires _stop_lock. _terminate_group() does not call stop() and does not take _stop_lock.
#
# Single-caller behavior is unchanged: the lock is uncontended (acquire is ~ns), then the identical
# body runs. That is why test_stop_is_noop_when_no_process / test_stop_with_dead_process_is_noop
# stay green.
```

### Integration Points

```yaml
DAEMON SHUTDOWN PATHS (the concurrent callers — NOT edited in S1):
  - SIGTERM: signal handler -> request_shutdown() -> _bounded_shutdown() -> host.stop(timeout)
    [signal thread] AND main() finally -> daemon.shutdown() -> _bounded_shutdown() -> host.stop()
    [main thread]. S1 makes these two host.stop() calls single-flight at the RecorderHost boundary.
  - voicectl quit: request_shutdown() + daemon.shutdown() run SEQUENTIALLY on the same socket-worker
    thread -> the second host.stop() already sees _proc is None. S1 is harmless here (uncontended).
  - idle-unload: _idle_unload -> host.stop() under _lock; single caller. S1 is harmless (uncontended).
  - load failure: _load_host -> host.stop() on a half-built host; single caller. Harmless.

CONTROLSERVER / OTHER CALLERS:
  - No other code path calls RecorderHost.stop() re-entrantly or while holding a lock that _stop_lock
    would deadlock with (verified: stop() is reached only via _bounded_shutdown, which holds no lock
    that nests into _stop_lock).

SYSTEMD (systemd/voice-typing.service):
  - NOT modified by S1. TimeoutStopSec stays 15. (The sub-15s margin under a wedged child comes from
    T2.S2's 10s->5s _bounded_shutdown timeout; S1 removes the DOUBLED teardown, T2.S2 trims the single one.)

REGRESSION TEST (sibling subtask — NOT S1):
  - S2 (P1.M1.T1.S2) adds tests/test_recorder_host.py::test_concurrent_stop_shares_one_teardown (or
    similar) using _make_host() + a fake proc with a blocking join(), spawning 2 threads calling
    host.stop(), asserting exactly one join/killpg. S1's lock makes that test pass once written.
```

## Validation Loop

> Full paths for python (machine aliases python3->uv run). No ruff/mypy in this project — the gates
> are: static structure + the existing pytest suite. The concurrency regression is S2's test (not
> committed here), but an optional manual smoke is provided in L3.

### Level 1: The lock is added and wraps the guard (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- _stop_lock created in __init__ ---"
grep -n '_stop_lock = threading.Lock()' voice_typing/recorder_host.py && echo "L1a PASS" || echo "L1a FAIL"
echo "--- stop() body is under 'with self._stop_lock:' and the guard is INSIDE ---"
# Show the with-block + the indented guard that must follow it:
grep -n -A2 'with self._stop_lock:' voice_typing/recorder_host.py | grep -E 'with self._stop_lock:|if self\._proc is None' && echo "L1b PASS" || echo "L1b FAIL"
echo "--- no statement leaked outside the with (the guard line is indented under the with) ---"
awk '/def stop\(/{s=1} s&&/with self\._stop_lock:/{w=NR} s&&/if self\._proc is None/{g=NR; print "with_line="w" guard_line="g} s&&/^    def /{exit}' voice_typing/recorder_host.py
echo "--- _STOP_JOIN_TIMEOUT_S still 5.0 ---"
grep -n '_STOP_JOIN_TIMEOUT_S: float = 5.0' voice_typing/recorder_host.py && echo "L1c PASS" || echo "L1c FAIL"
echo "--- only ONE _stop_lock creation site ---"
test "$(grep -c '_stop_lock = threading.Lock()' voice_typing/recorder_host.py)" -eq 1 && echo "L1d PASS" || echo "L1d FAIL"
# Expected: L1a–L1d PASS; the awk shows guard_line = with_line+1 (guard immediately inside the with).
```

### Level 2: Existing recorder_host suite stays green (incl. the two stop() tests)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_recorder_host.py -v 2>&1 | tail -8
# Expected: 20 passed. Critically these two must be PASSED:
#   test_stop_is_noop_when_no_process
#   test_stop_with_dead_process_is_noop
.venv/bin/python -m pytest tests/test_recorder_host.py -k "stop" -v 2>&1 | tail -6
```

### Level 3: No regressions in the broader daemon suite (exercises _bounded_shutdown -> host.stop)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q 2>&1 | tail -8
# Expected: all pass. test_daemon.py exercises the daemon shutdown paths that CALL host.stop(); if
# S1's lock introduced a deadlock or changed single-caller behavior, these would fail.

# OPTIONAL manual concurrency smoke (NOT a committed test — S2 owns the regression test):
.venv/bin/python - <<'PY'
import threading, tests.test_recorder_host as t   # reuse the test helper's _make_host()
host = t._make_host()
calls = []
def go(): 
    host.stop(); calls.append(threading.get_ident())
a = threading.Thread(target=go); b = threading.Thread(target=go)
a.start(); b.start(); a.join(); b.join()
print("both callers returned:", len(calls) == 2, "; _proc is None:", host._proc is None)
PY
# Expected (with _proc=None via _make_host): both callers return, _proc stays None, no error.
# (A meaningful TWO-TEARDOWN-PROOF test needs a fake proc with a blocking join — that is S2.)
```

### Level 4: Scope — only recorder_host.py changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY voice_typing/recorder_host.py ---"
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/recorder_host\.py' | grep -E '\.py$|systemd/|tests/|config' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: only recorder_host.py"
# Expected: "only recorder_host.py". (Pre-existing orchestrator entries under plan/ are fine.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1a: `_stop_lock = threading.Lock()` present in `__init__` (exactly once).
- [ ] L1b: `with self._stop_lock:` wraps the body; `if self._proc is None: return` is the first statement inside it.
- [ ] L1c: `_STOP_JOIN_TIMEOUT_S` still `5.0`.
- [ ] L2: `tests/test_recorder_host.py` 20/20 (incl. both `stop()` idempotency tests).
- [ ] L3: `tests/test_recorder_host.py tests/test_daemon.py` green (no deadlock/behavior regression).
- [ ] L4: only `voice_typing/recorder_host.py` changed.

### Feature Validation
- [ ] `stop()` docstring documents single-flight + the SIGTERM double-caller rationale.
- [ ] Two concurrent `stop()` callers cannot run two teardowns (the guard-inside-the-lock invariant).
- [ ] Single-caller behavior unchanged (lock uncontended → identical body).

### Code Quality Validation
- [ ] Body correctly re-indented one level; no statement left outside the `with`.
- [ ] No second lock added in `_terminate_group`; no `RLock` (plain `Lock`, no re-entrancy).
- [ ] Comments/docstrings match the file's existing style.

### Scope Boundary Validation
- [ ] `daemon.py` unmodified (T2 owns daemon-side `_shutdown_done`/`_teardown_done` + 10s→5s).
- [ ] No test added/edited (S2 owns the concurrent-calls regression).
- [ ] No config/systemd/install.sh/README changes.

---

## Anti-Patterns to Avoid

- ❌ Don't leave `if self._proc is None: return` OUTSIDE `with self._stop_lock:` — that defeats single-flight (two callers pass it concurrently). The guard MUST be inside the with.
- ❌ Don't use `RLock` — `stop()` is never re-entered (verified); a plain `threading.Lock()` is correct and clearer.
- ❌ Don't add a lock inside `_terminate_group` — it's only called from `stop()` (which already holds `_stop_lock`); a second lock is dead code.
- ❌ Don't change `_STOP_JOIN_TIMEOUT_S` (5.0) or `stop()`'s signature — the contract only adds the lock.
- ❌ Don't edit `daemon.py` to "also fix it here" — the daemon-side coordination (`_shutdown_done` + `_teardown_done`) and the 10s→5s timeout are T2's scope.
- ❌ Don't commit a concurrency regression test in S1 — that's S2 (P1.M1.T1.S2). S1's gate is the existing suite staying green.
- ❌ Don't invoke ruff/mypy — they're not configured in this project; the gates are pytest + static checks.
- ❌ Don't assume S1 alone makes the SIGTERM stop sub-15s — S1 removes the DOUBLED teardown; the single-teardown margin under a wedged child comes from T2.S2 (10s→5s).

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is one `Lock` + one indentation level at verified locations (`__init__` primitives @134-139, `stop()` @250-282), with the load-bearing invariant (guard inside the lock) stated explicitly and checked by gate L1b. No re-entrancy exists (verified by grep), so a plain `Lock` cannot deadlock; the existing two `stop()` tests stay green by construction (uncontended single-caller path is unchanged); and the broader `test_daemon.py` suite exercises the `host.stop()` call paths. The −0.5 is that the *concurrency* proof (two callers → one teardown) is only formally asserted by S2's not-yet-written test — S1's L3 provides a manual smoke but not the committed regression.
