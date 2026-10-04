# PRP — P1.M3.T9.S1: README.md — sweep streaming/cancel/configuration prose (Rev 2 bugfix changeset)

## Goal

**Feature Goal**: Mode B changeset-level docs sweep — make README.md's §Streaming dictation (:129), §Backspace-cancel (:164), and §Configuration (:197) reflect the LANDED Rev 2 bugfix behaviors: **rejected finals recover at the next utterance** (BUG-001), **the re-said sentence after Backspace-cancel streams live** (BUG-002), and **unknown config `[section]` names are rejected at load time like unknown keys** (BUG-006). Edit ONLY where prose is wrong or silent about a landed behavior; where a section needs no change, record an explicit no-change verdict instead of forcing an edit.

**Deliverable** (ONE file, three small edits + recorded verdicts):
1. `README.md` §Streaming dictation — add ONE safety-rails bullet (rejected-final recovery) [+ one optional clause: nothing types while toggled off].
2. `README.md` §Backspace-cancel — extend ONE sentence (the re-said sentence types live).
3. `README.md` §Configuration — add ONE sentence (unknown keys AND unknown section names rejected at load).

**Success Definition**:
- (a) The three required edits land, each matching the README's voice (bold bullet leads, em-dash, backticked config keys) and each stating the user-visible guarantee without engine internals (no `resume()`/`_suppressed`/`reset_boundary` in prose).
- (b) Explicit no-change verdicts recorded in the subtask result for: BUG-003 (README already promises space-separated commits via the `output.append_space` row), BUG-008 (internal; "types only the delta" stays accurate), BUG-007 (internal timing), and any section verified already-correct.
- (c) `git diff` touches ONLY the three regions of README.md; every other section (incl. the config table rows, Feedback surfaces, §Logs/status, Upgrading from Rev 1) is byte-identical.
- (d) The BUG-006 sentence is gated: only written if the unknown-table rejection is landed (preflight grep); if unexpectedly absent, report blocked rather than write a false claim.
- (e) Header count and fence parity unchanged; no test files, no ACCEPTANCE.md (that is S2), no config.toml (T6.S1's Mode A).

## User Persona

**Target User**: "dustin, six months from now, and anyone who clones the repo" — the README's stated audience; a Linux power user who needs to know what the tool guarantees after the bugfix pass (rejected hallucinations don't kill the session; cancel doesn't degrade the next utterance; config typos fail loudly).

**Use Case**: The user hits a blocklist rejection or uses Backspace-cancel and wants to know from the README what SHOULD happen next — recovery and live re-say — and trusts that a typo'd config section errors at load instead of silently disabling a feature.

**Pain Points Addressed**: pre-fix, all three behaviors were either broken (silent session death, append-only degradation, glued words) or undocumented (config table typos). The README now states the guarantees the fixes deliver.

## Why

- The contract names exactly three behaviors to document: rejected-final recovery, live re-say after cancel, config table rejection — each now LANDED (M1.T1/T2 ✅; M2.T6 lands before this task per M2→M3 ordering) and each SILENT in the README today.
- architecture/config_tests_docs.md (the cited research note) prescribes this exact Mode B scope: "update §Streaming dictation / §Backspace-cancel / §Configuration for the fixed behaviors", and its per-bug map confirms BUG-003/007/008 need NO README prose (internal correctness or already-promised outcomes) — the no-change verdicts are part of the deliverable, not omissions.
- The parallel T5.S1's conditional README touch does not fire (no request-framing prose in README — verified by grep), and ACCEPTANCE.md/config.toml belong to S2/T6.S1: zero file overlap with any in-flight task.

## What

Three minimal, user-facing edits to README.md (verbatim anchors + text below) plus recorded no-change verdicts. Nothing else changes.

### Success Criteria

- [ ] §Streaming dictation gains the rejected-final-recovery bullet before the Rollback-hatch bullet.
- [ ] §Backspace-cancel's "just say the sentence again" is extended with the live-streaming guarantee.
- [ ] §Configuration gains the unknown-key-AND-section rejection sentence near the "Real tunable keys" intro (gated on the T6 preflight grep).
- [ ] (Optional) the toggled-off guarantee clause/bullet is present.
- [ ] `git diff README.md` touches only these regions; `git status --porcelain` shows only `M README.md`.
- [ ] The subtask result records the explicit no-change verdicts (BUG-003/007/008 + any verified-correct section).
- [ ] `grep -cE '^#{1,3} ' README.md` unchanged; fence count stays even.

## All Needed Context

### Context Completeness Check

_Pass._ All three sections were read verbatim at PRP time; the exact edit anchors and replacement text are pinned below; the landing state of every referenced behavior was grepped (M1 ✅, T6 gated with a preflight command); the no-change verdicts are pre-derived from the architecture note's per-bug map; the parallel task's non-overlap is grep-verified. The implementer re-verifies live (anchors drift) then applies three edits.

### Documentation & References

```yaml
# MUST READ — the verdict table, landing state, anchors, voice, scope, the T6 gate
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M3T1S1/research/readme_sweep_verdicts.md
  why: "§1 section map + parallel-task non-overlap (grep proof). §2 landing state (M1.T1-T4 grepped
        landed; T6 preflight gate command). §3 THE VERDICT TABLE: per section, what is REQUIRED /
        OPTIONAL / NO-CHANGE and why (each traced to the contract or the per-bug map). §4 voice+scope
        (don't-touch list). §5 validation greps."
  section: "ALL load-bearing — §3 is the decision record."

# MUST READ — the file being edited (the three sections, verbatim)
- file: README.md
  why: "§Streaming dictation :129-163 (safety-rails bullets end with 'Rollback hatch'), §Backspace-cancel
        :164-181 ('mic stays hot — just say the sentence again'), §Configuration :197-233 ('Real tunable
        keys…' intro + the table). The edit anchors below are copied from the live file."
  critical: "Re-locate the anchors live (line numbers drift). Edit ONLY these three regions; the config
             table rows and every other section stay byte-identical. Match the voice: bold bullet leads,
             em-dash —, backticked config keys, terse."

# MUST READ — the cited research note (per-bug doc map + the Mode B prescription)
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/config_tests_docs.md
  why: "Prescribes this exact sweep ('Mode B final sweep: update §Streaming/§Backspace-cancel/
        §Configuration') and the per-bug map that JUSTIFIES the no-change verdicts (BUG-003 'README
        already promises space-separated words'; BUG-005 README 'likely silent' — verified; BUG-007/008
        'none')."
  critical: "READ-ONLY. config.toml's header extension is T6.S1's Mode A ride-along — NOT this task."

# CONTEXT — the bug behaviors being documented (what the fixes guarantee), READ-ONLY
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: "BUG-001 (rejected-final session death), BUG-002 (post-cancel append-only degradation),
        BUG-006 (unknown table silently ignored) — the user-facing failures the three edits now
        guarantee against."
  critical: "Do NOT document the bugs themselves (no changelog voice) — state the fixed guarantees."

# CONTEXT — the parallel task (disjoint, grep-verified)
- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M2T5S1/PRP.md
  why: "Edits daemon.py + tests/test_control_socket.py; its conditional README touch requires
        request-framing prose in README — grep shows none. Zero overlap."
  critical: "Do not touch §Logs/status (out of scope regardless)."
```

### Current Codebase tree (excerpt)

```bash
README.md        # <-- EDIT: 3 small edits (§Streaming bullet, §Backspace-cancel clause, §Configuration sentence)
tests/ACCEPTANCE.md   # NOT this task (S2 = P1.M3.T9.S2)
config.toml           # NOT this task (T6.S1's Mode A header extension)
# no docs/ dir exists in this repo
```

### Desired Codebase tree

```bash
README.md   # MODIFIED: +1 safety-rails bullet (+1 optional clause) +1 extended sentence +1 config sentence.
# NOTHING ELSE.
```

### Known Gotchas

```python
# CRITICAL #1 — THREE EDITS, VERDICTS FOR THE REST. The contract explicitly allows (expects) explicit
#   no-change verdicts. BUG-003/007/008 get verdicts, NOT prose (per the per-bug map: internal
#   correctness or already-promised). Forcing edits for them = scope violation.

# CRITICAL #2 — T6 GATE. The §Configuration sentence is only true once M2.T6.S1 lands the unknown-table
#   rejection. Preflight: grep -nE 'unknown.*(table|section)|_KNOWN_TABLES' voice_typing/config.py —
#   must hit. Absent at implementation time → report blocked (M2 precedes M3 per plan ordering; if the
#   plan held, it hits). Never write a claim the code doesn't yet satisfy.

# CRITICAL #3 — NO ENGINE INTERNALS IN PROSE. User-facing guarantees only: 'recovers at the next
#   utterance', 'types live', 'rejected at load time with a clear error'. Never resume()/_suppressed/
#   reset_boundary/append_space-path mechanics.

# CRITICAL #4 — RE-LOCATE ANCHORS LIVE. Line numbers (:129/:164/:197) were verified at PRP time but
#   drift; anchor on the quoted text (unique), not the numbers. Copy the — em-dash exactly where the
#   anchor includes it.

# GOTCHA #5 — README voice: bold bullet leads, em-dash, backticked config keys, terse; no marketing,
#   no changelog voice ("fixed a bug…"). State behavior, not history.

# GOTCHA #6 — No test framework applies (markdown). Validation = greps + git diff region check + header/
#   fence parity. Full paths if running anything (.venv/bin/python).
```

## Implementation Blueprint

### Data models and structure

Not applicable — three prose edits + verdicts.

### Implementation Tasks (ordered)

```yaml
Task 0: PREFLIGHT — verify anchors + the T6 gate (no mutation)
  - RUN: grep -nE '^#{1,3} ' README.md                        # section map intact
    grep -n 'Rollback hatch' README.md                        # the §Streaming insert anchor
    grep -n 'just say the sentence again' README.md           # the §Backspace-cancel anchor
    grep -n 'Real tunable keys' README.md                     # the §Configuration anchor
    grep -cE '^#{1,3} ' README.md; grep -c '^```' README.md   # baselines
    grep -nE 'unknown.*(table|section)|_KNOWN_TABLES' voice_typing/config.py   # T6 gate (must hit)
  - EXPECTED: all anchors found; T6 gate hits. T6 miss → apply only edits 1-2, report the §Configuration
    edit blocked in the result.

Task 1: EDIT README.md §Streaming dictation — rejected-final recovery bullet (+optional clause)
  - oldText (the rollback-hatch bullet, unique):
        - **Rollback hatch:** `output.streaming = false` restores append-only behavior (only
          finalized text typed, one append per utterance).
  - newText (the new bullet before it; keep the hatch bullet byte-identical):
        - **Rejected fragments don't stall the session.** A final the filters drop (a blocklist
          hallucination like "thank you.", or anything shorter than `filter.min_chars`) freezes that
          fragment as-is and writes one journal line — the next utterance types live again; nothing
          stays silent until you re-toggle.
        - **Nothing types while toggled off.** A trailing partial arriving just after a toggle-off
          is dropped, never typed.
        - **Rollback hatch:** `output.streaming = false` restores append-only behavior (only
          finalized text typed, one append per utterance).
  - (The toggled-off bullet is the optional BUG-004 clause — include it; if the implementer judges it
    redundant with the First-run prose, a no-change verdict for it is acceptable.)
  - ACCURACY: matches the landed daemon behavior (resume at next speech + the rejected-final journal
    line, daemon.py :1166/:1169) and the BUG-004 partial-path gate (:1397).

Task 2: EDIT README.md §Backspace-cancel — the re-said sentence streams live
  - oldText (unique):
        the in-flight utterance is dropped, and the mic stays hot — just say the sentence again.
  - newText:
        the in-flight utterance is dropped, and the mic stays hot — just say the sentence again.
        The re-said sentence types live, partials and all: cancelling never degrades the next
        utterance to wait-for-the-commit typing.
  - ACCURACY: the BUG-002 guarantee (suppression lifts at the next utterance start).

Task 3: EDIT README.md §Configuration — unknown sections rejected (T6-gated)
  - oldText (unique):
        Real tunable keys (every key below is a real field in `voice_typing/config.py`):
  - newText:
        Unknown keys — and unknown `[section]` names — are rejected at load time with a clear
        error, so a typo'd section can never silently disable a feature.

        Real tunable keys (every key below is a real field in `voice_typing/config.py`):
  - ACCURACY: the BUG-006 guarantee (from_toml raises TypeError for unknown tables like unknown keys).

Task 4: VERIFY + record verdicts
  - Greps: the three new phrases present; header count + fence parity unchanged from Task-0 baselines.
  - git diff README.md touches ONLY the three regions; git status shows only ' M README.md'.
  - Record in the result the no-change verdicts: BUG-003 (space-separated commits already promised by
    the output.append_space row), BUG-007 (internal timing), BUG-008 (internal; delta bullet stays
    accurate), Feedback surfaces / Upgrading / config table rows verified unchanged.
```

### Implementation Patterns & Key Details

```markdown
<!-- Each edit = ONE user-facing guarantee sentence/bullet. Pattern:
     bold lead → the guarantee → the concrete trigger in backticks → the recovery/outcome. No history. -->
- **Rejected fragments don't stall the session.** A final the filters drop (… `filter.min_chars`) freezes
  that fragment as-is and writes one journal line — the next utterance types live again; …
<!-- Anchors are unique quoted text (not line numbers). Em-dashes preserved byte-exactly. -->
```

### Integration Points

```yaml
DOCUMENTATION ONLY:
  - README.md: "+3 guarantee statements (rejected-final recovery, live re-say, unknown-section rejection)"
CONSUMED (verified landed / gated):
  - M1.T1/T2 resume-at-next-speech + rejected-final journal line (daemon.py :1166/:1169)
  - M1.T4 partial-path listening gate (daemon.py :1397)
  - M2.T6 unknown-table rejection (gated by Task-0; lands before this task per plan ordering)
NOT TOUCHED:
  - tests/ACCEPTANCE.md (S2), config.toml header (T6.S1 Mode A), §Logs/status, config table rows
```

## Validation Loop

### Level 1: Structure intact
```bash
cd /home/dustin/projects/voice-typing
grep -cE '^#{1,3} ' README.md      # == Task-0 baseline
test $(( $(grep -c '^```' README.md) % 2 )) -eq 0 && echo "fences OK"
```

### Level 2: The edits landed
```bash
grep -n "Rejected fragments don't stall the session" README.md        # §Streaming bullet
grep -n "types live, partials and all" README.md                      # §Backspace-cancel clause
grep -n "unknown \`\[section\]\` names" README.md                     # §Configuration sentence
grep -n "just say the sentence again" README.md                       # still present (extended, not replaced)
```

### Level 3: Scope + accuracy
```bash
git diff --stat         # only README.md
git diff README.md      # hunks confined to the three regions
grep -n 'unknown.*(table|section)' voice_typing/config.py   # the claim is true in code (T6 landed)
# Read each new sentence against the landed behavior (research §2/§3): recovery-next-utterance,
# live re-say, load-time section rejection. No engine internals in prose.
```

### Level 4: Verdicts recorded
The subtask result lists the no-change verdicts (BUG-003/007/008, untouched sections) — per the
contract, "if a section needs no change, say so explicitly."

## Final Validation Checklist

- [ ] Three required edits landed (greps green); optional toggled-off clause present or verdicted.
- [ ] `git diff` confined to the three README regions; only `M README.md` in status.
- [ ] T6 gate honored (claim written only if the code rejects unknown tables).
- [ ] No-change verdicts recorded (BUG-003/007/008 + verified-unchanged sections).
- [ ] Header count / fence parity unchanged; voice matches (no changelog tone, no internals).

## Anti-Patterns to Avoid

- ❌ Don't force edits for BUG-003/007/008 — record verdicts (Critical #1).
- ❌ Don't write the §Configuration sentence if the T6 grep misses — report blocked (Critical #2).
- ❌ Don't document engine mechanics (resume/_suppressed/reset_boundary) — guarantees only (Critical #3).
- ❌ Don't anchor on line numbers — re-locate the quoted text live (Critical #4).
- ❌ Don't touch ACCEPTANCE.md (S2), config.toml (T6.S1), §Logs/status, or the config table rows.
- ❌ Don't use changelog voice ("we fixed…") — state the behavior.
- ❌ Don't reword the kept anchor text (the hatch bullet / "just say the sentence again" lead-in /
     "Real tunable keys" line stay byte-identical inside the hunks).

---

**Confidence Score: 9.5/10** — the three sections were read verbatim, the anchors and replacement text are pinned byte-exact, the verdicts are pre-derived from the architecture note's per-bug map, the only unlanded dependency (T6) is gated with a preflight grep, and validation is deterministic (phrase greps + diff-region confinement + structure parity). The −0.5 reserves anchor-drift and the optional-clause judgment call, both handled by live re-location and the explicit-verdict escape hatch.
