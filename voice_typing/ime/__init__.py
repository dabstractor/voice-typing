"""voice_typing.ime — IM-v2 primary-route transport package (Mode A; R.4-decided).

Purpose: the daemon-importable transport skeleton for the input-method-v2
primary delivery route — a hand-rolled stdlib Wayland wire client (the
wlwire lineage: the daemon venv has no Wayland binding installed, so this
is the decided lineage), a pure JSONL request/reply
protocol, and a stdin/stdout IM host. This is the TRANSPORT layer only:
subprocess lifecycle (P1.M4.T1.S2), acquire/verify/show semantics (T2/T3),
and takeover detection (T4) build on this seam; none of that lives here.

Lineage: evolved from the im-lab spike — tools/im-lab/wlwire.py +
tools/im-lab/im_probe.py — kept byte-identical in tools/im-lab/ as the
durable evidence record (cite those paths; never edit them).

R.2 mechanism evidence (from the lab's 29-row matrix; carried so nobody
re-derives or over-claims it):
  - insert latency 26–40 ms from command to field text;
  - ONE atomic commit — delete_surrounding_text(before, 0) + commit_string +
    commit(serial) — corrects a whole 1024-byte span byte-exactly, with 1–2
    internal changed-signals from the toolkit;
  - surrounding_text reports cursor/anchor byte-exactly up to 1024 B;
  - commit_string generates ZERO key events, so delivery cannot self-trigger
    takeover detection.
Field-class matrix (insert capability): GTK-class apps full (insert + replace);
foot + kitty insert-only; ghostty dead.

A passing transport probe is MECHANISM EVIDENCE ONLY — never acceptance (R.2).

Re-exports the protocol vocabulary for convenience. Importing this package
requires no Wayland display (wlwire resolves WAYLAND_DISPLAY only inside
Client.__init__; the host's Client() call happens in main()/serve()).
"""
from __future__ import annotations

from .protocol import (
    LOG_CAP_BYTES,
    REQUEST_CMDS,
    SHOW_FIELDS,
    SHOW_RESULTS,
    EventLogWriter,
    ProtocolError,
    decode,
    encode,
    make_error,
    make_event,
    make_reply,
    validate_request,
)
from .takeover import (
    CHORD_KEY,
    CHORD_MODS,
    KEY_D,
    MODIFIER_KEYCODES,
    TakeoverDetector,
    TakeoverWatch,
)

__all__ = [
    "LOG_CAP_BYTES",
    "REQUEST_CMDS",
    "SHOW_FIELDS",
    "SHOW_RESULTS",
    "EventLogWriter",
    "ProtocolError",
    "TakeoverDetector",
    "TakeoverWatch",
    "CHORD_KEY",
    "CHORD_MODS",
    "KEY_D",
    "MODIFIER_KEYCODES",
    "decode",
    "encode",
    "make_error",
    "make_event",
    "make_reply",
    "validate_request",
]
