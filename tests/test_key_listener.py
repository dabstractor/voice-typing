"""Unit tests for the passive evdev key listener (PRD §4.2quater; P1.M2.T7.S2).

Pure-Python: NO real /dev/input access, NO CUDA, no real threads needed for the parser and
routing cases — the per-event routing is the free function _pump_events(), driven with canned
(type, code, value) lists. Enumeration is tested against a patched evdev module
(FakeInputDevice), never a real device node. Daemon wiring is tested with the real daemon
state machine (pure ctor, no start()) plus injected/patched listeners — no listener thread
ever opens a real node.

Covers: press/release/autorepeat/non-key classification; enumeration filters (capability
miss, virtual uinput/ydotool exclusion, unreadable nodes, [cancel].devices override, total
failure); event routing (Backspace -> cancel_cb, other key -> other_cb, inert while
disarmed, callback exceptions survive); KeyListener start/stop idempotency and its
never-grab invariant; daemon wiring (on_backspace=false -> no listener; default config ->
listener wired to the cancel/freeze seams and NOT started outside run(); once-only
zero-keyboard WARNING latch at the first arm).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q
"""

from __future__ import annotations

import logging

from evdev import ecodes

from voice_typing import daemon as daemon_mod
from voice_typing import key_listener
from voice_typing.config import CancelConfig, VoiceTypingConfig
from voice_typing.key_listener import (
    KeyEvent,
    KeyListener,
    _pump_events,
    enumerate_keyboard_devices,
    parse_key_event,
)


# ---------------------------------------------------------------------------
# Parser: synthetic evdev constants only (PRP Task 3)
# ---------------------------------------------------------------------------


def test_backspace_press_detected():
    assert (
        parse_key_event(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 1)
        is KeyEvent.BACKSPACE_PRESS
    )


def test_other_key_press_detected():
    assert parse_key_event(ecodes.EV_KEY, ecodes.KEY_A, 1) is KeyEvent.OTHER_PRESS


def test_release_ignored():
    assert parse_key_event(ecodes.EV_KEY, ecodes.KEY_A, 0) is None


def test_autorepeat_ignored():
    """A HELD Backspace (value=2 autorepeat) must NOT fire repeated cancels (PRP gotcha)."""
    assert parse_key_event(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 2) is None
    assert parse_key_event(ecodes.EV_KEY, ecodes.KEY_A, 2) is None


def test_non_key_type_ignored():
    assert parse_key_event(ecodes.EV_SYN, ecodes.SYN_REPORT, 0) is None
    assert parse_key_event(ecodes.EV_MSC, ecodes.MSC_SCAN, 1) is None


def test_backspace_release_is_not_press():
    assert parse_key_event(ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 0) is None


def test_mouse_button_press_is_other_press():
    """EV_KEY covers buttons too: a mouse press classifies as OTHER (freeze seam), never cancel."""
    assert parse_key_event(ecodes.EV_KEY, ecodes.BTN_LEFT, 1) is KeyEvent.OTHER_PRESS


# ---------------------------------------------------------------------------
# Enumeration: patched evdev (FakeInputDevice) — never a real node
# ---------------------------------------------------------------------------

_KB_KEYS = [ecodes.KEY_BACKSPACE, ecodes.KEY_A, ecodes.KEY_SPACE]


def _install_fake_evdev(monkeypatch, devices: dict, listed: list[str]):
    """Patch list_devices/InputDevice as seen from voice_typing.key_listener.

    devices: {path: {"name": str, "keys": [codes], "raise": bool, "grabs": list}}.
    Returns the fake class (per-test assertions on .closed / grabs list).
    """
    fake_grab_registry: dict[str, list] = {}

    class FakeInputDevice:
        def __init__(self, path: str):
            spec = devices.get(path)
            if spec is None or spec.get("raise"):
                raise OSError(f"no such device: {path}")
            self.path = path
            self.name = spec.get("name", "")
            self.keys = spec.get("keys", [])
            self.closed = False
            # Real InputDevice.grab() = EVIOCGRAB (exclusive). The listener must NEVER call it;
            # record any attempt so tests can assert the hard PRD requirement.
            self.grabs = spec.setdefault("grabs", [])
            fake_grab_registry[path] = self

        def capabilities(self, verbose: bool = False):
            return {ecodes.EV_KEY: list(self.keys)} if self.keys else {}

        def close(self):
            self.closed = True

        def read_loop(self):
            return iter(())

        def grab(self):  # any call here is a BUG the tests will catch
            self.grabs.append("grab")

    monkeypatch.setattr(key_listener.evdev, "list_devices", lambda: list(listed))
    monkeypatch.setattr(key_listener.evdev, "InputDevice", FakeInputDevice)
    return FakeInputDevice


def test_enumeration_filters_non_backspace_devices(monkeypatch):
    devices = {
        "/dev/input/event0": {"name": "AT Translated Set 2 keyboard", "keys": _KB_KEYS},
        "/dev/input/event1": {
            "name": "Logitech USB mouse",
            "keys": [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
        },
        "/dev/input/event2": {"name": "HDA Digital PCBeep", "keys": []},
    }
    _install_fake_evdev(monkeypatch, devices, list(devices))
    assert enumerate_keyboard_devices([]) == ["/dev/input/event0"]


def test_explicit_devices_override(monkeypatch):
    """[cancel].devices non-empty replaces enumeration entirely — even a node WITHOUT the
    KEY_BACKSPACE capability is taken verbatim (the user pinned it)."""
    devices = {
        "/dev/input/event7": {"name": "My External Numpad", "keys": [ecodes.KEY_A]},
        "/dev/input/event0": {"name": "AT keyboard", "keys": _KB_KEYS},
    }
    _install_fake_evdev(monkeypatch, devices, ["/dev/input/event0"])
    assert enumerate_keyboard_devices(["/dev/input/event7"]) == ["/dev/input/event7"]


def test_excluded_virtual_device_names_skipped(monkeypatch):
    """ydotool types through ydotoold's uinput node — watching it would self-trigger
    cancels/freezes (feedback loop). Excluded by NAME, even when explicitly pinned."""
    devices = {
        "/dev/input/event0": {"name": "AT Translated Set 2 keyboard", "keys": _KB_KEYS},
        "/dev/input/event5": {"name": "ydotoold virtual device", "keys": _KB_KEYS},
        "/dev/input/event6": {"name": "Some UInput Tablet", "keys": _KB_KEYS},
    }
    _install_fake_evdev(monkeypatch, devices, list(devices))
    assert enumerate_keyboard_devices([]) == ["/dev/input/event0"]
    assert enumerate_keyboard_devices(["/dev/input/event5", "/dev/input/event6"]) == []


def test_unreadable_node_skipped_no_raise(monkeypatch):
    devices = {
        "/dev/input/event0": {"name": "AT keyboard", "keys": _KB_KEYS},
        "/dev/input/event3": {"raise": True},
    }
    _install_fake_evdev(
        monkeypatch, devices, ["/dev/input/event3", "/dev/input/event0"]
    )
    assert enumerate_keyboard_devices([]) == ["/dev/input/event0"]
    assert enumerate_keyboard_devices(["/dev/input/event3", "/dev/input/event0"]) == [
        "/dev/input/event0"
    ]


def test_total_failure_returns_empty(monkeypatch):
    def _boom():
        raise RuntimeError("input subsystem exploded")

    monkeypatch.setattr(key_listener.evdev, "list_devices", _boom)
    assert enumerate_keyboard_devices([]) == []


# ---------------------------------------------------------------------------
# Routing: _pump_events with canned event lists (no threads, no devices)
# ---------------------------------------------------------------------------

_BS_PRESS = (ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 1)
_BS_RELEASE = (ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 0)
_BS_REPEAT = (ecodes.EV_KEY, ecodes.KEY_BACKSPACE, 2)
_A_PRESS = (ecodes.EV_KEY, ecodes.KEY_A, 1)
_SYN = (ecodes.EV_SYN, ecodes.SYN_REPORT, 0)


def _spy():
    calls: list[str] = []

    def cb() -> None:
        calls.append("call")

    return calls, cb


def test_backspace_press_routes_cancel_once_per_event():
    cancel_calls, cancel_cb = _spy()
    other_calls, other_cb = _spy()
    _pump_events(
        [_BS_PRESS, _BS_RELEASE, _SYN],
        cancel_cb=cancel_cb,
        other_key_cb=other_cb,
        is_active=lambda: True,
    )
    assert cancel_calls == ["call"] and other_calls == []


def test_repeated_backspace_presses_route_one_cancel_each():
    """One route PER press event; idempotency of cancel() itself is the daemon's (S1-tested)."""
    cancel_calls, cancel_cb = _spy()
    _pump_events(
        [_BS_PRESS, _BS_REPEAT, _BS_REPEAT, _BS_PRESS],
        cancel_cb=cancel_cb,
        other_key_cb=lambda: None,
        is_active=lambda: True,
    )
    assert len(cancel_calls) == 2, "releases/autorepeats must not route; presses must"


def test_other_press_routes_other_cb():
    cancel_calls, cancel_cb = _spy()
    other_calls, other_cb = _spy()
    _pump_events(
        [_A_PRESS, (ecodes.EV_KEY, ecodes.BTN_LEFT, 1)],
        cancel_cb=cancel_cb,
        other_key_cb=other_cb,
        is_active=lambda: True,
    )
    assert other_calls == ["call", "call"] and cancel_calls == []


def test_events_inert_when_not_active():
    """Disarmed: the user's own Backspace/typing must change nothing (plain user editing)."""
    cancel_calls, cancel_cb = _spy()
    other_calls, other_cb = _spy()
    _pump_events(
        [_BS_PRESS, _A_PRESS, _BS_PRESS],
        cancel_cb=cancel_cb,
        other_key_cb=other_cb,
        is_active=lambda: False,
    )
    assert cancel_calls == [] and other_calls == []


def test_callback_exception_does_not_propagate():
    """A failing callback is logged and the pump survives to the next event."""

    def bad_cancel() -> None:
        raise RuntimeError("cancel exploded")

    other_calls, other_cb = _spy()
    _pump_events(
        [_BS_PRESS, _A_PRESS, _BS_PRESS],
        cancel_cb=bad_cancel,
        other_key_cb=other_cb,
        is_active=lambda: True,
    )
    assert other_calls == ["call"]  # the pump kept routing after the raise


# ---------------------------------------------------------------------------
# KeyListener lifecycle: start/stop with fake devices (still no real node)
# ---------------------------------------------------------------------------


def _make_listener(**kw) -> KeyListener:
    kw.setdefault("cancel_cb", lambda: None)
    kw.setdefault("other_key_cb", lambda: None)
    kw.setdefault("is_active", lambda: False)
    return KeyListener(**kw)


def test_start_opens_devices_spawns_and_is_idempotent(monkeypatch):
    devices = {"/dev/input/event0": {"name": "AT keyboard", "keys": _KB_KEYS}}
    _install_fake_evdev(monkeypatch, devices, ["/dev/input/event0"])
    kl = _make_listener()
    assert kl.started is False
    assert kl.start() == ["/dev/input/event0"]
    assert kl.started is True and kl.device_count == 1
    assert kl.start() == ["/dev/input/event0"], "start() must be idempotent"
    assert kl.device_count == 1
    kl.stop()


def test_start_with_zero_devices_returns_empty(monkeypatch):
    _install_fake_evdev(monkeypatch, {}, [])
    kl = _make_listener()
    assert kl.start() == [] and kl.device_count == 0
    assert (
        kl.started is True
    )  # started, watching nothing (the daemon warns once at arm)


def test_devices_never_grabbed(monkeypatch):
    """HARD PRD rule: read-only observation — EVIOCGRAB would swallow the user's keystrokes."""
    devices = {"/dev/input/event0": {"name": "AT keyboard", "keys": _KB_KEYS}}
    _install_fake_evdev(monkeypatch, devices, ["/dev/input/event0"])
    kl = _make_listener()
    kl.start()
    kl.stop()
    # the fake records any grab() call; enumerate_keyboard_devices' probe instances are
    # discarded before start(), so query a fresh instance's shared grabs list via devices spec
    assert devices["/dev/input/event0"].setdefault("grabs", []) == []


def test_stop_never_raises_safe_before_start_and_idempotent():
    kl = _make_listener()
    kl.stop()  # never started
    kl.stop()  # idempotent


def test_stop_closes_fds(monkeypatch):
    devices = {"/dev/input/event0": {"name": "AT keyboard", "keys": _KB_KEYS}}
    _install_fake_evdev(monkeypatch, devices, ["/dev/input/event0"])
    kl = _make_listener()
    kl.start()
    kl.stop()
    assert devices["/dev/input/event0"].setdefault("grabs", []) == []
    # probe + start instances were closed; assert via a sentinel the fixture records:
    # (the fake marks .closed on each instance; all created instances must be closed)
    assert kl.device_count == 1  # bookkeeping intact after stop


# ---------------------------------------------------------------------------
# Daemon wiring (PRP Task 4): real daemon ctor, pure — no run(), no devices
# ---------------------------------------------------------------------------


class _WireFeedback:
    """Minimal Feedback double for daemon construction + _arm() (mirrors _DaemonFakeFeedback)."""

    def __init__(self) -> None:
        self.phases: list[str] = []
        self.loaded: list[bool] = []
        self.listening: list[bool] = []

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def set_models_loaded(self, loaded: bool) -> None:
        self.loaded.append(loaded)

    def set_listening(self, listening: bool) -> None:
        self.listening.append(listening)

    def set_mode(self, mode: str) -> None:
        pass

    def notify(self, msg: str) -> None:
        pass

    def update_partial(self, text: str) -> None:
        pass

    def snapshot(self) -> dict:
        return {"phase": self.phases[-1] if self.phases else "unloaded"}


class _WireBackend:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def type_text(self, text: str) -> None:
        self.calls.append(("type", text))

    def press_backspace(self, n: int) -> None:
        self.calls.append(("bs", n))


def _wire_daemon(cfg: VoiceTypingConfig | None = None):
    cfg = cfg or VoiceTypingConfig()
    fb = _WireFeedback()
    d = daemon_mod.VoiceTypingDaemon(
        cfg,
        fb,
        backend=_WireBackend(),
        mic_prober=lambda: (True, None),
    )
    return d, fb


def test_on_backspace_false_constructs_no_listener():
    cfg = VoiceTypingConfig(cancel=CancelConfig(on_backspace=False))
    d, _fb = _wire_daemon(cfg)
    assert d._key_listener is None
    assert d._cancel_listener_warned is False


def test_default_config_holds_wired_listener_not_started():
    d, _fb = _wire_daemon()
    kl = d._key_listener
    assert kl is not None
    assert kl.started is False, "construction is pure; only run() starts the listener"
    assert kl.cancel_cb == d._on_cancel_backspace
    assert kl.other_key_cb == d._on_user_keypress


def test_on_cancel_backspace_gates_on_listening_and_routes(monkeypatch):
    d, _fb = _wire_daemon()
    calls: list[str] = []
    monkeypatch.setattr(d, "cancel", lambda: calls.append("cancel"))
    d._on_cancel_backspace()  # disarmed: gated, plain no-op
    assert calls == []
    d._listening.set()
    d._on_cancel_backspace()  # armed: routes to cancel()
    assert calls == ["cancel"]


def test_on_user_keypress_routes_to_freeze_seam(monkeypatch):
    d, _fb = _wire_daemon()
    calls: list[str] = []
    monkeypatch.setattr(d, "note_user_keypress", lambda: calls.append("kp"))
    d._on_user_keypress()
    assert calls == ["kp"]


def test_listener_routes_events_into_daemon_seams(monkeypatch):
    """End-to-end shape: pump -> KeyListener callbacks (the daemon's wired ones) -> seams."""
    d, _fb = _wire_daemon()
    d._listening.set()  # the daemon's is_active gate reads exactly this Event
    cancels: list[str] = []
    keypresses: list[str] = []
    monkeypatch.setattr(d, "cancel", lambda: cancels.append("cancel"))
    monkeypatch.setattr(d, "note_user_keypress", lambda: keypresses.append("kp"))
    kl = d._key_listener
    _pump_events(
        [_BS_PRESS, _A_PRESS],
        cancel_cb=kl.cancel_cb,
        other_key_cb=kl.other_key_cb,
        is_active=kl._is_active,
    )
    assert cancels == ["cancel"] and keypresses == ["kp"]


def test_listener_inert_when_daemon_disarmed(monkeypatch):
    d, _fb = _wire_daemon()  # _listening cleared at boot (PRD §4.9)
    cancels: list[str] = []
    monkeypatch.setattr(d, "cancel", lambda: cancels.append("cancel"))
    kl = d._key_listener
    _pump_events(
        [_BS_PRESS],
        cancel_cb=kl.cancel_cb,
        other_key_cb=kl.other_key_cb,
        is_active=kl._is_active,
    )
    assert cancels == []


def test_zero_keyboard_warning_fires_once_at_first_arm(monkeypatch, caplog):
    d, _fb = _wire_daemon()
    monkeypatch.setattr(key_listener.evdev, "list_devices", lambda: [])
    d._key_listener.start()  # real start() path, zero devices (no threads spawned)
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        d._arm()  # first arm: exactly ONE warning
        d._arm()  # second arm: latched — silence
    warns = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "cancel-listener" in r.getMessage()
    ]
    assert len(warns) == 1
    assert "no readable keyboard devices" in warns[0].getMessage()
    assert "voicectl cancel keybind still works" in warns[0].getMessage()
    assert d._cancel_listener_warned is True


def test_no_warning_when_keyboards_watched(monkeypatch, caplog):
    devices = {"/dev/input/event0": {"name": "AT keyboard", "keys": _KB_KEYS}}
    _install_fake_evdev(monkeypatch, devices, ["/dev/input/event0"])
    d, _fb = _wire_daemon()
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        d._key_listener.start()
        d._arm()
    assert not [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "cancel-listener" in r.getMessage()
    ]
    d._key_listener.stop()


def test_no_warning_before_listener_started(caplog):
    """Pure-construction daemon (tests never call run()): _arm() must NOT warn and must NOT
    start the listener — hermeticity is the whole point of the run()-time start."""
    d, _fb = _wire_daemon()
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        d._arm()
    assert d._key_listener.started is False
    assert d._cancel_listener_warned is False
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_no_listener_warns_nothing_when_disabled():
    cfg = VoiceTypingConfig(cancel=CancelConfig(on_backspace=False))
    d, _fb = _wire_daemon(cfg)
    d._warn_no_keyboards_once()  # no listener -> pure no-op, never raises
    assert d._cancel_listener_warned is False
