"""LAB REFERENCE — the retired bulk-text realtime-lane recorder wiring (P1.M1.T1.S2).

Moved verbatim out of tests/test_prompt_engine.py when the daemon detached the bulk
surface (P1.M1.T1.S2). These tests pin recorder_host.augment_kwargs_with_executor /
arm_bulk_realtime_executor's BULK-only lane split — the recorder-side wiring that
P1.M1.T1.S3 removes from the product. They are NOT collected (pyproject norecursedirs
excludes tools/) and NOT runnable as-is: OutputConfig(delivery="bulk-text") raises at
config load since P1.M1.T1.S1. Kept as the lab pin S3 references while removing the
product wiring (PRD §4.2sexies, superseded).
"""
from __future__ import annotations

import logging

from voice_typing import prompt_engine
from voice_typing.config import AsrConfig, OutputConfig, VoiceTypingConfig
from voice_typing.recorder_host import (
    arm_bulk_realtime_executor,
    augment_kwargs_with_executor,
)

_RESOLVED_CUDA = {"device": "cuda", "compute_type": "float32", "model": "small.en"}
_LOG = logging.getLogger("prompt-engine-tests")


class _FakeExecutor:
    """Executor stand-in for augment_kwargs_with_executor (records warmup count)."""

    def __init__(self, model: str, device: str, compute_type: str) -> None:
        self.args = (model, device, compute_type)
        self.warmed = 0

    def warmup(self) -> None:
        self.warmed += 1


def _cfg_delivery(delivery: str, context_prompt: bool = True) -> VoiceTypingConfig:
    return VoiceTypingConfig(
        asr=AsrConfig(context_prompt=context_prompt),
        output=OutputConfig(delivery=delivery),
    )


def test_bulk_delivery_splits_realtime_lane():
    """bulk-text: two DISTINCT executors — finals keep the shared lane, partials get their own."""
    kwargs: dict = {"model": "small.en", "device": "cuda"}
    executor = augment_kwargs_with_executor(
        kwargs, _cfg_delivery("bulk-text"), _RESOLVED_CUDA, _LOG,
        executor_factory=_FakeExecutor,
    )
    assert isinstance(executor, _FakeExecutor) and executor.warmed == 1
    finals_lane = kwargs["transcription_executor"]
    realtime_lane = kwargs["realtime_transcription_executor"]
    assert finals_lane is executor  # the final lane keeps the context-prompt executor
    assert isinstance(realtime_lane, _FakeExecutor)
    assert realtime_lane is not finals_lane  # the SPLIT — the whole point
    assert realtime_lane.args == ("small.en", "cuda", "float32")  # same model, its own instance
    assert realtime_lane.warmed == 1  # probed before arming, exactly once


def test_bulk_realtime_lane_probe_failure_degrades_to_shared(caplog):
    """A failed lane probe leaves the SHARED executor in the realtime kwarg — pre-split behavior."""
    good = _FakeExecutor("small.en", "cuda", "float32")

    class _BadExecutor(good.__class__):
        def warmup(self) -> None:
            raise RuntimeError("rt lane probe boom")

    calls = {"n": 0}

    def _factory(model: str, device: str, compute_type: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return good
        return _BadExecutor(model, device, compute_type)

    kwargs: dict = {"model": "small.en", "device": "cuda"}
    with caplog.at_level(logging.INFO, logger="prompt-engine-tests"):
        executor = augment_kwargs_with_executor(
            kwargs, _cfg_delivery("bulk-text"), _RESOLVED_CUDA, _LOG,
            executor_factory=_factory,
        )
    assert executor is good
    assert kwargs["transcription_executor"] is good
    # Degrade: the realtime kwarg points back at the SHARED executor (identical to
    # the pre-split build — the lane split never becomes a failure mode):
    assert kwargs["realtime_transcription_executor"] is good
    assert calls["n"] == 2  # the dedicated lane WAS attempted before degrading
    infos = [
        r for r in caplog.records
        if r.levelno == logging.INFO and "bulk realtime lane: probe failed" in r.getMessage()
    ]
    assert len(infos) == 1  # ONE concise degrade line


def test_bulk_realtime_lane_default_factory_uses_greedy_beam(monkeypatch):
    """Production factory (no injection): the dedicated lane is a greedy beam-1 PromptedExecutor."""
    captured: dict = {}

    def _fake_probe(executor):
        captured["executor"] = executor
        return prompt_engine.PromptProbeResult(ok=True)

    monkeypatch.setattr(prompt_engine, "probe_prompt_executor", _fake_probe)
    kwargs: dict = {"model": "small.en", "device": "cuda"}
    executor = arm_bulk_realtime_executor(kwargs, _cfg_delivery("bulk-text"), _RESOLVED_CUDA, _LOG)
    assert executor is captured["executor"]
    assert executor._beam_size == 1  # greedy — the measured-collapse fix
    assert kwargs["realtime_transcription_executor"] is executor
