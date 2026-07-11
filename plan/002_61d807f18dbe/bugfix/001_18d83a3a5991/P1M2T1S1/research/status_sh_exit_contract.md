# Research: status.sh exit-code contract fix + regression test (P1.M2.T1.S1)

Target: `voice_typing/status.sh` (bugfix Issue 2, Minor) — honor the script's own
documented "exit 0 (never abort)" contract by appending an explicit `exit 0`, soften
the overstated tmux rationale in the header comment, and add the first regression
test (`tests/test_status_sh.py`) proving exit 0 + empty stdout on missing/corrupt
state.json (plus a happy-path guard).

---

## 1. The defect (verified + reproduced)

`voice_typing/status.sh` is a POSIX `#!/bin/sh` script (39 lines, executable
`-rwxr-xr-x`) that jq-reads the daemon's `state.json` and prints a one-line
"🎤 <partial>" for tmux's `status-right`. Its header comment (lines 23-25)
promises:

> "NO `set -e`: a missing or malformed state.json must print an empty line with
> **exit 0 (never abort)** — otherwise tmux would show an error string in
> status-right."

The script correctly prints an empty line on failure (jq's stderr is sent to
`2>/dev/null` and the `// ""` defaults yield empty stdout), but it has **no
`exit` command anywhere** (grep-confirmed in the scout doc §1). Its exit code is
therefore **jq's exit code** — the last command (lines 34-39). Reproduced live:

```
$ XDG_RUNTIME_DIR=$(mktemp -d) voice_typing/status.sh; echo "exit=$?"   # no state file
exit=2                                            # jq: missing file
$ <corrupt JSON in state.json> voice_typing/status.sh; echo "exit=$?"
exit=5                                            # jq: corrupt JSON
```

Both violate the documented "exit 0" contract.

## 2. Why practical impact is low (but the contract still matters)

tmux's `#(...)` substitution captures **stdout** and **ignores the exit code**
(so status-right renders blank on failure regardless). Thus the documented use
case is unaffected. The defect is the **broken self-documented contract**: a
non-tmux caller (e.g. a wrapper script, a monitoring check, or a future UI) that
inspects `$?` would see 2/5 and misread a normal "daemon idle / not started"
state as an error. The fix makes the script behave as documented for EVERY
caller. (PRD Issue 2 / §4.6.)

The comment's "otherwise tmux would show an error string in status-right" claim
is **overstated** — tmux ignores exit codes in `#(...)`. The comment softening
corrects this to an accurate statement (tmux ignores the exit code; the exit 0
matters for non-tmux callers). This is the Mode A doc update (the header comment
IS the user-facing tmux-integration doc).

## 3. The fix (proven in a throwaway copy — did NOT touch the real script)

**(a) Append `exit 0` after the jq call (after line 39).** This zeroes the exit
code regardless of jq's result. Proven live via a `/tmp` copy of status.sh with
`exit 0` appended:

| scenario | before fix | after fix |
|---|---|---|
| missing state.json | exit=2, empty stdout | **exit=0**, empty stdout |
| corrupt JSON | exit=5, empty stdout | **exit=0**, empty stdout |
| listening + partial (happy) | exit=0, "🎤 hello world" | **exit=0**, "🎤 hello world" (no regression) |

The happy path still renders correctly — `exit 0` only changes the exit code
when jq failed; jq's stdout (the rendered line) still flows through unchanged on
success.

**(b) Soften the header comment (lines 23-25).** Replace the overstated "tmux
would show an error string" claim with an accurate statement: tmux's `#(...)`
ignores the exit code (so the empty stdout alone keeps status-right blank), but a
non-tmux caller checking `$?` would see jq's non-zero exit (2/5); the explicit
`exit 0` honors the contract for every caller.

An equivalent alternative (`jq ... || true`) was considered and **rejected**: the
item specifies `exit 0`, and an explicit terminal `exit 0` is clearer about the
"never abort" contract than a per-command `|| true` (and is robust to any future
command added above it).

## 4. status.sh structure (exact edit sites)

```sh
# line 1
#!/bin/sh
...
# lines 23-25  ← EDIT (b): soften the tmux rationale
# POSIX sh + jq only. NO `set -e`: a missing or malformed state.json must print an empty
# line with exit 0 (never abort) — otherwise tmux would show an error string in status-right.
# The `2>/dev/null` + the jq `// ""` defaults already guarantee empty-on-failure.
...
# line 27
STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"
...
# line 33
MAX="${VOICE_TYPING_STATUS_MAX:-60}"
# lines 34-39  ← the jq call (last command; its exit code propagates today)
jq -r --arg max "$MAX" '
  (if (.listening // false) then "🎤 " + (.partial // "") else "" end) as $line
  | if ($line | length) > ($max | tonumber)
    then $line[:(($max | tonumber) - 1)] + "…"
    else $line end
' "$STATE" 2>/dev/null
# (end of file — NO exit command)  ← EDIT (a): append `exit 0` here
```

- `STATE` resolves to `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json`
  — so a test controls the path by setting `XDG_RUNTIME_DIR`.
- jq exit codes: 0 = success; 2 = usage/file error (e.g. missing file); 4 = parse
  error in the jq program; 5 = invalid JSON input. (Hence 2 for missing, 5 for
  corrupt.)
- The script is executable (`-rwxr-xr-x`), shebang `#!/bin/sh` → `/bin/sh` is
  `bash` on this host (POSIX-compatible invocation). jq 1.8.1 is installed.

## 5. Test design (new file tests/test_status_sh.py — there is NO existing test)

The scout doc §7 confirms: `grep -rn 'status\.sh' tests/` finds only a comment in
`test_feedback.py:351` ("status.sh renders '🎤 <partial>'..."). No test asserts
status.sh's exit code or output. So this task **establishes the status.sh test**
(justified new pattern).

**Approach:** a pytest module that runs the REAL script via `subprocess.run` with
a controlled `XDG_RUNTIME_DIR` env (hermetic — does not touch the real
`/run/user/$(id -u)/voice-typing/`). This is a real-subprocess integration test,
DISTINCT from `test_typing_backends.py`'s pattern (which MOCKS `subprocess.run` to
capture argv without touching the OS). Mocking does not apply here — the point is
to exercise the real shell script + real jq.

**Cases (4):**
1. `test_status_sh_missing_state_file_exits_zero_with_empty_stdout` — no state
   file → exit 0 + empty stdout (the Issue 2 regression: was exit 2).
2. `test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout` — invalid
   JSON → exit 0 + empty stdout (was exit 5).
3. `test_status_sh_listening_renders_partial_and_exits_zero` — happy path:
   `{"listening": true, "partial": "hello world"}` → "🎤 hello world" + exit 0
   (regression guard that `exit 0` does NOT suppress normal output).
4. `test_status_sh_not_listening_renders_empty_and_exits_zero` — idle:
   `{"listening": false, ...}` → empty + exit 0 (the common idle case).

**Conventions mirrored:**
- `from __future__ import annotations` (every test module in this repo).
- Module-relative script path: `Path(__file__).resolve().parent.parent / "voice_typing" / "status.sh"` (CWD-independent; same idiom as `config.py`'s `_repo_config_path` and `test_config_repo_default.py`).
- `tmp_path` (pytest builtin) for the temp `XDG_RUNTIME_DIR` (auto-cleaned).
- `env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}` — carry the full environ so `jq`/`id`/`sh` stay on `PATH` (critical: a bare `{"XDG_RUNTIME_DIR": ...}` would lose PATH and the script would fail to find jq).
- `subprocess.run([...], capture_output=True, text=True, timeout=10)`.
- pytest 9.1.1 is the project's runner (`[dependency-groups] dev = ["pytest>=9.1.1"]`); NO ruff/mypy in pyproject.

## 6. Scope boundaries (do NOT cross)

- **Do NOT touch `launch_daemon.sh`, `install.sh`, `systemd/voice-typing.service`, or `daemon.py`.** The parallel P1.M1.T2.S1 edits `install.sh` + `tests/test_systemd_unit.py` (the offline journal grep + summary). No file overlap with status.sh or the new test.
- **Do NOT touch `test_feedback.py`** (it has a passing test that references status.sh in a comment only — unrelated; the Feedback state.json writer is a different concern).
- **Do NOT change status.sh's rendering logic** (the jq program). The ONLY edits are: (a) append `exit 0`, (b) soften the header comment. The jq `// ""` defaults + `2>/dev/null` already produce empty stdout on failure; this fix only zeroes the exit code.
- **Do NOT add `set -e`.** The contract is "never abort" — `set -e` would abort on jq's failure. The fix is the opposite: an explicit `exit 0` that masks jq's non-zero.
- **Do NOT use `jq ... || true` instead of `exit 0`** — the item specifies `exit 0`; a terminal `exit 0` is clearer and robust to future commands added above it.
- **Test-only deps:** the new test uses only stdlib (`os`, `subprocess`, `pathlib`) + pytest. No new dependencies.

## 7. Validation strategy

1. **Static:** `sh -n voice_typing/status.sh` (POSIX syntax check) exits 0; status.sh ends with a line `exit 0`; the old "otherwise tmux would show an error string" phrase is GONE; the new "IGNORES the exit code" / "non-tmux caller" wording is present.
2. **New test:** `.venv/bin/python -m pytest tests/test_status_sh.py -v` → 4 passed.
3. **Manual contract proof (the documented repro):** `XDG_RUNTIME_DIR=$(mktemp -d) voice_typing/status.sh; echo $?` → `0` (was `2`); corrupt JSON → `0` (was `5`).
4. **No regression:** full fast suite `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (test_feed_audio.py is the heavy GPU/offline suite; the new test is fast/subprocess-only).
5. **Scope guard:** `git status --short` shows ONLY `voice_typing/status.sh` + `tests/test_status_sh.py`.
