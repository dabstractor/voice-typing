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
    PromptInstallResult,
    PromptProbeResult,
    PromptState,
    PromptedExecutor,
    fit_initial_prompt,
    probe_prompt_executor,
    prompt_token_budget,
    rolling_context_prompt,
    trim_prompt,
    utf8_suffix_within,
)
from voice_typing.recorder_host import (
    _prompt_targets,
    _ready_payload,
    augment_kwargs_with_executor,
)  # arm_bulk_realtime_executor moved to tools/lab-tests/ (P1.M1.T1.S2)

_RESOLVED_CUDA = {"device": "cuda", "compute_type": "float32", "model": "small.en"}
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
    assert executor.args == ("small.en", "cuda", "float32")
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
    base = {"device": "cuda", "compute_type": "float32", "model": "small.en"}
    ready = _ready_payload(base, True)
    assert ready["context_prompt"] is True
    assert ready["model"] == "small.en"
    assert _ready_payload(base, False)["context_prompt"] is False
    assert "context_prompt" not in base  # input dict not mutated


def test_prompt_targets_single_executor_contract():
    """_prompt_targets (P1.M1.T1.S3): the ONE-executor contract — exactly the armed executor, or none."""
    main = _FakeExecutor("m", "d", "c")
    assert _prompt_targets(main) == [main]   # one object, one target
    assert _prompt_targets(None) == []       # nothing armed: no targets (the loop logs + ignores)


def test_recorder_host_has_no_bulk_lane_surface():
    """P1.M1.T1.S3: the Rev-4 bulk realtime-lane SPLIT is gone from recorder_host — ONE executor
    contract. No split helper exists, the module carries no bulk/beam wiring, augment arms the SAME
    object into both kwargs, the prompt fan-out reaches exactly that object, and the config layer
    (S1) rejects the only delivery value that could have requested a split."""
    import inspect

    import voice_typing.recorder_host as rh

    assert not hasattr(rh, "arm_bulk_realtime_executor")
    assert not hasattr(rh, "_default_bulk_realtime_executor_factory")
    src = inspect.getsource(rh)
    assert "bulk" not in src.lower() and "beam" not in src.lower(), "bulk/beam wiring survived"
    assert "extra_kwargs" not in inspect.signature(rh._prompt_targets).parameters  # 1-arg seam
    # the ONE object lands in BOTH kwargs (context-prompt on, fake factory)
    kwargs: dict = {"model": "small.en", "device": "cuda"}
    executor = rh.augment_kwargs_with_executor(
        kwargs,
        VoiceTypingConfig(asr=AsrConfig(context_prompt=True)),
        _RESOLVED_CUDA,
        _LOG,
        executor_factory=_FakeExecutor,
    )
    assert executor is not None
    assert kwargs["transcription_executor"] is executor
    assert kwargs["realtime_transcription_executor"] is executor   # SAME object — no split
    assert rh._prompt_targets(executor) == [executor]
    # S1's chain: no constructible config can request the retired lane
    with pytest.raises(ValueError, match="retired"):
        VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}})


# ---------------------------------------------------------------------------
# §4.8.1 initial-prompt seed (P1.M1.T2.S1): confirmed install + tokenizer-proven fit
# ---------------------------------------------------------------------------


_ASTRAL_MARK = 0x200000  # pair-start token for astral codepoints (see _FakeTokenizer)


class _FakeTokenizer:
    """Deterministic invertible tokenizer: a BMP codepoint encodes to 1 token (its codepoint);
    an astral codepoint encodes to 2 tokens (marker + offset) — so emoji/ZWJ sequences are
    genuinely multi-token and a naive token-list cut CAN split them. decode() inverts
    exactly; a SPLIT pair decodes to U+FFFD glue, so decode(prefix)+decode(suffix) !=
    decode(all) for a cut inside a codepoint — the exact property the fitter's alignment
    check relies on. encode() raises TypeError on non-str (the failure path)."""

    def encode(self, text):
        if not isinstance(text, str):
            raise TypeError("encode expects str")
        out = []
        for ch in text:
            cp = ord(ch)
            if cp < 0x10000:
                out.append(cp)
            else:
                out.append(_ASTRAL_MARK)
                out.append(cp - 0x10000)
        return out

    def decode(self, tokens):
        chars = []
        pending = False
        for t in tokens:
            if t == _ASTRAL_MARK:
                if pending:
                    chars.append("\ufffd")  # orphaned marker (a split pair)
                pending = True
            elif pending:
                chars.append(chr(0x10000 + t))
                pending = False
            else:
                chars.append(chr(t))
        if pending:
            chars.append("\ufffd")
        return "".join(chars)


class _WarmModel:
    """Just the attributes install_initial_prompt reads from a warmed faster-whisper model:
    the integer `.max_length` (448 on the installed faster-whisper) and a `.tokenizer`
    exposing encode/decode."""

    def __init__(self, max_length=448, tokenizer=None):
        self.max_length = max_length
        self.tokenizer = _FakeTokenizer() if tokenizer is None else tokenizer


def _warm_executor(model=None) -> PromptedExecutor:
    ex = _executor()
    ex._model = _WarmModel() if model is None else model
    return ex


def test_prompt_state_is_str_backed_and_result_carries_counts_only():
    assert PromptState.APPLIED == "applied"
    assert PromptState.CLEAR == "clear"
    assert PromptState.UNCONFIRMED == "unconfirmed"
    assert set(PromptInstallResult.__dataclass_fields__) == {"state", "tokens"}  # NO text field
    assert PromptInstallResult(PromptState.APPLIED, 5).tokens == 5
    assert PromptInstallResult(PromptState.CLEAR).tokens is None


def test_prompt_token_budget_read_from_model_not_copied():
    assert prompt_token_budget(_WarmModel(max_length=448)) == 223  # the faster-whisper number
    assert prompt_token_budget(_WarmModel(max_length=450)) == 224  # derived, not a literal
    assert prompt_token_budget(_WarmModel(max_length=4)) == 1
    assert prompt_token_budget(_WarmModel(max_length=3)) is None  # formula floor: >= 1
    assert prompt_token_budget(_WarmModel(max_length=None)) is None
    assert prompt_token_budget(_WarmModel(max_length="448")) is None  # non-int
    assert prompt_token_budget(_WarmModel(max_length=True)) is None  # bool is not a length

    class _NoLen:
        pass

    assert prompt_token_budget(_NoLen()) is None  # missing attribute


def test_install_initial_prompt_applied_on_warm_installs_fitted_tail():
    ex = _warm_executor()
    seed = "meeting notes for the weekly sync " + " ".join(f"w{i}" for i in range(400))
    result = ex.install_initial_prompt(seed)
    assert result.state is PromptState.APPLIED
    assert result.tokens is not None and result.tokens <= 223  # 448 // 2 - 1, READ from the model
    fitted = ex.prompt
    assert fitted
    toks = _FakeTokenizer().encode(fitted)
    assert len(toks) <= 223  # the decode-side prompt window cannot clip it
    assert result.tokens == len(toks)
    assert fitted.endswith("w399")  # the NEWEST context survived the fit


def test_install_initial_prompt_under_budget_installs_normalized_verbatim():
    ex = _warm_executor()
    result = ex.install_initial_prompt("  hello \t world  ")
    assert result.state is PromptState.APPLIED
    assert result.tokens == 11  # the fake is char-per-token: "hello world" = 11 codepoints
    assert ex.prompt == "hello world"


def test_install_initial_prompt_clear_on_warm():
    ex = _warm_executor()
    ex._prompt = "previous"
    for blank in (None, "", "   "):
        result = ex.install_initial_prompt(blank)
        assert result.state is PromptState.CLEAR
        assert result.tokens is None
        assert ex.prompt is None


def test_install_initial_prompt_unconfirmed_when_cold_forces_prompt_none():
    ex = _executor()  # cold: warmup never built the model
    ex._prompt = "stale"
    result = ex.install_initial_prompt("seed text")
    assert result.state is PromptState.UNCONFIRMED
    assert result.tokens is None
    assert ex.prompt is None  # forced defensively — the decode degrades to context-free
    result2 = ex.install_initial_prompt(None)  # a cold CLEAR is just as unprovable
    assert result2.state is PromptState.UNCONFIRMED
    assert ex.prompt is None


def test_install_initial_prompt_unconfirmed_without_usable_budget_or_tokenizer():
    ex = _warm_executor(_WarmModel(max_length=None))
    assert ex.install_initial_prompt("seed").state is PromptState.UNCONFIRMED
    assert ex.prompt is None

    class _NoLen:  # no max_length attribute at all
        tokenizer = _FakeTokenizer()

    ex2 = _warm_executor(_NoLen())
    assert ex2.install_initial_prompt("seed").state is PromptState.UNCONFIRMED
    assert ex2.prompt is None

    class _NoTok:  # max_length fine, tokenizer missing (unexpected attribute shape)
        max_length = 448

    ex3 = _warm_executor(_NoTok())
    assert ex3.install_initial_prompt("seed").state is PromptState.UNCONFIRMED
    assert ex3.prompt is None


def test_install_initial_prompt_unconfirmed_when_tokenizer_raises():
    seed = "secret seed content " + "x" * 250  # > budget: the fit MUST call encode + decode

    class _BoomEncodeTok(_FakeTokenizer):
        def encode(self, text):
            raise RuntimeError(f"tokenize exploded on {text}")

    ex = _warm_executor(_WarmModel(tokenizer=_BoomEncodeTok()))
    result = ex.install_initial_prompt(seed)  # must NOT raise
    assert result.state is PromptState.UNCONFIRMED
    assert ex.prompt is None

    class _BoomDecodeTok(_FakeTokenizer):
        def decode(self, tokens):
            raise RuntimeError(f"decode exploded on {seed}")

    ex2 = _warm_executor(_WarmModel(tokenizer=_BoomDecodeTok()))
    result2 = ex2.install_initial_prompt(seed)  # failure inside the fitter
    assert result2.state is PromptState.UNCONFIRMED
    assert ex2.prompt is None

    # non-str input is a failure too (fail-closed), never a crash:
    ex3 = _warm_executor()
    assert ex3.install_initial_prompt(123).state is PromptState.UNCONFIRMED  # type: ignore[arg-type]
    assert ex3.prompt is None


def test_fit_initial_prompt_keeps_newest_tokens_under_budget():
    words = [f"w{i}" for i in range(400)]
    text = " ".join(words)
    tok = _FakeTokenizer()
    out = fit_initial_prompt(text, encode=tok.encode, decode=tok.decode, budget=223)
    out_toks = tok.encode(out)
    assert len(out_toks) <= 223
    assert out.endswith("w399")  # newest kept
    # In this fake every character is a token, so the newest-TOKEN tail may end mid-word —
    # the contract is token alignment, not word alignment. Assert a true suffix + tail-ness:
    assert text.endswith(out)
    assert len(out) < len(text)  # something was dropped from the OLDEST end


def test_fit_initial_prompt_never_splits_a_codepoint():
    emoji = "\U0001F469\u200D\U0001F4BB"  # 👩‍💻 ZWJ sequence: 2 + 1 + 2 = 5 tokens in the fake
    assert len(_FakeTokenizer().encode(emoji)) == 5  # genuinely multi-token
    tok = _FakeTokenizer()
    text = "context " + emoji * 120  # 8 + 840 tokens — well over the budget
    out = fit_initial_prompt(text, encode=tok.encode, decode=tok.decode, budget=223)
    assert out
    assert "\ufffd" not in out  # nothing decoded to replacement glue — no half codepoints
    assert out.endswith(emoji)  # the newest emoji survived WHOLE
    assert tok.decode(tok.encode(out)) == out  # round-trips exactly
    assert len(tok.encode(out)) <= 223


def test_fit_initial_prompt_ignores_sentence_boundaries():
    # Under budget, the '.' must NOT cut (the sentence cut is the ROLLING path's rule):
    tok = _FakeTokenizer()
    out = fit_initial_prompt("hello. world tail", encode=tok.encode, decode=tok.decode, budget=223)
    assert out == "hello. world tail"  # rolling_context_prompt would return only "world tail"


def test_utf8_suffix_within_is_codepoint_safe_and_bounded():
    emoji = "\U0001F600"  # 4 UTF-8 bytes
    text = "aaa" + emoji  # 3 + 4 = 7 bytes
    assert utf8_suffix_within(text, 7) == text
    assert utf8_suffix_within(text, 6) == "aa" + emoji  # the leading 'a' drops WHOLE
    big = emoji * 1200  # 4800 bytes
    out = utf8_suffix_within(big, 4096)
    assert len(out) == 1024 and len(out.encode("utf-8")) == 4096
    assert all(ch == emoji for ch in out)  # whole emoji only — never half
    mixed = ("aaa" + emoji) * 1000  # 7000 bytes
    out2 = utf8_suffix_within(mixed, 4096)
    assert len(out2.encode("utf-8")) <= 4096
    assert out2.endswith(emoji) and "\ufffd" not in out2
    assert mixed.endswith(out2)  # a true suffix
    assert utf8_suffix_within("ok", 4096) == "ok"
    assert utf8_suffix_within(mixed, 0) == ""
    assert utf8_suffix_within(None, 4096) == ""  # type: ignore[arg-type]


def test_install_initial_prompt_never_leaks_seed_into_logs_or_results(caplog):
    seed = "TOP SECRET dictation 👩‍💻 never log this " + "y" * 250  # > budget: fit decodes
    marker = "TOP SECRET"

    class _BoomDecodeTok(_FakeTokenizer):
        def decode(self, tokens):
            # the EXCEPTION ITSELF carries seed-derived content — fit swallows it to "" and
            # the caller must never log/propagate it (shape/counts only):
            raise RuntimeError(f"decode exploded on {seed}")

    caplog.set_level(logging.DEBUG, logger="voice_typing.prompt_engine")
    ex = _warm_executor()
    applied = ex.install_initial_prompt(seed)
    assert applied.state is PromptState.APPLIED  # even the success path must not log text
    unconfirmed = _warm_executor(_WarmModel(tokenizer=_BoomDecodeTok())).install_initial_prompt(seed)
    assert unconfirmed.state is PromptState.UNCONFIRMED
    cold = _executor().install_initial_prompt(seed)
    assert cold.state is PromptState.UNCONFIRMED
    clear = _warm_executor().install_initial_prompt(None)
    assert clear.state is PromptState.CLEAR
    nonstr = _warm_executor().install_initial_prompt(123)  # type: ignore[arg-type]
    assert nonstr.state is PromptState.UNCONFIRMED  # the except branch: exception TYPE logged
    # every captured log record: counts/shape/exception TYPE only — no seed text anywhere
    assert any("AttributeError" in r.getMessage() for r in caplog.records)  # type-only logging lives
    for rec in caplog.records:
        assert marker not in rec.getMessage()
        assert "👩" not in rec.getMessage()
    # results carry counts only — repr is safe by construction:
    for res in (applied, unconfirmed, cold, clear, nonstr):
        assert marker not in repr(res)


def test_set_prompt_remains_best_effort_word_proxy_distinct_from_install():
    # The ordinary rolling path is byte-identical: word-proxy cap, works cold, no tri-state.
    ex = _warm_executor()
    ex.set_prompt(" ".join(["x"] * 500))
    assert ex.prompt is not None
    assert len(ex.prompt.split()) == prompt_engine._PROMPT_TOKEN_CAP
    cold = _executor()
    cold.set_prompt("hello there")  # cold set_prompt: still best-effort, no UNCONFIRMED dance
    assert cold.prompt == "hello there"
    assert rolling_context_prompt("done first. now the second") == "now the second"
