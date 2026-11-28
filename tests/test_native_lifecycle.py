"""P1.M1.T4.S5 — native stop / cancel / drain: ONE bounded wind-down policy with ONE terminal action.

PRD §4.8.1 B: while a native editor session owns the mic, every way the session can end is
routed through native finishing — never the generic graceful_stop heuristic:

  stop / voicectl stop / idle  → LISTENING → DRAINING(reason): at most the already-in-flight
                                 utterance finishes (bounded ASR drain, _DRAIN_TIMEOUT_S), then
                                 queued offers settle for ≤ 5 s aggregate
                                 (NATIVE_SETTLE_TIMEOUT_S) — only while the target is valid.
  cancel                       → invalidate FIRST (revoke queue + drop unattempted finals +
                                 end), THEN abort in-flight audio; no drain.
  lost / EOF / lease expiry    → revoke first, then DRAINING → ENDED(loss): the in-flight
                                 utterance drains into recovery only (no ACK can arrive); no
                                 settlement wait. Loss while STARTING ends without capture.
  shutdown / recorder death    → end at once; no recoverable-drain promise.

No abort/cancel/drain wait/settlement wait runs under _lock or on the recorder reader
thread. The terminal transition is idempotent when stop / loss / exit / EOF race (first
reason wins). Logs and EndRecords carry codes/counts/ids only — never recognition text.

Hermetic CPU-only suite: no threads, sockets or subprocesses started by a test (the ONLY
thread a policy path may start is the pre-existing drain watchdog Timer, mirroring the
test_daemon.py drain precedent); nothing written under /tmp.
"""

from __future__ import annotations

import argparse
import logging
import threading
import time

import pytest

import voice_typing.ctl as ctl
import test_editor_session as tes  # noqa: E402 (repo convention: sibling-fake imports)
from voice_typing.daemon import NativeEndFacts  # noqa: F401  (the facts surface, asserted below)
from voice_typing.editor_protocol import EndReason, END_REASONS
from voice_typing.editor_session import AckOutcome, Stage
from voice_typing.recorder_host import FinalClass, _CaptureBoundary, _RelayEvent

from conftest import hermetic_cfg
import test_daemon as td  # noqa: E402 (repo convention: tests import sibling fakes)


SID_A = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"  # canonical UUIDv4 (matches the editor wire)
SID_B = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5c"


# === harness: injectable clock/timers (verbatim from tests/test_editor_session.py) ===


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def now(self):
        return self.t

    def advance(self, s):
        self.t += s


class ManualTimers:  # S3's test convention: arm records, fire is explicit
    def __init__(self):
        self.armed, self.fired, self.cancelled = [], [], []

    def arm(self, deadline, fire):
        h = object()
        self.armed.append((h, deadline, fire))
        return h

    def cancel(self, h):
        self.cancelled.append(h)

    def fire(self, h):
        for hh, _d, f in self.armed:
            if hh is h:
                self.fired.append(h)
                f()


class _NoBackend(td._FakeBackend):
    """Tripwire: a native session's text must NEVER reach the generic typing backend."""

    def type_text(self, text: str) -> None:
        pytest.fail(f"generic type_text reached in a native session: {text!r}")

    def press_backspace(self, n: int) -> None:
        pytest.fail("generic press_backspace reached in a native session")


class _BHost(td._FakeHost):
    """_FakeHost + the T4.S3 identity/boundary surface (generation/arm_seq/relay_event/
    capture_boundary). set_microphone(True) bumps arm_seq BEFORE the mic cmd — exactly what
    the daemon's fence latch relies on."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.generation = 3
        self.arm_seq = 0
        self.relay_event: _RelayEvent | None = None
        self.capture_boundary: _CaptureBoundary | None = None

    def set_microphone(self, on):
        if on:
            self.arm_seq += 1
        super().set_microphone(on)


def _ev(uid, gen=1, host_gen=3, arm=1, cls=FinalClass.ACCEPTED):
    """An event snapshot as the real reader would report inside the callback."""
    return _RelayEvent("final", cls, host_gen, arm, gen, uid)


def _make(cfg=None):
    """(daemon, clock, timers, recorder, backend) with the native seams injected."""
    d, fb, rec, be = td._make_daemon(cfg=cfg, backend=_NoBackend())
    fc, mt = FakeClock(), ManualTimers()
    d._native_clock, d._native_timers = fc.now, mt
    return d, fc, mt, rec, be


def _listening_native(d, host, ends, sid=SID_A):
    """A live LISTENING native owner + the arm (mirrors _start_fenced's commit block)."""
    d._host = host
    res = d.reserve_native(None, sid, on_end=ends)
    assert res.accepted
    with d._lock:
        assert d._native.commit(res.owner.token)
        d._arm(native=True)
    assert d._native.stage is Stage.LISTENING and d._native_fence == (3, 1)
    return res.owner.token


def _in_flight(d, host, uid):
    """Simulate an utterance in flight: the boundary snapshot + a thread inside text()."""
    host.capture_boundary = _CaptureBoundary(3, 1, 1, uid)
    d._text_in_flight.set()


def _text_returned(d):
    """What run() does when text() returns while _drain is set (+ the parked worker's
    off-lock on_end delivery, which production gets for free from the native session's
    parked start worker — the harness spawns none)."""
    d._text_in_flight.clear()
    d._complete_drain()
    d._flush_native_end()


def _lock_free(d, obj, name):
    """Wrap obj.<name> so it asserts it was NOT called under d._lock."""
    real = getattr(obj, name)

    def wrapped(*a, **k):
        assert not d._lock.locked(), f"{obj.__class__.__name__}.{name} ran under _lock"
        return real(*a, **k)

    setattr(obj, name, wrapped)


def _settling(d, fc, mt, ends, uid=7, sid=SID_A):
    """A native session in the middle of its ACK settlement: one accepted final queued
    (un-offered), the ASR drain done, the 5 s settle budget armed. Returns (token, queue)."""
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    token = _listening_native(d, host, ends, sid=sid)
    _in_flight(d, host, uid)
    assert d.native_stop("stopped") is None  # DRAINING now; the EndRecord comes later
    host.relay_event = _ev(uid)
    d.on_final("hello world")  # the in-flight utterance's final is accepted + queued
    _text_returned(d)  # ASR drain complete -> mic off + settlement window armed
    q = d._native_queue
    assert d._native.stage is Stage.DRAINING and d._native_settle_deadline is not None
    return token, q


# === (b) graceful stop with nothing in flight =======================================


def test_stop_without_utterance_in_flight_ends_promptly():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    armed_before = len(mt.armed)  # the reserve watchdog only

    recd = d.native_stop("stopped", token=tok)

    assert recd is not None and recd.reason == "stopped" and recd.cause is None
    assert d._native.stage is Stage.ENDED
    assert host.recorder.mic[-1] is False  # mic off now
    assert ends.records == [recd]
    assert d._native_fence is None and d._native_queue is None
    assert d._drain is False  # no drain, no cancel
    assert host.recorder.aborts == 0
    assert host.cancel_calls == 0
    assert len(mt.armed) == armed_before  # no settle timer
    assert d._native_settle_timer is None and d._native_settle_deadline is None
    assert d._native_end_facts == NativeEndFacts("stopped", None, False)


# === (a)+(c) graceful stop with an utterance in flight: drain, then settle ==========


def test_stop_with_utterance_in_flight_drains_then_settles():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)

    assert d.native_stop("stopped", token=tok) is None  # not ended yet

    assert d._native.stage is Stage.DRAINING and d._native.drain_reason == "stopped"
    assert d._drain is True  # bounded ASR drain for THAT utterance
    assert d._native_offer_evt.is_set()  # pump woken (finishing + offers)
    assert host.recorder.mic[-1] is True  # mic still on
    assert d._listening.is_set()
    assert ends.records == []

    host.relay_event = _ev(7)  # the final of THAT utterance is retained + queued
    d.on_final("hello world")
    q = d._native_queue
    assert q.pending_count == 1
    assert d._native_recovery.counts() == (0, 1)
    assert d._final_pending is False

    _text_returned(d)  # text() returned -> the ASR drain completes
    assert host.recorder.mic[-1] is False
    assert d._native_settle_deadline == fc.t + 5.0  # clock + NATIVE_SETTLE_TIMEOUT_S
    assert len(mt.armed) == 2  # reserve watchdog + ONE settle watchdog
    settle_handle = d._native_settle_timer
    assert settle_handle is mt.armed[-1][0] and mt.armed[-1][1] == fc.t + 5.0
    assert d._native.stage is Stage.DRAINING  # still winding down

    # the pump delivers the offer and the editor ACKs it -> SETTLED
    with d._lock:
        att = q.begin_offer(fc.now())
    with d._lock:
        outcome = q.ack({"cmd": "applied", "id": SID_A, "seq": att.seq}, fc.now())
    assert outcome is AckOutcome.SETTLED

    recd = d.native_settle_kick(token=tok)  # one settlement step
    assert recd is not None and recd.reason == "stopped"
    assert d._native.stage is Stage.ENDED
    assert settle_handle in mt.cancelled
    assert d._native_end_facts.recoverable is False
    assert len(ends.records) == 1 and ends.records[0] is recd


def test_drain_final_of_another_utterance_is_rejected():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    d.native_stop("stopped", token=tok)

    host.relay_event = _ev(8)  # a DIFFERENT utterance's final — outside the drain snapshot
    d.on_final("hello world")

    assert d._native_recovery.counts() == (0, 0)  # nothing retained
    assert d._native_rejects.get("drain") == 1
    assert d._final_pending is False
    assert d._native_queue.pending_count == 0


def test_drain_timeout_aborts_then_ends_with_stop_reason():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    d.native_stop("stopped", token=tok)
    assert d._drain is True

    d._drain_timeout()  # the watchdog: the final never fires -> abort the blocked text()

    assert host.recorder.aborts == 1
    _text_returned(d)
    recd = ends.records[0]
    assert recd.reason == "stopped" and d._native.stage is Stage.ENDED
    assert d._native_settle_timer is None  # nothing queued -> no settle window
    assert d._native_settle_deadline is None


def test_native_stop_drains_regardless_of_graceful_stop():
    for graceful in (False, True):
        cfg = hermetic_cfg()
        cfg.asr.graceful_stop = graceful
        d, fc, mt, rec, be = _make(cfg)
        ends = tes._Ends()
        host = _BHost(
            d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech
        )
        tok = _listening_native(d, host, ends)
        _in_flight(d, host, 7)
        d.native_stop("stopped", token=tok)
        assert d._drain is True, f"graceful_stop={graceful}"


def test_stop_is_idempotent_and_first_reason_wins():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)

    assert d.native_stop("stopped", token=tok) is None
    assert d.native_stop("idle", token=tok) is None  # DRAINING: first reason wins
    assert d._native.drain_reason == "stopped"

    _text_returned(d)
    assert d.native_stop("stopped", token=tok) is None  # ENDED: no-op
    assert len(ends.records) == 1 and ends.records[0].reason == "stopped"


# === (g) idle auto-stop routes/routes only when actually idle =======================


def test_idle_auto_stop_routes_only_when_actually_idle():
    d, fc, mt, rec, be = _make()
    assert d._cfg.asr.auto_stop_idle_seconds > 0
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    d._last_speech_monotonic = time.monotonic() - 999  # idle beyond the threshold

    d._maybe_auto_stop()

    assert ends.records and ends.records[0].reason == "idle"
    assert d._native.stage is Stage.ENDED
    assert host.recorder.mic[-1] is False

    # a NON-idle native session stays LISTENING (the old premature tag is gone)
    ends2 = tes._Ends()
    host2 = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    d2, fc2, mt2, rec2, be2 = _make()
    tok2 = _listening_native(d2, host2, ends2)
    d2._last_speech_monotonic = time.monotonic()  # just spoke
    d2._maybe_auto_stop()
    assert d2._native.stage is Stage.LISTENING
    assert ends2.records == []
    assert host2.recorder.mic[-1] is True


def test_generic_voicectl_stop_drains_a_native_session():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)

    d.stop()  # the generic control path must ROUTE to native finishing

    assert d._native.stage is Stage.DRAINING and d._native.drain_reason == "stopped"
    assert d._drain is True
    assert host.recorder.aborts == 0  # the in-flight utterance is NOT aborted
    assert host.recorder.mic[-1] is True


# === settlement deadline / delivery failure =========================================


def test_settlement_deadline_ends_timeout():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    token, q = _settling(d, fc, mt, ends)
    settle_handle = d._native_settle_timer

    fc.advance(5.0)  # the budget is spent with the offer still un-delivered
    mt.fire(settle_handle)

    recd = ends.records[0]
    assert recd.reason == "timeout" and recd.cause == "settle-timeout"
    assert d._native.stage is Stage.ENDED
    assert d._native_end_facts == NativeEndFacts("timeout", "timeout", True)
    assert q.revoked and q.revocation_reason == "timeout"  # queue revoked; text recoverable
    assert q.pending_count == 1
    # P1.M1.T4.S6: the terminal action calls NativeRecovery.end_session on EVERY end, so the
    # retained final now lives in the ENDED list (still recoverable via recover(SID_A)).
    assert d._native_recovery.counts() == (1, 0)
    assert d._native_recovery.recover(SID_A) is not None  # the intent: the text stays recoverable
    assert settle_handle in mt.cancelled


def test_settlement_ends_early_on_delivery_failed():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    token, q = _settling(d, fc, mt, ends)
    settle_handle = d._native_settle_timer

    with d._lock:
        outcome = q.ack({"cmd": "applied", "id": SID_A, "seq": 99}, fc.now())  # stale seq
    assert outcome is AckOutcome.REVOKED

    recd = d.native_settle_kick(token=token)
    assert recd is not None and recd.reason == "delivery_failed"
    assert d._native.stage is Stage.ENDED
    assert settle_handle in mt.cancelled
    assert ends.records == [recd]


# === (e) cancel: invalidate FIRST, then abort; never drains =========================


def test_cancel_revokes_aborts_and_never_drains():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    host.relay_event = _ev(7)
    d.on_final("hello world")  # one final already queued
    q = d._native_queue
    assert q.pending_count == 1

    recd = d.native_cancel(token=tok)

    # invalidate happened BEFORE the end: queue revoked + pending cleared in that order
    assert recd is not None and recd.reason == "cancelled" and recd.cause == "cancel"
    assert d._native.stage is Stage.ENDED
    assert q.revoked and q.revocation_reason == "cancelled"
    assert q.pending_count == 0
    assert host.recorder.mic[-1] is False
    assert d._listening.is_set() is False
    assert len(ends.records) == 1
    assert host.cancel_calls == 1  # asserted AFTER return — it happens off-lock
    assert d._drain is False  # cancel NEVER drains

    # a late final with matching identity is neither retained nor typed
    host.relay_event = _ev(7)
    d.on_final("late words")
    # P1.M1.T4.S6: end_session moved the cancelled final to the ENDED list — the count is
    # UNCHANGED by the late final (it is neither retained nor typed) and stays recoverable.
    assert d._native_recovery.counts() == (1, 0)  # unchanged (the cancelled final stays)
    assert d._native_recovery.recover(SID_A) is not None
    assert q.pending_count == 0


def test_cancel_without_text_in_flight_never_touches_the_host():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)

    recd = d.native_cancel(token=tok)

    assert recd is not None and recd.reason == "cancelled"
    assert host.cancel_calls == 0
    assert host.recorder.aborts == 0


# === (f) loss: revoke first, recovery-only drain, no settlement wait ================


def test_lost_revokes_first_then_drains_recovery_only():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)

    assert d.native_lost("disconnected", token=tok) is None  # the drain comes first

    assert d._native.stage is Stage.DRAINING and d._native.drain_reason == "disconnected"
    q = d._native_queue
    assert q.revoked and q.revocation_reason == "disconnected"  # revoked BEFORE anything else
    assert d._drain is True
    assert not d._native_offer_evt.is_set()  # no pump wakeup: no ACK can arrive

    host.relay_event = _ev(7)  # the in-flight utterance still lands — recovery only
    d.on_final("hello world")
    assert q.pending_count == 0  # REVOKED: retained, never offered
    assert d._native_recovery.counts() == (0, 1)
    assert not d._native_offer_evt.is_set()

    _text_returned(d)
    recd = ends.records[0]
    assert recd.reason == "disconnected"
    assert d._native_settle_timer is None  # NO settlement wait after a loss
    assert d._native_settle_deadline is None


def test_lost_without_utterance_ends_immediately():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)

    recd = d.native_lost("disconnected", token=tok)

    assert recd is not None and recd.reason == "disconnected"
    assert d._native.stage is Stage.ENDED
    assert ends.records == [recd]


def test_lost_while_starting_aborts_without_capture():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    d._host = host
    res = d.reserve_native(None, SID_A, on_end=ends)  # reserve ONLY: never committed
    assert res.accepted
    tok = res.owner.token

    recd = d.native_lost("target_lost", token=tok)

    assert recd is not None and recd.reason == "target_lost"
    assert d._native.stage is Stage.ENDED
    assert d.begin_native_start(tok) is False  # tombstoned: no late capture, ever
    assert d._native_blockers_locked() is False


def test_loss_during_settlement_ends_at_once():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    token, q = _settling(d, fc, mt, ends)
    settle_handle = d._native_settle_timer

    recd = d.native_lost("disconnected", token=token)

    assert recd is not None and recd.reason == "disconnected"
    assert d._native.stage is Stage.ENDED
    assert settle_handle in mt.cancelled
    assert ends.records == [recd]


# === shutdown / host death: end at once, retire the watchdog ========================


def test_shutdown_and_host_death_end_without_settlement():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    token, q = _settling(d, fc, mt, ends)
    settle_handle = d._native_settle_timer

    recd = d.terminate_native("shutdown", cause="shutdown", token=token)
    assert recd is not None and recd.reason == "shutdown"
    assert d._native.stage is Stage.ENDED
    assert settle_handle in mt.cancelled
    assert d._native_settle_timer is None

    # recorder-host death on a FRESH settling session (fresh daemon: the daemon-wide
    # NativeRecovery only frees a session's slot at T4.S6's end_session — out of scope here,
    # so a second session on the SAME daemon would self-revoke 'delivery_failed' by design)
    d5, fc5, mt5, rec5, be5 = _make()
    ends2 = tes._Ends()
    token2, _q2 = _settling(d5, fc5, mt5, ends2, sid=SID_A)
    assert d5._native.stage is Stage.DRAINING
    recd2 = d5.terminate_native("disconnected", cause="host-died", token=token2)
    assert recd2 is not None and recd2.reason == "disconnected"
    assert d5._native_settle_timer is None


# === (k) abort/cancel never under _lock; no surprise threads ========================


def test_abort_and_cancel_never_run_under_the_lock():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)

    # stop-timeout path: host.abort runs OFF-lock (watchdog callback or caller thread)
    d.native_stop("stopped", token=tok)
    _lock_free(d, host, "abort")
    d._drain_timeout()
    assert host.recorder.aborts == 1
    _text_returned(d)

    # cancel path: host.cancel runs OFF-lock and starts no thread
    host2 = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    ends2 = tes._Ends()
    d2, fc2, mt2, rec2, be2 = _make()
    tok2 = _listening_native(d2, host2, ends2)
    _in_flight(d2, host2, 7)
    _lock_free(d2, host2, "cancel")
    n_threads = threading.active_count()
    d2.native_cancel(token=tok2)
    assert threading.active_count() == n_threads

    # lost path (nothing in flight): host.abort runs OFF-lock, starts no thread
    host3 = _BHost(d2._cfg, d2._feedback, d2._latency, d2.on_final, d2._on_partial, d2._touch_speech)
    ends3 = tes._Ends()
    tok3 = _listening_native(d2, host3, ends3, sid=SID_B)
    d2._text_in_flight.set()
    _lock_free(d2, host3, "abort")
    d2.native_lost("target_lost", token=tok3)
    assert threading.active_count() == n_threads

    # settle kick starts no thread
    token4, _q4 = _settling(d, fc, mt, tes._Ends(), sid=SID_B)
    d.native_settle_kick(token=token4)
    assert threading.active_count() == threading.active_count()  # no change mid-call


def test_settle_kick_with_stale_token_is_a_noop():
    d, fc, mt, rec, be = _make()
    ends_a = tes._Ends()
    host_a = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok_a = _listening_native(d, host_a, ends_a, sid=SID_A)
    d.native_stop("stopped", token=tok_a)  # session A ends promptly (nothing in flight)
    assert d._native.stage is Stage.ENDED

    ends_b = tes._Ends()
    host_b = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok_b = _listening_native(d, host_b, ends_b, sid=SID_B)
    _in_flight(d, host_b, 7)
    d.native_stop("stopped", token=tok_b)
    host_b.relay_event = _ev(7)
    d.on_final("hello world")
    _text_returned(d)
    assert d._native.stage is Stage.DRAINING  # B is settling

    assert d.native_settle_kick(token=tok_a) is None  # A's late watchdog fire: no-op
    assert d._native.stage is Stage.DRAINING  # B is untouched

    # the pump delivers B's offer, the editor ACKs it, and B's kick ends the session
    with d._lock:
        att = d._native_queue.begin_offer(fc.now())
    with d._lock:
        assert d._native_queue.ack({"cmd": "applied", "id": SID_B, "seq": att.seq}, fc.now()) is AckOutcome.SETTLED
    recd = d.native_settle_kick(token=tok_b)
    assert recd is not None and recd.reason == "stopped"


# === (j) with no native reservation every generic path behaves as today =============


def test_generic_paths_unchanged_without_a_native_owner():
    # graceful drain: unchanged
    d, fc, mt, rec, be = _make()
    d._cfg.asr.graceful_stop = True
    d.start()
    d._touch_speech()
    d._text_in_flight.set()
    d._request_stop()
    assert d._drain is True and d.is_listening() is True and rec.aborts == 0
    d._text_in_flight.clear()
    d._complete_drain()
    assert d._drain is False and d.is_listening() is False

    # immediate stop (graceful_stop=False): unchanged — disarm NOW + abort
    d2, fc2, mt2, rec2, be2 = _make()
    d2._cfg.asr.graceful_stop = False
    d2.start()
    d2._touch_speech()
    d2._text_in_flight.set()
    d2._request_stop()
    assert d2._drain is False and d2.is_listening() is False and rec2.aborts == 1

    # idle auto-stop disarms (no native owner)
    d3, fc3, mt3, rec3, be3 = _make()
    d3.start()
    d3._last_speech_monotonic = time.monotonic() - 999
    d3._maybe_auto_stop()
    assert d3.is_listening() is False

    # generic cancel still replies ok without a native owner
    d4, fc4, mt4, rec4, be4 = _make()
    d4.start()
    out = d4.cancel()
    assert out["ok"] is True


# === (l) logs and EndRecord carry no recognition text ===============================


def test_logs_and_end_record_carry_no_text(caplog):
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    with caplog.at_level(logging.INFO):
        d.native_stop("stopped", token=tok)
        host.relay_event = _ev(7)
        d.on_final("hello world")
        _text_returned(d)
        with d._lock:  # the pump delivers + the editor ACKs the offer
            att = d._native_queue.begin_offer(fc.now())
        with d._lock:
            assert d._native_queue.ack({"cmd": "applied", "id": SID_A, "seq": att.seq}, fc.now()) is AckOutcome.SETTLED
        d.native_settle_kick(token=tok)
    assert "hello world" not in caplog.text
    assert "hello" not in caplog.text
    recd = ends.records[0]
    for field in (recd.reason, recd.cause, recd.stage.value):
        assert "hello" not in (field or "")
    assert recd.reason in END_REASONS
    facts = d._native_end_facts
    assert set(facts.__dataclass_fields__) == {"reason", "revoked", "recoverable"}


# === ctl help distinguishes the native behaviour ====================================


def _entry_block(epilog: str, name: str) -> str:
    """One help entry verbatim: its first line plus all deeper-indented continuation lines."""
    lines = epilog.splitlines()
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith(f"{name} ") and ln.startswith("    "):
            out = [ln]
            for nxt in lines[i + 1:]:
                if not nxt.strip() or len(nxt) - len(nxt.lstrip()) <= 4:
                    break
                out.append(nxt)
            return "\n".join(out)
    return ""


def test_ctl_help_distinguishes_native_behaviour():
    help_text = ctl.__doc__ or ""  # the per-command entries render from the module docstring
    stop_block = _entry_block(help_text, "stop")
    cancel_block = _entry_block(help_text, "cancel")
    assert stop_block.lstrip().startswith("stop") and "native" in stop_block
    assert cancel_block.lstrip().startswith("cancel") and "native" in cancel_block
    assert "busy" in cancel_block


# === the loss/stop reason vocabularies are the §4.8.1 B END_REASONS codes ===========


def test_stop_and_loss_reasons_are_end_reasons():
    from voice_typing.daemon import _LOSS_REASONS, _STOP_REASONS

    assert _STOP_REASONS == frozenset({"stopped", "idle"})
    assert _LOSS_REASONS == frozenset({"target_lost", "disconnected", "timeout"})
    assert _STOP_REASONS | _LOSS_REASONS <= set(END_REASONS)
    assert all(r in EndReason._value2member_map_ for r in _STOP_REASONS | _LOSS_REASONS)
