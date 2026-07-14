# PRP — P1.M2.T1.S2: Test phase returns to idle after disarm (stop, toggle-off, auto-stop)

## Goal

**Feature Goal**: Add the committed pytest regression coverage for bugfix **Issue 2** (Major): after any disarm path — manual `stop()`, `toggle()`-off, or the 30 s `_maybe_auto_stop()` auto-stop — the daemon's `phase` must return to **`idle`** (the "loaded / not listening" lifecycle state per PRD §4.2bis/§4.6). The code fix is the sibling **P1.M2.T1.S1** (one line: `_disarm()` calls `self._feedback.set_phase("idle")` — already present at `daemon.py:875`). This task delivers the **tests that prove it** and guard against regression.

**Deliverable** (test-only; APPEND to ONE existing file, no new files, no source edits):
- `tests/test_daemon.py` — a new `# P1.M2.T1.S2 — phase returns to idle after disarm` section (4 tests + `import json`). Verbatim source in Implementation Blueprint → Task 1.

**Success Definition**:
- (a) Four new tests exist and pass: `test_disarm_resets_phase_to_idle` (stop), `test_toggle_off_resets_phase_to_idle` (toggle-off), `test_auto_stop_resets_phase_to_idle` (30 s auto-stop), `test_state_json_phase_idle_after_stop` (real Feedback → on-disk `state.json`).
- (b) Each asserts the full invariant: `d.is_listening() is False` AND `phase == "idle"` (via `fb.phases[-1]` for the fake-feedback tests; via `json.load(state.json)["phase"]` for the real-Feedback test).
- (c) The tests are genuine regression tests — they FAIL without S1's `_disarm()` line (verified by simulation: pre-fix `fb.phases[-1]` stays `'listening'`/`'speaking'`).
- (d) `.venv/bin/python -m pytest tests/test_daemon.py -q` → 0 failed; `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- (e) Only `tests/test_daemon.py` changes (append). No source file (`daemon.py`/`feedback.py`/`recorder_host.py`), no config, no docs.

## User Persona

Not applicable (test-only; no user/config/API/doc surface — DOCS: none). The beneficiary is the maintainer/CI: a regression that re-introduces the contradictory `listening: off / phase: listening` status is caught deterministically and fast.

## Why

- **Issue 2 is a Major state-contract violation.** PRD §4.6 ("once loaded, `phase` cycles `idle`/`listening`/`speaking`") + §4.2bis (`loaded / not listening` ⇒ `phase idle`). Pre-fix, `phase` froze at the last VAD value after any stop, producing `voicectl status` output like `listening: off / phase: listening` and a matching `state.json`. S1 fixes the single chokepoint (`_disarm()`); **this task locks the fix in with tests** so it cannot silently regress.
- **`_disarm()` is the one chokepoint for all three paths** — `stop()`, `toggle()`-off, `_maybe_auto_stop()`. So three tests (one per path) + one on-disk test give complete coverage of the invariant with minimal code.
- **The VAD phase test today covers only the FORWARD direction.** `test_callback_vad_phases` (~line 247) asserts VAD events → phase (`listening`/`speaking`); no test asserts the REVERSE (disarm → `idle`). This task closes that gap (called out in `architecture/test_infrastructure.md` "Existing Test Coverage Gaps").
- **Pure test addition, GPU-free, deterministic.** All four tests are synchronous (no `run()` thread, no real subprocess, no real sleep) — they drive `start()`/`stop()`/`toggle()`/`_maybe_auto_stop()` directly on fake-injected daemons. Fast (<50 ms) and not flaky.

## What

Append a `# P1.M2.T1.S2` section to `tests/test_daemon.py` with `import json` and four tests (verbatim in Implementation Blueprint → Task 1):
- (a) **stop path** — `_make_daemon()`; `d.start()`; simulate VAD via `d._feedback.set_phase("listening")`; `d.stop()`; assert `not listening` + `fb.phases[-1] == "idle"`.
- (b) **toggle-off path** — same but `d.toggle()` while listening; phase `'speaking'` first.
- (c) **auto-stop path** — `d.start()`; `set_phase("speaking")`; push `_last_speech_monotonic` to `now - 31.0` (the established idiom from `test_auto_stop_*`); `d._maybe_auto_stop()`; assert disarmed + `fb.phases[-1] == "idle"`.
- (d) **on-disk state.json** — `_make_daemon_with_feedback(tmp_path, monkeypatch)` (real `Feedback`); `d.start()`; `fb.set_phase("listening")`; `d.stop()`; `json.load(tmp_path/"state.json")`; assert `["phase"] == "idle"` + `["listening"] is False`.

### Success Criteria

- [ ] `tests/test_daemon.py` has the 4 new test functions + `import json`.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py::test_disarm_resets_phase_to_idle tests/test_daemon.py::test_toggle_off_resets_phase_to_idle tests/test_daemon.py::test_auto_stop_resets_phase_to_idle tests/test_daemon.py::test_state_json_phase_idle_after_stop -v` → 4 passed.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -q` → 0 failed.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] `git status --short` == `tests/test_daemon.py` only (modified/append). No source/config/doc file touched.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo can implement it from this PRP + the referenced research. The 4 tests are given verbatim and were each verified PASSING against the current (S1-fixed) code; the test-fake APIs (`_make_daemon` → `(d,fb,rec,be)`, `_DaemonFakeFeedback.phases`, `_make_daemon_with_feedback` → real `Feedback` writing `tmp_path/"state.json"`), the time-advancement idiom (`_last_speech_monotonic = _time.monotonic() - 31.0`), the import situation (`_time` @350, `Feedback`/`FeedbackConfig` @1392-3, `json` NOT yet imported), and the regression property (FAIL without S1's line) are all documented with line numbers and verified live.

### Documentation & References

```yaml
# MUST READ — boundary + infrastructure + verified test designs + regression property (load-bearing)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T1S2/research/phase_idle_after_disarm_tests.md
  why: "§1 boundary (S1=daemon.py one-liner @875; S2=tests/test_daemon.py append). §2 S1's fix already in tree.
        §3 the test fakes (_make_daemon/_DaemonFakeFeedback.phases/_make_daemon_with_feedback/_time @350/
        auto-stop idiom). §4 the 4 tests, verified passing. §5 regression property (FAIL without S1's line).
        §6 placement + that json must be added. §7 scope."
  section: "ALL load-bearing. §3 (fakes + idiom), §4 (verbatim tests) are the core."

# MUST READ — the contract for what exists when this task runs (S1, parallel "Ready")
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T1S1/PRP.md
  why: "S1 adds the ONE line self._feedback.set_phase('idle') inside _disarm() (after set_listening(False)).
        S1's PRP explicitly says 'S2 owns the committed pytest; S1's validation uses a throwaway inline check
        (NOT a committed test)'. S1 edits ONLY daemon.py; S2 edits ONLY test_daemon.py. _disarm() is the
        chokepoint called by stop()/toggle()/_maybe_auto_stop()."
  critical: "Do NOT edit daemon.py (S1 owns it; the fix is already at line 875). CONSUME the fix: your tests
             assert fb.phases[-1]=='idle', which only holds because of S1's line."

# THE TEST INFRASTRUCTURE MAP (referenced by the item)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/test_infrastructure.md
  why: "Documents _make_daemon (returns (d,fb,rec,be)), _DaemonFakeFeedback (tracks set_phase via .phases),
        _make_daemon_with_feedback (real Feedback + tmp_path state.json), _wait_for, _cuda_resolve. Confirms
        the 'Phase after disarm' coverage gap (test_callback_vad_phases is forward-only)."
  critical: "_make_daemon injects a stub recorder/host so d.start() arms WITHOUT the run loop — the tests are
             synchronous. _make_daemon_with_feedback writes to tmp_path/'state.json' (read it back with json.load)."

# THE FILE BEING EDITED (fakes + idioms to mirror)
- file: tests/test_daemon.py
  why: "_FakeFeedback.set_phase appends to .phases (37-42). _DaemonFakeFeedback adds set_listening (records
        listening_states). _make_daemon (@~512) returns (d,fb,rec,be). _make_daemon_with_feedback (@~1265)
        returns (d,fb) with REAL Feedback, state_file=tmp_path/'state.json'. test_auto_stop_disarms_when_idle
        _beyond_threshold (@583) is the time-advancement idiom to mirror: d._last_speech_monotonic =
        _time.monotonic() - 31.0. test_callback_vad_phases (@247) is the forward-direction test this complements.
        import time as _time @350; from voice_typing.feedback import Feedback @1393; json NOT imported."
  critical: "APPEND at END of file; add `import json  # noqa: E402` in the new section (mirrors the mid-file
             import convention @350/@1392). Use _time.monotonic() (the _time alias), not time.monotonic(). Do
             NOT modify _make_daemon/_make_daemon_with_feedback or any existing test."

# THE DEFECT (Issue 2) + the S1 fix site (context only — NOT edited here)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: "§Issue 2 (MAJOR): '_disarm() ... NEVER calls feedback.set_phase(idle)'. S1's fix adds it. These tests
        prove the fix for all 3 disarm paths + the on-disk state.json contract."
- file: voice_typing/daemon.py
  why: "_disarm() (@~851) is the chokepoint; S1's line is @875. start()/stop()/toggle()/_maybe_auto_stop() all
        funnel disarm through _disarm(). READ-ONLY here — S1 owns it."
  critical: "Do NOT edit daemon.py. The tests assert the OBSERVABLE behavior (fb.phases[-1], state.json), not
             the implementation, so they survive any future refactor that keeps _disarm() setting phase idle."

# THE PRD CONTRACT
- file: PRD.md
  why: "§4.2bis lifecycle: 'loaded / not listening ⇒ phase idle; loaded / listening ⇒ phase listening'. §4.6:
        'once loaded, phase cycles idle/listening/speaking'. These tests assert the cycle closes back to idle."
```

### Current Codebase tree (relevant slice — the one file this task edits)

```bash
/home/dustin/projects/voice-typing/
└── tests/
    └── test_daemon.py   # EDIT (APPEND): +import json, +4 tests in a '# P1.M2.T1.S2' section at END.
# voice_typing/daemon.py (_disarm @851, S1's set_phase('idle') @875) = S1's file — UNCHANGED here.
# feedback.py / recorder_host.py / config / ctl / systemd / README — UNCHANGED.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py     # APPEND ONLY — `import json` + 4 test functions under a section banner.
# NOTHING ELSE. (daemon.py = S1. recorder_host.py gate = deferred. README/ACCEPTANCE = P1.M4.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TESTS ARE SYNCHRONOUS (no run loop). _make_daemon() injects a stub recorder/host so the daemon
#   boots already-loaded (_models_loaded=True, _host is the legacy adapter). So d.start() arms IMMEDIATELY via
#   _arm() without spawning anything, and d.stop()/d.toggle()/d._maybe_auto_stop() are directly callable. Do NOT
#   start a d.run() thread or use _wait_for — these are plain unit tests (deterministic, <50ms, not flaky).
#   (research §3, §4.)

# CRITICAL #2 — USE _time.monotonic(), not time.monotonic(). The test file imports `import time as _time` @350.
#   The auto-stop idiom is `d._last_speech_monotonic = _time.monotonic() - 31.0` (> the 30.0s default threshold),
#   mirroring test_auto_stop_disarms_when_idle_beyond_threshold @583. Do NOT re-import time.

# CRITICAL #3 — ASSERT fb.phases[-1] == 'idle' (the LAST set_phase), not just membership. Pre-fix, _disarm() does
#   NOT call set_phase('idle'), so fb.phases ends with the VAD value ('listening'/'speaking') → fb.phases[-1]==
#   'idle' FAILS (the regression-detection property). Asserting the LAST element is the precise invariant.
#   (research §5.)

# CRITICAL #4 — EACH TEST ALSO ASSERTS d.is_listening() is False. This proves the disarm actually happened (not
#   just that phase happens to be idle), i.e. the full 'loaded / not listening ⇒ phase idle' invariant. Without
#   it, a test could pass on a daemon that never disarmed.

# CRITICAL #5 — TEST (d) READS tmp_path/'state.json' (the real-Feedback path). _make_daemon_with_feedback sets
#   feedback.state_file=str(tmp_path/'state.json'); Feedback.set_phase atomically writes that file. Read it with
#   json.load(open(tmp_path/'state.json')). This is the ON-DISK proof (the _DaemonFakeFeedback in (a)-(c) is
#   in-memory only). json is NOT imported at module level → add `import json  # noqa: E402` in the new section.

# CRITICAL #6 — DO NOT EDIT daemon.py (or any source). S1 owns the fix (already at line 875). This task is a
#   pure test append. The tests assert OBSERVABLE behavior (fb.phases, state.json), so they are robust to
#   implementation refactor. (research §1, §7.)

# CRITICAL #7 — DO NOT add the VAD-relay gate test or any recorder_host.py change. The optional gate is deferred
#   by S1 ('only if observed'). This task tests only the _disarm() → set_phase('idle') invariant.

# GOTCHA #8 — APPEND AT END of test_daemon.py with a section banner (mirrors the file's sectioned convention,
#   e.g. the '# P1.M2.T1.S1 — lazy load' banner). Do NOT insert mid-file (would split existing sections).

# GOTCHA #9 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare
#   python/pytest/uv. (system_context.md; S1 PRP GOTCHA #6.)

# GOTCHA #10 — pytest>=9.1.1 is the runner; NO ruff/mypy configured. Validation = pytest. The `# noqa: E402` on
#   the mid-file `import json` matches the file's existing convention (@350, @1392) so a future ruff adoption
#   won't flag it. (research §3.)
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/types/source change. This appends 4 pytest functions + one stdlib import to a test file. It consumes the existing test fakes (`_make_daemon`, `_DaemonFakeFeedback`, `_make_daemon_with_feedback`, `_StubRecorder`) and the `_time` alias — no new fakes, no new fixtures.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: APPEND the P1.M2.T1.S2 test section to tests/test_daemon.py — use the `edit`/`write` tool to append the
        EXACT block in "Task 1 SOURCE" at the END of the file.
  - FILE: tests/test_daemon.py (APPEND at END).
  - CONTENT: see "Task 1 SOURCE" (verbatim — `import json` + 4 test functions under a section banner).
  - WHY: each test exercises one disarm path funneling through _disarm() (S1's set_phase('idle') site):
    stop() (a), toggle()-off (b), _maybe_auto_stop() (c), and the real-Feedback on-disk state.json write (d).
    The fake-feedback tests assert fb.phases[-1]=='idle'; the real-Feedback test reads state.json. All
    synchronous (no run loop), deterministic.
  - DO NOT: edit daemon.py (CRITICAL #6); add a run loop / _wait_for (CRITICAL #1); re-import time (use _time,
    CRITICAL #2); weaken the assertion to membership (CRITICAL #3); skip the is_listening() check (CRITICAL #4);
    insert mid-file (APPEND at END, GOTCHA #8); add the VAD-relay gate (CRITICAL #7).

Task 2: VALIDATE — run the Validation Loop L1-L4; fix until green. No git commit unless the orchestrator directs
  it. If asked, message: "P1.M2.T1.S2: regression tests — phase returns to 'idle' after disarm (stop/toggle-off/
  auto-stop) + on-disk state.json (Issue 2)".
```

#### Task 1 SOURCE — APPEND at END of `tests/test_daemon.py` (verbatim)

```python
# ===========================================================================
# P1.M2.T1.S2 — phase returns to 'idle' after disarm (stop / toggle-off / auto-stop)
# Regression for Issue 2: _disarm() now calls feedback.set_phase("idle") (P1.M2.T1.S1),
# publishing the 'loaded / not listening' lifecycle state to state.json + voicectl status
# (PRD §4.2bis/§4.6). Without that one line these tests FAIL (fb.phases[-1] stays at the
# last VAD value 'listening'/'speaking'). Synchronous unit tests — no run loop, no GPU.
# ===========================================================================
import json  # noqa: E402  (state.json read in the _make_daemon_with_feedback test below)


def test_disarm_resets_phase_to_idle():
    """stop() -> _disarm() -> phase 'idle' (the 'loaded / not listening' state, PRD §4.2bis/§4.6)."""
    d, fb, _rec, _be = _make_daemon()
    d.start()                                  # arm (set_microphone True, listening on)
    d._feedback.set_phase("listening")         # simulate the child's VAD advancing phase
    assert d.is_listening() is True
    d.stop()                                   # -> _disarm() -> set_listening(False) + set_phase("idle")
    assert d.is_listening() is False
    assert fb.phases[-1] == "idle", f"phase after stop = {fb.phases[-1]!r}"


def test_toggle_off_resets_phase_to_idle():
    """toggle() while listening disarms -> phase 'idle'."""
    d, fb, _rec, _be = _make_daemon()
    d.start()
    d._feedback.set_phase("speaking")          # VAD had reached 'speaking' before the toggle
    assert d.is_listening() is True
    d.toggle()                                 # listening -> disarm branch -> _disarm()
    assert d.is_listening() is False
    assert fb.phases[-1] == "idle", f"phase after toggle-off = {fb.phases[-1]!r}"


def test_auto_stop_resets_phase_to_idle():
    """The 30s idle auto-stop (_maybe_auto_stop -> _disarm) resets phase to 'idle'."""
    d, fb, _rec, _be = _make_daemon()
    d.start()                                  # arm -> _last_speech_monotonic = now
    d._feedback.set_phase("speaking")
    # Idle > 30.0s default threshold (mirrors test_auto_stop_disarms_when_idle_beyond_threshold @583):
    d._last_speech_monotonic = _time.monotonic() - 31.0
    d._maybe_auto_stop()                       # -> _disarm() -> set_phase("idle")
    assert d.is_listening() is False
    assert fb.phases[-1] == "idle", f"phase after auto-stop = {fb.phases[-1]!r}"


def test_state_json_phase_idle_after_stop(tmp_path, monkeypatch):
    """The REAL Feedback writes phase 'idle' to state.json on disarm (on-disk contract, PRD §4.6)."""
    d, fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    d.start()
    fb.set_phase("listening")                  # real Feedback.set_phase (writes state.json)
    assert fb.snapshot()["phase"] == "listening"
    d.stop()                                   # _disarm -> set_phase("idle") -> atomic state.json write
    state = json.load(open(tmp_path / "state.json"))   # _make_daemon_with_feedback writes here
    assert state["phase"] == "idle", state
    assert state["listening"] is False
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — synchronous disarm test via the fake-injected daemon. _make_daemon() injects a stub recorder/host
# so d.start() arms immediately (no run loop, no spawn). Simulate VAD by calling set_phase directly, then disarm.
d, fb, _rec, _be = _make_daemon()
d.start()
d._feedback.set_phase("listening")     # the value that USED to get stuck (Issue 2)
d.stop()                               # -> _disarm() -> set_phase("idle") [S1's fix]
assert d.is_listening() is False and fb.phases[-1] == "idle"

# PATTERN 2 — auto-stop time advancement (the established idiom @583). Push _last_speech_monotonic into the past,
# then call _maybe_auto_stop() directly. Deterministic; no real sleep, no run loop.
d._last_speech_monotonic = _time.monotonic() - 31.0    # > 30.0s default auto_stop_idle_seconds
d._maybe_auto_stop()

# PATTERN 3 — on-disk state.json proof via the REAL Feedback (_make_daemon_with_feedback). The fake feedback is
# in-memory only; this variant writes a real file you json.load back. Path = tmp_path/"state.json".
d, fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
d.start(); fb.set_phase("listening"); d.stop()
assert json.load(open(tmp_path / "state.json"))["phase"] == "idle"
```

### Integration Points

```yaml
UPSTREAM CONSUMED — P1.M2.T1.S1 (parallel "Ready"): the one line self._feedback.set_phase("idle") inside _disarm()
  (daemon.py:875). Without it, test (a)/(b)/(c) FAIL at fb.phases[-1]=='idle' and test (d) FAILS at
  state['phase']=='idle'. This task CONSUMES the fix; it does not edit daemon.py.

UPSTREAM CONSUMED — test fakes (UNCHANGED): _make_daemon, _DaemonFakeFeedback (.phases/.listening_states),
  _make_daemon_with_feedback (real Feedback + tmp_path state.json), _StubRecorder, _FakeBackend, _ok_probe,
  the _time alias (@350). No fake/fixture is modified.

DOWNSTREAM — P1.M2.T2 (child-crash recovery, Issue 3): will add _handle_dead_host liveness tests (different
  methods). No overlap with the phase-after-disarm tests.

UNCHANGED: daemon.py (S1), feedback.py, recorder_host.py, config.py/config.toml, ctl.py, status.sh, systemd,
  README, ACCEPTANCE.md. No new files. No pyproject/uv.lock/.venv changes.

BUILD ARTIFACTS: NO new deps (json is stdlib). Validation = pytest only.
```

## Validation Loop

> Full paths in every bash command (zsh aliases — GOTCHA #9). Run from `/home/dustin/projects/voice-typing`.
> pytest>=9.1.1 is the runner; NO ruff/mypy (GOTCHA #10). All gates are fast/unit (fakes; no GPU/RealtimeSTT).

### Level 1: the 4 tests + import are in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the 4 tests + the json import exist ---"
for fn in test_disarm_resets_phase_to_idle test_toggle_off_resets_phase_to_idle \
          test_auto_stop_resets_phase_to_idle test_state_json_phase_idle_after_stop; do
  grep -q "def ${fn}(" tests/test_daemon.py && echo "L1 PASS: $fn" || echo "L1 FAIL: $fn missing"
done
grep -nE '^import json  # noqa: E402' tests/test_daemon.py && echo "L1 PASS: import json present" || echo "L1 FAIL: import json missing"
# Expected: 4 functions present + the json import line present.
```

### Level 2: the 4 tests pass (the contract)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest \
  "tests/test_daemon.py::test_disarm_resets_phase_to_idle" \
  "tests/test_daemon.py::test_toggle_off_resets_phase_to_idle" \
  "tests/test_daemon.py::test_auto_stop_resets_phase_to_idle" \
  "tests/test_daemon.py::test_state_json_phase_idle_after_stop" -v
# Expected: 4 passed. If a fake-feedback test fails at fb.phases[-1]=='idle', S1's _disarm() line is missing
# (re-check daemon.py:875 has set_phase("idle")); if (d) fails at state['phase'], the real Feedback path is
# wrong (re-check _make_daemon_with_feedback + that d.stop() reaches _disarm()).
```

### Level 3: no regression — full daemon suite + full fast suite green

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_daemon.py -q
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed for both. The new tests are additive (append); they don't touch _make_daemon or any fixture,
# so existing tests are unaffected. (test_feed_audio.py is the heavy GPU suite — ignored on a fast sweep.)
```

### Level 4: scope guard — only test_daemon.py changed (append)

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY tests/test_daemon.py (modified). No daemon.py/feedback.py/recorder_host.py/config/ctl/systemd/
# README/ACCEPTANCE. Confirm the diff is purely an APPEND (no existing line changed):
git diff tests/test_daemon.py | grep -E '^[+-]' | grep -vE '^\+\+\+ |^\+\+ |^--- ' | head
# Expected: only '+' lines (additions) — no '-' lines removing existing code. If '-' lines appear, re-do as append.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: 4 test functions + `import json` present in `tests/test_daemon.py`.
- [ ] L2: the 4 named tests pass (`4 passed`).
- [ ] L3: `pytest tests/test_daemon.py -q` → 0 failed; `pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L4: `git status` == `tests/test_daemon.py` only; the diff is pure additions (append).

### Feature Validation
- [ ] stop / toggle-off / 30 s auto-stop each leave `phase == 'idle'` (the 3 disarm paths through `_disarm()`).
- [ ] The real-Feedback path writes `phase: idle` to `state.json` on disk (on-disk contract).
- [ ] Each test also asserts `d.is_listening() is False` (the disarm actually happened).
- [ ] The tests are genuine regression tests (would FAIL without S1's `set_phase('idle')` line).

### Code Quality Validation
- [ ] Synchronous unit tests (no run loop / `_wait_for` / real sleep) — deterministic, fast, not flaky.
- [ ] Uses the existing `_time` alias and `tmp_path/"state.json"` convention; `import json  # noqa: E402`.
- [ ] Mirrors the `test_auto_stop_*` (@583) time-advancement idiom and the `test_callback_vad_phases` (@247) section style.
- [ ] Full paths in every bash command; no bare python/pytest/uv.

### Scope Boundary Validation
- [ ] No source files touched (`daemon.py`/`feedback.py`/`recorder_host.py`/`config`/`ctl`/`status.sh`/`systemd`).
- [ ] No VAD-relay gate (deferred); no `test_main_*`/SIGTERM/child-crash tests (other tasks).
- [ ] No `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md`/README/ACCEPTANCE changes.

---

## Anti-Patterns to Avoid

- ❌ Don't edit `daemon.py` (or any source) — S1 owns the `_disarm()` fix (already at line 875). This is a pure test append. (CRITICAL #6.)
- ❌ Don't start a `run()` thread or use `_wait_for` — the fakes make `start()`/`stop()`/`toggle()`/`_maybe_auto_stop()` directly callable; the tests are synchronous. (CRITICAL #1.)
- ❌ Don't use `time.monotonic()` — the file aliases it as `_time` (@350). Use `_time.monotonic()`. (CRITICAL #2.)
- ❌ Don't weaken the assertion to `"idle" in fb.phases` — assert `fb.phases[-1] == "idle"` (the LAST `set_phase` is the invariant; pre-fix the last value is the stuck VAD phase). (CRITICAL #3.)
- ❌ Don't skip the `d.is_listening() is False` check — it proves the disarm happened, not just that phase is incidentally idle. (CRITICAL #4.)
- ❌ Don't read state.json from a private attr — use `tmp_path/"state.json"` (the documented `_make_daemon_with_feedback` path); add `import json  # noqa: E402`. (CRITICAL #5, GOTCHA #10.)
- ❌ Don't insert the tests mid-file (would split an existing section) — APPEND at END under a section banner. (GOTCHA #8.)
- ❌ Don't add the VAD-relay gate or any `recorder_host.py` change — deferred by S1 ("only if observed"). (CRITICAL #7.)
- ❌ Don't invent ruff/mypy gates (not configured). Don't use bare `python`/`pytest`/`uv` (zsh aliases). (GOTCHA #9, #10.)
- ❌ Don't edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`/README/ACCEPTANCE.

---

## Confidence Score

**9/10** for one-pass implementation success. All 4 tests are given verbatim and were each verified PASSING against the current (S1-fixed) tree; the test-fake APIs, the `_time` alias, the `tmp_path/"state.json"` path, and the auto-stop time-advancement idiom are all confirmed live against the actual `tests/test_daemon.py` (line numbers cited); the regression property (tests FAIL without S1's `set_phase('idle')` line) is verified by simulation; and the tests are synchronous/deterministic (no run loop, no real sleep, no flakiness). The residual uncertainty (−1) is purely the parallel-execution ordering: S1 must have landed its one line in `_disarm()` (it already has — `daemon.py:875`); if for any reason it had not, tests (a)/(b)/(c)/(d) would fail at the `phase == 'idle'` assertion, which is the correct, loud signal (the implementer then confirms S1 is in place rather than weakening the test).
