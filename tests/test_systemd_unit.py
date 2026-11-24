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

import pytest

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


def _hypr_binds_path() -> Path:
    # hypr-binds.conf — repo root is the parent of tests/.
    return Path(__file__).resolve().parent.parent / "hypr-binds.conf"


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


def test_launch_daemon_fetches_wayland_display_from_manager():
    """launch_daemon.sh must fetch WAYLAND_DISPLAY (+DISPLAY) from the user-manager environment.

    Regression guard for validation Issue 1 (HIGH): the wtype default backend is silently broken on
    every cold boot because the systemd unit (WantedBy=default.target) does NOT wait for
    graphical-session.target, so the unit's ExecStartPre=`import-environment WAYLAND_DISPLAY` runs
    while the manager env does not yet hold WAYLAND_DISPLAY → the import is a no-op and the daemon
    runs without it. The wrapper-side fix fetches the vars from `systemctl --user show-environment`
    at exec time (when the compositor has inevitably imported them), making the daemon robust to
    boot order itself. This static check pins that the fetch loop is present and runs BEFORE exec.
    """
    lines = _launch_daemon_path().read_text().splitlines()
    # The fetch loop spans two lines: `for _v in WAYLAND_DISPLAY DISPLAY; do` (the vars) and
    # `_val="$(systemctl --user show-environment ...)"` (the fetch command). Check both pieces are
    # present, then that the fetch command precedes exec. Accept either line form so a future
    # reformat (e.g. unrolling the loop) still passes as long as both the var + the fetch command
    # remain.
    show_env_idx = next(
        (i for i, ln in enumerate(lines) if "systemctl --user show-environment" in ln),
        None,
    )
    assert show_env_idx is not None, (
        "launch_daemon.sh is missing the `systemctl --user show-environment` fetch — the "
        "boot-order-robust fix for the wtype-on-cold-boot regression (validation Issue 1)."
    )
    wayland_idx = next(
        (i for i, ln in enumerate(lines) if "WAYLAND_DISPLAY" in ln),
        None,
    )
    assert wayland_idx is not None, "launch_daemon.sh never references WAYLAND_DISPLAY."
    exec_idx = next((i for i, ln in enumerate(lines) if _EXEC_RE.match(ln)), None)
    assert exec_idx is not None, (
        "launch_daemon.sh has no `exec \"$PY\" -m voice_typing.daemon` line — cannot verify "
        "fetch ordering."
    )
    assert show_env_idx < exec_idx, (
        f"the WAYLAND_DISPLAY fetch (line {show_env_idx + 1}) must precede "
        f"`exec \"$PY\" …` (line {exec_idx + 1}) — the var must be in the env before python starts."
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


def test_install_sh_usage_lists_all_commands_and_correct_keybinds():
    """install.sh [7/7] usage lists the 5 commands + the single toggle keybind (Rev 2).

    Rev 2 single-mode collapse (P1.M1.T2.S4): ctl.py _COMMANDS is exactly
    (toggle, start, stop, status, quit) and hypr-binds.conf ships ONE bind
    (Ctrl+Alt+Super+D -> voicectl toggle); the lite commands and the
    standalone Alt+Super+D bind are deleted surfaces. Static read_text check
    (same pattern as test_install_sh_offline_grep_and_summary) — closes the
    gap that let a wrong hint ship (the config drift-guard checks only parsed
    VALUES, not usage/help strings).
    """
    text = _install_sh_path().read_text()
    # (a) usage line lists all 5 commands (ctl.py _COMMANDS; Rev 2 single-mode).
    for cmd in ("toggle", "start", "stop", "status", "quit"):
        assert cmd in text, f"install.sh usage omits '{cmd}' (Rev 2: 5 commands)."
    # (b) the single keybind is stated (hypr-binds.conf: Ctrl+Alt+Super+D -> toggle).
    assert "Ctrl+Alt+Super+D" in text, (
        "install.sh bind hint is missing 'Ctrl+Alt+Super+D' "
        "(Rev 2: the ONE dictation bind is Ctrl+Alt+Super+D -> voicectl toggle)."
    )
    # (c) NEGATIVE: the deleted lite surfaces must not survive anywhere in install.sh.
    assert "toggle-lite" not in text, (
        "install.sh still mentions 'toggle-lite' (Rev 2 deleted it — P1.M1.T2.S4)."
    )
    assert "start-lite" not in text, (
        "install.sh still mentions 'start-lite' (Rev 2 deleted it — P1.M1.T2.S4)."
    )
    # The standalone lite bind is gone. NOTE 'Ctrl+Alt+Super+D' CONTAINS 'Alt+Super+D'
    # as a substring, so strip the legit bind before asserting the bare form is absent.
    assert "Alt+Super+D" not in text.replace("Ctrl+Alt+Super+D", ""), (
        "install.sh still advertises the standalone lite bind 'Alt+Super+D' "
        "(Rev 2 collapsed to one bind — P1.M1.T2.S4)."
    )
    # (d) the WRONG mapping is still gone. 'SUPER+ALT+D -> voicectl toggle' claimed the
    #     lite bind maps to the single toggle — backwards even in the two-mode era.
    assert "SUPER+ALT+D -> voicectl toggle" not in text, (
        "install.sh still claims 'SUPER+ALT+D -> voicectl toggle' — wrong mapping "
        "(the single bind is Ctrl+Alt+Super+D -> voicectl toggle)."
    )


# ---------------------------------------------------------------------------
# VT-003: no hardcoded /home/<user> paths in executable wiring (portability).
# The repo must not bake in a specific username / repo location. install.sh rewrites the unit's
# __REPO__ placeholder + installs a stable voicectl launcher; hypr-binds.conf uses $HOME (Hyprland
# runs `bind exec` through /bin/sh -c, which expands it). These static checks pin that no
# /home/dustin (or any absolute /home/...) path leaks into a functional site.
# ---------------------------------------------------------------------------


def test_systemd_unit_execstart_uses_repo_placeholder():
    """VT-003: the SOURCE unit's ExecStart uses the __REPO__ placeholder (NOT a hardcoded
    /home/<user> path); install.sh substitutes __REPO__ -> $REPO at install time so the INSTALLED
    ExecStart is portable across users / repo locations."""
    exec_lines = [ln for ln in _unit_lines() if ln.startswith("ExecStart=")]
    assert len(exec_lines) == 1, exec_lines
    line = exec_lines[0]
    assert line.startswith("ExecStart=__REPO__/"), (
        f"ExecStart must use the __REPO__ placeholder (install.sh substitutes it); got {line!r}"
    )
    assert line.endswith("/voice_typing/launch_daemon.sh"), line
    assert "/home/" not in line, f"ExecStart hardcodes an absolute home path: {line!r}"


def test_install_sh_substitutes_repo_placeholder():
    """VT-003: install.sh substitutes the __REPO__ placeholder with $REPO when copying the unit,
    so the installed ExecStart points at the actual repo (portable). Static check that the sed
    substitution is present in install.sh."""
    text = _install_sh_path().read_text()
    assert "__REPO__" in text and "#" in text, "install.sh does not reference the __REPO__ placeholder"
    # sed -i "s#__REPO__#$REPO#g" on the copied unit (the # delimiter avoids clashes with paths).
    assert re.search(r'sed\s+-i\s+"s#__REPO__#\$REPO#g"', text) or \
        re.search(r"s#__REPO__#\$REPO#g", text), (
        "install.sh is missing the `sed -i s#__REPO__#$REPO#g` substitution on the copied unit (VT-003)."
    )


def test_install_sh_uv_path_is_portable():
    """VT-003: install.sh must NOT hardcode /home/dustin/.local/bin/uv. It honors a UV= override,
    else `command -v uv`, else falls back to $HOME/.local/bin/uv."""
    text = _install_sh_path().read_text()
    assert '/home/dustin/' not in text, (
        "install.sh still hardcodes a /home/dustin path (VT-003); use ${UV:-$(command -v uv ...)}."
    )
    assert 'UV="${UV:-' in text, (
        "install.sh UV resolution must honor an override / command -v (VT-003)."
    )
    assert 'command -v uv' in text, "install.sh should look uv up on PATH (VT-003)."


def test_install_sh_installs_stable_voicectl_launcher():
    """VT-003: install.sh installs a stable $HOME/.local/bin/voicectl launcher (symlink -> the
    repo's voicectl) so hypr-binds.conf can reference voicectl via $HOME (no hardcoded repo path).
    Static check that the symlink install is present + never clobbers a foreign file."""
    text = _install_sh_path().read_text()
    assert "$HOME/.local/bin/voicectl" in text, (
        "install.sh must install the $HOME/.local/bin/voicectl launcher (VT-003)."
    )
    assert "ln -s" in text, "install.sh must create the voicectl symlink (VT-003)."
    # never blindly clobber a foreign file the user may have at that path
    assert "already exists" in text or "readlink -f" in text, (
        "install.sh must not clobber a foreign $HOME/.local/bin/voicectl (VT-003)."
    )


# BUG-003: hypr-binds.conf:60 intentionally ships ONE documented hard-kill panic bind
# (PRD Rev 3(4)) that deliberately bypasses voicectl AND the control socket — the escape
# hatch for a wedged socket: `bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing`.
# The VT-003 checker below pins that exact tuple (parsed, whitespace-tolerant, exactly once)
# instead of over-generalizing the launcher rule to every bind line.

_PANIC_BIND = ("SUPER ALT", "Escape", "exec", "systemctl --user stop voice-typing")

# String fixtures (the two shipped ordinary lines verbatim + the exact panic line) — the
# negative-space tests call _check_binds() on these directly; hypr-binds.conf is NEVER rewritten.
_PORTABLE_TOGGLE = "bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle"
_PORTABLE_CANCEL = "bind = SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel"
_PANIC_EXACT = "bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing"


def _is_panic_bind(ln: str) -> bool:
    """Exact parsed match of the documented panic bind (PRD Rev 3(4)) — BUG-003.

    The line is split on commas into (mods, key, dispatcher, command); whitespace between
    fields and tokens is ignored and SUPER_ALT == SUPER ALT. Everything else is EXACT: the
    mods SET, the key, the dispatcher, and the command TOKEN LIST — so any deviation
    (different chord/key/dispatcher, extra/missing/reordered/case-changed command token, a
    chained `;`/`&&` command, extra args) is NOT the panic bind and must satisfy the ordinary
    VT-003 rules. Deliberately NOT a substring or `# exempt`-marker check: a substring would
    silently accept '… stop voice-typing; reboot'.
    """
    body = re.sub(r"^bind\s*=\s*", "", ln.strip())
    parts = [p.strip() for p in body.split(",", 3)]  # mods, key, dispatcher, command
    if len(parts) != 4 or not parts[0]:
        return False
    mods = parts[0].replace("_", " ").split()
    if sorted(mods) != ["ALT", "SUPER"]:
        return False
    cmd = parts[3].split()  # token-list compare: whitespace-insensitive, otherwise exact
    return parts[1] == "Escape" and parts[2] == "exec" and cmd == _PANIC_BIND[3].split()


def _check_binds(bind_lines: list[str]) -> None:
    """The VT-003 portability contract over raw bind lines — shared by the shipped-file test
    and the string-fixture negative-space tests: exactly ONE exact panic bind (PRD Rev 3(4));
    every OTHER line must invoke the stable $HOME launcher and hardcode no /home/ path."""
    assert bind_lines, "no bind = lines"
    panic = [ln for ln in bind_lines if _is_panic_bind(ln)]
    assert panic, (
        "the documented panic bind was removed — restore `bind = SUPER ALT, Escape, exec, "
        "systemctl --user stop voice-typing` (PRD Rev 3(4); the escape hatch for a wedged socket)"
    )
    assert len(panic) == 1, (
        f"two+ panic binds shipped — deduplicate (exactly one documented hard-kill route): {panic!r}"
    )
    for ln in bind_lines:
        if _is_panic_bind(ln):
            continue  # the exact panic tuple only; lookalikes fall through to the ordinary rules
        assert "$HOME/.local/bin/voicectl" in ln, (
            f"hypr bind must use $HOME/.local/bin/voicectl (VT-003); got {ln!r}"
        )
        assert "/home/" not in ln, f"hypr bind hardcodes an absolute home path: {ln!r}"


def test_hypr_binds_use_portable_home_launcher():
    """VT-003: hypr-binds.conf invokes voicectl via $HOME/.local/bin/voicectl (Hyprland runs `bind
    exec` through /bin/sh -c, which expands $HOME) — NO hardcoded /home/<user> repo path, so the
    binds work regardless of which user runs it or where the repo was cloned.

    Panic exception (BUG-003): the config intentionally ships ONE documented hard-kill route
    (PRD Rev 3(4)) — SUPER+ALT+Escape → `systemctl --user stop voice-typing` — which bypasses
    voicectl and the control socket ON PURPOSE (the escape hatch when the socket is wedged).
    The exemption is the exact parsed tuple (chord/key/dispatcher/command token list,
    whitespace-only tolerance) and it must appear EXACTLY once; every other line — including
    `;`/`&&`-chained lookalikes, wrong chords/commands and extra args — keeps BOTH ordinary
    asserts. The stop is systemd's clean socket-bypassing stop (KillMode=mixed,
    TimeoutStopSec=15) — NOT a SIGKILL — and Restart=on-failure still applies after a crash.
    """
    text = _hypr_binds_path().read_text()
    bind_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("bind =")]
    _check_binds(bind_lines)


# --- negative space (string fixtures): every mutation of the panic bind must be rejected ----


def test_panic_bind_lookalike_with_semicolon_chain_rejected():
    """A trailing `; reboot` is NOT the panic bind — the command token list differs, so the
    line falls back to the ordinary rules and fails (substring matching would accept it)."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PORTABLE_CANCEL,
                      "bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing; reboot"])


def test_panic_bind_lookalike_with_and_chain_rejected():
    """A chained `&& reboot` lookalike likewise falls back to the ordinary rules and fails."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PORTABLE_CANCEL,
                      "bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing && reboot"])


def test_panic_bind_wrong_chord_rejected():
    """`SUPER, Escape` (missing ALT) is not the panic tuple — ordinary rules fail the line."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PORTABLE_CANCEL,
                      "bind = SUPER, Escape, exec, systemctl --user stop voice-typing"])


def test_panic_bind_wrong_command_rejected():
    """`systemctl --user restart` drifts from the pinned command; extra args drift too."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PORTABLE_CANCEL,
                      "bind = SUPER ALT, Escape, exec, systemctl --user restart voice-typing"])
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PORTABLE_CANCEL,
                      "bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing --force"])


def test_duplicate_panic_bind_rejected():
    """Two exact panic binds = a copy-paste error; the contract is exactly one."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PANIC_EXACT, _PANIC_EXACT])


def test_missing_panic_bind_rejected():
    """The panic bind is part of the shipped contract — removing it is a regression."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_TOGGLE, _PORTABLE_CANCEL])


def test_nonportable_ordinary_bind_still_rejected():
    """Ordinary rules are untouched: a hardcoded /home/dustin launcher (no $HOME form) fails,
    and so does a $HOME launcher line that smuggles an absolute /home/ path."""
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_CANCEL,
                      "bind = CTRL SUPER ALT, D, exec, /home/dustin/.local/bin/voicectl toggle"])
    with pytest.raises(AssertionError):
        _check_binds([_PORTABLE_CANCEL,
                      "bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle --conf /home/dustin/x"])


def test_panic_bind_tolerates_whitespace_and_underscore_only():
    """The POSITIVE edge of the normalization contract: whitespace runs between fields/tokens
    and the SUPER_ALT spelling still match the exact tuple (exactly once), while the ordinary
    binds pass alongside — proving the exemption is parsed, not a substring pass."""
    _check_binds([_PORTABLE_TOGGLE,
                  "bind = SUPER_ALT,  Escape , exec,\tsystemctl  --user   stop voice-typing",
                  _PORTABLE_CANCEL])


# ---------------------------------------------------------------------------
# VT-004: the unit is graphical-session-aware so ExecStartPre=import-environment is meaningful
# (on a cold boot the old WantedBy=default.target raced the compositor exporting WAYLAND_DISPLAY).
# ---------------------------------------------------------------------------


def test_unit_is_graphical_session_aware():
    """VT-004: the unit orders after + binds its lifecycle to graphical-session.target (so it
    starts AFTER the compositor exported WAYLAND_DISPLAY/DISPLAY, making ExecStartPre=
    import-environment meaningful instead of a cold-boot no-op), and is WantedBy it (not
    default.target). launch_daemon.sh still re-fetches the vars as belt-and-suspenders.
    """
    lines = _unit_lines()
    after = [ln for ln in lines if ln.startswith("After=")]
    assert after, "no After= directive"
    assert any("graphical-session.target" in ln for ln in after), (
        f"After= must include graphical-session.target (VT-004); got {after!r}"
    )
    assert any(ln.startswith("PartOf=graphical-session.target") for ln in lines), (
        "unit must declare PartOf=graphical-session.target (VT-004)"
    )
    install_lines = [ln for ln in lines if ln.startswith("WantedBy=")]
    assert install_lines == ["WantedBy=graphical-session.target"], (
        f"WantedBy must be graphical-session.target, not default.target (VT-004); got {install_lines!r}"
    )


def test_install_sh_cleans_stale_default_target_symlink():
    """VT-004: because WantedBy moved default.target -> graphical-session.target, install.sh must
    remove a stale default.target.wants symlink from a prior install (systemctl enable/disable key
    off the CURRENT unit's [Install] and will not clean up the old one on their own)."""
    text = _install_sh_path().read_text()
    assert "default.target.wants/voice-typing.service" in text, (
        "install.sh must remove a stale default.target.wants symlink (VT-004 WantedBy migration)."
    )
    assert "rm -f" in text, "install.sh must rm the stale symlink (VT-004)."


def test_execstoppost_ducking_crash_heal():
    """ExecStopPost runs the ducking crash-heal (best-effort media restore; PRD §4.2quinquies).

    systemd runs ExecStopPost on EVERY stop — clean exit, failure, AND SIGKILL/timeout — which
    makes it the crash net for ducked media: the heal module is flag-gated, so it no-ops
    (exit 0, zero backend calls) on every clean stop where the daemon already released +
    flushed itself. The exact-line assert doubles as the __REPO__-placeholder pin (install.sh
    substitutes it file-wide via the `sed s#__REPO__#$REPO#g` at install time).
    """
    lines = [ln for ln in _unit_lines() if ln.startswith("ExecStopPost=")]
    assert len(lines) == 1, lines
    assert lines[0] == "ExecStopPost=__REPO__/.venv/bin/python -m voice_typing.ducking_heal", lines[0]
