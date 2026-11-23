"""voice_typing.bulk_controller — the R.5 ordering core for bulk text delivery.

THE ORDERING LAWS THIS MODULE IMPLEMENTS (PRD §4.2sexies R.5, verbatim):

  "bulk mode MUST enqueue and return — no subprocess, editor wait, or display
   polling there or under the daemon control lock. One writer per target; one
   operation in flight; newest partial wins for the current utterance; finals
   and boundaries are ordered barriers, never overwritten (bounded queue,
   default 32; overflow stops delivery rather than dropping a barrier)."

  "Discard late post-final partials, duplicate finals, and canceled-utterance
   events; a dropped or filtered final still closes its utterance boundary"

  "queued operations re-check at mutation time"

  "NEVER retry an operation that may already have landed."

Plus R.1's event-count law, generalized: "two strings that render identically
⇒ zero events". The controller-side zero-diff skip makes that structural: a
partial whose span renders equal to the last shown span NEVER reaches the
target — zero target calls, counted, not a show() that returns unchanged.

DESIGN IN ONE PARAGRAPH: the event entries (on_partial / on_final /
on_final_dropped / arm) run on the daemon reader/control threads and touch
ONLY a bounded deque + Condition — cheap dict/deque ops, never target I/O,
never blocking. ONE writer thread (start()) pops one item at a time,
re-checks identity at mutation time, and executes AT MOST ONE
target.show/finalize — the only place target I/O ever happens. Partials of
the same (generation, utterance) coalesce REPLACE-IN-PLACE (newest wins,
queue position kept, always dispatched before their own utterance's final);
finals / boundaries / session-begins are appended barriers, never
overwritten. Identity: every event carries its own (session generation,
utterance id, seq); per-utterance seq high-water marks and a closed set
discard late / duplicate events at enqueue time, AND the writer re-checks
generation + closure at mutation time. expected_revision is seeded by
acquire() and advances +1 ONLY on ShowResult.APPLIED (UNCHANGED = no edit
landed = no advance). ShowResult.REFUSED / UNKNOWN stop delivery — no retry;
ANY enqueue onto a full queue stops delivery with reason "queue-overflow" —
nothing is ever dropped-and-continued.

CONSUMES: voice_typing.bulk_delivery (DeliveryTarget / ShowResult /
AcquireResult / rendered_equal — the P1.M3.T1.S1 contract surface).
CONSUMED BY: P1.M3.T2.S2 (the 250 ms deadline + disarm-on-unknown extend
this class; the on_stopped seam and the single target-call site in
_process_next are its hook points), P1.M3.T3 (config gate + the
delivery_state surface, fed by stats()), and P1.M6.T2.S1 (daemon wiring:
reader thread → on_partial/on_final/on_final_dropped; control thread →
arm/stop/acquire).

SCOPE (d2 §3): NO textproc guards (the daemon wiring applies them BEFORE
these entries), NO typing fallback, NO feedback/_stream/backend access.
This module imports ONLY stdlib + voice_typing.bulk_delivery (guard-tested
in tests/test_bulk_controller.py).
"""
from __future__ import annotations

import collections
import dataclasses
import logging
import threading

from voice_typing.bulk_delivery import (
    AcquireResult,
    DeliveryTarget,
    ShowResult,
    rendered_equal,
)

__all__ = ["BulkController"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Queue items (module-private): three barrier kinds + the coalescible partial
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class _SessionBegin:
    """arm(gen) barrier: the writer resets per-generation state at dispatch."""

    gen: int


@dataclasses.dataclass(frozen=True, slots=True)
class _Partial:
    """A live partial span; the ONLY coalescible item kind."""

    gen: int
    utterance: str
    seq: int
    span: str


@dataclasses.dataclass(frozen=True, slots=True)
class _Final:
    """A recognition final — an ordered barrier, never overwritten."""

    gen: int
    utterance: str
    seq: int
    span: str


@dataclasses.dataclass(frozen=True, slots=True)
class _Boundary:
    """A dropped/filtered final's boundary — closes WITHOUT any finalize call."""

    gen: int
    utterance: str


class BulkController:
    """Orders, coalesces, and executes bulk-delivery operations for ONE target.

    State (all under self._cond unless noted):
        _dq: bounded deque of queue items (barriers append; partials of the
            same (gen, utterance) replace-in-place). Bounded by queue_size;
            an enqueue onto a full deque STOPS delivery (reason
            "queue-overflow") rather than dropping a barrier or blocking.
        _session_gen: the current arm generation (set by arm()); events with
            a different gen are discarded at enqueue AND re-checked at
            dispatch ("queued operations re-check at mutation time").
        _high_seq: per-(gen, utterance) seq high-water mark; seq <= mark →
            late → discarded. Finals/boundaries set it at enqueue.
        _closed: per-(gen, utterance) closure set (finals/boundaries close at
            enqueue); late post-final partials and duplicate finals die here.
        _closed_dispatched: closures already executed by the writer — the
            mutation-time re-check for a queued partial (a partial enqueued
            BEFORE its final must still dispatch first, so the re-check keys
            on dispatched closures, not the enqueue-time closed set).
        _shown_span: last shown/accepted span per (gen, utterance) — drives
            the zero-diff skip (updated on dispatch AND on skip).
        _expected_revision: seeded from AcquireResult.revision by acquire();
            +1 ONLY on ShowResult.APPLIED.
        _active: delivery live? False rejects every entry (post-stop events
            are rejected, never queued).
        _running / _writer: the single writer thread's lifecycle.
        _left: target.leave() happened (exactly once per controller).
        _stopped_reason: why delivery stopped ("queue-overflow", the
            ShowResult taxonomy word on REFUSED/UNKNOWN, "stopped", or the
            acquire-failure reason).
        _stats: counts and reasons only — never recognition text (R.5).

    The writer is the only thread that performs target I/O and the only
    mutator of _expected_revision/_shown_span, so one operation is in flight
    by construction. Tests drive the very same dispatch handler via
    _process_next()/drain() instead of starting the thread.
    """

    def __init__(
        self,
        target: DeliveryTarget,
        *,
        queue_size: int = 32,
        on_stopped=None,
    ) -> None:
        """Args:
        target: a DeliveryTarget (bulk_delivery contract; the R.3 adapter).
        queue_size: bounded-queue capacity (R.5: default 32). ANY enqueue at
            capacity stops delivery — it never blocks and never drops.
        on_stopped: optional callback fired EXACTLY ONCE with the stop reason
            when delivery stops from a fault (REFUSED/UNKNOWN/overflow) — the
            P1.M3.T2.S2 disarm seam. Must be quick and non-blocking; it runs
            on whichever thread triggered the stop (reader or writer), never
            under the condition lock.
        """
        self._target = target
        self._queue_size = max(1, int(queue_size))
        self._on_stopped = on_stopped
        self._cond = threading.Condition()
        self._dq: collections.deque = collections.deque()
        self._session_gen: int | None = None
        self._high_seq: dict[tuple[int, str], int] = {}
        self._closed: set[tuple[int, str]] = set()
        self._closed_dispatched: set[tuple[int, str]] = set()
        self._shown_span: dict[tuple[int, str], str] = {}
        self._expected_revision: int = 0
        self._active: bool = False
        self._running: bool = False
        self._left: bool = False
        self._stopped_reason: str | None = None
        self._stopped_cb_fired: bool = False
        self._writer: threading.Thread | None = None
        self._stats: dict[str, int] = {
            "applied": 0,
            "unchanged": 0,
            "zero_diff_skipped": 0,
            "discarded_stale": 0,
            "discarded_dup": 0,
            "coalesced": 0,
            "overflow": 0,
        }

    # -- lifecycle (daemon-thread calls, not reader-thread calls) ------------

    def acquire(self) -> bool:
        """Bind the target and seed expected_revision (R.3 acquire model).

        Returns True and activates delivery on success; on a fail-before-
        delivery result the reason is recorded and delivery stays inactive.
        """
        result: AcquireResult = self._target.acquire()
        with self._cond:
            if result.ok:
                self._expected_revision = int(result.revision)
                self._active = True
                self._stopped_reason = None
                self._stopped_cb_fired = False
                return True
            self._stopped_reason = result.reason or "acquire-failed"
            return False

    def start(self) -> None:
        """Launch THE writer thread (one per controller; R.5 one-writer law).

        No-op if already started or not active (acquire() first). The writer
        exits by itself when delivery stops; stop() joins it.
        """
        with self._cond:
            if self._writer is not None or not self._active:
                return
            self._running = True
            self._writer = threading.Thread(
                target=self._writer_loop, name="bulk-controller-writer", daemon=True
            )
            self._writer.start()

    def stop(self, *, leave: bool = True) -> None:
        """Halt delivery; the writer exits; target.leave() exactly once (R.3).

        Post-stop events are rejected at every entry. Idempotent.
        """
        writer = None
        with self._cond:
            if self._active:
                self._active = False
                if self._stopped_reason is None:
                    self._stopped_reason = "stopped"
            self._running = False
            self._cond.notify_all()
            writer = self._writer
        if writer is not None and writer is not threading.current_thread():
            writer.join(timeout=5.0)
        if leave:
            with self._cond:
                first = not self._left
                self._left = True
            if first:
                self._target.leave()

    # -- event entries (reader/control threads: enqueue-and-return ONLY) -----

    def arm(self, gen: int) -> bool:
        """SESSION_BEGIN barrier: adopt `gen` as the current generation.

        Per-generation state for `gen` is reset immediately (fresh session)
        and a _SessionBegin barrier is queued so the writer re-syncs at the
        correct point in the dispatch order. Events of any older generation
        are discarded from here on. Returns False when delivery is inactive
        or the barrier overflow-stopped the queue.
        """
        stopped = False
        with self._cond:
            if not self._active:
                return False
            self._session_gen = gen
            # Atomic with the generation bump: wipe ALL per-utterance state.
            # No event of the new generation can exist yet (we hold the lock),
            # so everything here belongs to older arms or same-numbered reuse.
            self._reset_session_locked()
            if len(self._dq) >= self._queue_size:
                stopped = self._stop_locked("queue-overflow")
                ok = False
            else:
                self._dq.append(_SessionBegin(gen=gen))
                self._cond.notify_all()
                ok = True
        if stopped:
            self._fire_on_stopped()
        return ok

    def on_partial(self, span: str, *, utterance: str, seq: int, gen: int) -> None:
        """Live partial: coalesce/dedup/enqueue under _cond, then return.

        Never touches the target, never blocks (R.5 enqueue-and-return).
        Newest-partial-wins: a queued partial of the same (gen, utterance)
        is REPLACED IN PLACE so it keeps its position — always dispatched
        before its own utterance's final.
        """
        stopped = False
        with self._cond:
            if not self._active or gen != self._session_gen:
                self._stats["discarded_stale"] += 1
                return
            key = (gen, utterance)
            if key in self._closed:
                self._stats["discarded_dup"] += 1  # late post-final partial
                return
            if seq <= self._high_seq.get(key, -1):
                self._stats["discarded_stale"] += 1  # late seq
                return
            self._high_seq[key] = seq
            if len(self._dq) >= self._queue_size:
                # Overflow STOPS delivery — never drop-and-continue, never wait.
                stopped = self._stop_locked("queue-overflow")
                if stopped:
                    self._stats["overflow"] += 1
                return
            for i, item in enumerate(self._dq):
                if isinstance(item, _Partial) and (item.gen, item.utterance) == key:
                    self._dq[i] = _Partial(gen=gen, utterance=utterance, seq=seq, span=span)
                    self._stats["coalesced"] += 1
                    self._cond.notify_all()
                    return
            self._dq.append(_Partial(gen=gen, utterance=utterance, seq=seq, span=span))
            self._cond.notify_all()
        if stopped:
            self._fire_on_stopped()

    def on_final(self, span: str, *, utterance: str, seq: int, gen: int) -> None:
        """Recognition final: an ordered barrier, never overwritten.

        Closes the utterance and raises the seq high-water at ENQUEUE time,
        so late partials and duplicate finals die on sight afterwards.
        """
        stopped = False
        with self._cond:
            if not self._active or gen != self._session_gen:
                self._stats["discarded_stale"] += 1
                return
            key = (gen, utterance)
            if key in self._closed:
                self._stats["discarded_dup"] += 1  # duplicate final
                return
            if seq <= self._high_seq.get(key, -1):
                self._stats["discarded_stale"] += 1  # late final
                return
            self._closed.add(key)
            self._high_seq[key] = seq
            if len(self._dq) >= self._queue_size:
                stopped = self._stop_locked("queue-overflow")
                if stopped:
                    self._stats["overflow"] += 1
                return
            self._dq.append(_Final(gen=gen, utterance=utterance, seq=seq, span=span))
            self._cond.notify_all()
        if stopped:
            self._fire_on_stopped()

    def on_final_dropped(self, *, utterance: str, gen: int) -> None:
        """BOUNDARY barrier for a dropped/filtered final (R.5: "a dropped or
        filtered final still closes its utterance boundary").

        Closes the utterance at enqueue with NO finalize call, ever.
        """
        stopped = False
        with self._cond:
            if not self._active or gen != self._session_gen:
                self._stats["discarded_stale"] += 1
                return
            key = (gen, utterance)
            if key in self._closed:
                self._stats["discarded_dup"] += 1
                return
            self._closed.add(key)
            if len(self._dq) >= self._queue_size:
                stopped = self._stop_locked("queue-overflow")
                if stopped:
                    self._stats["overflow"] += 1
                return
            self._dq.append(_Boundary(gen=gen, utterance=utterance))
            self._cond.notify_all()
        if stopped:
            self._fire_on_stopped()

    # -- state ---------------------------------------------------------------

    def is_active(self) -> bool:
        """True while delivery is live (acquire() ok, no stop has fired)."""
        with self._cond:
            return self._active

    def stats(self) -> dict:
        """Counters and state — counts and reasons, NEVER recognition text."""
        with self._cond:
            out = dict(self._stats)
            out.update(
                active=self._active,
                queue_depth=len(self._dq),
                session_gen=self._session_gen,
                expected_revision=self._expected_revision,
                stopped_reason=self._stopped_reason,
            )
            return out

    # -- deterministic dispatch seam (the SAME handler the writer thread runs)

    def _process_next(self, blocking: bool = False, timeout: float | None = None) -> bool:
        """Pop and execute at most ONE queue item. Returns False when the
        queue is exhausted (or delivery stopped), True when an item was
        consumed (dispatched, skipped, or discarded).

        The writer thread loops this with blocking=True; tests call it with
        blocking=False / drain() for fully deterministic dispatch.
        """
        with self._cond:
            while not self._dq:
                if not blocking or not self._running or not self._active:
                    return False
                self._cond.wait(1.0 if timeout is None else timeout)
            if not self._active:
                return False  # stopped: queued items are dead, no target call
            item = self._dq.popleft()
            # Mutation-time re-checks (R.5: "queued operations re-check at
            # mutation time") — an arm() racing the writer must not leak a
            # stale item through.
            if item.gen != self._session_gen:
                self._stats["discarded_stale"] += 1
                return True
            if isinstance(item, _SessionBegin):
                self._drop_stale_generations_locked(item.gen)
                return True
            key = (item.gen, item.utterance)
            if isinstance(item, _Boundary):
                self._closed_dispatched.add(key)  # boundary: NO target call
                return True
            if key in self._closed_dispatched:
                # Defensive closure re-check (enqueue-side checks make this
                # unreachable today, but the law is re-check at mutation time).
                self._stats["discarded_dup"] += 1
                return True
            prev_span = self._shown_span.get(key, "")
            revision = self._expected_revision
            if isinstance(item, _Partial) and rendered_equal(prev_span, item.span):
                # Zero-diff skip (R.1): renders identically ⇒ ZERO events —
                # no target call at all. Real case/punctuation/word diffs are
                # NEVER folded here (rendered_equal's contract).
                self._shown_span[key] = item.span
                self._stats["zero_diff_skipped"] += 1
                return True

        # ---- OUTSIDE _cond: AT MOST ONE target call (one op in flight) ----
        if isinstance(item, _Partial):
            result = self._target.show(item.gen, item.utterance, item.seq, revision, item.span)
        else:  # _Final — always ONE finalize (the adapter decides unchanged)
            result = self._target.finalize(
                item.gen, item.utterance, item.seq, revision, item.span
            )

        stopped = False
        with self._cond:
            if result is ShowResult.APPLIED:
                self._expected_revision = revision + 1  # +1 ONLY on applied
                self._shown_span[key] = item.span
                self._stats["applied"] += 1
            elif result is ShowResult.UNCHANGED:
                self._shown_span[key] = item.span  # no edit landed: no advance
                self._stats["unchanged"] += 1
            else:  # REFUSED / UNKNOWN — stop, NEVER retry (R.5)
                stopped = self._stop_locked(result.value)
        if stopped:
            self._fire_on_stopped()
        return True

    def drain(self, max_items: int | None = None) -> int:
        """Run _process_next until the queue is exhausted; return item count.

        Deterministic test seam — identical semantics to the writer loop.
        """
        processed = 0
        while max_items is None or processed < max_items:
            if not self._process_next(blocking=False):
                break
            processed += 1
        return processed

    # -- internal ------------------------------------------------------------

    def _writer_loop(self) -> None:
        """The single writer: pops and executes one item at a time, forever,
        until delivery stops. One operation in flight by construction."""
        while True:
            with self._cond:
                if not self._running or not self._active:
                    return
            if not self._process_next(blocking=True, timeout=0.25):
                return

    def _reset_session_locked(self) -> None:
        """arm() time: clear ALL per-utterance state (call under _cond).

        Atomic with the session_gen bump, so nothing valid for the NEW
        generation can be wiped — only older arms' state existed.
        """
        self._high_seq.clear()
        self._closed.clear()
        self._closed_dispatched.clear()
        self._shown_span.clear()

    def _drop_stale_generations_locked(self, current_gen: int) -> None:
        """_SessionBegin dispatch: drop keys of OTHER generations only (call
        under _cond).

        Events enqueued after arm(current_gen) are NEWER than this barrier and
        queued behind it — their same-generation state (closures, high-water
        marks, shown spans) MUST survive this dispatch (R.5: barriers are
        ordered; only old-generation stragglers queued ahead are dead).
        """
        for key in [k for k in self._high_seq if k[0] != current_gen]:
            del self._high_seq[key]
        # Materialize before mutating — never iterate a set while updating it.
        self._closed.intersection_update([k for k in self._closed if k[0] == current_gen])
        self._closed_dispatched.intersection_update(
            [k for k in self._closed_dispatched if k[0] == current_gen]
        )
        for key in [k for k in self._shown_span if k[0] != current_gen]:
            del self._shown_span[key]

    def _stop_locked(self, reason: str) -> bool:
        """Transition to stopped; True iff THIS call caused the transition.

        Fires nothing here — callers invoke _fire_on_stopped() OUTSIDE the
        lock (a user callback must never run under _cond).
        """
        if not self._active:
            return False
        self._active = False
        self._stopped_reason = reason
        self._cond.notify_all()
        return True

    def _fire_on_stopped(self) -> None:
        """Fire the on_stopped seam exactly once per delivery lifetime."""
        with self._cond:
            if self._stopped_cb_fired or self._on_stopped is None:
                return
            self._stopped_cb_fired = True
            callback = self._on_stopped
            reason = self._stopped_reason
        try:
            callback(reason)
        except Exception:  # noqa: BLE001 — the seam must never break the stop path
            logger.warning("bulk_controller: on_stopped callback raised", exc_info=True)
