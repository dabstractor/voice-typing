"""Unit tests for tests/pi_seam_support.py (P1.M5.T1.S1).

Pure-stdlib tests — no pi, tmux, sockets, or the lab driver. They pin the
protocol-v1 data model, the closed reply/event vocabularies (mirroring
bulk_delivery.ShowResult), the proof oracle, and the bounded renderer.
"""

import json

import pytest

from pi_seam_support import (
    ASCII_PROBE,
    ERROR_VOCAB,
    EVENT_VOCAB,
    EXPECTED_MATRIX,
    REFUSE_REASONS,
    REPLACE_NEW,
    REPLACE_OLD,
    REQUEST_KINDS,
    RESULT_VOCAB,
    UNITS,
    UNICODE_PROBE,
    OpRequest,
    build_probe_payloads,
    build_probe_plan,
    classify_event,
    classify_reply,
    expected_matrix,
    is_event,
    json_dumps,
    render_proof_table,
)


# ---------------------------------------------------------------------------
# vocabularies: closed and ShowResult-mirrored
# ---------------------------------------------------------------------------


def test_result_vocab_mirrors_showresult_minus_unknown():
    # voice_typing/bulk_delivery.py ShowResult: applied|unchanged|refused|unknown;
    # socket ops are synchronous, so `unknown` stays reserved for S2's deadline layer.
    assert RESULT_VOCAB == frozenset({"applied", "unchanged", "refused"})


def test_refuse_reasons_closed():
    assert REFUSE_REASONS == frozenset({"range not owned", "dirty", "out_of_bounds"})


def test_event_vocab_closed():
    assert EVENT_VOCAB == frozenset({"takeover"})


def test_error_vocab_closed():
    assert ERROR_VOCAB == frozenset(
        {"malformed_json", "not_object", "unknown_op", "bad_args", "not_ready", "other"}
    )


def test_units_marker():
    assert UNITS == "utf-16"


# ---------------------------------------------------------------------------
# OpRequest encoding (byte-exact wire shape)
# ---------------------------------------------------------------------------


def test_insert_request_encode_exact():
    req = OpRequest("insert", text="hi")
    assert json.loads(req.encode()) == {"op": "insert", "text": "hi"}
    assert req.encode() == '{"op":"insert","text":"hi"}'  # compact, insertion-ordered


def test_replace_request_encode_exact():
    req = OpRequest("replace", text="x", start=3, end=9)
    assert json.loads(req.encode()) == {
        "op": "replace",
        "text": "x",
        "start": 3,
        "end": 9,
    }
    assert list(json.loads(req.encode())) == ["op", "text", "start", "end"]


def test_cancel_read_encode():
    assert json.loads(OpRequest("cancel").encode()) == {"op": "cancel"}
    assert json.loads(OpRequest("read").encode()) == {"op": "read"}


def test_unicode_payload_roundtrips_through_json():
    line = OpRequest("insert", text=UNICODE_PROBE).encode()
    assert json.loads(line)["text"] == UNICODE_PROBE  # ensure_ascii=False preserved
    assert "日本語" in line


# ---------------------------------------------------------------------------
# classify_reply: legal replies
# ---------------------------------------------------------------------------


def test_insert_applied_reply():
    reply = classify_reply(
        {"ok": True, "result": "applied", "cursor": {"line": 0, "col": 5}, "changes": 1}
    )
    assert reply.ok and reply.result == "applied"
    assert reply.cursor == {"line": 0, "col": 5}
    assert reply.changes == 1


def test_replace_unchanged_zero_diff():
    reply = classify_reply(
        {
            "ok": True,
            "result": "unchanged",
            "cursor": {"line": 0, "col": 0},
            "changes": 0,
        }
    )
    assert reply.result == "unchanged" and reply.changes == 0


def test_refused_with_reason():
    for reason in REFUSE_REASONS:
        reply = classify_reply({"ok": True, "result": "refused", "reason": reason})
        assert reply.result == "refused" and reply.reason == reason


def test_refused_carries_instrumentation_when_present():
    reply = classify_reply(
        {
            "ok": True,
            "result": "refused",
            "reason": "range not owned",
            "cursor": {"line": 1, "col": 2},
            "changes": 0,
        }
    )
    assert reply.cursor == {"line": 1, "col": 2} and reply.changes == 0


def test_read_reply_full_state():
    raw = {
        "ok": True,
        "result": "applied",
        "text": "hello",
        "cursor": {"line": 0, "col": 5},
        "owned": {"start": 0, "end": 5},
        "dirty": False,
        "units": "utf-16",
        "changes": 3,
    }
    reply = classify_reply(raw)
    assert reply.text == "hello"
    assert reply.owned == (0, 5)  # normalized to a tuple
    assert reply.dirty is False and reply.units == "utf-16" and reply.changes == 3


def test_read_reply_owned_null():
    raw = {
        "ok": True,
        "result": "applied",
        "text": "",
        "cursor": {"line": 0, "col": 0},
        "owned": None,
        "dirty": False,
        "units": "utf-16",
    }
    reply = classify_reply(raw)
    assert reply.owned is None


# ---------------------------------------------------------------------------
# classify_reply: error replies and violations
# ---------------------------------------------------------------------------


def _err(raw) -> str:
    reply = classify_reply(raw)
    assert reply.ok is False and reply.result == "error"
    return reply.error_kind


def test_error_categories():
    assert (
        _err({"ok": False, "error": "malformed JSON: Unexpected token"})
        == "malformed_json"
    )
    assert _err({"ok": False, "error": "request must be a JSON object"}) == "not_object"
    assert _err({"ok": False, "error": 'unknown op: "frobnicate"'}) == "unknown_op"
    assert _err({"ok": False, "error": "editor not ready"}) == "not_ready"
    assert _err({"ok": False, "error": "insert: 'text' must be a string"}) == "bad_args"
    assert _err({"ok": False, "error": "op failed: boom"}) == "other"


@pytest.mark.parametrize(
    "raw",
    [
        {"result": "applied"},  # ok missing
        {"ok": 1, "result": "applied"},  # ok not bool
        {"ok": True, "result": "Applied"},  # not in vocabulary
        {"ok": True, "result": "unknown"},  # reserved for S2 — illegal over this socket
        {
            "ok": True,
            "result": "refused",
            "reason": "because",
        },  # reason not in vocabulary
        {
            "ok": True,
            "result": "applied",
            "cursor": {"line": -1, "col": 0},
        },  # negative cursor
        {
            "ok": True,
            "result": "applied",
            "cursor": {"row": 0, "col": 0},
        },  # wrong key (line, not row)
        {"ok": True, "result": "applied", "changes": -1},
        {
            "ok": True,
            "result": "applied",
            "text": "x",
            "units": "bytes",
        },  # units must be utf-16
        {
            "ok": True,
            "result": "applied",
            "text": "x",
            "units": "utf-16",
            "dirty": "no",
        },
        {
            "ok": True,
            "result": "applied",
            "text": "x",
            "units": "utf-16",
            "owned": {"start": 5, "end": 2},
        },
        {"ok": False},  # error missing
        {"ok": False, "error": ""},
    ],
)
def test_classify_rejects_violations(raw):
    with pytest.raises(ValueError):
        classify_reply(raw)


def test_classify_rejects_non_dict():
    with pytest.raises(ValueError):
        classify_reply(["ok", True])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# classify_event / is_event
# ---------------------------------------------------------------------------


def test_takeover_event():
    evt = classify_event({"event": "takeover", "source": "key"})
    assert evt.event == "takeover" and evt.source == "key"


def test_event_violations():
    with pytest.raises(ValueError):
        classify_event({"event": "takeover", "source": "mouse"})
    with pytest.raises(ValueError):
        classify_event({"event": "hijack", "source": "key"})


def test_is_event_discriminator():
    assert is_event({"event": "takeover", "source": "key"})
    assert not is_event({"ok": True, "result": "applied"})
    assert not is_event({"op": "read"})


# ---------------------------------------------------------------------------
# oracle: expected_matrix
# ---------------------------------------------------------------------------


def test_oracle_covers_every_request_kind():
    assert set(expected_matrix()) == set(REQUEST_KINDS)


def test_oracle_rows_nonempty_and_closed():
    for kind, legal in expected_matrix().items():
        assert len(legal) > 0, kind
        assert legal <= RESULT_VOCAB | {"error"}, kind


def test_oracle_semantics():
    m = expected_matrix()
    assert m["insert"] == frozenset({"applied"})
    assert m["replace"] == frozenset({"applied", "unchanged", "refused"})
    assert m["cancel"] == frozenset({"applied", "unchanged"})
    assert m["read"] == frozenset({"applied"})
    assert m["malformed"] == frozenset({"error"})
    # fresh copy: mutating the returned dict must not touch the module constant
    m["insert"] = frozenset()
    assert EXPECTED_MATRIX["insert"] == frozenset({"applied"})


# ---------------------------------------------------------------------------
# probe payloads / plan
# ---------------------------------------------------------------------------


def test_probe_payloads_exact_strings():
    p = build_probe_payloads()
    assert p["ascii"] == "hello from pi seam"
    assert p["unicode"] == UNICODE_PROBE
    assert p["replace_old"] == REPLACE_OLD and p["replace_new"] == REPLACE_NEW
    assert p["owned_after_cancel_probe"] == "again"


def test_probe_offsets_consistent():
    prefix = "pre-existing "
    p = build_probe_payloads(prefix)
    ascii_start = len(prefix)
    assert p["replace_start"] == ascii_start + len(ASCII_PROBE) - len(REPLACE_OLD)
    assert p["replace_end"] == ascii_start + len(ASCII_PROBE)
    # zero-diff targets the span AS THE REPLACE LEFT IT, with identical text
    assert p["zero_diff_start"] == p["replace_start"]
    assert p["zero_diff_end"] == p["replace_start"] + len(REPLACE_NEW)
    assert p["zero_diff_text"] == REPLACE_NEW
    assert p["oob_end"] > p["replace_end"]


def test_probe_plan_row_count_and_kinds():
    plan = build_probe_plan("")
    kinds = [req.op for _, req in plan.rows]
    assert kinds.count("insert") == 3  # ascii, unicode, re-own probe
    assert kinds.count("replace") == 3  # owned, zero-diff, outside
    assert kinds.count("cancel") == 1
    assert kinds.count("read") == 1
    assert len(plan.rows) == 8


# ---------------------------------------------------------------------------
# renderer: bounded
# ---------------------------------------------------------------------------


def test_render_proof_table_bounded():
    rows = [
        {"step": str(i), "request": f"op{i}|pipe", "result": "pass", "detail": "x" * 50}
        for i in range(500)
    ]
    table = render_proof_table(rows)
    assert len(table.splitlines()) <= 120
    assert "rows elided" in table
    assert "op0\\|pipe" in table  # pipes escaped


def test_render_proof_table_small_passthrough():
    rows = [{"step": "1", "request": "insert", "result": "pass", "detail": "ok"}]
    table = render_proof_table(rows)
    assert "| 1 | insert | pass | ok |" in table
    assert len(table.splitlines()) == 3


# ---------------------------------------------------------------------------
# purity: no pi/tmux/socket imports in the support module
# ---------------------------------------------------------------------------


def test_support_module_is_pure_stdlib():
    import pi_seam_support

    banned = ("socket", "subprocess", "tmux", "shutil", "pi_seam_lab")
    source = open(pi_seam_support.__file__).read()
    for word in banned:
        assert f"import {word}" not in source
        assert "from " + word not in source


def test_json_dumps_compact():
    assert json_dumps({"a": 1, "b": "x"}) == '{"a":1,"b":"x"}'
