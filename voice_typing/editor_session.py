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
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass

from voice_typing.editor_protocol import END_REASONS, START_CAP_S

__all__ = ["Stage", "Owner", "EndRecord", "NativeReserveResult", "NativeReservation", "END_REASONS"]


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
