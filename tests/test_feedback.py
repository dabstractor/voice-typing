"""Unit tests for voice_typing.feedback (PRD §4.6 — state file + hyprctl notify).

Pure-Python, NO real hyprctl, NO real disk throttle timing:
  - subprocess.run is monkeypatched (same _Recorder mechanic as tests/test_typing_backends.py)
    so hyprctl argv is captured and NEVER sent to the OS.
  - time.monotonic is monkeypatched (a controllable fake clock) so the >=10 Hz throttle is
    asserted DETERMINISTICALLY (no timing flakiness, no sleeps).
  - the state file is written to pytest's tmp_path (real round-trip: write -> json.load back).

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_feedback.py -v

Covers: state-file round-trip + shape, atomic write (no .tmp litter, valid JSON), throttle
(>=10 Hz cap, first-call-writes, in-memory partial always updated), hyprctl argv pinning,
the "never notify per partial" contract, notify-only-on-transition, hypr_notify=False gate,
and fire-and-forget error swallowing. TDD — RED until voice_typing/feedback.py (P1.M3.T2.S1)
lands.
"""
from __future__ import annotations

import json
import os
import subprocess
import time

import pytest

from voice_typing.config import FeedbackConfig
from voice_typing.feedback import Feedback


# ---------------------------------------------------------------------------
# Harness: subprocess.run recorder (hyprctl) — identical mechanic to
# tests/test_typing_backends.py::_Recorder. Captures argv + kwargs, never touches the OS.
# ---------------------------------------------------------------------------


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = {}
        self.calls = []
        self._raises: dict[str, BaseException] = {}

    def raise_on(self, cmd0: str, exc: BaseException) -> None:
        self._raises[cmd0] = exc

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(argv, **kwargs):
            self.calls.append((tuple(argv), dict(kwargs)))
            exc = self._raises.get(argv[0])
            if exc is not None:
                raise exc
            return subprocess.CompletedProcess(args=list(argv), returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)

    @property
    def argvs(self) -> list[tuple[str, ...]]:
        return [argv for argv, _kw in self.calls]


# ---------------------------------------------------------------------------
# Harness: controllable monotonic clock (throttle). time.time() is left REAL so ts is a
# plausible epoch; only time.monotonic is frozen/advanced (it drives the throttle).
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def advance(self, dt: float) -> None:
        self._now += dt


# ---------------------------------------------------------------------------
# Fixtures: a Feedback pointed at a tmp_path state file, with hyprctl + clock mocked.
# ---------------------------------------------------------------------------


def _cfg(tmp_path) -> FeedbackConfig:
    return FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=True, notify_ms=2500)


@pytest.fixture
def feedback(monkeypatch, tmp_path):
    """A Feedback with hyprctl mocked + a frozen monotonic clock; state file in tmp_path."""
    rec = _Recorder()
    rec.install(monkeypatch)
    clock = _Clock()
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    fb = Feedback(_cfg(tmp_path))
    return fb, rec, clock


def _read_state(tmp_path) -> dict:
    with open(tmp_path / "state.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# State-file round-trip + shape (PRD §4.6)
# ---------------------------------------------------------------------------


def test_initial_state_not_written_until_first_call(tmp_path):
    # __init__ is lazy — no file until a state-changing call (daemon's set_listening(False)
    # at startup creates it).
    Feedback(_cfg(tmp_path))
    assert not os.path.exists(tmp_path / "state.json")


def test_update_partial_round_trip(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("hello world")
    state = _read_state(tmp_path)
    assert state["partial"] == "hello world"
    assert isinstance(state["ts"], float) and state["ts"] > 0.0


def test_state_shape_has_exactly_the_five_fields(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("x")
    state = _read_state(tmp_path)
    assert set(state.keys()) == {"listening", "phase", "models_loaded", "partial", "last_final", "ts"}


def test_set_phase_round_trip(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.set_phase("speaking")
    assert _read_state(tmp_path)["phase"] == "speaking"


def test_record_final_sets_last_final(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.record_final("A finished sentence.")
    state = _read_state(tmp_path)
    assert state["last_final"] == "A finished sentence."


def test_set_listening_round_trip(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.set_listening(True)
    assert _read_state(tmp_path)["listening"] is True


# ---------------------------------------------------------------------------
# Atomic write — no .tmp litter; file is always valid JSON (readable mid-write)
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_files(feedback, tmp_path):
    fb, _rec, _clock = feedback
    for i in range(20):
        fb.update_partial(f"partial {i}")
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".state.") and p.endswith(".tmp")]
    assert leftovers == [], f"orphaned temp files: {leftovers}"


def test_state_file_mode_0600(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("x")
    mode = os.stat(tmp_path / "state.json").st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_state_dir_mode_0700(tmp_path, monkeypatch):
    # Nested target dir must be created 0o700.
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    nested = tmp_path / "voice-typing" / "state.json"
    Feedback(FeedbackConfig(state_file=str(nested))).update_partial("x")
    dmode = os.stat(tmp_path / "voice-typing").st_mode & 0o777
    assert dmode == 0o700, oct(dmode)


# ---------------------------------------------------------------------------
# Throttle — >=10 Hz max (min 0.1 s between writes); in-memory partial always updated
# ---------------------------------------------------------------------------


def test_first_partial_always_writes(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("first")
    assert _read_state(tmp_path)["partial"] == "first"


def test_throttle_skips_write_within_0_1s(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("first")          # writes (clock=1000.0)
    clock.advance(0.05)                 # 50 ms later — under the 0.1 s cap
    fb.update_partial("second")         # throttled: NOT written to disk
    assert _read_state(tmp_path)["partial"] == "first"  # disk still shows first


def test_throttle_releases_after_0_1s(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("first")          # writes
    clock.advance(0.1)                  # exactly the cap
    fb.update_partial("second")         # writes again
    assert _read_state(tmp_path)["partial"] == "second"


def test_in_memory_partial_updated_even_when_throttled(feedback):
    fb, _rec, clock = feedback
    fb.update_partial("first")
    clock.advance(0.01)                 # under cap -> throttled write
    fb.update_partial("second")
    # memory has the latest; the NEXT non-throttled write flushes it
    assert fb._state["partial"] == "second"


def test_set_phase_always_writes_regardless_of_throttle(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("p")              # writes (resets throttle baseline)
    clock.advance(0.001)                # way under cap
    fb.set_phase("speaking")            # set_phase is NOT throttled -> writes immediately
    assert _read_state(tmp_path)["phase"] == "speaking"


def test_record_final_always_writes_regardless_of_throttle(feedback, tmp_path):
    fb, _rec, clock = feedback
    fb.update_partial("p")
    clock.advance(0.001)
    fb.record_final("done.")            # record_final is NOT throttled -> writes
    assert _read_state(tmp_path)["last_final"] == "done."


# ---------------------------------------------------------------------------
# hyprctl notify — argv pinning, the "never per partial" contract, transitions, gate
# ---------------------------------------------------------------------------


def test_hyprctl_argv_exact_on_listening_start(feedback):
    _fb, rec, _clock = feedback
    feedback[0].set_listening(True)
    assert rec.argvs[0] == (
        "hyprctl", "notify", "-1", "2500", "rgb(88c0d0)", "● listening"
    )


def test_hyprctl_passes_check_false_and_devnull(feedback):
    fb, rec, _clock = feedback
    fb.set_listening(True)
    _argv, kw = rec.calls[0]
    assert kw.get("check") is False
    assert kw.get("stdout") == subprocess.DEVNULL
    assert kw.get("stderr") == subprocess.DEVNULL


def test_record_final_notifies_with_check_glyph(feedback):
    fb, rec, _clock = feedback
    fb.record_final("Hello there.")
    assert rec.argvs[-1][-1] == "✔ Hello there."


def test_record_final_updates_partial_so_status_matches_screen(feedback, tmp_path):
    """record_final must write the FINAL text into partial, not leave the stale realtime partial.

    Regression: the tmux status-right used to keep showing the last realtime partial, which
    trails the final by a word or two (final '...here today?' vs partial '...here?'). The
    status must match what was typed, so record_final overwrites partial with the final text.
    """
    fb, _rec, _clock = feedback
    fb.set_listening(True)
    fb.update_partial("okay what are we typing here")          # trailing realtime partial
    fb.record_final("Okay, what are we typing here today?")    # final has the last word
    state = _read_state(tmp_path)
    assert state["partial"] == "Okay, what are we typing here today?"
    assert state["last_final"] == "Okay, what are we typing here today?"


def test_record_final_silent_when_notify_on_final_false(monkeypatch, tmp_path):
    """notify_on_final=False suppresses ONLY the final popup; start/stop still fire; state still written."""
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=True,
                         notify_ms=2500, notify_on_final=False)
    fb = Feedback(cfg)
    fb.set_listening(True)        # start popup STILL fires (gated by hypr_notify, not notify_on_final)
    fb.record_final("a final")   # final popup SUPPRESSED; state still written; partial = final
    state = _read_state(tmp_path)
    assert state["last_final"] == "a final" and state["partial"] == "a final"
    fb.set_listening(False)       # stop popup STILL fires
    msgs = [a[-1] for a in rec.argvs if a[0] == "hyprctl"]
    assert msgs == ["● listening", "■ stopped"]   # NO "✔ a final" in the list


def test_set_listening_stop_notifies_stopped(feedback):
    fb, rec, _clock = feedback
    fb.set_listening(True)   # start
    fb.set_listening(False)  # stop
    assert rec.argvs[-1][-1] == "■ stopped"


def test_update_partial_never_invokes_hyprctl(feedback):
    """THE anti-spam contract: partials go to state.json ONLY, NEVER to hyprctl."""
    fb, rec, _clock = feedback
    for i in range(50):
        fb.update_partial(f"partial {i}")
    assert rec.argvs == [], f"hyprctl was called {len(rec.argvs)} times for partials"


def test_set_phase_never_invokes_hyprctl(feedback):
    fb, rec, _clock = feedback
    fb.set_phase("speaking"); fb.set_phase("listening"); fb.set_phase("idle")  # noqa: E702
    assert rec.argvs == []


def test_no_notify_on_noop_listening_transition(feedback):
    # set_listening(False) when already False -> write but NO popup (no startup spam).
    fb, rec, _clock = feedback
    fb.set_listening(False)
    assert rec.argvs == []


def test_no_double_notify_when_set_true_twice(feedback):
    fb, rec, _clock = feedback
    fb.set_listening(True)
    fb.set_listening(True)   # already True -> no transition -> no popup
    notify_calls = [a for a in rec.argvs if a[0] == "hyprctl"]
    assert len(notify_calls) == 1


def test_no_notify_when_hypr_notify_false(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=False, notify_ms=2500)
    fb = Feedback(cfg)
    fb.set_listening(True)
    fb.record_final("text")
    fb.set_listening(False)
    assert rec.argvs == []  # hypr_notify=False suppresses ALL popups


def test_notify_ms_from_config_in_argv(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"), hypr_notify=True, notify_ms=9999)
    Feedback(cfg).set_listening(True)
    assert rec.argvs[0][3] == "9999"  # str(notify_ms) in the argv


def test_start_clears_stale_partial_so_status_does_not_flash_old_words(feedback, tmp_path):
    """Arming (False->True) must clear any leftover partial from the previous session.

    Regression: status.sh renders '🎤 <partial>' the moment listening flips true, so a stale
    partial made the OLD utterance flash in the tmux status-right on every re-arm until new
    speech arrived. The partial must be blank on arm and repopulate only from the next
    realtime callback.
    """
    fb, _rec, _clock = feedback
    fb.set_listening(True)
    fb.update_partial("leftover from last session")
    assert _read_state(tmp_path)["partial"] == "leftover from last session"
    fb.set_listening(False)  # disarm: partial persists on disk (invisible — listening is False)
    assert _read_state(tmp_path)["partial"] == "leftover from last session"
    fb.set_listening(True)   # re-arm: partial MUST be cleared
    state = _read_state(tmp_path)
    assert state["partial"] == ""
    assert state["listening"] is True


def test_stop_does_not_clear_partial(feedback, tmp_path):
    """Only arming clears; disarming leaves the partial in place (it's just invisible)."""
    fb, _rec, _clock = feedback
    fb.set_listening(True)
    fb.update_partial("said something")
    fb.set_listening(False)
    assert _read_state(tmp_path)["partial"] == "said something"


def test_noop_set_listening_does_not_clear_partial(feedback, tmp_path):
    """A no-op set_listening (same value, no transition) must not wipe the partial."""
    fb, _rec, _clock = feedback
    fb.set_listening(True)
    fb.update_partial("keep me")
    fb.set_listening(True)  # already True -> no transition -> no clear
    assert _read_state(tmp_path)["partial"] == "keep me"


# ---------------------------------------------------------------------------
# Fire-and-forget — hyprctl failures never propagate (missing binary / non-Hyprland)
# ---------------------------------------------------------------------------


def test_notify_swallows_missing_binary(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    rec.raise_on("hyprctl", FileNotFoundError(2, "No such file", "hyprctl"))
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"))
    fb = Feedback(cfg)
    fb.set_listening(True)  # must NOT raise despite hyprctl missing
    assert os.path.exists(tmp_path / "state.json")  # state write still happened


def test_notify_swallows_subprocess_error(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    rec.raise_on("hyprctl", subprocess.SubprocessError("hyprctl exploded"))
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    cfg = FeedbackConfig(state_file=str(tmp_path / "state.json"))
    Feedback(cfg).record_final("x")  # must NOT raise


# ---------------------------------------------------------------------------
# No real hyprctl — the recorder guarantees subprocess.run never runs for real.
# ---------------------------------------------------------------------------


def test_no_real_subprocess_run_during_tests(monkeypatch, tmp_path):
    rec = _Recorder(); rec.install(monkeypatch)  # noqa: E702
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    fb = Feedback(FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb.set_listening(True); fb.update_partial("p"); fb.record_final("f")  # noqa: E702
    # every hyprctl call was captured, none reached the OS
    assert all(a[0] == "hyprctl" for a in rec.argvs) or rec.argvs == []


# ===========================================================================
# P1.M4.T2.S1 — Feedback.snapshot() (additive: a low-latency in-memory read for status)
# ===========================================================================

def test_snapshot_returns_a_copy_with_the_five_state_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    fb = Feedback(FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb.set_listening(True)
    fb.update_partial("hello")
    snap = fb.snapshot()
    assert set(snap.keys()) == {"listening", "phase", "models_loaded", "partial", "last_final", "ts"}
    assert snap["listening"] is True and snap["partial"] == "hello"


def test_snapshot_is_a_copy_not_an_alias(tmp_path, monkeypatch):
    # Mutating the snapshot must NOT affect the live in-memory state (concurrent-reader safety).
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    fb = Feedback(FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb.update_partial("orig")
    snap = fb.snapshot()
    snap["partial"] = "mutated"
    assert fb._state["partial"] == "orig"   # live state untouched


def test_snapshot_reflects_recorded_final(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "monotonic", _Clock().monotonic)
    fb = Feedback(FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb.record_final("a final utterance")
    assert fb.snapshot()["last_final"] == "a final utterance"


# ---------------------------------------------------------------------------
# Issue 5 (P1.M2.T2.S2): the THREAD SAFETY module-docstring must NOT restate the
# FALSE "The daemon serializes on_final anyway" claim. It must name the actual
# serialization mechanism — VoiceTypingDaemon._on_final_lock (sibling P1.M2.T2.S1).
# Textual guard only. NOTE: `feedback` is a fixture here, so use a distinct alias.
# ---------------------------------------------------------------------------


def test_module_docstring_names_on_final_serialization_lock():
    """Issue 5 regression guard: THREAD SAFETY note names _on_final_lock; stale false claim gone."""
    import voice_typing.feedback as feedback_module  # NOT `feedback` — that's a pytest fixture here

    doc = feedback_module.__doc__ or ""
    assert "_on_final_lock" in doc, "THREAD SAFETY note must reference _on_final_lock"
    assert "serializes on_final anyway" not in doc, "stale FALSE claim removed (Issue 5)"
