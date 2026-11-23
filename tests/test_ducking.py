"""Unit tests for voice_typing.audio_ducking (PRD §4.2quinquies — media ducking core, D1).

Pure-Python, NO subprocess, NO daemon, NO CUDA, NO PipeWire:
  - the DuckBackend protocol is exercised through an in-process _FakeBackend that
    records every call and FLIPS PLAYER STATE on pause/resume (so the sovereignty
    rules are asserted against real state transitions, not a log alone).
  - user sovereignty is proven behaviorally: a player the USER resumed stays playing,
    a player the USER paused themselves is never touched, and a user-changed volume
    is never overwritten (compare-before-restore).
  - failure discipline is proven with a backend that raises: exactly ONE warning per
    failure, nothing ever propagates out of engage()/release().

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_ducking.py -v

Covers: only-Playing ledger fill (rules a+b), resume-only-still-Paused (rule c),
player-gone skip, volume snapshot/duck/compare-before-restore, double-engage
idempotence, release-without-engage no-op, off-mode zero backend calls, exception
swallowing, volume read failure leaving no snapshot, and from_config wiring.
"""
from __future__ import annotations

import logging

import pytest

from voice_typing.audio_ducking import AudioDucker, PlayerState


class _FakeBackend:
    """In-process DuckBackend double: records every call, flips player/volume state.

    CRITICAL: pause_player/resume_player MUTATE self.players (a log-only fake would
    leave players `Playing`, so rule (c) would correctly skip every resume);
    set_sink_volume_pct stores the value so release's compare-before-restore reads it.
    `fail` names methods that RAISE (simulating a misbehaving subprocess backend).
    """

    def __init__(self, players=(), volume=50.0, fail=()):
        self.players = list(players)
        self.volume = volume
        self.fail = set(fail)
        self.paused: list[str] = []
        self.resumed: list[str] = []
        self.set_calls: list[float] = []
        self.call_log: list[str] = []

    def _enter(self, method: str) -> None:
        self.call_log.append(method)
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

    # --- test helpers: simulate the USER (not the ducker) changing state ---

    def user_sets_playing(self, name: str, playing: bool) -> None:
        self._set_playing(name, playing)

    def user_sets_volume(self, pct: float) -> None:
        self.volume = float(pct)


# --- 1. MPRIS tier: ledger fill (rules a+b) ---

def test_engage_mpris_pauses_only_playing_players():
    b = _FakeBackend([PlayerState("A", True), PlayerState("B", False)])
    d = AudioDucker(b, mode="mpris")
    d.engage()
    assert b.paused == ["A"]          # only the `Playing` player was paused
    assert b.paused != ["A", "B"]
    assert d.engaged is True
    d.release()
    assert b.resumed == ["A"]         # ledger behavior: exactly what WE got paused
    assert "B" not in b.resumed


def test_release_resumes_only_we_paused_and_still_paused():
    b = _FakeBackend([PlayerState("A", True), PlayerState("B", False), PlayerState("C", True)])
    d = AudioDucker(b, mode="mpris")
    d.engage()                        # pauses A and C (B was already paused)
    assert b.paused == ["A", "C"]
    # mid-dictation the USER: resumed A themselves, paused B themselves
    b.user_sets_playing("A", True)
    b.user_sets_playing("B", False)
    d.release()
    assert b.resumed == ["C"]         # rule (c): A is Playing again — never fight the user
    assert "A" not in b.resumed and "B" not in b.resumed


def test_release_player_gone_is_skipped():
    b = _FakeBackend([PlayerState("A", True)])
    d = AudioDucker(b, mode="mpris")
    d.engage()
    b.players = []                    # player quit while we were listening
    d.release()                       # must not raise, must not resume a ghost
    assert b.resumed == []


# --- 2. Volume tier: snapshot / duck / compare-before-restore ---

def test_volume_engage_snapshots_and_ducks():
    b = _FakeBackend(volume=50.0)
    d = AudioDucker(b, mode="volume", volume_pct=15)
    d.engage()
    assert b.set_calls == [15.0]
    assert d.engaged is True


def test_volume_release_restores_when_untouched():
    b = _FakeBackend(volume=50.0)
    d = AudioDucker(b, mode="volume", volume_pct=15)
    d.engage()
    d.release()                       # user never touched volume → restore the snapshot
    assert b.set_calls == [15.0, 50.0]
    assert b.volume == 50.0


def test_volume_release_skips_restore_when_user_changed(caplog):
    b = _FakeBackend(volume=50.0)
    d = AudioDucker(b, mode="volume", volume_pct=15)
    d.engage()
    b.user_sets_volume(80)            # the USER raised the volume mid-dictation
    with caplog.at_level(logging.INFO):
        d.release()
    assert b.set_calls == [15.0]      # NO restore write — their value wins
    assert b.volume == 80.0
    keeping = [r for r in caplog.records if "keeping user value" in r.getMessage()]
    assert len(keeping) == 1
    assert keeping[0].levelno == logging.INFO


# --- 3. Idempotence + no-op gates ---

def test_engage_idempotent_double_engage():
    # mpris: two engages perform exactly ONE pause set
    bm = _FakeBackend([PlayerState("A", True)])
    dm = AudioDucker(bm, mode="mpris")
    dm.engage()
    dm.engage()
    assert bm.paused == ["A"]
    # volume: double engage preserves the ORIGINAL snapshot (50, not 15)
    bv = _FakeBackend(volume=50.0)
    dv = AudioDucker(bv, mode="volume", volume_pct=15)
    dv.engage()
    dv.engage()
    dv.release()
    assert bv.set_calls == [15.0, 50.0]  # restored to 50 → the 50 snapshot survived


def test_release_without_engage_is_noop():
    b = _FakeBackend([PlayerState("A", True)], volume=50.0)
    d = AudioDucker(b, mode="mpris")
    d.release()
    d.release()
    assert b.call_log == []           # zero backend calls


def test_off_mode_never_calls_backend():
    b = _FakeBackend([PlayerState("A", True)], volume=50.0)
    d = AudioDucker(b, mode="off", volume_pct=15)
    d.engage()
    d.release()
    assert b.call_log == []           # byte-identical no-op: zero backend calls
    assert d.engaged is False


# --- 4. Failure discipline ---

def test_backend_exception_swallowed_logged_once(caplog):
    b = _FakeBackend([PlayerState("A", True)], fail={"pause_player"})
    d = AudioDucker(b, mode="mpris")
    with caplog.at_level(logging.WARNING):
        d.engage()                    # must NOT raise
        d.release()                   # empty ledger → no-op, no further calls
    assert d.engaged is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1         # exactly ONE warning, no traceback spam
    assert "pause_player(A)" in warnings[0].getMessage()
    # the failed pause left the player Playing and OUT of the ledger → release no-ops
    assert b.paused == [] and b.resumed == []
    assert b.call_log == ["list_players", "pause_player"]


def test_volume_engage_read_failure_leaves_no_snapshot():
    b = _FakeBackend(volume=None, fail=set())
    d = AudioDucker(b, mode="volume", volume_pct=15)
    d.engage()                        # get returns None → no duck attempted
    assert b.set_calls == []
    d.release()                       # no snapshot → release no-ops
    assert b.set_calls == []
    assert b.call_log == ["get_sink_volume_pct"]


# --- 5. Config wiring (P1.M2.T1.S1 contract) ---

try:
    import voice_typing.config as _vt_config

    _HAS_AUDIO_CONFIG = hasattr(_vt_config, "AudioConfig")
except ImportError:  # pragma: no cover — config module itself missing
    _HAS_AUDIO_CONFIG = False


@pytest.mark.skipif(
    not _HAS_AUDIO_CONFIG,
    reason="AudioConfig (parallel P1.M2.T1.S1) has not landed yet — defer, never delete",
)
def test_from_config_reads_audio_section():
    from voice_typing.config import AudioConfig, VoiceTypingConfig

    cfg = VoiceTypingConfig(audio=AudioConfig(duck_mode="volume", duck_volume_pct=25))
    b = _FakeBackend(volume=50.0)
    d = AudioDucker.from_config(cfg, b)
    d.engage()
    assert b.set_calls == [25.0]      # duck_mode="volume" + duck_volume_pct=25 wired through
    assert d.engaged is True
    d.release()
    assert b.set_calls == [25.0, 50.0]
