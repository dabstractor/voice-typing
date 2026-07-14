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

Also drift-guards voice_typing/launch_daemon.sh's offline env exports (bugfix
Issue 1): both HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 must be exported
before `exec "$PY"`, line-anchored so the WHY comment prose cannot false-pass.

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_systemd_unit.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

# Line-anchored regexes for launch_daemon.sh offline-export drift guard (bugfix Issue 1).
# Anchored on `^export ` so the WHY comment block (which mentions HF_HUB_OFFLINE=1 in
# prose) cannot cause a false pass. Accept bare `=1` and quoted variants.
_HF_RE = re.compile(r'^export\s+HF_HUB_OFFLINE=(?:1|"1"|\'1\')\s*$')
_TF_RE = re.compile(r'^export\s+TRANSFORMERS_OFFLINE=(?:1|"1"|\'1\')\s*$')
# `exec "$PY" -m voice_typing.daemon` — `$PY` is literal bash (regex needs `\$`).
_EXEC_RE = re.compile(r'^exec\s+"\$PY"\s+-m\s+voice_typing\.daemon')


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


def _launch_daemon_path() -> Path:
    # voice_typing/launch_daemon.sh — repo root is the parent of tests/.
    return Path(__file__).resolve().parent.parent / "voice_typing" / "launch_daemon.sh"


def _install_sh_path() -> Path:
    # install.sh — repo root is the parent of tests/.
    return Path(__file__).resolve().parent.parent / "install.sh"


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


def test_timeout_stop_sec_bounds_shutdown():
    """TimeoutStopSec=15 bounds systemd's stop so the daemon is never SIGKILLed at the 90s default.

    The daemon's own _bounded_shutdown(timeout=5) (P1.M1.T1.S2 + P1.M1.T2.S2) returns within
    ~7s; the 15s unit budget = 5s bounded teardown + 5s coordination + 5s headroom for the
    SIGTERM → handler → run-loop → finally latency.
    Without this directive systemd applies its 90s default, which produced
    'Failed with result timeout' / SIGKILL on every quit (PRD §8 risk row; root-caused in
    P1.M1.T1.S1). Companion to the daemon-side bound; both are required.
    """
    assert any(ln == "TimeoutStopSec=15" for ln in _unit_lines()), (
        "systemd unit missing TimeoutStopSec=15 — without it the 90s default SIGKILLs the "
        "daemon on stop (PRD §8 risk row)."
    )


def test_launch_daemon_exports_offline_vars():
    """launch_daemon.sh must export HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 BEFORE exec.

    Static drift guard for bugfix Issue 1 (PRD §1 "100% local" + acceptance §7.8). The
    production daemon phones home to https://huggingface.co on every startup unless
    HF_HUB_OFFLINE=1 is in the process environment before python starts (huggingface_hub
    latches the flag at import time). S1 put both exports in launch_daemon.sh — the
    sanctioned single source for the daemon env (same place LD_LIBRARY_PATH lives), inherited
    by both `systemctl` starts and manual launches. This test FAILS if either export is
    removed or moved after `exec`, so the "100% local" guarantee cannot silently regress.

    This is a STATIC check (read_text + line regex), not a live-systemd or runtime test:
    it is fast, needs no GPU/models/network, and runs on every commit. It guards the
    configurational precondition; the runtime no-network proof is test_idle_and_gpu.sh
    (S3 removes its pre-set masking so it exercises the real production path).

    Accepts bare `=1` and the quoted variants `="1"` / `='1'` so a harmless future reformat
    does not break the guard. Line-anchored on `^export ` so the WHY comment block (which
    mentions HF_HUB_OFFLINE=1 in prose) cannot cause a false pass.
    """
    lines = _launch_daemon_path().read_text().splitlines()

    hf_idx = next((i for i, ln in enumerate(lines) if _HF_RE.match(ln)), None)
    tf_idx = next((i for i, ln in enumerate(lines) if _TF_RE.match(ln)), None)
    assert hf_idx is not None, (
        "launch_daemon.sh is missing `export HF_HUB_OFFLINE=1` — the offline guarantee "
        "(bugfix Issue 1; PRD §1/§7.8) must be exported before exec."
    )
    assert tf_idx is not None, (
        "launch_daemon.sh is missing `export TRANSFORMERS_OFFLINE=1` — belt-and-suspenders "
        "offline var (bugfix Issue 1); both vars are required."
    )

    exec_idx = next((i for i, ln in enumerate(lines) if _EXEC_RE.match(ln)), None)
    assert exec_idx is not None, (
        "launch_daemon.sh has no `exec \"$PY\" -m voice_typing.daemon` line — cannot verify "
        "export ordering."
    )
    # Env vars are read at execve(2); exports MUST precede exec or they never reach python.
    assert hf_idx < exec_idx, (
        f"`export HF_HUB_OFFLINE=1` (line {hf_idx + 1}) must precede "
        f"`exec \"$PY\" …` (line {exec_idx + 1})."
    )
    assert tf_idx < exec_idx, (
        f"`export TRANSFORMERS_OFFLINE=1` (line {tf_idx + 1}) must precede "
        f"`exec \"$PY\" …` (line {exec_idx + 1})."
    )


def test_install_sh_offline_grep_and_summary():
    """install.sh must (a) grep the post-restart journal for huggingface.co HTTP calls
    (warn-level runtime regression surface) and (b) print an offline summary line (the Mode A
    user-facing offline promise). bugfix Issue 1 / Issue 4 (P1.M1.T2.S1).

    The hard config gate is test_launch_daemon_exports_offline_vars; this asserts install.sh
    carries the runtime surface + the documented promise, so neither can be silently removed.
    """
    text = _install_sh_path().read_text()
    assert "HTTP Request: GET https://huggingface.co" in text, (
        "install.sh is missing the post-restart journal grep for huggingface.co HTTP calls "
        "(bugfix Issue 1/Issue 4 runtime regression surface)."
    )
    assert "no network at runtime" in text, (
        "install.sh is missing the offline summary line (Mode A user-facing offline promise)."
    )
