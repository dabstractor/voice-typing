#!/usr/bin/env python3
"""ime_g3_editor_browser_lab — G3 rows for the GRAPHICAL EDITOR (Gtk.TextView)
and a REAL BROWSER TEXT FIELD (Chromium 158, text-input-v3) through the REAL
takeover-complete IM-v2 adapter (voice_typing/ime ImeProcess + ImeTarget).
NOT collected by pytest (no test_ prefix; env-gated). Run by hand against a
PRIVATE disposable desktop ONLY — it never touches the live desktop, the real
clipboard or Chromium profile, the default microphone, or the user's service
(it owns its ImeProcess and speaks only to the private seat; no control
socket, no system service manager, no audio server, no global clipboard):

    timeout -k 2 420 env IME_G3_EDITOR_BROWSER_LAB=1 .venv/bin/python \\
        tests/ime_g3_editor_browser_lab.py

Optional: IME_G3_EDITOR_BROWSER_STAGE=editor stops after the editor class
(milestone mode; browser rows record honest untested verdicts);
IME_G3_EDITOR_BROWSER_OUT=<dir> additionally writes g3_editor_browser_rows.md
+ editor_browser_row_verdicts.jsonl into that dir.

Rows (one JSON verdict line each, mirrored to <root>/verdicts.jsonl; t_ms is
mechanism-level info — NEVER G5; same assertion families as the landed G3
harness, tests/ime_g3_lab.py R1–R5):
  E1 editor-short-updates     6 short inserts: APPLIED, cumulative text
                              byte-exact, cursor at end (chars), cseq Δ∈(1,2),
                              frame oracle = exactly ONE text transition,
                              zero transient frames, dones ≥1 per op.
  E2 editor-firstword-20sent  ~1.5–2 KB 20-sentence span inserted, then its
                              FIRST word corrected in ONE wire commit
                              (delete_surrounding + commit): byte-exact,
                              single visible edit, reach ≫ utterance, pre-op
                              recheck() ok, verify suffix-agreement.
  E3 editor-identical-finals  the same final span show()n 3x: UNCHANGED each,
                              cseq Δ0, dones unchanged — zero-diff ⇒ zero
                              events on the buffer-based field.
  E4 editor-long-unicode      (a) 951 B multilingual; (b) ~3.5 KB mixed;
                              (c) >4 KB REFUSED at the 4000 B cap, field
                              untouched.
  E5 editor-refusing-readonly the view booted non-editable: NO visible edit
                              under any branch; the ACTUAL branch recorded;
                              then a fresh writable view takes one insert.
  E6 editor-takeover          real xdotool key mid-owned-fragment with the
                              host grab engaged: grab_key events → takeover
                              detector → halt_for_takeover EXACTLY once,
                              next op refused, field counters FROZEN (the
                              grab consumed the key).
  B1 browser-short-updates    6 short inserts into a real DOM <input>: value
                              byte-exact, selectionStart exact (UTF-16 via
                              map_span), exactly 1 input event per op, no
                              intermediate rAF value-hashes.
  B2 browser-firstword-20sent 20-sentence span + first-word correction: ONE
                              input event with the full before→after delta;
                              whatever the correction branch ACTUALLY does
                              (applied / refused for lack of surrounding_text)
                              is recorded honestly — insert-only is a
                              legitimate outcome for this class.
  B3 browser-identical-finals same applied span ×3: UNCHANGED, ZERO input
                              events, value hash unchanged.
  B4 browser-long-unicode     (a)/(b) applied byte-exact; (c) overcap REFUSED,
                              field untouched (Δn=0).
  B5 browser-refusing-readonly <input readonly> (?mode=ro): honest refusing
                              branch + recovery insert on a writable window.
  B6 browser-takeover         the E6 leg against the browser window + the
                              page's keydown counter did NOT move.

Witnesses: the editor app's own atomic dump + frame oracle + counters
(tests/ime_g3_field_edit.py); the page's OWN JS state pushes / title fallback
(tests/fixtures/ime_g3_browser_field.html + ime_g3_editor_browser_support).
Supplementary grim screenshots are evidence, never the gate.

Boot pattern copied from tests/ime_g3_lab.py (itself from
tests/ime_correction_lab.py — READ-ONLY lineage, forked not modified; NO
cross-lab imports — the small helpers below are local copies with lineage
comments): xvfb-run -a + dbus-run-session --config-file=<private bus> + sway
x11 backend on a disposable HOME/XDG_RUNTIME_DIR/TMPDIR (ONE
TemporaryDirectory, prefix ime-g3-eb-lab-). The editor field runs on SYSTEM
python3 (the venv has no gi); Chromium runs from /usr/bin with an isolated
temp-root profile; the adapter is ImeProcess (venv python) driving ImeTarget.
ONE ImeProcess per seat; rows share it; leave() between rows; re-acquire per
row. Teardown killpg's our own session groups + TemporaryDirectory removes the
root. Without IME_G3_EDITOR_BROWSER_LAB=1: prints skipped, exits 0. Exit
codes: 0 all rows pass, 1 any row failed, 2 gate/env misuse.
"""

from __future__ import annotations

import collections
import json
import os
import platform
import shutil
import signal
import subprocess as sp
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from voice_typing.bulk_delivery import ShowResult, TargetUnits, map_span
from voice_typing.ime.manager import ImeProcess
from voice_typing.ime.target import FieldBinding, ImeTarget
from voice_typing.ime.takeover import TakeoverWatch

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE.parent), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from ime_g3_support import OVERCAP_BLOCKED_REASON, build_payloads, single_edit_analysis  # noqa: E402
from ime_g3_editor_browser_support import (  # noqa: E402
    BrowserState,
    class_verdict,
    chromium_argv,
    firefox_argv,
    fnv1a32,
    input_event_law,
    parse_push,
    parse_title,
    render_class_report,
)

REPO = Path(__file__).resolve().parents[1]
GATE_ENV = "IME_G3_EDITOR_BROWSER_LAB"
STAGE_ENV = "IME_G3_EDITOR_BROWSER_STAGE"
OUT_ENV = "IME_G3_EDITOR_BROWSER_OUT"
PREFIX = "ime-g3-eb-lab-"
FIELD_APP = REPO / "tests" / "ime_g3_field_edit.py"
EDITOR_TITLE = "vtg3-editor"
FIXTURE = REPO / "tests" / "fixtures" / "ime_g3_browser_field.html"
BROWSER_TITLE = "vtg3-browser"
SYSTEM_PY = shutil.which("python3") or "python3"
XDOTOOL = shutil.which("xdotool")  # real-key injection per the im-lab recipe
WTYPE = shutil.which("wtype")  # native-Wayland fallback injector
REAL_KEY_DRIFT = (
    "the leg drives ONE real key via xdotool XTEST into sway's X window on the "
    "Xvfb display (tools/im-lab/imlab_run.py grab_rows recipe: search "
    "--onlyvisible --maxdepth 1 + windowfocus + key) — the injected X events "
    "become seat keyboard input through wlroots' x11 backend and arrive as "
    "grab_key while the IM holds the grab; wtype is the recorded fallback"
)
INNER_WAIT_S = 400  # bounded well inside the outer `timeout -k 2 420`
READY_S = 30  # cold Chromium is slow — bounded first-push poll

REPORT_TITLE = "G3 editor + browser row report — TextView + Chromium text field, IM-v2 (P1.M5.T2.S2)"


def until(probe, seconds: float):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        v = probe()
        if v is not None and v is not False and v != "":
            return v
        time.sleep(0.02)
    return None


def _field(lab: "Lab", tag: str = "") -> dict | None:
    try:
        return json.loads(
            (lab.root / f"field{('-' + tag) if tag else ''}.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return None


class _EventCollector:
    """on_event callback: bounded deque (never unbounded), plus a count helper.
    The DURABLE event record is the host's capped EventLogWriter file; this is
    row-convenience only. (Lineage: tests/ime_g3_lab.py.)"""

    def __init__(self, cap: int = 4096):
        self.items: collections.deque = collections.deque(maxlen=cap)

    def __call__(self, ev: dict) -> None:
        self.items.append(ev)

    def count(self, name: str) -> int:
        return sum(1 for e in self.items if e.get("ev") == name)


class _DuckController:
    """Records halt_for_takeover calls — the takeover leg's evidence seam
    (consumption pattern from tests/test_ime_takeover.py)."""

    def __init__(self):
        self.halts = 0
        self.reasons: list[str] = []

    def halt_for_takeover(self, reason) -> None:
        self.halts += 1
        self.reasons.append(str(reason))


class Lab:
    """Seat-scoped helpers. (Lineage: tests/ime_g3_lab.py Lab — copied, not
    imported: cross-lab internals are fenced by the item contract.)"""

    def __init__(self, root: Path):
        self.root = root
        self.env = os.environ.copy()
        self.procs: list[sp.Popen] = []
        self.field_proc: sp.Popen | None = None
        self.verdicts: list[dict] = []
        self.report_rows: list[dict] = []
        self.events = _EventCollector()
        self.takeover_ran = False
        self.grab_keys_after_first_takeover: int | None = None
        self.chromium_no_sandbox = False

    def spawn(self, args, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr_name=None):
        err = (self.root / stderr_name).open("wb") if stderr_name else sp.DEVNULL  # noqa: SIM115
        p = sp.Popen(
            args,
            stdin=stdin,
            stdout=stdout,
            stderr=err,
            env=self.env,
            start_new_session=True,
        )
        self.procs.append(p)
        return p

    def kill(self, p: sp.Popen) -> None:
        if p in self.procs:
            self.procs.remove(p)
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            p.wait(timeout=2)
        except sp.TimeoutExpired:
            pass

    def cmd(self, args, timeout=5):
        return sp.run(
            args,
            stdin=sp.DEVNULL,
            stdout=sp.PIPE,
            stderr=sp.DEVNULL,
            env=self.env,
            timeout=timeout,
        ).stdout

    def focus(self, criteria: str) -> None:
        try:
            self.cmd(["swaymsg", "-r", criteria + " focus"])
        except (sp.TimeoutExpired, OSError):
            pass

    def err_head(self, name, n=300):
        try:
            return (self.root / name).read_text(errors="replace")[:n]
        except FileNotFoundError:
            return ""

    def verdict(self, row: str, ok, sub: str = "", checks=(), t_ms=None, **kw):
        v = {"row": row, "sub": sub, "pass": ok, "checks": list(checks), "t_ms": t_ms}
        v.update(kw)
        self.verdicts.append(v)
        print(json.dumps(v, ensure_ascii=False), flush=True)
        try:
            with (self.root / "verdicts.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(v, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def shot(self, name: str) -> str | None:
        """Optional per-row screenshot: sha256[:16] ONLY — the image is deleted
        immediately (bounded scratch; evidence stays capped)."""
        if not shutil.which("grim"):
            return None
        png = self.root / f"{name}.png"
        try:
            sp.run(
                ["grim", str(png)],
                env=self.env,
                timeout=5,
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL,
                check=False,
            )
            if not png.exists():
                return None
            import hashlib

            digest = hashlib.sha256(png.read_bytes()).hexdigest()[:16]
            return digest
        except (sp.TimeoutExpired, OSError):
            return None
        finally:
            try:
                png.unlink()
            except OSError:
                pass

    def teardown(self):
        for p in reversed(self.procs):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            try:
                p.wait(timeout=2)
            except sp.TimeoutExpired:
                pass


def start_desktop(lab: Lab) -> None:
    """(Lineage: tests/ime_g3_lab.py start_desktop.) Private sway x11 seat."""
    conf = lab.root / "sway.conf"
    conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
    sway = lab.spawn(["sway", "-c", str(conf)])
    if (
        not until(lambda: next(lab.root.glob("sway-ipc.*.sock"), None), 7)
        or sway.poll() is not None
    ):
        raise RuntimeError("private Sway failed to start")
    lab.env["SWAYSOCK"] = str(next(lab.root.glob("sway-ipc.*.sock")))
    lab.env["WAYLAND_DISPLAY"] = until(
        lambda: next(
            (p.name for p in lab.root.glob("wayland-*") if p.is_socket()), None
        ),
        7,
    )
    lab.env["PYTHONPATH"] = str(REPO)


def spawn_field_edit(lab: Lab, tag: str = "", readonly: bool = False) -> sp.Popen:
    """Boot the TextView editor app on SYSTEM python3 (PyGObject lives there).
    The adapter stays on the venv python; they share only the private seat.
    (Lineage: tests/ime_g3_lab.py spawn_field.)"""
    args = [SYSTEM_PY, str(FIELD_APP), str(lab.root)]
    if readonly:
        args.append("--readonly")
    if tag:
        args += ["--tag", tag]
    err_name = f"gtk{('-' + tag) if tag else ''}.err"
    p = lab.spawn(args, stderr_name=err_name)
    lab.field_proc = p  # E5 kills THE FIELD — never a generic alive-proc match
    suffix = f"-{tag}" if tag else ""
    if (
        not until(lambda: (lab.root / f"field{suffix}.ready").exists(), 8)
        or p.poll() is not None
    ):
        raise RuntimeError(
            f"field{suffix} never became ready: {lab.err_head(err_name)}"
        )
    return p


def _verify_snapshot(proc: ImeProcess) -> dict:
    return proc.request("verify", timeout=2.5) or {}


def _verify_agrees(proc: ImeProcess, expected: str, ev: dict) -> bool:
    """Assertion family 6: target-CONFIRMED text vs the expected field text.

    LOCAL COPY of tests/ime_g3_lab.py:_verify_agrees (PRP gotcha: do NOT
    import cross-lab internals — fork with lineage). GTK caps the client-side
    surrounding_text window near the cursor (~4 KiB, measured 3999 B on this
    stack): for fields beyond the cap, FULL agreement is impossible by toolkit
    design and agreement is asserted on the overlap — the caret sits at the
    END, so the snapshot must be a byte-exact SUFFIX of the expected text."""
    v = _verify_snapshot(proc)
    vtext = v.get("text") or ""
    exp = expected.encode("utf-8")
    got = vtext.encode("utf-8")
    ev["verify_bytes"] = v.get("bytes")
    ev["expected_bytes"] = len(exp)
    if v.get("snapshot_truncated"):
        ev["verify_note"] = "host head cap"
        return False
    if len(got) < len(exp):
        if not got or not exp.endswith(got):
            ev["verify_head"] = vtext[:40]
            ev["verify_tail"] = vtext[-40:]
            return False
        ev["verify_note"] = (
            f"snapshot window {len(got)} B < field {len(exp)} B — toolkit caps "
            f"surrounding_text near the cursor; suffix agreement verified"
        )
        return True
    if got != exp:
        ev["verify_head"] = vtext[:40]
        ev["verify_tail"] = vtext[-40:]
        return False
    return True


def _browser_verify(
    proc: ImeProcess,
    prev_expected: str,
    ev: dict,
    bad: list[str],
    key: str,
    *,
    current_expected: str | None = None,
) -> None:
    """Honest family-6 for the browser. MEASURED at chromium 158.0.8127.36:
    the surrounding_text snapshot reflects the field value BEFORE the last
    IM commit (a one-commit structural lag — confirmed numerically: the
    snapshot equals the pre-commit value byte-for-byte with cursor/anchor at
    its window end), so the primary assertion target is prev_expected. If
    the snapshot IS current (== current_expected) that is recorded too. The
    snapshot must match prev exactly — or, when the snapshot window caps it,
    be a byte-exact TAIL of prev with cursor==anchor==window end. Absent
    surrounding_text is recorded, never papered over."""
    v = _verify_snapshot(proc)
    if v.get("ok") is False:
        ev[f"{key}_surrounding"] = f"absent ({v.get('reason')})"
        return
    vtext = v.get("text") or ""
    got = vtext.encode("utf-8")
    cur = (current_expected or prev_expected).encode("utf-8")
    prev = prev_expected.encode("utf-8")
    ev[f"{key}_verify_bytes"] = v.get("bytes")
    ev[f"{key}_expected_prev_bytes"] = len(prev)
    ev[f"{key}_verify_cursor"] = [v.get("cursor"), v.get("anchor")]
    ok: bool
    if v.get("snapshot_truncated"):
        ev[f"{key}_verify_note"] = "host head cap"
        ok = False
    elif got == cur:
        ok = True
        ev[f"{key}_verify_note"] = "snapshot current"
    elif got == prev:
        ok = True
        ev[f"{key}_verify_note"] = (
            "one-commit lag MEASURED: snapshot == field value before the last commit"
        )
    elif len(got) < len(prev) and prev.endswith(got) and v.get("cursor") == len(got):
        ok = True
        ev[f"{key}_verify_note"] = (
            f"one-commit lag + window cap: snapshot is the tail {len(got)} B of the "
            f"pre-commit value ({len(prev)} B), cursor at window end"
        )
    elif len(got) < len(cur) and cur.endswith(got) and v.get("cursor") == len(got):
        ok = True
        ev[f"{key}_verify_note"] = (
            f"snapshot window {len(got)} B < field {len(cur)} B — suffix rule"
        )
    else:
        ok = False
        ev[f"{key}_verify_head"] = vtext[:40]
        ev[f"{key}_verify_tail"] = vtext[-40:]
    if not ok:
        bad.append(f"{key}-target-confirmed")


def _focused_title(lab: "Lab") -> str | None:
    """Title of the focused sway node (focus evidence). (Lineage:
    tests/ime_g3_lab.py _focused_title — WINDOW nodes only.)"""
    try:
        tree = json.loads(lab.cmd(["swaymsg", "-r", "-t", "get_tree"]).decode())
    except (sp.TimeoutExpired, OSError, json.JSONDecodeError, ValueError):
        return None
    stack = [tree]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        if n.get("type") in ("con", "floating_con") and n.get("focused"):
            return n.get("name")
        stack.extend(n.get("nodes") or [])
        stack.extend(n.get("floating_nodes") or [])
    return None


def _browser_window(lab: "Lab") -> dict | None:
    """The vtg3-browser* window's title + app_id from the sway tree (recorded
    evidence; sway focus ≠ DOM focus — the fixture autofocuses the input)."""
    try:
        tree = json.loads(lab.cmd(["swaymsg", "-r", "-t", "get_tree"]).decode())
    except (sp.TimeoutExpired, OSError, json.JSONDecodeError, ValueError):
        return None
    stack = [tree]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        if n.get("type") in ("con", "floating_con") and str(
            n.get("name") or ""
        ).startswith(BROWSER_TITLE):
            return {"title": n.get("name"), "app_id": n.get("app_id")}
        stack.extend(n.get("nodes") or [])
        stack.extend(n.get("floating_nodes") or [])
    return None


def start_adapter(lab: Lab) -> ImeProcess:
    """Spawn the REAL adapter: ImeProcess (venv python; cwd=repo root is
    inherited from the outer spawn; PYTHONPATH=REPO set by start_desktop).
    ONE per seat (input-method singleton) — every row shares this instance.
    (Lineage: tests/ime_g3_lab.py start_adapter.)"""
    host_log = lab.root / "ime_host.jsonl"  # EventLogWriter-capped at 64 KiB
    proc = ImeProcess(log_path=str(host_log), on_event=lab.events)
    if not proc.spawn(timeout=15):
        raise RuntimeError(
            f"ImeProcess spawn failed (state={proc.state}): "
            f"{lab.err_head('im_host.err')} events={list(lab.events.items)[-3:]}"
        )
    if not until(
        lambda: host_log.exists() and "globals" in host_log.read_text(errors="replace"),
        7,
    ):
        raise RuntimeError("ime_host never became the seat's input method")
    return proc


def _ping(proc: ImeProcess) -> dict:
    r = proc.request("ping", timeout=1.0) or {}
    return {"activated": bool(r.get("activated")), "dones": int(r.get("dones", 0))}


def wait_activated(proc: ImeProcess, seconds: float = 8.0) -> bool:
    """Pump pings until the IM reports activation (the host drains wire events
    around request handling; the manager's reader thread needs the pump)."""
    return until(lambda: _ping(proc)["activated"], seconds) is not None


def wait_deactivated(proc: ImeProcess, seconds: float = 2.0) -> bool:
    return until(lambda: not _ping(proc)["activated"], seconds) is not None


def _show(
    target: ImeTarget,
    rev_box: list[int],
    session: int,
    utterance: str,
    seq: int,
    span: str,
) -> ShowResult:
    """One controller-shaped show call; bumps expected_revision on applied
    (the host's dones +1 per wire commit). (Lineage: ime_g3_lab._show.)"""
    r = target.show(session, utterance, seq, rev_box[0], span)
    if r is ShowResult.APPLIED:
        rev_box[0] += 1
    return r


def _stable_dump(
    lab: Lab,
    expect_text: str,
    tag: str = "",
    seconds: float = 5.0,
    painted: bool = False,
) -> dict | None:
    """Wait until the editor's own dump shows the settled expected text (the
    field dump — NOT a signal count — is the visible-field witness).
    painted=True additionally requires the dump to be POST-PAINT
    (kind == "frame"). (Lineage: tests/ime_g3_lab.py _stable_dump.)"""

    def ok():
        f = _field(lab, tag)
        if f is None or f.get("text") != expect_text:
            return None
        if f.get("pos") != len(f.get("text", "")):
            return None
        if painted and f.get("kind") != "frame":
            return None
        return f

    return until(ok, seconds)


def _check_oracle(
    before: dict, after: dict, expect: str, bad: list[str], ev: dict, key: str = ""
) -> dict:
    a = single_edit_analysis(before, after, expect=expect)
    ev[f"{key}oracle" if key else "oracle"] = {
        k: a[k] for k in ("frames", "transitions", "transient_hashes", "painted_final")
    }
    if not a["ok"]:
        bad.append(f"{key}oracle-{expect}" if key else f"oracle-{expect}")
    return a


# --- the browser witness: in-lab push server -------------------------------------


class PushServer:
    """threading http.server on 127.0.0.1:0 (ephemeral). POST /push → 204 +
    Access-Control-Allow-Origin:* (file:// origin = null — the text/plain
    simple request avoids preflight). Bounded store: ≤256 pushes × ≤8 KiB
    (tmpfs = RAM — AGENTS.md Rule 3)."""

    MAX_BODY = 8192

    def __init__(self):
        self.items: collections.deque = collections.deque(maxlen=256)  # (mono, raw)
        self.total = 0
        self.dropped = 0
        store = self
        store_holder = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 — stdlib naming
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if self.path != "/push":
                    self.send_response(404)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    return
                if n <= 0 or n > store.MAX_BODY:
                    if n > store.MAX_BODY:
                        # bounded drain (never read an unbounded body into RAM)
                        remaining = n
                        while remaining > 0:
                            chunk = self.rfile.read(min(65536, remaining))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    store_holder.dropped += 1
                    self.send_response(413)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    return
                raw = self.rfile.read(n)
                store.items.append((time.monotonic(), raw))
                store.total += 1
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

            def log_message(self, *a) -> None:  # silence per-request stderr
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/push"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except OSError:
            pass

    def latest(self, since: float = 0.0) -> bytes | None:
        for t, raw in reversed(self.items):
            if t > since:
                return raw
        return None

    def all_states(self, since: float = 0.0) -> list[BrowserState]:
        out = []
        for _t, raw in self.items:
            if _t > since:
                try:
                    out.append(parse_push(raw))
                except ValueError:
                    continue
        return out


def _bstate(srv: PushServer, since: float = 0.0) -> BrowserState | None:
    raw = srv.latest(since)
    if raw is None:
        return None
    try:
        return parse_push(raw)
    except ValueError:
        return None


def _stable_bstate(
    srv: PushServer,
    expect_text: str,
    *,
    since: float = 0.0,
    seconds: float = 6.0,
    painted: bool = False,
    ro: bool | None = None,
) -> BrowserState | None:
    """Wait until the page's OWN push shows the settled expected value. The
    DOM text is the field's truth; painted=True requires the final value-hash
    in the rAF ring (visibility witnessed — not vacuous)."""

    def ok():
        s = _bstate(srv, since)
        if s is None or s.text != expect_text:
            return None
        if painted and fnv1a32(expect_text) not in s.frames:
            return None
        if ro is not None and s.readonly is not ro:
            return None
        return s

    return until(ok, seconds)


# --- the browser field app --------------------------------------------------------


def spawn_browser(
    lab: Lab, srv: PushServer, *, tag: str, readonly: bool = False
) -> sp.Popen:
    """Chromium in app mode: isolated temp-root profile (NEVER the real
    profile), IM-v2 flag set, the fixture URL with this run's push URL. First
    boot tries the sandboxed form; if the window never appears, ONE --no-
    sandbox retry INSIDE the disposable desktop (recorded)."""
    url = f"file://{FIXTURE}?push={srv.url}"
    if readonly:
        url += "&mode=ro"
    err_name = f"chromium-{tag}.err"
    profile = lab.root / f"chromium-profile-{tag}"
    argv = chromium_argv(profile, url)
    p = lab.spawn(argv, stderr_name=err_name)
    since = time.monotonic()
    state = _wait_browser_up(lab, srv, p, since, readonly)
    if state is None:
        lab.kill(p)
        lab.chromium_no_sandbox = True  # recorded; disposable desktop only
        argv = chromium_argv(profile, url, extra=("--no-sandbox",))
        p = lab.spawn(argv, stderr_name=err_name)
        since = time.monotonic()
        state = _wait_browser_up(lab, srv, p, since, readonly)
        if state is None:
            raise RuntimeError(
                f"chromium-{tag} never came up: {lab.err_head(err_name)}"
            )
    return p


def _wait_browser_up(
    lab: Lab, srv: PushServer, proc: sp.Popen, since: float, readonly: bool
) -> BrowserState | None:
    """First push received + the page's window present in the tree + process
    alive (cold Chromium is slow — bounded READY_S poll)."""

    def ok():
        if proc.poll() is not None:
            return None
        w = _browser_window(lab)
        if w is None:
            return None
        want = BROWSER_TITLE + ("-ro" if readonly else "")
        if not str(w.get("title") or "").startswith(want):
            return None
        return _bstate(srv, since)

    return until(ok, READY_S)


def focus_browser(lab: Lab, readonly: bool = False) -> None:
    # sway title criteria are regex (PCRE2); the fallback title is
    # "vtg3-browser[-ro]|{...}" — anchor on the base + literal pipe.
    pipe = r"\|"
    crit = f'[title="^{BROWSER_TITLE}{"-ro" if readonly else ""}{pipe}"]'
    lab.focus(crit)


# --- the takeover leg (shared by E6/B6) -------------------------------------------


def _injector_order(lab: "Lab") -> list[str]:
    """Bounded injector ladder, most-real first: uinput (ydotool — a REAL
    kernel input device through libinput, indistinguishable from physical
    keys), then xdotool XTEST into sway's X window (the im-lab recipe), then
    wtype (native Wayland virtual keyboard)."""
    order = []
    if (
        shutil.which("ydotool")
        and shutil.which("ydotoold")
        and os.access("/dev/uinput", os.R_OK | os.W_OK)
    ):
        order.append("ydotool")
    if XDOTOOL:
        order.append("xdotool")
    if WTYPE:
        order.append("wtype")
    return order


def _inject_real_key(lab: "Lab", which: str) -> str:
    """ONE real key (space, keycode 57) via the requested injector; returns a
    bounded diagnostic tag (never unbounded output)."""
    try:
        if which == "ydotool":
            sock = lab.root / "ydotoold.sock"
            if not hasattr(lab, "_ydotoold"):
                lab._ydotoold = lab.spawn(
                    ["ydotoold", "-p", str(sock)], stderr_name="ydotoold.err"
                )
            until(lambda: sock.exists(), 3)
            r = sp.run(
                ["ydotool", "-s", str(sock), "key", "57:1", "57:0"],
                stdin=sp.DEVNULL,
                stdout=sp.DEVNULL,
                stderr=sp.PIPE,
                env=lab.env,
                timeout=5,
            )
            return (
                f"ydotool(rc={r.returncode},"
                f"err={r.stderr.decode(errors='replace')[:60]!r})"
            )
        if which == "xdotool":
            win, name = "", ""
            wins = lab.cmd(
                [
                    "xdotool",
                    "search",
                    "--onlyvisible",
                    "--maxdepth",
                    "1",
                    "--name",
                    ".*",
                ],
                timeout=5,
            ).splitlines()
            if wins:
                win = wins[-1].decode().strip()
                lab.cmd(["xdotool", "windowfocus", win], timeout=5)
                name = lab.cmd(["xdotool", "getwindowname", win], timeout=5).decode(
                    errors="replace"
                )[:40]
            lab.cmd([XDOTOOL, "key", "--delay", "10", "space"], timeout=5)
            return f"xdotool(win={win or '?'},name={name!r})"
        if which == "wtype":
            r = sp.run(
                [WTYPE, " "],
                stdin=sp.DEVNULL,
                stdout=sp.DEVNULL,
                stderr=sp.PIPE,
                env=lab.env,
                timeout=5,
            )
            return (
                f"wtype(rc={r.returncode},"
                f"err={r.stderr.decode(errors='replace')[:60]!r})"
            )
    except (sp.TimeoutExpired, OSError) as e:
        return f"{which}(EXC={e!r:.80})"
    return f"{which}(unknown)"


def _takeover_leg(
    lab: Lab,
    proc: ImeProcess,
    target: ImeTarget,
    field_keys: callable,  # noqa: ANN001 — returns the app-side key counter
    field_text: callable,  # noqa: ANN001 — returns the app-side current text
    tag: str,
    bad: list[str],
    ev: dict,
) -> None:
    """Acquire NOTHING here — the caller owns the binding + owned fragment.
    Engage the host grab, drive ONE real key via xdotool into the PRIVATE
    display, feed the collected grab_key events into the REAL takeover
    machinery (TakeoverWatch: detector → target.leave() → ONE
    controller.halt_for_takeover — the R.5 revocation order), then assert:
    exactly one halt, reason 'user key <keycode>', the field's key counter
    FROZEN (the grab consumed the key), text unchanged, next op REFUSED."""
    lab.takeover_ran = True
    duck = _DuckController()
    marker = len(lab.events.items)
    grab_before = lab.events.count("grab_key")
    ev["grab_key_before"] = grab_before
    if lab.grab_keys_after_first_takeover is not None:
        # no grab_key may fire outside a takeover row (M4.T5.S1 invariant)
        if grab_before != lab.grab_keys_after_first_takeover:
            bad.append(f"{tag}-grab_key-outside-takeover")
    elif grab_before != 0:
        bad.append(f"{tag}-grab_key-before-first-takeover")
    keys_before = field_keys()
    text_before = field_text()
    g = proc.request("grab", timeout=2.5) or {}
    ev["grab_ok"] = g.get("ok")
    if not g.get("ok"):
        bad.append(f"{tag}-grab-refused ({g.get('reason')})")
        return
    ev["inject_attempts"] = []
    ev["injector"] = "none"

    def pump_got_key():
        # the host drains wire events only while handling stdin lines — every
        # ping FORCES a drain so asynchronously-arriving grab_key events reach
        # the collector (same pump principle as wait_activated)
        _ping(proc)
        return any(e.get("ev") == "grab_key" for e in list(lab.events.items)[marker:])

    for inj in _injector_order(lab):
        ev["inject_attempts"].append(_inject_real_key(lab, inj))
        if until(pump_got_key, 1.5) is not None:
            ev["injector"] = inj
            break
    if ev["injector"] == "none":
        bad.append(f"{tag}-no-grab_key-event")
    drain_until = time.monotonic() + 0.3  # the key RELEASE flows as grab_key too
    while time.monotonic() < drain_until:
        _ping(proc)
        time.sleep(0.05)
    events = list(lab.events.items)[marker:]
    ev["grab_key_events"] = sum(1 for e in events if e.get("ev") == "grab_key")
    watch = TakeoverWatch(target=target, controller=duck)
    for e in events:  # feed IN ORDER; the watch latches to ONE revocation
        watch.on_event(e)
    lab.grab_keys_after_first_takeover = lab.events.count("grab_key")
    ev["halt_reasons"] = list(duck.reasons)
    ev["watch_reason"] = watch.reason
    if duck.halts != 1:
        bad.append(f"{tag}-halt-count-{duck.halts}")
    if not (watch.reason or "").startswith("user key"):
        bad.append(f"{tag}-halt-reason")
    if field_keys() != keys_before:
        bad.append(f"{tag}-field-keys-moved")  # the grab consumed the key
    if field_text() != text_before:
        bad.append(f"{tag}-field-text-changed")
    r = target.show(9, f"{tag}-after", 1, 0, "must not land")
    ev["post_takeover"] = r.name
    if r is not ShowResult.REFUSED:
        bad.append(f"{tag}-post-takeover-not-refused")


# --- editor rows E1–E6 ------------------------------------------------------------


def row_e1_short_updates(lab: Lab, proc: ImeProcess, payloads) -> dict:
    """E1: 6 short inserts (growing span, INSERT path, delta-only wire)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    insert_ok = None
    try:
        lab.focus(f'[title="{EDITOR_TITLE}"]')
        if not wait_activated(proc):
            lab.verdict(
                "editor-short-updates",
                None,
                reason="input method never activated",
                stderr=lab.err_head("gtk.err"),
                **ev,
            )
            return {
                "row": "e1",
                "ok": None,
                "insert_ok": None,
                "correction_ok": None,
                "reason": "never activated",
            }
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "editor-short-updates", False, error=f"acquire refused: {a.reason!r}"
            )
            return {"row": "e1", "ok": False, "checks": ("acquire",)}
        rev = [a.revision]
        before = _field(lab)
        expected = ""
        dones = _ping(proc)["dones"]
        for i, span in enumerate(payloads["short"], start=1):
            expected = span  # cumulative — payloads["short"] IS the growing list
            r = _show(target, rev, 1, "e1", i, span)
            if r is not ShowResult.APPLIED:
                bad.append(f"op{i}-not-applied")
                ev[f"op{i}"] = r.name
                break
            after = _stable_dump(lab, expected, painted=True)
            if after is None:
                bad.append(f"op{i}-never-settled")
                break
            if after["text"].encode("utf-8") != expected.encode("utf-8"):
                bad.append(f"op{i}-byte-exact")
            if after["pos"] != len(after["text"]):
                bad.append(f"op{i}-cursor-end")
            if not 1 <= after["cseq"] - before["cseq"] <= 2:
                bad.append(f"op{i}-cseq-delta")
            _check_oracle(before, after, "change", bad, ev)
            d2 = _ping(proc)["dones"]
            ev[f"op{i}_dones"] = d2 - dones
            if d2 - dones < 1:
                bad.append(f"op{i}-wire-commits")
            dones = d2
            before = after
        if not bad:
            v = _verify_snapshot(proc)
            ev["verify_bytes"] = v.get("bytes")
            if (v.get("text") or "").encode("utf-8") != expected.encode("utf-8"):
                bad.append("target-confirmed-text")
            insert_ok = True
        ok = not bad
        lab.verdict(
            "editor-short-updates",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            ops=len(payloads["short"]),
            shot=lab.shot("e1"),
            **ev,
        )
        target.leave()
        return {
            "row": "e1",
            "ok": ok,
            "insert_ok": insert_ok,
            "correction_ok": None,
            "checks": tuple(bad),
        }
    except Exception as e:  # noqa: BLE001 — one bad row never kills the run
        lab.verdict("editor-short-updates", None, error=repr(e))
        return {"row": "e1", "ok": None, "reason": repr(e)[:80]}


def row_e2_firstword(lab: Lab, proc: ImeProcess, payloads) -> ImeTarget | None:
    """E2: insert the committed 20-sentence span, then correct its FIRST word
    via ONE atomic replacement (the CORRECTION path). Returns the still-bound
    target for E3 (the zero-diff law needs the same acquisition)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "editor-firstword-20sent", False, error=f"acquire refused: {a.reason!r}"
            )
            return None
        binding: FieldBinding = a.handle
        rev = [a.revision]
        committed = payloads["twenty_committed"]
        corrected = payloads["twenty_corrected"]
        pre = _f.get("text", "") if (_f := _field(lab)) else ""
        expected_insert = pre + committed
        before = _stable_dump(lab, pre)
        r = _show(target, rev, 2, "e2", 1, committed)  # INSERT path
        if r is not ShowResult.APPLIED:
            lab.verdict(
                "editor-firstword-20sent",
                False,
                error=f"20-sentence insert not applied: {r.name}",
                reason=target.last_reason,
            )
            target.leave()
            return None
        after = _stable_dump(lab, expected_insert, painted=True)
        if after is None:
            lab.verdict(
                "editor-firstword-20sent",
                False,
                error="field never settled after 20-sentence insert",
            )
            target.leave()
            return None
        _check_oracle(before, after, "change", bad, ev)
        if after["text"].encode("utf-8") != expected_insert.encode("utf-8"):
            bad.append("insert-byte-exact")
        ev["span_bytes"] = len(committed.encode("utf-8"))
        # pre-op recheck (R.5): with OUR cumulative inserted bytes (the insert
        # moved the caret; inserted_bytes=0 would spuriously say "caret moved")
        ok_rc, why_rc, _rev = target.recheck(binding, target._inserted_bytes)
        ev["recheck"] = "ok" if ok_rc else f"refused ({why_rc})"
        if not ok_rc:
            bad.append("pre-op-recheck")
        dones = _ping(proc)["dones"]
        before = after
        expected_corrected = pre + corrected
        r = _show(target, rev, 2, "e2", 2, corrected)  # CORRECTION path
        correction_ok = None
        if r is not ShowResult.APPLIED:
            bad.append("correction-not-applied")
            ev["correction"] = f"{r.name} ({target.last_reason})"
        else:
            after = _stable_dump(lab, expected_corrected, painted=True)
            if after is None:
                bad.append("correction-never-settled")
            else:
                if after["text"].encode("utf-8") != expected_corrected.encode("utf-8"):
                    bad.append("correction-byte-exact")
                if after["pos"] != len(after["text"]):
                    bad.append("correction-cursor-end")
                if not 1 <= after["cseq"] - before["cseq"] <= 2:
                    bad.append("correction-cseq-delta")
                _check_oracle(before, after, "change", bad, ev)
                d2 = _ping(proc)["dones"]
                ev["correction_dones"] = d2 - dones
                if d2 - dones < 1:
                    bad.append("correction-wire-commits")
                correction_ok = not any(b.startswith("correction") for b in bad)
        if not _verify_agrees(proc, expected_corrected, ev):
            bad.append("target-confirmed-text")
        ok = not bad
        lab.verdict(
            "editor-firstword-20sent",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            shot=lab.shot("e2"),
            correction_ok=correction_ok,
            **ev,
        )
        if not ok:
            target.leave()
            return None
        return target  # E3 continues this acquisition
    except Exception as e:  # noqa: BLE001
        lab.verdict("editor-firstword-20sent", None, error=repr(e))
        return None


def row_e3_identical_finals(
    lab: Lab, proc: ImeProcess, target: ImeTarget | None, payloads
) -> dict:
    """E3: the same final span show()n 3x — UNCHANGED each, zero events, zero
    edits, zero frame transitions. CONTINUES E2's acquisition (the zero-diff
    guard only hits while the same binding owns the span)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        if target is None:
            lab.verdict(
                "editor-identical-finals",
                None,
                reason="skipped (E2 did not leave a bound target)",
            )
            return {"row": "e3", "ok": None, "reason": "no bound target"}
        span = payloads["twenty_corrected"]
        before = _field(lab)
        dones = _ping(proc)["dones"]
        results = []
        for i in range(3):
            r = target.show(2, "e2", 10 + i, _rev_for(proc, target), span)
            results.append(r.name)
            if r is not ShowResult.UNCHANGED:
                bad.append(f"repeat{i}-not-unchanged")
        after = _field(lab)
        d2 = _ping(proc)["dones"]
        if after is None or before is None:
            bad.append("field-dump-missing")
        else:
            if after["cseq"] != before["cseq"]:
                bad.append("cseq-delta-nonzero")
            if after["text"].encode("utf-8") != before["text"].encode("utf-8"):
                bad.append("text-changed")
            _check_oracle(before, after, "noop", bad, ev)
        if d2 != dones:
            bad.append("wire-commits-nonzero")  # identical ⇒ ZERO events
        ev["results"] = results
        ev["dones_before"], ev["dones_after"] = dones, d2
        ok = not bad
        lab.verdict(
            "editor-identical-finals",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        target.leave()
        return {
            "row": "e3",
            "ok": ok,
            "insert_ok": None,
            "correction_ok": None,
            "checks": tuple(bad),
        }
    except Exception as e:  # noqa: BLE001
        lab.verdict("editor-identical-finals", None, error=repr(e))
        return {"row": "e3", "ok": None, "reason": repr(e)[:80]}


def _show_settled(
    proc: ImeProcess,
    target: ImeTarget,
    rev_box: list[int],
    session: int,
    utterance: str,
    seq: int,
    span: str,
    *,
    ev: dict,
    key: str,
) -> ShowResult:
    """One show; on a REFUSED whose reason is the adapter's caret guard racing
    Chromium's ASYNCHRONOUS surrounding_text updates (the measured cadence
    fact — the snapshot can lag the just-committed DOM value by a frame), wait
    a bounded settle while pumping pings (each forces a host event drain),
    then re-show ONCE. A refused op was declined PRE-wire — the field never
    changed — so the re-show is not an R.5 retry of a possibly-landed op (that
    rule is for UNKNOWN). Both attempts stay in the evidence."""
    r = _show(target, rev_box, session, utterance, seq, span)
    if r is ShowResult.REFUSED and str(target.last_reason).startswith("recheck:"):
        ev[f"{key}_first"] = f"REFUSED ({target.last_reason})"
        deadline = time.monotonic() + 0.35
        while time.monotonic() < deadline:
            _ping(proc)
            time.sleep(0.05)
        r = _show(target, rev_box, session, utterance, seq, span)
        ev[f"{key}_resettled"] = r.name
    return r


def _rev_for(proc: ImeProcess, target: ImeTarget) -> int:
    """A revision satisfying the no-regression guard: the binding's revision
    floor. (Lineage: ime_g3_lab._rev_for.)"""
    binding = target._binding
    return binding.revision if binding is not None else int(_ping(proc)["dones"])


def row_e4_long_unicode(lab: Lab, proc: ImeProcess, payloads) -> dict:
    """E4: (a) 951 B Unicode insert; (b) ~3.5 KB mixed extension; (c) >4 KB
    REFUSED at the 4000 B commit cap — never chunked, field untouched."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    subs = []
    insert_ok = None
    try:
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "editor-long-unicode", False, error=f"acquire refused: {a.reason!r}"
            )
            return {"row": "e4", "ok": False, "checks": ("acquire",)}
        rev = [a.revision]
        pre = _f.get("text", "") if (_f := _field(lab)) else ""
        unicode_ = payloads["unicode_951b"]
        mixed = payloads["mixed_3500b"]
        overcap = payloads["overcap_4500b"]
        # (a) 951 B multilingual insert
        before = _stable_dump(lab, pre, painted=True)
        r = _show(target, rev, 4, "e4", 1, unicode_)
        if r is not ShowResult.APPLIED:
            bad.append("unicode-951b-not-applied")
            ev["a"] = f"{r.name} ({target.last_reason})"
        else:
            after = _stable_dump(lab, pre + unicode_, painted=True)
            if after is None or after["text"].encode("utf-8") != (
                pre + unicode_
            ).encode("utf-8"):
                bad.append("unicode-951b-byte-exact")
            elif not 1 <= after["cseq"] - before["cseq"] <= 2:
                bad.append("unicode-951b-cseq-delta")
            else:
                _check_oracle(before, after, "change", bad, ev)
            subs.append(
                (
                    "unicode-951b",
                    "FAIL" if any(b.startswith("unicode-951b") for b in bad) else "ok",
                )
            )
        # (b) ~3.5 KB mixed extension of the owned span
        before = _field(lab)  # settled post-(a) — never an unbound-variable read
        span_b = unicode_ + mixed
        r = _show(target, rev, 4, "e4", 2, span_b)
        if r is not ShowResult.APPLIED:
            bad.append("mixed-3500b-not-applied")
            ev["b"] = f"{r.name} ({target.last_reason})"
        else:
            expected_b = pre + span_b
            after = _stable_dump(lab, expected_b, painted=True)
            if after is None or after["text"].encode("utf-8") != expected_b.encode(
                "utf-8"
            ):
                bad.append("mixed-3500b-byte-exact")
            elif not 1 <= after["cseq"] - before["cseq"] <= 2:
                bad.append("mixed-3500b-cseq-delta")
            else:
                _check_oracle(before, after, "change", bad, ev)
            subs.append(
                (
                    "mixed-3500b",
                    "FAIL" if any(b.startswith("mixed-3500b") for b in bad) else "ok",
                )
            )
        # (c) >4 KB — REFUSED by design, field untouched (behavior row PASSES)
        before = _field(lab)
        dones = _ping(proc)["dones"]
        r = _show(target, rev, 4, "e4", 3, span_b + overcap)
        overcap_ok = True
        if r is not ShowResult.REFUSED:
            bad.append("overcap-not-refused")  # refused, NEVER chunked
            ev["c"] = r.name
            overcap_ok = False
        else:
            after = _field(lab)
            if after is None or before is None:
                bad.append("overcap-field-dump-missing")
                overcap_ok = False
            else:
                if after["cseq"] != before["cseq"] or after["text"].encode(
                    "utf-8"
                ) != before["text"].encode("utf-8"):
                    bad.append("overcap-field-touched")
                    overcap_ok = False
                _check_oracle(before, after, "noop", bad, ev)
            if _ping(proc)["dones"] != dones:
                bad.append("overcap-wire-commits")
                overcap_ok = False
            ev["overcap_bytes"] = len((span_b + overcap).encode("utf-8"))
            subs.append(
                ("overcap-4500b", "refused-by-design" if overcap_ok else "FAIL")
            )
        if not bad[:]:
            if not _verify_agrees(proc, pre + span_b, ev):
                bad.append("target-confirmed-text")
        if not any(
            b.endswith(("not-applied", "byte-exact", "never-settled")) for b in bad
        ):
            insert_ok = True
        ev["subrows"] = subs
        ok = not bad
        lab.verdict(
            "editor-long-unicode",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            shot=lab.shot("e4"),
            **ev,
        )
        target.leave()
        # capability sub-row (report only — the behavior row itself passed)
        lab.report_rows.append(
            {
                "id": "editor-overcap-4500b (capability sub-row)",
                "title": ">4000 B delivery capability",
                "passed": None,
                "status": OVERCAP_BLOCKED_REASON
                if overcap_ok
                else "blocked (overcap behavior FAILED)",
                "evidence": ["refused pre-wire, never chunked; field untouched"],
            }
        )
        return {
            "row": "e4",
            "ok": ok,
            "insert_ok": insert_ok,
            "correction_ok": None,
            "checks": tuple(bad),
        }
    except Exception as e:  # noqa: BLE001
        lab.verdict("editor-long-unicode", None, error=repr(e))
        return {"row": "e4", "ok": None, "reason": repr(e)[:80]}


def row_e5_refusing_readonly(lab: Lab, proc: ImeProcess, payloads) -> dict:
    """E5: the editor app booted non-editable. Whatever branch the platform
    takes (activation refused / acquire refused / show refused / applied-but-
    ignored), NO visible edit may land; the ACTUAL branch is recorded. Then a
    fresh WRITABLE view takes one insert — the adapter-not-wedged witness."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        if lab.field_proc is not None and lab.field_proc.poll() is None:
            lab.kill(lab.field_proc)  # remove the writable view: focus unambiguous
        wait_deactivated(proc)
        ro = spawn_field_edit(lab, tag="ro", readonly=True)
        lab.focus(f'[title="{EDITOR_TITLE}-ro"]')

        def _focused_ro():
            t = _focused_title(lab)
            return t if t is not None and t.endswith("-ro") else None

        focused = until(_focused_ro, 3)
        ev["focused"] = focused
        branch = ""
        if focused is None or not focused.endswith("-ro"):
            lab.verdict(
                "editor-refusing-readonly",
                None,
                reason=f"readonly field never got focus (focused={focused!r})",
                stderr=lab.err_head("gtk-ro.err"),
                **ev,
            )
            lab.kill(ro)
            return {"row": "e5", "ok": None, "reason": "no focus"}
        if not wait_activated(proc):
            # GTK disables the input method for a non-editable view — the
            # refusing behavior manifests at ACTIVATION level. Record the
            # branch and prove the adapter recovers below; never a silent skip.
            branch = "activation-refused (non-editable view never enabled text-input)"
        else:
            target = ImeTarget(proc)
            a = target.acquire()
            if not a.ok:
                branch = f"acquire-refused ({a.reason})"
            else:
                before = _field(lab, "ro")
                r = _show(target, [a.revision], 5, "e5", 1, "must not land")
                if r is ShowResult.APPLIED:
                    after = _stable_dump(
                        lab, before["text"] if before else "", "ro", seconds=1.5
                    ) or _field(lab, "ro")
                    unchanged = (
                        after is not None
                        and before is not None
                        and after["text"].encode("utf-8")
                        == before["text"].encode("utf-8")
                        and after["cseq"] == before["cseq"]
                    )
                    branch = (
                        "applied-but-ignored-by-field"
                        if unchanged
                        else "applied-and-FIELD-CHANGED"
                    )
                    if not unchanged:
                        bad.append("readonly-field-changed")
                    elif before is not None:
                        _check_oracle(before, after, "noop", bad, ev)
                elif r is ShowResult.REFUSED:
                    branch = f"show-refused ({target.last_reason})"
                elif r is ShowResult.UNKNOWN:
                    branch = "show-unknown (host never saw the compositor done)"
                else:
                    branch = "show-unchanged"
                target.leave()
        after = _field(lab, "ro")
        ev["branch"] = branch
        if after is not None and after.get("keys", 0) != 0:
            bad.append("readonly-field-saw-keys")
        # --- recovery witness: a fresh WRITABLE view takes one insert ------
        lab.kill(ro)
        wait_deactivated(proc)
        spawn_field_edit(lab, tag="w2")
        lab.focus(
            f'[title="{EDITOR_TITLE}"]'  # the only field window now (ro killed)
        )
        if not wait_activated(proc):
            bad.append("recovery-field-never-activated")
        else:
            t2 = ImeTarget(proc)
            a2 = t2.acquire()
            if not a2.ok:
                bad.append(f"recovery-acquire-refused ({a2.reason})")
            else:
                r2 = _show(t2, [a2.revision], 5, "e5", 2, "recovered.")
                if r2 is not ShowResult.APPLIED:
                    bad.append(f"recovery-insert-not-applied ({r2.name})")
                elif _stable_dump(lab, "recovered.", "w2", painted=True) is None:
                    bad.append("recovery-never-settled")
                ev["recovery"] = r2.name
            t2.leave()
        ok = not bad
        lab.verdict(
            "editor-refusing-readonly",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        return {"row": "e5", "ok": ok, "branch": branch, "checks": tuple(bad)}
    except Exception as e:  # noqa: BLE001
        lab.verdict("editor-refusing-readonly", None, error=repr(e))
        return {"row": "e5", "ok": None, "reason": repr(e)[:80]}


def row_e6_takeover(lab: Lab, proc: ImeProcess) -> dict:
    """E6: REAL key mid-owned-fragment on the writable E5-recovery view:
    grab → xdotool space → grab_key events → TakeoverWatch → EXACTLY one
    halt_for_takeover → next op refused → field counters frozen."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        lab.focus(f'[title="{EDITOR_TITLE}"]')  # w2 is the only field window left
        if not wait_activated(proc):
            lab.verdict(
                "editor-takeover", None, reason="recovery view never activated", **ev
            )
            return {"row": "e6", "ok": None, "reason": "no activation"}
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "editor-takeover", False, error=f"acquire refused: {a.reason!r}"
            )
            return {"row": "e6", "ok": False, "checks": ("acquire",)}
        rev = [a.revision]
        r = _show(target, rev, 6, "e6", 1, "owned fragment; ")
        if r is not ShowResult.APPLIED:
            lab.verdict(
                "editor-takeover", False, error=f"owned insert not applied: {r.name}"
            )
            target.leave()
            return {"row": "e6", "ok": False, "checks": ("owned-insert",)}
        if _stable_dump(lab, "recovered.owned fragment; ", "w2", painted=True) is None:
            lab.verdict("editor-takeover", False, error="owned insert never settled")
            target.leave()
            return {"row": "e6", "ok": False, "checks": ("owned-insert-settle",)}

        def field_keys():
            f = _field(lab, "w2")
            return None if f is None else f.get("keys")

        def field_text():
            f = _field(lab, "w2")
            return None if f is None else f.get("text")

        _takeover_leg(lab, proc, target, field_keys, field_text, "e6", bad, ev)
        ev["shot"] = lab.shot("e6")
        ok = not bad
        lab.verdict(
            "editor-takeover",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        return {"row": "e6", "ok": ok, "checks": tuple(bad)}
    except Exception as e:  # noqa: BLE001
        lab.verdict("editor-takeover", None, error=repr(e))
        return {"row": "e6", "ok": None, "reason": repr(e)[:80]}


# --- browser rows B1–B6 ------------------------------------------------------------


def _browser_cursor_utf16(exp_text: str) -> int:
    """Expected DOM caret (UTF-16 units) — via bulk_delivery.map_span ONLY
    (never len(); astral chars count 2). Caret sits at the end."""
    n = len(exp_text)
    return map_span(exp_text, n, n, TargetUnits.UTF16_UNITS)[0]


def _law_check(
    s0: BrowserState,
    s2: BrowserState,
    expect: str,
    exp_text: str,
    bad: list[str],
    ev: dict,
    key: str,
) -> None:
    law = input_event_law(s0, s2, expect=expect, exp_text=exp_text)
    ev[f"{key}_law"] = {
        k: law[k]
        for k in ("dn", "transitions", "transient", "painted_final", "underflow")
    }
    if not law["ok"]:
        bad.append(f"{key}-event-law")


def _browser_row_wrap(lab, row_id, fn, *args):
    try:
        return fn(lab, *args)
    except Exception as e:  # noqa: BLE001
        lab.verdict(row_id, None, error=repr(e))
        return {"row": row_id[:2], "ok": None, "reason": repr(e)[:80]}


def row_b1_short_updates(lab, proc, srv, payloads) -> dict:  # noqa: ANN001
    """B1: 6 short inserts into the real DOM input — the page's OWN pushes."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    insert_ok = None
    try:
        focus_browser(lab)
        if not wait_activated(proc):
            lab.verdict(
                "browser-short-updates",
                None,
                reason="text-input never activated for the DOM input (focus+autofocus "
                "were verified; chromium text-input-v3 activation is the "
                "measured fact)",
                stderr=lab.err_head("chromium-b1.err"),
                window=_browser_window(lab),
                title_state=parse_title(
                    _browser_window(lab).get("title") if _browser_window(lab) else None
                ),
                **ev,
            )
            return {
                "row": "b1",
                "ok": None,
                "insert_ok": None,
                "correction_ok": None,
                "reason": "never activated",
                "blocked_reason": (
                    "chromium text-input-v3 never activated for the DOM input "
                    "(sway window focus + page autofocus verified first)"
                ),
            }
        s0 = _stable_bstate(srv, "")
        if s0 is None:
            lab.verdict(
                "browser-short-updates", False, error="field never pushed empty state"
            )
            return {"row": "b1", "ok": False, "checks": ("first-state",)}
        expected = ""
        tgt: ImeTarget | None = None
        rev = [0]
        for i, span in enumerate(payloads["short"], start=1):
            expected = span
            s0 = _bstate(srv)
            cur = s0.text if s0 else ""
            # Per-utterance binding (the delivery model's acquire cycle): each
            # short update is ONE acquire + ONE delta-append; the measured
            # one-acquisition multi-op caret-guard refusal is B4(b)'s row.
            if tgt is None:
                tgt = ImeTarget(proc)
                a = tgt.acquire()
                if not a.ok:
                    bad.append(f"op{i}-acquire-refused ({a.reason})")
                    break
                rev = [a.revision]
            delta = expected[len(cur) :] if expected.startswith(cur) else span
            r = _show_settled(
                proc, tgt, rev, 1, f"b1-{i}", i, delta, ev=ev, key=f"op{i}"
            )
            if r is not ShowResult.APPLIED:
                bad.append(f"op{i}-not-applied")
                ev[f"op{i}"] = f"{r.name} ({tgt.last_reason})"
                break
            s2 = _stable_bstate(srv, expected, painted=True)
            if s2 is None:
                bad.append(f"op{i}-never-settled")
                break
            if s2.text.encode("utf-8") != expected.encode("utf-8"):
                bad.append(f"op{i}-byte-exact")
            caret = _browser_cursor_utf16(expected)
            if (s2.sel_start, s2.sel_end) != (caret, caret):
                bad.append(f"op{i}-cursor-utf16")
                ev[f"op{i}_sel"] = [s2.sel_start, s2.sel_end, caret]
            _law_check(s0, s2, "change", expected, bad, ev, f"op{i}")
            if s2.k != 0:
                bad.append(f"op{i}-page-keydowns")
            s0 = s2
            tgt.leave()
            tgt = None
        if not bad:
            _browser_verify(
                proc,
                payloads["short"][4],  # field value BEFORE the last commit
                ev,
                bad,
                "b1",
                current_expected=expected,
            )
            insert_ok = True
        ev["binding"] = "fresh-acquire per op (per-utterance cadence)"
        ok = not bad
        lab.verdict(
            "browser-short-updates",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            ops=len(payloads["short"]),
            shot=lab.shot("b1"),
            channel=("push" if srv.total else "title-fallback"),
            **ev,
        )
        return {
            "row": "b1",
            "ok": ok,
            "insert_ok": insert_ok,
            "correction_ok": None,
            "checks": tuple(bad),
        }
    except Exception as e:  # noqa: BLE001
        lab.verdict("browser-short-updates", None, error=repr(e))
        return {"row": "b1", "ok": None, "reason": repr(e)[:80]}


def row_b2_firstword(lab, proc, srv, payloads) -> tuple[ImeTarget | None, dict]:
    """B2: insert the 20-sentence span, then correct its FIRST word. The
    correction branch is RECORDED, never assumed: applied → verified-path
    evidence; refused (owned-region check needs surrounding_text) → the
    exact reason becomes the class's insert-only evidence."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    info = {"row": "b2", "ok": None, "insert_ok": None, "correction_ok": None}
    try:
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "browser-firstword-20sent",
                False,
                error=f"acquire refused: {a.reason!r}",
            )
            info["ok"] = False
            info["checks"] = ("acquire",)
            return None, info
        binding: FieldBinding = a.handle
        rev = [a.revision]
        committed = payloads["twenty_committed"]
        corrected = payloads["twenty_corrected"]
        s_pre = _bstate(srv)
        pre = s_pre.text if s_pre else ""
        before = _stable_bstate(srv, pre)
        r = _show(target, rev, 2, "b2", 1, committed)  # INSERT path
        if r is not ShowResult.APPLIED:
            lab.verdict(
                "browser-firstword-20sent",
                False,
                error=f"20-sentence insert not applied: {r.name}",
                reason=target.last_reason,
            )
            info["ok"] = False
            info["checks"] = ("insert-not-applied",)
            target.leave()
            return None, info
        s_ins = _stable_bstate(srv, pre + committed, painted=True)
        if s_ins is None:
            lab.verdict(
                "browser-firstword-20sent",
                False,
                error="field never settled after insert",
            )
            info["ok"] = False
            info["checks"] = ("insert-settle",)
            target.leave()
            return None, info
        _law_check(before, s_ins, "change", pre + committed, bad, ev, "insert")
        caret = _browser_cursor_utf16(pre + committed)
        if (s_ins.sel_start, s_ins.sel_end) != (caret, caret):
            bad.append("insert-cursor-utf16")
            ev["insert_sel"] = [s_ins.sel_start, s_ins.sel_end, caret]
        ev["span_bytes"] = len(committed.encode("utf-8"))
        # pre-op recheck (R.5) — with OUR cumulative inserted bytes
        ok_rc, why_rc, _rev2 = target.recheck(binding, target._inserted_bytes)
        if not ok_rc and "recheck" in str(why_rc):
            # the measured cadence race: settle for Chromium's async caret
            # update to flush, then recheck once more (read-only, no wire)
            ev["recheck_first"] = f"refused ({why_rc})"
            deadline = time.monotonic() + 0.35
            while time.monotonic() < deadline:
                _ping(proc)
                time.sleep(0.05)
            ok_rc, why_rc, _rev2 = target.recheck(binding, target._inserted_bytes)
        ev["recheck"] = "ok" if ok_rc else f"refused ({why_rc})"
        if not ok_rc:
            # the MEASURED class limitation, not a harness failure: the
            # adapter's caret guard reads a surrounding_text snapshot that
            # lags the just-committed value — record it as the correction
            # blocker; the honest refusal is the row's data (R.5 safe: the
            # guard refused PRE-wire, the field keeps the committed span)
            ev["recheck_note"] = (
                "surrounding_text snapshot lags the committed value at this "
                "chromium — the caret guard cannot confirm ownership"
            )
            info["correction_ok"] = False
            info["reason"] = (
                "correction blocked: caret guard refused recheck "
                f"({why_rc}) — snapshot lags committed value"
            )
        expected_after_correction = pre + corrected
        s2 = _bstate(srv)
        r = _show_settled(
            proc, target, rev, 2, "b2", 2, corrected, ev=ev, key="correction"
        )  # CORRECTION path
        if r is ShowResult.APPLIED:
            s_corr = _stable_bstate(srv, expected_after_correction, painted=True)
            if s_corr is None:
                bad.append("correction-never-settled")
            else:
                _law_check(
                    s2,
                    s_corr,
                    "change",
                    expected_after_correction,
                    bad,
                    ev,
                    "correction",
                )
                caret = _browser_cursor_utf16(expected_after_correction)
                if (s_corr.sel_start, s_corr.sel_end) != (caret, caret):
                    bad.append("correction-cursor-utf16")
            ev["correction_branch"] = "applied"
            info["correction_ok"] = not any(b.startswith("correction") for b in bad)
        else:
            # honest branch: record EXACTLY what happened and why
            ev["correction_branch"] = f"{r.name} ({target.last_reason})"
            ev["correction_note"] = (
                "correction refused — the adapter's owned-region check "
                "(_owned_region_intact) needs surrounding_text; the DOM field "
                "kept the committed (misspelled) span"
            )
            info["correction_ok"] = False
            info["correction_ok"] = False
            info["reason"] = (
                f"correction {r.name} ({target.last_reason}) — the "
                "surrounding_text snapshot lags the committed value at this "
                "chromium, so the adapter's owned-region precheck cannot confirm"
            )
        _browser_verify(
            proc,
            pre,  # field value BEFORE the last commit (B2's insert)
            ev,
            bad,
            "b2",
            current_expected=(
                expected_after_correction
                if r is ShowResult.APPLIED
                else pre + committed
            ),
        )
        ok = not bad
        lab.verdict(
            "browser-firstword-20sent",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            shot=lab.shot("b2"),
            **ev,
        )
        info["ok"] = ok
        info["insert_ok"] = True if ok else None
        info["checks"] = tuple(bad)
        if not ok:
            target.leave()
            return None, info
        return target, info  # B3 continues this acquisition
    except Exception as e:  # noqa: BLE001
        lab.verdict("browser-firstword-20sent", None, error=repr(e))
        info["ok"] = None
        info["reason"] = repr(e)[:80]
        return None, info


def row_b3_identical_finals(lab, proc, srv, target) -> dict:  # noqa: ANN001
    """B3: the currently-APPLIED span show()n 3x — UNCHANGED, ZERO input
    events, value hash unchanged. (Adaptive span: if B2's correction was
    honestly refused, the applied span is the committed text — the zero-diff
    law still measured on the class's own truth.)"""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        if target is None:
            lab.verdict(
                "browser-identical-finals",
                None,
                reason="skipped (B2 did not leave a bound target)",
            )
            return {"row": "b3", "ok": None, "reason": "no bound target"}
        span = target._last_applied_span
        drain_until = time.monotonic() + 0.35  # caret update flush before repeats
        while time.monotonic() < drain_until:
            _ping(proc)
            time.sleep(0.05)
        s0 = _bstate(srv)
        dones = _ping(proc)["dones"]
        results = []
        refused = 0
        for i in range(3):
            r = target.show(2, "b2", 10 + i, _rev_for(proc, target), span)
            results.append(r.name)
            if r is not ShowResult.UNCHANGED:
                if r is ShowResult.REFUSED and str(target.last_reason).startswith(
                    "recheck:"
                ):
                    refused += 1
                bad.append(f"repeat{i}-not-unchanged")
        if refused == 3:
            # the zero-diff law is UNMEASURABLE on this binding: every repeat
            # was refused PRE-wire by the caret guard (snapshot lag) — nothing
            # diverged, so this is honest infra-data, never a pass
            lab.verdict(
                "browser-identical-finals",
                None,
                reason=(
                    "all three repeats refused by the caret guard "
                    f"({target.last_reason}) — surrounding_text snapshot lags "
                    "the committed value; zero-diff law unmeasurable on one "
                    "acquisition"
                ),
                results=results,
                t_ms=int((time.monotonic() - t0) * 1000),
                **ev,
            )
            target.leave()
            return {
                "row": "b3",
                "ok": None,
                "reason": "caret guard refused repeats (snapshot lag)",
            }
        s3 = _bstate(srv)
        d2 = _ping(proc)["dones"]
        if s3 is None or s0 is None:
            bad.append("page-state-missing")
        else:
            _law_check(s0, s3, "noop", s0.text, bad, ev, "noop")
            if s3.text.encode("utf-8") != s0.text.encode("utf-8"):
                bad.append("text-changed")
        if d2 != dones:
            bad.append("wire-commits-nonzero")
        ev["results"] = results
        ev["dones_before"], ev["dones_after"] = dones, d2
        ok = not bad
        lab.verdict(
            "browser-identical-finals",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        target.leave()
        return {"row": "b3", "ok": ok, "checks": tuple(bad)}
    except Exception as e:  # noqa: BLE001
        lab.verdict("browser-identical-finals", None, error=repr(e))
        return {"row": "b3", "ok": None, "reason": repr(e)[:80]}


def row_b4_long_unicode(lab, proc, srv, payloads) -> dict:  # noqa: ANN001
    """B4: (a) 951 B Unicode insert; (b) ~3.5 KB mixed extension; (c) >4 KB
    REFUSED at the cap — field untouched (Δn = 0, value hash unchanged)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    subs = []
    insert_ok = None
    try:
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "browser-long-unicode", False, error=f"acquire refused: {a.reason!r}"
            )
            return {"row": "b4", "ok": False, "checks": ("acquire",)}
        rev = [a.revision]
        s_pre = _bstate(srv)
        pre = s_pre.text if s_pre else ""
        unicode_ = payloads["unicode_951b"]
        mixed = payloads["mixed_3500b"]
        overcap = payloads["overcap_4500b"]
        # (a) 951 B multilingual insert
        before = _stable_bstate(srv, pre, painted=True)
        r = _show(target, rev, 4, "b4", 1, unicode_)
        if r is not ShowResult.APPLIED:
            bad.append("unicode-951b-not-applied")
            ev["a"] = f"{r.name} ({target.last_reason})"
        else:
            after = _stable_bstate(srv, pre + unicode_, painted=True)
            if after is None or after.text.encode("utf-8") != (pre + unicode_).encode(
                "utf-8"
            ):
                bad.append("unicode-951b-byte-exact")
            else:
                _law_check(before, after, "change", pre + unicode_, bad, ev, "unicode")
            subs.append(
                (
                    "unicode-951b",
                    "FAIL" if any(b.startswith("unicode-951b") for b in bad) else "ok",
                )
            )
        # (b) ~3.5 KB mixed extension
        before = _bstate(srv)
        span_b = unicode_ + mixed
        expected_b = pre + span_b
        applied_b = False
        r = _show_settled(proc, target, rev, 4, "b4", 2, span_b, ev=ev, key="b")
        if r is not ShowResult.APPLIED:
            # the measured one-acquisition multi-op limitation: the extension
            # of the owned span beyond ONE commit is refused PRE-wire by the
            # caret guard (surrounding_text lags the committed value) — the
            # honest refusal is the row's data, never papered over
            ev["b_note"] = (
                "owned-span extension beyond one commit refused by the caret "
                "guard (snapshot lags committed value at this chromium) — the "
                "streaming multi-op cadence is unmeasurable on one acquisition"
            )
            subs.append(("mixed-3500b", "refused-recorded"))
        else:
            applied_b = True
            after = _stable_bstate(srv, expected_b, painted=True)
            if after is None or after.text.encode("utf-8") != expected_b.encode(
                "utf-8"
            ):
                bad.append("mixed-3500b-byte-exact")
            else:
                _law_check(before, after, "change", expected_b, bad, ev, "mixed")
            subs.append(
                (
                    "mixed-3500b",
                    "FAIL" if any(b.startswith("mixed-3500b") for b in bad) else "ok",
                )
            )
        # (c) >4 KB — REFUSED by design, field untouched (behavior row PASSES)
        before = _bstate(srv)
        dones = _ping(proc)["dones"]
        overcap_ok = True
        r = _show(target, rev, 4, "b4", 3, span_b + overcap)
        if r is not ShowResult.REFUSED:
            bad.append("overcap-not-refused")
            ev["c"] = r.name
            overcap_ok = False
        else:
            after = _bstate(srv)
            if after is None or before is None:
                bad.append("overcap-page-state-missing")
                overcap_ok = False
            else:
                if after.text.encode("utf-8") != before.text.encode("utf-8"):
                    bad.append("overcap-field-touched")
                    overcap_ok = False
                _law_check(before, after, "noop", before.text, bad, ev, "overcap")
            if _ping(proc)["dones"] != dones:
                bad.append("overcap-wire-commits")
                overcap_ok = False
            ev["overcap_bytes"] = len((span_b + overcap).encode("utf-8"))
            subs.append(
                ("overcap-4500b", "refused-by-design" if overcap_ok else "FAIL")
            )
        applied_expected = expected_b if applied_b else pre + unicode_
        _browser_verify(
            proc,
            pre,  # field value BEFORE the last commit ((a)'s — (b)/(c) never commit)
            ev,
            bad,
            "b4",
            current_expected=applied_expected,
        )
        if not any(
            b.endswith(("not-applied", "byte-exact", "never-settled")) for b in bad
        ):
            insert_ok = True
        ev["subrows"] = subs
        ok = not bad
        lab.verdict(
            "browser-long-unicode",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            shot=lab.shot("b4"),
            **ev,
        )
        target.leave()
        lab.report_rows.append(
            {
                "id": "browser-overcap-4500b (capability sub-row)",
                "title": ">4000 B delivery capability",
                "passed": None,
                "status": OVERCAP_BLOCKED_REASON
                if overcap_ok
                else "blocked (overcap behavior FAILED)",
                "evidence": ["refused pre-wire, never chunked; field untouched (Δn=0)"],
            }
        )
        return {
            "row": "b4",
            "ok": ok,
            "insert_ok": insert_ok,
            "correction_ok": None,
            "checks": tuple(bad),
        }
    except Exception as e:  # noqa: BLE001
        lab.verdict("browser-long-unicode", None, error=repr(e))
        return {"row": "b4", "ok": None, "reason": repr(e)[:80]}


def row_b5_refusing_readonly(lab, proc, srv, field_proc) -> dict:  # noqa: ANN001
    """B5: <input readonly> (?mode=ro) in its own isolated-profile window.
    NO visible edit may land; the ACTUAL branch recorded; then a fresh
    WRITABLE window takes one insert (adapter not wedged)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        if field_proc is not None and field_proc.poll() is None:
            lab.kill(field_proc)  # remove the writable window: focus unambiguous
        wait_deactivated(proc)
        ro = spawn_browser(lab, srv, tag="b5ro", readonly=True)
        focus_browser(lab, readonly=True)

        def _focused_ro():
            t = _focused_title(lab)
            return t if t is not None and t.startswith(BROWSER_TITLE + "-ro") else None

        focused = until(_focused_ro, 3)
        ev["focused"] = (focused or "")[:60]
        branch = ""
        if focused is None:
            lab.verdict(
                "browser-refusing-readonly",
                None,
                reason=f"readonly window never got focus (focused={focused!r})",
                stderr=lab.err_head("chromium-b5ro.err"),
                **ev,
            )
            lab.kill(ro)
            return {"row": "b5", "ok": None, "reason": "no focus"}
        if not wait_activated(proc):
            branch = "activation-refused (readonly <input> never enabled text-input)"
        else:
            target = ImeTarget(proc)
            a = target.acquire()
            if not a.ok:
                branch = f"acquire-refused ({a.reason})"
            else:
                s_before = _bstate(srv)
                r = _show(target, [a.revision], 5, "b5", 1, "must not land")
                if r is ShowResult.APPLIED:
                    after = _bstate(srv)
                    unchanged = (
                        after is not None
                        and s_before is not None
                        and after.text == s_before.text
                        and after.n == s_before.n
                    )
                    branch = (
                        "applied-but-ignored-by-field"
                        if unchanged
                        else "applied-and-FIELD-CHANGED"
                    )
                    if not unchanged:
                        bad.append("readonly-field-changed")
                elif r is ShowResult.REFUSED:
                    branch = f"show-refused ({target.last_reason})"
                elif r is ShowResult.UNKNOWN:
                    branch = "show-unknown (host never saw the compositor done)"
                else:
                    branch = "show-unchanged"
                target.leave()
        after = _bstate(srv)
        ev["branch"] = branch
        if after is not None and after.k != 0:
            bad.append("readonly-page-saw-keydowns")
        # --- recovery witness: a fresh WRITABLE window takes one insert ----
        lab.kill(ro)
        wait_deactivated(proc)
        w2 = spawn_browser(lab, srv, tag="b6")
        focus_browser(lab)
        if not wait_activated(proc):
            bad.append("recovery-window-never-activated")
        else:
            t2 = ImeTarget(proc)
            a2 = t2.acquire()
            if not a2.ok:
                bad.append(f"recovery-acquire-refused ({a2.reason})")
            else:
                s_w2 = _bstate(srv)
                pre2 = s_w2.text if s_w2 else ""
                r2 = _show(t2, [a2.revision], 5, "b5", 2, "recovered.")
                if r2 is not ShowResult.APPLIED:
                    bad.append(f"recovery-insert-not-applied ({r2.name})")
                elif _stable_bstate(srv, pre2 + "recovered.", painted=True) is None:
                    bad.append("recovery-never-settled")
                ev["recovery"] = r2.name
            t2.leave()
        ok = not bad
        lab.verdict(
            "browser-refusing-readonly",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        return {
            "row": "b5",
            "ok": ok,
            "branch": branch,
            "field_proc": w2,
            "checks": tuple(bad),
        }
    except Exception as e:  # noqa: BLE001
        lab.verdict("browser-refusing-readonly", None, error=repr(e))
        return {"row": "b5", "ok": None, "reason": repr(e)[:80]}


def row_b6_takeover(lab, proc, srv) -> dict:  # noqa: ANN001
    """B6: the E6 leg against the browser window + the page's keydown counter
    did NOT move (grab consumed the key — never reached the page)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        focus_browser(lab)
        if not wait_activated(proc):
            lab.verdict(
                "browser-takeover", None, reason="recovery window never activated", **ev
            )
            return {"row": "b6", "ok": None, "reason": "no activation"}
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "browser-takeover", False, error=f"acquire refused: {a.reason!r}"
            )
            return {"row": "b6", "ok": False, "checks": ("acquire",)}
        rev = [a.revision]
        s_pre = _bstate(srv)
        pre = s_pre.text if s_pre else ""
        r = _show(target, rev, 6, "b6", 1, "owned fragment; ")
        if r is not ShowResult.APPLIED:
            lab.verdict(
                "browser-takeover", False, error=f"owned insert not applied: {r.name}"
            )
            target.leave()
            return {"row": "b6", "ok": False, "checks": ("owned-insert",)}
        s_own = _stable_bstate(srv, pre + "owned fragment; ", painted=True)
        if s_own is None:
            lab.verdict("browser-takeover", False, error="owned insert never settled")
            target.leave()
            return {"row": "b6", "ok": False, "checks": ("owned-insert-settle",)}

        def page_keys():
            s = _bstate(srv)
            return None if s is None else s.k

        def page_text():
            s = _bstate(srv)
            return None if s is None else s.text

        _takeover_leg(lab, proc, target, page_keys, page_text, "b6", bad, ev)
        ev["shot"] = lab.shot("b6")
        ok = not bad
        lab.verdict(
            "browser-takeover",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        return {"row": "b6", "ok": ok, "checks": tuple(bad)}
    except Exception as e:  # noqa: BLE001
        lab.verdict("browser-takeover", None, error=repr(e))
        return {"row": "b6", "ok": None, "reason": repr(e)[:80]}


# --- global invariants + versions + class verdicts --------------------------------


def check_global_invariants(lab: Lab, srv: PushServer | None) -> None:
    """Whole-run: every editor dump witnessed ZERO received keys and ZERO
    Enter submissions; every page push witnessed ZERO keydowns; grab_key
    events exist ONLY because takeover rows ran (delivery cannot self-trigger
    takeover — M4.T5.S1/T4 invariant, re-pinned by E6/B6's counter freezes)."""
    bad: list[str] = []
    for f in sorted(lab.root.glob("field*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("keys", 0) != 0:
            bad.append(f"keys-nonzero:{f.name}")
        if d.get("activated", 0) != 0:
            bad.append(f"activated-nonzero:{f.name}")
    if srv is not None:
        for s in srv.all_states():
            if s.k != 0:
                bad.append("page-keydowns-nonzero")
                break
    if lab.events.count("grab_key") and not lab.takeover_ran:
        bad.append("grab_key-without-takeover-row")
    lab.verdict("global-invariants", not bad, checks=bad)


def capture_versions(lab: Lab) -> dict:
    versions = {"kernel": platform.uname().release}
    try:
        versions["sway"] = (
            sp.run(
                ["sway", "--version"],
                env=lab.env,
                timeout=5,
                stdout=sp.PIPE,
                stderr=sp.DEVNULL,
            )
            .stdout.decode()
            .strip()
        )
    except (sp.TimeoutExpired, OSError):
        versions["sway"] = "unknown"
    ready = lab.root / "field.ready"
    try:
        r = json.loads(ready.read_text(encoding="utf-8"))
        versions["gtk"] = r.get("gtk", "unknown")
        versions["pygobject"] = r.get("pygobject", "unknown")
    except (OSError, json.JSONDecodeError):
        versions["gtk"] = versions["pygobject"] = "unknown"
    try:
        out = (
            sp.run(
                ["pacman", "-Q", "gtk4", "sway"],
                env=lab.env,
                timeout=5,
                stdout=sp.PIPE,
                stderr=sp.DEVNULL,
            )
            .stdout.decode()
            .strip()
        )
        for line in out.splitlines():
            name, _, ver = line.partition(" ")
            if name == "gtk4":
                versions["pacman_gtk4"] = ver
            elif name == "sway":
                versions["pacman_sway"] = ver
    except (sp.TimeoutExpired, OSError):
        pass
    try:
        versions["chromium"] = (
            sp.run(
                ["/usr/bin/chromium", "--version"],
                env=lab.env,
                timeout=10,
                stdout=sp.PIPE,
                stderr=sp.DEVNULL,
            )
            .stdout.decode()
            .strip()
            or "unknown"
        )
    except (sp.TimeoutExpired, OSError):
        versions["chromium"] = "absent"
    flags = (
        "--ozone-platform=wayland --enable-wayland-ime "
        "--wayland-text-input-version=3 --user-data-dir=<temp root> "
        "--no-first-run --no-default-browser-check --disable-gpu "
        "--password-store=basic"
    )
    if lab.chromium_no_sandbox:
        flags += " --no-sandbox (disposable desktop only — recorded)"
    versions["chromium_flags"] = flags
    try:
        versions["firefox"] = (
            sp.run(
                ["/usr/bin/firefox", "--version"],
                env=lab.env,
                timeout=10,
                stdout=sp.PIPE,
                stderr=sp.DEVNULL,
            )
            .stdout.decode()
            .strip()
            or "unknown"
        )
    except (sp.TimeoutExpired, OSError):
        versions["firefox"] = "absent"
    versions["firefox_flags"] = (
        "MOZ_ENABLE_WAYLAND=1 --profile <temp root> (contingency only)"
    )
    print(json.dumps({"row": "versions", **versions}, ensure_ascii=False), flush=True)
    try:
        (lab.root / "versions.json").write_text(json.dumps(versions))
    except OSError:
        pass
    return versions


def class_contribution(rows: list[dict], row_id: str) -> dict:
    for r in rows:
        if r.get("row") == row_id:
            return r
    return {"row": row_id, "ok": None, "reason": "row never ran"}


def write_outputs(
    lab: Lab,
    versions: dict,
    editor_rows: list[dict],
    browser_rows: list[dict],
    class_verdicts: dict[str, str],
    meta_extra: dict,
) -> None:
    """Report rows + class verdicts + the bounded report (renderer-enforced
    ≤150 lines). Verdicts ride <root>/verdicts.jsonl; with OUT set the same
    data lands in the architecture dir."""
    # ---- report rows (id/title/passed/status/evidence) ----------------------
    report_rows: list[dict] = list(lab.report_rows)  # capability sub-rows first-fit
    for contrib, rid, title in (
        (editor_rows[0], "editor-short-updates", "6 short inserts into the TextView"),
        (
            editor_rows[1],
            "editor-firstword-20sent",
            "20-sentence span + FIRST-word correction",
        ),
        (
            editor_rows[2],
            "editor-identical-finals",
            "same final ×3 — zero-diff ⇒ zero events",
        ),
        (
            editor_rows[3],
            "editor-long-unicode",
            "951 B unicode + 3.5 KB mixed; >4 KB refused",
        ),
        (
            editor_rows[4],
            "editor-refusing-readonly",
            "non-editable view refuses; recovery insert",
        ),
        (
            editor_rows[5],
            "editor-takeover",
            "real key mid-owned-fragment → exactly ONE halt",
        ),
        (
            browser_rows[0],
            "browser-short-updates",
            "6 short inserts into the DOM input",
        ),
        (
            browser_rows[1],
            "browser-firstword-20sent",
            "20-sentence span + FIRST-word correction (recorded branch)",
        ),
        (
            browser_rows[2],
            "browser-identical-finals",
            "same applied span ×3 — zero input events",
        ),
        (
            browser_rows[3],
            "browser-long-unicode",
            "951 B unicode + 3.5 KB mixed; >4 KB refused",
        ),
        (
            browser_rows[4],
            "browser-refusing-readonly",
            "<input readonly> refuses; recovery insert",
        ),
        (
            browser_rows[5],
            "browser-takeover",
            "real key mid-owned-fragment; page keydowns frozen",
        ),
    ):
        ok = contrib.get("ok")
        if ok is False:
            checks = contrib.get("checks") or ()
            status = f"blocked (FAILED: {checks[0] if checks else rid})"
        elif ok is None:
            status = f"untested (infra: {contrib.get('reason') or rid})"
        elif contrib.get("correction_ok") is True:
            status = "verified (versions + evidence)"
        elif (
            rid == "editor-identical-finals"
            and editor_rows[1].get("correction_ok") is True
            and ok
        ):
            # zero-diff continuation of E2's acquisition — its class standing
            # follows the owning row's correction leg (gtk-report convention)
            status = "verified (versions + evidence)"
        elif rid in ("editor-refusing-readonly", "browser-refusing-readonly"):
            status = (
                "blocked (refuses at activation by toolkit/browser design — "
                f"the expected refusing branch: {contrib.get('branch', '?')}; "
                "recovery insert verified)"
            )
        elif rid in ("editor-takeover", "browser-takeover"):
            status = "verified (versions + evidence)" if ok else "blocked"
        else:
            status = "insert-only"
        v = next((x for x in lab.verdicts if x.get("row") == rid), {})
        evidence = [
            f"pass={v.get('pass')}",
            f"t_ms={v.get('t_ms')} (mechanism-level, never G5)",
        ]
        for k, val in v.items():
            if k.endswith(
                ("_law", "_oracle", "_verify_note", "_sel", "_surrounding")
            ) or k in (
                "branch",
                "correction_branch",
                "correction_note",
                "recheck",
                "recheck_note",
                "results",
                "subrows",
                "channel",
                "binding",
                "grab_key_events",
                "halt_reasons",
                "watch_reason",
                "post_takeover",
                "injector",
                "recovery",
            ):
                evidence.append(f"{k}={val}")
        report_rows.append(
            {
                "id": rid,
                "title": title,
                "passed": ok,
                "status": status,
                "evidence": evidence,
            }
        )
    class_row_ids = {
        "graphical-editor": "editor",
        "browser-text-field": "browser",
    }
    for cls, prefix in class_row_ids.items():
        verdict = class_verdicts.get(cls, "untested (infra: no rows)")
        report_rows.append(
            {
                "id": f"CLASS {cls}",
                "title": "one closed-vocabulary verdict per field class (R.7)",
                "passed": None if not verdict.startswith("verified") else None,
                "status": verdict,
                "evidence": [f"rows = {prefix}-* (see per-row sections)"],
            }
        )
    open_items = list(meta_extra.get("open_items", []))
    meta = {
        "date": meta_extra["date"],
        "head": meta_extra["head"],
        "command": meta_extra["command"],
        "summary": meta_extra["summary"],
        "open_items": open_items,
    }
    text = render_class_report(
        versions,
        report_rows,
        meta,
        title=REPORT_TITLE,
        links=(
            "harness tests/ime_g3_editor_browser_lab.py (rows E1–E6 + B1–B6,"
            " takeover legs, injector ladder)",
            "editor field app tests/ime_g3_field_edit.py (fork of"
            " tests/ime_g3_field_gtk.py — the TextView-class document editor)",
            "browser fixture tests/fixtures/ime_g3_browser_field.html (real DOM"
            " input, self-witnessing JS, push + title channels)",
            "helpers tests/ime_g3_editor_browser_support.py (event-count law,"
            " argv builders, class verdicts); unit pins"
            " tests/test_ime_g3_editor_browser_support.py",
            "conventions plan/008_a47116bb2b79/architecture/g3_gtk_rows.md +"
            " g3_field_matrix.md; verdicts.jsonl beside this report",
        ),
        drift=(
            REAL_KEY_DRIFT,
            "E4(a)'s post-op dump waits for the commit's PAINTED frame"
            " (painted=True) — tightens the harness R4 fork's oracle window"
            " (the signal-time dump can precede the paint; determinism fix)",
            "B1 drives each short update as ONE acquire + ONE delta-append"
            " (per-utterance cadence); the one-acquisition multi-op cadence is"
            " B4(b)'s explicit measurement",
            "family-6 verify for the browser asserts the field value BEFORE the"
            " last commit (the measured one-commit structural lag); a"
            " current-value snapshot is recorded when already fresh",
        ),
    )
    lab.verdict(
        "class-graphical-editor",
        class_verdicts.get("graphical-editor", "").startswith("verified") or None,
        verdict=class_verdicts.get("graphical-editor", "untested"),
    )
    lab.verdict(
        "class-browser-text-field",
        class_verdicts.get("browser-text-field", "").startswith("verified") or None,
        verdict=class_verdicts.get("browser-text-field", "untested"),
    )
    out_dir = os.environ.get(OUT_ENV)
    if out_dir:
        outp = Path(out_dir)
        outp.mkdir(parents=True, exist_ok=True)
        (outp / "g3_editor_browser_rows.md").write_text(text + "\n", encoding="utf-8")
        with (outp / "editor_browser_row_verdicts.jsonl").open(
            "w", encoding="utf-8"
        ) as fh:
            for v in lab.verdicts:
                fh.write(json.dumps(v, ensure_ascii=False) + "\n")
            for cls, verdict in class_verdicts.items():
                fh.write(
                    json.dumps(
                        {"row": f"class:{cls}", "verdict": verdict}, ensure_ascii=False
                    )
                    + "\n"
                )
        print(json.dumps({"row": "outputs", "dir": str(outp)}), flush=True)


# --- phases ------------------------------------------------------------------------


def run(root: Path) -> None:
    if not (
        root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
        and root.name.startswith(PREFIX)
        and os.environ.get("WLR_BACKENDS") == "x11"
    ):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    stage = os.environ.get(STAGE_ENV, "all")
    lab = Lab(root)
    proc = None
    srv: PushServer | None = None
    browser_field_proc = None
    try:
        start_desktop(lab)
        os.environ.update(lab.env)  # the ImeProcess child inherits the SEAT env
        proc = start_adapter(lab)
        spawn_field_edit(lab)
        lab.focus(f'[title="{EDITOR_TITLE}"]')
        versions = capture_versions(lab)
        payloads = build_payloads()
        # ---------------- editor class (E1–E6) ----------------
        e1 = _browser_row_wrap(
            lab, "editor-short-updates", row_e1_short_updates, proc, payloads
        )
        target_e2 = None
        try:
            target_e2 = row_e2_firstword(lab, proc, payloads)
            e2_info = {
                "row": "e2",
                "ok": True if target_e2 is not None else False,
                "insert_ok": True if target_e2 is not None else None,
                "correction_ok": True if target_e2 is not None else None,
            }
        except Exception as e:  # noqa: BLE001
            e2_info = {"row": "e2", "ok": None, "reason": repr(e)[:80]}
        e3 = _browser_row_wrap(
            lab,
            "editor-identical-finals",
            row_e3_identical_finals,
            proc,
            target_e2,
            payloads,
        )
        e4 = _browser_row_wrap(
            lab, "editor-long-unicode", row_e4_long_unicode, proc, payloads
        )
        e5 = _browser_row_wrap(
            lab, "editor-refusing-readonly", row_e5_refusing_readonly, proc, payloads
        )
        e6 = _browser_row_wrap(lab, "editor-takeover", row_e6_takeover, proc)
        editor_rows = [e1, e2_info, e3, e4, e5, e6]
        # ---------------- browser class (B1–B6) ----------------
        browser_rows = []
        chromium_usable = shutil.which("chromium") is not None
        if stage == "editor" or not chromium_usable:
            why = (
                "not attempted (stage=editor)"
                if stage == "editor"
                else "chromium absent"
            )
            for rid in (
                "browser-short-updates",
                "browser-firstword-20sent",
                "browser-identical-finals",
                "browser-long-unicode",
                "browser-refusing-readonly",
                "browser-takeover",
            ):
                lab.verdict(rid, None, reason=why)
                browser_rows.append({"row": rid[:2], "ok": None, "reason": why})
        else:
            srv = PushServer()
            srv.start()
            try:
                field_proc = spawn_browser(lab, srv, tag="b1")
                browser_field_proc = field_proc
                b1 = _browser_row_wrap(
                    lab,
                    "browser-short-updates",
                    row_b1_short_updates,
                    proc,
                    srv,
                    payloads,
                )
                browser_rows.append(b1)
                if b1.get("ok") is None:
                    # activation failed → ONE bounded Firefox sub-row before
                    # declaring the class blocked (the PRP's strict contingency)
                    ff = firefox_contingency(lab, proc, srv, payloads)
                    browser_rows.append(ff)
                    b2i = {
                        "row": "b2",
                        "ok": None,
                        "reason": "chromium never activated",
                    }
                    b3 = {"row": "b3", "ok": None, "reason": "chromium never activated"}
                else:
                    tgt, b2i = row_b2_firstword(lab, proc, srv, payloads)
                    b3 = _browser_row_wrap(
                        lab,
                        "browser-identical-finals",
                        row_b3_identical_finals,
                        proc,
                        srv,
                        tgt,
                    )
                browser_rows += [b2i, b3]
                b4 = _browser_row_wrap(
                    lab,
                    "browser-long-unicode",
                    row_b4_long_unicode,
                    proc,
                    srv,
                    payloads,
                )
                browser_rows.append(b4)
                if b1.get("ok") is None:
                    b5 = {"row": "b5", "ok": None, "reason": "chromium never activated"}
                else:
                    b5 = _browser_row_wrap(
                        lab,
                        "browser-refusing-readonly",
                        row_b5_refusing_readonly,
                        proc,
                        srv,
                        browser_field_proc,
                    )
                    browser_field_proc = b5.get("field_proc", browser_field_proc)
                browser_rows.append(b5)
                if b1.get("ok") is None or b5.get("ok") is None:
                    b6 = {
                        "row": "b6",
                        "ok": None,
                        "reason": "no writable window to drive",
                    }
                else:
                    b6 = _browser_row_wrap(
                        lab, "browser-takeover", row_b6_takeover, proc, srv
                    )
                browser_rows.append(b6)
            finally:
                if srv is not None:
                    srv.stop()
        check_global_invariants(lab, srv)
        # ---------------- class verdicts ----------------
        e_rows = [r for r in editor_rows if r.get("ok") is not None or r.get("reason")]
        editor_class = class_verdict(e_rows)
        b_attempted = any(r.get("attempted", True) for r in browser_rows)
        browser_class = (
            "untested (not attempted)"
            if not b_attempted
            else class_verdict(browser_rows)
        )
        # ---------------- summary + report ----------------
        head = "unknown"
        try:
            head = (
                sp.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(REPO),
                    timeout=5,
                    stdout=sp.PIPE,
                    stderr=sp.DEVNULL,
                )
                .stdout.decode()
                .strip()
            )
        except (sp.TimeoutExpired, OSError):
            pass
        open_items = []
        if stage == "editor":
            open_items.append("browser rows not attempted (stage=editor) — rerun full")
        b2c = class_contribution(browser_rows, "b2")
        if b2c.get("ok") and not b2c.get("correction_ok"):
            open_items.append(
                "browser correction branch: "
                + str(b2c.get("reason") or "refused")
                + " — feeds P1.M5.T3.S1 clipboard-fallback decision"
            )
        e2c = class_contribution(editor_rows, "e2")
        if e2c.get("ok") is False or (e2c.get("ok") is None and e2c.get("reason")):
            open_items.append(
                "editor correction leg did not complete — see row evidence"
            )
        meta_extra = {
            "date": time.strftime("%Y-%m-%d"),
            "head": head,
            "command": (
                "timeout -k 2 420 env IME_G3_EDITOR_BROWSER_LAB=1 "
                ".venv/bin/python tests/ime_g3_editor_browser_lab.py"
            ),
            "summary": (
                f"editor: {editor_class}; browser: {browser_class}; "
                f"rows={len(lab.verdicts)} pass="
                f"{sum(1 for v in lab.verdicts if v['pass'] is True)} "
                f"fail={sum(1 for v in lab.verdicts if v['pass'] is False)} "
                f"skip={sum(1 for v in lab.verdicts if v['pass'] is None)}"
            ),
            "open_items": open_items,
        }
        write_outputs(
            lab,
            versions,
            editor_rows,
            browser_rows,
            {"graphical-editor": editor_class, "browser-text-field": browser_class},
            meta_extra,
        )
    except Exception as e:  # noqa: BLE001 — one bad block still tears down honestly
        lab.verdict("harness", False, error=repr(e))
    finally:
        try:
            if proc is not None:
                proc.stop(timeout=5)  # bounded SIGTERM -> killpg SIGKILL
        except Exception:  # noqa: BLE001
            pass
        if srv is not None:
            srv.stop()
        lab.teardown()  # killpg our own session groups — never a pattern sweep
    fails = [v["row"] for v in lab.verdicts if v["pass"] is False]
    print(
        json.dumps(
            {
                "rows": len(lab.verdicts),
                "passed": sum(1 for v in lab.verdicts if v["pass"] is True),
                "skipped": sum(1 for v in lab.verdicts if v["pass"] is None),
                "failed": len(fails),
                "failed_rows": fails,
            }
        ),
        flush=True,
    )
    if fails:
        raise SystemExit(1)


def firefox_contingency(lab: Lab, proc: ImeProcess, srv: PushServer, payloads) -> dict:
    """The STRICTLY BOUNDED contingency: chromium never activated → ONE
    Firefox sub-row (MOZ_ENABLE_WAYLAND=1, same fixture, title-channel
    witness). Any outcome is recorded honestly; firefox is a RESCUE attempt,
    not the row's primary class."""
    try:
        if shutil.which("firefox") is None:
            return {
                "row": "ff",
                "ok": None,
                "attempted": False,
                "reason": "firefox absent",
            }
        lab.env["MOZ_ENABLE_WAYLAND"] = "1"
        url = f"file://{FIXTURE}?push={srv.url}"
        profile = lab.root / "firefox-profile"
        err_name = "firefox.err"
        p = lab.spawn(firefox_argv(profile, url), stderr_name=err_name)
        since = time.monotonic()

        def up():
            if p.poll() is not None:
                return None
            t = _focused_title(lab) or ""
            w = _browser_window(lab)
            title = (w or {}).get("title") or ""
            if not (title.startswith(BROWSER_TITLE) or t.startswith(BROWSER_TITLE)):
                return None
            raw = srv.latest(since)
            if raw is None:
                return parse_title(title)  # title channel counts as witness
            return parse_push(raw)

        state = until(up, READY_S)
        if state is None:
            lab.kill(p)
            return {
                "row": "ff",
                "ok": False,
                "attempted": True,
                "reason": "firefox window/first-push never appeared",
                "stderr": lab.err_head(err_name),
            }
        focus_browser(lab)
        if not wait_activated(proc):
            lab.kill(p)
            return {
                "row": "ff",
                "ok": False,
                "attempted": True,
                "reason": "firefox text-input never activated",
            }
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.kill(p)
            return {
                "row": "ff",
                "ok": False,
                "attempted": True,
                "reason": f"acquire refused ({a.reason})",
            }
        rev = [a.revision]
        r = _show(target, rev, 7, "ff", 1, "firefox rescue insert")
        if r is not ShowResult.APPLIED:
            target.leave()
            lab.kill(p)
            return {
                "row": "ff",
                "ok": False,
                "attempted": True,
                "reason": f"insert {r.name} ({target.last_reason})",
            }
        settled = until(
            lambda: (
                (lambda s: s is not None and s.text == "firefox rescue insert")(
                    _bstate(srv, since)
                )
            ),
            6,
        )
        ok = settled is not None
        lab.verdict(
            "firefox-contingency",
            ok,
            checks=[] if ok else ["insert-never-witnessed"],
            channel=("push" if srv.latest(since) else "title"),
            t_ms=int((time.monotonic() - since) * 1000),
        )
        target.leave()
        lab.kill(p)
        return {
            "row": "ff",
            "ok": ok,
            "attempted": True,
            "insert_ok": True if ok else None,
            "reason": None if ok else "insert never witnessed by the page",
        }
    except Exception as e:  # noqa: BLE001
        return {"row": "ff", "ok": None, "attempted": True, "reason": repr(e)[:80]}


def _cleanup_stale_dirs() -> None:
    """Remove scratch dirs from an aborted earlier run (bounded tmpfs scratch).
    NO pattern sweep over processes — killpg owns OUR session groups only."""
    for stale in Path("/tmp").glob(PREFIX + "*"):
        shutil.rmtree(stale, ignore_errors=True)


def main() -> None:
    if os.environ.get(GATE_ENV) != "1":
        print(
            json.dumps(
                {"row": "gate", "pass": None, "note": f"skipped (set {GATE_ENV}=1)"}
            ),
            flush=True,
        )
        return
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        # INNER run invocation: our own argv carries the tmpdir path.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        run(Path(sys.argv[2]))
        return
    if len(sys.argv) != 1:
        print(f"usage: {GATE_ENV}=1 {sys.executable} {sys.argv[0]}", file=sys.stderr)
        raise SystemExit(2)
    _cleanup_stale_dirs()
    with tempfile.TemporaryDirectory(prefix=PREFIX) as folder:
        root = Path(folder)
        bus = root / "private-bus.conf"
        bus.write_text(
            "<busconfig><type>session</type><listen>unix:tmpdir="
            + folder
            + '</listen><policy context="default">'
            '<allow send_destination="*"/><allow own="*"/>'
            '<allow receive_sender="*"/></policy></busconfig>'
        )
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": folder,
            "XDG_RUNTIME_DIR": folder,
            "XDG_CONFIG_HOME": folder,
            "TMPDIR": folder,
            "GDK_BACKEND": "wayland",
            "WLR_BACKENDS": "x11",
            "WLR_LIBINPUT_NO_DEVICES": "1",
            "WLR_RENDERER": "pixman",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true",
            "XDG_SESSION_TYPE": "wayland",
            "LANG": "C.UTF-8",
            "GTK_A11Y": "none",
            "GIO_USE_VFS": "local",
            GATE_ENV: "1",
            STAGE_ENV: os.environ.get(STAGE_ENV, "all"),
            OUT_ENV: os.environ.get(OUT_ENV, ""),
            "PYTHONPATH": str(REPO),
        }  # forward the driver's own opt-in gate + stage + out knobs
        # Own the WHOLE session process group: on timeout kill the group so the
        # dbus session cannot survive reparented to init and hold pipes open.
        proc = sp.Popen(
            [
                "xvfb-run",
                "-a",
                "dbus-run-session",
                f"--config-file={bus}",
                "--",
                sys.executable,
                str(Path(__file__).resolve()),
                "run",
                folder,
            ],
            env=env,
            cwd=str(REPO),
            start_new_session=True,
        )
        try:
            proc.wait(timeout=INNER_WAIT_S)
        except sp.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except sp.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            print(
                json.dumps({"row": "harness", "pass": False, "error": "outer timeout"}),
                flush=True,
            )
            raise SystemExit(1)
        # forward the INNER verdict exit code — proc.wait() alone would mask it
        if proc.returncode not in (0, None):
            raise SystemExit(proc.returncode)


def test_gate_skips_lab():
    """Collected guard: the lab NEVER boots a desktop under plain pytest."""
    if os.environ.get(GATE_ENV) == "1":
        pytest_skip = __import__("pytest").skip
        pytest_skip("lab gate explicitly armed — run the lab, not pytest")
    assert os.environ.get(GATE_ENV) != "1"


if __name__ == "__main__":
    main()
