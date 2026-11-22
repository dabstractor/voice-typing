"""Input-method-v2 client probe. Run INSIDE the disposable desktop session:

    WAYLAND_DISPLAY=<private> XDG_RUNTIME_DIR=<private> python3 im_probe.py <root>

Becomes the seat's input method, then takes JSON commands on <root>/ctl.sock
(one line each) and logs protocol events to <root>/im.jsonl (size-capped).
Commands: state | insert | replace | preedit | endpreedit | grab | quit.
This is spike instrumentation, not production code: it proves what the
compositor/toolkit actually does with commit_string / delete_surrounding_text /
set_preedit_string, and how long the round trip takes.
"""
from __future__ import annotations

import json
import os
import select
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wlwire import Client, WlError

LOG_CAP = 64 * 1024
IFACE = "zwp_input_method_v2"


class Probe:
    def __init__(self, root: Path):
        self.root = root
        self.c = Client()
        self.c.registry = self.c.new("wl_registry")
        self.c.request(1, "wl_display", "get_registry", self.c.registry)
        self.c.roundtrip()
        self.log_bytes = 0
        self.dones = 0
        self.activated = False
        self.surround: dict | None = None
        self.grab = 0
        self.grab_keys = 0
        self.log({"ev": "globals",
                  "manager_v2": any(i == "zwp_input_method_manager_v2" for _n, (i, _v) in self.c.globals.items()),
                  "text_input_v3": any(i == "zwp_text_input_manager_v3" for _n, (i, _v) in self.c.globals.items()),
                  "n_globals": len(self.c.globals)})

    def log(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        if self.log_bytes >= LOG_CAP:
            return
        self.log_bytes += len(line)
        with open(self.root / "im.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line)

    def become_im(self) -> None:
        mgr_name = next(n for n, (i, _v) in self.c.globals.items() if i == "zwp_input_method_manager_v2")
        seat_name = next(n for n, (i, _v) in self.c.globals.items() if i == "wl_seat")
        mgr = self.c.bind(mgr_name, "zwp_input_method_manager_v2", 1)
        seat = self.c.bind(seat_name, "wl_seat", 1)
        self.im = self.c.new(IFACE)
        self.c.request(mgr, "zwp_input_method_manager_v2", "get_input_method", seat, self.im)
        # Two roundtrips so early activate events are drained before ctl setup.
        self.c.roundtrip()
        self.c.roundtrip()

    def on_event(self, ev) -> None:
        if ev.iface != IFACE and ev.iface != "zwp_input_method_keyboard_grab_v2":
            return
        t = round(time.monotonic() * 1000, 3)
        if ev.name == "done":
            self.dones += 1
            self.log({"t": t, "ev": "done", "dones": self.dones})
        elif ev.name == "activate":
            self.activated = True
            self.log({"t": t, "ev": "activate"})
        elif ev.name == "deactivate":
            self.activated = False
            self.log({"t": t, "ev": "deactivate"})
        elif ev.name == "surrounding_text":
            text, cursor, anchor = ev.args
            self.surround = {"text": text, "cursor": cursor, "anchor": anchor}
            self.log({"t": t, "ev": "surrounding_text", "bytes": len(text.encode()),
                      "cursor": cursor, "anchor": anchor, "head": text[:80]})
        elif ev.name == "key":
            self.grab_keys += 1
            self.log({"t": t, "ev": "grab_key", "key": ev.args[2], "state": ev.args[3]})
        elif ev.name in ("keymap", "modifiers", "repeat_info", "content_type", "text_change_cause"):
            self.log({"t": t, "ev": ev.name, "args": list(ev.args)[:4]})
        elif ev.name == "unavailable":
            self.log({"t": t, "ev": "unavailable"})
            raise WlError("input method slot taken (another IME is running)")

    def apply(self, cmd: dict) -> dict:
        t0 = time.monotonic()
        kind = cmd["cmd"]
        if kind == "state":
            return {"ok": True, "activated": self.activated, "dones": self.dones,
                    "surround": self.surround, "grab": bool(self.grab)}
        if not self.activated:
            return {"error": "not activated (no text-input focused)"}
        if kind == "insert":
            self.c.request(self.im, IFACE, "commit_string", cmd["text"])
        elif kind == "replace":
            self.c.request(self.im, IFACE, "delete_surrounding_text",
                           cmd.get("before", 0), cmd.get("after", 0))
            self.c.request(self.im, IFACE, "commit_string", cmd["text"])
        elif kind == "preedit":
            self.c.request(self.im, IFACE, "set_preedit_string",
                           cmd["text"], cmd.get("begin", 0), cmd.get("end", -1))
        elif kind == "endpreedit":
            self.c.request(self.im, IFACE, "commit_string", cmd.get("text", ""))
        elif kind == "grab":
            self.grab = self.c.new("zwp_input_method_keyboard_grab_v2")
            self.c.request(self.im, IFACE, "grab_keyboard", self.grab)
        else:
            return {"error": f"unknown cmd {kind}"}
        if kind != "grab":
            self.c.request(self.im, IFACE, "commit", self.dones)
        return {"ok": True, "t_ms": round((time.monotonic() - t0) * 1000, 3), "dones": self.dones}

    def serve(self) -> None:
        ctl_path = self.root / "ctl.sock"
        ctl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ctl.bind(str(ctl_path))
        ctl.listen(1)
        conn = None
        try:
            while True:
                socks = [self.c.s, ctl] + ([conn] if conn else [])
                r, _, _ = select.select(socks, [], [], 0.2)
                for s in r:
                    if s is ctl:
                        conn, _ = ctl.accept()
                        conn.setblocking(True)
                    elif s is conn:
                        try:
                            line = conn.recv(8192)
                        except ConnectionResetError:
                            conn = None
                            continue
                        if not line:
                            conn = None
                            continue
                        try:
                            reply = self.apply(json.loads(line.decode()))
                        except Exception as e:  # noqa: BLE001 - probe must survive bad rows
                            reply = {"error": repr(e)}
                        if reply.get("ok") or "error" in reply:
                            try:
                                conn.sendall(json.dumps(reply).encode() + b"\n")
                            except OSError:
                                conn = None
                        if json.loads(line.decode()).get("cmd") == "quit":
                            return
                    else:
                        try:
                            ev = self.c.next_event(0)
                            if ev:
                                self.on_event(ev)
                        except Exception as e:  # noqa: BLE001 - probe must survive odd events
                            self.log({"ev": "probe_error", "e": repr(e)[:200]})
                # Drain any remaining events each cycle.
                while True:
                    try:
                        ev = self.c.next_event(0)
                    except Exception as e:  # noqa: BLE001
                        self.log({"ev": "probe_error", "e": repr(e)[:200]})
                        break
                    if not ev:
                        break
                    self.on_event(ev)
        finally:
            if conn:
                conn.close()
            ctl.close()
            os.unlink(ctl_path)
            self.log({"ev": "exit", "activated": self.activated, "dones": self.dones,
                      "grab_keys": self.grab_keys, "log_bytes": self.log_bytes})


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not root:
        raise SystemExit("usage: im_probe.py <root>")
    probe = Probe(root)
    probe.become_im()
    probe.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
