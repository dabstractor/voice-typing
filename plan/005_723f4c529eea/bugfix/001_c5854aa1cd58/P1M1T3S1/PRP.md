# PRP — P1.M1.T3.S1: Update voicectl help text to list all 7 commands + add help-text assertion test

## Goal

**Feature Goal**: Fix bugfix **Issue 3** (Minor doc defect): `voicectl --help` and the CLI help surfaces in `voice_typing/ctl.py` list only **5 of 7** commands — they omit `toggle-lite`/`start-lite` — while `_COMMANDS` (the canonical tuple, ctl.py:35) and the no-arg error path (ctl.py:179) correctly list all **7**. So `voicectl --help` HIDES lite mode while `voicectl` (no args) REVEALS it: internally inconsistent and contradicting PRD §4.8 (`voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>`). The lite commands themselves already work (main() routes them, ctl.py:197) — only the **help/docstring TEXT** is stale. This subtask updates 4 text surfaces in `ctl.py` to list all 7, and adds a **TDD red→green** test asserting every help surface contains all 7 commands so the drift cannot recur.

**Deliverable** (2 files edited, no new files):
1. `voice_typing/ctl.py` — 4 text edits (no behavior change): (a) module-docstring Usage line, (b) module-docstring subcommand block (+2 lines), (c) argparse epilog, (d) positional `cmd` help.
2. `tests/test_voicectl.py` — one ADDITIVE test (`test_help_surfaces_list_all_seven_commands`) under a new banner section: builds the parser via `ctl._build_parser()`, asserts `format_help()` + `ctl.__doc__` each contain all 7 commands. RED before the ctl.py fix, GREEN after.

**Success Definition**:
- (a) `ctl._build_parser().format_help()` lists all 7 commands (toggle, start, stop, status, quit, **toggle-lite, start-lite**) in both the positional `cmd` help AND the epilog.
- (b) `ctl.__doc__` (the module docstring) lists all 7 in the Usage line AND documents `toggle-lite`/`start-lite` in the subcommand block.
- (c) The new test is **RED before** the ctl.py edits (TDD) and **GREEN after**.
- (d) `_COMMANDS`, `main()`, `format_result()`, `send_command()` are byte-identical — zero runtime behavior change. All existing tests pass unmodified.
- (e) `voicectl --help` and `voicectl` (no args) now show the SAME 7-command set (the inconsistency is gone).

> **VERIFIED DEFECT (this PRP's research):** `voicectl --help` shows `toggle | start | stop | status | quit` (5); the no-arg path shows `choose from toggle, start, stop, status, quit, toggle-lite, start-lite` (7). The implementing agent applies the 4 verbatim edits below; the new test goes red→green.

## User Persona

**Target User**: the end user / operator who runs `voicectl --help` (or reads the module docstring) to discover what commands exist — including the lite-mode commands bound to `Alt+Super+D` (PRD §4.10).
**Use Case**: user wants to try lite mode (single small model, lower latency), runs `voicectl --help` to find the command, and currently sees no lite option — so they conclude lite mode doesn't exist or has no CLI. After the fix, `--help` shows `toggle-lite`/`start-lite` alongside the normal commands.
**Pain Points Addressed**: Issue 3 — `--help` hides lite mode while the no-arg error path reveals it; a user reading `--help` is actively misled into thinking there are only 5 commands.

## Why

- **PRD §4.8 is the source of truth.** It specifies the 7-command surface: `voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>`. `_COMMANDS` (ctl.py:35) implements exactly that. The 4 help surfaces contradict it (5 commands) AND contradict the no-arg path (7 commands).
- **The inconsistency is the real harm.** A user who runs `voicectl --help` sees 5 commands; a user who mistypes and runs `voicectl` (no args) sees 7. Same binary, two different answers about its own command set. That erodes trust in the help system and makes lite mode undiscoverable via the canonical discovery command (`--help`).
- **Why it slipped past tests.** The suite asserts `toggle-lite`/`start-lite` are in `_COMMANDS` (test_voicectl.py:75) but NO test asserts the HELP STRINGS list them. argparse's epilog/help are plain string literals (not derived from `_COMMANDS`), so they drift silently. The new TDD test reads `format_help()` + `ctl.__doc__` as text and asserts all 7 appear — closing the gap permanently.
- **Scope discipline.** T3.S1 owns ONLY `voice_typing/ctl.py` (4 text edits) + `tests/test_voicectl.py` (1 test). It does NOT touch `_COMMANDS`/`main()`/`format_result`/`send_command` (behavior unchanged), `config.toml` (P1.M1.T2.S1), `daemon.py` `toggle_lite` docstring (P1.M1.T4.S1), `install.sh` (P1.M1.T1.S1 — complete), `hypr-binds.conf` (correct), or `README` (P1.M1.T5.S1). Pure Mode-A doc surface fix + a regression test.

## What

Apply 4 verbatim text edits to `voice_typing/ctl.py` (lines 14-20, 156, 161) so every help surface lists all 7 commands, then add one TDD test to `tests/test_voicectl.py` that asserts all 7 appear in `format_help()` + `ctl.__doc__`. No value/schema/behavior change.

### Success Criteria

- [ ] ctl.py:20 Usage line reads `Usage:  voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>`.
- [ ] ctl.py subcommand block (after the `quit` line) documents `toggle-lite` (arm/disarm in LITE mode, single small model, PRD §4.2ter) and `start-lite` (arm in LITE mode).
- [ ] ctl.py:156 epilog reads `subcommands: toggle, start, stop, status, quit, toggle-lite, start-lite  (see the project README for the full usage table)`.
- [ ] ctl.py:161 positional help reads `toggle | start | stop | status | quit | toggle-lite | start-lite`.
- [ ] `_COMMANDS`, `main()`, `format_result()`, `send_command()`, `_build_parser()` body logic UNCHANGED (only the epilog/help STRING LITERALS change).
- [ ] New `test_help_surfaces_list_all_seven_commands` passes; it is RED before the ctl.py edits (TDD).
- [ ] `.venv/bin/python -m pytest tests/test_voicectl.py -v` → 0 failures (all existing + the 1 new).
- [ ] `git diff --name-only` == `voice_typing/ctl.py` + `tests/test_voicectl.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact defect is empirically confirmed (the live `--help` output shows 5 commands; the no-arg path shows 7). Every edit is given as verbatim old→new text against the current file (exact line numbers: 14-20, 156, 161 — verified), the `_COMMANDS` source of truth + the no-arg consistency reference are cited, the TDD test design + placement are specified (mirroring the file's banner-section convention), and the no-conflict boundary with the parallel T2.S1 (disjoint files) is established. An agent new to this repo can apply the fix from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the verified defect + the verbatim old→new edits + the TDD test design (this task's own research)
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/P1M1T3S1/research/voicectl_help_text_7_commands.md
  why: "§0 confirms the defect empirically (--help=5, no-arg=7). §1 is the verbatim old→new for all 4 edit
        sites with exact line numbers. §2 explains WHY this slipped past tests (help strings are literals,
        not derived from _COMMANDS; no test asserted them). §3 is the TDD test design + placement (banner
        section at END of test_voicectl.py; format_help() covers epilog+positional; ctl.__doc__ covers the
        docstring) + the red→green proof. §4 parallel no-conflict. §5 scope discipline."
  critical: "§1 (the 4 verbatim edits) and §3 (the test) are load-bearing. The subcommand-block padding
            note (lite names are 10-12 chars → own 2-3 space padding, not column-13) prevents a misaligned
            block. The 'do NOT derive from _COMMANDS at runtime' note (§5) prevents an out-of-scope refactor."

# THE FILE UNDER FIX — voice_typing/ctl.py (the 4 edit sites)
- file: voice_typing/ctl.py
  why: "The 4 stale surfaces: (a) module docstring Usage line @20; (b) module docstring subcommand block
        @14-18 (5 commands, no lite); (c) _build_parser() epilog @156; (d) positional cmd help @161.
        _COMMANDS @35 (the 7-command truth) and main()'s no-arg path @179 (', '.join(_COMMANDS) = 7) are
        ALREADY correct — use them as the consistency reference, do NOT edit them."
  pattern: "All 4 surfaces are plain STRING LITERALS (not derived from _COMMANDS). Append the literal
            tokens '|toggle-lite|start-lite' / ', toggle-lite, start-lite' / ' | toggle-lite | start-lite'
            to the existing strings. Keep the curated ordering (normal commands first, lite last) and the
            '(see the project README for the full usage table)' suffix on the epilog."
  gotcha: "Do NOT replace the literals with a runtime `', '.join(_COMMANDS)` derivation — that reorders
           the commands and is an out-of-scope refactor (Mode A = a text fix). Append literal tokens."

# THE TEST FILE — tests/test_voicectl.py (where the new test goes)
- file: tests/test_voicectl.py
  why: "Imports `from voice_typing import ctl, daemon` @24. The argparse/structural section @218 has the
        patterns to mirror (test_main_rejects_unknown_command @220, test_main_rejects_missing_command @227).
        test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode @75 asserts toggle-lite/start-lite
        are in _COMMANDS (the EXISTING coverage gap this task closes at the help-string level). Each subtask
        adds its own BANNER SECTION at the END of the file (e.g. 'P1.M2.T1.S2 — loading models… hint' @263)
        — mirror that convention for the new test."
  pattern: "ADD a new section at the END under a 'P1.M1.T3.S1 — help text surfaces all 7 commands' banner.
            The test builds ctl._build_parser(), calls .format_help() (renders BOTH positional help AND
            epilog), and asserts all 7 commands are substrings; also asserts ctl.__doc__ contains all 7.
            No socket/daemon/subprocess — pure stdlib argparse formatting (hermetic)."
  critical: "format_help() is the right seam (it renders the epilog + positional help the user sees in
            `voicectl --help`). ctl.__doc__ is the module docstring. Asserting 'start'/'toggle' is trivially
            satisfied (substrings of start-lite/toggle-lite) — the LOAD-BEARING assertions are
            'toggle-lite'/'start-lite' (the 2 that are missing before the fix = the red→green discriminators)."

# THE MANDATE — PRD §4.8 (the 7-command spec) + Issue 3 definition
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md
  why: "§4.8 pins the 7-command surface: voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>.
        Issue 3 (Minor) is the source: 'voicectl --help and CLI help text omit the lite commands (lists 5
        of 7)' with the Suggested Fix: 'Add toggle-lite/start-lite to the epilog, the cmd help=, and the
        module-docstring usage/subcommand block in ctl.py. (The drift is untested ... no test asserts the
        help strings list them.)'"
  critical: "This subtask IS that fix + the test that closes the 'untested' gap. The 4 surfaces named in
            Issue 3 (docstring usage, docstring subcommand block, epilog, cmd help) are exactly the 4 edits."

# THE SOURCE OF TRUTH — _COMMANDS + the no-arg path (the consistency reference)
- file: voice_typing/ctl.py
  why: "_COMMANDS @35 = the canonical 7. main()'s no-arg path @179 prints ', '.join(_COMMANDS) = all 7
        (ALREADY correct — the reference the 4 stale surfaces must match). main() routes the lite commands
        @197 (start/toggle/start-lite/toggle-lite → loading hint) — so they WORK; only the help text is stale."
  critical: "Do NOT edit _COMMANDS or main(). They are the reference, not the defect. The 4 edits make the
            help surfaces AGREE with _COMMANDS (which they currently don't)."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── ctl.py                # 4 stale help surfaces @14-20,156,161; _COMMANDS @35 (correct); main() @179 (correct).
│   │                           NOTE: T2.S1 (parallel) edits config.toml + test_config_repo_default.py — DISJOINT.
└── tests/
    └── test_voicectl.py       # imports `from voice_typing import ctl` @24; argparse section @218;           ← EDIT (additive banner + 1 test)
                                # lite-in-_COMMANDS test @75 (the gap this task's help-text test closes).
# NOTE: the fix is 4 string-literal appends in ctl.py + 1 additive test. No behavior change. No GPU/socket/daemon.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/ctl.py            # EDIT: 4 text surfaces (Usage line, subcommand block +2 lines, epilog, cmd help).
#                              _COMMANDS/main()/format_result()/send_command() UNCHANGED. No new imports.
tests/test_voicectl.py         # ADD: one banner section + test_help_surfaces_list_all_seven_commands (additive;
#                              no existing test changed). No new imports (uses ctl._build_parser + ctl.__doc__).
# No new files. No config.toml / daemon.py / install.sh / README / hypr-binds.conf changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE 4 SURFACES ARE STRING LITERALS, NOT DERIVED FROM _COMMANDS. Append literal tokens
# ('|toggle-lite|start-lite' / ', toggle-lite, start-lite' / ' | toggle-lite | start-lite'); do NOT replace
# them with a runtime f"', '.join(_COMMANDS)" derivation. A derivation would (a) reorder the commands
# (tuple order ≠ the curated help order), (b) be an out-of-scope refactor (Mode A = a text fix), and (c)
# drop the '(see the project README for the full usage table)' epilog suffix. (research §5.)

# CRITICAL #2 — THE SUBCOMMAND-BLOCK PADDING. The existing normal commands (toggle/start/stop/status/quit)
# are ≤6 chars and pad their descriptions to column 13. The lite names are 10-12 chars (toggle-lite=12,
# start-lite=10) — they CANNOT align to column 13 without negative padding. Give them their own 2-3 space
# padding (matches the contract's example: 'toggle-lite  arm/...' / 'start-lite   arm/...'). Do NOT try to
# force them into the column-13 grid. (research §1 edit (b).)

# CRITICAL #3 — TDD RED→GREEN. The new test MUST fail BEFORE the ctl.py edit and pass AFTER. Verify by
# running it once against the unedited ctl.py (expect RED: 'toggle-lite' missing from --help / docstring),
# then apply the 4 edits and re-run (expect GREEN). If the test is GREEN before the edit, the assertions
# are wrong (too weak) — re-tighten. (research §3; mirrors the sibling T2.S1 TDD pattern.)

# CRITICAL #4 — DO NOT EDIT _COMMANDS OR main(). They are the canonical 7-command truth (ctl.py:35) and
# the correct no-arg error path (ctl.py:179). The 4 stale surfaces must AGREE with them — the surfaces are
# the defect, not _COMMANDS. Editing _COMMANDS/main() is out of scope and would change runtime behavior.

# GOTCHA #5 — format_help() IS THE RIGHT TEST SEAM. ctl._build_parser().format_help() renders BOTH the
# positional `cmd` help AND the epilog (the two argparse-level surfaces) in one string — verified
# empirically. So one format_help() call covers edit sites (c) and (d). ctl.__doc__ covers the module
# docstring (edit sites (a) and (b)). Two assertions, four surfaces covered. (research §3.)

# GOTCHA #6 — 'start'/'toggle' ASSERTIONS ARE TRIVIALLY TRUE. 'start' is a substring of 'start-lite' and
# 'toggle' of 'toggle-lite', so asserting them is always satisfied. The LOAD-BEARING red→green
# discriminators are 'toggle-lite' and 'start-lite' (the 2 that are absent before the fix). The loop over
# all 7 is belt-and-suspenders + expresses intent ('all 7 appear'); do NOT drop the lite-only assertions.

# GOTCHA #7 — USE FULL PATHS. This machine aliases python3→uv run, pip→alias, tmux→zsh plugin. Invoke
# .venv/bin/python (and .venv/bin/voicectl for the empirical --help check) explicitly. Never bare
# python/pytest/uv. (system_context.md.)

# GOTCHA #8 — THIS PROJECT USES pytest (NO ruff/mypy in pyproject). Validation = py_compile + pytest. Do
# NOT invent ruff/mypy commands (the PRP template's ruff/mypy lines are N/A here).

# GOTCHA #9 — NO SOCKET / DAEMON / GPU in the new test. format_help() + ctl.__doc__ are pure stdlib text
# operations. The test is hermetic (no connection, no subprocess beyond what ctl import does — which is
# pure: ctl imports only argparse/json/socket/sys/threading + daemon._default_control_socket_path).

# GOTCHA #10 — DO NOT touch config.toml (T2.S1), daemon.py (T4.S1), install.sh (T1.S1-complete), README
# (T5.S1), or hypr-binds.conf (correct). Only voice_typing/ctl.py + tests/test_voicectl.py. Editing other
# files risks a conflict with the parallel/later siblings (disjoint files = clean merges).
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config, no behavior. The only "data" is 4 string-literal
appends + one additive test function. `_COMMANDS` (the 7-tuple) is the unchanged source of truth.

### Implementation Tasks (ordered by dependencies — TDD: test FIRST, then the fix)

```yaml
Task 1: ADD the failing test FIRST (TDD red) — tests/test_voicectl.py
  - PLACE: a new banner section at the END of tests/test_voicectl.py (the file's convention — each subtask
    appends its own banner section; e.g. 'P1.M2.T1.S2 — loading models… hint' is the last one today).
  - ADD (verbatim; `ctl` is already imported at the top: `from voice_typing import ctl, daemon`):
        # ===========================================================================
        # P1.M1.T3.S1 — help text surfaces all 7 commands (bugfix Issue 3)
        # (argparse format_help() + the module docstring must list toggle-lite/start-lite, matching
        #  _COMMANDS + PRD §4.8 + the no-arg error path. Before the fix --help showed only 5 while
        #  `voicectl` (no args) showed 7 — internally inconsistent. TDD red→green.)
        # ===========================================================================
        def test_help_surfaces_list_all_seven_commands():
            """All 7 commands appear in every help surface (PRD §4.8; bugfix Issue 3).

            argparse's format_help() renders BOTH the positional `cmd` help AND the epilog (the two
            --help surfaces); ctl.__doc__ is the module docstring (Usage line + subcommand block). All
            must list toggle-lite/start-lite, matching _COMMANDS + the no-arg error path. Before the
            ctl.py fix this is RED (the lite commands are absent from --help + the docstring).
            """
            seven = {"toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite"}
            assert set(ctl._COMMANDS) == seven, sorted(ctl._COMMANDS)   # _COMMANDS = the source of truth
            # (1) argparse --help (format_help renders BOTH the positional help AND the epilog):
            help_text = ctl._build_parser().format_help()
            for cmd in seven:
                assert cmd in help_text, f"{cmd!r} missing from --help:\n{help_text}"
            # (2) module docstring (Usage line + subcommand block):
            assert ctl.__doc__ is not None, "ctl module docstring is missing"
            for cmd in seven:
                assert cmd in ctl.__doc__, f"{cmd!r} missing from the ctl module docstring"
  - RUN (confirm RED before the fix — TDD):
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/test_voicectl.py::test_help_surfaces_list_all_seven_commands -v
  - EXPECTED: the test FAILS (RED) with "toggle-lite missing from --help" (and/or the docstring). This
    proves the defect is real and the test discriminates. (If it PASSES, the assertions are too weak —
    re-check; Gotcha #6.) This RED run is the TDD baseline.

Task 2: EDIT voice_typing/ctl.py — module docstring Usage line (edit site a)
  - FIND ctl.py:20 (the Usage line in the module docstring). Current:
        Usage:  voicectl <toggle|start|stop|status|quit>
  - EDIT (oldText → newText):
      OLD: Usage:  voicectl <toggle|start|stop|status|quit>
      NEW: Usage:  voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>

Task 3: EDIT voice_typing/ctl.py — module docstring subcommand block (edit site b)
  - FIND the subcommand block (ctl.py:14-18). Current last line:
        quit     request a clean daemon shutdown (releases GPU workers)
  - EDIT: append two lines AFTER the `quit` line (Gotcha #2 — lite names get their own 2-3 space padding,
    NOT the column-13 grid the ≤6-char normal names use):
      OLD:
        quit     request a clean daemon shutdown (releases GPU workers)
      NEW:
        quit     request a clean daemon shutdown (releases GPU workers)
        toggle-lite  arm/disarm in LITE mode (single small model — PRD §4.2ter)
        start-lite   arm in LITE mode (start listening with the small model only)

Task 4: EDIT voice_typing/ctl.py — argparse epilog (edit site c)
  - FIND ctl.py:156 (the epilog= in _build_parser). Current:
        epilog="subcommands: toggle, start, stop, status, quit  (see the project README for the full usage table)",
  - EDIT (oldText → newText — append ', toggle-lite, start-lite' before the two-space + suffix):
      OLD: epilog="subcommands: toggle, start, stop, status, quit  (see the project README for the full usage table)",
      NEW: epilog="subcommands: toggle, start, stop, status, quit, toggle-lite, start-lite  (see the project README for the full usage table)",

Task 5: EDIT voice_typing/ctl.py — positional cmd help (edit site d)
  - FIND ctl.py:161 (the help= on the `cmd` positional). Current:
        help="toggle | start | stop | status | quit",
  - EDIT (oldText → newText — append ' | toggle-lite | start-lite'):
      OLD: help="toggle | start | stop | status | quit",
      NEW: help="toggle | start | stop | status | quit | toggle-lite | start-lite",

Task 6: VERIFY — TDD green + the empirical --help + full test_voicectl.py suite
  - RUN (the test from Task 1 must now be GREEN):
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/test_voicectl.py::test_help_surfaces_list_all_seven_commands -v
  - EXPECTED: PASS (GREEN). (Tasks 2-5 made both surfaces contain all 7.)
  - RUN (empirical confirmation — voicectl --help now shows 7):
      .venv/bin/python -c "from voice_typing import ctl; print(ctl._build_parser().format_help())"
      .venv/bin/voicectl --help    # the real CLI surface (full path — Gotcha #7)
  - EXPECTED: the positional help reads 'toggle | start | stop | status | quit | toggle-lite | start-lite'
    AND the epilog reads 'subcommands: toggle, start, stop, status, quit, toggle-lite, start-lite ...'.
  - RUN (full test_voicectl.py — no regression):
      .venv/bin/python -m pytest tests/test_voicectl.py -v
  - EXPECTED: 0 failures (all existing + the 1 new). See Validation L2.
  - DO NOT: edit _COMMANDS/main()/format_result()/send_command(); derive the help from _COMMANDS at runtime;
    touch config.toml/daemon.py/README/install.sh/hypr-binds.conf.

Task 7: VALIDATE — run the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T3.S1: voicectl --help + docstring now list all 7 commands (toggle-lite,
  start-lite added); help-text assertion test added (TDD red→green)."
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — append literal tokens to the existing curated strings (do NOT derive from _COMMANDS).
# The epilog/help/Usage are hand-curated for ordering + the README-reference suffix; appending the two
# lite tokens keeps them in lockstep with _COMMANDS without a refactor. (Gotcha #1.)
# epilog:   "...status, quit"  ->  "...status, quit, toggle-lite, start-lite  (see ... README ...)"
# cmd help: "toggle | ... | quit"  ->  "toggle | ... | quit | toggle-lite | start-lite"
# Usage:    "<toggle|...|quit>"    ->  "<toggle|...|quit|toggle-lite|start-lite>"

# PATTERN 2 — the TDD test reads TEXT (format_help + __doc__), not runtime values. argparse's epilog/help
# are string literals that can drift from _COMMANDS (the defect). Asserting the rendered TEXT against the
# 7-command set closes the gap permanently: any future removal of a lite command from a help surface turns
# the test RED. (Gotcha #5/#6.)
help_text = ctl._build_parser().format_help()   # renders positional help + epilog (verified)
for cmd in seven: assert cmd in help_text        # 'toggle-lite'/'start-lite' are the red→green discriminators
for cmd in seven: assert cmd in ctl.__doc__       # the module docstring (Usage line + subcommand block)
```

### Integration Points

```yaml
DELTA ACCEPTANCE (bugfix Issue 3 / PRD §4.8):
  - This subtask fixes Issue 3 (the help-text drift) + adds the regression test that the issue's analysis
    flagged as missing ("no test asserts the help strings list them"). PRD §4.8's 7-command surface is now
    consistent across _COMMANDS, the no-arg path, AND --help/the docstring.

PARALLEL — P1.M1.T2.S1 (config.toml lite_model keybind comment, in flight):
  - T2.S1 edits config.toml + tests/test_config_repo_default.py. T3.S1 edits voice_typing/ctl.py +
    tests/test_voicectl.py. DISJOINT files — no line-level conflict. Both are Mode-A doc fixes with a
    TDD static-text test. Clean merge.

SIBLINGS (later, also disjoint):
  - P1.M1.T4.S1 edits voice_typing/daemon.py toggle_lite docstring ('pressing F' → 'pressing D').
  - P1.M1.T5.S1 verifies README/overview consistency. Neither touches ctl.py.

NO INTERFACE / BEHAVIOR CHANGES:
  - _COMMANDS, main(), format_result(), send_command(), _build_parser() body logic: UNCHANGED. The lite
    commands already work (main routes them @197); only the help/docstring TEXT changes. Exit codes
    (0/1/2/64), the no-arg error path, and the loading-hint routing are all byte-identical.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy — Gotcha #8). All gates are
> pure/hermetic (no GPU/socket/daemon).

### Level 1: The 4 edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- (a) Usage line lists 7 ---"
grep -n '^Usage:' voice_typing/ctl.py
echo "--- (b) subcommand block documents toggle-lite + start-lite ---"
grep -nE 'toggle-lite|start-lite' voice_typing/ctl.py | grep -E 'arm|LITE|listening'
echo "--- (c) epilog lists 7 ---"
grep -n 'subcommands:' voice_typing/ctl.py
echo "--- (d) positional help lists 7 ---"
grep -n 'help="toggle' voice_typing/ctl.py
echo "--- _COMMANDS + main() UNCHANGED (still 7; no behavior edit) ---"
grep -n '_COMMANDS: tuple' voice_typing/ctl.py
# Expected: Usage line ends '|toggle-lite|start-lite>'; epilog has ', toggle-lite, start-lite'; cmd help
# ends '| toggle-lite | start-lite"'; the subcommand block has 2 new lines; _COMMANDS still the 7-tuple.
```

### Level 2: TDD red→green + full test_voicectl.py suite (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the new test PASSES (GREEN after Tasks 2-5) ---"
"$PY" -m pytest tests/test_voicectl.py::test_help_surfaces_list_all_seven_commands -v
echo "--- full test_voicectl.py — no regression (all existing + the 1 new) ---"
"$PY" -m pytest tests/test_voicectl.py -v 2>&1 | tail -8
# Expected: the new test PASSES; the full suite is GREEN (0 failures). (If you ran the new test BEFORE the
# ctl.py edits per Task 1, it was RED — that is the TDD baseline, now resolved by Tasks 2-5.)
```

### Level 3: Empirical --help shows all 7 (the user-facing fix)

```bash
cd /home/dustin/projects/voice-typing
echo "--- format_help() (positional help + epilog) ---"
.venv/bin/python -c "from voice_typing import ctl; print(ctl._build_parser().format_help())"
echo "--- the real CLI surface ---"
.venv/bin/voicectl --help
echo "--- the module docstring (Usage + subcommand block) ---"
.venv/bin/python -c "from voice_typing import ctl; print(ctl.__doc__)"
echo "--- consistency: --help and no-arg now AGREE on the 7-command set ---"
.venv/bin/voicectl 2>&1 | head -1   # no-arg path: 'choose from toggle, start, stop, status, quit, toggle-lite, start-lite'
# Expected: --help's positional help + epilog both list toggle-lite/start-lite; the docstring Usage line +
# subcommand block list them; the no-arg path already did. All surfaces now agree on the 7-command set.
```

### Level 4: Scope guards — only ctl.py + test_voicectl.py changed; behavior unchanged

```bash
cd /home/dustin/projects/voice-typing
echo "--- only the 2 in-scope files changed ---"
git diff --name-only
echo "--- _COMMANDS / main() / format_result / send_command body UNCHANGED ---"
git diff voice_typing/ctl.py | grep -E '^[+-]' | grep -vE '^[+-]{3}|^[+-]\s*#|Usage:|toggle-lite|start-lite|epilog=|help="toggle|arm/disarm in LITE|arm in LITE' || echo "(only the 4 help/docstring surfaces changed — behavior untouched)"
echo "--- read-only / sibling files UNCHANGED ---"
git diff --exit-code -- config.toml voice_typing/daemon.py install.sh README.md hypr-binds.conf PRD.md plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/tasks.json plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md .gitignore && echo "L4 PASS: no config/daemon/install/README/read-only changes" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected: git diff --name-only == voice_typing/ctl.py + tests/test_voicectl.py; the behavior-filter shows
# only help/docstring lines changed; config.toml/daemon.py/install.sh/README/hypr-binds.conf untouched.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: all 4 edit sites present (Usage line, subcommand block +2 lines, epilog, cmd help); `_COMMANDS` unchanged.
- [ ] L2: new `test_help_surfaces_list_all_seven_commands` GREEN (was RED before the edits per Task 1); full `tests/test_voicectl.py` green.
- [ ] L3: empirical `voicectl --help` + `ctl.__doc__` list all 7; `--help` and the no-arg path now agree.
- [ ] L4: only `voice_typing/ctl.py` + `tests/test_voicectl.py` changed; `_COMMANDS`/`main()`/`format_result`/`send_command` body untouched; sibling/read-only files unchanged.

### Feature Validation
- [ ] `voicectl --help` shows `toggle-lite`/`start-lite` in BOTH the positional help and the epilog.
- [ ] The module docstring lists all 7 in the Usage line and documents the 2 lite commands in the subcommand block.
- [ ] `--help` and `voicectl` (no args) report the SAME 7-command set (the inconsistency is resolved).
- [ ] The lite commands still work (main() routing @197 unchanged — no behavior regression).

### Code Quality / Scope Validation
- [ ] 4 string-literal appends only — no runtime derivation from `_COMMANDS` (Gotcha #1); curated ordering + README suffix preserved.
- [ ] Subcommand-block lite lines use their own 2-3 space padding (Gotcha #2), not the column-13 grid.
- [ ] New test is ADDITIVE (banner section at END; no existing test changed); pure stdlib (no socket/daemon/GPU).
- [ ] No conflict with parallel T2.S1 (disjoint files); no edit to config.toml/daemon.py/install.sh/README/hypr-binds.conf.

### Documentation & Deployment
- [ ] [Mode A] the user-facing CLI surface (`voicectl --help` + docstring) is the doc fix — no separate docs subtask.
- [ ] No user-facing/config/API BEHAVIOR change (exit codes, command routing, loading hints all byte-identical).

---

## Anti-Patterns to Avoid

- ❌ Don't derive the epilog/help/Usage from `_COMMANDS` at runtime (`f"subcommands: {', '.join(_COMMANDS)}"`) — that reorders the commands, drops the README suffix, and is an out-of-scope refactor. Append literal tokens. (Gotcha #1.)
- ❌ Don't force the lite subcommand-block lines into the column-13 description grid — the lite names are 10-12 chars and can't align to it. Give them their own 2-3 space padding (matches the contract example). (Gotcha #2.)
- ❌ Don't skip the TDD red step (Task 1) — run the new test AGAINST THE UNEDITED ctl.py first to confirm it FAILS (proves the defect + that the test discriminates). If it's green before the fix, the assertions are too weak. (Gotcha #3.)
- ❌ Don't edit `_COMMANDS`, `main()`, `format_result()`, or `send_command()` — they are the correct 7-command truth + the correct no-arg path; the 4 stale help surfaces are the defect. (Gotcha #4.)
- ❌ Don't touch config.toml (T2.S1), daemon.py (T4.S1), install.sh (T1.S1-complete), README (T5.S1), or hypr-binds.conf (correct) — only `voice_typing/ctl.py` + `tests/test_voicectl.py`. (Gotcha #10.)
- ❌ Don't use bare `python`/`pytest`/`uv`/`voicectl` (zsh aliases shadow them) — use `.venv/bin/python` / `.venv/bin/voicectl`. (Gotcha #7.)
- ❌ Don't invent ruff/mypy gates — this project uses pytest only. (Gotcha #8.)
- ❌ Don't drop the lite-only assertions in the test — `start`/`toggle` are trivially satisfied (substrings of start-lite/toggle-lite); `toggle-lite`/`start-lite` are the red→green discriminators. (Gotcha #6.)
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9.5/10** for one-pass implementation success. The defect is empirically confirmed (the live `--help` shows 5; the no-arg path shows 7), the 4 edits are given as verbatim old→new text against exact current line numbers (14-20, 156, 161 — verified), the TDD test design + placement mirror the file's existing banner-section convention and use the verified `format_help()`/`ctl.__doc__` seams, and the parallel T2.S1 edits disjoint files (config.toml/test_config_repo_default.py). The −0.5 residual is purely the small chance of a copy-paste slip in one of the 4 string appends (e.g., a missing space/pipe) — which the L1 grep + the L2 test (it asserts exact substrings) catch immediately. No GPU, socket, daemon, or network is required.
