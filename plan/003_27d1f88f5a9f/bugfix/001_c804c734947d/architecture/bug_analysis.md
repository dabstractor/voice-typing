# Bug Analysis: Root Causes, Code Locations, and Fix Strategies

## Issue 1 (CRITICAL): SIGTERM while armed hangs 15s → SIGKILL + "Failed with result 'timeout'"

### Root Cause (confirmed by code analysis)
The SIGTERM teardown is NOT single-flight: two concurrent teardowns of the recorder-host
child blow the 15s `TimeoutStopSec`.

**Call path on SIGTERM (two threads):**

1. **Signal handler thread** (spawned by `install_shutdown_signal_handlers._handler`):
   - `daemon.request_shutdown()` → sets `_shutdown` Event → calls `_safe_abort()` →
     calls `self._bounded_shutdown()` → calls `self._host.stop(timeout=10.0)`.
   - `request_shutdown()` does **NOT** set `self._shutdown_done = True`.

2. **Main thread** (`main()` finally block, after `run()` exits):
   - `daemon.shutdown()` → checks `_shutdown_done` (False, because step 1 didn't set it) →
     sets `_shutdown_done = True` → calls `self._bounded_shutdown()` → calls
     `self._host.stop(timeout=10.0)` **a SECOND time, concurrently with step 1**.

3. `RecorderHost.stop()` has **NO thread-safety** — two concurrent calls both see
   `self._proc is not None`, both call `self._proc.join(timeout=10)`, both potentially call
   `_terminate_group()` + `join(timeout=2)`. Two parallel ~12s teardowns + `server.stop()`'s
   2s join = 16s > 15s TimeoutStopSec → SIGKILL.

**Why the `voicectl quit` path works:** `ControlServer._dispatch("quit")` calls
`request_shutdown()` then `on_quit=daemon.shutdown()` **sequentially on the SAME socket
worker thread**. By the time `shutdown()` runs, `request_shutdown()`'s `host.stop()` has
already set `self._proc = None`, so the second `host.stop()` is a genuine no-op.

### Fix Strategy (combination of three measures)

**Fix 1A: Make `RecorderHost.stop()` single-flight (thread-safe).**
Add a `threading.Lock` (`_stop_lock`) in `RecorderHost.__init__`. Wrap `stop()` body in
`with self._stop_lock:`. A concurrent second caller blocks on the lock until the first
finishes, then sees `self._proc is None` and returns immediately (no second teardown).
This is the **core fix** — it directly eliminates the "two parallel host.stop() calls" race.

**Fix 1B: Make daemon-level teardown single-flight (request_shutdown sets the guard).**
Have `request_shutdown()` set `self._shutdown_done = True` under `self._lock` after it
launches its teardown. Add a `self._teardown_done` (`threading.Event`) that `request_shutdown()`
sets when its `_bounded_shutdown()` completes. In `shutdown()`, if `_shutdown_done` is
already True, wait on `_teardown_done` (bounded, e.g., 8s) then return — do NOT start a
second `_bounded_shutdown()`. This makes `main()`'s finally-block `shutdown()` a true
belt-and-suspenders no-op on the SIGTERM path.

**Fix 1C: Reduce the teardown timeout budget for headroom.**
Reduce `_bounded_shutdown` default timeout from 10.0s to 5.0s. A single teardown:
`host.stop(timeout=5)` → `proc.join(5)` + `killpg` + `join(2)` ≈ up to 7s.
Plus `server.stop()` join(2) = up to 2s. Total ≤ 9s, comfortable headroom under 15s.
Update `request_shutdown()` to call `_bounded_shutdown(timeout=5.0)`.

### Key Code Locations
- `voice_typing/recorder_host.py`: `RecorderHost.__init__` (~line 78), `RecorderHost.stop()`
  (~line 195). Add `_stop_lock`; wrap stop() body.
- `voice_typing/daemon.py`: `request_shutdown()` (~line 1140), `_bounded_shutdown()`
  (~line 1310), `shutdown()` (~line 1330). Add `_teardown_done` Event; set `_shutdown_done`
  in `request_shutdown`; reduce timeout.
- `systemd/voice-typing.service`: TimeoutStopSec=15 (unchanged, but now has headroom).

### Test Gap
No existing test exercises the concurrent `request_shutdown()` + `shutdown()` path (the SIGTERM
path). The existing `test_request_shutdown_*` tests call `request_shutdown()` on the test thread,
and `test_shutdown_*` tests call `shutdown()` on the test thread — never both concurrently with
a real _FakeHost. Need a new test that spawns `request_shutdown()` on one thread and `shutdown()`
on another, asserting only ONE `host.stop()` call and bounded completion.

---

## Issue 2 (MAJOR): phase field stays listening/speaking after stop (never returns to idle)

### Root Cause
`VoiceTypingDaemon._disarm()` (daemon.py ~line 970) clears `_listening` and calls
`self._feedback.set_listening(False)` but **NEVER calls `self._feedback.set_phase("idle")`**.
Phase is only ever advanced by VAD callbacks from the child:
- `on_vad_detect_start` → `set_phase("listening")`
- `on_vad_start` → `set_phase("speaking")`
- `on_vad_stop` → `set_phase("listening")`

There is no callback that resets phase to `"idle"` when the mic is disarmed. So after any
stop/toggle-off/auto-stop, phase stays stuck at the last VAD value (`listening` or `speaking`).

The `recorder_host._dispatch("vad", ...)` relay calls `self._feedback.set_phase(phase)` — this
also does NOT filter by listening state, so a stray late VAD event could re-flip phase even
after disarm.

### Fix Strategy
In `_disarm()`, after `self._feedback.set_listening(False)`, add:
```python
self._feedback.set_phase("idle")
```
This reflects the "loaded / not listening" lifecycle state per PRD §4.2bis.

Optional hardening: Gate the child's `("vad", ...)` relay in `recorder_host._dispatch` or
`daemon._dispatch` to ignore phase events while not listening (prevents stray late VAD events
from re-flipping). The PRD suggests this as a secondary measure if observed in practice.

### Key Code Locations
- `voice_typing/daemon.py`: `_disarm()` (~line 970). Add `set_phase("idle")`.
- `voice_typing/recorder_host.py`: `_dispatch("vad", ...)` (~line 260). Optional gate.

### Test Gap
No existing test asserts phase after disarm. The VAD phase tests (`test_callback_vad_phases`)
only test the forward direction (VAD events → phase). Need a test that arms, triggers a VAD
phase, disarms, and asserts phase returns to `"idle"`.

---

## Issue 3 (MAJOR): No detection/recovery when recorder-host child crashes

### Root Cause
The `run()` loop (daemon.py ~line 730) checks `self._host is None` but **never checks
`self._host.is_alive`**. When the child dies:
1. `self._host` is still the (dead) host object (not None).
2. `_listening` is still True, `_models_loaded` is still True.
3. `host.text()` returns immediately (dead child → `_dead=True` → loop idles).
4. After 30s auto-stop fires, but `_models_loaded` stays True.
5. Next `voicectl start` → `_load_host()` short-circuits on `if self._models_loaded: return True`
   **without checking liveness** → dead host is reused.

### Fix Strategy
**Fix 3A: Liveness check in `run()` loop.**
In the `run()` loop, before checking `_listening`, add:
```python
if self._host is not None and not self._host.is_alive:
    logger.warning("recorder-host child died; transitioning to unloaded")
    self._handle_dead_host()
```
`_handle_dead_host()` (new method): under `_lock`, clears `self._host = None`,
`self._models_loaded = False`, sets `self._feedback.set_phase("unloaded")`,
`self._feedback.set_models_loaded(False)`, sets `self._load_error` (so status surfaces it).
The run() loop then sees `self._host is None` → idles. Next arm → `_load_host()` re-spawns.

**Fix 3B: Liveness check in `_load_host()`.**
In `_load_host()`, change the early-return guard from:
```python
if self._models_loaded:
    return True
```
to:
```python
if self._models_loaded and self._host is not None and self._host.is_alive:
    return True
```
So a dead host with `_models_loaded=True` does NOT short-circuit — it proceeds to spawn fresh.

**Fix 3C: Clear `_listening` on dead-host detection.**
If the child dies WHILE listening, `_handle_dead_host()` must also clear `_listening` and
call `set_listening(False)` so the status is consistent (not "listening: on" with a dead child).

### Key Code Locations
- `voice_typing/daemon.py`: `run()` (~line 730), `_load_host()` (~line 650). Add liveness checks.
- New method `_handle_dead_host()` on `VoiceTypingDaemon`.
- `voice_typing/recorder_host.py`: `is_alive` property (~line 135) already exists and works
  (`self._proc is not None and self._proc.is_alive() and not self._dead`).

### Test Gap
No existing test injects a dead host (is_alive=False) into a running daemon. The `_FakeHost`
has an `is_alive` property and a `_alive` flag that can be flipped. Need tests:
1. Dead host detected in run() loop → phase transitions to unloaded, _models_loaded=False.
2. `_load_host()` re-spawns after a dead host (not short-circuited by stale _models_loaded).
3. Status reports correctly after child death (listening: off, models_loaded: false).

---

## Issue 4 (MINOR): Config numeric fields accept wrong types silently

### Root Cause
`VoiceTypingConfig.from_toml()` (config.py ~line 178) passes TOML values directly to dataclass
constructors without type validation:
```python
def _overlay(section_cls, table_name):
    section = data.get(table_name, {})
    return section_cls(**section)  # no type checking!
```
Python dataclasses do NOT enforce type annotations at runtime. So `auto_stop_idle_seconds = "thirty"`
loads as a string without error. At runtime, `time.monotonic() - ts < "thirty"` raises TypeError,
which `_idle_watchdog` swallows → auto-stop silently breaks.

### Fix Strategy
Add lightweight type coercion/validation in `from_toml._overlay()`. Two approaches:

**Approach A (coercion):** For known numeric fields, attempt `float(value)`:
```python
_NUMERIC_FIELDS = {"auto_stop_idle_seconds", "auto_unload_idle_seconds",
                    "post_speech_silence_duration", "realtime_processing_pause",
                    "notify_ms"}
def _overlay(section_cls, table_name):
    section = data.get(table_name, {})
    coerced = {}
    for key, val in section.items():
        if key in _NUMERIC_FIELDS and isinstance(val, str):
            try:
                coerced[key] = float(val)
            except ValueError:
                raise TypeError(f"[{table_name}] {key} expects a number, got {val!r}")
        else:
            coerced[key] = val
    return section_cls(**coerced)
```

**Approach B (`__post_init__` validation):** Add `__post_init__` to each dataclass that checks
types with `isinstance`. More robust but more code.

The PRD suggests `float(section["auto_stop_idle_seconds"])` or `pydantic`/`__post_init__`.
Approach A is lighter weight and mirrors the existing unknown-key rejection pattern (TypeError
at load). A `__post_init__` approach on AsrConfig would be cleaner for catching ALL type mismatches.

**Recommended: Approach B-lite** — Add `__post_init__` to `AsrConfig` (the section with the
numeric runtime-critical fields) that validates float fields with isinstance, raising TypeError
on mismatch. This is more robust than key-name lists (which can drift) and catches the error
at construction time (which is exactly when `from_toml` calls `AsrConfig(**section)`).

### Key Code Locations
- `voice_typing/config.py`: `AsrConfig` (~line 34), `from_toml._overlay()` (~line 178).
- Also consider `OutputConfig.notify_ms` (int field in FeedbackConfig).

### Test Gap
The existing `test_config.py` tests unknown-key rejection (`test_unknown_key_raises`) but does
NOT test wrong-type values. Need a test that `auto_stop_idle_seconds = "thirty"` raises TypeError
at load time.
