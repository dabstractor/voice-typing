# PRP — P1.M1.T4.S2: Replay the 4× incident sequence as a regression test (D3.3 closure)

## Goal

**Feature Goal**: Pin the **D3.3 incident** (2026-11-12..18, "dropped finals 4×" / "missing
sections") as a **green daemon-level regression test**: replay the exact 7-step chained sequence
from `d3_defects_g1_baseline.md` PART D — arm → partials (tail pending) → Backspace#1 →
sentinel LOST → re-speak → final <5 s **DROPPED** → Backspace#2 re-latch → ... ×4 — and assert
that **the chain TERMINATES** under the P1.M1.T4.S1 bound (the 3rd consecutive dropped final is
force-closed and PROCESSED: typed + recorded) and that **the boundary-reset invariant holds on
every drop** (PRD §4.2quater: "every DROPPED final MUST reset the utterance boundary — the tail
never accumulates across dropped finals"). This test-only task consumes the bound delivered by
the sibling P1.M1.T4.S1; it does not modify it.

**Deliverable** (1 file edited, 1 new test + banner): `tests/test_daemon.py` — a new section
banner `# P1.M1.T4.S2 — D3.3 incident replay: ...` and one comprehensive test
`test_incident_replay_chained_cancel_respeak_terminates_at_drop_cap`, written in the style of
`test_lost_sentinel_self_heals_after_timeout` (tests/test_daemon.py:5142 — mock host, no CUDA,
direct seam calls, everything synchronous). With the incident pinned green, **D3.3 is closed**.

**Success Definition**:
- (a) The test replays the chained press → sentinel-lost → re-speak → dropped-final cycle (the
  incident's exact shape, `_touch_speech()` + partial before each final, sentinel never marked)
  and asserts: finals 1–2 silently dropped (nothing typed/recorded, window still latched),
  **final 3 force-closed at the cap and PROCESSED** (window closed, typed + recorded),
  then a 4th utterance WITHOUT a press processes normally (full recovery — the incident's 4th
  drop is unreachable).
- (b) The boundary-reset invariant is asserted on EVERY drop: a partial grows a non-empty tail
  (`d._stream.pending_tail_len() > 0`), the dropped final resets it (`== 0`).
- (c) The per-press re-stamp (the defect's fuel) is pinned: `_cancel_suppress_since` strictly
  increases per re-press while `_cancel_suppress_drops` SURVIVES (1, 2 — budget NOT restored by
  a re-press) and returns to 0 only at the cap's healthy close.
- (d) `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q` → 0 failures; the whole
  cancel/self-heal family (`:4529`, `:4564`, `:5142`, `:5168`, `:5184`, T4.S1's 3) stays green.
- (e) `git diff --name-only` == `tests/test_daemon.py` — NOTHING else (test-only task; DOCS: none).

## User Persona (if applicable)

**Target User**: the self-correcting dictation user — cancels a bad fragment (Backspace),
immediately re-speaks it, and — when the result is still wrong — cancels and re-speaks again.
**Use Case / Journey**: arm → speak a bad fragment → Backspace (latch) → sentinel lost → re-speak
→ sentence vanishes (final dropped) → Backspace again (re-latch, re-stamp) → re-speak → vanishes
again → ... In the incident week this loop ate 4 sentences in a session. After T4.S1 + this pin:
at most 2 consecutive finals can be silently lost; the 3rd lands typed+recorded and the loop ends.
**Pain Points Addressed**: silent output death in a self-correcting loop with no bound ever
firing (every re-said final landed <5 s after ITS OWN press — "within bound" — so the 5 s
self-heal never tripped), and no regression test that would catch a reintroduction.

## Why

- **PRD §8 known-defects triage (2026-11-18)**: "Cancel-suppression window latched and dropped
  finals 4× in the week of 2026-11-12..18 ('missing/repeated sections') — window latch timing
  needs investigation." Baseline PART D closure assessment: NOT closed at HEAD — the incident ran
  builds WITH both 4640041 backstops (5 s self-heal + dropped-final boundary reset); the per-press
  re-stamp chain is the only mechanism that reproduces "dropped finals 4×" in one session.
- **The pinning gap is the incident shape**: `test_lost_sentinel_self_heals_after_timeout` (:5142)
  covers ONE cancel + a >5 s final. NO test covers finals arriving *within* the bound while the
  user actively re-speaks after a sentinel loss, chained across re-presses. T4.S1 fixed the defect
  and pinned the bound's *mechanics* (3 focused tests); **T4.S2 pins the incident itself** — the
  full 7-step ×4 replay — so any regression of the latch, the bound, or the boundary reset goes
  red immediately.
- **Scope discipline**: T4.S2 owns ONLY the incident replay in `tests/test_daemon.py`. It must not
  re-test T4.S1's mechanics in isolation (no duplicate cap/re-press/sentinel-reset unit tests), not
  touch `voice_typing/daemon.py` (T4.S1's file), not touch `tests/test_key_listener.py` (parallel
  T3.S2's file), and write no docs (the work item says DOCS: none — the banner docstring is the
  closure record).

## What

One new daemon-level test in `tests/test_daemon.py`, placed after the P1.M1.T4.S1 section (or at
file end if the T4.S1 banner is elsewhere), replaying the PART D sequence unrolled across three
chained press-cycles plus one recovery utterance, using the proven `_make_cancel_daemon()` harness
and the `:4529`/`:5142` seam sequence (`cancel()` / `_touch_speech()` / `_on_partial()` /
`on_final()` called directly — no threads, no CUDA, no socket, no foreground daemon).

### Success Criteria

- [ ] New banner + `test_incident_replay_chained_cancel_respeak_terminates_at_drop_cap` exist in
      `tests/test_daemon.py`; no existing test modified.
- [ ] The replay asserts, per chained cycle: latch True + fresh stamp (strictly increasing),
  `host.cancel_calls` increments, sentinel LOST (never marked), partial typed + tail grown,
  final dropped (fb.finals empty, sentence absent from typed, `pending_tail_len() == 0`,
  `_cancel_suppress_drops` == cycle number).
- [ ] The 3rd cycle's final: window force-closed (flag False, stamp None, drops 0) and PROCESSED
      (`fb.finals == ["sentence three"]`, "sentence three" in the typed join).
- [ ] The 4th utterance (no press): processed normally (`fb.finals == ["sentence three",
      "sentence four"]`), window still closed, listening never dropped.
- [ ] Full `tests/test_daemon.py` green under `timeout 600`; diff limited to `tests/test_daemon.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The PRP hands the implementer: the exact 7-step incident sequence (PART D, quoted), the
T4.S1 bound's observable behavior (what to assert, including the counter field name and the
force-close semantics), the proven harness + seam-call ordering (`cancel` → `_touch_speech` →
`_on_partial` → `on_final`) with the two existing tests that PROVE each leg works (:4529's
recovery leg, :5142's style), the streaming engine facts the asserts depend on
(`pending_tail_len`, reset_boundary clearing the tail, resume() lifting the drop-freeze, commit
shape `final` + `" "`), a verbatim test skeleton with per-phase asserts, the dependency gate on
T4.S1, and the AGENTS.md timeout/full-path discipline. No prior codebase knowledge required.

### Documentation & References

```yaml
# MUST READ — this task's research (incident sequence, T4.S1 contract, seam proofs, design calls)
- docfile: plan/008_a47116bb2b79/P1M1T4S2/research/d33_incident_replay_test.md
  why: "§1 the exact 7-step sequence to replay (from PART D). §2 the T4.S1 contract (constant,
        counter, force-close behavior, resets) — what the asserts rely on. §3 the proven test
        seams (:4454 harness, :4529/:5142 pin the exact call ordering and recovery legs). §4 the
        streaming facts behind each assert. §5 the test design decisions (3 cycles + recovery,
        partial-per-cycle, why no exact backspace-count / caplog asserts). §6 scope."
  critical: "§3's proof that `_touch_speech()` lifts the drop's session freeze (:4529 recovery
            leg) is what makes the chained re-speak partials type; without it the replay's
            tail-growth asserts would be vacuous."

# THE SPEC + INCIDENT ANALYSIS
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: "PART D (:267-374): the incident evidence (4× with backstops live), the latch map, and the
        'Exact event-sequence a regression test must replay' block — this PRP's §1 source."
  critical: "Part D step 3: the sentinel is LOST — the test must deliberately NOT call
            host.mark_cancel_sentinel(). Part D step 4: partials stream live again (tail grows)
            while the DAEMON latch stays closed — that duality is what the per-cycle asserts pin."
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "h2.7 §8 known-defects triage bullet (the mandate); h3.4 §4.2quater accounting invariant —
        'every DROPPED final MUST reset the utterance boundary — the tail never accumulates across
        dropped finals' — the invariant asserted on every drop."

# THE DEPENDENCY — T4.S1's PRP (TREAT AS CONTRACT; implemented in parallel, merged before this)
- docfile: plan/008_a47116bb2b79/P1M1T4S1/PRP.md
  why: "Defines everything this test consumes: `_CANCEL_SUPPRESS_MAX_DROPS = 3` (daemon.py ~:165),
        `self._cancel_suppress_drops` (init ~:675), the drop-site cap check (increment guarded on
        the flag still set; >= 3 → WARNING + clear flag/stamp/counter + fall-through to process;
        else return), resets ONLY at healthy closes (NOT in cancel()'s re-latch), and its 3 tests'
        banner text so this PRP's test is placed after them and does not duplicate them."
  critical: "Net behavior to assert: drops 1-2 silent; the 3rd consecutive drop is force-closed
            AND PROCESSED. If T4.S1's edits are absent, STOP (see Task 0) — do NOT implement the
            bound here."

# THE FILE TO EDIT — and the patterns to follow inside it
- file: tests/test_daemon.py
  why: "The only file edited. Patterns: `_make_cancel_daemon()` @:4454 (armed daemon + _FakeHost +
        _text_in_flight; returns (d, fb); d._backend.typed is a list of str and ('bs', n) tuples;
        d._host.cancel_calls / mark_cancel_sentinel()); :4529 the seam-ordering pin (cancel →
        on_final dropped → touch_speech → on_final typed — proves resume() lifts the drop-freeze);
        :5142 the style to mirror (direct flag/stamp asserts, `_touch_speech()` before a recovered
        final, commit shape `be.typed == ['fresh sentence', ' ']`, `fb.finals` records);
        :5100 BUG-004 test (proves `d._on_partial('hello there')` types while armed — substring
        assert style); :4471 (backspace batches appear as ('bs', n))."
  pattern: "Banner comment block naming P1.M1.T4.S2 + D3.3 + the incident, then ONE unrolled test
            with per-phase comments (press #1 / #2 / #3 / recovery). Assert internals directly
            (d._cancel_suppress_final, d._cancel_suppress_since, d._cancel_suppress_drops) exactly
            as :5142/:4529 assert flags. Use substring asserts on be.typed for partial/commit
            text; exact equality on fb.finals."
  gotcha: "Commits type `final` then a separate `' '` entry (append_space) — never assert an exact
           be.typed equality once partials are in play; join + substring, or assert the last two
           entries only. `_on_partial` is gated on `_listening` (stays set — cancel never disarms).
           Do NOT modify any existing test; do NOT re-add T4.S1's mechanics tests."

# ENGINE FACTS behind the asserts (read-only reference)
- file: voice_typing/streaming.py
  why: "`pending_tail_len()` :315 (== len(_tail)); `reset_after_cancel()` :317-331 (cancel clears
        tail + sets _suppressed); `reset_boundary()` :341-382 (absorbs tail keystroke-free,
        _tail='' :378 — the invariant assert); `resume()` :428-458 (_suppressed=False always;
        lifts stranded non-backend session freezes — why re-speak partials type); `on_partial`
        :560-573 (mirror-only while _suppressed); commit types final + ' '."
  gotcha: "READ ONLY — do not edit streaming.py (out of scope)."
- file: voice_typing/daemon.py
  why: "READ ONLY (T4.S1's file). `_touch_speech()` :1460-1499 (per-partial seam: resume() +
        idle clock + _final_pending) and `_on_partial()` :1500+ (listening-gated engine route);
        the drop path ~:1158-1217 post-T4.S1 (freeze(session=True) + reset_boundary() run for
        EVERY dropped final — including the force-closed one — BEFORE the cap fall-through)."
  gotcha: "READ ONLY — the ONLY daemon.py edit allowed is NONE. If the bound is missing, report;
            never write the fix here."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py      # READ ONLY (T4.S1 owns): latch/drop-path/bound. _touch_speech :1460, _on_partial :1500.
voice_typing/streaming.py   # READ ONLY: tail/boundary/resume semantics behind the asserts.
tests/test_daemon.py        # :4454 _make_cancel_daemon; :4529/:4564 cancel pins; :5100 partial-gate;   ← EDIT (banner + 1 test)
                            # :5142/:5168/:5184 self-heal pins; T4.S1's banner + 3 tests (placed near them / file end).
# Parallel T3.S2: tests/test_key_listener.py — DISJOINT. Sibling T4.S1: daemon.py + its 3 tests — consumed, not touched.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py   # + banner '# P1.M1.T4.S2 — D3.3 incident replay ...' + 1 test
                       #   test_incident_replay_chained_cancel_respeak_terminates_at_drop_cap
# (no other file changes; no new source files; no docs)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DEPENDENCY GATE (Task 0): this test consumes T4.S1's bound. Before writing
# anything, `grep -n "_CANCEL_SUPPRESS_MAX_DROPS\|_cancel_suppress_drops" voice_typing/daemon.py`
# MUST find the constant + counter + cap logic (and T4.S1's 3 tests must exist in
# tests/test_daemon.py). If absent, STOP and report the unmet dependency — do NOT implement or
# partially stub the bound in this task.

# CRITICAL #2 — SEAM ORDERING PER CYCLE (proven by :4529/:5142): d.cancel() FIRST (the press),
# then d._touch_speech() (the re-speak's speech event — lifts the engine _suppressed and the
# previous drop's session freeze via stream.resume()), then d._on_partial("...") (types; grows
# the tail), then d.on_final("..."). Calling _on_partial WITHOUT a prior _touch_speech leaves the
# engine suppressed (streaming.py:573 mirror-only) and the partial types nothing.

# CRITICAL #3 — THE SENTINEL IS LOST ON PURPOSE: never call host.mark_cancel_sentinel() anywhere
# in the replay (PART D step 3 — the cancel-raced-text()-boundary leak). Assert the drop happened
# via fb.finals/typed staying quiet while d._cancel_suppress_final is STILL True.

# CRITICAL #4 — ASSERT THE INVARIANT NON-VACUOUSLY: assert d._stream.pending_tail_len() > 0
# AFTER the cycle's partial and BEFORE on_final, then == 0 after the dropped final. Without the
# partial, the tail is always empty and the boundary-reset assert proves nothing.

# CRITICAL #5 — TYPED-TEXT ASSERTS: be.typed accumulates partial words, possible synthesized
# separator entries, and commits as `final` + `' '` pairs. Use substring asserts
# (`"sentence three" in "".join(x for x in be.typed if isinstance(x, str))`) and NEGATIVE
# substrings while dropping; exact equality ONLY on fb.finals. Do NOT assert the exact
# ('bs', n) count — compensation exactness is T3's pinned domain; assert only that a bs batch
# fired at press #1 (`any(isinstance(t, tuple) and t[0] == "bs" for t in be.typed)`).

# GOTCHA #6 — NO CAPLOG ASSERT: logging capture is not pinned in this suite; state + behavior
# asserts (flags, counter, fb.finals, typed) are the contract. The force-close WARNING text is
# T4.S1's concern.

# GOTCHA #7 — CANCEL KEEPS LISTENING: assert d.is_listening() is True after presses (PRD
# §4.2quater — cancel keeps the mic hot); the harness never disarms.

# GOTCHA #8 — TIMEOUTS + FULL PATHS (AGENTS.md): use .venv/bin/python (zsh aliases shadow
# python3), wrap EVERY pytest in `timeout 600` with the bash-tool timeout above it. pytest only
# (no ruff/mypy in this repo's flow). NEVER run the daemon in the foreground — this test runs
# everything synchronously via the doubles (no CUDA, no threads, no socket).

# GOTCHA #9 — DO NOT EDIT: voice_typing/daemon.py, voice_typing/streaming.py,
# voice_typing/recorder_host.py, tests/test_key_listener.py, config.*, README.md, PRD.md,
# plan/** (incl. tasks.json, prd_snapshot.md, the baseline doc), .gitignore. Test-only task.
```

## Implementation Blueprint

### Data models and structure

None — a pure test addition over the existing `_make_cancel_daemon()` harness
(`_FakeHost`, fake backend `.typed`, real `StreamingOutput` as `d._stream`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — verify the T4.S1 dependency is present
  - RUN: grep -n "_CANCEL_SUPPRESS_MAX_DROPS\|_cancel_suppress_drops" voice_typing/daemon.py
         grep -n "P1.M1.T4.S1" tests/test_daemon.py
  - EXPECTED: the constant, the counter (init + resets + cap check) in daemon.py AND the T4.S1
    banner + 3 tests in tests/test_daemon.py. If EITHER is missing → STOP and report
    "dependency P1.M1.T4.S1 not merged" (Gotcha #1). Do not proceed, do not implement the bound.

Task 1: ADD the incident-replay test — tests/test_daemon.py
  - PLACE: a new banner block immediately AFTER the P1.M1.T4.S1 section (search the banner text),
    or at the file end if cleaner. Banner text must name P1.M1.T4.S2, D3.3, and the incident
    (2026-11-12..18 "dropped finals 4×") — it is the closure record (DOCS: none → Mode A).
  - IMPLEMENT (verbatim skeleton — adjust only the sentence strings if desired; every assert is
    load-bearing and mirrors a proven pin):

        # ===========================================================================
        # P1.M1.T4.S2 — D3.3 incident replay (the 2026-11-12..18 "dropped finals 4×"
        # session): every Backspace re-latches AND re-stamps the cancel-suppression
        # window (daemon.py cancel(): "refreshed per press"), so each re-said
        # sentence's final lands <5 s after ITS OWN press — inside the timeout bound —
        # and was dropped, chaining the window open indefinitely (4 missing sections
        # in one session, with both 4640041 backstops live). P1.M1.T4.S1 bounds the
        # chain: at most _CANCEL_SUPPRESS_MAX_DROPS (3) consecutive dropped finals
        # since the last healthy close; a re-press re-stamp does NOT restore the
        # budget. This replay pins the incident GREEN: the chain TERMINATES (the 3rd
        # re-said final is force-closed and typed + recorded) and the boundary-reset
        # invariant (every dropped final resets the utterance boundary — PRD
        # §4.2quater) holds on every drop. Style: test_lost_sentinel_self_heals_
        # after_timeout (:5142) — mock host, no CUDA, sentinel deliberately LOST.
        # ===========================================================================
        def test_incident_replay_chained_cancel_respeak_terminates_at_drop_cap():
            """D3.3 regression: arm → partial (tail pending) → Backspace → sentinel LOST →
            re-speak → final <5 s DROPPED → Backspace re-latch → ... — the exact PART D
            7-step sequence. Asserts: (1) finals 1-2 silently dropped with the window
            still latched and the boundary reset on each drop; (2) the 3rd consecutive
            dropped final hits the T4.S1 cap — window force-closed, final typed +
            recorded; (3) the per-press re-stamp fires (stamp strictly increases) while
            the drop budget does NOT reset; (4) full recovery on the next utterance
            (the incident's 4th drop is unreachable).
            """
            d, fb = _make_cancel_daemon()
            be = d._backend
            host = d._host

            # Step 1 — armed, text() in flight (harness sets _text_in_flight), tail pending.
            d._touch_speech()
            d._on_partial("bad fragment")
            assert "bad fragment" in "".join(x for x in be.typed if isinstance(x, str))

            # --- press #1: latch + stamp S1; the physical keystroke compensates the tail ---
            d.cancel()
            assert d.is_listening() is True          # cancel never disarms
            assert d._cancel_suppress_final is True
            stamp1 = d._cancel_suppress_since
            assert stamp1 is not None
            assert host.cancel_calls == 1
            assert any(isinstance(t, tuple) and t[0] == "bs" for t in be.typed)
            # sentinel LOST (PART D step 3): mark_cancel_sentinel() deliberately NEVER called.
            # Re-speak: speech event lifts engine suppression + the drop-freeze; partial types.
            d._touch_speech()
            d._on_partial("re-said one")
            assert d._stream.pending_tail_len() > 0   # tail grew — the invariant has teeth
            d.on_final("sentence one")                # <5 s after S1 -> DROP 1
            assert d._cancel_suppress_final is True   # still latched, within bound
            assert d._cancel_suppress_drops == 1
            assert fb.finals == [] and "sentence one" not in "".join(
                x for x in be.typed if isinstance(x, str)
            )
            assert d._stream.pending_tail_len() == 0  # boundary reset on EVERY drop

            # --- press #2: re-latch + RE-STAMP (the defect's fuel); budget NOT restored ---
            d.cancel()
            stamp2 = d._cancel_suppress_since
            assert stamp2 is not None and stamp2 > stamp1      # per-press re-stamp pinned
            assert d._cancel_suppress_drops == 1               # budget SURVIVES the re-press
            assert host.cancel_calls == 2
            d._touch_speech()
            d._on_partial("re-said two")
            assert d._stream.pending_tail_len() > 0
            d.on_final("sentence two")                # <5 s after S2 -> DROP 2
            assert d._cancel_suppress_final is True
            assert d._cancel_suppress_drops == 2
            assert fb.finals == [] and "sentence two" not in "".join(
                x for x in be.typed if isinstance(x, str)
            )
            assert d._stream.pending_tail_len() == 0

            # --- press #3: the chain TERMINATES at the cap — final 3 processed ---
            d.cancel()
            stamp3 = d._cancel_suppress_since
            assert stamp3 is not None and stamp3 > stamp2
            assert d._cancel_suppress_drops == 2
            assert host.cancel_calls == 3
            d._touch_speech()
            d._on_partial("re-said three")
            assert d._stream.pending_tail_len() > 0
            d.on_final("sentence three")              # 3rd consecutive drop == cap
            assert d._cancel_suppress_final is False  # force-closed
            assert d._cancel_suppress_since is None
            assert d._cancel_suppress_drops == 0      # healthy close restores the budget
            assert fb.finals == ["sentence three"]
            assert "sentence three" in "".join(x for x in be.typed if isinstance(x, str))
            assert d._stream.pending_tail_len() == 0

            # --- recovery: the would-be 4th incident utterance, NO press -> normal ---
            d._touch_speech()
            d._on_partial("kept speaking")
            d.on_final("sentence four")
            assert d._cancel_suppress_final is False and d._cancel_suppress_drops == 0
            assert fb.finals == ["sentence three", "sentence four"]
            assert "sentence four" in "".join(x for x in be.typed if isinstance(x, str))
            assert d.is_listening() is True

  - NOTE: if the exact drop-count semantics differ from the contract (e.g. T4.S1 shipped the cap
    so that finals 1-3 drop and the 4th lands), READ T4.S1's landed tests FIRST and align the
    phase boundaries to the LANDED behavior — the PRP contract is "at most 2 silent drops, 3rd
    processed" per the T4.S1 PRP; do not weaken the termination/invariant asserts to pass.

Task 2: VERIFY — the new test + the cancel family + the full daemon suite
  - RUN:
      cd /home/dustin/projects/voice-typing
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "incident_replay" -q
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "cancel" -q 2>&1 | tail -3
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -3
  - EXPECTED: the new test GREEN; the whole cancel family green (:4529/:4564/:5142/:5168/:5184 +
    T4.S1's 3 unchanged); the full daemon suite green (record the counts for the closure record).

Task 3: VALIDATE — the Validation Loop L1-L3 below. No git commit unless the orchestrator
  directs it. If asked, message: "P1.M1.T4.S2: D3.3 closed — the 4× cancel→re-speak chained-drop
  incident replayed as tests/test_daemon.py::test_incident_replay_chained_cancel_respeak_
  terminates_at_drop_cap (green): chain terminates at the 3-drop cap, boundary-reset invariant
  asserted on every drop, per-press re-stamp pinned, full recovery after the chain ends."
```

### Implementation Patterns & Key Details

```python
# PATTERN — the incident cycle (each leg proven by an existing green test):
d.cancel()               # the press: latch + FRESH stamp (per-press refresh) + host.cancel().
                         #   [:4471/:4486 pins: compensation + host abort]
# sentinel LOST: never host.mark_cancel_sentinel()                     [PART D step 3]
d._touch_speech()        # re-speak's speech event: stream.resume() — clears engine _suppressed
                         #   and lifts the previous drop's session freeze  [:4529 recovery leg]
d._on_partial("...")     # partials stream live again; tail grows       [:5100 BUG-004 pin]
d.on_final("...")        # final <5 s after its own press:
                         #   drops 1-2 -> freeze(session=True)+reset_boundary()+return
                         #   (nothing typed/recorded; pending_tail_len()==0 after)
                         #   drop 3  -> T4.S1 cap: WARNING + force-close + PROCESSED

# GOTCHA — stamp ordering: time.monotonic() may not advance between fast successive calls on
# every platform, but here each cycle's cancel() follows partial-typing work; if a strict
# `stamp2 > stamp1` ever flakes, weaken ONLY to `stamp2 >= stamp1` plus
# `d._cancel_suppress_drops` surviving (the budget non-reset is the real contract; the re-stamp
# is the mechanism, already asserted structurally by the drop that follows).

# GOTCHA — assert fb.finals with EXACT equality (the recorded sequence IS the incident outcome);
# assert be.typed with substring membership (partial/commit/separator entry shapes vary).
```

### Integration Points

```yaml
D3.3 CLOSURE (this task IS the closure evidence):
  - The incident sequence is pinned green at the T4.S1-bounded HEAD; any regression of the latch,
    the re-stamp chain, the drop cap, or the dropped-final boundary reset turns this test red.
  - No docs edits (work item: DOCS none) — the banner docstring is the record (Mode A).

DEPENDS ON — P1.M1.T4.S1 (merged first): daemon.py bound (_CANCEL_SUPPRESS_MAX_DROPS=3,
  _cancel_suppress_drops, force-close semantics) + its 3 tests. Consumed, never edited.

DISJOINT FROM — P1.M1.T3.S2 (tests/test_key_listener.py, parallel) and all P1.M2+ work.

NO INTERFACE / CONFIG / DOC CHANGES: no socket protocol, no status fields, no config keys,
  no README/ACCEPTANCE.md/plan-file edits.
```

## Validation Loop

> Full paths (zsh aliases shadow python3); inner `timeout` on every pytest invocation (AGENTS.md
> Rule 1) + the bash-tool `timeout` parameter above it. The doubles run everything synchronously —
> no CUDA, no threads, no foreground daemon, no socket.

### Level 1: The dependency + the artifact (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- T4.S1 bound present (Task 0 gate) ---"
grep -n "_CANCEL_SUPPRESS_MAX_DROPS\|_cancel_suppress_drops" voice_typing/daemon.py
echo "--- the new test exists, sentinel never marked inside it ---"
grep -n "P1.M1.T4.S2\|def test_incident_replay_chained_cancel_respeak_terminates_at_drop_cap" tests/test_daemon.py
sed -n "/def test_incident_replay_chained/,/^def /p" tests/test_daemon.py | grep -c "mark_cancel_sentinel" || true
# Expected: bound found in daemon.py; banner + test found; mark_cancel_sentinel count == 0
# (the docstring may mention it in prose — the grep should show at most docstring mentions;
# zero CALLS. Verify by eye: no `host.mark_cancel_sentinel()` invocation).
.venv/bin/python -m py_compile tests/test_daemon.py && echo "L1 PASS"
```

### Level 2: The new test + the family + the full suite

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the incident replay ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -k "incident_replay" -q
echo "--- the cancel family (existing pins unchanged) ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -k "cancel" -q 2>&1 | tail -3
echo "--- full daemon suite ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -q 2>&1 | tail -3
# Expected: ALL GREEN (record the counts — they are D3.3's closure evidence).
# If the new test fails: read which phase — a drop assert failing means the T4.S1 cap semantics
# differ from the contract (read T4.S1's landed tests and align per Task 1's NOTE); a
# pending_tail_len assert failing means the boundary invariant regressed (a REAL D3.3-class bug).
```

### Level 3: Scope guard — exactly one file changed

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
# Expected: exactly tests/test_daemon.py
git diff --exit-code -- voice_typing/daemon.py voice_typing/streaming.py voice_typing/recorder_host.py tests/test_key_listener.py config.toml voice_typing/config.py README.md PRD.md plan/008_a47116bb2b79/tasks.json && echo "L3 PASS: no out-of-scope edits"
git diff -- tests/test_daemon.py | grep -c "^-.*def test_" || echo "0 tests removed/modified"
# Expected: no existing test touched (additive diff only).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: T4.S1 bound present (Task 0 gate passed); banner + test present; no `mark_cancel_sentinel()` call in the replay; file compiles.
- [ ] L2: new test GREEN; cancel family GREEN; full `tests/test_daemon.py` GREEN (counts recorded).
- [ ] L3: `git diff --name-only` == `tests/test_daemon.py`; no existing test modified.

### Feature Validation
- [ ] The replay covers all 7 PART D steps ×3 chained cycles + a no-press recovery utterance.
- [ ] Finals 1-2 dropped silently (fb.finals empty, sentences absent from typed, window latched).
- [ ] Final 3 force-closed at the cap and PROCESSED (typed + recorded; flag False, stamp None, drops 0).
- [ ] Boundary-reset invariant asserted on every drop (`pending_tail_len() > 0` before, `== 0` after).
- [ ] Per-press re-stamp pinned (stamp strictly increases) while the drop budget survives (1, 2 → 0 only at the healthy close).
- [ ] `host.cancel_calls` reaches 3; `is_listening()` True throughout (cancel never disarms).
- [ ] Recovery utterance processed normally — the incident's 4th drop shown unreachable.

### Code Quality / Scope Validation
- [ ] Mirrors the :5142 style (mock host, no CUDA, direct seam calls, synchronous).
- [ ] One comprehensive test; no duplication of T4.S1's 3 mechanics tests; no docs/config/source edits.

### Documentation & Deployment
- [ ] Banner docstring names P1.M1.T4.S2 + D3.3 + the incident (the closure record — Mode A; no separate docs).
- [ ] No config/env/socket/README changes.

---

## Anti-Patterns to Avoid

- ❌ Don't mark the sentinel — the incident IS the lost-sentinel path; `host.mark_cancel_sentinel()` anywhere in the replay voids the test (Gotcha #3).
- ❌ Don't implement or "help" the bound in daemon.py — test-only task; missing dependency = STOP and report (Gotcha #1).
- ❌ Don't assert exact `be.typed` equality or exact `("bs", n)` counts — partial/separator/commit entry shapes vary; substring asserts + exact `fb.finals` (Gotcha #5).
- ❌ Don't skip the pre-final `pending_tail_len() > 0` assert — without it the boundary invariant assert is vacuous (Gotcha #4).
- ❌ Don't call `_on_partial` before `_touch_speech` in a cycle — the engine stays suppressed post-cancel and the partial types nothing (Gotcha #2).
- ❌ Don't add caplog/log-text asserts (Gotcha #6), a 4th mechanical press (fresh-budget confusion — the recovery utterance is the design; see research §5), or T4.S1's mechanics tests over again.
- ❌ Don't run pytest without `timeout 600` / with bare `python`; never run the daemon foreground (Gotcha #8; AGENTS.md Rules 1-2).
- ❌ Don't edit `tests/test_key_listener.py`, streaming.py, recorder_host.py, README, config, or any plan/ file (Gotcha #9).

---

## Confidence Score

**9/10** for one-pass implementation success. The incident sequence is quoted verbatim from the
baseline's own "exact event-sequence a regression test must replay" block; every seam-call leg of
the replay is individually proven by an existing green test (:4471/:4486 press behavior, :4529 the
drop→touch→recovery chain, :5100 partial typing, :5142 the style + commit shape); the T4.S1
contract (constant, counter, force-close semantics, healthy-close resets) is pinned in the sibling
PRP with a preflight gate if it is absent; and the engine facts behind each assert
(`pending_tail_len`, reset_boundary clearing the tail, resume() lifting the drop-freeze) were read
from streaming.py this round. The −1 residual: T4.S1 is landing in parallel, so its exact landed
drop-count semantics could differ a hair from the contract (Task 1's NOTE covers the alignment
path — read the landed tests, never weaken the termination/invariant asserts). No CUDA, no
threads, no foreground daemon; one file, one test.
