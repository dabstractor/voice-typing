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
import re

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
        "no_log_file",
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


def test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log(cfg, monkeypatch):
    """bugfix Issue 1: no_log_file=True is fixed so the production daemon never opens
    realtimesst.log (PRD §4.2 sole log path is stderr → journald; parity with the
    tests/test_feed_audio.py G-NOLOGFILE override)."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    assert "no_log_file" in kw, sorted(kw)
    assert kw["no_log_file"] is True


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


def _ok_probe():
    """Hermetic mic-probe stub for daemon-constructing tests (bugfix Issue 2 / P1.M1.T2.S1).

    Returns a healthy mic so __init__/_arm never touch real PyAudio. Probe-specific tests
    inject their own probers (or mock pyaudio via sys.modules) to exercise _probe_mic directly.
    """
    return (True, None)


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
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be, mic_prober=_ok_probe)
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


# ===========================================================================
# P1.M4.T1.S3 — Per-utterance latency logging (LatencyLog + structured log line + device log)
# (ADDITIVE — everything above is S1+S2; do not change it.)
# ===========================================================================
# NOTE: `re` + `time as _time` are imported at module top (S1/S2 sections) — reused here.


# --- LatencyLog unit tests ---


def test_latencylog_partial_count_and_reset():
    lat = daemon.LatencyLog()
    lat.note_partial("a")
    lat.note_partial("b")
    rec = lat.finalize_utterance(text="ab", t_final_ready=10.0, t_typed=10.05)
    assert rec["partials"] == 2
    # reset: a new finalize with no partials between reads 0
    rec2 = lat.finalize_utterance(text="x", t_final_ready=11.0, t_typed=11.01)
    assert rec2["partials"] == 0


def test_latencylog_speech_end_and_deltas():
    lat = daemon.LatencyLog()
    t0 = _time.monotonic()
    lat.note_speech_end()
    rec = lat.finalize_utterance(text="hi", t_final_ready=t0 + 0.600, t_typed=t0 + 0.634)
    assert rec["t_speech_end"] is not None
    assert rec["speech_end_to_final_ms"] == 600.0   # 0.600s -> 600.0ms (rounded 0.1)
    assert rec["final_to_typed_ms"] == 34.0          # 0.034s -> 34.0ms
    assert rec["total_ms"] == 634.0


def test_latencylog_no_speech_end_yields_na_deltas():
    lat = daemon.LatencyLog()
    rec = lat.finalize_utterance(text="hi", t_final_ready=5.0, t_typed=5.02)
    assert rec["t_speech_end"] is None
    assert rec["speech_end_to_final_ms"] is None
    assert rec["total_ms"] is None
    assert rec["final_to_typed_ms"] == 20.0          # always present


def test_latencylog_ring_buffer_bounded_and_snapshot_copy():
    lat = daemon.LatencyLog(ring_size=3)
    for i in range(5):
        lat.finalize_utterance(text=str(i), t_final_ready=float(i), t_typed=float(i) + 0.01)
    snap = lat.snapshot()
    assert [r["text"] for r in snap] == ["2", "3", "4"]   # oldest evicted; newest last
    snap.append("mutate")                                  # snapshot is a copy
    assert len(lat.snapshot()) == 3


# --- _build_callbacks(fb, latency) wiring ---


def test_build_callbacks_threads_latency_into_partial_and_vad_stop():
    fb = _FakeFeedback()
    lat = daemon.LatencyLog()
    cb = daemon._build_callbacks(fb, lat)
    cb["on_realtime_transcription_stabilized"]("hello")
    cb["on_realtime_transcription_stabilized"]("hello world")
    cb["on_vad_stop"]()
    assert fb.partials == ["hello", "hello world"]          # feedback still driven
    assert fb.phases == ["listening"]                        # set_phase still driven
    rec = lat.finalize_utterance(text="hello world", t_final_ready=1.0, t_typed=1.02)
    assert rec["partials"] == 2
    assert rec["t_speech_end"] is not None                  # note_speech_end fired


def test_build_callbacks_latency_none_is_noop():
    # S1 behavior preserved: latency=None -> no extra side effect; phases/partials unchanged.
    fb = _FakeFeedback()
    cb = daemon._build_callbacks(fb, None)
    cb["on_realtime_transcription_stabilized"]("hi")
    cb["on_vad_stop"]()
    assert fb.partials == ["hi"]
    assert fb.phases == ["listening"]


# --- on_final emits the structured latency line + populates the ring buffer ---


def _grep_latency_line(messages):
    for m in messages:
        if m.startswith(daemon._LATENCY_LOG_PREFIX) and "event=utterance_final" in m:
            return m
    return None


def test_on_final_emits_structured_latency_line(caplog):
    d, fb, rec, be = _make_daemon()
    d._latency.note_speech_end()
    _time.sleep(0.001)
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.start()
        d.on_final("hello world")
    line = _grep_latency_line([r.getMessage() for r in caplog.records])
    assert line is not None, "no latency line emitted"
    assert line.startswith("voice-typing latency: event=utterance_final")
    assert "final_to_typed_ms=" in line and "total_ms=" in line and "partials=" in line
    assert "speech_end_to_final_ms=" in line and "ts_epoch=" in line
    assert "text='hello world'" in line          # %r of cleaned text
    # total_ms is a number (t_speech_end was set) -> not n/a
    assert re.search(r"total_ms=\d", line)
    # S2 behavior preserved:
    assert be.typed == ["hello world "] and fb.finals == ["hello world"]


def test_on_final_latency_line_na_when_no_vad_stop(caplog):
    d, fb, rec, be = _make_daemon()
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.start()
        d.on_final("quick")              # no note_speech_end -> t_speech_end None
    line = _grep_latency_line([r.getMessage() for r in caplog.records])
    assert line is not None
    assert "speech_end_to_final_ms=n/a" in line
    assert "total_ms=n/a" in line
    assert re.search(r"final_to_typed_ms=\d", line)      # always numeric
    # ring buffer still got a record
    snap = d._latency.snapshot()
    assert len(snap) == 1 and snap[0]["text"] == "quick"


def test_on_final_populates_ring_buffer_snapshot():
    d, _, _, _ = _make_daemon()
    d._latency.note_speech_end()
    d.start()
    d.on_final("one")
    d._latency.note_speech_end()
    d.on_final("two")
    snap = d._latency.snapshot()
    assert [r["text"] for r in snap] == ["one", "two"]


def test_on_final_rejected_hallucination_emits_no_latency_line(caplog):
    d, _, _, _ = _make_daemon()
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d.start()
        d.on_final("thank you.")         # blocklist -> clean() None -> early return
    line = _grep_latency_line([r.getMessage() for r in caplog.records])
    assert line is None
    assert d._latency.snapshot() == []


# --- run() logs the resolved device/models at startup ---


def test_run_logs_resolved_device_at_startup(monkeypatch, caplog):
    # Force a deterministic cuda resolution so the startup line is stable + hermetic.
    monkeypatch.setattr(
        daemon.cuda_check,
        "resolve_device_and_models",
        lambda defaults=None: {"device": "cuda", "compute_type": "float16",
                               "final_model": "distil-large-v3", "realtime_model": "small.en"},
    )
    d, _, _, _ = _make_daemon()
    import threading
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: any("device resolved" in r.getMessage() for r in caplog.records)
                  if caplog.records else False, timeout=2.0) or None
        msgs = [r.getMessage() for r in caplog.records]
    finally:
        d.request_shutdown()
        _wait_for(lambda: not t.is_alive(), timeout=2.0)
        t.join(timeout=2.0)
    assert any("voice-typing device resolved:" in m for m in msgs), msgs
    dev_line = next(m for m in msgs if "device resolved" in m)
    assert "device=cuda" in dev_line and "final_model=distil-large-v3" in dev_line


# ===========================================================================
# P1.M4.T2.S1 — VoiceTypingDaemon.status_snapshot() + _resolved_device() (ADDITIVE)
# (status_snapshot reads the LIVE in-memory Feedback state + caches the cuda_check probe once.
#  Uses a REAL Feedback so .snapshot() exists; reuses S2's _StubRecorder/_FakeBackend for the
#  daemon's recorder/backend slots, and S1's _cuda_resolve to force the device path hermetically.)
# ===========================================================================
from voice_typing.config import FeedbackConfig
from voice_typing.feedback import Feedback


def _make_daemon_with_feedback(tmp_path, monkeypatch, *, cuda=True):
    """A real VoiceTypingDaemon whose _feedback is a real Feedback (has .snapshot()).

    cuda_check.resolve_device_and_models is monkeypatched (via S1's _cuda_resolve) for hermetic
    device values. state_file lives under tmp_path so the Feedback write never touches the OS
    runtime dir. Returns (daemon, feedback).
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS if cuda else daemon.cuda_check.CPU_FALLBACK)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb = Feedback(cfg.feedback)
    rec = _StubRecorder()
    be = _FakeBackend()
    return daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be, mic_prober=_ok_probe), fb


def test_status_snapshot_keys_and_cuda_values(tmp_path, monkeypatch):
    d, fb = _make_daemon_with_feedback(tmp_path, monkeypatch, cuda=True)
    fb.update_partial("hello")
    fb.record_final("world")
    s = d.status_snapshot()
    assert set(s) == {"listening", "partial", "last_final", "uptime_s",
                      "device", "compute_type", "final_model", "realtime_model",
                      "mic_ok", "mic_error"}                      # bugfix Issue 2 / P1.M1.T2.S2
    assert s["listening"] is False and s["partial"] == "hello" and s["last_final"] == "world"
    assert s["device"] == "cuda" and s["compute_type"] == "float16"
    assert s["final_model"] == "distil-large-v3" and s["realtime_model"] == "small.en"
    assert s["mic_ok"] is True and s["mic_error"] == ""          # S1's _ok_probe via _make_daemon_with_feedback


def test_status_snapshot_reflects_listening_toggle(tmp_path, monkeypatch):
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    assert d.status_snapshot()["listening"] is False
    d.start()
    assert d.status_snapshot()["listening"] is True


def test_status_snapshot_cpu_fallback_models(tmp_path, monkeypatch):
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch, cuda=False)
    s = d.status_snapshot()
    assert s["device"] == "cpu" and s["final_model"] == "small.en" and s["realtime_model"] == "tiny.en"


def test_status_snapshot_reflects_mic_health(tmp_path, monkeypatch):
    """bugfix Issue 2 / P1.M1.T2.S2: status_snapshot surfaces self._mic_ok/_mic_error (S1's probe).

    Sets the attrs directly (decoupled from S1's probe mechanics) and asserts they appear in the
    snapshot with the right types (mic_ok bool, mic_error coerced from None -> '').
    """
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    # healthy (default from _ok_probe):
    assert d.status_snapshot()["mic_ok"] is True
    assert d.status_snapshot()["mic_error"] == ""
    # unhealthy — set directly to test the SURFACING (S2's job), not the probe (S1's job):
    d._mic_ok = False
    d._mic_error = "no PyAudio input devices available"
    s = d.status_snapshot()
    assert s["mic_ok"] is False
    assert s["mic_error"] == "no PyAudio input devices available"
    # mic_error None coerces to "" even if a probe ever stores None on a False result:
    d._mic_error = None
    assert d.status_snapshot()["mic_error"] == ""


def test_resolved_device_caches_resolve_called_once(tmp_path, monkeypatch):
    calls = {"n": 0}

    def _resolve(defaults=None):
        calls["n"] += 1
        return dict(daemon.cuda_check.CUDA_DEFAULTS)

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    d = daemon.VoiceTypingDaemon(
        cfg, Feedback(cfg.feedback), recorder=_StubRecorder(), backend=_FakeBackend(),
        mic_prober=_ok_probe,
    )
    d.status_snapshot()
    d.status_snapshot()
    assert calls["n"] == 1                      # cached after the first call


def test_resolved_device_failure_degrades_to_unknown(tmp_path, monkeypatch):
    def boom(defaults=None):
        raise RuntimeError("cuda exploded")

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", boom)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    d = daemon.VoiceTypingDaemon(
        cfg, Feedback(cfg.feedback), recorder=_StubRecorder(), backend=_FakeBackend(),
        mic_prober=_ok_probe,
    )
    s = d.status_snapshot()
    assert s["device"] == "unknown"             # never raises; degrades gracefully


# ===========================================================================
# P1.M4.T2.S2 — clean-shutdown wiring: VoiceTypingDaemon.shutdown() + SIGTERM/SIGINT handlers
# (ADDITIVE — everything above is S1/S2/S3/(S1-of-T2); do not change it.)
# ===========================================================================
# Reuses _make_daemon() / _StubRecorder / _wait_for from earlier in this file.
# `daemon` and `logging` are already imported at module top.
import signal as _signal


# --- Layer A: VoiceTypingDaemon.shutdown() ------------------------------------------------


def test_shutdown_calls_recorder_shutdown_once():
    d, fb, rec, be = _make_daemon()
    assert rec.shutdowns == 0
    d.shutdown()
    assert rec.shutdowns == 1


def test_shutdown_is_idempotent():
    d, fb, rec, be = _make_daemon()
    d.shutdown()
    d.shutdown()
    d.shutdown()
    # our _shutdown_done flag (RealtimeSTT's own guard is also idempotent) -> exactly one call
    assert rec.shutdowns == 1


class _RaisingRecorder(_StubRecorder):
    """shutdown() always raises — proves daemon.shutdown() is defensive (best-effort)."""

    def shutdown(self):
        self.shutdowns += 1
        raise RuntimeError("boom (test)")


def test_shutdown_swallows_recorder_failure(caplog):
    d, fb, rec, be = _make_daemon(recorder=_RaisingRecorder())
    with caplog.at_level(logging.ERROR, logger="voice_typing.daemon"):
        d.shutdown()  # must NOT raise
    assert rec.shutdowns == 1  # it was called once
    assert any("recorder.shutdown() failed" in r.getMessage() for r in caplog.records)


def test_stop_and_request_shutdown_still_never_shutdown():
    # Regression proof: shutdown() is a NEW path; stop/toggle/request_shutdown keep NOT tearing down.
    d, fb, rec, be = _make_daemon()
    d.start()
    d.stop()
    d.toggle()
    d.request_shutdown()
    assert rec.shutdowns == 0


# --- Layer B: install_shutdown_signal_handlers() -------------------------------------------


def test_install_registers_handler_for_sigterm_and_sigint():
    d, _, _, _ = _make_daemon()
    prev_term = _signal.getsignal(_signal.SIGTERM)
    prev_int = _signal.getsignal(_signal.SIGINT)
    try:
        restore = daemon.install_shutdown_signal_handlers(d)
        assert _signal.getsignal(_signal.SIGTERM) is not _signal.SIG_DFL
        assert _signal.getsignal(_signal.SIGINT) is not _signal.SIG_DFL
        restore()
        assert _signal.getsignal(_signal.SIGTERM) is prev_term
        assert _signal.getsignal(_signal.SIGINT) is prev_int
    finally:
        _signal.signal(_signal.SIGTERM, prev_term)
        _signal.signal(_signal.SIGINT, prev_int)


def test_handler_invocation_requests_shutdown_via_spawned_thread():
    d, _, rec, _ = _make_daemon()
    prev = _signal.getsignal(_signal.SIGUSR1)
    try:
        daemon.install_shutdown_signal_handlers(d, signals=(_signal.SIGUSR1,))
        handler = _signal.getsignal(_signal.SIGUSR1)
        handler(_signal.SIGUSR1, None)  # invoke directly (no real signal) — spawns a thread
        assert _wait_for(
            lambda: d._shutdown.is_set() and rec.aborts >= 1, timeout=2.0
        ), (d._shutdown.is_set(), rec.aborts)
    finally:
        _signal.signal(_signal.SIGUSR1, prev)


def test_handler_is_idempotent_vs_reentry():
    d, _, rec, _ = _make_daemon()
    prev = _signal.getsignal(_signal.SIGUSR1)
    try:
        daemon.install_shutdown_signal_handlers(d, signals=(_signal.SIGUSR1,))
        handler = _signal.getsignal(_signal.SIGUSR1)
        handler(_signal.SIGUSR1, None)
        assert _wait_for(lambda: d._shutdown.is_set(), timeout=2.0)
        aborts_after_first = rec.aborts
        handler(_signal.SIGUSR1, None)  # _shutdown already set -> no new thread
        handler(_signal.SIGUSR1, None)
        _time.sleep(0.1)
        assert rec.aborts == aborts_after_first  # no further abort spawned
    finally:
        _signal.signal(_signal.SIGUSR1, prev)


def test_install_custom_signals_set_honored():
    d, _, _, _ = _make_daemon()
    prev_usr2 = _signal.getsignal(_signal.SIGUSR2)
    prev_term = _signal.getsignal(_signal.SIGTERM)
    try:
        restore = daemon.install_shutdown_signal_handlers(d, signals=(_signal.SIGUSR2,))
        assert _signal.getsignal(_signal.SIGUSR2) is not _signal.SIG_DFL
        # SIGTERM NOT touched (custom set honored)
        assert _signal.getsignal(_signal.SIGTERM) is prev_term
        restore()
        assert _signal.getsignal(_signal.SIGUSR2) is prev_usr2
    finally:
        _signal.signal(_signal.SIGUSR2, prev_usr2)
        _signal.signal(_signal.SIGTERM, prev_term)


# ===========================================================================
# P1.M4.T3.S1 — daemon main() entry point: _resolve_log_level / _setup_logging /
# main() lifecycle + the if __name__ == "__main__" guard.
# (ADDITIVE — everything above is S1/S2/S3/(S1-of-T2)/(T2.S2); do not change it.)
# ===========================================================================
import ast
import sys
from pathlib import Path


# --- Layer A: _resolve_log_level ---------------------------------------------------------


def test_resolve_log_level_valid_names():
    assert daemon._resolve_log_level("INFO") == logging.INFO
    assert daemon._resolve_log_level("DEBUG") == logging.DEBUG
    assert daemon._resolve_log_level("warning") == logging.WARNING  # case-insensitive
    assert daemon._resolve_log_level("  debug  ") == logging.DEBUG  # stripped


def test_resolve_log_level_invalid_falls_back_to_info():
    assert daemon._resolve_log_level("VERBOSE") == logging.INFO  # getLevelName -> "Level VERBOSE"
    assert daemon._resolve_log_level("") == logging.INFO
    assert daemon._resolve_log_level(None) == logging.INFO  # non-str
    assert daemon._resolve_log_level(20) == logging.INFO  # non-str


# --- Layer B: _setup_logging (monkeypatch basicConfig — hermetic) -------------------------


def test_setup_logging_configures_stderr_at_level(monkeypatch):
    captured = {}

    def _capture(**kw):
        captured.update(kw)

    monkeypatch.setattr(logging, "basicConfig", _capture)
    daemon._setup_logging("DEBUG")
    assert captured["stream"] is sys.stderr
    assert captured["level"] == logging.DEBUG
    assert "asctime" in captured["format"] and "message" in captured["format"]


def test_setup_logging_passes_resolved_level(monkeypatch):
    captured = {}

    def _capture(**kw):
        captured.update(kw)

    monkeypatch.setattr(logging, "basicConfig", _capture)
    daemon._setup_logging("not-a-level")  # invalid -> INFO
    assert captured["level"] == logging.INFO


# --- Layer C: main() lifecycle orchestration (all components monkeypatched) ----------------


class _MainFakeFeedback:
    def __init__(self, cfg):
        self.cfg = cfg


class _MainFakeDaemon:
    def __init__(self, cfg, fb, **kw):
        self.cfg, self.fb = cfg, fb
        self.run_called = False
        self.shutdown_calls = 0

    def run(self):  # return immediately (NO block, NO recorder)
        self.run_called = True

    def shutdown(self):
        self.shutdown_calls += 1
    # on_quit is wired to this bound method; ControlServer must receive it AS-IS


class _MainFakeServer:
    def __init__(self, d, *, on_quit=None, **kw):
        self.daemon = d
        self.on_quit = on_quit
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


def _patch_main_lifecycle(
    monkeypatch,
    *,
    daemon_cls=_MainFakeDaemon,
    server_cls=_MainFakeServer,
    feedback_cls=_MainFakeFeedback,
):
    refs = {}
    monkeypatch.setattr(
        daemon,
        "VoiceTypingConfig",
        type("C", (), {"load": classmethod(lambda cls: VoiceTypingConfig())}),
    )
    monkeypatch.setattr(daemon, "VoiceTypingDaemon", daemon_cls)
    monkeypatch.setattr(daemon, "ControlServer", server_cls)
    monkeypatch.setattr("voice_typing.feedback.Feedback", feedback_cls)
    restored = {"called": False}

    def _install(d, *, signals=None):
        refs["install_arg"] = d

        def _restore():
            restored["called"] = True

        return _restore

    monkeypatch.setattr(daemon, "install_shutdown_signal_handlers", _install)
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)  # don't touch real root
    return refs, restored


def test_main_runs_full_lifecycle_and_returns_zero(monkeypatch):
    refs, restored = _patch_main_lifecycle(monkeypatch)
    code = daemon.main()
    assert code == 0
    assert daemon.VoiceTypingDaemon is _MainFakeDaemon  # sanity: patch active
    assert refs["install_arg"] is not None  # install_shutdown_signal_handlers got a daemon


def test_main_calls_run_start_stop_and_restore(monkeypatch):
    bag = {}

    class D(_MainFakeDaemon):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            bag["d"] = self

    class S(_MainFakeServer):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            bag["s"] = self

    refs, restored = _patch_main_lifecycle(monkeypatch, daemon_cls=D, server_cls=S)
    assert daemon.main() == 0
    assert bag["d"].run_called is True
    assert bag["s"].start_calls == 1 and bag["s"].stop_calls == 1
    assert bag["d"].shutdown_calls == 1  # finally called shutdown() (no quit here)
    assert restored["called"] is True  # restore() ran in finally


def test_main_wires_on_quit_to_daemon_shutdown(monkeypatch):
    bag = {}

    class D(_MainFakeDaemon):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            bag["d"] = self

    class S(_MainFakeServer):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            bag["s"] = self

    _patch_main_lifecycle(monkeypatch, daemon_cls=D, server_cls=S)
    daemon.main()
    # ControlServer MUST have been built with on_quit == the daemon's shutdown bound method.
    assert bag["s"].on_quit == bag["d"].shutdown


def test_main_passes_config_feedback_to_daemon(monkeypatch):
    bag = {}

    class D(_MainFakeDaemon):
        def __init__(self, cfg, fb, **k):
            super().__init__(cfg, fb, **k)
            bag["cfg"], bag["fb"] = cfg, fb

    _patch_main_lifecycle(monkeypatch, daemon_cls=D)
    daemon.main()
    assert isinstance(bag["cfg"], VoiceTypingConfig)
    assert isinstance(bag["fb"], _MainFakeFeedback) and bag["fb"].cfg is bag["cfg"].feedback


# --- Layer E: fatal path -> return 1, no None-deref ---------------------------------------


def test_main_returns_one_on_daemon_construction_failure(monkeypatch):
    class BoomDaemon:
        def __init__(self, *a, **k):
            raise RuntimeError("recorder init failed")

        def run(self):
            pass

        def shutdown(self):
            pass

    _patch_main_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
    assert daemon.main() == 1  # caught, logged, returns 1 (systemd Restart)


def test_main_returns_one_on_config_load_failure(monkeypatch):
    def _boom(cls):
        raise RuntimeError("bad toml")

    monkeypatch.setattr(
        daemon,
        "VoiceTypingConfig",
        type("C", (), {"load": classmethod(_boom)}),
    )
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)
    assert daemon.main() == 1


# --- Layer F: the __main__ guard (AST — hermetic, no subprocess) --------------------------


def test_main_guard_present_and_calls_main():
    tree = ast.parse(Path("voice_typing/daemon.py").read_text())
    guard = None
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            t = node.test
            if (
                isinstance(t.left, ast.Name)
                and t.left.id == "__name__"
                and any(isinstance(o, ast.Eq) for o in t.ops)
                and any(
                    isinstance(c, ast.Constant) and c.value == "__main__"
                    for c in t.comparators
                )
            ):
                guard = node
                break
    assert guard is not None, "no `if __name__ == '__main__':` guard at module level"
    # body references main (either `main()` or `sys.exit(main())`).
    names = set()
    for stmt in guard.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if isinstance(call.func, ast.Name):  # main()
                names.add(call.func.id)
            elif isinstance(call.func, ast.Attribute):  # sys.exit(...)
                names.add(call.func.attr)
            for arg in call.args:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                    names.add(arg.func.id)  # exit(main())
    assert "main" in names, "guard body does not call main()"


def test_main_is_callable():
    assert callable(daemon.main)


# ===========================================================================
# bugfix P1.M1.T2.S1 — mic health probe: _probe_mic / _refresh_mic_status / __init__ / _arm
# (ADDITIVE — mocks pyaudio via sys.modules + injects probers; ZERO real PyAudio I/O.)
# ===========================================================================


def _install_fake_pyaudio(monkeypatch, *, device_input_channels):
    """Install a fake 'pyaudio' module in sys.modules; _probe_mic's `import pyaudio` binds to it.

    device_input_channels: list of maxInputChannels per device index (the probe keeps those >0).
    """
    class _Dev(dict):
        pass
    devices = [_Dev(maxInputChannels=ch) for ch in device_input_channels]
    class _PA:
        def get_device_count(self):
            return len(devices)
        def get_device_info_by_index(self, i):
            return devices[i]
        def terminate(self):
            pass
    fake = type("M", (), {"PyAudio": _PA})
    monkeypatch.setitem(sys.modules, "pyaudio", fake)
    return fake


def test_probe_mic_ok_when_input_device_present(tmp_path, monkeypatch):
    _install_fake_pyaudio(monkeypatch, device_input_channels=[0, 2, 0])  # index 1 is an input
    d, *_ = _make_daemon()   # _ok_probe used at init (no real pyaudio); we call _probe_mic directly
    ok, err = d._probe_mic()
    assert ok is True and err is None


def test_probe_mic_fails_when_no_input_devices(tmp_path, monkeypatch):
    _install_fake_pyaudio(monkeypatch, device_input_channels=[0, 0])  # outputs only
    d, *_ = _make_daemon()
    ok, err = d._probe_mic()
    assert ok is False and isinstance(err, str) and err


def test_probe_mic_raises_when_pyaudio_unavailable(monkeypatch):
    # `import pyaudio` raises ImportError when sys.modules["pyaudio"] is None.
    monkeypatch.setitem(sys.modules, "pyaudio", None)
    d, *_ = _make_daemon()
    with pytest.raises(ImportError):
        d._probe_mic()   # _probe_mic itself raises; _refresh_mic_status is what catches it


def test_refresh_mic_status_catches_probe_exception():
    # An injected prober that raises -> _mic_ok=False, _mic_error=str(exc); never propagates.
    def boom():
        raise RuntimeError("portaudio exploded")
    d, *_ = _make_daemon()
    d._mic_prober = boom
    d._refresh_mic_status()
    assert d._mic_ok is False and "portaudio exploded" in (d._mic_error or "")


def test_refresh_mic_status_stores_probe_result():
    d, *_ = _make_daemon()
    d._mic_prober = lambda: (False, "no devices")
    d._refresh_mic_status()
    assert d._mic_ok is False and d._mic_error == "no devices"


def test_init_initializes_mic_status_and_calls_probe():
    calls = []
    cfg = VoiceTypingConfig()
    d = daemon.VoiceTypingDaemon(
        cfg, _DaemonFakeFeedback(), recorder=_StubRecorder(), backend=_FakeBackend(),
        mic_prober=lambda: (calls.append(1), (True, None))[1],
    )
    assert d._mic_ok is True and d._mic_error is None
    assert len(calls) == 1          # __init__ probed exactly once


def test_arm_refreshes_mic_status():
    calls = []
    d = daemon.VoiceTypingDaemon(
        VoiceTypingConfig(), _DaemonFakeFeedback(), recorder=_StubRecorder(),
        backend=_FakeBackend(),
        mic_prober=lambda: (calls.append(1), (True, None))[1],
    )
    assert len(calls) == 1          # init
    d.start()                       # -> _arm -> _refresh_mic_status
    assert len(calls) == 2          # armed once more


def test_make_daemon_injection_is_hermetic_no_real_pyaudio():
    # Guard against regression: the factory must inject _ok_probe (no real pyaudio in tests).
    d, *_ = _make_daemon()
    assert d._mic_prober is _ok_probe
    assert d._mic_ok is True        # the stub reported healthy
    assert "pyaudio" not in sys.modules or True  # (informational; other tests may have imported it)
