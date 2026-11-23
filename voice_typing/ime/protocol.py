"""JSONL wire contract for the ime_host subprocess (P1.M4.T1.S1) — pure stdlib.

Mode A transport: one JSON object per line in each direction over stdin/stdout
(the P1.M4.T1.S2 subprocess host speaks pipes).

Requests (every request carries a caller-supplied `id`; the reply echoes it):
  {"id": N, "cmd": "acquire"}
      → reply {ok, handle, revision, reason} — AcquireResult shape verbatim
        (voice_typing.bulk_delivery.AcquireResult); S1's handle/revision is a
        PLACEHOLDER passthrough (P1.M4.T2 owns ownership semantics).
  {"id": N, "cmd": "show", "session": ..., "utterance": ..., "seq": ...,
   "expected_revision": ..., "text": ...}
      → reply {result, t_ms} with result ∈ SHOW_RESULTS (ShowResult words
        verbatim — cross-pinned by tests/test_ime_protocol.py).
  {"id": N, "cmd": "verify"}   → reply {text_head, cursor, anchor, bytes}
  {"id": N, "cmd": "leave"}    → reply {ok: true} (keeps serving; S2 owns exit)
  {"id": N, "cmd": "ping"}     → reply {activated, dones} (health/heartbeat)
  "cancel" is RESERVED in the vocabulary (P1.M4.T3.S3 owns its semantics);
  until then it gets an error reply.

Replies carry `reply` = the cmd; events are ASYNC and id-less:
  {"ev": name, "t_ms": ..., ...}
They may interleave arbitrarily between replies. P1.M4.T4 takeover detection
subscribes to exactly these stdout lines (activate/deactivate, done,
surrounding_text, grab key/keymap/modifiers, unavailable).

Purity rule (mirror of bulk_delivery's): this module imports NOTHING from the
daemon/streaming/backends — json/time/pathlib only. Unknown request → error
reply, host keeps serving (im_probe's survive-bad-rows posture).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

REQUEST_CMDS = ("acquire", "show", "verify", "leave", "ping")   # 'cancel' RESERVED (P1.M4.T3.S3)
SHOW_RESULTS = ("applied", "unchanged", "refused", "unknown")   # == ShowResult values, verbatim
LOG_CAP_BYTES = 64 * 1024                                       # im_probe lineage
SHOW_FIELDS = ("session", "utterance", "seq", "expected_revision", "text")


class ProtocolError(ValueError):
    """JSONL framing fault (undecodable line / non-object payload)."""


def encode(obj: dict) -> bytes:
    """One JSON object → one newline-terminated UTF-8 line (embedded newlines are escaped)."""
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: str | bytes) -> dict:
    """One JSONL line → dict; ProtocolError on bad JSON or a non-object payload."""
    try:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        obj = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProtocolError(f"bad json: {e}") from e
    if not isinstance(obj, dict):
        raise ProtocolError(f"expected a JSON object, got {type(obj).__name__}")
    return obj


def make_reply(id, cmd: str, **fields) -> dict:
    """Reply line: echoes the caller id + names the cmd."""
    return {"id": id, "reply": cmd, **fields}


def make_error(id, message: str) -> dict:
    return {"id": id, "error": message}


def make_event(name: str, **fields) -> dict:
    """Async event line: id-less by contract (t_ms = monotonic ms, probe lineage)."""
    return {"ev": name, "t_ms": round(time.monotonic() * 1000, 3), **fields}


def validate_request(obj: dict) -> tuple[str | None, str | None]:
    """(cmd, error): missing id, unknown/reserved cmd, or show missing SHOW_FIELDS → error."""
    if "id" not in obj:
        return None, "missing id"
    cmd = obj.get("cmd")
    if not isinstance(cmd, str):
        return None, f"unknown request {cmd!r}"
    if cmd == "cancel":
        return None, "cancel reserved (P1.M4.T3.S3)"
    if cmd not in REQUEST_CMDS:
        return None, f"unknown request {cmd!r}"
    if cmd == "show":
        missing = [f for f in SHOW_FIELDS if f not in obj]
        if missing:
            return None, f"show missing required fields: {', '.join(missing)}"
    return cmd, None


class EventLogWriter:
    """64 KiB-capped JSONL event log (im_probe lineage; AGENTS.md Rule 3 bounded scratch).

    append(obj): no-op once the byte cap is reached; otherwise counts the
    line's bytes and appends. The cap is what makes writing under
    $XDG_RUNTIME_DIR (tmpfs = RAM) safe.
    """

    def __init__(self, path: Path | str | None):
        self.path = Path(path) if path is not None else None
        self.bytes = 0

    def append(self, obj: dict) -> None:
        if self.path is None or self.bytes >= LOG_CAP_BYTES:
            return
        data = encode(obj)
        self.bytes += len(data)
        with open(self.path, "ab") as fh:
            fh.write(data)
