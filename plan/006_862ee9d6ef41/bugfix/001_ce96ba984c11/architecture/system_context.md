# Architecture: Voice-Typing Bug Fix (3 Issues)

## System Overview

The voice-typing project is a CUDA faster-whisper daemon with a control socket, live audio capture,
and typing backends. The daemon runs as a systemd user service, lazy-loads ASR models on first arm,
and communicates with `voicectl` over an AF_UNIX control socket using a one-line-JSON-request /
one-line-JSON-response protocol.

**Key files touched by this bug fix:**
- `voice_typing/daemon.py` (2247 lines) — Issues 1 & 2
- `voice_typing/config.py` (308 lines) — Issue 3
- `voice_typing/ctl.py` (219 lines) — Issue 1 (client-side rendering, NO change needed)
- `voice_typing/typing_backends.py` (164 lines) — Issue 3 (existing runtime validation, unchanged)

**Test files:**
- `tests/test_daemon.py` (~3900 lines) — Issues 1 & 2 tests
- `tests/test_control_socket.py` — Issue 1 dispatch-layer tests
- `tests/test_config.py` — Issue 3 config validation tests
- `tests/test_voicectl.py` — Issue 1 client-side tests

---

## Issue 1: Cross-mode toggle failure silently returns `ok:true`

### Location
`voice_typing/daemon.py` — `ControlServer._dispatch()` lines ~1918–1951 (the `toggle` and
`toggle-lite` branches).

### Root Cause (confirmed)
The `arm_attempted` flag is computed as:
```python
arm_attempted = not was_listening or self._daemon.is_listening()
```
For a cross-mode toggle failure:
- `was_listening = True` (was armed in the OTHER mode)
- After `toggle()`: `_load_host()` fails → `_disarm()` is called → `is_listening() = False`
- `arm_attempted = not True or False = False or False = False`

Since `arm_attempted` is False, the response goes to `{"ok": True, **status_snapshot()}` instead of
routing through `_arm_response()` (which checks `_load_error` and returns `ok:false`).

### `_arm_response()` is correct
```python
def _arm_response(self) -> dict:
    load_error = getattr(self._daemon, "_load_error", None)
    if load_error and not self._daemon.is_listening():
        return {"ok": False, "error": f"model load failed: {load_error}"}
    return {"ok": True, **self._daemon.status_snapshot()}
```
If routed here, it correctly returns `ok:false` for the cross-mode failure case (load_error is set,
is_listening is False).

### `_load_error` Lifecycle (confirmed)
- Set to `None` at the START of `_load_host()` (line 726)
- Set to `"recorder host spawn failed"` on spawn failure (line 782)
- Set to `"recorder-host child died unexpectedly"` by `_handle_dead_host()` (line 915)
- Set to `None` on successful load (line 767)
- Set to `None` after ordinary idle unload (line 1269)
- Reset to `None` on next load attempt

**Key invariant**: `_load_host()` always resets `_load_error = None` before attempting, so a freshly-
set value is always from THIS attempt. This means snapshotting `_load_error` before/after `toggle()`
reliably detects a fresh load failure.

### Daemon-level behavior is CORRECT
`toggle()` / `toggle_lite()` correctly clear stale `_listening` and set `_load_error` on a failed
cross-mode reload (tested by `test_toggle_while_armed_in_lite_failed_reload_clears_listening` at
test_daemon.py:3877). The bug is PURELY in the dispatch-layer response shaping.

### Client-side (`ctl.py`) needs NO change
`format_result()` already handles `ok:false`:
```python
if response.get("ok") is not True:
    return f"error: {response.get('error', 'unknown error')}", 1
```
Once `_dispatch()` returns `ok:false`, `voicectl` prints the error and exits 1. No `ctl.py` change.

### Recommended Fix (PRD approach #3 — least invasive, most precise)
In `_dispatch()`, snapshot `_load_error` before `toggle()`, and if it was freshly set afterward, route
through `_arm_response()`:
```python
if cmd == "toggle":
    was_listening = self._daemon.is_listening()
    load_error_before = getattr(self._daemon, "_load_error", None)
    self._daemon.toggle()
    arm_attempted = not was_listening or self._daemon.is_listening()
    if arm_attempted:
        return self._arm_response()
    # Cross-mode toggle failure: was_listening=True → load attempted → failed → disarmed.
    # _load_error was freshly set by the failed _load_host inside toggle().
    if load_error_before is None and getattr(self._daemon, "_load_error", None):
        return self._arm_response()
    return {"ok": True, **self._daemon.status_snapshot()}
```
Identical change for the `toggle-lite` branch. The `load_error_before is None` check ensures we only
catch a FRESH error, not a stale one from a prior failed session.

### Test Strategy
Combine the failing-spawn factory pattern (`_failing_second_spawn_factory` at test_daemon.py:3843)
with the dispatch-test pattern (test_control_socket.py `_disp()` / direct `ControlServer._dispatch()`):

1. `_make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))` → real daemon
2. `d.start_lite()` → arms in lite (1st spawn succeeds)
3. `srv = daemon.ControlServer(d)`
4. `resp = srv._dispatch(json.dumps({"cmd": "toggle"}))` → cross-mode switch fails (2nd spawn fails)
5. Assert `resp["ok"] is False` and `"model load failed" in resp["error"]`

Mirror test for `toggle-lite` (arm in normal first, toggle-lite fails).

---

## Issue 2: Stale `_final_pending` causes spurious 5-second drain

### Location
`voice_typing/daemon.py` — `_arm()` (line 1006), `_disarm()` (line 1021), `_touch_speech()` (line 1048),
`_request_stop()` (line 1072).

### Root Cause (confirmed)
`_final_pending` is set to `True` by `_touch_speech()` on EVERY realtime partial callback (including
tail-end stabilization / silence processing / late IPC events). It is only cleared by `on_final()`
(line 973). It is NEVER reset in `_arm()` or `_disarm()`.

After a final lands and `on_final()` clears `_final_pending=False`, a late partial fires
`_touch_speech()` → `_final_pending=True` again. When the user then presses stop, `_request_stop()`
sees `_text_in_flight.is_set() AND _final_pending` → enters the drain path → no final arrives →
drain watchdog fires after `_DRAIN_TIMEOUT_S = 5.0` seconds.

### `_request_stop()` decision logic (line 1084)
```python
if self._host is not None and self._text_in_flight.is_set() and self._final_pending:
    self._begin_drain()   # DRAIN PATH (5s timeout)
else:
    with self._lock:
        self._disarm()    # IMMEDIATE PATH
    if self._host is not None:
        self._safe_abort()
```

### Existing test gap
`test_stop_aborts_immediately_when_text_idle_no_speech` (test_daemon.py:726) sets `_text_in_flight`
but does NOT call `_touch_speech()`, so `_final_pending` stays False. It never simulates the stray
partial that sets `_final_pending=True` in production.

### Recommended Fix
Add `self._final_pending = False` to `_arm()` (a fresh arm = no utterance in flight yet):
```python
def _arm(self) -> None:
    self._listening.set()
    self._final_pending = False   # fresh session: no utterance in flight
    self._last_speech_monotonic = time.monotonic()
    ...
```
Optionally also add to `_disarm()` for defense in depth (resets between sessions even without a
fresh arm).

### Test Strategy
Mirror `test_stop_aborts_immediately_when_text_idle_no_speech` but with the stale partial:
1. `d, fb, rec, be = _make_daemon()`
2. `d.start()` → arm
3. `d._touch_speech()` → `_final_pending=True`
4. `d.on_final("hello")` → `_final_pending=False`, text typed
5. `d._touch_speech()` → stale partial → `_final_pending=True` (WITHOUT fix: stays True; WITH fix
   in `_arm()`: this simulates within-session, so it's True here, but the arm reset prevents
   cross-session staleness)

Actually, the most direct test for the `_arm()` fix:
1. Arm → `_touch_speech()` → `on_final()` (clears it) → stray `_touch_speech()` (sets it True) →
   `_disarm()` (stop completes) → RE-arm → assert `_final_pending is False` (the stale value from
   the previous session's stray partial was cleared by `_arm()`)

AND/OR test the end-to-end spurious drain: arm → touch_speech → on_final → stray touch_speech →
stop → assert `_drain is False` + `rec.aborts == 1` (immediate disarm, not 5s drain).

**IMPORTANT**: The `_arm()` reset alone fixes the CROSS-SESSION staleness (arm clears stale value
before the next stop). For the WITHIN-SESSION case (stray partial after final but before stop in
the same session), the `_arm()` reset doesn't help — but the PRD's suggested fix is minimal: "reset
`_final_pending` on arm is the minimal, safe fix." The within-session case is a deeper issue
(VAD-vs-partial distinction) that the PRD marks as "a more thorough fix." We implement the minimal
fix (reset on arm/disarm) as specified.

---

## Issue 3: Unknown `output.backend` not validated at config load

### Location
`voice_typing/config.py` — `OutputConfig` dataclass (line 119–125), missing `__post_init__()`.

### Root Cause (confirmed)
`OutputConfig` has NO `__post_init__()`. An invalid backend (e.g., `"wtyp"` typo) loads silently.
The error only surfaces later in `typing_backends.make_backend()` (line 142) during daemon init,
causing a crash-loop under systemd.

### Existing Validation Precedent
`AsrConfig.__post_init__()` (config.py:72–118) validates `device` value (VT-005):
```python
if self.device not in ("cuda", "cpu"):
    raise ValueError(f'[asr] device must be "cuda" or "cpu", got {self.device!r}')
```

### `make_backend()` already validates at runtime (typing_backends.py:142)
```python
def make_backend(cfg: OutputConfig) -> TypingBackend:
    backend = cfg.backend
    if backend == "wtype":  return _WtypeWithFallback()
    if backend == "ydotool": return YdotoolBackend()
    if backend == "tmux":   return TmuxBackend(cfg)
    raise ValueError(f"unknown output.backend: {backend!r}")
```
The fix ADDS load-time validation; the runtime check stays as a defensive second gate.

### Recommended Fix
```python
@dataclass
class OutputConfig:
    backend: str = "wtype"
    tmux_target: str = ""
    append_space: bool = True

    def __post_init__(self) -> None:
        if self.backend not in ("wtype", "ydotool", "tmux"):
            raise ValueError(
                f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}'
            )
```

### Test Strategy
Mirror VT-005 tests (test_config.py:172–183):
- Invalid values: `"wtyp"`, `"xterm"`, `"WTYPE"`, `""`, `"auto"` → `ValueError, match="backend"`
- Valid values: `"wtype"`, `"ydotool"`, `"tmux"` → load OK, round-trip

---

## Cross-Cutting: Dependencies & Independence

| Issue | File | Method(s) | Depends on |
|-------|------|-----------|------------|
| 1 | daemon.py | `ControlServer._dispatch()` | None |
| 2 | daemon.py | `_arm()`, `_disarm()` | None |
| 3 | config.py | `OutputConfig.__post_init__()` | None |

All three issues are **independent** — they touch different methods/files with no overlap. They can
be implemented in parallel or in any order.

Issues 1 & 2 both modify `daemon.py` but in non-overlapping regions (dispatch layer ~line 1918 vs.
arm/disarm ~line 1006). No merge conflict risk.

## Documentation Surface

- **README.md** already documents `output.backend` valid values (`"wtype"`, `"ydotool"`, `"tmux"`)
  at line ~167. The content is already accurate — no change needed for Issue 3's content.
- Issues 1 & 2 are internal correctness fixes with no user-facing config/API surface change.
- The final documentation task verifies README consistency and is a no-op sweep if no drift exists.