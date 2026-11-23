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

from voice_typing.bulk_delivery import ShowResult, TargetUnits
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


# ------------------------------------------------------------------ show ---
# P1.M4.T3.S1 — the INSERT path: ordering zero-diff → extension → recheck →
# cap → ONE atomic request; mapping applied/unchanged/refused/unknown; state
# advances ONLY on APPLIED; cumulative UTF-8 inserted_bytes (astral = 4).

_SHOW_FIELDS = ("session", "utterance", "seq", "expected_revision", "text")


def _showreply(result="applied", t_ms=31.0, **over):
    r = {"id": 3, "reply": "show", "result": result, "t_ms": t_ms}
    r.update(over)
    return r


def test_show_not_acquired_refuses_without_any_request():
    proc = _FakeProc([])
    target = ImeTarget(proc)
    assert target.show(1, "u1", 1, 2, "hello") is ShowResult.REFUSED
    assert target.last_reason == "not acquired"
    assert proc.calls == []  # nothing went near the wire


def test_show_pure_extension_sends_one_atomic_insert():
    target, proc, _ = _bound(_verify("héllo Hel", 7, 7), _showreply())
    r = target.show(1, "u1", 1, 3, "Hel")
    assert r is ShowResult.APPLIED
    assert len(proc.calls) == 3  # acquire + verify + exactly ONE show
    cmd, timeout, fields = proc.calls[-1]
    assert (cmd, timeout) == ("show", 0.25)  # the 250 ms deadline budget
    for f in _SHOW_FIELDS:
        assert f in fields  # protocol.validate_request demands all five
    assert fields["text"] == "Hel" and fields["before"] == 0  # pure insert
    assert (fields["session"], fields["utterance"], fields["seq"],
            fields["expected_revision"]) == (1, "u1", 1, 3)
    assert target._last_applied_span == "Hel" and target._inserted_bytes == 3
    assert target.last_reason == ""


def test_show_zero_diff_after_applied_emits_zero_requests():
    target, proc, _ = _bound(_verify("héllo Hel", 7, 7), _showreply())
    assert target.show(1, "u1", 1, 3, "Hel") is ShowResult.APPLIED
    n = len(proc.calls)
    assert target.show(1, "u1", 2, 4, "Hel") is ShowResult.UNCHANGED
    assert len(proc.calls) == n  # zero-diff ⇒ ZERO events (R.1)


def test_show_not_acquired_guard_precedes_zero_diff():
    # The binding guard is FIRST: even a render-empty span on a never-acquired
    # target refuses — zero-diff is not consulted, no request is sent.
    proc = _FakeProc([])
    target = ImeTarget(proc)
    assert target.show(1, "u1", 1, 1, "") is ShowResult.REFUSED
    assert target.last_reason == "not acquired"
    assert proc.calls == []


def test_show_render_equal_spacing_only_is_unchanged():
    # verify carries the PRE-mutation caret (7 = binding point, nothing sent yet).
    target, proc, _ = _bound(_verify("héllo Hello world", 7, 7), _showreply())
    assert target.show(1, "u1", 1, 3, "Hello world") is ShowResult.APPLIED
    n = len(proc.calls)
    assert target.show(1, "u1", 2, 4, "Hello  world ") is ShowResult.UNCHANGED
    assert len(proc.calls) == n  # rendered_equal consumed, not reimplemented


def test_show_second_extension_delta_new_part_recheck_cumulative_bytes():
    target, proc, _ = _bound(
        _verify("héllo Hel", 7, 7), _showreply(),
        _verify("héllo Hello w", 10, 10), _showreply(t_ms=33.0),
    )
    assert target.show(1, "u1", 1, 3, "Hel") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "Hello w") is ShowResult.APPLIED
    fields = proc.calls[-1][2]
    assert fields["text"] == "lo w" and fields["before"] == 0  # delta only
    # The 2nd recheck passed only because expected caret == 7 + 3 (cumulative
    # bytes of the FIRST delta): the scripted cursor 10 refuses otherwise.
    assert target._inserted_bytes == 7 and target._last_applied_span == "Hello w"


def test_show_astral_delta_counts_four_utf8_bytes():
    # "𝄞" is ONE char but FOUR UTF-8 bytes: applying just it advances
    # _inserted_bytes by 4 — the byte (not char) accounting, pinned directly.
    target, proc, _ = _bound(_verify("héllo ", 7, 7), _showreply())
    assert target.show(1, "u1", 1, 3, "𝄞") is ShowResult.APPLIED
    assert target._inserted_bytes == 4


def test_show_reply_unknown_maps_unknown_state_not_advanced():
    target, proc, _ = _bound(_verify("héllo Hel", 7, 7),
                             _showreply(result="unknown", t_ms=250.0))
    assert target.show(1, "u1", 1, 3, "Hel") is ShowResult.UNKNOWN
    assert target.last_reason == "host result 'unknown'"
    assert target._last_applied_span == "" and target._inserted_bytes == 0


def test_show_reply_refused_maps_refused():
    target, proc, _ = _bound(_verify("héllo Hel", 7, 7), _showreply(result="refused"))
    assert target.show(1, "u1", 1, 3, "Hel") is ShowResult.REFUSED
    assert target.last_reason == "host refused"
    assert target._last_applied_span == ""  # state NEVER advances on refused


def test_show_no_reply_maps_unknown():
    target, proc, _ = _bound(_verify("héllo Hel", 7, 7), None)
    assert target.show(1, "u1", 1, 3, "Hel") is ShowResult.UNKNOWN
    assert target.last_reason == "ime no reply"


def test_show_reply_missing_result_field_maps_unknown():
    target, proc, _ = _bound(_verify("héllo Hel", 7, 7),
                             {"id": 3, "reply": "show", "t_ms": 1.0})
    assert target.show(1, "u1", 1, 3, "Hel") is ShowResult.UNKNOWN
    assert target.last_reason == "host result None"  # odd reply ⇒ defensive UNKNOWN, no crash


def test_show_recheck_caret_moved_refuses_before_any_show_request():
    target, proc, _ = _bound(_verify("héllo X", 8, 8))  # caret moved, inserted 0
    r = target.show(1, "u1", 1, 3, "Hel")
    assert r is ShowResult.REFUSED
    assert target.last_reason == "recheck: caret moved"
    assert [c[0] for c in proc.calls] == ["acquire", "verify"]  # NO show on the wire


def test_show_recheck_selection_refuses():
    target, proc, _ = _bound(_verify("héllo Hel", 9, 7))  # fresh user selection
    r = target.show(1, "u1", 1, 3, "Hel")
    assert r is ShowResult.REFUSED
    assert target.last_reason == "recheck: user selection present"
    assert [c[0] for c in proc.calls] == ["acquire", "verify"]


def test_show_delta_over_commit_cap_refused_after_recheck_no_request():
    span = "x" * 4001  # 4001 ASCII bytes — one over the per-commit cap
    target, proc, _ = _bound(_verify("héllo ", 7, 7))  # recheck passes FIRST (ordering)
    r = target.show(1, "u1", 1, 3, span)
    assert r is ShowResult.REFUSED
    assert target.last_reason == "commit cap 4000B exceeded (4001B)"
    assert [c[0] for c in proc.calls] == ["acquire", "verify"]  # never chunked, never sent


def test_show_delta_exactly_at_cap_is_one_commit():
    span = "y" * 4000  # == cap: allowed (the check is >, not >=)
    target, proc, _ = _bound(_verify("héllo ", 7, 7), _showreply())
    assert target.show(1, "u1", 1, 3, span) is ShowResult.APPLIED
    assert target._inserted_bytes == 4000


def test_show_non_extension_span_takes_correction_path():
    # Supersedes S1's placeholder pin ("correction not implemented (P1.M4.T3.S2)"):
    # P1.M4.T3.S2 lands the real correction — ONE atomic verified-owned replacement.
    target, proc, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),   # insert lands "hello" (5 B)
        _verify("héllo hello", 12, 12),                 # correction recheck (caret at end)
        _verify("héllo hello", 12, 12),                 # owned-region pull
        _showreply(),                                   # the ONE atomic commit
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "xello") is ShowResult.APPLIED  # not an extension
    cmd, timeout, fields = proc.calls[-1]
    assert (cmd, timeout) == ("show", 0.25)
    assert fields["before"] == 5 and fields["text"] == "xello"  # FULL span, not a diff
    assert [c[0] for c in proc.calls] == \
        ["acquire", "verify", "show", "verify", "verify", "show"]
    assert target._last_applied_span == "xello" and target._inserted_bytes == 5


def test_show_state_not_advanced_on_refusal_next_delta_vs_last_applied():
    target, proc, _ = _bound(
        _verify("héllo ", 7, 7), _showreply(),               # "hello" applied (5 B)
        _verify("héllo hello world", 18, 18),                 # caret ran ahead → refused
        _verify("héllo hello world", 12, 12), _showreply(),   # retry with settled caret
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hello world") is ShowResult.REFUSED
    # Retry of the IDENTICAL span: delta computed vs the last APPLIED span —
    # the wire carries only " world" (NOT " world world"); the recheck's
    # expected caret 7+5==12 proves inserted_bytes did NOT double-count.
    assert target.show(1, "u1", 3, 5, "hello world") is ShowResult.APPLIED
    assert proc.calls[-1][2]["text"] == " world"
    assert target._inserted_bytes == 11 and target._last_applied_span == "hello world"


# ------------------------------------------- show(): correction path (P1.M4.T3.S2) ---
# A non-extension span is ONE atomic range replacement of the VERIFIED-OWNED range:
# recheck proves the caret sits at the END of our owned span (the delete counts
# backward from the caret), then _owned_region_intact re-reads the field and proves
# the range's CURRENT content is still exactly ours — only then ONE show request
# with before == UTF-8 bytes of the owned span and text == the FULL corrected span.


def test_show_prefix_divergent_correction_one_atomic_replacement():
    target, proc, _ = _bound(
        _verify("héllo helllo w", 7, 7), _showreply(),   # insert lands "helllo w" (8 B)
        _verify("héllo helllo w", 15, 15),                 # correction recheck
        _verify("héllo helllo w", 15, 15),                 # owned-region pull
        _showreply(),                                      # the ONE atomic commit
    )
    assert target.show(1, "u1", 1, 3, "helllo w") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hello world") is ShowResult.APPLIED
    assert [c[0] for c in proc.calls] == \
        ["acquire", "verify", "show", "verify", "verify", "show"]  # 2 pulls + ONE show
    cmd, timeout, fields = proc.calls[-1]
    assert (cmd, timeout) == ("show", 0.25)               # the 250 ms deadline budget
    for f in _SHOW_FIELDS:
        assert f in fields                                 # ALL SHOW_FIELDS on the wire
    assert fields["before"] == len("helllo w".encode()) == 8  # UTF-8 bytes, backward delete
    assert fields["text"] == "hello world"                 # the FULL corrected span
    assert target._last_applied_span == "hello world"
    assert target._inserted_bytes == 11                    # SET to the owned size
    assert target.last_reason == ""


def test_show_shrink_correction_sets_inserted_bytes_to_owned_size():
    # A shrink makes the caret EARLIER: _inserted_bytes must be SET to the new owned
    # size (2), never += (13) — recheck's caret arithmetic depends on the invariant.
    target, proc, _ = _bound(
        _verify("héllo hello world", 7, 7), _showreply(),  # insert "hello world" (11 B)
        _verify("héllo hello world", 18, 18),                # recheck
        _verify("héllo hello world", 18, 18),                # owned-region pull
        _showreply(),                                        # replacement commit
    )
    assert target.show(1, "u1", 1, 3, "hello world") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hi") is ShowResult.APPLIED
    fields = proc.calls[-1][2]
    assert fields["text"] == "hi" and fields["before"] == 11
    assert target._inserted_bytes == 2                       # SET — not 13
    assert target._last_applied_span == "hi"


def test_show_correction_after_correction_before_vs_first_corrected_span():
    target, proc, _ = _bound(
        _verify("héllo hello world", 7, 7), _showreply(),  # insert (11 B)
        _verify("héllo hello world", 18, 18),
        _verify("héllo hello world", 18, 18), _showreply(),  # correction 1 → "jello world"
        _verify("héllo jello world", 18, 18),
        _verify("héllo jello world", 18, 18), _showreply(), # correction 2 → "bellow world"
    )
    assert target.show(1, "u1", 1, 3, "hello world") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "jello world") is ShowResult.APPLIED
    assert target.show(1, "u1", 3, 5, "bellow world") is ShowResult.APPLIED
    assert proc.calls[-1][2]["before"] == len("jello world".encode()) == 11  # state chaining
    assert target._last_applied_span == "bellow world" and target._inserted_bytes == 12


def test_show_correction_astral_chars_count_utf8_bytes():
    # "😀" and "🙂" are ONE char but FOUR UTF-8 bytes each: before counts 4 for the
    # astral char — the wire's byte units (an off-by-one here eats user text).
    target, proc, _ = _bound(
        _verify("héllo hi \U0001F600 you", 7, 7), _showreply(),  # insert (11 B)
        _verify("héllo hi \U0001F600 you", 18, 18),
        _verify("héllo hi \U0001F600 you", 18, 18), _showreply(),
    )
    assert target.show(1, "u1", 1, 3, "hi \U0001F600 you") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hi \U0001F642 you") is ShowResult.APPLIED
    fields = proc.calls[-1][2]
    assert fields["before"] == len("hi \U0001F600 you".encode("utf-8")) == 11
    assert fields["text"] == "hi \U0001F642 you"
    assert target._inserted_bytes == 11


def test_show_owned_region_diverged_refused_no_show_request():
    # recheck alone passes (caret restored, same length): only the second pull sees
    # that [cursor, cursor+owned) no longer holds OUR bytes — the verified-owned guard.
    target, proc, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),   # insert "hello" (5 B)
        _verify("héllo hello", 12, 12),                 # recheck passes
        _verify("héllo Xello", 12, 12),                 # same-length in-region edit
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "jello") is ShowResult.REFUSED
    assert target.last_reason == "owned region diverged"
    assert [c[0] for c in proc.calls] == \
        ["acquire", "verify", "show", "verify", "verify"]  # NO show request
    assert target._last_applied_span == "hello" and target._inserted_bytes == 5


def test_show_owned_region_snapshot_truncated_past_range_refused():
    target, proc, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),
        _verify("héllo hello", 12, 12),                       # recheck passes
        _verify("héllo hel", 12, 12, snapshot_truncated=True),  # cap cut INSIDE our range
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "jello") is ShowResult.REFUSED
    assert target.last_reason == "owned region diverged"       # cannot verify through the cap
    assert [c[0] for c in proc.calls] == ["acquire", "verify", "show", "verify", "verify"]


def test_show_recheck_caret_moved_on_correction_refuses_no_show_request():
    target, proc, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),
        _verify("héllo hello world", 18, 18),           # caret ran past our range end
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "jello") is ShowResult.REFUSED
    assert target.last_reason == "recheck: caret moved"
    assert [c[0] for c in proc.calls] == ["acquire", "verify", "show", "verify"]


def test_show_unchunkable_correction_refused_no_request():
    span = "b" + "x" * 4000                             # 4001 B, divergent from owned "a"
    target, proc, _ = _bound(
        _verify("héllo a", 7, 7), _showreply(),          # insert "a" (1 B)
        _verify("héllo a", 8, 8),                        # recheck
        _verify("héllo a", 8, 8),                        # owned-region pull
    )
    assert target.show(1, "u1", 1, 3, "a") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, span) is ShowResult.REFUSED
    assert target.last_reason == "unchunkable correction 4001B > 4000B cap"
    assert [c[0] for c in proc.calls] == \
        ["acquire", "verify", "show", "verify", "verify"]  # never chunked, never sent
    assert target._last_applied_span == "a" and target._inserted_bytes == 1


def test_show_revision_regression_refused_no_request_and_equal_proceeds():
    target, proc, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 2, "jello") is ShowResult.REFUSED  # 2 < acquire revision 3
    assert target.last_reason == "revision regression"
    assert [c[0] for c in proc.calls] == ["acquire", "verify", "show"]  # NO further request
    # The equal case still proceeds (controller seeds from acquire, only +1s):
    target2, proc2, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),
        _verify("héllo hello", 12, 12),
        _verify("héllo hello", 12, 12), _showreply(),
    )
    assert target2.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target2.show(1, "u1", 2, 3, "jello") is ShowResult.APPLIED  # == revision: fine


def test_show_extension_after_correction_uses_new_owned_state():
    # After the shrink to "hi" the owned state is 2 B: the next extension takes the
    # INSERT path against the NEW span (before=0, delta only) — the SET pin's payoff.
    target, proc, _ = _bound(
        _verify("héllo hello world", 7, 7), _showreply(),  # insert (11 B)
        _verify("héllo hello world", 18, 18),
        _verify("héllo hello world", 18, 18), _showreply(),  # shrink correction → "hi"
        _verify("héllo hi", 9, 9), _showreply(),             # settled post-shrink field
    )
    assert target.show(1, "u1", 1, 3, "hello world") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hi") is ShowResult.APPLIED
    assert target.show(1, "u1", 3, 5, "hi!") is ShowResult.APPLIED
    fields = proc.calls[-1][2]
    assert fields["before"] == 0 and fields["text"] == "!"   # extension fast-path preserved
    assert target._inserted_bytes == 3 and target._last_applied_span == "hi!"


def test_show_render_equal_would_be_correction_is_unchanged_zero_requests():
    target, proc, _ = _bound(
        _verify("héllo hello world", 7, 7), _showreply(),
    )
    assert target.show(1, "u1", 1, 3, "hello world") is ShowResult.APPLIED
    n = len(proc.calls)
    assert target.show(1, "u1", 2, 4, "hello world") is ShowResult.UNCHANGED   # exact
    assert target.show(1, "u1", 3, 5, "hello  world ") is ShowResult.UNCHANGED  # spacing-only
    assert len(proc.calls) == n   # zero-diff FIRST — even for correction-shaped spans (R.1)


def test_show_correction_no_reply_maps_unknown_state_not_advanced():
    target, proc, _ = _bound(
        _verify("héllo helllo w", 7, 7), _showreply(),
        _verify("héllo helllo w", 15, 15),
        _verify("héllo helllo w", 15, 15), None,             # the IM died before the commit
    )
    assert target.show(1, "u1", 1, 3, "helllo w") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hello world") is ShowResult.UNKNOWN
    assert target.last_reason == "ime no reply"              # never retried by the caller
    assert target._last_applied_span == "helllo w" and target._inserted_bytes == 8


def test_show_correction_host_refused_maps_refused_state_not_advanced():
    target, proc, _ = _bound(
        _verify("héllo helllo w", 7, 7), _showreply(),
        _verify("héllo helllo w", 15, 15),
        _verify("héllo helllo w", 15, 15), _showreply(result="refused"),
    )
    assert target.show(1, "u1", 1, 3, "helllo w") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hello world") is ShowResult.REFUSED
    assert target.last_reason == "host refused"
    assert target._last_applied_span == "helllo w" and target._inserted_bytes == 8


def test_show_correction_odd_result_maps_unknown():
    target, proc, _ = _bound(
        _verify("héllo helllo w", 7, 7), _showreply(),
        _verify("héllo helllo w", 15, 15),
        _verify("héllo helllo w", 15, 15), _showreply(result="weird"),
    )
    assert target.show(1, "u1", 1, 3, "helllo w") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "hello world") is ShowResult.UNKNOWN
    assert target.last_reason == "host result 'weird'"       # defensive, no crash
    assert target._last_applied_span == "helllo w" and target._inserted_bytes == 8


def test_show_correction_refusal_then_retry_recomputes_vs_last_applied_span():
    target, proc, _ = _bound(
        _verify("héllo hello", 7, 7), _showreply(),        # insert "hello" (5 B)
        _verify("héllo hello", 12, 12),
        _verify("héllo hello", 12, 12), _showreply(result="refused"),  # attempt 1 refused
        _verify("héllo hello", 12, 12),
        _verify("héllo hello", 12, 12), _showreply(),        # retry: fresh pulls again
    )
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 4, "jello") is ShowResult.REFUSED
    assert target.show(1, "u1", 3, 5, "jello") is ShowResult.APPLIED
    assert proc.calls[-1][2]["before"] == 5   # vs the last APPLIED span — state NOT advanced
    assert proc.calls[-1][2]["text"] == "jello"
    assert target._inserted_bytes == 5 and target._last_applied_span == "jello"
