# PRP — P1.M2.T1.S1: Add exit 0 + soften comment + regression test for status.sh

## Goal

**Feature Goal**: Fix bugfix **Issue 2** (Minor): make `voice_typing/status.sh` honor its own documented "exit 0 (never abort)" contract by appending an explicit `exit 0` after the `jq` call (so the script's exit code is no longer jq's 2/5 on missing/corrupt `state.json`), soften the header comment's overstated tmux rationale to an accurate statement, and add the **first** regression test (`tests/test_status_sh.py`) proving exit 0 + empty stdout on missing/corrupt state.json plus a happy-path guard. The defect is a broken self-documented contract (practical impact on tmux is negligible — tmux's `#(...)` ignores exit codes — but a non-tmux caller checking `$?` is misled).

**Deliverable** (2 files; one tiny source patch + one new test file):
1. `voice_typing/status.sh` — two edits: (a) append `exit 0` (with a brief explaining comment) after the `jq` call at line 39; (b) soften the header comment at lines 23-25 (correct the "otherwise tmux would show an error string" claim — tmux ignores exit codes in `#(...)`; the exit 0 matters for non-tmux callers). Verbatim oldText→newText in Implementation Blueprint → Task 1.
2. `tests/test_status_sh.py` — NEW pytest module (4 tests) running the REAL script via `subprocess.run` with a controlled `XDG_RUNTIME_DIR`, asserting exit 0 + empty stdout for missing/corrupt state.json, and a happy-path regression guard. Verbatim source in Implementation Blueprint → Task 2.

**Success Definition**:
- (a) `voice_typing/status.sh` ends with an explicit `exit 0`; `sh -n voice_typing/status.sh` exits 0 (POSIX syntax clean).
- (b) The documented contract is honored: `XDG_RUNTIME_DIR=$(mktemp -d) voice_typing/status.sh; echo $?` → **`0`** (currently `2`); corrupt JSON → **`0`** (currently `5`). stdout stays empty on both failures (unchanged).
- (c) The happy path still renders: `{"listening": true, "partial": "hello world"}` → stdout `🎤 hello world`, exit 0 (no regression from `exit 0`).
- (d) The header comment no longer claims "tmux would show an error string" (overstated); it accurately states tmux's `#(...)` ignores exit codes and the `exit 0` covers non-tmux callers.
- (e) `.venv/bin/python -m pytest tests/test_status_sh.py -v` → 4 passed.
- (f) Full fast suite `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- (g) No out-of-scope files touched (no `launch_daemon.sh`, `install.sh`, `daemon.py`, `test_feedback.py`, `config`, README — those are other tasks'/S1's domain).

## User Persona

Not applicable (no end-user surface change — the script's observable stdout is unchanged; only its exit code becomes correct). DOCS: **Mode A** — the `status.sh` header comment IS the user-facing tmux-integration doc; the comment softening (step b) updates that doc in-place for accuracy. No external docs files.

## Why

- **The contract is documented and broken.** The script's own header promises "exit 0 (never abort)" for missing/malformed state.json, but the script has no `exit` command — its exit code is jq's (2 = missing file, 5 = corrupt JSON). A self-documented contract that silently fails is worse than no contract: a maintainer or wrapper script reading the comment and trusting `$? == 0` is misled. (bugfix Issue 2; PRD §4.6.)
- **Cheap, isolated, contract-honoring.** A one-line `exit 0` (proven in a throwaway copy) zeroes the exit code for every caller. It changes nothing about the (already-correct) empty-on-failure stdout; it only fixes the exit code.
- **First test for status.sh.** There is currently NO test asserting status.sh's exit code or output (scout doc §7: only a comment reference in `test_feedback.py:351`). The regression test locks the contract so a future edit that removes `exit 0` (or adds `set -e`) is caught immediately in the fast pytest suite.
- **Comment accuracy (Mode A).** The "otherwise tmux would show an error string in status-right" claim is overstated — tmux's `#(...)` ignores exit codes. Correcting it prevents a future maintainer from "fixing" the wrong thing or from reasoning about a non-existent failure mode.

## What

Two coordinated edits to `voice_typing/status.sh` + one new pytest module:

1. **Append `exit 0`** after the `jq` call (after line 39), with a short comment explaining why (jq exits non-zero on missing/corrupt; this zeroes the exit code to honor the contract).
2. **Soften the header comment** (lines 23-25): replace the overstated "otherwise tmux would show an error string" with an accurate statement (tmux's `#(...)` ignores exit codes; the `exit 0` matters for non-tmux callers checking `$?`).
3. **New `tests/test_status_sh.py`** (4 tests): missing-file → exit 0 + empty stdout; corrupt-JSON → exit 0 + empty stdout; listening+partial → "🎤 hello world" + exit 0; idle → empty + exit 0.

### Success Criteria

- [ ] `voice_typing/status.sh` ends with a line `exit 0`; `sh -n voice_typing/status.sh` exits 0.
- [ ] Exactly one `exit 0` in status.sh (a terminal exit, not `|| true`).
- [ ] `XDG_RUNTIME_DIR=$(mktemp -d) voice_typing/status.sh; echo $?` → `0` (was `2`).
- [ ] Corrupt JSON in state.json → `exit 0` + empty stdout (was `5`).
- [ ] Happy path (`listening: true`) still prints `🎤 <partial>` + exit 0 (no regression).
- [ ] The old comment phrase "otherwise tmux would show an error string in status-right" is GONE; the new comment states tmux's `#(...)` ignores exit codes and the `exit 0` covers non-tmux callers.
- [ ] `.venv/bin/python -m pytest tests/test_status_sh.py -v` → 4 passed.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] `git status --short` == `voice_typing/status.sh` (modified) + `tests/test_status_sh.py` (new) — nothing else.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the referenced research. The defect is reproduced live (exit 2/5 vs documented exit 0), the fix is proven live in a throwaway copy (exit 0 on both failure cases + happy path still renders), both status.sh edits are given as exact oldText→newText against the current file, and the verbatim 4-test source is provided. The test design (real subprocess + controlled `XDG_RUNTIME_DIR`, carrying full environ for PATH) is documented against the codebase conventions.

### Documentation & References

```yaml
# MUST READ — the defect, root cause, proven fix, exact edit sites, test design, scope (load-bearing)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M2T1S1/research/status_sh_exit_contract.md
  why: "§1 reproduces the bug (exit 2 missing / exit 5 corrupt). §2 why impact is low (tmux ignores exit codes)
        but the contract still matters. §3 the fix PROVEN in a throwaway copy (exit 0 on both failures + happy
        path still renders). §4 exact edit sites (comment lines 23-25, jq call ends line 39, no exit anywhere).
        §5 test design (new file; real subprocess + controlled XDG_RUNTIME_DIR; 4 cases; carry full environ for
        PATH so jq/id/sh resolve). §6 scope boundaries (no launch_daemon.sh/install.sh/daemon.py/test_feedback.py).
        §7 validation strategy."
  section: "§3 (proven fix) and §5 (test design — especially carry full environ for PATH) are load-bearing."

# MUST READ — the script under test (the exact text the edits match against)
- file: voice_typing/status.sh
  why: "POSIX #!/bin/sh, 39 lines, executable. Header comment lines 23-25 (the contract + the overstated tmux
        claim). STATE line 27: ${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json (a test controls
        the path via XDG_RUNTIME_DIR). The jq call is the LAST command (lines 34-39), NO exit anywhere -> exit
        code = jq's (2/5). Edit (a) appends exit 0 after line 39; edit (b) rewrites lines 23-25."
  critical: "The ONLY edits are append-exit-0 and soften-comment. Do NOT touch the jq program (the // \"\" defaults
             + 2>/dev/null already produce empty-on-failure stdout); do NOT add set -e (the contract is never-abort);
             do NOT use `jq ... || true` (item specifies exit 0). jq exit codes: 2=missing file, 5=corrupt JSON."

# THE DEFECT (Issue 2) + the mandated fix
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/prd_snapshot.md
  why: "§2.3 Issue 2: 'end status.sh with an explicit exit 0 after the jq call (or jq ... || true), so the script
        honors its documented exit 0 (never abort) contract. Optionally also soften the comment's otherwise-tmux-
        would-show-an-error-string claim (tmux ignores exit codes in #(...)).' This PRP implements exactly that
        (choosing exit 0 over || true per the item spec)."
  section: "Issue 2 (Minor)."

# THE SCOUT (verified facts: no exit, no set -e, no test; jq exit codes; edit anchor)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/scout_launch_status_install.md
  why: "§1: 'No set -e, no exit command anywhere. Last line is the jq call (lines 34-39), NO trailing exit 0. Exit
        code = jq exit code: 2 (missing), 5 (corrupt). Fix anchor: append exit 0 after line 39.' §7: 'Existing
        tests for status.sh — NONE. grep -rn status.sh tests/ -> only a comment in test_feedback.py:351. A new
        test is needed.' Confirms the edit site + justifies the new test file."

# PARALLEL CONTEXT — P1.M1.T2.S1 (install.sh offline grep; NO overlap)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M1T2S1/PRP.md
  why: "T2.S1 edits install.sh + tests/test_systemd_unit.py (the post-restart offline journal grep + summary line).
        It does NOT touch status.sh or any test_status_sh.py. No file overlap -> safe parallel landing. The current
        status.sh/launch_daemon.sh state already reflects T1.S1 (offline exports landed); this task is independent."
  critical: "Do NOT edit install.sh or tests/test_systemd_unit.py (T2.S1 owns them). Only status.sh + tests/test_status_sh.py."

# THE COMMENT-ONLY REFERENCE in the existing suite (do NOT edit; context only)
- file: tests/test_feedback.py
  why: "Line ~351 has a docstring mentioning status.sh ('status.sh renders 🎤 <partial>...') in a passing Feedback
        test about clearing stale partials. It is NOT a status.sh exit-code test and must NOT be edited. The new
        tests/test_status_sh.py is the dedicated status.sh regression suite."
  critical: "Do NOT modify test_feedback.py — different concern (the state.json WRITER), no overlap."

# CODEBASE TEST CONVENTIONS (mirror these in the new test)
- file: tests/test_config_repo_default.py
  why: "Shows the module-relative repo-path idiom: Path(__file__).resolve().parent.parent / 'config.toml' (CWD-
        independent). The new test uses the same idiom to locate voice_typing/status.sh. Also confirms pytest style
        (no ruff/mypy) + `from __future__ import annotations` at the top of every test module."
  pattern: "Path(__file__).resolve().parent.parent / 'voice_typing' / 'status.sh' for the script under test."
```

### Current Codebase tree (relevant slice — the 2 files this task touches)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── status.sh          # EDIT (Task 1: append exit 0 after jq call @L39; soften comment @L23-25). 39 lines, exec.
└── tests/
    └── test_status_sh.py  # CREATE (Task 2: the first status.sh regression suite — 4 tests).
# jq 1.8.1 installed (/usr/bin/jq). /bin/sh -> bash. status.sh is executable (-rwxr-xr-x). pytest>=9.1.1 is the
# project's runner (NO ruff/mypy in pyproject). test_feed_audio.py is the heavy GPU suite (ignored in the fast sweep).
# NO existing status.sh test (scout §7). test_feedback.py:351 references status.sh in a comment only.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/status.sh     # EDIT — append `exit 0` (+ short comment) after the jq call; soften the header comment.
tests/test_status_sh.py    # CREATE — 4 pytest tests (missing/corrupt/listening/idle), real subprocess + controlled env.
# NOTHING ELSE. (install.sh + tests/test_systemd_unit.py = P1.M1.T2.S1; launch_daemon.sh = P1.M1.T1.S1; daemon.py/
# test_feedback.py = unrelated; README/ACCEPTANCE = P1.M3.T1.S1.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE TEST MUST CARRY THE FULL ENVIRON (for PATH). status.sh calls `jq`, `id`, and runs under
# /bin/sh. subprocess.run(env={"XDG_RUNTIME_DIR": ...}) ALONE would drop PATH -> jq not found -> false failure.
# Use env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)} so PATH (and HOME, etc.) are preserved. The ONLY
# var you need to override is XDG_RUNTIME_DIR (to redirect STATE to the temp dir). (research §5.)

# CRITICAL #2 — CONTROL STATE VIA XDG_RUNTIME_DIR, not by editing the script. STATE =
# ${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json. Set XDG_RUNTIME_DIR=tmp_path in the test env;
# then the state file lives at <tmp_path>/voice-typing/state.json. For the missing-file case, create NOTHING
# (no voice-typing/ subdir); for corrupt/valid, mkdir voice-typing/ and write state.json. Do NOT touch the real
# /run/user/$(id -u)/voice-typing/ (non-hermetic; may belong to a running daemon). (research §5.)

# CRITICAL #3 — `exit 0` MUST BE A TERMINAL LINE, not `|| true`. The item specifies `exit 0`. A terminal `exit 0`
# zeroes the exit code REGARDLESS of what jq (or any future command above it) returned, and is the clearest
# expression of "never abort". Do NOT use `jq ... || true` (per-command; less clear; the item chose exit 0).
# (research §3.)

# CRITICAL #4 — DO NOT ADD `set -e`. The contract is "never abort". set -e would abort on jq's non-zero exit,
# the OPPOSITE of the fix. status.sh is intentionally `set -e`-free. The fix is a terminal `exit 0` that MASKS
# jq's non-zero. (research §6.)

# CRITICAL #5 — DO NOT TOUCH THE jq PROGRAM. The `2>/dev/null` + the jq `// ""` defaults already produce
# empty-on-failure stdout (verified: missing/corrupt -> empty stdout even before the exit-code fix). The ONLY
# behavior change is the exit code (2/5 -> 0). Edit (a) appends exit 0; edit (b) rewrites the comment. Nothing
# inside the jq '...' program changes. (research §3, §6.)

# CRITICAL #6 — COMMENT WORDING MUST BE ACCURATE (Mode A doc). The old "otherwise tmux would show an error string
# in status-right" is OVERSTATED — tmux's #(...) captures stdout and IGNORES the exit code. The new comment states
# this correctly: tmux ignores exit codes (empty stdout alone keeps status-right blank), but a non-tmux caller
# checking $? would see jq's 2/5; the explicit exit 0 honors the contract for every caller. Do NOT restate the
# old claim. (research §2, §4.)

# GOTCHA #7 — CORRUPT-JSON TEST INPUT. Use genuinely invalid JSON, e.g. 'not json{{}'. jq -r on invalid JSON
# exits 5 (parse error) with empty stdout (stderr -> /dev/null). Avoid inputs that are technically valid but
# surprising (e.g. a bare number is valid JSON; `null` is valid JSON -> jq would exit 0, not 5). 'not json{{}' is
# robustly invalid. (research §1, §4; jq exit code 5.)

# GOTCHA #8 — STATUS.SH IS EXECUTABLE; run it directly ([str(script)]) to mirror real tmux invocation (tmux calls
# #(.../status.sh) directly, not via `sh`). It is -rwxr-xr-x with #!/bin/sh. Running via ["sh", str(script)] is an
# acceptable fallback if the exec bit is ever lost, but direct execution is the faithful test. (Verified exec.)

# GOTCHA #9 — FULL PATHS in every bash command. This machine aliases python3->uv run, pip->alias, tmux->zsh plugin.
# Invoke .venv/bin/python and .venv/bin/python -m pytest explicitly. Never bare python/pytest/uv. (system_context.md §1.)

# GOTCHA #10 — THIS PROJECT USES pytest, NOT ruff/mypy. pyproject.toml has [dependency-groups] dev=["pytest>=9.1.1"]
# and NO [tool.ruff]/[tool.mypy]. Validation = sh -n (the shell script) + pytest (the tests). Do NOT invent
# ruff/mypy commands. (research §5.)

# GOTCHA #11 — `sh -n` NOT `bash -n` for the syntax gate. status.sh is POSIX #!/bin/sh. `sh -n` is the faithful
# POSIX syntax check (on this host /bin/sh -> bash, but sh -n still validates POSIX-compliant syntax). Either
# works here, but sh -n matches the shebang. (research §7.)
```

## Implementation Blueprint

### Data models and structure

None. No data/schema/types/config change. This is a 2-edit patch to a POSIX shell script + a new pytest module (stdlib `os`/`subprocess`/`pathlib` only).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/status.sh — (a) append `exit 0` after the jq call + (b) soften the header comment
  - Apply these TWO exact oldText -> newText edits (in ONE edit call with 2 entries; each oldText is unique):

    EDIT (a) — append exit 0 after the jq call (currently the last command; its exit code propagates):
      OLD:
        ' "$STATE" 2>/dev/null
      NEW:
        ' "$STATE" 2>/dev/null

        # Issue 2 fix: always exit 0. jq exits non-zero on a missing (2) or corrupt (5) state.json; without this
        # the script's exit code would be jq's, violating the "exit 0 (never abort)" contract documented above.
        # stdout is already empty-on-failure (2>/dev/null + the jq // "" defaults); this zeroes the exit code only.
        exit 0

    EDIT (b) — soften the header comment (lines 23-25) to an accurate tmux rationale:
      OLD:
        # POSIX sh + jq only. NO `set -e`: a missing or malformed state.json must print an empty
        # line with exit 0 (never abort) — otherwise tmux would show an error string in status-right.
        # The `2>/dev/null` + the jq `// ""` defaults already guarantee empty-on-failure.
      NEW:
        # POSIX sh + jq only. NO `set -e`: a missing or malformed state.json must print an empty
        # line with exit 0 (never abort). tmux's #(...) substitution captures stdout and IGNORES the
        # exit code (so the empty line alone keeps status-right blank) — but a non-tmux caller that
        # checks $? would see jq's non-zero exit (2 = missing file, 5 = corrupt JSON); the explicit
        # `exit 0` at the end honors the documented zero-exit contract for every caller. The
        # `2>/dev/null` + the jq `// ""` defaults guarantee empty-on-failure stdout.
  - WHY: (a) zeroes the exit code for every caller (the contract; proven in a throwaway copy); the comment
    explains why (so a future maintainer doesn't remove it). (b) corrects the overstated "tmux would show an
    error string" claim (tmux ignores exit codes) — Mode A doc accuracy. (research §2-4; Gotchas #3-#6.)
  - DO NOT: use `jq ... || true` instead of exit 0 (Gotcha #3); add `set -e` (Gotcha #4); touch the jq program
    (Gotcha #5); restate the old tmux claim (Gotcha #6); edit any other line.

Task 2: CREATE tests/test_status_sh.py — use the `write` tool with EXACTLY the content in "Task 2 SOURCE" below.
  - FILE: tests/test_status_sh.py
  - WHY: there is NO existing status.sh test (scout §7). This is the dedicated regression suite for the exit-code
    contract + output behavior. Runs the REAL script via subprocess with a controlled XDG_RUNTIME_DIR (hermetic).
  - DO NOT: mock subprocess (the point is to exercise the real script + real jq — Gotcha: distinct from
    test_typing_backends.py's mocked-subprocess pattern); drop PATH from the env (Gotcha #1); touch the real
    /run/user/$(id -u)/voice-typing/ (Gotcha #2); edit test_feedback.py.

Task 3: VALIDATE — run the Validation Loop L1-L4 below; fix until all green. No git commit unless the orchestrator
  directs it. If asked, message:
  "P1.M2.T1.S1: status.sh always exits 0 (honors the documented contract) + softened tmux comment + tests/test_status_sh.py".
```

#### Task 2 SOURCE — `tests/test_status_sh.py` (write verbatim)

```python
"""Regression tests for voice_typing/status.sh (bugfix Issue 2 — exit-code contract).

status.sh is the tmux status-right helper (PRD §4.6). Its header comment promises
"exit 0 (never abort)" on a missing/corrupt state.json. Before the Issue 2 fix the
script exited with jq's exit code (2 = missing file, 5 = corrupt JSON), breaking
that contract for any non-tmux caller checking $?. These tests run the REAL script
via subprocess with a controlled XDG_RUNTIME_DIR and assert exit 0 + empty stdout
on failure, plus a happy-path guard that the fix did not break normal rendering.

Run: cd /home/dustin/projects/voice-typing && .venv/bin/python -m pytest tests/test_status_sh.py -v
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Module-relative path to the script (CWD-independent; same idiom as config.py's _repo_config_path
# and tests/test_config_repo_default.py). tests/test_status_sh.py -> parent=tests/ -> parent=repo root.
_SCRIPT = Path(__file__).resolve().parent.parent / "voice_typing" / "status.sh"

_STATE_SUBDIR = "voice-typing"
_STATE_FILE = "state.json"


def _run_status(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run status.sh with XDG_RUNTIME_DIR pointed at tmp_path; capture stdout/stderr/exit.

    Carries the FULL environ (only XDG_RUNTIME_DIR is overridden) so `jq`, `id`, and the
    #!/bin/sh interpreter stay on PATH. A bare {"XDG_RUNTIME_DIR": ...} would drop PATH and
    the script would fail to find jq -> false test failure.
    """
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}
    return subprocess.run(
        [str(_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _write_state(tmp_path: Path, contents: str) -> Path:
    """Write contents to <tmp_path>/voice-typing/state.json (the path status.sh reads)."""
    state = tmp_path / _STATE_SUBDIR / _STATE_FILE
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(contents, encoding="utf-8")
    return state


def test_status_sh_missing_state_file_exits_zero_with_empty_stdout(tmp_path):
    """Issue 2 regression: no state file at all -> exit 0 + empty stdout (was: exit 2)."""
    # tmp_path has no voice-typing/state.json -> jq gets a missing file -> exit 2 without the fix.
    result = _run_status(tmp_path)
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "", f"expected empty stdout, got {result.stdout!r}"


def test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout(tmp_path):
    """Issue 2 regression: corrupt JSON in state.json -> exit 0 + empty stdout (was: exit 5)."""
    _write_state(tmp_path, "not json{{}")  # robustly invalid JSON -> jq parse error (exit 5 without the fix)
    result = _run_status(tmp_path)
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "", f"expected empty stdout, got {result.stdout!r}"


def test_status_sh_listening_renders_partial_and_exits_zero(tmp_path):
    """Happy path (regression guard): listening + partial -> '🎤 <partial>' + exit 0.

    Proves the `exit 0` fix does not suppress normal output — jq's stdout (the rendered
    line) still reaches stdout and the exit code is 0 (jq succeeded).
    """
    _write_state(tmp_path, '{"listening": true, "partial": "hello world"}')
    result = _run_status(tmp_path)
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}; stderr={result.stderr!r}"
    )
    out = result.stdout.strip()
    assert out.startswith("🎤"), f"expected emoji prefix, got {out!r}"
    assert "hello world" in out, f"expected the partial in output, got {out!r}"


def test_status_sh_not_listening_renders_empty_and_exits_zero(tmp_path):
    """Idle path: not listening -> empty stdout + exit 0 (the common idle case)."""
    _write_state(tmp_path, '{"listening": false, "partial": "leftover from before"}')
    result = _run_status(tmp_path)
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "", f"expected empty stdout when idle, got {result.stdout!r}"
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the terminal `exit 0` (the contract fix). Masks jq's non-zero exit on missing (2)/corrupt (5)
# state.json. stdout is ALREADY empty-on-failure (2>/dev/null + jq // "" defaults); this zeroes the exit code only.
jq -r --arg max "$MAX" ' ... ' "$STATE" 2>/dev/null
# Issue 2 fix: always exit 0 ... (comment)
exit 0

# PATTERN 2 — run the REAL script with a controlled env (the test idiom). Carry full environ for PATH; override
# only XDG_RUNTIME_DIR to redirect STATE to the temp dir. Hermetic (never touches /run/user/$(id -u)/...).
env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path)}        # PATH preserved -> jq/id/sh resolve
result = subprocess.run([str(_SCRIPT)], env=env, capture_output=True, text=True, timeout=10)
assert result.returncode == 0 and result.stdout.strip() == ""  # the contract (missing/corrupt)

# PATTERN 3 — module-relative repo path (CWD-independent; mirrors config.py's _repo_config_path).
_SCRIPT = Path(__file__).resolve().parent.parent / "voice_typing" / "status.sh"   # tests/ -> repo root
```

### Integration Points

```yaml
UPSTREAM CONSUMED — the daemon's state.json writer (feedback.py; UNCHANGED):
  - status.sh READS $XDG_RUNTIME_DIR/voice-typing/state.json written by voice_typing/feedback.py (the atomic
    state-file writer). This task changes ONLY the reader's exit code + comment — the writer, the JSON schema
    ({listening, phase, partial, last_final, ts}), and feedback.py are untouched. The happy-path test's JSON
    matches the schema feedback.py emits.

PARALLEL — P1.M1.T2.S1 (install.sh offline grep; NO overlap):
  - T2.S1 edits install.sh + tests/test_systemd_unit.py. This task edits voice_typing/status.sh + creates
    tests/test_status_sh.py. No shared files -> safe parallel landing.

DOWNSTREAM — P1.M3.T1.S1 (README/ACCEPTANCE sync; PLANNED):
  - The README's tmux snippet points at status.sh. The comment softening (step b) is the in-place Mode A doc
    update; P1.M3.T1.S1's broader README sync does not conflict (it spans the whole changeset, not status.sh's
    internal comment). No edit to README.md here.

UNCHANGED (scope boundary):
  - launch_daemon.sh (P1.M1.T1.S1), install.sh + tests/test_systemd_unit.py (P1.M1.T2.S1), daemon.py,
    feedback.py, config.toml/config.py, test_feedback.py, ctl.py, typing_backends.py, systemd unit, README.md.

BUILD ARTIFACTS:
  - This task creates NO dist/, NO pyproject/uv.lock/.venv changes, NO new dependencies. It is a 2-edit shell
    patch + a stdlib-only pytest module. `uv sync`/`uv build` are NOT run. Validation = sh -n + pytest.
```

## Validation Loop

> Full paths in every bash command (zsh aliases — system_context.md §1; Gotcha #9). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy — Gotcha #10). All gates are
> fast/subprocess (no GPU, no daemon, no model load — status.sh is jq-only).

### Level 1: the two status.sh edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- POSIX syntax check ---"
sh -n voice_typing/status.sh && echo "L1 PASS: sh -n clean" || echo "L1 FAIL: syntax error"
echo "--- ends with a terminal exit 0 (exactly one) ---"
tail -n 1 voice_typing/status.sh | grep -qx 'exit 0' && echo "L1 PASS: last line is 'exit 0'" || echo "L1 FAIL: last line is not 'exit 0'"
[ "$(grep -cE '^exit 0$' voice_typing/status.sh)" -eq 1 ] && echo "L1 PASS: exactly one 'exit 0' line" || echo "L1 FAIL: zero or multiple 'exit 0' lines"
echo "--- comment softened: old overstated claim GONE; new accurate wording present ---"
! grep -q 'otherwise tmux would show an error string' voice_typing/status.sh && echo "L1 PASS: old claim removed" || echo "L1 FAIL: old 'tmux would show an error string' claim still present"
grep -qE 'IGNORES the(\s| )exit code' voice_typing/status.sh && grep -q 'non-tmux caller' voice_typing/status.sh && echo "L1 PASS: new accurate wording present" || echo "L1 FAIL: new wording missing"
echo "--- no set -e added; jq program untouched ---"
! grep -q 'set -e' voice_typing/status.sh && echo "L1 PASS: still no 'set -e' (never-abort preserved)" || echo "L1 FAIL: 'set -e' was added (violates the contract)"
grep -q '// ""' voice_typing/status.sh && echo "L1 PASS: jq // '' defaults intact" || echo "L1 FAIL: jq program altered"
# Expected: sh -n clean; last line exit 0; exactly one exit 0; old claim gone; new wording present; no set -e; jq intact.
```

### Level 2: the new regression test (the contract proof)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_status_sh.py -v
# Expected: 4 passed (missing -> exit 0 + empty; corrupt -> exit 0 + empty; listening -> '🎤 hello world' + exit 0;
# idle -> empty + exit 0). Any failure -> READ the failure; if a failure-case exit code is 2/5, the exit 0 edit
# (Task 1 EDIT a) was not applied correctly.
```

### Level 3: the documented manual contract proof (the Issue 2 repro, now green)

```bash
cd /home/dustin/projects/voice-typing
echo "--- missing state file (was exit=2) ---"
TD=$(mktemp -d)
XDG_RUNTIME_DIR="$TD" voice_typing/status.sh; CODE=$?
echo "exit=$CODE"
[ "$CODE" -eq 0 ] && echo "L3 PASS: missing-file exit 0" || echo "L3 FAIL: exit $CODE"
echo "--- corrupt JSON (was exit=5) ---"
mkdir -p "$TD/voice-typing"; printf 'not json{{}' > "$TD/voice-typing/state.json"
OUT=$(XDG_RUNTIME_DIR="$TD" voice_typing/status.sh); CODE=$?
echo "stdout=[$OUT] exit=$CODE"
[ "$CODE" -eq 0 ] && [ -z "$OUT" ] && echo "L3 PASS: corrupt-JSON exit 0 + empty stdout" || echo "L3 FAIL: exit=$CODE stdout=[$OUT]"
echo "--- happy path still renders (no regression) ---"
printf '{"listening": true, "partial": "hello world"}' > "$TD/voice-typing/state.json"
OUT=$(XDG_RUNTIME_DIR="$TD" voice_typing/status.sh); CODE=$?
echo "stdout=[$OUT] exit=$CODE"
[ "$CODE" -eq 0 ] && echo "$OUT" | grep -q '🎤 hello world' && echo "L3 PASS: happy path renders + exit 0" || echo "L3 FAIL"
rm -rf "$TD"
# Expected: all three PASS (missing -> 0; corrupt -> 0 empty; happy -> '🎤 hello world' + 0).
```

### Level 4: full fast suite green + scope guard

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py is the heavy GPU/offline suite, intentionally ignored on the fast sweep.)
echo "--- scope: only status.sh + tests/test_status_sh.py changed ---"
git status --short
# Expected: ONLY voice_typing/status.sh (modified) + tests/test_status_sh.py (new). No install.sh, no
# tests/test_systemd_unit.py (P1.M1.T2.S1), no launch_daemon.sh, no daemon.py, no test_feedback.py, no README.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `sh -n voice_typing/status.sh` clean; last line `exit 0`; exactly one `exit 0`; old tmux claim gone; new accurate wording present; no `set -e`; jq program intact.
- [ ] L2: `.venv/bin/python -m pytest tests/test_status_sh.py -v` → 4 passed.
- [ ] L3: manual contract proof — missing → exit 0; corrupt → exit 0 + empty stdout; happy → `🎤 hello world` + exit 0.
- [ ] L4: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed; `git status` shows ONLY `voice_typing/status.sh` + `tests/test_status_sh.py`.

### Feature Validation
- [ ] status.sh exits 0 on missing state.json (was 2) and corrupt JSON (was 5) — the documented contract is honored.
- [ ] status.sh stdout is unchanged (empty on failure; `🎤 <partial>` when listening) — `exit 0` only fixes the exit code.
- [ ] The header comment accurately describes the tmux `#(...)` behavior (ignores exit codes) + why `exit 0` matters (non-tmux callers).

### Code Quality Validation
- [ ] The new test mirrors codebase conventions (`from __future__ import annotations`, module-relative repo path, `tmp_path`, full-env carry for PATH).
- [ ] The new test is hermetic (controls `XDG_RUNTIME_DIR`; never touches the real `/run/user/$(id -u)/`).
- [ ] Full paths in every bash command (`.venv/bin/python`, no bare python/pytest/uv).

### Scope Boundary Validation
- [ ] No `launch_daemon.sh`/`install.sh`/`systemd`/`daemon.py`/`feedback.py`/`config`/`ctl.py`/`typing_backends.py` changes.
- [ ] No `tests/test_systemd_unit.py`/`test_feedback.py`/`test_idle_and_gpu.sh` changes (other tasks own them).
- [ ] No `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md` changes.
- [ ] No new dependencies (the test is stdlib `os`/`subprocess`/`pathlib` + pytest only).

---

## Anti-Patterns to Avoid

- ❌ Don't use `jq ... || true` instead of a terminal `exit 0` — the item specifies `exit 0`; a terminal `exit 0` is clearer about "never abort" and robust to future commands added above it.
- ❌ Don't add `set -e` — the contract is "never abort"; `set -e` would abort on jq's non-zero, the opposite of the fix.
- ❌ Don't touch the jq program — `2>/dev/null` + the `// ""` defaults already yield empty-on-failure stdout; the fix is exit-code-only.
- ❌ Don't restate the old "otherwise tmux would show an error string" claim — tmux's `#(...)` ignores exit codes; the new comment must say so accurately.
- ❌ Don't mock `subprocess.run` in the new test — the point is to exercise the REAL script + REAL jq. (test_typing_backends.py's mocked-subprocess pattern is for capturing argv without OS side effects; it does not apply here.)
- ❌ Don't pass `env={"XDG_RUNTIME_DIR": ...}` alone to `subprocess.run` — that drops PATH and jq won't be found. Carry the full environ (`{**os.environ, "XDG_RUNTIME_DIR": ...}`).
- ❌ Don't let the test touch the real `/run/user/$(id -u)/voice-typing/` — control the path via `XDG_RUNTIME_DIR` + `tmp_path` (hermetic).
- ❌ Don't use technically-valid JSON (e.g. `null`, a bare number) as the "corrupt" input — jq would exit 0, not 5. Use robustly-invalid JSON like `not json{{}`.
- ❌ Don't edit `install.sh`/`tests/test_systemd_unit.py` (P1.M1.T2.S1), `launch_daemon.sh` (P1.M1.T1.S1), `test_feedback.py` (different concern), or `README.md` (P1.M3.T1.S1).
- ❌ Don't invent ruff/mypy commands — this project uses pytest only (`[dependency-groups] dev = ["pytest>=9.1.1"]`); the shell-script gate is `sh -n`.
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases shadow them) — use `.venv/bin/python -m pytest`.

---

## Confidence Score

**10/10** for one-pass implementation success. The defect is reproduced live (exit 2/5 vs documented exit 0), the fix is proven live in a throwaway copy (exit 0 on both failure cases AND the happy path still renders `🎤 hello world`), both status.sh edits are given as exact oldText→newText against the current file, and the verbatim 4-test source is provided (real subprocess + controlled `XDG_RUNTIME_DIR`, carrying full environ for PATH). The change is a 2-edit shell patch + a stdlib-only test with no new dependencies and no overlap with the parallel P1.M1.T2.S1 (which touches only `install.sh` + `tests/test_systemd_unit.py`). No residual uncertainty.
