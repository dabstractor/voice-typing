# PRP — P1.M1.T2.S1: Engine — `resume()` also clears post-cancel suppression

## Goal

**Feature Goal**: Close BUG-002 at the ENGINE level. After a Backspace-cancel, `reset_after_cancel()` sets `_suppressed=True` so a stale late partial cannot re-type the deleted fragment — but suppression currently lifts only at `reset_boundary()`, and the daemon never fires a boundary between a cancel and the next real final (the sentinel final is dropped at daemon.py:1130-1137 BEFORE `commit()`/`reset_boundary()` can run). Result: the re-said sentence loses live streaming (Rev 1 append-only) until its commit. The fix per PRD h2.5: **clear `_suppressed` on the child's next speech/first partial after the sentinel** — via the existing `resume()` seam (ONE resume API clearing both the rejected-final freeze and post-cancel suppression).

**Deliverable** (two files):
1. `tests/test_streaming_freeze.py` — the contract's **exact full-repro regression test** (`test_cancel_then_resume_restores_live_delta_typing`): partial → commit → partial → `reset_after_cancel()` → partial yields **zero** `type_text` (stale-partial guard HOLDS without resume) → `resume()` → next partial lands a **live delta** type call.
2. `voice_typing/streaming.py` — **Mode A docstring updates**: `reset_after_cancel()` still says suppression lasts "until the next `reset_boundary()`" — STALE now that `resume()` is the intended lift point; state both lift points. `resume()`'s docstring already documents the `_suppressed`-always-clear (T1.S1) — refresh only if wording needs it.

**Success Definition**:
- (a) The new full-repro test passes and encodes BOTH invariants: (i) suppression persists through `on_partial` until `resume()` fires (zero backend calls — the safety NOT weakened); (ii) after `resume()`, the next partial produces a real `("type", <delta>)` backend call against the committed checkpoint (live typing restored).
- (b) `timeout 600 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_freeze.py -q` → all green (43 + 1 = 44).
- (c) `resume()` remains the ONE seam (no second API; no changes to its semantics — it already clears `_suppressed` unconditionally, streaming.py:296).
- (d) The `reset_after_cancel()` docstring names `resume()` as the lift point (Mode A).
- (e) Only the two files change; `daemon.py` untouched (T2.S2 owns the wiring).

## Verified Current State (read before planning this PRP)

- **`resume()` already clears `_suppressed`** — landed WITH T1.S1 (Complete): streaming.py:274-296, body `self._suppressed = False` under `self._lock`, docstring line "…ALSO the post-cancel seam; P1.M1.T2.S1 / BUG-002 reuses exactly this". Backend-failure freezes survive; idempotent; no keystrokes. **So this subtask is mostly PINNING the contract's exact repro + fixing the stale docstring** — not new engine logic. If the new test is RED for any leg, fix `resume()`/suppression in streaming.py; if GREEN first run (expected), it is the committed regression guard.
- **A simpler pin already exists**: `test_resume_clears_post_cancel_suppression` (test_streaming_freeze.py:341-355) — but it lacks the contract's commit/boundary history, the **zero-type midpoint** (guard-holds-without-resume), and the **delta** assertion (it checks a fresh partial types, not a delta against committed). The new test is the authoritative repro; keep the simple one.
- **`reset_after_cancel()` docstring is stale** (streaming.py:204-212): "until the next `reset_boundary()`, on_partial mirrors only" — `resume()` is now the primary lift point (the daemon fires no boundary post-cancel).
- **Both suites currently green**: 43 passed in 0.02s (run 2026-07, hermetic).

## What

One additive test (the contract repro, verbatim sequence) + docstring refresh. TDD order: write the test FIRST, run it — expected GREEN (T1.S1 landed the seam); if any leg is RED, fix the engine minimally (e.g. suppression leaking through the extend path), never by weakening the stale-partial guard.

### Success Criteria

- [ ] `test_cancel_then_resume_restores_live_delta_typing` exists in tests/test_streaming_freeze.py, docstring citing BUG-002 / P1.M1.T2.S1 + the daemon-flow rationale (sentinel dropped before commit → no boundary → resume() is the lift).
- [ ] The test asserts the midpoint: after `reset_after_cancel()` + `on_partial("the quick brown fox")` → `be.calls == []` (suppression HOLDS).
- [ ] The test asserts the landing: after `resume()` + `on_partial("the quick brown fox jumps")` → the last backend call is `("type", <delta>)` restoring live typing (see Gotcha #1 for the exact-delta determination).
- [ ] `reset_after_cancel()` docstring: suppression lifts at `resume()` (the daemon's next-speech seam, T2.S2) OR the next `reset_boundary()`.
- [ ] `timeout 600 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_freeze.py -q` → 44 passed.
- [ ] `git diff --name-only` == the two files; `daemon.py` untouched.

## All Needed Context

### Context Completeness Check

_Pass._ The engine state (resume body, suppression sites :380/:490/:524, reset_boundary :243, reset_session :265), the existing test double (`_make_stream()`/`RecordingBackend`/`FakeFeedback` in test_streaming_core.py:27-88, imported by the freeze file), the current green count (43), and the T1.S1/T1.S2/T2.S2 boundaries are all verified. No CUDA/mic/keystrokes — pure unit.

### Documentation & References

```yaml
- file: voice_typing/streaming.py
  why: resume() @274 (clears _suppressed @296 — ALREADY the seam); reset_after_cancel() @204 (sets
        _suppressed @213; STALE docstring to fix); suppression checks @380 (on_partial mirror-only) and
        clears @243 (reset_boundary)/@265 (reset_session)/@490/:524 (commit paths).
  critical: "Do NOT touch resume() semantics — T1.S1 pinned them (idempotent, lock-held, backend-failure
            freezes survive, no keystrokes). This task PINS the cancel-path behavior + fixes docs."

- file: tests/test_streaming_freeze.py
  why: The sibling patterns: test_rejected_final_freeze_lives_until_resume_then_next_utterance_types @274
        (the BUG-001 twin — copy its structure), test_resume_clears_post_cancel_suppression @341 (keep;
        simpler), test_resume_cannot_lift_backend_failure_freeze @304. `_make_stream()` imported from
        test_streaming_core (RecordingBackend records ("type", t)/("bs", n); FakeFeedback mirrors).
  pattern: "New test goes right after :341's simple pin, mirroring :274's twin structure."

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/streaming_engine.md
  why: The suppression lifecycle map (:197-206 set; :221/:424/:458 clears) + the daemon never firing a
        boundary post-cancel (sentinel dropped at daemon.py:1130-1137).

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T1S1/PRP.md
  why: The resume() CONTRACT (one seam, both uses) this task reuses — do not add a second API.

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T1S2/PRP.md
  why: The PARALLEL daemon wiring: _touch_speech() calls self._stream.resume() (its line 24: "S1's
        resume() clears _suppressed ALWAYS … T2.S2 reduces to its regression test"). Confirms the
        engine seam is consumed exactly as this PRP pins it. No file overlap (daemon.py is theirs).

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: §h2.2/h3.1 (BUG-002: the re-said sentence must stream live) + §h2.5 ("clear _suppressed on the
        child's next speech/first partial after the sentinel") — the mandate.
```

### Current / Desired tree

```bash
voice_typing/streaming.py       # EDIT: reset_after_cancel() docstring (+resume() docstring touch-up only if needed)
tests/test_streaming_freeze.py  # EDIT: + test_cancel_then_resume_restores_live_delta_typing (after :341's pin)
# daemon.py — T2.S2's file. README/ACCEPTANCE — P1.M3.T9.
```

### Known Gotchas

```python
# CRITICAL #1 — DETERMINE THE EXACT DELTA EMPIRICALLY, then pin it. After resume(), on_partial(
# "the quick brown fox jumps") against committed "Hello world" may take the EXTEND path (delta "
# jumps"-style), or a full-rewind if the 300ms rate-limit/guards force it (BUG-008 territory).
# FIRST run the sequence in a scratch REPL/pytest with be.calls printed, THEN pin the observed
# ("type", <delta>) — the invariant is "a real type call lands" + "the final screen equals
# 'Hello world the quick brown fox jumps'" (derive screen from be.calls like the :274 twin does).
# Use the file's FakeClock if a rate-limit interferes (test_streaming_core.py:336 precedent).

# CRITICAL #2 — THE GUARD MUST HOLD. The midpoint assert (be.calls == [] after reset_after_cancel +
# on_partial) is the safety half — do NOT weaken it to make the landing leg pass. Suppression
# persists until resume(); that IS the contract ("stale-partial safety must not be weakened").

# CRITICAL #3 — TEST-FIRST, EXPECTED-GREEN. Write the test, run it BEFORE any streaming.py edit.
# Expected GREEN (T1.S1 landed the seam). If RED: fix the engine minimally (e.g. suppression
# leaking through extend); NEVER by clearing _suppressed earlier than resume().

# CRITICAL #4 — NO SECOND API, NO SEMANTIC DRIFT. resume() is the one seam (T1.S1's contract;
# T1.S2/T2.S2 wire it). Do not add clear_suppression()/unfreeze() variants; do not make resume()
# conditional. Docstrings only.

# GOTCHA #5 — FULL PATHS + timeout 600 (AGENTS.md). The suites are hermetic (~0.02s) but keep the
# wrapper. No ruff/mypy configured.
```

## Implementation Blueprint

### Tasks

```yaml
Task 1: ADD tests/test_streaming_freeze.py — the full-repro regression test (FIRST; CRITICAL #1/#3)
  - PLACE: immediately after test_resume_clears_post_cancel_suppression (:355).
  - CODE (shape; pin the delta per CRITICAL #1):
        def test_cancel_then_resume_restores_live_delta_typing():
            """BUG-002 / P1.M1.T2.S1: post-cancel suppression lifts at resume() — the re-said
            sentence streams LIVE. The daemon never fires reset_boundary() between a cancel and
            the next real final (the sentinel is dropped pre-commit, daemon.py:1130-1137), so
            resume() (wired at next speech, T2.S2) is the lift point. Guard half: until resume(),
            partials are mirror-only."""
            stream, be, fb = _make_stream()
            stream.on_partial("Hello world")
            stream.commit("Hello world")
            stream.on_partial("the quick brown")
            stream.reset_after_cancel()
            stream.on_partial("the quick brown fox")          # re-said sentence begins
            assert be.calls == [], "suppression must HOLD until resume() (stale-partial guard)"
            stream.resume()
            stream.on_partial("the quick brown fox jumps")
            assert any(c[0] == "type" for c in be.calls), "live typing must resume after resume()"
            # pin the exact delta + screen per the observed engine behavior (CRITICAL #1):
            # assert be.calls[-1] == ("type", "<delta>")
            # screen = _screen(be)  # derive from calls; assert "...the quick brown fox jumps"
  - RUN (before any streaming.py edit): timeout 600 .venv/bin/python -m pytest
    tests/test_streaming_freeze.py::test_cancel_then_resume_restores_live_delta_typing -q
    → expected PASS (T1.S1's seam); if FAIL, minimally fix the engine (CRITICAL #3).

Task 2: EDIT voice_typing/streaming.py — reset_after_cancel() docstring (Mode A)
  - REPLACE "until the next reset_boundary(), on_partial mirrors only" with: "until resume() (the
    daemon's next-speech seam — P1.M1.T1.S2 wiring; the daemon fires no boundary between a cancel
    and the next real final, BUG-002) or the next reset_boundary(); on_partial mirrors only while
    suppressed."
  - TOUCH resume()'s docstring ONLY if needed to name the cancel lift explicitly (it already cites
    "P1.M1.T2.S1 / BUG-002 reuses exactly this").

Task 3: VALIDATE (see Loop). Commit msg if asked: "P1.M1.T2.S1: pin resume() as the post-cancel
  suppression lift (BUG-002 engine) + full-repro regression test".
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S2 (daemon wiring + daemon-level regression):
  - T2.S2 consumes this seam: _touch_speech() → stream.resume() lifts suppression at genuinely-new
    speech (per T1.S2's PRP the call is already wired there; T2.S2 adds the daemon-level cancel→
    next-utterance live-typing regression). This task guarantees the engine half is pinned.
SIBLINGS: T1.S1 (resume contract — consumed, not modified); T1.S2 (parallel; daemon.py only — no
  overlap); T2.S3/T2.S4 (other BUGs). P1.M3.T9 owns README/ACCEPTANCE.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1: test exists + guard-half assert present
grep -q 'test_cancel_then_resume_restores_live_delta_typing' tests/test_streaming_freeze.py \
  && grep -q 'be.calls == \[\]' tests/test_streaming_freeze.py && echo "L1 PASS"
# L2: the contract's verbatim gate
timeout 600 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_freeze.py -q 2>&1 | tail -2
#   → 44 passed. (Also run the new test -v standalone.)
# L3: scope + docs
grep -q 'resume()' voice_typing/streaming.py && sed -n '/def reset_after_cancel/,/with self._lock/p' voice_typing/streaming.py | grep -q 'resume' && echo "L3a docstring PASS"
git status --short | grep -vE 'streaming.py|test_streaming_freeze.py' && echo "L3b FAIL" || echo "L3b PASS"
git diff --quiet voice_typing/daemon.py && echo "L3c daemon untouched PASS"
```

## Final Validation Checklist

- [ ] L1: new test present with the zero-calls midpoint assert.
- [ ] L2: 44 passed across the two engine suites.
- [ ] L3: docstring names resume(); diff == streaming.py + test_streaming_freeze.py; daemon.py untouched.
- [ ] resume() semantics unchanged (one seam; idempotent; backend-failure survives; no keystrokes).
- [ ] Guard NOT weakened (suppression persists until resume()); delta landing pinned empirically.

## Anti-Patterns

- ❌ Don't add a second API or make resume() conditional (CRITICAL #4).
- ❌ Don't weaken the midpoint (guard-holds) assert to make the landing pass (CRITICAL #2).
- ❌ Don't guess the delta string — run the sequence, observe, pin (CRITICAL #1); prefer also asserting the final screen.
- ❌ Don't edit daemon.py (T2.S2) or skip the test-first run (CRITICAL #3).
- ❌ No bare python/pytest; keep `timeout 600` + `.venv/bin/python -m pytest` (Gotcha #5).

## Confidence Score

**9.5/10** — the engine seam ALREADY landed (verified: streaming.py:296 + both suites 43-green), so the deliverable is the authoritative repro pin + a stale-docstring fix, with copy-ready structure from the :274/:341 twins. The only unknown is the exact delta string (extend vs rewind under the rate limit), handled empirically by CRITICAL #1 + the screen assertion; −0.5 for that one observation step.
