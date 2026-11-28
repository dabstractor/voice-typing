"""TmuxBackend (2026-11-25): paste-into-focused-tmux-pane delivery with a ydotool
fallback whenever focus is NOT a tmux client.

Pure CPU, hermetic: the subprocess runner and the focus-pid probe are injected,
so no tmux/hyprctl process is ever spawned here.
"""
from __future__ import annotations

import subprocess

from voice_typing.typing_backends import TmuxBackend


class Rec:
    def __init__(self, stdout=""):
        self.calls: list[list] = []
        self.kwargs: list[dict] = []
        self.stdout = stdout

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        self.kwargs.append(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="")


class Fallback:
    def __init__(self):
        self.typed: list[str] = []
        self.backspaces: list[int] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def press_backspace(self, n: int) -> None:
        self.backspaces.append(n)


PANES = "1 1 main:0.0\n0 1 main:0.1\n"


def make(focused: bool, runner_stdout: str = PANES):
    rec, fb = Rec(runner_stdout), Fallback()
    be = TmuxBackend(
        fb, runner=rec,
        focus_pid=(lambda: 4242 if focused else None),
        focus_is_tmux=lambda pid: focused,
    )
    return be, rec, fb


def test_paste_goes_to_active_pane_when_tmux_focused() -> None:
    be, rec, fb = make(focused=True)
    be.type_text("hello ")
    assert fb.typed == []
    assert rec.calls[0][:2] == ["tmux", "list-panes"]  # focus resolution first
    assert rec.calls[1][:2] == ["tmux", "load-buffer"]
    assert rec.kwargs[1]["input"] == "hello "
    assert rec.calls[2] == ["tmux", "paste-buffer", "-t", "main:0.0"]


def test_non_tmux_focus_uses_fallback() -> None:
    be, rec, fb = make(focused=False)
    be.type_text("hello ")
    be.press_backspace(3)
    assert fb.typed == ["hello "]
    assert fb.backspaces == [3]
    assert rec.calls == []


def test_backspace_is_one_send_keys_burst() -> None:
    be, rec, fb = make(focused=True)
    be.press_backspace(42)
    assert fb.backspaces == []
    assert rec.calls[-1] == ["tmux", "send-keys", "-t", "main:0.0"] + ["BSpace"] * 42


def test_tmux_failure_falls_back_once() -> None:
    fb = Fallback()
    calls = []

    def flaky(cmd, **kw):
        calls.append(cmd)
        if "paste-buffer" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=PANES, stderr="")

    be = TmuxBackend(fb, runner=flaky, focus_pid=lambda: 1, focus_is_tmux=lambda pid: True)
    be.type_text("word ")
    assert fb.typed == ["word "]
    assert any("paste-buffer" in c for c in calls)


def test_empty_and_zero_are_noops() -> None:
    be, rec, fb = make(focused=True)
    be.type_text("")
    be.press_backspace(0)
    assert rec.calls == [] and fb.typed == [] and fb.backspaces == []
