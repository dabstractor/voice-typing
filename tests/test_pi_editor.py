"""Taxonomy-pinned suite for voice_typing.pi_editor (P1.M5.T1.S2 — the required gate).

Two layers, no real pi / no daemon / no .pi/ anywhere:
  A. _FakeClient unit tests — every acquire/show/finalize/leave/cancel branch,
     the verbatim machine-readable refusal taxonomy, zero-diff ⇒ ZERO requests,
     UTF-16 offsets vs map_span ground truth (astral 🫡 counts 2), UNKNOWN never
     re-sent, and the takeover latch (exactly ONE halt, ONE reason).
  B. socket-level tests — an in-process fake extension serving S1 protocol v1
     on a tmp_path AF_UNIX socket (mirrors tests/test_control_socket.py): a full
     arm→acquire→show×2→finalize→cancel cycle, absolute-offset replaces over
     astral payloads, a mid-session takeover halt, server-death ⇒ UNKNOWN, and
     re-acquire after leave. Every wait is _wait_for-bounded; every thread is
     a daemon.

Run (AGENTS.md Rule 1 — two timeouts):
    cd /home/dustin/projects/voice-typing
    timeout 180 .venv/bin/python -m pytest tests/test_pi_editor.py -q
"""

from __future__ import annotations

import dataclasses
import json
import os
import socket
import threading
import time as _time

import pytest

from voice_typing.bulk_delivery import ShowResult, TargetUnits, map_span
from voice_typing.pi_editor import (
    PiEditorBinding,
    PiEditorClient,
    PiEditorTarget,
    PiEditorTakeoverWatch,
)

_ASTRAL = "hi! abc🫡"  # 🫡 is astral: 2 UTF-16 units, never len()
_SHOW_TIMEOUT_S = 0.25
_ACQUIRE_TIMEOUT_S = 2.5


def _wait_for(predicate, timeout=2.0, interval=0.01):
    """Bounded poll (tests/test_control_socket.py pattern) — no unbounded waits."""
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if predicate():
            return True
        _time.sleep(interval)
    return predicate()


# ===========================================================================
# Part A — _FakeClient taxonomy tests (no sockets at all)
# ===========================================================================


class _FakeClient:
    """The injection seam: records request(op, timeout, **fields); scripted replies.

    Mirrors tests/test_ime_target.py's _FakeProc duck plus the connect/on_event
    surface the real PiEditorClient exposes (the target's full client duck).
    """

    def __init__(self, replies=(), *, connect_ok=True, connect_error=""):
        self.sock_path = "/fake/pi-editor.sock"
        self.calls = []  # (op, timeout, fields) per request, in order
        self.connect_calls = []  # timeout per connect, in order
        self.closed = 0
        self.connect_ok = connect_ok
        self.connect_error = connect_error
        self.on_event = None  # settable slot (watch.attach target)
        self._replies = list(replies)

    def connect(self, timeout=None):
        self.connect_calls.append(timeout)
        return self.connect_ok

    def request(self, op, timeout=None, **fields):
        self.calls.append((op, timeout, fields))
        return self._replies.pop(0) if self._replies else None

    def close(self):
        self.closed += 1

    @property
    def ops(self):
        return [c[0] for c in self.calls]


def _read(text="", owned=None, dirty=False, units="utf-16", **over):
    """A well-formed S1 ``read`` reply (owned as [start, end] or None)."""
    r = {
        "ok": True,
        "result": "applied",
        "text": text,
        "cursor": {"line": 0, "col": 0},
        "owned": None if owned is None else {"start": owned[0], "end": owned[1]},
        "dirty": dirty,
        "units": units,
        "changes": 0,
    }
    r.update(over)
    return r


def _apply(**over):
    r = {"ok": True, "result": "applied", "cursor": {"line": 0, "col": 3}, "changes": 1}
    r.update(over)
    return r


def _bound(replies=()):
    """A PiEditorTarget whose acquire already succeeded (default clean read)."""
    client = _FakeClient([_read(), *replies])
    target = PiEditorTarget(client)
    acquired = target.acquire()
    assert acquired.ok, acquired.reason
    return target, client, acquired


# ----------------------------------------------------------------- acquire ---


def test_acquire_happy_path_binds_field():
    client = _FakeClient([_read(text="user: ", owned=None, dirty=False)])
    target = PiEditorTarget(client)
    acquired = target.acquire()
    assert acquired.ok
    assert acquired.revision == 0
    assert isinstance(acquired.handle, PiEditorBinding)
    assert acquired.handle.sock_path == "/fake/pi-editor.sock"
    assert (
        acquired.handle.owned_start_u16 == -1
    )  # caret-relative insert: unbound until first apply
    assert acquired.handle.owned_len_u16 == 0
    assert target.last_reason == ""


def test_acquire_socket_absent():
    client = _FakeClient(connect_ok=False, connect_error="pi socket absent")
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "pi socket absent"
    assert client.calls == []  # fail BEFORE any read


def test_acquire_socket_no_reply_connect():
    client = _FakeClient(connect_ok=False, connect_error="pi socket no reply")
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "pi socket no reply"


def test_acquire_read_never_replies():
    client = _FakeClient([None])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "pi socket no reply"


def test_acquire_error_reply_propagates_verbatim():
    client = _FakeClient([{"ok": False, "error": "editor not ready"}])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "editor not ready"


def test_acquire_dirty_refused():
    client = _FakeClient([_read(text="typed", dirty=True)])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "editor dirty"


def test_acquire_stale_owned_fragment_refused():
    # A stranded prior-session fragment is NEVER adopted — even in-bounds.
    client = _FakeClient([_read(text="left over", owned=[0, 9])])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "editor owns fragment"


def test_acquire_owned_out_of_bounds_refused():
    client = _FakeClient([_read(text="abc", owned=[0, 99])])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "inconsistent owned range"


def test_acquire_owned_negative_start_refused():
    client = _FakeClient([_read(text="abc", owned=[-3, 1])])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "inconsistent owned range"


def test_acquire_owned_reversed_range_refused():
    client = _FakeClient([_read(text="abc🫡", owned=[4, 2])])
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "inconsistent owned range"


def test_acquire_missing_fields_refused():
    for over in (
        {"text": None},
        {"dirty": None},
        {"units": "utf-8"},
    ):
        client = _FakeClient([_read(**over)])
        res = PiEditorTarget(client).acquire()
        assert not res.ok and res.reason == "read missing fields", over
    # a wrong-typed owned FIELD (not a dict/null) is missing fields too:
    client = _FakeClient(
        [
            {
                "ok": True,
                "result": "applied",
                "text": "abc",
                "cursor": {"line": 0, "col": 0},
                "owned": "dropped",
                "dirty": False,
                "units": "utf-16",
            }
        ]
    )
    res = PiEditorTarget(client).acquire()
    assert not res.ok and res.reason == "read missing fields"


def test_acquire_passes_explicit_timeouts():
    client = _FakeClient([_read()])
    PiEditorTarget(client).acquire()
    assert client.connect_calls == [_ACQUIRE_TIMEOUT_S]
    assert client.calls == [("read", _ACQUIRE_TIMEOUT_S, {})]


def test_acquire_resets_prior_state():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")  # applied: revision → 1, owned bound
    client._replies.clear()
    client._replies.append(_read())  # a fresh clean field
    client._replies.append(_apply())  # the fresh utterance's insert
    assert target.acquire().ok
    assert (
        target.show(1, "u2", 1, 0, "fresh") is ShowResult.APPLIED
    )  # revision reseeded to 0


# -------------------------------------------------------------------- show ---


def test_show_not_acquired_refuses_without_any_request():
    client = _FakeClient()
    target = PiEditorTarget(client)
    assert target.show(1, "u", 1, 0, "hi") is ShowResult.REFUSED
    assert target.last_reason == "not acquired"
    assert client.calls == []


def test_show_pure_extension_sends_one_atomic_insert():
    target, client, _ = _bound([_apply()])
    res = target.show(1, "u1", 1, 0, "hello")
    assert res is ShowResult.APPLIED
    assert client.ops == [
        "read",
        "insert",
        "read",
    ]  # acquire + insert + first-bind read
    assert client.calls[1] == ("insert", _SHOW_TIMEOUT_S, {"text": "hello"})


def test_show_extension_delta_only_after_first_span():
    target, client, _ = _bound(
        [_apply(), _read(text="hello", owned=[0, 5]), _apply(), _apply()]
    )
    target.show(1, "u1", 1, 0, "hello")
    target.show(1, "u1", 2, 1, "hello world")  # pure extension → delta only
    target.show(1, "u1", 3, 2, "hello world!")  # and again
    inserts = [c for c in client.calls if c[0] == "insert"]
    assert [c[2]["text"] for c in inserts] == ["hello", " world", "!"]
    assert all("start" not in c[2] and "end" not in c[2] for c in inserts)


def test_show_zero_diff_emits_zero_requests():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")
    before = len(client.calls)
    assert target.show(1, "u1", 2, 1, "hello") is ShowResult.UNCHANGED
    assert len(client.calls) == before  # NO socket traffic (R.1: 0 events)


def test_show_zero_diff_whitespace_fold():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")
    before = len(client.calls)
    assert target.show(1, "u1", 2, 1, "hello   ") is ShowResult.UNCHANGED
    assert len(client.calls) == before
    # …but a real case difference is NEVER zero-diff:
    assert target.show(1, "u1", 3, 1, "Hello") is not ShowResult.UNCHANGED


def test_show_first_span_empty_is_zero_diff():
    target, client, _ = _bound()
    assert target.show(1, "u1", 1, 0, "") is ShowResult.UNCHANGED
    assert client.calls == [("read", _ACQUIRE_TIMEOUT_S, {})]  # acquire's read only


def test_show_revision_regression_refused_before_request():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")  # applied → client revision 1
    before = len(client.calls)
    assert (
        target.show(1, "u1", 2, 0, "hello?") is ShowResult.REFUSED
    )  # stale caller (0 < 1)
    assert target.last_reason == "revision regression"
    assert target.show(1, "u1", 3, None, "hello?") is ShowResult.REFUSED  # non-int
    assert target.last_reason == "revision regression"
    assert len(client.calls) == before  # NO request on either refusal


def test_show_replace_uses_utf16_offsets_vs_map_span_ground_truth():
    target, client, _ = _bound(
        [_apply(), _read(text="hi! abc🫡", owned=[0, 9]), _apply()]
    )
    target.show(1, "u1", 1, 0, _ASTRAL)  # insert: 9 UTF-16 units (🫡 counts 2)
    target.show(1, "u1", 2, 1, "hi! xyz🫡!")  # divergence → ONE replace
    replace = [c for c in client.calls if c[0] == "replace"]
    assert len(replace) == 1
    op, timeout, fields = replace[0]
    assert timeout == _SHOW_TIMEOUT_S
    expected_end = map_span(_ASTRAL, 0, len(_ASTRAL), TargetUnits.UTF16_UNITS)[
        1
    ]  # 9, not 8
    assert fields["start"] == 0
    assert fields["end"] == expected_end  # EXACT map_span ground truth
    assert fields["text"] == "hi! xyz🫡!"


def test_show_replace_uses_absolute_server_offsets_not_zero():
    # The fragment begins at UTF-16 unit 6 ("user: " before it) — the replace
    # MUST speak the server-reported absolute range, never 0-based guesses.
    target, client, _ = _bound(
        [_apply(), _read(text="user: hi", owned=[6, 8]), _apply()]
    )
    target.show(1, "u1", 1, 0, "hi")  # insert at caret (unit 6)
    target.show(1, "u1", 2, 1, "hey")  # divergence → replace [6, 8)
    replace = [c for c in client.calls if c[0] == "replace"][0]
    assert replace[2] == {"start": 6, "end": 8, "text": "hey"}


def test_show_no_reply_is_unknown_and_never_re_sent():
    target, client, _ = _bound([None])
    res = target.show(1, "u1", 1, 0, "hello")
    assert res is ShowResult.UNKNOWN
    assert target.last_reason == "pi socket no reply"
    assert client.ops == ["read", "insert"]  # exactly ONE insert attempt — no repeat


def test_show_refused_carries_editor_reason_verbatim():
    target, client, _ = _bound(
        [
            {
                "ok": True,
                "result": "refused",
                "reason": "range not owned",
                "cursor": {"line": 0, "col": 1},
                "changes": 0,
            }
        ]
    )
    res = target.show(1, "u1", 1, 0, "hello")
    assert res is ShowResult.REFUSED
    assert target.last_reason == "range not owned"


def test_show_error_reply_refused_with_error_string():
    target, client, _ = _bound([{"ok": False, "error": "editor not ready"}])
    res = target.show(1, "u1", 1, 0, "hello")
    assert res is ShowResult.REFUSED
    assert target.last_reason == "editor not ready"


def test_show_unknown_result_value_maps_unknown():
    target, client, _ = _bound([{"ok": True, "result": "weird"}])
    res = target.show(1, "u1", 1, 0, "hello")
    assert res is ShowResult.UNKNOWN
    assert target.last_reason == "editor result 'weird'"


def test_show_unchanged_reply_adopts_span():
    target, client, _ = _bound(
        [
            {
                "ok": True,
                "result": "unchanged",
                "cursor": {"line": 0, "col": 0},
                "changes": 0,
            }
        ]
    )
    res = target.show(1, "u1", 1, 0, "hello")
    assert res is ShowResult.UNCHANGED
    # adopted: the very same span is now zero-diff (no further request)
    before = len(client.calls)
    assert target.show(1, "u1", 2, 0, "hello") is ShowResult.UNCHANGED
    assert len(client.calls) == before


def test_show_state_advances_only_on_applied():
    target, client, _ = _bound([{"ok": True, "result": "refused", "reason": "dirty"}])
    assert target.show(1, "u1", 1, 0, "hello") is ShowResult.REFUSED
    # the refused span was NOT adopted: the same span is still not zero-diff
    client._replies.append(_apply())
    client._replies.append(_read(text="hello", owned=[0, 5]))
    assert target.show(1, "u1", 2, 0, "hello") is ShowResult.APPLIED  # revision still 0


# ---- replace-path bind: verify BEFORE any mutating request; never repair ----


def test_replace_bind_read_failure_refuses_without_replace():
    target, client, _ = _bound(
        [_apply(), None]
    )  # insert applied; bind read never replies
    assert (
        target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    )  # op landed; bind deferred
    res = target.show(1, "u1", 2, 1, "help!")  # TRUE divergence → bind attempt
    assert res is ShowResult.REFUSED
    assert target.last_reason == "pi socket no reply"
    assert "replace" not in client.ops  # NOTHING was sent on guessed coords


def test_replace_bind_dirty_refused():
    # Bind attempt #1 (eager, after the applied insert) and attempt #2 (before
    # the replace) both hit a dirty editor — refused, NO replace ever sent.
    target, client, _ = _bound(
        [
            _apply(),
            _read(text="hello typed", dirty=True),
            _read(text="hello typed", dirty=True),
        ]
    )
    assert (
        target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    )  # op landed; bind deferred
    res = target.show(1, "u1", 2, 1, "help?")  # TRUE divergence → bind retry
    assert res is ShowResult.REFUSED
    assert target.last_reason == "editor dirty"
    assert client.ops == [
        "read",
        "insert",
        "read",
        "read",
    ]  # acquire+insert+bind×2 — no replace


def test_replace_bind_inconsistent_length_refused():
    # Server owns 3 units; our accounting says 5 — refuse, never repair.
    target, client, _ = _bound(
        [_apply(), _read(text="abcde", owned=[0, 3]), _read(text="abcde", owned=[0, 3])]
    )
    assert (
        target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    )  # bind failed: mismatch deferred
    res = target.show(1, "u1", 2, 1, "world")
    assert res is ShowResult.REFUSED
    assert target.last_reason == "inconsistent owned range"
    assert client.ops == ["read", "insert", "read", "read"]  # verify, NEVER repair


def test_replace_bind_owned_null_refused():
    target, client, _ = _bound(
        [_apply(), _read(text="", owned=None), _read(text="", owned=None)]
    )
    assert (
        target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    )  # applied; bind deferred
    res = target.show(1, "u1", 2, 1, "world")
    assert res is ShowResult.REFUSED
    assert (
        target.last_reason == "inconsistent owned range"
    )  # we applied ops — owned cannot be null
    assert client.ops == ["read", "insert", "read", "read"]  # bind twice, no replace


def test_replace_bind_success_then_replace_fires():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")  # applied + bound in the same call
    res = target.show(1, "u1", 2, 1, "help!")  # divergence; NO extra bind read needed
    assert res is ShowResult.APPLIED
    replace = [c for c in client.calls if c[0] == "replace"][0]
    assert replace[2] == {"start": 0, "end": 5, "text": "help!"}
    assert client.ops == ["read", "insert", "read", "replace"]


# --------------------------------------------------------------- finalize ---


def test_finalize_matching_settles_without_any_edit():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")
    before = len(client.calls)
    assert (
        target.finalize(1, "u1", 2, 1, "hello") is ShowResult.UNCHANGED
    )  # matching ⇒ NO edit
    assert len(client.calls) == before  # zero requests
    assert (
        target.finalize(1, "u1", 3, 1, "hello") is ShowResult.REFUSED
    )  # duplicate final
    assert target.last_reason == "utterance closed"
    assert len(client.calls) == before  # ...and no request for it either


def test_finalize_differing_goes_through_show_then_settles():
    target, client, _ = _bound(
        [_apply(), _read(text="hello", owned=[0, 5]), _apply(), _apply()]
    )
    target.show(1, "u1", 1, 0, "hello")
    assert target.finalize(1, "u1", 2, 1, "help!") is ShowResult.APPLIED  # ONE replace
    assert [c[0] for c in client.calls[-1:]] == ["replace"]
    assert target.finalize(1, "u1", 3, 2, "help!") is ShowResult.REFUSED  # settled
    assert target.last_reason == "utterance closed"


def test_finalize_without_partial_inserts_once():
    target, client, _ = _bound([_apply()])  # live=false path: final arrives cold
    assert target.finalize(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    assert client.ops == ["read", "insert", "read"]  # insert + the first-bind read
    assert client.calls[1] == ("insert", _SHOW_TIMEOUT_S, {"text": "hello"})


def test_finalize_not_acquired_refuses():
    client = _FakeClient()
    target = PiEditorTarget(client)
    assert target.finalize(1, "u", 1, 0, "x") is ShowResult.REFUSED
    assert target.last_reason == "not acquired"


# ----------------------------------------------------------------- cancel ---


def test_cancel_nothing_pending_is_unchanged_with_no_request():
    target, client, _ = _bound()
    assert target.cancel() is ShowResult.UNCHANGED  # G2 trace_07 pin
    assert target.last_reason == "nothing pending"
    assert client.calls == [("read", _ACQUIRE_TIMEOUT_S, {})]  # NO cancel request


def test_cancel_pending_sends_one_op_and_resets():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")
    assert target.cancel() is ShowResult.APPLIED
    assert client.calls[-1] == ("cancel", _SHOW_TIMEOUT_S, {})  # ONE op, no range args
    # ownership cleared server-side ⇒ client coords reset; second cancel: nothing pending
    before = len(client.calls)
    assert target.cancel() is ShowResult.UNCHANGED
    assert len(client.calls) == before
    assert target._owned_start_u16 == -1 and target._owned_len_u16 == 0  # coords reset


def test_cancel_applied_closes_utterance_against_late_strays():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), _apply()])
    target.show(1, "u1", 1, 0, "hello")
    assert target.cancel() is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 1, "hello?") is ShowResult.REFUSED
    assert (
        target.last_reason == "utterance closed"
    )  # cancelled utterance never mutates again


def test_cancel_no_reply_is_unknown():
    target, client, _ = _bound([_apply(), _read(text="hello", owned=[0, 5]), None])
    assert target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    assert target.cancel() is ShowResult.UNKNOWN
    assert target.last_reason == "pi socket no reply"


def test_cancel_refused_carries_editor_reason():
    target, client, _ = _bound(
        [
            _apply(),
            _read(text="hello", owned=[0, 5]),
            {"ok": True, "result": "refused", "reason": "dirty"},
        ]
    )
    assert target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    assert target.cancel() is ShowResult.REFUSED
    assert target.last_reason == "dirty"
    assert target._last_applied_span == "hello"  # uncertain state: NOTHING was repaired


def test_cancel_not_acquired_refuses():
    client = _FakeClient()
    target = PiEditorTarget(client)
    assert target.cancel() is ShowResult.REFUSED
    assert target.last_reason == "not acquired"


# ------------------------------------------------------------------ leave ---


def test_leave_clears_binding_first_and_never_writes_after():
    target, client, _ = _bound([_apply()])
    target.show(1, "u1", 1, 0, "hello")
    target.leave()
    assert target._binding is None  # cleared FIRST
    assert client.closed == 1  # hung up — v1 has NO leave op
    assert client.ops == ["read", "insert", "read"]  # NO post-stop request
    assert target.show(1, "u2", 1, 0, "x") is ShowResult.REFUSED
    assert target.last_reason == "not acquired"
    assert target.finalize(1, "u2", 1, 0, "x") is ShowResult.REFUSED
    assert target.cancel() is ShowResult.REFUSED
    assert client.ops == ["read", "insert", "read"]  # still zero writes after leave


def test_leave_is_idempotent_and_never_raises():
    target, client, _ = _bound()
    target.leave()
    target.leave()  # second leave: pure no-op
    assert client.closed == 1
    dead = _FakeClient()
    dead.close = lambda: (_ for _ in ()).throw(OSError("boom"))
    t2 = PiEditorTarget(dead)
    t2._binding = PiEditorBinding(
        sock_path="p", owned_start_u16=-1, owned_len_u16=0, revision=0
    )
    t2.leave()  # a dead client must not propagate
    assert t2._binding is None


# ------------------------------------------------------------------- misc ---


def test_units_is_utf16_units():
    assert PiEditorTarget.units is TargetUnits.UTF16_UNITS


def test_to_u16_span_matches_map_span_including_astral():
    text = "Zoë — naïve 日本語 🫡"
    assert PiEditorTarget.to_u16_span(text, 0, len(text)) == map_span(
        text, 0, len(text), TargetUnits.UTF16_UNITS
    )
    # 🫡 counts 2: the u16 span end EXCEEDS the char count by exactly 1 (one astral char)
    assert PiEditorTarget.to_u16_span(text, 0, len(text))[1] == len(text) + 1


def test_binding_is_frozen():
    b = PiEditorBinding(sock_path="p", owned_start_u16=-1, owned_len_u16=0, revision=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.revision = 5


class _HaltRecorder:
    def __init__(self):
        self.halts = []

    def halt_for_takeover(self, reason):
        self.halts.append(reason)


class _LeavingTarget:
    def __init__(self):
        self.left = 0

    def leave(self):
        self.left += 1


# ---------------------------------------------------------- takeover latch ---


def test_takeover_event_halts_exactly_once_with_fixed_reason():
    client = _FakeClient()
    recorder = _HaltRecorder()
    watch = PiEditorTakeoverWatch(controller=recorder)
    watch.attach(client)
    assert client.on_event == watch.on_event  # attach wired the feed
    client.on_event({"event": "takeover", "source": "key"})
    assert recorder.halts == ["pi-editor key takeover"]
    assert watch.revocations == 1 and watch.reason == "pi-editor key takeover"
    client.on_event(
        {"event": "takeover", "source": "key"}
    )  # second event: latched away
    client.on_event({"event": "takeover", "source": "paste"})
    assert recorder.halts == ["pi-editor key takeover"]  # exactly ONE halt, ONE reason
    assert watch.revocations == 1


def test_watch_leaves_target_before_halting():
    client = _FakeClient()
    tgt = _LeavingTarget()
    recorder = _HaltRecorder()
    order = []
    tgt.leave = lambda: order.append("leave")
    recorder.halt_for_takeover = lambda r: order.append(("halt", r))
    watch = PiEditorTakeoverWatch(controller=recorder, target=tgt)
    watch.attach(client)
    client.on_event({"event": "takeover", "source": "key"})
    assert order == [
        "leave",
        ("halt", "pi-editor key takeover"),
    ]  # leave FIRST, then halt


def test_client_routes_events_and_replies_disjointly():
    """CRITICAL #1 at the transport level: events NEVER parse as replies."""
    client = PiEditorClient("/nonexistent.sock")  # constructor only — no dial
    got = []
    client.on_event = got.append
    client._on_line(b'{"event": "takeover", "source": "key"}')
    client._on_line(b'{"ok": true, "result": "applied"}')
    client._on_line(b"not json at all")
    client._on_line(b"[1, 2]")
    assert got == [{"event": "takeover", "source": "key"}]
    with client._reply_cv:
        assert client._reply == {"ok": True, "result": "applied"}


def test_watch_ignores_non_takeover_events_and_op_replies():
    client = _FakeClient()
    recorder = _HaltRecorder()
    watch = PiEditorTakeoverWatch(controller=recorder)
    watch.attach(client)
    client.on_event({"ok": True, "result": "applied"})  # a reply shape is NOT an event
    client.on_event({"event": "render"})  # unknown events dropped
    client.on_event("garbage")  # non-dicts dropped
    assert recorder.halts == [] and watch.revocations == 0


def test_watch_missing_source_defaults_to_key():
    recorder = _HaltRecorder()
    watch = PiEditorTakeoverWatch(controller=recorder)
    watch.on_event({"event": "takeover"})
    assert recorder.halts == ["pi-editor key takeover"]


def test_watch_without_controller_still_latches_and_never_raises():
    watch = PiEditorTakeoverWatch()
    watch.on_event({"event": "takeover", "source": "key"})
    assert watch.revocations == 1 and watch.reason == "pi-editor key takeover"
    watch.on_event({"event": "takeover"})  # latched — no second reason


def test_watch_survives_raising_controller_and_target():
    class _Boom:
        def halt_for_takeover(self, reason):
            raise RuntimeError("halt seam exploded")

    class _BoomTarget:
        def leave(self):
            raise RuntimeError("leave exploded")

    watch = PiEditorTakeoverWatch(controller=_Boom(), target=_BoomTarget())
    watch.on_event({"event": "takeover", "source": "key"})  # must not raise outward
    assert watch.revocations == 1


def test_watch_detach_unwires_feed():
    client = _FakeClient()
    watch = PiEditorTakeoverWatch(controller=_HaltRecorder())
    watch.attach(client)
    watch.close()
    assert client.on_event is None  # feed unwired
    assert watch.revocations == 0


# ===========================================================================
# Part B — socket-level tests: an in-process fake extension (S1 protocol v1)
# ===========================================================================


class _FakeExtension:
    """Threaded AF_UNIX JSONL server honoring S1 protocol v1 (.pi/extensions/voice-editor.ts).

    Buffer semantics mirror the landed extension exactly: absolute UTF-16
    offsets (JS String.length units), owned=[start,end) extended by contiguous
    inserts / rewritten by replace / cleared by cancel, dirty+ONE takeover
    event on the first delegated keystroke while owned.
    """

    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.text = ""  # the buffer (python str; UTF-16 units via _u16len)
        self.owned = None  # [start, end) UTF-16 units, or None
        self.dirty = False
        self.changes = 0
        self.requests = []  # op names served, in order
        self._events = []  # queued unsolicited event lines
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._listener = None
        self._conn = None
        self._thread = None

    # -- lifecycle --
    def start(self):
        os.makedirs(os.path.dirname(self.sock_path), exist_ok=True)
        try:
            os.unlink(self.sock_path)
        except FileNotFoundError:
            pass
        lst = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        lst.bind(self.sock_path)
        lst.listen(4)
        lst.settimeout(0.05)
        self._listener = lst
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        for s in (self._conn, self._listener):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            os.unlink(self.sock_path)
        except FileNotFoundError:
            pass

    # -- test-side event injection (mirror handleInput's first-key rule) --
    def push_takeover(self, force=False):
        with self._lock:
            if force or (self.owned is not None and not self.dirty):
                self.dirty = True
                self._events.append({"event": "takeover", "source": "key"})
                return True
            return False

    # -- UTF-16 helpers (JS String semantics) --
    @staticmethod
    def _u16len(s):
        return sum(2 if ord(c) > 0xFFFF else 1 for c in s)

    @staticmethod
    def _u16_to_char(s, off):
        units = 0
        for i, ch in enumerate(s):
            if units == off:
                return i
            units += 2 if ord(ch) > 0xFFFF else 1
            if units > off:
                raise ValueError("mid-surrogate offset")
        if units == off:
            return len(s)
        raise ValueError("offset past end")

    # -- serving --
    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._conn = conn
            self._pump(conn)
            self._conn = None

    def _pump(self, conn):
        conn.settimeout(0.05)
        buf = b""
        while not self._stop.is_set():
            while self._events:  # unsolicited events, never a reply
                ev = self._events.pop(0)
                conn.sendall((json.dumps(ev) + "\n").encode("utf-8"))
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    rep = self._handle(line.decode("utf-8", "replace"))
                    conn.sendall((json.dumps(rep) + "\n").encode("utf-8"))

    # -- protocol v1 dispatch (mirror voice-editor.ts) --
    def _handle(self, line):
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"malformed JSON: {exc}"}
        if not isinstance(req, dict):
            return {"ok": False, "error": "request must be a JSON object"}
        op = req.get("op")
        with self._lock:
            self.requests.append(op)
            if op == "insert":
                if not isinstance(req.get("text"), str):
                    return {"ok": False, "error": "insert: 'text' must be a string"}
                return self._finish(self._op_insert(req["text"]))
            if op == "replace":
                start, end, text = req.get("start"), req.get("end"), req.get("text")
                if (
                    not isinstance(text, str)
                    or not isinstance(start, int)
                    or not isinstance(end, int)
                ):
                    return {
                        "ok": False,
                        "error": "replace: 'start', 'end' (numbers) and 'text' (string) required",
                    }
                return self._finish(self._op_replace(start, end, text))
            if op == "cancel":
                return self._finish(self._op_cancel())
            if op == "read":
                return {
                    "ok": True,
                    "result": "applied",
                    "text": self.text,
                    "cursor": {"line": 0, "col": self._u16len(self.text)},
                    "owned": None
                    if self.owned is None
                    else {"start": self.owned[0], "end": self.owned[1]},
                    "dirty": self.dirty,
                    "units": "utf-16",
                    "changes": self.changes,
                }
            return {"ok": False, "error": f"unknown op: {json.dumps(op)}"}

    def _finish(self, res):
        if not res.get("ok", True):
            return res
        return {
            **res,
            "cursor": {"line": 0, "col": self._u16len(self.text)},
            "changes": 1,
        }

    def _op_insert(self, text):
        caret_before = self.owned[1] if self.owned else self._u16len(self.text)
        i = self._u16_to_char(self.text, caret_before)
        after = self.text[:i] + text + self.text[i:]
        caret_after = caret_before + self._u16len(text)
        if self.owned and not self.dirty and caret_before == self.owned[1]:
            self.owned = [self.owned[0], caret_after]  # contiguous extension
        elif self.owned and not self.dirty and caret_before == self.owned[0]:
            self.owned = [caret_before, caret_after]  # head extension
        else:
            self.owned = [caret_before, caret_after]  # disown-and-reown
        self.text = after
        self.changes += 1
        return {"ok": True, "result": "applied"}

    def _op_replace(self, start, end, text):
        u16_len = self._u16len(self.text)
        if (
            not (isinstance(start, int) and isinstance(end, int))
            or start < 0
            or end > u16_len
            or start > end
        ):
            return {"ok": True, "result": "refused", "reason": "out_of_bounds"}
        if self.owned is None:
            return {"ok": True, "result": "refused", "reason": "range not owned"}
        if self.dirty:
            return {"ok": True, "result": "refused", "reason": "dirty"}
        if start < self.owned[0] or end > self.owned[1]:
            return {"ok": True, "result": "refused", "reason": "range not owned"}
        i0, i1 = self._u16_to_char(self.text, start), self._u16_to_char(self.text, end)
        nxt = self.text[:i0] + text + self.text[i1:]
        if nxt == self.text:
            return {"ok": True, "result": "unchanged"}
        self.text = nxt
        self.owned = [start, start + self._u16len(text)]
        self.changes += 1
        return {"ok": True, "result": "applied"}

    def _op_cancel(self):
        if self.owned is None:
            return {"ok": True, "result": "refused", "reason": "range not owned"}
        if self.dirty:
            return {"ok": True, "result": "refused", "reason": "dirty"}
        i0, i1 = (
            self._u16_to_char(self.text, self.owned[0]),
            self._u16_to_char(self.text, self.owned[1]),
        )
        nxt = self.text[:i0] + self.text[i1:]
        self.owned = None
        if nxt == self.text:
            return {"ok": True, "result": "unchanged"}
        self.text = nxt
        self.changes += 1
        return {"ok": True, "result": "applied"}


def _arm(sock_path):
    """Server + client + latched watch, all wired; returns (ext, client, target, watch, rec)."""
    ext = _FakeExtension(sock_path)
    ext.start()
    client = PiEditorClient(ext.sock_path)
    rec = _HaltRecorder()
    watch = PiEditorTakeoverWatch(controller=rec)
    watch.attach(client)
    target = PiEditorTarget(client)
    return ext, client, target, watch, rec


@pytest.fixture()
def session(tmp_path):
    """A started fake extension + connected adapter, torn down bounded."""
    ext, client, target, watch, rec = _arm(str(tmp_path / "pi-editor.sock"))
    yield ext, client, target, watch, rec
    client.close()
    ext.stop()


# ------------------------------------------------------- the full cycle ---


def test_full_arm_show2_finalize_cancel_cycle(session):
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    assert target.show(1, "u1", 1, 0, "hello") is ShowResult.APPLIED
    assert target.show(1, "u1", 2, 1, "hello world") is ShowResult.APPLIED
    assert ext.text == "hello world"
    assert ext.owned == [0, 11]
    # zero-diff: the third identical show emits NO request (R.1: 0 events)
    n = len(ext.requests)
    assert target.show(1, "u1", 3, 2, "hello world") is ShowResult.UNCHANGED
    assert len(ext.requests) == n
    # matching final settles with NO edit; nothing-pending cancel sends NO request
    assert target.finalize(1, "u1", 4, 2, "hello world") is ShowResult.UNCHANGED
    assert len(ext.requests) == n
    assert target.cancel() is ShowResult.UNCHANGED
    assert len(ext.requests) == n
    assert ext.requests == [
        "read",
        "insert",
        "read",
        "insert",
    ]  # the WHOLE cycle: 4 requests
    # our own op replies never trigger the takeover halt (pin d)
    assert watch.revocations == 0 and rec.halts == []


def test_replace_cycle_with_astral_payload_over_socket(session):
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, _ASTRAL) is ShowResult.APPLIED
    assert ext.text == _ASTRAL
    # 🫡 counts 2 UTF-16 units: owned end == map_span ground truth, NOT len()
    truth = map_span(_ASTRAL, 0, len(_ASTRAL), TargetUnits.UTF16_UNITS)[1]
    assert ext.owned == [0, truth]
    assert truth == len(_ASTRAL) + 1  # exactly one surrogate pair
    assert (
        target.show(1, "u", 2, 1, "hi! xyz🫡!") is ShowResult.APPLIED
    )  # divergence → ONE replace
    assert ext.text == "hi! xyz🫡!"
    assert ext.owned == [0, map_span("hi! xyz🫡!", 0, 9, TargetUnits.UTF16_UNITS)[1]]


def test_replace_uses_absolute_server_offsets_over_socket(session):
    ext, client, target, watch, rec = session
    ext.text = "user: "  # pre-existing user text (6 units)
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, "hi") is ShowResult.APPLIED
    assert ext.text == "user: hi" and ext.owned == [6, 8]
    assert target.show(1, "u", 2, 1, "hey") is ShowResult.APPLIED
    assert ext.text == "user: hey"  # replaced the ABSOLUTE range [6, 8)
    assert ext.owned == [6, 9]


def test_cancel_with_pending_removes_fragment_over_socket(session):
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, "hello") is ShowResult.APPLIED
    assert ext.text == "hello"
    assert target.cancel() is ShowResult.APPLIED
    assert ext.text == "" and ext.owned is None  # ONE op removed the fragment
    assert target.cancel() is ShowResult.UNCHANGED  # nothing pending (no request)
    assert ext.text == ""


def test_takeover_halts_exactly_once_over_socket(session):
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, "hello") is ShowResult.APPLIED
    assert watch.revocations == 0  # op replies never halt (pin d)
    assert ext.push_takeover() is True  # the delegated keystroke
    assert _wait_for(lambda: watch.revocations == 1)
    assert rec.halts == ["pi-editor key takeover"]
    assert ext.dirty
    # a second event is latched away — exactly ONE halt, ONE reason per watch
    assert ext.push_takeover(force=True)
    _time.sleep(0.1)
    assert watch.revocations == 1 and rec.halts == ["pi-editor key takeover"]
    # the extension now refuses REPLACE mutations — the adapter propagates the reason
    assert target.show(1, "u", 2, 1, "different") is ShowResult.REFUSED
    assert target.last_reason == "dirty"


def test_server_death_mid_op_reports_unknown(session):
    ext, client, target, watch, rec = session
    attempts = []
    real_request = client.request

    def counting(op, timeout=_SHOW_TIMEOUT_S, **fields):
        attempts.append(op)
        return real_request(op, timeout, **fields)

    client.request = counting
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, "hello") is ShowResult.APPLIED
    ext.stop()  # the editor (process) died mid-session
    assert target.show(1, "u", 2, 1, "hello!") is ShowResult.UNKNOWN
    assert target.last_reason == "pi socket no reply"
    assert attempts.count("insert") == 2  # the dead op attempted ONCE — never re-sent


def test_reacquire_after_leave_over_socket(session):
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, "hello") is ShowResult.APPLIED
    assert target.cancel() is ShowResult.APPLIED  # remove the fragment BEFORE stopping
    target.leave()
    assert target.show(1, "u2", 1, 0, "x") is ShowResult.REFUSED  # "not acquired"
    acq = target.acquire()  # same client duck re-dials onto a CLEAN field
    assert acq.ok, acq.reason
    assert target.show(1, "u2", 1, 0, "next") is ShowResult.APPLIED
    assert ext.text == "next"


def test_reacquire_refuses_stranded_fragment_over_socket(session):
    """A fragment left visible by stop is server-owned — acquire NEVER adopts it."""
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    assert target.show(1, "u", 1, 0, "hello") is ShowResult.APPLIED
    target.leave()  # no cancel: the fragment stays visible AND server-owned
    res = target.acquire()
    assert not res.ok and res.reason == "editor owns fragment"


def test_default_socket_path_via_xdg_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    expected = os.path.join(str(tmp_path), "voice-typing", "pi-editor.sock")
    ext = _FakeExtension(expected)
    ext.start()
    client = PiEditorClient()  # default path resolution
    target = PiEditorTarget(client)
    try:
        assert client.sock_path == expected
        assert target.acquire().ok
        assert target.show(1, "u", 1, 0, "xdg") is ShowResult.APPLIED
        assert ext.text == "xdg"
    finally:
        client.close()
        ext.stop()


def test_stream_survives_many_ops_over_one_connection(session):
    """One line in → one line out: a long op stream never desyncs the framing."""
    ext, client, target, watch, rec = session
    assert target.acquire().ok
    span = ""
    for i in range(1, 13):  # 12 contiguous inserts over ONE socket
        span += f"w{i} "
        assert target.show(1, "u", i, i - 1, span) is ShowResult.APPLIED
    assert ext.text == span
    assert ext.owned == [0, _FakeExtension._u16len(span)]
