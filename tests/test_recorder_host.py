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
    *, on_final=None, on_partial=None, on_speech=None, force_cpu=False
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
    device = {"device": "cuda", "compute_type": "float16",
              "final_model": "distil-large-v3", "realtime_model": "small.en"}
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
    device = {"device": "cuda", "compute_type": "float16",
              "final_model": "distil-large-v3", "realtime_model": "small.en"}
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
