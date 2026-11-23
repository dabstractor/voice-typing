"""Opcode-table/XML pins + wire byte-layout units for voice_typing.ime.wlwire.

The vendored XML is authoritative: a table/XML mismatch here is exactly the
silent-blast-radius drift (a re-ordered entry sends a different request than
intended, e.g. delete_surrounding_text vs commit) this test exists to catch.
The core wl_* tables come from wayland.xml, NOT this fixture — those are
pinned by literal opcode expectations (commit_string=0, delete_surrounding_
text=2, commit=3).
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from voice_typing.ime import wlwire

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "input-method-unstable-v2.xml"
KIND = {"uint": "u", "int": "i", "string": "s", "object": "o", "new_id": "n", "fd": "h"}
IFACES = (
    "zwp_input_method_manager_v2",
    "zwp_input_method_v2",
    "zwp_input_method_keyboard_grab_v2",
)


def xml_entries(root, iface: str, tag: str) -> list[tuple[str, str]]:
    """(name, arg-kinds) per <request>/<event> element in DOCUMENT order."""
    el = next(e for e in root.findall("interface") if e.get("name") == iface)
    return [(e.get("name"), "".join(KIND[a.get("type")] for a in e.findall("arg")))
            for e in el.findall(tag)]


def xml_arg_names(root, iface: str, tag: str) -> dict[str, list[str]]:
    el = next(e for e in root.findall("interface") if e.get("name") == iface)
    return {e.get("name"): [a.get("name") for a in e.findall("arg")] for e in el.findall(tag)}


def test_opcode_tables_match_vendored_xml():
    root = ET.parse(FIXTURE).getroot()
    for iface in IFACES:
        assert [(n, k) for n, k in wlwire.REQUESTS[iface]] == xml_entries(root, iface, "request")
        # manager has NO events in the XML; an absent table == empty list
        assert [(n, k) for n, k in wlwire.EVENTS.get(iface, [])] == xml_entries(root, iface, "event")


def test_arg_names_wire_order():
    """Semantic pin: arg order on the ops the host drives (XML <arg> children = wire order)."""
    root = ET.parse(FIXTURE).getroot()
    reqs = xml_arg_names(root, "zwp_input_method_v2", "request")
    assert reqs["commit_string"] == ["text"]
    assert reqs["delete_surrounding_text"] == ["before_length", "after_length"]
    assert reqs["commit"] == ["serial"]
    evs = xml_arg_names(root, "zwp_input_method_v2", "event")
    assert evs["surrounding_text"] == ["text", "cursor", "anchor"]
    grab_evs = xml_arg_names(root, "zwp_input_method_keyboard_grab_v2", "event")
    assert grab_evs["key"] == ["serial", "time", "key", "state"]


def test_wstr_layout():
    b = wlwire.wstr("hi")
    (n,) = struct.unpack_from("<I", b, 0)
    assert n == 3              # length prefix counts the NUL
    assert b[4:7] == b"hi\0"   # utf-8 payload + NUL terminator
    assert len(b) % 4 == 0     # total padded to a 4-byte boundary
    assert b[7:] == b"\0"      # exactly one pad byte here


def test_u32_i32_bytes():
    assert wlwire.u32(1) == b"\x01\x00\x00\x00"            # little-endian
    assert wlwire.u32(0xFFFFFFFF) == b"\xff\xff\xff\xff"
    assert wlwire.i32(-1) == b"\xff\xff\xff\xff"           # negative wraps as two's complement
    assert wlwire.i32(-2) == struct.pack("<i", -2)


class _RecordingSock:
    """Minimal fake: records sendall payloads; no real socket anywhere."""

    def __init__(self):
        self.sent = bytearray()

    def sendall(self, data):
        self.sent += data


def _bare_client() -> wlwire.Client:
    c = wlwire.Client.__new__(wlwire.Client)  # bypass __init__: no compositor, no display
    c.s = _RecordingSock()
    return c


def test_injected_sock_skips_display():
    fake = _RecordingSock()
    c = wlwire.Client(sock=fake)
    assert c.s is fake
    assert c.next_id == 1 and c.ifaces[1] == "wl_display"


def test_request_message_bytes():
    c = _bare_client()
    c.request(42, "zwp_input_method_v2", "commit_string", "ab")
    payload = wlwire.wstr("ab")
    # opcode 0 = first table entry; header <IHH> = (object id, opcode, size)
    assert bytes(c.s.sent) == struct.pack("<IHH", 42, 0, 8 + len(payload)) + payload


def test_opcode_pins_order_of_tables():
    c = _bare_client()
    c.request(7, "zwp_input_method_v2", "delete_surrounding_text", 3, 0)
    payload = wlwire.u32(3) + wlwire.u32(0)
    assert bytes(c.s.sent) == struct.pack("<IHH", 7, 2, 8 + len(payload)) + payload  # opcode 2
    c.s.sent.clear()
    c.request(7, "zwp_input_method_v2", "commit", 5)
    assert bytes(c.s.sent) == struct.pack("<IHH", 7, 3, 12) + wlwire.u32(5)          # opcode 3


def test_unknown_request_raises():
    c = _bare_client()
    with pytest.raises(wlwire.WlError):
        c.request(1, "zwp_input_method_v2", "bogus")
    with pytest.raises(wlwire.WlError):
        c.request(1, "no_such_iface", "commit")
    with pytest.raises(wlwire.WlError):  # wrong arity
        c.request(1, "zwp_input_method_v2", "commit")


def test_id_space_guard():
    c = wlwire.Client.__new__(wlwire.Client)
    c.next_id = 0xFF000000 - 1
    c.ifaces = {}
    with pytest.raises(wlwire.WlError):
        c.new("wl_callback")
