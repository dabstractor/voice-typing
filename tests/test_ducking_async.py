"""Unit tests for voice_typing.ducking_async (PRD §4.2quinquies — failure discipline, D1).

Pure-Python, NO subprocess, NO daemon, NO CUDA, NO tier imports:
  - AsyncDucker is exercised over S1's REAL AudioDucker wrapping an in-process
    _FakeBackend (mutating players/volume + a `slow` map that sleeps BEFORE
    answering — the mocked backend hang of PRD test case (d)).
  - every timing assert uses a generous bound (caller-return < 0.5 s, flush-hung
    < 2.5 s) and _wait_until polling with a deadline — never a bare sleep.

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_ducking_async.py -v

Covers: PRD case (d) hung-backend promptness (engage + release), case (e)
idempotence (mpris one pause round / volume one set / release-without-engage
zero calls), latest-wins ordering (E-R-E ends engaged / E-R-R ends released),
never-a-gate swallowing on an all-failing backend, off-mode zero backend calls,
bounded flush (True fast when drained / False within bound when hung), and the
worker thread shape (exactly one daemon "vt-ducking" thread while busy; gone
after drain).
"""
from __future__ import annotations

import logging
import threading
import time

from voice_typing.audio_ducking import AudioDucker, PlayerState
from voice_typing.ducking_async import AsyncDucker


class _FakeBackend:
    """S1's mutating fake (tests/test_ducking.py) + a `slow` hung-backend seam.

    `slow` maps method name -> seconds to sleep BEFORE answering (case d: the
    mocked 5 s backend hang that violates the tiers' own <=1 s contract). All
    other behavior mirrors S1's: pause/resume MUTATE player state,
    set_sink_volume_pct stores the value, `fail` names methods that raise.
    """

    def __init__(self, players=(), volume=50.0, fail=(), slow=None):
        self.players = list(players)
        self.volume = volume
        self.fail = set(fail)
        self.slow = dict(slow or {})
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.set_calls: list[float] = []
        self.call_log: list[str] = []

    def _enter(self, method: str) -> None:
        self.call_log.append(method)
        if method in self.slow:
            time.sleep(self.slow[method])
        if method in self.fail:
            raise RuntimeError(f"{method} failed (simulated)")

    def list_players(self):
        self._enter("list_players")
        return list(self.players)

    def pause_player(self, name: str) -> bool:
        self._enter("pause_player")
        self.paused.append(name)
        self._set_playing(name, False)
        return True

    def resume_player(self, name: str) -> bool:
        self._enter("resume_player")
        self.resumed.append(name)
        self._set_playing(name, True)
        return True

    def get_sink_volume_pct(self):
        self._enter("get_sink_volume_pct")
        return self.volume

    def set_sink_volume_pct(self, pct: float) -> bool:
        self._enter("set_sink_volume_pct")
        self.set_calls.append(float(pct))
        self.volume = float(pct)
        return True

    def _set_playing(self, name: str, playing: bool) -> None:
        for i, p in enumerate(self.players):
            if p.name == name:
                self.players[i] = PlayerState(p.name, playing)
                return


class _Boom:
    """A duck-typed ducker double that raises from EVERY member — the wrapper
    must absorb it all (never a gate)."""

    @property
    def engaged(self):
        raise RuntimeError("boom")

    def engage(self):
        raise RuntimeError("boom")

    def release(self):
        raise RuntimeError("boom")


def _wait_until(pred, timeout=5.0, interval=0.02):
    """Poll pred until true or the deadline; mirrors tests/test_daemon.py's _wait_for."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return pred()


def _vt_threads():
    return [t for t in threading.enumerate() if t.name == "vt-ducking"]


# --- 1. Case (d): a hung backend never delays the caller ---

def test_engage_returns_promptly_with_hung_backend():
    b = _FakeBackend(volume=50.0, slow={"get_sink_volume_pct": 5.0})
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    t0 = time.monotonic()
    d.engage()  # backend hangs 5 s — the arm must not wait for it
    dt = time.monotonic() - t0
    assert dt < 0.5, f"engage blocked the caller {dt:.2f}s — ducking became a gate"
    assert d.flush(timeout=8.0) is True  # hung call still applied, eventually
    assert b.set_calls == [15.0]


def test_release_returns_promptly_with_hung_backend():
    b = _FakeBackend(volume=50.0)
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    d.engage()
    assert d.flush(timeout=5.0) is True
    assert b.volume == 15.0  # ducked
    b.slow = {"get_sink_volume_pct": 5.0}  # hang the release's re-read
    t0 = time.monotonic()
    d.release()
    dt = time.monotonic() - t0
    assert dt < 0.5, f"release blocked the caller {dt:.2f}s — ducking became a gate"
    assert d.flush(timeout=8.0) is True
    assert b.volume == 50.0  # restore applied eventually


# --- 2. Case (e): repeated arms coalesce to ONE backend application ---

def test_repeated_arms_pause_mpris_round_once():
    b = _FakeBackend(
        [PlayerState("A", True), PlayerState("B", False), PlayerState("C", True)],
        slow={"list_players": 0.25},  # worker busy while the 2nd/3rd arm arrives
    )
    d = AsyncDucker(AudioDucker(b, mode="mpris"))
    d.engage()
    d.engage()
    d.engage()
    assert d.flush(timeout=8.0) is True
    assert b.paused == ["A", "C"]  # exactly ONE pause per playing player
    assert b.call_log.count("pause_player") == 2
    assert b.call_log.count("list_players") == 1  # no second round for coalesced arms
    assert d.engaged is True
    d.release()
    assert d.flush(timeout=5.0) is True


def test_repeated_arms_set_volume_once():
    b = _FakeBackend(volume=50.0, slow={"get_sink_volume_pct": 0.25})
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    d.engage()
    d.engage()
    d.engage()
    assert d.flush(timeout=8.0) is True
    assert b.set_calls == [15.0]  # ONE set — no stacked volume writes
    assert d.engaged is True
    d.release()
    assert d.flush(timeout=5.0) is True


def test_release_without_engage_is_full_noop():
    b = _FakeBackend([PlayerState("A", True)], volume=50.0)
    d = AsyncDucker(AudioDucker(b, mode="mpris"))
    d.release()
    assert d.flush(timeout=5.0) is True
    assert b.call_log == []  # ZERO backend calls
    assert d.engaged is False


# --- 3. Ordering: the LAST request wins ---

def test_arm_disarm_arm_latest_state_wins():
    # E→R→E: ends ENGAGED at duck volume; no stale restore after the final arm.
    b = _FakeBackend(volume=50.0, slow={"get_sink_volume_pct": 0.3})
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    d.engage()
    d.release()
    d.engage()
    assert d.flush(timeout=10.0) is True
    assert d.engaged is True
    assert b.volume == 15.0
    assert b.set_calls[-1] == 15.0

    # E→R→R on a fresh session: ends RELEASED, volume restored.
    b2 = _FakeBackend(volume=50.0, slow={"get_sink_volume_pct": 0.3})
    d2 = AsyncDucker(AudioDucker(b2, mode="volume", volume_pct=15))
    d2.engage()
    d2.release()
    d2.release()
    assert d2.flush(timeout=10.0) is True
    assert d2.engaged is False
    assert b2.volume == 50.0
    assert b2.set_calls[-1] == 50.0


# --- 4. Never a gate: failures are swallowed, one line each ---

def test_dispatch_never_raises_on_failing_backend(caplog):
    b = _FakeBackend(
        volume=50.0,
        fail={"list_players", "pause_player", "resume_player",
              "get_sink_volume_pct", "set_sink_volume_pct"},
    )
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    d.engage()  # must not raise
    d.release()  # must not raise
    assert d.flush(timeout=5.0) is True

    # Even a ducker that raises from EVERY member is absorbed by the wrapper.
    d2 = AsyncDucker(_Boom())
    d2.engage()
    d2.release()
    assert d2.flush(timeout=5.0) is True
    assert d2.engaged is False  # swallow-wrapped proxy

    # Nothing above WARNING ever propagates; the wrapper warns once per path.
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    wrapper_warns = [r for r in caplog.records if r.name == "voice_typing.ducking_async"]
    assert len(wrapper_warns) == 3  # one per failure path: engage, release, engaged read


# --- 5. Off mode: duck_mode="off" touches nothing, end to end ---

def test_off_mode_makes_zero_backend_calls():
    b = _FakeBackend([PlayerState("A", True)], volume=50.0)
    d = AsyncDucker(AudioDucker(b, mode="off"))
    d.engage()
    d.release()
    assert d.flush(timeout=5.0) is True
    assert b.call_log == []
    assert d.engaged is False


# --- 6. flush: bounded both ways (True fast drained / False within bound hung) ---

def test_flush_is_bounded_drained_and_hung():
    b = _FakeBackend(volume=50.0)
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    assert d.flush(timeout=1.0) is True  # idle: True immediately
    d.engage()
    assert d.flush(timeout=5.0) is True
    assert b.volume == 15.0

    # A fresh session over a hung backend: flush must give up within its bound.
    b.slow = {"get_sink_volume_pct": 5.0}
    d2 = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    d2.engage()
    t0 = time.monotonic()
    result = d2.flush(timeout=1.0)
    elapsed = time.monotonic() - t0
    assert result is False
    assert elapsed < 2.5, f"flush hung {elapsed:.2f}s — not bounded"
    assert d2.flush(timeout=8.0) is True  # eventually drained for cleanliness


# --- 7. Worker thread shape: single, daemon, named, short-lived ---

def test_worker_thread_shape_single_daemon_and_short_lived():
    b = _FakeBackend(volume=50.0, slow={"get_sink_volume_pct": 0.5})
    d = AsyncDucker(AudioDucker(b, mode="volume", volume_pct=15))
    d.engage()
    assert _wait_until(lambda: len(_vt_threads()) == 1, timeout=5.0)
    assert _vt_threads()[0].daemon is True
    d.engage()
    d.engage()  # extra arms while busy: still exactly ONE worker
    assert len(_vt_threads()) == 1
    assert d.flush(timeout=8.0) is True
    assert _wait_until(lambda: not _vt_threads(), timeout=5.0)  # short-lived: gone
    assert b.set_calls == [15.0]
