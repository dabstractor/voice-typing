"""Owner connection pump (PRD §4.8.1 B; P1.M1.T3.S3). NO live listener, NO CUDA, NO daemon import.

Byte-level and race cases run on a duck-typed FakeConn with a fake clock and manual timers (no sleeps);
three integration cases use socket.socketpair() with real timers and 0.5 s budgets. Run: timeout 300
.venv/bin/python -m pytest tests/test_editor_pump.py -q
"""
from __future__ import annotations
import json, socket, threading, time
import pytest
from voice_typing import editor_protocol as ep

ID = "123e4567-e89b-42d3-a456-426614174000"
OTHER = "123e4567-e89b-42d3-a456-426614174001"
HOLD = object()          # a recv chunk that blocks the reader on `release` until the test sets it
HOLD2 = object()         # a SECOND hold that only `settle` releases (via `reader_release`)


class FakeClock:
    def __init__(self, now: float = 100.0) -> None: self.now = now
    def __call__(self) -> float: return self.now
    def advance(self, s: float) -> None: self.now += s


class _Handle:
    def __init__(self, deadline, fire): self.deadline, self.fire, self.cancelled = deadline, fire, False


class ManualTimers:
    """Deterministic timer source: records arms; the TEST decides what fires (never a real wait)."""
    def __init__(self) -> None: self.armed: list[_Handle] = []
    def arm(self, deadline, fire):
        h = _Handle(deadline, fire); self.armed.append(h); return h
    @staticmethod
    def cancel(handle): handle.cancelled = True
    def live(self): return [h for h in self.armed if not h.cancelled]


class _Twin:
    """What conn.dup() returns: its OWN settimeout/poll budget log (a real dup shares the fd but keeps
    its own Python-level state). The writer's wait budget per attempt is recorded here."""
    def __init__(self, parent): self._p = parent; self.timeouts: list[float] = []
    def settimeout(self, t): self.timeouts.append(t)
    def poll_send(self, t):
        self.timeouts.append(t)                 # the per-attempt REMAINING budget handed to the send
        return self._p._poll_step()
    def send(self, buf): return self._p._send(buf)
    def shutdown(self, how): self._p.shutdowns.append(("twin", how))
    def close(self): self._p.twin_closed = True


class FakeConn:
    """Duck-typed socket: scripted recv chunks (HOLD blocks until `release`), scripted write outcomes,
    logs settimeout/poll budgets/shutdown/close. The WRITE script is consumed by poll_send (the
    writer's per-attempt budget): int = bytes the next send accepts, ("timeout", advance_s) = burn
    budget and stay unwritable, "block" = wait for `send_release` (the writer is stuck), an OSError
    instance = raised from the wait. HOLD in the recv chunks waits on `release` (the reader is stuck)."""
    def __init__(self, *chunks, send_script=(), clock=None):
        self._chunks = list(chunks); self._script = list(send_script); self._clock = clock
        self.sent: list[bytes] = []; self.sent_from: list[str] = []
        self.timeouts: list[float] = []; self.shutdowns: list = []
        self.closed = False; self.twin_closed = False
        self.release = threading.Event(); self.in_send = threading.Event()
        self.send_release = threading.Event(); self.reader_release = threading.Event()
        self._pending = None
        self.twin = _Twin(self)
    def recv(self, n):
        chunk = self._chunks.pop(0) if self._chunks else b""
        if chunk is HOLD:
            self.release.wait(5)
            return self.recv(n)
        if chunk is HOLD2:
            self.reader_release.wait(5)
            return self.recv(n)
        return chunk
    def dup(self): return self.twin
    def settimeout(self, t): self.timeouts.append(t)          # tripwire: the writer must never call this
    def poll_send(self, t):
        self.timeouts.append(t)                                # write_reject path (pre-pump, shared object)
        return self._poll_step()
    def _poll_step(self):
        step = self._script.pop(0) if self._script else None
        if step == "block":
            self.in_send.set(); self.send_release.wait(5); return False
        if isinstance(step, tuple):
            if self._clock is not None: self._clock.advance(step[1])
            return False
        if isinstance(step, OSError): raise step
        self._pending = step                                   # int: bytes the next send accepts
        return True
    def send(self, buf): return self._send(buf)
    def _send(self, buf):
        self.sent.append(bytes(buf)); self.sent_from.append(threading.current_thread().name)
        n = self._pending; self._pending = None
        return len(buf) if n is None else n
    def shutdown(self, how): self.shutdowns.append(("conn", how))
    def close(self): self.closed = True


def frame(obj) -> bytes: return ep.encode_line(obj)
def ping(sid=ID) -> bytes: return frame({"cmd": "ping", "id": sid})


def mk(conn, *, clock=None, timers=None, **kw):
    clock, timers = clock or FakeClock(), timers or ManualTimers()
    cmds, losses = [], []
    pump = ep.OwnerPump(conn, ID, on_command=cmds.append, on_loss=losses.append, clock=clock, timers=timers, **kw)
    return pump, clock, timers, cmds, losses


def settle(pump, conn=None, timeout=5.0):
    """Release any stuck reader/writer, then wait for both threads; asserts they actually exited."""
    if conn is not None:
        conn.release.set(); conn.send_release.set(); conn.reader_release.set()
    assert pump.wait(timeout), "pump threads did not exit"


def await_lost(pump, timeout=5.0):
    """Bounded wait for the pump's terminal loss (fake clock: the cap trips in milliseconds)."""
    deadline = time.monotonic() + timeout
    while not pump.lost and time.monotonic() < deadline: time.sleep(0.005)
    assert pump.lost, "pump never reached its terminal loss"


# --- constants / helpers (the client + session deadline reference) ---
def test_deadline_reference_constants():
    assert (ep.PING_INTERVAL_S, ep.LEASE_S, ep.WRITE_CAP_S, ep.START_CAP_S, ep.ACK_DEADLINE_S) == (2.0, 6.0, 2.0, 30.0, 5.0)
    assert ep.LEASE_S == 3 * ep.PING_INTERVAL_S          # a lease tolerates exactly two missed pings
    assert ep.deadline_after(2.5, now=10.0) == 12.5 and ep.remaining(12.5, now=10.0) == 2.5
    assert ep.remaining(12.5, now=20.0) == 0.0             # clamped, never negative
    assert {c.end_reason for c in ep.LossCause} == {"timeout", "delivery_failed", "disconnected"}
    assert ep.LossCause.LEASE.end_reason == "timeout" and ep.LossCause.REQUEST.end_reason == "delivery_failed"
    assert all(X.end_reason == "disconnected" for X in (ep.LossCause.EOF, ep.LossCause.IO, ep.LossCause.FRAME, ep.LossCause.WRITE))


# --- ping / pong / lease renewal (deterministic: the reader is held until the test moves the clock) ---
def test_ping_queues_pong_and_renews_lease_with_new_timer():
    conn = FakeConn(HOLD, ping()); pump, clock, timers, cmds, losses = mk(conn)
    pump.start(); before = pump.lease_deadline
    clock.advance(1.0); conn.release.set(); settle(pump)      # reader: ping at t=101, then EOF
    assert losses == [ep.LossCause.EOF] and cmds == []
    assert pump.last_ping_at == 101.0 and before == 106.0     # lease was armed at start() = 100 + 6
    assert [h.deadline for h in timers.armed] == [106.0, 107.0] and timers.armed[0].cancelled
    assert timers.live() == []                                 # the EOF loss retired the renewed timer too
    assert conn.sent == [frame({"event": "pong", "id": ID})] and conn.sent_from == ["owner-pump-write"]


def test_lease_timer_fire_without_traffic_is_loss_once():
    conn = FakeConn(HOLD); pump, clock, timers, cmds, losses = mk(conn)
    pump.start(); timers.live()[0].fire()                      # 6 s passed with no ping
    assert losses == [ep.LossCause.LEASE] and pump.loss_cause is ep.LossCause.LEASE
    assert ("conn", socket.SHUT_RDWR) in conn.shutdowns        # both I/O threads are woken
    assert timers.live() == []
    timers.armed[0].fire()                                     # a second (stale) fire changes nothing
    settle(pump, conn); assert losses == [ep.LossCause.LEASE]  # the EOF it caused is NOT a second loss


def test_ping_after_lease_deadline_is_loss_not_renewal():
    conn = FakeConn(HOLD, ping()); pump, clock, timers, cmds, losses = mk(conn)
    pump.start(); clock.advance(6.5); conn.release.set(); settle(pump)
    assert losses == [ep.LossCause.LEASE] and pump.loss_detail == "ping after lease deadline"
    assert pump.loss_cause.end_reason == "timeout" and conn.sent == [] and pump.last_ping_at == 100.0


def test_stale_lease_timer_is_ignored_after_renewal():
    conn = FakeConn(HOLD, ping(), ping()); pump, clock, timers, cmds, losses = mk(conn)
    pump.start(); clock.advance(1.0); conn.release.set(); settle(pump)
    assert losses == [ep.LossCause.EOF]                       # neither stale fire nor EOF-before-… produced LEASE
    assert timers.armed[0].cancelled and timers.armed[1].cancelled   # both superseded timers were cancelled
    assert [h.deadline for h in timers.armed] == [106.0, 107.0, 107.0]


# --- loss taxonomy on the read path (details never carry request bytes) ---
@pytest.mark.parametrize("chunks, cause", [
    ((b"",), ep.LossCause.EOF),
    ((b'{"cmd":"pi',), ep.LossCause.EOF),                                 # partial frame at EOF -> detail "partial"
    ((b"x" * (ep.MAX_FRAME_BYTES + 1) + b"\n",), ep.LossCause.FRAME),     # oversize
    ((b"\xff\xfe{\n",), ep.LossCause.FRAME),                              # invalid UTF-8
    ((b"{not json}\n",), ep.LossCause.FRAME),
    ((frame({"cmd": "toggle"}),), ep.LossCause.REQUEST),                  # S2: legacy cmd is not native
    ((frame({"cmd": "applied", "id": ID, "seq": True}),), ep.LossCause.REQUEST),
    ((ping(OTHER),), ep.LossCause.REQUEST),                               # wrong id
    ((frame({"cmd": "editor-start", "version": 1, "id": ID, "context": ""}),), ep.LossCause.REQUEST),
    ((frame([1, 2]),), ep.LossCause.REQUEST),                             # JSON, not an object
    ((OSError("boom"),), ep.LossCause.IO),                               # recv raised
])
def test_read_path_loss_causes(chunks, cause):
    first = chunks[0]
    conn = FakeConn(*(() if isinstance(first, OSError) else chunks))
    if isinstance(first, OSError):
        def recv(n): raise first
        conn.recv = recv
    pump, clock, timers, cmds, losses = mk(conn); pump.start(); settle(pump, conn)
    assert losses == [cause] and pump.loss_cause is cause and pump.lost and cmds == []
    if cause is ep.LossCause.REQUEST: assert pump.loss_cause.end_reason == "delivery_failed"
    if cause is ep.LossCause.EOF and chunks == (b'{"cmd":"pi',): assert pump.loss_detail == "partial"


def test_loss_details_never_echo_request_bytes():
    secret = "private editor text"
    conn = FakeConn(frame({"cmd": "ping", "id": ID, "extra": secret}) + b"\n")   # unknown field -> S2 detail names the FIELD only
    pump, clock, timers, cmds, losses = mk(conn); pump.start(); settle(pump, conn)
    assert losses == [ep.LossCause.REQUEST] and secret not in pump.loss_detail and secret not in str(pump.loss_cause)


# --- commands reach on_command in order, on the reader thread, and keep the pump alive ---
def test_commands_are_delivered_in_order_on_reader_thread():
    conn = FakeConn(frame({"cmd": "applied", "id": ID, "seq": 1}), frame({"cmd": "stop", "id": ID}),
                    frame({"cmd": "cancel", "id": ID}), frame({"cmd": "lost", "id": ID}), b"")
    names, got = [], []
    losses = []
    pump = ep.OwnerPump(conn, ID, on_command=lambda o: (got.append(o), names.append(threading.current_thread().name)),
                        on_loss=losses.append, clock=FakeClock(), timers=ManualTimers())
    pump.start(); assert pump.wait(5)
    assert [o["cmd"] for o in got] == ["applied", "stop", "cancel", "lost"] and got[0]["seq"] == 1
    assert names == ["owner-pump-read"] * 4 and losses == [ep.LossCause.EOF]   # stop/cancel do NOT end the pump; the session does


def test_crashing_command_handler_ends_as_request_loss():
    def boom(o): raise RuntimeError("handler bug")
    conn = FakeConn(frame({"cmd": "stop", "id": ID}), b"")
    losses = []
    pump = ep.OwnerPump(conn, ID, on_command=boom, on_loss=losses.append, clock=FakeClock(), timers=ManualTimers())
    pump.start(); assert pump.wait(5)
    assert losses == [ep.LossCause.REQUEST] and pump.loss_detail == "command handler failed"


# --- writer: whole-frame absolute cap, offset tracking, dup()-only timeouts ---
def test_write_cap_is_whole_frame_and_never_resends():
    clock = FakeClock(); conn = FakeConn(HOLD, send_script=[5, ("timeout", 2.0)], clock=clock)
    pump, clock, timers, cmds, losses = mk(conn, clock=clock); ev = {"event": "final", "id": ID, "seq": 1, "text": "hello"}
    pump.send_event(ev); pump.start()
    await_lost(pump)
    settle(pump, conn)
    line = frame(ev)
    assert losses == [ep.LossCause.WRITE] and pump.loss_detail == "write cap exceeded"
    assert conn.sent == [line]                        # 5 bytes accepted; the retried attempt never got a byte out
    assert conn.twin.timeouts == [2.0, 2.0]           # absolute deadline: the second attempt's budget was still the full 2 s
    assert conn.timeouts == []                        # CRITICAL #2: the shared object was never given a timeout
    assert conn.sent_from == ["owner-pump-write"] and conn.twin_closed and ("twin", socket.SHUT_WR) in conn.shutdowns


def test_write_cap_remaining_budget_shrinks():
    clock = FakeClock(); conn = FakeConn(HOLD, send_script=[5, ("timeout", 1.0), 3, ("timeout", 5.0)], clock=clock)
    pump, clock, timers, cmds, losses = mk(conn, clock=clock); pump.send_event({"event": "pong", "id": ID}); pump.start()
    await_lost(pump); settle(pump, conn)
    line = frame({"event": "pong", "id": ID})
    # Attempt 2 burned 1.0 s of the absolute 2.0 s budget; attempt 3 sent line[5:] against the remaining
    # 1.0 s; attempt 4 burned past the deadline. Offsets progress 0 -> 5; never byte 0 again.
    assert conn.twin.timeouts == [2.0, 2.0, 1.0, 1.0] and conn.sent == [line, line[5:]]
    assert pump.loss_cause is ep.LossCause.WRITE and pump.loss_detail == "write cap exceeded"


def test_send_oserror_is_io_loss():
    conn = FakeConn(HOLD, send_script=[BrokenPipeError()]); pump, clock, timers, cmds, losses = mk(conn)
    pump.send_event({"event": "pong", "id": ID}); pump.start()
    await_lost(pump); settle(pump, conn)
    assert pump.loss_cause is ep.LossCause.IO and pump.loss_detail == "BrokenPipeError"


def test_lease_is_read_while_write_is_blocked():      # THE cold-load / blocked-receiver requirement
    clock = FakeClock(); conn = FakeConn(HOLD, ping(), HOLD2, send_script=["block", ("timeout", 2.0)], clock=clock)
    pump, clock, timers, cmds, losses = mk(conn, clock=clock)
    pump.send_event({"event": "final", "id": ID, "seq": 1, "text": "x" * 50}); pump.start()
    assert conn.in_send.wait(5) and not pump.lost      # the writer IS stuck waiting to write
    clock.advance(1.0); conn.release.set()             # ... and the reader ALONE processes the ping at t=101
    deadline = time.monotonic() + 5
    while pump.last_ping_at != 101.0 and time.monotonic() < deadline: time.sleep(0.005)
    assert pump.last_ping_at == 101.0 and pump.lease_deadline == 107.0 and not pump.lost   # lease renewed DURING the block
    conn.send_release.set()                            # unstick the writer -> remaining budget 1.0 -> cap
    await_lost(pump)                                   # the WRITE loss is sticky before the reader's EOF
    settle(pump, conn)
    assert losses == [ep.LossCause.WRITE] and conn.twin.timeouts == [2.0, 1.0]   # renewed-attempt budgets: full, then remaining
    assert conn.sent == []                             # the dead peer accepted nothing; the cap tripped in the wait


def test_send_event_is_nonblocking_and_refuses_after_loss():
    conn = FakeConn(HOLD, send_script=["block"]); pump, *_ = mk(conn); pump.send_event({"event": "pong", "id": ID}); pump.start()
    assert conn.in_send.wait(5)
    t0 = time.monotonic(); pump.send_event({"event": "pong", "id": ID}); assert time.monotonic() - t0 < 0.05
    assert "MainThread" not in conn.sent_from            # the CALLER never touches the socket
    pump._on_loss(ep.LossCause.WRITE, "test"); settle(pump, conn)
    with pytest.raises(ep.PumpClosed): pump.send_event({"event": "pong", "id": ID})


def test_outbound_queue_full_is_write_loss():
    conn = FakeConn(HOLD, send_script=["block"]); pump, *_ = mk(conn, queue_max=2)
    pump.send_event({"event": "pong", "id": ID})         # the writer takes this one and blocks inside send
    pump.start(); assert conn.in_send.wait(5)
    pump.send_event({"event": "pong", "id": ID})         # queued (1 of 2)
    pump.send_event({"event": "pong", "id": ID})         # queued (2 of 2)
    with pytest.raises(ep.PumpClosed): pump.send_event({"event": "pong", "id": ID})   # 3rd -> Full
    assert pump.loss_cause is ep.LossCause.WRITE and pump.loss_detail == "outbound queue full"; settle(pump, conn)


def test_loss_is_sticky_under_three_way_race():
    errs = []
    conn = FakeConn(HOLD, send_script=["block"]); pump, clock, timers, cmds, _ = mk(conn)
    pump._on_loss_cb = errs.append
    pump.send_event({"event": "pong", "id": ID}); pump.start(); assert conn.in_send.wait(5)
    racers = [threading.Thread(target=lambda: timers.live()[0].fire()),                 # lease expiry
              threading.Thread(target=lambda: conn.release.set())]                      # reader -> EOF
    for t in racers: t.start()
    for t in racers: t.join(5)
    settle(pump, conn)
    assert len(errs) == 1 and pump.loss_cause is errs[0] and errs[0] in (ep.LossCause.LEASE, ep.LossCause.EOF)


# --- graceful end ---
def test_shutdown_writes_terminal_then_eof_is_idempotent_and_not_loss():
    conn = FakeConn(HOLD); pump, clock, timers, cmds, losses = mk(conn); pump.start()
    ended = {"event": "ended", "id": ID, "reason": "stopped", "recoverable": False}
    pump.shutdown(ended); pump.shutdown({"event": "ended", "id": ID, "reason": "idle", "recoverable": False})
    with pytest.raises(ep.PumpClosed): pump.send_event({"event": "pong", "id": ID})
    settle(pump, conn)
    assert conn.sent == [frame(ended)] and losses == [] and not pump.lost and pump.closed
    assert conn.shutdowns[0] == ("twin", socket.SHUT_WR)     # EOF only AFTER the last frame
    assert timers.live() == []                                # the lease timer was retired by shutdown


def test_shutdown_after_loss_is_noop():
    conn = FakeConn(b""); pump, clock, timers, cmds, losses = mk(conn); pump.start(); settle(pump, conn)
    pump.shutdown({"event": "ended", "id": ID, "reason": "stopped", "recoverable": False})
    assert losses == [ep.LossCause.EOF] and not pump.closed and conn.sent == []


def test_wait_returns_false_on_timeout():
    conn = FakeConn(HOLD); pump, *_ = mk(conn); pump.start()
    assert pump.wait(0.2) is False; settle(pump, conn); assert pump.wait(1) is True and conn.closed


def test_start_twice_raises():
    conn = FakeConn(HOLD); pump, *_ = mk(conn); pump.start()
    with pytest.raises(RuntimeError): pump.start()
    settle(pump, conn)


# --- write_reject (the rejected-first-frame path T4.S7 calls before any pump exists) ---
def test_write_reject_sends_error_then_eof():
    conn = FakeConn(); ep.write_reject(conn, "busy")
    assert conn.sent == [frame({"ok": False, "error": "busy"})] and conn.shutdowns == [("conn", socket.SHUT_WR)]
    assert conn.closed and len(conn.timeouts) == 1 and 0 < conn.timeouts[0] <= 2.0   # shared object OK pre-pump (real clock)
    conn = FakeConn(send_script=[BrokenPipeError()]); ep.write_reject(conn, "unsupported_version")   # never raises


# --- handoff: an existing FrameReader's unread bytes are consumed first ---
def test_handoff_reader_unread_is_consumed_first():
    chunks = [ping() + frame({"cmd": "stop", "id": ID})]       # coalesced in ONE recv
    class Sock:
        def __init__(self, *c): self.c = list(c)
        def recv(self, n): return self.c.pop(0) if self.c else b""
    reader = ep.FrameReader(Sock(chunks[0]).recv)
    assert reader.read_frame_bytes() == ping().rstrip(b"\n") and reader.unread == frame({"cmd": "stop", "id": ID})
    got = []
    losses = []
    pump = ep.OwnerPump(FakeConn(b""), ID, on_command=got.append, on_loss=losses.append, reader=reader, clock=FakeClock(), timers=ManualTimers())
    pump.start(); assert pump.wait(5)
    assert [o["cmd"] for o in got] == ["stop"] and pump.last_ping_at == 100.0 and losses == [ep.LossCause.EOF]


# --- real socketpair, real timers (ThreadTimers), 0.5 s budgets ---
def test_socketpair_lease_expires_without_ping():
    a, b = socket.socketpair(); losses = []
    pump = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=losses.append, lease_s=0.5)
    t0 = time.monotonic(); pump.start(); assert pump.wait(5)
    assert losses == [ep.LossCause.LEASE] and time.monotonic() - t0 < 3
    assert b.recv(1) == b""                                      # peer saw EOF (shutdown) — no bytes written
    b.close()


def test_socketpair_blocked_receiver_trips_write_cap():
    a, b = socket.socketpair(); a.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4608); losses = []
    pump = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=losses.append, lease_s=5.0, write_cap_s=0.5)
    pump.send_event({"event": "final", "id": ID, "seq": 1, "text": "x" * 30000})   # > the ~9 KiB the peer can buffer
    t0 = time.monotonic(); pump.start(); assert pump.wait(5)
    assert losses == [ep.LossCause.WRITE] and pump.loss_detail == "write cap exceeded" and time.monotonic() - t0 < 3
    b.close()                                                    # never read from: the cap, not the lease, fired


def test_socketpair_ping_pong_then_graceful_ended():
    a, b = socket.socketpair(); b.settimeout(5); losses = []
    pump = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=losses.append, lease_s=5.0)
    pump.send_event({"ok": True, "event": "starting", "id": ID}); pump.start()
    assert json.loads(b.recv(4096)) == {"ok": True, "event": "starting", "id": ID}
    b.sendall(ping()); pong = json.loads(b.recv(4096)); assert pong == {"event": "pong", "id": ID}
    ended = {"event": "ended", "id": ID, "reason": "stopped", "recoverable": False}
    pump.shutdown(ended)
    assert b.recv(4096) == frame(ended) and b.recv(4096) == b""   # last frame, then EOF
    assert pump.wait(5) and losses == [] and pump.closed; b.close()
