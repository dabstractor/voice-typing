"""tests/test_ime_g3_support.py — collected, compositor-free unit tests for
tests/ime_g3_support.py (P1.M4.T5.S1 Task 2).

Pins: the frame oracle matrix (noop/change/transient/missing-final/RLE-window
boundary), the closed row-status vocabulary (R.7), payload byte sizes (951 B
byte-exact; 20-sentence spans under the 4000 B cap; over-cap > 4000 B), the
report renderer's 150-line hard cap under a 200-row stress, and determinism.
No env gate, no I/O outside pytest, stdlib only. Run:

    timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_support.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ime_g3_support import (  # noqa: E402
    MAX_REPORT_LINES,
    OVERCAP_BLOCKED_REASON,
    ROW_IDS,
    ROW_STATUSES,
    RowVerdict,
    build_payloads,
    render_report,
    row_status,
    single_edit_analysis,
    text_hash8,
)

# --- helpers -------------------------------------------------------------------


def _dump(text: str, frames: int, ring) -> dict:
    return {"text": text, "frames": frames, "ring_rle": ring}


def _rle(*pairs):
    return [[h, n] for h, n in pairs]


def _all_true(n=1, correction=False):
    vs = [RowVerdict(row="gtk-short-updates", passed=True) for _ in range(n)]
    return vs


# --- row_status: closed vocabulary ----------------------------------------------


def test_row_status_output_always_starts_with_vocab_word():
    cases = [
        ([RowVerdict(row="r", passed=True)], False),
        ([RowVerdict(row="r", passed=True)], True),
        ([RowVerdict(row="r", passed=False, checks=("byte-exact",))], False),
        ([RowVerdict(row="r", passed=None)], False),
        ([RowVerdict(row="r", passed=True)], False),
    ]
    for verdicts, corr in cases:
        assert row_status(verdicts, exercised_correction=corr).startswith(ROW_STATUSES)


def test_row_status_verified_requires_correction_exercised():
    v = _all_true()
    assert row_status(v, exercised_correction=True) == "verified (versions + evidence)"
    assert row_status(v, exercised_correction=False) == "insert-only"


def test_row_status_false_maps_to_blocked_with_first_check():
    v = [
        RowVerdict(row="gtk-short-updates", passed=True),
        RowVerdict(
            row="gtk-short-updates",
            sub="op3",
            passed=False,
            checks=("cseq-delta", "byte-exact"),
        ),
    ]
    assert row_status(v, exercised_correction=True) == "blocked (FAILED: cseq-delta)"


def test_row_status_none_is_untested_never_pass():
    v = [RowVerdict(row="gtk-long-unicode", sub="mixed-3500b", passed=None)]
    out = row_status(v, exercised_correction=False)
    assert out == "untested (infra: mixed-3500b)"
    assert "verified" not in out


def test_row_status_capability_blocked_reason_wins():
    v = _all_true()
    out = row_status(
        v, exercised_correction=False, capability_blocked_reason=OVERCAP_BLOCKED_REASON
    )
    assert out == f"blocked ({OVERCAP_BLOCKED_REASON})"


def test_row_status_empty_verdicts_is_untested():
    assert row_status([], exercised_correction=False).startswith("untested")


def test_row_status_false_beats_capability_and_none():
    v = [
        RowVerdict(row="r", passed=False, checks=("x",)),
        RowVerdict(row="r2", passed=None),
    ]
    assert row_status(v, exercised_correction=False).startswith("blocked (FAILED")


# --- frame oracle ---------------------------------------------------------------


def test_oracle_noop_empty_window_passes():
    before = _dump("abc", 10, _rle(("h1", 10)))
    after = _dump("abc", 10, _rle(("h1", 10)))
    a = single_edit_analysis(before, after, expect="noop")
    assert a["ok"] and a["transitions"] == 0 and a["frames"] == 0


def test_oracle_noop_with_idle_frames_same_hash_passes():
    hold = text_hash8("old")
    ring = _rle((hold, 8), (hold, 3))  # idle frames, then the earlier same-hash tail
    before = _dump("old", 4, _rle((hold, 4)))
    after = _dump("old", 11, ring)  # window = 7 idle frames, all hash 'old'
    a = single_edit_analysis(before, after, expect="noop")
    assert a["ok"] and a["transitions"] == 0 and a["transient_hashes"] == []


def test_oracle_change_exactly_one_transition_and_painted_final():
    ha, hb = text_hash8("before text"), text_hash8("after text")
    ring = _rle((ha, 6), (hb, 4))  # newest-last: 4 painted-final frames
    before = _dump("before text", 10, _rle((ha, 10)))
    after = _dump("after text", 20, ring)  # window = 10 frames: 6 ha + 4 hb
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"]
    assert a["transitions"] == 1
    assert a["transient_hashes"] == []
    assert a["painted_final"] is True
    assert a["frames"] == 10


def test_oracle_transient_frame_is_rejected():
    ha, hm, hb = text_hash8("before"), text_hash8("mid"), text_hash8("after")
    ring = _rle((ha, 3), (hm, 2), (hb, 3))  # a delete/retype frame painted 'mid'
    before = _dump("before", 10, _rle((ha, 10)))
    after = _dump("after", 18, ring)
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"] is False
    assert a["transient_hashes"] == [hm]
    assert a["transitions"] == 2


def test_oracle_missing_painted_final_is_rejected():
    ha = text_hash8("before")
    ring = _rle((ha, 8))  # window painted, but only OLD text ever appeared
    before = _dump("before", 10, _rle((ha, 10)))
    after = _dump("after", 18, ring)
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"] is False
    assert a["painted_final"] is False
    assert a["transitions"] == 0


def test_oracle_consumes_exactly_window_frames():
    """Consumption stops after exactly `want` frames — older ring segments
    (beyond the window's old boundary) are never consulted."""
    hx, ha, hb = text_hash8("x"), text_hash8("a"), text_hash8("b")
    ring = _rle((hx, 4), (ha, 8), (hb, 6))  # newest-last; window = newest 8
    before = _dump("a", 10, _rle((ha, 10)))
    after = _dump("b", 18, ring)  # window 8 = 2 ha + 6 hb; hx never reached
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"]
    assert a["transitions"] == 1
    assert a["frames"] == 8


def test_oracle_boundary_straddle_counts_one_transition():
    """The before-dump often IS the last old-text paint (on-demand clock paints
    nothing between ops): the window then contains only final-hash frames, and
    the A→B transition is the boundary at the window start — counted as the
    commit's exactly-1 transition."""
    ha, hb = text_hash8("before"), text_hash8("after")
    ring = _rle((ha, 10), (hb, 1))  # the window's single frame carries hB
    before = _dump("before", 10, _rle((ha, 10)))
    after = _dump("after", 11, ring)
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"]
    assert a["transitions"] == 1
    assert a["painted_final"] is True
    assert a["transient_hashes"] == []


def test_oracle_rle_cap_underflow_is_honest_failure():
    before = _dump("x", 100, _rle(("h", 100)))
    after = _dump("y", 300, _rle(("h2", 5)))  # only 5 of 200 window frames kept
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"] is False
    assert a["underflow"] is True


def test_oracle_partial_segment_counts_as_its_hash():
    ha, hb = text_hash8("a"), text_hash8("b")
    ring = _rle((ha, 7), (hb, 5))  # window 9: 4 ha + 5 hb (hb pair cut at 5)
    before = _dump("a", 3, _rle((ha, 3)))
    after = _dump("b", 12, ring)
    a = single_edit_analysis(before, after, expect="change")
    assert a["ok"] and a["frames"] == 9


def test_oracle_rejects_bad_expect():
    with pytest.raises(ValueError):
        single_edit_analysis(_dump("a", 1, []), _dump("a", 1, []), expect="x")


# --- payloads -------------------------------------------------------------------


def test_payload_unicode_951b_byte_exact_and_multilingual():
    p = build_payloads()["unicode_951b"]
    assert len(p.encode("utf-8")) == 951
    assert any("\u4e00" <= ch <= "\u9fff" for ch in p)  # CJK
    assert any(0x1F300 <= ord(ch) <= 0x1FAFF for ch in p)  # emoji (astral)
    assert any(ch in "áéíóúñüö" for ch in p)  # accents


def test_payload_twenty_sentence_spans_in_cap_and_differ_in_first_word():
    p = build_payloads()
    for key in ("twenty_committed", "twenty_corrected"):
        n = len(p[key].encode("utf-8"))
        assert 1200 <= n < 4000, (key, n)
    assert (
        p["twenty_committed"].split(" ", 1)[1] == p["twenty_corrected"].split(" ", 1)[1]
    )
    assert (
        p["twenty_committed"].split(" ", 1)[0] != p["twenty_corrected"].split(" ", 1)[0]
    )
    assert p["twenty_committed"].count(".") == 20


def test_payload_mixed_and_overcap_sizes():
    p = build_payloads()
    assert 3300 <= len(p["mixed_3500b"].encode("utf-8")) <= 3700
    assert len(p["overcap_4500b"].encode("utf-8")) > 4000


def test_payload_short_six_growing_under_cap():
    shorts = build_payloads()["short"]
    assert len(shorts) == 6
    sizes = [len(s.encode("utf-8")) for s in shorts]
    assert sizes == sorted(sizes) and len(set(sizes)) == 6
    assert all(n < 4000 for n in sizes)


def test_payloads_deterministic():
    assert build_payloads() == build_payloads()


# --- report renderer ------------------------------------------------------------


def _row(i: int) -> dict:
    return {
        "id": f"row-{i}",
        "title": "t",
        "passed": True,
        "status": "verified (versions + evidence)",
        "evidence": [f"ev line {j}" for j in range(20)],
    }


def test_render_report_basic_shape_and_banner():
    rows = [
        {
            "id": rid,
            "title": rid,
            "passed": True,
            "status": "insert-only",
            "evidence": ["t_ms=12 (mechanism-level, not G5)"],
        }
        for rid in ROW_IDS
    ]
    out = render_report(
        {"kernel": "7.2.7-arch1-1", "sway": "sway 1.12", "gtk": "4.24.1"},
        rows,
        {
            "date": "2026-11-23",
            "head": "abc1234",
            "command": "timeout 300 env IME_G3_LAB=1 …",
            "summary": "5 rows, 5 pass",
            "open_items": ["preedit transition not rowed here"],
        },
    )
    lines = out.splitlines()
    assert len(lines) <= MAX_REPORT_LINES
    assert "A G2 pass never marks a row verified" in out
    assert "NEVER G5" in out
    assert "| gtk-short-updates | true | insert-only |" in out
    assert "Open items" in out


def test_render_report_hard_cap_under_200_row_stress():
    rows = [_row(i) for i in range(200)]
    out = render_report(
        {},
        rows,
        {
            "date": "d",
            "head": "h",
            "command": "c",
            "summary": "s",
            "open_items": ["x", "y"],
        },
    )
    lines = out.splitlines()
    assert len(lines) <= MAX_REPORT_LINES
    assert lines[-1] == "- y"  # open-items tail preserved
    assert any("truncated" in ln for ln in lines)


def test_render_report_deterministic():
    rows = [_row(i) for i in range(5)]
    meta = {
        "date": "d",
        "head": "h",
        "command": "c",
        "summary": "s",
        "open_items": ["o"],
    }
    assert render_report({"k": "v"}, rows, meta) == render_report(
        {"k": "v"}, rows, meta
    )


def test_text_hash8_sane():
    assert text_hash8("") == "da39a3ee"
    assert text_hash8("a") != text_hash8("b")
    assert text_hash8("héllo 🌍") == text_hash8("héllo 🌍")
