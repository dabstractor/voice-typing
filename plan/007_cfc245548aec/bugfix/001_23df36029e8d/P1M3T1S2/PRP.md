# PRP — P1.M3.T9.S2: tests/ACCEPTANCE.md — refresh rows 4/11/12 evidence

## Goal

**Feature Goal**: Mode B acceptance-matrix sync — refresh the Evidence cells of ACCEPTANCE.md rows 4
(`:35`), 11 (`:42`), and 12 (`:43`) so every claim cites the new daemon-level sequencing regression
tests landed by the bugfix subtasks (P1.M1.T1.S2/T2.S2/T3.S1/T4.S1) and is true against the fixed code.
Rationale (PRD Overview): the old evidence masked the sequencing bugs the same way the old unit tests
did ("they drive engine methods directly and even manually invoke reset_boundary()"); the refreshed
rows must cite the tests that actually pin the fixed daemon flow. **Do not invent evidence — cite only
tests that exist and pass** (verify each by running it first).

**Deliverable**: `tests/ACCEPTANCE.md` — 3 single-line Evidence-cell extensions (rows 4, 11, 12).
Statuses stay **PASS**. All existing citations kept (CUDA-gated suite, hatch tests, E2E/STATIC refs) —
the refresh ADDS the new fast-suite citations.

**Success Definition**:
- (a) Row 4's evidence cites `test_commit_frozen_absorbs_tail_and_types_separator` (BUG-003,
  space-separated frozen commits) alongside the already-cited BUG-004 gate test.
- (b) Row 11's evidence cites `test_rejected_final_recovers_at_next_speech_with_cue` (BUG-001) and
  `test_cancel_then_next_utterance_streams_live_daemon_level` (BUG-002) as the fast daemon-level
  sequencing regressions complementing the CUDA-gated `test_streaming.py` 7/7 suite.
- (c) Row 12's evidence cites `test_cancel_then_next_utterance_streams_live_daemon_level` (the re-said
  sentence after cancel streams live — the T8e continuation).
- (d) Every cited test node-id was re-run green BEFORE being written (gate, below).
- (e) `git status --porcelain` shows only ` M tests/ACCEPTANCE.md`; no other file touched (README is S1).

## Why

- PRD Overview: "the current matrix masked the sequencing bugs" — rows 11/12 cited only the CUDA-gated
  suite + engine-level tests, the exact blind spot. The four new daemon-level tests are the fix's proof.
- architecture/config_tests_docs.md pins this task: "rows 11-12 :42-43 (streaming & cancel criteria
  evidence)" + row 4's Mode B re-verify after T4.S1's Mode A edit.
- Disjoint from S1 (README-only), T6.S1 (config.toml/config.py), T5.S1 (daemon/control-socket tests).

## What

Three single-line edits appending test citations to the Evidence cells. Cited tests + verdicts:

| Test (node-id) | File:line | Bug | Row(s) | Verified |
|---|---|---|---|---|
| `test_rejected_final_recovers_at_next_speech_with_cue` | tests/test_daemon.py:4730 | BUG-001 | 11 | ✅ pass (live) |
| `test_cancel_then_next_utterance_streams_live_daemon_level` | tests/test_daemon.py:4579 | BUG-002 | 11, 12 | ✅ pass (live) |
| `test_commit_frozen_absorbs_tail_and_types_separator` | tests/test_streaming_commit.py:245 | BUG-003 | 4 | ✅ pass (live) |
| `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` | tests/test_daemon.py:4972 | BUG-004 | 4 | ✅ already cited |

**M2 minors — NOT cited** (no row 4/11/12 claim depends on them): BUG-005 tests exist but are socket-row
material; BUG-006/BUG-007 tests do not exist yet (Planned) and no refreshed claim references them.

### Success Criteria
- [ ] The three node-ids above appear in rows 4/11/12 respectively.
- [ ] Rows remain well-formed table rows (single line, pipes intact); Statuses unchanged (**PASS**).
- [ ] Only `tests/ACCEPTANCE.md` modified; existing citations (streaming 7/7, hatch, E2E/STATIC) intact.

## All Needed Context

### Context Completeness Check
_Pass._ The research note pins: row line numbers + what each row lacks, the verified-passing node-ids
with file:line, the M2 skip rationale, the masking rationale, and the edit mechanics (one-line rows,
append-to-Evidence, unique-tail anchors, run-before-cite gate).

### Documentation & References
```yaml
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M3T1S2/research/acceptance_rows_refresh.md
  why: "§1 row states + gaps; §2 the verified citation table; §3 M2 skip rationale; §4 masking rationale;
        §5 edit mechanics + gates. THE decision record."
- file: tests/ACCEPTANCE.md
  why: "EDIT rows :35/:42/:43. Anchor on each row's unique Evidence-cell tail (re-locate live — numbers
        drift). Keep existing citations; append the new ones with the bug/task tags the file already
        uses (e.g. '(BUG-004 / P1.M1.T4.S1)')."
  critical: "Rows are single lines — extend, don't rewrap. Reproduce — and backticks byte-exactly."
- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/config_tests_docs.md
  why: "The cited research note: pins rows 11-12 as the streaming/cancel evidence surface + row 4's
        Mode B re-verify; the per-bug map confirming no M2 doc dependency for these rows."
- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M3T1S1/PRP.md
  why: "The parallel README sweep (Mode B sibling). Confirms zero overlap: it edits README.md only and
        explicitly lists ACCEPTANCE.md as out of scope (S2 = this task)."
  critical: "Do NOT edit README.md here."
```

### Current Codebase tree (excerpt)
```bash
tests/ACCEPTANCE.md   # <-- EDIT: rows 4 (:35), 11 (:42), 12 (:43) — Evidence-cell extensions only
README.md             # NOT this task (S1 = P1.M3.T9.S1)
voice_typing/ + tests/test_*.py  # NOT this task (impl tasks own them)
```

### Known Gotchas
```python
# CRITICAL #1 — RUN BEFORE CITE. Re-run each node-id (.venv/bin/python -m pytest <id> -q) and only
#   then write it into a row. "Do not invent evidence — cite only tests that exist and pass."
# CRITICAL #2 — ONE LINE PER ROW. Rows are single markdown table lines; append inside the Evidence
#   cell before the closing ' |'. No rewrapping, no pipe breakage, Statuses stay PASS.
# CRITICAL #3 — ANCHORS ARE UNIQUE TAILS, NOT LINE NUMBERS. Row 4 tail: '...tests/test_streaming.py
#   -v`. |'; row 11 tail: '...test_streaming_commit.py:307`). |'; row 12 tail: '...test_key_listener
#   .py:459`). |'. Verify uniqueness with grep before each edit (row 10 also cites test_streaming.py
#   — confirm the exact tail string matches only the intended row).
# GOTCHA #4 — M2 MINORS STAY OUT. BUG-005/006/007 tests are either socket-row material or not yet
#   landed; no row-4/11/12 claim references them. Citing them anyway violates the no-invention rule.
# GOTCHA #5 — Keep the file's citation idiom: backticked test name + (BUG-00x / P1.Mx.Tx.Sx) tag +
#   'mocked LIVE'/'fast suite' qualifier where the neighbors use it.
```

## Implementation Blueprint

### Tasks (ordered)

```yaml
Task 1: PREFLIGHT — locate rows + run the four candidate tests (no mutation)
  - RUN: grep -n '^| 4 \|^| 11 \|^| 12 ' tests/ACCEPTANCE.md       # :35/:42/:43 (re-locate)
          .venv/bin/python -m pytest tests/test_daemon.py::test_rejected_final_recovers_at_next_speech_with_cue \
            tests/test_daemon.py::test_cancel_then_next_utterance_streams_live_daemon_level \
            tests/test_daemon.py::test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing \
            tests/test_streaming_commit.py::test_commit_frozen_absorbs_tail_and_types_separator -q
  - EXPECTED: 4 passed. Any failure → STOP: do not cite; report the failure (a failing cited test
    would make the row claim false).

Task 2: EDIT row 4 — append the BUG-003 separator citation
  - ANCHOR (unique tail of row 4's Evidence cell): "suite 7/7 green via `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v`. |"
  - newText: same text + " Typed-output correctness after a user-keypress freeze (BUG-003 / P1.M1.T3.S1): `test_commit_frozen_absorbs_tail_and_types_separator` (`tests/test_streaming_commit.py`) — frozen commits still type the `output.append_space` separator, mocked **LIVE**. |"

Task 3: EDIT row 11 — append the BUG-001/BUG-002 daemon-level sequencing citations
  - ANCHOR (row 11 tail): "(`tests/test_streaming_commit.py:307`). |"
  - newText: same text + " Fast daemon-level sequencing regressions (the round's masked-bug class, mocked **LIVE**): `test_rejected_final_recovers_at_next_speech_with_cue` (BUG-001 — a blocklist/`min_chars`-rejected final does NOT silence the session; output resumes at the next utterance with a journal cue) + `test_cancel_then_next_utterance_streams_live_daemon_level` (BUG-002 — the re-said sentence after Backspace-cancel streams live partials, not wait-for-commit). |"

Task 4: EDIT row 12 — append the BUG-002 citation (cancel continuation)
  - ANCHOR (row 12 tail): "(`tests/test_key_listener.py:459`). |"
  - newText: same text + " Post-cancel live re-say (BUG-002 / P1.M1.T2.S2): `test_cancel_then_next_utterance_streams_live_daemon_level` (`tests/test_daemon.py`, mocked **LIVE**) — the utterance after the socket/Backspace cancel types live again. |"

Task 5: VERIFY — greps + scope guard (Validation Loop); record in the result which tests were re-run
  - No git commit unless the orchestrator directs it.
```

### Implementation Patterns & Key Details
```markdown
<!-- Each edit: keep the row's existing tail byte-identical, append one or two citations in the file's
     idiom (backticked name, bug/task tag, mocked-LIVE qualifier), row stays one line. Example shape:
     ... existing evidence ... + `test_name` (BUG-00x / P1.Mx.Tx.Sx — what it pins), mocked **LIVE**. | -->
```

### Integration Points
```yaml
DOCUMENTATION ONLY:
  - tests/ACCEPTANCE.md: "rows 4/11/12 Evidence cells + the 4 new citations (3 newly added; 1 already present)"
CONSUMED (verified landed + green):
  - P1.M1.T1.S2 / T2.S2 / T4.S1 (tests/test_daemon.py:4730/:4579/:4972)
  - P1.M1.T3.S1 (tests/test_streaming_commit.py:245)
NOT TOUCHED: README.md (S1), config.toml/config.py (T6.S1), daemon.py + test files (impl tasks)
```

## Validation Loop

### Level 1: Structure intact
```bash
cd /home/dustin/projects/voice-typing
awk -F'|' '/^\| (4|11|12) /{print NF}' tests/ACCEPTANCE.md   # each row still splits into the same field count (6)
grep -c 'PASS' tests/ACCEPTANCE.md                            # no Status changed
```

### Level 2: Citations landed + true
```bash
grep -n 'test_commit_frozen_absorbs_tail_and_types_separator' tests/ACCEPTANCE.md   # row 4
grep -n 'test_rejected_final_recovers_at_next_speech_with_cue' tests/ACCEPTANCE.md  # row 11
grep -c 'test_cancel_then_next_utterance_streams_live_daemon_level' tests/ACCEPTANCE.md  # rows 11 AND 12 → 2
# And every cited node-id re-run green (Task 1's run is the proof; re-run if edited after).
```

### Level 3: Scope guard
```bash
git status --porcelain            # ONLY ' M tests/ACCEPTANCE.md'
git diff tests/ACCEPTANCE.md | grep -cE '^\+'   # exactly 3 added lines (one per row)
```

### Level 4: Accuracy read
Read each extended row against the fixed code: row 4's claim ("gates BOTH paths" + space-separated
commits) — true via :4972 gate test + :245 separator test; row 11's sequencing claims — true via
:4730/:4579; row 12's live-re-say — true via :4579. No claim lacks a test citation.

## Final Validation Checklist

### Technical Validation
- [ ] Task 1 preflight: 4 tests pass (recorded in the result).
- [ ] 3 new citations present (row 4 ×1; row 11 ×2; row 12 ×1); row 4's BUG-004 citation intact.
- [ ] Rows 4/11/12 still single-line, 6 fields, Status **PASS**; `git status` shows only ACCEPTANCE.md.

### Feature Validation
- [ ] Row 4: gate (BUG-004) + separator (BUG-003) both cited — the "typed output reaches the target"
      claim is now fully test-backed.
- [ ] Row 11: BUG-001 recovery + BUG-002 live re-say cited as the daemon-level sequencing regressions.
- [ ] Row 12: BUG-002 cited for the post-cancel live re-say continuation.
- [ ] No M2-minor citations (BUG-005/006/007) — none needed, none invented.

### Code Quality Validation
- [ ] Citation idiom matches the file (backticks, bug/task tags, mocked-LIVE qualifiers).
- [ ] Existing citations (CUDA-gated 7/7, hatch, E2E/STATIC) byte-identical.

### Documentation & Deployment
- [ ] This IS the Mode B docs task for ACCEPTANCE.md; no README/config/impl files touched.

---

## Anti-Patterns to Avoid

- ❌ Don't cite a test without re-running it green first (Critical #1 — the no-invention rule).
- ❌ Don't rewrap or split the one-line rows; don't touch Status cells (Critical #2).
- ❌ Don't anchor on line numbers — grep the unique row tails live (Critical #3; row 10 also cites
     `test_streaming.py`, so verify each tail matches exactly one row).
- ❌ Don't cite BUG-005/006/007 tests — socket-row material or not landed (Gotcha #4).
- ❌ Don't delete/replace existing citations (CUDA-gated, hatch, E2E/STATIC) — the refresh is additive.
- ❌ Don't edit README.md (S1 owns it) or any code/test/config file.

---

**Confidence Score: 9.5/10** — all four cited tests verified passing live at PRP time; the row gaps,
anchors, and the M2 skip rationale are pinned in the research note; the parallel tasks are disjoint
(README vs ACCEPTANCE vs code); and validation is deterministic (citation greps + 3-added-lines diff +
scope guard). The −0.5 reserves anchor drift (handled by live tail-greps) and the small chance an M2
test lands mid-implementation and tempts an out-of-scope citation (forbidden by Gotcha #4).
