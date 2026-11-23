"""Unit tests for voice_typing.ydotoold_client (PRD Rev 3e — SOCK_DGRAM fix).

100% in-process: a FakeYdotoold (threading AF_UNIX SOCK_DGRAM server on a pytest
tmp_path socket) records every datagram; the client talks ONLY to it. No real
ydotoold, no /dev/uinput, no /run/ydotoold.socket, no keystrokes. The client is
always constructed AFTER the fake server binds, so YdotoolClient.__init__'s
exists-fallback can never redirect to a real system socket.

Wire-format expectations here follow the "<6I" packing in ydotoold_client
(16 zero bytes + u16 ev_type + u16 keycode as code<<16|type + i32 value, one
event datagram followed by one all-zero EV_SYN datagram) — the basis is source
analysis, pending independent verification (see module docstring there).

Datagram count note: press_backspace(n) sends a press AND a release per char
(matching `ydotool key -d 6 14:1 14:0` CLI semantics — a lone press would
auto-repeat), so n=3 is 12 datagrams: [key(1) sync key(0) sync] x 3.

Run:  cd <repo> && .venv/bin/python -m pytest tests/test_ydotoold_client.py -v
"""
from __future__ import annotations

import os
import socket
import struct
import subprocess
import threading
import time

import pytest

from voice_typing.ydotoold_client import (
    _BACKSPACE,
    _CHAR_GAP_S,
    _MSG,
    YdotoolClient,
)
from voice_typing.typing_backends import YdotoolBackend

_RECV_TIMEOUT_S = 0.05  # per-recvfrom timeout in the server loop (stop-flag liveness)
_WAIT_DEADLINE_S = 2.0  # max wait for N datagrams to be recorded


class FakeYdotoold:
    """In-process fake ydotoold: AF_UNIX SOCK_DGRAM, records (bytes, src) per datagram."""

    def __init__(self, socket_path: str) -> None:
        self.path = socket_path
        self.datagrams: list[tuple[bytes, object]] = []
        self._stop = threading.Event()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(self.path)  # file exists from here on — safe client fallback
        self._sock.settimeout(_RECV_TIMEOUT_S)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                data, src = self._sock.recvfrom(4096)
            except socket.timeout:
                continue  # poll the stop flag at 50 ms cadence
            except OSError:
                break  # socket closed underneath us
            self.datagrams.append((data, src))

    def stop(self) -> None:
        """Close the server and unlink its socket file (kill the daemon)."""
        self._stop.set()
        self._thread.join(timeout=_WAIT_DEADLINE_S)
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    def wait_for(self, n: int) -> None:
        """Block (bounded) until n datagrams have been recorded."""
        deadline = time.monotonic() + _WAIT_DEADLINE_S
        while len(self.datagrams) < n:
            if time.monotonic() > deadline:
                raise AssertionError(
                    f"only {len(self.datagrams)} of {n} datagrams arrived "
                    f"in {_WAIT_DEADLINE_S}s"
                )
            time.sleep(0.002)

    @property
    def payloads(self) -> list[bytes]:
        return [data for data, _src in self.datagrams]


def _decode_event(data: bytes) -> dict[str, int]:
    """Decode a 24-byte '<6I' message into zeros/code/ev_type/value fields."""
    assert len(data) == _MSG.size, f"datagram must be {_MSG.size} bytes, got {len(data)}"
    fields = struct.unpack("<6I", data)
    word = fields[4]
    return {
        "zeros": fields[:4],
        "code": word >> 16,
        "ev_type": word & 0xFFFF,
        "value": fields[5],
    }


@pytest.fixture
def fake_daemon(tmp_path):
    """A live in-process fake ydotoold bound BEFORE any client is constructed."""
    srv = FakeYdotoold(str(tmp_path / "fake_ydotoold.sock"))
    yield srv
    srv.stop()


@pytest.fixture
def client(fake_daemon) -> YdotoolClient:
    # Constructed AFTER the fake binds: __init__ sees our path exists and never
    # falls back to /run/ydotoold.socket (a REAL system socket we must not touch).
    return YdotoolClient(socket_path=fake_daemon.path)


# ---------------------------------------------------------------------------
# Datagram framing & content — press_backspace(3)
# ---------------------------------------------------------------------------


def test_press_backspace_3_sends_12_datagrams_24_bytes_each(client, fake_daemon):
    client.press_backspace(3)
    fake_daemon.wait_for(12)
    payloads = fake_daemon.payloads
    assert len(payloads) == 12  # per char: press-event, SYN, release-event, SYN
    assert all(len(p) == 24 for p in payloads)


def test_press_backspace_3_key_datagrams_decode_press_then_release(client, fake_daemon):
    client.press_backspace(3)
    fake_daemon.wait_for(12)
    for char in range(3):
        press = _decode_event(fake_daemon.payloads[char * 4 + 0])
        syn_p = _decode_event(fake_daemon.payloads[char * 4 + 1])
        release = _decode_event(fake_daemon.payloads[char * 4 + 2])
        syn_r = _decode_event(fake_daemon.payloads[char * 4 + 3])
        assert press == {
            "zeros": (0, 0, 0, 0), "ev_type": 1, "code": _BACKSPACE, "value": 1
        }, f"char {char}: press event wrong"
        assert release == {
            "zeros": (0, 0, 0, 0), "ev_type": 1, "code": _BACKSPACE, "value": 0
        }, f"char {char}: release event wrong"
        assert syn_p["zeros"] == (0, 0, 0, 0) and syn_p["ev_type"] == 0 \
            and syn_p["code"] == 0 and syn_p["value"] == 0, f"char {char}: SYN after press not all-zero"
        assert syn_r == syn_p, f"char {char}: SYN after release not all-zero"


def test_press_backspace_interleaving_event_then_sync(client, fake_daemon):
    # Strict alternation: every non-zero (key) datagram is immediately followed
    # by an all-zero EV_SYN datagram — never two key datagrams in a row.
    client.press_backspace(3)
    fake_daemon.wait_for(12)
    for i, p in enumerate(fake_daemon.payloads):
        is_syn = p == b"\x00" * 24
        if i % 2 == 1:
            assert is_syn, f"datagram {i} must be a SYN (odd position)"
        else:
            assert not is_syn, f"datagram {i} must be a key event (even position)"


# ---------------------------------------------------------------------------
# One persistent connection — reused across calls, no reconnect
# ---------------------------------------------------------------------------


def test_one_connection_reused_across_two_calls(client, fake_daemon):
    client.press_backspace(1)
    fake_daemon.wait_for(4)
    sock_first = client._sock
    client.press_backspace(1)
    fake_daemon.wait_for(8)
    # No-reconnect proof: `_connect()` only ever builds a NEW socket object on a
    # reconnect, so the same object across calls means ONE persistent connection.
    # (Source addresses can't prove this here: Linux does NOT autobind unbound
    # unix DGRAM sockets on connect(), so every peer arrives with an empty
    # address — recvfrom() reports None — regardless of how many connections.)
    assert sock_first is not None
    assert client._sock is sock_first


def test_socket_is_datagram(client, fake_daemon):
    # The regression this fix pins: the client must open SOCK_DGRAM. (Every
    # passing test above implies it — STREAM could not even connect to the DGRAM
    # fake — but assert it explicitly.)
    client.press_backspace(1)
    fake_daemon.wait_for(4)
    assert client._sock is not None
    assert client._sock.type & socket.SOCK_DGRAM


# ---------------------------------------------------------------------------
# Failure path — server dies: raise + backend CLI fallback + self-heal
# ---------------------------------------------------------------------------


def test_server_killed_next_call_raises_and_backend_falls_back_to_cli(
    client, fake_daemon, monkeypatch
):
    client.press_backspace(1)  # establish the persistent connection
    fake_daemon.wait_for(4)

    calls: list[tuple[str, ...]] = []

    def fake_run(argv, **kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(args=list(argv), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    fake_daemon.stop()  # daemon dies; socket file unlinked
    backend = YdotoolBackend(client=client)
    backend.press_backspace(2)  # must NOT raise: falls back to the CLI path

    assert calls == [
        ("ydotool", "key", "-d", "6", "14:1", "14:0", "14:1", "14:0")
    ], "client failure must fall back to exactly ONE paced ydotool CLI call"
    assert client._sock is None  # failure closed the dead socket (self-heal prep)


def test_client_self_heals_after_server_restart(client, fake_daemon, tmp_path):
    client.press_backspace(1)
    fake_daemon.wait_for(4)
    first_sock = client._sock
    fake_daemon.stop()

    with pytest.raises(OSError):
        client.press_backspace(1)  # direct use: transport failure propagates
    assert client._sock is None  # dead socket closed, ready to reconnect

    # ydotoold comes back at the same path -> next call reconnects and succeeds.
    revived = FakeYdotoold(fake_daemon.path)
    try:
        client.press_backspace(1)
        revived.wait_for(4)
        assert len(revived.datagrams) == 4
        assert client._sock is not None and client._sock is not first_sock, (
            "recovery must use a NEW connection (fresh socket object)"
        )
    finally:
        revived.stop()


# ---------------------------------------------------------------------------
# Edge cases & pacing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [0, -1, -3])
def test_nonpositive_sends_no_datagrams(client, fake_daemon, n):
    client.press_backspace(n)
    time.sleep(0.05)  # bounded settle; nothing may ever arrive
    assert fake_daemon.datagrams == []


def test_press_backspace_3_latency_under_100ms(client, fake_daemon):
    t0 = time.perf_counter()
    client.press_backspace(3)
    dt = time.perf_counter() - t0
    fake_daemon.wait_for(12)
    assert dt < 0.100, f"press_backspace(3) took {dt * 1000:.1f} ms (> 100 ms budget)"
    # Pacing sanity (Rev 3d): 2 inter-char gaps of _CHAR_GAP_S each must elapse.
    assert dt >= 2 * _CHAR_GAP_S - 0.002, (
        f"{dt * 1000:.1f} ms is implausibly fast — pacing regression?"
    )
