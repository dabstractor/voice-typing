# PRP — P1.M3.T2.S2: Audit voicectl CLI (ctl.py) — all commands, formatting, loading hint, exit codes & run tests (vs PRD §4.8 / §4.2bis / §4.2ter)

## Goal

**Feature Goal**: Produce the authoritative **voicectl CLI audit** for `voice_typing/ctl.py`
(`main`/`format_result`/`send_command`/`_send_command_with_loading_hint`/`_build_parser`/`_COMMANDS`)
against PRD §4.8 (+ §4.2bis loading hint + §4.2ter lite mode) — verifying the 5 item checks
(a)-(e) + Mode A docs: (a) all 7 commands in `_COMMANDS`; (b) `status` pretty-prints
`phase`/`models_loaded`/`mode`; (c) the `loading models…` hint routes for start/toggle/start-lite/
toggle-lite; (d) exit 2 when the daemon is not running (socket connection refused / XDG unset);
(e) the `[project.scripts] voicectl = "voice_typing.ctl:main"` console-script entry point; (Mode A)
the `__doc__` + argparse help text list all 7 commands. This is a **READ-ONLY AUDIT**: the deliverable
is a report file; NO source code is modified (ctl.py is compliant — this PRP's research verified it;
the audit re-confirms live). Satisfies **Acceptance #6** ("`voicectl toggle/start/stop/status/quit`
all work").

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_voicectl.md` — a NEW self-contained `# Gap Report —
  P1.M3.T2.S2: …` file (there is NO existing `gap_voicectl.md`; this subtask creates it — like S1's
  `gap_socket.md`). Format mirrors `gap_typing.md`. Verbatim content in Implementation Blueprint →
  Task 3 (the evidence is pre-filled from verified file:line + pinning tests; the auditor re-confirms
  the line numbers live + records the live pytest count).

**Success Definition**:
- (a) The report verifies all 5 checks (a)-(e) + Mode A docs against the LIVE `voice_typing/ctl.py` +
  `pyproject.toml` (re-grep + re-read — not trusting this PRP's line numbers blindly) and records a
  ✅ verdict + file:line evidence + a pinning test for each.
- (b) The contract's mandated run command — `.venv/bin/python -m pytest tests/test_voicectl.py -q` —
  is re-run live and the pass count is recorded in the report's §3 (do NOT hard-code the number;
  record what the live run prints).
- (c) The entry-point check (e) is corroborated by a live CLI probe (`.venv/bin/voicectl --help`
  prints the argparse help, exit 0) AND the pyproject.toml:16-18 declaration.
- (d) The 4 non-defect nuances (VT-001 scope boundary; loading-hint routing tested via `start` only;
  entry point is a packaging declaration; exit 64 EX_USAGE extension) are recorded in §4 so they are
  not mistaken for code gaps.
- (e) **No source files are modified** — `ctl.py`/`test_voicectl.py`/`pyproject.toml` are compliant +
  read-only; the only artifact change is creating `gap_voicectl.md`. `git status --short` shows ONLY
  `plan/006_862ee9d6ef41/architecture/gap_voicectl.md`.
- (f) The report's scope is the `ctl.py` CLIENT only — NOT the daemon-side control socket (P1.M3.T2.S1,
  `gap_socket.md`), NOT `status.sh` (P1.M3.T2.S3), NOT the daemon's VT-001 doc-drift (P1.M2.* /
  P1.M6.T1.S2 — nuance §4.1).

> **VERIFIED VERDICT (this PRP's research): ctl.py is COMPLIANT on all 5 checks + Mode A — no code
> fix needed.** The audit's job is to re-confirm this live and document it with evidence + the 4
> non-defect nuances. If a check surprisingly fails on re-read, document it as a real gap for a
> SEPARATE remediation task (this audit does not fix code).

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check)
who needs an authoritative, file:line-evidenced record that the `voicectl` CLI matches PRD §4.8 — so
every command works, `status` surfaces the lifecycle/mode fields, the loading hint fires on a cold arm,
and exit codes are correct — the entire user-facing control surface (Acceptance #6).

**Use Case**: A reviewer asks "do all 7 commands work, does status show phase/models/mode, does the
loading hint print on the first arm, and does voicectl exit 2 cleanly when the daemon is down?" The
report answers yes/no per check with the exact source lines + the pinning test.

**Pain Points Addressed**: Without this audit, a regression (a dropped `toggle-lite` command; a status
payload that stops rendering `mode`; the loading hint routing that misses `start-lite`; an exit-2 path
that returns 1; a help text that hides the lite pair) would be invisible until a user sees a wrong
status / a missing hint / a confusing exit code. The audit pins the CLI to PRD §4.8 with evidence.

## Why

- **PRD §4.8 is the user's entire control surface.** Every user action is `voicectl <cmd>` → JSON line
  → daemon → JSON response → human text + exit code. Acceptance #6 ("all commands work") is satisfied
  by THIS audit (complementing S1's daemon-side socket audit). A CLI drift would break every command.
- **Closes the control-plane audit area (P1.M3.T2, S2).** Every other audit area in round 006 produced
  a `gap_*.md`; voicectl is this round's S2. (S1 = daemon socket → `gap_socket.md`; S3 = `status.sh` —
  separate.)
- **Read-only + parallel-safe.** The audit reads `ctl.py` + `test_voicectl.py` + `pyproject.toml` and
  CREATES `gap_voicectl.md`. The parallel S1 creates `gap_socket.md` — a DIFFERENT file; no conflict.
  No source edits → no conflict with any in-flight implementation task.
- **The research already did the work.** This PRP's research note pre-maps every check to its
  file:line + verdict + pinning test, so the implementing agent re-verifies + writes the report in one
  pass (the value of a PRP: curated context, not open-ended exploration).

## What

A read-only verification of `voice_typing/ctl.py` — `_COMMANDS` (the 7 commands), `format_result` (the
status multi-line render incl. mode/phase/models_loaded + the toggle/start/stop/quit branches), the
loading-hint routing in `main` (`_send_command_with_loading_hint` for the 4 arm commands), the exit-2
paths (RuntimeError + OSError), `_build_parser` (the help/epilog/docstring listing all 7), and the
`pyproject.toml` `[project.scripts]` entry point — re-confirmed live, then documented as a new
`gap_voicectl.md` (mirroring `gap_typing.md`'s format). The 5 checks (a)-(e) + Mode A docs + the live
test run + the 4 non-defect nuances.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_voicectl.md` exists, titled `# Gap Report — P1.M3.T2.S2: voicectl CLI (ctl.py) vs PRD §4.8 / §4.2bis / §4.2ter`.
- [ ] The report records a ✅ verdict + `ctl.py`/`pyproject.toml` file:line + a pinning test (`tests/test_voicectl.py`) for each of the 5 checks (a)-(e) + the Mode A docs row.
- [ ] `.venv/bin/python -m pytest tests/test_voicectl.py -q` is re-run live; its pass count is recorded (not hard-coded).
- [ ] The entry point (e) is corroborated by a live `.venv/bin/voicectl --help` probe + the pyproject.toml:16-18 declaration.
- [ ] The 4 non-defect nuances (§4.1 VT-001 scope boundary; §4.2 loading-hint routing via `start` only; §4.3 entry point = packaging declaration; §4.4 exit 64 EX_USAGE extension) are documented in §4.
- [ ] The report's scope is the `ctl.py` client only — not the daemon socket (S1), not `status.sh` (S3), not VT-001 (P1.M2/P1.M6.T1.S2).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_voicectl.md` — NO source files modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → new report file), the `gap_typing.md` FORMAT template, the verified verdict
(compliant) + the file:line evidence + the pinning test for all 5 checks + Mode A, the 4 non-defect
nuances, the exact test command + the live `--help` probe, the verbatim report body (Task 3), and the
scope boundaries are all pinned. The audit re-verifies live (re-grep + re-read + re-run) rather than
trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the 4 nuances + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M3T2S2/research/voicectl_cli_audit.md
  why: "§0 THE VERIFIED VERDICT: ctl.py COMPLIANT on all 5 checks + Mode A. §1 each check (a-e + Mode A)
        -> ctl.py/pyproject.toml file:line -> ✅ -> pinning test. §2 the exit-code matrix (0/1/2/64).
        §3 the gap-report FORMAT (mirror gap_typing.md). §4 the 4 NON-DEFECT nuances. §5 the test-suite
        coverage map (3 layers + 2 sections). §6 scope boundaries. §7 tooling."
  section: "ALL load-bearing. §1 (verdict+evidence), §3 (format), §4 (nuances), §6 (scope)."

# MUST READ — the file being audited (ctl.py: _COMMANDS / format_result / send_command / _send_command_with_loading_hint / _build_parser / main)
- file: voice_typing/ctl.py
  why: "AUDIT TARGET (read-only, 219 lines). _COMMANDS :37 (the 7 commands). format_result :48-103
        (ok:false :62; quit :64; status :66-101 incl mode :69/90, phase :68/91, models_loaded :77/87/96,
        mic :79-86/97, load_error :78/99-100; toggle/start/stop :103). send_command :106-122 (connect
        raises OSError -> caller exit 2; empty/non-JSON -> ValueError -> exit 1). _send_command_with_loading_hint
        :125-144 (threading.Timer _LOADING_HINT_DELAY=0.3 :45/:135 prints 'loading models…' to stderr
        :137; cancelled in finally :143). _build_parser :147-165 (epilog :158 + cmd help :163 list all 7).
        main :168-213 (cmd validation :179-184 -> exit 64; RuntimeError -> exit 2 :189-191; OSError ->
        exit 2 :203-205; ValueError -> exit 1 :206-208; arm-cmd routing :199-200). __doc__ :1-26
        (subcommands :12-20 + usage :22 list all 7). _EX_USAGE=64 :40."
  critical: "RE-VERIFY by grep + read — do NOT trust the line numbers blindly (re-locate them live).
             The audit READS this file; it does NOT edit it (compliant code = no modification)."

# MUST READ — the test file (coverage to cite per check; the contract's run command)
- file: tests/test_voicectl.py
  why: "404-line suite, 3 layers + 2 feature sections. Layer A (format_result, pure) :39-126. Layer B
        (real-socket round-trip, _StubDaemon + ControlServer) :129-191. Layer C (exit-2 paths) :194-215.
        argparse/structural :218-260 (unknown->64 :220, missing->64 :227, import purity :235, returns-int
        :258). P1.M2.T1.S2 loading-hint + load-failure :262-356 (slow-arm hint :319, fast-arm no-hint :333,
        status/stop no-hint :342, start load-fail->ok:false+exit1 :351, _dispatch load-fail :357/:365,
        _dispatch ok:true guard :372). P1.M1.T3.S1 help surfaces all 7 :339-404 (_COMMANDS==7 + format_help
        lists 7 + __doc__ lists 7 :339). Run it + record the count."
  critical: "Characterize coverage accurately. The loading-hint EMISSION is tested via `start` only
             (nuance §4.2) — do NOT claim per-command hint tests for toggle/start-lite/toggle-lite. The
             entry point (e) has NO pytest — verify it via the live --help probe + pyproject.toml (nuance §4.3)."

# MUST READ — the entry-point declaration (check e)
- file: pyproject.toml
  why: "[project.scripts] :16-18: voicectl = 'voice_typing.ctl:main' :17 + voice-typing-daemon =
        'voice_typing.daemon:main' :18. Hatchling build backend :1-3 generates .venv/bin/voicectl from
        this. Corroborate with the live probe: .venv/bin/voicectl --help (prints argparse help, exit 0)."
  critical: "This is a PACKAGING declaration, not a pytest (nuance §4.3). Verify by reading pyproject.toml
             :16-18 AND the installed script (.venv/bin/voicectl --help or head -1 .venv/bin/voicectl)."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md
  why: "The format template. Structure: title (# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X) + Date +
        Scope + Audited artifacts (read-only) + Bottom line (✅) + §1 Method (w/ commands run + observed
        output) + §2 per-check compliance TABLE (PRD req | expected | actual | file:line | pinning test | ✅)
        + §3 Test results (the live count) + §4 non-defect nuances + §5 Conclusion (PASS; no fix). Mirror
        it EXACTLY. gap_voicectl.md is a NEW file (CREATE, not append)."
  critical: "Mirror the structure. Cite ctl.py/pyproject.toml file:line + a tests/test_voicectl.py test
             per check. gap_socket.md (S1) is the closest sibling (same task area) — also a useful reference."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.8 voicectl: the 7 commands (toggle/start/stop/status/quit/toggle-lite/start-lite); status
        pretty-prints partial/phase/models_loaded/mode; toggle-lite/start-lite arm in lite mode; 'If
        daemon not running: clear message + exit 2'; exit code 0/1. §4.2bis: 'voicectl prints a loading
        models… hint' while the first arm blocks (~1-3s). §4.2ter: mode normal|lite, toggle-lite/start-lite.
        §7 #6 acceptance: 'voicectl toggle/start/stop/status/quit all work'. This is the spec each check
        is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.8/§4.2bis/§4.2ter/§7#6 as the contract.
             NOTE §4.2bis references 'BUGS.md VT-001' — BUGS.md does NOT exist (nuance §4.1; owned by
             P1.M6.T1.S2, out of scope for this client audit)."

# CONTEXT — the parallel task contract (P1.M3.T2.S1 = daemon socket; DIFFERENT file; no conflict)
- file: plan/006_862ee9d6ef41/P1M3T2S1/PRP.md
  why: "The parallel item (daemon-side control socket audit) CREATEs gap_socket.md — a DIFFERENT file
        from gap_voicectl.md (which this task CREATEs). Confirms the two audits are disjoint (client vs
        daemon socket) and neither touches the other's report or any source file."
  critical: "gap_voicectl.md is INDEPENDENT of gap_socket.md. CREATE the file fresh. S1 audits
        daemon.ControlServer/_dispatch/status_snapshot; S2 audits ctl.py — do not duplicate S1's
        daemon-side findings (e.g. the status_snapshot key set is S1's concern; S2 cares only that
        format_result RENDERS the keys the daemon sends)."
```

### Current Codebase tree (state at P1.M3.T2.S2 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/ctl.py                 # AUDIT TARGET (read-only — _COMMANDS/format_result/send_command/_send_command_with_loading_hint/_build_parser/main/__doc__)
├── pyproject.toml                      # AUDIT (check e: [project.scripts] voicectl :17 — read-only)
├── .venv/bin/voicectl                  # AUDIT (check e corroboration: live --help probe — read-only)
└── tests/
    └── test_voicectl.py                # AUDIT (cite the pinning test per check; the contract's run command) — 404 lines
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_typing.md                   # FORMAT TEMPLATE (mirror its structure)
    ├── gap_socket.md                   # FORMAT REFERENCE (S1, same task area; closest sibling)
    └── gap_voicectl.md                 # <-- CREATE (NEW file; no prior voicectl gap report exists)
# NO source/test/doc files modified. The only artifact change is creating gap_voicectl.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_voicectl.md   # CREATE (NEW): the P1.M3.T2.S2 voicectl CLI audit
                                                    #   (5-check + Mode A compliance table + live pytest count
                                                    #    + live --help probe + 4 nuances + conclusion).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT; DO NOT EDIT ctl.py / test_voicectl.py / pyproject.toml /
#   PRD.md / any source. ctl.py is COMPLIANT (this PRP's research verified it). The ONLY artifact change
#   is CREATING gap_voicectl.md. If a check fails on re-read, document it as a real gap for a SEPARATE
#   remediation task — do NOT fix it here (consistent with S1 + every round-006 audit). (Research §0.)

# CRITICAL #2 — RE-VERIFY THE LINE NUMBERS LIVE. This PRP cites ctl.py:37/_COMMANDS, :66-101/status,
#   :199-200/routing, :189-191 + :203-205/exit-2, :1-26 + :147-165/docs, pyproject.toml:17. These were
#   correct at research time but the file may have shifted — re-grep (e.g. `grep -n "_COMMANDS"`,
#   `grep -n "if cmd == \"status\""`, `grep -n "_send_command_with_loading_hint"`, `grep -n "voicectl ="`
#   pyproject.toml) and record the ACTUAL line numbers in the report. Do NOT copy the PRP's numbers blind.

# CRITICAL #3 — THE ENTRY POINT (e) HAS NO PYTEST; VERIFY VIA THE LIVE SCRIPT. `[project.scripts]
#   voicectl = "voice_typing.ctl:main"` (pyproject.toml:17) is a Hatchling packaging declaration that
#   generates .venv/bin/voicectl at install. Corroborate it LIVE: `.venv/bin/voicectl --help` (prints the
#   argparse help, exit 0) OR `head -1 .venv/bin/voicectl` (the hatchling entry-point line). Do NOT claim
#   a unit test pins it (none does — nuance §4.3).

# CRITICAL #4 — RECORD THE LIVE PYTEST COUNT; DO NOT HARD-CODE IT. The contract's run command is
#   `.venv/bin/python -m pytest tests/test_voicectl.py -q` (FULL PATH — zsh aliases python/pytest).
#   Run it + paste the actual "N passed in Xs" line into §3. The suite is pure-stdlib (no GPU/CUDA/
#   daemon; the socket round-trips use _StubDaemon; import purity runs in a fresh subprocess) → <1s.

# CRITICAL #5 — VT-001 IS DAEMON-SIDE, NOT A ctl.py CLIENT GAP (DO NOT FLAG IT AS A ctl.py DEFECT).
#   PRD §4.2bis says "voicectl status currently violates this [daemon never imports torch]; see BUGS.md
#   VT-001." Two facts: (i) BUGS.md does NOT exist in the repo (doc drift — owned by P1.M6.T1.S2);
#   (ii) the CLIENT voice_typing.ctl is import-clean (test_ctl_module_present_and_imports_pure :235
#   asserts NO RealtimeSTT/torch/ctranslate2 leak in a fresh interpreter). The "violation" is the DAEMON's
#   status path (status_snapshot -> _resolved_device -> cuda_check imports ctranslate2 IN THE DAEMON) —
#   out of scope for S2 (owned by P1.M2/P1.M6.T1.S2). Record this as nuance §4.1, NOT a ctl.py gap.

# CRITICAL #6 — SCOPE IS THE ctl.py CLIENT ONLY. Do NOT audit the daemon's ControlServer/_dispatch/
#   status_snapshot (S1, gap_socket.md), status.sh (S3), or the recorder-host lifecycle (P1.M2.*). S2
#   cares that format_result RENDERS the keys the daemon sends + that the CLI routes/exit-codes correctly
#   — not whether the daemon's status_snapshot HAS the keys (that is S1's concern).

# GOTCHA #7 — STATUS RENDERING vs DAEMON KEY SET. format_result uses defensive .get(...) everywhere
#   (ctl.py:62-80) so a missing key never raises. The status fields ctl.py RENDERS (mode/phase/
#   models_loaded/partial/last_final/uptime/device/compute_type/final_model/realtime_model/mic/load_error)
#   must match what the daemon SENDS — but verifying the daemon SENDS them is S1's job (gap_socket.md).
#   S2 verifies ctl.py RENDERS them given a canned response (Layer A tests do exactly this).

# GOTCHA #8 — EXIT 64 (EX_USAGE) IS A DOCUMENTED EXTENSION, NOT A DEVIATION. PRD §4.8 says "exit code
#   0/1" + "exit 2 daemon not running". ctl.py adds 64 for unknown/missing commands (bugfix Issue 7) so
#   exit 2 stays EXCLUSIVE to daemon-not-running. Record it as nuance §4.4 (a faithful enhancement), NOT
#   a gap. Pinning tests: test_main_rejects_unknown_command :220 + test_main_rejects_missing_command :227.

# GOTCHA #9 — LOADING-HINT ROUTING IS TESTED VIA `start` ONLY. The routing tuple
#   ("start","toggle","start-lite","toggle-lite") (ctl.py:199) covers all 4 arm commands, but the hint-
#   EMISSION tests exercise `start` (test_start_prints_loading_hint_when_arm_is_slow :319) + the
#   stop/status negatives (:342). toggle/start-lite/toggle-lite route via the same one-line membership.
#   Record as nuance §4.2 (not a defect — the routing is a single set-membership check proven by `start`).

# GOTCHA #10 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always
#   `.venv/bin/python -m pytest ...`. mypy NOT installed (skip). ruff at /home/dustin/.local/bin/ruff is
#   OPTIONAL (not in .venv; not a gate; ctl.py is already clean). (Research §7.)

# GOTCHA #11 — DO NOT CREATE a tests/__init__.py or edit any test. The audit only READS test_voicectl.py
#   (to cite pinning tests) and RUNS it. No new files except gap_voicectl.md.
```

## Implementation Blueprint

### Data models and structure

No production data model. The deliverable is a Markdown gap-report file mirroring `gap_typing.md`'s
structure. No Python/bash changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — re-verify the contract + locate the live line numbers (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/ctl.py && test -f tests/test_voicectl.py && test -f pyproject.toml && echo "ok: files present" || echo "PREFLIGHT FAIL"
      grep -nE '_COMMANDS.*=|_EX_USAGE|_LOADING_HINT_DELAY' voice_typing/ctl.py
      grep -nE 'def format_result|if cmd == "status"|mode = |phase = |models_loaded = |loaded_marker' voice_typing/ctl.py
      grep -nE 'def send_command|def _send_command_with_loading_hint|if cmd in \(' voice_typing/ctl.py
      grep -nE 'def _build_parser|epilog=|help="toggle' voice_typing/ctl.py
      grep -nE 'return 2|return 1|return _EX_USAGE|RuntimeError|except OSError|except ValueError' voice_typing/ctl.py
      grep -nE 'voicectl = "|voice-typing-daemon = "' pyproject.toml
      .venv/bin/voicectl --help >/dev/null 2>&1 && echo "ok: live voicectl --help exit 0" || echo "PREFLIGHT FAIL: voicectl script missing/broken"
  - EXPECTED: all files present; the grep hits locate _COMMANDS/the status branch/the routing tuple/
    _build_parser/the exit-code returns; pyproject.toml has the voicectl entry point; the live --help
    exits 0 (corroborates check e). RECORD the actual line numbers for the report.
  - DO NOT: edit anything yet, or touch any source/test/doc file.

Task 2: RUN the suite live (record the count for §3)
  - RUN: .venv/bin/python -m pytest tests/test_voicectl.py -q
  - EXPECTED: all pass (the suite is pure-stdlib, <1s). RECORD the exact "N passed in Xs" line. If any
    FAIL: that contradicts the verified-compliant verdict — READ the failure, and if it is a REAL ctl.py
    defect, document it as a gap in §4 (do NOT fix ctl.py here); if it is an environment issue (e.g. a
    stale .venv), note it. (Research §5; Critical #4.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_voicectl.md — write the report body from
        "Task 3 SOURCE" below, REPLACING the <...> placeholders with the LIVE line numbers from Task 1
        and the LIVE pass count from Task 2. Mirror gap_typing.md's structure exactly.
  - FILE: plan/006_862ee9d6ef41/architecture/gap_voicectl.md (NEW — CREATE, do not append).
  - DO NOT: edit ctl.py/test_voicectl.py/pyproject.toml/PRD.md (Critical #1); hard-code the pass count
    (Critical #4); flag VT-001 as a ctl.py defect (Critical #5); audit the daemon socket (Critical #6).

Task 4: VALIDATE — L1 (file exists + markdown sanity) + L2 (the pytest count is in §3) + L3 (scope
        guard: ONLY gap_voicectl.md created; no source modified). No git commit unless the orchestrator
        directs it. If asked: message "P1.M3.T2.S2: voicectl CLI audit (ctl.py compliant; gap_voicectl.md
        created; no code changes)".
```

#### Task 3 SOURCE — `gap_voicectl.md` (write this body; replace `<...>` with LIVE values from Task 1/2)

````markdown
# Gap Report — P1.M3.T2.S2: voicectl CLI (ctl.py) vs PRD §4.8 / §4.2bis / §4.2ter

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/ctl.py` against PRD §4.8 (the voicectl command surface) + §4.2bis (the
`loading models…` hint on the first arm) + §4.2ter (lite mode: `toggle-lite`/`start-lite`) — the 5 item
checks (a)-(e) + Mode A docs (the `__doc__` + argparse help list all 7 commands) — and re-run the
pure-Python unit suite (`tests/test_voicectl.py`). Subtask **P1.M3.T2.S2** of verification round
`006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/ctl.py` — `_COMMANDS` (`:<L37>`), `format_result` (`:<L48>-<L103>`), `send_command`
  (`:<L106>-<L122>`), `_send_command_with_loading_hint` (`:<L125>-<L144>`), `_build_parser`
  (`:<L147>-<L165>`), `main` (`:<L168>-<L213>`), module `__doc__` (`:<L1>-<L26>`), `_EX_USAGE=64`
  (`:<L40>`), `_LOADING_HINT_DELAY=0.3` (`:<L45>`).
- `tests/test_voicectl.py` — the 404-line suite (the contract's run command); 3 layers + 2 feature
  sections; NO RealtimeSTT/CUDA/real daemon (socket round-trips use `_StubDaemon`; import purity runs in
  a fresh subprocess).
- `pyproject.toml` — `[project.scripts]` (`:<L16>-<L18>`): the `voicectl` console-script entry point.
- `.venv/bin/voicectl` — the installed console script (live `--help` probe corroborates the entry point).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.8, §4.2bis, §4.2ter, §7#6 (the contract).

**Bottom line:** ✅ `ctl.py` is **COMPLIANT** with PRD §4.8 / §4.2bis / §4.2ter — all 5 checks (a)-(e)
+ Mode A docs hold, each mapped to a `ctl.py`/`pyproject.toml` file:line and a pinning test, and the
suite is green. **No source files were modified** — the CLI faithfully implements the spec, including
the documented exit-64 (EX_USAGE) extension that keeps exit 2 exclusive to "daemon not running". The
four non-blocking observations (the VT-001 scope boundary; loading-hint routing tested via `start` only;
the entry point being a packaging declaration; the exit-64 extension) are recorded in §4 so they are not
mistaken for defects.

---

## 1. Method

Each of the 5 item checks (a)-(e) + Mode A docs was mapped 1:1 to its `ctl.py`/`pyproject.toml`
implementation by `grep -n` (the file:line evidence), and the exit-2 / exit-64 paths were checked
directly. The entry point (e) was corroborated by the LIVE installed script (`.venv/bin/voicectl
--help`). The full `tests/test_voicectl.py` suite was then **re-run live** to record the actual pass
count and timing. Nothing was assumed from the PRP's embedded numbers — every line number + the pass
count below was re-verified this round (pure stdlib: argparse/json/socket/sys/threading + the shared
`_default_control_socket_path`; no GPU/daemon required).

### Commands run (re-verification)

```bash
# (a-e + Mode A) Line-number map (grep -n)
grep -nE '_COMMANDS.*=|_EX_USAGE|_LOADING_HINT_DELAY' voice_typing/ctl.py
grep -nE 'if cmd == "status"|mode = response|phase = response|models_loaded = response|loaded_marker' voice_typing/ctl.py
grep -nE 'if cmd in \("start"|_send_command_with_loading_hint|loading models' voice_typing/ctl.py
grep -nE 'return 2|except OSError|except RuntimeError|_default_control_socket_path' voice_typing/ctl.py
grep -nE 'epilog=|help="toggle|def __doc__|^"""voicectl' voice_typing/ctl.py
grep -nE 'voicectl = "|voice-typing-daemon = "' pyproject.toml
# (e) live entry-point corroboration
.venv/bin/voicectl --help >/dev/null 2>&1 && echo "voicectl --help exit 0"
# the unit suite (the contract's run command), LIVE
.venv/bin/python -m pytest tests/test_voicectl.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
(a) <L37>:_COMMANDS = ("toggle","start","stop","status","quit","toggle-lite","start-lite")
(b) <L66>:if cmd == "status":  <L69>:mode = response.get("mode","normal")  <L68>:phase = ...
    <L77>:models_loaded = response.get(...)  <L87>:loaded_marker = "loaded" if models_loaded ...  <L90>:mode:  <L91>:phase:  <L96>:models: ... ({loaded_marker})
(c) <L199>:if cmd in ("start","toggle","start-lite","toggle-lite"):  <L200>:response = _send_command_with_loading_hint(...)
    <L137>:print("loading models… (first arm, ~1–3 s)", file=sys.stderr)  <L45>:_LOADING_HINT_DELAY: float = 0.3
(d) <L189>:except RuntimeError: ... <L191>:return 2   <L203>:except OSError as exc: ... <L205>:return 2
(e) pyproject.toml:<L17>:voicectl = "voice_typing.ctl:main"   live: .venv/bin/voicectl --help exit 0
(Mode A) <L12>-<L20>:subcommand block lists 7  <L22>:Usage lists 7  <L158>:epilog lists 7  <L163>:cmd help lists 7
............                                                            [100%]
<N> passed in <X>s
```

---

## 2. Per-check Compliance Table (PRD §4.8 / §4.2bis / §4.2ter vs `ctl.py`)

| # | PRD requirement | Expected (spec) | `ctl.py` / `pyproject.toml` actual | file:line | Pinning tests (`tests/test_voicectl.py`) | Verdict |
|---|---|---|---|---|---|---|
| **(a)** | All 7 commands present (`toggle`/`start`/`stop`/`status`/`quit`/`toggle-lite`/`start-lite`) | `_COMMANDS` tuple with exactly those 7 (§4.8 + §4.2ter lite pair) | `_COMMANDS = ("toggle","start","stop","status","quit","toggle-lite","start-lite")` | `ctl.py:<L37>` | `test_help_surfaces_list_all_seven_commands` `:<L339>` (asserts `set(ctl._COMMANDS)==seven`); `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` `:<L75>` | ✅ |
| **(b)** | `status` pretty-prints `phase` / `models_loaded` / `mode` (§4.8 + §4.2bis + §4.2ter) | multi-line: listening, mode, phase, partial, last, uptime, device, models (loaded marker), mic (+ load error) | `if cmd=="status":` branch renders `mode:` (from `response.get("mode","normal")`), `phase:`, `models: <f> + <r> (<loaded\|not loaded>)` (from `models_loaded`→`loaded_marker`), + partial/last/uptime/device/mic/load_error | status branch `ctl.py:<L66>-<L101>`; mode `<L69>`/`<L90>`; phase `<L68>`/`<L91>`; models `<L77>`/`<L87>`/`<L96>` | `test_format_status_multiline_has_partial_and_models` `:<L62>`; `test_format_status_shows_unloaded_state_and_load_error` `:<L82>`; `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` `:<L75>` (mode: lite) | ✅ |
| **(c)** | `loading models…` hint for start/toggle/start-lite/toggle-lite (§4.2bis) | the 4 ARM commands route through the hint wrapper; hint to stderr after a delay, cancelled for fast arms | `if cmd in ("start","toggle","start-lite","toggle-lite"): response = _send_command_with_loading_hint(...)`; the wrapper starts a `threading.Timer(_LOADING_HINT_DELAY=0.3)` printing `"loading models… (first arm, ~1–3 s)"` to **stderr**, cancelled in `finally` | routing `ctl.py:<L199>-<L200>`; wrapper `<L125>-<L144>`; delay `<L45>`; print `<L137>` | `test_start_prints_loading_hint_when_arm_is_slow` `:<L319>`; `test_start_does_not_print_loading_hint_for_fast_arm` `:<L333>`; `test_status_and_stop_do_not_print_loading_hint` `:<L342>` | ✅ |
| **(d)** | exit 2 when daemon not running (socket refused / XDG unset) | `RuntimeError` (XDG unset) AND connect `OSError` (FileNotFoundError/ConnectionRefusedError/PermissionError) → stderr msg + `return 2` | `_default_control_socket_path()` `RuntimeError` → `return 2`; `send_command` connect `OSError` → `return 2` | `ctl.py:<L189>-<L191>` (RuntimeError); `<L203>-<L205>` (OSError) | `test_main_exit2_when_socket_absent` `:<L196>`; `test_main_exit2_when_stale_socket_no_listener` `:<L203>`; `test_main_exit2_when_xdg_runtime_dir_unset` `:<L212>` | ✅ |
| **(e)** | console-script entry point `[project.scripts] voicectl='voice_typing.ctl:main'` | the hatchling-generated `.venv/bin/voicectl` dispatches to `voice_typing.ctl:main` | `[project.scripts]` block: `voicectl = "voice_typing.ctl:main"`; live `.venv/bin/voicectl --help` prints argparse help (exit 0) | `pyproject.toml:<L17>` (block `<L16>-<L18>`) | (none — packaging declaration; corroborated by the live `--help` probe) | ✅ |
| **Mode A** | `__doc__` + argparse help list all 7 commands | the module docstring subcommand block + Usage line, AND argparse epilog + positional help, all list the 7 | docstring "Subcommands" block + Usage line; `_build_parser` epilog + `cmd` help — all list 7 | `ctl.py:<L12>-<L20>` + `<L22>` (doc); `<L158>` (epilog) + `<L163>` (cmd help) | `test_help_surfaces_list_all_seven_commands` `:<L339>` (asserts all 7 in `_COMMANDS` + `format_help()` + `__doc__`) | ✅ |

> All checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The exit-code matrix (0 success / 1 logical failure / 2 daemon-not-running / 64 usage) is
> documented in §4.4.

---

## 3. Test results (the contract's run command, LIVE)

```
$ .venv/bin/python -m pytest tests/test_voicectl.py -q
....<paste the live summary line, e.g. "33 passed in 0.4s">....
```

The suite (404 lines) has 3 layers + 2 feature sections: Layer A `format_result` (pure, canned JSON),
Layer B real-socket round-trip (`_StubDaemon` + `ControlServer`), Layer C exit-2 paths, the
argparse/structural tests, the P1.M2.T1.S2 loading-hint + load-failure section, and the P1.M1.T3.S1
help-surfaces-all-7 section. Pure stdlib — no GPU/CUDA/real daemon. Entry point (e) corroborated by the
live `.venv/bin/voicectl --help` probe (exit 0).

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 VT-001 is daemon-side, NOT a `ctl.py` client gap (out of scope)
PRD §4.2bis says "caveat: `voicectl status` currently violates this [the daemon never imports
RealtimeSTT/torch/ctranslate2]; see BUGS.md VT-001." Two facts: (i) **BUGS.md does not exist** in the
repo (`find . -name BUGS.md` → none) — the reference is doc drift owned by **P1.M6.T1.S2**; (ii) the
**client** `voice_typing.ctl` is import-clean: `test_ctl_module_present_and_imports_pure` (`:<L235>`)
runs a FRESH interpreter importing only `voice_typing.ctl` and asserts NO
`RealtimeSTT`/`torch`/`ctranslate2` in `sys.modules`. The "violation" is the **daemon's** status path
(`status_snapshot → _resolved_device → cuda_check` imports ctranslate2 IN THE DAEMON PROCESS) — out of
scope for S2 (owned by P1.M2/P1.M6.T1.S2). The client itself is clean. ✅

### 4.2 Loading-hint routing is tested via `start` only (not per-command)
The routing tuple `("start","toggle","start-lite","toggle-lite")` (`ctl.py:<L199>`) covers all 4 arm
commands, but the hint-EMISSION tests exercise `start` only (`test_start_prints_loading_hint...` `:<L319>`,
with `_LOADING_HINT_DELAY` monkeypatched to 0.02 + a `_SlowStartStubDaemon(0.4)` so it is deterministic)
plus the stop/status negatives (`:<L342>`). `toggle`/`start-lite`/`toggle-lite` route through the same
one-line `if cmd in (...)` membership, so their routing is implicit (not a separate test). Not a defect —
the routing is a single set-membership check proven by `start`; the negatives prove stop/status/quit do
NOT route through it.

### 4.3 The entry point (e) is a packaging declaration — verified by inspection, not pytest
`[project.scripts] voicectl = "voice_typing.ctl:main"` (`pyproject.toml:<L17>`) is a Hatchling build
declaration; no unit test asserts it (it produces the `.venv/bin/voicectl` console script at install).
Verified by reading `pyproject.toml:<L16>-<L18>` AND the live probe `.venv/bin/voicectl --help` (prints
the argparse help, exit 0). Consistent with how every round-006 audit treated packaging declarations.

### 4.4 Exit 64 (EX_USAGE) is a documented extension beyond PRD §4.8's "0/1/2"
PRD §4.8 specifies exit 0/1 + "exit 2 if daemon not running". `ctl.py` adds **64** (BSD `sysexits.h`
`EX_USAGE`, `_EX_USAGE=64` `:<L40>`) for unknown/missing commands, deliberately validated in `main`
(NOT argparse `choices`) so argparse's `SystemExit(2)` cannot collide with the daemon-not-running exit 2
(bugfix Issue 7). Pinning tests: `test_main_rejects_unknown_command` `:<L220>` +
`test_main_rejects_missing_command` `:<L227>` + the returns-int contract `test_main_returns_int` `:<L258>`.
Documented in the docstring (`:<L7>-<L10>`) + the argparse description (`:<L155>-<L156>`). A faithful,
documented enhancement, NOT a deviation.

---

## 5. Conclusion

**PASS.** `voice_typing/ctl.py` is compliant with PRD §4.8 / §4.2bis / §4.2ter on all 5 item checks
(a)-(e) + Mode A docs. The CLI surface — 7 commands, status rendering (mode/phase/models_loaded/...),
the client-side `loading models…` hint on a cold arm, the exit-2 daemon-not-running paths, the
exit-64 usage extension, and the console-script entry point — all hold, each pinned by a
`tests/test_voicectl.py` test (except the packaging entry point, corroborated live) and re-verified
live this round. **No source files were modified** (read-only audit); the sole artifact is this report.
Scope is the `ctl.py` client only — the daemon-side control socket is P1.M3.T2.S1 (`gap_socket.md`),
`status.sh` is P1.M3.T2.S3, and the VT-001 daemon-side doc-drift is P1.M6.T1.S2.
````

> NOTE for the implementer: replace every `<L...>` placeholder with the ACTUAL line number from your
> Task-1 greps, and paste the LIVE pytest summary line into §3. The body above is the verified-compliant
> verdict pre-filled from research — re-confirm each file:line + the pass count live (Critical #2, #4).

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the audit is READ-ONLY. The ONLY file created is gap_voicectl.md. ctl.py/test_voicectl.py/
#   pyproject.toml are compliant + untouched. If a check fails on re-read, document it as a gap for a
#   SEPARATE remediation task (do NOT fix ctl.py here). (Critical #1.)

# PATTERN 2 — re-verify line numbers live (grep -n), then paste them into the report's <L...> slots.
#   Do NOT copy the PRP's numbers blindly — the file may have shifted. (Critical #2.)

# PATTERN 3 — the entry point (e) has NO pytest; corroborate it LIVE: `.venv/bin/voicectl --help`
#   (exit 0) + read pyproject.toml:16-18. (Critical #3.)

# PATTERN 4 — run the suite live + paste the actual count into §3. Do NOT hard-code a number. (Critical #4.)

# PATTERN 5 — frame the 4 nuances precisely (§4): VT-001 is daemon-side + BUGS.md is absent (NOT a
#   ctl.py defect); loading-hint routing tested via `start`; entry point = packaging declaration;
#   exit 64 = documented EX_USAGE extension. (Critical #5, Gotchas #8/#9.)
```

### Integration Points

```yaml
REPORT FILE:
  - create: "plan/006_862ee9d6ef41/architecture/gap_voicectl.md (NEW — mirror gap_typing.md's structure)"
CONSUMED (read-only — NO edits):
  - voice_typing/ctl.py: "_COMMANDS, format_result, send_command, _send_command_with_loading_hint,
                          _build_parser, main, __doc__ (the 5 checks + Mode A)"
  - tests/test_voicectl.py: "cite the pinning test per check; the contract's run command"
  - pyproject.toml: "[project.scripts] voicectl (check e)"
  - .venv/bin/voicectl: "live --help probe (check e corroboration)"
DISJOINT FROM SIBLINGS:
  - P1.M3.T2.S1: "gap_socket.md (daemon-side ControlServer/_dispatch/status_snapshot) — DIFFERENT file"
  - P1.M3.T2.S3: "status.sh tmux helper — NOT ctl.py"
  - P1.M2.* / P1.M6.T1.S2: "daemon lifecycle / VT-001 doc-drift — daemon-side, out of scope"
DEPENDENCIES: none new (read-only audit + the existing pytest suite + the live voicectl script).
```

## Validation Loop

> This is a READ-ONLY AUDIT. The gate is: the report exists with ✅ verdicts + live file:line evidence +
> the live pytest count + the live `--help` probe, and NO source file is modified. No GPU/CUDA/daemon
> (the suite is pure-stdlib; the entry point is corroborated by the installed script).

### Level 1: Report exists + structure sanity

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L1 report present" || echo "L1 FAIL: report missing"
# Structure mirrors gap_typing.md:
head -1 plan/006_862ee9d6ef41/architecture/gap_voicectl.md | grep -q '^# Gap Report — P1.M3.T2.S2: voicectl CLI' && echo "L1 title ok" || echo "L1 FAIL: title"
grep -q '^## 2\. Per-check Compliance Table' plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L1 §2 ok" || echo "L1 FAIL: §2 table"
grep -q '^## 3\. Test results' plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L1 §3 ok" || echo "L1 FAIL: §3"
grep -q '^## 4\. Non-defect nuances' plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L1 §4 ok" || echo "L1 FAIL: §4"
# No leftover <L...> placeholders (all replaced with live line numbers):
! grep -q '<L[0-9]' plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L1 placeholders resolved" || echo "L1 FAIL: leftover <L...> placeholder"
# Expected: report present; title/§2/§3/§4 headings present; NO <L...> placeholders remain.
```

### Level 2: The contract's run command (re-run live; count recorded in §3)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_voicectl.py -q | tee /tmp/voicectl_audit_run.log
echo "exit: ${PIPESTATUS[0]}"
# Expected: exit 0; "N passed in Xs". Confirm the report's §3 pasted THIS run's summary line:
COUNT=$(grep -oE '[0-9]+ passed' /tmp/voicectl_audit_run.log | head -1)
grep -q "$COUNT passed" plan/006_862ee9d6ef41/architecture/gap_voicectl.md && echo "L2 count recorded" || echo "L2 FAIL: live count not in §3"
# Entry-point corroboration (check e): the live script dispatches to main.
.venv/bin/voicectl --help >/dev/null 2>&1 && echo "L2 voicectl --help exit 0 (check e)" || echo "L2 FAIL: voicectl script broken"
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected: ONLY "?? plan/006_862ee9d6ef41/architecture/gap_voicectl.md" (new untracked file). Any change
#   to voice_typing/ctl.py, tests/test_voicectl.py, pyproject.toml, PRD.md, tasks.json, prd_snapshot.md,
#   .gitignore, or any source is a SCOPE VIOLATION (read-only audit).
git diff --name-only   # Expected: empty (the report is a NEW untracked file, not a modification)
! git status --porcelain | grep -qE 'voice_typing/|tests/|pyproject.toml|PRD.md|tasks.json|prd_snapshot.md' && echo "L3 ok: no source/test/doc modified" || echo "L3 FAIL: source/test/doc modified"
# Confirm the report is the only NEW file + no daemon-socket/status.sh overlap:
test -f plan/006_862ee9d6ef41/architecture/gap_socket.md && echo "L3 ok: S1's gap_socket.md coexists (disjoint)" || echo "L3 note: S1's gap_socket.md not yet present (parallel)"
```

### Level 4: Evidence spot-check (the 5 checks are real, not hand-waved)

```bash
cd /home/dustin/projects/voice-typing
# Each check's file:line cited in the report must actually exist + contain the claimed code:
grep -nE '_COMMANDS.*toggle.*start.*stop.*status.*quit.*toggle-lite.*start-lite' voice_typing/ctl.py   # (a)
grep -nE 'if cmd == "status"' voice_typing/ctl.py                                                       # (b)
grep -nE 'if cmd in \("start", "toggle", "start-lite", "toggle-lite"\)' voice_typing/ctl.py            # (c)
grep -nE 'return 2' voice_typing/ctl.py                                                                  # (d)
grep -nE 'voicectl = "voice_typing.ctl:main"' pyproject.toml                                             # (e)
# Expected: each grep hits the line the report cites (re-verify the numbers match the report's <L...> → live values).
```

## Final Validation Checklist

### Technical Validation
- [ ] `plan/006_862ee9d6ef41/architecture/gap_voicectl.md` exists with the correct title + §1-§5 structure mirroring `gap_typing.md`.
- [ ] No `<L...>` placeholders remain (all replaced with live `grep -n` line numbers).
- [ ] `.venv/bin/python -m pytest tests/test_voicectl.py -q` → exit 0; the live pass count is pasted into §3.
- [ ] `.venv/bin/voicectl --help` → exit 0 (corroborates check e); recorded in §1/§3.
- [ ] L3 scope guard: ONLY `gap_voicectl.md` created (new untracked); NO source/test/doc modified.
- [ ] L4: each check's cited file:line exists + contains the claimed code.

### Feature Validation
- [ ] **(a)** `_COMMANDS` has exactly 7 commands (toggle/start/stop/status/quit/toggle-lite/start-lite).
- [ ] **(b)** `format_result("status", ...)` renders `mode:` / `phase:` / `models: ... (loaded|not loaded)` (+ partial/last/uptime/device/mic/load_error).
- [ ] **(c)** `main` routes start/toggle/start-lite/toggle-lite through `_send_command_with_loading_hint` (hint to stderr after 0.3s, cancelled for fast arms).
- [ ] **(d)** `main` returns 2 on `RuntimeError` (XDG unset) AND connect `OSError` (socket refused/absent).
- [ ] **(e)** `pyproject.toml` `[project.scripts] voicectl = "voice_typing.ctl:main"`; live `.venv/bin/voicectl --help` exits 0.
- [ ] **Mode A** the `__doc__` subcommand block + Usage line, AND argparse epilog + positional help, all list 7 commands.

### Code Quality Validation
- [ ] The report mirrors `gap_typing.md`'s structure (title/Date/Scope/Audited artifacts/Bottom line/§1-§5).
- [ ] Every check row has a real `ctl.py`/`pyproject.toml` file:line + a `tests/test_voicectl.py` pinning test (except (e), corroborated live).
- [ ] The 4 nuances are documented precisely (VT-001 scope boundary; loading-hint via `start` only; entry point = packaging; exit 64 extension).
- [ ] No claim that overstates coverage (e.g. do NOT claim per-command hint tests or a pytest for the entry point).

### Documentation & Deployment
- [ ] The report is self-contained (a reviewer needs only it + the repo to confirm the verdict).
- [ ] Scope boundaries explicit (client-only; S1 = daemon socket; S3 = status.sh; VT-001 = P1.M6.T1.S2).
- [ ] No new env vars, no config keys, no user-facing surface (read-only audit; Acceptance #6 evidence).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/ctl.py`, `tests/test_voicectl.py`, `pyproject.toml`, `PRD.md`, or any source — this is a read-only audit; ctl.py is compliant. If a check fails, document it as a gap for a separate remediation task (Critical #1).
- ❌ Don't copy the PRP's line numbers blindly — re-grep (`grep -n`) live and paste the ACTUAL numbers into the report's `<L...>` slots (Critical #2).
- ❌ Don't claim a pytest pins the entry point (e) — it's a packaging declaration; corroborate it via the live `.venv/bin/voicectl --help` probe + pyproject.toml:16-18 (Critical #3).
- ❌ Don't hard-code the pytest count — run it live + paste the actual summary line into §3 (Critical #4).
- ❌ Don't flag VT-001 as a `ctl.py` defect — it's daemon-side (the daemon's status path imports cuda_check), BUGS.md is absent (doc drift), and the client `voice_typing.ctl` is import-clean. Record it as a scope-boundary nuance (Critical #5).
- ❌ Don't audit the daemon-side `ControlServer`/`_dispatch`/`status_snapshot` — that's S1 (`gap_socket.md`). S2 is the `ctl.py` client only (Critical #6).
- ❌ Don't claim per-command loading-hint tests for toggle/start-lite/toggle-lite — the emission is tested via `start` only; the routing is a one-line tuple membership (Gotcha #9).
- ❌ Don't call exit 64 a deviation — it's a documented EX_USAGE extension (bugfix Issue 7) keeping exit 2 exclusive (Gotcha #8).
- ❌ Don't append to an existing file or create `tests/__init__.py` — CREATE `gap_voicectl.md` fresh; it's the only new file (Gotcha #11).
- ❌ Don't run `mypy` (not installed) or bare `python`/`pytest` (zsh aliases) — use `.venv/bin/python -m pytest` + `.venv/bin/voicectl` (Gotcha #10).

---

## Confidence Score

**9/10** for one-pass success. This is a read-only audit of a 219-line `ctl.py` that is already
compliant (verified by reading every line + the full 404-line test suite + pyproject.toml). The
deliverable is a Markdown report mirroring an existing template (`gap_typing.md`), with the verdict +
file:line evidence + pinning tests pre-filled in the Task-3 SOURCE body; the implementer only re-verifies
the line numbers live + pastes the live pytest count + runs the `--help` probe. The 5 checks (a)-(e) +
Mode A are all straightforward (a tuple literal, a format branch, a routing `if`, two exit-2 paths, a
packaging line, and doc/help text) and each has a pinning test already green. The scope is cleanly
disjoint from S1 (client vs daemon socket) and from S3 (status.sh).

The −1 reserves: (a) the exact live pytest count must be recorded (not hard-coded) — if the suite has
shifted (a test added/removed since research), the count differs but the audit logic is unchanged; the
implementer pastes whatever the live run prints. (b) The line numbers must be re-located live (the file
may have shifted a line or two); the `<L...>` placeholders make this explicit and the L1/L4 gates catch
any leftover. Both are mechanical, gate-checked steps, not judgment calls.