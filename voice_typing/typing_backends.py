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
import subprocess
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
        subprocess.run(["wtype", "--", text], check=True)

    def press_backspace(self, n: int) -> None:
        # ONE batched invocation: repeated "-k Backspace" pairs are verified to repeat
        # within a single wtype call (external_deps.md §2, env -i probe). No "--" —
        # all args are options (there is no positional text to separate).
        if n <= 0:
            return
        subprocess.run(["wtype"] + ["-k", "Backspace"] * n, check=True)


class YdotoolBackend(TypingBackend):
    """ydotool type: uinput-level. Fallback; non-ASCII/layout quirks (PRD §4.3)."""

    def type_text(self, text: str) -> None:
        # --key-delay 2: 2ms between key events (PRD §4.3 verbatim; man ydotool
        # documents the space form `--key-delay <ms>`; GNU argp accepts it).
        subprocess.run(
            ["ydotool", "type", "--key-delay", "2", "--", text], check=True
        )

    def press_backspace(self, n: int) -> None:
        # ONE batched invocation: "14:1 14:0" = Backspace press+release (keycode 14);
        # explicit "-d 1" (1 ms between events) — never rely on the default delay for
        # an 80-press batch.
        if n <= 0:
            return
        subprocess.run(
            ["ydotool", "key", "-d", "1"] + ["14:1", "14:0"] * n, check=True
        )


class NullBackend(TypingBackend):
    """Types nothing. Headless E2E tests verify finals via the state file instead."""

    def type_text(self, text: str) -> None:
        logger.debug("null backend: suppressed %d chars", len(text))

    def press_backspace(self, n: int) -> None:
        logger.debug("null backend: suppressed %d backspaces", n)


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
        - backend == "null"    -> NullBackend (types nothing)

    Raises:
        ValueError: unknown backend name.
    """
    backend = cfg.backend
    if backend == "wtype":
        return _WtypeWithFallback()
    if backend == "ydotool":
        return YdotoolBackend()
    if backend == "null":
        return NullBackend()
    raise ValueError(f"unknown output.backend: {backend!r}")
