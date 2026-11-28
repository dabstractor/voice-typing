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
import io
import json
import socket
import subprocess
import sys
import threading
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


# --- P1.M3.T3.S2: delivery status lines (PRD §4.2sexies R.5 surface) -----------------------


def test_format_status_delivery_line_renders_after_context_prompt():
    """Ordering pin: the delivery line lands AFTER context-prompt (before the optional
    load error) — the G3/G5 evidence harnesses grep these lines in order."""
    resp = {**_STATUS_ON, "delivery_mode": "bulk-text", "delivery_state": "active"}
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert text.index("context-prompt:") < text.index("delivery: bulk-text (active)")


def test_format_status_delivery_reason_and_op_render_when_populated():
    resp = {
        **_STATUS_ON,
        "delivery_mode": "bulk-text",
        "delivery_state": "fault",
        "delivery_reason": "op-deadline",
        "last_confirmed_op": "insert utt=3 seq=7 rev=12 +34ch 41ms",
    }
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "delivery: bulk-text (fault)" in text
    assert "delivery reason: op-deadline" in text
    assert "delivery op: insert utt=3 seq=7 rev=12 +34ch 41ms" in text
    assert "\ndelivery reason: op-deadline\n" in "\n" + text + "\n"  # exactly one line


def test_format_status_delivery_reason_and_op_hidden_when_empty():
    """The PRD R.5 default (stream-edit, nothing wired): exactly ONE new line, and the
    reason/op lines are hidden while empty — no 'delivery reason:' noise."""
    resp = {**_STATUS_ON, "delivery_mode": "stream-edit", "delivery_state": "inactive",
            "delivery_reason": "", "last_confirmed_op": ""}
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "delivery: stream-edit (inactive)" in text
    assert "delivery reason:" not in text
    assert "delivery op:" not in text


def test_format_status_delivery_defaults_unknown_when_keys_absent():
    """Old-daemon tolerance (the context_prompt precedent): a reply with NO delivery keys
    at all renders 'delivery: unknown (unknown)', never raises, exit 0."""
    resp = {k: v for k, v in _STATUS_ON.items() if k not in
            ("delivery_mode", "delivery_state", "delivery_reason", "last_confirmed_op")}
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "delivery: unknown (unknown)" in text
    assert "delivery reason:" not in text and "delivery op:" not in text


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
    def __init__(self, session=None):
        self.calls = []
        self._listening = False
        self._session = session
        self.session_calls: list[bool] = []

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

    def session_reply(self, copy: bool = False):
        # P1.M6.T2.S3: mirror VoiceTypingDaemon.session_reply() — records the copy flag,
        # returns the canned shape (None -> the no-completed-session error).
        self.session_calls.append(bool(copy))
        if self._session is None:
            return {"ok": False, "error": "no completed session yet"}
        return {"ok": True, "session": dict(self._session)}

    def start_context(self, context, *, streaming=None):
        # P1.M1.T2.S5: mirror VoiceTypingDaemon.start_context() — records the wire triple,
        # returns a canned SEEDED reply (dispatch passes it through verbatim).
        self.calls.append(("start-context", context, streaming))
        self._listening = True
        return {"ok": True, "listening": True, "context_seeded": True,
                "context_tokens": 5, **self.status_snapshot()}


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
    """Rev 2 surface (P1.M1.T2.S3; 'cancel' added by P1.M2.T7.S1; 'session' added by
    P1.M6.T2.S3; 'recover' added by P1.M1.T5.S2): exactly 12 commands in _COMMANDS,
    --help (positional help + epilog), and the module docstring — and NO stale lite entries
    anywhere (bugfix Issue 3's consistency guard, inverted for the collapse).
    """
    commands = {
        "toggle",
        "start",
        "stop",
        "status",
        "quit",
        "cancel",
        "session",
        "toggle-block",
        "start-block",  # per-session output mode (2026-11-27)
        "toggle-stream",
        "start-stream",
        "recover",  # native editor recovery read (P1.M1.T5.S2)
    }
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
    assert ctl._COMMANDS == (
        "toggle", "start", "toggle-block", "toggle-stream", "start-block", "start-stream",
        "stop", "status", "quit", "cancel", "session", "recover",
    )
    assert "cancel" in (ctl.__doc__ or ""), "the module docstring's subcommand block must list cancel"
    epilog = ctl._build_parser().epilog or ""
    assert "cancel" in epilog, "the argparse epilog must list cancel"


# --- P1.M1.T1.S4: usage baseline (troubleshooting help + no stale bulk + wedged remedy) ------


def test_help_troubleshooting_names_out_of_band_stop_and_migration():
    """P1.M1.T1.S4 (usage baseline): --help and the module docstring must tell a user whose
    control socket is nonresponsive how to stop the installed user unit OUT OF BAND
    (`systemctl --user stop voice-typing` — the supplied unit's dependable remedy; Restart=
    on-failure never overrides an explicit stop), reuse S1's actionable migration wording, and
    state that keybinds are user-owned (PRD §4.10 — nothing is shipped)."""
    help_text = ctl._build_parser().format_help()
    doc = ctl.__doc__ or ""
    for needle in (
        "systemctl --user stop voice-typing",                 # the out-of-band stop
        "journalctl --user -u voice-typing",                  # where the startup error lands
        'output.delivery="bulk-text" is retired',            # S1's wording (config.py:204-207)
        'set delivery = "stream-edit"',                      # …with BOTH actionable verbs
        "user-owned",                                        # no shipped shortcut (PRD §4.10)
    ):
        assert needle in help_text, f"{needle!r} missing from --help:\n{help_text}"
        assert needle in doc, f"{needle!r} missing from the ctl module docstring"
    # The retired delivery state machine is no longer advertised as a live status feature
    assert "mode/state, reason/op" not in doc


def test_voicectl_source_has_no_bulk_surface_beyond_migration_hint():
    """P1.M1.T1.S4: the only 'bulk' token left in ctl.py is S1's retirement phrase (the
    migration hint users must see). Mirrors S2/S3's no-bulk-surface pins on their modules."""
    import inspect

    src = inspect.getsource(ctl)
    assert src.lower().count("bulk") == src.count('output.delivery="bulk-text" is retired'), (
        "a stale bulk claim crept into ctl.py — only the migration phrase may name it"
    )


def test_wedged_timeout_names_out_of_band_stop(monkeypatch, tmp_path, capfd):
    """P1.M1.T1.S4: a socket that accepts but NEVER replies must produce the wedged ValueError
    with (a) the 'daemon wedged: no reply within' prefix kept byte-identical (existing match=
    tests/users depend on it) and (b) `systemctl --user stop voice-typing` as the remedy.
    main() routes ValueError -> stderr + exit 1; the fake server never touches a real daemon."""
    sock_dir = tmp_path / "voice-typing"
    sock_dir.mkdir()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_dir / "control.sock"))
    server.listen(1)
    held: list[socket.socket] = []

    def accept_and_hold() -> None:
        conn, _ = server.accept()
        held.append(conn)  # accept, then NEVER reply

    acceptor = threading.Thread(target=accept_and_hold, daemon=True)
    acceptor.start()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))  # ctl resolves .../voice-typing/control.sock
    monkeypatch.setenv("VOICECTL_TIMEOUT", "1")           # keep the test fast
    try:
        rc = ctl.main(["status"])
    finally:
        server.close()
        for conn in held:
            conn.close()
    _, err = capfd.readouterr()
    assert rc == 1, err
    assert err.startswith("voicectl: daemon wedged: no reply within"), err  # prefix contract
    assert "systemctl --user stop voice-typing" in err, err


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


# ===========================================================================
# P1.M6.T2.S3 — `voicectl session [--copy]` (R.6 recovery surface)
# Layer A: format_result session branch (pure); Layer B: main() orchestration over the
# running_server fixture; helper tests: _copy_session_to_clipboard with a fully mocked
# subprocess (G10: no real clipboard is EVER touched in automated validation).
# ===========================================================================

_SESSION = {
    "text": "hello dictated world", "truncated": False, "finals": 3,
    "finals_dropped": 0, "tail_chars": 0, "ended_monotonic": 12345.678,
}


# --- Layer A: format_result session branch (PURE) -----------------------------------------

def test_format_session_prints_text_exactly():
    """session ok:true → (text, 0) — stdout is EXACTLY the recovered text, no metadata (G2)."""
    text, code = ctl.format_result("session", {"ok": True, "session": dict(_SESSION)})
    assert (text, code) == (_SESSION["text"], 0)
    assert "truncated" not in text and "finals" not in text


def test_format_session_none_is_error_exit1():
    """The none-case rides format_result's FIRST branch (G1): ok:false → error text + exit 1 —
    so --copy code in main() is unreachable when no session exists (clipboard untouched)."""
    text, code = ctl.format_result("session", {"ok": False, "error": "no completed session yet"})
    assert (text, code) == ("error: no completed session yet", 1)


# --- Layer B: main() orchestration over the real socket -----------------------------------

def test_main_session_round_trip_prints_text(capsys, running_server):
    """Full stack: canned session → main(["session"]) == 0; stdout is EXACTLY text + one
    terminal newline (byte-exact stdout purity, G2)."""
    srv, _path = running_server
    srv._daemon._session = dict(_SESSION)
    code = ctl.main(["session"])
    out = capsys.readouterr().out
    assert code == 0
    assert out == _SESSION["text"] + "\n"


def test_main_session_none_exits_1_no_subprocess(monkeypatch, capsys, running_server):
    """No completed session → exit 1, 'error: no completed session yet' on stdout, and ZERO
    subprocesses (clipboard untouched — G1/G10 by construction: ok:false → code 1 → the
    --copy orchestration never runs)."""

    def _boom(*_a, **_k):
        raise AssertionError("subprocess spawned on the none path")

    monkeypatch.setattr(ctl.subprocess, "run", _boom)
    srv, _path = running_server   # default stub: _session is None
    code = ctl.main(["session"])
    out = capsys.readouterr().out
    assert code == 1
    assert out == "error: no completed session yet\n"


def test_main_session_truncation_warns_on_stderr(capsys, running_server):
    """Truncated session (store cap): exit 0, stdout == text exactly, the warning + the
    finals_dropped count on STDERR only (G2)."""
    srv, _path = running_server
    canned = {**_SESSION, "text": "only the newest tail", "truncated": True,
              "finals_dropped": 2}
    srv._daemon._session = canned
    code = ctl.main(["session"])
    out, err = capsys.readouterr()
    assert code == 0
    assert out == "only the newest tail\n"
    assert "truncated" in err and "2" in err
    assert "truncated" not in out


def test_main_session_copy_calls_helper_with_exact_text(monkeypatch, capsys, running_server):
    """--copy: the helper is called ONCE with EXACTLY the recovered text; stdout 'copied N chars'."""
    calls: list[str] = []

    def fake_copy(t):
        calls.append(t)
        return (True, "")

    monkeypatch.setattr(ctl, "_copy_session_to_clipboard", fake_copy)
    srv, _path = running_server
    srv._daemon._session = dict(_SESSION)
    code = ctl.main(["session", "--copy"])
    out = capsys.readouterr().out
    assert code == 0
    assert calls == [_SESSION["text"]]
    assert out == f"copied {len(_SESSION['text'])} chars\n"


def test_main_session_copy_failure_exits_1(monkeypatch, capsys, running_server):
    """A failed copy (wl-copy error / verify timeout) → exit 1, detail on stderr, no 'copied'."""
    monkeypatch.setattr(
        ctl, "_copy_session_to_clipboard", lambda t: (False, "wl-copy failed: boom")
    )
    srv, _path = running_server
    srv._daemon._session = dict(_SESSION)
    code = ctl.main(["session", "--copy"])
    out, err = capsys.readouterr()
    assert code == 1
    assert "wl-copy failed: boom" in err
    assert "copied" not in out


def test_main_session_copy_sends_copy_flag_through_socket(monkeypatch, running_server):
    """Full-stack wire pin: --copy → {"copy": true} survives send_command → _dispatch → the
    stub records session_calls == [True]."""
    monkeypatch.setattr(ctl, "_copy_session_to_clipboard", lambda t: (True, ""))
    srv, _path = running_server
    srv._daemon._session = dict(_SESSION)
    assert ctl.main(["session", "--copy"]) == 0
    assert srv._daemon.session_calls == [True]


def test_main_copy_flag_requires_session(capsys):
    """--copy with a non-session command is a usage error (64) BEFORE any socket resolution."""
    code = ctl.main(["status", "--copy"])
    err = capsys.readouterr().err
    assert code == 64
    assert "--copy" in err


# --- _copy_session_to_clipboard: fully mocked subprocess (G10) -----------------------------

def test_copy_helper_stages_exact_bytes_no_newline(monkeypatch):
    """THE clipboard contract (G3/G4/G6): wl-copy fork mode with explicit MIME, input == the
    exact UTF-8 bytes (no trailing \\n added); wl-paste --no-newline byte-verify; the ONLY
    subprocesses ever spawned are wl-copy and wl-paste (never wtype/ydotool)."""
    text = "paste me exactly\nwith a legit trailing newline\n"
    payload = text.encode("utf-8")
    calls: list[tuple[list, dict]] = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        if argv[0].endswith("wl-copy"):
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(ctl.subprocess, "run", fake_run)
    ok, detail = ctl._copy_session_to_clipboard(text)
    assert (ok, detail) == (True, "")
    copy_calls = [c for c in calls if c[0][0].endswith("wl-copy")]
    paste_calls = [c for c in calls if c[0][0].endswith("wl-paste")]
    assert len(copy_calls) == 1 and len(paste_calls) == 1
    argv, kwargs = copy_calls[0]
    assert "--type" in argv and "text/plain;charset=utf-8" in argv
    for banned in ("--primary", "--paste-once", "--trim-newline", "--foreground"):
        assert banned not in argv
    assert kwargs["input"] == payload  # EXACT bytes — no trailing b"\n" added
    paste_argv, _paste_kwargs = paste_calls[0]
    assert "--no-newline" in paste_argv
    for argv_all, _kw in calls:  # G6: only wl tools, never wtype/ydotool
        assert argv_all[0].endswith(("wl-copy", "wl-paste"))


def test_copy_helper_verify_retries_then_succeeds(monkeypatch):
    """A FRESH wl-paste connection may lag one compositor event-loop turn (G4): first readback
    mismatches, second matches → (True, '')."""
    text = "retry verify"
    payload = text.encode("utf-8")
    state = {"n": 0}

    def fake_run(argv, **kwargs):
        if argv[0].endswith("wl-paste"):
            state["n"] += 1
            out = b"stale" if state["n"] == 1 else payload
            return subprocess.CompletedProcess(argv, 0, stdout=out, stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ctl.subprocess, "run", fake_run)
    monkeypatch.setattr(ctl, "_WL_VERIFY_POLL_S", 0.0)   # no real sleeping
    ok, detail = ctl._copy_session_to_clipboard(text)
    assert (ok, detail) == (True, "")
    assert state["n"] == 2


def test_copy_helper_verify_timeout_fails(monkeypatch):
    """wl-paste never sees the bytes → bounded failure with 'verification failed' detail."""
    text = "never matches"
    bad = b"something else"

    def fake_run(argv, **kwargs):
        if argv[0].endswith("wl-paste"):
            return subprocess.CompletedProcess(argv, 0, stdout=bad, stderr=b"")
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(ctl.subprocess, "run", fake_run)
    monkeypatch.setattr(ctl, "_WL_VERIFY_DEADLINE_S", 0.05)
    monkeypatch.setattr(ctl, "_WL_VERIFY_POLL_S", 0.0)
    ok, detail = ctl._copy_session_to_clipboard(text)
    assert ok is False and "verification failed" in detail


def test_copy_helper_missing_binary(monkeypatch):
    """wl-copy absent (pinned path missing AND not on PATH) → (False, 'wl-copy not found')."""
    monkeypatch.setattr(ctl, "_WL_COPY", "/nonexistent/wl-copy")
    monkeypatch.setattr(ctl.shutil, "which", lambda name: None)
    ok, detail = ctl._copy_session_to_clipboard("anything")
    assert ok is False and "wl-copy not found" in detail


def test_copy_helper_wl_copy_error_surfaces_stderr(monkeypatch):
    """wl-copy exit 1 (e.g. not on Wayland) → the first stderr line becomes the failure detail."""
    err = b"Failed to connect to a Wayland server\n"

    def fake_run(argv, **kwargs):
        assert argv[0].endswith("wl-copy")
        return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=err)

    monkeypatch.setattr(ctl.subprocess, "run", fake_run)
    ok, detail = ctl._copy_session_to_clipboard("anything")
    assert ok is False and "Failed to connect to a Wayland server" in detail


# ===========================================================================
# P1.M1.T2.S5 — context starts (§4.8.1 A): start|start-block|start-stream
# --context-stdin. Bounded stdin reader, the start-context wire route, the
# format branch, usage pairing (64), old-daemon + uncertain-outcome handling.
# Hermetic: send paths are monkeypatched (or the in-process ControlServer stub
# is used) — NO real daemon, NO CUDA, no sleeps (bounded joins / Events only).
# ===========================================================================

_SEED_MARKER = "SEEDTEXT-MARKER-7f3a"  # a seed string asserted ABSENT from all output


def test_context_flag_on_non_start_commands_is_usage_error(monkeypatch, capsys):
    """--context-stdin with any non-start command is a usage error (64) BEFORE any socket
    I/O — mirror of the --copy check (PRD §4.8 exit-code contract; CRITICAL #10)."""

    def _boom(*a, **k):
        raise AssertionError("send paths must not be called on a usage error")

    monkeypatch.setattr(ctl, "send_command", _boom)
    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _boom)
    for argv in (
        ["toggle", "--context-stdin"],
        ["status", "--context-stdin"],
        ["stop", "--context-stdin"],
        ["quit", "--context-stdin"],
        ["cancel", "--context-stdin"],
        ["session", "--context-stdin"],
        ["session", "--copy", "--context-stdin"],  # --copy + --context-stdin together: 64
    ):
        assert ctl.main(argv) == ctl._EX_USAGE, argv
        assert capsys.readouterr().out == ""  # usage errors print to stderr only


def test_utf8_suffix_keeps_newest_4k_on_codepoint_boundary():
    """The newest 4096 BYTES survive; a cut landing mid-character drops the leading
    continuation byte(s) instead of emitting U+FFFD at the head (CRITICAL #7)."""
    s = "é" * 3000  # 6000 bytes of 2-byte chars
    out = ctl._utf8_suffix(s.encode("utf-8"))
    assert out.encode("utf-8") == s.encode("utf-8")[-4096:]  # exact newest suffix
    assert out.startswith("é")
    e = "\U0001f600" * 2000  # 8000 bytes of 4-byte chars
    out2 = ctl._utf8_suffix(e.encode("utf-8"))
    assert len(out2.encode("utf-8")) <= 4096 and out2.startswith("\U0001f600")
    odd = "a" + "é" * 3000  # 6001 bytes: the 4096-byte cut lands mid-character
    out3 = ctl._utf8_suffix(odd.encode("utf-8"))
    assert out3.startswith("é") and not out3.startswith("\ufffd")


def test_read_context_stdin_multiline_unicode_and_empty():
    """Round-trips to EOF: interior newlines survive, empty stdin is VALID ("")."""
    assert ctl._read_context_stdin(io.BytesIO("a\nb\n日本語".encode("utf-8"))) == "a\nb\n日本語"
    assert ctl._read_context_stdin(io.BytesIO(b"")) == ""
    got = ctl._read_context_stdin(io.BytesIO(b"x" * 9000))
    assert got == "x" * 4096  # only the newest 4 KiB are retained whatever the size


def test_read_context_stdin_unreadable_stream_raises_type_name():
    """A stream without .read -> ValueError carrying the exception TYPE name only."""
    with pytest.raises(ValueError, match="TypeError"):
        ctl._read_context_stdin(object())


def test_read_context_stdin_unreadable_sys_stdin_is_exit_1(monkeypatch, tmp_path, capsys):
    """Unreadable stdin fails BEFORE the socket: exit 1, zero sends (CRITICAL #8/#9)."""

    def _boom(*a, **k):
        raise AssertionError("send paths must not be called on an unreadable stdin")

    monkeypatch.setattr(ctl, "send_command", _boom)
    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _boom)
    monkeypatch.setattr(sys, "stdin", object())  # no .buffer, no .read
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert ctl.main(["start", "--context-stdin"]) == 1
    assert "TypeError" in capsys.readouterr().err


def test_read_context_stdin_deadline_is_uncertain_and_sends_nothing(
    monkeypatch, tmp_path, capsys
):
    """EOF never reached within _STDIN_DEADLINE_S -> UNCERTAIN input: ValueError BEFORE the
    socket, nothing sent, exit 1 well inside the bound (a hung producer can't hang the keybind)."""
    gate = threading.Event()  # never set: the producer never closes its pipe

    class _HangingStream:
        def read(self, _n):
            gate.wait(5.0)  # bounded so the daemon pump thread cannot outlive the test
            return b""

    def _boom(*a, **k):
        raise AssertionError("send paths must not be called on an uncertain stdin")

    monkeypatch.setattr(ctl, "send_command", _boom)
    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _boom)
    monkeypatch.setattr(sys, "stdin", _HangingStream())
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(ctl, "_STDIN_DEADLINE_S", 0.2)
    t0 = time.monotonic()
    try:
        code = ctl.main(["start-block", "--context-stdin"])
        dt = time.monotonic() - t0
    finally:
        gate.set()  # release the pump thread (daemon thread; hygiene only)
    assert code == 1
    assert dt < 1.5  # the 0.2 s budget + join slack, never the full deadline default
    err = capsys.readouterr().err
    assert "EOF" in err and "nothing was sent" in err


@pytest.mark.parametrize(
    "argv,mode",
    [
        (["start", "--context-stdin"], None),
        (["start-block", "--context-stdin"], "block"),
        (["start-stream", "--context-stdin"], "stream"),
    ],
)
def test_context_start_wires_start_context_with_mode(
    monkeypatch, tmp_path, capsys, argv, mode
):
    """Wire/CLI parity: each start variant sends EXACTLY ONE start-context line with the
    right mode extra, prints 'listening: on' + 'context: seeded', exits 0."""
    sends = []

    def _fake_send(socket_path, cmd, extra=None):
        sends.append((socket_path, cmd, extra))
        return {"ok": True, "listening": True, "context_seeded": True, "context_tokens": 7}

    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _fake_send)
    monkeypatch.setattr(ctl, "send_command", _fake_send)
    monkeypatch.setattr(ctl, "_default_control_socket_path", lambda: str(tmp_path / "c.sock"))
    monkeypatch.setattr(sys, "stdin", io.BytesIO(b"hello"))
    code = ctl.main(argv)
    out = capsys.readouterr()
    assert code == 0
    assert len(sends) == 1  # exactly one send on the happy path too
    _path, cmd, extra = sends[0]
    assert cmd == "start-context"
    assert extra["context"] == "hello"
    assert extra.get("mode") == mode
    assert out.out == "listening: on\ncontext: seeded\n"


def test_context_start_old_daemon_hint_exit_1(monkeypatch, tmp_path, capsys):
    """An OLD daemon answers unknown command: exit 1 + the stderr hint; exactly one send,
    never a retry or a plain-start fallback (CRITICAL #9)."""
    sends = []

    def _fake_send(socket_path, cmd, extra=None):
        sends.append(cmd)
        return {"ok": False, "error": "unknown command: 'start-context'"}

    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _fake_send)
    monkeypatch.setattr(ctl, "_default_control_socket_path", lambda: str(tmp_path / "c.sock"))
    monkeypatch.setattr(sys, "stdin", io.BytesIO(_SEED_MARKER.encode()))
    code = ctl.main(["start", "--context-stdin"])
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert code == 1 and sends == ["start-context"]
    assert "predates context starts" in err and "nothing was armed" in err
    assert _SEED_MARKER not in out + err  # the seed never reaches stdout/stderr


def test_context_start_timeout_is_uncertain_no_retry(monkeypatch, tmp_path, capsys):
    """Socket timeout / malformed reply -> UNCERTAIN outcome: exit 1 + 'outcome unknown',
    exactly one send, no retry (the daemon may still have completed its fenced start)."""
    sends = []

    def _raise(socket_path, cmd, extra=None):
        sends.append(cmd)
        raise ValueError("daemon wedged: no reply within 10s")

    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _raise)
    monkeypatch.setattr(ctl, "_default_control_socket_path", lambda: str(tmp_path / "c.sock"))
    monkeypatch.setattr(sys, "stdin", io.BytesIO(b"seed"))
    code = ctl.main(["start", "--context-stdin"])
    assert code == 1 and sends == ["start-context"]
    assert "outcome unknown" in capsys.readouterr().err


def test_context_start_busy_reply_exit_1(monkeypatch, tmp_path, capsys):
    """The daemon's busy rejection renders as 'error: ...' on stdout, exit 1."""

    def _fake_send(socket_path, cmd, extra=None):
        return {"ok": False, "listening": False, "context_seeded": False,
                "error": "start-context rejected: busy (arming, listening or draining)"}

    monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _fake_send)
    monkeypatch.setattr(ctl, "_default_control_socket_path", lambda: str(tmp_path / "c.sock"))
    monkeypatch.setattr(sys, "stdin", io.BytesIO(_SEED_MARKER.encode()))
    code = ctl.main(["start", "--context-stdin"])
    out = capsys.readouterr()
    assert code == 1
    assert "error: start-context rejected: busy" in out.out
    assert _SEED_MARKER not in out.out + out.err


def test_format_start_context_unseeded_reasons():
    """Pure format_result: the three reason codes + the defensive 'unknown'."""
    for reason in ("empty", "disabled", "unavailable"):
        text, code = ctl.format_result(
            "start-context",
            {"ok": True, "listening": True, "context_seeded": False,
             "context_reason": reason},
        )
        assert code == 0
        assert text == f"listening: on\ncontext: unseeded ({reason})"
    text, code = ctl.format_result(
        "start-context", {"ok": True, "listening": False, "context_seeded": False}
    )
    assert code == 0 and "unseeded (unknown)" in text


def test_context_seed_never_in_output(monkeypatch, tmp_path, capsys):
    """On every reply shape the seed string stays off stdout+stderr (CRITICAL #6); it only
    rides the wire inside the request extra."""
    for reply in (
        {"ok": False, "listening": False, "context_seeded": False,
         "error": "start-context rejected: busy (arming, listening or draining)"},
        {"ok": False, "error": "unknown command: 'start-context'"},
        {"ok": True, "listening": True, "context_seeded": False, "context_reason": "empty"},
        {"ok": True, "listening": True, "context_seeded": True, "context_tokens": 3},
    ):
        seen = {}

        def _fake_send(socket_path, cmd, extra=None, _r=reply):
            seen["extra"] = extra
            return dict(_r)

        monkeypatch.setattr(ctl, "_send_command_with_loading_hint", _fake_send)
        monkeypatch.setattr(ctl, "_default_control_socket_path", lambda: str(tmp_path / "c.sock"))
        monkeypatch.setattr(sys, "stdin", io.BytesIO(_SEED_MARKER.encode()))
        code = ctl.main(["start", "--context-stdin"])
        out = capsys.readouterr()
        assert code in (0, 1)
        assert seen["extra"]["context"] == _SEED_MARKER  # sent (on the wire), never echoed
        assert _SEED_MARKER not in out.out + out.err


def test_help_lists_context_stdin_flag(capsys):
    """--help surfaces the flag + the focus-vs-native Mode A paragraph."""
    with pytest.raises(SystemExit) as exc_info:
        ctl.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--context-stdin" in out
    assert "NOT a safe editor integration" in out


def test_context_round_trip_over_real_server(monkeypatch, capsys, running_server):
    """One real-socket round trip: the wire request reaches _dispatch and the stub's
    start_context, and the seeded reply renders through format_result."""
    srv, _path = running_server
    monkeypatch.setattr(sys, "stdin", io.BytesIO(b"piped seed\n"))
    code = ctl.main(["start", "--context-stdin"])
    out = capsys.readouterr()
    assert code == 0
    assert "listening: on" in out.out and "context: seeded" in out.out
    assert srv._daemon.calls == [("start-context", "piped seed\n", None)]  # raw wire value
    # (the CLIENT never strips — the daemon's _normalize_context owns .strip(); an echo-style
    # trailing newline must not become prompt text server-side)
