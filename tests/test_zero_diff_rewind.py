"""Characterization tests for the 2026-11-19 user-reported rewind incidents.

User report (paraphrased from the 2026-11-19 session — see
plan/drafts/REV4-HANDOFF-user-session.md):
  (a) Mid-monologue, the tool decides to "correct" the FIRST WORDS of the
      utterance — often re-typing the exact same visible words — and rewinds
      the ENTIRE tail: with a 10-20 sentence tail that is 20-30 seconds of
      backspace+retype at ~10 ms/char, during which ANY keypress HALTs and
      leaves a broken text field.
  (b) After finishing talking, the tool sometimes starts deleting everything,
      or leaves jumbled words / stray chars / missing spaces.

These tests pin the MECHANISMS in voice_typing/streaming.py:

  T1  exact-equal commit guard EXISTS — an identical final emits ZERO
      keystrokes (so the incidents are NOT plain equality misses).
  T2  k=0 divergence on a long tail orders a FULL-TAIL rewind + full retype
      by design — the 20-30 s incident is this rule times a monologue-length
      tail times 10 ms/char.
  T3  a silently DROPPED insertion (compositor drop, exit 0 — per the Rev 4
      draft's transport evidence) desyncs believed-tail from screen truth;
      the next rewind eats text the engine had already committed — the
      "jumbled/broken words" class. Paste-delivery (Rev 4) exists to starve
      this: fewer events, no per-char drops.

Run: .venv/bin/pytest tests/test_zero_diff_rewind.py -q   (no CUDA, no daemon)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_streaming_core import FakeFeedback, _make_stream  # noqa: E402
from voice_typing.streaming import StreamingOutput  # noqa: E402


LONG_TAIL = (
    "the quick brown fox jumps over the lazy dog and keeps running through "
    "twenty sentences of monologue because the speaker never paused longer "
    "than the endpointer gate so it all became one single utterance tail "
    "that the correction machinery now has to consider as one unit"
)


def test_T1_exact_equal_commit_emits_zero_keystrokes():
    """An identical final is already a no-op (guard exists)."""
    s, be, _ = _make_stream()
    s.on_partial(LONG_TAIL)
    be.calls.clear()
    s.commit(LONG_TAIL)
    assert be.calls == [], f"expected zero keystrokes, got {be.calls}"


def test_T2_k0_divergence_on_long_tail_orders_full_tail_rewind():
    """Any first-byte divergence (k=0) rewinds + retypes the WHOLE tail.

    At ~10 ms per injected event this is len(tail)*2 events — the reported
    20-30 second full-rewrite of an eye-identical monologue when the first
    word differs by one byte (or believed-vs-screen desync shifts k to 0).
    """
    s, be, _ = _make_stream(revision_debounce_s=0.0)
    s.on_partial(LONG_TAIL)
    be.calls.clear()
    # First word differs at byte 0 ("the" -> "their"): common prefix k=0.
    s.commit("their " + LONG_TAIL[len("the ") :])
    bses = [n for op, n in be.calls if op == "bs"]
    types = [t for op, t in be.calls if op == "type"]
    assert bses and bses[0] >= 0.9 * len(LONG_TAIL), (
        f"expected a near-full-tail rewind, got {be.calls}"
    )
    assert any(len(t) > 100 for t in types), (
        f"expected a near-full retype, got {be.calls}"
    )


class _ScreenModel:
    """Tracks what ACTUALLY landed: a type_text that drops silently (compositor
    loss, exit 0) records nothing, like wtype/ydotool dropping a burst."""

    def __init__(self, drop_first_type: bool = True) -> None:
        self.text = ""
        self.drop_first_type = drop_first_type
        self.dropped = 0

    def type(self, s: str) -> None:
        if self.drop_first_type and self.dropped == 0:
            self.dropped += 1
            return  # SILENT drop: engine believes it landed
        self.text += s

    def backspace(self, n: int) -> None:
        self.text = self.text[: max(0, len(self.text) - n)]


def test_T3_dropped_insertion_desync_makes_next_rewind_eat_committed_text():
    """One silent insertion drop permanently desyncs the engine's believed
    screen from reality; the next minimal-diff rewind deletes characters the
    engine had ALREADY committed (screen eats into earlier text)."""
    s, be, _ = _make_stream(revision_debounce_s=0.0)
    screen = _ScreenModel(drop_first_type=True)

    # One committed utterance first (lands fine, engine + screen agree).
    s.on_partial("first sentence committed.")
    s.commit("first sentence committed.")
    screen.text = "first sentence committed. "  # post-commit screen truth

    # Utterance two: the engine's FIRST type lands on screen, then a partial
    # revision diverges at the tail and the debounced rewind fires.
    s.on_partial("second sentence with a tail that diverges")
    be.calls.clear()
    divergent = "second sentence with a tail that now diverges differently"
    s.on_partial(divergent)
    # Replay every keystroke the engine emitted onto the screen model, with
    # the first type of THIS burst silently dropped (compositor loss, exit 0).
    dropped_one = False
    for op, arg in be.calls:
        if op == "type":
            if not dropped_one:
                dropped_one = True  # the silent loss
                continue
            screen.type(arg)
        else:
            screen.backspace(arg)

    believed = "first sentence committed. " + divergent
    assert screen.text != believed, "test setup failed to create desync"
    # The rewind was computed from the BELIEVED tail, so on the real screen it
    # deleted more than the tail — it ate into committed text.
    assert not screen.text.startswith("first sentence committed."), (
        f"screen should have lost committed text, got: {screen.text!r}"
    )
