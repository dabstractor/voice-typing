"""Unit + integration tests for voice_typing.ctl (P1.M5.T1.S1).

Three layers (research §4):
  A. format_result() — pure function fed CANNED JSON (the item's mandated TDD core); no socket.
  B. real-socket round-trip — a live daemon.ControlServer + _StubDaemon on a tmp socket; ctl.main([..])
     connects, sends, formats, returns the exit code; assert stdout (capsys).
  C. exit-2 paths — socket absent (FileNotFoundError), stale socket no listener (ConnectionRefusedError),
     XDG_RUNTIME_DIR unset (RuntimeError).

NO RealtimeSTT / NO CUDA / NO real VoiceTypingDaemon. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_voicectl.py -v
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time

import pytest

from voice_typing import ctl, daemon


# ---------------------------------------------------------------------------
# canned daemon status_snapshot (matches daemon.ControlServer._dispatch output)
# ---------------------------------------------------------------------------
_STATUS_ON = {
    "ok": True, "listening": True, "phase": "listening", "models_loaded": True, "load_error": "",
    "partial": "hello wor", "last_final": "previous sentence.",
    "uptime_s": 12.345, "device": "cuda", "compute_type": "float32",
    "mode": "lite", "model": "small.en",                 # Rev 2 13-key snapshot (P1.M1.T2.S2/S3)
    "mic_ok": True, "mic_error": "",                       # bugfix Issue 2 / P1.M1.T2.S2
}


# --- Layer A: format_result (pure; canned JSON) --------------------------------------------

def test_format_toggle_on():
    assert ctl.format_result("toggle", {**_STATUS_ON, "listening": True}) == ("listening: on", 0)


def test_format_toggle_off():
    assert ctl.format_result("toggle", {**_STATUS_ON, "listening": False}) == ("listening: off", 0)


def test_format_start_on():
    assert ctl.format_result("start", {**_STATUS_ON, "listening": True}) == ("listening: on", 0)


def test_format_stop_off():
    assert ctl.format_result("stop", {**_STATUS_ON, "listening": False}) == ("listening: off", 0)


def test_format_quit_no_listening_key():
    # quit reply is {"ok":true,"shutting_down":true} — NO listening key -> must not KeyError
    assert ctl.format_result("quit", {"ok": True, "shutting_down": True}) == ("shutting down", 0)


def test_format_status_multiline_has_partial_and_mode():
    text, code = ctl.format_result("status", _STATUS_ON)
    assert code == 0
    assert "listening: on" in text
    assert "mode: lite" in text                      # Rev 2 constant (P1.M1.T2.S2); .get default stays
    assert "phase: listening" in text                # P1.M2.T2.S1: lifecycle phase rendered
    assert "hello wor" in text                      # partial
    assert "models:" not in text                     # models line DROPPED (P1.M1.T2.S3); JSON-only now
    assert "cuda" in text and "float32" in text      # device + compute_type
    assert "12.345" in text                          # uptime


def test_lite_commands_are_rejected_as_usage_errors():
    """Rev 2 single-mode (P1.M1.T2.S3): start-lite is gone from the surface and rejected with
    exit 64 (EX_USAGE) BEFORE any socket connect. toggle-lite is ALSO absent from _COMMANDS —
    it survives only as a deprecated migration alias (validation Issue 2), remapped to
    `toggle` by main() before this check (see test_toggle_lite_alias_maps_to_toggle)."""
    assert "toggle-lite" not in ctl._COMMANDS and "start-lite" not in ctl._COMMANDS
    assert ctl.main(["start-lite"]) == 64      # usage path returns before socket resolution


def test_toggle_lite_alias_maps_to_toggle(monkeypatch):
    """validation Issue 2: pre-Rev-2 keybind wrappers (this machine's own Hyprland bind among
    them) still call `voicectl toggle-lite`. main() remaps it to `toggle` BEFORE the usage
    gate, so the stale command arms dictation instead of dying with exit 64. With the socket
    deliberately unresolvable, the remapped command proceeds to the daemon-not-running path
    (exit 2) — proving it passed the usage gate (which alone returns 64)."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert ctl._ALIASES == {"toggle-lite": "toggle"}  # the shim is exactly this one mapping
    assert ctl.main(["toggle-lite"]) == 2  # NOT 64: remapped to `toggle`, socket attempted


def test_format_status_shows_unloaded_state_and_load_error():
    # P1.M2.T2.S1: an unloaded daemon (failed/never-loaded) renders phase + (not loaded) + the load error.
    resp = {**_STATUS_ON, "phase": "unloaded", "models_loaded": False,
            "load_error": "CUDA load failed: RuntimeError('no cudnn')"}
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "phase: unloaded" in text
    assert "load error: CUDA load failed" in text


def test_format_status_shows_mic_ok_when_healthy():
    text, code = ctl.format_result("status", _STATUS_ON)
    assert code == 0
    assert "mic: ok" in text


def test_format_status_shows_mic_unavailable_with_error_when_broken():
    resp = {**_STATUS_ON, "mic_ok": False, "mic_error": "no PyAudio input devices available"}
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "mic: unavailable (no PyAudio input devices available)" in text


def test_format_status_mic_defaults_healthy_when_key_absent():
    # A response missing mic_ok (old daemon) must read as healthy, never 'unavailable'.
    resp = {k: v for k, v in _STATUS_ON.items() if k not in ("mic_ok", "mic_error")}
    text, code = ctl.format_result("status", resp)
    assert code == 0 and "mic: ok" in text


def test_format_ok_false_unknown_command():
    text, code = ctl.format_result("toggle", {"ok": False, "error": "unknown command: 'x'"})
    assert code == 1 and "unknown command" in text


def test_format_ok_false_malformed_json_error():
    text, code = ctl.format_result("status", {"ok": False, "error": "malformed JSON: ..."})
    assert code == 1 and "malformed JSON" in text


def test_format_ok_false_missing_error_key_is_defensive():
    text, code = ctl.format_result("toggle", {"ok": False})
    assert code == 1 and "unknown error" in text


# --- Layer B: real-socket round-trip (live ControlServer + _StubDaemon) --------------------

class _StubDaemon:
    """Duck-type VoiceTypingDaemon for round-trip tests (mirror tests/test_control_socket.py)."""
    def __init__(self):
        self.calls = []
        self._listening = False

    def toggle(self):
        self.calls.append("toggle")
        self._listening = not self._listening

    def start(self):
        self.calls.append("start")
        self._listening = True

    def stop(self):
        self.calls.append("stop")
        self._listening = False

    def cancel(self):
        # P1.M2.T7.S1: mirror VoiceTypingDaemon.cancel() — records the call, returns the shape.
        self.calls.append("cancel")
        return {"ok": True, "listening": self._listening, **self.status_snapshot()}

    def request_shutdown(self):
        self.calls.append("quit")

    def is_listening(self):
        return self._listening

    def status_snapshot(self):
        return {**_STATUS_ON, "listening": self._listening}


@pytest.fixture
def running_server(monkeypatch, tmp_path):
    """A ControlServer on a tmp socket; XDG_RUNTIME_DIR pointed at tmp_path so ctl resolves it."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    socket_path = str(tmp_path / "voice-typing" / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=socket_path)
    srv.start()
    yield srv, socket_path
    srv.stop()


def test_main_status_round_trip_returns_zero_and_prints(capsys, running_server):
    srv, path = running_server
    code = ctl.main(["status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "listening: off" in out and "mode: lite" in out
    assert "models:" not in out                     # models line dropped (P1.M1.T2.S3)


def test_main_toggle_then_status_lists_on(capsys, running_server):
    srv, path = running_server
    assert ctl.main(["toggle"]) == 0
    capsys.readouterr()
    assert ctl.main(["status"]) == 0
    assert "listening: on" in capsys.readouterr().out


def test_main_quit_returns_zero_and_says_shutting_down(capsys, running_server):
    srv, path = running_server
    code = ctl.main(["quit"])
    assert code == 0
    assert "shutting down" in capsys.readouterr().out
    assert srv._daemon.calls == ["quit"]


# --- Layer C: exit-2 paths (daemon not running) -------------------------------------------

def test_main_exit2_when_socket_absent(monkeypatch, tmp_path, capfd):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))   # path resolves but file does NOT exist
    code = ctl.main(["status"])
    err = capfd.readouterr().err
    assert code == 2 and "not running" in err


def test_main_exit2_when_stale_socket_no_listener(monkeypatch, tmp_path, capfd):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sockdir = tmp_path / "voice-typing"
    sockdir.mkdir()
    (sockdir / "control.sock").touch()                     # stale file present, nothing listening
    code = ctl.main(["status"])
    assert code == 2 and "not running" in capfd.readouterr().err


def test_main_exit2_when_xdg_runtime_dir_unset(monkeypatch, capfd):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    code = ctl.main(["status"])
    assert code == 2 and "not running" in capfd.readouterr().err


# --- argparse / structural ---------------------------------------------------------------

def test_main_rejects_unknown_command():
    # Unknown command is now validated in main() (not argparse), returning EX_USAGE (64)
    # so exit 2 is reserved exclusively for "daemon not running" (PRD §4.8, bugfix Issue 7).
    code = ctl.main(["frobnicate"])
    assert code == 64


def test_main_rejects_missing_command():
    # `voicectl` with no command is a usage error -> EX_USAGE (64), NOT argparse SystemExit(2).
    # Requires the positional to be nargs='?' so argparse does not raise SystemExit(2) for a
    # missing required arg (see PRP research/exit_code_matrix.md).
    code = ctl.main([])          # empty list == zero positionals (NOT None == sys.argv)
    assert code == 64


def test_ctl_module_present_and_imports_pure():
    # Import purity, ORDER-INDEPENDENT: a FRESH interpreter importing only voice_typing.ctl
    # must NOT pull in RealtimeSTT/torch/ctranslate2. Asserting in a child process means the
    # result reflects ONLY what ctl itself imports — never what earlier tests left in this
    # process's sys.modules (PRD bugfix Issue 4; defense-in-depth with P1.M2.T1.S1).
    assert importlib.util.find_spec("voice_typing.ctl") is not None
    probe = (
        "import sys, voice_typing.ctl; "
        "leaked = [m for m in ('RealtimeSTT', 'torch', 'ctranslate2') if m in sys.modules]; "
        "assert not leaked, f'voice_typing.ctl transitively imports heavy deps: {leaked}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        "fresh interpreter importing voice_typing.ctl leaked heavy deps or failed to import:\n"
        f"--- returncode {result.returncode}\n--- stdout:\n{result.stdout}\n--- stderr:\n{result.stderr}"
    )


def test_main_returns_int(monkeypatch, tmp_path):
    # main()'s return type is the exit-code contract — it must be an int in every branch.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))   # socket absent -> exit 2 path
    assert isinstance(ctl.main(["status"]), int)
# ===========================================================================
# P1.M2.T1.S2 — 'loading models…' hint (client-side, during the blocking first arm)
# + _dispatch ok:false on model-load failure (PRD §4.2bis). Stubs simulate T1.S1's
# contract (start() blocks on _load_recorder; _load_error set on failure) so these
# tests are hermetic — NO GPU / NO RealtimeSTT.
# ===========================================================================


class _SlowStartStubDaemon(_StubDaemon):
    """A _StubDaemon whose start() blocks briefly to simulate the ~1–3 s lazy model load."""
    def __init__(self, delay: float = 0.4):
        super().__init__()
        self._delay = delay

    def start(self):
        time.sleep(self._delay)   # simulate _load_recorder() blocking the arm (PRD §4.2bis)
        super().start()


class _FailingLoadStubDaemon(_StubDaemon):
    """Simulates T1.S1's failed-load state: start()/toggle()-arm do NOT arm + _load_error is set (§4.2bis).

    Mirrors the REAL T1.S1 contract (voice_typing/daemon.py): on an arm attempt both start() and the
    arm-branch of toggle() call _load_recorder() FIRST and, on failure, return early WITHOUT arming (the
    daemon stays not-listening, _load_error set). _StubDaemon.toggle() unconditionally flips _listening,
    which would NOT model a failed arm — so override it to suppress the arm on the not-listening branch
    (the only branch this stub is used on; it starts not-listening and never arms).
    """
    def __init__(self, error: str = "cuda init failed: no device"):
        super().__init__()
        self._load_error = error   # the attr P1.M2.T1.S1 adds on a failed _load_recorder()

    def start(self):
        self.calls.append("start")
        # load failed → arm suppressed → stays not-listening (mirrors T1.S1 start() when _load_recorder() is False)

    def toggle(self):
        # Mirror T1.S1 toggle(): a disarm (was listening) still disarms; an ARM attempt (was not listening)
        # would load → fail → stay not-listening. This stub is never armed, so any toggle is an arm attempt
        # that fails → do NOT flip _listening (the real _arm() is never reached).
        self.calls.append("toggle")
        if self._listening:
            self._listening = False   # disarm path (defensive; not used by the failing-load tests)
        # else: arm attempt with a failed load → stays not-listening (mirrors T1.S1 toggle() early-return)


def _server_for(stub, monkeypatch, tmp_path):
    """A ControlServer on a tmp socket backed by `stub` (mirrors the running_server fixture)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    socket_path = str(tmp_path / "voice-typing" / "control.sock")
    srv = daemon.ControlServer(stub, socket_path=socket_path)
    srv.start()
    return srv, socket_path


def test_start_prints_loading_hint_when_arm_is_slow(monkeypatch, tmp_path, capsys):
    """voicectl start prints 'loading models…' to stderr when the arm blocks (PRD §4.2bis)."""
    monkeypatch.setattr(ctl, "_LOADING_HINT_DELAY", 0.02)   # fire well under the stub's 0.4 s
    srv, _socket_path = _server_for(_SlowStartStubDaemon(0.4), monkeypatch, tmp_path)
    try:
        code = ctl.main(["start"])
    finally:
        srv.stop()
    out, err = capsys.readouterr()
    assert code == 0
    assert "listening: on" in out
    assert "loading models" in err


def test_start_does_not_print_loading_hint_for_fast_arm(capsys, running_server):
    """A resident (instant) arm replies before the threshold → no hint (no flicker)."""
    code = ctl.main(["start"])
    out, err = capsys.readouterr()
    assert code == 0
    assert "listening: on" in out
    assert "loading models" not in err


def test_status_and_stop_do_not_print_loading_hint(capsys, running_server):
    """status/stop use plain send_command → never the loading-hint wrapper."""
    assert ctl.main(["status"]) == 0
    assert ctl.main(["stop"]) == 0
    _out, err = capsys.readouterr()
    assert "loading models" not in err


def test_start_load_failure_returns_ok_false_and_exit_one(monkeypatch, tmp_path, capsys):
    """A failed model load → _dispatch ok:false → voicectl 'error:' + exit 1 (PRD §4.2bis)."""
    srv, _socket_path = _server_for(_FailingLoadStubDaemon(), monkeypatch, tmp_path)
    try:
        code = ctl.main(["start"])
    finally:
        srv.stop()
    out, _err = capsys.readouterr()
    assert code == 1
    assert "error" in out and "model load failed" in out


def test_dispatch_start_returns_ok_false_with_load_error():
    """Unit: _dispatch('start') on a failed-load daemon → {'ok':False,'error':...} (the §4.2bis contract)."""
    srv = daemon.ControlServer(_FailingLoadStubDaemon(), socket_path="/tmp/unused-p1m2t1s2")
    resp = srv._dispatch(json.dumps({"cmd": "start"}))
    assert resp["ok"] is False
    assert "model load failed" in resp["error"]


def test_dispatch_toggle_arm_failure_returns_ok_false():
    """A toggle that attempts to arm + load fails → ok:false (was_listening=False path)."""
    srv = daemon.ControlServer(_FailingLoadStubDaemon(), socket_path="/tmp/unused-p1m2t1s2")
    resp = srv._dispatch(json.dumps({"cmd": "toggle"}))
    assert resp["ok"] is False and "model load failed" in resp["error"]


def test_dispatch_start_ok_true_when_no_load_error_attr():
    """The duck-typed _StubDaemon (no _load_error) → ok:true (existing-behavior guard)."""
    srv = daemon.ControlServer(_StubDaemon(), socket_path="/tmp/unused-p1m2t1s2")
    resp = srv._dispatch(json.dumps({"cmd": "start"}))
    assert resp["ok"] is True
    assert resp["listening"] is True   # _StubDaemon.start() arms
# ===========================================================================
# P1.M1.T2.S3 — help surfaces list exactly the 5 Rev 2 commands (bugfix Issue 3, inverted)
# (argparse format_help() + the module docstring must list the 5 commands matching _COMMANDS
#  + the no-arg error path — and NO stale toggle-lite/start-lite anywhere. The negative sweep
#  catches a stale epilog/docstring line the way Issue 3's positive sweep caught the missing ones.)
# ===========================================================================
def test_help_surfaces_list_all_commands():
    """Rev 2 surface (P1.M1.T2.S3; 'cancel' added by P1.M2.T7.S1): exactly 6 commands in _COMMANDS,
    --help (positional help + epilog), and the module docstring — and NO stale lite entries
    anywhere (bugfix Issue 3's consistency guard, inverted for the collapse).
    """
    commands = {"toggle", "start", "stop", "status", "quit", "cancel"}
    assert set(ctl._COMMANDS) == commands, sorted(ctl._COMMANDS)   # _COMMANDS = the source of truth
    # (1) argparse --help (format_help renders BOTH the positional help AND the epilog):
    help_text = ctl._build_parser().format_help()
    for cmd in commands:
        assert cmd in help_text, f"{cmd!r} missing from --help:\n{help_text}"
        assert cmd in ctl.__doc__, f"{cmd!r} missing from the ctl module docstring"
    # (2) negative sweep: the lite commands must be ABSENT from every help surface. (toggle-lite
    # remains a FUNCTIONAL migration alias in main() — validation Issue 2 — but is deliberately
    # undocumented: the Rev 2 surface stays the six commands above.)
    for stale in ("toggle-lite", "start-lite"):
        assert stale not in help_text, f"{stale!r} still in --help:\n{help_text}"
        assert stale not in ctl.__doc__, f"{stale!r} still in the module docstring"


# --- P1.M2.T7.S1: 'cancel' subcommand -------------------------------------------------------


def test_cancel_in_commands_docstring_and_epilog():
    """'cancel' is a first-class subcommand: the _COMMANDS entry, the module docstring subcommand
    block, and the --help epilog all list it."""
    assert ctl._COMMANDS == ("toggle", "start", "stop", "status", "quit", "cancel")
    assert "cancel" in (ctl.__doc__ or ""), "the module docstring's subcommand block must list cancel"
    epilog = ctl._build_parser().epilog or ""
    assert "cancel" in epilog, "the argparse epilog must list cancel"


def test_format_cancel_renders_listening_on_and_off():
    """cancel falls through format_result's default branch: 'listening: on/off', exit 0 — no
    loading-hint wrapping (it is NOT an arm command; P1.M2.T7.S1)."""
    assert ctl.format_result("cancel", {"ok": True, "listening": True}) == ("listening: on", 0)
    assert ctl.format_result("cancel", {"ok": True, "listening": False}) == ("listening: off", 0)


def test_main_cancel_round_trip_returns_zero_and_routes(capsys, running_server):
    """'voicectl cancel' routes {cmd: cancel} over the socket and renders the listening line."""
    srv, _path = running_server
    code = ctl.main(["cancel"])
    out = capsys.readouterr().out
    assert code == 0
    assert "listening:" in out
    assert srv._daemon.calls == ["cancel"], "the cancel command must reach the daemon"
