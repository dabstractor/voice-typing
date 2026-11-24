# PRP — P1.M2.T2.S3: Qualify the selected production source on both routes

## Goal

**Feature Goal**: Be the **qualification authority** for BUG-002's timing gate (PRD §4.2sexies R.7 **G5**): after S1 (dispatch promptness) and S2 (stage remediation, landing in parallel) are in the tree, run the **production partial-source selection** — the UNFLAGGED arm, whatever `daemon.py`'s `_PARTIAL_CALLBACK_ATTR` resolves to; **never** an experimental `--partial-source` override — **independently on both isolated routes** (im-gtk, pi-ghostty) against the gate numbers, re-comparing the two callbacks first ONLY if S2's change materially altered scheduling. Then refresh `tests/G5_TIMING_EVIDENCE.md` into the **authoritative current two-route verdict** (`pass | fail(reason) | blocked(reason)` — a verdict for BOTH routes **even when unverified**), with the historical baseline and the A/B tables archived under headers the G6 parser cannot read as current. **A verified bulk source does NOT change default delivery** — graduation is G6's, and the doc sync (G6/README) is P1.M2.T3.S1/.S2's, fed by this task's evidence.

**Deliverable** (evidence + bounded docs; no remediation):
1. The qualification runs per research §5 (± the conditional A/B arms per §4), each under `timeout -k 2 1500` with a larger harness backstop, artifacts copied into `plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S3/research/`, scratch deleted.
2. `tests/G5_TIMING_EVIDENCE.md` EDIT: refreshed `## Verdict table` (SAME column format; exactly one parser-compatible current table; both routes; `blocked` for unverified), a `## Qualification run (P1.M2.T2.S3)` provenance section (date/commit, **effective source** = the resolved callback name, exact commands, sample counts, misses, instrumentation limits, per-route frame basis), updated thresholds-vs-measured, and Open items carrying the BUG-002/acceptance-#13 status with the exact blocker. Historical/A-B tables re-headed or left under archive headings — never parser-current.
3. (Conditional) The selection-default flip in `daemon.py:219-234` IF the re-comparison shows plain wins by visible lag + counts — plus the Mode A rationale docstring update (research §10).
4. The pre/post CPU-baseline diff vs the M1.T3.S1 20-name list (research §6) + the real-model watch attempt recorded honestly (research §7).

**Success Definition**:
- (a) Both routes carry a current, parser-visible verdict derived from REAL runs this round (or an honest `blocked(reason)` naming what is missing — an unrun/uncertifiable route is recorded, never imputed; re-run-once discipline for aborted arms).
- (b) The gate numbers are applied per route: speech-end→word-visible median ≤500 ms / p95 <1 s; ready→first-changed-frame insertion p95 ≤100 ms / correction p95 ≤50 ms; ≥100 real insertions AND ≥100 corrections per route; unchanged ⇒ zero edits; no sustained ≥5-word backlog ≥2 s; no sentence-end dump; clock/coverage sanity reported. **ACKs, editor-poll state, and the no-desktop smoke are never credited as display frames** — if a route's frame basis is still the im-gtk read-poll proxy, its frame bars are labeled unverified.
- (c) `tests/g6_assessment.py:parse_route_verdicts` provably sees exactly the two current routes with the new verdicts (recorded before/after) — no historical/A-B row leaks as current.
- (d) If any route fails/blocks: opt-in retained, no unproven source promoted, BUG-002/#13 left OPEN with the exact blocker.
- (e) `timeout 500` test_daemon.py failures diffed BY NAME against the M1.T3.S1 20-name list — zero new names; fast sweep shows no new failures beyond the documented classifications.
- (f) `git status --short`: only `tests/G5_TIMING_EVIDENCE.md` (+ `voice_typing/daemon.py` ONLY if the §4 flip fired) + this task's research artifacts. No `bulk_controller.py`/S2-candidate-section edits, no config/default-delivery change, no PRD/tasks/snapshot.

## User Persona

**Target User**: the operator dictating with `output.delivery="bulk-text"` (opt-in) — who must see words land while speaking (R.1); and the maintainers/P1.M2.T3.S1/.S2 who must publish claims that match measured reality. **Use Case**: after S1+S2's fixes, someone must answer, with numbers: "do BOTH routes now meet G5, and if not, exactly which bar still fails and why?" **Pain Points Addressed**: the 57-word backlog / sentence-end dumps / 12.6 s pi-ghostty median (the shipped failures); and the industry-standard failure of evidence rot — stale verdicts, borrowed numbers, and graduated claims without measurement.

## Why

- **BUG-002 is the unmet normative acceptance (#13)**: both routes failed G5 at the baseline; S1 fixed the writer's promptness, S2 moved the stage S6's numbers indicted — but without an independent, production-selection re-qualification on both routes, nobody may claim the fix landed. This task is that claim's only legitimate source.
- **The gate law is explicit and anti-fudge**: per-route verdicts, unverifiable metrics reported not imputed, ACKs/smoke never counted as frames, and "if selection plus targeted delivery work does not clear the gate, retain opt-in and record an open BUG-002/#13" (bulk_delivery_gate.md §Gate). This task executes that law verbatim.
- **The parser makes evidence surgery hazardous**: `parse_route_verdicts` overwrites duplicate route keys — one stale "current"-looking table silently corrupts G6's assessment. The one-current-table + archive-headers rule (research §2) is load-bearing.
- **Regression safety is part of qualification**: S1+S2+(possible S3 flip) touched production scheduling — the M1.T3.S1 named baseline diff proves the CPU suite did not regress; the honest real-model watch attempt keeps the record complete without over-claiming.

## What

Read S2's candidate section → decide the conditional A/B re-comparison (material scheduling change?) → (if plain wins, flip the default) → run the scaffold smoke (wiring only) → run the production arm on each route sequentially, copying artifacts → apply the gate numbers → rewrite the evidence file per the surgery rules → run the parser check + the CPU-baseline diff + the watch attempt → hand P1.M2.T3.S1/.S2 the evidence. Every step bounded; the honest-blocked path is first-class (research §9).

### Success Criteria

- [ ] S2's candidate section is quoted (consumed verdict, chosen stage, or blocker) in the qualification provenance; the A/B re-comparison decision (ran / not-needed + one-line reason) is recorded.
- [ ] Both routes have current `pass|fail|blocked` verdicts from this round's runs (or honest blocked), with ins/cor counts, misses, backlog max, dump flags, and frame basis.
- [ ] Exactly one parser-compatible current verdict table; before/after `parse_route_verdicts` output recorded; historical + A/B tables archived under non-current headers.
- [ ] Effective source (resolved callback name), exact commands, provenance (commit, RealtimeSTT version, model/device, cadence, budget, warm policy, observer status) recorded per run.
- [ ] CPU-baseline name-diff clean; real-model watch outcome recorded with provenance ("not-run" if unavailable — never claimed).
- [ ] On failure: opt-in retained, BUG-002/#13 open with the exact blocker; on success: still no default-delivery change, G6 untouched (T3's).
- [ ] All commands under GNU `timeout` + larger bash-tool backstop; no live desktop touched; no run interrupted mid-flight.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to the repo gets: the gate law + numbers verbatim (research §1), the current evidence file's structure + the exact surgery rules incl. the parser's duplicate-key behavior and the column format (research §2), the S6 measured baseline being qualified against with numbers (research §3), the conditional-A/B decision rule + the flip authority (research §4), the exact run commands incl. fixture/smoke/artifact/scratch discipline (research §5), the named-baseline diff procedure + the 20-name list location (research §6), the watch policy (research §7), the safety rails (research §8), the honest-failure path (research §9), and the Mode A docstring scope (research §10). What CANNOT be pre-supplied is S2's final candidate state — hence the conditional §4 rule and the blocked path.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S3/research/production_qualification_runs.md
  why: "ALL of it is load-bearing: §1 the gate law/numbers + the not-a-frame rule; §2 the evidence-file
        surgery (one current table, archive headers, parser proof); §3 the S6 baseline numbers this round is
        measured against; §4 the conditional A/B + flip authority; §5 exact commands; §6 the name-diff
        procedure; §7 the watch policy; §8 safety rails; §9 the blocked path; §10 the Mode A scope."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§'Gate and evidence handoff' is the authoritative law this task executes (per-route requirement,
        the exact numbers, the parser's duplicate-route-key overwrite, the one-current-table rule, the
        retain-opt-in-on-failure rule). §'G5 experiment and instrumentation' pins the frame-basis honesty
        rules (editor read-poll ≠ frame; no-desktop smoke ≠ measurement)."
  critical: "No threshold lowering; no imputed passes; ACKs are not frames."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S2/PRP.md
  why: "The S2 CONTRACT: it hands THIS task either a qualified candidate (diff/settings + regression proof
        recorded in its '## Candidate remediation' append) or an explicit blocker — consume exactly that
        section; do not re-derive or edit it."
  critical: "S2 is Implementing in parallel — read its append from the live file at implementation time; if
             absent/incomplete, that fact is part of THIS task's provenance (and possibly the blocker)."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/PRP.md   # + P1M2T1S6/research/*
  why: "S6 defines the A/B methodology, the non-verdict vocabulary, the stage_summary semantics, and its
        explicit handoff ('what T2 must move' / 'what S1's design must survive') — the §4 re-comparison
        reuses its exact commands and comparability rules (same clips/kernel/budget, sequential arms)."
  critical: "im-gtk/plain was not-run in S6 (two sanctioned attempts, 'bulk delivery never re-armed') —
             completing that pair is legitimately THIS task's job if §4 fires; never borrow its numbers."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T3S1/research/bug004_named_daemon_baseline.md
  why: "§1's canonical 20-name failed-node-ID list (verbatim) — the set-diff target for the pre/post CPU
        check (research §6). Names, never counts."
  critical: "Diff by node ID; a new name = regression (investigate or record as blocker); a missing name = a fix."
- file: tests/G5_TIMING_EVIDENCE.md
  why: "The file under edit: :14 the verdict table (THIS task refreshes it), :50+ the paired-arm commands,
        :144 thresholds-vs-measured, :166 failure register, :424 the S6 section, :181 the historical baseline
        context. Its own header rules ('a G5 pass never marks a row verified'; misses are misses) bind the edit."
  critical: "Preserve the verdict-table column format for the parser; archive historical/A-B rows under
             different headers; S2's candidate section is read-only."
- file: tests/g5_timing_lab.py   # + tests/g5_timing_support.py, tests/g6_assessment.py
  why: "The runner: --route im-gtk|pi-ghostty, --partial-source plain (EXPERIMENTAL — not for the
        qualification runs), G5_TIMING_LAB=1 gate, G5_NO_DESKTOP=1 smoke, G5_KEEP_SCRATCH=1, PI_BIN discovery;
        exit 0 pass / 1 honest fail / 2 misuse; ONE JSON verdict line per route. g6_assessment.
        parse_route_verdicts is the Level-3 check."
  critical: "NEVER interrupt a lab run mid-flight; the JSON verdict line is the artifact of record."
- file: voice_typing/daemon.py   # :219-234
  why: "_PARTIAL_CALLBACK_ATTR + _PARTIAL_SOURCES + the default-resolution/child-monkeypatch notes — the
        production selection site. Read it to RECORD the effective source; edit it ONLY if §4's re-comparison
        flips the winner (then update the Mode A rationale docstring)."
  critical: "Selection changes go through the default-resolution key, never parent-side monkeypatching; the
             spawn child is a fresh interpreter."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py                    # READ (:219-234 effective source); EDIT ONLY on the §4 flip (+ docstring).
└── ...                          # bulk_controller.py (S1), S2's seams — READ-ONLY for this task.
tests/
├── g5_timing_lab.py             # RUN (the qualification harness; flags above).
├── g5_timing_support.py         # RUN-DEPENDENCY (aggregation; do not edit).
├── g6_assessment.py             # RUN parse_route_verdicts (the parser check).
├── test_daemon.py               # RUN (the 20-name baseline diff; CPU-only).
├── test_streaming.py            # RUN (real-model watch, bounded, honestly recorded).
└── G5_TIMING_EVIDENCE.md        # EDIT (the authoritative deliverable).
plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S3/research/   # artifacts land here.
```

### Desired Codebase tree (unchanged structure)

```bash
# Same tree. Content changes: tests/G5_TIMING_EVIDENCE.md (verdict refresh + provenance), optionally
# voice_typing/daemon.py's selection default + docstring (ONLY on the §4 flip), + research artifacts.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ★ THE PARSER OVERWRITES DUPLICATE ROUTE KEYS. tests/g6_assessment.py:parse_route_verdicts
#   scans verdict tables; a second im-gtk row anywhere parser-readable SILENTLY replaces the current one.
#   Exactly ONE current table (same column format), both routes, pass|fail|blocked; every historical/A-B
#   table under a header the parser does not treat as the current verdict table. Prove with a before/after
#   parser run recorded in the evidence. (Research §2.)
# CRITICAL #2 — ACKs / EDITOR-POLL STATE / NO-DESKTOP SMOKE ARE NOT DISPLAY FRAMES. Never credit a target
#   ACK, a 10 ms read-poll observation, or the G5_NO_DESKTOP scaffold smoke as word-visible/first-changed-
#   frame. If im-gtk's frame basis remains the read-poll proxy, its frame bars are UNVERIFIED — label them,
#   don't pass them. The pi route's S5-qualified paint (disclosed fallback) is the only qualified frame
#   evidence; exact-pair vs fallback are never merged. (Research §1/§3.)
# CRITICAL #3 — THE QUALIFICATION RUNS ARE UNFLAGGED (production selection). --partial-source plain is an
#   EXPERIMENTAL arm for the conditional §4 A/B only. Record the EFFECTIVE source (the resolved callback
#   name) per run. (Research §4/§5.)
# CRITICAL #4 — RUN DISCIPLINE: GNU timeout -k 2 1500 per route, bash-tool backstop strictly larger (S6
#   used 1560); sequential, never parallel (one CUDA model load at a time); NEVER interrupt mid-flight;
#   re-run-once for runner-side aborts — two failed attempts = the arm stands not-run (recorded, blocked).
#   Copy artifacts to research/; delete scratch tmpdirs immediately (tmpfs = RAM). (Research §5/§8.)
# CRITICAL #5 — HONESTY IS THE DELIVERABLE: a route that fails, cannot certify frames, or is unrun gets
#   fail(reason)/blocked(reason); opt-in retained; BUG-002/acceptance #13 left open with the exact blocker;
#   no unproven source promoted; no default-delivery change; G6/README untouched (T3's). A blocked table is
#   a successful outcome; a fabricated pass is the only failure. (Research §9.)
# CRITICAL #6 — BASELINE DIFF BY NAME: the pre/post test_daemon.py failures are diffed against the canonical
#   20-name list (M1.T3.S1 research §1) — counts alone lie (hermeticity tests grew the pass count before).
#   Zero NEW names required. (Research §6.)
# CRITICAL #7 — WATCH POLICY: the real-model set (test_streaming.py) runs separately, bounded; if the GPU
#   is unavailable, record "not-run" — NEVER claim it ran or borrow numbers. (Research §7.)
# CRITICAL #8 — S2/S1 BOUNDARIES: no stage tuning (S2), no bulk_controller.py (S1), no edits to S2's
#   candidate section, no config schema, no new knob. The ONLY production edit allowed here is the §4
#   selection-default flip + docstrings. (Research §11.)
# CRITICAL #9 — AGENTS.md: full tool paths (.venv/bin/python); every command timed; no daemon foregrounded;
#   the live systemd daemon NEVER armed; live desktop/service/clipboard untouched.
```

## Implementation Blueprint

### Data models and structure

None new — the deliverable is evidence. The one structural rule: the verdict table's ROW SCHEMA is
frozen for the parser (`| route | verdict | ins | cor | miss | speech med/p95 ms | worst ms | ready
ins/cor p95 ms | max out | flags |`).

### Implementation Tasks (ordered)

```yaml
Task 1: CONSUME S2 + DECIDE THE A/B (research §4)
  - READ tests/G5_TIMING_EVIDENCE.md "## Candidate remediation (P1.M2.T2.S2)" + daemon.py:219-234 (the
    landed effective source). IF S2 materially changed scheduling (cadence/dispatch/update-volume
    profile): schedule the paired A/B arms per route (S6's exact commands, sequential, re-run-once);
    re-derive the winner by VISIBLE lag + counts; if plain wins, flip the default at :219-234 + Mode A
    docstring. ELSE: record the one-line not-needed reason. If S2's section is absent/incomplete: record
    that fact; proceed to qualify whatever IS in the tree (the verdict will reflect reality).
Task 2: PRE-FLIGHT (research §5/§6)
  - CPU baseline (pre): timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no → name-diff
    vs the 20-list (record). Verify alignment fixtures exist (re-run G5_ALIGN=1 only on drift).
  - Scaffold smoke (wiring only, NEVER a measurement): G5_NO_DESKTOP=1 im-gtk, both arms if A/B fires.
Task 3: THE QUALIFICATION RUNS (research §5)
  - Route by route, UNFLAGGED arm: the two timeout -k 2 1500 commands; copy each JSON verdict artifact
    into research/; delete scratch; record exit codes. (Plus the A/B arms if scheduled.) On a runner-side
    abort: ONE re-run; two failures → the route is blocked("runner: <error>") — no imputation.
Task 4: APPLY THE GATE + WRITE THE EVIDENCE (research §1/§2)
  - Per route: check every bar (median/p95, ins/cor ≥100, zero unchanged edits, backlog, dump, clock
    sanity); annotate the frame basis per route (S5-qualified vs read-poll-proxy-unverified).
  - EDIT tests/G5_TIMING_EVIDENCE.md: refresh ## Verdict table (same format; pass|fail|blocked BOTH
    routes); add "## Qualification run (P1.M2.T2.S3)" (provenance: date/commit, effective source, exact
    commands, counts, misses, instrumentation limits, frame basis, S2-consumed verdict, A/B decision);
    update ## Thresholds vs measured + ## Run commands + ## Open items (BUG-002/#13 status + exact
    blocker). Historical/A-B tables archived under non-current headers.
Task 5: PROOFS + HYGIENE (research §2/§6/§7/§8)
  - Parser check before/after (parse_route_verdicts) — record both.
  - CPU baseline (post) name-diff; fast sweep (timeout 600, --ignore=test_feed_audio) — no new failures.
  - Real-model watch attempt (test_streaming.py, bounded) — record outcome or "not-run".
  - git status scope guard (Critical #8).
Task 6: HANDOFF (no edits — the evidence IS the handoff)
  - P1.M2.T3.S1 (G6 refresh) / P1.M2.T3.S2 (README) consume the verdict table + Open items as-is.
```

### Implementation Patterns & Key Details

```python
# (1) The verdict-table row shape (FROZEN for parse_route_verdicts — mirror the existing :14 columns):
# | im-gtk | pass | 214 | 118 | 12 | 312.4/488.1 ✓ | 612 ms | 38.2 / 41.9 ✓ | 4 | — |
# | pi-ghostty | fail (speech→visible 9.4 s median; dump) | ... | flags: backlog-sustained, dump |
# | im-gtk | blocked (frame basis = editor read-poll proxy; frame bars unverified) | ... |
# (2) The honesty vocabulary: verdict values pass|fail(reason)|blocked(reason) ONLY in the current table;
#     historical/A-B sections use measured|not-run|unverified-clock vocabulary (S6's rule).
# (3) The one allowed production edit (ONLY on the §4 flip): daemon.py:219-234 default-resolution key +
#     docstring — never parent-side monkeypatching (the spawn child is a fresh interpreter).
```

### Integration Points

```yaml
EVIDENCE (the deliverable):
  - tests/G5_TIMING_EVIDENCE.md: "the authoritative current two-route verdict + provenance + safety limits"
  - parser: "tests/g6_assessment.py:parse_route_verdicts — one current table, both routes, before/after proof"
CONSUMED-BY:
  - P1.M2.T3.S1: "refreshes tests/G6_GRADUATION.md FROM this evidence (never broadens claims)"
  - P1.M2.T3.S2: "syncs README.md to the verified scope/limits"
HANDS-OFF (owned by siblings):
  - bulk_controller.py (S1); S2's seams + its candidate section; G6_GRADUATION.md/README.md (T3);
    config/default delivery (a verified bulk source changes NOTHING by itself)
CONDITIONAL EDIT:
  - daemon.py:219-234: "selection-default flip ONLY if the §4 re-comparison shows plain wins (visible lag
    + counts), bulk-internal; stream-edit builds byte-identical"
```

## Validation Loop

### Level 1: Pre-flight sanity

```bash
cd /home/dustin/projects/voice-typing
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no    # pre name-diff vs the 20-list
timeout 120 .venv/bin/python -c "from tests import g6_assessment as g6; \
print(g6.parse_route_verdicts(open('tests/G5_TIMING_EVIDENCE.md', encoding='utf-8').read()))"  # parser BEFORE
```

### Level 2: The qualification runs (THE gate — research §5 commands)

```bash
cd /home/dustin/projects/voice-typing
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk   # smoke only
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk        # bash backstop >1500
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" \
    .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty                                                        # bash backstop >1500
# (+ conditional A/B arms w/ --partial-source plain per research §4.) Exit 0/1/2; JSON verdict = the record.
```

### Level 3: Parser + baseline proofs

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -c "from tests import g6_assessment as g6; \
print(g6.parse_route_verdicts(open('tests/G5_TIMING_EVIDENCE.md', encoding='utf-8').read()))"  # AFTER == intended
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no     # post name-diff: zero NEW names
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # no new failures
grep -nE '^## Verdict table|blocked|pass|fail' tests/G5_TIMING_EVIDENCE.md | head   # both routes present
```

### Level 4: Scope + honesty guard

```bash
cd /home/dustin/projects/voice-typing
git status --short   # evidence doc (+ daemon.py ONLY on the §4 flip) + research artifacts; nothing else
# Manual: every unmeasured metric labeled; no ACK/poll/smoke credited as a frame; BUG-002/#13 status
# consistent with the verdicts; opt-in retained regardless; no G6/README edit.
```

## Final Validation Checklist

### Technical Validation
- [ ] Both qualification runs completed (or two-attempt-blocked) under `timeout -k 2 1500` + backstop; artifacts in research/; scratch deleted.
- [ ] Parser before/after recorded; exactly one current table, both routes.
- [ ] test_daemon.py name-diff clean (pre+post); fast sweep no new failures.

### Feature (Qualification) Validation
- [ ] Every gate bar evaluated per route with real numbers; frame basis labeled per route (unverified where proxy-only).
- [ ] Effective source + provenance recorded; S2 verdict consumed; A/B decision recorded.
- [ ] Failure path (if any): opt-in retained, no source promoted, BUG-002/#13 open with the exact blocker.

### Code Quality Validation
- [ ] Verdict-table format preserved; historical/A-B tables not parser-current.
- [ ] No sibling-owned file edited (S1/S2/T3); the only production edit is the conditional flip.

### Documentation & Deployment
- [ ] Evidence sections dated, command-exact, provenance-complete, honest-vocabulary.
- [ ] daemon.py docstring updated iff the selection rationale changed (Mode A).

---

## Anti-Patterns to Avoid

- ❌ Don't run the qualification with `--partial-source` (experimental override) — production selection only, unflagged (Critical #3).
- ❌ Don't let a second parser-readable route row exist anywhere — the overwrite is silent (Critical #1).
- ❌ Don't credit ACKs, editor-poll state, or the no-desktop smoke as display frames (Critical #2).
- ❌ Don't lower thresholds, impute misses, merge exact-pair with fallback frame evidence, or promote an unproven source (Critical #5).
- ❌ Don't change default delivery, graduate, or edit G6/README — T3's; the evidence is the handoff (Critical #5).
- ❌ Don't tune a stage, edit bulk_controller.py, or touch S2's candidate section (Critical #8).
- ❌ Don't diff baselines by counts, or claim the real-model watch ran when it didn't (Criticals #6/#7).
- ❌ Don't run untimed commands, parallel CUDA runs, or interrupt a lab run mid-flight; never touch the live desktop (Criticals #4/#9).

---

## Confidence Score

**9/10** — one-pass success likelihood. The gate law, run commands, evidence surgery rules, parser behavior, baseline list, and honesty vocabulary are all pinned from the live tree (the S6 section's own provenance format is the template); the harness (`g5_timing_lab.py` + support + the S5 observer) is landed and its exit-code/JSON contract is documented in the evidence file itself. The two inherent uncertainties are handled first-class: S2's final state is consumed via its append (with the absent/incomplete case recorded, not guessed), and an unrun/uncertifiable route has the sanctioned `blocked` path rather than a temptation to fudge. The task's real risk — evidence-file surgery corrupting G6 parsing — is neutralized by the before/after parser proof in the validation loop.
