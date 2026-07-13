# Research Note: bounded teardown implementation (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo (`voice_typing/daemon.py`, `tests/test_daemon.py`, the installed RealtimeSTT wheel) on July 13 2026.
**Purpose:** Pin the exact edit anchors, the test-fake contracts, and the one critical compatibility trap for `_bounded_shutdown`.

---

## §1. Current `shutdown()` — exact body + location (the edit site)

`voice_typing/daemon.py:818-844`. Verbatim body (the part S2 rewrites):

```python
    def shutdown(self) -> None:
        """Full recorder teardown (PRD §4.2; P1.M4.T2.S2). Idempotent + defensive.
        ...docstring (L819-835)...
        """
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return
            self._shutdown_done = True
        try:
            self._recorder.shutdown()
            logger.info("recorder shutdown complete (GPU workers released)")
        except Exception:
            logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
```

- Idempotency guard: `with self._lock:` + `getattr(self,"_shutdown_done",False)` + `self._shutdown_done=True`. NO `__init__` edit (getattr-guarded). KEEP as-is.
- Defensive: the `except Exception: logger.exception(...)` swallows + logs. KEEP the "never re-raise" contract.
- **S2 change**: insert `if self._recorder is None: return` (M2 lazy-load prep) and replace `self._recorder.shutdown()` with `self._bounded_shutdown()`.

`daemon.py` ALREADY imports `threading` (L75) and `time` (L76) at module top → `_bounded_shutdown` needs NO new imports.

## §2. The docstring + comment tags to update (DOCS deliverable)

- **L819** (shutdown docstring opener): `"""Full recorder teardown (PRD §4.2; P1.M4.T2.S2). Idempotent + defensive.` → rewrite to describe the **bounded** behavior + force-cleanup (drop the stale P1.M4.T2.S2 tag; this is now the bounded-teardown of plan 003).
- **L11** (module-top SCOPE block): `  - LATER: control socket (P1.M4.T2.S1), full clean shutdown (P1.M4.T2.S2 — recorder.shutdown()),` → update the "full clean shutdown" part: bounded teardown is now IMPLEMENTED (the control socket is also long since done; keep the edit surgical to the shutdown clause per the contract).
- **L409**: `    toggle-on). NEVER recorder.shutdown() on toggle/stop — only on quit (P1.M4.T2.S2).` → drop/refresh the stale `(P1.M4.T2.S2)` tag (the "NEVER on toggle/stop" rule STAYS — it is still correct; only the stale plan tag changes).

Exact anchor text captured verbatim for precise edits (see PRP Implementation Tasks).

## §3. RealtimeSTT attributes for force-cleanup (confirmed from S1 analysis + installed wheel)

The force-cleanup branch touches these `recorder` attributes (all confirmed in `realtimesttt_shutdown_analysis.md` + `_confirmed.md`):

| Attribute | Type | Force-cleanup action |
|---|---|---|
| `transcript_process` | `mp.Process` (spawn) — holds CUDA context/VRAM | `.is_alive()` → `.terminate()` (releases VRAM) |
| `reader_process` | `mp.Process` (spawn) — holds mic + VRAM | `.is_alive()` → `.terminate()` |
| `is_shut_down` | `bool` flag | set `= True` (makes future `.shutdown()` idempotent — `shutdown_recorder()` returns early) |
| `realtime_transcription_model` | whisper model ref | set `= None` (lets GC reclaim host-side model state) |

`recording_thread` / `realtime_thread` are `threading.Thread` with `.daemon=True` → CANNOT be killed, and NEEDN'T be (they die with the process). S2 does NOT touch them.

## §4. Test fakes — contracts S2 must preserve / extend

`tests/test_daemon.py` (additive-section style; later sections add their own imports):
- **L346 `import threading`**, **L347 `import time as _time`** — module-level after L347; the new test reuses them (no new import needed if placed after L347; or add a local `import threading`/`import time as _time` to match the additive style).
- **`_StubRecorder` (L365-390)**: has `.text_calls`, `.mic`, `.aborts`, **`.shutdowns`** (int, incremented in `shutdown()`), `.text()`, `.set_microphone()`, `.abort()`, `.shutdown()`. Fast (returns instantly).
- **`_make_daemon(*, recorder=None, backend=None, cfg=None)` (L424-430)**: helper; `recorder=None` → builds a `_StubRecorder()`. Returns `(d, fb, rec, be)`.
- **`_RaisingRecorder(_StubRecorder)` (L1074-1079)**: `.shutdown()` does `self.shutdowns += 1; raise RuntimeError("boom (test)")`.

**Existing shutdown tests S2 MUST keep green (L1058-1095):**
- `test_shutdown_calls_recorder_shutdown_once` → after `d.shutdown()`, `rec.shutdowns == 1`.
- `test_shutdown_is_idempotent` → 3× `d.shutdown()` → `rec.shutdowns == 1`.
- `test_shutdown_swallows_recorder_failure` → `d.shutdown()` with `_RaisingRecorder` does NOT raise; `rec.shutdowns == 1`; AND `caplog` contains `"recorder.shutdown() failed"`.
- `test_stop_and_request_shutdown_still_never_shutdown` → `rec.shutdowns == 0` after start/stop/toggle/request_shutdown.

## §5. THE CRITICAL COMPATIBILITY TRAP (the one thing that breaks existing tests)

The architecture-analysis SKETCH of `_bounded_shutdown` uses:
```python
def _do_shutdown():
    try: self._recorder.shutdown()
    except Exception: pass      # ← SILENT swallow
    finally: done.set()
```
**That `except Exception: pass` would BREAK `test_shutdown_swallows_recorder_failure`**, which asserts the `"recorder.shutdown() failed"` log line is present in `caplog`. The silent swallow erases it.

**FIX (mandatory):** the inner thread must LOG the exception, exactly as the current code does:
```python
def _do_shutdown():
    try:
        self._recorder.shutdown()
        logger.info("recorder shutdown complete (GPU workers released)")
    except Exception:
        logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
    finally:
        done.set()
```
`logger.exception` (ERROR level, on `voice_typing.daemon`) is captured by `caplog.at_level(logging.ERROR, logger="voice_typing.daemon")`. Because `done.set()` is in `finally` (after the except block logged), when `done.wait()` returns True the log record is already emitted → the assertion holds. **caplog is thread-safe** (handler-based), so logging from the daemon thread is fine.

This also preserves the success INFO log ("recorder shutdown complete (GPU workers released)") for the fast path — moved inside the thread.

## §6. Timing/happens-before for the fast-path `.shutdowns` assertions

`_StubRecorder.shutdown()` increments `.shutdowns` then returns. In `_bounded_shutdown`:
- `_do_shutdown` (daemon thread): `recorder.shutdown()` (`.shutdowns += 1`) → `finally: done.set()`.
- main: `done.wait(timeout)` returns True ONLY after `done.set()`, i.e. AFTER `.shutdowns` was incremented.
- `d.shutdown()` returns only after `_bounded_shutdown` returns (after `done.wait()`).

∴ when `d.shutdown()` returns, `rec.shutdowns == 1` is guaranteed (no race). The existing `test_shutdown_calls_recorder_shutdown_once` / `test_shutdown_is_idempotent` pass unchanged.

## §7. New-test design (FakeSlowRecorder + force-cleanup assertion)

- **`_FakeProcess`**: `.is_alive()→True`, `.terminate()` sets `.terminated=True`.
- **`FakeSlowRecorder(_StubRecorder)`**: adds `transcript_process=_FakeProcess()`, `reader_process=_FakeProcess()`, `is_shut_down=False`, `realtime_transcription_model=<non-None sentinel>`; overrides `shutdown()` to block forever (`threading.Event().wait()` — no increment; the bounded thread is `daemon=True` so it dies with the test process).
- **Test** calls `d._bounded_shutdown(timeout=0.3)` directly (NOT `d.shutdown()` — the default 10s would make the suite slow), asserts: returns in `< 2.0s`; `transcript_process.terminated` + `reader_process.terminated`; `is_shut_down is True`; `realtime_transcription_model is None`.
- **Delegation proof** (proves `shutdown()` actually routes through `_bounded_shutdown`, not a leftover direct call): spy on `d._bounded_shutdown` → `d.shutdown()` → assert spy called with `10.0`. Fast (no threading).
- **None-guard test** (M2 prep): `_make_daemon(); d._recorder = None; d.shutdown()` must NOT raise.

## SUMMARY (what S2 can rely on)

1. ✅ Edit site is `shutdown()` L818-844 (body) + docstring L819 + comments L11/L409. `threading`/`time` already imported in daemon.py.
2. ⚠️ **MANDATORY**: `_do_shutdown` must `logger.exception(...)` on failure (NOT silent `pass`) — else `test_shutdown_swallows_recorder_failure` breaks (§5).
3. ✅ Keep idempotency guard + defensive (never re-raise) + add `if self._recorder is None: return`.
4. ✅ Force-cleanup: terminate `transcript_process` + `reader_process` (VRAM holders); set `is_shut_down=True`; `realtime_transcription_model=None`. Daemon threads left alone (die with process).
5. ✅ Default timeout `10.0`; tests call `_bounded_shutdown(timeout=0.3)` directly for speed.
6. ✅ New fakes: `_FakeProcess`, `FakeSlowRecorder`. New tests: force-cleanup-on-timeout, delegation spy, None-guard. Existing shutdown tests stay green.
7. ✅ test_daemon.py already has `threading` (L346) + `time as _time` (L347); additive-section style.
