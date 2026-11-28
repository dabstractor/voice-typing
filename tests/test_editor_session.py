"""P1.M1.T3.S4 — native owner reservation + startup fence (PRD §4.8.1 B).
NO live socket listener, NO CUDA, NO daemon run(). Fake clock + manual timers + Event barriers; no sleeps."""
import sys, threading, dataclasses
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent))          # tests/ has no __init__.py; pytest prepend mode
import test_daemon as td                                # _make_daemon, _fake_host_factory, _wait_for
from voice_typing import daemon
from voice_typing.editor_session import (Stage, Owner, EndRecord, NativeReservation, NativeReserveResult)
from voice_typing.editor_protocol import START_CAP_S, ThreadTimers


class FakeClock:
    def __init__(self, t=1000.0): self.t = t
    def now(self): return self.t
    def advance(self, s): self.t += s


class ManualTimers:                                      # S3's test convention: arm records, fire is explicit
    def __init__(self): self.armed, self.fired, self.cancelled = [], [], []
    def arm(self, deadline, fire):
        h = object(); self.armed.append((h, deadline, fire)); return h
    def cancel(self, h): self.cancelled.append(h)
    def fire(self, h):
        for hh, d, f in self.armed:
            if hh is h: self.fired.append(h); f()


def _gated_host_factory(entered, gate, mic_log):
    """Wraps td._fake_host_factory(): spawn blocks on `gate`; set_microphone calls are logged with the
    daemon's native stage at call time (proves the commit is atomic with capture)."""
    inner = td._fake_host_factory()
    def factory(*a, **k):
        host = inner(*a, **k)
        orig_spawn, orig_mic = host.spawn, host.set_microphone
        def spawn(timeout=180.0):
            entered.set(); gate.wait(5.0); return orig_spawn(timeout)
        def set_microphone(on):
            mic_log.append((bool(on), factory.daemon._native.stage if factory.daemon._native else None))
            orig_mic(on)
        host.spawn, host.set_microphone = spawn, set_microphone
        return host
    factory.daemon = None
    return factory


def _native_daemon(*, gate=None, entered=None, mic_log=None, prime=None):
    """A hermetic LAZY daemon with injected clock/timers and (optionally) a gated spawn.

    Lazy (td._make_lazy_daemon, the established pattern) is REQUIRED: _make_daemon injects a
    legacy _StubRecorder, which boots the daemon WARM (_models_loaded=True) so _load_host
    short-circuits and host_factory is never consulted. The ungated path STILL goes through
    _gated_host_factory (with an already-set gate) so set_microphone calls are logged into
    mic_log — the commit-atomicity tests assert on mic_log in both paths."""
    mic_log = mic_log if mic_log is not None else []
    _gate = gate if gate is not None else threading.Event()
    _gate.set()                                          # ungated: spawn proceeds immediately
    _entered = entered if entered is not None else threading.Event()
    f = _gated_host_factory(_entered, _gate, mic_log)
    d, _fb = td._make_lazy_daemon(host_factory=f); f.daemon = d
    fc, mt = FakeClock(), ManualTimers()
    d._native_clock, d._native_timers = fc.now, mt
    return d, fc, mt, mic_log, None


class _Ends:                                             # on_end collector with an optional hook
    def __init__(self, hook=None): self.records, self.hook, self.lock = [], hook, threading.Lock()
    def __call__(self, rec):
        with self.lock: self.records.append(rec)
        if self.hook: self.hook(rec)


ID = "123e4567-e89b-42d3-a456-426614174000"     # a valid UUIDv4 (S2 vectors use this one)
ID2 = "123e4567-e89b-42d3-a456-426614174001"


# ---- A. pure state machine (editor_session.NativeReservation) ----
def test_reservation_stage_machine_fake_clock():
    fc = FakeClock(); r = NativeReservation(Owner(ID, 1, fc.now(), fc.now() + START_CAP_S), object(), now=fc.now())
    assert r.stage is Stage.STARTING and r.live and r.can_commit(1, fc.now()) and not r.can_commit(2, fc.now())
    assert not r.begin_drain("stopped")                       # not listening yet
    assert r.commit(1) and r.stage is Stage.LISTENING and not r.commit(1)
    assert r.begin_drain("idle") and r.stage is Stage.DRAINING and r.end_reason == "idle"
    rec = r.terminate("idle", None, now=fc.now())
    assert isinstance(rec, EndRecord) and rec.stage is Stage.DRAINING and r.stage is Stage.ENDED
    assert not r.live and r.tombstoned(1) and r.terminate("stopped", None, now=fc.now()) is None


def test_reservation_cap_boundary_is_exclusive():
    fc = FakeClock(); dl = fc.now() + START_CAP_S
    r = NativeReservation(Owner(ID, 1, fc.now(), dl), object(), now=fc.now())
    assert r.can_commit(1, dl - 0.001) and not r.can_commit(1, dl)   # at the deadline the cap has passed


def test_end_record_fields_are_codes_only():
    names = {f.name for f in dataclasses.fields(EndRecord)}
    assert names == {"owner", "stage", "reason", "cause", "ended_at"}
    r = NativeReservation(Owner(ID, 1, 0.0, 1.0), object(), now=0.0)
    with pytest.raises(ValueError): r.terminate("not-a-code", None, now=0.0)
    assert r.live                                           # an unknown reason did not end it


# ---- B. atomic check-and-reserve ----
def test_reserve_native_accepts_and_arms_one_timer():
    d, fc, mt, _, _ = _native_daemon()
    res = d.reserve_native(object(), ID, on_end=_Ends())
    assert res.accepted and res.error is None and res.owner.token == 1 and res.owner.id == ID
    assert res.owner.deadline == fc.now() + START_CAP_S and d._native.stage is Stage.STARTING
    assert d.native_id_known(ID) and len(mt.armed) == 1 and mt.armed[0][1] == res.owner.deadline
    assert d._arming is None and d._arm_seq == 0 and not d._listening.is_set()   # nothing armed


def test_reserve_native_rejections_reserve_nothing():
    d, fc, mt, _, _ = _native_daemon()
    assert d.reserve_native(object(), "nope") == NativeReserveResult(False, None, "invalid_request")
    assert d._native is None and not mt.armed
    d._shutdown.set(); assert d.reserve_native(object(), ID).error == "busy"; d._shutdown.clear()
    for flag in ("_arming", "_loading", "_drain"):
        setattr(d, flag, 2 if flag == "_arming" else True)
        assert d.reserve_native(object(), ID).error == "busy" and d._native is None and d._arm_seq == 0
        setattr(d, flag, None if flag == "_arming" else False)
    d._listening.set(); assert d.reserve_native(object(), ID).error == "busy"; d._listening.clear()
    assert not mt.armed


def test_second_native_owner_and_duplicate_id_are_busy():
    d, fc, mt, _, _ = _native_daemon(); ends = _Ends()
    assert d.reserve_native(object(), ID, on_end=ends).accepted
    assert d.reserve_native(object(), ID2).error == "busy"             # one owner at a time
    d.terminate_native("stopped", cause="test", token=1)
    assert len(ends.records) == 1
    assert d.reserve_native(object(), ID).error == "duplicate_id"      # ended ids stay retained
    res = d.reserve_native(object(), ID2); assert res.accepted and res.owner.token == 2


# ---- C. symmetric busy: generic/context arms never supersede or join ----
def test_generic_arms_are_busy_under_native_owner_and_reserve_nothing():
    d, fc, mt, _, _ = _native_daemon(); d.reserve_native(object(), ID)
    seq0 = d._arm_seq
    assert d.start().reason == "busy" and d.toggle().reason == "busy"
    assert d.start_with_seed("seed text").reason == "busy"
    reply = d.start_context("seed text")
    assert reply["ok"] is False and "busy" in reply["error"] and reply["context_seeded"] is False
    assert d._arm_seq == seq0 and d._arming is None and d._native.stage is Stage.STARTING


def test_dispatch_maps_native_busy_for_toggle_and_start():
    d, fc, mt, _, _ = _native_daemon(); d.reserve_native(object(), ID)
    srv = daemon.ControlServer(d, socket_path="/nonexistent/s4.sock")   # never started: _dispatch only
    for cmd in ('{"cmd":"toggle"}', '{"cmd":"start"}', '{"cmd":"start-block"}', '{"cmd":"start-stream"}',
                '{"cmd":"toggle-stream"}', '{"cmd":"toggle-block"}'):
        r = srv._dispatch(cmd)
        assert r["ok"] is False and r["busy"] is True and "native" in r["error"], cmd
    assert srv._dispatch('{"cmd":"status"}')["ok"] is True                 # status stays usable


def test_cancel_is_busy_without_side_effects_under_native_owner():
    d, fc, mt, _, rec = _native_daemon(); d.reserve_native(object(), ID)
    r = d.cancel()
    assert r["ok"] is False and r["busy"] is True and "native" in r["error"]


# ---- D. the startup fence (worker blocked in spawn = the cold-load barrier) ----
def _start_blocked(d, **kw):
    gate, entered = threading.Event(), threading.Event()
    f = _gated_host_factory(entered, gate, []); f.daemon = d
    d._host_factory = f                                       # the lazy loader picks the gated factory
    res = d.reserve_native(object(), ID, on_end=_Ends()); assert res.accepted
    assert d.begin_native_start(res.owner.token, **kw) is True
    assert td._wait_for(entered.is_set)                       # worker is inside spawn, no lock held
    return gate, res


def test_status_and_stop_stay_responsive_during_blocked_load():
    d, fc, mt, mic, _ = _native_daemon(); gate, res = _start_blocked(d)
    out = {}
    t = threading.Thread(target=lambda: out.update(snap=d.status_snapshot(), stopped=d.stop()))
    t.start(); t.join(timeout=1.0)
    assert not t.is_alive() and "listening" in out["snap"]     # both returned while spawn was blocked
    assert d._native.stage is Stage.ENDED and d._native.end.reason == "stopped"
    assert d._native.end.cause == "stop-during-start"
    gate.set(); d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and d._arming is None and not d._listening.is_set()
    assert all(not on for on, _ in mic)                       # capture never opened


def test_stop_during_startup_delivers_end_once_before_worker_returns():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate = threading.Event(); entered = threading.Event()
    f = _gated_host_factory(entered, gate, mic); f.daemon = d; d._host_factory = f
    res = d.reserve_native(object(), ID, on_end=ends); assert d.begin_native_start(res.owner.token)
    assert td._wait_for(entered.is_set)
    assert d.stop() is None and len(ends.records) == 1        # delivered NOW, not after the load
    assert ends.records[0].stage is Stage.STARTING and mt.cancelled                 # watchdog retired
    gate.set(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and all(not on for on, _ in mic)


def test_start_cap_timer_ends_reservation_as_timeout():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d); d._native_end_cb = ends
    fc.advance(START_CAP_S + 0.001); mt.fire(mt.armed[0][0])
    assert len(ends.records) == 1 and ends.records[0].reason == "timeout" and ends.records[0].cause == "start-cap"
    gate.set(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and all(not on for on, _ in mic) and d._arming is None


def test_late_commit_after_cap_is_refused_host_left_idle():
    """Timer NEVER fires; the worker returns from spawn after the deadline → the commit block itself
    ends the reservation ('timeout') and aborts; host stays resident+idle; seed cleaned by _abort_start."""
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d, seed="seed text")
    d._native_end_cb = ends
    fc.advance(START_CAP_S + 1.0); gate.set(); d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and len(ends.records) == 1
    assert ends.records[0].reason == "timeout" and all(not on for on, _ in mic)
    assert d._host is not None and d._arming is None and d._seed_active is False and d._listening.is_set() is False


def test_early_or_stale_timer_fire_is_ignored():
    d, fc, mt, _, _ = _native_daemon(); gate, res = _start_blocked(d); ends = _Ends(); d._native_end_cb = ends
    mt.fire(mt.armed[0][0])                                   # clock NOT advanced → early fire
    assert d._native.stage is Stage.STARTING and not ends.records
    gate.set(); d.stop(); assert d._native.end.reason == "stopped"


# ---- E. commit is atomic with capture; end paths ----
def test_commit_hook_flips_stage_in_same_lock_hold_as_mic_open():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    assert d.begin_native_start(res.owner.token) is True
    d._native_worker.join(timeout=10.0)                       # warm fake host: load + arm complete
    assert d._native.stage is Stage.LISTENING and d._listening.is_set()
    assert mic and mic[0] == (True, Stage.LISTENING)          # stage already LISTENING when the mic opened
    assert len(mt.cancelled) == 1 and not ends.records and d._arming is None
    assert d._native_worker.is_alive()                        # parked for the owner's lifetime (CRITICAL #6)
    d.terminate_native("stopped", token=res.owner.token)      # end it → the parked worker wakes + exits
    d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and len(ends.records) == 1


def test_disarm_ends_listening_owner_with_drain_reason_via_parked_worker():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    d.begin_native_start(res.owner.token); d._native_worker.join(timeout=10.0)
    d.stop()                                                  # _request_stop tags 'stopped' → _disarm stashes
    d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and len(ends.records) == 1
    assert ends.records[0].stage is Stage.DRAINING and ends.records[0].reason == "stopped"
    assert d._native.stage is Stage.ENDED and not d._listening.is_set()


def test_idle_auto_stop_path_records_idle_reason():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    d.begin_native_start(res.owner.token); d._native_worker.join(timeout=10.0)
    d._native_drain_or_stop("idle"); d.stop(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and ends.records[0].reason == "idle"


def test_host_death_and_shutdown_end_the_reservation():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    d.begin_native_start(res.owner.token); d._native_worker.join(timeout=10.0)
    d._handle_dead_host()
    assert len(ends.records) == 1 and ends.records[0].reason == "disconnected" and ends.records[0].cause == "host-died"
    res2 = d.reserve_native(object(), ID2, on_end=ends)       # STARTING owner, no worker
    d.request_shutdown()
    assert [r.reason for r in ends.records] == ["disconnected", "shutdown"] and d._native.stage is Stage.ENDED


# ---- F. exactly-once, off-lock delivery ----
def test_three_way_race_delivers_exactly_once():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d); d._native_end_cb = ends
    fc.advance(START_CAP_S + 1.0)
    ts = [threading.Thread(target=f) for f in (
        lambda: d.stop(), lambda: mt.fire(mt.armed[0][0]), lambda: d.terminate_native("disconnected", token=1))]
    [t.start() for t in ts]; [t.join(timeout=5.0) for t in ts]
    assert len(ends.records) == 1 and ends.records[0].reason in ("stopped", "timeout", "disconnected")
    gate.set(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and all(not on for on, _ in mic)


def test_end_callback_runs_off_lock_and_exceptions_are_swallowed(caplog):
    import logging
    d, fc, mt, _, _ = _native_daemon(); res = d.reserve_native(object(), ID)
    seen = []
    def hook(rec): seen.append(d.status_snapshot())            # takes _lock → would deadlock under it
    d._native_end_cb = hook; d.terminate_native("stopped", token=1); assert len(seen) == 1
    d.reserve_native(object(), ID2)
    def boom(rec): raise RuntimeError("secret seed text must not leak")
    d._native_end_cb = boom
    with caplog.at_level(logging.WARNING):
        d.terminate_native("shutdown", token=2)
    assert d._native.stage is Stage.ENDED and "secret" not in caplog.text
    assert "RuntimeError" in caplog.text                     # type name only


def test_no_text_leaks_in_logs_or_records(caplog):
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d, seed="SEED-DO-NOT-LOG")
    d._native_end_cb = ends
    import logging
    with caplog.at_level(logging.DEBUG):
        fc.advance(START_CAP_S + 1.0); gate.set(); d._native_worker.join(timeout=5.0)
        d.start_context("CTX-DO-NOT-LOG")
    blob = caplog.text + repr(ends.records) + repr(d.status_snapshot())
    assert "SEED-DO-NOT-LOG" not in blob and "CTX-DO-NOT-LOG" not in blob


def test_scope_and_existing_behavior_without_native_owner():
    d, fc, mt, mic, _ = _native_daemon()                       # no reservation: legacy paths untouched
    d.start(); assert d._listening.is_set() and mic[-1][0] is True and mic[-1][1] is None
    d.stop(); assert not d._listening.is_set()
    assert d.cancel()["ok"] is True and d._native is None
