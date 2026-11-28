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
