# Research — P1.M1.T2.S3: Concurrent request_shutdown + shutdown SIGTERM-path regression test

This is a TEST-ONLY task (no source change). It adds ONE end-to-end regression test to
`tests/test_daemon.py` that reproduces the SIGTERM double-teardown race (bugfix Issue 1) and proves
the fix (P1.M1.T1.S1 `RecorderHost._stop_lock` + P1.M1.T2.S1 daemon single-flight + P1.M1.T2.S2
5s budget). All findings verified against the live repo + the landed S1/S2 code.

---

## A. The bug + the landed fix (what the test must prove)

### A1. The SIGTERM race (bug_analysis.md L3-31; prd_snapshot §Issue 1)
On SIGTERM while ARMED, TWO threads tear down concurrently:
  - **Thread A (signal-handler thread):** `install_shutdown_signal_handlers` spawns a daemon thread →
    `daemon.request_shutdown()` → `_shutdown.set()` → `_safe_abort()` → `_bounded_shutdown()` →
    `host.stop(timeout)`.
  - **Thread B (main thread):** `run()` exits (it polls `_shutdown`) → `main()`'s `finally` →
    `daemon.shutdown()`.
Pre-fix, `request_shutdown()` deliberately did NOT set `_shutdown_done`, and `shutdown()` did its OWN
`_bounded_shutdown()` → `host.stop()` a SECOND time, concurrently → two parallel ~12s teardowns +
`server.stop()` join → 15.2s → systemd SIGKILL + `Failed with result 'timeout'`. (The `voicectl quit`
path worked because there A and B run SEQUENTIALLY on one socket-worker thread, so B saw the child
already gone.)

### A2. The landed fix (verified in voice_typing/daemon.py, current working copy)
- **P1.M1.T1.S1 (Complete):** `RecorderHost._stop_lock` wraps `stop()` — concurrent `host.stop()`
  calls share ONE teardown (belt-and-suspenders; makes the wait-timeout fallback safe).
- **P1.M1.T2.S1 (Complete, verified):** `request_shutdown()` CLAIMS `_shutdown_done` under `_lock`
  BEFORE the teardown and signals `_teardown_done` (`threading.Event`) in a `finally`. `shutdown()`,
  if `_shutdown_done` already claimed, WAITS on `_teardown_done` (bounded `_TEARDOWN_WAIT_TIMEOUT`,
  OUTSIDE `_lock`) instead of starting a second `_bounded_shutdown()`. On wait-timeout it falls back
  to its own teardown (safe via `_stop_lock`). So on the SIGTERM path EXACTLY ONE `host.stop()` runs.
  - `request_shutdown` verified body: `_shutdown.set()`; `if self._host is None: return`;
    `with self._lock: if getattr(self,"_shutdown_done",False): return; self._shutdown_done=True`;
    `_safe_abort()`; `try: self._bounded_shutdown() finally: self._teardown_done.set()`.
  - `shutdown` verified body: `with self._lock: already_claimed=getattr(...); if not already_claimed:
    self._shutdown_done=True`; `if already_claimed: if self._teardown_done.wait(timeout=_TEARDOWN_WAIT_TIMEOUT): return; (warn+fallback)`;
    `if self._host is None: return; try: self._bounded_shutdown() except ... finally: self._teardown_done.set()`.
- **P1.M1.T2.S2 (landed in this working copy):** `_bounded_shutdown(self, timeout: float = 5.0)`
  (was 10.0). Single teardown ≈ 7s; + `server.stop()` ≈ 2s; total ≤ ~9s < `TimeoutStopSec=15`.

### A3. What the test must assert (the contract)
1. **`host.stop_calls == 1`** (NOT 2) — the single-flight fix prevents the double teardown. Pre-fix
   this would be 2 (both A and B call `host.stop()`; `_FakeHost.stop()` always increments).
2. **Total wall time < 8s** — bounded teardown, no 15s hang/deadlock.
3. **The run() thread exits cleanly.**

---

## B. The test infrastructure (verified exact locations)

### B1. The lazy-boot + host_factory injection seam
- `_make_lazy_daemon(cfg=None, host_factory=None)` (tests/test_daemon.py:2367) — builds a daemon with
  `recorder=None` so `self._host is None` + `_models_loaded=False` at boot (production lazy boot).
  Pass `host_factory=` so `_load_host` spawns the FAKE host (CUDA-free) on the first arm.
  - USE THIS (not `_make_daemon`) for the lazy spawn-on-arm path. `_make_daemon(host_factory=...)`
    injects a default `_StubRecorder` → `_host` is a resident legacy adapter at boot → `_load_host`
    is a no-op → the host_factory is never called. The contract's "_make_daemon() with host_factory="
    is imprecise; `_make_lazy_daemon` is the correct lazy helper.
- `_fake_host_factory(spawn_result=True, device=None)` (L501) — returns a factory callable that builds
  a `_FakeHost`. `_load_host` calls `factory(cfg, feedback, latency, on_final, on_partial, on_speech)`.
- `_load_host` (voice_typing/daemon.py:631) — single-flight spawn: calls `factory(...)`, `host.spawn()`,
  on success installs `self._host`, `_models_loaded=True`, seeds `_resolved_device_cache=host.device`,
  phase='idle'. So after `d.start()`, `d._host` IS the spawned fake.

### B2. `_FakeHost` (tests/test_daemon.py:434) — the surface to preserve
Full surface (mirrors real RecorderHost): `spawn()` (returns True, sets `_alive`), `is_alive`/`pid`
properties, `device` dict, `set_microphone/abort/text` (proxy to a wrapped `_StubRecorder`), `stop(timeout)`.
Attrs of interest: `spawn_calls`, `stop_calls`, `_alive`, `recorder` (the wrapped `_StubRecorder`).
**`stop(timeout=5.0)`** (L481): `stop_calls += 1; self._alive = False`; spawns a daemon thread running
the wrapped `recorder.shutdown()` then `done.set()`; `done.wait(timeout=timeout)`.
**CRITICAL GOTCHA:** `_StubRecorder.shutdown()` (L386) is just `self.shutdowns += 1` — INSTANT. So
`_FakeHost.stop()`'s `done.wait(timeout)` returns IMMEDIATELY (microseconds). => the default
`_FakeHost.stop()` gives NO concurrency-overlap window. The contract's claim ("_FakeHost.stop() has a
brief wait ... gives the concurrency overlap window") is INCORRECT for the default. To DETERMINISTICALLY
reproduce the concurrent race (the whole point of this test), use a `_GatedFakeHost(_FakeHost)` subclass
whose `stop()` blocks on a release Event. (This is the single most important detail for one-pass success.)

### B3. The closest analog: `_StrandingHost` SIGTERM test (tests/test_daemon.py:946)
`test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final` is the template for the run-loop +
arm + SIGTERM structure:
- `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)`
- subclass `_FakeHost` (`_StrandingHost`) with a `text()` that BLOCKS until a final OR `_dead` (mirrors
  `RecorderHost.text()`), and a `stop()` that sets `_dead=True` (child death → text() returns).
- wrap the factory: `_wrap(*a,**k)` builds the subclass sharing `recorder`/`device`.
- `_make_lazy_daemon(host_factory=_wrap)`; `t=Thread(target=d.run,daemon=True); t.start()`;
  `d.start()` (arm → lazy spawn); `_wait_for(lambda: d._text_in_flight.is_set())`; `d.request_shutdown()`;
  `_wait_for(lambda: not t.is_alive())`.
S3 EXTENDS this: instead of only `request_shutdown`, it runs `request_shutdown` (thread A) AND
`shutdown` (thread B) CONCURRENTLY and asserts `stop_calls == 1`.

### B4. S1's unit-level proof (distinct from S3 — do NOT duplicate)
`_CountingHost`/`_GatedHost` (tests/test_daemon.py:1490/1501) + 6 tests (L1516-1600). These inject the
host DIRECTLY via `_make_daemon(recorder_host=host)` and call `request_shutdown()`/`shutdown()` directly
— NO `run()` loop, NO `d.start()` arm, NO `host_factory`. They are the UNIT proof; S3 is the END-TO-END
proof (real run() loop + lazy spawn + arm). `test_shutdown_waits_for_inflight_teardown_no_second_stop`
(L1538) is S1's unit analog of S3 — S3 mirrors its assertions through the real lifecycle.

### B5. Helpers available (no new imports needed)
- `_wait_for(predicate, timeout=2.0, interval=0.01)` (L417) — poll-until helper.
- `_cuda_resolve(monkeypatch, mapping)` (L69) — pins `cuda_check.resolve_device_and_models` hermetic.
  (For a lazy daemon `_log_resolved_device()` is skipped at boot and `_resolved_device_cache` is seeded
  from `host.device`, so the probe isn't strictly hit — but call it anyway: belt-and-suspenders + matches
  the contract INPUT + the `_StrandingHost` precedent.)
- `threading` + `time as _time` already imported in this file (L333-334). `_time.monotonic()` for the
  wall-time bound.

### B6. bug_analysis.md §Test Gap (L61-65) — the explicit mandate
> "No existing test exercises the concurrent `request_shutdown()` + `shutdown()` path (the SIGTERM
> path). The existing `test_request_shutdown_*` tests call `request_shutdown()` on the test thread,
> and `test_shutdown_*` tests call `shutdown()` on the test thread — never both concurrently with a
> real _FakeHost. Need a new test that spawns `request_shutdown()` on one thread and `shutdown()` ..."
S3 IS that test.

---

## C. The threading model the test drives (verified in voice_typing/daemon.py)

- **`run()` loop (L702-797):** `while not self._shutdown.is_set():` — if `_listening.is_set()`:
  `_text_in_flight.set(); try: self._host.text(self.on_final) finally: _text_in_flight.clear()`; else
  `time.sleep(0.05)`. Exits when `_shutdown` is set. With a `_StrandingHost`-style blocking `text()`,
  run() is genuinely blocked in `host.text()` while listening (realistic).
- **`start()` (L1109):** `_load_host()` (outside `_lock`) → spawn host → `with _lock: _arm()` (sets
  `_listening` + `host.set_microphone(True)`).
- **`request_shutdown()` (L1148):** `_shutdown.set()`; `if host None: return`; claim `_shutdown_done`
  under `_lock`; `_safe_abort()`; `try: _bounded_shutdown() finally: _teardown_done.set()`.
- **`_bounded_shutdown(timeout=5.0)` (L1294):** `if host None: return; try: self._host.stop(timeout)`.
- **`shutdown()` (L1321):** read/claim `_shutdown_done`; if already claimed → `_teardown_done.wait(
  _TEARDOWN_WAIT_TIMEOUT)` then return (or fallback); else own teardown + `_teardown_done.set()`.

**Determinism via the gated host:** with `_GatedFakeHost.stop()` blocking on a release Event, thread A
(`request_shutdown`) is OBSERVABLY inside `host.stop()` (via a `stop_entered` Event) when thread B
(`shutdown`) runs. That GUARANTEES the in-flight window during which `shutdown()` must WAIT (not start a
2nd `stop()`). The test asserts `stop_calls == 1` BOTH mid-flight (B is waiting) and after release.

---

## D. Regression sensitivity (why this test catches a revert of S1)

Pre-S1 code: `request_shutdown()` does NOT claim `_shutdown_done`; `shutdown()` always sees
`_shutdown_done=False` → claims → does its OWN `_bounded_shutdown()` → `host.stop()`. So BOTH threads
call `host.stop()` → `stop_calls == 2` (deterministically — `_FakeHost.stop()` always increments, no
`_proc` short-circuit). Post-S1: `shutdown()` waits → `stop_calls == 1`. So `assert stop_calls == 1`
reliably FAILS if S1 is reverted (and the gated host guarantees the overlap that makes the wait path
the one exercised). This makes S3 a true regression guard, not just a happy-path test.

---

## E. Parallel-execution / no-conflict boundary

- **S1 (Complete) + S2 (parallel, landed in this copy):** S3 CONSUMES their outputs (the single-flight
  coordination + the 5s budget). S3 changes NO source — it only adds a test. No conflict.
- **S2 edits test_daemon.py** at the `_bounded_shutdown` delegation lambda (~L1472, `10.0`→`5.0`) +
  its assertion. S3's new test is placed far from that (after the `_StrandingHost` SIGTERM test, ~L1005,
  navigated by test NAME) — disjoint region, no merge tangle.
- **T1.S2 (Complete)** added the RecorderHost-level concurrent-stop test in `tests/test_recorder_host.py`
  (different file). S3 is daemon-level in `tests/test_daemon.py`. No overlap.
