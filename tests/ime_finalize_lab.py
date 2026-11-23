#!/usr/bin/env python3
"""ime_finalize_lab — env-gated GTK-harness EVIDENCE driver for ImeTarget lifecycle
(finalize / leave / cancel — P1.M4.T3.S3).

NOT collected by pytest (no test_ prefix; default runs NEVER execute it). Run by hand, only
against a PRIVATE disposable desktop:

    timeout 300 env IME_FINALIZE_LAB=1 .venv/bin/python tests/ime_finalize_lab.py

Rows (one JSON verdict line each; mechanism evidence only — never acceptance, R.2):
  S3-a finalize-differ  partial "hel" applied → finalize "hello world" → field ends
                "hello world", caret at end, cseq grew by ≤2 (insert + ONE replacement;
                GTK may coalesce a delete+insert commit cycle into one `changed`).
  S3-b finalize-match  partial shown, then finalize with the SAME span → UNCHANGED and
                cseq grew by 0 (a matching final sends NOTHING — commit side effects
                cannot visibly change or duplicate visible text, R.3).
  S3-c cancel    partial applied → cancel → fragment gone, caret back at the
                pre-utterance position, cseq grew by exactly ONE edit. Also records the
                `before` byte count the adapter sent (must equal the fragment's UTF-8
                length — NO legacy len(tail)−1 compensation).
  S3-d leave     leave() → refocus/re-activate → ZERO further text changes (no post-stop
                writes anywhere, including into the re-focused field), and post-leave
                adapter calls refuse "not acquired" without touching the field.

Pattern copied from tests/ime_acquire_lab.py (READ-ONLY evidence — never edited):
xvfb-run + dbus-run-session + sway private seat, disposable HOME/runtime, our ime_host
served over pipes (S2-style Popen), tools/im-lab/field_gtk.py as the graphical field
(system python3 — the venv has no gi); cseq counts document edits only, which is how the
"ONE visible edit" / "zero events" pins are asserted. Scratch stays in one mktemp dir
(RAM-backed tmpfs: files are small, the host event log is EventLogWriter-capped at
64 KiB, and everything dies with the dir via TemporaryDirectory). Gotcha #14: the empty
commit_string("") inside the host's cancel triple is the one mechanism not proven by
R.2 — row S3-c is exactly that evidence; if GTK misbehaves the fallback is to drop the
commit_string request (one line in ime_host._cancel) and re-record honestly.
Without IME_FINALIZE_LAB=1: prints skipped, exits 0.
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
GATE_ENV = "IME_FINALIZE_LAB"
PREFIX = "ime-finalize-lab-"


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
    wait_event so the driver can sequence on the target's own pushed snapshots, and pump()
    so confirm-loops can drain events while the driver idles.
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

    def pump(self, seconds: float) -> None:
        """Keep draining host events (via pings) for a bounded beat — no expectations."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.wait_event("__never__", 0.2)  # one ping; any drained events land in self.events
            deadline_left = deadline - time.monotonic()
            if deadline_left <= 0:
                return


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


def start_gtk_field(lab: Lab, pipes: HostPipes) -> dict | None:
    """Spawn the GTK field, focus it, wait for activation, seed one committed char.

    Returns the acquire result handle of a fresh ImeTarget binding, or None (row skips).
    """
    gtk = lab.spawn([shutil.which("python3"), str(REPO / "tools" / "im-lab" / "field_gtk.py"),
                     str(lab.root)], stderr_name="gtk.err")
    if not until(lambda: (lab.root / "field.ready").exists(), 8) or gtk.poll() is not None:
        lab.verdict("harness", False, error="GTK field never became ready",
                    stderr=lab.err_head("gtk.err"))
        return None
    lab.focus('[title="imlab-field-gtk"]')
    if not pipes.wait_event("activate", 8.0):
        lab.verdict("harness", False, error="input method never activated for the GTK field",
                    stderr=lab.err_head("gtk.err"))
        return None
    r = pipes.request("show", timeout=3.0, session=1, utterance="lab", seq=1,
                      expected_revision=0, text="x")
    if not r or r.get("result") != "applied":
        lab.verdict("harness", False, error=f"seed commit not applied: {r}")
        return None
    # The field pushes a FRESH snapshot after applying our commit; sequence on it.
    push = pipes.wait_event("surrounding_text", 5.0, pred=lambda ev: ev.get("bytes", 0) >= 1)
    if not push:
        lab.verdict("harness", False, error="field never pushed a post-commit snapshot")
        return None
    from voice_typing.ime.target import ImeTarget
    t = ImeTarget(pipes)
    a = t.acquire()
    if not a.ok:
        lab.verdict("harness", False, error=f"acquire refused: {a.reason!r}")
        return None
    return {"target": t, "revision": a.revision, "field": _field(lab)}


def row_finalize_differ(lab: Lab, st: dict) -> None:
    """S3-a: partial "hel" → finalize "hello world" — ONE replacement, caret at end."""
    t, rev = st["target"], st["revision"]
    c0 = (_field(lab) or {}).get("cseq", 0)
    from voice_typing.bulk_delivery import ShowResult
    if t.show(1, "u1", 1, rev, "hel") is not ShowResult.APPLIED:
        lab.verdict("S3-a finalize-differ", False, error=f"partial not applied: {t.last_reason!r}")
        return
    if not until(lambda: (f := _field(lab)) and f.get("text", "").endswith("hel"), 4.0):
        lab.verdict("S3-a finalize-differ", False, error="partial never landed in the field")
        return
    if t.finalize(1, "u1", 2, rev + 1, "hello world") is not ShowResult.APPLIED:
        lab.verdict("S3-a finalize-differ", False, error=f"finalize not applied: {t.last_reason!r}")
        return
    landed = until(lambda: (f := _field(lab)) and f.get("text", "").endswith("hello world")
                   and f.get("pos") == len(f.get("text", "")), 4.0)
    c2 = (_field(lab) or {}).get("cseq", 0)
    if not landed:
        lab.verdict("S3-a finalize-differ", False, error="finalized text never landed",
                    field=_field(lab))
        return
    f = _field(lab) or {}
    grew = c2 - c0
    lab.verdict("S3-a finalize-differ", grew <= 2, edits=grew,
                text=f.get("text"), pos=f.get("pos"),
                note="insert + ONE atomic replacement; GTK may coalesce the commit cycle")


def row_finalize_match(lab: Lab, st: dict) -> None:
    """S3-b: finalize the SAME span just shown ⇒ UNCHANGED, ZERO edits (cseq frozen)."""
    from voice_typing.bulk_delivery import ShowResult
    from voice_typing.ime.target import ImeTarget
    t = ImeTarget(st["target"]._proc)  # fresh adapter: acquire resets the closed set
    a = t.acquire()
    if not a.ok:
        lab.verdict("S3-b finalize-match", False, error=f"re-acquire refused: {a.reason!r}")
        return
    rev = a.revision
    if t.show(1, "u2", 1, rev, " and more") is not ShowResult.APPLIED:
        lab.verdict("S3-b finalize-match", False, error=f"partial not applied: {t.last_reason!r}")
        return
    if not until(lambda: (f := _field(lab)) and f.get("text", "").endswith(" and more"), 4.0):
        lab.verdict("S3-b finalize-match", False, error="partial never landed in the field")
        return
    c1 = (_field(lab) or {}).get("cseq", 0)
    r = t.finalize(1, "u2", 2, rev + 1, " and more")
    t._proc.pump(0.8)  # give any illegal commit side effects time to surface
    c2 = (_field(lab) or {}).get("cseq", 0)
    f = _field(lab) or {}
    if r is not ShowResult.UNCHANGED:
        lab.verdict("S3-b finalize-match", False, error=f"matching final not UNCHANGED: "
                    f"{r} reason={t.last_reason!r}")
        return
    lab.verdict("S3-b finalize-match", c2 == c1, edits_after_finalize=c2 - c1,
                text=f.get("text"),
                note="a matching final sends NOTHING — zero events means zero requests")


def row_cancel(lab: Lab, st: dict) -> None:
    """S3-c: partial applied → cancel → fragment gone, caret back, exactly ONE edit.

    Gotcha #14 evidence: the host's empty commit_string("") variant under GTK.
    """
    from voice_typing.bulk_delivery import ShowResult
    from voice_typing.ime.target import ImeTarget
    t = ImeTarget(st["target"]._proc)
    a = t.acquire()
    if not a.ok:
        lab.verdict("S3-c cancel", False, error=f"re-acquire refused: {a.reason!r}")
        return
    rev = a.revision
    pre = _field(lab) or {}
    pos0 = pre.get("pos")
    frag = " wait no"
    if t.show(1, "u3", 1, rev, frag) is not ShowResult.APPLIED:
        lab.verdict("S3-c cancel", False, error=f"partial not applied: {t.last_reason!r}")
        return
    if not until(lambda: (f := _field(lab)) and f.get("text", "").endswith(frag), 4.0):
        lab.verdict("S3-c cancel", False, error="partial never landed in the field")
        return
    c1 = (_field(lab) or {}).get("cseq", 0)
    r = t.cancel()
    t._proc.pump(0.8)
    c2 = (_field(lab) or {}).get("cseq", 0)
    f = _field(lab) or {}
    ok = (r is ShowResult.APPLIED and not f.get("text", "").endswith(frag)
          and f.get("text") == pre.get("text") and f.get("pos") == pos0 and c2 - c1 == 1)
    lab.verdict("S3-c cancel", ok, result=r.value if hasattr(r, "value") else str(r),
                reason=t.last_reason, edits=c2 - c1, before_bytes=len(frag.encode("utf-8")),
                text=f.get("text"), pos=f.get("pos"), pos_before=pos0,
                note="ONE atomic removal; before == fragment UTF-8 bytes EXACTLY (no −1); "
                     "this row is the empty commit_string(\"\") evidence (Gotcha #14)")


def row_leave(lab: Lab, st: dict) -> None:
    """S3-d: leave() → refocus/re-activate → ZERO further text changes; post-leave
    adapter calls refuse \"not acquired\" without touching the field."""
    from voice_typing.bulk_delivery import ShowResult
    from voice_typing.ime.target import ImeTarget
    t = ImeTarget(st["target"]._proc)
    a = t.acquire()
    if not a.ok:
        lab.verdict("S3-d leave", False, error=f"re-acquire refused: {a.reason!r}")
        return
    before = _field(lab) or {}
    t.leave()
    lab.focus('[title="imlab-field-gtk"]')  # re-activate: focus churn, NOT a write
    t._proc.pump(1.5)
    refused = t.show(1, "u4", 1, a.revision, "should not land")
    after = _field(lab) or {}
    unchanged = (after.get("text") == before.get("text") and after.get("pos") == before.get("pos")
                 and after.get("cseq") == before.get("cseq"))
    lab.verdict("S3-d leave", unchanged and refused is ShowResult.REFUSED
                and t.last_reason == "not acquired",
                post_leave_show=str(refused), reason=t.last_reason,
                text=after.get("text"),
                note="stop preserves the last visible words; nothing writes after leave, "
                     "even into the re-focused field")


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
        st = start_gtk_field(lab, pipes)
        if st is not None:
            row_finalize_differ(lab, st)   # S3-a
            row_finalize_match(lab, st)    # S3-b
            row_cancel(lab, st)            # S3-c (Gotcha #14 evidence)
            row_leave(lab, st)             # S3-d
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
