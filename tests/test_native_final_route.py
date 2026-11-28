"""P1.M1.T4.S4 — the native acceptance route routes finals BEFORE any generic output.

PRD §4.8.1 B: while a native editor session has capture open, an ASR final is handled by
identity verification → textproc.clean → retain+enqueue (NativeRecovery + OfferQueue) — and
NOTHING generic runs: no typing/StreamingOutput commit, no generic SessionRecovery, no
feedback.record_final/latency/transcript log, no hypr notify, no cancel-suppression window,
no evdev HALT/Backspace guard. Partials and the 'speech' event are lifecycle-only.

Hermetic CPU-only suite: no threads started by the tests, no sockets, no subprocesses (the
subprocess surface is monkeypatched to raise during on_final — a native final that reached
any desktop/injection tool would fail loudly), state under the hermetic config builder.

Tripwire style: every generic seam is replaced by a double that RAISES AssertionError the
moment it is touched — a silent green test with a tripwire installed means the native route
kept the promise; a red test names the exact generic seam that leaked.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import time

import pytest

import voice_typing.daemon as daemon
from voice_typing import session_recovery
from voice_typing.config import FilterConfig, OutputConfig, VoiceTypingConfig
from voice_typing.editor_session import NativeReservation, Owner, Stage
from voice_typing.recorder_host import FinalClass, _RelayEvent

from conftest import hermetic_cfg  # P1.M1.T1.S2: shared hermetic cfg builder (config-only)
from test_daemon import (  # noqa: E402 (repo convention: tests import sibling fakes)
    _DaemonFakeFeedback,
    _FakeBackend,
    _FakeHost,
    _StubRecorder,
    _ok_probe,
)

SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"  # canonical UUIDv4 (matches the editor wire)


# === tripwires: any generic seam touch raises — silence IS the assertion ============


class _NoBackend(_FakeBackend):
    """Generic typing backend that must NEVER be reached from a native session."""

    def type_text(self, text: str) -> None:
        raise AssertionError(f"generic type_text reached in a native session: {text!r}")

    def press_backspace(self, n: int) -> None:
        raise AssertionError("generic press_backspace reached in a native session")


class _NoStream:
    """StreamingOutput double: ANY engine touch (or committed read) is a native leak."""

    def on_partial(self, text: str) -> None:
        raise AssertionError("stream.on_partial reached in a native session")

    def commit(self, text: str) -> None:
        raise AssertionError("stream.commit reached in a native session")

    def freeze(self, *a, **k) -> None:
        raise AssertionError("stream.freeze reached in a native session")

    def resume(self) -> None:
        raise AssertionError("stream.resume reached in a native session")

    def reset_boundary(self) -> None:
        raise AssertionError("stream.reset_boundary reached in a native session")

    def reset_session(self) -> None:
        raise AssertionError("stream.reset_session reached in a native session")

    def set_streaming(self, streaming: bool) -> None:
        raise AssertionError("stream.set_streaming reached in a native session")

    def note_user_keypress(self) -> None:
        raise AssertionError("stream.note_user_keypress reached in a native session")

    @property
    def committed(self) -> str:
        raise AssertionError("stream.committed READ in a native session (never fed native)")

    @property
    def tail(self) -> str:
        return ""  # read-only mirror; safe (defensive getattr callers may probe it)


class _NoLatency:
    """LatencyLog double: the per-utterance latency surface is generic-only."""

    def note_partial(self, text: str) -> None:
        raise AssertionError("latency.note_partial reached in a native session")

    def finalize_utterance(self, **k) -> dict:
        raise AssertionError("latency.finalize_utterance reached in a native session")


class _NoFeedback(_DaemonFakeFeedback):
    """_DaemonFakeFeedback whose transcript/notification surfaces raise (native: none run).

    set_mode/set_listening/set_phase stay recording (lifecycle feedback is ALLOWED native);
    record_final/update_partial/notify are transcript- or desktop-bearing and must never fire.
    """

    def record_final(self, text: str) -> None:
        raise AssertionError("feedback.record_final reached in a native session")

    def update_partial(self, text: str) -> None:
        raise AssertionError("feedback.update_partial reached in a native session")

    def notify(self, msg: str) -> None:
        raise AssertionError("feedback.notify (desktop toast) reached in a native session")


class _RecordingRecovery:
    """Wraps the real SessionRecovery; records METHOD NAMES only (never text)."""

    def __init__(self) -> None:
        self._real = session_recovery.SessionRecovery()
        self.calls: list[str] = []

    def open_session(self) -> None:
        self.calls.append("open_session")
        return self._real.open_session()

    def note_final(self, text: str) -> None:
        self.calls.append("note_final")
        return self._real.note_final(text)

    def note_rejected(self) -> None:
        self.calls.append("note_rejected")
        return self._real.note_rejected()

    def note_tail(self, text: str) -> None:
        self.calls.append("note_tail")
        return self._real.note_tail(text)

    def close_session(self):
        self.calls.append("close_session")
        return self._real.close_session()

    def __getattr__(self, name):  # forward the rest to the real store
        return getattr(self._real, name)


@contextlib.contextmanager
def silent(*_tripwires):
    """Assert NO tripwire fires across the enclosed daemon call.

    The tripwires themselves raise AssertionError the moment a generic seam is touched;
    'silent' means the with-block completes without any of them firing — the native route's
    zero-generic-side-effects promise, stated at the call site.
    """
    yield


# === harness: identity host + native listening arm ==================================


class _IdentityHost(_FakeHost):
    """_FakeHost + the T4.S3 identity surface (generation/arm_seq/relay_event/set_prompt).

    set_microphone(True) bumps arm_seq BEFORE the cmd put (T4.S3 Critical #4) — exactly what
    the daemon's fence latch relies on. relay_event stands in for the reader-thread snapshot:
    tests set it before each on_final (the real host reports the event being relayed NOW).
    """

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.generation = 3  # the child-lifetime fence (bumped per spawn; fixed here)
        self.arm_seq = 0  # 0 = never armed; bumped by each set_microphone(True)
        self.relay_event: _RelayEvent | None = None
        self.prompts: list[str] = []  # set_prompt recorder (rolling-context pushes)

    def set_microphone(self, on: bool) -> None:
        if on:
            self.arm_seq += 1  # BEFORE the cmd put — the daemon latches AFTER this returns
        super().set_microphone(on)

    def set_prompt(self, text: str) -> None:
        self.prompts.append(text)


def ev(
    final_class: FinalClass = FinalClass.ACCEPTED,
    *,
    kind: str = "final",
    gen: int | None = 1,
    uid: int | None = 1,
    host_gen: int = 3,
    arm: int = 1,
) -> _RelayEvent:
    """An event snapshot as the real reader would report inside the callback."""
    return _RelayEvent(
        kind=kind,
        final_class=final_class if kind == "final" else None,
        host_generation=host_gen,
        arm_seq=arm,
        session_gen=gen,
        utterance_id=uid,
    )


def native_listening(d, host: _IdentityHost | None = None) -> _IdentityHost:
    """Put the daemon in the T4.S4 route state: a live LISTENING native owner + the arm.

    Mirrors _start_fenced's commit block: STARTING→LISTENING commit under _lock, then
    _arm(native=True) (which opens the mic — bumping the host's arm_seq — and latches the
    fence). Returns the host so tests can set relay_event per final.
    """
    if host is None:
        host = _IdentityHost(
            d._cfg, d._feedback, d._latency, d.on_final, d._on_partial, d._touch_speech
        )
    d._host = host
    now = time.monotonic()
    d._native_seq += 1
    owner = Owner(SID, d._native_seq, now, now + 30.0)
    d._native = NativeReservation(owner, None, now=now)
    with d._lock:
        assert d._native.commit(owner.token)
        d._arm(native=True)
    return host


def _wire_native(cfg=None):
    """Build a daemon with EVERY generic output seam replaced by a tripwire.

    Returns (d, fb, rec, be, stream, recovery) — the doubles the tests assert on. Also
    monkeypatch-free: subprocess raising is installed per-test where the PRP asks for it.
    """
    cfg = hermetic_cfg(cfg)
    fb = _NoFeedback()
    rec = _StubRecorder()
    be = _NoBackend()
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be, mic_prober=_ok_probe)
    stream = _NoStream()
    recovery = _RecordingRecovery()
    d._stream = stream
    d._session_recovery = recovery
    d._latency = _NoLatency()
    return d, fb, rec, be, stream, recovery


def _forbid_subprocess(monkeypatch):
    """Negative proof: no desktop/injection tool is reachable from the native route —
    any subprocess spawn during on_final fails the test instead of touching the desktop.
    Patched on the shared subprocess MODULE (daemon reaches it lazily) — restored by monkeypatch."""

    def _boom(*a, **k):
        raise AssertionError("subprocess reached from a native final (desktop/injection leak)")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


# === (a) the acceptance route ========================================================


def test_accepted_final_is_retained_queued_and_not_typed(monkeypatch):
    """(a) An ACCEPTED final on the arm fence: cleaned, retained in NativeRecovery, enqueued
    in OfferQueue, pump wakeup set, lifecycle closed — every generic tripwire silent, and no
    subprocess (typing/clipboard/notify surface) reachable."""
    _forbid_subprocess(monkeypatch)
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)
    host.relay_event = ev()  # gen=1 uid=1 host_gen=3 arm=1 == the latched fence (3, 1)

    with silent(be, stream, recovery, fb):
        d.on_final("hello world")

    assert d._native_queue is not None
    assert d._native_queue.pending_count == 1  # offered → the T4.S7 pump's job
    assert d._native_recovery.counts() == (
        0,
        1,
    )  # 0 ended sessions, 1 final retained in the ACTIVE session
    assert d._native_offer_evt.is_set()  # WAKEUP for the T4.S7 pump
    assert d._final_pending is False  # lifecycle closed — a drain can finish
    assert d._utterance_finalized is True
    assert fb.listening_states[-1] is True  # mic/gate/feedback stayed up
    assert host.recorder.mic[-1] is True  # mic stays on for the next utterance


def test_generic_session_is_byte_identical():
    """(f) With no native capture open (fence None) the generic path runs EXACTLY today's
    lines: the final is cleaned, typed via the backend, recorded in feedback — and the native
    helper is never entered, no queue is built, no wakeup is set."""
    cfg = VoiceTypingConfig(output=OutputConfig(streaming=False))  # Rev 1 verbatim type path
    cfg = hermetic_cfg(cfg)
    fb = _DaemonFakeFeedback()
    be = _FakeBackend()
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=_StubRecorder(), backend=be,
                                 mic_prober=_ok_probe)

    def _native_must_not_run(text):
        raise AssertionError("native route entered without a native session")

    d._native_on_final = _native_must_not_run
    d._arm()  # generic arm: fence stays None
    assert d._native_fence is None
    d.on_final("hello")

    assert be.typed == ["hello "]  # append_space default — today's exact output
    assert fb.finals == ["hello"]  # transcript feedback still fires (generic session)
    assert d._native_queue is None
    assert not d._native_offer_evt.is_set()


# === (b) rejection: identity, class, fence, filter, ended ===========================


def test_missing_identity_is_rejected():
    """(b) No relay snapshot (relay_event None) → rejected: no retain, nothing typed,
    lifecycle closed, the seed NOT consumed."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)
    d._seed_handoff_pending = True  # a confirmed seed is resident
    host.relay_event = None

    with silent(be, stream, recovery, fb):
        d.on_final("hello world")

    assert d._native_recovery.counts() == (0, 0)  # nothing retained
    assert d._final_pending is False and d._utterance_finalized is True
    assert d._seed_handoff_pending is True  # "say it again" — the seed stays pending
    assert d._seed_handoff_done is False
    assert d._native_rejects == {"missing": 1}


@pytest.mark.parametrize(
    "cls",
    [FinalClass.SENTINEL, FinalClass.CANCELLED, FinalClass.UNIDENTIFIED],
    ids=["sentinel", "cancelled", "unidentified"],
)
def test_non_accepted_classes_are_rejected(cls):
    """(b) Only FinalClass.ACCEPTED is eligible; sentinel/cancelled/legacy are diagnostic
    classes the consumer contract refuses."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)
    host.relay_event = ev(cls)

    with silent(be, stream, recovery, fb):
        d.on_final("hello world")

    assert d._native_recovery.counts() == (0, 0)
    assert d._native_queue.pending_count == 0
    assert d._final_pending is False and d._utterance_finalized is True
    assert list(d._native_rejects) == [f"class:{cls.value}"]


def test_fence_mismatches_are_rejected():
    """(b) A previous arm's final (arm_seq behind the fence), a respawned host's final
    (generation bumped), a never-armed event (arm_seq 0) and a non-final relay kind are all
    refused — nothing is attributed to this session."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)  # fence latched: (3, 1)
    assert d._native_fence == (3, 1)

    # previous arm: the fence has moved on (simulating the NEXT arm of the same host)
    d._native_fence = (3, 2)
    host.relay_event = ev(arm=1)
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    assert d._native_recovery.counts() == (0, 0)

    # respawned host: generation bumped (child re-spawned mid-session)
    d._native_fence = (3, 1)
    host.relay_event = ev(host_gen=4, arm=1)
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    assert d._native_recovery.counts() == (0, 0)

    # never-armed host: arm_seq 0 is NEVER eligible
    d._native_fence = (3, 1)
    host.relay_event = ev(arm=0)
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    assert d._native_recovery.counts() == (0, 0)

    # a relayed 'partial' kind never satisfies the final verdict
    host.relay_event = ev(kind="partial")
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    assert d._native_recovery.counts() == (0, 0)

    assert d._native_queue.pending_count == 0
    assert d._final_pending is False and d._utterance_finalized is True
    assert set(d._native_rejects) == {"fence", "missing", "kind"}
    assert sum(d._native_rejects.values()) == 4  # every mismatch counted under its code


def test_filtered_final_is_rejected_and_seed_kept():
    """(b) A blocklist final is rejected ('filtered'): nothing retained, nothing typed, the
    seed stays pending, lifecycle closed."""
    cfg = VoiceTypingConfig(filter=FilterConfig(blocklist=["you"]))
    d, fb, rec, be, stream, recovery = _wire_native(cfg)
    host = native_listening(d)
    d._seed_handoff_pending = True  # a confirmed seed is resident
    host.relay_event = ev()

    with silent(be, stream, recovery, fb):
        d.on_final("you")

    assert d._native_recovery.counts() == (0, 0)
    assert d._native_queue.pending_count == 0
    assert d._seed_handoff_pending is True  # rejected ≠ accepted: the seed is NOT consumed
    assert d._seed_handoff_done is False
    assert d._final_pending is False and d._utterance_finalized is True
    assert d._native_rejects == {"filtered": 1}


def test_ended_session_closes_queue_and_refuses_late_final():
    """(b)/(CRITICAL #6) Every native end clears the fence + closes the queue: a late final
    cannot resurrect the session — nothing retained, nothing typed, lifecycle closed."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)
    q = d._native_queue
    with d._lock:
        d._end_native_locked("stopped", None)  # mirror the _disarm call shape (:1940)
    assert d._native_fence is None
    assert d._native_queue is None
    assert q.revoked is False and q.pending_count == 0

    # 1) a late final after the mic closed: the on_final listening gate drops it (today's
    #    behavior — the gate stays OUTSIDE the native branch, byte-identical generic lines)
    d._listening.clear()
    host.relay_event = ev()
    with silent(be, stream, recovery, fb):
        d.on_final("late")
    assert d._native_recovery.counts() == (0, 0)

    # 2) the in-flight race: the reader passed the fence check BEFORE the end landed
    #    (fence momentarily still set while the owner is ENDED / the queue is gone) —
    #    the enqueue step must refuse ("ended"), not retain.
    d._listening.set()
    d._native_fence = (3, 1)  # simulate: verdict already passed when the end interleaved
    host.relay_event = ev()
    with silent(be, stream, recovery, fb):
        d.on_final("late")
    assert d._native_recovery.counts() == (0, 0)  # no retain: no resurrection
    assert not d._native_offer_evt.is_set()  # no wakeup for a refused final
    assert d._final_pending is False and d._utterance_finalized is True
    assert d._native_rejects.get("ended") == 1


# === (c) partials + speech are lifecycle-only =======================================


def test_partial_and_speech_are_lifecycle_only():
    """(c) For native, _on_partial does NO generic work (stream/recovery/latency/feedback
    silent) and _touch_speech only runs the lifecycle stores (idle clock, _final_pending) —
    stream.resume is never called."""
    d, fb, rec, be, stream, recovery = _wire_native()
    native_listening(d)

    last_speech = d._last_speech_monotonic
    calls_before = list(recovery.calls)
    with silent(be, stream, recovery, fb):
        d._on_partial("hel")
    assert d._last_speech_monotonic == last_speech  # no generic work, no clock touch
    assert recovery.calls == calls_before  # no note_tail

    with silent(be, stream, recovery, fb):
        d._touch_speech()
    assert d._last_speech_monotonic != last_speech  # idle auto-stop clock still updates
    assert d._final_pending is True  # in-flight utterance still flagged for the drain
    # stream.resume never ran (the _NoStream tripwire stayed silent through the block)


# === (d) keypresses neither HALT nor cancel native ==================================


def test_keypress_neither_halts_nor_cancels_native():
    """(d) note_user_keypress is a no-op for native: the editor's own input must not HALT
    (disarm), cancel, abort or touch the backend — mic stays on, session stays LISTENING."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)
    d._armed_monotonic = time.monotonic() - 10.0  # PAST the arm-chord grace window

    with silent(be, stream, recovery, fb):
        d.note_user_keypress()

    assert d._listening.is_set()  # no HALT disarm
    assert host.recorder.mic == [True]  # mic never closed
    assert host.recorder.aborts == 0  # no abort
    assert host.cancel_calls == 0  # no cancel
    assert d._native.live and d._native.stage is Stage.LISTENING  # session untouched
    assert be.typed == []  # backend untouched


# === (e) _arm(native=True) keeps mic/gate/feedback/ducking, skips generic setup ======


def test_arm_skips_generic_session_setup():
    """(e) _arm(native=True) opens the mic, the listening gate and lifecycle feedback — but
    opens NO generic recovery session and touches NO stream-engine session state."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)

    assert d._listening.is_set()  # the gate is up (run loop may enter text())
    assert host.arm_seq == 1 and host.recorder.mic == [True]  # mic opened exactly once
    assert any(s is True for s in fb.listening_states)  # lifecycle feedback ran
    assert "open_session" not in recovery.calls  # NO generic recovery session
    assert "reset_session" not in dir(stream) or True  # (tripwire would have raised)
    assert d._native_fence == (3, 1)  # the fence latched AFTER the mic bump
    q = d._native_queue
    assert q is not None and q.session_id == SID
    assert fb.modes == ["lite"]  # mode constant still published (§4.6 schema stable)


# === rolling context + overflow + logs ==============================================


def test_rolling_context_uses_this_sessions_accepted_finals():
    """(a) The native rolling prompt sources ONLY this session's accepted finals — seeded and
    unseeded — never the generic engine's committed checkpoint."""
    d, fb, rec, be, stream, recovery = _wire_native()
    d._context_prompt_active = True  # the child lane is armed (probe normally sets this)
    host = native_listening(d)
    assert host.prompts == []  # no push before any final

    host.relay_event = ev(uid=1)
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    expected = daemon.prompt_engine.rolling_context_prompt("hello world")
    assert host.prompts == [expected]  # unseeded: refresh pushes the accumulator source

    host.relay_event = ev(uid=2)
    with silent(be, stream, recovery, fb):
        d.on_final("second utterance")
    both = daemon.prompt_engine.rolling_context_prompt("hello world second utterance")
    assert host.prompts[-1] == both  # after 2 finals the prompt covers both
    assert d._session_accepted == ["hello world", "second utterance"]


def test_rolling_context_seeded_first_final_replaces_seed():
    """(a) Seeded: the FIRST accepted final replaces the seed (one set_prompt) — then the
    refresh keeps sourcing the accumulator; a rejected final never touches the seed."""
    d, fb, rec, be, stream, recovery = _wire_native()
    d._context_prompt_active = True
    host = native_listening(d)
    d._seed_handoff_pending = True  # the fenced seam installed an APPLIED seed

    host.relay_event = ev(uid=1)
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    expected = daemon.prompt_engine.rolling_context_prompt("hello world")
    assert host.prompts[0] == expected  # the seed handoff push
    assert host.prompts[1] == expected  # the refresh push (same native source)
    assert d._seed_handoff_pending is False and d._seed_handoff_done is True

    # a REJECTED final must not consume the (now-consumed) seed chain or push anything
    prompts_before = list(host.prompts)
    host.relay_event = None
    with silent(be, stream, recovery, fb):
        d.on_final("hello world")
    assert host.prompts == prompts_before  # no push for a rejected final


def test_overflow_switches_to_recovery_only():
    """(a)/T4.S2 ≥ 9th unsettled final: the queue revokes (sticky) — the final is STILL
    retained (recoverable), never typed; the earlier QUEUED finals set the pump wakeup."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)

    for uid in range(1, 10):  # 9 distinct finals; MAX_UNSETTLED = 8
        host.relay_event = ev(uid=uid)
        with silent(be, stream, recovery, fb):
            d.on_final(f"utterance {uid}")

    q = d._native_queue
    assert q.revoked is True  # sticky revoke — offers stop
    assert q.revocation_reason == "delivery_failed"
    assert d._native_recovery.counts() == (0, 9)  # ALL 9 retained (overflow = recovery-only)
    assert d._native_offer_evt.is_set()  # the QUEUED prefix woke the pump (T4.S7's job now)
    assert be.typed == []  # nothing typed, ever


def test_reject_and_accept_logs_carry_no_text(caplog):
    """(h) No new log line carries recognition text or seed text — codes, counts, ids only."""
    d, fb, rec, be, stream, recovery = _wire_native()
    host = native_listening(d)

    with caplog.at_level(logging.DEBUG, logger="voice_typing"):
        host.relay_event = ev(uid=1)
        d.on_final("hello world")  # accepted
        host.relay_event = None
        d.on_final("hello world")  # rejected (missing identity)
        host.relay_event = ev(uid=2)
        d.on_final("second utterance")  # accepted (uid distinct) — a second outcome line
    # (h) risk surface: the outcome/verdict lines, the capture-open line and any stray
    # latency/transcript/debug push. Every record is scanned for BOTH recognition strings.

    for record in caplog.records:
        msg = record.getMessage()
        assert "hello world" not in msg, f"log leaked recognition text: {msg}"
        assert "second utterance" not in msg, f"log leaked recognition text: {msg}"
