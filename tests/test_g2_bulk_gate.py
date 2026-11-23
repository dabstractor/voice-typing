"""tests/test_g2_bulk_gate.py — THE G2 GATE (PRD §4.2sexies R.7): full
fake-target trace matrix over BulkController, with the six assertion families
woven into every trace, legacy-backend sentinels, and a machine-checked
coverage summary. The gate record lives at
plan/008_a47116bb2b79/architecture/g2_gate_record.md.

PRD §4.2sexies R.7, second bullet, verbatim:

  "G2 controller, fake target: deterministic traces — append; first-word
  change; identical update and final; retraction; Unicode; rejected/lost
  final; repeated cancel; timeout-after-apply; held key; out-of-order
  results; stop + immediate re-arm; child death; focus change
  mid-operation. Assert exact text/caret, bounded queue, zero legacy-backend
  calls, no duplicates, no extra writes, no post-takeover mutations.
  Necessary, never sufficient."

**G2 is necessary, NEVER sufficient — a G2 pass never marks a field row
verified.** G3 (P1.M4.T5) is the real-field gate; a passing transport probe
or a G2 pass NEVER flips any R.2 row to "passed".

Everything is deterministic: dispatch is driven through the SAME seam the
writer thread runs (drain()/_process_next), fakes gate on threading.Event
with bounded waits (≤1.0 s), and op_deadline=0.02 s so the only real-thread
use is the controller's own single-worker op runner. No bare sleeps, no
CUDA, no daemon, no Wayland. Run:

    cd /home/dustin/projects/voice-typing
    timeout 60 .venv/bin/python -m pytest tests/test_g2_bulk_gate.py -v
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import voice_typing.typing_backends as typing_backends  # noqa: E402  (sentinel patching ONLY)
from voice_typing.bulk_controller import BulkController  # noqa: E402
from voice_typing.bulk_delivery import (  # noqa: E402
    AcquireResult,
    ShowResult,
    rendered_equal,
)

QSIZE = 32           # R.5 bounded-queue default
DEADLINE = 0.02      # op_deadline for every trace (only trace 08/10 hit it)

# The frozen 13-trace matrix (R.7's G2 bullet vocabulary, 1:1). The summary
# test machine-checks module coverage against EXACTLY this list.
_TRACE_NAMES = [
    "test_trace_01_append",
    "test_trace_02_first_word_change",
    "test_trace_03_identical_update_and_final",
    "test_trace_04_retraction",
    "test_trace_05_unicode",
    "test_trace_06_rejected_lost_final",
    "test_trace_07_repeated_cancel",
    "test_trace_08_timeout_after_apply",
    "test_trace_09_held_key",
    "test_trace_10_out_of_order_results",
    "test_trace_11_stop_and_immediate_rearm",
    "test_trace_12_child_death",
    "test_trace_13_focus_change_mid_operation",
]


# ---------------------------------------------------------------------------
# FAMILY 3 fixture — ZERO legacy-backend calls, behavioral, on EVERY trace
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_legacy_backend(monkeypatch):
    """Replace the ENTIRE legacy typing-backend surface with sentinel
    recorders that fail the test on ANY call (d2 §3: no type_text /
    press_backspace / make_backend / backend classes reachable in bulk
    mode). This is the runtime twin of S1's source-scan purity guards: even
    with the surface wired to explosives, all 13 traces must pass with zero
    recorded calls. Bulk mode has no typing fallback — R.1.
    """
    calls: list[str] = []

    def _sentinel(name):
        def _boom(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"legacy backend {name} reached in bulk mode")

        return _boom

    for name in ("type_text", "press_backspace", "make_backend"):
        monkeypatch.setattr(typing_backends, name, _sentinel(name), raising=False)
    for klass in ("TypingBackend", "WtypeBackend", "YdotoolBackend", "NullBackend"):
        monkeypatch.setattr(typing_backends, klass, _sentinel(f"class:{klass}"), raising=False)
    yield calls
    assert calls == [], f"legacy backend reached during the gate: {calls}"


# ---------------------------------------------------------------------------
# G2FakeTarget — the field-modeling fake (research §1)
# ---------------------------------------------------------------------------


class G2FakeTarget:
    """Field-modeling DeliveryTarget double: owned-range replacement, visible
    edit counting, programmable faults.

    Field model (what the R.2 GTK probe asserted): ``text`` (the whole
    field), ``owned`` (the (start, end) char span WE own — the ONLY range
    ever mutated; adjacent user text survives byte-exact, R.3), ``caret``
    (char index; owned end after an APPLIED show/finalize), ``edit_count``
    (VISIBLE edits — the R.1 event-count-law counter: +1 per mutation, +0
    for unchanged/refused/unknown no-ops).

    Evidence: ``ops`` = completed [(method, span, expected_revision, result)];
    ``begun`` = every protocol call that STARTED (in-flight evidence for the
    one-call/no-retry families); ``thread_ids`` = idents of mutating calls
    (one-writer corroboration).

    Faults: ``gate`` (Event — block show/finalize for timeout-after-apply),
    ``raise_exc`` (child death), ``refuse_after`` (refuse every mutating op
    after this many successes — held key / focus change), ``raise_on_leave``
    (dead target's leave), ``bound_session`` (adapter-side mutation-time
    ownership re-check: ops of any other session are REFUSED).
    """

    def __init__(self, *, seed_prefix: str = "", seed_suffix: str = "",
                 acquire_revision: int = 0) -> None:
        self.seed_prefix = seed_prefix
        self.text = seed_prefix + seed_suffix
        self.owned = (len(seed_prefix), len(seed_prefix))
        self.caret = len(seed_prefix)
        self.edit_count = 0
        self.ops: list[tuple] = []
        self.begun: list[str] = []
        self.thread_ids: set[int] = set()
        self.leave_calls = 0
        self.gate: threading.Event | None = None
        self.raise_exc: BaseException | None = None
        self.refuse_after: int | None = None
        self.raise_on_leave = False
        self.bound_session: int | None = None
        self._acquire_revision = acquire_revision
        self._ok = 0
        self._lock = threading.Lock()

    # -- internals ----------------------------------------------------------

    def _faults(self):
        """Fault injection BEFORE any mutation (runs OUTSIDE the lock so a
        gated op never wedges an inspection)."""
        if self.gate is not None:
            self.gate.wait(1.0)  # bounded: the controller's deadline fires first
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.refuse_after is not None and self._ok >= self.refuse_after:
            return ShowResult.REFUSED
        return None

    def _begin(self, method: str) -> None:
        with self._lock:
            self.begun.append(method)
            if method in ("show", "finalize", "cancel"):
                # MUTATING ops only — F6's one-writer corroboration (acquire/
                # leave run on the caller's thread and write nothing, R.3).
                self.thread_ids.add(threading.get_ident())

    def _perform(self, method: str, session: int, expected_revision: int, span: str,
                 *, final: bool = False) -> ShowResult:
        """ONE insert-or-replace of EXACTLY the owned range (R.3), with the
        mutation-time ownership re-check and fault injection first."""
        refused = self._faults()
        with self._lock:
            if self.bound_session is not None and session != self.bound_session:
                result = ShowResult.REFUSED  # stale session: never mutate
            elif refused is not None:
                result = refused
            elif final and rendered_equal(self.text[self.owned[0]:self.owned[1]], span):
                result = ShowResult.UNCHANGED  # zero-diff finalize: edit_count += 0
            else:
                start, end = self.owned
                self.text = self.text[:start] + span + self.text[end:]
                self.owned = (start, start + len(span))
                self.caret = self.owned[1]
                self.edit_count += 1
                self._ok += 1
                result = ShowResult.APPLIED
            self.ops.append((method, span, expected_revision, result))
            return result

    # -- DeliveryTarget protocol ---------------------------------------------

    def acquire(self) -> AcquireResult:
        self._begin("acquire")
        return AcquireResult(ok=True, handle="g2", revision=self._acquire_revision)

    def show(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        self._begin("show")
        return self._perform("show", session, expected_revision, span)

    def finalize(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        self._begin("finalize")
        return self._perform("finalize", session, expected_revision, span, final=True)

    def leave(self) -> None:
        """leave = preserve: records the call, NEVER mutates (zero writes)."""
        with self._lock:
            self.leave_calls += 1
        if self.raise_on_leave:
            raise RuntimeError("field died before leave()")

    def cancel(self) -> ShowResult:
        """R.3 cancel: remove the owned fragment in ONE operation. Nothing
        owned ⇒ unchanged (+0 edits); owned ⇒ range removed, caret back to
        the owned start, +1 edit."""
        with self._lock:
            self.begun.append("cancel")
            self.thread_ids.add(threading.get_ident())
            if self.owned[0] == self.owned[1]:
                result = ShowResult.UNCHANGED
            else:
                start, end = self.owned
                self.text = self.text[:start] + self.text[end:]
                self.owned = (start, start)
                self.caret = start
                self.edit_count += 1
                result = ShowResult.APPLIED
            self.ops.append(("cancel", None, None, result))
            return result


# ---------------------------------------------------------------------------
# Drive + assertion-family helpers (research §2/§2b)
# ---------------------------------------------------------------------------


def _controller(fake, *, gen=1, queue_size=QSIZE, op_deadline=DEADLINE, on_stopped=None):
    ctrl = BulkController(fake, queue_size=queue_size, on_stopped=on_stopped,
                          op_deadline=op_deadline)
    assert ctrl.acquire() is True
    assert ctrl.arm(gen) is True
    return ctrl


def _wait_until(predicate, timeout=1.0, interval=0.005) -> bool:
    """Bounded Event-style poll (≤1.0 s) — the gate's only real-thread wait."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _families(fake, ctrl, *, legacy_calls, expected_text=None, expected_caret=None,
              expected_edits=None, queue_size=QSIZE, max_writers=1):
    """The six R.7 assertion families, woven through EVERY trace (§2b):

    F1 exact text/caret (adjacent user text byte-exact) — expected_* args;
    F2 bounded queue — len(ctrl._dq) <= queue_size here and after every step;
    F3 zero legacy-backend calls — the sentinel recorders stayed empty;
    F4 no duplicates / F5 no extra writes — per-trace op-log + edit_count
       asserts against the event-count-law numbers below;
    F6 no post-takeover mutations + one-writer — thread_ids never grows past
       the single op-runner thread.
    """
    if expected_text is not None:
        assert fake.text == expected_text, f"F1 field text drifted: {fake.text!r}"
    if expected_caret is not None:
        assert fake.caret == expected_caret, f"F1 caret drifted: {fake.caret!r}"
    assert len(ctrl._dq) <= queue_size, "F2 queue exceeded its bound"
    assert legacy_calls == [], f"F3 legacy backend reached: {legacy_calls}"
    assert len(fake.thread_ids) <= max_writers, "F6 more writer threads than lifetimes touched the target"
    if expected_edits is not None:
        assert fake.edit_count == expected_edits, (
            f"F5 edit_count {fake.edit_count} != event-count-law number {expected_edits}"
        )


def _spans(fake, method=None):
    return [op[1] for op in fake.ops if method is None or op[0] == method]


# ---------------------------------------------------------------------------
# THE 13-TRACE MATRIX (R.7 G2 bullet, one named test per trace)
# ---------------------------------------------------------------------------


def test_trace_01_append(_no_legacy_backend):
    """R.7 trace 1 — append: partials then final; 2 shows + finalize UNCHANGED."""
    fake = G2FakeTarget(seed_prefix="log: ")
    ctrl = _controller(fake)
    ctrl.on_partial("Hello", utterance="u1", seq=1, gen=1)
    assert ctrl.drain() == 2                       # SessionBegin barrier + the partial
    ctrl.on_partial("Hello world", utterance="u1", seq=2, gen=1)
    ctrl.drain()
    ctrl.on_final("Hello world", utterance="u1", seq=3, gen=1)
    ctrl.drain()
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="log: Hello world", expected_caret=5 + 11, expected_edits=2)
    assert [op[0] for op in fake.ops] == ["show", "show", "finalize"]
    assert _spans(fake, "show") == ["Hello", "Hello world"]
    assert fake.ops[-1] == ("finalize", "Hello world", 2, ShowResult.UNCHANGED)
    assert fake.text.count("Hello world") == 1                      # F4 no duplicates
    assert ctrl.stats()["expected_revision"] == 2                   # +1 ONLY on APPLIED
    assert ctrl.stats()["applied"] == 2 and ctrl.stats()["unchanged"] == 1
    assert ctrl.stats()["zero_diff_skipped"] == 0
    assert ctrl.confirmed_visible() == "Hello world"
    assert ctrl.is_active() is True


def test_trace_02_first_word_change(_no_legacy_backend):
    """R.7 trace 2 — first-word change: ONE show with the COMPLETE new span."""
    fake = G2FakeTarget(seed_prefix="pre ", seed_suffix=" post")
    ctrl = _controller(fake)
    ctrl.on_partial("Hello world", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    ctrl.on_partial("Hi world", utterance="u1", seq=2, gen=1)
    ctrl.drain()
    # the correction = exactly ONE op carrying the complete new span (R.1:
    # correction = 1), never a per-character retype; insertion was 1 op too
    assert _spans(fake, "show") == ["Hello world", "Hi world"]
    assert fake.begun.count("show") == 2
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="pre Hi world post", expected_caret=4 + 8, expected_edits=2)
    assert fake.owned == (4, 12)                                    # owned range replaced in place
    assert fake.text.count("Hi world") == 1                         # F4
    assert ctrl.confirmed_visible() == "Hi world"
    assert ctrl.stats()["expected_revision"] == 2


def test_trace_03_identical_update_and_final(_no_legacy_backend):
    """R.7 trace 3 — identical update AND final: zero-diff partial = ZERO
    target calls; identical final = finalize once → UNCHANGED, edit 0."""
    fake = G2FakeTarget()
    ctrl = _controller(fake)
    ctrl.on_partial("same text", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    ctrl.on_partial("same text", utterance="u1", seq=2, gen=1)
    assert ctrl.drain() == 1                                        # the skip IS the dispatch
    assert fake.begun.count("show") == 1                            # 2nd partial: ZERO target calls
    assert ctrl.stats()["zero_diff_skipped"] == 1
    ctrl.on_final("same text", utterance="u1", seq=3, gen=1)
    ctrl.drain()
    assert fake.begun.count("finalize") == 1                        # finalize called ONCE
    assert fake.ops[-1] == ("finalize", "same text", 1, ShowResult.UNCHANGED)
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="same text", expected_caret=9, expected_edits=1)
    assert fake.text.count("same text") == 1                        # F4: no duplicate text
    assert ctrl.stats()["expected_revision"] == 1                   # UNCHANGED: no advance
    assert ctrl.stats()["unchanged"] == 1


def test_trace_04_retraction(_no_legacy_backend):
    """R.7 trace 4 — retraction: the owned range SHRINKS, one show per change."""
    fake = G2FakeTarget(seed_prefix="s: ")
    ctrl = _controller(fake)
    ctrl.on_partial("hello world", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    assert fake.owned == (3, 14)
    ctrl.on_partial("hello", utterance="u1", seq=2, gen=1)
    ctrl.drain()
    assert _spans(fake, "show") == ["hello world", "hello"]
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="s: hello", expected_caret=3 + 5, expected_edits=2)
    assert fake.owned == (3, 8)                                     # SHRUNK, never left residue
    assert fake.text.count("hello") == 1 and "world" not in fake.text  # F4
    assert ctrl.confirmed_visible() == "hello"


def test_trace_05_unicode(_no_legacy_backend):
    """R.7 trace 5 — Unicode spans byte/codepoint-exact; caret = char index."""
    fake = G2FakeTarget(seed_prefix="❄ ")
    ctrl = _controller(fake)
    span = "naïve café 😀 猫"
    ctrl.on_partial(span, utterance="u1", seq=1, gen=1)
    ctrl.drain()
    ctrl.on_final(span, utterance="u1", seq=2, gen=1)
    ctrl.drain()
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="❄ " + span, expected_caret=2 + len(span), expected_edits=1)
    assert fake.owned == (2, 2 + len(span))                         # codepoint-exact span
    assert len(fake.text) == 2 + len(span)                          # no mojibake: exact codepoints
    assert "😀" in fake.text and "猫" in fake.text
    assert fake.text.count(span) == 1                               # F4
    assert fake.ops[-1] == ("finalize", span, 1, ShowResult.UNCHANGED)


def test_trace_06_rejected_lost_final(_no_legacy_backend):
    """R.7 trace 6 — rejected/lost final: NO finalize, shown tail PRESERVED,
    boundary closes, late partials die, queue empties."""
    fake = G2FakeTarget()
    ctrl = _controller(fake)
    ctrl.on_partial("shown tail", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    ctrl.on_final_dropped(utterance="u1", gen=1)
    assert ctrl.drain() == 1                                        # the boundary; NO finalize call
    ctrl.on_partial("late!", utterance="u1", seq=2, gen=1)          # post-boundary: dead at enqueue
    assert ctrl.stats()["discarded_dup"] == 1
    assert ctrl.drain() == 0                                        # queue drains to empty
    assert not _spans(fake, "finalize")                             # F5: rejected final never finalizes
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="shown tail", expected_caret=10, expected_edits=1)
    assert fake.begun.count("show") == 1                            # shown tail preserved, untouched
    assert ctrl.stats()["queue_depth"] == 0
    assert ctrl.is_active() is True                                 # a boundary close is not a stop


def test_trace_07_repeated_cancel(_no_legacy_backend):
    """R.7 trace 7 — repeated cancel through the controller seam: 1st ⇒ ONE
    target.cancel APPLIED + pending discarded + STILL ACTIVE (mic armed);
    2nd ⇒ nothing pending, NO target call, edit flat (idempotent). NO
    press_backspace anywhere — R.5 forbids physical compensation in bulk."""
    fake = G2FakeTarget(seed_prefix="kept ")
    ctrl = _controller(fake)
    ctrl.on_partial("transient", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    assert fake.text == "kept transient" and fake.edit_count == 1
    assert ctrl.cancel() is True                                    # 1st cancel
    assert _spans(fake, "cancel") == [None]                         # exactly ONE cancel op
    assert fake.ops[-1] == ("cancel", None, None, ShowResult.APPLIED)
    assert fake.text == "kept "                                     # owned range removed: back to pre-utterance
    assert fake.caret == 5
    assert ctrl.is_active() is True                                 # mic stays armed
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="kept ", expected_caret=5, expected_edits=2)
    # canceled utterance's events are dead: late partial discards, no show
    ctrl.on_partial("transient", utterance="u1", seq=2, gen=1)
    assert ctrl.stats()["discarded_dup"] == 1
    assert ctrl.drain() == 0
    assert fake.begun.count("show") == 1
    # 2nd cancel: nothing pending ⇒ NO target call, no edit
    begun_before = fake.begun.count("cancel")
    assert ctrl.cancel() is True
    assert fake.begun.count("cancel") == begun_before
    assert fake.edit_count == 2                                     # flat
    assert sum(1 for op in fake.ops if op[0] == "cancel") == 1      # F4: no duplicate cancel
    assert ctrl.is_active() is True
    assert ctrl.stats()["expected_revision"] == 2                   # show APPLIED +1, cancel APPLIED +1


def test_trace_08_timeout_after_apply(_no_legacy_backend):
    """R.7 trace 8 — timeout-after-apply: ONE call, stop "op-deadline", the
    late APPLIED is DISCARDED — the controller's view froze even though the
    fake's field may show the edit (discarded ≠ not-happened)."""
    fake = G2FakeTarget()
    fake.gate = threading.Event()
    stopped: list[str] = []
    ctrl = _controller(fake, on_stopped=stopped.append)
    ctrl.on_partial("slow", utterance="u1", seq=1, gen=1)
    assert ctrl._process_next() is True             # the SessionBegin barrier
    assert ctrl._process_next() is True             # the give-up IS the dispatch
    assert ctrl.stats()["stopped_reason"] == "op-deadline"
    assert ctrl.stats()["deadline_exceeded"] == 1
    assert ctrl.is_active() is False
    assert stopped == ["op-deadline"]                               # on_stopped exactly once
    assert fake.begun.count("show") == 1                            # ONE target call, no retry
    assert fake.ops == []                                           # nothing completed yet
    assert ctrl.confirmed_visible() == ""                           # controller view FROZEN
    assert ctrl.stats()["expected_revision"] == 0
    assert ctrl.stats()["applied"] == 0
    fake.gate.set()                                                 # the op completes late…
    assert _wait_until(lambda: ctrl.stats()["late_results_discarded"] == 1)
    # …the FAKE shows the edit, the CONTROLLER never consumed it (Critical #5):
    assert fake.ops == [("show", "slow", 0, ShowResult.APPLIED)]
    assert fake.text == "slow" and fake.edit_count == 1
    assert ctrl.confirmed_visible() == ""                           # still frozen
    assert ctrl.latest_recognized() == "slow"                       # recognition retained (R.5)
    assert ctrl.stats()["expected_revision"] == 0 and ctrl.stats()["applied"] == 0
    assert stopped == ["op-deadline"]
    assert ctrl.drain() == 0                                        # no retry, no further calls
    assert fake.begun.count("show") == 1
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_edits=None)  # fake's field intentionally shows the edit


def test_trace_09_held_key(_no_legacy_backend):
    """R.7 trace 9 — held key (target refuses): stop "refused", on_stopped
    once, NO retry, the queued op behind it never dispatched, edits frozen."""
    fake = G2FakeTarget()
    fake.refuse_after = 0                                           # refuse EVERY mutating op
    stopped: list[str] = []
    ctrl = _controller(fake, on_stopped=stopped.append)
    ctrl.on_partial("held", utterance="u1", seq=1, gen=1)
    ctrl.on_partial("queued-behind", utterance="u2", seq=1, gen=1)  # queued, different utterance
    assert ctrl.drain() == 2                        # SessionBegin barrier + the refused op
    assert fake.begun.count("show") == 1                            # ONE op — never retried
    assert fake.ops[0] == ("show", "held", 0, ShowResult.REFUSED)
    assert fake.edit_count == 0                                     # a refusal mutates nothing
    assert ctrl.stats()["stopped_reason"] == "refused"
    assert stopped == ["refused"]                                   # on_stopped exactly once
    assert ctrl.is_active() is False
    assert ctrl.latest_recognized() == "queued-behind"              # newest RECEIVED at enqueue, retained
    assert ctrl.drain() == 0                                        # queued item: dead, never dispatched
    assert fake.begun.count("show") == 1                            # ZERO post-stop calls (F5/F6)
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="", expected_caret=0, expected_edits=0)


def test_trace_10_out_of_order_results(_no_legacy_backend):
    """R.7 trace 10 — out-of-order results: a stale gen1 op resolves AFTER
    stop + re-arm(gen2); gen2 APPLIES; the stale result can never touch gen2."""
    fake = G2FakeTarget()
    fake.gate = threading.Event()
    ctrl = _controller(fake)
    ctrl.on_partial("stale", utterance="a", seq=1, gen=1)
    assert ctrl._process_next() is True             # the SessionBegin barrier
    assert ctrl._process_next() is True             # deadline give-up; op still in flight
    assert ctrl.stats()["stopped_reason"] == "op-deadline"
    fake.gate.set()                                                 # stale gen1 result resolves LAST
    assert _wait_until(lambda: ctrl.stats()["late_results_discarded"] == 1)
    fake.gate = None
    assert ctrl.acquire() is True                                   # fresh lifetime
    assert ctrl.arm(2) is True                                      # generation bump
    ctrl.on_partial("fresh", utterance="b", seq=1, gen=2)
    ctrl.drain()
    # dispatch order was stale-then-fresh; BOTH applies are real field writes
    # (Critical #5: discarded ≠ not-happened) — gen2's write replaces the owned
    # range the stale op created, so the field shows exactly "fresh" ONCE,
    # while the CONTROLLER consumed only gen2's result (revision 1, not 2).
    assert [op[1] for op in fake.ops] == ["stale", "fresh"]
    assert fake.ops[0] == ("show", "stale", 0, ShowResult.APPLIED)
    assert fake.ops[1] == ("show", "fresh", 0, ShowResult.APPLIED)
    assert fake.text == "fresh" and "stale" not in fake.text
    assert fake.text.count("fresh") == 1                            # F4 no duplicate writes
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="fresh", expected_caret=5, expected_edits=2)
    assert ctrl.confirmed_visible() == "fresh"                      # gen2's, never gen1's
    assert ctrl.stats()["expected_revision"] == 1                   # exactly one consumed apply
    assert ctrl.stats()["late_results_discarded"] == 1
    assert ctrl.latest_recognized() == "fresh"


def test_trace_11_stop_and_immediate_rearm(_no_legacy_backend):
    """R.7 trace 11 — stop + immediate re-arm: leave() exactly once (and
    leave NEVER mutates), gen2 flows, gen1 stragglers die at dispatch AND at
    enqueue."""
    fake = G2FakeTarget()
    stopped: list[str] = []
    ctrl = _controller(fake, on_stopped=stopped.append)
    ctrl.on_partial("first", utterance="a", seq=1, gen=1)
    ctrl.drain()
    ctrl.on_partial("zombie", utterance="z", seq=1, gen=1)          # queued, gen1 never drained
    ctrl.stop()
    assert fake.leave_calls == 1                                    # leave exactly once
    assert stopped == []                                            # a normal stop fires no fault seam
    assert fake.edit_count == 1                                     # F5: leave preserved, zero writes
    assert ctrl.acquire() is True
    assert ctrl.arm(2) is True
    ctrl.on_partial("second", utterance="b", seq=1, gen=2)
    assert ctrl.drain() == 3                                        # zombie→stale, barrier, gen2 show
    assert [op[1] for op in fake.ops] == ["first", "second"]        # "zombie" NEVER reached the target
    assert ctrl.stats()["discarded_stale"] >= 1                     # discarded at DISPATCH
    before = ctrl.stats()["discarded_stale"]
    ctrl.on_partial("late1", utterance="c", seq=9, gen=1)           # and at ENQUEUE
    assert ctrl.stats()["discarded_stale"] == before + 1
    assert ctrl.drain() == 0
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="second", expected_caret=6, expected_edits=2,
              max_writers=2)  # fresh op-runner per delivery lifetime (S2): one writer per LIFETIME
    assert fake.leave_calls == 1                                    # still exactly one leave
    assert ctrl.confirmed_visible() == "second"


def test_trace_12_child_death(_no_legacy_backend):
    """R.7 trace 12 — child death: target.show raises → stop "target-error",
    nothing escapes drain(), stop()'s leave() on the dead target is wrapped,
    no further calls."""
    fake = G2FakeTarget()
    fake.raise_exc = ConnectionError("child died")
    stopped: list[str] = []
    ctrl = _controller(fake, on_stopped=stopped.append)
    ctrl.on_partial("boom", utterance="u1", seq=1, gen=1)
    assert ctrl.drain() == 2                                        # barrier + raising op; nothing escapes
    assert ctrl.stats()["stopped_reason"] == "target-error"
    assert ctrl.stats()["target_errors"] == 1
    assert ctrl.stats()["last_target_error"] == "ConnectionError"
    assert stopped == ["target-error"]                              # on_stopped exactly once
    assert fake.begun.count("show") == 1                            # no retry (R.5)
    assert fake.edit_count == 0                                     # the edit never landed
    fake.raise_on_leave = True                                      # leave on the dead target raises too…
    ctrl.stop()                                                     # …and must be swallowed
    assert fake.leave_calls == 1                                    # attempted exactly once
    ctrl.stop()
    assert fake.leave_calls == 1                                    # idempotent
    assert ctrl.drain() == 0
    assert fake.begun.count("show") == 1                            # F6: zero post-stop calls
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text="", expected_caret=0, expected_edits=0)


def test_trace_13_focus_change_mid_operation(_no_legacy_backend):
    """R.7 trace 13 — focus change mid-operation: the target flips REFUSED
    between accept and apply; the op queued behind it is re-checked at
    mutation time ⇒ NEVER dispatched; no post-takeover mutations."""
    fake = G2FakeTarget(seed_prefix=">> ")
    fake.refuse_after = 1                                           # focus lost after the 1st apply
    stopped: list[str] = []
    ctrl = _controller(fake, on_stopped=stopped.append)
    ctrl.on_partial("kept", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    ctrl.on_partial("refused", utterance="u2", seq=1, gen=1)
    ctrl.on_partial("queued-behind", utterance="u3", seq=1, gen=1)
    ctrl.drain()
    assert [op[1] for op in fake.ops] == ["kept", "refused"]        # u3 NEVER reached the target
    assert fake.ops[1] == ("show", "refused", 1, ShowResult.REFUSED)
    assert fake.edit_count == 1                                     # frozen at the refusal
    assert ctrl.stats()["stopped_reason"] == "refused"
    assert stopped == ["refused"]
    assert ctrl.is_active() is False
    assert ctrl.drain() == 0
    assert [op[1] for op in fake.ops] == ["kept", "refused"]        # F6: zero post-stop mutations
    _families(fake, ctrl, legacy_calls=_no_legacy_backend,
              expected_text=">> kept", expected_caret=3 + 4, expected_edits=1)
    assert ctrl.latest_recognized() == "queued-behind"              # newest RECEIVED, retained


# ---------------------------------------------------------------------------
# THE GATE-VERDICT SUMMARY — machine-checked matrix coverage (research §2b)
# ---------------------------------------------------------------------------


def test_g2_gate_summary():
    """The gate record's "13/13" is MACHINE-CHECKED, not hand-claimed: this
    module must carry exactly one test per frozen R.7 trace name, in order."""
    present = {name for name in globals() if name.startswith("test_trace_")}
    assert len(_TRACE_NAMES) == 13, "the frozen matrix must hold exactly R.7's 13 traces"
    assert present == set(_TRACE_NAMES), (
        f"matrix drift — missing: {sorted(set(_TRACE_NAMES) - present)}, "
        f"extra: {sorted(present - set(_TRACE_NAMES))}"
    )
