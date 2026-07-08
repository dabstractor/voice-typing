# Validation approach (P1.M2.T4.S1)

## Tooling present

- **pytest**: installed (pyproject dev dep `pytest>=9.1.1`). Invoke via
  `.venv/bin/python -m pytest ...` (matches the test-file docstring and PRD Issue 4).
- **ruff / mypy**: NOT installed in `.venv`. The repo has no `[tool.ruff]`/`[tool.mypy]`
  config in pyproject.toml. → **No lint/type gate for this task.** Validation is pytest-only.
  Do NOT invent `ruff`/`mypy` commands (they will fail with "command not found").

## Level 1: targeted unit tests (the contract's mandated changes)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_voicectl.py -v
```
Expected: ALL pass, including:
- `test_main_rejects_unknown_command` → now asserts `code == 64` (not SystemExit).
- `test_main_rejects_missing_command` → new, asserts `code == 64` (the nargs='?' guard).
- `test_main_exit2_when_socket_absent` / `_stale_socket_no_listener` / `_xdg_runtime_dir_unset`
  → STILL assert `code == 2` (unchanged).
- `test_main_returns_int` → still 2/int (valid command, socket absent).

## Level 2: fast suite (PRD Issue 4 path — order-independence)

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -v
```
Expected: green (no `1 failed`). The order-independence fix (P1.M2.T1) is already landed, so
this should be fully passing both before and after this change. This task does not touch
daemon/cuda code, so it cannot reintroduce the sys.modules pollution.

## Level 3: manual end-to-end exit-code check (the real contract proof)

These exercise the actual `[project.scripts]` console entry (`voicectl =
"voice_typing.ctl:main"`, which wraps `sys.exit(main())`), confirming the shell sees the right
`$?`. The live systemd daemon is active (pid per PRD Overview), so the daemon-down case is
simulated by pointing XDG_RUNTIME_DIR at an empty dir.

```bash
# (a) unknown command -> 64
.venv/bin/voicectl frobnicate; echo "rc=$?"
# Expected: "voicectl: invalid command 'frobnicate'; choose from toggle, start, stop, status, quit" on stderr, rc=64

# (b) missing command -> 64
.venv/bin/voicectl; echo "rc=$?"
# Expected: "voicectl: a command is required; choose from toggle, start, stop, status, quit" on stderr, rc=64

# (c) valid command, daemon up -> 0 (status prints to stdout)
.venv/bin/voicectl status; echo "rc=$?"
# Expected: the status block on stdout, rc=0

# (d) valid command, daemon NOT running -> 2 (the exclusive-meaning path)
XDG_RUNTIME_DIR=/tmp/empty_no_daemon_here .venv/bin/voicectl status; echo "rc=$?"
# Expected: "voicectl: daemon not running (...)" on stderr, rc=2
```

(a) vs (d) is the whole point of the task: a script can now do
`if [ $? -eq 2 ]; then echo daemon-down; elif [ $? -eq 64 ]; then echo bad-usage; fi`.

## Level 4: purity regression (defense-in-depth)

```bash
.venv/bin/python -c "import sys, voice_typing.ctl; leaked=[m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]; print('pure' if not leaked else f'LEAKED {leaked}')"
# Expected: pure   (nargs='?' + a manual check adds no heavy deps)
```

## What NOT to do

- Do NOT run `ruff`/`mypy` (not installed; will error).
- Do NOT edit README.md (out of scope — see research/test_and_docs_scope.md).
- Do NOT modify PRD.md (READ-ONLY, forbidden).
- Do NOT "fix" the three daemon-not-running tests to return 64 — they MUST stay 2.
