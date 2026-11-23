"""tests/test_ime_takeover.py — P1.M4.T4.S1 detector matrix + watch wiring + halt.

Pure-python: no compositor, no daemon, no subprocess. Fakes per the repo
idiom (test_ime_manager's injection, test_ime_host's fake client). Pins:

  (b) the detector matrix — ordinary key ⇒ `user key <code>`; modifier-only
      DOWN/UP never revoke (down-set maintained); KEY_D with ALT+SUPER held ⇒
      chord ignored (covers BOTH §4.10 binds); surrounding_text divergence
      (caret/selection) revokes with a non-input_method cause, matching OUR
      accounting is benign, cause=input_method never revokes; deactivate
      revokes; NO event ⇒ nothing happens (pointer motion alone is not an
      edit); `unavailable` is silent here (the manager owns that emission).
  (c) revocation — exactly ONE target.leave(); post-leave ops refuse "not
      acquired" with ZERO further requests; the controller halts with ONE
      reason, idempotent, never masked.
  (d) wiring — TakeoverWatch(proc, target, controller) subscribes; a detector
      or target fault cannot raise out of on_event; no double-emission.
  (e) logs carry keycodes/reasons ONLY — never recognition text.

The arming chord is matched BY COMPOSITION, never by a timer (there is no
grace window in this module — the Level-4 grep is the static proof; the
chord-release tests here are the behavioral one).
"""

from __future__ import annotations

import logging

from voice_typing.bulk_controller import BulkController
from voice_typing.bulk_delivery import ShowResult
from voice_typing.ime.takeover import (
    CHORD_KEY,
    CHORD_MODS,
    KEY_D,
    MODIFIER_KEYCODES,
    MODIFIER_NAMES,
    TakeoverDetector,
    TakeoverWatch,
)
from voice_typing.ime.target import ImeTarget

# ---- event builders (the manager's forwarded dict shapes) -------------------


def _key(key, state):
    return {"ev": "grab_key", "t_ms": 1.0, "key": key, "state": state}


def _st(cursor, anchor, head="…"):
    return {
        "ev": "surrounding_text",
        "t_ms": 1.0,
        "bytes": 32,
        "cursor": cursor,
        "anchor": anchor,
        "head": head,
    }


def _cause(v):
    return {"ev": "text_change_cause", "t_ms": 1.0, "args": [v]}


DEACTIVATE = {"ev": "deactivate", "t_ms": 1.0}


# ---- fakes -------------------------------------------------------------------


class _FakeTarget:
    def __init__(self):
        self.leaves = 0

    def leave(self):
        self.leaves += 1


class _FakeController:
    def __init__(self):
        self.halts = []

    def halt_for_takeover(self, reason):
        self.halts.append(reason)


class _FakeProc:
    """Attachable feed seam (a settable on_event attribute, fake-style)."""

    def __init__(self):
        self.on_event = None


class _ScriptedProc:
    """ImeTarget's injection seam: records requests, pops scripted replies."""

    def __init__(self, replies):
        self.calls = []
        self._replies = list(replies)

    def request(self, cmd, timeout=None, **fields):
        self.calls.append((cmd, timeout, fields))
        return self._replies.pop(0)


class _RaisingDetector:
    def feed(self, ev):
        raise RuntimeError("detector boom")


class _RaisingTarget:
    def __init__(self):
        self.leaves = 0

    def leave(self):
        self.leaves += 1
        raise RuntimeError("dead target")


def _acquire_reply(text="héllo ", cursor=7, anchor=7, revision=3):
    return {
        "id": 1,
        "reply": "acquire",
        "ok": True,
        "handle": "im7",
        "revision": revision,
        "text": text,
        "cursor": cursor,
        "anchor": anchor,
        "snapshot_truncated": False,
    }


# ---------------------------------------------------------------------------
# (b) the detector matrix
# ---------------------------------------------------------------------------


def test_keycode_constants_match_the_pinned_table():
    assert KEY_D == 32
    assert CHORD_KEY == KEY_D
    assert MODIFIER_KEYCODES == frozenset(
        {29, 97, 56, 100, 42, 54, 58, 69, 70, 125, 126}
    )
    assert MODIFIER_KEYCODES == frozenset(
        MODIFIER_NAMES
    )  # the name map covers exactly these
    assert CHORD_MODS == frozenset({"ALT", "SUPER"})


def test_ordinary_key_press_revokes():
    d = TakeoverDetector()
    assert d.feed(_key(30, 1)) == "user key 30"  # the row-O probe key family
    assert d.feed(_key(KEY_D, 1)) == "user key 32"  # D alone (no mods held) is ordinary


def test_modifier_only_press_and_release_never_revoke_and_maintain_the_set():
    d = TakeoverDetector()
    for code in sorted(MODIFIER_KEYCODES):
        assert d.feed(_key(code, 1)) is None  # DOWN
        assert d.feed(_key(code, 0)) is None  # UP
    # the down-set is genuinely maintained: chord composes only while held
    d.feed(_key(56, 1))  # LALT down
    d.feed(_key(125, 1))  # LSUPER down
    assert d.feed(_key(KEY_D, 1)) is None  # chord → ignored
    d.feed(_key(125, 0))  # super up
    assert d.feed(_key(KEY_D, 1)) == "user key 32"  # ALT alone is NOT the chord


def test_chord_ignored_normal_bind_ctrl_alt_super_d():
    d = TakeoverDetector()
    d.feed(_key(29, 1))  # LCTRL
    d.feed(_key(56, 1))  # LALT
    d.feed(_key(125, 1))  # LSUPER
    assert d.feed(_key(KEY_D, 1)) is None  # §4.10 normal bind → ignored


def test_chord_ignored_lite_bind_alt_super_d():
    d = TakeoverDetector()
    d.feed(_key(100, 1))  # RALT
    d.feed(_key(126, 1))  # RSUPER
    assert d.feed(_key(KEY_D, 1)) is None  # §4.10 lite bind → ignored (⊇ match)


def test_chord_requires_both_alt_and_super():
    d = TakeoverDetector()
    d.feed(_key(56, 1))  # ALT only
    assert d.feed(_key(KEY_D, 1)) == "user key 32"
    d2 = TakeoverDetector()
    d2.feed(_key(29, 1))  # CTRL only
    d2.feed(_key(56, 1))
    assert d2.feed(_key(KEY_D, 1)) == "user key 32"


def test_chord_is_exact_key_d_not_any_key():
    d = TakeoverDetector()
    d.feed(_key(56, 1))
    d.feed(_key(125, 1))
    assert d.feed(_key(31, 1)) == "user key 31"  # S with the mods held is ordinary


def test_chord_composition_not_grace_window():
    """The chord is ignored whenever the mods are DOWN and only then — no timer,
    no latch: after the chord, a plain D is an ordinary user key again."""
    d = TakeoverDetector()
    d.feed(_key(56, 1))
    d.feed(_key(125, 1))
    assert d.feed(_key(KEY_D, 1)) is None  # the arming chord itself
    d.feed(_key(56, 0))  # user releases the mods
    d.feed(_key(125, 0))
    assert d.feed(_key(KEY_D, 1)) == "user key 32"  # same keycode, mods up → revoke


def test_non_modifier_release_never_revokes_even_after_mods_released_first():
    """Key-release ordering must not betray the chord: the user may release
    the modifiers BEFORE the chord key. Releases never revoke (composition is
    evaluated on press only) — also why no synthetic key event can revoke."""
    d = TakeoverDetector()
    d.feed(_key(56, 1))
    d.feed(_key(125, 1))
    assert d.feed(_key(KEY_D, 1)) is None  # chord press ignored
    d.feed(_key(56, 0))  # mods released first
    d.feed(_key(125, 0))
    assert d.feed(_key(KEY_D, 0)) is None  # chord key release — still silent


def test_grab_key_guards_and_missing_state_defaults_to_press():
    d = TakeoverDetector()
    assert d.feed({"ev": "grab_key"}) is None  # no key field
    assert d.feed(_key(True, 1)) is None  # non-int keycode
    # missing state ⇒ treated as a press (a grabbed user key must not be
    # silently swallowed); the real host always emits both fields.
    assert d.feed({"ev": "grab_key", "key": 30}) == "user key 30"


def test_surrounding_text_matching_our_accounting_is_benign():
    d = TakeoverDetector()
    d.note_acquired(10)
    assert d.feed(_st(10, 10)) is None  # caret at expectation, no selection
    d.note_committed(3)
    assert d.feed(_st(13, 13)) is None  # our commit advanced the formula


def test_caret_moved_revokes():
    d = TakeoverDetector()
    d.note_acquired(10)
    assert d.feed(_st(12, 12)) == "caret moved"


def test_selection_present_revokes():
    d = TakeoverDetector()
    d.note_acquired(10)
    assert d.feed(_st(10, 4)) == "selection present"  # anchor behind the caret
    assert d.feed(_st(5, 9)) == "selection present"  # any anchor≠cursor diverges


def test_selection_precedes_caret_moved_like_recheck():
    d = TakeoverDetector()
    d.note_acquired(10)
    assert d.feed(_st(12, 4)) == "selection present"  # recheck()'s precedence order


def test_input_method_cause_never_revokes_and_adopts_the_new_caret():
    d = TakeoverDetector()
    d.note_acquired(10)
    d.feed(_cause(0))  # cause cycle: input_method
    assert d.feed(_st(16, 16)) is None  # OUR commit landing — benign…
    d.feed(_cause(1))  # …and the expectation ADOPTED 16:
    assert d.feed(_st(10, 10)) == "caret moved"  # the old caret now diverges
    d2 = TakeoverDetector()
    d2.note_acquired(10)
    d2.feed(_cause(0))
    assert d2.feed(_st(16, 3)) is None  # input_method ⇒ never revokes


def test_other_cause_divergence_revokes():
    d = TakeoverDetector()
    d.note_acquired(10)
    d.feed(_cause(1))  # cause: other (the user edited)
    assert d.feed(_st(12, 12)) == "caret moved"
    assert d.feed(_st(12, 3)) == "selection present"


def test_unknown_cause_divergence_revokes():
    """No text_change_cause seen at all → not attributable to us → revoke."""
    d = TakeoverDetector()
    d.note_acquired(10)
    assert d.feed(_st(11, 11)) == "caret moved"


def test_surrounding_text_before_acquire_is_advisory():
    d = TakeoverDetector()
    assert d.feed(_st(5, 5)) is None  # no expectation yet — nothing to judge
    assert d.feed({"ev": "surrounding_text"}) is None  # malformed — never guess


def test_deactivate_revokes():
    assert TakeoverDetector().feed(DEACTIVATE) == "deactivated"


def test_unavailable_is_silent_manager_owns_that_emission():
    """unavailable/child death must NOT double-emit: the manager already fired
    unsupported/fault exactly once; the wiring treats THAT as revocation."""
    assert TakeoverDetector().feed({"ev": "unavailable", "t_ms": 1.0}) is None


def test_advisory_events_are_all_silent():
    d = TakeoverDetector()
    for ev in (
        {"ev": "activate"},
        {"ev": "done", "dones": 2},
        {"ev": "keymap", "args": [1, 0]},
        {"ev": "modifiers", "args": [0, 0, 0, 0]},
        {"ev": "repeat_info", "args": [40, 400]},
        {"ev": "bogus"},
    ):
        assert d.feed(ev) is None, ev


# ---------------------------------------------------------------------------
# (c)+(d) watch wiring + revocation
# ---------------------------------------------------------------------------


def test_no_events_nothing_happens():
    """Pointer motion alone generates NO IM event — a bound watch that is never
    fed can never revoke."""
    target, ctrl = _FakeTarget(), _FakeController()
    TakeoverWatch(target=target, controller=ctrl)
    assert target.leaves == 0 and ctrl.halts == []


def test_watch_revoke_leaves_once_halts_once_latched():
    target, ctrl = _FakeTarget(), _FakeController()
    watch = TakeoverWatch(target=target, controller=ctrl)
    watch.on_event(_key(30, 1))
    assert target.leaves == 1 and ctrl.halts == ["user key 30"]
    watch.on_event(_key(31, 1))  # a second takeover must NOT double-fire
    watch.on_event(DEACTIVATE)
    assert target.leaves == 1 and ctrl.halts == ["user key 30"]
    assert watch.revocations == 1 and watch.reason == "user key 30"


def test_watch_deactivate_path_revokes():
    target, ctrl = _FakeTarget(), _FakeController()
    watch = TakeoverWatch(target=target, controller=ctrl)
    watch.on_event(DEACTIVATE)
    assert target.leaves == 1 and ctrl.halts == ["deactivated"]


def test_watch_subscribes_proc_and_revokes_through_it():
    proc = _FakeProc()
    target, ctrl = _FakeTarget(), _FakeController()
    watch = TakeoverWatch(proc, target, ctrl)  # the PRP wiring shape
    assert proc.on_event == watch.on_event  # bound methods: == by (self, func)
    assert proc.on_event.__self__ is watch
    proc.on_event(_key(30, 1))
    assert target.leaves == 1 and ctrl.halts == ["user key 30"]


def test_watch_survives_detector_exception():
    target, ctrl = _FakeTarget(), _FakeController()
    watch = TakeoverWatch(target=target, controller=ctrl, detector=_RaisingDetector())
    watch.on_event(_key(30, 1))  # must not raise out of the reader-thread callback
    watch.on_event(DEACTIVATE)
    assert target.leaves == 0 and ctrl.halts == []


def test_watch_survives_target_fault_and_still_halts():
    ctrl = _FakeController()
    watch = TakeoverWatch(target=_RaisingTarget(), controller=ctrl)
    watch.on_event(DEACTIVATE)  # leave() raised — must not propagate
    assert ctrl.halts == ["deactivated"]


def test_watch_survives_controller_fault():
    class _RaisingController:
        def halt_for_takeover(self, reason):
            raise RuntimeError("halt boom")

    target = _FakeTarget()
    watch = TakeoverWatch(target=target, controller=_RaisingController())
    watch.on_event(_key(30, 1))  # must not raise
    assert target.leaves == 1


def test_logs_carry_reason_only_never_recognition_text(caplog):
    target, ctrl = _FakeTarget(), _FakeController()
    watch = TakeoverWatch(target=target, controller=ctrl)
    with caplog.at_level(logging.INFO, logger="voice_typing.ime.takeover"):
        watch.on_event(_st(3, 3, head="SECRET-RECOGNITION"))  # benign — never logged
        watch.on_event(_key(30, 1))  # revoke — reason only
    assert "SECRET-RECOGNITION" not in caplog.text  # (e): text-free logs
    assert "user key 30" in caplog.text


# ---------------------------------------------------------------------------
# (c) mutation-time re-checks against the REAL target/controller
# ---------------------------------------------------------------------------


def test_post_revoke_target_refuses_not_acquired_with_zero_requests():
    proc = _ScriptedProc([_acquire_reply(), {"id": 2, "reply": "leave", "ok": True}])
    target = ImeTarget(proc)
    watch = TakeoverWatch(target=target, controller=None)
    assert target.acquire().ok is True
    watch.on_event(_key(30, 1))  # user typed a key → revoke
    assert proc.calls[-1][0] == "leave"  # the revocation request went out
    assert target._binding is None  # binding cleared AT the target
    assert target.show(1, "u1", 1, 3, "hello") is ShowResult.REFUSED
    assert target.last_reason == "not acquired"  # the mutation-time guard
    assert [c[0] for c in proc.calls] == ["acquire", "leave"]  # ZERO requests after


def test_full_stack_takeover_halts_drains_queue_without_mutation():
    proc = _ScriptedProc([_acquire_reply(), {"id": 2, "reply": "leave", "ok": True}])
    target = ImeTarget(proc)
    ctrl = BulkController(target)
    watch = TakeoverWatch(target=target, controller=ctrl)
    assert ctrl.acquire() is True
    assert ctrl.arm(1) is True
    ctrl.on_partial("typed text", utterance="u1", seq=1, gen=1)  # queued, undispatched
    watch.on_event(_key(30, 1))  # a plain user key — revoke AT the target
    assert ctrl.is_active() is False
    assert (
        ctrl.stats()["stopped_reason"] == "takeover: user key 30"
    )  # ONE concise reason
    assert [c[0] for c in proc.calls] == [
        "acquire",
        "leave",
    ]  # queued op NEVER dispatched
    assert (
        target.show(1, "u1", 1, 99, "hello") is ShowResult.REFUSED
    )  # mutation-time guard
    assert target.last_reason == "not acquired"
    ctrl.on_partial("late", utterance="u2", seq=1, gen=1)  # post-stop → rejected
    ctrl.drain()
    assert [c[0] for c in proc.calls] == ["acquire", "leave"]  # still zero mutations
    watch.on_event(_key(31, 1))  # latched: no double-leave
    assert [c[0] for c in proc.calls] == ["acquire", "leave"]
