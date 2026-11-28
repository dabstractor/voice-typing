"""P1.M1.T4.S6 — finalize ownership: one cleanup per native end + transcript-free hints.

PRD §4.8.1 B/C: every way a native editor session can end finishes through ONE exactly-once
cleanup (seed clear → recovery end_session → diagnostic log → desktop warning → on_end →
teardown callback), and the user learns WHAT happened (reason code + recovery hint) without
ANYONE learning WHAT WAS SAID — status, logs, notifications and the `ended` frame carry
codes/counts/ids only. Desktop warning only when the transport itself is gone
(disconnected / timeout). Shutdown and dead-host end a session with NO drain and expire the
recovery store at exit; idle-unload never kills the child under a live owner.

Hermetic CPU-only suite: no threads, sockets or subprocesses started by a test (the ONLY
threads a path may start are the pre-existing bounded fake-host stop threads); nothing
written under /tmp.
"""

from __future__ import annotations

import dataclasses
import logging
import time

import pytest

import voice_typing.ctl as ctl
from voice_typing.config import AsrConfig, VoiceTypingConfig
from voice_typing.daemon import (
    NATIVE_HINT_NONE,
    NATIVE_HINT_RECOVER,
    NATIVE_HINT_RECOVER_MAYBE_APPLIED,
    NativeEndState,
    build_ended_frame,
    native_end_hint,
)
from voice_typing.editor_protocol import validate_event
from voice_typing.editor_session import AckOutcome, Stage
from voice_typing.recorder_host import FinalClass, _CaptureBoundary, _RelayEvent

from conftest import hermetic_cfg
import test_daemon as td  # noqa: E402 (repo convention: tests import sibling fakes)
import test_editor_session as tes  # noqa: E402

SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"  # canonical UUIDv4 (matches the editor wire)
TEXT = "hello world"
SEED = "the quick seed phrase"


# === harness: injectable clock/timers (verbatim from tests/test_native_lifecycle.py) ===


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


class _PromptHost(_BHost):
    """_BHost with a set_prompt recorder (the context-prompt seed/clear seam)."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.prompts: list[str] = []

    def set_prompt(self, text):
        self.prompts.append(text)


def _ev(uid, gen=1, host_gen=3, arm=1, cls=FinalClass.ACCEPTED):
    """An event snapshot as the real reader would report inside the callback."""
    return _RelayEvent("final", cls, host_gen, arm, gen, uid)


def _make(cfg=None):
    """(daemon, clock, timers, recorder, backend) with the native seams injected."""
    d, fb, rec, be = td._make_daemon(cfg=cfg, backend=_NoBackend())
    fc, mt = FakeClock(), ManualTimers()
    d._native_clock, d._native_timers = fc.now, mt
    return d, fc, mt, rec, be


def _listening_native(d, host, ends, sid=SID):
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
    """What run() does when text() returns while _drain is set (+ the off-lock on_end
    delivery, which production gets for free from the parked start worker)."""
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


def _settling(d, fc, mt, ends, uid=7, sid=SID):
    """A native session in the middle of its ACK settlement: one accepted final queued
    (un-offered), the ASR drain done, the 5 s settle budget armed. Returns (token, queue)."""
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    token = _listening_native(d, host, ends, sid=sid)
    _in_flight(d, host, uid)
    assert d.native_stop("stopped") is None  # DRAINING now; the EndRecord comes later
    host.relay_event = _ev(uid)
    d.on_final(TEXT)  # the in-flight utterance's final is accepted + queued
    _text_returned(d)  # ASR drain complete -> mic off + settlement window armed
    q = d._native_queue
    assert d._native.stage is Stage.DRAINING and d._native_settle_deadline is not None
    return token, q, host


# === S6 recorders (injectable sink + teardown hook) ==================================


class _Sink:
    """Injectable desktop-warning sink: records messages, refuses to run under _lock."""

    def __init__(self, d):
        self.msgs: list[str] = []
        self._d = d

    def msg(self, text: str) -> None:
        assert not self._d._lock.locked(), "desktop warning ran under _lock"
        self.msgs.append(text)


class _Teardown:
    """Records NativeEndState objects; refuses to run under _lock."""

    def __init__(self, d):
        self.states: list[NativeEndState] = []
        self._d = d

    def record(self, state: NativeEndState) -> None:
        assert not self._d._lock.locked(), "teardown callback ran under _lock"
        self.states.append(state)


class _LockedEnds:
    """on_end collector that refuses to run under _lock (exactly-once proof)."""

    def __init__(self, d):
        self.records = []
        self._d = d

    def __call__(self, rec):
        assert not self._d._lock.locked(), "on_end ran under _lock"
        self.records.append(rec)


def _fb_texts(d) -> list[str]:
    """Every string the fake feedback surface currently holds (partials are phase-only in
    the stub snapshot; notify toasts land in .notifies + .toasts)."""
    fb = d._feedback
    vals = [v for v in fb.snapshot().values() if isinstance(v, str)]
    return vals + list(fb.notifies) + list(getattr(fb, "toasts", []))


def _no_text(blob: str, *needles: str) -> None:
    for needle in needles:
        assert needle not in blob, f"leaked {needle!r}"


# === (a) one stop, one cleanup, one state ===========================================


def test_stop_without_text_ends_once_and_publishes_state():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    td_cb = _Teardown(d)
    d.set_native_teardown(td_cb.record)
    ends = _LockedEnds(d)
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)

    recd = d.native_stop("stopped", token=tok)

    assert recd is not None and recd.reason == "stopped"
    assert d._native.stage is Stage.ENDED
    assert len(ends.records) == 1 and ends.records[0] is recd
    assert len(td_cb.states) == 1
    state = td_cb.states[0]
    assert (state.session_id, state.reason) == (SID, "stopped")
    assert state.recoverable is False and state.hint == NATIVE_HINT_NONE
    assert d._native_recovery.active_id() is None
    assert d.native_last_end() is state
    assert sink.msgs == []  # stopped: no desktop warning
    assert d.native_last_end().frame() == {
        "event": "ended",
        "id": SID,
        "reason": "stopped",
        "recoverable": False,
    }

    # a repeated/late call adds nothing
    assert d.native_stop("stopped", token=tok) is None
    assert len(ends.records) == 1 and len(td_cb.states) == 1 and sink.msgs == []


def test_ended_frame_has_exactly_the_prd_keys():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    recd = d.native_stop("stopped", token=tok)
    state = d.native_last_end()
    assert state is not None and recd is not None
    assert set(state.frame()) == {"event", "id", "reason", "recoverable"}
    assert state.frame() == {
        "event": "ended",
        "id": SID,
        "reason": "stopped",
        "recoverable": False,
    }
    validate_event(state.frame())  # codec-valid: must not raise
    assert build_ended_frame(SID, "stopped", False) == state.frame()
    # the pure hint mapping: None snapshot -> not recoverable
    assert native_end_hint("stopped", None) == (False, NATIVE_HINT_NONE)


# === (c) recoverable/hint follow the recovery store =================================


def test_unconfirmed_final_sets_recover_hint():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    assert d.native_stop("stopped", token=tok) is None
    host.relay_event = _ev(7)
    d.on_final(TEXT)  # the in-flight final is retained + queued (unconfirmed)
    _text_returned(d)
    handle = d._native_settle_timer
    fc.advance(5.0)
    mt.fire(handle)  # settle budget spent -> 'timeout' / 'settle-timeout'

    assert d._native.stage is Stage.ENDED
    state = d.native_last_end()
    assert state.reason == "timeout" and state.cause == "settle-timeout"
    assert state.recoverable is True and state.hint == NATIVE_HINT_RECOVER
    assert d._native_recovery.recover(SID) is not None
    # a settle timeout means the editor stopped responding -> ONE desktop warning
    assert len(sink.msgs) == 1
    assert sink.msgs[0] == (
        "Dictation stopped: editor stopped responding. Start again in your editor."
        f" Unconfirmed text: voicectl recover {SID}"
    )
    assert TEXT not in sink.msgs[0]


def test_disconnected_loss_warns_with_recovery_hint():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    host.relay_event = _ev(7)
    d.on_final(TEXT)  # retained, un-offered

    recd = d.native_lost("disconnected")

    assert recd is not None and recd.reason == "disconnected"
    assert d._native.stage is Stage.ENDED
    state = d.native_last_end()
    assert state.recoverable is True and state.hint == NATIVE_HINT_RECOVER
    assert len(sink.msgs) == 1
    assert sink.msgs[0] == (
        "Dictation stopped: editor connection lost. Start again in your editor."
        f" Unconfirmed text: voicectl recover {SID}"
    )
    assert state.desktop_warning == sink.msgs[0]
    assert TEXT not in sink.msgs[0]


def test_target_lost_does_not_desktop_warn():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    host.relay_event = _ev(7)
    d.on_final(TEXT)

    recd = d.native_lost("target_lost")  # a LIVE transport: the editor warns itself

    assert recd is not None and recd.reason == "target_lost"
    state = d.native_last_end()
    assert state.recoverable is True and state.hint == NATIVE_HINT_RECOVER
    assert sink.msgs == []  # no desktop popup for target_lost
    assert state.desktop_warning is None


def test_acknowledged_final_is_not_recoverable():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    q = d._native_queue
    with d._lock:
        att = q.begin_offer(fc.now())
    with d._lock:
        outcome = q.ack({"cmd": "applied", "id": SID, "seq": att.seq}, fc.now())
    assert outcome is AckOutcome.SETTLED

    recd = d.native_stop("stopped", token=tok)

    assert recd is not None
    assert d._native_recovery.recover(SID) is None  # fully-ACKed ending is DISCARDED
    state = d.native_last_end()
    assert state.recoverable is False and state.hint == NATIVE_HINT_NONE
    assert sink.msgs == []


def test_cancelled_is_not_recoverable_unless_possibly_applied():
    # (i) the user asked to drop the words: an unattempted retained final stays silent
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    recd = d.native_cancel(token=tok)
    assert recd is not None and recd.reason == "cancelled"
    state = d.native_last_end()
    assert state.recoverable is False and state.hint == NATIVE_HINT_NONE
    assert sink.msgs == []

    # (ii) but an offer write that may have landed must be reported
    d2, fc2, mt2, _r2, _b2 = _make()
    sink2 = _Sink(d2)
    d2._native_warning_sink = sink2.msg
    ends2 = tes._Ends()
    host2 = _BHost(d2._cfg, d2._feedback, d2._latency, d2.on_final, d2._on_partial, d2._touch_speech)
    tok2 = _listening_native(d2, host2, ends2)
    host2.relay_event = _ev(7)
    d2.on_final(TEXT)
    q2 = d2._native_queue
    with d2._lock:
        att2 = q2.begin_offer(fc2.now())  # mark-BEFORE-write: possibly_applied
    assert att2 is not None
    recd2 = d2.native_cancel(token=tok2)
    assert recd2 is not None and recd2.reason == "cancelled"
    state2 = d2.native_last_end()
    assert state2.recoverable is True
    assert state2.hint == NATIVE_HINT_RECOVER_MAYBE_APPLIED
    assert sink2.msgs == []  # cancel is NOT a desktop-warn reason


def test_possibly_applied_warning_mentions_partial_typing():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    q = d._native_queue
    with d._lock:
        att = q.begin_offer(fc.now())  # attempted, never ACKed
    assert att is not None

    recd = d.native_lost("disconnected")

    assert recd is not None and recd.reason == "disconnected"
    state = d.native_last_end()
    assert state.recoverable is True
    assert state.hint == NATIVE_HINT_RECOVER_MAYBE_APPLIED
    assert len(sink.msgs) == 1
    assert sink.msgs[0].endswith("(may already be partially typed)")
    assert TEXT not in sink.msgs[0]


# === (f) shutdown / dead host: no drain, store expired at exit =======================


def test_shutdown_expires_recovery_and_ends_without_drain():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    td_cb = _Teardown(d)
    d.set_native_teardown(td_cb.record)
    ends = tes._Ends()
    token, q, host = _settling(d, fc, mt, ends)
    settle_handle = d._native_settle_timer
    assert d._native_recovery.counts() == (0, 1)  # TEXT retained

    d.request_shutdown()

    recd = ends.records[0]
    assert recd.reason == "shutdown" and recd.cause == "shutdown"
    assert d._native.stage is Stage.ENDED
    assert d.native_last_end().reason == "shutdown"
    assert d._drain is False  # no drain was armed by the shutdown
    assert host.recorder.aborts == 0
    assert host.cancel_calls == 0
    assert settle_handle in mt.cancelled  # the settle watchdog was retired
    assert d._native_recovery.recover(SID) is None  # store expired at exit
    assert d._native_recovery.counts() == (0, 0)
    assert len(ends.records) == 1 and len(td_cb.states) == 1

    d.shutdown()  # a second exit call is idempotent and keeps the store empty

    assert len(ends.records) == 1 and len(td_cb.states) == 1
    assert d._native_recovery.counts() == (0, 0)


def test_shutdown_method_alone_expires_recovery():
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    host.relay_event = _ev(7)
    d.on_final(TEXT)  # retained

    d.shutdown()

    assert d._native.stage is Stage.ENDED
    assert ends.records[0].reason == "shutdown"
    assert d.native_last_end().reason == "shutdown"
    assert d._native_recovery.recover(SID) is None
    assert d._native_recovery.counts() == (0, 0)


def test_dead_child_ends_without_drain_exactly_once():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    td_cb = _Teardown(d)
    d.set_native_teardown(td_cb.record)
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    ducks: list[int] = []
    real_release = d._duck_release
    d._duck_release = lambda *a, **k: (ducks.append(1), real_release(*a, **k))
    host._alive = False  # the child just died

    d._handle_dead_host()

    assert d._native.stage is Stage.ENDED
    recd = ends.records[0]
    assert (recd.reason, recd.cause) == ("disconnected", "host-died")
    assert d._drain is False  # no drain for a dead child
    assert host.recorder.aborts == 0
    assert host.cancel_calls == 0
    assert host.stop_calls == 0  # a dead child is never stopped
    assert len(ducks) == 1  # duck released exactly once
    assert d._listening.is_set() is False
    assert d._load_error
    assert len(ends.records) == 1 and len(td_cb.states) == 1
    assert sink.msgs == []  # transport is gone but this is not an editor-loss popup
    nat = d.status_snapshot()["native"]
    assert nat["state"] == "ended" and nat["reason"] == "disconnected"

    d._handle_dead_host()  # a racing repeat is the documented NO-OP

    assert len(ends.records) == 1 and len(td_cb.states) == 1 and len(ducks) == 1
    assert host.stop_calls == 0 and host.recorder.aborts == 0


def test_dead_child_while_starting_reports_load_failed():
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    res = d.reserve_native(None, SID, on_end=ends)
    assert res.accepted
    host._alive = False

    d._handle_dead_host()

    assert d._native.stage is Stage.ENDED
    recd = ends.records[0]
    assert (recd.reason, recd.cause) == ("load_failed", "host-died")
    state = d.native_last_end()
    validate_event(state.frame())  # load_failed is codec-valid as an ended reason
    assert sink.msgs == []


# === (g) idle-unload defers under a live owner =======================================


def test_idle_unload_is_deferred_under_a_live_owner():
    cfg = hermetic_cfg(VoiceTypingConfig(asr=AsrConfig(auto_unload_idle_seconds=1.0)))
    d, fc, mt, rec, be = _make(cfg)
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    d._host = host
    d._models_loaded = True
    d._disarmed_monotonic = time.monotonic() - 10.0  # far past the 1.0 s threshold

    # (i) STARTING (reserved, no worker)
    res = d.reserve_native(None, SID, on_end=ends)
    assert res.accepted and d._native.stage is Stage.STARTING
    d._maybe_idle_unload()
    assert host.stop_calls == 0  # deferred: a live owner is never unloaded under

    # (ii) LISTENING
    with d._lock:
        assert d._native.commit(res.owner.token)
        d._arm(native=True)
    d._maybe_idle_unload()
    assert host.stop_calls == 0

    # (iii) DRAINING settling
    _in_flight(d, host, 7)
    assert d.native_stop("stopped", token=res.owner.token) is None
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    _text_returned(d)
    assert d._native.stage is Stage.DRAINING and d._native_settle_deadline is not None
    d._disarmed_monotonic = time.monotonic() - 10.0  # _disarm re-stamped it just now
    d._maybe_idle_unload()
    assert host.stop_calls == 0  # still deferred while settling

    # the session ends -> the next tick reclaims normally
    fc.advance(5.0)
    mt.fire(d._native_settle_timer)
    assert d._native.stage is Stage.ENDED
    d._disarmed_monotonic = time.monotonic() - 10.0
    d._maybe_idle_unload()
    assert host.stop_calls == 1


# === (h) responsiveness + (e) the always-present native block ========================


def test_status_is_responsive_and_transcript_free_in_every_phase():
    d, fc, mt, rec, be = _make()
    fb = d._feedback
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)

    def _check(phase: str) -> dict:
        t0 = time.monotonic()
        s = d.status_snapshot()
        assert time.monotonic() - t0 < 1.0, f"status blocked in {phase}"
        nat = s["native"]
        assert set(nat) == {"state", "id", "reason", "recoverable", "hint"}
        assert nat["state"] == phase
        for v in list(nat.values()) + [v for v in s.values() if isinstance(v, str)]:
            _no_text(str(v), TEXT, SEED)
        return nat

    # STARTING (reserved, no worker)
    d._host = host
    res = d.reserve_native(None, SID, on_end=ends)
    assert res.accepted
    nat = _check("starting")
    assert nat["id"] == SID and nat["reason"] is None

    # LISTENING with dictated text in the feedback surface
    with d._lock:
        assert d._native.commit(res.owner.token)
        d._arm(native=True)
    fb.update_partial(TEXT)
    _check("listening")

    # DRAINING (settling, TEXT queued in recovery)
    _in_flight(d, host, 7)
    assert d.native_stop("stopped", token=res.owner.token) is None
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    _text_returned(d)
    assert d._native.stage is Stage.DRAINING
    _check("draining")

    # ENDED
    fc.advance(5.0)
    mt.fire(d._native_settle_timer)
    nat = _check("ended")
    assert nat["reason"] == "timeout" and nat["recoverable"] is True
    assert nat["hint"] == NATIVE_HINT_RECOVER


def test_stop_and_quit_are_responsive_in_every_phase():
    def _phase_daemon(phase: str):
        d, fc, mt, rec, be = _make()
        ends = tes._Ends()
        host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
        if phase == "starting":
            d._host = host
            d.reserve_native(None, SID, on_end=ends)
        elif phase == "listening":
            _listening_native(d, host, ends)
        elif phase == "draining":
            tok = _listening_native(d, host, ends)
            _in_flight(d, host, 7)
            assert d.native_stop("stopped", token=tok) is None
            host.relay_event = _ev(7)
            d.on_final(TEXT)
            _text_returned(d)
        else:  # ended
            tok = _listening_native(d, host, ends)
            d.native_stop("stopped", token=tok)
        return d

    for phase in ("starting", "listening", "draining", "ended"):
        d = _phase_daemon(phase)
        t0 = time.monotonic()
        d.stop()
        assert time.monotonic() - t0 < 1.0, f"stop blocked in {phase}"

        d2 = _phase_daemon(phase)
        t0 = time.monotonic()
        d2.request_shutdown()
        assert time.monotonic() - t0 < 1.0, f"request_shutdown blocked in {phase}"
        if phase != "ended":  # a live session ends at once, with NO drain
            assert d2._native.stage is Stage.ENDED
        assert d2._drain is False


def test_status_native_block_defaults_when_never_used():
    d, fc, mt, rec, be = _make()
    assert d._lock.locked() is False
    s = d.status_snapshot()
    assert d._lock.locked() is False  # status takes NO lock for the native block
    assert s["native"] == {
        "state": "inactive",
        "id": None,
        "reason": None,
        "recoverable": False,
        "hint": None,
    }
    assert d._native_status.as_dict() == s["native"]  # one immutable attribute, no rebuild
    assert d.native_last_end() is None


# === (k) nothing blocking under the lock; cleanup without a callback =================


def test_end_cleanup_never_runs_under_the_lock():
    def _install(d, host):
        # end_session is ALLOWED (required) inside the terminal lock hold — leaf store only
        rec_store = d._native_recovery
        real_end = rec_store.end_session

        def end_session(sid, reason, *a, **k):
            assert d._lock.locked(), "end_session must run inside the terminal lock hold"
            return real_end(sid, reason, *a, **k)

        rec_store.end_session = end_session
        # every callback/sink/host call must run OFF the lock
        _lock_free(d, host, "abort")
        _lock_free(d, host, "cancel")
        _lock_free(d, host, "stop")
        sink = _Sink(d)
        d._native_warning_sink = sink.msg
        td_cb = _Teardown(d)
        d.set_native_teardown(td_cb.record)
        ends = _LockedEnds(d)
        _lock_free(d, d, "_clear_context_prompt")
        return ends

    # 1) stop (with drain + settle)
    d, fc, mt, rec, be = _make()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    ends = _install(d, host)
    tok = _listening_native(d, host, ends)
    _in_flight(d, host, 7)
    d.native_stop("stopped", token=tok)
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    _text_returned(d)
    fc.advance(5.0)
    mt.fire(d._native_settle_timer)
    assert d._native.stage is Stage.ENDED and len(ends.records) == 1

    # 2) cancel
    d2, fc2, mt2, _r, _b = _make()
    host2 = _BHost(d2._cfg, d2._feedback, d2._latency, d2.on_final, d2._on_partial, d2._touch_speech)
    ends2 = _install(d2, host2)
    tok2 = _listening_native(d2, host2, ends2)
    host2.relay_event = _ev(7)
    d2.on_final(TEXT)
    d2.native_cancel(token=tok2)
    assert d2._native.stage is Stage.ENDED and len(ends2.records) == 1

    # 3) lost
    d3, fc3, mt3, _r3, _b3 = _make()
    host3 = _BHost(d3._cfg, d3._feedback, d3._latency, d3.on_final, d3._on_partial, d3._touch_speech)
    ends3 = _install(d3, host3)
    tok3 = _listening_native(d3, host3, ends3)
    d3.native_lost("disconnected")
    assert d3._native.stage is Stage.ENDED and len(ends3.records) == 1

    # 4) dead host
    d4, fc4, mt4, _r4, _b4 = _make()
    host4 = _BHost(d4._cfg, d4._feedback, d4._latency, d4.on_final, d4._on_partial, d4._touch_speech)
    ends4 = _install(d4, host4)
    _listening_native(d4, host4, ends4)
    host4._alive = False
    d4._handle_dead_host()
    assert d4._native.stage is Stage.ENDED and len(ends4.records) == 1

    # 5) shutdown
    d5, fc5, mt5, _r5, _b5 = _make()
    host5 = _BHost(d5._cfg, d5._feedback, d5._latency, d5.on_final, d5._on_partial, d5._touch_speech)
    ends5 = _install(d5, host5)
    _listening_native(d5, host5, ends5)
    d5.request_shutdown()
    assert d5._native.stage is Stage.ENDED and len(ends5.records) == 1


def test_cleanup_runs_without_an_on_end_callback():
    d, fc, mt, rec, be = _make()
    host = _PromptHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    d._host = host
    clears: list[int] = []
    real_clear = d._clear_context_prompt

    def counting_clear(*a, **k):
        clears.append(1)
        return real_clear(*a, **k)

    d._clear_context_prompt = counting_clear
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    td_cb = _Teardown(d)
    d.set_native_teardown(td_cb.record)
    d._context_prompt_active = True  # the child confirmed a seed is resident
    res = d.reserve_native(None, SID, on_end=None)  # NO on_end registered
    assert res.accepted
    with d._lock:
        assert d._native.commit(res.owner.token)
        d._arm(native=True)
    baseline_prompts = len(host.prompts)

    recd = d.native_stop("stopped", token=res.owner.token)

    assert recd is not None  # cleanup must NOT depend on a callback being registered
    state = d.native_last_end()
    assert state is not None and state.reason == "stopped"
    assert len(td_cb.states) == 1 and td_cb.states[0] is state
    assert len(clears) >= 1  # the seed clear was attempted
    assert host.prompts[baseline_prompts:] == [""]  # the child got the CLEAR put
    assert sink.msgs == []  # stopped is not a warn reason


def test_seed_is_cleared_after_every_native_end():
    def _seeded(cfg=None):
        d, fc, mt, rec, be = _make(cfg)
        host = _PromptHost(
            d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech
        )
        d._host = host
        attempts: list[int] = []
        real_clear = d._clear_context_prompt

        def counting_clear(*a, **k):
            attempts.append(1)
            return real_clear(*a, **k)

        d._clear_context_prompt = counting_clear
        ends = tes._Ends()
        tok = _listening_native(d, host, ends)
        d._context_prompt_active = True  # seed resident (capability confirmed)
        host.set_prompt(SEED)
        return d, host, tok, attempts, ends

    # stop / cancel / lost / shutdown: the child survives -> it gets the CLEAR put
    for cause in ("stop", "cancel", "lost", "shutdown"):
        d, host, tok, attempts, ends = _seeded()
        baseline = len(host.prompts)
        if cause == "stop":
            d.native_stop("stopped", token=tok)
        elif cause == "cancel":
            d.native_cancel(token=tok)
        elif cause == "lost":
            d.native_lost("disconnected")
        else:
            d.request_shutdown()
        assert len(attempts) >= 1, f"{cause}: seed clear not attempted"
        assert host.prompts[baseline:] == [""], f"{cause}: no clear put reached the child"
        assert not d._lock.locked()

    # dead host: the clear is still ATTEMPTED, but the capability died with the child so
    # the (gone) child receives nothing — the gate keeps it a safe no-op.
    d, host, tok, attempts, ends = _seeded()
    host._alive = False
    d._handle_dead_host()
    assert len(attempts) >= 1
    assert host.prompts == [SEED]  # unchanged: the gate (capability None) blocked the put

    # context_prompt disabled by config: never called (no prime, no clear, ever)
    cfg_off = hermetic_cfg(VoiceTypingConfig(asr=AsrConfig(context_prompt=False)))
    d2, host2, tok2, attempts2, _e2 = _seeded(cfg_off)
    assert host2.prompts == [SEED]  # the seed we pushed; the arm itself never primed/cleared
    d2.native_stop("stopped", token=tok2)
    assert host2.prompts == [SEED] and len(attempts2) >= 1  # attempted, gated to a no-op


# === (i) content tripwires + (§4.8.1 C) diagnostic log ==============================


def test_feedback_and_logs_carry_no_content(caplog):
    d, fc, mt, rec, be = _make()
    sink = _Sink(d)
    d._native_warning_sink = sink.msg
    ends = tes._Ends()
    host = _PromptHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    d._context_prompt_active = True
    host.set_prompt(SEED)  # a confirmed seed is resident in the child
    host.relay_event = _ev(7)
    d.on_final(TEXT)  # dictated text retained in the recovery store

    with caplog.at_level(logging.DEBUG, logger="voice_typing"):
        recd = d.native_lost("disconnected")

    assert recd is not None
    state = d.native_last_end()
    fb = d._feedback
    blob = "\n".join(
        [
            caplog.text,
            repr(_fb_texts(d)),
            repr(fb.snapshot()),
            repr(sink.msgs),
            repr(d.status_snapshot()["native"]),
            repr(dataclasses.asdict(state)),
            repr(state.frame()),
        ]
    )
    _no_text(blob, TEXT, SEED)
    lines = [r.getMessage() for r in caplog.records if "voice-typing native: ended id=" in r.getMessage()]
    assert lines, "the §4.8.1 C diagnostic line is missing"
    assert "reason=" in lines[-1] and "hint=" in lines[-1]
    _no_text(lines[-1], TEXT, SEED)


def test_abnormal_end_logs_at_warning_level(caplog):
    # stopped -> the INFO line only
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    with caplog.at_level(logging.INFO, logger="voice_typing"):
        d.native_stop("stopped", token=tok)
    stopped = [
        r for r in caplog.records if "voice-typing native: ended id=" in r.getMessage()
    ]
    assert len(stopped) == 1 and stopped[0].levelno == logging.INFO
    caplog.clear()  # the second daemon must be judged on its own records

    # disconnected -> WARNING with id/reason/hint (codes only)
    d2, fc2, mt2, _r2, _b2 = _make()
    ends2 = tes._Ends()
    host2 = _BHost(d2._cfg, d2._feedback, d2._latency, d2.on_final, d2._on_partial, d2._touch_speech)
    tok2 = _listening_native(d2, host2, ends2)
    with caplog.at_level(logging.INFO, logger="voice_typing"):
        d2.native_lost("disconnected")
    lost = [r for r in caplog.records if "voice-typing native: ended id=" in r.getMessage()]
    assert len(lost) == 1 and lost[0].levelno == logging.WARNING
    msg = lost[0].getMessage()
    assert f"id={SID}" in msg and "reason=disconnected" in msg and "hint=" in msg


def test_duck_is_released_on_every_end_path():
    def _counter(d):
        n = []
        real = d._duck_release
        d._duck_release = lambda *a, **k: (n.append(1), real(*a, **k))
        return n

    # stop with a drain: released when the mic closes (_disarm tail)
    d, fc, mt, rec, be = _make()
    ends = tes._Ends()
    host = _BHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    tok = _listening_native(d, host, ends)
    n1 = _counter(d)
    _in_flight(d, host, 7)
    d.native_stop("stopped", token=tok)
    host.relay_event = _ev(7)
    d.on_final(TEXT)
    _text_returned(d)
    assert len(n1) >= 1

    # cancel: released in the same hold as the end
    d2, fc2, mt2, _r2, _b2 = _make()
    ends2 = tes._Ends()
    host2 = _BHost(d2._cfg, d2._feedback, d2._latency, d2.on_final, d2._on_partial, d2._touch_speech)
    tok2 = _listening_native(d2, host2, ends2)
    n2 = _counter(d2)
    d2.native_cancel(token=tok2)
    assert len(n2) >= 1

    # dead host: the §4.2quinquies edge release
    d3, fc3, mt3, _r3, _b3 = _make()
    ends3 = tes._Ends()
    host3 = _BHost(d3._cfg, d3._feedback, d3._latency, d3.on_final, d3._on_partial, d3._touch_speech)
    _listening_native(d3, host3, ends3)
    n3 = _counter(d3)
    host3._alive = False
    d3._handle_dead_host()
    assert len(n3) >= 1

    # loss during STARTING: duck was never engaged -> never released
    d4, fc4, mt4, _r4, _b4 = _make()
    ends4 = tes._Ends()
    res = d4.reserve_native(None, SID, on_end=ends4)
    assert res.accepted
    n4 = _counter(d4)
    d4.native_lost("disconnected")
    assert n4 == []


# === ctl rendering + help ============================================================


def test_ctl_renders_native_state_and_hint():
    resp = {
        "ok": True,
        "listening": False,
        "mode": "lite",
        "phase": "idle",
        "native": {
            "state": "ended",
            "id": SID,
            "reason": "disconnected",
            "recoverable": True,
            "hint": "recover",
        },
    }
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "native: ended" in text
    assert f"native: ended ({SID})" in text
    assert "native end: disconnected" in text
    assert f"unconfirmed text: voicectl recover {SID}" in text
    _no_text(text, TEXT, SEED)

    # state inactive -> NO native lines at all
    text2, code2 = ctl.format_result(
        "status",
        {
            "ok": True,
            "listening": False,
            "native": {"state": "inactive", "id": None, "reason": None,
                       "recoverable": False, "hint": None},
        },
    )
    assert code2 == 0
    assert "native:" not in text2

    # recover_maybe_applied hint renders the partial-typing caveat
    text3, _c3 = ctl.format_result(
        "status",
        {
            "ok": True,
            "listening": False,
            "native": {"state": "ended", "id": SID, "reason": "timeout",
                       "recoverable": True, "hint": "recover_maybe_applied"},
        },
    )
    assert "native end: timeout" in text3
    assert (
        f"unconfirmed text: voicectl recover {SID} (may already be partially typed)"
        in text3
    )


def test_ctl_status_help_mentions_native():
    parser = ctl._build_parser()
    assert "native" in parser.format_help()
    assert "recovery hint" in ctl.__doc__ or "native editor session" in ctl.__doc__


# === (j) generic paths unchanged without a native owner ==============================

_OLD_STATUS_KEYS = {
    "listening",
    "mode",
    "output_mode",
    "phase",
    "models_loaded",
    "load_error",
    "partial",
    "last_final",
    "uptime_s",
    "device",
    "compute_type",
    "model",
    "mic_ok",
    "mic_error",
    "context_prompt",
    "delivery_mode",
    "delivery_state",
    "delivery_reason",
    "last_confirmed_op",
}


def test_generic_paths_unchanged_without_a_native_owner():
    d, fc, mt, rec, be = _make()
    s = d.status_snapshot()
    assert set(s) == _OLD_STATUS_KEYS | {"native"}  # additive only
    assert s["native"]["state"] == "inactive"

    # the idle-unload guard is a NO-OP without a native owner
    host = td._FakeHost(d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech)
    d._host = host
    d._models_loaded = True
    d._disarmed_monotonic = time.monotonic() - 10**6  # far past the 1800 s default threshold
    d._maybe_idle_unload()
    assert host.stop_calls == 1

    # request_shutdown behaves as today (no reservation to end, nothing published)
    d2, _fc2, _mt2, _r2, _b2 = _make()
    d2.request_shutdown()
    assert d2._shutdown.is_set()
    assert d2.native_last_end() is None
    assert d2._native_status.as_dict()["state"] == "inactive"
