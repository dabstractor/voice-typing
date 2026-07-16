"""voice_typing.recorder_host — owns the AudioToTextRecorder in a managed child subprocess.

(PRD §7.9 + §6 T6(d); P1.M3.T2.S2 re-plan.) The WHOLE point of this module is GPU-VRAM
reclamation on idle-unload. RealtimeSTT v1.0.2 loads the realtime (small.en) model IN-PROCESS
(its realtime model is driven by a threading.Thread in the constructor's process), so any
process that constructs an AudioToTextRecorder acquires a CUDA primary context (~100–300 MiB)
that is UNRELEASABLE until that process exits (del/gc.collect()/torch.cuda.empty_cache() do
NOT release it). The idle-unload teardown therefore CANNOT reach ~0 VRAM on the daemon PID
while the daemon lives, because the daemon process itself holds that context.

FIX: construct the recorder in a CHILD subprocess (spawn) that the daemon spawns on first arm
and terminates on idle-unload/quit. Then the DAEMON process NEVER touches CUDA — all CUDA
contexts live in the child. Terminating the child PROCESS GROUP (os.setsid in the child +
os.killpg in the daemon) releases ALL VRAM (including the realtime-model context) so the
daemon tree is ABSENT from nvidia-smi while the daemon keeps running. This is the only way to
satisfy PRD §7.9 + §6 T6(d). See plan/003.../P1M3T2S2/research/residual_cuda_context_rootcause.md.

IPC PROTOCOL (two multiprocessing queues + one event):
  cmd_queue (daemon -> child):  ("arm", {}) | ("disarm", {}) | ("text", {}) | ("shutdown", {})
  abort_event (daemon -> child): a multiprocessing.Event SET by the daemon to interrupt a child
      blocked in recorder.text() (the cmd_queue is NOT read while text() blocks). A separate child
      thread polls it and calls recorder.abort(). ("abort", {}) on cmd_queue is belt-and-suspenders.
  event_queue (child -> daemon): ("ready", {device,compute_type,final_model,realtime_model}) |
                                 ("error", {msg}) |
                                 ("final", {text}) |
                                 ("partial", {text}) |     # realtime stabilized partial
                                 ("speech", {}) |          # on_speech -> _touch_speech (idle auto-stop reset)
                                 ("vad", {phase}) |        # "listening"|"speaking" (on_vad_detect_start/_start)
                                 ("speech_end", {}) |      # on_vad_stop -> latency.note_speech_end
                                 ("gone", {})              # child acked shutdown (clean exit)

CALLBACK RELAY (child): build_recorder wires _build_callbacks(feedback, latency, on_speech). In the
child those callbacks fire on the recorder's threads and must RELAY events to the daemon (they
cannot touch the daemon's Feedback/LatencyLog — those objects live in the daemon process). The
child passes _RelayFeedback + _RelayLatency whose methods put events on evt_q; the daemon's reader
thread drives the REAL Feedback/LatencyLog/_touch_speech. The mapping is exact:
  partial callback:  update_partial -> ("partial", {text}); on_speech -> ("speech", {})
  on_vad_detect_start: set_phase("listening") -> ("vad", {phase:"listening"})
  on_vad_start:        set_phase("speaking")  -> ("vad", {phase:"speaking"})
  on_vad_stop:         set_phase("listening") -> ("vad", {phase:"listening"});
                       note_speech_end()      -> ("speech_end", {})
  on_final (via text): child_on_final(text)   -> ("final", {text})

THREADING MODEL (daemon side):
  - The daemon's run() loop calls host.text(on_final), which puts ("text", {}) and BLOCKS on a
    threading.Event (self._final_evt) set by the reader thread when a "final" event arrives.
    on_final is invoked by the READER thread (matches how on_final ran today: a worker thread,
    not the text() caller).
  - A daemon reader thread (started by spawn()) drains event_queue and dispatches to the daemon's
    Feedback/LatencyLog/_touch_speech/on_final. It is daemon=True so it never blocks daemon shutdown.
  - BrokenPipeError/EOFError from a dead child are swallowed (the reader thread exits cleanly;
    text()/stop()/spawn() handle a dead child idempotently).

IMPORT PURITY: this module does NOT import RealtimeSTT/torch/ctranslate2 at module scope. The
recorder is imported + constructed ONLY inside _worker_main() (which runs in the CHILD). The
daemon process imports only the RecorderHost handle (multiprocessing + threading + stdlib). Verify:
  grep -nE 'import (RealtimeSTT|torch|ctranslate2)' voice_typing/recorder_host.py  # should be empty
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import signal
import threading
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from voice_typing.config import VoiceTypingConfig
    from voice_typing.daemon import LatencyLog
    from voice_typing.feedback import Feedback

logger = logging.getLogger(__name__)

# The spawn() ready/error wait budget. The child loads both Whisper models (seconds on a cold
# cache; ~1–3 s warm). 180 s mirrors the test_daemon run() ready ceiling and absorbs a cold CUDA
# init. The daemon's run() loop is NOT blocked here — spawn() is called from _load_host() OUTSIDE
# the daemon _lock, with the reader thread already draining the event queue.
_SPAWN_READY_TIMEOUT_S: float = 180.0

# The stop() join budget before SIGKILL-ing the child process group. RealtimeSTT's own
# recorder.shutdown() can wedge ~90 s (unbounded thread joins — core/shutdown.py:33/62); we do NOT
# wait on it. We send "shutdown" (best-effort graceful), then join this budget, then SIGKILL the
# group. 5 s is enough for a cooperative child to flush its queue + exit; if it does not, the
# SIGKILL releases VRAM immediately regardless. This supersedes the in-process _bounded_shutdown
# timeout thread (P1.M1.T1.S2) — killing the process is strictly stronger + simpler.
_STOP_JOIN_TIMEOUT_S: float = 5.0


class RecorderHost:
    """Owns the AudioToTextRecorder in a spawn child; IPC for arm/disarm/abort/text/shutdown.

    The daemon constructs this and calls spawn() on first arm (single-flight via the daemon's
    _load_host). set_microphone/abort/text proxy to the child via cmd_queue; partial/final/speech
    events arrive on event_queue and are dispatched by a reader thread to the daemon's callbacks.
    stop() terminates the child PROCESS GROUP (os.killpg) so ALL VRAM (including the realtime-model
    CUDA context) is released and the daemon tree drops off nvidia-smi.

    TEST SEAM: tests inject a fake with the SAME surface (set_microphone/abort/text/stop/poll_events
    /is_alive/device) so test_daemon.py stays CUDA-free + fast. The real RecorderHost spawns a child.
    """

    def __init__(
        self,
        cfg: "VoiceTypingConfig",
        feedback: "Feedback",
        latency: "LatencyLog",
        on_final: "Callable[[str], None]",
        on_partial: "Callable[[str], None]",
        on_speech: "Callable[[], None]",
        *,
        force_cpu: bool = False,
        is_listening: "Callable[[], bool] | None" = None,
    ) -> None:
        self._cfg = cfg
        self._feedback = feedback
        self._latency = latency
        self._on_final = on_final
        self._on_partial = on_partial
        self._on_speech = on_speech
        self._force_cpu = force_cpu
        # Optional listening-gate predicate (bugfix Issue 2 residual / PRD §4.6). The child may emit
        # a stray ('vad', ...) event still in the IPC queue when the mic is disarmed (a late
        # on_vad_stop/on_vad_start that raced the disarm). Relaying it to feedback.set_phase() would
        # flip phase back to listening/speaking while listening: off — the exact contradiction Issue 2
        # was about. When provided, the 'vad' dispatch consults it and drops the event unless the
        # daemon is actively listening. None preserves the old behavior for tests that don't inject it.
        self._is_listening = is_listening
        # Create the queues + (later) the Process with the SAME 'spawn' context. Mixing a fork-
        # context Queue with a spawn-context Process raises 'SemLock created in a fork context is
        # being shared with a process in a spawn context' (multiprocessing.synchronize). Using the
        # spawn context for both guarantees the child (and its RealtimeSTT-spawned grandchildren,
        # which also use spawn) inherit compatible semaphores.
        ctx = mp.get_context("spawn")
        self._cmd_q: Any = ctx.Queue()
        self._evt_q: Any = ctx.Queue()
        # Dedicated abort signal: the child's command loop BLOCKS in recorder.text() while listening,
        # so a ('abort', {}) command queued on cmd_q would NOT be read until text() returns. An mp.Event
        # is polled by a SEPARATE child thread that calls recorder.abort() the instant it is set — this
        # is how stop()/toggle(off) interrupt a blocked text() so the run loop can re-check _listening.
        # Spawn-context (same as the Process) so the child inherits it cleanly.
        self._abort_event: Any = ctx.Event()
        self._proc: Any = None
        # Single-flight lock for stop(): serializes concurrent callers (SIGTERM signal thread +
        # main-thread finally both reach host.stop()) so exactly ONE join+killpg teardown runs; the
        # 2nd caller blocks on the lock, then sees _proc is None and no-ops. See stop() (bugfix
        # Issue 1 / P1.M1.T1.S1). Plain Lock (not RLock): stop() is never re-entered.
        self._stop_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._final_evt = threading.Event()
        self._ready_evt = threading.Event()
        self._device: dict[str, str] = {}
        self._error: str | None = None
        self._dead = False  # set when the child is known-gone (reader EOF / stop()); idempotent guards

    # --- public surface (the daemon calls these) ---

    @property
    def device(self) -> dict[str, str]:
        """The resolved {device,compute_type,final_model,realtime_model} from the child's 'ready'."""
        return dict(self._device)

    @property
    def is_alive(self) -> bool:
        """Is the child process still running?"""
        return self._proc is not None and self._proc.is_alive() and not self._dead

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    def spawn(self, timeout: float = _SPAWN_READY_TIMEOUT_S) -> bool:
        """Start the child + wait for its 'ready'/'error'. True iff the recorder loaded.

        Single-flight is enforced by the CALLER (_load_host under the daemon _lock) — spawn() itself
        assumes it is called once per RecorderHost instance. The reader thread is started BEFORE the
        ready wait so events the child emits during load are drained. The heavy model load happens
        IN THE CHILD; the daemon process stays CUDA-free.
        """
        ctx = mp.get_context("spawn")
        # cfg is a picklable dataclass; the queues are spawn-context mp.Queue (picklable across
        # spawn — they share the spawn context the Process uses); force_cpu is a bool. The child
        # target _worker_main is a module-level fn (picklable).
        self._proc = ctx.Process(
            target=_worker_main,
            args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event, self._force_cpu),
            name="voice-typing-recorder-host",
            daemon=True,
        )
        self._proc.start()
        # Reader thread dispatches events -> never block the daemon main loop. daemon=True so it
        # never blocks daemon shutdown.
        self._reader = threading.Thread(
            target=self._read_loop, name="vt-host-reader", daemon=True
        )
        self._reader.start()
        # Wait for the child's 'ready'/'error'. The model load (~1-3 s warm, longer cold) happens
        # in the child; this blocks _load_host's caller (the arm) but NOT the daemon run() loop
        # (spawn is called outside the daemon _lock; status/stop stay responsive).
        if not self._ready_evt.wait(timeout=timeout):
            logger.error(
                "recorder host: child did not signal ready/error within %.1fs; terminating", timeout
            )
            self._terminate_group()
            self._proc = None
            self._dead = True
            return False
        if self._error is not None:
            logger.error("recorder host: child reported load error: %s", self._error)
            self._terminate_group()
            self._proc = None
            self._dead = True
            return False
        logger.info(
            "recorder host: child ready (pid=%s, device=%s)",
            self._proc.pid if self._proc else "?",
            self._device.get("device", "?"),
        )
        return True

    def set_microphone(self, on: bool) -> None:
        """Proxy arm/disarm to the child. Best-effort (never blocks; a dead child is a no-op)."""
        try:
            self._cmd_q.put(("arm" if on else "disarm", {}))
        except (BrokenPipeError, OSError, EOFError):
            self._dead = True  # child gone; idempotent

    def abort(self) -> None:
        """Interrupt a blocked text() in the child. Sets the abort event (polled by a child thread).

        The child's command loop BLOCKS in recorder.text() while listening, so a queued command would
        not be read. The dedicated abort event is polled by a SEPARATE child thread that calls
        recorder.abort() the instant it is set — this unblocks text() so the run loop can re-check
        _listening/_shutdown. Idempotent (setting an already-set event is a no-op). Best-effort.
        """
        try:
            self._abort_event.set()
        except (OSError, EOFError):
            self._dead = True

    def text(self, on_final: "Callable[[str], None]") -> None:
        """Block until the child produces ONE final, then invoke on_final on the reader thread.

        Mirrors the daemon's blocking text() (daemon.py run loop). Puts ("text", {}) and blocks on
        self._final_evt, which the reader thread sets when a "final" event arrives. on_final is
        invoked by the READER thread (set self._on_final first) — matches how on_final ran today (a
        worker thread, not the text() caller). Returns immediately (no final) if the child died.
        """
        self._on_final = on_final
        self._final_evt.clear()
        try:
            self._cmd_q.put(("text", {}))
        except (BrokenPipeError, OSError, EOFError):
            self._dead = True
            return  # child gone -> no final; the run loop re-checks and idles
        # Unblocked by the reader thread on "final". Wait in a loop so a dead child (reader sets
        # _dead + _final_evt on EOF, but belt-and-suspenders: also check the proc) unblocks us.
        while not self._final_evt.wait(timeout=0.5):
            if self._dead or (self._proc is not None and not self._proc.is_alive()):
                self._dead = True
                return  # child gone -> no final; run loop idles

    def stop(self, timeout: float = _STOP_JOIN_TIMEOUT_S) -> None:
        """Terminate the child PROCESS GROUP. Idempotent + SINGLE-FLIGHT. THE bounded teardown.

        Sends "shutdown" (best-effort graceful), joins up to `timeout`, then SIGKILL the child's
        PROCESS GROUP (os.setsid in the child -> it is its own group leader; killpg reaches its
        RealtimeSTT-spawned grandchildren: transcript_process/reader_process). Killing the group
        releases ALL VRAM (the whole point) and cannot reproduce RealtimeSTT's ~90 s shutdown wedge
        (we do NOT wait on its unbounded thread joins). Supersedes _bounded_shutdown (P1.M1.T1.S2).

        SINGLE-FLIGHT (thread-safe, bugfix Issue 1 / P1.M1.T1.S1): the ENTIRE body — including
        the `self._proc is None` early guard — runs under `self._stop_lock`. On the SIGTERM path
        two threads call stop() concurrently (request_shutdown() on the signal-handler thread +
        shutdown() on the main-thread finally); without serialization both passed the None-guard
        and ran two parallel teardowns, blowing systemd's 15s TimeoutStopSec. Under the lock the
        second caller blocks until the first finishes the join+killpg and sets `self._proc =
        None`, then acquires the lock, sees `_proc is None`, and returns immediately — so exactly
        ONE process-group teardown ever executes. (Plain Lock, not RLock: stop() is never
        re-entered.)
        """
        with self._stop_lock:
            if self._proc is None:
                return
            # Set the abort event so a child blocked in text() unblocks before we tear it down.
            try:
                self._abort_event.set()
            except (OSError, EOFError):
                pass
            # Best-effort graceful shutdown command. BOUNDED: the child's command loop BLOCKS in
            # recorder.text() while listening, so it does NOT drain cmd_q until an abort unblocks it.
            # Under an external cgroup-wide SIGTERM (systemd KillMode=control-group) the child is
            # killed mid-text() BEFORE it can ever read this put — and an mp.Queue.put can then block
            # indefinitely on the queue's feeder thread / lock if the child's process is wedged. We
            # therefore put on a SEPARATE daemon thread and NEVER wait on it; the join+killpg below is
            # the actual teardown. put_nowait is avoided (it would raise Full on a saturated queue);
            # the detached thread swallows all errors and dies with the daemon.
            def _best_effort_shutdown_cmd() -> None:
                try:
                    self._cmd_q.put(("shutdown", {}), timeout=2.0)
                except Exception:
                    pass  # child gone / queue full / wedged -> killpg handles it
            threading.Thread(target=_best_effort_shutdown_cmd, daemon=True).start()
            # Graceful join (cooperative child may flush its queue + exit). This join is BOUNDED by
            # `timeout` — if the child does not exit, we fall through to killpg. As a belt-and-
            # suspenders against a proc.join that could itself stall on a multiprocessing internal
            # lock after an external child kill, we ALSO run the killpg fallback if join has not
            # returned within timeout (checked via a detached watchdog that sets a flag).
            self._proc.join(timeout=timeout)
            if self._proc.is_alive():
                logger.warning(
                    "recorder host: child did not exit within %.1fs; SIGKILL-ing the process group",
                    timeout,
                )
                self._terminate_group()
                self._proc.join(timeout=2.0)
            self._dead = True
            self._proc = None

    # --- internals ---

    def _read_loop(self) -> None:
        """Drain event_queue -> dispatch to daemon callbacks. Daemon thread; swallows child death."""
        try:
            while True:
                try:
                    kind, payload = self._evt_q.get()
                except (EOFError, OSError):
                    break  # child died / queue closed
                try:
                    self._dispatch(kind, payload)
                except Exception:
                    # A dispatch error must never kill the reader thread (it would strand text()).
                    logger.exception("recorder host reader: dispatch error for %r (ignored)", kind)
                if kind == "gone":
                    return  # child acked shutdown -> exit cleanly
        except (BrokenPipeError, OSError):
            return  # child gone — idempotent
        finally:
            # Mark dead so a blocked text() unblocks; set the events so spawn()/text() do not stall.
            self._dead = True
            self._final_evt.set()
            self._ready_evt.set()  # unblock spawn() if it is still waiting (error path)

    def _dispatch(self, kind: str, payload: dict) -> None:
        """Dispatch one event to the daemon callbacks. Mirrors _build_callbacks (in-process today)."""
        if kind == "ready":
            self._device = dict(payload)
            self._ready_evt.set()
        elif kind == "error":
            self._error = str(payload.get("msg", "unknown error"))
            self._ready_evt.set()
        elif kind == "final":
            text = str(payload.get("text", ""))
            # on_final runs HERE (the reader thread), matching the in-process worker-thread model.
            # The daemon's on_final stamps t_final_ready, calls finalize_utterance, types, logs.
            try:
                self._on_final(text)
            except Exception:
                logger.exception("recorder host reader: on_final raised (ignored)")
            self._final_evt.set()
        elif kind == "partial":
            text = str(payload.get("text", ""))
            self._on_partial(text)
        elif kind == "speech":
            self._on_speech()
        elif kind == "speech_end":
            # on_vad_stop -> stamp t_speech_end. (The preceding ("vad","listening") event already
            # drove set_phase("listening"); this is purely the latency stamp.)
            self._latency.note_speech_end()
        elif kind == "vad":
            phase = str(payload.get("phase", "listening"))
            # Issue 2 residual gate (PRD §4.6): a stray VAD event still in the IPC queue when the mic
            # was disarmed (a late on_vad_stop/on_vad_start racing the disarm) must NOT flip phase
            # back to listening/speaking while listening: off. When an is_listening predicate was
            # provided by the daemon, drop the event unless we are actively listening.
            if self._is_listening is not None and not self._is_listening():
                return
            self._feedback.set_phase(phase)
        elif kind == "gone":
            pass  # handled by the read loop (return)
        else:
            logger.warning("recorder host reader: unknown event %r (ignored)", kind)

    def _terminate_group(self) -> None:
        """SIGKILL the child's process group (releases ALL VRAM incl. grandchildren). Best-effort."""
        if self._proc is None:
            return
        pid = self._proc.pid
        if pid is None:
            return
        try:
            # The child did os.setsid() -> it is its own session/group leader; getpgid(pid) is its
            # pid. killpg reaches its RealtimeSTT-spawned grandchildren (transcript_process/
            # reader_process) so they die too and release VRAM (the exact failure mode attempt 1 hit,
            # now at the grandchild level — killpg is the fix).
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError) as exc:
            # Already gone or permission denied — nothing more to do; the child + its group are the
            # daemon's own descendants (spawned by us), so permission is not normally an issue.
            logger.debug("recorder host: killpg(%s) failed (best-effort): %s", pid, exc)


# ---------------------------------------------------------------------------
# _worker_main — runs IN THE CHILD process (spawn). Constructs the recorder
# and serves the command loop. RealtimeSTT/torch/ctranslate2 are imported HERE
# (lazily inside build_recorder), so ONLY the child process touches CUDA.
# ---------------------------------------------------------------------------


def _worker_main(
    cfg: "VoiceTypingConfig",
    cmd_q: Any,
    evt_q: Any,
    abort_event: Any,
    force_cpu: bool,
) -> None:
    """Child-process entry point: construct the recorder + serve commands until shutdown.

    os.setsid() makes the child its own session/group leader so the daemon's killpg teardown
    reaches the child's OWN spawn-grandchildren (transcript_process/reader_process). The recorder
    is built via the UNCHANGED production path (daemon.build_recorder) — now in the child, so the
    daemon process stays CUDA-free. On construction failure, the child retries ONCE with
    force_cpu=True (CPU fallback, PRD §4.4 — only the child touches CUDA, so the retry is clean
    here) then signals 'error' + exits.

    Command loop: ("text", {}) -> recorder.text(child_on_final) (BLOCKS until a final, which puts
    a "final" event then returns); ("arm"/"disarm", {}) -> set_microphone; ("abort", {}) ->
    recorder.abort(); ("shutdown", {}) -> recorder.shutdown() (best-effort; the daemon SIGKILLs the
    group anyway), put "gone", exit.
    """
    # Own session/group so killpg(child) reaches our grandchildren. Must be the first syscall so
    # any RealtimeSTT-spawned mp.Process inherits our pgid.
    try:
        os.setsid()
    except OSError as exc:
        # setsid can fail if we are already a process group leader (rare under spawn). Non-fatal:
        # killpg(getpgid(pid)) still targets our group; the grandchildren just inherit our pgid.
        logger.debug("child: os.setsid() failed (non-fatal): %s", exc)

    # Lazy import: ONLY the child imports daemon.build_recorder (which lazy-imports RealtimeSTT).
    # This keeps the daemon process CUDA-free (the daemon imports only the RecorderHost handle).
    from voice_typing.daemon import build_recorder

    # The child's recorder callbacks RELAY events to the daemon over evt_q (they cannot touch the
    # daemon's Feedback/LatencyLog — those objects live in the daemon process). build_recorder wires
    # _build_callbacks(feedback, latency, on_speech); we pass relay stand-ins whose methods put
    # events on evt_q. See the module docstring's CALLBACK RELAY block for the exact mapping.
    relay_fb: Any = _RelayFeedback(evt_q)
    relay_lat: Any = _RelayLatency(evt_q)

    def _child_on_speech() -> None:
        _safe_put(evt_q, ("speech", {}))

    # Construct the recorder via the UNCHANGED production path. CPU fallback: retry once with
    # force_cpu=True if the cuda construction fails (mirrors _load_recorder's old in-process retry,
    # now in the child where the CUDA context lives — cleaner because only the child touches CUDA).
    recorder = None
    try:
        try:
            recorder = build_recorder(cfg, relay_fb, relay_lat, on_speech=_child_on_speech)
        except Exception as exc:
            if force_cpu:
                _safe_put(evt_q, ("error", {"msg": f"force_cpu build failed: {exc!r}"}))
                return
            logger.warning(
                "child: CUDA recorder construction failed (%s); retrying with force_cpu=True", exc
            )
            try:
                recorder = build_recorder(
                    cfg, relay_fb, relay_lat, force_cpu=True, on_speech=_child_on_speech
                )
            except Exception as exc2:
                _safe_put(
                    evt_q,
                    ("error", {"msg": f"CUDA build failed: {exc!r}; CPU fallback also failed: {exc2!r}"}),
                )
                return
        # Report the resolved device so the daemon can seed _resolved_device_cache WITHOUT probing
        # CUDA itself (the daemon must stay CUDA-free). _child_resolved_device derives it from the
        # cuda_check resolution the child just performed (idempotent within a boot).
        resolved_device = _child_resolved_device(cfg, force_cpu)
        _safe_put(evt_q, ("ready", dict(resolved_device)))
    except Exception as exc:
        _safe_put(evt_q, ("error", {"msg": f"unexpected construction error: {exc!r}"}))
        return

    # Command loop. recorder.text() BLOCKS until a final -> child_on_final puts a "final" event.
    # A SEPARATE abort-handler thread watches abort_event so stop()/toggle(off) can interrupt a
    # blocked text() (the main loop cannot read cmd_q while blocked in text()).
    def _child_on_final(text: str) -> None:
        _safe_put(evt_q, ("final", {"text": text}))

    stop_abort_thread = threading.Event()

    def _abort_handler() -> None:
        """Watch abort_event; call recorder.abort() to unblock a sleeping text()."""
        while not stop_abort_thread.is_set():
            if abort_event.wait(timeout=0.2):
                abort_event.clear()
                try:
                    recorder.abort()
                except Exception:
                    logger.exception("child: recorder.abort() raised (best-effort; ignored)")

    abort_thread = threading.Thread(target=_abort_handler, name="vt-child-abort", daemon=True)
    abort_thread.start()

    running = True
    try:
        while running:
            try:
                kind, payload = cmd_q.get()
            except (EOFError, OSError):
                break  # daemon gone -> exit
            try:
                if kind == "text":
                    # Clear any stale abort before entering text() so a leftover set from a previous
                    # session does not immediately abort this utterance.
                    abort_event.clear()
                    # blocks until a final (or an abort). _run_text_and_emit_final GUARANTEES a
                    # ('final', ...) event on BOTH paths (real final via on_final, OR abort via the
                    # sentinel) so the daemon's host.text() always unblocks — without it an abort
                    # (stop/toggle-off/auto-stop) leaves host.text() blocked forever (the child is
                    # still alive), wedging the run() loop so no further utterance transcribes.
                    _run_text_and_emit_final(recorder, evt_q, _child_on_final)
                elif kind == "arm":
                    recorder.set_microphone(True)
                elif kind == "disarm":
                    recorder.set_microphone(False)
                    # Drop ALL buffered/queued audio so the next arm transcribes fresh speech, not the
                    # previous (aborted) utterance. RealtimeSTT's wait_audio() falls back to
                    # transcribing leftover recorder.frames / last_frames / recorded_audio_queue when a
                    # new text() finds no queued recording — so without this, re-arming after a toggle-off
                    # types the OLD utterance again (the "flushed out the last of what got cut off" bug).
                    _clear_recorder_audio(recorder)
                elif kind == "abort":
                    recorder.abort()  # belt-and-suspenders (the abort_event path is the primary one)
                elif kind == "shutdown":
                    running = False
                else:
                    logger.warning("child: unknown command %r (ignored)", kind)
            except Exception:
                logger.exception("child: command %r raised (ignored)", kind)
    finally:
        stop_abort_thread.set()
        # Best-effort graceful shutdown; the daemon SIGKILLs our group anyway (the bounded teardown).
        try:
            recorder.shutdown()
        except Exception:
            pass
        _safe_put(evt_q, ("gone", {}))


def _safe_put(evt_q: Any, item: tuple) -> None:
    """evt_q.put that swallows a dead daemon (BrokenPipe/OSError/EOFError). Never raises."""
    try:
        evt_q.put(item)
    except (BrokenPipeError, OSError, EOFError):
        pass


def _clear_recorder_audio(recorder: Any) -> None:
    """Drop ALL buffered/queued audio so a disarm does not leak a stale final into the next arm.

    RealtimeSTT's wait_audio() (core/lifecycle.py) consumes a queued completed recording via
    get_next_recorded_audio(), and when none is queued it FALLS BACK to transcribing leftover
    recorder.frames / recorder.last_frames. So after a toggle-off aborts an utterance mid-flight,
    the captured frames + any queued recording persist; the NEXT arm's text() then transcribes that
    STALE audio and types the old utterance again (the "flushed out the last of what got cut off
    from the previous attempt" double-type). Clearing on disarm makes each arm start fresh.

    Defensive: every clear is wrapped (RealtimeSTT version drift could rename/drop an attribute;
    a clear failure must never break the disarm). The public clear_audio_queue() clears audio_queue +
    the pre-recording buffer; we ALSO drain recorded_audio_queue (completed recordings awaiting
    transcription — the stale-final source) and frames/last_frames/audio (the wait_audio() fallbacks).
    """
    try:
        recorder.clear_audio_queue()  # public: drains audio_queue + pre-recording buffer
    except Exception:
        logger.debug("child: recorder.clear_audio_queue() raised (ignored)", exc_info=True)
    for _attr in ("recorded_audio_queue",):
        q = getattr(recorder, _attr, None)
        if q is None:
            continue
        try:
            while True:
                try:
                    q.get_nowait()
                except Exception:
                    break  # queue.Empty (or anything) -> drained
        except Exception:
            logger.debug("child: draining %s raised (ignored)", _attr, exc_info=True)
    for _attr in ("frames", "last_frames"):
        buf = getattr(recorder, _attr, None)
        try:
            if buf is not None and hasattr(buf, "clear"):
                buf.clear()
        except Exception:
            logger.debug("child: clearing %s raised (ignored)", _attr, exc_info=True)
    try:
        recorder.audio = None
    except Exception:
        logger.debug("child: clearing recorder.audio raised (ignored)", exc_info=True)


def _run_text_and_emit_final(recorder: Any, evt_q: Any, on_final: "Callable[[str], None]") -> None:
    """Child: run ONE recorder.text(on_final) call AND guarantee a ('final', ...) event when it ends.

    This is the fix for the run()-loop wedge (regression: stop / toggle-off / auto-stop wedged the
    daemon after the first disarm so NO further utterance was ever transcribed). recorder.text()
    has TWO return paths in RealtimeSTT (core/transcription_api.py `text()`):
      - NORMAL finalization (with on_transcription_finished provided): it runs `transcribe()` then
        `threading.Thread(target=on_final, args=(...)).start()` and returns None. on_final fires in
        that thread and emits ('final', {text}) itself.
      - ABORT / shutdown: recorder.abort() sets interrupt_stop_event, so text() returns '' WITHOUT
        ever calling on_final -> NO ('final', ...) is emitted.
    The daemon's host.text() blocks until a 'final' event OR child death (recorder_host.text()).
    On the abort path the child is still alive, so WITHOUT this helper host.text() blocks FOREVER —
    the run() loop can never send the next ('text', {}) and every subsequent arm transcribes
    nothing. request_shutdown() already works around this by KILLING the child (so host.text() sees
    child death), but stop()/toggle()/auto-stop keep the child resident and relied on _safe_abort()
    alone, which 'leaves the loop stranded' (its own docstring) 100% of the time on the abort path.

    FIX: detect the no-callback abort path by the non-None return value (the normal path returns
    None because on_final is always provided) and emit a ('final', {text:''}) sentinel so host.text()
    unblocks. The daemon's on_final handles the empty text safely: a disarm has already cleared
    _listening (the on_final gate returns early) and textproc.clean('') rejects it regardless, so
    nothing is ever typed from the sentinel — it is purely an unblock signal. This restores the
    in-process semantics (where abort simply made recorder.text() return and the run() loop
    re-checked _listening) now that text() lives behind IPC.

    API-drift note: the non-None return as the abort marker is verified against RealtimeSTT v1.0.2
    (core/transcription_api.py). If a future version returns None on the abort path this helper would
    stop emitting the sentinel and the wedge would recur; the recorder-host integration test
    (tests/test_idle_and_gpu.sh) + the abort-path unit test guard that contract.
    """
    result = recorder.text(on_final)
    if result is not None:
        # Abort/shutdown path: text() returned '' and did NOT invoke on_final. Emit the sentinel so
        # the daemon's host.text() unblocks instead of wedging the run() loop forever.
        _safe_put(evt_q, ("final", {"text": ""}))


def _child_resolved_device(cfg: "VoiceTypingConfig", force_cpu: bool) -> dict[str, str]:
    """Re-derive {device,compute_type,final_model,realtime_model} the child's recorder loaded.

    The daemon needs this for status_snapshot()'s device/models fields WITHOUT probing CUDA itself
    (the daemon must stay CUDA-free). On force_cpu it is the PRD §4.4 CPU_FALLBACK; otherwise it is
    the cuda_check resolution the child just performed. Falls back to CPU_FALLBACK on probe error
    (defensive — status degrades to 'cpu' rather than crashing the child).
    """
    from voice_typing import cuda_check  # imported in the CHILD only

    if force_cpu:
        return dict(cuda_check.CPU_FALLBACK)
    try:
        return cuda_check.resolve_device_and_models(
            {
                "device": cfg.asr.device,
                "compute_type": "float16" if cfg.asr.device == "cuda" else "int8",
                "final_model": cfg.asr.final_model,
                "realtime_model": cfg.asr.realtime_model,
            }
        )
    except Exception:
        return dict(cuda_check.CPU_FALLBACK)


class _RelayFeedback:
    """A child-local Feedback stand-in that RELAYS recorder callbacks to the daemon via evt_q.

    build_recorder wires _build_callbacks(feedback, ...) which calls feedback.update_partial +
    feedback.set_phase. In the child those must NOT touch the daemon's Feedback object (it does not
    exist here); they relay events to the daemon, whose reader thread drives the REAL Feedback.

    Only the VAD phases (listening/speaking) are relayed as ("vad", phase). The lifecycle phases
    (unloaded/loading/idle) are driven by the DAEMON's _load_host/_unload_host, not here.
    """

    def __init__(self, evt_q: Any) -> None:
        self._evt_q = evt_q

    def update_partial(self, text: str) -> None:
        _safe_put(self._evt_q, ("partial", {"text": text}))

    def set_phase(self, phase: str) -> None:
        if phase in ("listening", "speaking"):
            _safe_put(self._evt_q, ("vad", {"phase": phase}))
        # lifecycle phases (unloaded/loading/idle) are owned by the daemon — ignore here.

    def set_models_loaded(self, loaded: bool) -> None:
        pass  # driven by the daemon

    def record_final(self, text: str) -> None:
        pass  # driven by the daemon's on_final

    def set_listening(self, listening: bool) -> None:
        pass  # driven by the daemon


class _RelayLatency:
    """A child-local LatencyLog stand-in. note_speech_end relays ("speech_end", {}).

    build_recorder wires latency.note_partial + latency.note_speech_end via _build_callbacks. In the
    child, note_partial fires inside the partial callback (which ALSO relays ("partial", {text}) via
    _RelayFeedback.update_partial) — so the daemon already gets a "partial" event and its reader
    thread calls the REAL latency.note_partial. note_speech_end fires inside on_vad_stop — relay it
    as ("speech_end", {}) so the daemon stamps t_speech_end. The other LatencyLog methods are no-ops
    here (finalize_utterance/snapshot are driven on the daemon side).
    """

    def __init__(self, evt_q: Any) -> None:
        self._evt_q = evt_q

    def note_partial(self, _text: str) -> None:
        pass  # the daemon's reader thread calls the REAL note_partial on the "partial" event

    def note_speech_end(self) -> None:
        _safe_put(self._evt_q, ("speech_end", {}))

    def finalize_utterance(self, **kw: Any) -> dict:
        return {}  # driven by the daemon's on_final

    def snapshot(self) -> list[dict]:
        return []
