# PRP — P1.M1.T1.S2: Classify reds vs the lazy-separator contract

## Goal

**Feature Goal**: Turn S1's G1 baseline failure inventory into a **verified classification** — all 20 reds tagged **(i) legacy lazy-separator contract red** (tests encode the *eager* separator; HEAD defers it since `26d570b`) or **(ii) new/unexpected** — each (i) backed by a named contract facet, NOT just transcribed. Establish the **watch set** (the two (ii) candidates) with a **pre-change flake baseline** (3× re-run of `test_streaming.py`) and a **pre/post re-run protocol** that every later D3 change uses to disambiguate regression vs flake. **No blanket skips, no legacy behavior edits to fake parity.**

**Deliverable**: A "Failure classification (P1.M1.T1.S2)" section **appended to `tests/G1_BASELINE.md`** (S1's committed doc): the 20-row classification table (Class + Facet + one-line evidence), the watch-set subsection (the 3-run baseline + the per-change protocol), and the no-skip/no-parity statement. Committed alone (doc-only change).

**Success Definition**: (a) the 16 fast reds are re-verified live and match the record's names exactly (`16 failed, 76 passed` combined); (b) each of the 18 (i) tags is confirmed by mapping its failing expectation to a lazy-separator facet (F1–F5); (c) the two (ii) candidates are confirmed non-separator-shaped by reading their assertions; (d) the 3× pre-change `test_streaming.py` baseline is recorded (per-run per-test outcomes, bounded table) and interpreted (stable-red vs flaky); (e) the protocol text is actionable for P1.M1.T2/T3/T4; (f) only `tests/G1_BASELINE.md` changes.

## User Persona

**Target User**: The implementing agents of P1.M1.T2 onward (the merge, the socket gap, the cancel-audit replay, the latch fix) who must answer "is this red MINE?" — and the PRD R.7 G1 gate that mandates exactly this reconciliation.

**Use Case**: A D3 change lands; the agent re-runs `test_streaming.py`, sees `test_a_delta_cadence` red, consults the watch-set baseline + protocol, and knows whether that red is a pre-existing stable red, a flake, or ITS regression.

**Pain Points Addressed**: Without classification, every later task inherits 20 unexplained reds and cannot detect new damage; the two (ii) candidates would either be chased blindly or silently ignored.

## Why

- **PRD R.7 G1 mandates the reconciliation**: "reconcile the legacy separator failures at HEAD … against the lazy-separator contract and separate them from NEW failures (no blanket skips, no legacy behavior changes to fake parity)."
- **The research record pre-classified but did not VERIFY**: `d3_defects_g1_baseline.md` A.1 tags items 1–18 (i) and 19–20 (ii) with one-line reasons. S2's value-add is (a) confirming each (i) maps to a specific clause of the `26d570b` contract (so the tag is falsifiable, not folklore), (b) confirming the (ii)s by reading their assertions, and (c) operationalizing the watch set with a flake baseline + protocol — none of which the record did (single run, read-only).
- **Stable-red vs flake matters for the whole phase**: the two (ii) candidates are red against ACCEPTANCE row 11's past 7/7 claim — either a late regression from the post-T8 commits (`cf2dfb1` debounce, `0e7dd05` clamped rewinds, `26d570b` lazy separator, `e5409a1` pacing) or a real-model flake. A 3-run pre-change baseline is the only cheap way to tell them apart before changes start stacking.
- **Protects the (i) reds from accidental "fixes"**: pinning them as contract reds (with facets) tells later agents NOT to reconcile them inside unrelated tasks — and that their set must stay EXACTLY stable unless a task explicitly targets it.

## What

Re-verify the 16 fast reds live; read + confirm the 4 real-model reds' classifications against the `26d570b` contract; run `test_streaming.py` 3× for the flake baseline; append the classification table + watch-set protocol to `tests/G1_BASELINE.md`; commit the doc alone. **Zero code, zero test, zero config changes; no skips added.**

### Success Criteria

- [ ] `tests/G1_BASELINE.md` exists (S1's contract) before any append; S2 appends only.
- [ ] Combined re-run `timeout 120 uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no` → exactly `16 failed, 76 passed`, names matching the record (fix the doc's #6 typo to `test_commit_extend_strips_spurious_mid_sentence_period`).
- [ ] The appended table has 20 rows: #1–18 class (i) each citing facet F1/F2/F3/F4/F5; #19 `test_a_delta_cadence`, #20 `test_b_commit_rewind_exact` class (ii) with the "not separator-shaped" rationale.
- [ ] 3 pre-change runs of `tests/test_streaming.py` recorded (run # × per-test outcome for all 7 tests) with the stable-red/flaky interpretation stated.
- [ ] The per-change protocol (before/after every D3 change: one `test_streaming.py` run + the 3 fast suites; the regression vs flake decision rules; the (i)-set-must-stay-exact rule) is in the doc.
- [ ] The doc states: NO blanket skips, NO legacy behavior edits to fake parity (and that reconciling the (i) reds is deliberate later work, never an accident).
- [ ] `git diff --name-only` for the commit == `tests/G1_BASELINE.md` only.

## All Needed Context

### Context Completeness Check

_Pass._ The full classification (with facet mapping, live re-verified for the 16 fast reds TODAY), the two (ii) candidates' actual assertions, the `26d570b` contract clauses, the protocol design, the exact run counts, and the doc-append shape are all below. An agent new to this repo needs nothing else.

### Verified Current State (re-verified this session)

- **HEAD `d78ff95` == code-state `2335a9e`** for `voice_typing/ tests/ config.toml` (verify: `git diff 2335a9e --stat -- voice_typing/ tests/ config.toml` → empty). `tests/G1_BASELINE.md` does NOT exist yet at research time — S1 (in flight) creates it; **S2 appends and must verify it exists first**.
- **The 16 fast reds reproduce EXACTLY** (re-run today, combined, `--tb=no`): `16 failed, 76 passed`; the FAILED names match `d3_defects_g1_baseline.md` A.1 items 1–16 byte-for-byte.
- **The lazy-separator contract** (commit `26d570b`, 2026-10-28): no standalone space keystrokes (the space rides inside the next payload — the `_lead_sep` flag, streaming.py:277/:664/:796/:819); a pending separator at non-commit exits discharged on the next fragment; recognized text never carries the space while keystroke accounting counts it; disarm folds on-screen words into settled text. Facet taxonomy (every (i) maps to one):
  - **F1 EAGER-SEP** — expects standalone `('type',' ')` / trailing space in the delta at commit (A.1 #1,3,4,5,6,7,9,11,13,14,16,17)
  - **F2 EMPTY-DELTA-SEP** — empty-delta commit still types the separator; HEAD defers → zero keystrokes (#2,15)
  - **F3 SEP-FAILSAFE** — fail-safe promote on a failing separator keystroke that HEAD never emits (#8,10)
  - **F4 RESET-DOUBLE-SEP** — "already spaced" state across reset_session (#12)
  - **F5 ABSORB-SPACING** — frozen/stranded absorb leaves exactly one trailing space (#7 partially, #18)
- **The (ii) candidates** (read at tests/test_streaming.py:1202/:1236): `test_a_delta_cadence` asserts ≥1 delta-only extend cycle; `test_b_commit_rewind_exact` asserts ≥1 revising commit (one that rewound a non-empty tail) with a bounded same-session retry. Both are CADENCE/liveness properties over the real small.en harness — no separator facet applies. Candidate causes: late regression from the post-T8 commits / real-model flake / legitimate frequency change from the lazy separator itself (an exact-confirm commit now rewinds nothing AND types nothing).
- **`test_streaming.py`**: 7 tests, ~106 s (real small.en on wav fixtures); research run = 3P/4F (a, b, f, g red). Two-timeout rule applies (inner 300 / bash ≥360).

### Documentation & References

```yaml
# THE RESEARCH RECORD (the pre-classification S2 verifies)
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: Part A (the 15-suite baseline) + A.1 (the 20-item inventory with one-line reasons and the
        preliminary (i)/(ii) tags) + the methodology. S2 CONFIRMS, formalizes (facets), and
        operationalizes (watch set) — never blindly transcribes.
  critical: "A.1 #6's name has a typo ('stips…strips') — the real name is
        test_commit_extend_strips_spurious_mid_sentence_period. Fix it in the appended table."

# THE BASELINE CONTRACT (S1 — this task's INPUT)
- file: plan/008_a47116bb2b79/P1M1T1S1/PRP.md
  why: Defines tests/G1_BASELINE.md's shape (15-row table, totals 379/20, failure inventory,
        bounded, committed alone) — S2 APPENDS to that doc without rewriting S1's sections.
  critical: "If tests/G1_BASELINE.md does not exist at implementation time, S1 has not landed —
        STOP (input contract unmet); do not create a partial doc yourself."

# THE CONTRACT BEING CLASSIFIED AGAINST
- url: (git show 26d570bea9fc1e03eb9de7517023fc3d3dfed869 in-repo)
  why: The lazy-separator commit message is the contract's authoritative statement (clauses a/b/c:
        pending-separator flag, screen-vs-decoder split, no standalone space keystrokes, disarm
        folding). Read it before classifying anything.
  critical: "16 fast reds = expectations that still encode the EAGER separator or its fail-safe
            consequences; the lazy separator is BY DESIGN at HEAD — the reds are the tests' debt,
            not the code's bug."

# THE SPEC
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: §4.2sexies R.7 gate G1 (the mandate + the no-blanket-skips/no-parity-edit rule) and §4.2quater
        (the streaming contract the tests encode).

# THE WATCH-SET CANDIDATES (read their assertions)
- file: tests/test_streaming.py
  why: :1202 test_a_delta_cadence (extend-cycle property), :1236 test_b_commit_rewind_exact
        (revising-commit property, bounded same-session retry). Reading them is the (ii)
        confirmation — the failure reasons ("no delta-only extend cycle", "no revising commit")
        share nothing with separator placement.
  gotcha: "test_streaming.py is the ONLY slow file (~106 s, real model). Never run it without
           the two-timeout wrapper; never run the 4 forbidden suites."

# THE ENGINE (for facet verification if a classification is disputed)
- file: voice_typing/streaming.py
  why: :277 the _lead_sep flag doc; :664 set; :683/:803/:824 kept through rewinds; :796/:819
        carried lazily on exact-confirm/empty-retype; :766 no lone-space type_text. If a
        proposed facet mapping doesn't hold against these lines, the (i) tag is wrong —
        re-classify as (ii) instead of forcing it.

# THIS SUBTASK'S RESEARCH NOTE (the full pre-verified table)
- docfile: plan/008_a47116bb2b79/P1M1T1S2/research/red_classification_findings.md
  why: §1 the contract + facet taxonomy; §2 the 20-row table (live-verified for #1-16, record-
        based for #17-18, read-confirmed for #19-20); §3 the (ii) causes; §4 the protocol; §6 facts.
  section: "§2 (the table — transcribe into the doc) and §4 (the protocol) are load-bearing."
```

### Current Codebase tree (relevant slice)

```bash
tests/G1_BASELINE.md                 # S1's deliverable (in flight)   ← APPEND the classification section
tests/test_streaming.py              # :1202/:1236 the (ii) candidates; 7 tests, ~106 s, real model
tests/test_streaming_{commit,core,freeze}.py   # the 16 fast (i) reds; combined run ~0.05 s
plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md   # the research record (READ)
voice_typing/streaming.py            # the lazy-separator implementation (READ, facet verification)
```

### Desired Codebase tree with files to be changed

```bash
tests/G1_BASELINE.md    # MODIFY: append the classification table + watch set + protocol (+ commit alone)
# NOTHING ELSE. No code, no tests, no config, no skips, no CI changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S2 DEPENDS ON S1's DOC. tests/G1_BASELINE.md must exist (S1 committed it) before
# the append. If absent, STOP — do not create S1's sections yourself (that would fake the input
# contract and duplicate S1's work).

# CRITICAL #2 — VERIFY, DON'T TRANSCRIBE. Every (i) tag must cite a facet whose eager expectation
# actually appears in the recorded failure reason (or a fresh --tb=line run). If one doesn't map,
# classify (ii) and add it to the watch set — the record's tag is a hypothesis, not truth. Same
# for the two (ii)s: confirm by reading the test bodies, not by trusting the doc.

# CRITICAL #3 — NO BLANKET SKIPS, NO PARITY FAKING. Do not add pytest skips/xfails, do not edit
# any test expectation, do not touch voice_typing/. The (i) reds STAY RED (reconciling them is a
# deliberate later decision, never an accident). The doc says so explicitly.

# CRITICAL #4 — THE (i) SET IS A INVARIANT. The protocol must state: after every D3 change the
# 16 fast reds must remain EXACTLY this set (same names); any growth/shrinkage = a finding to
# investigate, even if it looks like an improvement.

# CRITICAL #5 — TWO TIMEOUTS + THE FORBIDDEN SET. Inner `timeout` (120 for the fast combined run,
# 300 for each test_streaming.py run) with the bash-tool timeout above it. NEVER run
# test_feed_audio/test_daemon/test_recorder_host/test_cuda_check or any *.sh / daemon / voicectl.

# GOTCHA #6 — THE 106 s FILE × 3 RUNS ≈ 5.5 min. Run the three baseline runs SEQUENTIALLY (each
# its own bash call with its own timeouts — AGENTS.md discipline), recording per-run per-test
# outcomes between runs. Do not parallelize (the real model + loaded machine is exactly the flake
# variable under measurement).

# GOTCHA #7 — BOUNDED DOC. The append is a table + protocol text — NO pytest transcripts, NO
# _dump_events payloads, NO tracebacks (repo /tmp-bloat discipline; S1's doc is bounded too).

# GOTCHA #8 — COMMIT DISCIPLINE. Stage ONLY tests/G1_BASELINE.md. The tree has expected
# plan/008_… orchestrator noise — never include it.

# GOTCHA #9 — FULL-PATH UV: /home/dustin/.local/bin/uv (zsh aliases python3/pip/uv).
```

## Implementation Blueprint

### Data models and structure

None (documentation artifact). The table schema: `A.1# | Test | Suite:line | Class | Facet | One-line evidence`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECKS.
  - git diff 2335a9e --stat -- voice_typing/ tests/ config.toml   # EMPTY (pre-change state holds)
  - test -f tests/G1_BASELINE.md   # S1 landed. Absent → STOP (Critical #1).
  - git show 26d570b --stat >/dev/null && git log -1 --format=%B 26d570b   # read the contract
    clauses (a)/(b)/(c) before classifying anything.

Task 1: RE-VERIFY the 16 fast reds (live confirmation).
  - RUN: timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py \
           tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no
    (bash-tool timeout 180; the combined run is S2's verification — S1's one-file-per-call
    methodology was for the RECORD, and it already agrees.)
  - EXPECT: exactly "16 failed, 76 passed"; the FAILED set == A.1 #1–16 (names above; note the
    #6 typo fix). Any difference → record it in the doc as drift and investigate BEFORE
    classifying (the inventory must be true before it is classified).

Task 2: CONFIRM the classifications (facet mapping).
  - For each #1–18: check the recorded one-line reason (or a fresh --tb=line for any doubtful
    item) exhibits the eager expectation of its facet (F1–F5). Disputed item → read the test's
    assertion + streaming.py's _lead_sep lines; if it still doesn't map, tag (ii) instead.
  - For #19/#20: read tests/test_streaming.py:1202 and :1236 (the extend-cycle and
    revising-commit assertions) — confirm neither involves separator/space placement.
  - For #17/#18 (real-model, no re-run here): confirm from their assertion text — "must send
    ONLY the append_space separator, got []" (F1) and the two-trailing-spaces absorb (F5).

Task 3: RUN the watch-set flake baseline (3× the real-model file).
  - RUN 3 TIMES, sequentially, each in its own bash call:
        timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_streaming.py -q --tb=no
    (bash-tool timeout 360 per run; ~106 s each).
  - RECORD per run: the pass/fail of ALL 7 tests (parse the FAILED lines; also capture the
    passed/failed totals). Keep it as a bounded 3-column table (test × run1/run2/run3).
  - INTERPRET: #19/#20 red in all 3 → STABLE red (regression-shaped; note the candidate causes:
    post-T8 commits cf2dfb1/0e7dd05/26d570b/e5409a1, or the lazy separator legitimately
    suppressing revising commits). Flips → FLAKY (record the flip rate). Also note f/g outcomes
    per run (they are (i) but live in the same file — their flip behavior is context).

Task 4: APPEND the classification section to tests/G1_BASELINE.md.
  - APPEND (do not modify S1's sections) a section with:
      1. Heading: "## Failure classification vs the lazy-separator contract (P1.M1.T1.S2)" +
         method line (16 fast reds re-verified live at <hash> <date>; 18 (i) tags confirmed by
         facet mapping against 26d570b; the 2 (ii) confirmed by reading the test bodies).
      2. The facet taxonomy (F1–F5, one line each, citing the 26d570b clause).
      3. The 20-row table (from the research note §2; #6's name corrected).
      4. "### Watch set + re-run protocol": the two (ii) tests; the 3-run baseline table; the
         interpretation (stable vs flaky); the PER-CHANGE PROTOCOL — (a) before and after every
         D3 change (P1.M1.T2/T3/T4 + any streaming/daemon-touching change) run
         tests/test_streaming.py once (timeout 300) and the 3 fast red suites (timeout 120);
         (b) decision rules: watch test red in ALL post-change runs + green in all pre-change
         runs → REGRESSION (investigate that change); red↔green flips with no code change →
         FLAKE (record, don't chase); the 16 (i) fast reds must stay EXACTLY the known set —
         any growth/shrinkage = finding.
      5. The contract statement: "NO blanket skips; NO legacy behavior edits to fake parity
         (PRD R.7 G1). Reconciling the (i) reds with the lazy-separator contract is a
         deliberate, separately-decided change — it must never happen as a side effect."
  - BOUNDED: no transcripts, no event dumps.

Task 5: COMMIT the doc alone.
  - git add tests/G1_BASELINE.md
  - git commit -m "P1.M1.T1.S2: classify G1 reds — 18 legacy lazy-separator (facets F1-F5), 2 watch-set (ii) + 3-run flake baseline"
  - VERIFY: git show --stat HEAD lists exactly tests/G1_BASELINE.md.

Task 6: VALIDATE (gates below).
```

### Implementation Patterns & Key Details

```python
# The task's discipline is the deliverable:
#  (1) VERIFY-EVERY-TAG: an (i) tag is only as good as its facet mapping; the record's tags are
#      hypotheses. One disputed mapping → (ii) + watch set (never force-fit).
#  (2) INVARIANTS OVER SNAPSHOTS: the value is not "20 reds explained" but "the (i) set is now an
#      invariant + the (ii) set has a decision procedure" — that is what later tasks consume.
#  (3) RECORD-ONLY: no skips, no test edits, no code. The doc is the artifact.
# The 3-run flake baseline exists because regression-vs-flake cannot be distinguished from ONE
# observation — and every later D3 change will be judged against it.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS:
  - P1.M1.T2 (merge + socket gap): uses the protocol (before/after runs) + the (i)-set invariant.
  - P1.M1.T3 (cancel auto-repeat replay) / P1.M1.T4 (latch fix): same — and T4 touches the
    suppression-window path that test_streaming.py's harness exercises, so the watch set matters
    most there.
  - P1.M3 (bulk controller, G2) and P1.M7 (graduation): the doc is the G1 artifact of record.
SIBLING (S1): the append completes S1's doc; S1's sections stay untouched.
NO CODE SURFACE CHANGES.
```

## Validation Loop

> AGENTS.md two-timeout rule on every run. Full-path uv. Never the forbidden suites, never the daemon/voicectl/*.sh.

### Level 1: Preconditions held

```bash
cd /home/dustin/projects/voice-typing
git diff 2335a9e --stat -- voice_typing/ tests/ config.toml | wc -l    # EXPECT 0
test -f tests/G1_BASELINE.md && echo "L1 PASS: S1's doc present" || echo "L1 FAIL: S1 not landed — STOP"
grep -q "P1.M1.T1.S1" tests/G1_BASELINE.md && echo "L1b PASS: S1's commit present in history or doc"
```

### Level 2: The classification section landed and is well-formed

```bash
cd /home/dustin/projects/voice-typing
grep -q "P1.M1.T1.S2" tests/G1_BASELINE.md && echo "L2a PASS: section present"
grep -c "(i)" tests/G1_BASELINE.md | xargs echo "(i) mentions:"    # table rows 18 + legend
grep -q "test_a_delta_cadence" tests/G1_BASELINE.md && grep -q "test_b_commit_rewind_exact" tests/G1_BASELINE.md && echo "L2b PASS: watch set present"
for f in F1 F2 F3 F4 F5; do grep -q "$f" tests/G1_BASELINE.md || echo "L2 FAIL: facet $f missing"; done; echo "L2c facets checked"
grep -qE "no blanket skips|NO blanket skips" tests/G1_BASELINE.md && echo "L2d PASS: contract statement present"
grep -q "run 1\|Run 1\|run1\|baseline run" tests/G1_BASELINE.md && echo "L2e PASS: flake baseline table present"
grep -q "test_commit_extend_strips_spurious_mid_sentence_period" tests/G1_BASELINE.md && echo "L2f PASS: #6 name corrected"
# Expected: all PASS.
```

### Level 3: The classification is TRUE (reproducibility + spot verification)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the 16 fast reds still reproduce as classified ---"
timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no 2>&1 | tail -1
# EXPECT: "16 failed, 76 passed" — exactly the (i) set.
echo "--- the (ii) tags are defensible (read check, not a run) ---"
sed -n '1202,1210p;1236,1248p' tests/test_streaming.py | grep -E "delta-only|revising commit" && echo "L3b PASS: cadence properties confirmed (not separator-shaped)"
echo "--- watch-set spot: one more streaming run agrees with the recorded baseline pattern ---"
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_streaming.py -q --tb=no 2>&1 | tail -1
# EXPECT: the totals row consistent with the 3-run table (3P/4F or a recorded flip); if this
# 4th run CONTRADICTS the table's stability conclusion, record it as an addendum — do not edit
# history silently.
```

### Level 4: Scope — doc-only change, no skips, no parity edits

```bash
cd /home/dustin/projects/voice-typing
git show --stat HEAD | tail -3                      # EXPECT: exactly tests/G1_BASELINE.md
git diff --name-only HEAD~1 HEAD                    # EXPECT: tests/G1_BASELINE.md only
git status --short | grep -vE 'plan/' | grep -vE 'tests/G1_BASELINE.md' ; echo "(residue check — expect empty)"
echo "--- no skip/xfell/expectation edits anywhere ---"
git diff HEAD~1 HEAD -- tests/G1_BASELINE.md | grep -E '^\+' | grep -viE 'skip|classification|watch|protocol|facet|\|' | head -5
git diff HEAD~1 HEAD --stat | grep -E '\.py$' && echo "L4 FAIL: a .py changed" || echo "L4 PASS: no code/test changes"
grep -rn "pytest.mark.skip\|pytest.skip\|xfail" tests/*.py | grep -v ".venv" | wc -l   # EXPECT: unchanged (0 or pre-existing count)
# Expected: doc-only; zero skips added; zero .py changes.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: pre-change state holds; S1's doc present before the append.
- [ ] L2: classification section present (20 rows, facets F1–F5, watch set, 3-run baseline, protocol, no-skip statement, #6 name fixed).
- [ ] L3: 16 fast reds reproduce exactly; (ii) properties confirmed by reading; watch-set spot run consistent.
- [ ] L4: the commit touches only `tests/G1_BASELINE.md`; no skips/xfails added; no .py changed.

### Feature Validation
- [ ] All 18 (i) tags facet-mapped (verifiable, not transcribed); any disputed mapping moved to (ii).
- [ ] The watch set = exactly the two non-separator-shaped candidates, with a 3-run baseline + interpretation (stable vs flaky).
- [ ] The per-change protocol is executable by later tasks as written (commands + decision rules).

### Code Quality Validation
- [ ] The append is bounded (table + protocol; no transcripts/dumps).
- [ ] S1's sections untouched; the doc remains internally consistent (totals still 379/20).

### Scope Boundary Validation
- [ ] No code/test/config/skip changes; forbidden suites not run; two-timeout discipline throughout.
- [ ] The (i) reconciliation remains deferred (explicitly marked as deliberate future work).

### Documentation & Deployment
- [ ] The doc is the durable G1 classification artifact referenced by PRD R.7 and P1.M7.

---

## Anti-Patterns to Avoid

- ❌ Don't transcribe the research record's tags without verification — every (i) must map to a facet visible in its failure reason; force-fitting a disputed item is worse than growing the watch set.
- ❌ Don't add skips/xfails or edit any test expectation to "make reds green" — no blanket skips, no parity faking (PRD R.7 G1; the contract).
- ❌ Don't run the forbidden suites (`test_feed_audio`/`test_daemon`/`test_recorder_host`/`test_cuda_check`), any `tests/*.sh`, the daemon, or `voicectl` — hang vectors (repo AGENTS.md).
- ❌ Don't run `test_streaming.py`'s three baseline runs in parallel or without both timeouts — the loaded-machine real-model run IS the flake variable you're measuring.
- ❌ Don't create/rewrite `tests/G1_BASELINE.md`'s S1 sections if S1 hasn't landed — STOP instead.
- ❌ Don't paste pytest transcripts, `--tb=line` dumps, or `_dump_events` payloads into the doc — bounded table + protocol only.
- ❌ Don't commit anything besides `tests/G1_BASELINE.md` (plan/008_… noise is the orchestrator's).
- ❌ Don't bury the (i)-set invariant — the "must stay EXACTLY this set" rule is what later tasks rely on.

---

## Confidence Score

**9/10** for one-pass success. The heavy lifting is pre-verified in this PRP: the 20-row classification table (16 fast reds re-run TODAY and matching byte-for-byte; the facet taxonomy mapped from the `26d570b` contract clauses; the two (ii)s confirmed against their actual assertions), the protocol design, and the exact run commands/counts. The implementer's judgment surface is small (verify the mapping, run the 3× baseline, transcribe). The −1: the 3-run flake baseline outcome is genuinely unknown (stable vs flaky — either is a valid result, but a mixed pattern needs careful transcription), and S1's doc landing is a sequencing dependency handled by the STOP gate rather than by this PRP.
