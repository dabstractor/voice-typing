name: "P1.M3.T1.S2 — Update tests/ACCEPTANCE.md criterion #10 for lite_post_speech_silence_duration"
description: |

---

## Goal

**Feature Goal**: Make the criterion #10 row in `tests/ACCEPTANCE.md` (the human-readable record of
PRD §7 acceptance evidence) mirror the updated PRD §7 criterion #10 by documenting the landed
`asr.lite_post_speech_silence_duration` feature (config field P1.M1.T1.S1 + daemon wiring
P1.M2.T1.S1). The row's **Criterion** column must add the silence-gate clause, and the **Evidence**
column must cite the `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` unit test as proof the
override is wired.

**Deliverable**: A single edited markdown-table row (line 39 of `tests/ACCEPTANCE.md`) — two
non-overlapping substring edits, both inside that one row. No code, no test run, no other file.

**Success Definition**: 
- The Criterion column of row #10 contains the phrase about lite using its own shorter
  `post_speech_silence_duration` and the §4.2ter silence-gate insight (mirrors PRD §7 #10 text
  updated in commit `a66b9d4`).
- The Evidence column of row #10 names the config field (`asr.lite_post_speech_silence_duration`,
  default `0.5`), cites that it is wired in `cfg_to_kwargs`, and references the unit test
  `test_cfg_to_kwargs_lite_uses_shorter_silence_duration`.
- The Status column stays `**PASS**`.
- `git status` shows ONLY `tests/ACCEPTANCE.md` modified — nothing else.

## User Persona

**Target User**: The maintainer / reviewer reading the acceptance evidence to confirm PRD §7 is met.

**Use Case**: "I want to verify the lite silence-gate feature is implemented and accepted, by reading
the criterion #10 row and its evidence, without re-deriving it from the PRD."

**Pain Points Addressed**: The current row omits the silence-gate requirement entirely, so a reader
cannot tell the feature exists — even though it is implemented and unit-tested.

## Why

- This is the **Mode B changeset-level documentation sync** for `lite_post_speech_silence_duration`
  (the item explicitly states this — DOCS: Mode B).
- PRD §7 criterion #10 was updated in commit `a66b9d4 "Refine Lite mode latency via silence gate"` to
  add the clause: *"lite uses its own shorter `post_speech_silence_duration` (the silence gate is the
  perceived bottleneck — §4.2ter) so it is observably snappier end-to-end, not just faster at
  transcription."* `tests/ACCEPTANCE.md` is the human-readable mirror of PRD §7, so it must track that
  update.
- Keeps the acceptance record internally consistent (the PRD says X; the evidence doc must show X is
  met). This is the final task of the P1 "Lite Mode Silence Gate" milestone — it closes the loop on a
  feature whose code + config + tests + README (P1.M3.T1.S1) are already landed.

## What

A markdown-only edit to **one table row** (criterion #10, currently line 39 of
`tests/ACCEPTANCE.md`). Two non-overlapping substring edits inside that row:

1. **Criterion column** — insert the silence-gate clause before the existing trailing
   "both modes honor the graceful drain".
2. **Evidence column** — append a "Lite silence gate" note citing the config field, the `cfg_to_kwargs`
   wiring, and the unit test, before the existing trailing "(Evidence block below.)".

### Success Criteria

- [ ] Criterion #10 row's Criterion column mentions `lite_post_speech_silence_duration` (default
      `0.5`) and the §4.2ter silence-gate-as-perceived-bottleneck insight.
- [ ] Criterion #10 row's Evidence column references
      `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` and notes the field is wired in
      `cfg_to_kwargs`.
- [ ] Status column remains `**PASS**`.
- [ ] No other row, no other criterion (1–9), and no fenced `=== ACCEPTANCE EVIDENCE ===` block is
      touched.
- [ ] `git status` shows only `tests/ACCEPTANCE.md` modified.

## All Needed Context

### Context Completeness Check

_If someone knew nothing about this codebase, would they have everything needed to implement this
successfully?_ **Yes** — this PRP gives the exact file, the exact line, byte-exact `oldText`/`newText`
anchors (verified unique in-file), the verbatim text to add, and the precise do-not-touch boundaries.
The whole task is editing one markdown row; no code, no test framework, no GPU.

### Documentation & References

```yaml
# MUST READ — include these in your context window before editing
- url: https://github.com/your-org/voice-typing/blob/a66b9d4/PRD.md#L7
  why: commit a66b9d4 "Refine Lite mode latency via silence gate" is the canonical source of the
       PRD §7 criterion #10 text this row must mirror. The new clause to mirror is verbatim:
       "lite uses its own shorter post_speech_silence_duration (the silence gate is the perceived
       bottleneck — §4.2ter) so it is observably snappier end-to-end, not just faster at transcription"
  critical: The row's Criterion column must REPRODUCE the substance of this clause (you may compress
            slightly for table width, but the silence-gate / §4.2ter / "observably snappier end-to-end"
            framing must survive).

- file: tests/ACCEPTANCE.md
  why: THE FILE TO EDIT. The criterion #10 row is currently line 39 (a single long markdown line).
       The table has columns: # | Criterion (PRD §7) | Status | Evidence.
  pattern: Each row is one physical markdown line. Edit via substring replacement on that one line.
  gotcha: The row uses NON-ASCII characters (em-dash —, ≥) in the existing text. The two chosen
          oldText anchors below are ASCII-clean (no em-dash/≥ inside the anchor itself) so they match
          byte-for-byte; the newText INTRODUCES em-dashes and backticks (markdown renders fine). Do
          NOT copy-paste an em-dash from this PRP into an oldText anchor that must match ASCII.

- file: voice_typing/config.py  (line 59)  # READ-ONLY reference — the feature being documented
  why: The config field this row cites: `lite_post_speech_silence_duration: float = 0.5` with the
       comment "PRD §4.2ter: lite-mode silence threshold — the silence gate, not the model, is the
       perceived-latency bottleneck".
  pattern: evidence citation should name this field + default 0.5.

- file: voice_typing/daemon.py  (line 213)  # READ-ONLY reference
  why: The wiring this row cites — inside `cfg_to_kwargs(..., lite=True)`:
       `kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration`
       (the lite override of the normal-mode value set in the common block).
  pattern: evidence should say the field is "wired in cfg_to_kwargs (lite path)".

- file: tests/test_daemon.py  (line 216)  # READ-ONLY reference — the unit test evidence
  why: `def test_cfg_to_kwargs_lite_uses_shorter_silence_duration(cfg, monkeypatch):` — the unit test
       that PROVES the override is wired (asserts lite kwargs carry the shorter silence duration).
       VERIFIED PASSING: `.venv/bin/python -m pytest tests/test_daemon.py -k
       "test_cfg_to_kwargs_lite_uses_shorter_silence_duration or test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal" -q`
       → `2 passed`. Cite this test name in the Evidence column.

- file: PRD.md  (§4.2ter, the "silence gate" latency note)  # READ-ONLY — the rationale to reference
  why: The PRD's load-bearing insight to reference in the Evidence note: "the silence gate, not the
       model, is the perceived-latency bottleneck" — lite overrides post_speech_silence_duration
       (0.5 vs normal 0.6) so stop→text latency drops from ~1.6 s to ~0.6 s.
```

### Current Codebase tree (run `tree` in the root of the project)

Only the path under `tests/` is relevant to this task:

```bash
tests/
├── ACCEPTANCE.md        # ← THE ONLY FILE TO EDIT (criterion #10 row = line 39)
├── e2e_virtual_mic.sh
├── make_test_audio.sh
├── test_daemon.py       # contains the unit test cited as evidence (line 216)
├── test_feed_audio.py
├── test_idle_and_gpu.sh # the GPU integration test — DO NOT run (5-8 min) — evidence block is OUT OF SCOPE
└── test_textproc.py
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
# NO files added. ONE file modified:
tests/
└── ACCEPTANCE.md        # criterion #10 row (line 39): Criterion col + Evidence col updated
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: tests/ACCEPTANCE.md row #10 is a SINGLE physical markdown line (line 39).
# It is very long. Edit it with SUBSTRING REPLACEMENT (edit tool), NOT a full-line rewrite — a
# full-line oldText would be ~900 chars and fragile. Use the two small ASCII anchors below.

# CRITICAL: The row already contains em-dash (—) and ≥ in its EXISTING text. Do NOT include any
# non-ASCII char in an oldText anchor unless you copy it byte-exact from the file. The anchors below
# are chosen to be ASCII-only so they match deterministically.

# CRITICAL: This is a Mode B doc sync — DO NOT regenerate the fenced `=== ACCEPTANCE EVIDENCE ===`
# block (lines ~62-110). That needs the ~5-8 min GPU `test_idle_and_gpu.sh` run; the item explicitly
# forbids it (clause (c)). Only the criterion #10 ROW (line 39) is in scope.

# CRITICAL: README.md is owned by the PARALLEL sibling task P1.M3.T1.S1 — do NOT touch it.
# config.py / config.toml / daemon.py / test_daemon.py are already landed (P1.M1.T1.S1 +
# P1.M2.T1.S1) — this task only DOCUMENTS them, never edits them.
```

## Implementation Blueprint

### Data models and structure

None. This is a markdown documentation edit — no data models, no code, no types.

### Implementation Tasks (ordered by dependencies)

There is exactly ONE task: edit the criterion #10 row (line 39) of `tests/ACCEPTANCE.md` with two
non-overlapping substring edits. Both anchors are **verified unique** in the file (1 match each) and
**ASCII-clean** in `oldText`.

```yaml
Task 1: MODIFY tests/ACCEPTANCE.md  (criterion #10 row = line 39, two substring edits)

  Edit A — Criterion column: INSERT the silence-gate clause.
    - oldText: "both modes honor the graceful drain | **PASS** |"
      # (UNIQUE in-file: appears only in row #10; row #10 is the only place "graceful drain" meets
      #  "| **PASS** |".)
    - newText: "lite uses its own shorter `post_speech_silence_duration`
      (`asr.lite_post_speech_silence_duration`, default `0.5` — the silence gate, not the model, is
      the perceived-latency bottleneck, §4.2ter) so it is observably snappier end-to-end, not just
      faster at transcription; both modes honor the graceful drain | **PASS** |"
    - NAMING/PLACEMENT: insert the clause INTO the Criterion (2nd) column, immediately before the
      existing trailing "both modes honor the graceful drain". Keeps the column's semicolon-delimited
      clause list.
    - WHY: mirrors the PRD §7 #10 clause added in commit a66b9d4.

  Edit B — Evidence column: APPEND a "Lite silence gate" note.
    - oldText: "applies identically in lite). (Evidence block below.) |"
      # (UNIQUE in-file: row #10 ends with this exact tail.)
    - newText: "applies identically in lite). **Lite silence gate:** lite's
      `post_speech_silence_duration` is overridden in `cfg_to_kwargs` (daemon.py, lite path) by
      `asr.lite_post_speech_silence_duration` (config.py, default `0.5`, vs normal `0.6` — PRD §4.2ter:
      the silence gate, not the model, is the perceived-latency bottleneck). Unit-test evidence:
      `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` (tests/test_daemon.py) — PASSES
      (`.venv/bin/python -m pytest tests/test_daemon.py -k 'test_cfg_to_kwargs_lite_uses_shorter_silence_duration' -q`
      → 1 passed). (Evidence block below.) |"
    - NAMING/PLACEMENT: append INTO the Evidence (4th) column, immediately before the existing
      trailing "(Evidence block below.)". Keep that trailing marker + the closing `|`.
    - WHY: documents the landed implementation + cites the unit test as evidence (item clause (b)).

  Status column: NO CHANGE (it is already `**PASS**` and the feature is implemented — item clause (a)).
```

### Implementation Patterns & Key Details

```python
# Pattern: substring replacement on a single long markdown-table row.
# The row is ONE physical line; the edit tool matches oldText anywhere in the file, so a small unique
# anchor is safer and more readable than quoting the whole ~900-char line.

# GOTCHA (character fidelity): the EXISTING row text contains em-dash (—) and ≥. The two oldText
# anchors above are deliberately chosen from ASCII-only spans of the row, so they match regardless of
# how the tool/terminal renders the surrounding non-ASCII chars. The newText introduces em-dashes and
# backticks (markdown renders these fine). If you re-derive an oldText anchor yourself, verify it is
# byte-exact — prefer an ASCII-only span.

# GOTCHA (do not over-edit): make BOTH edits to the SAME line 39 in ONE edit tool call (the file has
# many em-dashes; two small unique anchors in one call is the lowest-risk path). The two oldTexts do
# not overlap (Edit A's anchor is in the Criterion column; Edit B's anchor is the row's final tail).
```

### Integration Points

```yaml
DOCUMENTATION:
  - file: tests/ACCEPTANCE.md
  - change: criterion #10 row (line 39) — Criterion col gains the silence-gate clause; Evidence col
            gains the wiring + unit-test citation. Status stays PASS. Nothing else in the file moves.
  - pattern: keep the existing column delimiters (`|`), the existing semicolon-delimited clause style
             in the Criterion column, and the existing "(Evidence block below.)" tail in the Evidence
             column.

NO CODE / NO CONFIG / NO TEST / NO ROUTE CHANGES:
  - This task ONLY documents already-landed code. It edits zero .py / .toml files.
```

## Validation Loop

There is no test framework for a markdown file. Validation is deterministic grep + git + a manual
accuracy read. Run ALL levels.

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The criterion #10 row still parses as a markdown table row (correct number of `|` columns = 5
# leading+trailing incl. the leading/trailing pipes for a 4-col table: "| # | Crit | Status | Ev |").
awk 'NR==39 {n=gsub(/\|/,"|"); print "row39 pipes:", n}' tests/ACCEPTANCE.md
# Expected: the pipe count of row 39 is UNCHANGED vs the original (the edits add text inside columns,
# not new columns). Quick check: it should equal the pipe count of, e.g., row 30 (criterion #1).

# The field appears in BOTH the Criterion column AND the Evidence column of the row.
grep -n "lite_post_speech_silence_duration" tests/ACCEPTANCE.md
# Expected: at least 2 matches on (or near) line 39 — one in the Criterion clause, one in the
# Evidence note.
```

### Level 2: Unit Tests (Component Validation)

```bash
# No pytest applies to a markdown edit. Instead, verify the EVIDENCE WE CITE actually still passes
# (this is the test the Evidence column names — a sanity check that the citation is honest, NOT a
# test of the doc edit itself):
.venv/bin/python -m pytest tests/test_daemon.py \
  -k "test_cfg_to_kwargs_lite_uses_shorter_silence_duration or test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal" -q
# Expected: "2 passed" (already verified live — re-confirming keeps the citation accurate).
```

### Level 3: Integration Testing (System Validation)

```bash
# Confirm the edit is scoped to EXACTLY one file (the do-not-touch boundaries):
git status --porcelain
# Expected: ONLY " M tests/ACCEPTANCE.md". If anything else shows as modified, STOP and revert it.

# Confirm the fenced evidence block (lines ~62-110) is UNTOUCHED (it must NOT be regenerated):
git diff tests/ACCEPTANCE.md | grep -n "=== ACCEPTANCE EVIDENCE ===\|=== END ACCEPTANCE EVIDENCE ==="
# Expected: NO output (the fenced block markers are unchanged = not in the diff).

# Confirm criteria 1-9 rows are UNTOUCHED:
git diff tests/ACCEPTANCE.md | grep -E "^\+.*\| (1|2|3|4|5|6|7|8|9) \|"
# Expected: NO output (only the #10 row should appear as a changed line, prefixed "+").
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Manual accuracy read of the final row 39. Open tests/ACCEPTANCE.md, read criterion #10, and
# verify against this checklist:
#   [ ] Criterion column says lite uses its own shorter post_speech_silence_duration (default 0.5),
#       references §4.2ter, and the silence-gate-as-perceived-bottleneck framing.
#   [ ] Evidence column names asr.lite_post_speech_silence_duration, says it is wired in
#       cfg_to_kwargs (lite path), and cites test_cfg_to_kwargs_lite_uses_shorter_silence_duration.
#   [ ] Status column is still **PASS**.
#   [ ] The "(Evidence block below.)" tail + closing "|" are intact.
#   [ ] The existing evidence about VRAM (876 MiB < 2804 MiB), mode-switch, test_lite_feed_audio_*
#       is PRESERVED (the edit only ADDS, it does not delete those lines of evidence).
```

## Final Validation Checklist

### Technical Validation

- [ ] `awk` pipe-count check: row 39 column structure intact (Level 1).
- [ ] `grep lite_post_speech_silence_duration tests/ACCEPTANCE.md` shows ≥2 matches in row #10.
- [ ] `git status --porcelain` shows ONLY ` M tests/ACCEPTANCE.md` (Level 3).
- [ ] `git diff` shows the fenced `=== ACCEPTANCE EVIDENCE ===` block is UNCHANGED (Level 3).
- [ ] Cited test still passes: `2 passed` (Level 2 — honesty check on the citation).

### Feature Validation

- [ ] Criterion column of row #10 mirrors PRD §7 #10's silence-gate clause (commit a66b9d4).
- [ ] Evidence column of row #10 cites `test_cfg_to_kwargs_lite_uses_shorter_silence_duration`.
- [ ] Evidence column names `asr.lite_post_speech_silence_duration` (default `0.5`) + cfg_to_kwargs wiring.
- [ ] Status column stays `**PASS**`.
- [ ] All other evidence in the row (VRAM, mode-switch, test_lite_feed_audio_*) is PRESERVED.

### Code Quality Validation

- [ ] Edit uses the existing table column style (`|` delimiters, semicolon-delimited Criterion clauses).
- [ ] File placement matches desired tree (only `tests/ACCEPTANCE.md` changed).
- [ ] No new files created; no other files modified.
- [ ] Em-dashes/backticks in newText render as valid markdown.

### Documentation & Deployment

- [ ] The acceptance record now mirrors PRD §7 criterion #10 for the silence-gate feature.
- [ ] No runtime/env/doc implications — pure documentation.

---

## Anti-Patterns to Avoid

- ❌ Don't regenerate the fenced `=== ACCEPTANCE EVIDENCE ===` block — that needs the ~5-8 min GPU
  `test_idle_and_gpu.sh` run (explicitly out of scope per item clause (c)).
- ❌ Don't edit README.md — owned by the parallel sibling task P1.M3.T1.S1.
- ❌ Don't edit config.py / config.toml / daemon.py / test_daemon.py — already landed; this task only
  DOCUMENTS them.
- ❌ Don't edit PRD.md / tasks.json / prd_snapshot.md / .gitignore — forbidden / orchestrator-owned.
- ❌ Don't touch criteria 1–9 rows or any other part of ACCEPTANCE.md — out of scope.
- ❌ Don't rewrite the whole ~900-char row #10 line as one giant oldText — use the two small unique
  ASCII anchors (lower risk of a byte-mismatch on the non-ASCII chars in the row).
- ❌ Don't delete existing evidence in the row (VRAM numbers, mode-switch PASS lines,
  test_lite_feed_audio_* citations) — the edit ADDS the silence-gate note; it preserves everything else.
- ❌ Don't change the Status column — it is already `**PASS**` and the feature is implemented.

---

## Confidence Score

**9/10** — This is a single-row markdown documentation edit with byte-exact, in-file-verified,
ASCII-clean anchors; the feature is already landed and the cited test passes (confirmed live). The
only residual risk is a non-ASCII character fidelity issue in an anchor if the implementer re-derives
anchors rather than copying them verbatim from this PRP — mitigated by using the exact anchors above
and validating with the grep/pipe-count checks.
