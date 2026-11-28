"""P1.M1.T5.S1 — the §4.8.1 C owner-only capped recovery reply (`editor-recover`).

Layers (hermetic, CPU-only — NO RealtimeSTT / NO CUDA / NO XDG_RUNTIME_DIR):
  A. Pure builder/selector — build_recovery_reply / select_native_recovery /
     _encode_reply_line against real NativeRecovery stores and crafted
     NativeRecoverySnapshots. The 7 MiB cap is UNREACHABLE through the default store
     (worst-case escape 6× a 1 MiB UTF-8 cap ⇒ ≤ ~6.01 MiB escaped), so the cap path is
     exercised ONLY with a CRAFTED snapshot — never by inflating the store (GOTCHA #2).
  B. Wire — a REAL ControlServer on ONE private mkdtemp socket with a directly seeded
     NativeRecovery: the four outcomes, selection precedence (shape → busy → not_found →
     reply), non-consuming repeat reads, exact key sets, the 2 s capped write (a stalled
     reader is released; the server keeps serving), generic-path isolation (one reply per
     line; `editor-recover` as a FIRST frame never becomes a native owner), and
     privacy/no-side-effects (backend tripwire, subprocess patched to raise, caplog
     without any recovery text, status/store unchanged).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_native_recover.py -q
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time

import pytest

import test_daemon as td
from voice_typing import daemon as dm
from voice_typing.session_recovery import NativeRecovery, NativeRecoverySnapshot

SID = "123e4567-e89b-42d3-a456-426614174000"  # canonical UUIDv4 (version 4, variant 10xx)
SID2 = "223e4567-e89b-42d3-a456-426614174001"
SID3 = "323e4567-e89b-42d3-a456-426614174002"

RECOVERY_KEYS = {"ok", "id", "text", "truncated", "possibly_applied"}


# --------------------------------------------------------------------------- harness


def _no_subprocess(*a, **kw):
    """Tripwire: the recovery read must spawn NOTHING (no notify, no wtype, no clipboard)."""
    raise AssertionError("subprocess reached in an editor-recover test (side-effect)")


class _NoBackend(td._FakeBackend):
    """Tripwire: recovery text must NEVER reach the generic typing backend."""

    def type_text(self, text: str) -> None:
        pytest.fail(f"generic type_text reached in an editor-recover test: {text!r}")

    def press_backspace(self, n: int) -> None:
        pytest.fail("generic press_backspace reached in an editor-recover test")


def _seed(store: NativeRecovery, sid: str = SID) -> None:
    """retain alpha/beta, mark the first offer attempted (no verified ACK), end target_lost."""
    assert store.retain_final(sid, 1, "alpha")
    assert store.retain_final(sid, 2, "beta")
    assert store.mark_offer_attempted(sid, 1)
    store.end_session(sid, "target_lost")


@pytest.fixture()
def rc_env(monkeypatch):
    """(daemon, socket_path, control_server): real hermetic daemon + ControlServer on ONE
    private mkdtemp socket; subprocess.run/Popen patched to raise for the whole test."""
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _no_subprocess)
    tmp = tempfile.mkdtemp(prefix="vt-rc-")  # short private path; removed in the teardown
    d, _fb, _rec, _be = td._make_daemon(backend=_NoBackend())
    sock_path = os.path.join(tmp, "control.sock")
    cs = dm.ControlServer(d, socket_path=sock_path, accept_timeout=0.05)
    cs.start()
    try:
        yield d, sock_path, cs
    finally:
        cs.stop()
        shutil.rmtree(tmp, ignore_errors=True)


def _recv_line(sock: socket.socket) -> bytes:
    """Read ONE newline-terminated reply with NO 32 KiB assumption (recv-loop until \\n)."""
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    line, _, _ = bytes(buf).partition(b"\n")
    return line


def ask(sock_path: str, obj: dict, *, read: bool = True):
    """One-shot client: connect, send one JSON line; return the parsed reply (or the open
    socket when read=False — the stalled-reader case)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(sock_path)
    s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    if not read:
        return s
    line = _recv_line(s)
    s.close()
    return json.loads(line)


def _status_ok(sock_path: str) -> dict:
    return ask(sock_path, {"cmd": "status"})


# ------------------------------------------------------------- A. pure builder/selector


def test_unit_build_five_keys_and_join():
    """u1: EXACTLY {ok, id, text, truncated, possibly_applied}; text is the store's
    single-space join; flags mirror the snapshot; no sixth key ever."""
    store = NativeRecovery()
    _seed(store)
    snap = store.recover(SID)
    r = dm.build_recovery_reply(snap)
    assert set(r) == RECOVERY_KEYS
    assert r == {"ok": True, "id": SID, "text": "alpha beta",
                 "truncated": False, "possibly_applied": True}


def test_unit_escaping_is_lossless():
    """u2: quotes, backslashes, newlines, control chars, non-ASCII, U+2028 all round-trip
    through the reply line byte-for-byte (ensure_ascii=False + strict UTF-8)."""
    text = 'a"b\\c\nd\x00\x1fé中\u2028'
    snap = NativeRecoverySnapshot(SID, text, False, True, 1, "target_lost", 0.0)
    r = dm.build_recovery_reply(snap)
    line = dm._encode_reply_line(r)
    assert line.endswith(b"\n")
    assert json.loads(line.decode("utf-8"))["text"] == text


def test_unit_cap_clips_crafted_snapshot():
    """u3: the 7 MiB bound is enforced by the BUILDER (unreachable via the default store):
    a crafted snapshot whose minimal encoding exceeds the cap comes back clipped —
    start-preserving, UTF-8-safe, truncated=True, still a valid JSON line ≤ 7 MiB."""
    text = "\x01" * (2 << 20)  # escapes 6 B/char ⇒ minimal JSON ≈ 12 MiB > 7 MiB
    snap = NativeRecoverySnapshot(SID, text, False, True, 1, "target_lost", 0.0)
    r = dm.build_recovery_reply(snap)
    line = dm._encode_reply_line(r)
    assert len(line) <= dm.MAX_RECOVERY_REPLY_BYTES
    assert r["truncated"] is True
    assert len(r["text"]) > 0
    assert text.startswith(r["text"])  # kept the START
    back = json.loads(line.decode("utf-8"))  # strict decode of the clipped line
    assert back["id"] == SID and back["truncated"] is True
    # a snapshot ALREADY truncated keeps truncated=True even when no clip happens
    snap2 = NativeRecoverySnapshot(SID, "short", True, False, 1, "target_lost", 0.0)
    r2 = dm.build_recovery_reply(snap2)
    assert r2["truncated"] is True and r2["text"] == "short"


def test_unit_no_clip_near_the_boundary():
    """u4: 1 MiB of \\x01 escapes to ~6 MiB — UNDER the 7 MiB cap ⇒ byte-identical text,
    store flags untouched (truncated stays False). The clip must not fire early."""
    text = "\x01" * (1 << 20)
    snap = NativeRecoverySnapshot(SID, text, False, False, 1, "stopped", 0.0)
    r = dm.build_recovery_reply(snap)
    assert r["text"] == text and r["truncated"] is False


def test_unit_selector_precedence():
    """u5: active id → ('busy', None) (decided by active_id(), NOT by recover()); omitted
    id → the LATEST ENDED (never the active session); unknown id / empty store →
    ('not_found', None); explicit ended id → that snapshot."""
    store = NativeRecovery()
    assert dm.select_native_recovery(store, None) == ("not_found", None)
    assert dm.select_native_recovery(store, SID) == ("not_found", None)
    _seed(store)  # SID ends (alpha/beta) — the only ENDED session
    assert dm.select_native_recovery(store, SID)[0] == "ok"
    assert dm.select_native_recovery(store, None)[1].session_id == SID
    assert dm.select_native_recovery(store, SID3) == ("not_found", None)
    # NOW take the ONE active slot with SID2 (§4.8.1 B exclusivity): the active id → busy
    # while the omitted id still selects the ENDED session (never the active one).
    assert store.retain_final(SID2, 1, "x")
    assert dm.select_native_recovery(store, SID2) == ("busy", None)
    assert dm.select_native_recovery(store, None)[1].session_id == SID


# ------------------------------------------------------------------- B. wire (socket)


def test_wire_latest_ended_and_repeat(rc_env, caplog):
    """w1+w8: omitted id → the ENDED session with the exact 5-key reply; a repeat read is
    NON-CONSUMING (identical reply, store counts unchanged, status unchanged); caplog has
    codes/ids only — never any recovery text; the backend/subprocess tripwires never fire."""
    d, sock_path, _cs = rc_env
    _seed(d._native_recovery)
    counts0 = d._native_recovery.counts()
    status0 = d.status_snapshot()
    with caplog.at_level(logging.DEBUG, logger="voice_typing.daemon"):
        r1 = ask(sock_path, {"cmd": "editor-recover"})
        assert r1 == {"ok": True, "id": SID, "text": "alpha beta",
                      "truncated": False, "possibly_applied": True}
        r2 = ask(sock_path, {"cmd": "editor-recover"})
    assert r2 == r1  # non-consuming
    assert d._native_recovery.counts() == counts0
    assert d.status_snapshot() == status0
    for rec in caplog.records:
        blob = rec.getMessage()
        assert "alpha" not in blob and "beta" not in blob  # never the text


def test_wire_explicit_id_and_not_found(rc_env):
    """w2: explicit ended id → that snapshot; unknown UUIDv4 → exactly-2-key not_found."""
    d, sock_path, _cs = rc_env
    _seed(d._native_recovery)
    r = ask(sock_path, {"cmd": "editor-recover", "id": SID})
    assert r == {"ok": True, "id": SID, "text": "alpha beta",
                 "truncated": False, "possibly_applied": True}
    r = ask(sock_path, {"cmd": "editor-recover", "id": SID3})
    assert r == {"ok": False, "error": "not_found"}
    assert set(r) == {"ok", "error"}


def test_wire_busy_and_omitted_prefers_ended(rc_env):
    """w3: the ACTIVE id → busy; the omitted id still selects the ENDED session (never the
    active one) even while an active session exists."""
    d, sock_path, _cs = rc_env
    _seed(d._native_recovery)
    assert d._native_recovery.retain_final(SID2, 1, "x")  # ACTIVE, never ended
    r = ask(sock_path, {"cmd": "editor-recover", "id": SID2})
    assert r == {"ok": False, "error": "busy"}
    r = ask(sock_path, {"cmd": "editor-recover"})
    assert r["ok"] is True and r["id"] == SID  # ended session, never SID2


@pytest.mark.parametrize("bad", [
    {"cmd": "editor-recover", "id": "abc"},                       # not a UUIDv4
    {"cmd": "editor-recover", "id": 5},                           # not a str
    {"cmd": "editor-recover", "id": ""},                          # empty str
    {"cmd": "editor-recover", "id": SID.upper()},                 # not canonical lowercase
    {"cmd": "editor-recover", "extra": 1},                        # unknown key
    {"cmd": "editor-recover", "id": SID, "extra": 1},             # unknown key beside id
])
def test_wire_invalid_request_shapes(rc_env, bad):
    """w4: malformed shape → {"ok": false, "error": "invalid_request"} (validated in the
    daemon — _REQUEST_SPECS untouched), BEFORE any busy/not_found consideration."""
    d, sock_path, _cs = rc_env
    _seed(d._native_recovery)
    assert ask(sock_path, bad) == {"ok": False, "error": "invalid_request"}


def test_wire_big_reply_arrives_whole(rc_env):
    """w5: a ~600 KiB store text escapes to a >1 MiB line — far past the 32 KiB frame
    bound — and reaches the client WHOLE (the reply has its own 7 MiB bound)."""
    d, sock_path, _cs = rc_env
    big = '"\\' * 300_000  # 600_000 chars; every char escapes 2× ⇒ ~1.2 MiB line
    assert d._native_recovery.retain_final(SID, 1, big)
    d._native_recovery.end_session(SID, "target_lost")
    r = ask(sock_path, {"cmd": "editor-recover"})
    assert r["ok"] is True and r["text"] == big
    assert r["truncated"] is False and r["id"] == SID


def test_wire_stalled_reader_released_and_server_keeps_serving(rc_env, caplog):
    """w6: a client that never reads cannot wedge its connection thread: the capped whole-
    write (2 s) gives up, ONE codes-only debug line notes it, and a second client is still
    served immediately."""
    d, sock_path, _cs = rc_env
    big = "\x01" * 400_000  # escapes to ~2.4 MiB — cannot fit any socket buffer at once
    assert d._native_recovery.retain_final(SID, 1, big)  # BEFORE end_session (an ended id stays closed)
    d._native_recovery.end_session(SID, "target_lost")
    with caplog.at_level(logging.DEBUG, logger="voice_typing.daemon"):
        stalled = ask(sock_path, {"cmd": "editor-recover"}, read=False)  # never reads
        t0 = time.monotonic()
        while time.monotonic() - t0 < 6.0:
            if any("write" in r.getMessage().lower() for r in caplog.records):
                break
            time.sleep(0.05)
        r = _status_ok(sock_path)  # a second client must NOT wait behind the stalled one
    assert r.get("ok") is True
    assert any("write" in rec.getMessage().lower() for rec in caplog.records), \
        "the capped writer never released within its cap"
    assert time.monotonic() - t0 < 6.0
    assert "alpha" not in " ".join(rec.getMessage() for rec in caplog.records)
    stalled.close()  # let the worker see EOF and exit


def test_wire_generic_isolation_one_reply_per_line(rc_env):
    """w7a: on ONE connection, status → editor-recover → status each get exactly one
    ordinary reply, in order — the recovery read is just another generic command."""
    d, sock_path, _cs = rc_env
    _seed(d._native_recovery)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(sock_path)
    try:
        replies = []
        for req in ({"cmd": "status"}, {"cmd": "editor-recover"}, {"cmd": "status"}):
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            replies.append(json.loads(_recv_line(s).decode("utf-8")))
    finally:
        s.close()
    status1, rec, status2 = replies
    assert status1 == status2 and status1.get("ok") is True and "listening" in status1
    assert set(rec) == RECOVERY_KEYS and rec["id"] == SID and rec["text"] == "alpha beta"


def test_wire_recover_first_frame_never_owner(rc_env):
    """w7b: S7's first-frame rule keys on editor-start ONLY — an editor-recover FIRST
    frame keeps the connection generic (status still answers on the same connection; no
    native owner session is ever created)."""
    d, sock_path, cs = rc_env
    _seed(d._native_recovery)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(sock_path)
    try:
        s.sendall(b'{"cmd":"editor-recover"}\n')  # FIRST frame on this connection
        r = json.loads(_recv_line(s).decode("utf-8"))
        assert r["ok"] is True and r["id"] == SID
        s.sendall(b'{"cmd":"status"}\n')  # SAME connection — still the generic loop
        r2 = json.loads(_recv_line(s).decode("utf-8"))
        assert r2.get("ok") is True and "listening" in r2
    finally:
        s.close()
    assert cs._sessions == {}  # no native owner was ever reserved


def test_wire_read_is_silent_on_text_in_errors(rc_env, caplog):
    """w8b: the failure paths log the code and the id only — no text, no context."""
    d, sock_path, _cs = rc_env
    _seed(d._native_recovery)
    with caplog.at_level(logging.DEBUG, logger="voice_typing.daemon"):
        assert ask(sock_path, {"cmd": "editor-recover", "id": SID3}) == \
            {"ok": False, "error": "not_found"}
        assert d._native_recovery.retain_final(SID2, 1, "x")
        assert ask(sock_path, {"cmd": "editor-recover", "id": SID2}) == \
            {"ok": False, "error": "busy"}
    for rec in caplog.records:
        blob = rec.getMessage()
        assert "alpha" not in blob and "beta" not in blob and "x" not in blob.replace("id=", "")
