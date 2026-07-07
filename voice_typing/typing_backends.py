"""voice_typing.typing_backends — typing output backends (PRD §4.3).

type_text(text) sends finalized, textproc-cleaned text to the focused window (or a
tmux pane) via one of three backends, selected by config output.backend:

  - wtype    (default): Wayland virtual-keyboard-v1. Full Unicode, no layout issues.
             Types into the focused window incl. terminals/tmux.
  - ydotool: uinput-level. Works for XWayland apps; known weakness: non-ASCII / layout
             quirks. Kept as the auto-fallback when wtype fails.
  - tmux:    tmux send-keys -l into an explicit target pane. Used by the E2E test and
             for SSH/detached use.

AUTO-FALLBACK (PRD §4.3 + §8 risk "wtype fails on some window"): make_backend() returns
a wrapper for backend=="wtype" that runs wtype, and on a nonzero exit or a missing/
unusable binary (subprocess.CalledProcessError / OSError, which includes FileNotFoundError)
logs a WARNING and retries ONCE via ydotool. If the fallback also raises, the exception
propagates to the caller (the daemon logs/handles it) — it is never silently swallowed.

THREAD SAFETY: type_text is safe to call from the daemon's on_final callback thread.
The backends hold NO shared mutable state (Wtype/Ydotool are stateless; TmuxBackend
stores one immutable tmux_target at construction), and subprocess.run spawns an
independent child process per call (reentrant). The daemon serializes on_final calls,
so no locking is needed.

NEVER EMIT ENTER/NEWLINE: the backends type EXACTLY the text passed (no trailing
newline). textproc.clean() already stripped trailing newlines/whitespace; the daemon
appends a single trailing space when output.append_space (not the backend). For tmux,
the `-l` flag makes send-keys treat the keys as literal text (no key-name interpretation,
no trailing Enter) — do not drop it.

CONSUMES: voice_typing.config.OutputConfig (P1.M2.T1.S1): backend, tmux_target.
  append_space is the DAEMON's concern (not used here).
CONSUMED BY: daemon on_final (P1.M4.T1.S2) as:
    backend = typing_backends.make_backend(cfg.output)
    backend.type_text(text + (" " if cfg.output.append_space else ""))
  and the E2E test (P1.M7.T3.S1) via backend="tmux".

PURE STDLIB (subprocess, logging, abc, OutputConfig). No cuda_check / torch /
realtimestt / ctranslate2 — loads in CPU-only and test contexts; subprocess.run is
mocked in unit tests (P1.M3.T1.S2).
"""
from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod

from voice_typing.config import OutputConfig

logger = logging.getLogger(__name__)

# Full path: zsh aliases `tmux` to a plugin wrapper. ALWAYS invoke the real binary in
# subprocess (PRD §4.3; system_context.md §1).
_TMUX = "/usr/bin/tmux"


class TypingBackend(ABC):
    """Abstract typing backend (PRD §4.3). type_text sends text to the target."""

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type `text` exactly (no trailing newline). Raise on failure.

        Implementations run a subprocess (wtype/ydotool/tmux). Failures surface as
        subprocess.CalledProcessError (nonzero exit) or OSError (missing/unusable
        binary). The auto-fallback wrapper (for wtype) catches these and retries
        via ydotool; other backends let exceptions propagate to the caller.
        """
        raise NotImplementedError


class WtypeBackend(TypingBackend):
    """wtype: Wayland virtual-keyboard-v1. Full Unicode. The default backend."""

    def type_text(self, text: str) -> None:
        # `--` separates options from text so text starting with '-' is literal.
        # check=True -> nonzero exit raises CalledProcessError, caught by the
        # auto-fallback wrapper. A missing wtype binary raises FileNotFoundError
        # (an OSError), also caught by the fallback.
        subprocess.run(["wtype", "--", text], check=True)


class YdotoolBackend(TypingBackend):
    """ydotool type: uinput-level. Fallback; non-ASCII/layout quirks (PRD §4.3)."""

    def type_text(self, text: str) -> None:
        # --key-delay 2: 2ms between key events (PRD §4.3 verbatim; man ydotool
        # documents the space form `--key-delay <ms>`; GNU argp accepts it).
        subprocess.run(
            ["ydotool", "type", "--key-delay", "2", "--", text], check=True
        )


class TmuxBackend(TypingBackend):
    """tmux send-keys -l into an explicit target pane. E2E test / SSH backend."""

    def __init__(self, cfg: OutputConfig) -> None:
        # tmux_target may be "" (active pane of most recent client) or explicit,
        # e.g. "voicetest:0.0". -l treats the keys as literal text (no key-name
        # interpretation), so punctuation is typed verbatim and no Enter is sent.
        self._tmux_target = cfg.tmux_target

    def type_text(self, text: str) -> None:
        subprocess.run(
            [_TMUX, "send-keys", "-t", self._tmux_target, "-l", "--", text],
            check=True,
        )


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


def make_backend(cfg: OutputConfig) -> TypingBackend:
    """Select a typing backend from output.backend (PRD §4.3).

    Args:
        cfg: the [output] config (backend, tmux_target). append_space is the
            daemon's concern and is NOT used here.

    Returns:
        - backend == "wtype"   -> wtype with auto-fallback to ydotool (default)
        - backend == "ydotool" -> ydotool (no further fallback)
        - backend == "tmux"    -> tmux send-keys into cfg.tmux_target

    Raises:
        ValueError: unknown backend name.
    """
    backend = cfg.backend
    if backend == "wtype":
        return _WtypeWithFallback()
    if backend == "ydotool":
        return YdotoolBackend()
    if backend == "tmux":
        return TmuxBackend(cfg)
    raise ValueError(f"unknown output.backend: {backend!r}")
