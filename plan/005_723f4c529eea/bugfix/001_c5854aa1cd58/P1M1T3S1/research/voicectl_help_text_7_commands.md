# Research: voicectl help-text surfaces all 7 commands (bugfix Issue 3) — VERIFIED

**Status:** VERIFIED against the live `voice_typing/ctl.py` + `tests/test_voicectl.py` on this machine.
This note is the load-bearing evidence for `P1M1T3S1/PRP.md`.
**Task:** bugfix Issue 3 (Minor) — `voicectl --help` + CLI help text omit the lite commands (list 5 of 7).

---

## 0. THE DEFECT (empirically confirmed)

`_COMMANDS` (ctl.py:35) is the canonical 7-command set:
```python
_COMMANDS = ("toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite")
```

But `voicectl --help` renders only **5** (verified by running `ctl._build_parser().format_help()`):
```
positional arguments:
  cmd         toggle | start | stop | status | quit          ← MISSING toggle-lite, start-lite
...
subcommands: toggle, start, stop, status, quit (see the ...) ← MISSING toggle-lite, start-lite
```

Meanwhile `voicectl` (no args) correctly prints **all 7** (ctl.py:179, via `', '.join(_COMMANDS)`):
```
voicectl: a command is required; choose from toggle, start, stop, status, quit, toggle-lite, start-lite
```
So `--help` HIDES lite mode while the no-arg path REVEALS it — internally inconsistent (and contradicts PRD §4.8's 7-command spec). The lite commands WORK (main() routes them at ctl.py:197) — only the help text is stale.

---

## 1. THE 4 EDIT SITES (verbatim old → new; all in `voice_typing/ctl.py`)

**(a) Module docstring Usage line (ctl.py:20)**
```
OLD: Usage:  voicectl <toggle|start|stop|status|quit>
NEW: Usage:  voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>
```

**(b) Module docstring subcommand block — append two lines after the `quit` line (after ctl.py:18)**
Current block (lines 14-18):
```
    toggle   arm/disarm the mic (flip the listening gate)
    start    arm the mic (start listening)
    stop     disarm the mic (stop listening)
    status   pretty-print listening + partial + last final + uptime + device + loaded models
    quit     request a clean daemon shutdown (releases GPU workers)
```
Append (the lite names are 10-12 chars, so they get their own 2-3 space padding, not the column-13
alignment of the ≤6-char normal names — matches the contract's example):
```
    toggle-lite  arm/disarm in LITE mode (single small model — PRD §4.2ter)
    start-lite   arm in LITE mode (start listening with the small model only)
```

**(c) argparse epilog (ctl.py:156)**
```
OLD: epilog="subcommands: toggle, start, stop, status, quit  (see the project README for the full usage table)",
NEW: epilog="subcommands: toggle, start, stop, status, quit, toggle-lite, start-lite  (see the project README for the full usage table)",
```

**(d) positional `cmd` help (ctl.py:161)**
```
OLD: help="toggle | start | stop | status | quit",
NEW: help="toggle | start | stop | status | quit | toggle-lite | start-lite",
```

**NOT edited (already correct — the consistency reference):** main()'s no-arg error path (ctl.py:179/181)
prints `', '.join(_COMMANDS)` = all 7. No change to main(), _COMMANDS, format_result, or send_command.

---

## 2. WHY THIS SLIPPED PAST TESTS (the gap the new test closes)

The existing test suite asserts the lite commands are in `_COMMANDS`
(`test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` @test_voicectl.py:75 — asserts
`toggle-lite`/`start-lite` ⊆ `_COMMANDS`). But NO test asserts the HELP STRINGS list them. argparse's
epilog/help are plain string literals — not derived from `_COMMANDS` — so they can drift silently.
(config drift-guards parse via `tomllib`, irrelevant here; the help strings are in ctl.py source.) The
new TDD test reads `parser.format_help()` + `ctl.__doc__` as TEXT and asserts all 7 appear — closing the
gap permanently (any future removal of a lite command from the help text turns the test RED).

---

## 3. THE TDD TEST (placement + design) — verified hermetic

**Placement:** a new banner section at the END of `tests/test_voicectl.py` (matches the file's
convention — each subtask adds its own banner section, e.g. "P1.M2.T1.S2 — loading models… hint" @263).

**Design:** `_build_parser()` exists (ctl.py:145) and returns an `ArgumentParser` whose
`.format_help()` renders BOTH the positional help AND the epilog (verified empirically). So one
`format_help()` call covers epilog + positional. The module docstring is `ctl.__doc__`.

```python
# ===========================================================================
# P1.M1.T3.S1 — help text surfaces all 7 commands (bugfix Issue 3)
# (argparse format_help() + the module docstring must list toggle-lite/start-lite,
#  matching _COMMANDS + PRD §4.8 + the no-arg error path. Before the fix --help showed
#  only 5 while `voicectl` (no args) showed 7 — internally inconsistent. TDD red→green.)
# ===========================================================================
def test_help_surfaces_list_all_seven_commands():
    """All 7 commands appear in every help surface (PRD §4.8; bugfix Issue 3)."""
    seven = {"toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite"}
    assert set(ctl._COMMANDS) == seven, sorted(ctl._COMMANDS)   # _COMMANDS = source of truth
    # (1) argparse --help (covers BOTH the positional help AND the epilog via format_help):
    help_text = ctl._build_parser().format_help()
    for cmd in seven:
        assert cmd in help_text, f"{cmd!r} missing from --help:\n{help_text}"
    # (2) module docstring (Usage line + subcommand block):
    assert ctl.__doc__ is not None
    for cmd in seven:
        assert cmd in ctl.__doc__, f"{cmd!r} missing from the ctl module docstring"
```

**TDD red→green (verified):** BEFORE the ctl.py fix, `toggle-lite`/`start-lite` are absent from both
`format_help()` and `ctl.__doc__` → the test FAILS (RED). AFTER the 4 edits, both surfaces contain all
7 → the test PASSES (GREEN). The `start`/`toggle` assertions are trivially satisfied (substrings of
`start-lite`/`toggle-lite`), so the LOAD-BEARING discriminators are the two lite commands — exactly the
defect. No external services, no socket, no daemon — pure stdlib argparse formatting.

---

## 4. PARALLEL-TASK AWARENESS (no conflict)

- **P1.M1.T2.S1** (in parallel): edits `config.toml` (line 34, `SUPER+ALT+F`→`D`) +
  `tests/test_config_repo_default.py`. T3.S1 edits `voice_typing/ctl.py` + `tests/test_voicectl.py`.
  **DISJOINT files** — no line-level conflict. Both are Mode-A doc fixes with a TDD static-text test.
- **P1.M1.T4.S1** (planned, later): edits `voice_typing/daemon.py` `toggle_lite` docstring
  (`pressing F`→`pressing D`). Also disjoint from ctl.py. No conflict.
- **P1.M1.T1.S1** (COMPLETE): install.sh onboarding line. Already landed. No overlap.
- T3.S1 does NOT touch main(), _COMMANDS, format_result, send_command, config.toml, daemon.py, README,
  hypr-binds.conf, or install.sh.

---

## 5. SCOPE DISCIPLINE (the contract's negative constraints)

- DO NOT change `_COMMANDS`, `main()`, `format_result()`, `send_command()`, or any runtime behavior —
  the lite commands ALREADY work; only the help/docstring TEXT is stale.
- DO NOT derive the epilog/help from `_COMMANDS` at runtime (e.g. `f"subcommands: {', '.join(_COMMANDS)}"`).
  The contract specifies appending the literal tokens to the existing strings (keeps the curated
  ordering + the "see the project README" suffix). A runtime-derivation would be a larger refactor
  (out of Mode-A scope) and would reorder the commands.
- DO NOT touch config.toml (T2.S1), daemon.py (T4.S1), README (T5.S1), install.sh (T1.S1-complete),
  hypr-binds.conf (correct), or any other file. Only `voice_typing/ctl.py` + `tests/test_voicectl.py`.
- The two lite subcommand-block lines should reference PRD §4.2ter (the lite-mode spec) — matches the
  contract's example wording.
