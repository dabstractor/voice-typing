# Research — P1.M1.T4.S2: Replay the 4× incident sequence as a regression test (D3.3)

Sources read this session (all claims below trace to these):
- `plan/008_a47116bb2b79/P1M1T4S1/PRP.md` (the sibling PRP — the bound this test consumes; TREAT AS CONTRACT)
- `plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md` PART D (:267-374)
- `tests/test_daemon.py` :4440-4563 (`_make_cancel_daemon`, `_FakeStream`, the cancel pins),
  :5100-5194 (BUG-004 partial gate, the lost-sentinel self-heal family)
- `voice_typing/streaming.py` :236-237, :315, :317-331, :341-382, :428-458, :500-535, :560-573
- `voice_typing/daemon.py` :1460-1499 (`_touch_speech`), :1500+ (`_on_partial`)

## 1. The exact incident sequence to replay (baseline Part D, "Exact event-sequence")

1. Arm; feed partials so text() is in flight and a tail is pending.
2. Backspace press #1 → `cancel()` (latch + stamp S1, host.cancel(), tail reset).
3. Sentinel LOST — do NOT call `host.mark_cancel_sentinel()` (the cancel-raced-text()-boundary leak).
4. User re-speaks: partial → `_touch_speech()` (engine `resume()`; partials stream live again — tail grows)
   — daemon latch STILL closed.
5. Final of the re-said sentence arrives at S1+δ, δ < 5 s → **DROPPED** (freeze(session=True) +
   reset_boundary(); nothing typed/recorded — the "missing section").
6. Backspace press #2 while the new text is in flight → re-latch, stamp refreshed to S2 = now.
7. Re-speak → final at S2+δ, δ < 5 s → DROPPED again. Repeat ×4 (the incident: 4 dropped finals).

## 2. The T4.S1 contract this test builds on (from the sibling PRP, verbatim behavior)

- Constant `_CANCEL_SUPPRESS_MAX_DROPS: int = 3` (daemon.py ~:165, next to `_CANCEL_SUPPRESS_TIMEOUT_S` :164).
- Counter `self._cancel_suppress_drops` (init ~:675 next to `_cancel_suppress_since`).
- At the drop site (~:1213ff): increment guarded on `_cancel_suppress_final` STILL True;
  `>= 3` → `logger.warning("cancel: suppression window dropped %d consecutive finals (sentinel
  lost + re-latch chain) — force-closing and processing this final", ...)` + clear flag/stamp/
  counter + FALL THROUGH to clean/commit (processed); else `return` (dropped).
- Counter resets ONLY at healthy closes: timeout self-heal, sentinel consume, the cap force-close
  itself, fresh `_arm()`. **NOT** in `cancel()`'s re-latch (the whole point).
- Net behavior: drops 1 and 2 are silent; the **3rd consecutive drop is force-closed and
  PROCESSED** (typed + recorded, WARNING logged). A re-press re-stamps the window but does NOT
  restore the budget; a healthy close does.
- T4.S1 adds 3 tests under banner `# P1.M1.T4.S1 — suppression-window re-latch chain bound (D3.3)`
  (cap force-close; re-press no-reset; sentinel-close reset). T4.S2 must NOT duplicate them —
  T4.S2 owns the FULL 7-step ×4 incident replay only.

## 3. The proven test seams (tests/test_daemon.py)

- `_make_cancel_daemon()` :4454 — ARMED daemon + `_FakeHost` + `_text_in_flight` set; returns
  `(d, fb)`; `d._backend` (fake with `.typed` list of strings + `("bs", n)` tuples), `d._host`
  (`.cancel_calls`, `.mark_cancel_sentinel()`, `.consume_cancel_mark()` — mirrors
  recorder_host.py:310-319 via _FakeHost :625-631). No threads, no CUDA; everything synchronous.
- `:4529` `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` — PROVES the exact
  chained seam sequence: `d.cancel()` → `d.on_final("racing tail")` (dropped; nothing typed) →
  `host.mark_cancel_sentinel()` → `d.on_final("")` (window closes) → `d._touch_speech()` →
  `d.on_final("fresh sentence")` → `be.typed == ["fresh sentence", " "]`, `fb.finals == [...]`.
  I.e. `_touch_speech()` lifts the drop's session freeze and the next final TYPES.
- `:5142` `test_lost_sentinel_self_heals_after_timeout` — the style to mirror (per the work item):
  direct flag asserts (`d._cancel_suppress_final is True/False`, `d._cancel_suppress_since`),
  stamp aging by direct poke, `d._touch_speech()` before the recovered final, commit shape
  `["fresh sentence", " "]` (final + trailing " ").
- `:5100` BUG-004 test — proves `d._on_partial("hello there")` types while armed (substring assert
  style `"hello there" in "".join(be.typed)`), and that `_on_partial` is gated on `_listening`.
- `d._touch_speech()` (:1460) — fires `stream.resume()` (clears engine `_suppressed`; lifts a
  stranded non-backend session freeze), resets idle clock, re-arms `_final_pending`.
  `d._on_partial(text)` (:1500) — routes through the engine (types unless `_suppressed`).
  Tests call BOTH separately (real flow: the child's speech event rides every partial).

## 4. Streaming engine facts the asserts rely on (voice_typing/streaming.py)

- `_committed`/`_tail` :236-237; `pending_tail_len()` :315 → `len(self._tail)` (public-ish, used
  by the daemon's cancel compensation).
- `reset_boundary()` :341-382 — the boundary reset: ABSORBS tail into committed (keystroke-free),
  `_tail = ""` (:378), `_suppressed = False` (:380), clears divergence-debounce state. So after
  every dropped final: `pending_tail_len() == 0` — THE boundary-reset invariant assert.
- `reset_after_cancel()` :317-331 — cancel's engine side: `_tail = ""`, `_suppressed = True`.
- `resume()` :428-458 — `_suppressed = False` ALWAYS; lifts session-class freezes of non-backend
  origin (the drop-freeze qualifies — proven by :4529's recovery leg).
- `freeze(reason, session=True)` :500+ — the drop's freeze; survives reset_boundary (session class).
- `on_partial` :560+ — mirror-only while `_suppressed` (:573); types otherwise (minimal-diff).
- Commit shape: final types as its text then a separate `" "` entry (append_space; :5142/:4529
  assert `be.typed == ["fresh sentence", " "]`).

## 5. Test design decisions (this PRP)

- ONE comprehensive daemon-level test (the work item: "the 4× incident sequence ... a regression
  test", singular), unrolled (not looped) for precise per-cycle asserts, mirroring :5142's style.
- Replay = 3 chained press→re-speak→dropped-final cycles + a 4th utterance WITHOUT a press
  (recovery). Rationale: with cap=3 the 3rd consecutive drop is PROCESSED, so the user's sentence
  lands and the correction loop ENDS — the incident's 4th drop is unreachable. A mechanical 4th
  press would start a FRESH budget (drop 1 of a new chain — correct but confusing to assert as
  "incident pinned green"); fresh-budget mechanics are already pinned by T4.S1's tests.
- Sentinel deliberately LOST every cycle: never call `host.mark_cancel_sentinel()` (Part D step 3).
- Feed ONE partial per cycle (after `_touch_speech()`) so `pending_tail_len() > 0` before each
  final — making the per-drop `pending_tail_len() == 0` invariant assert NON-vacuous — and so
  press #1 has a real pending tail to compensate (assert a `("bs", n)` batch fired, NOT the exact
  n — compensation exactness is T3's pinned domain, and the engine's leading-space synthesis
  makes exact-n brittle here).
- Per-cycle asserts: window flag/stamp (stamp strictly increases per re-press — pins the per-press
  re-stamp, the defect's fuel), `d._cancel_suppress_drops` (survives re-press; 0 after healthy
  closes), `fb.finals == []` while dropping, `"sentence N" not in` typed-join while dropping,
  `pending_tail_len() == 0` after every drop, `host.cancel_calls` increments per press,
  `d.is_listening()` stays True (cancel never disarms).
- NO caplog assert (logging capture config not pinned in this suite; state+behavior asserts are
  the contract — the WARNING itself is T4.S1's concern).
- NO edits outside tests/test_daemon.py (work item: test-only; DOCS: none). Precondition gate:
  T4.S1's bound MUST already be in daemon.py (`grep _CANCEL_SUPPRESS_MAX_DROPS`) — else STOP and
  report the missing dependency; this task does NOT implement the bound.

## 6. Scope boundaries

- Consumes T4.S1 (daemon.py bound + its 3 tests). Disjoint from parallel T3.S2
  (tests/test_key_listener.py). No streaming.py / recorder_host.py / config / README / docs /
  plan-file edits. D3.3 "closed" = this incident replay green at the T4.S1-bounded HEAD; the
  test's banner docstring is the closure record (Mode A — "DOCS: none").
