"""Native v1 session ownership — reservation + startup fence (P1.M1.T3.S4; PRD §4.8.1 B).

RESERVATION STATE ONLY. This module answers three questions for the daemon: who owns the mic (one
connection-bound native owner), what stage its startup/session is in, and when its Start budget
expires. Ordered offer delivery (P1.M1.T4.S2), stop/cancel/drain policy (T4.S5), the `ended` frame and
failure hints (T4.S6) and socket activation (T4.S7) all build on these hooks.

Discipline (Mode A):
  * No I/O, no sockets, no threads started, no daemon import. The only import is editor_protocol
    (END_REASONS, START_CAP_S) — the single reference for every native timer/reason code.
  * Every method is a PURE transition that MUST run under the CALLER's lock (the daemon's `_lock`);
    nothing here takes a lock. The daemon's critical sections make check-and-reserve atomic.
  * Time is an injected monotonic clock; the Start deadline is ABSOLUTE (created_at + START_CAP_S).
  * EndRecords carry fixed codes only — never request text, seed text or frame bytes.

OFFER DELIVERY (OfferQueue, P1.M1.T4.S2; PRD §4.8.1 B/C + system_context "Buffer ownership and
recovery"): accepted finals reach the editor as ONE outstanding sequenced offer at a time, settled
only on an EXACT verified ACK (id + seq == the outstanding offer). At most MAX_UNSETTLED (8) finals
are unsettled (pending + the one outstanding), each <= 4 KiB UTF-8; seq is monotonic per session
from 1. The queue owns the recovery store for the offer lifecycle: enqueue RETAINS BEFORE OFFER
(overflow/oversize/invalid text is retained-if-possible and then revokes — never a truncated
insert), and begin_offer marks the attempt in recovery (mark-before-write) and stamps the ABSOLUTE
ACK deadline BEFORE the caller writes, so a failed or uncertain write leaves possibly_applied set
in recovery — correct; never cleared, never re-sent. The write itself happens OUTSIDE any lock via
the begin/finish split: the caller takes the daemon `_lock`, calls begin_offer, releases, writes
(send_line_capped — the 2 s write cap sits INSIDE the 5 s ACK budget), re-takes the lock and calls
finish_offer(ok). An ACK landing between the two finds `outstanding` already set and settles
normally; a then-failed write must NOT revoke an already-settled offer — the verified ACK wins.
Deadline ownership: the queue stamps the deadline at the attempt; the CALLER's timer (the pump)
calls check_deadline — no threads, no waits here. Duplicate ACK of the last-settled seq is a
harmless no-op (no extension, no replay). Malformed / wrong-id / stale / uncertain / failed
delivery REVOKE — sticky, first reason wins; reasons are END_REASONS codes only ("timeout" |
"delivery_failed" | T4.S5's "cancelled"), never text.
"""

from __future__ import annotations

import enum
import threading
import time
from collections import deque
from dataclasses import dataclass

from voice_typing.editor_protocol import (
    END_REASONS,
    MAX_FINAL_TEXT_BYTES,
    START_CAP_S,
    ProtocolError,
    has_lone_surrogates,
    utf8_len,
    validate_event,
    validate_request,
)

__all__ = [
    "Stage",
    "Owner",
    "EndRecord",
    "NativeReserveResult",
    "NativeReservation",
    "ACK_TIMEOUT_S",
    "MAX_UNSETTLED",
    "EnqueueOutcome",
    "AckOutcome",
    "OfferAttempt",
    "OfferQueue",
    "END_REASONS",
]


class Stage(str, enum.Enum):
    STARTING = "starting"    # reservation acquired; load/priming may be running; capture NOT open
    LISTENING = "listening"  # arm committed under the daemon lock: capture open
    DRAINING = "draining"    # stop/idle/lost wind-down ("finishing"); T4.S5 owns the policy
    ENDED = "ended"          # terminal; the owner token is tombstoned from here on


ACTIVE_STAGES = frozenset({Stage.STARTING, Stage.LISTENING, Stage.DRAINING})


@dataclass(frozen=True)
class Owner:
    id: str          # the client's UUIDv4 (S2 is_uuid_v4) — opaque, safe to log
    token: int       # daemon-side monotonic owner token — THE fence every hook checks
    created_at: float
    deadline: float  # created_at + START_CAP_S — the TOTAL Start cap incl. model load + priming


@dataclass(frozen=True)
class EndRecord:
    """What T4.S6 turns into the `ended` frame. Fixed codes only."""
    owner: Owner
    stage: Stage          # the stage just before ENDED
    reason: str           # §4.8.1 B ended.reason (an END_REASONS member)
    cause: str | None     # "start-cap" | "stop-during-start" | "host-died" | "shutdown" | a LossCause value | None
    ended_at: float


@dataclass(frozen=True)
class NativeReserveResult:
    accepted: bool
    owner: Owner | None
    error: str | None     # native error code for native_error_reply/write_reject: busy | duplicate_id | invalid_request


class NativeReservation:
    """The one live reservation. Guarded by the daemon's `_lock`; pure transitions; terminal is idempotent.
    `end_evt` is per-reservation so the session's parked worker can be woken by an under-lock terminator
    (daemon._disarm) without a daemon-wide Event being cleared by the next reserve."""

    def __init__(self, owner: Owner, conn: object, *, now: float) -> None:
        self.owner = owner
        self.conn = conn                 # kept for T4.S6/T4.S7; never used here
        self.stage = Stage.STARTING
        self.drain_reason: str | None = None
        self.end: EndRecord | None = None
        self.end_evt = threading.Event()

    @property
    def live(self) -> bool:
        return self.stage in ACTIVE_STAGES

    @property
    def end_reason(self) -> str:
        """The reason an end from DRAINING will carry (recorded by begin_drain; 'stopped' otherwise)."""
        return self.drain_reason or "stopped"

    def can_commit(self, token: int, now: float) -> bool:
        """True iff `token` is this reservation, it is still STARTING, and the Start cap has not passed."""
        return token == self.owner.token and self.stage is Stage.STARTING and now < self.owner.deadline

    def commit(self, token: int) -> bool:
        """STARTING -> LISTENING. Must run in the SAME lock hold that opens capture (daemon._start_fenced)."""
        if token != self.owner.token or self.stage is not Stage.STARTING:
            return False
        self.stage = Stage.LISTENING
        return True

    def begin_drain(self, reason: str) -> bool:
        """LISTENING -> DRAINING, recording the reason the end will carry ('stopped' | 'idle' | ...)."""
        if self.stage is not Stage.LISTENING or reason not in END_REASONS:
            return False
        self.stage = Stage.DRAINING
        self.drain_reason = reason
        return True

    def terminate(self, reason: str, cause: str | None, *, now: float) -> EndRecord | None:
        """Any live stage -> ENDED (tombstones the token). Idempotent: None once ended."""
        if reason not in END_REASONS:
            raise ValueError("unknown end reason")
        if not self.live:
            return None
        prev, self.stage = self.stage, Stage.ENDED
        self.end = EndRecord(self.owner, prev, reason, cause, now)
        return self.end

    def tombstoned(self, token: int) -> bool:
        return self.owner.token == token and self.stage is Stage.ENDED


# === P1.M1.T4.S2 — the offer/ACK FIFO (one sequenced offer, verified ACK) =========

ACK_TIMEOUT_S: float = 5.0  # §4.8.1: offer ACK deadline (code constant, not config)
MAX_UNSETTLED: int = 8  # eight finals total INCLUDING the one outstanding


class EnqueueOutcome(str, enum.Enum):
    """Result of OfferQueue.enqueue — QUEUED, REVOKED (retained if possible, sticky
    revoke), or CLOSED (the session ended; nothing retained)."""

    QUEUED = "queued"
    REVOKED = "revoked"
    CLOSED = "closed"


class AckOutcome(str, enum.Enum):
    """Result of OfferQueue.ack — SETTLED (exact ACK), DUPLICATE (exact duplicate of
    the last settled seq: harmless no-op), REVOKED (malformed/wrong-id/stale), or
    IGNORED (not an applied request / queue already revoked)."""

    SETTLED = "settled"
    DUPLICATE = "duplicate"
    REVOKED = "revoked"
    IGNORED = "ignored"


@dataclass(frozen=True)
class _Item:
    """One unsettled final awaiting its offer (internal)."""

    seq: int
    text: str


@dataclass(frozen=True)
class OfferAttempt:
    """begin_offer's result — the pre-validated offer the CALLER writes outside the
    lock (send_line_capped(attempt.event())). `deadline` is ABSOLUTE (clock + ACK_TIMEOUT_S)."""

    session_id: str
    seq: int
    text: str
    deadline: float

    def event(self) -> dict:
        """The daemon->editor `final` event (already shape/size-validated by begin_offer)."""
        return {"event": "final", "id": self.session_id, "seq": self.seq, "text": self.text}


class OfferQueue:
    """Native-v1 FIFO offer policy (P1.M1.T4.S2; §4.8.1 B/C): one OUTSTANDING sequenced
    offer at a time, settled only by an EXACT verified ACK; at most MAX_UNSETTLED finals
    unsettled (pending + outstanding); mark-before-write; 5 s ACK deadline owned by the
    queue; revoke-on-uncertainty, sticky.

    OWNERSHIP: this queue owns ALL NativeRecovery calls for the offer lifecycle — the
    reader thread calls enqueue (retain-before-offer), the pump timer calls
    check_deadline, the ACK path calls ack. A verified ACK removes the final from
    recovery; an attempted-but-unsettled one keeps possibly_applied set FOREVER (a lost
    ACK is indistinguishable from an unapplied edit — consumers warn, never auto-replay).

    LOCK DISCIPLINE (the begin/finish split): every method is a pure transition under
    the CALLER's lock — nothing here takes a lock, waits, or does I/O. The socket write
    happens BETWEEN begin_offer and finish_offer, OUTSIDE the lock:

        with d._lock:
            attempt = q.begin_offer(now)
        if attempt is not None:                  # write OUTSIDE the lock (2 s cap)
            ok = send_line_capped(conn, encode_line(attempt.event()))
            with d._lock:
                q.finish_offer(ok)

    DEADLINE OWNERSHIP: begin_offer stamps deadline = clock() + ack_timeout_s (the 2 s
    write cap sits INSIDE the ACK budget); the caller's timer calls
    check_deadline(now) — now >= deadline with the offer still outstanding revokes
    "timeout". Duplicate ACK of the last settled seq is harmless (no extension, no
    replay). A failed/uncertain write revokes "delivery_failed" — unless a verified ACK
    already settled the offer (the ACK wins).
    """

    def __init__(
        self,
        session_id: str,
        recovery,
        *,
        clock=time.monotonic,
        ack_timeout_s: float = ACK_TIMEOUT_S,
        max_unsettled: int = MAX_UNSETTLED,
    ) -> None:
        self._sid = session_id
        self._recovery = recovery
        self._clock = clock
        self._ack_timeout_s = ack_timeout_s
        self._max_unsettled = max_unsettled
        self._pending: deque[_Item] = deque()
        self._outstanding: OfferAttempt | None = None
        self._deadline: float | None = None
        self._next_seq = 1
        self._last_ack = 0
        self._revoked = False
        self._reason: str | None = None
        self._closed = False

    # -- read-only state -----------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._sid

    @property
    def outstanding(self) -> OfferAttempt | None:
        """The offered-but-unsettled offer (None when none): seq, text and ABSOLUTE deadline."""
        return self._outstanding

    @property
    def revoked(self) -> bool:
        return self._revoked

    @property
    def revocation_reason(self) -> str | None:
        return self._reason

    @property
    def last_ack_seq(self) -> int:
        return self._last_ack

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    # -- enqueue (reader thread, after the daemon's accept gates) -------------------

    def enqueue(self, text: str) -> EnqueueOutcome:
        """Accept one final into the FIFO: retain in recovery FIRST (retain-before-offer;
        overflow/oversize stays recoverable), then queue. REVOKED — sticky — on invalid
        text (empty/lone-surrogate/>4 KiB UTF-8), a recovery refusal, or a full capacity
        (>= max_unsettled unsettled incl. outstanding); NEVER a truncated insert.
        CLOSED after close(): the session ended — no retain, no seq, no resurrection."""
        if self._closed:
            return EnqueueOutcome.CLOSED  # no retain: a late final cannot resurrect the session
        seq = self._next_seq
        self._next_seq += 1
        stripped = text.strip()
        invalid = (
            not stripped
            or has_lone_surrogates(text)
            or utf8_len(text) > MAX_FINAL_TEXT_BYTES
        )
        retained = self._recovery.retain_final(self._sid, seq, stripped)
        if self._revoked:
            return EnqueueOutcome.REVOKED  # sticky: retain-only from here on
        if invalid or not retained:
            self.revoke("delivery_failed")
            return EnqueueOutcome.REVOKED
        if len(self._pending) + (1 if self._outstanding is not None else 0) >= self._max_unsettled:
            self.revoke("delivery_failed")  # retained above — recoverable, never dropped
            return EnqueueOutcome.REVOKED
        self._pending.append(_Item(seq, stripped))
        return EnqueueOutcome.QUEUED

    # -- offer lifecycle (begin -> write OUTSIDE the lock -> finish) ----------------

    def begin_offer(self, now: float | None = None) -> OfferAttempt | None:
        """Pop the oldest pending final and make it THE outstanding offer: mark it
        offer-attempted in recovery (mark-BEFORE-write — a failed/uncertain write leaves
        possibly_applied set, correct), stamp the ABSOLUTE ACK deadline (clock +
        ack_timeout_s), pre-validate the `final` event, return the OfferAttempt. None
        when revoked/closed/an offer is already outstanding/nothing pending — or when
        the event fails validation (revokes delivery_failed; must never happen for
        text that passed enqueue)."""
        if self._revoked or self._closed or self._outstanding is not None or not self._pending:
            return None
        item = self._pending.popleft()
        self._recovery.mark_offer_attempted(self._sid, item.seq)
        attempt = OfferAttempt(self._sid, item.seq, item.text, self._clock() + self._ack_timeout_s)
        try:
            validate_event(attempt.event())
        except ProtocolError:
            self.revoke("delivery_failed")
            return None
        self._outstanding = attempt
        self._deadline = attempt.deadline
        return attempt

    def finish_offer(self, ok: bool) -> None:
        """Settle the write half of the split. ok -> nothing more (the outstanding offer
        stands, waiting for the ACK). False -> revoke "delivery_failed" — unless a
        verified ACK already settled the offer between begin and finish (the ACK wins;
        nothing to revoke)."""
        if not ok and self._outstanding is not None:
            self.revoke("delivery_failed")

    def ack(self, obj: object, now: float | None = None) -> AckOutcome:
        """Settle ONLY the exact ACK ({"cmd":"applied","id":sid,"seq":outstanding.seq}):
        remove the final from recovery, clear the offer, record last_ack. A malformed
        request (ProtocolError), a foreign id, or a stale/never-offered seq REVOKE
        "delivery_failed" (sticky). An exact DUPLICATE of the last settled seq is a
        harmless no-op — never an extension, never a replay; the CURRENT outstanding's
        deadline is untouched. Non-applied requests and post-revoke ACKs are IGNORED."""
        if self._revoked:
            return AckOutcome.IGNORED
        try:
            validate_request(obj)
        except ProtocolError:
            self.revoke("delivery_failed")
            return AckOutcome.REVOKED
        assert isinstance(obj, dict)  # validate_request guarantees a validated dict
        if obj["cmd"] != "applied":
            return AckOutcome.IGNORED
        if obj["id"] != self._sid:
            self.revoke("delivery_failed")
            return AckOutcome.REVOKED
        seq = obj["seq"]
        if self._outstanding is not None and seq == self._outstanding.seq:
            self._recovery.settle_final(self._sid, seq)
            self._outstanding = None
            self._deadline = None
            self._last_ack = seq
            return AckOutcome.SETTLED
        if seq == self._last_ack:
            return AckOutcome.DUPLICATE
        self.revoke("delivery_failed")  # stale: settled-older, never-offered, or future
        return AckOutcome.REVOKED

    def check_deadline(self, now: float | None = None) -> bool:
        """The pump timer's tick: True (after revoking "timeout") iff the offer is still
        outstanding and now >= its ABSOLUTE deadline. The queue owns the deadline; the
        caller owns the clock."""
        n = self._clock() if now is None else now
        if self._outstanding is not None and self._deadline is not None and n >= self._deadline:
            self.revoke("timeout")
            return True
        return False

    # -- teardown / wind-down (T4.S5) -----------------------------------------------

    def revoke(self, reason: str) -> str | None:
        """REVOKE the queue — sticky, first reason wins (later calls return None). The
        queue stops offering and accepting (enqueue retains only; begin_offer is None);
        retained finals stay in recovery exactly as they are (possibly_applied survives).
        `reason` is an END_REASONS code ("timeout" | "delivery_failed" | "cancelled")."""
        if reason not in END_REASONS:
            raise ValueError("unknown end reason")
        if self._revoked:
            return None
        self._revoked = True
        self._reason = reason
        return reason

    def clear_pending(self) -> int:
        """Drop the UNATTEMPTED pending finals (T4.S5 stop/cancel: no more offers); the
        outstanding offer stands, recovery is untouched (their finals stay recoverable).
        Returns the number dropped."""
        n = len(self._pending)
        self._pending.clear()
        return n

    def drain_pending(self) -> bool:
        """True while unsettled work remains (an outstanding offer or pending finals) —
        T4.S5's 'let the in-flight offer finish' check."""
        return self._outstanding is not None or bool(self._pending)

    def close(self) -> None:
        """Close the queue (after recovery.end_session): enqueue returns CLOSED — no
        retain, no seq, no late-final session resurrection. Idempotent and revoke-safe."""
        self._closed = True
