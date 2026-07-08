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
import sys

import pytest

from voice_typing import ctl, daemon


# ---------------------------------------------------------------------------
# canned daemon status_snapshot (matches daemon.ControlServer._dispatch output)
# ---------------------------------------------------------------------------
_STATUS_ON = {
    "ok": True, "listening": True, "partial": "hello wor", "last_final": "previous sentence.",
    "uptime_s": 12.345, "device": "cuda", "compute_type": "float16",
    "final_model": "distil-large-v3", "realtime_model": "small.en",
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


def test_format_status_multiline_has_partial_and_models():
    text, code = ctl.format_result("status", _STATUS_ON)
    assert code == 0
    assert "listening: on" in text
    assert "hello wor" in text                      # partial
    assert "distil-large-v3" in text and "small.en" in text   # models loaded
    assert "cuda" in text and "float16" in text      # device + compute_type
    assert "12.345" in text                          # uptime


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
    assert "listening: off" in out and "distil-large-v3" in out


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
    with pytest.raises(SystemExit) as exc:                 # argparse usage error (exit 2, G7)
        ctl.main(["frobnicate"])
    assert exc.value.code == 2


def test_ctl_module_present_and_imports_pure():
    # Import purity: importing voice_typing.ctl must NOT pull in RealtimeSTT/torch/ctranslate2.
    assert importlib.util.find_spec("voice_typing.ctl") is not None
    assert not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]


def test_main_returns_int(monkeypatch, tmp_path):
    # main()'s return type is the exit-code contract — it must be an int in every branch.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))   # socket absent -> exit 2 path
    assert isinstance(ctl.main(["status"]), int)
