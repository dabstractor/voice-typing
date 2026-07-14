# Test Infrastructure & Patterns

## Test Framework
- pytest with `monkeypatch`, `caplog`, `tmp_path` fixtures.
- All tests are CUDA-free, GPU-free, no real subprocess spawn for the recorder.
- ~340 tests, all green, fast suite.

## Key Test Stubs (tests/test_daemon.py)

### _StubRecorder (line ~368)
Legacy stub with: `text(on_transcription_finished)`, `set_microphone(on)`, `abort()`,
`shutdown()`. Tracks calls: `text_calls`, `mic`, `aborts`, `shutdowns`. Returns "" from text()
(loop spins fast). Wrapped in `_LegacyRecorderHostAdapter` when injected via `recorder=`.

### _FakeHost (line ~432)
Mirrors real RecorderHost surface: `spawn()`, `set_microphone()`, `abort()`, `text()`,
`stop(timeout)`, `device` property, `is_alive` property, `pid` property.
Has configurable `spawn_result` and `_alive` flag. Wraps a `_StubRecorder` for assertions.
Used when injected via `host_factory=`.

### _FakeSlowRecorder (line ~1436)
Extends _StubRecorder. `shutdown()` blocks forever (simulates RealtimeSTT ~90s wedge).
Has `transcript_process`, `reader_process` (FakeProcess), `is_shut_down`, 
`realtime_transcription_model` attrs for force-cleanup testing.

### _ControllableShutdownRecorder (line ~2362)
Extends _StubRecorder. Shutdown timing is controllable (for race-condition tests).

### _FakeBackend (line ~395)
Records `type_text` calls; optionally raises on specific text.

### _DaemonFakeFeedback
Tracks set_listening/set_phase/set_models_loaded calls for assertions.

### _FakeFeedback (tests/test_recorder_host.py)
Tracks set_phase and update_partial calls.

### _make_daemon() (line ~512)
```python
def _make_daemon(*, recorder=None, recorder_host=None, host_factory=None, backend=None, cfg=None):
    # Returns (daemon, feedback, recorder, backend)
    # Uses _StubRecorder by default, _DaemonFakeFeedback, _FakeBackend, _ok_probe
```

### _make_daemon_with_feedback() (line ~1265)
Uses real Feedback + tmp_path state file. For tests that need real state.json behavior.

### _wait_for() (line ~410)
Poll-based assertion helper: `_wait_for(predicate, timeout=2.0, interval=0.01)`.

### _cuda_resolve() 
Monkeypatches `daemon.cuda_check.resolve_device_and_models` to return CUDA_DEFAULTS (avoids
real CUDA probing in tests).

## Run-Loop Integration Test Pattern
```python
_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
d, fb, rec, be = _make_daemon()
t = threading.Thread(target=d.run, daemon=True)
t.start()
try:
    _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)  # run() booted
    # ... test assertions ...
finally:
    d.request_shutdown()
assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
t.join(timeout=2.0)
```

## Existing Test Coverage Gaps (from PRD)

| Gap | Current Coverage | What's Missing |
|-----|-----------------|----------------|
| SIGTERM concurrent teardown | `test_request_shutdown_*` (single-threaded) + `test_shutdown_*` (single-threaded) | No test with CONCURRENT request_shutdown + shutdown (the SIGTERM race) |
| Phase after disarm | `test_callback_vad_phases` (forward only) | No test asserting phase returns to "idle" after _disarm() |
| Child crash recovery | None | No test with is_alive=False host injection |
| Config type validation | `test_unknown_key_raises` (unknown keys only) | No test for wrong-typed numeric values |
| Real armed SIGTERM | None (only voicectl quit path tested) | No integration test with live SIGTERM + armed daemon |

## Test Files
- `tests/test_daemon.py` (119KB, ~2700 lines) — main daemon tests
- `tests/test_recorder_host.py` (~12KB) — RecorderHost IPC/dispatch tests
- `tests/test_config.py` (~11KB) — config loader tests
- `tests/test_feedback.py` (~20KB) — feedback/state-file tests
- `tests/test_control_socket.py` (~8KB) — control socket protocol tests
- `tests/test_voicectl.py` (~16KB) — voicectl CLI tests
- `tests/ACCEPTANCE.md` — acceptance criteria document
- `tests/test_idle_and_gpu.sh` — L3/L4 integration test (shell script, live daemon)
