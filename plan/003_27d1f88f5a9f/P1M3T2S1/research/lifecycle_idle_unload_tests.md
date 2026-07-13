# Research — P1.M3.T2.S1: idle-unload lifecycle + start-level single-flight tests

Verified live on the target machine (2026-07-13). Authoritative for the PRP.

## 0. What this subtask IS and IS NOT

**IS:** a test-only APPEND to `tests/test_daemon.py` adding the **idle-unload lifecycle** tests
(clauses e/f/g — `_maybe_idle_unload()` fire/disable/reset) + two small gap-fills (boot phase,
start-level single-flight). NO CUDA, NO RealtimeSTT — all via the existing `_StubRecorder` fake.

**IS NOT:** NOT a re-test of clauses already covered by the P1.M2.T1.S1 lazy-load section. The
item lists (a)-(h), but (a)/(b)/(c)/(d)/(h) ALREADY EXIST (see §1). Duplicating them would be a
scope error. This subtask fills the real gaps (§2).

## 1. Already-covered clauses (CITE — do NOT duplicate)

`tests/test_daemon.py` line numbers (P1.M2.T1.S1 "lazy load" section, ~1905-2060):

| Item clause | Existing test (line) | What it asserts |
|---|---|---|
| (a) boot unloaded (attrs) | `test_lazy_daemon_boots_unloaded_with_no_recorder` (~1918) | `_recorder None`, `_models_loaded False`, `_loading False`, `_load_error None` — **but NOT phase** |
| (b) start→load→arm | `test_start_on_lazy_daemon_triggers_load_then_arms` (~2010) | `_models_loaded True`, `is_listening() True`, `rec.mic == [True]` |
| (c) single-flight (mechanism) | `test_load_recorder_single_flight_one_build_under_concurrency` (~2031) | two concurrent `_load_recorder()` → ONE build (the `_load_recorder` entry point) |
| (d) load failure → unloaded | `test_load_recorder_total_failure_stays_unloaded` (~1985) + `test_start_suppressed_when_load_fails` (~2020) | `_load_error` set, `_recorder None`, `_models_loaded False`, start() stays unarmed |
| (h) injected recorder loaded at boot | `test_injected_recorder_is_loaded_at_construction` (~2027) | `_models_loaded True` when `recorder=` injected |

→ DO NOT re-write these. Reference them in the PRP.

## 2. The GENUINELY NEW work (this subtask)

**Idle-unload lifecycle via `_maybe_idle_unload()` — NO existing test calls it.** (S2's race tests
call `_unload_recorder()` DIRECTLY — a different entry point; they do not cover the lock-free
pre-check / disable / arm-reset behavior of `_maybe_idle_unload`.)

| New test | Clause | Mirrors (auto-stop section) |
|---|---|---|
| `test_lazy_boot_records_unloaded_phase` | (a) phase gap | — (existing boot test omits phase) |
| `test_concurrent_start_calls_build_recorder_once` | (c) start-level gap | `test_load_recorder_single_flight_one_build_under_concurrency` (but via `start()`) |
| `test_idle_unload_fires_when_disarmed_beyond_threshold` | (e) | `test_auto_stop_disarms_when_idle_beyond_threshold` (~480) |
| `test_idle_unload_keeps_resident_within_threshold` | (e negative) | `test_auto_stop_keeps_alive_with_recent_speech` |
| `test_idle_unload_disabled_when_threshold_zero` | (f) | `test_auto_stop_disabled_when_threshold_zero` (~513) |
| `test_idle_unload_noop_when_listening` | (e guard) | — |
| `test_idle_unload_noop_when_never_disarmed` | (e guard) | `test_auto_stop_noop_when_not_listening` |
| `test_idle_unload_noop_when_not_loaded` | (e guard) | — |
| `test_arm_resets_idle_unload_clock` | (g) | `test_touch_speech_resets_the_idle_clock` / `test_disarm_clears_the_idle_clock` |

**9 new tests.** Baseline 131 → 140.

## 3. The daemon API contracts under test (read from voice_typing/daemon.py)

- **`_maybe_idle_unload()`** (793-815): `threshold = cfg.asr.auto_unload_idle_seconds`. If
  `threshold <= 0` → return (disabled). Lock-free pre-check: `not _models_loaded OR
  _listening.is_set() OR _disarmed_monotonic is None OR time.monotonic() - _disarmed_monotonic <
  threshold` → return; else delegate to `_unload_recorder()`.
- **`_unload_recorder()`** (818-855): `with _lock`: re-check full condition (incl. `_listening`) →
  abort OR `_bounded_shutdown()` + `_recorder=None` + `_models_loaded=False` +
  `set_phase("unloaded")`.
- **`_arm()`** (699-707): `_listening.set()`, **`_disarmed_monotonic = None`** (clears the
  idle-unload clock), `set_microphone(True)`, `set_listening(True)`.
- **`_disarm()`** (709-728): `_listening.clear()`, **`_disarmed_monotonic = time.monotonic()`**
  (stamps the idle-unload clock), `set_microphone(False)`, `set_listening(False)`.
- **`__init__`** (415-481): `_disarmed_monotonic = None`; `_models_loaded = recorder is not None`;
  `set_phase("idle" if recorder is not None else "unloaded")`.
- **`config.py`** line 60: `auto_unload_idle_seconds: float = 1800.0` on `AsrConfig` (0 disables).

## 4. The setup idiom (mirror the auto-stop section — INLINE, no new helper)

The auto-stop tests (~480-560) do NOT use a helper; they inline `_make_daemon()` → `d.start()` →
set `_last_speech_monotonic` directly → `_maybe_auto_stop()`. The idle-UNLOAD analogue:

```python
d, fb, rec, _be = _make_daemon()          # injected _StubRecorder -> _models_loaded True
d.start()                                  # arm  -> _disarmed_monotonic = None
d.stop()                                   # disarm -> _disarmed_monotonic = now
d._disarmed_monotonic = _time.monotonic() - 1801.0   # push past the 1800s default threshold
d._maybe_idle_unload()
assert d._recorder is None and d._models_loaded is False
```

This is deterministic (no sleeps) and uses ONLY `_make_daemon()`/`_make_lazy_daemon()`/`_StubRecorder`/
`_DaemonFakeFeedback`/module-level `threading` + `_time`. NO new helper class — and CRUCIALLY
**different names from S2** (which already landed `_ControllableShutdownRecorder` +
`_idle_unloaded_loaded_daemon` at lines 2071/2091).

## 5. Test-fake limitation (CRITICAL for assertions)

`_DaemonFakeFeedback` / `_FakeFeedback` have **NO `snapshot()` method** (verified: `grep "def
snapshot" tests/test_daemon.py` → none). `status_snapshot()` calls `self._feedback.snapshot()`, so
calling `d.status_snapshot()` on a `_make_daemon()`/`_make_lazy_daemon()` daemon RAISES
AttributeError. (status_snapshot IS tested at lines 969-997 via a DIFFERENT helper
`_make_daemon_with_feedback` that wires a feedback WITH `snapshot()`.)

→ **Assert via `fb.phases[-1]` (the fake records `set_phase` calls) + `d._load_error` /
`d._recorder` / `d._models_loaded` (instance attrs), NOT `d.status_snapshot()`.** This is exactly
what the existing lazy-load tests do.

## 6. Coordination with the parallel item (P1.M3.T1.S2 — race safety)

S2 has ALREADY LANDED in `tests/test_daemon.py` (section header at line 2063; 5 tests; file now
131 tests; ends at line 2281 with `test_armed_state_aborts_unload_via_listening_recheck`).
- **Append point:** the VERY END of the file (after line 2281). Do NOT insert in the middle.
- **Names S2 owns (do NOT redefine):** `_ControllableShutdownRecorder`, `_idle_unloaded_loaded_daemon`.
- **Disjoint scope:** S2 tests `_unload_recorder()` directly (race safety); this subtask tests
  `_maybe_idle_unload()` (lifecycle/disable/reset) + the two gap-fills. No overlap.

## 7. Tooling reality (confirmed live 2026-07-13)

- **Run:** `.venv/bin/python -m pytest tests/test_daemon.py -v` (zsh aliases `python`→`uv run`;
  ALWAYS `.venv/bin/python`). Baseline GREEN: **131 passed** (post-S2).
- **No mypy** (skip). **ruff** optional at `/home/dustin/.local/bin/ruff` (NOT in .venv) — soft lint.
- The idle-unload tests are SINGLE-THREADED + deterministic (no Event/sleep races) except the one
  start-level single-flight test (which mirrors the existing single-flight test's Event-gated design).
- `_StubRecorder.shutdown()` does `self.shutdowns += 1` (line ~383) and returns instantly →
  `_bounded_shutdown` completes synchronously → `rec.shutdowns == 1` is a safe assertion after an
  unload (proven by S2's `test_unload_routes_through_bounded_shutdown...` which uses the same fake).
