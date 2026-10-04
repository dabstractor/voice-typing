"""Daemon-side rolling context-prompt wiring (P1.M2.T5.S2; PRD §4.2quater).

PURE-PYTHON: no CUDA, no mic, no real keystrokes, no child process — the daemon is
constructed with an injected fake host factory (the `host_factory=` seam, per
tests/test_control_socket.py) plus the RecordingBackend/FakeFeedback doubles
convention (copied per tests/test_streaming_commit.py from the house doubles).
The formal computation itself is unit-pinned in tests/test_prompt_engine.py;
this file pins the DAEMON WIRING around it. Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_context_prompt_refresh.py -q

Covers: a streaming commit pushes rolling_context_prompt(committed) via
host.set_prompt and consecutive commits advance it; _arm() queues set_prompt("")
BEFORE set_microphone(True) (FIFO ordering — a warm re-arm never conditions on the
previous session's text); context_prompt=false config -> ZERO set_prompt calls
across arm + commits and a "disabled" status label; a degraded child
(ready.context_prompt=false) -> zero pushes and a "degraded" status label; Rev 1
mode (output.streaming=false) refreshes from the daemon-side committed accumulator
with the engine untouched; a host without set_prompt is a silent DEBUG no-op and a
raising set_prompt is swallowed (the on_final thread survives); a rejected final
(blocklist) does not push; status labels on / off (models not loaded).
"""

from __future__ import annotations

import logging

from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig


# ---------------------------------------------------------------------------
# Test doubles (house convention: copied per tests/test_streaming_commit.py)
# ---------------------------------------------------------------------------


class _FakeFeedback:
    """Feedback stand-in: records partials/phases/finals/listening (daemon contract)."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []
        self.notifies: list[str] = []
        self.modes: list[str] = []
        self.finals: list[str] = []
        self.listening_states: list[bool] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def snapshot(self) -> dict:  # status_snapshot reads this
        return {
            "phase": self.phases[-1] if self.phases else "unloaded",
            "models_loaded": self.phases[-1:] not in (["unloaded"], []),
        }

    def set_models_loaded(self, loaded: bool) -> None:
        pass

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def notify(self, msg: str) -> None:
        self.notifies.append(msg)

    def record_final(self, text: str) -> None:
        self.finals.append(text)

    def set_listening(self, listening: bool) -> None:
        self.listening_states.append(listening)


class _FakeBackend:
    """Records type_text calls (the Rev 1 hatch types directly through it)."""

    def __init__(self) -> None:
        self.typed: list[str] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def press_backspace(self, n: int) -> None:
        self.typed.append(("bs", n))


def _ok_probe():
    return (True, None)  # hermetic mic probe: never touches PyAudio


class _PromptHost:
    """Fake RecorderHost: records set_prompt AND set_microphone IN CALL ORDER.

    The single ordered `calls` list is what pins the arm-time FIFO rule
    (prompt clear must precede the mic/arm command). `context_prompt=False`
    simulates the S1 degraded child (stock context-free kwargs).
    """

    def __init__(
        self,
        cfg,
        feedback,
        latency,
        on_final,
        on_partial,
        on_speech,
        *,
        context_prompt: bool = True,
        **_kw,
    ):
        self.device = {
            "device": "cuda",
            "compute_type": "float32",
            "model": "small.en",
            "context_prompt": bool(context_prompt),  # S1's additive ready flag
        }
        self.calls: list[tuple[str, object]] = []
        self._alive = False

    def spawn(self, timeout: float = 180.0) -> bool:
        self._alive = True
        return True

    @property
    def is_alive(self) -> bool:
        return self._alive

    @property
    def pid(self):
        return None

    def set_microphone(self, on: bool) -> None:
        self.calls.append(("mic", on))

    def set_prompt(self, text: str) -> None:
        self.calls.append(("prompt", text))

    def abort(self) -> None:
        pass

    def text(self, on_final) -> None:
        pass

    def stop(self, timeout: float = 5.0) -> None:
        self._alive = False


def _host_factory(**host_kwargs):
    def _factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        return _PromptHost(
            cfg, feedback, latency, on_final, on_partial, on_speech, **host_kwargs
        )

    return _factory


def _make_daemon(*, cfg=None, host_factory=None, backend=None):
    cfg = cfg or VoiceTypingConfig()
    fb = _FakeFeedback()
    d = daemon.VoiceTypingDaemon(
        cfg,
        fb,
        recorder=None,
        host_factory=host_factory,
        backend=backend if backend is not None else _FakeBackend(),
        mic_prober=_ok_probe,
    )
    return d, fb


def _host_of(d: daemon.VoiceTypingDaemon) -> _PromptHost:
    return d._host  # type: ignore[return-value] — the fake factory's product


def _prompts(d: daemon.VoiceTypingDaemon) -> list[str]:
    return [text for kind, text in _host_of(d).calls if kind == "prompt"]


# ---------------------------------------------------------------------------
# Commit-time refresh (streaming mode, the default)
# ---------------------------------------------------------------------------


def test_streaming_commit_pushes_rolling_context_and_advances():
    d, _fb = _make_daemon(host_factory=_host_factory())
    d.start()
    d.on_final("hello world")  # committed "hello world " (no terminator)
    d.on_final("more words")  # committed "hello world more words "
    assert _prompts(d) == ["", "hello world", "hello world more words"]


def test_streaming_commit_no_boundary_pushes_whole_committed():
    # The T8c pause-join case through the daemon: an unpunctuated run conditions the
    # next decode with its WHOLE text (the thin seam pushed "" here — superseded).
    d, _fb = _make_daemon(host_factory=_host_factory())
    d.start()
    d.on_final("I want to test whether this system")
    assert _prompts(d) == ["", "I want to test whether this system"]


def test_streaming_commit_ends_with_terminator_pushes_empty():
    d, _fb = _make_daemon(host_factory=_host_factory())
    d.start()
    d.on_final("a full sentence.")  # committed ends with '.' -> fresh sentence
    assert _prompts(d) == ["", ""]


# ---------------------------------------------------------------------------
# Arm-time clear: FIFO ordering (clear BEFORE the arm/mic cmd)
# ---------------------------------------------------------------------------


def test_arm_clears_prompt_before_microphone():
    d, _fb = _make_daemon(host_factory=_host_factory())
    d.start()
    assert _host_of(d).calls == [("prompt", ""), ("mic", True)]


def test_warm_rearm_clears_before_microphone_again():
    d, _fb = _make_daemon(host_factory=_host_factory())
    d.start()
    d.on_final("hello world")  # session 1 commit: prompt advanced
    d.stop()  # _disarm records ("mic", False)
    d.start()  # warm re-arm: child stayed resident
    calls = _host_of(d).calls
    last_mic = len(calls) - 1 - calls[::-1].index(("mic", True))
    assert calls[last_mic - 1 : last_mic + 1] == [("prompt", ""), ("mic", True)]
    assert "hello world" not in _prompts(d)[2:]  # stale text NEVER survives an arm


# ---------------------------------------------------------------------------
# Gates: config-off and degraded child -> ZERO pushes; distinguishable labels
# ---------------------------------------------------------------------------


def test_config_off_means_zero_prompt_calls_and_disabled_status():
    cfg = VoiceTypingConfig()
    cfg.asr.context_prompt = False
    d, _fb = _make_daemon(cfg=cfg, host_factory=_host_factory())
    d.start()
    d.on_final("hello world")
    d.on_final("more words")
    assert _host_of(d).calls == [("mic", True)]  # not even the arm-time clear
    assert d.status_snapshot()["context_prompt"] == "off (disabled by config)"


def test_degraded_child_means_zero_pushes_and_degraded_status():
    d, _fb = _make_daemon(host_factory=_host_factory(context_prompt=False))
    d.start()
    d.on_final("hello world")
    assert _host_of(d).calls == [("mic", True)]  # zero pushes across arm + commit
    assert (
        d.status_snapshot()["context_prompt"]
        == "off (degraded — context-free decoding)"
    )


def test_status_labels_on_when_active_and_not_loaded_when_lazy():
    d, _fb = _make_daemon(host_factory=_host_factory())
    assert d.status_snapshot()["context_prompt"] == "off (models not loaded)"
    d.start()
    assert d.status_snapshot()["context_prompt"] == "on"


# ---------------------------------------------------------------------------
# Rev 1 rollback hatch (output.streaming=false): refresh from the accumulator
# ---------------------------------------------------------------------------


def test_rev1_mode_commits_refresh_from_daemon_accumulator():
    cfg = VoiceTypingConfig()
    cfg.output.streaming = False
    d, fb = _make_daemon(cfg=cfg, host_factory=_host_factory())
    be = d._backend
    d.start()
    d.on_final("alpha")  # typed "alpha " directly; accumulator "alpha "
    d.on_final("beta")  # typed "beta ";  accumulator "alpha beta "
    assert be.typed == ["alpha ", "beta "]  # Rev 1 keystroke discipline intact
    assert _prompts(d) == ["", "alpha", "alpha beta"]  # refreshed from the accumulator
    assert d._stream.committed == ""  # the engine is NEVER touched
    assert fb.finals == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# Defensive seams: missing / raising set_prompt; rejected finals do not push
# ---------------------------------------------------------------------------


class _BareHost(_PromptHost):
    """The legacy-adapter shape: a host with NO set_prompt attribute at all."""

    set_prompt = None  # type: ignore[assignment] — the getattr seam must tolerate this


def _bare_host_factory():
    def _factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        return _BareHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)

    return _factory


def test_host_without_set_prompt_is_silent_debug_noop(caplog):
    d, fb = _make_daemon(host_factory=_bare_host_factory())
    d.start()  # arm-time clear must also survive
    with caplog.at_level(logging.DEBUG, logger="voice_typing.daemon"):
        d.on_final("hello world")  # must not raise
    assert fb.finals == ["hello world"]
    assert any("no set_prompt seam" in r.getMessage() for r in caplog.records)


class _BrokenHost(_PromptHost):
    """A host whose set_prompt seam RAISES (simulates an IPC failure)."""

    def set_prompt(self, text: str) -> None:
        self.calls.append(("prompt", text))
        raise RuntimeError("prompt seam exploded (test)")


def _broken_host_factory():
    def _factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        return _BrokenHost(
            cfg, feedback, latency, on_final, on_partial, on_speech, **kw
        )

    return _factory


def test_raising_set_prompt_is_swallowed_and_thread_survives(caplog):
    d, fb = _make_daemon(host_factory=_broken_host_factory())
    d.start()  # the arm-time clear raises too — swallowed
    with caplog.at_level(logging.DEBUG, logger="voice_typing.daemon"):
        d.on_final("hello world")  # commit-time push raises — swallowed
        d.on_final("second final")  # the on_final thread keeps working
    assert fb.finals == ["hello world", "second final"]
    assert any("push failed (ignored)" in r.getMessage() for r in caplog.records)


def test_rejected_final_does_not_push():
    d, _fb = _make_daemon(host_factory=_host_factory())
    d.start()
    d.on_final("hello world")  # good commit: pushed
    d.on_final("thank you.")  # default-blocklist hallucination: NO refresh
    assert _prompts(d) == ["", "hello world"]
