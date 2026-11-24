# Research — G6 graduation refresh from current evidence (bugfix P1.M2.T3.S1)

## §1. What exists now (verified live)

- `tests/G6_GRADUATION.md` (79 lines): assessed **2026-11-23 @ HEAD 69952ae** (P1.M7.T1.S1).
  Structure: title/meta → "## Verdict block (verbatim tests/g6_assessment.py output)" (embeds route
  evidence lines + `G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing,
  D-sessions)`) → "## Per-condition record" table (| # | Condition | Verdict | Evidence | Detail |)
  with rows A/B/C/D → "## Decision" + "### Consequence executed" → "## Outstanding inputs" (1-4) →
  "## Honesty notes". All four conditions **unmet**.
- `tests/g6_assessment.py`: the mechanical verdict engine. Inputs are COMMITTED FILES ONLY (no
  network, no daemons): `plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl` (24 rows) +
  `editor_browser_row_verdicts.jsonl` (17 rows) → conditions A/B; `tests/G5_TIMING_EVIDENCE.md` →
  condition C (`parse_route_verdicts` scans its verdict tables, **overwrites duplicate route keys**);
  `tests/G6_WRITING_SESSIONS.md` → condition D. `assess_g5_timing` applies the per-route bars.
  Fail-closed: FLAGLESS "not verified"/"insert-only (correction REFUSED…)" markers DENY verification
  even when a pass flag is true. Exit 0 for STAY OPT-IN (recorded data, not an error — G8).
- `tests/G5_TIMING_EVIDENCE.md` current "## Verdict table" (the ONE parser-current table, @14):
  `im-gtk | **fail** (backlog sustained; counts 20/0 < 100 …)` and `pi-ghostty | **fail**
  (speech→visible 12.6 s median; …)`. Historical/A-B tables must live under headers the parser
  cannot read as current.
- `tests/G6_WRITING_SESSIONS.md`: ships as an empty operator-authored template; 0 valid sessions.
  **Automation must NEVER author entries** (R.2; the doc's own Outstanding #1).

## §2. What the parallel S3 refresh changes (the input this task consumes)

P1.M2.T2.S3 (implementing now) rewrites `tests/G5_TIMING_EVIDENCE.md` into the authoritative
current two-route verdict after the S1/S2 remediation: exactly ONE parser-compatible `## Verdict
table` with BOTH routes (`im-gtk`, `pi-ghostty`), each `pass | fail(reason) | blocked(reason)`,
plus a "## Qualification run (P1.M2.T2.S3)" provenance section and archived historical/A-B tables.
Per its PRP: S3 records before/after `parse_route_verdicts` output; a verified source does NOT
change default delivery; on failure BUG-002/#13 stays open with the exact blocker. Its success (d):
opt-in retained, no G6 edits (G6 is OURS).

## §3. The independence law (the contract's RESEARCH NOTE)

A (G3 rows) and B (integrity) come from the jsonl registers — NOT touched by this changeset unless
a sibling explicitly re-ran G3 rows (none did; P1.M1.* touched only tests/config). D needs operator
sessions that cannot exist yet. So **only C can move** this round; the DECISION therefore stays
STAY-OPT-IN regardless of S3's outcome unless A+B+D also verify (they won't — D is structurally
unmet). The refresh must still re-derive ALL four rows from the live files (not copy stale text):
if the registers are byte-identical, the A/B verdicts repeat with "unchanged" noted in Detail.

## §4. The task's shape (bounded re-assessment + Mode B doc surgery)

1. PRECONDITION CHECK: S3's refreshed G5 file present; exactly one parser-current table; both
   routes present. If absent → blocked; report (do not author evidence).
2. Run `timeout 60 .venv/bin/python tests/g6_assessment.py`; capture the verbatim output + exit
   code. Confirm the C-condition evidence line names BOTH routes (both entries consumed).
3. Parser sanity on PURE FIXTURES (file inputs only — never mutate the real G5): a tmpdir fixture
   table with `pass`/`fail`/`blocked` rows → parse_route_verdicts via importlib → assert blocked
   denies C, a duplicate route key overwrites (last wins) — documenting why exactly-one-table is
   load-bearing. This is the "rejected/blocked evidence cannot silently disappear" check.
4. EDIT `tests/G6_GRADUATION.md`: new current assessment (new date/@HEAD; verbatim new verdict
   block; per-condition table with C citing the S3-refreshed evidence + per-route verdicts;
   re-derived A/B/D; Decision; Consequence — delivery stays stream-edit, precondition triple
   untouched; Outstanding inputs updated to S3's exact blocker wording if C still fails) AND
   preserve the 2026-11-23 block verbatim under a dated archive heading (e.g.
   "## Historical assessment — 2026-11-23 @ 69952ae (P1.M7.T1.S1)").
5. Record the decision + one-paragraph reason for P1.M2.T3.S2's README consumption (inside the
   doc — S2 owns README).

## §5. Hard prohibitions (contract + gate law)

No fake operator sessions (G6_WRITING_SESSIONS.md untouched); no desktop/service/daemon execution
(the assessment is file-driven; g6_assessment.py touches no live service); no delivery-default or
config flips (graduation is G6's mechanical verdict — FLIP requires ALL four verified; not
possible this round); no elevating G3/integrity claims (fail-closed markers deny); no edits to
G5_TIMING_EVIDENCE.md / g6_assessment.py / registers (S3 + prior tasks own them); no README (S2).

## §6. Validation (verified paths/commands)

```bash
timeout 60 .venv/bin/python tests/g6_assessment.py | tee /tmp/g6_out.txt   # exit 0 expected (STAY OPT-IN = data)
grep -c "im-gtk\|pi-ghostty" /tmp/g6_out.txt                                # both routes named in evidence lines
grep -n "G6 DECISION" tests/G6_GRADUATION.md                                # one current + one archived decision
git status --short                                                          # ONLY tests/G6_GRADUATION.md (+ research)
```
Full paths (.venv/bin/python; zsh aliases). Fast suites unaffected (doc-only edit); optional
`timeout 300 .venv/bin/python -m pytest tests/test_config.py -q` sanity (default pin untouched).
