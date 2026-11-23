# PRP — P1.M1.T3.S2: Mitigate or record the residual desync window (D3.2 closure)

## Goal

**Feature Goal**: Close **D3.2** by consuming the S1 (P1.M1.T3.S1) audit finding and executing the
item's decision gate: *if the desync hold-window is unbounded → apply the smallest PRD-sanctioned
mitigation; if bounded and correct-by-design → record the evidence and STOP (no gold-plating).*
This PRP ships the analysis **pre-executed with verified numbers**: the window is **BOUNDED** —
`R ≤ repeat_rate × (n × per_char_pace + spawn_gap)` with every factor verified finite — so the
executed branch is **RECORD**: (1) correct the stale bound arithmetic in S1's hold-trace test
docstring (it says "~12 ms/char" yet "≤150 ms for ~80 chars → R ≤ 4–5" — internally inconsistent;
the true figures are 12–18 ms/char → R ≈ 4–22 typical / 30–45 pathological) and append the S2
closure decision to it; (2) the evidence record already written at
`plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md` IS the deliverable artifact —
the implementer verifies its claims still hold at implementation time (3 greps) and does not
rewrite it. The conditional mitigation branch is specified in the Blueprint but is NOT to be
executed unless a verification grep FAILS.

**Deliverable** (1 tracked file edited, docstring-only; zero source, zero new tests, zero README):
1. `tests/test_key_listener.py` — inside `test_sustained_backspace_hold_fires_one_cancel_and_
   never_restamps`'s AUDIT NOTE docstring (the S1-landed test): replace the stale bound sentences
   with the corrected parametric bound + append the **S2 CLOSURE** paragraph (decision: bounded,
   accepted, no mitigation; D3.2 closed). **Zero assertion changes.**

**Success Definition**:
- (a) The three bound inputs verify green at implementation time (L1 greps: filter :81 intact;
  pace argv pins at test_typing_backends.py:310/:318/:413 intact; streaming clamp :870-871 +
  VAD cadence intact). If ANY fails → STOP and execute the Conditional Fallback (Blueprint Task 3)
  instead — do not silently proceed.
- (b) The docstring carries the corrected bound (`R ≤ 30 cps × (n × 0.012–0.018 s + 0.025 s)`
  → R ≈ 4–22 typical, 30–45 pathological at n=80) + the closure sentence.
- (c) `timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q` → **0 failures**
  (S1's pin still green — assertions untouched).
- (d) `git diff --name-only` == `tests/test_key_listener.py` (the research note under `plan/` is
  an untracked add, allowed).

## User Persona

**Target User**: the maintainer reasoning about whether Backspace-cancel compensation is safe
under a held key, and the orchestrator closing D3.2. **Use Case**: someone later reads the
hold-trace test to check the residual-window verdict — they must find *correct* arithmetic and an
explicit accepted-bounded decision, not a stale 4–5-char figure a reviewer could disprove in one
line. **Pain Points**: the audit note as-written contradicts itself (12 ms/char vs ≤150 ms/80
chars); an uncorrected record would either breed a needless mitigation (gold-plating, breaking
S1's deliberate pin) or a false "safe" claim.

## Why

- **The item is a decision gate, and the evidence is now complete.** S1 (parallel, its PRP is the
  contract) pins the one-cancel contract and designates its test docstring as the written audit
  finding S2 consumes: "Mitigation vs acceptance is S2's decision". S2's job is to decide with
  real numbers and record it — not to add code.
- **The numbers decide: bounded.** per_char_pace is a fixed, test-pinned constant (12 ms/char
  wtype `-d 12`, typing_backends.py:109-116; 12 ms/char ydotool CLI `-d 6`×2, :134-152; 18 ms/char
  ydotoold socket, :140; `_MIN_SPAWN_GAP_S=0.025` once, :65 — pinned at
  test_typing_backends.py:310/:318/:321/:413/:427). `n` is bounded by VAD commit segmentation
  (`post_speech_silence_duration` 0.6/0.8 s → tails are per-pause fragments, config.toml:37-38)
  plus the accounting clamp (streaming.py:870-871 "NEVER delete more characters than THIS engine
  typed… clamped to len(tail)"). repeat_rate ≈ 30 cps (OS typematic default — the same documented
  assumption Part C uses). No unbounded input exists → RECORD branch, per the item's own LOGIC.
- **The stale figure must be corrected, not merely supplemented.** Part C / S1's docstring say
  "~12 ms/char" AND "≤150 ms for ~80 chars → R ≤ ~4–5 chars worst case". At the pinned pace an
  80-char burst runs 1.0–1.4 s → R ≈ 30–45. The corrected record is *worse-looking but true* —
  and still bounded and still accepted (post-burst repeats are by-design plain user edits; the
  user was actively Backspacing through that text anyway). A record that understates the window
  by 10× is the real defect here.
- **Mitigation is affirmatively wrong, not just unnecessary.** Observing value==2 events to
  compensate holds would re-fire cancels per repeat — exactly the regression S1's pin exists to
  catch ("so any change… is a deliberate, visible red"). The item's example mitigation ("bound
  the burst so a hold past the burst is provably a user edit") is *already structurally present*:
  the burst is finite (n clamped to the engine's own tail × fixed pace), and once it completes
  the accounting is zeroed so any further deletion is provably a user edit.
- **Scope discipline / no gold-plating.** 1-point task; DOCS: none (no README); the bound's
  inputs are already regression-pinned, so no new test is needed. Editing only the docstring of
  the already-landed S1 test keeps a single source of truth for the audit note.

## What

A docstring-only correction + closure paragraph in `tests/test_key_listener.py`, plus verification
gates. No behavior change anywhere.

### Success Criteria

- [ ] L1 verification greps pass (filter, pace pins, clamp/cadence) — else Conditional Fallback.
- [ ] S1's test docstring: stale "≤150 ms for ~80 chars … R ≤ ~4-5 chars" bound replaced by the
      parametric formula with 12–18 ms/char and the R ≈ 4–22 / 30–45 figures.
- [ ] The same docstring gains a short **S2 CLOSURE (P1.M1.T3.S2)** paragraph: bounded; accepted;
      no mitigation; post-burst repeats are by-design user edits; D3.2 closed (test + recorded
      evidence).
- [ ] Zero assertion/body changes to the test; `tests/test_key_listener.py` suite green (0 fail).
- [ ] `git diff --name-only` == `tests/test_key_listener.py`.
- [ ] The evidence record at `plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md`
      exists (pre-written by research; verify presence — do not rewrite).

## All Needed Context

### Context Completeness Check

_Pass._ The decision is pre-made with every number file:line-verified (research note §3-§4); the
sole code edit is a docstring replacement given verbatim below against the S1-PRP-contract text
(with an explicit drift-handling instruction); the conditional fallback is fully specified but
gated off. A developer who has never seen this repo executes gates, one docstring edit, and test
runs — nothing else.

### Documentation & References

```yaml
# MUST READ — the executed decision + all verified numbers + the conditional fallback
- docfile: plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md
  why: "§3 the three bound inputs with file:line cites (pace argv, VAD cadence, streaming clamp,
        repeat-rate assumption). §4 the corrected arithmetic (R formula; 4-22 typical / 30-45 at
        n=80) that the docstring edit records. §5 the decision against the item's LOGIC. §6 the
        conditional fallback procedure (only if an L1 grep fails). §7 what closure consists of."
  critical: "This note IS the deliverable artifact — the implementer VERIFIES it (L1 greps), never
            rewrites it."

# THE CONTRACT (S1, parallel-implementing) — owns the test being edited + the audit-note text
- docfile: plan/008_a47116bb2b79/P1M1T3S1/PRP.md
  why: "Specifies verbatim the test + its AUDIT NOTE docstring this task edits. Its Integration
        Points: 'S2 consumes the audit note in this test's docstring… If S2 lands a mitigation
        that changes the one-cancel contract, THIS test is the deliberate red.' A docstring-only
        edit changes no assertion → the pin stays green by construction."
  critical: "PREREQUISITE: S1's test must have LANDED before this edit (L0 gate). Its docstring
            per the contract contains the stale sentences quoted in Task 2; if the landed text
            differs slightly, match the ACTUAL text (grep 'AUDIT NOTE') and preserve S1's
            non-bound sentences verbatim."

# THE AUDIT INPUT (Part C) + baseline reds context
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: "PART C is the D3.2 audit: filter :81, the hold walkthrough (press → one cancel → paced
        burst; repeats invisible but OS deletes real chars; release inert), the n+1+R arithmetic,
        and the origin of the stale ≤150ms/4-5-char figure this task corrects. PART A: the
        pre-existing red classes (test_daemon.py legacy-separator) — NOT touched by this task."
  critical: "Part C's '~12 ms/char' and '≤150 ms for ~80 chars' cannot both be true; the pinned
            argv constants (not Part C's prose) are authoritative."

# THE TEST FILE (the only file edited)
- file: tests/test_key_listener.py
  why: "S1's banner section 'D3.2 hold trace (P1.M1.T3.S1)' at END of file holds
        test_sustained_backspace_hold_fires_one_cancel_and_never_restamps; its docstring's AUDIT
        NOTE paragraph is the edit target. Harness around it (_wire_daemon :379, tuples :190-193,
        _pump_events) is untouched."
  pattern: "Docstring-only edit inside the existing test function. Do not touch any `def` body,
            any assertion, or any other test/section."
  gotcha: "If grep 'def test_sustained_backspace_hold' finds nothing → S1 has not landed; STOP and
           report (prerequisite), do not author S1's test yourself."

# THE BOUND-INPUT SITES (read-only verification targets)
- file: voice_typing/typing_backends.py
  why: ":109-116 wtype press_backspace ('-d','12' + ['-k','Backspace']*n); :134-152 ydotool CLI
        ('-d','6' + ['14:1','14:0']*n) and socket client (18 ms/char comment, :140); :65
        _MIN_SPAWN_GAP_S=0.025. L1 verifies the argv pins in tests/test_typing_backends.py
        :310/:318/:313-321/:413 — these make the recorded bound regression-proof."
- file: voice_typing/key_listener.py
  why: ":81 `if ev_type != ecodes.EV_KEY or value != 1: return None` — the one-cancel filter S2's
        acceptance rests on (repeats invisible ⇒ no re-fire ⇒ desync is exactly the during-burst
        R)."
- file: voice_typing/streaming.py
  why: ":870-871 the clamp invariant ('NEVER delete more characters than THIS engine typed since
        the checkpoint — clamped to len(tail)') bounding n; :31/:280/:312 accounting on the REAL
        tail."
- file: voice_typing/daemon.py
  why: ":1756-1795 cancel() — compensation n=max(tail_len-1,0) at :1779, idempotence guard, window
        latch. READ-ONLY: unchanged by this task."
- file: config.toml
  why: ":37-38 post_speech_silence_duration 0.6 / lite 0.8 — the VAD commit cadence that keeps
        tails to per-pause fragments (bounds n)."

# SIBLING (parallel) — disjoint
- docfile: plan/008_a47116bb2b79/P1M1T2S3/PRP.md
  why: "T2.S3 (Complete, landed at 2cb3b29) owns tests/test_typing_backends.py content including
        the press_backspace argv pins — S2 only GREPs that file; no edit, no conflict."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/key_listener.py        # :81 filter — L1 verify (read-only).
voice_typing/typing_backends.py     # :109-152 press_backspace paces — L1 verify (read-only).
voice_typing/streaming.py           # :870-871 clamp — L1 verify (read-only).
voice_typing/daemon.py              # :1756-1795 cancel() — read-only.
tests/test_key_listener.py          # S1's D3.2 hold-trace section at END —                    ← EDIT (docstring only)
tests/test_typing_backends.py       # :310/:318/:321/:413/:427 pace pins — L1 verify (grep only; T2.S3 owns).
plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md   # the evidence record — verify present (pre-written).
```

### Desired Codebase tree with files to be changed

```bash
tests/test_key_listener.py   # EDIT: inside test_sustained_backspace_hold_fires_one_cancel_and_
#                           never_restamps docstring — correct the bound sentences + append the
#                           S2 CLOSURE paragraph. NOTHING else.
# No source changes. No README. No new tests. No edits to test_typing_backends.py / test_daemon.py.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS THE RECORD BRANCH, NOT THE MITIGATION BRANCH. The evidence says bounded
# (research §3-§5). Do NOT observe value==2 events, do NOT change pacing, do NOT clamp cancel().
# The Conditional Fallback (Task 3) executes ONLY if an L1 grep fails — and its first step is to
# STOP and reassess, not to edit code reflexively.

# CRITICAL #2 — DOCSTRING-ONLY. Zero assertion changes; S1's pin must stay green untouched. If
# you find yourself editing anything other than the AUDIT NOTE sentences + the appended closure
# paragraph, stop — you have left scope.

# CRITICAL #3 — S1 IS A PARALLEL LANDING. Its test may not be on disk yet when you start. L0 gate:
# grep 'def test_sustained_backspace_hold_fires_one_cancel_and_never_restamps' — if absent, S1
# hasn't landed; STOP and report the prerequisite. Never author S1's test yourself.

# CRITICAL #4 — THE LANDED DOCSTRING IS AUTHORITATIVE OVER THE PRP QUOTE. Task 2's oldText quotes
# the S1-PRP contract; if the landed text drifted (reworded, reflowed), match the ACTUAL text
# (grep 'AUDIT NOTE' / '4-5' / '150 ms') and preserve every non-bound sentence verbatim — only
# the bound arithmetic sentences are replaced.

# GOTCHA #5 — test_key_listener.py HAS 0 REDS at baseline (Part A row 6: 32/0). The gate is plain
# green, no before/after comparison needed. Do NOT touch test_daemon.py (21 legacy-separator reds
# there are the G1 reconciliation's problem, not this task's).

# GOTCHA #6 — FULL PATHS + timeout. timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q.
# pytest only (no ruff/mypy configured). Never bare python/pytest/uv.

# GOTCHA #7 — KEEP THE NUMBERS EXACTLY AS VERIFIED. 12 ms/char (wtype '-d 12'; ydotool CLI '-d 6'
# × 2 events), 18 ms/char (ydotoold socket: contact 6 + inter 12), spawn floor 25 ms once, repeat
# rate ~30 cps (documented OS-typical assumption, same as Part C), R ≈ 4–22 typical (n=10–40),
# 30–45 pathological (n=80). Rounding or "improving" them re-creates the stale-figure defect.
```

## Implementation Blueprint

### Data models and structure

None — a documentation-record edit inside one test docstring. No types, no config, no schema.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREREQUISITE GATE — S1 has landed
  - RUN: grep -n 'def test_sustained_backspace_hold_fires_one_cancel_and_never_restamps' \
      tests/test_key_listener.py
  - EXPECT: exactly one hit. If ZERO hits: S1 (parallel) has not landed — STOP and report the
    prerequisite unmet; do not proceed, do not author the test yourself.

Task 1: VERIFY THE BOUND INPUTS (the decision gate — all must pass before Task 2)
  - RUN (each must match):
      grep -n 'value != 1' voice_typing/key_listener.py                       # the :81 filter intact
      grep -n '"-d", "12"' voice_typing/typing_backends.py                    # wtype pace
      grep -n '"-d", "6"' voice_typing/typing_backends.py                     # ydotool CLI pace
      grep -n '18 ms/char' voice_typing/typing_backends.py                    # socket pace comment
      grep -n 'clamped to len(tail)\|clamped' voice_typing/streaming.py       # :870-871 clamp
      grep -n 'post_speech_silence_duration' config.toml                      # VAD cadence
      grep -n 'def test_wtype_press_backspace_exact_argv\|def test_ydotool_press_backspace_exact_argv' \
        tests/test_typing_backends.py                                        # pace pins (T2.S3-landed)
      test -s plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md && echo present
  - IF ALL MATCH → the RECORD branch holds; proceed to Task 2. (These greps re-validate research
    note §3 against the live tree.)
  - IF ANY FAIL → the bound has an unbounded input or the tree drifted: execute Task 3
    (Conditional Fallback) INSTEAD of Task 2. Do not blend branches.

Task 2: EDIT tests/test_key_listener.py — correct the bound + record the closure (THE deliverable)
  - FIND the AUDIT NOTE paragraph in test_sustained_backspace_hold_fires_one_cancel_and_
    never_restamps's docstring. Per the S1-PRP contract it contains:
        ... Repeats landing while the daemon's paced
        press_backspace(n) burst runs (~12 ms/char on the D3.1 socket path; ≤150 ms for ~80 chars)
        interleave with it: total deleted = n+1+R vs n+1 believed → belief-desync of R chars.
        BOUND: R ≈ repeat_rate × burst_duration — at a typical ~30 cps autorepeat, R ≤ ~4-5 chars
        worst case during the burst; repeats after the burst delete committed/user text with the
        accounting already zeroed (plain user edits — uncompensable by design). Mitigation vs
        acceptance is S2's decision; this test pins the CURRENT contract so any change (e.g.
        observing value==2 to compensate holds) is a deliberate, visible red.
  - EDIT (oldText → newText) — replaces ONLY the two stale bound sentences, keeps the rest, and
    appends the closure paragraph before the final closing quotes of the docstring:
      OLD:
        press_backspace(n) burst runs (~12 ms/char on the D3.1 socket path; ≤150 ms for ~80 chars)
        interleave with it: total deleted = n+1+R vs n+1 believed → belief-desync of R chars.
        BOUND: R ≈ repeat_rate × burst_duration — at a typical ~30 cps autorepeat, R ≤ ~4-5 chars
        worst case during the burst; repeats after the burst delete committed/user text with the
        accounting already zeroed (plain user edits — uncompensable by design). Mitigation vs
        acceptance is S2's decision; this test pins the CURRENT contract so any change (e.g.
        observing value==2 to compensate holds) is a deliberate, visible red.
      NEW:
        press_backspace(n) burst runs interleave with it: total deleted = n+1+R vs n+1 believed
        → belief-desync of R chars.
        BOUND (corrected P1.M1.T3.S2; the earlier ≤150 ms/4-5-char figure was arithmetically
        stale): R ≤ repeat_rate × (n × per_char_pace + spawn_gap) — pace 12 ms/char (wtype
        '-d 12'; ydotool CLI '-d 6' × 2 events) or 18 ms/char (ydotoold socket: contact 6 +
        inter 12), spawn floor 25 ms once, ~30 cps OS autorepeat. Typical tails (n=10-40, VAD
        commits at 0.6/0.8 s silences) → R ≈ 4-22 chars; a pathological n=80 tail → R ≈ 30-45.
        Every factor is finite and regression-pinned (test_typing_backends.py press_backspace
        argv pins; streaming.py clamps every rewind to the engine's own tail). Repeats after the
        burst delete committed/user text with the accounting already zeroed (plain user edits —
        uncompensable by design).
        S2 CLOSURE (P1.M1.T3.S2): the window is BOUNDED — accepted, NO mitigation. Post-burst
        repeats are provably user edits (idempotence; the engine owns nothing once the tail
        resets), and a compensation that observed holds would re-fire cancels per repeat — the
        exact regression this test pins as a deliberate red. D3.2 closed: this test + the
        recorded evidence (plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md).
  - WHY: single source of truth for the audit note stays in this docstring (S1's Mode A choice);
    the corrected figures match the verified constants exactly (GOTCHA #7).
  - DO NOT: touch the test body, assertions, doubles, or any other test/section; reword S1's
    surviving sentences; change numbers.

Task 3 (CONDITIONAL — EXECUTE ONLY IF A TASK-1 GREP FAILED): smallest PRD-sanctioned mitigation
  - STEP 1: STOP and reassess which input is unbounded (filter removed? pace pin gone? clamp
    removed?). A single drifted grep may be tree churn, not a real unboundedness — re-read the
    site before concluding.
  - STEP 2 (only for genuine unboundedness): bound the compensation burst — in daemon.py cancel(),
    clamp n to a fixed duration budget: n_capped = min(n, int(BUDGET_S / per_char_pace)) with
    BUDGET_S a named module constant (~1.0 s), journal the stranded remainder
    ("cancel: burst capped at N chars; M stranded tail chars remain"), and update BOTH this
    docstring and the research note to document that a hold past the capped burst is provably a
    user edit. NOTE this strands tail chars on screen (a worse failure than the desync) — the
    trade-off must be stated, and S1's pin + the task record updated deliberately in the same
    change.
  - STEP 3: run the FULL validation loop (L1-L4) on the modified files; scope guard becomes
    tests/test_key_listener.py + voice_typing/daemon.py.
  - THIS TASK IS EXPECTED NOT TO RUN (Task 1 verifies green at research time).

Task 4: VALIDATE (L1-L4 below). If committing: "P1.M1.T3.S2: D3.2 closed — residual cancel-hold
  desync window verified BOUNDED (R ≤ 30cps × (n×12-18ms + 25ms)); corrected audit-note bound +
  recorded acceptance in the S1 hold-trace docstring; no mitigation (record branch)".
```

### Implementation Patterns & Key Details

```python
# THE DECISION (recorded, not re-derived): every factor of R is finite and pinned.
R <= repeat_rate * (n * per_char_pace + spawn_gap)
#   per_char_pace = 0.012 (wtype '-d 12'; ydotool CLI '-d 6' x2) | 0.018 (socket: 6+12)
#   spawn_gap     = 0.025 (once; _MIN_SPAWN_GAP_S)
#   n             <= engine's own pending tail (streaming clamp) <= one VAD utterance
#   repeat_rate   ~ 30 cps (OS typematic; documented assumption)
# ⇒ typical n=10-40 → R ≈ 4-22; pathological n=80 → R ≈ 30-45. Finite. Accepted.

# WHY NO MITIGATION: post-burst repeats hit tail_len=0 → cancel() is an idempotent no-op and the
# engine owns nothing (no belief to desync). Observing value==2 to compensate holds would re-fire
# cancel per repeat — the regression S1's pin exists to catch. The item's example mitigation
# ("a hold past the burst is provably a user edit") already holds structurally.
```

### Integration Points

```yaml
UPSTREAM CONSUMED — P1.M1.T3.S1 (hold-trace test + audit note; parallel landing):
  - Task 0 gates on its presence; Task 2 edits ONLY its docstring AUDIT NOTE. S1's assertions,
    doubles, and one-cancel pin are untouched (green by construction).

DOWNSTREAM — D3.2 closure (this task IS the closure):
  - "closed with test or recorded evidence": test = S1's hold-trace regression test; recorded
    evidence = the corrected docstring + research note. After this lands, D3.2 needs nothing else.

SIBLING (parallel-landed, disjoint) — P1.M1.T2.S3:
  - Owns tests/test_typing_backends.py (landed 2cb3b29). S2 only GREPs it (Task 1); no edit.

FUTURE — P1.M1.T4 (D3.3 suppression-window latch chaining):
  - Disjoint concern (window re-LATCH chaining, not the desync bound). S2's docstring edit does
    not touch the re-stamp sentences S1 asserted; T4 must keep them intact.

UNCHANGED: daemon.py, key_listener.py, streaming.py, typing_backends.py, config.toml,
test_typing_backends.py, test_daemon.py, README.md (DOCS: none), all other files.
```

## Validation Loop

### Level 1: The decision inputs still verify (re-run the Task-1 greps post-edit)

```bash
cd /home/dustin/projects/voice-typing
grep -c 'value != 1' voice_typing/key_listener.py          # 1
grep -c '"-d", "12"' voice_typing/typing_backends.py       # >=1 (wtype pace)
grep -c '"-d", "6"' voice_typing/typing_backends.py        # >=1 (ydotool CLI pace)
grep -n 'S2 CLOSURE' tests/test_key_listener.py            # 1 (the closure paragraph landed)
grep -c '4-5 chars worst case\|≤150 ms\|≤~4-5' tests/test_key_listener.py   # 0 (stale figure gone)
.venv/bin/python -m py_compile tests/test_key_listener.py && echo "L1 PASS: compiles"
# Expected: all greps match; the stale figure is fully replaced; file compiles.
```

### Level 2: The suite is green (S1's pin untouched)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q 2>&1 | tail -3
# Expected: 0 failures (baseline Part A row 6 is 32/0; S1 adds 1 → all green incl. the edited test).
```

### Level 3: The edited test, isolated (docstring edit broke nothing)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q -k sustained -v 2>&1 | tail -4
# Expected: 1 passed. (A docstring cannot break a test unless the edit escaped the string —
# L1's py_compile + this run prove it didn't.)
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only            # exactly: tests/test_key_listener.py
git diff --exit-code -- voice_typing/ tests/test_daemon.py tests/test_typing_backends.py README.md \
  && echo "L4 PASS: zero source/out-of-scope changes" || echo "L4 FAIL"
test -s plan/008_a47116bb2b79/P1M1T3S2/research/d32_closure_decision.md && echo "evidence record present"
# Expected: only the test file modified; the evidence record exists. (If Task 3's conditional
# branch ran, daemon.py is additionally expected — see its STEP 3 note.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L0 prerequisite: S1's test present. L1: decision-input greps + closure paragraph + stale-figure-gone + py_compile. L2: key-listener suite 0 failures. L3: the edited test passes isolated. L4: only `tests/test_key_listener.py` changed (research note present, untracked).

### Feature Validation
- [ ] The decision executed is RECORD (bounded), backed by live-verified inputs (Task 1 all green).
- [ ] The docstring now states: the parametric bound with 12–18 ms/char + 25 ms + ~30 cps; R ≈ 4–22 typical / 30–45 at n=80; post-burst repeats = by-design user edits; S2 CLOSURE paragraph (accepted, no mitigation, D3.2 closed, evidence pointer).
- [ ] S1's assertions, doubles, one-cancel pin, and re-stamp sentences byte-identical (docstring-only edit).

### Code Quality / Scope Validation
- [ ] No source change; no README (DOCS: none); no new tests (inputs already pinned); no test_typing_backends.py/test_daemon.py edits.
- [ ] Numbers recorded exactly as verified (GOTCHA #7) — no rounding, no re-derivation.
- [ ] Conditional fallback documented and gated (Task 3 runs only on a Task-1 failure, and then starts by reassessing, not editing).

### Documentation & Deployment
- [ ] Mode A record lives in the test docstring (single source of truth, per S1's design); the orchestrator-facing evidence is the research note. No other docs.

---

## Anti-Patterns to Avoid

- ❌ Don't implement a mitigation — the evidence says bounded; the fallback is gated on a failed
  verification grep, and its first step is reassessment (CRITICAL #1).
- ❌ Don't observe value==2 autorepeats or alter cancel()/pacing — that re-fires cancels per repeat,
  the exact regression S1's pin exists to catch (a deliberate red, not an accident).
- ❌ Don't edit anything outside the AUDIT NOTE sentences + appended closure paragraph (CRITICAL #2).
- ❌ Don't author S1's test if it's absent — that's a prerequisite failure; STOP and report (CRITICAL #3).
- ❌ Don't keep or soften the stale "≤150 ms / 4–5 chars" figure — replace it with the verified
  numbers; a flattering-but-wrong record is worse than a worse-but-true one (CRITICAL #4, GOTCHA #7).
- ❌ Don't touch test_daemon.py's legacy-separator reds or test_typing_backends.py (T2.S3's file).
- ❌ Don't run pytest without timeout/full paths; don't invent ruff/mypy gates.

---

## Confidence Score

**9/10** for one-pass success. The decision is pre-executed with every number file:line-verified
(pace argv, clamp, VAD cadence — and the pace pins are themselves test-landed), the sole edit is a
verbatim docstring replacement, and the validation is three greps + two pytest runs of a suite
that is green at baseline. The −1 covers exactly two residual risks, both handled by construction:
(a) S1 lands with reworded docstring text (CRITICAL #4 tells the implementer to match actual text,
not the quote); (b) tree drift on the bound inputs between research and implementation (Task 1
re-verifies; drift routes to Task 3's reassess-first fallback, never to reflexive editing).
Pure-Python, no devices, no CUDA, no daemon, no threads.
