# PRP — P1.M3.T1.S2: Verify teardown-vs-load race safety (arm racing idle-unload waits, then loads fresh)

## Goal

**Feature Goal**: Add a committed unit-test section to `tests/test_daemon.py` (using the existing
`_StubRecorder` fake — **NO CUDA, NO RealtimeSTT**) that VERIFIES the single-flight race-safety
design P1.M3.T1.S1 implements (PRD §4.2bis): when an arm (`start`) races an in-flight idle-unload
teardown, it **blocks** on the SAME `self._lock` the teardown holds, **waits**, then **loads a fresh
recorder** — it can never observe a half-torn-down recorder, and the wait is bounded by the bounded
teardown (`_bounded_shutdown`). This is a **test-only** subtask: it produces NO production code;
it hardens S1's non-committed L3 race smoke into deterministic, committed pytest.

**Deliverable** (ONE artifact — append a test section; do NOT create a new file):
1. `tests/test_daemon.py` — APPEND a `# P1.M3.T1.S2 — teardown-vs-load race safety` section (after
   `test_load_recorder_single_flight_one_build_under_concurrency`, the current last test) containing
   a `_ControllableShutdownRecorder` fake, an `_idle_unloaded_loaded_daemon` helper, and **5 tests**
   (verbatim source in Implementation Blueprint → Task 2).

**Success Definition**:
- (a) `tests/test_daemon.py` parses; `.venv/bin/python -m pytest tests/test_daemon.py -v` → all prior
  126 tests still pass + **5 new tests pass** (131 total), deterministically (Event-gated, not
  `time.sleep` races).
- (b) **Clause (a)+(b)** — `test_arm_racing_unload_waits_then_loads_fresh`: with a teardown holding
  `_lock` (via the REAL `_bounded_shutdown` running a recorder whose `shutdown()` blocks on a release
  Event), a concurrent `start()` is proven STILL BLOCKED (arm thread alive, not listening, `_lock.locked()`);
  after `release.set()` it loads a FRESH recorder (≠ the torn-down original) and arms (`_models_loaded
  is True`, `is_listening() is True`).
- (c) **Clause (c)** — `test_recorder_never_half_torn_down_during_race`: a polling thread sampling
  `d._recorder` every 1ms across the unload→reload observes ONLY `None` or a fully-built recorder
  (never a partial/garbage value); both the `None` window and a resident recorder are seen.
- (d) **Clause (d)** — `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded`:
  `_unload_recorder()` is proven to tear down via `_bounded_shutdown(10.0)` (the bounded path whose
  ≤10s cap is proven in the existing `test_bounded_shutdown_force_cleans_on_timeout`); the unload
  completes promptly (elapsed < 2s), so a racing arm's wait is bounded, never the legacy ~90s wedge.
- (e) **Mechanism** — `test_load_and_unload_serialize_on_the_same_single_flight_lock`: a direct
  structural proof that `_load_recorder()`'s first `with self._lock:` blocks while the lock is held
  (simulating an in-flight teardown), then proceeds once released — no timing.
- (f) **Reverse race** — `test_armed_state_aborts_unload_via_listening_recheck`: an arm that wins the
  race to the lock makes `_unload_recorder()`'s `_listening.is_set()` re-check (under the lock) ABORT
  the unload → recorder stays resident (the armed state wins).
- (g) No out-of-scope files: NO edit to `voice_typing/daemon.py` (S1 owns it, in parallel), no new
  test file, no `tests/__init__.py`, no edits to `config.py`/`feedback.py`/`ctl.py`/`config.toml`/
  `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps.

## User Persona

**Target User**: None directly (test-only; item DOCS: "none"). Its "users" are the maintainer running
`pytest` and the orchestrator gating P1.M3.T1 (idle-unload) complete on a proven race-safe design.

**Use Case**: `cd voice-typing && .venv/bin/python -m pytest tests/test_daemon.py -v` → 5 new race
tests green → PRD §4.2bis concurrency guarantee ("an arm can never see a half-torn-down recorder") is
regression-proof in CI/CPU contexts, with no GPU.

**Pain Points Addressed**: (1) The teardown-vs-load race is the subtlest correctness property of the
idle-unload feature — without a committed test, a future refactor that drops the `_listening` re-check
or moves `_bounded_shutdown` out from under `_lock` would silently reintroduce a half-torn-down-
recorder bug. (2) Verifying it for real would require a GPU + a 30-min idle window; the fakes make it
a 2-second deterministic pytest.

## Why

- **It is the verification gate for the hardest part of idle-unload.** S1 ships the implementation +
  a non-committed L3 smoke; S2 hardens the race-safety claim into committed, deterministic pytest so
  the design cannot silently regress. PRD §4.2bis pins the guarantee verbatim.
- **Tests ride with the work (SOW §3).** This is the dedicated teardown-vs-load RACE test the plan
  splits out of S1 (S1 = impl + config-test fix; S2 = race test; T2.S1 = fire/reset/disable behavior).
- **Cheap, additive, GPU-free, no new deps.** Pure pytest + stdlib `threading`/`time` + the existing
  `_StubRecorder` fake. Disjoint from S1's edits (S1 touches `daemon.py`/`config.py`/`config.toml`/
  `test_config_repo_default.py`; S2 touches only `tests/test_daemon.py` — a DIFFERENT file).
- **Guards the PRD §8 risk row directly.** The ~90s `recorder.shutdown()` wedge is the reason
  teardown MUST be bounded; clause (d) proves `_unload_recorder` routes through `_bounded_shutdown`
  (bounded), so a racing arm's wait can never reproduce that 90s hang every 30 min.

## What

Append a `# P1.M3.T1.S2 — teardown-vs-load race safety` section to `tests/test_daemon.py` containing:
a `_ControllableShutdownRecorder(_StubRecorder)` fake (its `shutdown()` blocks on a release Event,
holding `_unload_recorder` inside the real `_bounded_shutdown` and thus holding `_lock`); an
`_idle_unloaded_loaded_daemon` helper (a loaded, disarmed daemon with `_disarmed_monotonic` pushed
far into the past so `_unload_recorder`'s time re-check passes deterministically with no sleeps); and
5 tests realizing clauses (a)–(d) + the single-flight-lock mechanism + the reverse `_listening` race.
All use `monkeypatch` (stdlib pytest), `threading`, `time as _time`, and the existing fakes — no new
imports, no new deps. Verbatim source in Implementation Blueprint → Task 2.

### Success Criteria

- [ ] `tests/test_daemon.py` parses (`.venv/bin/python -m py_compile` + `ast.parse`).
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → 131 passed (126 prior + 5 new), 0 failed.
- [ ] `test_arm_racing_unload_waits_then_loads_fresh`: arm proven BLOCKED while teardown holds `_lock`
  (thread alive, not armed, `_lock.locked()`); after release, fresh recorder resident + armed.
- [ ] `test_recorder_never_half_torn_down_during_race`: every `_recorder` sample is `None` or a full
  recorder; both states observed.
- [ ] `test_load_and_unload_serialize_on_the_same_single_flight_lock`: `_load_recorder()` blocks while
  `_lock` is held, proceeds once released.
- [ ] `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded`: `_unload_recorder` calls
  `_bounded_shutdown(10.0)`; unload completes in < 2s.
- [ ] `test_armed_state_aborts_unload_via_listening_recheck`: an armed daemon's `_unload_recorder()`
  is a no-op (recorder stays resident, `_models_loaded` True).
- [ ] ONLY `tests/test_daemon.py` modified (`git status --short` shows only that file).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the CONTRACT under test (S1's `_unload_recorder` —
its `with self._lock:` re-check incl. `_listening`, its `_bounded_shutdown()`-under-the-lock, its
state flips) is pinned from `P1M3T1S1/PRP.md` (Edit D4) and mirrored in research §1; the consumed
prerequisites (`_load_recorder`'s acquire-release-reacquire of `_lock`, `_bounded_shutdown`'s
boundedness + lock-freedom, `start()`'s load-then-arm flow) are pinned with line numbers (research §1);
the concurrency model (single-flight + the TOCTOU `_listening` re-check) is explained (research §2);
the existing fakes + helpers to reuse (`_StubRecorder`, `_make_daemon`, `_DaemonFakeFeedback`,
`_wait_for`, module-level `threading`/`_time`, the `monkeypatch.setattr(daemon, "build_recorder", ...)`
load-injection pattern) are identified; the deterministic Event-gated blocking-assertion idiom is
demonstrated from the existing `test_on_final_lock_held_across_type_text` +
`test_load_recorder_single_flight_one_build_under_concurrency`; the verbatim test source is in
Implementation Blueprint → Task 2. The fast-suite baseline (126 passed) is verified live.

### Documentation & References

```yaml
# MUST READ — the contract under test (S1's deliverable). READ to align method names + behavior.
- file: plan/003_27d1f88f5a9f/P1M3T1S1/PRP.md
  why: "Defines EXACTLY what _unload_recorder does (Edit D4): `with self._lock:` -> re-check
        (not _models_loaded OR _listening.is_set() OR _disarmed_monotonic is None OR threshold<=0 OR
        now-_disarmed_monotonic<threshold) -> return; else _bounded_shutdown() UNDER the lock, then
        _recorder=None/_models_loaded=False/set_phase('unloaded')/set_models_loaded(False). Also pins
        _disarmed_monotonic wiring (init None; _arm clears; _disarm stamps) + _maybe_idle_unload."
  critical: "S1 is implemented IN PARALLEL; assume it lands EXACTLY as specified. _unload_recorder
             calls self._bounded_shutdown() with NO timeout arg (default 10.0) — test (d) asserts that.
             The _listening.is_set() re-check is the race guard test (reverse race) exercises."

# MUST READ — this task's research (concurrency model + per-clause test realization + fakes)
- docfile: plan/003_27d1f88f5a9f/P1M3T1S2/research/test_design_notes.md
  why: "§1 the S1 contract table + consumed prerequisites (_load_recorder acquire-release-reacquires
        _lock; _bounded_shutdown bounded + never touches _lock + reads self._recorder; start()
        load-then-arm). §2 the concurrency model (single-flight under _lock + the TOCTOU _listening
        re-check). §3 each item clause mapped to a test. §4 the fakes (_ControllableShutdownRecorder,
        _idle_unloaded_loaded_daemon). §5 insertion point + style. §6 tooling. §7 the test inventory."
  section: "ALL load-bearing. §1 (contract), §2 (model), §3 (clause->test), §4 (fakes)."

# MUST READ — the consumed prerequisite (_load_recorder: single-flight over _lock) + start() flow
- file: voice_typing/daemon.py
  why: "_load_recorder (481-563): FIRST line `with self._lock:` -> the arm's blocking point. start()
        (829-836): `if not self._load_recorder(): return` then `with self._lock: self._arm()`. _arm
        (691-698) clears _disarmed_monotonic (S1); _disarm (700-722) stamps it. __init__ (415-481):
        _lock, _listening, _recorder, _models_loaded, _load_cond. These are the EXACT attrs the tests
        read/set. READ, do NOT edit (S1 owns daemon.py in parallel)."
  critical: "Do NOT edit daemon.py. The tests access d._lock/d._recorder/d._models_loaded/d._listening/
             d._disarmed_monotonic (all instance attrs). _load_recorder acquire-release-reacquires
             _lock -> calling it WHILE holding _lock deadlocks (the test never holds _lock across a
             _load_recorder CALL except the structural test, which holds it then RELEASES)."

# MUST READ — the consumed prerequisite (_bounded_shutdown: bounded + lock-free + reads _recorder)
- file: voice_typing/daemon.py
  why: "_bounded_shutdown (1030-1088): runs self._recorder.shutdown() in a daemon thread + done.wait(
        timeout=10.0); on timeout force-terminates transcript_process/reader_process. NEVER re-raises;
        NEVER acquires self._lock (uses its own done Event). READS self._recorder directly."
  critical: "_unload_recorder calls self._bounded_shutdown() with NO arg -> default 10.0 (test d
             asserts calls == [10.0]). The bound (<=10s) + the daemon worker thread mean a forgotten
             release.set() in a test caps any hang at ~10s and the worker dies with the process — but
             the _ControllableShutdownRecorder also uses release.wait(5.0) as a belt-and-suspenders
             safety so a test bug never hangs the suite."

# MUST READ — the file being edited (the fakes + helpers + threading idioms to REUSE)
- file: tests/test_daemon.py
  why: "REUSE: _StubRecorder (368-394: text/set_microphone/abort/shutdown), _DaemonFakeFeedback
        (353-366), _FakeBackend (395-407), _make_daemon(*, recorder=, backend=, cfg=) (427-437:
        injects _StubRecorder by default -> _models_loaded True at boot), _wait_for (417-425),
        module-level `threading` (349) + `time as _time` (350). PATTERNS: test_on_final_lock_held_
        across_type_text (575-602: Event-gated blocking + _lock.locked() probe),
        test_load_recorder_single_flight_one_build_under_concurrency (2031-2060: monkeypatch
        daemon.build_recorder + two threads + Event-gated slow build) — MIRROR these idioms."
  critical: "APPEND after test_load_recorder_single_flight_one_build_under_concurrency (currently the
             LAST test, line 2060). Do NOT add imports (threading/_time already module-level). Do NOT
             create a new file or tests/__init__.py. The blocking assertions use thread.is_alive() +
             _lock.locked() + Event probes (NOT fixed sleeps) — matches the file's deterministic style."

# MUST READ — the established load-injection pattern (monkeypatch daemon.build_recorder)
- file: tests/test_daemon.py
  why: "Tests that exercise _load_recorder against a lazy daemon monkeypatch daemon.build_recorder
        (_make_lazy_daemon + fake_build, lines 1930-2060). S2's race test uses the SAME technique so
        the FRESH post-unload load returns a distinct _StubRecorder (assert d._recorder is the fresh
        build, != the torn-down original)."
  critical: "monkeypatch.setattr(daemon, 'build_recorder', fake_build) is the seam; fake_build must
             accept (cfg, feedback, latency=None, force_cpu=False, on_speech=None) (the kwargs
             _load_recorder passes). Return a NEW _StubRecorder each call; count builds."

# THE PRD LIFECYCLE (the contract) — READ-ONLY
- docfile: PRD.md
  why: "§4.2bis: 'Teardown (idle-unload and quit) runs under the SAME single-flight lock as load, so
        an arm that races an in-flight teardown waits for it, then loads fresh — an arm can never see
        a half-torn-down recorder.' §8 risk row: the ~90s recorder.shutdown() wedge -> teardown MUST
        be bounded (clause d)."
  critical: "Do NOT edit PRD.md (forbidden). The single-flight-under-_lock guarantee + the
             no-half-torn-down-recorder invariant are the verbatim contracts these tests pin."
```

### Current Codebase tree (state at P1.M3.T1.S2 start — S1 IN PARALLEL)

> P1.M3.T1.S1 is implemented IN PARALLEL and may not have landed yet. Assume it lands EXACTLY as
> `P1M3T1S1/PRP.md` specifies (its Edit D4 is the verbatim `_unload_recorder`). These tests will be
> RED (AttributeError on `d._disarmed_monotonic` / `d._unload_recorder`) until S1 lands — that is
> expected (TDD).

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py            # ← P1.M3.T1.S1 adds _unload_recorder/_maybe_idle_unload/_disarmed_monotonic.
│   │                        #   CONSUME (read the contract); DO NOT EDIT (S1 owns it, in parallel).
│   ├── config.py            # S1 adds auto_unload_idle_seconds. READ only.
│   ├── feedback.py          # P1.M2.T2.S1 surface. READ only.
│   └── ctl.py               # P1.M2.T2.S1. READ only.
└── tests/
    └── test_daemon.py       # ← EDIT (APPEND the race-safety section). 126 tests currently; baseline GREEN.
# NO new files. NO tests/__init__.py. NO daemon.py/config.py edits.
```

### Desired Codebase tree with files to be added

```bash
tests/test_daemon.py   # MODIFIED: APPEND `# P1.M3.T1.S2 — teardown-vs-load race safety` section
                       #          (1 fake class + 1 helper + 5 tests) after the single-flight test.
# NOTHING ELSE. No new files. No daemon.py/config.py/feedback.py/ctl.py/config.toml edits. No new deps.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A TEST-ONLY SUBTASK; DO NOT EDIT daemon.py. S1 (P1.M3.T1.S1) owns
#   daemon.py and is implemented IN PARALLEL. If a test reveals an S1 bug, raise it — do NOT patch
#   the impl here. S2's ONLY edit is APPENDING to tests/test_daemon.py. (Research §5; item OUTPUT.)

# CRITICAL #2 — THE RACE TESTS REQUIRE S1 TO HAVE LANDED. They access d._disarmed_monotonic (S1's
#   __init__ field) and call d._unload_recorder() (S1's method). Until S1 lands, collection/teardown
#   raises AttributeError — that is EXPECTED (TDD RED). They turn GREEN once S1 lands. The
#   pre-existing _load_recorder/_bounded_shutdown/start/_arm/_disarm + _lock/_listening/_recorder/
#   _models_loaded attrs already exist (M1/M2 landed). (Research §1; §7.)

# CRITICAL #3 — THE BLOCKING ASSERTIONS ARE EVENT-GATED, NOT time.sleep RACES. Mirror
#   test_on_final_lock_held_across_type_text + test_load_recorder_single_flight: use threading.Event
#   (started/release) to hold the teardown/load at a known point, assert the racing arm is blocked via
#   t.is_alive() + _lock.locked() + an `armed` Event that is NOT set, THEN release. The one short
#   _time.sleep(0.15) is a clear-window probe (give the arm a chance to WRONGLY proceed), not the
#   synchronization mechanism. (Research §6.)

# CRITICAL #4 — _ControllableShutdownRecorder.shutdown() MUST release.wait(5.0), NOT release.wait()
#   (forever). A test bug that forgets release.set() must NOT hang the suite. The real _bounded_shutdown
#   caps at 10s anyway (done.wait(timeout=10.0)) and its worker thread is daemon=True (dies with the
#   process), so double-bounded. (Research §4.)

# CRITICAL #5 — _unload_recorder CALLS _bounded_shutdown() WITH NO TIMEOUT ARG (default 10.0). The
#   clause-(d) test monkeypatches d._bounded_shutdown and asserts calls == [10.0] — proving the unload
#   routes through the BOUNDED path (the same _bounded_shutdown whose <=10s cap is proven in
#   test_bounded_shutdown_force_cleans_on_timeout). Do NOT assert a different timeout. (Research §1, §3.)

# CRITICAL #6 — TO MAKE _unload_recorder PROCEED DETERMINISTICALLY, set _disarmed_monotonic = 0.0
#   (not time.monotonic()). time.monotonic() - 0.0 is huge vs the tiny positive threshold, so the time
#   re-check passes with NO sleep. auto_unload_idle_seconds must be > 0 (0 disables — would abort).
#   The helper _idle_unloaded_loaded_daemon does this. (Research §4.)

# CRITICAL #7 — CALL _disarm() UNDER THE LOCK, THEN override _disarmed_monotonic. _disarm is
#   documented "called under the lock by start/toggle"; do `with d._lock: d._disarm()` then set
#   d._disarmed_monotonic = 0.0 (outside the lock is fine — it's a test setup stamp). _disarm also
#   clears _listening (needed: _unload_recorder aborts if _listening.is_set()). (Research §4.)

# CRITICAL #8 — DO NOT CALL _load_recorder() WHILE HOLDING _lock. _load_recorder acquire-release-
#   reacquires _lock (Condition.wait must release it); nesting under the non-reentrant _lock DEADLOCKS.
#   The arm path (start()) calls _load_recorder OUTSIDE _lock. The structural test holds _lock from
#   the MAIN thread and calls _load_recorder from a WORKER thread (which blocks) — that's correct.
#   (daemon.py _load_recorder docstring; S1 research §2.1.)

# CRITICAL #9 — REUSE THE EXISTING FAKES; DO NOT REDEFINE _StubRecorder. _ControllableShutdownRecorder
#   SUBCLASSES _StubRecorder (super().__init__(); override shutdown() only). _make_daemon injects a
#   _StubRecorder by default (so _models_loaded is True at boot — the loaded state the race needs).
#   For the FRESH post-unload build, monkeypatch daemon.build_recorder to return a NEW _StubRecorder.
#   (Research §4; tests/test_daemon.py 368-437, 1930-2060.)

# CRITICAL #10 — APPEND; DO NOT CREATE A NEW FILE. The section goes at the END of tests/test_daemon.py
#   (after test_load_recorder_single_flight_one_build_under_concurrency, line 2060). No new imports
#   (threading/_time are module-level at 349-350). No tests/__init__.py (pytest discovers without it).
#   (Research §5.)

# GOTCHA #11 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always
#   `.venv/bin/python -m pytest ...` / `.venv/bin/python -m py_compile ...`. mypy NOT installed (skip).
#   ruff at /home/dustin/.local/bin/ruff is an OPTIONAL lint (not in .venv; not a gate). (Research §6.)

# GOTCHA #12 — monkeypatch.setattr(d, "_bounded_shutdown", fake) shadows the instance method for that
#   instance (sets d.__dict__["_bounded_shutdown"]); _unload_recorder's self._bounded_shutdown() then
#   calls the fake. To DELEGATE to the real one (test d), capture `real = d._bounded_shutdown` BEFORE
#   monkeypatching and call real(timeout) inside the fake. monkeypatch restores after the test.
#   (Research §3 test d.)
```

## Implementation Blueprint

### Data models and structure

No new production data model. The section adds one fake class (`_ControllableShutdownRecorder`, a
`_StubRecorder` subclass) and one helper (`_idle_unloaded_loaded_daemon`). Both are local to the test
section. No new imports (reuse module-level `threading`, `_time`, `daemon`, `VoiceTypingConfig`, and
the existing `_StubRecorder`/`_make_daemon`/`_DaemonFakeFeedback`/`_FakeBackend`/`_wait_for`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the contract + fakes exist and the target is the append site (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f tests/test_daemon.py && echo "ok: test_daemon.py exists" || echo "PREFLIGHT FAIL"
      test -f voice_typing/daemon.py && echo "ok: daemon.py exists" || echo "PREFLIGHT FAIL"
      grep -n "class _StubRecorder\|def _make_daemon\|def _wait_for\|^import threading\|import time as _time" tests/test_daemon.py
      grep -n "def _load_recorder\|def _bounded_shutdown\|def start" voice_typing/daemon.py
      grep -n "def _unload_recorder\|_disarmed_monotonic" voice_typing/daemon.py && echo "S1 LANDED" || echo "S1 NOT YET LANDED (RED expected)"
      .venv/bin/python -m pytest tests/test_daemon.py -q --no-header 2>&1 | tail -3
  - EXPECTED: test_daemon.py + daemon.py present; the fakes/helpers/imports found by grep; _load_recorder/
    _bounded_shutdown/start exist in daemon.py; _unload_recorder/_disarmed_monotonic either present
    (S1 landed -> GREEN-able) or absent (S1 pending -> RED until it lands); the baseline prints
    "126 passed".
  - DO NOT: append the section yet, edit daemon.py, run uv sync/add, or touch any other file.

Task 2: APPEND the race-safety section to tests/test_daemon.py — use the `edit` tool to add the
        verbatim block from "Task 2 SOURCE" below AFTER the last line of
        test_load_recorder_single_flight_one_build_under_concurrency (the file's current end).
  - FILE: tests/test_daemon.py
  - ANCHOR oldText: the LAST two lines of the file:
        assert built["n"] == 1           # exactly ONE build (single-flight)
        assert results == [True, True]   # both callers see success (2nd waited for the 1st)
  - newText: those same two lines (unchanged) + a blank line + the ENTIRE Task 2 SOURCE block.
  - DO NOT: edit daemon.py (Critical #1); create a new file / tests/__init__.py (Critical #10);
    re-_StubRecorder (Critical #9); call _load_recorder under _lock (Critical #8); use bare python
    (Gotcha #11).

Task 3: VALIDATE — run the Validation Loop L1 (py_compile) + L2 (pytest, the primary gate).
        Iterate until 131 passed. If S1 has NOT landed, the 5 new tests error (AttributeError on
        d._unload_recorder / d._disarmed_monotonic) — that is EXPECTED (TDD RED); they go GREEN once
        S1 lands. L3/L4 are scope guards. No git commit unless the orchestrator directs it. If asked:
        message "P1.M3.T1.S2: teardown-vs-load race-safety tests (5 tests, fakes, no CUDA)".
```

#### Task 2 SOURCE — append verbatim to `tests/test_daemon.py`

```python


# P1.M3.T1.S2 — teardown-vs-load race safety (PRD §4.2bis). Unit tests using fakes; NO CUDA.
#
# Verifies: an arm (start) racing an in-flight idle-unload teardown BLOCKS on the SAME single-flight
# self._lock the teardown holds, waits, then loads a FRESH recorder (it can never see a half-torn-down
# recorder); the wait is bounded (the teardown routes through _bounded_shutdown). Reuses _StubRecorder
# / _make_daemon / _wait_for / module-level threading + _time defined earlier in this file.


class _ControllableShutdownRecorder(_StubRecorder):
    """shutdown() blocks until `release` is set, signalling `started` on entry.

    Lets a test hold _unload_recorder() inside the REAL _bounded_shutdown() (and thus holding
    self._lock) for a controlled window, then release it. release.wait(5.0) is a belt-and-suspenders
    safety so a test bug never hangs the suite (the real _bounded_shutdown also caps at 10s and its
    worker thread is daemon=True -> dies with the process).
    """

    def __init__(self, started, release):
        super().__init__()
        self._started = started
        self._release = release

    def shutdown(self):  # type: ignore[override]
        self._started.set()           # signal: _bounded_shutdown is now running under _lock
        self._release.wait(5.0)       # bounded: never hang the suite on a forgotten release.set()
        self.shutdowns += 1


def _idle_unloaded_loaded_daemon(*, recorder=None, threshold=0.001):
    """A LOADED daemon, DISARMED, with _disarmed_monotonic far in the past + a tiny threshold.

    So _unload_recorder()'s re-check passes when called DIRECTLY (the idle-unload fire condition,
    PRD §4.2bis) WITHOUT sleeping: time.monotonic() - 0.0 is huge vs any tiny positive threshold.
    threshold must be > 0 (0 disables idle-unload -> _unload_recorder aborts).
    """
    cfg = VoiceTypingConfig()
    cfg.asr.auto_unload_idle_seconds = threshold
    d, _fb, _rec, _be = _make_daemon(recorder=recorder, cfg=cfg)
    with d._lock:
        d._disarm()                       # clears _listening; stamps _disarmed_monotonic (P1.M3.T1.S1)
        d._disarmed_monotonic = 0.0       # push the stamp far into the past -> time re-check passes NOW
    assert d._models_loaded is True
    assert d.is_listening() is False
    return d


def test_arm_racing_unload_waits_then_loads_fresh(monkeypatch):
    """Clause (a)+(b): an arm (start) racing an in-flight idle-unload teardown BLOCKS on self._lock
    until _unload_recorder releases it, then _load_recorder() builds FRESH and arms. PRD §4.2bis."""
    started = threading.Event()
    release = threading.Event()
    original = _ControllableShutdownRecorder(started, release)
    d = _idle_unloaded_loaded_daemon(recorder=original)
    assert d._recorder is original

    built = []

    def fake_build(*a, **k):
        rec = _StubRecorder()
        built.append(rec)
        return rec

    monkeypatch.setattr(daemon, "build_recorder", fake_build)

    # U: the idle-unload teardown. Acquires _lock, runs the REAL _bounded_shutdown (whose
    # done.wait blocks because recorder.shutdown() blocks on `release`) -> HOLDS _lock.
    def unload():
        d._unload_recorder()

    t_u = threading.Thread(target=unload, name="test-unload", daemon=True)
    t_u.start()
    assert started.wait(2.0), "unload never entered _bounded_shutdown (lock not held yet)"

    # S: a racing arm. start() -> _load_recorder() -> `with self._lock:` BLOCKS (U holds it).
    armed = threading.Event()

    def arm():
        d.start()
        armed.set()

    t_s = threading.Thread(target=arm, name="test-arm", daemon=True)
    t_s.start()
    _time.sleep(0.15)  # clear window: an unblocked arm would have armed by now
    assert not armed.is_set(), "arm proceeded while teardown still held the lock (race not serialized)"
    assert t_s.is_alive(), "arm thread should still be blocked on the single-flight lock"
    assert d._lock.locked(), "the single-flight lock must be held by the teardown"

    # Release the teardown -> U nulls the recorder + frees the lock -> S loads FRESH + arms.
    release.set()
    assert armed.wait(3.0), "arm did not complete after teardown released the lock"
    t_u.join(2.0)
    t_s.join(2.0)
    assert not t_u.is_alive() and not t_s.is_alive(), "threads did not finish"

    # Clause (b): a FRESH recorder is resident, models loaded, listening on.
    assert len(built) == 1, "exactly one fresh build after the unload"
    assert d._recorder is built[0], "resident recorder must be the FRESH build, not the torn-down one"
    assert d._recorder is not original, "the torn-down recorder must NOT be resident"
    assert d._models_loaded is True
    assert d.is_listening() is True


def test_recorder_never_half_torn_down_during_race(monkeypatch):
    """Clause (c): throughout the unload->reload race, self._recorder is ALWAYS either None or a
    fully-built recorder — never a partial/garbage value. CPython attribute reads are atomic; only
    None + complete build_recorder results are ever assigned."""
    started = threading.Event()
    release = threading.Event()
    d = _idle_unloaded_loaded_daemon(recorder=_ControllableShutdownRecorder(started, release))

    def fake_build(*a, **k):
        # A tiny delay WIDENS the None window (between U's _recorder=None and S's fresh assignment)
        # so the 1ms sampler reliably observes it.
        _time.sleep(0.05)
        return _StubRecorder()

    monkeypatch.setattr(daemon, "build_recorder", fake_build)

    samples = []
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            samples.append(d._recorder)   # atomic attribute read
            _time.sleep(0.001)

    t_poll = threading.Thread(target=sampler, name="test-sampler", daemon=True)
    t_poll.start()

    def unload():
        d._unload_recorder()

    threading.Thread(target=unload, name="test-unload2", daemon=True).start()
    assert started.wait(2.0)
    d.start()  # racing arm (loads fresh after the unload)
    assert _wait_for(lambda: any(r is None for r in samples), timeout=3.0), \
        "sampler never observed the torn-down None state"
    _time.sleep(0.1)  # let the reload land + the sampler observe the fresh resident recorder
    stop.set()
    t_poll.join(1.0)

    assert samples, "sampler never observed the recorder"
    for rec in samples:
        assert rec is None or (
            callable(getattr(rec, "text", None))
            and callable(getattr(rec, "set_microphone", None))
            and callable(getattr(rec, "abort", None))
            and callable(getattr(rec, "shutdown", None))
        ), f"observed a non-None, non-complete recorder: {rec!r}"
    assert any(r is None for r in samples), "never saw the torn-down None state"
    assert any(r is not None for r in samples), "never saw a resident recorder"


def test_load_and_unload_serialize_on_the_same_single_flight_lock():
    """Clause (a) mechanism: _load_recorder()'s FIRST action is `with self._lock:` — the SAME lock
    _unload_recorder() holds during teardown. So while the lock is held, a load physically CANNOT
    proceed. Proven directly, without timing."""
    d, _fb, _rec, _be = _make_daemon()  # loaded, not listening (injected _StubRecorder)
    assert d._models_loaded is True

    # Hold the single-flight lock from the test (simulating an in-flight teardown holding it).
    assert d._lock.acquire(blocking=False) is True

    proceeded = threading.Event()

    def load():
        d._load_recorder()  # first line is `with self._lock:` -> blocks here
        proceeded.set()

    t = threading.Thread(target=load, name="test-load-blocked", daemon=True)
    t.start()
    _time.sleep(0.15)
    assert not proceeded.is_set(), "_load_recorder proceeded without the single-flight lock"
    assert t.is_alive(), "load must be blocked on the lock the teardown holds"

    d._lock.release()  # teardown releases -> load proceeds (resident -> immediate True)
    assert proceeded.wait(2.0), "load did not proceed after the lock was released"
    t.join(2.0)
    assert d._models_loaded is True  # resident -> load is a no-op True


def test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded(monkeypatch):
    """Clause (d): _unload_recorder() tears down via _bounded_shutdown() (bounded <=10s; proven in
    test_bounded_shutdown_force_cleans_on_timeout). So a racing arm's wait is bounded by THAT
    teardown, never the legacy ~90s recorder.shutdown() wedge (PRD §8). Asserts routing + a bounded
    completion window."""
    d = _idle_unloaded_loaded_daemon()
    real = d._bounded_shutdown
    calls = []

    def recording_bounded(timeout=10.0):
        calls.append(timeout)
        return real(timeout)  # delegate so the recorder is actually shut down (stays hermetic)

    monkeypatch.setattr(d, "_bounded_shutdown", recording_bounded)

    start = _time.monotonic()
    d._unload_recorder()
    elapsed = _time.monotonic() - start

    assert calls == [10.0], f"_unload_recorder did not route through _bounded_shutdown(10.0): {calls}"
    assert elapsed < 2.0, f"unload took {elapsed:.2f}s (a racing arm would wait this long)"
    assert d._models_loaded is False and d._recorder is None, "unload did not complete"


def test_armed_state_aborts_unload_via_listening_recheck():
    """Reverse race (PRD §4.2bis + S1 Critical #2): if an arm wins the race to the lock, _unload_recorder's
    `_listening.is_set()` re-check (under the lock) ABORTS the unload — the armed state wins and the
    recorder stays resident. The other half of 'an arm can never see a half-torn-down recorder'."""
    d = _idle_unloaded_loaded_daemon()
    # An arm wins the race JUST BEFORE the unload acquires the lock -> listening is now ON.
    with d._lock:
        d._arm()
    assert d.is_listening() is True

    d._unload_recorder()  # re-check sees _listening.is_set() -> abort

    assert d._models_loaded is True, "unload must abort when an arm raced in (listening is on)"
    assert d._recorder is not None, "the recorder must stay resident (unload aborted)"
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — Event-gated blocking assertion (mirror test_on_final_lock_held_across_type_text):
started = threading.Event(); release = threading.Event()
# U holds _lock via the REAL _bounded_shutdown (recorder.shutdown() blocks on `release`).
assert started.wait(2.0)                      # U is inside _bounded_shutdown (lock held)
# S is the racing arm; assert it is BLOCKED, then release:
assert not armed.is_set() and t_s.is_alive()  # arm could NOT proceed
release.set(); assert armed.wait(3.0)         # after release, arm loaded fresh + armed

# PATTERN 2 — deterministic unload condition (no sleeps): _disarmed_monotonic = 0.0 + tiny threshold.
cfg.asr.auto_unload_idle_seconds = 0.001      # > 0 (0 disables)
with d._lock:
    d._disarm(); d._disarmed_monotonic = 0.0  # now - 0.0 >> 0.001 -> time re-check passes NOW

# PATTERN 3 — load injection for the FRESH post-unload build (mirror the single-flight test):
monkeypatch.setattr(daemon, "build_recorder", lambda *a, **k: built.append(_StubRecorder()) or built[-1])
# assert d._recorder is built[0] and d._recorder is not original

# PATTERN 4 — atomic-visibility probe (clause c): CPython attr reads never tear; only None + complete
# stubs are ever assigned, so every sample is None-or-full. A tiny fake_build delay widens the None
# window so the sampler reliably observes it.

# PATTERN 5 — routing proof via monkeypatch (clause d): shadow d._bounded_shutdown to RECORD the call;
# assert _unload_recorder calls it with the default 10.0 (the bounded path). Delegate to the real one
# via a captured reference (real = d._bounded_shutdown before monkeypatch).
```

### Integration Points

```yaml
TEST FILE:
  - append to: "tests/test_daemon.py (after test_load_recorder_single_flight_one_build_under_concurrency)"
  - new symbols: "_ControllableShutdownRecorder (fake class), _idle_unloaded_loaded_daemon (helper),
                  + 5 test functions (all module-level, no fixtures beyond monkeypatch)"
REUSED (no new imports):
  - fakes: "_StubRecorder, _DaemonFakeFeedback, _FakeBackend (defined earlier in this file)"
  - helpers: "_make_daemon(*, recorder=, backend=, cfg=), _wait_for(predicate, timeout, interval)"
  - module-level: "threading (line 349), time as _time (line 350), daemon, VoiceTypingConfig"
CONSUMED CONTRACT (do NOT edit — S1/landed):
  - daemon.py: "_unload_recorder (S1), _load_recorder (M2.T1), _bounded_shutdown (M1.T1.S2),
                start/_arm/_disarm (M2.T1), _lock/_listening/_recorder/_models_loaded/_disarmed_monotonic"
DEPENDENCIES: none new (stdlib threading/time + the existing pytest fakes). dev=["pytest>=9.1.1"].
```

## Validation Loop

> pytest is the gate (`.venv/bin/python`). FULL PATHS (zsh aliases). mypy NOT installed (skip). ruff
> optional (`/home/dustin/.local/bin/ruff`, NOT in `.venv`). The race tests are DETERMINISTIC
> (Event-gated), so they run in well under 1s.

### Level 1: Syntax

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f tests/test_daemon.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile tests/test_daemon.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
"$PY" -c "import ast; ast.parse(open('tests/test_daemon.py').read()); print('L1 ast.parse OK')"
# Expected: file present; py_compile OK; ast.parse OK.
```

### Level 2: Unit Tests (THE gate — 5 new tests pass; 131 total)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python

# 2a — collect first (does the section parse + are the 5 tests discovered?).
"$PY" -m pytest tests/test_daemon.py --collect-only -q 2>&1 | tail -5
# Expected: collects 131 tests (126 prior + 5 new), NO collection errors. If S1 has NOT landed,
#   COLLECTION still succeeds (the tests are module-level funcs) but RUNNING them raises
#   AttributeError on d._unload_recorder / d._disarmed_monotonic — that is EXPECTED (TDD RED);
#   re-run once S1 lands. (Confirm S1 landed: `grep -n "_unload_recorder\|_disarmed_monotonic" voice_typing/daemon.py`.)

# 2b — run just the new section.
"$PY" -m pytest tests/test_daemon.py -v -k "racing_unload or half_torn or single_flight_lock or bounded_shutdown_so_arm or aborts_unload_via_listening"
# Expected: 5 passed. If any FAIL: READ the assertion (it prints what it saw), reconcile against S1's
#   _unload_recorder (P1M3T1S1/PRP.md Edit D4), and fix the TEST (not S1 — S1 owns daemon.py; raise
#   the discrepancy if the impl diverges from its PRP).

# 2c — full test_daemon.py regression (nothing else broke).
"$PY" -m pytest tests/test_daemon.py -q
# Expected: 131 passed, 0 failed.

# 2d — whole fast suite (no regression elsewhere; test_feed_audio.py is GPU-gated — exclude it).
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed.
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
# ONLY tests/test_daemon.py changed; daemon.py untouched (S1 owns it).
git status --porcelain
# Expected: ONLY " M tests/test_daemon.py" (one modified file). Any change to voice_typing/daemon.py,
#   config.py, feedback.py, ctl.py, config.toml, PRD.md, tasks.json is a SCOPE VIOLATION.
git diff --name-only
# Expected: tests/test_daemon.py
# Confirm the section landed at the end (after the single-flight test) + no new files:
test ! -e tests/test_typing_backends_race.py && echo "L3 ok: no stray new test file"
grep -n "P1.M3.T1.S2 — teardown-vs-load race safety" tests/test_daemon.py
# Expected: one match (the section header).
```

### Level 4: Determinism / no-flake check

```bash
cd /home/dustin/projects/voice-typing
# Run the new section several times — the Event-gated design must never flake.
for i in 1 2 3 4 5; do
  .venv/bin/python -m pytest tests/test_daemon.py -q -k "racing_unload or half_torn or single_flight_lock or bounded_shutdown_so_arm or aborts_unload_via_listening" 2>&1 | tail -1
done
# Expected: "5 passed" on EVERY run (no ordering/timing dependence). If a run flakes, the offending
# test likely needs a wider clear-window or a more explicit Event handshake — but the design above
# (Event-gated, not time.sleep-synchronized) should be stable.
```

## Final Validation Checklist

### Technical Validation
- [ ] `.venv/bin/python -m py_compile tests/test_daemon.py` → exit 0.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py --collect-only -q` → 131 collected, no errors.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v -k "racing_unload or half_torn or single_flight_lock or bounded_shutdown_so_arm or aborts_unload_via_listening"` → **5 passed**.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -q` → 131 passed.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L4: 5 repeated runs of the new section → "5 passed" each time (deterministic).
- [ ] L3 scope guard: ONLY `tests/test_daemon.py` modified; daemon.py untouched.

### Feature Validation
- [ ] Clause (a): arm proven BLOCKED while teardown holds `_lock` (not armed, thread alive, `_lock.locked()`).
- [ ] Clause (b): after release, a FRESH recorder (≠ torn-down original) is resident; `_models_loaded is True`; `is_listening() is True`.
- [ ] Clause (c): every `_recorder` sample during the race is `None` or a full recorder; both observed.
- [ ] Clause (d): `_unload_recorder` calls `_bounded_shutdown(10.0)`; unload completes in < 2s.
- [ ] Mechanism: `_load_recorder()` blocks while `_lock` is held, proceeds once released.
- [ ] Reverse race: an armed daemon's `_unload_recorder()` is a no-op (recorder stays resident).
- [ ] No real CUDA / RealtimeSTT (every test uses `_StubRecorder` + `_make_daemon` + `monkeypatch`).

### Code Quality Validation
- [ ] Section header + docstrings mirror the file's style (PRD §4.2bis cross-ref; "NO CUDA" note).
- [ ] Reuses `_StubRecorder`/`_make_daemon`/`_wait_for`/`_DaemonFakeFeedback`/`_FakeBackend` (no redefinition).
- [ ] No new imports (module-level `threading`/`_time`); no new deps.
- [ ] Blocking assertions are Event-gated (not `time.sleep` races); `_ControllableShutdownRecorder.release.wait(5.0)` bounds any hang.
- [ ] Only `tests/test_daemon.py` modified; append-only (no edits to earlier tests).

### Documentation & Deployment
- [ ] Section header documents: the PRD §4.2bis contract, the fakes, the "no CUDA" guarantee, the clause each test realizes.
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none — test-only").

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/daemon.py` — S1 owns it (in parallel); this subtask is test-only. If a test reveals an impl bug, raise it, don't patch it here (Critical #1).
- ❌ Don't create a new test file or `tests/__init__.py` — APPEND to `tests/test_daemon.py` (Critical #10).
- ❌ Don't use `unittest.mock` / `pytest-mock` — the project uses stdlib `monkeypatch` exclusively; no new deps (reuse the `monkeypatch.setattr(daemon, "build_recorder", ...)` pattern).
- ❌ Don't synchronize the race with `time.sleep` — use `threading.Event` (started/release/armed) + `t.is_alive()` + `_lock.locked()` probes, mirroring `test_on_final_lock_held_across_type_text` + the single-flight test (Critical #3).
- ❌ Don't make `_ControllableShutdownRecorder.shutdown()` block forever (`release.wait()` with no timeout) — use `release.wait(5.0)` so a forgotten `release.set()` never hangs the suite (Critical #4).
- ❌ Don't assert a non-default `_bounded_shutdown` timeout — `_unload_recorder` calls it with NO arg (default 10.0); assert `calls == [10.0]` (Critical #5).
- ❌ Don't call `_load_recorder()` WHILE holding `_lock` — it acquire-release-reacquires the non-reentrant lock and deadlocks. The structural test holds `_lock` in the MAIN thread and calls `_load_recorder` from a WORKER (which blocks) (Critical #8).
- ❌ Don't re-`_StubRecorder` — subclass it (`_ControllableShutdownRecorder(_StubRecorder)`) (Critical #9).
- ❌ Don't set `auto_unload_idle_seconds = 0` — 0 disables idle-unload (`_unload_recorder` aborts). Use a tiny POSITIVE threshold + `_disarmed_monotonic = 0.0` (Critical #6).
- ❌ Don't run `mypy` (not installed) or bare `python`/`pytest` (zsh aliases) — use `.venv/bin/python -m pytest` (Gotcha #11).

---

## Confidence Score

**9/10** for one-pass success. The 5 tests + 2 helpers are ~180 lines of straightforward pytest +
`threading`, reusing fakes/helpers already proven in the same file. The CONTRACT under test (S1's
`_unload_recorder`) is pinned verbatim from `P1M3T1S1/PRP.md` (Edit D4) and mirrored in the research
table; the consumed prerequisites (`_load_recorder`/`_bounded_shutdown`/`start`) are pinned with line
numbers. The Event-gated blocking-assertion idiom is demonstrated from two existing passing tests
(`test_on_final_lock_held_across_type_text`, `test_load_recorder_single_flight_one_build_under_
concurrency`), and the fast-suite baseline (126 passed) is verified live. Each test maps to one item
clause (a)–(d) + the mechanism + the reverse race.

The −1 reserves: (a) S1 is implemented IN PARALLEL — if its landed `_unload_recorder` diverges from
the PRP (e.g. renames `_disarmed_monotonic`, calls `_bounded_shutdown(timeout=...)` with an explicit
arg, or omits the `_listening` re-check), tests 4/5 or the helper would need a one-line tweak. (b)
The clause-(c) sampler observes the `None` window via a widened (50ms) fake-build delay + 1ms polling
+ a `_wait_for` gate — deterministic in practice, but it is the one test that depends on observing a
transient state (mitigated by the explicit `_wait_for(any None)` gate before the final asserts). Both
are bounded, one-line fixes gated by the L2 pytest output, not architectural risks.
