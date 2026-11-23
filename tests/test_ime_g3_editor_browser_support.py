"""tests/test_ime_g3_editor_browser_support.py — collected, compositor-free
unit tests for tests/ime_g3_editor_browser_support.py (P1.M5.T2.S2 Task 1).

Pins: parse_push round-trips the fixture's JSON incl. astral chars (🫡 → 2
UTF-16 units; fnv1a32 stable over the TextEncoder byte stream), the DOM
event-count law (clean insert = 1 full-delta ring entry; a 2-event correction,
a 1-event-with-intermediate-frame correction, and a zero-diff that emitted an
event all FAIL), the isolated argv builders, the closed-vocabulary class
verdict mapper (every branch), and the 150-line report cap. No env gate, no
I/O outside pytest, stdlib only. Run:

    timeout 120 .venv/bin/python -m pytest tests/test_ime_g3_editor_browser_support.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ime_g3_editor_browser_support import (  # noqa: E402
    MAX_REPORT_LINES,
    VERIFIED_SUFFIX,
    BrowserState,
    class_verdict,
    chromium_argv,
    firefox_argv,
    fnv1a32,
    input_event_law,
    parse_push,
    parse_title,
    render_class_report,
    utf16_len,
)

# --- helpers -------------------------------------------------------------------


def _state(text="", *, n=0, k=0, sel=None, ring=(), frames=(), f=0, ro=False):
    return BrowserState(
        n=n,
        k=k,
        sel_start=(sel or [0, 0])[0],
        sel_end=(sel or [0, 0])[1],
        length=utf16_len(text),
        text=text,
        ring=tuple(tuple(e) for e in ring),
        frames=tuple(frames),
        f=f,
        readonly=ro,
    )


def _push_body(s: BrowserState) -> bytes:
    return json.dumps(
        {
            "n": s.n,
            "k": s.k,
            "sel": [s.sel_start, s.sel_end],
            "len": s.length,
            "text": s.text,
            "ring": [list(e) for e in s.ring],
            "frames": list(s.frames),
            "f": s.f,
            "ro": s.readonly,
        },
        ensure_ascii=False,
    ).encode("utf-8")


# --- fnv1a32: the fixture JS twin ------------------------------------------------


def test_fnv1a32_known_vectors():
    # FNV-1a 32-bit spec vectors over the same UTF-8 byte strings.
    assert fnv1a32("") == "811c9dc5"
    assert fnv1a32("a") == "e40c292c"
    assert fnv1a32("foobar") == "bf9cf968"


def test_fnv1a32_astral_matches_utf8_byte_stream():
    # 🫡 (U+1FAE1) encodes to 4 UTF-8 bytes; FNV runs over BYTES (TextEncoder
    # twin), while utf16_len counts the SURROGATE PAIR — both pinned here.
    assert utf16_len("🫡") == 2
    assert len(fnv1a32("🫡x")) == 8


# --- parse_push round-trip + validation -------------------------------------------


def test_parse_push_roundtrip_astral():
    s = _state(
        "a🫡b",
        n=3,
        k=0,
        sel=[4, 4],
        ring=[("11111111", "22222222", 2, 4)],
        frames=["aaaaaaaa"],
        f=9,
    )
    raw = _push_body(s)
    got = parse_push(raw)
    assert got.text == "a🫡b"
    assert got.length == 4  # 3 chars → 4 UTF-16 units (astral = 2)
    assert got.sel_start == got.sel_end == 4
    assert got.n == 3 and got.k == 0 and got.f == 9
    assert got.ring == (("11111111", "22222222", 2, 4),)
    assert got.frames == ("aaaaaaaa",)
    assert got.readonly is False


def test_parse_push_accepts_bytes_and_str():
    s = _state("hi", n=1)
    assert parse_push(_push_body(s)).text == "hi"
    assert parse_push(_push_body(s).decode()).text == "hi"


@pytest.mark.parametrize(
    "mut",
    [
        lambda d: d.pop("n"),
        lambda d: d.pop("sel"),
        lambda d: d.update({"ring": [[1, 2, 3, 4]]}),  # hashes not 8-hex strings
        lambda d: d.update({"ring": [["11111111", "22222222", "x", 4]]}),
        lambda d: d.update({"frames": ["abc"]}),  # not 8 chars
        lambda d: d.update({"n": True}),  # bool is not an int here
        lambda d: d.update({"sel": [1]}),
        lambda d: d.update({"text": 5}),
        lambda d: d.update({"f": "9"}),
    ],
)
def test_parse_push_rejects_malformed(mut):
    body = json.loads(_push_body(_state("x", n=1)))
    mut(body)
    with pytest.raises(ValueError):
        parse_push(json.dumps(body))


def test_parse_push_rejects_non_object():
    with pytest.raises(ValueError):
        parse_push(b"[1,2]")


# --- parse_title (the fallback channel) -------------------------------------------


def test_parse_title_roundtrip():
    t = 'vtg3-browser|{"n":2,"k":0,"f":31,"v":"abcd1234","s":3,"ro":false}'
    obj = parse_title(t)
    assert obj is not None and obj["n"] == 2 and obj["v"] == "abcd1234"
    assert obj["base"] == "vtg3-browser"
    assert parse_title('vtg3-browser-ro|{"n":0}')["base"] == "vtg3-browser-ro"


def test_parse_title_garbage():
    assert parse_title(None) is None
    assert parse_title("") is None
    assert parse_title("some other window title") is None
    assert parse_title("vtg3-browser|not json") is None
    assert parse_title("wrong-prefix|{}") is None


# --- input_event_law: the DOM event-count law -------------------------------------


def test_law_clean_insert_passes():
    before = _state("abc", n=3, f=10, frames=["%s" % fnv1a32("abc")] * 5, sel=[3, 3])
    after_text = "abcX"
    frames = [fnv1a32("abc")] * 6 + [fnv1a32(after_text)] * 4
    after = _state(
        after_text,
        n=4,
        f=20,
        frames=frames,
        ring=[(fnv1a32("abc"), fnv1a32(after_text), 3, 4)],
        sel=[4, 4],
    )
    law = input_event_law(before, after, expect="change", exp_text=after_text)
    assert law["ok"], law
    assert law["dn"] == 1 and law["transitions"] == 1 and law["painted_final"]


def test_law_two_event_correction_fails():
    before = _state("Thier x", n=1, f=5, frames=[fnv1a32("Thier x")] * 5)
    after = _state(
        "Their x",
        n=3,  # TWO input events for one edit — R.1 violation
        f=12,
        frames=[fnv1a32("Thier x")] * 2
        + [fnv1a32("Thei x")] * 3
        + [fnv1a32("Their x")] * 2,
        ring=[
            (fnv1a32("Thier x"), fnv1a32("Thei x"), 7, 6),
            (fnv1a32("Thei x"), fnv1a32("Their x"), 6, 7),
        ],
    )
    law = input_event_law(before, after, expect="change", exp_text="Their x")
    assert not law["ok"] and law["dn"] == 2


def test_law_one_event_with_intermediate_frame_fails():
    before = _state("Thier x", n=1, f=5, frames=[fnv1a32("Thier x")] * 5)
    after_text = "Their x"
    # ONE event, but a painted frame showed a transient intermediate value.
    frames = [fnv1a32("Thier x")] * 2 + [fnv1a32("zzz")] + [fnv1a32(after_text)] * 3
    after = _state(
        after_text,
        n=2,
        f=11,
        frames=frames,
        ring=[(fnv1a32("Thier x"), fnv1a32(after_text), 7, 7)],
    )
    law = input_event_law(before, after, expect="change", exp_text=after_text)
    assert not law["ok"] and law["transient"] == [fnv1a32("zzz")]


def test_law_ring_entry_not_full_delta_fails():
    before = _state("abc", n=1, f=5, frames=[fnv1a32("abc")] * 5)
    after_text = "abcdef"
    after = _state(
        after_text,
        n=2,
        f=8,
        frames=[fnv1a32("abc")] * 2 + [fnv1a32(after_text)] * 1,
        ring=[(fnv1a32("abc"), fnv1a32("abcd"), 3, 4)],  # partial delta
    )
    law = input_event_law(before, after, expect="change", exp_text=after_text)
    assert not law["ok"] and not law["ring_full"]


def test_law_zero_diff_that_emitted_event_fails():
    before = _state("same", n=5, f=8, frames=[fnv1a32("same")] * 8)
    after = _state("same", n=6, f=10, frames=[fnv1a32("same")] * 10)
    law = input_event_law(before, after, expect="noop", exp_text="same")
    assert not law["ok"] and law["dn"] == 1


def test_law_clean_noop_passes():
    before = _state("same", n=5, f=8, frames=[fnv1a32("same")] * 8)
    after = _state("same", n=5, f=12, frames=[fnv1a32("same")] * 12)
    law = input_event_law(before, after, expect="noop", exp_text="same")
    assert law["ok"] and law["dn"] == 0 and law["transitions"] == 0


def test_law_underflow_fails():
    before = _state("abc", n=1, f=0, frames=())
    after = _state("abcX", n=2, f=80, frames=[fnv1a32("abcX")] * 64)  # window 80 > 64
    law = input_event_law(before, after, expect="change", exp_text="abcX")
    assert not law["ok"] and law["underflow"]


def test_law_wrong_text_fails():
    before = _state("abc", n=1, f=5, frames=[fnv1a32("abc")] * 5)
    after = _state(
        "abd",
        n=2,
        f=7,
        frames=[fnv1a32("abc")] * 2 + [fnv1a32("abd")],
        ring=[(fnv1a32("abc"), fnv1a32("abd"), 3, 3)],
    )
    law = input_event_law(before, after, expect="change", exp_text="abd")
    assert law["ok"]
    law2 = input_event_law(before, after, expect="change", exp_text="abe")
    assert not law2["ok"] and not law2["text_ok"]


def test_law_rejects_bad_expect():
    with pytest.raises(ValueError):
        input_event_law(_state(), _state(), expect="insert", exp_text="")


# --- argv builders ----------------------------------------------------------------


def test_chromium_argv_contract():
    argv = chromium_argv("/tmp/prof", "file:///x.html?push=http://127.0.0.1:1/push")
    assert argv[0] == "/usr/bin/chromium"
    assert "--ozone-platform=wayland" in argv
    assert "--enable-wayland-ime" in argv
    assert "--wayland-text-input-version=3" in argv
    assert "--user-data-dir=/tmp/prof" in argv  # temp-root profile, never real
    assert "--password-store=basic" in argv
    assert "--disable-gpu" in argv
    assert argv[-1] == "--app=file:///x.html?push=http://127.0.0.1:1/push"


def test_chromium_argv_extra_appended():
    argv = chromium_argv("/tmp/p", "u", extra=("--no-sandbox",))
    assert argv[-2:] == ["--app=u", "--no-sandbox"]


def test_firefox_argv_contract():
    argv = firefox_argv("/tmp/fprof", "file:///x.html")
    assert argv[0] == "/usr/bin/firefox"
    assert "--profile" in argv and "/tmp/fprof" in argv
    assert argv[-1] == "file:///x.html"


# --- class_verdict: every branch of the closed vocabulary -------------------------


def test_class_verdict_verified_needs_insert_and_correction():
    rows = [
        {"row": "b1", "ok": True, "insert_ok": True, "correction_ok": None},
        {"row": "b2", "ok": True, "insert_ok": True, "correction_ok": True},
    ]
    assert class_verdict(rows) == VERIFIED_SUFFIX


def test_class_verdict_insert_only_with_reason():
    rows = [
        {"row": "b1", "ok": True, "insert_ok": True, "correction_ok": None},
        {
            "row": "b2",
            "ok": True,
            "insert_ok": True,
            "correction_ok": False,
            "reason": "correction refused: surrounding_text absent at chromium 158.0.8127.36",
        },
    ]
    v = class_verdict(rows)
    assert v.startswith("insert-only (") and "surrounding_text absent" in v


def test_class_verdict_insert_only_no_reason():
    rows = [{"row": "b1", "ok": True, "insert_ok": True, "correction_ok": False}]
    assert class_verdict(rows) == "insert-only"


def test_class_verdict_blocked_failed_row():
    rows = [
        {"row": "b1", "ok": True, "insert_ok": True},
        {"row": "b2", "ok": False, "checks": ["correction-byte-exact"]},
    ]
    assert class_verdict(rows) == "blocked (FAILED: correction-byte-exact)"


def test_class_verdict_blocked_capability_reason():
    # a MEASURED capability gap (never activated) with nothing passing → blocked
    rows = [
        {
            "row": "b1",
            "ok": None,
            "blocked_reason": "chromium 158 never activated text-input",
        }
    ]
    assert class_verdict(rows) == "blocked (chromium 158 never activated text-input)"
    # passing insert+correction rows decide even alongside a skipped row
    # (the skipped row's reason stays visible in the report rows)
    rows2 = [
        {"row": "b1", "ok": None, "reason": "text-input never activated"},
        {"row": "b2", "ok": True, "insert_ok": True, "correction_ok": True},
    ]
    assert class_verdict(rows2) == VERIFIED_SUFFIX
    rows3 = [{"row": "b1", "ok": True, "insert_ok": True, "correction_ok": True}]
    assert class_verdict(rows3) == VERIFIED_SUFFIX


def test_class_verdict_untested_not_attempted_and_empty():
    assert (
        class_verdict([{"row": "ff", "ok": None, "attempted": False}])
        == "untested (not attempted)"
    )
    assert class_verdict([]) == "untested (infra: no rows)"


def test_class_verdict_no_insert_exercised():
    rows = [{"row": "b3", "ok": True, "insert_ok": None, "correction_ok": None}]
    assert class_verdict(rows) == "untested (infra: no insert exercised)"


def test_class_verdict_skipped_row_never_erases_passing_inserts():
    # a skipped zero-diff row (B3 unmeasurable) does not downgrade the class:
    # the inserts that DID pass keep insert-only
    rows = [
        {"row": "b1", "ok": True, "insert_ok": True, "correction_ok": None},
        {
            "row": "b2",
            "ok": True,
            "insert_ok": True,
            "correction_ok": False,
            "reason": "caret guard refused recheck (snapshot lags committed value)",
        },
        {"row": "b3", "ok": None, "reason": "caret guard refused repeats"},
    ]
    v = class_verdict(rows)
    assert v.startswith("insert-only (") and "snapshot lags committed value" in v


def test_class_verdict_skip_only_when_nothing_passed():
    rows = [
        {"row": "b3", "ok": None, "reason": "caret guard refused repeats"},
        {"row": "b5", "ok": None, "reason": "no writable window"},
    ]
    assert class_verdict(rows) == "untested (infra: caret guard refused repeats)"


def test_class_verdict_failure_beats_skip():
    rows = [
        {"row": "b1", "ok": None, "reason": "never activated"},
        {"row": "b2", "ok": False, "checks": ["boom"]},
    ]
    assert class_verdict(rows) == "blocked (FAILED: boom)"


# --- render_class_report: bounded, titled, extra versions -------------------------


def test_render_class_report_bounded_and_titled():
    versions = {
        "kernel": "k",
        "sway": "s",
        "gtk": "4.24.1",
        "pygobject": "3.58.1",
        "chromium": "Chromium 158.0.8127.36 Arch Linux",
        "chromium_flags": "--enable-wayland-ime --wayland-text-input-version=3",
    }
    rows = [
        {
            "id": f"row-{i}",
            "title": "t",
            "passed": True,
            "status": "insert-only",
            "evidence": [f"ev{j}" for j in range(20)],
        }
        for i in range(200)
    ]
    meta = {
        "date": "d",
        "head": "h",
        "command": "c",
        "summary": "s",
        "open_items": ["oi1"],
    }
    text = render_class_report(versions, rows, meta, title="T")
    lines = text.split("\n")
    assert lines[0] == "T"
    assert len(lines) <= MAX_REPORT_LINES
    assert "- chromium: Chromium 158.0.8127.36 Arch Linux" in lines
    assert (
        "- chromium_flags: --enable-wayland-ime --wayland-text-input-version=3" in lines
    )
    assert "oi1" in text  # open items survive the cap
    # no duplicate kernel line (the extra-version dedup)
    assert sum(1 for ln in lines if ln == "- kernel: k") == 1
