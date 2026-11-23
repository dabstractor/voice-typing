"""tests/test_bulk_controller.py — deterministic fake-target tests for the
P1.M3.T2.S1 ordering core (BulkController).

Everything is driven through the SAME dispatch handler the writer thread
runs (_process_next/drain) — no timing races, no sleeps for synchronization
(the one-writer probe is the single dedicated real-thread test). The
_FakeTarget records every call as (method, session, utterance, seq, rev,
span, thread-ident) with per-call programmable ShowResults.

Matrix (research §3): A delivery traces · B ordering invariants · C purity.
"""
from __future__ import annotations

import collections
import re
import threading
import time
from pathlib import Path

import voice_typing.bulk_controller as bc
from voice_typing.bulk_controller import BulkController
from voice_typing.bulk_delivery import AcquireResult, ShowResult

GEN = 1

Call = collections.namedtuple("Call", "method session utterance seq rev span ident")

# ---------------------------------------------------------------------------
# _FakeTarget + helpers
# ---------------------------------------------------------------------------


class _FakeTarget:
    """In-process DeliveryTarget double: records calls, per-call results."""

    def __init__(self, results=(), acquire_revision=0):
        self.calls: list[Call] = []
        self.acquire_result = AcquireResult(ok=True, handle="fake", revision=acquire_revision)
        self._results = list(results)
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def _next_result(self) -> ShowResult:
        with self._lock:
            return self._results.pop(0) if self._results else ShowResult.APPLIED

    def _record(self, call: Call) -> None:
        with self._lock:
            self.calls.append(call)
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)

    def _finish(self) -> None:
        with self._lock:
            self._in_flight -= 1

    def acquire(self) -> AcquireResult:
        self.calls.append(Call("acquire", 0, "", 0, 0, "", threading.get_ident()))
        return self.acquire_result

    def show(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        self._record(Call("show", session, utterance, seq, expected_revision, span,
                          threading.get_ident()))
        time.sleep(0.002)  # widen the race window for the one-writer probe
        self._finish()
        return self._next_result()

    def finalize(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        self._record(Call("finalize", session, utterance, seq, expected_revision, span,
                          threading.get_ident()))
        time.sleep(0.002)
        self._finish()
        return self._next_result()

    def leave(self) -> None:
        self.calls.append(Call("leave", 0, "", 0, 0, "", threading.get_ident()))

    def cancel(self) -> ShowResult:  # not used by the controller (S2/later)
        return ShowResult.APPLIED


def _controller(results=(), acquire_revision=0, **kw):
    fake = _FakeTarget(results=results, acquire_revision=acquire_revision)
    ctrl = BulkController(fake, **kw)
    return ctrl, fake


def _armed(results=(), acquire_revision=0, gen=GEN, **kw):
    ctrl, fake = _controller(results=results, acquire_revision=acquire_revision, **kw)
    assert ctrl.acquire() is True
    assert ctrl.arm(gen) is True
    return ctrl, fake


def _methods(fake):
    return [c.method for c in fake.calls]


def _spans(fake, method="show"):
    return [c.span for c in fake.calls if c.method == method]


# ---------------------------------------------------------------------------
# A. Delivery traces
# ---------------------------------------------------------------------------


def test_append_first_partial_one_show_applied_and_revision_advances():
    ctrl, fake = _armed()
    ctrl.on_partial("hello", utterance="u1", seq=1, gen=GEN)
    assert ctrl.drain() == 2  # SessionBegin barrier + the partial
    assert _spans(fake) == ["hello"]
    st = ctrl.stats()
    assert st["applied"] == 1 and st["expected_revision"] == 1
    assert ctrl.is_active() is True


def test_acquire_failure_leaves_delivery_inactive():
    ctrl, fake = _controller()
    fake.acquire_result = AcquireResult(ok=False, reason="password-secret")
    assert ctrl.acquire() is False
    assert ctrl.is_active() is False
    assert ctrl.stats()["stopped_reason"] == "password-secret"


def test_extend_updates_two_shows_exact_spans():
    ctrl, fake = _armed()
    ctrl.on_partial("hello wor", utterance="u1", seq=1, gen=GEN)
    ctrl.drain()
    ctrl.on_partial("hello world", utterance="u1", seq=2, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["hello wor", "hello world"]


def test_first_word_change_sends_one_new_complete_span():
    ctrl, fake = _armed()
    ctrl.on_partial("Hello world", utterance="u1", seq=1, gen=GEN)
    ctrl.drain()
    ctrl.on_partial("Help world", utterance="u1", seq=2, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["Hello world", "Help world"]  # NEW complete span


def test_identical_update_makes_zero_target_calls():
    ctrl, fake = _armed()
    ctrl.on_partial("hello", utterance="u1", seq=1, gen=GEN)
    ctrl.drain()  # first partial dispatches: ONE show
    ctrl.on_partial("hello", utterance="u1", seq=2, gen=GEN)  # render-equal
    ctrl.drain()
    assert _spans(fake) == ["hello"]  # exactly ONE show total
    assert ctrl.stats()["zero_diff_skipped"] == 1
    assert ctrl.drain() == 0  # nothing queued left


def test_render_equal_whitespace_skips_but_case_differs_is_real():
    ctrl, fake = _armed()
    ctrl.on_partial("a  b", utterance="u1", seq=1, gen=GEN)
    ctrl.drain()
    ctrl.on_partial("a b", utterance="u1", seq=2, gen=GEN)  # equal after spacing guard
    ctrl.drain()
    ctrl.on_partial("Hi", utterance="u2", seq=1, gen=GEN)
    ctrl.drain()
    ctrl.on_partial("hi", utterance="u2", seq=2, gen=GEN)  # case = REAL diff
    ctrl.drain()
    assert _spans(fake) == ["a  b", "Hi", "hi"]
    assert ctrl.stats()["zero_diff_skipped"] == 1


def test_retraction_delivers_the_shorter_span():
    ctrl, fake = _armed()
    ctrl.on_partial("hello world", utterance="u1", seq=1, gen=GEN)
    ctrl.drain()
    ctrl.on_partial("hello", utterance="u1", seq=2, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["hello world", "hello"]


def test_unicode_spans_flow_byte_exact():
    ctrl, fake = _armed()
    ctrl.on_partial("naïve café 😀", utterance="u1", seq=1, gen=GEN)
    ctrl.on_final("naïve café 😀 — résumé", utterance="u1", seq=2, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["naïve café 😀"]
    assert _spans(fake, "finalize") == ["naïve café 😀 — résumé"]  # no normalization


def test_final_closes_utterance_after_partial():
    ctrl, fake = _armed()
    ctrl.on_partial("hello wor", utterance="u1", seq=1, gen=GEN)
    ctrl.on_final("hello world", utterance="u1", seq=2, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["hello wor"]
    assert _spans(fake, "finalize") == ["hello world"]
    assert ctrl.stats()["expected_revision"] == 2  # both applied
    ctrl.on_partial("late", utterance="u1", seq=3, gen=GEN)  # post-final → dead
    assert ctrl.drain() == 0
    assert len(_spans(fake)) == 1


# ---------------------------------------------------------------------------
# B. Ordering invariants
# ---------------------------------------------------------------------------


def test_newest_wins_three_partials_one_show():
    ctrl, fake = _armed()
    ctrl.on_partial("one", utterance="u1", seq=1, gen=GEN)
    ctrl.on_partial("one two", utterance="u1", seq=2, gen=GEN)
    ctrl.on_partial("one two three", utterance="u1", seq=3, gen=GEN)
    assert ctrl.drain() == 2  # SessionBegin barrier + the ONE coalesced partial
    assert _spans(fake) == ["one two three"]  # ONE show, seq-3 text
    assert ctrl.stats()["coalesced"] == 2


def test_coalesced_partial_keeps_position_before_its_final():
    ctrl, fake = _armed()
    ctrl.on_partial("hello", utterance="u1", seq=1, gen=GEN)
    ctrl.on_final("hello world", utterance="u1", seq=2, gen=GEN)
    ctrl.on_partial("next", utterance="u2", seq=1, gen=GEN)
    ctrl.drain()
    assert _methods(fake) == ["acquire", "show", "finalize", "show"]
    assert _spans(fake) == ["hello", "next"]
    assert _spans(fake, "finalize") == ["hello world"]


def test_late_post_final_partial_discarded():
    ctrl, fake = _armed()
    ctrl.on_final("done", utterance="u1", seq=2, gen=GEN)
    ctrl.on_partial("late", utterance="u1", seq=3, gen=GEN)
    ctrl.drain()
    assert _methods(fake) == ["acquire", "finalize"]
    assert ctrl.stats()["discarded_dup"] == 1


def test_duplicate_final_discarded():
    ctrl, fake = _armed()
    ctrl.on_final("f1", utterance="u1", seq=1, gen=GEN)
    ctrl.on_final("f2", utterance="u1", seq=2, gen=GEN)  # duplicate
    ctrl.drain()
    assert _spans(fake, "finalize") == ["f1"]
    assert ctrl.stats()["discarded_dup"] == 1


def test_stale_generation_discarded_at_enqueue_and_at_dispatch():
    ctrl, fake = _armed(gen=1)
    ctrl.on_partial("old", utterance="u1", seq=1, gen=1)  # queued, gen 1
    ctrl.arm(2)  # new session generation
    ctrl.on_partial("straggler", utterance="u2", seq=1, gen=1)  # enqueue-side discard
    ctrl.on_partial("fresh", utterance="u3", seq=1, gen=2)
    ctrl.drain()
    # The queued gen-1 partial AND the stale gen-1 SessionBegin barrier both
    # dispatch BEFORE the gen-2 barrier and must be discarded at MUTATION time
    # by the writer's gen re-check, alongside the enqueue-side straggler.
    assert _spans(fake) == ["fresh"]
    assert ctrl.stats()["discarded_stale"] == 3


def test_dropped_final_closes_boundary_without_finalize():
    ctrl, fake = _armed()
    ctrl.on_partial("hello", utterance="u1", seq=1, gen=GEN)
    ctrl.on_final_dropped(utterance="u1", gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["hello"]
    assert _methods(fake).count("finalize") == 0  # NO finalize, ever
    ctrl.on_partial("more", utterance="u1", seq=2, gen=GEN)  # boundary closed
    ctrl.drain()
    assert len(_spans(fake)) == 1
    assert ctrl.stats()["discarded_dup"] == 1


def test_queue_overflow_stops_delivery_barrier_variant():
    ctrl, fake = _controller(queue_size=4)
    ctrl.acquire()
    ctrl.arm(GEN)
    ctrl.drain()  # dispatch the SessionBegin barrier so the queue starts empty
    for i in range(4):  # fill the queue with undelivered partials
        ctrl.on_partial(f"t{i}", utterance=f"u{i}", seq=1, gen=GEN)
    assert ctrl.is_active() is True
    ctrl.on_final("barrier", utterance="u9", seq=1, gen=GEN)  # overflow → STOP
    assert ctrl.is_active() is False
    st = ctrl.stats()
    assert st["stopped_reason"] == "queue-overflow" and st["overflow"] == 1
    assert ctrl.drain() == 0  # nothing dropped-and-continued: NOTHING dispatches
    assert _methods(fake) == ["acquire"]  # writer never touched the target
    ctrl.on_partial("late", utterance="u10", seq=1, gen=GEN)  # post-stop rejected
    assert ctrl.drain() == 0
    assert _methods(fake) == ["acquire"]


def test_queue_overflow_stops_delivery_partial_variant():
    ctrl, fake = _controller(queue_size=4)
    ctrl.acquire()
    ctrl.arm(GEN)
    ctrl.drain()  # dispatch the SessionBegin barrier so the queue starts empty
    for i in range(4):
        ctrl.on_partial(f"t{i}", utterance=f"u{i}", seq=1, gen=GEN)
    ctrl.on_partial("t5", utterance="u5", seq=1, gen=GEN)  # partial overflows too
    assert ctrl.is_active() is False
    assert ctrl.stats()["stopped_reason"] == "queue-overflow"
    assert _methods(fake) == ["acquire"]


def test_refused_stops_delivery_without_retry():
    stopped = []
    ctrl, fake = _controller(results=[ShowResult.REFUSED], on_stopped=stopped.append)
    ctrl.acquire()
    ctrl.arm(GEN)
    ctrl.on_partial("x", utterance="u1", seq=1, gen=GEN)
    ctrl.on_partial("y", utterance="u2", seq=1, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["x"]  # exactly one attempt — NO retry
    assert ctrl.is_active() is False
    assert ctrl.stats()["stopped_reason"] == "refused"
    assert stopped == ["refused"]  # seam fired exactly once
    assert ctrl.stats()["expected_revision"] == 0  # refused = no advance
    ctrl.drain()  # the second partial never reached the target
    assert len(fake.calls) == 2  # acquire + the single refused show


def test_unknown_stops_delivery_without_retry():
    stopped = []
    ctrl, fake = _controller(results=[ShowResult.UNKNOWN], on_stopped=stopped.append)
    ctrl.acquire()
    ctrl.arm(GEN)
    ctrl.on_partial("x", utterance="u1", seq=1, gen=GEN)
    ctrl.on_partial("y", utterance="u2", seq=1, gen=GEN)
    ctrl.drain()
    assert _spans(fake) == ["x"]
    assert ctrl.is_active() is False
    assert ctrl.stats()["stopped_reason"] == "unknown"
    assert stopped == ["unknown"]
    assert len(fake.calls) == 2  # no retry, no further target calls


def test_unchanged_continues_without_revision_bump():
    ctrl, fake = _controller(results=[ShowResult.APPLIED, ShowResult.UNCHANGED])
    ctrl.acquire()
    ctrl.arm(GEN)
    ctrl.on_partial("alpha", utterance="u1", seq=1, gen=GEN)
    ctrl.on_partial("beta", utterance="u2", seq=1, gen=GEN)  # target says unchanged
    ctrl.drain()
    ctrl.on_partial("beta", utterance="u2", seq=2, gen=GEN)  # identical-after-UNCHANGED
    ctrl.drain()
    assert _spans(fake) == ["alpha", "beta"]  # third was a zero-diff SKIP
    st = ctrl.stats()
    assert st["expected_revision"] == 1  # UNCHANGED never advances
    assert st["unchanged"] == 1 and st["zero_diff_skipped"] == 1
    assert ctrl.is_active() is True  # delivery CONTINUES


def test_expected_revision_advances_only_on_applied():
    ctrl, fake = _controller(
        results=[ShowResult.APPLIED, ShowResult.UNCHANGED, ShowResult.APPLIED],
        acquire_revision=5,
    )
    ctrl.acquire()
    ctrl.arm(GEN)
    ctrl.on_partial("a", utterance="u1", seq=1, gen=GEN)   # applied: 5 -> 6
    ctrl.on_partial("b", utterance="u2", seq=1, gen=GEN)   # unchanged: stays 6
    ctrl.on_partial("c", utterance="u3", seq=1, gen=GEN)   # applied: 6 -> 7
    ctrl.drain()
    revs = [c.rev for c in fake.calls if c.method == "show"]
    assert revs == [5, 6, 6]  # seeded 5; +1 after applied; UNCHANGED frozen
    assert ctrl.stats()["expected_revision"] == 7


def test_one_writer_thread_serializes_every_target_call():
    ctrl, fake = _controller()
    ctrl.acquire()
    ctrl.arm(3)
    n = 20
    for i in range(n):  # distinct utterances → nothing coalesces
        ctrl.on_partial(f"span {i}", utterance=f"u{i:02d}", seq=1, gen=3)
    ctrl.start()
    deadline = time.monotonic() + 10
    while sum(1 for c in fake.calls if c.method == "show") < n:
        if time.monotonic() > deadline:
            raise AssertionError("writer thread never drained the queue")
        time.sleep(0.002)
    ctrl.stop()
    shows = [c for c in fake.calls if c.method == "show"]
    assert len(shows) == n
    idents = {c.ident for c in shows}
    assert len(idents) == 1  # every target call on ONE thread
    assert idents != {threading.main_thread().ident}  # not the caller's thread
    assert fake.max_in_flight == 1  # strictly one operation in flight


def test_arm_resets_generation_state_and_discards_stragglers():
    ctrl, fake = _armed(gen=1)
    ctrl.on_partial("old", utterance="u1", seq=1, gen=1)
    ctrl.drain()
    assert _spans(fake) == ["old"]
    ctrl.arm(2)
    ctrl.on_partial("straggler", utterance="u1", seq=2, gen=1)  # old gen → dead
    ctrl.on_partial("new", utterance="u1", seq=1, gen=2)  # same name, NEW gen: fresh state
    ctrl.drain()
    assert _spans(fake) == ["old", "new"]
    assert ctrl.stats()["discarded_stale"] == 1


def test_stop_leaves_target_exactly_once_and_rejects_later_events():
    ctrl, fake = _armed()
    ctrl.on_partial("x", utterance="u1", seq=1, gen=GEN)
    ctrl.drain()
    ctrl.stop()
    ctrl.stop()  # idempotent
    assert _methods(fake).count("leave") == 1  # exactly once
    assert ctrl.is_active() is False
    ctrl.on_partial("y", utterance="u2", seq=1, gen=GEN)  # post-stop → rejected
    ctrl.drain()
    assert _spans(fake) == ["x"]  # no post-stop target calls


# ---------------------------------------------------------------------------
# C. Purity guards (d2 §3)
# ---------------------------------------------------------------------------


def test_module_exposes_no_typing_fallback_surface():
    for bad in ("type_text", "type_character", "press_backspace", "make_backend",
                "StreamingOutput"):
        assert not hasattr(bc, bad), f"bulk_controller must never expose {bad}"


def test_source_never_imports_engine_modules_and_stays_stdlib():
    src = Path(bc.__file__).read_text(encoding="utf-8")
    for dotted in ("voice_typing.streaming", "voice_typing.typing_backends",
                   "voice_typing.daemon"):
        assert dotted not in src, f"bulk_controller must not reference {dotted}"
    assert not re.search(
        r"import\s+(voice_typing\.)?(streaming|typing_backends|daemon)\b", src
    ), "bulk_controller must not import the engine modules"
    tops = set(re.findall(r"^from\s+([\w.]+)", src, re.M)) | set(
        re.findall(r"^import\s+([\w.]+)", src, re.M)
    )
    allowed = {"__future__", "collections", "dataclasses", "logging", "threading",
               "voice_typing.bulk_delivery"}
    assert tops <= allowed, f"unexpected imports: {tops - allowed}"
