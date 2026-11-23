"""ime_host: seat input-method host serving the JSONL protocol on stdin/stdout.

Evolved from tools/im-lab/im_probe.py (that lab copy stays byte-identical as
R.2 evidence; its ctl.sock was lab instrumentation — this host serves the
P1.M4.T1.S2 subprocess pipes instead, and never runs in the foreground of a
test: unit tests inject fakes via ImeHost(client, out, log_path)).

Usage (from the S2 subprocess host):
    python -m voice_typing.ime.ime_host [event-log-path]

Becomes the seat's input method (get_registry → roundtrip → bind manager+seat
→ get_input_method → two roundtrips, proven in the lab), then serves JSONL:
requests acquire/show/verify/leave/ping/cancel, replies echoing
the caller id, async id-less {"ev":...} event lines interleaved on stdout,
and a 64 KiB-capped event log at argv[1] (default under $XDG_RUNTIME_DIR).
`unavailable` → event line + log + clean exit(0) (one-IM-per-seat; S2 marks
the route unavailable).

TRANSPORT ONLY: acquire's handle/revision is a placeholder passthrough; show
does no ownership/units verification and no chunking strategy (T2/T3); no
takeover POLICY — that lives daemon-side (voice_typing.ime.takeover, T4): the
host only engages/releases the keyboard grab (`grab` request / `leave`) and
forwards the event lines the daemon's detector consumes. no subprocess
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
SHOW_CONFIRM_WAIT = 0.22  # s — ONE bounded wait for the compositor `done`; no retry, ever.
                          # ≤0.22 so the receiver's verdict precedes the daemon's 0.25 s
                          # give-up on the show request (P1.M4.T3.S1 deadline budget)
_SNAPSHOT_HEAD_BYTES = 64 * 1024   # generous vs the ~4 KiB practical cap; refuse rather than mis-slice
_SURROUND_WAIT_S = 1.0             # bounded poll for a first surrounding_text after activation


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
        if cmd == "cancel":
            return self._cancel(rid, obj)
        if cmd == "grab":
            return self._grab(rid)
        if cmd == "verify":
            return self._verify(rid)
        if cmd == "leave":
            return self._leave(rid)
        return protocol.make_error(rid, f"unknown request {cmd!r}")

    def _acquire(self, rid) -> dict:
        # T2: snapshot-carrying acquire (transport-level; the daemon's ImeTarget
        # owns interpretation — selection/consistency/refusal taxonomy).
        if not self.activated:
            return protocol.make_reply(rid, "acquire", ok=False, handle="",
                                       revision=0, reason="not activated")
        # Bounded wait for a cached surrounding_text snapshot (the text-input side
        # PUSHES it; the IM cannot request it). Pump _drain_events so it can arrive.
        deadline = time.monotonic() + _SURROUND_WAIT_S
        while self.surround is None and time.monotonic() < deadline:
            self._drain_events()
            if self.surround is not None:
                break
            time.sleep(0.02)
        if self.surround is None:
            return protocol.make_reply(rid, "acquire", ok=False, handle="", revision=0,
                                       reason="no surrounding text")
        text, cursor, anchor = self.surround["text"], self.surround["cursor"], self.surround["anchor"]
        return protocol.make_reply(rid, "acquire", ok=True, handle=str(self.im),
                                   revision=self.dones,
                                   text=text[:_SNAPSHOT_HEAD_BYTES],  # str slice keeps chars whole
                                   cursor=cursor, anchor=anchor,
                                   snapshot_truncated=len(text) > _SNAPSHOT_HEAD_BYTES)

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

    def _cancel(self, rid, obj: dict) -> dict:
        """(P1.M4.T3.S3) ONE atomic removal: delete_surrounding_text(before, 0) +
        commit_string("") + commit — mirrors _show's posture (not-activated ⇒ refused;
        wire send failure ⇒ unknown, never retried) minus the text payload. The empty
        commit_string keeps the delete+commit_string+commit triple the lab proved; the
        optional GTK lab row (tests/ime_finalize_lab.py) verifies it end-to-end."""
        if not self.activated:
            return protocol.make_reply(rid, "cancel", result="refused", t_ms=0.0)
        t0 = time.monotonic()
        dones_before = self.dones
        try:
            before = int(obj.get("before", 0) or 0)
            self.c.request(self.im, IFACE, "delete_surrounding_text", before, 0)
            self.c.request(self.im, IFACE, "commit_string", "")   # empty-text triple variant
            self.c.request(self.im, IFACE, "commit", self.dones)
        except Exception:  # wire send failed → outcome unverifiable; NEVER retry (R.5)
            return protocol.make_reply(rid, "cancel", result="unknown",
                                       t_ms=round((time.monotonic() - t0) * 1000, 3))
        deadline = time.monotonic() + SHOW_CONFIRM_WAIT  # same bounded confirm loop as _show
        while True:
            self._drain_events()
            if self.dones > dones_before:
                return protocol.make_reply(rid, "cancel", result="applied",
                                           t_ms=round((time.monotonic() - t0) * 1000, 3))
            if self.stopped or time.monotonic() >= deadline:
                return protocol.make_reply(rid, "cancel", result="unknown",
                                           t_ms=round((time.monotonic() - t0) * 1000, 3))
            time.sleep(0.01)

    def _grab(self, rid) -> dict:
        """(P1.M4.T4.S1) Engage the keyboard grab: a new
        zwp_input_method_keyboard_grab_v2 object + grab_keyboard — the exact
        im_probe-proven sequence (tools/im-lab/im_probe.py:112-114). While the
        grab is live, physical keys arrive here as grab_key events and are NOT
        forwarded to the app (im-lab row O) — the takeover detector's only key
        source, which is also why revocation MUST release it AT THE TARGET
        (`_leave` below releases when held). Additive arm; release stays in
        _leave — this handler never releases."""
        if not self.activated:
            return protocol.make_reply(rid, "grab", ok=False, reason="not activated")
        try:
            grab = self.c.new(GRAB_IFACE)
            self.c.request(self.im, IFACE, "grab_keyboard", grab)
        except Exception:  # wire send failed → nothing engaged; the caller may retry
            return protocol.make_reply(rid, "grab", ok=False, reason="grab failed")
        self.grab = grab
        return protocol.make_reply(rid, "grab", ok=True)

    def _verify(self, rid) -> dict:
        # T2: the same bounded snapshot shape acquire replies (+ activated/dones).
        # text_head/bytes are the legacy S1 reply fields (the pinned S1 test
        # asserts them); the FULL bounded snapshot rides in text/cursor/anchor.
        s = self.surround
        if s is None:
            return protocol.make_reply(rid, "verify", activated=self.activated, dones=self.dones,
                                       ok=False, reason="no surrounding text")
        text, cursor, anchor = s["text"], s["cursor"], s["anchor"]
        head = text[:_SNAPSHOT_HEAD_BYTES]
        return protocol.make_reply(rid, "verify", activated=self.activated, dones=self.dones,
                                   ok=True, text=head, cursor=cursor, anchor=anchor,
                                   snapshot_truncated=len(text) > _SNAPSHOT_HEAD_BYTES,
                                   text_head=head[:80], bytes=len(text.encode()))

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
