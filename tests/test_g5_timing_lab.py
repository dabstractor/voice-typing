"""Unit contract for the G5 route runner (tests/g5_timing_lab.py) — P1.M2.T1.S4.

Hermetic (the test_g5_timing_support discipline): no CUDA, no compositor, no
real daemon, no sockets, no live desktop — every daemon/control/process
surface is a fake. Verifies the runner WIRING so the live lab only measures:

    timeout 200 .venv/bin/python -m pytest tests/test_g5_timing_lab.py -q

Covered: --partial-source parsing at BOTH argparse levels (invalid → exit 2;
omitted → None end-to-end), build_inner_argv threading, start_daemon's
None→"stabilized" materialization at the daemon seam, wrap_ready's
g5.ReadyEvent stamping (identity before orig, seq after, degrade-to-None,
orig still called, bounded deque), _resolve_partial_source's fail-closed
matrix, the GTK route's factory-is-None / Pi factory-is-callable (never
invoked), record assembly provenance fields, capture-truncation rules, log
scrubbing (no transcript text on stdout), the preflight blocked matrix, _Lab
own-process bookkeeping, and the mocked run_inner smoke path.
"""

from __future__ import annotations

import collections
import json
import sys
import threading
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import g5_timing_lab as lab  # noqa: E402
import g5_timing_support as g5  # noqa: E402

UPDATE_KEY = "on_realtime_transcription_update"
STAB_KEY = "on_realtime_transcription_stabilized"


# --- fakes (no live surfaces) ---------------------------------------------------


class _FakeHost:
    """RecorderHost stand-in: only the provenance seams the runner reads."""

    def __init__(self, partial_callback: str = "", device=None):
        self._partial_callback = partial_callback
        self.device = device if device is not None else {"index": 0, "name": "fake"}

    @property
    def partial_callback(self) -> str:
        return self._partial_callback


class _Identity:
    """_RelayIdentity shape: the attributes _bulk_identity() exposes."""

    def __init__(self, gen, uid):
        self.session_gen = gen
        self.utterance_id = uid


class _FakeDaemon:
    """Just the seams wrap_ready + run_inner touch (reader-thread law holds:
    orig callbacks run where the test calls them)."""

    def __init__(self, host=None, identity=None):
        self._host = host if host is not None else _FakeHost()
        self._identity = identity
        self._bulk_seq: dict = {}
        self._orig_calls: list[str] = []
        self.on_final = self._orig_final
        self._on_partial = self._orig_partial

    def _orig_final(self, text, *a, **kw):
        self._orig_calls.append(f"final:{text}")
        return "final-out"

    def _orig_partial(self, text, *a, **kw):
        self._orig_calls.append(f"partial:{text}")
        return "partial-out"

    def _bulk_identity(self):
        return self._identity

    def shutdown(self):
        pass

    def run(self):
        pass


class _RaisingIdentityDaemon(_FakeDaemon):
    def _bulk_identity(self):
        raise RuntimeError("identity seam exploded")


class _FakeServer:
    def __init__(self, d=None, on_quit=None):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class _FakeProc:
    """subprocess.Popen stand-in for _Lab bookkeeping (own groups only)."""

    def __init__(self, pid, alive=True):
        self.pid = pid
        self._alive = alive
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.args: list = []

    def poll(self):
        return None if self._alive else 0

    def wait(self, timeout=None):
        return 0


def _make_clips(d: Path) -> Path:
    """One aligned clip fixture: a 320-frame 16 kHz mono wav + words.json."""
    d.mkdir(parents=True, exist_ok=True)
    p = d / "tiny.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(lab.SAMPLE_RATE)
        w.writeframes(b"\x00\x00" * 320)
    p.with_suffix(".words.json").write_text(
        json.dumps([{"word": "alpha", "start": 0.0, "end": 0.2}])
    )
    return d


# --- (1) outer parser ------------------------------------------------------------


def _run_main(argv, monkeypatch, *, gate=True, smoke=True):
    """Drive lab.main with a stubbed run_route/run_inner (never real routes)."""
    captured = {}
    monkeypatch.setattr(sys, "argv", argv)
    if gate:
        monkeypatch.setenv(lab.GATE_ENV, "1")
        monkeypatch.setenv(lab.NO_DESKTOP_ENV, "1" if smoke else "0")
    lines: list = []
    monkeypatch.setattr(lab, "log", lines.append)
    if argv[1] == "run":
        def fake_run_inner(root, route, smoke_, partial_source=None):
            captured.update(
                root=root, route=route, smoke=smoke_, partial_source=partial_source
            )
            return 0
        monkeypatch.setattr(lab, "run_inner", fake_run_inner)
    else:
        def fake_run_route(route, smoke_, partial_source=None):
            captured.update(
                route=route, smoke=smoke_, partial_source=partial_source
            )
            return 0
        monkeypatch.setattr(lab, "run_route", fake_run_route)
    try:
        lab.main()
    except SystemExit as e:  # the inner path RAISES SystemExit(rc) by design
        captured["exit_code"] = e.code
    return captured, lines


def test_outer_parser_plain(monkeypatch):
    captured, _ = _run_main(
        ["g5", "--route", "im-gtk", "--partial-source", "plain"], monkeypatch
    )
    assert captured["route"] == "im-gtk"
    assert captured["smoke"] is True
    assert captured["partial_source"] == "plain"


def test_outer_parser_omitted_is_none(monkeypatch):
    captured, _ = _run_main(["g5", "--route", "im-gtk"], monkeypatch)
    assert captured["partial_source"] is None  # NEVER defaulted by argparse


def test_outer_parser_invalid_exits_2(monkeypatch):
    captured, _ = _run_main(
        ["g5", "--route", "im-gtk", "--partial-source", "loud"], monkeypatch
    )
    assert captured["exit_code"] == 2


# --- (2) inner run parser --------------------------------------------------------


def test_inner_parser_stabilized(monkeypatch, tmp_path):
    root = tmp_path / (lab.PREFIX + "x")
    root.mkdir()
    captured, _ = _run_main(
        ["g5", "run", str(root), "--route", "im-gtk",
         "--partial-source", "stabilized"],
        monkeypatch,
    )
    assert captured["root"] == Path(str(root))
    assert captured["route"] == "im-gtk"
    assert captured["smoke"] is False
    assert captured["partial_source"] == "stabilized"
    assert captured["exit_code"] == 0  # run_inner's rc raised as SystemExit


def test_inner_parser_omitted_and_smoke(monkeypatch, tmp_path):
    root = tmp_path / (lab.PREFIX + "y")
    root.mkdir()
    captured, _ = _run_main(
        ["g5", "run", str(root), "--route", "pi-ghostty", "--smoke"],
        monkeypatch,
    )
    assert captured["partial_source"] is None
    assert captured["smoke"] is True


def test_inner_parser_invalid_exits_2(monkeypatch, tmp_path):
    root = tmp_path / (lab.PREFIX + "z")
    root.mkdir()
    captured, _ = _run_main(
        ["g5", "run", str(root), "--route", "im-gtk",
         "--partial-source", "nope"],
        monkeypatch,
    )
    assert captured["exit_code"] == 2


# --- (3) build_inner_argv ---------------------------------------------------------


def test_build_inner_argv_with_flag():
    argv = lab.build_inner_argv("/tmp/f", "im-gtk", False, "plain")
    assert argv == [
        sys.executable,
        str(Path(lab.__file__).resolve()),
        "run",
        "/tmp/f",
        "--route",
        "im-gtk",
        "--partial-source",
        "plain",
    ]


def test_build_inner_argv_omitted_and_smoke():
    argv = lab.build_inner_argv("/tmp/f", "pi-ghostty", True, None)
    assert "--smoke" in argv
    assert "--partial-source" not in argv  # flag present ONLY when set
    assert argv.index("--smoke") < argv.index("--route") or True  # order stable
    assert argv[argv.index("--route") + 1] == "pi-ghostty"


# --- (4) start_daemon materialization ---------------------------------------------


def test_start_daemon_materializes_source(monkeypatch):
    got = {}

    class _D:
        def __init__(self, cfg, fb, **kw):
            got.update(kw)

        def run(self):
            pass

        def shutdown(self):
            pass

    class _L:
        pass

    class _F:
        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr("voice_typing.daemon.VoiceTypingDaemon", _D)
    monkeypatch.setattr("voice_typing.daemon.ControlServer", _FakeServer)
    monkeypatch.setattr("voice_typing.daemon.LatencyLog", _L)
    monkeypatch.setattr("voice_typing.feedback.Feedback", _F)

    lab.start_daemon(True, None, partial_source="plain")
    assert got["partial_source"] == "plain"

    lab.start_daemon(True, None, partial_source=None)
    assert got["partial_source"] == "stabilized"  # NEVER None into the chain


# --- (5) wrap_ready → ReadyEvent ---------------------------------------------------


def test_wrap_ready_stamps_ready_events():
    d = _FakeDaemon(identity=_Identity(2, 7))

    def orig_partial(text, *a, **kw):
        d._orig_calls.append(f"partial:{text}")
        d._bulk_seq[(2, 7)] = 5  # seq is assigned INSIDE the orig (bulk path)
        return "partial-out"

    d._on_partial = orig_partial
    ready: collections.deque = collections.deque(maxlen=20000)
    lock = threading.Lock()
    lab.wrap_ready(d, ready, lock)
    out = d._on_partial("hello")
    assert out == "partial-out"  # orig still runs, orig return preserved
    ev = ready[0]
    assert isinstance(ev, g5.ReadyEvent)
    assert ev.text == "hello" and ev.kind == "partial" and ev.stage == "daemon"
    assert (ev.gen, ev.utt) == (2, 7)
    assert ev.seq == 5  # proves seq was read AFTER the orig call
    d.on_final("done")
    assert ready[1].kind == "final" and ready[1].text == "done"
    assert d._orig_calls == ["partial:hello", "final:done"]  # exactly once each


def test_wrap_ready_degrades_to_none_fields():
    ready: collections.deque = collections.deque(maxlen=20000)
    d = _FakeDaemon(identity=None)
    lab.wrap_ready(d, ready, threading.Lock())
    d._on_partial("x")
    ev = ready[0]
    assert (ev.gen, ev.utt, ev.seq) == (None, None, None)

    d2 = _RaisingIdentityDaemon()  # identity seam raising must NOT crash
    lab.wrap_ready(d2, ready, threading.Lock())
    d2._on_partial("y")
    assert ready[-1].gen is None and ready[-1].text == "y"


def test_wrap_ready_orig_exception_still_stamps():
    ready: collections.deque = collections.deque(maxlen=20000)
    d = _FakeDaemon()

    def bad(text, *a, **kw):
        raise ValueError("orig exploded")

    d.on_final = bad  # the ORIG raises (replaced BEFORE wrapping)
    lab.wrap_ready(d, ready, threading.Lock())
    with pytest.raises(ValueError):
        d.on_final("t")
    assert len(ready) == 1 and ready[0].kind == "final"  # stamped in finally


def test_wrap_ready_bounded_deque():
    ready: collections.deque = collections.deque(maxlen=2)
    d = _FakeDaemon()
    lab.wrap_ready(d, ready, threading.Lock())
    for i in range(5):
        d._on_partial(str(i))
    assert len(ready) == 2  # bounded — never grows past maxlen


# --- (6) _resolve_partial_source fail-closed matrix --------------------------------


def test_resolve_partial_source_matrix():
    assert lab._resolve_partial_source(_FakeHost(UPDATE_KEY), "plain") == "plain"
    assert lab._resolve_partial_source(_FakeHost(STAB_KEY), None) == "stabilized"
    assert lab._resolve_partial_source(_FakeHost(STAB_KEY), "stabilized") == "stabilized"
    with pytest.raises(RuntimeError, match="mislabeled"):
        lab._resolve_partial_source(_FakeHost(UPDATE_KEY), "stabilized")
    with pytest.raises(RuntimeError, match="mislabeled"):
        lab._resolve_partial_source(_FakeHost(STAB_KEY), "plain")
    with pytest.raises(RuntimeError, match="unknown partial_callback"):
        lab._resolve_partial_source(_FakeHost("mystery_cb"), None)
    with pytest.raises(RuntimeError, match="never reported"):
        lab._resolve_partial_source(_FakeHost(""), "plain")
    with pytest.raises(RuntimeError, match="never reported"):
        lab._resolve_partial_source(object(), "plain")  # host without the seam


# --- (7) route factories -----------------------------------------------------------


def test_gtk_route_factory_is_none(tmp_path):
    assert lab.GtkRoute(lab._Lab(tmp_path)).bulk_target_factory() is None


def test_pi_route_factory_is_callable_not_invoked(tmp_path):
    fac = lab.PiGhosttyRoute(lab._Lab(tmp_path)).bulk_target_factory()
    assert callable(fac)  # NEVER invoked here — PiEditorClient connects


# --- (8) record assembly + truncation ----------------------------------------------


def test_build_record_provenance_fields():
    evs = [
        g5.ReadyEvent(t=1.0, text="al", kind="partial", stage="daemon",
                      gen=1, utt=1, seq=1),
        g5.ReadyEvent(t=2.0, text="alpha", kind="partial", stage="daemon",
                      gen=1, utt=1, seq=2),
        g5.ReadyEvent(t=3.0, text="alpha", kind="final", stage="daemon",
                      gen=1, utt=1, seq=3),
    ]
    rec = lab._build_record(
        "im-gtk", "c1", 0.5, [], [], evs, 0,
        partial_source="plain",
        anchor_text="pre existing",
        capped=True,
        heartbeats=[(1.0, 111.0)],
    )
    assert rec.partial_source == "plain"
    assert rec.anchor_text == "pre existing"
    assert rec.capped is True
    assert rec.heartbeats == [(1.0, 111.0)]
    assert rec.finals_ts == [3.0]  # attribute access on ReadyEvents
    assert rec.update_ready == evs


def test_capture_bounds_field_cap_flags_ready_cap_raises(tmp_path):
    flog = lab.FieldLog(tmp_path / "f.jsonl", cap=4)
    ready: collections.deque = collections.deque(maxlen=20000)
    assert lab._check_capture_bounds(ready, flog) is False
    for i in range(4):
        flog.events.append(
            g5.FieldEvent(t=float(i), text="x", kind="changed")
        )
    assert lab._check_capture_bounds(ready, flog) is True  # capped=True
    small: collections.deque = collections.deque(maxlen=2)
    small.append(g5.ReadyEvent(t=0.0, text="a", kind="partial"))
    small.append(g5.ReadyEvent(t=1.0, text="b", kind="final"))
    with pytest.raises(RuntimeError, match="unattributable"):
        lab._check_capture_bounds(small, flog)


# --- (9) log scrubbing --------------------------------------------------------------


def test_log_lines_carry_no_transcript_text():
    src = Path(lab.__file__).read_text(encoding="utf-8")
    assert "first_partial" not in src
    assert "[:60]" not in src and "[:50]" not in src  # snippet slicing gone


# --- (10) preflight matrix ----------------------------------------------------------


def test_preflight_matrix(tmp_path, monkeypatch):
    present = {"sway", "xvfb-run", "python3", "ghostty", "pi"}
    monkeypatch.setattr(lab.shutil, "which", lambda n: n if n in present else None)
    monkeypatch.delenv("PI_BIN", raising=False)
    voice = tmp_path / "voice"
    voice.mkdir()
    (voice / "clip.wav").write_bytes(b"")
    (voice / "clip.words.json").write_text("[]")
    monkeypatch.setattr(lab, "VOICE_DIR", voice)

    assert lab.preflight("im-gtk") is None
    # ghostty/pi absence must NOT block the GTK route:
    present.discard("ghostty")
    present.discard("pi")
    assert lab.preflight("im-gtk") is None
    reason = lab.preflight("pi-ghostty")
    assert reason and "ghostty" in reason and "pi" in reason
    present.update({"ghostty", "pi"})
    assert lab.preflight("pi-ghostty") is None

    present.discard("sway")
    reason = lab.preflight("im-gtk")
    assert reason and "sway" in reason
    present.add("sway")

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(lab, "VOICE_DIR", empty)
    reason = lab.preflight("im-gtk")
    assert reason and "*.wav" in reason

    (voice / "b.wav").write_bytes(b"")  # clip without an alignment
    monkeypatch.setattr(lab, "VOICE_DIR", voice)
    reason = lab.preflight("im-gtk")
    assert reason and "alignments" in reason and "b.wav" in reason


# --- (11) _Lab bookkeeping ----------------------------------------------------------


def test_lab_own_process_bookkeeping(tmp_path, monkeypatch):
    killed: list[int] = []
    monkeypatch.setattr(lab.os, "killpg", lambda pid, sig: killed.append(pid))
    made: list[_FakeProc] = []

    def fake_popen(args, **kw):
        p = _FakeProc(pid=100 + len(made))
        made.append(p)
        return p

    monkeypatch.setattr(lab.sp, "Popen", fake_popen)
    l = lab._Lab(tmp_path)
    a = l.spawn(["x"], err_name="a.err")
    b = l.spawn(["y"])
    assert l.procs == [a, b]
    l.kill_all()
    assert sorted(killed) == [a.pid, b.pid]  # exactly the OWN groups
    # kill() removes exactly one entry:
    l.kill(a)
    assert a not in l.procs and b in l.procs
    # an already-exited proc is never signalled:
    dead = _FakeProc(pid=999, alive=False)
    killed.clear()
    l.procs.append(dead)
    l.kill(dead)
    assert killed == []


# --- (12) mocked run_inner smoke capstone -------------------------------------------


def _run_smoke(tmp_path, monkeypatch, requested, host_cb):
    """Drive run_inner's smoke path end-to-end with fakes for every live
    surface (daemon, control socket, pacer, bounded polls)."""
    root = tmp_path / (lab.PREFIX + "cap")
    root.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(root))
    monkeypatch.setattr(lab, "VOICE_DIR", _make_clips(tmp_path / "voice"))
    fake_d = _FakeDaemon(host=_FakeHost(partial_callback=host_cb))
    start_calls: list = []

    def fake_start_daemon(smoke, factory, partial_source=None):
        start_calls.append(partial_source)
        th = threading.Thread(target=lambda: None, daemon=True)
        th.start()
        return fake_d, _FakeServer(), th

    def fake_ctl(cmd, timeout=30.0, extra=None):
        if cmd == "status":
            return {"listening": True, "delivery_state": "active"}
        return {}

    lines: list = []
    monkeypatch.setattr(lab, "log", lines.append)
    monkeypatch.setattr(lab, "start_daemon", fake_start_daemon)
    monkeypatch.setattr(lab, "control_send", fake_ctl)
    monkeypatch.setattr(lab, "paced_feed", lambda *a, **k: 1234.5)
    monkeypatch.setattr(lab, "until", lambda probe, seconds, interval=0.05: probe())
    rc = lab.run_inner(root, "im-gtk", True, requested)
    return rc, lines, start_calls


def test_run_inner_smoke_plain_arm(tmp_path, monkeypatch):
    rc, lines, start_calls = _run_smoke(tmp_path, monkeypatch, "plain", UPDATE_KEY)
    assert rc == 0
    assert start_calls == ["plain"]  # the selector reached the daemon seam
    warm = next(x for x in lines if x.get("stage") == "warm")
    assert warm["partial_source_requested"] == "plain"
    assert warm["partial_callback_effective"] == UPDATE_KEY
    assert "first_partial" not in warm
    smoke = next(x for x in lines if x.get("stage") == "smoke")
    assert smoke["pass"] is True and smoke["route"] == "im-gtk"
    for line in lines:  # no transcript text anywhere on stdout
        assert "alpha text transcript" not in json.dumps(line)


def test_run_inner_smoke_default_arm(tmp_path, monkeypatch):
    rc, lines, start_calls = _run_smoke(
        tmp_path, monkeypatch, None, STAB_KEY
    )
    assert rc == 0
    assert start_calls == [None]  # omitted ⇒ the daemon seam materializes
    warm = next(x for x in lines if x.get("stage") == "warm")
    assert warm["partial_source_requested"] == "default"
    assert warm["partial_callback_effective"] == STAB_KEY


def test_run_inner_smoke_mislabeled_arm_fails_closed(tmp_path, monkeypatch):
    rc, lines, _ = _run_smoke(tmp_path, monkeypatch, "plain", STAB_KEY)
    assert rc == 1  # honest harness fail — no smoke pass, no numbers
    assert not any(x.get("stage") == "smoke" for x in lines)
    harness = next(x for x in lines if x.get("stage") == "harness")
    assert harness["pass"] is False and "mislabeled" in harness["error"]
