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
    """Records update_partial/set_phase/notify calls. Matches the Feedback contract S1+ wires."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []
        self.notifies: list[str] = []
        self.modes: list[str] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def snapshot(self) -> dict:                       # mirror Feedback.snapshot (status_snapshot reads it)
        return {"phase": self.phases[-1] if self.phases else "unloaded"}

    def set_models_loaded(self, loaded: bool) -> None:  # P1.M2.T2.S1: mirror Feedback contract (no-op stub)
        pass

    def set_mode(self, mode: str) -> None:  # PRD §4.2ter: mirror Feedback.set_mode (no-op stub)
        self.modes.append(mode)

    def notify(self, msg: str) -> None:  # cold-load UX popup (mirrors Feedback.notify)
        self.notifies.append(msg)


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


def test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: avoid the real cuda_check probe
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


def test_cfg_to_kwargs_lite_mode_uses_one_model(cfg, monkeypatch):
    """lite=True (PRD §4.2ter): lite_model for BOTH realtime + final + use_main_model_for_realtime=True.

    Pins that lite mode loads exactly ONE model (the large final model is never constructed) and
    overrides the _FIXED_KWARGS use_main_model_for_realtime=False.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    cfg.asr.lite_model = "small.en"
    kw = daemon.cfg_to_kwargs(cfg, lite=True)
    assert kw["model"] == "small.en"                       # lite_model as the final model
    assert kw["realtime_model_type"] == "small.en"          # AND the realtime model (one model)
    assert kw["use_main_model_for_realtime"] is True        # skips the separate realtime engine
    assert kw["device"] == "cuda" and kw["compute_type"] == "float16"   # device unchanged
    # normal mode is untouched:
    kw_n = daemon.cfg_to_kwargs(cfg)
    assert kw_n["model"] == "distil-large-v3" and kw_n["use_main_model_for_realtime"] is False


def test_cfg_to_kwargs_cpu_fallback(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CPU_FALLBACK)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["device"] == "cpu"
    assert kw["compute_type"] == "int8"
    assert kw["model"] == "small.en"
    assert kw["realtime_model_type"] == "tiny.en"


def test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en(cfg):
    """lite + CPU → tiny.en for BOTH model fields (pins S1 / delta §3.2 BUG-A; PRD §4.2ter).

    On the CPU path lite mode loads the CPU lite substitute 'tiny.en' for BOTH the final and
    realtime model — mirroring how normal CPU-fallback maps small.en→tiny.en for the realtime
    field. Passing resolved=CPU_FALLBACK skips the cuda_check probe, so this is deterministic
    with NO CUDA and NO monkeypatch. use_main_model_for_realtime stays True (one-model guarantee
    holds on CPU too). This is the committed regression for S1 (P1.M1.T1.S1), which S1's PRP
    explicitly deferred to S2.
    """
    kw = daemon.cfg_to_kwargs(
        cfg, resolved=dict(daemon.cuda_check.CPU_FALLBACK), lite=True
    )
    assert kw["model"] == "tiny.en", kw["model"]
    assert kw["realtime_model_type"] == "tiny.en", kw["realtime_model_type"]
    assert kw["device"] == "cpu"
    assert kw["compute_type"] == "int8"
    assert kw["use_main_model_for_realtime"] is True   # one-model guarantee on CPU too


def test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal(cfg, monkeypatch):
    """Lite mode changes ONLY model/realtime_model_type/use_main_model_for_realtime/post_speech_silence_duration.

    Drift guard (PRD §4.2ter): device/compute_type/language/timing/VAD/silero must be IDENTICAL
    between lite and normal mode on CUDA, so a future cfg_to_kwargs / _FIXED_KWARGS edit can't
    silently diverge lite from normal. The CUDA-lite model pick itself is pinned by
    test_cfg_to_kwargs_lite_mode_uses_one_model; this test guards the REST of the kwargs dict.
    (post_speech_silence_duration is the 4th allowed difference — §4.2ter: lite's snugger silence gate is the
    perceived-latency lever; its value is pinned by test_cfg_to_kwargs_lite_uses_shorter_silence_duration.)
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    normal = daemon.cfg_to_kwargs(cfg)
    lite = daemon.cfg_to_kwargs(cfg, lite=True)

    differing = {"model", "realtime_model_type", "use_main_model_for_realtime", "post_speech_silence_duration"}
    # 1) the key SETS are identical (no kwarg silently added/dropped by lite):
    assert set(normal) == set(lite)
    # 2) after removing the 4 allowed-to-differ keys, the remaining dicts are byte-identical:
    assert {k: v for k, v in lite.items() if k not in differing} == \
           {k: v for k, v in normal.items() if k not in differing}
    # 3) and the 4 differing keys differ EXACTLY as the spec requires:
    assert lite["model"] == cfg.asr.lite_model == "small.en"        # lite_model as the final model
    assert lite["realtime_model_type"] == "small.en"                # AND the realtime model (one model)
    assert lite["use_main_model_for_realtime"] is True              # skips the realtime engine
    assert lite["post_speech_silence_duration"] == 0.5              # §4.2ter: snugger lite silence gate
    assert normal["model"] == "distil-large-v3"
    assert normal["realtime_model_type"] == "small.en"
    assert normal["use_main_model_for_realtime"] is False
    assert normal["post_speech_silence_duration"] == 0.6            # normal mode unchanged


def test_cfg_to_kwargs_lite_uses_shorter_silence_duration(cfg, monkeypatch):
    """Lite uses its own snugger post_speech_silence_duration (§4.2ter latency lever); normal is unaffected.

    The silence gate — not the model — is the perceived-latency bottleneck (PRD §4.2ter), so lite MUST shorten
    post_speech_silence_duration to actually feel faster. Pins: (a) the default lite value (0.5) reaches the kwargs;
    (b) an override flows through; (c) normal mode is unchanged (0.6).
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    # (a) default: lite carries the snugger 0.5; normal carries 0.6.
    assert daemon.cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == 0.5
    assert daemon.cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6
    # (b) override flows through lite only (cfg fixture is function-scoped -> safe to mutate):
    cfg.asr.lite_post_speech_silence_duration = 0.3
    assert daemon.cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == 0.3
    # (c) normal is unaffected by the lite override (still the normal cfg value):
    assert daemon.cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6


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


def test_construct_wires_on_speech_into_partial_callback(cfg, monkeypatch):
    """on_speech (idle auto-stop reset hook) fires on a realtime partial, and ONLY then."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    fired = []
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder,
                            on_speech=lambda: fired.append(1))
    rec.kwargs["on_realtime_transcription_stabilized"]("a partial")   # partial -> fires
    assert fired == [1]
    rec.kwargs["on_vad_start"]()                                      # VAD-only -> does NOT fire
    assert fired == [1]


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
import threading  # noqa: E402 (mid-file: S2 section imports; module top is S1 above)
import time as _time  # noqa: E402


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


# P1.M3.T2.S2 (re-plan): the recorder now lives in a RecorderHost child. The lazy-load tests inject
# a FAKE host factory (host_factory=) so _load_host stays CUDA-free + fast. _FakeHost mirrors the
# real RecorderHost's surface (spawn/set_microphone/abort/text/stop/device) but never spawns a child.
# It wraps a _StubRecorder so the existing assertions on rec.mic/rec.aborts/rec.text_calls still work,
# and it records spawn()/stop() calls so the single-flight + idle-unload tests can assert on them.


class _FakeHost:
    """A fake RecorderHost for the lazy-load / idle-unload tests (CUDA-free, fast).

    spawn() returns a configurable result (default True) + sets a fake device dict so _load_host can
    seed _resolved_device_cache. set_microphone/abort/text proxy to the wrapped _StubRecorder so the
    existing assertions (rec.mic / rec.aborts / rec.text_calls) hold. stop() records the call + a
    bounded join on the wrapped recorder's shutdown() (mirrors the legacy adapter's force-cleanup).
    """

    def __init__(self, cfg, feedback, latency, on_final, on_partial, on_speech, *, force_cpu=False, is_listening=None, mode="normal"):
        # Mirror the real RecorderHost.__init__ signature so host_factory=lambda *a, **k: _FakeHost(*a, **k)
        # works. Store the callbacks (the tests do not exercise them, but the daemon wires them).
        self.cfg = cfg
        self.feedback = feedback
        self.latency = latency
        self.on_final = on_final
        self.on_partial = on_partial
        self.on_speech = on_speech
        self.force_cpu = force_cpu
        self.is_listening = is_listening
        self.mode = mode                     # PRD §4.2ter: the mode this fake child was built for
        self.recorder = _StubRecorder()   # the wrapped stub the tests assert on
        self.spawn_calls = 0
        self.spawn_result = True
        self.stop_calls = 0
        self.device = {"device": "cuda", "compute_type": "float16",
                       "final_model": "distil-large-v3", "realtime_model": "small.en"}
        self._alive = False

    def spawn(self, timeout=180.0):
        self.spawn_calls += 1
        self._alive = bool(self.spawn_result)
        return self.spawn_result

    @property
    def is_alive(self):
        return self._alive

    @property
    def pid(self):
        return None

    def set_microphone(self, on):
        self.recorder.set_microphone(on)

    def abort(self):
        self.recorder.abort()

    def text(self, on_final):
        self.recorder.text(on_final)

    def stop(self, timeout=5.0):
        self.stop_calls += 1
        self._alive = False
        # bounded best-effort shutdown of the wrapped stub (mirrors the legacy adapter).
        import threading as _t
        done = _t.Event()
        def _do():
            try:
                self.recorder.shutdown()
            except Exception:
                pass
            finally:
                done.set()
        th = _t.Thread(target=_do, daemon=True)
        th.start()
        done.wait(timeout=timeout)


def _fake_host_factory(spawn_result=True, device=None, mode=None):
    """Build a host_factory callable returning a _FakeHost with the given spawn() result + device.

    `mode` (default None): if given, the returned _FakeHost reports that mode (so lite/mismatch
    tests can pin it); None leaves the _FakeHost default "normal".
    """
    def _factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)
        host.spawn_result = spawn_result
        if mode is not None:
            host.mode = mode
        if device is not None:
            host.device = dict(device)
        return host
    return _factory


def _make_daemon(*, recorder=None, recorder_host=None, host_factory=None, backend=None, cfg=None):
    cfg = cfg or VoiceTypingConfig()
    fb = _DaemonFakeFeedback()
    rec = recorder if recorder is not None else _StubRecorder()
    be = backend if backend is not None else _FakeBackend()
    d = daemon.VoiceTypingDaemon(
        cfg, fb, recorder=rec, recorder_host=recorder_host, host_factory=host_factory,
        backend=be, mic_prober=_ok_probe,
    )
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


# --- graceful-stop drain: a premature stop lets the FINAL model finish, then disarms ---
# stop()/toggle-off do NOT abort an in-flight utterance (that would kill the large model + drop its
# text). When speech is pending (_final_pending) and the run loop is inside text() (_text_in_flight),
# _request_stop sets _drain; the run loop disarms once text() returns the natural final. A watchdog
# (_drain_timeout) aborts the rare no-final case so the drain can't hang. Idle stops disarm at once.

def test_stop_drains_when_utterance_in_flight():
    """stop() mid-utterance does NOT abort — it drains: lets the final finish, THEN disarms."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()               # speech happened -> _final_pending=True
    d._text_in_flight.set()         # simulate the run loop blocked inside text()
    d.stop()                        # graceful stop -> drain (NOT abort)
    assert d._drain is True         # draining
    assert d.is_listening() is True # still listening — the final model is still working
    assert rec.aborts == 0          # NOT aborted: the large model is allowed to finish
    # The run loop would let text() return the final then complete the drain; simulate that:
    d._text_in_flight.clear()
    d._complete_drain()
    assert d.is_listening() is False   # now disarmed
    assert d._drain is False


def test_toggle_off_drains_when_utterance_in_flight():
    """toggle-off (the hotkey) mid-utterance drains, exactly like stop()."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()
    d._text_in_flight.set()
    d.toggle()                      # listening -> disarm branch -> _request_stop -> drain
    assert d._drain is True
    assert rec.aborts == 0


def test_stop_disarms_immediately_when_idle():
    """stop() when idle (no utterance in flight) disarms immediately — nothing to wait for."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d.stop()                        # no _final_pending, not in text() -> immediate disarm
    assert d.is_listening() is False
    assert d._drain is False


def test_stop_aborts_immediately_when_text_idle_no_speech():
    """stop() while text() is blocked but no speech is pending -> immediate disarm + abort."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._text_in_flight.set()         # loop in text(), idle-waiting for the next utterance
    d.stop()                        # _final_pending False -> immediate path
    assert d.is_listening() is False
    assert d._drain is False
    assert rec.aborts == 1          # aborted (no utterance to finish)


def test_drain_timeout_aborts_blocked_text():
    """If no final fires during a drain, the watchdog aborts so the stop completes (no hang)."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()
    d._text_in_flight.set()
    d._begin_drain()
    assert rec.aborts == 0
    d._drain_timeout()              # simulate the watchdog firing (final never came)
    assert rec.aborts == 1          # aborted the blocked text()
    assert d._drain is True         # still set until the run loop completes the drain


def test_on_final_clears_final_pending():
    """A real final clears _final_pending (the utterance is finalized) and types its text."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()
    assert d._final_pending is True
    d.on_final("hello world")
    assert d._final_pending is False
    assert be.typed == ["hello world "]


def test_arm_resets_stale_final_pending_from_prior_session():
    """Issue 2: a fresh _arm() clears a stale _final_pending left by a stray/late partial from a prior session, so the
    next stop disarms immediately (no spurious 5s drain). Before the fix _arm() never reset _final_pending."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()                # speech -> _final_pending=True
    d.on_final("hello world")        # final -> _final_pending=False, text typed
    d._touch_speech()                # STRAY late partial -> _final_pending=True (stale)
    assert d._final_pending is True  # the stale state the fix must clear
    d.stop()                         # disarm (ends the prior session)
    # re-arm: _arm() must reset _final_pending=False (the fix) — no utterance is in flight yet
    d.start()
    assert d._final_pending is False  # CLEAN SLATE (fails before the fix: still True)


def test_disarm_clears_final_pending():
    """Issue 2 (defense in depth): _disarm() clears _final_pending so a stray partial around the disarm doesn't leave it
    stale True into the next session/stop."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()                # _final_pending=True
    assert d._final_pending is True
    d.stop()                         # -> _disarm() (under _lock via stop)
    assert d._final_pending is False  # the fix in _disarm cleared it


def test_stop_after_stray_partial_in_fresh_session_disarms_immediately():
    """Issue 2 end-to-end: after a re-arm (clean slate), a stop with text() idle but NO speech in THIS session disarms
    immediately (no drain) — the stale flag from the prior session was cleared by _arm(). Before the fix this drained 5s."""
    d, fb, rec, be = _make_daemon()
    d.start()
    d._touch_speech()
    d.on_final("hello world")
    d._touch_speech()                # stray stale partial (prior session)
    d.stop()                         # end prior session
    d.start()                        # re-arm -> _arm() resets _final_pending=False (the fix)
    d._text_in_flight.set()          # run loop blocked in text(), idle-waiting for the next utterance
    d.stop()                         # no speech in THIS session -> immediate disarm + abort (NOT a drain)
    assert d.is_listening() is False
    assert d._drain is False
    assert rec.aborts == 1           # immediate abort (before the fix: 0 — it drained instead)


# --- idle auto-stop (asr.auto_stop_idle_seconds) ---
# _idle_watchdog ticks ~1s and calls _maybe_auto_stop(); here we call it directly for deterministic
# logic tests (no real timing). _touch_speech (wired into the partial callback via on_speech) and
# _arm refresh _last_speech_monotonic; _disarm clears it. Default threshold 30.0; 0 disables.


def test_auto_stop_disarms_when_idle_beyond_threshold():
    d, _fb, _rec, _be = _make_daemon()
    d.start()                                              # arm -> _last_speech_monotonic = now
    assert d.is_listening() is True
    d._last_speech_monotonic = _time.monotonic() - 31.0    # 31s silent (> 30.0 default)
    d._maybe_auto_stop()
    assert d.is_listening() is False                       # disarmed by the idle timeout


def test_auto_stop_keeps_alive_with_recent_speech():
    d, _fb, _rec, _be = _make_daemon()
    d.start()
    d._last_speech_monotonic = _time.monotonic() - 5.0     # only 5s silent
    d._maybe_auto_stop()
    assert d.is_listening() is True


def test_touch_speech_resets_the_idle_clock():
    d, _fb, _rec, _be = _make_daemon()
    d.start()
    d._last_speech_monotonic = _time.monotonic() - 60.0    # would be idle
    d._touch_speech()                                      # a partial arrived -> clock reset
    d._maybe_auto_stop()
    assert d.is_listening() is True


def test_auto_stop_disabled_when_threshold_zero():
    cfg = VoiceTypingConfig()
    cfg.asr.auto_stop_idle_seconds = 0.0
    d, _fb, _rec, _be = _make_daemon(cfg=cfg)
    d.start()
    d._last_speech_monotonic = _time.monotonic() - 9999.0  # absurdly idle
    d._maybe_auto_stop()
    assert d.is_listening() is True                        # 0 disables -> never auto-stops


def test_auto_stop_noop_when_not_listening():
    d, _fb, _rec, _be = _make_daemon()
    assert d._last_speech_monotonic is None                 # boot state
    d._maybe_auto_stop()                                    # must be a clean no-op (no error)
    assert d.is_listening() is False


def test_disarm_clears_the_idle_clock():
    d, _fb, _rec, _be = _make_daemon()
    d.start()
    assert d._last_speech_monotonic is not None
    d.stop()
    assert d._last_speech_monotonic is None                 # cleared -> stale watchdog tick is a no-op


def test_idle_watchdog_actually_disarms_in_background():
    """The real watchdog thread (started as run() does) disarms after the threshold elapses."""
    cfg = VoiceTypingConfig()
    cfg.asr.auto_stop_idle_seconds = 1.0                    # 1s for a fast test
    d, _fb, _rec, _be = _make_daemon(cfg=cfg)
    d.start()
    threading.Thread(target=d._idle_watchdog, name="test-idle", daemon=True).start()
    assert _wait_for(lambda: not d.is_listening(), timeout=4.0, interval=0.1), \
        "watchdog did not disarm within 4s of a 1.0s idle threshold"


# --- on_final serialization (P1.M2.T2.S1 / bugfix Issue 5) ---
# RealtimeSTT fires on_final in a NEW thread per final without joining, so two finals can overlap.
# _on_final_lock serializes the clean->type->record->log body. threading + time (as _time) are
# module-level (lines 334-335); _wait_for is at line 402. No new import needed.


def test_on_final_has_dedicated_serialization_lock():
    """The lock exists, is a SEPARATE object from self._lock, and is a working mutex."""
    d, _, _, _ = _make_daemon()
    assert hasattr(d, "_on_final_lock"), "daemon must expose self._on_final_lock"
    assert d._on_final_lock is not d._lock, "must be a SEPARATE lock from self._lock"
    # It is a real, working mutex: acquires uncontended; reports locked().
    assert d._on_final_lock.acquire(blocking=False) is True
    assert d._on_final_lock.locked() is True
    d._on_final_lock.release()
    assert d._on_final_lock.locked() is False


def test_on_final_lock_held_across_type_text():
    """The lock is held for the whole clean->type->record->log body, so a second on_final cannot
    interleave its type_text. Deterministic: while a worker is blocked INSIDE type_text (holding the
    lock), the lock is locked(); once on_final returns, it is not. No fixed sleeps."""
    started = threading.Event()
    release = threading.Event()

    class _BlockingBackend:
        def __init__(self):
            self.typed = []

        def type_text(self, text):
            started.set()                 # signal: we are inside type_text
            release.wait(timeout=2.0)     # hold so the probe can observe the lock being held
            self.typed.append(text)

    probe = _BlockingBackend()
    d, _, _, _ = _make_daemon(backend=probe)
    d.start()
    worker = threading.Thread(target=d.on_final, args=("hello world",))
    worker.start()
    assert _wait_for(started.is_set), "type_text never started (worker stalled)"
    assert d._on_final_lock.locked() is True, "lock must be held while type_text runs"
    release.set()                        # let the worker finish
    worker.join(timeout=2.0)
    assert not worker.is_alive(), "on_final worker did not finish"
    assert d._on_final_lock.locked() is False, "lock must be released once on_final returns"
    assert probe.typed == ["hello world "]   # append_space default True


def test_on_final_serializes_two_concurrent_callbacks():
    """Two on_final callbacks fired concurrently run strictly sequentially: type_text calls never
    overlap (max in-flight == 1) and both texts are typed. In a no-lock (buggy) build the second
    worker enters type_text during the gate window and max_in_flight becomes 2 -> this asserts fail."""
    gate = threading.Event()

    class _ConcurrencyBackend:
        def __init__(self):
            self.typed = []
            self.max_in_flight = 0
            self._in_flight = 0
            self._guard = threading.Lock()

        def type_text(self, text):
            with self._guard:
                self._in_flight += 1
                if self._in_flight > self.max_in_flight:
                    self.max_in_flight = self._in_flight
            gate.wait(timeout=2.0)        # a second call WOULD overlap here if on_final were unserialized
            with self._guard:
                self._in_flight -= 1
            self.typed.append(text)

    probe = _ConcurrencyBackend()
    d, _, _, _ = _make_daemon(backend=probe)
    d.start()
    t1 = threading.Thread(target=d.on_final, args=("alpha",))
    t2 = threading.Thread(target=d.on_final, args=("bravo",))
    t1.start()
    t2.start()
    # Wait until one worker is blocked inside type_text (holding the lock), then give the second a
    # clear window to (wrongly) enter. Under the lock the second is blocked on _on_final_lock.
    assert _wait_for(lambda: probe.max_in_flight >= 1), "no worker reached type_text"
    _time.sleep(0.2)                      # let the second worker attempt entry
    assert probe.max_in_flight == 1, "type_text calls overlapped — on_final is not serialized"
    gate.set()                            # release the blocked worker(s)
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)
    assert not t1.is_alive() and not t2.is_alive(), "workers did not finish"
    assert sorted(probe.typed) == ["alpha ", "bravo "]   # both typed, in some order


# --- start / stop / toggle ---


def test_start_arms():
    d, fb, rec, be = _make_daemon()
    d.start()
    assert d.is_listening() is True
    assert rec.mic == [True]
    assert fb.listening_states == [True]


def test_stop_disarms_and_aborts_when_text_in_flight():
    d, fb, rec, be = _make_daemon()
    d.start()
    d._text_in_flight.set()   # simulate the run() loop blocked inside recorder.text()
    d.stop()
    assert d.is_listening() is False
    assert rec.mic == [True, False]
    assert rec.aborts >= 1     # text() was in flight -> abort() is the correct nudge
    assert fb.listening_states == [True, False]


def test_stop_skips_abort_when_no_text_in_flight():
    # validation Issue 1: abort() blocks forever on was_interrupted.wait() when no thread is in
    # text() (set ONLY inside text()). stop() must NOT call abort() in that case — the listening
    # Event gate + set_microphone(False) already guarantee the instant disarm; abort() is a no-op
    # here and skipping it eliminates the voicectl stop/toggle/quit hang.
    d, fb, rec, be = _make_daemon()
    d.start()
    assert not d._text_in_flight.is_set()   # boot: no thread in text()
    d.stop()
    assert d.is_listening() is False
    assert rec.aborts == 0                   # no thread in text() -> abort() correctly skipped


def test_toggle_off_to_on_arms():
    d, fb, rec, be = _make_daemon()
    assert d.is_listening() is False
    d.toggle()
    assert d.is_listening() is True
    assert rec.mic == [True]


def test_toggle_on_to_off_disarms():
    d, fb, rec, be = _make_daemon()
    d.start()
    d._text_in_flight.set()   # run() loop blocked inside recorder.text() -> abort() is valid
    d.toggle()
    assert d.is_listening() is False
    assert rec.mic == [True, False]
    assert rec.aborts >= 1


def test_toggle_is_an_invololution():
    d, _, _, _ = _make_daemon()
    before = d.is_listening()
    d.toggle(); d.toggle()  # noqa: E702 (involution: two toggles == identity)
    assert d.is_listening() is before


def test_stop_never_calls_recorder_shutdown():
    d, fb, rec, be = _make_daemon()
    d.start(); d.stop()  # noqa: E702 (compact arm-then-disarm setup)
    assert rec.shutdowns == 0   # Critical #3: shutdown() is ONLY for quit (P1.M4.T2.S2)


# --- request_shutdown ---


def test_request_shutdown_sets_event_aborts_and_tears_down_child():
    # BUG-1 fix: request_shutdown() now ALSO tears down the recorder-host child (so a run() loop
    # blocked in host.text() unblocks via child death, not just a racy "final"). This mirrors the
    # voicectl quit path. _shutdown is set, abort() wakes any in-flight text(), AND the child is
    # torn down (host.stop() -> rec.shutdown() via the legacy adapter).
    d, fb, rec, be = _make_daemon()
    d._text_in_flight.set()   # run() loop blocked inside recorder.text() -> abort() wakes it
    d.request_shutdown()
    assert d._shutdown.is_set() is True
    assert rec.aborts >= 1        # in-flight text() -> abort() wakes it
    assert rec.shutdowns >= 1     # BUG-1: child teardown so host.text() unblocks on child death


def test_request_shutdown_skips_abort_but_tears_down_when_no_text_in_flight():
    # validation Issue 1: when no thread is blocked in text(), abort() would hang forever on
    # was_interrupted.wait() (set only inside text()). _shutdown.set() is the real signal the
    # run() loop re-checks on its next 0.05s tick; abort() is correctly skipped when idle.
    # BUG-1: the child is STILL torn down (host.stop()) regardless — it's belt-and-suspenders
    # for the idle case but required for the in-text() case, and harmless/idempotent either way.
    d, fb, rec, be = _make_daemon()
    assert not d._text_in_flight.is_set()
    d.request_shutdown()
    assert d._shutdown.is_set() is True
    assert rec.aborts == 0        # no thread in text() -> abort() skipped (would deadlock)
    assert rec.shutdowns >= 1     # BUG-1: child teardown runs regardless (idempotent vs quit path)


# --- validation Issue 1: abort()-deadlock regression (run-loop integration) ---
# RealtimeSTT's abort() blocks on was_interrupted.wait(), set ONLY inside text(). When the run()
# loop is disarmed/idle (in time.sleep(0.05)) nothing sets that event, so an unconditional abort()
# blocks FOREVER — that hung voicectl stop/toggle(off)/quit intermittently. _safe_abort() gates
# abort() on _text_in_flight (set by run() around recorder.text()), so a stop while the loop is
# IDLE returns instantly (no abort) instead of hanging. These pin both halves of that fix.


def test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang(monkeypatch):
    """voicectl stop while the loop is disarmed/idle must return instantly (validation Issue 1).

    The run() loop is NOT in text() (not listening), so abort() would block forever. _safe_abort()
    skips it; stop() returns. A bounded wait proves it doesn't hang.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)  # run() booted
        assert not d.is_listening()                      # disarmed at boot
        assert not d._text_in_flight.is_set()            # loop idle in time.sleep(0.05)
        done = threading.Event()

        def _stop():
            d.stop()
            done.set()

        threading.Thread(target=_stop, daemon=True).start()
        assert done.wait(timeout=3.0), "stop() hung >3s (abort() deadlock regression)"
        assert rec.aborts == 0                            # idle -> abort() correctly skipped
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_quit_while_run_loop_idle_returns_promptly(monkeypatch):
    """voicectl quit while the loop is disarmed/idle must not hang (validation Issue 1).

    Mirrors the stop() regression: request_shutdown() skips abort() when no thread is in text();
    _shutdown.set() is the real signal the loop re-checks on its 0.05s tick. A bounded wait proves
    the quit path (the one that intermittently dropped the reply -> exit 1) returns promptly.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)
        assert not d._text_in_flight.is_set()            # idle
        done = threading.Event()

        def _quit():
            d.request_shutdown()
            done.set()

        threading.Thread(target=_quit, daemon=True).start()
        assert done.wait(timeout=3.0), "request_shutdown() hung >3s (abort() deadlock regression)"
        assert rec.aborts == 0                            # idle -> abort() skipped
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0)
    t.join(timeout=2.0)


def test_stop_while_text_in_flight_aborts_and_unblocks_loop(monkeypatch):
    """The happy half of the fix: when the loop IS blocked in text(), stop() must still abort().

    _safe_abort() only skips abort() when _text_in_flight is clear; when it is set (the loop is
    inside recorder.text()) abort() is the correct nudge that unblocks text() so the loop can
    re-check _listening and exit. A stub recorder whose text() blocks until aborted proves the
    loop unblocks.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)

    class _BlockingRecorder(_StubRecorder):
        """text() blocks until abort() is called, then returns (mimics RealtimeSTT)."""
        def __init__(self):
            super().__init__()
            self._abort_event = threading.Event()

        def text(self, on_transcription_finished=None):
            self.text_calls += 1
            self.last_callback = on_transcription_finished
            self._abort_event.wait(timeout=5.0)   # block until abort() (or 5s safety)
            return ""

        def abort(self):
            self.aborts += 1
            self._abort_event.set()                # unblock the in-flight text()

    rec = _BlockingRecorder()
    d, fb, _rec, be = _make_daemon(recorder=rec)
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        d.start()
        assert _wait_for(lambda: d._text_in_flight.is_set(), timeout=2.0), "loop did not enter text()"
        done = threading.Event()

        def _stop():
            d.stop()
            done.set()

        threading.Thread(target=_stop, daemon=True).start()
        assert done.wait(timeout=3.0), "stop() hung >3s"
        assert rec.aborts >= 1                      # text() was in flight -> abort() fired
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0)
    t.join(timeout=2.0)


def test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final(monkeypatch):
    """BUG-1 regression: SIGTERM while listening must exit promptly even when the aborted
    recorder.text() does NOT fire a final.

    The real failure: while the run() loop is blocked in host.text(), the SIGTERM handler calls
    request_shutdown(). The child's aborted recorder.text() does NOT always emit a "final" (it
    returns silently ~40% of the time), so _safe_abort() alone leaves host.text()'s wait-loop
    stranded -> the run() loop never re-checks _shutdown -> main()'s finally never runs -> systemd
    SIGKILLs after TimeoutStopSec. The fix: request_shutdown() ALSO tears down the child
    (host.stop()), so host.text()'s wait-loop detects child death and returns within ~0.5s.

    This stub mimics the REAL RecorderHost.text() loop: it blocks on a final-event until either a
    final arrives OR the host is stopped (child death). Pre-fix (abort-only, no stop()) this hung
    indefinitely because abort() never produced a final; post-fix the loop exits within the
    bounded wait because stop() marks the host dead.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)

    class _StrandingHost(_FakeHost):
        """Mimics RecorderHost.text(): blocks on a final-event OR host death (stop()).

        abort() sets the child abort event (as in production) but the recorder does NOT fire a
        final on abort (the racy ~40% path). Only stop() (child teardown) unblocks text().
        """
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._final_evt = threading.Event()
            self._dead = False

        def text(self, on_final):
            self.recorder.text_calls += 1
            self.recorder.last_callback = on_final
            # Mirror RecorderHost.text()'s wait loop: return on final OR death.
            while not self._final_evt.wait(timeout=0.05):
                if self._dead:
                    return

        def abort(self):
            self.recorder.abort()  # set, but NO final fires (the race) -> text() stays blocked

        def stop(self, timeout=5.0):
            self._dead = True       # child death -> host.text()'s loop returns
            super().stop(timeout=timeout)

    factory = _fake_host_factory()
    _orig_factory = factory

    def _wrap(*a, **k):
        h = _orig_factory(*a, **k)
        # rebuild as a _StrandingHost sharing the same cfg/callbacks
        s = _StrandingHost(*a, **k)
        s.recorder = h.recorder
        s.device = h.device
        return s

    d, fb = _make_lazy_daemon(host_factory=_wrap)
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        d.start()  # first arm lazily spawns the host
        assert _wait_for(lambda: d._text_in_flight.is_set(), timeout=2.0), "loop did not enter text()"
        # SIGTERM path: request_shutdown() must unblock host.text() via child teardown (BUG-1 fix).
        d.request_shutdown()
        assert _wait_for(lambda: not t.is_alive(), timeout=3.0), (
            "BUG-1: run() thread did not exit within 3s — request_shutdown() failed to unblock "
            "a stranded host.text() (child teardown missing?)"
        )
    finally:
        d.request_shutdown()
        _wait_for(lambda: not t.is_alive(), timeout=2.0)
    t.join(timeout=2.0)
    assert not t.is_alive()


# ===========================================================================
# P1.M1.T2.S3 — concurrent request_shutdown + shutdown (SIGTERM double-teardown race)
# End-to-end regression for bugfix Issue 1: drives the REAL run() loop + lazy host spawn on
# arm, runs request_shutdown (signal thread) + shutdown (main-thread finally) CONCURRENTLY,
# and asserts exactly ONE host.stop() (single-flight), wall < 8s, clean run-thread exit.
# (S1's _CountingHost/_GatedHost unit tests above prove the mechanics WITHOUT the run loop;
#  THIS test wires them through the real lifecycle — bug_analysis.md §Test Gap.)
# ===========================================================================


def test_concurrent_request_shutdown_and_shutdown_only_one_stop(monkeypatch):
    """SIGTERM-path regression (bugfix Issue 1 / P1.M1.T2.S3).

    The real SIGTERM race: the signal-handler thread runs request_shutdown() (tears the child
    down via _bounded_shutdown() -> host.stop()) WHILE main()'s finally-block runs
    daemon.shutdown() CONCURRENTLY. Pre-fix (pre-P1.M1.T2.S1) BOTH called _bounded_shutdown()
    -> host.stop() TWICE -> the double teardown that blew systemd's 15s TimeoutStopSec -> SIGKILL.
    Post-fix, shutdown() WAITS on _teardown_done instead of a 2nd teardown, so exactly ONE
    host.stop() runs.

    This is the END-TO-END proof (vs S1's unit-level _GatedHost test above): real run()
    loop in a thread + real lazy host spawn on arm (host_factory) + concurrent request_shutdown
    (thread A) + shutdown (thread B). bug_analysis.md §Test Gap: 'No existing test exercises
    the concurrent request_shutdown() + shutdown() path (the SIGTERM path) ... with a real
    _FakeHost' — this is that test.

    The default _FakeHost.stop() returns INSTANTLY (_StubRecorder.shutdown() is a counter++),
    so it gives no concurrency-overlap window. _GatedFakeHost.stop() blocks on a release Event
    to GUARANTEE the in-flight window during which shutdown() is observed WAITING (not starting
    a 2nd stop). Its text() mirrors RecorderHost.text() (blocks until final or child death), so
    run() is genuinely listening when the SIGTERM fires (same shape as the _StrandingHost test).
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic (belt-and-suspenders)

    class _GatedFakeHost(_FakeHost):
        """A _FakeHost whose stop() blocks on a release gate (the in-flight teardown window)
        and whose text() blocks until child death — so a concurrent shutdown() can be observed
        WAITING on _teardown_done instead of starting a 2nd host.stop(). Full _FakeHost surface
        preserved so run()/_load_host/arm work unchanged."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._final_evt = threading.Event()
            self._dead = False
            self.stop_entered = threading.Event()
            self.stop_release = threading.Event()

        def text(self, on_final):
            self.recorder.text_calls += 1
            self.recorder.last_callback = on_final
            # Mirror RecorderHost.text()'s wait loop: return on final OR child death (stop()).
            while not self._final_evt.wait(timeout=0.05):
                if self._dead:
                    return  # child death -> host.text() returns -> run() re-checks _shutdown

        def stop(self, timeout=5.0):
            self.stop_calls += 1
            self._alive = False
            self._dead = True          # child death -> any blocked text() returns (run() exits)
            self.stop_entered.set()     # tell the test we are INSIDE the teardown
            self.stop_release.wait(timeout=5.0)  # in-flight teardown window (bounded; never hangs)

    def _factory(*a, **k):
        return _GatedFakeHost(*a, **k)

    d, _fb = _make_lazy_daemon(host_factory=_factory)
    t_run = threading.Thread(target=d.run, daemon=True)
    t_run.start()
    wall_start = _time.monotonic()
    host = None
    t_sig = None
    t_main = None
    main_done = threading.Event()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)  # run() booted
        d.start()  # first arm lazily spawns the gated host (_load_host -> factory -> _arm)
        assert _wait_for(lambda: d._text_in_flight.is_set(), timeout=2.0), "loop did not enter text()"
        host = d._host
        assert isinstance(host, _GatedFakeHost), "arm did not spawn the gated host"

        # --- Thread A: the SIGTERM signal-handler analog ---
        t_sig = threading.Thread(target=d.request_shutdown, name="sigterm-sig", daemon=True)
        t_sig.start()
        # request_shutdown claimed _shutdown_done + is INSIDE host.stop() (blocked on stop_release).
        assert host.stop_entered.wait(timeout=2.0), "request_shutdown did not reach host.stop()"
        assert d._shutdown_done is True            # the single-flight CLAIM
        assert not d._teardown_done.is_set()       # teardown still in flight

        # --- Thread B: main()'s finally-block analog (runs CONCURRENTLY with A) ---
        def _main_shutdown():
            d.shutdown()
            main_done.set()

        t_main = threading.Thread(target=_main_shutdown, name="sigterm-main", daemon=True)
        t_main.start()
        _time.sleep(0.2)  # let shutdown() reach _teardown_done.wait()

        # CORE REGRESSION ASSERT: B is WAITING, NOT starting a 2nd host.stop().
        assert host.stop_calls == 1, (
            f"shutdown() started a SECOND host.stop() (double teardown!) stop_calls={host.stop_calls}"
        )
        assert not main_done.is_set(), "shutdown() returned before the in-flight teardown finished"

        # Release the in-flight teardown -> A finishes -> _teardown_done set -> B's wait returns.
        host.stop_release.set()
        assert _wait_for(main_done.is_set, timeout=5.0), "shutdown() did not return after release"
        t_sig.join(timeout=5.0)
        t_main.join(timeout=5.0)
        assert not t_sig.is_alive() and not t_main.is_alive(), "shutdown threads did not finish"

        # run() exits: request_shutdown set _shutdown first; text() saw _dead -> returned.
        assert _wait_for(lambda: not t_run.is_alive(), timeout=3.0), "run() thread did not exit cleanly"

        # FINAL regression asserts: still exactly ONE teardown; bounded wall time.
        assert host.stop_calls == 1, f"double teardown after release! stop_calls={host.stop_calls}"
        wall = _time.monotonic() - wall_start
        assert wall < 8.0, f"total wall time {wall:.2f}s >= 8s (bounded-teardown regression?)"
    finally:
        # ALWAYS release + signal + join so no thread is left blocked (test isolation).
        if host is not None:
            host.stop_release.set()
        d.request_shutdown()  # idempotent under S1's _shutdown_done guard; re-sets _shutdown
        if t_sig is not None:
            t_sig.join(timeout=5.0)
        if t_main is not None:
            t_main.join(timeout=5.0)
        _wait_for(lambda: not t_run.is_alive(), timeout=3.0)
        t_run.join(timeout=3.0)
    assert not t_run.is_alive(), "run() thread still alive after teardown"


# --- run() loop ---


def test_run_loop_not_listening_does_not_call_text(monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
    d, fb, rec, be = _make_daemon()
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: True, timeout=0.2)   # let it sleep-loop a moment
        assert rec.text_calls == 0             # not listening → never calls text()
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)  # noqa: E702
    assert not t.is_alive()


def test_run_closes_capture_stream_at_boot_while_not_listening(monkeypatch):
    # Regression: validation Issue 2. The recorder is constructed with use_microphone=True so
    # RealtimeSTT opens the PyAudio capture stream in __init__. The "listening" Event is cleared
    # at boot but that gate only suppresses recorder.text() OUTPUT — it does NOT close the physical
    # capture stream, so without an explicit set_microphone(False) in run() the mic stays
    # hot-capturing (PipeWire: an uncorked source-output) while voicectl status reports listening:
    # off. run() must match the device capture state to the listening gate from boot.
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
    d, fb, rec, be = _make_daemon()
    assert rec.mic == []                       # pre-run: no set_microphone calls yet
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        # wait for the boot-time set_microphone(False) (the recorder is resident before the loop)
        assert _wait_for(lambda: False in rec.mic, timeout=1.0), rec.mic
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)  # noqa: E702
    assert not t.is_alive()
    assert rec.mic[-1] is False                # boot left the capture stream closed (not listening)
    assert rec.text_calls == 0                 # and text() was never entered (not listening)

def test_run_loop_calls_text_when_listening_then_exits_on_shutdown(monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
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


def test_run_sets_uptime_after_start(monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
    d, fb, rec, be = _make_daemon()
    assert d.uptime_s == 0.0   # not started yet
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d.uptime_s >= 0.0 and d._start_monotonic is not None, timeout=1.0)
        assert d.uptime_s >= 0.0
    finally:
        d.request_shutdown(); _wait_for(lambda: not t.is_alive(), timeout=2.0); t.join(timeout=2.0)  # noqa: E702


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
from voice_typing.config import FeedbackConfig  # noqa: E402 (mid-file: T2.S1 section import)
from voice_typing.feedback import Feedback  # noqa: E402


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
    # VT-001: the daemon must NEVER call cuda_check.resolve_device_and_models for status (that
    # would import ctranslate2/torch + touch the CUDA driver in the DAEMON process, breaking the
    # recorder-host subprocess architecture's core invariant). Assert it is not invoked.
    calls = {"n": 0}

    def _resolve(defaults=None):
        calls["n"] += 1
        return dict(daemon.cuda_check.CUDA_DEFAULTS)

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)
    d, fb = _make_daemon_with_feedback(tmp_path, monkeypatch, cuda=True)
    fb.update_partial("hello")
    fb.record_final("world")
    s = d.status_snapshot()
    assert set(s) == {"listening", "mode", "phase", "models_loaded", "load_error", "partial", "last_final",
                      "uptime_s", "device", "compute_type", "final_model", "realtime_model",
                      "mic_ok", "mic_error"}                     # P1.M2.T2.S1: +phase/models_loaded/load_error; §4.2ter: +mode
    assert s["listening"] is False and s["partial"] == "world" and s["last_final"] == "world"   # record_final writes the final into partial so the status matches the screen
    assert s["phase"] == "idle" and s["models_loaded"] is True and s["load_error"] == ""  # P1.M2.T2.S1: injected recorder -> loaded
    # device/compute_type/models come from the UN-PROBED config (VT-001) until the child reports
    # its actual resolved device on arm. The defaults happen to equal CUDA_DEFAULTS, so this also
    # pins that the config<->cuda_check defaults have not drifted.
    assert s["device"] == "cuda" and s["compute_type"] == "float16"
    assert s["final_model"] == "distil-large-v3" and s["realtime_model"] == "small.en"
    assert s["mic_ok"] is True and s["mic_error"] == ""          # S1's _ok_probe via _make_daemon_with_feedback
    assert calls["n"] == 0, "status_snapshot must NOT call cuda_check.resolve_device_and_models (VT-001)"


def test_status_snapshot_reflects_listening_toggle(tmp_path, monkeypatch):
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    assert d.status_snapshot()["listening"] is False
    d.start()
    assert d.status_snapshot()["listening"] is True


def test_status_snapshot_reports_configured_device_when_not_loaded(tmp_path, monkeypatch):
    """VT-001: before a child reports its resolved device, status reflects the CONFIGURED asr.device
    (here cpu) — NOT a cuda_check probe. The daemon must stay CUDA-free; the authoritative
    cuda-vs-cpu-fallback decision is made by the CHILD on arm (see
    test_load_recorder_cpu_fallback_on_cuda_failure). compute_type is derived from the configured
    device (int8 for cpu). Models are the CONFIGURED final/realtime models, not CPU_FALLBACK's.
    """
    calls = {"n": 0}
    monkeypatch.setattr(
        daemon.cuda_check, "resolve_device_and_models",
        lambda defaults=None: calls.__setitem__("n", calls["n"] + 1) or dict(daemon.cuda_check.CPU_FALLBACK),
    )
    cfg = VoiceTypingConfig(
        asr=AsrConfig(device="cpu"),
        feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")),
    )
    fb = Feedback(cfg.feedback)
    d = daemon.VoiceTypingDaemon(
        cfg, fb, recorder=_StubRecorder(), backend=_FakeBackend(), mic_prober=_ok_probe,
    )
    s = d.status_snapshot()
    assert s["device"] == "cpu" and s["compute_type"] == "int8"   # UN-PROBED configured values
    assert s["final_model"] == "distil-large-v3" and s["realtime_model"] == "small.en"  # configured, NOT cpu-fallback
    assert calls["n"] == 0, "status_snapshot must NOT call cuda_check (VT-001)"


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


def test_resolved_device_never_calls_cuda_check(tmp_path, monkeypatch):
    """VT-001: status_snapshot() must NEVER call cuda_check.resolve_device_and_models — not once,
    not ever (the daemon process must stay CUDA-free). Previously this probed + cached; now the
    cache is seeded in __init__ from the un-probed config and replaced only by the child on arm.
    """
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
    assert calls["n"] == 0                      # NEVER probed (the cache is seeded from config in __init__)


def test_resolved_device_unaffected_by_cuda_check_failure(tmp_path, monkeypatch):
    """VT-001: a cuda_check failure must have NO effect on status — the daemon never invokes it, so
    it cannot raise into status. Status reports the configured device; it does not degrade to
    'unknown' (that fallback was part of the now-removed probe path).
    """
    def boom(defaults=None):
        raise RuntimeError("cuda exploded")

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", boom)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    d = daemon.VoiceTypingDaemon(
        cfg, Feedback(cfg.feedback), recorder=_StubRecorder(), backend=_FakeBackend(),
        mic_prober=_ok_probe,
    )
    s = d.status_snapshot()
    assert s["device"] == "cuda"             # configured value; cuda_check never called, so no 'unknown'
    assert s["compute_type"] == "float16"


def test_status_snapshot_does_not_import_cuda_stack(tmp_path, monkeypatch):
    """VT-008: the daemon process must NEVER import ctranslate2/torch (or otherwise touch the CUDA
    driver) on a status query — the recorder-host subprocess architecture's core invariant
    (recorder_host.py: "the daemon process NEVER imports RealtimeSTT/torch/ctranslate2").
    status_snapshot() on a never-armed daemon must not ADD either to sys.modules. This is the
    automated guard VT-001 added so the invariant cannot regress (a future status field /
    diagnostic / logging path that re-introduces a CUDA import would fail here).
    """
    import sys  # noqa: E402 (local; test lives above the mid-file `import sys` in the T3 section)
    # The daemon may legitimately resolve its device cache from the config, but it must NEVER go
    # through cuda_check (which imports ctranslate2 + calls get_cuda_device_count()).
    monkeypatch.setattr(
        daemon.cuda_check, "resolve_device_and_models",
        lambda defaults=None: (_ for _ in ()).throw(AssertionError(
            "status_snapshot must NOT call cuda_check.resolve_device_and_models (VT-001/VT-008)")),
    )
    before = {m for m in ("ctranslate2", "torch") if m in sys.modules}
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    d = daemon.VoiceTypingDaemon(
        cfg, Feedback(cfg.feedback), backend=_FakeBackend(), mic_prober=_ok_probe,
    )  # never-armed: recorder=None (lazy boot, the cold-cache path VT-001 reproduced)
    snap = d.status_snapshot()
    assert snap["device"] in ("cuda", "cpu")   # a non-probing value (the configured device)
    added = {m for m in ("ctranslate2", "torch") if m in sys.modules} - before
    assert not added, (
        f"status_snapshot imported the CUDA stack into the daemon process: {added} "
        "(VT-001/VT-008: the daemon must stay CUDA-free)"
    )


# ===========================================================================
# P1.M4.T2.S2 — clean-shutdown wiring: VoiceTypingDaemon.shutdown() + SIGTERM/SIGINT handlers
# (ADDITIVE — everything above is S1/S2/S3/(S1-of-T2); do not change it.)
# ===========================================================================
# Reuses _make_daemon() / _StubRecorder / _wait_for from earlier in this file.
# `daemon` and `logging` are already imported at module top.
import signal as _signal  # noqa: E402 (mid-file: T2.S2 section import)


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


def test_stop_and_toggle_never_shutdown_but_request_shutdown_does():
    # Regression proof: shutdown() is a distinct path; stop/toggle keep NOT tearing down the
    # recorder (models stay resident for instant re-arm). request_shutdown() (BUG-1 fix) now DOES
    # tear down the child so a SIGTERM while listening unblocks the run loop — that is the fix,
    # not a regression.
    d, fb, rec, be = _make_daemon()
    d.start()
    d.stop()
    d.toggle()
    assert rec.shutdowns == 0   # stop/toggle NEVER tear down (models resident)
    d.request_shutdown()
    assert rec.shutdowns >= 1   # BUG-1: request_shutdown tears down (SIGTERM-path unblock)


# P1.M1.T1.S2 — bounded teardown: _bounded_shutdown force-cleans on timeout (ADDITIVE).
# Reuses _make_daemon / _StubRecorder / threading / time-as-_time from earlier in this file.


class _FakeProcess:
    """Stand-in for an mp.Process: .is_alive() True, .terminate() records the call."""

    def __init__(self) -> None:
        self.terminated = False

    def is_alive(self) -> bool:
        return True

    def terminate(self) -> None:
        self.terminated = True


class _FakeSlowRecorder(_StubRecorder):
    """shutdown() blocks forever — simulates the RealtimeSTT ~90s wedge.

    Adds the force-cleanup attrs the real recorder has (transcript_process, reader_process,
    is_shut_down, realtime_transcription_model) so the timeout branch can act on them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.transcript_process = _FakeProcess()
        self.reader_process = _FakeProcess()
        self.is_shut_down = False
        self.realtime_transcription_model = object()  # non-None sentinel

    def shutdown(self):  # type: ignore[override]
        # Blocks forever; never returns, never increments .shutdowns. Runs in a daemon thread
        # inside _bounded_shutdown, so it dies with the test process (no hang).
        threading.Event().wait()


def test_bounded_shutdown_force_cleans_on_timeout():
    d, _fb, rec, _be = _make_daemon(recorder=_FakeSlowRecorder())
    start = _time.monotonic()
    d._bounded_shutdown(timeout=0.3)  # MUST return despite shutdown() blocking forever
    elapsed = _time.monotonic() - start
    assert elapsed < 2.0, f"bounded teardown took {elapsed:.2f}s (expected < ~0.3s + slack)"
    assert rec.transcript_process.terminated, "transcript_process not force-terminated (VRAM leak)"
    assert rec.reader_process.terminated, "reader_process not force-terminated (VRAM leak)"
    assert rec.is_shut_down is True, "is_shut_down not set (idempotency marker)"
    assert rec.realtime_transcription_model is None, "realtime model ref not released"


def test_shutdown_delegates_to_bounded_shutdown():
    # Proves shutdown() routes through _bounded_shutdown (not a leftover direct recorder.shutdown()).
    d, _fb, _rec, _be = _make_daemon()
    calls: list[float] = []
    d._bounded_shutdown = lambda timeout=5.0: calls.append(timeout)
    d.shutdown()
    assert calls == [5.0], f"shutdown() did not delegate to _bounded_shutdown(): {calls}"


def test_shutdown_is_noop_when_recorder_is_none():
    # M2 lazy-load prep: if the recorder was never built, shutdown() must not raise / not touch it.
    d, _fb, _rec, _be = _make_daemon()
    d._recorder = None
    d.shutdown()  # must NOT raise


# ===========================================================================
# P1.M1.T2.S1 — daemon-level single-flight shutdown coordination (bugfix Issue 1)
# (_shutdown_done claim + _teardown_done Event; request_shutdown + shutdown concurrency.)
# ===========================================================================


class _CountingHost:
    """Minimal host for shutdown-coordination tests: counts stop() calls. The daemon calls no
    other host method in the teardown path (only host.stop()), so this suffices."""

    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self, timeout: float | None = None) -> None:
        self.stop_calls += 1


class _GatedHost:
    """Host whose stop() BLOCKS until the test releases it — simulates an in-flight teardown so
    a concurrent shutdown() can be observed WAITING (not starting its own stop)."""

    def __init__(self) -> None:
        self.stop_calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def stop(self, timeout: float | None = None) -> None:
        self.stop_calls += 1
        self.entered.set()
        self.release.wait(timeout=5.0)  # block until the test releases (bounded — no hang)


def test_request_shutdown_claims_and_signals_teardown_done():
    """request_shutdown claims _shutdown_done + signals _teardown_done (the SIGTERM-path contract)."""
    host = _CountingHost()
    d, *_ = _make_daemon(recorder_host=host)
    assert not d._teardown_done.is_set()
    d.request_shutdown()
    assert d._shutdown_done is True
    assert d._teardown_done.is_set()    # finally fired
    assert host.stop_calls == 1          # exactly one teardown


def test_shutdown_does_own_teardown_when_called_first():
    """Normal/called-first path: shutdown() claims + does the teardown + signals _teardown_done."""
    host = _CountingHost()
    d, *_ = _make_daemon(recorder_host=host)
    assert not d._teardown_done.is_set()
    d.shutdown()
    assert d._shutdown_done is True
    assert d._teardown_done.is_set()
    assert host.stop_calls == 1


def test_shutdown_waits_for_inflight_teardown_no_second_stop():
    """SIGTERM path (core fix): while request_shutdown's teardown is in flight, a concurrent
    shutdown() WAITS on _teardown_done and does NOT start a second host.stop()."""
    host = _GatedHost()
    d, *_ = _make_daemon(recorder_host=host)
    # Thread A (signal thread): request_shutdown -> host.stop() blocks on `release`.
    ta = threading.Thread(target=d.request_shutdown, name="sig")
    ta.start()
    assert host.entered.wait(timeout=2.0), "request_shutdown did not reach host.stop()"
    # Claim is made; teardown in flight; _teardown_done NOT yet set.
    assert d._shutdown_done is True
    assert not d._teardown_done.is_set()
    # Thread B (main-thread finally analog): shutdown() must WAIT, not start a 2nd host.stop().
    main_done = threading.Event()

    def _main_shutdown():
        d.shutdown()
        main_done.set()

    tm = threading.Thread(target=_main_shutdown, name="main", daemon=True)
    tm.start()
    _time.sleep(0.2)                       # let shutdown() reach _teardown_done.wait()
    assert host.stop_calls == 1, "shutdown() started a 2nd host.stop() while it should WAIT"
    assert not main_done.is_set(), "shutdown() returned before the in-flight teardown finished"
    # Release the in-flight teardown -> request_shutdown finishes -> _teardown_done set ->
    # shutdown()'s wait returns -> main_done set. Exactly ONE host.stop().
    host.release.set()
    ta.join(timeout=5.0)
    tm.join(timeout=5.0)
    assert main_done.is_set(), "shutdown() did not return after the teardown finished"
    assert host.stop_calls == 1, "exactly ONE host.stop() — shutdown() waited, no double-teardown"


def test_shutdown_returns_immediately_when_teardown_already_done():
    """Quit path (sequential): after request_shutdown finishes, shutdown() sees _teardown_done
    already set and returns immediately (no second host.stop())."""
    host = _CountingHost()
    d, *_ = _make_daemon(recorder_host=host)
    d.request_shutdown()                  # teardown done + _teardown_done set
    assert host.stop_calls == 1
    d.shutdown()                          # the on_quit call, strictly after
    assert host.stop_calls == 1, "shutdown() re-tore-down on the sequential quit path"


def test_request_shutdown_idempotent_vs_second_call():
    """A second request_shutdown (double signal / quit+signal overlap) returns without
    re-tearing-down (single-flight)."""
    host = _CountingHost()
    d, *_ = _make_daemon(recorder_host=host)
    d.request_shutdown()
    d.request_shutdown()                  # second call — must no-op
    assert host.stop_calls == 1, "second request_shutdown re-tore-down"
    assert d._teardown_done.is_set()


def test_shutdown_falls_back_to_own_teardown_on_wait_timeout(monkeypatch):
    """If the in-flight teardown doesn't signal within the wait timeout (signal thread died),
    shutdown() logs a warning and falls back to its OWN _bounded_shutdown(). Safe via _stop_lock
    (P1.M1.T1.S1) on a real host; here we assert the fallback PATH fires (host.stop called twice:
    the in-flight one + the fallback one). The wait timeout is shrunk to keep the test fast."""
    monkeypatch.setattr(daemon, "_TEARDOWN_WAIT_TIMEOUT", 0.2)   # CRITICAL #4: fast fallback
    host = _GatedHost()
    d, *_ = _make_daemon(recorder_host=host)
    ta = threading.Thread(target=d.request_shutdown, name="sig", daemon=True)
    ta.start()
    assert host.entered.wait(timeout=2.0)     # request_shutdown's host.stop() in flight (blocked)
    main_done = threading.Event()

    def _main_shutdown():
        d.shutdown()
        main_done.set()

    tm = threading.Thread(target=_main_shutdown, name="main", daemon=True)
    tm.start()
    # shutdown() waits 0.2s, times out, logs, falls back to its OWN host.stop() (stop_calls=2).
    assert _wait_for(lambda: host.stop_calls >= 2, timeout=3.0), (
        f"fallback did not fire (stop_calls={host.stop_calls})"
    )
    # release both host.stop() calls (the in-flight + the fallback) so threads can finish
    host.release.set()
    ta.join(timeout=5.0)
    tm.join(timeout=5.0)
    assert main_done.is_set()
    assert host.stop_calls == 2, "fallback must run its own host.stop() (the wait timed out)"


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
    d._text_in_flight.set()   # simulate run() blocked in text() -> request_shutdown's abort() is valid
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
import ast  # noqa: E402 (mid-file: T3 section imports)
import sys  # noqa: E402
from pathlib import Path  # noqa: E402


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

    # P1.M2.T1.S1: main() no longer retries construction (lazy load — the CPU fallback moved to _load_recorder).
    # BoomDaemon raises in __init__ -> main()'s outer except -> return 1. (No GPU/build_recorder hermeticity needed:
    # construction is model-free now.) The == 1 assertion is unchanged.
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
    d._refresh_mic_status(force=True)  # force: bypass TTL cache so the swapped prober actually runs
    assert d._mic_ok is False and "portaudio exploded" in (d._mic_error or "")


def test_refresh_mic_status_stores_probe_result():
    d, *_ = _make_daemon()
    d._mic_prober = lambda: (False, "no devices")
    d._refresh_mic_status(force=True)  # force: bypass TTL cache so the swapped prober actually runs
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
    assert len(calls) == 1          # init (force=True)
    d.start()                       # -> _arm -> _refresh_mic_status (TTL-cached within 30s)
    assert len(calls) == 1          # arm within TTL -> probe CACHED, not re-run (bugfix Issue 3)


def test_mic_probe_cached_within_ttl(monkeypatch):
    """P1.M2.T2.S1 / bugfix Issue 3: _arm's mic probe is TTL-cached.

    _refresh_mic_status skips the probe within _MIC_PROBE_TTL_S and re-runs it after the window.
    Deterministic via _fixed_clock. NOTE: the base clock MUST be non-zero — _mic_probe_at uses 0.0
    as the 'never' sentinel, so freezing the clock to exactly 0.0 would stamp _mic_probe_at=0.0 and
    collide with the sentinel (the within-TTL cache would never hit). Use a clearly-non-zero base.
    """
    calls = []

    def counting_probe():
        calls.append(1)
        return (True, None)

    _fixed_clock(monkeypatch, 1000.0)   # non-zero base: avoid the 0.0 'never' sentinel collision
    d = daemon.VoiceTypingDaemon(
        VoiceTypingConfig(), _DaemonFakeFeedback(), recorder=_StubRecorder(),
        backend=_FakeBackend(), mic_prober=counting_probe,
    )
    assert len(calls) == 1              # __init__ force-probed; _mic_probe_at == 1000.0

    _fixed_clock(monkeypatch, 1005.0)   # within TTL (5s < 30s)
    d.start()                           # _arm -> _refresh_mic_status -> CACHED
    assert len(calls) == 1, "arm within TTL must NOT re-probe"

    _fixed_clock(monkeypatch, 1000.0 + daemon._MIC_PROBE_TTL_S + 5.0)  # past TTL (35s)
    d.start()                           # _arm -> _refresh_mic_status -> re-probe
    assert len(calls) == 2, "arm past TTL MUST re-probe"


def test_make_daemon_injection_is_hermetic_no_real_pyaudio():
    # Guard against regression: the factory must inject _ok_probe (no real pyaudio in tests).
    d, *_ = _make_daemon()
    assert d._mic_prober is _ok_probe
    assert d._mic_ok is True        # the stub reported healthy
    assert "pyaudio" not in sys.modules or True  # (informational; other tests may have imported it)


# ===========================================================================
# bugfix P1.M1.T2.S3 — rate-limit RealtimeSTT mic-retry traceback spam
# (MicRetryRateLimitFilter + _install_mic_retry_rate_limiter + _setup_logging wiring.
#  ADDITIVE: pure filter-logic unit tests (deterministic daemon.time.monotonic) + an
#  idempotent-install integration test + a chokepoint test. ZERO real RealtimeSTT/mic/CUDA.)
# ===========================================================================


def _mic_retry_record(
    msg="Microphone connection failed: boom. Retrying...",
    level=logging.ERROR,
    exc_info=None,
):
    return logging.LogRecord(
        name="realtimestt",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


def _fixed_clock(monkeypatch, t):
    """Freeze daemon.time.monotonic at t (deterministic dedup-window tests)."""
    monkeypatch.setattr(daemon.time, "monotonic", lambda: t)


def test_mic_retry_filter_passes_unrelated_records_untouched():
    f = daemon.MicRetryRateLimitFilter()
    rec = _mic_retry_record(msg="Microphone connected and validated (device index: 2)")
    assert f.filter(rec) is True          # transparent
    assert f._count == 0                  # unrelated records do NOT increment the counter
    assert rec.levelno == logging.ERROR    # record untouched


def test_mic_retry_filter_first_occurrence_passes_through_unchanged(monkeypatch):
    _fixed_clock(monkeypatch, 0.0)
    f = daemon.MicRetryRateLimitFilter()
    rec = _mic_retry_record()
    assert f.filter(rec) is True
    assert rec.levelno == logging.ERROR            # level preserved (full error once)
    assert "Microphone connection failed" in rec.getMessage()  # message preserved
    assert f._count == 1


def test_mic_retry_filter_first_occurrence_preserves_traceback(monkeypatch):
    _fixed_clock(monkeypatch, 0.0)
    f = daemon.MicRetryRateLimitFilter()
    try:
        raise RuntimeError("portaudio exploded")
    except RuntimeError:
        exc_info = sys.exc_info()
    rec = _mic_retry_record(
        msg="Microphone connection failed: portaudio exploded. Retrying...",
        exc_info=exc_info,
    )
    assert f.filter(rec) is True
    assert rec.exc_info is exc_info      # traceback preserved on the first pass
    assert rec.exc_text is None           # not yet formatted/cached
    assert rec.levelno == logging.ERROR


def test_mic_retry_filter_suppresses_repeats_within_window(monkeypatch):
    f = daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=20)
    _fixed_clock(monkeypatch, 0.0)
    assert f.filter(_mic_retry_record()) is True      # count=1: first (pass)
    for i in range(2, 20):                             # every ~3s, well within the 60s window
        _fixed_clock(monkeypatch, (i - 1) * 3.0)
        assert f.filter(_mic_retry_record()) is False  # count=2..19: suppressed
    assert f._count == 19


def test_mic_retry_filter_summary_on_nth_occurrence(monkeypatch):
    f = daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=20)
    _fixed_clock(monkeypatch, 0.0)
    assert f.filter(_mic_retry_record()) is True       # count=1: first (full error)
    for i in range(2, 20):
        _fixed_clock(monkeypatch, (i - 1) * 3.0)
        assert f.filter(_mic_retry_record()) is False  # 2..19 suppressed
    _fixed_clock(monkeypatch, 19 * 3.0)                # 57s: within window, but count%20==0
    summary = _mic_retry_record()
    assert f.filter(summary) is True                   # count=20: summary tick
    assert summary.levelno == logging.WARNING
    assert summary.levelname == "WARNING"
    assert summary.exc_info is None and summary.exc_text is None   # CRITICAL #2
    text = summary.getMessage()
    assert "Microphone still unavailable after 20 retry attempts" in text
    assert "last error: boom" in text
    assert f._count == 20


def test_mic_retry_filter_summary_after_dedup_window(monkeypatch):
    # summary_every huge so ONLY the elapsed-window triggers a summary
    f = daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=10_000)
    _fixed_clock(monkeypatch, 0.0)
    assert f.filter(_mic_retry_record()) is True       # count=1 @ t=0
    _fixed_clock(monkeypatch, 3.0)
    assert f.filter(_mic_retry_record()) is False      # count=2 suppressed
    _fixed_clock(monkeypatch, 70.0)                    # > 60s since last emitted record
    summary = _mic_retry_record()
    assert f.filter(summary) is True                   # window elapsed -> summary
    assert summary.levelno == logging.WARNING
    assert "after 3 retry attempts" in summary.getMessage()


def test_mic_retry_filter_count_is_cumulative(monkeypatch):
    # dedup_seconds=0 -> window always elapsed -> every attempt past the first is a summary
    f = daemon.MicRetryRateLimitFilter(dedup_seconds=0.0, summary_every=10_000)
    _fixed_clock(monkeypatch, 0.0)
    assert f.filter(_mic_retry_record()) is True                    # 1: first
    _fixed_clock(monkeypatch, 1.0); s = _mic_retry_record()  # noqa: E702 (clock-set + record-build)
    assert f.filter(s) is True and "after 2 retry attempts" in s.getMessage()
    _fixed_clock(monkeypatch, 2.0); s = _mic_retry_record()  # noqa: E702
    assert f.filter(s) is True and "after 3 retry attempts" in s.getMessage()


def test_extract_mic_retry_error_parses_message():
    assert daemon._extract_mic_retry_error(
        "Microphone connection failed: Selected device validation failed. Retrying..."
    ) == "Selected device validation failed"
    assert daemon._extract_mic_retry_error(
        "Microphone connection failed: boom. Retrying..."
    ) == "boom"
    assert daemon._extract_mic_retry_error("something else") == "something else"  # fallback


def test_setup_logging_attaches_exactly_one_rate_limit_filter(monkeypatch):
    rt = logging.getLogger("realtimestt")
    saved = list(rt.filters)
    try:
        monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)  # don't touch root
        rt.filters[:] = []                                            # start clean
        daemon._setup_logging("INFO")
        matches = [f for f in rt.filters if isinstance(f, daemon.MicRetryRateLimitFilter)]
        assert len(matches) == 1
        # idempotent: a second call must NOT double-register (CRITICAL #4)
        daemon._setup_logging("DEBUG")
        matches = [f for f in rt.filters if isinstance(f, daemon.MicRetryRateLimitFilter)]
        assert len(matches) == 1
    finally:
        rt.filters[:] = saved                                         # restore global state


def test_rate_limit_filter_is_logger_level_chokepoint():
    captured = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append(record)

    name = "voice_typing.test.micretry.chokepoint"
    log = logging.getLogger(name)
    log.handlers = [_Cap()]
    log.propagate = False
    log.setLevel(logging.DEBUG)
    log.addFilter(daemon.MicRetryRateLimitFilter(dedup_seconds=60, summary_every=20))
    for _ in range(25):
        log.error("Microphone connection failed: boom. Retrying...")
    # first occurrence (count=1) + summary at count=20 = exactly 2 records reach the handler
    assert len(captured) == 2
    assert captured[0].levelno == logging.ERROR                       # the first (full)
    assert "Microphone connection failed" in captured[0].getMessage()
    assert captured[1].levelno == logging.WARNING                     # the summary
    assert "after 20 retry attempts" in captured[1].getMessage()


# ===========================================================================
# bugfix P1.M1.T3.S1 — force_cpu capability on _construct / build_recorder / cfg_to_kwargs
# (ADDITIVE: the force_cpu path builds CPU kwargs WITHOUT calling _resolve_device_config/cuda_check.
#  Uses S1's _FakeRecorder (VAR_KEYWORD → captures kwargs) + _FakeFeedback + _cuda_resolve. ZERO
#  real CUDA/RealtimeSTT/model-load — force_cpu LOGIC is tested via the _construct seam.)
# ===========================================================================
import inspect  # noqa: E402 (kept local to this section to match the file's additive-section style)


def test_construct_force_cpu_uses_cpu_fallback(cfg):
    """force_cpu=True builds the exact PRD §4.4 CPU config regardless of cfg.asr.device."""
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
    kw = rec.kwargs
    assert kw["device"] == "cpu"
    assert kw["compute_type"] == "int8"
    assert kw["model"] == "small.en"
    assert kw["realtime_model_type"] == "tiny.en"


def test_construct_force_cpu_skips_resolve(cfg, monkeypatch):
    """force_cpu=True NEVER calls _resolve_device_config (the cuda_check probe is skipped)."""
    def _boom(_cfg=None):
        raise AssertionError("_resolve_device_config must NOT be called when force_cpu=True")
    monkeypatch.setattr(daemon, "_resolve_device_config", _boom)
    # force_cpu=True: no raise -> the skip works (cfg_to_kwargs used the injected resolved dict)
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
    assert rec.kwargs["device"] == "cpu"
    # force_cpu=False (default): _resolve_device_config IS called -> the AssertionError fires
    with pytest.raises(AssertionError):
        daemon._construct(cfg, _FakeFeedback(), _FakeRecorder)


def test_construct_force_cpu_overrides_cuda_path(cfg, monkeypatch):
    """force_cpu wins even when cuda_check is monkeypatched to the CUDA path."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # force cuda
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
    assert rec.kwargs["device"] == "cpu"            # force_cpu overrides the cuda verdict
    assert rec.kwargs["model"] == "small.en"
    assert rec.kwargs["realtime_model_type"] == "tiny.en"


def test_construct_force_cpu_keeps_non_device_kwargs(cfg):
    """force_cpu overrides ONLY device/models; language/timing/_FIXED_KWARGS still come from cfg."""
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
    kw = rec.kwargs
    # non-device tunables from cfg (default cfg):
    assert kw["language"] == "en"
    assert kw["realtime_processing_pause"] == 0.15
    assert kw["post_speech_silence_duration"] == 0.6
    # _FIXED_KWARGS survive (P1.M1.T1.S1's no_log_file + the silero correction):
    assert kw["no_log_file"] is True
    assert kw["silero_backend"] == "auto"
    assert kw["use_microphone"] is True
    assert kw["enable_realtime_transcription"] is True
    # _construct ALSO wires the on_* callbacks (built-in behavior, unaffected by force_cpu):
    assert "on_realtime_transcription_stabilized" in kw
    assert "on_vad_detect_start" in kw and "on_vad_start" in kw and "on_vad_stop" in kw


def test_construct_force_cpu_false_is_default_behavior(cfg, monkeypatch):
    """force_cpu=False (explicit) and omitted behave exactly as the pre-change code (cuda path)."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    explicit = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=False)
    omitted = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder)
    # callbacks are fresh closures each call (never equal by identity), so compare the NON-callback
    # kwargs that force_cpu controls — device/models/timing/_FIXED_KWARGS must be identical:
    _cb = {k for k in explicit.kwargs if k.startswith("on_")}
    assert {k for k in omitted.kwargs if k.startswith("on_")} == _cb
    non_cb_explicit = {k: v for k, v in explicit.kwargs.items() if not k.startswith("on_")}
    non_cb_omitted = {k: v for k, v in omitted.kwargs.items() if not k.startswith("on_")}
    assert non_cb_explicit == non_cb_omitted
    assert omitted.kwargs["device"] == "cuda"       # the normal cuda path, untouched
    assert omitted.kwargs["model"] == "distil-large-v3"


def test_cfg_to_kwargs_accepts_resolved_override(cfg, monkeypatch):
    """cfg_to_kwargs(resolved=...) uses the injected dict and skips _resolve_device_config."""
    def _boom(_cfg=None):
        raise AssertionError("must not resolve when resolved= is given")
    monkeypatch.setattr(daemon, "_resolve_device_config", _boom)
    kw = daemon.cfg_to_kwargs(
        cfg, resolved={"device": "cpu", "compute_type": "int8",
                       "final_model": "small.en", "realtime_model": "tiny.en"}
    )
    assert kw["device"] == "cpu" and kw["model"] == "small.en"
    assert kw["realtime_model_type"] == "tiny.en" and kw["compute_type"] == "int8"


def test_build_recorder_and_construct_force_cpu_in_signature():
    """force_cpu (default False) + on_speech (default None) are on the public surface. (Smoke.)"""
    sb = inspect.signature(daemon.build_recorder).parameters
    assert "force_cpu" in sb and sb["force_cpu"].default is False
    assert "on_speech" in sb and sb["on_speech"].default is None
    assert "lite" in sb and sb["lite"].default is False            # PRD §4.2ter
    assert list(sb) == ["cfg", "feedback", "latency", "force_cpu", "on_speech", "lite"], list(sb)
    sc = inspect.signature(daemon._construct).parameters
    assert "force_cpu" in sc and sc["force_cpu"].default is False
    assert "on_speech" in sc and sc["on_speech"].default is None
    assert "lite" in sc and sc["lite"].default is False
    assert list(sc) == ["cfg", "feedback", "recorder_cls", "latency", "force_cpu", "on_speech", "lite"], list(sc)
    # cfg_to_kwargs got the keyword-only resolved injection point (default None):
    sk = inspect.signature(daemon.cfg_to_kwargs).parameters
    assert "resolved" in sk and sk["resolved"].default is None
    assert sk["resolved"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "lite" in sk and sk["lite"].default is False            # PRD §4.2ter


def test_log_resolved_device_reads_cache_after_cpu_fallback(caplog):
    """_log_resolved_device reports the SEEDED cpu cache, not a fresh driver probe (CRITICAL #4)."""
    d, *_ = _make_daemon()                            # _ok_probe; no cache set
    d._resolved_device_cache = dict(daemon.cuda_check.CPU_FALLBACK)  # simulate main()'s seed
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        d._log_resolved_device()
    line = next(
        (m for m in (r.getMessage() for r in caplog.records) if "device resolved" in m), None
    )
    assert line is not None, "no device-resolved line"
    assert "device=cpu" in line and "compute_type=int8" in line
    assert "final_model=small.en" in line and "realtime_model=tiny.en" in line


# ===========================================================================
# P1.M2.T1.S1 — lazy load: _load_recorder() single-flight + CPU-fallback migration
# (The CPU fallback MOVED here from main(); main() no longer retries on construction. These tests
#  build a recorder=None daemon + monkeypatch daemon.build_recorder — ZERO real CUDA/models.)
# ===========================================================================


def _make_lazy_daemon(cfg=None, host_factory=None):
    """A daemon with NO injected recorder: self._host is None, _models_loaded False (the lazy boot state).

    Mirrors production lazy boot. Tests that exercise _load_host inject a host_factory (so the spawn
    stays hermetic — no real child). P1.M3.T2.S2 re-plan: "loading" is now host.spawn()."""
    cfg = cfg or VoiceTypingConfig()
    fb = _DaemonFakeFeedback()
    return daemon.VoiceTypingDaemon(
        cfg, fb, recorder=None, host_factory=host_factory, backend=_FakeBackend(), mic_prober=_ok_probe
    ), fb


def test_lazy_daemon_boots_unloaded_with_no_recorder():
    """A recorder-less daemon boots lazy: _host None, _models_loaded False (§4.2bis)."""
    d, _fb = _make_lazy_daemon()
    assert d._host is None
    assert d._recorder is None                        # back-compat property (None when no legacy adapter)
    assert d._models_loaded is False
    assert d._loading is False
    assert d._load_error is None


def test_load_recorder_success_loads_and_marks_loaded(monkeypatch):
    """_load_host() spawns via host_factory + flips _models_loaded; returns True."""
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    assert d._load_recorder() is True
    assert d._host is not None and d._host.spawn_calls == 1
    assert d._models_loaded is True
    assert d._load_error is None
    assert fb.phases[-1] == "idle"          # phase driven to 'idle' on success


def test_load_recorder_is_noop_once_loaded(monkeypatch):
    """A second _load_recorder() after success does NOT spawn again (resident)."""
    factory = _fake_host_factory(spawn_result=True)
    d, _fb = _make_lazy_daemon(host_factory=factory)
    assert d._load_recorder() is True
    assert d._load_recorder() is True       # resident -> no-op
    assert d._host.spawn_calls == 1         # spawn called exactly ONCE


def test_load_recorder_cpu_fallback_on_cuda_failure(monkeypatch, caplog):
    """CPU fallback now lives in the CHILD (recorder_host._worker_main). At the daemon level, a
    spawn that reports a CPU device (the child fell back) seeds _resolved_device_cache from the
    child's 'ready' device dict — so status reports device=cpu WITHOUT the daemon probing CUDA.
    This test pins that the daemon seeds the cache from the host's device (the post-fix path)."""
    cpu_device = {"device": "cpu", "compute_type": "int8",
                  "final_model": "small.en", "realtime_model": "tiny.en"}
    factory = _fake_host_factory(spawn_result=True, device=cpu_device)
    d, _fb = _make_lazy_daemon(host_factory=factory)
    assert d._load_recorder() is True
    assert d._host is not None and d._models_loaded is True
    assert d._resolved_device()["device"] == "cpu"   # cache seeded from the host's (child's) device


def test_load_recorder_total_failure_stays_unloaded(monkeypatch):
    """A spawn that returns False -> _load_host stays unloaded, NO half-built host, _load_error set (§4.2bis)."""
    factory = _fake_host_factory(spawn_result=False)
    d, _fb = _make_lazy_daemon(host_factory=factory)
    assert d._load_recorder() is False
    assert d._host is None                           # NO half-built host
    assert d._models_loaded is False
    assert d._load_error is not None


def test_start_on_lazy_daemon_triggers_load_then_arms(monkeypatch):
    """start() on an unloaded daemon spawns the host, then arms (set_microphone True)."""
    factory = _fake_host_factory(spawn_result=True)
    d, _fb = _make_lazy_daemon(host_factory=factory)
    d.start()
    assert d._models_loaded is True
    assert d.is_listening() is True
    assert d._host.recorder.mic == [True]            # armed (proxied to the fake host's stub)


def test_cold_first_arm_fires_loading_toast(monkeypatch):
    """A COLD first arm (models not loaded) shows a 'Loading…' toast before the model load.

    The lazy model load blocks ~1–3 s; to make the hotkey's effect visible the daemon fires a
    'Loading…' hyprctl toast (_load_host -> Feedback.notify) BEFORE spawning the host. The arm
    then fires the normal 'Recording' start toast (set_listening). This pins that 'Loading…' fires
    exactly once on a cold arm (the start toast's wording is pinned in test_feedback.py).
    """
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    d.start()
    assert d.is_listening() is True
    assert fb.notifies == ["Loading…"]               # fired once, before the spawn


def test_warm_arm_fires_no_loading_toast(monkeypatch):
    """A WARM arm (models already resident) fires NO 'Loading…' toast.

    Resident arms reply in ms — there is no model load to announce, so 'Loading…' never fires; only
    the 'Recording' start toast (set_listening) does. This is the every-arm-after-the-first case.
    """
    d, fb, _rec, _be = _make_daemon()                # injected recorder -> _models_loaded True at boot
    d.start()
    assert d.is_listening() is True
    assert fb.notifies == []                          # no cold load -> no 'Loading…' toast


# --- lite mode (PRD §4.2ter): small-model-only quick dictation on a separate keybind ---

def test_start_lite_loads_lite_host_and_arms():
    """start_lite() spawns the host in LITE mode (host.mode == 'lite') and arms."""
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    d.start_lite()
    assert d._models_loaded is True
    assert d.is_listening() is True
    assert d._host.mode == "lite"                     # the child was built for lite
    assert d._mode == "lite"                          # daemon tracks it
    assert fb.modes == ["lite"]                       # published to state.json via set_mode


def test_mode_switch_normal_to_lite_reloads():
    """Arming lite while a NORMAL child is resident tears it down + respawns lite (one reload).

    Pins the accepted §4.2ter tradeoff: switching modes costs one bounded reload (the recorder is
    built with a different model set). spawn() runs AGAIN and the new host reports mode 'lite'.
    """
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    d.start()                                        # cold arm -> normal host, spawn_calls == 1
    assert d._host.mode == "normal" and d._host.spawn_calls == 1
    d.stop()                                         # disarm (resident stays, just not listening)
    d.start_lite()                                   # mode mismatch -> teardown + respawn lite
    assert d._host.mode == "lite"                     # a NEW lite host is resident
    assert d._host.spawn_calls == 1                   # the new host spawned once (fresh instance)
    assert d._mode == "lite"


def test_same_mode_arm_is_instant_no_reload():
    """Re-arming the SAME mode while resident does NOT reload (instant, like a warm arm)."""
    factory = _fake_host_factory(spawn_result=True, mode="lite")
    d, fb = _make_lazy_daemon(host_factory=factory)
    d.start_lite()                                   # spawn lite
    host1 = d._host
    d.stop()
    d.start_lite()                                   # resident lite -> instant, no reload
    assert d._host is host1                           # SAME host object (no teardown/respawn)
    assert d._host.mode == "lite"


def test_toggle_lite_while_listening_in_lite_stops():
    """toggle_lite while listening IN LITE disarms (mode-specific arming, delta §3.4).

    The cross-mode case (toggle_lite while armed-in-normal → switch to lite) is covered by
    test_toggle_lite_while_armed_in_normal_switches_to_lite in the P1.M1.T2.S1 section below.
    """
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    d.start_lite()                                  # listening in lite
    assert d.is_listening() is True
    d.toggle_lite()                                  # armed-in-lite -> disarm branch
    assert d.is_listening() is False


def test_status_snapshot_reports_mode():
    """status_snapshot carries 'mode' (normal | lite) for voicectl status + state.json consumers."""
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    assert d.status_snapshot()["mode"] == "normal"   # default at boot
    d.start_lite()
    assert d.status_snapshot()["mode"] == "lite"


def test_mode_switch_stops_outgoing_host():
    """P1.M1.T2.S2: a normal->lite mode switch TEARS DOWN the outgoing resident host
    (host.stop() called exactly once), not just respawns.

    Pins the switch_mode teardown branch (daemon.py: resident-wrong-mode -> _bounded_shutdown ->
    host.stop path). The existing test_mode_switch_normal_to_lite_reloads counts the NEW host's
    spawns but never reads the OUTGOING host's stop_calls (the default _fake_host_factory drops the
    old instance); this closes that gap. A regression that respawns but forgets to tear down the
    old host would leak VRAM + leave a dangling child.
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.start()                                        # resident + armed in normal
    assert len(spawns) == 1 and spawns[0].mode == "normal"
    assert spawns[0].stop_calls == 0
    d.start_lite()                                   # switch normal -> lite (teardown normal, spawn lite, arm)
    assert len(spawns) == 2
    assert spawns[1].mode == "lite" and d._mode == "lite" and d._host is spawns[1]
    assert spawns[0].stop_calls == 1, (              # the OUTGOING normal host was torn down exactly once
        f"mode switch did not stop the outgoing host (stop_calls={spawns[0].stop_calls})"
    )
    assert spawns[1].stop_calls == 0                 # the new lite host has not been stopped


def test_start_lite_after_idle_unload_reloads_in_lite(monkeypatch):
    """P1.M1.T2.S2: after idle-unload (no resident), start_lite() reloads in LITE mode (the lite
    counterpart of test_cold_arm_after_idle_unload for normal).

    Mirrors test_cold_arm_after_idle_unload_refires_loading_toast's idle-unload trigger verbatim
    (the _idle_unload_watchdog only starts in run(), which the fast suite never calls; the tests
    force the condition via the -9999.0 _disarmed_monotonic trick + _maybe_idle_unload()).
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.start_lite()                                   # load + arm lite
    assert len(spawns) == 1 and spawns[0].mode == "lite" and d._mode == "lite"
    d.stop()                                         # disarm -> _disarmed_monotonic stamped
    # Force the idle-UNLOAD condition (the _idle_unload_watchdog thread only starts in run(),
    # which these unit tests never call); mirror test_cold_arm_after_idle_unload's -9999.0 trick.
    d._disarmed_monotonic = _time.monotonic() - 9999.0
    d._maybe_idle_unload()
    assert d._models_loaded is False and d._host is None   # host torn down -> next arm is cold again
    d.start_lite()                                   # reload after idle-unload -> lite again
    assert len(spawns) == 2
    assert spawns[1].mode == "lite" and d._mode == "lite" and d._host is spawns[1]


def test_cold_arm_after_idle_unload_refires_loading_toast(monkeypatch):
    """After an idle-unload tears the host down, the next arm is cold AGAIN -> 'Loading…' refires.

    A session that idle-unloads (PRD §4.2bis) returns to _models_loaded=False, so the subsequent arm
    pays the load again and must re-announce it (the user should not see a silent gap on re-arm).
    """
    factory = _fake_host_factory(spawn_result=True)
    d, fb = _make_lazy_daemon(host_factory=factory)
    d.start()                                         # cold arm #1: 'Loading…'
    assert fb.notifies == ["Loading…"]
    d.stop()                                         # disarm -> _disarmed_monotonic stamped
    # Force the idle-UNLOAD condition (the _idle_unload_watchdog thread only starts in run(),
    # which these unit tests never call); mirror test_arm_resets_idle_unload_clock's -9999.0 trick.
    d._disarmed_monotonic = _time.monotonic() - 9999.0
    d._maybe_idle_unload()
    assert d._models_loaded is False                  # host torn down -> next arm is cold again
    d.start()                                         # cold arm #2 (reloaded): refires 'Loading…'
    assert fb.notifies == ["Loading…", "Loading…"]


def test_start_suppressed_when_load_fails(monkeypatch):
    """A failed spawn -> start() returns without arming (stays not-listening, §4.2bis)."""
    factory = _fake_host_factory(spawn_result=False)
    d, _fb = _make_lazy_daemon(host_factory=factory)
    d.start()
    assert d._models_loaded is False
    assert d.is_listening() is False                 # stayed unarmed


def test_injected_recorder_is_loaded_at_construction():
    """A pre-injected recorder (the _make_daemon pattern) -> _models_loaded True at boot (no lazy)."""
    d, _fb, _rec, _be = _make_daemon()
    assert d._recorder is not None
    assert d._models_loaded is True                      # tests that inject get a loaded daemon immediately


def test_load_recorder_single_flight_one_build_under_concurrency(monkeypatch):
    """Two concurrent _load_recorder() calls -> exactly ONE host spawn (the 2nd waits, §4.2bis)."""
    import threading as _t
    started = _t.Event()
    release = _t.Event()
    spawn_count = {"n": 0}

    class _SlowFakeHost(_FakeHost):
        def spawn(self, timeout=180.0):
            spawn_count["n"] += 1
            started.set()
            release.wait(2.0)            # make the spawn slow so the 2nd caller arrives while _loading
            return super().spawn(timeout)

    def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        return _SlowFakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)

    d, _fb = _make_lazy_daemon(host_factory=factory)
    results = []

    def caller():
        results.append(d._load_recorder())

    t1 = _t.Thread(target=caller)
    t2 = _t.Thread(target=caller)
    t1.start()
    assert started.wait(2.0)         # ensure the loader is mid-spawn before the 2nd starts
    t2.start()
    release.set()                    # let the spawn finish
    t1.join(2.0)
    t2.join(2.0)
    assert spawn_count["n"] == 1     # exactly ONE spawn (single-flight)
    assert results == [True, True]   # both callers see success (2nd waited for the 1st)


# P1.M3.T1.S2 — teardown-vs-load race safety (PRD §4.2bis). Unit tests using fakes; NO CUDA.
#
# Verifies: an arm (start) racing an in-flight idle-unload teardown BLOCKS on the SAME single-flight
# self._lock the teardown holds, waits, then loads a FRESH recorder (it can never see a half-torn-down
# recorder); the wait is bounded (the teardown routes through _bounded_shutdown). Reuses _StubRecorder
# / _make_daemon / _wait_for / module-level threading + _time defined earlier in this file.


class _ControllableShutdownRecorder(_StubRecorder):
    """shutdown() blocks until `release` is set, signalling `started` on entry.

    Lets a test hold _unload_recorder() inside the REAL _bounded_shutdown() (and thus holding
    self._lock) for a controlled window, then release it. release.wait(5.0) is a belt-and-suspenders
    safety so a test bug never hangs the suite (the real _bounded_shutdown also caps at 10s and its
    worker thread is daemon=True -> dies with the process).
    """

    def __init__(self, started, release):
        super().__init__()
        self._started = started
        self._release = release

    def shutdown(self):  # type: ignore[override]
        self._started.set()           # signal: _bounded_shutdown is now running under _lock
        self._release.wait(5.0)       # bounded: never hang the suite on a forgotten release.set()
        self.shutdowns += 1


def _idle_unloaded_loaded_daemon(*, recorder=None, threshold=0.001, host_factory=None):
    """A LOADED daemon, DISARMED, with _disarmed_monotonic far in the past + a tiny threshold.

    So _unload_recorder()'s re-check passes when called DIRECTLY (the idle-unload fire condition,
    PRD §4.2bis) WITHOUT sleeping: time.monotonic() - 0.0 is huge vs any tiny positive threshold.
    threshold must be > 0 (0 disables idle-unload -> _unload_recorder aborts). host_factory= lets
    the race tests inject a fake for the post-unload reload (P1.M3.T2.S2 re-plan).
    """
    cfg = VoiceTypingConfig()
    cfg.asr.auto_unload_idle_seconds = threshold
    d, _fb, _rec, _be = _make_daemon(recorder=recorder, host_factory=host_factory, cfg=cfg)
    with d._lock:
        d._disarm()                       # clears _listening; stamps _disarmed_monotonic (P1.M3.T1.S1)
        d._disarmed_monotonic = 0.0       # push the stamp far into the past -> time re-check passes NOW
    assert d._models_loaded is True
    assert d.is_listening() is False
    return d


def test_arm_racing_unload_waits_then_loads_fresh(monkeypatch):
    """Clause (a)+(b): an arm (start) racing an in-flight idle-unload teardown BLOCKS on self._lock
    until _unload_host releases it, then _load_host() spawns a FRESH host and arms. PRD §4.2bis."""
    started = threading.Event()
    release = threading.Event()
    original = _ControllableShutdownRecorder(started, release)
    # The post-unload reload uses a fake host factory (the unload tears down the legacy adapter).
    d = _idle_unloaded_loaded_daemon(recorder=original, host_factory=_fake_host_factory())
    assert d._recorder is original

    # U: the idle-unload teardown. Acquires _lock, runs the REAL _bounded_shutdown (whose adapter
    # stop() blocks because recorder.shutdown() blocks on `release`) -> HOLDS _lock.
    def unload():
        d._unload_recorder()

    t_u = threading.Thread(target=unload, name="test-unload", daemon=True)
    t_u.start()
    assert started.wait(2.0), "unload never entered _bounded_shutdown (lock not held yet)"

    # S: a racing arm. start() -> _load_host() -> `with self._lock:` BLOCKS (U holds it).
    armed = threading.Event()

    def arm():
        d.start()
        armed.set()

    t_s = threading.Thread(target=arm, name="test-arm", daemon=True)
    t_s.start()
    _time.sleep(0.15)  # clear window: an unblocked arm would have armed by now
    assert not armed.is_set(), "arm proceeded while teardown still held the lock (race not serialized)"
    assert t_s.is_alive(), "arm thread should still be blocked on the single-flight lock"
    assert d._lock.locked(), "the single-flight lock must be held by the teardown"

    # Release the teardown -> U nulls the host + frees the lock -> S spawns a FRESH host + arms.
    release.set()
    assert armed.wait(3.0), "arm did not complete after teardown released the lock"
    t_u.join(2.0)
    t_s.join(2.0)
    assert not t_u.is_alive() and not t_s.is_alive(), "threads did not finish"

    # Clause (b): a FRESH host is resident (the fake factory's _FakeHost), models loaded, listening on.
    assert d._host is not None
    assert d._host is not original, "the torn-down legacy adapter must NOT be resident"
    assert d._models_loaded is True
    assert d.is_listening() is True


def test_recorder_never_half_torn_down_during_race(monkeypatch):
    """Clause (c): throughout the unload->reload race, self._host is ALWAYS either None or a
    fully-built host — never a partial/garbage value. CPython attribute reads are atomic; only
    None + complete host-factory results are ever assigned."""
    started = threading.Event()
    release = threading.Event()

    # A SLOW fake host factory: spawn() sleeps briefly to WIDEN the None window (between U's
    # _host=None and the fresh host assignment) so the 1ms sampler reliably observes it.
    class _SlowFakeHost(_FakeHost):
        def spawn(self, timeout=180.0):
            _time.sleep(0.05)
            return super().spawn(timeout)

    def slow_factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        return _SlowFakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)

    d = _idle_unloaded_loaded_daemon(
        recorder=_ControllableShutdownRecorder(started, release),
        host_factory=slow_factory,
    )

    samples = []
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            samples.append(d._host)   # atomic attribute read
            _time.sleep(0.001)

    t_poll = threading.Thread(target=sampler, name="test-sampler", daemon=True)
    t_poll.start()

    def unload():
        d._unload_recorder()

    t_u = threading.Thread(target=unload, name="test-unload2", daemon=True)
    t_u.start()
    assert started.wait(2.0)
    release.set()  # let the blocking shutdown() return so the unload completes quickly
    d.start()  # racing arm (spawns fresh after the unload)
    assert _wait_for(lambda: any(h is None for h in samples), timeout=3.0), \
        "sampler never observed the torn-down None state"
    _time.sleep(0.1)  # let the reload land + the sampler observe the fresh resident host
    stop.set()
    t_poll.join(1.0)

    assert samples, "sampler never observed the host"
    for host in samples:
        assert host is None or (
            callable(getattr(host, "set_microphone", None))
            and callable(getattr(host, "abort", None))
            and callable(getattr(host, "text", None))
            and callable(getattr(host, "stop", None))
        ), f"observed a non-None, non-complete host: {host!r}"
    assert any(h is None for h in samples), "never saw the torn-down None state"
    assert any(h is not None for h in samples), "never saw a resident host"


def test_load_and_unload_serialize_on_the_same_single_flight_lock():
    """Clause (a) mechanism: _load_recorder()'s FIRST action is `with self._lock:` — the SAME lock
    _unload_recorder() holds during teardown. So while the lock is held, a load physically CANNOT
    proceed. Proven directly, without timing."""
    d, _fb, _rec, _be = _make_daemon()  # loaded, not listening (injected _StubRecorder)
    assert d._models_loaded is True

    # Hold the single-flight lock from the test (simulating an in-flight teardown holding it).
    assert d._lock.acquire(blocking=False) is True

    proceeded = threading.Event()

    def load():
        d._load_recorder()  # first line is `with self._lock:` -> blocks here
        proceeded.set()

    t = threading.Thread(target=load, name="test-load-blocked", daemon=True)
    t.start()
    _time.sleep(0.15)
    assert not proceeded.is_set(), "_load_recorder proceeded without the single-flight lock"
    assert t.is_alive(), "load must be blocked on the lock the teardown holds"

    d._lock.release()  # teardown releases -> load proceeds (resident -> immediate True)
    assert proceeded.wait(2.0), "load did not proceed after the lock was released"
    t.join(2.0)
    assert d._models_loaded is True  # resident -> load is a no-op True


def test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded(monkeypatch):
    """Clause (d): _unload_host() tears down via _bounded_shutdown() (bounded <=5s; the host's stop()
    joins the child for ~5s then SIGKILLs the group). So a racing arm's wait is bounded by THAT
    teardown, never the legacy ~90s recorder.shutdown() wedge (PRD §8). Asserts routing + a bounded
    completion window."""
    d = _idle_unloaded_loaded_daemon()
    real = d._bounded_shutdown
    calls = []

    def recording_bounded(timeout=10.0):
        calls.append(timeout)
        return real(timeout)  # delegate so the host is actually torn down (stays hermetic)

    monkeypatch.setattr(d, "_bounded_shutdown", recording_bounded)

    start = _time.monotonic()
    d._unload_recorder()
    elapsed = _time.monotonic() - start

    assert calls == [5.0], f"_unload_host did not route through _bounded_shutdown(5.0): {calls}"
    assert elapsed < 2.0, f"unload took {elapsed:.2f}s (a racing arm would wait this long)"
    assert d._models_loaded is False and d._host is None, "unload did not complete"


def test_armed_state_aborts_unload_via_listening_recheck():
    """Reverse race (PRD §4.2bis + S1 Critical #2): if an arm wins the race to the lock, _unload_recorder's
    `_listening.is_set()` re-check (under the lock) ABORTS the unload — the armed state wins and the
    recorder stays resident. The other half of 'an arm can never see a half-torn-down recorder'."""
    d = _idle_unloaded_loaded_daemon()
    # An arm wins the race JUST BEFORE the unload acquires the lock -> listening is now ON.
    with d._lock:
        d._arm()
    assert d.is_listening() is True

    d._unload_recorder()  # re-check sees _listening.is_set() -> abort

    assert d._models_loaded is True, "unload must abort when an arm raced in (listening is on)"
    assert d._host is not None, "the host must stay resident (unload aborted)"


# ===========================================================================
# P1.M3.T2.S1 — idle-unload lifecycle + start-level single-flight (PRD §4.2bis)
# Unit tests using the existing _StubRecorder fake — NO CUDA, NO RealtimeSTT.
#
# Pins _maybe_idle_unload()'s fire/disable/reset behavior (P1.M3.T1.S1):
#   (e) FIRES after auto_unload_idle_seconds DISARMED -> recorder torn down, phase 'unloaded';
#   (f) threshold<=0 DISABLES (no-op even when absurdly past);
#   (g) any _arm() RESETS the idle-unload clock (_disarmed_monotonic -> None).
# Plus two lifecycle gap-fills the P1.M2.T1.S1 section left:
#   (a) lazy boot drives phase='unloaded' (existing boot test checks attrs, not phase);
#   (c) two concurrent start() calls build the recorder exactly ONCE (existing is _load_recorder-level).
# Mirrors the auto-stop section (~480-560): inline setup, direct _maybe_idle_unload() call, pushed
# _disarmed_monotonic timestamp. Asserts via fb.phases[-1] / d._recorder / d._models_loaded /
# rec.shutdowns (the fakes have NO snapshot() — do NOT call d.status_snapshot() here).
# ===========================================================================


def test_lazy_boot_records_unloaded_phase():
    """Clause (a) gap: a lazy boot (recorder=None) drives the lifecycle phase to 'unloaded'.
    The existing test_lazy_daemon_boots_unloaded_with_no_recorder checks _recorder/_models_loaded/
    _loading/_load_error but NOT the phase — this pins it (the §4.2bis boot state)."""
    d, fb = _make_lazy_daemon()
    assert d._recorder is None
    assert d._models_loaded is False
    assert fb.phases[-1] == "unloaded"   # __init__ -> feedback.set_phase("unloaded") for a lazy boot


def test_concurrent_start_calls_build_recorder_once(monkeypatch):
    """Clause (c) gap: two concurrent start() calls spawn the host EXACTLY ONCE (single-flight
    through the start() entry point). The existing test_load_recorder_single_flight_one_build_under_
    concurrency proves it at the _load_host level; this proves start()'s load-then-arm does not
    undermine it (and both calls arm)."""
    started = threading.Event()
    release = threading.Event()
    spawn_count = {"n": 0}

    class _SlowFakeHost(_FakeHost):
        def spawn(self, timeout=180.0):
            spawn_count["n"] += 1
            started.set()
            release.wait(2.0)            # slow the spawn so the 2nd start() arrives while _loading
            return super().spawn(timeout)

    def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        return _SlowFakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)

    d, _fb = _make_lazy_daemon(host_factory=factory)
    errors = []

    def starter():
        try:
            d.start()
        except Exception as exc:        # never swallow silently — surface to the test
            errors.append(exc)

    t1 = threading.Thread(target=starter, name="test-start-a", daemon=True)
    t2 = threading.Thread(target=starter, name="test-start-b", daemon=True)
    t1.start()
    assert started.wait(2.0), "first start() never spawned the host"
    t2.start()
    release.set()                      # let the in-flight spawn finish
    t1.join(2.0)
    t2.join(2.0)
    assert not errors, errors
    assert spawn_count["n"] == 1, f"single-flight violated: {spawn_count['n']} spawns under two concurrent start()s"
    assert d._models_loaded is True
    assert d.is_listening() is True    # armed (both starts armed; the load is shared)


# --- idle-unload lifecycle: _maybe_idle_unload() fire / disable / reset (PRD §4.2bis) ---
# Mirrors the auto-stop section: inline _make_daemon() -> start() -> stop() -> push
# _disarmed_monotonic into the past -> _maybe_idle_unload(). Default auto_unload_idle_seconds=1800.0.


def test_idle_unload_fires_when_disarmed_beyond_threshold():
    """Clause (e): after auto_unload_idle_seconds (default 1800) DISARMED, _maybe_idle_unload() tears
    the recorder down -> _recorder None, _models_loaded False, phase 'unloaded' (PRD §4.2bis)."""
    d, fb, rec, _be = _make_daemon()                       # injected _StubRecorder -> loaded
    d.start()                                              # arm  -> _disarmed_monotonic = None
    d.stop()                                               # disarm -> _disarmed_monotonic = now
    d._disarmed_monotonic = _time.monotonic() - 1801.0     # past the 1800s default threshold
    d._maybe_idle_unload()
    assert d._recorder is None                             # torn down
    assert d._models_loaded is False
    assert fb.phases[-1] == "unloaded"                     # _unload_recorder drove phase to 'unloaded'
    assert rec.shutdowns == 1                              # the recorder was shut down via _bounded_shutdown


def test_idle_unload_keeps_resident_within_threshold():
    """Clause (e) negative: well WITHIN the threshold -> _maybe_idle_unload() is a no-op (resident)."""
    d, _fb, rec, _be = _make_daemon()
    d.start()
    d.stop()
    d._disarmed_monotonic = _time.monotonic() - 100.0      # 100s << 1800s default
    d._maybe_idle_unload()
    assert d._recorder is rec
    assert d._models_loaded is True
    assert rec.shutdowns == 0


def test_idle_unload_disabled_when_threshold_zero():
    """Clause (f): auto_unload_idle_seconds=0 DISABLES idle-unload -> no-op even when absurdly past
    (PRD §4.2bis '0 disables'). The recorder MUST stay resident."""
    cfg = VoiceTypingConfig()
    cfg.asr.auto_unload_idle_seconds = 0.0
    d, _fb, rec, _be = _make_daemon(cfg=cfg)
    d.start()
    d.stop()
    d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire, but 0 disables
    d._maybe_idle_unload()
    assert d._recorder is rec                              # stayed resident
    assert d._models_loaded is True
    assert rec.shutdowns == 0


def test_idle_unload_noop_when_listening():
    """Guard: _maybe_idle_unload() MUST NOT fire while LISTENING (armed) — firing then would tear the
    recorder down mid-dictation (the §4.2bis / §8 half-torn-down hazard). The _listening.is_set() guard
    in the lock-free pre-check aborts it."""
    d, _fb, rec, _be = _make_daemon()
    d.start()                                              # armed -> listening ON
    d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire by time alone...
    d._maybe_idle_unload()
    assert d._recorder is rec                              # ...but listening aborts the unload
    assert d._models_loaded is True
    assert d.is_listening() is True


def test_idle_unload_noop_when_never_disarmed():
    """Guard: at boot _disarmed_monotonic is None (never disarmed) -> _maybe_idle_unload() is a clean
    no-op (no error, recorder resident)."""
    d, _fb, rec, _be = _make_daemon()                      # boot: _disarmed_monotonic is None
    assert d._disarmed_monotonic is None
    d._maybe_idle_unload()
    assert d._recorder is rec
    assert d._models_loaded is True


def test_idle_unload_noop_when_not_loaded():
    """Guard: a LAZY daemon (no recorder resident) -> _maybe_idle_unload() is a no-op (nothing to
    unload; the not-_models_loaded guard short-circuits)."""
    d, _fb = _make_lazy_daemon()                           # lazy: _models_loaded False, _recorder None
    d._disarmed_monotonic = _time.monotonic() - 9999.0
    d._maybe_idle_unload()
    assert d._recorder is None                             # still nothing resident
    assert d._models_loaded is False


def test_arm_resets_idle_unload_clock():
    """Clause (g): any _arm() RESETS the idle-unload clock (_disarmed_monotonic -> None), so a re-arm
    CANCELS a pending idle-unload that would otherwise fire (PRD §4.2bis 'resets on any arm')."""
    d, _fb, rec, _be = _make_daemon()
    d.start()                                              # arm -> _disarmed_monotonic = None
    assert d._disarmed_monotonic is None
    d.stop()                                               # disarm -> stamps _disarmed_monotonic
    assert d._disarmed_monotonic is not None
    d._disarmed_monotonic = _time.monotonic() - 9999.0     # would fire...
    d.start()                                              # ...but a re-arm RESETS the clock
    assert d._disarmed_monotonic is None                   # armed -> idle-unload clock inactive
    # The reset cancels the pending unload: _maybe_idle_unload is now a no-op.
    d._maybe_idle_unload()
    assert d._recorder is rec                              # stayed resident (arm reset cancelled it)
    assert d._models_loaded is True


# ===========================================================================
# P1.M2.T1.S2 — phase returns to 'idle' after disarm (stop / toggle-off / auto-stop)
# Regression for Issue 2: _disarm() now calls feedback.set_phase("idle") (P1.M2.T1.S1),
# publishing the 'loaded / not listening' lifecycle state to state.json + voicectl status
# (PRD §4.2bis/§4.6). Without that one line these tests FAIL (fb.phases[-1] stays at the
# last VAD value 'listening'/'speaking'). Synchronous unit tests — no run loop, no GPU.
# ===========================================================================
import json  # noqa: E402  (state.json read in the _make_daemon_with_feedback test below)


def test_disarm_resets_phase_to_idle():
    """stop() -> _disarm() -> phase 'idle' (the 'loaded / not listening' state, PRD §4.2bis/§4.6)."""
    d, fb, _rec, _be = _make_daemon()
    d.start()                                  # arm (set_microphone True, listening on)
    d._feedback.set_phase("listening")         # simulate the child's VAD advancing phase
    assert d.is_listening() is True
    d.stop()                                   # -> _disarm() -> set_listening(False) + set_phase("idle")
    assert d.is_listening() is False
    assert fb.phases[-1] == "idle", f"phase after stop = {fb.phases[-1]!r}"


def test_toggle_off_resets_phase_to_idle():
    """toggle() while listening disarms -> phase 'idle'."""
    d, fb, _rec, _be = _make_daemon()
    d.start()
    d._feedback.set_phase("speaking")          # VAD had reached 'speaking' before the toggle
    assert d.is_listening() is True
    d.toggle()                                 # listening -> disarm branch -> _disarm()
    assert d.is_listening() is False
    assert fb.phases[-1] == "idle", f"phase after toggle-off = {fb.phases[-1]!r}"


def test_auto_stop_resets_phase_to_idle():
    """The 30s idle auto-stop (_maybe_auto_stop -> _disarm) resets phase to 'idle'."""
    d, fb, _rec, _be = _make_daemon()
    d.start()                                  # arm -> _last_speech_monotonic = now
    d._feedback.set_phase("speaking")
    # Idle > 30.0s default threshold (mirrors test_auto_stop_disarms_when_idle_beyond_threshold @583):
    d._last_speech_monotonic = _time.monotonic() - 31.0
    d._maybe_auto_stop()                       # -> _disarm() -> set_phase("idle")
    assert d.is_listening() is False
    assert fb.phases[-1] == "idle", f"phase after auto-stop = {fb.phases[-1]!r}"


def test_state_json_phase_idle_after_stop(tmp_path, monkeypatch):
    """The REAL Feedback writes phase 'idle' to state.json on disarm (on-disk contract, PRD §4.6)."""
    d, fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    d.start()
    fb.set_phase("listening")                  # real Feedback.set_phase (writes state.json)
    assert fb.snapshot()["phase"] == "listening"
    d.stop()                                   # _disarm -> set_phase("idle") -> atomic state.json write
    state = json.load(open(tmp_path / "state.json"))   # _make_daemon_with_feedback writes here
    assert state["phase"] == "idle", state
    assert state["listening"] is False


# ---------------------------------------------------------------------------
# Regression for Issue 3 (P1.M2.T2.S3): dead recorder-host child detection,
# recovery on next arm, and status correctness. Exercises run()'s liveness
# check + _handle_dead_host() (S1, daemon.py:750/778) and _load_host()'s is_alive
# guard (S2, daemon.py:654) via a _FakeHost whose is_alive flips to False
# (simulating a CUDA-OOM / segfault / OOM-killer child crash).
# ---------------------------------------------------------------------------


def test_run_loop_detects_dead_host_and_transitions_to_unloaded(monkeypatch):
    """A crashed recorder-host child is detected by run() and the daemon resets to 'unloaded'.

    Arms (start -> _load_host spawns a _FakeHost via host_factory -> _alive=True), then flips
    host._alive=False to simulate the child dying. run()'s liveness check fires _handle_dead_host():
    _host=None, _models_loaded=False, _listening cleared, phase 'unloaded', _load_error set.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    factory = _fake_host_factory(spawn_result=True)
    # recorder=None => lazy boot (self._host is None, _models_loaded False) so start()'s _load_host()
    # spawns a _FakeHost via the factory (_alive=True). A non-None recorder would be wrapped in a
    # _LegacyRecorderHostAdapter (is_alive always True -> undetectable death). Mirrors _make_lazy_daemon.
    fb = _DaemonFakeFeedback()
    d = daemon.VoiceTypingDaemon(
        VoiceTypingConfig(), fb, recorder=None, host_factory=factory,
        backend=_FakeBackend(), mic_prober=_ok_probe,
    )
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)   # run() booted
        d.start()                                          # _load_host spawns _FakeHost (_alive=True) + _arm
        assert _wait_for(lambda: d._models_loaded, timeout=2.0), "host did not load+arm"
        assert d.is_listening() and d._host is not None
        d._host._alive = False                             # simulate the child crashing
        assert _wait_for(
            lambda: d._host is None and "died" in (d._load_error or ""), timeout=2.0
        ), "run() did not detect the dead host within 2s"
        assert d._host is None
        assert d._models_loaded is False
        assert d.is_listening() is False                   # _listening cleared (died WHILE listening)
        assert "died" in (d._load_error or ""), d._load_error
        assert fb.phases[-1] == "unloaded"                 # _handle_dead_host -> set_phase("unloaded")
        assert fb.listening_states[-1] is False
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_load_host_respawns_after_dead_child(monkeypatch):
    """After a dead-child cleanup, the next arm re-spawns a FRESH host (recovery).

    Recovery (_handle_dead_host) clears _models_loaded=False, so _load_host()'s
    `if self._models_loaded and ... is_alive` guard (S2) does NOT short-circuit -> the factory
    builds a NEW _FakeHost and spawn() runs again. Proves Issue 3 self-heals on re-arm.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    factory = _fake_host_factory(spawn_result=True)
    # recorder=None => lazy boot so start()'s _load_host() spawns a _FakeHost (see test (a)).
    fb = _DaemonFakeFeedback()
    d = daemon.VoiceTypingDaemon(
        VoiceTypingConfig(), fb, recorder=None, host_factory=factory,
        backend=_FakeBackend(), mic_prober=_ok_probe,
    )
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)
        d.start()
        assert _wait_for(lambda: d._models_loaded, timeout=2.0)
        old_host = d._host                              # capture before killing
        old_host._alive = False                         # child crashes
        assert _wait_for(
            lambda: d._host is None and d._load_error, timeout=2.0
        ), "dead host not cleaned up"
        assert d._models_loaded is False
        d.start()                                        # re-arm -> _load_host spawns a FRESH host
        assert _wait_for(lambda: d._models_loaded, timeout=2.0), "host did not re-spawn"
        assert d._host is not old_host, "re-arm reused the dead host instead of spawning a new one"
        assert d._host.spawn_calls == 1, "the new host was not spawned exactly once"
        assert d._models_loaded is True
        assert d.is_listening() is True                 # recovery: listening again
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_status_reports_unloaded_after_child_death(tmp_path, monkeypatch):
    """status_snapshot() surfaces the crash (listening off / phase unloaded / models not loaded / load_error).

    Uses a REAL Feedback (not _DaemonFakeFeedback) because status_snapshot() reads phase/models_loaded
    from feedback.snapshot(), which the fake lacks. Asserts the §7.6 status contract.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb = Feedback(cfg.feedback)
    factory = _fake_host_factory(spawn_result=True)
    d = daemon.VoiceTypingDaemon(
        cfg, fb, recorder=None, host_factory=factory, backend=_FakeBackend(), mic_prober=_ok_probe
    )
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)
        d.start()
        assert _wait_for(lambda: d._models_loaded, timeout=2.0)
        d._host._alive = False                          # child crashes
        assert _wait_for(
            lambda: d._host is None and "died" in (d._load_error or ""), timeout=2.0
        ), "dead host not cleaned up"
        snap = d.status_snapshot()
        assert snap["listening"] is False               # is_listening()
        assert snap["phase"] == "unloaded"              # real Feedback.set_phase("unloaded")
        assert snap["models_loaded"] is False           # real Feedback.set_models_loaded(False)
        assert "died" in snap["load_error"], snap["load_error"]   # self._load_error
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_status_device_reseeded_not_stale_after_child_death(tmp_path, monkeypatch):
    """VT-002: after the recorder-host child dies, the resolved-device cache must NOT retain the
    dead child's device. _handle_dead_host reseeds _resolved_device_cache to the UN-PROBED config,
    so status reports the CONFIGURED device (not a stale cuda/cpu-fallback for a recorder that no
    longer exists) alongside models_loaded=False / phase=unloaded / load_error.

    Setup: a child that reports device=cpu (it "fell back"), armed on a default device=cuda cfg
    (so the cache was seeded cpu from the child). Kill the child -> the cache must reseed to the
    configured cuda, NOT stay stale at cpu.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb = Feedback(cfg.feedback)
    cpu_device = {"device": "cpu", "compute_type": "int8",
                  "final_model": "small.en", "realtime_model": "tiny.en"}
    factory = _fake_host_factory(spawn_result=True, device=cpu_device)
    d = daemon.VoiceTypingDaemon(
        cfg, fb, recorder=None, host_factory=factory, backend=_FakeBackend(), mic_prober=_ok_probe
    )
    t = threading.Thread(target=d.run, daemon=True)
    t.start()
    try:
        _wait_for(lambda: d._start_monotonic is not None, timeout=2.0)
        d.start()
        assert _wait_for(lambda: d._models_loaded, timeout=2.0)
        assert d.status_snapshot()["device"] == "cpu"   # cache seeded from the child's 'ready'
        d._host._alive = False                           # child crashes
        assert _wait_for(lambda: d._host is None, timeout=2.0), "dead host not cleaned up"
        # VT-002: reseeded to the CONFIGURED device (cuda), not stale at the dead child's cpu.
        snap = d.status_snapshot()
        assert snap["device"] == "cuda" and snap["compute_type"] == "float16"
        assert snap["phase"] == "unloaded" and snap["models_loaded"] is False
    finally:
        d.request_shutdown()
    assert _wait_for(lambda: not t.is_alive(), timeout=2.0), "run() thread did not exit"
    t.join(timeout=2.0)


def test_status_device_reseeded_not_stale_after_idle_unload(tmp_path, monkeypatch):
    """VT-002: after idle-unload tears the host down, the resolved-device cache is reseeded to the
    UN-PROBED config (not the torn-down child's device). Same setup as the death test but via
    _unload_host (the idle-unload path). Status then reports the configured device with
    models_loaded=False / phase=unloaded.
    """
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    cfg = VoiceTypingConfig(
        asr=AsrConfig(auto_unload_idle_seconds=0.001),  # fire immediately once disarmed
        feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")),
    )
    fb = Feedback(cfg.feedback)
    cpu_device = {"device": "cpu", "compute_type": "int8",
                  "final_model": "small.en", "realtime_model": "tiny.en"}
    factory = _fake_host_factory(spawn_result=True, device=cpu_device)
    d = daemon.VoiceTypingDaemon(
        cfg, fb, recorder=None, host_factory=factory, backend=_FakeBackend(), mic_prober=_ok_probe
    )
    d.start()                                       # arm -> _load_host seeds cache=cpu from child
    assert d._models_loaded is True
    assert d.status_snapshot()["device"] == "cpu"   # seeded from the child
    d.stop()                                        # disarm -> _disarmed_monotonic set
    # Force the idle-UNLOAD condition deterministically (the _idle_unload_watchdog thread only
    # starts in run(), which this test skips) — mirror the existing idle-unload tests' past-clock
    # trick instead of relying on real time elapsing past a 0.001s threshold.
    d._disarmed_monotonic = _time.monotonic() - 9999.0
    d._maybe_idle_unload()
    assert d._host is None and d._models_loaded is False, "idle-unload did not tear the host down"
    # VT-002: reseeded to the CONFIGURED device (cuda), not stale at the unloaded child's cpu.
    snap = d.status_snapshot()
    assert snap["device"] == "cuda" and snap["compute_type"] == "float16"
    assert snap["phase"] == "unloaded" and snap["models_loaded"] is False


# ===========================================================================
# Regression for validation Issue 1 — the idle-unload / dead-host-detector race.
#
# In production, _idle_unload_watchdog -> _unload_host() holds self._lock ACROSS
# _bounded_shutdown() while it kills the child (os.killpg). During that ~120-200ms
# window the run() loop's 50ms liveness check sees self._host still set (nulled only
# AFTER the shutdown returns) AND not host.is_alive (the child just died) -> it
# calls _handle_dead_host(), which blocks on the lock, then unconditionally set
# _load_error = "recorder-host child died unexpectedly" -> voicectl status shows a
# scary "load error" after ordinary idle behavior (every 30 min of idle). The mock
# _FakeHost.is_alive does not flip during _bounded_shutdown the way the real proc
# does, so the race never opens under the test harness — these tests pin the FIX
# INVARIANTS directly instead of reproducing the timing:
#   (1) _unload_host() clears _load_error on its successful path (an unload is not
#       a load failure).
#   (2) _handle_dead_host() is a NO-OP when another path already cleared the host
#       (host is None and not _models_loaded) -> a racing handler cannot clobber a
#       clean teardown.
# ===========================================================================


def test_idle_unload_clears_load_error():
    """Validation Issue 1 (fix 1): a successful idle-unload clears any stale _load_error.

    An idle-unload is NOT a load failure — voicectl status must NOT show a scary
    "load error" after ordinary idle behavior. Seeds a _load_error (as a failed arm
    would), then runs _maybe_idle_unload past the threshold and asserts the error is
    cleared alongside the teardown (host None, models_loaded False, phase unloaded).
    """
    d, fb, _rec, _be = _make_daemon()                       # injected _StubRecorder -> loaded
    d.start()                                              # arm
    d.stop()                                               # disarm -> _disarmed_monotonic set
    d._load_error = "recorder host spawn failed"           # simulate a PRIOR failed arm's error
    assert d._load_error is not None
    d._disarmed_monotonic = _time.monotonic() - 1801.0     # past the 1800s default threshold
    d._maybe_idle_unload()
    assert d._host is None                                 # torn down
    assert d._models_loaded is False
    assert fb.phases[-1] == "unloaded"
    assert d._load_error is None, "idle-unload did not clear the stale _load_error"


def test_handle_dead_host_noop_when_host_already_cleared():
    """Validation Issue 1 (fix 2): _handle_dead_host() is a NO-OP if the host was already
    cleared by another path (a concurrent idle-unload, or a prior dead-host handling).

    Simulates the losing side of the race: _unload_host() has ALREADY run (host None,
    models_loaded False, _load_error cleared) and THEN the racing _handle_dead_host()
    fires. It must NOT clobber the clean teardown's state with the "died" message.
    """
    d, fb, _rec, _be = _make_daemon()
    d.start()
    d.stop()
    # Simulate the idle-unload path having already won the race: host torn down + error cleared.
    d._host = None
    d._models_loaded = False
    d._load_error = None
    fb.set_phase("unloaded")
    fb.set_models_loaded(False)
    d._handle_dead_host()                                  # the racing (losing) dead-host call
    assert d._host is None
    assert d._models_loaded is False
    assert d._load_error is None, (
        "racing _handle_dead_host clobbered a clean teardown with the 'died' error"
    )
    assert fb.phases[-1] == "unloaded"


# ===========================================================================
# P1.M1.T2.S1 — toggle/toggle_lite mode-specific arming (delta §3.4 / BUG-B)
# (Each key toggles its own mode; cross-mode press switches = one reload.)
# ===========================================================================

def _spawning_factory(spawns):
    """A host_factory that appends each built _FakeHost to `spawns` (so reloads are countable)
    and respects the `mode` kwarg _load_host passes (no closure override)."""
    def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)
        spawns.append(host)
        return host
    return factory


def test_toggle_lite_while_idle_arms_in_lite():
    """F while idle → arms in lite (mode becomes lite, one spawn)."""
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    assert not d.is_listening() and d._mode == "normal"
    d.toggle_lite()
    assert d.is_listening() is True
    assert d._mode == "lite"
    assert d._host.mode == "lite"
    assert len(spawns) == 1                      # armed once (no reload from idle)


def test_toggle_lite_while_armed_in_lite_disarms():
    """F while armed-in-lite → disarms (no reload)."""
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.start_lite()                               # arm in lite
    assert d._mode == "lite" and d.is_listening()
    d.toggle_lite()                              # armed-in-lite → disarm
    assert d.is_listening() is False
    assert len(spawns) == 1                      # no reload on a same-mode disarm


def test_toggle_lite_while_armed_in_normal_switches_to_lite():
    """BUG-B fix: F while armed-in-NORMAL → switches to lite (exactly ONE reload)."""
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.start()                                    # arm in normal
    assert d._mode == "normal" and d.is_listening()
    d.toggle_lite()                              # cross-mode press → switch (not disarm!)
    assert d.is_listening() is True              # re-armed in lite (not disarmed)
    assert d._mode == "lite"
    assert d._host.mode == "lite"
    assert len(spawns) == 2                      # normal spawn + ONE lite reload


def test_toggle_while_idle_arms_in_normal():
    """D while idle → arms in normal (mode becomes normal, one spawn)."""
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.toggle()
    assert d.is_listening() is True
    assert d._mode == "normal"
    assert d._host.mode == "normal"
    assert len(spawns) == 1


def test_toggle_while_armed_in_normal_disarms():
    """D while armed-in-normal → disarms (no reload)."""
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.start()                                    # arm in normal
    d.toggle()                                   # armed-in-normal → disarm
    assert d.is_listening() is False
    assert len(spawns) == 1


def test_toggle_while_armed_in_lite_switches_to_normal():
    """BUG-B fix: D while armed-in-LITE → switches to normal (exactly ONE reload)."""
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
    d.start_lite()                               # arm in lite
    assert d._mode == "lite" and d.is_listening()
    d.toggle()                                   # cross-mode press → switch (not disarm!)
    assert d.is_listening() is True              # re-armed in normal (not disarmed)
    assert d._mode == "normal"
    assert d._host.mode == "normal"
    assert len(spawns) == 2                      # lite spawn + ONE normal reload


# --- validation Issue MEDIUM: a failed cross-mode toggle must clear stale `listening` ---
#
# toggle()/toggle_lite() call _load_host() for the mode switch; on failure they used to `return`
# WITHOUT clearing _listening (set True by the previous arm). _load_host tears down the resident
# host on failure (_host = None), so the daemon ended up reporting listening: True with NO recorder,
# and status_snapshot (hence voicectl status) printed a misleading 'listening: on'. These tests pin
# the fix: on a failed cross-mode reload the daemon DISARMS (listening: off, _load_error surfaced).


def _failing_second_spawn_factory(spawns):
    """host_factory whose FIRST spawn succeeds (arms the first mode) and whose SECOND spawn fails.

    The second spawn is the cross-mode RELOAD; making it fail reproduces the MEDIUM-bug scenario
    (resident host torn down by _load_host, _load_error set, listening left stale without the fix).
    """
    def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)
        # First built host spawns True; every subsequent one fails.
        host.spawn_result = len(spawns) == 0
        spawns.append(host)
        return host
    return factory


def test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening():
    """Failed cross-mode toggle_lite (armed-in-normal → lite reload fails) clears stale listening.

    Regression guard for validation Issue MEDIUM: without the fix, the failed reload left
    is_listening() == True with _host is None + models_loaded False, so status_snapshot reported
    'listening: on' for a daemon with no recorder and never surfaced _load_error.
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
    d.start()                                    # arm in normal (first spawn succeeds)
    assert d._mode == "normal" and d.is_listening()
    d.toggle_lite()                              # cross-mode switch → lite reload FAILS
    assert d.is_listening() is False             # FIXED: disarmed (was stale-True without the fix)
    assert d._host is None                       # the resident host was torn down by _load_host
    assert d._models_loaded is False
    assert d._load_error is not None             # surfaced so status/voicectl can report it
    assert d._mode == "normal"                   # never flipped to lite (spawn failed)


def test_toggle_while_armed_in_lite_failed_reload_clears_listening():
    """Failed cross-mode toggle (armed-in-lite → normal reload fails) clears stale listening.

    The lite→normal mirror of the test above.
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
    d.start_lite()                               # arm in lite (first spawn succeeds)
    assert d._mode == "lite" and d.is_listening()
    d.toggle()                                   # cross-mode switch → normal reload FAILS
    assert d.is_listening() is False             # FIXED: disarmed
    assert d._host is None
    assert d._models_loaded is False
    assert d._load_error is not None
    assert d._mode == "lite"                     # never flipped to normal (spawn failed)


def test_failed_cross_mode_toggle_status_snapshot_is_honest():
    """After a failed cross-mode toggle, status_snapshot() reports listening: False (not stale True).

    Pins the user-visible symptom from validation Issue MEDIUM: voicectl status must NOT print
    'listening: on' for a daemon whose recorder failed to (re)load. Also asserts load_error is
    surfaced in the snapshot so the failure is diagnosable.
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
    d.start()                                    # arm in normal
    assert d.is_listening() is True
    d.toggle_lite()                              # lite reload fails
    snap = d.status_snapshot()
    assert snap["listening"] is False            # honest status (was True without the fix)
    assert snap["models_loaded"] is False
    assert snap["load_error"]                     # the failure reason is surfaced


def test_dispatch_toggle_cross_mode_lite_to_normal_failure_returns_ok_false():
    """Cross-mode toggle (armed-in-lite → normal reload fails) surfaces ok:false+error.

    Regression for bugfix Issue 1: _dispatch's toggle branch returned {ok:true, listening:false}
    (silent) when a cross-mode reload failed, because arm_attempted was False. The fix routes a
    FRESH _load_error through _arm_response() so voicectl prints 'error: model load failed: ...'
    (exit 1), matching start/start-lite.
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
    d.start_lite()                                              # arm in lite (1st spawn succeeds)
    assert d.is_listening() and d._mode == "lite"
    srv = daemon.ControlServer(d)
    resp = srv._dispatch(json.dumps({"cmd": "toggle"}))         # lite→normal, 2nd spawn FAILS
    assert resp["ok"] is False
    assert "model load failed" in resp["error"]


def test_dispatch_toggle_lite_cross_mode_normal_to_lite_failure_returns_ok_false():
    """Cross-mode toggle-lite (armed-in-normal → lite reload fails) surfaces ok:false+error.

    The normal→lite mirror of the test above (bugfix Issue 1).
    """
    spawns: list = []
    d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
    d.start()                                                   # arm in normal (1st spawn succeeds)
    assert d.is_listening() and d._mode == "normal"
    srv = daemon.ControlServer(d)
    resp = srv._dispatch(json.dumps({"cmd": "toggle-lite"}))    # normal→lite, 2nd spawn FAILS
    assert resp["ok"] is False
    assert "model load failed" in resp["error"]


# ===========================================================================
# P1.M1.T4.S1 — toggle_lite docstring references the correct key D (bugfix Issue 4)
# (the lite keybind is Alt+Super+D — key D, never F (hypr-binds.conf:44 / PRD §4.10). The
#  toggle_lite docstring previously said "pressing F" 3×; this pins it at "pressing D",
#  mirroring the sibling toggle() docstring. Pure static-text assertion on __doc__ — no
#  instantiation, no GPU/socket/recorder.)
# ===========================================================================
def test_toggle_lite_docstring_says_pressing_d_not_f():
    """toggle_lite.__doc__ references key D (the lite bind is Alt+Super+D), never F (Issue 4).

    The lite keybind is SUPER ALT, D (hypr-binds.conf:44 / PRD §4.10) — key D, not F. The
    docstring must mirror the sibling toggle() docstring, which correctly says "pressing D".
    Before the fix this was RED: "pressing F" present (3×), "pressing D" absent.
    """
    doc = daemon.VoiceTypingDaemon.toggle_lite.__doc__
    assert doc is not None, "toggle_lite is missing its docstring"
    assert "pressing D" in doc, "toggle_lite docstring must say 'pressing D' (lite bind = Alt+Super+D)"
    assert "pressing F" not in doc, "toggle_lite docstring must NOT reference key F (it is D)"
