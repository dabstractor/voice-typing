"""Unit tests for the P1.M2.T2.S2 stage remediation (BUG-002 / PRD §4.2sexies R.1/R.8).

Hermetic (test_daemon.py discipline): cuda_check.resolve_device_and_models is monkeypatched
onto a deterministic path and _construct() is called with a kwarg-capturing fake recorder —
NO RealtimeSTT import, NO model load, NO CUDA, NO live desktop (the real-route qualification
is T2.S3; the G5 lab is never started from here).

WHAT IS PINNED (research stage_remediation.md §5):
  - the SINGLE stage fix (recognizer/decode cadence): a bulk-text build gets the tightened
    module constant `_BULK_REALTIME_PROCESSING_PAUSE` in kwargs["realtime_processing_pause"];
    a stream-edit build keeps cfg.asr.realtime_processing_pause BYTE-IDENTICALLY (bulk-only
    scoping — the stream-edit path must not move; PRD R.8 + gate law);
  - the override is a pure function of the EXISTING cfg (no module state, no knob, no
    cross-build leakage; two identical bulk builds are identical, an interleaved stream
    build changes nothing);
  - NO new config key: the constant lives in daemon (code), the config schema is unchanged
    (AsrConfig keeps exactly its one pause field; OutputConfig gains none);
  - R.8 selection NOT flipped (S6: ±3 ms on both boundaries, im-gtk plain arm not-run):
    the default build still registers exactly ONE partial callback and it is the
    "stabilized" key — for bulk AND stream builds;
  - no new failure mode: a recorder signature that lacks the pause kwarg still builds in
    bulk mode (the filter drops the constant exactly like it dropped the cfg value);
  - the child's executor injection (extra_kwargs) still wins for its own keys and carries
    no pause key, so the documented merge order cannot resurrect a stale cadence.

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_bulk_stage_remediation.py -v
"""
from __future__ import annotations

import dataclasses
import inspect
from typing import Any, Callable

import pytest

from voice_typing import daemon
from voice_typing.config import AsrConfig, OutputConfig, VoiceTypingConfig

from conftest import hermetic_cfg


# ---------------------------------------------------------------------------
# Stubs — duck-typed stand-ins so tests never import RealtimeSTT or feedback.py.
# ---------------------------------------------------------------------------


class _FakeFeedback:
    """Only the methods the wired closures COULD call (none are invoked here)."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)


class _CapturingRecorder:
    """Accepts ANY kwargs (VAR_KEYWORD) and captures them (mirrors test_daemon._FakeRecorder)."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)


class _StrictNoPauseRecorder:
    """Explicit signature WITH the stabilized partial key but WITHOUT realtime_processing_pause
    (no **kwargs): the filter drops the cadence kwarg exactly like it dropped the cfg-sourced
    value pre-fix — the bulk override must NOT become a new build-failure mode — while the
    partial-callback enforcement still passes (build ⟹ the selected key survived)."""

    def __init__(
        self,
        model: str = "",
        on_realtime_transcription_stabilized: "Callable[[str], None] | None" = None,
    ) -> None:
        self.kwargs = {
            "model": model,
            "on_realtime_transcription_stabilized": on_realtime_transcription_stabilized,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cuda_resolve(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str]) -> None:
    """Force daemon.cuda_check.resolve_device_and_models onto a deterministic path
    (verbatim mechanic from tests/test_daemon.py — no CUDA, no probe)."""

    def _resolve(cfg: VoiceTypingConfig) -> dict[str, str]:
        return dict(mapping)

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)


def _cfg_with(delivery: str, pause: float = 0.15) -> VoiceTypingConfig:
    base = hermetic_cfg()
    return dataclasses.replace(
        base,
        asr=dataclasses.replace(base.asr, realtime_processing_pause=pause),
        output=dataclasses.replace(base.output, delivery=delivery),
    )


def _build(cfg: VoiceTypingConfig, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> _CapturingRecorder:
    _cuda_resolve(monkeypatch, dict(daemon.cuda_check.CUDA_DEFAULTS))
    return daemon._construct(cfg, _FakeFeedback(), _CapturingRecorder, **kw)


# ---------------------------------------------------------------------------
# The cadence fix — bulk-only scoping (the ONE production stage change)
# ---------------------------------------------------------------------------


def test_bulk_build_gets_the_tightened_constant(monkeypatch):
    rec = _build(_cfg_with("bulk-text", pause=0.15), monkeypatch)
    assert rec.kwargs["realtime_processing_pause"] == daemon._BULK_REALTIME_PROCESSING_PAUSE
    assert daemon._BULK_REALTIME_PROCESSING_PAUSE == 0.05  # the S2 value, pinned


def test_stream_build_keeps_the_cfg_value_byte_identical(monkeypatch):
    # Default cfg value (0.15) flows through UNCHANGED — the constant must not leak:
    rec = _build(_cfg_with("stream-edit", pause=0.15), monkeypatch)
    assert rec.kwargs["realtime_processing_pause"] == 0.15
    # A non-default cfg value flows through byte-identically too:
    rec2 = _build(_cfg_with("stream-edit", pause=0.2), monkeypatch)
    assert rec2.kwargs["realtime_processing_pause"] == 0.2


def test_bulk_override_wins_over_any_cfg_value(monkeypatch):
    # Override semantics (not min/max): whatever the cfg says, bulk gets the constant.
    rec = _build(_cfg_with("bulk-text", pause=0.2), monkeypatch)
    assert rec.kwargs["realtime_processing_pause"] == 0.05
    rec2 = _build(_cfg_with("bulk-text", pause=0.01), monkeypatch)
    assert rec2.kwargs["realtime_processing_pause"] == 0.05


def test_pure_function_of_cfg_no_state_no_cross_build_leak(monkeypatch):
    # Identical bulk builds are identical; an interleaved stream build changes nothing.
    bulk_a = _build(_cfg_with("bulk-text"), monkeypatch)
    stream = _build(_cfg_with("stream-edit"), monkeypatch)
    bulk_b = _build(_cfg_with("bulk-text"), monkeypatch)
    assert bulk_a.kwargs["realtime_processing_pause"] == 0.05
    assert bulk_b.kwargs["realtime_processing_pause"] == 0.05
    assert stream.kwargs["realtime_processing_pause"] == 0.15  # untouched by its neighbours


# ---------------------------------------------------------------------------
# No new knob — the constant is CODE, the config schema is untouched
# ---------------------------------------------------------------------------


def test_cadence_is_a_module_constant_and_config_schema_is_unchanged():
    assert isinstance(daemon._BULK_REALTIME_PROCESSING_PAUSE, float)
    # AsrConfig keeps EXACTLY its one pause field (no bulk twin introduced):
    asr_pause_fields = [f.name for f in dataclasses.fields(AsrConfig) if "pause" in f.name]
    assert asr_pause_fields == ["realtime_processing_pause"]
    # OutputConfig gained NO pause/cadence field:
    assert [f.name for f in dataclasses.fields(OutputConfig) if "pause" in f.name] == []


# ---------------------------------------------------------------------------
# R.8 selection NOT flipped — exactly ONE partial callback key, still "stabilized"
# ---------------------------------------------------------------------------


def test_default_selection_registers_exactly_one_stabilized_key_both_modes(monkeypatch):
    stabilized_key = daemon._PARTIAL_SOURCES["stabilized"]
    plain_key = daemon._PARTIAL_SOURCES["plain"]
    for delivery in ("bulk-text", "stream-edit"):
        rec = _build(_cfg_with(delivery), monkeypatch)
        registered = [k for k in rec.kwargs if k in daemon._PARTIAL_SOURCES.values()]
        assert registered == [stabilized_key], (
            f"{delivery}: expected exactly ONE partial callback ({stabilized_key!r}), "
            f"got {registered!r}"
        )
        assert plain_key not in rec.kwargs


def test_partial_source_default_is_stabilized():
    sig = inspect.signature(daemon._construct)
    assert sig.parameters["partial_source"].default == "stabilized"


# ---------------------------------------------------------------------------
# No new failure modes — filter compatibility + child executor-injection order
# ---------------------------------------------------------------------------


def test_strict_signature_without_pause_still_builds_in_bulk_mode(monkeypatch):
    _cuda_resolve(monkeypatch, dict(daemon.cuda_check.CUDA_DEFAULTS))
    rec = daemon._construct(
        _cfg_with("bulk-text"), _FakeFeedback(), _StrictNoPauseRecorder
    )
    assert "realtime_processing_pause" not in rec.kwargs  # dropped like any unknown kwarg
    assert rec.kwargs["model"]  # the build itself is healthy


def test_extra_kwargs_win_for_their_own_keys_and_carry_no_pause(monkeypatch):
    executor = object()  # stand-in for the child's transcription executor
    _cuda_resolve(monkeypatch, dict(daemon.cuda_check.CUDA_DEFAULTS))
    rec = daemon._construct(
        _cfg_with("bulk-text"),
        _FakeFeedback(),
        _CapturingRecorder,
        extra_kwargs={"transcription_executor": executor},
    )
    assert rec.kwargs["transcription_executor"] is executor
    assert rec.kwargs["realtime_processing_pause"] == 0.05  # the constant survives the merge


# ---------------------------------------------------------------------------
# The dedicated bulk REALTIME lane (validation round 3 — BUG-002 / R.1)
#
# The qualification round measured the collapse of the shared-lane build:
# every partial decode re-decoded the ENTIRE growing buffer at beam 5 on the
# MAIN executor/lock — ~3.7 update callbacks per ~17.5 s replay, the 57-word
# sentence-end dump, speech→visible med 6714 ms ≈ 13× the 500 ms bar
# (tests/G5_TIMING_EVIDENCE.md, production arms). The lane split gives bulk
# builds a dedicated greedy-beam realtime engine (or, when the context-prompt
# executor is armed, a dedicated beam-1 PromptedExecutor injected by
# recorder_host.augment_kwargs_with_executor). Stream-edit builds keep Rev-2's
# single-lane build BYTE-IDENTICALLY.
# ---------------------------------------------------------------------------


def test_bulk_build_splits_the_realtime_lane(monkeypatch):
    """A bulk build carries use_main_model_for_realtime=False + the greedy beam constant."""
    rec = _build(_cfg_with("bulk-text"), monkeypatch)
    assert rec.kwargs["use_main_model_for_realtime"] is False
    assert rec.kwargs["beam_size_realtime"] == daemon._BULK_REALTIME_BEAM_SIZE
    assert daemon._BULK_REALTIME_BEAM_SIZE == 1  # greedy: the whole point is cheap decodes
    assert rec.kwargs["realtime_processing_pause"] == 0.05  # S2's cadence fix still applies
    # Same model string in BOTH slots (Rev-2 model choice is NOT re-opened — only the
    # decode settings of the partial lane get cheaper):
    assert rec.kwargs["realtime_model_type"] == rec.kwargs["model"]


def test_stream_build_keeps_the_single_lane_byte_identical(monkeypatch):
    """Stream-edit builds keep Rev-2 single-model routing — no lane kwargs leak into them."""
    rec = _build(_cfg_with("stream-edit"), monkeypatch)
    assert rec.kwargs["use_main_model_for_realtime"] is True
    assert "beam_size_realtime" not in rec.kwargs
    assert rec.kwargs["realtime_processing_pause"] == 0.15  # cfg value, not the bulk constant


def test_bulk_lane_is_a_module_constant_and_config_schema_is_unchanged():
    assert isinstance(daemon._BULK_REALTIME_BEAM_SIZE, int)
    assert daemon._BULK_REALTIME_BEAM_SIZE >= 1
    # NO new config key on either side (the BUG-002 contract forbids an end-user knob):
    asr_fields = [f.name for f in dataclasses.fields(AsrConfig) if "beam" in f.name]
    out_fields = [f.name for f in dataclasses.fields(OutputConfig) if "beam" in f.name]
    assert asr_fields == [] and out_fields == []
    asr_main_fields = [
        f.name for f in dataclasses.fields(AsrConfig) if "use_main_model" in f.name
    ]
    assert asr_main_fields == []


def test_strict_signature_drops_lane_kwargs_and_still_builds_in_bulk_mode(monkeypatch):
    """The lane kwargs follow the log-and-drop filter law: a signature without them builds
    exactly like the pre-lane build (no new failure mode), while the partial-callback
    enforcement still holds."""
    _cuda_resolve(monkeypatch, dict(daemon.cuda_check.CUDA_DEFAULTS))
    rec = daemon._construct(
        _cfg_with("bulk-text"), _FakeFeedback(), _StrictNoPauseRecorder
    )
    assert "use_main_model_for_realtime" not in rec.kwargs  # dropped like any unknown kwarg
    assert "beam_size_realtime" not in rec.kwargs
    assert "realtime_processing_pause" not in rec.kwargs
    assert rec.kwargs["model"]  # the build itself is healthy


def test_lane_kwargs_pure_function_of_cfg_no_cross_build_leak(monkeypatch):
    """Interleaved builds cannot leak lane settings across delivery modes."""
    bulk_a = _build(_cfg_with("bulk-text"), monkeypatch)
    stream = _build(_cfg_with("stream-edit"), monkeypatch)
    bulk_b = _build(_cfg_with("bulk-text"), monkeypatch)
    for bulk in (bulk_a, bulk_b):
        assert bulk.kwargs["use_main_model_for_realtime"] is False
        assert bulk.kwargs["beam_size_realtime"] == 1
    assert stream.kwargs["use_main_model_for_realtime"] is True
    assert "beam_size_realtime" not in stream.kwargs
