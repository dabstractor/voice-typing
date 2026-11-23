"""ImeProcess: subprocess supervisor for the IM-v2 transport (P1.M4.T1.S2).

CONSUMES (S1 contract, read-only): voice_typing.ime.protocol (encode/decode,
ProtocolError) and `python -m voice_typing.ime.ime_host [event-log]` — a JSONL
request/reply host on stdin/stdout where every request `id` gets exactly ONE
id-echoing reply, id-less {"ev":...} event lines interleave arbitrarily, and an
`unavailable` event (one-IM-per-seat) precedes a clean exit(0).

CONSUMED BY (downstream seams, nothing wired here):
  - P1.M4.T2/T3 build the DeliveryTarget adapter over request()
    ('acquire'|'show'|'verify'|'leave') + the on_event feed.
  - P1.M4.T4 subscribes takeover detection via on_event.
  - P1.M6.T2.S1 constructs ImeProcess(on_delivery_state=feedback.set_delivery_state,
    ...), spawn() at bulk arm, stop() at quit, healthy() at arm-time re-check.

Pattern lineage: voice_typing/recorder_host.py's hard-won invariants, re-encoded
for a pipes/JSONL child instead of mp queues — child in its OWN process group
(Popen start_new_session=True == the child-side os.setsid there), SINGLE-FLIGHT
bounded stop (SIGTERM -> wait(5s) -> killpg SIGKILL; recorder_host's
_STOP_JOIN_TIMEOUT_S / _stop_lock / _terminate_group), readiness ping instead of
the 'ready' event, and liveness SURFACED, never self-healed (no respawn loop
anywhere: the caller's next spawn() IS the restart; a respawn fight against the
user's fcitx5 is explicitly forbidden — R.5 / one-IM-per-seat item).

State machine (failure states are terminal until the next spawn()):
    idle -> spawn() -> starting -> (ping echo) running
        running -> { unsupported (unavailable event) | fault (crash/spawn-timeout)
                   | idle (stop()) }
    spawn() while running -> True (idempotent); while unsupported/fault -> the
    sanctioned next-arm respawn (implicit stop of any leftover, fresh Popen).

Reader thread = the SOLE stdout consumer (Critical #4): id-echoing replies
resolve pending request()s via per-id Events; {"ev":...} lines forward to
on_event (T4 feed); `unavailable` latches unsupported (emitted ONCE, never
respawned). EOF has THREE flavors (Critical #5, distinguished by the EVENT +
latches, never by the exit code):
  - deliberate stop() latched  -> silent (the caller owns the transition);
  - after `unavailable`        -> silent (unsupported already emitted);
  - otherwise                  -> fault: "ime subprocess exited (rc=N)".
All pending requests fail (None) at EOF or on a broken stdin pipe; callbacks
(on_event/on_delivery_state) run ON the reader thread and are exception-guarded
so a bad callback can never kill the reader.

Emissions policy (test-pinned): on_delivery_state fires ONLY for `unsupported`
and `fault` — never `active`/`inactive` (T2/M6 own those; per
feedback.set_delivery_state's "written ONLY by the bulk-delivery wiring"
docstring). stop() itself emits NOTHING.

FENCES: transport-only supervisor — no acquire/show/verify semantics (T2/T3),
no takeover policy (T4), no daemon/Feedback import (the callback seam is the
wiring point), no config/pyproject/systemd changes. Purity: stdlib +
voice_typing.ime.protocol ONLY; importing this module spawns nothing and needs
no WAYLAND_DISPLAY.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading

from . import protocol

logger = logging.getLogger(__name__)

_DEFAULT_SPAWN_TIMEOUT_S: float = 10.0  # wayland connect+bind is fast; 10 s is generous
_DEFAULT_STOP_TIMEOUT_S: float = 5.0  # mirrors recorder_host._STOP_JOIN_TIMEOUT_S
_REQUEST_TIMEOUT_S: float = 1.0

_UNAVAILABLE_REASON = "seat input-method unavailable: another input method holds the seat"


class _Pending:
    """One in-flight request: a per-id Event + its reply slot (resolved by the reader)."""

    __slots__ = ("evt", "reply")

    def __init__(self):
        self.evt = threading.Event()
        self.reply: dict | None = None


class ImeProcess:
    """Supervises one `python -m voice_typing.ime.ime_host` child (spawn/monitor/teardown).

    Constructor injection keeps tests pure: on_delivery_state(state, reason) is the
    M6 feedback seam (unsupported/fault ONLY), on_event(ev_dict) is the T4 takeover
    feed, and _popen is the ONLY private injection seam (fake-proc tests), mirroring
    S1's sock= pattern.
    """

    def __init__(
        self,
        on_delivery_state=None,
        on_event=None,
        python_exe: str | None = None,
        log_path: str | None = None,
        spawn_timeout: float = _DEFAULT_SPAWN_TIMEOUT_S,
        stop_timeout: float = _DEFAULT_STOP_TIMEOUT_S,
        _popen=None,
    ):
        self._on_delivery_state = on_delivery_state
        self._on_event = on_event
        self._python_exe = python_exe or sys.executable  # the daemon venv by default
        self._log_path = log_path
        self._spawn_timeout = float(spawn_timeout)
        self._stop_timeout = float(stop_timeout)
        self._popen = _popen or subprocess.Popen

        self._state = "idle"
        self._state_lock = threading.Lock()  # guards _state/_unavailable/_dead/_epoch
        self._send_lock = threading.Lock()  # id allocation + stdin write (Critical #7)
        self._pending_lock = threading.Lock()
        self._pending: dict[int, _Pending] = {}
        # SINGLE-FLIGHT stop() (bugfix Issue 1's lesson via recorder_host): the quit
        # path may reach stop() from the signal thread AND main() finally. Plain Lock
        # (never re-entered); the 2nd caller sees idle and no-ops.
        self._stop_lock = threading.Lock()
        self._proc = None
        self._reader: threading.Thread | None = None
        self._deliberate_stop = False  # latched BEFORE terminating -> EOF stays silent
        self._unavailable = False  # latched by the event -> unsupported emitted ONCE
        self._dead = False  # child known-gone (reader EOF / broken pipe)
        self._epoch = 0  # generation counter: a stale reader can never touch new state
        self._next_id = 0

    # --- public surface (T2/T3/T4/M6 call these) ---

    @property
    def state(self) -> str:
        """idle | starting | running | unsupported | fault."""
        return self._state

    @property
    def is_alive(self) -> bool:
        """RUNNING and the child is not known-dead."""
        with self._state_lock:
            if self._state != "running" or self._dead:
                return False
        proc = self._proc
        return proc is not None and proc.poll() is None

    def spawn(self, timeout: float | None = None) -> bool:
        """Start the child + require ONE id-echoing ping reply within `timeout`.

        True iff the host reached RUNNING. Readiness timeout or child death ->
        bounded teardown -> FAULT (emitted once) -> False. A child `unavailable`
        during starting (fcitx5 holds the seat) -> False with state UNSUPPORTED
        (the reader already emitted the ONE reason). Idempotent while RUNNING;
        UNSUPPORTED/FAULT spawn is the sanctioned next-arm respawn (implicit
        stop of any leftover, fresh Popen) — never two children.
        """
        t = self._spawn_timeout if timeout is None else float(timeout)
        with self._state_lock:
            st = self._state
        if st == "running":
            return True
        if st == "starting":
            return False
        if st in ("unsupported", "fault"):
            self.stop()  # implicit bounded cleanup of any leftover (usually already dead)

        argv = [self._python_exe, "-m", "voice_typing.ime.ime_host"]
        if self._log_path:
            argv.append(str(self._log_path))
        proc = self._popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # child stderr -> journald
            start_new_session=True,  # own session/pgroup so killpg reaches grandchildren
        )
        with self._state_lock:
            self._epoch += 1
            epoch = self._epoch
            self._pending = {}
            self._deliberate_stop = False
            self._unavailable = False
            self._dead = False
            self._next_id = 0
            self._proc = proc
            self._state = "starting"
        # Reader starts BEFORE the ping wait so early events (unavailable!) drain.
        self._reader = threading.Thread(
            target=self._read_loop, args=(proc, epoch), daemon=True,
            name=f"ime-manager-reader-{epoch}",
        )
        self._reader.start()

        if self._send_and_wait("ping", timeout=t) is not None:
            self._set_state("running")
            return True

        # Readiness failed. Distinguish timeout-from-alive-child vs death BEFORE the
        # teardown runs — terminate() would make poll() unconditionally non-None.
        timed_out = not self._dead and proc.poll() is None
        self._teardown(proc, self._stop_timeout)
        self._join_reader()
        with self._state_lock:
            if self._deliberate_stop:
                return False  # stop() raced in; the caller owns the transition
            if self._unavailable:
                self._state = "unsupported"  # reason already emitted by the reader
                return False
            if self._state == "fault":
                return False  # crash EOF already emitted fault with the rc
            self._state = "fault"
        reason = (
            f"ime subprocess not ready in {t}s"
            if timed_out
            else f"ime subprocess exited (rc={proc.poll()}) before ready"
        )
        self._fire(self._on_delivery_state, "fault", reason)
        return False

    def request(self, cmd: str, timeout: float = _REQUEST_TIMEOUT_S, **fields) -> dict | None:
        """One JSONL request -> the id-echoing reply dict, or None.

        None on timeout or a dead child — NEVER a resend (R.5: never retry an
        operation that may already have landed). Returns None unless RUNNING.
        """
        with self._state_lock:
            ok = self._state == "running" and not self._dead
        if not ok or self._proc is None:
            return None
        return self._send_and_wait(cmd, timeout, **fields)

    def healthy(self) -> bool:
        """RUNNING + one short ping round-trip (the arm-time re-check seam)."""
        with self._state_lock:
            if self._state != "running" or self._dead:
                return False
        return self._send_and_wait("ping", timeout=_REQUEST_TIMEOUT_S) is not None

    def stop(self, timeout: float | None = None) -> None:
        """Bounded single-flight teardown: terminate -> wait -> killpg SIGKILL.

        The guard + deliberate-stop latch + clearing run under _stop_lock so a
        second concurrent caller (signal thread vs main-thread finally) sees
        idle and no-ops — exactly ONE teardown ever runs. Emits NO
        delivery_state transition. No-op when never spawned / already idle.
        """
        t = self._stop_timeout if timeout is None else float(timeout)
        with self._stop_lock:
            if self._proc is None and self._state == "idle":
                return
            self._deliberate_stop = True  # latched BEFORE terminating (silent EOF)
            proc, self._proc = self._proc, None
            self._state = "idle"
        if proc is None:
            return
        self._teardown(proc, t)
        self._join_reader()

    # --- internals ---

    def _send_and_wait(self, cmd: str, timeout: float, **fields) -> dict | None:
        """Correlating duplex write+wait. The reader resolves; the sender waits."""
        with self._send_lock:
            self._next_id += 1
            rid = self._next_id
            pend = _Pending()
            with self._pending_lock:
                self._pending[rid] = pend
            proc = self._proc
            if proc is None:
                with self._pending_lock:
                    self._pending.pop(rid, None)
                return None
            try:
                proc.stdin.write(protocol.encode({"id": rid, "cmd": cmd, **fields}))
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                # Dead child: mark dead, fail THIS request, never raise to the caller.
                logger.debug("ime manager: stdin write failed (child gone)")
                with self._pending_lock:
                    self._pending.pop(rid, None)
                self._mark_dead()
                return None
        replied = pend.evt.wait(timeout)
        with self._pending_lock:
            self._pending.pop(rid, None)  # a late reply must not resolve a stale slot
        return pend.reply if replied else None

    def _read_loop(self, proc, epoch: int) -> None:
        """The ONLY stdout consumer. Never lets a bad line/callback kill the loop."""
        try:
            for raw in proc.stdout:
                try:
                    obj = protocol.decode(raw)
                except protocol.ProtocolError as exc:
                    logger.warning("ime manager reader: undecodable line dropped (%s)", exc)
                    continue
                if not self._dispatch(obj, epoch):
                    return  # stale generation (superseded by a newer spawn) — retire
        except Exception:
            if epoch == self._epoch:  # stale-reader teardown noise is expected; stay quiet
                logger.exception("ime manager reader: unexpected error")
        finally:
            # The reader OWNS stdout: it alone closes it, AFTER its blocked read has
            # returned. Closing it from the teardown thread would deadlock on the
            # buffered reader's lock (close-vs-read race). stdin is closed under the
            # send lock so no writer is mid-write; the child sees stdin EOF too.
            try:
                proc.stdout.close()
            except Exception:
                pass
            self._close_stdin(proc)
            self._on_eof(proc, epoch)

    def _dispatch(self, obj: dict, epoch: int) -> bool:
        """Route one decoded line: reply (id echo) | event ({"ev":...}). False if stale."""
        with self._state_lock:
            if epoch != self._epoch:
                return False
        if "id" in obj and "ev" not in obj:  # reply: resolves the pending request
            with self._pending_lock:
                pend = self._pending.pop(obj["id"], None)
            if pend is None:
                logger.debug("ime manager reader: reply for unknown/stale id ignored")
            else:
                pend.reply = obj
                pend.evt.set()
            return True
        name = obj.get("ev")
        if name is None:
            logger.debug("ime manager reader: non-protocol line ignored: %r", obj)
            return True
        self._fire(self._on_event, obj)  # forward ALL events (T4 feed), incl. unavailable
        if name == "unavailable":  # one-IM-per-seat: latch ONCE, emit ONCE, NO respawn
            with self._state_lock:
                if self._unavailable or self._state not in ("starting", "running"):
                    return True
                self._unavailable = True
                self._state = "unsupported"
            self._fire(self._on_delivery_state, "unsupported", _UNAVAILABLE_REASON)
        return True

    def _on_eof(self, proc, epoch: int) -> None:
        """EOF: fail pending requests, then the THREE flavors (Critical #5)."""
        if epoch != self._epoch:
            return  # stale reader from a superseded spawn — never touch current state
        self._fail_pending()
        with self._state_lock:
            self._dead = True
            if self._deliberate_stop:
                return  # caller-owned transition (stop already set idle); silent
            if self._unavailable:
                return  # unsupported already emitted; stays until the next arm
            st = self._state
        if st not in ("running", "starting"):
            return  # already fault (e.g. spawn-timeout path emitted) — no double-emit
        try:
            rc = proc.wait(timeout=0.5)
        except Exception:
            rc = proc.poll()
        self._set_state("fault")
        self._fire(self._on_delivery_state, "fault", f"ime subprocess exited (rc={rc})")

    def _mark_dead(self) -> None:
        """Broken stdin pipe: the child is gone; fail all pending requests now."""
        with self._state_lock:
            self._dead = True
        self._fail_pending()

    def _fail_pending(self) -> None:
        """EOF/death resolves every pending request with None (immediately)."""
        with self._pending_lock:
            pendings = list(self._pending.values())
            self._pending.clear()
        for pend in pendings:
            pend.evt.set()  # reply stays None -> waiter returns None

    def _teardown(self, proc, timeout: float) -> None:
        """THE bounded teardown (recorder_host law): terminate -> wait -> killpg."""
        if proc is None:
            return
        try:
            proc.terminate()  # SIGTERM (graceful: ime_host also sees stdin EOF)
        except Exception:
            logger.debug("ime manager: terminate failed (best-effort)", exc_info=True)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Wedged child: SIGKILL its PROCESS GROUP — start_new_session=True made
            # it its own group leader, so this reaches its own grandchildren too.
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (OSError, OverflowError):
                # Already gone / fake pid in tests (ProcessLookupError ⊂ OSError) —
                # the direct kill is both the fallback and the test seam.
                try:
                    proc.kill()
                except Exception:
                    logger.debug("ime manager: kill failed (best-effort)", exc_info=True)
            try:
                proc.wait(timeout=1.0)  # best-effort reap (Popen must not leak a zombie)
            except Exception:
                pass
        self._close_stdin(proc)  # stdout belongs to the reader thread (see _read_loop)

    def _close_stdin(self, proc) -> None:
        """Close the WRITE side only, under the send lock (no writer mid-write)."""
        if proc is None:
            return
        try:
            with self._send_lock:
                proc.stdin.close()
        except Exception:
            pass

    def _join_reader(self) -> None:
        th = self._reader
        if th is not None and th.is_alive():
            th.join(timeout=1.0)  # bounded; the daemon thread never blocks exit

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            self._state = state

    @staticmethod
    def _fire(cb, *args) -> None:
        """Run a callback; a bad callback must never kill the reader/caller."""
        if cb is None:
            return
        try:
            cb(*args)
        except Exception:
            logger.exception("ime manager: callback raised (ignored)")
