"""OfferQueue unit tests (P1.M1.T4.S2) — the native-v1 FIFO offer/ACK policy.

Hermetic: the REAL NativeRecovery (voice_typing/session_recovery.py), an injected
fake monotonic clock, and a simulated write result (finish_offer). No sockets, no
threads, no daemon import. Every queue transition is exercised directly, the way
T4.S4 (enqueue), T4.S5 (drain/cancel) and T4.S7 (ack via on_command, the pump
timer for deadlines, send_line_capped as the write) will drive it.
"""

from voice_typing.editor_session import (
    ACK_TIMEOUT_S,
    MAX_UNSETTLED,
    AckOutcome,
    EnqueueOutcome,
    OfferQueue,
)
from voice_typing.session_recovery import NativeRecovery

SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"  # canonical lowercase UUIDv4
OTHER_ID = "1f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"


def applied(seq: int, sid: str = SID) -> dict:
    return {"cmd": "applied", "id": sid, "seq": seq}


class Clock:
    """Injected monotonic clock — the queue stamps ABSOLUTE deadlines from it."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def mk() -> tuple[OfferQueue, NativeRecovery, Clock]:
    clock = Clock()
    recovery = NativeRecovery(clock=clock)
    return OfferQueue(SID, recovery, clock=clock), recovery, clock


def test_sequential_offers_settle_on_exact_ack():
    """One outstanding offer at a time; the exact ACK settles it; the next offer's
    seq is previous + 1; settle frees the recovery slot."""
    q, rec, _clock = mk()
    assert q.enqueue("alpha") is EnqueueOutcome.QUEUED
    assert q.enqueue("beta") is EnqueueOutcome.QUEUED
    assert rec.counts()[1] == 2  # both finals retained in the active session

    a1 = q.begin_offer()
    assert a1 is not None and a1.seq == 1 and a1.text == "alpha"
    assert a1.session_id == SID
    assert q.begin_offer() is None  # one outstanding at a time

    assert q.ack(applied(1)) is AckOutcome.SETTLED
    assert rec.counts()[1] == 1  # settled final removed from recovery
    assert q.last_ack_seq == 1

    a2 = q.begin_offer()
    assert a2 is not None and a2.seq == 2 and a2.text == "beta"
    assert a2.event() == {"event": "final", "id": SID, "seq": 2, "text": "beta"}
    assert q.ack(applied(2)) is AckOutcome.SETTLED
    assert rec.counts()[1] == 0  # every settled final leaves recovery


def test_attempt_recorded_and_deadline_stamped_before_write():
    """Mark-before-write: begin_offer flags the final offer-attempted in recovery and
    stamps the ACK deadline BEFORE the caller's write runs (write cap inside budget)."""
    q, rec, clock = mk()
    q.enqueue("say this")
    attempt = q.begin_offer()
    assert attempt is not None
    snap = rec.recover(SID)
    assert snap is not None and snap.possibly_applied is True
    assert attempt.deadline == clock() + ACK_TIMEOUT_S == 5.0  # clock at 0.0


def test_only_exact_ack_settles():
    """Malformed / wrong id / stale / never-offered seq all REVOKE (delivery_failed);
    only (id, seq) == the outstanding offer settles."""
    q, _rec, _clock = mk()
    q.enqueue("one")
    assert q.begin_offer() is not None  # outstanding seq 1
    assert q.ack(applied(2)) is AckOutcome.REVOKED  # stale/future seq
    assert q.revoked and q.revocation_reason == "delivery_failed"

    q2, _rec2, _clock2 = mk()
    q2.enqueue("one")
    assert q2.begin_offer() is not None
    assert q2.ack(applied(1, sid=OTHER_ID)) is AckOutcome.REVOKED  # foreign id

    q3, _rec3, _clock3 = mk()
    q3.enqueue("one")
    assert q3.begin_offer() is not None
    assert q3.ack(applied(0)) is AckOutcome.REVOKED  # seq minimum is 1
    q4, _rec4, _clock4 = mk()
    q4.enqueue("one")
    assert q4.begin_offer() is not None
    assert q4.ack({"cmd": "applied", "id": SID, "seq": "1"}) is AckOutcome.REVOKED
    q5, _rec5, _clock5 = mk()
    q5.enqueue("one")
    assert q5.begin_offer() is not None
    assert q5.ack({"cmd": "applied", "id": SID}) is AckOutcome.REVOKED  # missing seq


def test_duplicate_last_ack_is_harmless():
    """An exact duplicate of the last ACK is a no-op: no extension, no replay, the NEW
    outstanding's deadline untouched, queue never revoked."""
    q, _rec, clock = mk()
    q.enqueue("one")
    assert q.begin_offer() is not None  # seq 1
    assert q.ack(applied(1)) is AckOutcome.SETTLED
    clock.t = 10.0
    q.enqueue("two")
    a2 = q.begin_offer()  # seq 2, deadline 15.0
    assert a2 is not None and a2.seq == 2 and a2.deadline == 15.0
    assert q.ack(applied(1)) is AckOutcome.DUPLICATE  # stale duplicate of last ACK
    assert q.revoked is False
    assert q.outstanding is not None and q.outstanding.seq == 2
    assert q.outstanding.deadline == 15.0  # NOT extended, NOT cleared


def test_deadline_revokes_timeout():
    """now >= deadline with the offer still outstanding revokes 'timeout'; the final
    stays in recovery with its possibly_applied uncertainty (never cleared)."""
    q, rec, _clock = mk()
    q.enqueue("one")
    assert q.begin_offer() is not None
    assert q.check_deadline(4.9) is False
    assert q.revoked is False
    assert q.check_deadline(5.0) is True
    assert q.revoked is True and q.revocation_reason == "timeout"
    snap = rec.recover(SID)
    assert snap is not None and snap.final_count == 1 and snap.possibly_applied is True


def test_failed_write_revokes_unless_already_settled():
    """finish_offer(False) revokes delivery_failed while outstanding; a verified ACK
    that already settled the offer wins — the late failure must NOT revoke."""
    q, _rec, _clock = mk()
    q.enqueue("one")
    assert q.begin_offer() is not None
    q.finish_offer(False)
    assert q.revoked is True and q.revocation_reason == "delivery_failed"

    q2, _rec2, _clock2 = mk()
    q2.enqueue("one")
    assert q2.begin_offer() is not None
    assert q2.ack(applied(1)) is AckOutcome.SETTLED  # ACK landed between begin/finish
    q2.finish_offer(False)  # the write then reports failure — the ACK wins
    assert q2.revoked is False and q2.outstanding is None


def test_overflow_retains_and_revokes():
    """The 9th unsettled final (8 incl. outstanding) is retained for recovery and
    revokes delivery_failed — never a truncated insert, never a silent drop."""
    q, rec, _clock = mk()
    for i in range(1, MAX_UNSETTLED + 1):
        assert q.enqueue(f"f{i}") is EnqueueOutcome.QUEUED
    snap9 = rec.recover(SID)
    assert snap9 is not None and snap9.final_count == MAX_UNSETTLED
    assert q.enqueue("f9") is EnqueueOutcome.REVOKED  # capacity exceeded
    assert q.revocation_reason == "delivery_failed"
    snap = rec.recover(SID)
    assert snap is not None and snap.final_count == 9  # the 9th retained for recovery
    assert snap.text.split(" ") == [f"f{i}" for i in range(1, 10)]  # texts intact
    assert snap.truncated is False  # never a truncated insert
    assert q.begin_offer() is None  # revoked: no offers leave the queue


def test_oversize_and_invalid_text_revoke():
    """Oversize (>4 KiB UTF-8) and lone-surrogate text take the retain-if-possible +
    revoke path — no truncated insert."""
    q, rec, _clock = mk()
    assert q.enqueue("x" * 4097) is EnqueueOutcome.REVOKED
    assert q.revocation_reason == "delivery_failed"
    snap = rec.recover(SID)
    assert snap is not None and snap.final_count == 1  # full text retained, untruncated
    assert snap.text == "x" * 4097
    assert q.enqueue("\ud800") is EnqueueOutcome.REVOKED  # lone surrogate
    assert rec.counts()[1] == 1  # the surrogate was rejected by recovery (unchanged)
    assert q.begin_offer() is None  # revoked is sticky


def test_revoke_is_sticky_and_close_blocks_enqueue():
    """First revocation reason wins (sticky): later enqueues retain only, begin_offer
    is None, and close() blocks enqueues entirely (no late-final session resurrection)."""
    q, rec, _clock = mk()
    q.enqueue("a")
    assert q.revoke("cancelled") == "cancelled"
    assert q.revoke("timeout") is None  # first reason wins
    assert q.revocation_reason == "cancelled"
    assert q.enqueue("b") is EnqueueOutcome.REVOKED
    assert rec.counts()[1] == 2  # 'b' still retained for recovery
    assert q.begin_offer() is None  # sticky: no offers
    q.close()
    before = rec.counts()
    assert q.enqueue("c") is EnqueueOutcome.CLOSED
    assert rec.counts() == before  # CLOSED: no retain, counts unchanged


def test_clear_pending_and_drain_pending():
    """clear_pending drops unattempted pending items only (the outstanding offer
    stands); drain_pending reports whether any unsettled work remains."""
    q, rec, _clock = mk()
    assert q.drain_pending() is False
    q.enqueue("a")
    q.enqueue("b")
    assert q.begin_offer() is not None  # 'a' outstanding, 'b' pending
    assert q.drain_pending() is True
    assert q.clear_pending() == 1  # only the unattempted 'b'
    assert q.outstanding is not None and q.outstanding.seq == 1  # outstanding stands
    assert q.ack(applied(1)) is AckOutcome.SETTLED
    assert q.drain_pending() is False  # nothing unsettled left
    q.enqueue("c")
    assert q.drain_pending() is True
    assert q.clear_pending() == 1
    assert q.drain_pending() is False
    assert rec.counts()[1] == 2  # recovery untouched by clear_pending ('b' + 'c' held)
