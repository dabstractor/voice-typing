"""Unit tests for the StreamingOutput freeze lifecycle (PRD §4.2quater rules 4-5 — P1.M2.T6.S3).

Pure-Python: no CUDA, no mic, no real keystrokes — reuses the S1 doubles
(RecordingBackend / FakeFeedback) copied verbatim from tests/test_streaming_core.py.
Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_streaming_freeze.py -q

Covers: the two freeze classes (per-utterance lifted by reset_boundary(); session
survives it and clears only at reset_session()), promote-only class upgrades,
backend-failure freezes being session-class, note_user_keypress() (freeze iff a
tail is pending; idempotent; cannot demote a session freeze; frozen commit
absorbs without keystrokes and the boundary lifts the freeze so the next
utterance types normally), and stranded-tail semantics (late commit absorbs and
STAYS frozen; late partials mirror-only; disarm sends zero keystrokes).
"""
from __future__ import annotations

import logging

from voice_typing.streaming import StreamingOutput
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


def _make_stream(
    backend: RecordingBackend | None = None,
    *,
    streaming: bool = True,
) -> tuple[StreamingOutput, RecordingBackend, FakeFeedback]:
    backend = backend if backend is not None else RecordingBackend()
    fb = FakeFeedback()
    return StreamingOutput(backend, fb, streaming), backend, fb


# ---------------------------------------------------------------------------
# Freeze classes: per-utterance vs session (PRD rules 4-5 lifecycle)
# ---------------------------------------------------------------------------

def test_freeze_default_is_per_utterance_and_lifted_by_reset_boundary():
    stream, _be, _fb = _make_stream()
    stream.freeze("test freeze")
    assert stream.frozen is True and stream.frozen_session is False
    stream.reset_boundary()
    assert stream.frozen is False and stream.frozen_session is False


def test_freeze_session_survives_reset_boundary_until_reset_session():
    stream, _be, _fb = _make_stream()
    stream.freeze("stranded tail", session=True)
    stream.reset_boundary()
    assert stream.frozen is True, "a session freeze must survive the boundary"
    assert stream.frozen_session is True
    stream.reset_session()
    assert stream.frozen is False and stream.frozen_session is False


def test_freeze_promotes_per_utterance_to_session():
    """A session freeze arriving while already frozen (per-utterance) must UPGRADE
    the class — never silently leave the weaker lifetime in charge."""
    stream, _be, _fb = _make_stream()
    stream.freeze("user keypress")            # per-utterance first
    stream.freeze("stranded tail", session=True)
    assert stream.frozen_session is True
    stream.reset_boundary()
    assert stream.frozen is True, "the promotion must survive the boundary"


def test_freeze_never_demotes_session_to_per_utterance():
    stream, _be, _fb = _make_stream()
    stream.freeze("stranded tail", session=True)
    stream.freeze("later user keypress")      # weaker class: must NOT demote
    assert stream.frozen_session is True
    stream.reset_boundary()
    assert stream.frozen is True


def test_freeze_idempotent_first_class_wins_within_same_class():
    stream, _be, _fb = _make_stream()
    stream.freeze("first")
    stream.freeze("second")                   # same class: no-op
    assert stream.frozen_session is False
    stream.reset_boundary()
    assert stream.frozen is False


# ---------------------------------------------------------------------------
# Backend-failure freezes are SESSION-class (S1 fail-safe paths, retagged S3)
# ---------------------------------------------------------------------------

def test_backend_type_failure_freezes_session_class():
    be = RecordingBackend(fail_type=True)
    stream, _backend, _fb = _make_stream(be)
    stream.on_partial("hello")                # fresh start -> type_text raises -> freeze
    assert stream.frozen is True and stream.frozen_session is True
    stream.reset_boundary()
    assert stream.frozen is True, "backend-failure freeze must survive the boundary"
    stream.reset_session()
    assert stream.frozen is False


def test_backend_backspace_failure_freezes_session_class():
    be = RecordingBackend(fail_backspace=True)
    stream, _backend, _fb = _make_stream(be)
    stream.on_partial("hello wor")            # extends fine
    stream.on_partial("goodbye")              # revise -> press_backspace raises -> freeze
    assert stream.frozen is True and stream.frozen_session is True
    stream.reset_boundary()
    assert stream.frozen is True


# ---------------------------------------------------------------------------
# note_user_keypress (PRD rule 5 — never type over the user's cursor)
# ---------------------------------------------------------------------------

def test_note_user_keypress_freezes_pending_tail_and_mirrors_only():
    stream, be, fb = _make_stream()
    stream.on_partial("hello wor")            # tail typed and pending
    stream.note_user_keypress()
    assert stream.frozen is True and stream.frozen_session is False
    stream.on_partial("hello world")          # late partial: mirror-only, NO keystrokes
    assert be.calls == [("type", "hello wor")]
    assert fb.partials[-1] == "hello wor"     # frozen mirror shows the TYPED tail
    assert stream.tail == "hello wor"


def test_note_user_keypress_noop_without_pending_tail():
    stream, be, _fb = _make_stream()
    stream.note_user_keypress()               # nothing typed yet: plain user editing
    assert stream.frozen is False
    stream.on_partial("hello")
    assert be.calls == [("type", "hello")], "typing must be unaffected by an early keypress"


def test_note_user_keypress_idempotent():
    stream, be, _fb = _make_stream()
    stream.on_partial("hello")
    stream.note_user_keypress()
    stream.note_user_keypress()               # already frozen: no-op, no error
    assert stream.frozen is True and stream.frozen_session is False
    assert be.calls == [("type", "hello")]


def test_note_user_keypress_noop_when_streaming_disabled():
    stream, _be, _fb = _make_stream(streaming=False)
    stream.note_user_keypress()
    assert stream.frozen is False


def test_note_user_keypress_cannot_demote_session_freeze():
    stream, _be, _fb = _make_stream()
    stream.on_partial("hello")
    stream.freeze("stranded tail", session=True)
    stream.note_user_keypress()               # weaker class: must not weaken
    assert stream.frozen_session is True
    stream.reset_boundary()
    assert stream.frozen is True


def test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types():
    """The S3 daemon sequence (PRP gotcha — do not reorder): keypress freezes the
    tail -> the final arrives -> commit() takes the frozen-ABSORB branch (zero
    keystrokes, tail into committed) -> reset_boundary() lifts the per-utterance
    freeze -> the NEXT utterance types normally."""
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    stream.note_user_keypress()
    stream.commit("hello world")
    assert be.calls == [("type", "hello wor")], "a frozen commit must absorb, not type"
    assert stream.committed == "hello wor"
    assert stream.tail == ""
    assert stream.frozen is True, "commit() must not unfreeze; the boundary does"
    stream.reset_boundary()                   # the daemon's post-commit boundary call
    assert stream.frozen is False
    stream.on_partial("next")
    assert be.calls == [("type", "hello wor"), ("type", "next")]


def test_note_user_keypress_logs_warning(caplog):
    stream, _be, _fb = _make_stream()
    stream.on_partial("hello")
    with caplog.at_level(logging.WARNING, logger="voice_typing.streaming"):
        stream.note_user_keypress()
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# Stranded-tail semantics (PRD rule 4): drain timeout / child death class
# ---------------------------------------------------------------------------

def test_session_frozen_tail_late_commit_absorbs_without_keystrokes_and_stays_frozen():
    """Race case: the watchdog froze a stranded tail but the final fires anyway —
    commit() must absorb (no rewind, no retype) and the session freeze must
    survive the daemon's post-commit reset_boundary()."""
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    stream.freeze("drain timeout: stranded tail", session=True)
    stream.commit("hello world")
    assert be.calls == [("type", "hello wor")]
    assert stream.committed == "hello wor"
    stream.reset_boundary()
    assert stream.frozen is True and stream.frozen_session is True


def test_session_frozen_late_partials_mirror_only_never_type():
    stream, be, fb = _make_stream()
    stream.on_partial("hello wor")
    stream.freeze("recorder-host child died: stranded tail", session=True)
    stream.on_partial("hello world again")
    assert be.calls == [("type", "hello wor")], "a stranded tail must never gain keystrokes"
    assert fb.partials[-1] == "hello wor"


def test_session_frozen_disarm_sends_no_keystrokes_and_next_session_types():
    """reset_session() (the disarm/next-arm path) clears the engine strings but
    sends ZERO keystrokes — the stranded tail stays on screen (no rewind-on-disarm,
    PRD rule 4) — and the fresh session types normally."""
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    stream.freeze("stranded", session=True)
    stream.reset_session()
    assert stream.frozen is False and stream.committed == "" and stream.tail == ""
    assert be.calls == [("type", "hello wor")], "reset_session must never press backspace"
    stream.on_partial("fresh session")
    assert be.calls == [("type", "hello wor"), ("type", "fresh session")]
