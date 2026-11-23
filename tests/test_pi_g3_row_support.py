"""Pure unit tests for pi_g3_row_support (P1.M5.T2.S1).

Always collected — no desktop, no pi, no sockets (the lab itself is
env-gated). Covers: the trace table's closed vocabularies and order, the
honest status rule (every branch), the editor-state mirror against the
landed extension's op semantics (incl. astral UTF-16 math via map_span),
the paste-marker/control-byte detector, and the bounded report renderer.
"""

from __future__ import annotations

import json

try:
    from pi_g3_row_support import (  # sibling import
        EXPECTS,
        KINDS,
        LONG_CORRECTED,
        LONG_PAYLOAD,
        MAX_REPORT_LINES,
        STATUSES,
        EditorMirror,
        G3Step,
        VerdictRow,
        assert_no_paste_markers,
        render_row_report,
        row_status,
        row_traces,
    )
except ImportError:  # package-style import (tests.*): namespace-relative
    from .pi_g3_row_support import (  # type: ignore[no-redef]
        EXPECTS,
        KINDS,
        LONG_CORRECTED,
        LONG_PAYLOAD,
        MAX_REPORT_LINES,
        STATUSES,
        EditorMirror,
        G3Step,
        VerdictRow,
        assert_no_paste_markers,
        render_row_report,
        row_status,
        row_traces,
    )
try:
    from pi_seam_support import UNICODE_PROBE
except ImportError:  # package-style import (tests.*): namespace-relative
    from .pi_seam_support import UNICODE_PROBE  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Trace table
# ---------------------------------------------------------------------------


def test_traces_use_closed_vocabularies() -> None:
    for s in row_traces():
        assert s.kind in KINDS, s
        assert s.expect in EXPECTS, s
        assert isinstance(s.expect_changes, int) and s.expect_changes >= 0


def test_traces_cover_the_g3_trace_list() -> None:
    kinds = [s.kind for s in row_traces()]
    for required in (
        "insert",
        "correction",
        "zero_diff",
        "finalize",
        "unicode",
        "long",
        "long_correction",
        "refusal_range",
        "refusal_oob",
        "cancel_empty",
        "cancel_pending",
        "focus",
        "takeover",
        "refusal_dirty",
        "cancel_dirty",
    ):
        assert required in kinds, required
    # the measured order: focus switch runs BEFORE the takeover leg (only a
    # delegated keystroke revokes v1; a post-takeover focus switch would be
    # unanswerable), and the dirty refusals only come AFTER takeover. The
    # owned-null refusal rides the post-cancel boundary (owned is null only
    # there — ownership binds at offset 0 and grows to the caret).
    assert kinds.index("focus") < kinds.index("takeover")
    assert kinds.index("refusal_range") < kinds.index("unicode")
    assert kinds.index("refusal_oob") > kinds.index("unicode")  # owned must be live
    for post in ("refusal_dirty", "refusal_acquire_dirty", "cancel_dirty"):
        assert kinds.index(post) > kinds.index("takeover"), post


def test_long_payload_is_1kb_single_line_ascii() -> None:
    assert len(LONG_PAYLOAD) == 1024
    assert LONG_PAYLOAD.isascii() and LONG_PAYLOAD.isprintable()
    assert "\n" not in LONG_PAYLOAD and "\t" not in LONG_PAYLOAD
    # the first-word correction rewrites exactly the first word, in place
    assert len(LONG_CORRECTED) == len(LONG_PAYLOAD)
    assert LONG_CORRECTED[5:] == LONG_PAYLOAD[5:]
    assert LONG_CORRECTED[:5] == "ALPHA"


# ---------------------------------------------------------------------------
# The honest status rule — every branch, in the PRP's decision order
# ---------------------------------------------------------------------------


def test_status_blocked_takes_precedence() -> None:
    s = row_status(
        boot_ok=False,
        traces_passed=False,
        corrections_passed=False,
        visibility_instrumented=True,
        block_reason="pi boot: SIGKILL",
    )
    assert s == "blocked (pi boot: SIGKILL)"
    assert s.startswith("blocked (")


def test_status_verified_requires_visibility_instrumentation() -> None:
    common = dict(boot_ok=True, traces_passed=True, corrections_passed=True)
    assert (
        row_status(visibility_instrumented=True, **common)
        == "verified (versions + evidence)"
    )
    assert (
        row_status(visibility_instrumented=False, **common)
        == "not verified (visibility instrumentation absent)"
    )


def test_status_insert_only_and_untested() -> None:
    assert (
        row_status(
            boot_ok=True,
            traces_passed=False,
            corrections_passed=True,
            visibility_instrumented=True,
        )
        == "insert-only"
    )
    assert (
        row_status(
            boot_ok=True,
            traces_passed=False,
            corrections_passed=False,
            visibility_instrumented=False,
        )
        == "untested"
    )


def test_status_vocabulary_membership() -> None:
    for head in STATUSES:
        assert any(
            row_status(
                boot_ok=(head != "blocked"),
                traces_passed=(head in ("verified", "not verified", "insert-only")),
                corrections_passed=True,
                visibility_instrumented=(head == "verified"),
            ).startswith(head)
            for head in STATUSES
        )


# ---------------------------------------------------------------------------
# EditorMirror — the pure oracle for the landed extension's semantics
# ---------------------------------------------------------------------------


def test_mirror_insert_extends_contiguous_ownership() -> None:
    m = EditorMirror()
    m.op_insert("hello")
    assert (m.text, m.owned, m.dirty) == ("hello", (0, 5), False)
    m.op_insert(" world")
    assert (m.text, m.owned) == ("hello world", (0, 11))


def test_mirror_replace_rewrites_owned_range_in_place() -> None:
    m = EditorMirror()
    m.op_insert("hello from pi")
    m.op_replace(0, 13, "Hello from pi")
    assert m.text == "Hello from pi"
    assert m.owned == (0, 13)
    assert m.caret_u16 == 13  # caret lands end-of-buffer after setText


def test_mirror_cancel_removes_owned_range_in_one_op() -> None:
    m = EditorMirror()
    m.op_insert("Hello from pi")
    m.op_insert("again")
    assert m.owned == (0, 18)
    m.op_cancel()  # the OWNED range is removed — it spans the whole buffer
    assert (m.text, m.owned, m.dirty) == ("", None, False)
    assert m.caret_u16 == 0


def test_mirror_unicode_offsets_route_through_map_span() -> None:
    m = EditorMirror()
    m.op_insert("Hello from pi")  # 13 ASCII units
    m.op_insert(UNICODE_PROBE)  # "Zoë — naïve 日本語 🫡" — 🫡 is 2 units
    assert len(UNICODE_PROBE) == 17  # chars
    assert m.owned == (0, 13 + 18)  # contiguous extend keeps the 0 start
    assert m.caret_u16 == 31
    assert m.cursor() == {"line": 0, "col": 31}


def test_mirror_takeover_flips_dirty_exactly_once() -> None:
    m = EditorMirror()
    m.op_insert("abc")
    assert m.dirty is False
    m.take_real_key(" ")
    assert m.dirty is True
    assert m.owned == (0, 3)  # ownership survives the keystroke
    assert m.text == "abc "
    # further keys mutate but never re-flip (the event fired only once)
    m.take_real_key(" ")
    assert m.dirty is True and m.text == "abc  "


def test_mirror_post_cancel_insert_starts_a_fresh_fragment() -> None:
    m = EditorMirror()
    m.op_insert("Hello from pi")
    m.op_cancel()
    m.op_insert("Zoë — naïve 日本語 🫡")
    assert m.owned == (0, 18)  # fresh fragment binds at the caret (0 now)


def test_mirror_replays_the_whole_trace_list() -> None:
    """Dry-run the §4 list through the mirror with the adapter's span rules:
    zero-diff vs the last applied span, insert = delta at the caret (after a
    finalize the next utterance's FULL span), replace = the owned range, and
    exactly one real key at the takeover step. The final state is what the
    live lab must witness via the editor's own read.
    """
    from voice_typing.bulk_delivery import rendered_equal

    m = EditorMirror()
    last_applied = ""
    for step in row_traces():
        if step.kind.startswith("refusal") or step.kind == "cancel_dirty":
            continue  # refused post-takeover / owned-null — NO mutation
        if not step.payload:
            if step.kind == "cancel_pending":
                m.op_cancel()
                last_applied = ""
            elif step.kind == "takeover":
                m.take_real_key(" ")
            continue  # zero-request steps mutate nothing
        if rendered_equal(last_applied, step.payload):
            if step.kind == "finalize":
                last_applied = ""  # finalize ends ownership CLIENT-side (S2)
        if step.payload.startswith(last_applied):
            m.op_insert(step.payload[len(last_applied) :])
        else:
            assert m.owned is not None
            m.op_replace(m.owned[0], m.owned[1], step.payload)
        last_applied = step.payload
    assert m.dirty is True
    assert m.owned == (0, 18 + len(LONG_CORRECTED) + 5)  # unicode+1KB+" tail"
    assert m.caret_u16 == 18 + len(LONG_CORRECTED) + 6  # + the takeover space
    assert m.text.endswith(" tail ")
    assert "\n" not in m.text
    assert assert_no_paste_markers(m.text) == ()


def test_step_payloads_are_single_line_printable() -> None:
    for s in row_traces():
        if s.payload:
            assert "\n" not in s.payload and "\t" not in s.payload, s.name
            assert not assert_no_paste_markers(s.payload), s.name


def test_g3step_is_frozen() -> None:
    step = G3Step("n", "insert", "x", "applied", 1)
    try:
        step.payload = "y"  # type: ignore[misc]
        raised = False
    except Exception:  # noqa: BLE001 - frozen dataclass raises
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# Paste-marker / control-byte detector — catches every forbidden byte
# ---------------------------------------------------------------------------


def test_marker_detector_is_clean_on_prose() -> None:
    assert assert_no_paste_markers(UNICODE_PROBE) == ()
    assert assert_no_paste_markers(LONG_PAYLOAD) == ()
    assert assert_no_paste_markers("") == ()


def test_marker_detector_catches_bracketed_paste_markers() -> None:
    assert any("200~" in v for v in assert_no_paste_markers("a\x1b[200~b"))
    assert any("201~" in v for v in assert_no_paste_markers("a\x1b[201~b"))


def test_marker_detector_catches_control_bytes_and_newlines() -> None:
    assert any("control-byte" in v for v in assert_no_paste_markers("a\x00b"))
    assert any("whitespace-control" in v for v in assert_no_paste_markers("a\tb"))
    assert any("whitespace-control" in v for v in assert_no_paste_markers("a\nb"))
    assert any("whitespace-control" in v for v in assert_no_paste_markers("a\rb"))


# ---------------------------------------------------------------------------
# Verdict rows + bounded renderer
# ---------------------------------------------------------------------------


def test_verdict_row_jsonl_round_trip() -> None:
    row = VerdictRow(
        row="short-insert-1",
        passed=True,
        status="applied",
        detail="changes=1",
        versions={"pi": "1.0.2"},
        evidence=("verdicts.jsonl:2",),
    )
    parsed = json.loads(row.to_jsonl())
    assert parsed["row"] == "short-insert-1"
    assert parsed["passed"] is True
    assert parsed["versions"] == {"pi": "1.0.2"}


def test_untested_row_serializes_null_pass() -> None:
    parsed = json.loads(VerdictRow("r", None, "untested").to_jsonl())
    assert parsed["passed"] is None  # infra-untested is NEVER a pass


def test_renderer_is_bounded_and_carries_the_verdict() -> None:
    rows = [
        VerdictRow(
            f"row-{i}",
            True,
            "not verified (visibility instrumentation absent)",
            "changes=1 cursor ok",
            {"pi": "1.0.2", "ghostty": "1.4.0-arch2"},
            (),
        )
        for i in range(60)
    ]
    report = render_row_report(
        "t",
        ["- Date: today", f"- Command: {ROW_CMD}"],
        rows,
        ["## notes", "t_ms values are mechanism-level, NEVER G5 timing."],
    )
    lines = report.splitlines()
    assert len(lines) <= MAX_REPORT_LINES
    assert "not verified" in report
    assert "NEVER G5" in report


ROW_CMD = "timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py"
