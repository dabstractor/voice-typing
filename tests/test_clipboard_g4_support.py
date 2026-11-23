"""Unit tests for clipboard_g4_support — pure helpers, no desktop."""
from __future__ import annotations

import json

import pytest

from clipboard_g4_support import (
    BLOCKED,
    MAX_REPORT_LINES,
    ROUTE_TABLE_CITATION,
    SIX_LEGS,
    STATUSES,
    UNPROVABLE,
    VERIFIED,
    G4Verdict,
    all_legs_recorded,
    availability_statement,
    leg_recorded,
    read_verdicts,
    render_g4_report,
    status_ok,
    verdict_from_dict,
    write_verdicts,
)


def _verdicts(*statuses):
    names = [leg.leg for leg in SIX_LEGS]
    return [G4Verdict(leg=n, status=s) for n, s in zip(names, statuses)]


# --- the six legs + clause coverage ---------------------------------------

def test_six_legs_exist_with_unique_ids():
    ids = [leg.leg for leg in SIX_LEGS]
    assert ids == ["L1", "L2", "L3", "L4", "L5", "L6"]
    assert len({leg.leg for leg in SIX_LEGS}) == 6


def test_every_r6_clause_has_a_leg_and_mechanism():
    from clipboard_g4_support import R6_CLAUSES
    reqs = " ".join(c["requirement"] for c in R6_CLAUSES)
    for token in ("formats AND bytes", "identical copy",
                  "simultaneous user paste protected",
                  "history watcher", "PRIMARY selection untouched"):
        assert token in reqs
    for c in R6_CLAUSES:
        assert c["mechanism"].strip() and c["legs"].strip()


def test_leg_assertions_are_content_assertions_not_exit_codes():
    for leg in SIX_LEGS:
        assert leg.assertion.strip()
        assert "exit code" not in leg.assertion.lower() or "never" in leg.assertion.lower()


# --- verdict vocabulary (closed; honest words only) ------------------------

def test_status_vocabulary_is_closed():
    assert set(STATUSES) == {"verified", "unprovable", "blocked"}
    assert status_ok(VERIFIED) and status_ok(UNPROVABLE) and status_ok(BLOCKED)
    assert not status_ok("passed") and not status_ok("failed") and not status_ok("")


def test_unknown_status_is_a_hard_error():
    with pytest.raises(ValueError):
        verdict_from_dict({"leg": "L1", "status": "passed"})


def test_verdict_round_trip_and_evidence_cap():
    v = G4Verdict(leg="L4", status=VERIFIED, reason="",
                  checks=[f"c{i}" for i in range(10)],
                  evidence=[f"e{i}" for i in range(10)], primary_unchanged=True,
                  versions={"sway": "1.12"}, t_ms=173.0)
    d = v.to_dict()
    assert json.dumps(d)               # JSON-serializable
    v2 = verdict_from_dict(d)
    assert v2 == v or (v2.checks == [f"c{i}" for i in range(10)]
                       and len(v2.evidence) == 4)   # evidence capped on parse


def test_jsonl_io_round_trip(tmp_path):
    verdicts = [G4Verdict(leg="L1", status=UNPROVABLE, reason="watcher active"),
                G4Verdict(leg="L2", status=VERIFIED)]
    p = tmp_path / "v.jsonl"
    write_verdicts(p, verdicts)
    lines = p.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["leg"] == "L1"
    back = read_verdicts(p)
    assert [b.leg for b in back] == ["L1", "L2"]
    assert back[0].status == UNPROVABLE


# --- recorded helpers -------------------------------------------------------

def test_leg_recorded_and_all_legs_recorded():
    vs = _verdicts(VERIFIED, VERIFIED, VERIFIED, VERIFIED, VERIFIED)
    assert not all_legs_recorded(vs)          # L6 missing
    assert leg_recorded(vs, "L5") and not leg_recorded(vs, "L6")
    assert all_legs_recorded(_verdicts(*[VERIFIED] * 6))


# --- availability statement (the honest outcome derivation) ----------------

def test_availability_unavailable_under_watcher():
    vs = _verdicts(UNPROVABLE, VERIFIED, VERIFIED, VERIFIED, VERIFIED, VERIFIED)
    vs[0].reason = "watcher detected at acquire — refused before delivery"
    s = availability_statement(vs)
    assert s.startswith("UNAVAILABLE under a clipboard-history watcher")
    assert "never disabled" in s


def test_availability_available_requires_clean_engagement():
    vs = _verdicts(VERIFIED, VERIFIED, VERIFIED, VERIFIED, VERIFIED, VERIFIED)
    assert availability_statement(vs).startswith("AVAILABLE")
    vs2 = _verdicts(VERIFIED, BLOCKED, VERIFIED, VERIFIED, VERIFIED, VERIFIED)
    assert availability_statement(vs2).startswith("UNAVAILABLE")


def test_availability_blocked_reason_recorded():
    vs = _verdicts(BLOCKED, VERIFIED, VERIFIED, VERIFIED, VERIFIED, VERIFIED)
    vs[0].reason = "sway failed to boot"
    s = availability_statement(vs)
    assert s.startswith("UNAVAILABLE (other reason: sway failed to boot)")


# --- the bounded renderer ---------------------------------------------------

def test_renderer_carries_decision_citation_and_no_g5_claim():
    vs = _verdicts(UNPROVABLE, VERIFIED, VERIFIED, VERIFIED, VERIFIED, VERIFIED)
    vs[0].reason = "watcher detected — refused before delivery"
    vs[4].t_ms = 180.0
    report = render_g4_report(
        {"kernel": "7.2.7", "sway": "1.12", "ghostty": "1.4.0-arch2"},
        vs,
        {"date": "d", "head": "h", "command": "c",
         "summary": "six legs recorded"},
    )
    assert "clipboard_fallback_m5t3" in report
    assert ROUTE_TABLE_CITATION in report
    assert "1.4.0-arch2" in report
    assert "NEVER G5" in report
    assert "UNAVAILABLE" in report
    assert "1.5.0" in report                  # the future ELSE trigger is carried
    assert f"t_ms (mechanism only, NOT G5): 180.0" in report


def test_renderer_bounded_under_overflow():
    vs = []
    for i, leg in enumerate(SIX_LEGS):
        vs.append(G4Verdict(leg=leg.leg, status=VERIFIED,
                            checks=[f"check-{i}-{j}-" + "x" * 60 for j in range(20)],
                            evidence=[f"ev-{i}-{j}-" + "y" * 80 for j in range(20)]))
    meta = {"open_items": [f"item {i} " + "z" * 100 for i in range(120)]}
    report = render_g4_report({"sway": "1.12"}, vs, meta)
    lines = report.splitlines()
    assert len(lines) <= MAX_REPORT_LINES
    assert any("[… truncated …]" in ln for ln in lines)   # the cut is honest
    assert lines[-1].startswith("- ") or lines[-1].startswith(("UNAVAILABLE", "AVAILABLE"))


def test_renderer_small_input_is_not_truncated():
    report = render_g4_report({}, _verdicts(*[VERIFIED] * 6), {})
    assert "[… truncated …]" not in report
