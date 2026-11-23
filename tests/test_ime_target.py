"""Fake-proc unit suite for voice_typing.ime.target (P1.M4.T2.S1 — the required gate).

No compositor, no manager import, no subprocess: ImeTarget gets a _FakeProc that
records .request(cmd, timeout=..., **fields) calls and returns scripted replies
(None = dead/timed-out child). Pins: the R.3 acquire refusal taxonomy
(6 refusals + happy path), byte-offset (UTF-8) correctness of pre_caret and
to_bytes_span on the ORIGINAL text (incl. a 4-byte astral char), every recheck
branch (never mutates, one fresh verify pull), the explicit timeout=2.5 on both
requests, and the exported units plumbing T3 consumes.
"""
from __future__ import annotations

import dataclasses

import pytest

from voice_typing.bulk_delivery import TargetUnits
from voice_typing.ime.target import FieldBinding, ImeTarget


class _FakeProc:
    """The injection seam: records requests; scripted replies popped in order."""

    def __init__(self, replies):
        self.calls = []  # (cmd, timeout, fields) per request, in order
        self._replies = list(replies)

    def request(self, cmd, timeout=None, **fields):
        self.calls.append((cmd, timeout, fields))
        return self._replies.pop(0)


def _snap(text="héllo ", cursor=7, anchor=7, handle="im7", revision=3, **over):
    r = {"id": 1, "reply": "acquire", "ok": True, "handle": handle, "revision": revision,
         "text": text, "cursor": cursor, "anchor": anchor, "snapshot_truncated": False}
    r.update(over)
    return r


def _verify(text, cursor, anchor, activated=True, dones=4, **over):
    r = {"id": 2, "reply": "verify", "ok": True, "activated": activated, "dones": dones,
         "text": text, "cursor": cursor, "anchor": anchor, "snapshot_truncated": False}
    r.update(over)
    return r


def _bound(*replies):
    """An ImeTarget whose acquire already succeeded (binding from the default snap)."""
    proc = _FakeProc([_snap(), *replies])
    target = ImeTarget(proc)
    acquired = target.acquire()
    assert acquired.ok, acquired.reason
    return target, proc, acquired.handle


# ---------------------------------------------------------------- acquire ---

def test_acquire_happy_path_binds_field():
    proc = _FakeProc([_snap()])
    target = ImeTarget(proc)
    a = target.acquire()
    assert a.ok and a.reason == ""
    b = a.handle
    assert isinstance(b, FieldBinding)
    assert b.im_handle == "im7" and b.cursor_bytes == 7 and b.anchor_bytes == 7
    assert b.pre_caret == "héllo " and b.revision == 3
    assert a.revision == 3  # AcquireResult.revision mirrors the binding's


def test_acquire_pre_caret_is_byte_derived_not_char_derived():
    # "héllo " is 6 chars but 7 UTF-8 bytes (é = 2 bytes): cursor 7 is only
    # explainable as a BYTE offset — the binding must carry it verbatim.
    proc = _FakeProc([_snap(text="héllo ", cursor=7, anchor=7)])
    b = ImeTarget(proc).acquire().handle
    assert b.cursor_bytes == 7 and b.anchor_bytes == 7
    assert b.pre_caret == "héllo "


def test_acquire_astral_char_byte_correctness():
    # "a𝄞b" = 3 chars / 6 bytes (𝄞 = U+1D11E = 4 UTF-8 bytes). A field cursor at
    # byte 5 sits between 𝄞 and b — char math would say past-the-end (len == 3).
    proc = _FakeProc([_snap(text="a𝄞b", cursor=5, anchor=5)])
    b = ImeTarget(proc).acquire().handle
    assert b.cursor_bytes == 5 and b.anchor_bytes == 5
    assert b.pre_caret == "a𝄞"  # bytes [:5] decoded back — exactly "a" + the astral char


def test_acquire_no_reply():
    a = ImeTarget(_FakeProc([None])).acquire()
    assert not a.ok and a.reason == "ime no reply" and a.revision == 0


def test_acquire_not_activated_propagated():
    a = ImeTarget(_FakeProc([{"id": 1, "reply": "acquire", "ok": False,
                              "reason": "not activated"}])).acquire()
    assert not a.ok and a.reason == "not activated"


def test_acquire_no_surrounding_text_propagated():
    a = ImeTarget(_FakeProc([{"id": 1, "reply": "acquire", "ok": False,
                              "reason": "no surrounding text"}])).acquire()
    assert not a.ok and a.reason == "no surrounding text"


def test_acquire_refused_without_reason_gets_default():
    a = ImeTarget(_FakeProc([{"id": 1, "reply": "acquire", "ok": False}])).acquire()
    assert not a.ok and a.reason == "acquire refused"


def test_acquire_user_selection_refused():
    # R.3 verbatim: a pre-existing selection (cursor != anchor) is never replaced.
    a = ImeTarget(_FakeProc([_snap(text="héllo ", cursor=3, anchor=7)])).acquire()
    assert not a.ok and a.reason == "user selection present"


def test_acquire_inconsistent_snapshot_cursor_past_bytes():
    a = ImeTarget(_FakeProc([_snap(text="hi", cursor=3, anchor=2)])).acquire()  # 2 bytes only
    assert not a.ok and a.reason == "inconsistent snapshot"


def test_acquire_inconsistent_snapshot_negative_anchor():
    a = ImeTarget(_FakeProc([_snap(cursor=6, anchor=-1)])).acquire()  # 6 == byte len; -1 < 0
    assert not a.ok and a.reason == "inconsistent snapshot"


def test_acquire_truncated_snapshot_refused():
    a = ImeTarget(_FakeProc([_snap(snapshot_truncated=True)])).acquire()
    assert not a.ok and a.reason == "snapshot truncated"


def test_acquire_snapshot_missing_fields():
    a = ImeTarget(_FakeProc([{"id": 1, "reply": "acquire", "ok": True,
                              "handle": "im7", "revision": 1}])).acquire()
    assert not a.ok and a.reason == "snapshot missing fields"


def test_acquire_passes_explicit_timeout_on_both_requests():
    # S2's request() default is 1.0 s; the host waits up to 1.0 s for the snapshot —
    # a default-timeout acquire would race. Both calls must carry timeout=2.5.
    proc = _FakeProc([_snap(), _verify("héllo ok", 9, 9)])
    target = ImeTarget(proc)
    a = target.acquire()
    ok, _why, _rev = target.recheck(a.handle, inserted_bytes=2)
    assert ok
    assert proc.calls == [("acquire", 2.5, {}), ("verify", 2.5, {})]


# ---------------------------------------------------------------- recheck ---

def test_recheck_no_reply():
    target, _proc, binding = _bound(None)
    assert target.recheck(binding) == (False, "ime no reply", 0)


def test_recheck_deactivated():
    target, _proc, binding = _bound(_verify("héllo ", 7, 7, activated=False))
    assert target.recheck(binding) == (False, "ime deactivated", 0)


def test_recheck_no_snapshot():
    target, _proc, binding = _bound(
        {"id": 2, "reply": "verify", "ok": False, "activated": True, "dones": 2,
         "reason": "no surrounding text"})
    assert target.recheck(binding) == (False, "no surrounding text", 0)


def test_recheck_selection_present():
    target, _proc, binding = _bound(_verify("héllo ok", 9, 0))  # fresh selection
    assert target.recheck(binding) == (False, "user selection present", 4)


def test_recheck_caret_moved_arithmetic_with_inserted_bytes():
    # Expected caret = binding.cursor_bytes (7) + inserted_bytes (3) = 10; a fresh
    # caret at 9 (one byte short) must refuse — proving the caller's accounting.
    target, _proc, binding = _bound(_verify("héllo okX", 9, 9))
    assert target.recheck(binding, inserted_bytes=3) == (False, "caret moved", 4)
    # And the SAME snapshot passes with the matching accounting:
    target2, _proc2, binding2 = _bound(_verify("héllo okX", 10, 10))
    assert target2.recheck(binding2, inserted_bytes=3) == (True, "", 4)


def test_recheck_adjacent_text_changed():
    # Caret matches the accounting, but the text BEFORE it was rewritten.
    target, _proc, binding = _bound(_verify("userX ok", 8, 8))
    assert target.recheck(binding, inserted_bytes=1) == (False, "adjacent text changed", 4)


def test_recheck_ok_after_our_insert():
    target, _proc, binding = _bound(_verify("héllo ok", 9, 9))
    assert target.recheck(binding, inserted_bytes=2) == (True, "", 4)


def test_recheck_post_caret_change_does_not_revoke():
    # Text AFTER the expected caret changed — irrelevant to ownership (only the
    # act of typing is takeover's signal, T4). The prefix still matches.
    target, _proc, binding = _bound(_verify("héllo ok — user kept typing", 9, 9))
    assert target.recheck(binding, inserted_bytes=2) == (True, "", 4)


def test_recheck_sends_only_verify_and_never_mutates():
    # ONE fresh verify pull per recheck; no show/commit/leave ever goes out, and
    # no request fields ride along (verify takes none).
    target, proc, binding = _bound(_verify("héllo ", 7, 7))
    ok, _why, _rev = target.recheck(binding)
    assert ok
    assert [c[0] for c in proc.calls] == ["acquire", "verify"]
    assert proc.calls[1] == ("verify", 2.5, {})


def test_recheck_is_fresh_pull_not_cached_state():
    # The check must reflect CURRENT target state: same binding, diverged target
    # (user moved the caret) → refused even though acquire saw it matching.
    target, proc, binding = _bound(_verify("héllo X ", 12, 12))  # caret moved on the field
    ok, why, _rev = target.recheck(binding, inserted_bytes=2)
    assert not ok and why == "caret moved"
    # a second recheck pulls verify AGAIN (fresh every call):
    proc._replies.append(_verify("héllo ok", 9, 9))
    assert target.recheck(binding, inserted_bytes=2) == (True, "", 4)
    assert [c[0] for c in proc.calls] == ["acquire", "verify", "verify"]


# ----------------------------------------------------------------- units ---

def test_units_is_utf8_bytes():
    assert ImeTarget.units is TargetUnits.UTF8_BYTES


def test_to_bytes_span_round_trip_including_astral():
    # "a𝄞bc": a=1B, 𝄞=4B, b=1B, c=1B → char spans map to cumulative byte offsets.
    text = "a𝄞bc"
    assert ImeTarget.to_bytes_span(text, 0, 2) == (0, 5)     # a + 𝄞 = 5 bytes
    assert ImeTarget.to_bytes_span(text, 2, 4) == (5, 7)     # bc = bytes 5..7
    assert ImeTarget.to_bytes_span("héllo", 0, 5) == (0, 6)  # é counts as 2 bytes
    assert ImeTarget.to_bytes_span(text, 3, 3) == (6, 6)     # empty span at byte 6


def test_binding_caret_after_arithmetic():
    proc = _FakeProc([_snap()])
    binding = ImeTarget(proc).acquire().handle
    assert ImeTarget.binding_caret_after(binding, 0) == 7
    assert ImeTarget.binding_caret_after(binding, 4) == 11


def test_field_binding_is_frozen():
    b = FieldBinding(im_handle="im", cursor_bytes=1, anchor_bytes=1, pre_caret="x", revision=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.cursor_bytes = 2  # the handle must be immutable once acquired
