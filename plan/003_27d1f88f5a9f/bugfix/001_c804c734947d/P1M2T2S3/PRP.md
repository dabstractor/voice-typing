# PRP — P1.M2.T2.S3: Tests — dead-child detection in `run()`, recovery on next arm, status correctness

## Goal

**Feature Goal**: Commit the regression tests for bugfix **Issue 3** (PRD §2.2/§3.2/§4.2bis — "no
detection/recovery when the recorder-host child crashes → daemon silently stuck `listening: on`").
Sibling **S1** (run() liveness check `daemon.py:750` + `_handle_dead_host()` `daemon.py:778`) and
**S2** (`_load_host()` is_alive guard `daemon.py:654`) are **both already in-tree** (verified:
`git status` + grep + 345-passed baseline). This task APPENDS three pytest functions to
`tests/test_daemon.py` that inject a `_FakeHost` whose `is_alive` flips to `False` (simulating a
child crash: CUDA OOM / segfault / OOM-killer) and assert: **(a)** the run loop detects the dead
host and transitions to `unloaded`; **(b)** the next arm re-spawns a FRESH host (recovery); **(c)**
`status_snapshot()` reports `listening: off / phase: unloaded / models_loaded: false / load_error:
…died`. These are the committed proof that Issue 3 is fixed (detection + recovery + status).

**Deliverable** (3 NEW test functions + 1 section comment header, APPENDED to the END of
`tests/test_daemon.py`; **NO production file edited, NO existing helper/fake modified, NO new import**):
1. `test_run_loop_detects_dead_host_and_transitions_to_unloaded` — `_make_daemon(host_factory=)`,
   run loop in a thread, arm, kill host (`_alive=False`), assert unloaded transition.
2. `test_load_host_respawns_after_dead_child` — arm, kill, `d.start()` again, assert a NEW host
   spawned + loaded + listening (recovery).
3. `test_status_reports_unloaded_after_child_death` — real-Feedback daemon (so `.snapshot()` exists),
   arm, kill, assert `status_snapshot()` reports the crashed/unloaded state.

**Success Definition**:
- (a) After `d._host._alive = False`, within 2s: `d._host is None`, `d._models_loaded is False`,
  `d.is_listening() is False`, `"died" in (d._load_error or "")`, `fb.phases[-1] == "unloaded"`.
- (b) After kill + recovery + `d.start()`: `d._host is not <old host>`, `d._host.spawn_calls == 1`,
  `d._models_loaded is True`, `d.is_listening() is True`.
- (c) After kill: `status_snapshot()` → `listening is False`, `phase == "unloaded"`,
  `models_loaded is False`, `"died" in load_error`.
- (d) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → **348 passed**
  (345 baseline + 3 new). No regression.
- (e) `git status --short` == `tests/test_daemon.py` (+ the in-tree `voice_typing/daemon.py` from
  S1/S2 + `plan/...` task files; this task adds ONLY the test file). **No** edits to
  `daemon.py`/`recorder_host.py`/`feedback.py`/`config.py`, **no** changes to any existing fake/helper
  (`_FakeHost`/`_make_daemon`/`_make_daemon_with_feedback`/`_DaemonFakeFeedback`), **no** new imports.
  DOCS: none.

## User Persona

Not applicable (internal regression-test suite; no user/config/API/doc surface — item DOCS: "none").
The beneficiary is the **maintainer**: these tests pin Issue 3's fix so a future regression that
re-introduces the silent-stuck-on-listening failure (or removes the run() liveness check / the
`_load_host` guard / the `_handle_dead_host` cleanup) fails CI instead of shipping.

## Why

- **Issue 3 was silent permanent breakage; the fix has no committed test yet.** S1 (detection +
  recovery) and S2 (race guard) are in-tree, but the only proof of the behavior is the throwaway
  `python -c` probes in the S1/S2 PRPs — nothing is committed to the suite. The PRD testing summary
  (§2.4) explicitly lists "child-process liveness monitoring" under "Areas needing more attention"
  and prescribes: "Add a test that injects a `RecorderHost` fake whose `is_alive` flips to `False`
  and asserts the daemon recovers on the next arm." This task delivers exactly that.
- **The test seam is already built and CUDA-free.** `_FakeHost` (test_daemon.py:434) already has a
  flippable `is_alive` (`self._alive`, set True by `spawn()`), a `spawn_calls` counter, and a fast
  `text()` (returns `""` instantly). `_fake_host_factory()` + `_make_daemon(host_factory=)` +
  `_wait_for()` are the documented integration-test seams (architecture/test_infrastructure.md).
  No new fake is needed.
- **Three tests = the three parts of the fix.** (a) proves S1's run() detection + `_handle_dead_host`
  state reset; (b) proves recovery-on-next-arm (and incidentally exercises S2's `_load_host` guard,
  since recovery clears `_models_loaded`); (c) proves the status contract (§7.6 "voicectl status must
  accurately report state") surfaces the crash instead of lying.
- **Cheap, surgical, parallel-safe.** A pure append to `tests/test_daemon.py` (disjoint line range
  from P1.M2.T1.S2's appends at the current EOF). No production edits, no fake edits.

## What

Append three pytest functions to the END of `tests/test_daemon.py` (currently 3064 lines; append
after `test_state_json_phase_idle_after_child_death`... after `test_state_json_phase_idle_after_stop`,
the last P1.M2.T1.S2 test). Each starts the daemon's `run()` in a daemon thread, arms via `d.start()`
(which lazy-loads a `_FakeHost` through `host_factory=`), simulates a child crash by flipping
`d._host._alive = False`, polls with `_wait_for(...)`, asserts the post-crash state, and tears down
with the canonical `request_shutdown()` + `_wait_for(not t.is_alive)` + `t.join()` pattern.

- **(a)/(b)** use `_make_daemon(host_factory=_fake_host_factory(spawn_result=True))` (the
  `_DaemonFakeFeedback` it builds records `fb.phases` / `fb.listening_states` for bonus assertions;
  daemon attrs carry the load-bearing asserts).
- **(c)** builds a **real `Feedback`** daemon (a `host_factory=` variant of
  `_make_daemon_with_feedback`) because `status_snapshot()` reads `phase`/`models_loaded` from
  `self._feedback.snapshot()`, which `_DaemonFakeFeedback` lacks. (`listening` + `load_error` come
  from daemon attrs and would work with either feedback, but `phase`/`models_loaded` need the real one.)

### Success Criteria

- [ ] `test_run_loop_detects_dead_host_and_transitions_to_unloaded` exists and passes (assertion set (a)).
- [ ] `test_load_host_respawns_after_dead_child` exists and passes (assertion set (b)).
- [ ] `test_status_reports_unloaded_after_child_death` exists and passes (assertion set (c)).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `348 passed`.
- [ ] `git status --short` shows `tests/test_daemon.py` as the only file THIS task adds (besides
      the in-tree S1/S2 `daemon.py` + plan task files).
- [ ] No production file edited; no existing fake/helper modified; no new import added.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo can implement it from this PRP + the research note. The exact
test seams (`_make_daemon(host_factory=)`, `_fake_host_factory()`, `_FakeHost._alive`/`spawn_calls`,
`_wait_for()`, `status_snapshot()`'s feedback dependency) are documented (research §1-§2). The
**status-snapshot gotcha** — `status_snapshot()` calls `self._feedback.snapshot()` which
`_DaemonFakeFeedback` lacks, so test (c) MUST use real `Feedback` — is the single most important
non-obvious fact and is spelled out (research §2) with the exact construction (§3.2). The **kill
mechanism** (`d._host._alive = False`) and why `host_factory=` (not `recorder_host=`) is the only
correct seam (`_FakeHost._alive` defaults False; only `spawn()` sets it True) is in research §1+§4.
The **timing** (why `_wait_for(timeout=2.0)` is ample — `_FakeHost.text()` returns instantly) is §5.
The **idle-watchdog non-interference** is §6. The **append-only / no-breakage** proof is §7. Verbatim
test bodies are given in the Implementation Blueprint below.

### Documentation & References

```yaml
# MUST READ — the test seams, the status-snapshot gotcha, the kill mechanism, no-breakage, scope.
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S3/research/dead_child_tests.md
  why: "§0 S1+S2 are IN-TREE (run() check @750, _handle_dead_host @778, _load_host guard @654) + 345
        baseline. §1 the EXACT seams (_make_daemon host_factory=, _fake_host_factory, _FakeHost surface,
        _wait_for, _cuda_resolve). §2 ★ THE STATUS-SNAPSHOT GOTCHA: status_snapshot() reads phase/models_loaded
        from feedback.snapshot(); _DaemonFakeFeedback has NO snapshot() + no-op set_models_loaded -> test (c)
        MUST use real Feedback. §3 the two constructions verbatim. §4 the kill + per-test assertions. §5 timing.
        §6 idle-watchdog non-interference. §7 append-only no-breakage. §10 scope."
  section: "ALL load-bearing. §2 (gotcha), §3 (constructions), §4 (assertions) are the core."

# MUST READ — the SIBLING task contract (S1 in-tree): the code these tests verify.
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S1/PRP.md
  why: "S1 added run()'s liveness check (daemon.py:750) + _handle_dead_host() (778) whose body these
        tests assert against (_host=None, _models_loaded=False, _listening.clear(), set_phase('unloaded'),
        _load_error='recorder-host child died unexpectedly'). S1's research §6 validated the SAME killable-host
        behavior with a throwaway probe; S3 commits it."
  critical: "Do NOT edit daemon.py (S1/S2 own it, already landed). These tests are the COMMITTED proof of S1/S2."

# MUST READ — the S2 task contract (also in-tree): the _load_host guard test (b) exercises.
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S2/PRP.md
  why: "S2 tightened _load_host()'s guard to 'if self._models_loaded and self._host is not None and
        self._host.is_alive: return True' (daemon.py:654). Test (b)'s re-arm after recovery clears
        _models_loaded=False, so the guard does NOT short-circuit -> spawn path -> fresh host. The S2 PRP's
        Level-3 probe used the SAME _fake_host_factory + object-identity assertion S3 commits."
  critical: "S2's guard is in-tree (verified). Test (b) incidentally covers it. Do NOT re-implement S1/S2."

# MUST READ — the file being edited: the seams, the appendsite, the existing run-loop teardown pattern.
- file: tests/test_daemon.py
  why: "APPEND to EOF (3064 lines; last test = test_state_json_phase_idle_after_stop). Seams: _make_daemon
        (512), _fake_host_factory (501), _FakeHost (434: is_alive->_alive, spawn() sets _alive=True + spawn_calls,
        text()->instant '', pid->None, _alive DEFAULTS False), _wait_for (417), _cuda_resolve (69),
        _DaemonFakeFeedback (353: phases/listening_states lists, set_models_loaded NO-OP), _make_daemon_with_feedback
        (1396: real Feedback + tmp_path state.json). Run-loop teardown precedent: lines 845-865
        (try/finally request_shutdown + _wait_for(not t.is_alive) + t.join). Imports already module-level:
        threading (349), time as _time (350), Feedback (1393), FeedbackConfig (1392), pytest (21),
        daemon/VoiceTypingConfig (24)."
  critical: "Do NOT modify _FakeHost/_make_daemon/_make_daemon_with_feedback/_DaemonFakeFeedback or add imports.
             Use _make_daemon(host_factory=) for (a)/(b); real Feedback + host_factory= for (c). Inject the
             _FakeHost ONLY via host_factory= (NOT recorder_host=; _alive defaults False -> instant false death)."

# MUST READ — the production methods these tests assert against (READ-ONLY; S1/S2 own them).
- file: voice_typing/daemon.py
  why: "run() liveness check (750) + _handle_dead_host() (778-800) = S1 (the behavior test (a)/(c) assert).
        _load_host() guard (654) = S2 (test (b) exercises). status_snapshot() (1282): 'listening'=is_listening(),
        'phase'/'models_loaded'=self._feedback.snapshot().get(...), 'load_error'=self._load_error or ''. start()
        (1153): _load_host() then _arm(). is_listening() (1242): self._listening.is_set()."
  critical: "READ-ONLY. Do NOT edit daemon.py. These tests verify the already-landed S1/S2 behavior."

# MUST READ — the Feedback contract test (c) depends on (status_snapshot reads feedback.snapshot()).
- file: voice_typing/feedback.py
  why: "Feedback.snapshot() (176) -> dict(self._state) {listening,phase,models_loaded,partial,last_final,ts}.
        set_phase (115)/set_models_loaded (126)/set_listening (156) mutate _state. _handle_dead_host() calls all
        three with 'unloaded'/False/False -> snapshot() reflects the crash. THIS is why test (c) needs real Feedback."
  critical: "READ-ONLY. Do NOT edit feedback.py. _DaemonFakeFeedback (the _make_daemon default) lacks snapshot()."

# Background — the test-infra doc (the seams this task uses).
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/test_infrastructure.md
  why: "Documents _FakeHost, _make_daemon(host_factory=), _wait_for, the run-loop integration pattern
        (thread target=d.run + _wait_for + request_shutdown), and the coverage gap 'Child crash recovery: None'."
  critical: "Background. The item CONTRACT (LOGIC a/b/c) prescribes the three tests verbatim."

# THE DEFECT (Issue 3) — the PRD/bug source.
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: "§2.2/§3.2 Issue 3 documents the silent-stuck-on-listening failure + prescribes the test
        ('inject a RecorderHost fake whose is_alive flips to False and assert the daemon recovers on the next arm')."
  critical: "READ-ONLY. Never modify prd_snapshot.md (orchestrator-owned)."
```

### Current Codebase tree (relevant slice — the 1 file this task appends to)

```bash
/home/dustin/projects/voice-typing/
└── tests/
    └── test_daemon.py    # APPEND: 3 test functions + section comment header at EOF (after line 3064).
# voice_typing/daemon.py (S1/S2, IN-TREE, UNCHANGED), recorder_host.py, feedback.py, config.py — UNCHANGED.
```

### Desired Codebase tree (unchanged structure — pure append)

```bash
# Same tree. tests/test_daemon.py grows by 3 functions + a section comment (~90-110 lines) at the END.
# No new file, no production edit, no fake/helper edit, no new import.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ★ status_snapshot() READS feedback.snapshot(); _DaemonFakeFeedback HAS NO .snapshot().
#   daemon.status_snapshot() (daemon.py:1282) does `snap = self._feedback.snapshot()` then reads
#   snap.get("phase"/"models_loaded"). _DaemonFakeFeedback (the _make_daemon default) has NO snapshot()
#   method AND its set_models_loaded is a no-op. So a _make_daemon(host_factory=) daemon CANNOT service
#   status_snapshot() (AttributeError). => Tests (a)/(b) assert DAEMON ATTRS (d._host, d._models_loaded,
#   d.is_listening(), d._load_error) + the _DaemonFakeFeedback lists (fb.phases[-1], fb.listening_states[-1]).
#   => Test (c) builds a REAL Feedback daemon (host_factory= variant of _make_daemon_with_feedback) so
#   .snapshot() exists and reflects set_phase('unloaded')/set_models_loaded(False). (Research §2.)

# CRITICAL #2 — INJECT THE _FakeHost VIA host_factory=, NEVER recorder_host=. _FakeHost._alive DEFAULTS
#   False (test_daemon.py:459); only spawn() sets it True (462-463). A recorder_host= injection never calls
#   spawn() -> _alive stays False -> the run loop's liveness check fires on iteration 1 (instant false death).
#   host_factory= makes _load_host() call factory(...) then host.spawn() -> _alive=True. ONLY host_factory= is
#   correct. (Research §1.)

# CRITICAL #3 — KILL VIA d._host._alive = False (a plain attribute write from the main thread). The run loop
#   reads host.is_alive on the LOOP thread (no lock on the read); CPython attribute write is atomic, so the
#   write is visible without a lock. _handle_dead_host() then takes self._lock for the cleanup. The main thread
#   NEVER holds _lock during the kill -> no deadlock. (Research §5.)

# CRITICAL #4 — _wait_for(timeout=2.0) IS AMPLE. _FakeHost.text() returns "" INSTANTLY (proxies to
#   _StubRecorder.text()), so on the listening path the loop spins with NO 0.05s sleep; once _alive flips
#   False the next iteration (microseconds later) hits the liveness check. Detection is sub-millisecond in
#   practice. (Research §5.)

# CRITICAL #5 — THE IDLE WATCHDOGS WILL NOT INTERFERE. _handle_dead_host() clears _disarmed_monotonic=None
#   (the idle-UNLOAD clock) + _models_loaded=False, so the idle-unload watchdog no-ops after recovery. The
#   idle AUTO-STOP (30s default) cannot fire in the <2s test window (and test b re-arms immediately). (Research §6.)

# CRITICAL #6 — PURE APPEND. Add ONLY the 3 functions + a section comment header at EOF. Do NOT modify
#   _FakeHost/_make_daemon/_make_daemon_with_feedback/_DaemonFakeFeedback, do NOT add imports (threading @349,
#   time @_time @350, Feedback @1393, FeedbackConfig @1392, pytest @21, daemon/VoiceTypingConfig @24 are all
#   already module-level), do NOT edit any production file. (Research §7.)

# CRITICAL #7 — USE THE CANONICAL RUN-LOOP TEARDOWN. try/finally: d.request_shutdown() in finally; then
#   assert _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0). (Precedent: lines 845-865.)
#   Without it a failing assertion could leave the run thread spinning (test hang). (Research §3.)

# CRITICAL #8 — FULL TOOL PATHS (zsh aliases python/pytest). Run
#   .venv/bin/python -m pytest ... (never bare 'pytest'/'python'). Optional ruff is at
#   /home/dustin/.local/bin/ruff (NOT in .venv). mypy is NOT installed — do NOT run it. (Research §9.)
```

## Implementation Blueprint

### Data models and structure

None. No data model, no new fixture, no helper, no import. Three plain pytest functions appended to
`tests/test_daemon.py`. (a)/(b) take `monkeypatch`; (c) takes `tmp_path, monkeypatch` (pytest
fixtures, no import).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: APPEND a section comment header + test (a) to the END of tests/test_daemon.py
  - ADD: a section comment header naming P1.M2.T2.S3 / Issue 3 (detection+recovery+status regression).
  - ADD: def test_run_loop_detects_dead_host_and_transitions_to_unloaded(monkeypatch): ...
  - CONSTRUCTION: _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS); factory=_fake_host_factory(True);
    d, fb, _rec, _be = _make_daemon(host_factory=factory); thread target=d.run; _wait_for booted; d.start();
    _wait_for(lambda: d._models_loaded, timeout=2.0).
  - KILL: d._host._alive = False.
  - WAIT: _wait_for(lambda: d._models_loaded is False, timeout=2.0).
  - ASSERT: d._host is None; d._models_loaded is False; d.is_listening() is False; "died" in (d._load_error or "");
    fb.phases[-1] == "unloaded"; fb.listening_states[-1] is False.
  - TEARDOWN: try/finally request_shutdown + _wait_for(not t.is_alive) + t.join (Critical #7).
  - EXACT body: see "Test (a)" verbatim block below.
  - VERIFY: passes; asserts the S1 detection + _handle_dead_host state reset.

Task 2: APPEND test (b) to the END of tests/test_daemon.py
  - ADD: def test_load_host_respawns_after_dead_child(monkeypatch): ...
  - CONSTRUCTION: same as (a) (_make_daemon host_factory=).
  - KILL: capture old = d._host FIRST; then d._host._alive = False.
  - WAIT cleanup: _wait_for(lambda: d._host is None, timeout=2.0).
  - RE-ARM: d.start() again (exercises S2's _load_host guard: _models_loaded False -> no short-circuit -> spawn).
  - WAIT: _wait_for(lambda: d._models_loaded, timeout=2.0).
  - ASSERT: d._host is not old; d._host.spawn_calls == 1; d._models_loaded is True; d.is_listening() is True.
  - TEARDOWN: same canonical pattern.
  - EXACT body: see "Test (b)" verbatim block below.
  - VERIFY: passes; proves recovery (NEW host spawned, loaded, listening).

Task 3: APPEND test (c) to the END of tests/test_daemon.py
  - ADD: def test_status_reports_unloaded_after_child_death(tmp_path, monkeypatch): ...
  - CONSTRUCTION: REAL Feedback + host_factory (Critical #1): _cuda_resolve(...);
    cfg=VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path/"state.json"))); fb=Feedback(cfg.feedback);
    factory=_fake_host_factory(True); d=daemon.VoiceTypingDaemon(cfg, fb, recorder=None, host_factory=factory,
    backend=_FakeBackend(), mic_prober=_ok_probe).
  - KILL: d._host._alive = False after arm.
  - WAIT cleanup: _wait_for(lambda: d._host is None, timeout=2.0).
  - ASSERT: snap=d.status_snapshot(); snap["listening"] is False; snap["phase"]=="unloaded";
    snap["models_loaded"] is False; "died" in snap["load_error"].
  - TEARDOWN: same canonical pattern.
  - EXACT body: see "Test (c)" verbatim block below.
  - VERIFY: passes; proves the status contract surfaces the crash (needs real Feedback.snapshot()).

Task 4: VALIDATE
  - RUN: .venv/bin/python -m pytest tests/test_daemon.py -q -k "dead_host or respawn or status_reports_unloaded"
    -> 3 passed.
  - RUN: .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q -> 348 passed.
  - (OPTIONAL) /home/dustin/.local/bin/ruff check tests/test_daemon.py.
```

### Edits — verbatim blocks to APPEND at the END of `tests/test_daemon.py`

Append the following block after the last line of the file (`test_state_json_phase_idle_after_stop`):

```python


# ---------------------------------------------------------------------------
# Regression for Issue 3 (P1.M2.T2.S3): dead recorder-host child detection,
# recovery on next arm, and status correctness. Exercises run()'s liveness
# check + _handle_dead_host() (S1, daemon.py:750/778) and _load_host()'s is_alive
# guard (S2, daemon.py:654) via a _FakeHost whose is_alive flips to False
# (simulating a CUDA-OOM / segfault / OOM-killer child crash).
# ---------------------------------------------------------------------------


def test_run_loop_detects_dead_host_and_transitions_to_unloaded(monkeypatch):
    """A crashed recorder-host child is detected by run() and the daemon resets to 'unloaded'.

    Arms (start -> _load_host spawns a _FakeHost via host_factory -> _alive=True), then flips
    host._alive=False to simulate the child dying. run()'s liveness check fires _handle_dead_host():
    _host=None, _models_loaded=False, _listening cleared, phase 'unloaded', _load_error set.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    factory = _fake_host_factory(spawn_result=True)
    d, fb, _rec, _be = _make_daemon(host_factory=factory)
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)   # run() booted
        d.start()                                          # _load_host spawns _FakeHost (_alive=True) + _arm
        assert _wait_for(lambda: d._models_loaded, timeout=2.0), "host did not load+arm"
        assert d.is_listening() and d._host is not None
        d._host._alive = False                             # simulate the child crashing
        assert _wait_for(lambda: d._models_loaded is False, timeout=2.0), \
            "run() did not detect the dead host within 2s"
        assert d._host is None
        assert d._models_loaded is False
        assert d.is_listening() is False                   # _listening cleared (died WHILE listening)
        assert "died" in (d._load_error or ""), d._load_error
        assert fb.phases[-1] == "unloaded"                 # _handle_dead_host -> set_phase("unloaded")
        assert fb.listening_states[-1] is False
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_load_host_respawns_after_dead_child(monkeypatch):
    """After a dead-child cleanup, the next arm re-spawns a FRESH host (recovery).

    Recovery (_handle_dead_host) clears _models_loaded=False, so _load_host()'s
    `if self._models_loaded and ... is_alive` guard (S2) does NOT short-circuit -> the factory
    builds a NEW _FakeHost and spawn() runs again. Proves Issue 3 self-heals on re-arm.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    factory = _fake_host_factory(spawn_result=True)
    d, fb, _rec, _be = _make_daemon(host_factory=factory)
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)
        d.start()
        assert _wait_for(lambda: d._models_loaded, timeout=2.0)
        old_host = d._host                              # capture before killing
        old_host._alive = False                         # child crashes
        assert _wait_for(lambda: d._host is None, timeout=2.0), "dead host not cleaned up"
        assert d._models_loaded is False
        d.start()                                        # re-arm -> _load_host spawns a FRESH host
        assert _wait_for(lambda: d._models_loaded, timeout=2.0), "host did not re-spawn"
        assert d._host is not old_host, "re-arm reused the dead host instead of spawning a new one"
        assert d._host.spawn_calls == 1, "the new host was not spawned exactly once"
        assert d._models_loaded is True
        assert d.is_listening() is True                 # recovery: listening again
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_status_reports_unloaded_after_child_death(tmp_path, monkeypatch):
    """status_snapshot() surfaces the crash (listening off / phase unloaded / models not loaded / load_error).

    Uses a REAL Feedback (not _DaemonFakeFeedback) because status_snapshot() reads phase/models_loaded
    from feedback.snapshot(), which the fake lacks. Asserts the §7.6 status contract.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb = Feedback(cfg.feedback)
    factory = _fake_host_factory(spawn_result=True)
    d = daemon.VoiceTypingDaemon(
        cfg, fb, recorder=None, host_factory=factory, backend=_FakeBackend(), mic_prober=_ok_probe
    )
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)
        d.start()
        assert _wait_for(lambda: d._models_loaded, timeout=2.0)
        d._host._alive = False                          # child crashes
        assert _wait_for(lambda: d._host is None, timeout=2.0), "dead host not cleaned up"
        snap = d.status_snapshot()
        assert snap["listening"] is False               # is_listening()
        assert snap["phase"] == "unloaded"              # real Feedback.set_phase("unloaded")
        assert snap["models_loaded"] is False           # real Feedback.set_models_loaded(False)
        assert "died" in snap["load_error"], snap["load_error"]   # self._load_error
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)
```

> **Why these three tests:** (a) is the S1 detection proof (run loop catches the dead host →
> `_handle_dead_host` resets state). (b) is the recovery proof (next arm re-spawns a fresh host —
> the object-identity `is not old_host` + `spawn_calls == 1` proves the factory ran again; this also
> exercises S2's guard since recovery cleared `_models_loaded`). (c) is the status-contract proof
> (real Feedback's `snapshot()` reflects the `unloaded`/`models_loaded=False`/`load_error` set by
> `_handle_dead_host`). Together they pin the full Issue-3 fix. The `try/finally request_shutdown`
> + `_wait_for(not t.is_alive)` + `t.join` teardown (Critical #7) prevents a hung run thread on any
> assertion failure.

### Implementation Patterns & Key Details

```python
# (1) The canonical run-loop integration test shape (precedent: test_daemon.py:845-865):
t = threading.Thread(target=d.run, daemon=True)
t.start()
try:
    _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)   # run() booted
    d.start()                                                        # lazy-load via host_factory + arm
    _wait_for(lambda: d._models_loaded, timeout=2.0)                 # loaded
    # ... kill (d._host._alive = False) + wait + assert ...
finally:
    d.request_shutdown()
assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
t.join(timeout=2.0)

# (2) Why host_factory= (Critical #2): _FakeHost._alive defaults False; spawn() (called by
#   _load_host via the factory) sets it True. A recorder_host= injection skips spawn() -> dead on boot.
factory = _fake_host_factory(spawn_result=True)
d, fb, _rec, _be = _make_daemon(host_factory=factory)

# (3) The kill + detection (Critical #3/#4): plain attr write; detected on the loop's next iteration
#   (microseconds, since _FakeHost.text() returns "" instantly -> no 0.05s sleep on the listening path):
d._host._alive = False
assert _wait_for(lambda: d._models_loaded is False, timeout=2.0)

# (4) Test (c) MUST use real Feedback (Critical #1): status_snapshot() calls self._feedback.snapshot().
cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
fb = Feedback(cfg.feedback)
d = daemon.VoiceTypingDaemon(cfg, fb, recorder=None, host_factory=factory,
                             backend=_FakeBackend(), mic_prober=_ok_probe)
# ... after kill: snap = d.status_snapshot(); assert snap["phase"] == "unloaded" ...
```

### Integration Points

```yaml
TEST FILE (tests/test_daemon.py):
  - append: "3 functions + section comment header at EOF (after test_state_json_phase_idle_after_stop, line 3064)"
  - imports: "NONE added — threading(349)/time-as-_time(350)/Feedback(1393)/FeedbackConfig(1392)/pytest(21)/
              daemon+VoiceTypingConfig(24) are already module-level"
  - fixtures: "(a)/(b) take monkeypatch; (c) takes tmp_path, monkeypatch (pytest built-ins, no import)"
SEAMS USED (unchanged):
  - _make_daemon(host_factory=): "(a)/(b) construction (_DaemonFakeFeedback records phases/listening_states)"
  - _fake_host_factory(spawn_result=True): "builds the factory; each call -> a NEW _FakeHost"
  - _FakeHost: "is_alive->_alive (True after spawn), spawn_calls counter, text()->instant '', pid->None"
  - _wait_for(predicate, timeout=2.0): "poll-based async assertion"
  - _cuda_resolve(monkeypatch, CUDA_DEFAULTS): "defensive (host.device seeds the cache; cuda not probed)"
  - _make_daemon_with_feedback (pattern): "(c) mirrors it but passes host_factory= instead of recorder="
PRODUCTION (READ-ONLY, S1/S2 own — these tests VERIFY):
  - run() liveness check (daemon.py:750): "the detection S1 added (asserted by a/c)"
  - _handle_dead_host (daemon.py:778-800): "the state reset S1 added (asserted by a/b/c)"
  - _load_host guard (daemon.py:654): "S2's is_alive guard (exercised by b's re-arm after recovery)"
  - status_snapshot (daemon.py:1282): "reads feedback.snapshot() + daemon attrs (asserted by c)"
COORDINATION (sibling / parallel — DISJOINT):
  - P1.M2.T1.S2: "also appends to test_daemon.py (the last ~50 lines to 3064); S3 appends AFTER it.
                   Disjoint line ranges + distinct test names -> git merges cleanly."
  - S1/S2: "own voice_typing/daemon.py (already landed); S3 does NOT touch it."
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
# The three new test names exist exactly once each (no typo / no accidental dup):
grep -n "def test_run_loop_detects_dead_host_and_transitions_to_unloaded\|def test_load_host_respawns_after_dead_child\|def test_status_reports_unloaded_after_child_death" tests/test_daemon.py
# Expected: 3 hits (one per name).

# Module imports cleanly (no syntax/indentation breakage from the append):
.venv/bin/python -c "import tests.test_daemon as td; print('test_daemon imports OK')"

# OPTIONAL lint — ruff is a uv tool at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed.
/home/dustin/.local/bin/ruff check tests/test_daemon.py || true
# Expected: clean (pure test additions; reuses existing module-level imports + seams).
```

### Level 2: Unit Tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing
# Just the three new tests (fast, isolated):
.venv/bin/python -m pytest tests/test_daemon.py -q \
    -k "dead_host or respawn or status_reports_unloaded"
# Expected: 3 passed.

# The existing run-loop + lazy-load tests (must stay green — these tests reuse their seams):
.venv/bin/python -m pytest tests/test_daemon.py -q \
    -k "run_loop or load or spawn or lazy or idle_unload or single_flight"
# Expected: all green.

# Whole fast suite (no regression — baseline 345; +3 new = 348):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 348 passed. (test_feed_audio.py needs a GPU + espeak assets; excluded.)
```

### Level 3: Integration (feature behavior — these tests ARE the integration proof)

```bash
cd /home/dustin/projects/voice-typing
# Run the three tests verbosely to confirm the detection/recovery/status assertions all hold:
.venv/bin/python -m pytest tests/test_daemon.py -v \
    -k "dead_host or respawn or status_reports_unloaded"
# Expected: each test PASSED, each _wait_for succeeded (no timeout), run() threads exited cleanly.

# (Sanity) confirm git touched ONLY the test file THIS task owns (plus the in-tree S1/S2 daemon.py):
git status --short
# Expected: ' M tests/test_daemon.py' (this task) + ' M voice_typing/daemon.py' (S1/S2, pre-existing)
#           + plan/... task files. NO recorder_host.py / feedback.py / config.py / other test files.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-daemon/GPU/audio path is exercised by pure test additions. The end-to-end guarantee —
# "kill the recorder-host grandchild -> voicectl status shows unloaded + load_error -> re-arm reloads"
# — is exactly what tests (a)/(b)/(c) pin in-process via the _FakeHost crash simulation. A live smoke
# (optional, GPU-gated, NOT part of this task): arm, `kill -9 <child-pid>`, then
# `.venv/bin/voicectl status` -> expect 'phase: unloaded' + '(not loaded)' + 'load error: ...died' +
# 'listening: off'; then `.venv/bin/voicectl start` reloads (~1-3s) and transcription works again.
# That live behavior is now GUARDED by these committed pytest (a/b/c) on every CI run.
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep -n "def test_run_loop_detects_dead_host_and_transitions_to_unloaded\|def test_load_host_respawns_after_dead_child\|def test_status_reports_unloaded_after_child_death" tests/test_daemon.py` → exactly 3 hits.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -q -k "dead_host or respawn or status_reports_unloaded"` → `3 passed`.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `348 passed`.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check tests/test_daemon.py` → clean.

### Feature Validation
- [ ] Test (a): after `d._host._alive=False`, `d._host is None`, `d._models_loaded is False`, `d.is_listening() is False`, `"died" in d._load_error`, `fb.phases[-1]=="unloaded"`, `fb.listening_states[-1] is False`.
- [ ] Test (b): after kill + `d.start()`, `d._host is not <old>`, `d._host.spawn_calls == 1`, `d._models_loaded is True`, `d.is_listening() is True`.
- [ ] Test (c): after kill, `status_snapshot()` → `listening is False`, `phase=="unloaded"`, `models_loaded is False`, `"died" in load_error`.
- [ ] All three tests' run-loop threads exit cleanly (no hang; the `request_shutdown` + `_wait_for(not t.is_alive)` + `t.join` teardown).

### Code Quality Validation
- [ ] Only `tests/test_daemon.py` modified by THIS task (pure append); no production file edited.
- [ ] No existing fake/helper modified (`_FakeHost`/`_make_daemon`/`_make_daemon_with_feedback`/`_DaemonFakeFeedback` untouched).
- [ ] No new import added (all symbols already module-level).
- [ ] Test names unique; section comment header names P1.M2.T2.S3 / Issue 3.
- [ ] Each test uses the canonical `try/finally request_shutdown` + `_wait_for(not t.is_alive)` + `t.join` teardown.

### Documentation & Deployment
- [ ] Each test has a docstring stating what it proves (detection / recovery / status).
- [ ] Section comment header documents the S1/S2 code under test (daemon.py line refs) + the crash simulation.
- [ ] No new env vars, no config keys, no external docs (regression-test suite; item DOCS: none).

---

## Anti-Patterns to Avoid

- ❌ Don't use `_DaemonFakeFeedback` (the `_make_daemon` default) for test (c) — `status_snapshot()`
  calls `self._feedback.snapshot()` which the fake lacks (Critical #1). Test (c) MUST use real `Feedback`.
- ❌ Don't inject the `_FakeHost` via `recorder_host=` — `_alive` defaults False and `spawn()` is never
  called, so the loop treats it as dead on iteration 1 (Critical #2). Use `host_factory=` ONLY.
- ❌ Don't forget the `try/finally request_shutdown` + `_wait_for(not t.is_alive)` + `t.join` teardown —
  a failing assertion would otherwise leave the run thread spinning (test hang) (Critical #7).
- ❌ Don't edit any production file (`daemon.py`/`recorder_host.py`/`feedback.py`/`config.py`) or any
  existing fake/helper — this task is a PURE APPEND of 3 tests (Critical #6).
- ❌ Don't add imports — `threading`, `time` (as `_time`), `Feedback`, `FeedbackConfig`, `pytest`,
  `daemon`, `VoiceTypingConfig` are all already module-level (Critical #6).
- ❌ Don't run `mypy` — it's not installed; pytest is the authoritative gate (Critical #8).
- ❌ Don't re-implement S1/S2 (run() check / `_handle_dead_host` / `_load_host` guard) — they're
  in-tree; these tests VERIFY them (Critical #6).
- ❌ Don't assert `models_loaded` via `_DaemonFakeFeedback` in (a)/(b) — its `set_models_loaded` is a
  no-op stub; assert `d._models_loaded` (the daemon attr) instead (Critical #1).

---

## Confidence Score

**9/10** — one-pass success likelihood. This is a pure append of three pytest functions that reuse
existing, documented seams (`_make_daemon(host_factory=)`, `_fake_host_factory()`, `_FakeHost._alive`,
`_wait_for()`) against already-in-tree production code (S1's run() check + `_handle_dead_host`; S2's
`_load_host` guard — all verified present with a 345-green baseline). The two non-obvious failure
modes are explicitly flagged and worked around: (1) test (c) uses real `Feedback` because
`status_snapshot()` needs `.snapshot()` (Critical #1); (2) the `_FakeHost` is injected via
`host_factory=` not `recorder_host=` because `_alive` defaults False (Critical #2). Verbatim test
bodies are provided (including the exact assertions, kill mechanism, and teardown), and the kill
mechanism + detection timing + watchdog non-interference are all validated facts from the S1/S2
research probes (which exercised the identical `_FakeHost`-crash path). Residual risk is only a
verbatim-paste indentation mismatch, which the grep/import sanity gates (Level 1) catch immediately.
