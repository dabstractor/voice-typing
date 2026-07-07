"""Unit tests for voice_typing.daemon — cfg_to_kwargs + build_recorder wiring (P1.M4.T1.S1).

NO real RealtimeSTT / NO model load / NO CUDA / NO real feedback.py dependency:
  - cfg_to_kwargs is tested directly (pure dict; cuda_check.resolve_device_and_models is mocked).
  - _construct (build_recorder's testable core) is tested with a _FakeRecorder that captures **kwargs.
  - _filter_kwargs_to_signature is tested with strict fakes (drop path) + a **kwargs fake (accept-all).
  - callbacks are tested by calling _build_callbacks(_FakeFeedback())[name](...) and asserting state.

Decoupled from the in-progress feedback.py (P1.M3.T2.S1): a _FakeFeedback stub records calls instead
of importing voice_typing.feedback. Decoupled from RealtimeSTT: _construct takes a fake recorder class.

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_daemon.py -v
"""
from __future__ import annotations

import logging

import pytest

from voice_typing import daemon
from voice_typing.config import AsrConfig, VoiceTypingConfig


# ---------------------------------------------------------------------------
# Stubs — duck-typed stand-ins so tests never import RealtimeSTT or feedback.py.
# ---------------------------------------------------------------------------


class _FakeFeedback:
    """Records update_partial/set_phase calls. Matches the Feedback contract S1 wires."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)


class _FakeRecorder:
    """Accepts ANY kwargs (VAR_KEYWORD) and captures them. Filter returns all verbatim."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)


class _StrictFakeRecorder:
    """Explicit param list (no **kwargs) missing most of our kwargs -> exercises the DROP path."""

    # Accepts only these three of our kwargs; everything else must be filtered out.
    def __init__(self, model: str = "", language: str = "", device: str = "") -> None:
        self.kwargs = {"model": model, "language": language, "device": device}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _cuda_resolve(monkeypatch, mapping: dict[str, str]) -> None:
    """Force voice_typing.cuda_check.resolve_device_and_models onto a deterministic path.

    Faithfully emulates the real function's contract so cfg-derived values still flow
    through on the cuda path:
      - cuda path (mapping is CUDA_DEFAULTS): echo the caller's `defaults` (built from cfg),
        exactly as the real function does when is_cuda_available() is True. This is what lets
        the passthrough test observe custom model/device values.
      - cpu path (mapping is CPU_FALLBACK): ignore `defaults` and return CPU_FALLBACK verbatim,
        exactly as the real function does when CUDA is absent (the PRD §4.4 hard override).
    """
    is_fallback = mapping is daemon.cuda_check.CPU_FALLBACK

    def _resolve(defaults=None):
        if is_fallback:
            return dict(mapping)
        # cuda path: the real function returns dict(defaults) — honor cfg-derived values.
        return dict(defaults) if defaults is not None else dict(mapping)

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)


@pytest.fixture
def cfg() -> VoiceTypingConfig:
    return VoiceTypingConfig()


# ---------------------------------------------------------------------------
# cfg_to_kwargs — keys + model/timing identity
# ---------------------------------------------------------------------------


def test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set(cfg):
    kw = daemon.cfg_to_kwargs(cfg)
    # No on_* callbacks here (they are wired in build_recorder).
    assert not any(k.startswith("on_") for k in kw), sorted(kw)
    expected = {
        "model", "realtime_model_type", "language", "device", "compute_type",
        "realtime_processing_pause", "post_speech_silence_duration",
        "enable_realtime_transcription", "use_main_model_for_realtime",
        "min_length_of_recording", "min_gap_between_recordings", "silero_sensitivity",
        "webrtc_sensitivity", "silero_backend", "spinner", "use_microphone",
        "ensure_sentence_starting_uppercase", "ensure_sentence_ends_with_period",
    }
    assert set(kw) == expected, sorted(set(kw) ^ expected)


def test_cfg_to_kwargs_cuda_path(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["device"] == "cuda"
    assert kw["compute_type"] == "float16"
    assert kw["model"] == "distil-large-v3"
    assert kw["realtime_model_type"] == "small.en"


def test_cfg_to_kwargs_cpu_fallback(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CPU_FALLBACK)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["device"] == "cpu"
    assert kw["compute_type"] == "int8"
    assert kw["model"] == "small.en"
    assert kw["realtime_model_type"] == "tiny.en"


def test_cfg_to_kwargs_fixed_values(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["enable_realtime_transcription"] is True
    assert kw["use_main_model_for_realtime"] is False
    assert kw["min_length_of_recording"] == 0.3
    assert kw["min_gap_between_recordings"] == 0.0
    assert kw["silero_sensitivity"] == 0.4
    assert kw["webrtc_sensitivity"] == 3
    assert kw["spinner"] is False
    assert kw["use_microphone"] is True


def test_cfg_to_kwargs_silero_correction(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    # item correction (a): explicit silero_backend="auto"; legacy silero_use_onnx dropped.
    assert kw["silero_backend"] == "auto"
    assert "silero_use_onnx" not in kw


def test_cfg_to_kwargs_textproc_owns_cleanup(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    # item correction (b): both False so textproc is authoritative.
    assert kw["ensure_sentence_starting_uppercase"] is False
    assert kw["ensure_sentence_ends_with_period"] is False


def test_cfg_to_kwargs_no_device_index_overrides(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    # PRD §4.4: leave input_device_index unset (PipeWire default); gpu_device_index defaults to 0.
    assert "input_device_index" not in kw
    assert "gpu_device_index" not in kw


def test_cfg_to_kwargs_passes_through_config_values(monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    custom = VoiceTypingConfig(asr=AsrConfig(
        language="es",
        post_speech_silence_duration=0.9,
        realtime_processing_pause=0.2,
        final_model="large-v3-turbo",
        realtime_model="medium.en",
        device="cuda",
    ))
    kw = daemon.cfg_to_kwargs(custom)
    assert kw["language"] == "es"
    assert kw["post_speech_silence_duration"] == 0.9
    assert kw["realtime_processing_pause"] == 0.2
    # final_model/realtime_model flow through the resolver (CUDA_DEFAULTS here keeps them).
    assert kw["model"] == "large-v3-turbo"
    assert kw["realtime_model_type"] == "medium.en"


def test_cfg_to_kwargs_calls_resolve_with_cfg_defaults(cfg, monkeypatch):
    """cfg_to_kwargs builds cuda_check defaults FROM cfg (respects an explicit device='cpu')."""
    seen: list[dict] = []

    def fake(defaults=None):
        seen.append(dict(defaults) if defaults else {})
        return dict(daemon.cuda_check.CUDA_DEFAULTS)

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", fake)
    daemon.cfg_to_kwargs(cfg)
    assert seen, "resolve_device_and_models was not called"
    d = seen[0]
    assert d["final_model"] == cfg.asr.final_model
    assert d["realtime_model"] == cfg.asr.realtime_model
    assert d["device"] == cfg.asr.device
    assert d["compute_type"] == "float16"  # derived from device=='cuda'


# ---------------------------------------------------------------------------
# _build_callbacks — wiring
# ---------------------------------------------------------------------------


def test_build_callbacks_keys():
    cb = daemon._build_callbacks(_FakeFeedback())
    assert set(cb) == {
        "on_realtime_transcription_stabilized",
        "on_vad_detect_start",
        "on_vad_start",
        "on_vad_stop",
    }


def test_callback_partial_updates_feedback():
    fb = _FakeFeedback()
    daemon._build_callbacks(fb)["on_realtime_transcription_stabilized"]("hello world")
    assert fb.partials == ["hello world"]
    assert fb.phases == []


@pytest.mark.parametrize("attr,phase", [
    ("on_vad_detect_start", "listening"),
    ("on_vad_start", "speaking"),
    ("on_vad_stop", "listening"),
])
def test_callback_vad_phases(attr, phase):
    fb = _FakeFeedback()
    daemon._build_callbacks(fb)[attr]()
    assert fb.phases == [phase]
    assert fb.partials == []


# ---------------------------------------------------------------------------
# _filter_kwargs_to_signature — defensive drop
# ---------------------------------------------------------------------------


def test_filter_keeps_kwargs_in_signature():
    kw = {"model": "x", "language": "en", "device": "cpu"}
    out = daemon._filter_kwargs_to_signature(kw, _StrictFakeRecorder)
    assert out == kw  # all three are accepted params of _StrictFakeRecorder


def test_filter_drops_unknown_kwargs(caplog):
    kw = {"model": "x", "language": "en", "device": "cpu", "bogus_kw": 1, "also_bogus": 2}
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        out = daemon._filter_kwargs_to_signature(kw, _StrictFakeRecorder)
    assert out == {"model": "x", "language": "en", "device": "cpu"}
    # the two unknown kwargs are named in a WARNING log line
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "bogus_kw" in joined and "also_bogus" in joined


def test_filter_accepts_all_when_var_keyword():
    # _FakeRecorder declares **kwargs -> VAR_KEYWORD -> accept everything.
    kw = {"model": "x", "anything": 1, "on_vad_start": lambda: None}
    out = daemon._filter_kwargs_to_signature(kw, _FakeRecorder)
    assert out == kw


# ---------------------------------------------------------------------------
# _construct — end-to-end wiring through the testable seam (no RealtimeSTT)
# ---------------------------------------------------------------------------


def test_construct_passes_filtered_kwargs_to_recorder(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder)
    kw = rec.kwargs
    # cfg values present
    assert kw["model"] == "distil-large-v3"
    assert kw["device"] == "cuda"
    assert kw["language"] == "en"
    # callbacks present
    assert "on_realtime_transcription_stabilized" in kw
    assert "on_vad_detect_start" in kw and "on_vad_start" in kw and "on_vad_stop" in kw


def test_construct_callbacks_are_live(cfg, monkeypatch):
    """A callback captured by the constructed recorder actually drives the feedback."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    fb = _FakeFeedback()
    rec = daemon._construct(cfg, fb, _FakeRecorder)
    rec.kwargs["on_vad_start"]()           # simulate RealtimeSTT firing on_vad_start
    rec.kwargs["on_realtime_transcription_stabilized"]("live partial")
    assert fb.phases == ["speaking"]
    assert fb.partials == ["live partial"]


def test_construct_drops_kwargs_not_in_strict_recorder(cfg, monkeypatch, caplog):
    """A strict recorder (no **kwargs) forces the defensive drop of most of our kwargs."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        rec = daemon._construct(cfg, _FakeFeedback(), _StrictFakeRecorder)
    # _StrictFakeRecorder accepts only model/language/device -> only those survive filtering.
    assert set(rec.kwargs) == {"model", "language", "device"}
    assert any("dropping" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# build_recorder — the production entry is a thin lazy-import wrapper (smoke only)
# ---------------------------------------------------------------------------


def test_build_recorder_is_callable_and_documented():
    # We do NOT call build_recorder() here (it would import RealtimeSTT + load models — heavy,
    # and that is P1.M7.T2.S1's job via feed_audio). We only assert the contract surface exists.
    assert callable(daemon.build_recorder)
    assert daemon.build_recorder.__doc__, "build_recorder must have a docstring"


# ===========================================================================
# P1.M4.T1.S2 — VoiceTypingDaemon: listen-forever loop + on_final + gate + toggle
# (ADDITIVE — everything above is S1; do not change it.)
# ===========================================================================
import threading
import time as _time


class _DaemonFakeFeedback(_FakeFeedback):
    """Extends S1's _FakeFeedback with record_final + set_listening (S2's contract)."""

    def __init__(self) -> None:
        super().__init__()
        self.finals: list[str] = []
        self.listening_states: list[bool] = []

    def record_final(self, text: str) -> None:
        self.finals.append(text)

    def set_listening(self, listening: bool) -> None:
        self.listening_states.append(listening)


class _StubRecorder:
    """Runtime stand-in for AudioToTextRecorder (held by VoiceTypingDaemon as an INSTANCE).
    Distinct from S1's _FakeRecorder (which captures **kwargs for construction). text() returns
    immediately so the loop spins fast when listening (loop-test friendliness — research §5)."""

    def __init__(self) -> None:
        self.text_calls = 0
        self.last_callback = None
        self.mic: list[bool] = []
        self.aborts = 0
        self.shutdowns = 0

    def text(self, on_transcription_finished=None):
        self.text_calls += 1
        self.last_callback = on_transcription_finished
        return ""   # mimic RealtimeSTT: returns "" when interrupted/idle; loop re-enters

    def set_microphone(self, microphone_on=True):
        self.mic.append(microphone_on)

    def abort(self):
        self.aborts += 1

    def shutdown(self):
        self.shutdowns += 1


class _FakeBackend:
    """Records type_text calls; optionally raises to test on_final error handling."""

    def __init__(self, *, raise_on: str | None = None) -> None:
        self.typed: list[str] = []
        self._raise_on = raise_on

    def type_text(self, text: str) -> None:
        if self._raise_on is not None and text == self._raise_on:
            raise RuntimeError("boom (test)")
        self.typed.append(text)


def _wait_for(predicate, timeout=2.0, interval=0.01):
    """Poll until predicate() is truthy or timeout (s). Returns True if predicate became truthy."""
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if predicate():
            return True
        _time.sleep(interval)
    return predicate()


def _make_daemon(*, recorder=None, backend=None, cfg=None):
    cfg = cfg or VoiceTypingConfig()
    fb = _DaemonFakeFeedback()
    rec = recorder if recorder is not None else _StubRecorder()
    be = backend if backend is not None else _FakeBackend()
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be)
    return d, fb, rec, be


# --- boot: no hot-mic (PRD §4.9) ---


def test_fresh_daemon_not_listening():
    d, _, _, _ = _make_daemon()
    assert d.is_listening() is False


# --- on_final: gate / happy / append_space / reject / typing-error ---


def test_on_final_gate_when_not_listening():
    d, fb, rec, be = _make_daemon()
    # listening is False at boot → on_final drops everything
    d.on_final("hello world")
    assert be.typed == []
    assert fb.finals == []


def test_on_final_happy_path_appends_space():
    d, fb, rec, be = _make_daemon()
    d.start()   # arm
    d.on_final("hello world")
    assert be.typed == ["hello world "]   # append_space default True
    assert fb.finals == ["hello world"]   # recorded WITHOUT the trailing space


def test_on_final_append_space_false():
    cfg = VoiceTypingConfig()
    cfg.output.append_space = False
    d, fb, rec, be = _make_daemon(cfg=cfg)
    d.start()
    d.on_final("hello world")
    assert be.typed == ["hello world"]
    assert fb.finals == ["hello world"]


def test_on_final_rejects_hallucination():
    d, fb, rec, be = _make_daemon()
    d.start()
    d.on_final("thank you.")   # blocklist entry → textproc.clean returns None
    assert be.typed == []
    assert fb.finals == []


def test_on_final_typing_raises_is_caught_and_record_still_happens():
    d, fb, rec, be = _make_daemon(backend=_FakeBackend(raise_on="boom "))
    d.start()
    d.on_final("boom")   # payload "boom " matches raise_on → type_text raises
    assert be.typed == []          # nothing typed (it raised)
    assert fb.finals == ["boom"]   # record_final STILL called (recognition is final regardless)


# --- start / stop / toggle ---


def test_start_arms():
    d, fb, rec, be = _make_daemon()
    d.start()
    assert d.is_listening() is True
    assert rec.mic == [True]
    assert fb.listening_states == [True]


def test_stop_disarms_and_aborts():
    d, fb, rec, be = _make_daemon()
    d.start()
    d.stop()
    assert d.is_listening() is False
    assert rec.mic == [True, False]
    assert rec.aborts >= 1
    assert fb.listening_states == [True, False]


def test_toggle_off_to_on_arms():
    d, fb, rec, be = _make_daemon()
    assert d.is_listening() is False
    d.toggle()
    assert d.is_listening() is True
    assert rec.mic == [True]


def test_toggle_on_to_off_disarms():
    d, fb, rec, be = _make_daemon()
    d.start()
    d.toggle()
    assert d.is_listening() is False
    assert rec.mic == [True, False]
    assert rec.aborts >= 1


def test_toggle_is_an_invololution():
    d, _, _, _ = _make_daemon()
    before = d.is_listening()
    d.toggle(); d.toggle()
    assert d.is_listening() is before


def test_stop_never_calls_recorder_shutdown():
    d, fb, rec, be = _make_daemon()
    d.start(); d.stop()
    assert rec.shutdowns == 0   # Critical #3: shutdown() is ONLY for quit (P1.M4.T2.S2)


# --- request_shutdown ---


def test_request_shutdown_sets_event_and_aborts_not_shutdown():
    d, fb, rec, be = _make_daemon()
    d.request_shutdown()
    assert rec.aborts >= 1
    assert rec.shutdowns == 0   # NO full teardown here (P1.M4.T2.S2 owns it)


# --- run() loop ---


def test_run_loop_not_listening_does_not_call_text():
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: True, timeout=0.2)   # let it sleep-loop a moment
        assert rec.text_calls == 0             # not listening → never calls text()
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)
    assert not t.is_alive()


def test_run_loop_calls_text_when_listening_then_exits_on_shutdown():
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        d.start()
        assert _wait_for(lambda: rec.text_calls >= 2, timeout=2.0), rec.text_calls
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)
    assert not t.is_alive()


def test_run_sets_uptime_after_start():
    d, fb, rec, be = _make_daemon()
    assert d.uptime_s == 0.0   # not started yet
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d.uptime_s >= 0.0 and d._start_monotonic is not None, timeout=1.0)
        assert d.uptime_s >= 0.0
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)
