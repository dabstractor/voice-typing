"""tests/test_bulk_context_prompt.py — P1.M6.T3.S1: bulk-mode prompt source + triggers.

Pins BOTH modes' rolling-context-prompt content (PRD §4.2quater via the P1.M6.T3.S1
contract): in bulk-text mode the prompt source is the BulkController's OWN mirror of
target-CONFIRMED text (confirmed_visible() — R.5 three-value law #3), NEVER
_stream.committed (read-only in every mode; the bulk path never feeds nor writes it),
and _stream stays untouched all session (no cross-mode state bleed).

Triggers pinned here:
  - A: accepted-final enqueue (_bulk_handle_final, inside the is_active guard) —
       covers UNCHANGED finals, which fire NO on_applied;
  - B: finalize-APPLIED (_on_bulk_applied, kind == "finalize" only) — post-correction
       context; partial shows (kind == "show") deliberately never push;
  - D4: post-cancel context-free clear (_bulk_cancel) — a removed fragment must never
       become decode context (the stream-edit deliberate divergence);
  - the arm-time FIFO clear (set_prompt("") BEFORE the mic/arm cmd) still fires in
       bulk mode via the behavior-identical _clear_context_prompt extraction.

Gates pinned: config-off ⇒ zero set_prompt calls; degraded child (ready payload
context_prompt=False) ⇒ zero pushes; a fault-stopped controller pushes nothing even
though confirmed_visible() is retained; stream-edit keeps its _stream.committed source
(branch-order regression guard: the bulk branch must not shadow stream-edit).

NO CUDA, no subprocess, no live desktop (AGENTS.md): fake bundle over a fake
DeliveryTarget, a fake RecorderHost with a set_prompt recorder + settable
relay_identity, a spy typing backend (any call is a failure — the R.1 zero-legacy-call
law), and a spy stream with committed read/write counters. Real BulkController over the
fake target; the deterministic ctrl.drain() seam pumps the writer ops inline, so every
assertion is synchronous — no real waits except the re-arm thread (_wait_until).

Run:
    cd /home/dustin/projects/voice-typing
    timeout 300 .venv/bin/python -m pytest tests/test_bulk_context_prompt.py -q
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_typing import config as config_mod
from voice_typing import prompt_engine
from voice_typing.bulk_controller import BulkController
from voice_typing.bulk_delivery import AcquireResult, ShowResult
from voice_typing.daemon import VoiceTypingDaemon

# ---------------------------------------------------------------------------
# fakes — mirrors of the test_bulk_dispatch.py doubles (kept local so the
# existing suites stay untouched), extended with the prompt-spy host seam
# (the tests/test_context_prompt_refresh.py _PromptHost pattern).
# ---------------------------------------------------------------------------


class _Identity(NamedTuple):
    """Stand-in for recorder_host._RelayIdentity (the T1.S1 seam shape)."""

    session_gen: "int | None"
    utterance_id: "int | None"


class _SpyBackend:
    """The R.1 zero-legacy-call spy: the bulk path must NEVER reach it."""

    def __init__(self) -> None:
        self.typed: list = []
        self.backspaces: list[int] = []

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def press_backspace(self, n: int) -> None:
        self.backspaces.append(n)


class _BulkFakeFeedback:
    """Full recording Feedback double (the delivery surfaces included)."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []
        self.notifies: list[str] = []
        self.modes: list[str] = []
        self.finals: list[str] = []
        self.listening_states: list[bool] = []
        self.ducked_states: list[bool] = []
        self.delivery_modes: list[str] = []
        self.delivery_states: list[tuple[str, str]] = []  # (state, reason)
        self.confirmed_ops: list[str] = []
        self._state: dict = {
            "phase": "unloaded",
            "models_loaded": False,
            "partial": "",
            "last_final": "",
            "delivery_mode": "stream-edit",
            "delivery_state": "inactive",
            "delivery_reason": "",
            "last_confirmed_op": "",
        }

    def snapshot(self) -> dict:
        return dict(self._state)

    def update_partial(self, text: str) -> None:
        self.partials.append(text)
        self._state["partial"] = text

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)
        self._state["phase"] = phase

    def set_models_loaded(self, loaded: bool) -> None:
        self._state["models_loaded"] = bool(loaded)

    def set_mode(self, mode: str) -> None:
        self.modes.append(mode)

    def notify(self, msg: str) -> None:
        self.notifies.append(msg)

    def set_ducked(self, ducked: bool) -> None:
        self.ducked_states.append(bool(ducked))

    def set_listening(self, listening: bool) -> None:
        self.listening_states.append(bool(listening))

    def record_final(self, text: str) -> None:
        self.finals.append(text)
        self._state["last_final"] = text
        self._state["partial"] = text

    def set_delivery_mode(self, mode: str) -> None:
        self.delivery_modes.append(mode)
        self._state["delivery_mode"] = mode

    def set_delivery_state(self, state: str, reason: str = "") -> None:
        self.delivery_states.append((state, reason))
        self._state["delivery_state"] = state
        self._state["delivery_reason"] = reason

    def record_confirmed_op(self, op: str) -> None:
        self.confirmed_ops.append(op)
        self._state["last_confirmed_op"] = op


class _FakeHost:
    """RecorderHost duck with a SETTABLE relay_identity + a set_prompt recorder.

    `calls` records set_prompt AND set_microphone IN CALL ORDER — the single ordered
    list is what pins the arm-time FIFO rule (prompt clear must precede the mic/arm
    command), the tests/test_context_prompt_refresh.py _PromptHost pattern. The
    `context_prompt` ctor kwarg rides the 'ready' device dict exactly like the real
    child's additive S1 flag: False simulates the degraded child (_context_prompt_active
    resolves False ⇒ every push/clear gate short-circuits).
    """

    def __init__(
        self,
        cfg,
        feedback,
        latency,
        on_final,
        on_partial,
        on_speech,
        *,
        context_prompt: bool = True,
        **kw,
    ):
        self.cfg = cfg
        self.feedback = feedback
        self.latency = latency
        self.on_final = on_final
        self.on_partial = on_partial
        self.on_speech = on_speech
        self.relay_identity_value: "_Identity | None" = None
        self.spawn_calls = 0
        self.cancel_calls = 0
        self.mic: list[bool] = []
        self.calls: list[tuple[str, object]] = []  # ordered (kind, payload) recorder
        self.prompts: list[str] = []  # set_prompt text only, in order
        self.aborts = 0
        self._cancel_mark = False
        self.device = {
            "device": "cuda",
            "compute_type": "float32",
            "model": "small.en",
            "context_prompt": bool(context_prompt),  # S1's additive ready flag
        }

    def spawn(self, timeout: float = 180.0) -> bool:
        self.spawn_calls += 1
        return True

    @property
    def is_alive(self) -> bool:
        return True

    @property
    def pid(self):
        return None

    def set_microphone(self, on: bool) -> None:
        self.mic.append(on)
        self.calls.append(("mic", on))

    def set_prompt(self, text: str) -> None:
        self.prompts.append(text)
        self.calls.append(("prompt", text))

    def abort(self) -> None:
        self.aborts += 1

    def cancel(self) -> None:
        self.cancel_calls += 1

    def consume_cancel_mark(self) -> bool:
        marked = self._cancel_mark
        self._cancel_mark = False
        return marked

    def mark_cancel_sentinel(self) -> None:
        self._cancel_mark = True

    def relay_identity(self) -> "_Identity | None":
        return self.relay_identity_value

    def text(self, on_final) -> str:
        return ""

    def stop(self, timeout: float = 5.0) -> None:
        pass


class _PromptSpyStream:
    """The zero-_stream-call spy with a COUNTED `committed` attribute: the bulk path
    must never read it (the P1.M6.T3.S1 source decision) nor write it — both directions
    are observable, so a regression that silently falls back to the streaming source
    (or feeds _stream from bulk — risk #7) fails loudly instead of degrading quietly.
    """

    def __init__(self) -> None:
        self._committed = ""
        self.committed_reads = 0
        self.committed_writes: list[str] = []
        self.partial_calls: list[str] = []
        self.commit_calls: list[str] = []
        self.freeze_calls: list[str] = []
        self.reset_calls = 0
        self.resume_calls = 0
        self.user_keypress_calls = 0

    @property
    def committed(self) -> str:
        self.committed_reads += 1
        return self._committed

    @committed.setter
    def committed(self, value: str) -> None:
        self.committed_writes.append(value)
        self._committed = value

    def on_partial(self, text: str) -> None:
        self.partial_calls.append(text)

    def commit(self, text: str) -> None:
        self.commit_calls.append(text)

    def freeze(self, reason: str, session: bool = False) -> None:
        self.freeze_calls.append(reason)

    def reset_boundary(self) -> None:
        pass

    def reset_after_cancel(self) -> None:
        self.reset_calls += 1

    def reset_session(self) -> None:
        pass

    def resume(self) -> None:
        self.resume_calls += 1

    def pending_tail_len(self) -> int:
        return 0

    def arm_stray_echo_guard(self, text: str) -> None:
        pass

    def note_user_keypress(self) -> None:
        self.user_keypress_calls += 1


class _FakeTarget:
    """DeliveryTarget duck (the G2FakeTarget shape): acquire → ok; show/finalize
    APPLIED (programmable refuse_after / raise_after / finalize_unchanged); cancel
    APPLIED when owned; leave recorded exactly-once evidence."""

    def __init__(
        self,
        *,
        acquire_ok: bool = True,
        acquire_reason: str = "no field",
        refuse_after: "int | None" = None,
        raise_after: "int | None" = None,
        finalize_unchanged: bool = False,
    ):
        self.acquire_ok = acquire_ok
        self.acquire_reason = acquire_reason
        self.refuse_after = refuse_after
        self.raise_after = raise_after
        self.finalize_unchanged = finalize_unchanged
        self.acquire_calls = 0
        self.leave_calls = 0
        self.begun: list[str] = []
        self.ops: list[tuple] = []

    def acquire(self):
        self.acquire_calls += 1
        self.begun.append("acquire")
        if self.acquire_ok:
            return AcquireResult(ok=True, handle="fake", revision=0)
        return AcquireResult(ok=False, reason=self.acquire_reason)

    def _mutate(self, method: str, span):
        self.begun.append(method)
        if self.raise_after is not None and len(self.ops) >= self.raise_after:
            raise RuntimeError("target exploded (programmed)")
        if method == "finalize" and self.finalize_unchanged:
            result = ShowResult.UNCHANGED
        elif self.refuse_after is not None and len(self.ops) >= self.refuse_after:
            result = ShowResult.REFUSED
        else:
            result = ShowResult.APPLIED
        self.ops.append((method, span, result))
        return result

    def show(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        return self._mutate("show", span)

    def finalize(self, session, utterance, seq, expected_revision, span) -> ShowResult:
        return self._mutate("finalize", span)

    def cancel(self) -> ShowResult:
        self.begun.append("cancel")
        self.ops.append(("cancel", None, ShowResult.APPLIED))
        return ShowResult.APPLIED

    def leave(self) -> None:
        self.leave_calls += 1


class _FakeBundle:
    """The bulk_target_factory= test double: records attach/teardown; carries the target."""

    def __init__(self, target: _FakeTarget) -> None:
        self.target = target
        self.attached: list = []
        self.teardown_calls = 0

    def attach(self, controller) -> None:
        self.attached.append(controller)

    def teardown(self) -> None:
        self.teardown_calls += 1


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def _bulk_cfg(**over) -> "config_mod.VoiceTypingConfig":
    """The precondition triple satisfied at construction (streaming=True,
    graceful_stop=False, keypress_action='disarm' are the defaults)."""
    return config_mod.VoiceTypingConfig.from_toml(
        {"output": {"delivery": "bulk-text"}, **over}
    )


def _make_bulk_daemon(
    *,
    cfg=None,
    factory=None,
    identity=None,
    context_prompt: bool = True,
):
    """A daemon wired for bulk prompt tests: fake host (settable identity + set_prompt
    recorder), spy backend, fake bundle factory, prompt-spy stream installed, real
    LatencyLog. No threads started."""
    cfg = cfg or _bulk_cfg()
    fb = _BulkFakeFeedback()
    be = _SpyBackend()
    host_holder: dict = {}

    def _host_factory(cfg_, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(
            cfg_, feedback, latency, on_final, on_partial, on_speech,
            context_prompt=context_prompt, **kw,
        )
        host.relay_identity_value = identity
        host_holder["host"] = host
        return host

    if factory is None:
        def factory(cfg_):
            return _FakeBundle(_FakeTarget())

    d = VoiceTypingDaemon(
        cfg,
        fb,
        recorder=None,
        host_factory=_host_factory,
        backend=be,
        mic_prober=lambda: (True, None),
        bulk_target_factory=factory,
    )
    assert d._load_host() is True
    d._stream = _PromptSpyStream()  # the counted committed spy (bulk never reads/writes it)
    return d, fb, be, host_holder["host"]


def _wire_direct_ctrl(d, fb, target=None, gen: int = 1):
    """Deterministic dispatch setup: install a REAL BulkController over a fake target,
    acquired + armed, WITHOUT starting the writer (ctrl.drain() is the pump)."""
    target = target or _FakeTarget()
    ctrl = BulkController(target, on_stopped=d._on_bulk_stopped,
                          on_applied=d._on_bulk_applied)
    assert ctrl.acquire() is True
    assert ctrl.arm(gen) is True
    d._bulk_ctrl = ctrl
    d._bulk_gen = gen
    d._bulk_bundle = _FakeBundle(target)
    d._listening.set()
    return ctrl, target


def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    """Bounded poll (the G2 _wait_until idiom) — the re-arm tests' only real waits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _prompts_of(host: _FakeHost) -> list[str]:
    return list(host.prompts)


# ---------------------------------------------------------------------------
# 1-2. the two steady-state pushes (trigger A + trigger B)
# ---------------------------------------------------------------------------


def test_bulk_final_enqueues_then_applies_two_pushes():
    """(a) Accepted final in the steady state → TWO pushes: at ENQUEUE the context is
    rolling(confirmed_visible) = the utterance's last APPLIED show span; at
    finalize-APPLIED it is rolling(final span) — the finalize REVISED the visible text.
    Order: enqueue push precedes the drain (the writer hadn't processed the finalize)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("hello wor")  # APPLIED show → confirmed span 1; NO push (trigger B is finalize-only)
    assert ctrl.drain() >= 1
    assert ctrl.confirmed_visible() == "hello wor"
    assert _prompts_of(host) == [], "a partial show never pushes"

    d.on_final("hello world")  # accepted final → trigger A fires INSIDE on_final
    assert _prompts_of(host) == [
        prompt_engine.rolling_context_prompt("hello wor")
    ], "trigger A: enqueue-time push reads the last APPLIED show span"

    ctrl.drain()  # finalize APPLIED → trigger B on the writer path
    assert ctrl.confirmed_visible() == "hello world"
    assert _prompts_of(host) == [
        prompt_engine.rolling_context_prompt("hello wor"),
        prompt_engine.rolling_context_prompt("hello world"),
    ], "trigger B: finalize-APPLIED push carries the exact final span"
    assert be.typed == [] and be.backspaces == [], "the R.1 zero-legacy-call law holds"


def test_bulk_unchanged_finalize_single_push():
    """(b) UNCHANGED finalize (final renders equal to the shown span — the common
    stabilized-partial-equals-final case): the ENQUEUE push fired; NO finalize push
    (on_applied does not fire on UNCHANGED, _confirmed_visible is not advanced) — yet
    the context is still correct, because the show span renders equal to the final."""
    target = _FakeTarget(finalize_unchanged=True)
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, _ = _wire_direct_ctrl(d, fb, target=target)
    d._on_partial("hello wor")
    ctrl.drain()
    assert ctrl.confirmed_visible() == "hello wor"

    d.on_final("hello wor")  # renders equal → the finalize will come back UNCHANGED
    assert _prompts_of(host) == [
        prompt_engine.rolling_context_prompt("hello wor")
    ], "trigger A covered the UNCHANGED final at enqueue time"

    ctrl.drain()
    assert target.ops == [
        ("show", "hello wor", ShowResult.APPLIED),
        ("finalize", "hello wor", ShowResult.UNCHANGED),
    ]
    assert _prompts_of(host) == [
        prompt_engine.rolling_context_prompt("hello wor")
    ], "NO finalize-APPLIED push: UNCHANGED fires no on_applied — and none is needed"
    assert ctrl.confirmed_visible() == "hello wor", "UNCHANGED does not advance the mirror"


# ---------------------------------------------------------------------------
# 3-5. the deliberate no-ops + the cancel clear
# ---------------------------------------------------------------------------


def test_bulk_partial_shows_never_push():
    """(e) Several APPLIED shows, no final → ZERO prompt pushes (no mid-utterance
    self-conditioning), even though confirmed_visible() advanced each time."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("a")
    ctrl.drain()
    host.relay_identity_value = _Identity(1, 8)  # a second utterance, same gen
    d._on_partial("abc")
    ctrl.drain()
    assert ctrl.confirmed_visible() == "abc", "shows DID confirm (value #3 advances)"
    shows = [op for op in target.ops if op[0] == "show"]
    assert len(shows) == 2 and all(r is ShowResult.APPLIED for _, _, r in shows)
    assert _prompts_of(host) == [], "kind == 'show' never pushes (mid-utterance self-conditioning)"


def test_bulk_cancel_clears_prompt():
    """(c) Bulk cancel → exactly ONE set_prompt("") clear (D4); the cancelled fragment
    text appears in NO pushed prompt; zero physical-character compensation (R.1)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("cancelled fragment words")
    ctrl.drain()
    assert ctrl.confirmed_visible() == "cancelled fragment words"
    assert _prompts_of(host) == [], "the show never pushed (trigger B is finalize-only)"

    d.cancel()  # the bulk intercept → _bulk_cancel → ctrl.cancel + D4 clear
    assert _prompts_of(host) == [""], "exactly one ''-clear after cancel (D4)"
    for p in _prompts_of(host):
        assert "cancelled fragment" not in p, "a removed fragment is never decode context"
    assert be.backspaces == [], "R.1: zero physical-character compensation in bulk mode"


def test_bulk_rejected_final_no_push():
    """(d) Rejected final (below min_chars) in bulk → ZERO pushes (parity with the
    stream-edit deliberate no-op); the boundary still closes controller-side."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._cfg.filter.min_chars = 50
    d.on_final("short one")
    ctrl.drain()
    assert fb.finals == [], "the final was rejected (recognition meaning withheld)"
    assert "filtered hallucination" in fb.notifies[-1], "the legacy rejected-final UX"
    assert target.ops == [], "the boundary closed with NO target call (nothing auto-erased)"
    assert _prompts_of(host) == [], "rejected final: zero pushes"


# ---------------------------------------------------------------------------
# 6. the no-cross-mode-bleed law
# ---------------------------------------------------------------------------


def test_bulk_never_reads_or_writes_stream():
    """(g) Across a full bulk arm→speak→cancel→re-arm→speak session _stream.committed
    stays "" (never written, never even read) and the backend is never reached (R.1)."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("first part")
    ctrl.drain()
    d.on_final("first part done")
    ctrl.drain()
    assert len(_prompts_of(host)) == 2, "both steady-state pushes fired"
    d.cancel()
    assert _prompts_of(host)[-1] == "", "the D4 clear fired"

    d._arm()  # re-arm: fresh gen, arm-time FIFO clear, new delivery lifetime
    assert _wait_until(
        lambda: d._bulk_wired()
        and d._bulk_ctrl is not ctrl
        and d._bulk_ctrl.is_active()
    ), "the re-arm thread built a fresh wired controller"
    ctrl2 = d._bulk_ctrl
    host.relay_identity_value = _Identity(2, 7)  # match the re-arm's bumped gen FIRST
    d._on_partial("second part")
    assert _wait_until(
        lambda: any(op[0] == "show" for op in d._bulk_bundle.target.ops)
    ), "the started writer dispatched the post-re-arm partial"
    n_before = len(_prompts_of(host))
    d.on_final("second part done")
    assert _wait_until(
        lambda: ctrl2.confirmed_visible() == "second part done"
    ), "the started writer applied the post-re-arm final (trigger B advanced the mirror)"
    assert len(_prompts_of(host)) == n_before + 2, (
        "the post-re-arm pair pushed enqueue (A) + finalize-APPLIED (B) as usual"
    )

    spy = d._stream
    assert spy._committed == "", "committed NEVER written by the bulk path (stays '')"
    assert spy.committed_writes == [] and spy.committed_reads == 0, (
        "the bulk path never feeds nor reads _stream.committed — no cross-mode bleed"
    )
    assert spy.commit_calls == [] and spy.partial_calls == [], "zero engine calls"
    assert be.typed == [] and be.backspaces == [], "R.1: the backend is never reached"
    assert ctrl2.confirmed_visible() == "second part done", (
        "the new controller's own mirror advanced; the old controller is gone"
    )


# ---------------------------------------------------------------------------
# 7-8. the gates
# ---------------------------------------------------------------------------


def test_bulk_config_off_zero_pushes():
    """(h) asr.context_prompt=false ⇒ zero set_prompt calls in bulk mode — not even the
    arm-time or cancel-time clears."""
    cfg = _bulk_cfg(**{"asr": {"context_prompt": False}})
    d, fb, be, host = _make_bulk_daemon(cfg=cfg, identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("words")
    ctrl.drain()
    d.on_final("more words here")
    ctrl.drain()
    d.cancel()
    assert host.prompts == [], "config-off: zero pushes"
    assert host.calls == [], "config-off: not even the clears touch the host seam"
    assert be.typed == []


def test_bulk_degraded_child_zero_pushes():
    """(h) A degraded child (ready payload context_prompt=False ⇒ _context_prompt_active
    is False) ⇒ zero pushes, zero clears — the gates ARE the spec."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7), context_prompt=False)
    assert d._context_prompt_active is False, "the ready flag resolved degraded"
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("words")
    ctrl.drain()
    d.on_final("more words here")
    ctrl.drain()
    d.cancel()
    assert host.prompts == [] and host.calls == [], "degraded child: zero set_prompt calls"
    assert be.typed == []


# ---------------------------------------------------------------------------
# 9. the re-arm FIFO pin (bulk mode)
# ---------------------------------------------------------------------------


def test_bulk_rearm_clears_first():
    """(g) After confirmed spans exist, re-arm in bulk mode: the FIRST prompt is the
    context-free "" clear, FIFO BEFORE the mic/arm cmd (the warm-re-arm pin), and the
    fresh controller starts with an empty mirror."""
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, target = _wire_direct_ctrl(d, fb)
    d._on_partial("session one words")
    ctrl.drain()
    d.on_final("session one words done")
    ctrl.drain()
    assert len(_prompts_of(host)) == 2, "session one left two context pushes behind"

    d._arm()  # re-arm (the real _arm path: clear → mic → new delivery lifetime)
    assert _wait_until(
        lambda: d._bulk_wired() and d._bulk_ctrl is not ctrl and d._bulk_ctrl.is_active()
    )
    assert host.calls[-2:] == [("prompt", ""), ("mic", True)], (
        "FIFO pin: set_prompt('') immediately BEFORE set_microphone(True)"
    )
    assert _prompts_of(host)[-1] == "", "the re-arm's first prompt is the '' clear"
    assert d._bulk_ctrl.confirmed_visible() == "", (
        "a fresh controller has no cross-session bleed (R.5 _reset_session law)"
    )


# ---------------------------------------------------------------------------
# 10. the branch-order guard (stream-edit must keep its source)
# ---------------------------------------------------------------------------


def test_stream_edit_source_unchanged():
    """(f) In stream-edit mode (streaming=true) commits still push
    rolling(_stream.committed) — the bulk branch (first in _refresh_context_prompt)
    must NOT shadow the stream-edit source; the legacy byte-identical behavior."""
    from voice_typing.daemon import VoiceTypingDaemon as _D  # local: the ctor seam

    cfg = config_mod.VoiceTypingConfig()  # delivery="stream-edit" (default), streaming=True
    fb = _BulkFakeFeedback()
    be = _SpyBackend()
    host_holder: dict = {}

    def _factory(cfg_, feedback, latency, on_final, on_partial, on_speech, **kw):
        host = _FakeHost(cfg_, feedback, latency, on_final, on_partial, on_speech)
        host_holder["host"] = host
        return host

    d = _D(
        cfg,
        fb,
        recorder=None,
        host_factory=_factory,
        backend=be,
        mic_prober=lambda: (True, None),
    )
    assert d._load_host() is True
    assert d._bulk_mode() is False and d._bulk_wired() is False, (
        "stream-edit: the bulk branch is unreachable (_bulk_wired() is False)"
    )
    d._arm()
    d.on_final("hello world")  # committed "hello world " (no terminator)
    d.on_final("more words")  # committed "hello world more words "
    assert _prompts_of(host_holder["host"]) == [
        "",
        "hello world",
        "hello world more words",
    ], "stream-edit pushes rolling(_stream.committed) — byte-identical to the pre-T3S1 pin"


# ---------------------------------------------------------------------------
# 11. the fault-stopped controller never feeds a stale push
# ---------------------------------------------------------------------------


def test_bulk_fault_stopped_no_stale_push():
    """(h/i) After a target fault stops the controller, a subsequent accepted final
    fires NO push: trigger A sits inside the is_active guard, and the retained
    confirmed text (recoverable recognition) is never read into a prompt."""
    target = _FakeTarget(raise_after=2)  # op0 show OK, op1 finalize OK, op2 raises
    d, fb, be, host = _make_bulk_daemon(identity=_Identity(1, 7))
    ctrl, _ = _wire_direct_ctrl(d, fb, target=target)
    d._on_partial("pre-fault words")
    ctrl.drain()
    d.on_final("pre-fault words done")
    ctrl.drain()
    assert len(_prompts_of(host)) == 2 and ctrl.is_active(), "the healthy pair pushed twice"

    host.relay_identity_value = _Identity(1, 8)  # a NEW utterance on the same gen
    d._on_partial("post-fault words")
    ctrl.drain()  # op2 raises → controller stops "target-error"
    assert not ctrl.is_active(), "the fault stopped the controller"
    assert ctrl.confirmed_visible() == "pre-fault words done", (
        "the three-value law RETAINS recoverable recognition across a fault stop"
    )
    fault = fb.delivery_states[-1]
    assert fault[0] == "fault" and fault[1] == "target-error"

    d._listening.set()  # simulate a final already past the listening gate when the
    # fault disarmed — THIS is the race the is_active guard exists for
    d.on_final("post fault final")
    ctrl.drain()
    assert fb.finals[-1] == "post fault final", "the final was accepted (recorded)"
    assert len(_prompts_of(host)) == 2, (
        "trigger A sits inside the is_active guard: NO push from a stopped controller"
    )
    assert be.typed == [] and be.backspaces == []
