"""Tests for the G6 assessment engine (tests/g6_assessment.py) — P1.M7.T1.S1.

Synthetic fixtures in tmp dirs; no CUDA, no desktop, no live service. Every
decision branch is exercised, with the absent/unparsable-input paths (the
honesty rules) as first-class cases:

    timeout 300 uv run pytest tests/test_g6_assessment.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

import g6_assessment as g6  # noqa: E402

ARCH = Path("plan") / "008_a47116bb2b79" / "architecture"


# --------------------------------------------------------------------------
# fixture builders
# --------------------------------------------------------------------------


def _pi_rows(**overrides: dict) -> str:
    rows = [
        {"row": "short-insert-1", "passed": True, "status": "applied"},
        {"row": "first-word-correction", "passed": True, "status": "applied"},
        {"row": "pi-prompt-ghostty", "passed": True, "status": "verified (23 records)"},
    ]
    for name, patch in overrides.items():
        for row in rows:
            if row["row"] == name:
                row.update(patch)
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def _eb_rows(**overrides: dict) -> str:
    rows = [
        {"row": "editor-short-updates", "sub": "", "pass": True, "checks": []},
        {"row": "editor-firstword-20sent", "sub": "", "pass": True, "checks": []},
        {"row": "browser-short-updates", "sub": "", "pass": True, "checks": []},
        {"row": "browser-firstword-20sent", "sub": "", "pass": True, "checks": []},
    ]
    for name, patch in overrides.items():
        for row in rows:
            if row["row"] == name:
                row.update(patch)
    return "\n".join(json.dumps(r) for r in rows) + "\n"


def _g5_report(
    verdict: str = "pass", routes: tuple[str, ...] = ("im-gtk", "pi-ghostty")
) -> str:
    lines = [
        "# G5 TIMING EVIDENCE — per-route timing gate (P1.M6.T4.S1)",
        "## Verdict table",
        "| route | verdict | ins | cor |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r} | **{verdict}** (synthetic fixture) | 120 | 120 |" for r in routes
    ]
    return "\n".join(lines) + "\n"


def _session_entry(date: str, raw_words: int = 1800, net_min: float = 15.0) -> str:
    """A valid entry: usable wpm = raw_words / net_min (default 120 > 110)."""
    correction, recovery, rereading = 2.0, 1.0, 2.0
    duration = net_min + correction + recovery + rereading
    return (
        f"### {date}\n"
        f"duration_min: {duration}\n"
        f"raw_words: {raw_words}\n"
        f"correction_min: {correction}\n"
        f"recovery_min: {recovery}\n"
        f"rereading_min: {rereading}\n"
        f"usable_wpm: {raw_words / net_min:.1f}\n"
        "attributed: operator: dustin\n"
        "notes: synthetic fixture entry\n"
    )


def _sessions_file(*entries: str) -> str:
    header = (
        "# G6 WRITING SESSIONS\n\n"
        "## Recorded sessions\n\n"
        "*(operator-authored entries only — see the template rules)*\n\n"
    )
    return header + "\n".join(entries)


def make_repo(
    tmp_path: Path,
    *,
    pi_text: str | None = None,
    eb_text: str | None = None,
    g2_text: str | None = None,
    g5_text: str | None = None,
    sessions_text: str | None = None,
) -> Path:
    """Lay down a synthetic repo root; pass None to omit that input file."""
    arch = tmp_path / ARCH
    arch.mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    if pi_text is not None:
        (arch / "pi_row_verdicts.jsonl").write_text(pi_text)
    if eb_text is not None:
        (arch / "editor_browser_row_verdicts.jsonl").write_text(eb_text)
    if g2_text is not None:
        (arch / "g2_gate_record.md").write_text(g2_text)
    if g5_text is not None:
        (tmp_path / "tests" / "G5_TIMING_EVIDENCE.md").write_text(g5_text)
    if sessions_text is not None:
        (tmp_path / "tests" / "G6_WRITING_SESSIONS.md").write_text(sessions_text)
    return tmp_path


ALL_MET = dict(
    pi_text=_pi_rows(),
    eb_text=_eb_rows(),
    g2_text="| 1 | append | `t01` | ✅ |\n| 13 | focus change | `t13` | ✅ |\n",
    g5_text=_g5_report(),
    sessions_text=_sessions_file(
        _session_entry("2026-01-01"),
        _session_entry("2026-01-02"),
        _session_entry("2026-01-03"),
    ),
)


def cond(assessment: g6.Assessment, name: str) -> g6.ConditionResult:
    return next(r for r in assessment.results if r.condition == name)


# --------------------------------------------------------------------------
# the decision branches
# --------------------------------------------------------------------------


def test_all_conditions_met_yields_flip(tmp_path):
    a = g6.run_assessment(make_repo(tmp_path, **ALL_MET))
    assert a.flip is True
    assert all(r.verdict == "verified" for r in a.results)
    assert a.decision_line == "G6 DECISION: FLIP"


def test_sessions_file_absent_stays_opt_in(tmp_path):
    root = make_repo(
        tmp_path, **{k: v for k, v in ALL_MET.items() if k != "sessions_text"}
    )
    a = g6.run_assessment(root)
    assert a.flip is False
    d = cond(a, "D-sessions")
    assert d.verdict == "unmet"
    assert "no operator writing-session evidence on record" in d.reason
    assert "STAY OPT-IN" in a.decision_line


def test_sessions_fewer_than_three_stays_opt_in(tmp_path):
    sessions = _sessions_file(
        _session_entry("2026-01-01"), _session_entry("2026-01-02")
    )
    a = g6.run_assessment(make_repo(tmp_path, **{**ALL_MET, "sessions_text": sessions}))
    d = cond(a, "D-sessions")
    assert d.verdict == "unmet"
    assert "need >= 3" in d.reason


def test_session_at_or_below_110_wpm_stays_opt_in(tmp_path):
    # 110.0 does NOT beat 110 (strict >), and neither does 95.
    sessions = _sessions_file(
        _session_entry("2026-01-01"),
        _session_entry("2026-01-02"),
        _session_entry("2026-01-03", raw_words=1650, net_min=15.0),  # exactly 110.0
    )
    a = g6.run_assessment(make_repo(tmp_path, **{**ALL_MET, "sessions_text": sessions}))
    d = cond(a, "D-sessions")
    assert d.verdict == "unmet"
    assert "2026-01-03=110.0wpm" in d.reason

    sessions = _sessions_file(
        _session_entry("2026-01-01"),
        _session_entry("2026-01-02"),
        _session_entry("2026-01-03", raw_words=1425, net_min=15.0),  # 95.0
    )
    a = g6.run_assessment(make_repo(tmp_path, **{**ALL_MET, "sessions_text": sessions}))
    assert "2026-01-03=95.0wpm" in cond(a, "D-sessions").reason


def test_failed_g3_row_stays_opt_in(tmp_path):
    root = make_repo(
        tmp_path,
        **{
            **ALL_MET,
            "pi_text": _pi_rows(
                **{"pi-prompt-ghostty": {"passed": False, "status": "boom"}}
            ),
        },
    )
    a = g6.run_assessment(root)
    assert cond(a, "A-g3-matrix").verdict == "unmet"
    assert "failed rows" in cond(a, "A-g3-matrix").reason
    # the same failed row is an observed (integrity) failure for condition B
    assert cond(a, "B-integrity").verdict == "unmet"
    assert a.flip is False


def test_not_verified_status_denies_a_passing_row(tmp_path):
    # R.2: a passing transport probe never flips a NOT VERIFIED claim — a row
    # with passed:true whose status says "not verified" must NOT count as met.
    root = make_repo(
        tmp_path,
        **{
            **ALL_MET,
            "pi_text": _pi_rows(
                **{"pi-prompt-ghostty": {"status": "not verified (visibility absent)"}}
            ),
        },
    )
    a = g6.run_assessment(root)
    d = cond(a, "A-g3-matrix")
    assert d.verdict == "unmet"
    assert "pi-prompt-ghostty" in d.reason


def test_missing_g3_row_class_stays_opt_in(tmp_path):
    # drop every browser row: the browser insert+correct classes go missing
    eb = (
        "\n".join(
            json.dumps(r)
            for r in json.loads("[" + _eb_rows().replace("}\n", "},").rstrip(",") + "]")
            if not str(r["row"]).startswith("browser")
        )
        + "\n"
    )
    a = g6.run_assessment(make_repo(tmp_path, **{**ALL_MET, "eb_text": eb}))
    d = cond(a, "A-g3-matrix")
    assert d.verdict == "unmet"
    assert "browser:insert" in d.reason and "browser:correct" in d.reason


def test_g5_report_absent_is_not_run_and_stays_opt_in(tmp_path):
    root = make_repo(tmp_path, **{k: v for k, v in ALL_MET.items() if k != "g5_text"})
    a = g6.run_assessment(root)
    d = cond(a, "C-g5-timing")
    assert d.verdict == "not-run"
    assert "report absent" in d.reason
    assert a.flip is False  # absent evidence never passes by default


def test_g5_unparsable_is_not_run(tmp_path):
    root = make_repo(
        tmp_path, **{**ALL_MET, "g5_text": "# G5 report\n\nlorem ipsum, no table\n"}
    )
    a = g6.run_assessment(root)
    d = cond(a, "C-g5-timing")
    assert d.verdict == "not-run"
    assert "cannot parse" in d.reason


def test_g5_failed_route_stays_opt_in(tmp_path):
    root = make_repo(
        tmp_path,
        **{**ALL_MET, "g5_text": _g5_report("fail", routes=("im-gtk", "pi-ghostty"))},
    )
    a = g6.run_assessment(root)
    d = cond(a, "C-g5-timing")
    assert d.verdict == "unmet"
    assert "im-gtk" in d.reason and "pi-ghostty" in d.reason

    root = make_repo(
        tmp_path,
        **{
            **ALL_MET,
            "g5_text": _g5_report("pass") + _g5_report("blocked", routes=("x",)),
        },
    )
    assert cond(g6.run_assessment(root), "C-g5-timing").verdict == "unmet"


def test_g2_record_missing_or_failing_stays_opt_in(tmp_path):
    root = make_repo(tmp_path, **{k: v for k, v in ALL_MET.items() if k != "g2_text"})
    a = g6.run_assessment(root)
    d = cond(a, "B-integrity")
    assert d.verdict == "unmet"
    assert "cannot read G2 gate record" in d.reason

    root = make_repo(
        tmp_path, **{**ALL_MET, "g2_text": "| 7 | repeated cancel | `t07` | ❌ |\n"}
    )
    d = cond(g6.run_assessment(root), "B-integrity")
    assert d.verdict == "unmet"
    assert "failing trace" in d.reason


def test_failed_checks_row_is_an_integrity_failure(tmp_path):
    eb = _eb_rows(**{"editor-short-updates": {"checks": ["caret drifted"]}})
    a = g6.run_assessment(make_repo(tmp_path, **{**ALL_MET, "eb_text": eb}))
    assert cond(a, "B-integrity").verdict == "unmet"
    assert cond(a, "A-g3-matrix").verdict == "unmet"


def test_transport_probe_evidence_never_counts(tmp_path):
    # R.2: probe/lab mechanism evidence is not G3/G5/G6 evidence. A sessions
    # file of probe notes has zero valid entries (D unmet); a G5 report of
    # probe prose with no verdict table is unparsable (C not-run).
    sessions = (
        "# G6 WRITING SESSIONS\n\n## Recorded sessions\n\n"
        "- probe run via tools/paste-lab: 140 wpm, unattributed\n"
        "- im-lab transport probe: fast\n"
    )
    a = g6.run_assessment(
        make_repo(
            tmp_path,
            **{
                **ALL_MET,
                "sessions_text": sessions,
                "g5_text": (
                    "# G5 TIMING EVIDENCE\n\nTransport probes all passed (paste-lab, im-lab).\n"
                ),
            },
        )
    )
    assert cond(a, "D-sessions").verdict == "unmet"
    d_reason = cond(a, "D-sessions").reason
    # zero parseable entries — the probe notes never counted toward the gate
    assert "0 valid" in d_reason or "no operator attribution" in d_reason
    assert cond(a, "C-g5-timing").verdict == "not-run"
    assert a.flip is False


def test_session_entry_without_attribution_is_invalid(tmp_path):
    entry = _session_entry("2026-01-01").replace("attributed: operator: dustin\n", "")
    valid, invalid = g6.parse_writing_sessions(
        _sessions_file(entry) + _session_entry("2026-01-02")
    )
    assert len(valid) == 1 and len(invalid) == 1
    assert "attribution" in invalid[0]


def test_entry_wpm_mismatch_is_invalid(tmp_path):
    entry = _session_entry("2026-01-01").replace(
        "usable_wpm: 120.0", "usable_wpm: 130.0"
    )
    valid, invalid = g6.parse_writing_sessions(_sessions_file(entry))
    assert not valid and "!= computed" in invalid[0]


def test_decision_line_format(tmp_path):
    a = g6.run_assessment(make_repo(tmp_path / "flip", **ALL_MET))
    assert a.decision_line == "G6 DECISION: FLIP"
    b = make_repo(
        tmp_path / "stay", **{k: v for k, v in ALL_MET.items() if k != "sessions_text"}
    )
    assert (
        g6.run_assessment(b).decision_line
        == "G6 DECISION: STAY OPT-IN (unmet: D-sessions)"
    )


def test_exit_zero_both_ways():
    # G8: the decision is data, not an error. The REAL committed artifacts run
    # via subprocess; exit 0 and a decision line — whichever way the evidence
    # currently points.
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "g6_assessment.py")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert "G6 DECISION: " in proc.stdout
    assert "STAY OPT-IN" in proc.stdout or "FLIP" in proc.stdout
