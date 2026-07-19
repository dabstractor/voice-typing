# Scout: Test Patterns for Bugfix Issues 1, 2, 3

Research of existing test patterns across `tests/test_control_socket.py`,
`tests/test_daemon.py`, `tests/test_config.py`, and `tests/test_config_repo_default.py`,
to plan the three bugfixes documented in `plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/prd_snapshot.md`.

---

## Summary of Findings (read this first)

| Issue | Test file(s) | Status of existing coverage | Key gap |
|-------|-------------|-----------------------------|---------|
| 1 — toggle dispatch response shaping | `test_control_socket.py` (dispatch), `test_daemon.py` (daemon-state) | Daemon-level cross-mode failure IS tested; dispatch-layer wire response is NOT | No test exercises `ControlServer._dispatch()` on a cross-mode toggle failure |
| 2 — `_final_pending` lifecycle | `test_daemon.py` | `test_stop_aborts_immediately_when_text_idle_no_speech` exists but does not simulate stray partials | No test resets `_final_pending` on arm/disarm; the stale-partial path is uncovered |
| 3 — config `backend` validation | `test_config.py`, `test_config_repo_default.py`, `test_typing_backends.py` | `device` (VT-005) is validated; `backend` is NOT — validated only in `make_backend()` at runtime | `OutputConfig` has no `__post_init__` |

---

## Issue 1: Toggle Dispatch Response Shaping

### 1a. How `ControlServer._dispatch()` is tested today

`tests/test_control_socket.py` has **two dispatch-test styles**:

**Style A — direct `_dispatch()` call (no socket, no thread):**
Uses a module-level `_disp()` helper + a `_StubDaemon` (duck-typed, **no** `_load_error` attr):

```python
# test_control_socket.py:106-110
def _disp(msg_obj_or_str):
    return daemon.ControlServer(_StubDaemon())._dispatch(
        msg_obj_or_str if isinstance(msg_obj_or_str, str) else json.dumps(msg_obj_or_str)
    )
```

`_StubDaemon` (`test_control_socket.py:24-49`) is a plain class that records calls and
mutates `_listening`. **Critically it has NO `_load_error` attribute** — so `_arm_response()`'s
`getattr(self._daemon, "_load_error", None)` returns `None`, always taking the `ok:True` path.
This means **no existing dispatch test can exercise the `ok:false` failure response** — the stub
cannot model a failed load.

```python
# test_control_socket.py:24-49  (the _StubDaemon)
class _StubDaemon:
    def __init__(self, *, listening=False, snapshot=None):
        self.calls: list[str] = []
        self._listening = listening
        self._snapshot = snapshot or { ... 9 default keys ... }
    def toggle(self):
        self.calls.append("toggle"); self._listening = not self._listening
    def start(self): ...
    def start_lite(self): ...
    def toggle_lite(self): ...
    def stop(self): ...
    def request_shutdown(self): ...
    def is_listening(self): return self._listening
    def status_snapshot(self):
        s = dict(self._snapshot); s["listening"] = self._listening; return s
```

The toggle dispatch test (`test_control_socket.py:113-116`):
```python
def test_dispatch_toggle():
    r = _disp({"cmd": "toggle"})
    assert r["ok"] is True and r["listening"] is True and "device" in r   # uniform payload
```

**Style B — real AF_UNIX socket round-trip:**
Uses the `server` pytest fixture (`test_control_socket.py:88-94`):
```python
@pytest.fixture
def server(tmp_path):
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    yield srv, path
    srv.stop()
```
Then `_send(path, {...})` opens a real socket, sends JSON, reads one response line.

**The lite dispatch tests** (`test_control_socket.py:129-139`):
```python
def test_dispatch_lite_commands_call_daemon(monkeypatch):
    d = _StubDaemon()
    srv = daemon.ControlServer(d)
    assert srv._dispatch(json.dumps({"cmd": "start-lite"}))["ok"] is True
    assert d.calls == ["start-lite"]
    # ... toggle-lite mirrors
```

### 1b. The dispatch-source under test (the bug)

`voice_typing/daemon.py:1899-1970` — `ControlServer._dispatch()`. The `arm_attempted` flag
is the bug site:

```python
# daemon.py:1901-1918  (_arm_response)
def _arm_response(self) -> dict:
    load_error = getattr(self._daemon, "_load_error", None)
    if load_error and not self._daemon.is_listening():
        return {"ok": False, "error": f"model load failed: {load_error}"}
    return {"ok": True, **self._daemon.status_snapshot()}

# daemon.py:1927-1942  (toggle branch — the bug)
if cmd == "toggle":
    was_listening = self._daemon.is_listening()
    self._daemon.toggle()
    arm_attempted = not was_listening or self._daemon.is_listening()
    if arm_attempted:
        return self._arm_response()
    return {"ok": True, **self._daemon.status_snapshot()}   # <-- cross-mode FAILURE lands here
# toggle-lite branch is identical (daemon.py:1944-1951)
```

**The bug**: for a cross-mode toggle failure, `was_listening=True`, and after the failed reload
the daemon disarms so `is_listening()=False`. Thus `arm_attempted = not True or False = False`,
and the response is `{"ok": True, **status_snapshot()}` (no `error`) instead of routing through
`_arm_response()` which would return `ok:false`.

### 1c. The daemon-level cross-mode failure tests (the models, NOT the wire)

These exist in `tests/test_daemon.py` and test **daemon state**, not the dispatch response:

- **`test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening`**
  — `test_daemon.py:3861-3881`
- **`test_toggle_while_armed_in_lite_failed_reload_clears_listening`**
  — `test_daemon.py:3884-3900`  ← the one named in the task
- **`test_failed_cross_mode_toggle_status_snapshot_is_honest`**
  — `test_daemon.py:3903-3918`

All three use the same pattern:
```python
# test_daemon.py:3884-3900
def test_toggle_while_armed_in_lite_failed_reload_clears_listening():
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
    d.start_lite()                               # arm in lite (first spawn succeeds)
    assert d._mode == "lite" and d.is_listening()
    d.toggle()                                   # cross-mode switch → normal reload FAILS
    assert d.is_listening() is False             # FIXED: disarmed
    assert d._host is None
    assert d._models_loaded is False
    assert d._load_error is not None             # surfaced
    assert d._mode == "lite"                     # never flipped to normal
```

They assert on `d.is_listening()`, `d._host`, `d._models_loaded`, `d._load_error`, `d._mode`.
They do **NOT** call `ControlServer._dispatch()` or assert on the wire response dict.

### 1d. How tests simulate cross-mode toggle failures (host_factory)

The key helper: **`_failing_second_spawn_factory`** (`test_daemon.py:3843-3856`):
```python
def _failing_second_spawn_factory(spawns):
    """host_factory whose FIRST spawn succeeds and whose SECOND spawn fails."""
    def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)
        host.spawn_result = len(spawns) == 0   # first spawn True, rest False
        spawns.append(host)
        return host
    return factory
```

This factory is injected via `_make_lazy_daemon(host_factory=...)`. The `_FakeHost` class
(`test_daemon.py:532-616`) has a `spawn(timeout)` method that returns `self.spawn_result`
and sets `self._alive`. On failure (`spawn_result=False`), `_load_host` tears down the resident
host, sets `_load_error`, and clears `_listening`.

### 1e. GAP for the bugfix (what a new test must do)

There is **no test** that wires a real daemon (with `_load_error`) into `ControlServer._dispatch()`
and asserts the response dict. A new test must:
1. Construct a real `VoiceTypingDaemon` via `_make_lazy_daemon(host_factory=_failing_second_spawn_factory(...))`.
2. Wrap it: `srv = daemon.ControlServer(d)` and call `srv._dispatch(json.dumps({"cmd": "toggle"}))`
   after arming in the opposite mode.
3. Assert the response is `{"ok": False, "error": "model load failed: ..."}` (post-fix), NOT
   `{"ok": True, "listening": False}`.

This is the **union of two existing patterns**: the dispatch test style from
`test_control_socket.py` + the failing-spawn factory from `test_daemon.py`. The dispatch tests in
`test_control_socket.py` cannot be reused directly because `_StubDaemon` has no `_load_error` and no
real `_load_host`/`toggle` logic.

---

## Issue 2: `_final_pending` Lifecycle

### 2a. The target test and its surrounding drain tests

All in `tests/test_daemon.py:684-810`. The block header (`:684-690`):
```
# --- graceful-stop drain: a premature stop lets the FINAL model finish, then disarms ---
# stop()/toggle-off do NOT abort an in-flight utterance ... When speech is pending
# (_final_pending) and the run loop is inside text() (_text_in_flight), _request_stop sets
# _drain; the run loop disarms once text() returns the natural final.
```

The named test (`test_daemon.py:726-734`):
```python
def test_stop_aborts_immediately_when_text_idle_no_speech():
    """stop() while text() is blocked but no speech is pending -> immediate disarm + abort."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._text_in_flight.set()         # loop in text(), idle-waiting for the next utterance
    d.stop()                        # _final_pending False -> immediate path
    assert d.is_listening() is False
    assert d._drain is False
    assert rec.aborts == 1          # aborted (no utterance to finish)
```

**Why it misses the bug**: it sets `d._text_in_flight.set()` but does NOT call
`d._touch_speech()` (which sets `_final_pending=True`). In production, a stray realtime partial
after a final fires `_touch_speech()` → `_final_pending=True`, and then `d.stop()` takes the
drain path (5s) instead of the immediate path. (Documented in the PRD snapshot, Issue 2.)

Other drain tests in the same block:
- **`test_stop_drains_when_utterance_in_flight`** — `:692-701` (the happy drain path)
- **`test_toggle_off_drains_when_utterance_in_flight`** — `:704-712`
- **`test_stop_disarms_immediately_when_idle`** — `:715-721`
- **`test_drain_timeout_aborts_blocked_text`** — `:737-748` (calls `d._drain_timeout()` directly)
- **`test_on_final_clears_final_pending`** — `:750-759`

### 2b. How tests manipulate `_final_pending` / drain state

Tests directly poke daemon internals (no mocking of callbacks):
```python
d._touch_speech()          # sets _final_pending=True + _last_speech_monotonic=now
d._text_in_flight.set()    # simulate the run loop blocked inside text()
d._begin_drain()           # arm the drain + watchdog
d._complete_drain()        # finish the drain (disarm + cancel watchdog)
d._drain_timeout()         # simulate the watchdog firing
d._final_pending           # read/assert directly
d._drain                   # read/assert directly (bool)
```

Assertion pattern: `assert d.is_listening() is False`, `assert d._drain is True/False`,
`assert rec.aborts == N`, `assert be.typed == [...]`.

### 2c. The source under test

`voice_typing/daemon.py`:
- **`_arm()`** — `:1006-1019`. **Does NOT reset `_final_pending`** (the bug).
- **`_disarm()`** — `:1021-1047`. **Does NOT reset `_final_pending`** either.
- **`_touch_speech()`** — `:1048-1062`. Sets `self._final_pending = True` unconditionally on every partial.
- **`_request_stop()`** — `:1072-1085`. The drain decision:
  ```python
  if self._host is not None and self._text_in_flight.is_set() and self._final_pending:
      self._begin_drain()
  else:
      with self._lock:
          self._disarm()
      if self._host is not None:
          self._safe_abort()
  ```
- **`_begin_drain()`** — `:1092-1101`. Arms a `threading.Timer(_DRAIN_TIMEOUT_S, _drain_timeout)`.
- **`_complete_drain()`** — `:1103-1120`. Disarms + cancels timer.
- **`_drain_timeout()`** — `:1122-1136`. Watchdog: aborts the blocked `text()`.
- **`_DRAIN_TIMEOUT_S`** — `daemon.py:138` = `5.0`.

### 2d. The suggested fix + the test pattern for it

PRD snapshot fix: add `self._final_pending = False` in `_arm()` (and optionally `_disarm()`).

A new test should follow the existing drain-block style: use `_make_daemon()`, arm with
`d.start()`, simulate the stale partial with `d._touch_speech()` then clear via `on_final`,
then a second stray `d._touch_speech()`, then assert `d.stop()` disarms immediately
(`d._drain is False`, `rec.aborts == 1`). The **mirror of the existing
`test_stop_aborts_immediately_when_text_idle_no_speech`** but WITH the stale `_final_pending`
set and the fix in `_arm()`.

---

## Issue 3: Config Validation (`output.backend`)

### 3a. The VT-005 `device` validation precedent

`voice_typing/config.py:72-118` — `AsrConfig.__post_init__()`. Three validation tiers:
1. Numeric fields: reject non-int/float + reject bool (int subclass). `TypeError`.
2. String fields (`final_model`, `realtime_model`, `lite_model`, `language`, `device`): reject
   non-str. `TypeError`.
3. **Device VALUE validation (VT-005)**: `if self.device not in ("cuda", "cpu"): raise ValueError(...)`.
   `ValueError` (type is correct, value is not).

The tests (`tests/test_config.py:172-183`):
```python
def test_invalid_device_value_raises():
    """VT-005: a device value outside {cuda, cpu} is rejected at load with a ValueError naming it."""
    for bad in ("gpu", "cud", "CUDA", "cuda ", "auto", ""):
        with pytest.raises(ValueError, match="device"):
            VoiceTypingConfig.from_toml({"asr": {"device": bad}})

def test_valid_device_values_load():
    """VT-005: 'cuda' and 'cpu' are the accepted device values and round-trip through TOML."""
    for good in ("cuda", "cpu"):
        cfg = VoiceTypingConfig.from_toml({"asr": {"device": good}})
        assert cfg.asr.device == good
```

**Pattern**: `ValueError` for invalid enum-value; `TypeError` for wrong type. Tests go through
`VoiceTypingConfig.from_toml({...})` (the load path), loop over bad/good values.

### 3b. How `__post_init__` tests are structured (the general pattern)

`tests/test_config.py:138-183` shows the consistent structure:
1. **Type guard tests** — `with pytest.raises(TypeError, match="<field_name>")`:
   `VoiceTypingConfig.from_toml({"<section>": {"<field>": <wrong-type>}})`.
   Examples: `test_string_for_float_field_raises` (`:143`), `test_bool_for_float_field_raises`
   (`:151`), `test_int_for_string_field_raises` (`:157`).
2. **Value guard tests** — `with pytest.raises(ValueError, match="<field_name>")`:
   Examples: `test_invalid_device_value_raises` (`:172`).
3. **Happy-path round-trip** — `cfg = VoiceTypingConfig.from_toml({...}); assert cfg.x.y == expected`.
   Example: `test_valid_device_values_load` (`:179`).

### 3c. `OutputConfig` has NO `__post_init__` (the gap)

`voice_typing/config.py:119-125`:
```python
@dataclass
class OutputConfig:
    """[output] — typing-output backend selection."""
    backend: str = "wtype"     # "wtype" | "ydotool" | "tmux"
    tmux_target: str = ""      # used only when backend == "tmux"
    append_space: bool = True
```
**No `__post_init__` method at all.** Contrast with `AsrConfig.__post_init__` (`:72`) and
`FeedbackConfig.__post_init__` (`:140`, validates `notify_ms`).

### 3d. Where backend validation currently lives (and is tested)

`voice_typing/typing_backends.py:142-164` — `make_backend()`:
```python
def make_backend(cfg: OutputConfig) -> TypingBackend:
    backend = cfg.backend
    if backend == "wtype":  return _WtypeWithFallback()
    if backend == "ydotool": return YdotoolBackend()
    if backend == "tmux":   return TmuxBackend(cfg)
    raise ValueError(f"unknown output.backend: {backend!r}")
```
Tested in `tests/test_typing_backends.py:236-239`:
```python
def test_make_backend_unknown_raises_value_error():
    with pytest.raises(ValueError, match="bogus"):
        make_backend(OutputConfig(backend="bogus"))
```
This is a **runtime** check (inside `VoiceTypingDaemon.__init__`), NOT a config-load check.
The fix moves/duplicates it into `OutputConfig.__post_init__` so it fails at load time.

### 3e. `test_config_repo_default.py` — drift guard only

`tests/test_config_repo_default.py` has 3 tests, none about `__post_init__` validation:
- `test_repo_config_toml_equals_defaults` (`:16`) — asserts `config.toml == dataclass defaults`.
- `test_repo_config_toml_has_no_extra_keys` (`:27`) — asserts exactly 20 schema keys present.
- `test_repo_config_lite_model_comment_names_correct_keybind` (`:49`) — asserts comment text.

**If the fix adds `__post_init__` to `OutputConfig`, the repo-default tests will still pass** (the
repo `config.toml` uses `backend="wtype"`, a valid value). No changes needed to this file.

### 3f. The fix + test pattern for it

Add to `OutputConfig` (mirroring `AsrConfig.__post_init__` device validation):
```python
def __post_init__(self) -> None:
    if self.backend not in ("wtype", "ydotool", "tmux"):
        raise ValueError(
            f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}'
        )
```
New tests in `tests/test_config.py` (mirroring VT-005):
```python
def test_invalid_backend_value_raises():
    for bad in ("wtyp", "xterm", "WTYPE", "", "auto"):
        with pytest.raises(ValueError, match="backend"):
            VoiceTypingConfig.from_toml({"output": {"backend": bad}})

def test_valid_backend_values_load():
    for good in ("wtype", "ydotool", "tmux"):
        cfg = VoiceTypingConfig.from_toml({"output": {"backend": good}})
        assert cfg.output.backend == good
```

---

## Key Helper Functions Reference (test_daemon.py)

| Helper | Line | Purpose |
|--------|------|---------|
| `_DaemonFakeFeedback` | `:451-461` | Records `finals`, `listening_states` |
| `_StubRecorder` | `:466-486` | In-process recorder stub: `text()` returns `""`, counts `aborts`/`shutdowns`/`mic` |
| `_FakeBackend` | `:493-503` | Records `typed` list; optionally raises on a payload |
| `_ok_probe` | `:506-...` | Hermetic mic probe returning healthy mic (avoids real PyAudio) |
| `_FakeHost` | `:532-616` | Fake RecorderHost: configurable `spawn_result`, `device`, `mode`; proxies to `_StubRecorder` |
| `_fake_host_factory` | `:619-633` | Builds a `_FakeHost` factory with given spawn result |
| `_make_daemon` | `:618-626` | Real `VoiceTypingDaemon` with injected stubs + `_StubRecorder`. Returns `(d, fb, rec, be)` |
| `_make_lazy_daemon` | `:2758-2768` | Real daemon, `recorder=None` (lazy boot: `_host is None`, `_models_loaded False`). Takes `host_factory`. Returns `(d, fb)` |
| `_failing_second_spawn_factory` | `:3843-3856` | Factory: 1st spawn succeeds, 2nd+ fail (cross-mode reload failure) |

## Assertion Style Reference

- **Daemon state**: `assert d.is_listening() is False`, `assert d._host is None`,
  `assert d._models_loaded is False`, `assert d._load_error is not None`, `assert d._mode == "lite"`,
  `assert d._drain is True`, `assert rec.aborts == 1`.
- **Dispatch response**: `assert r["ok"] is True/False`, `assert r["listening"] is True/False`,
  `assert "device" in r`, `assert "error" in r`.
- **Config**: `with pytest.raises(ValueError, match="..."): VoiceTypingConfig.from_toml({...})`.

## Start Here

1. **Issue 1**: Open `tests/test_daemon.py:3843-3918` (the failing-spawn factory + the three
   cross-mode daemon tests) to see the daemon-level pattern, then `tests/test_control_socket.py:106-139`
   for the dispatch-test style. The new test combines both: a real daemon from `_make_lazy_daemon`
   with `_failing_second_spawn_factory`, wrapped in `daemon.ControlServer(d)`, dispatched via
   `_dispatch()`, asserting the response is `ok:false`.

2. **Issue 2**: Open `tests/test_daemon.py:684-759` (the drain test block). The new test is a
   mirror of `test_stop_aborts_immediately_when_text_idle_no_speech` (`:726`) but with a stray
   `d._touch_speech()` after `on_final` clears `_final_pending`, then asserting `d.stop()` disarms
   immediately (no drain).

3. **Issue 3**: Open `tests/test_config.py:164-183` (the VT-005 device-validation tests) to copy
   the pattern. The fix adds `__post_init__` to `OutputConfig` (`voice_typing/config.py:119`).