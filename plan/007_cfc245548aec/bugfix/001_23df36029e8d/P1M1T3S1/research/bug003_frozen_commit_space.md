# Research: BUG-003 — frozen commit omits append_space (VERIFIED)

**Status:** Verified against live `voice_typing/streaming.py` (573 lines), `tests/test_streaming_commit.py`,
`tests/test_streaming_freeze.py`. Baseline: `test_streaming_commit.py + test_streaming_core.py` = **49 passed**.

## 1. The bug (verbatim — streaming.py:484-494)

```python
            if self._frozen:
                self._committed = " ".join(
                    p for p in (self._committed.rstrip(), self._tail) if p
                )
                self._tail = ""
                self._suppressed = False
                self._feedback.update_partial(self._committed)
                return
```
No `_safe_type(' ')` — no trailing space. The non-frozen paths (same fn, ~:518-526) DO type it:
```python
            space = " " if self._append_space else ""
            if space and not self._safe_type(space):
                return
            self._committed = (" ".join(p for p in (self._committed.rstrip(), typed) if p) + space)
```

**Trigger chain (verified):** `note_user_keypress()` (:349) freezes PER-UTTERANCE (the evdev listener
routes ALL non-Backspace keys incl. Shift/Ctrl/CapsLock here — modifiers insert nothing but still
freeze) → the final arrives → `commit()` takes the frozen-absorb branch (no space) → daemon's
`reset_boundary()` (~daemon.py:1243) lifts the per-utterance freeze → the next utterance's fresh
fragment types flush against the absorbed tail → **'…the quicknew sentence'** (glued).

**Trace of the contract's test sequence under the fix** (guards: empty committed → verbatim; committed
without terminal punct → lowercase first word — so 'New' → 'new'):
`on_partial('Hello world')` → type 'Hello world' · `commit` (EXTEND, delta='') → type ' ' → committed
'Hello world ' · `reset_boundary` · `on_partial('the quick')` → type 'the quick' · `note_user_keypress()`
→ frozen · `commit('the quick')` → **FIX: type ' '** → committed 'Hello world the quick ' ·
`reset_boundary` lifts · `on_partial('New sentence')` → type 'new sentence'. Screen:
**'Hello world the quick new sentence'** ✓ (matches the PRD h3.2 expected screen, lowercase 'new').

## 2. The fix (one block, mirroring the non-frozen discipline exactly)

```python
            if self._frozen:
                # BUG-003 (P1.M1.T3.S1): absorb WITHOUT revision keystrokes, but still
                # honor append_space — type the separator so the next utterance's first
                # word does not glue onto the absorbed tail once reset_boundary() lifts
                # a per-utterance freeze (PRD §4.2quater rule 2). Space exactly once
                # (rstrip base + " + space"), the non-frozen path's discipline.
                # Fail-safe: a space-type failure freezes SESSION-class (promote-only)
                # — acceptable (the tail is stranded anyway); absorb nothing then.
                space = " " if self._append_space else ""
                if space and not self._safe_type(space):
                    return  # frozen (session); checkpoint stays at the pre-commit boundary
                self._committed = (
                    " ".join(p for p in (self._committed.rstrip(), self._tail) if p)
                    + space
                )
                self._tail = ""
                self._suppressed = False
                self._feedback.update_partial(self._committed)
                return
```
Unconditional across freeze classes (per-utterance AND session): the space is an ADDITION (PRD rule 4
bans auto-DELETE only); in the session-class case nothing further types before reset_session() clears
state anyway; a failing `_safe_type` is the documented fail-safe. Do NOT touch `reset_boundary()`'s
frozen-absorb (~:240): it serves session-class stranded tails (nothing follows in-session) — no gluing
is possible from that path.

## 3. Existing tests that pin the BUG (must be updated — verified they run append_space=True)

Both helpers default `append_space=True` (commit-suite's `_make_stream` passes it explicitly
:75-87; freeze-suite's `_make_stream` :63-71 omits it → StreamingOutput default True):

| test | file:line | current pin | updated pin |
|---|---|---|---|
| `test_commit_frozen_touches_no_backend_and_absorbs_tail` | commit:244 | `calls == [("type","hello wor")]`, `committed == "hello wor"` | RENAME → `test_commit_frozen_absorbs_tail_and_types_separator`; `calls == [("type","hello wor"),("type"," ")]`; `committed == "hello wor "` |
| `test_commit_frozen_with_empty_tail` | commit:256 | `calls == []` | construct `append_space=False` (keeps the pure empty-absorb semantics); assertions unchanged |
| `test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types` | freeze:197 | `calls == [("type","hello wor")]`, `committed == "hello wor"`, final `+ ("type","next")` | `+ ("type"," ")` after the commit; `committed == "hello wor "`; final calls `[("type","hello wor"),("type"," "),("type","next")]` — screen now correctly space-separated (the fix demonstrated) |
| `test_session_frozen_tail_late_commit_absorbs_without_keystrokes_and_stays_frozen` | freeze:228 | `calls == [("type","hello wor")]`, `committed == "hello wor"` | RENAME → `..._absorbs_plus_separator_and_stays_frozen`; `+ ("type"," ")`; `committed == "hello wor "`; freeze assertions unchanged |

NOT affected: `test_commit_space_type_failure_keeps_checkpoint_at_boundary` (commit:292 — non-frozen
EXTEND path), `test_reset_boundary_under_freeze_absorbs_tail_into_committed` (freeze:325 — drives
reset_boundary, not commit), test_streaming_core.py (no frozen-commit assertions).

## 4. New tests (TDD — write FIRST; contract's exact sequence)

1. `test_frozen_commit_types_separator_prd_sequence` (commit suite): the contract sequence verbatim →
   reconstruct screen as `"".join(t for m,t in be.calls if m=="type")` →
   `assert screen == "Hello world the quick new sentence"`; also `committed == "Hello world the quick "`.
2. `test_frozen_commit_append_space_false_stays_space_free` (commit suite): same sequence with
   `append_space=False` → `("type", " ")` appears NOWHERE in be.calls.
3. `test_frozen_commit_space_type_failure_absorbs_nothing` (commit suite): on_partial('hello wor'),
   note_user_keypress(), `be._fail_type = True`, commit('hello world') → frozen_session True,
   `committed == ""`, `tail == "hello wor"` (nothing absorbed — mirrors the non-frozen boundary
   discipline), no exception.

## 5. Verify + scope

- `timeout 600 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q`
  (contract names commit+core; **freeze MUST be added** — it pins the same behavior). Equivalent:
  `.venv/bin/python -m pytest …`. Full fast suite after.
- Files: `voice_typing/streaming.py` (1 block) + `tests/test_streaming_commit.py` (2 updated + 3 new) +
  `tests/test_streaming_freeze.py` (2 updated). **Parallel P1.M1.T2.S2** edits tests/test_daemon.py +
  daemon.py (comment-only) — DISJOINT. No daemon edits, no reset_boundary changes, no README
  (P1.M3.T9 owns the doc sweep).
