"""Byte-bounded strict-UTF-8 JSONL framing for the owner-only control socket (PRD §4.8.1 B).

MAX_FRAME_BYTES is the wire limit PER FRAME INCLUDING the terminating newline (32 KiB). FrameReader
enforces it WHILE READING raw bytes (before any unbounded buffering) over an injectable recv(), keeps
bytes past a frame's newline in `unread` so a later protocol (the native owner pump) can take the
connection over without losing coalesced frames, and RESYNCS after an oversized frame by consuming
through its newline (one error per bad request — the one-reply-per-line lockstep). Strict UTF-8
decoding is the HANDLER's job (daemon.ControlServer._handle): this module is bytes-only so a decode
failure never corrupts the handoff buffer. encode_line() is the live/event encoder with the same bound.
Errors are replyable (FrameError carries a stable reason) — never a crash, never a raw-request echo.
Also holds the v1 message validation contract (PRD §4.8.1 B/C) and the §C splice-padding + §A
code-point-safe seed helpers (P1.M1.T3.S2).
Also owns the owner connection pump: 2 s/6 s ping-lease, the single serialized bounded writer and the
sticky terminal-loss contract (P1.M1.T3.S3; PRD §4.8.1 B).

DISPATCH (P1.M1.T4.S7 — the wiring that makes this module live on the REAL socket):
  voice_typing.daemon.ControlServer._handle routes a connection by its FIRST frame: a parsed
  first frame with cmd == "editor-start" goes validate_request → daemon.reserve_native →
  write_reject (one {"ok":false,"error":code} line + EOF, nothing reserved) | OwnerPump —
  the SAME FrameReader instance is handed to the pump so `unread` coalesced bytes survive
  the handoff; the generic voicectl loop never runs on that connection again. Every other
  first frame (including native cmds from a voicectl-style client) keeps the generic
  one-reply-per-line behaviour. Exactly ONE connection may be the live owner (reserve_native
  enforces it; start/toggle/cancel from other clients return busy, §4.8.1 B).

  MESSAGE LIFECYCLE on an owner connection (who emits what, in wire order):
    starting   daemon session, ONCE, queued BEFORE begin_native_start (models may load)
    listening  daemon session via begin_native_start(on_committed), ONCE, the moment the arm
               commits — always before any final (capture opens only after LISTENING)
    final      session tick: begin_offer (mark) → send_event → finish_offer (mark-before-write);
               one outstanding, ≤ 8 unsettled, seq monotonic, ≤ 4 KiB text
    pong       pump reader, one per valid ping (each ping renews the 6 s lease)
    finishing  session, ONCE, on the DRAINING wake — ordered before any final accepted during
               that drain (the S6 teardown hook backstops a fully-settled synchronous end)
    ended      the daemon's ONE S6 teardown hook → pump.shutdown(state.frame()): last frame,
               then EOF. Never built or sent anywhere else; a no-op once the pump is lost
               (EOF/IO/FRAME/REQUEST/LEASE/WRITE losses shut the transport down first).
  Timers: lease 6 s (pump) · Start cap 30 s (daemon watchdog) · ACK 5 s (OfferQueue deadline
  checked on the session's ≤ 0.5 s tick) · write cap 2 s (writer, per whole line).

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


# --- v1 message validation (P1.M1.T3.S2; PRD §4.8.1 B wire, §4.8.1 A seed, §4.8.1 C padding) ---
# Pure, stateless validators over the DICT the handler parsed (framing/UTF-8/JSON are handled above).
# They never raise anything but ProtocolError, never coerce, never echo field values in errors.
# Reservation state (busy / duplicate_id) is NOT decided here — see P1.M1.T3.S3 / T3.S4.
import enum
import re

PROTOCOL_VERSION: int = 1   # §4.8.1 B: the only version; "version":2 → unsupported_version

MAX_CONTEXT_BYTES: int = 4 * 1024      # §4.8.1 A: newest 4 KiB of pre-caret text (UTF-8, code-point aligned)
MAX_FINAL_TEXT_BYTES: int = 4 * 1024   # §4.8.1 B: "4 KiB UTF-8 per final"


class NativeErrorCode(str, enum.Enum):
    """§4.8.1 B native error codes. busy/duplicate_id are STATE decisions (T3.S3/T3.S4), emitted elsewhere."""

    INVALID_REQUEST = "invalid_request"
    TOO_LARGE = "too_large"
    UNSUPPORTED_VERSION = "unsupported_version"
    BUSY = "busy"               # not produced by this module's validators
    DUPLICATE_ID = "duplicate_id"   # not produced by this module's validators


class EndReason(str, enum.Enum):
    """§4.8.1 B `ended` reasons."""

    STOPPED = "stopped"; IDLE = "idle"; CANCELLED = "cancelled"; TARGET_LOST = "target_lost"
    DISCONNECTED = "disconnected"; TIMEOUT = "timeout"; DELIVERY_FAILED = "delivery_failed"
    LOAD_FAILED = "load_failed"; SHUTDOWN = "shutdown"


class ContextReason(str, enum.Enum):
    """§4.8.1 A: only when context_seeded is false."""

    EMPTY = "empty"; DISABLED = "disabled"; UNAVAILABLE = "unavailable"


NATIVE_ERROR_CODES = frozenset(c.value for c in NativeErrorCode)
END_REASONS = frozenset(c.value for c in EndReason)
CONTEXT_REASONS = frozenset(c.value for c in ContextReason)

# §C splice-edge tables — EXPLICIT, so TS/Lua mirror the same scalars (never \s or %s).
OPEN_DELIMITERS = "([{"
CLOSE_PUNCTUATION = ")]},.!?;:"

# Canonical lowercase RFC 4122 v4: 8-4-4-4-12, version nibble 4, variant nibble 8/9/a/b.
# (uuid.UUID() is deliberately NOT used: it accepts braces, urn:, uppercase and hyphen-less forms.)
UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class ProtocolError(Exception):
    """A v1 validation failure. `code` ∈ NATIVE_ERROR_CODES; `detail` names field + class, NEVER the value."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def native_error_reply(code: str) -> dict:
    """The wire failure reply for a rejected FIRST request: {"ok": False, "error": "<code>"} (+ EOF by caller)."""
    return {"ok": False, "error": code}


def is_uuid_v4(value: object) -> bool:
    """True iff `value` is the canonical lowercase text form of a UUIDv4 (strict; no coercion)."""
    return isinstance(value, str) and UUID_V4_RE.match(value) is not None


def utf8_len(text: str) -> int:
    """UTF-8 byte length — the unit of every §4.8.1 size limit (text bytes, NOT JSON-escaped wire bytes)."""
    return len(text.encode("utf-8"))


def has_lone_surrogates(text: str) -> bool:
    """True if any code point is a lone (unpaired) UTF-16 surrogate — such a str cannot be UTF-8 encoded."""
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _lead_len(byte: int) -> int:
    """Expected UTF-8 sequence length from a lead byte (1 for ASCII/continuation)."""
    if byte < 0x80: return 1
    if byte < 0xC0: return 1          # continuation byte passed as lead: treat as 1 (caller walks back first)
    if byte < 0xE0: return 2
    if byte < 0xF0: return 3
    return 4


def _drop_partial_tail(raw: bytes) -> bytes:
    """Drop a trailing INCOMPLETE UTF-8 sequence (the cut landed inside a multi-byte character)."""
    i = len(raw) - 1
    while i >= 0 and (raw[i] & 0xC0) == 0x80:   # walk back over continuation bytes to the lead
        i -= 1
    if i >= 0 and len(raw) - i < _lead_len(raw[i]):
        return raw[:i]
    return raw


def truncate_utf8_suffix(text: str, max_bytes: int = MAX_CONTEXT_BYTES) -> str:
    """The NEWEST ≤max_bytes of `text`, cut on a UTF-8 code-point boundary (§4.8.1 A seed rule).

    Keeps the suffix (text nearest the caret); if the cut lands inside a multi-byte character the
    WHOLE partial leading sequence is dropped, so the result always decodes cleanly. ≤ max → unchanged.
    """
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    cut = raw[-max_bytes:]
    k = 0
    while k < len(cut) and (cut[k] & 0xC0) == 0x80:   # drop leading continuation bytes (partial seq)
        k += 1
    return cut[k:].decode("utf-8")


def _require_str(obj: dict, key: str, *, allow_empty: bool = True) -> str:
    if key not in obj:
        raise ProtocolError("invalid_request", f"missing field {key!r}")
    value = obj[key]
    if not isinstance(value, str):
        raise ProtocolError("invalid_request", f"field {key!r}: expected string")
    if has_lone_surrogates(value):
        raise ProtocolError("invalid_request", f"field {key!r}: lone surrogate")
    if not allow_empty and value == "":
        raise ProtocolError("invalid_request", f"field {key!r}: expected non-empty string")
    return value


def _require_id(obj: dict) -> str:
    value = _require_str(obj, "id", allow_empty=False)
    if not is_uuid_v4(value):
        raise ProtocolError("invalid_request", "field 'id': expected canonical UUIDv4")
    return value


def _require_int(obj: dict, key: str, *, minimum: int) -> int:
    if key not in obj:
        raise ProtocolError("invalid_request", f"missing field {key!r}")
    value = obj[key]
    if type(value) is not int:          # bool is an int subclass in Python — JSON true must NOT pass
        raise ProtocolError("invalid_request", f"field {key!r}: expected int")
    if value < minimum:
        raise ProtocolError("invalid_request", f"field {key!r}: expected int >= {minimum}")
    return value


def _reject_unknown(obj: dict, allowed: set) -> None:
    extra = sorted(set(obj) - allowed)
    if extra:
        raise ProtocolError("invalid_request", f"unknown field {extra[0]!r}")


# cmd → (allowed fields, field spec). A CLOSED schema: §4.8.1 B forbids target names, buffer text
# beyond the seed, and output-mode options in editor-start; unknown keys are invalid_request.
_REQUEST_SPECS: dict = {
    "editor-start": {"cmd", "version", "id", "context"},
    "ping": {"cmd", "id"},
    "applied": {"cmd", "id", "seq"},
    "stop": {"cmd", "id"},
    "cancel": {"cmd", "id"},
    "lost": {"cmd", "id"},
}
_POST_START_CMDS = frozenset({"ping", "applied", "stop", "cancel", "lost"})


def request_kind(obj: object) -> str | None:
    """The cmd name if `obj` is a dict with a known native cmd string, else None (no validation)."""
    if isinstance(obj, dict) and isinstance(obj.get("cmd"), str) and obj["cmd"] in _REQUEST_SPECS:
        return obj["cmd"]
    return None


def validate_request(obj: object) -> dict:
    """Validate one editor→daemon v1 request; return it unchanged or raise ProtocolError.

    Precedence (pinned by the vectors; TS/Lua MUST match): (1) object/shape/types → invalid_request,
    (2) version value → unsupported_version (editor-start only), (3) context bytes → too_large.
    `busy` and `duplicate_id` depend on reservation state and are never raised here.
    """
    if not isinstance(obj, dict):
        raise ProtocolError("invalid_request", "expected a JSON object")
    cmd = obj.get("cmd")
    if not isinstance(cmd, str) or cmd not in _REQUEST_SPECS:
        raise ProtocolError("invalid_request", "field 'cmd': unknown native command")
    # Layer 1 — shape (closed field set + strict types), checked BEFORE version/size:
    if cmd == "editor-start":
        _reject_unknown(obj, _REQUEST_SPECS["editor-start"])
        if "version" not in obj:
            raise ProtocolError("invalid_request", "missing field 'version'")
        if type(obj["version"]) is not int:
            raise ProtocolError("invalid_request", "field 'version': expected int")
        _require_id(obj)
        context = _require_str(obj, "context")
        # Layer 2 — protocol version (right type, wrong value):
        if obj["version"] != PROTOCOL_VERSION:
            raise ProtocolError("unsupported_version", "field 'version': unsupported protocol version")
        # Layer 3 — field size (UTF-8 TEXT bytes, not escaped wire bytes):
        if utf8_len(context) > MAX_CONTEXT_BYTES:
            raise ProtocolError("too_large", "field 'context': exceeds 4 KiB UTF-8")
        return obj
    _reject_unknown(obj, _REQUEST_SPECS[cmd])
    _require_id(obj)
    if cmd == "applied":
        _require_int(obj, "seq", minimum=1)
    return obj


_EVENT_SPECS: dict = {
    "starting": {"event", "id"},
    "listening": {"event", "id", "context_seeded", "context_reason"},
    "pong": {"event", "id"},
    "final": {"event", "id", "seq", "text"},
    "finishing": {"event", "id"},
    "ended": {"event", "id", "reason", "recoverable"},
}


def validate_event(obj: object) -> dict:
    """Validate one daemon→editor v1 event (used by clients on receive; by the daemon before encode_line).

    Same layer order as validate_request; `ended.reason` ∈ END_REASONS; `context_reason` present only
    when `context_seeded` is false; final `text` ≤ 4 KiB UTF-8.
    """
    if not isinstance(obj, dict):
        raise ProtocolError("invalid_request", "expected a JSON object")
    event = obj.get("event")
    if not isinstance(event, str) or event not in _EVENT_SPECS:
        raise ProtocolError("invalid_request", "field 'event': unknown native event")
    spec = _EVENT_SPECS[event]
    _reject_unknown(obj, spec)
    required = spec - {"context_reason"}          # context_reason is optional
    missing = sorted(required - set(obj))
    if missing:
        raise ProtocolError("invalid_request", f"missing field {missing[0]!r}")
    _require_id(obj)
    if event == "listening":
        if type(obj["context_seeded"]) is not bool:
            raise ProtocolError("invalid_request", "field 'context_seeded': expected bool")
        if "context_reason" in obj:
            if obj["context_seeded"] is not False:
                raise ProtocolError("invalid_request", "field 'context_reason': only when context_seeded is false")
            if not (isinstance(obj["context_reason"], str) and obj["context_reason"] in CONTEXT_REASONS):
                raise ProtocolError("invalid_request", "field 'context_reason': expected empty|disabled|unavailable")
    if event == "final":
        _require_int(obj, "seq", minimum=1)
        text = _require_str(obj, "text")
        if utf8_len(text) > MAX_FINAL_TEXT_BYTES:
            raise ProtocolError("too_large", "field 'text': exceeds 4 KiB UTF-8")
    if event == "ended":
        if not (isinstance(obj["reason"], str) and obj["reason"] in END_REASONS):
            raise ProtocolError("invalid_request", "field 'reason': unknown end reason")
        if type(obj["recoverable"]) is not bool:
            raise ProtocolError("invalid_request", "field 'recoverable': expected bool")
    return obj


def _is_ws(ch: str) -> bool:
    """Unicode whitespace per CODE POINT (Python str.isspace). Consumers mirror via the pad vectors."""
    return ch.isspace()


def splice_padding(before: str, text: str, after: str) -> tuple:
    """§4.8.1 C: (left_pad, right_pad), each '' or one ASCII space.

    No pad for empty/whitespace adjacency, after an opening delimiter '([{' (left), or before closing
    punctuation ')]},.!?;:' (right); otherwise one space where adjacent text would touch. Pure over
    code points — no normalization. An empty `text` gets no pads. The adapter inserts
    before + left_pad + text + right_pad + after and places the caret after right_pad.
    """
    if text == "":
        return ("", "")
    left = ""
    if before != "" and not _is_ws(before[-1]) and before[-1] not in OPEN_DELIMITERS:
        left = " "
    right = ""
    if after != "" and not _is_ws(after[0]) and after[0] not in CLOSE_PUNCTUATION:
        right = " "
    return (left, right)


# --- owner connection pump (P1.M1.T3.S3; PRD §4.8.1 B: lease, bounded writes, terminal callbacks) ---
# Transport ONLY: no daemon import, no reservation/offer state (T3.S4/T4.*), no ACK deadline (T4.S2).
import enum
import json
import queue
import socket
import struct
import threading
import time

PING_INTERVAL_S: float = 2.0    # §4.8.1 B: client pings every 2 s while reserved (incl. load + drain) — client reference
LEASE_S: float = 6.0            # §4.8.1 B: owner lease expires 6 s after the last valid ping (three missed pings)
WRITE_CAP_S: float = 2.0        # §4.8.1 B: "bounded socket writes (at most 2 s)" — per WHOLE encoded line
START_CAP_S: float = 30.0       # §4.8.1 B: total Start budget incl. load/priming — SESSION-owned (T3.S4/T4.S7)
ACK_DEADLINE_S: float = 5.0     # §4.8.1 B: offer ACK deadline from offer write — SESSION-owned (T4.S2), never the ping path
OUTBOUND_QUEUE_MAX: int = 64    # bounded writer queue (the 8-final live cap is the session's FIFO, not this)
_PUMP_POLL_S: float = 0.1


def deadline_after(budget: float, now: float | None = None) -> float:
    """Absolute monotonic deadline = now + budget (every timer in this module is expressed this way)."""
    return (time.monotonic() if now is None else now) + budget


def remaining(deadline: float, now: float | None = None) -> float:
    """Remaining budget to an ABSOLUTE deadline, clamped at 0 — the only way this module waits."""
    return max(0.0, deadline - (time.monotonic() if now is None else now))


class LossCause(str, enum.Enum):
    """Why an owner connection ended abnormally (sticky; first cause wins). `.end_reason` is the
    §4.8.1 B `ended.reason` the session SHOULD report (T4.S6 owns the actual `ended` frame)."""
    EOF = "eof"            # clean EOF / partial frame at EOF  -> disconnected
    IO = "io"              # recv/send OSError                 -> disconnected
    FRAME = "frame"        # oversize, invalid UTF-8, bad JSON  -> disconnected
    REQUEST = "request"    # ProtocolError, wrong id, 2nd start -> delivery_failed
    LEASE = "lease"        # 6 s without a valid ping          -> timeout
    WRITE = "write"        # 2 s whole-frame cap / full queue  -> disconnected

    @property
    def end_reason(self) -> str:
        if self is LossCause.LEASE:
            return "timeout"
        if self is LossCause.REQUEST:
            return "delivery_failed"
        return "disconnected"


class PumpClosed(Exception):
    """send_event() after the pump is lost or gracefully closing."""

    def __init__(self, cause: object) -> None:
        super().__init__(f"owner pump closed ({cause})")
        self.cause = cause


def _timeval(timeout: float) -> bytes:
    """struct timeval for SO_SNDTIMEO: whole seconds + microseconds (native long layout, Linux)."""
    sec = int(timeout)
    usec = max(0, min(999_999, int((timeout - sec) * 1_000_000)))
    return struct.pack("@ll", sec, usec)


def _arm_send_budget(conn, timeout: float) -> bool:
    """Cap the writer's NEXT blocking send at `timeout` seconds. Returns False if the budget was
    consumed by the wait itself (test doubles) — the caller re-checks the absolute deadline.

    SO_SNDTIMEO ON PURPOSE: CPython's socket.settimeout() flips O_NONBLOCK on the underlying open file
    description, which dup() SHARES with the reader — a settimeout'd writer twin would make the
    reader's blocking recv raise BlockingIOError (EAGAIN) and cause a spurious loss. SO_SNDTIMEO is a
    send-only socket option: the reader's recv is governed by SO_RCVTIMEO (never set here), so the
    reader's recv stays genuinely blocking. A budget-expired send raises BlockingIOError/TimeoutError
    (no byte accepted → retry at the same offset) or returns a PARTIAL byte count (progress → resume).
    Test doubles expose poll_send(timeout) instead (duck-typed, same contract)."""
    wait = getattr(conn, "poll_send", None)
    if wait is not None:
        return wait(timeout)
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, _timeval(timeout))
    return True


def _clear_send_budget(conn) -> None:
    """Disarm a leftover SO_SNDTIMEO so no later line inherits a stale budget (no-op for doubles)."""
    if getattr(conn, "poll_send", None) is None:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, _timeval(0.0))


def send_line_capped(conn, line: bytes, *, cap_s: float = WRITE_CAP_S,
                     clock=time.monotonic) -> bool:
    """Send ONE whole encoded line under an ABSOLUTE cap (default 2 s). True = fully sent; False = cap
    exceeded; raises OSError on a hard socket error (caller maps it). Never resends: each attempt
    resumes at the byte offset (socket.send, NOT sendall — a partial write must never be repeated).
    Per attempt the REMAINING budget is armed as the send timeout (_arm_send_budget) BEFORE the send,
    so a wedged peer can hold the line hostage for at most the cap. `conn` must be the writer's own
    socket object (see _arm_send_budget for why this is SO_SNDTIMEO and never settimeout)."""
    deadline = clock() + cap_s
    view = memoryview(line)
    sent = 0
    try:
        while sent < len(line):
            left = deadline - clock()
            if left <= 0:
                return False
            if not _arm_send_budget(conn, left):   # per-attempt budget = the REMAINING cap (absolute deadline)
                continue                            # budget burned with no byte accepted; re-check the clock
            try:
                n = conn.send(view[sent:])          # offset-tracked; the kernel reports partial progress
            except (TimeoutError, BlockingIOError):  # budget expired, nothing accepted — retry at the offset
                continue
            if n > 0:
                sent += n
        return True
    finally:
        _clear_send_budget(conn)                    # never leave a send budget armed across lines


class ThreadTimers:
    """Production timer source: one daemon threading.Timer per arm, relative to the injected clock."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock

    def arm(self, deadline: float, fire) -> object:
        timer = threading.Timer(max(0.0, deadline - self._clock()), fire)
        timer.daemon = True
        timer.start()
        return timer

    @staticmethod
    def cancel(handle) -> None:
        handle.cancel()


def write_reject(conn, code: str, *, cap_s: float = WRITE_CAP_S) -> None:
    """A REJECTED FIRST request (T4.S7 calls this; S2's code): write native_error_reply(code) under the
    write cap, then EOF. Best effort on the connection thread BEFORE any pump exists — never raises,
    never echoes the request. This is the WHOLE refusal surface: unsupported_version / too_large /
    invalid_request (validate_request), busy / duplicate_id (reserve_native) — one line, nothing
    reserved, daemon byte-identical to before the attempt."""
    try:
        send_line_capped(conn, encode_line(native_error_reply(code)), cap_s=cap_s)
        conn.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass


class OwnerPump:
    """Owner connection pump (PRD §4.8.1 B). Transport for ONE native v1 session after its first
    `editor-start` was accepted; T4.S7 constructs it on the connection thread with the live FrameReader
    (so S1's `unread` handoff bytes are preserved), queues `starting`, calls start(), then waits.

    THREAD OWNERSHIP (Mode A):
      * `owner-pump-read`  — FrameReader loop: decodes, validate_request (S2), routes. ping -> pong +
                             lease renewal; applied/stop/cancel/lost -> on_command(obj). Never writes.
      * `owner-pump-write` — the ONLY writer: drains a bounded queue of encoded lines through
                             send_line_capped on `conn.dup()`. Never reads.
      * the lease timer's thread — ThreadTimers (or the test's ManualTimers) fires _lease_fired.
    NOTHING here runs on the daemon control lock or the recorder reader thread, and nothing here takes
    a daemon lock. send_event() is non-blocking and does no socket I/O (encode_line + put_nowait), so
    the session may call it from any thread, including under the control lock or on the recorder
    reader thread (§4.8.1 B: "enqueue it without socket I/O").

    ABSOLUTE DEADLINES (Mode A): lease_deadline = last_ping_at + LEASE_S (armed at start(), re-armed
    per valid ping; a stale timer fire is ignored via a generation counter; a ping AFTER the deadline
    is loss, never a renewal). Each outbound line gets ONE deadline = clock() + write_cap_s; every
    send attempt arms its REMAINING budget as a send-only SO_SNDTIMEO cap (never settimeout, whose
    O_NONBLOCK would leak across dup() into the reader). The Start cap (30 s) and ACK
    deadline (5 s) belong to the session and are exported as constants only.

    TERMINAL CALLBACK CONTRACT (Mode A): on_loss(cause) is called EXACTLY ONCE, on the thread that
    first detected the failure (reader, writer or timer thread), after the socket has been shut down
    (so both I/O threads wake) and with NO pump lock held. Callbacks must not block, raise, or do
    socket I/O; queue the work elsewhere. After loss, send_event raises PumpClosed. A graceful
    shutdown(terminal) is NOT a loss: the terminal line (the session's `ended`) is written under the
    same cap, then the write side closes — "last frame then EOF"; an EOF observed afterwards is ignored.

    T4.S7 DISPATCH (who constructs/drives this, and the wire order — Mode A): the daemon's
    ControlServer._native_handshake constructs the pump on the connection thread with the LIVE
    FrameReader (S1's `unread` handoff), queues `starting`, then start(); begin_native_start
    (on_committed=) emits `listening` on commit; the session thread's ≤ 0.5 s tick drives
    final offers (mark-before-write through send_event), `finishing` on DRAINING, and the ACK
    deadline (q.check_deadline + the settle kick); on_command(obj) delivers the reader's
    validated applied/stop/cancel/lost frames to the session inbox (never blocks, never writes);
    on_loss(cause) routes to the S5 funnels (native_lost / terminate_native, token-fenced);
    `ended` arrives ONLY through the daemon's ONE S6 teardown hook as shutdown(state.frame()).
    Transport-level losses (EOF/IO/FRAME/REQUEST/LEASE/WRITE) shut the socket down BEFORE the
    hook runs, so a lost pump delivers EOF only — the end state lives in daemon.native_last_end()
    and status["native"]. See the module docstring for the full lifecycle table.
    """

    def __init__(self, conn, session_id: str, *, on_command, on_loss, reader=None,
                 clock=time.monotonic, timers=None, lease_s: float = LEASE_S,
                 write_cap_s: float = WRITE_CAP_S, queue_max: int = OUTBOUND_QUEUE_MAX) -> None:
        self._conn = conn                      # duck type: recv, dup, shutdown, close (writer twin: send, poll_send)
        self._wconn = conn.dup()               # D5: the writer's OWN object; the cap is a send-only option
                                               # (SO_SNDTIMEO) so NO fd flag (O_NONBLOCK) ever leaks into the reader
        self._id = session_id
        self._reader = reader if reader is not None else FrameReader(conn.recv)
        self._on_command = on_command
        self._on_loss_cb = on_loss
        self._clock = clock
        self._timers = timers if timers is not None else ThreadTimers(clock)
        self._lease_s = float(lease_s)
        self._write_cap_s = float(write_cap_s)
        self._q: queue.Queue = queue.Queue(maxsize=int(queue_max))
        self._lock = threading.Lock()          # guards ONLY the fields below; never held during I/O/callbacks
        self._lost = False
        self._closing = False
        self._cause = None
        self._detail = ""
        self._last_ping_at = float(clock())
        self._lease_gen = 0
        self._lease_timer = None
        self._threads: list = []
        self._done = 0
        self._all_done = threading.Event()

    @property
    def lost(self) -> bool:
        return self._lost

    @property
    def loss_cause(self):
        return self._cause

    @property
    def loss_detail(self) -> str:
        return self._detail

    @property
    def closed(self) -> bool:
        return self._closing

    @property
    def last_ping_at(self) -> float:
        return self._last_ping_at

    @property
    def lease_deadline(self) -> float:
        return self._last_ping_at + self._lease_s

    def start(self) -> None:
        """Arm the lease and spawn the reader + writer threads. Returns immediately. Once per pump."""
        with self._lock:
            if self._threads or self._lost or self._closing:
                raise RuntimeError("owner pump already started or closed")
            self._arm_lease()
            self._threads = [
                threading.Thread(target=self._read_loop, name="owner-pump-read", daemon=True),
                threading.Thread(target=self._write_loop, name="owner-pump-write", daemon=True),
            ]
        for t in self._threads:
            t.start()

    def send_event(self, obj: dict) -> None:
        """Queue ONE daemon->editor event (encode on the CALLER's thread; FrameError propagates for an
        oversize event). Non-blocking, no socket I/O. Raises PumpClosed when lost/closing; a full queue
        is a WRITE loss (the peer stopped reading long ago) and raises PumpClosed."""
        line = encode_line(obj)
        full = False
        with self._lock:
            if self._lost or self._closing:
                raise PumpClosed(self._cause or "closing")
            try:
                self._q.put_nowait(line)
            except queue.Full:
                full = True
        if full:
            self._on_loss(LossCause.WRITE, "outbound queue full")
            raise PumpClosed(LossCause.WRITE)

    def shutdown(self, terminal: dict | None = None) -> None:
        """Graceful end: queue `terminal` (the session's `ended` frame) as the LAST line, then EOF.
        Idempotent; no-op once lost. The terminal is queued under the same lock hold that sets
        _closing, so nothing can be queued after it and the writer cannot exit before it."""
        line = encode_line(terminal) if terminal is not None else None
        timer = None
        full = False
        with self._lock:
            if self._lost or self._closing:
                return
            self._closing = True
            self._lease_gen += 1
            timer, self._lease_timer = self._lease_timer, None
            try:
                if line is not None:
                    self._q.put_nowait(line)
            except queue.Full:
                self._closing = False
                full = True
        if timer is not None:
            self._timers.cancel(timer)
        if full:
            self._on_loss(LossCause.WRITE, "outbound queue full at shutdown")

    def wait(self, timeout: float | None = None) -> bool:
        """Block until BOTH pump threads exited. True if they did within `timeout`."""
        return self._all_done.wait(timeout)

    # --- lease (all under _lock) ---
    def _arm_lease(self) -> None:
        self._lease_gen += 1
        gen = self._lease_gen
        if self._lease_timer is not None:
            self._timers.cancel(self._lease_timer)
        self._lease_timer = self._timers.arm(self._last_ping_at + self._lease_s,
                                             lambda: self._lease_fired(gen))

    def _lease_fired(self, gen: int) -> None:
        with self._lock:
            if gen != self._lease_gen or self._lost or self._closing:
                return
        self._on_loss(LossCause.LEASE, "lease expired")

    def _renew_lease(self) -> None:
        with self._lock:
            if self._lost or self._closing:
                return
            now = self._clock()
            if now > self._last_ping_at + self._lease_s:
                expired = True          # a ping after the deadline never revives the lease
            else:
                expired = False
                self._last_ping_at = now
                self._arm_lease()
        if expired:
            self._on_loss(LossCause.LEASE, "ping after lease deadline")

    # --- sticky loss ---
    def _on_loss(self, cause: LossCause, detail: str = "") -> bool:
        with self._lock:
            if self._lost or self._closing:
                return False
            self._lost = True
            self._cause = cause
            self._detail = detail
            self._lease_gen += 1
            timer, self._lease_timer = self._lease_timer, None
        if timer is not None:
            self._timers.cancel(timer)
        try:
            self._conn.shutdown(socket.SHUT_RDWR)   # wakes recv (-> b"") and send (-> OSError)
        except OSError:
            pass
        self._on_loss_cb(cause)                    # exactly once; no lock held; detecting thread
        return True

    # --- reader thread ---
    def _read_loop(self) -> None:
        try:
            while True:
                with self._lock:
                    if self._lost or self._closing:
                        return
                try:
                    raw = self._reader.read_frame_bytes()
                except FrameError as fe:
                    if fe.reason == "eof":
                        self._on_loss(LossCause.EOF, fe.detail)
                    elif fe.reason == "frame-too-large":
                        self._on_loss(LossCause.FRAME, "frame too large")
                    else:
                        self._on_loss(LossCause.IO, fe.detail)
                    return
                if not self._handle_frame(raw):
                    return
        finally:
            self._finished()

    def _handle_frame(self, raw: bytes) -> bool:
        try:
            obj = json.loads(raw.decode("utf-8"))
            validate_request(obj)
        except (UnicodeDecodeError, ValueError):     # bad UTF-8 / bad JSON (JSONDecodeError is a ValueError)
            self._on_loss(LossCause.FRAME, "undecodable or malformed frame")
            return False
        except ProtocolError as exc:                 # right JSON, not a valid v1 request
            self._on_loss(LossCause.REQUEST, exc.detail)
            return False
        if obj["id"] != self._id:
            self._on_loss(LossCause.REQUEST, "id mismatch")
            return False
        cmd = obj["cmd"]
        if cmd == "editor-start":
            self._on_loss(LossCause.REQUEST, "duplicate start on owner connection")
            return False
        if cmd == "ping":
            self._renew_lease()
            try:
                self.send_event({"event": "pong", "id": self._id})
            except PumpClosed:
                pass
        else:                                       # applied | stop | cancel | lost
            try:
                self._on_command(obj)                # reader thread; must not block / raise / do I/O
            except Exception:
                self._on_loss(LossCause.REQUEST, "command handler failed")
                return False
        with self._lock:
            return not self._lost and not self._closing

    # --- writer thread ---
    def _write_loop(self) -> None:
        try:
            while True:
                with self._lock:
                    if self._lost or (self._closing and self._q.empty()):
                        return
                try:
                    item = self._q.get(timeout=_PUMP_POLL_S)
                except queue.Empty:
                    continue
                try:
                    sent = send_line_capped(self._wconn, item, cap_s=self._write_cap_s, clock=self._clock)
                except OSError as exc:
                    self._on_loss(LossCause.IO, type(exc).__name__)
                    return
                if not sent:
                    self._on_loss(LossCause.WRITE, "write cap exceeded")
                    return
        finally:
            try:
                self._wconn.shutdown(socket.SHUT_WR)     # peer sees EOF AFTER the last frame
            except OSError:
                pass
            try:
                self._wconn.shutdown(socket.SHUT_RDWR)   # wakes our reader
            except OSError:
                pass
            try:
                self._wconn.close()
            except OSError:
                pass
            self._finished()

    def _finished(self) -> None:
        with self._lock:
            self._done += 1
            done = self._done >= len(self._threads)
        if done:
            try:
                self._conn.close()
            except OSError:
                pass
            self._all_done.set()
