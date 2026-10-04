# PRP — P1.M1.T2.S2: Daemon — lift post-cancel suppression at next utterance start (daemon-level regression test)

## Goal

**Feature Goal**: Close BUG-002 at the DAEMON level. After a Backspace-cancel, the re-said sentence must stream live (phone-style deltas), not wait ~0.8s+ for its commit. The suppression lift is wired at **`_touch_speech()` → `self._stream.resume()`** (daemon.py:1389, landed with T1.S1/T1.S2) and the engine's `resume()` clears `_suppressed` unconditionally (S1, parallel). **This subtask verifies that wiring is the ONE chosen point (comment records why), strengthens the comment if needed, and adds the daemon-level regression test the PRD demands** — replacing the masking pattern where `tests/test_streaming_core.py:291` manually invokes `stream.reset_boundary()` ("next utterance begins"), which no daemon code path ever fires post-cancel.

**Deliverable** (1 test file edited + daemon.py comment-only if needed):
1. `tests/test_daemon.py` — `test_cancel_then_next_utterance_streams_live_daemon_level`: arm → `_on_partial` types live → `cancel()` → **stale window** (`_on_partial('late partial')` types NOTHING) → `_touch_speech()` → `_on_partial('the quick brown fox')` → backend receives a **live delta type call BEFORE any commit**. Doubles only (`_make_daemon` + a host with `cancel()`/`consume_cancel_mark()`, or the :4430+ section's construction); no CUDA.
2. `voice_typing/daemon.py` — **comment-only** (verify :1382-1388's rationale covers the BUG-002 lift; add a sentence citing BUG-002/P1.M1.T2.S2 if absent). Zero logic edits expected.

**Success Definition**:
- (a) The wiring is verified as the ONE lift point: `_touch_speech()` calls `self._stream.resume()`; the on_final suppression branch (:1131-1138) consumes the sentinel WITHOUT resuming; the comment records why speech-start is the point.
- (b) The new regression test passes and encodes BOTH halves: (i) the **stale-partial guard HOLDS** after cancel (zero new backend calls until speech); (ii) after `_touch_speech()` the next partial produces a real live type call with **no commit involved**.
- (c) `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q` → all green (existing suite + the new test).
- (d) `git diff --name-only` ⊆ `{tests/test_daemon.py, voice_typing/daemon.py}`; daemon.py diff is comment-only if present at all.
- (e) S1's engine suites stay green (no streaming.py edits here): `timeout 600 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_freeze.py -q`.

> **VERIFIED STATE (research note): the wiring ALREADY LANDED.** daemon.py:1389 `self._stream.resume()` inside `_touch_speech()`, comment :1382-1388 explicitly covering "any post-cancel suppression, via the engine's resume()". S1's `resume()`-clears-`_suppressed` is in the tree (streaming.py:296, docstring :282). This subtask is **verify + pin**, not new wiring. S1's PRP states it plainly: "T2.S2 reduces to its regression test."

## User Persona

**Target User**: the dictation user who presses Backspace mid-fragment and immediately re-says the sentence. Today the re-said words freeze on screen until the commit (Rev 1 feel); after BUG-002's fix they stream live as spoken.
**Pain Points Addressed**: PRD h2.2/h3.1 (BUG-002) — "every use of the flagship Backspace-cancel feature silently degrades the very next utterance from phone-style live typing to Rev 1 append-only"; h2.5 — "clear `_suppressed` on the child's next speech/first partial after the sentinel, so the re-said sentence streams live."

## Why

- **BUG-002's daemon half.** The engine fix (S1) makes `resume()` clear `_suppressed`; the daemon must FIRE it at the right moment. The chosen point — `_touch_speech()`, the host reader's 'speech'-event hook (daemon.py:843/853 wiring) — fires on genuinely-new speech start, exactly the PRD h2.5 recommendation. The sentinel-consuming on_final branch deliberately does NOT resume (a stray late final/partial of the CANCELLED utterance must not lift suppression — only real new speech may).
- **The unit suites mask the bug.** `tests/test_streaming_core.py:291` manually invokes `stream.reset_boundary()` — an event NO daemon path fires between a cancel and the next real final (the sentinel is dropped at :1131-1138 BEFORE `commit()`/`reset_boundary()`). The PRD h2.4/h2.5 explicitly demand daemon-level regression tests that drive the daemon's own seams (`_on_partial`/`cancel`/`_touch_speech`).
- **Sequencing.** The contract OUTPUT notes P1.M2.T7.S1 (clear `_final_pending` in the sentinel branch) touches the same on_final branch AFTER this task — landing the regression test first pins the branch's current behavior before T7.S1 edits it.
- **Scope discipline.** No engine edits (S1 owns streaming.py); no listening gate (T4.S1's BUG-004); no README/ACCEPTANCE (Mode B, P1.M3.T9).

## What

1. **Verify** the wiring (Task 1 greps) — `_touch_speech` → `resume()` at the head of the method (BEFORE the `_final_pending` guard), comment citing both freeze classes.
2. **Strengthen the comment** only if it lacks the BUG-002/P1.M1.T2.S2 citation (research shows it covers post-cancel; add one sentence if the task-ID lineage is missing).
3. **Add the regression test** (TDD: write it, expect GREEN — the wiring landed; if RED, the daemon-side gap is in `_touch_speech` ordering or `_reset_stream_after_cancel`, fix minimally).

### Success Criteria

- [ ] `_touch_speech()`'s FIRST stream action is `self._stream.resume()` (before the `_final_pending` guard); the comment names the rejected-final AND post-cancel lift + why speech-start (not the sentinel branch) is the point.
- [ ] The on_final suppression branch does NOT call resume (one wiring point only).
- [ ] `test_cancel_then_next_utterance_streams_live_daemon_level` exists in tests/test_daemon.py, docstring citing BUG-002 / P1.M1.T2.S2 + the masking pattern it replaces (:291's manual `reset_boundary()`).
- [ ] The test's stale-window leg asserts ZERO new backend calls after `cancel()` + a late partial.
- [ ] The test's landing leg asserts a live type call (empirically pinned, see Gotcha #1) with NO commit in the sequence.
- [ ] Focused + full daemon suites green; S1's engine suites untouched and green.
- [ ] `git diff --name-only` ⊆ {tests/test_daemon.py, voice_typing/daemon.py}; daemon.py comment-only.

## All Needed Context

### Context Completeness Check

_Pass._ The wiring site, the cancel flow (including the `_text_in_flight`-and-host gate), the suppression branch, the test doubles (`_make_daemon` @682, `_FakeHost.cancel` @625 / `consume_cancel_mark` @630, the :4430+ cancel-test section with its streaming stand-in), the masking pattern (:291), and the event order (speech before partials; `_on_partial` deliberately does not call `_touch_speech`) are all verified with line numbers in the research note. An agent new to the repo can implement from this PRP + the note.

### Documentation & References

```yaml
# MUST READ — the verified wiring + cancel flow + test seam
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T2S2/research/postcancel_lift_wiring_and_test_seam.md
  why: "§1 the wiring-is-landed evidence (:1389 + comment :1382-1388 + S1's 'T2.S2 reduces to its
        regression test'); §2 the cancel flow incl. the _text_in_flight-and-host gate the test must
        satisfy; §3 the suppression branch (read-only); §4 the test seam (incl. :4430+ to mirror and
        :291 being replaced); §5 sibling boundaries."
  critical: "Expected source delta is ZERO-to-comment-only. If the regression test is RED, the fix is in
            daemon.py's _touch_speech ordering or the test's construction — NOT in streaming.py (S1's)."

# MUST READ — the bug + the mandate
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: "h2.2/h3.1 (BUG-002 full description + repro) + h2.5 ('clear _suppressed on the child's next
        speech/first partial after the sentinel') + h2.4 (the daemon-level regression-test demand)."
  critical: "The test must be DAEMON-level (drive d._on_partial / d.cancel / d._touch_speech) — engine-
            level pinning already exists in S1's test_streaming_freeze.py."

# MUST READ — the engine contract this wiring consumes (parallel sibling)
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T2S1/PRP.md
  why: "resume() clears _suppressed ALWAYS (streaming.py:296) — the ONE seam, no second API; S1's own
        repro test (test_cancel_then_resume_restores_live_delta_typing) is the ENGINE twin whose
        empirical-delta gotcha (CRITICAL #1) this task mirrors at daemon level."
  critical: "If S1 has not landed (grep streaming.py:296 'self._suppressed = False' inside resume), the
            daemon test's stale-window/landing legs misbehave — gate on it (Task 0)."

# THE WIRING SITE + THE BRANCH (read-only verification targets)
- file: voice_typing/daemon.py
  why: "_touch_speech @1365 (resume() @1389 FIRST, comment @1382-1388); on_final suppression branch
        @1126-1157 (sentinel consume_cancel_mark, NO resume — keep it that way); cancel() @1621-1655
        (the _text_in_flight + host gate at :1647-1652; _reset_stream_after_cancel @1653);
        _reset_stream_after_cancel @1454-1463; _on_partial @1394."
  pattern: "Comment-only edit target: :1382-1388. Add ONE sentence citing 'BUG-002 / P1.M1.T2.S2' if
            the lineage is absent — do not restructure the comment."
  gotcha: "Do NOT move/duplicate the resume() call into the on_final branch — ONE wiring point is the
           contract; the sentinel branch resuming would let a stray late final lift suppression."

# THE TEST FILE + THE PATTERN TO MIRROR
- file: tests/test_daemon.py
  why: "_make_daemon @682 (recorder/recorder_host/host_factory/backend/cfg kwargs); _FakeHost.cancel @625
        + consume_cancel_mark @630; the P1.M2.T7.S1 cancel-test section @4430+ (a streaming stand-in
        @4436 with reset_after_cancel @4446; the note @4455 'No threads run; tests call cancel()/
        on_final() directly'); the legacy streaming-core masking at tests/test_streaming_core.py:291."
  pattern: "READ the :4430+ section FIRST; mirror its daemon construction but prefer the REAL
            StreamingOutput (streaming cfg) so deltas flow to _FakeBackend — the stand-in stubs them.
            Place the new test adjacent to that section under a P1.M1.T2.S2 banner."
  gotcha: "cancel()'s suppress leg needs _text_in_flight SET + a host — set d._text_in_flight.set() and
           pass a host double (recorder_host=_FakeHost(...) or the section's construction). Without
           them _cancel_suppress_final stays False and host.cancel() never runs (the test would silently
           test less than it claims)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py       # wiring LANDED (_touch_speech→resume @1389). ← comment-only edit at most.
voice_typing/streaming.py    # S1's engine seam (resume clears _suppressed @296). UNTOUCHED here.
tests/test_daemon.py         # ← ADD the regression test (near the :4430+ cancel section).
tests/test_streaming_core.py # :291 = the masking pattern replaced. UNTOUCHED (S1/other tasks own it).
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py         # MODIFY: + test_cancel_then_next_utterance_streams_live_daemon_level.
voice_typing/daemon.py       # MODIFY (comment-only, at most): strengthen :1382-1388's rationale lineage.
# No streaming.py (S1), no listening gate (T4.S1), no README/ACCEPTANCE (P1.M3.T9).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — PIN THE EXPECTED BACKEND CALLS EMPIRICALLY (S1's twin gotcha, daemon edition). After
# cancel() the tail is "" and committed is whatever preceded; after _touch_speech + _on_partial(
# 'the quick brown fox') the engine takes the fresh-fragment path (a single live type call) OR an
# extend/rewind depending on history + the 300ms rate limit. FIRST run the exact sequence in a scratch
# pytest with be.calls printed, THEN pin the observed calls. The INVARIANTS (not the exact delta):
# (i) zero new calls in the stale window; (ii) >=1 ("type", ...) lands BEFORE any commit — and this
# test sends NO on_final at all, so ANY type call in the landing leg is live-streaming by construction.
# Use FakeClock if the rate limit interferes (test_streaming_core.py:336 precedent).

# CRITICAL #2 — SATISFY cancel()'s GATE. The suppress leg (daemon.py:1647-1652) requires
# _text_in_flight.is_set() AND self._host is not None. In the test: d._text_in_flight.set() BEFORE
# d.cancel(), and construct with a host double (recorder_host=... — see the :4430+ section's approach).
# Otherwise _cancel_suppress_final stays False: the test still exercises the ENGINE suppression (the
# stale window rides _suppressed from _reset_stream_after_cancel), but it would not cover the sentinel
# machinery — cover both: set the flag AND assert _cancel_suppress_final handling via the host double
# if the section's pattern does.

# CRITICAL #3 — EXPECTED-GREEN TEST-FIRST. Write the test, run BEFORE any daemon.py edit. The wiring
# landed (research §1) — RED means a real daemon-side gap (check _touch_speech ordering: resume() must
# be FIRST, before the _final_pending guard) or a test-construction bug (CRITICAL #2). NEVER fix by
# weakening the stale-window assert (the guard holding IS half the contract).

# CRITICAL #4 — ONE WIRING POINT. Do NOT add resume() to the on_final suppression branch (the contract
# says pick ONE; the landed choice is _touch_speech — speech-start, per PRD h2.5). A stray late final of
# the cancelled utterance must NOT lift suppression; only genuinely-new speech may.

# GOTCHA #5 — THE EVENT ORDER IS FAITHFUL. RealtimeSTT fires on_speech (VAD) BEFORE partials; the
# reader calls _touch_speech on 'speech' events (wired @843/853); _on_partial deliberately does NOT
# call _touch_speech (:1402 comment). Driving d._touch_speech() then d._on_partial() mirrors the real
# sequence exactly — that's what makes this daemon-level (vs :291's manual reset_boundary).

# GOTCHA #6 — DON'T CONFLATE WITH T4.S1's GATE. _on_partial currently has NO listening gate (BUG-004,
# P1.M1.T4.S1). Keep the daemon ARMED throughout this test so the missing gate is irrelevant; do not
# add any gate here.

# GOTCHA #7 — SEQUENCING NOTE FOR P1.M2.T7.S1: it edits the same on_final suppression branch (clears
# _final_pending at the sentinel). This task lands FIRST and pins the branch's behavior; record in the
# test docstring that T7.S1 will extend the branch (its stop-after-cancel fix must keep this test green).

# GOTCHA #8 — FULL PATHS + timeout 600 (AGENTS.md). No ruff/mypy. The suite is hermetic (no CUDA/mic).
```

## Implementation Blueprint

### Data models and structure

None — no data changes. The deliverable is one regression test (+ an optional comment sentence).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — confirm both halves of the seam are in the tree
  - RUN:
      cd /home/dustin/projects/voice-typing
      grep -n 'self._stream.resume()' voice_typing/daemon.py | head -3        # expect _touch_speech's :1389
      sed -n '274,296p' voice_typing/streaming.py | grep -n '_suppressed'      # expect the always-clear in resume()
  - IF the engine clear is absent: S1 hasn't landed — STOP and flag (the stale-window/landing legs
    depend on it). IF the daemon wiring is absent: implement it per PRD h2.5 (resume() FIRST in
    _touch_speech, before the _final_pending guard, comment citing BUG-001 T1.S2 + BUG-002 T2.S2).

Task 1: READ the :4430+ cancel-test section + determine the construction
  - RUN: sed -n '4430,4470p' tests/test_daemon.py
  - Decide: mirror its construction (host double + streaming cfg + REAL self._stream so deltas flow to
    _FakeBackend). Note how it sets _text_in_flight / arms / drives cancel.

Task 2: ADD tests/test_daemon.py — the regression test (FIRST; expected GREEN per CRITICAL #3)
  - PLACE: adjacent to the :4430+ P1.M2.T7.S1 section, under a banner:
      # ===========================================================================
      # P1.M1.T2.S2 — BUG-002 daemon level: post-cancel suppression lifts at next
      # speech (_touch_speech -> stream.resume()); the re-said sentence streams live.
      # (Replaces test_streaming_core.py:291's MANUAL reset_boundary() masking — the
      #  daemon fires no boundary post-cancel; the sentinel is dropped pre-commit.)
      # ===========================================================================
  - CODE (shape; PIN the backend calls per CRITICAL #1):

        def test_cancel_then_next_utterance_streams_live_daemon_level():
            """BUG-002 / P1.M1.T2.S2: after a Backspace-cancel, the NEXT utterance's partials type
            live again (a delta lands BEFORE any commit) — suppression lifts at the daemon's
            next-speech signal (_touch_speech -> stream.resume()), not at a boundary the daemon
            never fires post-cancel (the sentinel final is dropped in on_final BEFORE commit()).

            Mirrors the live flow: speech event -> partials -> cancel (in flight) -> [stale window]
            -> next speech -> re-said partials stream live. Doubles only; no CUDA; no threads
            (we drive _on_partial/cancel/_touch_speech directly, as the T7.S1 section does).
            P1.M2.T7.S1 will extend the same suppression branch (stop-after-cancel) — it must keep
            this test green.
            """
            # construct per Task 1's findings: streaming cfg + host double with cancel()/
            # consume_cancel_mark(); backend = _FakeBackend()
            d.start()                                  # arm
            d._text_in_flight.set()                    # utterance in flight (CRITICAL #2)
            d._on_partial("the quick brown")           # live typing before the cancel
            typed_before = len(be.typed)               # or be.calls — match the section's recording
            assert typed_before > 0                    # the pre-cancel fragment typed live

            d.cancel()                                 # Backspace-cancel: tail gone, suppression on
            n_after_cancel = <backend-call count>
            d._on_partial("late partial")              # stale window: a late partial of the CANCELLED
            assert <backend-call count> == n_after_cancel   # utterance types NOTHING (guard HOLDS)

            d._touch_speech()                          # the daemon's next-utterance-start signal
            d._on_partial("the quick brown fox")       # the RE-SAID sentence...
            # ...streams live: >=1 type call landed, and NO commit was involved anywhere after the
            # cancel (this test never calls on_final) — pin the observed calls per CRITICAL #1.
            assert <a ("type", <delta>) call landed>
            # (empirically: likely the full fresh fragment as one delta — tail was reset to "")

  - CONSTRAINTS: keep the daemon armed throughout (GOTCHA #6); no on_final anywhere after cancel
    (the landing leg's type calls are live-streaming BY CONSTRUCTION); pin exact calls empirically.

Task 3: VERIFY/STRENGTHEN the daemon.py rationale comment (comment-only)
  - RUN: sed -n '1380,1392p' voice_typing/daemon.py
  - The comment (:1382-1388) already covers "any post-cancel suppression, via the engine's resume()".
    IF it lacks the task lineage, add ONE sentence: "BUG-002 / P1.M1.T2.S2: this is the ONE post-cancel
    lift point — the on_final sentinel branch deliberately does NOT resume (a stray late final of the
    cancelled utterance must not lift suppression; only genuinely-new speech may)."
  - DO NOT: move the resume() call, add a second call site, or touch any logic.

Task 4: VALIDATE — the Validation Loop. No git commit unless directed. If asked:
  "P1.M1.T2.S2: daemon-level BUG-002 regression — post-cancel suppression lifts at next speech
  (_touch_speech->resume); re-said sentence streams live; replaces the manual reset_boundary masking".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the one-wiring-point invariant (verification target, not an edit):
#   _touch_speech():  self._stream.resume()   # FIRST (before _final_pending guard) — lifts BOTH the
#                     # rejected-final freeze AND post-cancel suppression at genuinely-new speech
#   on_final suppression branch: consume_cancel_mark() only — NO resume (stray late finals stay dropped)

# PATTERN 2 — the regression test's three legs (the contract sequence, daemon-driven):
#   arm -> _on_partial (types) -> cancel (tail gone, _suppressed on) -> _on_partial('late partial')
#   -> ASSERT nothing new typed -> _touch_speech -> _on_partial('the quick brown fox')
#   -> ASSERT a live type call landed (no commit exists in the sequence at all).
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S1 (engine, parallel): resume() clears _suppressed ALWAYS. Gate on it (Task 0).
           Its engine-level repro (test_streaming_freeze.py) is the twin; this is the daemon level.
DOWNSTREAM — P1.M2.T7.S1 (clear _final_pending in the same suppression branch): lands AFTER this;
           the test docstring records that it must stay green through T7.S1's edit.
SIBLING — P1.M1.T4.S1 (BUG-004 listening gate on _on_partial): later; this test stays armed so the
           gate is irrelevant to it.
DOCS — README §Backspace-cancel sweep is Mode B (P1.M3.T9). No per-subtask docs.
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic. Run from `/home/dustin/projects/voice-typing`.

### Level 1: The wiring is the one lift point (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- _touch_speech resumes FIRST ---"
sed -n '1365,1392p' voice_typing/daemon.py | grep -n 'resume()' | head -1   # expect it before _final_pending
echo "--- the suppression branch does NOT resume ---"
sed -n '1126,1140p' voice_typing/daemon.py | grep -c 'resume()' | xargs -I{} echo "resume calls in branch: {} (expect 0)"
echo "--- the comment carries the BUG-002 lineage (post-strengthening) ---"
sed -n '1380,1392p' voice_typing/daemon.py | grep -q 'post-cancel' && echo "L1 PASS: rationale present" || echo "L1 FAIL"
# Expected: resume() in _touch_speech (early); 0 in the branch; rationale comment present.
```

### Level 2: The new regression test (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cancel_then_next_utterance" -v 2>&1 | tail -4
# Expected: PASSED. If the stale-window leg fails (something typed): suppression isn't holding — check
# Task 0's engine gate + that the test used a REAL stream (a stand-in may stub _suppressed away).
# If the landing leg fails (nothing typed): _touch_speech didn't resume — check ordering (resume FIRST).
```

### Level 3: No regressions (daemon + engine suites)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -2
timeout 600 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_freeze.py -q 2>&1 | tail -2
# Expected: both green. S1's suites untouched by this task; the daemon suite gains exactly one test.
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'tests/test_daemon.py|voice_typing/daemon.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS"
git diff voice_typing/daemon.py | grep -E '^[+-]' | grep -vE '^[+-]{3}|^[+-]\s*#' && echo "L4 FAIL: daemon.py logic changed (comment-only allowed)" || echo "L4 PASS: daemon.py comment-only"
git diff --quiet voice_typing/streaming.py && echo "L4 PASS: streaming.py untouched (S1's)" || echo "L4 NOTE: streaming.py diff is S1's parallel work, not this task's"
# Expected: only tests/test_daemon.py (+ daemon.py comments); streaming.py's diff, if any, is S1's.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `_touch_speech` resumes first; suppression branch has 0 resume calls; rationale comment present.
- [ ] L2: the regression test passes (stale-window guard HOLDS + live type lands with no commit).
- [ ] L3: daemon suite green (+1 test); S1's engine suites green and untouched.
- [ ] L4: diff ⊆ {test_daemon.py, daemon.py(comment-only)}; streaming.py untouched by this task.

### Feature Validation
- [ ] After cancel, a late partial of the cancelled utterance types NOTHING (safety unweakened).
- [ ] After the next speech signal, the re-said sentence's partials type live BEFORE any commit.
- [ ] The test drives daemon seams (`_on_partial`/`cancel`/`_touch_speech`) — not engine internals.
- [ ] The masking pattern (manual `reset_boundary()`) is documented as replaced in the test docstring.

### Code Quality Validation
- [ ] Backend calls pinned empirically (CRITICAL #1), invariants asserted explicitly.
- [ ] Test placed adjacent to the T7.S1 section; banner + docstring cite BUG-002/P1.M1.T2.S2 + T7.S1 sequencing.
- [ ] No gate added (T4.S1's), no engine edits (S1's), no second resume site.

### Scope Boundary Validation
- [ ] daemon.py comment-only; streaming.py/test_streaming_* untouched; README/ACCEPTANCE untouched.
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore untouched.

### Documentation & Deployment
- [ ] The comment lineage (BUG-002 / P1.M1.T2.S2 / one-wiring-point rationale) recorded in daemon.py.

---

## Anti-Patterns to Avoid

- ❌ Don't implement new wiring before Task 0/2 — the wiring LANDED (T1.S2); a RED test means a construction bug or a real ordering gap, not a mandate to rewire.
- ❌ Don't add `resume()` to the on_final suppression branch — ONE wiring point (speech-start); a stray late final must not lift suppression.
- ❌ Don't weaken the stale-window assert to make the landing leg pass — the guard holding IS half the contract (PRD h2.5's "safety not weakened").
- ❌ Don't skip `d._text_in_flight.set()` + the host double — cancel()'s suppress leg silently no-ops without them (CRITICAL #2) and the test would under-cover while appearing green.
- ❌ Don't pin the landing delta from theory — run the sequence and pin the observed calls (extend-vs-fresh-fragment vs rate-limit rewind; CRITICAL #1).
- ❌ Don't touch streaming.py (S1's), don't add a listening gate (T4.S1's), don't edit daemon logic (comment-only).
- ❌ Don't run/edit the CUDA suites (AGENTS.md); keep the test hermetic with the repo doubles.
- ❌ Don't modify PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**9/10** for one-pass implementation success. The heavy half already landed: the daemon wiring (`_touch_speech → stream.resume()`, first-in-method, with a rationale comment covering post-cancel suppression) is verified in-tree, and S1's engine seam (`resume()` clears `_suppressed` unconditionally) is visible in the working tree with its own engine-level twin test. This subtask is therefore **verify + one regression test**, with every construction fact pinned: the exact test sequence (contract, verbatim), the cancel-flow gate the test must satisfy (`_text_in_flight` + host), the doubles to use (`_make_daemon` @682, `_FakeHost.cancel` @625/`consume_cancel_mark` @630, the :4430+ section to mirror), the masking pattern being replaced (:291's manual `reset_boundary()`), and the empirical-delta discipline (S1's twin gotcha, mirrored). The −1 is the shared-surface residual: S1 is still landing (Task 0 gates on its `resume()` body) and the exact expected backend calls in the landing leg depend on engine history/rate-limit behavior — mitigated by pin-empirically-then-assert and by the invariant-level assertions (zero-calls midpoint; a type call with no commit in the sequence at all) that hold regardless of which engine path fires.
