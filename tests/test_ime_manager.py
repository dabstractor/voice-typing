"""ImeProcess supervisor tests (P1.M4.T1.S2) — fake-proc duplex over REAL os.pipe() streams.

No compositor, no real subprocess, no WAYLAND_DISPLAY, no daemon/Feedback import.
The only injection seam is ImeProcess's private ``_popen`` factory (mirrors S1's
sock= seam); everything else goes through real blocking pipes so the reader
thread is genuinely exercised.

Matrix (research §5): 1 import purity/constants · 2 spawn readiness + pinned
Popen args + id sequence · 3 spawn timeout -> FAULT + teardown + next-arm respawn
· 4 request id-correlation / timeout -> None / NO resend · 5 event forwarding +
bad-line resilience · 6 unavailable -> ONE unsupported, silent exit(0), no
respawn, dead route fails fast · 7 crash -> fault naming rc, pending requests
failed by EOF · 8 deliberate stop -> NO transition · 9 stop single-flight /
killpg fallback / idle no-op · 10 request after death -> None.  Plus the
persona flow: unavailable DURING starting maps spawn() -> unsupported.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import subprocess
import sys
import threading
import time

from voice_typing.ime import protocol
from voice_typing.ime import manager as mgr
from voice_typing.ime.manager import (
    ImeProcess,
    _DEFAULT_SPAWN_TIMEOUT_S,
    _DEFAULT_STOP_TIMEOUT_S,
    _REQUEST_TIMEOUT_S,
    _UNAVAILABLE_REASON,
)

FAKE_PID = 4_000_000_000  # far outside real pids: os.getpgid -> ProcessLookupError (killpg fallback seam)


def _wait_for(pred, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


class _CountingWriter:
    """proc.stdin double: records every write() while passing through to a real pipe."""

    def __init__(self, fh):
        self._fh = fh
        self._lk = threading.Lock()
        self.writes: list[bytes] = []

    def write(self, b):
        with self._lk:
            self.writes.append(bytes(b))
        return self._fh.write(b)

    def flush(self):
        return self._fh.flush()

    def close(self):
        return self._fh.close()


class _FakeProc:
    """Popen double with real pipe streams. pid is fake -> killpg falls back to kill()."""

    def __init__(self, wait_blocks: bool = False):
        self.pid = FAKE_PID
        self.returncode = None
        self._wait_blocks = wait_blocks
        self._lk = threading.Lock()
        self.calls: list[str] = []
        r_out, w_out = os.pipe()  # child stdout: test writes w_out, manager reads r_out
        r_in, w_in = os.pipe()  # child stdin:  manager writes w_in, test reads r_in
        self.stdout = os.fdopen(r_out, "rb")
        self.stdin = _CountingWriter(os.fdopen(w_in, "wb"))
        self.peer_w = w_out  # test-side: feed lines / close -> EOF
        self.peer_r = r_in  # test-side: drained by _ScriptedChild
        self.argv = None
        self.pkwargs = None

    # --- minimal Popen surface ---
    def poll(self):
        return self.returncode

    def terminate(self):
        with self._lk:
            self.calls.append("term")
            self.returncode = 0

    def kill(self):
        with self._lk:
            self.calls.append("kill")
            self.returncode = -9

    def wait(self, timeout=None):
        if self._wait_blocks:
            raise subprocess.TimeoutExpired(self.pid, timeout)
        return self.returncode

    # --- test-side plumbing ---
    def feed(self, obj):
        os.write(self.peer_w, protocol.encode(obj))

    def feed_raw(self, data: bytes):
        os.write(self.peer_w, data)

    def close_stdout(self):
        os.close(self.peer_w)

    def calls_snapshot(self):
        with self._lk:
            return list(self.calls)


class _ScriptedChild:
    """Drains manager-written request lines; answers per script {cmd: dict|callable|None}.

    dict  -> id-echoing reply with those fields; callable(obj) -> list of raw
    lines to feed (or [] for silence); None/absent -> silence (timeout path).
    """

    def __init__(self, script=None):
        self.script = dict(script or {})
        self.proc = None
        self.received: list[dict] = []
        self._lk = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def bind(self, proc):
        self.proc = proc
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self.proc is not None:
            try:
                os.close(self.proc.peer_r)
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(2.0)

    def _loop(self):
        fd = self.proc.peer_r
        try:
            while not self._stop.is_set():
                data = os.read(fd, 65536)
                if not data:
                    break
                for line in data.split(b"\n"):
                    if not line.strip():
                        continue
                    try:
                        obj = protocol.decode(line)
                    except protocol.ProtocolError:
                        continue
                    with self._lk:
                        self.received.append(obj)
                    self._respond(obj)
        except OSError:
            pass

    def _respond(self, obj):
        cmd = obj.get("cmd")
        with self._lk:
            val = self.script.get(cmd)
        if val is None:
            return
        if callable(val):
            for out in val(obj) or []:
                self.proc.feed(out)
        else:
            self.proc.feed(protocol.make_reply(obj["id"], cmd, **val))


class _Harness:
    """ImeProcess + fake popen + scripted child + recorded transitions/events."""

    def __init__(self, script=None, wait_blocks=False, **mgr_kw):
        self.transitions: list[tuple[str, str]] = []
        self.events: list[dict] = []
        self.procs: list[_FakeProc] = []
        self.child = _ScriptedChild(script)
        self._lk = threading.Lock()

        def popen(argv, **pkwargs):
            proc = _FakeProc(wait_blocks=wait_blocks)
            proc.argv = list(argv)
            proc.pkwargs = pkwargs
            self.procs.append(proc)
            self.child.bind(proc)
            return proc

        defaults = dict(
            on_delivery_state=lambda s, r: self._rec(self.transitions, (s, r)),
            on_event=lambda ev: self._rec(self.events, ev),
            spawn_timeout=2.0,
            stop_timeout=2.0,
            _popen=popen,
        )
        defaults.update(mgr_kw)
        self.m = ImeProcess(**defaults)

    def _rec(self, lst, item):
        with self._lk:
            lst.append(item)

    def snapshot(self, lst):
        with self._lk:
            return list(lst)


_PING = {"activated": False, "dones": 0}


@contextlib.contextmanager
def harness(script=None, spawn=False, **kw):
    sc = {"ping": dict(_PING)}
    if script:
        sc.update(script)
    h = _Harness(script=sc, **kw)
    try:
        if spawn:
            assert h.m.spawn() is True
            assert h.m.state == "running"
        yield h
    finally:
        h.child.stop()
        for p in h.procs:
            for fd in (p.peer_w,):
                try:
                    os.close(fd)
                except OSError:
                    pass
            for f in (p.stdout, getattr(p.stdin, "_fh", None)):
                try:
                    f.close()
                except OSError:
                    pass


# --- 1: import purity + constants + construct-spawns-nothing -----------------
def test_import_purity_and_constants():
    assert _DEFAULT_SPAWN_TIMEOUT_S == 10.0
    assert _DEFAULT_STOP_TIMEOUT_S == 5.0
    assert _REQUEST_TIMEOUT_S == 1.0
    # pure module: stdlib + voice_typing.ime.protocol ONLY (no feedback/daemon)
    assert "voice_typing.feedback" not in sys.modules
    assert "voice_typing.daemon" not in sys.modules
    src = inspect.getsource(mgr)
    assert "voice_typing.feedback" not in src
    assert "voice_typing.daemon" not in src
    with harness() as h:
        assert h.m.state == "idle" and h.m.is_alive is False
        assert h.procs == []  # construction spawns nothing
        h.m.stop()  # idle no-op must not raise


# --- 2: spawn readiness, pinned Popen args, id sequence, log_path ------------
def test_spawn_ready_pinned_popen_and_ids():
    with harness(script=_PING) as h:
        m = h.m
        assert m.spawn() is True
        assert m.state == "running" and m.is_alive is True
        p = h.procs[0]
        assert p.pkwargs["start_new_session"] is True
        assert p.pkwargs["stdin"] is subprocess.PIPE
        assert p.pkwargs["stdout"] is subprocess.PIPE
        assert p.argv[:3] == [sys.executable, "-m", "voice_typing.ime.ime_host"]
        # readiness ping was id 1; next request continues the sequence and echoes it
        with h._lk:
            got = list(h.child.received)
        assert got[0] == {"id": 1, "cmd": "ping"}
        reply = m.request("ping")
        assert reply is not None and reply["id"] == 2 and reply["reply"] == "ping"
        # NO resend: exactly two write() calls so far
        assert len(p.stdin.writes) == 2
    # log_path appends the argv slot (ime_host main() takes argv[1])
    with harness(script=_PING, log_path="/tmp/ime-test-events.jsonl") as h2:
        assert h2.m.spawn() is True
        assert h2.procs[0].argv == [sys.executable, "-m", "voice_typing.ime.ime_host",
                                    "/tmp/ime-test-events.jsonl"]


# --- 3: spawn timeout -> FAULT + teardown; next spawn IS the respawn ----------
def test_spawn_timeout_fault_teardown_and_next_arm():
    with harness(script={"ping": None}) as h:  # NO responder: silence = timeout path
        m = h.m
        assert m.spawn(timeout=0.3) is False
        assert m.state == "fault" and m.is_alive is False
        assert h.snapshot(h.transitions) == [("fault", "ime subprocess not ready in 0.3s")]
        assert "term" in h.procs[0].calls_snapshot()
        # late EOF (clean rc) after the fault must NOT double-emit
        h.procs[0].returncode = 0
        h.procs[0].close_stdout()
        m._reader.join(2.0)
        assert h.snapshot(h.transitions) == [("fault", "ime subprocess not ready in 0.3s")]
        # the NEXT spawn is the sanctioned respawn (Critical #6) — fresh child
        h.child.script["ping"] = {"activated": False, "dones": 0}
        assert m.spawn() is True
        assert len(h.procs) == 2 and m.state == "running"


# --- 4: request id-correlation, timeout -> None, NO bytes re-sent -------------
def test_request_correlation_timeout_no_resend():
    with harness(spawn=True) as h:
        m, p = h.m, h.procs[0]
        # wrong-id reply is ignored; the request still times out -> None
        h.child.script["verify"] = lambda obj: [protocol.make_reply(obj["id"] + 99, "verify",
                                                                   text_head="")]
        out = m.request("verify", timeout=0.3, session="s", utterance="u", seq=1,
                        expected_revision=0, text="t")
        assert out is None
        assert len(p.stdin.writes) == 2  # readiness ping + verify — NO resend
        time.sleep(0.1)  # let the late wrong-id reply land
        assert len(p.stdin.writes) == 2  # still no resend
        assert m.state == "running"
        # correct id correlation
        h.child.script["verify"] = {"text_head": "abc", "cursor": 3, "anchor": 0, "bytes": 3}
        out = m.request("verify", timeout=1.0, session="s", utterance="u", seq=2,
                        expected_revision=0, text="t")
        with h._lk:
            rid = h.child.received[-1]["id"]
        assert out is not None and out["id"] == rid and out["text_head"] == "abc"
        assert len(p.stdin.writes) == 3
        with m._pending_lock:
            assert not m._pending  # no slot leak


# --- 5: events forwarded; undecodable line never kills the reader -------------
def test_event_forwarding_and_bad_line_resilience():
    with harness(spawn=True) as h:
        h.procs[0].feed_raw(b"this is not json\n")
        h.procs[0].feed({"ev": "surrounding_text", "text": "hi", "t_ms": 1.0})
        assert _wait_for(lambda: any(
            e.get("ev") == "surrounding_text" for e in h.snapshot(h.events)))
        ev = [e for e in h.snapshot(h.events) if e.get("ev") == "surrounding_text"][0]
        assert ev["text"] == "hi"
        assert h.snapshot(h.transitions) == []  # events alone emit no delivery_state


# --- 6: unavailable -> ONE unsupported; silent exit(0); NO respawn ------------
def test_unavailable_unsupported_silent_exit_no_respawn():
    with harness(spawn=True) as h:
        m, p = h.m, h.procs[0]
        p.feed({"ev": "unavailable", "t_ms": 1.0})
        assert _wait_for(
            lambda: h.snapshot(h.transitions) == [("unsupported", _UNAVAILABLE_REASON)])
        assert m.state == "unsupported"
        assert p.calls_snapshot() == []  # no teardown/kill machinery ran
        n_writes = len(p.stdin.writes)
        # clean exit(0) after unavailable: silent (no fault)
        p.returncode = 0
        p.close_stdout()
        m._reader.join(2.0)
        assert h.snapshot(h.transitions) == [("unsupported", _UNAVAILABLE_REASON)]
        assert len(h.procs) == 1  # NO auto respawn
        assert m.request("ping") is None  # dead route fails fast, no write
        assert len(p.stdin.writes) == n_writes
        # the explicit next-arm spawn IS allowed (Critical #6)
        assert m.spawn() is True
        assert len(h.procs) == 2 and m.state == "running"


# --- 6b: the persona flow — unavailable DURING starting maps spawn->unsupported
def test_spawn_unavailable_during_starting_maps_unsupported():
    def respond_with_unavailable(obj):
        h.procs[0].feed({"ev": "unavailable", "t_ms": 0.0})
        return []

    with harness(script={"ping": respond_with_unavailable}) as h:
        assert h.m.spawn() is False  # arm fails ...
        assert h.m.state == "unsupported"  # ... as seat-unavailable, NOT fault
        assert h.snapshot(h.transitions) == [("unsupported", _UNAVAILABLE_REASON)]
        assert len(h.procs) == 1


# --- 7: crash -> fault naming rc; pending requests failed promptly ------------
def test_crash_fault_names_rc_and_fails_pending():
    with harness(spawn=True) as h:
        m, p = h.m, h.procs[0]
        slow = {}

        def slow_req():
            slow["t0"] = time.monotonic()
            slow["out"] = m.request("verify", timeout=5.0, session="s", utterance="u",
                                    seq=1, expected_revision=0, text="t")
            slow["dt"] = time.monotonic() - slow["t0"]

        th = threading.Thread(target=slow_req, daemon=True)
        th.start()
        assert _wait_for(lambda: len(p.stdin.writes) == 2)  # pending armed
        p.returncode = 1
        p.close_stdout()  # unexpected EOF, no unavailable
        th.join(2.0)
        assert slow["out"] is None and slow["dt"] < 4.0  # failed by EOF, not by timeout
        assert _wait_for(lambda: m.state == "fault")
        faults = [r for s, r in h.snapshot(h.transitions) if s == "fault"]
        assert len(faults) == 1 and "rc=1" in faults[0]
        # request after death -> None immediately, no write (case 10)
        n = len(p.stdin.writes)
        assert m.request("ping") is None and len(p.stdin.writes) == n


# --- 8: deliberate stop emits NOTHING (no spurious fault) ---------------------
def test_deliberate_stop_emits_nothing():
    with harness(spawn=True) as h:
        m, p = h.m, h.procs[0]
        m.stop()
        assert m.state == "idle" and m.is_alive is False
        assert h.snapshot(h.transitions) == []
        assert "term" in p.calls_snapshot()
        # EOF after a deliberate stop stays silent
        p.close_stdout()
        m._reader.join(2.0)
        assert h.snapshot(h.transitions) == []
        # second stop is a no-op
        calls = p.calls_snapshot()
        m.stop()
        assert p.calls_snapshot() == calls


# --- 9: stop single-flight + bounded killpg fallback + idle no-op -------------
def test_stop_single_flight_killpg_fallback_idle_noop():
    # (a) two concurrent stops -> exactly ONE terminate->wait sequence
    with harness(spawn=True) as h:
        m, p = h.m, h.procs[0]
        barrier = threading.Barrier(2)

        def stopper():
            barrier.wait()
            m.stop()

        ths = [threading.Thread(target=stopper) for _ in range(2)]
        for t in ths:
            t.start()
        for t in ths:
            t.join(5.0)
        assert p.calls_snapshot() == ["term"]  # cooperative wait -> no kill, ONE teardown
        assert h.snapshot(h.transitions) == []  # stop emits no delivery_state

    # (b) wait times out -> killpg path; fake pgid -> ProcessLookupError -> proc.kill()
    with harness(spawn=True, wait_blocks=True) as h2:
        h2.m.stop()
        assert h2.procs[0].calls_snapshot() == ["term", "kill"]

    # (c) stop() when never spawned: no-op
    with harness() as h3:
        h3.m.stop()
        assert h3.procs == [] and h3.snapshot(h3.transitions) == []


# --- constants sanity: stop budget mirrors recorder_host's teardown law -------
def test_stop_budget_default():
    with harness() as h:
        assert h.m._stop_timeout == 2.0  # harness override honored
    m = ImeProcess()
    assert m._stop_timeout == _DEFAULT_STOP_TIMEOUT_S
    assert m._spawn_timeout == _DEFAULT_SPAWN_TIMEOUT_S
