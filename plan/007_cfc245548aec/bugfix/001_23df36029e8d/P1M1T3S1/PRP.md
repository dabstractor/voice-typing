# PRP — P1.M1.T3.S1: Engine — type the trailing space in commit()'s frozen-absorb path (BUG-003)

## Goal

**Feature Goal**: Fix bugfix **BUG-003** (Major): `StreamingOutput.commit()`'s frozen-absorb path (streaming.py:484-494) absorbs the tail into `committed` with NO keystrokes and NO trailing space — `append_space` is honored only in the non-frozen paths. After a user-keypress freeze (note_user_keypress, PRD rule 5 — the evdev listener routes ALL non-Backspace keys incl. Shift/Ctrl/CapsLock there), the daemon's `reset_boundary()` lifts the per-utterance freeze, and the next utterance's first word types flush against the absorbed tail: on-screen text reads **'Hello world the quicknew sentence'** instead of '…the quick new sentence'. The fix mirrors the non-frozen discipline in the frozen path: when `self._append_space`, type the separator via `_safe_type(' ')` and account for it exactly once in the committed join.

**Deliverable** (3 files edited, no new files):
1. `voice_typing/streaming.py` — one block replaced in `commit()`'s frozen path (verbatim below).
2. `tests/test_streaming_commit.py` — 3 NEW tests (TDD, written first, incl. the PRD h3.2 exact call sequence) + 2 existing tests updated (they pin the bug).
3. `tests/test_streaming_freeze.py` — 2 existing frozen-commit tests updated (they pin the bug; both helpers default `append_space=True`).

**Success Definition**:
- (a) The PRD h3.2 sequence — `on_partial('Hello world'); commit('Hello world'); reset_boundary(); on_partial('the quick'); note_user_keypress(); commit('the quick'); reset_boundary(); on_partial('New sentence')` on `StreamingOutput(backend, feedback, streaming=True, append_space=True)` — leaves the reconstructed screen reading **'Hello world the quick new sentence'** (a space precedes the new fragment; 'new' lowercase via the casing guard).
- (b) `append_space=False` stays space-free: `("type", " ")` appears NOWHERE.
- (c) Fail-safe: a space-type failure in the frozen path freezes SESSION-class (promote-only) and absorbs NOTHING (committed/tail unchanged, no exception) — mirrors the non-frozen "checkpoint stays at the pre-commit boundary".
- (d) The frozen commit still sends NO revision keystrokes (no rewind, no retype) — only the separator.
- (e) `timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q` → 0 failures (contract names commit+core; freeze MUST also run — it pins the same behavior).
- (f) `git diff --name-only` == `{voice_typing/streaming.py, tests/test_streaming_commit.py, tests/test_streaming_freeze.py}`.

## User Persona

The end user dictating continuously: they press ANY key (even Shift/CapsLock — the evdev listener routes all non-Backspace keys to the freeze) while a fragment is pending; the fragment commits (absorbed); they keep dictating. Before the fix the next sentence's first word glues onto the previous tail, corrupting the document. After: normal space-separated flow, exactly what README already promises.

## Why

- **PRD §4.2quater rule 2**: on commit, "append the trailing space (`output.append_space`); advance the checkpoint." The frozen path skips it — a plain spec omission, and the bug report (h2.2 Issue 2) reproduced it with the real engine following the daemon's exact call sequence.
- **The glue is inevitable in the common path.** The per-utterance freeze lifts right after this commit (daemon reset_boundary ~:1243), so typing resumes immediately against the separator-less absorbed tail. Modifier keys insert nothing yet still trigger the freeze — the trigger is ANY non-Backspace keypress, not a rare corner.
- **Checkpoint integrity, not just cosmetics.** `committed` is the screen-truth the casing guard and the rolling context prompt diff against; omitting the space stales both by one character.
- **Scope discipline.** Engine-only: do NOT touch `reset_boundary()`'s frozen-absorb (~:240) — it serves session-class stranded tails where nothing further types before `reset_session()` clears state, so no gluing is possible from that path. No daemon edits (parallel P1.M1.T2.S2 owns daemon.py + test_daemon.py — disjoint), no README/ACCEPTANCE (P1.M3.T9).

## What

Replace one block in `commit()`'s frozen path; add 3 tests; update 4 existing tests that pin the no-space behavior.

### Success Criteria

- [ ] Frozen path types `' '` iff `_append_space`, exactly once; committed join uses the rstrip-base `+ space` discipline.
- [ ] Screen after the PRD sequence == 'Hello world the quick new sentence' (test 1).
- [ ] append_space=False → no `("type", " ")` anywhere (test 2).
- [ ] Space-type failure → session-class freeze, nothing absorbed (test 3).
- [ ] The 4 listed existing tests updated to the corrected contract (2 renamed — their names assert the old falsehood).
- [ ] Engine suites green: commit + core + freeze (0 failures).

## All Needed Context

### Context Completeness Check

_Pass._ The buggy block and the non-frozen discipline are quoted verbatim with line numbers; the fix block is given verbatim; the full trace of the PRD test sequence (including the casing guard's 'New'→'new') is worked out; every affected existing test is identified with its current pin and required update; both test helpers' `append_space` defaults are verified (True). No CUDA/mic/daemon needed — pure engine + fakes.

### Documentation & References

```yaml
# MUST READ — the verified bug, fix block, affected-test table, sequence trace (this task's own research)
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T3S1/research/bug003_frozen_commit_space.md
  why: "§1 quotes the buggy block (:484-494) + the non-frozen discipline (:518-526) + the trigger chain
        + the full fix-sequence trace (screen lands exactly on the PRD's expected string). §2 is the
        verbatim fix. §3 is the affected-existing-test table (4 tests, current pin → updated pin, both
        helpers default append_space=True — verified). §4 the 3 new tests. §5 verify command + scope."
  critical: "§3 is load-bearing: without updating those 4 tests the suite stays red. The freeze-suite
            helper OMITS append_space (StreamingOutput default True) — do not 'fix' it to False."

# THE FILE TO EDIT
- file: voice_typing/streaming.py
  why: "commit()'s frozen path :484-494 (the block in research §1). _safe_type :542 (returns False +
        freezes session-class + tags backend-origin on any exception). Non-frozen space handling
        :518-526 — the discipline to mirror."
  pattern: "Early-return-without-advance on _safe_type failure (the non-frozen path's 'checkpoint stays
            at the pre-commit boundary'). Space typed BEFORE the committed join; join = rstrip base,
            drop empty parts, + space once."
  gotcha: "Do NOT touch reset_boundary()'s frozen-absorb (~:240) — session-class only, no gluing follows.
           Do NOT unfreeze in the frozen path (reset_boundary owns the lift). No rewind/retype ever."

# THE TEST FILES
- file: tests/test_streaming_commit.py
  why: "Doubles: RecordingBackend (records ('type',text)/('bs',n); fail_type/fail_backspace), FakeFeedback,
        FakeClock; _make_stream(backend, *, streaming=True, append_space=True, clock=None) :75-87. Update
        :244 (rename + separator pin) and :256 (append_space=False). New tests mirror the existing style."
- file: tests/test_streaming_freeze.py
  why: "_make_stream :63-71 (no append_space param → default True). Update :197 (keypress-frozen commit —
        now gains ('type',' ') and the 'next' fragment lands space-separated: the fix demonstrated) and
        :228 (session-class late commit — rename + separator pin)."

# THE SPEC + PARALLEL
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: "h2.2 Issue 2 (BUG-003) + h2.5 recommendation 'Append the trailing space in commit()'s frozen-absorb
        path'. h3.2's Steps-to-Reproduce IS the required test sequence."
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T2S2/PRP.md
  why: "Parallel task: tests/test_daemon.py + voice_typing/daemon.py (comment-only) — DISJOINT files."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/streaming.py          # commit() frozen path :484-494 (the bug); _safe_type :542.       ← EDIT (1 block)
tests/test_streaming_commit.py     # _make_stream :75-87 (append_space=True default); :244/:256 pins. ← EDIT (2 upd + 3 new)
tests/test_streaming_freeze.py     # _make_stream :63-71 (default True); :197/:228 pins.              ← EDIT (2 upd)
# Parallel T2.S2: tests/test_daemon.py + daemon.py — DISJOINT. Baseline: commit+core = 49 passed.
```

### Desired Codebase tree with files to be changed

```bash
# (no new files — the 3 edits above only)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — WRITE THE NEW TESTS FIRST (TDD). Run test 1 against the UNEDITED engine: it must FAIL
# with screen 'Hello world the quicknew sentence' (the bug demonstrated). Then apply the fix → green.

# CRITICAL #2 — THE 4 EXISTING TESTS PIN THE BUG. test_commit_frozen_touches_no_backend_and_absorbs_tail
# (commit:244), test_commit_frozen_with_empty_tail (commit:256),
# test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types (freeze:197),
# test_session_frozen_tail_late_commit_absorbs_without_keystrokes_and_stays_frozen (freeze:228). Both
# helpers run append_space=True (freeze's omits the param → StreamingOutput default True — verified).
# Update per research §3's table; rename the two whose names assert the old falsehood.

# CRITICAL #3 — EARLY-RETURN ON SPACE FAILURE (before the absorb). Mirrors the non-frozen boundary
# discipline: committed/tail unchanged, session-class freeze (promote-only — _safe_type tags it), no
# mirror update, no exception. State the acceptability in the comment (research §2's block has it).

# CRITICAL #4 — SPACE UNCONDITIONALLY ACROSS FREEZE CLASSES (when append_space). PRD rule 4 bans
# auto-DELETE; a space is an addition. In the session-class case nothing further types before
# reset_session() clears state. Do NOT gate on freeze class; do NOT touch reset_boundary's absorb.

# GOTCHA #5 — FULL PATHS. Use /home/dustin/.local/bin/uv run pytest (contract form) or
# .venv/bin/python -m pytest (equivalent). Always under timeout 600. pytest only (no ruff/mypy).

# GOTCHA #6 — NO daemon.py / test_daemon.py edits (parallel T2.S2); no README/ACCEPTANCE (P1.M3.T9);
# no listening gate (T4.S1). git diff must show exactly the 3 files.
```

## Implementation Blueprint

### Data models and structure

None — a one-block behavioral fix inside an existing method; no schema/config/API change.

### Implementation Tasks (ordered by dependencies — TDD)

```yaml
Task 1: ADD the 3 failing tests (RED) — tests/test_streaming_commit.py, new banner section at END
  - Banner: "# P1.M1.T3.S1 / BUG-003 — frozen commit types the append_space separator".
  - test_frozen_commit_types_separator_prd_sequence: _make_stream(append_space=True); drive the PRD h3.2
    sequence EXACTLY (on_partial('Hello world'); commit('Hello world'); reset_boundary();
    on_partial('the quick'); note_user_keypress(); commit('the quick'); reset_boundary();
    on_partial('New sentence')); screen = "".join(t for m, t in be.calls if m == "type");
    assert screen == "Hello world the quick new sentence"; assert stream.committed == "Hello world the quick ".
  - test_frozen_commit_append_space_false_stays_space_free: same sequence, append_space=False;
    assert ("type", " ") not in be.calls.
  - test_frozen_commit_space_type_failure_absorbs_nothing: on_partial("hello wor"); note_user_keypress();
    be._fail_type = True; commit("hello world") — no raise; frozen_session is True; committed == "";
    tail == "hello wor".
  - RUN (expect RED on test 1 — screen '…quicknew sentence'; tests 2/3 may pass pre-fix): 
    timeout 600 .venv/bin/python -m pytest tests/test_streaming_commit.py -q -k frozen_commit

Task 2: EDIT voice_typing/streaming.py — replace commit()'s frozen block (verbatim in research §2)
  - OLD (exact): the 10-line `if self._frozen:` block quoted in research §1.
  - NEW (exact): the research §2 block — space = " " if self._append_space else ""; early return on
    _safe_type failure; committed = join(rstrip base, tail) + space; then tail/suppressed/mirror/return
    unchanged. Keep the BUG-003 + fail-safe comments.

Task 3: UPDATE the 4 pinning tests (research §3 table)
  - commit:244 → rename test_commit_frozen_absorbs_tail_and_types_separator; calls ==
    [("type","hello wor"),("type"," ")]; committed == "hello wor "; frozen still True.
  - commit:256 → _make_stream(append_space=False); assertions unchanged (calls == []).
  - freeze:197 → after commit: calls == [("type","hello wor"),("type"," ")], committed == "hello wor ";
    final assert calls == [("type","hello wor"),("type"," "),("type","next")].
  - freeze:228 → rename …absorbs_plus_separator_and_stays_frozen; calls + ("type"," "); committed
    == "hello wor "; freeze-survives assertions unchanged.

Task 4: VALIDATE (L1–L4). If committing: "P1.M1.T3.S1: BUG-003 — frozen commit types the append_space
  separator (engine fix + 3 new tests, 4 updated)".
```

### Implementation Patterns & Key Details

```python
# THE FIX (verbatim — research §2). Mirror of the non-frozen discipline, frozen-appropriate:
space = " " if self._append_space else ""
if space and not self._safe_type(space):
    return  # frozen (session); checkpoint stays at the pre-commit boundary
self._committed = (
    " ".join(p for p in (self._committed.rstrip(), self._tail) if p) + space
)
# … then the existing tail/suppressed/mirror/return lines unchanged.

# SCREEN RECONSTRUCTION idiom (test 1): "".join(t for m, t in be.calls if m == "type")
```

### Integration Points

```yaml
DOWNSTREAM: P1.M3.T9 (doc sweep) consumes the green engine tests; P1.M3.T9.S2's ACCEPTANCE refresh may
  cite the new separator test. The daemon needs NO change (its reset_boundary flow already assumes
  commit handles the space).
PARALLEL: P1.M1.T2.S2 edits tests/test_daemon.py + daemon.py (comment-only) — DISJOINT.
UNCHANGED: reset_boundary()'s absorb, note_user_keypress, _safe_type/_safe_backspace, on_partial, all
  non-frozen commit paths, config schema, feedback, daemon.
```

## Validation Loop

### Level 1: The edit landed

```bash
cd /home/dustin/projects/voice-typing
grep -q 'BUG-003' voice_typing/streaming.py && grep -A3 'if self._frozen:' voice_typing/streaming.py | grep -q 'space = " "' && echo "L1 PASS" || echo "L1 FAIL"
.venv/bin/python -m py_compile voice_typing/streaming.py && echo "compiles"
```

### Level 2: Engine suites green (the contract gate + freeze)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q 2>&1 | tail -3
# Expected: 0 failures (baseline commit+core 49 + freeze suite; count grows by the 3 new tests).
```

### Level 3: The behavioral proof (hermetic)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_streaming_commit.py -q -k "prd_sequence or space_free or failure_absorbs_nothing" -v 2>&1 | tail -6
# Expected: the 3 new tests PASS (test 1 was RED pre-fix per Task 1).
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only   # == the 3 files
git diff --exit-code -- voice_typing/daemon.py tests/test_daemon.py README.md tests/ACCEPTANCE.md && echo "L4 PASS: parallel/downstream files untouched" || echo "L4 FAIL"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 fix block present + compiles; L2 commit+core+freeze 0 failures; L3 the 3 new tests pass; L4 exactly 3 files changed.

### Feature Validation
- [ ] PRD sequence screen == 'Hello world the quick new sentence'; append_space=False space-free; space-failure absorbs nothing + session freeze; frozen commit still sends no revision keystrokes.

### Code Quality / Scope Validation
- [ ] 4 pinning tests updated (2 renamed); no edits to reset_boundary/_safe_type/daemon/README; early-return discipline mirrors the non-frozen path.

### Documentation & Deployment
- [ ] Inline BUG-003 + fail-safe comments; no user-facing surface change (README already promises space-separated words).

---

## Anti-Patterns to Avoid

- ❌ Don't skip the RED step — run the PRD-sequence test against the unedited engine first.
- ❌ Don't forget the 4 pinning tests (freeze-suite helper defaults append_space=True — verified) or "fix" it to False.
- ❌ Don't absorb on space-type failure (early return first) or gate the space on freeze class.
- ❌ Don't touch reset_boundary's absorb, the daemon, or the docs (parallel/downstream scope).
- ❌ Don't run pytest without timeout/full paths; don't invent ruff/mypy gates.

---

## Confidence Score

**9.5/10** — the buggy block and fix are verbatim; the test sequence is fully traced (including the casing guard's 'New'→'new') to land exactly on the PRD's expected string; every affected existing test is identified with its exact updated pin; both helpers' append_space defaults verified; parallel task edits disjoint files. The −0.5 is a possible assertion slip in one of the 4 test updates — caught by L2 immediately. Pure engine + fakes: no CUDA/mic/daemon.
