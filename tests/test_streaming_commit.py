"""Unit tests for StreamingOutput.commit()/reset_session() (PRD §4.2quater R2 — P1.M2.T6.S2).

Pure-Python: no CUDA, no mic, no real keystrokes — reuses the S1 doubles
(RecordingBackend / FakeFeedback / FakeClock) from tests/test_streaming_core.py.
Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_streaming_commit.py tests/test_streaming_core.py -q

Covers: prefix-extend commit types only the guarded delta + trailing space; a
differing commit rewinds EXACTLY len(tail) and retypes the guarded final; commits
are NOT subject to the >=300 ms full-rewind rate limit; the checkpoint advances so
the next utterance's partials diff against an empty tail and its casing guard sees
the new committed text; append_space=False types no space; frozen commit touches no
backend and absorbs the tail; backend failure inside commit freezes and never
propagates; reset_session() clears everything INCLUDING frozen; and the
context_after_last_boundary() slicing helper.
"""
from __future__ import annotations

from voice_typing.streaming import StreamingOutput, context_after_last_boundary
from voice_typing.typing_backends import TypingBackend


# ---------------------------------------------------------------------------
# Test doubles (copied verbatim from tests/test_streaming_core.py, S1 pattern)
# ---------------------------------------------------------------------------

class RecordingBackend(TypingBackend):
    """Records (method, arg) calls; never spawns a subprocess. Optionally raises.

    press_backspace(n<=0) is a no-op and is NOT recorded (backend contract).
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
            return  # contract no-op — nothing recorded
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
    append_space: bool = True,
    clock: FakeClock | None = None,
) -> tuple[StreamingOutput, RecordingBackend, FakeFeedback]:
    backend = backend if backend is not None else RecordingBackend()
    fb = FakeFeedback()
    kwargs: dict = {"append_space": append_space}
    if clock is not None:
        kwargs["clock"] = clock
    return StreamingOutput(backend, fb, streaming, **kwargs), backend, fb


def _typed(backend: RecordingBackend) -> list[str]:
    """Just the type_text args, in order."""
    return [arg for method, arg in backend.calls if method == "type"]


# ---------------------------------------------------------------------------
# Commit: prefix-extend path (delta + space only)
# ---------------------------------------------------------------------------

def test_commit_extend_types_only_delta_and_space():
    stream, be, fb = _make_stream()
    stream.on_partial("hello wor")          # fresh start: types the whole partial
    stream.commit("hello world")            # final extends the tail -> delta + space
    assert be.calls == [("type", "hello wor"), ("type", "ld"), ("type", " ")]
    assert stream.tail == ""                # checkpoint advanced: nothing pending
    assert stream.committed == "hello world "
    assert fb.partials[-1] == "hello world "


def test_commit_extend_applies_casing_guard_to_the_delta():
    # committed mid-sentence: the delta's first word is lowercased + a spurious
    # single trailing '.' is stripped, exactly like the on_partial extend path.
    stream, be, _fb = _make_stream()
    stream.on_partial("then he said")
    stream.commit("then he said Stop.")     # mid-sentence final waffle
    assert _typed(be) == ["then he said", " stop", " "]
    assert stream.committed == "then he said stop "


def test_commit_empty_delta_types_only_the_space():
    # tail already matches the final exactly: only the trailing space is typed.
    stream, be, _fb = _make_stream()
    stream.on_partial("hello world")
    stream.commit("hello world")
    assert be.calls == [("type", "hello world"), ("type", " ")]
    assert stream.committed == "hello world "


# ---------------------------------------------------------------------------
# Commit: revise / fresh path (exact rewind + retype)
# ---------------------------------------------------------------------------

def test_commit_revise_rewinds_exact_tail_len_and_retypes():
    stream, be, _fb = _make_stream()
    stream.on_partial("hello world")        # tail = "hello world" (11 chars)
    stream.commit("hello there")            # differs -> full rewind, NOT rate-limited
    assert be.calls == [("type", "hello world"), ("bs", 11), ("type", "hello there"), ("type", " ")]
    assert stream.committed == "hello there "


def test_commit_fresh_start_no_backspace_recorded():
    # No tail (commit without any partial): no backspace event at all (n<=0 no-op
    # must not be recorded), just the guarded final + space.
    stream, be, _fb = _make_stream()
    stream.commit("Hello world")
    assert be.calls == [("type", "Hello world"), ("type", " ")]
    assert stream.committed == "Hello world "


def test_commit_not_rate_limited_back_to_back():
    # Two full-rewind commits back-to-back on a clock that NEVER advances: both must
    # go through (if commit consulted/stamped the limiter, the second would freeze).
    stream, be, _fb = _make_stream(clock=FakeClock(0.0))
    stream.on_partial("hello")              # types "hello"
    stream.commit("goodbye")                # rewind #1 (bs 5)
    stream.on_partial("goodbye now")        # fresh start after commit: types whole
    stream.commit("farewell")               # rewind #2 (bs 11) — still allowed
    assert be.calls == [
        ("type", "hello"),
        ("bs", 5), ("type", "goodbye"), ("type", " "),
        ("type", "goodbye now"),
        ("bs", 11), ("type", "farewell"), ("type", " "),
    ]
    # committed ACCUMULATES across commits; the previous commit's trailing space is
    # not doubled by the second join (screen truth: one space between utterances).
    assert stream.committed == "goodbye farewell "


def test_commit_shorter_final_rewinds_and_retypes():
    stream, be, _fb = _make_stream()
    stream.on_partial("hello world how are")
    stream.commit("hello world")            # final SHORTER than the tail
    assert be.calls == [
        ("type", "hello world how are"),
        ("bs", 19), ("type", "hello world"), ("type", " "),
    ]
    assert stream.committed == "hello world "


# ---------------------------------------------------------------------------
# Checkpoint advance: next utterance diffs fresh + guards see the new committed
# ---------------------------------------------------------------------------

def test_commit_advances_checkpoint_next_partial_diffs_against_empty_tail():
    stream, be, _fb = _make_stream()
    stream.on_partial("Hello wor")
    stream.commit("Hello world")            # checkpoint -> "Hello world "
    stream.on_partial("The quick")          # NEXT utterance: fresh tail (no prefix diff)
    assert _typed(be) == ["Hello wor", "ld", " ", "the quick"]  # casing guard saw committed
    assert stream.committed == "Hello world "   # partials never advance the checkpoint
    assert stream.tail == "the quick"
    stream.commit("The quick fox")          # the next commit extends the checkpoint
    assert stream.committed == "Hello world the quick fox "


def test_commit_checkpoint_guard_context_is_screen_truth():
    # The guard stripped the final's spurious mid-sentence '.', so `committed` must
    # NOT end with a terminator: the next utterance's first word stays lowercase.
    stream, be, _fb = _make_stream()
    stream.on_partial("he said")
    stream.commit("he said Stop.")          # '.' stripped by the mid-sentence guard
    assert stream.committed == "he said stop "
    stream.on_partial("Then")
    assert _typed(be) == ["he said", " stop", " ", "then"]   # "Then" landed lowercase


def test_commit_extend_strips_spurious_mid_sentence_period():
    # The delta guard is context-driven: committed is empty but the TAIL "Done" is
    # mid-sentence context, so the final's lone '.' is stripped (same as on_partial).
    stream, be, _fb = _make_stream()
    stream.on_partial("Done")
    stream.commit("Done.")
    assert stream.committed == "Done "      # period eaten -> still mid-sentence
    stream.on_partial("Next")
    assert _typed(be) == ["Done", " ", "next"]       # next partial lands lowercase


# ---------------------------------------------------------------------------
# append_space=False: never a space keystroke, committed has no trailing space
# ---------------------------------------------------------------------------

def test_commit_append_space_false_types_no_space():
    stream, be, _fb = _make_stream(append_space=False)
    stream.on_partial("hello wor")
    stream.commit("hello world")
    assert _typed(be) == ["hello wor", "ld"]
    assert stream.committed == "hello world"
    # next utterance still guards correctly (context joins with a space internally)
    stream.on_partial("The")
    assert _typed(be) == ["hello wor", "ld", "the"]


def test_commit_append_space_false_revise_path():
    stream, be, _fb = _make_stream(append_space=False)
    stream.on_partial("hello world")
    stream.commit("hello there")
    assert be.calls == [("type", "hello world"), ("bs", 11), ("type", "hello there")]
    assert stream.committed == "hello there"


# ---------------------------------------------------------------------------
# Frozen commit: tail absorbed into committed + the append_space separator
# typed (BUG-003 fix) — no revision keystrokes (no rewind, no retype)
# ---------------------------------------------------------------------------

def test_commit_frozen_absorbs_tail_and_types_separator():
    stream, be, fb = _make_stream()
    stream.on_partial("hello wor")          # typed tail
    stream.freeze("test freeze")
    stream.commit("hello world")
    assert be.calls == [("type", "hello wor"), ("type", " ")]  # separator only
    assert stream.committed == "hello wor "           # tail + separator (screen truth)
    assert stream.tail == ""
    assert fb.partials[-1] == "hello wor "
    assert stream.frozen is True                      # freeze lifecycle untouched (T6.S3)


def test_commit_frozen_with_empty_tail():
    # append_space=False keeps this the pure empty-absorb semantics (nothing to
    # type at all: no tail to absorb, no separator to send).
    stream, be, fb = _make_stream(append_space=False)
    stream.freeze("test freeze")
    stream.commit("hello world")
    assert be.calls == []
    assert stream.committed == ""
    assert fb.partials[-1] == ""


# ---------------------------------------------------------------------------
# Backend failure inside commit: freeze, never propagate, checkpoint intact
# ---------------------------------------------------------------------------

def test_commit_type_failure_freezes_and_never_raises():
    stream, be, fb = _make_stream()
    stream.on_partial("hello")              # tail = "hello"
    be._fail_type = True                    # the retype (and space) will fail
    stream.commit("goodbye")                # must NOT raise
    assert stream.frozen is True
    assert stream.committed == ""           # checkpoint NOT advanced
    assert be.calls == [("type", "hello"), ("bs", 5)]  # rewind landed, retype did not
    stream.on_partial("next")               # frozen: mirror-only, no backend calls
    assert be.calls == [("type", "hello"), ("bs", 5)]   # no NEW calls after the freeze
    assert fb.partials[-1] == "hello"       # frozen mirror = the typed tail


def test_commit_backspace_failure_freezes_tail_intact():
    stream, be, _fb = _make_stream()
    stream.on_partial("hello")
    be._fail_backspace = True
    stream.commit("goodbye")                # must NOT raise
    assert stream.frozen is True
    assert stream.tail == "hello"           # tail untouched: rewind never landed
    assert be.calls == [("type", "hello")]


def test_commit_space_type_failure_keeps_checkpoint_at_boundary():
    # tail already equals the final: delta path types nothing, the SPACE fails.
    stream, be, _fb = _make_stream()
    stream.on_partial("hello world")
    be._fail_type = True
    stream.commit("hello world")            # must NOT raise
    assert stream.frozen is True
    assert stream.committed == ""           # checkpoint stays at the pre-commit boundary
    assert be.calls == [("type", "hello world")]


# ---------------------------------------------------------------------------
# Disabled engine: commit is a no-op (Rev 1 rollback hatch)
# ---------------------------------------------------------------------------

def test_commit_disabled_is_a_noop():
    stream, be, fb = _make_stream(streaming=False)
    stream.commit("hello world")
    assert be.calls == []
    assert stream.committed == ""
    assert fb.partials == []


# ---------------------------------------------------------------------------
# reset_session: the ONLY method that clears frozen (session lifecycle)
# ---------------------------------------------------------------------------

def test_reset_session_clears_everything_including_frozen():
    stream, be, fb = _make_stream()
    stream.on_partial("Hello")
    stream.commit("Hello world")
    stream.freeze("test freeze")
    assert stream.committed == "Hello world " and stream.frozen is True
    stream.reset_session()
    assert stream.committed == ""
    assert stream.tail == ""
    assert stream.frozen is False
    stream.on_partial("Next")               # fresh session start: case preserved, types again
    assert _typed(be) == ["Hello", " world", " ", "Next"]
    assert fb.partials[-1] == "Next"


def test_reset_session_clears_post_cancel_suppression():
    stream, be, _fb = _make_stream()
    stream.on_partial("hello")
    stream.reset_after_cancel()             # suppressed
    stream.on_partial("stale")              # mirror-only while suppressed
    assert be.calls == [("type", "hello")]
    stream.reset_session()
    stream.on_partial("fresh")
    assert _typed(be) == ["hello", "fresh"]


def test_reset_boundary_still_does_not_clear_frozen():
    # P1.M2.T6.S3 refined the S2 interim contract: reset_boundary lifts a PER-UTTERANCE
    # freeze (see tests/test_streaming_freeze.py) but must NEVER clear a SESSION-class
    # one — reset_session() is the only path that does. (Deliberate call-site update:
    # the explicit session= tag is what preserves the survival property asserted here.)
    stream, be, _fb = _make_stream()
    stream.freeze("test freeze", session=True)
    stream.reset_boundary()
    assert stream.frozen is True and stream.frozen_session is True


# ---------------------------------------------------------------------------
# context_after_last_boundary: the daemon's prompt-slice helper
# ---------------------------------------------------------------------------

def test_context_no_terminator_is_empty():
    assert context_after_last_boundary("hello world") == ""
    assert context_after_last_boundary("") == ""
    assert context_after_last_boundary("no commas, only commas") == ""


def test_context_terminator_mid_text():
    assert context_after_last_boundary("First one. second part tail") == "second part tail"
    assert context_after_last_boundary("First one! second tail") == "second tail"
    assert context_after_last_boundary("First one? second tail") == "second tail"


def test_context_terminator_at_very_end_is_empty():
    assert context_after_last_boundary("Done.") == ""
    assert context_after_last_boundary("Done. ") == ""


def test_context_last_terminator_wins():
    assert context_after_last_boundary("One. Two? three tail") == "three tail"
    assert context_after_last_boundary("One? Two. Three! ") == ""


def test_context_strips_surrounding_whitespace():
    assert context_after_last_boundary("Hi.   spaced tail  ") == "spaced tail"


def test_context_after_committed_with_trailing_space():
    # The real post-commit shape: committed always ends with the appended space.
    assert context_after_last_boundary("First one. second ") == "second"


# ---------------------------------------------------------------------------
# P1.M1.T3.S1 / BUG-003 — frozen commit types the append_space separator
# (the frozen-absorb path previously sent NO keystrokes at all, so after a
# user-keypress freeze + reset_boundary() the next utterance's first word
# glued onto the absorbed tail: '…the quicknew sentence'.)
# ---------------------------------------------------------------------------


def test_frozen_commit_types_separator_prd_sequence():
    # The bug report's exact Steps-to-Reproduce (PRD h3.2), end to end: a normal
    # commit, then a user-keypress freeze (any non-Backspace key) whose fragment
    # commits absorbed, then reset_boundary() lifts the freeze and the next
    # utterance must land SPACE-SEPARATED. The casing guard lowercases 'New'
    # (committed has no terminal punctuation) -> 'new sentence'.
    stream, be, _fb = _make_stream(append_space=True)
    stream.on_partial("Hello world")
    stream.commit("Hello world")
    stream.reset_boundary()
    stream.on_partial("the quick")
    stream.note_user_keypress()          # freeze the pending fragment
    stream.commit("the quick")          # frozen-ABSORB branch — must still type ' '
    assert stream.committed == "Hello world the quick "   # checkpoint gained the space
    stream.reset_boundary()              # the daemon's post-commit lift
    # reset_boundary()'s own frozen-absorb rstrips the checkpoint (the separator is
    # already ON SCREEN; the next commit re-appends it) — the SCREEN is the contract:
    assert stream.frozen is False
    stream.on_partial("New sentence")
    screen = "".join(t for m, t in be.calls if m == "type")
    assert screen == "Hello world the quick new sentence"
    assert stream.committed == "Hello world the quick"


def test_frozen_commit_append_space_false_stays_space_free():
    # append_space=False: the frozen absorb must not invent a separator either.
    stream, be, _fb = _make_stream(append_space=False)
    stream.on_partial("Hello world")
    stream.commit("Hello world")
    stream.reset_boundary()
    stream.on_partial("the quick")
    stream.note_user_keypress()
    stream.commit("the quick")
    stream.reset_boundary()
    stream.on_partial("New sentence")
    assert ("type", " ") not in be.calls


def test_frozen_commit_space_type_failure_absorbs_nothing():
    # Fail-safe mirror of the non-frozen discipline: if typing the separator
    # fails, the engine freezes SESSION-class and absorbs NOTHING — the
    # checkpoint stays at the pre-commit boundary, no exception.
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    stream.note_user_keypress()
    be._fail_type = True                 # the separator type_text will fail
    stream.commit("hello world")         # must NOT raise
    assert stream.frozen is True
    assert stream.frozen_session is True # _safe_type's promote-only fail-safe
    assert stream.committed == ""        # nothing absorbed
    assert stream.tail == "hello wor"    # tail intact on screen
