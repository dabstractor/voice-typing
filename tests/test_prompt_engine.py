"""Unit tests for voice_typing.prompt_engine + the recorder_host context-prompt wiring.

P1.M2.T5.S1. PURE-PYTHON: no CUDA, no RealtimeSTT import, no model loads — faster_whisper is
monkeypatched with a fake module (sys.modules) whose WhisperModel records every constructor
arg and every transcribe() kwarg. Run:
    cd /home/dustin/projects/voice-typing
    timeout 600 .venv/bin/pytest tests/test_prompt_engine.py -q

Pins (PRD §4.2quater + PRD §8 degrade-not-fail):
  - trim_prompt keeps the NEWEST tokens under the 200-word cap (context tail matters most)
  - set_prompt stores trimmed text; None/"" clears; garbage input never raises
  - transcribe passes the CURRENT prompt as initial_prompt (partials AND finals path);
    language passthrough; use_prompt=False -> initial_prompt None
  - transcribe NEVER raises (model build or decode failure -> empty result)
  - warmup (the startup capability probe) RAISES on failure, succeeds once on health
  - recorder_host.augment_kwargs_with_executor: executor kwargs injected on success; stock
    kwargs untouched on config-off AND probe failure (identical degrade path); one INFO
    degrade line
  - _ready_payload: additive context_prompt flag, input not mutated
"""

from __future__ import annotations

import logging
import sys
import types

import pytest

from voice_typing import prompt_engine
from voice_typing.config import AsrConfig, VoiceTypingConfig
from voice_typing.prompt_engine import (
    PromptProbeResult,
    PromptedExecutor,
    probe_prompt_executor,
    rolling_context_prompt,
    trim_prompt,
)
from voice_typing.recorder_host import _ready_payload, augment_kwargs_with_executor

_RESOLVED_CUDA = {"device": "cuda", "compute_type": "float16", "model": "small.en"}
_LOG = logging.getLogger("prompt-engine-tests")


# ---------------------------------------------------------------------------
# Fake faster_whisper (installed into sys.modules; WhisperModel records everything)
# ---------------------------------------------------------------------------


class _FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


def _install_fake_faster_whisper(
    monkeypatch: pytest.MonkeyPatch,
    *,
    segments: "list[_FakeSegment] | None" = None,
    info: "prompt_engine.TranscriptionInfo | None" = None,
    raise_on_init: "Exception | None" = None,
    raise_on_transcribe: "Exception | None" = None,
) -> "tuple[list[dict], list[dict]]":
    """Install a fake faster_whisper module; return (ctor_records, transcribe_kwarg_records)."""
    created: list[dict] = []
    calls: list[dict] = []

    class _Model:
        def __init__(
            self, model_size_or_path=None, device=None, compute_type=None, **kw
        ):
            if raise_on_init is not None:
                raise raise_on_init
            created.append(
                {
                    "model": model_size_or_path,
                    "device": device,
                    "compute_type": compute_type,
                }
            )

        def transcribe(self, audio, **kwargs):
            if raise_on_transcribe is not None:
                raise raise_on_transcribe
            calls.append(kwargs)
            segs = segments if segments is not None else [_FakeSegment(" hello world ")]
            info_obj = info or prompt_engine.TranscriptionInfo("en", 0.9)
            return iter(segs), info_obj

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=_Model)
    )
    return created, calls


def _executor() -> PromptedExecutor:
    return PromptedExecutor(model_name="small.en", device="cpu", compute_type="int8")


def _cfg(context_prompt: bool = True) -> VoiceTypingConfig:
    return VoiceTypingConfig(asr=AsrConfig(context_prompt=context_prompt))


class _FakeExecutor:
    """Executor stand-in for augment_kwargs_with_executor (records warmup count)."""

    def __init__(self, model: str, device: str, compute_type: str) -> None:
        self.args = (model, device, compute_type)
        self.warmed = 0

    def warmup(self) -> None:
        self.warmed += 1


# ---------------------------------------------------------------------------
# trim_prompt (pure)
# ---------------------------------------------------------------------------


def test_trim_prompt_caps_and_keeps_tail():
    words = [f"w{i}" for i in range(250)]
    out = trim_prompt(" ".join(words))
    assert len(out.split()) == 200
    assert out.split() == words[-200:]  # newest kept, oldest dropped


def test_trim_prompt_normalizes_whitespace():
    assert trim_prompt("  hello \t world\n ") == "hello world"


def test_trim_prompt_under_cap_returns_all_tokens():
    assert trim_prompt("hello world") == "hello world"


def test_trim_prompt_empty_or_blank_is_empty():
    assert trim_prompt("") == ""
    assert trim_prompt("   ") == ""


def test_trim_prompt_nonpositive_cap_is_empty():
    assert trim_prompt("hello world", cap=0) == ""
    assert trim_prompt("hello world", cap=-1) == ""


# ---------------------------------------------------------------------------
# rolling_context_prompt (P1.M2.T5.S2 — the formal daemon-side computation)
# ---------------------------------------------------------------------------


def test_rolling_prompt_midstring_boundary_slices_in_progress_sentence():
    # Last '.' sits mid-string: the prompt is ONLY the text after it (whitespace-normalized).
    assert rolling_context_prompt("done first. now the second") == "now the second"
    # '!' and '?' are boundaries too.
    assert rolling_context_prompt("really! tell me more") == "tell me more"
    assert rolling_context_prompt("what now? I think") == "I think"


def test_rolling_prompt_ends_with_terminator_is_empty():
    # Committed ends at a boundary: fresh sentence — the decoder may capitalize.
    assert rolling_context_prompt("a full sentence.") == ""
    assert rolling_context_prompt("one. two!") == ""
    assert rolling_context_prompt("done? ") == ""


def test_rolling_prompt_no_terminator_is_whole_committed():
    # The T8c pause-join case (the thin seam's bug): an unpunctuated run conditions
    # the next decode with its WHOLE text, not "".
    assert (
        rolling_context_prompt("I want to test whether this system")
        == "I want to test whether this system"
    )


def test_rolling_prompt_run_on_over_cap_keeps_newest_200():
    words = [f"w{i}" for i in range(250)]  # 250-token run-on: no boundary anywhere
    out = rolling_context_prompt(" ".join(words))
    assert out.split() == words[-200:]  # newest kept, oldest dropped (trim_prompt)

    # Same cap applies after a boundary slice: 250 fresh tokens since the last '.'.
    tail_words = [f"t{i}" for i in range(250)]
    out2 = rolling_context_prompt("done. " + " ".join(tail_words))
    assert out2.split() == tail_words[-200:]


def test_rolling_prompt_normalizes_whitespace():
    assert rolling_context_prompt("done.  spaced \t out\n") == "spaced out"
    assert rolling_context_prompt("a\tb   c") == "a b c"


def test_rolling_prompt_empty_or_none_is_empty():
    assert rolling_context_prompt("") == ""
    assert rolling_context_prompt("   ") == ""
    assert rolling_context_prompt(None) == ""  # type: ignore[arg-type] — defensive degrade


# ---------------------------------------------------------------------------
# set_prompt / prompt property
# ---------------------------------------------------------------------------


def test_set_prompt_stores_trimmed():
    ex = _executor()
    ex.set_prompt(" ".join(["x"] * 500))
    assert ex.prompt is not None
    assert len(ex.prompt.split()) == prompt_engine._PROMPT_TOKEN_CAP


def test_set_prompt_clears_on_none_and_empty():
    ex = _executor()
    ex.set_prompt("hello there")
    assert ex.prompt == "hello there"
    ex.set_prompt(None)
    assert ex.prompt is None
    ex.set_prompt("hello there")
    ex.set_prompt("")
    assert ex.prompt is None


def test_set_prompt_garbage_never_raises():
    ex = _executor()
    ex.set_prompt("good prompt")
    ex.set_prompt(123)  # type: ignore[arg-type] — defensive: cmd payload coercion upstream
    assert ex.prompt == "good prompt"  # previous prompt kept on failure


# ---------------------------------------------------------------------------
# transcribe (the RealtimeSTT executor contract)
# ---------------------------------------------------------------------------


def test_transcribe_passes_initial_prompt_and_assembles_text(monkeypatch):
    created, calls = _install_fake_faster_whisper(monkeypatch)
    ex = _executor()
    ex.set_prompt("the context tail")
    result = ex.transcribe(b"audio-bytes")
    assert calls, "fake model.transcribe was not called"
    assert calls[0]["initial_prompt"] == "the context tail"
    assert calls[0]["language"] is None  # upstream default passthrough
    assert calls[0]["condition_on_previous_text"] is False
    assert result.text == "hello world"  # joined + stripped from fake segments
    assert result.info.language == "en"
    assert result.info.language_probability == pytest.approx(0.9)
    assert created == [{"model": "small.en", "device": "cpu", "compute_type": "int8"}]


def test_transcribe_language_passthrough(monkeypatch):
    _created, calls = _install_fake_faster_whisper(monkeypatch)
    ex = _executor()
    ex.transcribe(b"a", language="en")
    assert calls[0]["language"] == "en"


def test_transcribe_use_prompt_false_omits_prompt(monkeypatch):
    _created, calls = _install_fake_faster_whisper(monkeypatch)
    ex = _executor()
    ex.set_prompt("context")
    ex.transcribe(b"a", use_prompt=False)
    assert calls[0]["initial_prompt"] is None


def test_transcribe_never_raises_on_decode_failure(monkeypatch):
    _install_fake_faster_whisper(monkeypatch, raise_on_transcribe=RuntimeError("boom"))
    ex = _executor()
    ex.set_prompt("context")
    result = ex.transcribe(b"a")  # must not raise
    assert result.text == ""
    assert result.info.language is None


def test_transcribe_never_raises_on_model_build_failure(monkeypatch):
    _install_fake_faster_whisper(monkeypatch, raise_on_init=RuntimeError("no cuda"))
    result = _executor().transcribe(b"a")  # must not raise
    assert result.text == ""


# ---------------------------------------------------------------------------
# warmup / probe (the startup capability probe)
# ---------------------------------------------------------------------------


def test_warmup_success_builds_one_model_and_transcribes_once(monkeypatch):
    created, calls = _install_fake_faster_whisper(monkeypatch)
    _executor().warmup()
    assert len(created) == 1
    assert len(calls) == 1  # the 1 s zero-audio warmup pass


def test_warmup_failure_raises(monkeypatch):
    _install_fake_faster_whisper(
        monkeypatch, raise_on_transcribe=RuntimeError("cuda dead")
    )
    with pytest.raises(RuntimeError, match="cuda dead"):
        _executor().warmup()


def test_warmup_build_failure_raises(monkeypatch):
    _install_fake_faster_whisper(monkeypatch, raise_on_init=RuntimeError("cuda gone"))
    with pytest.raises(RuntimeError, match="cuda gone"):
        _executor().warmup()


def test_probe_prompt_executor_ok(monkeypatch):
    _install_fake_faster_whisper(monkeypatch)
    probe = probe_prompt_executor(_executor())
    assert probe == PromptProbeResult(ok=True, error=None)


def test_probe_prompt_executor_failure_folds_exception(monkeypatch):
    _install_fake_faster_whisper(monkeypatch, raise_on_init=RuntimeError("cuda broken"))
    probe = probe_prompt_executor(_executor())
    assert probe.ok is False
    assert probe.error is not None and "cuda broken" in probe.error


# ---------------------------------------------------------------------------
# recorder_host.augment_kwargs_with_executor (child wiring, CUDA-free via fake factory)
# ---------------------------------------------------------------------------


def test_executor_kwargs_injection_success():
    kwargs: dict = {"model": "small.en", "language": "en", "use_microphone": True}
    executor = augment_kwargs_with_executor(
        kwargs, _cfg(), _RESOLVED_CUDA, _LOG, executor_factory=_FakeExecutor
    )
    assert isinstance(executor, _FakeExecutor)
    assert executor.warmed == 1  # the capability probe ran exactly once
    assert executor.args == ("small.en", "cuda", "float16")
    assert kwargs["transcription_executor"] is executor
    assert (
        kwargs["realtime_transcription_executor"] is executor
    )  # SAME object = ONE model
    # Stock kwargs untouched:
    assert kwargs["model"] == "small.en" and kwargs["language"] == "en"
    assert kwargs["use_microphone"] is True


def test_executor_kwargs_config_off_is_stock_path():
    kwargs: dict = {"model": "small.en", "device": "cuda"}
    executor = augment_kwargs_with_executor(
        kwargs,
        _cfg(context_prompt=False),
        _RESOLVED_CUDA,
        _LOG,
        executor_factory=_FakeExecutor,
    )
    assert executor is None
    assert "transcription_executor" not in kwargs
    assert "realtime_transcription_executor" not in kwargs
    assert kwargs["device"] == "cuda"  # untouched


def test_executor_kwargs_probe_failure_degrades_with_one_info_line(caplog):
    class _BadExecutor:
        def __init__(self, *a: object) -> None:
            pass

        def warmup(self) -> None:
            raise RuntimeError("probe boom")

    kwargs: dict = {"model": "small.en", "device": "cuda"}
    with caplog.at_level(logging.INFO, logger="prompt-engine-tests"):
        executor = augment_kwargs_with_executor(
            kwargs, _cfg(), _RESOLVED_CUDA, _LOG, executor_factory=_BadExecutor
        )
    assert executor is None
    assert "transcription_executor" not in kwargs
    assert (
        kwargs["device"] == "cuda"
    )  # stock kwargs untouched — identical to config-off path
    infos = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "probe failed" in r.getMessage()
    ]
    assert len(infos) == 1
    assert "degrading to context-free decoding" in infos[0].getMessage()
    assert "probe boom" in infos[0].getMessage()


# ---------------------------------------------------------------------------
# _ready_payload (additive context_prompt flag)
# ---------------------------------------------------------------------------


def test_ready_payload_flag_true_and_false():
    base = {"device": "cuda", "compute_type": "float16", "model": "small.en"}
    ready = _ready_payload(base, True)
    assert ready["context_prompt"] is True
    assert ready["model"] == "small.en"
    assert _ready_payload(base, False)["context_prompt"] is False
    assert "context_prompt" not in base  # input dict not mutated
