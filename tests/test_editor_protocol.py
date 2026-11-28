"""Unit tests for voice_typing.editor_protocol + ControlServer._handle framing (P1.M1.T3.S1).

NO live socket listener, NO CUDA. Byte-level cases use a scripted fake recv (handoff assertions
are TIMING-DEPENDENT over a real socketpair — the kernel may coalesce sendalls into one recv, so
exact `unread` contents legitimately differ run-to-run); _handle cases use socket.socketpair()
and assert only REPLY CONTENT/COUNT, never intermediate buffers. Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol.py -q
"""
from __future__ import annotations

import json
import socket
import threading

import pytest

from voice_typing import daemon
from voice_typing.editor_protocol import (
    MAX_FRAME_BYTES,
    FrameError,
    FrameReader,
    encode_line,
)
from test_control_socket import _StubDaemon


class FakeSock:
    """Scripted recv: pops one chunk per call, b'' once exhausted (EOF). Records requested sizes."""

    def __init__(self, *chunks: bytes) -> None:
        self._chunks = list(chunks)
        self.calls: list[int] = []

    def recv(self, n: int) -> bytes:
        self.calls.append(n)
        return self._chunks.pop(0) if self._chunks else b""


class RaisingSock:
    """recv that always raises OSError (the io reason)."""

    def recv(self, n: int) -> bytes:
        raise OSError("connection reset by peer")


# --- codec: encode_line -------------------------------------------------------------------


def test_encode_line_round_trips_unicode_and_appends_newline():
    line = encode_line({"ok": True, "u": "héllo"})
    assert line.endswith(b"\n")
    assert json.loads(line.decode("utf-8")) == {"ok": True, "u": "héllo"}  # strict UTF-8 round-trip


def test_encode_line_rejects_oversize():
    with pytest.raises(FrameError) as ei:
        encode_line({"x": "y" * MAX_FRAME_BYTES})
    assert ei.value.reason == "frame-too-large"


# --- reader: reassembly + handoff (deterministic fake recv) -------------------------------


def test_reader_partial_reads_reassemble():
    f1 = b'{"cmd":"stop"}\n'
    # Frame 1 split across 3 scripted recvs (sliced from the REAL frame — never hand-typed).
    r = FrameReader(FakeSock(f1[:6], f1[6:12], f1[12:]).recv)
    assert r.read_frame_bytes() == b'{"cmd":"stop"}'
    assert r.unread == b""


def test_reader_preserves_unread_for_handoff():
    f1 = b'{"cmd":"stop"}\n'
    f2 = b'{"cmd":"status"}\n'
    # Frame 1 split twice; its tail coalesced with ALL of frame 2 in one recv.
    fs = FakeSock(f1[:10], f1[10:14], f1[14:] + f2)
    r = FrameReader(fs.recv)
    assert r.read_frame_bytes() == b'{"cmd":"stop"}'
    assert r.unread == f2  # frame 2 preserved IN FULL — the protocol-handoff seam
    assert r.read_frame_bytes() == b'{"cmd":"status"}'  # re-arms from unread, no socket read
    assert r.unread == b""
    assert len(fs.calls) == 3  # frame 2 came from the handoff buffer: no extra recv


def test_reader_coalesced_frames_in_one_recv():
    f1 = b'{"cmd":"stop"}\n'
    f2 = b'{"cmd":"status"}\n'
    fs = FakeSock(f1 + f2)  # both frames in ONE recv
    r = FrameReader(fs.recv)
    assert r.read_frame_bytes() == b'{"cmd":"stop"}'
    assert r.read_frame_bytes() == b'{"cmd":"status"}'
    assert r.unread == b""
    assert fs.calls == [4096]  # both frames served by the single recv (bounded request size)


def test_reader_recv_requests_are_bounded():
    f1 = b'{"cmd":"stop"}\n'
    fs = FakeSock(*[f1[i : i + 7] for i in range(0, len(f1), 7)])
    r = FrameReader(fs.recv)
    r.read_frame_bytes()
    assert fs.calls and all(n == 4096 for n in fs.calls)


# --- reader: the byte bound (INCLUDING newline) -------------------------------------------


def test_reader_exact_boundary_passes():
    payload = b"x" * (MAX_FRAME_BYTES - 1)  # payload MAX-1 + newline == MAX total
    r = FrameReader(FakeSock(payload + b"\n").recv)
    frame = r.read_frame_bytes()
    assert len(frame) == MAX_FRAME_BYTES - 1


def test_reader_max_payload_fails():
    payload = b"x" * MAX_FRAME_BYTES  # MAX payload + newline == MAX+1 total -> over
    r = FrameReader(FakeSock(payload + b"\n").recv)
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "frame-too-large"


# --- reader: resync after oversize (the probe-caught lockstep invariant) ------------------


def test_reader_oversize_with_newline_resyncs_then_next_frame():
    over = b"x" * (MAX_FRAME_BYTES + 5) + b"\n"
    r = FrameReader(FakeSock(over, b'{"cmd":"ok"}\n').recv)
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "frame-too-large"
    # Exactly ONE error: the next read lands on a REAL frame boundary (no phantom empty frame).
    assert r.read_frame_bytes() == b'{"cmd":"ok"}'
    assert r.unread == b""


def test_reader_oversize_coalesced_with_next_frame_resyncs():
    # Oversize frame + its newline + the NEXT VALID frame coalesced into ONE chunk.
    chunk = b"x" * (MAX_FRAME_BYTES + 10) + b"\n" + b'{"cmd":"ok"}\n'
    r = FrameReader(FakeSock(chunk).recv)
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "frame-too-large"
    assert r.read_frame_bytes() == b'{"cmd":"ok"}'
    assert r.unread == b""


def test_reader_two_oversize_frames_then_valid_lockstep():
    chunk = (
        b"x" * (MAX_FRAME_BYTES + 1)
        + b"\n"
        + b"y" * (MAX_FRAME_BYTES + 2)
        + b"\n"
        + b'{"cmd":"ok"}\n'
    )
    r = FrameReader(FakeSock(chunk).recv)
    for _ in range(2):  # exactly TWO errors (one per bad frame), no phantom frames between
        with pytest.raises(FrameError) as ei:
            r.read_frame_bytes()
        assert ei.value.reason == "frame-too-large"
    assert r.read_frame_bytes() == b'{"cmd":"ok"}'


def test_reader_oversize_without_newline_then_eof():
    r = FrameReader(FakeSock(b"x" * 40960).recv)  # > MAX bytes, NO newline ever
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "frame-too-large"
    # EOF mid-runaway: nothing to resync to -> the next read is a CLEAN eof.
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "eof"
    assert ei.value.detail == ""


# --- reader: EOF + io ----------------------------------------------------------------------


def test_reader_eof_clean():
    r = FrameReader(FakeSock().recv)
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "eof"
    assert ei.value.detail == ""


def test_reader_eof_partial():
    r = FrameReader(FakeSock(b'{"partial"').recv)
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "eof"
    assert ei.value.detail == "partial"


def test_reader_recv_oserror_is_frame_error_io():
    r = FrameReader(RaisingSock().recv)
    with pytest.raises(FrameError) as ei:
        r.read_frame_bytes()
    assert ei.value.reason == "io"


# --- ControlServer._handle (socketpair: reply content/count only) --------------------------


def _make_server() -> daemon.ControlServer:
    return daemon.ControlServer(_StubDaemon(), socket_path="/tmp/vt-test-unused.sock")


def _read_replies(client: socket.socket, n: int) -> list[str]:
    """Read exactly n reply lines (newline-terminated) from the client side."""
    client.settimeout(5.0)
    data = b""
    while data.count(b"\n") < n:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
    return [ln for ln in data.decode("utf-8", errors="replace").splitlines() if ln]


def _join(t: threading.Thread) -> None:
    t.join(timeout=5.0)
    assert not t.is_alive(), "handler thread did not exit"


def test_handle_invalid_utf8_gets_one_reply_and_continues():
    srv = _make_server()
    client, server_side = socket.socketpair()
    t = threading.Thread(target=srv._handle, args=(server_side,), daemon=True)
    t.start()
    client.sendall(b"\xff\xfe{\n" + b'{"cmd":"status"}\n')
    replies = _read_replies(client, 2)
    assert len(replies) == 2  # lockstep: one reply per frame, connection survives
    assert json.loads(replies[0]) == {"ok": False, "error": "invalid UTF-8 frame"}
    assert json.loads(replies[1])["ok"] is True  # the next frame is independent
    client.close()
    _join(t)


def test_handle_oversize_gets_one_reply_then_resyncs():
    srv = _make_server()
    client, server_side = socket.socketpair()
    t = threading.Thread(target=srv._handle, args=(server_side,), daemon=True)
    t.start()
    client.sendall(b"x" * (MAX_FRAME_BYTES + 1) + b"\n" + b'{"cmd":"status"}\n')
    replies = _read_replies(client, 2)
    assert len(replies) == 2  # exactly ONE error for the bad frame (resync — no phantom reply)
    assert json.loads(replies[0]) == {"ok": False, "error": "frame too large (max 32768 bytes)"}
    assert json.loads(replies[1])["ok"] is True
    client.close()
    _join(t)


def test_handle_partial_eof_gets_one_reply_then_closes():
    srv = _make_server()
    client, server_side = socket.socketpair()
    t = threading.Thread(target=srv._handle, args=(server_side,), daemon=True)
    t.start()
    client.sendall(b'{"partial"')
    client.shutdown(socket.SHUT_WR)  # EOF with a partial frame buffered
    replies = _read_replies(client, 1)
    assert replies == ['{"ok": false, "error": "partial frame at EOF"}']
    assert client.recv(4096) == b""  # then the connection closes
    client.close()
    _join(t)


def test_handle_error_replies_never_echo_request_bytes():
    srv = _make_server()
    client, server_side = socket.socketpair()
    t = threading.Thread(target=srv._handle, args=(server_side,), daemon=True)
    t.start()
    bad = b"\xff\xfe{garbage" + b"\n" + b"x" * (MAX_FRAME_BYTES + 1) + b"\n"
    client.sendall(bad + b'{"cmd":"status"}\n')
    replies = _read_replies(client, 3)
    joined = "\n".join(replies)
    for marker in ("garbage", "\ufffd", "x" * 64):  # no raw-request echo in ANY reply
        assert marker not in joined
    client.close()
    _join(t)


def test_handle_quit_replies_then_closes():
    srv = _make_server()
    client, server_side = socket.socketpair()
    t = threading.Thread(target=srv._handle, args=(server_side,), daemon=True)
    t.start()
    client.sendall(b'{"cmd":"quit"}\n')
    replies = _read_replies(client, 1)
    assert json.loads(replies[0])["shutting_down"] is True
    assert client.recv(4096) == b""  # reply sent, then the connection closes
    client.close()
    _join(t)
