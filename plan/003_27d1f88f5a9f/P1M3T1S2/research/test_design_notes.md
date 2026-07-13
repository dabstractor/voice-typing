# P1.M3.T1.S2 — Test Design Notes (teardown-vs-load race safety)

**Goal:** Verify, via committed unit tests in `tests/test_daemon.py` (using the `_StubRecorder`
fake — NO CUDA), that an arm racing an in-flight idle-unload teardown **waits** (single-flight
under `self._lock`), then **loads fresh** — it can never see a half-torn-down recorder, and the
wait is bounded. This is a **test-only** subtask: it VERIFIES the design P1.M3.T1.S1 implements
(PRD §4.2bis). Written FIRST (TDD) — RED until S1 lands `_unload_recorder`/`_maybe_idle_unload`/
`_disarmed_monotonic`.

---

## 1. The contract under test (from P1M3T1S1/PRP.md — assume it lands EXACTLY as specified)

S1 adds to `voice_typing/daemon.py`:

| Symbol | Behavior |
|---|---|
| `_unload_recorder()` | `with self._lock:` → re-check `not _models_loaded OR _listening.is_set() OR _disarmed_monotonic is None OR threshold<=0 OR now-_disarmed_monotonic<threshold` → `return` (abort); else `_bounded_shutdown()` UNDER the lock, then `_recorder=None`, `_models_loaded=False`, `set_phase('unloaded')`, `set_models_loaded(False)`. |
| `_maybe_idle_unload()` | Lock-free pre-check; delegates to `_unload_recorder()`. (S2 tests `_unload_recorder` directly.) |
| `_disarmed_monotonic` | `None` in `__init__`; `_arm()` clears it; `_disarm()` stamps `time.monotonic()`. |
| `_idle_unload_watchdog()` | run()-started daemon thread; calls `_maybe_idle_unload`. (Not exercised by S2 — the race is at `_unload_recorder` granularity.) |

**Consumed (prerequisites — do NOT edit, already landed):**
- `_load_recorder()` (P1.M2.T1.S1): FIRST action is `with self._lock:`; checks `_models_loaded`/
  `_loading`; acquire-release-reacquires `_lock` (the heavy `build_recorder` runs OUTSIDE `_lock`).
  Called by `start()`/`toggle()` OUTSIDE `_lock`.
- `_bounded_shutdown(timeout=10.0)` (P1.M1.T1.S2): runs `recorder.shutdown()` in a daemon thread +
  `done.wait(timeout)`; on timeout force-terminates `transcript_process`/`reader_process`. **Bounded
  ≤10s; NEVER touches `self._lock`; READS `self._recorder` directly.** → safe to call UNDER `_lock`.
- `start()` (P1.M2.T1.S1): `if not self._load_recorder(): return` then `with self._lock: self._arm()`.
- `_arm()`/`_disarm()`: take `_lock` (caller holds it); `_arm` clears `_disarmed_monotonic`, `_disarm`
  stamps it.

---

## 2. The concurrency model (the core — PRD §4.2bis, pinned by S1 research §3)

**Single-flight under `_lock`:** `_unload_recorder()` holds `_lock` for the WHOLE teardown
(`_bounded_shutdown()` runs under it). `_load_recorder()`'s FIRST action is `with self._lock:`.
So an arm (`start`) that arrives while a teardown holds the lock **blocks** there, waits for the
teardown to release, then sees `_models_loaded=False`/`_recorder=None` and builds FRESH. An arm can
never see a half-torn-down recorder.

**The TOCTOU re-check (reverse race):** the watchdog's pre-check is lock-free; between it and
`_unload_recorder` acquiring the lock, an arm could happen. So `_unload_recorder` re-checks the FULL
condition UNDER the lock — critically `self._listening.is_set()` — so an arm that raced in ABORTS the
unload (the armed state wins, recorder stays resident). This is the OTHER direction of "an arm can
never see a half-torn-down recorder."

**Why teardown-under-lock is OK:** `_bounded_shutdown` is bounded (≤10s) and never touches `_lock`.
So holding `_lock` across it cannot deadlock, and the worst-case arm wait is the teardown bound (not
the legacy ~90s `recorder.shutdown()` wedge — PRD §8 risk row).

---

## 3. Realizing each item clause as a committed test

| Clause | Test | How (deterministic, fakes only) |
|---|---|---|
| (a) arm blocks until unload releases `_lock`, then `_load_recorder` runs | `test_arm_racing_unload_waits_then_loads_fresh` | `_ControllableShutdownRecorder` (shutdown() blocks on a release Event) holds `_lock` via the REAL `_bounded_shutdown`; a racing `start()` is asserted STILL BLOCKED (thread alive, not armed, `_lock.locked()`) until `release.set()`; then it loads fresh + arms. |
| (b) after race: fresh instance, `_models_loaded=True`, listening on | (assertions in the same test) | `monkeypatch daemon.build_recorder` to return a DISTINCT `_StubRecorder`; assert `d._recorder is fresh` (≠ torn-down original), `_models_loaded is True`, `is_listening() is True`. |
| (c) no half-torn-down recorder ever visible | `test_recorder_never_half_torn_down_during_race` | A polling thread samples `d._recorder` every 1ms across the unload→reload; assert EVERY sample is `None` OR a fully-built recorder (callable `text`/`set_microphone`/`abort`/`shutdown`). CPython attr reads are atomic; only `None`+complete stubs are ever assigned. |
| (d) `_bounded_shutdown` doesn't block the arm excessively (bounded wait) | `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded` | `monkeypatch d._bounded_shutdown` to RECORD the call; assert `_unload_recorder` calls it with the default bounded timeout (10.0) + the unload completes promptly (elapsed < 2s). The bound itself is proven in the existing `test_bounded_shutdown_force_cleans_on_timeout`. |
| (mechanism) `_load_recorder` + `_unload_recorder` share the SAME lock | `test_load_and_unload_serialize_on_the_same_single_flight_lock` | Acquire `d._lock` from the test (simulate an in-flight teardown); assert a `_load_recorder()` call in a thread is BLOCKED until the lock is released. Pure structural proof, no timing. |
| (reverse race) armed state aborts the unload | `test_armed_state_aborts_unload_via_listening_recheck` | Arm the daemon, then call `_unload_recorder()`; the `_listening.is_set()` re-check under the lock aborts it → recorder stays resident. |

**6 tests, all using `_StubRecorder` / `_make_daemon` / `_DaemonFakeFeedback` / `_FakeBackend` /
`_wait_for` / module-level `threading` + `_time`.** No new imports. No CUDA, no RealtimeSTT.

---

## 4. The fakes

- **`_ControllableShutdownRecorder(_StubRecorder)`** — `__init__(started, release)`;
  `shutdown()` sets `started`, then `release.wait(5.0)` (bounded safety so a test bug never hangs
  the suite), then `super`-style `self.shutdowns += 1`. This holds `_unload_recorder` inside the
  REAL `_bounded_shutdown` (`done.wait(timeout=10.0)` blocks until the daemon-thread `shutdown()`
  returns), which holds `_lock`. The real 10s cap + daemon worker thread = no suite hang.
- **`_idle_unloaded_loaded_daemon(recorder, threshold=0.001)`** — a helper that builds a LOADED
  daemon (`_make_daemon(recorder=...)`), disarms it under the lock, and sets `_disarmed_monotonic =
  0.0` so `_unload_recorder`'s time re-check passes DETERMINISTICALLY (no sleeps): `time.monotonic()
  - 0.0` is huge vs the tiny positive threshold. Tiny `auto_unload_idle_seconds` (>0; 0 disables).

---

## 5. Insertion point + style

- **Append** the section to the END of `tests/test_daemon.py`, immediately after
  `test_load_recorder_single_flight_one_build_under_concurrency` (currently the LAST test, line 2060).
  Both are concurrency tests → natural home.
- **Style** mirrors the file: section header `# P1.M3.T1.S2 — ...`; `from __future__ import
  annotations` already at top (line 16); `threading` + `time as _time` already module-level (349-350);
  reuse `_StubRecorder`/`_make_daemon`/`_wait_for`; `monkeypatch.setattr(daemon, "build_recorder",
  fake)` is the established load-injection pattern (used by the single-flight test).
- **DO NOT** create a new test file; **DO NOT** edit `daemon.py` (S1 owns it, in parallel); **DO NOT**
  add `tests/__init__.py`.

---

## 6. Tooling reality (confirmed live 2026-07-13)

- **Run:** `.venv/bin/python -m pytest tests/test_daemon.py -v` (zsh aliases `python`→`uv run`;
  ALWAYS `.venv/bin/python`). The fast suite baseline is GREEN: **126 passed** (pre-S2).
- **No mypy** (skip). **ruff** optional at `/home/dustin/.local/bin/ruff` (a uv tool, NOT in `.venv`)
  — `ruff format --check` is a soft lint, not a gate.
- The race tests are DETERMINISTIC (Event-gated, not `time.sleep` races) — they assert blocking via
  thread-alive + `_lock.locked()` + Event probes, mirroring `test_on_final_lock_held_across_type_text`
  + `test_load_recorder_single_flight_one_build_under_concurrency`.

---

## 7. Test inventory (6 tests)

| # | Test | Clause |
|---|---|---|
| 1 | `test_arm_racing_unload_waits_then_loads_fresh` | (a)+(b) |
| 2 | `test_recorder_never_half_torn_down_during_race` | (c) |
| 3 | `test_load_and_unload_serialize_on_the_same_single_flight_lock` | (a) mechanism |
| 4 | `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded` | (d) |
| 5 | `test_armed_state_aborts_unload_via_listening_recheck` | reverse race (c) |
| 6 | (helper `_idle_unloaded_loaded_daemon` + `_ControllableShutdownRecorder` class) | — |

(Plus the helper + fake class — not tests themselves.)
