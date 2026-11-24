# PRP — P1.M7.T2.S2: tests/ACCEPTANCE.md rows + install.sh usage

## Goal

**Feature Goal**: Bring the acceptance dossier (`tests/ACCEPTANCE.md`) and the installer's printed
usage (`install.sh`) current with the Rev-3/4 delta changeset — this is the **Mode B
changeset-level sync** tail (delta_prd.md:91: "`install.sh` printed usage gains `session`;
`tests/ACCEPTANCE.md`: add the ducking row and row #13 with actual command output links; refresh
row #12 if D3 changes cancel behavior. Every claim verified against the code as landed — no
aspirational prose").

Concretely: **row 11 is STALE and must be re-measured** (it claims `tests/test_streaming.py`
"7/7 green" and "77 passed" for the mocked trio; HEAD measures **3/7** and **76/18**) and
refreshed with numbers **reconciled against the G1 baseline classification**
(`tests/G1_BASELINE.md`: lazy-separator legacy reds separated from NEW failures — **no parity
faking**); row 12 gains the D3 cancel-behavior regression evidence; a **ducking row (D1,
§4.2quinquies)** and **row #13 (§7 item 13, bulk text)** are added with actual command-output
links; the doc's totals are updated; `install.sh`'s usage line gains the `session` command.

**Deliverable** (2 files MODIFIED; nothing else):
- `tests/ACCEPTANCE.md` — header scope line, dossier/row-1 totals, refreshed rows 11 + 12, new
  ducking row, new row 13.
- `install.sh` — the printed usage block gains `session` (+ one hint line).

**Success Definition**:
- (a) No stale claim remains: grep for `7/7`, `77 passed`, and `424` shows either updated
  re-measured numbers or explicitly round-attributed historical numbers — never a stale number
  presented as current.
- (b) Every red counted in row 11/12 evidence is reconciled **by name** against the G1 20-row
  classification table; any red NOT in that table is reported in the row as a NEW failure (and
  flagged in the final report) — never skipped, never hidden, never re-classified by this task.
- (c) The ducking row and row 13 cite committed evidence files by path with their actual
  recorded results (12/12 duck checks; `G6 DECISION: STAY OPT-IN` verbatim-derived framing).
- (d) `bash -n install.sh` passes; `tests/test_systemd_unit.py` and `tests/test_voicectl.py`
  stay green after the usage edit.
- (e) `git diff --name-only` (excluding `plan/`) shows exactly `tests/ACCEPTANCE.md` and
  `install.sh`.

## User Persona

**Target User**: (1) the operator + any future auditor reading `tests/ACCEPTANCE.md` as the
human-readable record PRD §7.1 demands ("T1–T4, T6 pass, demonstrated by actual command output —
not claimed") — a row claiming 7/7 when HEAD is 3/7 is exactly the "claimed, not demonstrated"
failure the PRD forbids; (2) a fresh-cloner reading `install.sh`'s final usage block who would
otherwise never learn `voicectl session` exists.

**Use Case**: audit any acceptance row → re-run its cited command → get the number the row
states; read install output → see all seven voicectl commands.

**Pain Points Addressed**: stale row 11 actively over-claims streaming health at HEAD; rows for
ducking (P1.M2, landed + evidence-flipped default) and bulk text (§7.13) don't exist; the 424
total predates the whole delta changeset; install usage omits `session`.

## Why

- **PRD §7.1**: acceptance must be "demonstrated by actual command output (not claimed)" — the
  dossier IS that demonstration; a stale row violates the definition of done it records.
- **PRD §4.2sexies R.7 G1 contract** (via `tests/G1_BASELINE.md`): the (i)/(ii) classification
  is the invariant later work diffs against; the dossier's row 11 must carry the reconciled
  split (legacy lazy-separator reds ≠ NEW failures) so parity is never faked by silence.
- **PRD §7.13 tail**: bulk-text "claims are reported as unverified" until G6 — the acceptance
  row is where those claims get reported with links to the actual gate outputs.
- **§4.2quinquies Acceptance paragraph**: ducking's five scenarios have committed scripted
  evidence (`tests/D1_DUCK_EVIDENCE.md`, 12/12) that the dossier must surface as a row.
- **install.sh header contract**: "This script's stdout IS the user-facing install/usage
  quick-start" — the usage line is the shipped command surface; `session` landed in P1.M6.T2.S3.

## What

Six scoped edits:

1. **Header scope**: "PRD §7 criteria 1–12" → "PRD §7 criteria 1–13 plus the §4.2quinquies
   media-ducking row (D1)".
2. **Row 11 refresh** (streaming, §4.2quater): re-measure `tests/test_streaming.py`
   (`timeout 300` … `-q --tb=line`) and the mocked trio (`timeout 120` … commit+core+freeze
   `-q --tb=line`); write the measured numbers with the G1 reconciliation split: the four
   streaming reds = `test_a_delta_cadence` (ii, watch set), `test_b_commit_rewind_exact` (ii,
   watch set), `test_f_user_key_freeze` (i/F1), `test_g_stranded_tail` (i/F5, FLAKY class);
   trio reds = the 16 classified (i) legacy lazy-separator reds + **every red beyond that set
   named as NEW**; keep/refresh the rollback-hatch and `-k` sub-run numbers.
3. **Row 12 refresh** (cancel fallback): re-run the cited `-k` selections; append the D3
   regression-test citations (auto-repeat compensation, suppression-window latch bound —
   verify names at HEAD first) with their re-measured counts.
4. **NEW ducking row** labeled `D1` (§4.2quinquies), placed between rows 12 and 13: the five
   acceptance scenarios → 12/12 scripted checks, `tests/D1_DUCK_EVIDENCE.md`, re-runnable via
   `timeout 900 bash tests/d1_duck_evidence.sh`.
5. **NEW row 13** (§7 item 13, bulk text): opt-in shipped (`output.delivery="bulk-text"`,
   default stays `"stream-edit"`); evidence links with actual outputs — G2 13/13 traces, G3
   matrix + honest row statuses, G4 verdicts, G5 failing-route numbers, and the verbatim
   `G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)` —
   claims reported **unverified**; `voicectl session [--copy]` tested.
6. **Totals**: row 1's "**424 LIVE-green**" and the dossier paragraph's "424 LIVE-green test
   executions this round" — re-measure the cited suites where runnable and update, else
   explicitly re-attribute the number to its capture round; and **install.sh** usage line:
   `toggle|start|stop|status|cancel|session|quit` + a `session [--copy]` hint line.

### Success Criteria

- [ ] 14 rows (1–12 + D1 + 13); header sentence matches.
- [ ] Row 11 shows HEAD-measured numbers with the (i)-legacy / (ii)-watch / NEW split by name.
- [ ] Rows D1 + 13 cite evidence files by path; row 13's framing derived from the G6 decision line.
- [ ] Totals updated or explicitly re-attributed; no "7/7"/"77 passed"/bare-"424" stale claims.
- [ ] install.sh usage lists `session`; `bash -n` + the two pinning test files green.
- [ ] `git diff --name-only` (minus `plan/`) = exactly the two files.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs: the current ACCEPTANCE.md contents (read in full — it is the file
being edited), the G1 classification authority, the four evidence files for the new rows, the
D3 test names, the install.sh usage block, and the sibling-task boundaries — all pinned below
with paths and verbatim anchors. No prior knowledge assumed beyond reading these.

### Documentation & References

```yaml
# MUST READ — the assembled fact ledger for this task (rows inventory, G1 mapping, ducking/row-13
# content, install.sh target, D3 test names, boundaries).
- file: plan/008_a47116bb2b79/P1M7T2S2/research/acceptance_rows_and_install_usage.md
  why: "Everything gathered this session with file:line cites — the PRP's facts derive from it."

# MUST READ — the file being edited (rows 1–12, evidence block, method notes).
- file: tests/ACCEPTANCE.md
  why: "Row table format '| # | Criterion (PRD §7) | Status | Evidence |'; the stale claims live
        in rows 1/11 and the dossier paragraph; the method notes at the bottom explain evidence
        conventions (LIVE / STATIC / PAST-LIVE typing)."
  critical: "Preserve the existing evidence-typing vocabulary and voice. Do not renumber §7 rows."

# MUST READ — the classification authority row 11 must reconcile against.
- file: tests/G1_BASELINE.md
  why: "The 20-row (i)/(ii) classification table (suite:line + facet F1–F5), the test_streaming.py
        3P/4F flake table, the watch-set protocol, and the contract statement (no skips, no
        expectation edits, the (i) set is the diff invariant)."
  critical: "DO NOT EDIT this file and DO NOT re-classify anything in it. Row 11 REPORTS the
             reconciliation; G1_BASELINE.md OWNS the classification. A red not in its table is a
             NEW failure to name and escalate — not to reclassify."

# MUST READ — ducking row evidence (the row's substance).
- file: tests/D1_DUCK_EVIDENCE.md
  why: "The five §4.2quinquies acceptance scenarios → 12/12 scripted checks (exit 0), the 107 ms
        pause timing, verbatim journal lines, the sovereignty ledger refinement. Copy results +
        the re-run command into the row."

# MUST READ — row 13's framing source of truth.
- file: tests/G6_GRADUATION.md
  why: "G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions) +
        the per-condition table (edit-count-law 'warm-up overcount', pi-prompt not-verified,
        browser insert-only/correction REFUSED, G5 im-gtk + pi-ghostty failing, 0 writing
        sessions)."
  critical: "Derive the row's framing from the decision line VERBATIM. If the file were absent or
             the decision changed: re-derive via `timeout 60 .venv/bin/python tests/g6_assessment.py`
             and follow what it says — never soften 'unmet' wording."

# READ — row 13's linked registers (skim headers/verdict lines only).
- file: plan/008_a47116bb2b79/architecture/g2_gate_record.md        # 13/13 traces
- file: plan/008_a47116bb2b79/architecture/g3_field_matrix.md       # field-class matrix + versions
- file: plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl    # pi-prompt row (24 rows)
- file: plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl  # browser rows (17)
- file: plan/008_a47116bb2b79/architecture/g4_clipboard_verdicts.jsonl       # clipboard gate
- file: tests/G5_TIMING_EVIDENCE.md                                 # failing-route numbers
- file: tests/G6_WRITING_SESSIONS.md                                # 0 valid sessions (the outstanding input)

# READ — the code surfaces the claims must match (grep, don't full-read).
- file: install.sh                  # usage echo block at :209-211 (the edit target)
- file: tests/test_systemd_unit.py  # :205 test_install_sh_offline_grep_and_summary — greps install.sh
  why: "Confirm the usage-line edit doesn't break its greps; run the suite after editing."
- file: voice_typing/ctl.py         # session/--copy semantics for the hint line (exit 0/1/64,
  why: "'copied N chars', no added newline, clipboard untouched on failure, works in both modes)."
- file: tests/test_voicectl.py      # grep for usage-string pins before editing install.sh

# READ — D3 regression test names to verify at HEAD then cite in row 12.
- file: tests/test_key_listener.py  # grep 'def test_' for autorepeat / repeated_backspace
- file: tests/test_daemon.py        # grep 'def test_' for suppression / sentinel set
```

### Current Codebase tree (task-relevant slice)

```bash
tests/ACCEPTANCE.md            # ← MODIFY (12 §7 rows + evidence block + method notes)
install.sh                     # ← MODIFY (usage echo block :209)
tests/G1_BASELINE.md           # classification authority (READ-ONLY for this task)
tests/D1_DUCK_EVIDENCE.md  tests/G6_GRADUATION.md  tests/G5_TIMING_EVIDENCE.md
tests/G6_WRITING_SESSIONS.md  tests/g6_assessment.py
plan/008_a47116bb2b79/architecture/{g2_gate_record,g3_field_matrix,g3_gtk_rows,g3_editor_browser_rows,
  g4_clipboard_evidence}.md {pi_row_verdicts,editor_browser_row_verdicts,g4_clipboard_verdicts}.jsonl
tests/test_streaming.py  tests/test_streaming_commit.py  tests/test_streaming_core.py
tests/test_streaming_freeze.py  tests/test_daemon.py  tests/test_key_listener.py
README.md                      # S1's file — DO NOT TOUCH
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
tests/ACCEPTANCE.md            # modified: header 1–13+D1, refreshed rows 1/11/12, new D1 + 13 rows
install.sh                     # modified: usage line + session hint line
# no new files (research already in plan/008_a47116bb2b79/P1M7T2S2/research/)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G-REPO-TIMEOUTS — AGENTS.md, non-negotiable): EVERY pytest/voicectl command runs
#   under an inner GNU `timeout` AND a generous bash-tool timeout above it. test_streaming.py is a
#   real-small.en CUDA suite (~106 s); test_daemon.py can load real models (minutes cold) — wrap in
#   `timeout 600`, bash-tool timeout 660+. Exit 124 = "timed out", a FINDING, never "retry blindly".

# CRITICAL #2 (G-NO-PARITY-FAKING — the item's core rule): the G1 contract forbids skips, xfails,
#   or expectation edits to make reds green. Row 11 must NOT claim the trio is green. It reports
#   measured reds split as: (i) legacy lazy-separator reds (pre-classified, expected at HEAD),
#   (ii) watch-set reds (pre-classified), NEW (any red not in the G1 20-row table — name it,
#   report it, flag it in the final summary). Do NOT count a flake flip (test_g_stranded_tail)
#   as fixed or broken — cite its FLAKY class.

# CRITICAL #3 (G-ROW13-FRAMING): row 13's status must encode §7.13's own pass condition — mode
#   shipped + opt-in + claims reported unverified — while REPORTING the unmet gates (G3 matrix
#   rows, edit-count-law, G5 failing routes, 0 writing sessions). Never write "PASS" in a way
#   that reads as "bulk delivery verified"; never upgrade a register row's status; the G6
#   decision line is copied verbatim.

# CRITICAL #4 (G-D1-NUMBERING): PRD §7 numbers 1–13 are fixed; ducking is a §4.2quinquies
#   criterion, NOT §7.14 — label the new row "D1" (or "12½") so §7 numbering stays aligned with
#   the PRD; update the header sentence to say so explicitly.

# CRITICAL #5 (G-INSTALL-PINS): tests/test_systemd_unit.py:205 greps install.sh output strings;
#   test_voicectl.py may pin usage text. Read the greps FIRST, edit SECOND, run BOTH suites after.

# CRITICAL #6 (G-SCOPE): README.md is S1's (parallel); the cross-doc consistency sweep is S3's.
#   No config/source/test/PRD/tasks.json edits. Flag (commit message) any drift you notice —
#   don't fix it.

# CRITICAL #7 (G-D3-NAMES): the D3 regression test names in the research note came from research
#   files — VERIFY each exists at HEAD (`grep -n "def test_..." tests/test_*.py`) before citing;
#   cite what exists, with the -k expression that re-runs them.

# CRITICAL #8 (G-EVIDENCE-TYPING): keep the dossier's LIVE / STATIC / PAST-LIVE vocabulary and
#   the "(Block below)" convention; new rows state their evidence type the same way. Ducking
#   evidence is scripted-LIVE (recorded 2026-11-23, re-runnable); row 13's register evidence is
#   recorded lab evidence — attribute each with its file, never imply operator acceptance.
```

## Implementation Blueprint

### Data models and structure

No code models — this is a documentation task. The "model" is the row schema:
`| # | Criterion (source) | Status | Evidence |` — one line per criterion, evidence cell carries
measured numbers + file paths + re-run commands, using the existing LIVE/STATIC/PAST-LIVE typing.

### Row content to pin

**Row 11 (streaming, §4.2quater) — refreshed shape (numbers from YOUR re-measurement):**

> Status: **PASS with standing G1 reds** (legacy (i) + watch (ii), none NEW) — or, if the
> re-measurement finds reds beyond the G1 table: **PARTIAL — N NEW failures** (named).
>
> Evidence must state: `tests/test_streaming.py` CUDA-gated suite at HEAD = **3 passed / 4
> failed** (expected from G1 flake table: `test_c/d/e` pass; `test_a_delta_cadence` +
> `test_b_commit_rewind_exact` red = the two **(ii) watch-set** reds; `test_f_user_key_freeze`
> red = **(i)/F1** legacy; `test_g_stranded_tail` = **(i)/F5 FLAKY** class — 4F/2P over 6
> observations, single observations prove nothing). The "7/7 green" claim was measured at an
> earlier HEAD and is **superseded** — the four reds are the pre-classified G1 baseline set,
> NOT regressions of this changeset (cite `tests/G1_BASELINE.md` §"Failure classification").
> Mocked trio: `timeout 120 uv run pytest tests/test_streaming_commit.py
> tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=line` = **76 passed /
> 18 failed** → reconcile: 16 = the classified (i) fast reds (commit×10, core×2, freeze×4);
> **each remaining red beyond those 16 is named and marked NEW** with its one-line `--tb=line`
> reason. Keep the existing rollback-hatch citations (`test_on_final_streaming_false_is_verbatim_
> rev1_hatch`, `test_commit_disabled_is_a_noop`) and the `-k` mocked sub-run numbers, re-measured.

**Row 12 (cancel fallback) — append to the existing (re-verified) evidence:**

> D3.2 auto-repeat compensation: `test_autorepeat_ignored` +
> `test_repeated_backspace_presses_route_one_cancel_each` (tests/test_key_listener.py — verify
> names at HEAD). D3.3 suppression-window latch bound (the 4× incident sequence + force-close +
> sentinel self-heal): the `test_cancel_suppression_*` / `test_*sentinel*` /
> `test_arm_clears_stale_cancel_suppression` / `test_fresh_arm_clears_suppress_since` /
> `test_sentinel_consume_clears_suppress_since` set (tests/test_daemon.py). One re-run command:
> `timeout 300 uv run pytest tests/test_daemon.py tests/test_key_listener.py -q -k
> "autorepeat or suppression or sentinel or repeated_backspace" --tb=no` → **N passed**.
> Core claims re-verified unchanged: socket rewind identical, second cancel no-op, listener
> failure logged once at arm.

**NEW ducking row (label `D1`, §4.2quinquies):**

> | D1 | **Media ducking (§4.2quinquies):** music playing → arm → pauses ≤~1 s and resumes at
> stop; `duck_mode="volume"` ducks to `duck_volume_pct` and restores exactly; user
> media/volume changes mid-dictation never overridden; `duck_mode="off"` byte-identical;
> flipped default engages with no `[audio]` key | **PASS** | Scripted-LIVE 2026-11-23:
> `timeout 900 bash tests/d1_duck_evidence.sh` → exit 0, **12/12 scenario checks** — the five
> §4.2quinquies rows mapped to scripted checks incl. **107 ms** MPRIS pause after arm-return
> and exact 40%→15%→40% volume cycle; sovereignty ×4; `off` = zero `ducking:` journal lines;
> default engages with `[audio]` omitted. Evidence: `tests/D1_DUCK_EVIDENCE.md` (journal-line
> excerpts verbatim). Unit: mocked-backend `tests/test_ducking*.py` suites green. |

**NEW row 13 (§7 item 13, bulk text):**

> | 13 | **Bulk text (§4.2sexies):** with `delivery="bulk-text"` every recognition update is
> visible in the focused field with no character-typing fallback; corrections replace verified
> owned text in one visible edit; unchanged results emit zero edits; any takeover/refusal/
> unknown stops delivery without retries or post-stop writes; `voicectl session [--copy]`
> recovers the last nonempty session; graduation to default requires G3+G6 — until then
> opt-in with claims reported unverified | **PASS-as-specified: shipped OPT-IN, claims reported
> UNVERIFIED** (G6: STAY OPT-IN) | Mode live behind `output.delivery="bulk-text"` (default
> `"stream-edit"` unchanged); G2 controller gate 13/13 fake-target traces
> (`plan/008…/architecture/g2_gate_record.md`); G3 field matrix with honest rows — GTK-class
> full, pi-prompt **not verified** (visibility instrumentation absent), browser insert-only
> (correction REFUSED by the ownership guard), `edit-count-law` FAILED (warm-up overcount)
> (`g3_field_matrix.md`, `pi_row_verdicts.jsonl`, `editor_browser_row_verdicts.jsonl`); G4
> clipboard gate L1 unprovable→refuse, L2–L6 verified (`g4_clipboard_verdicts.jsonl`); G5
> timing BOTH routes failing — im-gtk backlog sustained (20 inserts / 0 corrections), pi-ghostty
> speech→visible 12.6 s median (`tests/G5_TIMING_EVIDENCE.md`); **`G6 DECISION: STAY OPT-IN
> (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)`** — 0 of ≥3 operator writing
> sessions (`tests/G6_WRITING_SESSIONS.md`); re-derive: `timeout 60 .venv/bin/python
> tests/g6_assessment.py`. `voicectl session [--copy]`: unit-tested (tests/test_voicectl.py),
> exit 1 no-session, `--copy` only with `session`. |

**Totals edits:** row 1's "**424 LIVE-green**" and the dossier paragraph's "424 … this round"
→ re-measure the cited suites (T1 `tests/test_feed_audio.py`, T2 `tests/test_textproc.py`,
mocked daemon+recorder) with timeout discipline and update the arithmetic; any suite not
re-runnable this session keeps its recorded number **explicitly attributed to its capture
round** (the 006 dossier). The dossier cross-reference sentence to
`plan/006_862ee9d6ef41/…/acceptance_gate.md` stays (historical) but must not present 006-round
numbers as current.

**install.sh edit (exact):**

```bash
# line ~209, before:
echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|cancel|quit"
# after:
echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|cancel|session|quit"
# and append one hint line after the SUPER+ALT+Backspace line:
echo "          (voicectl session [--copy] prints or copies the last completed dictation - no added newline)"
```
(Adjust the hint wording to match `ctl.py` semantics exactly; keep the block's style — no
emoji, plain dashes if the file avoids UTF-8 punctuation there.)

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT (read-only):
  - READ tests/ACCEPTANCE.md (whole file), tests/G1_BASELINE.md (classification + flake table),
    tests/G6_GRADUATION.md (decision line), tests/D1_DUCK_EVIDENCE.md (scenario table).
  - GREP the install.sh pins: grep -n "usage\|summary" tests/test_systemd_unit.py tests/test_voicectl.py
  - RECORD HEAD: git rev-parse --short HEAD (the re-measured numbers' provenance).

Task 1: RE-MEASURE row 11/12 evidence (timeout discipline — inner timeout + bash-tool margin):
  - RUN: timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_streaming.py -q --tb=line
  - RUN: timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=line
  - RUN: timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_daemon.py -q -k "rejected_final_recovers or cancel_then_next_utterance or stop_after_cancel or on_partial_gated or user_keypress_frozen or cancel_suppression_drops or next_utterance_after_cancel" --tb=no
  - RUN: timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_daemon.py tests/test_key_listener.py -q -k "autorepeat or suppression or sentinel or repeated_backspace" --tb=no
  - RECONCILE every FAILED name against tests/G1_BASELINE.md's 20-row table; classify (i)/(ii)/NEW.
  - If totals differ from the research note (3/7, 76/18): YOUR numbers win; note the drift.

Task 2: RE-MEASURE totals (row 1 + dossier paragraph):
  - RUN: timeout 600 uv run pytest tests/test_feed_audio.py -q ; timeout 300 uv run pytest tests/test_textproc.py -q
  - RUN (mocked, may be slow cold): timeout 600 uv run pytest tests/test_daemon.py tests/test_recorder_host.py -q
  - Any 124/timeout or hang vector: keep the recorded number, attribute its round explicitly.

Task 3: MODIFY tests/ACCEPTANCE.md — header sentence, row 1 + dossier totals, row 11, row 12,
  new D1 row, new row 13 (content pinned above; use YOUR measured numbers).

Task 4: MODIFY install.sh — usage line + session hint (Task list above); bash -n install.sh.

Task 5: VALIDATE — run the Validation Loop below; fix until green. If committing:
  "P1.M7.T2.S2: ACCEPTANCE.md rows (D1 + #13, refresh 11/12 + totals) + install.sh session usage".
```

### Integration Points

```yaml
CONSUMED (read-only): tests/G1_BASELINE.md (classification), tests/D1_DUCK_EVIDENCE.md,
  tests/G6_GRADUATION.md + tests/g6_assessment.py, tests/G5_TIMING_EVIDENCE.md,
  tests/G6_WRITING_SESSIONS.md, plan/008…/architecture/{g2_gate_record,g3_field_matrix,
  pi_row_verdicts,editor_browser_row_verdicts,g4_clipboard_verdicts}*, voice_typing/ctl.py.
PRODUCED: tests/ACCEPTANCE.md (14 rows, current numbers), install.sh (7-command usage).
DOWNSTREAM: P1.M7.T2.S3 (final consistency sweep + commit discipline) consumes this state and
  aligns README↔ACCEPTANCE↔config claims.
PARALLEL: P1.M7.T2.S1 edits README.md only — no overlap; do not touch README.
```

## Validation Loop

> Repo-root, two-layer timeouts per AGENTS.md. All measured numbers quoted in the file must come
> from commands run THIS session at the recorded HEAD.

### Level 1: Structure (after editing ACCEPTANCE.md)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
rows=$(grep -c "^| [0-9D]" tests/ACCEPTANCE.md)          # expect 14 (1..12, D1, 13)
[ "$rows" = 14 ] || { echo "FAIL: row count $rows != 14"; exit 1; }
grep -q "criteria 1–13" tests/ACCEPTANCE.md || { echo "FAIL: header scope not updated"; exit 1; }
grep -q "^| D1 " tests/ACCEPTANCE.md || { echo "FAIL: ducking row missing"; exit 1; }
grep -q "^| 13 " tests/ACCEPTANCE.md || { echo "FAIL: row 13 missing"; exit 1; }
grep -q "G6 DECISION: STAY OPT-IN" tests/ACCEPTANCE.md || { echo "FAIL: G6 line not verbatim"; exit 1; }
grep -q "D1_DUCK_EVIDENCE.md" tests/ACCEPTANCE.md || { echo "FAIL: duck evidence not linked"; exit 1; }
grep -q "G1_BASELINE.md" tests/ACCEPTANCE.md || { echo "FAIL: classification not cited"; exit 1; }
echo "L1 OK"
'
```

### Level 2: Staleness purge + reconciliation integrity

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
! grep -q "7/7 green" tests/ACCEPTANCE.md   || { echo "FAIL: stale 7/7 claim remains"; exit 1; }
! grep -q "77 passed" tests/ACCEPTANCE.md   || { echo "FAIL: stale 77-passed claim remains"; exit 1; }
# every 424 must now be round-attributed or replaced:
if grep -q "424" tests/ACCEPTANCE.md; then grep -q "424.*\(006\|round\|recorded\)" tests/ACCEPTANCE.md \
  || { echo "FAIL: bare 424 totals"; exit 1; }; fi
# row 11 carries the measured split vocabulary:
grep -q "3 passed / 4 failed\|3/7" tests/ACCEPTANCE.md || { echo "FAIL: streaming number missing"; exit 1; }
grep -qi "new failure\|NEW" tests/ACCEPTANCE.md || { echo "FAIL: NEW-failure reconciliation absent"; exit 1; }
# no skips/xfails were added anywhere to fake parity (repo-wide guard):
! git diff -- tests/ | grep -q "pytest.mark.skip\|xfail" || { echo "FAIL: parity faking"; exit 1; }
echo "L2 OK"
'
```

### Level 3: install.sh correctness

```bash
cd /home/dustin/projects/voice-typing
bash -n install.sh || { echo "FAIL: syntax"; exit 1; }
timeout 60 bash -c '
grep -q "toggle|start|stop|status|cancel|session|quit" install.sh || { echo "FAIL: session missing from usage"; exit 1; }
grep -q "session \[--copy\]" install.sh || { echo "FAIL: session hint missing"; exit 1; }
echo "L3a OK"
'
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_systemd_unit.py tests/test_voicectl.py -q \
  || { echo "FAIL: install.sh/voicectl pins broke"; exit 1; }
```

### Level 4: Evidence re-derivability (G6 + ducking rows point at runnable truth)

```bash
cd /home/dustin/projects/voice-typing
# G6 decision re-derives to the same verdict the row quotes:
timeout 60 .venv/bin/python tests/g6_assessment.py | grep "G6 DECISION" | diff - <(grep -o "G6 DECISION: .*" tests/G6_GRADUATION.md | head -1) \
  || { echo "NOTE: G6 verdict drifted since the doc — re-derive row 13 framing from the NEW output"; }
# duck evidence script is present + checked in (re-RUNNING it is NOT required for this docs task):
test -x tests/d1_duck_evidence.sh && grep -q "12/12\|ALL 12" tests/D1_DUCK_EVIDENCE.md || { echo "FAIL: duck evidence unreadable"; exit 1; }
# scope:
timeout 60 bash -c '[ "$(git diff --name-only | grep -v "^plan/" | sort)" = "$(printf "install.sh\ntests/ACCEPTANCE.md")" ] \
  || { echo "FAIL: out-of-scope edits"; git diff --name-only; exit 1; } && echo "L4 OK"'
```

## Final Validation Checklist

### Technical

- [ ] L1 structure (14 rows, D1 + 13 present, G6 line verbatim, evidence files linked).
- [ ] L2 staleness purge (no 7/7, no 77-passed, no unattributed 424; NEW-failure split present;
      no skip/xfail added).
- [ ] L3 `bash -n` + usage strings + `test_systemd_unit.py`/`test_voicectl.py` green.
- [ ] L4 G6 re-derivation consistent (or row re-framed); scope = the two files.

### Feature

- [ ] Row 11 numbers are THIS session's measurements at the recorded HEAD, split
      (i)-legacy / (ii)-watch / NEW by name, flake class cited for `test_g_stranded_tail`.
- [ ] Row 12 re-verified + D3 test citations exist at HEAD and their `-k` run passes.
- [ ] D1 row: 12/12 + journal lines + re-run command; row 13: verbatim G6 decision, honest
      unmet-gate reporting, session recovery cited.
- [ ] install.sh usage: 7 commands + `session [--copy]` hint matching `ctl.py` semantics.

### Code Quality (doc equivalents)

- [ ] Existing dossier voice/evidence-typing (LIVE/STATIC/PAST-LIVE) preserved; §7 numbering
      untouched; D1 labeled as §4.2quinquies, not §7.14.
- [ ] No over-claim anywhere: bulk stays "unverified until G6"; no register row upgraded;
      no "works on Wayland"-class phrases.
- [ ] Drift noticed outside scope (README/config inconsistencies) flagged in the commit
      message — left for S3.

### Documentation & Deployment

- [ ] Provenance recorded: HEAD sha + date for every re-measured number.
- [ ] install.sh stdout remains a coherent quick-start (print the block once to eyeball).

---

## Anti-Patterns to Avoid

- ❌ Don't soften reds into greens — the G1 contract forbids parity faking; NEW reds are
  reported, never hidden, skipped, or reclassified.
- ❌ Don't re-run heavy CUDA/E2E suites unnecessarily — cite committed evidence
  (D1/G5/G6/registers); re-measure only what the rows' own citations claim as current.
- ❌ Don't edit `tests/G1_BASELINE.md`, any test file, `config.*`, `README.md`, `PRD.md`, or
  `tasks.json` — this task owns exactly two files.
- ❌ Don't run any command without the inner `timeout` (AGENTS.md Rule 1) — 124 is a finding.
- ❌ Don't present 006-round numbers (424 etc.) as current — attribute or re-measure.
- ❌ Don't guess the G6 verdict or D3 test names — read the files / grep HEAD first.

---

## Confidence Score

**8/10.** The two files, every row's target content, the classification authority, the evidence
paths, the install.sh target line, and the pinning tests are all pinned with verbatim anchors;
the validation loop mechanically greps the exact outcomes (row count, stale-claim purge, G6
verbatim, scope). The −2: (1) the re-measured numbers themselves can drift from the research
note's 3/7 and 76/18 — the PRP handles this by making the implementer's fresh numbers
authoritative with the reconciliation rules doing the work; (2) the count of NEW trio reds and
their identity is genuinely unknown until measured — the decision rules (name them, report
them, escalate) are specified, but the row's final status line depends on what is found.
