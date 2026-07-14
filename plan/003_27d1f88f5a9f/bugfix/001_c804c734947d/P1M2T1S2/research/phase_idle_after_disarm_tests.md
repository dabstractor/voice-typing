# Research — P1.M2.T1.S2: Test phase returns to idle after disarm (stop, toggle-off, auto-stop)

> Purpose: pin down the test-only deliverable for the Issue 2 regression. Sibling **P1.M2.T1.S1**
> ("Ready") adds the CODE fix — one line, `self._feedback.set_phase("idle")` inside `_disarm()`
> (already present in the current tree at `daemon.py:875`). **This task (S2) writes the committed
> pytest** that proves the fix: after any disarm path, `phase` returns to `'idle'`. All facts below
> were verified live (Python 3.12.10, `.venv/bin/python`).

## 1. Boundary (S1 = code, S2 = tests)

- **P1.M2.T1.S1** owns the one-line source edit in `VoiceTypingDaemon._disarm()` (after
  `set_listening(False)`). Its PRP explicitly says "S2 owns the committed pytest; S1's validation
  uses a throwaway inline check (NOT a committed test)." The fix is the chokepoint: `_disarm()` is
  called by ALL THREE disarm paths — `stop()`, `toggle()` (disarm branch), and `_maybe_auto_stop()`
  (the 30 s auto-stop). So one line fixes all three, and three tests cover all three.
- **P1.M2.T1.S2 (THIS TASK)** owns ONLY `tests/test_daemon.py` additions. NO source changes. No
  `recorder_host.py`, no `feedback.py`, no `daemon.py` (S1 owns it; the fix is already in).
- The optional VAD-relay gate (recorder_host._dispatch('vad')) is **deferred** by S1 ("only if
  observed") — out of scope here too.

## 2. S1's fix is already in the tree (verified)

```
daemon.py:875:        self._feedback.set_phase("idle")  # Issue 2 / P1.M2.T1.S1: 'loaded / not listening' ⇒ phase idle
```
(There is also a `set_phase("idle")` at `daemon.py:677` — a different, pre-existing site —
`_handle_dead_host`/`_unload`; not this task's concern.) So the new tests will PASS against the
current code. They are **regression tests**: without S1's line, `fb.phases[-1]` would stay
`'listening'`/`'speaking'` and the assertions would FAIL (verified by simulation, §5).

## 3. Test infrastructure (verified — `tests/test_daemon.py`)

- **`_FakeFeedback`** (base): `.phases: list[str]` — `set_phase(p)` APPENDS p. `.partials`.
  `set_models_loaded` is a no-op stub.
- **`_DaemonFakeFeedback(_FakeFeedback)`**: adds `.listening_states` (`set_listening` appends),
  `.finals` (`record_final`). This is what `_make_daemon()` uses as `fb`.
- **`_make_daemon(*, recorder=None, recorder_host=None, host_factory=None, backend=None, cfg=None)`**
  → returns `(d, fb, rec, be)`. Injects `_StubRecorder` (wrapped in the legacy host adapter) so the
  daemon boots **already-loaded** (`_models_loaded=True`, `_host` is the legacy adapter). ⇒
  `d.start()` arms WITHOUT needing the run loop / `_load_host` spawn. `_DaemonFakeFeedback`,
  `_FakeBackend`, `_ok_probe` mic prober.
- **`_make_daemon_with_feedback(tmp_path, monkeypatch, *, cuda=True)`** → returns `(d, fb)` where
  `fb` is a **REAL** `Feedback` (has `.snapshot()`) with `state_file=str(tmp_path/"state.json")`.
  Used for the on-disk state.json test. (It monkeypatches `cuda_check.resolve_device_and_models`.)
- **Time advancement idiom** (from `test_auto_stop_*` @583): `d._last_speech_monotonic =
  _time.monotonic() - 31.0` (> the 30.0 s default `auto_stop_idle_seconds`) then call
  `d._maybe_auto_stop()` directly. **No run loop, no real sleep — fully deterministic.**
- **Imports**: `import time as _time` @350 (mid-file, `# noqa: E402`); `Feedback`/`FeedbackConfig`
  @1392-1393 (mid-file); `from voice_typing import daemon` @23; `VoiceTypingConfig` @24; `pytest`
  @21. **`json` is NOT imported** — the state.json test adds `import json` (mid-file, noqa E402,
  mirroring the file's convention).

## 4. The 4 tests (all verified PASSING against current code)

All four are **synchronous unit tests** (no `run()` thread, no `_wait_for`, no real subprocess) —
the fakes make `start()`/`stop()`/`toggle()`/`_maybe_auto_stop()` directly callable.

(a) **`test_disarm_resets_phase_to_idle`** (stop path): `_make_daemon()` → `d.start()` →
   `d._feedback.set_phase("listening")` (simulate VAD) → `d.stop()` → assert `d.is_listening()
   is False` and `fb.phases[-1] == "idle"`.
(b) **`test_toggle_off_resets_phase_to_idle`**: same but `d.toggle()` while listening (disarm
   branch); set phase `'speaking'` first.
(c) **`test_auto_stop_resets_phase_to_idle`**: `d.start()` → `set_phase("speaking")` →
   `d._last_speech_monotonic = _time.monotonic() - 31.0` → `d._maybe_auto_stop()` → assert
   disarmed + `fb.phases[-1] == "idle"`.
(d) **`test_state_json_phase_idle_after_stop`** (real Feedback, on-disk):
   `_make_daemon_with_feedback(tmp_path, monkeypatch)` → `d.start()` → `fb.set_phase("listening")`
   → `d.stop()` → `json.load(open(tmp_path/"state.json"))` → assert `["phase"] == "idle"` and
   `["listening"] is False`. This proves the atomic state.json WRITE (the `_DaemonFakeFeedback` in
   (a)-(c) is in-memory only; (d) is the integration-level on-disk proof).

The primary assertion is `fb.phases[-1] == "idle"` (the LAST `set_phase` after disarm is idle) —
stronger than `"idle" in fb.phases`. Each test ALSO asserts `d.is_listening() is False` (the disarm
actually happened), so it proves the full "loaded / not listening ⇒ phase idle" invariant.

## 5. Regression property (verified)

The assertion `fb.phases[-1] == "idle"` FAILS without S1's `_disarm()` line: pre-fix, `_disarm()`
calls `set_listening(False)` but NOT `set_phase("idle")`, so `fb.phases` ends with the VAD value
(`'listening'`/`'speaking'`). Simulated: `PRE-fix fb.phases[-1] = 'listening' -> assertion FAIL
(detects the bug)`. So these are genuine regression tests, not tautologies.

## 6. Placement + scope

- **APPEND** a new section at END of `tests/test_daemon.py` with a `# P1.M2.T1.S2 — phase returns
  to idle after disarm` banner + `import json  # noqa: E402`. Four `test_*` functions. No other
  file touched. No source changes (S1 owns `daemon.py`).
- No run loop / threading ⇒ no flakiness, no `_wait_for`, fast (<50 ms total).
- Existing tests unaffected: the new tests are additive; they don't modify `_make_daemon` or any
  fixture. (S1's no-regression note: the additive `set_phase('idle')` only appends to `fb.phases`
  on disarm; no existing test asserts `fb.phases` after a disarm, so the suite stayed green — and
  these new tests are the ones that finally DO assert it.)

## 7. Scope boundaries (no conflict)

- **vs S1 (parallel, "Ready")**: S1 edits `daemon.py` `_disarm()` (one line); S2 edits
  `tests/test_daemon.py` (append tests). Different files. S2 CONSUMES S1's fix.
- **vs P1.M2.T2 (child-crash recovery, Issue 3)**: that touches `_handle_dead_host`/`_load_host`
  liveness — different methods, different tests. No overlap.
- **No source files touched.** This is a pure test addition. Validation = pytest only (no ruff/mypy).
