"""Persistent ydotoold socket client (PRD Rev 3e — zero-spawn key events).

Wire protocol (captured empirically via strace from ydotool 1.x on this machine):
every event is TWO 24-byte little-endian messages on a persistent AF_UNIX socket
($XDG_RUNTIME_DIR/.ydotool_socket, fallback /run/ydotoold.socket):
  event: 16 zero bytes + u16 ev_type(1=EV_KEY) + u16 keycode + i32 value(1=press/0=release)
  sync:  24 zero bytes (EV_SYN report)
This is exactly what `ydotool key -d 6 14:1 14:0` writes per event — minus the
process spawn, connect, and exit per batch (the last per-event spawn overhead;
PRD Rev 3d). A dropped connection self-heals on the next call; ANY failure
raises and the backend falls back to the paced CLI path.
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
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
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
