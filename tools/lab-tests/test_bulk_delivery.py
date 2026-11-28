"""Unit tests for voice_typing.bulk_delivery — the R.3 bulk-delivery contract surface (PRD §4.2sexies).

Pure-Python: no CUDA, no daemon, no audio. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_bulk_delivery.py -v

Pins, per the PRP: the ShowResult taxonomy (exactly the four PRD words), the
DeliveryTarget Protocol shape (runtime_checkable conformance), the generalized
zero-diff guard rendered_equal (spacing normalization ONLY — case/punct/word
differences are REAL), map_span's Unicode-exact units mapping on the ORIGINAL
string, and the do-not-touch law: no typing-fallback surface, no imports of the
streaming engine / typing backends / daemon, no heavy deps pulled in.
"""
from __future__ import annotations

import re
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import voice_typing.bulk_delivery as bd  # noqa: E402


# ---------------------------------------------------------------------------
# ShowResult taxonomy (R.3 / R.5)
# ---------------------------------------------------------------------------

def test_showresult_has_exactly_four_members():
    assert sorted(bd.ShowResult.__members__) == ["APPLIED", "REFUSED", "UNCHANGED", "UNKNOWN"]


def test_showresult_values_are_the_prd_words():
    assert bd.ShowResult.APPLIED.value == "applied"
    assert bd.ShowResult.UNCHANGED.value == "unchanged"
    assert bd.ShowResult.REFUSED.value == "refused"
    assert bd.ShowResult.UNKNOWN.value == "unknown"
    assert {m.value for m in bd.ShowResult} == {"applied", "unchanged", "refused", "unknown"}


def test_showresult_is_str_valued_for_status_lines():
    # str-Enum: compares equal to the bare word so it serializes into the
    # R.5 delivery_state/delivery_reason surface without mapping tables.
    assert bd.ShowResult.APPLIED == "applied"
    assert isinstance(bd.ShowResult.UNKNOWN, str)
    assert bd.ShowResult("refused") is bd.ShowResult.REFUSED


# ---------------------------------------------------------------------------
# AcquireResult shape
# ---------------------------------------------------------------------------

def test_acquire_result_defaults_and_equality():
    ok = bd.AcquireResult(ok=True, handle=object(), revision=7)
    assert ok.reason == "" and ok.revision == 7
    assert bd.AcquireResult(ok=False, reason="password field") == bd.AcquireResult(
        ok=False, handle=None, revision=0, reason="password field"
    )


def test_acquire_result_is_frozen():
    r = bd.AcquireResult(ok=True)
    with pytest.raises(FrozenInstanceError):
        r.revision = 3  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DeliveryTarget Protocol shape (runtime_checkable)
# ---------------------------------------------------------------------------

class FakeTarget:
    """The minimal conforming adapter (method presence is all isinstance checks)."""

    def acquire(self):
        return bd.AcquireResult(ok=True, handle=object(), revision=7)

    def show(self, session, utterance, seq, expected_revision, span):
        return bd.ShowResult.APPLIED

    def finalize(self, session, utterance, seq, expected_revision, span):
        return bd.ShowResult.UNCHANGED

    def leave(self):
        ...

    def cancel(self):
        return bd.ShowResult.REFUSED


def test_minimal_fake_satisfies_protocol():
    assert isinstance(FakeTarget(), bd.DeliveryTarget)


def test_incomplete_target_fails_protocol_check():
    class NoCancel(FakeTarget):
        cancel = None  # type: ignore[assignment]  # method removed -> not conforming

    assert not isinstance(NoCancel(), bd.DeliveryTarget)


def test_protocol_is_runtime_checkable_and_has_five_methods():
    assert bd.DeliveryTarget.__protocol_attrs__ == {
        "acquire",
        "show",
        "finalize",
        "leave",
        "cancel",
    }


# ---------------------------------------------------------------------------
# rendered_equal — the generalized zero-diff guard (R.1)
# ---------------------------------------------------------------------------

def test_identical_strings_are_equal():
    assert bd.rendered_equal("Hello world", "Hello world") is True


def test_whitespace_run_difference_is_equal():
    assert bd.rendered_equal("Hello  world", "Hello world") is True


def test_leading_trailing_whitespace_difference_is_equal():
    assert bd.rendered_equal("  Hello world ", "Hello world") is True
    assert bd.rendered_equal("Hello world\t", "Hello world") is True


def test_line_break_normalizes_to_space():
    assert bd.rendered_equal("Hello\nworld", "Hello world") is True
    assert bd.rendered_equal("Hello\r\nworld", "Hello  world") is True


def test_nbsp_is_whitespace_here():
    assert bd.rendered_equal("Hello\xa0world", "Hello world") is True


def test_tabs_collapse_like_spaces():
    assert bd.rendered_equal("Hello\t\tworld", "Hello world") is True


def test_empty_vs_whitespace_only_is_equal():
    assert bd.rendered_equal("", " ") is True
    assert bd.rendered_equal("", "  \n\t ") is True


def test_case_difference_is_never_equal():
    assert bd.rendered_equal("Hello world", "hello world") is False


def test_trailing_period_difference_is_never_equal():
    assert bd.rendered_equal("Hi.", "Hi") is False


def test_word_difference_is_never_equal():
    assert bd.rendered_equal("Hello world", "Hello word") is False


def test_unicode_whitespace_runs_with_diacritics_are_equal():
    assert bd.rendered_equal("naïve  café", "naïve café") is True


def test_unicode_emoji_whitespace_runs_are_equal_but_words_are_not():
    assert bd.rendered_equal("a 😀  b", "a 😀 b") is True
    assert bd.rendered_equal("a 😀 b", "a 😀 c") is False


# ---------------------------------------------------------------------------
# map_span — units mapping on the ORIGINAL string (R.3)
# ---------------------------------------------------------------------------

def test_characters_is_identity():
    assert bd.map_span("héllo wörld", 1, 3, bd.TargetUnits.CHARACTERS) == (1, 3)


def test_utf8_bytes_for_two_byte_char():
    assert bd.map_span("héllo", 1, 2, bd.TargetUnits.UTF8_BYTES) == (1, 3)


def test_utf8_bytes_cumulative_over_mixed_widths():
    # a(1) + é(2) + 😀(4) = 7 bytes total
    assert bd.map_span("aé😀", 0, 3, bd.TargetUnits.UTF8_BYTES) == (0, 7)


def test_astral_emoji_counts():
    # 😀 = 4 UTF-8 bytes / 2 UTF-16 units / 1 character
    assert bd.map_span("😀", 0, 1, bd.TargetUnits.UTF8_BYTES) == (0, 4)
    assert bd.map_span("😀", 0, 1, bd.TargetUnits.UTF16_UNITS) == (0, 2)
    assert bd.map_span("😀", 0, 1, bd.TargetUnits.CHARACTERS) == (0, 1)


def test_utf16_surrogate_pairs_in_mixed_span():
    # "a😀b": a=1 unit, 😀=2 units, b=1 unit -> whole span is 4 UTF-16 units
    assert bd.map_span("a😀b", 0, 3, bd.TargetUnits.UTF16_UNITS) == (0, 4)
    # span over "é😀" in "aé😀b": start after a(1), end after é(1)+😀(2) = 4
    assert bd.map_span("aé😀b", 1, 3, bd.TargetUnits.UTF16_UNITS) == (1, 4)


def test_editor_markers_raise_not_implemented():
    with pytest.raises(NotImplementedError):
        bd.map_span("hello", 0, 5, bd.TargetUnits.EDITOR_MARKERS)


@pytest.mark.parametrize(
    "text,start,end",
    [("hello", 3, 2), ("hello", -1, 2), ("hello", 0, 6), ("hello", 7, 8), ("", 0, 1)],
)
def test_invalid_spans_raise_valueerror(text, start, end):
    with pytest.raises(ValueError):
        bd.map_span(text, start, end, bd.TargetUnits.UTF8_BYTES)


# ---------------------------------------------------------------------------
# The do-not-touch law (d2 §3): no typing fallback, no engine imports, pure stdlib
# ---------------------------------------------------------------------------

def test_module_exposes_no_typing_fallback_surface():
    for bad in ("type_text", "type_character", "press_backspace", "make_backend", "StreamingOutput"):
        assert not hasattr(bd, bad), f"bulk_delivery must never expose {bad}"


def test_source_never_imports_engine_modules():
    src = Path(bd.__file__).read_text(encoding="utf-8")
    for dotted in ("voice_typing.streaming", "voice_typing.typing_backends", "voice_typing.daemon"):
        assert dotted not in src, f"bulk_delivery must not reference {dotted}"
    assert not re.search(
        r"import\s+(voice_typing\.)?(streaming|typing_backends|daemon)\b", src
    ), "bulk_delivery must not import the engine modules"


def test_module_purity_no_heavy_imports_bound():
    # The module only binds names from enum/dataclasses/typing — never a module
    # object, and nothing drawn from the heavy engine deps.
    heavy = ("torch", "RealtimeSTT", "ctranslate2", "numpy", "sounddevice")
    public = {k: v for k, v in vars(bd).items() if not k.startswith("__")}
    for name, value in public.items():
        assert not isinstance(value, types.ModuleType), f"bulk_delivery bound module {name!r}"
        mod = getattr(value, "__module__", "") or ""
        assert not mod.startswith(heavy), f"bulk_delivery.{name} comes from {mod}"
