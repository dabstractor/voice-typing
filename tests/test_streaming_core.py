"""Unit tests for voice_typing.streaming.StreamingOutput (PRD §4.2quater R1 — P1.M2.T6.S1).

Pure-Python: no CUDA, no mic, no real keystrokes (RecordingBackend records calls
instead of spawning subprocesses — mirrors tests/test_typing_backends.py's
no-real-subprocess guard and test_daemon.py's _FakeBackend shape). Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -q

Covers: delta-only extends (guarded), exact-length rewind + guarded retype on
revise, the >=300 ms full-rewind rate limit, no-trailing-space-while-tentative,
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
) -> tuple[StreamingOutput, RecordingBackend, FakeFeedback]:
    backend = backend if backend is not None else RecordingBackend()
    fb = FakeFeedback()
    kwargs = {} if clock is None else {"clock": clock}
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
# Revise path: exact-length rewind + guarded retype
# ---------------------------------------------------------------------------

def test_revise_rewinds_exact_tail_len_then_retypes():
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5, 1.0))
    stream.on_partial("hello wrld")    # fresh: types "hello wrld" (10 chars)
    stream.on_partial("hello world")   # revise: backspace(10) + retype
    assert be.calls == [
        ("type", "hello wrld"),
        ("bs", 10),
        ("type", "hello world"),
    ]
    assert stream.tail == "hello world"


def test_revise_guard_context_is_committed_alone():
    # A revise replaces the whole tail, so the casing context is `committed` —
    # NOT committed+tail (the tail is going away).
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5, 1.0))
    stream._committed = "Done."
    stream.on_partial("new")
    # "Fine wording" retracts the tail's first word (genuine non-prefix even
    # case-insensitively — post-BUG-008 a capitalized matching partial extends).
    stream.on_partial("Fine wording")
    # after "Done." a new sentence keeps its capital on revise
    assert _typed(be) == ["new", "Fine wording"]


def test_revise_to_empty_deletes_everything():
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.5))
    stream.on_partial("hello")
    stream.on_partial("")  # decoder retracted everything
    assert be.calls == [("type", "hello"), ("bs", 5)]
    assert stream.tail == ""


# ---------------------------------------------------------------------------
# Full-rewind rate limit (>=300 ms, code constant)
# ---------------------------------------------------------------------------

def test_rate_limit_suppresses_second_rewind_within_300ms():
    stream, be, fb = _make_stream(clock=FakeClock(0.0, 0.1, 0.2))
    stream.on_partial("hello one")     # fresh start at t~n/a (no clock use)
    stream.on_partial("hello twelve")  # revise at t=0.0 -> allowed (first rewind)
    stream.on_partial("hello three")   # revise at t=0.1 -> 0.1 < 0.3 -> SUPPRESSED
    assert be.calls == [
        ("type", "hello one"),
        ("bs", 9),
        ("type", "hello twelve"),
    ]
    assert stream.tail == "hello twelve"          # screen keeps the FIRST revise
    assert fb.partials[-1] == "hello twelve"      # mirror keeps the tail too


def test_rate_limit_releases_after_300ms():
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.1, 0.4))
    stream.on_partial("hello one")
    stream.on_partial("hello twelve")  # t=0.0 -> allowed, stamped 0.0
    stream.on_partial("hello three")   # t=0.1 -> suppressed (0.1 < 0.3)
    stream.on_partial("hello four")    # t=0.4 -> 0.4 - 0.0 >= 0.3 -> allowed
    assert be.calls == [
        ("type", "hello one"),
        ("bs", 9),
        ("type", "hello twelve"),
        ("bs", 12),
        ("type", "hello four"),
    ]
    assert stream.tail == "hello four"


def test_fresh_start_is_not_rate_limited():
    # A fresh start deletes nothing -> not a "full rewind" -> never rate-limited.
    # (Revise-to-empty IS a rewind, so it still respects the >=300 ms spacing: t=0.4.)
    stream, be, _fb = _make_stream(clock=FakeClock(0.0, 0.4))
    stream.on_partial("hello one")
    stream.on_partial("hello twelve")  # t=0.0 revise -> allowed (first rewind)
    stream.on_partial("")              # t=0.4 revise-to-empty -> allowed; empty retype
    assert be.calls == [
        ("type", "hello one"),
        ("bs", 9),
        ("type", "hello twelve"),
        ("bs", 12),
    ]                    # no ("type", ""): an empty guarded retype is skipped
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
    stream, _be, fb = _make_stream(clock=FakeClock(0.0, 0.1))
    stream.on_partial("alpha one")      # fresh
    stream.on_partial("alpha two")      # revise at t=0.0 (allowed; not a prefix)
    n_before = len(fb.partials)
    stream.on_partial("alpha three")    # revise at t=0.1 -> rate-limited
    stream.on_partial("alpha two x")    # extend (prefix of tail "alpha two")
    assert len(fb.partials) == n_before + 2   # suppressed cycle ALSO mirrors
    assert fb.partials[-2] == "alpha two"     # suppressed cycle keeps the tail
    assert fb.partials[-1] == "alpha two x"
