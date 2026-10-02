# Research: apply_streaming_guards pure functions (P1.M2.T4.S1, PRD §4.2quater R6)

Target: add `apply_streaming_guards(committed: str, fragment: str) -> str` to
`voice_typing/textproc.py` — the Rev 2 deterministic casing + period guards. Pure, stdlib-only,
unit-testable. `clean()` stays BYTE-IDENTICAL (21 existing tests must stay green; baseline verified:
**21 passed in 0.01s**).

## 1. Semantics (derived from PRD §4.2quater "Deterministic guards" + the contract)

**Mid-sentence** = `committed.rstrip()` is non-empty AND its last char is NOT in `.!?`.
DECISION (implicit in the contract, explicit here): **empty/whitespace-only committed → NOT
mid-sentence** — a session's first fragment IS a sentence start (the capital is correct; the
PRD's guards exist to fix *mid-paragraph* fragments). This is what P1.M2.T6.S1 (the consumer)
needs: `committed=""` at the first fragment of a session.

1. **Casing guard** (fires iff mid-sentence): lowercase the fragment's **first cased alphabetic
   character** (the first word's first cased char). Implementation: scan for the first `ch` with
   `ch.isalpha() and ch != ch.lower()`, lowercase just it, stop. Leading non-alpha chars (quotes,
   digits, punctuation) are skipped: `"Hello` → `"hello`, `123 Hello` → `123 hello`. An
   already-lowercase fragment is unchanged — but the guard still "fired".
2. **Period guard** (fires iff **the mid-sentence condition** held — NOT iff casing mutated):
   if `result.rstrip().endswith('.')`, remove **exactly one** trailing '.' (the last
   non-whitespace char), preserving any trailing whitespace: `world.` → `world`; `wait...` →
   `wait..`; `world. ` → `world `. A trailing non-'.' char (e.g. `."`) blocks the strip.
3. **Not mid-sentence** (empty committed, or ends `.`/`!`/`?`): return the fragment UNCHANGED
   (capital + period kept). Heuristic limitation (documented, accepted): `Dr.` counts as terminal.

Purity: no mutation of inputs, no I/O, no config — deterministic on (committed, fragment) only.
Signature is a suggestion per the contract; `apply_streaming_guards` is used.

## 2. Exact edit sites (verified; textproc.py is 70 lines)

- Module docstring: currently describes ONLY clean(). ADD a short "REV 2 STREAMING GUARDS"
  section + a CONSUMED BY line (P1.M2.T6.S1 StreamingOutput) — additive; the clean() pipeline
  text is untouched (clean() itself byte-identical).
- Append `_SENTENCE_TERMINALS = ".!?"` + `apply_streaming_guards()` AFTER `clean()` (the file
  ends at `return cleaned`, line 70). Keep the constant DISTINCT from `_TRAILING_PUNCT`
  (".!?,;" — the blocklist strip class; different purpose, do NOT reuse).
- tests/test_textproc.py: import line 17 becomes
  `from voice_typing.textproc import apply_streaming_guards, clean`; ADD a guards section at the
  END (~19 tests). Existing 21 tests untouched.

## 3. The consumer contract (P1.M2.T6.S1 — why these exact semantics)

Applied to EVERY typed fragment (partial deltas AND commit retypes) by StreamingOutput:
mid-stream fragments inherit a spurious capital/trailing period from the decoder "starting" a
sentence it was told it was continuing (the rolling context prompt, P1.M2.T5, is the primary fix;
these guards are the deterministic backstop). The consumer passes the committed prefix + the
fragment delta and types the return value.

## 4. Test matrix (the contract's list, expanded)

mid-sentence lowercase / after-terminal `.`/`!`/`?` keep / empty-committed keep (session start) /
whitespace-only committed / trailing-ws committed / already-lowercase unchanged / already-lowercase
period STILL stripped (guard fired on the condition) / leading non-alpha skipped / exactly one '.'
stripped / `...` → `..` / no-'.' casing-only / `."` not stripped / empty fragment / both empty /
purity (inputs unmutated) / digits-only fragment.

## 5. Scope + parallel context

- Files: `voice_typing/textproc.py` (+~45 lines) + `tests/test_textproc.py` (+~19 tests). Nothing else.
- P1.M1.T3.S1 (parallel, Implementing): press_backspace in typing_backends.py + its tests. NO overlap.
- pytest>=9.1.1; NO ruff/mypy. Full paths + functional `timeout` (AGENTS.md).
  Validate: `timeout 60 .venv/bin/python -m pytest tests/test_textproc.py -q` (21 → ~40).
