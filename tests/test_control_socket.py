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
            "listening": listening, "mode": "lite", "phase": "idle", "models_loaded": True,
            "load_error": "", "partial": "", "last_final": "", "uptime_s": 0.0,
            "device": "cuda", "compute_type": "float16", "model": "small.en",
            "mic_ok": True, "mic_error": "",
        }
    def toggle(self):
        self.calls.append("toggle"); self._listening = not self._listening  # noqa: E702
    def start(self): self.calls.append("start"); self._listening = True  # noqa: E702
    def stop(self): self.calls.append("stop"); self._listening = False  # noqa: E702
    def cancel(self):
        # P1.M2.T7.S1: mirror VoiceTypingDaemon.cancel() — records the call, returns the shape
        # dispatch passes through verbatim ({ok, listening, **status_snapshot()}).
        self.calls.append("cancel")
        return {"ok": True, "listening": self._listening, **self.status_snapshot()}
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
    assert set(r) == {"ok", "listening", "mode", "phase", "models_loaded", "load_error",
                      "partial", "last_final", "uptime_s", "device", "compute_type",
                      "model", "mic_ok", "mic_error"}   # ok + the 13-key Rev 2 snapshot


def test_dispatch_start_stop_set_listening():
    assert _disp({"cmd": "start"})["listening"] is True
    assert _disp({"cmd": "stop"})["listening"] is False


def test_dispatch_lite_commands_are_unknown_except_toggle_lite_alias():
    """Rev 2 (P1.M1.T2.S2): start-lite is gone — unknown-command reply. toggle-lite survives
    ONLY as a deprecated migration alias for `toggle` (validation Issue 2: pre-Rev-2 keybind
    wrappers still call it), so over the socket it dispatches exactly like toggle."""
    assert _disp({"cmd": "start-lite"}) == {"ok": False, "error": "unknown command: 'start-lite'"}
    assert _disp({"cmd": "toggle-lite"}) == _disp({"cmd": "toggle"})   # identical payload
    assert _disp({"cmd": "toggle-lite"})["listening"] is True           # ...and it arms


def test_dispatch_status_response_carries_mode():
    """The wire status response carries the daemon's 'mode' field.

    The shared _StubDaemon.status_snapshot() carries the Rev 2 CONSTANT 'lite'; this subclass
    proves the {'ok': True, **status_snapshot()} spread surfaces mode on the wire (the PRD §4.2
    status-payload contract) even when a daemon reports a different value.
    """
    class _ModeDaemon(_StubDaemon):
        def status_snapshot(self):
            return {**super().status_snapshot(), "mode": "other"}

    srv = daemon.ControlServer(_ModeDaemon())
    r = srv._dispatch(json.dumps({"cmd": "status"}))
    assert r["ok"] is True
    assert r.get("mode") == "other", f"status response missing 'mode': {r}"


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


def test_dispatch_empty_line():
    # BUG-005: an empty request line is just malformed JSON — it must get the standard error
    # reply, never silence (silence hangs a client forever on the timeout-less control socket).
    for line in ("", "   "):
        r = _disp(line)
        assert r["ok"] is False
        assert r["error"].startswith("malformed JSON:")


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


def test_round_trip_empty_line_gets_error_reply(server):
    # BUG-005: the reported hang — a bare newline (and a whitespace-only line) used to get NO
    # response, wedging the client on the timeout-less socket. Each must now yield exactly one
    # malformed-JSON error line (the _send helper itself is the hang repro: it blocks until a
    # reply line arrives).
    _srv, path = server
    for raw in (b"\n", b"   \n"):
        r = json.loads(_send(path, raw))
        assert r["ok"] is False
        assert r["error"].startswith("malformed JSON:")


def test_round_trip_empty_line_mid_connection(server):
    # BUG-005: an error reply mid-connection must neither kill the loop nor desync the
    # one-response-per-request-line lockstep: valid, empty, valid over ONE connection -> 3 replies.
    _srv, path = server
    payload = (
        json.dumps({"cmd": "start"}) + "\n\n" + json.dumps({"cmd": "status"}) + "\n"
    ).encode()
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(path)
    c.sendall(payload)
    data = b""
    while data.count(b"\n") < 3:
        chunk = c.recv(4096)
        if not chunk:
            break
        data += chunk
    c.close()
    lines = [ln for ln in data.decode().splitlines() if ln]
    assert len(lines) == 3
    assert json.loads(lines[0])["listening"] is True  # valid request 1 processed
    assert json.loads(lines[1])["ok"] is False        # empty line -> malformed-JSON reply
    assert json.loads(lines[2])["ok"] is True          # loop survived; valid request 2 processed


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


# --- P1.M2.T7.S1: dispatch 'cancel' -------------------------------------------------------


def test_dispatch_cancel_routes_to_daemon_cancel_and_returns_shape():
    """'cancel' dispatches to daemon.cancel() exactly once and returns its dict verbatim — the
    {ok: true, listening: true, **status} shape voicectl renders as 'listening: on' (exit 0)."""
    stub = _StubDaemon(listening=True)
    r = daemon.ControlServer(stub)._dispatch(json.dumps({"cmd": "cancel"}))
    assert stub.calls == ["cancel"]
    assert r["ok"] is True
    assert r["listening"] is True
    assert "mode" in r   # the uniform status payload rides along


def test_dispatch_cancel_disarmed_still_ok():
    """cancel while disarmed: the stub mirrors the daemon's idempotent ok (no error, no 500-style
    reply) — dispatch must not special-case the disarmed state."""
    stub = _StubDaemon(listening=False)
    r = daemon.ControlServer(stub)._dispatch(json.dumps({"cmd": "cancel"}))
    assert stub.calls == ["cancel"]
    assert r["ok"] is True and r["listening"] is False


def test_dispatch_cancel_near_miss_still_unknown():
    """Guards the unknown-command fallthrough ordering: a near-miss of 'cancel' is still unknown
    (the 'cancel' case must not shadow other commands, and vice versa)."""
    assert _disp({"cmd": "cancel-now"}) == {"ok": False, "error": "unknown command: 'cancel-now'"}
