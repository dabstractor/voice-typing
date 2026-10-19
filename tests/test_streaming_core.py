"""Unit tests for voice_typing.streaming.StreamingOutput (PRD §4.2quater R1 — P1.M2.T6.S1).

Pure-Python: no CUDA, no mic, no real keystrokes (RecordingBackend records calls
instead of spawning subprocesses — mirrors tests/test_typing_backends.py's
no-real-subprocess guard and test_daemon.py's _FakeBackend shape). Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -q

Covers: delta-only extends (guarded), minimal-diff (longest-common-prefix)
revision — backspace exactly the diverging suffix, guarded suffix retype — the
>=300 ms rewind rate limit, no-trailing-space-while-tentative,
freeze/suppress mirror-only paths, the pending_tail_len()/reset_after_cancel()
seam names daemon.cancel() already calls, and the fail-safe (freeze, never
propagate) backend-failure policy.
"""
from __future__ import annotations

import logging

from voice_typing.streaming import StreamingOutput
from voice_typing.typing_backends import TypingBackend


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class RecordingBackend(TypingBackend):
    """Records (method, arg) calls; never spawns a subprocess. Optionally raises.

    Mirrors the REAL backend contract at the seams the engine relies on:
    press_backspace(n<=0) is a no-op (and is NOT recorded — real backends spawn
    nothing for it, so recorded call lists must not show it either).
    """

    def __init__(self, *, fail_backspace: bool = False, fail_type: bool = False) -> None:
        self.calls: list[tuple[str, object]] = []
        self._fail_backspace = fail_backspace
        self._fail_type = fail_type

    def type_text(self, text: str) -> None:
        if self._fail_type:
            raise RuntimeError("type_text failed (test)")
        self.calls.append(("type", text))

    def press_backspace(self, n: int) -> None:
        if n <= 0:
            return  # contract no-op — nothing recorded, matching wtype/ydotool
        if self._fail_backspace:
            raise RuntimeError("press_backspace failed (test)")
        self.calls.append(("bs", n))


class FakeFeedback:
    """Captures update_partial args in order (the Feedback partial mirror)."""

    def __init__(self) -> None:
        self.partials: list[str] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)


class FakeClock:
    """Deterministic monotonic clock: pops scripted values, repeating the last."""

    def __init__(self, *values: float) -> None:
        self._values = list(values) or [0.0]
        self._i = 0

    def __call__(self) -> float:
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v


def _make_stream(
    backend: RecordingBackend | None = None,
    *,
    streaming: bool = True,
    clock: FakeClock | None = None,
    revision_debounce_s: float = 0.0,
) -> tuple[StreamingOutput, RecordingBackend, FakeFeedback]:
    backend = backend if backend is not None else RecordingBackend()
    fb = FakeFeedback()
    kwargs = {"revision_debounce_s": revision_debounce_s}
    if clock is not None:
        kwargs["clock"] = clock
    return StreamingOutput(backend, fb, streaming, **kwargs), backend, fb


def _typed(backend: RecordingBackend) -> list[str]:
    """Just the type_text args, in order."""
    return [arg for method, arg in backend.calls if method == "type"]


# ---------------------------------------------------------------------------
# Extend path: type ONLY the guarded delta
# ---------------------------------------------------------------------------

def test_extend_types_only_the_delta():
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")   # fresh start: types the whole guarded partial
    stream.on_partial("hello world")  # extends: must type ONLY "ld"
    assert be.calls == [("type", "hello wor"), ("type", "ld")]
    assert stream.tail == "hello world"


def test_extend_never_retypes_the_whole_tail_on_multi_word_growth():
    stream, be, _fb = _make_stream()
    stream.on_partial("the quick")
    stream.on_partial("the quick brown fox")
    stream.on_partial("the quick brown fox jumps")
    assert _typed(be) == ["the quick", " brown fox", " jumps"]
    assert stream.tail == "the quick brown fox jumps"


def test_extend_applies_casing_guard_to_the_delta_not_the_whole_tail():
    # committed mid-sentence + tail mid-utterance: the DELTA's first word is
    # lowercased even though the raw partial capitalizes it.
    stream, be, _fb = _make_stream()
    stream._committed = "Then he said"  # white-box: no commit API until T6.S2
    stream.on_partial("hello")
    stream.on_partial("hello The rest")
    # delta " The rest" -> guard -> " the rest" (mid-sentence, joins the tail)
    assert _typed(be) == ["hello", " the rest"]
    assert stream.tail == "hello the rest"


def test_session_start_partial_preserves_capitalization():
    # committed == "" -> guards preserve case (and periods) on the fresh start
    stream, be, _fb = _make_stream()
    stream.on_partial("Hello world")
    assert _typed(be) == ["Hello world"]
    assert stream.tail == "Hello world"


def test_extend_with_no_new_content_is_a_noop():
    stream, be, fb = _make_stream()
    stream.on_partial("hello wor")
    calls_after_first = list(be.calls)
    stream.on_partial("hello wor")        # identical partial
    stream.on_partial("hello wor   ")     # trailing-space waffle normalizes away
    assert be.calls == calls_after_first
    assert fb.partials == ["hello wor", "hello wor", "hello wor"]  # mirror still updates


def test_extend_period_only_delta_types_nothing():
    # tail "hello" + partial "hello." mid-sentence: the spurious '.' is stripped
    # -> empty guarded delta -> no backend call at all, tail unchanged.
    stream, be, fb = _make_stream()
    stream.on_partial("hello")
    stream.on_partial("hello.")
    assert be.calls == [("type", "hello")]
    assert stream.tail == "hello"
    assert fb.partials[-1] == "hello"


def test_mid_sentence_capitalized_partials_extend_case_insensitively():
    # BUG-008: the casing guard lowercases a fresh mid-sentence fragment's first
    # word ("Hello there" lands as "hello there"), while decoder partials keep
    # the capital — the extend test must compare case-insensitively (comparison
    # ONLY: deltas are still sliced from the originals) or every subsequent
    # partial becomes a rate-limited full rewind+retype (flicker churn).
    stream, be, _fb = _make_stream()
    stream.commit("and then he said")            # seeds mid-sentence committed
    stream.on_partial("Hello there")             # fresh start; guard lowercases
    stream.on_partial("Hello there friend")      # BUG-008: EXTEND, not full rewind
    stream.on_partial("Hello there friend how")  # EXTEND " how"
    assert _typed(be) == ["and then he said", " ", "hello there", " friend", " how"]
    # ZERO backspaces after the first cycle:
    assert not [c for c in be.calls if c[0] == "bs"]
    assert stream.tail == "hello there friend how"


def test_capitalized_partial_equal_length_case_only_diff_is_noop():
    # A partial identical to the tail except casing is a no-op mirror: the
    # case-insensitive prefix match yields an empty delta -> no keystrokes.
    stream, be, fb = _make_stream()
    stream.commit("and then he said")
    stream.on_partial("Hello there")          # types guarded "hello there"
    calls_after_first = list(be.calls)
    stream.on_partial("HELLO THERE")          # case-only, equal length -> empty delta
    stream.on_partial("Hello there")          # identical partial -> no-op too
    assert be.calls == calls_after_first      # no new backend calls at all
    assert fb.partials[-1] == "hello there"   # mirror still updates (TYPED tail)


# ---------------------------------------------------------------------------
# Revise path: minimal-diff rewind — backspace EXACTLY the diverging suffix
# (len(tail) - k for k = the CI longest common prefix; PRD §4.2quater rule 1,
# as amended — a whole-tail rewind for a tail-only edit is a FAILURE)
# ---------------------------------------------------------------------------

def test_revise_backspaces_exactly_the_diverging_suffix():
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5, 1.0))
    stream.on_partial("hello wrld")    # fresh: types "hello wrld" (10 chars)
    stream.on_partial("hello world")   # revise: k=7 ("hello w") -> bs 3, type "orld"
    assert be.calls == [
        ("type", "hello wrld"),
        ("bs", 3),
        ("type", "orld"),
    ]
    assert stream.tail == "hello world"


def test_revise_multi_word_tail_retracts_only_the_changed_word():
    # A last-word revision rewinds ONLY that word's chars — never the whole tail.
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5))
    stream.on_partial("the quick brown fox")
    stream.on_partial("the quick brown dog")   # k=16 -> bs 3, type "dog"
    assert be.calls == [
        ("type", "the quick brown fox"),
        ("bs", 3),
        ("type", "dog"),
    ]
    assert stream.tail == "the quick brown dog"


def test_whole_tail_rewind_only_for_a_genuinely_prefix_free_rewrite():
    # k=0 is the ONLY case that may backspace the whole tail (fresh start /
    # total rewrite — T8a: "a whole-tail rewind for a tail-only edit is a test
    # FAILURE").
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5))
    stream.on_partial("hello world")
    stream.on_partial("goodbye")   # shares nothing with the tail -> k=0
    assert be.calls == [("type", "hello world"), ("bs", 11), ("type", "goodbye")]
    assert stream.tail == "goodbye"


def test_revise_guard_context_is_committed_alone():
    # A revise whose partial shares NO prefix with the tail (k=0) replaces the
    # whole tail, so the casing context is `committed` — NOT committed+tail (the
    # tail is going away).
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5, 1.0))
    stream._committed = "Done."
    stream.on_partial("new")
    # "Fine wording" retracts the tail's first word (genuine non-prefix even
    # case-insensitively — post-BUG-008 a capitalized matching partial extends).
    stream.on_partial("Fine wording")
    # after "Done." a new sentence keeps its capital on revise
    assert _typed(be) == ["new", "Fine wording"]


def test_revise_guard_context_is_the_kept_on_screen_prefix():
    # The corrected suffix goes through the guards with the ON-SCREEN prefix
    # (committed + the surviving tail[:k]) as casing context: mid-sentence it
    # lowercases the suffix's first cased char; a kept prefix that itself ends a
    # sentence preserves the capital.
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5, 1.0))
    stream.on_partial("the quick brown")
    stream.on_partial("the quick Red")    # k=10 -> bs 5, suffix "Red" mid-sentence
    assert be.calls == [
        ("type", "the quick brown"),
        ("bs", 5),
        ("type", "red"),
    ]
    assert stream.tail == "the quick red"

    # The KEPT prefix ends a sentence -> the suffix keeps its capital.
    stream2, be2, _fb2 = _make_stream(clock=FakeClock(0.0, 0.5))
    stream2.on_partial("stop. then")      # typed tail spans a sentence boundary
    stream2.on_partial("stop. Now")       # k=6 -> bs 4, suffix "Now" after '.'
    assert be2.calls == [("type", "stop. then"), ("bs", 4), ("type", "Now")]


def test_revise_indices_counted_on_original_characters():
    # A length-changing casefold ('ß'.casefold() == 'ss') must never desync the
    # indices: k counts ORIGINAL characters, so the backspace deletes exactly
    # the 2 diverging chars ("ße") and the suffix is sliced from the original
    # partial — never from folded text (PRD §4.2quater rule 1, as amended).
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5))
    stream.on_partial("die straße")     # 'ß' is ONE typed char
    stream.on_partial("die strasse")    # k=8 -> bs 2, type "sse"
    assert be.calls == [("type", "die straße"), ("bs", 2), ("type", "sse")]
    assert stream.tail == "die strasse"


def test_revise_to_empty_deletes_everything():
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5))
    stream.on_partial("hello")
    stream.on_partial("")  # decoder retracted everything
    assert be.calls == [("type", "hello"), ("bs", 5)]
    assert stream.tail == ""


# ---------------------------------------------------------------------------
# Revision debounce (smoothness: extend-only while divergence is fresh; ONE
# rewind after it PERSISTS — the commit stays the authoritative correction)
# ---------------------------------------------------------------------------

def test_transient_wobble_reconverges_with_zero_backspaces():
    # The smoothness core: a mid-word retract that grows back past the tail is a
    # pure EXTEND — the divergence window opens and closes with ZERO backspaces.
    stream, be, fb = _make_stream(
        clock=FakeClock(0.0, 0.1, 0.2), revision_debounce_s=2.0
    )
    stream.on_partial("hello twel")     # fresh start
    stream.on_partial("hello")          # retract -> divergent: window opens, NO rewind
    stream.on_partial("hello twelve")   # re-converged -> EXTEND: type only the delta
    assert be.calls == [("type", "hello twel"), ("type", "ve")]
    assert stream.tail == "hello twelve"
    assert fb.partials[-1] == "hello twelve"


def test_persistent_divergence_revises_once_with_the_latest_text():
    stream, be, _fb = _make_stream(
        clock=FakeClock(0.0, 0.5, 2.6), revision_debounce_s=2.0
    )
    stream.on_partial("hello one")        # fresh start (no clock sample)
    stream.on_partial("hello two")        # t=0.0: divergent -> window opens, nothing typed
    stream.on_partial("hello three")      # t=0.5: still inside the window -> nothing
    assert be.calls == [("type", "hello one")]
    stream.on_partial("hello wonderful")  # t=2.6: persisted -> ONE minimal-diff revision
    assert be.calls == [
        ("type", "hello one"),
        ("bs", 3),               # only the diverging suffix ("one"), never the tail
        ("type", "wonderful"),   # the LATEST partial, not the first divergent one
    ]
    assert stream.tail == "hello wonderful"


def test_revision_rearms_the_window():
    # After a debounced revision, a FRESH divergence must persist a full window
    # again — no revision storm even under sustained decoder churn.
    stream, be, _fb = _make_stream(
        clock=FakeClock(0.0, 2.1, 2.2, 4.3), revision_debounce_s=2.0
    )
    stream.on_partial("hello one")       # fresh start
    stream.on_partial("hello two")       # t=0.0: divergent
    stream.on_partial("hello three")     # t=2.1: persisted -> revision lands, re-arms
    stream.on_partial("hello four")      # t=2.2: divergent again 0.1s in -> SUPPRESSED
    assert be.calls == [
        ("type", "hello one"),
        ("bs", 3),
        ("type", "three"),
    ]
    stream.on_partial("hello five")      # t=4.3: 4.3 - 2.2 >= 2.0 -> second revision
    assert be.calls == [
        ("type", "hello one"),
        ("bs", 3),
        ("type", "three"),
        ("bs", 5),
        ("type", "five"),
    ]
    assert stream.tail == "hello five"


def test_fresh_start_is_never_debounced_and_revise_to_empty_waits():
    # An empty tail has nothing to rewind: the first partial types immediately at
    # any debounce. Revise-to-EMPTY is a real revision and waits for the window.
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 2.1), revision_debounce_s=2.0)
    stream.on_partial("hello one")   # fresh start: types immediately
    assert be.calls == [("type", "hello one")]
    stream.on_partial("")            # t=0.0: revise-to-empty opens the window
    assert be.calls == [("type", "hello one")]     # nothing yet
    stream.on_partial("")            # t=2.1: persisted -> rewind lands, empty retype skipped
    assert be.calls == [("type", "hello one"), ("bs", 9)]
    assert stream.tail == ""
    assert stream.tail == ""


# ---------------------------------------------------------------------------
# No trailing space while tentative
# ---------------------------------------------------------------------------

def test_no_trailing_space_ever_typed_while_tentative():
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.4, 0.8))
    for partial in (
        "Hello",
        "Hello world",
        "Hello world ",          # raw trailing space normalizes away
        "Hello wrl",             # revise (decoder retracted)
        "Hello world is here",
    ):
        stream.on_partial(partial)
    typed = _typed(be)
    assert typed, "expected some typing to have happened"
    assert not any(t.endswith(" ") for t in typed), f"trailing space typed: {typed!r}"
    assert not stream.tail.endswith(" ")


# ---------------------------------------------------------------------------
# Freeze / suppress / disabled: mirror-only
# ---------------------------------------------------------------------------

def test_frozen_suppresses_typing_but_keeps_tail_mirror():
    stream, be, fb = _make_stream()
    stream.on_partial("hello wor")
    calls_before = list(be.calls)
    mirror_before = len(fb.partials)
    stream.freeze("test freeze")
    stream.on_partial("hello world")   # would be an extend — must not type
    assert be.calls == calls_before            # no backend calls at all
    assert len(fb.partials) == mirror_before + 1  # mirror still updated...
    assert fb.partials[-1] == stream.tail == "hello wor"  # ...with the TYPED tail


def test_freeze_is_idempotent():
    stream, be, fb = _make_stream()
    stream.freeze("first")
    stream.freeze("second")  # must not double-log nor raise; still frozen
    stream.on_partial("hello")
    assert be.calls == [] and stream.frozen is True


def test_suppressed_after_cancel_mirrors_only_until_boundary():
    stream, be, fb = _make_stream()
    stream.on_partial("hello")          # normal typing works
    stream.reset_after_cancel()         # simulate the daemon's cancel seam
    stream.on_partial("hello again")    # stale partial from the cancelled utterance
    assert be.calls == [("type", "hello")]      # nothing typed post-cancel
    assert fb.partials[-1] == "hello again"     # raw partial mirrored (Rev 1 parity)
    assert stream.tail == ""
    stream.reset_boundary()             # next utterance begins
    stream.on_partial("fresh words")
    assert _typed(be) == ["hello", "fresh words"]
    assert stream.tail == "fresh words"


def test_streaming_disabled_is_mirror_only():
    stream, be, fb = _make_stream(streaming=False)
    stream.on_partial("Hello raw  partial ")
    assert be.calls == []                    # no backend calls, ever
    assert fb.partials == ["Hello raw  partial "]  # RAW text mirrored verbatim (Rev 1)
    assert stream.tail == ""                 # tail never grows when disabled


# ---------------------------------------------------------------------------
# cancel() seam: pending_tail_len / reset_after_cancel names + semantics
# ---------------------------------------------------------------------------

def test_pending_tail_len_tracks_typed_tail():
    stream, be, _fb = _make_stream()
    assert stream.pending_tail_len() == 0
    stream.on_partial("hello wor")
    assert stream.pending_tail_len() == 9
    stream.on_partial("hello world")
    assert stream.pending_tail_len() == 11


def test_reset_after_cancel_zeroes_tail_keeps_committed():
    stream, _be, _fb = _make_stream()
    stream._committed = "Keep. "  # white-box seed: committed is T6.S2's to advance
    stream.on_partial("hello wor")
    assert stream.pending_tail_len() == 9
    stream.reset_after_cancel()
    assert stream.pending_tail_len() == 0
    assert stream.tail == ""
    assert stream.committed == "Keep. "  # committed untouched by cancel


# ---------------------------------------------------------------------------
# Backend failure: never propagate, freeze + WARNING
# ---------------------------------------------------------------------------

def test_backspace_failure_freezes_and_does_not_propagate(caplog):
    stream, be, fb = _make_stream(
        RecordingBackend(fail_backspace=True), clock=FakeClock(0.0, 0.4)
    )
    stream.on_partial("hello wor")     # fresh start succeeds
    # "hello wrl" retracts a mid-word letter ('o' -> 'l') -> NOT a prefix even
    # case-insensitively (BUG-008 fixed the casing route to REVISE) -> true
    # revise, whose press_backspace raises.
    with caplog.at_level(logging.WARNING, logger="voice_typing.streaming"):
        stream.on_partial("hello wrl")
    assert stream.frozen is True              # engine froze itself
    assert stream.tail == "hello wor"         # tail untouched (retype never landed)
    assert _typed(be) == ["hello wor"]        # no partial retype happened
    assert any(
        r.levelno == logging.WARNING and "press_backspace" in r.message
        for r in caplog.records
    ), "expected a WARNING naming press_backspace"


def test_type_failure_on_extend_freezes_and_does_not_propagate(caplog):
    stream, be, fb = _make_stream(
        RecordingBackend(fail_type=True), clock=FakeClock(0.0, 0.4)
    )
    with caplog.at_level(logging.WARNING, logger="voice_typing.streaming"):
        stream.on_partial("hello world")   # fresh start -> type_text raises
    assert stream.frozen is True
    assert stream.tail == ""               # nothing recorded as typed
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    # ...and the engine stays mirror-only afterwards, without raising:
    stream.on_partial("hello world again")
    assert be.calls == [] and fb.partials[-1] == ""


# ---------------------------------------------------------------------------
# Feedback mirror on every event
# ---------------------------------------------------------------------------

def test_mirror_updates_on_every_event_including_suppressed_cycles():
    stream, _be, fb = _make_stream(clock=FakeClock(0.0, 0.1), revision_debounce_s=2.0)
    stream.on_partial("alpha one")      # fresh start: types + mirrors
    n_before = len(fb.partials)
    stream.on_partial("alpha two")      # t=0.0: divergent -> window opens, SUPPRESSED
    stream.on_partial("alpha three")    # t=0.1: still inside the window -> SUPPRESSED
    stream.on_partial("alpha one two")  # extend (tail "alpha one" is a prefix)
    assert len(fb.partials) == n_before + 3   # every cycle mirrors, suppressed included
    assert fb.partials[-3] == "alpha one"     # suppressed cycles keep the tail
    assert fb.partials[-2] == "alpha one"
    assert fb.partials[-1] == "alpha one two"
