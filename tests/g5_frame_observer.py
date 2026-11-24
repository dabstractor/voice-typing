"""g5_frame_observer — route-local frame observer for the pi-ghostty G5 lab
(P1.M2.T1.S5). NOT collected by pytest (no test_ prefix); consumed by
tests/g5_timing_lab.py's PiGhosttyRoute and unit-proven by
tests/test_g5_frame_observer.py.

Scope (Mode A): a BOUNDED grim window-region digest loop over the PRIVATE
lab Ghostty window (identity-guarded: exactly one ghostty node whose pid is
in the lab's tracked set), correlated with the independent ~10 ms editor
read-poll and the S3/S4 ack/anchor data into an 8-class qualification
(visible_insert / visible_correction / ack_only / unchanged / cursor_redraw
/ reset / missed_below_resolution / unpaired_frame). Pure stdlib; the only
in-repo import is g5_timing_support for changed_spans/normalize_tokens
(READ-ONLY consumption of the S3 engine).

Limits (stated so no consumer over-reads the numbers):
  - Observer resolution is cadence + capture latency (~50 ms loop + grim
    spawn) — it CANNOT certify the ≤100/50 ms frame bars by itself. Every
    digest observation is a LOWER BOUND on paint time; the measured
    resolution is REPORTED alongside latencies and NEVER subtracted from
    them (conservative; S6 interprets).
  - A miss is a miss (S3 law): a field change with no correlated frame in
    the attribution window is counted missed_below_resolution — never
    latency-imputed, never a fast sample.
  - An ACK is not a frame (R.5 #3): ack_only is only labeled when the
    observer is demonstrably alive (changed frames seen in the run).
  - Digests only: no pixel bytes are persisted anywhere — the JSONL carries
    sha256 hex digests, bounded by the same write-cap discipline as the
    poll loop (g5.MAX_REPORT_LINES * 200).
  - Every observer subprocess (swaymsg / grim / wtype) receives the
    EXPLICIT private compositor env (SWAYSOCK / WAYLAND_DISPLAY /
    XDG_RUNTIME_DIR captured at boot) — never a bare inherit, so no path
    here can reach the operator's display (R.7).
  - Calibration probes go through wtype keystrokes into the FOCUSED private
    window; Enter/Return is NEVER sent (no submission), and a missing or
    failing wtype degrades calibration to {"status": "skipped"} — no
    fabricated numbers.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import os
import shutil
import statistics
import subprocess as sp
import threading
import time

import g5_timing_support as g5  # read-only: changed_spans / normalize_tokens

# The 8 qualification classes (fixed contract — research §5 / PRP).
CLASS_NAMES = (
    "visible_insert",
    "visible_correction",
    "ack_only",
    "unchanged",
    "cursor_redraw",
    "reset",
    "missed_below_resolution",
    "unpaired_frame",
)

# The private-compositor identity keys EVERY observer subprocess gets
# explicitly (CRITICAL #3 — never a bare env inherit).
PRIVATE_ENV_KEYS = ("SWAYSOCK", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR")

ATTRIB_WINDOW_FLOOR_S = 0.15  # 2×cadence clamp floor (research §5)

# Known ghostty Wayland app_ids (conservative allowlist — anything else is a
# refusal, never a guess). Verified live: ghostty 1.4.0 maps as
# "com.mitchellh.ghostty"; older/docs forms use "ghostty".
GHOSTTY_APP_IDS = ("ghostty", "com.mitchellh.ghostty")


# --- data model -----------------------------------------------------------------


@dataclasses.dataclass
class FrameEvent:
    """One captured frame observation — the DIGEST, never the bytes."""

    seq: int  # capture order (0-based within this observer)
    t_mono: float  # time.monotonic() at capture start (the observer clock)
    t_wall: float  # time.time() twin (heartbeat-style sanity pairing)
    digest: str  # sha256 hex of the cropped PNG bytes — NEVER the bytes
    changed: bool  # digest != previous capture's digest (first capture: False)
    capture_ms: float  # wall time spent inside capture_fn (latency component)


# --- subprocess surfaces (explicit-env law) -------------------------------------


def compositor_env(base: dict | None = None) -> dict:
    """base ⊕ the explicit private compositor identity (PRIVATE_ENV_KEYS).

    Every observer subprocess env must be built through this (or an equal
    explicit dict): the lab's inner process env already carries the private
    SWAYSOCK/WAYLAND_DISPLAY from boot_sway and the private XDG_RUNTIME_DIR
    from the disposable root — passing them EXPLICITLY means a stray bare
    inherit can never target the operator's session (CRITICAL #3).
    """
    env = dict(base) if base is not None else {}
    env.update({k: os.environ[k] for k in PRIVATE_ENV_KEYS if k in os.environ})
    return env


def window_geometry(env: dict, allowed_pids: set[int]) -> tuple[str | None, str]:
    """Resolve the private Ghostty window's grim geometry — or refuse.

    Guard (CRITICAL #3): exactly ONE sway tree node with app_id == "ghostty"
    whose pid is in `allowed_pids` (the lab's tracked spawn set). Zero nodes,
    multiple nodes, an untracked pid, a malformed tree or a failed query are
    all a REFUSAL — (None, reason) — never a guess. Returns
    ("X,Y WxH", "ok") on success.
    """
    try:
        r = sp.run(
            ["swaymsg", "-t", "get_tree"],
            env=env,
            capture_output=True,
            timeout=3.0,
        )
        tree = json.loads(r.stdout.decode("utf-8", errors="replace"))
    except (sp.TimeoutExpired, OSError, ValueError) as exc:
        return None, f"swaymsg get_tree failed: {exc!r}"
    hits = [n for n in _walk(tree) if n.get("app_id") in GHOSTTY_APP_IDS]
    tracked = [n for n in hits if n.get("pid") in allowed_pids]
    if len(hits) != 1 or len(tracked) != 1:
        return None, f"ghostty nodes={len(hits)} tracked={len(tracked)} (refusing)"
    rect = tracked[0].get("rect") or {}
    try:
        geo = (
            f"{int(rect['x'])},{int(rect['y'])} "
            f"{int(rect['width'])}x{int(rect['height'])}"
        )
    except (KeyError, TypeError, ValueError):
        return None, "tracked ghostty node has no usable rect"
    return geo, "ok"


def _walk(node: dict):
    """Depth-first walk of a sway tree node's sub-node lists."""
    yield node
    for key in ("nodes", "floating_nodes"):
        for child in node.get(key) or []:
            yield from _walk(child)


def grim_capture(geo: str, env: dict, timeout: float = 2.0) -> bytes:
    """Capture the window region → PNG BYTES (never persisted here).

    `grim -g "X,Y WxH" -` writes the cropped PNG to stdout; the CALLER
    digests it immediately (sha256) and drops the bytes. Raises on a nonzero
    grim exit so the observer loop can count the failure honestly.
    """
    r = sp.run(["grim", "-g", geo, "-"], env=env, capture_output=True,
               timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            f"grim rc={r.returncode}: {r.stderr[:200]!r}"
        )
    return r.stdout


def run_wtype(argv_tail: list[str], env: dict, timeout: float = 5.0) -> bool:
    """Send calibration keystrokes via wtype(1) under the EXPLICIT env.

    `argv_tail` is the raw wtype argument tail (e.g. ["x", "y"] for chars or
    ["-k", "BackSpace"] / ["-k", "Left"] for special keys). Enter/Return is
    NEVER part of any probe set (no submission path exists here). False on
    any failure — calibration degrades honestly, no retries, no fabrication.
    """
    if not shutil.which("wtype"):
        return False
    try:
        r = sp.run(["wtype", *argv_tail], env=env, capture_output=True,
                   timeout=timeout)
        return r.returncode == 0
    except (sp.TimeoutExpired, OSError):
        return False


# --- the observer loop ----------------------------------------------------------


class FrameObserver:
    """Bounded digest-capture thread; `capture_fn` is INJECTED so the whole
    loop is unit-testable without a compositor.

    Bounds (CRITICAL #4): in-RAM events live in a maxlen-`max_samples`
    deque; the JSONL sidecar (`jsonl_path`) stops after `max_writes` lines
    (default g5.MAX_REPORT_LINES * 200 — the poll loop's discipline) and the
    loop itself stops on `stop()` or that cap (`capped` flag set — evidence,
    never silence). Only digests are ever stored or written.
    """

    def __init__(
        self,
        capture_fn,
        *,
        cadence_s: float = 0.05,
        max_samples: int = 4000,
        max_writes: int | None = None,
        clock=time.monotonic,
        jsonl_path=None,
    ):
        self._capture_fn = capture_fn
        self._cadence_s = cadence_s
        self._max_samples = max_samples
        self._max_writes = (
            g5.MAX_REPORT_LINES * 200 if max_writes is None else max_writes
        )
        self._clock = clock
        self._jsonl_path = jsonl_path
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._events: collections.deque = collections.deque(maxlen=max_samples)
        self._lock = threading.Lock()
        self._seq = 0
        self._writes = 0
        self._capped = False
        self._errors = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="g5-frame-obs",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def events(self) -> list[FrameEvent]:
        with self._lock:
            return list(self._events)

    def stats(self) -> dict:
        evs = self.events()
        starts = [e.t_mono for e in evs]
        d = [b - a for a, b in zip(starts, starts[1:])]
        caps = [e.capture_ms for e in evs]
        return {
            "samples": len(evs),
            "changed": sum(1 for e in evs if e.changed),
            "capped": self._capped,
            "errors": self._errors,
            "cadence_s": self._cadence_s,
            "max_samples": self._max_samples,
            "cadence_ms_p50": _pct_s(d, 50),
            "cadence_ms_p95": _pct_s(d, 95),
            "capture_ms_p50": _pct(caps, 50),  # capture_ms is already ms
            "capture_ms_p95": _pct(caps, 95),
        }

    def _run(self) -> None:
        prev: str | None = None
        fh = None
        try:
            if self._jsonl_path is not None:
                fh = self._jsonl_path.open("a", encoding="utf-8")
            while not self._stop.is_set() and self._writes < self._max_writes:
                t0 = self._clock()
                cap0 = time.monotonic()
                err = ""
                digest = ""
                try:
                    blob = self._capture_fn()
                    digest = hashlib.sha256(blob).hexdigest()
                except Exception as exc:  # noqa: BLE001 — counted, not fatal
                    err = repr(exc)
                    self._errors += 1
                capture_ms = (time.monotonic() - cap0) * 1000.0
                if not err:
                    changed = prev is not None and digest != prev
                    ev = FrameEvent(
                        seq=self._seq,
                        t_mono=t0,
                        t_wall=time.time(),
                        digest=digest,
                        changed=changed,
                        capture_ms=capture_ms,
                    )
                    self._seq += 1
                    prev = digest
                    with self._lock:
                        self._events.append(ev)
                    if fh is not None:
                        fh.write(
                            json.dumps(
                                {
                                    "seq": ev.seq,
                                    "t_mono": round(ev.t_mono, 6),
                                    "t_wall": round(ev.t_wall, 6),
                                    "digest": ev.digest,
                                    "changed": ev.changed,
                                    "capture_ms": round(ev.capture_ms, 3),
                                }
                            )
                            + "\n"
                        )
                        fh.flush()
                        self._writes += 1
                        if self._writes >= self._max_writes:
                            self._capped = True  # bounded, and visible
                self._stop.wait(self._cadence_s)
        finally:
            if fh is not None:
                fh.close()


def _pct(vals: list[float], q: float) -> float | None:
    """Percentile of values ALREADY in ms. None on empty input."""
    if not vals:
        return None
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(round((q / 100.0) * (len(s) - 1)))))
    return round(s[k], 3)


def _pct_s(vals: list[float], q: float) -> float | None:
    """Percentile of SECONDS values, returned in ms."""
    if not vals:
        return None
    return _pct([v * 1000.0 for v in vals], q)


# --- correlation (the 8-class classifier) ---------------------------------------


def attribution_window(cadence_p50_s: float) -> float:
    """The correlation window: max(2×observer cadence p50, 150 ms floor).

    Recorded in the artifact block; the LAB derives it from the observer's
    measured cadence — never hard-coded against a real run."""
    return max(2.0 * max(0.0, cadence_p50_s), ATTRIB_WINDOW_FLOOR_S)


def correlate_frames(
    field_events,
    frame_events,
    acks,
    anchor_text: str,
    *,
    attrib_window_s: float,
    period_tol: float = 0.35,
    min_period_s: float = 0.15,
    span_s: float | None = None,
) -> dict:
    """Classify the run into EXACTLY the 8 classes (research §5).

    Inputs: field_events (g5.FieldEvent poll snapshots), frame_events
    (FrameEvent digests), acks (floats OR ReadyEvent-like with .ack_ts),
    anchor_text (pre-replay field state — reset detection seed).

    Laws enforced here:
      - Miss rule (CRITICAL #5): a field change with no changed frame within
        attrib_window_s is counted missed_below_resolution; its qualification
        entry carries frame_t=None/latency=None — NEVER imputed, never a
        sample.
      - ACK ≠ frame (CRITICAL #6): ack_only requires no field AND no frame in
        the ack's window AND a demonstrably alive observer (≥1 changed frame
        in the stream); from a dead observer it is withheld entirely.
      - reset (revert to anchor equality) is counted separately — excluded
        from dictation counts downstream — but verified painted when a frame
        correlates.
      - Period-stable changed frames with no field change (cursor blink /
        cursor move) are cursor_redraw; non-periodic ones are unpaired_frame
        (S3's orphan rule analog).
      - `unchanged` also counts quiet attribution windows (no ack/field/frame
        activity) as `quiet_windows` — dead time is reported, not hidden.
    """
    classes = {name: 0 for name in CLASS_NAMES}
    qualifications: list[dict] = []
    w = max(0.0, attrib_window_s)

    # acks: floats or objects with ack_ts
    ack_ts = sorted(
        a if isinstance(a, (int, float)) else getattr(a, "ack_ts")
        for a in acks
        if a is not None
    )
    ack_ts = [float(a) for a in ack_ts]

    # field CHANGES (consecutive differing snapshots; first event = baseline)
    changes: list[tuple[float, str, str]] = []
    prev = None
    for ev in field_events:
        if prev is not None and ev.text != prev.text:
            changes.append((float(ev.t), prev.text, ev.text))
        prev = ev

    changed_frames = sorted(
        (f for f in frame_events if getattr(f, "changed", False)),
        key=lambda f: f.t_mono,
    )
    observer_alive = bool(changed_frames)

    # period baseline over the whole changed-frame stream (cursor blink etc.)
    intervals = [
        b.t_mono - a.t_mono for a, b in zip(changed_frames, changed_frames[1:])
    ]
    period = statistics.median(intervals) if len(intervals) >= 2 else None
    periodic = period is not None and period >= min_period_s

    def nearest_frame(t: float):
        near = [f for f in changed_frames if abs(f.t_mono - t) <= w]
        return min(near, key=lambda f: abs(f.t_mono - t)) if near else None

    used: set[int] = set()
    for t, old, new in changes:
        entry = {
            "field_t": round(t, 6),
            "ack_ts": None,
            "frame_t": None,
            "class": "",
            "latency_ms": None,
        }
        near_acks = [a for a in ack_ts if abs(a - t) <= w]
        if near_acks:
            entry["ack_ts"] = round(min(near_acks, key=lambda a: abs(a - t)), 6)
        f0 = nearest_frame(t)
        if anchor_text and new == anchor_text:
            # revert to the pre-replay anchor: reset (excluded from dictation)
            if f0 is not None:
                used.add(f0.seq)
                entry.update(
                    _class="reset",
                    frame_t=round(f0.t_mono, 6),
                    latency_ms=round((f0.t_mono - t) * 1000.0, 3),
                )
                classes["reset"] += 1
            else:
                entry["_class"] = "missed_below_resolution"
                classes["missed_below_resolution"] += 1
        else:
            spans = g5.changed_spans(old, new)
            if not spans:
                entry["_class"] = "unchanged"  # raw diff, zero content diff
                classes["unchanged"] += 1
            elif f0 is not None:
                kind = _span_kind(old, new, spans)
                cls = "visible_insert" if kind == "insert" else \
                    "visible_correction"
                used.add(f0.seq)
                entry.update(
                    _class=cls,
                    frame_t=round(f0.t_mono, 6),
                    latency_ms=round((f0.t_mono - t) * 1000.0, 3),
                )
                classes[cls] += 1
            else:
                entry["_class"] = "missed_below_resolution"  # a miss is a miss
                classes["missed_below_resolution"] += 1
        entry["class"] = entry.pop("_class")
        qualifications.append(entry)

    for a in ack_ts:
        near_field = any(abs(ct - a) <= w for ct, _o, _n in changes)
        near_frame = any(abs(f.t_mono - a) <= w for f in changed_frames)
        if not near_field and not near_frame and observer_alive:
            classes["ack_only"] += 1
            qualifications.append(
                {
                    "field_t": None,
                    "ack_ts": round(a, 6),
                    "frame_t": None,
                    "class": "ack_only",
                    "latency_ms": None,
                }
            )

    for f in changed_frames:
        if f.seq in used or f.changed is False:
            continue
        if any(abs(ct - f.t_mono) <= w for ct, _o, _n in changes):
            continue  # paired to a field change above
        stable = periodic and any(
            abs(iv - period) <= period_tol * period
            for iv, pair in zip(
                intervals,
                zip(changed_frames, changed_frames[1:]),
            )
            if f.seq in (pair[0].seq, pair[1].seq)
        )
        cls = "cursor_redraw" if stable else "unpaired_frame"
        classes[cls] += 1
        qualifications.append(
            {
                "field_t": None,
                "ack_ts": None,
                "frame_t": round(f.t_mono, 6),
                "class": cls,
                "latency_ms": None,
            }
        )

    # quiet attribution windows over the covered span (dead time, reported)
    ts = [float(ev.t) for ev in field_events]
    ts += [f.t_mono for f in frame_events] + ack_ts
    quiet = 0
    if ts or span_s is not None:
        lo = min(ts) if ts else 0.0
        hi = max(ts) if ts else (lo + (span_s or 0.0))
        if span_s is not None:
            hi = max(hi, lo + span_s)
        span = hi - lo
        if span > 0:
            n_buckets = min(int(span / w) if w > 0 else 0, 10000)
            for i in range(n_buckets):
                b0, b1 = lo + i * w, lo + (i + 1) * w
                if not any(b0 <= t < b1 for t in ts):
                    quiet += 1

    return {
        "classes": classes,
        "qualifications": qualifications,
        "attrib_window_s": attrib_window_s,
        "period_s": round(period, 6) if period is not None else None,
        "quiet_windows": quiet,
        "observer_alive": observer_alive,
    }


def _span_kind(old_text: str, new_text: str, spans) -> str:
    """insert vs correction from g5.changed_spans output: a span whose
    re-insertion into the old token list reproduces the new snapshot is a
    pure insert; anything else is a rewrite (correction). Deterministic."""
    old_toks = g5.normalize_tokens(old_text)
    new_toks = g5.normalize_tokens(new_text)
    for span in spans:
        if old_toks[: span.pos] + list(span.tokens) + old_toks[span.pos:] != \
                new_toks:
            return "correction"
    return "insert"


# --- boot-time calibration ------------------------------------------------------

DEFAULT_PROBES = (
    {"kind": "text", "keys": ["x", "y"]},
    {"kind": "revert", "keys": ["-k", "BackSpace"]},
    {"kind": "revert", "keys": ["-k", "BackSpace"]},
    {"kind": "redraw", "keys": ["-k", "Left"]},
    {"kind": "redraw", "keys": ["-k", "Right"]},
)


def calibrate(
    *,
    type_fn,
    read_text,
    frames_since,
    clock=time.monotonic,
    sleep_fn=time.sleep,
    settle_s: float = 2.0,
    frame_wait_s: float = 1.5,
    probes=None,
) -> dict:
    """Boot-time observer calibration (pre-warmup — outside every measured
    window; the LAB owns that ordering, not this function).

    Probes (defaults; NEVER Enter/Return — no submission path):
      - text: plain chars via wtype → the editor read-poll must see the text
        change and the observer must see a changed frame;
      - revert: Backspace removes them (a second text change back to anchor);
      - redraw: ArrowLeft/Right — a frame change with NO text change (the
        cursor-redraw discriminandum; blink must stay distinguishable, never
        sanitized away).

    Per probe: poll_ms (read-poll detection vs keystroke), frame_ms (changed
    frame vs keystroke), delta_ms (frame vs poll — text/revert only). The
    delta distribution IS the recorded observer resolution; it is REPORTED
    alongside latencies and never subtracted from them.

    Honesty: a missing/failing wtype (or a failing editor read) returns
    {"status": "skipped", "reason": …} with the probes completed so far and
    NO aggregate numbers — nothing is fabricated (PRP Gotcha #8).
    """
    if probes is None:
        probes = list(DEFAULT_PROBES)
    out: list[dict] = []
    for probe in probes:
        try:
            before = read_text()
        except Exception as exc:  # noqa: BLE001
            return {"status": "skipped",
                    "reason": f"editor read failed: {exc!r}",
                    "probes": out}
        t0 = clock()
        if not type_fn(probe["keys"]):
            return {"status": "skipped",
                    "reason": "keystroke probe failed (wtype missing/failed?)",
                    "probes": out}
        text_changed = False
        poll_t = None
        deadline = t0 + settle_s
        while clock() < deadline:
            try:
                if read_text() != before:
                    text_changed = True
                    poll_t = clock()
                    break
            except Exception:  # noqa: BLE001 — a read hiccup must not kill it
                pass
            sleep_fn(0.01)
        frame_t = None
        fdeadline = clock() + frame_wait_s  # relative to NOW (settle may have run)
        while clock() < fdeadline:
            ts = [t for t in frames_since(t0) if t >= t0]
            if ts:
                frame_t = min(ts)
                break
            sleep_fn(0.01)
        out.append(
            {
                "kind": probe["kind"],
                "keys": list(probe["keys"]),
                "text_changed": text_changed,
                "poll_ms": round((poll_t - t0) * 1000.0, 3)
                if poll_t is not None
                else None,
                "frame_ms": round((frame_t - t0) * 1000.0, 3)
                if frame_t is not None
                else None,
                "delta_ms": round((frame_t - poll_t) * 1000.0, 3)
                if frame_t is not None and poll_t is not None
                else None,
            }
        )
    deltas = [p["delta_ms"] for p in out if p["delta_ms"] is not None]
    return {
        "status": "ran",
        "reason": "",
        "probes": out,
        "latency_ms_p50": _pct(deltas, 50),
        "latency_ms_p95": _pct(deltas, 95),
        "text_detections": sum(
            1
            for p in out
            if p["kind"] in ("text", "revert")
            and p["text_changed"]
            and p["frame_ms"] is not None
        ),
        "redraw_detections": sum(
            1
            for p in out
            if p["kind"] == "redraw"
            and not p["text_changed"]
            and p["frame_ms"] is not None
        ),
    }


# --- the additive artifact block (research §6) ----------------------------------


def build_frame_block(
    *,
    observer_stats: dict | None,
    calibration: dict | None,
    classes: dict,
    attrib_window_s: float,
    geo: str = "",
    reason: str = "",
    proxy: str = "editor 10 ms read-poll (proxy; extension exposes no render "
    "callback)",
) -> dict:
    """The ONE additive `frame_observer` artifact block for S6 / T2.S3.

    Status semantics (never a synthetic pass):
      - verified   — the observer ran AND ≥1 text-correlated frame was
                     detected (a calibration text/revert probe, or in-run
                     visible_insert/visible_correction/reset);
      - unverified — the observer ran but detected ZERO text-correlated
                     frames (cadence/capture stats still recorded);
      - blocked    — the observer never ran (grim missing, geometry guard
                     refusal, env guard) → the editor poll stays the LABELLED
                     PROXY and every frame metric is unverified.
    An ACK never upgrades a status (R.5 #3): ack_only alone is not evidence.
    """
    cls = {name: int(classes.get(name, 0)) for name in CLASS_NAMES}
    cal = calibration if isinstance(calibration, dict) else {
        "status": "skipped",
        "reason": "calibration unavailable",
    }
    ran = observer_stats is not None
    text_corr = cls["visible_insert"] + cls["visible_correction"] + \
        cls["reset"]
    cal_text = int(cal.get("text_detections") or 0) if ran else 0
    if not ran:
        status, why = "blocked", reason or "observer never started"
    elif text_corr > 0 or cal_text > 0:
        status, why = "verified", "text-correlated frames detected"
    else:
        status, why = "unverified", "ran; zero text-correlated frames"
    return {
        "status": status,
        "reason": why,
        "proxy": proxy,
        "observer": {
            "tool": "grim window-region digest (wlr-screencopy)",
            "window_geo": geo,
            "cadence_s": (observer_stats or {}).get("cadence_s"),
        },
        "cadence_ms_p50": (observer_stats or {}).get("cadence_ms_p50"),
        "cadence_ms_p95": (observer_stats or {}).get("cadence_ms_p95"),
        "capture_ms_p50": (observer_stats or {}).get("capture_ms_p50"),
        "capture_ms_p95": (observer_stats or {}).get("capture_ms_p95"),
        "resolution_ms_p50": cal.get("latency_ms_p50"),
        "resolution_ms_p95": cal.get("latency_ms_p95"),
        "calibration": cal,
        "samples": {
            "n": (observer_stats or {}).get("samples", 0),
            "changed": (observer_stats or {}).get("changed", 0),
            "capped": (observer_stats or {}).get("capped", False),
            "errors": (observer_stats or {}).get("errors", 0),
        },
        "classes": cls,
        "attrib_window_s": attrib_window_s,
    }
