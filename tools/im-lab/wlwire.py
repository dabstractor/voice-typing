"""Minimal Wayland wire-protocol client — stdlib only, no pywayland dependency.

Scope: exactly what the input-method spike needs. Core display/registry/seat,
zwp_input_method_v2, and its keyboard grab. Argument kinds used here:
u = uint, i = int, s = string, o = object id, n = new_id (u32), h = fd.
Event/request opcode order MUST match the protocol XML; see im-lab/README.md
for provenance (Hyprland vendored input-method-unstable-v2.xml, wlr-protocols).
"""
from __future__ import annotations

import os
import socket
import struct


class WlError(Exception):
    pass


def u32(x) -> bytes:
    return struct.pack("<I", x & 0xFFFFFFFF)


def i32(x) -> bytes:
    return struct.pack("<i", x)


def wstr(s: str) -> bytes:
    b = s.encode("utf-8") + b"\0"
    return struct.pack("<I", len(b)) + b + b"\0" * (-len(b) % 4)


# (name, arg kinds) in protocol-XML order — opcodes are the list indexes.
REQUESTS: dict[str, list[tuple[str, str]]] = {
    "wl_display": [("sync", "n"), ("get_registry", "n")],
    "wl_registry": [("bind", "usun")],
    "wl_seat": [("get_pointer", "n"), ("get_keyboard", "n"), ("get_touch", "n"), ("release", "")],
    "zwp_input_method_manager_v2": [("get_input_method", "on"), ("destroy", "")],
    "zwp_input_method_v2": [
        ("commit_string", "s"),
        ("set_preedit_string", "sii"),
        ("delete_surrounding_text", "uu"),
        ("commit", "u"),
        ("get_input_popup_surface", "no"),
        ("grab_keyboard", "n"),
        ("destroy", ""),
    ],
    "zwp_input_method_keyboard_grab_v2": [("release", "")],
}

EVENTS: dict[str, list[tuple[str, str]]] = {
    "wl_display": [("error", "ous"), ("delete_id", "u")],
    "wl_registry": [("global", "usu"), ("global_remove", "u")],
    "wl_seat": [("capabilities", "u"), ("name", "s")],
    "wl_callback": [("done", "u")],
    "zwp_input_method_v2": [
        ("activate", ""),
        ("deactivate", ""),
        ("surrounding_text", "suu"),
        ("text_change_cause", "u"),
        ("content_type", "uu"),
        ("done", ""),
        ("unavailable", ""),
    ],
    "zwp_input_method_keyboard_grab_v2": [
        ("keymap", "uhu"),
        ("key", "uuuu"),
        ("modifiers", "uuuuu"),
        ("repeat_info", "ii"),
    ],
}


class Event:
    __slots__ = ("obj", "iface", "name", "args")

    def __init__(self, obj: int, iface: str, name: str, args: tuple):
        self.obj, self.iface, self.name, self.args = obj, iface, name, args

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Event({self.iface}.{self.name}{self.args} obj={self.obj})"


class Client:
    def __init__(self, display: str | None = None):
        d = display or os.environ.get("WAYLAND_DISPLAY")
        if not d:
            raise WlError("WAYLAND_DISPLAY not set")
        path = d if d.startswith("/") else os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), d)
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.connect(path)
        self.buf = bytearray()
        self.next_id = 1
        self.ifaces: dict[int, str] = {1: "wl_display"}
        self.registry = 0
        self.globals: dict[int, tuple[str, int]] = {}
        self.pending_fds: list[int] = []

    # ---- object ids ------------------------------------------------------
    def new(self, iface: str) -> int:
        self.next_id += 1
        if self.next_id >= 0xFF000000:
            raise WlError("client id space exhausted")
        self.ifaces[self.next_id] = iface
        return self.next_id

    def bind(self, global_name: int, iface: str, version: int = 1) -> int:
        obj = self.new(iface)
        self.request(self.registry, "wl_registry", "bind", global_name, iface, version, obj)
        return obj

    # ---- requests ---------------------------------------------------------
    def request(self, obj: int, iface: str, name: str, *args) -> None:
        table = REQUESTS.get(iface)
        if table is None or name not in [t[0] for t in table]:
            raise WlError(f"unknown request {iface}.{name}")
        opcode = [t[0] for t in table].index(name)
        kinds = [t for t in table if t[0] == name][0][1]
        if len(kinds) != len(args):
            raise WlError(f"{iface}.{name}: {len(kinds)} args expected, got {len(args)}")
        payload = bytearray()
        for kind, arg in zip(kinds, args):
            if kind == "u" or kind == "n" or kind == "o":
                payload += u32(arg)
            elif kind == "i":
                payload += i32(arg)
            elif kind == "s":
                payload += wstr(arg)
            else:
                raise WlError(f"unsupported arg kind {kind}")
        msg = struct.pack("<IHH", obj, opcode, 8 + len(payload)) + bytes(payload)
        self.s.sendall(msg)

    # ---- event pump -------------------------------------------------------
    def _fill(self, need: int, timeout: float | None) -> bool:
        while len(self.buf) < need:
            if timeout is not None:
                r, _, _ = __import__("select").select([self.s], [], [], timeout)
                if not r:
                    return False
            data, anc, _flags, _addr = self.s.recvmsg(65536, socket.CMSG_SPACE(28))
            if not data:
                raise WlError("compositor closed the connection")
            self.buf += data
            for cmsg_level, cmsg_type, cmsg_data in anc:
                if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
                    for fd in struct.unpack(f"<{len(cmsg_data) // 4}i", cmsg_data):
                        self.pending_fds.append(fd)
            if timeout is not None:
                timeout = max(timeout - 0.01, 0.01)
        return True

    def next_event(self, timeout: float | None = 0.5) -> Event | None:
        if not self._fill(8, timeout):
            return None
        obj, opcode, size = struct.unpack_from("<IHH", self.buf)
        if size < 8:
            raise WlError(f"bad event size {size}")
        if not self._fill(size, 0.2):
            return None
        body = bytes(self.buf[8:size])
        del self.buf[:size]
        iface = self.ifaces.get(obj)
        if iface is None:
            return Event(obj, "unknown", "?", ())
        table = EVENTS.get(iface, [])
        if opcode >= len(table):
            return Event(obj, iface, f"op{opcode}", ())
        name, kinds = table[opcode]
        args, pos = [], 0
        for kind in kinds:
            if kind == "u" or kind == "i" or kind == "o":
                (v,) = struct.unpack_from("<i" if kind == "i" else "<I", body, pos)
                args.append(v)
                pos += 4
            elif kind == "s":
                (n,) = struct.unpack_from("<I", body, pos)
                pos += 4
                raw = body[pos:pos + n]
                pos += (n + 3) & ~3
                args.append(raw[:-1].decode("utf-8", "replace"))
            elif kind == "h":
                fd = self.pending_fds.pop(0) if self.pending_fds else -1
                if fd >= 0:
                    os.close(fd)  # spike keeps no keymap; close to avoid leaks
                args.append(fd)
            else:
                raise WlError(f"unsupported event kind {kind}")
        return Event(obj, iface, name, tuple(args))

    def roundtrip(self, timeout: float = 5.0) -> None:
        cb = self.new("wl_callback")
        self.request(1, "wl_display", "sync", cb)
        import time
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise WlError("sync roundtrip timed out")
            ev = self.next_event(left)
            if ev is None:
                continue
            self.handle(ev)
            if ev.iface == "wl_callback" and ev.obj == cb:
                return

    def handle(self, ev: Event) -> None:  # override / extend
        if ev.iface == "wl_display" and ev.name == "error":
            raise WlError(f"protocol error on {ev.args[0]}: {ev.args[1]} {ev.args[2]}")
        if ev.iface == "wl_registry" and ev.name == "global":
            self.globals[ev.args[0]] = (ev.args[1], ev.args[2])
