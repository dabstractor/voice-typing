# PRP — P1.M7.T2.S3: Final consistency sweep + commit discipline

## Goal

**Feature Goal**: Close the Rev-3/4 delta changeset with a **verification sweep**: walk every
user-facing documentation surface — `README.md`, `tests/ACCEPTANCE.md`, `config.toml` comments,
`voicectl --help` (+ `install.sh` usage) — against the code **as landed**, confirm no claim
anywhere over-states what is verified (every unverified claim stays labeled unverified), confirm
the G1 watch set shows **no unexplained new failures** vs `tests/G1_BASELINE.md`, confirm the
repo is clean and all work is committed on `main` with sensible messages, and append the **final
sign-off note** to the acceptance dossier. This satisfies delta acceptance #4 verbatim
(`plan/008_a47116bb2b79/delta_prd.md:98`): "All work under AGENTS.md discipline (two timeouts
on every non-trivial command; never foreground the daemon; bounded scratch); everything
committed to `main` with sensible messages" — plus the #2 tail rule: "No over-claiming: any
field/latency not verified stays labeled unverified."

**Deliverable**:
- `tests/ACCEPTANCE.md` — (a) NEW `## Final sign-off (P1.M7.T2.S3)` section at the end (Mode B:
  it documents the sweep itself — surfaces walked, verdicts, G1 re-run, git state, fixes,
  flagged findings); (b) residual doc-drift fixes found by the sweep (known: row 7's stale
  sign-off pointer "P1.M6.T1.S3" → this task/section).
- Optional bounded fixes in `README.md` / `config.toml` comments ONLY where a claim mismatches
  landed behavior (comment/prose edits; never values, never code).
- One or more commits on `main` in the repo convention, e.g.
  `Final doc consistency sweep + dossier sign-off (P1.M7.T2.S3)`, including the
  `plan/008_a47116bb2b79/P1M7T2S{1,2,3}/` PRP+research dirs so the tree ends clean.
- Research notes in `plan/008_a47116bb2b79/P1M7T2S3/research/` (sweep matrix).

**Success Definition**:
- (a) Every claim on the four surfaces matches landed behavior or carries an explicit
  unverified/opt-in label; the `G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity,
  C-g5-timing, D-sessions)` line appears VERBATIM in ACCEPTANCE.md; G3-matrix row statuses are
  never upgraded; greps for stale numbers (`7/7`, `77 passed`, bare `424`) find only
  round-attributed historical uses.
- (b) The G1 15-suite re-run (baseline-parity methodology) shows the 16 fast (i) reds EXACTLY
  as the named set; watch-set reds accounted for; any failure beyond the 20-row table is
  named, drift-addended to `tests/G1_BASELINE.md` (one bounded row), and escalated — never
  hidden, never reclassified, never "fixed".
- (c) `git branch --show-current` = `main`; `git status --porcelain` is empty except possibly
  the orchestrator's `plan/008_a47116bb2b79/tasks.json` (flagged, not committed by you); commit
  messages follow the repo convention.
- (d) The sign-off section exists, is self-contained (date + HEAD sha), and cites re-run
  commands + outputs — "demonstrated by actual command output (not claimed)" per PRD §7.1.

## User Persona

**Target User**: (1) the operator + any future auditor reading the dossier as the PRD §7.1
record — this note is the LAST word on whether the changeset's claims are honest; (2) a
fresh-cloner whose first impressions of ducking/bulk/session come from README, `config.toml`
comments, and `voicectl --help`.

**Use Case**: auditor reads the sign-off → sees each surface was walked with named checks and
re-run commands → re-runs any check and gets the stated result.

**User Journey**: (task, not runtime) preflight siblings landed → build sweep matrix → re-run
G1 set → audit over-claiming → fix residual doc drift → commit → write sign-off → final gates.

**Pain Points Addressed**: docs drift from shipped behavior after a 50-commit changeset;
stale sign-off pointer (row 7 names a dead plan-006 task); risk that opt-in bulk mode reads as
"verified" anywhere; risk that a regression slipped in during the doc tail unobserved.

## Why

- **Delta acceptance #4** is the item's own definition of done (see Goal, verbatim).
- **PRD §7.1**: acceptance must be "demonstrated by actual command output (not claimed)" — the
  sign-off note is that demonstration for the doc sweep itself (Mode B).
- **PRD §7.13 tail / R.7 no-over-claim rule**: bulk-text stays opt-in with unverified claims
  until G6 — the sweep is the final enforcement pass over every surface.
- **G1 contract** (`tests/G1_BASELINE.md`): "Every later subtask diffs its post-change suite
  results against THIS file; drift from these numbers is a finding to investigate, never to
  'fix' silently." S3 is the last subtask — it runs that diff.
- **PRD §7.7**: "Everything committed to git; README documents …" — the formal close-out.

## What

1. **Preflight (read-only)**: confirm S1 and S2 landed — `git log --oneline | grep -E
   "P1\.M7\.T2\.S[12]"` shows their commits; README has the ducking/bulk/session sections;
   ACCEPTANCE.md has 14 rows (`grep -c "^| [0-9D]"` = 14) incl. `^| D1 ` and `^| 13 `;
   `install.sh` usage line lists `session`. If any is absent → STOP, report; do not
   re-implement a sibling's task.
2. **Build the sweep matrix** (research notes): one row per claim-cluster × surface ×
   landed-behavior check (file:line or command) × verdict. Surfaces:
   - **README.md** — ducking section claims (default `duck_mode="mpris"` with evidence,
     sovereignty guarantees, `[audio]` keys) vs `voice_typing/config.py` defaults +
     `tests/D1_DUCK_EVIDENCE.md`; bulk section (opt-in flag, precondition triple
     streaming/graceful_stop/keypress_action, delivery states, `voicectl session`,
     "unverified until G3/G6" framing, per-terminal matrix) vs
     `voice_typing/bulk_*` + `tests/G6_GRADUATION.md`; config table values vs `config.toml` +
     `config.py`; troubleshooting rows vs landed behavior; command list in "Logs, status,
     stopping" vs `_COMMANDS`.
   - **tests/ACCEPTANCE.md** — row claims vs their cited evidence files; totals attribution;
     LIVE/STATIC/PAST-LIVE typing intact.
   - **config.toml comments** — every comment matches the `config.py` default and README table;
     no comment implies bulk-text is default or verified (default is `"stream-edit"`).
   - **`voicectl --help` + install.sh usage** — enumerate `_COMMANDS` in
     `voice_typing/ctl.py` (grep near the `cmd not in _COMMANDS` check ~:375); diff the
     epilog (:333), README command table, and install.sh usage (~:209) against it. Known
     suspect: the epilog names `toggle, start, stop, status, quit, cancel, session` but not the
     lite arming commands — if `_COMMANDS` contains them and any surface omits (or any surface
     lists a command `_COMMANDS` rejects), that is a finding: fix the DOC surface; for the
     ctl.py epilog string, fixing is allowed ONLY with `tests/test_voicectl.py` +
     `tests/test_control_socket.py` green after (usage text may be pinned there).
3. **G1 watch-set confirmation**: re-run the 15 G1 suites exactly per baseline methodology
   (below), diff totals + FAILED names vs `tests/G1_BASELINE.md`'s table and 20-row
   classification. Verdict rules: 16 fast (i) reds = exact set (no growth/shrinkage);
   watch-set (ii) reds expected/recorded; `test_g_stranded_tail` = FLAKY class (single
   observation proves nothing — do not chase); anything else = NEW failure → name it, append
   ONE bounded drift-addendum row to `tests/G1_BASELINE.md`, escalate in the sign-off.
4. **Over-claiming audit**: targeted greps (`7/7`, `77 passed`, unqualified `424`, `verified`
   near bulk/ducking claims) + semantic read of the bulk sections/row 13; verify the G6 line is
   verbatim and no register row's status is upgraded anywhere.
5. **Fix residual drift** (doc-level only): ACCEPTANCE row 7's "P1.M6.T1.S3" sign-off pointer
   → "the `## Final sign-off (P1.M7.T2.S3)` section below"; any README/config-comment claim
   corrections. NEVER: source values, test expectations, `tests/G1_BASELINE.md`
   classifications, PRD/plan docs other than your own dir, `tasks.json`.
6. **Commit discipline**: stage and commit all work on `main` (convention: imperative
   one-liner + `(P1.M7.T2.S3)`); include the plan PRP/research dirs; leave `tasks.json` to the
   orchestrator (flag it). Do not push (criterion is "committed", not pushed; `ahead 51` is
   expected).
7. **Write the sign-off note** (format pinned in Blueprint) and commit it last.

### Success Criteria

- [ ] Preflight passed; siblings' deliverables present as committed work.
- [ ] Sweep matrix exists in research/ with a verdict for every surface.
- [ ] G1 re-run recorded (15 suites, totals + names) with the (i)/(ii)/FLAKY/NEW split.
- [ ] G6 decision line verbatim; no upgraded row statuses; stale-number greps clean.
- [ ] Row 7 pointer corrected; all residual drift fixed or explicitly flagged.
- [ ] Sign-off section appended, self-contained, cites commands + HEAD sha.
- [ ] `main`, clean tree (modulo tasks.json), sensible messages.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs: the two sibling PRPs (contracts for what S1/S2 produced), the
G1 baseline + its protocol, the dossier's current shape, the config/help surfaces, the evidence
files, the git conventions, and the AGENTS.md timeout discipline — all pinned below with paths
and anchors. No prior knowledge assumed beyond reading these.

### Documentation & References

```yaml
# MUST READ — this session's fact ledger (surfaces, G1 protocol, git facts, sequencing).
- file: plan/008_a47116bb2b79/P1M7T2S3/research/sweep_surfaces_signoff_facts.md
  why: "Every fact below with file:line cites; the PRP derives from it."

# MUST READ — sibling contracts (S3's inputs; treat as landed).
- file: plan/008_a47116bb2b79/P1M7T2S1/PRP.md
  why: "What the README sections must contain (ducking/bulk framing, config rows,
        troubleshooting) — the sweep verifies against these expectations."
- file: plan/008_a47116bb2b79/P1M7T2S2/PRP.md
  why: "What ACCEPTANCE.md + install.sh must contain (14 rows, D1 + 13 content, totals,
        session usage) + S2's success criteria (a)–(e), which S3 re-verifies."

# MUST READ — the four surfaces being swept (read in full / grep per matrix).
- file: README.md                # sections: Media ducking :204, Bulk text :251, Session
  why: "recovery :308, Takeover :318, Configuration :343, Logs/status :532, Troubleshooting :432+"
- file: tests/ACCEPTANCE.md      # 14 rows + evidence block + method notes (LIVE/STATIC/PAST-LIVE)
- file: config.toml              # Mode A self-documenting; lockstep contract in header
- file: voice_typing/ctl.py      # usage/epilog :333-:343, exit-64 path :353-:375 (_COMMANDS)
- file: install.sh               # usage echo block ~:209

# MUST READ — the G1 classification authority (read in full).
- file: tests/G1_BASELINE.md
  why: "15-suite table (380P/19F), 20-row (i)/(ii) classification, facet taxonomy F1–F5,
        watch set + 3-run flake table + decision rules, contract statement."
  critical: "READ-ONLY except ONE bounded drift-addendum row IF a new failure appears. Never
             reclassify; never edit to make parity look better."

# READ — evidence the over-claiming audit checks against (headers/verdict lines).
- file: tests/G6_GRADUATION.md   # 'G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity,
  why: "C-g5-timing, D-sessions)' — the verbatim line; per-condition table. Re-derive if absent:
        timeout 60 .venv/bin/python tests/g6_assessment.py — never soften 'unmet'."
- file: tests/G5_TIMING_EVIDENCE.md   # both routes failing; im-gtk backlog; pi-ghostty 12.6 s
- file: tests/G6_WRITING_SESSIONS.md  # 0 valid sessions (the outstanding G6 input)
- file: tests/D1_DUCK_EVIDENCE.md     # 12/12 checks, 107 ms pause (re-run only if disputed)
- file: plan/008_a47116bb2b79/architecture/g3_field_matrix.md  # honest row statuses — never upgrade

# READ — pinning tests to run if you touch their surfaces.
- file: tests/test_config.py + tests/test_config_repo_default.py  # config lockstep (key set)
- file: tests/test_voicectl.py + tests/test_control_socket.py     # usage-string pins
- file: tests/test_systemd_unit.py                                # :205 greps install.sh strings

# MUST READ — repo operating discipline (hang vectors; two-layer timeouts).
- file: AGENTS.md                # non-negotiable for every command you run
```

### Current Codebase tree (task-relevant slice)

```bash
README.md  tests/ACCEPTANCE.md  config.toml  install.sh     # sweep surfaces (doc-level)
voice_typing/ctl.py                                            # --help surface (code-embedded)
tests/G1_BASELINE.md                                           # classification authority (read-only)
tests/{G6_GRADUATION,G6_WRITING_SESSIONS,G5_TIMING_EVIDENCE,D1_DUCK_EVIDENCE}.md
plan/008_a47116bb2b79/architecture/{g2_gate_record,g3_field_matrix}.md
plan/008_a47116bb2b79/P1M7T2S{1,2,3}/                          # sibling + own PRPs (commit)
# G1 suites (15): test_streaming{,_commit,_core,_freeze}.py test_zero_diff_rewind.py
#   test_key_listener.py test_control_socket.py test_config{,_repo_default}.py
#   test_textproc.py test_typing_backends.py test_voicectl.py test_feedback.py
#   test_prompt_engine.py test_context_prompt_refresh.py
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
tests/ACCEPTANCE.md        # modified: sign-off section appended (+ row-7 pointer fix, + residual fixes)
README.md                  # modified ONLY if sweep finds claim drift (prose/comments)
config.toml                # modified ONLY if comment drift found (never values)
plan/008_a47116bb2b79/P1M7T2S3/research/sweep_matrix.md   # NEW: the claim×check×verdict matrix
# tests/G1_BASELINE.md: +1 bounded drift-addendum row ONLY if a new failure appears
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G-TIMEOUTS — AGENTS.md, non-negotiable): EVERY pytest/voicectl command runs
#   under an inner GNU `timeout` AND a bash-tool timeout above it. G1 methodology parity:
#   `timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q --tb=line`, ONE FILE PER CALL,
#   bash-tool ≥ 360. test_streaming.py is real-CUDA (~106 s); the contract-forbidden hang
#   vectors (test_feed_audio, test_daemon, test_recorder_host, test_cuda_check) are NOT in the
#   G1 set — do not run them for this task. `voicectl --help` is socket-free (argparse exits
#   first) → `timeout 15 .venv/bin/voicectl --help` is safe; NEVER run voicectl status against
#   a possibly-dead daemon untimed; NEVER foreground the daemon.

# CRITICAL #2 (G-NO-PARITY-FAKING): the G1 contract forbids skips/xfails/expectation edits; the
#   16 fast (i) reds STAY RED and must remain the exact named set. A red beyond the 20-row
#   table is a NEW failure: name it, addendum it, escalate it. test_g_stranded_tail is FLAKY
#   (4F/2P over 6 obs) — a single flip proves nothing in either direction.

# CRITICAL #3 (G-NO-OVER-CLAIM): the G6 line is copied VERBATIM; never write "PASS" in a way
#   that reads as "bulk delivery verified"; never upgrade a G3-matrix row status; any
#   field/latency not verified stays labeled unverified (delta_prd.md:96).

# CRITICAL #4 (G-SCOPE): README is S1's, ACCEPTANCE/install.sh are S2's — verify, don't redo.
#   Fixes are DOC-LEVEL ONLY: no source values, no test expectations, no PRD/plan docs outside
#   your own dir, no tasks.json (orchestrator-owned). Code-side drift (e.g. ctl.py epilog) is
#   FLAGGED in the sign-off; edit it only per the narrow rule in What #2, then run the pinning
#   suites.

# CRITICAL #5 (G-CONFIG-LOCKSTEP): config.toml comments must stay in lockstep with config.py
#   defaults (unknown keys/tables are REJECTED at load; key set pinned by test_config.py).
#   Comment-only edits still get the two config suites re-run.

# CRITICAL #6 (G-GIT): branch must be `main`; `plan/` is tracked — commit the P1M7T2S{1,2,3}
#   dirs; leave tasks.json to the orchestrator and flag it; do not push; message convention
#   "Add/Sync/Fix <thing> (P1.M7.T2.S3)".

# CRITICAL #7 (G-SIBLING-GATE): if S1 or S2 output is missing at preflight, STOP and report —
#   sweeping a half-state produces a false sign-off, the exact failure mode this task exists
#   to prevent.
```

## Implementation Blueprint

### Data models and structure

No code models. Two artifacts: (1) **sweep matrix** — a markdown table
`| Surface | Claim (file:line) | Landed-behavior check | Verdict | Fix/Flag |`; (2) **sign-off
note** — the dossier section pinned below.

### G1 re-run commands (baseline-parity; one file per call, bash-tool timeout ≥ 360)

```bash
cd /home/dustin/projects/voice-typing
for f in test_streaming_commit test_streaming_core test_streaming_freeze test_zero_diff_rewind \
         test_key_listener test_control_socket test_config test_config_repo_default \
         test_textproc test_typing_backends test_voicectl test_feedback test_prompt_engine \
         test_context_prompt_refresh; do
  timeout 300 /home/dustin/.local/bin/uv run pytest "tests/$f.py" -q --tb=line
done
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_streaming.py -q --tb=line  # real CUDA ~106 s
```
Expected (baseline): fast suites 22/10, 32/2, 22/4, 3/0, 32/0, 27/0, 54/0, 3/0, 31/0, 36/0,
36/0, 38/0, 28/0, 12/0; streaming 4P/3F (g may flip — FLAKY class). Record YOUR numbers; diff
FAILED names against the 20-row table; classify per the decision rules.

### Sign-off note format (append to tests/ACCEPTANCE.md)

```markdown
## Final sign-off (P1.M7.T2.S3) — delta changeset consistency sweep

Recorded <DATE> at HEAD `<sha>` (`git rev-parse --short HEAD`). Delta acceptance #4: AGENTS.md
discipline held; everything committed to `main` with sensible messages. Mode B: this section
verifies the doc sweep itself.

### Surfaces walked (verdict per surface)
| Surface | Verdict | Checks performed (commands/files) |
|---|---|---|
| README.md | <CLEAN | FIXED: … | FLAGGED: …> | … |
| tests/ACCEPTANCE.md (14 rows) | … | row-claims vs cited evidence files … |
| config.toml comments | … | lockstep vs config.py + README table … |
| voicectl --help + install.sh usage | … | _COMMANDS enumeration vs epilog/README/install.sh … |

### No-over-claiming audit
G6 decision line verbatim-checked; register row statuses un-upgraded; stale-number greps
(`7/7`, `77 passed`, bare `424`) → <results>; bulk-text framing opt-in/unverified on every
surface that mentions it.

### G1 watch set — no unexplained new failures
15-suite re-run at HEAD: <totals>. 16 fast (i) reds = exact set <confirm/drift>; watch set
(ii) <status>; test_g_stranded_tail <obs> (FLAKY class). NEW failures: <none | named + addendum
row in tests/G1_BASELINE.md + escalation>.

### Repo state
Branch `main`; `git status --porcelain` (excl. orchestrator tasks.json): clean; commits this
task: <hashes + subjects>; plan/008 P1M7T2S{1,2,3} dirs committed.

### Fixes applied by this sweep / Flagged, not fixed (code-side)
<lists; each flagged item names file:line + recommendation + owner suggestion>
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT (read-only):
  - git log --oneline | grep -E "P1\.M7\.T2\.S[12]"   # both siblings committed?
  - grep -c "^| [0-9D]" tests/ACCEPTANCE.md            # = 14
  - grep -n "session" install.sh | head                # usage line updated?
  - grep -n "^## " README.md | grep -E "ducking|Bulk"  # S1 sections present?
  - RECORD HEAD sha + date for the sign-off.
  - If any check fails → STOP and report (G-SIBLING-GATE).

Task 1: SWEEP MATRIX (research/sweep_matrix.md):
  - Build the table per Blueprint; every row cites file:line (claim) and a landed-behavior
    check (file:line of code/default, or a unit-test grep, or voicectl --help output).
  - Enumerate _COMMANDS (grep -n "_COMMANDS" voice_typing/ctl.py) and diff the four command
    surfaces (epilog, README table, install.sh usage, README hotkey section).

Task 2: G1 RE-RUN (commands above; record totals + FAILED names; classify; drift-addendum
  ONLY if a new failure; keep G1_BASELINE.md otherwise untouched).

Task 3: OVER-CLAIM AUDIT (greps + semantic read; verify G6 verbatim; check no row upgrades).

Task 4: FIX residual doc drift (row-7 pointer mandatory; others as found; rerun affected
  pinning suites: config pair for config.toml, voicectl+control_socket for ctl.py help,
  systemd_unit for install.sh — only for surfaces actually touched).

Task 5: COMMIT on main (repo convention; include plan/008_a47116bb2b79/P1M7T2S{1,2,3}/;
  exclude tasks.json; sensible messages, e.g. "Sync docs to landed behavior (P1.M7.T2.S3)"
  then "Final doc consistency sweep + dossier sign-off (P1.M7.T2.S3)" — or one commit if small).

Task 6: WRITE sign-off section (format above) with YOUR measured results; commit; re-verify
  git state (branch/porcelain) as the last action; update the matrix with final verdicts.
```

### Integration Points

```yaml
CONSUMED (read-only): sibling PRPs + their landed outputs; tests/G1_BASELINE.md;
  G6/G5/G6-sessions/D1 evidence files; architecture/ registers; voice_typing/{config,ctl}.py.
PRODUCED: tests/ACCEPTANCE.md sign-off section + residual fixes; README/config.toml comment
  fixes (as found); research/sweep_matrix.md; commits on main.
DOWNSTREAM: none — this is the changeset's terminal task; the sign-off is the dossier's last word.
PARALLEL: none remaining; S1/S2 must already be landed (preflight gates this).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
grep -q "## Final sign-off (P1.M7.T2.S3)" tests/ACCEPTANCE.md || { echo "FAIL: sign-off missing"; exit 1; }
[ "$(grep -c "^| [0-9D]" tests/ACCEPTANCE.md)" = 14 ] || { echo "FAIL: rows != 14"; exit 1; }
grep -q "G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)" tests/ACCEPTANCE.md \
  || { echo "FAIL: G6 line not verbatim"; exit 1; }
! grep -n "P1\.M6\.T1\.S3" tests/ACCEPTANCE.md | grep -qv "historical\|plan-006\|006" || { echo "FAIL: stale row-7 pointer"; exit 1; }
grep -qn "7/7\|77 passed" README.md tests/ACCEPTANCE.md && echo "WARN: check round-attribution of old numbers"
bash -n install.sh || { echo "FAIL: install.sh syntax"; exit 1; }
echo L1-OK'
# Expected: L1-OK (WARN lines investigated and resolved or attributed).
```

### Level 2: Unit Tests (Component Validation)

```bash
# G1 set re-run is Task 2 (recorded in the matrix + sign-off). Post-fix pinning suites, only
# for surfaces touched:
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_config.py tests/test_config_repo_default.py -q   # if config.toml touched
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_voicectl.py tests/test_control_socket.py -q       # if ctl.py help touched
timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_systemd_unit.py -q                                 # if install.sh touched
# Expected: all green. If a doc edit breaks a pin, the PIN reflects intended behavior — fix the
# doc, not the test.
```

### Level 3: Integration Testing (System Validation)

```bash
timeout 15 .venv/bin/voicectl --help        # socket-free; output vs _COMMANDS enumeration
git branch --show-current                    # main
git status --porcelain | grep -v "plan/008_a47116bb2b79/tasks.json" | wc -l   # 0
git log --oneline -5                         # sensible messages, item ids present
# Expected: help lists every real command; branch main; clean tree; convention messages.
# NEVER run the daemon in the foreground; no daemon is needed for this task.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# The sweep matrix IS the domain validation — every row has an executed check behind it.
# Over-claim greps (each hit must be round-attributed or relabeled, never silently kept):
timeout 60 bash -c 'grep -n "424" tests/ACCEPTANCE.md README.md | grep -v "006\|round\|P1M5" || true'
# G6 re-derivation only if the verbatim line is missing anywhere it must appear:
timeout 60 .venv/bin/python tests/g6_assessment.py
# Expected: matrix complete; greps clean or attributed; G6 output unchanged (STAY OPT-IN).
```

## Final Validation Checklist

### Technical Validation

- [ ] Levels 1–4 executed with two-layer timeouts on every command (AGENTS.md discipline).
- [ ] G1 15-suite re-run recorded; 16 (i) reds exact; watch set accounted; no unexplained NEW.
- [ ] Pinning suites green for every touched surface.
- [ ] `git status --porcelain` clean except orchestrator tasks.json (flagged in sign-off).

### Feature Validation

- [ ] All success criteria from "What" met; preflight gated siblings landed.
- [ ] Four surfaces walked with per-surface verdicts in the sign-off.
- [ ] G6 line verbatim; no upgraded statuses; unverified labels intact everywhere.
- [ ] Row 7 sign-off pointer redirected; flagged-not-fixed list complete.

### Code Quality Validation

- [ ] Doc-only changes (plus at most the ctl.py epilog string under its pinning-suite rule).
- [ ] No edits to tests/G1_BASELINE.md classifications, PRD, plan docs outside your dir,
      tasks.json, source values, or test expectations.
- [ ] Sign-off is self-contained (date, HEAD sha, commands, results).

### Documentation & Deployment

- [ ] Commit messages follow the repo convention with `(P1.M7.T2.S3)`.
- [ ] Nothing pushed; work is on local `main`.

---

## Anti-Patterns to Avoid

- ❌ Don't sweep a half-state — preflight-gate on S1+S2 being landed.
- ❌ Don't "fix" G1 reds, reclassify them, or edit the baseline to make parity look better.
- ❌ Don't soften "unmet"/"unverified" wording or upgrade a register row to pass the vibe check.
- ❌ Don't run untimed commands, foreground the daemon, or poke voicectl status at a dead socket.
- ❌ Don't edit code/test values in a docs task — flag code-side drift instead.
- ❌ Don't commit tasks.json or push; don't leave uncommitted repo deliverables behind.

---

**Confidence Score: 9/10** — verification/docs task with fully pinned sibling contracts, an
explicit G1 protocol, known drift targets (row-7 pointer, epilog command set), and mechanical
gates; the only residual risk is sibling output landing later than expected, which the
preflight gate handles by stopping rather than guessing.
