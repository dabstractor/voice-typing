#!/usr/bin/env python3
"""ime_correction_lab — env-gated GTK-harness EVIDENCE driver for ImeTarget.show()'s
correction path (P1.M4.T3.S2).

NOT collected by pytest (no test_ prefix; default runs NEVER execute it). Run by hand,
only against a PRIVATE disposable desktop:

    timeout 300 env IME_CORRECTION_LAB=1 .venv/bin/python tests/ime_correction_lab.py

Rows (one JSON verdict line each; mechanism evidence only — never acceptance, R.2):
  R1 gtk small  seed "x" → acquire → inserts "hell", "lo w" (extension path) → ONE
                correction to "hello world" (diverges at char 1): the field's dumped text
                must end with "hello world", caret at the end, the correction's commit
                grew the document-edit counter by ≤3 (GTK fires 1–2 internal `changed`
                signals per atomic commit cycle — EXPECTED, R.2), zero synthetic keys.
  R2 gtk >1024B fresh acquire → ONE insert of a 1500-char owned span → correct its
                FIRST char via ONE atomic replacement (before=1500) → the field text
                must equal the corrected span BYTE-EXACTLY (the im-lab 1024 B proof,
                scaled), caret at the end.

Pattern copied from tests/ime_acquire_lab.py / tools/im-lab/imlab_run.py (READ-ONLY
evidence — never edited): xvfb-run + dbus-run-session + sway private seat, disposable
HOME/runtime, our ime_host served over pipes, tools/im-lab/field_gtk.py as the
graphical field (system python3 — the venv has no gi). Scratch stays in one mktemp
dir (RAM-backed tmpfs; the host event log is EventLogWriter-capped at 64 KiB and
everything dies with the dir via TemporaryDirectory). Without IME_CORRECTION_LAB=1:
prints skipped, exits 0.
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

from voice_typing.bulk_delivery import ShowResult

REPO = Path(__file__).resolve().parents[1]
GATE_ENV = "IME_CORRECTION_LAB"
PREFIX = "ime-correction-lab-"


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

    Skips id-less event lines (stashing them) until the id-echoing reply arrives; also
    exposes wait_event so rows sequence on the field's own pushed snapshots (the next
    show's mutation-time recheck must see the SETTLED caret, not a stale cache).
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
        # pipe read would deadlock. Drive the pump: ping per poll cycle, inspect
        # the event lines each ping flushes out before its reply.
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._id += 1
            rid = self._id
            self.p.stdin.write((json.dumps({"id": rid, "cmd": "ping"}) + "\n").encode())
            self.p.stdin.flush()
            while True:
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


def _settled(lab: Lab, expect_text: str, seconds=5.0) -> bool:
    """field.json (the GTK field's own dump) shows the settled post-commit text.

    Sequencing on the field dump, not on pipe events: the surrounding_text push
    often arrives DURING the show request window (the host drains the wire around
    request handling) and is consumed before a wait_event could observe it.
    """
    def ok():
        f = _field(lab)
        if f is None or f.get("text") != expect_text:
            return None
        return f.get("pos") == len(f.get("text", "")) or None   # caret at the end
    return until(ok, seconds) is not None


def _show(target, rev_box, session, seq, span):
    """One controller-shaped show call; bumps the local expected_revision on applied."""
    r = target.show(session, "correction-lab", seq, rev_box[0], span)
    if r.name == "APPLIED":
        rev_box[0] += 1
    return r


def row_gtk_small_correction(lab: Lab, pipes: HostPipes) -> None:
    """R1: seed → two inserts → ONE atomic correction (rewrites 'helllo w')."""
    gtk = lab.spawn([shutil.which("python3"), str(REPO / "tools" / "im-lab" / "field_gtk.py"),
                     str(lab.root)], stderr_name="gtk.err")
    if not until(lambda: (lab.root / "field.ready").exists(), 8) or gtk.poll() is not None:
        lab.verdict("R1 gtk small correction", False, error="GTK field never became ready",
                    stderr=lab.err_head("gtk.err"))
        return
    lab.focus('[title="imlab-field-gtk"]')
    if not pipes.wait_event("activate", 8.0):
        lab.verdict("R1 gtk small correction", False,
                    error="input method never activated for the GTK field",
                    stderr=lab.err_head("gtk.err"))
        return
    # Seed one char (real user text the correction must NEVER touch — R.3).
    r = pipes.request("show", timeout=3.0, session=1, utterance="lab", seq=0,
                      expected_revision=0, text="x")
    if not r or r.get("result") != "applied":
        lab.verdict("R1 gtk small correction", False, error=f"seed commit not applied: {r}")
        return
    if not _settled(lab, "x"):
        lab.verdict("R1 gtk small correction", False, error="field never settled after seed")
        return
    from voice_typing.ime.target import ImeTarget
    target = ImeTarget(pipes)
    a = target.acquire()
    if not a.ok:
        lab.verdict("R1 gtk small correction", False, error=f"acquire refused: {a.reason!r}")
        return
    rev = [a.revision]
    r = _show(target, rev, 1, 1, "hell")
    if r is not ShowResult.APPLIED:
        lab.verdict("R1 gtk small correction", False,
                    error=f"insert 'hell' not applied: {r.name}", reason=target.last_reason)
        return
    if not _settled(lab, "xhell"):
        lab.verdict("R1 gtk small correction", False, error="field never settled after 'hell'")
        return
    r = _show(target, rev, 1, 2, "helllo w")
    if r is not ShowResult.APPLIED:
        lab.verdict("R1 gtk small correction", False,
                    error=f"insert 'lo w' not applied: {r.name}", reason=target.last_reason)
        return
    owned = "helllo w"
    if not _settled(lab, "x" + owned):
        lab.verdict("R1 gtk small correction", False, error="field never settled after 'lo w'")
        return
    f0 = _field(lab)
    cseq_before = f0["cseq"] if f0 else None
    r = _show(target, rev, 1, 3, "hello world")          # THE correction (diverges at char 1)
    end_caret = a.handle.cursor_bytes + len("hello world".encode())
    if r.name != "APPLIED":
        lab.verdict("R1 gtk small correction", False,
                    error=f"correction not applied: {r.name} reason={target.last_reason!r}")
        return
    if not _settled(lab, "xhello world"):
        lab.verdict("R1 gtk small correction", False, error="field never settled after fix")
        return
    f1 = _field(lab)
    cseq_delta = (f1["cseq"] - cseq_before) if (f1 and cseq_before is not None) else None
    ok = (f1 is not None and f1["text"].endswith("hello world")
          and f1["pos"] == len(f1["text"])
          and cseq_delta is not None and 1 <= cseq_delta <= 3
          and target._last_applied_span == "hello world"
          and target._inserted_bytes == len("hello world".encode()))
    lab.verdict("R1 gtk small correction", ok,
                field_text_tail=(f1["text"][-16:] if f1 else None),
                pos=(f1.get("pos") if f1 else None),
                cseq_delta=cseq_delta,                     # 1–2 per commit cycle EXPECTED
                before_bytes=len(owned.encode()), text_bytes=len("hello world".encode()),
                grab_keys=0)                               # IM commit only — no synthetic keys


def row_gtk_large_correction(lab: Lab, pipes: HostPipes) -> None:
    """R2 (>1024 B): 1500-char owned span, first char rewritten — byte-exact replacement."""
    from voice_typing.ime.target import ImeTarget
    target = ImeTarget(pipes)
    a = target.acquire()                                    # same field, binds at its end
    if not a.ok:
        lab.verdict("R2 gtk >1024B correction", False, error=f"acquire refused: {a.reason!r}")
        return
    rev = [a.revision]
    pre = (_f := _field(lab)) and _f.get("text", "")       # whatever R1 left in the field
    big = "z" + "a" * 1499                                  # 1500 B owned span (one insert)
    r = _show(target, rev, 1, 10, big)
    if r is not ShowResult.APPLIED:
        lab.verdict("R2 gtk >1024B correction", False,
                    error=f"1500-char insert not applied: {r.name}", reason=target.last_reason)
        return
    if not _settled(lab, (pre or "") + big):
        lab.verdict("R2 gtk >1024B correction", False, error="field never settled after insert")
        return
    fixed = "q" + "a" * 1499                                # first char rewritten
    f0 = _field(lab)
    cseq_before = f0["cseq"] if f0 else None
    r = _show(target, rev, 1, 11, fixed)                    # ONE atomic replacement, before=1500
    if r is not ShowResult.APPLIED:
        lab.verdict("R2 gtk >1024B correction", False,
                    error=f"correction not applied: {r.name} reason={target.last_reason!r}")
        return
    if not _settled(lab, (pre or "") + fixed):
        lab.verdict("R2 gtk >1024B correction", False, error="field never settled after fix")
        return
    f1 = _field(lab)
    cseq_delta = (f1["cseq"] - cseq_before) if (f1 and cseq_before is not None) else None
    ok = (f1 is not None and f1["text"] == (pre or "") + fixed  # BYTE-EXACT replacement
          and f1["pos"] == len(f1["text"])
          and cseq_delta is not None and 1 <= cseq_delta <= 3
          and target._inserted_bytes == len(fixed.encode()))
    lab.verdict("R2 gtk >1024B correction", ok,
                byte_exact=(f1 is not None and f1["text"] == (pre or "") + fixed),
                pos=(f1.get("pos") if f1 else None), cseq_delta=cseq_delta,
                before_bytes=len(big.encode()), text_bytes=len(fixed.encode()), grab_keys=0)


def run(root: Path) -> None:
    if not (root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
            and root.name.startswith(PREFIX)):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    lab = Lab(root)
    lab_ = lab
    host_log = root / "im-events.jsonl"  # EventLogWriter-capped at 64 KiB (bounded scratch)
    try:
        start_desktop(lab)
        host = lab.spawn([sys.executable, "-m", "voice_typing.ime.ime_host", str(host_log)],
                         stdin=sp.PIPE, stdout=sp.PIPE, stderr_name="im_host.err")
        pipes = HostPipes(host)
        if not until(lambda: host_log.exists() and "globals" in host_log.read_text(errors="replace"), 7):
            raise RuntimeError(f"ime_host never became the IM: {lab.err_head('im_host.err')}")
        row_gtk_small_correction(lab, pipes)   # R1
        row_gtk_large_correction(lab, pipes)   # R2 (>1024 B)
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

    NO pkill here: a path-prefix process match can hit unrelated processes whose
    cmdline merely MENTIONS the path. Process cleanup belongs to the driver's own
    session-group teardown (killpg), never a pattern sweep.
    """
    for stale in Path("/tmp").glob(PREFIX + "*"):
        shutil.rmtree(stale, ignore_errors=True)


def main() -> None:
    if os.environ.get(GATE_ENV) != "1":
        print(json.dumps({"row": "gate", "pass": None,
                          "note": f"skipped (set {GATE_ENV}=1)"}), flush=True)
        return
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        # INNER run invocation: our own argv carries the tmpdir path — any pattern
        # sweep here would target ourselves. Clean only in outer.
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
        # Own the WHOLE session process group: on timeout kill the group so the dbus
        # session cannot survive reparented to init and hold pipes open.
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
