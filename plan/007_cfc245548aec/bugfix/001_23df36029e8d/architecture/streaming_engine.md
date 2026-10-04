# Streaming engine findings — `voice_typing/streaming.py` + `textproc.py`

All lines verified by direct read. Engine = `StreamingOutput` (class :100), constructed per armed session by the daemon.

## Public API (the daemon seam — exact names are load-bearing)

- `__init__(backend, feedback, streaming, *, append_space=True, rate_limit_s=_FULL_REWIND_RATE_LIMIT_S, clock=time.monotonic)` :123 — `backend` needs `type_text(s)` / `press_backspace(n)`; `feedback` needs `update_partial(text)`.
- Properties: `committed` :167, `tail` :172, `frozen` :177, `frozen_session` :182, `pending_tail_len()` :192.
- Lifecycle: `reset_after_cancel()` :197, `reset_boundary()` :208, `reset_session()` :226, `freeze(reason, *, session=False)` :248, `note_user_keypress()` :279.
- Runtime: `on_partial(text)` :301, `commit(final_text)` :377.

## State machine internals

- `_committed` (checkpoint), `_tail` (tentative typed, never trailing space), `_frozen`/`_frozen_session`, `_suppressed`, `_last_full_rewind` (300ms full-rewind rate limit). All under `self._lock`.
- `reset_boundary()` :208: clears `_tail`, clears `_suppressed`, lifts per-utterance freeze ONLY. **Drops the tail WITHOUT absorbing it into `_committed`** — relevant to BUG-001: after a rejected final the on-screen fragment is orphaned from the checkpoint (guards/context/mirror go stale).
- `reset_session()` :226: clears everything incl. session freeze; sends NO keystrokes.
- `freeze()` :248: PROMOTE-ONLY (session upgrades per-utterance, never downgraded). Logs WARNING.
- `on_partial()` :301 order: streaming-off → raw mirror; `_suppressed` → raw mirror; `_frozen` → tail mirror; else EXTEND if `self._tail and text.startswith(self._tail)` :328 (CASE-SENSITIVE — BUG-008) typing guarded delta; else REVISE (full rewind+retype) gated by `rate_limit_s`, stamping `_last_full_rewind`.
- `commit()` :377: frozen → absorb `committed = join(committed.rstrip(), tail)`, clear tail+suppressed, mirror, RETURN — **no `_safe_type(" ")` even when `_append_space`** (BUG-003); extend → guarded delta; revise/fresh → rewind+guarded retype; then `space = " " if self._append_space else ""`, `_safe_type(space)`, `committed = join(...)+space`.
- `_safe_type`/`_safe_backspace` :472/:485: backend exception → SESSION freeze, return False (fail-safe).
- Guards: `textproc.apply_streaming_guards(context, fragment)` — mid-sentence (context not empty and not ending `./!?`) lowercases the fragment's first cased char and strips one trailing `.` (textproc.py :107-134). PURE function.

## Bug validations (engine side)

- **BUG-001 ( Critical) confirmed.** daemon.py:1154 freezes session-class on a rejected final. While frozen: `on_partial` :318 tail-mirror only; `commit` :415 absorbs without typing. Only `reset_session()` (next arm/disarm) lifts. PRD repro sequence produces zero backend calls after the freeze.
- **BUG-002 confirmed.** `reset_after_cancel` :206 sets `_suppressed`; `on_partial` :314 mirrors only; cleared at `reset_boundary` :221 or `commit` :424/:458 — but the daemon never fires a boundary between the cancel and the next real final (sentinel dropped upstream).
- **BUG-003 confirmed.** Frozen-absorb path :415-425 has no append_space; the daemon's post-commit `reset_boundary()` then lifts the per-utterance (user-keypress) freeze and the next utterance types flush against the absorbed tail → glued words. PRD repro yields screen `Hello world the quicknew sentence`.
- **BUG-008 confirmed.** EXTEND test :328 is case-sensitive; the guard lowercases a fresh mid-sentence fragment's first word, so subsequent capitalized decoder partials can never prefix-match → every cycle is a rate-limited full rewind (~3/s flicker). Same `startswith` pattern exists in `commit()`'s extend branch (:417 region) — consider mirroring the fix there for consistency.

## Fix directions (per PRD §Recommendations, h2.5)

1. **BUG-001/002 (shared seam):** add ONE explicit engine resume API, e.g. `resume()` (name TBD by implementer): clears `_suppressed` and lifts a rejected-final freeze, callable only when new speech is certain. Daemon calls it from `_touch_speech()` (:1354, fed by the child's `on_speech` `("speech",{})` event — verified in recorder_host.py :447-448) — i.e. at the NEXT utterance's start, not at the boundary. Do NOT simply retag the daemon's freeze to `session=False`: reset_boundary() fires on the very next line and stray late partials of the rejected utterance would then revise a frozen screen tail. Additionally: absorb the rejected utterance's frozen tail into `_committed` when the boundary is reset (mirror/context truth), mirroring the frozen-commit join.
2. **BUG-003:** in the frozen-absorb path, type the trailing space via `_safe_type(" ")` when `_append_space` (fail-safe: a failure keeps the freeze; note promote-only semantics make a per-utterance freeze session on failure — acceptable, document it) and include it in the join exactly once.
3. **BUG-008:** normalize case for the prefix COMPARISON only (typed text keeps decoder casing). Beware length-changing casefolds (`İ`.casefold()); prefer a length-preserving compare (e.g. both sides `.lower()` for the startswith test, then slice delta by tail length — verify length equality of the lowered prefix slice, else fall back to revise).

## Test seams

Fast, no CUDA: construct `StreamingOutput(fake_backend, fake_feedback, streaming=True, append_space=True)` and drive `on_partial`/`commit`/`freeze`/`reset_boundary` directly (patterns in `tests/test_streaming_core.py`, `test_streaming_freeze.py`, `test_streaming_commit.py`). NOTE: `tests/test_streaming_core.py:292` calls `stream.reset_boundary()` manually ("next utterance begins") — this is exactly the daemon-sequencing masking the PRD calls out; daemon-level regression tests must NOT rely on it.
