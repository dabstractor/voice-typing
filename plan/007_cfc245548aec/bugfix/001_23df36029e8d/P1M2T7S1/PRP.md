# PRP — P1.M2.T7.S1: Clear `_final_pending` when the cancelled sentinel is consumed (BUG-007)

## Goal

**Feature Goal**: After a Backspace-cancel, a subsequent stop (`voicectl stop` / hotkey toggle-off) must disarm **immediately** (the normal idle-stop path: `_disarm()` + `_safe_abort()`), never entering the ~5s graceful-drain wait. Today the cancelled sentinel final is dropped by `on_final`'s `_cancel_suppress_final` branch via an early `return` that skips the `self._final_pending = False` bookkeeping, so the daemon forever believes "an utterance is in flight" until the next arm/disarm — and `_request_stop()` then drains, blocking the stop for `_DRAIN_TIMEOUT_S = 5.0` seconds waiting for a final that can never come (the cancelled utterance's audio was discarded by the child).

**Deliverable**: A minimal, surgical change to `voice_typing/daemon.py` `on_final()`'s cancel-suppression branch: when `consume_cancel_mark()` returns `True` (the marked sentinel was just consumed and the suppression window closed), also (a) clear `self._final_pending` and (b) set `self._utterance_finalized = True` — mirroring the bookkeeping of the other two `on_final` exits (rejected-final and clean-final). Plus daemon-level regression tests in `tests/test_daemon.py` using the existing cancel-test doubles.

**Success Definition**:
1. New regression test: sentinel consumed → `d._final_pending is False` (fails on current code) → `d.stop()` disarms immediately (`_drain` stays `False`, `is_listening()` becomes `False`, recorder aborted like any idle stop).
2. All existing tests in `tests/test_daemon.py` stay green — in particular `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`, `test_cancel_then_next_utterance_streams_live_daemon_level`, and the drain tests (`test_stop_drains_when_utterance_in_flight`, `test_drain_timeout_aborts_blocked_text`).
3. The re-said utterance after a cancel still gets correct drain semantics: genuinely-new speech (after the run loop re-enters `text()`) re-arms `_final_pending`, so a stop mid-re-said-utterance still drains (guarded by a new test).

## User Persona (if applicable)

**Target User**: The dictation end user (and, in tests, the daemon maintainer).

**Use Case**: "Scratch that, done" — the user dictates a fragment, presses Backspace to cancel it (mic stays hot), decides they're finished, and presses the stop hotkey / runs `voicectl stop`.

**User Journey**: Arm → speak a fragment → press Backspace (cancel: fragment deleted, audio discarded, mic stays hot) → press stop → **expect**: recording stops instantly (as it does when idle). **Current**: disarm hangs ~5s behind the drain watchdog before the stop completes.

**Pain Points Addressed**: A natural cancel-then-stop sequence stalls the disarm for the full 5s watchdog window; from the user's perspective the daemon appears wedged right at the moment they asked it to stop (the exact "wedge" UX this repo's AGENTS.md treats as the cardinal sin).

## Why

- **Business value / user impact**: BUG-007 (PRD Minor Issue 3). The flagship Backspace-cancel feature (PRD §4.2quater) leaves the drain heuristic poisoned; every "cancel, then stop" sequence pays a 5-second penalty. Silent multi-second hangs erode trust in a dictation tool whose whole value proposition is responsiveness.
- **Integration with existing features**: The graceful-stop drain (`_request_stop` → `_begin_drain` → `_complete_drain`, watchdog `_drain_timeout`) is a deliberate, tested feature that must keep working for *genuine* in-flight utterances. This fix does not touch the drain machinery at all — it fixes the *signal* (`_final_pending`) feeding it, at the exact event (sentinel consumption) that proves the cancelled utterance is bookended.
- **Problems this solves / for whom**: For users, instant stop after cancel. For maintainers, `on_final`'s three exits become symmetric in their finalization bookkeeping (all three now clear `_final_pending` and set `_utterance_finalized`), removing a special case future edits could trip over.

## What

In `voice_typing/daemon.py`, `on_final()`, the `_cancel_suppress_final` branch currently reads (verified in the working tree; line numbers ~1132-1139 — they drift, match on text):

```python
if self._cancel_suppress_final:
    consume = getattr(self._host, "consume_cancel_mark", None)
    if callable(consume) and consume():
        self._cancel_suppress_final = (
            False  # sentinel seen; pipeline re-armed
        )
    return  # dropped: no clean, no type_text, no record_final
```

Change it so the consumed-sentinel leg also finalizes the utterance bookkeeping:

```python
if self._cancel_suppress_final:
    consume = getattr(self._host, "consume_cancel_mark", None)
    if callable(consume) and consume():
        self._cancel_suppress_final = (
            False  # sentinel seen; pipeline re-armed
        )
        # BUG-007 / P1.M2.T7.S1: the cancelled utterance is bookended HERE — its
        # audio was discarded, so no further final can ever come for it. Clear
        # _final_pending so _request_stop takes the immediate path (a drain would
        # wait _DRAIN_TIMEOUT_S for a final that cannot arrive), and set
        # _utterance_finalized so a stray late partial/'speech' of the cancelled
        # utterance cannot re-arm the flag before the run loop re-enters text()
        # (same validation-Issue-2 semantics as the two exits below). The run
        # loop's re-entry into text() resets _utterance_finalized, so genuinely-
        # new speech (the re-said sentence) re-arms the drain correctly.
        self._final_pending = False
        self._utterance_finalized = True
    return  # dropped: no clean, no type_text, no record_final
```

Nothing else in the production code changes. Specifically:

- The `consume()` False / not-callable legs (a *racing real* final dropped by the window, or a host without the seam) must NOT touch either flag — the marked sentinel has not arrived yet, and the legacy `recorder=` adapter path has no sentinel at all (out of scope; `_arm()` already re-arms defensively).
- `cancel()` itself must NOT clear `_final_pending`: at cancel time the sentinel hasn't landed, and stray partials/'speech' events of the dying utterance would re-arm the flag before the sentinel arrives, recreating the stale drain. The sentinel consumption (under `_on_final_lock`, serialized with the other finalize exits) is the single authoritative event.
- The drain machinery (`_request_stop`, `_begin_drain`, `_complete_drain`, `_drain_timeout`, `_DRAIN_TIMEOUT_S`) is untouched.

### Success Criteria

- [ ] After the cancelled sentinel is consumed, `_final_pending` is `False` and `_utterance_finalized` is `True` (new daemon-level test; the first assertion fails on current code).
- [ ] `stop()` after cancel-then-sentinel disarms immediately: `_drain` stays `False`, `is_listening()` becomes `False`, and the blocked text() is aborted exactly once more (2 total on the stub: 1 from cancel + 1 from the immediate-stop `_safe_abort()`).
- [ ] A stray `_touch_speech()` (late 'speech' of the cancelled utterance) after sentinel consumption does NOT re-arm `_final_pending` (the `_utterance_finalized` guard).
- [ ] After the run loop re-enters `text()` (simulated by `_utterance_finalized = False`), genuinely-new speech re-arms `_final_pending` — a stop mid-re-said-utterance still drains (no over-fix).
- [ ] Racing-real-final and lost-sentinel behaviors are unchanged (`test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`, `test_arm_clears_stale_cancel_suppression` stay green).
- [ ] Full `tests/test_daemon.py` passes.

## All Needed Context

### Context Completeness Check

_If someone knew nothing about this codebase, would they have everything needed to implement this successfully?_ **Yes** — this PRP states the exact branch to modify (quoted verbatim), the exact two flag stores to add, the threading rationale, the test doubles to use (with their file/line locations and seam methods), and the timeout-wrapped validation commands mandated by this repo's AGENTS.md.

### Documentation & References

```yaml
# MUST READ - Include these in your context window
- file: voice_typing/daemon.py
  why: on_final()'s _cancel_suppress_final branch (~lines 1132-1139) is THE edit site; _request_stop()
        (~1416-1441) is the consumer of _final_pending; the run loop (~1027-1033) resets
        _utterance_finalized on text() re-entry; cancel() (~1636-1666) arms the window;
        _begin_drain/_complete_drain/_drain_timeout (~1668-1727) are the drain machinery (DO NOT TOUCH).
  pattern: note how the OTHER two on_final exits finalize bookkeeping — rejected-final path
        (~1158: _final_pending=False, _utterance_finalized=True) and clean-final path (~1176).
        The fix makes the sentinel exit symmetric with them.
  gotcha: line numbers in the PRD snapshot are stale (P1.M1 fixes shifted them) — match on the
        quoted code text, not line numbers. Also: the codebase contains comments labeled
        "P1.M2.T7.S1" from a PREVIOUS plan's numbering (the cancel feature itself); today's
        P1.M2.T7.S1 is THIS bugfix — do not be confused when you see them.

- file: voice_typing/recorder_host.py
  why: the sentinel lifecycle — RecorderHost.cancel() (:286-301) sets cancel_event then abort_event;
        the child discards buffered audio and emits ("final", {text:"", cancelled:true}); the reader
        thread sets _cancel_mark (:436) just before relaying; consume_cancel_mark() (:307-317) is
        read-and-clear with per-event semantics.
  pattern: consume() returns True exactly once, for the sentinel final itself.
  gotcha: a plain (unmarked) final resets the mark to False — consume() True means THE sentinel,
        never a racing real final.

- file: tests/test_daemon.py
  why: the test doubles and the exact patterns to copy for the regression tests.
  pattern: _make_cancel_daemon() (:4451) — armed daemon + resident _FakeHost + _text_in_flight set;
        the _FakeHost (:560-645) exposes mark_cancel_sentinel() (test seam simulating the reader
        thread having marked the relayed final), consume_cancel_mark(), cancel_calls, and the wrapped
        _StubRecorder whose .aborts the stop tests assert on. Drive d.cancel()/d.on_final("")/
        d._touch_speech()/d.stop() DIRECTLY — no threads run (that is the established style; the
        tests call daemon seams synchronously).
  gotcha: _FakeBackend.press_backspace appends ("bs", n) tuples into be.typed (not strings).
        test_daemon.py is doubles-only: fast and CUDA-free.

- file: tests/test_daemon.py:765-831 and :4526-4552
  why: the drain tests (test_stop_drains_when_utterance_in_flight, test_drain_timeout_aborts_blocked_text,
        test_on_final_clears_final_pending) and the suppression test
        (test_cancel_suppression_drops_racing_final_and_clears_on_sentinel) that MUST stay green.
  pattern: they simulate the run loop by hand (_touch_speech() then _text_in_flight.set()).
  gotcha: d.stop() while _text_in_flight is set and _final_pending True sets _drain=True and starts a
        REAL 5s Timer — tests that assert the immediate path must assert d._drain is False right
        after stop() (the timer thread is harmless, it no-ops when _drain is False... actually
        _drain_timeout checks self._drain first — but prefer asserting _drain is False immediately
        to keep tests deterministic; see existing test_stop_disarms_immediately_when_idle).

- file: AGENTS.md
  why: MANDATORY operational rules for this repo — every test/CLI command gets an inner GNU
        `timeout` AND a bash-tool timeout; never run the daemon in the foreground; voicectl always
        under `timeout 30`.
  pattern: `timeout 600 uv run pytest tests/test_daemon.py -q` with bash-tool timeout 900.
  gotcha: several suites (test_feed_audio/test_recorder_host/test_daemon in full-CUDA configs)
        load real models — that is why this PRP's validation sticks to the doubles-only
        test_daemon.py with -k filters when iterating.

- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M2T7S1/research/codebase-analysis.md
  why: the research notes backing this PRP — verified current line numbers, threading/race
        analysis, the rejected alternative (clearing in cancel()), and the repro sequence.
  section: all

- url: https://docs.python.org/3/library/threading.html#threading.Event
  why: _text_in_flight is a threading.Event; _listening is an Event; the stores we add are plain
        atomic bools under _on_final_lock (CPython) — consistent with the __init__ comment style
        at daemon.py ~654-661 documenting _cancel_suppress_final's own memory-model reasoning.
  critical: do NOT take self._lock inside the on_final suppression branch — it runs under
        _on_final_lock already, and _lock is the control-socket serialization lock.
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
├── daemon.py          # THE edit site: on_final() suppression branch (+ comments only elsewhere)
├── recorder_host.py   # sentinel machinery (read-only context; NO changes)
├── streaming.py       # engine (NO changes)
├── config.py, ctl.py, feedback.py, key_listener.py, textproc.py, typing_backends.py  # NO changes
tests/
├── test_daemon.py     # add regression tests here (doubles-only, fast)
└── ...                # NO changes needed elsewhere
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
# NO new files. Two modified files only:
voice_typing/daemon.py   # +2 flag stores + comment in on_final()'s sentinel-consumption leg
tests/test_daemon.py     # +3 regression tests appended near the P1.M2.T7.S1 cancel section (~line 4620)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: This repo HANGS on untimed commands (AGENTS.md). Every pytest/voicectl invocation
#           gets an inner GNU `timeout` (exit 124 = timed out = wedged, do NOT blind-retry) and
#           the bash tool's own timeout parameter above it. Never run the daemon foreground.

# CRITICAL: on_final's suppression branch runs under self._on_final_lock on the host reader
#           thread. Do NOT acquire self._lock there (control-socket serialization lock — taking
#           it here can wedge toggle/stop). Plain bool stores are the established pattern.

# CRITICAL: _utterance_finalized=True is REQUIRED, not optional. Without it, a stray late
#           'speech'/partial of the cancelled utterance re-arms _final_pending via _touch_speech()
#           before the run loop re-enters text() — recreating the stale drain (validation Issue 2
#           was the original fix for exactly this class on the clean-final path).

# CRITICAL: Only the consume()==True leg changes. The racing-real-final leg (consume False) and
#           the legacy-host leg (consume not callable) must leave both flags untouched.

# NOTE: d.stop() in the drain state starts a REAL threading.Timer(5.0). Tests asserting the
#       immediate path should assert d._drain is False immediately after stop() (mirrors
#       test_stop_disarms_immediately_when_idle); the daemon never quits in unit tests, so the
#       timer thread is daemon=True and harmless, but keep assertions synchronous.

# NOTE: pyproject has NO ruff/mypy — validation is pytest-only. Python 3.12, uv-managed.
```

## Implementation Blueprint

### Data models and structure

None — no data models change. The two flags already exist on `VoiceTypingDaemon` (`__init__`, daemon.py ~672-694) with documented semantics; this fix extends the set of events that transition them.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — on_final()'s _cancel_suppress_final branch
  - IMPLEMENT: inside the `if callable(consume) and consume():` leg, after clearing
    _cancel_suppress_final, add `self._final_pending = False` and
    `self._utterance_finalized = True` with the comment text given in the What section.
  - FIND pattern: the branch is the FIRST thing under `with self._on_final_lock:` in on_final
    (after the listening gate which stays OUTSIDE the lock). Match on
    `if self._cancel_suppress_final:` — current location ~line 1132.
  - PRESERVE: the trailing `return` fires for BOTH legs (window still open AND just closed) —
    the sentinel final itself is never cleaned/typed/recorded.
  - UPDATE the __init__ comment for _final_pending (~line 672-680) with one sentence: it is
    also cleared when the cancelled sentinel is consumed (BUG-007). Optional but keeps the
    documented invariant ("True from the first speech ... until its final is typed") truthful.

Task 2: CREATE regression tests in tests/test_daemon.py (append to the P1.M2.T7 cancel section, ~line 4620, right after test_cancel_then_next_utterance_streams_live_daemon_level and its sibling — put a section header comment in the house style:
  "# ===========================================================================\n# P1.M2.T7.S1 — BUG-007 daemon level: stop right after a Backspace-cancel\n# disarms immediately (the cancelled sentinel clears _final_pending).\n# ===========================================================================")
  - TEST A `test_stop_after_cancel_disarms_immediately`:
      d, _fb = _make_cancel_daemon()
      d._touch_speech()                    # speech happened -> _final_pending=True (pre-condition assert)
      assert d._final_pending is True
      d.cancel()                           # suppression window armed; host.cancel() called
      assert d._cancel_suppress_final is True
      d._host.mark_cancel_sentinel()       # reader thread marked the relayed sentinel
      d.on_final("")                       # sentinel consumed: window closes + flags finalize
      assert d._cancel_suppress_final is False
      assert d._final_pending is False     # FAILS BEFORE THE FIX (the core regression assertion)
      assert d._utterance_finalized is True
      d.stop()                             # _text_in_flight is still set from the helper
      assert d._drain is False             # immediate path, NOT a drain (fails before the fix:
                                           #   stop() would set _drain=True)
      assert d.is_listening() is False
      # the stop aborted the blocked text() exactly once MORE than cancel() already had
      # (host.cancel() rides the abort path in _FakeHost: aborts==1 after d.cancel()):
      assert d._host.recorder.aborts == 2  # +1 from the immediate-stop _safe_abort()
      (docstring: cite BUG-007 / PRD Minor Issue 3 — cancel-then-stop must not pay the 5s drain)
  - TEST B `test_sentinel_consumption_blocks_stray_partial_rearm`:
      same setup through d.on_final(""), then
      d._touch_speech()                    # stray late 'speech' of the CANCELLED utterance
      assert d._final_pending is False     # _utterance_finalized guard holds (validation Issue 2 parity)
  - TEST C `test_next_utterance_after_cancel_rearms_final_pending` (guards against over-fixing):
      same setup through d.on_final(""), then
      d._utterance_finalized = False       # the run loop re-entered text() for the next utterance
      d._touch_speech()                    # genuinely-new speech (the re-said sentence)
      assert d._final_pending is True      # in-flight again -> stop would still drain (unchanged)
  - FOLLOW pattern: _make_cancel_daemon() + direct seam calls, mirroring
    test_cancel_suppression_drops_racing_final_and_clears_on_sentinel (:4526). No threads, no CUDA.
  - NAMING: test_* function style of the file (snake_case, descriptive).
  - PLACEMENT: tests/test_daemon.py, in/after the existing P1.M2.T7 cancel section.

Task 3: RUN validation (see Validation Loop) and fix any fallout. Expected fallout: NONE in
  production code; if test_cancel_then_next_utterance_streams_live_daemon_level or any drain test
  regresses, the likely cause is touching the wrong leg (racing-final leg) or clearing flags in
  cancel() instead — re-read the What section.
```

### Implementation Patterns & Key Details

```python
# The exact production diff (match on text; line numbers have drifted since the PRD snapshot):

# BEFORE (voice_typing/daemon.py, on_final, under `with self._on_final_lock:`):
#     if self._cancel_suppress_final:
#         consume = getattr(self._host, "consume_cancel_mark", None)
#         if callable(consume) and consume():
#             self._cancel_suppress_final = (
#                 False  # sentinel seen; pipeline re-armed
#             )
#         return  # dropped: no clean, no type_text, no record_final

# AFTER — only the consume()-True leg gains the two finalize stores (comment condensed):
#     if self._cancel_suppress_final:
#         consume = getattr(self._host, "consume_cancel_mark", None)
#         if callable(consume) and consume():
#             self._cancel_suppress_final = False   # sentinel seen; pipeline re-armed
#             # BUG-007 / P1.M2.T7.S1: the cancelled utterance is bookended here — its audio
#             # was discarded, no further final can come. Clear _final_pending so _request_stop
#             # stops immediately (a drain would wait _DRAIN_TIMEOUT_S for a final that cannot
#             # arrive), and set _utterance_finalized so a stray late partial cannot re-arm the
#             # flag before the run loop re-enters text() (validation-Issue-2 semantics, same as
#             # the two exits below). text() re-entry resets the flag, so genuinely-new speech
#             # re-arms the drain correctly.
#             self._final_pending = False
#             self._utterance_finalized = True
#         return  # dropped: no clean, no type_text, no record_final

# WHY HERE (threading): on_final runs on the host reader thread under _on_final_lock; plain bool
# stores are atomic in CPython and each writer owns the full transition — the same memory-model
# reasoning the __init__ comment (~:654-661) documents for _cancel_suppress_final itself.
# WHY NOT cancel(): at cancel() time the sentinel hasn't landed; stray partials of the dying
# utterance would re-arm _final_pending before the sentinel arrives. Sentinel consumption is the
# single authoritative bookend, serialized with the other finalize exits by _on_final_lock.
# WHY _utterance_finalized TOO: _touch_speech() (daemon.py ~1386-1396) re-arms _final_pending on
# every 'speech' event unless _utterance_finalized is True. The run loop (~:1027-1033) resets it
# False on text() re-entry — one ~50ms loop iteration later — so the re-said utterance's drain
# semantics are preserved (pinned by TEST C).
```

### Integration Points

```yaml
NO integration points beyond the single branch:
  DATABASE: none
  CONFIG:   none (no new config keys; behavior is unconditional)
  ROUTES:   none (control socket's stop/toggle routing via _request_stop benefits automatically)
  DOCS:     tests/ACCEPTANCE.md is NOT touched by this subtask (P1.M3.T9 owns doc sync).
            README.md untouched (P1.M3.T9.S1). Do not edit PRD.md / tasks.json (forbidden).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# No ruff/mypy in this project — compile check is the smoke test:
timeout 60 uv run python -m py_compile voice_typing/daemon.py tests/test_daemon.py
# Expected: silent success (exit 0). Bash-tool timeout: 120.
```

### Level 2: Unit Tests (Component Validation)

```bash
# Targeted: the new tests + every test that touches the touched machinery:
timeout 300 uv run pytest tests/test_daemon.py -q -k "cancel or sentinel or drain or final_pending or request_stop"
# Expected: all pass, including the 3 new tests (TEST A fails before the fix — verify by
# stashing the daemon change if you want to confirm the regression test actually bites).

# Full fast suite for the file (doubles-only, ~seconds):
timeout 600 uv run pytest tests/test_daemon.py -q
# Expected: 0 failures. Bash-tool timeout: 900.
```

### Level 3: Integration Testing (System Validation)

```bash
# Cross-suite consistency: the streaming engine suites pin the cancel/suppression seams
# (they must be unaffected — this PRP touches only daemon.py):
timeout 300 uv run pytest tests/test_streaming.py tests/test_streaming_core.py tests/test_streaming_commit.py tests/test_streaming_freeze.py -q
# Expected: 0 failures.

# Recorder-host sentinel semantics (read-only dependency, should be untouched):
timeout 300 uv run pytest tests/test_recorder_host.py -q -k "cancel or sentinel"
# Expected: 0 failures. (Full test_recorder_host.py loads CUDA models — the -k filter keeps it
# bounded; if the filtered selection still loads models and exceeds the inner timeout, report
# exit 124 rather than raising the timeout blindly — see AGENTS.md.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# OPTIONAL live confirmation (only if a daemon is already running under systemd per AGENTS.md —
# do NOT spawn one for this). With the fixed daemon and the unit tests green this is redundant:
#   1. arm dictation (hotkey), speak a short fragment
#   2. press Backspace mid-fragment (cancel), then immediately the stop hotkey
#   3. stop must complete instantly (no ~5s lag); `timeout 15 .venv/bin/voicectl status` shows
#      listening: off right away
# All voicectl calls MUST be wrapped in `timeout 30` (control socket has no read timeout).
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 compile check passes
- [ ] `timeout 600 uv run pytest tests/test_daemon.py -q` — all pass (Level 2)
- [ ] Streaming + recorder-host suites pass (Level 3)
- [ ] New TEST A assertion `d._final_pending is False` after sentinel consumption verified to FAIL on the pre-fix code (proves the test bites)

### Feature Validation

- [ ] Stop after cancel-then-sentinel: `_drain` False, `is_listening()` False, exactly one additional abort beyond cancel's — immediate disarm (Success Criterion 2)
- [ ] Stray `_touch_speech()` post-sentinel does not re-arm `_final_pending` (TEST B)
- [ ] Post-`text()`-re-entry speech DOES re-arm `_final_pending` — mid-re-said-utterance stop still drains (TEST C)
- [ ] Racing-real-final drop, lost-sentinel `_arm()` re-arm, and all drain behaviors unchanged (existing tests green)
- [ ] The `consume()` False / not-callable legs are byte-identical to before

### Code Quality Validation

- [ ] Only `voice_typing/daemon.py` (one branch + comments) and `tests/test_daemon.py` (3 tests + section header) modified
- [ ] Comment style matches the file's dense invariant-documentation house style (see neighboring comments)
- [ ] No new locks, threads, config, or APIs
- [ ] PRD.md / tasks.json / prd_snapshot.md untouched (forbidden files)

### Documentation & Deployment

- [ ] The `_final_pending` `__init__` comment (if updated in Task 1) stays truthful: cleared on real final, rejected final, AND cancelled-sentinel consumption
- [ ] ACCEPTANCE.md / README.md left for P1.M3.T9 (out of scope here)
- [ ] No environment variables introduced

## Anti-Patterns to Avoid

- ❌ Don't clear `_final_pending` inside `cancel()` — the sentinel hasn't arrived yet; stray partials would re-arm it (see Implementation Patterns)
- ❌ Don't touch the `consume()` False / not-callable legs — racing-real-final drop and lost-sentinel recovery are load-bearing tested behaviors
- ❌ Don't modify the drain machinery (`_request_stop`, `_begin_drain`, `_complete_drain`, `_drain_timeout`, `_DRAIN_TIMEOUT_S`) — the bug is the signal, not the consumer
- ❌ Don't take `self._lock` in the on_final branch (it runs under `_on_final_lock`; `_lock` is the control-socket serialization lock)
- ❌ Don't skip the `_utterance_finalized = True` store — without it the fix is incomplete (stray-partial re-arm window)
- ❌ Don't run any command without an inner `timeout` + bash-tool timeout (AGENTS.md Rule 1); never run the daemon foreground (Rule 2)
- ❌ Don't edit PRD.md, tasks.json, prd_snapshot.md, or .gitignore (forbidden)

---

**Confidence Score: 9/10** — one-pass success highly likely. The production change is two atomic bool stores in a single already-identified branch with fully-quoted before/after code; the test infrastructure (`_make_cancel_daemon`, `_FakeHost.mark_cancel_sentinel`) already exists and is proven by adjacent tests; the only residual risk is line-number drift (mitigated by text-match instructions) and the subtle `_utterance_finalized` semantics, both documented above with pinning tests.
