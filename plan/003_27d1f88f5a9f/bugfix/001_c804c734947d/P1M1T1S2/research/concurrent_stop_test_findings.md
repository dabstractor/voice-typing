# Research Note: concurrent-stop single-flight regression test (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo (`voice_typing/recorder_host.py`, `tests/test_recorder_host.py`) on July 14 2026.
**Purpose:** Pin the exact `stop()`/`_terminate_group` flow, the existing test patterns to mirror, and the deterministic single-flight proof for the new concurrency test.

---

## §1. S1 is ALREADY APPLIED — the test PASSES on first run

`voice_typing/recorder_host.py` already contains S1's `_stop_lock`:
- **L140** (in `__init__`, right after `self._proc: Any = None`): `self._stop_lock = threading.Lock()`
- **L274**: `with self._stop_lock:` wrapping the WHOLE `stop()` body.
- **L275**: `if self._proc is None:` is the FIRST statement INSIDE the with-block (the load-bearing single-flight invariant).

→ The new S2 test is expected to PASS on first run. It is the committed regression guard that proves S1's invariant holds under concurrent access.

## §2. The exact `stop()` flow + `_terminate_group` (what the test drives)

`stop(self, timeout: float = _STOP_JOIN_TIMEOUT_S) -> None` (L255-296), body under `with self._stop_lock:`:
1. `if self._proc is None: return` (guard INSIDE the lock — the single-flight point).
2. `self._abort_event.set()` (real `mp.Event`; harmless in-test).
3. `self._cmd_q.put(("shutdown", {}))` (real `mp.Queue`; unbounded → never blocks; item just accumulates).
4. `self._proc.join(timeout=timeout)`.
5. `if self._proc.is_alive():` → `logger.warning(...)` → `self._terminate_group()` → `self._proc.join(timeout=2.0)`.
6. `self._dead = True` ; `self._proc = None`.

`_terminate_group()` (L356-374):
- `if self._proc is None: return` ; `pid = self._proc.pid` ; `if pid is None: return`.
- `pgid = os.getpgid(pid)` ; `os.killpg(pgid, signal.SIGKILL)` (wrapped in `except (ProcessLookupError, PermissionError, OSError)`).

**`os` is imported as a module** (`import os` at L63; `signal` at L64). So `recorder_host.os` IS the `os` module → tests monkeypatch **`recorder_host.os.getpgid`** and **`recorder_host.os.killpg`** (the contract's exact targets). A real `os.getpgid(fake_pid)` would raise `ProcessLookupError` → the monkeypatch is MANDATORY, not optional.

## §3. Existing test patterns to mirror (tests/test_recorder_host.py, 317 lines)

- Imports already present: **`threading` (L18), `time` (L19)**, `from voice_typing import recorder_host`. → the new test needs NO new imports.
- **`_make_host(*, on_final=None, on_partial=None, on_speech=None, force_cpu=False)`** (L48): builds a `RecorderHost` with `_FakeFeedback` + `_FakeLatency` + dummy `cfg=object()`. NO child spawned. Returns the host.
- **`_DeadProc`** (INNER class in `test_stop_with_dead_process_is_noop`, L218-227): `pid = 12345`, `is_alive()->False`, `join(timeout=None)->pass`. The test sets `host._proc = _DeadProc()` then `host.stop()`.
- **`test_stop_is_noop_when_no_process`** (L213): `_make_host(); host.stop()` — single-caller, no-proc no-op.
- **`test_stop_with_dead_process_is_noop`** (L218): injects `_DeadProc`, `host.stop()` — single-caller, dead-proc (is_alive False → skips terminate_group).

The new test mirrors `_DeadProc` but inverts it: a **`_SlowProc`** with `is_alive()->True` and `join()->time.sleep(0.3)`, so `stop()` enters the join → terminate_group path (not the early-return) and forces a ~0.6s teardown per caller.

## §4. The deterministic single-flight proof (killpg count)

The distinguishing signal is the **`os.killpg` call count**, recorded via a monkeypatched list:

| S1 state | Caller A | Caller B | `len(killpg_calls)` |
|---|---|---|---|
| **Applied (with `_stop_lock`)** | acquires lock → full join+terminate_group → `_proc=None` | blocks on lock → sees `_proc is None` → returns | **1** |
| Reverted (no serialization) | passes guard → join+terminate_group | passes guard → join+terminate_group | **2** |

The 0.3s `_SlowProc.join` makes the race window HUGE and deterministic: with the barrier both threads enter `join()` together; both only proceed past `is_alive()` after the sleep. Without the lock both reach `_terminate_group` → killpg fires twice, reliably. With the lock the second caller provably no-ops. → `assert len(killpg_calls) == 1` is the load-bearing assertion (the contract's "at most once"; precisely exactly-once here because `_SlowProc.is_alive()` is always True so caller A always reaches terminate_group).

## §5. Timing budget (why `< 2.0s`)

With the lock: caller A = `_SlowProc.join` (0.3s) + `_terminate_group` (monkeypatched, instant) + second `_SlowProc.join(timeout=2.0)` (0.3s — the fake ignores the 2.0 and sleeps 0.3) ≈ **0.6s**. Caller B blocks on the lock ~0.6s then no-ops. Both finish ≈ 0.6s. `assert elapsed < 2.0` is a generous CI-safe bound (actual ~0.6s). The timing assertion is a sanity bound, NOT the distinguishing signal (killpg count is).

## §6. The "test actually guards" validation (mutation, no import needed)

To prove the test is not vacuous (a real risk for concurrency tests), temporarily DEFEAT single-flight in `recorder_host.py` with a one-line, no-import swap and confirm the test goes RED:

```bash
# MUTATION: replace the lock-context with a no-op 'if True:' (body indentation unchanged)
sed -i 's/^        with self\._stop_lock:/        if True:  # MUTATION/' voice_typing/recorder_host.py
.venv/bin/python -m pytest tests/test_recorder_host.py::test_concurrent_stop_calls_share_one_teardown -v
# EXPECT: FAIL — assert len(killpg_calls) == 1  (got 2)
git checkout voice_typing/recorder_host.py   # RESTORE S1
```

`if True:` is chosen because: (a) one line, (b) needs no `import`, (c) the existing indented body stays valid under it, (d) trivially git-revertible. After the swap, two threads run `stop()`'s body concurrently → killpg fires twice → the `== 1` assertion fails. This proves the test catches the regression (it is not a vacuous pass).

Optionally also run the (restored) test in a loop to confirm zero flakiness: `for i in $(seq 1 20); do .venv/bin/python -m pytest tests/test_recorder_host.py::test_concurrent_stop_calls_share_one_teardown -q || break; done`.

## SUMMARY (what S2 can rely on)

1. ✅ S1 applied: `_stop_lock` (L140) wraps `stop()` body (L274), guard inside (L275). Test PASSES first run.
2. ✅ Mirror `_DeadProc`/`_make_host` patterns; define `_SlowProc` (is_alive True, join sleeps 0.3s). `threading`+`time` already imported.
3. ✅ MANDATORY monkeypatch: `recorder_host.os.getpgid` (→ fake pgid) + `recorder_host.os.killpg` (→ list recorder); a real `os.getpgid(fake_pid)` raises `ProcessLookupError`.
4. ✅ Two threads + `threading.Barrier(2)` for deterministic contention.
5. ✅ Load-bearing assertion: `len(killpg_calls) == 1` (single-flight). Plus: no errors, both threads finish, `elapsed < 2.0`, `host._proc is None`, `host._dead is True`.
6. ✅ Mutation validation: `sed` swap `with self._stop_lock:` → `if True:` → test FAILS (killpg==2) → `git checkout` restore.
7. ✅ Test-only subtask: only `tests/test_recorder_host.py` edited; `recorder_host.py`/`daemon.py` untouched (the mutation is transient + restored).
