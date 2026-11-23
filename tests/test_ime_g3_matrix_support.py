"""Unit tests for the P1.M4.T5.S2 pure support module (compositor-free).

Covers: the term-probe classifier over the WHOLE legal cross-product (closed
vocabulary, skip-dep None-rules), the expected foot/kitty/ghostty shapes, the
route-table derivation (the M5.T3 decision), the Hyprland ladder statuses,
and the bounded report renderer (cap, banner, determinism).
Pattern follows tests/test_g2_bulk_gate.py: sys.path insert, plain asserts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ime_g3_matrix_support import (  # noqa: E402
    CORRECT_APPLIED_LINE,
    CORRECT_IGNORED_LINE,
    LEGAL_TERM_OUTCOMES,
    MAX_MATRIX_REPORT_LINES,
    ROW_STATUSES,
    TERM_PAYLOADS,
    ASCII_INSERT_LINE,
    UNICODE_INSERT_LINE,
    HyprlandAttempt,
    TermProbeOutcome,
    attempts_from_verdict,
    derive_route_table,
    first_version_line,
    hypr_row_status,
    outcome_from_verdict,
    pacman_versions,
    render_matrix_report,
    term_row_status,
)
import pytest  # noqa: E402

V = "kitty 0.51.0 (live)"
GTK_REF = "plan/008_a47116bb2b79/architecture/g3_gtk_rows.md"


def _outcome(**kw) -> TermProbeOutcome:
    base = dict(
        terminal="kitty",
        version=V,
        activate="activated",
        insert="delivered",
        correct="delete_ignored",
        insert_unicode_roundtrip=True,
        surround="never_sent",
    )
    base.update(kw)
    return TermProbeOutcome(**base)


# --- closed vocabulary + expected shapes --------------------------------------


def test_foot_kitty_expected_shape_is_insert_only():
    o = _outcome()  # delivered + delete_ignored + never_sent
    s = term_row_status(o)
    assert s.startswith("insert-only") and V in s
    assert all(w not in s.split()[0] for w in ("blocked", "verified", "untested"))


def test_full_support_shape_is_verified():
    s = term_row_status(_outcome(correct="delete_applied", surround="sent"))
    assert s.startswith("verified") and V in s


def test_ghostty_expected_shape_is_blocked():
    s = term_row_status(
        _outcome(
            terminal="ghostty",
            version="ghostty 1.4.0 (live)",
            insert="not_delivered",
            correct=None,
            insert_unicode_roundtrip=None,
        )
    )
    assert s.startswith("blocked") and "not_delivered" in s and "1.4.0" in s


def test_not_activated_shape_is_blocked():
    s = term_row_status(
        _outcome(
            activate="not_activated",
            insert="not_delivered",
            correct=None,
            insert_unicode_roundtrip=None,
        )
    )
    assert s.startswith("blocked") and "not_activated" in s


def test_every_legal_combo_maps_into_closed_vocabulary():
    """The classifier is TOTAL over the legal cross-product: every output
    starts with a ROW_STATUSES word and no combo raises."""
    starts = set()
    for activate in LEGAL_TERM_OUTCOMES["activate"]:
        for insert in LEGAL_TERM_OUTCOMES["insert"]:
            for correct in (None, *LEGAL_TERM_OUTCOMES["correct"]):
                for surround in LEGAL_TERM_OUTCOMES["surround"]:
                    for uni in (None, True, False):
                        if insert == "not_delivered" or activate == "not_activated":
                            if correct is not None or uni is not None:
                                continue  # None-rule combos (illegal, next test)
                        if activate == "not_activated" and insert == "delivered":
                            continue  # cross-probe invariant (raises-test)
                        if insert == "delivered" and (correct is None or uni is None):
                            continue  # REQUIRED branches (raises-test)
                        o = _outcome(
                            activate=activate,
                            insert=insert,
                            correct=correct,
                            surround=surround,
                            insert_unicode_roundtrip=uni,
                        )
                        s = term_row_status(o)
                        starts.add(s.split()[0])
    assert starts <= set(ROW_STATUSES)


def test_skip_dep_violations_raise():
    with pytest.raises(ValueError):  # correct probe after a not-delivered insert
        _outcome(
            insert="not_delivered",
            correct="delete_ignored",
            insert_unicode_roundtrip=None,
        )
    with pytest.raises(ValueError):  # unicode probe after a not-delivered insert
        _outcome(insert="not_delivered", correct=None, insert_unicode_roundtrip=True)
    with pytest.raises(ValueError):  # missing REQUIRED correct branch
        _outcome(correct=None)
    with pytest.raises(ValueError):  # not-activated cannot deliver
        _outcome(activate="not_activated")
    with pytest.raises(ValueError):  # unknown terminal
        _outcome(terminal="alacritty")
    with pytest.raises(ValueError):  # branch outside the closed set
        _outcome(insert="kind-of-delivered")


def test_payload_byte_math_and_line_consistency():
    # UTF-8 byte math for before= (ime_host passes it straight to
    # delete_surrounding_text): len(" im".encode()) == 3.
    assert len(TERM_PAYLOADS["correct_delete"].encode("utf-8")) == 3
    assert ASCII_INSERT_LINE == TERM_PAYLOADS["insert_ascii"]
    assert (
        CORRECT_APPLIED_LINE
        == ASCII_INSERT_LINE[: -len(TERM_PAYLOADS["correct_delete"])]
        + TERM_PAYLOADS["correct_replacement"]
    )
    assert (
        CORRECT_IGNORED_LINE == ASCII_INSERT_LINE + TERM_PAYLOADS["correct_replacement"]
    )
    assert UNICODE_INSERT_LINE == ASCII_INSERT_LINE + TERM_PAYLOADS["insert_unicode"]


# --- route table derivation ----------------------------------------------------


def test_ghostty_not_delivered_decides_m5t3_needed():
    rows = [
        _outcome(terminal="foot", version="foot 1.28.0 (live)"),
        _outcome(),
        _outcome(
            terminal="ghostty",
            version="ghostty 1.4.0 (live)",
            insert="not_delivered",
            correct=None,
            insert_unicode_roundtrip=None,
        ),
    ]
    rt = derive_route_table(
        rows, hypr="blocked (nested Hyprland: x @ ladder)", gtk_rows_ref=GTK_REF
    )
    assert rt["clipboard_fallback_m5t3"].startswith("needed")
    assert "1.4.0" in rt["clipboard_fallback_m5t3"]
    assert rt["field_classes"]["ghostty"]["route"] == "clipboard insert-fallback (R.6)"
    assert rt["field_classes"]["foot"]["route"] == "im-v2 insert-only"
    assert (
        rt["field_classes"]["foot"]["corrections"] == "cooperating-editor seam (M5.T1)"
    )
    assert rt["field_classes"]["gtk"] == {"route": "im-v2 full", "evidence": GTK_REF}
    assert rt["hyprland_relay"].startswith("blocked")


def test_ghostty_delivered_decides_m5t3_skip():
    rows = [
        _outcome(
            terminal="ghostty",
            version="ghostty 1.5.0 (live)",
            correct="delete_applied",
            surround="sent",
        )
    ]
    rt = derive_route_table(rows, hypr="insert-only (x)", gtk_rows_ref=GTK_REF)
    assert (
        rt["clipboard_fallback_m5t3"].startswith("skip")
        and "1.5.0" in rt["clipboard_fallback_m5t3"]
    )
    assert rt["field_classes"]["ghostty"]["route"] == "im-v2 full"


def test_kitty_surprise_full_upgrades_route():
    rt = derive_route_table(
        [_outcome(correct="delete_applied", surround="sent")],
        hypr="untested",
        gtk_rows_ref=GTK_REF,
    )
    assert rt["field_classes"]["kitty"]["route"] == "im-v2 full"


def test_route_table_key_is_verbatim_for_m5t3_grep():
    rt = derive_route_table([_outcome()], hypr="untested", gtk_rows_ref=GTK_REF)
    assert "clipboard_fallback_m5t3" in rt


# --- Hyprland ladder statuses ---------------------------------------------------


def test_all_failed_ladder_is_blocked_with_head_and_variants():
    attempts = [
        HyprlandAttempt(
            variant="nested-wayland", err_head="CBackend::create() failed", booted=False
        ),
        HyprlandAttempt(
            variant="legacy-x11",
            err_head="Make sure you're running either on a tty",
            booted=False,
        ),
    ]
    s = hypr_row_status(attempts)
    assert s.startswith("blocked") and "nested-wayland,legacy-x11" in s
    assert "CBackend::create() failed" in s


def test_booted_ladder_reports_rows():
    booted = HyprlandAttempt(
        variant="nested-wayland",
        booted=True,
        rows_measured={
            "insert": "delivered",
            "correct": "delete_applied",
            "surround": "sent",
        },
    )
    assert hypr_row_status([booted]).startswith("verified")
    partial = HyprlandAttempt(
        variant="nested-wayland",
        booted=True,
        rows_measured={
            "insert": "delivered",
            "correct": "delete_ignored",
            "surround": "never_sent",
        },
    )
    assert hypr_row_status([partial]).startswith("insert-only")
    dead_relay = HyprlandAttempt(
        variant="nested-wayland", booted=True, rows_measured={"insert": "not_delivered"}
    )
    assert hypr_row_status([dead_relay]).startswith("blocked")


def test_headless_registry_only_is_blocked_not_silent():
    a = HyprlandAttempt(variant="aq-headless", booted=True, rows_measured=None)
    s = hypr_row_status([a])
    assert s.startswith("blocked") and "no visible output" in s and "aq-headless" in s


def test_empty_ladder_is_untested_infra():
    assert hypr_row_status([]).startswith("untested")


# --- verdict round-trips ---------------------------------------------------------


def test_outcome_from_verdict_roundtrip():
    v = {
        "terminal": "foot",
        "version": "foot 1.28.0 (live)",
        "branches": {
            "activate": "activated",
            "insert": "delivered",
            "correct": "delete_ignored",
            "surround": "never_sent",
            "unicode": True,
        },
        "reasons": {"acquire": "no surrounding text"},
        "evidence": ["x"],
    }
    o = outcome_from_verdict(v)
    assert o.terminal == "foot" and o.correct == "delete_ignored"
    assert o.reasons["acquire"] == "no surrounding text"


def test_attempts_from_verdict_roundtrip():
    v = {
        "attempts": [
            {
                "variant": "legacy-x11",
                "booted": False,
                "err_head": "boom",
                "rows_measured": None,
            }
        ]
    }
    (a,) = attempts_from_verdict(v)
    assert a.variant == "legacy-x11" and not a.booted and a.err_head == "boom"


# --- version helpers --------------------------------------------------------------


def test_pacman_versions_and_first_line():
    v = pacman_versions("foot 1.28.0-2\nkitty 0.51.0-1\nghostty 1.4.0-2\n")
    assert v == {"foot": "1.28.0-2", "kitty": "0.51.0-1", "ghostty": "1.4.0-2"}
    assert first_version_line("\n\nkitty 0.51.0\nnext") == "kitty 0.51.0"
    assert first_version_line("") == ""


# --- bounded renderer ---------------------------------------------------------------


def _stress_rows(n: int) -> list[TermProbeOutcome]:
    names = ("foot", "kitty", "ghostty")
    return [
        _outcome(
            terminal=names[i % 3],
            version=f"term {i} (live)",
            evidence=[f"excerpt line {j} — " + "x" * 60 for j in range(10)],
        )
        for i in range(n)
    ]


def test_renderer_under_cap_with_banner_and_route_key():
    rows = _stress_rows(6)
    attempts = [
        HyprlandAttempt(
            variant="nested-wayland",
            env={"AQ_X": "1", "WY": "s"},
            err_head="e " * 200,
            booted=False,
        ),
        HyprlandAttempt(
            variant="aq-headless",
            env={"AQ_NO_KMS_REQUIREMENT": "1"},
            booted=True,
            rows_measured={"insert": "delivered"},
        ),
    ]
    rt = derive_route_table(
        rows[:3], hypr=hypr_row_status(attempts), gtk_rows_ref=GTK_REF
    )
    meta = {
        "date": "2026-11-23",
        "head": "abc1234",
        "command": "timeout 420 …",
        "gtk_rows_ref": GTK_REF,
        "open_items": [f"item {i}" for i in range(30)],
        "summary": "3 rows measured",
    }
    text = render_matrix_report(
        {"kernel": "7.2.7", "foot": "foot 1.28.0", "pacman": "foot 1.28.0-2"},
        rows,
        attempts,
        rt,
        meta,
    )
    lines = text.split("\n")
    assert len(lines) <= MAX_MATRIX_REPORT_LINES
    assert "G2/lab pass never" in text
    assert "clipboard_fallback_m5t3:" in text
    assert GTK_REF in text  # GTK rows cited, not re-run
    assert "…" not in ("",) and (
        "[… truncated …]" in text or len(lines) < MAX_MATRIX_REPORT_LINES
    )
    assert text == render_matrix_report(
        {"kernel": "7.2.7", "foot": "foot 1.28.0", "pacman": "foot 1.28.0-2"},
        rows,
        attempts,
        rt,
        meta,
    )  # determinism
