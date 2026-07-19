# PRP — P1.M3.T2.S3: Audit `status.sh` tmux helper — state.json read, jq filter, 60-char truncation, lite ⚡ prefix, missing-file handling (vs PRD §4.6 / §4.2ter)

## Goal

**Feature Goal**: Produce the authoritative **`status.sh` tmux-helper audit** for
`voice_typing/status.sh` against PRD §4.6 (+ §4.2ter lite ⚡ prefix) — verifying the 5 item checks
(a)-(e) + Mode A self-doc + Mode B README/install.sh references: (a) reads
`$XDG_RUNTIME_DIR/voice-typing/state.json`; (b) jq filter: `if .listening then 🎤 + partial else empty`;
(c) truncation to 60 chars (the PRD's inline snippet says `cut -c1-60`); (d) lite mode `⚡` prefix when
`mode=="lite"`; (e) handles a missing/corrupt file gracefully (`2>/dev/null` + exit 0). Plus Mode A:
the status.sh header comment IS the self-documenting tmux doc; Mode B: README §"tmux status line" +
install.sh print the snippet referencing `status.sh`. This is a **READ-ONLY AUDIT**: the deliverable is
a report file; NO source code is modified (status.sh is compliant — this PRP's research verified it;
the audit re-confirms live). Satisfies the PRD §4.6 "tmux status integration" requirement + Acceptance
#7 ("README … documents usage" — the status-line portion).

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_status_sh.md` — a NEW self-contained `# Gap Report —
  P1.M3.T2.S3: …` file (there is NO existing `gap_status_sh.md`; this subtask creates it). Format
  mirrors `gap_typing.md` / `gap_voicectl.md`. Verbatim content in Implementation Blueprint → Task 3
  (the evidence is pre-filled from verified file:line + pinning tests; the auditor re-confirms the line
  numbers live + records the live pytest count).

**Success Definition**:
- (a) The report verifies all 5 checks (a)-(e) + Mode A + Mode B against the LIVE
  `voice_typing/status.sh` + `README.md` + `install.sh` (re-grep + re-read — not trusting this PRP's
  line numbers blindly) and records a ✅ verdict + file:line evidence + a pinning test for each.
- (b) The contract's mandated run command — `.venv/bin/python -m pytest tests/test_status_sh.py -q` —
  is re-run live and the pass count is recorded in the report's §3 (do NOT hard-code the number;
  record what the live run prints; this research: 5 passed in 0.03s).
- (c) The **headline nuance — check (c) truncation**: the report documents that `status.sh` truncates
  INSIDE jq (codepoint slicing to `MAX`=default 60 + `…` overflow marker, overridable via
  `VOICE_TYPING_STATUS_MAX`) rather than via the PRD's literal `| cut -c1-60`, and explains WHY this
  is compliant-by-design (PRD §4.6 explicitly redirects to the helper with "cleaner quoting"; the
  functional 60-char intent is preserved AND improved on three axes). Recorded in nuance §4.1 so it is
  not mistaken for a dropped feature.
- (d) The 2 non-defect nuances (§4.2 the absent truncation-bound test — a coverage gap, not a code gap;
  §4.3 the `XDG_RUNTIME_DIR:-/run/user/$(id -u)` resolution superset) are recorded in §4.
- (e) **No source files are modified** — `status.sh` / `test_status_sh.py` / `README.md` /
  `install.sh` are compliant + read-only; the only artifact change is creating `gap_status_sh.md`.
  `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_status_sh.md`.
- (f) The report's scope is the **`status.sh` tmux helper only** — NOT the state.json schema/atomic
  writes (P1.M3.T1.S1 → `gap_feedback.md`, COMPLETE), NOT `voicectl` (P1.M3.T2.S2 → `gap_voicectl.md`),
  NOT the daemon control socket (P1.M3.T2.S1 → `gap_socket.md`, COMPLETE), NOT a full README/install.sh
  audit (P1.M6.T1.S1 / P1.M4.T3.S1).

> **VERIFIED VERDICT (this PRP's research): `status.sh` is COMPLIANT on all 5 checks + Mode A/B — no
> code fix needed.** The audit's job is to re-confirm this live and document it with evidence + the 3
> nuances. If a check surprisingly fails on re-read, document it as a real gap for a SEPARATE
> remediation task (this audit does not fix code).

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M6.T1.S1 README audit +
P1.M5.T5 acceptance cross-check) who needs an authoritative, file:line-evidenced record that
`status.sh` — the user-visible tmux status line — matches PRD §4.6: it reads the daemon's state file,
renders `🎤 <partial>` while listening, `⚡🎤 <partial>` in lite mode, truncates long lines to ~60 chars,
and never aborts (exit 0) on a missing/corrupt state file.

**Use Case**: A reviewer asks "does the tmux status line show live partials, prefix lite mode with ⚡,
truncate to 60, and survive a missing state.json with exit 0 — exactly as §4.6 / §4.2ter say?" The report
answers yes/no per check with the exact source lines + the pinning test.

**Pain Points Addressed**: Without this audit, a regression (a dropped `⚡` lite prefix; a
truncation that silently chops a multibyte glyph; a missing-file path that exits 2 instead of 0 and
breaks a non-tmux caller) would be invisible until a user sees a garbled status line or a script that
exits non-zero. The audit pins the helper to PRD §4.6 / §4.2ter with evidence.

## Why

- **PRD §4.6's "tmux status integration" is the user's primary feedback surface while dictating.** The
  partial text, the lite-mode indicator, and the truncation all live here. This audit closes the §4.6
  requirement that says *"Provide a small `voice_typing/status.sh` helper script instead of inline jq,
  and reference that"* — confirming the helper exists, is referenced in README + install.sh, and behaves
  per spec.
- **Closes the control-plane audit area (P1.M3.T2, S3 — the last sibling).** S1 = daemon socket →
  `gap_socket.md` (COMPLETE); S2 = `voicectl` CLI → `gap_voicectl.md` (in flight, parallel); S3 =
  `status.sh` → this `gap_status_sh.md`. Three disjoint filenames; no conflict.
- **Read-only + parallel-safe.** The audit reads `status.sh` + `test_status_sh.py` + `README.md` +
  `install.sh` and CREATES `gap_status_sh.md`. The parallel S2 CREATES `gap_voicectl.md` — a DIFFERENT
  file; no conflict. No source edits → no conflict with any in-flight implementation task.
- **The research already did the work.** This PRP's research note pre-maps every check to its
  file:line + verdict + pinning test, so the implementing agent re-verifies + writes the report in one
  pass (the value of a PRP: curated context, not open-ended exploration).

## What

A read-only verification of `voice_typing/status.sh` (the 50-line POSIX `sh` + `jq` tmux status-right
helper) — the `STATE` path resolution (`:30`), the `jq -r` render program (`:38-44`: the
`.listening // false` gate, the `🎤 ` literal, the `.partial // ""` default, the `.mode == "lite"` →
`⚡` prefix, the codepoint truncation to `MAX` + `…` overflow), the `2>/dev/null` + trailing `exit 0`
failure handling (`:45` + `:50`), the `MAX` override (`:37`), the self-documenting header comment
(`:1-28`), and the README + install.sh references (Mode B) — re-confirmed live, then documented as a
new `gap_status_sh.md` (mirroring `gap_typing.md`'s format). The 5 checks (a)-(e) + Mode A + Mode B +
the live test run + the 3 non-defect nuances.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_status_sh.md` exists, titled `# Gap Report — P1.M3.T2.S3: status.sh tmux helper (§4.6)`.
- [ ] The report records a ✅ verdict + `status.sh`/`README.md`/`install.sh` file:line + a pinning test (`tests/test_status_sh.py`) for each of the 5 checks (a)-(e) + the Mode A + Mode B rows.
- [ ] `.venv/bin/python -m pytest tests/test_status_sh.py -q` is re-run live; its pass count is recorded (not hard-coded).
- [ ] The check (c) truncation nuance (jq codepoint slicing + `…` vs the PRD's literal `cut -c1-60`) is documented in §4.1 as compliant-by-design.
- [ ] The 2 other non-defect nuances (§4.2 no truncation-bound test; §4.3 the XDG fallback superset) are documented in §4.
- [ ] The report's scope is the `status.sh` helper only — not state.json schema (P1.M3.T1.S1), not `voicectl` (S2), not the daemon socket (S1), not a full README/install.sh audit.
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_status_sh.md` — NO source files modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → new report file), the `gap_typing.md` FORMAT template, the verified verdict
(compliant) + the file:line evidence + the pinning test for all 5 checks + Mode A/B, the headline
truncation nuance (why jq-slicing is compliant vs the PRD's literal `cut`), the 2 other nuances, the
exact test command, the verbatim report body (Task 3), and the scope boundaries are all pinned. The
audit re-verifies live (re-grep + re-read + re-run) rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the 3 nuances + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M3T2S3/research/status_sh_audit.md
  why: "§0 THE VERIFIED VERDICT: status.sh COMPLIANT on all 5 checks + Mode A/B. §1 each check (a-e +
        Mode A/B) -> status.sh/README.md/install.sh file:line -> ✅ -> pinning test. §2 THE TRUNCATION
        NUANCE (the audit's headline finding: jq codepoint slicing + ellipsis vs cut -c1-60). §3 the
        absent-truncation-test coverage gap. §4 scope boundaries. §5 the test-suite coverage map (5
        tests). §6 exit-code/failure-semantics detail (check e). §7 tooling."
  section: "ALL load-bearing. §1 (verdict+evidence), §2 (truncation nuance), §5 (coverage map),
            §6 (exit codes), §4 (scope)."

# MUST READ — the file being audited (status.sh: STATE path / jq render / 2>/dev/null / exit 0 / MAX / header)
- file: voice_typing/status.sh
  why: "AUDIT TARGET (read-only, 50 lines). STATE path :30 ('${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/
        voice-typing/state.json' — the XDG-fallback superset, nuance §4.3). MAX override :37
        ('${VOICE_TYPING_STATUS_MAX:-60}'). jq render :38-44 (the .listening//false gate :39; the
        .mode=='lite'->⚡ prefix :40; the 🎤 literal + .partial//'' :40; the truncation if/else :42-44
        — codepoint slice + …). 2>/dev/null :45 (jq stderr swallow). exit 0 :50 (the Issue 2 fix).
        Header self-doc block :1-28 (USER INTEGRATION + the 2-line tmux.conf snippet + the MAX
        override note)."
  critical: "RE-VERIFY by grep + read — do NOT trust the line numbers blindly (re-locate them live).
             The audit READS this file; it does NOT edit it (compliant code = no modification).
             CRITICAL: there is NO 'cut -c1-60' anywhere — truncation is jq-internal. That is the
             headline nuance (§4.1), NOT a missing feature."

# MUST READ — the test file (coverage to cite per check; the contract's run command)
- file: tests/test_status_sh.py
  why: "109-line suite, 5 tests, pure-stdlib subprocess (runs the REAL script with a controlled
        XDG_RUNTIME_DIR; no GPU/CUDA/daemon/mic). _run_status :26 (full-env carry so jq/id/sh stay on
        PATH; timeout=10). _write_state :43. test_status_sh_missing_state_file_exits_zero_with_empty_stdout
        :51 (check e — jq exit 2). test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout :61
        (check e — jq exit 5). test_status_sh_listening_renders_partial_and_exits_zero :71 (check b —
        🎤 + partial). test_status_sh_lite_mode_prefixes_bolt :87 (check d — ⚡ lite + normal-negative).
        test_status_sh_not_listening_renders_empty_and_exits_zero :102 (check b — idle empty). NO test
        for check (c) truncation (nuance §4.2). Run it + record the count."
  critical: "Characterize coverage accurately. (c) has NO pinning test — cite it as nuance §4.2, do NOT
             invent a truncation test. The suite is subprocess-based, NOT mocked — it exercises the
             real shell + jq interpreter (so it catches real breakage)."

# MUST READ — Mode B references (README + install.sh cite status.sh, per PRD §4.6)
- file: README.md
  why: "§'## tmux status line' :135-150 — the two-line snippet (status-interval 1 :141 +
        status-right '#(.../status.sh)' :142) + the result description :145 + the state.json reference
        :150. Also :63, :69, :111, :132 reference the tmux status line / ⚡ lite prefix in context.
        PRD §4.6: 'document in README' — Mode B."
  critical: "This audit only CONFIRMS status.sh is referenced here (Mode B); it does NOT audit the rest
             of README (that is P1.M6.T1.S1)."

- file: install.sh
  why: ":212-214 — prints the snippet verbatim: '  set -g status-interval 1' :213 +
        '  set -g status-right \"#($REPO/voice_typing/status.sh)\"' :214. PRD §4.6: 'install.sh prints
        the snippet' — Mode B. The header 'tmux status (add these TWO lines ...)' :212."
  critical: "This audit only CONFIRMS install.sh prints the status.sh snippet; it does NOT audit
             install.sh idempotency/model-prefetch (that is P1.M4.T3.S1)."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md
  why: "The format template. Structure: title (# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X) + Date +
        Scope + Audited artifacts (read-only) + Bottom line (✅) + §1 Method (w/ commands run + observed
        output) + §2 per-check compliance TABLE (PRD req | expected | actual | file:line | pinning test |
        ✅) + §3 Test results (the live count) + §4 non-defect nuances + §5 Conclusion (PASS; no fix).
        Mirror it EXACTLY. gap_status_sh.md is a NEW file (CREATE, not append)."
  critical: "Mirror the structure. Cite status.sh/README.md/install.sh file:line + a tests/test_status_sh.py
             test per check. gap_voicectl.md (S2) + gap_socket.md (S1) are the closest siblings (same
             task area P1.M3.T2) — also useful references."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.6 Feedback: the state file ($XDG_RUNTIME_DIR/voice-typing/state.json with
        listening/phase/models_loaded/mode/partial/last_final/ts); the tmux status integration block —
        the inline '#(jq -r \"if .listening then 🎤 + .partial else empty end ... | cut -c1-60)' snippet
        AND the directive 'Provide a small voice_typing/status.sh helper script instead of inline jq ...
        cleaner quoting'; 'document in README, and install.sh prints the snippet; do NOT edit the user's
        tmux.conf'. §4.2ter: 'the tmux status line prefixes lite with ⚡'. This is the spec each check
        is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.6/§4.2ter as the contract. CRITICAL:
             the PRD's 'cut -c1-60' is in the INLINE jq snippet that the PRD itself redirects AWAY from
             in favor of the status.sh helper — so its absence in status.sh is compliant (nuance §4.1)."

# CONTEXT — the parallel task contract (P1.M3.T2.S2 = voicectl; DIFFERENT file; no conflict)
- file: plan/006_862ee9d6ef41/P1M3T2S2/PRP.md
  why: "The parallel item (voicectl CLI audit) CREATEs gap_voicectl.md — a DIFFERENT file from
        gap_status_sh.md (which this task CREATEs). Confirms the two audits are disjoint (tmux helper
        vs CLI client) and neither touches the other's report or any source file."
  critical: "gap_status_sh.md is INDEPENDENT of gap_voicectl.md. CREATE the file fresh. S2 audits
             voice_typing/ctl.py; S3 audits voice_typing/status.sh — do not duplicate S2's CLI findings
             (e.g. voicectl's status rendering is S2's concern; S3 cares only that status.sh renders
             the state.json fields correctly)."
```

### Current Codebase tree (state at P1.M3.T2.S3 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/status.sh               # AUDIT TARGET (read-only — STATE path / jq render / 2>/dev/null / exit 0 / MAX / header)
├── README.md                            # AUDIT (Mode B: §"tmux status line" :135-150 cites status.sh — read-only)
├── install.sh                           # AUDIT (Mode B: :212-214 prints the status.sh snippet — read-only)
└── tests/
    └── test_status_sh.py                # AUDIT (cite the pinning test per check; the contract's run command) — 109 lines, 5 tests
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_typing.md                    # FORMAT TEMPLATE (mirror its structure)
    ├── gap_socket.md                    # FORMAT REFERENCE (S1, same task area; COMPLETE)
    ├── gap_voicectl.md                  # FORMAT REFERENCE (S2, same task area; in flight — different file)
    └── gap_status_sh.md                 # <-- CREATE (NEW file; no prior status.sh gap report exists)
# NO source/test/doc files modified. The only artifact change is creating gap_status_sh.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_status_sh.md   # CREATE (NEW): the P1.M3.T2.S3 status.sh tmux-helper audit
                                                      #   (5-check + Mode A/B compliance table + live pytest count
                                                      #    + 3 nuances [truncation/coverage/XDG-superset] + conclusion).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```sh
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT; DO NOT EDIT status.sh / test_status_sh.py / README.md /
#   install.sh / PRD.md / any source. status.sh is COMPLIANT (this PRP's research verified it). The ONLY
#   artifact change is CREATING gap_status_sh.md. If a check fails on re-read, document it as a real gap
#   for a SEPARATE remediation task — do NOT fix it here (consistent with S1 + S2 + every round-006
#   audit). (Research §0.)

# CRITICAL #2 — RE-VERIFY THE LINE NUMBERS LIVE. This PRP cites status.sh:30/STATE, :37/MAX, :38-44/jq
#   render, :45/2>/dev/null, :50/exit 0, :1-28/header; README.md:135-150/§tmux + :141-142 snippet;
#   install.sh:212-214 snippet; test_status_sh.py:51/61/71/87/102 tests. These were correct at research
#   time but the files may have shifted — re-grep (e.g. `grep -n "STATE=" status.sh`,
#   `grep -n "VOICE_TYPING_STATUS_MAX" status.sh`, `grep -n "if (.listening" status.sh`,
#   `grep -n "status.sh" README.md install.sh`, `grep -n "^def test_" tests/test_status_sh.py`) and
#   record the ACTUAL line numbers in the report. Do NOT copy the PRP's numbers blind.

# CRITICAL #3 — THERE IS NO `cut -c1-60` IN status.sh; THAT IS COMPLIANT, NOT A GAP. PRD §4.6's inline
#   snippet truncates with `| cut -c1-60`, BUT the same sentence redirects to the helper: "Provide a
#   small voice_typing/status.sh helper script instead of inline jq … cleaner quoting." status.sh
#   truncates INSIDE jq via codepoint slicing to MAX (default 60) + a `…` overflow marker, overridable
#   via VOICE_TYPING_STATUS_MAX. This preserves the 60-char intent AND is strictly better
#   (codepoint-accurate emoji handling + visible truncation + override). Record as nuance §4.1
#   (compliant-by-design); do NOT "restore" cut (that regresses the improvements). (Research §2.)

# CRITICAL #4 — RECORD THE LIVE PYTEST COUNT; DO NOT HARD-CODE IT. The contract's run command is
#   `.venv/bin/python -m pytest tests/test_status_sh.py -q` (FULL PATH — zsh aliases python/pytest).
#   Run it + paste the actual "N passed in Xs" line into §3. The suite is pure-stdlib subprocess
#   (runs the REAL script; no GPU/CUDA/daemon/mic) → ~0.03s. This research: 5 passed in 0.03s.

# CRITICAL #5 — CHECK (c) HAS NO PINNING TEST; CITE IT AS A COVERAGE GAP, NOT A CODE GAP. The 5-test
#   suite pins (a) transitively, (b), (d), (e) — but NOT the 60-codepoint truncation bound or the `…`
#   marker (no test feeds a >60-char partial). Document this as nuance §4.2 (non-blocking; the logic
#   exists + is correct-by-inspection). Do NOT add a test here (read-only audit; every round-006 audit
#   keeps "no new tests" discipline — a test-hardening pass would be a separate task).

# CRITICAL #6 — SCOPE IS THE status.sh HELPER ONLY. Do NOT audit the state.json schema/atomic writes
#   (P1.M3.T1.S1 → gap_feedback.md, COMPLETE), voicectl (S2 → gap_voicectl.md), the daemon socket
#   (S1 → gap_socket.md, COMPLETE), or a full README/install.sh audit (P1.M6.T1.S1 / P1.M4.T3.S1). S3
#   cares that status.sh READS + RENDERS the state.json fields correctly — not how the daemon WRITES
#   them (feedback.py's job) or whether voicectl surfaces them (ctl.py's job).

# GOTCHA #7 — XDG_FALLBACK SUPERSET (nuance §4.3). status.sh:30 uses
#   `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}` — it resolves to $XDG_RUNTIME_DIR when set (the PRD path)
#   AND falls back to /run/user/$(id -u) (the conventional default) when unset. This is STRICTLY more
#   robust than the bare $XDG_RUNTIME_DIR the PRD names; record as nuance §4.3 (compliant-by-design
#   superset, mirroring gap_typing.md's OSError-superset framing). The test suite exercises this via
#   _run_status setting XDG_RUNTIME_DIR=tmp_path.

# GOTCHA #8 — THE SCRIPT IS POSIX sh + jq ONLY (no bash, no set -e). status.sh:1 `#!/bin/sh`; the
#   header note explicitly says "NO `set -e`: a missing or malformed state.json must print an empty
#   line with exit 0 (never abort)." The failure chain: jq exits non-zero (2=missing, 5=corrupt) →
#   stderr swallowed by `2>/dev/null` → stdout already empty (jq `// ""` defaults) → the trailing
#   `exit 0` zeroes the code. Both regressions pinned (:51 + :61). (Research §6.)

# GOTCHA #9 — tmux's #(...) SUBSTITUTION IGNORES THE EXIT CODE (captures stdout only). So even without
#   the `exit 0` fix, the tmux status line would still render empty on failure (stdout-empty). The
#   `exit 0` (Issue 2 fix, :50) honors the documented "exit 0 (never abort)" contract for NON-tmux
#   callers that check $? (e.g. a user running status.sh by hand, or a wrapper script). Both matters;
#   the test asserts both exit 0 AND empty stdout.

# GOTCHA #10 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always
#   `.venv/bin/python -m pytest ...`. mypy NOT installed (skip). ruff at
#   /home/dustin/.local/bin/ruff is OPTIONAL (not in .venv; not a gate; status.sh is a SHELL SCRIPT —
#   ruff/mypy do not apply to it). shellcheck is not in the project's gate (do not introduce one).
#   (Research §7.)

# GOTCHA #11 — DO NOT CREATE a tests/__init__.py or edit any test. The audit only READS test_status_sh.py
#   (to cite pinning tests) and RUNS it. No new files except gap_status_sh.md.

# GOTCHA #12 — TWO TIMEOUTS PER AGENTS.md RULE 1. The test is sub-second + pure-stdlib, but STILL wrap:
#   `timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q` (inner GNU timeout) + set the
#   bash-tool `timeout` param above it (outer harness backstop). This research did exactly that.
```

## Implementation Blueprint

### Data models and structure

No production data model. The deliverable is a Markdown gap-report file mirroring `gap_typing.md`'s
structure. No shell/Python changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — re-verify the contract + locate the live line numbers (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/status.sh && test -f tests/test_status_sh.py && test -f README.md && test -f install.sh && echo "ok: files present" || echo "PREFLIGHT FAIL"
      grep -nE 'STATE=|VOICE_TYPING_STATUS_MAX|MAX=' voice_typing/status.sh
      grep -nE 'if \(\.listening|mode == "lite"|\.partial|⚡|🎤|then \$line' voice_typing/status.sh
      grep -nE '2>/dev/null|exit 0' voice_typing/status.sh
      grep -nE 'cut -c1-60' voice_typing/status.sh || echo "ok: NO cut -c1-60 in status.sh (truncation is jq-internal — nuance §4.1)"
      grep -nE 'status\.sh|status-right|status-interval|tmux status line' README.md install.sh
      grep -nE '^def test_' tests/test_status_sh.py
  - EXPECTED: all files present; the grep hits locate STATE/MAX/the jq render (listening gate + lite
    prefix + 🎤 literal + truncation if/else)/2>/dev/null/exit 0; README + install.sh both cite
    status.sh; the `cut -c1-60` grep returns NOTHING (confirms the headline nuance — truncation is
    jq-internal); the 5 tests are located. RECORD the actual line numbers for the report.
  - DO NOT: edit anything yet, or touch any source/test/doc file.

Task 2: RUN the suite live (record the count for §3) — TWO TIMEOUTS per AGENTS.md Rule 1
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q
    (and set the bash-tool `timeout` param to 140 — above the inner 120s backstop)
  - EXPECTED: all pass (the suite is pure-stdlib subprocess, ~0.03s). RECORD the exact "N passed in Xs"
    line. This research: "5 passed in 0.03s". If any FAIL: that contradicts the verified-compliant
    verdict — READ the failure, and if it is a REAL status.sh defect, document it as a gap in §4 (do
    NOT fix status.sh here); if it is an environment issue (e.g. jq not installed — check `command -v
    jq`), note it. (Research §5; Critical #4; Gotcha #12.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_status_sh.md — write the report body from
        "Task 3 SOURCE" below, REPLACING the <...> placeholders with the LIVE line numbers from Task 1
        and the LIVE pass count from Task 2. Mirror gap_typing.md's structure exactly.
  - FILE: plan/006_862ee9d6ef41/architecture/gap_status_sh.md (NEW — CREATE, do not append).
  - DO NOT: edit status.sh/test_status_sh.py/README.md/install.sh/PRD.md (Critical #1); hard-code the
    pass count (Critical #4); flag the absent `cut` as a defect (Critical #3); flag the absent
    truncation test as a code defect (Critical #5); audit feedback.py/ctl.py/daemon.py (Critical #6).

Task 4: VALIDATE — L1 (file exists + markdown sanity) + L2 (the pytest count is in §3) + L3 (scope
        guard: ONLY gap_status_sh.md created; no source modified). No git commit unless the orchestrator
        directs it. If asked: message "P1.M3.T2.S3: status.sh tmux-helper audit (compliant;
        gap_status_sh.md created; no code changes)".
```

#### Task 3 SOURCE — `gap_status_sh.md` (write this body; replace `<...>` with LIVE values from Task 1/2)

````markdown
# Gap Report — P1.M3.T2.S3: status.sh tmux helper (§4.6)

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/status.sh` — the tmux status-right helper (PRD §4.6) — against the 5 item
checks (a)-(e) + Mode A (the self-documenting header comment) + Mode B (README + install.sh reference
`status.sh`): (a) reads `$XDG_RUNTIME_DIR/voice-typing/state.json`; (b) jq filter: `if .listening then
🎤 + partial else empty`; (c) truncation to 60 chars (PRD §4.6 inline snippet says `cut -c1-60`); (d)
lite mode `⚡` prefix when `mode=="lite"` (§4.2ter); (e) handles missing/corrupt file gracefully
(`2>/dev/null` + exit 0) — and re-run the pure-Python unit suite (`tests/test_status_sh.py`). Subtask
**P1.M3.T2.S3** of verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/status.sh` — `STATE` path resolution (`:<L30>`), `MAX` override (`:<L37>`), the `jq -r`
  render program (`:<L38>-<L44>`: `.listening // false` gate `:<L39>`; `.mode == "lite"` → `⚡` prefix
  `:<L40>`; `🎤 ` literal + `.partial // ""` `:<L40>`; truncation if/else `:<L42>-<L44>`), `2>/dev/null`
  (`:<L45>`), trailing `exit 0` (`:<L50>`, the Issue 2 fix), self-documenting header block (`:<L1>-<L28>`).
- `tests/test_status_sh.py` — the 5-test suite (the contract's run command); pure-stdlib subprocess
  (runs the REAL script with a controlled `XDG_RUNTIME_DIR`; no GPU/CUDA/daemon/mic).
- `README.md` — §"tmux status line" (`:<L135>-<L150>`): the two-line snippet (`:<L141>-<L142>`) + the
  result description + the state.json reference.
- `install.sh` — prints the snippet verbatim (`:<L212>-<L214>`).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.6 (state file + the tmux status integration
  block incl. the "Provide a small `status.sh` helper … cleaner quoting" directive) + §4.2ter (the `⚡`
  lite prefix).

**Bottom line:** ✅ `status.sh` is **COMPLIANT** with PRD §4.6 / §4.2ter — all 5 checks (a)-(e) + Mode A
self-doc + Mode B README/install.sh references hold, each mapped to a `status.sh`/`README.md`/
`install.sh` file:line and a pinning test, and the suite is green (**5 passed in 0.03s**, re-run live).
**No source files were modified** — the helper faithfully implements the spec, INCLUDING the deliberate
jq-internal truncation that refines the PRD's inline `cut -c1-60` snippet per §4.6's own "cleaner
quoting" directive. The three non-blocking observations (the jq-truncation refinement; the absent
truncation-bound test; the XDG-fallback resolution superset) are recorded in §4 so they are not
mistaken for defects.

---

## 1. Method

Each of the 5 item checks (a)-(e) + Mode A/B was mapped 1:1 to its `status.sh`/`README.md`/`install.sh`
implementation by `grep -n` (the file:line evidence), and the truncation approach + the failure-handling
chain were read directly. The full `tests/test_status_sh.py` suite was then **re-run live** to record
the actual pass count and timing. Nothing was assumed from the PRP's embedded numbers — every line
number + the pass count below was re-verified this round (the suite is pure-stdlib `subprocess`/`os`/
`pathlib`; it runs the REAL `voice_typing/status.sh` under a controlled `XDG_RUNTIME_DIR` — no GPU/
CUDA/daemon/mic required).

### Commands run (re-verification)

```bash
# (a-e + Mode A) Line-number map (grep -n)
grep -nE 'STATE=|VOICE_TYPING_STATUS_MAX|MAX=' voice_typing/status.sh
grep -nE 'if \(\.listening|mode == "lite"|\.partial|⚡|🎤' voice_typing/status.sh
grep -nE '2>/dev/null|exit 0' voice_typing/status.sh
# (c) the headline nuance check — there is NO cut -c1-60 in status.sh (truncation is jq-internal):
grep -nE 'cut -c1-60' voice_typing/status.sh || echo "CLEAN: no cut -c1-60 (truncation is jq-internal — §4.1)"
# Mode B references:
grep -nE 'status\.sh|status-right|status-interval|tmux status line' README.md install.sh
# the pinning tests:
grep -nE '^def test_' tests/test_status_sh.py
# the unit suite (the contract's run command), LIVE (two timeouts per AGENTS.md Rule 1)
timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
(a) <L30>:STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"   (XDG-fallback superset, §4.3)
(b) <L39>:if (.listening // false)  <L40>:... "🎤 " + (.partial // "")  else "" end
(c) <L37>:MAX="${VOICE_TYPING_STATUS_MAX:-60}"  <L42>-<L44>:if ($line|length) > ($max|tonumber) then $line[:($max-1)] + "…" else $line end
    (c-clean) grep 'cut -c1-60' status.sh → CLEAN (truncation is jq-internal, §4.1)
(d) <L40>:(if (.mode == "lite") then "⚡" else "" end)
(e) <L45>:' "$STATE" 2>/dev/null   <L50>:exit 0
(Mode A) <L1>-<L28>: header self-doc block (USER INTEGRATION + 2-line tmux.conf snippet + MAX override note)
(Mode B) README.md:<L135>-<L150> §"tmux status line" (<L141>-<L142> snippet)  install.sh:<L212>-<L214> snippet
.....                                                                                          [100%]
<N> passed in <X>s
```

---

## 2. Per-check Compliance Table (PRD §4.6 / §4.2ter vs `status.sh`)

| # | PRD requirement | Expected (spec) | `status.sh` / `README.md` / `install.sh` actual | file:line | Pinning tests (`tests/test_status_sh.py`) | Verdict |
|---|---|---|---|---|---|---|
| **(a)** | reads `$XDG_RUNTIME_DIR/voice-typing/state.json` | `STATE` resolves the XDG runtime path | `STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"` — resolves to `$XDG_RUNTIME_DIR` when set (the PRD path) AND falls back to `/run/user/$(id -u)` when unset (the conventional default — a strictly-more-robust superset, §4.3) | `status.sh:<L30>` | `_run_status` (`:<L26>`) sets `XDG_RUNTIME_DIR`→`tmp_path`; every test's `_write_state` proves the script reads `<tmp>/voice-typing/state.json` (resolution exercised transitively by all 5 tests) | ✅ |
| **(b)** | jq filter: `if .listening then 🎤 + partial else empty` | listening → `🎤 <partial>`; not listening → `` (empty) | `jq -r` program: `(if (.listening // false) then (… + "🎤 " + (.partial // "")) else "" end) as $line` — null-safe `.listening // false` + `.partial // ""`, `🎤 ` literal, `else ""` empty branch | render program `status.sh:<L38>-<L44>`; gate `<L39>`; emoji+partial `<L40>` | `test_status_sh_listening_renders_partial_and_exits_zero` (`:<L71>`, `🎤` prefix + `hello world`); `test_status_sh_not_listening_renders_empty_and_exits_zero` (`:<L102>`, idle → empty stdout) | ✅ |
| **(c)** | truncate to 60 chars (PRD §4.6 inline snippet: `cut -c1-60`) | a long line capped at ~60 chars | **NO `cut -c1-60`** — truncation is jq-INTERNAL: `MAX="${VOICE_TYPING_STATUS_MAX:-60}"`; `if ($line\|length) > ($max\|tonumber) then $line[:($max-1)] + "…" else $line end` → codepoint slice to 60 + `…` overflow marker, overridable. Compliant-by-design: PRD §4.6 redirects to the helper ("cleaner quoting"); the 60-char intent is preserved AND improved (codepoint-accurate emoji, visible `…`, override hook). See §4.1 | `MAX` `status.sh:<L37>`; truncation if/else `<L42>-<L44>` | (none — coverage gap, §4.2; not a code gap) | ✅ |
| **(d)** | lite mode `⚡` prefix when `mode=="lite"` (§4.2ter) | the status line prefixes lite with `⚡` | `(if (.mode == "lite") then "⚡" else "" end)` prepended before `🎤 ` → `⚡🎤 <partial>` in lite, `🎤 <partial>` in normal/missing | `status.sh:<L40>` | `test_status_sh_lite_mode_prefixes_bolt` (`:<L87>`, `⚡🎤` prefix in lite + NOT `⚡` in normal — negative guard) | ✅ |
| **(e)** | handles missing/corrupt file gracefully (`2>/dev/null`) | missing/corrupt state.json → empty stdout + exit 0 (never abort) | `2>/dev/null` swallows jq's stderr (exit 2=missing, 5=corrupt); jq `// ""` defaults keep stdout empty; the trailing `exit 0` zeroes the exit code (Issue 2 fix) honoring the "exit 0 (never abort)" contract for non-tmux callers that check `$?` | `status.sh:<L45>` (`2>/dev/null`) + `<L50>` (`exit 0`) | `test_status_sh_missing_state_file_exits_zero_with_empty_stdout` (`:<L51>`, no file → exit 0+empty — jq exit 2 regression); `test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout` (`:<L61>`, `not json{{}` → exit 0+empty — jq exit 5 regression) | ✅ |
| **Mode A** | `status.sh` is self-documenting (item DOCS) | the header comment IS the tmux doc | the `# USER INTEGRATION #` block documents the 2-line `tmux.conf` snippet (`status-interval 1` + `status-right "#(.../status.sh)"`), the expected result, and the `VOICE_TYPING_STATUS_MAX` override | `status.sh:<L1>-<L28>` (snippet block `<L8>-<L23>`) | (n/a — documentation; corroborated by reading the header) | ✅ |
| **Mode B** | README documents it + install.sh prints the snippet (PRD §4.6) | both reference `status.sh` (NOT inline jq) | README §"tmux status line" has the 2-line snippet; install.sh `echo`s the snippet verbatim with `$REPO/voice_typing/status.sh` | README.md `:<L135>-<L150>` (snippet `<L141>-<L142>`); install.sh `:<L212>-<L214>` (snippet `<L213>-<L214>`) | (n/a — documentation; corroborated by grep) | ✅ |

> All checks **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this
> round. The `(c)`-clean grep (no `cut -c1-60`) confirms the headline nuance: truncation is jq-internal,
> not a dropped feature (§4.1).

---

## 3. Test results (the contract's run command, LIVE)

```
$ timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q
....<paste the live summary line, e.g. "5 passed in 0.03s">....
```

The suite (109 lines, 5 tests) is pure-stdlib `subprocess`/`os`/`pathlib`: it runs the REAL
`voice_typing/status.sh` under a controlled `XDG_RUNTIME_DIR` (full env carried so `jq`/`id`/`sh` stay
on PATH) with a synthesized `state.json` — no GPU/CUDA/daemon/mic. Coverage by check: (e) missing-file
(`:<L51>`) + corrupt-JSON (`:<L61>`) exit-0 regressions; (b) listening-render (`:<L71>`) + idle-empty
(`:<L102>`); (d) lite-bolt + normal-negative (`:<L87>`); (a) path resolution exercised transitively by
all 5. **No test for check (c)** (the 60-codepoint truncation bound / `…` marker) — §4.2.

---

## 4. Non-defect nuances (so they are not mistaken for gaps)

### 4.1 (c) Truncation is jq-INTERNAL (codepoint slice + `…`), NOT `cut -c1-60` — compliant-by-design
PRD §4.6's *inline* snippet truncates with `| cut -c1-60`. `status.sh` does NOT — it truncates INSIDE jq:
`MAX="${VOICE_TYPING_STATUS_MAX:-60}"` (`:<L37>`); `if ($line | length) > ($max | tonumber) then
$line[:($max - 1)] + "…" else $line end` (`:<L42>-<L44>`). **Why this is compliant, not a gap:**

1. **PRD §4.6 explicitly redirects to the helper:** the SAME sentence says *"Provide a small
   `voice_typing/status.sh` helper script instead of inline jq, and reference that — cleaner quoting."*
   The inline `cut -c1-60` snippet is the ALTERNATIVE the PRD steers the implementer AWAY from.
2. **The functional intent is preserved AND improved on three axes:**
   - **Codepoint-accurate:** jq string slicing is codepoint-based, so a 4-byte emoji (🎤/⚡/…) counts as
     1; `cut -c1-60` is locale/byte-dependent and can split a multibyte glyph mid-sequence.
   - **Visible truncation:** `$line[:($max - 1)] + "…"` drops the last char and appends `…`, so a cut
     line is visibly cut, not silently chopped.
   - **Override hook:** `VOICE_TYPING_STATUS_MAX` lets the user widen it (`tmux set-environment
     VOICE_TYPING_STATUS_MAX 80`) without editing the script.
3. **No literal "60" is lost:** the DEFAULT is still 60 (`:-60`), matching the PRD's `c1-60`.

> **Do NOT "restore" `cut -c1-60`.** That would regress the codepoint-accuracy + ellipsis + override
> improvements. ✅

### 4.2 (c) No test pins the 60-codepoint truncation bound — a coverage gap, not a code gap
The 5-test suite pins (a) transitively, (b), (d), (e) — but NO test feeds a >60-char partial and asserts
the output is ≤60 codepoints + ends in `…` (check c). This is a **non-blocking coverage observation**,
not a §4.6 violation: the truncation logic exists (`:<L42>-<L44>`) and is correct-by-inspection; the
happy-path tests prove the render pipeline works. A future test-hardening pass COULD add a truncation
test (out of scope for this read-only audit — do NOT add one here; consistent with every round-006
audit's "read-only, no new tests" discipline). ✅

### 4.3 (a) The `XDG_RUNTIME_DIR:-/run/user/$(id -u)` resolution is a TESTED SUPERSET — compliant
PRD §4.6 names the path `$XDG_RUNTIME_DIR/voice-typing/state.json`. `status.sh` uses
`${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json` (`:<L30>`): it resolves to
`$XDG_RUNTIME_DIR` when set (the PRD path) AND falls back to `/run/user/$(id -u)` (the conventional XDG
default) when unset. This is **strictly more robust** than the bare `$XDG_RUNTIME_DIR` — a host where
XDG_RUNTIME_DIR is somehow unset (rare but possible) still resolves correctly. Intentionally more robust
than the contract's literal wording; exercised transitively by all 5 tests (`_run_status` sets
`XDG_RUNTIME_DIR`→`tmp_path`). Mirrors the "compliant-by-design superset" framing in `gap_typing.md`
§4.1 (the `(CalledProcessError, OSError)` fallback superset). ✅

---

## 5. Conclusion

**PASS.** `voice_typing/status.sh` is compliant with PRD §4.6 / §4.2ter on all 5 item checks (a)-(e) +
Mode A self-doc + Mode B README/install.sh references. The helper resolves the state.json path with a
robust XDG fallback (`:<L30>`), renders `🎤 <partial>` while listening and `` when idle (`:<L38>-<L44>`),
prefixes `⚡` in lite mode (`:<L40>`), truncates long lines to 60 codepoints with a visible `…` marker
INSIDE jq (an improvement on the PRD's inline `cut -c1-60`, explicitly authorized by §4.6's "cleaner
quoting" directive — `:<L37>`/`:<L42>-<L44>`), and survives a missing/corrupt state.json with empty
stdout + exit 0 (`2>/dev/null` `:<L45>` + `exit 0` `:<L50>`, the Issue 2 fix). README (`:<L135>-<L150>`)
+ install.sh (`:<L212>-<L214>`) both reference `status.sh` (not inline jq). The 5-test suite pins every
check except the truncation bound (a coverage gap, §4.2). **No source files were modified** (read-only
audit); the sole artifact is this report.

Scope is the `status.sh` tmux helper only — the state.json schema/atomic writes are P1.M3.T1.S1
(`gap_feedback.md`, COMPLETE), `voicectl` is P1.M3.T2.S2 (`gap_voicectl.md`), the daemon control socket
is P1.M3.T2.S1 (`gap_socket.md`, COMPLETE), and a full README/install.sh audit is P1.M6.T1.S1 /
P1.M4.T3.S1.
````

> NOTE for the implementer: replace every `<L...>` placeholder with the ACTUAL line number from your
> Task-1 greps, and paste the LIVE pytest summary line into §3. The body above is the verified-compliant
> verdict pre-filled from research — re-confirm each file:line + the pass count live (Critical #2, #4).
> The `(c)`-clean grep result (no `cut -c1-60`) is the headline evidence — record its "CLEAN" output in §1.

### Implementation Patterns & Key Details

```sh
# PATTERN 1 — the audit is READ-ONLY. The ONLY file created is gap_status_sh.md. status.sh/
#   test_status_sh.py/README.md/install.sh are compliant + untouched. If a check fails on re-read,
#   document it as a gap for a SEPARATE remediation task (do NOT fix status.sh here). (Critical #1.)

# PATTERN 2 — re-verify line numbers live (grep -n), then paste them into the report's <L...> slots.
#   Do NOT copy the PRP's numbers blindly — the file may have shifted. (Critical #2.)

# PATTERN 3 — THE HEADLINE NUANCE: there is NO `cut -c1-60` in status.sh. Run
#   `grep -nE 'cut -c1-60' voice_typing/status.sh` — it returns NOTHING. That is the EVIDENCE for §4.1
#   (truncation is jq-internal + codepoint-accurate + ellipsis + override — an improvement the PRD's
#   own directive authorizes). Do NOT flag the absent `cut` as a dropped feature. (Critical #3.)

# PATTERN 4 — run the suite live + paste the actual count into §3. Do NOT hard-code a number. (Critical #4.)
#   TWO TIMEOUTS: `timeout 120 .venv/bin/python -m pytest ...` (inner) + bash-tool timeout param (outer).

# PATTERN 5 — check (c) has NO pinning test; cite it as nuance §4.2 (coverage gap, not code gap). Do NOT
#   invent a truncation test and do NOT add one. (Critical #5.)

# PATTERN 6 — frame the 3 nuances precisely (§4): jq-internal truncation is compliant-by-design (§4.1);
#   the absent truncation test is a non-blocking coverage gap (§4.2); the XDG fallback is a robust
#   superset (§4.3). (Critical #3/#5, Gotcha #7.)
```

### Integration Points

```yaml
REPORT FILE:
  - create: "plan/006_862ee9d6ef41/architecture/gap_status_sh.md (NEW — mirror gap_typing.md's structure)"
CONSUMED (read-only — NO edits):
  - voice_typing/status.sh: "STATE path / jq render / 2>/dev/null / exit 0 / MAX / header (the 5 checks + Mode A)"
  - tests/test_status_sh.py: "cite the pinning test per check; the contract's run command"
  - README.md: "§'tmux status line' (Mode B reference)"
  - install.sh: "the status.sh snippet print (Mode B reference)"
DISJOINT FROM SIBLINGS:
  - P1.M3.T1.S1: "gap_feedback.md (state.json schema/atomic writes) — COMPLETE; status.sh only CONSUMES state.json"
  - P1.M3.T2.S1: "gap_socket.md (daemon control socket) — COMPLETE; different file"
  - P1.M3.T2.S2: "gap_voicectl.md (ctl.py CLI) — in flight, parallel; different file"
  - P1.M6.T1.S1 / P1.M4.T3.S1: "full README / install.sh audit — this task only CONFIRMS status.sh is referenced"
DEPENDENCIES: none new (read-only audit + the existing pytest suite + grep).
```

## Validation Loop

> This is a READ-ONLY AUDIT. The gate is: the report exists with ✅ verdicts + live file:line evidence +
> the live pytest count + the `(c)`-clean grep evidence, and NO source file is modified. No GPU/CUDA/
> daemon/mic (the suite runs the REAL script with a synthesized state.json under a controlled
> XDG_RUNTIME_DIR).

### Level 1: Report exists + structure sanity

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_status_sh.md && echo "L1 report present" || echo "L1 FAIL: report missing"
# Structure mirrors gap_typing.md:
head -1 plan/006_862ee9d6ef41/architecture/gap_status_sh.md | grep -q '^# Gap Report — P1.M3.T2.S3: status.sh' && echo "L1 title ok" || echo "L1 FAIL: title"
grep -q '^## 2\. Per-check Compliance Table' plan/006_862ee9d6ef41/architecture/gap_status_sh.md && echo "L1 §2 ok" || echo "L1 FAIL: §2 table"
grep -q '^## 3\. Test results' plan/006_862ee9d6ef41/architecture/gap_status_sh.md && echo "L1 §3 ok" || echo "L1 FAIL: §3"
grep -q '^## 4\. Non-defect nuances' plan/006_862ee9d6ef41/architecture/gap_status_sh.md && echo "L1 §4 ok" || echo "L1 FAIL: §4"
# No leftover <L...> placeholders (all replaced with live line numbers):
! grep -q '<L[0-9]' plan/006_862ee9d6ef41/architecture/gap_status_sh.md && echo "L1 placeholders resolved" || echo "L1 FAIL: leftover <L...> placeholder"
# Expected: report present; title/§2/§3/§4 headings present; NO <L...> placeholders remain.
```

### Level 2: The contract's run command (re-run live; count recorded in §3) — TWO TIMEOUTS

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q | tee /tmp/status_sh_audit_run.log
echo "exit: ${PIPESTATUS[0]}"
# Expected: exit 0; "N passed in Xs". Confirm the report's §3 pasted THIS run's summary line:
COUNT=$(grep -oE '[0-9]+ passed' /tmp/status_sh_audit_run.log | head -1)
grep -q "$COUNT passed" plan/006_862ee9d6ef41/architecture/gap_status_sh.md && echo "L2 count recorded" || echo "L2 FAIL: live count not in §3"
# jq must be installed (the script + the test depend on it):
command -v jq >/dev/null && echo "L2 jq present" || echo "L2 FAIL: jq not on PATH (suite would have failed)"
# (NOTE: do NOT leave /tmp/status_sh_audit_run.log behind unbounded — it is a one-shot tee of a <1KB
#  summary; remove it after the check: rm -f /tmp/status_sh_audit_run.log)
rm -f /tmp/status_sh_audit_run.log
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected: ONLY "?? plan/006_862ee9d6ef41/architecture/gap_status_sh.md" (new untracked file). Any change
#   to voice_typing/status.sh, tests/test_status_sh.py, README.md, install.sh, PRD.md, tasks.json,
#   prd_snapshot.md, .gitignore, or any source is a SCOPE VIOLATION (read-only audit).
git diff --name-only   # Expected: empty (the report is a NEW untracked file, not a modification)
! git status --porcelain | grep -qE 'voice_typing/|tests/|README\.md|install\.sh|PRD\.md|tasks.json|prd_snapshot.md' && echo "L3 ok: no source/test/doc modified" || echo "L3 FAIL: source/test/doc modified"
# Confirm the report is disjoint from its siblings (different filenames, no overlap):
for f in gap_feedback gap_socket gap_voicectl gap_status_sh; do test -f plan/006_862ee9d6ef41/architecture/$f.md && echo "L3 ok: $f.md coexists (disjoint)" || echo "L3 note: $f.md not present"; done
```

### Level 4: Evidence spot-check (the checks are real, not hand-waved)

```bash
cd /home/dustin/projects/voice-typing
# Each check's file:line cited in the report must actually exist + contain the claimed code:
grep -nE 'STATE="\$\{XDG_RUNTIME_DIR' voice_typing/status.sh                                 # (a) path
grep -nE 'if \(\.listening // false\)' voice_typing/status.sh                                # (b) gate
grep -nE 'if \(\.mode == "lite"\) then "⚡"' voice_typing/status.sh                           # (d) lite prefix
grep -nE '2>/dev/null' voice_typing/status.sh && grep -nE '^exit 0' voice_typing/status.sh    # (e) graceful
# (c) the headline nuance — NO cut -c1-60 (truncation is jq-internal, §4.1):
if grep -qE 'cut -c1-60' voice_typing/status.sh; then echo "L4 UNEXPECTED: cut -c1-60 present (report §4.1 framing needs revisiting)"; else echo "L4 ok: no cut -c1-60 (truncation is jq-internal)"; fi
grep -nE 'VOICE_TYPING_STATUS_MAX|then \$line\[:' voice_typing/status.sh                      # (c) jq truncation
grep -nE 'status\.sh' README.md install.sh                                                    # Mode B references
# Expected: each grep hits the line the report cites (re-verify the numbers match the report's <L...> → live values).
```

## Final Validation Checklist

### Technical Validation
- [ ] `plan/006_862ee9d6ef41/architecture/gap_status_sh.md` exists with the correct title + §1-§5 structure mirroring `gap_typing.md`.
- [ ] No `<L...>` placeholders remain (all replaced with live `grep -n` line numbers).
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_status_sh.py -q` → exit 0; the live pass count is pasted into §3.
- [ ] L3 scope guard: ONLY `gap_status_sh.md` created (new untracked); NO source/test/doc modified.
- [ ] L4: each check's cited file:line exists + contains the claimed code; the `(c)`-clean grep (no `cut -c1-60`) is recorded.

### Feature Validation
- [ ] **(a)** `STATE` resolves `$XDG_RUNTIME_DIR/voice-typing/state.json` (with a robust `/run/user/$(id -u)` fallback).
- [ ] **(b)** the jq program renders `🎤 <partial>` when listening + `` (empty) when not (null-safe `.listening // false` + `.partial // ""`).
- [ ] **(c)** long lines truncate to `MAX` (default 60) codepoints + `…` — INSIDE jq (no `cut -c1-60`); documented as compliant-by-design (§4.1).
- [ ] **(d)** lite mode (`mode=="lite"`) prefixes the line with `⚡` (else no bolt).
- [ ] **(e)** a missing/corrupt state.json yields empty stdout + exit 0 (`2>/dev/null` + the trailing `exit 0`).
- [ ] **Mode A** the header comment block (`# USER INTEGRATION #`) documents the 2-line `tmux.conf` snippet + the `MAX` override.
- [ ] **Mode B** README §"tmux status line" + install.sh both reference `status.sh` (not inline jq).

### Code Quality Validation
- [ ] The report mirrors `gap_typing.md`'s structure (title/Date/Scope/Audited artifacts/Bottom line/§1-§5).
- [ ] Every check row has a real `status.sh`/`README.md`/`install.sh` file:line + a `tests/test_status_sh.py` pinning test (except (c), cited as a coverage gap §4.2, and the Mode A/B doc rows, corroborated by reading).
- [ ] The 3 nuances are documented precisely (jq-internal truncation §4.1; absent truncation test §4.2; XDG-fallback superset §4.3).
- [ ] No claim that overstates coverage (e.g. do NOT claim a truncation test exists for (c)).

### Documentation & Deployment
- [ ] The report is self-contained (a reviewer needs only it + the repo to confirm the verdict).
- [ ] Scope boundaries explicit (status.sh only; state.json schema = P1.M3.T1.S1; voicectl = S2; daemon socket = S1; full README/install.sh = P1.M6.T1.S1/P1.M4.T3.S1).
- [ ] No new env vars, no config keys, no user-facing surface (read-only audit; PRD §4.6 evidence).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/status.sh`, `tests/test_status_sh.py`, `README.md`, `install.sh`, `PRD.md`, or any source — this is a read-only audit; status.sh is compliant. If a check fails, document it as a gap for a separate remediation task (Critical #1).
- ❌ Don't copy the PRP's line numbers blindly — re-grep (`grep -n`) live and paste the ACTUAL numbers into the report's `<L...>` slots (Critical #2).
- ❌ Don't flag the absent `cut -c1-60` as a dropped feature — truncation is jq-internal (codepoint slice + `…` + override), an improvement the PRD §4.6 "cleaner quoting" directive authorizes. Record it as nuance §4.1 (Critical #3).
- ❌ Don't hard-code the pytest count — run it live + paste the actual summary line into §3 (Critical #4).
- ❌ Don't claim a truncation test exists for check (c) — none does; cite it as a non-blocking coverage gap (§4.2), and do NOT add one (Critical #5).
- ❌ Don't audit the state.json schema/atomic writes (P1.M3.T1.S1 → `gap_feedback.md`), voicectl (S2 → `gap_voicectl.md`), the daemon socket (S1 → `gap_socket.md`), or a full README/install.sh audit (P1.M6.T1.S1 / P1.M4.T3.S1). S3 is the `status.sh` helper only (Critical #6).
- ❌ Don't narrow the `XDG_RUNTIME_DIR:-/run/user/$(id -u)` resolution to the bare `$XDG_RUNTIME_DIR` — the fallback is a robust superset (§4.3, Gotcha #7).
- ❌ Don't introduce a `shellcheck`/`ruff`/`mypy` gate — status.sh is a POSIX shell script; those tools don't apply / aren't in the project gate (Gotcha #10).
- ❌ Don't append to an existing file or create `tests/__init__.py` — CREATE `gap_status_sh.md` fresh; it's the only new file (Gotcha #11).
- ❌ Don't run bare `python`/`pytest` (zsh aliases) or skip the inner `timeout` — use `.venv/bin/python -m pytest` wrapped in `timeout 120`, with the bash-tool `timeout` param above it (Gotcha #10, #12, AGENTS.md Rule 1).

---

## Confidence Score

**9/10** for one-pass success. This is a read-only audit of a 50-line POSIX `sh` + `jq` script that is
already compliant (verified by reading every line + the full 109-line/5-test suite + the README +
install.sh references). The deliverable is a Markdown report mirroring an existing template
(`gap_typing.md`), with the verdict + file:line evidence + pinning tests pre-filled in the Task-3 SOURCE
body; the implementer only re-verifies the line numbers live + pastes the live pytest count + runs the
`(c)`-clean grep. The 5 checks (a)-(e) + Mode A/B are all straightforward (a path assignment, a jq
render program, a truncation if/else, a lite-prefix branch, a `2>/dev/null` + `exit 0`, and two doc
references) and the suite is already green. The scope is cleanly disjoint from S1 (daemon socket),
S2 (voicectl), and P1.M3.T1.S1 (feedback.py / state.json schema).

The −1 reserves: (a) the exact live pytest count must be recorded (not hard-coded) — if a test was
added/removed since research, the count differs but the audit logic is unchanged; the implementer
pastes whatever the live run prints. (b) The line numbers must be re-located live (the files may have
shifted a line or two); the `<L...>` placeholders make this explicit and the L1/L4 gates catch any
leftover. (c) The headline nuance (no `cut -c1-60`) must be framed as compliant-by-design, not a gap —
the Task-3 SOURCE body + §4.1 pre-write this framing, and the L4 grep gate confirms the "CLEAN" output.
All three are mechanical, gate-checked steps, not judgment calls.