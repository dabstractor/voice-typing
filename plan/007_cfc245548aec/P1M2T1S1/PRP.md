# PRP — P1.M2.T4.S1: Casing + period guard pure functions (`apply_streaming_guards`)

## Goal

**Feature Goal**: Add `apply_streaming_guards(committed: str, fragment: str) -> str` to `voice_typing/textproc.py` — the PRD §4.2quater R6 deterministic streaming guards: (a) **casing guard** — if `committed` (rstripped) is non-empty and does NOT end with a terminal `. ! ?`, lowercase the fragment's first cased alphabetic character (the first word's first cased char); (b) **period guard** — if the mid-sentence condition held (NOT iff casing mutated) and the fragment (rstripped) ends with `.`, strip **exactly one** trailing `.`. Pure, stdlib-only, deterministic on its two arguments. `clean()` stays **byte-identical**.

**Deliverable** (2 files, additive):
1. `voice_typing/textproc.py` — module-docstring guards section + `_SENTENCE_TERMINALS = ".!?"` constant + `apply_streaming_guards()` appended after `clean()`. Verbatim below.
2. `tests/test_textproc.py` — import-line edit + an additive guards test section (~19 tests). Verbatim below.

**Success Definition**:
- (a) `apply_streaming_guards` is pure (no input mutation, no I/O, no cfg) and returns the guarded fragment.
- (b) Empty/whitespace-only `committed` → fragment UNCHANGED (session start = sentence start; the capital is correct).
- (c) `timeout 60 .venv/bin/python -m pytest tests/test_textproc.py -q` → ~40 passed (verified baseline: **21 passed**; all existing tests untouched and green).
- (d) `git diff voice_typing/textproc.py` shows ONLY additions — the `clean()` function body is byte-identical.

## User Persona

Not applicable (internal pure function; DOCS: none — README tuning notes land with P1.M3.T10.S1 per PRD R6). The consumer is **P1.M2.T6.S1** (StreamingOutput): it applies the guards to every typed fragment (partial deltas AND commit retypes).

## Why

- **PRD §4.2quater R6 is the mandate**: "Deterministic guards (textproc, Rev 2), applied at typing time (pure, unit-tested): Casing — if committed does not end a sentence (no terminal `. ! ?`), lowercase the fragment's first word. Period — if the casing guard fired (we joined mid-sentence), strip one trailing `.` — a decoder closing a sentence it was just told it was continuing is spurious by definition." The rolling context prompt (P1.M2.T5) is the primary fix; these guards are the deterministic backstop.
- **Leaf task, zero dependencies** — pure functions, no upstream input; everything downstream (T6 streaming) depends on this.
- **Rev 1 `clean()` unchanged** (PRD: "Rev 1 clean() rules are unchanged") — the guards live alongside, not inside.

## What

One pure function + constant appended to textproc.py; additive tests. No behavior change to `clean()`.

### Success Criteria

- [ ] `apply_streaming_guards(committed, fragment) -> str` exists, pure, after `clean()`.
- [ ] Mid-sentence (committed non-empty, no terminal): first cased alpha char lowercased; exactly one trailing `.` stripped (`world.` → `world`; `wait...` → `wait..`).
- [ ] Already-lowercase fragment mid-sentence: casing no-op but the `.` is STILL stripped (guard fired on the condition).
- [ ] After-terminal / empty / whitespace-only committed: fragment returned unchanged.
- [ ] 21 existing tests green; ~19 new tests pass; only the 2 files changed.

## All Needed Context

### Context Completeness Check

_Pass._ The full function source (verbatim), the semantics table (incl. the empty-committed decision), the exact append sites (textproc.py ends at `return cleaned`, line 70; test import at line 17), the test matrix, and the verified baseline (21 passed) are all below + in the research note.

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/P1M2T1S1/research/streaming_guards.md
  why: "§1 semantics incl. the empty-committed→NOT-mid-sentence decision + the guard-fired-on-condition (not
        mutation) rule. §2 edit sites (the _SENTENCE_TERMINALS vs _TRAILING_PUNCT distinction). §3 the consumer
        contract. §4 test matrix. §5 scope/parallel boundary."
- file: voice_typing/textproc.py
  why: "70 lines, ends `return cleaned`. _TRAILING_PUNCT = '.!?,;' is the BLOCKLIST strip class — do NOT reuse it
        for the terminal check (different purpose). clean() + module docstring describe Rev 1 only; the guards
        section is additive."
  critical: "clean() must remain byte-identical (21 existing tests pin it). Append only."
- file: tests/test_textproc.py
  why: "21 tests (baseline verified). Import line 17: `from voice_typing.textproc import clean` → add the new
        import. Add the guards section at the END, mirroring the section-banner style."
- file: PRD.md  # §4.2quater "Deterministic guards (textproc, Rev 2)" — the verbatim guard spec
- docfile: plan/007_cfc245548aec/P1M1T3S1/PRP.md  # parallel: typing_backends press_backspace — NO overlap with textproc
```

### Known Gotchas

```python
# CRITICAL #1 — _SENTENCE_TERMINALS = ".!?" is NOT _TRAILING_PUNCT (".!?,;"). The blocklist strip class includes
#   ','/'"'; the sentence-terminal set is exactly '.!?' (PRD §4.2quater). Two constants, two purposes.
# CRITICAL #2 — "casing guard fired" = the MID-SENTENCE CONDITION held, not that casing mutated. An already-lowercase
#   fragment mid-sentence keeps the period guard active (the '.' is still spurious).
# CRITICAL #3 — Empty/whitespace-only committed → NOT mid-sentence (session start; capital correct). Do NOT lowercase
#   a session's first fragment.
# CRITICAL #4 — Period guard strips EXACTLY ONE '.' (the last non-whitespace char), preserving trailing whitespace:
#   'wait...' → 'wait..'; 'world. ' → 'world '. A trailing non-'.' char ('."') blocks the strip.
# GOTCHA #5 — Do NOT take cfg / add config — the guards are deterministic text transforms (PRD).
# GOTCHA #6 — Full paths + functional `timeout` on every command (AGENTS.md); pytest>=9.1.1, NO ruff/mypy.
```

## Implementation Blueprint

### Implementation Tasks

```yaml
Task 1: EDIT voice_typing/textproc.py — append the constant + function (verbatim), and extend the module docstring
  - ADD to the module docstring (after the CONSUMED BY block, before the closing quotes):
        REV 2 STREAMING GUARDS (PRD §4.2quater R6): apply_streaming_guards(committed, fragment) lowercases the
        fragment's first cased alphabetic character and strips one spurious trailing '.' when the committed text
        does not end a sentence (mid-fragment join). Pure; applied by the streaming state machine (P1.M2.T6.S1)
        to every typed fragment. clean() is unchanged (Rev 1 rules: blocklist, min_chars, whitespace).
  - APPEND at end of file (after `return cleaned`):

        # Sentence-terminal punctuation (PRD §4.2quater guards). DISTINCT from _TRAILING_PUNCT
        # (the blocklist strip class ".!?,;"): the terminal set is exactly . ! ? — a committed
        # string rstripped of whitespace ending in one of these ends a sentence.
        _SENTENCE_TERMINALS = ".!?"


        def apply_streaming_guards(committed: str, fragment: str) -> str:
            """Apply the Rev 2 deterministic streaming guards (PRD §4.2quater R6).

            Args:
                committed: the finalized text ending at the last commit checkpoint.
                fragment: the fragment about to be typed (a partial delta or a commit retype).

            Returns:
                The guarded fragment. Never rejects (clean() owns rejection); pure transform.

            Casing guard: if committed (rstripped) is non-empty and does NOT end with a terminal
            (. ! ?) we joined mid-sentence -> lowercase the fragment's first cased alphabetic
            character (the first word's first cased char; leading quotes/digits/punctuation are
            skipped). Empty/whitespace-only committed = session start = a sentence start: the
            capital is correct and the fragment is returned unchanged.

            Period guard: fires on the SAME mid-sentence condition (NOT on whether casing mutated
            — an already-lowercase fragment mid-sentence still gets the strip): a fragment whose
            rstripped form ends '.' is a decoder closing a sentence it was told it was continuing
            — spurious. Strip EXACTLY ONE trailing '.' (the last non-whitespace char), preserving
            any trailing whitespace: "world." -> "world"; "wait..." -> "wait..".
            """
            committed_r = committed.rstrip()
            if not committed_r or committed_r[-1] in _SENTENCE_TERMINALS:
                return fragment  # sentence start / after-terminal: capital + period kept

            # Casing guard: lowercase the FIRST cased alphabetic character, then stop.
            chars = list(fragment)
            for i, ch in enumerate(chars):
                if ch.isalpha() and ch != ch.lower():
                    chars[i] = ch.lower()
                    break
            result = "".join(chars)

            # Period guard: strip exactly one trailing '.' (checked on the rstripped view; the
            # char itself is removed, so preceding text + trailing whitespace are preserved).
            stripped = result.rstrip()
            if stripped.endswith("."):
                dot_idx = len(stripped) - 1
                result = result[:dot_idx] + result[dot_idx + 1:]
            return result
  - DO NOT: touch clean()/_TRAILING_PUNCT; reuse _TRAILING_PUNCT as the terminal set; take cfg; mutate inputs.

Task 2: EDIT tests/test_textproc.py — import + additive guards section (verbatim).
  - EDIT line 17: `from voice_typing.textproc import clean` → `from voice_typing.textproc import apply_streaming_guards, clean`
  - APPEND at end of file:

        # ---------------------------------------------------------------------------
        # Rev 2 streaming guards (PRD §4.2quater R6): apply_streaming_guards (P1.M2.T4.S1)
        # ---------------------------------------------------------------------------

        def test_guard_lowercases_first_word_mid_sentence():
            assert apply_streaming_guards("I said hello", "World.") == "world"

        def test_guard_keeps_capital_after_terminal_period():
            assert apply_streaming_guards("I said hello.", "World.") == "World."

        def test_guard_keeps_capital_after_exclamation_and_question():
            assert apply_streaming_guards("Stop!", "Hello") == "Hello"
            assert apply_streaming_guards("What?", "Hello") == "Hello"

        def test_guard_keeps_capital_at_session_start_empty_committed():
            assert apply_streaming_guards("", "Hello world.") == "Hello world."

        def test_guard_ignores_whitespace_only_committed():
            assert apply_streaming_guards("   \n ", "Hello") == "Hello"

        def test_guard_ignores_trailing_whitespace_in_committed():
            assert apply_streaming_guards("I said hello  ", "World") == "world"

        def test_guard_fragment_already_lowercase_is_unchanged():
            assert apply_streaming_guards("I said hello", "world") == "world"

        def test_guard_period_still_stripped_when_fragment_already_lowercase():
            # the guard FIRED (mid-sentence) though casing was a no-op -> '.' still spurious
            assert apply_streaming_guards("I said hello", "world.") == "world"

        def test_guard_skips_leading_non_alphabetic_characters():
            assert apply_streaming_guards("I said", '"Hello') == '"hello'
            assert apply_streaming_guards("I said", "123 Hello") == "123 hello"

        def test_guard_strips_only_one_period_from_ellipsis():
            assert apply_streaming_guards("I said hello", "wait...") == "wait.."

        def test_guard_casing_only_when_no_trailing_period():
            assert apply_streaming_guards("I said hello", "World") == "world"

        def test_guard_period_requires_trailing_dot():
            # '.' must be the last non-whitespace char; a trailing quote blocks the strip
            assert apply_streaming_guards("I said hello", 'World."') == 'world."'

        def test_guard_empty_fragment_returns_empty():
            assert apply_streaming_guards("I said hello", "") == ""

        def test_guard_both_empty():
            assert apply_streaming_guards("", "") == ""

        def test_guard_digits_only_fragment_unchanged_mid_sentence():
            assert apply_streaming_guards("I said hello", "123") == "123"

        def test_guard_is_pure_inputs_not_mutated():
            committed, fragment = "I said hello", "World."
            apply_streaming_guards(committed, fragment)
            assert (committed, fragment) == ("I said hello", "World.")

Task 3: VALIDATE.
  - `timeout 60 .venv/bin/python -m pytest tests/test_textproc.py -q` → ~37 passed (21 existing + 16 new), 0 failed.
  - `git diff voice_typing/textproc.py` → additions only; clean() body unchanged.
  - Full fast sweep green. Message if committed: "P1.M2.T4.S1: apply_streaming_guards casing+period pure guards (PRD §4.2quater R6) + 16 tests".
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T6.S1 (StreamingOutput): calls apply_streaming_guards(committed, fragment) on every typed
  fragment (partial deltas AND commit retypes) before backend.type_text. P1.M2.T5's rolling context prompt is the
  primary mid-sentence fix; these guards are the deterministic backstop.
UNCHANGED: clean() (byte-identical; 21 tests pin it), _TRAILING_PUNCT, config, daemon, typing_backends
  (P1.M1.T3.S1 owns press_backspace in typing_backends.py — NO overlap).
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_textproc.py -q        # ~37 passed, 0 failed
timeout 60 .venv/bin/python -m pytest tests/test_textproc.py -q -k guard   # the 16 new tests
git diff --stat voice_typing/textproc.py tests/test_textproc.py        # additions only
timeout 150 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # full fast sweep green
git status --short   # ONLY the 2 files
```

## Final Validation Checklist

- [ ] `apply_streaming_guards` pure, appended after `clean()`; `_SENTENCE_TERMINALS = ".!?"` (not `_TRAILING_PUNCT`).
- [ ] Mid-sentence casing + exactly-one-period semantics per the 16 tests; empty-committed unchanged.
- [ ] 21 existing tests green (clean() byte-identical); full fast sweep green; only 2 files changed.

## Anti-Patterns to Avoid

- ❌ Don't modify `clean()` or reuse `_TRAILING_PUNCT` as the terminal set (that's the blocklist strip class ".!?,;").
- ❌ Don't fire the period guard on "casing mutated" — it fires on the mid-sentence CONDITION.
- ❌ Don't lowercase on empty/whitespace committed (session start = sentence start).
- ❌ Don't strip more than one '.' or touch non-trailing '.'s; don't add cfg/params (pure, 2 args).
- ❌ Don't run pytest without `timeout`; no bare python/pytest (zsh aliases); no ruff/mypy (not configured).

---

## Confidence Score

**10/10** — a leaf pure function with the full source + 16 verbatim tests given, `clean()` untouched (additions only), semantics edge cases all enumerated and decided (empty-committed, already-lowercase, ellipsis, trailing-quote, purity), baseline verified (21 passed), and zero dependency/overlap risk (the parallel task edits only typing_backends.py).
