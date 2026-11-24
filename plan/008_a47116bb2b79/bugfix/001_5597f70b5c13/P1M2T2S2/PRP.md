# PRP — P1.M2.T2.S2: Remediate the measured source-to-field bottleneck

## Goal

**Feature Goal**: Close the remaining measured speech→word-visible gap in bulk-text delivery (BUG-002, PRD §4.2sexies R.1/R.8) **at the stage S6's decomposition proves dominant** — after S1's controller promptness fix and R.8 callback selection are accounted for. This is a **bounded, evidence-gated remediation**: (1) apply the R.8 selection rule (earliest useful callback **by visible lag, not name**); (2) if the measured gap persists, change **exactly one dominant stage** with the stage-specific bounded fix (bulk-only evaluation cadence for the recognizer stage / prompt routing of usable updates for the relay stage / elimination of *measured-redundant* adapter waits for the adapter stage); (3) prove it with hermetic stage-specific regressions (mocked recorder/relay clock + target transports) and the affected bulk suites; (4) hand T2.S3 either a qualified candidate (diff/settings + regression proof) or the **explicit remaining blocker**. Never guess a stage, never invent text between callbacks, never remove a guard, never touch the live desktop.

**Deliverable** (bounded edits to existing files + 1 new test file; NO new end-user knob):
1. The stage-specific production diff at the seam S6's numbers indict (one of: `voice_typing/daemon.py` `_PARTIAL_CALLBACK_ATTR`/`_PARTIAL_SOURCES` default +/or `cfg_to_kwargs`/`_construct` bulk-cadence constant; `voice_typing/recorder_host.py` `_read_loop`/`_dispatch` partial routing; `voice_typing/ime/target.py` (+ `pi_editor.py`) redundant-wait elimination) — with Mode A docstring updates on every touched symbol.
2. NEW `tests/test_bulk_stage_remediation.py` — the hermetic stage regression (fake recorder clock, fake relay, fake target transport).
3. `tests/G5_TIMING_EVIDENCE.md` — append `## Candidate remediation (P1.M2.T2.S2)` (NON-verdict vocabulary; the authoritative verdict table :14 stays untouched — that is T2.S3's).

**Success Definition**:
- (a) The chosen remedy is justified **by S6's stage_summary numbers** (the dominant share named with figures), or — if S6's evidence is unavailable/inconclusive — the deliverable is the **explicit blocker record** (what is missing, why a safe fix needs a separate design) and NO speculative stage change lands.
- (b) Selection (if flipped): the default partial source changes only with S6's visible-lag + churn numbers behind it; stream-edit builds are byte-identical.
- (c) The stage fix is scoped to the bulk path only where the contract demands it (cadence constant applies only when `cfg.output.delivery == "bulk-text"`); the legacy stream-edit branch (`_on_partial` → `_stream.on_partial`), final filtering, R.6 recovery, takeover, and no-retry safety are untouched and re-proven green.
- (d) `tests/test_bulk_stage_remediation.py` passes; the contract's named suites (`tests/test_bulk_dispatch.py`, `tests/test_bulk_context_prompt.py`, `tests/test_session_recovery.py`) plus S1's gates (`tests/test_bulk_controller.py`, `tests/test_g2_bulk_gate.py`) and the fast sweep show no new failures.
- (e) The G5 evidence append records: consumed S6 verdict, chosen stage + fix, exact diff/settings, regression proof, and the T2.S3 handoff line (or blocker); `tests/test_g6_assessment.py`-style parser non-interference holds (no verdict vocabulary, verdict table untouched).
- (f) `git status --short` shows only the touched production files + the new test + the evidence doc; no `PRD.md`/`tasks.json`/`prd_snapshot.md`/config-schema changes; no new config key.

## User Persona

**Target User**: the operator dictating with `output.delivery="bulk-text"` — who must see words appear **while still speaking** (R.1), not at utterance end. Secondary: the T2.S3 implementer (consumes this candidate to qualify both routes) and future maintainers (the docstrings + evidence append are the record of WHY the stage changed).

**Use Case**: The measured G5 evidence shows speech→visible lag dominated by ONE stage (recognizer cadence / relay / adapter paint). This task moves that stage's number within safety rails, without re-architecting.

**Pain Points Addressed**: the 57-word sustained backlog / 12.6 s pi-ghostty median / sentence-end dumps — to the extent the dominant stage contributes after S1 + selection; if a stage cannot be safely moved, the pain point becomes an honestly-published blocker instead of a hidden failure.

## Why

- **BUG-002 is the unmet normative acceptance (#13)**: R.1 mandates visible words as recognition updates arrive; the repo's own G5 gate records both routes FAIL. S1 fixes the writer's promptness; selection fixes the source granularity; S2 is the *only* task that addresses the residual measured stage — without it, a dominant recognizer/relay/adapter share would survive both prior fixes.
- **Evidence-gated by design**: the gate doc's law — "Diagnose the dominant stage BEFORE tuning; do not lower thresholds or disguise zero-edit violations" — is this task's operating mode. A wrong-stage fix wastes the round and risks guards; the decision tree enforces the measured ordering.
- **Bounded and reversible**: every candidate fix is a small diff at a named seam with a code constant (no new knob), hermetic regressions, and an honest handoff — T2.S3 retains the qualification authority and the verdict table.

## What

Execute the decision tree (Implementation Blueprint) keyed on S6's stage decomposition: consume the evidence → apply selection if the numbers say so → if the gap persists, implement the ONE dominant-stage fix from the catalog (§3 of the research note) → regress hermetically → publish the candidate or the blocker. Preserve every safety rail (research §4). The contract's escape hatch is explicit: **if evidence is unavailable or a safe fix requires a separate design, publish the exact blocker instead of guessing or dropping safeguards.**

### Success Criteria

- [ ] S6's stage verdict (with numbers) is quoted in the evidence append — or its absence is the recorded blocker.
- [ ] Exactly one production stage changed (or selection only, or nothing + blocker) — never two stages in one changeset without recorded justification.
- [ ] Bulk-only scoping proven: stream-edit builds byte-identical (test asserts the cfg value flows unchanged for non-bulk).
- [ ] The new hermetic stage regression passes; the named bulk suites + S1 gates + fast sweep stay green.
- [ ] G5 append uses non-verdict vocabulary, touches no verdict table row, and hands T2.S3 a candidate or a blocker.
- [ ] No new config key; no live-desktop run; all commands under GNU `timeout` + larger bash-tool timeout.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo gets: the stage model + gate law (bulk_delivery_gate.md, quoted in research §1), the measured baseline numbers (research §2), the exact code seams per stage with grep anchors (research §3 — selection :219-234/`:353`/`:439`/`:486` + recorder_host `:154/:171`; cadence `daemon.py:342` + the lite-mode constant precedent; relay `_read_loop`/`_dispatch`/`_on_partial:2023-2045` + the DISPATCH LAW `:97`; adapter `ime/target.py:97/:127/:151-231/:268`), the safety rails verbatim (research §4), the regression + evidence plan (research §5), and the S1/S6 contracts to consume. What CANNOT be pre-supplied is S6's final numbers — the PRP therefore makes the decision tree explicit and the blocker path first-class.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S2/research/stage_remediation.md
  why: "§1 the input contracts (S6 stage_summary semantics; S1's writer ownership). §2 the measured baseline.
        §3 THE SEAM CATALOG per stage w/ anchors (selection / cadence / relay / adapter) + the bounded fix for
        each. §4 the safety rails verbatim. §5 regression + evidence plan (incl. the g6-parser non-interference
        rule and the T2.S3 handoff)."
  critical: "§3 is the fix catalog; §4 is non-negotiable."

- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "The authoritative stage model (recognizer→child→daemon | daemon→single writer | writer→target), the
        'diagnose the dominant stage BEFORE tuning' law, the R.7 gate numbers, the edge-case list for the
        writer path (S1's), and the g6-parser duplicate-route-key rule."
  critical: "No stage change without a measured dominant share. No threshold lowering."

- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/PRP.md   # + its research/ab_comparison.md
  why: "S6 defines stage_summary (speech→first-useful-update | update→ACK | ACK→field | field→frame), the
        non-verdict evidence vocabulary, and the consumer handoff (§6: 'T2.S2 needs the dominant-stage verdict
        per route with numbers'). Its run artifacts live in P1M2T1S6/research/."
  critical: "S6 is Implementing — if its evidence section/artifacts are incomplete, that is a recorded limit or
             the blocker, NEVER imputed numbers."

- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S1/PRP.md
  why: "S1's controller contract (burst coalescing, fail-closed overflow, generation re-check, prompt first
        partial). S2 consumes its suites as green gates and does NOT edit bulk_controller.py."
  critical: "Do not duplicate or re-touch the writer stage."

- file: voice_typing/daemon.py
  why: "The seams: :219-234 (_PARTIAL_CALLBACK_ATTR + _PARTIAL_SOURCES + the default-key/child-monkeypatch
        notes), :342 (cfg_to_kwargs realtime_processing_pause), :353-392 (_build_callbacks ONE-key selection),
        :431-505 (_construct/build_recorder partial_source flow), :97 (DISPATCH LAW), :2023-2045 (_on_partial
        gate + bulk/stream split), _bulk_handle_partial (enqueue-only)."
  critical: "The legacy stream branch and the enqueue-only law are inviolate. A cadence constant mirrors the
             lite-mode post_speech_silence_duration precedent (mode-scoped constant, not config)."

- file: voice_typing/recorder_host.py
  why: "The relay: _RelayFeedback.update_partial → evt_q → _read_loop → _dispatch → _on_partial; the identity
        stamping (_RelayIds) and stale/settled rejection; partial_source threading (:154/:171)."
  critical: "Partials must reach controller ingress with enqueue + notify only — never batched, never behind a
             final's barrier."

- file: voice_typing/ime/target.py   # + voice_typing/pi_editor.py
  why: "The adapter seams: acquire(:97), verify(:127,:268), show(:151-231), the request timeouts. The candidate
        'redundant wait' elimination site IF ACK→field dominates."
  critical: "Ownership/caret verification and one-edit proofs MUST remain intact — a load-bearing wait is a
             blocker, not a removal."

- file: tests/G5_TIMING_EVIDENCE.md
  why: "The measured baseline (verdict table :14 — UNTOUCHED), the paired-arm commands (:50-91), the failure
        register, and where the S2 candidate append goes (after S6's section)."
  critical: "Non-verdict vocabulary only; parse_route_verdicts must be provably unaffected."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # EDIT (selection default and/or bulk cadence constant; _construct/cfg_to_kwargs).
├── recorder_host.py     # EDIT (partial routing in _read_loop/_dispatch) — only if the relay stage dominates.
├── ime/target.py        # EDIT (+ pi_editor.py) — only if the adapter stage dominates, proofs intact.
└── ...                  # bulk_controller.py — READ-ONLY (S1); config.py — UNTOUCHED (no new knob).
tests/
├── test_bulk_stage_remediation.py   # CREATE (hermetic stage regression: fake clock/relay/transport).
└── G5_TIMING_EVIDENCE.md            # EDIT (append the S2 candidate section; verdict table untouched).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — EVIDENCE FIRST. No stage changes without S6's dominant-stage numbers. If S6's evidence is
#   missing/inconclusive, the deliverable IS the blocker record (research §1/§5) — a speculative fix is a
#   failure mode, not a fallback.
# CRITICAL #2 — RealtimeSTT 1.0.2 fires BOTH callbacks in the SAME eligible decode (stabilized first, inline);
#   plain is NOT earlier in invocation time — its win is content granularity. Select by VISIBLE lag only.
# CRITICAL #3 — The child is a FRESH interpreter (parent-side monkeypatch never reaches it): selection changes
#   go through _PARTIAL_CALLBACK_ATTR/_PARTIAL_SOURCES default resolution, never test-side patching (daemon.py:227).
# CRITICAL #4 — BULK-ONLY SCOPING. A cadence constant applies only when cfg.output.delivery == "bulk-text"
#   (mirror the lite-mode constant precedent); stream-edit builds must be proven byte-identical by test.
# CRITICAL #5 — THE DISPATCH LAW (daemon.py:97) + enqueue-only (_bulk_handle_partial) + S1's no-timer law stand.
#   No batching/deferring partials; no second writer; no retry of possibly-applied mutations.
# CRITICAL #6 — ADAPTER CHANGES ARE THE RISKIEST TIER: only a wait that is MEASURED redundant (its information
#   already proven by the op's own result) may go; ownership/caret + one-edit proofs must remain intact and be
#   re-proven. A load-bearing wait ⇒ blocker.
# CRITICAL #7 — G5 EVIDENCE APPEND: non-verdict vocabulary ("candidate"/"measured"/"blocked"); the verdict
#   table (:14) and g6 parsing are T2.S3's; duplicate route keys get overwritten by parse_route_verdicts.
# CRITICAL #8 — NO LIVE DESKTOP. S2 proves the candidate hermetically; the real-route qualification (both
#   routes, the gate numbers) is T2.S3. R.7 automation law.
# CRITICAL #9 — AGENTS.md: every command under GNU `timeout` (inner) + a strictly larger bash-tool timeout;
#   full tool paths (.venv/bin/python -m pytest); never interrupt a G5 run mid-flight (do not start one).
```

## Implementation Blueprint

### Data models and structure

None new. All fixes are constants/routing/docstrings at existing seams; the one new artifact is a test file.

### Implementation Tasks (ordered — the decision tree)

```yaml
Task 1: CONSUME THE EVIDENCE
  - Read S6's "## Paired callback comparison and stage diagnosis" section in tests/G5_TIMING_EVIDENCE.md +
    the stage_summary artifacts in P1M2T1S6/research/. Extract per route: speech→first-useful-update,
    update→ACK, ACK→field, field→frame shares, and the visible-lag winner (plain vs stabilized) with churn.
  - IF the section/artifacts are absent or marked unverified: execute Task 6 (blocker path) and stop.

Task 2: SELECTION (R.8 — applies first, cheap, always considered)
  - IF plain wins on VISIBLE lag on both routes AND churn (superseded/no_op) is inside S1's absorbed profile:
    flip the production default at daemon.py:219-234 (_PARTIAL_CALLBACK_ATTR + the default-resolution key),
    update the touched docstrings, and add the stream-identity + child-receives-selected-key regression to
    tests/test_bulk_stage_remediation.py. ELSE: record why not (numbers) and proceed.

Task 3: STAGE REMEDIATION (ONLY if S1 + selection leave a dominant gap per S6's shares)
  - Pick the SINGLE stage with the dominant share. Implement its bounded fix from research §3:
    recognizer/cadence → bulk-only evaluation cadence constant at _construct/cfg_to_kwargs
    (cfg.output.delivery-scoped; lite-mode constant precedent); relay → prompt routing of usable
    updates in _read_loop/_dispatch (enqueue+notify only; partials never behind a barrier);
    adapter → eliminate the MEASURED-redundant wait in ime/target.py(+pi_editor.py) with proofs re-proven.
  - ONE stage per changeset; record the justification (numbers) in the docstring + evidence append.

Task 4: STAGE-SPECIFIC REGRESSION (NEW tests/test_bulk_stage_remediation.py — hermetic)
  - Fake recorder clock + fake relay + fake target transport; pin the stage contract end-to-end:
    cadence fix ⇒ bulk cfg gets the constant, stream cfg gets the cfg value (byte-identical);
    routing fix ⇒ a usable partial reaches controller ingress before non-barrier kinds / with zero added wait;
    adapter fix ⇒ ownership/caret/one-edit assertions unchanged (reuse bulk_delivery.rendered_equal + the
    G2 fake-target trace shapes); selection ⇒ exactly ONE callback key registered in the child build.
  - RE-RUN the contract's affected suites: tests/test_bulk_dispatch.py, tests/test_bulk_context_prompt.py,
    tests/test_session_recovery.py + S1's tests/test_bulk_controller.py, tests/test_g2_bulk_gate.py.

Task 5: PUBLISH THE CANDIDATE (tests/G5_TIMING_EVIDENCE.md append)
  - "## Candidate remediation (P1.M2.T2.S2)": date/commit, the S6 verdict consumed (quoted numbers), the
    chosen stage + fix + exact diff/settings, the regression proof (commands + counts), the T2.S3 handoff
    line. NON-verdict vocabulary; verdict table untouched; g6 parser provably unaffected.

Task 6: BLOCKER PATH (only when evidence is unavailable or no safe fix exists)
  - Append the same section as an EXPLICIT BLOCKER: what is missing (which clock/arm), why the safe fix needs
    a separate design, and what T2.S3 must measure first. NO speculative stage change lands.
```

### Implementation Patterns & Key Details

```python
# (1) The cadence constant (recognizer stage) — mode-scoped, mirroring lite's silence-gate precedent:
_BULK_REALTIME_PROCESSING_PAUSE = 0.05   # module constant; NO new config key (contract)
# in _construct (after cfg_to_kwargs, before callbacks):
if cfg.output.delivery == "bulk-text":
    kwargs["realtime_processing_pause"] = _BULK_REALTIME_PROCESSING_PAUSE
# Test pins: bulk cfg → 0.05; stream cfg → cfg.asr.realtime_processing_pause (unchanged).

# (2) The routing rule (relay stage): a partial's path is evt_q → _read_loop → _dispatch → _on_partial →
#     controller.on_partial with enqueue + Condition-notify ONLY. If a measured serialization exists (e.g.
#     dispatch order behind non-barrier kinds), reorder so usable partials are never deferred — never batch.

# (3) The adapter rule: delete ONLY a wait whose information the op's own result already proves; re-prove
#     ownership/caret + one-edit (G2-style traces) unchanged. Otherwise: blocker.

# (4) The evidence vocabulary (S6's rule): "measured" / "not-run" / "unverified-clock" / "candidate" /
#     "blocked" — never pass/fail; parse_route_verdicts must see no new verdict rows.
```

### Integration Points

```yaml
HANDS-OFF (owned by siblings — do not edit):
  - bulk_controller.py: "S1's writer stage; its suites are S2's green gates"
  - tests/G5_TIMING_EVIDENCE.md :14: "the authoritative verdict table — T2.S3 refreshes it"
  - config.py/config.toml: "NO new end-user knob (contract); the cadence is a code constant"
CONSUMED-BY:
  - T2.S3: "qualifies THIS candidate on both real routes against the R.7 gate numbers, then refreshes the
            verdict table + G6/README claims"
PRESERVED (re-proven, not edited):
  - stream-edit branch / final filtering / R.6 recovery / takeover / no-retry: "the named suites re-run green"
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -c "import voice_typing.daemon, voice_typing.recorder_host, voice_typing.ime.target; print('imports OK')"
```

### Level 2: Unit + affected suites (THE gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_bulk_stage_remediation.py -v        # NEW: all pass
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_bulk_context_prompt.py \
    tests/test_session_recovery.py -q                                                  # contract's list
timeout 300 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q   # S1 gates
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q     # no NEW failures
```

### Level 3: Evidence-append hygiene (parser non-interference)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python - <<'PY'
from tests import g6_assessment as g6
doc = open("tests/G5_TIMING_EVIDENCE.md", encoding="utf-8").read()
before = g6.parse_route_verdicts(doc)
# the S2 section must not have changed the parsed verdicts (same routes, same verdicts):
import subprocess, json
print("routes:", {r: v for r, v in before.items()})   # manual compare vs pre-append run + record in the evidence
PY
# Also verify the verdict table (:14) region is untouched: git diff tests/G5_TIMING_EVIDENCE.md | grep -E '^[+-]\|' | head
```

### Level 4: Scope guard (NO live desktop; bounded diff)

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: only the touched production seams + tests/test_bulk_stage_remediation.py (new) + the evidence doc.
# NO config.py/config.toml schema change; NO bulk_controller.py; NO PRD/tasks/snapshot; no daemon foregrounded;
# no G5 lab run started (qualification is T2.S3).
```

## Final Validation Checklist

### Technical Validation
- [ ] All Level-2 suites green under `timeout` (new file + contract list + S1 gates + fast sweep).
- [ ] Parser non-interference checked (Level 3); verdict table untouched.
- [ ] `git status` clean-scoped (Level 4).

### Feature Validation
- [ ] The stage choice (or selection, or blocker) is backed by quoted S6 numbers in the evidence append.
- [ ] Bulk-only scoping proven by test where the fix is mode-scoped; stream-edit byte-identical.
- [ ] Safety rails re-proven: stream branch, final filtering, R.6 recovery, takeover, no-retry.
- [ ] T2.S3 handoff present (candidate diff/settings + regression proof, or the explicit blocker).

### Code Quality Validation
- [ ] Every touched symbol's docstring updated (Mode A) — callback/cadence/routing/adapter contract.
- [ ] One stage per changeset; no invented text between callbacks; no guard removed; no new knob.

### Documentation & Deployment
- [ ] `tests/G5_TIMING_EVIDENCE.md` candidate section dated, provenance-complete, non-verdict vocabulary.

---

## Anti-Patterns to Avoid

- ❌ Don't change a stage without S6's measured dominant-share numbers — the blocker record is the correct output when evidence is missing (Critical #1).
- ❌ Don't select the callback by name or invocation time — visible lag only (Critical #2), and never via parent-side monkeypatch (Critical #3).
- ❌ Don't let a cadence/routing/adapter change touch stream-edit builds or the enqueue-only law (Criticals #4/#5).
- ❌ Don't remove a load-bearing adapter wait — that's a blocker, not a fix (Critical #6).
- ❌ Don't write verdict vocabulary into the evidence append or touch the :14 table (Critical #7).
- ❌ Don't run the G5 lab or touch the live desktop — qualification is T2.S3 (Critical #8).
- ❌ Don't edit `bulk_controller.py` (S1), config schema, or run un-timed commands (Critical #9 / AGENTS.md).

---

## Confidence Score

**8/10** — the seams, safety rails, fix catalog, and evidence vocabulary are fully verified in-tree; the S1/S6 contracts are explicit; the decision tree has a first-class blocker path so the agent cannot "guess" a stage. The residual risk is deliberate: S6's final numbers were still landing at research time, so the PRP's strength is conditional correctness — it forces the evidence gate rather than pretending the numbers exist.
