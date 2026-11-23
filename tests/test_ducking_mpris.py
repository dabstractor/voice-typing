"""Unit tests for voice_typing.ducking_mpris (PRD §4.2quinquies — MPRIS ducking tier, P1.M2.T2.S2).

Pure-Python, busctl MOCKED: subprocess.run is monkeypatched for every test via the `bus`
fixture, so no test ever touches the real session bus, launches a real player, or sends
Pause/Play to the user's media (the Level-3 live smoke is a separate READ-ONLY step; PRD
test case (a) is pinned at the TIER level through the REAL AudioDucker in test 14 —
still over the fake bus only).

Pins (research mpris_busctl_tier.md §4):
  - the five exact busctl argv forms (external_tech_notes §3.3) byte-for-byte;
  - regex-over-stdout parsing of ListNames / PlaybackStatus / CanPause (no token splitting);
  - both user-sovereignty gates: CanPause read before every Pause; Play() issued ONLY on
    exactly "Paused" — never on Stopped (the restart hazard) or Playing (already resumed);
  - the failure discipline (timeout=1.0, check=False, stderr DEVNULL — asserted on EVERY
    call by the fake; ONE WARNING on timeout / missing binary; DEBUG on per-player churn;
    nothing ever raises);
  - volume methods as documented zero-call stubs (S3's wpctl backend owns the real ones).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_ducking_mpris.py -v
"""
from __future__ import annotations

import logging
import subprocess

import pytest

from voice_typing import ducking_mpris
from voice_typing.audio_ducking import AudioDucker, PlayerState
from voice_typing.ducking_mpris import MprisBusctlBackend

_BUSCTL = ducking_mpris._BUSCTL
_LOGGER = "voice_typing.ducking_mpris"

MPD = "org.mpris.MediaPlayer2.mpd"
VLC = "org.mpris.MediaPlayer2.vlc"
FOO = "org.mpris.MediaPlayer2.foo"
NEW = "org.mpris.MediaPlayer2.audacious"


# ---------------------------------------------------------------------------
# _FakeBus — records subprocess.run(argv, **kwargs) and never touches the OS.
#
# ducking_mpris does `import subprocess` and calls `subprocess.run(...)`, so
# patching the `run` attribute on the shared subprocess module (same mechanic as
# test_typing_backends._Recorder) is what the backend sees; monkeypatch restores
# the real subprocess.run after each test — no leakage.
#
# Each busctl call is normalized to an op tuple so tests target exactly one call:
#   ("ListNames",)                                   -- DBus ListNames
#   ("get-property", name, "PlaybackStatus"|"CanPause")
#   ("call", name, "Pause"|"Play")
# ---------------------------------------------------------------------------


class _FakeBus:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.list_names_stdout = ""
        self.statuses: dict[str, str] = {}
        self.can_pause: dict[str, bool] = {}
        self.fail_ops: set[tuple[str, ...]] = set()               # rc != 0 (churn path)
        self.raise_ops: dict[tuple[str, ...], BaseException] = {}  # raise path

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ducking_mpris.subprocess, "run", self)

    # -- argv plumbing ------------------------------------------------------

    @staticmethod
    def _op(argv: list[str]) -> tuple[str, ...]:
        rest = argv[1:]  # strip /usr/bin/busctl
        assert rest[0] == "--user"
        verb = rest[1]
        if verb == "call" and rest[2] == "org.freedesktop.DBus":
            return ("ListNames",)
        if verb == "get-property":
            return ("get-property", rest[2], rest[5])
        return ("call", rest[2], rest[5])

    def _stdout(self, argv: list[str]) -> str:
        op = self._op(argv)
        if op == ("ListNames",):
            return self.list_names_stdout
        _kind, name, prop = op
        if prop == "PlaybackStatus":
            return f's "{self.statuses[name]}"' if name in self.statuses else ""
        if prop == "CanPause":
            return f'b {"true" if self.can_pause.get(name) else "false"}'
        return ""  # Pause / Play: empty stdout, rc 0 == success

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        # Failure discipline is enforced on EVERY call, in EVERY test, for free:
        assert kwargs.get("timeout") == ducking_mpris._TIMEOUT_S == 1.0  # PRD: bounded <=1 s
        assert kwargs.get("check") is False
        assert kwargs.get("stdout") is subprocess.PIPE  # we parse stdout
        assert kwargs.get("stderr") is subprocess.DEVNULL
        assert kwargs.get("text") is True
        self.calls.append((argv, kwargs))
        op = self._op(argv)
        if op in self.raise_ops:
            raise self.raise_ops[op]
        rc = 1 if op in self.fail_ops else 0
        if rc == 0 and op[0] == "call":
            # Model real player behavior: a successful Pause flips the player to
            # "Paused" and a successful Play to "Playing" — without this, release
            # would read pre-duck statuses and the ducker would (rightly) refuse.
            self.statuses[op[1]] = "Paused" if op[2] == "Pause" else "Playing"
        return subprocess.CompletedProcess(argv, rc, stdout=self._stdout(argv))

    # -- test helpers -------------------------------------------------------

    def argvs(self) -> list[list[str]]:
        return [argv for argv, _kw in self.calls]

    def calls_for(self, op: tuple[str, ...]) -> list[list[str]]:
        return [argv for argv in self.argvs() if self._op(argv) == op]

    def ops(self) -> list[tuple[str, ...]]:
        return [self._op(argv) for argv in self.argvs()]


@pytest.fixture
def bus(monkeypatch: pytest.MonkeyPatch) -> _FakeBus:
    fake = _FakeBus()
    fake.install(monkeypatch)
    return fake


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# list_players — parsing + enumeration
# ---------------------------------------------------------------------------


def test_1_list_players_parses_names_and_status(bus):
    bus.list_names_stdout = (
        'as 42 "org.mpris.MediaPlayer2.mpd" "org.freedesktop.DBus" '
        '"org.mpris.MediaPlayer2.vlc"'
    )
    bus.statuses = {MPD: "Playing", VLC: "Paused"}
    players = MprisBusctlBackend().list_players()
    assert players == [PlayerState(MPD, True), PlayerState(VLC, False)]
    # The ListNames call itself uses the EXACT argv form (external_tech_notes §3.3):
    assert bus.argvs()[0] == [
        _BUSCTL, "--user", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus", "ListNames",
    ]


def test_2_list_players_ignores_non_mpris_names(bus):
    bus.list_names_stdout = (
        'as 3 "org.freedesktop.DBus" "org.bar.Baz" "org.mpris.MediaPlayer2.mpd"'
    )
    bus.statuses = {MPD: "Paused"}
    players = MprisBusctlBackend().list_players()
    assert [p.name for p in players] == [MPD]
    # Only ONE status read happened — the non-MPRIS names were never queried:
    assert bus.ops() == [
        ("ListNames",),
        ("get-property", MPD, "PlaybackStatus"),
    ]


def test_3_list_players_omits_player_whose_status_read_fails(bus):
    bus.list_names_stdout = f'as 2 "{MPD}" "{VLC}"'
    bus.statuses = {MPD: "Playing", VLC: "Paused"}
    bus.fail_ops.add(("get-property", VLC, "PlaybackStatus"))
    players = MprisBusctlBackend().list_players()  # must not raise
    assert players == [PlayerState(MPD, True)]
    assert not any(op[0] == "call" for op in bus.ops())  # unreadable => never paused


def test_4_list_names_failure_returns_empty_with_one_warning(bus, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    bus.fail_ops.add(("ListNames",))
    assert MprisBusctlBackend().list_players() == []
    warns = _warnings(caplog)
    assert len(warns) == 1
    assert "ListNames failed" in warns[0].getMessage()
    # The per-call rc!=0 line is DEBUG (normal churn), NOT a warning:
    assert any(r.levelno == logging.DEBUG for r in caplog.records)


# ---------------------------------------------------------------------------
# pause_player — the CanPause gate + exact argv
# ---------------------------------------------------------------------------


def test_5_pause_player_exact_argv_and_success(bus):
    bus.can_pause = {MPD: True}
    assert MprisBusctlBackend().pause_player(MPD) is True
    assert bus.argvs() == [
        # CanPause read first...
        [_BUSCTL, "--user", "get-property", MPD, "/org/mpris/MediaPlayer2",
         "org.mpris.MediaPlayer2.Player", "CanPause"],
        # ...then the EXACT Pause argv (external_tech_notes §3.3):
        [_BUSCTL, "--user", "call", MPD, "/org/mpris/MediaPlayer2",
         "org.mpris.MediaPlayer2.Player", "Pause"],
    ]


def test_6_pause_player_respects_can_pause_false(bus):
    bus.can_pause = {MPD: False}
    assert MprisBusctlBackend().pause_player(MPD) is False
    # NO Pause call — only the CanPause read (the ducker therefore never ledgers it):
    assert bus.ops() == [("get-property", MPD, "CanPause")]


def test_7_pause_player_canpause_unreadable_skips(bus):
    bus.fail_ops.add(("get-property", MPD, "CanPause"))
    assert MprisBusctlBackend().pause_player(MPD) is False
    assert bus.ops() == [("get-property", MPD, "CanPause")]  # unreadable => no Pause


# ---------------------------------------------------------------------------
# resume_player — the Play()-only-on-exactly-Paused gate + exact argv
# ---------------------------------------------------------------------------


def test_8_resume_player_plays_when_paused(bus):
    bus.statuses = {MPD: "Paused"}
    assert MprisBusctlBackend().resume_player(MPD) is True
    assert bus.calls_for(("call", MPD, "Play")) == [
        [_BUSCTL, "--user", "call", MPD, "/org/mpris/MediaPlayer2",
         "org.mpris.MediaPlayer2.Player", "Play"],  # EXACT argv (§3.3)
    ]


def test_9_resume_player_never_restarts_stopped(bus):
    # THE restart hazard: Play() on a Stopped player RESTARTS it (tech-notes §3.1).
    bus.statuses = {MPD: "Stopped"}
    assert MprisBusctlBackend().resume_player(MPD) is False
    assert bus.ops() == [("get-property", MPD, "PlaybackStatus")]  # NO Play call


def test_10_resume_player_skips_already_playing(bus):
    # Double-play race guard: "Playing" means the user already resumed.
    bus.statuses = {MPD: "Playing"}
    assert MprisBusctlBackend().resume_player(MPD) is False
    assert bus.ops() == [("get-property", MPD, "PlaybackStatus")]  # NO Play call


# ---------------------------------------------------------------------------
# Failure discipline — one WARNING, safe default, nothing propagates
# ---------------------------------------------------------------------------


def test_11_timeout_swallowed_into_one_warning(bus, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    bus.can_pause = {MPD: True}
    bus.raise_ops[("get-property", MPD, "CanPause")] = subprocess.TimeoutExpired(
        cmd=_BUSCTL, timeout=1.0
    )
    assert MprisBusctlBackend().pause_player(MPD) is False  # safe default, no raise
    warns = _warnings(caplog)
    assert len(warns) == 1
    assert "timed out" in warns[0].getMessage()


def test_12_missing_binary_swallowed(bus, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    bus.statuses = {MPD: "Paused"}
    bus.raise_ops[("call", MPD, "Play")] = FileNotFoundError(2, "No such file or directory")
    assert MprisBusctlBackend().resume_player(MPD) is False  # safe default, no raise
    warns = _warnings(caplog)
    assert len(warns) == 1
    assert "failed" in warns[0].getMessage()


# ---------------------------------------------------------------------------
# Volume stubs — protocol completeness only (S3's wpctl owns the real ones)
# ---------------------------------------------------------------------------


def test_13_volume_methods_are_stubs(bus):
    backend = MprisBusctlBackend()
    assert backend.get_sink_volume_pct() is None
    assert backend.set_sink_volume_pct(15.0) is False
    assert bus.calls == []  # ZERO busctl calls


# ---------------------------------------------------------------------------
# PRD test case (a) — pinned at the TIER level through the REAL AudioDucker
# ---------------------------------------------------------------------------


def test_14_case_a_tier_pin_through_real_ducker(bus):
    """A player the user paused/resumed/started mid-dictation is never fought.

    Arm with A(Playing), B(Paused), C(Playing): engage pauses ONLY A and C (B was
    never playing — not ours to restore). Mid-dictation the user resumes A, starts
    a NEW player D. Release must Play ONLY C: A is skipped by the ducker's rule (c)
    (fresh state says playing), B/D are not in the ledger, and the backend's own
    Paused-only gate closes the Stopped-restart hazard underneath.
    """
    bus.list_names_stdout = f'as 3 "{MPD}" "{VLC}" "{FOO}"'
    bus.statuses = {MPD: "Playing", VLC: "Paused", FOO: "Playing"}
    bus.can_pause = {MPD: True, VLC: True, FOO: True, NEW: True}

    ducker = AudioDucker(MprisBusctlBackend(), mode="mpris")
    ducker.engage()
    assert ducker.engaged is True
    # Paused exactly the Playing players — and NOTHING else:
    assert len(bus.calls_for(("call", MPD, "Pause"))) == 1
    assert len(bus.calls_for(("call", FOO, "Pause"))) == 1
    assert not bus.calls_for(("call", VLC, "Pause"))  # already Paused at arm: untouched
    pauses = len(bus.calls_for(("call", MPD, "Pause"))) + len(bus.calls_for(("call", FOO, "Pause")))
    assert pauses == 2

    # Mid-dictation, the user acts; the fake bus mutates accordingly:
    bus.statuses[MPD] = "Playing"   # user resumed A themselves
    bus.statuses[NEW] = "Playing"   # user started a NEW player
    bus.list_names_stdout = f'as 4 "{MPD}" "{VLC}" "{FOO}" "{NEW}"'

    ducker.release()
    assert ducker.engaged is False
    # Play fired ONLY for FOO (ledger ∧ fresh-enumerated ∧ still-Paused):
    assert len(bus.calls_for(("call", FOO, "Play"))) == 1
    for name in (MPD, VLC, NEW):
        assert not bus.calls_for(("call", name, "Play")), (
            f"release must never Play {name}: MPD was resumed by the user, VLC was "
            "never ours, NEW started mid-dictation"
        )
