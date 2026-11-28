"""voice_typing.typing_backends — typing output backends (PRD §4.3).

type_text(text) sends finalized, textproc-cleaned text to the focused window (or
nowhere, with backend="null") via one of three backends, selected by config
output.backend:

  - wtype    (default): Wayland virtual-keyboard-v1. Full Unicode, no layout issues.
             Types into the focused window.
  - ydotool: uinput-level. Works for XWayland apps; known weakness: non-ASCII / layout
             quirks. Kept as the auto-fallback when wtype fails.
  - null:    types NOTHING. For the headless E2E tests (finals are verified through
             the state file instead of real keystrokes) and for output-disabled setups.

AUTO-FALLBACK (PRD §4.3 + §8 risk "wtype fails on some window"): make_backend() returns
a wrapper for backend=="wtype" that runs wtype, and on a nonzero exit or a missing/
unusable binary (subprocess.CalledProcessError / OSError, which includes FileNotFoundError)
logs a WARNING and retries ONCE via ydotool. If the fallback also raises, the exception
propagates to the caller (the daemon logs/handles it) — it is never silently swallowed.

THREAD SAFETY: type_text is called from the daemon's on_final callback thread. on_final
is serialized by the daemon's _on_final_lock (VoiceTypingDaemon), so only one type_text
call executes at a time. The backends are also individually safe: WtypeBackend/
YdotoolBackend are stateless and spawn an independent child subprocess per call.

NEVER EMIT ENTER/NEWLINE: the backends type EXACTLY the text passed (no trailing
newline). textproc.clean() already stripped trailing newlines/whitespace; the daemon
appends a single trailing space when output.append_space (not the backend).

Rev 2 adds press_backspace(n) (PRD §4.2quater): delete exactly n characters — ONE
batched subprocess per call (wtype repeats "-k Backspace"; ydotool repeats
"14:1","14:0" press/release pairs); n <= 0 is a no-op (no subprocess).

CONSUMES: voice_typing.config.OutputConfig (P1.M2.T1.S1): backend.
  append_space is the DAEMON's concern (not used here).
CONSUMED BY: daemon on_final (P1.M4.T1.S2) as:
    backend = typing_backends.make_backend(cfg.output)
    backend.type_text(text + (" " if cfg.output.append_space else ""))
  and the E2E test via backend="null" (finals verified through the state file).

PURE STDLIB (subprocess, logging, abc, OutputConfig). No cuda_check / torch /
realtimestt / ctranslate2 — loads in CPU-only and test contexts; subprocess.run is
mocked in unit tests (P1.M3.T1.S2).
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

# EVENT PACING (Rev 3d): synthesized key events sent at 0-2 ms intervals get
# COALESCED/dropped by the compositor's input path when bursts bunch up (sustained
# dictation — the "missing characters, worse the longer I use it" report; the
# injector always exits 0, so the loss is silent). Every spawn is serialized with
# a minimum inter-spawn floor so one batch's events drain before the next begins.
_SPAWN_LOCK = threading.Lock()
_LAST_SPAWN = [0.0]
_MIN_SPAWN_GAP_S = 0.025


def _paced_run(cmd: list[str]) -> None:
    """subprocess.run serialized + floored: one injector at a time, >=25 ms apart."""
    with _SPAWN_LOCK:
        gap = _MIN_SPAWN_GAP_S - (time.monotonic() - _LAST_SPAWN[0])
        if gap > 0:
            time.sleep(gap)
        _LAST_SPAWN[0] = time.monotonic()
        subprocess.run(cmd, check=True)
from abc import ABC, abstractmethod

from voice_typing.config import OutputConfig

logger = logging.getLogger(__name__)

class TypingBackend(ABC):
    """Abstract typing backend (PRD §4.3). type_text sends text to the target."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type `text` exactly (no trailing newline). Raise on failure.

        Implementations run a subprocess (wtype/ydotool). Failures surface as
        subprocess.CalledProcessError (nonzero exit) or OSError (missing/unusable
        binary). The auto-fallback wrapper (for wtype) catches these and retries
        via ydotool; other backends let exceptions propagate to the caller.
        """
        raise NotImplementedError

    @abstractmethod
    def press_backspace(self, n: int) -> None:
        """Delete exactly n characters via n Backspace keypresses (PRD §4.2quater R2).

        Implementations MUST batch into ONE subprocess invocation (~80 chars in <150 ms —
        per-keystroke spawning blows the budget). n <= 0 is a no-op (no subprocess).
        """
        raise NotImplementedError


class WtypeBackend(TypingBackend):
    """wtype: Wayland virtual-keyboard-v1. Full Unicode. The default backend."""

    def type_text(self, text: str) -> None:
        # `--` separates options from text so text starting with '-' is literal.
        # check=True -> nonzero exit raises CalledProcessError, caught by the
        # auto-fallback wrapper. A missing wtype binary raises FileNotFoundError
        # (an OSError), also caught by the fallback.
        _paced_run(["wtype", "-d", "1", "--", text])

    def press_backspace(self, n: int) -> None:
        # ONE batched invocation: repeated "-k Backspace" pairs are verified to repeat
        # within a single wtype call (external_deps.md §2, env -i probe). No "--" —
        # all args are options (there is no positional text to separate).
        if n <= 0:
            return
        _paced_run(["wtype", "-d", "1"] + ["-k", "Backspace"] * n)


class YdotoolBackend(TypingBackend):
    """ydotool type: uinput-level. press_backspace prefers a PERSISTENT ydotoold
    socket client (PRD Rev 3e — zero spawn per revision, 3d pacing) when injected;
    direct construction (unit tests) keeps the CLI path. Client failure -> CLI."""

    def __init__(self, client: "object | None" = None) -> None:
        self._client = client

    def type_text(self, text: str) -> None:
        # --key-delay 12: 12ms between key events (was 2 — too tight: compositor
        # input coalescing silently DROPPED characters under sustained bursts; 12ms
        # still types ~80 chars/s, faster than any fragment needs).
        _paced_run(
            ["ydotool", "type", "--key-delay", "1", "--", text]
        )

    def press_backspace(self, n: int) -> None:
        # ONE batched invocation: "14:1 14:0" = Backspace press+release (keycode 14);
        if n <= 0:
            return
        if self._client is not None:
            try:
                self._client.press_backspace(n)  # persistent socket, 18 ms/char (contact 6 + inter 12; P1.M1.T2.S2)
                return
            except Exception:  # noqa: BLE001 — transport hiccup: fall back to CLI
                logger.warning(
                    "ydotoold client failed; falling back to ydotool CLI", exc_info=True
                )
        _paced_run(
            # -d 6 = 6ms/event, 2 events/char = 12ms/char — same pace as type (Rev 3d)
            ["ydotool", "key", "-d", "0"] + ["14:1", "14:0"] * n
        )


class NullBackend(TypingBackend):
    """Types nothing. Headless E2E tests verify finals via the state file instead."""

    def type_text(self, text: str) -> None:
        logger.debug("null backend: suppressed %d chars", len(text))

    def press_backspace(self, n: int) -> None:
        logger.debug("null backend: suppressed %d backspaces", n)


class TmuxBackend(TypingBackend):
    """tmux-buffer delivery (2026-11-25): text enters the focused tmux pane as ONE
    paste per call — no per-character key events, no clipboard, no cliphist exposure.

    type_text: `tmux load-buffer -` + `tmux paste-buffer` into the ACTIVE pane of the
    active window (word-chunk streaming makes each call one word — the measured
    4 ms/600-char atomic path). press_backspace: ONE `tmux send-keys` call with n
    BSpace arguments (measured 300 backspaces applied in <5 ms).

    FOCUS GATE (the safety seam): every call first asks Hyprland for the focused
    window's pid (`hyprctl -j activewindow`); only if that pid is a tmux client
    process (its /proc/<pid>/exe resolves under tmux) is the tmux path used.
    Otherwise the call falls through to the injected fallback backend (ydotool) —
    so dictating into a browser or any non-tmux window keeps working unchanged.
    tmux/hyprctl failures fall back too; a failed tmux op falls back ONCE per call.
    """

    def __init__(
        self,
        fallback: "TypingBackend | None" = None,
        *,
        runner=None,
        focus_pid=None,
        focus_is_tmux=None,
    ) -> None:
        # runner: subprocess.run stand-in (tests inject); focus_pid: callable
        # returning the focused window's pid or None; focus_is_tmux: callable
        # pid -> bool (tests inject; production checks /proc/<pid>/exe).
        self._fallback = fallback if fallback is not None else YdotoolBackend()
        self._runner = runner if runner is not None else subprocess.run
        self._focus_pid = focus_pid if focus_pid is not None else _hypr_focused_pid
        self._focus_is_tmux = (
            focus_is_tmux if focus_is_tmux is not None else _pid_is_tmux
        )

    def _active_pane(self) -> str | None:
        """`session:window.pane` of the active pane in the active window, or None."""
        try:
            out = self._runner(
                ["tmux", "list-panes", "-a", "-F",
                 "#{window_active} #{pane_active} #{session_name}:#{window_index}.#{pane_index}"],
                check=True, capture_output=True, text=True, timeout=2,
            ).stdout
        except Exception:  # noqa: BLE001 — any tmux failure means "not tmux-focused"
            return None
        for line in out.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[0] == "1" and parts[1] == "1":
                return parts[2]
        return None

    def _focused_on_tmux(self) -> bool:
        pid = self._focus_pid()
        if pid is None:
            return False
        return self._focus_is_tmux(pid)

    def type_text(self, text: str) -> None:
        if not text:
            return
        pane = self._active_pane() if self._focused_on_tmux() else None
        if pane is None:
            self._fallback.type_text(text)
            return
        try:
            self._runner(
                ["tmux", "load-buffer", "-"], input=text, check=True,
                capture_output=True, text=True, timeout=2,
            )
            self._runner(
                ["tmux", "paste-buffer", "-t", pane], check=True,
                capture_output=True, text=True, timeout=2,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.warning("tmux paste failed (%s); falling back to key backend", exc)
            self._fallback.type_text(text)

    def press_backspace(self, n: int) -> None:
        if n <= 0:
            return
        pane = self._active_pane() if self._focused_on_tmux() else None
        if pane is None:
            self._fallback.press_backspace(n)
            return
        try:
            self._runner(
                ["tmux", "send-keys", "-t", pane] + ["BSpace"] * n,
                check=True, capture_output=True, text=True, timeout=2,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.warning("tmux backspace failed (%s); falling back to key backend", exc)
            self._fallback.press_backspace(n)


def _pid_is_tmux(pid: int) -> bool:
    """True iff the process's executable resolves under tmux."""
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return False
    return "tmux" in exe


def _hypr_focused_pid() -> int | None:
    """Focused Wayland window's pid via hyprctl, or None (no Hyprland / parse failure)."""
    try:
        out = subprocess.run(
            ["hyprctl", "-j", "activewindow"],
            check=True, capture_output=True, text=True, timeout=2,
        ).stdout
        import json

        return int(json.loads(out).get("pid") or 0) or None
    except Exception:  # noqa: BLE001 — non-Hyprland or timeout: not tmux-focused
        return None


class _WtypeWithFallback(TypingBackend):
    """wtype primary, ydotool fallback (PRD §4.3 auto-fallback; §8 risk).

    Runs wtype; on a nonzero exit (CalledProcessError) or a missing/unusable binary
    (OSError, which includes FileNotFoundError), logs a WARNING and retries ONCE via
    ydotool. If the fallback also raises, the exception propagates to the caller
    (daemon logs/handles it) — never silently swallowed.
    """

    def __init__(
        self,
        primary: TypingBackend | None = None,
        fallback: TypingBackend | None = None,
    ) -> None:
        # Optional injection lets unit tests (P1.M3.T1.S2) swap in fakes to assert
        # fallback ORDERING deterministically; defaults are the real backends.
        self._primary = primary if primary is not None else WtypeBackend()
        self._fallback = fallback if fallback is not None else YdotoolBackend()

    def type_text(self, text: str) -> None:
        try:
            self._primary.type_text(text)
        except (subprocess.CalledProcessError, OSError) as exc:
            # OSError covers FileNotFoundError (binary missing) and PermissionError
            # (binary not executable); CalledProcessError covers nonzero exit. A
            # bug raising, e.g., TypeError is NOT caught here — let it surface.
            logger.warning(
                "wtype typing failed (%s); retrying once via ydotool", exc
            )
            self._fallback.type_text(text)  # may raise -> propagates (one retry only)

    def press_backspace(self, n: int) -> None:
        if n <= 0:
            return  # guard BEFORE the try: n=0 must not try wtype nor log a WARNING
        try:
            self._primary.press_backspace(n)
        except (subprocess.CalledProcessError, OSError) as exc:
            # Same superset as type_text: OSError covers FileNotFoundError and
            # PermissionError; CalledProcessError covers nonzero exit. TypeError is
            # NOT caught here — let it surface.
            logger.warning(
                "wtype backspace failed (%s); retrying once via ydotool", exc
            )
            self._fallback.press_backspace(n)  # may raise -> propagates (one retry)


def make_backend(cfg: OutputConfig) -> TypingBackend:
    """Select a typing backend from output.backend (PRD §4.3).

    Args:
        cfg: the [output] config. append_space is the daemon's concern and is NOT
            used here.

    Returns:
        - backend == "wtype"   -> wtype with auto-fallback to ydotool (default)
        - backend == "ydotool" -> ydotool (no further fallback)
        - backend == "tmux"    -> TmuxBackend (paste into focused tmux pane;
                                  non-tmux focus falls back to ydotool)
        - backend == "null"    -> NullBackend (types nothing)

    Raises:
        ValueError: unknown backend name.
    """
    backend = cfg.backend
    if backend == "wtype":
        return _WtypeWithFallback()
    if backend == "ydotool":
        from voice_typing.ydotoold_client import YdotoolClient

        return YdotoolBackend(client=YdotoolClient())
    if backend == "null":
        return NullBackend()
    if backend == "tmux":
        from voice_typing.ydotoold_client import YdotoolClient

        return TmuxBackend(fallback=YdotoolBackend(client=YdotoolClient()))
    raise ValueError(f"unknown output.backend: {backend!r}")
