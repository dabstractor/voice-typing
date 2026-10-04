---
name: "bugfix P1.M3.T9.S2 — tests/ACCEPTANCE.md: refresh rows 4/11/12 evidence"
description: "Docs-only refresh of the acceptance-evidence table rows most affected by the 8 landed bugfixes (BUG-001..008): re-verify row 4 (listening gates), and extend rows 11 (streaming) and 12 (cancel fallback) with the new daemon-level and engine-level regression-test citations plus verified run commands."
---

## Goal

**Feature Goal**: Make `tests/ACCEPTANCE.md` rows **4, 11, and 12** truthful and complete against
the 8 landed bugfixes (BUG-001..BUG-008, commits `03f9602`..`eac2d03`): every evidence claim is
re-verified against pinned code/tests, every new regression test that pins a bugfix behavior is
cited with a reproducible command, and stale line-number citations are corrected.

**Deliverable**: An edited `tests/ACCEPTANCE.md` — ONLY the Status/Evidence cells of table rows
4, 11, 12 (the `## Criteria` pipe table). Docs-only diff; no other file changes.

**Success Definition**: `git diff --stat` shows `tests/ACCEPTANCE.md` only; each new claim in
rows 4/11/12 is backed by a test that exists (grep-verifiable name) and passes (commands below,
run under `timeout`, green); the Criterion column text is byte-identical to before; no LIVE tag
is claimed for a command the implementer did not actually run.

## User Persona (if applicable)

**Target User**: The human reviewer / future maintainer who reads `tests/ACCEPTANCE.md` to decide
whether PRD §7 acceptance criteria 4, 11, 12 actually hold for the shipped code.

**Use Case**: After the bugfix changeset, the reviewer opens the acceptance table to check that
streaming/cancel/disarm guarantees (nothing typed while toggled off; live re-say after cancel;
recovery after a rejected final; no glued words) are demonstrated by real test evidence.

**User Journey**: Reviewer reads row 11 → sees citations of `test_cancel_then_next_utterance_streams_live_daemon_level`
etc. → runs the quoted command → gets the quoted pass count → trusts the PASS verdict.

**Pain Points Addressed**: Rows 11/12 currently predate the bugfixes (no citation of the new
regression tests — exactly the tests the PRD's Recommendations demanded); row 4 was refreshed
mid-fix but never re-verified as a docs pass; three cited line numbers have drifted and now point
at the wrong lines, which is precisely the "evidence that doesn't reproduce" failure this doc exists to prevent.

## Why

- The bugfix PRD (Recommendations) requires daemon-level regression tests for the four sequencing
  bugs; those tests landed (commits `8dc1534`, `60356cc`, `fe30155`, `aae7060`, `c9f2c8b`,
  `eac2d03`) — but the acceptance dossier, the human-readable record PRD §7 criterion 1 requires,
  still doesn't cite them.
- `architecture/config_tests_docs.md:23` prescribed this exact sequencing: row 4 gets a "Mode A
  update with the fix, then Mode B re-verify"; rows 11–12 get the changeset-level evidence sync.
  This task IS that Mode B pass (sibling S1 did README; both close milestone P1.M3).

## What

Edit `tests/ACCEPTANCE.md` (criteria table, rows 4, 11, 12 only):

1. **Row 4 — re-verify, minimal edit**: the BUG-004 fix commit `fe30155` already rewrote the
   evidence cell. Verify each claim still holds (pins below). If all verify, the row may stay
   as-is — record that as the re-verification (optionally tighten wording/counts). Do NOT touch
   the Criterion cell.
2. **Row 11 — extend evidence** with the new bugfix regression tests, grouped by bug:
   BUG-001 (rejected-final recovery, utterance-scoped), BUG-002 (re-said sentence streams live
   after cancel), BUG-003 (frozen commit types the trailing separator), BUG-008 (case-insensitive
   extends stop rewind churn) — plus fix the stale `tests/test_daemon.py:4510` → name-based
   citation and `tests/test_streaming_commit.py:307` → `:329` (or drop line numbers for names).
3. **Row 12 — extend evidence** with the cancel-path bugfix tests: BUG-002 daemon-level re-say
   (drives the same `daemon.cancel()` path `voicectl cancel` routes to) and BUG-007
   cancel-then-stop immediate disarm — plus fix the stale `tests/test_control_socket.py:278` →
   `:326` (or name-based).

### Success Criteria

- [ ] Row 4 claims re-verified: commit gate on `on_final`'s first line, partial gate on
      `_on_partial`'s first line, cited test exists and passes.
- [ ] Row 11 cites the new regression tests for BUG-001/002/003/008 with a quoted command and
      pass counts that the implementer actually observed.
- [ ] Row 12 cites `test_cancel_then_next_utterance_streams_live_daemon_level`,
      `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`,
      `test_stop_after_cancel_disarms_immediately`, `test_next_utterance_after_cancel_rearms_final_pending`.
- [ ] All three stale line citations (`:4510`, `:278`, `:307`) corrected or converted to
      name-based citations.
- [ ] Criterion column byte-identical; only Status/Evidence cells changed.
- [ ] `git diff --stat` → `tests/ACCEPTANCE.md` only.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, could they implement this successfully?" — Yes:
this PRP contains the exact current row texts' location, the full test-name inventory with file
paths, verified commands with observed outputs, the code pins for each claim, drafted evidence
prose, and the repo's safety rules (AGENTS.md) for running tests.

### Documentation & References

```yaml
# MUST READ - Include these in your context window
- file: tests/ACCEPTANCE.md
  why: THE file being edited. `## Criteria` pipe table (~line 27+): rows 4, 11, 12 are each ONE
        very long physical line. Columns: # | Criterion (PRD §7) | Status | Evidence.
  pattern: Follow the existing evidence style — bold LIVE/STATIC/PAST-LIVE tags, backticked test
        names with file paths, quoted commands WITH `timeout` wrappers, commit hashes where useful.
  gotcha: Each table row is a single line — edit the Evidence cell content, never reflow the
        table. Keep pipe-escaping (no raw `|` inside cells). Do NOT touch the evidence blocks for
        criteria 5/6/8/9/10 or the header regeneration note — out of scope.

- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M3T9S2/research/research-notes.md
  why: This item's research: verified test names + line numbers, observed pass counts, code pins,
        contract constraints, bugfix commit list.
  section: all

- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/config_tests_docs.md
  why: The changeset's docs architecture map; line 23 prescribes the row-4 "Mode A update then
        Mode B re-verify" sequencing this task completes.
  section: docs-surface section

- file: AGENTS.md
  why: Repo safety rules: EVERY non-trivial command under GNU `timeout` + a generous bash-tool
        timeout; `voicectl` always `timeout 30`; NEVER run the daemon in the foreground; prefer
        single pytest files / -k over whole suites; skip the 5–8 min shell E2E scripts.
  pattern: This is a docs task — Level 1/2 validation below is all that is required.
  gotcha: tests/test_daemon.py, test_streaming_core/freeze/commit.py are FAST (mocked fakes, <1 s);
        tests/test_streaming.py is CUDA-gated (minutes, needs GPU + prefetched models).

- file: plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md
  why: The cross-checked dossier every row references. Read-only sanity: rows are keyed by NUMBER
        (4/11/12), which this task does not change, so cross-references stay valid. Do NOT edit it.
  gotcha: It belongs to the PRIOR plan (006) — leave untouched.
```

### Current Codebase tree (relevant excerpt)

```bash
$ tree -L 2 -I '__pycache__|*.egg-info|.venv|.git'
.
├── AGENTS.md                  # safety rules — read before running anything
├── README.md                  # sibling task S1 already swept it (commit 22d105a) — DO NOT touch
├── PRD.md                     # READ-ONLY (human-owned)
├── config.toml
├── tests/
│   ├── ACCEPTANCE.md          # ← THE deliverable (rows 4, 11, 12 of the `## Criteria` table)
│   ├── test_daemon.py         # 227 fast mocked tests; new regression tests :4464-:5060
│   ├── test_streaming_core.py # fast engine tests (BUG-002/008 pins)
│   ├── test_streaming_freeze.py # fast engine freeze tests (BUG-001/002/003 pins)
│   ├── test_streaming_commit.py # fast engine commit tests (BUG-003/008 pins)
│   ├── test_streaming.py      # 7 CUDA-gated real-model tests (slow; needs GPU)
│   ├── test_control_socket.py # cancel-dispatch test :326 (row 12 citation)
│   └── test_key_listener.py   # listener-warning test :459 (row 12 citation, still accurate)
├── voice_typing/              # source — READ-ONLY for this task
└── plan/007_cfc245548aec/bugfix/001_23df36029e8d/
    ├── P1M3T9S2/PRP.md        # this PRP
    └── P1M3T9S2/research/research-notes.md
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
# NO new files. Exactly ONE modified file:
tests/ACCEPTANCE.md   # rows 4/11/12 Evidence (and Status, only if a verdict changes) refreshed
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: AGENTS.md — every pytest invocation needs GNU timeout INSIDE plus a bash-tool
#   timeout OUTSIDE (generously larger). Verified-safe forms are given in the Validation Loop.
# CRITICAL: tests/ACCEPTANCE.md table rows are single physical lines. Use the edit tool with a
#   unique substring of the row's Evidence cell; never reflow.
# CRITICAL: the Criterion column quotes PRD §7 verbatim — leave byte-identical. Only Status/Evidence.
# GOTCHA: evidence honesty — this doc's own convention tags LIVE / STATIC / PAST-LIVE. Tag LIVE
#   only what YOU ran this session. The pre-bugfix "7/7 green" claim for tests/test_streaming.py
#   predates the streaming.py changes; either re-run it once (Level 3) or keep it and pin the
#   bugfix delta via the 77 fast engine tests.
# GOTCHA: line-number citations drift (the bugfix commits added ~500 lines to test_daemon.py).
#   Prefer name-based citations; where a line number is kept, re-verify with grep -n first.
# GOTCHA: do not run tests/e2e_virtual_mic.sh or tests/test_idle_and_gpu.sh for this task —
#   5–8 min, CUDA, and the E2E one rebinds the system default audio source. Not needed for docs.
# GOTCHA: paths in this repo's venv: fast suites run via `uv run pytest ...`; the CUDA suite via
#   `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v` (as ACCEPTANCE.md itself
#   quotes). Never run the daemon binary or launch_daemon.sh in the foreground.
```

## Implementation Blueprint

### Data models and structure

None — documentation-only task. The "model" is the evidence table row:

```python
# Row anatomy (one physical line each, in tests/ACCEPTANCE.md `## Criteria`):
# | 11 | <criterion text — PRD §7 verbatim, DO NOT EDIT> | **PASS** | <evidence cell — EDIT THIS> |
# Evidence-cell house style: bold **LIVE**/**STATIC**/**PAST-LIVE** tags, `backticked` test
# names + (tests/file.py) paths, quoted `timeout`-wrapped commands with observed pass counts.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY the evidence commands (before writing any claim)
  - RUN (fast, mocked — safe, seconds):
      timeout 300 uv run pytest tests/test_streaming_core.py tests/test_streaming_freeze.py tests/test_streaming_commit.py -q
      # observed 2026-xx session: 77 passed
      timeout 300 uv run pytest tests/test_daemon.py -q -k "rejected_final_recovers or cancel_then_next_utterance or stop_after_cancel or on_partial_gated or user_keypress_frozen or cancel_suppression_drops or next_utterance_after_cancel"
      # observed: 7 passed, 220 deselected
  - RECORD the ACTUAL counts you observe; paste those (not the ones in this PRP) into the doc.
  - VERIFY cited test names exist:
      grep -n "def test_cancel_then_next_utterance_streams_live_daemon_level\|def test_rejected_final_recovers_at_next_speech_with_cue\|def test_stop_after_cancel_disarms_immediately\|def test_next_utterance_after_cancel_rearms_final_pending\|def test_cancel_suppression_drops_racing_final_and_clears_on_sentinel\|def test_on_final_user_keypress_frozen_commit_absorbs_then_unfreezes\|def test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing" tests/test_daemon.py
      grep -n "def test_rejected_final_freeze_lives_until_resume_then_next_utterance_types\|def test_resume_clears_post_cancel_suppression\|def test_cancel_then_resume_restores_live_delta_typing\|def test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen\|def test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types" tests/test_streaming_freeze.py
      grep -n "def test_mid_sentence_capitalized_partials_extend_case_insensitively\|def test_capitalized_partial_equal_length_case_only_diff_is_noop" tests/test_streaming_core.py
      grep -n "def test_commit_extend_matches_case_insensitively" tests/test_streaming_commit.py
  - VERIFY row-4 code pins: grep -n "_on_partial" voice_typing/daemon.py  (is_listening gate at
    first line) and grep -n "def on_final\|_on_final" voice_typing/daemon.py (gate at first line).

Task 2: EDIT row 4 (re-verify pass)
  - FILE: tests/ACCEPTANCE.md, the `| 4 |` line.
  - CONFIRM current evidence cell (already rewritten by commit fe30155) is accurate: partial
    gate on `_on_partial`'s first line, commit gate on on_final's first line, pinned by
    `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` (mocked LIVE,
    tests/test_daemon.py), E2E CRIT4 STATIC, tests/test_streaming.py 7/7.
  - OUTCOME: if everything verifies, EITHER leave the cell unchanged (legitimate — the
    architecture doc prescribed exactly "Mode A update with the fix, then Mode B re-verify") OR
    apply a minimal tightening. Any edit must keep the Criterion cell byte-identical.
  - GOTCHA: "suite 7/7" claims the CUDA suite; it still has 7 tests — but it was last run before
    the bugfix commits. If you do NOT re-run it (Task 5 optional), do not add any wording that
    implies fresh LIVE execution of that suite.

Task 3: EDIT row 11 (main work — extend the Evidence cell)
  - FILE: tests/ACCEPTANCE.md, the `| 11 |` line. KEEP the existing valid citations
    (tests/test_streaming.py a/b/c/e/g + the two hatch tests) and APPEND the bugfix coverage.
  - FIX stale citations in the kept text: `tests/test_daemon.py:4510` → name-based
    (`test_on_final_streaming_false_is_verbatim_rev1_hatch`, now :4747) and
    `tests/test_streaming_commit.py:307` → :329 (or name-based for both).
  - ADD (drafted — adjust counts to what you observed in Task 1; keep the house style):
    "Bugfix regression coverage (mocked **LIVE**, fast — `<the exact -q command>` → N passed,
    and the 3 engine suites → 77 passed): rejected-final recovery is utterance-scoped —
    `test_rejected_final_freeze_lives_until_resume_then_next_utterance_types` +
    `test_rejected_final_recovers_at_next_speech_with_cue` (daemon WARNING cue) +
    `test_on_final_streaming_rejected_final_freezes_tail_and_keeps_bookkeeping` (BUG-001; T8g
    tail frozen as-is, never auto-deleted, typing resumes at next speech); the re-said sentence
    after Backspace-cancel streams live — `test_cancel_then_next_utterance_streams_live_daemon_level`
    (daemon-level; no manual reset_boundary) + engine `test_cancel_then_resume_restores_live_delta_typing`
    / `test_resume_clears_post_cancel_suppression` (BUG-002; T8a/T8e); a frozen (user-keypress)
    commit types the trailing separator so words never glue —
    `test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen`,
    `test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types`
    (tests/test_streaming_freeze.py), daemon `test_on_final_user_keypress_frozen_commit_absorbs_then_unfreezes`
    (BUG-003); extends match case-insensitively so capitalized mid-sentence partials keep
    delta-typing instead of rewind churn — `test_mid_sentence_capitalized_partials_extend_case_insensitively`,
    `test_capitalized_partial_equal_length_case_only_diff_is_noop` (tests/test_streaming_core.py),
    `test_commit_extend_matches_case_insensitively` (tests/test_streaming_commit.py) (BUG-008; T8a)."
  - OPTIONAL: also cite `tests/test_streaming.py::test_f_user_key_freeze` (:1497) among the
    real-model tests (currently uncited although row text already claims 7/7, which includes it).

Task 4: EDIT row 12 (extend the Evidence cell)
  - FILE: tests/ACCEPTANCE.md, the `| 12 |` line. KEEP existing citations (test_e_cancel,
    socket dispatch, listener-warning-once, T7 cancel smoke) and FIX the stale
    `tests/test_control_socket.py:278` → :326 (or name-based).
  - ADD (drafted — same rules):
    "Re-said sentence after a cancel streams live (BUG-002): `test_cancel_then_next_utterance_streams_live_daemon_level`
    + `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` (tests/test_daemon.py,
    mocked **LIVE** — they drive `daemon.cancel()`, the same path `voicectl cancel` routes to).
    Cancel-then-stop disarms immediately — no ~5 s drain (BUG-007): `test_stop_after_cancel_disarms_immediately`
    + `test_next_utterance_after_cancel_rearms_final_pending` (tests/test_daemon.py)."
  - GOTCHA: `tests/test_key_listener.py:459` is still accurate — leave it.

Task 5 (OPTIONAL, only if a GPU + prefetched models are available): re-certify the CUDA suite
  - RUN: timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v   (bash-tool timeout ≥ 960)
  - EXPECT: 7/7. If run, row 11's real-model claim is freshly LIVE; if not run, leave the claim
    as-is (it documents the prior round) — the bugfix delta is pinned by the fast suites.
  - GOTCHA: single file only; never the whole suite; never the shell E2E scripts.

Task 6: FINAL SWEEP
  - RUN: git diff -- tests/ACCEPTANCE.md  — confirm ONLY rows 4/11/12 Evidence/Status cells
    changed, Criterion cells byte-identical, no table reflow (git diff should show 1–3 long-line
    changes), no unescaped `|` introduced.
  - RUN the Level 1 greps in the Validation Loop.
```

### Implementation Patterns & Key Details

```python
# Editing pattern for one-line table rows (use the edit tool, unique substring anchor):
#   oldText: a distinctive slice of the CURRENT Evidence cell, e.g.
#     "Rollback hatch (`output.streaming=false` → Rev 1 append-only): `test_on_final_streaming_false_is_verbatim_rev1_hatch` (`tests/test_daemon.py:4510`)"
#   newText: same slice with corrected citation + appended bugfix coverage.
# Do NOT include the Criterion cell in oldText — it must never change.
# Keep the row on ONE physical line (the file's existing convention; no hard wraps inside rows).
```

### Integration Points

```yaml
GIT:
  - commit message convention (match siblings): short imperative, e.g.
    "Refresh acceptance rows 4/11/12 with bugfix regression evidence"
DOCS-CONTRACT (Mode B):
  - edit ONLY tests/ACCEPTANCE.md — README.md belongs to sibling S1 (complete, commit 22d105a)
  - NEVER touch: PRD.md, **/tasks.json, prd_snapshot.md, voice_typing/*, tests/*.py (test code)
  - the `plan/006_.../acceptance_gate.md` dossier is referenced BY rows but owned by plan 006 — untouched
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# Markdown sanity: the table still parses as a table (each row exactly one line, pipes balanced)
grep -c "^| 4 |\|^| 11 |\|^| 12 |" tests/ACCEPTANCE.md   # Expect: 3
awk -F'|' '/^\| (4|11|12) \|/ {print NF}' tests/ACCEPTANCE.md  # Expect: 6 6 6 (5 columns + edges)

# Criterion cells byte-identical (compare against git HEAD before/after):
git diff -- tests/ACCEPTANCE.md | grep -E "^[-+]\| (4|11|12) \|" | sed 's/|[^|]*|[^|]*|[^|]*|//' >/dev/null
git diff --stat                                           # Expect: tests/ACCEPTANCE.md | N +- (only)

# Cited test names all exist (run from repo root; expect 1 hit each, exit 0):
grep -rn "def test_cancel_then_next_utterance_streams_live_daemon_level\|def test_stop_after_cancel_disarms_immediately\|def test_rejected_final_recovers_at_next_speech_with_cue" tests/test_daemon.py
```

### Level 2: Unit Tests (Component Validation)

```bash
# The evidence you cite must actually pass — run exactly what the rows quote:
timeout 300 uv run pytest tests/test_streaming_core.py tests/test_streaming_freeze.py tests/test_streaming_commit.py -q
# Expected: 77 passed (observed pre-writing; paste YOUR observed count)

timeout 300 uv run pytest tests/test_daemon.py -q -k "rejected_final_recovers or cancel_then_next_utterance or stop_after_cancel or on_partial_gated or user_keypress_frozen or cancel_suppression_drops or next_utterance_after_cancel"
# Expected: 7 passed, 220 deselected

# Full fast daemon suite still green (docs change must not have touched code — sanity):
timeout 600 uv run pytest tests/test_daemon.py tests/test_control_socket.py -q
# Expected: all passed (227 + socket suite)
```

### Level 3: Integration Testing (System Validation)

```bash
# OPTIONAL (only with GPU + prefetched models) — re-certify row 11's real-model claim:
timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v   # bash-tool timeout ≥ 960
# Expected: 7 passed. If skipped, keep the existing claim wording untouched (no fresh-LIVE framing).

# NOT REQUIRED and DO NOT RUN for this task (5–8 min, CUDA, audio-source rebind):
#   ./tests/test_idle_and_gpu.sh, ./tests/e2e_virtual_mic.sh
# NEVER run: voice-typing-daemon, voice_typing/launch_daemon.sh (blocks forever — AGENTS.md Rule 2)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Evidence-doc-specific checks: every quoted command inside rows 4/11/12 is copy-pasteable and
# carries a `timeout` wrapper (grep the rows for bare `pytest`/`voicectl` invocations):
sed -n '/^| 11 |/p;/^| 12 |/p;/^| 4 |/p' tests/ACCEPTANCE.md | grep -o "timeout [0-9]* [^`]*" | head

# Claim→pin spot checks (house discipline from the sibling task):
grep -n "_stream.resume()" voice_typing/daemon.py        # recovery hook (row 11 BUG-001 claim)
grep -n "filtered hallucination" voice_typing/daemon.py  # user-visible rejected-final cue
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 greps pass (3 rows, balanced pipes, Criterion cells byte-identical)
- [ ] Level 2 suites green with the counts pasted into the rows
- [ ] Level 3 either run (7/7) or explicitly not re-framed as fresh LIVE
- [ ] `git diff --stat` → `tests/ACCEPTANCE.md` only

### Feature Validation

- [ ] Row 4 re-verified (gate pins + test name) — edit or explicit no-change verdict
- [ ] Row 11 cites BUG-001/002/003/008 regression tests + corrected stale line refs
- [ ] Row 12 cites BUG-002 cancel-path + BUG-007 stop-after-cancel tests + corrected `:278` ref
- [ ] All counts/claims in the rows were observed by the implementer this session
- [ ] House style kept: LIVE/STATIC/PAST-LIVE tags, backticked names, timeout-wrapped commands

### Code Quality Validation

- [ ] No table reflow; rows still one physical line each
- [ ] No unescaped `|` inside cells; no trailing whitespace introduced
- [ ] No changes outside the three Evidence/Status cells

### Documentation & Deployment

- [ ] No source, test-code, PRD, tasks.json, or README changes
- [ ] Commit follows sibling convention (short imperative summary)

## Anti-Patterns to Avoid

- ❌ Don't cite a test you didn't watch pass this session under a **LIVE** tag — re-tag honestly.
- ❌ Don't renumber/rewrite the Criterion column (PRD §7 quotes stay verbatim).
- ❌ Don't "fix" evidence by weakening a claim (e.g. dropping the listening-gate statement) —
  the fixes landed; the evidence should now demonstrate them.
- ❌ Don't run the daemon, the shell E2E scripts, or untimed `voicectl` (AGENTS.md hang vectors).
- ❌ Don't touch rows 1–3, 5–10, the evidence blocks, or the header regeneration note.
- ❌ Don't introduce markdown line-wrapping inside table rows.

---

## Confidence Score

**9/10** — docs-only task with fully drafted evidence text, verified test names/line numbers/
commands/counts (research session pinned every claim), and explicit stale-citation fixes. The
one residual uncertainty: whether the optional CUDA re-run (Task 5) is performed, which only
affects LIVE-tag freshness of pre-existing row-11 claims, not correctness.
