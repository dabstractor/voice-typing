# PRP — P1.M2.T4.S1: Remap argparse usage errors to exit 64; reserve 2 for daemon-not-running

## Goal

**Feature Goal**: Fix bugfix Issue 7 (PRD §4.8; selected h3.6). Today `voicectl` exits **2** for
both a usage error (argparse: `voicectl` with no command, or `voicectl frobnicate`) and a genuine
"daemon not running" — so a caller checking `$? -eq 2` cannot tell a typo from a down daemon.
Remap **usage errors → exit 64** (BSD `sysexits.h` `EX_USAGE`) and make **2 exclusive to
daemon-not-running**. Exit codes 0 (success) and 1 (logical failure) are unchanged.

**Deliverable** (two files; no new files):
- `voice_typing/ctl.py`: stop letting argparse validate the command (`choices` removed) and
  validate it manually in `main()`, returning 64 for unknown/missing commands. The positional
  MUST become optional (`nargs='?'`) so a *missing* command does not trigger argparse's
  `SystemExit(2)`. Update the three in-file exit-code docstrings to document 64.
- `tests/test_voicectl.py`: change `test_main_rejects_unknown_command` to assert returned `64`;
  add `test_main_rejects_missing_command`; leave the three daemon-not-running tests asserting `2`.

**Success Definition**:
- `voicectl frobnicate` prints `voicectl: invalid command 'frobnicate'; choose from toggle, start, stop, status, quit` to **stderr** and the shell sees `rc=64`.
- `voicectl` (no command) prints `voicectl: a command is required; choose from toggle, start, stop, status, quit` to **stderr** and the shell sees `rc=64`.
- `voicectl status` against a live daemon → `rc=0` (unchanged); against a down daemon → `rc=2` (unchanged).
- A script can distinguish: `$? -eq 2` ⟺ daemon down; `$? -eq 64` ⟺ the user typed the command wrong.
- `tests/test_voicectl.py` is fully green (modified test, new test, and the three unchanged exit-2 tests).

## User Persona

**Target User**: A Linux power user scripting around `voicectl` (status checks, restart-on-down
wrappers, Nagios/systemd health hooks) — and, secondarily, any interactive user who mistypes a
command.

**Use Case**: A wrapper script wants to react differently to "daemon down" (restart it) vs
"caller typo" (surface a usage error, do NOT loop-restart).

**User Journey**: user runs `voicectl statu` → sees `invalid command 'statu'` on stderr + `$?=64`
→ corrects to `status`. Separately, `voicectl status` against a dead unit → `daemon not running` +
`$?=2` → wrapper runs `systemctl --user start voice-typing`.

**Pain Points Addressed**: Today both cases are `$?=2`, so a restart-on-down wrapper would fire
on every typo and any typo-check would fire when the daemon is merely down.

## Why

- **PRD §4.8 contracts exit 2 for "daemon not running"**: that contract is broken while argparse
  also emits 2 for usage errors. Issue 7 calls this out as "a caller checking `$? -eq 2` cannot
  tell a usage error from a down daemon."
- **Distinguishing codes is cheap and standard**: `64` = `EX_USAGE` from BSD `sysexits.h`, the
  conventional "command-line usage error" code. Scripts that only care about success/failure keep
  working (`$? -ne 0`); scripts that care about *why* now can.
- **Minimal, surgical, low-risk**: a parser tweak + one `if`/`return` before socket resolution.
  No new deps, no socket/protocol change, daemon-not-running path untouched. stdlib-only stays
  stdlib-only.

## What

In `voice_typing/ctl.py`:
1. Add a module constant `_EX_USAGE: int = 64` next to `_COMMANDS`.
2. In `_build_parser()`: **remove `choices=_COMMANDS`** from the `cmd` positional and **add
   `nargs="?"`** (so a missing command yields `args.cmd = None` instead of argparse `SystemExit(2)`).
   Update the parser's `description=` string and `_build_parser` docstring.
3. In `main()`: immediately after `parse_args()`, validate `if cmd not in _COMMANDS:` — print a
   distinct stderr message (missing vs invalid) and `return _EX_USAGE`. Update `main()` docstring
   and the module-level exit-code table.

In `tests/test_voicectl.py`:
4. Change `test_main_rejects_unknown_command` to `assert ctl.main(["frobnicate"]) == 64`.
5. Add `test_main_rejects_missing_command` asserting `ctl.main([]) == 64`.
6. Leave `test_main_exit2_when_*` (3 tests) and `test_main_returns_int` unchanged (they still
   assert 2 / int).

### Success Criteria

- [ ] `ctl.main(["frobnicate"])` returns `64` (does NOT raise `SystemExit`).
- [ ] `ctl.main([])` returns `64` (proves `nargs='?'` is set; without it argparse raises `SystemExit(2)`).
- [ ] The three daemon-not-running paths still return `2` (XDG unset / socket absent / stale socket).
- [ ] Unknown/missing messages go to **stderr**; stdout stays reserved for the daemon result.
- [ ] ctl.py module docstring, `main()` docstring, and `_build_parser` description all document `64`.
- [ ] `pytest tests/test_voicectl.py -v` is fully green.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the three
research notes: the exact edit anchors (verbatim line ranges in `ctl.py`), the critical
`nargs='?'` gotcha (empirically verified), the `EX_USAGE=64` decision, the byte-exact test
rewrites, and the verified-working pytest commands (ruff/mypy are NOT installed here).

### Documentation & References

```yaml
# MUST READ — the ONE gotcha that determines success: removing `choices` alone leaves the
# missing-command case at argparse SystemExit(2). The OUTPUT requires "unknown/missing" both →64,
# so the positional MUST become nargs='?'. Empirically proven.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T4S1/research/exit_code_matrix.md
  why: "§ THE GOTCHA: argparse experiment proving no-choices+missing-arg -> SystemExit(2), but
        nargs='?' -> args.cmd=None (no SystemExit). § the exit-code matrix (0/1/2/64). § why a
        module constant _EX_USAGE=64 over importing os. § why NOT to catch SystemExit around
        parse_args (would swallow --help exit 0)."
  section: "ALL."

# MUST READ — exact test rewrites (byte-exact) + the docstring/README scope decision.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T4S1/research/test_and_docs_scope.md
  why: "§ the verbatim new body of test_main_rejects_unknown_command (assert 64, no SystemExit).
        § the new test_main_rejects_missing_command (the nargs='?' regression guard). § the THREE
        daemon-not-running tests that MUST stay 2. § DOCS: README is OUT of scope (grep shows NO
        exit-code table; changeset README sync is P1.M3.T1.S1); ctl.py docstrings are IN scope;
        PRD.md §4.8 is READ-ONLY (forbidden). § sibling disjointness (install.sh / feedback.py)."
  section: "ALL."

# MUST READ — pytest-only validation (ruff/mypy NOT installed; do NOT invent lint commands) +
# the 4 manual end-to-end exit-code checks that prove the contract.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T4S1/research/validation_approach.md
  why: "§ ruff/mypy absent -> validation is pytest only. § the 4 manual checks (frobnicate→64,
        no-args→64, status-up→0, status-down→2). § purity regression (no new heavy deps)."
  section: "ALL."

# MUST READ — the file being edited (verbatim source for the exact edit anchors).
- file: voice_typing/ctl.py
  why: "Edit anchors: (1) module exit-code table lines 6-12; (2) _build_parser lines 104-120
        (description + add_argument with choices=_COMMANDS); (3) main() docstring + parse_args
        lines 122-131. _COMMANDS is defined at line 33."
  pattern: "Single [project.scripts] entry 'voicectl = voice_typing.ctl:main' (pyproject.toml:17)
            wraps sys.exit(main()) — so the int main() returns IS the shell exit code. main()
            NEVER raises on the usage path post-change (returns int). All error messages already
            use 'print(..., file=sys.stderr)' — mirror that."
  gotcha: "argparse raises SystemExit(2) for a MISSING required positional even with choices
           removed (verified). MUST add nargs='?' or the no-args case stays SystemExit(2), breaking
           the OUTPUT 'missing command -> 64' requirement and the new test."

# MUST READ — the test file being edited (verbatim source for the test rewrites).
- file: tests/test_voicectl.py
  why: "test_main_rejects_unknown_command is lines 195-198 (the SystemExit(2) assertion to rewrite).
        The three exit-2 tests are lines 171-190 (KEEP). test_main_returns_int is line 224 (KEEP).
        The '# argparse / structural' section header is line 193 — place the new test there."
  pattern: "Tests call ctl.main([...]) directly and assert the returned int. capfd/capsys capture
            stderr/stdout. The pytest import stays (used elsewhere)."
  gotcha: "The new missing-command test must pass [] (empty list), NOT None — main() already
           defaults argv to None meaning sys.argv; to force 'no command' in-test you pass an
           EMPTY list so parse_args([]) runs with zero positionals."

# SHOULD READ — the PRD exit-code contract (READ-ONLY; do NOT edit PRD.md).
- docfile: PRD.md
  why: "§4.8 (PRD.md:230): 'exit code 0/1. ... If daemon not running: clear message + exit 2.'
        This is the contract 2 must keep meaning; the DOCS clause updates REFERENCES to §4.8 in
        docstrings, not the PRD itself."
  section: "§4.8 (around line 230)."

# CONTEXT — README is OUT of scope (no exit-code table exists to update).
- file: README.md
  why: "grep for exit codes in README returns NO match; the '## Logs, status, stopping' section
        (line 229+) shows example status output only. The conditional DOCS clause does not fire.
        Changeset-wide README sync is owned by P1.M3.T1.S1."
  critical: "Do NOT edit README.md in this task."

# CONTEXT — the in-flight sibling (disjoint files; no merge conflict).
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T3S1/PRP.md
  why: "P1.M2.T3.S1 edits install.sh ONLY. This task edits voice_typing/ctl.py + tests/test_voicectl.py
        ONLY. Zero file overlap."
```

### Current Codebase tree (run `tree` in the repo root, or `ls -1`)

```bash
$ ls -1   # files relevant to this task
voice_typing/ctl.py          # <-- EDIT: parser + main() validation + 3 docstrings
tests/test_voicectl.py       # <-- EDIT: 1 rewrite + 1 new test (3 exit-2 tests unchanged)
pyproject.toml               # (read-only ref: line 17 the [project.scripts] voicectl entry)
README.md                    # (out of scope)
PRD.md                       # (READ-ONLY)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/ctl.py          # MODIFIED: +_EX_USAGE constant; parser choices→nargs='?';
                             #   main() gains a usage-check early-return(64); 3 docstrings updated.
tests/test_voicectl.py       # MODIFIED: test_main_rejects_unknown_command→assert 64;
                             #   +test_main_rejects_missing_command; (3 exit-2 tests unchanged).
# No new files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: argparse raises SystemExit(2) for a MISSING required positional even after removing
# `choices`. Verified empirically:
#     no-choices argv=[]            -> SystemExit(2)     # STILL exits 2!
#     nargs='?' argv=[]             -> cmd=None          # no SystemExit
# So the positional MUST get nargs='?' (in addition to removing choices) or the no-command case
# stays SystemExit(2) and violates the OUTPUT "missing command -> 64" requirement. The new
# test_main_rejects_missing_command is the regression guard for exactly this.

# CRITICAL: the [project.scripts] `voicectl` entry (pyproject.toml:17) is
# `voicectl = "voice_typing.ctl:main"`, which the console-script wrapper invokes as
# sys.exit(main()). So the INT main() returns IS the shell $? — returning 64 propagates to the
# shell correctly with zero further plumbing. Do NOT add a sys.exit(64) anywhere.

# GOTCHA: args.cmd is now Optional[str] (None when no command). The local var annotation must
# become `cmd: str | None = args.cmd` and the `if cmd not in _COMMANDS` check runs BEFORE any
# downstream use (send_command/format_result expect a str). After the guard, cmd is narrowed to
# a valid _COMMANDS member, so the rest of main() is unchanged.

# GOTCHA: stdout is reserved for the daemon's human-readable result (format_result output).
# The usage-error messages MUST go to stderr (file=sys.stderr), matching every existing error
# message in ctl.py (lines 136, 142, 146). The manual Level-3 checks assert the message on stderr.

# GOTCHA: tests must pass an EMPTY list [] to simulate 'no command' (not None). main() defaults
# argv to None meaning "use sys.argv" — so ctl.main(None) in a test would pick up pytest's argv.
# ctl.main([]) forces parse_args([]) with zero positionals -> args.cmd is None -> return 64.

# GOTCHA: ruff/mypy are NOT installed in this repo (no [tool.ruff]/[tool.mypy] config; .venv
# lacks the binaries). Validation is pytest ONLY. Do NOT add ruff/mypy to the validation loop —
# they will fail "command not found". (The template's Level-1 ruff/mypy block does not apply here.)
```

## Implementation Blueprint

### Data models and structure

Not applicable — no data models. The only new symbol is a module-level int constant.

```python
# Add next to _COMMANDS (ctl.py ~line 33). BSD sysexits.h command-line usage error.
_EX_USAGE: int = 64
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/ctl.py — add _EX_USAGE constant
  - ANCHOR: the _COMMANDS line (ctl.py:33):
        _COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit")
  - ADD immediately AFTER it:
        # BSD sysexits.h: command-line usage error. Usage errors (unknown/missing command) exit 64
        # so exit 2 stays exclusive to "daemon not running" (PRD §4.8, bugfix Issue 7).
        _EX_USAGE: int = 64
  - NAMING: leading-underscore module-private (matches _COMMANDS idiom); UPPER_SNAKE (it's a constant).
  - WHY a constant not os.EX_USAGE: self-documenting, no new import; matches the file's idiom.
    (os.EX_USAGE == 64 is available on Linux; the constant simply fixes the value at 64 explicitly.)

Task 2: MODIFY voice_typing/ctl.py — _build_parser(): drop choices, add nargs='?', update docs
  - ANCHOR A (the _build_parser docstring, ctl.py:105):
        """argparse with one positional `cmd` over the 5 subcommands (Mode A doc surface)."""
    REPLACE with:
        """argparse with one optional positional `cmd`. choices validation is intentionally NOT done
        here — main() validates against _COMMANDS so usage errors map to exit 64 (EX_USAGE), not
        argparse's SystemExit(2) which would collide with the daemon-not-running code (PRD §4.8)."""
  - ANCHOR B (the description= string, ctl.py:110-112):
            "Control the voice-typing daemon. Connects to the control socket, sends one command, "
            "prints the result. Exits 0 on success, 1 on a logical failure, 2 if the daemon is not running."
    REPLACE with:
            "Control the voice-typing daemon. Connects to the control socket, sends one command, "
            "prints the result. Exits 0 on success, 1 on a logical failure, 2 if the daemon is not "
            "running, 64 on a usage error (unknown/missing command)."
  - ANCHOR C (the add_argument call, ctl.py:114-118):
        parser.add_argument(
            "cmd",
            choices=_COMMANDS,
            help="toggle | start | stop | status | quit",
        )
    REPLACE with (REMOVE choices=, ADD nargs="?"):
        parser.add_argument(
            "cmd",
            nargs="?",
            help="toggle | start | stop | status | quit",
        )
  - PRESERVE: prog=, epilog=, and the `return parser`. The help= string stays.

Task 3: MODIFY voice_typing/ctl.py — main(): usage check + docstring + type annotation
  - ANCHOR A (the main() docstring, ctl.py:124-129):
        """voicectl entry point: parse -> resolve socket -> send -> format -> print -> return exit code.

        Returns 0 (success), 1 (logical failure / protocol error), or 2 (daemon not running). NEVER
        raises: every path returns an int (the [project.scripts] wrapper does sys.exit(main())). argparse
        handles usage errors itself (SystemExit 2 on an unknown choice — a usage error, not a daemon
        status; G7).
        """
    REPLACE with:
        """voicectl entry point: parse -> validate command -> resolve socket -> send -> format -> print.

        Returns 0 (success), 1 (logical failure / protocol error), 2 (daemon not running), or
        64 (usage error — unknown/missing command, BSD EX_USAGE). NEVER raises on the usage path:
        every path returns an int (the [project.scripts] wrapper does sys.exit(main())). The command
        is validated HERE (not by argparse choices) so usage errors map to 64 while 2 stays exclusive
        to daemon-not-running (PRD §4.8, bugfix Issue 7). --help still exits 0 via argparse as usual.
        """
  - ANCHOR B (the parse_args + cmd line, ctl.py:130-131):
        args = _build_parser().parse_args(argv)
        cmd: str = args.cmd
    REPLACE with (annotation str|None + the usage guard):
        args = _build_parser().parse_args(argv)
        cmd: str | None = args.cmd          # None when no command given (positional is nargs='?')
        if cmd not in _COMMANDS:            # missing (None) or unknown string -> usage error
            if cmd is None:
                print(f"voicectl: a command is required; choose from {', '.join(_COMMANDS)}", file=sys.stderr)
            else:
                print(f"voicectl: invalid command {cmd!r}; choose from {', '.join(_COMMANDS)}", file=sys.stderr)
            return _EX_USAGE
  - PRESERVE: everything below (socket resolution returning 2, OSError->2, ValueError->1,
    format_result path). Those are reached only after the guard, where cmd is a valid command.
  - NOTE: the type annotation change str -> str|None is correct (args.cmd can be None now). mypy is
    not run in this repo, but the annotation should still be accurate.

Task 4: MODIFY voice_typing/ctl.py — module docstring exit-code table (lines 6-12)
  - ANCHOR:
        0  success            (daemon replied {"ok": true, ...})
        1  logical failure    (daemon replied {"ok": false, "error": ...})
        2  daemon not running (socket absent / connection refused / XDG_RUNTIME_DIR unset)
    REPLACE with (add a 64 line; clarify 2 is exclusive):
        0  success            (daemon replied {"ok": true, ...})
        1  logical failure    (daemon replied {"ok": false, "error": ...})
        2  daemon not running (socket absent / connection refused / XDG_RUNTIME_DIR unset) — EXCLUSIVE
        64 usage error        (unknown or missing command — BSD EX_USAGE)
  - PRESERVE: the rest of the module docstring (subcommand list, Usage line, stdlib-only note).
    The "Stdlib-only: argparse, json, socket, sys" line stays accurate (no new imports).

Task 5: MODIFY tests/test_voicectl.py — rewrite test_main_rejects_unknown_command (lines 195-198)
  - ANCHOR:
        def test_main_rejects_unknown_command():
            with pytest.raises(SystemExit) as exc:                 # argparse usage error (exit 2, G7)
                ctl.main(["frobnicate"])
            assert exc.value.code == 2
    REPLACE with:
        def test_main_rejects_unknown_command():
            # Unknown command is now validated in main() (not argparse), returning EX_USAGE (64)
            # so exit 2 is reserved exclusively for "daemon not running" (PRD §4.8, bugfix Issue 7).
            code = ctl.main(["frobnicate"])
            assert code == 64
  - NOTE: `pytest` import stays (used by other tests in the file). No import changes.

Task 6: ADD tests/test_voicectl.py — test_main_rejects_missing_command (the nargs='?' guard)
  - PLACE: immediately AFTER test_main_rejects_unknown_command (before line 201 blank / the
    test_ctl_module_present_and_imports_purity test), inside the "# argparse / structural" section.
  - ADD:
        def test_main_rejects_missing_command():
            # `voicectl` with no command is a usage error -> EX_USAGE (64), NOT argparse SystemExit(2).
            # Requires the positional to be nargs='?' so argparse does not raise SystemExit(2) for a
            # missing required arg (see PRP research/exit_code_matrix.md).
            code = ctl.main([])          # empty list == zero positionals (NOT None == sys.argv)
            assert code == 64
  - WHY this test exists: it is the regression guard for the Task-2 nargs='?' change. If someone
    later removes nargs='?', this test raises SystemExit(2) and fails loudly.

Task 7: VALIDATE (no file change — see Validation Loop)
  - .venv/bin/python -m pytest tests/test_voicectl.py -v
  - .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -v   (fast suite)
  - the 4 manual end-to-end exit-code checks (Level 3).
```

### Implementation Patterns & Key Details

```python
# PATTERN: the usage guard is the FIRST thing after parse_args — it must run before socket
# resolution so a typo never costs a connect attempt, and so a missing command never reaches
# code that assumes cmd is a str.
args = _build_parser().parse_args(argv)
cmd: str | None = args.cmd          # None when no command given (positional is nargs='?')
if cmd not in _COMMANDS:            # missing (None) OR unknown string -> both usage errors
    if cmd is None:
        print(f"voicectl: a command is required; choose from {', '.join(_COMMANDS)}", file=sys.stderr)
    else:
        print(f"voicectl: invalid command {cmd!r}; choose from {', '.join(_COMMANDS)}", file=sys.stderr)
    return _EX_USAGE
# ... existing socket resolution / send / format path unchanged below; cmd is now a valid command

# PATTERN: ', '.join(_COMMANDS) keeps the "choose from ..." list in sync with _COMMANDS — never
# hardcode "toggle, start, stop, status, quit" in the message (it would drift if _COMMANDS grows).

# PATTERN: every error in ctl.py goes to stderr (file=sys.stderr); stdout is the daemon result.
# The usage messages follow that. capfd (not capsys) is used by the existing exit-2 tests; the new
# tests assert the return code, and the manual checks assert the stderr text.

# GOTCHA: the [project.scripts] wrapper does sys.exit(main()) — so returning _EX_USAGE (64) IS the
# shell exit code. Do NOT add a separate sys.exit(64); do NOT print then sys.exit.
```

### Integration Points

```yaml
NO external integration points.
  - DATABASE: none.
  - CONFIG: none (config.toml untouched).
  - ROUTES: none (no socket/protocol change — the daemon never sees an invalid command; voicectl
            rejects it client-side before connecting).
  - DEPENDENCIES: none (stdlib only; no new imports — _EX_USAGE is a literal int constant).
  - CONSOLE ENTRY: pyproject.toml:17 `voicectl = "voice_typing.ctl:main"` is unchanged; sys.exit(main())
            already propagates the returned int to the shell.
  - README: OUT of scope (no exit-code table exists; changeset README sync is P1.M3.T1.S1).
  - PRD.md: READ-ONLY (forbidden); only docstring REFERENCES to §4.8 are updated.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# No ruff/mypy in this repo (not installed; no config). Use py_compile for a syntax check.
.venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl.py   # expect exit 0
# Expected: exit 0, no output. If a SyntaxError appears, READ it and fix before proceeding.
# (Do NOT run ruff/mypy — they are absent here; see research/validation_approach.md §Tooling.)
```

### Level 2: Unit Tests (the contract's mandated changes)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_voicectl.py -v
# Expected: ALL pass, including:
#   test_main_rejects_unknown_command   -> asserts code == 64 (was SystemExit(2))
#   test_main_rejects_missing_command   -> NEW, asserts code == 64
#   test_main_exit2_when_socket_absent  -> STILL code == 2
#   test_main_exit2_when_stale_socket_no_listener -> STILL code == 2
#   test_main_exit2_when_xdg_runtime_dir_unset    -> STILL code == 2
#   test_main_returns_int              -> STILL int (valid command, socket absent -> 2)
# If test_main_rejects_missing_command FAILS with SystemExit(2), you forgot nargs='?' (Task 2).
```

### Level 3: Integration Testing (System Validation — the real contract proof)

```bash
# Exercise the actual [project.scripts] console entry (sys.exit(main())) so $? is the shell code.
cd /home/dustin/projects/voice-typing

# (a) unknown command -> 64
.venv/bin/voicectl frobnicate; echo "rc=$?"
# Expected stderr: "voicectl: invalid command 'frobnicate'; choose from toggle, start, stop, status, quit"
# Expected: rc=64

# (b) missing command -> 64  (proves nargs='?' works end-to-end)
.venv/bin/voicectl; echo "rc=$?"
# Expected stderr: "voicectl: a command is required; choose from toggle, start, stop, status, quit"
# Expected: rc=64

# (c) valid command, daemon up -> 0
.venv/bin/voicectl status; echo "rc=$?"
# Expected: the status block on STDOUT, rc=0

# (d) valid command, daemon NOT running -> 2  (the exclusive-meaning path)
XDG_RUNTIME_DIR=/tmp/empty_no_daemon_here .venv/bin/voicectl status; echo "rc=$?"
# Expected stderr: "voicectl: daemon not running (...)", rc=2
# (a) vs (d) is the whole point: $? 64 == bad usage; $? 2 == daemon down.
```

### Level 4: Fast-suite + purity regression

```bash
# Fast suite (PRD Issue 4 path; should be fully green — this task touches no daemon/cuda code).
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: all pass (no "1 failed").

# Purity regression (nargs='?' + a manual check add no heavy deps).
.venv/bin/python -c "import sys, voice_typing.ctl; leaked=[m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]; print('pure' if not leaked else f'LEAKED {leaked}')"
# Expected: pure
```

## Final Validation Checklist

### Technical Validation

- [ ] `.venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl.py` exits 0.
- [ ] `pytest tests/test_voicectl.py -v` fully green (modified + new + 3 unchanged exit-2 tests).
- [ ] `pytest tests/ --ignore=tests/test_feed_audio.py -q` fully green (no order/isolation regression).

### Feature Validation

- [ ] `.venv/bin/voicectl frobnicate` → stderr message + `rc=64`.
- [ ] `.venv/bin/voicectl` (no command) → stderr message + `rc=64` (proves `nargs='?'`).
- [ ] `.venv/bin/voicectl status` (daemon up) → status block on stdout + `rc=0`.
- [ ] daemon-down `voicectl status` → stderr "not running" + `rc=2` (unchanged, EXCLUSIVE).
- [ ] Usage messages on **stderr**; stdout reserved for the daemon result.

### Code Quality Validation

- [ ] `choices=_COMMANDS` REMOVED; `nargs="?"` ADDED on the `cmd` positional.
- [ ] `_EX_USAGE: int = 64` constant added next to `_COMMANDS`; `main()` returns it (not a bare `64`).
- [ ] The "choose from …" text is `', '.join(_COMMANDS)` (not hardcoded).
- [ ] `cmd` local annotation is `str | None`; the guard runs before any downstream `str` use.
- [ ] No new imports (stdlib-only invariant preserved); no `sys.exit(64)` added.

### Documentation & Deployment

- [ ] Module docstring exit-code table lists `64 usage error`.
- [ ] `main()` docstring documents 64 and removes the now-false "argparse handles usage errors
      itself (SystemExit 2)" claim.
- [ ] `_build_parser` `description=` string and docstring document 64 / the manual-validation choice.
- [ ] README.md NOT edited (out of scope). PRD.md NOT edited (forbidden).

---

## Anti-Patterns to Avoid

- ❌ Don't remove `choices=_COMMANDS` **without** adding `nargs="?"` — a missing command would still
  raise argparse `SystemExit(2)`, violating the OUTPUT "missing command → 64" and failing the new
  `test_main_rejects_missing_command`. (Empirically verified; see research/exit_code_matrix.md.)
- ❌ Don't wrap `parse_args()` in `try/except SystemExit` to coerce the code — it would also swallow
  argparse's `--help` exit (0) and conflate missing-arg with internal errors. Use `nargs='?'` +
  manual check instead (what the PRD Issue 7 suggestion describes).
- ❌ Don't change the three `test_main_exit2_when_*` tests to expect 64 — they assert genuine
  daemon-not-running and MUST stay 2 (that is the entire point of reserving 2).
- ❌ Don't add `sys.exit(64)` anywhere — `main()` returns the int and the `[project.scripts]` wrapper
  does `sys.exit(main())`. Returning is the contract.
- ❌ Don't run `ruff`/`mypy` — neither is installed in this repo. Validation is pytest-only.
- ❌ Don't edit README.md (no exit-code table exists to update; changeset sync is P1.M3.T1.S1) or
  PRD.md (READ-ONLY / forbidden). Update only the ctl.py inline docstrings.
- ❌ Don't hardcode `"toggle, start, stop, status, quit"` in the usage message — use
  `', '.join(_COMMANDS)` so it cannot drift from `_COMMANDS`.
- ❌ Don't print the usage error to stdout — stdout is the daemon result; errors go to stderr
  (`file=sys.stderr`), matching every existing error message in ctl.py.

---

**Confidence Score: 9.5/10** for one-pass success. The change is small and fully specified:
verbatim edit anchors for all three ctl.py regions and both test changes, the critical
empirically-verified `nargs='?'` gotcha called out with its own regression test, a literal
`EX_USAGE=64` value, a clear exit-code matrix, and verified-working pytest + manual `$?` checks.
The only residual risk is an agent who skips Task 2's `nargs='?'` — but the new
`test_main_rejects_missing_command` and the manual Level-3(b) check will catch it immediately.
