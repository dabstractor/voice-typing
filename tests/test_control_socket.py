"""Unit + integration tests for voice_typing.daemon.ControlServer (P1.M4.T2.S1).

Three layers (research §8):
  A. _dispatch() logic — no socket; a _StubDaemon records calls + returns canned status.
  B. Real AF_UNIX round-trip — ControlServer on a tmp_path socket_path; a client connects,
     sends one JSON line, reads one response line, json.loads, asserts.
  C. Lifecycle/hardening — idempotent start, dir 0700 / socket 0600, stale-.sock recovery,
     clean stop (select-poll) joins the thread <1 s + unlinks the file.

NO RealtimeSTT / NO CUDA / NO XDG_RUNTIME_DIR (explicit socket_path under tmp_path).
Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_control_socket.py -v
"""
from __future__ import annotations

import json
import os
import socket
import time as _time

import pytest

from voice_typing import daemon


class _StubDaemon:
    """Duck-type VoiceTypingDaemon for dispatch tests (no recorder, no CUDA)."""
    def __init__(self, *, listening=False, snapshot=None):
        self.calls: list[str] = []
        self._listening = listening
        self._snapshot = snapshot or {
            "listening": listening, "partial": "", "last_final": "",
            "uptime_s": 0.0, "device": "cuda", "compute_type": "float16",
            "final_model": "distil-large-v3", "realtime_model": "small.en",
        }
    def toggle(self):
        self.calls.append("toggle"); self._listening = not self._listening  # noqa: E702
    def start(self): self.calls.append("start"); self._listening = True  # noqa: E702
    def start_lite(self): self.calls.append("start-lite"); self._listening = True  # noqa: E702
    def toggle_lite(self): self.calls.append("toggle-lite"); self._listening = not self._listening  # noqa: E702
    def stop(self): self.calls.append("stop"); self._listening = False  # noqa: E702
    def request_shutdown(self): self.calls.append("quit")
    def is_listening(self): return self._listening
    def status_snapshot(self):
        s = dict(self._snapshot); s["listening"] = self._listening; return s  # noqa: E702


def _wait_for(predicate, timeout=2.0, interval=0.01):
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if predicate():
            return True
        _time.sleep(interval)
    return predicate()


def _send(path, msg_obj_or_bytes):
    """One client round-trip: connect, send one line, read one response line, close."""
    raw = msg_obj_or_bytes if isinstance(msg_obj_or_bytes, bytes) else (
        json.dumps(msg_obj_or_bytes) + "\n"
    ).encode()
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(path)
    c.sendall(raw)
    data = b""
    while not data.endswith(b"\n"):
        chunk = c.recv(4096)
        if not chunk:
            break
        data += chunk
    c.close()
    return data.decode().strip()


def _send_lines(path, *objs):
    """Send multiple JSON lines in one connection; return the list of response lines."""
    payload = b"".join((json.dumps(o) + "\n").encode() for o in objs)
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(path)
    c.sendall(payload)
    data = b""
    while data.count(b"\n") < len(objs):
        chunk = c.recv(4096)
        if not chunk:
            break
        data += chunk
    c.close()
    return [ln for ln in data.decode().splitlines() if ln]


def stat_is_socket(p):
    import stat
    return stat.S_ISSOCK(os.stat(p).st_mode)


@pytest.fixture
def server(tmp_path):
    """A ControlServer on a tmp_path socket backed by a _StubDaemon."""
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    yield srv, path
    srv.stop()


# --- A. dispatch logic (no socket) --------------------------------------------------------

def _disp(msg_obj_or_str):
    return daemon.ControlServer(_StubDaemon())._dispatch(
        msg_obj_or_str if isinstance(msg_obj_or_str, str) else json.dumps(msg_obj_or_str)
    )


def test_dispatch_toggle():
    r = _disp({"cmd": "toggle"})
    assert r["ok"] is True and r["listening"] is True and "device" in r   # uniform payload


def test_dispatch_status_has_all_keys():
    r = _disp({"cmd": "status"})
    assert set(r) == {"ok", "listening", "partial", "last_final", "uptime_s", "device",
                      "compute_type", "final_model", "realtime_model"}


def test_dispatch_start_stop_set_listening():
    assert _disp({"cmd": "start"})["listening"] is True
    assert _disp({"cmd": "stop"})["listening"] is False


def test_dispatch_lite_commands_call_daemon(monkeypatch):
    """toggle-lite / start-lite dispatch to the daemon's lite arm methods (PRD §4.2ter)."""
    d = _StubDaemon()
    srv = daemon.ControlServer(d)
    assert srv._dispatch(json.dumps({"cmd": "start-lite"}))["ok"] is True
    assert d.calls == ["start-lite"]
    d2 = _StubDaemon()
    srv2 = daemon.ControlServer(d2)
    assert srv2._dispatch(json.dumps({"cmd": "toggle-lite"}))["ok"] is True
    assert d2.calls == ["toggle-lite"]


def test_dispatch_quit_calls_request_shutdown():
    d = _StubDaemon()
    daemon.ControlServer(d)._dispatch(json.dumps({"cmd": "quit"}))
    assert d.calls == ["quit"]
    r = daemon.ControlServer(_StubDaemon())._dispatch(json.dumps({"cmd": "quit"}))
    assert r == {"ok": True, "shutting_down": True}


def test_dispatch_unknown_command():
    assert _disp({"cmd": "frobnicate"}) == {"ok": False, "error": "unknown command: 'frobnicate'"}


def test_dispatch_missing_cmd():
    assert _disp({})["ok"] is False and "unknown command" in _disp({})["error"]


def test_dispatch_malformed_json():
    r = _disp("not json{")
    assert r["ok"] is False and r["error"].startswith("malformed JSON:")


def test_dispatch_non_dict_json():
    for bad in ('"a string"', "42", "[1,2]"):
        assert _disp(bad) == {"ok": False, "error": "request must be a JSON object"}


# --- B. real-socket round-trip ------------------------------------------------------------

def test_round_trip_status(server):
    _srv, path = server
    r = json.loads(_send(path, {"cmd": "status"}))
    assert r["ok"] is True and r["device"] == "cuda"


def test_round_trip_toggle_then_status(server):
    _srv, path = server
    json.loads(_send(path, {"cmd": "toggle"}))      # arms
    r = json.loads(_send(path, {"cmd": "status"}))
    assert r["listening"] is True


def test_round_trip_malformed_over_wire(server):
    _srv, path = server
    r = json.loads(_send(path, b"garbled\n"))
    assert r["ok"] is False


def test_round_trip_multi_line_one_connection(server):
    _srv, path = server
    lines = _send_lines(path, {"cmd": "start"}, {"cmd": "stop"}, {"cmd": "status"})
    assert len(lines) == 3
    assert json.loads(lines[0])["listening"] is True
    assert json.loads(lines[1])["listening"] is False


def test_round_trip_quit(server):
    _srv, path = server
    r = json.loads(_send(path, {"cmd": "quit"}))
    assert r == {"ok": True, "shutting_down": True}


# --- C. lifecycle / hardening -------------------------------------------------------------

def test_start_creates_dir_0700_and_socket_0600(tmp_path):
    path = str(tmp_path / "sub" / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    try:
        assert oct(os.stat(tmp_path / "sub").st_mode & 0o777) == "0o700"
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    finally:
        srv.stop()


def test_start_recovers_stale_socket_file(tmp_path):
    path = str(tmp_path / "control.sock")
    open(path, "w").close()                # pre-existing stale file -> would block bind
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    try:
        assert os.path.exists(path) and stat_is_socket(path)
    finally:
        srv.stop()


def test_start_is_idempotent(tmp_path):
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    t1 = srv._thread
    srv.start()          # second start is a no-op
    t2 = srv._thread
    assert t1 is t2
    srv.stop()


def test_stop_joins_thread_and_unlinks(tmp_path):
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    srv.stop()
    assert srv._thread is not None and not srv._thread.is_alive()
    assert not os.path.exists(path)


def test_default_socket_path_honors_xdg(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/fake-xdg-123")
    assert daemon._default_control_socket_path() == "/tmp/fake-xdg-123/voice-typing/control.sock"


def test_default_socket_path_raises_when_xdg_unset(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with pytest.raises(RuntimeError):
        daemon._default_control_socket_path()
