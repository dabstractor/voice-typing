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
