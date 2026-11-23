# Research — P1.M1.T4.S1: Bound the suppression-window re-latch chain (D3.3)

> The 4× "missing/repeated sections" incident (week 2026-11-12..18) happened WITH both 4640041
> backstops live (5 s timeout self-heal + dropped-final boundary reset). The unbounded mechanism
> (baseline Part D, item 4): **every new Backspace press re-latches + re-stamps the window**
> (daemon.py:1789-1791 "refreshed per press"), so a cancel → re-speak → cancel → re-speak loop
> chains the window open indefinitely, dropping each re-said sentence's final — no bound ever
> fires. This task implements ONE product decision to bound the chain; the sibling T4.S2 replays
> the 4× incident sequence as its regression test.

## §1 — The latch state machine at HEAD (verified file:line this round)

- **Constant**: `_CANCEL_SUPPRESS_TIMEOUT_S: float = 5.0` — daemon.py:164 (rationale :151-163).
- **Init**: `self._cancel_suppress_final = False` @:673; `self._cancel_suppress_since` @:674
  (LOST-SENTINEL SELF-HEAL stamp).
- **Latch** — `cancel()` @:1788-1792: `self._cancel_suppress_final = True`;
  `self._cancel_suppress_since = time.monotonic()` — **refreshed per press** — then `host_cancel()`.
- **Drop path** — `on_final` @:1158-1217, structure:
  1. `if self._cancel_suppress_final:` (:1158)
  2. timeout self-heal (:1166-1189): if `now - _cancel_suppress_since > 5.0` → WARNING, clear
     flag+stamp, absorb accumulated tail (`stream.freeze(..., session=True)` + `reset_boundary()`
     when streaming + tail pending), **fall through** and process the final.
  3. else (:1193-1207): `host.consume_cancel_mark()` — True → clear flag+stamp, `_final_pending
     = False`, `_utterance_finalized = True` (BUG-007 bookend).
  4. BOTH paths (:1213-1216, KEEP): every DROPPED final is still a boundary —
     `stream.freeze("final dropped (cancel suppression window latched)", session=True)` +
     `reset_boundary()` — then `return` @:1217 (no clean/type/record).
- **Healthy exits**: sentinel consume (:1194-1197), timeout self-heal (:1177-1178), fresh `_arm()`
  (:1371-1374 clears flag AND stamp). Partials do NOT close the daemon latch — `_touch_speech`
  (:1460-1499) only calls `stream.resume()` (:1498-1499) which lifts the ENGINE `_suppressed`
  (streaming.py), a separate mechanism.

## §2 — Why the chain is unbounded (the incident mechanism, Part D item 4)

The stamp-refresh-per-press defeats the 5 s bound: each press re-stamps, so a final arriving <5 s
after the LATEST press is always "within bound". The incident loop:

```
press #1 → latch, stamp S1, sentinel LOST (no mark_cancel_sentinel)
user re-speaks → partial → _touch_speech (engine resume; tail grows) — daemon latch STILL closed
final of the re-said sentence at S1+δ, δ<5s → DROPPED  ("missing section" #1)
press #2 (text in flight again) → RE-LATCH, stamp refreshed to S2
re-speak → final at S2+δ → DROPPED ("missing section" #2)  ... ×4
```

`test_lost_sentinel_self_heals_after_timeout` (:5142) covers only ONE cancel + a final >5 s later;
nothing pins the chained case. That is the open defect.

## §3 — THE PRODUCT DECISION (implement exactly this; record it in a code comment)

The contract offers (a) cap consecutive dropped finals per latch, or (b) close on genuinely-fresh
speech (partial after latch, no sentinel). **DECISION: (a), a drop-count cap — variant:**

> **The counter counts CONSECUTIVE dropped finals since the last HEALTHY close (sentinel
> consume / timeout self-heal / cap force-close / fresh arm) — and is deliberately NOT reset by
> a re-press re-stamp.** A per-press reset would re-open the exact unbounded chain (each cycle
> drops exactly 1 final per latch, cap never exceeded); only a healthy close restores the budget.

**Why (a) over (b):** (b)'s discriminator is unreliable — stray late partials of the cancelled
utterance are documented to arrive at `_touch_speech` "paired with their partial"
(:1486-1489 docstring); such a stray would prematurely close the window and let the racing REAL
final type (the double-type bug class the window exists to prevent). The drop counter increments
at the exact drop site (deterministic, race-free ordering under `_on_final_lock`).

**Cap value: `_CANCEL_SUPPRESS_MAX_DROPS: int = 3`.** Rationale (put in the comment): one healthy
cancel drops at most the racing real final (1) plus possible duplicate finals (RealtimeSTT
emission is not deduped at HEAD) before the sentinel closes the window; a sentinel-lost window
that has dropped 3 consecutive finals is by construction eating the user's re-said sentences —
the 4th final (the incident's exact count) must be PROCESSED. The cap force-close mirrors the
timeout self-heal's semantics (WARNING + close + already-reset boundary + fall through), so the
residual risk (processing a late racing final) equals the risk the 5 s self-heal already accepts.

## §4 — The verbatim implementation (3 edits in daemon.py)

**Edit 1 — constant** (next to `_CANCEL_SUPPRESS_TIMEOUT_S` @:164):

```python
_CANCEL_SUPPRESS_MAX_DROPS: int = 3
```
(with a short comment: consecutive dropped finals since the last HEALTHY close; NOT reset by a
re-press re-stamp — see on_final drop path. Bounds the D3.3 re-latch chain.)

**Edit 2 — init** (next to `self._cancel_suppress_since` @:674):

```python
        self._cancel_suppress_drops = 0
```

**Edit 3 — reset on the healthy closes + cap at the drop site (on_final :1158-1217):**
- timeout self-heal close (:1177-1178, where flag+stamp are cleared): add `self._cancel_suppress_drops = 0`.
- sentinel consume close (:1194-1197): add `self._cancel_suppress_drops = 0`.
- fresh `_arm()` (:1371-1374): add `self._cancel_suppress_drops = 0`.
- **the drop site** — replace the tail of the within-bound branch. Current (:1213-1217):

```python
                    if self._cfg.output.streaming:
                        self._stream.freeze(
                            "final dropped (cancel suppression window latched)",
                            session=True,
                        )
                        self._stream.reset_boundary()
                    return  # dropped: no clean, no type_text, no record_final
```

  NEW:

```python
                    if self._cfg.output.streaming:
                        self._stream.freeze(
                            "final dropped (cancel suppression window latched)",
                            session=True,
                        )
                        self._stream.reset_boundary()
                    # D3.3 re-latch chain bound (P1.M1.T4.S1): PRODUCT DECISION — cap consecutive
                    # dropped finals since the last HEALTHY close (sentinel consume / timeout
                    # self-heal / this cap / fresh arm). The counter is deliberately NOT reset by
                    # a re-press re-stamp: each press refreshing it would re-open the unbounded
                    # cancel→re-speak chain (one drop per latch, cap never reached). 3 covers the
                    # racing real final + duplicate finals; the NEXT drop is by construction the
                    # user's re-said sentence — force-close and process it (same residual risk the
                    # 5 s timeout self-heal already accepts).
                    self._cancel_suppress_drops += 1
                    if self._cancel_suppress_drops >= _CANCEL_SUPPRESS_MAX_DROPS:
                        logger.warning(
                            "cancel: suppression window dropped %d consecutive finals "
                            "(sentinel lost + re-latch chain) — force-closing and "
                            "processing this final",
                            self._cancel_suppress_drops,
                        )
                        self._cancel_suppress_final = False
                        self._cancel_suppress_since = None
                        self._cancel_suppress_drops = 0
                        # fall through: the boundary was just reset above; process this final
                    else:
                        return  # dropped: no clean, no type_text, no record_final
```

  NOTE the flow: after a force-close the code FALLS THROUGH to `cleaned = textproc.clean(text, ...)`
  (:1219) exactly like the timeout path. The sentinel-consume path already cleared the flag and
  reaches this same tail — a consumed sentinel then increments... wait, it MUST NOT: after a
  sentinel consume the flag is False and the final is the sentinel's own ("" or racing text) — the
  existing code returns at the same `return` for it. With the new structure, a consumed-sentinel
  final would increment the counter (harmless, since the close already reset it to 0 → becomes 1)
  and then RETURN via the else (1 < 3). Acceptable but noisy; cleaner: only count when the flag
  is STILL set, i.e. wrap the increment + cap check in `if self._cancel_suppress_final:` (after
  the sentinel-consume attempt). Prefer that (see the PRP's verbatim block, which guards on the flag).

**Mode A doc**: `cancel()`'s docstring (near :1760) gains one sentence: the suppression window is
bounded by BOTH the 5 s lost-sentinel timeout AND a 3-consecutive-dropped-finals cap that a
re-press re-stamp does NOT reset.

## §5 — TDD tests (daemon level, `_make_cancel_daemon()` @:4454 — armed daemon + _FakeHost +
text-in-flight; no threads, no CUDA; call cancel()/on_final() directly)

Existing pins to KEEP green: `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`
(:4529), `test_arm_clears_stale_cancel_suppression` (:4564),
`test_lost_sentinel_self_heals_after_timeout` (:5142), `test_sentinel_consume_clears_suppress_since`
(:5168), `test_fresh_arm_clears_suppress_since` (:5184).

New (banner `P1.M1.T4.S1` at the end of the cancel section / file):

1. `test_cancel_suppression_drop_cap_force_closes_window_and_processes_final` (THE RED TEST):
   sentinel lost (never `mark_cancel_sentinel()`); `d.on_final("first")`, `d.on_final("second")`
   → dropped (typed==[], finals==[]); `d.on_final("third")` → still dropped (drops==3 == cap →
   wait: cap fires when counter REACHES 3 — see §4: increments then `>= 3` force-closes. So drops
   1,2 return; drop 3 force-closes and PROCESSES). Assert: `be.typed == ["third", " "]`,
   `fb.finals == ["third"]`, flag False, counter 0. RED before: "third" is dropped (the bug).
2. `test_cancel_suppression_repress_restamp_does_not_reset_drop_counter` (the CHAIN bound — the
   incident shape, minimal): sentinel lost; press → drop "one" (drops=1) → `d.cancel()` again
   (re-latch, re-stamp; must reset `_text_in_flight`? `_make_cancel_daemon` sets it; a second
   cancel() with text_in_flight still set re-latches fine) → drop "two" (drops=2) → third final
   processed. RED before: unbounded (3rd, 4th, ... all dropped).
3. `test_cancel_suppression_drop_counter_resets_on_sentinel_close`: sentinel lost → 2 drops →
   then a HEALTHY window: `d.cancel()`; `host.mark_cancel_sentinel()`; `d.on_final("")` (sentinel
   consumed → counter 0) → then 2 more drops only reach 2 → 3rd final of the NEW chain processed.
   Simpler assert: after the sentinel close, `d._cancel_suppress_drops == 0`.

Keep tests to these 3 (the sibling **T4.S2** owns the full 4×-incident replay — do NOT duplicate it;
T4.S1's tests pin the BOUND mechanics).

FakeHost seam: `host.mark_cancel_sentinel()` + `host.consume_cancel_mark()` (:625-631) mirror
RecorderHost (:310-319); `d._backend.typed` accumulates ("text"," ") commits; `_FakeStream`/real
stream: the default `_make_cancel_daemon` daemon uses the REAL StreamingOutput (streaming cfg
default) — commits type `final + " "` (see :4557-4558).

## §6 — Verify + scope

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "cancel" -q      # all cancel tests
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q                  # full daemon suite
```

Scope: ONLY `voice_typing/daemon.py` (constant + init + 4 small on_final/arm edits + cancel()
docstring sentence) and `tests/test_daemon.py` (1 banner + 3 additive tests). NO streaming.py,
recorder_host.py, README, config. Parallel **T3.S2** owns `tests/test_key_listener.py`
(docstring-only) — DISJOINT. Sibling **T4.S2** builds its incident-replay regression test ON the
bound shipped here (its PRP will assert the chain terminates at the cap).

Machine gotchas: `.venv/bin/python` full path (zsh aliases), `timeout 600` wrapper (AGENTS.md
Rule 1), pytest only (no ruff/mypy), never run the daemon foreground.
