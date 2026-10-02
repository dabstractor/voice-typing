"""Unit tests for voice_typing.typing_backends (PRD §4.3 — typing-backend test harness).

Pure-Python, subprocess.run MOCKED: no display, no ydotoold, NO real keystrokes. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_typing_backends.py -v

subprocess.run is monkeypatched for every test via the `recorder` fixture, so each call
is captured (argv + kwargs) and never reaches the OS. This is the test harness for
typing_backends.py (P1.M3.T1.S1): it pins the three PRD §4.3 command lists (wtype /
ydotool --key-delay 2 / null no-op) and the wtype->ydotool auto-fallback
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
    NullBackend,
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
    of argv selects the behavior ("wtype" / "ydotool").
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
# NullBackend — types nothing (headless E2E verifies finals via state.json)
# ---------------------------------------------------------------------------


def test_null_backend_spawns_no_subprocess(recorder):
    # The null backend must not touch the OS at all — the E2E relies on that so a
    # headless run never types into the developer's focused window.
    NullBackend().type_text("hi")
    assert recorder.argvs == []


# ---------------------------------------------------------------------------
# TypingBackend ABC — abstract, uninstantiable (PRD §4.3 interface)
# ---------------------------------------------------------------------------


def test_typing_backend_is_abstract():
    with pytest.raises(TypeError):
        TypingBackend()


def test_concrete_backends_are_typing_backends():
    assert isinstance(WtypeBackend(), TypingBackend)
    assert isinstance(YdotoolBackend(), TypingBackend)
    assert isinstance(NullBackend(), TypingBackend)


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


def test_make_backend_null():
    b = make_backend(OutputConfig(backend="null"))
    assert isinstance(b, NullBackend)


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


# ---------------------------------------------------------------------------
# Issue 5 (P1.M2.T2.S2): the THREAD SAFETY module-docstring must NOT restate the
# FALSE "The daemon serializes on_final calls, so no locking is needed" claim. It
# must name the actual serialization mechanism — VoiceTypingDaemon._on_final_lock,
# added by the sibling task P1.M2.T2.S1. Textual guard only (does not import daemon).
# ---------------------------------------------------------------------------


def test_module_docstring_names_on_final_serialization_lock():
    """Issue 5 regression guard: THREAD SAFETY note names _on_final_lock; stale false claim gone."""
    import voice_typing.typing_backends as typing_backends

    doc = typing_backends.__doc__ or ""
    assert "_on_final_lock" in doc, "THREAD SAFETY note must reference _on_final_lock"
    assert "no locking is needed" not in doc, "stale FALSE claim removed (Issue 5)"
    assert "serializes on_final calls" not in doc, "stale FALSE claim removed (Issue 5)"


# ===========================================================================
# Rev 2 P1.M1.T3.S1 — press_backspace(n): batched backspace primitive (PRD §4.2quater R2)
# (ONE subprocess per call — the <150ms/80-char budget; n<=0 is a no-op. Exact argv pins for
#  wtype (-k Backspace ×n) and ydotool (key -d 1 + 14:1/14:0 ×n); the wrapper mirrors the
#  type_text catch/WARNING/retry-once contract. All via the `recorder` fixture — no real keys.)
# ===========================================================================


def test_wtype_press_backspace_exact_argv(recorder):
    WtypeBackend().press_backspace(3)
    assert recorder.argvs == [
        ("wtype", "-k", "Backspace", "-k", "Backspace", "-k", "Backspace")
    ]
    assert recorder.calls[0][1].get("check") is True


def test_ydotool_press_backspace_exact_argv(recorder):
    YdotoolBackend().press_backspace(2)
    assert recorder.argvs == [
        ("ydotool", "key", "-d", "1", "14:1", "14:0", "14:1", "14:0")
    ]
    assert recorder.calls[0][1].get("check") is True


@pytest.mark.parametrize("n", [0, -1, -5])
def test_press_backspace_nonpositive_spawns_nothing(recorder, caplog, n):
    with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
        WtypeBackend().press_backspace(n)
        YdotoolBackend().press_backspace(n)
        make_backend(OutputConfig(backend="wtype")).press_backspace(n)
    assert recorder.calls == []  # no subprocess at all
    assert not any(
        "ydotool" in r.getMessage() for r in caplog.records
    )  # no spurious WARNING


def test_press_backspace_n80_is_one_invocation(recorder):
    # The budget contract (PRD §4.2quater): ~80 chars must rewind via ONE subprocess call.
    WtypeBackend().press_backspace(80)
    assert len(recorder.argvs) == 1
    assert len(recorder.argvs[0]) == 1 + 2 * 80  # "wtype" + 80 × ("-k","Backspace")
    assert recorder.argvs[0].count("Backspace") == 80
    YdotoolBackend().press_backspace(80)
    assert len(recorder.argvs) == 2  # one MORE call (total), still 1 each
    assert len(recorder.argvs[1]) == 4 + 2 * 80  # + "-d","1" pair
    assert recorder.argvs[1].count("14:1") == 80 and recorder.argvs[1].count("14:0") == 80


def test_press_backspace_fallback_ordering(recorder):
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    make_backend(OutputConfig(backend="wtype")).press_backspace(2)
    assert recorder.argvs == [
        ("wtype", "-k", "Backspace", "-k", "Backspace"),
        ("ydotool", "key", "-d", "1", "14:1", "14:0", "14:1", "14:0"),
    ]  # retry exactly ONCE, correct argv each


def test_press_backspace_fallback_missing_binary_also_retries(recorder):
    recorder.raise_on("wtype", FileNotFoundError("wtype"))
    make_backend(OutputConfig(backend="wtype")).press_backspace(1)
    assert recorder.argvs[0][0] == "wtype" and recorder.argvs[1][0] == "ydotool"


def test_press_backspace_fallback_logs_warning(recorder, caplog):
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
        make_backend(OutputConfig(backend="wtype")).press_backspace(1)
    assert any(
        r.levelno == logging.WARNING and "ydotool" in r.getMessage()
        for r in caplog.records
    )


def test_press_backspace_fallback_failure_propagates(recorder):
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    recorder.raise_on("ydotool", FileNotFoundError("ydotool"))
    with pytest.raises(OSError):
        make_backend(OutputConfig(backend="wtype")).press_backspace(1)


def test_press_backspace_primary_success_no_fallback(recorder):
    make_backend(OutputConfig(backend="wtype")).press_backspace(2)
    assert len(recorder.argvs) == 1 and recorder.argvs[0][0] == "wtype"


def test_null_press_backspace_spawns_no_subprocess(recorder):
    NullBackend().press_backspace(5)
    assert recorder.calls == []


def test_press_backspace_is_abstract_on_abc():
    with pytest.raises(TypeError):
        TypingBackend()  # still abstract overall

    class _OnlyTypeText(TypingBackend):
        def type_text(self, text):
            ...

    with pytest.raises(TypeError):
        _OnlyTypeText()  # press_backspace missing -> uninstantiable (genuinely abstract)
