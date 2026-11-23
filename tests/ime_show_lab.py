#!/usr/bin/env python3
"""ime_show_lab — env-gated GTK-harness EVIDENCE driver for ImeTarget.show insert path (P1.M4.T3.S1).

NOT collected by pytest (no test_ prefix; default runs NEVER execute it). Run by hand, only
against a PRIVATE disposable desktop:

    timeout 300 env IME_SHOW_LAB=1 .venv/bin/python tests/ime_show_lab.py

Rows (one JSON verdict line each; mechanism evidence only — never acceptance, R.2):
  R4 gtk bind  (seed one char into the real GTK4 field, then ImeTarget.acquire)
               → ok, byte-exact pre_caret "x" (the T2.S1 binding the inserts extend)
  R5 gtk x3    (three sequential ImeTarget.show() inserts — wire deltas "Hel", "lo w",
               "orld" via cumulative spans) → all APPLIED; the dumped field text ends
               with "Hello world", caret at the end, the changed-signal edit count grew
               by ≤3, and ZERO grab_key events (delivery commits are not keystrokes, R.2)

Pattern copied from tests/ime_acquire_lab.py (itself from tools/im-lab/imlab_run.py — both
READ-ONLY evidence, never edited): xvfb-run + dbus-run-session + sway private seat,
disposable HOME/runtime, our ime_host served over pipes (S2-style Popen),
tools/im-lab/field_gtk.py as the graphical field (system python3 — the venv has no gi).
Scratch stays in one mktemp dir (RAM-backed tmpfs: files are small, the host event log is
EventLogWriter-capped at 64 KiB, field dumps capped at 2000, and everything dies with the
dir via TemporaryDirectory). Without IME_SHOW_LAB=1: prints skipped, exits 0.
"""
from __future__ import annotations

import json
import os
import select
import shutil
import signal
import subprocess as sp
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE_ENV = "IME_SHOW_LAB"
PREFIX = "ime-show-lab-"


def until(probe, seconds: float):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        v = probe()
        if v is not None and v is not False and v != "":
            return v
        time.sleep(0.02)
    return None


def _field(lab) -> dict | None:
    try:
        return json.loads((lab.root / "field.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class HostPipes:
    """The proc duck ImeTarget consumes: request(cmd, timeout=..., **fields) over JSONL pipes.

    Skips id-less event lines (stashing them) until the id-echoing reply arrives; also exposes
    wait_event so the driver can sequence on the target's own pushed snapshots.
    """

    def __init__(self, proc):
        self.p = proc
        self._buf = ""
        self._id = 0
        self.events = []  # event lines seen while pumping (bounded by row count)

    def _readline(self, deadline) -> str | None:
        while "\n" not in self._buf:
            remain = deadline - time.monotonic()
            if remain <= 0 or self.p.poll() is not None:
                return None
            r, _, _ = select.select([self.p.stdout], [], [], min(remain, 0.2))
            if not r:
                continue
            chunk = os.read(self.p.stdout.fileno(), 65536)
            if not chunk:
                return None  # EOF — host died
            self._buf += chunk.decode("utf-8", errors="replace")
        line, self._buf = self._buf.split("\n", 1)
        return line

    def request(self, cmd, timeout=2.5, **fields) -> dict | None:
        self._id += 1
        rid = self._id
        self.p.stdin.write((json.dumps({"id": rid, "cmd": cmd, **fields}) + "\n").encode())
        self.p.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            line = self._readline(deadline)
            if line is None:
                return None
            obj = json.loads(line)
            if obj.get("reply") == cmd and obj.get("id") == rid:
                return obj
            self.events.append(obj)  # interleaved event line

    def wait_event(self, name, seconds=5.0, pred=None) -> dict | None:
        # The host drains wire events ONLY around request handling — a passive
        # pipe read would deadlock. Drive the pump: send a ping per poll cycle
        # and inspect the event lines each ping flushes out before its reply.
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._id += 1
            rid = self._id
            self.p.stdin.write((json.dumps({"id": rid, "cmd": "ping"}) + "\n").encode())
            self.p.stdin.flush()
            while True:  # read until THIS ping's reply: events it drained surface first
                line = self._readline(deadline)
                if line is None:
                    return None
                obj = json.loads(line)
                if obj.get("reply") == "ping" and obj.get("id") == rid:
                    break
                if obj.get("ev") == name and (pred is None or pred(obj)):
                    return obj
                self.events.append(obj)
            time.sleep(0.05)
        return None


class Lab:
    def __init__(self, root: Path):
        self.root = root
        self.env = os.environ.copy()
        self.procs: list[sp.Popen] = []
        self.verdicts: list[dict] = []

    def spawn(self, args, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr_name=None):
        err = (self.root / stderr_name).open("wb") if stderr_name else sp.DEVNULL  # noqa: SIM115
        p = sp.Popen(args, stdin=stdin, stdout=stdout, stderr=err, env=self.env,
                     start_new_session=True)
        self.procs.append(p)
        return p

    def cmd(self, args, timeout=5):
        return sp.run(args, stdin=sp.DEVNULL, stdout=sp.PIPE, stderr=sp.DEVNULL,
                      env=self.env, timeout=timeout).stdout

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

    def verdict(self, row: str, ok, **kw):
        v = {"row": row, "pass": ok}
        v.update(kw)
        self.verdicts.append(v)
        print(json.dumps(v, ensure_ascii=False), flush=True)

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
    conf = lab.root / "sway.conf"
    conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
    sway = lab.spawn(["sway", "-c", str(conf)])
    if not until(lambda: next(lab.root.glob("sway-ipc.*.sock"), None), 7) or sway.poll() is not None:
        raise RuntimeError("private Sway failed to start")
    lab.env["SWAYSOCK"] = str(next(lab.root.glob("sway-ipc.*.sock")))
    lab.env["WAYLAND_DISPLAY"] = until(
        lambda: next((p.name for p in lab.root.glob("wayland-*") if p.is_socket()), None), 7)
    lab.env["PYTHONPATH"] = str(REPO)


def _spawn_gtk_field(lab: Lab) -> bool:
    gtk = lab.spawn([shutil.which("python3"), str(REPO / "tools" / "im-lab" / "field_gtk.py"),
                     str(lab.root)], stderr_name="gtk.err")
    if not until(lambda: (lab.root / "field.ready").exists(), 8) or gtk.poll() is not None:
        return False
    lab.focus('[title="imlab-field-gtk"]')
    return True


def row_gtk_bind(lab: Lab, pipes: HostPipes) -> object | None:
    """R4: seed one char → ImeTarget.acquire binds the real GTK4 field byte-exactly."""
    if not _spawn_gtk_field(lab):
        lab.verdict("R4 gtk bind", False, error="GTK field never became ready",
                    stderr=lab.err_head("gtk.err"))
        return None
    if not pipes.wait_event("activate", 8.0):
        lab.verdict("R4 gtk bind", False, error="input method never activated for the GTK field",
                    stderr=lab.err_head("gtk.err"))
        return None
    seed = pipes.request("show", timeout=3.0, session=1, utterance="lab", seq=0,
                         expected_revision=0, text="x")
    if not seed or seed.get("result") != "applied":
        lab.verdict("R4 gtk bind", False, error=f"seed commit not applied: {seed}")
        return None
    # The field pushes a FRESH snapshot after applying our commit; sequence on it.
    if not pipes.wait_event("surrounding_text", 5.0, pred=lambda ev: ev.get("bytes", 0) >= 1):
        lab.verdict("R4 gtk bind", False, error="field never pushed a post-commit snapshot")
        return None
    from voice_typing.ime.target import ImeTarget
    a = ImeTarget(pipes).acquire()
    if a.ok and getattr(a.handle, "pre_caret", None) == "x" and a.handle.cursor_bytes == 1:
        lab.verdict("R4 gtk bind", True, pre_caret=a.handle.pre_caret,
                    cursor_bytes=a.handle.cursor_bytes, revision=a.revision)
        target = ImeTarget(pipes)
        target._binding = a.handle  # carry the SAME binding into the insert row (evidence chain)
        target._last_applied_span = ""  # the seed "x" predates this acquisition (T2.S1 semantics)
        return target
    lab.verdict("R4 gtk bind", False, got=f"ok={a.ok} reason={a.reason!r} "
                f"pre_caret={getattr(a.handle, 'pre_caret', None)!r}")
    return None


def row_gtk_insert3(lab: Lab, pipes: HostPipes, target) -> None:
    """R5: three sequential show() inserts land as ≤3 edits, caret at end, zero grabs."""
    if target is None:  # bind row failed — nothing to extend; record honestly
        lab.verdict("R5 gtk insert x3", None, note="bind row failed — skipped")
        return
    base = _field(lab)
    cseq_before = base.get("cseq", 0) if base else 0
    spans = ["Hel", "Hello w", "Hello world"]  # cumulative → wire deltas "Hel"/"lo w"/"orld"
    rev = target._binding.revision
    elapsed_ms = []
    for i, span in enumerate(spans, start=1):
        t0 = time.monotonic()
        r = target.show(1, "lab", i, rev + i, span)
        elapsed_ms.append(round((time.monotonic() - t0) * 1000, 1))
        if r is not r.__class__.APPLIED:
            lab.verdict("R5 gtk insert x3", False, error=f"insert {i} not applied",
                        got=str(r), reason=target.last_reason)
            return
    landed = until(lambda: (f := _field(lab)) and f.get("text") == "xHello world", 4.0)
    field = _field(lab)
    grab_keys = 0
    try:  # the event log is EventLogWriter-capped at 64 KiB — bounded read (AGENTS.md R3)
        grab_keys = (lab.root / "im-events.jsonl").read_text(errors="replace").count(
            '"ev": "grab_key"')
    except FileNotFoundError:
        pass
    cseq_after = field.get("cseq", 0) if field else -1
    ok = bool(landed and field
              and field.get("text", "").endswith("Hello world")
              and field.get("pos") == len(field.get("text", ""))
              and 0 <= cseq_after - cseq_before <= 3
              and grab_keys == 0)
    lab.verdict("R5 gtk insert x3", ok,
                text=field.get("text") if field else None,
                caret_pos=field.get("pos") if field else None,
                cseq_delta=cseq_after - cseq_before,
                show_ms=elapsed_ms,
                grab_keys=grab_keys)


def run(root: Path) -> None:
    if not (root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
            and root.name.startswith(PREFIX)):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    lab = Lab(root)
    host_log = root / "im-events.jsonl"  # EventLogWriter-capped at 64 KiB (bounded scratch)
    try:
        start_desktop(lab)
        host = lab.spawn([sys.executable, "-m", "voice_typing.ime.ime_host", str(host_log)],
                         stdin=sp.PIPE, stdout=sp.PIPE, stderr_name="im_host.err")
        pipes = HostPipes(host)
        # become_im is proven by the capped event log's first "globals" line.
        if not until(lambda: host_log.exists() and "globals" in host_log.read_text(errors="replace"), 7):
            raise RuntimeError(f"ime_host never became the IM: {lab.err_head('im_host.err')}")
        target = row_gtk_bind(lab, pipes)      # R4
        row_gtk_insert3(lab, pipes, target)    # R5
    except Exception as e:  # noqa: BLE001 — one bad block still tears down honestly
        lab.verdict("harness", False, error=repr(e))
    finally:
        lab.teardown()
    fails = [v["row"] for v in lab.verdicts if v["pass"] is False]
    print(json.dumps({"rows": len(lab.verdicts),
                      "passed": sum(1 for v in lab.verdicts if v["pass"] is True),
                      "skipped": sum(1 for v in lab.verdicts if v["pass"] is None),
                      "failed": len(fails), "failed_rows": fails}), flush=True)
    if fails:
        raise SystemExit(1)


def _cleanup_stale_dirs() -> None:
    """Remove scratch dirs from an aborted earlier run (bounded tmpfs scratch).

    NO pkill here: a path-prefix process match can hit unrelated processes
    whose cmdline merely MENTIONS the path. Process cleanup belongs to the
    driver's own session-group teardown (killpg), never a pattern sweep.
    """
    for stale in Path("/tmp").glob(PREFIX + "*"):
        shutil.rmtree(stale, ignore_errors=True)


def main() -> None:
    if os.environ.get(GATE_ENV) != "1":
        print(json.dumps({"row": "gate", "pass": None,
                          "note": f"skipped (set {GATE_ENV}=1)"}), flush=True)
        return
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        # INNER run invocation: our own argv carries the tmpdir path — any
        # pattern sweep here would target ourselves. Clean only in outer.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        run(Path(sys.argv[2]))
        return
    _cleanup_stale_dirs()
    with tempfile.TemporaryDirectory(prefix=PREFIX) as folder:
        root = Path(folder)
        bus = root / "private-bus.conf"
        bus.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + folder + '</listen>'
                       '<policy context="default"><allow send_destination="*"/><allow own="*"/>'
                       '<allow receive_sender="*"/></policy></busconfig>')
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": folder, "XDG_RUNTIME_DIR": folder,
               "XDG_CONFIG_HOME": folder, "TMPDIR": folder, "GDK_BACKEND": "wayland",
               "WLR_BACKENDS": "x11", "WLR_LIBINPUT_NO_DEVICES": "1", "WLR_RENDERER": "pixman",
               "LIBGL_ALWAYS_SOFTWARE": "1", "MESA_SHADER_CACHE_DISABLE": "true",
               "XDG_SESSION_TYPE": "wayland", "LANG": "C.UTF-8", "GTK_A11Y": "none",
               "GIO_USE_VFS": "local", GATE_ENV: "1"}  # forward the driver's own opt-in gate
        # Own the WHOLE session process group: on timeout kill the group so the
        # dbus session cannot survive reparented to init and hold pipes open.
        proc = sp.Popen(["xvfb-run", "-a", "dbus-run-session", f"--config-file={bus}", "--",
                         sys.executable, str(Path(__file__).resolve()), "run", folder],
                        env=env, start_new_session=True)
        try:
            proc.wait(timeout=240)  # whole run bounded well inside any outer wrapper
        except sp.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except sp.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            print(json.dumps({"row": "harness", "pass": False, "error": "outer timeout"}),
                  flush=True)


if __name__ == "__main__":
    main()
