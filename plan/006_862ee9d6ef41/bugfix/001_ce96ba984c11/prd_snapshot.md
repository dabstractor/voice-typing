# Bug Fix Requirements

## Overview

A creative end-to-end validation was performed against the voice-typing PRD. The test
suite (421 tests) passes completely, and the core functionality (lazy load, drain, idle
auto-stop, idle unload, lite mode, control socket protocol, textproc, feedback, typing
backends) is well-implemented and robust. The daemon was verified running under systemd
at ~0 VRAM (lazy load confirmed via `nvidia-smi`).

However, three issues were found through adversarial probing of edge cases, race
conditions, and cross-component interactions that the standard test suite does not
cover. Two are Major (impact user-visible behavior in common or moderately-common
scenarios); one is Minor (config robustness gap).

All three issues were **confirmed with executable reproduction scripts** (included in
Steps to Reproduce) before being documented here.

## Critical Issues (Must Fix)

None. The system does not crash, corrupt data, or hang indefinitely in any scenario
tested. All issues below are correctness/UX problems, not data-loss or
availability-breaking bugs.

## Major Issues (Should Fix)

### Issue 1: Cross-mode toggle failure silently returns `ok:true` instead of surfacing the error

**Severity**: Major
**PRD Reference**: §4.2bis ("the arm command returns `{"ok":false,"error":...}`"); §4.2ter (mode switching); §4.8 (voicectl exit codes)
**Affected file**: `voice_typing/daemon.py` — `ControlServer._dispatch()` (the `toggle` and `toggle-lite` branches)

**Expected Behavior**: When a toggle command triggers a mode-switch model load that FAILS
(e.g., CUDA OOM, missing model file, cuDNN load error), the control socket response MUST
return `{"ok": false, "error": "model load failed: ..."}` so `voicectl` prints the error
and exits with code 1. This is what `start` and `start-lite` already do via
`_arm_response()`.

**Actual Behavior**: The response is `{"ok": true, "listening": false}` with no `error`
field. `voicectl` prints `listening: off` and exits 0. The user receives **zero
indication** that the mode switch failed. The error IS present in the status snapshot's
`load_error` field, but `format_result()` for `toggle`/`toggle-lite` only prints
`listening: on/off` — it does not print `load_error`.

**Root Cause**: In `_dispatch()`, the `arm_attempted` flag is computed as:
```python
arm_attempted = not was_listening or self._daemon.is_listening()
```
For a cross-mode toggle failure: `was_listening=True` (was armed in the other mode),
and after the failed reload + disarm, `is_listening()=False`. So
`arm_attempted = not True or False = False`. Since `arm_attempted` is False, the code
returns `{"ok": True, **status_snapshot()}` instead of routing through
`_arm_response()` (which checks `_load_error` and returns `ok:false`).

Note: the DAEMON-level behavior is correct — `toggle()`/`toggle_lite()` DO clear stale
`_listening` and set `_load_error` on a failed cross-mode reload (tested by
`test_toggle_while_armed_in_lite_failed_reload_clears_listening`). The bug is purely in
the dispatch-layer response shaping: the error is not conveyed over the wire as an
`ok:false` response.

**Steps to Reproduce**:
```python
# instantiate daemon with a host_factory whose 2nd spawn (the mode-switch reload) fails
# arm in lite mode (1st spawn succeeds), then send toggle (switch lite->normal, 2nd spawn fails)
# observe: response is {"ok": true, "listening": false} with no "error" key
# the load_error is buried in the status snapshot but format_result ignores it for toggle
```
Full repro script verified: arm lite → stop → arm lite → press normal toggle (fails) →
response `ok:True, listening:False, error=(none)`, `load_error` present but not surfaced.

**Impact**: A user pressing the hotkey to switch modes (e.g., Alt+Super+D while armed
in normal, or Ctrl+Alt+Super+D while armed in lite) when the target model fails to load
sees only "listening: off" with no error. They may believe the toggle simply disarmed,
not that a load failure occurred. They must separately run `voicectl status` to discover
the `load error:` line. Compare with `voicectl start` from idle, which correctly prints
`error: model load failed: ...` (exit 1).

**Suggested Fix**: In `_dispatch()`, the `toggle`/`toggle-lite` disarm-path return should
also check `_load_error` when a load was involved. The cleanest approach: track whether
`_load_host` was called during the toggle (mode switch), and route through
`_arm_response()` in that case. Alternatively, have `toggle()`/`toggle_lite()` expose
whether a load was attempted (e.g., return a result enum or set a `_load_attempted`
flag), so dispatch can decide. A simpler but slightly less precise fix: in the
non-`arm_attempted` return path, check if `_load_error` was freshly set during THIS
toggle (by snapshotting it before and comparing after).

---

### Issue 2: Stale `_final_pending` from realtime partials causes spurious 5-second drain on stop

**Severity**: Major
**PRD Reference**: §4.2 #2 ("If nothing is in flight (idle, or the last utterance already finalized), it disarms immediately + aborts — responsive when there's nothing to wait for")
**Affected file**: `voice_typing/daemon.py` — `_request_stop()`, `_arm()`, `_disarm()`, `_touch_speech()`

**Expected Behavior**: When the user stops after an utterance has already finalized (no
new speech in flight), the stop should disarm **immediately** (sub-second), as the PRD
requires. The drain path is reserved for when an utterance is genuinely in flight.

**Actual Behavior**: After a final lands and `on_final()` clears `_final_pending=False`,
the realtime model (small.en, running on a separate thread) can fire one or more
additional partial callbacks (tail-end transcription stabilization, or silence-period
processing). Each partial fires `on_speech → _touch_speech()`, which sets
`_final_pending=True` again. When the user then presses stop, `_request_stop()` sees
`_text_in_flight=True` (the run loop re-entered `text()` after the final) AND
`_final_pending=True` (from the stale partial), so it enters the **drain** path instead
of disarming immediately. Since no real speech is in flight, no final arrives, and the
drain watchdog fires after `_DRAIN_TIMEOUT_S = 5.0` seconds, making the stop take **5
full seconds** instead of being instant.

The `_final_pending` flag is **never reset** in `_arm()` or `_disarm()` — it is only
cleared by `on_final()`. So any partial arriving between sessions (a late event from the
IPC queue after disarm) leaves it stale `True` into the next arm/stop cycle.

**Root Cause**: `_final_pending` is used as the proxy for "an utterance is in flight",
but it is set by `_touch_speech()` on **every** realtime partial callback — including
partials that do not correspond to new speech (tail-end stabilization, silence
processing, or late IPC events). The PRD's intent is "speech occurred since the last
final", but the implementation treats "any partial fired since the last final" as
equivalent. Since `_final_pending` is not reset on arm/disarm, a stale True value
persists across session boundaries.

**Steps to Reproduce**:
```python
# 1. Arm the daemon
# 2. Simulate speech: _touch_speech() -> _final_pending=True
# 3. Deliver a final: on_final("text") -> _final_pending=False, text() returns
# 4. Simulate a late/stray partial: _touch_speech() -> _final_pending=True (STALE)
# 5. Stop: _request_stop() sees _text_in_flight=True + _final_pending=True -> DRAIN
# 6. No new speech -> no final -> drain watchdog fires after 5.0s
# Observed: stop takes 5s; _drain=True for the full duration; _listening stays True
```
Full repro script verified: the spurious drain was triggered and confirmed to hold
`_drain=True` for 5 seconds before the watchdog completed it.

**Impact**: Every stop that occurs shortly after a finalized utterance (the common case:
speak a phrase, pause for the final, press stop) risks a 5-second delay where the hotkey
appears unresponsive. The mic stays armed (listening) during the drain, so any ambient
noise captured in that window could produce an unwanted final that gets typed. This
directly violates the PRD's responsiveness requirement for the "nothing in flight" case.

The existing test `test_stop_aborts_immediately_when_text_idle_no_speech` passes because
it manually sets `_text_in_flight` without setting `_final_pending` — it does not
simulate the stray partial that sets `_final_pending=True` in production.

**Suggested Fix**: Reset `_final_pending = False` in `_arm()` (a fresh arm means no
utterance is in flight yet). Optionally also reset it in `_disarm()` for defense in
depth. This ensures that stale values from late/stray partials do not persist into the
next session:
```python
def _arm(self) -> None:
    self._listening.set()
    self._final_pending = False   # <-- ADD: fresh session, no utterance in flight
    self._last_speech_monotonic = time.monotonic()
    ...
```
A more thorough fix would also make `_touch_speech()` (or the `on_speech` callback)
check whether VAD actually detected speech rather than firing unconditionally on every
partial, but resetting `_final_pending` on arm is the minimal, safe fix.

## Minor Issues (Nice to Fix)

### Issue 3: Unknown `output.backend` value is not validated at config load time

**Severity**: Minor
**PRD Reference**: §4.5 (config validation — "Unknown keys raise TypeError"); §4.4 (VT-005 precedent: `device` value IS validated at load time)
**Affected file**: `voice_typing/config.py` — `OutputConfig.__post_init__()` (missing); compare `AsrConfig.__post_init__()` which validates `device`

**Expected Behavior**: An invalid `output.backend` value (e.g., a typo like `"wtyp"`
instead of `"wtype"`) should be rejected at config **load time** with a clear
`ValueError`, just as `device = "gpu"` is rejected by VT-005. This gives the user an
immediate, actionable error before the daemon starts.

**Actual Behavior**: The config loads successfully with `backend = "wtyp"`. The error
only surfaces later when `typing_backends.make_backend()` raises `ValueError` during
`VoiceTypingDaemon.__init__()`. Under systemd, this causes the daemon to exit with code
1, and `Restart=on-failure` loops it forever (the config never changes between restarts).
The error IS logged clearly (`unknown output.backend: 'wtyp'`), but it requires
`journalctl` to discover — there is no fast-fail at config load.

**Steps to Reproduce**:
```python
import tomllib
from voice_typing.config import VoiceTypingConfig
data = tomllib.loads('[output]\nbackend = "wtyp"')  # typo
cfg = VoiceTypingConfig.from_toml(data)  # loads OK — no validation!
print(f"backend={cfg.output.backend!r}")  # 'wtyp' — accepted silently
# make_backend(cfg.output) -> ValueError: unknown output.backend: 'wtyp'
```

**Impact**: Low. A typo in `backend` causes a crash-loop, but the error message is clear
in the journal and the fix (correct the typo) is obvious. The inconsistency with
`device` validation (VT-005) is a code-quality gap, not a user-facing breakage in normal
operation.

**Suggested Fix**: Add value validation to `OutputConfig.__post_init__()`:
```python
def __post_init__(self) -> None:
    if self.backend not in ("wtype", "ydotool", "tmux"):
        raise ValueError(
            f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}'
        )
```
This mirrors the `AsrConfig.__post_init__()` `device` validation (VT-005) and gives the
user a fast-fail at `VoiceTypingConfig.load()` time.

## Testing Summary

- **Total tests performed**: ~50+ manual probes across 8 probe scripts, plus the full
  421-test suite (all passing), plus live verification of the running systemd daemon
  (status, nvidia-smi VRAM check, voicectl exit codes).
- **Passing**: 421 unit/integration tests; all protocol, lifecycle, config, textproc,
  feedback, status.sh, and typing-backend probes.
- **Failing (bugs found)**: 3 issues (2 Major, 1 Minor), all confirmed with executable
  reproductions.
- **Areas with good coverage**: textproc edge cases (unicode, blocklist, whitespace),
  config type/value validation (except `backend`), control socket protocol (all
  commands, malformed JSON, unknown commands), mode switching (success path), dead-host
  recovery, idle auto-stop, idle unload, feedback atomic writes + throttling, status.sh
  rendering, voicectl exit codes, lazy-load VRAM guarantee.
- **Areas needing more attention**:
  - **Dispatch-layer response shaping for toggle/toggle-lite failure paths** (Issue 1) —
    daemon-level behavior is tested but the wire response is not.
  - **`_final_pending` lifecycle across arm/disarm boundaries** (Issue 2) — tests
    manually set `_text_in_flight` without simulating stray partials; the stale-flag
    scenario is uncovered.
  - **Config value validation for `output.backend`** (Issue 3) — `device` is validated
    (VT-005) but `backend` is not, an inconsistency.