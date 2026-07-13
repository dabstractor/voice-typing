# PRP — P1.M3.T2.S1: idle-unload lifecycle + start-level single-flight tests (fast pytest)

## Goal

**Feature Goal**: Append a committed unit-test section to `tests/test_daemon.py` (using the existing
`_StubRecorder` fake — **NO CUDA, NO RealtimeSTT**) that pins the **idle-unload lifecycle** the
preceding milestones shipped (PRD §4.2bis): `_maybe_idle_unload()` **fires** after
`auto_unload_idle_seconds` of being disarmed (→ recorder torn down, phase 'unloaded'), is a **no-op**
when listening / never-disarmed / not-loaded / threshold=0 (disabled), and is **reset** by any arm
(`_disarmed_monotonic → None`). It also fills two lifecycle gaps the P1.M2.T1.S1 section left: the
boot **phase='unloaded'** assertion and a **start()-level** single-flight test. This is a
**test-only** subtask: it produces NO production code and DUPLICATES NONE of the existing lazy-load
tests (clauses a/b/c-mechanism/d/h already exist — see Context).

**Deliverable** (ONE artifact — APPEND a section; do NOT create a new file, do NOT edit existing tests):
1. `tests/test_daemon.py` — APPEND a `# P1.M3.T2.S1 — idle-unload lifecycle + start-level single-flight`
   section at the VERY END of the file (after `test_armed_state_aborts_unload_via_listening_recheck`,
   the file's current last test, which is the P1.M3.T1.S2 race section). The section contains **9 new
   tests** + NO new helper classes (it inlines setup, mirroring the auto-stop section). Verbatim source
   in Implementation Blueprint → Task 2.

**Success Definition**:
- (a) `tests/test_daemon.py` parses; `.venv/bin/python -m pytest tests/test_daemon.py -v` → all prior
  **131** tests still pass + **9 new tests pass** (140 total), deterministically (no `time.sleep`
  races except the one start-level single-flight test, which mirrors the existing Event-gated design).
- (b) **Clause (e)** — `test_idle_unload_fires_when_disarmed_beyond_threshold`: a loaded+disarmed
  daemon with `_disarmed_monotonic = now - 1801s` → `_maybe_idle_unload()` tears the recorder down
  (`_recorder is None`, `_models_loaded is False`, `fb.phases[-1] == "unloaded"`, `rec.shutdowns == 1`).
- (c) **Clause (f)** — `test_idle_unload_disabled_when_threshold_zero`: `auto_unload_idle_seconds=0`
  → `_maybe_idle_unload()` is a no-op even with `_disarmed_monotonic = now - 9999s` (recorder stays
  resident, `rec.shutdowns == 0`).
- (d) **Clause (g)** — `test_arm_resets_idle_unload_clock`: `_arm()` clears `_disarmed_monotonic` to
  `None` (so a re-arm cancels a pending idle-unload that would otherwise fire).
- (e) **Clause (a) gap** — `test_lazy_boot_records_unloaded_phase`: a lazy boot drives
  `fb.phases[-1] == "unloaded"` (the existing boot test checks attrs but NOT phase).
- (f) **Clause (c) gap** — `test_concurrent_start_calls_build_recorder_once`: two concurrent `start()`
  calls → `build_recorder` called exactly ONCE (single-flight through the `start()` entry point; the
  existing test proves it at the `_load_recorder` level).
- (g) **Robustness guards** — `_maybe_idle_unload()` is a no-op when: within threshold, listening
  (armed), never disarmed (`_disarmed_monotonic is None`), and not loaded (lazy). (4 negative tests.)
- (h) No out-of-scope files: NO edit to `voice_typing/daemon.py` (S1/M2 own it), no new test file, no
  `tests/__init__.py`, no edits to `config.py`/`feedback.py`/`ctl.py`/`config.toml`/`PRD.md`/
  `tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps. No redefinition
  of the parallel item's `_ControllableShutdownRecorder`/`_idle_unloaded_loaded_daemon`.

## User Persona

**Target User**: None directly (test-only; item DOCS: "none"). Its "users" are the maintainer running
`pytest` and the orchestrator gating P1.M3.T2 (idle-unload fast pytest) complete.

**Use Case**: `cd voice-typing && .venv/bin/python -m pytest tests/test_daemon.py -v` → 9 new
lifecycle tests green → the idle-unload watchdog's fire/disable/reset behavior + the lazy-boot phase
are regression-proof in CI/CPU contexts, with no GPU and no 30-min idle wait.

**Pain Points Addressed**: (1) `_maybe_idle_unload()` is the user-facing VRAM-reclamation path
(P1.M3.T1.S1); without committed tests, a future refactor that flips the threshold sign, drops the
`_listening`/`_disarmed_monotonic is None` guard, or stops clearing `_disarmed_monotonic` on arm
would silently break idle-unload (either never firing → VRAM never reclaimed, or firing while armed
→ recorder torn down mid-dictation). (2) Verifying it for real needs a 30-min idle window + a GPU;
the fakes + pushed timestamps make it a sub-second deterministic pytest.

## Why

- **It is the verification gate for the idle-unload lifecycle.** P1.M3.T1.S1 ships `_maybe_idle_unload`/
  `_unload_recorder`/`_disarmed_monotonic`; P1.M3.T1.S2 (parallel) ships the teardown-vs-load RACE tests
  (via `_unload_recorder` directly). NEITHER covers `_maybe_idle_unload`'s own fire/disable/reset
  semantics — this subtask does. PRD §4.2bis pins the behavior verbatim ("threshold<=0 disables";
  "the clock starts when the mic disarms ... and resets on any arm").
- **Tests ride with the work (SOW §3).** The plan splits P1.M3.T2 into S1 (these lifecycle tests) and
  S2 (the shell-level T6 rewrite). This is the fast-pytest half.
- **Cheap, additive, GPU-free, no new deps, disjoint from S2.** Pure pytest + the existing
  `_StubRecorder`/`_make_daemon`/`_make_lazy_daemon` fakes + module-level `threading`/`_time`. The new
  section appends at the file END (after S2's section) and uses NO helper names S2 introduced — no
  collision. S1/S2 edit `daemon.py`; this subtask edits only `tests/test_daemon.py`.
- **Guards the PRD §8 risk row.** Idle-unload that fires while armed (the listening-guard regression)
  would tear the recorder down mid-dictation — exactly the half-torn-down hazard §4.2bis forbids. The
  `test_idle_unload_noop_when_listening` guard catches that.

## What

Append a `# P1.M3.T2.S1 — idle-unload lifecycle + start-level single-flight` section to the END of
`tests/test_daemon.py` containing **9 tests** (verbatim source in Task 2): one boot-phase gap-fill,
one start()-level single-flight gap-fill, one idle-unload **fire** test (+ phase + shutdown-count
assertions), four idle-unload **no-op guard** tests (within-threshold / listening / never-disarmed /
not-loaded), one **disable-at-zero** test, and one **arm-resets-clock** test. All inline their setup
(mirroring the auto-stop section at ~480-560) using `_make_daemon()`/`_make_lazy_daemon()` +
`_StubRecorder`; assertions use `fb.phases[-1]`/`d._recorder`/`d._models_loaded`/`rec.shutdowns`
(the test fakes have NO `snapshot()` — see Gotcha #5). No new imports (module-level `threading` +
`_time` already present), no new helper classes, no new deps.

### Success Criteria

- [ ] `tests/test_daemon.py` parses (`.venv/bin/python -m py_compile` + `ast.parse`).
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py --collect-only -q` → 140 collected (131 prior + 9 new), no errors.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → **140 passed**, 0 failed.
- [ ] `test_idle_unload_fires_when_disarmed_beyond_threshold`: `_disarmed_monotonic = now-1801` → after `_maybe_idle_unload()`, `_recorder is None`, `_models_loaded is False`, `fb.phases[-1] == "unloaded"`, `rec.shutdowns == 1`.
- [ ] `test_idle_unload_disabled_when_threshold_zero`: `auto_unload_idle_seconds=0` → `_maybe_idle_unload()` no-op (recorder resident, `rec.shutdowns == 0`) even at `now-9999`.
- [ ] `test_arm_resets_idle_unload_clock`: after `start()` (re-arm), `_disarmed_monotonic is None`; a pending unload is cancelled (recorder stays resident).
- [ ] `test_lazy_boot_records_unloaded_phase`: lazy boot → `fb.phases[-1] == "unloaded"`.
- [ ] `test_concurrent_start_calls_build_recorder_once`: two concurrent `start()` → exactly ONE `build_recorder`; `_models_loaded True`; `is_listening() True`.
- [ ] The 4 no-op guards pass (within-threshold / listening / never-disarmed / not-loaded).
- [ ] ONLY `tests/test_daemon.py` modified (`git status --short` shows only that file); appended at END (after the P1.M3.T1.S2 section).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the CONTRACT under test (`_maybe_idle_unload`'s
lock-free pre-check + disable + delegate; `_arm`/`_disarm`'s `_disarmed_monotonic` clear/stamp; the
boot phase) is pinned from `voice_typing/daemon.py` with exact line numbers (research §3) and is
ALREADY LANDED (M2.T1.S1 + M3.T1.S1 are Complete); the **already-covered** clauses (a/b/c-mechanism/
d/h) are listed with their existing test names + line numbers so nothing is duplicated (research §1);
the setup idiom (inline, mirroring the auto-stop section) is demonstrated (research §4); the test-fake
limitation (no `snapshot()` → use `fb.phases`/attrs) is pinned (research §5); the coordination with
the parallel S2 item (append at END, avoid its helper names) is pinned (research §6); the verbatim
9-test source is in Implementation Blueprint → Task 2. The fast-suite baseline (131 passed) is verified
live.

### Documentation & References

```yaml
# MUST READ — the behavior spec (the contract these tests pin)
- docfile: PRD.md
  why: "§4.2bis Idle unload: 'when the recorder has sat in loaded/not-listening for
        auto_unload_idle_seconds (default 1800.0=30min; 0 disables), it tears the recorder down ...
        transitions to unloaded, and frees the ~1.5-3GB VRAM. The clock starts when the mic disarms
        ... and resets on any arm; time spent listening does not count.' §4.2bis concurrency: the
        lock-free pre-check + the under-lock re-check (incl. _listening). §8 risk row: idle-unload
        must not fire while armed (the listening guard). §7 acceptance #9: after
        auto_unload_idle_seconds of disarmed idle, the recorder unloads (~0 VRAM)."
  critical: "Do NOT edit PRD.md (forbidden). threshold<=0 DISABLES (never fires). The clock resets on
             ANY arm (_disarmed_monotonic -> None). _maybe_idle_unload must be a no-op while LISTENING
             (armed) — firing then would tear the recorder down mid-dictation."

# MUST READ — the contract under test (already-landed daemon methods). READ, do NOT edit.
- file: voice_typing/daemon.py
  why: "_maybe_idle_unload (793-815): threshold=cfg.asr.auto_unload_idle_seconds; threshold<=0 -> return;
        lock-free pre-check (not _models_loaded OR _listening.is_set() OR _disarmed_monotonic is None OR
        now-_disarmed_monotonic<threshold) -> return; else _unload_recorder(). _unload_recorder (818-855):
        with _lock re-check -> _bounded_shutdown() + _recorder=None/_models_loaded=False/set_phase(
        'unloaded'). _arm (699-707): _disarmed_monotonic=None. _disarm (709-728): _disarmed_monotonic=
        time.monotonic(). __init__ (457-469): _models_loaded=recorder is not None; set_phase('idle' if
        recorder else 'unloaded'). These EXACT attrs/lines the tests read/set."
  critical: "Do NOT edit daemon.py (test-only subtask). The tests set d._disarmed_monotonic directly
             (a float) to push the clock deterministically — mirrors how the auto-stop tests set
             d._last_speech_monotonic. _maybe_idle_unload's pre-check is LOCK-FREE (atomic reads)."

# MUST READ — this task's research (already-covered clauses + new-work table + setup idiom + fake limit)
- docfile: plan/003_27d1f88f5a9f/P1M3T2S1/research/lifecycle_idle_unload_tests.md
  why: "§1 the ALREADY-COVERED clauses (a/b/c-mechanism/d/h) with existing test names+lines — DO NOT
        duplicate. §2 the 9 NEW tests mapped to clauses + their auto-stop mirrors. §3 the daemon API
        contracts with line numbers. §4 the inline setup idiom (no new helper). §5 the fake limitation
        (no snapshot() -> fb.phases + attrs). §6 coordination with S2 (append at END, avoid its names).
        §7 tooling + the rec.shutdowns assertion safety."
  section: "ALL load-bearing. §1 (avoid dup), §3 (contract), §4 (idiom), §5 (assert via fb.phases),
            §6 (append point + names to avoid)."

# MUST READ — the file being edited: the fakes/helpers/patterns to REUSE + the append point
- file: tests/test_daemon.py
  why: "REUSE: _StubRecorder (368-394: text/set_microphone/abort/shutdown; shutdown does self.shutdowns
        += 1), _DaemonFakeFeedback (353-366: records phases/finals/listening_states/partials; set_models
        loaded is a no-op — NO snapshot()), _FakeBackend (395-407), _make_daemon(*, recorder=, backend=,
        cfg=) (427-437: injects _StubRecorder -> _models_loaded True at boot), _make_lazy_daemon(cfg=)
        (1911: recorder=None -> _models_loaded False), _wait_for (417-425), module-level threading (349)
        + time as _time (350). PATTERNS: the auto-stop section (~480-560: inline _make_daemon -> d.start
        -> set _last_speech_monotonic -> _maybe_auto_stop) is the EXACT template for the idle-unload
        tests (set _disarmed_monotonic instead). The single-flight test (~2031) is the template for the
        start()-level single-flight test."
  critical: "APPEND at the VERY END (after test_armed_state_aborts_unload_via_listening_recheck, line
             ~2281 — the last test of the P1.M3.T1.S2 section). Do NOT add imports (threading/_time are
             module-level). Do NOT create a new file / tests/__init__.py. Do NOT redefine S2's
             _ControllableShutdownRecorder (2071) / _idle_unloaded_loaded_daemon (2091). Assert via
             fb.phases[-1] / d._recorder / d._models_loaded / rec.shutdowns — NEVER d.status_snapshot()
             (the fakes lack snapshot())."

# MUST READ — the already-covered lazy-load section (so the new tests are NON-duplicative)
- file: tests/test_daemon.py
  why: "The P1.M2.T1.S1 'lazy load' section (~1905-2060) already has: test_lazy_daemon_boots_unloaded_
        with_no_recorder (boot attrs — but NOT phase), test_start_on_lazy_daemon_triggers_load_then_arms
        (b), test_load_recorder_single_flight_one_build_under_concurrency (c at _load_recorder level),
        test_load_recorder_total_failure_stays_unloaded + test_start_suppressed_when_load_fails (d),
        test_injected_recorder_is_loaded_at_construction (h). The NEW tests fill the GAPS (phase; start
        -level single-flight) + add the idle-unload lifecycle (e/f/g) — they are ADDITIVE, not redundant."
  critical: "Do NOT re-test boot attrs / load-success / _load_recorder-level single-flight / load-failure
             / injected-recorder — they exist. The new boot test asserts PHASE only (the gap); the new
             single-flight test goes through start() (the gap)."

# MUST READ — the parallel item's PRP (coordination: S2's section + names are in-file)
- file: plan/003_27d1f88f5a9f/P1M3T1S2/PRP.md
  why: "S2 (teardown-vs-load race safety) has LANDED: its section is at test_daemon.py:2063, its 5
        tests end the file at ~2281, and it introduced _ControllableShutdownRecorder + _idle_unloaded_
        loaded_daemon. This subtask's section goes AFTER S2's (file END) and uses NEITHER name. S2 tests
        _unload_recorder() directly (race); this subtask tests _maybe_idle_unload() (lifecycle) —
        disjoint."
  critical: "Append AFTER S2's last test (test_armed_state_aborts_unload_via_listening_recheck). Use a
             DIFFERENT section header + inline setup (no _idle_unloaded_loaded_daemon). The two sections
             coexist in one file."

# Background — the idle-unload implementation contract (S1, already Complete)
- file: plan/003_27d1f88f5a9f/P1M3T1S1/PRP.md
  why: "Pins _maybe_idle_unload/_unload_recorder/_disarmed_monotonic/auto_unload_idle_seconds verbatim
        (the Edit that landed). Confirms threshold<=0 disables, _arm clears _disarmed_monotonic, _disarm
        stamps it, and the under-lock _listening re-check."
  critical: "The implementation is LANDED (Complete). These tests verify it; they are not TDD-RED."
```

### Current Codebase tree (state at P1.M3.T2.S1 start)

P1.M2.T1.S1 (lazy load) + P1.M3.T1.S1 (idle-unload impl) + P1.M3.T1.S2 (race tests) are ALL LANDED.
`tests/test_daemon.py` currently collects **131 tests** (GREEN).

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py            # LANDED: _maybe_idle_unload/_unload_recorder/_disarmed_monotonic (M3.T1.S1)
│   │                        #   + _load_recorder/_arm/_disarm/start (M2.T1.S1). CONSUME (read); DO NOT EDIT.
│   ├── config.py            # LANDED: AsrConfig.auto_unload_idle_seconds=1800.0 (line 60). READ only.
│   ├── feedback.py          # LANDED. READ only.
│   └── ctl.py               # LANDED. READ only.
└── tests/
    └── test_daemon.py       # ← EDIT (APPEND the lifecycle section at the END). 131 tests currently; GREEN.
                              #   S2's race section is at :2063 (ends file at ~2281). Append AFTER it.
# NO new files. NO tests/__init__.py. NO daemon.py/config.py/feedback.py/ctl.py edits. No new deps.
```

### Desired Codebase tree with files to be added

```bash
tests/test_daemon.py   # MODIFIED: APPEND `# P1.M3.T2.S1 — idle-unload lifecycle + start-level
                       #          single-flight` section (9 tests, no new helpers) at the file END.
# NOTHING ELSE. No new files. No daemon.py/config.py/feedback.py/ctl.py/config.toml edits. No new deps.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A TEST-ONLY SUBTASK; DO NOT EDIT daemon.py. M2.T1.S1 + M3.T1.S1 own the
#   implementation and it is LANDED. If a test reveals an impl bug, raise it — do NOT patch the impl
#   here. This subtask's ONLY edit is APPENDING to tests/test_daemon.py. (Research §0; item OUTPUT.)

# CRITICAL #2 — DO NOT DUPLICATE THE EXISTING LAZY-LOAD TESTS. Clauses (a-boot attrs)/(b)/(c at
#   _load_recorder level)/(d)/(h) ALREADY EXIST in the P1.M2.T1.S1 section (~1905-2060). The NEW
#   tests fill GAPS (boot PHASE; start()-level single-flight) + add the idle-unload lifecycle (e/f/g)
#   which has NO existing test. Re-testing boot attrs / load-success / load-failure would be a scope
#   error. (Research §1; cite the existing tests, don't rewrite them.)

# CRITICAL #3 — ASSERT VIA fb.phases[-1] / d._recorder / d._models_loaded / rec.shutdowns — NEVER
#   d.status_snapshot(). The test fakes (_DaemonFakeFeedback/_FakeFeedback) have NO snapshot() method
#   (verified: grep "def snapshot" tests/test_daemon.py -> none). status_snapshot() calls
#   self._feedback.snapshot() -> AttributeError on these fakes. status_snapshot is tested separately
#   (lines 969-997 via _make_daemon_with_feedback, which wires a feedback WITH snapshot). fb.phases
#   records every set_phase call (boot->'unloaded'/'idle'; _unload_recorder->'unloaded'). (Research §5.)

# CRITICAL #4 — APPEND AT THE VERY END; DO NOT COLLIDE WITH S2. The P1.M3.T1.S2 race section is at
#   test_daemon.py:2063 and ENDS the file (~2281, last test test_armed_state_aborts_unload_via_
#   listening_recheck). Append AFTER it. Do NOT redefine S2's _ControllableShutdownRecorder (2071) or
#   _idle_unloaded_loaded_daemon (2091) — use a different section header + INLINE setup (no new helper
#   class), mirroring the auto-stop section. (Research §6.)

# CRITICAL #5 — THE IDLE-UNLOAD FIRE SETUP IS: start() then stop() then push _disarmed_monotonic.
#   _make_daemon() injects a _StubRecorder (_models_loaded True). d.start() ARMS (_disarmed_monotonic
#   -> None). d.stop() DISARMS (_disarmed_monotonic -> now). Then set d._disarmed_monotonic =
#   _time.monotonic() - 1801.0 to push it past the 1800s default. This mirrors the auto-stop tests
#   setting d._last_speech_monotonic. NO sleeps. (Research §4; daemon.py _arm 699-707 / _disarm 709-728.)

# CRITICAL #6 — threshold<=0 DISABLES; USE A POSITIVE THRESHOLD FOR THE FIRE TEST. The default
#   auto_unload_idle_seconds=1800.0 (>0) works for the fire test (push _disarmed_monotonic to now-1801).
#   For the DISABLE test set auto_unload_idle_seconds=0.0 and assert the recorder STAYS resident even
#   at now-9999. NEVER set threshold=0 in a test that expects an unload to fire. (PRD §4.2bis; daemon.py
#   _maybe_idle_unload 805.)

# CRITICAL #7 — _maybe_idle_unload IS LOCK-FREE + DELEGATES; TEST IT DIRECTLY. The pre-check reads
#   _models_loaded/_listening/_disarmed_monotonic atomically (CPython), then calls _unload_recorder
#   (which takes _lock). For the lifecycle tests, call d._maybe_idle_unload() DIRECTLY (like the
#   auto-stop tests call d._maybe_auto_stop()). Do NOT start the _idle_unload_watchdog thread (that
#   needs real timing); the direct call is deterministic. (daemon.py 793-815; research §3.)

# CRITICAL #8 — _unload_recorder (via _maybe_idle_unload) CALLS _bounded_shutdown -> rec.shutdown().
#   _StubRecorder.shutdown() does self.shutdowns += 1 and returns INSTANTLY, so _bounded_shutdown's
#   done.wait(10.0) returns immediately (the timeout/force-cleanup path that touches transcript_process/
#   reader_process is NEVER hit). So after a fire, rec.shutdowns == 1 is a SAFE, correct assertion
#   (proven by S2's test_unload_routes_through_bounded_shutdown... using the same fake). (Research §7.)

# CRITICAL #9 — REUSE THE EXISTING FAKES; NO NEW HELPER CLASS. _make_daemon (loaded) + _make_lazy_daemon
#   (unloaded) + _StubRecorder + _DaemonFakeFeedback cover every test. The setup is inlined per-test
#   (mirrors the auto-stop section). Do NOT add _idle_unloaded_loaded_daemon (S2's name) or any other
#   module-level helper. (Research §4, §6.)

# CRITICAL #10 — THE START()-LEVEL SINGLE-FLIGHT TEST MIRRORS THE EXISTING _load_recorder ONE. Use
#   threading.Event (started/release) to make the build slow so the 2nd start() arrives while _loading;
#   release.wait(2.0) (bounded) so a forgotten release.set() never hangs. monkeypatch
#   daemon.build_recorder. Assert built["n"]==1 + d.is_listening() True (the arm path). (Research §2;
#   tests/test_daemon.py ~2031.)

# GOTCHA #11 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always
#   `.venv/bin/python -m pytest ...` / `.venv/bin/python -m py_compile ...`. mypy NOT installed (skip).
#   ruff at /home/dustin/.local/bin/ruff is an OPTIONAL lint (not in .venv; not a gate). (Research §7.)

# GOTCHA #12 — DO NOT CREATE tests/__init__.py. pytest discovers test_*.py without it (131 already
#   collect). Adding it changes import semantics. (Sibling tasks.)

# GOTCHA #13 — auto_unload_idle_seconds lives on AsrConfig (cfg.asr.auto_unload_idle_seconds), NOT on a
#   top-level [idle] section. Set it via cfg = VoiceTypingConfig(); cfg.asr.auto_unload_idle_seconds = X.
#   (config.py line 60.)
```

## Implementation Blueprint

### Data models and structure

No new production data model and NO new test helper class. The section is 9 module-level test
functions that reuse `_make_daemon()` / `_make_lazy_daemon()` / `_StubRecorder` /
`_DaemonFakeFeedback` / `_FakeBackend` / `_wait_for` / module-level `threading` + `_time` (all
defined earlier in `tests/test_daemon.py`). No new imports.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the contract + fakes + append point (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f tests/test_daemon.py && echo "ok: test_daemon.py exists" || echo "PREFLIGHT FAIL"
      test -f voice_typing/daemon.py && echo "ok: daemon.py exists" || echo "PREFLIGHT FAIL"
      grep -n "def _StubRecorder\|def _make_daemon\|def _make_lazy_daemon\|def _wait_for\|^import threading\|import time as _time" tests/test_daemon.py
      grep -n "def _maybe_idle_unload\|_disarmed_monotonic\|def _arm\b\|def _disarm\b" voice_typing/daemon.py
      grep -n "auto_unload_idle_seconds" voice_typing/config.py
      grep -n "_ControllableShutdownRecorder\|_idle_unloaded_loaded_daemon\|P1.M3.T1.S2" tests/test_daemon.py && echo "S2 section present (append AFTER it)"
      tail -2 tests/test_daemon.py
      .venv/bin/python -m pytest tests/test_daemon.py -q --no-header 2>&1 | tail -2
  - EXPECTED: test_daemon.py + daemon.py present; the fakes/helpers/imports found by grep; _maybe_idle_unload
    /_disarmed_monotonic/_arm/_disarm present in daemon.py (M3.T1.S1 LANDED); auto_unload_idle_seconds in
    config.py; S2's section present (append after it); the baseline prints "131 passed".
  - DO NOT: append the section yet, edit daemon.py, run uv sync/add, or touch any other file.

Task 2: APPEND the lifecycle section to tests/test_daemon.py — use the `edit` tool to add the
        verbatim block from "Task 2 SOURCE" below AFTER the LAST two lines of the file:
            assert d._models_loaded is True, "unload must abort when an arm raced in (listening is on)"
            assert d._recorder is not None, "the recorder must stay resident (unload aborted)"
        (anchor oldText = those two lines; newText = those two lines UNCHANGED + blank line + the
        ENTIRE Task 2 SOURCE block).
  - FILE: tests/test_daemon.py
  - DO NOT: edit daemon.py (Critical #1); duplicate existing lazy-load tests (Critical #2); call
    d.status_snapshot() (Critical #3); insert before S2's section or reuse its helper names (Critical
    #4); use threshold=0 in a fire test (Critical #6); create a new file / tests/__init__.py (Gotcha
    #12); use bare python (Gotcha #11).

Task 3: VALIDATE — run the Validation Loop L1 (py_compile) + L2 (pytest, the primary gate).
        Iterate until 140 passed. L3 is the scope guard; L4 the determinism check. No git commit
        unless the orchestrator directs it. If asked: message "P1.M3.T2.S1: idle-unload lifecycle +
        start-level single-flight tests (9 tests, fakes, no CUDA)".
```

#### Task 2 SOURCE — append verbatim to `tests/test_daemon.py`

```python


# ===========================================================================
# P1.M3.T2.S1 — idle-unload lifecycle + start-level single-flight (PRD §4.2bis)
# Unit tests using the existing _StubRecorder fake — NO CUDA, NO RealtimeSTT.
#
# Pins _maybe_idle_unload()'s fire/disable/reset behavior (P1.M3.T1.S1):
#   (e) FIRES after auto_unload_idle_seconds DISARMED -> recorder torn down, phase 'unloaded';
#   (f) threshold<=0 DISABLES (no-op even when absurdly past);
#   (g) any _arm() RESETS the idle-unload clock (_disarmed_monotonic -> None).
# Plus two lifecycle gap-fills the P1.M2.T1.S1 section left:
#   (a) lazy boot drives phase='unloaded' (existing boot test checks attrs, not phase);
#   (c) two concurrent start() calls build the recorder exactly ONCE (existing is _load_recorder-level).
# Mirrors the auto-stop section (~480-560): inline setup, direct _maybe_idle_unload() call, pushed
# _disarmed_monotonic timestamp. Asserts via fb.phases[-1] / d._recorder / d._models_loaded /
# rec.shutdowns (the fakes have NO snapshot() — do NOT call d.status_snapshot() here).
# ===========================================================================


def test_lazy_boot_records_unloaded_phase():
    """Clause (a) gap: a lazy boot (recorder=None) drives the lifecycle phase to 'unloaded'.
    The existing test_lazy_daemon_boots_unloaded_with_no_recorder checks _recorder/_models_loaded/
    _loading/_load_error but NOT the phase — this pins it (the §4.2bis boot state)."""
    d, fb = _make_lazy_daemon()
    assert d._recorder is None
    assert d._models_loaded is False
    assert fb.phases[-1] == "unloaded"   # __init__ -> feedback.set_phase("unloaded") for a lazy boot


def test_concurrent_start_calls_build_recorder_once(monkeypatch):
    """Clause (c) gap: two concurrent start() calls build the recorder EXACTLY ONCE (single-flight
    through the start() entry point). The existing test_load_recorder_single_flight_one_build_under_
    concurrency proves it at the _load_recorder level; this proves start()'s load-then-arm does not
    undermine it (and both calls arm)."""
    d, _fb = _make_lazy_daemon()
    built = {"n": 0}
    started = threading.Event()
    release = threading.Event()

    def fake_build(cfg, feedback, latency=None, force_cpu=False, on_speech=None):
        built["n"] += 1
        started.set()
        release.wait(2.0)            # slow the build so the 2nd start() arrives while _loading
        return _StubRecorder()

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    errors = []

    def starter():
        try:
            d.start()
        except Exception as exc:        # never swallow silently — surface to the test
            errors.append(exc)

    t1 = threading.Thread(target=starter, name="test-start-a", daemon=True)
    t2 = threading.Thread(target=starter, name="test-start-b", daemon=True)
    t1.start()
    assert started.wait(2.0), "first start() never entered build_recorder"
    t2.start()
    release.set()                      # let the in-flight load finish
    t1.join(2.0)
    t2.join(2.0)
    assert not errors, errors
    assert built["n"] == 1, f"single-flight violated: {built['n']} builds under two concurrent start()s"
    assert d._models_loaded is True
    assert d.is_listening() is True    # armed (both starts armed; the load is shared)


# --- idle-unload lifecycle: _maybe_idle_unload() fire / disable / reset (PRD §4.2bis) ---
# Mirrors the auto-stop section: inline _make_daemon() -> start() -> stop() -> push
# _disarmed_monotonic into the past -> _maybe_idle_unload(). Default auto_unload_idle_seconds=1800.0.


def test_idle_unload_fires_when_disarmed_beyond_threshold():
    """Clause (e): after auto_unload_idle_seconds (default 1800) DISARMED, _maybe_idle_unload() tears
    the recorder down -> _recorder None, _models_loaded False, phase 'unloaded' (PRD §4.2bis)."""
    d, fb, rec, _be = _make_daemon()                       # injected _StubRecorder -> loaded
    d.start()                                              # arm  -> _disarmed_monotonic = None
    d.stop()                                               # disarm -> _disarmed_monotonic = now
    d._disarmed_monotonic = _time.monotonic() - 1801.0     # past the 1800s default threshold
    d._maybe_idle_unload()
    assert d._recorder is None                             # torn down
    assert d._models_loaded is False
    assert fb.phases[-1] == "unloaded"                     # _unload_recorder drove phase to 'unloaded'
    assert rec.shutdowns == 1                              # the recorder was shut down via _bounded_shutdown


def test_idle_unload_keeps_resident_within_threshold():
    """Clause (e) negative: well WITHIN the threshold -> _maybe_idle_unload() is a no-op (resident)."""
    d, _fb, rec, _be = _make_daemon()
    d.start()
    d.stop()
    d._disarmed_monotonic = _time.monotonic() - 100.0      # 100s << 1800s default
    d._maybe_idle_unload()
    assert d._recorder is rec
    assert d._models_loaded is True
    assert rec.shutdowns == 0


def test_idle_unload_disabled_when_threshold_zero():
    """Clause (f): auto_unload_idle_seconds=0 DISABLES idle-unload -> no-op even when absurdly past
    (PRD §4.2bis '0 disables'). The recorder MUST stay resident."""
    cfg = VoiceTypingConfig()
    cfg.asr.auto_unload_idle_seconds = 0.0
    d, _fb, rec, _be = _make_daemon(cfg=cfg)
    d.start()
    d.stop()
    d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire, but 0 disables
    d._maybe_idle_unload()
    assert d._recorder is rec                              # stayed resident
    assert d._models_loaded is True
    assert rec.shutdowns == 0


def test_idle_unload_noop_when_listening():
    """Guard: _maybe_idle_unload() MUST NOT fire while LISTENING (armed) — firing then would tear the
    recorder down mid-dictation (the §4.2bis / §8 half-torn-down hazard). The _listening.is_set() guard
    in the lock-free pre-check aborts it."""
    d, _fb, rec, _be = _make_daemon()
    d.start()                                              # armed -> listening ON
    d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire by time alone...
    d._maybe_idle_unload()
    assert d._recorder is rec                              # ...but listening aborts the unload
    assert d._models_loaded is True
    assert d.is_listening() is True


def test_idle_unload_noop_when_never_disarmed():
    """Guard: at boot _disarmed_monotonic is None (never disarmed) -> _maybe_idle_unload() is a clean
    no-op (no error, recorder resident)."""
    d, _fb, rec, _be = _make_daemon()                      # boot: _disarmed_monotonic is None
    assert d._disarmed_monotonic is None
    d._maybe_idle_unload()
    assert d._recorder is rec
    assert d._models_loaded is True


def test_idle_unload_noop_when_not_loaded():
    """Guard: a LAZY daemon (no recorder resident) -> _maybe_idle_unload() is a no-op (nothing to
    unload; the not-_models_loaded guard short-circuits)."""
    d, _fb = _make_lazy_daemon()                           # lazy: _models_loaded False, _recorder None
    d._disarmed_monotonic = _time.monotonic() - 9999.0
    d._maybe_idle_unload()
    assert d._recorder is None                             # still nothing resident
    assert d._models_loaded is False


def test_arm_resets_idle_unload_clock():
    """Clause (g): any _arm() RESETS the idle-unload clock (_disarmed_monotonic -> None), so a re-arm
    CANCELS a pending idle-unload that would otherwise fire (PRD §4.2bis 'resets on any arm')."""
    d, _fb, rec, _be = _make_daemon()
    d.start()                                              # arm -> _disarmed_monotonic = None
    assert d._disarmed_monotonic is None
    d.stop()                                               # disarm -> stamps _disarmed_monotonic
    assert d._disarmed_monotonic is not None
    d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire...
    d.start()                                              # ...but a re-arm RESETS the clock
    assert d._disarmed_monotonic is None                   # armed -> idle-unload clock inactive
    # The reset cancels the pending unload: _maybe_idle_unload is now a no-op.
    d._maybe_idle_unload()
    assert d._recorder is rec                              # stayed resident (arm reset cancelled it)
    assert d._models_loaded is True
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — idle-unload fire setup (mirror the auto-stop section; NO sleeps, NO helper):
d, fb, rec, _be = _make_daemon()                       # injected _StubRecorder -> _models_loaded True
d.start()                                              # arm  -> _disarmed_monotonic = None
d.stop()                                               # disarm -> _disarmed_monotonic = now
d._disarmed_monotonic = _time.monotonic() - 1801.0     # push past the 1800s default threshold
d._maybe_idle_unload()
assert d._recorder is None and d._models_loaded is False
assert fb.phases[-1] == "unloaded" and rec.shutdowns == 1

# PATTERN 2 — disable test: threshold=0 short-circuits BEFORE the time check (recorder stays resident).
cfg.asr.auto_unload_idle_seconds = 0.0
d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire, but 0 disables
d._maybe_idle_unload()
assert d._recorder is rec and rec.shutdowns == 0

# PATTERN 3 — arm resets the clock: _arm() sets _disarmed_monotonic = None (cancels a pending unload).
d.stop(); d._disarmed_monotonic = _time.monotonic() - 9999.0   # would fire...
d.start()                                              # ...re-arm resets -> _disarmed_monotonic is None
d._maybe_idle_unload(); assert d._recorder is rec     # stayed resident (unload cancelled)

# PATTERN 4 — assert via fb.phases[-1] / attrs, NEVER d.status_snapshot() (fakes lack snapshot()).
assert fb.phases[-1] == "unloaded"                     # the fake records every set_phase call
assert d._recorder is None and d._models_loaded is False

# PATTERN 5 — start()-level single-flight (mirror the existing _load_recorder single-flight test):
started, release = threading.Event(), threading.Event()
def fake_build(*a, **k): started.set(); release.wait(2.0); return _StubRecorder()
monkeypatch.setattr(daemon, "build_recorder", fake_build)
# two concurrent d.start() -> built["n"] == 1 (single-flight) + d.is_listening() True (armed)
```

### Integration Points

```yaml
TEST FILE:
  - append to: "tests/test_daemon.py (at the VERY END, after test_armed_state_aborts_unload_via_listening_recheck)"
  - new symbols: "9 module-level test functions (NO new helper class, NO new imports)"
REUSED (no new imports):
  - fakes: "_StubRecorder, _DaemonFakeFeedback, _FakeBackend (defined earlier in this file)"
  - helpers: "_make_daemon(*, recorder=, backend=, cfg=) (loaded), _make_lazy_daemon(cfg=) (unloaded),
              _wait_for(predicate, timeout, interval)"
  - module-level: "threading (line 349), time as _time (line 350), daemon, VoiceTypingConfig"
CONSUMED CONTRACT (do NOT edit — LANDED):
  - daemon.py: "_maybe_idle_unload (M3.T1.S1), _unload_recorder (M3.T1.S1), _bounded_shutdown (M1.T1.S2),
                _load_recorder/_arm/_disarm/start (M2.T1.S1), _lock/_listening/_recorder/_models_loaded/
                _disarmed_monotonic"
  - config.py: "AsrConfig.auto_unload_idle_seconds (default 1800.0; 0 disables)"
DEPENDENCIES: none new (stdlib threading/time + the existing pytest fakes). dev=["pytest>=9.1.1"].
```

## Validation Loop

> pytest is the gate (`.venv/bin/python`). FULL PATHS (zsh aliases). mypy NOT installed (skip). ruff
> optional (`/home/dustin/.local/bin/ruff`, NOT in `.venv`). The 8 lifecycle tests are SINGLE-THREADED
> + deterministic (pushed timestamps, no sleeps); the 1 start-level single-flight test mirrors the
> existing Event-gated single-flight design.

### Level 1: Syntax

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f tests/test_daemon.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile tests/test_daemon.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
"$PY" -c "import ast; ast.parse(open('tests/test_daemon.py').read()); print('L1 ast.parse OK')"
# Expected: file present; py_compile OK; ast.parse OK.
```

### Level 2: Unit Tests (THE gate — 9 new tests pass; 140 total)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python

# 2a — collect first (does the section parse + are the 9 tests discovered?).
"$PY" -m pytest tests/test_daemon.py --collect-only -q 2>&1 | tail -3
# Expected: collects 140 tests (131 prior + 9 new), NO collection errors.

# 2b — run just the new section.
"$PY" -m pytest tests/test_daemon.py -v -k "lazy_boot_records_unloaded_phase or concurrent_start_calls_build_recorder_once or idle_unload_fires_when_disarmed or idle_unload_keeps_resident_within or idle_unload_disabled_when_threshold_zero or idle_unload_noop_when_listening or idle_unload_noop_when_never_disarmed or idle_unload_noop_when_not_loaded or arm_resets_idle_unload_clock"
# Expected: 9 passed. If any FAIL: READ the assertion (it prints what it saw), reconcile against the
#   daemon's _maybe_idle_unload/_arm/_disarm (voice_typing/daemon.py 699-815) + the PRD §4.2bis contract,
#   and fix the TEST (not daemon.py — this is test-only; raise the discrepancy if the impl diverges).

# 2c — full test_daemon.py regression (nothing else broke — esp. S2's race tests + the lazy-load section).
"$PY" -m pytest tests/test_daemon.py -q
# Expected: 140 passed, 0 failed.

# 2d — whole fast suite (no regression elsewhere; test_feed_audio.py is GPU-gated — exclude it).
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed.
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
# ONLY tests/test_daemon.py changed; daemon.py untouched.
git status --porcelain
# Expected: ONLY " M tests/test_daemon.py" (one modified file). Any change to voice_typing/daemon.py,
#   config.py, feedback.py, ctl.py, config.toml, PRD.md, tasks.json is a SCOPE VIOLATION.
git diff --name-only
# Expected: tests/test_daemon.py
# Confirm the section landed at the END (after S2's section) + no new files / helpers:
test ! -e tests/__init__.py && echo "L3 ok: no tests/__init__.py" || echo "L3 FAIL: __init__.py created"
grep -n "P1.M3.T2.S1 — idle-unload lifecycle" tests/test_daemon.py
# Expected: one match (the section header), at a line number AFTER the P1.M3.T1.S2 header (line 2063).
# Confirm no name collision with S2's helpers:
test "$(grep -c 'class _ControllableShutdownRecorder' tests/test_daemon.py)" -eq 1 && echo "L3 ok: did not redefine _ControllableShutdownRecorder" || echo "L3 FAIL"
test "$(grep -c 'def _idle_unloaded_loaded_daemon' tests/test_daemon.py)" -eq 1 && echo "L3 ok: did not redefine _idle_unloaded_loaded_daemon" || echo "L3 FAIL"
```

### Level 4: Determinism / no-flake check

```bash
cd /home/dustin/projects/voice-typing
# Run the new section several times — the lifecycle tests must never flake.
for i in 1 2 3 4 5; do
  .venv/bin/python -m pytest tests/test_daemon.py -q -k "idle_unload or arm_resets_idle_unload or lazy_boot_records_unloaded or concurrent_start_calls_build_recorder" 2>&1 | tail -1
done
# Expected: "9 passed" on EVERY run (no ordering/timing dependence). The lifecycle tests use pushed
# timestamps (deterministic); the single start()-level test is Event-gated (mirrors the existing
# single-flight test, which is itself stable).
```

## Final Validation Checklist

### Technical Validation
- [ ] `.venv/bin/python -m py_compile tests/test_daemon.py` → exit 0.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py --collect-only -q` → 140 collected, no errors.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v -k "<the 9 new test names>"` → **9 passed**.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -q` → 140 passed.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L4: 5 repeated runs of the new section → "9 passed" each time (deterministic).
- [ ] L3 scope guard: ONLY `tests/test_daemon.py` modified; daemon.py untouched; appended at END (after S2); no helper-name collision; no `tests/__init__.py`.

### Feature Validation
- [ ] Clause (e): `_maybe_idle_unload()` fires after `now-1801` disarmed → `_recorder None`, `_models_loaded False`, `fb.phases[-1]=="unloaded"`, `rec.shutdowns==1`.
- [ ] Clause (f): `auto_unload_idle_seconds=0` → no-op even at `now-9999` (resident, `rec.shutdowns==0`).
- [ ] Clause (g): `_arm()` clears `_disarmed_monotonic` → a re-arm cancels a pending unload (resident).
- [ ] Clause (a) gap: lazy boot → `fb.phases[-1]=="unloaded"`.
- [ ] Clause (c) gap: two concurrent `start()` → exactly ONE `build_recorder`; armed.
- [ ] Guards: no-op within threshold / while listening / never disarmed / not loaded.
- [ ] No real CUDA / RealtimeSTT (every test uses `_StubRecorder` + `_make_daemon`/`_make_lazy_daemon` + `monkeypatch`).
- [ ] No duplication of the existing lazy-load tests (a-attrs/b/c-mechanism/d/h).

### Code Quality Validation
- [ ] Section header + docstrings mirror the file's style (PRD §4.2bis cross-ref; "NO CUDA" note; clause each test realizes).
- [ ] Reuses `_StubRecorder`/`_make_daemon`/`_make_lazy_daemon`/`_wait_for`/`_DaemonFakeFeedback`/`_FakeBackend` (no redefinition; no new helper class).
- [ ] No new imports (module-level `threading`/`_time`); no new deps.
- [ ] Asserts via `fb.phases[-1]`/`d._recorder`/`d._models_loaded`/`rec.shutdowns` — NEVER `d.status_snapshot()` (fakes lack `snapshot()`).
- [ ] Only `tests/test_daemon.py` modified; append-only at the END (after S2's section); no edits to earlier tests.

### Documentation & Deployment
- [ ] Section header documents: the PRD §4.2bis contract, the fakes reused, the "no CUDA" guarantee, the clause each test realizes, and the gap each fills vs the existing lazy-load section.
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none — test-only").

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/daemon.py` — the implementation is LANDED (M2.T1.S1 + M3.T1.S1); this subtask is test-only. If a test reveals an impl bug, raise it, don't patch it here (Critical #1).
- ❌ Don't duplicate the existing lazy-load tests — clauses (a-boot attrs)/(b)/(c at _load_recorder level)/(d)/(h) ALREADY EXIST (~1905-2060). Fill the GAPS (boot phase; start-level single-flight) + add the idle-unload lifecycle (e/f/g) (Critical #2).
- ❌ Don't call `d.status_snapshot()` — the test fakes have NO `snapshot()` → AttributeError. Assert via `fb.phases[-1]` + the daemon attrs (Critical #3).
- ❌ Don't insert before S2's section or reuse its helper names (`_ControllableShutdownRecorder`, `_idle_unloaded_loaded_daemon`) — APPEND at the file END with inline setup (Critical #4).
- ❌ Don't set `auto_unload_idle_seconds=0` in a test that expects an unload to FIRE — 0 disables. Use the 1800 default (+ `now-1801`) for fire; use 0 only for the disable test (Critical #6).
- ❌ Don't start the `_idle_unload_watchdog` thread (needs real timing) — call `_maybe_idle_unload()` DIRECTLY, mirroring the auto-stop tests' direct `_maybe_auto_stop()` call (Critical #7).
- ❌ Don't use `unittest.mock`/`pytest-mock` — the project uses stdlib `monkeypatch` exclusively; no new deps (reuse `monkeypatch.setattr(daemon, "build_recorder", ...)` for the single-flight test).
- ❌ Don't synchronize the single-flight race with bare `time.sleep` — use `threading.Event` (started/release), mirroring the existing single-flight test (Critical #10).
- ❌ Don't add a new helper class or module-level helper — inline the setup per-test (mirrors the auto-stop section); reuse `_make_daemon`/`_make_lazy_daemon` (Critical #9).
- ❌ Don't create a new test file or `tests/__init__.py` — APPEND to `tests/test_daemon.py` (Gotcha #12).
- ❌ Don't run `mypy` (not installed) or bare `python`/`pytest` (zsh aliases) — use `.venv/bin/python -m pytest` (Gotcha #11).

---

## Confidence Score

**9/10** for one-pass success. The 9 tests are ~150 lines of straightforward pytest, reusing
fakes/helpers already proven in the same file (`_StubRecorder`, `_make_daemon`, `_make_lazy_daemon`,
`_DaemonFakeFeedback`, module-level `threading`/`_time`). The CONTRACT under test
(`_maybe_idle_unload`/`_arm`/`_disarm`/`_disarmed_monotonic`/`auto_unload_idle_seconds`) is LANDED
(M3.T1.S1 + M2.T1.S1 Complete) and pinned from `voice_typing/daemon.py` with exact line numbers. The
inline setup idiom (start→stop→push `_disarmed_monotonic`→`_maybe_idle_unload()`) is a direct analogue
of the passing auto-stop section (~480-560), and the start-level single-flight test mirrors the
existing Event-gated single-flight test (~2031). The fast-suite baseline (131 passed) is verified live,
and the section is disjoint from S2's race tests (different entry point `_maybe_idle_unload` vs
`_unload_recorder`; appended at the file END; no helper-name collision).

The −1 reserves: (a) the `rec.shutdowns == 1` assertion in the fire test depends on
`_bounded_shutdown` calling `rec.shutdown()` synchronously-to-return for the instant `_StubRecorder`
— proven by S2's `test_unload_routes_through_bounded_shutdown...` (same fake), so low risk, but it is
the one assertion that reaches into the teardown path rather than pure state. (b) The start-level
single-flight test is the one multi-threaded test; it mirrors the existing (stable) single-flight
test, but if the implementer's Event handshake differs slightly it could need a one-line nudge. Both
are bounded, one-line fixes gated by the L2 pytest output, not architectural risks.
