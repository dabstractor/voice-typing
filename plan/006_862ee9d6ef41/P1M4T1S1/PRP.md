# PRP — P1.M4.T1.S1: Audit systemd unit — all directives, VT-003/VT-004 wiring & run tests (vs PRD §4.9)

## Goal

**Feature Goal**: Produce the authoritative **`systemd/voice-typing.service` directive audit** as a NEW
`gap_systemd.md` report — verifying **ALL** PRD §4.9 directives + the two validation-round wirings
(VT-003 `__REPO__` portability placeholder; VT-004 graphical-session-target lifecycle) + the Issue-1/BUG-1
`KillMode=mixed` against the LIVE unit file, and re-running the contract's mandated command
(`.venv/bin/python -m pytest tests/test_systemd_unit.py -q`). This is a **READ-ONLY AUDIT**: the
deliverable is the report file; NO source is modified (the unit is compliant — this PRP's research
verified all 10 directives + 15/15 tests pass; the audit re-confirms live). Satisfies **Acceptance #6**
("daemon runs as systemd service, auto-restarts") — the unit IS the service definition and
`Restart=on-failure` is the auto-restart.

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_systemd.md` — a NEW self-contained `# Gap Report — P1.M4.T1.S1:
  …` file (there is NO existing `gap_systemd.md`; this subtask creates it). Format mirrors `gap_typing.md` /
  `gap_status_sh.md`. Verbatim content in Implementation Blueprint → Task 3 (the evidence is pre-filled
  from verified file:line + pinning tests; the auditor re-confirms the line numbers live + records the
  live pytest count).

> **VERIFIED VERDICT (this PRP's research): the systemd unit is COMPLIANT with PRD §4.9 — no fix needed.**
> All 10 directives present + correct (Description :2, After :9, PartOf :10, ExecStartPre :26, ExecStart :50,
> Restart :51, RestartSec :52, KillMode :67, TimeoutStopSec :78, WantedBy :86); VT-003 `__REPO__` (:50) +
> VT-004 (After/PartOf/WantedBy graphical-session :9/:10/:86) both hold; `KillMode=mixed` (:67) is the
> Issue-1/BUG-1 fix; and `tests/test_systemd_unit.py` = **15 passed in 0.01s** (re-run live this round).
> The audit's value-add = confirming the directives the suite does NOT pin (Description, RestartSec,
> KillMode, the full `After=` list, the `/usr/bin/systemctl` ExecStartPre path) by direct read, + recording
> the coverage gaps as non-blocking nuances.

**Success Definition**:
- (a) The report verifies **all 10** PRD §4.9 directives + VT-003 + VT-004 + `KillMode=mixed` against the
  LIVE `systemd/voice-typing.service` (re-grep — not trusting this PRP's line numbers blindly) and records
  a ✅ verdict + file:line evidence + a pinning test (or "coverage gap §4.x") for each.
- (b) The contract's mandated run command — `.venv/bin/python -m pytest tests/test_systemd_unit.py -q` — is
  re-run live (under `timeout 60`, per AGENTS.md Rule 1) and the pass count is recorded in the report's §3
  (do NOT hard-code the number; record what the live run prints; this research: **15 passed in 0.01s**).
- (c) The report documents the **headline nuance — `KillMode=mixed`** (§4.1): it is the load-bearing
  Issue-1/BUG-1 fix (systemd's default `control-group` SIGTERMs the whole cgroup simultaneously, wedging
  the recorder-host child mid-`text()`; `mixed` SIGTERMs the MAIN daemon only so its `host.stop()` can
  `killpg` its own child) AND it has NO dedicated test (a coverage gap, not a code gap).
- (d) The report documents the other non-defect nuances (§4.2 the untested directives Description/
  RestartSec/After-full/ExecStartPre-path; §4.3 the `__REPO__` template nature; §4.4 the cross-file tests
  corroborate VT-003/VT-004 but audit OTHER files).
- (e) **No source files are modified** — `systemd/voice-typing.service` / `tests/test_systemd_unit.py` /
  `voice_typing/launch_daemon.sh` / `install.sh` / `hypr-binds.conf` are compliant + read-only; the only
  artifact change is creating `gap_systemd.md`. `git status --short` shows ONLY
  `plan/006_862ee9d6ef41/architecture/gap_systemd.md`.
- (f) The report's scope is the **systemd UNIT directives only** — NOT `launch_daemon.sh` internals
  (P1.M4.T2.S1), NOT `install.sh` idempotency/prefetch (P1.M4.T3.S1), NOT `hypr-binds.conf` (P1.M4.T4.S1),
  NOT the daemon teardown mechanism (P1.M2.T2.S3 → `gap_lifecycle.md` §3). The 8 cross-file tests in
  `test_systemd_unit.py` are cited as CORROBORATING evidence, not re-audited.

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check,
which maps Acceptance #6 "daemon runs as systemd service, auto-restarts" to this audit's evidence) who
needs an authoritative, file:line-evidenced record that `systemd/voice-typing.service` matches PRD §4.9
on every directive — incl. the load-bearing `KillMode=mixed` (Issue-1/BUG-1), the VT-003 `__REPO__`
portability placeholder, and the VT-004 graphical-session lifecycle — so a regression (a reverted
`KillMode`, a hardcoded `/home/dustin` path, a `default.target` re-migration) cannot ship silently.

**Use Case**: A reviewer asks "does the unit point ExecStart at the wrapper (not python), import
WAYLAND_DISPLAY, restart on failure, bound the stop at 15s, deliver SIGTERM main-only via
`KillMode=mixed`, and bind to graphical-session.target — exactly as §4.9 + VT-003/VT-004 say?" The report
answers yes/no per directive with the exact source line + the pinning test (or a coverage-gap note).

**Pain Points Addressed**: Without this audit, the directives the test suite does NOT pin
(`KillMode=mixed`, `RestartSec`, `Description`, the full `After=` list, the ExecStartPre `/usr/bin/systemctl`
path) are invisible until a real-world regression bites — a reverted `KillMode=mixed` would silently
re-break the SIGTERM teardown (the Issue-1 hang); a `default.target` re-migration would silently re-introduce
the cold-boot WAYLAND race. The audit pins them to PRD §4.9 with evidence + records the coverage gaps.

## Why

- **The unit is deployed VERBATIM** (install.sh `cp`s it into `~/.config/systemd/user/`), so what lives in
  the repo IS what runs. A directive drift here ships straight to production. The audit + the 15-test suite
  are the guard.
- **`KillMode=mixed` is the keystone of the bounded-teardown story** (PRD §4.9 inline comment + §8 + the
  P1.M2.T2.S3 teardown audit). It is the single directive that lets the daemon's single-flight `host.stop()`
  `killpg` its own child instead of systemd cgroup-SIGTERMing the child mid-`text()`. The audit certifies it
  is present + records that no test pins it (the headline nuance) — so a future "cleanup" cannot drop it.
- **VT-003/VT-004 are validation-round fixes with no PRD §4.9 precedent to lean on** — they were added to
  resolve portability (`__REPO__`) and the cold-boot WAYLAND race (graphical-session.target). The audit
  records WHY they exist (so a maintainer doesn't "simplify" them back into the bugs they fixed).
- **Closes the Infrastructure audit area's first subtask (P1.M4.T1).** S1 = systemd unit → this
  `gap_systemd.md`; S2 = `launch_daemon.sh` (P1.M4.T2.S1); S3 = `install.sh` (P1.M4.T3.S1); S4 = `hypr-binds`
  (P1.M4.T4.S1). Four disjoint files; no conflict. This task's cross-file test citations stop at
  "corroborating" — it does not audit those files.
- **Read-only + parallel-safe.** The audit reads `systemd/voice-typing.service` + `tests/test_systemd_unit.py`
  and CREATES `gap_systemd.md`. No source edits → no conflict with any in-flight task.
- **The research already did the work.** This PRP's research note pre-maps every directive to its file:line
  + verdict + pinning test, so the implementing agent re-verifies + writes the report in one pass.

## What

A read-only verification of `systemd/voice-typing.service` (the 86-line INI user unit, PRD §4.9) — the
`[Unit]` block (Description :2, After :9, PartOf :10), the `[Service]` block (ExecStartPre :26,
ExecStart :50, Restart :51, RestartSec :52, KillMode :67, TimeoutStopSec :78), and the `[Install]` block
(WantedBy :86) — re-confirmed live, then documented as a new `gap_systemd.md` (mirroring `gap_typing.md`'s
format). The 10 directives + VT-003 + VT-004 + the live test run + the 4 non-defect nuances.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_systemd.md` exists, titled `# Gap Report — P1.M4.T1.S1: systemd unit directives vs PRD §4.9`.
- [ ] The report records a ✅ verdict + `systemd/voice-typing.service` file:line + a pinning test (or
  "coverage gap §4.x") for each of the 10 directives + the VT-003 + VT-004 rows.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` is re-run live; its pass count
  (baseline 15) is recorded (not hard-coded).
- [ ] The `KillMode=mixed` nuance (§4.1: Issue-1/BUG-1 fix, no dedicated test) is documented.
- [ ] The other nuances (§4.2 untested directives; §4.3 `__REPO__` template; §4.4 cross-file tests audit
  other files) are documented.
- [ ] The report ties the verdict to Acceptance #6 (daemon runs as systemd service; Restart=on-failure).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_systemd.md` — NO source modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → new report file), the `gap_typing.md` / `gap_status_sh.md` FORMAT template, the
verified verdict (compliant) + the file:line evidence + the pinning test for all 10 directives + VT-003/VT-004,
the headline `KillMode=mixed` nuance, the other nuances, the exact test command, the verbatim report body
(Task 3), and the scope boundaries are all pinned. The audit re-verifies live (re-grep + re-run) rather
than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the 4 nuances + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M4T1S1/research/systemd_unit_directive_audit.md
  why: "§0 THE VERIFIED VERDICT: unit COMPLIANT (15/15 tests). §1 the 10-directive table (each ->
        systemd/voice-typing.service:line -> ✅ -> pinning test or 'coverage gap §4.x'). §2 VT-003 (__REPO__)
        + VT-004 (graphical-session) wiring. §3 the test file's 15-test coverage map + the contract's run
        command. §4 the 4 non-defect nuances (KillMode=mixed headline; untested directives; __REPO__ template;
        cross-file tests audit other files). §5 scope boundaries. §6 output location + format. §7 tooling."
  section: "ALL load-bearing. §1 (verdict+evidence), §2 (VT-003/VT-004), §3 (coverage map), §4 (nuances),
            §5 (scope)."

# MUST READ — the file being audited (systemd/voice-typing.service — the 10 directives + VT-003/VT-004)
- file: systemd/voice-typing.service
  why: "AUDIT TARGET (read-only, 86 lines). [Unit]: Description :2, After=pipewire.service ydotool.service
        graphical-session.target :9, PartOf=graphical-session.target :10. [Service]: ExecStartPre=/usr/bin/
        systemctl --user import-environment WAYLAND_DISPLAY DISPLAY :26, ExecStart=__REPO__/voice_typing/
        launch_daemon.sh :50, Restart=on-failure :51, RestartSec=2 :52, KillMode=mixed :67 (the Issue-1/BUG-1
        fix — inline comment :53-66), TimeoutStopSec=15 :78. [Install]: WantedBy=graphical-session.target :86.
        The inline comments document WHY each non-obvious directive exists (VT-003/VT-004/KillMode/TimeoutStopSec)."
  critical: "RE-VERIFY by grep (`grep -nE '^[A-Za-z][A-Za-z0-9_-]*=' systemd/voice-typing.service`) — do NOT
             trust the line numbers blindly (re-locate them live). The audit READS this file; it does NOT edit
             it (compliant code = no modification). The whole file is INI; comments (#) + blanks are not directives."

# MUST READ — the test file (coverage to cite per directive; the contract's run command)
- file: tests/test_systemd_unit.py
  why: "440-line suite, 15 tests, pure-stdlib re+pathlib (parses the unit + wrapper/install/binds files; NO
        live systemd/GPU/CUDA/daemon/mic). _unit_lines() filters comments+blanks. The 6 UNIT-directive tests:
        test_execstart_points_at_launch_daemon_wrapper :71, test_execstartpre_imports_wayland_and_display_env
        :78, test_restart_on_failure :94, test_timeout_stop_sec_bounds_shutdown :99,
        test_systemd_unit_execstart_uses_repo_placeholder :266 (VT-003), test_unit_is_graphical_session_aware
        :341 (VT-004). The 9 CROSS-FILE tests (launch_daemon.sh/install.sh/hypr-binds.conf) corroborate
        VT-003/VT-004/Issue-1 but audit OTHER files (§4.4). Run it + record the count."
  critical: "Characterize coverage accurately. KillMode/RestartSec/Description have NO pinning test (§4.1/§4.2).
             The After= test checks graphical-session.target ∈ After but NOT pipewire/ydotool explicitly (§4.2).
             The ExecStartPre test checks import-environment+vars but NOT the /usr/bin/systemctl path (§4.2).
             Do NOT invent coverage that isn't there."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md
  why: "The format template. Structure: title (# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X) + Date + Scope +
        Audited artifacts (read-only) + Bottom line (✅) + §1 Method (commands run + observed output) + §2
        per-directive compliance TABLE (PRD req | expected | actual | file:line | pinning test | ✅) + §3 Test
        results (the live count) + §4 Mismatches/Drift/Notes (the nuances) + §5 Conclusion (PASS; ties to
        acceptance). Mirror it EXACTLY. gap_systemd.md is a NEW file (CREATE, not append)."
  critical: "Mirror the structure. Cite systemd/voice-typing.service:line + a tests/test_systemd_unit.py test
             per directive. gap_status_sh.md (P1.M3.T2.S3) is the closest sibling (same single-file CREATE
             pattern) — also a useful reference."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.9 systemd user service — the authoritative directive list (Description, After, PartOf, ExecStartPre,
        ExecStart, Restart, RestartSec, KillMode, TimeoutStopSec, WantedBy) + the inline rationale for the
        non-obvious ones. §8 risk row 'recorder.shutdown() hangs ~90s … SIGKILL after TimeoutStopSec' (the
        KillMode+TimeoutStopSec story). This is the spec each directive is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.9 + §8 as the contract."

# CONTEXT — the sibling audit PRP (the CREATE-new-gap-file precedent)
- docfile: plan/006_862ee9d6ef41/P1M3T2S3/PRP.md
  why: "The status.sh audit (P1.M3.T2.S3) CREATEd gap_status_sh.md — the EXACT same single-file-CREATE pattern
        this task follows for gap_systemd.md. Its Task 3 SOURCE (verbatim report body with <L...>→live line
        numbers) + its §4-nuance framing + its L1-L4 validation gates are the template."
  critical: "gap_systemd.md is INDEPENDENT of gap_status_sh.md (different files, different audit areas). CREATE
             the file fresh. Do NOT duplicate the status.sh findings."

# CONTEXT — the teardown audit this report cross-references (KillMode is its keystone directive)
- docfile: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "§3 (P1.M2.T2.S3 bounded teardown) certifies the daemon-side killpg-after-5s-join. KillMode=mixed
        (:67) is the unit-side counterpart that lets that daemon-side teardown run (main-only SIGTERM). This
        report cross-references §3; it does NOT re-audit the teardown mechanism."
  critical: "Do NOT re-audit daemon teardown (P1.M2.T2.S3 owns gap_lifecycle.md §3). Cite KillMode=mixed as
             the unit-side enabler + cross-reference §3."
```

### Current Codebase tree (state at P1.M4.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── systemd/
│   └── voice-typing.service     # AUDIT TARGET (read-only — the 10 directives + VT-003/VT-004 + KillMode=mixed)
├── voice_typing/launch_daemon.sh # CROSS-FILE (test reads it; audited by P1.M4.T2.S1 — NOT this task)
├── install.sh                    # CROSS-FILE (test reads it; audited by P1.M4.T3.S1 — NOT this task)
├── hypr-binds.conf               # CROSS-FILE (test reads it; audited by P1.M4.T4.S1 — NOT this task)
└── tests/
    └── test_systemd_unit.py      # AUDIT (cite the pinning test per directive; the contract's run command) — 440 lines, 15 tests
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_typing.md             # FORMAT TEMPLATE (mirror its structure)
    ├── gap_status_sh.md          # FORMAT REFERENCE (P1.M3.T2.S3 — same single-file CREATE pattern)
    ├── gap_lifecycle.md          # CROSS-REFERENCE (§3 bounded teardown — KillMode is its unit-side keystone)
    └── gap_systemd.md            # <-- CREATE (NEW file; no prior systemd gap report exists)
# NO source/test/doc files modified. The only artifact change is creating gap_systemd.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_systemd.md   # CREATE (NEW): the P1.M4.T1.S1 systemd-unit directive audit
                                                    #   (10-directive + VT-003/VT-004 compliance table + live pytest count
                                                    #    + 4 nuances [KillMode headline / untested directives / __REPO__
                                                    #    template / cross-file tests] + conclusion tied to acceptance #6).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```sh
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT; DO NOT EDIT systemd/voice-typing.service / tests/test_systemd_unit.py
#   / launch_daemon.sh / install.sh / hypr-binds.conf / PRD.md / any source. The unit is COMPLIANT (this PRP's
#   research verified all 10 directives + 15/15 tests). The ONLY artifact change is CREATING gap_systemd.md. If
#   a directive fails on re-read, document it as a real gap for a SEPARATE remediation task — do NOT fix it here
#   (consistent with every round-006 audit). (Research §0/§5.)

# CRITICAL #2 — RE-VERIFY THE LINE NUMBERS LIVE. This PRP cites the unit's directives at :2/:9/:10/:26/:50/:51/
#   :52/:67/:78/:86 + sections [Unit]:1/[Service]:12/[Install]:80 + the test functions at :71/:78/:94/:99/:266/:341.
#   These were correct at research time but the file may have shifted — re-grep
#   (`grep -nE '^[A-Za-z][A-Za-z0-9_-]*=' systemd/voice-typing.service`) and record the ACTUAL line numbers in
#   the report. Do NOT copy the PRP's numbers blind.

# CRITICAL #3 — KillMode=mixed IS THE HEADLINE NUANCE (§4.1), NOT a defect. It is the load-bearing Issue-1/BUG-1
#   fix: systemd's default control-group SIGTERMs the whole cgroup simultaneously (wedging the recorder-host child
#   mid-text()); mixed SIGTERMs the MAIN daemon only (letting its host.stop() killpg its own child), then SIGKILL
#   the group only after TimeoutStopSec. It has NO dedicated test — record as a coverage gap (§4.1), NOT a code gap.
#   Do NOT "simplify" it away or add a test here. (Research §4.1.)

# CRITICAL #4 — RECORD THE LIVE PYTEST COUNT; DO NOT HARD-CODE IT. The contract's run command is
#   `.venv/bin/python -m pytest tests/test_systemd_unit.py -q` (FULL PATH — zsh aliases python/pytest). Run it
#   (under `timeout 60` per AGENTS.md Rule 1) + paste the actual "N passed in Xs" line into §3. This research:
#   15 passed in 0.01s.

# CRITICAL #5 — CHARACTERIZE TEST COVERAGE ACCURATELY. The 15-test suite pins: ExecStart(×2), Restart,
#   TimeoutStopSec, After(PARTIAL — graphical-session only), PartOf, WantedBy, ExecStartPre(PARTIAL — import+vars,
#   not the /usr/bin path). It does NOT pin: Description, RestartSec, KillMode, the full After= list, the
#   ExecStartPre /usr/bin/systemctl path. Cite the untested ones as coverage gaps (§4.2), do NOT invent pinning
#   tests for them. Do NOT add a test here (read-only audit). (Research §1/§3/§4.2.)

# CRITICAL #6 — SCOPE IS THE UNIT DIRECTIVES ONLY. Do NOT audit launch_daemon.sh internals (P1.M4.T2.S1),
#   install.sh idempotency/prefetch (P1.M4.T3.S1), hypr-binds.conf (P1.M4.T4.S1), or the daemon teardown
#   mechanism (P1.M2.T2.S3 → gap_lifecycle.md §3). The 8 cross-file tests in test_systemd_unit.py CORROBORATE
#   VT-003/VT-004/Issue-1 wiring end-to-end — cite them as evidence, do NOT re-audit those files (§4.4).

# GOTCHA #7 — VT-003 __REPO__ IS A TEMPLATE, NOT A RUNNABLE UNIT (§4.3). The source unit's
#   ExecStart=__REPO__/voice_typing/launch_daemon.sh (:50) is a PLACEHOLDER install.sh substitutes with $REPO
#   at install time. The source unit is NOT directly runnable until then — compliant-by-design (portability),
#   NOT a defect. Pinned by test_systemd_unit_execstart_uses_repo_placeholder (:266).

# GOTCHA #8 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always `.venv/bin/python -m pytest ...`.
#   mypy NOT installed (skip). ruff at /home/dustin/.local/bin/ruff is OPTIONAL (not in .venv; not a gate; the
#   unit file is INI — ruff/mypy do not apply to it). (Research §7.)

# GOTCHA #9 — DO NOT CREATE a tests/__init__.py or edit any test. The audit only READS test_systemd_unit.py
#   (to cite pinning tests) and RUNS it. No new files except gap_systemd.md.

# GOTCHA #10 — TWO TIMEOUTS PER AGENTS.md RULE 1. The test is sub-second + pure-stdlib, but STILL wrap:
#   `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` (inner GNU timeout) + set the
#   bash-tool `timeout` param above it (outer harness backstop). This research did exactly that.
```

## Implementation Blueprint

### Data models and structure

No production data model. The deliverable is a Markdown gap-report file mirroring `gap_typing.md`'s
structure. No code changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — re-verify the contract + locate the live line numbers (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f systemd/voice-typing.service && test -f tests/test_systemd_unit.py && echo "ok: files present" || echo "PREFLIGHT FAIL"
      # ALL directives (line-numbered) — confirms the 10 + no extras:
      grep -nE '^[A-Za-z][A-Za-z0-9_-]*=' systemd/voice-typing.service
      # section headers:
      grep -nE '^\[[A-Za-z]+\]' systemd/voice-typing.service
      # KillMode=mixed present (the headline directive):
      grep -nE '^KillMode=mixed' systemd/voice-typing.service
      # the 6 unit-directive test functions (coverage to cite):
      grep -nE '^def test_(execstart_points|execstartpre_imports|restart_on_failure|timeout_stop_sec|systemd_unit_execstart_uses_repo|unit_is_graphical_session)' tests/test_systemd_unit.py
      # confirm the 3 directives with NO test (coverage gaps §4.1/§4.2):
      grep -qE 'def test_.*killmode|def test_.*restartsec|def test_.*description' tests/test_systemd_unit.py && echo "note: a KillMode/RestartSec/Description test EXISTS (update §4)" || echo "ok: no KillMode/RestartSec/Description test (coverage gaps §4.1/§4.2 confirmed)"
  - EXPECTED: both files present; the directive grep returns exactly the 10 directives (Description :2, After :9,
    PartOf :10, ExecStartPre :26, ExecStart :50, Restart :51, RestartSec :52, KillMode :67, TimeoutStopSec :78,
    WantedBy :86) + 3 section headers; the KillMode grep hits :67; the 6 unit-directive tests are located; the
    no-KillMode/RestartSec/Description-test grep confirms the coverage gaps. RECORD the actual line numbers.
  - DO NOT: edit anything yet, or touch any source/test/doc file.

Task 2: RUN the suite live (record the count for §3) — TWO TIMEOUTS per AGENTS.md Rule 1
  - RUN: timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
    (and set the bash-tool `timeout` param to 90 — above the inner 60s backstop)
  - EXPECTED: all pass (the suite is pure-stdlib re+pathlib, ~0.01s). RECORD the exact "N passed in Xs" line.
    This research: "15 passed in 0.01s". If any FAIL: that contradicts the verified-compliant verdict — READ
    the failure, and if it is a REAL unit defect, document it as a gap in §4 (do NOT fix the unit here); if it
    is an environment issue (e.g. a missing cross-file like launch_daemon.sh/install.sh/hypr-binds.conf), note it.
    (Research §3; Critical #4; Gotcha #10.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_systemd.md — write the report body from
        "Task 3 SOURCE" below, REPLACING the <...> placeholders with the LIVE line numbers from Task 1
        and the LIVE pass count from Task 2. Mirror gap_typing.md's structure exactly.
  - FILE: plan/006_862ee9d6ef41/architecture/gap_systemd.md (NEW — CREATE, do not append).
  - DO NOT: edit systemd/voice-typing.service/test_systemd_unit.py/launch_daemon.sh/install.sh/hypr-binds.conf/
    PRD.md (Critical #1); hard-code the pass count (Critical #4); flag KillMode's absent test as a code defect
    (Critical #3); invent pinning tests for untested directives (Critical #5); audit launch_daemon.sh/
    install.sh/hypr-binds.conf/daemon-teardown (Critical #6).

Task 4: VALIDATE — L1 (file exists + markdown sanity) + L2 (the pytest count is in §3) + L3 (scope guard:
        ONLY gap_systemd.md created; no source modified) + L4 (evidence spot-check). No git commit unless the
        orchestrator directs it. If asked: message "P1.M4.T1.S1: systemd-unit directive audit (compliant;
        gap_systemd.md created; no code changes)".
```

#### Task 3 SOURCE — `gap_systemd.md` (write this body; replace `<...>` with LIVE values from Task 1/2)

````markdown
# Gap Report — P1.M4.T1.S1: systemd unit directives vs PRD §4.9

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `systemd/voice-typing.service` — the systemd user unit (PRD §4.9) — against ALL directives
PRD §4.9 names (Description, After, PartOf, ExecStartPre, ExecStart, Restart, RestartSec, KillMode,
TimeoutStopSec, WantedBy) + the two validation-round wirings expressed BY the unit (VT-003 `__REPO__`
portability placeholder; VT-004 graphical-session-target lifecycle) + the Issue-1/BUG-1 `KillMode=mixed` —
and re-run the pure-Python unit suite (`tests/test_systemd_unit.py`). Subtask **P1.M4.T1.S1** of verification
round `006_862ee9d6ef41`. Satisfies **Acceptance #6** ("daemon runs as systemd service, auto-restarts").
**Audited artifacts (all read-only):**
- `systemd/voice-typing.service` — the 86-line INI user unit. `[Unit]` (`:<L1>`): Description (`:<L2>`),
  After=pipewire.service ydotool.service graphical-session.target (`:<L9>`), PartOf=graphical-session.target
  (`:<L10>`). `[Service]` (`:<L12>`): ExecStartPre=/usr/bin/systemctl --user import-environment
  WAYLAND_DISPLAY DISPLAY (`:<L26>`), ExecStart=__REPO__/voice_typing/launch_daemon.sh (`:<L50>`),
  Restart=on-failure (`:<L51>`), RestartSec=2 (`:<L52>`), KillMode=mixed (`:<L67>`, the Issue-1/BUG-1 fix —
  inline comment `:<L53>-<L66>`), TimeoutStopSec=15 (`:<L78>`). `[Install]` (`:<L80>`):
  WantedBy=graphical-session.target (`:<L86>`).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib
  (parses the unit + the wrapper/install/binds files; NO live systemd/GPU/CUDA/daemon/mic).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.9 (the directive list + inline rationale) + §8 risk
  row (the KillMode+TimeoutStopSec story).

**Bottom line:** ✅ `systemd/voice-typing.service` is **COMPLIANT** with PRD §4.9 — all 10 directives present
+ correct, VT-003 (`__REPO__`) + VT-004 (graphical-session) wiring both hold, `KillMode=mixed` is the
Issue-1/BUG-1 fix, and the suite is green (**<N> passed in <X>s**, re-run live). **No source files were
modified** — the unit faithfully implements the spec. The audit's value-add = confirming by direct read the
directives the suite does NOT pin (`KillMode=mixed`, `RestartSec`, `Description`, the full `After=` list, the
ExecStartPre `/usr/bin/systemctl` path) and recording those as non-blocking coverage observations (§4), so a
regression on the un-pinned directives cannot ship silently. Acceptance #6 (systemd service + auto-restart)
is met: the unit IS the service definition; `Restart=on-failure` (`:<L51>`) is the auto-restart;
`RestartSec=2` (`:<L52>`) the backoff.

---

## 1. Method

Each of the 10 PRD §4.9 directives + VT-003 + VT-004 was mapped 1:1 to its `systemd/voice-typing.service`
implementation by `grep -n` (the file:line evidence), and the inline comments explaining the non-obvious
directives (KillMode/TimeoutStopSec/VT-003/VT-004) were read directly. The full `tests/test_systemd_unit.py`
suite was then **re-run live** to record the actual pass count and timing. Nothing was assumed from the PRP's
embedded numbers — every line number + the pass count below was re-verified this round (the suite is pure-stdlib
`re`/`pathlib`; it parses the unit + wrapper/install/binds files — no GPU/CUDA/daemon/mic required).

### Commands run (re-verification)

```bash
# ALL directives (line-numbered) — confirms the 10 + no extras:
grep -nE '^[A-Za-z][A-Za-z0-9_-]*=' systemd/voice-typing.service
# section headers:
grep -nE '^\[[A-Za-z]+\]' systemd/voice-typing.service
# KillMode=mixed present (the headline directive):
grep -nE '^KillMode=mixed' systemd/voice-typing.service
# the unit-directive test functions (coverage to cite):
grep -nE '^def test_(execstart_points|execstartpre_imports|restart_on_failure|timeout_stop_sec|systemd_unit_execstart_uses_repo|unit_is_graphical_session)' tests/test_systemd_unit.py
# the 3 directives with NO test (coverage gaps §4.1/§4.2):
grep -qE 'def test_.*killmode|def test_.*restartsec|def test_.*description' tests/test_systemd_unit.py && echo "a test exists (update §4)" || echo "no KillMode/RestartSec/Description test (coverage gaps §4.1/§4.2)"
# the unit suite (the contract's run command), LIVE (two timeouts per AGENTS.md Rule 1)
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
[Unit]:<L1>  [Service]:<L12>  [Install]:<L80>
Description=Local voice typing daemon (RealtimeSTT)                                   :<L2>
After=pipewire.service ydotool.service graphical-session.target                        :<L9>
PartOf=graphical-session.target                                                       :<L10>
ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY     :<L26>
ExecStart=__REPO__/voice_typing/launch_daemon.sh                                      :<L50>
Restart=on-failure                                                                    :<L51>
RestartSec=2                                                                          :<L52>
KillMode=mixed                                                                        :<L67>
TimeoutStopSec=15                                                                     :<L78>
WantedBy=graphical-session.target                                                     :<L86>
(no KillMode/RestartSec/Description test — coverage gaps §4.1/§4.2)
<N> passed in <X>s
```

---

## 2. Per-directive Compliance Table (PRD §4.9 vs `systemd/voice-typing.service`)

| # | PRD §4.9 directive | expected | actual (file:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| 1 | `Description=` | `Local voice typing daemon (RealtimeSTT)` | `Description=Local voice typing daemon (RealtimeSTT)` | (none — coverage gap §4.2) | ✅ |
| 2 | `After=` | `pipewire.service ydotool.service graphical-session.target` | `After=pipewire.service ydotool.service graphical-session.target` (`:<L9>`) | `test_unit_is_graphical_session_aware` (`:<L341>`) asserts `graphical-session.target ∈ After` — PARTIAL (does not assert pipewire/ydotool explicitly); §4.2 | ✅ |
| 3 | `PartOf=` | `graphical-session.target` | `PartOf=graphical-session.target` (`:<L10>`) | `test_unit_is_graphical_session_aware` (`:<L341>`) asserts `PartOf=graphical-session.target` | ✅ |
| 4 | `ExecStartPre=` | `import-environment WAYLAND_DISPLAY DISPLAY` | `ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY` (`:<L26>`) — uses the absolute `/usr/bin/systemctl` path (best practice in units where PATH may be minimal) | `test_execstartpre_imports_wayland_and_display_env` (`:<L78>`) checks `import-environment` + `WAYLAND_DISPLAY` + `DISPLAY` — does NOT pin the `/usr/bin/systemctl` path; §4.2 | ✅ |
| 5 | `ExecStart=` | `__REPO__/voice_typing/launch_daemon.sh` (VT-003 placeholder) | `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (`:<L50>`) — the LD_LIBRARY_PATH wrapper, NOT python directly | `test_execstart_points_at_launch_daemon_wrapper` (`:<L71>`, endswith launch_daemon.sh) + `test_systemd_unit_execstart_uses_repo_placeholder` (`:<L266>`, `__REPO__` + no `/home/`) — TWO tests | ✅ |
| 6 | `Restart=` | `on-failure` | `Restart=on-failure` (`:<L51>`) | `test_restart_on_failure` (`:<L94>`) | ✅ |
| 7 | `RestartSec=` | `2` | `RestartSec=2` (`:<L52>`) | (none — coverage gap §4.2) | ✅ |
| 8 | `KillMode=` | `mixed` (Issue-1/BUG-1 fix) | `KillMode=mixed` (`:<L67>`) — SIGTERM to the MAIN daemon only (letting its `host.stop()` `killpg` its own child), SIGKILL the group only after `TimeoutStopSec` | (none — coverage gap §4.1, the HEADLINE nuance) | ✅ |
| 9 | `TimeoutStopSec=` | `15` | `TimeoutStopSec=15` (`:<L78>`) — bounds the stop so the daemon is never SIGKILLed at systemd's 90s default | `test_timeout_stop_sec_bounds_shutdown` (`:<L99>`) | ✅ |
| 10 | `WantedBy=` | `graphical-session.target` (VT-004) | `WantedBy=graphical-session.target` (`:<L86>`) — NOT `default.target` (which raced the compositor on cold boot) | `test_unit_is_graphical_session_aware` (`:<L341>`) asserts EXACTLY `WantedBy=graphical-session.target` | ✅ |

> All directives **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this round.
> The directives with no pinning test (Description, RestartSec, KillMode, the full After= list, the
> ExecStartPre path) are confirmed correct by direct read; the gaps are recorded as non-blocking coverage
> observations in §4.

### VT-003 / VT-004 wiring (expressed BY the unit)

| wiring | expected | actual (file:line) | pinning test | verdict |
|---|---|---|---|---|
| **VT-003** `__REPO__` portability | the SOURCE unit's ExecStart uses the `__REPO__` placeholder (install.sh substitutes `$REPO`); no hardcoded `/home/<user>` path | `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (`:<L50>`) — the source unit is a portable TEMPLATE, not directly runnable until install (§4.3) | `test_systemd_unit_execstart_uses_repo_placeholder` (`:<L266>`) + (the substitution in install.sh) `test_install_sh_substitutes_repo_placeholder` (`:<L280>`) | ✅ |
| **VT-004** graphical-session lifecycle | After + PartOf + WantedBy all bind to `graphical-session.target` (NOT `default.target`) | After includes it (`:<L9>`), PartOf=graphical-session.target (`:<L10>`), WantedBy=graphical-session.target (`:<L86>`) | `test_unit_is_graphical_session_aware` (`:<L341>`) + (the stale-symlink cleanup in install.sh) `test_install_sh_cleans_stale_default_target_symlink` (`:<L362>`) | ✅ |

---

## 3. Test results (the contract's run command, LIVE)

```
$ timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
.<paste the live summary line, e.g. "15 passed in 0.01s">.
```

The suite (440 lines, 15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
the wrapper/install/binds files — no GPU/CUDA/daemon/mic. **6 tests pin UNIT directives** (ExecStart×2, Restart,
TimeoutStopSec, VT-003 `__REPO__`, VT-004 graphical-session); **9 tests are CROSS-FILE** (they read
`voice_typing/launch_daemon.sh` / `install.sh` / `hypr-binds.conf` and corroborate VT-003/VT-004/Issue-1
end-to-end — those files are audited by P1.M4.T2.S1 / P1.M4.T3.S1 / P1.M4.T4.S1; §4.4). Coverage gaps:
**no test pins `KillMode=mixed`** (§4.1), `RestartSec`, `Description`, the full `After=` list, or the
ExecStartPre `/usr/bin/systemctl` path (§4.2).

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 `KillMode=mixed` is the load-bearing Issue-1/BUG-1 fix; it has NO dedicated test — coverage gap, not code gap
`KillMode=mixed` (`:<L67>`) is the keystone directive for the SIGTERM-teardown story (PRD §4.9 inline comment
`:<L53>-<L66>` + §8 risk row + the P1.M2.T2.S3 bounded-teardown audit, `gap_lifecycle.md` §3). systemd's
DEFAULT is `control-group`, which sends SIGTERM to EVERY process in the unit's cgroup SIMULTANEOUSLY — the
daemon AND the recorder-host child AND the multiprocessing resource tracker. The recorder-host child does NOT
install a SIGTERM handler (only the daemon's `main()` does), so a cgroup-wide SIGTERM kills the child mid-
`recorder.text()`, wedging the multiprocessing Queue/Process such that the daemon's correct single-flight
`host.stop()` (`proc.join` / `cmd_q.put("shutdown")`) never completes → SIGKILL @ `TimeoutStopSec=15s`
(Result=timeout). Proven: `kill -TERM <MainPID>` (signal to the MAIN process only) exits cleanly in ~1.3s;
only `systemctl stop` (cgroup-wide) wedged. `KillMode=mixed` makes systemd deliver SIGTERM to the MAIN daemon
ONLY (letting the daemon's already-correct bounded `host.stop()` tear its OWN child group down via `killpg`),
while still sending the final SIGKILL to the whole group only after `TimeoutStopSec` — preserving the outer
safety net. **No test in the file asserts `KillMode=mixed`** — this is a **non-blocking coverage
observation**, not a §4.9 violation: the directive IS present + correct-by-read; the bounded-teardown tests
in `tests/test_daemon.py` / `tests/test_recorder_host.py` exercise the daemon-side mechanism (the P1.M2.T2.S3
audit), not the unit directive. A future test-hardening pass COULD add a `test_killmode_is_mixed` (out of scope
for this read-only audit — do NOT add one here; consistent with every round-006 audit's "read-only, no new
tests" discipline). ✅

### 4.2 The untested directives (Description / RestartSec / KillMode / the full After= list / the ExecStartPre path) — coverage gaps, not code gaps
The 15-test suite pins ExecStart(×2), Restart, TimeoutStopSec, After(PARTIAL — `graphical-session.target ∈
After` only, not `pipewire.service`/`ydotool.service` explicitly), PartOf, WantedBy, ExecStartPre(PARTIAL —
`import-environment` + `WAYLAND_DISPLAY` + `DISPLAY`, not the `/usr/bin/systemctl` absolute path). It does NOT
pin: `Description=` (`:<L2>`), `RestartSec=2` (`:<L52>`), `KillMode=mixed` (`:<L67>`, §4.1), the FULL `After=`
list, or the `/usr/bin/systemctl` path. This audit CONFIRMS each by direct read (§2 table) — they are all
correct. Non-blocking coverage observations; a test-hardening pass could pin them (out of scope here). ✅

### 4.3 VT-003 `__REPO__`: the SOURCE unit is a portable TEMPLATE (not directly runnable)
The source unit's `ExecStart=__REPO__/voice_typing/launch_daemon.sh` (`:<L50>`) is NOT runnable as-is —
`__REPO__` is a PLACEHOLDER install.sh substitutes with `$REPO` (`sed -i "s#__REPO__#$REPO#g"`) when it copies
the unit into `~/.config/systemd/user/`. This is **compliant-by-design** (portability across users / repo
locations — the source unit is a template), NOT a defect. The INSTALLED unit (in `~/.config/systemd/user/`)
has the real repo path. Pinned by `test_systemd_unit_execstart_uses_repo_placeholder` (`:<L266>`). ✅

### 4.4 The 9 cross-file tests corroborate VT-003/VT-004/Issue-1 but audit OTHER files
9 of the 15 tests in `test_systemd_unit.py` read `voice_typing/launch_daemon.sh` (`test_launch_daemon_exports_
offline_vars` `:<L115>`, `test_launch_daemon_fetches_wayland_display_from_manager` `:<L164>`), `install.sh`
(`test_install_sh_offline_grep_and_summary` `:<L205>`, `test_install_sh_usage_lists_all_commands_and_correct_
keybinds` `:<L223>`, `test_install_sh_substitutes_repo_placeholder` `:<L280>`, `test_install_sh_uv_path_is_
portable` `:<L293>`, `test_install_sh_installs_stable_voicectl_launcher` `:<L306>`, `test_install_sh_cleans_
stale_default_target_symlink` `:<L362>`), and `hypr-binds.conf` (`test_hypr_binds_use_portable_home_launcher`
`:<L321>`). They CORROBORATE that the unit's VT-003/VT-004 wiring holds end-to-end (the `__REPO__` substitution
actually happens; the stale `default.target.wants` symlink is cleaned; the offline vars are exported before
exec) — but those FILES' internals are audited by **P1.M4.T2.S1** (launch_daemon.sh), **P1.M4.T3.S1**
(install.sh), and **P1.M4.T4.S1** (hypr-binds). This report's scope is the UNIT directives; it cites the
cross-file tests as evidence the wiring is exercised, WITHOUT re-auditing those files. ✅

---

## 5. Conclusion

**PASS.** `systemd/voice-typing.service` is compliant with PRD §4.9 on all 10 directives + the VT-003
(`__REPO__`) + VT-004 (graphical-session) wirings. The unit describes the service (`Description` `:<L2>`),
orders + binds to the graphical session (`After` `:<L9>` / `PartOf` `:<L10>` / `WantedBy` `:<L86>`), imports
the Wayland/X display vars (`ExecStartPre` `:<L26>`), runs the LD_LIBRARY_PATH wrapper via the portable
`__REPO__` placeholder (`ExecStart` `:<L50>`), auto-restarts on failure with a 2s backoff (`Restart` `:<L51>`
/ `RestartSec` `:<L52>` — Acceptance #6), bounds the stop at 15s (`TimeoutStopSec` `:<L78>`), and — the
keystone — delivers SIGTERM main-only via `KillMode=mixed` (`:<L67>`, the Issue-1/BUG-1 fix) so the daemon's
single-flight `host.stop()` can `killpg` its own recorder-host child instead of systemd cgroup-SIGTERMing it
mid-`text()`. The 15-test suite pins a strong subset; the un-pinned directives (KillMode/RestartSec/
Description/After-full/ExecStartPre-path) are confirmed correct by direct read and recorded as non-blocking
coverage observations (§4). **No source files were modified** (read-only audit); the sole artifact is this
report.

Acceptance #6 ("daemon runs as systemd service, auto-restarts") is met. Scope is the systemd UNIT directives
only — `launch_daemon.sh` is P1.M4.T2.S1, `install.sh` is P1.M4.T3.S1, `hypr-binds.conf` is P1.M4.T4.S1, and
the daemon teardown mechanism is P1.M2.T2.S3 (`gap_lifecycle.md` §3, which this report's `KillMode=mixed`
nuance cross-references).
````

> NOTE for the implementer: replace every `<L...>` placeholder with the ACTUAL line number from your Task-1
> greps, and paste the LIVE pytest summary line into §3. The body above is the verified-compliant verdict
> pre-filled from research — re-confirm each file:line + the pass count live (Critical #2, #4).

### Implementation Patterns & Key Details

```sh
# PATTERN 1 — the audit is READ-ONLY. The ONLY file created is gap_systemd.md. systemd/voice-typing.service /
#   test_systemd_unit.py / launch_daemon.sh / install.sh / hypr-binds.conf are compliant + untouched. If a
#   directive fails on re-read, document it as a gap for a SEPARATE remediation task (do NOT fix the unit here).
#   (Critical #1.)

# PATTERN 2 — re-verify line numbers live (grep -nE '^[A-Za-z][A-Za-z0-9_-]*=' systemd/voice-typing.service),
#   then paste them into the report's <L...> slots. Do NOT copy the PRP's numbers blindly. (Critical #2.)

# PATTERN 3 — KillMode=mixed IS THE HEADLINE NUANCE. It is the Issue-1/BUG-1 fix (main-only SIGTERM so the
#   daemon's host.stop() killpgs its own child) AND it has NO dedicated test. Record as coverage gap §4.1, NOT
#   a code gap. Do NOT "simplify" it or add a test. (Critical #3.)

# PATTERN 4 — run the suite live (timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q) + paste
#   the actual count into §3. Do NOT hard-code a number. TWO TIMEOUTS (inner GNU + outer bash-tool). (Critical #4.)

# PATTERN 5 — characterize test coverage accurately: the suite pins ExecStart(×2)/Restart/TimeoutStopSec/
#   After(partial)/PartOf/WantedBy/ExecStartPre(partial); it does NOT pin KillMode/RestartSec/Description/
#   After-full/ExecStartPre-path. Cite the gaps as §4.1/§4.2; do NOT invent pinning tests. (Critical #5.)

# PATTERN 6 — scope = UNIT directives only. The 9 cross-file tests corroborate VT-003/VT-004 but audit
#   launch_daemon.sh/install.sh/hypr-binds.conf (P1.M4.T2/T3/T4). Cite as evidence, do NOT re-audit. (Critical #6.)
```

### Integration Points

```yaml
REPORT FILE:
  - create: "plan/006_862ee9d6ef41/architecture/gap_systemd.md (NEW — mirror gap_typing.md / gap_status_sh.md structure)"
CONSUMED (read-only — NO edits):
  - systemd/voice-typing.service: "the 10 directives + VT-003/VT-004 + KillMode=mixed (the audit target)"
  - tests/test_systemd_unit.py: "cite the pinning test per directive; the contract's run command"
DISJOINT FROM SIBLINGS:
  - P1.M4.T2.S1: "launch_daemon.sh LD_LIBRARY_PATH wrapper (different file — test_systemd_unit.py cross-file tests corroborate but this audit does NOT own it)"
  - P1.M4.T3.S1: "install.sh idempotency/prefetch/service-install (different file)"
  - P1.M4.T4.S1: "hypr-binds.conf keybinds (different file)"
  - P1.M2.T2.S3: "daemon bounded-teardown mechanism (gap_lifecycle.md §3) — KillMode=mixed is the UNIT-SIDE enabler; cross-reference, do NOT re-audit"
CONSUMERS:
  - P1.M5.T5: "acceptance cross-check maps Acceptance #6 (daemon runs as systemd service, auto-restarts) to this report's Restart=on-failure evidence"
  - future maintainers: "the reference for any unit-directive change (a reverted KillMode, a default.target re-migration, a hardcoded path)"
DEPENDENCIES: none new (read-only audit + the existing pytest suite + grep).
```

## Validation Loop

> This is a READ-ONLY AUDIT. The gate is: the report exists with ✅ verdicts + live file:line evidence + the
> live pytest count + the KillMode nuance, and NO source file is modified. No GPU/CUDA/daemon/mic (the suite
> parses files).

### Level 1: Report exists + structure sanity

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_systemd.md && echo "L1 report present" || echo "L1 FAIL: report missing"
# Structure mirrors gap_typing.md:
head -1 plan/006_862ee9d6ef41/architecture/gap_systemd.md | grep -q '^# Gap Report — P1.M4.T1.S1: systemd unit' && echo "L1 title ok" || echo "L1 FAIL: title"
grep -q '^## 2\. Per-directive Compliance Table' plan/006_862ee9d6ef41/architecture/gap_systemd.md && echo "L1 §2 ok" || echo "L1 FAIL: §2 table"
grep -q '^## 3\. Test results' plan/006_862ee9d6ef41/architecture/gap_systemd.md && echo "L1 §3 ok" || echo "L1 FAIL: §3"
grep -q '^## 4\. Non-defect nuances' plan/006_862ee9d6ef41/architecture/gap_systemd.md && echo "L1 §4 ok" || echo "L1 FAIL: §4"
# No leftover <L...> placeholders (all replaced with live line numbers):
! grep -q '<L[0-9]' plan/006_862ee9d6ef41/architecture/gap_systemd.md && echo "L1 placeholders resolved" || echo "L1 FAIL: leftover <L...> placeholder"
# Expected: report present; title/§2/§3/§4 headings present; NO <L...> placeholders remain.
```

### Level 2: The contract's run command (re-run live; count recorded in §3) — TWO TIMEOUTS

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q | tee /tmp/systemd_audit_run.log
echo "exit: ${PIPESTATUS[0]}"
# Expected: exit 0; "N passed in Xs". Confirm the report's §3 pasted THIS run's summary line:
COUNT=$(grep -oE '[0-9]+ passed' /tmp/systemd_audit_run.log | head -1)
grep -q "$COUNT passed" plan/006_862ee9d6ef41/architecture/gap_systemd.md && echo "L2 count recorded" || echo "L2 FAIL: live count not in §3"
# (one-shot tee of a <1KB summary; remove it after the check: rm -f /tmp/systemd_audit_run.log)
rm -f /tmp/systemd_audit_run.log
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected: ONLY "?? plan/006_862ee9d6ef41/architecture/gap_systemd.md" (new untracked file). Any change to
#   systemd/voice-typing.service, tests/test_systemd_unit.py, voice_typing/launch_daemon.sh, install.sh,
#   hypr-binds.conf, PRD.md, tasks.json, prd_snapshot.md, .gitignore, or any source is a SCOPE VIOLATION.
git diff --name-only   # Expected: empty (the report is a NEW untracked file, not a modification)
! git status --porcelain | grep -qE 'systemd/|tests/|voice_typing/|install\.sh|hypr-binds\.conf|PRD\.md|tasks.json|prd_snapshot.md' && echo "L3 ok: no source/test/doc modified" || echo "L3 FAIL: source/test/doc modified"
# Confirm the report is disjoint from its siblings (different filenames, no overlap):
for f in gap_systemd gap_status_sh gap_typing gap_lifecycle; do test -f plan/006_862ee9d6ef41/architecture/$f.md && echo "L3 ok: $f.md coexists (disjoint)" || echo "L3 note: $f.md not present"; done
```

### Level 4: Evidence spot-check (the directives cited are real, not hand-waved)

```bash
cd /home/dustin/projects/voice-typing
# Each directive cited in the report must actually exist + match the claimed value (re-verify the line numbers):
grep -nE '^Description=Local voice typing daemon' systemd/voice-typing.service          # #1 Description
grep -nE '^After=pipewire.service ydotool.service graphical-session.target' systemd/voice-typing.service   # #2 After (FULL list)
grep -nE '^PartOf=graphical-session.target' systemd/voice-typing.service                # #3 PartOf
grep -nE '^ExecStartPre=/usr/bin/systemctl --user import-environment WAYLAND_DISPLAY DISPLAY' systemd/voice-typing.service  # #4 ExecStartPre (full path)
grep -nE '^ExecStart=__REPO__/voice_typing/launch_daemon.sh' systemd/voice-typing.service   # #5 ExecStart (VT-003)
grep -nE '^Restart=on-failure' systemd/voice-typing.service                              # #6 Restart
grep -nE '^RestartSec=2' systemd/voice-typing.service                                   # #7 RestartSec
grep -nE '^KillMode=mixed' systemd/voice-typing.service                                 # #8 KillMode (the headline nuance §4.1)
grep -nE '^TimeoutStopSec=15' systemd/voice-typing.service                              # #9 TimeoutStopSec
grep -nE '^WantedBy=graphical-session.target' systemd/voice-typing.service              # #10 WantedBy (VT-004)
# Confirm the 3 untested directives really have no test (the §4.1/§4.2 framing):
grep -qE 'def test_.*(killmode|restartsec|description)' tests/test_systemd_unit.py && echo "L4 UNEXPECTED: a KillMode/RestartSec/Description test now EXISTS (update §4)" || echo "L4 ok: no KillMode/RestartSec/Description test (coverage gaps §4.1/§4.2)"
# Expected: each directive grep hits exactly one line; the report's <L...> values match these live numbers;
#   the no-test check confirms the §4.1/§4.2 coverage-gap framing.
```

## Final Validation Checklist

### Technical Validation
- [ ] `plan/006_862ee9d6ef41/architecture/gap_systemd.md` exists with the correct title + §1-§5 structure mirroring `gap_typing.md`.
- [ ] No `<L...>` placeholders remain (all replaced with live `grep -n` line numbers).
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` → exit 0; the live pass count is pasted into §3.
- [ ] L3 scope guard: ONLY `gap_systemd.md` created (new untracked); NO source/test/doc modified.
- [ ] L4: each directive's cited file:line exists + matches the claimed value; the no-KillMode/RestartSec/Description-test check confirms the §4.1/§4.2 framing.

### Feature (Audit) Validation
- [ ] **All 10** PRD §4.9 directives verified: Description, After (full list), PartOf, ExecStartPre, ExecStart, Restart, RestartSec, KillMode, TimeoutStopSec, WantedBy — each ✅ with file:line.
- [ ] **VT-003** (`__REPO__` placeholder) + **VT-004** (graphical-session After/PartOf/WantedBy) wiring verified.
- [ ] **KillMode=mixed** documented as the Issue-1/BUG-1 fix + its absent-test coverage gap (§4.1).
- [ ] Acceptance #6 (systemd service + `Restart=on-failure` auto-restart) mapped in the conclusion.

### Code Quality Validation
- [ ] The report mirrors `gap_typing.md`'s structure (title/Date/Scope/Audited artifacts/Bottom line/§1-§5).
- [ ] Every directive row has a real `systemd/voice-typing.service:line` + a `tests/test_systemd_unit.py` pinning test (or an explicit "coverage gap §4.x" — for Description/RestartSec/KillMode/After-full/ExecStartPre-path).
- [ ] The 4 nuances are documented precisely (KillMode headline §4.1; untested directives §4.2; `__REPO__` template §4.3; cross-file tests audit other files §4.4).

### Documentation & Deployment
- [ ] The report is self-contained (scope, method, evidence, verdict) — a future maintainer can re-run the audit from it.
- [ ] Adjacent concerns correctly deferred (launch_daemon.sh → P1.M4.T2.S1; install.sh → P1.M4.T3.S1; hypr-binds → P1.M4.T4.S1; daemon teardown → P1.M2.T2.S3 / `gap_lifecycle.md` §3).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `systemd/voice-typing.service` / `tests/test_systemd_unit.py` / `launch_daemon.sh` / `install.sh` / `hypr-binds.conf` / `PRD.md` or any source — this is a READ-ONLY AUDIT; the unit is COMPLIANT (Critical #1).
- ❌ Don't run pytest without `timeout 60` (inner) + the bash-tool timeout — AGENTS.md Rule 1 (Critical #4 / Gotcha #10).
- ❌ Don't assert directive compliance without file:line evidence — every table row must cite the `systemd/voice-typing.service:line` (Critical #2).
- ❌ Don't mistake the nuances for defects: `KillMode=mixed` is the Issue-1/BUG-1 fix (§4.1); `__REPO__` is a portable template (§4.3); the untested directives are coverage gaps not code gaps (§4.2); the cross-file tests audit OTHER files (§4.4).
- ❌ Don't invent pinning tests for the untested directives (KillMode/RestartSec/Description/After-full/ExecStartPre-path) — characterize the coverage gap accurately; do NOT add a test here (Critical #5).
- ❌ Don't re-audit `launch_daemon.sh` / `install.sh` / `hypr-binds.conf` / the daemon teardown mechanism — those are P1.M4.T2/T3/T4 + P1.M2.T2.S3; cite the cross-file tests as corroborating evidence only (Critical #6).
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — `.venv/bin/python -m pytest` (Gotcha #8).
- ❌ Don't create a NEW standalone `gap_systemd.md` outside `plan/006_862ee9d6ef41/architecture/` — that IS the location (mirrors all other `gap_*.md`); do NOT also put it in the work-item `research/` dir.

---

## Confidence Score

**10/10** for one-pass success. This is a read-only audit whose findings are **pre-verified** (research note
§1: every directive mapped to `systemd/voice-typing.service:line` with the COMPLIANT verdict) and whose test
evidence is **re-ran live** (the contract's run command = **15 passed in 0.01s** this round). The 10 directives
are a direct `grep -n` of the in-tree unit file (Description :2, After :9, PartOf :10, ExecStartPre :26,
ExecStart :50, Restart :51, RestartSec :52, KillMode :67, TimeoutStopSec :78, WantedBy :86) — all confirmed
present + correct this round. The deliverable is a new report file in an established format (`gap_typing.md` /
`gap_status_sh.md`), and the headline `KillMode=mixed` nuance is documented with its Issue-1/BUG-1 rationale
+ its (non-blocking) absent-test coverage gap. Residual risk is only line-number drift, which the Task-1 grep
re-location step catches immediately, and an accidental `<L...>` placeholder left in the report, which the L1
gate catches. No code changes, no new tests, no cross-file re-auditing — the scope is tight and the evidence
is deterministic.