"""Unit contract for the Pi route frame observer (tests/g5_frame_observer.py)
— P1.M2.T1.S5.

Hermetic (the test_g5_timing_support / test_g5_timing_lab discipline): no
CUDA, no compositor, no sockets, no live desktop — every capture, IPC and
keystroke surface is a fake (scripted capture_fn on a controllable clock;
monkeypatched subprocess for swaymsg/grim; a fake wtype runner). The 8-class
classifier matrix, the bounded-capture laws, the identity-guarded geometry,
the disposable-HOME env and the calibration honesty are proven HERE so the
live lab only measures — never re-decides:

    timeout 200 .venv/bin/python -m pytest tests/test_g5_frame_observer.py -q

Covered: FrameObserver bounded deque + bounded JSONL (digests only, no
pixel bytes anywhere, capture_ms stamped, changed flag correct, stop joins),
window_geometry guard matrix (exactly-one tracked ghostty node or blocked),
correlate_frames — one test per class incl. the S3 miss rule (a miss is a
miss, never latency-imputed) and the reset exclusion, attribution-window
edges (2×cadence clamp 150 ms), calibrate per-probe latencies + skipped
honesty, build_frame_block status transitions, and _pi_window_env
(disposable HOME/XDG, PATH preserved, LD_LIBRARY_PATH stripped, private
compositor keys explicit, home dir created).
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess as sp
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import g5_frame_observer as fo  # noqa: E402
import g5_timing_lab as lab  # noqa: E402
import g5_timing_support as g5  # noqa: E402


# --- fakes (no live surfaces) ---------------------------------------------------


class FakeClock:
    """Controllable monotonic clock; every call advances by `step` so poll
    loops terminate deterministically."""

    def __init__(self, start: float = 1000.0, step: float = 0.05):
        self.t = start
        self.step = step
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            self.t += self.step
            return self.t

    def advance(self, dt: float) -> None:
        with self._lock:
            self.t += dt


_SEQ = itertools.count(1)


def fr(t: float, changed: bool = True) -> fo.FrameEvent:
    """One synthetic frame event (digest only — bytes never exist here)."""
    return fo.FrameEvent(
        seq=next(_SEQ),
        t_mono=t,
        t_wall=0.0,
        digest=f"{next(_SEQ):064x}",
        changed=changed,
        capture_ms=1.0,
    )


def fe(t: float, text: str) -> g5.FieldEvent:
    return g5.FieldEvent(t=t, text=text, kind="poll")


def tree_json(nodes: list[dict]) -> bytes:
    """A minimal swaymsg get_tree payload."""
    return json.dumps({"id": 1, "nodes": nodes, "floating_nodes": []}).encode()


def ghostty_node(pid: int, x=10, y=20, w=800, h=600) -> dict:
    return {
        "app_id": "ghostty",
        "pid": pid,
        "rect": {"x": x, "y": y, "width": w, "height": h},
        "nodes": [],
        "floating_nodes": [],
    }


@pytest.fixture
def no_subprocess(monkeypatch):
    """Guard: a unit test must never reach a real binary."""
    real = sp.run

    def _guard(*a, **kw):
        raise AssertionError(f"real subprocess call escaped: {a!r}")

    monkeypatch.setattr(fo.sp, "run", _guard)
    yield real


# --- (1) FrameObserver: bounded, digest-only, stamped ---------------------------


def test_observer_changed_flags_and_digests_only(tmp_path):
    blobs = iter([b"A", b"A", b"B"])
    clock = FakeClock(step=0.0)  # fixed time; cadence pacing via real waits
    obs = fo.FrameObserver(
        lambda: next(blobs),
        cadence_s=0.01,
        max_samples=10,
        clock=clock,
        jsonl_path=tmp_path / "field_frames.jsonl",
    )
    obs.start()
    deadline = time.monotonic() + 5
    while len(obs.events()) < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    obs.stop()
    evs = obs.events()
    assert len(evs) == 3
    assert [e.changed for e in evs] == [False, False, True]  # first is baseline
    assert evs[0].digest != evs[2].digest
    assert evs[1].digest == evs[0].digest
    assert all(e.capture_ms >= 0.0 for e in evs)
    # digests only: the JSONL carries no raw-byte field, and the digest is hex
    lines = [json.loads(x) for x in
             (tmp_path / "field_frames.jsonl").read_text().splitlines()]
    assert len(lines) == 3
    for rec in evs + lines:  # both in-RAM events and persisted lines
        d = rec.digest if isinstance(rec, fo.FrameEvent) else rec["digest"]
        assert len(d) == 64 and int(d, 16) >= 0
    for rec in lines:
        assert not any(k in rec for k in ("png", "bytes", "blob", "data"))
        assert set(rec) == {"seq", "t_mono", "t_wall", "digest", "changed",
                            "capture_ms"}


def test_observer_bounded_deque_and_jsonl_writes(tmp_path):
    n = itertools.count()
    obs = fo.FrameObserver(
        lambda: bytes([next(n) % 251]),
        cadence_s=0.005,
        max_samples=4,
        max_writes=3,
        clock=FakeClock(step=0.0),
        jsonl_path=tmp_path / "field_frames.jsonl",
    )
    obs.start()
    deadline = time.monotonic() + 5
    while not obs.stats()["capped"] and time.monotonic() < deadline:
        time.sleep(0.005)
    obs.stop()
    st = obs.stats()
    assert st["capped"] is True          # JSONL write cap hit → capped, honest
    assert len(obs.events()) <= 4        # deque bound (RAM rule)
    assert st["samples"] <= 4
    assert len((tmp_path / "field_frames.jsonl").read_text().splitlines()) == 3


def test_observer_capture_latency_and_error_stats(tmp_path):
    calls = itertools.count()

    def slow_capture():
        if next(calls) == 0:
            time.sleep(0.02)
            return b"first-ok"
        raise OSError("grim went away")

    obs = fo.FrameObserver(
        slow_capture, cadence_s=0.005, max_samples=10,
        clock=FakeClock(step=0.0),
    )
    obs.start()
    deadline = time.monotonic() + 5
    while obs.stats()["errors"] < 1 and time.monotonic() < deadline:
        time.sleep(0.005)
    obs.stop()
    st = obs.stats()
    assert st["errors"] >= 1             # capture failures counted, not hidden
    assert st["samples"] >= 1
    assert st["capture_ms_p50"] is not None and st["capture_ms_p50"] >= 0
    # capture stats are MILLISECONDS (regression: a 20 ms capture must never
    # read as 20000 — the qualification run caught exactly that 1000× error)
    assert st["capture_ms_p50"] < 1000.0
    assert st["cadence_ms_p50"] is None or st["cadence_ms_p50"] >= 0


# --- (2) window_geometry identity guard -----------------------------------------


def _geo_with(monkeypatch, payload: bytes | OSError):
    def fake_run(*a, **kw):
        if isinstance(payload, OSError):
            raise payload
        return sp.CompletedProcess(a[0], 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(fo.sp, "run", fake_run)


def test_window_geometry_one_tracked_node(monkeypatch):
    _geo_with(monkeypatch, tree_json([ghostty_node(4242)]))
    geo, reason = fo.window_geometry({"SWAYSOCK": "x"}, allowed_pids={4242})
    assert reason == "ok"
    assert geo == "10,20 800x600"


def test_window_geometry_accepts_reverse_dns_app_id(monkeypatch):
    # verified live: ghostty 1.4.0 maps as com.mitchellh.ghostty
    node = ghostty_node(4242)
    node["app_id"] = "com.mitchellh.ghostty"
    _geo_with(monkeypatch, tree_json([node]))
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert reason == "ok"
    assert geo == "10,20 800x600"


def test_window_geometry_unknown_app_id_refused(monkeypatch):
    node = ghostty_node(4242)
    node["app_id"] = "some-other-terminal"
    _geo_with(monkeypatch, tree_json([node]))
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert geo is None and "tracked=0" in reason


def test_window_geometry_zero_nodes_blocked(monkeypatch):
    _geo_with(monkeypatch, tree_json([{"app_id": "foot", "pid": 1,
                                       "rect": {"x": 0, "y": 0, "width": 5,
                                                "height": 5}}]))
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert geo is None and "tracked=0" in reason


def test_window_geometry_two_nodes_blocked(monkeypatch):
    _geo_with(monkeypatch, tree_json([ghostty_node(4242), ghostty_node(7)]))
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert geo is None and "tracked=1" in reason


def test_window_geometry_untracked_pid_blocked(monkeypatch):
    _geo_with(monkeypatch, tree_json([ghostty_node(999)]))
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert geo is None and "tracked=0" in reason


def test_window_geometry_malformed_json_blocked(monkeypatch):
    _geo_with(monkeypatch, b"{not json")
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert geo is None and reason


def test_window_geometry_swaymsg_failure_blocked(monkeypatch):
    _geo_with(monkeypatch, OSError("no socket"))
    geo, reason = fo.window_geometry({}, allowed_pids={4242})
    assert geo is None and "swaymsg" in reason


# --- (3) correlate_frames — the 8-class matrix ----------------------------------


W = 0.15  # attribution window used across the matrix


def test_class_visible_insert():
    evs = [fe(9.0, ""), fe(10.0, "hello")]
    frames = [fr(9.5), fr(10.02)]
    r = fo.correlate_frames(evs, frames, [9.99], "", attrib_window_s=W)
    assert r["classes"]["visible_insert"] == 1
    q = [x for x in r["qualifications"] if x["class"] == "visible_insert"]
    assert q[0]["field_t"] == 10.0
    assert q[0]["frame_t"] == 10.02
    assert q[0]["ack_ts"] == 9.99
    assert q[0]["latency_ms"] == pytest.approx(20.0)


def test_class_visible_correction():
    evs = [fe(9.0, "alpha beta"), fe(10.0, "alpha gamma")]
    frames = [fr(10.1)]
    r = fo.correlate_frames(evs, frames, [], "", attrib_window_s=W)
    assert r["classes"]["visible_correction"] == 1
    assert r["classes"]["visible_insert"] == 0


def test_class_ack_only_requires_alive_observer():
    # ack at 10.0; frames exist earlier (observer demonstrably alive) but
    # nothing within the window of the ack → ack_only (ACK ≠ frame proven).
    evs = [fe(1.0, "x")]
    frames = [fr(2.0)]
    r = fo.correlate_frames(evs, frames, [10.0], "x", attrib_window_s=W)
    assert r["classes"]["ack_only"] == 1
    # the same ack with a DEAD observer must NOT become ack_only (CRITICAL #6)
    r2 = fo.correlate_frames(evs, [], [10.0], "x", attrib_window_s=W)
    assert r2["classes"]["ack_only"] == 0


def test_class_unchanged_zero_diff_and_quiet_windows():
    # raw text differs but normalized content is identical (S3 zero-diff law)
    evs = [fe(9.0, "hello!"), fe(10.0, "hello.")]
    r = fo.correlate_frames(evs, [], [], "hello", attrib_window_s=W)
    assert r["classes"]["unchanged"] == 1
    # quiet span with no ack/field/frame activity at all
    r2 = fo.correlate_frames([], [], [], "", attrib_window_s=W, span_s=1.0)
    assert r2["quiet_windows"] >= 1
    assert all(v == 0 for v in r2["classes"].values())


def test_class_cursor_redraw_period_stable():
    frames = [fr(10.0), fr(10.6), fr(11.2)]  # blink-like stable period, no field
    r = fo.correlate_frames([], frames, [], "", attrib_window_s=W)
    assert r["classes"]["cursor_redraw"] == 3
    assert r["classes"]["unpaired_frame"] == 0


def test_class_reset_excluded_from_dictation():
    evs = [fe(10.0, "seed more"), fe(10.5, "seed")]
    frames = [fr(10.52)]
    r = fo.correlate_frames(evs, frames, [], "seed", attrib_window_s=W)
    assert r["classes"]["reset"] == 1
    assert r["classes"]["visible_correction"] == 0
    assert r["classes"]["visible_insert"] == 0
    assert r["classes"]["missed_below_resolution"] == 0


def test_class_missed_below_resolution_never_imputed():
    evs = [fe(9.0, ""), fe(10.0, "hello")]
    r = fo.correlate_frames(evs, [], [10.0], "", attrib_window_s=W)
    assert r["classes"]["missed_below_resolution"] == 1
    q = [x for x in r["qualifications"]
         if x["class"] == "missed_below_resolution"]
    assert q[0]["frame_t"] is None       # NEVER a fabricated frame ts
    assert q[0]["latency_ms"] is None    # NEVER a latency sample from a miss
    # the ack near the miss does not rescue it either
    assert r["classes"]["visible_insert"] == 0


def test_class_unpaired_frame_non_periodic():
    frames = [fr(10.0)]  # lone changed frame: no period can be established
    r = fo.correlate_frames([], frames, [], "", attrib_window_s=W)
    assert r["classes"]["unpaired_frame"] == 1
    assert r["classes"]["cursor_redraw"] == 0


def test_class_names_exactly_eight():
    r = fo.correlate_frames([], [], [], "", attrib_window_s=W)
    assert set(r["classes"]) == set(fo.CLASS_NAMES)
    assert len(fo.CLASS_NAMES) == 8


# --- (4) attribution-window edges -----------------------------------------------


def test_attribution_window_derivation():
    assert fo.attribution_window(0.05) == 0.15   # clamped to the 150 ms floor
    assert fo.attribution_window(0.20) == 0.40   # 2× cadence when larger
    assert fo.attribution_window(0.0) == 0.15


def test_window_edge_frame_just_outside_is_a_miss():
    evs = [fe(9.0, ""), fe(10.0, "hello")]
    inside = fo.correlate_frames(evs, [fr(10.14)], [], "",
                                 attrib_window_s=0.15)
    assert inside["classes"]["visible_insert"] == 1
    outside = fo.correlate_frames(evs, [fr(10.16)], [], "",
                                  attrib_window_s=0.15)
    assert outside["classes"]["visible_insert"] == 0
    assert outside["classes"]["missed_below_resolution"] == 1


# --- (5) calibration ------------------------------------------------------------


def test_calibrate_records_probe_latencies():
    clock = FakeClock(step=0.05)
    reads = itertools.cycle(["", "x"])  # first read (baseline) "", then change

    def read_text():
        return next(reads)

    def frames_since(t):
        return [t + 0.03]

    r = fo.calibrate(
        type_fn=lambda tail: True,
        read_text=read_text,
        frames_since=frames_since,
        clock=clock,
        sleep_fn=lambda *_: None,
        probes=[{"kind": "text", "keys": ["x", "y"]}],
    )
    assert r["status"] == "ran"
    assert r["text_detections"] == 1
    p = r["probes"][0]
    assert p["text_changed"] is True
    assert p["delta_ms"] is not None
    assert r["latency_ms_p50"] == pytest.approx(p["delta_ms"])


def test_calibrate_redraw_probe_no_text_change():
    clock = FakeClock(step=0.05)

    def read_text():
        return "stable"  # arrows never change the text

    def frames_since(t):
        return [t + 0.4]

    r = fo.calibrate(
        type_fn=lambda tail: True,
        read_text=read_text,
        frames_since=frames_since,
        clock=clock,
        sleep_fn=lambda *_: None,
        probes=[{"kind": "redraw", "keys": ["-k", "Left"]}],
    )
    assert r["status"] == "ran"
    assert r["redraw_detections"] == 1
    p = r["probes"][0]
    assert p["text_changed"] is False
    assert p["frame_ms"] == pytest.approx(400.0)
    assert p["delta_ms"] is None  # no poll detection to delta against


def test_calibrate_wtype_failure_is_skipped_no_numbers():
    r = fo.calibrate(
        type_fn=lambda tail: False,   # wtype missing / failed
        read_text=lambda: "",
        frames_since=lambda t: [],
        clock=FakeClock(step=0.05),
        sleep_fn=lambda *_: None,
    )
    assert r["status"] == "skipped"
    assert r["reason"]
    assert "latency_ms_p50" not in r  # no fabricated numbers
    assert all(p.get("delta_ms") is None for p in r.get("probes", []))


def test_calibrate_default_probes_never_enter():
    captured: list[list[str]] = []

    def type_fn(tail):
        captured.append(list(tail))
        return True

    fo.calibrate(
        type_fn=type_fn,
        read_text=itertools.cycle(["", "x"]).__next__,
        frames_since=lambda t: [t + 0.01],
        clock=FakeClock(step=0.05),
        sleep_fn=lambda *_: None,
    )
    assert captured, "default probes must run"
    for tail in captured:
        flat = " ".join(tail).lower()
        assert "return" not in flat and "enter" not in flat
    kinds = {t for tail in captured for t in tail}
    assert "BackSpace" in kinds and "Left" in kinds and "Right" in kinds


def test_run_wtype_rejects_enter_keys():
    # the module-level runner must never be handed a submit keysym
    import inspect

    src = inspect.getsource(fo)
    assert 'Return"' not in src and "'Return'" not in src
    assert '"enter"' not in src.lower().replace("never enter", "")


# --- (6) build_frame_block status semantics -------------------------------------


def stats_for(samples=10, changed=2):
    return {
        "samples": samples, "changed": changed, "capped": False, "errors": 0,
        "cadence_ms_p50": 50.0, "cadence_ms_p95": 55.0,
        "capture_ms_p50": 12.0, "capture_ms_p95": 30.0,
        "cadence_s": 0.05, "max_samples": 4000,
    }


def test_block_blocked_when_observer_never_ran():
    b = fo.build_frame_block(
        observer_stats=None,
        calibration={"status": "skipped", "reason": "observer unavailable"},
        classes={},
        attrib_window_s=0.15,
        reason="ghostty nodes=0 tracked=0 (refusing)",
    )
    assert b["status"] == "blocked"
    assert "refusing" in b["reason"]
    assert b["proxy"]  # the labelled-proxy note is ALWAYS present


def test_block_verified_via_calibration_detections():
    cal = {"status": "ran", "reason": "", "probes": [],
           "latency_ms_p50": 18.0, "latency_ms_p95": 40.0,
           "text_detections": 2, "redraw_detections": 1}
    b = fo.build_frame_block(
        observer_stats=stats_for(), calibration=cal, classes={},
        attrib_window_s=0.15, geo="10,20 800x600",
    )
    assert b["status"] == "verified"
    assert b["resolution_ms_p50"] == 18.0
    assert b["samples"]["n"] == 10


def test_block_verified_via_in_run_text_frames():
    b = fo.build_frame_block(
        observer_stats=stats_for(),
        calibration={"status": "skipped", "reason": "wtype missing"},
        classes={"visible_insert": 3},
        attrib_window_s=0.15,
    )
    assert b["status"] == "verified"


def test_block_unverified_when_ran_zero_detections():
    b = fo.build_frame_block(
        observer_stats=stats_for(changed=0),
        calibration={"status": "skipped", "reason": "wtype missing"},
        classes={},
        attrib_window_s=0.15,
    )
    assert b["status"] == "unverified"
    assert b["proxy"]


def test_block_classes_always_eight_keys():
    b = fo.build_frame_block(
        observer_stats=None, calibration=None, classes={"bogus": 9},
        attrib_window_s=0.15,
    )
    assert set(b["classes"]) == set(fo.CLASS_NAMES)
    assert b["classes"]["bogus"] == 0 if False else all(
        isinstance(v, int) for v in b["classes"].values()
    )


# --- (7) _pi_window_env — disposable HOME isolation ------------------------------


def test_pi_window_env_disposable_home(monkeypatch, tmp_path):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/cuda/lib")
    monkeypatch.setenv("SWAYSOCK", str(tmp_path / "sway-ipc.sock"))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-99")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    route = lab.PiGhosttyRoute(lab._Lab(tmp_path))
    env = route._pi_window_env()
    # HOME is the scratch home, and it exists
    assert env["HOME"] == str(tmp_path / "home")
    assert (tmp_path / "home").is_dir()
    # every XDG override lives under it
    for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                "XDG_STATE_HOME"):
        assert env[key].startswith(env["HOME"]), key
        assert Path(env[key]).is_dir()
    # PATH preserved; LD stripped; private compositor identity explicit
    assert env["PATH"] == os.environ["PATH"]
    assert "LD_LIBRARY_PATH" not in env
    assert env["SWAYSOCK"] == str(tmp_path / "sway-ipc.sock")
    assert env["WAYLAND_DISPLAY"] == "wayland-99"
    assert env["XDG_RUNTIME_DIR"] == str(tmp_path)
    # no real-HOME path may survive
    real_home = os.environ.get("HOME", "")
    if real_home:
        assert env["HOME"] != real_home


def test_pi_window_env_survives_missing_compositor_keys(monkeypatch, tmp_path):
    for key in ("SWAYSOCK", "WAYLAND_DISPLAY"):
        monkeypatch.delenv(key, raising=False)
    route = lab.PiGhosttyRoute(lab._Lab(tmp_path))
    env = route._pi_window_env()
    assert env["HOME"] == str(tmp_path / "home")


def test_compositor_env_is_explicit_not_inherited(monkeypatch, tmp_path):
    monkeypatch.setenv("SWAYSOCK", "priv.sock")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-7")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/x")
    merged = fo.compositor_env({"A": "1"})
    assert merged["SWAYSOCK"] == "priv.sock"
    assert merged["WAYLAND_DISPLAY"] == "wayland-7"
    assert merged["XDG_RUNTIME_DIR"] == "/tmp/x"
    assert merged["A"] == "1"
    # and the private keys ride along on a bare base too
    assert fo.compositor_env({})["SWAYSOCK"] == "priv.sock"


def test_observer_module_never_reads_real_home():
    import g5_frame_observer as mod
    import inspect

    src = inspect.getsource(mod)
    assert 'os.environ["HOME"]' not in src
    assert 'environ.get("HOME")' not in src
