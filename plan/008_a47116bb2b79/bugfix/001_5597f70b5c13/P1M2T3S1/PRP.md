# PRP — P1.M2.T3.S1: Refresh tests/G6_GRADUATION.md from current evidence

## Goal

**Feature Goal**: Re-derive the **G6 graduation decision** (PRD §4.2sexies R.7 G6) from the current
evidence — chiefly the authoritative two-route G5 verdict P1.M2.T2.S3 lands in
`tests/G5_TIMING_EVIDENCE.md` after the S1/S2 BUG-002 remediation — via a **short bounded
file-driven assessment**, and publish the current decision + reason in `tests/G6_GRADUATION.md`
**for P1.M2.T3.S2's README consumption**, preserving the dated historical assessment verbatim.

**Deliverable** (ONE file edited + research artifacts): `tests/G6_GRADUATION.md` — a NEW current
assessment section (new date/@HEAD; verbatim `tests/g6_assessment.py` output; per-condition table
with **condition C re-derived from S3's refreshed G5 evidence** and A/B/D re-derived from the
unchanged registers/sessions file; Decision; Consequence; updated Outstanding inputs) **plus** the
existing 2026-11-23 @ 69952ae block archived verbatim under a dated heading. No README, no config,
no evidence-file edits.

**Success Definition**:
- (a) `timeout 60 .venv/bin/python tests/g6_assessment.py` re-run against the live tree; its
  verbatim output embedded; **both real route entries (im-gtk, pi-ghostty) provably consumed**
  (the C evidence line names both).
- (b) Condition C's row cites S3's refreshed G5 evidence with the per-route verdicts; A/B/D are
  re-derived honestly from their files (registers byte-identical → same verdicts, noted as
  unchanged; `blocked`/not-verified evidence **cannot silently disappear** — verified by a pure
  fixture check of `parse_route_verdicts`).
- (c) The decision text matches the script's mechanical verdict exactly. Expected outcome: **STAY
  OPT-IN** (D is structurally unmet — 0 operator sessions; A/B independently unmet) even if C now
  passes; `output.delivery` stays `"stream-edit"`; no claim is elevated.
- (d) The 2026-11-23 @ 69952ae historical assessment survives verbatim under an archive heading.
- (e) No fake operator sessions, no desktop/service/daemon execution, no default flips, no edits to
  `G5_TIMING_EVIDENCE.md`/`g6_assessment.py`/registers/README.

## User Persona

**Target User**: P1.M2.T3.S2 (the README sync) — consumes this task's decision + reason; and any
maintainer deciding whether bulk-text may graduate. **Use Case**: "After the BUG-002 remediation,
what is G6's current verdict, which conditions moved, and what exactly remains outstanding?"
**Pain Points**: evidence rot — a stale `STAY OPT-IN (…C-g5-timing…)` row that no longer matches
the refreshed G5 file, or worse, a graduated implication without measurement.

## Why

- **The G6 doc must track the evidence, not the calendar.** S3 rewrites the authoritative two-route
  G5 verdict; G6's condition C and Outstanding-work sections are now stale until this refresh runs.
- **Graduation is mechanical and anti-fudge** (bulk_delivery_gate.md §Gate): per-route verdicts,
  fail-closed not-verified markers, `parse_route_verdicts` overwrites duplicate route keys (one
  stale current-looking table silently corrupts the assessment), and "if work does not clear the
  gate, retain opt-in and record an open BUG-002/#13". This task executes that law.
- **README claims inherit from here.** S2 publishes only what this assessment verifies; an honest
  STAY-OPT-IN with the exact blocker is the deliverable, not a flip.

## What

A bounded runbook: precondition-check S3's refreshed G5 file → re-run the assessment script →
verify both routes consumed → parser fail-closed sanity on pure fixture files → rewrite
`tests/G6_GRADUATION.md` (new current block + verbatim archive of the old) → record the
decision/reason for S2.

### Success Criteria

- [ ] Precondition verified: S3's `tests/G5_TIMING_EVIDENCE.md` present with exactly ONE
      parser-current `## Verdict table` carrying both routes (else: blocked — report, don't author).
- [ ] Fresh `g6_assessment.py` run captured verbatim (exit 0 — STAY OPT-IN is data, not error).
- [ ] C row re-derived from the refreshed G5 (per-route verdicts quoted); A/B/D re-derived.
- [ ] Fixture parser check recorded: `blocked` denies; duplicate route keys overwrite (last wins).
- [ ] Historical 2026-11-23 block preserved verbatim under a dated archive heading.
- [ ] `git status --short` == `tests/G6_GRADUATION.md` (+ research artifacts) only.

## All Needed Context

### Context Completeness Check

_Pass._ The research note maps the current G6 doc structure line-by-line, the assessment script's
file-driven inputs and fail-closed semantics, the one-parser-current-table rule, the S3 contract
(what its refreshed G5 looks like), the A/B/D independence argument (only C can move; decision
stays STAY OPT-IN), the fixture-based parser check, and the verified validation commands.

### Documentation & References

```yaml
# MUST READ — the full evidence map + runbook + prohibitions + validation.
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T3S1/research/g6_refresh_evidence_map.md
  why: "§1 the current doc/script/G5 state (verified). §2 the S3 input contract. §3 ★ the
        independence law (only C moves; D structurally unmet → STAY OPT-IN regardless). §4 the
        5-step runbook incl. the fixture parser check. §5 hard prohibitions. §6 validation."

# MUST READ — the gate law (parser semantics, one-current-table, no-graduation-on-timing-alone).
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  section: "## Gate and evidence handoff"
  critical: "parse_route_verdicts overwrites duplicate route keys; exactly one parser-compatible
             current table; blocked for unverified; G6/README must not imply operator acceptance,
             broaden G3, fill WRITING_SESSIONS, or graduate on timing alone."

# MUST READ — the file being edited (structure to mirror + archive).
- file: tests/G6_GRADUATION.md
  why: "Mirror its section shapes (Verdict block verbatim / per-condition table / Decision /
        Consequence / Outstanding / Honesty notes). The 2026-11-23 block (lines ~1-79) becomes the
        verbatim archive; the new assessment replaces it as current."

# MUST READ — the mechanical verdict engine (inputs, fail-closed, exit-0 semantics).
- file: tests/g6_assessment.py
  why: "File-driven only (jsonl registers → A/B; tests/G5_TIMING_EVIDENCE.md → C via
        parse_route_verdicts/assess_g5_timing; tests/G6_WRITING_SESSIONS.md → D). Do NOT edit it."

# MUST READ — the parallel CONTRACT producing the C input.
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S3/PRP.md
  why: "S3 refreshes G5_TIMING_EVIDENCE.md: one parser-current table, both routes
        pass|fail|blocked, qualification provenance, archived A-B tables, BUG-002/#13 status.
        Consume its outcome; do not duplicate (never edit G5 yourself)."
  critical: "If S3's refresh is absent at impl time (no current table / missing route), this task
             is BLOCKED — report; do not author or backfill evidence."

# CONTEXT — the upstream bug context (why C was unmet; what remediation happened).
- docfile: PRD.md  # bugfix h3.1 (BUG-002) + h2.5 recommendations
  why: "The baseline C failure (57-word backlog, sentence-end dumps, 12.6 s median, stabilized-only
        callback) and the honest record/opt-in mitigation that this refresh must preserve."
```

### Current Codebase tree (relevant slice)

```bash
tests/
├── G6_GRADUATION.md        # EDIT (this task): new current assessment + verbatim dated archive
├── g6_assessment.py        # READ-ONLY: run it; fixture-test parse_route_verdicts via importlib
├── G5_TIMING_EVIDENCE.md   # READ-ONLY (S3's output — the C input)
└── G6_WRITING_SESSIONS.md  # READ-ONLY (D; operator-authored only — NEVER touched)
plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/
├── bulk_delivery_gate.md   # READ (§Gate law)
├── pi_row_verdicts.jsonl   # READ-ONLY (A/B inputs)
└── editor_browser_row_verdicts.jsonl  # READ-ONLY (A/B inputs)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ONLY C CAN MOVE. A/B read unchanged registers; D needs operator sessions (0 on
#   record, and automation must NEVER author entries). So the decision stays STAY OPT-IN even if
#   S3's C passes — do not "helpfully" reword toward graduation.
# CRITICAL #2 — THE PARSER OVERWRITES DUPLICATE ROUTE KEYS. The doc refresh must not leave any
#   second current-looking verdict table anywhere the parser scans; historical tables live only
#   under archive headers (in G5 — S3's job — and inside G6_GRADUATION.md's dated archive block,
#   which the parser does not read but keep clearly dated anyway).
# CRITICAL #3 — FAIL-CLOSED MARKERS DENY: "not verified"/"insert-only (correction REFUSED…)"/
#   blocked rows deny verification even with pass:true flags. Quote them as-is; never summarize
#   them into passes.
# CRITICAL #4 — EXIT 0 FOR STAY OPT-IN (recorded data, not an error). Do not treat a non-FLIP
#   exit as failure or "fix" it.
# CRITICAL #5 — FIXTURES ONLY for parser-behavior checks: write a tmpdir fixture table and call
#   parse_route_verdicts on that text (importlib from the file path — tests/ is not a package);
#   NEVER mutate the real G5/registers to test the parser.
# CRITICAL #6 — Full paths (.venv/bin/python; zsh aliases); every command under GNU timeout;
#   the assessment is file-driven — no daemon, no desktop, no service is touched.
```

## Implementation Blueprint

### Data models and structure

None (documentation + a mechanical re-assessment; the "model" is the G6 doc's section shapes).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PRECONDITION — verify S3's refreshed evidence
  - grep -c "^## Verdict table" tests/G5_TIMING_EVIDENCE.md  → exactly 1
  - Confirm both routes in that table (grep "| im-gtk |\|| pi-ghostty |").
  - If absent/duplicated/missing a route → STOP; report blocked (never author evidence).

Task 2: RE-RUN the assessment (bounded, file-driven)
  - timeout 60 .venv/bin/python tests/g6_assessment.py | tee /tmp/g6_current.txt; echo "rc=$?"
  - Confirm the C evidence line names BOTH routes (both entries consumed).
  - Capture the verbatim verdict block + the G6 DECISION line + exit code (expect 0).

Task 3: PARSER SANITY on pure fixtures (the cannot-silently-disappear check)
  - tmpdir fixture table (pass/fail/blocked rows + a duplicate route key); run
    parse_route_verdicts over the fixture TEXT via importlib.util.spec_from_file_location;
    assert: blocked denies the route; duplicate key → last row wins (documents why
    exactly-one-current-table is load-bearing). Record in research/. Never touch real files.

Task 4: EDIT tests/G6_GRADUATION.md — new current assessment + archive
  - ARCHIVE the entire existing 2026-11-23 @ 69952ae block verbatim under
    "## Historical assessment — 2026-11-23 @ 69952ae (P1.M7.T1.S1)".
  - WRITE the new current assessment mirroring the same section shapes: meta (date/@HEAD,
    P1.M2.T3.S1); Verdict block = Task 2's verbatim output; per-condition table with C re-derived
    from S3's G5 (quote per-route verdicts + the exact blocker/pass numbers), A/B re-derived from
    the registers (note "registers unchanged since 2026-11-23" if byte-identical), D unchanged
    (0 sessions); Decision; Consequence executed (delivery stays stream-edit; precondition triple
    untouched; assessment exit 0); Outstanding inputs updated (S3's exact blocker wording if C
    still fails; drop stale items that S3 closed); Honesty notes.
  - RECORD (inside the doc) the decision + one-paragraph reason for P1.M2.T3.S2's README use.

Task 5: VALIDATE — research §6 commands (grep both routes in the captured output; one current +
  one archived G6 DECISION line; git status == G6_GRADUATION.md + research only).
```

### Implementation Patterns & Key Details

```bash
# The bounded re-assessment (file-driven; no service touched):
timeout 60 .venv/bin/python tests/g6_assessment.py | tee /tmp/g6_current.txt; echo "rc=$?"
grep -o "im-gtk\|pi-ghostty" /tmp/g6_current.txt | sort -u     # BOTH must appear (consumed)

# Fixture parser check (pure file inputs; never the real evidence):
.venv/bin/python - <<'EOF'
import importlib.util, pathlib, tempfile
spec = importlib.util.spec_from_file_location("g6a", "tests/g6_assessment.py")
m = importlib.util.util if False else importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
tbl = "| im-gtk | **blocked** (no frame basis) |\n| pi-ghostty | **fail** (median) |\n| im-gtk | **pass** |"
print(m.parse_route_verdicts(tbl))   # expect: im-gtk overwritten to pass (dup), pi-ghostty fail
EOF
# (Adapt to parse_route_verdicts' real signature — read it first; it is a pure function over table text.)
```

### Integration Points

```yaml
CONSUMED (read-only): S3's tests/G5_TIMING_EVIDENCE.md (condition C input); pi_row_verdicts.jsonl +
  editor_browser_row_verdicts.jsonl (A/B); tests/G6_WRITING_SESSIONS.md (D); g6_assessment.py (run only).
PRODUCED: refreshed tests/G6_GRADUATION.md (current decision + reason + archived history); research notes.
DOWNSTREAM: P1.M2.T3.S2 (README sync) consumes the decision/reason verbatim — no broader claims.
DO NOT TOUCH: README.md (S2), G5_TIMING_EVIDENCE.md / g6_assessment.py / registers / WRITING_SESSIONS,
  any config or default, PRD.md/tasks.json/prd_snapshot, any voice_typing/ source.
```

## Validation Loop

### Level 1: The assessment re-run (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python tests/g6_assessment.py | tee /tmp/g6_current.txt; echo "rc=$?"
grep -o "im-gtk\|pi-ghostty" /tmp/g6_current.txt | sort -u   # → both routes
grep "G6 DECISION" /tmp/g6_current.txt                        # the mechanical verdict
# Expected: exit 0; both routes consumed; decision STAY OPT-IN (A/B/D unmet) with C reflecting S3.
```

### Level 2: Doc integrity

```bash
grep -n "G6 DECISION" tests/G6_GRADUATION.md        # exactly 2: current + dated archive
grep -n "Historical assessment — 2026-11-23" tests/G6_GRADUATION.md
grep -c "^## Verdict table" tests/G5_TIMING_EVIDENCE.md   # still exactly 1 (untouched)
git status --short                                  # ONLY tests/G6_GRADUATION.md (+ research)
```

### Level 3: No-regression sanity (doc-only edit)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_config.py -q   # delivery default pin untouched
```

### Level 4: Creative & Domain-Specific

Not applicable — the assessment is file-driven by design; NO desktop, daemon, or live service is
exercised (and none may be).

## Final Validation Checklist

### Technical Validation
- [ ] Assessment re-run captured verbatim; exit 0; both routes provably consumed.
- [ ] Fixture parser check recorded (blocked denies; duplicate keys overwrite).
- [ ] Exactly one G6 DECISION as current + the 2026-11-23 one archived verbatim.

### Feature Validation
- [ ] Condition C cites S3's refreshed per-route verdicts; A/B/D re-derived honestly.
- [ ] Decision text == the script's mechanical verdict (no elevation, no imputed passes).
- [ ] Outstanding inputs updated (S3's exact blocker if C fails; stale items dropped).

### Code Quality / Scope
- [ ] `git status --short` == `tests/G6_GRADUATION.md` + research only.
- [ ] No edits to G5/g6_assessment.py/registers/WRITING_SESSIONS/README/config/source.
- [ ] No operator-session entries authored; no desktop/service touched; delivery stays opt-in.

---

## Anti-Patterns to Avoid

- ❌ Don't graduate or soften the verdict because C improved — A/B/D are independently unmet; the
  decision is the script's, verbatim.
- ❌ Don't author, backfill, or "summarize" evidence — a missing route/table means BLOCKED, reported.
- ❌ Don't summarize fail-closed markers ("not verified", "correction REFUSED", blocked) into passes.
- ❌ Don't leave a second parser-current-looking verdict table anywhere.
- ❌ Don't touch G6_WRITING_SESSIONS.md (operator-authored only) or the README (S2 owns it).
- ❌ Don't edit g6_assessment.py/G5/registers to make the output "look right".
- ❌ Don't test the parser against the real evidence files — fixtures only.
- ❌ Don't use bare python/pytest (zsh aliases); every command under GNU timeout.

---

## Confidence Score

**9/10**. The assessment is mechanical and file-driven (script + one-edit doc surgery with a
mirrored structure and a verbatim archive rule); the independence argument (only C moves; STAY
OPT-IN regardless) and the parser's duplicate-overwrite/fail-closed semantics are verified from
the gate doc and the script header. Residual risk (−1): S3's refresh must have landed with exactly
one parser-current table (hard precondition, checked first) and `parse_route_verdicts`' exact
signature must be read before the fixture check.
