"""Byte-bounded strict-UTF-8 JSONL framing for the owner-only control socket (PRD §4.8.1 B).

MAX_FRAME_BYTES is the wire limit PER FRAME INCLUDING the terminating newline (32 KiB). FrameReader
enforces it WHILE READING raw bytes (before any unbounded buffering) over an injectable recv(), keeps
bytes past a frame's newline in `unread` so a later protocol (the native owner pump) can take the
connection over without losing coalesced frames, and RESYNCS after an oversized frame by consuming
through its newline (one error per bad request — the one-reply-per-line lockstep). Strict UTF-8
decoding is the HANDLER's job (daemon.ControlServer._handle): this module is bytes-only so a decode
failure never corrupts the handoff buffer. encode_line() is the live/event encoder with the same bound.
Errors are replyable (FrameError carries a stable reason) — never a crash, never a raw-request echo.
Pure stdlib (json). No sockets are opened here; tests inject recv.
"""
from __future__ import annotations

import json
from collections.abc import Callable

MAX_FRAME_BYTES: int = 32 * 1024  # PRD §4.8.1 B: per request and live event, INCLUDING newline


class FrameError(Exception):
    """A framed, replyable protocol error. `reason` is a stable code; `detail` is short, never raw bytes."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class FrameReader:
    """Bytes-only JSONL frame reader: byte-bounded while reading; preserves post-newline bytes."""

    def __init__(
        self,
        recv: Callable[[int], bytes],
        *,
        max_bytes: int = MAX_FRAME_BYTES,
        chunk_size: int = 4096,
    ) -> None:
        self._recv = recv
        self._max = int(max_bytes)
        self._chunk = int(chunk_size)
        self._unread = b""  # bytes after the last consumed newline — the protocol-handoff seam

    @property
    def unread(self) -> bytes:
        return self._unread

    def read_frame_bytes(self) -> bytes:
        """Return one frame (sans newline). Raises FrameError; never buffers past the cap."""
        buf = bytearray(self._unread)
        self._unread = b""
        while True:
            i = buf.find(b"\n")
            if i != -1:
                frame = bytes(buf[:i])
                self._unread = bytes(buf[i + 1 :])  # resynced: the buffer already sits past this frame
                if len(frame) + 1 > self._max:  # INCLUDING the newline
                    raise FrameError("frame-too-large")
                return frame
            if len(buf) + 1 > self._max:  # no newline yet; the NEXT byte would exceed the cap
                self._drain_runaway(buf)  # resync THROUGH the offending newline
                raise FrameError("frame-too-large")
            try:
                chunk = self._recv(self._chunk)
            except OSError as exc:
                raise FrameError("io", str(exc)) from exc
            if not chunk:
                raise FrameError("eof", "partial" if buf else "")
            buf += chunk

    def _drain_runaway(self, buf: bytearray) -> None:
        """Consume an oversized frame through its newline so the next read starts at a real boundary.

        Without this, the runaway frame's tail + newline stay unread and the next read returns a
        PHANTOM EMPTY frame -> a second, spurious reply (two replies for one bad request).
        """
        while True:
            i = buf.find(b"\n")
            if i != -1:
                self._unread = bytes(buf[i + 1 :])
                return
            try:
                chunk = self._recv(self._chunk)
            except OSError:
                self._unread = b""
                return
            if not chunk:  # EOF mid-runaway: nothing to resync to
                self._unread = b""
                return
            buf += chunk


def encode_line(obj: dict) -> bytes:
    """Encode one reply/event as ONE UTF-8 JSON line (ensure_ascii=False) + '\\n'. Bounded by MAX_FRAME_BYTES."""
    line = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
    if len(line) > MAX_FRAME_BYTES:
        raise FrameError("frame-too-large")
    return line
