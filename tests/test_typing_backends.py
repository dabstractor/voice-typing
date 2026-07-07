"""Unit tests for voice_typing.typing_backends (PRD §4.3 — typing-backend test harness).

Pure-Python, subprocess.run MOCKED: no display, no ydotoold, NO real keystrokes. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_typing_backends.py -v

subprocess.run is monkeypatched for every test via the `recorder` fixture, so each call
is captured (argv + kwargs) and never reaches the OS. This is the test harness for
typing_backends.py (P1.M3.T1.S1): it pins the three PRD §4.3 command lists (wtype /
ydotool --key-delay 2 / tmux send-keys -t -l --) and the wtype->ydotool auto-fallback
contract (PRD §4.3 + §8 risk "wtype fails on some window") before the daemon
(P1.M4.T1.S2) is wired.

Written FIRST (TDD) — RED until voice_typing/typing_backends.py (P1.M3.T1.S1) lands.
"""
from __future__ import annotations

import logging
import subprocess

import pytest

from voice_typing.config import OutputConfig
from voice_typing.typing_backends import (
    TmuxBackend,
    TypingBackend,
    WtypeBackend,
    YdotoolBackend,
    _WtypeWithFallback,
    make_backend,
)


# ---------------------------------------------------------------------------
# subprocess.run recorder — captures EVERY call; never sends real keystrokes.
#
# typing_backends does `import subprocess` and calls `subprocess.run(...)`, so
# patching the `run` attribute on the `subprocess` module is what every backend
# sees (same module object regardless of importer). monkeypatch restores the real
# subprocess.run after each test — no leakage between tests.
# ---------------------------------------------------------------------------


class _Recorder:
    """Records subprocess.run(argv, **kwargs) calls and never touches the OS.

    By default each call returns CompletedProcess(returncode=0) (success under
    check=True). Configure failures with raise_on(argv[0], exc): the first element
    of argv selects the behavior ("wtype" / "ydotool" / "/usr/bin/tmux").
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        self._raises: dict[str, BaseException] = {}

    def raise_on(self, cmd0: str, exc: BaseException) -> None:
        """Make every call whose argv[0] == cmd0 raise `exc`."""
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
        """Just the argv tuples, in call order."""
        return [argv for argv, _kw in self.calls]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """subprocess.run is mocked for the WHOLE test; no real keystroke is ever sent."""
    rec = _Recorder()
    rec.install(monkeypatch)
    return rec


# ---------------------------------------------------------------------------
# WtypeBackend — exact argv ["wtype","--",text] (PRD §4.3)
# ---------------------------------------------------------------------------


def test_wtype_invokes_exact_argv(recorder):
    WtypeBackend().type_text("hello world")
    assert recorder.argvs == [("wtype", "--", "hello world")]


def test_wtype_passes_check_true(recorder):
    # check=True turns nonzero exit into CalledProcessError -> the fallback can catch it.
    WtypeBackend().type_text("hi")
    assert recorder.calls[0][1].get("check") is True


def test_wtype_text_starting_with_dash_stays_literal(recorder):
    # `--` keeps "-5 degrees" positional (not parsed as an option) — PRD §4.3.
    WtypeBackend().type_text("-5 degrees")
    assert recorder.argvs == [("wtype", "--", "-5 degrees")]


def test_wtype_never_appends_newline_or_space(recorder):
    # Backends type EXACTLY `text`; the trailing space is the daemon's job.
    WtypeBackend().type_text("Hello")
    assert recorder.argvs[0][-1] == "Hello"  # no "\n", no extra " "


# ---------------------------------------------------------------------------
# YdotoolBackend — argv includes ["type","--key-delay","2","--",text] (PRD §4.3)
# ---------------------------------------------------------------------------


def test_ydotool_uses_key_delay_2(recorder):
    YdotoolBackend().type_text("hi")
    assert recorder.argvs[0][:4] == ("ydotool", "type", "--key-delay", "2")


def test_ydotool_invokes_exact_argv(recorder):
    YdotoolBackend().type_text("hello")
    assert recorder.argvs[0] == (
        "ydotool",
        "type",
        "--key-delay",
        "2",
        "--",
        "hello",
    )


def test_ydotool_passes_check_true(recorder):
    YdotoolBackend().type_text("hi")
    assert recorder.calls[0][1].get("check") is True


# ---------------------------------------------------------------------------
# TmuxBackend — /usr/bin/tmux send-keys -t <target> -l -- text (PRD §4.3)
# ---------------------------------------------------------------------------


def test_tmux_uses_full_bin_path(recorder):
    # zsh aliases `tmux`; the FULL path is mandatory (system_context.md §1).
    TmuxBackend(OutputConfig(backend="tmux", tmux_target="s:0.0")).type_text("hi")
    assert recorder.argvs[0][0] == "/usr/bin/tmux"


def test_tmux_send_keys_with_dash_l(recorder):
    # `-l` = literal text (no key-name interpretation, no trailing Enter).
    TmuxBackend(OutputConfig(backend="tmux", tmux_target="s:0.0")).type_text("a;b")
    assert recorder.argvs[0][:5] == (
        "/usr/bin/tmux",
        "send-keys",
        "-t",
        "s:0.0",
        "-l",
    )


def test_tmux_invokes_exact_argv(recorder):
    TmuxBackend(OutputConfig(backend="tmux", tmux_target="voicetest:0.0")).type_text(
        "Hello 123"
    )
    assert recorder.argvs[0] == (
        "/usr/bin/tmux",
        "send-keys",
        "-t",
        "voicetest:0.0",
        "-l",
        "--",
        "Hello 123",
    )


def test_tmux_uses_empty_target_when_unset(recorder):
    # OutputConfig().tmux_target defaults to "" (active pane / explicit default).
    TmuxBackend(OutputConfig(backend="tmux")).type_text("hi")
    assert recorder.argvs[0] == (
        "/usr/bin/tmux",
        "send-keys",
        "-t",
        "",
        "-l",
        "--",
        "hi",
    )


def test_tmux_passes_check_true(recorder):
    TmuxBackend(OutputConfig(backend="tmux")).type_text("hi")
    assert recorder.calls[0][1].get("check") is True


# ---------------------------------------------------------------------------
# TypingBackend ABC — abstract, uninstantiable (PRD §4.3 interface)
# ---------------------------------------------------------------------------


def test_typing_backend_is_abstract():
    with pytest.raises(TypeError):
        TypingBackend()


def test_concrete_backends_are_typing_backends():
    assert isinstance(WtypeBackend(), TypingBackend)
    assert isinstance(YdotoolBackend(), TypingBackend)
    assert isinstance(TmuxBackend(OutputConfig(backend="tmux")), TypingBackend)


# ---------------------------------------------------------------------------
# make_backend — factory dispatch on cfg.backend (PRD §4.3)
# ---------------------------------------------------------------------------


def test_make_backend_wtype_returns_fallback_wrapper():
    b = make_backend(OutputConfig(backend="wtype"))
    assert isinstance(b, _WtypeWithFallback)
    # S1 designed _primary/_fallback as testable injection points.
    assert isinstance(b._primary, WtypeBackend)
    assert isinstance(b._fallback, YdotoolBackend)


def test_make_backend_ydotool():
    b = make_backend(OutputConfig(backend="ydotool"))
    assert isinstance(b, YdotoolBackend)


def test_make_backend_tmux_carries_target():
    b = make_backend(OutputConfig(backend="tmux", tmux_target="s:0.1"))
    assert isinstance(b, TmuxBackend)
    assert b._tmux_target == "s:0.1"


def test_make_backend_unknown_raises_value_error():
    with pytest.raises(ValueError, match="bogus"):
        make_backend(OutputConfig(backend="bogus"))


# ---------------------------------------------------------------------------
# Auto-fallback — wtype -> ydotool on failure (PRD §4.3 + §8 risk).
# Monkeypatch subprocess.run to simulate failure (the item's required approach).
# These exercise the REAL backends end-to-end (not injected fakes).
# ---------------------------------------------------------------------------


def test_wtype_success_does_not_invoke_fallback(recorder):
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert len(recorder.calls) == 1
    assert recorder.argvs[0][0] == "wtype"


def test_wtype_nonzero_exit_falls_back_to_ydotool(recorder):
    # check=True converts a nonzero returncode into CalledProcessError -> caught -> fallback.
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert recorder.argvs[0] == ("wtype", "--", "hi")
    assert recorder.argvs[1] == (
        "ydotool",
        "type",
        "--key-delay",
        "2",
        "--",
        "hi",
    )


def test_wtype_missing_binary_falls_back_to_ydotool(recorder):
    # FileNotFoundError (binary not installed) is an OSError -> caught -> fallback.
    recorder.raise_on(
        "wtype", FileNotFoundError(2, "No such file or directory", "wtype")
    )
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert recorder.argvs[0][0] == "wtype"
    assert recorder.argvs[1][0] == "ydotool"


def test_wtype_permission_error_also_falls_back(recorder):
    # PermissionError (binary not executable) is an OSError too -> must fall back.
    recorder.raise_on("wtype", PermissionError("wtype not executable"))
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert recorder.argvs[1][0] == "ydotool"


def test_fallback_fails_too_propagates(recorder):
    # If ydotool ALSO fails, the exception propagates (retry ONCE; no silent swallow).
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    recorder.raise_on("ydotool", subprocess.CalledProcessError(1, ["ydotool"]))
    with pytest.raises(subprocess.CalledProcessError):
        make_backend(OutputConfig(backend="wtype")).type_text("hi")
    # Exactly 2 subprocess calls: primary once, fallback once.
    assert len(recorder.calls) == 2


def test_fallback_retries_exactly_once(recorder):
    # Must NOT loop / retry repeatedly on consecutive failures.
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    recorder.raise_on("ydotool", subprocess.CalledProcessError(1, ["ydotool"]))
    with pytest.raises(subprocess.CalledProcessError):
        make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert len(recorder.calls) == 2  # never more than primary + one fallback


def test_fallback_logs_warning(recorder, caplog):
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
        make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert any(
        r.levelno == logging.WARNING and "ydotool" in r.getMessage()
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# No real keystrokes — the recorder guarantees subprocess.run never runs for real.
# ---------------------------------------------------------------------------


def test_no_real_subprocess_run_during_tests(monkeypatch):
    # Sanity guard: the monkeypatch mechanism itself replaces `subprocess.run`, so a
    # stray call records instead of executing (it would otherwise type into the user's
    # FOCUSED window — a real safety hazard). Every other test uses the `recorder`
    # fixture; this one asserts the mechanism directly.
    rec = _Recorder()
    rec.install(monkeypatch)
    result = subprocess.run(["wtype", "--", "x"], check=True)
    assert result.returncode == 0
    assert rec.argvs == [("wtype", "--", "x")]
