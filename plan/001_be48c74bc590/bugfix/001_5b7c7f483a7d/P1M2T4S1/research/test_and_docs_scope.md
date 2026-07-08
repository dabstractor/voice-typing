# Test changes + DOCS scope (P1.M2.T4.S1)

## Test changes in tests/test_voicectl.py

### 1. MODIFY `test_main_rejects_unknown_command` (lines 195-198) — the contract mandate

Current (asserts argparse SystemExit(2)):
```python
def test_main_rejects_unknown_command():
    with pytest.raises(SystemExit) as exc:                 # argparse usage error (exit 2, G7)
        ctl.main(["frobnicate"])
    assert exc.value.code == 2
```

New (asserts returned int 64, no SystemExit):
```python
def test_main_rejects_unknown_command():
    # Unknown command is now validated in main() (not argparse), returning EX_USAGE (64)
    # so exit 2 is reserved exclusively for "daemon not running" (bugfix Issue 7).
    code = ctl.main(["frobnicate"])
    assert code == 64
```

This is a direct call returning an int — `main()` now returns 64 instead of raising SystemExit.
Note: the `pytest` import is STILL used elsewhere (no import to remove).

### 2. ADD a missing-command test (aligned with OUTPUT "unknown/missing command")

```python
def test_main_rejects_missing_command():
    # `voicectl` with no command is a usage error -> EX_USAGE (64), NOT argparse SystemExit(2).
    # Requires the positional to be nargs='?' so argparse does not raise SystemExit(2) for a
    # missing required arg (see research/exit_code_matrix.md).
    code = ctl.main([])
    assert code == 64
```

PLACE near the existing `test_main_rejects_unknown_command` (the "# argparse / structural"
section, after line 198). This is the regression guard for the `nargs='?'` gotcha: without
`nargs='?'`, `ctl.main([])` raises SystemExit(2) and this test fails loudly.

### 3. KEEP UNCHANGED — the three daemon-not-running tests (lines 171-190)

- `test_main_exit2_when_socket_absent`          → `assert code == 2 and "not running" in err`
- `test_main_exit2_when_stale_socket_no_listener` → `assert code == 2 and "not running" in ...err`
- `test_main_exit2_when_xdg_runtime_dir_unset`  → `assert code == 2 and "not running" in ...err`

These MUST stay 2. They are unaffected by this change (the manual usage check is before socket
resolution; these tests pass a valid command so they skip it). After the change, re-run them to
confirm they still assert 2.

### 4. KEEP UNCHANGED — `test_main_returns_int` (line 224)

Calls `ctl.main(["status"])` with socket absent → returns 2 (int). Still valid; `status` is a
valid command so the usage check is skipped.

### 5. No effect on `test_ctl_module_present_and_imports_pure`

This task adds `nargs='?'` + a manual check + docstring edits to ctl.py — still stdlib-only
(argparse/json/socket/sys, no new heavy deps). The purity probe remains green.

## DOCS scope: README OUT; ctl.py docstrings IN

### README.md is OUT of scope

The DOCS clause is conditional: "Mode A — **If** README.md or any doc lists voicectl exit
codes, update...". README.md does NOT list voicectl exit codes anywhere:

- `grep -n "exit code\|exit 0\|exit 1\|exit 2\|code 0\|code 1\|code 2" README.md` → **no match**.
- The "## Logs, status, stopping" section (README.md:229+) shows example `voicectl status`
  OUTPUT only; no exit-code table.
- The conditional clause therefore does NOT fire for README. Additionally, changeset-wide
  README sync is owned by **P1.M3.T1.S1** (per the plan). Do NOT edit README.md here.

### ctl.py inline docstrings are IN scope

ctl.py itself lists exit codes in TWO docstrings — these MUST be updated (DOCS clause:
"Update the PRD §4.8 reference in any inline docstring"):

1. **Module docstring (ctl.py:6-12)** — the exit-code table. Currently lists 0/1/2. ADD a 64
   line and clarify 2 is exclusively daemon-not-running:
   ```
   0   success            (daemon replied {"ok": true, ...})
   1   logical failure    (daemon replied {"ok": false, "error": ...})
   2   daemon not running (socket absent / connection refused / XDG_RUNTIME_DIR unset)
   64  usage error        (unknown or missing command — BSD EX_USAGE)
   ```

2. **`main()` docstring (ctl.py:124-129)** — currently says "argparse handles usage errors
   itself (SystemExit 2 on an unknown choice — a usage error, not a daemon status; G7)."
   This is now FALSE (we parse manually). Replace with the new behavior: main() validates the
   command itself and returns 64 (EX_USAGE) for unknown/missing commands; 2 stays exclusive to
   daemon-not-running.

3. **`_build_parser()` argparse `description=` (ctl.py:110-113)** — currently "Exits 0 on
   success, 1 on a logical failure, 2 if the daemon is not running." Append "64 on a usage
   error (unknown/missing command).". Also the `_build_parser` docstring line "over the 5
   subcommands (Mode A doc surface)" can stay; note `choices` is intentionally removed (the
   parser no longer restricts `cmd` — `main()` validates against `_COMMANDS`).

### PRD.md §4.8 is READ-ONLY

PRD.md:230 reads "exit code 0/1. ... If daemon not running: clear message + exit 2." This is the
product doc owned by humans. The DOCS clause says update *references to* PRD §4.8 in docstrings,
NOT the PRD itself. Do NOT modify PRD.md (it is on the FORBIDDEN list).

## Sibling disjointness (parallel-execution safety)

This task edits ONLY `voice_typing/ctl.py` and `tests/test_voicectl.py`.
- P1.M2.T3.S1 (in flight) edits `install.sh` only. Zero overlap.
- P1.M2.T2.S2 (completed) edited `feedback.py` / `typing_backends.py`. Zero overlap.
No merge conflict possible.
