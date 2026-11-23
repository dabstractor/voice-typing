# PRP — P1.M1.T4.S1: Bound the suppression-window re-latch chain (D3.3)

## Goal

**Feature Goal**: Fix **D3.3** (the 2026-11-12..18 "dropped finals 4×" / "missing sections"
incident, open at HEAD per the G1 baseline Part D): the cancel-suppression window is latched in
`cancel()` (daemon.py:1788-1792 — `_cancel_suppress_final = True` + `_cancel_suppress_since =
time.monotonic()`, **refreshed per press**), and while latched `on_final` (:1158-1217) drops EVERY
final. The two existing backstops (the 5 s lost-sentinel timeout self-heal :1166-1189 and the
dropped-final boundary reset :1213-1216, both from 4640041) were LIVE during the incident — because
**every new Backspace press re-stamps the window**, a cancel → re-speak → cancel → re-speak loop
chains the window open indefinitely (each re-said sentence's final lands <5 s after the latest
press → "within bound" → dropped), and no bound ever fires. This task implements ONE product
decision — **(a) a cap on consecutive dropped finals since the last healthy close** (contract
option a, chain-aware variant: a re-press re-stamp does NOT reset the counter; only a healthy
close — sentinel consume / timeout self-heal / the cap itself / fresh arm — restores the budget) —
recorded in a code comment at the drop site. Option (b) (close on a fresh partial) is REJECTED
with rationale: stray late partials of the cancelled utterance are documented to arrive at
`_touch_speech` (:1486-1489) and cannot be discriminated from genuinely-new speech — a premature
close would let the racing real final type (the double-type bug class the window exists to prevent).

**Deliverable** (2 files edited, no new files):
1. `voice_typing/daemon.py` — (i) new constant `_CANCEL_SUPPRESS_MAX_DROPS: int = 3` near :164;
   (ii) new counter `self._cancel_suppress_drops = 0` in `__init__` near :674; (iii) counter reset
   added to the 3 healthy closes (timeout self-heal :1177-1178, sentinel consume :1194-1197, fresh
   `_arm()` :1371-1374); (iv) the cap check at the drop site (:1213-1217 → increment, force-close +
   WARNING + fall-through at >= 3, else return); (v) [Mode A] one sentence in `cancel()`'s
   docstring noting both bounds.
2. `tests/test_daemon.py` — 3 NEW daemon-level TDD tests under a `P1.M1.T4.S1` banner (cap
   force-closes + processes; re-press re-stamp does NOT reset the counter — the chain bound;
   sentinel close DOES reset it). No existing test touched.

**Success Definition**:
- (a) With the sentinel lost, the 3rd consecutive dropped final is FORCE-CLOSED (WARNING logged,
   flag+stamp+counter cleared) and PROCESSED (typed + recorded) — RED before (it is dropped).
- (b) A re-press re-stamp does NOT reset the counter: press→drop→press→drop→3rd final processed
   (the minimal incident shape — the chain terminates).
- (c) A healthy sentinel close DOES reset the counter (a subsequent window gets a fresh budget).
- (d) ALL existing behavior preserved: the sentinel consume / timeout self-heal / fresh-arm exits
   unchanged; **every dropped final still resets the utterance boundary** (:1213-1216 freeze+
   reset_boundary invariant — KEEP); `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`
   (:4529), `test_lost_sentinel_self_heals_after_timeout` (:5142), and the whole cancel suite stay green.
- (e) `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q` → 0 failures.
- (f) `git diff --name-only` == `{voice_typing/daemon.py, tests/test_daemon.py}`.

> **VERIFIED MECHANISM (this PRP's research, from baseline Part D + live source read):** the
> per-press re-stamp at :1789-1791 defeats the 5 s bound; no test pins the chained case
> (:5142 covers one cancel + a >5 s final only). The implementing agent writes the failing tests
> first, then applies the verbatim edits below.

## User Persona

**Target User**: the end user who cancels a fragment (Backspace), immediately re-speaks it, and —
when dissatisfied — cancels + re-speaks again. Today, if the sentinel is lost, EVERY re-said
sentence's final is silently dropped ("missing sections" — the 4×/week incident). After: at most
3 consecutive finals can be lost; the next one lands.
**Use Case / Journey**: arm → speak a bad fragment → Backspace (latch) → sentinel lost (cancel
raced a text() boundary — proven to still leak) → re-speak → final dropped → Backspace again
(re-latch, re-stamp) → re-speak → final dropped → ... today unbounded; after this fix the chain
terminates at the 3rd drop and the user's next sentence types.
**Pain Points Addressed**: silent output death across a self-correcting dictation loop, with no
bound ever firing despite the existing backstops.

## Why

- **The PRD names it a known defect (§8 triage, 2026-11-18)**: "Cancel-suppression window latched
  and dropped finals 4× in the week of 2026-11-12..18 ('missing/repeated sections') — window latch
  timing needs investigation." Part D's closure assessment: NOT closed at HEAD — the incident ran
  builds WITH both 4640041 backstops; the re-latch chain is the only mechanism that reproduces
  "dropped finals 4×" inside one session with no bound firing.
- **The 5 s timeout cannot bound a chain.** It measures from the LATEST press (`refreshed per
  press`, :1790-1791); each cycle's final arrives <5 s after its own press. Only a quantity that
  accumulates ACROSS re-latches — consecutive drops — bounds the loop.
- **Why option (a) over (b):** the window exists to drop the racing REAL final of the cancelled
  utterance (the double-type bug). (b)'s "genuinely-fresh speech" discriminator is unreliable —
  the codebase itself documents stray late partials of the cancelled utterance arriving at
  `_touch_speech` "paired with their partial" (:1486-1489); closing on one would admit the racing
  final. The drop counter increments at the exact drop site, inside `_on_final_lock` ordering —
  deterministic and race-free. The cap force-close carries exactly the residual risk the 5 s
  self-heal already accepts (processing a possibly-late racing final after a WARNING).
- **Cap = 3 rationale**: a healthy window drops at most the racing real final (+ possible duplicate
  finals) before the sentinel closes it; 3 consecutive drops with no sentinel = by construction
  the user's re-said sentences being eaten. The incident's exact count was 4 — with cap 3, the 4th
  never happens.
- **Scope discipline.** T4.S1 owns ONLY the bound mechanics (daemon.py + 3 tests). The sibling
  **T4.S2** replays the full 4× incident sequence as its regression test — building ON this bound;
  do NOT duplicate it. Parallel **T3.S2** owns tests/test_key_listener.py (docstring-only) —
  DISJOINT. No streaming.py (the ENGINE `_suppressed` is a separate mechanism, already lifted per
  partial), no recorder_host.py, no README, no config.

## What

Implement the product decision (a-variant): a consecutive-dropped-finals cap (`3`) counted since
the last healthy close, NOT reset by a re-press re-stamp; force-close + WARNING + process the
final when reached. Keep every existing exit and the boundary-reset invariant untouched.

### Success Criteria

- [ ] `_CANCEL_SUPPRESS_MAX_DROPS: int = 3` constant + `self._cancel_suppress_drops` counter exist.
- [ ] Counter resets at: timeout self-heal close, sentinel-consume close, the cap force-close, fresh `_arm()` — and NOT in `cancel()`'s re-latch.
- [ ] At the drop site: increment (only while the window is still latched after the sentinel-consume attempt), `>= 3` → WARNING + clear flag/stamp/counter + fall through to normal processing; else `return`.
- [ ] The dropped-final boundary reset (:1213-1216 freeze + reset_boundary) runs for EVERY dropped final, including the force-closed one BEFORE it falls through (same shape as the timeout path's absorb).
- [ ] 3 new tests (cap force-close RED→GREEN; re-press chain bound; sentinel-close reset) under a `P1.M1.T4.S1` banner.
- [ ] Full `tests/test_daemon.py` green; `git diff --name-only` == the 2 in-scope files.

## All Needed Context

### Context Completeness Check

_Pass._ The latch state machine is mapped with exact line numbers (constant :164, init :673-674,
latch :1788-1792, drop path :1158-1217 with all three exits, boundary reset :1213-1216, fresh arm
:1371-1374, `_touch_speech` :1460-1499), the unbounded chain mechanism is reproduced from the
baseline Part D, the product decision + its rejection of option (b) are argued, every edit is
given verbatim with a flow subtlety called out (the sentinel-consume path must not increment), and
the test patterns (`_make_cancel_daemon()` @:4454, `host.mark_cancel_sentinel()`, the :4529 test
shape) are quoted. No CUDA/threads/foreground daemon — the doubles run everything synchronously.

### Documentation & References

```yaml
# MUST READ — the latch map + the decision + the verbatim edits + the tests (this task's research)
- docfile: plan/008_a47116bb2b79/P1M1T4S1/research/d33_suppression_chain_bound.md
  why: "§1 is the latch state machine at HEAD (file:line for every element). §2 is the unbounded
        chain mechanism (the incident loop, from baseline Part D item 4). §3 is THE PRODUCT DECISION
        ((a)-variant: counter since last healthy close, NOT reset by re-press re-stamp; why (b) is
        rejected; cap=3 rationale). §4 is the verbatim implementation (5 edits) INCLUDING the
        flow subtlety: guard the increment on the flag still being set so the sentinel-consume path
        never counts. §5 is the 3 TDD tests + the existing pins to keep green + the T4.S2 boundary.
        §6 verify + scope."
  critical: "§4's NOTE is load-bearing: after a successful consume_cancel_mark() the flag is False
            and the same code tail runs — the increment MUST be guarded on `self._cancel_suppress_final`
            still being True, else the sentinel final itself counts toward the next chain. And the
            cap force-close must fall through to clean/commit EXACTLY like the timeout path (the
            boundary was already reset just above it)."

# THE FILE TO EDIT — voice_typing/daemon.py
- file: voice_typing/daemon.py
  why: "All 5 edit sites: constant @164; __init__ counter @673-674 (next to _cancel_suppress_since);
        on_final drop path @1158-1217 (timeout self-heal @1166-1189 — add counter reset where
        flag+stamp clear @1177-1178; sentinel consume @1193-1207 — add counter reset @1194-1197;
        drop site @1213-1217 — the cap check replacing the unconditional `return`); fresh _arm()
        @1371-1374 (add counter reset); cancel() docstring (~@1760) — one Mode-A sentence."
  pattern: "Mirror the timeout self-heal's close sequence for the cap close: logger.warning +
            clear flag + clear stamp + (reset counter) + fall through. The freeze(session=True) +
            reset_boundary() at :1213-1216 ALREADY ran for this final — do not repeat it."
  gotcha: "Do NOT touch _touch_speech/:1460-1499 (option (b) rejected — it stays as-is, lifting
           only the ENGINE suppression). Do NOT reset the counter in cancel() @1788-1792 (that is
           the whole point). Keep the `return` for the non-capped drops."

# THE TEST FILE — tests/test_daemon.py
- file: tests/test_daemon.py
  why: "_make_cancel_daemon() @4454 — an ARMED daemon + _FakeHost + text-in-flight; tests call
        cancel()/on_final() directly, no threads. The _FakeHost seam: host.cancel_calls,
        host.mark_cancel_sentinel(), host.consume_cancel_mark() @625-631 (mirrors
        recorder_host.py:310-319). The reference test test_cancel_suppression_drops_racing_final_
        and_clears_on_sentinel @4529 shows the exact call sequence + asserts (be.typed / fb.finals /
        d._cancel_suppress_final). Existing pins to keep green: @4529, @4564, @5142, @5168, @5184."
  pattern: "New banner 'P1.M1.T4.S1 — suppression-window re-latch chain bound (D3.3)' near the
            cancel section / file end. RED test: sentinel LOST (never mark_cancel_sentinel),
            feed 3 finals — #1,#2 dropped, #3 typed+recorded, flag False, counter 0."
  critical: "Commits type `final + \" \"` (be.typed entries like \"third \") — mirror the :4557-4558
            assert shape. Only 3 tests: the sibling T4.S2 owns the full 4×-incident replay; T4.S1
            pins the bound mechanics. Do not modify any existing test."

# THE SPEC + INCIDENT ANALYSIS
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: "PART D (D3.3 closure assessment, :267-358) — the incident evidence (4× with backstops
        live), the latch map, the pinning gap, and the exact chain sequence. Its 'Assertions to
        decide (product call)' list is what §3 of the research note decides."
  critical: "Part D item 3: 'No fix landed after the triage' — this task IS that fix. Item 4 is
            the chain mechanism the cap bounds."
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "h2.7 §8 Known-defects triage bullet ('window latch timing needs investigation') — the
        mandate. h3.4 §4.2quater accounting invariant: 'every DROPPED final ... MUST reset the
        utterance boundary' — the invariant this task MUST preserve (and does: :1213-1216 runs
        before both the return and the fall-through)."

# THE SIBLING + PARALLEL — boundaries
- docfile: plan/008_a47116bb2b79/P1M1T3S2/PRP.md
  why: "PARALLEL (implementing): owns tests/test_key_listener.py ONLY (docstring-only edit).
        T4.S1 owns daemon.py + test_daemon.py. DISJOINT — no merge conflict."
  critical: "Do NOT edit tests/test_key_listener.py."
# SIBLING T4.S2 (planned, AFTER this): replays the 4× incident sequence as a regression test,
# asserting the chain terminates at the cap. It CONSUMES this bound — leave its scenario (full
# 4-press replay) to it; T4.S1's 3 tests pin the mechanics only.
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py     # :164 _CANCEL_SUPPRESS_TIMEOUT_S; :673-674 latch init; :1158-1217 on_final drop path;     ← EDIT (5 sites)
                           # :1371-1374 fresh-arm clear; :1460-1499 _touch_speech (READ ONLY); :1788-1792 latch.
tests/test_daemon.py       # :4454 _make_cancel_daemon; :4529/:4564 the cancel pins; :5142/:5168/:5184 self-heal pins. ← EDIT (banner + 3 tests)
# Parallel T3.S2: tests/test_key_listener.py — DISJOINT. Sibling T4.S2: the 4× replay (later, builds on this).
```

### Desired Codebase tree with files to be changed

```bash
# (no new files — the 2 edits above only)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TDD: WRITE THE 3 TESTS FIRST. The RED test (cap force-close): against the UNEDITED
# daemon the 3rd final is DROPPED (be.typed == [] — the incident demonstrated at daemon level).
# Run it, confirm RED, then apply §4's edits → green.

# CRITICAL #2 — GUARD THE INCREMENT ON THE FLAG. After a successful consume_cancel_mark() the flag
# is False but the SAME code tail (freeze/reset_boundary/return) runs for the sentinel final — the
# increment must sit inside `if self._cancel_suppress_final:` (still latched) or the sentinel's own
# final counts toward the next chain. (research §4 NOTE.)

# CRITICAL #3 — DO NOT RESET THE COUNTER IN cancel(). The per-press re-latch (:1788-1792) re-stamps
# and MUST leave the counter alone — resetting there re-opens the exact unbounded chain (one drop
# per latch, cap never reached). Resets live ONLY at the healthy closes: timeout self-heal,
# sentinel consume, the cap force-close, fresh _arm(). (research §3 — the decision itself.)

# CRITICAL #4 — KEEP THE BOUNDARY-RESET INVARIANT. Every DROPPED final still freezes(session=True)
# + reset_boundary() (:1213-1216) — including the force-closed final BEFORE it falls through (the
# PRD §4.2quater accounting invariant: "every DROPPED final MUST reset the utterance boundary").
# The cap close mirrors the timeout path: absorb, then process as a fresh utterance.

# CRITICAL #5 — DO NOT IMPLEMENT OPTION (b). _touch_speech stays untouched: partials do NOT close
# the daemon latch (stray late partials of the cancelled utterance are documented at :1486-1489 —
# closing on one admits the racing real final = the double-type bug). The decision + rationale go
# in the code comment at the drop site (the contract requires the decision logged there).

# GOTCHA #6 — CAP=3 IS A CODE CONSTANT, NOT CONFIG. It is a self-protection bound (like
# _CANCEL_SUPPRESS_TIMEOUT_S @:164), not a tunable — do not add a config key (no config.py/
# config.toml/lockstep changes in this task).

# GOTCHA #7 — COMMIT SHAPE IN ASSERTS: streaming commits type `final + " "` (see :4557-4558:
# be.typed == ["fresh sentence", " "] — actually one "fresh sentence " entry per the engine's
# append_space; check the :4529 test's exact shape and mirror it). fb.finals records the final.

# GOTCHA #8 — FULL PATHS + TIMEOUTS (AGENTS.md): .venv/bin/python (zsh aliases shadow python3/pip);
# wrap pytest in `timeout 600` + bash-tool timeout above it. pytest only — no ruff/mypy. NEVER run
# the daemon foreground; _make_cancel_daemon runs everything synchronously (no threads, no CUDA).

# GOTCHA #9 — DO NOT EDIT tests/test_key_listener.py (parallel T3.S2's file), streaming.py,
# recorder_host.py, README, config.*, PRD.md, tasks.json, prd_snapshot.md, .gitignore.
```

## Implementation Blueprint

### Data models and structure

None. One int constant + one counter field + control-flow at the drop site + one docstring sentence.

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST, then the fix)

```yaml
Task 1: ADD the 3 failing tests FIRST (TDD red) — tests/test_daemon.py
  - PLACE: a banner '# P1.M1.T4.S1 — suppression-window re-latch chain bound (D3.3)' right after
    the existing cancel/self-heal pins (near :5184's section / the file's cancel region).
  - ADD (verbatim skeleton — mirror :4529's assert shapes; sentinel LOST = never call
    host.mark_cancel_sentinel()):
        def test_cancel_suppression_drop_cap_force_closes_window_and_processes_final():
            """D3.3: with the sentinel lost, at most _CANCEL_SUPPRESS_MAX_DROPS consecutive finals
            are dropped; the next one force-closes the window (WARNING) and is PROCESSED — the
            silent 'missing sections' chain terminates."""
            d, fb = _make_cancel_daemon(); be = d._backend; host = d._host
            d.cancel()                      # latch; sentinel will be LOST
            d.on_final("first")             # drop 1
            d.on_final("second")            # drop 2
            assert be.typed == [] and fb.finals == []
            d.on_final("third")             # drop 3 == cap -> force-close + process
            assert d._cancel_suppress_final is False and d._cancel_suppress_drops == 0
            assert "third" in "".join(x for x in be.typed if isinstance(x, str))
            assert fb.finals == ["third"]

        def test_cancel_suppression_repress_restamp_does_not_reset_drop_counter():
            """The CHAIN bound (the incident shape, minimal): a re-press re-stamps the window but
            does NOT restore the drop budget — only a healthy close does. press→drop→press→drop→
            third final processed."""
            d, fb = _make_cancel_daemon(); be = d._backend
            d.cancel(); d.on_final("one")           # drop 1
            d.cancel()                              # re-latch + re-stamp (counter SURVIVES)
            d.on_final("two")                       # drop 2
            assert be.typed == []
            d.on_final("three")                     # cap -> processed
            assert d._cancel_suppress_final is False
            assert "three" in "".join(x for x in be.typed if isinstance(x, str))

        def test_cancel_suppression_drop_counter_resets_on_sentinel_close():
            """A healthy sentinel close restores the full drop budget (a subsequent lost-sentinel
            window starts from 0)."""
            d, _fb = _make_cancel_daemon(); host = d._host
            d.cancel(); d.on_final("one"); d.on_final("two")   # drops 1-2, sentinel lost
            assert d._cancel_suppress_drops == 2
            d.cancel(); host.mark_cancel_sentinel(); d.on_final("")  # healthy close
            assert d._cancel_suppress_final is False
            assert d._cancel_suppress_drops == 0
  - RUN (confirm RED — especially tests 1 and 2: the 3rd/"three" final is dropped today):
      cd /home/dustin/projects/voice-typing
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "cancel_suppression and (cap or repress or resets_on_sentinel)" -q
  - EXPECTED: tests 1+2 FAIL (nothing typed — the bug); test 3 FAILS on the counter attribute
    (AttributeError — the field does not exist yet). All three are the TDD baseline.

Task 2: EDIT voice_typing/daemon.py — constant + counter + healthy-close resets
  - ADD near :164 (next to _CANCEL_SUPPRESS_TIMEOUT_S, with the §3 decision comment):
      _CANCEL_SUPPRESS_MAX_DROPS: int = 3
  - ADD in __init__ next to :674 (self._cancel_suppress_since):
      self._cancel_suppress_drops = 0
  - ADD `self._cancel_suppress_drops = 0` at the 3 healthy closes:
      timeout self-heal (:1177-1178, where flag+stamp are cleared),
      sentinel consume (:1194-1197),
      fresh _arm() (:1371-1374).

Task 3: EDIT voice_typing/daemon.py — the cap at the drop site (:1213-1217)
  - CURRENT:
        if self._cfg.output.streaming:
            self._stream.freeze("final dropped (cancel suppression window latched)", session=True)
            self._stream.reset_boundary()
        return  # dropped: no clean, no type_text, no record_final
  - NEW (guard on the flag still being set — Gotcha #2; decision comment required by the contract):
        if self._cfg.output.streaming:
            self._stream.freeze("final dropped (cancel suppression window latched)", session=True)
            self._stream.reset_boundary()
        if self._cancel_suppress_final:
            # D3.3 re-latch chain bound (P1.M1.T4.S1) — PRODUCT DECISION: cap consecutive dropped
            # finals since the last HEALTHY close (sentinel consume / timeout self-heal / this cap /
            # fresh arm). The counter is deliberately NOT reset by a re-press re-stamp: each press
            # refreshing it would re-open the unbounded cancel->re-speak chain (one drop per latch,
            # cap never reached). Closing on a fresh partial was REJECTED: stray late partials of
            # the cancelled utterance are indistinguishable from new speech and a premature close
            # admits the racing real final (the double-type bug). 3 covers the racing final +
            # duplicate finals; the next drop is by construction the user's re-said sentence.
            self._cancel_suppress_drops += 1
            if self._cancel_suppress_drops >= _CANCEL_SUPPRESS_MAX_DROPS:
                logger.warning(
                    "cancel: suppression window dropped %d consecutive finals (sentinel lost + "
                    "re-latch chain) — force-closing and processing this final",
                    self._cancel_suppress_drops,
                )
                self._cancel_suppress_final = False
                self._cancel_suppress_since = None
                self._cancel_suppress_drops = 0
                # fall through: the boundary was just reset above; process this final
            else:
                return  # dropped: no clean, no type_text, no record_final
        else:
            return  # sentinel consumed (healthy close above): the sentinel final itself is dropped
  - NOTE the fall-through lands on `cleaned = textproc.clean(text, self._cfg.filter)` (:1219),
    exactly like the timeout self-heal path. KEEP :1213-1216 untouched (Gotcha #4).

Task 4: EDIT voice_typing/daemon.py — cancel() docstring (Mode A)
  - FIND cancel()'s docstring (~:1760-1775, the block ending before the `if not self._listening`
    gate). APPEND one sentence: "The suppression window is doubly bounded: the 5 s lost-sentinel
    timeout AND a 3-consecutive-dropped-finals cap (D3.3) that a re-press re-stamp does NOT reset
    — see on_final's drop path."

Task 5: VERIFY — TDD green + the cancel suite + the full daemon suite
  - RUN:
      cd /home/dustin/projects/voice-typing
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "cancel" -q
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -3
  - EXPECTED: the 3 new tests GREEN; the whole cancel family green (:4529/:4564/:5142/:5168/:5184
    unchanged — the sentinel path now takes the `else: return` tail, identical behavior); the full
    daemon suite green.

Task 6: VALIDATE — the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T4.S1: suppression-window re-latch chain bounded — cap of 3 consecutive
  dropped finals since the last healthy close (not reset by re-press re-stamps; fresh-partial close
  rejected with rationale in the code comment); 3 daemon-level TDD tests; D3.3 bound in place for
  T4.S2's incident replay."
```

### Implementation Patterns & Key Details

```python
# PATTERN — the cap close mirrors the timeout self-heal exactly (WARNING + clear + fall-through),
# reusing the boundary reset that ALREADY ran for every dropped final (:1213-1216):
if self._cancel_suppress_final:              # still latched (sentinel not consumed)
    self._cancel_suppress_drops += 1
    if self._cancel_suppress_drops >= _CANCEL_SUPPRESS_MAX_DROPS:
        logger.warning(...)                   # the observable incident signal in journald
        self._cancel_suppress_final = False   # healthy-close triple: flag, stamp, counter
        self._cancel_suppress_since = None
        self._cancel_suppress_drops = 0
        # FALL THROUGH -> clean/commit as a fresh utterance (boundary already reset above)
    else:
        return                                # ordinary drop
else:
    return                                    # sentinel-consumed close: sentinel final dropped

# GOTCHA — do NOT move/replicate the freeze+reset_boundary into the cap branch: it runs for EVERY
# dropped final at :1213-1216 BEFORE this block, which is precisely the invariant the PRD requires.
```

### Integration Points

```yaml
DELTA ACCEPTANCE (PRD §8 known-defects triage: "window latch timing needs investigation"):
  - The re-latch chain is bounded; a lost-sentinel + repeated-cancel loop can now drop at most
    _CANCEL_SUPPRESS_MAX_DROPS finals, with a WARNING per force-close (the journald signal the
    incident lacked). The §4.2quater dropped-final boundary invariant is preserved unchanged.

SIBLING — P1.M1.T4.S2 (planned, after this): replays the full 4× incident sequence as a regression
  test, asserting the chain terminates at the cap. It CONSUMES this bound (references
  _CANCEL_SUPPRESS_MAX_DROPS + the WARNING); T4.S1's 3 tests pin the mechanics only — no duplication.

PARALLEL — P1.M1.T3.S2 (implementing): owns tests/test_key_listener.py (docstring-only). DISJOINT.

DOWNSTREAM: P1.M3+ (bulk delivery) — R.5's "duplicated/canceled-utterance events" handling builds
  on this daemon seam; the bound makes the legacy latch safe to inherit.

NO INTERFACE / CONFIG CHANGES: no socket protocol, no status fields, no config keys (the cap is a
  code constant like _CANCEL_SUPPRESS_TIMEOUT_S). Behavior changes ONLY on the chained
  lost-sentinel path (3rd+ consecutive drop now processed with a WARNING).
```

## Validation Loop

> Full paths (zsh aliases shadow python3/pip); inner `timeout` on every pytest invocation
> (AGENTS.md Rule 1) + the bash-tool timeout above it. pytest only (no ruff/mypy). The doubles run
> everything synchronously — no CUDA, no threads, no foreground daemon, no socket.

### Level 1: The bound is in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- constant + counter + the 4 reset sites + the cap ---"
grep -n "_CANCEL_SUPPRESS_MAX_DROPS\|_cancel_suppress_drops" voice_typing/daemon.py
.venv/bin/python -m py_compile voice_typing/daemon.py && echo "L1 PASS: compiles"
# Expected: the constant (:~164), the __init__ counter, resets at the timeout close / sentinel
# close / fresh arm / cap close, the increment at the drop site — and NO reset inside cancel()'s
# latch block (grep the latch region :1788-1792 to confirm).
```

### Level 2: TDD red→green + the cancel family + the full daemon suite

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the 3 new tests (GREEN after Tasks 2-4; RED per Task 1 before) ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -k "cap_force_closes or repress_restamp or resets_on_sentinel_close" -q
echo "--- the whole cancel family (existing pins unchanged) ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -k "cancel" -q 2>&1 | tail -3
echo "--- full daemon suite ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -q 2>&1 | tail -3
# Expected: all green (record the counts). Especially :4529 / :5142 / :5168 / :5184 unchanged-green.
```

### Level 3: The chain empirically terminates (doubles, no CUDA)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "tests")
from test_daemon import _make_cancel_daemon
d, fb = _make_cancel_daemon()
be = d._backend
# The incident loop: press -> drop -> press -> drop -> press -> drop -> 4th final
for i in range(3):
    d.cancel()                    # latch/re-latch, stamp refreshed each press
    d.on_final(f"dropped {i}")    # sentinel lost each time
assert be.typed == [], be.typed   # 3 drops absorbed
d.on_final("the survivors words")
assert any(isinstance(x, str) and "survivors" in x for x in be.typed), be.typed
assert d._cancel_suppress_final is False
print("L3 PASS: the 4x incident chain terminates at the cap; the 4th final types")
PY
# Expected: PASS (this IS the incident shape, minimal — before the fix all 4 finals drop).
```

### Level 4: Scope guards — only the 2 in-scope files changed

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
# Expected: exactly voice_typing/daemon.py + tests/test_daemon.py
git diff --exit-code -- voice_typing/streaming.py voice_typing/recorder_host.py tests/test_key_listener.py config.toml voice_typing/config.py README.md PRD.md plan/008_a47116bb2b79/tasks.json && echo "L4 PASS: parallel/read-only files untouched"
echo "--- the latch block gained NO counter reset (the decision) ---"
sed -n '/_cancel_suppress_final = True/,/host_cancel()/p' voice_typing/daemon.py | grep -n "_cancel_suppress_drops" && echo "L4 FAIL: counter reset inside the latch" || echo "L4 PASS: no reset in the re-latch"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: constant + counter + 4 reset sites + cap check present; daemon.py compiles; no reset inside cancel()'s latch.
- [ ] L2: 3 new tests GREEN (RED first per Task 1); whole cancel family green; full test_daemon.py green.
- [ ] L3: the empirical 4×-incident loop terminates at the cap; the 4th final types; window closed.
- [ ] L4: exactly the 2 in-scope files changed; parallel/read-only files untouched.

### Feature Validation
- [ ] Sentinel-lost chain: at most 3 consecutive finals dropped; the next is processed with a WARNING.
- [ ] Re-press re-stamp does NOT restore the drop budget (the chain bound); healthy closes DO.
- [ ] Every dropped final still resets the utterance boundary (freeze+reset_boundary) — invariant kept.
- [ ] Existing exits (sentinel consume / 5 s timeout / fresh arm) behaviorally unchanged.
- [ ] The product decision + the rejection of option (b) are recorded in the drop-site code comment; cancel()'s docstring notes both bounds (Mode A).

### Code Quality / Scope Validation
- [ ] 3 additive tests only; no existing test modified; T4.S2's full replay not duplicated.
- [ ] The cap is a code constant (not config); mirrors the timeout self-heal's close shape.
- [ ] No streaming.py / recorder_host.py / test_key_listener.py / config / README edits.

### Documentation & Deployment
- [ ] [Mode A] cancel() docstring sentence added; no separate docs task.
- [ ] No config/env/socket changes.

---

## Anti-Patterns to Avoid

- ❌ Don't implement option (b) (close on a fresh partial) — stray late partials are indistinguishable from new speech (:1486-1489); a premature close admits the racing real final. The decision + rationale go in the code comment (Gotcha #5).
- ❌ Don't reset the counter in `cancel()`'s re-latch — that re-opens the exact unbounded chain the task exists to bound (Gotcha #3 / research §3).
- ❌ Don't let the sentinel-consume path increment the counter — guard the increment on `_cancel_suppress_final` still being True (Gotcha #2).
- ❌ Don't skip or duplicate the :1213-1216 boundary reset — it runs for EVERY dropped final, including the force-closed one before it falls through (Gotcha #4; PRD §4.2quater invariant).
- ❌ Don't write the fix before the failing tests — Task 1's RED run proves the tests discriminate (Gotcha #1).
- ❌ Don't add a config key for the cap — it's a self-protection constant like `_CANCEL_SUPPRESS_TIMEOUT_S` (Gotcha #6).
- ❌ Don't write the full 4×-incident replay test — that is the sibling T4.S2's deliverable; T4.S1 pins the mechanics (3 tests) (Gotcha on scope).
- ❌ Don't run pytest without `timeout 600` / with bare `python` (AGENTS.md Rule 1 + zsh aliases — Gotcha #8); never run the daemon foreground.
- ❌ Don't invent ruff/mypy gates (pytest only — Gotcha #8).
- ❌ Don't touch `tests/test_key_listener.py` (parallel T3.S2's file) or any read-only file (Gotcha #9).

---

## Confidence Score

**9/10** for one-pass implementation success. The latch state machine is mapped to exact line numbers (read this round), the unbounded chain mechanism is reproduced from the baseline's Part D analysis, the product decision is fully argued (including the flow subtlety that the sentinel-consume path must not increment — the one place a naive edit goes wrong), every edit is verbatim, and the test patterns mirror the existing :4529 pin + `_make_cancel_daemon` (@4454) exactly. Parallel T3.S2 owns a disjoint file. The −1 residual: the sentinel-path control flow (flag cleared mid-branch, shared tail) is genuinely fiddly — Gotcha #2 + the verbatim Task 3 block guard it, and the existing :4529/:5168 pins go red immediately if the flow is miswired. No CUDA, no threads, no foreground daemon.
