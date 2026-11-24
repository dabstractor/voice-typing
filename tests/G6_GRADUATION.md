# G6 GRADUATION ASSESSMENT — bulk-text delivery (PRD §4.2sexies R.7)

- **Item**: P1.M2.T3.S1 (bugfix `001_5597f70b5c13`) — refresh the G6 gate decision from
  current evidence (post BUG-002 remediation, P1.M2.T2.S1/S2/S3).
- **Assessed**: 2026-11-24 @ HEAD `2909e03`.
- **Method**: mechanically derived by `tests/g6_assessment.py` (pure stdlib; reads the
  committed evidence files only — no desktop, no CUDA, no service contact). The
  per-condition block below is the script's verbatim output at this HEAD; a re-run
  re-derives it.
- **Environment provenance** (from the evidence files; not re-measured here): the
  condition-C input is P1.M2.T2.S3's qualification round (2026-11-24, HEAD `2909e03`,
  kernel 7.3.5-arch1-1) on the production selection — stabilized + S1's prompt dispatch +
  S2's 0.05 s bulk cadence, 20 measured replays per route. The condition A/B registers are
  byte-identical to the 2026-11-23 assessment (empty `git diff 69952ae..HEAD` over
  `plan/008_a47116bb2b79/architecture/`), so their recorded environment (kernel
  7.2.7-arch1-1 · sway 1.12 · Ghostty 1.4.0-arch2 · voice-typing pi bridge 1.0.2 ·
  node v26.13.1) still stands for them.
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
| A | Verified G3 rows: pi prompt in Ghostty + graphical editor + browser text field (insert AND correct) | **unmet** | `plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl` (24 rows), `editor_browser_row_verdicts.jsonl` (17 rows) | **unchanged since 2026-11-23** — both registers are byte-identical (empty `git diff 69952ae..HEAD`), so the verdict re-derives identically: failed row `edit-count-law` (status "warm-up overcount"); `pi-prompt-ghostty` passed:true but status "**not verified** (visibility instrumentation absent)"; browser class rows read "insert-only (correction REFUSED…)" — browser correction is **not** verified. All required row classes remain present. |
| B | Zero observed integrity failures | **unmet** | same registers + `plan/008_a47116bb2b79/architecture/g2_gate_record.md` | **unchanged since 2026-11-23**: the G2 record itself is clean (no ❌), but the `edit-count-law` register row (passed:false, "warm-up overcount") is still a failed row, so the zero-failures condition still does not hold. |
| C | G5 per-route timing evidence passing | **unmet** | `tests/G5_TIMING_EVIDENCE.md` — the ONE parser-current `## Verdict table`, refreshed by P1.M2.T2.S3's qualification round (2026-11-24 @ `2909e03`) | **both routes still fail** on the production selection (stabilized + S1 prompt dispatch + S2 0.05 s bulk cadence), 20 replays each — verdict rows quoted verbatim: `im-gtk | **fail** (counts 4/0 < 100; backlog sustained 57; correction p95 unexercised; frame bars unverified — field change-log proxy)`; `pi-ghostty | **fail** (speech→visible 6714.0 ms median; sentence-end dump; backlog sustained 57; counts 14/14 < 100; unchanged⇒zero-edits breached)`. pi's speech→visible median improved 7786.2 → 6714.0 ms (S2's cadence fix, −14%) but remains ~13× the 500 ms bar, and on the paint-qualified frame basis its ready→frame bars now measure real visible change and fail (11.3 s/13.2 s). The assessment consumed BOTH route entries (its evidence lines name `im-gtk` and `pi-ghostty`). |
| D | ≥ 3 operator writing sessions, usable proofread wpm > 110 each | **unmet** | `tests/G6_WRITING_SESSIONS.md` | 0 valid sessions on record — **structurally unchanged**: the file now exists as the operator-authored template (created after 69952ae: rules, fenced format spec, "*(none on record)*"), but it still carries zero entries. Entries are **operator-authored only** (R.2); automation must never author, seed, or "example-fill" one. |

## Decision

**`G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)`**

The decision is the script's mechanical verdict, verbatim. Condition C moved onto fresh
evidence (S3's qualification round) but still fails on both routes; A/B re-derive unchanged
from byte-identical registers; D is structurally unmet (0 operator sessions). Graduation
requires ALL four verified; none moved to verified, so nothing flips.

### Consequence executed

- `output.delivery` stays `"stream-edit"` everywhere: `voice_typing/config.py` default,
  `config.toml`, and the `tests/test_config.py:58` pin are **value-unchanged** (this task
  edited none of them).
- The precondition triple (`output.streaming=true`, `asr.graceful_stop=false`,
  `cancel.keypress_action="disarm"`) is untouched and continues to hold at defaults.
- No evidence file was edited: `G5_TIMING_EVIDENCE.md` (S3's output), `g6_assessment.py`,
  both verdict registers, `g2_gate_record.md`, and `G6_WRITING_SESSIONS.md` were consumed
  read-only. No desktop, service, or daemon was executed (the assessment is file-driven).
- Exit code of the assessment is 0 — STAY OPT-IN is recorded data, not an error (G8).
- Parser fail-closed discipline was re-verified on pure fixtures (task research note
  `fixture_parser_check.txt`): a `blocked` route row denies condition C; a duplicate route
  key overwrites (last row wins) — which is exactly why G5 must keep ONE parser-current
  verdict table; and absent evidence is `not-run`, never a pass.

## Record for P1.M2.T3.S2 (README consumption)

**Decision: STAY OPT-IN — bulk-text delivery remains opt-in; default stays `stream-edit`.**
Reason (one paragraph): the mechanical G6 gate is unmet on all four independent conditions
at HEAD `2909e03`. Timing (C) was re-measured after the BUG-002 remediation (P1.M2.T2.S3
qualification, 2026-11-24) and both routes still fail — pi-ghostty: speech→visible 6714 ms
median vs the 500 ms bar, sentence-end dump, 57-word sustained backlog, 14/14 count floors,
ready→frame 11.3 s/13.2 s, and a first-ever unchanged⇒zero-edits breach; im-gtk: 4/0
insert/correct counts vs the 100/100 floors with a sustained 57-word backlog and unverified
frame bars. The G3 matrix (A) and integrity (B) registers are byte-identical to 2026-11-23
and remain unmet (`edit-count-law` failed; pi-prompt-ghostty "not verified"; browser
correction REFUSED). Operator sessions (D) are 0-on-record and may only be authored by the
operator. BUG-002 / PRD acceptance #13 remain OPEN. README must reflect exactly this
verified scope: no operator acceptance implied, no G3 broadening, no WRITING_SESSIONS
filling, no graduation on timing alone.

## Outstanding inputs (what a future re-run needs)

1. **Operator**: complete ≥ 3 representative writing sessions and record them in
   `tests/G6_WRITING_SESSIONS.md` (strict format; usable proofread wpm > 110 each;
   attribution required). Automation must never author entries. *(unchanged)*
2. **G3 register rows** (P1.M5 follow-ups; registers untouched this round, still exactly
   as assessed 2026-11-23): resolve `edit-count-law` (warm-up overcount), add visibility
   instrumentation so `pi-prompt-ghostty`'s "not verified" status can flip honestly, and
   close the browser correction REFUSED (chromium `surrounding_text` snapshot lag) gap.
3. **G5 — BUG-002 / PRD acceptance #13: OPEN** after S3's qualification round (2026-11-24,
   HEAD `2909e03`); exact blockers quoted from its Open items: *im-gtk* — count floors
   4/0 ≪ 100/100 with a sustained 57-word backlog (the partial stream still collapses to
   ~4 updates per replay; the frame basis remains the read-poll proxy so the frame bars
   stay unverified); *pi-ghostty* — speech→visible 6714.0 ms median vs the 500 ms bar,
   sentence-end dump, sustained 57-word backlog, count floors 14/14, ready→frame
   11.3 s/13.2 s on the paint-qualified basis, and a first-ever breach of
   unchanged⇒zero-edits. Also open per G5: the im-gtk plain-vs-stabilized A/B pair remains
   unrun after four sanctioned attempts (route-harness defect, worth its own look), and the
   visibility matcher's positional assumptions likely inflate pi's speech→visible (a
   per-op diff-based matcher is the named follow-up). Neither open item affects the
   backlog/dump verdicts.
4. Then re-run `timeout 60 .venv/bin/python tests/g6_assessment.py`; if it prints
   `G6 DECISION: FLIP`, execute the lockstep default flip (config.py + config.toml +
   `tests/test_config.py:58`, same change) per `plan/008_a47116bb2b79/P1M7T1S1/PRP.md`
   (duck-precedent commit `22009a0` pattern). The repo-default lockstep test
   (`tests/test_config_repo_default.py`) is the guard.

## Honesty notes (R.2 discipline)

- The C refresh does NOT soften the prior verdict: both routes fail again, now on a larger
  production selection and a paint-qualified frame basis. Fail-closed markers are quoted
  verbatim from the evidence ("not verified", "insert-only (correction REFUSED…)",
  `**fail**` route rows) — none is summarized into a pass, and blocked/unverified evidence
  cannot silently disappear (fixture check recorded in the task research dir).
- No claim here upgrades a NOT VERIFIED item: `pi-prompt-ghostty` still counts as
  unverified despite `passed:true`, because its own status says "not verified". A passing
  transport probe never substitutes for G3/G5/G6 rows.
- The decision text is the script's, verbatim; this refresh elevated no claim, flipped no
  default, and authored no operator-session entry.
- All evidence artifacts (verdict jsonls, G2 record, G5 report, sessions file) are
  read-only inputs of the assessment; none was edited.

---

## Historical assessment — 2026-11-23 @ 69952ae (P1.M7.T1.S1)

*(preserved verbatim from the previous revision of this document; superseded by the
current assessment above — kept for the decision trail)*

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
