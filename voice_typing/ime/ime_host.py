"""ime_host: seat input-method host serving the JSONL protocol on stdin/stdout.

Evolved from tools/im-lab/im_probe.py (that lab copy stays byte-identical as
R.2 evidence; its ctl.sock was lab instrumentation — this host serves the
P1.M4.T1.S2 subprocess pipes instead, and never runs in the foreground of a
test: unit tests inject fakes via ImeHost(client, out, log_path)).

Usage (from the S2 subprocess host):
    python -m voice_typing.ime.ime_host [event-log-path]

Becomes the seat's input method (get_registry → roundtrip → bind manager+seat
→ get_input_method → two roundtrips, proven in the lab), then serves JSONL:
requests acquire/show/verify/leave/ping (+ reserved cancel), replies echoing
the caller id, async id-less {"ev":...} event lines interleaved on stdout,
and a 64 KiB-capped event log at argv[1] (default under $XDG_RUNTIME_DIR).
`unavailable` → event line + log + clean exit(0) (one-IM-per-seat; S2 marks
the route unavailable).

TRANSPORT ONLY: acquire's handle/revision is a placeholder passthrough; show
does no ownership/units verification and no chunking strategy (T2/T3); no
takeover policy (T4 — it only forwards the event lines); no subprocess
supervision (S2). show NEVER retries (R.5): one bounded wait for the
compositor `done`, then `unknown` and the loop moves on.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from . import protocol
from .wlwire import Client, WlError

IFACE = "zwp_input_method_v2"
MANAGER_IFACE = "zwp_input_method_manager_v2"
GRAB_IFACE = "zwp_input_method_keyboard_grab_v2"
SHOW_CONFIRM_WAIT = 0.5  # s — ONE bounded wait for the compositor `done`; no retry, ever


class ImeHost:
    """JSONL server over an injected wlwire Client (or fake) and an output stream."""

    def __init__(self, client, out, log_path=None):
        self.c = client
        self.out = out
        self.logw = protocol.EventLogWriter(log_path)
        self.im = 0
        self.dones = 0
        self.activated = False
        self.surround: dict | None = None
        self.grab = 0
        self.grab_keys = 0
        self.stopped = False  # set on `unavailable` → serve() returns cleanly

    # ---- become the seat's input method (probe lineage, verbatim sequence) ----
    def become_im(self) -> None:
        c = self.c
        c.registry = c.new("wl_registry")
        c.request(1, "wl_display", "get_registry", c.registry)
        c.roundtrip()
        try:
            mgr_name = next(n for n, (i, _v) in c.globals.items() if i == MANAGER_IFACE)
            seat_name = next(n for n, (i, _v) in c.globals.items() if i == "wl_seat")
        except StopIteration:
            raise WlError("compositor does not advertise zwp_input_method_manager_v2/wl_seat")
        mgr = c.bind(mgr_name, MANAGER_IFACE, 1)
        seat = c.bind(seat_name, "wl_seat", 1)
        self.im = c.new(IFACE)
        c.request(mgr, MANAGER_IFACE, "get_input_method", seat, self.im)
        # Two roundtrips so early activate events are drained before serving.
        c.roundtrip()
        c.roundtrip()
        self._log(protocol.make_event(
            "globals",
            manager_v2=any(i == MANAGER_IFACE for _n, (i, _v) in c.globals.items()),
            n_globals=len(c.globals)))

    # ---- event handling: forward to stdout (the T4 feed) + capped log ----
    def on_event(self, ev) -> None:
        if ev.iface != IFACE and ev.iface != GRAB_IFACE:
            return
        if ev.name == "done":
            self.dones += 1
            self._emit(protocol.make_event("done", dones=self.dones))
        elif ev.name == "activate":
            self.activated = True
            self._emit(protocol.make_event("activate"))
        elif ev.name == "deactivate":
            self.activated = False
            self._emit(protocol.make_event("deactivate"))
        elif ev.name == "surrounding_text":
            text, cursor, anchor = ev.args
            self.surround = {"text": text, "cursor": cursor, "anchor": anchor}
            self._emit(protocol.make_event("surrounding_text",
                                           bytes=len(text.encode()), cursor=cursor,
                                           anchor=anchor, head=text[:80]))
        elif ev.name == "key":
            self.grab_keys += 1
            self._emit(protocol.make_event("grab_key", key=ev.args[2], state=ev.args[3]))
        elif ev.name == "unavailable":
            self._emit(protocol.make_event("unavailable"))
            self.stopped = True
        elif ev.name in ("keymap", "modifiers", "repeat_info", "content_type",
                         "text_change_cause"):
            self._emit(protocol.make_event(ev.name, args=list(ev.args)[:4]))

    def _emit(self, ev: dict) -> None:
        self.logw.append(ev)
        self.out.write(protocol.encode(ev).decode("utf-8"))
        self.out.flush()

    def _log(self, obj: dict) -> None:
        self.logw.append(obj)

    # ---- request handling -------------------------------------------------
    def handle_line(self, line) -> None:
        """Decode → validate → dispatch → exactly ONE reply line; then drain events."""
        if not str(line).strip():
            return
        try:
            obj = protocol.decode(line)
            cmd, err = protocol.validate_request(obj)
            reply = self._dispatch(cmd, obj) if not err else protocol.make_error(obj["id"], err)
        except protocol.ProtocolError as e:
            reply = protocol.make_error(-1, f"bad json: {e}")
        self.out.write(protocol.encode(reply).decode("utf-8"))
        self.out.flush()
        self._drain_events()

    def _dispatch(self, cmd: str, obj: dict) -> dict:
        rid = obj["id"]
        if cmd == "ping":
            return protocol.make_reply(rid, "ping",
                                       activated=self.activated, dones=self.dones)
        if cmd == "acquire":
            return self._acquire(rid)
        if cmd == "show":
            return self._show(rid, obj)
        if cmd == "verify":
            return self._verify(rid)
        if cmd == "leave":
            return self._leave(rid)
        return protocol.make_error(rid, f"unknown request {cmd!r}")

    def _acquire(self, rid) -> dict:
        # PLACEHOLDER handle/revision (T2 replaces with verified binding semantics).
        if not self.activated:
            return protocol.make_reply(rid, "acquire", ok=False, handle="",
                                       revision=0, reason="not activated")
        return protocol.make_reply(rid, "acquire", ok=True, handle=str(self.im),
                                   revision=self.dones)

    def _show(self, rid, obj: dict) -> dict:
        if not self.activated:
            return protocol.make_reply(rid, "show", result="refused", t_ms=0.0)
        t0 = time.monotonic()
        dones_before = self.dones
        try:
            before = int(obj.get("before", 0) or 0)
            if before:  # replace: ONE atomic commit — delete + commit_string + commit
                self.c.request(self.im, IFACE, "delete_surrounding_text", before, 0)
            self.c.request(self.im, IFACE, "commit_string", obj["text"])
            self.c.request(self.im, IFACE, "commit", self.dones)
        except Exception:  # wire send failed → outcome unverifiable; NEVER retry (R.5)
            return protocol.make_reply(rid, "show", result="unknown",
                                       t_ms=round((time.monotonic() - t0) * 1000, 3))
        deadline = time.monotonic() + SHOW_CONFIRM_WAIT
        while True:
            self._drain_events()
            if self.dones > dones_before:
                return protocol.make_reply(rid, "show", result="applied",
                                           t_ms=round((time.monotonic() - t0) * 1000, 3))
            if self.stopped or time.monotonic() >= deadline:
                return protocol.make_reply(rid, "show", result="unknown",
                                           t_ms=round((time.monotonic() - t0) * 1000, 3))
            time.sleep(0.01)

    def _verify(self, rid) -> dict:
        s = self.surround or {}
        head = s.get("text") or ""
        return protocol.make_reply(rid, "verify", text_head=head[:80],
                                   cursor=s.get("cursor", 0), anchor=s.get("anchor", 0),
                                   bytes=len(head.encode()))

    def _leave(self, rid) -> dict:
        if self.grab:
            try:
                self.c.request(self.grab, GRAB_IFACE, "release")
            except Exception:  # keep serving regardless (probe posture)
                pass
            self.grab = 0
        return protocol.make_reply(rid, "leave", ok=True)

    # ---- event pump --------------------------------------------------------
    def _drain_events(self) -> None:
        """Forward pending wire events; never raises (probe's survive-odd-events posture)."""
        while not self.stopped:
            try:
                ev = self.c.next_event(0)
            except Exception as e:  # noqa: BLE001 — log-only; keep the loop alive
                self._log(protocol.make_event("probe_error", e=repr(e)[:200]))
                return
            if ev is None:
                return
            self.on_event(ev)

    # ---- serve loop ----------------------------------------------------------
    def serve(self, stdin=None) -> None:
        """become_im(), then serve JSONL lines until pipe close or `unavailable`."""
        try:
            self.become_im()
            for line in (stdin if stdin is not None else sys.stdin):
                self.handle_line(line)
                if self.stopped:
                    break
        finally:
            self._log(protocol.make_event("exit", activated=self.activated,
                                          dones=self.dones, grab_keys=self.grab_keys))


def _default_log_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        try:
            d = Path(base) / "voice-typing"
            d.mkdir(parents=True, exist_ok=True)
            return str(d / "ime-events.jsonl")
        except OSError:
            pass
    return "/dev/null"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv if argv is None else argv
    log_path = args[1] if len(args) > 1 else _default_log_path()
    host = ImeHost(Client(), sys.stdout, log_path)
    host.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
