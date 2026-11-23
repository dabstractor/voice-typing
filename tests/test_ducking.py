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


# ===========================================================================
# P1.M2.T3.S1 — daemon lifecycle wiring (PRD §4.2quinquies "Lifecycle wiring")
# ===========================================================================
# The daemon's arm/disarm seams, driven WITHOUT the run loop (mirroring the
# test_daemon.py precedents): d.start()/d.stop()/d.toggle() for immediate
# disarm, _touch_speech + _text_in_flight + _complete_drain for the graceful
# drain, _last_speech_monotonic + _maybe_auto_stop() for the idle auto-stop,
# note_user_keypress() past the 1.5 s arm-chord grace for the Rev-3 HALT,
# request_shutdown() for quit/SIGTERM, _handle_dead_host() for the child-death
# edge (which fires the stop toast WITHOUT _disarm), and cancel() as the
# MUST-NOT-RELEASE control. A _FakeDucker rides in through the new ducker=
# ctor seam (same injection pattern as backend=/mic_prober=/key_listener=).

import threading  # noqa: E402 (lifecycle section imports; module top owns the core tests)
import time as _time  # noqa: E402

import voice_typing.daemon as daemon  # noqa: E402
from test_daemon import (  # noqa: E402 (repo convention: tests import sibling fakes)
    _DaemonFakeFeedback,
    _StubRecorder,
    _ok_probe,
)
from test_daemon import _FakeBackend as _CtlFakeBackend  # noqa: E402 — ALIASED: test_ducking's
# own core-section _FakeBackend (the DuckBackend double) must keep its module-level name.
from voice_typing.config import VoiceTypingConfig  # noqa: E402


class _FakeDucker:
    """Thread-safe duck-typed AsyncDucker stand-in: records engage/release call order.

    Records CALLS at the seams (not the applied state) — the contract under test is the
    daemon's dispatch discipline, not S4's worker internals. Thread-safe because the
    seams run under self._lock while an AsyncDucker worker could run concurrently.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls: list[str] = []

    def engage(self) -> None:
        with self._lock:
            self.calls.append("engage")

    def release(self) -> None:
        with self._lock:
            self.calls.append("release")

    @property
    def engages(self) -> int:
        return self.calls.count("engage")

    @property
    def releases(self) -> int:
        return self.calls.count("release")


class _DuckingFakeFeedback(_DaemonFakeFeedback):
    """_DaemonFakeFeedback + set_ducked recording (the ducked write side under test)."""

    def __init__(self) -> None:
        super().__init__()
        self.ducked_states: list[bool] = []

    def set_ducked(self, ducked: bool) -> None:
        self.ducked_states.append(bool(ducked))


def _make_ducking_daemon(cfg=None, *, duck: bool = True):
    """Copy of tests/test_daemon.py::_make_daemon passing ducker=fake through the new seam.

    duck=False builds the daemon with NO ducker injected (combine with an explicit
    duck_mode="off" cfg for the off path: _ducker is None ⇒ byte-identical behavior).
    """
    cfg = cfg or VoiceTypingConfig()
    fb = _DuckingFakeFeedback()
    rec = _StubRecorder()
    be = _CtlFakeBackend()
    fake = _FakeDucker()
    extra = {"ducker": fake} if duck else {}
    d = daemon.VoiceTypingDaemon(
        cfg,
        fb,
        recorder=rec,
        backend=be,
        mic_prober=_ok_probe,
        **extra,
    )
    return d, fb, rec, be, fake


def test_ducking_engage_on_arm():
    """Arm via start() → the ducker is engaged and state mirrors ducked=True (PRD a)."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    assert fake.calls == ["engage"]
    assert fb.ducked_states == [True]
    d.stop()  # cleanup so the fake ledger is consistent for later runs


def test_ducking_release_on_stop():
    """Manual stop → release dispatched + ducked=False mirrored (PRD b)."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    d.stop()
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]
    assert d.is_listening() is False


def test_ducking_release_on_toggle_off():
    """toggle-off (the hotkey) releases exactly like stop() (PRD b)."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    d.toggle()  # armed -> the disarm branch
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]
    assert d.is_listening() is False


def test_ducking_release_on_drain_completion():
    """Graceful-stop drain holds the duck until the final lands, then _complete_drain releases."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d._cfg.asr.graceful_stop = True  # drain is opt-in since 2026-10
    d.start()
    d._touch_speech()  # speech happened -> _final_pending=True
    d._text_in_flight.set()  # simulate the run loop blocked inside text()
    d.stop()  # graceful stop -> drain: STILL listening, still ducked
    assert d._drain is True and d.is_listening() is True
    assert fake.releases == 0, "the duck must hold while the final model drains"
    d._text_in_flight.clear()
    d._complete_drain()  # what the run loop does once text() returns the final
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]


def test_ducking_release_on_idle_auto_stop():
    """The 30 s idle auto-stop (_maybe_auto_stop -> _disarm) releases (PRD b, case c)."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    d._last_speech_monotonic = _time.monotonic() - 31.0  # 31 s silent (> 30.0 default)
    d._maybe_auto_stop()
    assert d.is_listening() is False
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]


def test_ducking_release_on_halt():
    """Rev-3 HALT (a real keypress while armed, past the arm-chord grace) releases."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d._cfg.cancel.keypress_action = "disarm"  # HALT semantics (the 2026-10 default)
    d.start()
    assert fake.calls == ["engage"]
    d._armed_monotonic = _time.monotonic() - 10.0  # past the 1.5 s arm-chord grace
    d.note_user_keypress()  # -> with self._lock: _disarm()
    assert d.is_listening() is False
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]


def test_ducking_release_on_quit():
    """request_shutdown() (quit + SIGTERM) releases — never leave media ducked at exit."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    d.request_shutdown()
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]
    assert d._shutdown.is_set() is True


def test_ducking_release_on_dead_host():
    """Child death while ducked: _handle_dead_host releases WITHOUT any _disarm call."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    d._handle_dead_host()  # the run loop's dead-host path (child crash while armed)
    assert fake.calls == ["engage", "release"]
    assert fb.ducked_states == [True, False]
    assert d.is_listening() is False


def test_ducking_no_release_on_cancel():
    """Backspace-cancel keeps the mic hot: NO release, ducked stays True (PRD b/c)."""
    d, fb, _rec, _be, fake = _make_ducking_daemon()
    d.start()
    d.cancel()  # idempotent no-op with no pending tail — but MUST NOT release either way
    assert fake.calls == ["engage"], "cancel() must never release (the mic stays hot)"
    assert fb.ducked_states == [True]
    assert d.is_listening() is True, "cancel keeps _listening set — it is not a disarm"


def test_ducking_off_mode_no_ducker_zero_calls():
    """duck_mode="off" ⇒ _ducker is None ⇒ byte-identical behavior (P1.M2.T4 flipped the DEFAULT
    to "mpris", so the off path is constructed EXPLICITLY here — never via the default)."""
    off_cfg = VoiceTypingConfig()
    off_cfg.audio.duck_mode = "off"
    d, fb, _rec, _be, _fake = _make_ducking_daemon(cfg=off_cfg, duck=False)
    assert d._ducker is None  # the ctor factory never built one
    d.start()  # every seam no-ops; set_ducked is never called
    d.stop()
    assert fb.ducked_states == []


def test_ducking_default_factory_builds_by_mode():
    """_build_default_ducker: off ⇒ None (ctor), mpris/volume ⇒ the AsyncDucker stack."""
    from voice_typing.ducking_async import AsyncDucker
    from voice_typing.ducking_mpris import MprisBusctlBackend
    from voice_typing.ducking_volume import WpctlVolumeBackend

    off = VoiceTypingConfig()  # explicit off mode (P1.M2.T4: the DEFAULT is now "mpris")
    off.audio.duck_mode = "off"
    d = daemon.VoiceTypingDaemon(
        off, _DuckingFakeFeedback(), recorder=_StubRecorder(),
        backend=_CtlFakeBackend(), mic_prober=_ok_probe,
    )
    assert d._ducker is None
    assert daemon._build_default_ducker(off) is None  # the factory itself: off ⇒ None

    mpris_cfg = VoiceTypingConfig()
    mpris_cfg.audio.duck_mode = "mpris"
    dm = daemon._build_default_ducker(mpris_cfg)
    assert isinstance(dm, AsyncDucker)
    assert isinstance(dm._ducker, AudioDucker)
    assert isinstance(dm._ducker._backend, MprisBusctlBackend)
    assert dm._ducker._mode == "mpris"

    vol_cfg = VoiceTypingConfig()
    vol_cfg.audio.duck_mode = "volume"
    vol_cfg.audio.duck_volume_pct = 25
    dv = daemon._build_default_ducker(vol_cfg)
    assert isinstance(dv, AsyncDucker)
    assert isinstance(dv._ducker._backend, WpctlVolumeBackend)
    assert dv._ducker._volume_pct == 25.0


# ===========================================================================
# P1.M2.T3.S2 — crash safety: ducked-flag self-heal + shutdown flush (PRD §4.2quinquies)
# ===========================================================================
# ducking_heal.heal() is the post-crash media restore, shared by TWO consumers: the daemon's
# boot self-heal thread (reads the persisted `ducked` flag BEFORE the boot Feedback writes
# clobber it) and systemd's ExecStopPost (`python -m voice_typing.ducking_heal`, flag-gated →
# no-ops on clean stops). A _HealBackend double (same recording style as the core _FakeBackend)
# rides in through the backend= seam; state.json lives in tmp_path via
# FeedbackConfig(state_file=...). No subprocess, no busctl, no PipeWire — hermetic.

import json  # noqa: E402 (heal-section imports; module top owns the core + S1 lifecycle tests)

import voice_typing.ducking_heal as ducking_heal  # noqa: E402
from voice_typing.config import AudioConfig, FeedbackConfig  # noqa: E402
from voice_typing.feedback import Feedback  # noqa: E402


class _HealBackend:
    """DuckBackend double for the crash-heal: records resume/set calls; raises on demand.

    Separate from the core _FakeBackend because the heal only ever RESUMES (never pauses, and
    never sets volume — warn-only) — the recorded surface is exactly what the heal may call.
    `fail` names methods that RAISE (simulating a misbehaving subprocess backend); volume=None
    models a tier/backend that cannot read the sink (mpris stub semantics).
    """

    def __init__(self, players=(), volume=None, fail=()):
        self.players = list(players)
        self.volume = volume
        self.fail = set(fail)
        self.resumed: list[str] = []
        self.set_calls: list[float] = []
        self.call_log: list[str] = []
        # Set on the FIRST backend call — lets a test wait for the heal to reach the backend
        # WITHOUT racing thread-exit (a finished vt-duck-heal thread vanishes from
        # threading.enumerate(), so name-based join alone is a flake).
        self.reached = threading.Event()

    def _enter(self, method: str) -> None:
        self.call_log.append(method)
        self.reached.set()
        if method in self.fail:
            raise RuntimeError(f"{method} failed (simulated)")

    def list_players(self):
        self._enter("list_players")
        return list(self.players)

    def resume_player(self, name: str) -> bool:
        self._enter("resume_player")
        self.resumed.append(name)
        return True

    def get_sink_volume_pct(self):
        self._enter("get_sink_volume_pct")
        return self.volume

    def set_sink_volume_pct(self, pct: float) -> bool:
        self._enter("set_sink_volume_pct")
        self.set_calls.append(float(pct))
        return True


def _heal_cfg(tmp_path, *, ducked, duck_volume_pct=15):
    """(cfg, state_path) with the state file in tmp_path, seeded with the given flag.

    ducked=None leaves the file ABSENT (fresh-boot / wiped-runtime-dir case). state_file is set
    explicitly so tests never touch the real session's state.json.
    """
    state = tmp_path / "state.json"
    if ducked is not None:
        state.write_text(json.dumps({"ducked": ducked}), encoding="utf-8")
    cfg = VoiceTypingConfig(
        feedback=FeedbackConfig(state_file=str(state)),
        audio=AudioConfig(duck_mode="off", duck_volume_pct=duck_volume_pct),
    )
    return cfg, state


def test_heal_noop_when_ducked_false(tmp_path):
    """ducked:false (the clean-stop case) → heal makes ZERO backend calls (success crit. b)."""
    cfg, _state = _heal_cfg(tmp_path, ducked=False)
    be = _HealBackend(players=[PlayerState("org.mpris.a", playing=False)], volume=15.0)
    ducking_heal.heal(cfg, backend=be)
    assert be.call_log == [], "flag-gate must run BEFORE any backend call"
    assert be.resumed == []


def test_heal_noop_when_state_file_missing(tmp_path):
    """Absent state file (fresh boot) → zero calls, no raise: 'can't read' == 'not flagged'."""
    cfg, state = _heal_cfg(tmp_path, ducked=None)
    be = _HealBackend(players=[PlayerState("org.mpris.a", playing=False)], volume=15.0)
    ducking_heal.heal(cfg, backend=be)
    assert not state.exists()
    assert be.call_log == []


def test_heal_resumes_paused_players_when_ducked(tmp_path):
    """ducked:true → currently-Paused players resumed; Playing players NEVER touched (PRD f)."""
    cfg, _state = _heal_cfg(tmp_path, ducked=True)
    be = _HealBackend(
        players=[
            PlayerState("org.mpris.paused", playing=False),
            PlayerState("org.mpris.playing", playing=True),
        ],
        volume=70.0,
    )
    ducking_heal.heal(cfg, backend=be)
    assert be.resumed == ["org.mpris.paused"]
    assert be.call_log.count("resume_player") == 1, "only the Paused player is resumed"
    assert be.set_calls == [], "volume 70 != duck 15 → no volume interaction at all"


def test_heal_volume_warn_only(tmp_path, caplog):
    """ducked:true + sink at duck pct → ONE warning, NO volume set (the warn-only decision)."""
    cfg, _state = _heal_cfg(tmp_path, ducked=True, duck_volume_pct=15)
    be = _HealBackend(players=[PlayerState("org.mpris.paused", playing=False)], volume=15.0)
    with caplog.at_level(logging.INFO, logger="voice_typing.ducking_heal"):
        ducking_heal.heal(cfg, backend=be)
    assert be.set_calls == [], "never guesses a restore (a clobbering restore is worse than not ducking)"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "duck level" in warnings[0].getMessage()
    assert any(r.levelname == "INFO" and "resumed" in r.getMessage() for r in caplog.records)


def test_heal_always_exits_zero_on_backend_failure(tmp_path, caplog):
    """Backend raising on every call → swallowed (one warning each), nothing propagates."""
    cfg, _state = _heal_cfg(tmp_path, ducked=True)
    be_dead = _HealBackend(
        players=[PlayerState("org.mpris.paused", playing=False)], volume=70.0,
        fail={"list_players", "get_sink_volume_pct"},
    )
    ducking_heal.heal(cfg, backend=be_dead)  # must NOT raise
    assert be_dead.call_log == ["list_players", "get_sink_volume_pct"]
    be_resume = _HealBackend(
        players=[PlayerState("org.mpris.paused", playing=False)], volume=70.0,
        fail={"resume_player"},
    )
    ducking_heal.heal(cfg, backend=be_resume)  # per-player failure swallowed, loop continues
    assert "resume_player" in be_resume.call_log
    failures = [r for r in caplog.records if r.levelname == "WARNING" and "failed; continuing" in r.getMessage()]
    assert len(failures) == 3  # list_players + get_sink_volume_pct + resume_player: ONE each


def test_daemon_startup_heals_ducked_flag(tmp_path, monkeypatch, caplog):
    """Boot reads ducked:true BEFORE the Feedback writes and heals off-thread (PRD case f).

    Drives the REAL wiring: real Feedback ctor (writes nothing — the flag survives), real daemon
    ctor (pre-read → boot set_models_loaded write self-clears the flag → heal thread spawned).
    The heal's MprisBusctlBackend is monkeypatched to the fake; the vt-duck-heal thread is
    joined (bounded) before asserting.
    """
    cfg, state = _heal_cfg(tmp_path, ducked=True)
    be = _HealBackend(players=[PlayerState("org.mpris.paused", playing=False)], volume=70.0)
    monkeypatch.setattr(ducking_heal, "MprisBusctlBackend", lambda: be)
    fb = Feedback(cfg.feedback)  # REAL Feedback: ctor does not write (the flag survives boot)
    with caplog.at_level(logging.INFO):
        daemon.VoiceTypingDaemon(
            cfg, fb, recorder=_StubRecorder(), backend=_CtlFakeBackend(), mic_prober=_ok_probe,
        )
    # The boot write ALREADY self-cleared the flag (set_models_loaded resets ducked to seeded
    # False) — exactly why the pre-read + force=True exist (the heal must not re-read).
    assert json.loads(state.read_text(encoding="utf-8"))["ducked"] is False
    # Wait for the daemon-spawned heal to REACH the fake backend (bounded), then join the
    # thread best-effort — it may already have exited (a finished thread leaves enumerate).
    assert be.reached.wait(timeout=5.0), "heal thread never reached the backend"
    heal_t = next((t for t in threading.enumerate() if t.name == "vt-duck-heal"), None)
    if heal_t is not None:
        heal_t.join(timeout=5.0)
        assert not heal_t.is_alive()
    assert be.resumed == ["org.mpris.paused"], "heal ran on the daemon-spawned thread"
    assert any("crash-recovery" in r.getMessage() for r in caplog.records), "one INFO line"


class _FlushRecordingDucker(_FakeDucker):
    """_FakeDucker + flush() recorder (S2's contract: shutdown() flushes the async worker).

    Local extension — S1's _FakeDucker has no flush() (it predates S2); extending here, not in
    S1's class, keeps the lifecycle contract byte-identical for its own tests.
    """

    def __init__(self) -> None:
        super().__init__()
        self.flushes: list[float] = []

    def flush(self, timeout: float = 2.0) -> bool:
        self.flushes.append(float(timeout))
        return True


def test_shutdown_flushes_ducker():
    """shutdown() ends with a bounded ducker.flush(2.0) — closes S1's async-release gap (crit. c)."""
    fake = _FlushRecordingDucker()
    d = daemon.VoiceTypingDaemon(
        VoiceTypingConfig(), _DuckingFakeFeedback(), recorder=_StubRecorder(),
        backend=_CtlFakeBackend(), mic_prober=_ok_probe, ducker=fake,
    )
    d.shutdown()
    assert fake.flushes == [2.0], "exactly one flush, bounded at 2 s (TimeoutStopSec=15 budget)"


def test_shutdown_flush_noop_without_ducker():
    """duck_mode=off ⇒ _ducker None ⇒ shutdown() runs byte-identically (no flush attempt).

    Explicit off cfg: P1.M2.T4 flipped the default to "mpris", and this test is about the OFF
    path specifically (no ducker ⇒ no flush), not about whatever the default is.
    """
    off_cfg = VoiceTypingConfig()
    off_cfg.audio.duck_mode = "off"
    d, _fb, _rec, _be, _fake = _make_ducking_daemon(cfg=off_cfg, duck=False)
    assert d._ducker is None
    d.shutdown()  # must not raise / must not touch the (absent) ducker
    assert d._ducker is None
