"""tests/test_session_recovery.py — P1.M6.T2.S2: R.6 session recovery store + daemon wiring.

Two layers, fakes ONLY (no CUDA, no subprocess, no live desktop — AGENTS.md):

  Layer A — the pure store (voice_typing.session_recovery): EVERY exclusion rule of the
  R.6 contract gets a named test — exactly-once dedupe, rejected-final tail retention,
  cancel exclusion, late/post-disarm-event exclusion (closed-store ignores), empty/failed-
  arm survival + draft reset, the 2-sessions cap (eviction), the 1 MiB UTF-8 cap (whole
  oldest finals dropped first; a lone oversized item sliced at a codepoint boundary keeping
  its START), truncation reporting, clear-at-exit + reuse, and a bounded thread-safety smoke.

  Layer B — daemon wiring in BOTH delivery modes (stream-edit default + S1's bulk-text):
  the hook-placement precedents (listening gate, cancel-suppression window, rejected-final
  block) pinned through the public daemon surface (on_final/_on_partial/cancel/_disarm/
  request_shutdown) + the S3 contract point session_snapshot(). Stream-edit tests reuse
  test_daemon's fakes; bulk tests reuse test_bulk_dispatch's fixtures (identity host, fake
  bundle, spy backend, real BulkController).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py -q
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parent)
)  # sibling-test fixture imports

from voice_typing.session_recovery import (  # noqa: E402
    _MAX_SESSION_BYTES,
    _MAX_SESSIONS,
    CompletedSession,
    SessionRecovery,
)

import test_bulk_dispatch as tbd  # noqa: E402 — S1's bulk fixtures (identity host, fakes)
import test_daemon as td  # noqa: E402 — stream-edit fakes (_make_daemon, _fake_host_factory)

# ===========================================================================
# Layer A — the store: every R.6 exclusion rule + cap discipline
# ===========================================================================


def test_module_caps_are_code_constants():
    """R.6/G8: 2 sessions × 1 MiB UTF-8 — fixed in code, NOT config."""
    assert _MAX_SESSIONS == 2
    assert _MAX_SESSION_BYTES == 1 << 20


def test_completed_session_is_frozen():
    s = CompletedSession(("a",), "b", False, 0, 0.0)
    with pytest.raises(Exception):
        s.finals = ("x",)  # type: ignore[misc]


def test_accepted_finals_in_order_single_space_join():
    """(a) finals exactly once, in order; text() = single-space join, no trailing space,
    no added newline."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("one two")
    sr.note_final("three")
    sr.note_tail("fo")
    s = sr.close_session()
    assert s is not None
    assert s.finals == ("one two", "three")
    assert s.text() == "one two three fo"
    assert not s.text().endswith(" ")
    assert "\n" not in s.text()


def test_tail_only_session_text_is_the_tail():
    sr = SessionRecovery()
    sr.open_session()
    sr.note_tail("mid thought")
    s = sr.close_session()
    assert s is not None and s.finals == () and s.text() == "mid thought"


def test_exactly_once_same_key_deduped():
    """(G7) bulk (gen, uid) closed set: the same key records exactly once."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("hello", key=(1, 7))
    sr.note_final("hello", key=(1, 7))  # replay — same (gen, uid)
    s = sr.close_session()
    assert s is not None and s.finals == ("hello",)


def test_different_keys_two_entries():
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("one", key=(1, 7))
    sr.note_final("two", key=(1, 8))
    s = sr.close_session()
    assert s is not None and s.finals == ("one", "two")


def test_keyless_finals_record_each_call():
    """stream-edit passes key=None (G7): the single post-record_final funnel fires once per
    utterance upstream, so the store records every call — duplicates are unreachable there."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("a")
    sr.note_final("b")
    s = sr.close_session()
    assert s is not None and s.finals == ("a", "b")


def test_final_clears_pending_tail():
    """An accepted final CLOSES its utterance — its content is the final, not a tail."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_tail("hello wor")
    sr.note_final("hello world")
    s = sr.close_session()
    assert s is not None and s.tail == "" and s.text() == "hello world"


def test_rejected_final_retains_shown_tail():
    """(b) note_rejected is a content NO-OP: no final added, the shown tail retained."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_tail("abc")
    sr.note_rejected()
    s = sr.close_session()
    assert s is not None and s.finals == () and s.tail == "abc" and s.text() == "abc"


def test_cancel_excludes_tail_keeps_earlier_final():
    """(c) a deliberate cancel excludes the cancelled fragment; earlier finals survive."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("kept")
    sr.note_tail("cancelme")
    sr.note_cancel()
    s = sr.close_session()
    assert s is not None and s.tail == "" and s.text() == "kept"


def test_events_ignored_while_store_closed():
    """(c) late/post-disarm events: nothing is recorded while no session is open."""
    sr = SessionRecovery()
    sr.note_final("late final")
    sr.note_tail("late tail")
    assert sr.close_session() is None
    assert sr.latest_completed() is None


def test_empty_session_discarded_previous_survives():
    """(d) an empty/failed arm produces no completed session; the previous one survives."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("first")
    first = sr.close_session()
    assert first is not None
    sr.open_session()
    assert sr.close_session() is None  # empty arm → discarded
    assert sr.latest_completed() is first
    assert sr.count() == 1


def test_rearm_resets_draft_no_leak():
    """A fresh arm resets the draft: no leakage of a previous draft's tail/finals."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_tail("stale tail")
    sr.note_cancel()  # user cancelled; nothing else said
    assert sr.close_session() is None  # empty after the cancel → discarded
    sr.open_session()
    sr.note_final("fresh")
    s = sr.close_session()
    assert s is not None and s.text() == "fresh"  # "stale tail" must NOT appear


def test_two_session_cap_evicts_oldest():
    """(e) ≤2 completed sessions: the third completion evicts the oldest, latest wins."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("one")
    s1 = sr.close_session()
    sr.open_session()
    sr.note_final("two")
    sr.close_session()
    sr.open_session()
    sr.note_final("three")
    s3 = sr.close_session()
    assert sr.count() == 2
    assert sr.latest_completed() is s3
    assert s1 is not None and s1.text() == "one"  # the evicted snapshot is immutable


def test_cap_drops_whole_oldest_finals_first():
    """(e) overflow: whole oldest finals dropped until the newest complete text fits;
    truncated=True + finals_dropped reported; byte_len() ≤ cap."""
    sr = SessionRecovery(max_session_bytes=64)
    sr.open_session()
    sr.note_final("a" * 30)
    sr.note_final("b" * 30)
    sr.note_final("c" * 30)  # 30*3 + 2 joiner spaces = 92 > 64
    s = sr.close_session()
    assert s is not None
    assert s.truncated is True
    assert s.finals_dropped == 1
    assert s.finals == ("b" * 30, "c" * 30)  # newest complete text that fits
    assert s.byte_len() <= 64


def test_lone_oversized_final_sliced_at_codepoint_boundary():
    """(e) a lone oversized item is hard-truncated to fit: ≤ cap bytes, VALID UTF-8
    (codepoint boundary — the encode/decode round-trip must not raise), start kept."""
    sr = SessionRecovery(max_session_bytes=64)
    sr.open_session()
    sr.note_final("x" * 1000)
    s = sr.close_session()
    assert s is not None
    assert s.truncated is True and s.finals_dropped == 0  # sliced, not dropped
    assert s.byte_len() <= 64
    assert s.text().startswith("x")
    s.text().encode("utf-8").decode("utf-8")  # round-trip: still valid UTF-8


def test_lone_oversized_tail_sliced():
    sr = SessionRecovery(max_session_bytes=64)
    sr.open_session()
    sr.note_tail("y" * 1000)
    s = sr.close_session()
    assert s is not None and s.truncated is True
    assert s.byte_len() <= 64
    s.text().encode("utf-8").decode("utf-8")


def test_normal_session_not_marked_truncated():
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("plain")
    s = sr.close_session()
    assert s is not None and s.truncated is False and s.finals_dropped == 0


def test_clear_empties_store_and_allows_reuse():
    """(f) clear() at daemon exit: latest_completed() → None; the store still works after."""
    sr = SessionRecovery()
    sr.open_session()
    sr.note_final("gone")
    sr.close_session()
    assert sr.latest_completed() is not None
    sr.clear()
    assert sr.latest_completed() is None and sr.count() == 0
    sr.open_session()
    sr.note_final("again")
    s = sr.close_session()
    assert s is not None and s.text() == "again"


def test_thread_safety_smoke_bounded():
    """Concurrent note_final/note_tail from 2 threads + close: no exception, consistent
    state (bounded loop — 200 ops total)."""
    sr = SessionRecovery()
    sr.open_session()
    errors: list[Exception] = []

    def finals_worker() -> None:
        try:
            for i in range(100):
                sr.note_final(f"f{i}", key=(0, i))
        except Exception as e:  # noqa: BLE001 — recorded, never raised into the harness
            errors.append(e)

    def tail_worker() -> None:
        try:
            for i in range(100):
                sr.note_tail(f"t{i}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=finals_worker)
    t2 = threading.Thread(target=tail_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert errors == []
    s = sr.close_session()
    assert s is not None and len(s.finals) == 100


# ===========================================================================
# Layer B — daemon wiring, stream-edit (default mode)
# ===========================================================================


def _make_stream_daemon():
    """An ARMED stream-edit daemon over test_daemon's fakes (fake host with the cancel/
    sentinel seams, spy backend, real StreamingOutput). recorder=None so _load_host uses
    the host_factory (the _make_cancel_daemon shape — a legacy recorder would adapter-wrap
    and lose the cancel seam). No threads run; events are driven synchronously."""
    d, fb = td._make_lazy_daemon(host_factory=td._fake_host_factory(spawn_result=True))
    assert d._load_host() is True
    d.start()  # → _arm() under the lock (open_session included)
    return d, fb, d._backend


def test_session_snapshot_none_on_fresh_daemon():
    """S3 contract: None when the store is empty (boot, cleared, or empty arms only)."""
    d, _fb, _be = _make_stream_daemon()
    assert d.session_snapshot() is None


def test_stream_accepted_final_recorded_once():
    """(a) arm → accepted final → disarm: snapshot text == the final, exactly once."""
    d, fb, be = _make_stream_daemon()
    d.on_final("hello world")
    with d._lock:
        d._disarm()
    snap = d.session_snapshot()
    assert snap is not None
    assert snap["text"] == "hello world"
    assert snap["finals"] == 1 and snap["tail_chars"] == 0
    assert snap["truncated"] is False and snap["finals_dropped"] == 0
    assert isinstance(snap["ended_monotonic"], float)
    assert set(snap) == {
        "text",
        "truncated",
        "finals",
        "finals_dropped",
        "tail_chars",
        "ended_monotonic",
    }


def test_stream_partial_tail_appended_with_one_space():
    """(a) the unfinished tail is appended with one space after the finals."""
    d, fb, be = _make_stream_daemon()
    d.on_final("first sentence")
    d._on_partial("second sen")
    with d._lock:
        d._disarm()
    assert d.session_snapshot()["text"] == "first sentence second sen"


def test_stream_cancel_excludes_tail_and_racing_final():
    """(c) BOTH exclusion halves at the legacy entry point: the cancelled tail is cleared
    AND the racing final is dropped by the suppression window — neither reaches the store."""
    d, fb, be = _make_stream_daemon()
    d.on_final("kept sentence")
    d._on_partial("hello wor")
    d._text_in_flight.set()
    d.cancel()  # Backspace / voicectl cancel funnel: clears tail + opens the window
    d.on_final("racing final")  # the real final that raced the cancel → DROPPED
    with d._lock:
        d._disarm()
    snap = d.session_snapshot()
    assert snap is not None and snap["text"] == "kept sentence"


def test_stream_late_final_excluded_previous_session_intact():
    """(c) a post-disarm final hits the listening gate BEFORE the recovery hook — the
    completed session is untouched."""
    d, fb, be = _make_stream_daemon()
    d.on_final("in session")
    with d._lock:
        d._disarm()
    d.on_final("late text")  # not listening → dropped
    snap = d.session_snapshot()
    assert snap is not None and snap["text"] == "in session"
    assert d._session_recovery.count() == 1


def test_stream_rejected_final_no_final_tail_retained():
    """(b) a blocklisted final adds NO final; the partial-fed tail survives as the tail."""
    d, fb, be = _make_stream_daemon()
    d._on_partial("hello wor")
    d.on_final("thank you.")  # blocklist → rejected: note_rejected (content no-op)
    with d._lock:
        d._disarm()
    snap = d.session_snapshot()
    assert snap is not None
    assert snap["finals"] == 0 and snap["text"] == "hello wor"


def test_stream_empty_arm_previous_session_survives():
    """(d) arm → silence → disarm: no new session; `voicectl session` still answers with
    the previous one."""
    d, fb, be = _make_stream_daemon()
    d.on_final("the keeper")
    with d._lock:
        d._disarm()
    d.start()  # re-arm
    with d._lock:
        d._disarm()  # nothing dictated → empty → discarded
    snap = d.session_snapshot()
    assert snap is not None and snap["text"] == "the keeper"
    assert d._session_recovery.count() == 1


def test_quit_clears_the_store():
    """(f) request_shutdown() clears the store (SIGTERM + quit funnel, G10); S3's pull
    returns None afterwards."""
    d, fb, be = _make_stream_daemon()
    d.on_final("persist?")
    with d._lock:
        d._disarm()  # close the session first — snapshots expose COMPLETED sessions only
    assert d.session_snapshot() is not None
    d.request_shutdown()
    assert d.session_snapshot() is None


def test_close_log_line_counts_only(caplog):
    """(h) G6: the close-time INFO line carries counts/times ONLY — never session text."""
    d, fb, be = _make_stream_daemon()
    with caplog.at_level("INFO", logger="voice_typing.daemon"):
        d.on_final("wordone")
        d.on_final("wordtwo")
        with d._lock:
            d._disarm()
    lines = [
        r.getMessage() for r in caplog.records if "session recovery" in r.getMessage()
    ]
    assert len(lines) == 1, lines
    assert re.search(
        r"session recovery: session completed finals=2 tail_chars=0 bytes=\d+ "
        r"truncated=0 store=1",
        lines[0],
    ), lines[0]
    assert "wordone" not in lines[0] and "wordtwo" not in lines[0]


# ===========================================================================
# Layer B — daemon wiring, bulk-text mode (S1's fixtures; G3/G7)
# ===========================================================================


def _make_armed_bulk_daemon(identity):
    """A bulk daemon ARMED through start() (→ _arm bumps gen to 1, opens the recovery
    session, and the arm thread builds + arms the real controller over the fake target)."""
    d, fb, be, host = tbd._make_bulk_daemon(identity=identity)
    assert d._load_host() is True
    d.start()
    assert tbd._wait_until(lambda: d._bulk_delivery_active), "arm thread must settle"
    return d, fb, be, host


def test_bulk_accepted_final_exactly_once():
    """(a) + (G7): a bulk final is recorded keyed (gen, uid); replaying the SAME final
    (same identity, no re-arm) does NOT duplicate it."""
    d, fb, be, host = _make_armed_bulk_daemon(tbd._Identity(1, 7))
    d.on_final("hello world")
    d.on_final("hello world")  # dup delivery of the same (gen, uid)
    with d._lock:
        d._disarm()
    snap = d.session_snapshot()
    assert snap is not None
    assert snap["text"] == "hello world"
    assert snap["finals"] == 1


def test_bulk_cancel_excludes_tail_and_racing_final():
    """(c) the bulk entry point funnels the same exclusions: the partial tail is cleared
    by the cancel and the racing final is dropped by the suppression window."""
    d, fb, be, host = _make_armed_bulk_daemon(tbd._Identity(1, 8))
    d.on_final("kept")
    d._on_partial("hello wor")  # bulk partial → note_tail (recognized tail, D2)
    d._text_in_flight.set()
    d.cancel()  # bulk intercept: ctrl.cancel + shared latch + note_cancel
    d.on_final("racing final")  # latched window → dropped BEFORE the bulk dispatch
    with d._lock:
        d._disarm()
    snap = d.session_snapshot()
    assert snap is not None and snap["text"] == "kept"


def test_bulk_rejected_final_retains_tail():
    """(b) bulk rejected final (min_chars): no final recorded; the recognized tail survives."""
    d, fb, be, host = _make_armed_bulk_daemon(tbd._Identity(1, 9))
    d._on_partial("abc")
    d._cfg.filter.min_chars = 50
    d.on_final("hi")  # below min_chars → the bulk rejected branch → note_rejected
    with d._lock:
        d._disarm()
    snap = d.session_snapshot()
    assert snap is not None and snap["finals"] == 0 and snap["text"] == "abc"


def test_bulk_identity_missing_drop_records_nothing():
    """G6: an id-less payload is dropped BEFORE the recovery hook — nothing recorded."""
    d, fb, be, host = _make_armed_bulk_daemon(None)
    host.relay_identity_value = None
    d.on_final("no identity")
    with d._lock:
        d._disarm()
    assert d.session_snapshot() is None  # empty session → discarded
