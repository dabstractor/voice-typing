"""Word-chunked streaming + the sentence-eater commit guard (2026-11-24).

Two behaviors landed in one change, both driven by the user report:

  1. stream_chunks="word" — live partial typing flushes ONLY at word boundaries
     (\\W-to-\\W chunks): a mid-word delta is held off the screen (partials are
     cumulative, so the next event recomputes the excess — nothing is lost, no
     extra engine state). The default "char" mode types every delta immediately
     (legacy parity, pinned here so the new flag provably changes nothing else).
  2. The SENTENCE-EATER GUARD — a final that is a verbatim repeat of the last
     committed sentence while the tail holds the live utterance (k == 0: the
     revise path would rewind EVERYTHING) is absorbed without keystrokes
     instead of rewinding the user's real sentence and retyping the duplicate.
     A genuinely divergent final (k == 0, NOT a committed repeat) still revises.

Pure CPU, hermetic: fake backend + fake feedback, no daemon, no subprocess.
"""
from __future__ import annotations

import pytest

from voice_typing.streaming import StreamingOutput, _word_flush_point


class FakeBackend:
    def __init__(self) -> None:
        self.typed: list[str] = []
        self.backspaces: list[int] = []
        self.visible = ""

    def type_text(self, text: str) -> None:
        self.typed.append(text)
        self.visible += text

    def press_backspace(self, n: int) -> None:
        self.backspaces.append(n)
        if n:
            self.visible = self.visible[:-n]


class FakeFeedback:
    def __init__(self) -> None:
        self.updates: list[str] = []

    def update_partial(self, text: str) -> None:
        self.updates.append(text)


def make(streaming: bool = True, **kw) -> tuple[StreamingOutput, FakeBackend, FakeFeedback]:
    be, fb = FakeBackend(), FakeFeedback()
    eng = StreamingOutput(be, fb, streaming, **kw)
    return eng, be, fb


# --- the \\W-to-\\W splitter ------------------------------------------------------


def test_word_flush_point_basic() -> None:
    assert _word_flush_point("hello world") == 5       # the space
    assert _word_flush_point("hello") == -1            # word still growing
    assert _word_flush_point("it's done") == 4         # apostrophe is IN the word
    assert _word_flush_point("a. b? c") == 5           # punctuation boundaries too


# --- word mode: hold mid-word, flush on boundary ----------------------------------


def test_word_mode_holds_then_flushes_per_word() -> None:
    eng, be, fb = make(stream_chunks="word", append_space=False)
    eng.on_partial("hello")             # mid-word: nothing types
    assert be.typed == []
    eng.on_partial("hello world")       # boundary -> flush "hello "
    assert be.typed == ["hello "]
    eng.on_partial("hello world it's")  # it's is one word: flush "world "
    assert be.typed == ["hello ", "world "]
    eng.on_partial("hello world it's done")  # flush "it's "
    assert be.typed == ["hello ", "world ", "it's "]
    assert eng.tail == "hello world it's "


def test_word_mode_commit_dumps_remaining_in_one_payload() -> None:
    eng, be, fb = make(stream_chunks="word", append_space=False)
    eng.on_partial("hello world")  # flushes "hello "; "world" stays buffered
    assert be.typed == ["hello "]
    eng.commit("hello world end now")  # commit is BULK: one call, whole delta
    assert be.typed == ["hello ", "world end now"]
    assert eng.tail == ""
    assert "hello world end now" in eng.committed


def test_char_mode_types_every_delta_immediately() -> None:
    eng, be, fb = make(append_space=False)  # default stream_chunks="char"
    eng.on_partial("hello")
    assert be.typed == ["hello"]
    eng.on_partial("hello world")
    assert be.typed == ["hello", " world"]


@pytest.mark.parametrize("revision", ["partial", "final"])
@pytest.mark.parametrize("corrected", ["Next word", "Other words now"])
def test_rewind_preserves_separator_before_live_words(revision, corrected) -> None:
    eng, be, _ = make(stream_chunks="word", revision_debounce_s=0)
    # An unchanged final defers its separator to the first live chunk that follows.
    eng.on_partial("Previous sentence.")
    eng.commit("Previous sentence.")
    eng.reset_boundary()
    assert be.visible == "Previous sentence."

    eng.on_partial("Next wrong words here")
    assert be.visible == "Previous sentence. Next wrong words "

    if revision == "partial":
        eng.on_partial(corrected)
        trailing_space = ""
    else:
        eng.commit(corrected)
        trailing_space = " "

    # Cover both a shared prefix ("Next w") and a full rewrite. In neither case
    # is the leading separator part of the suffix being deleted.
    kept = len("Next w") if corrected.startswith("Next") else 0
    assert be.visible == f"Previous sentence. {corrected}{trailing_space}"
    assert be.backspaces == [len("Next wrong words ") - kept]


# --- the sentence-eater guard -----------------------------------------------------


def _seed_committed(eng: StreamingOutput) -> None:
    eng.commit("alpha beta gamma delta.")  # fresh-start commit types it whole
    eng.reset_boundary()                   # the daemon fires this after every commit


def test_hallinated_repeat_final_is_absorbed_not_rewound() -> None:
    eng, be, fb = make(append_space=False)
    _seed_committed(eng)
    eng.on_partial("epsilon zeta now")     # the user's REAL live sentence (typed)
    assert be.typed == ["alpha beta gamma delta.", "epsilon zeta now"]
    n_before = len(be.typed)
    eng.commit("alpha beta gamma delta.")  # hallucinated repeat, k=0 vs tail
    assert be.backspaces == []             # NEVER rewound the real sentence
    assert len(be.typed) == n_before       # and never typed the duplicate
    assert eng.tail == ""
    assert eng.committed == "alpha beta gamma delta. epsilon zeta now"


def test_short_repeat_still_revises() -> None:
    # <8 normalized chars: below the guard's floor — the normal path applies.
    eng, be, fb = make(append_space=False)
    _seed_committed(eng)
    eng.on_partial("yes please")
    eng.commit("yes.")
    assert be.backspaces == [len("yes please") - len("yes")]  # minimal-diff rewind happened


def test_genuinely_divergent_final_still_revises() -> None:
    eng, be, fb = make(append_space=False)
    _seed_committed(eng)
    eng.on_partial("epsilon zeta now")
    eng.commit("completely different text")  # k=0 but NOT a committed repeat
    assert be.backspaces == [len("epsilon zeta now")]  # full rewind is correct here
    assert be.typed[-1] == "completely different text"
    assert "completely different text" in eng.committed
