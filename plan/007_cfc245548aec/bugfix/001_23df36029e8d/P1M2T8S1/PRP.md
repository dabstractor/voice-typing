---
name: "P1.M2.T8.S1 — BUG-008: Case-insensitive prefix matching in the EXTEND path (engine)"
description: "Normalize case for the extend comparison ONLY in StreamingOutput.on_partial (and mirror it in commit()'s extend branch): the casing guard lowercases a fresh mid-sentence fragment's first word while decoder partials keep it capitalized, so the case-sensitive `text.startswith(self._tail)` test never matches and every subsequent partial cycle becomes a rate-limited full rewind+retype (screen-wide flicker churn). Fix = length-safe, case-insensitive prefix comparison; typed output, guards, rate limiter, and all other paths unchanged."
---

## Goal

**Feature Goal**: Make the streaming engine's EXTEND decision case-insensitive so that, once `apply_streaming_guards` has lowercased the first word of a fresh mid-sentence fragment, the decoder's subsequent capitalized partials ("The quick brown…") still prefix-match the guarded tail ("the quick") and extend it with a typed delta — eliminating the guard-induced full-rewind churn (BUG-008) precisely in the mid-paragraph-continuation scenario the delta-typing design exists for.

**Deliverable**: A small, pure, module-level helper in `voice_typing/streaming.py` (case-insensitive, length-safe prefix test) used by the EXTEND branches of `StreamingOutput.on_partial` (streaming.py:~398) and `StreamingOutput.commit` (streaming.py:~504), plus regression tests in `tests/test_streaming_core.py` / `tests/test_streaming_commit.py` and one deliberately-updated existing test that currently encodes the buggy case-sensitive behavior.

**Success Definition**: With committed text lacking terminal punctuation (e.g. "and then he said"), feeding partials `"Hello there"`, `"Hello there friend"`, `"Hello there friend how"` at natural cadence produces exactly one typed fragment (`"hello there"`, guard-lowercased) followed by pure delta extends (`" friend"`, `" how"`) and ZERO `press_backspace` calls after the first cycle — verified by the new regression test; the full existing streaming/textproc test set stays green.

## User Persona (if applicable)

**Target User**: End user dictating mid-paragraph continuations with streaming output enabled (the default `output.streaming = true` mode).

**Use Case**: The user has already dictated text not ending in `.`/`!`/`?` (mid-sentence), then dictates a continuation. Whisper/RealtimeSTT partials for the new fragment arrive with a capitalized first word ("The quick brown…"), while the engine's casing guard deliberately types "the quick" (lowercase, per PRD §4.2quater rule 1 mid-sentence casing).

**User Journey**: Speak a continuation → first partial types guarded text → each subsequent partial extends it with only the new words (phone-style live typing, no flicker) → commit confirms with a delta, not a rewrite.

**Pain Points Addressed**: Today every partial after the first fails the case-sensitive prefix test and triggers a full rewind+retype of the whole tail — ~3 screen-wide delete/retype flickers per second (throttled only by the 300 ms rate limiter), growing with utterance length. This is exactly the "Revision flicker (rewind/retype storms)" risk PRD §8 says delta-typing must minimize.

## Why

- **BUG-008 (PRD h2.3 Issue 4 / h3.7)**: "The extend test is case-sensitive (`'text.startswith(self._tail)'`, streaming.py:328), but apply_streaming_guards lowercases the first word of a fresh mid-sentence fragment (committed not ending in ./!/?). From then on the decoder's subsequent partials — which keep their capitalized first word ('The quick brown...') — can never prefix-match the guarded tail ('the quick'), so every partial cycle becomes a full rewind+retype, throttled only by the 300ms rate limiter."
- **PRD h2.5 recommendation (the chosen approach)**: "Consider a case-insensitive prefix match (normalizing only for comparison) to stop guard-induced full-rewind churn on mid-sentence continuations." The work-item contract pins it: "normalize case for the prefix COMPARISON ONLY — typed output keeps the decoder's casing; delta = `text[len(self._tail):]` guarded as today."
- Restores the core streaming UX (flicker-free delta typing) in the engine's own target scenario; no daemon, config, or backend changes are needed.

## What

Engine-only change, invisible except as the disappearance of rewind flicker:

1. The EXTEND-vs-REVISE decision in `on_partial` (and the extend decision in `commit`) compares the tail against the incoming text **case-insensitively, for the comparison only**.
2. The typed delta is still sliced from the ORIGINAL strings (`text[len(self._tail):]`) and passed through `textproc.apply_streaming_guards` exactly as today; the tail keeps its already-typed guarded casing (we never re-type the tail to the decoder's casing).
3. Everything else is untouched: the 300 ms full-rewind rate limiter, the frozen/suppressed/streaming-disabled mirror-only paths, `_guard_context_delta()`, the no-trailing-space-while-tentative invariant, the lock discipline, and the fail-safe freeze policy.

### Success Criteria

- [ ] New regression test (PRD h3.7 repro): mid-sentence commit → partials `'Hello there'` → `'Hello there friend'` → `'Hello there friend how'` produce `_typed == ["hello there", " friend", " how"]` and ZERO `press_backspace` calls.
- [ ] A partial identical to the tail except casing is a no-op mirror (empty delta path preserved).
- [ ] `commit()`'s extend branch uses the same case-insensitive helper; a capitalized final over a guarded tail commits as a delta + trailing space with no rewind (new commit test).
- [ ] Existing test `test_backspace_failure_freezes_and_does_not_propagate` updated to use a genuine non-prefix partial (it currently relies on the case mismatch to reach the REVISE path) and still passes.
- [ ] All of `tests/test_streaming_core.py`, `tests/test_streaming_commit.py`, `tests/test_textproc.py` green; `tests/test_streaming.py` (screen-model/fuzz suite) still green — its append-monotonicity assertions hold because extends remain pure appends.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, would they have everything needed to implement this successfully?" — Yes: this PRP quotes the exact current code at both change sites, the guard that creates the mismatch, the length-safety trap, the one test that encodes the old behavior, and the verified test-runner commands.

### Documentation & References

```yaml
- file: voice_typing/streaming.py
  why: The ONLY production file to modify. Module docstring documents the EXTEND/REVISE
        contract ("TAIL TRACKS TYPED TEXT... prefix-diffing stays consistent") and must
        get a one-phrase update. Two change sites (line numbers as of the P1.M1-landed
        code; the PRD's :328/:417 are pre-P1.M1 numbers):
        - on_partial EXTEND test  (~line 398):
            if self._tail and text.startswith(self._tail):
                # EXTEND: tail is a prefix -> type only the guarded delta.
                delta = text[len(self._tail) :]
        - commit() EXTEND test    (~line 504):
            if self._tail and text.startswith(self._tail):
                # EXTEND: the final confirms the tail — type only the guarded delta.
                delta = text[len(self._tail) :]
        Also relevant: context_after_last_boundary (module-level pure helper — the
        placement/style precedent for your new helper) and _guard_context_delta().
  pattern: module-level pure helpers with dense docstrings; all state mutations under
        self._lock; mirror into feedback on EVERY path.
  gotcha: NEVER normalize/store a case-folded string — only the boolean comparison is
        case-insensitive; the delta slice and the tail stay original-cased. Do not add
        config keys. Do not stamp _last_full_rewind on extends.

- file: voice_typing/textproc.py
  why: apply_streaming_guards (lines 82-134) is the OTHER half of the bug: rule (a)
        lowercases the FIRST cased character of a fresh mid-sentence fragment (context
        = committed.rstrip() non-empty and not ending in . ! ?). Rule (b) strips one
        spurious trailing '.' in the same mid-sentence branch. You do NOT change this
        file — you must understand WHY the tail's first char diverges from the
        decoder's partials (and why "Hello world." deltas can type nothing).
  pattern: pure function, deterministic, no I/O.
  gotcha: the guard runs on the DELTA in the extend path (context via
        _guard_context_delta()), so an extend delta's first word can itself be
        lowercased — that is correct and unchanged.

- file: tests/test_streaming_core.py
  why: The regression test goes here. Reuse the existing harness: RecordingBackend
        (records ("type", s)/("bs", n); press_backspace(n<=0) is an unrecorded no-op),
        FakeFeedback (.partials list), FakeClock, _make_stream(...), _typed(be).
        Existing extend tests at lines ~97-158 show the exact assertion style, e.g.
        test_extend_never_retypes_the_whole_tail_on_multi_word_growth asserts
        _typed(be) == ["the quick", " brown fox", " jumps"].
  pattern: plain functions, no pytest fixtures/classes; white-box poking
        (stream._committed = "Then he said") exists at line ~114 but PREFER the public
        commit() API (it has landed) to seed mid-sentence context.
  gotcha: LANDMINE — test_backspace_failure_freezes_and_does_not_propagate (line ~334)
        feeds "Hello world" over tail "hello wor" precisely BECAUSE the re-capitalized
        partial is currently NOT a prefix -> REVISE -> press_backspace raises -> freeze
        asserted. After your fix that input becomes an EXTEND and the test breaks; you
        MUST update it to a genuine non-prefix (decoder-retraction idiom, e.g.
        "hello wrl" — position 8 'o' vs 'r' mismatches case-insensitively too).

- file: tests/test_streaming_commit.py
  why: Where the commit-path mirror test goes. Existing tests (~lines 100-146) show the
        commit assertion style: be.calls == [("type", ...), ("type", " ")] and
        stream.committed == "... " (append-space discipline).
  pattern: same RecordingBackend/FakeFeedback doubles as test_streaming_core.py.
  gotcha: no existing commit test depends on a case-mismatch final being a revise, so
        mirroring the helper into commit() is test-safe (verified by grep).

- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/streaming_engine.md
  why: The task contract's research note on this engine; documents the EXTEND/REVISE
        state machine and the tail-truth invariant.

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M2T8S1/research/engine-extend-case-notes.md
  why: This session's research notes: exact code quotes, the landmine test, the
        casefold length trap, and verified runner commands.

- url: https://docs.python.org/3/library/stdtypes.html#str.casefold
  why: casefold() is the correct per-character case-insensitive comparison, but
        Unicode case folding can CHANGE STRING LENGTH ('ß'.casefold() == 'ss',
        'İ'.casefold() has len 2). That is why the helper below compares per-character
        casefolds over zip()'d original chars and never builds a folded string.
  critical: slicing delta = text[len(self._tail):] must use ORIGINAL lengths; a
        folded-string startswith would desynchronize lengths and corrupt the delta.
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
  streaming.py          # StreamingOutput engine — BOTH change sites (on_partial ~:398, commit ~:504)
  textproc.py           # apply_streaming_guards (casing+period guards) — read-only for this task
  daemon.py             # NOT touched (engine-only fix)
tests/
  test_streaming_core.py    # partial-path regression test + landmine test to update
  test_streaming_commit.py  # commit-path mirror test
  test_textproc.py          # must stay green (guard semantics unchanged)
  test_streaming.py         # screen-model/fuzz suite — must stay green (no CUDA; pure doubles)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
# NO new files. Modified only:
voice_typing/streaming.py          # + _ci_startswith() module-level pure helper; two branch edits; docstring phrase
tests/test_streaming_core.py       # + regression tests; ~1 existing test updated (landmine)
tests/test_streaming_commit.py     # + commit-extend case-insensitivity test
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: str.casefold()/lower() can change length ('ß'->'ss', 'İ'->2 chars).
# Compare per-character casefolds over the zip of the ORIGINAL strings; slice the
# delta from the originals. Never store or type a folded string.
# CRITICAL: The tail stores the GUARDED strings actually typed — len(tail) is exactly
# what a rewind deletes. Your change must not alter tail contents, only the boolean
# extend decision.
# CRITICAL: Extends are NEVER rate-limited and never stamp _last_full_rewind; only
# actual rewinds do (fresh starts stamp nothing either). Keep it that way.
# GOTCHA: 'Hello there' over tail 'hello there' (equal length, case-only diff) must
# stay a no-op mirror — the existing `if not delta` early-return already handles it.
# GOTCHA: This repo's control socket has no read timeout and several test files load
# CUDA models — run pytest ONLY on the pure files listed below, always under BOTH an
# inner `timeout N` and the harness bash timeout (repo AGENTS.md rule).
# NOTE: The decoder re-capitalizing a LATER word (not the first char) will now also
# be swallowed by the comparison; casing policy belongs to the guard, not the
# decoder — this is the intended PRD semantics ("normalizing only for comparison").
```

## Implementation Blueprint

### Data models and structure

None — no data models, config, schemas, or IPC change. Pure control-flow fix inside `voice_typing/streaming.py`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD failing regression tests FIRST (tests/test_streaming_core.py)
  - IMPLEMENT test_mid_sentence_capitalized_partials_extend_case_insensitively:
      stream, be, _fb = _make_stream()
      stream.commit("and then he said")            # public API: seeds mid-sentence committed + clears tail
      stream.on_partial("Hello there")             # fresh start; guard lowercases -> types "hello there"
      stream.on_partial("Hello there friend")      # BUG-008: currently full rewind; after fix EXTEND " friend"
      stream.on_partial("Hello there friend how")  # EXTEND " how"
      assert _typed(be) == ["hello there", " friend", " how"]
      assert not [c for c in be.calls if c[0] == "bs"]   # ZERO backspaces after the first cycle
      assert stream.tail == "hello there friend how"
  - IMPLEMENT test_capitalized_partial_equal_length_case_only_diff_is_noop:
      same seeding; on_partial("Hello there") twice (2nd via "HELLO there" if you
      want multi-char coverage) -> second is a no-op mirror, no new backend calls.
  - IMPLEMENT test_commit_extend_matches_case_insensitively (in tests/test_streaming_commit.py):
      stream.commit("and then he said"); on_partial("The quick")  -> types "the quick";
      stream.commit("The quick brown fox") -> NO "bs" call; calls gain
      ("type", " brown fox"), ("type", " "); stream.committed == "and then he said the quick brown fox "
  - FOLLOW pattern: neighboring extend tests (tests/test_streaming_core.py ~:97-158)
  - RUN them now: they must FAIL on the extend assertions (red) before Task 2.

Task 2: ADD the length-safe helper (voice_typing/streaming.py)
  - IMPLEMENT module-level private pure function next to context_after_last_boundary:
      def _ci_startswith(text: str, prefix: str) -> bool:
          """True iff `prefix` is a case-insensitive prefix of `text` (BUG-008).

          Per-character casefold comparison over the ORIGINAL strings — never builds a
          folded string, so a length-changing casefold ('ß'.casefold() == 'ss') cannot
          desynchronize the comparison from the original lengths. Callers slice deltas
          from the originals: delta = text[len(prefix):].
          """
          return len(text) >= len(prefix) and all(
              a.casefold() == b.casefold() for a, b in zip(text, prefix)
          )
  - NAMING: _ci_startswith (leading underscore = module-private, snake_case).
  - PLACEMENT: module level, immediately after context_after_last_boundary.

Task 3: USE it in on_partial's EXTEND branch (voice_typing/streaming.py ~:398)
  - CHANGE: `if self._tail and text.startswith(self._tail):`
        ->  `if self._tail and _ci_startswith(text, self._tail):`
  - PRESERVE: delta = text[len(self._tail):], the `if not delta` no-op mirror,
        apply_streaming_guards(self._guard_context_delta(), delta), _safe_type,
        tail += guarded, feedback mirror. NOTHING else in on_partial changes.

Task 4: MIRROR it in commit()'s EXTEND branch (voice_typing/streaming.py ~:504)
  - CHANGE: same one-line substitution.
  - PRESERVE: delta guard + _safe_type + append-space + committed join + mirror.
  - WHY: keeps partial/commit behavior consistent (a capitalized final over a guarded
        tail becomes a delta commit instead of a one-shot rewind+retype; screen text
        is identical either way because the guard re-applies the same casing).
  - Verified safe: no existing commit test encodes a case-mismatch final as a revise.

Task 5: UPDATE the landmine test (tests/test_streaming_core.py ~:334)
  - test_backspace_failure_freezes_and_does_not_propagate: its revise input
    "Hello world" (comment: 're-capitalizes -> NOT a prefix -> true revise') becomes
    an EXTEND after the fix. Change the partial to a genuine non-prefix retraction,
    e.g. "hello wrl", and update the comment to say the retraction is the revise
    trigger. The test's INTENT (revise whose press_backspace raises -> freeze, never
    propagate) is unchanged.

Task 6: DOCSTRING touch-up (voice_typing/streaming.py)
  - Module docstring EXTEND bullet: extend the phrase "old tail is a prefix of the
    new partial" with "(case-insensitively — the casing guard lowercases a fresh
    mid-sentence fragment while decoder partials stay capitalized; BUG-008)". One
    phrase; do not rewrite the docstring.
  - NO other docs: the task contract says "DOCS: none — internal flicker fix"; the
    README sweep is P1.M3.T9's job (its contract already lists "mid-sentence extends
    match case-insensitively" as a landed behavior to sync).
```

### Implementation Patterns & Key Details

```python
# The complete production change is two boolean substitutions plus the helper:

def _ci_startswith(text: str, prefix: str) -> bool:
    """True iff `prefix` is a case-insensitive prefix of `text` (BUG-008). ..."""
    return len(text) >= len(prefix) and all(
        a.casefold() == b.casefold() for a, b in zip(text, prefix)
    )

# on_partial (~:398) and commit (~:504), identical shape:
if self._tail and _ci_startswith(text, self._tail):
    # EXTEND: tail is a case-insensitive prefix -> type only the guarded delta.
    delta = text[len(self._tail):]          # ORIGINAL lengths — never folded

# PATTERN: comparison-only normalization. The tail KEEPS its guarded casing
# ("the quick"); we do NOT retype it as "The quick". The casing policy belongs
# to textproc.apply_streaming_guards, not to the diff.
# GOTCHA: zip(text, prefix) pairs exactly len(prefix) chars because
# len(text) >= len(prefix) is checked first — a shorter text can never extend.
# CRITICAL: extends stay non-rate-limited and never touch _last_full_rewind;
# frozen/suppressed/disabled mirror-only paths are BEFORE the comparison and
# must remain untouched.
```

### Integration Points

```yaml
NONE: pure engine fix. No config keys, no daemon.py changes, no backend changes,
      no IPC/schema changes, no README edits (P1.M3.T9 owns doc sync).
DAEMON: unaffected — daemon.py already routes partials/finals/cancel into the
      engine; only the engine's internal extend decision changes.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
ruff check voice_typing/streaming.py tests/test_streaming_core.py tests/test_streaming_commit.py
ruff format --check voice_typing/streaming.py tests/test_streaming_core.py tests/test_streaming_commit.py
# ruff is on PATH (~/.local/bin/ruff). Expected: zero errors.
```

### Level 2: Unit Tests (Component Validation)

```bash
# Repo AGENTS.md rule: EVERY command under an inner `timeout` AND the bash-tool
# timeout set above it. These files are pure-Python (RecordingBackend doubles,
# no CUDA, no mic) — sub-second runs.

timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -q
timeout 300 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_commit.py tests/test_textproc.py -q
timeout 600 uv run pytest tests/test_streaming.py -q   # screen-model/fuzz suite; pure doubles

# bash-tool timeout (outer backstop): 180 / 360 / 660 respectively.
# Expected: all pass. Do NOT run tests/test_feed_audio.py, test_daemon.py,
# test_recorder_host.py (CUDA model loads, minutes each) — out of scope here.
```

### Level 3: Direct engine probe (manual sanity, optional)

```bash
timeout 60 .venv/bin/python - <<'EOF'
from voice_typing.streaming import StreamingOutput
class BE:
    def __init__(self): self.calls=[]
    def type_text(self,s): self.calls.append(("type",s))
    def press_backspace(self,n): self.calls.append(("bs",n))
class FB:
    def update_partial(self,t): pass
s=StreamingOutput(BE(),FB(),streaming=True)
s.commit("and then he said")
for p in ["Hello there","Hello there friend","Hello there friend how"]:
    s.on_partial(p)
assert [c for c in s._backend.calls if c[0]=="bs"]==[], s._backend.calls
assert [c[1] for c in s._backend.calls if c[0]=="type"]==["hello there"," friend"," how"], s._backend.calls
print("BUG-008 probe OK")
EOF
# bash-tool timeout 90. Expected: "BUG-008 probe OK" — zero backspaces, pure deltas.
```

### Level 4: Creative & Domain-Specific Validation

Not applicable (no UI/service/DB). The screen-model fuzz suite (`tests/test_streaming.py`, Level 2) is this repo's domain-level guard: its delta-only-extend counting and append-monotonicity assertions directly verify the flicker-free property this fix restores.

## Final Validation Checklist

### Technical Validation

- [ ] Level 1: `ruff check` + `ruff format --check` clean on the three touched files
- [ ] Level 2: `timeout 300 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_commit.py tests/test_textproc.py -q` all pass
- [ ] Level 2: `timeout 600 uv run pytest tests/test_streaming.py -q` passes (append-monotone / delta-count invariants hold)
- [ ] New regression test written FIRST and observed failing (red) before the engine edit
- [ ] Level 3 probe (optional) prints `BUG-008 probe OK`

### Feature Validation

- [ ] Mid-sentence capitalized partials extend with deltas; ZERO press_backspace after the first cycle (new test asserts it)
- [ ] Case-only-equal partial is a no-op mirror (empty-delta path preserved)
- [ ] commit() extend branch mirrors the helper; capitalized final commits as delta + trailing space, no rewind
- [ ] Landmine test updated to a genuine non-prefix revise and still passes
- [ ] No behavior change for sentence-start utterances (committed empty/terminal) — `test_session_start_partial_preserves_capitalization` still green

### Code Quality Validation

- [ ] Helper is module-level, pure, private (`_ci_startswith`), placed after `context_after_last_boundary`
- [ ] No folded string is ever stored or typed; delta sliced from originals
- [ ] Rate limiter, freeze/suppress paths, mirrors, lock discipline untouched
- [ ] No new config keys; no daemon.py edits; no doc rewrites beyond the one docstring phrase

### Documentation & Deployment

- [ ] Module docstring EXTEND bullet mentions the case-insensitive comparison (one phrase)
- [ ] No README/config.toml changes (owned by P1.M3.T9)

## Anti-Patterns to Avoid

- ❌ Don't replace `startswith` with `text.lower().startswith(self._tail.lower())` — lower()/casefold() can change string length and desynchronize the delta slice
- ❌ Don't retype or re-case the tail to match the decoder — comparison-only normalization
- ❌ Don't touch `apply_streaming_guards`, the rate limiter, or the frozen/suppressed paths
- ❌ Don't skip updating `test_backspace_failure_freezes_and_does_not_propagate` — it WILL fail after the fix and encodes the bug
- ❌ Don't run the CUDA-heavy suites or the daemon in the foreground; every command gets both timeouts (repo AGENTS.md)
- ❌ Don't add config keys or logging for this — it is an invisible flicker fix
```
