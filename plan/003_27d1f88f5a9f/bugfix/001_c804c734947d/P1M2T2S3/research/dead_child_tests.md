# Research — committed dead-child tests (P1.M2.T2.S3 / bugfix Issue 3)

This note pins the test seams, the exact construction helpers, the status-snapshot
gotcha, the kill mechanism, the no-breakage facts, and the validated test logic.
The PRP (../PRP.md) references it as the single source of truth.

## 0. Prerequisite state — S1 + S2 are BOTH IN-TREE (verified)

`git status --short` shows `voice_typing/daemon.py` modified; both halves of Issue 3
landed before this test task:
- **S1** (P1.M2.T2.S1): `run()` liveness check at **daemon.py:750** + `_handle_dead_host()`
  at **daemon.py:778**. On `self._host is not None and not self._host.is_alive` it logs a
  pid-bearing WARNING, calls `_handle_dead_host()`, `continue`.
- **S2** (P1.M2.T2.S2): `_load_host()` early-return guard at **daemon.py:654** now reads
  `if self._models_loaded and self._host is not None and self._host.is_alive:`.
- `_handle_dead_host()` body (778-800): under `self._lock` → `_host=None`,
  `_models_loaded=False`, `_listening.clear()`, `feedback.set_phase("unloaded")`,
  `feedback.set_models_loaded(False)`, `feedback.set_listening(False)`,
  `_load_error="recorder-host child died unexpectedly"`, both idle clocks cleared.
- Baseline: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`
  → **345 passed** (verified live). These tests are what S3 commits.

The plan status lists S2 as "Implementing", but the grep + git status prove S2's guard
(654) is ALREADY in the working tree. S3 must assume BOTH S1 + S2 are present (they are).

## 1. The test seams (exact helpers in tests/test_daemon.py)

- **`_make_daemon(*, recorder=None, recorder_host=None, host_factory=None, backend=None, cfg=None)`**
  (line 512) → returns `(d, fb, rec, be)`. Uses `_DaemonFakeFeedback` + `_StubRecorder` +
  `_FakeBackend` + `_ok_probe`. With **`host_factory=factory`** (NO recorder) the daemon boots
  **lazy** (`_host=None`, `_models_loaded=False`) — the run loop idles until `d.start()` loads.
  THIS is the seam the item names ("`_make_daemon()` with `host_factory=`").
- **`_make_lazy_daemon(cfg=None, host_factory=None)`** (line 2498) → `(d, fb)`. Same idea,
  explicit `recorder=None`. Either works; `_make_daemon(host_factory=...)` matches the item verbatim.
- **`_fake_host_factory(spawn_result=True, device=None)`** (line 501) → a `_factory(cfg, feedback,
  latency, on_final, on_partial, on_speech)` returning a fresh `_FakeHost`. Each call builds a NEW
  `_FakeHost` instance (important for the re-spawn assertion).
- **`_FakeHost`** (line 434): mirrors RecorderHost. Relevant surface for these tests:
  - `spawn(timeout=180.0)` → `spawn_calls += 1`; `self._alive = bool(self.spawn_result)`; returns it.
  - `is_alive` property → `self._alive`.
  - `pid` property → `None` (safe under `getattr(self._host, "pid", "?")`).
  - `text(on_final)` → proxies to `_StubRecorder.text()` which returns `""` **immediately** (loop
    spins fast on the listening path — see §6 timing).
  - `_alive` **defaults to `False`** in `__init__` (line 459). ⇒ `_FakeHost` is only "alive" AFTER
    `spawn()` runs. ⇒ You CANNOT inject a `_FakeHost` via `recorder_host=` (pre-built, spawn() never
    called) — the loop would treat it as dead on iteration 1. **`host_factory=` is the ONLY correct
    seam** (so `_load_host()` calls `factory(...)` then `host.spawn()` → `_alive=True`).
- **`_wait_for(predicate, timeout=2.0, interval=0.01)`** (line 417) → polls until truthy / timeout.
  Returns the final predicate() value. Used for all the async (run-loop) assertions.
- **`_cuda_resolve(monkeypatch, mapping)`** (line 69) → monkeypatches `daemon.cuda_check.
  resolve_device_and_models`. NOTE: with `host_factory=` the `_FakeHost.device` dict seeds
  `_resolved_device_cache` directly inside `_load_host()` (daemon.py:680), so `_resolved_device()`
  (1317) returns the cache WITHOUT probing cuda. So `_cuda_resolve` is not strictly required for
  (a)/(b) — but the existing run-loop tests call it defensively (line 845), so we do too (harmless).

## 2. ★ THE STATUS-SNAPSHOT GOTCHA ★ (drives the (a)/(b) vs (c) feedback split)

`daemon.status_snapshot()` (line 1282) builds the payload from **two sources**:
```python
snap = self._feedback.snapshot()                 # <-- needs .snapshot() on the feedback!
return {
    "listening":   self.is_listening(),           # daemon Event — works with ANY feedback
    "phase":       snap.get("phase", "unloaded"), # from feedback.snapshot()
    "models_loaded": snap.get("models_loaded", False), # from feedback.snapshot()
    "load_error":  self._load_error or "",        # daemon attr — works with ANY feedback
    ...
}
```
- `_DaemonFakeFeedback` (used by `_make_daemon`) **has NO `.snapshot()` method** AND its
  `set_models_loaded` is a **no-op stub** (line 45). So a `_make_daemon(host_factory=)` daemon
  CANNOT service `status_snapshot()` — it would `AttributeError`.
- The REAL `Feedback` (voice_typing/feedback.py) HAS `.snapshot()` → `dict(self._state)` with live
  `phase`/`models_loaded`/`listening`/...; its `set_phase`/`set_models_loaded`/`set_listening`
  actually mutate `_state`. `_make_daemon_with_feedback(tmp_path, monkeypatch)` (line 1396) builds a
  real-Feedback daemon + a tmp_path state.json.

**Consequence (the design decision):**
- Tests **(a)** detection + **(b)** recovery assert on **daemon attrs** (`d._host`,
  `d._models_loaded`, `d.is_listening()`, `d._load_error`) + `_DaemonFakeFeedback` lists
  (`fb.phases[-1]`, `fb.listening_states[-1]`). → Use **`_make_daemon(host_factory=factory)`**
  (faithful to the item INPUT; `_DaemonFakeFeedback` records phases/listening_states).
- Test **(c)** status-correctness asserts on **`d.status_snapshot()`** → needs real Feedback.
  → Use a **real-Feedback + `host_factory=`** daemon (a host_factory variant of
  `_make_daemon_with_feedback`). See §3 for the construction.

(This mirrors the S1 research note's caveat: "S3's committed tests assert models_loaded via the
REAL Feedback / state.json, not the stub." `status_snapshot()["models_loaded"]` reads exactly that
real Feedback field, so (c) MUST use real Feedback.)

## 3. The two constructions (verified against in-tree helpers)

### 3.1 Tests (a) + (b): `_make_daemon(host_factory=factory)` + `_DaemonFakeFeedback`
```python
def test_...(monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)   # defensive (line 845 precedent)
    factory = _fake_host_factory(spawn_result=True)
    d, fb, _rec, _be = _make_daemon(host_factory=factory)
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)  # run() booted
        d.start()                                  # _load_host spawns _FakeHost (_alive=True) + _arm
        _wait_for(lambda: d._models_loaded, timeout=2.0)                # loaded + armed
        assert d.is_listening() and d._host is not None
        # ... kill + assert ...
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)
```

### 3.2 Test (c): real Feedback + `host_factory=` (status_snapshot needs .snapshot())
Mirror `_make_daemon_with_feedback` (1396) but pass `host_factory=` (not `recorder=`):
```python
def test_status_reports_unloaded_after_child_death(tmp_path, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb = Feedback(cfg.feedback)
    factory = _fake_host_factory(spawn_result=True)
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=None, host_factory=factory,
                                 backend=_FakeBackend(), mic_prober=_ok_probe)
    # run() in a thread ... arm ... kill ... wait for d._host is None ...
    snap = d.status_snapshot()
    assert snap["listening"] is False and snap["phase"] == "unloaded"
    assert snap["models_loaded"] is False and "died" in snap["load_error"]
```
`Feedback` + `FeedbackConfig` are already imported mid-file (lines 1392-1393); `threading`/`time`
at 349-350; `pytest` at 21; `daemon`/`VoiceTypingConfig` at 24. `tmp_path`+`monkeypatch` are pytest
fixtures (no import). Construction with `recorder=None, host_factory=factory` → lazy boot (verified
via `_make_lazy_daemon` at 2498, identical kwargs).

## 4. The kill mechanism + what each detection/assertion proves

After `d.start()`: `_load_host()` → `factory(...)` (NEW `_FakeHost`) → `host.spawn()` (`spawn_calls=1`,
`_alive=True`) → publish (`_models_loaded=True`, phase "idle") → `_arm()` (`_listening` set,
`set_listening(True)`). The run loop now sees `_host` alive + listening → calls `_FakeHost.text()`
which returns `""` at once (loop spins fast).

**Kill:** capture `host = d._host` then set **`host._alive = False`** (simulate child crash). The run
loop's TOP-OF-BODY check `self._host is not None and not self._host.is_alive` becomes True on the very
next iteration → WARNING(pid) + `_handle_dead_host()` + `continue`. Under `_lock`: `_host=None`,
`_models_loaded=False`, `_listening.clear()`, `set_phase("unloaded")`, `set_models_loaded(False)`,
`set_listening(False)`, `_load_error="recorder-host child died unexpectedly"`.

**Test (a)** `test_run_loop_detects_dead_host_and_transitions_to_unloaded`:
wait `_wait_for(lambda: d._models_loaded is False, timeout=2.0)`; assert:
- `d._host is None` ✓  `d._models_loaded is False` ✓  `d.is_listening() is False` ✓
- `"died" in (d._load_error or "")` ✓
- (bonus, proves the phase transition) `fb.phases[-1] == "unloaded"` and `fb.listening_states[-1] is False`

**Test (b)** `test_load_host_respawns_after_dead_child`: capture `old = d._host`; kill; wait
`_wait_for(lambda: d._host is None, timeout=2.0)` (cleanup done); **`d.start()` again** →
`_load_host()`: guard `if self._models_loaded and ...` is False (recovery cleared it; this EXERCISES
the S2 guard) → spawn path → `factory(...)` builds a FRESH `_FakeHost` → `spawn()` (`spawn_calls=1`,
`_alive=True`) → `_models_loaded=True` → `_arm()`. Assert:
- `d._host is not old` (a NEW host object — factory called again) ✓
- `d._host.spawn_calls == 1` (the new host was spawned exactly once) ✓
- `d._models_loaded is True` ✓  `d.is_listening() is True` ✓ (recovery proven)

(Alternative "factory called again" proof: wrap the factory in a counter `{"n":0}` and assert
`creations["n"] == 2`. Object-identity + `spawn_calls` is simpler and matches the S2 probe; the PRP
lists the counter as an optional hardening.)

**Test (c)** `test_status_reports_unloaded_after_child_death`: arm; kill; wait for cleanup;
`snap = d.status_snapshot()`; assert:
- `snap["listening"] is False` (reads `is_listening()`) ✓
- `snap["phase"] == "unloaded"` (reads real Feedback snapshot — REQUIRES real Feedback) ✓
- `snap["models_loaded"] is False` (reads real Feedback snapshot) ✓
- `"died" in snap["load_error"]` (reads `self._load_error`) ✓

## 5. ★ TIMING / CONCURRENCY FACTS (why timeout=2.0 is ample) ★

- `_FakeHost.text()` returns `""` IMMEDIATELY → on the listening path the run loop has NO 0.05s
  sleep; it spins calling `text()`. So once `host._alive` flips False, the NEXT iteration (micro-
  seconds later) hits the liveness check. `_wait_for(..., timeout=2.0)` succeeds near-instantly.
- If the loop were mid-`text()` when `_alive` flips, that call returns within microseconds anyway
  (`_StubRecorder.text()` is non-blocking) → same near-instant detection. No 50ms ceiling concern.
- The detection is single-threaded (run loop reads `host.is_alive` on the loop thread only); the
  kill (main thread setting `host._alive`) is a plain attribute write visible to the loop thread.
  No lock needed for the kill (CPython attribute write is atomic); `_handle_dead_host()` takes
  `_lock` for the cleanup. No deadlock (main thread never holds `_lock` during the kill).

## 6. ★ WHY THE IDLE-UNLOAD WATCHDOG WILL NOT INTERFERE ★

- `_handle_dead_host()` clears `self._disarmed_monotonic = None` (the idle-UNLOAD clock). So after
  recovery the idle-unload watchdog's `not self._models_loaded`/`_disarmed_monotonic is None` guard
  no-ops. And the test's `d.start()` re-arm happens within ~1s (≪ the multi-second unload threshold).
- The idle AUTO-STOP watchdog disarms after `auto_stop_idle_seconds` (default 30s) of no speech.
  These tests finish in <2s and (for b) re-arm immediately → no auto-stop fires. (If worried, the
  test re-arms right after cleanup, well inside any 30s window.)

## 7. ★ NO-BREAKAGE FACTS (these are PURE ADDITIONS) ★

- S3 ONLY **APPENDS** three new test functions (+ a section comment header) to the END of
  `tests/test_daemon.py` (currently 3064 lines; last test = `test_state_json_phase_idle_after_stop`
  from P1.M2.T1.S2). **NO production file is touched** (daemon.py / recorder_host.py / feedback.py
  unchanged). **NO existing helper/fake is modified** (`_FakeHost`, `_make_daemon`,
  `_make_daemon_with_feedback`, `_DaemonFakeFeedback` all unchanged).
- The three test names are UNIQUE (grep for them = 0 hits in the current file).
- Imports needed are ALREADY module-level: `threading` (349), `time as _time` (350), `Feedback`
  (1393), `FeedbackConfig` (1392), `pytest` (21), `daemon`/`VoiceTypingConfig` (24). Nothing to add.
- Expected post-count: **345 → 348 passed**. (No GPU/feed_audio needed.)

## 8. Sibling / parallel boundaries (DISJOINT — no merge conflict)

- **P1.M2.T1.S2** (phase-after-disarm tests) ALSO appends to `tests/test_daemon.py` (the last ~50
  lines, ending at 3064). S3 appends AFTER it (at EOF). Both are pure appends to disjoint line
  ranges → git merges cleanly. S3's test NAMES are distinct from P1.M2.T1.S2's
  (`test_stop_resets_phase_to_idle`, `test_toggle_off_resets_phase_to_idle`,
  `test_auto_stop_resets_phase_to_idle`, `test_state_json_phase_idle_after_stop`).
- **S1/S2** own `voice_typing/daemon.py` (already landed). S3 does NOT touch it.
- S3 does NOT touch `PRD.md` / `tasks.json` / `prd_snapshot.md` / `.gitignore` / `pyproject.toml`.

## 9. Tooling (verified)

- pytest 9.1.1 in `.venv`. Run: `.venv/bin/python -m pytest tests/test_daemon.py -q -k "dead_host
  or respawn or status_reports_unloaded"` for just these three; full gate =
  `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` (→ 348).
- ruff 0.14.13 at `/home/dustin/.local/bin/ruff` (NOT in `.venv`); optional lint on the test file.
- **mypy is NOT installed** — do NOT list it; pytest is the authoritative gate.
- Use FULL paths: `.venv/bin/python -m pytest ...` (zsh aliases `python`/`pytest`).

## 10. Scope (do / don't)

DO: append exactly THREE test functions (+ a section comment header) to the END of
`tests/test_daemon.py`. Use `_make_daemon(host_factory=...)` for (a)/(b); a real-Feedback +
`host_factory=` daemon for (c). Kill via `d._host._alive = False`. Wait via `_wait_for(...)`.
Tear down via the try/finally `request_shutdown()` + `_wait_for(not t.is_alive)` + `t.join()` pattern.

DON'T: edit any production file (daemon.py/recorder_host.py/feedback.py/config.py); edit any existing
fake/helper (`_FakeHost`/`_make_daemon`/`_make_daemon_with_feedback`/`_DaemonFakeFeedback`); add new
imports (all needed symbols already module-level); inject the `_FakeHost` via `recorder_host=` (it
boots `_alive=False` → instant false death); use `_DaemonFakeFeedback` for test (c) (no `.snapshot()`);
run mypy; touch PRD/tasks.json/prd_snapshot/.gitignore/pyproject/uv.lock. No new deps. DOCS: none.
