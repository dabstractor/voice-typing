"""tests/test_recorder_host.py — RecorderHost IPC unit tests (P1.M3.T2.S2 re-plan).

Hermetic: NO real child process, NO RealtimeSTT/torch/ctranslate2, NO CUDA. The RecorderHost's
queue/reader-thread/dispatch logic is exercised by feeding CANNED events onto its event_queue
(an mp.Queue, but we put events directly) + asserting the host dispatches them to the callbacks.
The spawn()/stop() PROCESS logic is tested with a stubbed _worker_main target (a function that
emits canned events + serves commands) so we verify the process-group teardown path without CUDA.

Run:
    cd /home/dustin/projects/voice-typing
    uv run pytest tests/test_recorder_host.py -v
"""
from __future__ import annotations

import threading
import time
from typing import Any


from voice_typing import recorder_host


# ---------------------------------------------------------------------------
# Stubs — duck-typed stand-ins so tests never import RealtimeSTT or spawn CUDA.
# ---------------------------------------------------------------------------


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
# _dispatch — the reader thread's per-event logic (tested directly, no thread) 
# ---------------------------------------------------------------------------


def test_dispatch_partial_calls_on_partial():
    """_dispatch('partial') calls _on_partial (the daemon's _on_partial drives feedback + latency).
    The host itself does NOT touch latency on partial — that's the daemon callback's job."""
    partials: list[str] = []
    host = _make_host(on_partial=lambda t: partials.append(t))
    host._dispatch("partial", {"text": "hello"})
    assert partials == ["hello"]


def test_dispatch_speech_calls_on_speech():
    fired: list[int] = []
    host = _make_host(on_speech=lambda: fired.append(1))
    host._dispatch("speech", {})
    assert fired == [1]


def test_dispatch_speech_end_stamps_latency():
    host = _make_host()
    host._dispatch("speech_end", {})
    assert host._latency.speech_ends == 1


def test_dispatch_vad_drives_feedback_phase():
    host = _make_host()
    host._dispatch("vad", {"phase": "speaking"})
    host._dispatch("vad", {"phase": "listening"})
    assert host._feedback.phases == ["speaking", "listening"]


def test_dispatch_final_calls_on_final_and_sets_final_event():
    finals: list[str] = []
    host = _make_host(on_final=lambda t: finals.append(t))
    host._final_evt.clear()
    host._dispatch("final", {"text": "done"})
    assert finals == ["done"]
    assert host._final_evt.is_set()       # text() would unblock


def test_dispatch_ready_seeds_device_and_sets_ready_event():
    host = _make_host()
    device = {"device": "cuda", "compute_type": "float32", "model": "small.en"}
    host._dispatch("ready", device)
    assert host.device == device
    assert host._ready_evt.is_set()
    assert host._error is None


def test_dispatch_error_sets_error_and_ready_event():
    host = _make_host()
    host._dispatch("error", {"msg": "CUDA exploded"})
    assert host._error == "CUDA exploded"
    assert host._ready_evt.is_set()


def test_dispatch_unknown_event_is_ignored(caplog):
    host = _make_host()
    with caplog.at_level("WARNING", logger="voice_typing.recorder_host"):
        host._dispatch("bogus", {})
    assert any("unknown event" in r.getMessage() for r in caplog.records)


def test_dispatch_final_swallows_on_final_exception(caplog):
    """A raising on_final must not kill dispatch (it would strand text()). final_evt still sets."""
    def boom(_t):
        raise RuntimeError("on_final exploded")
    host = _make_host(on_final=boom)
    host._final_evt.clear()
    with caplog.at_level("ERROR", logger="voice_typing.recorder_host"):
        host._dispatch("final", {"text": "x"})
    assert host._final_evt.is_set()       # still unblocks text() even though on_final raised
    assert any("on_final raised" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# text() — blocks on _final_evt; unblocks on final / child death
# ---------------------------------------------------------------------------


def test_text_blocks_until_final_event_then_returns():
    host = _make_host()
    done = threading.Event()

    def _text():
        host.text(lambda _t: None)
        done.set()

    t = threading.Thread(target=_text, daemon=True)
    t.start()
    time.sleep(0.1)
    assert not done.is_set(), "text() returned before a final event"
    host._dispatch("final", {"text": "hi"})   # reader-thread path sets _final_evt
    assert done.wait(2.0), "text() did not unblock after the final event"
    t.join(2.0)


def test_text_returns_promptly_if_child_already_dead():
    host = _make_host()
    host._dead = True  # simulate a dead child
    done = threading.Event()

    def _text():
        host.text(lambda _t: None)
        done.set()

    threading.Thread(target=_text, daemon=True).start()
    assert done.wait(2.0), "text() did not return promptly for a dead child"


# ---------------------------------------------------------------------------
# set_microphone / abort / stop — best-effort queue puts (never block)
# ---------------------------------------------------------------------------


def test_set_microphone_puts_arm_or_disarm_command():
    host = _make_host()
    host.set_microphone(True)
    host.set_microphone(False)
    cmd1 = host._cmd_q.get(timeout=1.0)
    cmd2 = host._cmd_q.get(timeout=1.0)
    assert cmd1 == ("arm", {})
    assert cmd2 == ("disarm", {})


def test_abort_sets_abort_event():
    """abort() sets the dedicated abort event (polled by a child thread to interrupt text())."""
    host = _make_host()
    assert not host._abort_event.is_set()
    host.abort()
    assert host._abort_event.is_set()


def test_stop_is_noop_when_no_process():
    host = _make_host()
    host.stop()  # must not raise (self._proc is None)


def test_stop_with_dead_process_is_noop():
    host = _make_host()

    class _DeadProc:
        pid = 12345
        def is_alive(self):
            return False
        def join(self, timeout=None):
            pass

    host._proc = _DeadProc()
    host.stop()  # must not raise; join returns immediately (not alive)


def test_concurrent_stop_calls_share_one_teardown(monkeypatch):
    """Two concurrent stop() callers share ONE teardown (single-flight under _stop_lock).

    Regression guard for bugfix Issue 1 (P1.M1.T1.S1): on the SIGTERM path request_shutdown()
    (signal-handler thread) + shutdown() (main-thread finally) both call host.stop() at once.
    Without serialization each caller passes the `self._proc is None` guard and runs its own
    join+killpg, so os.killpg fires TWICE and two parallel multi-second teardowns blow
    systemd's 15s TimeoutStopSec. _stop_lock makes check-then-teardown atomic: the second
    caller blocks on the lock, then sees _proc is None and no-ops — exactly ONE killpg.

    Hermetic + fast (~0.6s): a _SlowProc whose join() sleeps 0.3s + is_alive() stays True
    forces stop() into the join->_terminate_group path (not the early-return), and
    os.getpgid/os.killpg are monkeypatched so no real process is signaled. Two threads +
    a Barrier maximize contention. The PROOF is the killpg call count (1 with the lock,
    2 without) — see the L3 mutation in this subtask's PRP.
    """

    class _SlowProc:
        pid = 4242

        def is_alive(self):
            return True

        def join(self, timeout=None):
            time.sleep(0.3)  # wedge long enough that both callers overlap inside stop()

    host = _make_host()
    host._proc = _SlowProc()

    killpg_calls: list[tuple] = []
    monkeypatch.setattr(recorder_host.os, "getpgid", lambda _pid: 99999)
    monkeypatch.setattr(
        recorder_host.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig))
    )

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _call_stop() -> None:
        try:
            barrier.wait(timeout=2.0)
            host.stop()
        except BaseException as exc:  # noqa: BLE001 — capture, re-assert below
            errors.append(exc)

    t1 = threading.Thread(target=_call_stop, name="stop-A")
    t2 = threading.Thread(target=_call_stop, name="stop-B")
    start = time.monotonic()
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    elapsed = time.monotonic() - start

    assert not errors, f"a stop() caller raised: {errors!r}"
    assert not t1.is_alive() and not t2.is_alive(), "a stop() thread did not finish"
    assert elapsed < 2.0, f"concurrent stop took {elapsed:.2f}s (single-flight ~0.6s expected)"
    assert len(killpg_calls) == 1, (
        f"os.killpg called {len(killpg_calls)}x (expected 1) — _stop_lock single-flight is "
        "broken: two concurrent callers must share ONE teardown"
    )
    assert host._proc is None, "host._proc not cleared after teardown"
    assert host._dead is True, "host._dead not set after teardown"


# ---------------------------------------------------------------------------
# spawn() ready/error wait — tested via the dispatch path (no real child; pytest+spawn is
# fragile because the spawn child re-imports the test module). The real spawn() process path is
# validated by the L3/L4 integration tests (test_idle_and_gpu.sh). Here we verify the ready/error
# bookkeeping: _ready_evt gates spawn()'s return; _device is seeded from the 'ready' payload; an
# 'error' payload makes spawn()'s outcome False.
# ---------------------------------------------------------------------------


def test_spawn_ready_seeds_device_via_dispatch():
    """A 'ready' event on evt_q seeds host.device + sets _ready_evt (the spawn() happy path)."""
    host = _make_host()
    device = {"device": "cuda", "compute_type": "float32", "model": "small.en"}
    host._dispatch("ready", device)
    assert host._ready_evt.is_set()
    assert host.device == device
    assert host._error is None


def test_spawn_error_sets_error_via_dispatch():
    """An 'error' event sets host._error + _ready_evt (spawn() returns False on this)."""
    host = _make_host()
    host._dispatch("error", {"msg": "CUDA init failed"})
    assert host._ready_evt.is_set()
    assert host._error == "CUDA init failed"


# ---------------------------------------------------------------------------
# Reader thread — drains event_queue; EOF marks the child dead (idempotent)
# ---------------------------------------------------------------------------


def test_read_loop_drains_events_until_gone():
    finals: list[str] = []
    partials: list[str] = []
    speeches: list[int] = []
    host = _make_host(
        on_final=lambda t: finals.append(t),
        on_partial=lambda t: partials.append(t),
        on_speech=lambda: speeches.append(1),
    )
    host._reader = threading.Thread(target=host._read_loop, daemon=True)
    host._reader.start()
    _feed_event(host, "partial", {"text": "a"})
    _feed_event(host, "speech", {})
    _feed_event(host, "vad", {"phase": "speaking"})
    _feed_event(host, "speech_end", {})
    _feed_event(host, "final", {"text": "done"})
    _feed_event(host, "gone", {})
    host._reader.join(timeout=2.0)
    assert not host._reader.is_alive()
    assert finals == ["done"]
    assert partials == ["a"]
    assert speeches == [1]
    assert host._feedback.phases == ["speaking"]      # vad event
    assert host._latency.speech_ends == 1             # speech_end event
    assert host._dead is True           # 'gone' / reader exit marks dead


def test_read_loop_eof_marks_dead_and_unblocks_waiters():
    """When the reader loop exits (EOF on the queue / child gone), its finally block marks the
    host dead + sets the waiters so a blocked text()/spawn() unblocks."""
    host = _make_host()
    host._reader = threading.Thread(target=host._read_loop, daemon=True)
    host._reader.start()
    # Signal the reader to exit via the 'gone' event (the child acked shutdown). The reader's
    # finally block then marks _dead + sets _final_evt + _ready_evt.
    _feed_event(host, "gone", {})
    host._reader.join(timeout=2.0)
    assert not host._reader.is_alive()
    assert host._dead is True
    assert host._final_evt.is_set()     # a blocked text() unblocks
    assert host._ready_evt.is_set()     # a blocked spawn() unblocks


# ---------------------------------------------------------------------------
# Properties — device / is_alive / pid
# ---------------------------------------------------------------------------


def test_initial_properties():
    host = _make_host()
    assert host.device == {}
    assert host.is_alive is False       # no process yet
    assert host.pid is None


# ---------------------------------------------------------------------------
# _run_text_and_emit_final — the child's text() command handler (P1.M2.T2.S4 follow-up:
# the run()-loop wedge fix). recorder.text() on the ABORT path returns '' WITHOUT calling the
# callback; the helper MUST still emit a ('final', ...) sentinel so the daemon's host.text()
# unblocks instead of wedging the run() loop forever (stop/toggle-off/auto-stop regression).
# Hermetic: a fake recorder mimics RealtimeSTT's text() return semantics.
# ---------------------------------------------------------------------------


class _AbortFakeRecorder:
    """Mimics RealtimeSTT's ABORT path: text(cb) returns '' and NEVER calls cb.

    RealtimeSTT core/transcription_api.py `text()`: when recorder.abort() set interrupt_stop_event,
    text() `return ""` before the `if on_transcription_finished:` branch, so the callback never
    fires. This is the exact behavior that, pre-fix, left the daemon's host.text() blocked forever.
    """

    def __init__(self) -> None:
        self.text_calls = 0

    def text(self, callback):
        self.text_calls += 1
        return ""   # abort path: return '' WITHOUT calling the callback


class _NormalFakeRecorder:
    """Mimics RealtimeSTT's NORMAL path: text(cb) calls cb in a thread and returns None.

    RealtimeSTT: `threading.Thread(target=on_transcription_finished, args=(recorder.transcribe(),))
    .start()` then returns None (implicit) — the callback is delivered via the thread, NOT the
    return value, so result is None and the helper must NOT emit an extra sentinel.
    """

    def __init__(self) -> None:
        self.text_calls = 0

    def text(self, callback):
        self.text_calls += 1
        threading.Thread(target=callback, args=("hello world",), daemon=True).start()
        return None


def _drain(queue) -> list:
    out = []
    while True:
        try:
            out.append(queue.get_nowait())
        except Exception:
            break
    return out


def test_run_text_emits_sentinel_final_on_abort_path():
    """REGRESSION (the wedge): an aborted recorder.text() returns '' without the callback, so the
    helper MUST emit a ('final', {text:''}) sentinel. Without this, the daemon's host.text() blocks
    forever (the child is still alive) and the run() loop can never send the next ('text', {}) —
    so stop/toggle-off/auto-stop permanently breaks transcription after the first use."""
    import queue as _queue

    evt_q: Any = _queue.Queue()
    finals: list[str] = []

    def _child_on_final(text: str) -> None:
        recorder_host._safe_put(evt_q, ("final", {"text": text}))
        finals.append(text)

    rec = _AbortFakeRecorder()
    recorder_host._run_text_and_emit_final(rec, evt_q, _child_on_final)

    assert rec.text_calls == 1
    assert finals == [], "abort path must NOT invoke the on_final callback"
    events = _drain(evt_q)
    assert events == [("final", {"text": ""})], (
        f"abort path must emit exactly one ('final', {{'text': ''}}) sentinel so host.text() unblocks; "
        f"got {events!r}"
    )


def test_run_text_does_not_double_emit_on_normal_path():
    """On the NORMAL path the callback fires (in a thread) and text() returns None; the helper must
    NOT add a spurious empty sentinel (that would race a real final onto the queue and double-fire
    on_final). Asserts result-None => no extra emit."""
    import queue as _queue

    evt_q: Any = _queue.Queue()
    finals: list[str] = []

    def _child_on_final(text: str) -> None:
        recorder_host._safe_put(evt_q, ("final", {"text": text}))
        finals.append(text)

    rec = _NormalFakeRecorder()
    recorder_host._run_text_and_emit_final(rec, evt_q, _child_on_final)

    assert rec.text_calls == 1
    # the callback runs in a thread; give it a beat to enqueue its real final
    for _ in range(50):
        if finals:
            break
        time.sleep(0.01)
    assert finals == ["hello world"], "normal path must invoke the callback with the transcription"
    events = _drain(evt_q)
    assert events == [("final", {"text": "hello world"})], (
        f"normal path must emit ONLY the callback's real final, never an extra sentinel; got {events!r}"
    )


class _AbortReturnsNoneFakeRecorder:
    """VT-007: mimics a HYPOTHETICAL future RealtimeSTT whose ABORT path returns None (not '').

    The v1.0.2 contract the OLD code depended on: abort -> text() returns '' (non-None) and never
    calls the callback. A future version that returns None on abort too would break the
    `result is not None` marker and re-wedge the run loop. This fake returns None on abort AND
    never calls the callback, so the sentinel can ONLY come from the `aborted` flag we pass.
    """

    def __init__(self) -> None:
        self.text_calls = 0

    def text(self, callback):
        self.text_calls += 1
        return None   # future-version abort: None return, callback never invoked


def test_run_text_emits_sentinel_when_abort_flag_set_even_if_return_is_none():
    """VT-007 regression: the unblock sentinel must NOT depend on recorder.text()'s version-specific
    return value. With a fake whose abort path returns None (not ''), the helper must STILL emit the
    ('final', {text:''}) sentinel because the `aborted` flag is set — the abort signal WE control,
    independent of the return contract. Without this, a future RealtimeSTT version returning None on
    abort re-wedges the run loop after the first disarm (no further utterance transcribes).
    """
    import queue as _queue

    evt_q: Any = _queue.Queue()
    rec = _AbortReturnsNoneFakeRecorder()
    aborted = threading.Event()
    aborted.set()   # an abort was requested during this text() call
    recorder_host._run_text_and_emit_final(rec, evt_q, lambda _t: None, aborted)

    assert rec.text_calls == 1
    events = _drain(evt_q)
    assert events == [("final", {"text": ""})], (
        f"abort path with return=None must STILL emit the sentinel via the `aborted` flag "
        f"(VT-007); got {events!r}"
    )


def test_run_text_no_sentinel_on_normal_path_when_abort_flag_unset():
    """VT-007 complement: when the abort flag is NOT set (the normal path), the helper must not emit
    a spurious sentinel EVEN IF a caller passes the flag (it would otherwise double-fire a final).
    The normal-path callback is responsible for the real final; the flag being clear suppresses the
    sentinel regardless of the return value (here None).
    """
    import queue as _queue

    evt_q: Any = _queue.Queue()

    def _child_on_final(text: str) -> None:
        recorder_host._safe_put(evt_q, ("final", {"text": text}))

    rec = _NormalFakeRecorder()   # calls cb in a thread, returns None
    aborted = threading.Event()    # NOT set
    recorder_host._run_text_and_emit_final(rec, evt_q, _child_on_final, aborted)

    # the callback runs in a thread; give it a beat to enqueue its real final, then drain ONCE
    # (draining in a loop condition would consume+discard the item).
    import time as _t
    _t.sleep(0.2)
    events = _drain(evt_q)
    assert events == [("final", {"text": "hello world"})], (
        f"normal path (abort flag unset) must emit ONLY the real final, no sentinel; got {events!r}"
    )


def test_abort_sentinel_unblocks_blocked_host_text():
    """END-TO-END of the fix at the host layer: host.text() blocks on _final_evt; feeding the
    ('final', {text:''}) sentinel that _run_text_and_emit_final emits on the abort path MUST unblock
    it. This is the daemon-side half of the regression — pre-fix no such event was ever produced."""
    host = _make_host()
    done = threading.Event()

    def _text():
        host.text(lambda _t: None)
        done.set()

    t = threading.Thread(target=_text, daemon=True)
    t.start()
    time.sleep(0.1)
    assert not done.is_set(), "text() returned before any final/sentinel event"
    # The sentinel the child now emits on the abort path:
    host._dispatch("final", {"text": ""})
    assert done.wait(2.0), "the abort-path ('final', {text:''}) sentinel did NOT unblock host.text()"
    t.join(2.0)


# ---------------------------------------------------------------------------
# P1.M2.T7.S1 — cancel: marked sentinel + audio discard (plain abort UNCHANGED)
# ---------------------------------------------------------------------------


class _CancelFakeRecorder:
    """Cancel-path recorder: abort-style return ('') + the attribute surface _clear_recorder_audio
    touches, so the cancel branch's audio DISCARD is assertable.

    Mimics RealtimeSTT's abort semantics exactly like _AbortFakeRecorder (text(cb) returns ''
    without ever calling cb) and records every clear the helper performs: clear_audio_queue(),
    the recorded_audio_queue drain, frames/last_frames clear, and audio=None.
    """

    def __init__(self) -> None:
        import queue as _q
        self.text_calls = 0
        self.clear_audio_queue_calls = 0
        self.recorded_audio_queue: Any = _q.Queue()
        self.recorded_audio_queue.put(b"stale-audio")   # a completed recording awaiting transcription
        self.frames = ["frame1", "frame2"]              # the wait_audio() fallback source
        self.last_frames = ["last1"]
        self.audio: Any = object()

    def text(self, callback):
        self.text_calls += 1
        return ""   # cancel/abort path: return '' WITHOUT calling the callback

    def clear_audio_queue(self) -> None:
        self.clear_audio_queue_calls += 1


def test_cancel_sets_both_cancel_and_abort_events():
    """RecorderHost.cancel() sets _cancel_event AND _abort_event: cancel_event marks + discards,
    abort_event guarantees the text() unblock. Neither alone is the full signal."""
    host = _make_host()
    assert not host._cancel_event.is_set()
    assert not host._abort_event.is_set()
    host.cancel()
    assert host._cancel_event.is_set()
    assert host._abort_event.is_set()


def test_consume_cancel_mark_only_for_marked_sentinel():
    """The reader marks ONLY the ('final', {text:'', 'cancelled': True}) sentinel;
    consume_cancel_mark() returns-and-clears, and a plain final resets the mark to False
    (per-event semantics the daemon's suppression window depends on)."""
    host = _make_host()
    host._dispatch("final", {"text": "hello"})
    assert host.consume_cancel_mark() is False
    host._dispatch("final", {"text": "", "cancelled": True})
    assert host.consume_cancel_mark() is True
    assert host.consume_cancel_mark() is False   # cleared by the first consume
    host._dispatch("final", {"text": "next"})
    assert host.consume_cancel_mark() is False


def test_run_text_cancel_emits_marked_sentinel_and_discards_audio():
    """P1.M2.T7.S1: on the cancel path the helper DISCARDS the buffered/in-flight audio
    (clear_audio_queue + recorded_audio_queue drain + frames/last_frames/audio clear) and emits
    the unblock sentinel MARKED ('cancelled': True) so the daemon drops the cancelled utterance."""
    import queue as _queue

    evt_q: Any = _queue.Queue()
    rec = _CancelFakeRecorder()
    aborted = threading.Event()
    cancelled = threading.Event()
    aborted.set()      # the child's abort handler sets BOTH on a cancel
    cancelled.set()
    recorder_host._run_text_and_emit_final(rec, evt_q, lambda _t: None, aborted, cancelled)

    assert rec.text_calls == 1
    assert rec.clear_audio_queue_calls == 1, "cancel path must clear the recorder's audio queues"
    assert rec.recorded_audio_queue.empty(), "recorded_audio_queue must be drained (stale-final source)"
    assert rec.frames == [] and rec.last_frames == [] and rec.audio is None
    events = _drain(evt_q)
    assert events == [("final", {"text": "", "cancelled": True})], (
        f"cancel path must emit exactly one MARKED sentinel (the daemon drops it, but host.text() "
        f"must still unblock — the VT-007 contract); got {events!r}"
    )


def test_run_text_plain_abort_emits_unmarked_sentinel_and_keeps_audio():
    """REGRESSION GUARD for the plain abort() path (the drain watchdog _safe_abort depends on it):
    with `cancelled` UNSET the sentinel is emitted UNMARKED exactly as before P1.M2.T7.S1, and the
    recorder's audio is NOT touched (a drain may still want the in-flight utterance)."""
    import queue as _queue

    evt_q: Any = _queue.Queue()
    rec = _CancelFakeRecorder()
    aborted = threading.Event()
    aborted.set()          # plain abort (stop/drain watchdog) — NOT a cancel
    recorder_host._run_text_and_emit_final(rec, evt_q, lambda _t: None, aborted)

    assert rec.text_calls == 1
    assert rec.clear_audio_queue_calls == 0, "plain abort must NOT discard audio"
    assert not rec.recorded_audio_queue.empty()
    assert rec.frames == ["frame1", "frame2"] and rec.audio is not None
    events = _drain(evt_q)
    assert events == [("final", {"text": ""})], (
        f"plain abort sentinel must stay UNMARKED ({{'text': ''}} — no 'cancelled' key); got {events!r}"
    )


# ===========================================================================
# LOST-SIGNAL FIX (Backspace stuck-suppression bug): a cancel/abort landing in
# the gap BETWEEN the child's text() cycles used to be silently wiped by the
# 'text' command's fresh-marker clears — the marked sentinel was never emitted,
# the daemon's _cancel_suppress_final latched forever, every later final was
# dropped (no commit, no reset_boundary), and the streaming tail accumulated
# across utterances so everything dictated after the Backspace kept rewinding
# to the edit point. These tests pin the child-side halves of the fix.
# ===========================================================================


def test_drain_stale_abort_signals_cancel_wins_and_clears_both():
    """_drain_stale_abort_signals consumes a between-cycles cancel/abort, cancel FIRST
    (RecorderHost.cancel() sets both events; cancel's sentinel must be MARKED), and always
    clears both so the next text() cycle starts on the fresh-marker slate."""
    cancel_event = threading.Event()
    abort_event = threading.Event()
    assert recorder_host._drain_stale_abort_signals(cancel_event, abort_event) is None

    abort_event.set()
    assert recorder_host._drain_stale_abort_signals(cancel_event, abort_event) == "abort"
    assert not abort_event.is_set() and not cancel_event.is_set()

    cancel_event.set()
    abort_event.set()
    assert recorder_host._drain_stale_abort_signals(cancel_event, abort_event) == "cancel"
    assert not cancel_event.is_set() and not abort_event.is_set()


def test_run_text_holds_text_running_for_whole_text_call():
    """_run_text_and_emit_final holds the text_running lock for the WHOLE recorder.text() call
    (the abort handler's try-acquire liveness check: acquired == text() NOT in flight)."""
    import queue as _queue

    evt_q: Any = _queue.Queue()
    lock = threading.Lock()
    seen: dict[str, bool] = {}

    class _Rec:
        def text(self, on_final):
            seen["locked_during_text"] = lock.locked()
            return None

    recorder_host._run_text_and_emit_final(_Rec(), evt_q, lambda _t: None, None, None, lock)
    assert seen["locked_during_text"] is True, "text_running must be held inside recorder.text()"
    assert not lock.locked(), "text_running must be released once text() returns"


def test_bounded_recorder_abort_returns_on_wedged_abort():
    """_bounded_recorder_abort can never wedge the caller: an abort() that blocks forever
    (abort_recording's was_interrupted.wait() when text() is not in flight and the recorder
    state is not 'inactive') is abandoned after the bound — the handler thread stays alive."""
    entered = threading.Event()

    class _WedgingRec:
        def abort(self):
            entered.set()
            time.sleep(3600.0)  # the wedge (never returns this test's lifetime)

    t0 = time.monotonic()
    recorder_host._bounded_recorder_abort(_WedgingRec(), timeout_s=0.2)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"bounded abort must return promptly, took {elapsed:.2f}s"
    assert entered.is_set(), "the abort call must still have been attempted"


# ---------------------------------------------------------------------------
# Rev 3 hardening — 'arm' purges post-abort re-stashed audio (stale-replay fix)
# ---------------------------------------------------------------------------


def test_arm_purges_stale_audio_before_mic_on():
    """'arm' must clear the recorder's audio buffers BEFORE set_microphone(True).

    The stop's abort unblocks text() AFTER the 'disarm' clear ran, and the aborted decode
    re-stashes its audio into frames/last_frames — which the NEXT text() would otherwise
    fall back to and transcribe, replaying the previous session's last utterance into the
    new one (the stale-replay word-vomit). Order contract: purge, drain raced abort
    signals, then mic on."""
    import threading as _th

    rec = _CancelFakeRecorder()
    mic_calls: list[bool] = []
    rec.set_microphone = mic_calls.append  # record order + arg
    cancel_ev, abort_ev = _th.Event(), _th.Event()
    abort_ev.set()  # raced the disarm->arm toggle: must be drained, not leaked
    recorder_host._handle_arm(rec, cancel_ev, abort_ev)
    assert mic_calls == [True]  # mic on LAST
    assert rec.clear_audio_queue_calls == 1
    assert rec.recorded_audio_queue.empty()  # stale completed recording gone
    assert rec.frames == [] and rec.last_frames == []
    assert rec.audio is None
    assert not abort_ev.is_set() and not cancel_ev.is_set()  # raced signal drained


# ===========================================================================
# P1.M6.T1.S1 — relay payload identity (PRD §4.2sexies R.5): utterance_id +
# session_gen on the six final/partial sites, the daemon's _dispatch discard
# rules, and the relay_identity seam. Three layers:
#   A — _RelayIds/_with_identity units (the child-side stamper)
#   B — direct _dispatch discard semantics (the choke point; stub callbacks)
#   C — sentinel stamping via _run_text_and_emit_final + a queue round-trip
# All hermetic: doubles only, no CUDA, no real child process.
# ===========================================================================


# ---------------------------------------------------------------------------
# Layer A — _RelayIds / _with_identity units
# ---------------------------------------------------------------------------


def test_relay_ids_stamp_adds_both_keys_and_returns_same_dict():
    """stamp() ADDS utterance_id + session_gen (never renames/removes existing keys — the
    'cancelled' additive-key precedent) and returns the SAME dict object (the put sites rely on
    wrapping in place; the tuple kind must not change)."""
    ids = recorder_host._RelayIds()
    ids.rotate_utterance()
    ids.new_session()
    payload = {"text": "", "cancelled": True}
    out = ids.stamp(payload)
    assert out is payload, "stamp must return the same dict (in-place additive wrap)"
    assert payload["text"] == "" and payload["cancelled"] is True  # existing keys survive
    assert payload["utterance_id"] == 1 and payload["session_gen"] == 1  # + the identity keys


def test_with_identity_none_ids_is_noop():
    """ids=None (the legacy/test call sites — G7) must leave the payload byte-identical."""
    payload = {"text": "hello"}
    assert recorder_host._with_identity(payload, None) is payload
    assert recorder_host._with_identity({"text": "x"}, None) == {"text": "x"}


def test_relay_ids_rotate_and_new_session_are_monotonic():
    """Rotation and session bumps are strictly monotonic counters; sentinels stamp whatever id
    is current (they settle — never rotate, R.5)."""
    ids = recorder_host._RelayIds()
    assert ids.stamp({})["utterance_id"] == 0  # pre-speech: id 0 (no utterance opened yet)
    assert ids.rotate_utterance() == 1
    assert ids.rotate_utterance() == 2
    assert ids.new_session() == 1
    assert ids.new_session() == 2
    assert ids.stamp({})["utterance_id"] == 2  # stamping did NOT rotate (settle, not rotate)
    assert ids.stamp({})["session_gen"] == 2


def test_relay_ids_rotate_concurrent_no_lost_updates():
    """The stamper is lock-guarded (the realtime thread races the cmd loop): 2 threads × 50
    rotations must yield 50 UNIQUE ids per thread, no lost updates (a lost update would show a
    duplicate id in the collected set)."""
    ids = recorder_host._RelayIds()
    seen: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def _worker() -> None:
        barrier.wait(timeout=2.0)
        mine = [ids.rotate_utterance() for _ in range(50)]
        with lock:
            seen.extend(mine)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start(); t2.start(); t1.join(timeout=5); t2.join(timeout=5)
    assert len(seen) == 100
    assert len(set(seen)) == 100, "duplicate rotation ids — the lock is not guarding"
    assert max(seen) == 100


def test_relay_feedback_partial_stamped_and_legacy_default():
    """_RelayFeedback stamps update_partial payloads when given ids, and emits the id-LESS
    payload with its G7 default (the existing test doubles construct it 1-arg)."""
    import queue as _queue

    ids = recorder_host._RelayIds()
    ids.rotate_utterance()
    ids.new_session()
    q: Any = _queue.Queue()
    recorder_host._RelayFeedback(q, ids).update_partial("hi")
    assert _drain(q) == [("partial", {"text": "hi", "utterance_id": 1, "session_gen": 1})]
    q2: Any = _queue.Queue()
    recorder_host._RelayFeedback(q2).update_partial("hi")  # 1-arg: legacy id-less payload
    assert _drain(q2) == [("partial", {"text": "hi"})]


# ---------------------------------------------------------------------------
# Layer B — _dispatch discard rules (the single choke point, stub callbacks)
# ---------------------------------------------------------------------------


def test_dispatch_identity_partial_then_final_relayed_and_relay_identity_tracks():
    """Happy path: a partial and its final SHARE the id; both relay; relay_identity — read INSIDE
    the callbacks (they run on the reader thread) — carries the identity of the event being
    relayed (the P1.M6.T2.S1 seam)."""
    seen_in_partial: list[tuple] = []
    seen_in_final: list[tuple] = []

    host = _make_host(
        on_final=lambda t: seen_in_final.append((t, host.relay_identity)),
        on_partial=lambda t: seen_in_partial.append((t, host.relay_identity)),
    )
    host._dispatch("partial", {"text": "he", "utterance_id": 7, "session_gen": 2})
    host._final_evt.clear()
    host._dispatch("final", {"text": "hello", "utterance_id": 7, "session_gen": 2})

    assert seen_in_partial == [("he", (2, 7))]
    assert seen_in_final == [("hello", (2, 7))]
    assert host._final_evt.is_set()
    assert host.relay_identity == (2, 7)  # NamedTuple == plain tuple
    assert list(host._ids_settled) == [7]       # the final settled its id
    assert host._ids_open is None


def test_dispatch_late_post_final_partial_dropped():
    """R.5 discard rule 1: a partial whose id is already settled (realtime-thread straggler
    arriving after its final) is dropped BEFORE on_partial — no stale-tail rewind."""
    partials: list[str] = []
    finals: list[str] = []
    host = _make_host(on_final=finals.append, on_partial=partials.append)
    host._final_evt.clear()
    host._dispatch("final", {"text": "done", "utterance_id": 3, "session_gen": 1})
    host._dispatch("partial", {"text": "do", "utterance_id": 3, "session_gen": 1})  # LATE
    assert finals == ["done"]
    assert partials == [], "late post-final partial must be dropped, not relayed"


def test_dispatch_duplicate_final_dropped_but_final_evt_set_and_mark_untouched():
    """R.5 discard rule 2: a duplicate final (id settled) is NOT re-relayed to on_final, but
    _final_evt is STILL set (host.text() must unblock — VT-007/G3) and _cancel_mark is NOT
    disturbed (G5: a duplicate must not touch an already-consumed mark)."""
    finals: list[str] = []
    host = _make_host(on_final=finals.append)
    host._final_evt.clear()
    host._dispatch("final", {"text": "once", "utterance_id": 4, "session_gen": 1})
    host._cancel_mark = True  # an already-consumed mark from a previous cancelled sentinel
    host._final_evt.clear()
    host._dispatch("final", {"text": "once", "utterance_id": 4, "session_gen": 1})  # DUPLICATE
    assert finals == ["once"], "duplicate final must NOT re-fire on_final"
    assert host._final_evt.is_set(), "discarded duplicate must STILL set _final_evt (VT-007)"
    assert host._cancel_mark is True, "a discarded duplicate must not disturb _cancel_mark"


def test_dispatch_cancel_sentinel_settles_and_drops_straggler():
    """The cancel flow + the identity flow COMPOSE: the cancelled sentinel relays to on_final
    with the mark set AND settles its id, so a same-id straggler partial is dropped."""
    finals: list[str] = []
    partials: list[str] = []
    host = _make_host(on_final=finals.append, on_partial=partials.append)
    host._final_evt.clear()
    host._dispatch(
        "final", {"text": "", "cancelled": True, "utterance_id": 5, "session_gen": 1}
    )
    host._dispatch("partial", {"text": "stale", "utterance_id": 5, "session_gen": 1})
    assert finals == [""]                 # the sentinel still relays (host.text() unblocks)
    assert host._cancel_mark is True      # the mark survived stamping (additive keys)
    assert host._final_evt.is_set()
    assert partials == []                 # the cancelled utterance's stragglers are dropped
    assert list(host._ids_settled) == [5]


def test_dispatch_filtered_final_still_closes_boundary():
    """R.5/G4: the id settles BEFORE the on_final relay, so a FILTERED final (here: a raising
    callback — the clean()-rejection/cancel-suppression class) still closes its utterance
    boundary: the next same-id partial is dropped."""
    partials: list[str] = []

    def boom(_t: str) -> None:
        raise RuntimeError("downstream filter rejected the final")

    host = _make_host(on_final=boom, on_partial=partials.append)
    host._final_evt.clear()
    host._dispatch("final", {"text": "x", "utterance_id": 6, "session_gen": 1})  # raises inside
    assert host._final_evt.is_set()       # text() unblocks even though on_final raised
    host._dispatch("partial", {"text": "x", "utterance_id": 6, "session_gen": 1})
    assert partials == [], "a filtered final must still have settled its id (boundary closed)"


def test_dispatch_session_advance_clears_settled_and_drops_older_session():
    """R.5 session semantics: a newer session_gen advances the session and clears settled ids;
    an event carrying an OLDER gen than the latest seen is dropped (cross-session straggler)."""
    finals: list[str] = []
    partials: list[str] = []
    host = _make_host(on_final=finals.append, on_partial=partials.append)
    host._final_evt.clear()
    host._dispatch("final", {"text": "a", "utterance_id": 1, "session_gen": 1})
    assert list(host._ids_settled) == [1]
    host._final_evt.clear()
    host._dispatch("final", {"text": "b", "utterance_id": 2, "session_gen": 2})  # advance
    assert finals == ["a", "b"]
    assert list(host._ids_settled) == [2], "session advance must clear the previous session's settled"
    assert 1 not in host._ids_settled_set
    host._dispatch("partial", {"text": "straggler", "utterance_id": 3, "session_gen": 1})
    assert partials == [], "a gen=1 straggler after the gen=2 advance must be dropped"


def test_dispatch_cross_session_final_dropped_but_evt_set():
    """A final from an OLDER session than the latest seen is dropped (no commit), but STILL sets
    _final_evt (G3/VT-007 — host.text() unblocks on every final-kind event)."""
    finals: list[str] = []
    host = _make_host(on_final=finals.append)
    host._final_evt.clear()
    host._dispatch("final", {"text": "new", "utterance_id": 5, "session_gen": 2})  # latest=2
    host._final_evt.clear()
    host._dispatch("final", {"text": "old", "utterance_id": 5, "session_gen": 1})  # late gen=1
    assert finals == ["new"], "a cross-session final must NOT be relayed"
    assert host._final_evt.is_set(), "the dropped final must still unblock host.text()"


def test_dispatch_no_id_payloads_legacy_path():
    """G7 pin: payloads WITHOUT the identity keys dispatch byte-identically to today — no
    tracking, no discards (the same payload relayed twice is relayed twice), relay_identity
    stays (None, None), and the tracker is untouched."""
    finals: list[str] = []
    partials: list[str] = []
    host = _make_host(on_final=finals.append, on_partial=partials.append)
    host._final_evt.clear()
    host._dispatch("partial", {"text": "a"})
    host._dispatch("partial", {"text": "a"})   # identical id-less payload: relayed AGAIN
    host._dispatch("final", {"text": "done"})
    host._final_evt.clear()
    host._dispatch("final", {"text": "done"})  # identical id-less final: relayed AGAIN
    assert partials == ["a", "a"]
    assert finals == ["done", "done"]
    assert host._final_evt.is_set()
    assert host.relay_identity == (None, None)
    assert list(host._ids_settled) == [] and host._ids_settled_set == set()
    assert host._ids_latest_session == -1 and host._ids_open is None


def test_dispatch_settled_tracker_is_bounded():
    """G8 pin: settled ids are bounded (last 16) — the deque + its membership set stay exact
    mirrors across eviction (a long daemon session must not grow the tracker unboundedly)."""
    host = _make_host()
    host._final_evt.clear()
    for uid in range(1, 21):  # 20 finals in one session
        host._dispatch("final", {"text": f"u{uid}", "utterance_id": uid, "session_gen": 1})
        host._final_evt.clear()
    assert len(host._ids_settled) == 16
    assert set(host._ids_settled) == host._ids_settled_set  # exact mirror
    assert list(host._ids_settled) == list(range(5, 21))          # the LAST 16


# ---------------------------------------------------------------------------
# Layer C — sentinel stamping + the queue round-trip
# ---------------------------------------------------------------------------


def test_run_text_sentinels_stamped_with_identity():
    """_run_text_and_emit_final with ids stamps BOTH sentinels with the CURRENT id (capture at
    emission; sentinels settle — never rotate), and the cancel sentinel keeps cancelled:True
    alongside the identity keys (additive, G1)."""
    import queue as _queue

    ids = recorder_host._RelayIds()
    ids.new_session()
    ids.rotate_utterance()  # an utterance was open when the abort/cancel landed

    # CANCEL path: sentinel MARKED + stamped.
    evt_q: Any = _queue.Queue()
    rec = _CancelFakeRecorder()
    aborted, cancelled = threading.Event(), threading.Event()
    aborted.set(); cancelled.set()
    recorder_host._run_text_and_emit_final(rec, evt_q, lambda _t: None, aborted, cancelled, None, ids)
    events = _drain(evt_q)
    assert events == [
        ("final", {"text": "", "cancelled": True, "utterance_id": 1, "session_gen": 1})
    ], f"cancel sentinel must carry the mark PLUS identity; got {events!r}"

    # PLAIN ABORT path: sentinel UNMARKED + stamped (the mark must NOT leak in).
    evt_q2: Any = _queue.Queue()
    rec2 = _AbortFakeRecorder()
    aborted2 = threading.Event(); aborted2.set()
    recorder_host._run_text_and_emit_final(rec2, evt_q2, lambda _t: None, aborted2, None, None, ids)
    events2 = _drain(evt_q2)
    assert events2 == [
        ("final", {"text": "", "utterance_id": 1, "session_gen": 1})
    ], f"plain abort sentinel must carry identity WITHOUT the mark; got {events2!r}"
    # ...and stamping did NOT rotate: the same id is still current (sentinels settle).
    assert ids.stamp({})["utterance_id"] == 1


def test_identity_round_trip_queue_to_read_loop_to_dispatch():
    """Round-trip (hermetic — pytest+spawn is fragile, so the child is a thread, but the
    transport is the host's REAL mp event queue and the relay is the REAL reader loop): the
    child-side stamp chain (_RelayIds -> _with_identity -> _safe_put) travels queue ->
    _read_loop -> _dispatch; on_final sees the text AND relay_identity carries the stamped
    identity INSIDE the callback; the boundary closes (a same-id straggler is dropped)."""
    finals: list[str] = []
    partials: list[str] = []
    identity_in_final_cb: list[tuple] = []
    host = _make_host(
        on_final=lambda t: (
            finals.append(t), identity_in_final_cb.append(tuple(host.relay_identity))
        ),
        on_partial=partials.append,
    )

    def fake_child() -> None:
        ids = recorder_host._RelayIds()
        ids.new_session()       # the 'arm' bump
        ids.rotate_utterance()  # the speech-start rotation
        recorder_host._safe_put(
            host._evt_q, ("partial", recorder_host._with_identity({"text": "he"}, ids))
        )
        recorder_host._safe_put(
            host._evt_q, ("final", recorder_host._with_identity({"text": "hello"}, ids))
        )
        recorder_host._safe_put(host._evt_q, ("gone", {}))

    reader = threading.Thread(target=host._read_loop, daemon=True)
    child = threading.Thread(target=fake_child, daemon=True)
    reader.start()
    child.start()
    child.join(timeout=5)
    reader.join(timeout=5)
    assert not reader.is_alive() and not child.is_alive()
    assert partials == ["he"] and finals == ["hello"]
    assert identity_in_final_cb == [(1, 1)], (
        "relay_identity INSIDE on_final must be the identity of the relayed final "
        f"(the T2.S1 seam); got {identity_in_final_cb!r}"
    )
    assert list(host._ids_settled) == [1]  # the boundary closed
    assert host._dead is True        # 'gone' ended the reader cleanly


# ===========================================================================
# P1.M2.T1.S1 (BUG-002 remediation / PRD §4.2sexies R.8) — the partial_source
# selector crosses the spawn boundary HERE: the picklable str rides the
# ctx.Process args into _worker_main and is threaded into EVERY build_recorder
# call (the normal build AND the force_cpu CPU-fallback retry), and the
# child's ('ready', ...) payload reports the installed key ("partial_callback")
# as the G5 provenance. Hermetic: the spawn-context Process is faked;
# _worker_main runs IN-PROCESS with daemon.build_recorder monkeypatched and
# os.setsid stubbed — never a real child, never CUDA.
# ===========================================================================


def test_host_stores_partial_source_default_stabilized():
    """__init__ stores partial_source (keyword-only tail; default 'stabilized' = the
    production path, byte-identical — the lab seam mirrors feed_input)."""
    host = _make_host()
    assert host._partial_source == "stabilized"
    host2 = _make_host(partial_source="plain")
    assert host2._partial_source == "plain"


def test_spawn_args_carry_partial_source(monkeypatch):
    """The spawn args tuple carries the selector as its LAST element (a picklable str — the
    constructor-data path spawn isolation mandates; a parent monkeypatch dies in the child)."""
    real_ctx = recorder_host.mp.get_context("spawn")
    procs: list[Any] = []

    class _FakeProc:
        pid = 4242

        def __init__(self, target=None, args=None, name=None, daemon=None):
            self.target = target
            self.args = args
            procs.append(self)

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return False

    class _FakeCtx:
        """Only Process is faked; Queue/Event delegate to the REAL spawn context (the host's
        __init__ builds its queues/events there — only spawn()'s Process creation is intercepted)."""

        def __init__(self, real):
            self._real = real

        def Queue(self):
            return self._real.Queue()

        def Event(self):
            return self._real.Event()

        def Process(self, **kw):
            return _FakeProc(**kw)

    monkeypatch.setattr(recorder_host.mp, "get_context", lambda _name: _FakeCtx(real_ctx))

    host = _make_host()
    host._ready_evt.set()  # no child will signal; spawn() must return immediately
    assert host.spawn() is True
    assert procs and isinstance(procs[0].args[-1], str)
    assert procs[0].args[-1] == "stabilized"  # the default rides too (no special-casing)

    host_plain = _make_host(partial_source="plain")
    host_plain._ready_evt.set()
    assert host_plain.spawn() is True
    assert procs[-1].args[-1] == "plain"

    # Clean up both spawn()-started reader threads (they drain the real mp event queues).
    for host_ in (host, host_plain):
        host_._evt_q.put(("gone", {}))
        assert host_._reader is not None
        host_._reader.join(timeout=2.0)
        assert not host_._reader.is_alive()


def _run_worker_and_drain(monkeypatch, *, partial_source, first_build_raises):
    """Shared in-process harness for _worker_main: daemon.build_recorder is captured (the
    first CUDA build raising when requested, to exercise the force_cpu fallback) and the
    command queue is pre-loaded with ('shutdown', {}) so the loop exits cleanly. os.setsid is
    stubbed — the child entry point runs on the pytest main thread, never a real process.
    Returns (build-calls, drained events)."""
    import queue as _queue

    import voice_typing.daemon as daemon_mod
    from voice_typing.config import VoiceTypingConfig

    calls: list[dict] = []

    class _Rec:
        def shutdown(self) -> None:
            pass

        def set_microphone(self, on: bool) -> None:
            pass

    rec = _Rec()

    def _fake_build(cfg2, feedback, latency=None, force_cpu=False, on_speech=None,
                    extra_kwargs=None, partial_source="stabilized"):
        calls.append({"force_cpu": bool(force_cpu), "partial_source": partial_source})
        if first_build_raises and not force_cpu:
            raise RuntimeError("cuda boom")
        return rec

    monkeypatch.setattr(daemon_mod, "build_recorder", _fake_build)
    monkeypatch.setattr(recorder_host.os, "setsid", lambda: None)

    cmd_q: Any = _queue.Queue()
    cmd_q.put(("shutdown", {}))
    evt_q: Any = _queue.Queue()
    recorder_host._worker_main(
        VoiceTypingConfig(),
        cmd_q,
        evt_q,
        threading.Event(),
        threading.Event(),
        False,               # force_cpu (the child retries on failure, as in production)
        None,                # feed_q (production: None)
        partial_source,
    )
    return calls, _drain(evt_q)


def test_worker_main_threads_partial_source_to_both_build_paths(monkeypatch):
    """partial_source reaches EVERY build_recorder call in the child — the normal CUDA build
    AND the force_cpu retry — and the 'ready' payload reports the installed key (the G5
    provenance: build success ⟹ the key survived the signature filter)."""
    calls, events = _run_worker_and_drain(
        monkeypatch, partial_source="plain", first_build_raises=True
    )
    assert calls == [
        {"force_cpu": False, "partial_source": "plain"},
        {"force_cpu": True, "partial_source": "plain"},
    ]
    ready = [p for kind, p in events if kind == "ready"]
    assert ready and ready[0]["partial_callback"] == "on_realtime_transcription_update"
    assert ("gone", {}) in events


def test_worker_main_default_partial_source_is_stabilized(monkeypatch):
    """Omitting nothing (the default arg) keeps the production path byte-identical: the build
    gets 'stabilized' and the ready payload reports the stabilized key."""
    calls, events = _run_worker_and_drain(
        monkeypatch, partial_source="stabilized", first_build_raises=False
    )
    assert calls == [{"force_cpu": False, "partial_source": "stabilized"}]
    ready = [p for kind, p in events if kind == "ready"]
    assert ready and ready[0]["partial_callback"] == "on_realtime_transcription_stabilized"


def test_ready_payload_reports_partial_callback():
    """_ready_payload carries the INSTALLED key verbatim (the _worker_main call site maps the
    selector via daemon._PARTIAL_SOURCES — post-rejection, effective == requested) alongside
    the existing device/context_prompt keys (additive); unknown degrades to ""."""
    payload = recorder_host._ready_payload(
        {"device": "cpu", "compute_type": "int8", "model": "tiny.en"},
        False,
        "on_realtime_transcription_update",
    )
    assert payload["partial_callback"] == "on_realtime_transcription_update"
    assert payload["context_prompt"] is False
    assert payload["device"] == "cpu"
    assert (
        recorder_host._ready_payload({"device": "cpu"}, True)["partial_callback"] == ""
    )  # legacy/no-provenance default


def test_dispatch_ready_exposes_partial_callback_on_the_host():
    """The reader's 'ready' dispatch exposes the provenance on the host alongside .device;
    a legacy payload WITHOUT the key (test fakes predating it) degrades to '' (the
    context_prompt precedent)."""
    host = _make_host()
    host._dispatch(
        "ready",
        {
            "device": "cuda",
            "compute_type": "float16",
            "model": "small.en",
            "partial_callback": "on_realtime_transcription_update",
        },
    )
    assert host.partial_callback == "on_realtime_transcription_update"
    assert host.device["model"] == "small.en"

    host2 = _make_host()
    host2._dispatch("ready", {"device": "cuda"})
    assert host2.partial_callback == ""
