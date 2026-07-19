# PRP — P1.M2.T1.S1: Add `_final_pending` reset to `_arm()`/`_disarm()` + stale-partial drain regression test

## Goal

**Feature Goal**: Fix bugfix **Issue 2** (Major): a stale `_final_pending` (set True by stray/late realtime partials after a final, cleared ONLY by `on_final()`, never by `_arm()`/`_disarm()`) makes `_request_stop()` choose the 5-second drain path instead of disarming immediately on a stop after a finalized utterance — violating PRD §4.2 #2 ("if nothing is in flight … it disarms immediately + aborts — responsive"). The minimal, safe fix: reset `self._final_pending = False` in `_arm()` (fresh session = no utterance in flight) and `_disarm()` (defense in depth) — two one-line additions — plus a regression test that simulates the stray partial (the scenario the existing `test_stop_aborts_immediately_when_text_idle_no_speech` misses because it never calls `_touch_speech()`).

**Deliverable** (2 files; no new files):
1. `voice_typing/daemon.py` — (a) in `_arm()`, add `self._final_pending = False` right after `self._listening.set()`; (b) in `_disarm()`, add `self._final_pending = False` right after `self._listening.clear()`. Verbatim oldText→newText below.
2. `tests/test_daemon.py` — add 3 regression tests in the drain block (after `test_on_final_clears_final_pending`): `test_arm_resets_stale_final_pending_from_prior_session`, `test_disarm_clears_final_pending`, `test_stop_after_stray_partial_in_fresh_session_disarms_immediately`. Verbatim below.

**Success Definition**:
- (a) `_arm()` and `_disarm()` each set `self._final_pending = False` (at the top, right after the listening-flag flip).
- (b) The 3 new tests are RED before the daemon.py edit (stale True persists) and GREEN after.
- (c) `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or final_pending or stop_aborts or touch_speech'` → all pass (baseline 6 → 9 after adding 3); `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'arm or disarm'` → all pass (baseline 30). The existing drain tests stay green (they call `_touch_speech()` within the armed session, after `_arm()` resets it).
- (d) `_touch_speech()`, `on_final()`, `_request_stop()`, `_begin_drain()`, `_complete_drain()`, `_drain_timeout()` are UNMODIFIED.
- (e) Only `voice_typing/daemon.py` + `tests/test_daemon.py` changed.

## User Persona

Not applicable (internal lifecycle-state fix; no user-facing/config/API surface — DOCS: none. PRD §4.2 #2 already describes the intended immediate-stop behavior; this makes the code match).

## Why

- **PRD §4.2 #2 responsiveness violation.** After a final lands + `text()` re-enters (waiting for the next utterance), the realtime model fires stray/tail-end partials → each `_touch_speech()` re-sets `_final_pending=True`. The next stop sees `_text_in_flight and _final_pending` → drains the full `_DRAIN_TIMEOUT_S = 5.0s` (no real speech → no final → watchdog abort at 5s). The common case — speak a phrase, pause for the final, press stop — takes 5s instead of being instant, and the mic stays armed (ambient noise → unwanted typed final) during the drain.
- **Minimal, safe, root-cause fix.** Resetting `_final_pending` on arm/disarm gives a clean cross-session slate. The existing drain machinery (`_request_stop`/`_begin_drain`/`_complete_drain`/`_drain_timeout`) is correct and untouched. The deeper within-session fix (VAD-gated `_touch_speech`) is explicitly out of scope ("a more thorough fix" per the bug report) — this task ships the minimal arm/disarm reset.
- **Closes the test gap.** `test_stop_aborts_immediately_when_text_idle_no_speech` manually sets `_text_in_flight` without `_touch_speech()` → it never exercises the stray partial. The new test does, and pins the fix as a committed regression.

## What

Two one-line source additions (`_final_pending = False` in `_arm` + `_disarm`) + three regression tests. No behavior change for the genuine drain case (an utterance truly in flight still drains); only the stale-flag spurious drain is eliminated.

### Success Criteria

- [ ] `_arm()`: `self._final_pending = False` right after `self._listening.set()`.
- [ ] `_disarm()`: `self._final_pending = False` right after `self._listening.clear()`.
- [ ] 3 new tests added; RED before the edit, GREEN after.
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or final_pending or stop_aborts or touch_speech'` → 9 passed (baseline 6 + 3 new).
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'arm or disarm'` → 30 passed (unchanged).
- [ ] `_touch_speech`/`on_final`/`_request_stop`/`_begin_drain`/`_complete_drain`/`_drain_timeout` unmodified.

## All Needed Context

### Context Completeness Check

_Pass._ The `_final_pending` lifecycle (init/set/clear/check sites with file:line), the exact verbatim anchors for both edits (unique — `_listening.set()` only in `_arm`, `_listening.clear()` only in `_disarm`), the reason every existing drain/arm/disarm test stays green (they call `_touch_speech()` AFTER `_arm` resets it), the 3 verbatim new tests, the verified baselines (6 + 30 passed), and the no-overlap boundary with the parallel Issue-1 task are all below + in the research note. An agent new to this repo can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — lifecycle + verbatim anchors + why existing tests stay green + the regression scenario
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/P1M2T1S1/research/final_pending_reset.md
  why: "§1 the _final_pending lifecycle table (init:638, set:1059, clear:973, check:1084 — NEVER reset in _arm/_disarm = the bug).
        §2 the two verbatim edit anchors. §3 why every existing drain/arm/disarm test stays GREEN (they call _touch_speech AFTER
        _arm resets). §4 the 3 regression tests + the uncovered stray-partial scenario. §5 scope + parallel boundary."

# THE BUG REPORT (Issue 2) — root cause + the suggested fix (exactly this task)
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/prd_snapshot.md
  why: "§h3.1 Issue 2: '_final_pending is NEVER reset in _arm() or _disarm()' → spurious 5s drain. Suggested fix: 'Reset
        _final_pending = False in _arm() (a fresh arm means no utterance is in flight yet). Optionally also reset it in _disarm()
        for defense in depth.' This PRP implements BOTH (arm + disarm) + the regression test."

# THE EDIT SITES (daemon.py)
- file: voice_typing/daemon.py
  why: "_arm() (~987): the body starts `self._listening.set()` then `self._last_speech_monotonic = time.monotonic()`. _disarm()
        (~1006): starts `self._listening.clear()` then `self._last_speech_monotonic = None`. Insert the reset between each pair.
        _final_pending init:638; set by _touch_speech:1059; cleared by on_final:973; checked by _request_stop:1084
        (`if self._host is not None and self._text_in_flight.is_set() and self._final_pending:`). _DRAIN_TIMEOUT_S=5.0 (:138)."
  critical: "Anchor on `self._listening.set()` (+ the next line) for _arm and `self._listening.clear()` (+ the next line) for
             _disarm — both are UNIQUE (set() only in _arm, clear() only in _disarm). Do NOT touch any other method."

# THE TEST FILE (test_daemon.py)
- file: tests/test_daemon.py
  why: "_make_daemon() @617 returns (d, fb, rec, be); rec is _StubRecorder (rec.aborts counts abort calls @487); be is _FakeBackend
        (be.typed records typed text @503). The drain test block @683-759; test_on_final_clears_final_pending @748 is the LAST
        drain test before the idle-auto-stop section @762 — INSERT the 3 new tests right after it. test_stop_aborts_immediately_
        when_text_idle_no_speech @726 is the existing test that MISSES the bug (no _touch_speech)."
  pattern: "mirror the existing drain tests: _make_daemon() → d.start() → d._touch_speech() / d._text_in_flight.set() → d.stop() /
            d._complete_drain() → assert d._drain / d.is_listening() / rec.aborts."

# PARALLEL CONTEXT — P1.M1.T1.S1 (Issue 1, _dispatch toggle; NO overlap)
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/P1M1T1S1/PRP.md
  why: "M1.T1.S1 (Implementing) fixes ControlServer._dispatch() toggle/toggle-lite cross-mode-failure response routing + adds 2
        dispatch tests. It touches daemon.py _dispatch() (~1927) + test_daemon.py dispatch tests. NO overlap with _arm()/_disarm()/
        _final_pending/drain tests (disjoint methods + test sections). Both edit daemon.py + test_daemon.py but in different regions."
```

### Current Codebase tree (relevant slice — the 2 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py   # EDIT: _arm() ~987 (+1 line after _listening.set()) + _disarm() ~1006 (+1 line after _listening.clear()).
└── tests/
    └── test_daemon.py   # EDIT: +3 regression tests after test_on_final_clears_final_pending @748 (in the drain block).
# No other source/config/docs. _touch_speech/on_final/_request_stop/_begin_drain/_complete_drain/_drain_timeout UNCHANGED.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py    # EDIT — +1 line in _arm(), +1 line in _disarm() (self._final_pending = False).
tests/test_daemon.py      # EDIT — +3 tests in the drain block (arm-resets-stale, disarm-clears, end-to-end-stop).
# NOTHING ELSE. (ctl.py/feedback.py/config.py = untouched. README/docs = P1.M4.T1. _dispatch = P1.M1.T1.S1.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ANCHOR THE EDITS ON THE LISTENING-FLAG LINE (+ the next line). `self._listening.set()` appears ONLY in _arm;
#   `self._listening.clear()` appears ONLY in _disarm. Including the following _last_speech_monotonic line makes the oldText
#   unambiguous. Do NOT anchor on `self._final_pending` (it doesn't exist in _arm/_disarm yet — that's the bug).

# CRITICAL #2 — PLACE THE RESET IMMEDIATELY AFTER THE LISTENING-FLAG FLIP (set/clear), before anything else. A fresh arm/disarm
#   means no utterance is in flight; clearing it first thing publishes a consistent state. (The existing _last_speech_monotonic
#   reset already follows this pattern.)

# CRITICAL #3 — DO NOT MODIFY _touch_speech / on_final / _request_stop / _begin_drain / _complete_drain / _drain_timeout. They
#   are correct. The minimal fix is the arm/disarm reset. The deeper VAD-gated _touch_speech is OUT OF SCOPE ("a more thorough
#   fix" — do NOT implement VAD detection).

# CRITICAL #4 — THE EXISTING DRAIN TESTS STAY GREEN. They call _touch_speech() WITHIN the armed session AFTER _arm() resets
#   _final_pending=False; the explicit _touch_speech() re-sets it True → the drain still triggers correctly. Do NOT "fix" a test
#   by removing its _touch_speech() call. (Baseline: 6 drain/final_pending + 30 arm/disarm passed.)

# GOTCHA #5 — THE NEW TESTS MUST BE RED BEFORE THE FIX. Run them once after adding (before editing daemon.py): they should FAIL
#   (stale _final_pending True after re-arm / disarm). Then apply the daemon.py edit → GREEN. This proves the test catches the bug.

# GOTCHA #6 — WRAP EVERY PYTEST IN `timeout` (AGENTS.md — non-negotiable on this repo). Use `timeout 120 .venv/bin/python -m pytest ...`.

# GOTCHA #7 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest/uv.
#   pytest>=9.1.1 is the runner; NO ruff/mypy.
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/API change. Two one-line state resets + three regression tests.

### Implementation Tasks (ordered — TDD: tests RED first, then GREEN)

```yaml
Task 1: ADD the 3 regression tests to tests/test_daemon.py (RED — before the daemon.py fix)
  - INSERT immediately AFTER test_on_final_clears_final_pending (the last drain-block test, ~line 758, before the idle-auto-stop
    section's `# --- idle auto-stop` comment). Verbatim:
        def test_arm_resets_stale_final_pending_from_prior_session():
            """Issue 2: a fresh _arm() clears a stale _final_pending left by a stray/late partial from a prior session, so the
            next stop disarms immediately (no spurious 5s drain). Before the fix _arm() never reset _final_pending."""
            d, fb, rec, be = _make_daemon()
            d.start()
            d._touch_speech()                # speech -> _final_pending=True
            d.on_final("hello world")        # final -> _final_pending=False, text typed
            d._touch_speech()                # STRAY late partial -> _final_pending=True (stale)
            assert d._final_pending is True  # the stale state the fix must clear
            d.stop()                         # disarm (ends the prior session)
            # re-arm: _arm() must reset _final_pending=False (the fix) — no utterance is in flight yet
            d.start()
            assert d._final_pending is False  # CLEAN SLATE (fails before the fix: still True)


        def test_disarm_clears_final_pending():
            """Issue 2 (defense in depth): _disarm() clears _final_pending so a stray partial around the disarm doesn't leave it
            stale True into the next session/stop."""
            d, fb, rec, be = _make_daemon()
            d.start()
            d._touch_speech()                # _final_pending=True
            assert d._final_pending is True
            d.stop()                         # -> _disarm() (under _lock via stop)
            assert d._final_pending is False  # the fix in _disarm cleared it


        def test_stop_after_stray_partial_in_fresh_session_disarms_immediately():
            """Issue 2 end-to-end: after a re-arm (clean slate), a stop with text() idle but NO speech in THIS session disarms
            immediately (no drain) — the stale flag from the prior session was cleared by _arm(). Before the fix this drained 5s."""
            d, fb, rec, be = _make_daemon()
            d.start()
            d._touch_speech()
            d.on_final("hello world")
            d._touch_speech()                # stray stale partial (prior session)
            d.stop()                         # end prior session
            d.start()                        # re-arm -> _arm() resets _final_pending=False (the fix)
            d._text_in_flight.set()          # run loop blocked in text(), idle-waiting for the next utterance
            d.stop()                         # no speech in THIS session -> immediate disarm + abort (NOT a drain)
            assert d.is_listening() is False
            assert d._drain is False
            assert rec.aborts == 1           # immediate abort (before the fix: 0 — it drained instead)
  - RUN (RED check): `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'arm_resets_stale or disarm_clears_final or stop_after_stray'`
    → EXPECTED: 3 FAILED (the assertions on _final_pending is False / rec.aborts == 1 fail because the fix isn't in yet). This
    proves the tests catch the bug. (If they PASS already, the fix is already applied or the test is wrong — investigate.)
  - DO NOT: modify _make_daemon/_StubRecorder/_FakeBackend; call _touch_speech() AFTER d.start() in the fresh-session test (so
    the _arm reset is what's being tested, then a NEW _touch_speech would re-set it — the end-to-end test does NOT call
    _touch_speech in the fresh session, proving the stop is immediate with no speech).

Task 2: EDIT voice_typing/daemon.py — add the _final_pending reset to _arm() and _disarm() (GREEN)
  - EDIT 2a — _arm() (find `def _arm(self)` ~987). oldText -> newText:
      OLD:
            self._listening.set()
            self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh
      NEW:
            self._listening.set()
            self._final_pending = False  # Issue 2: fresh arm = no utterance in flight (clear stale stray partials)
            self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh
  - EDIT 2b — _disarm() (find `def _disarm(self)` ~1006). oldText -> newText:
      OLD:
            self._listening.clear()
            self._last_speech_monotonic = None  # not listening → idle clock is inactive
      NEW:
            self._listening.clear()
            self._final_pending = False  # Issue 2: disarm clears any stale stray-partial flag (defense in depth)
            self._last_speech_monotonic = None  # not listening → idle clock is inactive
  - WHY: _arm (fresh session, no utterance in flight → clean slate) + _disarm (defense in depth — a stray partial around the
    disarm doesn't leak into the next stop). Both anchors are unique (CRITICAL #1); placement is right after the listening flip
    (CRITICAL #2); no other method touched (CRITICAL #3).
  - DO NOT: modify _touch_speech/on_final/_request_stop/_begin_drain/_complete_drain/_drain_timeout; place the reset elsewhere;
    add a VAD check to _touch_speech (out of scope).

Task 3: VERIFY (GREEN) — run the prescribed suites.
  - RUN: `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or final_pending or stop_aborts or touch_speech'`
    → EXPECTED: 9 passed (baseline 6 + the 3 new). The existing drain tests stay green (they _touch_speech AFTER _arm resets).
  - RUN: `timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'arm or disarm'`
    → EXPECTED: 30 passed (unchanged).
  - No git commit unless the orchestrator directs it. If asked, message:
    "P1.M2.T1.S1: reset stale _final_pending in _arm()/_disarm() (Issue 2 — kills the spurious 5s drain) + 3 regression tests".
```

### Implementation Patterns & Key Details

```python
# PATTERN — reset the "utterance in flight" proxy on every session boundary. _final_pending means "speech occurred since the
# last final"; a fresh arm/disarm means NO utterance is in flight, so clear it first thing (right after the listening-flag flip),
# mirroring the existing _last_speech_monotonic reset that follows the same pattern.
# _arm:   self._listening.set(); self._final_pending = False; self._last_speech_monotonic = time.monotonic()
# _disarm: self._listening.clear(); self._final_pending = False; self._last_speech_monotonic = None

# PATTERN (test) — the existing drain tests call _touch_speech() AFTER d.start(); with the fix, _arm() resets _final_pending=False
# FIRST, then the explicit _touch_speech() re-sets it True → the drain still triggers. The NEW tests exploit the gap the existing
# ones miss: a _touch_speech() whose True value is STALE (after a final, or across a session boundary) — which the fix clears.
```

### Integration Points

```yaml
UPSTREAM/DOWNSTREAM — the _final_pending lifecycle (ALL UNCHANGED except _arm/_disarm):
  - init:638 (False); set True by _touch_speech:1059 (every realtime partial); cleared by on_final:973; checked by
    _request_stop:1084 (_text_in_flight AND _final_pending => drain else immediate). _DRAIN_TIMEOUT_S=5.0:138. The fix adds TWO
    more clear sites (_arm + _disarm) so a stale True can't persist across a session boundary.

UNCHANGED: _touch_speech(), on_final(), _request_stop(), _begin_drain(), _complete_drain(), _drain_timeout() — all correct.
  The genuine drain case (utterance truly in flight: _touch_speech AFTER _arm, then stop mid-final) still drains correctly.

PARALLEL — P1.M1.T1.S1 (Issue 1, _dispatch toggle): edits daemon.py _dispatch() (~1927) + test_daemon.py dispatch tests.
  NO overlap with _arm()/_disarm()/_final_pending/drain tests. Disjoint regions of the same files — no conflict.

BUILD ARTIFACTS: NO new files, NO pyproject/uv.lock/.venv changes, NO new deps. Validation = py_compile + pytest (both under timeout).
```

## Validation Loop

> Full paths + a functional `timeout` on EVERY command (AGENTS.md — CRITICAL #6/#7). Run from
> `/home/dustin/projects/voice-typing`. pytest>=9.1.1 (NO ruff/mypy). All gates are fast/unit (no CUDA; _StubRecorder/_FakeBackend).

### Level 1: the edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/daemon.py tests/test_daemon.py && echo "L1 PASS: py_compile" || echo "L1 FAIL"
# both resets present (exactly one each, in _arm and _disarm — NOT in _touch_speech/on_final/_request_stop):
grep -c "self._final_pending = False" voice_typing/daemon.py   # expect the EXISTING on_final:973 site + the 2 new = 3 total
# confirm _arm and _disarm each got one (by looking at the lines right after _listening.set/clear):
grep -A1 "self._listening.set()" voice_typing/daemon.py | grep -q "_final_pending = False" && echo "L1 PASS: _arm reset" || echo "L1 FAIL: _arm reset missing"
grep -A1 "self._listening.clear()" voice_typing/daemon.py | grep -q "_final_pending = False" && echo "L1 PASS: _disarm reset" || echo "L1 FAIL: _disarm reset missing"
```

### Level 2: the 3 new tests + the existing drain/arm/disarm suites (GREEN)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# the 3 new tests now PASS (were RED before the daemon.py edit):
timeout 120 "$PY" -m pytest tests/test_daemon.py -q -k 'arm_resets_stale or disarm_clears_final or stop_after_stray'
# Expected: 3 passed.
# the full drain/final_pending/stop_aborts/touch_speech slice (existing 6 + new 3):
timeout 120 "$PY" -m pytest tests/test_daemon.py -q -k 'drain or final_pending or stop_aborts or touch_speech'
# Expected: 9 passed (baseline was 6). The existing drain tests stay GREEN (they _touch_speech AFTER _arm resets).
# the arm/disarm slice (unchanged):
timeout 120 "$PY" -m pytest tests/test_daemon.py -q -k 'arm or disarm'
# Expected: 30 passed (baseline unchanged).
```

### Level 3: full fast suite (no regression) + scope guard

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
timeout 150 "$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py is the heavy GPU suite, ignored.) The fix is additive — no other test regresses.
git status --short
# Expected: ONLY voice_typing/daemon.py (modified) + tests/test_daemon.py (modified). No _touch_speech/on_final/_request_stop
# changes, no ctl/feedback/config, no docs. (P1.M1.T1.S1 may edit daemon.py _dispatch + test_daemon.py dispatch tests in parallel
# — disjoint regions, separate concern.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: py_compile clean; `_final_pending = False` appears in both `_arm()` (after `_listening.set()`) and `_disarm()` (after `_listening.clear()`).
- [ ] L2: the 3 new tests pass; drain/final_pending/stop_aborts/touch_speech slice = 9 passed; arm/disarm slice = 30 passed.
- [ ] L3: full fast sweep 0 failed; `git status` == `voice_typing/daemon.py` + `tests/test_daemon.py`.

### Feature Validation
- [ ] A fresh `_arm()` clears any stale `_final_pending` → the next stop (no speech in the fresh session) disarms immediately (no 5s drain).
- [ ] `_disarm()` clears `_final_pending` (defense in depth).
- [ ] The genuine drain case (utterance truly in flight) still drains (existing tests green).

### Code Quality Validation
- [ ] Both resets placed right after the listening-flag flip; anchored on unique `_listening.set()`/`_listening.clear()`.
- [ ] `_touch_speech`/`on_final`/`_request_stop`/`_begin_drain`/`_complete_drain`/`_drain_timeout` unmodified.
- [ ] New tests reuse `_make_daemon()`/`_StubRecorder`/`_FakeBackend`; hermetic (no external services).
- [ ] Full paths + functional `timeout` on every command.

### Scope Boundary Validation
- [ ] No VAD detection / `_touch_speech` change (the deeper within-session fix is out of scope).
- [ ] No ctl.py/feedback.py/config.py/docs changes; no `_dispatch` change (P1.M1.T1.S1).
- [ ] No new files; no new deps; no pyproject/uv.lock changes.

---

## Anti-Patterns to Avoid

- ❌ Don't anchor the edit on `self._final_pending` (it doesn't exist in `_arm`/`_disarm` yet) — anchor on `self._listening.set()`/`self._listening.clear()` (+ the next line).
- ❌ Don't modify `_touch_speech`/`on_final`/`_request_stop`/`_begin_drain`/`_complete_drain`/`_drain_timeout` — they're correct; the fix is ONLY the arm/disarm reset.
- ❌ Don't implement VAD-gated `_touch_speech` (the "more thorough fix") — explicitly out of scope; ship the minimal arm/disarm reset.
- ❌ Don't "fix" an existing drain test by removing its `_touch_speech()` call — it's correct (it calls it AFTER `_arm`, which is the genuine in-flight case). The existing tests stay green as-is.
- ❌ Don't skip the RED step — run the 3 new tests BEFORE the daemon.py edit to prove they fail (catch the bug); then GREEN after.
- ❌ Don't run pytest without a functional `timeout` (AGENTS.md); don't use bare python/pytest/uv (zsh aliases).
- ❌ Don't edit `_dispatch` (that's the parallel P1.M1.T1.S1 / Issue 1 — disjoint).
- ❌ Don't invent ruff/mypy commands — pytest only.

---

## Confidence Score

**10/10** for one-pass implementation success. The fix is two one-line additions with verified-unique verbatim anchors (`_listening.set()` only in `_arm`; `_listening.clear()` only in `_disarm`); the `_final_pending` lifecycle is fully traced (init:638 → set:1059 → clear:973 → check:1084, never reset in `_arm`/`_disarm` = the bug); the 3 verbatim regression tests cover the exact stale-partial scenario the existing suite misses; the reason every existing drain/arm/disarm test stays green is documented (they call `_touch_speech()` after `_arm` resets it); and the baselines are verified (6 + 30 passed). The no-overlap boundary with the parallel Issue-1 task (`_dispatch`) is explicit. No residual uncertainty.