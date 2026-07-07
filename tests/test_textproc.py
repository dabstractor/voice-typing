"""Unit tests for voice_typing.textproc.clean (PRD §4.7 — PRD test T2).

Pure-Python: no network, no GPU, no audio. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_textproc.py -v

This is PRD test T2 (§6). It pins the text normalizer + hallucination filter
that every finalized utterance passes through before typing. Whisper's
silence-hallucination ("thank you." on silent audio) is a top-3 project risk
(PRD §8); VAD gating + this filter + PRD test T4 (idle stability) defend
against it together. Written FIRST (TDD) — it is RED until textproc.py lands.
"""
from __future__ import annotations

from voice_typing.config import FilterConfig
from voice_typing.textproc import clean


# ---------------------------------------------------------------------------
# Whitespace normalization (PRD §4.7 step 1)
# ---------------------------------------------------------------------------

def test_collapses_internal_whitespace_runs():
    assert clean("Hello  world", FilterConfig()) == "Hello world"


def test_strips_leading_and_trailing_whitespace():
    assert clean("   Hello world   ", FilterConfig()) == "Hello world"


def test_drops_trailing_newlines_and_collapses():
    assert clean("Hello\n\nworld\n", FilterConfig()) == "Hello world"


def test_tabs_are_whitespace_too():
    assert clean("Hello\tworld", FilterConfig()) == "Hello world"


# ---------------------------------------------------------------------------
# min-length rejection (PRD §4.7 step 2)
# ---------------------------------------------------------------------------

def test_rejects_below_min_chars():
    # default min_chars == 2
    assert clean("A", FilterConfig()) is None


def test_accepts_at_min_chars_boundary():
    assert clean("Hi", FilterConfig()) == "Hi"


def test_rejects_empty_string():
    assert clean("", FilterConfig()) is None


def test_rejects_whitespace_only():
    # collapses to "" -> len 0 < min_chars
    assert clean("    \n  ", FilterConfig()) is None


def test_min_length_uses_cleaned_text_not_raw():
    # raw length 5 but cleaned length 1 -> rejected
    assert clean("  A  ", FilterConfig()) is None


def test_custom_min_chars():
    cfg = FilterConfig(min_chars=5, blocklist=[])
    assert clean("Hi", cfg) is None        # len 2 < 5
    assert clean("Hello", cfg) == "Hello"  # len 5 == 5


# ---------------------------------------------------------------------------
# Blocklist / hallucination filter (PRD §4.7 step 3) — case-insensitive
# ---------------------------------------------------------------------------

def test_rejects_default_blocklist_thank_you():
    assert clean("Thank you.", FilterConfig()) is None


def test_blocklist_is_case_insensitive():
    assert clean("THANK YOU.", FilterConfig()) is None
    assert clean("thank YOU", FilterConfig()) is None


def test_blocklist_matches_with_or_without_trailing_punct():
    # "bye." is in the default blocklist; "Bye"/"bye."/"BYE!" all normalize to "bye"
    assert clean("Bye", FilterConfig()) is None
    assert clean("bye.", FilterConfig()) is None
    assert clean("BYE!", FilterConfig()) is None  # "!" is in the strip class


def test_blocklist_entry_without_punctuation_matches():
    # "you" is in the default blocklist with no trailing punctuation
    assert clean("you", FilterConfig()) is None
    assert clean("You.", FilterConfig()) is None


def test_blocklist_is_exact_not_substring():
    # "you" is blocked, but "yourself" must NOT be dropped (exact normalized match)
    assert clean("yourself", FilterConfig()) == "yourself"


def test_empty_blocklist_never_rejects():
    cfg = FilterConfig(min_chars=2, blocklist=[])
    assert clean("thank you", cfg) == "thank you"


# ---------------------------------------------------------------------------
# Punctuation preserved (PRD §4.7 — return the cleaned text as-is)
# ---------------------------------------------------------------------------

def test_internal_punctuation_preserved():
    # the item's explicit success case: "Hello, world!" kept verbatim
    assert clean("Hello, world!", FilterConfig()) == "Hello, world!"


def test_question_mark_preserved():
    assert clean("Is this real?", FilterConfig()) == "Is this real?"


def test_period_preserved_when_not_blocklisted():
    assert clean("It works.", FilterConfig()) == "It works."


# ---------------------------------------------------------------------------
# Return-value contract
# ---------------------------------------------------------------------------

def test_never_appends_trailing_space():
    # clean() never adds a space; the daemon does (cfg.output.append_space)
    result = clean("Hello", FilterConfig())
    assert result == "Hello"
    assert not result.endswith(" ")


def test_returns_none_for_every_rejection_reason():
    assert clean("A", FilterConfig()) is None              # too short
    assert clean("Thank you.", FilterConfig()) is None     # blocklist
    assert clean("", FilterConfig()) is None               # empty
