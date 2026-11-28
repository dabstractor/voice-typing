"""P1.M1.T4.S3 — recorder identity safe at capture boundaries (hermetic, NO media/model/device).

Rules under test (D1-D5 + reader responsiveness + the preserved orderings):
  D1  an id-less event reports (None, None) — never the previous event's identity.
  D2  a cold (re-spawned) host's tracker resets at "ready" (reader thread).
  D3  each reader fences events by its captured generation; an old reader's straggler is dropped.
  D4  capture_boundary opens at the identified speech event, closes on EVERY final path.
  D5  arm_seq bumps once per arm (set_microphone(True)) and latches per session.
Plus: text() unblocks on a dropped duplicate WITHOUT relaying it, and _final_evt is set
AFTER on_final returns, not before (the :744-745 ordering, preserved).

Harness shape copied verbatim from tests/test_recorder_host.py :33-82 (do NOT import it).
"""

import queue
import threading

from voice_typing import recorder_host
from voice_typing.recorder_host import FinalClass, _RelayIds, _emit_speech


class _FakeFeedback:
    """Records set_phase calls (the host reader thread drives Feedback.set_phase on vad events)."""

    def __init__(self) -> None:
        self.phases: list[str] = []
        self.partials: list[str] = []

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def update_partial(self, text: str) -> None:
        self.partials.append(text)


class _FakeLatency:
    """Records note_speech_end / note_partial calls (the host reader drives LatencyLog)."""

    def __init__(self) -> None:
        self.speech_ends = 0
        self.partials = 0

    def note_speech_end(self) -> None:
        self.speech_ends += 1

    def note_partial(self, _text: str) -> None:
        self.partials += 1


def _make_host(
    *, on_final=None, on_partial=None, on_speech=None, force_cpu=False, partial_source="stabilized"
) -> recorder_host.RecorderHost:
    """Build a RecorderHost with fake callbacks + a dummy cfg (the host does not spawn in tests)."""
    cfg = object()  # the host stores but never inspects cfg in the dispatch path
    return recorder_host.RecorderHost(
        cfg,  # type: ignore[arg-type]
        _FakeFeedback(),  # type: ignore[arg-type]
        _FakeLatency(),  # type: ignore[arg-type]
        on_final or (lambda _t: None),
        on_partial or (lambda _t: None),
        on_speech or (lambda: None),
        force_cpu=force_cpu,
        partial_source=partial_source,
    )


def _feed_event(host: recorder_host.RecorderHost, kind: str, payload: dict | None = None) -> None:
    """Put a canned event on the host's event_queue (as if the child sent it)."""
    host._evt_q.put((kind, payload or {}))


# ---------------------------------------------------------------------------
# D1 — identity cleared on id-less events
# ---------------------------------------------------------------------------


def test_idless_event_clears_identity_and_reports_unidentified():
    """D1: an id-less final/partial reports (None, None) and UNIDENTIFIED — never the previous
    event's identity (the old conditional assignment latched it through)."""
    seen_final: list[tuple] = []
    seen_partial: list[tuple] = []
    host = _make_host(
        on_final=lambda t: seen_final.append((t, host.relay_identity, host.relay_event)),
        on_partial=lambda t: seen_partial.append((t, host.relay_identity, host.relay_event)),
    )
    host._final_evt.clear()
    host._dispatch("final", {"text": "one", "utterance_id": 7, "session_gen": 2})
    host._final_evt.clear()
    host._dispatch("final", {"text": "two"})  # id-less
    assert seen_final[0] == ("one", (2, 7),
                             ("final", FinalClass.ACCEPTED, 0, 0, 2, 7))
    assert seen_final[1][1] == (None, None), "id-less final must report (None, None)"
    assert seen_final[1][2] == ("final", FinalClass.UNIDENTIFIED, host.generation,
                                host.arm_seq, None, None)
    host._dispatch("partial", {"text": "he", "utterance_id": 8, "session_gen": 3})
    host._dispatch("partial", {"text": "lo"})  # id-less
    assert seen_partial[0][1] == (3, 8)
    assert seen_partial[1][1] == (None, None), "id-less partial must report (None, None)"
    assert seen_partial[1][2] == ("partial", None, host.generation, host.arm_seq, None, None)


# ---------------------------------------------------------------------------
# (b) — final classes are mutually distinguishable
# ---------------------------------------------------------------------------


def test_final_classes_are_distinguishable():
    """(b): accepted / sentinel / cancelled / unidentified / duplicate / stale are told apart via
    relay_event.final_class; duplicates and stale never reach on_final yet set _final_evt."""
    relayed: list[str] = []

    h1 = _make_host(on_final=relayed.append)
    h1._final_evt.clear()
    h1._dispatch("final", {"text": "hi", "utterance_id": 1, "session_gen": 1})
    assert h1.relay_event.final_class is FinalClass.ACCEPTED

    h2 = _make_host(on_final=relayed.append)
    h2._final_evt.clear()
    h2._dispatch("final", {"text": "", "utterance_id": 1, "session_gen": 1})
    assert h2.relay_event.final_class is FinalClass.SENTINEL

    h3 = _make_host(on_final=relayed.append)
    h3._final_evt.clear()
    h3._dispatch("final", {"text": "", "cancelled": True, "utterance_id": 1, "session_gen": 1})
    assert h3.relay_event.final_class is FinalClass.CANCELLED

    h4 = _make_host(on_final=relayed.append)
    h4._final_evt.clear()
    h4._dispatch("final", {"text": "legacy"})  # no uid -> UNIDENTIFIED, still relayed
    assert h4.relay_event.final_class is FinalClass.UNIDENTIFIED
    assert relayed == ["hi", "", "", "legacy"], "all four relayable finals must reach on_final"

    h5_finals: list[str] = []
    h5 = _make_host(on_final=h5_finals.append)
    h5._final_evt.clear()
    h5._dispatch("final", {"text": "a", "utterance_id": 1, "session_gen": 1})
    h5._final_evt.clear()
    h5._dispatch("final", {"text": "a", "utterance_id": 1, "session_gen": 1})  # DUPLICATE
    assert h5_finals == ["a"], "duplicate final must NOT re-fire on_final"
    assert h5._final_evt.is_set(), "dropped duplicate must still set _final_evt (VT-007)"
    assert h5.relay_event.final_class is FinalClass.DUPLICATE
    h5._final_evt.clear()
    h5._dispatch("final", {"text": "old", "utterance_id": 2, "session_gen": 0})  # STALE (0 < 1)
    assert h5_finals == ["a"], "stale final must NOT reach on_final"
    assert h5._final_evt.is_set(), "dropped stale final must still set _final_evt (VT-007)"
    assert h5.relay_event.final_class is FinalClass.STALE


# ---------------------------------------------------------------------------
# D2 — cold-host reset at "ready" (reader thread)
# ---------------------------------------------------------------------------


def test_cold_host_ready_resets_tracker():
    """D2: the reader's "ready" resets ALL tracker state — the previous child's settled ids and
    session_gen can neither drop nor advance the new child's events."""
    finals: list[str] = []
    host = _make_host(on_final=finals.append)
    host._final_evt.clear()
    host._dispatch("final", {"text": "x", "utterance_id": 9, "session_gen": 5})
    assert list(host._ids_settled) == [9] and host._ids_latest_session == 5
    host._dispatch("ready", {"device": "cpu"})  # cold-host reset
    assert host._ids_latest_session == -1
    assert list(host._ids_settled) == [] and host._ids_settled_set == set()
    assert host._ids_open is None
    assert host.relay_identity == (None, None)
    assert host.relay_event is None
    assert host.capture_boundary is None
    host._final_evt.clear()
    host._dispatch("final", {"text": "y", "utterance_id": 1, "session_gen": 1})
    assert finals == ["x", "y"], "post-reset final must be relayed (old ids cannot drop it)"
    assert host._final_evt.is_set()


# ---------------------------------------------------------------------------
# D3 — per-reader generation fence
# ---------------------------------------------------------------------------


def test_previous_generation_events_are_fenced():
    """D3: a reader captures its generation at entry; an OLD reader's straggler after a respawn
    is dropped (no callback, no tracker advance, no _final_evt); the new reader relays."""
    partials: list[str] = []
    host = _make_host(on_partial=partials.append)
    host._generation = 1  # test-only poke: spawn() bumps BEFORE the reader starts
    host._dispatch("ready", {}, generation=1)  # reader A entry (cold reset)
    host._dispatch("partial", {"text": "he", "utterance_id": 4, "session_gen": 3}, generation=1)
    assert partials == ["he"]
    assert host.relay_event is not None and host.relay_event.host_generation == 1
    host._generation = 2  # "respawn": the spawner bumped the generation
    host._dispatch("ready", {}, generation=2)  # reader B entry (cold reset)
    host._dispatch("partial", {"text": "straggler", "utterance_id": 9, "session_gen": 9},
                   generation=1)  # OLD reader's straggler
    assert partials == ["he"], "an old-generation event must be fenced"
    assert host._ids_latest_session == -1, "a fenced straggler must not advance the tracker"
    assert not host._final_evt.is_set()
    host._dispatch("partial", {"text": "new", "utterance_id": 1, "session_gen": 1}, generation=2)
    assert partials == ["he", "new"]
    assert host.capture_boundary is not None and host.capture_boundary.host_generation == 2


# ---------------------------------------------------------------------------
# D5 — arm_seq bumps once per arm, latches per session
# ---------------------------------------------------------------------------


def test_arm_seq_bumps_once_per_arm_and_latches_per_session():
    """D5: set_microphone(True) bumps exactly once (disarm never bumps); the reader LATCHES the
    arm seq at session advance, so a previous arm's straggler keeps the previous arm_seq."""
    speeches: list[int] = []
    host = _make_host(on_speech=lambda: speeches.append(1))
    assert host.arm_seq == 0
    host.set_microphone(False)
    assert host.arm_seq == 0, "disarm must not bump"
    host.set_microphone(True)
    assert host.arm_seq == 1
    host._dispatch("speech", {"utterance_id": 1, "session_gen": 1})
    assert host.relay_event is not None and host.relay_event.arm_seq == 1
    assert host.capture_boundary is not None and host.capture_boundary.arm_seq == 1
    host.set_microphone(True)  # re-arm
    assert host.arm_seq == 2
    host._dispatch("partial", {"text": "he", "utterance_id": 1, "session_gen": 1})  # OLD session
    assert host.relay_event is not None and host.relay_event.arm_seq == 1, (
        "a same-session straggler must reuse the LATCHED arm_seq, not the current one"
    )
    host._dispatch("speech", {"utterance_id": 2, "session_gen": 2})  # NEW session
    assert host.relay_event is not None and host.relay_event.arm_seq == 2
    assert host.capture_boundary is not None and host.capture_boundary.arm_seq == 2
    assert speeches == [1, 1]


# ---------------------------------------------------------------------------
# D4 — capture boundary opens at speech, closes on EVERY final path
# ---------------------------------------------------------------------------


def test_boundary_opens_at_speech_and_closes_on_every_final_path():
    """D4/(e): the boundary opens at the identified speech event and closes at every final path —
    accepted, sentinel, filtered (raising on_final), duplicate-dropped; an id-less partial
    never moves it."""
    # (i) open at speech, close at the accepted final
    h1 = _make_host()
    h1._dispatch("speech", {"utterance_id": 3, "session_gen": 2})
    g, a = h1.generation, h1.arm_seq
    assert h1.capture_boundary == (g, a, 2, 3)
    assert h1._ids_open == 3
    assert h1.relay_identity == (2, 3)
    h1._final_evt.clear()
    h1._dispatch("final", {"text": "done", "utterance_id": 3, "session_gen": 2})
    assert h1.capture_boundary == (g, a, 2, None)

    # (ii) sentinel final closes
    h2 = _make_host()
    h2._dispatch("speech", {"utterance_id": 1, "session_gen": 1})
    h2._final_evt.clear()
    h2._dispatch("final", {"text": "", "utterance_id": 1, "session_gen": 1})
    assert h2.capture_boundary == (h2.generation, h2.arm_seq, 1, None)

    # (iii) a raising (filtered) on_final still closes
    def boom(_t: str) -> None:
        raise RuntimeError("filtered")

    h3 = _make_host(on_final=boom)
    h3._dispatch("speech", {"utterance_id": 1, "session_gen": 1})
    h3._final_evt.clear()
    h3._dispatch("final", {"text": "x", "utterance_id": 1, "session_gen": 1})
    assert h3._final_evt.is_set()
    assert h3.capture_boundary == (h3.generation, h3.arm_seq, 1, None)

    # (iv) duplicate final leaves it closed + sets _final_evt; id-less partial never moves it
    h4 = _make_host()
    h4._dispatch("speech", {"utterance_id": 1, "session_gen": 1})
    h4._dispatch("partial", {"text": "he"})  # id-less: boundary untouched
    assert h4.capture_boundary == (h4.generation, h4.arm_seq, 1, 1)
    h4._final_evt.clear()
    h4._dispatch("final", {"text": "y", "utterance_id": 1, "session_gen": 1})
    assert h4.capture_boundary == (h4.generation, h4.arm_seq, 1, None)
    h4._final_evt.clear()
    h4._dispatch("final", {"text": "y", "utterance_id": 1, "session_gen": 1})  # DUPLICATE
    assert h4._final_evt.is_set()
    assert h4.capture_boundary == (h4.generation, h4.arm_seq, 1, None), (
        "a dropped duplicate must leave the boundary closed"
    )


# ---------------------------------------------------------------------------
# D4 (source side) — _emit_speech stamps the rotated id
# ---------------------------------------------------------------------------


def test_emit_speech_is_stamped_and_legacy_default():
    """D4: the child's speech put carries the ROTATED id (the boundary opens at the decode
    source); ids=None keeps the legacy un-stamped payload, byte-identical to today."""
    q: "queue.Queue[tuple]" = queue.Queue()
    ids = _RelayIds()
    _emit_speech(q, ids)
    kind, payload = q.get_nowait()
    assert (kind, payload) == ("speech", {"utterance_id": 1, "session_gen": 0})
    _emit_speech(q, ids)
    kind, payload = q.get_nowait()
    assert (kind, payload) == ("speech", {"utterance_id": 2, "session_gen": 0})
    _emit_speech(q, None)
    kind, payload = q.get_nowait()
    assert (kind, payload) == ("speech", {}), "legacy speech put must stay un-stamped"


# ---------------------------------------------------------------------------
# text() responsiveness — dropped duplicate still unblocks (VT-007)
# ---------------------------------------------------------------------------


def test_text_unblocks_on_dropped_duplicate_without_callback():
    """host.text() must unblock when the only final is a DROPPED duplicate — and the duplicate
    must never reach on_final."""
    host = _make_host(on_final=lambda _t: None)  # a real callback would fail the assert below
    got: list[str] = []
    host._dispatch("final", {"text": "a", "utterance_id": 1, "session_gen": 1})  # settle uid 1
    host._final_evt.clear()

    reader = threading.Thread(target=host._read_loop, daemon=True)
    reader.start()
    t = threading.Thread(target=host.text, args=(got.append,), daemon=True)
    t.start()
    _feed_event(host, "final", {"text": "a", "utterance_id": 1, "session_gen": 1})  # DUPLICATE
    t.join(timeout=2.0)
    assert not t.is_alive(), "text() must unblock on a dropped duplicate"
    assert got == [], "the duplicate must NOT reach on_final"
    _feed_event(host, "gone", {})
    reader.join(timeout=2.0)
    assert not reader.is_alive()


# ---------------------------------------------------------------------------
# Ordering — _final_evt AFTER the callback (preserved)
# ---------------------------------------------------------------------------


def test_final_evt_set_after_callback_not_before():
    """The reader must set _final_evt only AFTER on_final returns (the :744-745 ordering)."""
    entered = threading.Event()
    gate = threading.Event()

    def blocking_final(_t: str) -> None:
        entered.set()
        gate.wait(timeout=5.0)

    host = _make_host(on_final=blocking_final)
    reader = threading.Thread(target=host._read_loop, daemon=True)
    reader.start()
    try:
        _feed_event(host, "final", {"text": "x", "utterance_id": 1, "session_gen": 1})
        assert entered.wait(timeout=2.0), "on_final never ran"
        assert not host._final_evt.is_set(), "_final_evt must NOT be set before on_final returns"
    finally:
        gate.set()
    host._final_evt.wait(timeout=2.0)
    assert host._final_evt.is_set()
    _feed_event(host, "gone", {})
    reader.join(timeout=2.0)


# ---------------------------------------------------------------------------
# (f) — legacy events relay unchanged, in order, tracker untouched
# ---------------------------------------------------------------------------


def test_legacy_events_relay_unchanged_in_order():
    """(f)/G7: id-less final then id-less partial relay to the same callbacks in order, report
    (None, None) both times, and leave the tracker untouched."""
    calls: list[str] = []
    host = _make_host(
        on_final=lambda t: calls.append(f"final:{t}"),
        on_partial=lambda t: calls.append(f"partial:{t}"),
    )
    host._final_evt.clear()
    host._dispatch("final", {"text": "done"})
    host._dispatch("partial", {"text": "he"})
    assert calls == ["final:done", "partial:he"]
    assert host.relay_identity == (None, None)
    assert host._ids_latest_session == -1
    assert list(host._ids_settled) == [] and host._ids_settled_set == set()
    assert host._ids_open is None
