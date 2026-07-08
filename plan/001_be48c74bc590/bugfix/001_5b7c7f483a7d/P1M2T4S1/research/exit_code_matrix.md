# Exit-code matrix + the `nargs='?'` gotcha (P1.M2.T4.S1)

## The decision: usage errors → 64 (BSD EX_USAGE), daemon-not-running → 2 (exclusive)

The PRD bugfix Issue 7 (§4.8) says exit 2 is reserved for "daemon not running" but argparse
also exits 2 for usage errors (`voicectl` with no command, `voicectl frobnicate`). This task
remaps usage errors to **64** (BSD `sysexits.h` `EX_USAGE`) so a caller checking `$?` can
distinguish a typo (64) from a down daemon (2).

### `EX_USAGE` constant: `os.EX_USAGE == 64`

```
$ .venv/bin/python -c "import os; print('EX_USAGE =', os.EX_USAGE, hasattr(os,'EX_USAGE'))"
EX_USAGE = 64 True
```

`os.EX_USAGE` is available on this host (Linux). Two options for the implementation:

1. **Define a module constant** `_EX_USAGE = 64  # BSD sysexits.h: command-line usage error`
   and `return _EX_USAGE`. Self-documenting, no new import, matches the existing
   `_COMMANDS` module-constant idiom in ctl.py. **RECOMMENDED.**
2. `import os` + `return os.EX_USAGE`. Also self-documenting but adds an import solely for
   the constant. Acceptable but option 1 is lighter and matches the file's idiom.

Either way the *value* is 64. The test asserts the literal `64` (not the constant) so the
choice is invisible to tests.

## ⚠️ THE GOTCHA: removing `choices` alone does NOT cover the missing-command case

The contract LOGIC step (a) says "Remove `choices=_COMMANDS`". That handles the *unknown*
command (`frobnicate`) — argparse no longer validates choices, so `frobnicate` reaches `main()`
where the manual `if args.cmd not in _COMMANDS` check returns 64. ✅

**BUT** the contract OUTPUT says "Usage errors (unknown/missing command) exit 64." A *missing*
command (`voicectl` with no args) is a missing **required positional**, and argparse raises
`SystemExit(2)` for that regardless of `choices`. Empirically verified:

```
$ python /tmp/argtest.py
no-choices argv=[]         -> SystemExit(2)      # ← STILL exits 2! choices removal insufficient
no-choices argv=['frobnicate'] -> cmd='frobnicate'
nargs='?' argv=[]          -> cmd=None           # ← no SystemExit; args.cmd is None
nargs='?' argv=['frobnicate'] -> cmd='frobnicate'
```

**Therefore the positional MUST be made optional with `nargs='?'`** so a missing command
yields `args.cmd = None` (argparse never raises), and the single manual check
`if args.cmd not in _COMMANDS:` then catches BOTH cases:

- `args.cmd is None` (missing) → None not in _COMMANDS → True → return 64
- `args.cmd == 'frobnicate'` (unknown) → not in _COMMANDS → True → return 64
- `args.cmd == 'toggle'` (valid) → in _COMMANDS → False → proceed normally

This is the single non-obvious detail the implementing agent must get right. Removing
`choices` without `nargs='?'` leaves `voicectl` (no args) → SystemExit(2), violating the
OUTPUT contract.

## Final exit-code matrix (post-change)

| exit | meaning                                       | produced by                                |
|-----:|-----------------------------------------------|--------------------------------------------|
| 0    | success (daemon replied ok:true)             | `format_result` → 0                        |
| 1    | logical failure / protocol error             | `format_result` → 1, or `send_command` ValueError |
| 2    | **daemon not running** (EXCLUSIVE)           | XDG_RUNTIME_DIR unset, connect OSError      |
| 64   | **usage error** (unknown/missing command)    | new manual check in `main()` (EX_USAGE)     |

## Distinct error messages for the two usage-error sub-cases

So the human reader sees which mistake they made:

- missing (`args.cmd is None`): `"voicectl: a command is required; choose from toggle, start, stop, status, quit"`
- unknown (`args.cmd` is a string not in _COMMANDS): `"voicectl: invalid command {cmd!r}; choose from toggle, start, stop, status, quit"`

Both go to **stderr** (`file=sys.stderr`) — stdout is reserved for the daemon's human-readable
result (matches every existing error message in ctl.py, e.g. lines 136, 142, 146). The command
list in the message is `", ".join(_COMMANDS)` (not hardcoded) so it stays in sync with
`_COMMANDS`.

## Why NOT catch SystemExit around parse_args

An alternative would be `try: parse_args() except SystemExit: return 64`. Rejected: it would
also swallow argparse's `--help` exit (code 0) and `--version`, and it conflates *missing*
required-arg with genuine argparse internal errors. The `nargs='?'` + manual-check approach is
cleaner, keeps `--help` working, and is exactly what the contract's "parse manually instead of
relying on argparse choices" PRD suggestion describes.
