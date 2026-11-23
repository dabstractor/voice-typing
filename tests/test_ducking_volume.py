"""Unit tests for voice_typing.ducking_volume (PRD §4.2quinquies — volume duck tier, P1.M2.T2.S3).

Pure-Python, wpctl MOCKED: subprocess.run is monkeypatched for every test via the `runner`
fixture, so no test ever touches the real audio graph — a live `wpctl set-volume` would
mutate the operator's real sink volume and is FORBIDDEN in validation (research §8; the
live duck+restore is T4's acceptance evidence; live probes are READ-ONLY only).

Pins (research wpctl_volume_tier.md §7):
  - the three exact wpctl argv forms (research §6) byte-for-byte, ABSOLUTE percent only;
  - grammar-over-rc parsing of get-volume — a gone node answers rc=0 ("Node 'N' not
    found") and MUST be detected by the parse, never the return code (Critical #1);
  - the 6-row sequence state table (research §2): pin at the fresh get, read the pin at
    the release get, clear after the release set — correct even when D == V0 (test 14);
  - the Sinks-scoped `*` parse of `wpctl status` — the Sources block's own '*' never wins;
  - the failure discipline (timeout=1.0, check=False, stdout PIPE, stderr DEVNULL —
    asserted on EVERY call by the fake; ONE warning per failure; nothing raises);
  - MPRIS methods as documented zero-call stubs (S2's busctl backend owns the real ones);
  - PRD test case (b) pinned END-TO-END through the REAL AudioDucker (test 12), including
    the skipped-restore continuation the research rationale prescribes.

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_ducking_volume.py -v
"""
from __future__ import annotations

import logging
import subprocess

import pytest

from voice_typing import ducking_volume as dv
from voice_typing.audio_ducking import AudioDucker
from voice_typing.ducking_volume import WpctlVolumeBackend

_LOGGER = "voice_typing.ducking_volume"

# Live-shaped `wpctl status` slices (tree glyphs INCLUDED — the parser must tolerate them;
# the Sinks block carries the default '*' AND SO DOES Sources — the scoping trap).
STATUS_SINKS_AND_SOURCES = (
    "Audio\n"
    " ├─ Sinks:\n"
    " │      39. WholeHouse              [vol: 1.00]\n"
    " │  *   72. Local Analog Stereo     [vol: 1.05]\n"
    " ├─ Sources:\n"
    " │  *   74. Webcam                  [vol: 1.00]\n"
)
STATUS_DEFAULT_82 = (
    "Audio\n"
    " ├─ Sinks:\n"
    " │      39. WholeHouse              [vol: 1.00]\n"
    " │  *   82. New Default             [vol: 1.00]\n"
    " ├─ Sources:\n"
    " │  *   74. Webcam                  [vol: 1.00]\n"
)
STATUS_NO_SINK_DEFAULT = (
    "Audio\n"
    " ├─ Sinks:\n"
    " │      39. WholeHouse              [vol: 1.00]\n"
    " ├─ Sources:\n"
    " │  *   74. Webcam                  [vol: 1.00]\n"
)


# ---------------------------------------------------------------------------
# _FakeRunner — records subprocess.run(argv, **kwargs) and never touches the OS.
#
# ducking_volume does `import subprocess` and calls `subprocess.run(...)`, so patching
# the `run` attribute on the shared subprocess module (same mechanic as S2's
# test_ducking_mpris._FakeBus) is what the backend sees; monkeypatch restores the real
# subprocess.run after each test — no leakage.
#
# The fake models a real sink: a successful set-volume MUTES-by-value — i.e. it rewrites
# the canned get-volume stdout for that target to the new level, so a subsequent read
# observes the duck exactly like PipeWire would.
# ---------------------------------------------------------------------------


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.status_stdout: str = ""                 # canned `wpctl status` body
        self.get_stdout: dict[str, str] = {}         # per-target get-volume stdout override
        self.default_get: str = "Volume: 0.50"       # fallback get-volume stdout
        self.fail_targets: set[str] = set()          # set-volume to these targets → rc=1
        self.raise_ops: dict[str, BaseException] = {}  # verb ("get-volume"/...) → raise

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dv.subprocess, "run", self)

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        # Failure discipline is enforced on EVERY call, in EVERY test, for free:
        assert kwargs.get("timeout") == dv._TIMEOUT_S == 1.0   # PRD: bounded <=1 s
        assert kwargs.get("check") is False
        assert kwargs.get("stdout") is subprocess.PIPE         # we parse stdout
        assert kwargs.get("stderr") is subprocess.DEVNULL
        assert kwargs.get("text") is True
        assert "set-mute" not in argv  # Critical #4: this tier NEVER writes mute — ever
        self.calls.append(argv)
        verb = argv[1]
        if verb in self.raise_ops:
            raise self.raise_ops[verb]
        if verb == "status":
            return subprocess.CompletedProcess(argv, 0, stdout=self.status_stdout)
        if verb == "get-volume":
            rc = 1 if argv[2] in self.fail_targets else 0
            out = self.get_stdout.get(argv[2], self.default_get)
            return subprocess.CompletedProcess(argv, rc, stdout=out)
        if verb == "set-volume":
            target, value = argv[2], argv[3]
            if target in self.fail_targets:
                return subprocess.CompletedProcess(argv, 1)
            # Model the real sink: the level changed, so the next read observes it.
            self.get_stdout[target] = "Volume: %.2f" % (float(value.rstrip("%")) / 100.0)
            return subprocess.CompletedProcess(argv, 0, stdout="")
        raise AssertionError(f"unexpected wpctl verb: {verb!r}")

    # -- test helpers -------------------------------------------------------

    def argvs(self) -> list[list[str]]:
        return [list(a) for a in self.calls]

    def calls_by_verb(self, verb: str) -> list[list[str]]:
        return [a for a in self.argvs() if a[1] == verb]

    def set_argvs(self) -> list[list[str]]:
        return self.calls_by_verb("set-volume")


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> _FakeRunner:
    fake = _FakeRunner()
    fake.install(monkeypatch)
    return fake


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# get-volume parsing — grammar over rc (Criticals #1 / #3)
# ---------------------------------------------------------------------------


def test_1_parse_volume_basic(runner):
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    runner.default_get = "Volume: 0.65"
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() == 65.0
    # Fresh get = resolve (status) + read by the PINNED concrete id — the exact argv forms:
    assert runner.argvs() == [["wpctl", "status"], ["wpctl", "get-volume", "72"]]


def test_2_parse_volume_muted_suffix(runner):
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    runner.default_get = "Volume: 0.65 [MUTED]"
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() == 65.0  # [MUTED] must not break the parse
    assert backend._muted_at_engage is True       # snapshotted for the log ONLY
    # And nothing in the whole session ever writes mute (also enforced per-call by the fake):
    assert not any("set-mute" in " ".join(a) for a in runner.argvs())


def test_3_parse_volume_above_unity(runner):
    # Live-observed 1.05: percent = float × 100, NEVER clamped to 100.
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    runner.default_get = "Volume: 1.05"
    assert WpctlVolumeBackend().get_sink_volume_pct() == 105.0


def test_4_gone_node_returns_none_rc0(runner):
    # THE rc=0 trap: a gone node answers "Node '72' not found" with rc==0 (live-verified).
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() == 50.0        # pins node 72
    assert backend.set_sink_volume_pct(15) is True      # ducked
    runner.get_stdout["72"] = "Node '72' not found"     # canned with rc=0 BY CONSTRUCTION
    assert backend.get_sink_volume_pct() is None        # parse miss, NOT an rc check
    assert backend._node is None and backend._ducked is False  # graceful skip + self-heal
    runner.get_stdout["72"] = "Volume: 0.50"
    assert backend.get_sink_volume_pct() == 50.0        # next get re-resolves the default
    assert len(runner.calls_by_verb("status")) == 2     # …which is why status ran again


# ---------------------------------------------------------------------------
# default-sink resolution — scoped to the Sinks block (Critical #5)
# ---------------------------------------------------------------------------


def test_5_resolve_default_node_scoped_to_sinks(runner):
    runner.status_stdout = STATUS_SINKS_AND_SOURCES  # '*' in Sinks (72) AND Sources (74)
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() == 50.0
    assert backend._node == 72                        # the SINKS '*' won…
    assert runner.calls_by_verb("get-volume") == [["wpctl", "get-volume", "72"]]
    assert not any("74" in " ".join(a) for a in runner.argvs())  # …the Sources '*' never


def test_6_resolve_no_default_marker_falls_back_to_selector(runner):
    runner.status_stdout = STATUS_NO_SINK_DEFAULT     # no '*' in the Sinks block
    runner.default_get = "Volume: 0.65"
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() == 65.0
    # Degraded-not-broken: a one-shot read via the selector is still correct (DEBUG logged):
    assert runner.calls_by_verb("get-volume") == [["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]]
    assert backend._node is None


# ---------------------------------------------------------------------------
# The sequence state machine (research §2 state table) — rows 2, 4, 3
# ---------------------------------------------------------------------------


def test_7_engage_pins_node_and_sets_absolute(runner):
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() == 50.0
    assert backend.set_sink_volume_pct(15) is True
    # Duck applied to the PINNED id, ABSOLUTE percent, no +/- prefix:
    assert runner.set_argvs() == [["wpctl", "set-volume", "72", "15%"]]
    assert all(not a[3].startswith(("+", "-")) for a in runner.set_argvs())
    assert backend._node == 72 and backend._ducked is True   # row 2


def test_8_release_restores_by_pinned_id(runner):
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    backend = WpctlVolumeBackend()
    backend.get_sink_volume_pct()
    backend.set_sink_volume_pct(15)
    assert backend.get_sink_volume_pct() == 15.0   # the fake sink was mutated by the set
    assert backend.set_sink_volume_pct(50) is True
    assert runner.set_argvs()[-1] == ["wpctl", "set-volume", "72", "50%"]
    assert backend._node is None and backend._ducked is False  # row 4: pin cleared


def test_9_release_read_uses_pinned_node_not_new_default(runner):
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    backend = WpctlVolumeBackend()
    backend.get_sink_volume_pct()
    backend.set_sink_volume_pct(15)
    runner.status_stdout = STATUS_DEFAULT_82       # the user switched the default mid-dictation
    assert backend.get_sink_volume_pct() == 15.0   # reads the PINNED 72, not the new 82
    assert runner.calls_by_verb("get-volume")[-1] == ["wpctl", "get-volume", "72"]
    assert len(runner.calls_by_verb("status")) == 1  # NO re-resolve at release (row 3)


# ---------------------------------------------------------------------------
# Failure discipline — one WARNING, safe default, nothing propagates
# ---------------------------------------------------------------------------


def test_10_timeout_swallowed_one_warning(runner, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOGGER)
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    runner.raise_ops["get-volume"] = subprocess.TimeoutExpired(cmd="wpctl", timeout=1.0)
    backend = WpctlVolumeBackend()
    assert backend.get_sink_volume_pct() is None   # safe default, no raise
    warns = _warnings(caplog)
    assert len(warns) == 1
    assert "timed out" in warns[0].getMessage()
    caplog.clear()
    runner.raise_ops.clear()
    runner.raise_ops["set-volume"] = FileNotFoundError(2, "No such file or directory")
    assert backend.set_sink_volume_pct(15.0) is False  # safe default, no raise
    warns = _warnings(caplog)
    assert len(warns) == 1
    assert "failed" in warns[0].getMessage()


# ---------------------------------------------------------------------------
# MPRIS stubs — protocol completeness only (S2's busctl backend owns the real ones)
# ---------------------------------------------------------------------------


def test_11_mpris_stubs_zero_subprocess(runner):
    backend = WpctlVolumeBackend()
    assert backend.list_players() == []
    assert backend.pause_player("org.mpris.MediaPlayer2.mpd") is False
    assert backend.resume_player("org.mpris.MediaPlayer2.mpd") is False
    assert runner.calls == []  # ZERO wpctl calls


# ---------------------------------------------------------------------------
# PRD test case (b) — pinned END-TO-END through the REAL AudioDucker
# ---------------------------------------------------------------------------


def test_12_case_b_end_to_end_user_changed_volume_no_write(runner, caplog):
    """A volume the user touched mid-dictation is NEVER overridden — and the stale pin
    left by the skipped restore re-marks on the next engage, then restores exactly."""
    caplog.set_level(logging.DEBUG)
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    runner.default_get = "Volume: 0.50"
    backend = WpctlVolumeBackend()
    ducker = AudioDucker(backend, mode="volume", volume_pct=15)
    ducker.engage()
    assert runner.set_argvs() == [["wpctl", "set-volume", "72", "15%"]]
    assert backend._node == 72 and backend._ducked is True

    runner.get_stdout["72"] = "Volume: 0.80"  # the user changed the volume mid-dictation
    ducker.release()
    # NO restore write — the last set is still the engage's 15% (the ducker's sovereignty rule):
    assert runner.set_argvs() == [["wpctl", "set-volume", "72", "15%"]]
    assert any("keeping user value" in r.getMessage() for r in caplog.records)

    # Skipped-restore continuation (research §2 rationale): the flag stays set and sets
    # alternate, so the next session's engage-get reads the PINNED (still-ducked) node
    # and its completed release still restores the snapshot BY ID — exactly.
    ducker.engage()   # get reads the pinned node (sink at 80) → snapshot 80; duck set(15)
    ducker.release()  # compare hits the ducked level → restore the 80% snapshot
    assert runner.set_argvs() == [
        ["wpctl", "set-volume", "72", "15%"],  # session 1 engage
        ["wpctl", "set-volume", "72", "15%"],  # session 2 engage
        ["wpctl", "set-volume", "72", "80%"],  # session 2 release — restored EXACTLY
    ]
    assert runner.get_stdout["72"] == "Volume: 0.80"


def test_13_case_b_variant_node_gone_at_release(runner, caplog):
    """Node vanished mid-dictation: no restore write, ducker warns, backend self-heals."""
    caplog.set_level(logging.DEBUG)
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    backend = WpctlVolumeBackend()
    ducker = AudioDucker(backend, mode="volume", volume_pct=15)
    ducker.engage()
    runner.get_stdout["72"] = "Node '72' not found"  # rc=0 by construction — the live trap
    ducker.release()
    assert runner.set_argvs() == [["wpctl", "set-volume", "72", "15%"]]  # no restore write
    warns = _warnings(caplog)
    assert any("could not re-read sink volume" in w.getMessage() for w in warns)
    assert backend._node is None and backend._ducked is False  # unpinned — next get re-resolves


def test_14_degenerate_duck_equals_original(runner):
    """D == V0 (sink already at the duck level): sequence-driven state still round-trips."""
    runner.status_stdout = STATUS_SINKS_AND_SOURCES
    runner.default_get = "Volume: 0.15"
    backend = WpctlVolumeBackend()
    ducker = AudioDucker(backend, mode="volume", volume_pct=15)
    ducker.engage()   # snapshot 15 → set 15
    ducker.release()  # read 15 == D → restore 15
    assert runner.set_argvs() == [
        ["wpctl", "set-volume", "72", "15%"],
        ["wpctl", "set-volume", "72", "15%"],
    ]
    # The pin cleared despite IDENTICAL values — proof the state is sequence-driven, not
    # value-driven (a "is this the duck target?" hack would wedge _ducked here):
    assert backend._node is None and backend._ducked is False
    ducker.engage()   # …and the next session re-pins cleanly
    assert backend._node == 72 and backend._ducked is True
