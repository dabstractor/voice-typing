"""voice_typing.ducking_async — non-blocking engage/release dispatch (PRD §4.2quinquies, D1).

FAILURE DISCIPLINE (the invariant every line here serves): ducking is an
enhancement, NEVER a gate. The arm path (daemon `_arm()`, the toast site) runs
UNDER the daemon's control lock `self._lock` — called inline, S1's AudioDucker
would hold that CONTROL LOCK across up to ~2 s of ≤1 s-per-call subprocess work
(mpris tier: list + one pause per playing player). That is the exact wedge class
that once made `voicectl start/stop/toggle` hit `timeout`/exit-124 (validation
NEW-2; `abort()` was already moved out of `_lock` for the same reason — see
daemon.py's `_safe_abort`). Hence this module:

  * engage()/release() NEVER block the caller: they flip a desired-state slot
    under a TINY lock (acquired, state written, released — NEVER held across a
    backend call, a join, or a sleep) and ensure at most ONE short-lived daemon
    worker thread ("vt-ducking", daemon=True) applies it — the fire-and-forget
    spawn shape the daemon already uses in its signal handler
    (daemon.py:2738-2742, `voice-typing-signal-shutdown`).

WHY NOT ONE THREAD PER CALL: three racing threads (engage, release, engage)
contend on the inner ducker's lock in ARRIVAL order, not request order — a
release that lands before the first engage leaves media DUCKED while disarmed
(a stale engage applied last). The inner ducker's idempotence fixes duplicate
work, not ORDER. So this wrapper is a single-flight LATEST-WINS dispatcher:
the worker takes the latest pending state each iteration, so the finally-applied
state always matches the LAST request (rapid arm→disarm→arm ends armed).

HUNG BACKEND: the tiers promise ≤1 s per subprocess call; a backend that breaks
its own contract (say, hangs 5 s) cannot delay the caller (dispatch is O(µs))
and is applied eventually whenever the stuck worker finishes. We deliberately do
NOT watchdog-kill the worker — thread murder adds risk for zero product value;
crash safety belongs to the wiring task (T3.S2: `ducked` flag + ExecStopPost).

FLUSH CONTRACT (T3's quit seam): flush(timeout) waits BOUNDED for full drain
(no pending state, no live worker) and returns bool — True fast when idle/drained,
False on timeout. Best-effort join, never force, never raises.

OWNERSHIP MAP: S1 audio_ducking.py owns bookkeeping + user sovereignty (FROZEN);
S2 ducking_mpris.py / S3 ducking_volume.py own the subprocess tiers; S4 (this
file) owns ONLY the dispatch discipline — non-blocking entry, coalescing,
latest-wins ordering, bounded flush; T3 owns the daemon wiring + crash safety
(AsyncDucker(AudioDucker.from_config(cfg, backend))); T4 owns the default flip.
Tier-agnostic: zero tier/daemon imports; wraps ANY engage/release pair.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_WORKER_NAME = "vt-ducking"


class AsyncDucker:
    """Failure-discipline wrapper (PRD §4.2quinquies): non-blocking, bounded, idempotent.

    Wraps an AudioDucker (or any duck-typed engage/release pair with an `engaged`
    property) for the daemon's arm/disarm seams. engage()/release() record the
    latest desired state under a tiny lock, coalesce duplicates, and ensure at
    most one short-lived `vt-ducking` daemon worker applies pending states; both
    return immediately and never raise. The worker is the ONLY thread that
    touches the inner ducker's engage/release.
    """

    def __init__(self, ducker: Any) -> None:
        self._ducker = ducker
        self._lock = threading.Lock()       # tiny: never held across a backend call
        self._desired: bool | None = None   # True=engage pending, False=release pending, None=idle
        self._alive = False                 # a worker thread exists
        self._applied = threading.Event()   # set each time the worker drains the queue

    # --- public API ---

    def engage(self) -> None:
        """Request ducking; returns immediately, never raises (never a gate)."""
        self._dispatch(True)

    def release(self) -> None:
        """Request unduck; returns immediately, never raises (never a gate)."""
        self._dispatch(False)

    def flush(self, timeout: float = 2.0) -> bool:
        """Bounded-wait until every pending state is applied (T3's quit seam).

        True = fully drained (no pending state, no live worker); False = timed
        out (e.g. a hung backend call). Never force-kills anything; never raises.
        """
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                with self._lock:
                    if self._desired is None and not self._alive:
                        return True
                time.sleep(0.02)
            return False
        except Exception:
            logger.warning("ducking: flush failed; continuing")
            return False

    @property
    def engaged(self) -> bool:
        """Proxy the inner ducker's engaged flag; False (never raises) on failure."""
        try:
            return bool(self._ducker.engaged)
        except Exception:
            logger.warning("ducking: engaged read failed; continuing")
            return False

    # --- dispatch (the discipline) ---

    def _dispatch(self, engaged: bool) -> None:
        """Record the latest desired state; ensure one worker is applying it.

        The lock is TINY: acquired only to flip the slot — never held across a
        backend call, a join, or a sleep. Same pending state → coalesced (case e);
        different pending state → overwritten (latest-wins ordering).
        """
        try:
            spawn = False
            with self._lock:
                if self._desired == engaged and self._desired is not None:
                    return  # coalesce: same state already pending (case e)
                self._desired = engaged  # latest-wins: overwrites any pending state
                self._applied.clear()
                if not self._alive:
                    self._alive = True
                    spawn = True
            if spawn:
                try:
                    threading.Thread(target=self._worker, name=_WORKER_NAME, daemon=True).start()
                except Exception:
                    # Spawn failed: un-latch so a later dispatch can retry and
                    # flush() still reports not-drained honestly.
                    with self._lock:
                        self._alive = False
                        self._applied.set()
                    raise
        except Exception:
            logger.warning("ducking: async dispatch failed; continuing")

    def _worker(self) -> None:
        """Apply pending states until none remain, then exit (short-lived).

        The ONLY thread that calls the inner ducker's engage/release. Takes the
        LATEST pending state each iteration — a stale engage can never survive a
        newer release (or vice versa). Any backend/ducker failure is one warning.
        """
        while True:
            with self._lock:
                state, self._desired = self._desired, None
                if state is None:
                    self._alive = False
                    self._applied.set()
                    return
            try:
                if state:
                    self._ducker.engage()
                else:
                    self._ducker.release()
            except Exception:
                logger.warning(
                    "ducking: async %s failed; continuing", "engage" if state else "release"
                )
            with self._lock:
                self._applied.set()
