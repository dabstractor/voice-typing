"""Fake-client serve-loop dispatch tests for voice_typing.ime.ime_host.

No compositor, no daemon, no subprocess: ImeHost gets an injected _FakeWire
and StringIO in/out. Pins the JSONL contract: one reply per request with id
echo, errors survive, wrong-state show degrades (never crashes, never
retries), events forwarded id-less to stdout + capped log, unavailable stops.
"""
from __future__ import annotations

import io

import pytest

from voice_typing.ime import protocol
from voice_typing.ime.ime_host import ImeHost, SHOW_CONFIRM_WAIT
from voice_typing.ime.wlwire import Event


class _FakeWire:
    """Probe-relevant client double: scripted next_event results, request recorder."""

    def __init__(self, script=()):
        self.s = None
        self.ifaces = {1: "wl_display"}
        self.globals = {}
        self.registry = 0
        self.requests = []
        self.script = list(script)
        self._obj = 10

    def request(self, obj, iface, name, *args):
        self.requests.append((obj, iface, name, args))

    def next_event(self, timeout=0):
        return self.script.pop(0) if self.script else None

    def roundtrip(self, timeout=5):
        pass

    def new(self, iface):
        self._obj += 1
        self.ifaces[self._obj] = iface
        return self._obj

    def bind(self, global_name, iface, version=1):
        obj = self.new(iface)
        self.requests.append((self.registry, "wl_registry", "bind",
                              (global_name, iface, version, obj)))
        return obj


def _make_host(script=()):
    out = io.StringIO()
    wire = _FakeWire(script)
    host = ImeHost(wire, out, None)  # log_path None → logging disabled
    return host, wire, out


def _feed(host, out, *objs):
    start = out.tell()
    for o in objs:
        host.handle_line(protocol.encode(o).decode())
    out.seek(start)
    return [protocol.decode(l) for l in out.read().splitlines()]


SHOW_OBJ = {"id": 8, "cmd": "show", "session": 9, "utterance": "u1", "seq": 1,
            "expected_revision": 0, "text": "hi"}


def test_ping_replies_state():
    host, _wire, out = _make_host()
    lines = _feed(host, out, {"id": 1, "cmd": "ping"})
    assert lines == [{"id": 1, "reply": "ping", "activated": False, "dones": 0}]


def test_unknown_request_error_and_survive():
    host, _wire, out = _make_host()
    lines = _feed(host, out, {"id": 2, "cmd": "bogus"}, {"id": 3, "cmd": "ping"})
    assert lines[0]["id"] == 2 and "error" in lines[0]
    assert lines[1]["reply"] == "ping"  # the loop survived


def test_bad_json_survives():
    host, _wire, out = _make_host()
    start = out.tell()
    host.handle_line("this is not json\n")
    host.handle_line(protocol.encode({"id": 4, "cmd": "ping"}).decode())
    out.seek(start)
    lines = [protocol.decode(l) for l in out.read().splitlines()]
    assert "error" in lines[0] and lines[0]["id"] == -1
    assert lines[1]["reply"] == "ping"


def test_blank_line_is_silently_skipped():
    host, _wire, out = _make_host()
    host.handle_line("\n")
    assert out.getvalue() == ""


# --- live cancel dispatch (P1.M4.T3.S3 lifts the reservation) -----------------

CANCEL_OBJ = {"id": 5, "cmd": "cancel", "before": 7}


def test_cancel_missing_before_is_error_and_host_keeps_serving():
    host, _wire, out = _make_host()
    lines = _feed(host, out, {"id": 5, "cmd": "cancel"},
                  {"id": 6, "cmd": "ping"})  # a bad row must not stop the loop
    assert lines[0]["id"] == 5 and "before" in lines[0]["error"]
    assert lines[1] == {"id": 6, "reply": "ping", "activated": False, "dones": 0}


def test_cancel_not_activated_refused_without_wire_sends():
    host, wire, out = _make_host()
    lines = _feed(host, out, CANCEL_OBJ)
    assert lines[0]["result"] == "refused" and lines[0]["reply"] == "cancel"
    assert wire.requests == []  # nothing went out on the wire


def test_cancel_applied_on_scripted_done_sends_delete_empty_commit():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    host.dones = 4
    wire.script = [Event(11, "zwp_input_method_v2", "done", ())]
    lines = _feed(host, out, CANCEL_OBJ)
    replies = [d for d in lines if "reply" in d]
    assert replies[0]["result"] == "applied" and isinstance(replies[0]["t_ms"], float)
    sent = [(i, n, a) for _o, i, n, a in wire.requests]
    assert sent == [("zwp_input_method_v2", "delete_surrounding_text", (7, 0)),
                    ("zwp_input_method_v2", "commit_string", ("",)),
                    ("zwp_input_method_v2", "commit", (4,))]  # ONE commit per op


def test_cancel_wire_exception_maps_unknown():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11

    def _boom(*_a, **_k):
        raise RuntimeError("wire down")

    wire.request = _boom
    lines = _feed(host, out, CANCEL_OBJ)
    assert [d["result"] for d in lines if "reply" in d] == ["unknown"]  # never retry (R.5)
    assert [d for d in lines if "error" in d] == []      # a reply, not a crash


def test_cancel_unknown_on_timeout(monkeypatch):
    import voice_typing.ime.ime_host as ime_host_mod
    monkeypatch.setattr(ime_host_mod, "SHOW_CONFIRM_WAIT", 0.05)  # bounded wait, kept short
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    lines = _feed(host, out, CANCEL_OBJ)  # no scripted done
    assert [d["result"] for d in lines if "reply" in d] == ["unknown"]


def test_show_missing_field_is_error_not_crash():
    host, _wire, out = _make_host()
    lines = _feed(host, out, {"id": 6, "cmd": "show", "session": 1, "utterance": "u",
                              "seq": 1, "expected_revision": 0})
    assert lines[0]["id"] == 6 and "text" in lines[0]["error"]


def test_acquire_not_activated():
    host, _wire, out = _make_host()
    lines = _feed(host, out, {"id": 7, "cmd": "acquire"})
    assert lines[0] == {"id": 7, "reply": "acquire", "ok": False, "handle": "",
                        "revision": 0, "reason": "not activated"}


def test_show_not_activated_is_refused_without_wire_sends():
    host, wire, out = _make_host()
    lines = _feed(host, out, SHOW_OBJ)
    assert lines[0]["result"] == "refused"
    assert wire.requests == []  # nothing went out on the wire


def test_show_applied_on_scripted_done():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    wire.script = [Event(11, "zwp_input_method_v2", "done", ())]
    lines = _feed(host, out, dict(SHOW_OBJ, id=9))
    replies = [d for d in lines if "reply" in d]
    events = [d for d in lines if "ev" in d]
    assert replies[0]["result"] == "applied" and isinstance(replies[0]["t_ms"], float)
    assert events and events[-1]["ev"] == "done" and events[-1]["dones"] == 1
    sent = [(i, n, a) for _o, i, n, a in wire.requests]
    assert sent == [("zwp_input_method_v2", "commit_string", ("hi",)),
                    ("zwp_input_method_v2", "commit", (0,))]


def test_show_replace_sends_delete_first():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    host.dones = 4
    wire.script = [Event(11, "zwp_input_method_v2", "done", ())]
    lines = _feed(host, out, dict(SHOW_OBJ, id=10, before=6, text="ok"))
    replies = [d for d in lines if "reply" in d]
    assert replies[0]["result"] == "applied"
    sent = [(i, n, a) for _o, i, n, a in wire.requests]
    assert sent == [("zwp_input_method_v2", "delete_surrounding_text", (6, 0)),
                    ("zwp_input_method_v2", "commit_string", ("ok",)),
                    ("zwp_input_method_v2", "commit", (4,))]  # ONE commit per op


def test_show_unknown_on_timeout(monkeypatch):
    import voice_typing.ime.ime_host as ime_host_mod
    monkeypatch.setattr(ime_host_mod, "SHOW_CONFIRM_WAIT", 0.05)  # bounded wait, kept short in test
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    lines = _feed(host, out, SHOW_OBJ)  # no scripted done
    assert lines[0]["result"] == "unknown"
    assert [d["result"] for d in lines if "reply" in d] == ["unknown"]


def test_verify_last_surround_snapshot():
    host, wire, out = _make_host()
    wire.script = [Event(11, "zwp_input_method_v2", "surrounding_text", ("héllo", 4, 0))]
    host._drain_events()
    start = out.tell()
    host.handle_line(protocol.encode({"id": 10, "cmd": "verify"}).decode())
    out.seek(start)
    lines = [protocol.decode(l) for l in out.read().splitlines()]
    assert lines[0]["reply"] == "verify"
    assert lines[0]["text_head"] == "héllo"
    assert lines[0]["cursor"] == 4 and lines[0]["anchor"] == 0
    assert lines[0]["bytes"] == len("héllo".encode())


def test_leave_releases_grab_and_keeps_serving():
    host, wire, out = _make_host()
    host.grab = 12
    lines = _feed(host, out, {"id": 11, "cmd": "leave"}, {"id": 12, "cmd": "ping"})
    assert lines[0] == {"id": 11, "reply": "leave", "ok": True}
    assert wire.requests[-1] == (12, "zwp_input_method_keyboard_grab_v2", "release", ())
    assert host.grab == 0
    assert lines[1]["reply"] == "ping"  # still serving (S2 owns process exit)


def test_events_forwarded_to_stdout_and_log(tmp_path):
    log = tmp_path / "events.jsonl"
    out = io.StringIO()
    wire = _FakeWire()
    wire.script = [
        Event(11, "zwp_input_method_v2", "surrounding_text", ("some text", 9, 9)),
        Event(11, "zwp_input_method_v2", "activate", ()),
    ]
    host = ImeHost(wire, out, log)
    host.handle_line(protocol.encode({"id": 1, "cmd": "ping"}).decode())
    parsed = [protocol.decode(l) for l in out.getvalue().splitlines()]
    evs = [d for d in parsed if "ev" in d]
    assert [e["ev"] for e in evs] == ["surrounding_text", "activate"]
    assert all("id" not in e for e in evs)                      # event lines are id-less
    assert evs[0]["head"] == "some text"                        # head-truncation kept
    assert evs[0]["bytes"] == len("some text".encode())
    logged = [protocol.decode(l) for l in log.read_text().splitlines()]
    assert [e["ev"] for e in logged] == ["surrounding_text", "activate"]


def test_grab_key_event_forwarded(tmp_path):
    out = io.StringIO()
    wire = _FakeWire(script=[Event(12, "zwp_input_method_keyboard_grab_v2", "key", (1, 2, 30, 1))])
    host = ImeHost(wire, out, tmp_path / "events.jsonl")
    host.handle_line(protocol.encode({"id": 1, "cmd": "ping"}).decode())
    evs = [d for d in (protocol.decode(l) for l in out.getvalue().splitlines()) if "ev" in d]
    assert evs[0]["ev"] == "grab_key" and evs[0]["key"] == 30 and evs[0]["state"] == 1
    assert host.grab_keys == 1


def test_unavailable_stops_cleanly(tmp_path):
    log = tmp_path / "events.jsonl"
    out = io.StringIO()
    wire = _FakeWire(script=[Event(11, "zwp_input_method_v2", "unavailable", ())])
    host = ImeHost(wire, out, log)
    host.handle_line(protocol.encode({"id": 1, "cmd": "ping"}).decode())
    assert host.stopped
    evs = [d for d in (protocol.decode(l) for l in out.getvalue().splitlines()) if "ev" in d]
    assert evs[0]["ev"] == "unavailable"
    logged = [protocol.decode(l) for l in log.read_text().splitlines()]
    assert any(e["ev"] == "unavailable" for e in logged)
    host.handle_line(protocol.encode({"id": 2, "cmd": "ping"}).decode())  # still answers


def test_serve_become_im_sequence_then_stdin_loop():
    out = io.StringIO()
    wire = _FakeWire()
    wire.globals = {2: ("zwp_input_method_manager_v2", 1), 3: ("wl_seat", 1)}
    host = ImeHost(wire, out, None)
    stdin = io.StringIO(protocol.encode({"id": 1, "cmd": "ping"}).decode()
                        + protocol.encode({"id": 2, "cmd": "leave"}).decode())
    host.serve(stdin=stdin)
    parsed = [protocol.decode(l) for l in out.getvalue().splitlines()]
    replies = [d for d in parsed if "reply" in d]
    assert [r["id"] for r in replies] == [1, 2]
    names = [(i, n) for _o, i, n, _a in wire.requests]
    assert names[0] == ("wl_display", "get_registry")                # become-IM sequence:
    assert names[1][0] == "wl_registry" and names[1][1] == "bind"    #   bind manager + seat
    assert ("zwp_input_method_manager_v2", "get_input_method") in names
    assert host.im in wire.ifaces and wire.ifaces[host.im] == "zwp_input_method_v2"


def test_serve_stops_after_unavailable(tmp_path):
    out = io.StringIO()
    wire = _FakeWire(script=[Event(11, "zwp_input_method_v2", "unavailable", ())])
    wire.globals = {2: ("zwp_input_method_manager_v2", 1), 3: ("wl_seat", 1)}
    host = ImeHost(wire, out, tmp_path / "events.jsonl")
    stdin = io.StringIO(protocol.encode({"id": 1, "cmd": "ping"}).decode()
                        + protocol.encode({"id": 2, "cmd": "ping"}).decode())
    host.serve(stdin=stdin)  # clean return, not an exception / SystemExit
    assert host.stopped
    logged = [protocol.decode(l) for l in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert logged[-1]["ev"] == "exit"


# ---- P1.M4.T2.S1: snapshot-carrying acquire + full-snapshot verify (appended) ----


def _surround(text, cursor, anchor):
    return Event(11, "zwp_input_method_v2", "surrounding_text", (text, cursor, anchor))


def test_acquire_activated_with_cached_snapshot():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    host.dones = 3
    wire.script = [_surround("héllo ", 7, 7)]
    host._drain_events()  # the text-input side pushed the snapshot before acquire
    lines = _feed(host, out, {"id": 20, "cmd": "acquire"})
    r = lines[0]
    assert r == {"id": 20, "reply": "acquire", "ok": True, "handle": "11", "revision": 3,
                 "text": "héllo ", "cursor": 7, "anchor": 7, "snapshot_truncated": False}


def test_acquire_activated_no_snapshot_refused(monkeypatch):
    import voice_typing.ime.ime_host as ime_host_mod
    monkeypatch.setattr(ime_host_mod, "_SURROUND_WAIT_S", 0.05)  # bounded wait, kept short in test
    host, _wire, out = _make_host()  # no snapshot is ever pushed (foot/kitty class)
    host.activated = True
    lines = _feed(host, out, {"id": 21, "cmd": "acquire"})
    assert lines[0] == {"id": 21, "reply": "acquire", "ok": False, "handle": "",
                        "revision": 0, "reason": "no surrounding text"}


def test_acquire_snapshot_arrives_late_within_wait(monkeypatch):
    import voice_typing.ime.ime_host as ime_host_mod
    monkeypatch.setattr(ime_host_mod, "_SURROUND_WAIT_S", 0.5)
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    host.dones = 1
    wire.script = [_surround("late", 4, 4)]  # delivered by acquire's own drain pump
    lines = _feed(host, out, {"id": 22, "cmd": "acquire"})
    r = next(d for d in lines if "reply" in d)
    assert r["ok"] is True and r["text"] == "late" and r["cursor"] == 4
    assert any(d.get("ev") == "surrounding_text" for d in lines)  # event still forwarded id-less


def test_acquire_truncates_by_chars_not_bytes():
    # The head cap is a STR slice (chars whole); the flag reports an actual cut.
    host, wire, out = _make_host()
    host.activated = True
    host.im = 11
    text = "x" * 70000                       # 70000 chars > the 65536-char cap → really cut
    wire.script = [_surround(text, 70000, 70000)]
    host._drain_events()
    lines = _feed(host, out, {"id": 23, "cmd": "acquire"})
    r = lines[0]
    assert r["ok"] is True and r["snapshot_truncated"] is True
    assert r["text"] == "x" * 65536


def test_acquire_multibyte_text_over_byte_budget_but_uncut():
    # 40000 é chars = 80000 BYTES but only 40000 CHARS: the char slice sends the
    # full text untouched — nothing was cut, so truncated stays False.
    host, wire, out = _make_host()
    host.activated = True
    text = "é" * 40000
    wire.script = [_surround(text, 80000, 80000)]
    host._drain_events()
    lines = _feed(host, out, {"id": 26, "cmd": "acquire"})
    r = lines[0]
    assert r["ok"] is True and r["snapshot_truncated"] is False
    assert r["text"] == text and len(r["text"].encode()) == 80000


def test_verify_replies_full_snapshot_with_state():
    host, wire, out = _make_host()
    wire.script = [_surround("x" * 200, 200, 200)]
    host._drain_events()
    lines = _feed(host, out, {"id": 24, "cmd": "verify"})
    r = lines[0]
    assert r["reply"] == "verify" and r["ok"] is True
    assert r["text"] == "x" * 200            # FULL bounded text, NOT the :80 head
    assert r["cursor"] == 200 and r["anchor"] == 200 and r["snapshot_truncated"] is False
    assert r["activated"] is False and r["dones"] == 0  # state echoed with the snapshot
    assert r["text_head"] == "x" * 80       # legacy S1 fields kept for the pinned shape
    assert r["bytes"] == 200


def test_verify_no_snapshot_refused_with_state():
    host, _wire, out = _make_host()
    lines = _feed(host, out, {"id": 25, "cmd": "verify"})
    assert lines[0] == {"id": 25, "reply": "verify", "activated": False, "dones": 0,
                        "ok": False, "reason": "no surrounding text"}


# --- grab engagement (P1.M4.T4.S1) ----------------------------------------------

def test_grab_sends_grab_keyboard_and_replies_ok():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 5
    lines = _feed(host, out, {"id": 21, "cmd": "grab"}, {"id": 22, "cmd": "ping"})
    assert lines[0] == {"id": 21, "reply": "grab", "ok": True}
    assert host.grab == 11  # c.new() assigned the grab object id
    assert wire.requests == [(5, "zwp_input_method_v2", "grab_keyboard", (11,))]
    assert lines[1]["reply"] == "ping"  # host keeps serving


def test_grab_while_unactivated_refused_without_wire_sends():
    host, wire, out = _make_host()
    lines = _feed(host, out, {"id": 23, "cmd": "grab"})
    assert lines[0]["id"] == 23 and lines[0]["ok"] is False
    assert lines[0]["reason"] == "not activated"
    assert wire.requests == []


def test_grabbed_keys_forwarded_then_leave_releases_grab():
    host, wire, out = _make_host()
    host.activated = True
    host.im = 5
    _feed(host, out, {"id": 24, "cmd": "grab"})
    grab = host.grab
    assert grab != 0
    wire.script = [Event(12, "zwp_input_method_keyboard_grab_v2", "key", (1, 2, 30, 1))]
    lines = _feed(host, out, {"id": 25, "cmd": "ping"})   # the drain forwards grabbed keys
    evs = [d for d in lines if "ev" in d]
    assert len(evs) == 1 and evs[0]["ev"] == "grab_key"
    assert evs[0]["key"] == 30 and evs[0]["state"] == 1
    lines = _feed(host, out, {"id": 26, "cmd": "leave"})
    assert lines[0] == {"id": 26, "reply": "leave", "ok": True}
    assert wire.requests[-1] == (grab, "zwp_input_method_keyboard_grab_v2", "release", ())
    assert host.grab == 0
