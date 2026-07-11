"""Drift guard for systemd/voice-typing.service (PRD §4.9; validation Issue 1).

The systemd user unit is deployed verbatim by install.sh (`cp` into
~/.config/systemd/user/), so what lives in the repo IS what runs. These checks
keep the unit's critical, easy-to-regress directives honest without needing a
live systemd session:

  - ExecStart points at the launch_daemon.sh wrapper (NOT python directly) so
    LD_LIBRARY_PATH is set before the dynamic linker runs (PRD §8 risk row #1).
  - ExecStartPre imports WAYLAND_DISPLAY + DISPLAY into the service environment
    (validation Issue 1): without it the default `wtype` backend cannot connect
    to the Wayland compositor and every finalized utterance silently falls back
    to ydotool (~1.2s extra latency + the non-ASCII/layout quirks PRD §4.3
    reserves for fallback-only). systemd user services do NOT automatically
    inherit arbitrary variables from the user-manager environment.
  - Restart=on-failure so systemd restarts the daemon after a crash.

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_systemd_unit.py -v
"""
from __future__ import annotations

from pathlib import Path


def _unit_path() -> Path:
    # systemd/voice-typing.service — repo root is the parent of voice_typing/.
    return Path(__file__).resolve().parent.parent / "systemd" / "voice-typing.service"


def _unit_lines() -> list[str]:
    """Non-comment, non-empty directive lines (comments are illustrative, not contract)."""
    lines: list[str] = []
    for raw in _unit_path().read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def test_execstart_points_at_launch_daemon_wrapper():
    """ExecStart must run launch_daemon.sh (the LD_LIBRARY_PATH wrapper), not python directly."""
    exec_lines = [ln for ln in _unit_lines() if ln.startswith("ExecStart=")]
    assert len(exec_lines) == 1, exec_lines
    assert exec_lines[0].endswith("/voice_typing/launch_daemon.sh"), exec_lines[0]


def test_execstartpre_imports_wayland_and_display_env():
    """ExecStartPre must import WAYLAND_DISPLAY + DISPLAY so the wtype default backend works.

    Regression guard for validation Issue 1: systemd user services do not inherit arbitrary
    variables from the user-manager environment, so without this import wtype cannot reach the
    compositor and the daemon silently falls back to ydotool on every utterance.
    """
    pre_lines = [ln for ln in _unit_lines() if ln.startswith("ExecStartPre=")]
    assert pre_lines, "no ExecStartPre= directive found in the unit"
    # At least one ExecStartPre must import BOTH WAYLAND_DISPLAY and DISPLAY.
    assert any(
        "import-environment" in ln and "WAYLAND_DISPLAY" in ln and "DISPLAY" in ln
        for ln in pre_lines
    ), pre_lines


def test_restart_on_failure():
    """Restart=on-failure keeps the daemon alive across crashes (PRD §4.9 auto-restart)."""
    assert any(ln == "Restart=on-failure" for ln in _unit_lines())
