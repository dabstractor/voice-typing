# Research notes — P1.M2.T8.S1 (BUG-008: case-insensitive EXTEND comparison)

## Root cause (verified in current code, post-P1.M1)

- `voice_typing/streaming.py` has exactly TWO case-sensitive extend sites (PRD's :328/:417 are stale line numbers — P1.M1 moved them):
  - `on_partial` EXTEND test, **~line 398**: `if self._tail and text.startswith(self._tail):`
  - `commit()` EXTEND test, **~line 504**: `if self._tail and text.startswith(self._tail):`
  (grep `startswith` in voice_typing/ — only these two in streaming.py.)
- `voice_typing/textproc.py` `apply_streaming_guards` (lines 82–134): rule (a) lowercases the FIRST cased char of a fresh fragment when `committed.rstrip()` is non-empty and doesn't end in `.!?` → guarded tail `the quick` can never case-sensitively prefix-match decoder partials `The quick brown…` → every later partial = rate-limited (300 ms) full rewind+retype. Rule (b) strips one trailing `.` in the same branch.

## Fix shape (from the tasks.json contract + PRD h2.5)

Case-insensitive prefix comparison, **comparison-only** (typed strings never folded). Length-safe because per-CHAR casefold compare over `zip()`; `casefold()`/`lower()` on whole strings can change length (`'ß'→'ss'`, `'İ'`→2 chars) and would corrupt `delta = text[len(self._tail):]`. Delta then guarded exactly as today. Mirror into `commit()`'s extend branch too (keeps partial/commit consistent; no existing test encodes case-mismatch-at-commit as a revise — verified by grep of `tests/test_streaming_commit.py`).

## Test landmine (must update, do not delete)

`tests/test_streaming_core.py` **`test_backspace_failure_freezes_and_does_not_propagate` (~line 334)** deliberately feeds `"Hello world"` over tail `"hello wor"` *because* the re-capitalization currently forces the REVISE path (whose `press_backspace` raises). After the fix that input becomes an EXTEND → the test breaks. Update the partial to a genuine non-prefix retraction (repo idiom: `"hello wrl"`, line ~250) and fix the comment.

## Test harness facts (tests/test_streaming_core.py)

- Doubles: `RecordingBackend` (records `("type", s)`/`("bs", n)`; `press_backspace(n<=0)` unrecorded no-op), `FakeFeedback` (`.partials`), `FakeClock`, helpers `_make_stream(...)` / `_typed(be)`.
- Extend assertion style: `_typed(be) == ["the quick", " brown fox", " jumps"]` (test at ~line 105).
- White-box seeding `stream._committed = "Then he said"` exists (~line 114) but public `commit()` is landed — prefer it.
- `tests/test_streaming.py` (screen-model/fuzz, pure doubles, no CUDA): asserts delta-only extends (`screen_after.startswith(prev.screen_after)`, ~:1127) and append-monotone commits (`ec.startswith(base)`, ~:1224) — both remain true under case-insensitive extends; include it in the gate.

## Verified commands (repo AGENTS.md: inner `timeout` + bash-tool timeout)

- `timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -q` (docstring in that file)
- `timeout 300 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_commit.py tests/test_textproc.py -q`
- `timeout 600 uv run pytest tests/test_streaming.py -q`
- `ruff` on PATH (`~/.local/bin/ruff`); `uv` on PATH.
- AVOID: `tests/test_feed_audio.py`, `tests/test_daemon.py`, `tests/test_recorder_host.py` (CUDA, minutes).

## Docs

None for this subtask (contract: "DOCS: none — internal flicker fix"). README sweep belongs to P1.M3.T9 (its contract already lists this behavior). Touch only the streaming.py module-docstring EXTEND phrase.
