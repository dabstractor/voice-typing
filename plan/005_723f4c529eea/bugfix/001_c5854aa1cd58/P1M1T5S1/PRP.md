# PRP — P1.M1.T5.S1: Verify README.md + overview docs are consistent with the corrected lite-mode surfaces

## Goal

**Feature Goal**: Run the **changeset-level documentation consistency sweep** (Mode B) across the
overview docs that span the whole lite-mode delta — `README.md` and `tests/ACCEPTANCE.md` — and
confirm they agree with the **now-corrected** lite-mode surfaces produced by P1.M1.T1.S1–P1.M1.T4.S1
(install.sh, config.toml, ctl.py, daemon.py). The sweep tests three drift criteria, derived from the
item contract: **(a)** the keybind letter is **D** (not F) everywhere; **(b)** all **7** commands are
listed/mentioned wherever a command list appears (lite commands `toggle-lite`/`start-lite` not
omitted); **(c)** keybind→command mappings match `hypr-binds.conf` (`Ctrl+Alt+Super+D`=toggle/normal,
`Alt+Super+D`=toggle-lite/lite). If a gap is found, fix it in-place; if (as expected) none is found,
document the verification with the grep evidence — no code changes.

**Deliverable** (expected: **0 files edited**; the work product IS the verification record):
1. A reproduced, deterministic grep sweep (the Validation Loop L1–L3 commands below) over
   `README.md` and `tests/ACCEPTANCE.md` proving each of the three criteria (a/b/c) holds.
2. A one-line consistency verdict reported by the implementing agent (completion message):
   `README.md + tests/ACCEPTANCE.md CONFIRMED consistent with the corrected lite-mode surfaces (0 gaps; 0 edits).`
3. IF (unexpected) a real gap is found: an in-place text fix to the offending doc line, with the
   exact old→new edit recorded, scoped ONLY to that line.

**Success Definition**:
- (a) `grep` for wrong-F keybind references in `README.md` and `tests/ACCEPTANCE.md` finds nothing
  (criterion **a** holds), AND the documented keybind is `D` (matching `hypr-binds.conf`).
- (b) No command-list enumeration in either doc wrongly omits `toggle-lite`/`start-lite`. README has
  no 5-of-7 pipe-delimited usage line (it documents commands contextually, all 7 present).
  ACCEPTANCE.md criterion 6's 5-command list is a **verbatim quote of PRD §7 #6** (`PRD.md:371`) —
  lite is covered by the dedicated criterion 10 — so it is CORRECT and must NOT be "fixed" to 7.
- (c) The keybind→command mappings in README (the verbatim `bind =` block + prose) exactly match
  `hypr-binds.conf:42,44` (`CTRL SUPER ALT, D`→toggle, `SUPER ALT, D`→toggle-lite).
- The verification is reproducible: every claim above is backed by a `grep` command in the
  Validation Loop that returns the expected result on the live tree.
- `git diff --name-only` is EMPTY (or, only an unexpected in-place doc fix, scoped to one line).

> **VERIFIED OUTCOME (this PRP's research):** both target docs are ALREADY correct. The live-tree
> greps (research §2/§3) confirm: README has zero wrong-F references, all keybind mentions use D,
> its bind block matches hypr-binds.conf, and it has no 5-of-7 command enumeration; ACCEPTANCE.md
> has zero wrong-F references, states no keybind letters (criterion (a)/(c) vacuous), and its
> criterion 6 is a faithful PRD §7 #6 quote (criterion 10 covers lite). The implementing agent
> REPRODUCES this verification and reports the verdict — it does not invent edits.

## User Persona

**Target User**: the end user / contributor reading `README.md` (the canonical install/hotkey/config
doc) or `tests/ACCEPTANCE.md` (the PRD §7 done-criteria evidence) to learn the lite-mode keybinds
and command set.
**Use Case**: after the T1–T4 doc fixes land, a reader opens README to find the lite hotkey
(`Alt+Super+D`) and the lite commands (`toggle-lite`/`start-lite`), and opens ACCEPTANCE.md to see
the lite-mode acceptance evidence — and finds both correct and consistent with the corrected CLI
help, config comment, and keybind source file.
**Pain Points Addressed**: the PRD Overview found that lite-mode doc surfaces contradicted each other
and the PRD on the keybind letter (F vs D) and the command set (5 vs 7). T1–T4 fixed the source/help
surfaces; T5.S1 is the closing sweep that confirms the OVERVIEW docs (README + ACCEPTANCE) already
agree — so no remaining surface misleads a user about how to discover/invoke lite mode.

## Why

- **Closing the changeset's doc delta.** T1.S1 (install.sh), T2.S1 (config.toml), T3.S1 (ctl.py),
  T4.S1 (daemon.py) corrected the four source/help/docstring surfaces. T5.S1 (Mode B) sweeps the two
  OVERVIEW docs that span the whole feature — README (the canonical user-facing doc) and ACCEPTANCE
  (the done-criteria record) — to ensure the corrected surfaces didn't leave a stale reference behind
  in the docs a user is most likely to read. (PRD §2.0 Overview; item DOCS: "[Mode B] This IS the
  changeset-level documentation sync task.")
- **README is the first doc a user reads.** PRD §7 criterion 7 requires "README documents install /
  hotkey / tmux / config / troubleshooting / CPU-only mode." A stale keybind letter (F) or an omitted
  lite command in README would send a user to a dead key (F is bound to nothing) or hide lite mode
  entirely — exactly the class of defect T1–T4 remediated elsewhere.
- **Why it slipped past tests (and why this sweep matters).** Per the PRD Testing Summary: "Comments/
  help strings are not covered by the config drift-guard or any test" — and neither are README/ACCEPTANCE
  prose strings. The drift-guard only checks parsed config VALUES. So doc prose can drift silently;
  this task is the human+grep check that catches it for the overview surfaces. (system_context.md
  "Testing Patterns"; PRD §2.4.)
- **Scope discipline.** T5.S1 owns ONLY README.md + tests/ACCEPTANCE.md (read/verify, edit ONLY if a
  real gap is found). It does NOT touch the T1–T4 files (already corrected), `hypr-binds.conf`
  (correct, the source of truth), `PRD.md`/`tasks.json`/`prd_snapshot.md` (read-only), or any source
  code. Pure Mode-B doc verification.

## What

Run the 3-criteria grep sweep (Validation Loop L1–L3) over `README.md` and `tests/ACCEPTANCE.md`,
compare each reference against the corrected surfaces (§"All Needed Context" → Documentation &
References) and `hypr-binds.conf` (the keybind source of truth), capture the evidence, and report the
verdict. No code, no tests, no config change. An in-place doc fix is performed ONLY if a real gap is
found (none expected).

### Success Criteria

- [ ] Criterion **(a)** — keybind letter is D (not F): `grep -niE "..." README.md tests/ACCEPTANCE.md` finds zero wrong-F references; all documented keybinds use D.
- [ ] Criterion **(b)** — all 7 commands where a list appears: README has no 5-of-7 pipe-delimited command enumeration (it documents commands contextually; all 7 appear); ACCEPTANCE criterion 6 = verbatim PRD §7 #6 quote (lite in criterion 10) — NOT changed.
- [ ] Criterion **(c)** — keybind→command mappings match hypr-binds.conf: README's `bind =` block (L99-100) and prose (L81/103/104/125/171) match `hypr-binds.conf:42,44` exactly.
- [ ] Verdict reported: "README.md + tests/ACCEPTANCE.md CONFIRMED consistent (0 gaps; 0 edits)."
- [ ] `git diff --name-only` is EMPTY (or only a single-line unexpected doc fix, if a real gap was found).

## All Needed Context

### Context Completeness Check

_Pass._ The task is a deterministic doc-consistency sweep. The three drift criteria are concretely
defined (a/b/c), the two target files are named (`README.md`, `tests/ACCEPTANCE.md`), the CONTRACT
INPUTS (the corrected surfaces, with exact file:line + verified content) are enumerated in the
"corrected surfaces" table below, the source of truth for keybinds (`hypr-binds.conf:42,44`) and
command set (`ctl.py:37 _COMMANDS`) are cited, the exact grep commands that PROVE each criterion are
given in the Validation Loop (reproducible on the live tree), and the EXPECTED outcome (zero edits —
both docs already correct, proven in research §2/§3) plus the two implementation hazards
(MISREADING criterion 6 as a gap; speculative edits) are captured in the Gotchas. An agent new to
this repo can run the verification from this PRP alone.

### Documentation & References

```yaml
# MUST READ — this task's verification research (the evidence the agent reproduces)
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/P1M1T5S1/research/readme_acceptance_consistency_sweep.md
  why: "§1 = the CONTRACT INPUTS table (the 4 corrected surfaces, exact file:line + verified content,
        so the agent knows what the docs must agree WITH). §2 = README verification per criterion
        (a/b/c) with the exact greps + expected output (README ALREADY CORRECT). §3 = ACCEPTANCE
        verification, INCLUDING the load-bearing §3(b) finding that criterion 6's 5-command list is
        a verbatim PRD §7 #6 quote (PRD.md:371) and lite is covered by criterion 10 — so it is NOT a
        gap. §4 = conclusion (both correct; deliverable = verification record). §5 = parallel
        no-conflict with T4.S1."
  critical: "§3(b) is the #1 hazard guard: the agent MUST NOT 'fix' ACCEPTANCE criterion 6 to 7
            commands — it is a faithful PRD quote, and changing it DIVERGES FROM THE PRD. §1 (the
            corrected-surfaces table) is the comparison anchor for criteria (a)/(b)/(c)."

# THE TARGET FILE #1 — README.md (verify; do NOT edit unless a real gap is found)
- file: README.md
  why: "The canonical user-facing doc (install/hotkey/config/lifecycle/troubleshooting/CPU-only).
        L81 = 'Bind **Ctrl+Alt+Super+D** ... normal ... **Alt+Super+D** for **lite mode**' (correct
        D + mapping). L99-100 = verbatim bind block EXACTLY matching hypr-binds.conf:42,44. L103-104
        = mode→keybind prose (correct). L125-126 = 'toggle-lite / start-lite ... **Alt+Super+D**
        keybind' (correct). L171 = config table 'lite_model ... toggle-lite / Alt+Super+D' (correct).
        system_context.md:51 confirms: '## README Status (ALREADY CORRECT — no changes needed)'."
  pattern: "Sweep, do not edit. README documents commands CONTEXTUALLY (no pipe-delimited usage
            line) — so criterion (b) 'all 7 where a list appears' has no 5-of-7 enumeration to flag.
            The install.sh header comment (install.sh:21-22) says README 'copies the usage/tmux/hypr
            snippets verbatim' — this is a RED HERRING: README has INDEPENDENT correct content for
            the hotkey/usage prose (it does NOT reproduce install.sh's old usage line), so the T1.S1
            install.sh fix does NOT force a README change. (research §2; system_context.md:57-59.)"
  gotcha: "Do NOT edit README unless a grep in the Validation Loop surfaces a real contradiction. The
           research confirms all 4 reference points (L81, L99-100, L125, L171) are already correct."

# THE TARGET FILE #2 — tests/ACCEPTANCE.md (verify; do NOT edit unless a real gap is found)
- file: tests/ACCEPTANCE.md
  why: "The PRD §7 done-criteria evidence record (criteria 1-10). Criterion 10 = the lite-mode
        acceptance criterion (correctly documents toggle-lite arms lite, toggle arms normal, mode
        reporting, lite silence gate). Criterion 6 = 'voicectl toggle/start/stop/status/quit all
        work; ... systemd user service; starts un-armed; auto-restarts on failure' — a VERBATIM quote
        of PRD §7 #6. ACCEPTANCE states NO keybind LETTERS (no Super+/Alt+/Ctrl+ strings), so
        criteria (a) and (c) are vacuously satisfied for this file."
  pattern: "Sweep, do not edit. The PRD deliberately splits acceptance: criterion 6 tests the 5 BASE
            commands + systemd integration + boot state; criterion 10 (§4.2ter) tests lite mode. Both
            are correct as-is."
  critical: "DO NOT change criterion 6's 'toggle/start/stop/status/quit' to 7 commands. It is a
            verbatim quote of PRD.md:371. Changing it would DIVERGE FROM THE PRD. (research §3(b);
            Gotcha #1.)"

# THE KEYBIND SOURCE OF TRUTH — hypr-binds.conf (read-only comparison anchor)
- file: hypr-binds.conf
  why: ":42 = 'bind = CTRL SUPER ALT, D, ... toggle' (NORMAL); :44 = 'bind = SUPER ALT, D, ...
        toggle-lite' (LITE). BOTH use key D, never F. This is the authoritative keybind source
        (system_context.md 'Canonical Keybinds'). README's bind block (L99-100) must match it
        exactly — and does."
  pattern: "Use as the proof anchor for criterion (c). Do NOT edit (it is correct)."

# THE COMMAND-SET SOURCE OF TRUTH — ctl.py (read-only comparison anchor)
- file: voice_typing/ctl.py
  why: ":37 _COMMANDS = (toggle, start, stop, status, quit, toggle-lite, start-lite) — 7 commands,
        the canonical CLI set (PRD §4.8). Use as the proof anchor for criterion (b). Do NOT edit
        (T3.S1 owns it; already corrected)."

# THE CONTRACT INPUTS — the corrected surfaces (what the docs must agree WITH; read-only for T5)
- file: install.sh
  why: ":178 usage line = 'toggle|start|stop|status|quit|toggle-lite|start-lite' (7 cmds); :179 bind
        hint = 'Ctrl+Alt+Super+D -> voicectl toggle; Alt+Super+D -> voicectl toggle-lite'. T1.S1
        corrected these. README does NOT copy this line verbatim (independent content), so no README
        edit follows."
- file: config.toml
  why: ":34 lite_model comment = 'SUPER+ALT+D' (T2.S1 corrected F→D). README's config table (L171)
        independently says 'Alt+Super+D' — already correct."
- file: voice_typing/daemon.py
  why: ":1410-1411 toggle_lite docstring = 'pressing D' ×3 (T4.S1 corrects F→D). README/ACCEPTANCE do
        not reference this docstring, so no edit follows."

# THE MANDATE — PRD §7 (criterion 6 wording) + §4.8/§4.10 (the lite spec)
- docfile: PRD.md
  why: ":371 §7 criterion 6 verbatim = 'voicectl toggle/start/stop/status/quit all work; ... systemd
        user service; starts un-armed; un-loaded; auto-restarts on failure.' — the proof that
        ACCEPTANCE criterion 6 is a faithful quote (NOT drift). :286 §4.8 = the canonical 7-command
        CLI list. §4.10 = the keybinds (Ctrl+Alt+Super+D=toggle, Alt+Super+D=toggle-lite)."
  critical: ":371 is the load-bearing citation for why ACCEPTANCE criterion 6 must NOT be changed to
            7 commands. Read it before touching ACCEPTANCE."
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md
  why: "The bugfix PRD: §4.8 (7 commands), §4.10 (keybinds), Issues 1-4 (the corrected defects), and
        the Overview's finding that README/ACCEPTANCE were already correct for the silence gate
        (§2.0). Confirms the doc-defect scope is T1-T4 source surfaces, NOT README/ACCEPTANCE."
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/architecture/system_context.md
  why: "'Canonical Keybinds' + 'Canonical Command Set' (the source-of-truth tables) + 'README Status
        (ALREADY CORRECT — no changes needed)' (L51-59) — the authoritative statement that README is
        already correct and the install.sh header comment is a red herring."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── README.md                 # TARGET #1 (verify; edit ONLY if a real gap found). 380 lines. ALREADY CORRECT.
├── tests/
│   └── ACCEPTANCE.md         # TARGET #2 (verify; edit ONLY if a real gap found). ALREADY CORRECT.
├── hypr-binds.conf           # comparison anchor (keybind source of truth; :42,44). READ-ONLY.
├── voice_typing/ctl.py       # comparison anchor (_COMMANDS @37 = 7 cmds). T3.S1-corrected. READ-ONLY for T5.
├── install.sh                # CONTRACT INPUT (T1.S1-corrected usage @178 + bind hint @179). READ-ONLY for T5.
├── config.toml               # CONTRACT INPUT (T2.S1-corrected lite_model comment @34 = SUPER+ALT+D). READ-ONLY.
└── voice_typing/daemon.py    # CONTRACT INPUT (T4.S1-corrects toggle_lite docstring @1410-1411 F→D). READ-ONLY.
# NOTE: this task VERIFIES docs. Expected outcome: 0 edits. T4.S1 (parallel) edits daemon.py + test_daemon.py — DISJOINT.
```

### Desired Codebase tree with files to be changed

```bash
# EXPECTED (research confirms both docs already correct):
README.md                     # UNCHANGED (verified consistent).
tests/ACCEPTANCE.md           # UNCHANGED (verified consistent).
# No new files. No config/code/test changes.
#
# ONLY IF a real gap is found (none expected): a single-line in-place text edit to README.md OR
# tests/ACCEPTANCE.md, scoped to the offending reference. Then `git diff --name-only` lists exactly
# that one file.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT "FIX" ACCEPTANCE.md CRITERION 6 TO 7 COMMANDS. Its 'toggle/start/stop/status/
# quit' (5 commands) is a VERBATIM QUOTE of PRD §7 criterion 6 (PRD.md:371). The PRD deliberately
# splits acceptance: criterion 6 = 5 BASE commands + systemd/boot/restart; criterion 10 (§4.2ter) =
# lite mode (toggle-lite, mode reporting, lite silence gate). Both are correct. Changing criterion 6
# to 7 DIVERGES FROM THE PRD. (research §3(b).) This is the #1 hazard — verify PRD.md:371 BEFORE
# touching ACCEPTANCE, and only edit if a grep finds a DIFFERENT, real contradiction.

# CRITICAL #2 — DO NOT MAKE SPECULATIVE EDITS. The expected outcome is ZERO edits. Both README and
# ACCEPTANCE are already correct (research §2/§3; system_context.md:51). Only edit if a grep in the
# Validation Loop surfaces a real contradiction with the corrected surfaces or hypr-binds.conf.
# "Editing to be thorough" when no gap exists is a scope violation. The deliverable IS the
# verification record, not a diff.

# GOTCHA #3 — THE install.sh HEADER COMMENT IS A RED HERRING. install.sh:21-22 says README 'copies
# the usage/tmux/hypr snippets verbatim — keep them stable.' This is TRUE for the tmux + hypr SOURCE
# lines, but FALSE for the usage/bind-hint line: README has INDEPENDENT correct hotkey/usage prose
# (L81/L99-100/L125/L171), it does NOT reproduce install.sh's old usage line. So the T1.S1 install.sh
# fix does NOT force a README change. Do not 'correct' README to match install.sh's usage line.
# (research §2; system_context.md:57-59.)

# GOTCHA #4 — README HAS NO PIPE-DELIMITED COMMAND LIST. README documents commands CONTEXTUALLY
# (prose + code blocks), not as 'toggle|start|stop|status|quit'. So criterion (b) 'all 7 where a list
# appears' has no 5-of-7 enumeration to flag in README. Confirmed: no 'toggle|start|stop|status|quit'
# string in README. (research §2(b).) Do not add a command list to README — that is out of scope.

# GOTCHA #5 — ACCEPTANCE.md STATES NO KEYBIND LETTERS. It references commands (toggle-lite, toggle)
# and modes (mode: lite), not the hotkey letters (no Super+/Alt+/Ctrl+ strings). So criteria (a) and
# (c) are VACUOUSLY satisfied for ACCEPTANCE — there is nothing to drift. Do not add keybind letters
# to ACCEPTANCE to 'make it consistent' — that is out of scope. (research §3(a)/(c).)

# GOTCHA #6 — THE KEYBIND LETTER IS D, NEVER F. The canonical binds (hypr-binds.conf:42,44) BOTH use
# key D: 'CTRL SUPER ALT, D' (normal) and 'SUPER ALT, D' (lite). 'F' is bound to nothing. Any
# remaining 'F' reference in README/ACCEPTANCE (e.g. 'Alt+Super+F', 'SUPER+ALT+F', 'pressing F',
# 'bind = SUPER ALT, F') would be a real gap — but the grep finds none. (research §2(a)/§3(a).)

# GOTCHA #7 — USE FULL PATHS / EXPLICIT GREP. Run greps from the repo root
# /home/dustin/projects/voice-typing. This machine's zsh aliases shadow python3/pip/tmux (PRD §2);
# grep/rg are fine, but always cd to the repo root first so relative paths resolve. (system_context.md.)

# GOTCHA #8 — THIS PROJECT USES pytest (NO ruff/mypy). Validation = grep + (if an edit were made)
# py_compile is N/A for .md files. The Validation Loop is PURELY grep-based evidence capture; there
# are no code/test gates because no code/tests change. (research §4.)

# GOTCHA #9 — DO NOT TOUCH T1-T4 FILES, hypr-binds.conf, ctl.py, OR READ-ONLY FILES. T5.S1 owns ONLY
# README.md + tests/ACCEPTANCE.md. The corrected surfaces (install.sh, config.toml, ctl.py,
# daemon.py), hypr-binds.conf (source of truth), PRD.md/tasks.json/prd_snapshot.md (read-only) are
# OFF LIMITS. T4.S1 (parallel) edits daemon.py + test_daemon.py — DISJOINT from T5. (research §5.)

# GOTCHA #10 — THE DELIVERABLE IS THE VERDICT + EVIDENCE, NOT A DIFF. Report the consistency verdict
# in the completion message and ensure the Validation Loop greps all return their expected (clean)
# results. If `git diff --name-only` is non-empty, it must be ONLY an unexpected single-line doc fix
# to README or ACCEPTANCE — never a T1-T4 file.
```

## Implementation Blueprint

### Data models and structure

None. This is a documentation verification task. No code, types, config, schema, or behavior. The
only "data" is grep output (evidence strings).

### Implementation Tasks (ordered — verify, then (conditionally) fix)

```yaml
Task 1: CAPTURE the corrected-surface anchors + source-of-truth values (the comparison basis)
  - RUN (from the repo root): print the canonical keybinds + command set the docs must agree WITH.
        cd /home/dustin/projects/voice-typing
        echo "--- hypr-binds.conf (keybind source of truth) ---"
        grep -nE "^bind = (CTRL )?SUPER ALT, D," hypr-binds.conf
        echo "--- ctl.py _COMMANDS (command-set source of truth) ---"
        grep -nE "_COMMANDS = " voice_typing/ctl.py
        echo "--- PRD.md:371 §7 criterion 6 (the ACCEPTANCE criterion 6 quote source) ---"
        sed -n '371p' PRD.md
  - EXPECTED: hypr-binds.conf shows 'CTRL SUPER ALT, D ... toggle' + 'SUPER ALT, D ... toggle-lite'
    (key D, both); ctl.py _COMMANDS = the 7-cmd tuple; PRD.md:371 = 'voicectl
    toggle/start/stop/status/quit all work; ...'. These three lines are the comparison anchors for
    criteria (a)/(b)/(c) in Tasks 2-4. (Gotcha #6, #9.)

Task 2: VERIFY README.md — criterion (a) no wrong-F; (b) no 5-of-7 list; (c) mappings match
  - RUN (the README sweep; all three greps should return the EXPECTED result):
        cd /home/dustin/projects/voice-typing
        echo "--- (a) wrong-F references in README (expect: none) ---"
        grep -niE "super\+alt\+f|alt\+super\+f|super alt, f|pressing f|bind .* f," README.md \
          && echo "README (a) FAIL: wrong-F found — investigate" || echo "README (a) PASS: no wrong-F"
        echo "--- (b) a pipe-delimited 5-cmd usage line in README (expect: none — contextual only) ---"
        grep -nE "toggle\|start\|stop\|status\|quit[^|]" README.md \
          && echo "README (b) REVIEW: a command-list string exists — check it lists 7" \
          || echo "README (b) PASS: no 5-of-7 pipe-delimited list (commands documented contextually)"
        echo "--- (b2) all 7 commands MENTIONED in README (expect: each appears) ---"
        for c in toggle start stop status quit toggle-lite start-lite; do
          printf '  %-14s ' "$c:"; grep -qE "(^|[^-])\b$c\b|voicectl $c" README.md && echo "present" || echo "ABSENT — REVIEW"
        done
        echo "--- (c) README bind block matches hypr-binds.conf (expect: exact match on D binds) ---"
        grep -nE "^bind = (CTRL )?SUPER ALT, D," README.md
  - EXPECTED: (a) PASS (no wrong-F); (b) PASS (no 5-of-7 list; all 7 commands present contextually —
    notably 'toggle-lite' @L99-100/125, 'start-lite' @L125); (c) README L99-100 shows the same two
    'bind = ... D ...' lines as hypr-binds.conf (CTRL SUPER ALT, D → toggle; SUPER ALT, D →
    toggle-lite). (research §2; Gotcha #4/#6.)
  - IF ANY check deviates from expected: that is a REAL gap — record the exact line, proceed to
    Task 5 (conditional fix). (Expected: no deviation.)

Task 3: VERIFY tests/ACCEPTANCE.md — criteria (a) no wrong-F; (b) criterion 6 is a faithful PRD quote
  - RUN:
        cd /home/dustin/projects/voice-typing
        echo "--- (a) wrong-F references in ACCEPTANCE (expect: none; vacuous — no keybind letters) ---"
        grep -niE "super\+alt\+f|alt\+super\+f|super alt, f|pressing f|bind .* f," tests/ACCEPTANCE.md \
          && echo "ACCEPTANCE (a) FAIL: wrong-F found — investigate" || echo "ACCEPTANCE (a) PASS: no wrong-F"
        echo "--- (a2) any keybind-letter strings at all (expect: none — confirms (a)/(c) vacuous) ---"
        grep -niE "super\+|alt\+|ctrl\+|Alt\+Super\+D|Ctrl\+Alt" tests/ACCEPTANCE.md \
          && echo "ACCEPTANCE (a2) NOTE: keybind letters present — verify they use D" \
          || echo "ACCEPTANCE (a2) PASS: no keybind letters (criterion a/c vacuous)"
        echo "--- (b) criterion 6 row (expect: 'toggle/start/stop/status/quit' — a verbatim PRD §7 #6 quote) ---"
        grep -nE "voicectl toggle/start/stop/status/quit all work" tests/ACCEPTANCE.md
        echo "--- (b2) criterion 10 (lite) references toggle-lite + mode:lite correctly (expect: present) ---"
        grep -nE "toggle-lite|mode: lite|mode: normal" tests/ACCEPTANCE.md | head
  - EXPECTED: (a) PASS; (a2) PASS (no keybind letters); (b) criterion 6 row shows 'voicectl
    toggle/start/stop/status/quit all work' — MATCHING PRD.md:371 (do NOT change it; Gotcha #1);
    (b2) criterion 10 references toggle-lite/mode:lite/mode:normal correctly. (research §3.)
  - IF (a) FAILS (a wrong-F found): that is a REAL gap — proceed to Task 5. (Expected: no failure.)
    NOTE: criterion 6's 5-command list is CORRECT (PRD quote) — it is NEVER a gap. (Gotcha #1.)

Task 4: CONFIRM the no-edit outcome + report the verdict
  - RUN (the deliverable confirmation — git must show no T5 edits):
        cd /home/dustin/projects/voice-typing
        echo "--- git diff --name-only (expect: EMPTY, or only T4.S1's daemon.py/test_daemon.py) ---"
        git diff --name-only
        echo "--- README + ACCEPTANCE NOT in the diff (T5 made no edits) ---"
        git diff --name-only | grep -E "^(README\.md|tests/ACCEPTANCE\.md)$" \
          && echo "T5 NOTE: README/ACCEPTANCE edited — verify it was a real-gap fix only" \
          || echo "T5 PASS: README.md + tests/ACCEPTANCE.md unchanged (consistent as-is)"
  - EXPECTED: `git diff --name-only` is empty OR lists only T4.S1's files
    (`voice_typing/daemon.py`, `tests/test_daemon.py` — the parallel task); README/ACCEPTANCE are NOT
    in the diff. (research §4; Gotcha #2/#10.)
  - REPORT the verdict: "P1.M1.T5.S1: README.md + tests/ACCEPTANCE.md CONFIRMED consistent with the
    corrected lite-mode surfaces (criterion a/b/c PASS via grep sweep; 0 gaps; 0 edits). ACCEPTANCE
    criterion 6's 5-command list is a faithful PRD §7 #6 quote (lite covered by criterion 10) — not
    changed."

Task 5: (CONDITIONAL — ONLY if a REAL gap was found in Task 2 or Task 3) in-place doc fix
  - TRIGGER: only if a grep in Task 2/3 returned an UNEXPECTED result that is a genuine contradiction
    (e.g. a wrong-F reference like 'Alt+Super+F' in README/ACCEPTANCE, or a 5-of-7 list that is NOT
    the PRD-quoted criterion 6). Do NOT trigger for criterion 6's 5-command list (Gotcha #1).
  - FIX: a single-line in-place text edit to README.md OR tests/ACCEPTANCE.md (whichever file has the
    gap), scoped to the offending reference. Use the corrected surface as the target value (e.g.
    F→D; or add the missing lite command to a genuine command list).
  - RECORD: the exact old→new edit (file:line) and the grep that found it, in the completion message.
  - EXPECTED: this task does NOT run (no gap expected). If it does run, `git diff --name-only` lists
    exactly ONE doc file (README.md or tests/ACCEPTANCE.md) — never a T1-T4/source file. (Gotcha #2/#9.)
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — a docs sweep is a comparison against a SOURCE OF TRUTH, not free-form reading. The
# source of truth for keybinds is hypr-binds.conf:42,44 (key D, both binds); for the command set it
# is ctl.py:37 _COMMANDS (7 cmds); for the acceptance-criteria wording it is PRD.md §7. Every README/
# ACCEPTANCE reference is compared against these anchors — that is what makes the sweep deterministic
# and reproducible (not "does this read well"). (research §1.)

# PATTERN 2 — criterion (b) is NOT "every doc must list all 7 commands." It is "where a command list
# APPEARS, it must not omit lite." README has no command list (contextual only) → vacuous PASS.
# ACCEPTANCE criterion 6 IS a command list, but it is a VERBATIM PRD §7 #6 quote (lite is criterion
# 10) → correct, not a gap. (research §2(b)/§3(b); Gotcha #1/#4.)

# PATTERN 3 — the deliverable is the VERDICT + EVIDENCE. The implementing agent's job is to RUN the
# grep sweep, capture the expected (clean) output, and report "confirmed consistent, 0 edits." A
# non-empty git diff is only acceptable as a single-line unexpected doc fix (Task 5). (Gotcha #2/#10.)
```

### Integration Points

```yaml
DELTA ACCEPTANCE (bugfix lite-mode doc remediation — closing sweep):
  - This subtask closes the lite-mode doc-delta by confirming the OVERVIEW docs (README + ACCEPTANCE)
    already agree with the T1-T4-corrected source/help/config/docstring surfaces. PRD §4.8 (7 cmds),
    §4.10 (keybinds), and §7 (acceptance) are now consistent across ALL surfaces: hypr-binds.conf,
    README, ACCEPTANCE, install.sh, config.toml, ctl.py help, and daemon.py docstrings.

PARALLEL — P1.M1.T4.S1 (toggle_lite docstring F→D, in flight):
  - T4.S1 edits voice_typing/daemon.py + tests/test_daemon.py. T5.S1 edits NEITHER (it only
    READS README.md + tests/ACCEPTANCE.md and, conditionally, edits one of those). DISJOINT files —
    no merge contention. T5 reads daemon.py only as a comparison anchor (not edited). (research §5.)

SIBLINGS (all disjoint from T5's README/ACCEPTANCE):
  - T1.S1 (complete) owned install.sh; T2.S1 (complete) owned config.toml; T3.S1 (complete) owned
    ctl.py/test_voicectl.py; T4.S1 (in flight) owns daemon.py/test_daemon.py. None touch
    README.md or tests/ACCEPTANCE.md.

NO INTERFACE / BEHAVIOR / CONFIG CHANGES:
  - No source code, tests, config.toml, hypr-binds.conf, install.sh, or PRD changes. Pure
    documentation verification (expected: zero edits). The only possible output is a single-line
    in-place text fix to README.md OR tests/ACCEPTANCE.md IF a real gap is found (none expected).
```

## Validation Loop

> All gates are grep-based evidence capture (no code/tests change — Gotcha #8). Run from the repo
> root `/home/dustin/projects/voice-typing`. Use full paths; this machine's zsh aliases shadow
> python3/pip/tmux (Gotcha #7). Every gate states its EXPECTED result.

### Level 1: README.md — criterion (a) no wrong-F + (c) mappings match hypr-binds.conf

```bash
cd /home/dustin/projects/voice-typing
echo "=== L1 README: wrong-F references (EXPECT: none) ==="
grep -niE "super\+alt\+f|alt\+super\+f|super alt, f|pressing f|bind .* f," README.md && echo "L1 FAIL" || echo "L1 PASS: README has no wrong-F keybind"
echo "=== L1 README: keybind mentions all use D (EXPECT: Ctrl+Alt+Super+D / Alt+Super+D only) ==="
grep -niE "super\+|alt\+|ctrl\+" README.md
echo "=== L1 README: bind block matches hypr-binds.conf (EXPECT: same two 'bind = ... D' lines) ==="
grep -nE "^bind = (CTRL )?SUPER ALT, D," README.md
# Expected: L1 PASS (no wrong-F); all keybind mentions are D; README L99-100 == hypr-binds.conf:42,44.
```

### Level 2: README.md — criterion (b) no 5-of-7 command list + all 7 commands mentioned

```bash
cd /home/dustin/projects/voice-typing
echo "=== L2 README: a pipe-delimited 5-cmd usage line (EXPECT: none — contextual only) ==="
grep -nE "toggle\|start\|stop\|status\|quit[^|]" README.md && echo "L2 REVIEW" || echo "L2 PASS: no 5-of-7 pipe-delimited list in README"
echo "=== L2 README: each of the 7 commands is MENTIONED (EXPECT: all present) ==="
for c in toggle start stop status quit toggle-lite start-lite; do
  printf '  %-14s ' "$c:"; grep -qE "voicectl $c|(^|[^-])\b$c\b" README.md && echo "present" || echo "ABSENT"
done
# Expected: L2 PASS (no 5-of-7 list); all 7 commands present (toggle-lite + start-lite @L99-100/L125).
```

### Level 3: tests/ACCEPTANCE.md — criteria (a) no wrong-F; (b) criterion 6 = PRD §7 #6 quote; lite in criterion 10

```bash
cd /home/dustin/projects/voice-typing
echo "=== L3 ACCEPTANCE: wrong-F references (EXPECT: none) ==="
grep -niE "super\+alt\+f|alt\+super\+f|super alt, f|pressing f|bind .* f," tests/ACCEPTANCE.md && echo "L3 FAIL" || echo "L3 PASS: ACCEPTANCE has no wrong-F"
echo "=== L3 ACCEPTANCE: keybind-letter strings (EXPECT: none — criterion a/c vacuous) ==="
grep -niE "super\+|alt\+|ctrl\+|Alt\+Super\+D|Ctrl\+Alt" tests/ACCEPTANCE.md && echo "L3 REVIEW" || echo "L3 PASS: ACCEPTANCE states no keybind letters"
echo "=== L3 ACCEPTANCE: criterion 6 row == PRD.md:371 (EXPECT: identical 'toggle/start/stop/status/quit') ==="
echo "--- PRD.md:371 ---"; sed -n '371p' PRD.md
echo "--- ACCEPTANCE criterion 6 ---"; grep -nE "voicectl toggle/start/stop/status/quit all work" tests/ACCEPTANCE.md
echo "=== L3 ACCEPTANCE: criterion 10 lite references (EXPECT: toggle-lite + mode:lite present) ==="
grep -nE "toggle-lite|mode: lite|mode: normal" tests/ACCEPTANCE.md | head
# Expected: L3 PASS; ACCEPTANCE criterion 6 string IDENTICAL to PRD.md:371 (do NOT change — Gotcha #1);
# criterion 10 references toggle-lite/mode:lite correctly.
```

### Level 4: Outcome gate — no edits (or only a scoped single-line doc fix)

```bash
cd /home/dustin/projects/voice-typing
echo "=== L4 git diff --name-only (EXPECT: empty, or only T4.S1's daemon.py/test_daemon.py) ==="
git diff --name-only
echo "=== L4 README/ACCEPTANCE unchanged by T5 (EXPECT: 'T5 PASS: ... unchanged') ==="
git diff --name-only | grep -E "^(README\.md|tests/ACCEPTANCE\.md)$" \
  && echo "L4 NOTE: README/ACCEPTANCE edited — confirm it was a real-gap fix (Task 5), scoped to ONE line" \
  || echo "L4 PASS: README.md + tests/ACCEPTANCE.md unchanged (verified consistent as-is)"
echo "=== L4 read-only / T1-T4 files NOT touched by T5 (EXPECT: no T5 edits there) ==="
git diff --exit-code -- install.sh config.toml voice_typing/ctl.py voice_typing/daemon.py hypr-binds.conf PRD.md \
  && echo "L4 PASS: no edits to corrected-source / read-only files (T4.S1's daemon.py edit is the parallel task, not T5)" \
  || echo "L4 NOTE: daemon.py may show T4.S1's edit (parallel) — that is expected, NOT a T5 edit"
# Expected: git diff empty or T4.S1-only; README/ACCEPTANCE unchanged (or one scoped doc fix if Task 5 ran);
# install.sh/config.toml/ctl.py/hypr-binds.conf/PRD.md untouched by T5.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: README has zero wrong-F keybind references; all keybind mentions use D; README bind block (L99-100) == hypr-binds.conf:42,44.
- [ ] L2: README has no 5-of-7 pipe-delimited command list; all 7 commands are mentioned (incl. toggle-lite, start-lite).
- [ ] L3: ACCEPTANCE has zero wrong-F references; states no keybind letters (criterion a/c vacuous); criterion 6 row == PRD.md:371 (NOT changed); criterion 10 references lite correctly.
- [ ] L4: `git diff --name-only` empty or T4.S1-only; README/ACCEPTANCE unchanged by T5 (or one scoped doc fix if a real gap was found); corrected-source/read-only files untouched by T5.

### Feature Validation
- [ ] Criterion (a) — keybind letter is D (not F) — holds for both README and ACCEPTANCE.
- [ ] Criterion (b) — all 7 commands where a list appears — holds (README contextual/all-7; ACCEPTANCE criterion 6 = PRD §7 #6 quote, lite in criterion 10).
- [ ] Criterion (c) — keybind→command mappings match hypr-binds.conf — holds (README bind block exact match; ACCEPTANCE vacuous).
- [ ] Verdict reported: "README.md + tests/ACCEPTANCE.md CONFIRMED consistent (0 gaps; 0 edits)."

### Code Quality / Scope Validation
- [ ] No speculative edits — both docs verified as-is (Gotcha #2).
- [ ] ACCEPTANCE criterion 6 NOT changed to 7 commands (it is a faithful PRD §7 #6 quote — Gotcha #1).
- [ ] No edits to T1-T4 files, hypr-binds.conf, ctl.py, PRD.md/tasks.json/prd_snapshot.md (Gotcha #9).
- [ ] If an edit WAS made (unexpected), it is a single-line in-place fix to README OR ACCEPTANCE, with the old→new recorded.

### Documentation & Deployment
- [ ] [Mode B] the verification record IS this subtask's deliverable (the grep evidence + verdict); no separate docs artifact.
- [ ] No user-facing/config/API/code/test change (pure documentation verification; expected zero edits).

---

## Anti-Patterns to Avoid

- ❌ Don't "fix" ACCEPTANCE.md criterion 6's `toggle/start/stop/status/quit` to 7 commands — it is a VERBATIM QUOTE of PRD §7 #6 (PRD.md:371); lite is covered by criterion 10. Changing it DIVERGES FROM THE PRD. (Gotcha #1.)
- ❌ Don't make speculative edits "to be thorough" — both docs are already correct (research §2/§3; system_context.md:51). The deliverable is the verification record + verdict, not a diff. (Gotcha #2.)
- ❌ Don't treat the install.sh header comment (install.sh:21-22 "README copies snippets verbatim") as proof README must mirror install.sh's usage line — README has INDEPENDENT correct hotkey/usage prose. The T1.S1 install.sh fix does NOT force a README change. (Gotcha #3.)
- ❌ Don't add a pipe-delimited command list to README — README documents commands contextually (no 5-of-7 enumeration exists); adding one is out of scope. (Gotcha #4.)
- ❌ Don't add keybind letters to ACCEPTANCE.md to "make it consistent" — ACCEPTANCE references commands/modes, not hotkey letters (criterion a/c are vacuous); adding letters is out of scope. (Gotcha #5.)
- ❌ Don't touch the corrected-source files (install.sh, config.toml, ctl.py, daemon.py), hypr-binds.conf (source of truth), or PRD.md/tasks.json/prd_snapshot.md (read-only) — T5 owns ONLY README.md + tests/ACCEPTANCE.md. (Gotcha #9.)
- ❌ Don't invent ruff/mypy/pytest gates — this is a doc-verification task; validation is purely grep-based evidence capture (no code/tests change). (Gotcha #8.)
- ❌ Don't use bare `python`/`uv` (zsh aliases) — but note this task doesn't need python at all (grep/sed only). Always `cd` to the repo root first. (Gotcha #7.)
- ❌ Don't report success without running the L1-L4 grep gates and capturing their EXPECTED (clean) output — the verdict must be backed by reproduced evidence. (Gotcha #10.)

---

## Confidence Score

**9.5/10** for one-pass implementation success. The task is a deterministic doc-consistency sweep with
a verified expected outcome of zero edits: both target docs are empirically confirmed already correct
(research §2/§3 — README: zero wrong-F, all-D keybinds, bind block == hypr-binds.conf, all 7 commands
contextual; ACCEPTANCE: zero wrong-F, no keybind letters, criterion 6 == PRD.md:371 verbatim, lite in
criterion 10). The three drift criteria (a/b/c) are concretely defined, the source-of-truth anchors
(hypr-binds.conf:42,44; ctl.py:37; PRD.md:371) are cited, and the Validation Loop gives exact grep
commands with expected results that reproduce on the live tree. The #1 hazard — misreading ACCEPTANCE
criterion 6 as a 5-of-7 gap and "fixing" it to diverge from the PRD — is explicitly guarded by
Gotcha #1 and the L3 gate (which prints PRD.md:371 alongside the ACCEPTANCE row for direct
comparison). The −0.5 residual is the small chance the implementing agent misjudges a borderline
reference as a gap and makes an unnecessary edit — which the L4 gate (`git diff --name-only`) and the
"no speculative edits" guard (Gotcha #2) catch immediately. No GPU, socket, daemon, network, or code
change is required.
