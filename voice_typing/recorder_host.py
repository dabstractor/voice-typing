"""voice_typing.recorder_host — owns the AudioToTextRecorder in a managed child subprocess.

(PRD §7.9 + §6 T6(d); P1.M3.T2.S2 re-plan.) The WHOLE point of this module is GPU-VRAM
reclamation on idle-unload. RealtimeSTT v1.0.2 loads the Whisper model IN-PROCESS (its realtime-
partial engine is driven by a threading.Thread in the constructor's process), so any
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
                              | ("prompt", {"text": ...})   # P1.M2.T5.S1 rolling context prompt
                              | ("prime", {"token", "generation", "text"})
                                            # P1.M1.T2.S2 CONFIRMED priming (§4.8.1 initial seed;
                                            #   ack'd — unlike fire-and-forget "prompt"),
                                            #   text=None requests a plain clear
  abort_event (daemon -> child): a multiprocessing.Event SET by the daemon to interrupt a child
      blocked in recorder.text() (the cmd_queue is NOT read while text() blocks). A separate child
      thread polls it and calls recorder.abort(). ("abort", {}) on cmd_queue is belt-and-suspenders.
  cancel_event (daemon -> child): a multiprocessing.Event SET by RecorderHost.cancel() (P1.M2.T7.S1,
      PRD §4.2quater Backspace-cancel). The SAME child thread polls it: a cancel unblocks text()
      exactly like abort_event, but ALSO discards the buffered/in-flight audio and emits the
      unblock sentinel MARKED ("cancelled": True) so the daemon drops the cancelled utterance.
      Plain abort() (stop/drain) semantics are UNCHANGED.
  event_queue (child -> daemon): ("ready", {device,compute_type,model,       # Rev 2: ONE model;
                                            context_prompt,                  #   context_prompt=True iff the
                                            partial_callback})               #   dynamic PromptedExecutor is armed
                                                                             #   (P1.M2.T5.S1; additive keys — daemon
                                                                             #   consumption is P1.M2.T5.S2). partial_callback
                                                                             #   = the ONE upstream partial callback key the
                                                                             #   child installed (R.8 provenance, P1.M2.T1.S1)
                                 | ("error", {msg}) |
                                 ("final", {text, utterance_id, session_gen}) |
                                          # R.5 identity: the id SETTLES (closes) the utterance
                                          #   boundary at _dispatch; or {text:"", cancelled:True,
                                          #   utterance_id, session_gen} (the CANCEL sentinel,
                                          #   T7.S1 — the mark PLUS identity)
                                 ("partial", {text, utterance_id, session_gen}) |
                                                           # realtime stabilized partial
                                 ("speech", {}) |          # on_speech -> _touch_speech (idle auto-stop reset)
                                 ("vad", {phase}) |        # "listening"|"speaking" (on_vad_detect_start/_start)
                                 ("speech_end", {}) |      # on_vad_stop -> latency.note_speech_end
                                 ("prime_ack", {"token", "generation", "state", "tokens",
                                                "lanes"}) | # P1.M1.T2.S2: the CONFIRMED-priming ack
                                                            #   — OPAQUE outcome only, never text.
                                                            #   state = applied|clear|unconfirmed;
                                                            #   tokens = opaque count; lanes = the
                                                            #   confirmed lane count. The reader only
                                                            #   stores a (token, generation)-matching
                                                            #   ack + sets _prime_evt; the CALLER waits
                                                            #   (host.prime_prompt → sanitized
                                                            #   PrimeResult; S3 gates capture on it).
                                 ("gone", {})              # child acked shutdown (clean exit)

CONFIRMED PRIMING vs ROLLING PROMPT (P1.M1.T2.S2): ("prompt", ...) stays fire-and-forget — the
  executor swallows its own failures, so it can never COUNT as confirmation. ("prime", ...) is the
  acknowledged channel: the child installs the §4.8.1 initial seed via install_initial_prompt
  (S1's tri-state primitive) and ACKs with an opaque outcome. The daemon fences stale/late acks by
  (request token, host generation) — a late ack after a timeout, or an OLD child's ack after a
  respawn, is dropped and never satisfies a live waiter. The WAITER lives in the caller's thread
  (never the reader — that would strand text(); never under the daemon lock — that would wedge
  every control client). PRIVACY: the ack, the logs, and PrimeResult carry counts/reason codes
  ONLY — the seed text never crosses back and never reaches a log line.

IDENTITY (P1.M6.T1.S1 — PRD §4.2sexies R.5): every final/partial payload carries the ADDITIVE keys
  utterance_id + session_gen (the 'cancelled' precedent — never renamed/removed). Payloads WITHOUT
  them dispatch byte-identically (the legacy path — old doubles/tests, pre-upgrade children). The
  CHILD assigns identity at the decode source (_RelayIds): the utterance id rotates ONLY at
  on_speech (the new-utterance boundary), so a LATE event keeps the id of the utterance it belonged
  to — never relabeled as newer; session_gen bumps at every 'arm' command; sentinel finals settle
  the CURRENT id (no rotation). The DAEMON enforces the discard rules at the single choke point
  (_dispatch): (1) a partial whose id is already settled (post-final straggler) is dropped; (2) a
  duplicate final (id settled) is dropped BUT still sets _final_evt (host.text() must unblock —
  VT-007); (3) an event with an OLDER session_gen than the latest seen is dropped, while a newer
  gen advances the session and clears settled ids. The id settles BEFORE the on_final relay, so a
  dropped or filtered final (textproc.clean rejection, cancel suppression, a raising callback)
  still closes its utterance boundary. Consumers read host.relay_identity — the (session_gen,
  utterance_id) of the event being relayed, valid INSIDE the on_final/on_partial callbacks (they
  run on the reader thread) — the P1.M6.T2.S1 seam. Tracker state is reader-thread-only; settled
  ids are bounded (last 16) and cleared on session advance.

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

import collections
import itertools
import logging
import multiprocessing as mp
import os
import signal
import sys
import threading
import time  # VT-008: _abort_handler's defer branch sleeps — the missing import killed the
# thread with NameError on EVERY deferred cancel/abort, wedging all later stops into drain
# timeouts and latching the cancel-suppression window (the mass-rewind regressions of Oct 2026)
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, NamedTuple

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

# The confirmed-priming ("prime" → "prime_ack", P1.M1.T2.S2) wait budget. The child ACKs in ms
# when armed (the arm path primes while DISARMED, so cmd_q drains immediately); a cold/broken
# executor answers UNCONFIRMED fast; a dead child wakes the waiter via the reader-finally Event.
# The bound exists so a wedged/late child can never hang the arm — the daemon (S3) runs this
# inside its own larger start deadline. Tests shrink it via the prime_prompt(timeout=) kwarg.
_PRIME_TIMEOUT_S: float = 5.0


@dataclass(frozen=True)
class PrimeResult:
    """Sanitized outcome of one confirmed priming request (P1.M1.T2.S2; PRD §4.8.1).

    The daemon (S3) gates capture on this: "applied"/"clear" ⇒ proceed (known state),
    "unconfirmed" ⇒ degrade to context-free capture + a private hint. NO seed text ever
    appears here (frozen + text-free ⇒ repr is safe for logs by construction).

    state:      "applied" (seed installed on every active lane) | "clear" (known-empty — 0
                lanes, proven by the child's ready/capability evidence) | "unconfirmed"
                (UNKNOWN: timeout / dead child / cancelled / executor failure — never
                "unavailable"; unknown ≠ unavailable).
    tokens:     opaque count of prompted tokens (None unless applied — counts only, no text).
    lanes:      confirmed lane count (0 = known-empty; 1 = the one executor confirmed for BOTH
                lanes — P1.M1.T1.S3's one-executor contract).
    generation: the host lifetime this result belongs to (fence half; bumped on every spawn).
    reason:     sanitized code — "ok" | "no-lane" | "timeout" | "dead" | "cancelled" | "stale"
                | "executor-error" ("partial" lane failures collapse to unconfirmed/
                executor-error child-side; never over-claimed).
    """

    state: str
    tokens: "int | None"
    lanes: int
    generation: int
    reason: str


class RecorderHost:
    """Owns the AudioToTextRecorder in a spawn child; IPC for arm/disarm/abort/text/shutdown.

    The daemon constructs this and calls spawn() on first arm (single-flight via the daemon's
    _load_host). set_microphone/abort/text proxy to the child via cmd_queue; partial/final/speech
    events arrive on event_queue and are dispatched by a reader thread to the daemon's callbacks.
    stop() terminates the child PROCESS GROUP (os.killpg) so ALL VRAM (including the realtime-model
    CUDA context) is released and the daemon tree drops off nvidia-smi.

    EXECUTOR CONTRACT (P1.M1.T1.S3): the child arms at most ONE context-prompt PromptedExecutor,
    injected as BOTH transcription_executor and realtime_transcription_executor; the retired
    Rev-4 experiment's second partial-decoding executor is gone — the output-mode selector
    that could have requested it is rejected at config load (P1.M1.T1.S1). `feed_input` is
    the offline feed_audio lab seam; `partial_source` is the R.8 partial-callback provenance key.

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
        feed_input: bool = False,
        partial_source: str = "stabilized",
    ) -> None:
        self._cfg = cfg
        self._feedback = feedback
        self._latency = latency
        self._on_final = on_final
        self._on_partial = on_partial
        self._on_speech = on_speech
        self._force_cpu = force_cpu
        # G5 feed seam (P1.M6.T4.S1; PRD §4.4 sanctions use_microphone=False + feed_audio).
        # Default False = the production path, byte-identical: no feed queue is created and
        # the child builds the recorder with the microphone (as always). When True (lab-only),
        # the child gets a DEDICATED feed queue + feeder thread instead: the command loop
        # BLOCKS inside recorder.text() while listening, so ('feed', ...) commands on cmd_q
        # could only be read BETWEEN utterances — pacing would die. feed_audio is safe to call
        # from any thread while text() blocks (tests/test_feed_audio.py pattern).
        self._feed_input = bool(feed_input)
        # R.8 partial-source selector (P1.M2.T1.S1; PRD §4.2sexies): the ONE upstream partial
        # callback the CHILD's build_recorder should register — "stabilized" (the default =
        # production byte-identical) or "plain". A picklable str carried in the spawn args on
        # purpose: multiprocessing spawn gives the child a fresh interpreter, so parent-side
        # module state (e.g. a monkeypatch of daemon._PARTIAL_CALLBACK_ATTR) never reaches it
        # (the feed_input lab-seam precedent — private keyword-only, NOT a config knob).
        self._partial_source = partial_source
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
        # G5 feed queue — see the _feed_input comment above (lab-only; None in production).
        self._feed_q: Any = ctx.Queue() if self._feed_input else None
        # Dedicated abort signal: the child's command loop BLOCKS in recorder.text() while listening,
        # so a ('abort', {}) command queued on cmd_q would NOT be read until text() returns. An mp.Event
        # is polled by a SEPARATE child thread that calls recorder.abort() the instant it is set — this
        # is how stop()/toggle(off) interrupt a blocked text() so the run loop can re-check _listening.
        # Spawn-context (same as the Process) so the child inherits it cleanly.
        self._abort_event: Any = ctx.Event()
        # Dedicated CANCEL signal (P1.M2.T7.S1, PRD §4.2quater Backspace-cancel): the SAME polled-
        # Event mechanism as _abort_event — the child's command loop BLOCKS in recorder.text(), so
        # a queued command would never be read. Setting it makes the child unblock text() AND
        # discard the buffered audio AND emit the sentinel MARKED ("cancelled": True) so the daemon
        # drops the cancelled utterance. Spawn-context (same as the Process) like _abort_event.
        self._cancel_event: Any = ctx.Event()
        self._proc: Any = None
        # Single-flight lock for stop(): serializes concurrent callers (SIGTERM signal thread +
        # main-thread finally both reach host.stop()) so exactly ONE join+killpg teardown runs; the
        # 2nd caller blocks on the lock, then sees _proc is None and no-ops. See stop() (bugfix
        # Issue 1 / P1.M1.T1.S1). Plain Lock (not RLock): stop() is never re-entered.
        self._stop_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        # P1.M2.T7.S1: set by the reader when the 'final' event it is relaying is the CANCELLED
        # sentinel ("cancelled": True); consumed (read-and-cleared) by the daemon's on_final
        # suppression via consume_cancel_mark(). Per-event: each 'final' overwrites it, so it
        # always mirrors the most recent final event. on_final runs ON the reader thread, so the
        # mark is always observed in the write-then-relay order (no lock needed).
        self._cancel_mark = False
        self._final_evt = threading.Event()
        self._ready_evt = threading.Event()
        # Confirmed prompt priming (P1.M1.T2.S2 / §4.8.1): the daemon mints a token per request
        # and waits OUTSIDE the reader thread; the reader only stores the MATCHING ack + sets
        # the Event (the _cancel_mark/_final_evt shape — a reader-side wait would strand text(),
        # a lock-held wait would wedge every control client). Fenced by (token, generation):
        # a late ack (after timeout/cancel) or an OLD child's ack (after a respawn) can never
        # satisfy a live waiter. The ack payload is whitelisted to 5 safe keys — NEVER text.
        self._prime_evt = threading.Event()
        self._prime_ack: "dict | None" = None   # last matching ("prime_ack", ...) payload
        self._prime_token: "int | None" = None  # outstanding request token (None = none)
        self._prime_counter = itertools.count(1)  # strictly increasing request tokens
        self._generation = 0                    # bumped on every spawn (host lifetime fence)
        self._device: dict[str, str] = {}
        # R.8 provenance (P1.M2.T1.S1): the upstream partial callback key the child installed,
        # from its 'ready' payload ("partial_callback"). "" until ready; a legacy child payload
        # without the key degrades to "" (the context_prompt precedent).
        self._partial_callback: str = ""
        self._error: str | None = None
        self._dead = False  # set when the child is known-gone (reader EOF / stop()); idempotent guards
        # R.5 relay identity (P1.M6.T1.S1). Reader-thread-ONLY state (G6): mutated solely inside
        # _dispatch on the reader thread; the daemon's on_final/_on_partial read relay_identity on
        # that same thread -> no locking beyond the child-side _RelayIds lock. _ids_settled is
        # bounded (G8): the last 16 settled ids, cleared on session advance.
        self._ids_latest_session: int = -1
        self._ids_settled = collections.deque(maxlen=16)
        self._ids_settled_set: set[int] = set()
        self._ids_open: int | None = None
        self._relay_identity = _RelayIdentity(None, None)

    # --- public surface (the daemon calls these) ---

    @property
    def device(self) -> dict[str, str]:
        """The resolved {device,compute_type,model} from the child's 'ready'."""
        return dict(self._device)

    @property
    def partial_callback(self) -> str:
        """The upstream partial callback key the child INSTALLED (from its 'ready' payload).

        R.8 provenance (P1.M2.T1.S1; PRD §4.2sexies): "" until the child reports ready. Build
        success ⟹ the key survived the daemon's signature filter (daemon._construct rejects a
        dropped selection), so the reported key IS the effective one.
        """
        return self._partial_callback

    @property
    def is_alive(self) -> bool:
        """Is the child process still running?"""
        return self._proc is not None and self._proc.is_alive() and not self._dead

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def relay_identity(self) -> _RelayIdentity:
        """Identity of the event being relayed RIGHT NOW — (session_gen, utterance_id).

        The P1.M6.T2.S1 seam: the daemon's on_final/_on_partial callbacks run ON the reader
        thread inside _dispatch, so reading this inside them is race-free (G6) and yields the
        identity of the event that triggered the callback. Both fields are None for id-less
        (legacy) payloads. Snapshot semantics — copy the fields if you need them later.
        """
        return self._relay_identity

    def spawn(self, timeout: float = _SPAWN_READY_TIMEOUT_S) -> bool:
        """Start the child + wait for its 'ready'/'error'. True iff the recorder loaded.

        Single-flight is enforced by the CALLER (_load_host under the daemon _lock) — spawn() itself
        assumes it is called once per RecorderHost instance. The reader thread is started BEFORE the
        ready wait so events the child emits during load are drained. The heavy model load happens
        IN THE CHILD; the daemon process stays CUDA-free.
        """
        ctx = mp.get_context("spawn")
        # cfg is a picklable dataclass; the queues are spawn-context mp.Queue (picklable across
        # spawn — they share the spawn context the Process uses); force_cpu is a bool and
        # partial_source a plain str — BOTH must be constructor DATA because the spawn child is
        # a fresh interpreter (parent-side module state never survives). The child target
        # _worker_main is a module-level fn (picklable).
        self._proc = ctx.Process(
            target=_worker_main,
            args=(
                self._cfg,
                self._cmd_q,
                self._evt_q,
                self._abort_event,
                self._cancel_event,
                self._force_cpu,
                self._feed_q,
                self._partial_source,
            ),
            name="voice-typing-recorder-host",
            daemon=True,
        )
        # P1.M1.T2.S2 fence half: a NEW child lifetime. Any ack still in flight from the
        # PREVIOUS child (the evt_q pipe may hold stragglers) carries the old generation and
        # can never satisfy a request stamped with this one; its stored state is dropped too.
        self._generation += 1
        self._prime_ack = None
        self._prime_evt.clear()
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

    def set_prompt(self, text: str) -> None:
        """Queue a rolling context-prompt update for the child (P1.M2.T5.S1; sender T6.S2).

        Fire-and-forget cmd_q put, mirroring set_microphone: never blocks, never raises
        (a dead/full queue is a no-op). The child's command loop dispatches ("prompt",
        ...) BETWEEN utterances (it blocks inside text() while one is in flight —
        exactly when the daemon sends this, at commit time) and safely ignores the
        command when its prompt executor is degraded (logged DEBUG child-side).
        """
        try:
            self._cmd_q.put(("prompt", {"text": text}))
        except (BrokenPipeError, OSError, EOFError):
            self._dead = True  # child gone; idempotent

    def prime_prompt(
        self, text: "str | None", *, timeout: float = _PRIME_TIMEOUT_S
    ) -> PrimeResult:
        """Confirmed prompt priming across IPC (P1.M1.T2.S2; PRD §4.8.1 initial seed).

        The CONFIRMED channel — distinct from set_prompt()'s fire-and-forget rolling updates,
        which "cannot count as confirmation" (its executor catches its own failures; the arch
        note is the mandate). Puts ("prime", {token, generation, text}) with a fresh token +
        the current generation, then WAITS IN THE CALLER'S THREAD on _prime_evt (bounded;
        NEVER the reader thread, NEVER under any lock — either would strand text() or wedge
        the control clients; the reader only stores the matching ack + sets the Event).

        Fencing: only the ack whose (token, generation) matches THIS request resolves it. A
        late ack (the caller already timed out) or an OLD child's ack (after a respawn) is
        dropped by _dispatch (DEBUG, counts only) — a stale/late ack can never satisfy a live
        waiter, and a duplicate ack resolves once (idempotent token check).

        NEVER raises across IPC. Returns a sanitized frozen PrimeResult (no text; counts
        only): unconfirmed on timeout ("timeout"), a dead child ("dead" — the reader-finally
        Event wakes this wait immediately), cancellation ("cancelled"), or an executor that
        reported unconfirmed / raised ("executor-error"); 0 lanes is a KNOWN "clear"
        ("no-lane") per the child's ready/capability evidence. P1.M1.T2.S3 gates capture on
        PrimeResult.state.
        """
        gen = self._generation
        tok = next(self._prime_counter)
        self._prime_ack = None
        self._prime_token = tok
        self._prime_evt.clear()
        try:
            self._cmd_q.put(("prime", {"token": tok, "generation": gen, "text": text}))
        except (BrokenPipeError, OSError, EOFError):
            self._dead = True  # child gone; idempotent (mirrors set_prompt's catch)
            self._prime_token = None
            return PrimeResult("unconfirmed", None, 0, gen, "dead")
        # Wait in THIS thread (the caller's) — bounded; the reader thread only stores + sets.
        resolved = self._prime_evt.wait(timeout=timeout)
        if tok != self._prime_token:
            # Superseded: cancel_prime() cleared the token (or a newer request took over).
            # Our (possibly late) ack is now fenced — _dispatch drops it against the new
            # outstanding token.
            return PrimeResult("unconfirmed", None, 0, gen, "cancelled")
        if not resolved:
            self._prime_token = None  # retire the token: any late ack is fenced from here
            return PrimeResult("unconfirmed", None, 0, gen, "dead" if self._dead else "timeout")
        ack = self._prime_ack or {}
        if self._dead and not ack:
            # The reader-finally path (child died before answering): wake without an ack.
            self._prime_token = None
            return PrimeResult("unconfirmed", None, 0, gen, "dead")
        self._prime_token = None  # resolved; idempotent vs a duplicate ack
        if tok != ack.get("token") or gen != ack.get("generation"):
            # Spurious wake with no usable ack (defensive; _dispatch only stores matching
            # acks, so this is a belt-and-suspenders re-check).
            return PrimeResult("unconfirmed", None, 0, gen, "stale")
        state = str(ack.get("state", "unconfirmed"))
        lanes = int(ack.get("lanes", 0) or 0)
        tokens = ack.get("tokens") if state == "applied" else None
        if state in ("applied", "clear"):
            reason = "no-lane" if (state == "clear" and lanes == 0) else "ok"
        else:
            reason = "executor-error"  # unknown ⇒ unconfirmed; never "unavailable"
        return PrimeResult(state, tokens, lanes, gen, reason)

    def cancel_prime(self) -> None:
        """Fence the outstanding priming request (P1.M1.T2.S2): its (possibly late) ack can no
        longer resolve anything, and a blocked waiter wakes immediately with reason
        "cancelled". Idempotent; never raises. The NEXT prime_prompt mints a fresh token and
        works normally."""
        self._prime_token = None
        self._prime_evt.set()  # wake a blocked waiter → it sees the token cleared → "cancelled"

    def feed(self, pcm: Any, sr: int) -> None:
        """Queue one PCM slice for the child's feeder thread (G5 lab; feed_input=True only).

        Fire-and-forget put on the DEDICATED feed queue (NOT cmd_q — see ctor comment),
        mirroring set_prompt's never-blocks/never-raises discipline. With feed_input=False
        (production) there is no queue: the daemon never sends feed commands in production.
        """
        try:
            self._feed_q.put(("feed", {"pcm": pcm, "sr": int(sr)}))
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

    def cancel(self) -> None:
        """Cancel the in-flight utterance (PRD §4.2quater Backspace-cancel; P1.M2.T7.S1).

        Sets _cancel_event AND THEN _abort_event, in that order. BOTH are required: abort_event
        alone would unblock text() without discarding audio or marking the sentinel; cancel_event
        alone is only half the signal the child's poll loop acts on. The child's abort-handler
        thread processes the cancel: it sets its per-utterance `cancelled` marker, calls
        recorder.abort() (unblocking text()), the buffered/in-flight audio is DISCARDED
        (_clear_recorder_audio) and the unblock sentinel is emitted MARKED
        ("final", {text: "", "cancelled": True}) — the daemon's suppression flag drops it, so
        nothing is typed and no late final from the discarded utterance can land, while the mic
        stays hot. Idempotent (setting an already-set event is a no-op). Best-effort (never
        raises across IPC). abort()'s plain drain-watchdog semantics are UNCHANGED.
        """
        try:
            self._cancel_event.set()
        except (OSError, EOFError):
            self._dead = True
            return
        self.abort()

    def consume_cancel_mark(self) -> bool:
        """True iff the most recent 'final' event was the CANCELLED sentinel; clears the flag.

        The reader thread sets the mark from the event payload just before relaying that final to
        the daemon's on_final; the daemon's on_final suppression (P1.M2.T7.S1) consumes it to know
        the cancelled sentinel arrived and the suppression window can close. Per-event semantics:
        a plain final overwrites the mark to False.
        """
        marked = self._cancel_mark
        self._cancel_mark = False
        return marked

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
            self._prime_evt.set()  # P1.M1.T2.S2: a blocked prime_prompt wakes at once (reason "dead")

    def _ids_settle(self, uid: int) -> None:
        """Record uid as SETTLED (its final has been seen) — closes the utterance boundary (R.5).

        Bounded (G8): keep at most the last 16 per session. The deque + its membership set are
        kept as exact mirrors (explicit popleft + discard rather than relying on maxlen eviction,
        which would leave the set drifting).
        """
        if uid in self._ids_settled_set:
            return
        maxlen = self._ids_settled.maxlen
        if maxlen is not None and len(self._ids_settled) >= maxlen:
            self._ids_settled_set.discard(self._ids_settled[0])
            self._ids_settled.popleft()
        self._ids_settled.append(uid)
        self._ids_settled_set.add(uid)

    def _dispatch(self, kind: str, payload: dict) -> None:
        """Dispatch one event to the daemon callbacks. Mirrors _build_callbacks (in-process today)."""
        if kind == "ready":
            self._device = dict(payload)
            # R.8 provenance (P1.M2.T1.S1): expose the installed partial-callback key on the
            # host (partial_callback property). ADDITIVE key — legacy children without it
            # degrade to "" (the context_prompt precedent). The device dict deliberately keeps
            # the whole payload (the context_prompt key already flows to the daemon's cache).
            self._partial_callback = str(payload.get("partial_callback", ""))
            self._ready_evt.set()
        elif kind == "error":
            self._error = str(payload.get("msg", "unknown error"))
            self._ready_evt.set()
        elif kind == "final":
            text = str(payload.get("text", ""))
            # R.5 identity (P1.M6.T1.S1): the discard rules + the settle, at the single choke
            # point. Order is load-bearing: identity handling runs BEFORE the _cancel_mark line
            # (G5) and settles BEFORE the on_final relay (G4 — a dropped/filtered final still
            # closes its boundary regardless of what on_final does downstream: clean() rejection,
            # cancel suppression, a raising callback). A discarded duplicate sets _final_evt
            # (G3/VT-007: host.text() must unblock) and returns WITHOUT touching _cancel_mark
            # (a duplicate must not disturb an already-consumed mark). No id -> legacy path.
            uid = payload.get("utterance_id")
            gen = payload.get("session_gen")
            if uid is not None:
                if isinstance(gen, int) and gen < self._ids_latest_session:
                    self._final_evt.set()
                    logger.debug(
                        "recorder host reader: late cross-session final dropped "
                        "(uid=%s gen=%s latest=%s)", uid, gen, self._ids_latest_session,
                    )
                    return
                if uid in self._ids_settled_set:
                    self._final_evt.set()
                    logger.debug("recorder host reader: duplicate final dropped (uid=%s)", uid)
                    return
                if isinstance(gen, int) and gen > self._ids_latest_session:
                    self._ids_latest_session = gen
                    self._ids_settled.clear()
                    self._ids_settled_set.clear()
                self._ids_settle(uid)
                self._ids_open = None
                self._relay_identity = _RelayIdentity(gen, uid)
            # P1.M2.T7.S1: record whether THIS final is the cancelled sentinel BEFORE relaying it —
            # the daemon's on_final suppression consumes the mark (consume_cancel_mark()) to close
            # the cancel window. A plain final resets the mark to False (per-event semantics).
            self._cancel_mark = bool(payload.get("cancelled"))
            # on_final runs HERE (the reader thread), matching the in-process worker-thread model.
            # The daemon's on_final stamps t_final_ready, calls finalize_utterance, types, logs.
            try:
                self._on_final(text)
            except Exception:
                logger.exception("recorder host reader: on_final raised (ignored)")
            self._final_evt.set()
        elif kind == "partial":
            text = str(payload.get("text", ""))
            # R.5 identity: drop the pathological stragglers BEFORE they reach on_partial — a LATE
            # post-final partial (its id already settled) that would rewind the committed tail
            # (the stale-tail bug class), and an OLDER-session straggler. A NEWER gen advances
            # the session (settled ids cleared) and opens its id. No id -> legacy path (G7).
            uid = payload.get("utterance_id")
            gen = payload.get("session_gen")
            if uid is not None:
                if isinstance(gen, int) and gen < self._ids_latest_session:
                    logger.debug(
                        "recorder host reader: late cross-session partial dropped "
                        "(uid=%s gen=%s latest=%s)", uid, gen, self._ids_latest_session,
                    )
                    return
                if uid in self._ids_settled_set:
                    logger.debug(
                        "recorder host reader: late post-final partial dropped (uid=%s)", uid
                    )
                    return
                if isinstance(gen, int) and gen > self._ids_latest_session:
                    self._ids_latest_session = gen
                    self._ids_settled.clear()
                    self._ids_settled_set.clear()
                self._ids_open = uid
                self._relay_identity = _RelayIdentity(gen, uid)
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
        elif kind == "prime_ack":
            # P1.M1.T2.S2: reader-side ONLY stores + wakes (the _cancel_mark/_final_evt shape).
            # NEVER waits here — the caller's own thread waits on _prime_evt; a reader-side
            # wait would strand text() and every other drained event. Fence: accept ONLY the
            # ack matching the outstanding (token, generation); stale/late acks (a timed-out
            # request, a cancelled request, or an OLD child after a respawn) are dropped with
            # a counts-only DEBUG line. The stored dict is WHITELISTED to the 5 safe keys —
            # the ack protocol never carries the seed text (CRITICAL privacy rule).
            tok = payload.get("token")
            gen = payload.get("generation")
            if tok is not None and tok == self._prime_token and gen == self._generation:
                self._prime_ack = {
                    k: payload.get(k)
                    for k in ("token", "generation", "state", "tokens", "lanes")
                }
                self._prime_evt.set()
            else:
                logger.debug(
                    "recorder host reader: stale prime ack dropped (token=%s gen=%s)",
                    tok,
                    gen,
                )
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
    cancel_event: Any,
    force_cpu: bool,
    feed_q: Any = None,
    partial_source: str = "stabilized",
) -> None:
    """Child-process entry point: construct the recorder + serve commands until shutdown.

    os.setsid() makes the child its own session/group leader so the daemon's killpg teardown
    reaches the child's OWN spawn-grandchildren (transcript_process/reader_process). The recorder
    is built via the UNCHANGED production path (daemon.build_recorder) — now in the child, so the
    daemon process stays CUDA-free. On construction failure, the child retries ONCE with
    force_cpu=True (CPU fallback, PRD §4.4 — only the child touches CUDA, so the retry is clean
    here) then signals 'error' + exits. `partial_source` (PRD §4.2sexies R.8, default
    "stabilized") rides the spawn args as picklable data and is passed to EVERY build_recorder
    call — the normal build AND the force_cpu retry — so BOTH construction paths register the
    SAME single upstream partial callback ("no two callbacks delivering to one consumer").

    CONTEXT PROMPT (P1.M2.T5.S1): when cfg.asr.context_prompt is true, the child first arms a
    prompt_engine.PromptedExecutor — CAPABILITY PROBE = construct + warmup transcription of 1 s
    of zeros; on ANY failure it logs ONE INFO degrade line and the build proceeds with STOCK
    kwargs (context-free decoding — the SAME path as config-off, PRD §8 never-crash). On success
    the SAME executor object is injected as BOTH transcription_executor and
    realtime_transcription_executor (ONE faster-whisper model total; RealtimeSTT skips its
    TranscriptionWorker process). ONE executor is armed (P1.M1.T1.S3) — there is no
    realtime-lane split. The 'ready'
    payload reports the context-prompt outcome as context_prompt: true|false. The executors
    are constructed HERE in the child (CUDA objects are unpicklable and must never exist in
    the daemon process).

    Command loop: ("text", {}) -> recorder.text(child_on_final) (BLOCKS until a final, which puts
    a "final" event then returns); ("arm"/"disarm", {}) -> set_microphone; ("abort", {}) ->
    recorder.abort(); ("prompt", {"text"}) -> set_prompt via _prompt_targets (the one armed executor)
    (read only BETWEEN utterances — the loop blocks inside text(); commit-time delivery is BY
    DESIGN, no watcher thread); ("shutdown", {}) -> recorder.shutdown() (best-effort; the daemon SIGKILLs the
    group anyway), put "gone", exit. cancel_event (P1.M2.T7.S1) is polled by the SAME abort-handler
    thread: a cancel unblocks text() like an abort but DISCARDS the audio and MARKS the sentinel.
    """
    # Own session/group so killpg(child) reaches our grandchildren. Must be the first syscall so
    # any RealtimeSTT-spawned mp.Process inherits our pgid.
    try:
        os.setsid()
    except OSError as exc:
        # setsid can fail if we are already a process group leader (rare under spawn). Non-fatal:
        # killpg(getpgid(pid)) still targets our group; the grandchildren just inherit our pgid.
        logger.debug("child: os.setsid() failed (non-fatal): %s", exc)

    # Child logging (P1.M2.T5.S1): a spawn child never runs main()/_setup_logging, so without a
    # handler only WARNING+ reaches stderr (logging.lastResort) and the child's INFO lines — the
    # context-prompt probe result — would be INVISIBLE in journald (the PRP's Level-3 grep would
    # find nothing). basicConfig is IDEMPOTENT: a no-op when a root handler already exists
    # (pytest/caplog), so tests are unaffected. Mirrors the daemon's stderr format; the level
    # comes from the same cfg.log.level (defensively clamped — LogConfig.level is a free str).
    _child_level = str(getattr(getattr(cfg, "log", None), "level", "INFO") or "INFO").upper()
    if _child_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        _child_level = "INFO"
    logging.basicConfig(
        stream=sys.stderr,
        level=_child_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Lazy import: ONLY the child imports daemon.build_recorder (which lazy-imports RealtimeSTT).
    # This keeps the daemon process CUDA-free (the daemon imports only the RecorderHost handle).
    # _PARTIAL_SOURCES resolves the partial_source selector to the ONE upstream callback key
    # registered on the recorder (also reported in the 'ready' payload as partial_callback).
    from voice_typing.daemon import _PARTIAL_SOURCES, build_recorder
    # P1.M2.T5.S1 context-prompt wiring: augment_kwargs_with_executor (module-level, below) lazily
    # imports prompt_engine HERE IN THE CHILD. The prompt_engine MODULE is stdlib-only (CUDA-free)
    # at import, but the executor OBJECTS own faster-whisper/CUDA contexts: they are unpicklable
    # across the spawn boundary and must never exist in the daemon process.

    # The child's recorder callbacks RELAY events to the daemon over evt_q (they cannot touch the
    # daemon's Feedback/LatencyLog — those objects live in the daemon process). build_recorder wires
    # _build_callbacks(feedback, latency, on_speech); we pass relay stand-ins whose methods put
    # events on evt_q. See the module docstring's CALLBACK RELAY block for the exact mapping.
    # R.5 identity (P1.M6.T1.S1): the child assigns utterance/session identity at the decode
    # source; every final/partial payload carries it via _with_identity (additive keys).
    ids: _RelayIds = _RelayIds()
    relay_fb: Any = _RelayFeedback(evt_q, ids)
    relay_lat: Any = _RelayLatency(evt_q)

    def _child_on_speech() -> None:
        # G2: rotate the utterance id HERE — the decode source's new-utterance boundary, BEFORE
        # the speech put. A late realtime partial landing after final-N keeps id N (never
        # relabeled as newer) so the daemon's settled-id rule drops it. Sentinels do NOT rotate.
        # The speech payload itself stays UNSTAMPED (contract: only the six final/partial sites
        # carry identity keys).
        ids.rotate_utterance()
        _safe_put(evt_q, ("speech", {}))

    def _extra_kwargs_for_build(force: bool) -> "tuple[dict[str, Any] | None, Any]":
        """Probe + arm the context-prompt executor for ONE build attempt (P1.M2.T5.S1).

        Returns (extra_kwargs, prompt_executor). extra_kwargs is None on the stock path (config
        off OR probe failure — the SAME path) or carries transcription_executor +
        realtime_transcription_executor -> the PromptedExecutor on success. Runs IN THE CHILD.
        """
        if not cfg.asr.context_prompt:
            return None, None
        resolved = _child_resolved_device(cfg, force)
        extra: dict[str, Any] = {}
        executor = augment_kwargs_with_executor(extra, cfg, resolved, logger)  # module-level, below
        return (extra if executor is not None else None), executor

    def _build_kwargs(extra: "dict[str, Any] | None") -> "dict[str, Any] | None":
        """Merge the G5 feed override into one build's extra kwargs (feed_q is not None only
        under feed_input=True — PRD §4.4 sanctions use_microphone=False + feed_audio, the
        tests/test_feed_audio.py:276 pattern). Production (feed_q None) is untouched."""
        if feed_q is None:
            return extra
        merged: dict[str, Any] = dict(extra) if extra else {}
        merged["use_microphone"] = False
        return merged

    # Construct the recorder via the UNCHANGED production path. CPU fallback: retry once with
    # force_cpu=True if the cuda construction fails (mirrors the daemon's old in-process retry,
    # now in the child where the CUDA context lives — cleaner because only the child touches CUDA).
    recorder = None
    prompt_executor: Any = None
    try:
        try:
            extra_kwargs, prompt_executor = _extra_kwargs_for_build(force_cpu)
            recorder = build_recorder(
                cfg,
                relay_fb,
                relay_lat,
                on_speech=_child_on_speech,
                extra_kwargs=_build_kwargs(extra_kwargs),
                partial_source=partial_source,
            )
        except Exception as exc:
            if force_cpu:
                _safe_put(evt_q, ("error", {"msg": f"force_cpu build failed: {exc!r}"}))
                return
            logger.warning(
                "child: CUDA recorder construction failed (%s); retrying with force_cpu=True", exc
            )
            try:
                # FRESH probe for the CPU attempt: a CUDA-armed executor is wrong for a CPU
                # recorder; a CPU probe failure degrades exactly like the first attempt did.
                extra_kwargs, prompt_executor = _extra_kwargs_for_build(True)
                recorder = build_recorder(
                    cfg,
                    relay_fb,
                    relay_lat,
                    force_cpu=True,
                    on_speech=_child_on_speech,
                    extra_kwargs=_build_kwargs(extra_kwargs),
                    partial_source=partial_source,
                )
            except Exception as exc2:
                _safe_put(
                    evt_q,
                    ("error", {"msg": f"CUDA build failed: {exc!r}; CPU fallback also failed: {exc2!r}"}),
                )
                return
        # Report the resolved device so the daemon can seed _resolved_device_cache WITHOUT probing
        # CUDA itself (the daemon must stay CUDA-free). _child_resolved_device derives the 3-key
        # {device,compute_type,model} from the cuda_check resolution the child just performed.
        # P1.M2.T5.S1: + the additive context_prompt flag (True iff the executor is armed).
        resolved_device = _child_resolved_device(cfg, force_cpu)
        _safe_put(
            evt_q,
            (
                "ready",
                _ready_payload(
                    resolved_device,
                    prompt_executor is not None,
                    _PARTIAL_SOURCES[partial_source],
                ),
            ),
        )
    except Exception as exc:
        _safe_put(evt_q, ("error", {"msg": f"unexpected construction error: {exc!r}"}))
        return

    # Command loop. recorder.text() BLOCKS until a final -> child_on_final puts a "final" event.
    # A SEPARATE abort-handler thread watches abort_event so stop()/toggle(off) can interrupt a
    # blocked text() (the main loop cannot read cmd_q while blocked in text()).
    def _child_on_final(text: str) -> None:
        _safe_put(evt_q, ("final", _with_identity({"text": text}, ids)))

    stop_abort_thread = threading.Event()
    # VT-007: a flag the abort handler sets when it processes an abort, so _run_text_and_emit_final
    # can emit the unblock sentinel keyed on OUR abort signal (robust against a future RealtimeSTT
    # that returns None on the abort path) instead of relying on recorder.text()'s version-specific
    # non-None return value. Cleared at the top of each 'text' command below.
    aborted = threading.Event()
    # P1.M2.T7.S1 (Backspace-cancel): a sibling per-utterance marker set when the abort was a
    # CANCEL (RecorderHost.cancel()), not a plain stop/drain abort. _run_text_and_emit_final keys
    # the audio discard + the MARKED sentinel on it; cleared at the top of each 'text' command.
    cancelled = threading.Event()
    # LOST-SIGNAL FIX (Backspace stuck-suppression bug): held for the WHOLE recorder.text()
    # call inside _run_text_and_emit_final, so the abort handler's try-acquire below can tell
    # "text() is blocked inside (safe to recorder.abort())" from "between text() cycles
    # (defer: leave the events set for the next 'text' command's stale-signal check)".
    # recorder.abort() waits on was_interrupted — an event ONLY text() sets — so aborting
    # with text() not running would wedge the handler thread forever (and every later
    # abort/cancel with it: stops/drains would degrade to their timeouts).
    text_running = threading.Lock()

    def _abort_handler() -> None:
        """Watch cancel_event/abort_event; call recorder.abort() to unblock a sleeping text().

        cancel_event is checked FIRST (P1.M2.T7.S1): a cancel unblocks text() exactly like a plain
        abort, but ALSO sets `cancelled` so the sentinel is emitted MARKED and the buffered audio
        is discarded. RecorderHost.cancel() sets BOTH events — the cancel branch consumes
        abort_event too, so the plain-abort branch below does not run recorder.abort() twice.

        LOST-SIGNAL FIX: recorder.abort() runs ONLY while text() is in flight (the text_running
        try-acquire). When it is NOT, the events are LEFT SET — never consumed here — and the
        next 'text' command's stale-signal check consumes them and emits the sentinel directly,
        so the daemon's cancel-suppression window still closes and a stop's abort still
        unblocks text(). Consuming them here instead (the old behavior) silently discarded the
        signal: no marked sentinel was ever emitted and every later final was dropped daemon-side.
        """
        while not stop_abort_thread.is_set():
            if cancel_event.wait(timeout=0.2):
                if text_running.acquire(blocking=False):
                    text_running.release()  # text() not in flight: the next 'text' command's
                    time.sleep(0.05)  # stale-signal check owns these events — leave them set
                    continue
                cancel_event.clear()
                abort_event.clear()  # cancel() set both; consume both (ONE recorder.abort())
                aborted.set()        # VT-007: the sentinel must fire (same as a plain abort) ...
                cancelled.set()      # ... but MARKED, with the buffered audio discarded
                _bounded_recorder_abort(recorder)
                continue
            if abort_event.wait(timeout=0.2):
                if text_running.acquire(blocking=False):
                    text_running.release()  # same deferral as the cancel branch above
                    time.sleep(0.05)
                    continue
                abort_event.clear()
                aborted.set()  # VT-007: mark so _run_text_and_emit_final emits the sentinel
                _bounded_recorder_abort(recorder)

    def _abort_supervisor() -> None:
        """Restart _abort_handler if it EVER dies (belt & braces: a dead handler wedges every
        later abort/cancel into their timeouts — stops stop working, cancels latch windows)."""
        while not stop_abort_thread.is_set():
            try:
                _abort_handler()
            except Exception:  # pylint: disable=broad-except — the supervisor must survive
                logger.warning("vt-child-abort handler died; restarting", exc_info=True)
                time.sleep(0.5)

    abort_thread = threading.Thread(
        target=_abort_supervisor, name="vt-child-abort", daemon=True
    )
    abort_thread.start()

    if feed_q is not None:
        # G5 feeder thread: drain the dedicated feed queue and call feed_audio DIRECTLY.
        # The command loop below BLOCKS inside recorder.text() while listening, so feed
        # commands can never ride cmd_q (they would only be read between utterances).
        # feed_audio is non-blocking + re-slices to 32 ms internally (test_feed_audio.py);
        # the PACER's wall-clock pacing, never this queue, controls timing. Daemon thread:
        # dies with the process (the bounded killpg teardown owns shutdown).
        def _feed_loop() -> None:
            warned = False
            while True:
                try:
                    _kind, payload = feed_q.get()
                except (EOFError, OSError):
                    return
                if recorder is None:
                    if not warned:
                        logger.warning("child: feed command with no recorder (ignored)")
                        warned = True
                    continue
                try:
                    recorder.feed_audio(
                        payload["pcm"], original_sample_rate=int(payload["sr"])
                    )
                except Exception:  # noqa: BLE001 — one bad slice must not kill the feeder
                    logger.exception("child: feed_audio raised (ignored)")

        threading.Thread(target=_feed_loop, name="vt-child-feed", daemon=True).start()

    running = True
    try:
        while running:
            try:
                kind, payload = cmd_q.get()
            except (EOFError, OSError):
                break  # daemon gone -> exit
            try:
                if kind == "text":
                    # LOST-SIGNAL FIX (Backspace stuck-suppression bug): a cancel/abort that
                    # landed while we were BETWEEN text() cycles was silently discarded by
                    # these fresh-marker clears (and RealtimeSTT's text() entry clears
                    # interrupt_stop_event too) — the marked sentinel was never emitted, the
                    # daemon's cancel-suppression window never closed, and every later final
                    # was dropped (no commit, no reset_boundary: the streaming tail
                    # accumulated across utterances, so everything dictated after the
                    # Backspace kept rewinding to the edit point). Consume a stale signal
                    # HERE and emit its sentinel DIRECTLY — one ('final', ...) event per
                    # text command, the same invariant _run_text_and_emit_final guarantees —
                    # and do NOT enter recorder.text(); the daemon run loop re-sends 'text'.
                    stale = _drain_stale_abort_signals(cancel_event, abort_event)
                    abort_event.clear()  # fresh per-utterance markers (the original intent)
                    aborted.clear()  # VT-007: fresh per-utterance abort marker
                    cancelled.clear()  # P1.M2.T7.S1: fresh per-utterance cancel marker
                    if stale == "cancel":
                        _clear_recorder_audio(recorder)
                        _safe_put(
                            evt_q,
                            ("final", _with_identity({"text": "", "cancelled": True}, ids)),
                        )
                        continue
                    if stale == "abort":
                        _safe_put(evt_q, ("final", _with_identity({"text": ""}, ids)))
                        continue
                    # blocks until a final (or an abort). _run_text_and_emit_final GUARANTEES a
                    # ('final', ...) event on BOTH paths (real final via on_final, OR abort via the
                    # sentinel) so the daemon's host.text() always unblocks — without it an abort
                    # (stop/toggle-off/auto-stop) leaves host.text() blocked forever (the child is
                    # still alive), wedging the run() loop so no further utterance transcribes.
                    _run_text_and_emit_final(
                        recorder, evt_q, _child_on_final, aborted, cancelled, text_running, ids=ids
                    )
                elif kind == "arm":
                    # R.5: new session generation at EVERY arm (before _handle_arm; its signature
                    # is untouched). Events decoded after this carry the new gen, so the daemon
                    # drops pre-re-arm stragglers by generation.
                    ids.new_session()
                    _handle_arm(recorder, cancel_event, abort_event)
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
                elif kind == "prompt":
                    # P1.M2.T5.S1: rolling context-prompt update. DELIVERY TIMING (by design, NO
                    # watcher thread): this loop BLOCKS inside recorder.text() while an utterance
                    # is in flight, so prompt commands are only read BETWEEN utterances — exactly
                    # when the daemon sends them (commit time; the sender is P1.M2.T5.S2).
                    text = payload.get("text") if isinstance(payload, dict) else None
                    targets = _prompt_targets(prompt_executor)
                    if targets:
                        for _exec in targets:
                            _exec.set_prompt(str(text) if text is not None else None)
                    else:
                        logger.debug("child: prompt command ignored (context-prompt not armed)")
                elif kind == "prime":
                    # P1.M1.T2.S2: CONFIRMED priming (vs the fire-and-forget "prompt" above).
                    # Same between-utterances delivery timing (the loop blocks in text(); the
                    # daemon primes while DISARMED so the command drains immediately). The ACK
                    # carries opaque state/token-count/lane-count only — NEVER the seed text.
                    _handle_prime(
                        payload if isinstance(payload, dict) else {}, prompt_executor, evt_q
                    )
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


class _RelayIdentity(NamedTuple):
    """Identity of the event currently being relayed (R.5) — host.relay_identity's value.

    The daemon's on_final/_on_partial callbacks run ON the reader thread inside _dispatch, so
    reading this inside those callbacks yields the (session_gen, utterance_id) of the event that
    triggered them — the P1.M6.T2.S1 consumption seam. Either field is None when the payload was
    id-less (the legacy path).
    """

    session_gen: "int | None"
    utterance_id: "int | None"


class _RelayIds:
    """Child-side utterance/session identity stamper (PRD §4.2sexies R.5).

    utterance_id: rotated ONLY at on_speech (the decode source's new-utterance boundary) so a
    LATE event keeps the settled id of the utterance it belonged to (never relabeled as newer —
    R.5; see _child_on_speech). session_gen: bumped at every 'arm' command (new session
    generation per arm — R.5). stamp() captures both under the lock at callback entry (the
    realtime thread races the cmd loop). Sentinels stamp the CURRENT id — they settle, they
    never rotate.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._utterance = 0
        self._session = 0

    def rotate_utterance(self) -> int:
        with self._lock:
            self._utterance += 1
            return self._utterance

    def new_session(self) -> int:
        with self._lock:
            self._session += 1
            return self._session

    def stamp(self, payload: dict) -> dict:
        with self._lock:
            payload["utterance_id"] = self._utterance
            payload["session_gen"] = self._session
        return payload


def _with_identity(payload: dict, ids: "_RelayIds | None") -> dict:
    """ONE payload helper for the six final/partial event sites — adds utterance_id + session_gen
    (ADDITIVE keys; the 'cancelled' sentinel key and ready's 'context_prompt' are the precedents).
    ids=None stamps nothing (the legacy/test call sites — payloads byte-identical to today).
    """
    return ids.stamp(payload) if ids is not None else payload


def _prompt_targets(prompt_executor: Any) -> list[Any]:
    """The executors a ("prompt", ...) command must update, in order.

    ONE EXECUTOR CONTRACT (P1.M1.T1.S3 / PRD §4.2quater): at most the shared context-prompt
    executor — the same object in BOTH the transcription and realtime kwargs. The Rev-4
    split's second lane is retired (the output-mode selector that armed it is rejected at
    config load, P1.M1.T1.S1), so this is always a 0- or 1-element list; the confirmed-prompt ACK
    (P1.M1.T2.S2) extends THIS seam. set_prompt itself never raises (prompt_engine contract).
    """
    return [prompt_executor] if prompt_executor is not None else []


def _handle_prime(payload: dict, prompt_executor: Any, evt_q: Any) -> None:
    """Child-side handler for the ("prime", {token, generation, text}) command (P1.M1.T2.S2).

    CONFIRMED priming (PRD §4.8.1): installs the initial seed on every ACTIVE prompt lane via
    the executor's confirmed primitive (S1's install_initial_prompt — consumed BY ATTRIBUTE:
    .state.value / .tokens; PromptState is deliberately NOT imported — the daemon process must
    never pull prompt_engine's deps at module load), then emits ONE ("prime_ack", ...) with
    opaque state/token-count/lane-count ONLY — NEVER the seed text, NEVER str(exception) (an
    exception may embed its input; the TYPE name alone is logged).

    Semantics (the tri-state contract, fail to UNKNOWN):
      - 0 targets (context-prompt not armed — ALREADY PROVEN by the child's ready/capability
        payload) → state "clear", lanes 0: a KNOWN empty, not unconfirmed (unknown ≠
        unavailable).
      - An aliased lane pair (the same executor object in both kwargs, the P1.M1.T1.S3
        one-executor contract) installs ONCE and counts as ONE lane — dedup by identity.
      - All lanes applied → "applied" (tokens = the opaque count); all clear → "clear"; any
        unconfirmed/raise/mixed-lane outcome → "unconfirmed" (never over-claim; "partial"
        failures collapse here).
    Never raises: the install is wrapped; the ACK is sent on every path via _safe_put.
    """
    tok = payload.get("token")
    gen = payload.get("generation")
    text = payload.get("text")
    if not isinstance(text, str) and text is not None:
        text = None  # a non-string seed is unusable — treat as None (clear-request semantics)
    targets = list({id(t): t for t in _prompt_targets(prompt_executor)}.values())
    if not targets:
        # ready/capability already proved context-prompt is not armed → KNOWN empty (not
        # unconfirmed — unknown ≠ unavailable; the arch note's "clear is known" clause).
        _safe_put(
            evt_q,
            ("prime_ack", {"token": tok, "generation": gen, "state": "clear",
                           "tokens": None, "lanes": 0}),
        )
        return
    states: list[str] = []
    tokens: "int | None" = None
    failed = False
    for _exec in targets:
        try:
            res = _exec.install_initial_prompt(text)
            raw_state = getattr(res, "state", None)
            st = getattr(raw_state, "value", None) or (str(raw_state) if raw_state is not None else "")
            st_l = str(st).lower()
            if "applied" in st_l:
                st = "applied"
            elif "clear" in st_l:
                st = "clear"
            else:
                st = "unconfirmed"  # UNCONFIRMED / anything unknown — fail to UNKNOWN
            states.append(st)
            tokens = getattr(res, "tokens", None)
        except Exception as exc:  # CRITICAL privacy rule: TYPE name only — never str(exc)
            logger.warning(
                "child: priming install raised (%s) — unconfirmed", type(exc).__name__
            )
            states.append("unconfirmed")
            failed = True
    if failed or any(s == "unconfirmed" for s in states):
        state = "unconfirmed"
    elif all(s == "applied" for s in states):
        state = "applied"
    elif all(s == "clear" for s in states):
        state = "clear"
    else:
        state = "unconfirmed"  # mixed lanes → partial → UNKNOWN (never over-claim)
    _safe_put(
        evt_q,
        (
            "prime_ack",
            {
                "token": tok,
                "generation": gen,
                "state": state,
                "tokens": tokens if state == "applied" else None,
                "lanes": len(targets),
            },
        ),
    )


def _default_prompt_executor_factory(model: str, device: str, compute_type: str) -> Any:
    """Build the production PromptedExecutor (injectable seam for CUDA-free unit tests)."""
    from voice_typing.prompt_engine import PromptedExecutor  # child-only import

    return PromptedExecutor(model_name=model, device=device, compute_type=compute_type)


def augment_kwargs_with_executor(
    kwargs: dict[str, Any],
    cfg: "VoiceTypingConfig",
    resolved: dict[str, str],
    logger: logging.Logger,
    *,
    executor_factory: "Callable[[str, str, str], Any] | None" = None,
) -> Any | None:
    """Child-side: conditionally arm the context-prompt executor into recorder kwargs.

    P1.M2.T5.S1 (PRD §4.2quater rolling context prompt). When cfg.asr.context_prompt is true:
    construct ONE PromptedExecutor for cfg.asr.lite_model at the resolved device/compute_type,
    run the CAPABILITY PROBE (build + 1 s warmup transcription), and on success mutate `kwargs`
    in place with kwargs["transcription_executor"] = kwargs["realtime_transcription_executor"]
    = executor (the SAME object -> ONE model for partials AND finals; RealtimeSTT skips its
    TranscriptionWorker). On ANY probe failure — and when context_prompt is false, which takes
    the IDENTICAL stock path — kwargs are left untouched and None is returned (degrade to
    context-free decoding; PRD §8 never-crash).

    ONE EXECUTOR CONTRACT (P1.M1.T1.S3): there is no realtime-lane split. The Rev-4
    experiment's second partial-decoding executor is retired together with the output-mode
    selector that armed it, which the config layer rejects (P1.M1.T1.S1); `_prompt_targets` therefore
    always resolves to at most this one object — the surface P1.M1.T2.S2's prompt ACK builds on.

    Must run IN THE CHILD only: the executor owns faster-whisper/CUDA objects (unpicklable;
    daemon import purity). Module-level + factory-injectable so tests exercise it WITHOUT CUDA
    (tests/test_prompt_engine.py). Returns the armed executor, or None on the stock path.
    """
    if not getattr(cfg.asr, "context_prompt", False):
        return None  # config gate == degrade path: stock kwargs, no probe
    from voice_typing import prompt_engine  # child-only import (module scope is CUDA-free)

    factory = (
        executor_factory if executor_factory is not None else _default_prompt_executor_factory
    )
    try:
        executor = factory(cfg.asr.lite_model, resolved["device"], resolved["compute_type"])
        probe = prompt_engine.probe_prompt_executor(executor)
        if not probe.ok:
            raise RuntimeError(probe.error or "prompt-executor probe failed")
    except Exception as exc:  # noqa: BLE001 — deliberate broad degrade (probe contract)
        logger.info(
            "voice-typing context-prompt: probe failed (%s); degrading to context-free decoding",
            exc,
        )
        return None
    kwargs["transcription_executor"] = executor
    kwargs["realtime_transcription_executor"] = executor
    logger.info(
        "voice-typing context-prompt: dynamic executor armed "
        "(model=%s device=%s compute_type=%s)",
        cfg.asr.lite_model,
        resolved.get("device", "?"),
        resolved.get("compute_type", "?"),
    )
    return executor


def _ready_payload(
    resolved_device: dict[str, str],
    context_prompt_active: bool,
    partial_callback: str = "",
) -> dict[str, Any]:
    """The child's ('ready', ...) payload: resolved device/model + flags.

    'context_prompt' is True iff the dynamic PromptedExecutor was armed (probe passed); False
    on the config-off OR probe-failure degrade path (identical stock configuration). The key is
    ADDITIVE — existing readers ignore it; the daemon-side consumer is P1.M2.T5.S2.

    'partial_callback' (P1.M2.T1.S1; PRD §4.2sexies R.8) is the upstream partial callback key
    ACTUALLY installed on this child's recorder — the G5 provenance field. Build success ⟹ the
    key survived the daemon's signature filter (_construct rejects a dropped selection), so the
    requested key IS the installed key. ADDITIVE; empty when unknown.
    """
    payload = dict(resolved_device)
    payload["context_prompt"] = bool(context_prompt_active)
    payload["partial_callback"] = partial_callback
    return payload


def _handle_arm(recorder: Any, cancel_event: Any, abort_event: Any) -> None:
    """The child's 'arm' command: purge stale audio, drain raced abort signals, mic on.

    POST-ABORT RE-STASH PURGE (Rev 3 hardening): the 'disarm' clear runs BEFORE the stop's
    abort unblocks text(), so whatever the aborted decode re-stashes (recorder.frames /
    last_frames / audio) lands AFTER that clear — and survived until the next 'disarm',
    which never comes before the next 'arm'. The next text() then falls back to those
    buffers and transcribes the PREVIOUS session's last utterance into the new one (the
    "pringles can" word-vomit: stop right after speaking → re-arm → the cut-off sentence
    types itself, chars AND backspaces). Clearing HERE too makes every arm start provably
    fresh. Then: drain any cancel/abort that raced a disarm->arm toggle (LOST-SIGNAL FIX
    companion — a stale sentinel would freeze the session's first utterance), and only
    then un-mute the mic.
    """
    _clear_recorder_audio(recorder)
    _drain_stale_abort_signals(cancel_event, abort_event)
    recorder.set_microphone(True)


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
    # STALE-FINAL GUARD: the buffers above are only HALF of what an aborted utterance leaves
    # behind — its final-transcription credit/result is the other half. See the block below.
    _purge_final_transcription_results(recorder)


# -----------------------------------------------------------------------------
# STALE-FINAL RESULT PURGE — the "killed turn replaces the new turn" bug.
#
# RealtimeSTT's perform_final_transcription keeps a request CREDIT counter
# (recorder.transcribe_count): it submits the utterance's audio ONLY when the count is 0
# (an early-transcription request may already cover it) and decrements once per result it
# receives. Results travel over an UNTAGGED FIFO (the worker pipe, or the external-executor
# queue when context_prompt=true) — a result cannot be matched to the audio that produced it.
#
# A stop/cancel abort that lands while the final model is still decoding the utterance makes
# that function return "" on its next 0.1 s poll WITHOUT decrementing (transcription_api.py:
# the interrupt branch sits before the `-= 1`). The worker still finishes; its result parks in
# the FIFO. The child's aborted text() returns, the daemon disarms and re-arms on the next
# keypress, and the NEW session's first utterance reaches perform_final_transcription with
# count == 1: it SKIPS submitting its own audio and "receives" the KILLED session's last
# utterance instead. That stale text is relayed as the new utterance's final — the engine
# commits it (rewinds the freshly typed tail, types the old words) and the host settles that
# uid, so the new utterance's own partials/final are then dropped as post-final: "the new
# turn gets wiped out forever". The audio purge above never touched this half (it is not
# audio), and neither the cross-session gen filter nor the settled-uid filter can see it (the
# stale result is adopted by a legitimate text() of the NEW session, stamped with its ids).
#
# Fix, two halves that are both safe by construction:
#   1. _purge_final_transcription_results() — at EVERY audio-purge seam (disarm, arm, cancel:
#      all on the cmd-loop thread BETWEEN text() calls, so no final transcription is active):
#      zero the credit counter and discard whatever results have already arrived.
#   2. _discard_stale_final_results() — at the next text() entry: bounded-wait for any result
#      the purge found still IN FLIGHT and discard it before text() can adopt it. Waiting here
#      is free: the mic is already on, the recording worker captures audio independently of
#      the cmd loop (wait_audio() finds the queued recording afterwards), and realtime
#      partials keep flowing. The library's counter is never reset anywhere else (verified
#      against the installed source: init, += on submit, -= on receive, nothing on abort).
# -----------------------------------------------------------------------------

_STALE_FINAL_ATTR = "_vt_stale_final_results"  # per-recorder: results still to discard
_STALE_FINAL_DRAIN_TIMEOUT_S = 10.0  # bound on the in-flight wait at text() entry


def _receive_final_result(recorder: Any, timeout: float) -> Any:
    """One final-transcription result if one arrives within `timeout`, else None.

    Mirrors RealtimeSTT core/transcription.py receive_transcription_result() against the
    recorder's OWN attributes instead of importing it (the daemon process imports this module
    and must stay free of the ASR package; the child has it loaded already). Both result
    channels: the external-executor queue (context_prompt=true builds inject a
    transcription_executor) and the built-in worker pipe. Never raises."""
    try:
        if getattr(recorder, "_uses_external_transcription_executor", False):
            return recorder._external_transcription_results.get(timeout=timeout)
        pipe = getattr(recorder, "parent_transcription_pipe", None)
        if pipe is not None and pipe.poll(timeout):
            return pipe.recv()
    except Exception:  # queue.Empty; EOFError/OSError on a dead worker; attribute drift
        return None
    return None


def _purge_final_transcription_results(recorder: Any) -> int:
    """Audio-purge seam: zero the final-transcription credit counter, discard arrived results.

    Returns the number of results still IN FLIGHT (also recorded on the recorder for
    _discard_stale_final_results). Idempotent. A recorder without the counter (unit-test
    doubles, a future library rename) is a no-op. Never raises."""
    count = getattr(recorder, "transcribe_count", None)
    if not isinstance(count, int) or count <= 0:
        return 0
    lock = getattr(recorder, "transcription_lock", None)  # free by construction here
    acquired = False
    if lock is not None:
        try:
            acquired = bool(lock.acquire(blocking=False))
        except Exception:
            acquired = False
    try:
        recorder.transcribe_count = 0
        remaining = count
        # Only under the lock: perform_final_transcription receives on the same channel. A busy
        # lock is not expected here; its results are simply left for the text()-entry discard.
        while acquired and remaining > 0 and _receive_final_result(recorder, 0) is not None:
            remaining -= 1
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                pass
    if remaining:
        setattr(
            recorder,
            _STALE_FINAL_ATTR,
            int(getattr(recorder, _STALE_FINAL_ATTR, 0) or 0) + remaining,
        )
        logger.info(
            "child: %d aborted final-transcription result(s) still in flight; they will be "
            "discarded before the next text() (stale-final guard)",
            remaining,
        )
    return remaining


def _discard_stale_final_results(
    recorder: Any, timeout_s: float = _STALE_FINAL_DRAIN_TIMEOUT_S
) -> int:
    """text() entry: bounded-wait for and discard every result the last purge found in flight.

    Holds recorder.transcription_lock — the ONE lock perform_final_transcription takes — so
    the wait is serialized with any final transcription by construction (none is active at
    text() entry; the lock keeps that true even if a future caller changes). Returns the number
    still outstanding at timeout (0 = clean). Idempotent; never raises."""
    remaining = int(getattr(recorder, _STALE_FINAL_ATTR, 0) or 0)
    if remaining <= 0:
        return 0
    lock = getattr(recorder, "transcription_lock", None)
    acquired = False
    if lock is not None:
        try:
            acquired = bool(lock.acquire(timeout=min(timeout_s, 1.0)))
        except Exception:
            acquired = False
    deadline = time.monotonic() + timeout_s
    try:
        while remaining > 0:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            if _receive_final_result(recorder, min(0.1, left)) is not None:
                remaining -= 1
    finally:
        setattr(recorder, _STALE_FINAL_ATTR, remaining)
        if acquired:
            try:
                lock.release()
            except Exception:
                pass
    if remaining:
        logger.warning(
            "child: %d stale final-transcription result(s) never arrived within %.1fs; giving "
            "up the wait (a late one would be adopted by the next final)",
            remaining,
            timeout_s,
        )
    else:
        logger.debug("child: stale final-transcription result(s) discarded before text()")
    return remaining


def _drain_stale_abort_signals(cancel_event: Any, abort_event: Any) -> str | None:
    """Consume a cancel/abort signal that landed BETWEEN text() cycles. PURE event plumbing.

    LOST-SIGNAL FIX (Backspace stuck-suppression bug): the child's command loop sits at
    cmd_q.get() between utterance cycles. A cancel/abort arriving there used to be wiped by
    the 'text' command's fresh-marker clears without ever being observed, so the daemon's
    cancel-suppression window never closed. This drains the events instead, cancel FIRST
    (RecorderHost.cancel() sets both; cancel takes precedence so its sentinel is MARKED).

    Returns "cancel", "abort", or None (no stale signal). ALWAYS clears both events so the
    caller enters its next text() cycle with the fresh-marker slate the clears intend. PURE:
    no recorder calls, no queue puts — the caller decides what to emit.
    """
    stale = "cancel" if cancel_event.is_set() else ("abort" if abort_event.is_set() else None)
    cancel_event.clear()
    abort_event.clear()
    return stale


def _bounded_recorder_abort(recorder: Any, timeout_s: float = 2.0) -> None:
    """recorder.abort() that can never wedge the caller (the child's abort-handler thread).

    abort_recording() waits on was_interrupted — an event ONLY recorder.text() sets — so an
    abort with text() not in flight and recorder state != "inactive" blocks FOREVER. The
    handler calls this only after the text_running try-acquire says text() IS in flight, but
    the check-then-abort window is microscopic, not zero: if text() returns in between, a bare
    abort would wedge the handler thread permanently (killing every later abort/cancel —
    stops and drains degrade to their timeouts). The join bound turns that residual into a
    WARNING + one abandoned daemon thread (it holds no locks); the handler loop stays alive.
    Never raises.
    """
    def _call() -> None:
        try:
            recorder.abort()
        except Exception:
            logger.exception("child: recorder.abort() raised (best-effort; ignored)")

    t = threading.Thread(target=_call, name="vt-child-abort-call", daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        logger.warning(
            "child: recorder.abort() did not return within %.1fs (text() likely not in "
            "flight); the abort signal is left to the next text cycle's stale-signal check",
            timeout_s,
        )


def _run_text_and_emit_final(
    recorder: Any,
    evt_q: Any,
    on_final: "Callable[[str], None]",
    aborted: "threading.Event | None" = None,
    cancelled: "threading.Event | None" = None,
    text_running: "threading.Lock | None" = None,
    ids: "_RelayIds | None" = None,
) -> None:
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

    FIX: emit a ('final', {text:''}) sentinel on the abort path so host.text() unblocks. The daemon's
    on_final handles the empty text safely: a disarm has already cleared _listening (the on_final
    gate returns early) and textproc.clean('') rejects it regardless, so nothing is ever typed from
    the sentinel — it is purely an unblock signal. This restores the in-process semantics (where
    abort simply made recorder.text() return and the run() loop re-checked _listening) now that
    text() lives behind IPC.

    VT-007 (API-drift robustness): the abort path is detected via TWO independent signals (belt and
    suspenders) so the unblock guarantee NO LONGER depends on a RealtimeSTT-version-specific return
    value:
      (1) `aborted` — a threading.Event the child's _abort_handler sets around recorder.abort()
          (the abort signal WE control). This is the primary, version-independent signal. A future
          RealtimeSTT that returns None on the abort path still trips it.
      (2) the legacy non-None return marker (text() returns '' on abort in v1.0.2). Retained as a
          backstop for callers that do not pass `aborted` (the existing unit tests, which mimic the
          v1.0.2 return semantics exactly).
    Either signal fires the sentinel. The recorder-host integration test (tests/test_idle_and_gpu.sh)
    + the abort-path unit tests (incl. a fake text() returning None on abort) guard this contract.

    text_running (LOST-SIGNAL FIX): when given, held for the WHOLE recorder.text() call so the
    child's abort handler can tell "text() in flight (safe to recorder.abort())" from "between
    cycles (defer: leave the events for the next 'text' command's stale-signal check)". Default
    None keeps the existing unit-test call sites (4-arg) unchanged.

    ids (P1.M6.T1.S1): when given, BOTH emitted sentinels carry utterance_id/session_gen via
    _with_identity, stamped with the CURRENT id at emission (sentinels settle the current
    utterance — they never rotate it, R.5). Default None keeps the payloads id-less (the legacy
    path — the existing test doubles stay green untouched).
    STALE-FINAL GUARD: before text() is entered, _discard_stale_final_results() consumes any
    final-transcription result an aborted utterance left in flight (see the purge block above) —
    the one place it may wait safely. No-op without a pending stale result.
    """
    _discard_stale_final_results(recorder)
    if text_running is not None:
        text_running.acquire()
    try:
        result = recorder.text(on_final)
    finally:
        if text_running is not None:
            text_running.release()
    if (aborted is not None and aborted.is_set()) or result is not None:
        # Abort/shutdown path: emit the ('final', {text:''}) sentinel so the daemon's host.text()
        # unblocks instead of wedging the run() loop forever. See the VT-007 note above for why we
        # key on the `aborted` flag (our signal) OR the legacy non-None return (v1.0.2 contract).
        if cancelled is not None and cancelled.is_set():
            # P1.M2.T7.S1 cancel path: DISCARD the buffered/in-flight audio so NO late final from
            # the cancelled utterance can land (the same all-defensive helper the disarm path
            # uses — it never raises), and emit the sentinel MARKED. The daemon's suppression
            # flag drops it: nothing typed, nothing recorded, mic stays hot. The sentinel is
            # still EMITTED (never skipped) or host.text() would wedge forever (the VT-007
            # regression) — cancel changes its PAYLOAD, never its existence.
            _clear_recorder_audio(recorder)
            _safe_put(evt_q, ("final", _with_identity({"text": "", "cancelled": True}, ids)))
        else:
            _safe_put(evt_q, ("final", _with_identity({"text": ""}, ids)))


def _child_resolved_device(cfg: "VoiceTypingConfig", force_cpu: bool) -> dict[str, str]:
    """Re-derive {device,compute_type,model} — the ONE recorder the child actually loaded.

    The daemon needs this for status_snapshot()'s device/model fields WITHOUT probing CUDA itself
    (the daemon must stay CUDA-free). On force_cpu it is the PRD §4.4 CPU_FALLBACK; otherwise it is
    the cuda_check resolution the child just performed (which itself overrides wholesale with
    CPU_FALLBACK — device cpu, compute_type int8, the CPU substitute model tiny.en — when no CUDA
    is visible). Falls back to CPU_FALLBACK on probe error (defensive — status degrades to 'cpu'
    rather than crashing the child).
    """
    from voice_typing import cuda_check  # imported in the CHILD only

    if force_cpu:
        return dict(cuda_check.CPU_FALLBACK)
    try:
        return cuda_check.resolve_device_and_models(
            {
                "device": cfg.asr.device,
                "compute_type": cfg.asr.compute_type
                if cfg.asr.device == "cuda"
                else "int8",
                "model": cfg.asr.lite_model,
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

    def __init__(self, evt_q: Any, ids: "_RelayIds | None" = None) -> None:
        self._evt_q = evt_q
        # R.5 identity stamper (P1.M6.T1.S1). None -> id-less payloads (the legacy path the
        # existing unit tests exercise; the G7 backward-compat default).
        self._ids = ids

    def update_partial(self, text: str) -> None:
        _safe_put(self._evt_q, ("partial", _with_identity({"text": text}, self._ids)))

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
