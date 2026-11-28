"""tests/test_native_recovery.py — P1.M1.T4.S1: the NativeRecovery leaf (PRD §4.8.1 C).

Pure store tests, fakes ONLY (no CUDA, no socket, no daemon, no I/O — AGENTS.md): a fake
monotonic clock, canonical UUIDv4 fixtures, direct leaf calls. Every §4.8.1 C clause gets a
named test — the auto-created active session + seq-ordered snapshot text; retain validation
(non-UUIDv4 / lone surrogates / bad seq / duplicates → False, state untouched); the ONE
active-slot refusal; mark_offer_attempted → possibly_applied (survives truncation);
settle_final (verified ACK) removal + budget reclaim; the 1 MiB UTF-8 cap bounded WHILE
ACTIVE (whole-oldest-first overflow, separators counted, a lone oversized final clipped at
a codepoint boundary keeping its START — a flagged final is clipped, never dropped);
end_session retention vs empty-discard; the ≤2 ended cap (oldest evicted); latest-ended
selection; ended-id refusal; clear + reuse; counts-only diagnostics; a bounded
thread-safety smoke; and the legacy-isolation pin (SessionRecovery untouched).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 120 .venv/bin/python -m pytest tests/test_native_recovery.py -q
"""

from __future__ import annotations

import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parent)
)  # sibling-test fixture imports

from voice_typing.session_recovery import (  # noqa: E402
    _MAX_NATIVE_SESSION_BYTES,
    _MAX_NATIVE_SESSIONS,
    NativeRecovery,
    NativeRecoverySnapshot,
    SessionRecovery,
)


def _id(n: int) -> str:
    """A canonical lowercase UUIDv4 fixture (strict is_uuid_v4 accepts exactly this form)."""
    return str(uuid.UUID(int=n, version=4))


def _fake_clock():
    """A fake monotonic clock: (read, advance) closures over one mutable float."""
    t = [1000.0]

    def read() -> float:
        return t[0]

    def advance(step: float = 10.0) -> None:
        t[0] += step

    return read, advance


# 1 ---------------------------------------------------------------------------
def test_retain_final_creates_active_session_and_snapshot_lists_text_in_seq_order():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    assert r.active_id() is None
    assert r.retain_final(a, 2, "b") is True   # auto-creates the ACTIVE session
    assert r.retain_final(a, 1, "a") is True   # out-of-order arrival; snapshot is seq-ordered
    assert r.retain_final(a, 3, "c") is True
    assert r.active_id() == a
    snap = r.recover(a)
    assert isinstance(snap, NativeRecoverySnapshot)
    assert snap.text == "a b c"                # seq order, single-space joined
    assert snap.possibly_applied is False
    assert snap.truncated is False
    assert snap.end_reason is None and snap.ended_monotonic is None
    assert snap.final_count == 3 and snap.session_id == a


# 2 ---------------------------------------------------------------------------
def test_retain_rejects_non_uuid_lone_surrogates_bad_seq_and_duplicates():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    assert r.retain_final(a, 1, "ok") is True
    bad = [
        ("not-a-uuid", 9, "x"),                          # not a UUIDv4
        (_id(2).upper(), 9, "x"),                        # non-canonical case
        ("12345678-1234-1234-1234-123456789abc", 9, "x"),  # version nibble ≠ 4
        (a, 0, "x"),                                     # seq <= 0
        (a, -3, "x"),                                    # negative seq
        (a, True, "x"),                                  # bool is not an int seq
        (a, 1.0, "x"),                                   # non-int seq
        (a, 9, ""),                                      # empty after strip
        (a, 9, "   \n\t "),                              # whitespace-only
        (a, 9, "bad \ud800 surrogate"),                  # lone surrogate
    ]
    for sid, seq, text in bad:
        assert r.retain_final(sid, seq, text) is False, (sid, seq, text)
    assert r.retain_final(a, 1, "dup") is False          # duplicate (id, seq)
    snap = r.recover(a)
    assert snap.text == "ok" and snap.final_count == 1   # state untouched by every refusal


# 3 ---------------------------------------------------------------------------
def test_second_active_session_is_refused_while_one_is_active():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a, b = _id(1), _id(2)
    assert r.retain_final(a, 1, "a1") is True
    assert r.retain_final(b, 1, "b1") is False   # one active slot (§4.8.1 B exclusivity)
    assert r.active_id() == a
    assert r.counts() == (0, 1)                  # nothing leaked for b
    r.end_session(a, "done")
    assert r.retain_final(b, 1, "b1") is True    # the slot freed
    assert r.active_id() == b


# 4 ---------------------------------------------------------------------------
def test_mark_offer_attempted_sets_possibly_applied():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    r.retain_final(a, 1, "a")
    r.retain_final(a, 2, "b")
    assert r.mark_offer_attempted(a, 2) is True
    assert r.recover(a).possibly_applied is True
    assert r.mark_offer_attempted(a, 2) is True  # idempotent
    assert r.mark_offer_attempted(a, 99) is False  # unknown seq
    assert r.mark_offer_attempted(_id(3), 1) is False  # not the active session


# 5 ---------------------------------------------------------------------------
def test_verified_ack_removes_final_and_reclaims_budget():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    r.retain_final(a, 1, "a")
    r.retain_final(a, 2, "b")
    r.retain_final(a, 3, "c")
    r.mark_offer_attempted(a, 2)
    assert r.settle_final(a, 2) is True          # verified ACK → removed, budget reclaimed
    snap = r.recover(a)
    assert snap.text == "a c" and snap.final_count == 2
    assert snap.possibly_applied is False        # the flag went with the removed final
    assert r.settle_final(a, 2) is False         # exactly-once settle
    assert r.settle_final(a, 99) is False        # unknown seq
    assert r.settle_final(_id(2), 1) is False    # not the active session


# 6 ---------------------------------------------------------------------------
def test_mark_attempt_survives_truncation():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)              # default 1 MiB cap
    a = _id(1)
    assert r.retain_final(a, 1, "x" * 1_200_000) is True  # lone oversized → clipped at retain
    snap = r.recover(a)
    assert snap.truncated is True
    assert len(snap.text.encode("utf-8")) <= _MAX_NATIVE_SESSION_BYTES
    assert r.mark_offer_attempted(a, 1) is True  # the flag lands on the CLIPPED final
    assert r.retain_final(a, 2, "small") is True
    snap = r.recover(a)                          # overflow: the flagged final is clipped FURTHER, never dropped
    assert snap.truncated is True
    assert snap.possibly_applied is True         # uncertainty survived the truncation
    assert snap.text.startswith("x")             # START kept
    assert "small" in snap.text
    assert len(snap.text.encode("utf-8")) <= _MAX_NATIVE_SESSION_BYTES
    assert snap.final_count == 2


# 7 ---------------------------------------------------------------------------
def test_overflow_drops_whole_oldest_first_while_active():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock, max_session_bytes=100)
    a = _id(1)
    for seq in (1, 2, 3):
        assert r.retain_final(a, seq, "a" * 40) is True
    snap = r.recover(a)
    assert snap.truncated is True
    assert snap.final_count == 2                 # the whole OLDEST was dropped
    assert snap.text == "a" * 40 + " " + "a" * 40  # the two NEWEST joined
    assert len(snap.text.encode("utf-8")) <= 100
    assert r.counts() == (0, 2)


# 8 ---------------------------------------------------------------------------
def test_overflow_separators_count_toward_budget():
    clock, _advance = _fake_clock()
    cap = 60
    r = NativeRecovery(clock=clock, max_session_bytes=cap)
    a = _id(1)
    assert r.retain_final(a, 1, "a" * 30) is True  # 30 ≤ 60
    assert r.retain_final(a, 2, "b" * 30) is True  # 30+1+30 = 61 > 60 → oldest dropped
    snap = r.recover(a)
    assert snap.text == "b" * 30                   # no room for the 1-byte joiner → 'a' gone
    assert snap.truncated is True and snap.final_count == 1


# 9 ---------------------------------------------------------------------------
def test_end_session_retains_unacknowledged_and_discards_empty():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a, b = _id(1), _id(2)
    r.retain_final(a, 1, "kept")
    r.mark_offer_attempted(a, 1)
    r.end_session(a, "disconnected")
    snap = r.recover(a)
    assert snap is not None and snap.end_reason == "disconnected"
    assert snap.possibly_applied is True and snap.text == "kept"
    assert snap.ended_monotonic == 1000.0
    assert r.active_id() is None                   # the slot freed
    r.retain_final(b, 1, "tmp")
    r.settle_final(b, 1)                           # fully ACKed → nothing retained
    r.end_session(b, "stopped")
    assert r.recover(b) is None                    # empty ending discarded...
    assert r.recover(a) is not None                # ...and did NOT evict the previous recovery
    assert r.counts() == (1, 0)


# 10 --------------------------------------------------------------------------
def test_two_ended_sessions_cap_evicts_oldest_nonempty():
    clock, advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    ids = [_id(1), _id(2), _id(3)]
    for sid in ids:
        assert r.retain_final(sid, 1, "text-of-" + sid[:4]) is True
        advance()
        r.end_session(sid, "ended")
    assert r.recover(ids[0]) is None               # oldest nonempty evicted
    assert r.recover(ids[1]) is not None and r.recover(ids[2]) is not None
    assert r.counts() == (_MAX_NATIVE_SESSIONS, 0)


# 11 --------------------------------------------------------------------------
def test_recover_omitting_id_selects_latest_ended():
    clock, advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a, b = _id(1), _id(2)
    r.retain_final(a, 1, "first")
    advance(5.0)
    r.end_session(a, "timeout")
    r.retain_final(b, 1, "second")
    advance(5.0)
    r.end_session(b, "disconnected")
    assert r.recover().session_id == b             # latest ENDED by end time
    assert r.recover(None).session_id == b
    assert r.recover().ended_monotonic == 1010.0
    assert r.recover(a).session_id == a            # an explicit id is still addressable


# 12 --------------------------------------------------------------------------
def test_retain_after_end_is_refused():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    r.retain_final(a, 1, "one")
    r.end_session(a, "done")
    assert r.retain_final(a, 2, "two") is False    # an ended id stays closed
    assert r.recover(a).final_count == 1           # state untouched
    assert r.active_id() is None


# 13 --------------------------------------------------------------------------
def test_unicode_finals_round_trip_and_clip_on_codepoint_boundary():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock, max_session_bytes=50)
    a = _id(1)
    text = "汉" * 30 + "😀"                         # 3-byte CJK + a 4-byte emoji = 94 bytes
    assert r.retain_final(a, 1, text) is True
    snap = r.recover(a)
    raw = snap.text.encode("utf-8")
    assert len(raw) <= 50                          # clipped on a CODEPOINT boundary
    assert raw.decode("utf-8") == snap.text        # valid UTF-8 (no split codepoint)
    assert "\ufffd" not in snap.text
    assert snap.text[0] == "汉" and snap.truncated is True  # START kept
    assert r.settle_final(a, 1) is True
    assert r.retain_final(a, 2, "汉字😀 next") is True
    assert r.recover(a).text == "汉字😀 next"       # non-ASCII round-trips verbatim


# 14 --------------------------------------------------------------------------
def test_clear_drops_everything_and_store_is_reusable():
    clock, advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a, b = _id(1), _id(2)
    r.retain_final(a, 1, "x")
    advance()
    r.end_session(a, "ended")
    r.retain_final(b, 1, "active")
    r.clear()
    assert r.recover() is None and r.recover(a) is None and r.recover(b) is None
    assert r.active_id() is None and r.counts() == (0, 0)
    c = _id(3)
    assert r.retain_final(c, 1, "fresh") is True   # reusable
    assert r.active_id() == c and r.counts() == (0, 1)


# 15 --------------------------------------------------------------------------
def test_counts_are_counts_only():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    r.retain_final(a, 1, "x")
    r.retain_final(a, 2, "y")
    ended, active = r.counts()
    assert isinstance(ended, int) and isinstance(active, int)
    assert not isinstance(ended, bool) and not isinstance(active, bool)
    assert (ended, active) == (0, 2)
    snap = r.recover(a)
    for raw in ("finals", "_finals", "texts"):
        assert not hasattr(snap, raw)              # no live lists on the frozen snapshot
    assert snap.final_count == 2                   # counts only


# 16 --------------------------------------------------------------------------
def test_concurrent_retain_and_settle_thread_safety_smoke():
    clock, _advance = _fake_clock()
    r = NativeRecovery(clock=clock)
    a = _id(1)
    assert r.retain_final(a, 1, "seed") is True    # create the active session up front

    def worker(k: int) -> None:
        for i in range(200):
            seq = 100 + k * 1000 + i               # per-thread disjoint seq space
            if not r.retain_final(a, seq, f"t{k}-{i}"):
                raise AssertionError(f"retain refused: {seq}")
            if seq % 2 == 0 and not r.settle_final(a, seq):
                raise AssertionError(f"settle refused: {seq}")

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)  # bounded: the smoke must terminate
    snap = r.recover(a)
    assert snap.final_count == 401                 # the seed + 4 × 100 odd seqs kept, evens ACKed away
    assert r.counts() == (0, 401)


# 17 --------------------------------------------------------------------------
def test_legacy_session_recovery_untouched():
    clock, _advance = _fake_clock()
    legacy = SessionRecovery()
    legacy.open_session()
    legacy.note_final("legacy final")
    legacy.note_tail("legacy tail")
    native = NativeRecovery(clock=clock)
    a = _id(1)
    native.retain_final(a, 1, "native final")
    native.mark_offer_attempted(a, 1)
    native.end_session(a, "disconnected")
    native.clear()
    completed = legacy.close_session()
    assert completed is not None
    assert completed.finals == ("legacy final",)   # the legacy draft was untouched
    assert completed.tail == "legacy tail"
    assert completed.text() == "legacy final legacy tail"
    assert native.counts() == (0, 0)               # both leaves coexist in one module
