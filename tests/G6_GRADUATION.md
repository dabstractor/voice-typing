# G6 GRADUATION ASSESSMENT — bulk-text delivery (PRD §4.2sexies R.7)

- **Item**: P1.M7.T1.S1 — assemble the G6 gate; conditionally flip `output.delivery`.
- **Assessed**: 2026-11-23 @ HEAD `69952ae`.
- **Method**: mechanically derived by `tests/g6_assessment.py` (pure stdlib; reads the
  committed evidence registers only — no desktop, no CUDA, no service contact). The
  per-condition block below is the script's verbatim output; a re-run re-derives it.
- **Environment provenance** (from the evidence registers' `versions` fields; not
  re-measured here): kernel 7.2.7-arch1-1 · sway 1.12 · Ghostty 1.4.0-arch2 ·
  voice-typing pi bridge 1.0.2 · node v26.13.1.
- **Operator journal review**: *(not reviewed)* — attested field left to the operator;
  nothing here invents it.

## Verdict block (verbatim `tests/g6_assessment.py` output)

```text
G6 GRADUATION ASSESSMENT (PRD §4.2sexies R.7)
  A-g3-matrix: unmet — failed rows: ['edit-count-law']; unverified rows: ['pi-prompt-ghostty', 'class-browser-text-field', 'class:browser-text-field']
    evidence: pi_row_verdicts.jsonl:24 rows
    evidence: editor_browser_row_verdicts.jsonl:17 rows
  B-integrity: unmet — failed register rows: ['edit-count-law']
  C-g5-timing: unmet — failing/blocked routes: ['im-gtk', 'pi-ghostty']
    evidence: G5_TIMING_EVIDENCE.md:im-gtk
    evidence: G5_TIMING_EVIDENCE.md:pi-ghostty
  D-sessions: unmet — 0 valid session(s) on record, need >= 3
    evidence: G6_WRITING_SESSIONS.md: 0 valid
G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)
```

## Per-condition record

| # | Condition | Verdict | Evidence (read-only inputs) | Detail |
|---|-----------|---------|------------------------------|--------|
| A | Verified G3 rows: pi prompt in Ghostty + graphical editor + browser text field (insert AND correct) | **unmet** | `plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl` (24 rows), `editor_browser_row_verdicts.jsonl` (17 rows) | failed row `edit-count-law` (status "warm-up overcount"); `pi-prompt-ghostty` passed:true but status "**not verified** (visibility instrumentation absent)"; browser class rows read "insert-only (correction REFUSED…)" — browser correction is **not** verified. The `refuse-*` and insert/correct row classes otherwise pass; all required classes are present. |
| B | Zero observed integrity failures | **unmet** | same registers + `plan/008_a47116bb2b79/architecture/g2_gate_record.md` | the G2 record itself is clean (13/13 traces ✅, no ❌), but the `edit-count-law` register row (passed:false, "warm-up overcount: short-insert-1 changes=3; unicode-insert changes=8") is a failed row, so the zero-failures condition does not hold. |
| C | G5 per-route timing evidence passing | **unmet** | `tests/G5_TIMING_EVIDENCE.md` (P1.M6.T4.S1; present) | both measured routes fail: `im-gtk` (backlog sustained; 20 inserts / 0 corrections < 100 floor), `pi-ghostty` (speech→visible 12.6 s median; backlog sustained). |
| D | ≥ 3 operator writing sessions, usable proofread wpm > 110 each | **unmet** | `tests/G6_WRITING_SESSIONS.md` | 0 valid sessions on record. Entries are **operator-authored only**; the template ships empty and no implementer-authored entry exists anywhere. |

## Decision

**`G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)`**

### Consequence executed

- `output.delivery` stays `"stream-edit"` everywhere: `voice_typing/config.py` default,
  `config.toml`, and the `tests/test_config.py:58` pin are **value-unchanged**.
- The precondition triple (`output.streaming=true`, `asr.graceful_stop=false`,
  `cancel.keypress_action="disarm"`) is untouched and continues to hold at defaults.
- The `delivery` comment blocks in `config.py` / `config.toml` now point at this document
  and its verdict (value-neutral comment-only change).
- No daemon / controller / adapter behavior changed. Exit code of the assessment is 0 —
  STAY OPT-IN is recorded data, not an error (G8).

## Outstanding inputs (what a future re-run needs)

1. **Operator**: complete ≥ 3 representative writing sessions and record them in
   `tests/G6_WRITING_SESSIONS.md` (strict format; usable proofread wpm > 110 each;
   attribution required). Automation must never author entries.
2. **Remediate the G3 register rows** (P1.M5 follow-ups): resolve `edit-count-law`
   (warm-up overcount), add visibility instrumentation so `pi-prompt-ghostty`'s
   "not verified" status can flip honestly, and close the browser correction REFUSED
   (chromium `surrounding_text` snapshot lag) gap.
3. **G5**: re-run the failing routes per `tests/G5_TIMING_EVIDENCE.md`'s run commands
   until every claimed route verdict is `pass`.
4. Then re-run `timeout 60 .venv/bin/python tests/g6_assessment.py`; if it prints
   `G6 DECISION: FLIP`, execute the lockstep default flip (config.py + config.toml +
   `tests/test_config.py:58`, same change) per `plan/008_a47116bb2b79/P1M7T1S1/PRP.md`
   (duck-precedent commit `22009a0` pattern). The repo-default lockstep test
   (`tests/test_config_repo_default.py`) is the guard.

## Honesty notes (R.2 discipline)

- No claim here upgrades a NOT VERIFIED item: `pi-prompt-ghostty` counts as unverified
  despite `passed:true`, because its own status says "not verified (visibility
  instrumentation absent)". A passing transport probe never substitutes for G3/G5/G6 rows.
- No per-platform over-claim ("it just works everywhere") is made or supportable from
  single rows.
- All evidence artifacts (verdict jsonls, G2 record, G5 report) are read-only inputs of
  the assessment; none was edited.
