# PRP — P1.M1.T2.S1: Single-flight daemon shutdown coordination (`_shutdown_done` + `_teardown_done`)

## Goal

**Feature Goal**: Eliminate bugfix **Issue 1**'s daemon-level double-teardown on the SIGTERM path. Today `request_shutdown()` (signal-handler thread) tears the child down via `_bounded_shutdown()` but deliberately does NOT set the `_shutdown_done` idempotency flag — so when `main()`'s `finally`-block `daemon.shutdown()` runs **concurrently on the main thread**, it sees `_shutdown_done=False`, sets it, and calls `_bounded_shutdown()` → `host.stop()` **a second time, concurrently**. Two parallel multi-second teardowns + `ControlServer.stop()`'s join blow systemd's 15s `TimeoutStopSec` → SIGKILL + `Failed with result 'timeout'` (reproduced 2/2 at 15.2s). Fix it with **daemon-level single-flight coordination**: `request_shutdown()` claims `_shutdown_done` under `_lock` and signals a new `_teardown_done` `threading.Event` when its teardown finishes; `shutdown()` — if `_shutdown_done` is already claimed — **waits** on `_teardown_done` (bounded, outside `_lock`) instead of starting its own `_bounded_shutdown()`. Composes with T1.S1's `RecorderHost._stop_lock` (the belt-and-suspenders that makes the wait-timeout fallback safe).

**Deliverable** (one source file + its unit tests, no new files):
1. `voice_typing/daemon.py` — (i) `__init__`: add `self._teardown_done = threading.Event()`; (ii) `request_shutdown()`: claim `_shutdown_done` under `_lock` before the teardown, set `_teardown_done` in a `finally`, early-return if already claimed; (iii) `shutdown()`: if `_shutdown_done` already claimed, wait on `_teardown_done` (bounded) then return, else claim + do the teardown + signal; (iv) a module constant for the wait timeout (testability).
2. `tests/test_daemon.py` — focused unit tests proving: the claim/signal, the SIGTERM-path wait-no-second-stop, the quit-path immediate-return, the called-first own-teardown, the idempotent second `request_shutdown`, and the wait-timeout fallback.

**Success Definition**:
- (a) `request_shutdown()` sets `self._shutdown_done = True` under `self._lock` BEFORE calling `_bounded_shutdown()`, and sets `self._teardown_done` in a `try/finally` (always fires, even on exception).
- (b) A second `request_shutdown()` (double signal, or quit+signal overlap) returns early without re-tearing-down (`_shutdown_done` already True) — idempotent.
- (c) `shutdown()`, when `_shutdown_done` is already True, does **NOT** call `_bounded_shutdown()`/`host.stop()` — it waits on `_teardown_done` (bounded, OUTSIDE `_lock`) and returns when the in-flight teardown finishes.
- (d) `shutdown()`, when `_shutdown_done` is NOT yet claimed (normal/called-first path), claims it, does the teardown, and signals `_teardown_done` (existing behavior preserved).
- (e) On the SIGTERM path exactly ONE `host.stop()` runs (the signal thread's); `main()`'s `shutdown()` waits for it.
- (f) The wait is bounded; if `_teardown_done` doesn't fire in the timeout (signal thread died), `shutdown()` logs a warning and falls back to its own `_bounded_shutdown()` (safe via T1.S1's `_stop_lock`).
- (g) All new unit tests pass; the full `tests/test_daemon.py` suite stays green; `git diff` == `daemon.py` + `test_daemon.py`.

## User Persona

**Target User**: The user who runs `systemctl --user stop voice-typing` (or logs out, which systemd signals with SIGTERM) and expects a clean, prompt stop — not a 15.2s hang + SIGKILL.

**Use Case**: SIGTERM arrives while armed. The signal thread runs `request_shutdown()` (the one teardown); the main thread's `shutdown()` waits for it instead of racing a second teardown. Stop completes bounded (single teardown + `server.stop()`), cleanly under `TimeoutStopSec=15`.

**Pain Points Addressed**: Issue 1 — every armed `systemctl stop` hung 15.2s and was SIGKILLed (`Failed with result 'timeout'`), the exact symptom PRD §8/§7.9 say MUST NOT happen. The `voicectl quit` path worked (sequential), but the SIGTERM path (concurrent) raced a double teardown. This subtask makes the daemon-level teardown single-flight on BOTH paths.

## Why

- **PRD §4.2bis / §8 / §7.9 make bounded teardown a hard prerequisite** (for idle-unload and on its own). Issue 1 is the Critical regression: the SIGTERM double-teardown blows the 15s budget. This subtask is the **daemon-level** half of the three-part fix (Fix 1B in `bug_analysis.md`): 1A = `RecorderHost._stop_lock` (T1.S1, **Complete** — makes two concurrent `host.stop()` calls share one teardown); 1B = **this subtask** (makes `shutdown()` not even START a second `_bounded_shutdown()`); 1C = reduce `_bounded_shutdown` 10s→5s (T2.S2, separate — tightens the budget so single-teardown + `server.stop()` ≤ ~9s).
- **1A alone is not enough at the daemon layer.** Even with `_stop_lock`, the daemon still issues TWO `_bounded_shutdown()` calls on SIGTERM; the second blocks on `_stop_lock` then no-ops, but the coordination is wasteful and the timing is tight (~14s with the current 10s timeout). 1B makes `shutdown()` WAIT for the in-flight teardown instead — clean, and it returns the instant the teardown finishes.
- **Belt-and-suspenders with 1A.** The wait has a bounded timeout; if the signal thread died without finishing, `shutdown()` falls back to its own `_bounded_shutdown()` → `host.stop()`, which 1A's `_stop_lock` keeps single-flight. So even the fallback path cannot reproduce the double-teardown.
- **Scope discipline.** This subtask owns ONLY the daemon-level coordination (`request_shutdown`/`shutdown`/`__init__` + a wait-timeout constant) + its unit tests. It does NOT change `_bounded_shutdown`'s timeout (T2.S2), does NOT touch `recorder_host.py` (T1.S1), does NOT add the heavier SIGTERM-subprocess simulation test (T2.S3), and does NOT change config/systemd/README.

## What

Three coordinated edits to `voice_typing/daemon.py` + unit tests in `tests/test_daemon.py`:

1. **`__init__`**: add `self._teardown_done = threading.Event()` immediately after `self._shutdown = threading.Event()`. (`_shutdown_done` stays `getattr`-guarded per the existing pattern — NOT initialized in `__init__`.)
2. **Module constant** (near the other daemon constants): `_TEARDOWN_WAIT_TIMEOUT = 8.0` — the bounded wait `shutdown()` uses for an in-flight teardown. A named constant (not an inline literal) so the fallback unit test can monkeypatch it to ~0.2s and stay fast.
3. **`request_shutdown()`**: after the existing `_shutdown.set()` + `if self._host is None: return`, add a `_lock`-guarded claim (`if getattr(self,"_shutdown_done",False): return; self._shutdown_done = True`), then `self._safe_abort()`, then `try: self._bounded_shutdown() finally: self._teardown_done.set()`.
4. **`shutdown()`**: restructure so the `_shutdown_done`-already-True case **waits** on `_teardown_done` (bounded, outside `_lock`) and returns, instead of returning immediately / re-tearing-down. The called-first path (claim + teardown + signal) is preserved.
5. **Tests** (`tests/test_daemon.py`): 6 focused unit tests with minimal `_CountingHost`/`_GatedHost` fakes (only `.stop()` needed) proving the claim/signal, the wait-no-second-stop (SIGTERM path), the immediate-return (quit path), the called-first teardown, the idempotent second `request_shutdown`, and the wait-timeout fallback.

### Success Criteria

- [ ] `__init__` creates `self._teardown_done = threading.Event()` (right after `self._shutdown`).
- [ ] `request_shutdown()`: claims `_shutdown_done=True` under `_lock` before `_bounded_shutdown()`; sets `_teardown_done` in `finally`; early-returns if `_shutdown_done` already True.
- [ ] `shutdown()`: when `_shutdown_done` already True, waits on `_teardown_done` (timeout `_TEARDOWN_WAIT_TIMEOUT`, OUTSIDE `_lock`) and returns on completion; on timeout logs a warning and falls back to its own `_bounded_shutdown()`.
- [ ] `shutdown()` called-first path: claims `_shutdown_done`, does `_bounded_shutdown()`, sets `_teardown_done` (existing behavior preserved).
- [ ] `_TEARDOWN_WAIT_TIMEOUT = 8.0` module constant exists and is referenced by `shutdown()`.
- [ ] New unit tests pass (claim/signal, wait-no-second-stop, immediate-return, called-first, idempotent, fallback); full `tests/test_daemon.py` green.
- [ ] `git diff --name-only` == `voice_typing/daemon.py` + `tests/test_daemon.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact current bodies of `request_shutdown()` (L1136-1163), `_bounded_shutdown()` (L1265-1283), `shutdown()` (L1285-1332), and `__init__`'s Event block (L541-542) are verified verbatim below; the three-part fix strategy (1A/1B/1C) is confirmed in `bug_analysis.md`; the test fakes (`_make_daemon(recorder_host=...)` injects a host; only `.stop()` is needed for the teardown path) are confirmed; and the no-conflict boundary with T1.S1 (`recorder_host.py`) and T2.S2 (`_bounded_shutdown` timeout) is explicit. A developer new to this repo can implement 1B from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the fix strategy (1A/1B/1C) this subtask implements (1B)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: §Issue 1 "Fix Strategy" spells out the three measures. Fix 1B (THIS subtask): "request_shutdown()
       sets _shutdown_done under _lock + a _teardown_done Event it sets on completion; shutdown(), if
       _shutdown_done already True, waits on _teardown_done (bounded ~8s) then return — do NOT start a
       second _bounded_shutdown()." Fix 1A (T1.S1 Complete) = RecorderHost._stop_lock; Fix 1C (T2.S2) =
       10s->5s. The "Key Code Locations" + "Test Gap" sections are cited below.
  critical: "1B is the daemon-level single-flight. It COMPOSES with 1A (the fallback is safe because
            _stop_lock serializes host.stop) and with 1C (the ~9s wall-time target needs 1C's 5s timeout).
            1B alone fixes the double-teardown BUG; 1C tightens the budget."

# MUST READ — the defect (root cause + the concurrent-threads difference vs the quit path)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: §Issue 1 documents the SIGTERM double-host.stop() race: request_shutdown on the signal thread +
       shutdown on the main-thread finally, CONCURRENTLY (vs the quit path, sequential on one socket
       worker thread). The journal evidence (run() exits +0.5s, then ~13.7s silence, SIGKILL at 15.2s).
  critical: "The fix MUST handle CONCURRENCY: request_shutdown (thread A) + shutdown (thread B) overlap.
            A pure flag-set races the concurrent read — that's WHY the _teardown_done Event + bounded
            wait is required, not just the flag."

# THE EDIT SITE — the three methods (verbatim current bodies)
- file: voice_typing/daemon.py
  why: __init__ Event block L541-542 (`self._listening=Event(); self._shutdown=Event()`); request_shutdown
        L1136-1163 (sets _shutdown; `if self._host is None: return`; _safe_abort(); _bounded_shutdown();
        does NOT touch _shutdown_done — its docstring says so); _bounded_shutdown L1265-1283 (None-host
        no-op; try host.stop except logger.exception; does NOT null _host); shutdown L1285-1332
        (`with self._lock: if getattr(self,"_shutdown_done",False): return; self._shutdown_done=True`;
        None-host return; try _bounded_shutdown except logger.exception). threading imported (L346 area).
  pattern: "request_shutdown + _bounded_shutdown already run OUTSIDE _lock (the docstring emphasizes a
            slow teardown must not wedge the shutdown signal / block start/stop/toggle). Keep the new
            _bounded_shutdown call + the _teardown_done.wait OUTSIDE _lock. Only the _shutdown_done
            claim is under _lock (short critical section)."
  gotcha: "_bounded_shutdown does NOT null self._host, so a second request_shutdown still sees host not
           None — that's fine: it hits the _shutdown_done guard and returns. Do NOT add host-nulling here."

# THE BELT-AND-SUSPENDERS (Complete) — why the fallback is safe
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T1S1/PRP.md
  why: T1.S1 added RecorderHost._stop_lock wrapping stop()'s body (guard included). So even if 1B's
        wait times out and shutdown() falls back to its own _bounded_shutdown()->host.stop(), the TWO
        host.stop() calls serialize: the second blocks on _stop_lock then sees _proc is None and no-ops.
        => the fallback CANNOT reproduce the double-teardown.
  critical: "1B's wait-timeout fallback is ONLY safe because of 1A. Do NOT remove/relax the fallback's
            _bounded_shutdown() call — it is the 'signal thread died' recovery, and 1A makes it harmless."

# THE PARALLEL ITEM (no-conflict boundary)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T1S2/PRP.md
  why: T1.S2 (Complete) added the RecorderHost-LEVEL concurrent-stop test (tests/test_recorder_host.py).
        It explicitly does NOT touch daemon.py ("T2 owns daemon-side _shutdown_done/_teardown_done").
        T2.S1 = daemon level; T1.S2 = RecorderHost level. Distinct files, no conflict.
  critical: "Do NOT duplicate T1.S2's host.stop()-level test. T2.S1's tests are DAEMON-level
            (request_shutdown + shutdown coordination). The heavier SIGTERM-subprocess simulation is T2.S3."

# THE TEST FILE — fakes + the injection seam
- file: tests/test_daemon.py
  why: _make_daemon(*, recorder=None, recorder_host=None, host_factory=None, ...) L512 — passing
        recorder_host=<fake> sets self._host=<fake> in __init__ (recorder_host wins over recorder).
        _FakeHost L434 has stop_calls (L456, incremented L484) — but needs (cfg,feedback,latency,...)
        ctor args. For the coordination tests a MINIMAL fake with only .stop() suffices (the daemon
        calls no other host method in the teardown path). Existing shutdown/request_shutdown tests
        L804-1095 show the assertion style. threading + time already imported in this file.
  pattern: "Define _CountingHost (stop_calls counter) and _GatedHost (stop() blocks on a release Event
            to simulate an in-flight teardown) INNER to the test section. Inject via _make_daemon(
            recorder_host=fake). Assert on fake.stop_calls + d._shutdown_done + d._teardown_done.is_set()."
  critical: "_make_daemon ALWAYS also creates a _StubRecorder, but recorder_host takes precedence in
            __init__ — the stub is ignored. The coordination tests only call request_shutdown()/shutdown()
            (NOT run()/start()), so the fake needs ONLY .stop(timeout=None). No other host method is hit."

# TEST INFRASTRUCTURE
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/test_infrastructure.md
  why: Documents pytest + monkeypatch (for the wait-timeout override) + the SIGTERM-concurrent-teardown
        coverage gap. Confirms the fast-suite hermetic philosophy (tests must be <~1s — hence the
        _TEARDOWN_WAIT_TIMEOUT constant so the fallback test monkeypatches it to ~0.2s).
  section: "'Existing Test Coverage Gaps' — SIGTERM concurrent teardown row — T2.S1 (unit) + T2.S3 (subprocess)."
```

### Current Codebase tree (relevant slice — T1.S1 Complete; T2.S2 not yet landed)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py             # ← EDIT: __init__ (+_teardown_done); request_shutdown (claim+signal);
│   │                         #   shutdown (wait branch); +_TEARDOWN_WAIT_TIMEOUT constant.
│   │                         #   request_shutdown @1136-1163; _bounded_shutdown @1265-1283;
│   │                         #   shutdown @1285-1332; __init__ Events @541-542. threading already imported.
│   └── recorder_host.py      # T1.S1 APPLIED (_stop_lock). READ-ONLY for T2.S1.
└── tests/
    └── test_daemon.py        # ← EDIT: +6 coordination tests (+_CountingHost/_GatedHost fakes).
                              #   _make_daemon L512 (recorder_host= seam); existing shutdown tests L804-1095.
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/daemon.py        # MODIFY: +_teardown_done in __init__; request_shutdown claim+signal; shutdown wait; +_TEARDOWN_WAIT_TIMEOUT.
tests/test_daemon.py          # MODIFY: +_CountingHost/_GatedHost fakes; +6 coordination tests. NO new files.
# No recorder_host.py (T1.S1), no _bounded_shutdown timeout change (T2.S2), no config/systemd/README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE FLAG ALONE IS NOT ENOUGH; YOU NEED THE EVENT + WAIT. A naive "request_shutdown
# sets _shutdown_done; shutdown() returns if _shutdown_done" RACES: run() can exit (~0.5s) and reach
# shutdown() BEFORE request_shutdown's _lock-protected claim executes. The _teardown_done Event +
# bounded wait is what makes shutdown() BLOCK until the in-flight teardown is OBSERVED finished,
# eliminating the race. (bug_analysis.md Fix 1B; PRD §Issue 1 root cause.) Do NOT ship flag-only.

# CRITICAL #2 — _bounded_shutdown + the _teardown_done.wait MUST RUN OUTSIDE _lock. request_shutdown's
# docstring (L1146-1156) emphasizes the teardown runs outside _lock so a slow host.stop() doesn't wedge
# the shutdown signal or block concurrent start/stop/toggle (which take _lock via _arm/_disarm). Only
# the _shutdown_done claim is a short under-_lock critical section. shutdown()'s wait is OUTSIDE _lock
# (else a long teardown would hold _lock for ~7s). Match the existing outside-_lock discipline.

# CRITICAL #3 — _teardown_done MUST BE SET IN A finally. request_shutdown does `_safe_abort()` then
# `_bounded_shutdown()`. If either raises, _teardown_done must STILL fire or shutdown()'s waiter dead-
# locks until the timeout. Wrap the teardown in try/finally: `try: self._bounded_shutdown() finally:
# self._teardown_done.set()`. (_bounded_shutdown is itself best-effort/never-reraises, but _safe_abort
# or a future change could — the finally is the guarantee.)

# CRITICAL #4 — THE WAIT TIMEOUT MUST BE A NAMED CONSTANT (testability). Hardcoding `wait(timeout=8.0)`
# makes the fallback unit test take 8s (breaks the fast-suite <~1s philosophy). Define
# `_TEARDOWN_WAIT_TIMEOUT = 8.0` at module level; shutdown() references it; the fallback test does
# `monkeypatch.setattr(daemon, "_TEARDOWN_WAIT_TIMEOUT", 0.2)`. The value 8.0 covers 1C's ~7s teardown
# (5s join + 2s second join) with margin; with the current 10s timeout (pre-T2.S2) it may time out and
# fall back — that's correct + safe (CRITICAL #5).

# CRITICAL #5 — THE FALLBACK IS SAFE ONLY BECAUSE OF T1.S1's _stop_lock. If the wait times out (signal
# thread died, or the teardown is slower than 8s under the current 10s timeout), shutdown() falls back
# to its own _bounded_shutdown() -> host.stop(). RecorderHost._stop_lock (T1.S1, Complete) serializes
# the two host.stop() calls: the fallback's blocks on _stop_lock, then sees _proc is None, no-ops. So
# the fallback CANNOT reproduce the double-teardown. Do NOT remove the fallback; do NOT make the wait
# unbounded (a dead signal thread must not hang shutdown()).

# CRITICAL #6 — _bounded_shutdown DOES NOT null _host. So after request_shutdown's teardown, _host is
# still non-None. A second request_shutdown: _shutdown.set() (idempotent), host not None -> claim check
# -> _shutdown_done True -> return. Idempotent. (Do NOT add host-nulling in this subtask — out of scope
# and _unload_host owns that.)

# GOTCHA #7 — _make_daemon ALWAYS creates a _StubRecorder even when recorder_host is passed, but
# recorder_host wins in __init__. So _make_daemon(recorder_host=fake) gives self._host=fake; the stub
# is ignored. The coordination tests only call request_shutdown()/shutdown() (never run()/start()), so
# the fake host needs ONLY .stop(timeout=None). No other host method is invoked in the teardown path.

# GOTCHA #8 — DON'T INITIALIZE _shutdown_done IN __init__. It is (and stays) getattr-guarded so the
# existing tests that construct a daemon without ever shutting down don't carry the attribute. Only
# ADD _teardown_done (an Event, which MUST be constructed). The getattr(self,"_shutdown_done",False)
# reads in request_shutdown/shutdown keep working once request_shutdown sets the real attribute.

# GOTCHA #9 — DON'T CHANGE _bounded_shutdown's TIMEOUT (10.0) HERE. That is T2.S2 (10s->5s). T2.S1
# keeps _bounded_shutdown() calls unchanged (request_shutdown's + shutdown()'s both use its default).
# The ~9s wall-time TARGET (contract OUTPUT) composes T2.S1 + T2.S2; T2.S1 alone fixes the double-
# teardown bug (the must-pass), with wall-time bounded by a SINGLE teardown under the current 10s.

# GOTCHA #10 — DON'T BUILD THE SUBPROCESS SIGTERM TEST HERE. T2.S3 owns "concurrent request_shutdown +
# shutdown (SIGTERM path simulation)" with a real subprocess. T2.S1's tests are deterministic UNIT
# tests with fakes (the _GatedHost simulates the in-flight teardown without a real child). Keep them
# separate: T2.S1 = logic proof; T2.S3 = end-to-end SIGTERM proof.

# GOTCHA #11 — FULL PATHS. `.venv/bin/python -m pytest` (machine aliases python3->uv run). No
# ruff/mypy configured in this project — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

No ORM/pydantic. The only new "structure" is one `threading.Event` (`self._teardown_done`), one module constant (`_TEARDOWN_WAIT_TIMEOUT = 8.0`), and the `_shutdown_done` claim/wait coordination between `request_shutdown()` and `shutdown()`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — add _teardown_done Event + the _TEARDOWN_WAIT_TIMEOUT constant
  - FIND the __init__ Event block (L541-542):
        self._listening = threading.Event()   # cleared → NOT listening at boot (PRD §4.9)
        self._shutdown = threading.Event()    # cleared → keep looping
  - EDIT: add ONE line immediately after self._shutdown:
        self._shutdown = threading.Event()    # cleared → keep looping
        self._teardown_done = threading.Event()  # P1.M1.T2.S1 / bugfix Issue 1: signaled when the
        #   in-flight _bounded_shutdown() finishes, so a concurrent shutdown() can WAIT for it
        #   instead of starting a second teardown (SIGTERM double-teardown fix). Set in
        #   request_shutdown()'s finally + shutdown()'s finally.
  - ADD a module constant near the other daemon-level constants (e.g. near _LATENCY_RING_SIZE / the
    partial-callback constant), NOT inside the class:
        # P1.M1.T2.S1 / bugfix Issue 1: bounded wait shutdown() uses for an in-flight teardown claimed
        # by request_shutdown() (the SIGTERM signal thread). 8.0s covers a ~7s teardown (5s join +
        # 2s second join, post-T2.S2) with margin; a timeout falls back to shutdown()'s OWN teardown
        # (safe — RecorderHost._stop_lock serializes host.stop, P1.M1.T1.S1). A named constant (not a
        # literal) so the fallback unit test can monkeypatch it to ~0.2s and stay fast.
        _TEARDOWN_WAIT_TIMEOUT = 8.0
  - DO NOT initialize _shutdown_done in __init__ (it stays getattr-guarded — Gotcha #8).

Task 2: MODIFY voice_typing/daemon.py — request_shutdown() claims _shutdown_done + signals _teardown_done
  - FIND request_shutdown() body (L1156-1163), which currently ends:
        self._shutdown.set()
        if self._host is None:
            return  # nothing loaded (never armed, or already torn down) -> _shutdown is enough
        # abort() gated on _text_in_flight ...
        self._safe_abort()    # break any blocked text() so run() can return promptly (NOT under _lock)
        # Tear down the child (BUG-1) ...
        self._bounded_shutdown()
  - EDIT: insert the claim BEFORE _safe_abort, and wrap the teardown in try/finally:
        self._shutdown.set()
        if self._host is None:
            return  # nothing loaded (never armed, or already torn down) -> _shutdown is enough
        # P1.M1.T2.S1 / bugfix Issue 1: CLAIM the teardown so a concurrent shutdown() (main-thread
        # finally, on the SIGTERM path) WAITS on _teardown_done instead of starting a SECOND
        # _bounded_shutdown() (the double-teardown that blew TimeoutStopSec). Under _lock (short
        # critical section); the teardown itself runs OUTSIDE _lock (see CRITICAL #2). Idempotent: a
        # second signal / quit+signal overlap sees _shutdown_done already True and returns here.
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return  # another path already claimed/is doing the teardown — don't re-tear-down
            self._shutdown_done = True
        # abort() gated on _text_in_flight (validation Issue 1; see _safe_abort): when no thread is
        # blocked in text() there is nothing to wake — abort() would hang forever.
        self._safe_abort()    # break any blocked text() so run() can return promptly (NOT under _lock)
        # Tear down the child (BUG-1): kills the process group so host.text()'s wait-loop detects
        # child death and returns, unblocking the run() loop for a prompt, bounded SIGTERM exit.
        # P1.M1.T2.S1: wrap in try/finally so _teardown_done ALWAYS fires — a concurrent shutdown()
        # is waiting on it (a missing signal would deadlock it until the wait timeout).
        try:
            self._bounded_shutdown()
        finally:
            self._teardown_done.set()
  - ALSO: refresh the request_shutdown DOCSTRING — replace the "Routing the teardown through
    _bounded_shutdown() (NOT shutdown()'s _shutdown_done guard) lets the idempotent shutdown() in
    main()'s finally still run as a belt-and-suspenders no-op." sentence with: "P1.M1.T2.S1: this
    method CLAIMS _shutdown_done under _lock and signals _teardown_done on completion, so a CONCURRENT
    shutdown() (main-thread finally, on the SIGTERM path) WAITS for this teardown instead of starting
    a second one (bugfix Issue 1). The quit path is unaffected (sequential: shutdown() sees
    _teardown_done already set and returns immediately)."
  - DO NOT: null _host; move the claim inside the teardown; drop the _safe_abort() / host-None guard.

Task 3: MODIFY voice_typing/daemon.py — shutdown() waits for an in-flight teardown (the core change)
  - FIND shutdown()'s guard + body (L1307-1332), currently:
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return
            self._shutdown_done = True
        if self._host is None:
            ... return
        try:
            self._bounded_shutdown()
        except Exception:
            logger.exception("bounded teardown failed (best-effort; ignored)")
  - EDIT: restructure so the already-claimed case WAITS (bounded, outside _lock) then returns, with a
    fallback to its own teardown on timeout:
        # P1.M1.T2.S1 / bugfix Issue 1: daemon-level single-flight. If request_shutdown() (the SIGTERM
        # signal thread) already CLAIMED _shutdown_done, a second _bounded_shutdown() here would race
        # it (the double-teardown that blew TimeoutStopSec). Instead WAIT on _teardown_done (bounded,
        # OUTSIDE _lock — a slow teardown must not hold _lock) and return when it finishes. On timeout
        # (signal thread died) fall back to our OWN teardown — safe because RecorderHost._stop_lock
        # (P1.M1.T1.S1) serializes host.stop(), so the fallback cannot reproduce the double-teardown.
        with self._lock:
            already_claimed = getattr(self, "_shutdown_done", False)
            if not already_claimed:
                self._shutdown_done = True        # WE claim the teardown (called-first / normal path)
        if already_claimed:
            # Another path is doing (or did) the teardown — wait for it, do NOT start a second one.
            if self._teardown_done.wait(timeout=_TEARDOWN_WAIT_TIMEOUT):
                return                           # in-flight teardown finished -> done (no second teardown)
            logger.warning(
                "shutdown(): in-flight teardown did not signal within %.1fs; proceeding with fallback",
                _TEARDOWN_WAIT_TIMEOUT,
            )
            # fall through: do our own teardown as the fallback (safe via _stop_lock)
        if self._host is None:
            # M2 lazy-load prep: the recorder-host child is spawned on first arm, so it may never
            # exist (e.g. a session that never armed). Nothing to tear down.
            return
        try:
            self._bounded_shutdown()
        except Exception:
            # Defensive belt-and-suspenders: _bounded_shutdown is already best-effort, but
            # shutdown() itself must NEVER re-raise (a teardown failure must not mask the original
            # shutdown reason).
            logger.exception("bounded teardown failed (best-effort; ignored)")
        finally:
            # P1.M1.T2.S1: signal any waiter (covers the called-first path + the fallback path).
            self._teardown_done.set()
  - ALSO: refresh the shutdown DOCSTRING — update the "IDEMPOTENT: a getattr-guarded flag ... make a
    double call (quit on_quit + main() finally) a no-op the second time." paragraph to: "IDEMPOTENT +
    SINGLE-FLIGHT (P1.M1.T2.S1 / bugfix Issue 1): _shutdown_done (under _lock) + _teardown_done
    (Event) coordinate the SIGTERM path, where request_shutdown() (signal thread) + this method
    (main-thread finally) run CONCURRENTLY. The first caller claims + does the teardown + signals
    _teardown_done; a concurrent second caller WAITS on _teardown_done (bounded _TEARDOWN_WAIT_TIMEOUT)
    instead of starting a second _bounded_shutdown(). The quit path (sequential) sees _teardown_done
    already set and returns immediately. A wait timeout falls back to this method's own teardown,
    kept single-flight by RecorderHost._stop_lock (P1.M1.T1.S1)."
  - DO NOT: hold _lock during the wait or during _bounded_shutdown; make the wait unbounded; remove the
    None-host guard or the defensive try/except.

Task 4: ADD tests/test_daemon.py — 6 coordination unit tests (+ _CountingHost / _GatedHost fakes)
  - PLACE: a new section after the existing shutdown/request_shutdown tests (~after L1095), under a
    banner comment, e.g.:
        # ===========================================================================
        # P1.M1.T2.S1 — daemon-level single-flight shutdown coordination (bugfix Issue 1)
        # (_shutdown_done claim + _teardown_done Event; request_shutdown + shutdown concurrency.)
        # ===========================================================================
  - ADD the two minimal fakes + 6 tests. Reference implementation (copy-ready; threading + time already
    imported in this file; `daemon` + `threading`/`time` in scope):

        class _CountingHost:
            """Minimal host for shutdown-coordination tests: counts stop() calls. The daemon calls no
            other host method in the teardown path (only host.stop()), so this suffices."""

            def __init__(self) -> None:
                self.stop_calls = 0

            def stop(self, timeout: float | None = None) -> None:
                self.stop_calls += 1

        class _GatedHost:
            """Host whose stop() BLOCKS until the test releases it — simulates an in-flight teardown so
            a concurrent shutdown() can be observed WAITING (not starting its own stop)."""

            def __init__(self) -> None:
                self.stop_calls = 0
                self.entered = threading.Event()
                self.release = threading.Event()

            def stop(self, timeout: float | None = None) -> None:
                self.stop_calls += 1
                self.entered.set()
                self.release.wait(timeout=5.0)  # block until the test releases (bounded — no hang)


        def test_request_shutdown_claims_and_signals_teardown_done():
            """request_shutdown claims _shutdown_done + signals _teardown_done (the SIGTERM-path contract)."""
            host = _CountingHost()
            d, *_ = _make_daemon(recorder_host=host)
            assert not d._teardown_done.is_set()
            d.request_shutdown()
            assert d._shutdown_done is True
            assert d._teardown_done.is_set()    # finally fired
            assert host.stop_calls == 1          # exactly one teardown


        def test_shutdown_does_own_teardown_when_called_first():
            """Normal/called-first path: shutdown() claims + does the teardown + signals _teardown_done."""
            host = _CountingHost()
            d, *_ = _make_daemon(recorder_host=host)
            assert not d._teardown_done.is_set()
            d.shutdown()
            assert d._shutdown_done is True
            assert d._teardown_done.is_set()
            assert host.stop_calls == 1


        def test_shutdown_waits_for_inflight_teardown_no_second_stop():
            """SIGTERM path (core fix): while request_shutdown's teardown is in flight, a concurrent
            shutdown() WAITS on _teardown_done and does NOT start a second host.stop()."""
            host = _GatedHost()
            d, *_ = _make_daemon(recorder_host=host)
            # Thread A (signal thread): request_shutdown -> host.stop() blocks on `release`.
            ta = threading.Thread(target=d.request_shutdown, name="sig")
            ta.start()
            assert host.entered.wait(timeout=2.0), "request_shutdown did not reach host.stop()"
            # Claim is made; teardown in flight; _teardown_done NOT yet set.
            assert d._shutdown_done is True
            assert not d._teardown_done.is_set()
            # Thread B (main-thread finally analog): shutdown() must WAIT, not start a 2nd host.stop().
            main_done = threading.Event()

            def _main_shutdown():
                d.shutdown()
                main_done.set()

            tm = threading.Thread(target=_main_shutdown, name="main", daemon=True)
            tm.start()
            time.sleep(0.2)                       # let shutdown() reach _teardown_done.wait()
            assert host.stop_calls == 1, "shutdown() started a 2nd host.stop() while it should WAIT"
            assert not main_done.is_set(), "shutdown() returned before the in-flight teardown finished"
            # Release the in-flight teardown -> request_shutdown finishes -> _teardown_done set ->
            # shutdown()'s wait returns -> main_done set. Exactly ONE host.stop().
            host.release.set()
            ta.join(timeout=5.0)
            tm.join(timeout=5.0)
            assert main_done.is_set(), "shutdown() did not return after the teardown finished"
            assert host.stop_calls == 1, "exactly ONE host.stop() — shutdown() waited, no double-teardown"


        def test_shutdown_returns_immediately_when_teardown_already_done():
            """Quit path (sequential): after request_shutdown finishes, shutdown() sees _teardown_done
            already set and returns immediately (no second host.stop())."""
            host = _CountingHost()
            d, *_ = _make_daemon(recorder_host=host)
            d.request_shutdown()                  # teardown done + _teardown_done set
            assert host.stop_calls == 1
            d.shutdown()                          # the on_quit call, strictly after
            assert host.stop_calls == 1, "shutdown() re-tore-down on the sequential quit path"


        def test_request_shutdown_idempotent_vs_second_call():
            """A second request_shutdown (double signal / quit+signal overlap) returns without
            re-tearing-down (single-flight)."""
            host = _CountingHost()
            d, *_ = _make_daemon(recorder_host=host)
            d.request_shutdown()
            d.request_shutdown()                  # second call — must no-op
            assert host.stop_calls == 1, "second request_shutdown re-tore-down"
            assert d._teardown_done.is_set()


        def test_shutdown_falls_back_to_own_teardown_on_wait_timeout(monkeypatch):
            """If the in-flight teardown doesn't signal within the wait timeout (signal thread died),
            shutdown() logs a warning and falls back to its OWN _bounded_shutdown(). Safe via _stop_lock
            (P1.M1.T1.S1) on a real host; here we assert the fallback PATH fires (host.stop called twice:
            the in-flight one + the fallback one). The wait timeout is shrunk to keep the test fast."""
            monkeypatch.setattr(daemon, "_TEARDOWN_WAIT_TIMEOUT", 0.2)   # CRITICAL #4: fast fallback
            host = _GatedHost()
            d, *_ = _make_daemon(recorder_host=host)
            ta = threading.Thread(target=d.request_shutdown, name="sig", daemon=True)
            ta.start()
            assert host.entered.wait(timeout=2.0)     # request_shutdown's host.stop() in flight (blocked)
            main_done = threading.Event()

            def _main_shutdown():
                d.shutdown()
                main_done.set()

            tm = threading.Thread(target=_main_shutdown, name="main", daemon=True)
            tm.start()
            # shutdown() waits 0.2s, times out, logs, falls back to its OWN host.stop() (stop_calls=2).
            assert _wait_for(lambda: host.stop_calls >= 2, timeout=3.0), (
                f"fallback did not fire (stop_calls={host.stop_calls})"
            )
            # release both host.stop() calls (the in-flight + the fallback) so threads can finish
            host.release.set()
            ta.join(timeout=5.0)
            tm.join(timeout=5.0)
            assert main_done.is_set()
            assert host.stop_calls == 2, "fallback must run its own host.stop() (the wait timed out)"
  - NOTE: `_wait_for` already exists in tests/test_daemon.py (the S2 run-loop helper). Reuse it; do NOT
    redefine. If unsure of its name, grep `def _wait_for` — it polls a predicate with a timeout.
  - CONSTRAINTS:
      * _CountingHost / _GatedHost need ONLY .stop(timeout=None) (the daemon calls nothing else in the
        teardown path — Gotcha #7). Define them INNER to the new section.
      * Inject via _make_daemon(recorder_host=host). Assert on host.stop_calls + d._shutdown_done +
        d._teardown_done.is_set().
      * The fallback test monkeypatches daemon._TEARDOWN_WAIT_TIMEOUT to 0.2 (CRITICAL #4) — do NOT wait
        the real 8.0s.
      * Reuse the file's existing threading/time/daemon/_wait_for (no new imports).

Task 5: VALIDATE — run the Validation Loop L1–L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S1: daemon-level single-flight shutdown coordination (_shutdown_done + _teardown_done) — Issue 1".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — claim under _lock, teardown + wait OUTSIDE _lock. Only the _shutdown_done read/claim is a
# short under-_lock critical section. _bounded_shutdown() (slow host.stop) and _teardown_done.wait()
# run WITHOUT _lock — matching request_shutdown's existing outside-_lock discipline (a slow teardown
# must not block start/stop/toggle, which take _lock via _arm/_disarm).
# request_shutdown:
#     with self._lock:
#         if getattr(self, "_shutdown_done", False): return   # idempotent
#         self._shutdown_done = True                           # CLAIM
#     self._safe_abort()
#     try: self._bounded_shutdown()
#     finally: self._teardown_done.set()                       # SIGNAL (always fires)
# shutdown:
#     with self._lock:
#         already = getattr(self, "_shutdown_done", False)
#         if not already: self._shutdown_done = True           # claim if first
#     if already:
#         if self._teardown_done.wait(timeout=_TEARDOWN_WAIT_TIMEOUT): return   # WAIT (outside _lock)
#         logger.warning(...)                                   # timeout -> fallback
#     if self._host is None: return
#     try: self._bounded_shutdown()
#     except Exception: logger.exception(...)
#     finally: self._teardown_done.set()

# PATTERN 2 — the _teardown_done Event is what eliminates the race (a flag alone is insufficient).
# run() can exit (~0.5s) and reach shutdown() BEFORE request_shutdown's _lock-protected claim runs. The
# Event + bounded wait makes shutdown() BLOCK until the teardown is observed finished, so even if the
# claim/teardown ordering interleave, exactly ONE _bounded_shutdown() runs (the claimer's).

# PATTERN 3 — belt-and-suspenders with T1.S1's _stop_lock. The wait's bounded timeout + fallback means
# a dead signal thread cannot hang shutdown(). The fallback's host.stop() is kept single-flight by
# RecorderHost._stop_lock, so even the exceptional path cannot reproduce the double-teardown. 1A + 1B
# compose; neither replaces the other.
```

### Integration Points

```yaml
PRODUCTION RUNTIME (SIGTERM path, the bug):
  - Before: signal-thread request_shutdown + main-thread shutdown both called _bounded_shutdown() ->
    host.stop() concurrently -> double teardown -> 15.2s -> SIGKILL.
  - After: request_shutdown CLAIMS + does the ONE teardown + signals _teardown_done. main()'s shutdown()
    SEES _shutdown_done claimed -> WAITS on _teardown_done -> returns when it finishes. Exactly ONE
    host.stop(). Wall time = single teardown (~7s post-T2.S2, ~12s pre-T2.S2) + server.stop() (~2s).

QUIT PATH (sequential, unchanged correctness, cleaner):
  - ControlServer._dispatch("quit") -> request_shutdown() (claims + teardown + _teardown_done.set()) ->
    on_quit=daemon.shutdown() (sees _shutdown_done claimed, _teardown_done already set -> wait returns
    immediately -> return). No second teardown. (Was already correct via host._proc=None; now also
    correct via the coordination, double protection.)

COMPOSES WITH:
  - P1.M1.T1.S1 (Complete): RecorderHost._stop_lock — makes the wait-timeout fallback safe.
  - P1.M1.T2.S2 (separate): reduce _bounded_shutdown 10s->5s — tightens the budget so the single
    teardown + server.stop() <= ~9s (the contract OUTPUT's wall-time target). T2.S1 alone fixes the
    double-teardown BUG; the ~9s target needs T2.S2.
  - P1.M1.T2.S3 (separate): the heavier SIGTERM-subprocess simulation test (real armed daemon +
    SIGTERM + assert exit <8s, no SIGKILL). T2.S1's tests are the deterministic UNIT proof.

NO INTERFACE CHANGES:
  - request_shutdown()/shutdown() signatures unchanged (no new public params). _teardown_done +
    _shutdown_done are private attributes. _TEARDOWN_WAIT_TIMEOUT is a module constant.
  - config.toml, systemd unit, ctl.py, control-socket protocol, README: UNCHANGED.
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST unit tests with fakes — NO GPU /
> models / real child / network / systemd. No ruff/mypy configured. Reuse the file's `_wait_for` helper.

### Level 1: The edits are in place + the daemon module imports clean

```bash
cd /home/dustin/projects/voice-typing
echo "--- _teardown_done Event created in __init__ ---"
grep -n 'self._teardown_done = threading.Event()' voice_typing/daemon.py && echo "L1 PASS: _teardown_done in __init__" || echo "L1 FAIL"
echo "--- _TEARDOWN_WAIT_TIMEOUT module constant exists + is referenced ---"
grep -n '_TEARDOWN_WAIT_TIMEOUT = 8.0' voice_typing/daemon.py && grep -n 'wait(timeout=_TEARDOWN_WAIT_TIMEOUT)' voice_typing/daemon.py && echo "L1 PASS: constant + reference" || echo "L1 FAIL"
echo "--- request_shutdown claims under _lock + signals in finally ---"
grep -nA1 'with self._lock:' voice_typing/daemon.py | grep -q '_shutdown_done' && grep -q 'finally:' voice_typing/daemon.py && grep -q '_teardown_done.set()' voice_typing/daemon.py && echo "L1 PASS: claim + finally signal present" || echo "L1 FAIL"
echo "--- daemon.py imports (no syntax error) ---"
.venv/bin/python -c "import ast; ast.parse(open('voice_typing/daemon.py').read()); print('L1 PASS: daemon.py parses')"
# Expected: _teardown_done in __init__; _TEARDOWN_WAIT_TIMEOUT=8.0 + its wait() reference; claim under
# _lock + a finally that sets _teardown_done; daemon.py parses.
```

### Level 2: The 6 new coordination tests pass (the deterministic proof)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "request_shutdown_claims_and_signals or shutdown_does_own_teardown or shutdown_waits_for_inflight or shutdown_returns_immediately_when_teardown or request_shutdown_idempotent or shutdown_falls_back_to_own_teardown"
# Expected: 6 PASSED. The load-bearing ones:
#   test_shutdown_waits_for_inflight_teardown_no_second_stop  -> asserts host.stop_calls == 1 (the fix)
#   test_shutdown_falls_back_to_own_teardown_on_wait_timeout  -> asserts host.stop_calls == 2 (fallback)
# If the wait test shows stop_calls == 2: shutdown() is NOT waiting (it started its own teardown) —
# re-check the already_claimed branch (Task 3). If the fallback test times out: the monkeypatch of
# _TEARDOWN_WAIT_TIMEOUT didn't take (re-check the constant is module-level + referenced by shutdown()).
```

### Level 3: Full daemon suite green (no regression to existing shutdown/quit/run-loop tests)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v 2>&1 | tail -8
echo "--- specifically the existing request_shutdown / shutdown tests still green ---"
.venv/bin/python -m pytest tests/test_daemon.py -k "request_shutdown or shutdown" -v 2>&1 | tail -15
# Expected: full suite green. The existing test_request_shutdown_sets_event_aborts_and_tears_down_child,
# test_request_shutdown_skips_abort_but_tears_down_when_no_text_in_flight, test_shutdown_* all still
# pass — the coordination change preserves their behavior (request_shutdown still tears down; shutdown
# still idempotent). If an existing test fails, it likely asserted on the OLD "_shutdown_done not set by
# request_shutdown" behavior — update its expectation to match the new claim semantics.
```

### Level 4: Scope — only daemon.py + test_daemon.py changed; sibling files untouched

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY daemon.py + test_daemon.py ---"
git diff --name-only | grep -vxE 'voice_typing/daemon.py|tests/test_daemon.py' && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only daemon.py + test_daemon.py"
echo "--- sibling/scope files UNTOUCHED ---"
git diff --quiet voice_typing/recorder_host.py voice_typing/config.py systemd/voice-typing.service install.sh \
  && echo "L4 PASS: recorder_host.py/config/unit/install.sh unchanged" || echo "L4 FAIL: a scope file was modified"
echo "--- _bounded_shutdown default timeout UNCHANGED (T2.S2 owns 10->5) ---"
grep -n 'def _bounded_shutdown(self, timeout: float = 10.0)' voice_typing/daemon.py && echo "L4 PASS: timeout still 10.0 (T2.S2's job)" || echo "L4 NOTE: timeout signature changed — confirm T2.S2 didn't land early"
# Expected: diff = daemon.py + test_daemon.py only; recorder_host/config/unit/install.sh unchanged;
# _bounded_shutdown default still 10.0 (T2.S2 owns the reduction).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `_teardown_done` Event in `__init__`; `_TEARDOWN_WAIT_TIMEOUT=8.0` constant + its `wait()` reference; claim under `_lock` + a `finally` that sets `_teardown_done`; daemon.py parses.
- [ ] L2: 6 new coordination tests pass (claim/signal, called-first, **wait-no-second-stop**, immediate-return, idempotent, **fallback**).
- [ ] L3: full `tests/test_daemon.py` green; existing `request_shutdown_*`/`shutdown_*` tests still pass.
- [ ] L4: diff = `daemon.py` + `test_daemon.py` only; `recorder_host.py`/config/unit/install.sh unchanged; `_bounded_shutdown` default still 10.0 (T2.S2 owns it).

### Feature Validation
- [ ] `request_shutdown()` claims `_shutdown_done` under `_lock` + signals `_teardown_done` in `finally`.
- [ ] `shutdown()`, when `_shutdown_done` already claimed, WAITS on `_teardown_done` (outside `_lock`) and does NOT start a second `_bounded_shutdown()`.
- [ ] SIGTERM path → exactly ONE `host.stop()` (signal thread's); main's `shutdown()` waits.
- [ ] Quit path → `shutdown()` returns immediately (`_teardown_done` already set); no second teardown.
- [ ] Wait timeout → fallback to own `_bounded_shutdown()` (safe via `_stop_lock`); not unbounded.
- [ ] Second `request_shutdown()` → idempotent (no re-teardown).

### Code Quality Validation
- [ ] Claim is the only under-`_lock` step; teardown + wait run outside `_lock` (no deadlock, no wedged toggle).
- [ ] `_teardown_done.set()` is in a `finally` (always fires — no waiter deadlock).
- [ ] `_TEARDOWN_WAIT_TIMEOUT` is a named module constant (fallback test monkeypatches it; fast suite stays fast).
- [ ] Tests use minimal `_CountingHost`/`_GatedHost` (only `.stop()`); reuse `_make_daemon(recorder_host=)` + existing `threading`/`time`/`_wait_for`.
- [ ] Docstrings on `request_shutdown()`/`shutdown()` refreshed to describe the new coordination.

### Scope Boundary Validation
- [ ] `voice_typing/recorder_host.py` unmodified (T1.S1 owns `_stop_lock`).
- [ ] `_bounded_shutdown` timeout unchanged (T2.S2 owns 10→5).
- [ ] No config/systemd/install.sh/README/ctl.py/control-socket changes.
- [ ] No subprocess SIGTERM test (T2.S3 owns it; T2.S1 is the unit-level proof).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] No user-facing docs (contract §5 "DOCS: none — internal implementation change"). The refreshed method docstrings are the durable explanation.
- [ ] README teardown note is M4.T1's job (Mode B sweep), not this subtask.

---

## Anti-Patterns to Avoid

- ❌ Don't ship a FLAG-ONLY fix — `request_shutdown` setting `_shutdown_done` without the `_teardown_done` Event + bounded wait RACES (run() can reach shutdown() before the claim). The Event + wait is the actual race-eliminator (CRITICAL #1).
- ❌ Don't hold `_lock` during `_bounded_shutdown()` or during `_teardown_done.wait()` — a slow teardown would wedge `start/stop/toggle` (which take `_lock`). Only the `_shutdown_done` claim is under `_lock` (CRITICAL #2).
- ❌ Don't set `_teardown_done` outside a `finally` — if `_safe_abort()`/`_bounded_shutdown()` raises, a waiter deadlocks until the timeout. `try: … finally: self._teardown_done.set()` (CRITICAL #3).
- ❌ Don't hardcode `wait(timeout=8.0)` — the fallback unit test would take 8s. Use the `_TEARDOWN_WAIT_TIMEOUT` module constant + monkeypatch it (CRITICAL #4).
- ❌ Don't remove the wait-timeout fallback or make it unbounded — a dead signal thread must not hang `shutdown()`. The fallback is safe because of T1.S1's `_stop_lock` (CRITICAL #5).
- ❌ Don't change `_bounded_shutdown`'s 10.0s default — that's T2.S2. T2.S1 keeps the teardown calls unchanged (CRITICAL #9 / Gotcha #9).
- ❌ Don't initialize `_shutdown_done` in `__init__` — it stays `getattr`-guarded; only ADD `_teardown_done` (Gotcha #8).
- ❌ Don't null `_host` in `request_shutdown`/`shutdown` — `_bounded_shutdown` doesn't, and the `_shutdown_done` guard handles idempotency. Host-nulling is `_unload_host`'s job (Gotcha #6).
- ❌ Don't touch `recorder_host.py` (T1.S1) or build the subprocess SIGTERM test (T2.S3). T2.S1 is daemon-level unit tests only (Gotcha #10).
- ❌ Don't make the test fakes need more than `.stop()` — the teardown path calls nothing else; `_CountingHost`/`_GatedHost` with only `.stop(timeout=None)` suffice (Gotcha #7).
- ❌ Don't use bare `python`/`pytest` or invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest` (Gotcha #11).

---

## Confidence Score

**9/10** for one-pass implementation success. The change is well-bounded (one Event in `__init__`, one module constant, a restructured guard in two methods, plus 6 deterministic unit tests), and every load-bearing fact is **verified against the live repo**: the verbatim current bodies of `request_shutdown()` (L1136-1163), `_bounded_shutdown()` (L1265-1283), `shutdown()` (L1285-1332), and the `__init__` Event block (L541-542); the three-part fix strategy (1A/1B/1C) confirmed in `bug_analysis.md` (1A = T1.S1 Complete, 1B = this, 1C = T2.S2); the `_make_daemon(recorder_host=)` injection seam + the fact that only `.stop()` is needed in the teardown path; `threading` already imported; and the explicit no-conflict boundaries with T1.S1 (recorder_host.py), T1.S2 (recorder_host test), T2.S2 (timeout), T2.S3 (subprocess test). The 6 tests deterministically prove the four behavioral properties (claim/signal, wait-no-second-stop, immediate-return, fallback) including the race that a flag-only fix would miss. The −1 residual is the inherent subtlety of the concurrency edit itself: the claim/teardown/wait ordering must be exactly right (claim under `_lock` BEFORE the teardown; wait OUTSIDE `_lock`; signal in `finally`), and a mistake there would pass the simple tests but fail under real SIGTERM timing — which is precisely why T2.S3's subprocess simulation is a separate, complementary gate. The unit tests here (especially the `_GatedHost` wait test) exercise the coordination deterministically, narrowing that residual to the real-process timing that T2.S3 covers.
