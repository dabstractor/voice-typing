"""Session recovery store (PRD §4.2sexies R.6, P1.M6.T2.S2).

Mode A — the R.6 contract in one breath: daemon MEMORY ONLY (no persistence, no crash
recovery, no audio archive, no transcript-bearing logs), the store holds the last NONEMPTY
arm→disarm session — the filter-ACCEPTED final per utterance (exactly once each) plus the
last visible/recognized unfinished tail — with the exclusion rules (late finals, deliberate
cancels, rejected finals) enforced by HOOK PLACEMENT in the daemon: every hook sits AFTER
the existing gates (the listening gate, the cancel-suppression window, the `if not cleaned`
rejected-final block), so the store inherits their correctness instead of duplicating it.
At most two completed sessions × 1 MiB UTF-8 each; on overflow the newest COMPLETE text that
fits is kept (whole oldest items dropped first; only a lone oversized item is sliced — at a
codepoint boundary, keeping the item's START: the beginning of an utterance is the
recoverable part). Cleared at daemon exit (request_shutdown → clear()). Never touches
state.json.

LAWS:
- LEAF (G2): the store owns its own threading.Lock and NEVER calls back into the daemon,
  feedback, the controller, or logging. No callbacks, no I/O; open/note_* are O(1) (string
  ref assignment); close_session is bounded pure memory (≤ ~2 MiB encode worst case).
  Safe under the daemon's _lock and on the reader thread — deadlock-free by construction.
- NO TEXT OUT (G6): the one place session text leaves the store is `latest_completed()`
  (and the CompletedSession it returns), read on demand by the daemon's session_snapshot()
  for P1.M6.T2.S3's `voicectl session` control reply. Log lines carry counts/times ONLY.

CONSUMER CONTRACT (S3): `latest_completed().text()` is EXACTLY what `voicectl session`
prints/copies — accepted finals joined with single spaces plus the unfinished tail appended
with one space: no trailing space, NO added newline.

Draft accumulation note: between arm and disarm the draft holds at most one tail string
(note_tail is an overwrite) plus the session's finals list; the finals list is bounded only
at close (the cap is per STORED session, per R.6). A pathological session (hours of
dictation, never disarmed) accumulates finals in memory until close — accepted per R.6,
documented here so the growth is not a surprise.

NATIVE RECOVERY (PRD §4.8.1 C, P1.M1.T4.S1) — the SECOND leaf below (NativeRecovery) is the
native-editor counterpart, deliberately separate from SessionRecovery. ORDINARY recovery
(above) holds one draft's accepted finals plus the unfinished TAIL, capped only at close,
and feeds `voicectl session`. NATIVE recovery is keyed by the session's UUIDv4, holds
UNACKNOWLEDGED accepted finals only (no partials, no seed, no tail), is bounded WHILE
ACTIVE (1 MiB UTF-8 INCLUDING the single-space separators), reclaims a final on its
verified ACK, flags an offer write attempted without a verified ACK as `possibly_applied`
(set BEFORE the socket write, surviving truncation and end; cleared only by ACK removal —
consumers warn, never auto-replay: a lost ACK must not become a second insert), and
retains at most two NONEMPTY ended sessions (fully-ACKed/empty endings are discarded and
never evict). OWNERSHIP: the daemon retains from the reader thread after the accept gates
(T4.S4), marks before the socket write and settles on the editor's `applied` (T4.S2), ends
with the reservation's reason (T4.S6), and clears at exit. Shared with the leaf above: the
G2 leaf law (own lock, no callbacks, no I/O, no logging) and the `_fit_text`
codepoint-safe clipper; UUID/UTF-8 validation is imported from editor_protocol (T3.S2)
rather than duplicated.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from voice_typing.editor_protocol import has_lone_surrogates, is_uuid_v4, utf8_len

_MAX_SESSIONS = 2  # R.6: at most two completed sessions (code constant, NOT config)
_MAX_SESSION_BYTES = 1 << 20  # R.6: 1 MiB UTF-8 per session (code constant, NOT config)


def _fit_text(text: str, budget: int) -> str:
    """Longest prefix of ``text`` whose UTF-8 encoding fits ``budget`` bytes.

    Codepoint-binary-search (G5): Python str slicing is codepoint-safe — it can never split
    a surrogate pair — so the returned prefix round-trips through encode('utf-8') as valid
    UTF-8. O(log n) encodes; called only from close_session on an oversized lone item.
    """
    if budget <= 0:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[:mid].encode("utf-8")) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


@dataclass(frozen=True)
class CompletedSession:
    """One closed arm→disarm session (immutable snapshot — safe to hand across threads)."""

    finals: tuple[str, ...]  # accepted finals, in order, exactly once per utterance
    tail: str  # last visible/recognized unfinished tail ("" if none)
    truncated: bool  # size-cap truncation happened (whole items dropped and/or sliced)
    finals_dropped: int  # whole finals dropped by the cap (the truncation report)
    ended_monotonic: float

    def text(self) -> str:
        """EXACTLY what S3 prints/copies: single-space join, no trailing space, no newline."""
        parts = list(self.finals) + ([self.tail] if self.tail else [])
        return " ".join(parts)

    def byte_len(self) -> int:
        """UTF-8 size of the rendered text (the cap's unit, G5)."""
        return len(self.text().encode("utf-8"))


class SessionRecovery:
    """R.6 recovery store — daemon MEMORY ONLY (no persistence, no transcript-bearing logs).

    Lifecycle: the daemon calls open_session() on arm, note_* on recognition events (every
    hook placed AFTER the existing gates), close_session() on disarm (the funnel for every
    disarm path), clear() at daemon exit. close_session() returns the CompletedSession it
    just stored (None when the session was empty and discarded) so the DAEMON can emit the
    counts-only close-time INFO line — the store itself never logs (G2/G6).
    """

    def __init__(
        self,
        max_sessions: int = _MAX_SESSIONS,
        max_session_bytes: int = _MAX_SESSION_BYTES,
    ) -> None:
        self._lock = threading.Lock()  # leaf lock: never held across callbacks (G2)
        self._max_sessions = max_sessions
        self._max_session_bytes = max_session_bytes
        self._completed: list[CompletedSession] = []  # oldest first, ≤ max_sessions
        self._draft_finals: list[str] = []
        self._draft_keys: set[object] = set()  # bulk (gen, uid) closed set — exactly-once
        self._pending_tail: str = ""
        self._open = False

    # -- arm/disarm lifecycle -------------------------------------------------

    def open_session(self) -> None:
        """Start a fresh draft (fresh arm). Any stale draft state is dropped."""
        with self._lock:
            self._draft_finals = []
            self._draft_keys = set()
            self._pending_tail = ""
            self._open = True

    def close_session(self) -> CompletedSession | None:
        """Close the draft (disarm). Empty/failed arms discard the draft — the previous
        completed session survives untouched. Nonempty drafts are capped (G5: whole oldest
        finals dropped first; a lone oversized item sliced at a codepoint boundary keeping
        its START) and appended to the ≤max_sessions deque. Returns the stored session
        (None when discarded) for the daemon's counts-only close log."""
        with self._lock:
            self._open = False
            if not (self._draft_finals or self._pending_tail):
                # Empty session (nothing dictated / load error): discarded entirely.
                self._draft_finals = []
                self._draft_keys = set()
                self._pending_tail = ""
                return None
            finals = list(self._draft_finals)
            tail = self._pending_tail
            dropped = 0
            truncated = False

            def _mk(f: list[str], t: str, tr: bool, dr: int) -> CompletedSession:
                return CompletedSession(tuple(f), t, tr, dr, time.monotonic())

            session = _mk(finals, tail, truncated, dropped)
            # Cap pass 1 — drop WHOLE oldest finals first ("newest complete text that fits").
            while session.byte_len() > self._max_session_bytes and len(finals) > 1:
                finals.pop(0)
                dropped += 1
                truncated = True
                session = _mk(finals, tail, truncated, dropped)
            # Cap pass 2 — a lone oversized item: keep its START, slice off the overflow
            # suffix at a codepoint boundary (the beginning of an utterance is the
            # recoverable part; documented per the R.6 one-pass decision).
            if session.byte_len() > self._max_session_bytes:
                truncated = True
                if finals:
                    reserve = len((" " + tail).encode("utf-8")) if tail else 0
                    finals[0] = _fit_text(finals[0], self._max_session_bytes - reserve)
                if tail:
                    joiner = " " if finals else ""
                    used = len((" ".join(finals) + joiner).encode("utf-8"))
                    tail = _fit_text(tail, self._max_session_bytes - used)
                session = _mk(finals, tail, truncated, dropped)
            self._completed.append(session)
            del self._completed[:-self._max_sessions]  # keep the newest max_sessions
            self._draft_finals = []
            self._draft_keys = set()
            self._pending_tail = ""
            return session

    # -- recognition-event hooks (daemon inserts these AFTER the existing gates) ------

    def note_final(self, text: str, key: object | None = None) -> None:
        """Record an ACCEPTED final. ``key`` (bulk = (session_gen, utterance_id), G7) makes
        the draft a closed set: the same key is recorded exactly once. An accepted final
        CLOSES its utterance — the pending tail is cleared (the content is now the final,
        not a tail). Ignored while no session is open (late post-disarm finals, G1)."""
        with self._lock:
            if not self._open:
                return
            if key is not None:
                if key in self._draft_keys:
                    return  # exactly-once (R.6)
                self._draft_keys.add(key)
            self._draft_finals.append(text)
            self._pending_tail = ""  # closed utterance ⇒ not a tail

    def note_rejected(self) -> None:
        """A REJECTED final (blocklist/min_chars): content NO-OP by design — nothing was
        authoritative, so the shown tail is RETAINED as-is (R.6). Exists as an explicit,
        testable hook so the rejection site reads like the acceptance site."""
        with self._lock:
            pass  # deliberate: no draft mutation — pending_tail stays exactly as-is

    def note_tail(self, text: str) -> None:
        """Overwrite the pending unfinished tail with the newest visible/recognized partial
        (plain overwrite — newest wins, matching the visible field). Ignored when closed."""
        with self._lock:
            if not self._open:
                return
            self._pending_tail = text

    def note_cancel(self) -> None:
        """A DELIBERATE cancel: the cancelled fragment is excluded (R.6) — clear the pending
        tail. The racing final is excluded upstream by the suppression window."""
        with self._lock:
            self._pending_tail = ""

    # -- reads / teardown ------------------------------------------------------

    def latest_completed(self) -> CompletedSession | None:
        """The most recent COMPLETED session (never a draft); None when the store is empty."""
        with self._lock:
            return self._completed[-1] if self._completed else None

    def count(self) -> int:
        """Number of completed sessions currently held (≤ max_sessions). Counts only —
        for the close-time log line; never carries text."""
        with self._lock:
            return len(self._completed)

    def clear(self) -> None:
        """Daemon exit (request_shutdown, G10): empty the store entirely, open or not."""
        with self._lock:
            self._completed = []
            self._draft_finals = []
            self._draft_keys = set()
            self._pending_tail = ""
            self._open = False


# ---------------------------------------------------------------------------
# NATIVE RECOVERY (PRD §4.8.1 C, P1.M1.T4.S1) — the native-editor recovery leaf
# ---------------------------------------------------------------------------

_MAX_NATIVE_SESSIONS = 2  # §4.8.1 C: at most two nonempty ended sessions (code constant, NOT config)
_MAX_NATIVE_SESSION_BYTES = 1 << 20  # §4.8.1 C: 1 MiB UTF-8 per session INCLUDING separators, while active
_NATIVE_SEP = " "  # single-space join of the unacknowledged finals (the recovery text)


@dataclass(frozen=True)
class _HeldFinal:
    """One unacknowledged accepted final held for native recovery (immutable)."""

    seq: int
    text: str
    offer_attempted: bool = False  # set BEFORE the offer write; cleared ONLY by removal (settle_final)


class _NativeSession:
    """Internal per-session record (mutable; guarded by NativeRecovery._lock)."""

    __slots__ = (
        "session_id",
        "finals",
        "truncated",
        "ended",
        "end_reason",
        "ended_monotonic",
    )

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.finals: list[_HeldFinal] = []  # ordered by seq
        self.truncated = False  # a cap pass dropped and/or clipped finals
        self.ended = False
        self.end_reason: str | None = None
        self.ended_monotonic: float | None = None


@dataclass(frozen=True)
class NativeRecoverySnapshot:
    """Immutable recovery read — the 1:1 source of T5.S1's {ok, id, text, truncated,
    possibly_applied} reply (final_count / end_reason / ended_monotonic are diagnostics,
    never on the wire). Built under the store lock and handed off lock-free; carries no
    live references into the store."""

    session_id: str
    text: str  # unacknowledged finals in seq order, single-space joined (the RECOVERY text)
    truncated: bool  # a cap pass dropped and/or clipped finals
    possibly_applied: bool  # ANY retained final's offer write was attempted without a verified ACK
    final_count: int
    end_reason: str | None  # None while active
    ended_monotonic: float | None


class NativeRecovery:
    """NATIVE recovery store (§4.8.1 C) — daemon MEMORY ONLY, keyed by the session's UUIDv4.

    Holds the UNACKNOWLEDGED accepted finals of the ONE active native session (no partials,
    no seed, no tail), bounded WHILE ACTIVE at 1 MiB UTF-8 INCLUDING the separators; a
    verified ACK (settle_final) removes the final and reclaims its budget; an offer write
    ATTEMPTED without a verified ACK is flagged possibly_applied — it survives truncation
    and end, and only removal clears it. At most max_sessions NONEMPTY ended sessions are
    retained (fully-ACKed/empty endings are discarded and never evict). Snapshots are
    frozen and carry no live references. recover() NEVER decides `busy`: the wire layer
    (T5.S1) checks active_id() first; recover(active_id) still returns the snapshot.
    Cleared at daemon exit. Never logs, never raises for bad input (the reader thread
    calls this — every refusal is a False return with the state untouched).
    """

    def __init__(
        self,
        max_sessions: int = _MAX_NATIVE_SESSIONS,
        max_session_bytes: int = _MAX_NATIVE_SESSION_BYTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lock = threading.Lock()  # leaf lock: never held across callbacks (G2)
        self._max_sessions = max_sessions
        self._max_session_bytes = max_session_bytes
        self._clock = clock
        self._active: _NativeSession | None = None
        self._ended: list[_NativeSession] = []  # oldest first, ≤ max_sessions

    # -- retain (reader thread, after the daemon's accept gates) ----------------

    def retain_final(self, session_id: str, seq: int, text: str) -> bool:
        """Retain an ACCEPTED final (id, seq, text) — exactly-once per (id, seq).

        Returns False WITHOUT mutating anything when: session_id is not a canonical
        UUIDv4; text carries lone surrogates or is empty after strip; seq is not a
        positive non-bool int; that seq is already retained in the session; the id has
        ENDED; or ANOTHER session is active (one active slot — §4.8.1 B exclusivity; the
        reservation layer owns exclusivity, the store refuses rather than corrupts). The
        first valid retain auto-creates the active session. The cap pass runs HERE —
        bounded while active (§4.8.1 C) — dropping whole oldest UNFLAGGED finals first
        ("retain the newest complete finals that fit") and then clipping (never dropping)
        the oldest final — a flagged one is clipped FURTHER so its uncertainty survives, a
        lone oversized one is clipped to the cap — at a codepoint boundary keeping its
        START (the recovery-only carve-out), marking `truncated`.
        """
        with self._lock:
            if (
                not is_uuid_v4(session_id)
                or has_lone_surrogates(text)
                or isinstance(seq, bool)
                or not isinstance(seq, int)
                or seq <= 0
                or not text.strip()
            ):
                return False
            if any(e.session_id == session_id for e in self._ended):
                return False  # an ended id stays closed
            if self._active is not None and self._active.session_id != session_id:
                return False  # one active slot (§4.8.1 B)
            if self._active is None:
                self._active = _NativeSession(session_id)
            s = self._active
            if any(f.seq == seq for f in s.finals):
                return False  # exactly-once per (id, seq)
            s.finals.append(_HeldFinal(seq, text.strip()))
            s.finals.sort(key=lambda f: f.seq)
            self._cap_locked(s)
            return True

    # -- offer / ACK lifecycle (T4.S2's seams) -----------------------------------

    def mark_offer_attempted(self, session_id: str, seq: int) -> bool:
        """Flag a retained final OFFER-ATTEMPTED — call BEFORE the socket write so a
        mid-write failure still leaves the uncertainty recorded (a lost ACK must be
        indistinguishable from an unapplied edit: consumers warn, never auto-replay).
        True iff session_id is the ACTIVE session and a retained final with that seq
        exists (idempotent). NOTHING clears the flag except removal via settle_final —
        it survives truncation clipping and end_session."""
        with self._lock:
            if self._active is None or self._active.session_id != session_id:
                return False
            for i, f in enumerate(self._active.finals):
                if f.seq == seq:
                    if not f.offer_attempted:
                        self._active.finals[i] = _HeldFinal(f.seq, f.text, True)
                    return True
            return False

    def settle_final(self, session_id: str, seq: int) -> bool:
        """A VERIFIED ACK (the editor reported `applied` for this seq): REMOVE the final —
        its text is acknowledged applied, so it leaves the recovery budget and its
        uncertainty flag goes with it. True iff the final existed in the ACTIVE session;
        False for an unknown seq / an ended id / a foreign session (never re-sends: T4.S2
        marks BEFORE the write and settles exactly once)."""
        with self._lock:
            if self._active is None or self._active.session_id != session_id:
                return False
            for i, f in enumerate(self._active.finals):
                if f.seq == seq:
                    del self._active.finals[i]
                    return True
            return False

    # -- end / read / teardown ----------------------------------------------------

    def end_session(self, session_id: str, reason: str) -> None:
        """End the ACTIVE session (the reservation's EndRecord reason — T4.S6). Nothing
        retained after the ACKs → the record is DISCARDED (a fully-ACKed or empty ending
        never evicts previous recovery, §4.8.1 C). Otherwise the session is appended to
        the ≤max_sessions ended list (the oldest nonempty evicted) and the active slot is
        freed either way. Unknown / already-ended id → no-op."""
        with self._lock:
            if self._active is None or self._active.session_id != session_id:
                return
            s = self._active
            self._active = None  # the slot frees regardless
            if not s.finals:
                return  # empty ending: discarded, nothing evicted
            s.ended = True
            s.end_reason = reason
            s.ended_monotonic = self._clock()
            self._ended.append(s)
            del self._ended[: -self._max_sessions]  # keep the newest max_sessions

    def recover(self, session_id: str | None = None) -> NativeRecoverySnapshot | None:
        """Immutable snapshot of a retained recovery — None when nothing matches (the wire
        `not_found`). Omitted id → the LATEST ENDED session (never the active one). A
        known ended id → that session; the ACTIVE id → its live snapshot (the store does
        NOT decide `busy` — the wire layer (T5.S1) checks active_id() == id first and
        answers busy itself). Built under the lock: a fresh single-space join of the
        retained finals in seq order; possibly_applied = ANY retained final's
        offer_attempted; truncated = a cap pass dropped and/or clipped finals here."""
        with self._lock:
            if session_id is None:
                if not self._ended:
                    return None
                return self._snapshot_locked(self._ended[-1])
            if self._active is not None and self._active.session_id == session_id:
                return self._snapshot_locked(self._active)
            for s in self._ended:
                if s.session_id == session_id:
                    return self._snapshot_locked(s)
            return None

    def active_id(self) -> str | None:
        """The ACTIVE session's UUIDv4 (None when none) — T5.S1's `busy` check reads
        this; the store itself never refuses a recover() for the active id."""
        with self._lock:
            return self._active.session_id if self._active is not None else None

    def counts(self) -> tuple[int, int]:
        """(ended sessions retained, finals retained in the active session) — counts
        ONLY, for logs (G6: never text)."""
        with self._lock:
            return (
                len(self._ended),
                len(self._active.finals) if self._active is not None else 0,
            )

    def clear(self) -> None:
        """Daemon exit (request_shutdown, G10): drop everything — active + ended —
        leaving the store reusable. No persistence (§4.8.1 C: daemon memory only)."""
        with self._lock:
            self._active = None
            self._ended = []

    # -- internals (call with the lock held) --------------------------------------

    def _budget_used(self, s: _NativeSession) -> int:
        """UTF-8 bytes of the RENDERED recovery text — separators INCLUDED (§4.8.1 C's
        'at most 1 MiB UTF-8 per session' is the JOINED text, not the sum of parts)."""
        return utf8_len(_NATIVE_SEP.join(f.text for f in s.finals))

    def _cap_locked(self, s: _NativeSession) -> None:
        """The size cap, enforced at EVERY retain (bounded while active, §4.8.1 C).

        Pass 1 — drop WHOLE OLDEST finals while over budget ("retain the newest complete
        finals that fit"), NEVER a final flagged offer_attempted (its uncertainty must
        survive, so it is clipped instead) and never a LONE OVERSIZED one — a final whose
        text alone fills the session budget cannot coexist with any other content, so it
        is clipped to make room rather than dropped (§4.8.1 C's 'a lone oversized final
        may be safely clipped for recovery only').
        Pass 2 — while still over budget, clip the OLDEST final to the room left by the
        rest (_fit_text: codepoint-safe, keeping its START — the beginning of the
        utterance is the recoverable part). Every drop/clip sets `truncated`.
        """
        while (
            len(s.finals) > 1
            and self._budget_used(s) > self._max_session_bytes
            and not s.finals[0].offer_attempted
            and utf8_len(s.finals[0].text) < self._max_session_bytes
        ):
            s.finals.pop(0)
            s.truncated = True
        while s.finals and self._budget_used(s) > self._max_session_bytes:
            f = s.finals[0]
            rest = s.finals[1:]
            rest_bytes = utf8_len(_NATIVE_SEP.join(g.text for g in rest))
            if rest:
                rest_bytes += utf8_len(_NATIVE_SEP)  # the joiner between f and the rest
            clipped = _fit_text(f.text, max(self._max_session_bytes - rest_bytes, 0))
            if len(clipped) >= len(f.text):
                break  # cannot shrink further; avoid a no-progress loop
            s.finals[0] = _HeldFinal(f.seq, clipped, f.offer_attempted)
            s.truncated = True

    def _snapshot_locked(self, s: _NativeSession) -> NativeRecoverySnapshot:
        """Build the frozen snapshot (lock held): fresh strings, ints, bools only."""
        return NativeRecoverySnapshot(
            session_id=s.session_id,
            text=_NATIVE_SEP.join(f.text for f in s.finals),
            truncated=s.truncated,
            possibly_applied=any(f.offer_attempted for f in s.finals),
            final_count=len(s.finals),
            end_reason=s.end_reason,
            ended_monotonic=s.ended_monotonic,
        )
