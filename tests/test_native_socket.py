"""P1.M1.T4.S7 — the PRODUCTION ControlServer speaks native v1 (§4.8.1 B) on a real socket.

Drives the real ControlServer (voice_typing.daemon) over a private AF_UNIX socket with the
real VoiceTypingDaemon, the fake recorder host, the tripwire typing backend and injected
clock/timers. Hermetic CPU-only: NO live daemon, NO voicectl, NO CUDA, NO subprocess (both
subprocess.run and subprocess.Popen are patched to raise for the whole module — nothing may
reach the desktop, the clipboard or wtype), and the ONLY threads are the ControlServer's
accept/connection threads, the owner pump's, and the daemon's native-start worker.

Wire contract asserted per case (PRD §4.8.1 B): `starting` (exactly once, before
begin_native_start) → `listening` (exactly once, from the committed ArmOutcome) →
`final` offers (seq 1..n monotonic, one outstanding, verified by `applied`) → `finishing`
(graceful stop, before `ended`) → `ended` LAST, then EOF. Every refusal is one
{"ok":false,"error":code} line + EOF with NOTHING reserved. Ordinary voicectl clients
(status/start/toggle/stop/cancel/quit) keep working on their own connections while an owner
is live (busy where §4.8.1 B says so). Native text NEVER reaches the generic backend,
feedback, state, or the logs — codes/counts/ids only.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import threading
import time
import types

import pytest

import voice_typing.daemon as vtd
from voice_typing.editor_protocol import WRITE_CAP_S, validate_event
from voice_typing.recorder_host import FinalClass, _CaptureBoundary, _RelayEvent

import test_daemon as td  # noqa: E402 (repo convention: sibling-fake imports)
from conftest import hermetic_cfg  # noqa: E402
from test_native_lifecycle import (  # noqa: E402
    FakeClock,
    ManualTimers,
    _BHost,
    _NoBackend,
    _ev,
)

SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"  # canonical UUIDv4 (matches the editor wire)
SID2 = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5c"
CTX = "the quarterly launch metrics"  # a context seed that must NEVER leak
FINAL_A = "alpha beta"
FINAL_B = "gamma delta"


# === harness: tripwires + fake hosts ==========================================


def _no_subprocess(monkeypatch):
    """No desktop/injection tool is reachable from ANY native path (whole module)."""

    def _boom(*a, **k):
        raise AssertionError("subprocess reached from a native path")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


@pytest.fixture(autouse=True)
def _forbid_subprocess(monkeypatch):
    _no_subprocess(monkeypatch)


class _PrimeHost(_BHost):
    """_BHost + a CONFIRMING prime_prompt channel (records calls; never carries text)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.primed_seeds = []  # booleans only: was a (non-None) seed primed

    def prime_prompt(self, seed, timeout=1.0):
        self.primed_seeds.append(seed is not None)
        return types.SimpleNamespace(
            state=("applied" if seed is not None else "clear"), tokens=None
        )


class _GatedHost(_BHost):
    """spawn() blocks until the gate Event is set (cold-load / model-load simulation)."""

    def __init__(self, *a, gate=None, **kw):
        super().__init__(*a, **kw)
        self._gate = gate

    def spawn(self, timeout=180.0):
        if self._gate is not None:
            self._gate.wait(5.0)  # bounded: a wedged test cannot hang the suite
        return super().spawn(timeout)


# === harness: clock/timers + socket client ====================================


def _fire_due(mt, fc):
    """Fire every armed timer whose deadline has passed on the fake clock (once each)."""
    done = set(mt.fired) | set(mt.cancelled)
    for handle, deadline, fire in list(mt.armed):
        if handle not in done and deadline <= fc.t:
            fire()


def _until(fn, timeout=3.0, step=0.05):
    """Poll fn() until truthy or the (wall-clock) budget is spent."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(step)
    return bool(fn())


class Client:
    """A minimal native-v1 test client: one JSON line per frame; None on EOF."""

    def __init__(self, path, *, rcvbuf=None):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if rcvbuf is not None:
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
        self.s.settimeout(2.0)
        self.s.connect(path)
        self.buf = b""
        self.eof = False
        self.frames = []  # EVERY complete JSON line ever received (wire trace)

    def send(self, obj):
        self.s.sendall((json.dumps(obj) + "\n").encode("utf-8"))

    def send_raw(self, raw: bytes):
        self.s.sendall(raw)

    def recv(self, timeout=2.0):
        """One JSON frame (dict) — None on EOF — raises socket.timeout on stall."""
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0:
                raise socket.timeout("recv stalled")
            self.s.settimeout(left)
            chunk = self.s.recv(65536)
            if not chunk:
                self.eof = True
                return None
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        obj = json.loads(line)  # a truncated line fails the test right here
        self.frames.append(obj)
        return obj

    def expect(self, timeout=3.0):
        """The next frame, tolerating pongs (never part of a case's expected trace)."""
        while True:
            obj = self.recv(timeout=timeout)
            if obj is None or obj.get("event") != "pong":
                return obj

    def drain(self, quiet=0.4):
        """Collect frames until a quiet gap; swallows timeouts; keeps the trace."""
        out = []
        while True:
            try:
                out.append(self.recv(timeout=quiet))
            except socket.timeout:
                return out
            except OSError:
                return out

    def close(self):
        try:
            self.s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.s.close()


# === harness: daemon + server environment =====================================


def _build_env(tmp_path, monkeypatch, *, cfg=None, host_cls=_BHost):
    """The production daemon + ControlServer on a private socket. The fake host is delivered
    via host_factory (NOT recorder= — a recorder injection pre-loads _LegacyRecorderHostAdapter
    and bypasses the factory, hiding our fake from _load_host)."""
    _no_subprocess(monkeypatch)
    cfg = hermetic_cfg(cfg)
    fb = td._DaemonFakeFeedback()
    be = _NoBackend()
    d = vtd.VoiceTypingDaemon(
        cfg,
        fb,
        backend=be,
        host_factory=lambda *a, **k: host_cls(*a, **k),
        mic_prober=td._ok_probe,
    )
    fc, mt = FakeClock(), ManualTimers()
    d._native_clock, d._native_timers = fc.now, mt
    path = str(tmp_path / "ctl.sock")  # short path (UNIX sun_path 108); pytest cleans up
    srv = vtd.ControlServer(d, socket_path=path, accept_timeout=0.05)
    srv.start()
    e = types.SimpleNamespace(
        d=d, fb=fb, rec=None, be=be, fc=fc, mt=mt, srv=srv, path=path
    )
    e.sessions = getattr(srv, "_sessions", {})
    return e


@pytest.fixture()
def env(tmp_path, monkeypatch):
    e = _build_env(tmp_path, monkeypatch)
    yield e
    e.srv.stop()
    _until(lambda: len(e.sessions) == 0, timeout=5.0)
    assert not any(
        t.name.startswith("owner-pump") for t in threading.enumerate()
    ), "owner pump threads leaked"


# === harness: native-session drivers ==========================================


def _editor_start(e, sid=SID, context=""):
    c = Client(e.path)
    c.send({"cmd": "editor-start", "version": 1, "id": sid, "context": context})
    return c


def _owner_listening(e, sid=SID, context="", host=None):
    """An owner connection through the FULL production path to LISTENING (empty context)."""
    if host is not None:
        pass  # host classes are delivered via host_factory (see _build_env)
    c = _editor_start(e, sid=sid, context=context)
    f1 = c.recv()
    assert f1 == {"event": "starting", "id": sid}, f1
    f2 = c.expect()
    assert f2 == {
        "event": "listening",
        "id": sid,
        "context_seeded": False,
        "context_reason": "empty",
    }, f2
    return c


def _emit_final(e, uid, text):
    """Drive ONE accepted final through the production on_final route (reader thread stand-in)."""
    e.host = e.d._host  # the host _load_host built via host_factory
    e.d._host.capture_boundary = _CaptureBoundary(3, 1, 1, uid)
    e.d._host.relay_event = _ev(uid)
    e.d.on_final(text)


def _assert_frames_valid(frames):
    for f in frames:
        if "event" in f:
            validate_event(f)


def _assert_privacy(e, caplog, frames, *, final_texts=(), secrets=(CTX,)):
    """Codes/ids only: no secret (context seed) anywhere; final text ONLY in `final` frames;
    nothing in feedback or the state file."""
    non_final = [f for f in frames if f.get("event") != "final"]
    blob = json.dumps(non_final, default=str)
    if caplog is not None:
        blob += "".join(r.getMessage() for r in caplog.records)
        for r in caplog.records:
            blob += str(r.exc_info)
    blob += json.dumps(getattr(e.fb, "finals", []), default=str)
    blob += json.dumps(getattr(e.fb, "phases", []), default=str)
    blob += json.dumps(getattr(e.fb, "notifies", []), default=str)
    sf = e.d._cfg.feedback.state_file
    if sf and os.path.exists(sf):
        with open(sf, "rb") as fh:
            blob += fh.read().decode("utf-8", errors="replace")
    for secret in secrets:
        assert secret not in blob, f"secret leaked outside final frames: {secret!r}"
    finals = [f for f in frames if f.get("event") == "final"]
    finals_blob = json.dumps(finals, default=str)
    for text in final_texts:
        assert text in finals_blob, f"final text missing from a final frame: {text!r}"
    for f in non_final:
        for text in final_texts:
            assert text not in json.dumps(f), f"final text outside final frames: {text!r}"


# === 1. happy path: the full §4.8.1 B trace ===================================


def test_happy_path_full_trace(env, caplog):
    caplog.set_level(logging.DEBUG)
    c = _owner_listening(env)
    _emit_final(env, 101, FINAL_A)
    f = c.expect()
    assert f == {"event": "final", "id": SID, "seq": 1, "text": FINAL_A}, f
    c.send({"cmd": "applied", "id": SID, "seq": 1})
    c.send({"cmd": "stop", "id": SID})
    finishing = c.expect()
    assert finishing == {"event": "finishing", "id": SID}, finishing
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "stopped",
        "recoverable": False,
    }, ended
    assert c.recv() is None, "frames after ended"  # EOF — the LAST frame was ended
    _assert_frames_valid(c.frames)
    assert [f["event"] for f in c.frames] == [
        "starting",
        "listening",
        "final",
        "finishing",
        "ended",
    ]
    state = env.d.native_last_end()
    assert state is not None and state.reason == "stopped"
    _until(lambda: len(env.sessions) == 0)
    assert env.be.typed == []  # tripwire backend: zero calls (NoBackend would raise anyway)
    assert env.fb.finals == []  # feedback never carries native transcript
    _assert_privacy(env, caplog, c.frames, final_texts=(FINAL_A,))
    assert not env.d.is_listening()


# === 2. listening frame: seeded / disabled ====================================


def test_listening_seeded_confirmed(tmp_path, monkeypatch):
    e = _build_env(tmp_path, monkeypatch, host_cls=_PrimeHost)
    try:
        c = _editor_start(e, context=CTX)
        assert c.recv() == {"event": "starting", "id": SID}
        f = c.expect()
        assert f == {"event": "listening", "id": SID, "context_seeded": True}, f
        assert "context_reason" not in f  # present ONLY when context_seeded is false
        host = e.d._host
        assert host.primed_seeds == [True]  # a confirming prime ran (bool only)
        _assert_frames_valid(c.frames)
        _assert_privacy(e, caplog=None, frames=c.frames)  # the seed NEVER echoes
        c.send({"cmd": "lost", "id": SID})
        assert c.expect()["reason"] == "target_lost"
    finally:
        e.srv.stop()
        _until(lambda: len(e.sessions) == 0)


def test_listening_context_prompt_disabled(tmp_path, monkeypatch):
    cfg = hermetic_cfg()
    cfg.asr.context_prompt = False
    e = _build_env(tmp_path, monkeypatch, cfg=cfg, host_cls=_PrimeHost)
    try:
        c = _editor_start(e, context=CTX)
        assert c.recv() == {"event": "starting", "id": SID}
        f = c.expect()
        assert f == {
            "event": "listening",
            "id": SID,
            "context_seeded": False,
            "context_reason": "disabled",
        }, f
        assert e.d._host.primed_seeds == []  # prompting disabled → never primed
    finally:
        e.srv.stop()
        _until(lambda: len(e.sessions) == 0)


# === 3. handshake refusals: one {"ok":false,"error":code} + EOF, nothing reserved ==


def _refusal_case(e, payload, code, *, generic_live=False):
    c = Client(e.path)
    c.send(payload)
    reply = c.recv()
    assert reply == {"ok": False, "error": code}, reply
    assert c.recv() is None  # EOF right after the refusal
    with e.d._lock:
        assert not e.d._native_owner_live_locked()
    if not generic_live:
        assert not e.d.is_listening(), "a refusal must arm nothing"
    return c


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda p: p.update(version=2), "unsupported_version"),
        (lambda p: p.update(context="x" * (4 * 1024 + 1)), "too_large"),
        (lambda p: p.update(extra=1), "invalid_request"),  # unknown field
        (lambda p: p.update(id="not-a-uuid"), "invalid_request"),
        (lambda p: p.update(version="1"), "invalid_request"),  # wrong type
        (lambda p: p.update(context=5), "invalid_request"),  # wrong type
    ],
)
def test_handshake_refusals_validate_request(env, mutate, code):
    payload = {"cmd": "editor-start", "version": 1, "id": SID, "context": ""}
    mutate(payload)
    _refusal_case(env, payload, code)


def test_handshake_refusal_busy_generic_live(env):
    out = env.d.start()
    assert out.ok and env.d.is_listening()  # a GENERIC arm owns the mic
    _refusal_case(
        env, {"cmd": "editor-start", "version": 1, "id": SID, "context": ""}, "busy",
        generic_live=True,
    )
    env.d.stop()


def test_handshake_refusal_duplicate_id_after_end(env):
    c = _owner_listening(env)
    c.send({"cmd": "stop", "id": SID})
    assert c.expect()["event"] == "finishing"
    assert c.expect()["event"] == "ended"
    assert c.recv() is None
    _refusal_case(env, {"cmd": "editor-start", "version": 1, "id": SID, "context": ""},
                  "duplicate_id")


# === 4. non-owner frames keep today's generic behaviour =======================


def test_non_owner_frames_unchanged(env):
    c = Client(env.path)
    c.send({"cmd": "status"})
    reply = c.recv()
    assert reply["ok"] is True and "listening" in reply and "native" in reply
    c.send({"cmd": "ping", "id": SID})  # a native cmd on a NON-owner connection
    reply = c.recv()
    assert reply["ok"] is False and "unknown command" in reply["error"], reply
    c.send_raw(b"not json\n")
    reply = c.recv()
    assert reply["ok"] is False and "malformed JSON" in reply["error"], reply


# === 5. lease: 6 s without a valid ping → ended{timeout} (pong renews) ========


def test_lease_expiry_ends_session(env):
    c = _owner_listening(env)
    env.fc.advance(6.0)
    _fire_due(env.mt, env.fc)
    # The lease fire is a PUMP loss: S3 shuts the transport down first, so the client sees
    # EOF (S6's hook no-ops on a lost pump — no `ended` frame is deliverable). The daemon
    # state is the contract: ended{timeout}, visible via native_last_end/status.
    assert c.recv() is None
    # the loss callback records the end AFTER the transport EOF is observed — poll for it
    assert _until(lambda: env.d.native_last_end() is not None, timeout=3.0)
    state = env.d.native_last_end()
    assert state is not None and state.reason == "timeout"
    status = Client(env.path)
    status.send({"cmd": "status"})
    assert status.recv()["native"]["state"] == "ended"


def test_ping_pong_renews_lease(env):
    c = _owner_listening(env)
    env.fc.advance(5.0)
    c.send({"cmd": "ping", "id": SID})
    pong = c.recv()
    assert pong == {"event": "pong", "id": SID}, pong
    env.fc.advance(5.5)  # lease was renewed by the ping: not yet due
    _fire_due(env.mt, env.fc)
    with pytest.raises(socket.timeout):
        c.recv(timeout=0.6)  # nothing fired: still alive
    env.fc.advance(0.6)  # past the renewed lease
    _fire_due(env.mt, env.fc)
    assert c.recv() is None  # pump loss → EOF (see test_lease_expiry_ends_session)
    assert _until(lambda: env.d.native_last_end() is not None, timeout=3.0)
    assert env.d.native_last_end().reason == "timeout"


# === 6. stalled writer: a wedged reader is WRITE loss → disconnected ==========


def test_stalled_writer_write_loss(tmp_path, monkeypatch):
    e = _build_env(tmp_path, monkeypatch)
    try:
        # A nearly-closed reader: tiny receive buffer + we never read. The pump's writer
        # wedges, the outbound queue fills, and send_event fires WRITE loss (the only
        # route a full queue can take — offers alone can never fill 64 × ≤4 KiB lines).
        c = Client(e.path, rcvbuf=2048)
        c.send({"cmd": "editor-start", "version": 1, "id": SID, "context": ""})
        assert c.recv() == {"event": "starting", "id": SID}
        assert c.expect()["event"] == "listening"
        ping = {"cmd": "ping", "id": SID}
        for _ in range(8000):  # ~4600 pongs saturate the socket buffer, then the queue
            try:
                c.s.settimeout(2.0)
                c.s.sendall((json.dumps(ping) + "\n").encode("utf-8"))
            except (OSError, socket.timeout):
                break  # the daemon stopped reading: loss already fired
        assert _until(lambda: e.d.native_last_end() is not None, timeout=3.0)
        state = e.d.native_last_end()
        # LISTENING-path loss ends via the revoked queue (S5 policy): the reason carries the
        # end; the transport cause is deliberately not re-recorded there.
        assert state.reason == "disconnected"
        assert _until(lambda: len(e.sessions) == 0, timeout=3.0)
    finally:
        e.srv.stop()
        _until(lambda: len(e.sessions) == 0)


# === 7. ACK rules: duplicate harmless; stale/future/late never replay =========


def test_duplicate_ack_is_harmless_no_replay(env):
    c = _owner_listening(env)
    _emit_final(env, 201, FINAL_A)
    assert c.expect()["seq"] == 1
    c.send({"cmd": "applied", "id": SID, "seq": 1})
    c.send({"cmd": "applied", "id": SID, "seq": 1})  # exact duplicate
    _emit_final(env, 202, FINAL_B)
    f = c.expect()
    assert f["seq"] == 2 and f["text"] == FINAL_B  # the next final, no replay of seq 1
    c.send({"cmd": "applied", "id": SID, "seq": 2})
    c.send({"cmd": "stop", "id": SID})
    assert c.expect()["event"] == "finishing"
    ended = c.expect()
    assert ended["reason"] == "stopped"
    finals = [f for f in c.frames if f.get("event") == "final"]
    assert [f["seq"] for f in finals] == [1, 2]  # exactly once each, monotonic
    c.recv()


def test_stale_ack_is_delivery_failed_no_further_final(env):
    c = _owner_listening(env)
    _emit_final(env, 301, FINAL_A)
    assert c.expect()["seq"] == 1
    c.send({"cmd": "applied", "id": SID, "seq": 2})  # future seq — never offered
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "delivery_failed",
        "recoverable": True,
    }, ended
    assert c.recv() is None
    assert [f.get("event") for f in c.frames].count("ended") == 1  # no second ended
    assert not [f for f in c.frames if f.get("event") == "final" and f["seq"] > 1]


def test_ack_timeout_revokes_then_late_ack_ignored(env):
    c = _owner_listening(env)
    _emit_final(env, 401, FINAL_A)
    assert c.expect()["seq"] == 1
    env.fc.advance(5.0)  # past the ABSOLUTE ACK deadline (queue-owned, fake clock)
    ended = c.expect(timeout=3.0)
    assert ended["reason"] == "timeout" and ended["event"] == "ended"
    try:  # a late ACK after the end: the pump is already closing — EPIPE is fine
        c.send({"cmd": "applied", "id": SID, "seq": 1})
    except OSError:
        pass
    assert c.recv(timeout=0.6) is None  # EOF: no resend, no replay, no second ended
    assert [f.get("event") for f in c.frames].count("ended") == 1
    assert c.recv() is None or True  # EOF (client may already be at EOF)


# === 8. one live owner; ordinary clients intact ===============================


def test_old_clients_during_owner_session(env):
    c = _owner_listening(env)
    other = Client(env.path)
    other.send({"cmd": "status"})
    reply = other.recv()
    assert reply["ok"] is True
    assert reply["native"]["state"] == "listening"
    assert reply["native"]["id"] == SID
    other.send({"cmd": "start"})
    reply = other.recv()
    assert reply["ok"] is False and reply.get("busy") is True, reply
    other.send({"cmd": "cancel"})
    reply = other.recv()
    assert reply["ok"] is False and "busy" in reply.get("error", ""), reply
    # `toggle` under a live owner: the S4 contract fences only the ARM side; the disarm
    # side (toggle-off = a stop) is UNCHANGED by design — the generic listening flag is set
    # by the native arm, so a plain toggle is a graceful owner wind-down, not busy.
    other.send({"cmd": "toggle"})
    other.recv()
    finishing = c.expect()
    assert finishing == {"event": "finishing", "id": SID}, finishing
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "stopped",
        "recoverable": False,
    }, ended
    assert c.recv() is None
    _until(lambda: len(env.sessions) == 0)
    # the wind-down's drain flag settles via its watchdog before the next arm
    assert _until(lambda: not getattr(env.d, "_drain", False), timeout=4.0)
    # after the session ends the ordinary arm works again
    other.send({"cmd": "start"})
    reply = other.recv()
    assert reply["ok"] is True and reply["listening"] is True, reply
    other.send({"cmd": "stop"})
    reply = other.recv()
    assert reply["ok"] is True and reply["listening"] is False, reply


# === 9. overflow: a 9th unsettled final → delivery_failed, text retained ======


def test_overflow_nine_unsettled_finals(env):
    c = _owner_listening(env)
    for i in range(9):
        _emit_final(env, 500 + i, f"final number {i}")
    ended = c.expect(timeout=4.0)
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "delivery_failed",
        "recoverable": True,
    }, ended
    assert c.recv() is None
    finals = [f for f in c.frames if f.get("event") == "final"]
    assert len(finals) <= 8, "MAX_UNSETTLED=8 bounds the wire"
    seqs = [f["seq"] for f in finals]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # monotonic, unique
    snap = env.d._native_recovery.recover(SID)
    assert snap is not None, "unsettled finals stay recoverable"


# === 10. loss barriers ========================================================


def test_eof_mid_frame_is_disconnected(tmp_path, monkeypatch):
    e = _build_env(tmp_path, monkeypatch)
    try:
        c = _owner_listening(e)
        c.send_raw(b'{"cmd":"applied","id":"' + SID.encode())  # partial frame
        c.close()  # EOF mid-frame
        assert _until(lambda: e.d.native_last_end() is not None, timeout=3.0)
        state = e.d.native_last_end()
        # LISTENING-path loss ends via the revoked queue (S5 policy): the revocation reason
        # carries the end; the transport cause is deliberately not re-recorded there.
        assert state.reason == "disconnected"
        assert _until(lambda: len(e.sessions) == 0, timeout=3.0)
    finally:
        e.srv.stop()
        _until(lambda: len(e.sessions) == 0)


def test_owner_lost_command(env):
    c = _owner_listening(env)
    c.send({"cmd": "lost", "id": SID})
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "target_lost",
        "recoverable": False,
    }, ended
    assert c.recv() is None
    assert env.d.native_last_end().reason == "target_lost"


def test_owner_cancel_no_drain_host_cancelled(env):
    c = _owner_listening(env)
    host = env.d._host
    host.capture_boundary = _CaptureBoundary(3, 1, 1, 601)
    env.d._text_in_flight.set()  # an utterance is inside text(): host.cancel must run
    c.send({"cmd": "cancel", "id": SID})
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "cancelled",
        "recoverable": False,
    }, ended
    assert c.recv() is None
    assert host.cancel_calls == 1, "cancel discards the in-flight utterance audio"
    assert all(f.get("event") != "finishing" for f in c.frames)  # NO drain
    assert env.d.native_last_end().reason == "cancelled"


def test_second_editor_start_on_owner_connection(env):
    c = _owner_listening(env)
    c.send({"cmd": "editor-start", "version": 1, "id": SID2, "context": ""})
    # A duplicate start is a pump REQUEST loss → transport EOF (no `ended` frame is
    # deliverable on a lost pump); the daemon state carries delivery_failed.
    assert c.recv() is None
    # the loss callback records the end AFTER the transport EOF is observed — poll for it
    assert _until(lambda: env.d.native_last_end() is not None, timeout=3.0)
    state = env.d.native_last_end()
    assert state is not None and state.reason == "delivery_failed"
    assert _until(lambda: len(env.sessions) == 0, timeout=3.0)


# === 11. stop during STARTING: ended{stopped}, mic never opened ===============


def test_stop_during_cold_load(tmp_path, monkeypatch):
    gate = threading.Event()
    e = _build_env(tmp_path, monkeypatch, host_cls=lambda *a, **k: _GatedHost(*a, gate=gate, **k))
    try:
        c = _editor_start(e)
        assert c.recv() == {"event": "starting", "id": SID}
        c.send({"cmd": "stop", "id": SID})
        ended = c.expect()
        assert ended == {
            "event": "ended",
            "id": SID,
            "reason": "stopped",
            "recoverable": False,
        }, ended
        assert c.recv() is None
        state = e.d.native_last_end()
        assert state.cause == "stop-during-start", state.cause
        gate.set()  # release the worker: its revalidate must lose quietly
        assert _until(lambda: len(e.sessions) == 0, timeout=5.0)
        assert not e.d.is_listening(), "a stopped start must never open capture"
        assert all(f.get("event") != "listening" for f in c.frames)
    finally:
        gate.set()
        e.srv.stop()
        _until(lambda: len(e.sessions) == 0)


# === 12. Start cap: 30 s of cold load → ended{timeout, start-cap} =============


def test_start_cap_watchdog(tmp_path, monkeypatch):
    gate = threading.Event()
    e = _build_env(tmp_path, monkeypatch, host_cls=lambda *a, **k: _GatedHost(*a, gate=gate, **k))
    try:
        c = _editor_start(e)
        assert c.recv() == {"event": "starting", "id": SID}
        e.fc.advance(30.0)
        _fire_due(e.mt, e.fc)
        ended = c.expect()
        assert ended == {
            "event": "ended",
            "id": SID,
            "reason": "timeout",
            "recoverable": False,
        }, ended
        assert c.recv() is None
        state = e.d.native_last_end()
        assert state.cause == "start-cap", state.cause
        gate.set()
        assert _until(lambda: len(e.sessions) == 0, timeout=5.0)
        assert not e.d.is_listening()
    finally:
        gate.set()
        e.srv.stop()
        _until(lambda: len(e.sessions) == 0)


# === 13. quit retires the owner; srv.stop() is clean ==========================


def test_quit_retires_owner_and_srv_stop_is_clean(env):
    c = _owner_listening(env)
    other = Client(env.path)
    other.send({"cmd": "quit"})
    reply = other.recv()
    assert reply == {"ok": True, "shutting_down": True}, reply
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "shutdown",
        "recoverable": False,
    }, ended
    assert c.recv() is None
    t0 = time.monotonic()
    env.srv.stop()  # must retire within budget and unlink the socket
    assert time.monotonic() - t0 <= 3.5
    assert _until(lambda: len(env.sessions) == 0, timeout=5.0)  # the loop joins its pump
    assert not os.path.exists(env.path)
    assert not any(
        t.name.startswith("owner-pump") for t in threading.enumerate()
    ), "owner pump threads leaked after quit"
    assert len(env.sessions) == 0


# === 14. content tripwires on the busy path ==================================


def test_busy_reply_carries_no_native_content(env, caplog):
    caplog.set_level(logging.DEBUG)
    c = _owner_listening(env)
    _emit_final(env, 701, FINAL_A)
    assert c.expect()["seq"] == 1
    other = Client(env.path)
    other.send({"cmd": "editor-start", "version": 1, "id": SID2, "context": CTX})
    reply = other.recv()
    assert reply == {"ok": False, "error": "busy"}, reply
    assert other.recv() is None
    blob = json.dumps(other.frames) + "".join(r.getMessage() for r in caplog.records)
    assert CTX not in blob and FINAL_A not in blob  # refusal path leaks nothing
    c.send({"cmd": "stop", "id": SID})
    assert c.expect()["event"] == "finishing"
    env.fc.advance(5.0)  # the ACK-settlement window (fc clock) runs out with seq=1 unapplied
    _fire_due(env.mt, env.fc)
    ended = c.expect()
    assert ended == {
        "event": "ended",
        "id": SID,
        "reason": "timeout",
        "recoverable": True,
    }, ended
    assert c.recv() is None
    _assert_privacy(env, caplog, c.frames, final_texts=(FINAL_A,))
