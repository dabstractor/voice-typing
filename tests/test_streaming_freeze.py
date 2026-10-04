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
    tail -> the final arrives -> commit() takes the frozen-ABSORB branch (tail
    into committed + the append_space separator — BUG-003 fix; no revision
    keystrokes) -> reset_boundary() lifts the per-utterance freeze -> the NEXT
    utterance types normally, space-separated from the absorbed tail."""
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    stream.note_user_keypress()
    stream.commit("hello world")
    assert be.calls == [("type", "hello wor"), ("type", " ")], (
        "a frozen commit must absorb (no revision keystrokes) but still type the separator"
    )
    assert stream.committed == "hello wor "
    assert stream.tail == ""
    assert stream.frozen is True, "commit() must not unfreeze; the boundary does"
    stream.reset_boundary()                   # the daemon's post-commit boundary call
    assert stream.frozen is False
    stream.on_partial("next")
    assert be.calls == [("type", "hello wor"), ("type", " "), ("type", "next")]


def test_note_user_keypress_logs_warning(caplog):
    stream, _be, _fb = _make_stream()
    stream.on_partial("hello")
    with caplog.at_level(logging.WARNING, logger="voice_typing.streaming"):
        stream.note_user_keypress()
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# Stranded-tail semantics (PRD rule 4): drain timeout / child death class
# ---------------------------------------------------------------------------

def test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen():
    """Race case: the watchdog froze a stranded tail but the final fires anyway —
    commit() must absorb (no rewind, no retype) + the append_space separator
    (BUG-003 fix), and the session freeze must survive the daemon's post-commit
    reset_boundary()."""
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    stream.freeze("drain timeout: stranded tail", session=True)
    stream.commit("hello world")
    assert be.calls == [("type", "hello wor"), ("type", " ")]
    assert stream.committed == "hello wor "
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


# ---------------------------------------------------------------------------
# BUG-001 (PRD h3.0): a single rejected final (blocklist/min_chars) freezes with
# session=True and used to silence typed output until the next re-arm. The
# engine contract (re-scoped by the Rev-2 validation, ISSUE-001/ISSUE-002):
# resume() is fired on EVERY partial's paired speech event, so it is class-aware
# — it clears post-cancel suppression always, lifts a stranded non-backend
# session freeze, and REFUSES per-utterance (user-keypress) and echo-guarded
# (rejected-final) freezes. A guarded rejected-final freeze lifts at the first
# NON-echo partial inside on_partial; reset_boundary() under freeze ABSORBS the
# tail into the checkpoint; backend-failure freezes stay un-liftable (fail-safe).
# ---------------------------------------------------------------------------


def test_rejected_final_freeze_lives_until_resume_then_next_utterance_types():
    """BUG-001 engine contract (the PRD h3.0 repro): a rejected-final SESSION freeze
    survives the boundary AND stray late partials (the never-retag pin), lifts ONLY
    at resume(), and the next utterance then streams for real (on_partial types;
    commit corrects+joins)."""
    stream, be, _fb = _make_stream()
    stream.on_partial("Hello world.")         # baseline utterance types
    stream.commit("Hello world.")
    stream.reset_boundary()
    n0 = len(be.calls)
    assert n0 > 0, "baseline typing must have happened"
    stream.on_partial("Thank you")            # the to-be-rejected utterance typed live
    n1 = len(be.calls)
    assert n1 > n0
    stream.freeze("rejected final (blocklist/min_chars)", session=True)
    stream.reset_boundary()
    assert stream.frozen is True and stream.frozen_session is True
    stream.on_partial("ank you.")             # stray late partial of the REJECTED utterance
    assert stream.frozen is True, "must stay frozen across strays (never retag per-utterance)"
    assert len(be.calls) == n1, "frozen strays must be mirror-only (zero keystrokes)"
    stream.resume()
    assert stream.frozen is False and stream.frozen_session is False
    stream.on_partial("The next real sentence")
    # (casing guard lowercases the mid-sentence leading 'T' — match the stable suffix.)
    assert any("next real sentence" in t for _, t in be.calls), "real typing must resume"
    n2 = len(be.calls)
    stream.commit("The next real sentence")
    assert len(be.calls) > n2, "the next commit must produce real backend calls"


def test_resume_cannot_lift_backend_failure_freeze():
    """Fail-safe: a freeze raised by a backend exception (engine-internal origin) is
    NOT liftable by resume() — the on-screen state is untrusted; only reset_session()
    (fresh arm) recovers. Covers BOTH failure doubles."""
    be_type = RecordingBackend(fail_type=True)
    stream, _b1, _f1 = _make_stream(be_type)
    stream.on_partial("hello")                # fresh start -> type_text raises -> freeze
    assert stream.frozen is True and stream.frozen_session is True
    stream.resume()
    assert stream.frozen is True, "backend-failure freeze must survive resume()"
    stream.on_partial("hello again")
    assert be_type.calls == [], "a backend-failure freeze must stay mirror-only"

    be_bs = RecordingBackend(fail_backspace=True)
    stream2, _b2, _f2 = _make_stream(be_bs)
    stream2.on_partial("hello wor")           # types fine
    stream2.on_partial("goodbye")             # revise -> press_backspace raises -> freeze
    assert stream2.frozen is True
    stream2.resume()
    assert stream2.frozen is True, "backspace-failure freeze must also survive resume()"


def test_reset_boundary_under_freeze_absorbs_tail_into_committed():
    """BUG-001 companion: the rejected final's boundary drops the tail — it must be
    ABSORBED into the checkpoint first (commit()'s frozen-path join discipline), so
    the casing guard / context prompt / mirror stay truthful. Keystroke-free."""
    stream, be, _fb = _make_stream()
    stream.on_partial("Hello world")          # empty committed -> verbatim
    assert stream.tail == "Hello world"
    stream.freeze("rejected final (blocklist/min_chars)", session=True)
    stream.reset_boundary()
    assert stream.committed == "Hello world", "the frozen tail must be absorbed"
    assert stream.tail == ""
    assert be.calls == [("type", "Hello world")], "the absorb must send no keystrokes"
    assert stream.frozen is True, "the freeze itself survives (resume() owns the lift)"


def test_resume_clears_post_cancel_suppression():
    """resume() ALWAYS clears _suppressed (the P1.M1.T2.S1 / BUG-002 reuse seam):
    after reset_after_cancel() the suppressed mirror-only state is lifted and the
    next partial types again. Idempotent."""
    stream, be, fb = _make_stream()
    stream.reset_after_cancel()
    stream.on_partial("stale partial")        # suppressed: raw mirror only
    assert be.calls == []
    assert fb.partials[-1] == "stale partial"
    stream.resume()
    stream.resume()                           # idempotent: second call is a no-op
    stream.on_partial("hello")
    assert be.calls == [("type", "hello")], "typing must resume after resume()"


def test_cancel_then_resume_restores_live_delta_typing():
    """BUG-002 / P1.M1.T2.S1 (the contract's full repro): post-cancel suppression
    lifts at resume(), so the RE-SAID sentence streams LIVE again.

    Daemon-flow rationale: a Backspace-cancel fires reset_after_cancel() (tail
    cleared, _suppressed=True), but the daemon never fires reset_boundary()
    between the cancel and the next real final — the sentinel final is dropped
    BEFORE commit()/reset_boundary() can run (daemon.py:1130-1137). So until the
    daemon calls resume() at the next genuinely-new speech (P1.M1.T1.S2 wiring;
    T2.S2), on_partial must stay mirror-only; after resume(), the next partial
    types for real against the committed checkpoint.
    """
    stream, be, fb = _make_stream()
    stream.on_partial("Hello world")
    stream.commit("Hello world")
    stream.on_partial("the quick brown")
    stream.reset_after_cancel()               # tail cleared; committed UNCHANGED
    stream.on_partial("the quick brown fox")  # the re-said sentence begins
    # Guard half — suppression HOLDS without resume(): zero NEW keystrokes (the
    # stale partial of the cancelled utterance must not re-type anything).
    assert be.calls == [
        ("type", "Hello world"),
        ("type", " "),                # commit's inter-final space
        ("type", "the quick brown"),  # pre-cancel tail (daemon deletes it off-screen)
    ], "suppression must HOLD until resume() — the stale partial typed NOTHING"
    assert fb.partials[-1] == "the quick brown fox"  # suppressed: RAW partial mirrored
    stream.resume()
    stream.on_partial("the quick brown fox jumps")
    # Landing half — live typing restored. reset_after_cancel() cleared the tail,
    # so the landing is a FRESH START (no rewind, no rate-limit consult): exactly
    # ONE guarded type of the full re-said sentence (observed, CRITICAL #1).
    assert be.calls[-1] == ("type", "the quick brown fox jumps")
    assert all(c[0] == "type" for c in be.calls), "no backspaces: nothing to rewind"
    assert stream.committed == "Hello world " and stream.tail == "the quick brown fox jumps"
    assert (stream.committed + stream.tail) == "Hello world the quick brown fox jumps"


# ---------------------------------------------------------------------------
# Rev-2 validation ISSUE-001 / ISSUE-002: resume() is the PER-PARTIAL speech
# seam (the child's on_speech fires on every stabilized partial), so it must be
# class-aware, and a rejected-final freeze needs the stray-echo guard + the
# non-echo-partial lift inside on_partial.
# ---------------------------------------------------------------------------


def test_resume_never_lifts_per_utterance_keypress_freeze():
    """ISSUE-001: resume() is fired by the per-partial speech seam, so it must NEVER
    lift a user-keypress (per-utterance) freeze — that one lifts only at
    reset_boundary(), after the frozen commit absorbs the tail (PRD rule 5)."""
    stream, be, _fb = _make_stream()
    stream.on_partial("hello wor")
    assert be.calls == [("type", "hello wor")]
    stream.note_user_keypress()
    assert stream.frozen is True
    stream.resume()
    assert stream.frozen is True, "per-utterance freeze must survive resume()"
    stream.on_partial("hello world")  # mirror-only: nothing over the user's edit
    assert be.calls == [("type", "hello wor")]
    stream.commit("hello world")     # frozen absorb (separator only) ...
    stream.reset_boundary()          # ...then the boundary lifts the freeze
    assert stream.frozen is False
    stream.on_partial("New sentence")
    assert any("new sentence" in t.lower() for _, t in be.calls)


def test_stray_echo_guard_holds_until_first_non_echo_partial():
    """ISSUE-002 + BUG-001 together: after a rejected final the daemon arms the
    stray-echo guard; echo strays of the dead utterance (their paired speech event
    included) hold the freeze mirror-only; the first NON-echo partial lifts the
    freeze inside on_partial and streams live."""
    stream, be, fb = _make_stream()
    stream.on_partial("Hello world")
    stream.commit("Hello world")
    stream.reset_boundary()
    stream.freeze("rejected final (blocklist/min_chars)", session=True)
    stream.reset_boundary()
    stream.arm_stray_echo_guard("Thank you.")
    n0 = len(be.calls)
    for _ in range(2):  # two hallucination cycles: stray partial + paired speech
        stream.on_partial("thank you")
        assert stream.frozen is True
        assert fb.partials[-1] == "", "an echo stray mirrors the (empty) frozen tail"
        stream.resume()  # the paired ('speech', {}) event
        assert stream.frozen is True, "resume() must refuse an echo-guarded freeze"
    assert len(be.calls) == n0, "echo strays must type nothing"
    stream.on_partial("ank you")  # a mid-word truncation is still an echo
    assert stream.frozen is True and len(be.calls) == n0
    stream.on_partial("The next real sentence")  # genuinely new: lifts + types live
    assert stream.frozen is False
    assert any("the next real sentence" in t.lower() for _, t in be.calls)
    stream.on_partial("The next real sentence rocks")  # guard gone: normal extends
    assert any("rocks" in t for _, t in be.calls)


def test_reset_session_clears_stray_echo_guard():
    """The guard is cleared exactly with the freeze it guards: a fresh arm
    (reset_session) must leave no residue — the new session streams normally."""
    stream, be, _fb = _make_stream()
    stream.freeze("rejected final (blocklist/min_chars)", session=True)
    stream.arm_stray_echo_guard("Thank you.")
    stream.reset_session()
    assert stream.frozen is False
    stream.on_partial("thank you")  # would be an echo — but the guard is gone
    assert any("thank you" in t for _, t in be.calls), (
        "a fresh session must not inherit the echo guard"
    )


def test_resume_lifts_stranded_session_freeze_but_not_guarded_or_per_utterance():
    """resume()'s exact class matrix: lifts a stranded non-backend SESSION freeze;
    refuses a guarded one, a per-utterance one, and a backend-failure one."""
    # stranded session freeze (no guard): lifts
    s1, _b1, _f1 = _make_stream()
    s1.freeze("drain-timeout stranded tail", session=True)
    s1.resume()
    assert s1.frozen is False
    # guarded rejected-final freeze: refused
    s2, _b2, _f2 = _make_stream()
    s2.freeze("rejected final", session=True)
    s2.arm_stray_echo_guard("thank you.")
    s2.resume()
    assert s2.frozen is True
    # backend-failure freeze: still refused (fail-safe, unchanged)
    s3, _b3, _f3 = _make_stream(RecordingBackend(fail_type=True))
    s3.on_partial("hello")  # raises -> freeze
    assert s3.frozen is True
    s3.resume()
    assert s3.frozen is True
