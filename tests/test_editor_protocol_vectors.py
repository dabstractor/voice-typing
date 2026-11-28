"""Shared v1 protocol vectors (PRD §4.8.1; P1.M1.T3.S2).

Loads tests/fixtures/editor_v1.json and asserts EVERY case against voice_typing.editor_protocol —
the same file the Pi (TS) and Neovim (Lua) adapters consume (P1.M2.T1.S2 / P1.M2.T2.S1), so a
cross-language divergence is a named case, not a debugging session. Frame cases replay S1's
byte-level scenarios via bytes.fromhex("wire_hex") through FrameReader (bytes-only, terminal
"eof" reason included). NO socket, NO editor, NO daemon import. Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol_vectors.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from voice_typing import editor_protocol as ep

VECTORS = json.loads((Path(__file__).resolve().parent / "fixtures" / "editor_v1.json").read_text("utf-8"))
CASES = VECTORS["cases"]


def _cases(kind):
    return [c for c in CASES if c["kind"] == kind]


class _OneShotSock:
    """Returns the given bytes in ONE recv, then b'' (EOF) — the scripted fake recv S1's tests use."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def recv(self, n: int) -> bytes:
        out, self._data = self._data[:n], self._data[n:]
        return out


# --- fixture self-consistency (the oracle must match the module's exported constants) ---
def test_fixture_constants_match_module():
    assert VECTORS["version"] == ep.PROTOCOL_VERSION == 1
    assert VECTORS["limits"]["frame_bytes"] == ep.MAX_FRAME_BYTES
    assert VECTORS["limits"]["context_bytes"] == ep.MAX_CONTEXT_BYTES
    assert VECTORS["limits"]["final_text_bytes"] == ep.MAX_FINAL_TEXT_BYTES
    assert set(VECTORS["codes"]["error"]) == set(ep.NATIVE_ERROR_CODES)
    assert set(VECTORS["codes"]["end_reason"]) == set(ep.END_REASONS)
    assert set(VECTORS["codes"]["context_reason"]) == set(ep.CONTEXT_REASONS)
    assert VECTORS["pad_tables"]["open_delimiters"] == ep.OPEN_DELIMITERS
    assert VECTORS["pad_tables"]["close_punctuation"] == ep.CLOSE_PUNCTUATION


def test_fixture_case_names_are_unique_and_kinds_known():
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names)), "vector names must be stable unique ids"
    assert {c["kind"] for c in CASES} == {"request", "event", "pad", "truncate", "frame"}
    assert len(CASES) >= 40


# --- requests ---
@pytest.mark.parametrize("case", _cases("request"), ids=lambda c: c["name"])
def test_request_vectors(case):
    if case["expect"]["ok"]:
        assert ep.validate_request(case["frame"]) is case["frame"]
    else:
        with pytest.raises(ep.ProtocolError) as ei:
            ep.validate_request(case["frame"])
        assert ei.value.code == case["expect"]["code"]


# --- events (daemon emits / clients validate on receive) ---
@pytest.mark.parametrize("case", _cases("event"), ids=lambda c: c["name"])
def test_event_vectors(case):
    if case["expect"]["ok"]:
        assert ep.validate_event(case["frame"]) is case["frame"]
    else:
        with pytest.raises(ep.ProtocolError) as ei:
            ep.validate_event(case["frame"])
        assert ei.value.code == case["expect"]["code"]


# --- accepted events must also be wire-encodable within S1's frame bound ---
@pytest.mark.parametrize("case", [c for c in _cases("event") if c["expect"]["ok"]], ids=lambda c: c["name"])
def test_accepted_events_encode_within_frame_bound(case):
    line = ep.encode_line(case["frame"])          # raises FrameError if > 32 KiB
    assert line.endswith(b"\n") and len(line) <= ep.MAX_FRAME_BYTES


# --- §C splice padding ---
@pytest.mark.parametrize("case", _cases("pad"), ids=lambda c: c["name"])
def test_splice_padding_vectors(case):
    assert list(ep.splice_padding(case["before"], case["text"], case["after"])) == case["expect"]


# --- §A code-point-safe newest-suffix truncation ---
@pytest.mark.parametrize("case", _cases("truncate"), ids=lambda c: c["name"])
def test_truncate_utf8_suffix_vectors(case):
    out = ep.truncate_utf8_suffix(case["text"], case.get("max_bytes", ep.MAX_CONTEXT_BYTES))
    assert out == case["expect"]
    assert len(out.encode("utf-8")) <= case.get("max_bytes", ep.MAX_CONTEXT_BYTES)   # never over


# --- S1 framing cases replayed for cross-language parity (bytes come from hex; no decode step —
#     FrameReader is bytes-only, so an invalid-UTF-8 frame round-trips as raw bytes) ---
@pytest.mark.parametrize("case", _cases("frame"), ids=lambda c: c["name"])
def test_frame_vectors(case):
    reader = ep.FrameReader(_OneShotSock(bytes.fromhex(case["wire_hex"])).recv)
    frames, errors = [], []
    while True:
        try:
            frames.append(reader.read_frame_bytes())
        except ep.FrameError as fe:
            errors.append(fe.reason)
            if fe.reason == "eof":
                break
    assert frames == [bytes.fromhex(h) for h in case["expect"]["frames_hex"]]
    assert errors == case["expect"]["errors"]


# --- the probe-pinned properties that motivated the vectors (kept explicit, not only via the file) ---
def test_uuid_validator_rejects_forms_uuid_module_accepts():
    import uuid

    loose = ["{" + VECTORS["id"] + "}", "urn:uuid:" + VECTORS["id"], VECTORS["id"].upper(),
             VECTORS["id"].replace("-", "")]
    for s in loose:
        assert uuid.UUID(s) and not ep.is_uuid_v4(s)    # the stdlib accepts; the wire does not


def test_bool_is_not_an_int_seq():
    with pytest.raises(ep.ProtocolError):
        ep.validate_request({"cmd": "applied", "id": VECTORS["id"], "seq": True})


def test_text_limit_is_utf8_bytes_not_wire_bytes():
    text = '"' * 4096                               # 4096 text bytes, 8279 wire bytes
    assert ep.utf8_len(text) == 4096
    assert len(ep.encode_line({"event": "final", "id": VECTORS["id"], "seq": 1, "text": text})) > 4096
    ep.validate_event({"event": "final", "id": VECTORS["id"], "seq": 1, "text": text})   # passes
    with pytest.raises(ep.ProtocolError) as ei:
        ep.validate_event({"event": "final", "id": VECTORS["id"], "seq": 1, "text": text + "x"})
    assert ei.value.code == "too_large"


def test_errors_never_echo_field_values():
    secret = "private editor text " * 250           # 5000 B; +1 → too_large actually raises
    with pytest.raises(ep.ProtocolError) as ei:
        ep.validate_request({"cmd": "editor-start", "version": 1, "id": VECTORS["id"], "context": secret + "x"})
    assert "private" not in ei.value.detail and secret not in str(ei.value)
    assert ep.native_error_reply("too_large") == {"ok": False, "error": "too_large"}


def test_request_kind_recognizes_only_native_cmds():
    assert ep.request_kind({"cmd": "ping", "id": VECTORS["id"]}) == "ping"
    assert ep.request_kind({"cmd": "toggle"}) is None and ep.request_kind([]) is None
