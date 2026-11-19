"""Persistent ydotoold socket client (PRD Rev 3e — zero-spawn key events).

Socket type: AF_UNIX **SOCK_DGRAM** — this matches ydotoold's socket
($XDG_RUNTIME_DIR/.ydotool_socket, fallback /run/ydotoold.socket), whose type is
verified from kernel socket tables (/proc/net/unix / `ss -x`), NOT assumed: the
original SOCK_STREAM implementation could never connect (connect() raised
Errno 91, "Protocol wrong type for socket"), so every backspace burst silently
degraded to per-batch CLI `ydotool key` spawns.

Wire format (basis: source analysis of ydotoold's protocol by the protocol-
verification agent — PENDING independent verification against ydotoold source;
NOT captured empirically on this machine): every event is TWO 24-byte
little-endian datagrams on the persistent socket — one message per datagram
(each sendall() on a connected DGRAM socket emits exactly one datagram, which
is the per-message framing ydotoold's recv loop expects):
  event: 16 zero bytes + u16 ev_type(1=EV_KEY) + u16 keycode + i32 value(1=press/0=release)
  sync:  24 zero bytes (EV_SYN report)
This is the message shape `ydotool key -d 6 14:1 14:0` writes per event — minus
the process spawn, connect, and exit per batch. A dropped connection self-heals
on the next call; ANY failure raises and the backend falls back to the paced
CLI path.
"""
from __future__ import annotations

import logging
import os
import socket
import struct
import time

logger = logging.getLogger(__name__)

_MSG = struct.Struct("<6I")  # 24 bytes: 4 zero u32 + [code<<16|type] + value
_BACKSPACE = 14  # evdev KEY_BACKSPACE keycode
_CHAR_GAP_S = 0.012  # Rev 3d: 12 ms/char — same pace as the text path


class YdotoolClient:
    """One persistent connection to ydotoold; sends key events with pacing."""

    def __init__(self, socket_path: str | None = None) -> None:
        self._path = socket_path or os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), ".ydotool_socket"
        )
        if not os.path.exists(self._path):
            self._path = "/run/ydotoold.socket"
        self._sock: socket.socket | None = None

    def _connect(self) -> socket.socket:
        if self._sock is None:
            # SOCK_DGRAM: ydotoold's socket is a datagram socket (verified from
            # kernel socket tables); SOCK_STREAM connect() always fails with
            # Errno 91. Each sendall() on the connected DGRAM socket is one
            # datagram — the per-message framing ydotoold's recv loop expects.
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.connect(self._path)
            self._sock = s
        return self._sock

    def _send(self, ev_type: int, code: int, value: int) -> None:
        s = self._connect()
        s.sendall(_MSG.pack(0, 0, 0, 0, code << 16 | ev_type, value))
        s.sendall(_MSG.pack(0, 0, 0, 0, 0, 0))  # SYN report

    def _key(self, code: int, value: int) -> None:
        try:
            self._send(1, code, value)
        except OSError:
            self._close()
            raise  # caller falls back to the CLI path

    def _close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def press_backspace(self, n: int) -> None:
        """n backspaces at the Rev 3d pace; raises on transport failure."""
        for i in range(n):
            if i:
                time.sleep(_CHAR_GAP_S)
            self._key(_BACKSPACE, 1)
            self._key(_BACKSPACE, 0)
