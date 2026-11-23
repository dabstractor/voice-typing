"""JSONL framing + vocabulary + log-cap tests for voice_typing.ime.protocol."""
from __future__ import annotations

from voice_typing.bulk_delivery import ShowResult
from voice_typing.ime import protocol


def test_show_results_cross_pinned_to_bulk_delivery():
    """SHOW_RESULTS words == ShowResult values, verbatim (the cross-module pin)."""
    assert set(protocol.SHOW_RESULTS) == {r.value for r in ShowResult}
    assert all(isinstance(w, str) for w in protocol.SHOW_RESULTS)


def test_encode_decode_roundtrip_unicode_and_newline():
    obj = {"id": 3, "cmd": "show", "text": "héllo\nworld — 日本語"}
    line = protocol.encode(obj)
    assert line.endswith(b"\n") and line.count(b"\n") == 1  # dumps escapes the embedded newline
    assert protocol.decode(line) == obj
    assert len(line.decode("utf-8").splitlines()) == 1      # one line out, always


def test_decode_accepts_str_and_bytes():
    assert protocol.decode('{"id":1,"cmd":"ping"}') == {"id": 1, "cmd": "ping"}
    assert protocol.decode(b'{"id":1,"cmd":"ping"}') == {"id": 1, "cmd": "ping"}


def test_decode_garbage_raises_protocol_error():
    import json
    import pytest
    with pytest.raises(protocol.ProtocolError):
        protocol.decode("not json {")
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b"\xff\xfe garbage")  # undecodable utf-8
    with pytest.raises(protocol.ProtocolError):
        protocol.decode("[1, 2]")             # JSON, but not an object
    assert issubclass(protocol.ProtocolError, ValueError)


def test_validate_request_legal_cmds():
    for cmd in protocol.REQUEST_CMDS:
        obj = {"id": 1, "cmd": cmd}
        if cmd == "show":
            obj.update({f: 1 for f in protocol.SHOW_FIELDS})
        got, err = protocol.validate_request(obj)
        assert err is None and got == cmd


def test_validate_request_missing_id():
    cmd, err = protocol.validate_request({"cmd": "ping"})
    assert cmd is None and err


def test_validate_request_unknown_cmd():
    cmd, err = protocol.validate_request({"id": 1, "cmd": "bogus"})
    assert cmd is None and "bogus" in err


def test_validate_request_cancel_reserved():
    cmd, err = protocol.validate_request({"id": 1, "cmd": "cancel"})
    assert cmd is None and err == "cancel reserved (P1.M4.T3.S3)"


def test_validate_request_show_missing_field_names_it():
    obj = {"id": 1, "cmd": "show", "session": 9, "utterance": "u", "seq": 1,
           "expected_revision": 0}  # text missing
    cmd, err = protocol.validate_request(obj)
    assert cmd is None and "text" in err


def test_validate_request_extra_fields_tolerated():
    cmd, err = protocol.validate_request({"id": 2, "cmd": "ping", "extra": True})
    assert err is None and cmd == "ping"


def test_reply_echoes_id_and_cmd():
    assert protocol.make_reply(7, "ping", activated=True) == {
        "id": 7, "reply": "ping", "activated": True}


def test_error_shape():
    assert protocol.make_error(7, "boom") == {"id": 7, "error": "boom"}


def test_event_lines_id_less():
    ev = protocol.make_event("done", dones=2)
    assert "id" not in ev
    assert ev["ev"] == "done"
    assert isinstance(ev["t_ms"], float) and ev["t_ms"] >= 0
    assert ev["dones"] == 2


def test_event_log_writer_appends_until_cap(tmp_path):
    p = tmp_path / "events.jsonl"
    w = protocol.EventLogWriter(p)
    ev = {"ev": "x", "pad": "y" * 380}  # ~400+ bytes a line
    for _ in range(200):                # ~80 KB total > 64 KiB cap
        w.append(ev)
    size = p.stat().st_size
    assert size > 0
    assert size <= protocol.LOG_CAP_BYTES + len(protocol.encode(ev))  # cap + at most one line
    assert protocol.LOG_CAP_BYTES == 64 * 1024
    lines = p.read_text(encoding="utf-8").splitlines()
    assert all(line.startswith("{") for line in lines)


def test_event_log_writer_none_disables():
    w = protocol.EventLogWriter(None)
    w.append({"ev": "noop"})  # must not raise, write nothing anywhere
    assert w.bytes == 0
