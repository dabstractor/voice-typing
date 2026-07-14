# PRP — P1.M1.T2.S3: Concurrent `request_shutdown` + `shutdown` SIGTERM-path regression test

## Goal

**Feature Goal**: Add the END-TO-END regression test for bugfix **Issue 1**'s SIGTERM double-teardown
race — the test the PRD explicitly demands and that `bug_analysis.md §Test Gap` says is missing. Today
every `request_shutdown_*` / `shutdown_*` test calls those methods SEQUENTIALLY on the test thread
(`test_infrastructure.md` Run-Loop pattern); NONE drives them CONCURRENTLY through the real `run()`
loop with a real armed host. This test spawns `request_shutdown()` on a "signal-handler" thread and
`shutdown()` on a "main-thread finally" thread **concurrently**, while the real `run()` loop runs and
the host is armed (lazy-spawned via `host_factory`), and asserts **exactly ONE `host.stop()`**
(`stop_calls == 1`, NOT 2), a bounded total wall time (< 8 s), and a clean run-thread exit. It is the
end-to-end proof that **consumes** the landed fixes (P1.M1.T1.S1 `_stop_lock` + P1.M1.T2.S1 daemon
single-flight + P1.M1.T2.S2 5 s budget) and would FAIL if any of them were reverted.

**Deliverable** (ONE new test, ONE file, no source change, no new files):
1. `tests/test_daemon.py` — add `test_concurrent_request_shutdown_and_shutdown_only_one_stop(monkeypatch)`
   (+ an inner `_GatedFakeHost(_FakeHost)` subclass + a tiny factory), placed in the SIGTERM-path test
   region.

**Success Definition**:
- (a) The test drives the **real `run()` loop** in a thread, **lazy-spawns** the host on the first arm
  via `host_factory=` (`_load_host` → factory), and runs `request_shutdown()` (thread A) **concurrently**
  with `shutdown()` (thread B) — reproducing the actual SIGTERM two-thread topology, not a sequential
  call.
- (b) It asserts `host.stop_calls == 1` BOTH while the teardown is in flight (thread B is WAITING, has
  not started a 2nd `host.stop()`) AND after release — proving the daemon single-flight coordination.
- (c) It asserts the run() thread exits cleanly (`not t_run.is_alive()`) and the total wall time is
  `< 8.0 s` (bounded teardown, no 15 s hang / deadlock).
- (d) It is DETERMINISTIC: a `_GatedFakeHost` whose `stop()` blocks on a release `Event` guarantees the
  concurrency-overlap window (the default `_FakeHost.stop()` returns instantly — see CRITICAL #1 — so
  without the gate the in-flight wait path is not reliably exercised).
- (e) It is a true REGRESSION GUARD: pre-S1 code yields `stop_calls == 2` deterministically (both
  threads call `host.stop()`), so the test FAILS if S1's coordination is reverted.
- (f) No source code changes; no new files; no real CUDA/GPU/child/systemd/network; the test is hermetic
  and fast (< ~1 s wall with the gated host released promptly).

## User Persona

**Target User**: the maintainer / future contributor (and CI) who must be confident the SIGTERM teardown
stays single-flight and bounded. The end user's pain (15.2 s hang + SIGKILL on `systemctl stop`) is fixed
by S1/S2/T1.S1; this test is what PREVENTS that fix from silently regressing.

## Why

- **bugfix Issue 1 (Critical)** is the source. PRD §4.2bis/§8/§7.9 make bounded teardown a hard
  prerequisite. The PRD's prescribed verification: "Verify with a new test that drives the SIGTERM path
  … and asserts exit within e.g. 8 s with no SIGKILL — the existing fast pytest only exercises `voicectl
  quit` and legacy stub shutdowns, never a real armed SIGTERM." `bug_analysis.md §Test Gap` (L61-65)
  states verbatim: "No existing test exercises the concurrent `request_shutdown()` + `shutdown()` path
  (the SIGTERM path) … with a real `_FakeHost`. Need a new test that spawns `request_shutdown()` on one
  thread and `shutdown()` …". S3 IS that test.
- **Unit proof vs end-to-end proof.** P1.M1.T2.S1 already added 6 UNIT tests (`_CountingHost`/
  `_GatedHost`, `tests/test_daemon.py:1490-1600`) that prove the coordination by calling
  `request_shutdown()`/`shutdown()` directly on a host injected via `_make_daemon(recorder_host=host)`.
  They do NOT run the `run()` loop, do NOT arm via `start()`, do NOT lazy-spawn. S3 is the missing
  END-TO-END proof: it wires the coordination through the REAL lifecycle (`run()` loop + `_load_host`
  spawn + arm) and the REAL two-thread SIGTERM topology. The PRD explicitly wants the lifecycle path
  exercised (which is exactly why Issue 1 "slipped through" — the existing tests never drove it).
- **It consumes the whole fix composition.** S3 asserts `stop_calls == 1` (S1 single-flight), bounded
  wall time (S2's 5 s budget + the coordination), and clean exit (the BUG-1 child-teardown-unblocks-
  `text()` path). A revert of any one degrades the test.

## What

Add one test to `tests/test_daemon.py`:

- **`_GatedFakeHost(_FakeHost)`** (inner to the test): preserves the full `_FakeHost` surface
  (`spawn`/`is_alive`/`pid`/`device`/`set_microphone`/`abort`/`text`) so `run()` + `_load_host` + arm
  work unchanged; overrides:
  - `text(on_final)` — BLOCKS until a final-Event OR `_dead` (mirrors `RecorderHost.text()`'s wait loop;
    same shape as the `_StrandingHost` test at `tests/test_daemon.py:946`), so `run()` is genuinely
    listening when the SIGTERM fires;
  - `stop(timeout)` — `stop_calls += 1; self._alive = False; self._dead = True` (child death → any
    blocked `text()` returns → `run()` can exit); `stop_entered.set()` (tell the test we are inside the
    teardown); `stop_release.wait(timeout=5.0)` (the in-flight teardown window — bounded, never hangs).
- **`_factory(*a, **k)`** returns `_GatedFakeHost(*a, **k)` — the `host_factory` for `_load_host`.
- **`test_concurrent_request_shutdown_and_shutdown_only_one_stop(monkeypatch)`**:
  1. `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` (hermetic; matches the `_StrandingHost`
     precedent + the contract INPUT).
  2. `d, _fb = _make_lazy_daemon(host_factory=_factory)`; `t_run = Thread(target=d.run, daemon=True);
     t_run.start()`; `_wait_for(lambda: d._start_monotonic is not None)` (run() booted).
  3. `d.start()` (first arm → `_load_host` spawns the gated host → `_arm`); `_wait_for(lambda:
     d._text_in_flight.is_set())` (loop entered `text()`); `host = d._host`.
  4. **Thread A (signal handler):** `t_sig = Thread(target=d.request_shutdown)`; `start()`;
     `_wait_for(host.stop_entered.is_set / host.stop_entered.wait)` (request_shutdown is INSIDE
     `host.stop()`); assert `d._shutdown_done is True` and `not d._teardown_done.is_set()` (in flight).
  5. **Thread B (main-thread finally analog):** `t_main = Thread(target=lambda: (d.shutdown(),
     main_done.set()))`; `start()`; `_time.sleep(0.2)` (let it reach `_teardown_done.wait()`).
  6. Assert `host.stop_calls == 1` (B is WAITING, did NOT start a 2nd `host.stop()`) and
     `not main_done.is_set()` (B has not returned).
  7. `host.stop_release.set()` (release the in-flight teardown) → A finishes → `_teardown_done` set →
     B's wait returns; `_wait_for(main_done.is_set)`; `t_sig.join`; `t_main.join`.
  8. `_wait_for(lambda: not t_run.is_alive())` (run exited cleanly); assert `host.stop_calls == 1`
     (final — still single); `wall = _time.monotonic() - wall_start; assert wall < 8.0`.
  9. `finally:` always `host.stop_release.set()` + `d.request_shutdown()` (idempotent under S1's guard)
     + join all threads (test isolation — no thread left blocked).

### Success Criteria

- [ ] Test is named `test_concurrent_request_shutdown_and_shutdown_only_one_stop` and lives in
      `tests/test_daemon.py` (SIGTERM-path region, after the `_StrandingHost` test, navigated by name).
- [ ] It uses `_make_lazy_daemon(host_factory=...)` (NOT `_make_daemon`) so `_load_host` spawns the fake
      host on arm; it runs the real `run()` loop in a thread and arms via `d.start()`.
- [ ] `request_shutdown()` runs on one thread; `shutdown()` runs on another thread CONCURRENTLY
      (verified in-flight via the gated host's `stop_entered` Event before B starts).
- [ ] `host.stop_calls == 1` is asserted both mid-flight and after release; `wall < 8.0`;
      `not t_run.is_alive()` at the end.
- [ ] The gated host preserves the full `_FakeHost` surface (so `_load_host`/`run()`/arm work); only
      `text()` (blocks) + `stop()` (gated) are overridden.
- [ ] The `finally` releases the gate + joins all threads (no leaked/blocked thread on any path).
- [ ] No source file is modified; `git diff --name-only` == `tests/test_daemon.py`; the full fast suite
      stays green (the new test is additive).

## All Needed Context

### Context Completeness Check

_Pass._ Every claim is verified against the live repo + the landed S1/S2 code: the exact `run()` loop
(L702-797), `start()` (L1109), `request_shutdown()` (L1148), `_bounded_shutdown(timeout=5.0)` (L1294),
`shutdown()` (L1321), `_load_host()` (L631); the test helpers `_make_lazy_daemon` (L2367),
`_fake_host_factory` (L501), `_FakeHost` (L434, incl. the instant-`stop` gotcha), `_wait_for` (L417),
`_cuda_resolve` (L69); the `_StrandingHost` SIGTERM template (L946); S1's unit tests (L1490-1600,
distinct — no duplication); and `bug_analysis.md §Test Gap` (L61-65). The deterministic-gate rationale
is documented. A developer new to this repo can write the test from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the defect, the landed fix, and the explicit test mandate
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 1 (L3-31) = the SIGTERM two-thread double-teardown race (A=request_shutdown on the
        signal thread, B=shutdown on the main-thread finally; pre-fix BOTH called host.stop()).
        §Test Gap (L61-65) = the EXACT mandate for this test: 'No existing test exercises the
        concurrent request_shutdown() + shutdown() path (the SIGTERM path) ... with a real _FakeHost.'"
  critical: "The fix landed (P1.M1.T1.S1 _stop_lock + P1.M1.T2.S1 daemon single-flight + P1.M1.T2.S2
            5s). S3 is the regression test that PROVES it end-to-end and FAILS on revert (pre-fix =
            stop_calls==2 deterministically)."

# MUST READ — this task's verified design + the critical instant-stop gotcha + the threading model
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T2S3/research/sigterm_concurrent_test_design.md
  why: "§A = the bug + the landed fix (exact verified method bodies). §B = the test infra (lazy seam,
        _FakeHost surface, the INSTANT-STOP gotcha, the _StrandingHost template, S1's distinct unit
        tests, helpers). §C = the threading model the test drives. §D = regression sensitivity
        (pre-S1 = stop_calls==2). §E = the no-conflict boundary with S2."
  section: "§B2 (the instant-stop gotcha) and §B3 (the _StrandingHost template) are load-bearing."

# MUST READ — the contract (what S3 must produce)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: "§Issue 1 OUTPUT: 'Regression test for the SIGTERM double-teardown race ... the test the PRD
        explicitly requests: drives the SIGTERM path ... asserts exit within e.g. 8s with no SIGKILL.'
        §Issue 1 root cause names the exact two-thread topology S3 reproduces."

# THE EDIT SITE — the test file (navigate by test/handler names; line numbers shift with S1/S2)
- file: tests/test_daemon.py
  why: "Add ONE test. PLACE it right after test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final
        (the _StrandingHost SIGTERM test, ~L946-1005) — thematic grouping (SIGTERM-path tests together)
        AND far from S2's parallel lambda edit (~L1472). Navigate by the test NAME, not line number
        (S1/S2 are landing concurrently and shifting lines). threading + `time as _time` are already
        imported (L333-334); `_wait_for` (L417), `_cuda_resolve` (L69), `_make_lazy_daemon` (L2367),
        `_FakeHost` (L434) are in scope — NO new imports."
  pattern: "Mirror the _StrandingHost test's structure (subclass _FakeHost; factory wrapper;
            _make_lazy_daemon(host_factory=); run() in a thread; d.start(); _wait_for(_text_in_flight);
            request_shutdown). ADD the concurrent shutdown() on a 2nd thread + the gated-stop overlap
            (CRITICAL #1) + the stop_calls==1 / wall<8s / clean-exit asserts."
  critical: "Do NOT duplicate S1's _CountingHost/_GatedHost tests (L1490-1600) — those are UNIT-level
            (host injected via recorder_host=, no run() loop). S3 is END-TO-END (lazy spawn via
            host_factory + real run() loop + arm). Do NOT use _make_daemon(host_factory=) — it injects
            a resident _StubRecorder so _load_host is a no-op (the factory is never called). Use
            _make_lazy_daemon (recorder=None -> _host None at boot -> _load_host spawns on arm)."

# THE TEMPLATE — the closest run-loop SIGTERM test (copy its structure, extend to concurrency)
- file: tests/test_daemon.py
  why: "test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final (L946) — the _StrandingHost
        test. Its _StrandingHost.text() (blocks until final or _dead) is EXACTLY the realistic text()
        S3's _GatedFakeHost needs; its stop() (sets _dead) is the base S3's gated stop() builds on. Copy
        the _cuda_resolve + lazy-daemon + run-in-thread + d.start() + _wait_for(_text_in_flight) +
        request_shutdown skeleton, then add thread B (shutdown) + the gate."
  section: "L946-1005 (the whole test)."

# THE UNIT-LEVEL SIBLING (S1, Complete) — mirror its mid-flight assertion, end-to-end
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M1T2S1/PRP.md
  why: "S1's test_shutdown_waits_for_inflight_teardown_no_second_stop (tests/test_daemon.py:1538) is the
        UNIT analog: it asserts host.stop_calls==1 while shutdown() waits, then ==1 after release. S3
        mirrors those assertions but through the REAL run()/_load_host/arm lifecycle. S1 also defines
        _GatedHost (stop() blocks on a release Event) — S3's _GatedFakeHost is the _FakeHost-surface
        version of the same idea (so _load_host/run() work)."
  critical: "S3 CONSUMES S1's coordination (it does NOT re-test the unit mechanics). If S1 were
            reverted, S3's stop_calls==1 assertion FAILS (pre-S1 = 2). That is the regression value."
```

### Current Codebase tree (relevant slice — S1/S2 landed; this task is test-only)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py             # READ-ONLY for T2.S3. run()@702; start()@1109; request_shutdown()@1148
│   │                         #   (S1 claim+_teardown_done landed); _bounded_shutdown(timeout=5.0)@1294
│   │                         #   (S2 landed); shutdown()@1321 (S1 wait branch landed); _load_host()@631.
│   └── recorder_host.py      # READ-ONLY (T1.S1 _stop_lock landed).
└── tests/
    └── test_daemon.py        # ← EDIT (add ONE test + _GatedFakeHost). _StrandingHost template @946;
                              #   S1 unit tests @1490-1600 (distinct); _make_lazy_daemon @2367;
                              #   _FakeHost @434; _wait_for @417; _cuda_resolve @69; threading + `time as _time` @333.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py          # ADD: test_concurrent_request_shutdown_and_shutdown_only_one_stop (+ inner
#                              _GatedFakeHost subclass + _factory). NO source change. NO new files.
# No daemon.py / recorder_host.py / config / systemd / README changes. DOCS: none (contract §5).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE DEFAULT _FakeHost.stop() IS INSTANT, SO IT GIVES NO CONCURRENCY OVERLAP.
# _FakeHost.stop() (tests/test_daemon.py:481) does: stop_calls+=1; _alive=False; spawn a thread that
# runs the wrapped _StubRecorder.shutdown() then done.set(); done.wait(timeout). _StubRecorder.shutdown()
# (L386) is just `self.shutdowns += 1` — INSTANT. So done.wait(timeout) returns in microseconds. => the
# default _FakeHost.stop() returns before a concurrent shutdown() can be observed WAITING, so the test
# would only ever exercise the SEQUENTIAL/immediate-return path (which S1's unit tests already cover).
# The contract's claim ("_FakeHost.stop() has a brief wait ... gives the overlap window") is WRONG for
# the default. FIX: use a _GatedFakeHost(_FakeHost) whose stop() blocks on a release Event, so the
# in-flight window is GUARANTEED and shutdown()'s WAIT is observable. This is THE key detail.

# CRITICAL #2 — USE _make_lazy_daemon(host_factory=...), NOT _make_daemon(host_factory=...). _make_daemon
# injects a default _StubRecorder -> __init__ wraps it in a resident _LegacyRecorderHostAdapter ->
# self._host is NON-None at boot -> _load_host() is a no-op (resident) -> the host_factory is NEVER
# called -> no spawn on arm. _make_lazy_daemon (L2367) passes recorder=None -> _host is None at boot
# (production lazy boot) -> d.start() -> _load_host() calls factory(...) -> spawns the fake host. The
# contract's "_make_daemon() with host_factory=" is imprecise; _make_lazy_daemon is correct.

# CRITICAL #3 — DON'T DUPLICATE S1's UNIT TESTS. S1 added _CountingHost/_GatedHost + 6 tests
# (tests/test_daemon.py:1490-1600) that inject the host via _make_daemon(recorder_host=host) and call
# request_shutdown()/shutdown() DIRECTLY (no run() loop, no arm, no host_factory). S3 is the
# END-TO-END complement (real run() loop + lazy spawn via host_factory + arm + concurrent threads).
# Same idea (prove stop_calls==1 under concurrency), different level. Do not re-test the unit mechanics.

# CRITICAL #4 — THE _GatedFakeHost MUST PRESERVE THE FULL _FakeHost SURFACE so _load_host/run()/arm work.
# _load_host calls factory(cfg, feedback, latency, on_final, on_partial, on_speech) and then host.spawn()
# + reads host.device. run() calls host.set_microphone(False) at boot, host.text(on_final) in the loop.
# start()->_arm calls host.set_microphone(True). So _GatedFakeHost must keep: spawn(), is_alive, pid,
# device, set_microphone, abort, and text() (overridden to block). Override ONLY text() and stop();
# inherit the rest from _FakeHost. __init__ calls super().__init__(*a, **k) (the real RecorderHost
# signature) then adds the gates.

# CRITICAL #5 — text() MUST BLOCK (mirror RecorderHost.text()) so run() is genuinely LISTENING when the
# SIGTERM fires, AND so _text_in_flight stays set (the _wait_for(_text_in_flight.is_set) gate). Copy
# _StrandingHost.text() (L976): `while not self._final_evt.wait(0.05): if self._dead: return`. An
# instant-return text() (the raw _FakeHost.text()) makes run() spin + exit the moment _shutdown is set
# (still works for stop_calls==1, but loses realism + makes _text_in_flight flaky to catch). Blocking
# text() is the realistic + deterministic choice.

# CRITICAL #6 — stop() MUST set _dead BEFORE blocking, so a blocked text() returns and run() can exit.
# Order in _GatedFakeHost.stop(): stop_calls+=1; _alive=False; _dead=True; stop_entered.set();
# stop_release.wait(timeout=5.0). Setting _dead lets the (blocked) run-loop text() see child death on
# its next 0.05s poll and return -> run() re-checks _shutdown (set by request_shutdown) -> exits. If you
# block BEFORE setting _dead, run() stays stranded in text() (the original BUG-1) — wrong here.

# CRITICAL #7 — OBSERVE THE IN-FLIGHT WINDOW BEFORE STARTING THREAD B. Start t_sig (request_shutdown),
# then _wait_for(host.stop_entered) (request_shutdown is INSIDE host.stop()) BEFORE starting t_main
# (shutdown). That guarantees shutdown() sees _shutdown_done ALREADY claimed + _teardown_done NOT set ->
# it takes the WAIT branch (the path under test). If you start both "simultaneously" without the gate
# observation, B might claim first (then A early-returns) — still stop_calls==1, but not deterministically
# the wait path. The gate + ordered start make it deterministic.

# GOTCHA #8 — DON'T ASSERT t_run.is_alive() MID-TEST. request_shutdown sets _shutdown as its FIRST act;
# the run loop (in blocking text()) sees _dead (set by host.stop()) within ~0.05s and exits. So t_run
# is usually ALREADY dead by the time you observe stop_entered. Assert run-exit ONLY at the END
# (`_wait_for(lambda: not t_run.is_alive())`), not mid-flight. (The contract's "run thread exits cleanly"
# is an END assertion.)

# GOTCHA #9 — THE finally MUST RELEASE THE GATE + JOIN EVERY THREAD (test isolation). If any assertion
# fails mid-test, threads A/B/run could be left blocked on the gate or on _teardown_done.wait. The
# finally: `if host: host.stop_release.set()`; `d.request_shutdown()` (idempotent under S1's
# _shutdown_done guard — early-returns if already claimed, just re-sets _shutdown); join t_sig/t_main;
# _wait_for(not t_run.is_alive()); t_run.join(). Never leave a blocked thread behind.

# GOTCHA #10 — d.request_shutdown() IN finally IS SAFE (idempotent). After a normal run, _shutdown_done
# is already True (A claimed it), so the finally's request_shutdown hits the guard and early-returns
# (it does NOT call _bounded_shutdown again — no extra host.stop()). It only re-sets _shutdown (no-op)
# so run() is guaranteed to exit. If the try failed BEFORE A claimed, request_shutdown does a (fast,
# gate-released) teardown — also fine. Either way stop_calls stays as observed.

# GOTCHA #11 — FULL PATHS + no ruff/mypy. `.venv/bin/python -m pytest` (machine aliases python3->uv
# run). This project has NO ruff/mypy configured — do not invoke them. The test is in tests/test_daemon.py.

# GOTCHA #12 — WALL-TIME BOUND IS A SANITY CHECK, not a real 15s reproduction. With a gated host
# released promptly, wall is < ~1s. The `wall < 8.0` assert proves no DEADLOCK / no _TEARDOWN_WAIT_TIMEOUT
# fallback firing (which would mean the coordination mis-fired). The true 15s/SIGKILL bound is a
# subprocess/L4 concern (out of scope for S3; the contract specifies an IN-PROCESS simulation). Keep
# the < 8.0 assert (it matches the contract) but understand its real role.
```

## Implementation Blueprint

### Data models and structure

No source/types/config changes. The only new "structure" is one inner test-local class
(`_GatedFakeHost(_FakeHost)` with two `threading.Event` gates + a `_dead` flag + an inherited
`stop_calls` counter) and one test function. Everything is pure-Python using already-imported
`threading`/`time`/`pytest` machinery.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD tests/test_daemon.py — the concurrent SIGTERM-path regression test (+ _GatedFakeHost)
  - PLACE: immediately AFTER test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final
    (the _StrandingHost SIGTERM test). FIND it by NAME (line numbers shift with S1/S2 landing):
      grep -n 'def test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final' tests/test_daemon.py
    Place the new test right after that test's closing asserts, under a banner comment:
      # ===========================================================================
      # P1.M1.T2.S3 — concurrent request_shutdown + shutdown (SIGTERM double-teardown race)
      # End-to-end regression for bugfix Issue 1: drives the REAL run() loop + lazy host spawn on
      # arm, runs request_shutdown (signal thread) + shutdown (main-thread finally) CONCURRENTLY,
      # and asserts exactly ONE host.stop() (single-flight), wall < 8s, clean run-thread exit.
      # (S1's _CountingHost/_GatedHost unit tests above prove the mechanics WITHOUT the run loop;
      #  THIS test wires them through the real lifecycle — bug_analysis.md §Test Gap.)
      # ===========================================================================
  - ADD exactly this test (threading + `time as _time` + _wait_for + _cuda_resolve + _make_lazy_daemon
    + _FakeHost are all in scope — NO new imports):

        def test_concurrent_request_shutdown_and_shutdown_only_one_stop(monkeypatch):
            """SIGTERM-path regression (bugfix Issue 1 / P1.M1.T2.S3).

            The real SIGTERM race: the signal-handler thread runs request_shutdown() (tears the child
            down via _bounded_shutdown() -> host.stop()) WHILE main()'s finally-block runs
            daemon.shutdown() CONCURRENTLY. Pre-fix (pre-P1.M1.T2.S1) BOTH called _bounded_shutdown()
            -> host.stop() TWICE -> the double teardown that blew systemd's 15s TimeoutStopSec -> SIGKILL.
            Post-fix, shutdown() WAITS on _teardown_done instead of a 2nd teardown, so exactly ONE
            host.stop() runs.

            This is the END-TO-END proof (vs S1's unit-level _GatedHost test at ~L1538): real run()
            loop in a thread + real lazy host spawn on arm (host_factory) + concurrent request_shutdown
            (thread A) + shutdown (thread B). bug_analysis.md §Test Gap: 'No existing test exercises
            the concurrent request_shutdown() + shutdown() path (the SIGTERM path) ... with a real
            _FakeHost' — this is that test.

            The default _FakeHost.stop() returns INSTANTLY (_StubRecorder.shutdown() is a counter++),
            so it gives no concurrency-overlap window. _GatedFakeHost.stop() blocks on a release Event
            to GUARANTEE the in-flight window during which shutdown() is observed WAITING (not starting
            a 2nd stop). Its text() mirrors RecorderHost.text() (blocks until final or child death), so
            run() is genuinely listening when the SIGTERM fires (same shape as the _StrandingHost test).
            """
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic (belt-and-suspenders)

            class _GatedFakeHost(_FakeHost):
                """A _FakeHost whose stop() blocks on a release gate (the in-flight teardown window)
                and whose text() blocks until child death — so a concurrent shutdown() can be observed
                WAITING on _teardown_done instead of starting a 2nd host.stop(). Full _FakeHost surface
                preserved so run()/_load_host/arm work unchanged."""

                def __init__(self, *a, **k):
                    super().__init__(*a, **k)
                    self._final_evt = threading.Event()
                    self._dead = False
                    self.stop_entered = threading.Event()
                    self.stop_release = threading.Event()

                def text(self, on_final):
                    self.recorder.text_calls += 1
                    self.recorder.last_callback = on_final
                    # Mirror RecorderHost.text()'s wait loop: return on final OR child death (stop()).
                    while not self._final_evt.wait(timeout=0.05):
                        if self._dead:
                            return  # child death -> host.text() returns -> run() re-checks _shutdown

                def stop(self, timeout=5.0):
                    self.stop_calls += 1
                    self._alive = False
                    self._dead = True          # child death -> any blocked text() returns (run() exits)
                    self.stop_entered.set()     # tell the test we are INSIDE the teardown
                    self.stop_release.wait(timeout=5.0)  # in-flight teardown window (bounded; never hangs)

            def _factory(*a, **k):
                return _GatedFakeHost(*a, **k)

            d, _fb = _make_lazy_daemon(host_factory=_factory)
            t_run = threading.Thread(target=d.run, daemon=True)
            t_run.start()
            wall_start = _time.monotonic()
            host = None
            t_sig = None
            t_main = None
            main_done = threading.Event()
            try:
                _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)  # run() booted
                d.start()  # first arm lazily spawns the gated host (_load_host -> factory -> _arm)
                assert _wait_for(lambda: d._text_in_flight.is_set(), timeout=2.0), "loop did not enter text()"
                host = d._host
                assert isinstance(host, _GatedFakeHost), "arm did not spawn the gated host"

                # --- Thread A: the SIGTERM signal-handler analog ---
                t_sig = threading.Thread(target=d.request_shutdown, name="sigterm-sig", daemon=True)
                t_sig.start()
                # request_shutdown claimed _shutdown_done + is INSIDE host.stop() (blocked on stop_release).
                assert host.stop_entered.wait(timeout=2.0), "request_shutdown did not reach host.stop()"
                assert d._shutdown_done is True            # the single-flight CLAIM
                assert not d._teardown_done.is_set()       # teardown still in flight

                # --- Thread B: main()'s finally-block analog (runs CONCURRENTLY with A) ---
                def _main_shutdown():
                    d.shutdown()
                    main_done.set()

                t_main = threading.Thread(target=_main_shutdown, name="sigterm-main", daemon=True)
                t_main.start()
                _time.sleep(0.2)  # let shutdown() reach _teardown_done.wait()

                # CORE REGRESSION ASSERT: B is WAITING, NOT starting a 2nd host.stop().
                assert host.stop_calls == 1, (
                    f"shutdown() started a SECOND host.stop() (double teardown!) stop_calls={host.stop_calls}"
                )
                assert not main_done.is_set(), "shutdown() returned before the in-flight teardown finished"

                # Release the in-flight teardown -> A finishes -> _teardown_done set -> B's wait returns.
                host.stop_release.set()
                assert _wait_for(main_done.is_set, timeout=5.0), "shutdown() did not return after release"
                t_sig.join(timeout=5.0)
                t_main.join(timeout=5.0)
                assert not t_sig.is_alive() and not t_main.is_alive(), "shutdown threads did not finish"

                # run() exits: request_shutdown set _shutdown first; text() saw _dead -> returned.
                assert _wait_for(lambda: not t_run.is_alive(), timeout=3.0), "run() thread did not exit cleanly"

                # FINAL regression asserts: still exactly ONE teardown; bounded wall time.
                assert host.stop_calls == 1, f"double teardown after release! stop_calls={host.stop_calls}"
                wall = _time.monotonic() - wall_start
                assert wall < 8.0, f"total wall time {wall:.2f}s >= 8s (bounded-teardown regression?)"
            finally:
                # ALWAYS release + signal + join so no thread is left blocked (test isolation).
                if host is not None:
                    host.stop_release.set()
                d.request_shutdown()  # idempotent under S1's _shutdown_done guard; re-sets _shutdown
                if t_sig is not None:
                    t_sig.join(timeout=5.0)
                if t_main is not None:
                    t_main.join(timeout=5.0)
                _wait_for(lambda: not t_run.is_alive(), timeout=3.0)
                t_run.join(timeout=3.0)
            assert not t_run.is_alive(), "run() thread still alive after teardown"
  - CONSTRAINTS:
      * Use _make_lazy_daemon(host_factory=_factory) — NOT _make_daemon (CRITICAL #2).
      * _GatedFakeHost subclasses _FakeHost and overrides ONLY text() + stop() (CRITICAL #4).
      * Observe host.stop_entered BEFORE starting t_main (CRITICAL #7). Do NOT assert t_run.is_alive()
        mid-test (GOTCHA #8). The finally releases + joins everything (GOTCHA #9/#10).
      * NO new imports (threading, `time as _time`, _wait_for, _cuda_resolve, _make_lazy_daemon,
        _FakeHost, daemon are all in scope). NO source file edits.
  - DO NOT: modify daemon.py / recorder_host.py / any source; add a second test (one is the contract);
    duplicate S1's _CountingHost/_GatedHost unit tests; use a real subprocess/CUDA/systemd.

Task 2: VALIDATE — run the Validation Loop L1–L4 below; fix until green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S3: concurrent request_shutdown + shutdown SIGTERM-path regression test (assert single host.stop() + <8s)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — guarantee the in-flight window with a gated host (CRITICAL #1). The default _FakeHost.stop()
# is instant, so a concurrent shutdown() can't be observed WAITING. _GatedFakeHost.stop() blocks on a
# release Event; the test observes stop_entered (A is inside stop()) BEFORE starting B (shutdown).
class _GatedFakeHost(_FakeHost):
    def stop(self, timeout=5.0):
        self.stop_calls += 1
        self._alive = False
        self._dead = True            # CRITICAL #6: unblock any blocked text() so run() can exit
        self.stop_entered.set()       # signal the test: teardown is IN FLIGHT
        self.stop_release.wait(timeout=5.0)   # the in-flight window (bounded)

# PATTERN 2 — realistic blocking text() (CRITICAL #5), copied from the _StrandingHost test, so run() is
# genuinely listening when the SIGTERM fires and _text_in_flight stays set.
def text(self, on_final):
    self.recorder.text_calls += 1
    self.recorder.last_callback = on_final
    while not self._final_evt.wait(timeout=0.05):
        if self._dead:
            return

# PATTERN 3 — ordered two-thread SIGTERM topology + mid-flight assertion (the regression proof).
t_sig = Thread(target=d.request_shutdown); t_sig.start()
assert host.stop_entered.wait(timeout=2.0)     # A is INSIDE host.stop() (in flight)
assert d._shutdown_done and not d._teardown_done.is_set()
t_main = Thread(target=lambda:(d.shutdown(), main_done.set())); t_main.start()
_time.sleep(0.2)                                # B reaches _teardown_done.wait()
assert host.stop_calls == 1                      # B is WAITING, no 2nd stop (THE fix)
host.stop_release.set()                          # release -> A finishes -> _teardown_done -> B returns

# PATTERN 4 — finally releases + joins ALL threads (test isolation; GOTCHA #9/#10). d.request_shutdown()
# in finally is idempotent (S1 guard) — it never adds a 2nd teardown; it only re-sets _shutdown.
```

### Integration Points

```yaml
CONSUMES (the landed fix this test proves):
  - P1.M1.T1.S1 (Complete): RecorderHost._stop_lock — makes the wait-timeout fallback safe (not
    exercised here directly, but it is why the coordination is robust).
  - P1.M1.T2.S1 (Complete): request_shutdown claims _shutdown_done + signals _teardown_done; shutdown()
    WAITS on _teardown_done. THIS is what makes stop_calls == 1 (pre-S1 = 2).
  - P1.M1.T2.S2 (landed): _bounded_shutdown default 5.0s — the budget the < 8s wall assert reflects.

NO SOURCE CHANGES:
  - tests/test_daemon.py is the ONLY modified file. daemon.py / recorder_host.py / config / systemd /
    README / ctl / control-socket: UNCHANGED. No new files. No new dependencies.

NO CONFLICT WITH PARALLEL/SIBLING WORK:
  - S2 edits tests/test_daemon.py at the _bounded_shutdown delegation lambda (~L1472, 10.0->5.0) —
    DISJOINT from S3's test (placed after the _StrandingHost test ~L1005, navigated by name).
  - S1's unit tests (L1490-1600) are distinct (host injected via recorder_host=, no run loop).
  - T1.S2's RecorderHost-level concurrent-stop test is in tests/test_recorder_host.py (different file).

PRODUCTION RUNTIME (what the test models):
  - SIGTERM while armed -> signal thread (request_shutdown: claim + ONE host.stop) + main-thread finally
    (shutdown: WAIT on _teardown_done) -> exactly ONE host.stop() -> bounded exit < TimeoutStopSec=15.
```

## Validation Loop

> Full paths (machine aliases python3->uv run). All gates are the fast pytest suite — NO GPU / models /
> real child / systemd / network. No ruff/mypy configured. Line numbers shift with S1/S2 — gates match
> on TEXT, not line numbers.

### Level 1: The test exists + the file parses + no source touched

```bash
cd /home/dustin/projects/voice-typing
echo "--- the new test exists (by name) ---"
grep -n 'def test_concurrent_request_shutdown_and_shutdown_only_one_stop' tests/test_daemon.py && echo "L1 PASS: test present" || echo "L1 FAIL: test missing"
echo "--- it uses _make_lazy_daemon + host_factory (NOT _make_daemon) ---"
awk '/def test_concurrent_request_shutdown_and_shutdown_only_one_stop/{f=1} f&&/def test_/{if($0!~/concurrent_request_shutdown/)exit} f' tests/test_daemon.py | grep -q '_make_lazy_daemon(host_factory=' && echo "L1 PASS: lazy daemon + factory" || echo "L1 FAIL: should use _make_lazy_daemon(host_factory=)"
echo "--- it asserts exactly ONE host.stop() + wall<8 + clean exit ---"
awk '/def test_concurrent_request_shutdown_and_shutdown_only_one_stop/{f=1} f&&/def test_/{if($0!~/concurrent_request_shutdown/)exit} f' tests/test_daemon.py | grep -q 'stop_calls == 1' && echo "L1 PASS: stop_calls==1 asserted" || echo "L1 FAIL"
awk '/def test_concurrent_request_shutdown_and_shutdown_only_one_stop/{f=1} f&&/def test_/{if($0!~/concurrent_request_shutdown/)exit} f' tests/test_daemon.py | grep -q 'wall < 8.0' && echo "L1 PASS: wall<8 asserted" || echo "L1 FAIL"
echo "--- test_daemon.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('tests/test_daemon.py').read()); print('L1 PASS: test_daemon.py parses')"
echo "--- NO source file modified (test-only task) ---"
git diff --name-only | grep -vxE 'tests/test_daemon.py' && echo "L1 FAIL: a non-test file changed" || echo "L1 PASS: only tests/test_daemon.py"
# Expected: test present by name; uses _make_lazy_daemon(host_factory=); asserts stop_calls==1 + wall<8;
# file parses; ONLY tests/test_daemon.py changed.
```

### Level 2: The new test PASSES (the regression proof)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "test_concurrent_request_shutdown_and_shutdown_only_one_stop" 2>&1 | tail -15
# Expected: 1 PASSED. It exercises the real run() loop + lazy spawn + arm, runs request_shutdown (thread A)
# + shutdown (thread B) concurrently, and asserts host.stop_calls == 1 (mid-flight AND after release),
# wall < 8s, and a clean run-thread exit.
#
# FAILURE DEBUG:
#  * stop_calls == 2 mid-flight -> shutdown() did NOT wait (it started its own _bounded_shutdown). Causes:
#    (a) the gate isn't blocking (did you override stop() to block on stop_release? CRITICAL #1); (b) you
#    started t_main BEFORE observing host.stop_entered so B claimed first (CRITICAL #7); (c) S1 was NOT
#    actually landed (verify `grep -n '_teardown_done' voice_typing/daemon.py` shows the claim+wait).
#  * "run() thread did not exit" -> text() isn't unblocking; ensure _GatedFakeHost.stop() sets _dead
#    BEFORE blocking (CRITICAL #6) and text()'s loop checks _dead (CRITICAL #5).
#  * hang/timeout -> a thread is blocked; the finally must release stop_release + call request_shutdown +
#    join everything (GOTCHA #9). Also ensure stop_release.wait has its OWN timeout (5.0) so a buggy
#    release never hangs the test forever.
#  * "loop did not enter text()" -> arm didn't spawn the host; you used _make_daemon instead of
#    _make_lazy_daemon (CRITICAL #2), so _load_host was a no-op.
```

### Level 3: Regression sensitivity — the test FAILS if S1's coordination is reverted (optional but recommended)

```bash
cd /home/dustin/projects/voice-typing
# PROOF the test is a real guard: temporarily neuter S1's claim so shutdown() always does its own
# teardown (simulating a revert), confirm the test FAILS with stop_calls==2, then RESTORE. Do NOT commit.
cp voice_typing/daemon.py /tmp/daemon.py.bak
.venv/bin/python - <<'PY'
import re, pathlib
p = pathlib.Path("voice_typing/daemon.py")
src = p.read_text()
# Neuter the claim in request_shutdown: force _shutdown_done to stay False there (simulate pre-S1).
src2 = src.replace(
    '            if getattr(self, "_shutdown_done", False):\n                return  # another path already claimed/is doing the teardown — don’t re-tear-down\n            self._shutdown_done = True',
    '            self._shutdown_done = True  # TEMP-NEUTER (S3 regression check): still set so shutdown sees it...\n            pass  # (intentionally broken for the negative check)'
)
# Simpler reliable neuter: make shutdown() IGNORE an already-claimed state and always do its own teardown.
src2 = src.replace(
    "        if already_claimed:\n            # Another path is doing (or did) the teardown — wait for it, do NOT start a second one.",
    "        if False:  # TEMP-NEUTER (S3 regression check): force shutdown() to do its OWN teardown\n            # Another path is doing (or did) the teardown — wait for it, do NOT start a second one."
)
assert src2 != src, "neuter pattern not found — adjust the exact text to the current daemon.py"
p.write_text(src2)
print("TEMP-NEUTER applied (S1 wait branch disabled)")
PY
.venv/bin/python -m pytest tests/test_daemon.py -q -k "test_concurrent_request_shutdown_and_shutdown_only_one_stop" 2>&1 | tail -8
echo "--- RESTORING daemon.py ---"
cp /tmp/daemon.py.bak voice_typing/daemon.py && rm /tmp/daemon.py.bak
git diff --quiet voice_typing/daemon.py && echo "L3 PASS: daemon.py restored clean" || echo "L3 FAIL: daemon.py not restored"
echo "--- re-confirm the test PASSES again on the restored (fixed) code ---"
.venv/bin/python -m pytest tests/test_daemon.py -q -k "test_concurrent_request_shutdown_and_shutdown_only_one_stop" 2>&1 | tail -3
# Expected: with the wait branch neutered, the test FAILLS (stop_calls == 2 — the double teardown
# returns); after restoring daemon.py, it PASSES again. That PROVES the test is a real regression guard
# for S1's coordination (not a happy-path tautology). If it PASSES even when neutered, the gate isn't
# forcing the overlap (re-check CRITICAL #1/#7) or S1 wasn't actually the code path exercised.
```

### Level 4: No regression to the full fast suite + scope guards

```bash
cd /home/dustin/projects/voice-typing
echo "--- full fast suite green (the new test is additive) ---"
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh -q 2>&1 | tail -4
echo "--- sibling shutdown/request_shutdown tests still green ---"
.venv/bin/python -m pytest tests/test_daemon.py -k "request_shutdown or shutdown" -q 2>&1 | tail -5
echo "--- scope: ONLY tests/test_daemon.py changed; read-only files untouched ---"
git diff --name-only
git diff --exit-code -- PRD.md plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/tasks.json plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md voice_typing/daemon.py voice_typing/recorder_host.py .gitignore && echo "L4 PASS: source + read-only files untouched" || echo "L4 FAIL: a source/read-only file was modified"
# Expected: full fast suite green (count rises by 1 from the new test); the request_shutdown/shutdown
# family green; git diff == tests/test_daemon.py ONLY; daemon.py/recorder_host.py/PRD/tasks.json/
# prd_snapshot.md/.gitignore UNCHANGED.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: test present by name; uses `_make_lazy_daemon(host_factory=)`; asserts `stop_calls == 1` + `wall < 8.0`; `tests/test_daemon.py` parses; ONLY `tests/test_daemon.py` changed.
- [ ] L2: the new test PASSES (real run() loop + lazy spawn + arm + concurrent A/B threads; `stop_calls == 1` mid-flight + after release; `wall < 8s`; clean run-thread exit).
- [ ] L3 (recommended): with S1's wait branch neutered, the test FAILS (`stop_calls == 2`); restored → PASSES (proven regression guard).
- [ ] L4: full fast suite green (+1 test); request_shutdown/shutdown family green; diff == `tests/test_daemon.py` only; source + read-only files untouched.

### Feature Validation
- [ ] The test drives the REAL `run()` loop in a thread, lazy-spawns the host on arm via `host_factory`, and arms via `d.start()`.
- [ ] `request_shutdown()` (thread A) and `shutdown()` (thread B) run CONCURRENTLY (verified in-flight via the gated host's `stop_entered` before B starts).
- [ ] `host.stop_calls == 1` (single teardown — the S1/T1.S1 single-flight fix holds under concurrency).
- [ ] `wall < 8.0` (bounded; no deadlock / no `_TEARDOWN_WAIT_TIMEOUT` fallback firing).
- [ ] The run() thread exits cleanly (`not t_run.is_alive()`).
- [ ] No thread is left blocked on any path (the `finally` releases + joins).

### Code Quality Validation
- [ ] `_GatedFakeHost` subclasses `_FakeHost` and overrides ONLY `text()` + `stop()` (full surface preserved so `_load_host`/`run()`/arm work).
- [ ] `_GatedFakeHost.text()` blocks until final or `_dead` (mirrors `RecorderHost.text()`; copied from `_StrandingHost`).
- [ ] `_GatedFakeHost.stop()` sets `_dead` BEFORE blocking (unblocks `text()` → `run()` exits).
- [ ] The `finally` releases the gate + calls `d.request_shutdown()` (idempotent) + joins ALL threads (test isolation).
- [ ] No new imports; reuses `threading`/`time as _time`/`_wait_for`/`_cuda_resolve`/`_make_lazy_daemon`/`_FakeHost`.
- [ ] Banner comment cites bugfix Issue 1 / P1.M1.T2.S3 + the `§Test Gap` mandate + the distinction from S1's unit tests.

### Scope Boundary Validation
- [ ] NO source change (`daemon.py` / `recorder_host.py` / config / systemd / README / ctl unchanged).
- [ ] ONE new test only (no second test; the contract names exactly one).
- [ ] No duplication of S1's `_CountingHost`/`_GatedHost` unit tests (different level: end-to-end vs unit).
- [ ] No real CUDA/GPU/child/systemd/network (hermetic; fast — gated host released promptly).
- [ ] No conflict with S2's parallel `tests/test_daemon.py` edit (disjoint region: S3 near the `_StrandingHost` test ~L1005; S2 at the lambda ~L1472).
- [ ] PRD.md, tasks.json, prd_snapshot.md, bug_analysis.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] DOCS: none (contract §5). The test's docstring + banner are the durable explanation.

---

## Anti-Patterns to Avoid

- ❌ Don't use the default `_FakeHost.stop()` and hope for concurrency — it returns INSTANTLY (`_StubRecorder.shutdown()` is a counter++), so `shutdown()` can't be observed WAITING and the in-flight path isn't exercised. Use a `_GatedFakeHost` whose `stop()` blocks on a release Event (CRITICAL #1).
- ❌ Don't use `_make_daemon(host_factory=)` — it injects a resident `_StubRecorder` so `_load_host` is a no-op and the factory is never called. Use `_make_lazy_daemon(host_factory=)` (recorder=None → spawn on arm) (CRITICAL #2).
- ❌ Don't duplicate S1's unit tests — those inject the host via `recorder_host=` and call the methods directly (no run loop). S3 is the END-TO-END proof (lazy spawn + run loop + arm + concurrent threads) (CRITICAL #3).
- ❌ Don't override the whole `_FakeHost` surface in `_GatedFakeHost` — keep `spawn`/`is_alive`/`pid`/`device`/`set_microphone`/`abort`; override ONLY `text()` + `stop()`, else `_load_host`/`run()`/arm break (CRITICAL #4).
- ❌ Don't use an instant-return `text()` — `run()` would spin and `_text_in_flight` would be flaky to catch. Use the `_StrandingHost`-style blocking `text()` (blocks until final or `_dead`) (CRITICAL #5).
- ❌ Don't block in `stop()` BEFORE setting `_dead` — a blocked `text()` would strand `run()` (the BUG-1 hang). Set `_dead` first, THEN block on the gate (CRITICAL #6).
- ❌ Don't start thread B (`shutdown`) before observing thread A is inside `host.stop()` (`stop_entered`) — you'd lose determinism of the wait path. Observe `stop_entered` first (CRITICAL #7).
- ❌ Don't assert `t_run.is_alive()` mid-test — `run()` exits within ~0.05s of `_dead` being set. Assert run-exit only at the END (GOTCHA #8).
- ❌ Don't skip the `finally` release+join — a failed mid-test assert must not leave threads blocked. Always release the gate + `d.request_shutdown()` (idempotent) + join everything (GOTCHA #9/#10).
- ❌ Don't modify any source file — S3 is TEST-ONLY. Don't add a subprocess/real-SIGTERM test — the contract specifies an IN-PROCESS simulation; the real subprocess bound is an L4 concern out of scope.
- ❌ Don't invoke ruff/mypy — not configured in this project. Use `.venv/bin/python -m pytest`.
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `bug_analysis.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. This is a single additive test (no source change) that
composes two proven patterns already in the file: the `_StrandingHost` run-loop SIGTERM test
(`tests/test_daemon.py:946`, for `run()`-in-thread + lazy spawn + arm + `request_shutdown`) and S1's
`_GatedHost` wait proof (`tests/test_daemon.py:1538`, for the gated-stop + `stop_calls == 1` mid-flight
assertion). Every helper is in scope (`_make_lazy_daemon`, `_fake_host_factory`/`_FakeHost`, `_wait_for`,
`_cuda_resolve`, `threading`, `time as _time`); the threading model is verified against the landed
`run()`/`start()`/`request_shutdown()`/`shutdown()`/`_load_host()` source; and the regression sensitivity
is provable (L3: neuter S1's wait branch → `stop_calls == 2` → test fails). The contract is highly
prescriptive (test name, the SIGTERM two-thread topology, the `stop_calls == 1` + `< 8s` + clean-exit
asserts).

The −1 residual risk is the **concurrency determinism**: the default `_FakeHost.stop()` is instant
(CRITICAL #1), so a literal reading of the contract ("use `_fake_host_factory()`… `_FakeHost.stop()` has
a brief wait") would NOT deterministically exercise the in-flight wait path. This PRP resolves that
explicitly with a `_GatedFakeHost` subclass (preserving the full `_FakeHost` surface) whose `stop()`
blocks on a release Event — the same technique S1's `_GatedHost` already proved — guaranteeing the
overlap window and making `stop_calls == 1` a true regression guard (not a happy-path tautology). The
placement (after the `_StrandingHost` test, navigated by name) is disjoint from S2's parallel
`tests/test_daemon.py` edit (the `_bounded_shutdown` lambda ~L1472). No GPU/models/systemd/network
required for any gate.
