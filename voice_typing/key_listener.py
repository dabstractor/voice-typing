"""Passive evdev keyboard listener for Backspace-cancel (PRD §4.2quater; P1.M2.T7.S2).

Watches the user's REAL keyboard(s) on /dev/input/event* from the DAEMON process and, while
dictation is armed with a pending streaming tail (PRD §4.2quater):
  - a physical Backspace press  -> cancel_cb()      (daemon.cancel(), P1.M2.T7.S1: rewind the
    typed fragment, drop the in-flight utterance, keep listening), and
  - any other keypress          -> other_key_cb()   (daemon.note_user_keypress(), T6.S3 rule 5:
    freeze the tail — never type over the user's cursor).

Design invariants (PRD hard requirements + P1.M2.T7.S2 PRP):
  - READ-ONLY, NEVER device.grab(): EVIOCGRAB is exclusive and would swallow the user's own
    keystrokes. Opening an InputDevice is read-only; grab() is never called here.
  - NEVER watch self-typing virtual devices: ydotool types via ydotoold's uinput node, which IS
    a /dev/input/event* device — watching it would let our own press_backspace()/type_text()
    rewinds self-trigger cancels/freezes (an infinite feedback loop). Devices whose name matches
    _EXCLUDE_NAME_RE are excluded at enumeration (wtype uses the Wayland virtual-keyboard
    protocol and never touches kernel input nodes — safe — but ydotool is the auto-fallback).
  - Only value==1 counts: 0 = release, 2 = autorepeat (a HELD Backspace must not fire repeated
    cancels) — parse_key_event().
  - Fail-safe: enumeration NEVER raises; unreadable nodes are skipped quietly (DEBUG); when no
    keyboard is watchable the daemon logs ONE warning at the first arm and stays silent — the
    `voicectl cancel` keybind (P1.M2.T7.S1) remains the fallback.
  - Pure-python + testable: this module NEVER imports voice_typing.daemon (callbacks are
    injected), and the per-event routing lives in the free function _pump_events() so the tests
    drive the exact code path the device threads run — no real hardware, no threads required.
    evdev is pure-python, so importing this module never pulls torch/RealtimeSTT into the
    daemon process (PRD §4.2bis import-purity rule).
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable, Iterable
from enum import Enum

import evdev
from evdev import ecodes

logger = logging.getLogger(__name__)

# Self-typing sources: ydotoold's uinput device (and any other uinput-based injector) must never
# be watched — see module docstring. Matched case-insensitively against the device NAME.
_EXCLUDE_NAME_RE = re.compile(r"(?i)(uinput|ydotool)")


class KeyEvent(Enum):
    """The only event classes the listener cares about (presses; everything else is None)."""

    BACKSPACE_PRESS = "backspace_press"
    OTHER_PRESS = "other_press"


def parse_key_event(ev_type: int, code: int, value: int) -> KeyEvent | None:
    """Classify one raw evdev event. The ONLY piece that sees raw (type, code, value) tuples.

    evdev event values: 1 = press, 0 = release, 2 = autorepeat (held key). Only EV_KEY presses
    count; releases, autorepeats and non-EV_KEY types (EV_SYN, EV_MSC, ...) return None. A
    held Backspace therefore fires exactly ONE cancel (the press), never autorepeat storms.
    """
    if ev_type != ecodes.EV_KEY or value != 1:
        return None
    if code == ecodes.KEY_BACKSPACE:
        return KeyEvent.BACKSPACE_PRESS
    return KeyEvent.OTHER_PRESS


def _device_paths() -> list[str]:
    """evdev.list_devices() defensively: the input nodes to consider, [] on any failure.

    Handles both the modern (path strings) and legacy (InputDevice objects) return shapes.
    """
    try:
        found = evdev.list_devices()
    except Exception:  # pylint: disable=broad-except — enumeration must NEVER raise
        logger.debug("key-listener: evdev.list_devices() failed", exc_info=True)
        return []
    paths: list[str] = []
    for item in found:
        path = item if isinstance(item, str) else getattr(item, "path", None)
        if isinstance(path, str):
            paths.append(path)
    return paths


def _device_acceptable(
    dev: "evdev.InputDevice", *, require_backspace_key: bool
) -> bool:
    """Name/capability filter (the SAFETY filters — applied even to [cancel].devices overrides).
    Never raises: a capabilities() failure is treated as 'not acceptable' (DEBUG logged)."""
    name = getattr(dev, "name", "") or ""
    if _EXCLUDE_NAME_RE.search(name):
        logger.debug(
            "key-listener: excluding virtual/self-typing device %r (name=%r)",
            getattr(dev, "path", "?"),
            name,
        )
        return False
    if not require_backspace_key:
        return True
    try:
        caps = dev.capabilities(verbose=False) or {}
    except Exception:  # pylint: disable=broad-except — a broken node is just skipped
        logger.debug(
            "key-listener: capabilities() failed for %r",
            getattr(dev, "path", "?"),
            exc_info=True,
        )
        return False
    keys = caps.get(ecodes.EV_KEY) or ()
    return ecodes.KEY_BACKSPACE in keys


def _probe_keyboard(path: str, *, require_backspace_key: bool) -> str | None:
    """Open-read-close one node: is it watchable? Returns the path, or None. NEVER raises.

    InputDevice(path) itself fails on unreadable nodes (OSError/PermissionError) — that is a
    skip, not an error (PRP gotcha). The probe fd is closed immediately; start() re-opens the
    surviving paths (a node vanishing between probe and open is handled there per-device).
    """
    try:
        dev = evdev.InputDevice(path)
    except Exception:  # pylint: disable=broad-except — unreadable node: skip quietly
        logger.debug(
            "key-listener: skipping unreadable device node %s", path, exc_info=True
        )
        return None
    try:
        return (
            path
            if _device_acceptable(dev, require_backspace_key=require_backspace_key)
            else None
        )
    finally:
        try:
            dev.close()
        except Exception:  # pylint: disable=broad-except — hygiene only
            pass


def enumerate_keyboard_devices(explicit: list[str]) -> list[str]:
    """Resolve which /dev/input nodes to watch. NEVER raises; [] on total failure.

    explicit non-empty ([cancel].devices): those paths VERBATIM — the user override wins on
    WHICH nodes, but never on safety: name-excluded (uinput/ydotool) and unreadable nodes are
    still skipped, and no KEY_BACKSPACE capability check is applied (the user pinned it).
    explicit empty: scan evdev.list_devices(), keeping only EV_KEY devices that expose
    KEY_BACKSPACE (a keyboard), excluding self-typing virtual devices.
    """
    try:
        if explicit:
            candidates = [
                p
                for p in (
                    _probe_keyboard(p, require_backspace_key=False) for p in explicit
                )
                if p is not None
            ]
        else:
            candidates = [
                p
                for p in (
                    _probe_keyboard(p, require_backspace_key=True)
                    for p in _device_paths()
                )
                if p is not None
            ]
    except Exception:  # pylint: disable=broad-except — belt & braces: never raise
        logger.debug("key-listener: device enumeration failed", exc_info=True)
        return []
    logger.debug(
        "key-listener: %d watchable keyboard device(s): %s", len(candidates), candidates
    )
    return candidates


def _pump_events(
    events: Iterable[tuple[int, int, int]],
    *,
    cancel_cb: Callable[[], None],
    other_key_cb: Callable[[], None],
    is_active: Callable[[], bool],
) -> None:
    """Consume an iterable of (type, code, value) tuples; route presses to the callbacks.

    Shared by the device reader threads (a read_loop adapted to 3-tuples) and by the tests
    (canned lists) so the tested code path IS the live one. Events are inert while
    is_active() is False (disarmed — the user's own editing must never be touched). A failing
    callback is logged at WARNING and the pump CONTINUES — one bad callback kills nothing.
    All callbacks run with NO listener-held locks (daemon.cancel() takes the daemon lock).
    """
    for ev_type, code, value in events:
        parsed = parse_key_event(ev_type, code, value)
        if parsed is None or not is_active():
            continue
        try:
            if parsed is KeyEvent.BACKSPACE_PRESS:
                cancel_cb()
            else:
                other_key_cb()
        except Exception:  # pylint: disable=broad-except — a callback failure kills nothing
            logger.warning("key-listener callback failed", exc_info=True)


class KeyListener:
    """One daemon reader thread per watched keyboard; routes presses to injected callbacks.

    Lifecycle: construct (PURE — no devices opened, no threads) -> start() exactly once
    (enumerates, opens each device READ-ONLY, spawns a daemon=True thread per device) ->
    optionally stop() (closes fds, joins briefly). start() is idempotent; stop() never raises
    and is safe before start(); the reader threads are daemon threads so they can never block
    process shutdown. Callbacks are invoked with NO listener-held locks (the daemon's
    cancel() takes its own lock internally — holding any here would risk deadlock).
    """

    def __init__(
        self,
        *,
        cancel_cb: Callable[[], None],
        other_key_cb: Callable[[], None],
        is_active: Callable[[], bool],
        devices: list[str] | None = None,
        enumerate_fn: Callable[[list[str]], list[str]] | None = None,
    ) -> None:
        self._cancel_cb = cancel_cb
        self._other_key_cb = other_key_cb
        self._is_active = is_active
        self._devices = list(
            devices or []
        )  # [cancel].devices override ([] = auto-enumerate)
        self._enumerate_fn = (
            enumerate_fn if enumerate_fn is not None else enumerate_keyboard_devices
        )
        self._lifecycle = (
            threading.Lock()
        )  # guards start()/stop() idempotency ONLY (never held across callbacks)
        self._stop_event = threading.Event()
        self._started = False
        self._watched: list[str] = []
        self._opened: list["evdev.InputDevice"] = []
        self._threads: list[threading.Thread] = []

    @property
    def cancel_cb(self) -> Callable[[], None]:
        """The injected Backspace-press callback (read-only; exposed for wiring tests)."""
        return self._cancel_cb

    @property
    def other_key_cb(self) -> Callable[[], None]:
        """The injected other-keypress callback (read-only; exposed for wiring tests)."""
        return self._other_key_cb

    @property
    def started(self) -> bool:
        """True once start() has run (even if it found zero devices)."""
        return self._started

    @property
    def device_count(self) -> int:
        """How many devices the reader threads are actually watching (0 = none watchable)."""
        return len(self._watched)

    def start(self) -> list[str]:
        """Enumerate + open devices + spawn one daemon reader thread per device. Idempotent.

        Returns the watched device paths ([] when nothing is readable — the caller logs the
        once-only WARNING). NEVER raises: enumeration and every per-device open are guarded.
        """
        with self._lifecycle:
            if self._started:
                return list(self._watched)
            self._started = True
        try:
            paths = self._enumerate_fn(self._devices)
        except Exception:  # pylint: disable=broad-except — a broken enumerate_fn is a skip
            logger.debug("key-listener: enumeration failed", exc_info=True)
            paths = []
        watched: list[str] = []
        for path in paths:
            try:
                dev = evdev.InputDevice(
                    path
                )  # READ-ONLY; grab() is never called (PRD rule)
            except Exception:  # pylint: disable=broad-except — vanished/unreadable since probe
                logger.debug(
                    "key-listener: device unreadable at open: %s", path, exc_info=True
                )
                continue
            thread = threading.Thread(
                target=self._run_device,
                args=(dev,),
                name=f"voice-typing-key-listener-{path}",
                daemon=True,  # never blocks daemon shutdown (process exit reaps it)
            )
            self._opened.append(dev)
            self._threads.append(thread)
            thread.start()
            watched.append(path)
        self._watched = watched
        logger.debug("key-listener: watching %d device(s): %s", len(watched), watched)
        return list(watched)

    def stop(self) -> None:
        """Close device fds + join reader threads briefly. Idempotent, NEVER raises, safe
        before start(). Hygiene rather than correctness: the threads are daemon=True, so the
        process exit alone is safe (close-vs-select is racy on Linux; join() is bounded)."""
        with self._lifecycle:
            opened = list(self._opened)
            threads = list(self._threads)
            self._opened = []
            self._threads = []
        self._stop_event.set()
        for dev in opened:
            try:
                dev.close()  # unblocks the reader's read_loop (it then exits quietly)
            except Exception:  # pylint: disable=broad-except — best-effort
                pass
        for thread in threads:
            thread.join(timeout=1.0)

    def _run_device(self, dev: "evdev.InputDevice") -> None:
        """Thread body: pump one device's events until it dies or stop() closes the fd."""
        path = getattr(dev, "path", "?")
        active = (
            self._is_active
        )  # captured locally: read OUTSIDE any lock on every event
        stopped = self._stop_event.is_set

        def _events() -> Iterable[tuple[int, int, int]]:
            # Generator adapter so the LIVE path and the tested path share _pump_events.
            for ev in dev.read_loop():
                yield (ev.type, ev.code, ev.value)

        def _gate() -> bool:
            # Inert once stopped (belt & braces — the fd is closed anyway) or disarmed.
            return not stopped() and active()

        try:
            _pump_events(
                _events(),
                cancel_cb=self._cancel_cb,
                other_key_cb=self._other_key_cb,
                is_active=_gate,
            )
        except Exception:  # pylint: disable=broad-except — a dying device exits its thread quietly
            logger.debug("key-listener: device reader exited: %s", path, exc_info=True)
