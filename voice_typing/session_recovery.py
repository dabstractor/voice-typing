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
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

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
