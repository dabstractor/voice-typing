# Research — bounded-teardown audit (P1.M2.T2.S3 / PRD §4.2bis Idle-unload + §8 risk row)

This note pins the teardown mechanism's file:line evidence, the bounded-budget math, the BUG-1
fix, the test evidence, and the non-defect nuances. The PRP (../PRP.md) references it as the single
source of truth. **VERDICT: the bounded teardown is PRD §4.2bis + §8-risk-row COMPLIANT — no fix
needed.** All 5 item properties (a)-(e) pass with file:line evidence.

## 0. What this audit owns (scope) — DISJOINT from §1/§2

`gap_lifecycle.md` already has §1 (P1.M2.T2.S1, the lazy-load STATE MACHINE) and §2 (P1.M2.T2.S2,
the recorder-host IPC MECHANISM — which already recorded stop@272-329 + _terminate_group@394-413 +
killpg@407 + setsid@446 at the IPC level). **§3 (THIS) owns the teardown TIMING/ORCHESTRATION**:
the daemon-side single-flight lock around teardown, the bounded join(5s)+killpg budget that
SUPERSIDES the ~90s RealtimeSTT wedge, the idle-unload WATCHDOG that triggers it, and the
request_shutdown BUG-1 fix that unblocks a wedged text(). §2's stop/killpg findings are the
mechanism; §3 certifies the TIMING + the daemon orchestration that makes idle-unload safe
(acceptance #9). No overlap with §1 (states) or §2 (IPC vocabulary); §3 references them.

## 1. The mechanism under audit (2 files, ~7 regions)

**recorder_host.py** — the killpg teardown primitive (certified COMPLIANT at the IPC level in §2;
§3 certifies the BUDGET + how the daemon calls it):
- `_STOP_JOIN_TIMEOUT_S: float = 5.0` (L87) — the default join budget (the "join(5s)").
- `stop(self, timeout: float = _STOP_JOIN_TIMEOUT_S)` (L272) — SINGLE-FLIGHT under `self._stop_lock`
  (L297): abort_event.set() (L300-302, unblock a child blocked in text()); detached "shutdown" cmd
  thread (L311-316, NEVER waited on — the join+killpg is the real teardown); `self._proc.join
  (timeout=timeout)` (L318, BOUNDED); if still alive → warning (L319-322) → `_terminate_group()`
  (L323) → `self._proc.join(timeout=2.0)` (L325); then `_dead=True` (L327) + `_proc=None` (L328).
- `_terminate_group(self)` (L394) — `pgid = os.getpgid(pid)` (L406) + `os.killpg(pgid,
  signal.SIGKILL)` (L407); best-effort catches ProcessLookupError/PermissionError/OSError (L409).
- `os.setsid()` in the child `_worker_main` (L446) — makes the child its own session/group leader so
  getpgid(pid)==pid and killpg reaches the RealtimeSTT grandchildren (transcript_process/reader_process).

**daemon.py** — the teardown orchestration (THIS audit's core):
- `_idle_unload_watchdog(self)` (L1160) — daemon thread; `while not self._shutdown.wait(1.0):`
  (L1168, ticks ~1s AND exits promptly on shutdown) → `_maybe_idle_unload()` (L1170).
- `_maybe_idle_unload(self)` (L1172) — LOCK-FREE pre-check (atomic bool/float/Event reads): threshold
  `= self._cfg.asr.auto_unload_idle_seconds` (L1181); short-circuit if `threshold <= 0` (L1182); else
  return if `not self._models_loaded` / `self._listening.is_set()` / `self._disarmed_monotonic is
  None` / `time.monotonic() - self._disarmed_monotonic < threshold` (L1183-1187); else delegate to
  `_unload_recorder()` (L1188).
- `_unload_recorder(self)` (L1197) — back-compat alias → `self._unload_host()` (L1201).
- `_unload_host(self)` (L1204) — THE idle-unload teardown. `with self._lock:` (L1223, the SAME lock
  `_load_host` uses @714 — single-flight, PRD §4.2bis "SAME single-flight lock as load"); re-checks
  the FULL condition UNDER the lock (L1224-1231: not loaded / listening / disarmed_mono None /
  threshold<=0 / not enough time — a racing arm ABORTS the unload); then `self._bounded_shutdown
  (timeout=5.0)` (L1236); reset `self._host=None`@1240, `_models_loaded=False`@1241,
  `set_phase("unloaded")`@1242, `set_models_loaded(False)`@1243, reseed `_resolved_device_cache`@1246.
- `_bounded_shutdown(self, timeout: float = 5.0)` (L1620) — routes through `self._host.stop(timeout=
  timeout)` (L1634); None host = no-op (L1632); best-effort, never re-raises (L1635-1636).
- `shutdown(self)` (L1647) — idempotent + single-flight via `_shutdown_done` (under _lock) +
  `_teardown_done` (Event) coordinating the SIGTERM path (request_shutdown signal-thread +
  main-thread finally run concurrently: first claims+tears down+signals; second WAITS bounded).
  Delegates to `_bounded_shutdown()`.
- `request_shutdown(self)` (L1454) — THE BUG-1 fix. `self._shutdown.set()` (L1486); cancels the drain
  timer (L1489-1492); None host → return (L1494-1495); CLAIMs `_shutdown_done` under _lock
  (L1498-1503, idempotent); `self._safe_abort()` (L1505, OUTSIDE _lock, gated on _text_in_flight);
  `self._bounded_shutdown()` (L1510, kills the child group → host.text()'s wait-loop detects child
  death → unblocks run()); `self._teardown_done.set()` (L1514, try/finally — always fires).

## 2. ★ THE 5 PROPERTY-BY-PROPERTY VERDICT (file:line) ★

| # | item property | PRD §4.2bis/§8 expected | code actual (file:line) | verdict |
|---|---|---|---|---|
| (a) | stop() joins child w/ timeout, then _terminate_group() killpg | "join(5s) then SIGKILL the group" (§4.2bis resolved ¶) | recorder_host.py: `_STOP_JOIN_TIMEOUT_S=5.0`@87; `stop(timeout=…)`@272; `self._proc.join(timeout=timeout)`@318; `if self._proc.is_alive(): _terminate_group(); join(2.0)`@319-325; `_terminate_group`: `pgid=os.getpgid(pid)`@406 + `os.killpg(pgid, SIGKILL)`@407; child `os.setsid()`@446 | ✅ COMPLIANT |
| (b) | _unload_host acquires the SAME single-flight lock as load | "Teardown runs under the SAME single-flight lock as load" (§4.2bis) | daemon.py: `_unload_host` `with self._lock:`@1223 == `_load_host` `with self._lock:`@714 (same `threading.Lock` @591, shared by `Condition(self._lock)`@665); full-condition re-check UNDER lock @1224-1231 (a racing arm aborts the unload) | ✅ COMPLIANT |
| (c) | idle-unload watchdog tears down after auto_unload_idle_seconds of loaded+not-listening | "after auto_unload_idle_seconds (default 1800) of loaded/not-listening" (§4.2bis Idle unload) | daemon.py: `_idle_unload_watchdog` ticks `_shutdown.wait(1.0)`@1168 → `_maybe_idle_unload`@1170; pre-check `threshold=self._cfg.asr.auto_unload_idle_seconds`@1181, short-circuit `threshold<=0`@1182, return if `not _models_loaded`/`_listening.is_set()`/`_disarmed_monotonic is None`/`elapsed < threshold`@1183-1187; → `_unload_recorder()`→`_unload_host()`@1188/1197/1201 | ✅ COMPLIANT |
| (d) | teardown bounded (seconds), NEVER 90s | "MUST NOT reproduce the ~90s teardown hang" (§8 risk row; §4.2bis hard req) | recorder_host.py stop() join(5)+killpg+join(2)=~7s max@318-325 (CANNOT wedge — killpg is unconditional after the join budget); daemon.py `_bounded_shutdown(timeout=5.0)`→`host.stop(timeout=5)`@1634/1620; `stop()` docstring@282-284 "cannot reproduce RealtimeSTT's ~90s shutdown wedge; we do NOT wait on its unbounded thread joins"; `shutdown()` docstring@1657-1661 confirms the wedge is superseded | ✅ COMPLIANT |
| (e) | request_shutdown kills the child group so blocked text() unblocks (BUG-1 fix) | "Killing the child guarantees host.text() returns" (BUG-1; §4.2) | daemon.py `request_shutdown`@1454: `_shutdown.set()`@1486 → `_safe_abort()`@1505 → `_bounded_shutdown()`@1510 (kills group); docstring@1463-1472 "Killing the child (host.stop()) guarantees host.text()'s loop sees a dead child and returns within ~0.5s"; git: `84f03e8 P1.M4.BUG1: tear down child on shutdown to fix SIGTERM hang` + `4526870 P1.M1.T2.S3: end-to-end SIGTERM race regression test` | ✅ COMPLIANT |

## 3. ★ TEST EVIDENCE (the contract's run target — re-ran live) ★

```
$ timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py \
    -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'
42 passed, 177 deselected in 2.12s
```

Key evidence tests (re-locate with `-k`): the killpg `_terminate_group` (recorder_host tests:
SIGKILL-the-group + getpgid); `stop()` single-flight under `_stop_lock` (concurrent-stop shares ONE
teardown); `_unload_host` single-flight lock + racing-arm-aborts-unload (daemon tests); the idle-
unload watchdog firing after the threshold + the lock-free pre-check; `request_shutdown` +
`shutdown` SIGTERM-race (concurrent teardown shares ONE bounded `_bounded_shutdown`, fits under
TimeoutStopSec); the `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded` test
(pins the _bounded_shutdown→host.stop routing); the BUG-1 SIGTERM e2e regression
(`4526870`, `test_sigterm_*`).

## 4. ★ NON-DEFECT NUANCES (record so they are NOT mistaken for gaps) ★

1. **Two single-flight layers (intentional).** The daemon `_lock` (daemon.py:591) serializes
   arm-vs-teardown (`_load_host`@714 vs `_unload_host`@1223). `RecorderHost._stop_lock`
   (recorder_host.py) serializes CONCURRENT stop() calls (request_shutdown signal-thread +
   main-thread finally both call stop on the SIGTERM path — `_stop_lock` makes exactly ONE
   process-group teardown run, bugfix Issue 1 / P1.M1.T1.S1). Both are needed; neither is redundant.
2. **`_unload_host` calls `_bounded_shutdown(timeout=5.0)`, NOT `host.stop()` directly** (daemon.py
   :1236). `_bounded_shutdown` (L1620) is a thin router → `host.stop(timeout=5)` (L1634) + a None-
   host no-op guard + best-effort try/except. The indirection is pinned by
   `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded`. Net effect == host.stop().
3. **The graceful "shutdown" cmd is sent on a DETACHED daemon thread and NEVER waited on**
   (recorder_host.py:311-316). The child's command loop BLOCKS in recorder.text() while listening,
   so it does not drain cmd_q until an abort unblocks it; and an mp.Queue.put could block on a
   wedged child's feeder thread. So the detached thread swallows all errors; the join+killpg is the
   ACTUAL teardown. This is WHY teardown is bounded (we never block on the queue).
4. **`abort_event.set()` is called BEFORE the join** (recorder_host.py:300-302) so a child blocked
   in text() unblocks cooperatively and the join can complete fast (often << 5s). The killpg is the
   belt-and-suspenders for a child that ignores the abort.
5. **The idle-unload watchdog pre-check is LOCK-FREE** (daemon.py:1183-1187, atomic CPython reads)
   so the common "not time yet" path does NOT acquire `_lock` every 1s tick; `_unload_host` does the
   authoritative re-check UNDER `_lock` (L1224-1231). Performance design, not a gap.
6. **`request_shutdown` runs abort + _bounded_shutdown OUTSIDE `_lock`** (daemon.py:1505/1510); only
   the `_shutdown_done` CLAIM is under `_lock` (L1498-1503, short critical section). So a slow teardown
   cannot wedge the shutdown signal or block concurrent start/stop/toggle (validation NEW-2).
7. **The budget math** (bugfix Issue 1 / Fix 1C, P1.M1.T2.S2): host.stop(timeout=5) → join(5) +
   killpg + join(2) = ~7s max per call (only if the child wedges the full join; normally << that);
   + ControlServer.stop() join(2) ≈ ~2s; with daemon single-flight (exactly ONE _bounded_shutdown on
   the SIGTERM path) the total is ≤ ~9s — comfortable under systemd `TimeoutStopSec=15`. The default
   was 10.0 (→ ~12s/call, ~14s total, no margin); 5.0 makes the single-teardown path fit.

## 5. VERDICT + acceptance linkage

**✅ COMPLIANT on all 5 properties — no fix needed.** The teardown is bounded (killpg after a 5s join,
~7s max/call, ~9s total single-flight), so it CANNOT reproduce RealtimeSTT's ~90s `recorder.shutdown()`
wedge. This is the PRD §4.2bis "Hard requirement — bounded teardown" + the §8 risk-row mitigation,
and it is the prerequisite the **Idle unload** feature (acceptance #9: "the recorder unloads (~0 VRAM)
and a later arm reloads it; the teardown is bounded (completes in seconds, no 90s hang)") depends on.
No source/test files modified (read-only audit). The only artifact is the appended §3 report.

## 6. The append convention (§3 to gap_lifecycle.md)

`gap_lifecycle.md` currently has §1 (S1 lazy-load) + §2 (S2 IPC). **S3 APPENDS §3** (bounded
teardown) below §2 — same convention as P1.M2.T1.S2's §2-append to `gap_daemon_loop.md` (L156+) and
S2's §2-append here. Each section is self-contained under a `# §N — …` heading with its own
Scope/Audited-artifacts/Bottom-line/§N.1 Method/§N.2 compliance-table/§N.3 test-evidence/
§N.4 nuances/§N.5 Conclusion. §2's conclusion already says "the bounded teardown TIMING is S3" — §3
delivers it. DISJOINT content from §1/§2 → composes without conflict.

## 7. Tooling & validation (verified)

- pytest 9.x in `.venv`. Run the slice: `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py
  tests/test_recorder_host.py -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'`
  → 42 passed, 177 deselected in 2.12s (re-ran live).
- AGENTS.md Rule 1: wrap with `timeout 300` (inner) + the bash-tool timeout (outer). The slice is
  mocked-CUDA (fast) but the timeout is non-negotiable (the repo has hang vectors).
- ruff at `/home/dustin/.local/bin/ruff` (NOT in .venv); mypy NOT installed — pytest is the gate.
- FULL paths: `.venv/bin/python -m pytest ...` (zsh aliases python/pytest).

## 8. Scope (do / don't)

DO: APPEND a `# §3 — Bounded Teardown (P1.M2.T2.S3)` section to
`plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` with the 5-property compliance table
(file:line), the test evidence (42 passed), the 7 nuances, and the COMPLIANT verdict.

DON'T: edit `voice_typing/daemon.py` / `recorder_host.py` / any test (no defect exists — read-only
audit); edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`; re-audit the lazy-load states (§1)
or the IPC vocabulary (§2) — §3 owns teardown TIMING/orchestration only and REFERENCES §1/§2; create
a NEW standalone file (the item OUTPUT is "Append to gap_lifecycle.md"). DOCS: none (internal lifecycle).