"""tests/test_bulk_dispatch.py — P1.M6.T2.S1: bulk dispatch wiring + cancel intercept.

Covers the daemon-side wiring ONLY (the controller/adapters have their own suites):
  - dispatch branches (on_final/_on_partial) route partials/finals/rejected finals into
    BulkController with identity (host.relay_identity) -> (gen, utterance=str(uid),
    seq=daemon-synthesized monotonic), enqueue-and-return on the reader thread;
  - the bulk cancel() intercept: ctrl.cancel(gen) OUT of _lock, ZERO physical-character
    compensation (no press_backspace), the SHARED suppress latch + host.cancel(), idempotent;
  - the arm/disarm/fault lifecycle: acquire→arm→start, unsupported-on-acquire-failure
    (recording stays armed), fault-class on_stopped disarms BOTH with ONE reason, the
    epoch-guarded stopper (leave() exactly once, never under _lock), quit teardown bounded;
  - the on_applied hook -> feedback.record_confirmed_op (counts + times only);
  - default delivery="stream-edit" is fully inert (the unit-level G1 parity pin).

NO CUDA, no real subprocess, no live desktop (AGENTS.md): fake bundle over a fake
DeliveryTarget, a fake RecorderHost with a settable relay_identity, a spy typing backend
(any call is a failure — the R.1 zero-legacy-call law), and a spy stream.

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q
"""
from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_typing import config as config_mod
from voice_typing.bulk_controller import BulkController
from voice_typing.bulk_delivery import AcquireResult, ShowResult
from voice_typing.daemon import VoiceTypingDaemon

from conftest import hermetic_cfg  # P1.M1.T1.S2: hermetic cfg for the helper's daemon ctor

# ---------------------------------------------------------------------------
# fakes — mirrors of the test_daemon / test_g2_bulk_gate doubles (kept local so
# the existing suites stay untouched; the additive-hook gate requires that).
# ---------------------------------------------------------------------------


class _Identity(NamedTuple):
    """Stand-in for recorder_host._RelayIdentity (the T1.S1 seam shape)."""

    session_gen: "int | None"
    utterance_id: "int | None"


class _SpyBackend:
    """The R.1 zero-legacy-call spy: records every legacy typing call. The bulk path must
    NEVER reach it — tests assert on the recorded lists."""

    def __init__(self) -> None:
        self.typed: list = []
        self.backspaces: list[int] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def press_backspace(self, n: int) -> None:
        self.backspaces.append(n)


class _BulkFakeFeedback:
    """Full recording Feedback double (the delivery surfaces included)."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []
        self.notifies: list[str] = []
        self.modes: list[str] = []
        self.finals: list[str] = []
        self.listening_states: list[bool] = []
        self.ducked_states: list[bool] = []
        self.delivery_modes: list[str] = []
        self.delivery_states: list[tuple[str, str]] = []  # (state, reason)
        self.confirmed_ops: list[str] = []
        self._state: dict = {
            "phase": "unloaded",
            "models_loaded": False,
            "partial": "",
            "last_final": "",
            "delivery_mode": "stream-edit",
            "delivery_state": "inactive",
            "delivery_reason": "",
            "last_confirmed_op": "",
        }

    def snapshot(self) -> dict:
        return dict(self._state)

    def update_partial(self, text: str) -> None:
        self.partials.append(text)
        self._state["partial"] = text

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)
        self._state["phase"] = phase

    def set_models_loaded(self, loaded: bool) -> None:
        self._state["models_loaded"] = bool(loaded)

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def notify(self, msg: str) -> None:
        self.notifies.append(msg)

    def set_ducked(self, ducked: bool) -> None:
        self.ducked_states.append(bool(ducked))

    def set_listening(self, listening: bool) -> None:
        self.listening_states.append(bool(listening))

    def record_final(self, text: str) -> None:
        self.finals.append(text)
        self._state["last_final"] = text
        self._state["partial"] = text

    def set_delivery_mode(self, mode: str) -> None:
        self.delivery_modes.append(mode)
        self._state["delivery_mode"] = mode

    def set_delivery_state(self, state: str, reason: str = "") -> None:
        self.delivery_states.append((state, reason))
        self._state["delivery_state"] = state
        self._state["delivery_reason"] = reason

    def record_confirmed_op(self, op: str) -> None:
        self.confirmed_ops.append(op)
        self._state["last_confirmed_op"] = op


class _FakeHost:
    """RecorderHost duck with a SETTABLE relay_identity (the T1.S1 seam). Mirrors the
    constructor signature the daemon's host_factory must accept."""

    def __init__(self, cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        self.cfg = cfg
        self.feedback = feedback
        self.latency = latency
        self.on_final = on_final
        self.on_partial = on_partial
        self.on_speech = on_speech
        self.relay_identity_value: "_Identity | None" = None
        self.spawn_calls = 0
        self.cancel_calls = 0
        self.mic: list[bool] = []
        self.aborts = 0
        self._cancel_mark = False
        self.device = {"device": "cuda", "compute_type": "float32", "model": "small.en"}

    def spawn(self, timeout: float = 180.0) -> bool:
        self.spawn_calls += 1
        return True

    @property
    def is_alive(self) -> bool:
        return True

    @property
    def pid(self):
        return None

    def set_microphone(self, on: bool) -> None:
        self.mic.append(on)

    def abort(self) -> None:
        self.aborts += 1

    def cancel(self) -> None:
        self.cancel_calls += 1

    def consume_cancel_mark(self) -> bool:
        marked = self._cancel_mark
        self._cancel_mark = False
        return marked

    def mark_cancel_sentinel(self) -> None:
        self._cancel_mark = True

    def relay_identity(self) -> "_Identity | None":
        return self.relay_identity_value

    def text(self, on_final) -> str:
        return ""

    def stop(self, timeout: float = 5.0) -> None:
        pass


class _FakeTarget:
    """DeliveryTarget duck (the G2FakeTarget shape, trimmed to what dispatch tests need):
    acquire → ok; show/finalize APPLIED (programmable refuse_after / raise_exc); cancel
    APPLIED when owned; leave recorded exactly-once evidence."""

    def __init__(self, *, acquire_ok: bool = True, acquire_reason: str = "no field",
                 refuse_after: "int | None" = None, raise_exc: "BaseException | None" = None):
        self.acquire_ok = acquire_ok
        self.acquire_reason = acquire_reason
        self.refuse_after = refuse_after
        self.raise_exc = raise_exc
        self.acquire_calls = 0
        self.leave_calls = 0
        self.begun: list[str] = []
        self.ops: list[tuple] = []

    def acquire(self) -> AcquireResult:
        self.acquire_calls += 1
        self.begun.append("acquire")
        if self.acquire_ok:
            return AcquireResult(ok=True, handle="fake", revision=0)
        return AcquireResult(ok=False, reason=self.acquire_reason)

    def _mutate(self, method: str, span):
        self.begun.append(method)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.refuse_after is not None and len(self.ops) >= self.refuse_after:
            result = ShowResult.REFUSED
        else:
            result = ShowResult.APPLIED
        self.ops.append((method, span, result))
        return result

    def show(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        return self._mutate("show", span)

    def finalize(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        return self._mutate("finalize", span)

    def cancel(self) -> ShowResult:
        self.begun.append("cancel")
        self.ops.append(("cancel", None, ShowResult.APPLIED))
        return ShowResult.APPLIED

    def leave(self) -> None:
        self.leave_calls += 1


class _FakeBundle:
    """The bulk_target_factory= test double: records attach/teardown; carries the target."""

    def __init__(self, target: _FakeTarget) -> None:
        self.target = target
        self.attached: list = []
        self.teardown_calls = 0

    def attach(self, controller) -> None:
        self.attached.append(controller)

    def teardown(self) -> None:
        self.teardown_calls += 1


class _FakeStream:
    """The zero-_stream-call spy: the bulk path must NEVER touch the streaming engine."""

    def __init__(self) -> None:
        self.partial_calls: list[str] = []
        self.commit_calls: list[str] = []
        self.freeze_calls: list[str] = []
        self.reset_calls = 0
        self.resume_calls = 0
        self.user_keypress_calls = 0

    def on_partial(self, text: str) -> None:
        self.partial_calls.append(text)

    def commit(self, text: str) -> None:
        self.commit_calls.append(text)

    def freeze(self, reason: str, session: bool = False) -> None:
        self.freeze_calls.append(reason)

    def reset_boundary(self) -> None:
        pass

    def reset_after_cancel(self) -> None:
        self.reset_calls += 1

    def reset_session(self) -> None:
        pass

    def resume(self) -> None:
        self.resume_calls += 1

    def pending_tail_len(self) -> int:
        return 0

    def arm_stray_echo_guard(self, text: str) -> None:
        pass

    def note_user_keypress(self) -> None:
        self.user_keypress_calls += 1


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def _bulk_cfg() -> "config_mod.VoiceTypingConfig":
    """The precondition triple satisfied at construction (streaming=True,
    graceful_stop=False, keypress_action='disarm' are the defaults)."""
    return config_mod.VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}})


def _make_bulk_daemon(
    *, cfg=None, factory=None, identity=None, factory_calls: "list | None" = None
):
    """A daemon wired for bulk dispatch tests: fake host (settable identity), spy backend,
    fake bundle factory, spy stream installed, real LatencyLog. No threads started."""
    cfg = cfg or _bulk_cfg()
    fb = _BulkFakeFeedback()
    be = _SpyBackend()
    host_holder: dict = {}

    def _host_factory(cfg_, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(cfg_, feedback, latency, on_final, on_partial, on_speech, **kw)
        host.relay_identity_value = identity
        host_holder["host"] = host
        return host

    if factory is None:
        if factory_calls is None:
            factory_calls = []

        def factory(cfg_):
            factory_calls.append(cfg_)
            return _FakeBundle(_FakeTarget())

    d = VoiceTypingDaemon(
        hermetic_cfg(cfg),  # P1.M1.T1.S2: duck off + private state (BUG-001)
        fb,
        recorder=None,
        host_factory=_host_factory,
        backend=be,
        mic_prober=lambda: (True, None),
        bulk_target_factory=factory,
    )
    assert d._load_host() is True
    d._stream = _FakeStream()  # the zero-_stream-call spy (legacy paths keep working)
    return d, fb, be, host_holder["host"]


def _wire_direct_ctrl(d, fb, target=None, gen: int = 1):
    """Deterministic dispatch setup: install a REAL BulkController over a fake target,
    acquired + armed, WITHOUT starting the writer or the arm thread (dispatch is driven by
    calling on_final/_on_partial directly + ctrl.drain())."""
    target = target or _FakeTarget()
    ctrl = BulkController(target, on_stopped=d._on_bulk_stopped,
                          on_applied=d._on_bulk_applied)
    assert ctrl.acquire() is True
    assert ctrl.arm(gen) is True
    d._bulk_ctrl = ctrl
    d._bulk_gen = gen
    d._bulk_bundle = _FakeBundle(target)
    d._listening.set()
    return ctrl, target


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    """Bounded poll (the G2 _wait_until idiom) — the lifecycle tests' only real waits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------------------------------------------------------------------------
# 1. default mode inert (the unit-level G1 parity pin)
# ---------------------------------------------------------------------------


def test_default_mode_is_fully_inert():
    """delivery='stream-edit' (default): on_final/_on_partial/cancel make ZERO ctrl/bundle
    calls — the factory is never invoked, the legacy paths behave exactly as before."""
    calls: list = []
    d, fb, be, host = _make_bulk_daemon(
        cfg=config_mod.VoiceTypingConfig(), factory_calls=calls
    )
    host.relay_identity_value = _Identity(1, 7)
    d._listening.set()
    d._text_in_flight.set()
    d._on_partial("hello")
    d.on_final("hello world")
    d.cancel()
    assert calls == [], "the bulk factory must never be invoked in the default mode"
    assert d._bulk_ctrl is None and d._bulk_bundle is None
    assert d._bulk_mode() is False
    # legacy behavior intact (spot pins — the G1 watch set owns the full baseline):
    assert be.typed == [] and be.backspaces == []
    assert d._stream.commit_calls == ["hello world"], "the legacy commit path ran verbatim"
    assert fb.delivery_modes == ["stream-edit"]  # boot write records the mode


# ---------------------------------------------------------------------------
# 2-6. dispatch branches
# ---------------------------------------------------------------------------


def test_bulk_accepted_final_routes_to_controller(caplog):
    """Accepted final -> ctrl.on_final(span, utterance='7', seq=1, gen=1) enqueued; drain
    dispatches ONE APPLIED show; record_final keeps recognition meaning; ZERO backend calls,
    ZERO stream commits; the log line carries counts only (no text=<repr>)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.on_final("hello world")
    assert ctrl.accepted_final() == "hello world"
    assert fb.finals == ["hello world"], "recognition meaning stays on the feedback mirror"
    assert be.typed == [] and be.backspaces == [], "the bulk path never types"
    assert d._stream.commit_calls == [] and d._stream.partial_calls == []
    assert [b for b in target.begun if b != "acquire"] == [], (
        "enqueue-and-return: nothing dispatched on the reader thread"
    )
    n = ctrl.drain()  # the deterministic dispatch seam (the G2 idiom)
    assert n == 2, "the arm's _SessionBegin barrier + the final"
    assert target.ops == [
        ("finalize", "hello world", ShowResult.APPLIED)
    ], "the FINAL dispatches finalize (one op, APPLIED)"
    bulk_lines = [r.getMessage() for r in caplog.records if "bulk final" in r.getMessage()]
    assert bulk_lines, "the bulk final log line must exist"
    assert all("text=" not in m for m in bulk_lines), "counts only — NEVER recognition text"
    assert re.search(
        r"gen=1 utt=7 seq=1 chars=11 queue=2 partials=\d+", bulk_lines[0]
    ), bulk_lines[0]


def test_bulk_rejected_final_boundary_closes_without_erase(caplog):
    """Rejected final (below min_chars) -> ctrl.on_final_dropped (boundary, NO target call,
    nothing auto-erased) + the legacy hallucination notify."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._cfg.filter.min_chars = 50
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.on_final("hi")
    assert ctrl.accepted_final() is None
    assert "filtered hallucination — not typed; keep dictating" in fb.notifies
    assert [b for b in target.begun if b != "acquire"] == [], (
        "a boundary closes the utterance with NO target call"
    )
    ctrl.drain()
    assert target.ops == [], "nothing auto-erased (R.3: a dropped final never touches the field)"
    assert d._stream.commit_calls == [] and d._stream.freeze_calls == []


def test_bulk_partial_seq_increments_and_new_gen_resets():
    """Partials -> ctrl.on_partial with daemon-synthesized seq (1,2,3...); a new gen lazily
    clears the map (fresh utterances start at seq 1); update_partial + note_partial fire;
    ZERO _stream calls."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    for text in ("a", "ab", "abc"):
        d._on_partial(text)
    assert d._bulk_seq == {(1, 7): 3}
    assert ctrl.latest_recognized() == "abc"
    host.relay_identity_value = _Identity(2, 7)
    d._on_partial("b")
    assert d._bulk_seq == {(2, 7): 1}, "the seq map is lazily cleared when gen advances"
    assert fb.partials[-1] == "b"
    assert d._stream.partial_calls == [], "the bulk path never routes partials through the engine"
    assert be.typed == []


def test_identity_missing_drops_and_counts_never_fallback():
    """relay_identity missing (legacy fake / id-less payload): drop + count — NEVER a
    constant-utterance fallback; the drain flags still clear (the machinery is
    delivery-agnostic); nothing recorded, nothing routed."""
    d, fb, be, host = _make_bulk_daemon(identity=None)
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._listening.set()
    d._final_pending = True
    d._utterance_finalized = False
    d.on_final("hello world")
    d._on_partial("hello")
    assert d._bulk_dropped_no_id == 2
    assert d._final_pending is False and d._utterance_finalized is True
    assert ctrl.latest_recognized() == "" and ctrl.accepted_final() is None
    assert fb.finals == [] and fb.partials == []
    assert [b for b in target.begun if b != "acquire"] == []


def test_bulk_cancel_opens_suppression_window_and_drops_racing_final():
    """The SHARED suppress latch: _bulk_cancel latches it; the racing final (with the marked
    sentinel) is dropped with NO ctrl call; the sentinel consume closes + re-arms; the NEXT
    final routes to the controller normally."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._text_in_flight.set()
    resp = d.cancel()
    assert resp["ok"] is True
    assert d._cancel_suppress_final is True
    host.mark_cancel_sentinel()
    host.relay_identity_value = _Identity(1, 8)
    d.on_final("racing final")
    assert ctrl.accepted_final() is None, "the cancelled utterance's final must be dropped"
    assert fb.finals == []
    assert d._cancel_suppress_final is False, "the sentinel consume closed + re-armed the window"
    d.on_final("next utterance")
    assert ctrl.accepted_final() == "next utterance", "the window re-armed for new speech"


# ---------------------------------------------------------------------------
# 7. the cancel intercept
# ---------------------------------------------------------------------------


def test_bulk_cancel_intercept_no_physical_compensation():
    """Bulk cancel: ctrl.cancel(gen) called (OUT of _lock), ZERO press_backspace (the legacy
    n=max(tail_len-1,0) math is UNREACHABLE), host.cancel + suppress latch shared, reply ok."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("hello worl")
    ctrl.drain()  # the controller now OWNS a shown range
    d._text_in_flight.set()
    resp = d.cancel()
    assert resp["ok"] is True and resp["listening"] is True
    assert be.backspaces == [] and be.typed == [], "ZERO physical-character compensation (R.1)"
    assert host.cancel_calls == 1, "the shared recognition cancel still runs"
    assert d._cancel_suppress_final is True
    cancel_ops = [op for op in target.ops if op[0] == "cancel"]
    assert len(cancel_ops) == 1, "ctrl.cancel removed the owned range in ONE op"
    assert d._stream.reset_calls == 1, "the partial-mirror clear still runs"


def test_bulk_cancel_idempotent_when_not_wired_or_disarmed():
    """Not wired (no ctrl) or disarmed: ok reply, no crash, no ctrl call, no host touch."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    d._listening.set()
    resp = d.cancel()  # bulk mode, listening, but ctrl is None (arm never ran)
    assert resp["ok"] is True and be.backspaces == []
    d._listening.clear()
    resp2 = d.cancel()
    assert resp2["ok"] is True
    assert host.cancel_calls == 0 and be.backspaces == []


def test_legacy_cancel_body_untouched_in_default_mode():
    """The legacy compensation math must still work in stream-edit mode (the intercept is
    ADDITIVE — insert, don't rewrite): tail_len=8 -> exactly one ('bs', 7)."""
    d, fb, be, host = _make_bulk_daemon(cfg=config_mod.VoiceTypingConfig())
    d._listening.set()
    d._text_in_flight.set()
    stream = _FakeStream()

    def _tail_len():
        return 8

    stream.pending_tail_len = _tail_len  # type: ignore[method-assign]
    d._stream = stream
    resp = d.cancel()
    assert resp["ok"] is True
    assert be.typed == [] and be.backspaces == [7], f"legacy math intact; got {be.typed!r}"


# ---------------------------------------------------------------------------
# 8-10. lifecycle: arm / disarm / fault / epoch guard
# ---------------------------------------------------------------------------


def test_arm_lifecycle_acquire_arm_start_order_and_active():
    """_arm -> vt-bulk-arm thread -> acquire, arm(gen), start -> feedback 'active'; gen
    parity (ctrl session_gen == daemon _bulk_gen)."""
    target = _FakeTarget()
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: _FakeBundle(target))
    d._arm()
    assert _wait_until(
        lambda: fb.delivery_states and fb.delivery_states[-1] == ("active", "")
    )
    ctrl = d._bulk_ctrl
    assert ctrl is not None and ctrl.is_active()
    assert target.acquire_calls == 1
    assert ctrl.stats()["session_gen"] == d._bulk_gen == 1
    assert ctrl._writer is not None, "start() launched the writer"
    assert d._bulk_delivery_active is True


def test_acquire_failure_unsupported_recording_stays_armed():
    """Acquire failure -> delivery_state='unsupported' + the target's reason; the MIC STAYS
    ARMED (R.5: delivery failure never kills recording)."""
    target = _FakeTarget(acquire_ok=False, acquire_reason="no editable field")
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: _FakeBundle(target))
    d._arm()
    assert _wait_until(
        lambda: fb.delivery_states
        and fb.delivery_states[-1] == ("unsupported", "no editable field")
    )
    assert d.is_listening() is True, "recording stays armed on acquire failure"
    assert d._bulk_delivery_active is False


def test_disarm_stopper_leave_exactly_once_and_no_late_flush():
    """Clean disarm -> the stopper runs ctrl.stop(leave=True) + teardown; leave() EXACTLY
    once; post-stop events are rejected (no late flush); state -> inactive."""
    target = _FakeTarget()
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: _FakeBundle(target),
                                        identity=_Identity(1, 7))
    d._arm()
    assert _wait_until(lambda: fb.delivery_states and fb.delivery_states[-1] == ("active", ""))
    fb.partials.clear()
    d._disarm()
    assert d._bulk_stop_thread is not None
    d._bulk_stop_thread.join(timeout=2.0)
    assert not d._bulk_stop_thread.is_alive()
    assert target.leave_calls == 1, "leave() exactly once (R.3)"
    assert fb.delivery_states[-1] == ("inactive", "")
    assert d._bulk_delivery_active is False
    d._on_partial("late stray")  # post-stop: the daemon gate drops it before any routing
    assert fb.partials == [], "no late flush after disarm"


def test_stopper_epoch_guard_skips_stale_teardown(monkeypatch):
    """G11: a stopper whose epoch was superseded by a newer arm must NOT touch the new
    delivery lifetime; a matching-epoch stopper tears down. Deterministic: the stopper body
    is run manually (no thread-timing race)."""
    import voice_typing.daemon as daemon_mod

    class _ManualThread:
        """start() is a no-op; run() executes the stopper body under the test's control."""

        def __init__(self, target=None, daemon=True, name=None):
            self._target = target
            self.daemon = daemon
            self.name = name

        def start(self):
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return False

        def run(self):
            self._target()

    monkeypatch.setattr(daemon_mod.threading, "Thread", _ManualThread)
    target = _FakeTarget()
    bundle = _FakeBundle(target)
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: bundle)
    d._bulk_ctrl = BulkController(target)  # wired directly: the stopper must find them
    d._bulk_bundle = bundle
    d._bulk_epoch = 10
    d._bulk_schedule_stop()  # captures epoch 10 (stored, NOT started)
    d._bulk_epoch = 11  # a newer arm superseded it
    d._bulk_stop_thread.run()
    assert target.leave_calls == 0 and bundle.teardown_calls == 0, "stale stop skipped"
    d._bulk_epoch = 10  # matching again
    d._bulk_schedule_stop()
    d._bulk_stop_thread.run()
    assert target.leave_calls == 1 and bundle.teardown_calls == 1


def test_quit_schedules_stopper_and_bounded_joins():
    """request_shutdown in bulk mode schedules + bounded-joins the stopper (quit never
    strands a live writer or IM child)."""
    target = _FakeTarget()
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: _FakeBundle(target))
    d._arm()
    assert _wait_until(lambda: fb.delivery_states and fb.delivery_states[-1] == ("active", ""))
    d.request_shutdown()
    assert _wait_until(lambda: target.leave_calls == 1, timeout=3.0), "stopper tore down"
    assert d._teardown_done.is_set()


def test_note_user_keypress_halt_disarms_bulk():
    """HALT semantics (keypress_action='disarm' — the bulk-mode REQUIRED value): a non-
    Backspace keypress past the grace window disarms; the stopper tears the delivery down."""
    target = _FakeTarget()
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: _FakeBundle(target))
    d._arm()
    assert _wait_until(lambda: fb.delivery_states and fb.delivery_states[-1] == ("active", ""))
    d._armed_monotonic = time.monotonic() - 10  # past the 1.5 s grace window
    d.note_user_keypress()
    assert _wait_until(lambda: not d.is_listening())
    assert d._bulk_stop_thread is not None
    d._bulk_stop_thread.join(timeout=2.0)
    assert target.leave_calls == 1


# ---------------------------------------------------------------------------
# 8b. the one-reason fault law (direct handler drive — every named reason)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    ["queue-overflow", "op-deadline", "refused", "unknown", "target-error", "takeover: key"],
)
def test_every_fault_reason_disarms_both_with_one_reason(reason):
    """Each fault-class reason -> delivery_state='fault' + THAT reason + listening False
    (both disarmed); the stopper (scheduled by _disarm) keeps the fault (flag cleared first,
    G7)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    _wire_direct_ctrl(d, fb)
    d._disarm()  # start from a clean state: not listening, stopper joined below
    if d._bulk_stop_thread is not None:
        d._bulk_stop_thread.join(timeout=2.0)
    fb.delivery_states.clear()
    d._listening.set()
    d._bulk_delivery_active = True
    d._on_bulk_stopped(reason)
    assert fb.delivery_states == [("fault", reason)], "ONE concise reason (R.5)"
    assert d.is_listening() is False, "recording disarmed too"
    if d._bulk_stop_thread is not None:
        d._bulk_stop_thread.join(timeout=2.0)
    assert fb.delivery_states == [("fault", reason)], "G7: the stopper never erases the fault"


def test_clean_stop_reason_writes_no_fault():
    """A clean 'stopped' on_stopped does NOT write fault (the disarm path owns the state)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    _wire_direct_ctrl(d, fb)
    d._on_bulk_stopped("stopped")
    assert all(state != "fault" for state, _ in fb.delivery_states)


def test_fault_refused_end_to_end_through_the_controller():
    """A REFUSED op through the REAL controller -> on_stopped('refused') -> fault + both
    disarmed (the wiring seam the ctor docstring names, driven end-to-end)."""
    target = _FakeTarget(refuse_after=0)  # every mutating op REFUSES
    d, fb, be, host = _make_bulk_daemon(factory=lambda cfg_: _FakeBundle(target),
                                        identity=_Identity(1, 7))
    d._arm()
    assert _wait_until(lambda: fb.delivery_states and fb.delivery_states[-1] == ("active", ""))
    d._on_partial("hello")  # the live writer dispatches it -> REFUSED -> on_stopped
    assert _wait_until(lambda: fb.delivery_states and fb.delivery_states[-1] == ("fault", "refused"))
    assert _wait_until(lambda: not d.is_listening())
    assert d._bulk_delivery_active is False


# ---------------------------------------------------------------------------
# 11. the on_applied hook -> record_confirmed_op
# ---------------------------------------------------------------------------


def test_on_applied_descriptor_counts_and_times_only():
    """FakeTarget APPLIED -> the descriptor matches the feedback contract format:
    'insert utt=U seq=S rev=R +Nch Xms' — counts + times, never recognition text."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("hello worl")
    ctrl.drain()  # _SessionBegin + the partial (show dispatches, APPLIED)
    assert fb.confirmed_ops, "the hook recorded the APPLIED op"
    op = fb.confirmed_ops[0]
    assert re.fullmatch(r"insert utt=7 seq=1 rev=0 \+10ch \d+ms", op), op
    assert "hello" not in op and "worl" not in op, "counts + times ONLY (R.5)"
    assert fb.snapshot()["last_confirmed_op"] == op


def test_on_applied_cancel_descriptor_negative_chars():
    """An APPLIED cancel fires the hook with kind='cancel' and NEGATIVE chars (the removed
    owned-range size)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("hello worl")
    ctrl.drain()  # own a 11-char span
    fb.confirmed_ops.clear()
    assert ctrl.cancel(gen=d._bulk_gen) is True
    assert fb.confirmed_ops, "the APPLIED cancel fired the hook"
    assert re.fullmatch(
        r"cancel utt=7 seq=1 rev=1 -10ch \d+ms", fb.confirmed_ops[0]
    ), fb.confirmed_ops


# ---------------------------------------------------------------------------
# boot surface
# ---------------------------------------------------------------------------


def test_boot_writes_delivery_mode_from_config():
    """The boot set_delivery_mode call carries the CONFIG value (the landed surface's only
    writer is this wiring)."""
    d, fb, be, host = _make_bulk_daemon()
    assert fb.delivery_modes == ["bulk-text"]
    d2, fb2, _, _ = _make_bulk_daemon(cfg=config_mod.VoiceTypingConfig())
    assert fb2.delivery_modes == ["stream-edit"]


def test_bulk_wired_gate():
    """_bulk_mode vs _bulk_wired: mode is the config check; wired adds a live controller."""
    d, fb, be, host = _make_bulk_daemon()
    assert d._bulk_mode() is True and d._bulk_wired() is False
    _wire_direct_ctrl(d, fb)
    assert d._bulk_wired() is True
