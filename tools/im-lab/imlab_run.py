"""im-lab orchestrator: capability spike for PRD §4.2sexies (bulk text delivery).

Run: timeout -k 2 150 python3 imlab_run.py [--keep DIR]

Starts a PRIVATE disposable desktop (Xvfb seat + private D-Bus + Sway, x11
backend, disposable HOME/runtime — same isolation recipe as paste-lab), then
drives scripted input-method-v2 operations against real editable fields and
asserts byte-exact editor state. Never touches the live desktop, clipboard,
microphone or the voice-typing daemon. Prints one JSON verdict per row.

Rows:
  A  globals advertised by the private compositor
  B  gtk insert            F gtk unicode         I/L  foot/ghostty insert
  C  gtk one-edit correct  G gtk 951-byte        J/M  foot/ghostty correct
  D  gtk preedit           G2 whole-span correct K/N  foot/ghostty preedit
  D2 preedit->final atomic H surrounding_text    O    keyboard-grab takeover
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess as sp
import sys
import tempfile
import time

BIG = "Words arrive in one paste. " * 35 + "Café."
UNICODE = "Zoë — naïve résumé … 日本語のテストです 🫡 café"
SPAN = " ".join(f"word{i:02d}" for i in range(1, 31))


def until(probe, seconds: float = 3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if (v := probe()) is not None and v is not False and v != "":
            return v
        time.sleep(0.02)
    return None


class Lab:
    def __init__(self, root: Path):
        self.root = root
        self.env = os.environ.copy()
        self.procs: list[sp.Popen] = []
        self.verdicts: list[dict] = []
        self.ctl: socket.socket | None = None

    def spawn(self, args, stderr_name: str | None = None):
        err = open(self.root / stderr_name, "wb") if stderr_name else sp.DEVNULL  # noqa: SIM115
        p = sp.Popen(args, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=err,
                     env=self.env, start_new_session=True)
        self.procs.append(p)
        return p

    def cmd(self, args, timeout=5, check=True):
        return sp.check_output(args, stdin=sp.DEVNULL, stderr=sp.DEVNULL,
                               env=self.env, timeout=timeout) if check else sp.run(
            args, stdin=sp.DEVNULL, stdout=sp.PIPE, stderr=sp.DEVNULL,
            env=self.env, timeout=timeout).stdout

    def err_head(self, name, n=300):
        try:
            return (self.root / name).read_text(errors="replace")[:n]
        except FileNotFoundError:
            return ""

    def log_rows(self) -> list[dict]:
        try:
            text = (self.root / "im.jsonl").read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        return [json.loads(x) for x in text.splitlines() if x.strip()]

    def wait_log_since(self, base: int, pred, seconds: float = 3):
        return until(lambda: next((r for r in self.log_rows()[base:] if pred(r)), None), seconds)

    def field(self, name="field.json"):
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def ctl_send(self, payload: dict) -> dict:
        assert self.ctl is not None
        self.ctl.sendall(json.dumps(payload).encode() + b"\n")
        buf = b""
        deadline = time.monotonic() + 3
        while b"\n" not in buf and time.monotonic() < deadline:
            r, _, _ = select.select([self.ctl], [], [], max(deadline - time.monotonic(), 0.05))
            if not r:
                return {"error": "ctl timeout"}
            buf += self.ctl.recv(8192)
        return json.loads(buf.decode())

    def verdict(self, row: str, ok: bool | None, **kw):
        v = {"row": row, "pass": ok}
        v.update(kw)
        self.verdicts.append(v)
        print(json.dumps(v, ensure_ascii=False), flush=True)
        with open(self.root / "verdicts.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(v, ensure_ascii=False) + "\n")

    def wait_field(self, pred, seconds=3, field="field.json"):
        t0 = time.monotonic()
        got = until(lambda: (lambda s: s if pred(s) else None)(self.field(field)), seconds)
        return got, round((time.monotonic() - t0) * 1000)

    def focused_app_id(self):
        try:
            tree = json.loads(self.cmd(["swaymsg", "-r", "-t", "get_tree"]))
        except (sp.CalledProcessError, sp.TimeoutExpired, json.JSONDecodeError):
            return None

        def walk(n):
            if isinstance(n, dict):
                if n.get("focused"):
                    return n.get("app_id") or n.get("name") or "?"
                for k in ("nodes", "floating_nodes"):
                    for c in n.get(k) or []:
                        if (r := walk(c)):
                            return r
            return None

        return walk(tree)

    def focus(self, criteria: str) -> str | None:
        try:
            self.cmd(["swaymsg", criteria + " focus"])
        except (sp.CalledProcessError, sp.TimeoutExpired):
            return None
        return until(lambda: (fid := self.focused_app_id()), 3)

    def shot(self, name: str) -> str:
        p = self.root / name
        try:
            self.cmd(["grim", str(p)], timeout=5)
            return hashlib.sha256((self.root / name).read_bytes()).hexdigest()[:16] if p.exists() else ""
        except (sp.CalledProcessError, sp.TimeoutExpired):
            return ""

    def teardown(self):
        if self.ctl:
            try:
                self.ctl_send({"cmd": "quit"})
            except OSError:
                pass
            self.ctl.close()
        for p in reversed(self.procs):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
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
    window = lab.cmd(["xdotool", "search", "--onlyvisible", "--maxdepth", "1", "--name", ".*"]
                     ).splitlines()[-1].decode()
    lab.cmd(["xdotool", "windowfocus", window])
    lab.spawn([sys.executable, str(Path(__file__).parent / "im_probe.py"), str(lab.root)],
              stderr_name="im_probe.err")
    if not until(lambda: (lab.root / "ctl.sock").exists(), 7):
        raise RuntimeError(f"im_probe never started: {lab.err_head('im_probe.err')}")
    lab.ctl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    lab.ctl.connect(str(lab.root / "ctl.sock"))


def gtk_rows(lab: Lab):
    base = len(lab.log_rows())
    lab.spawn([sys.executable, str(Path(__file__).parent / "field_gtk.py"), str(lab.root)],
              stderr_name="gtk.err")
    if not until(lambda: (lab.root / "field.ready").exists(), 8):
        lab.verdict("B gtk-boot", False, error="GTK field never became ready",
                    stderr=lab.err_head("gtk.err"))
        return
    fid = lab.focus('[title="imlab-field-gtk"]')
    act = lab.wait_log_since(base, lambda r: r.get("ev") == "activate", 5)
    if not act:
        lab.verdict("B gtk-boot", False, error="input method never activated for the GTK field",
                    focused=fid, stderr=lab.err_head("gtk.err"))
        return
    lab.wait_log_since(base, lambda r: r.get("ev") == "done", 3)
    g = next((r for r in lab.log_rows() if r.get("ev") == "globals"), {})
    lab.verdict("A globals", bool(g.get("manager_v2")) and bool(g.get("text_input_v3")),
                manager_v2=g.get("manager_v2"), text_input_v3=g.get("text_input_v3"),
                n_globals=g.get("n_globals"))
    lab.verdict("B gtk-boot", True, focused=fid)

    t0 = time.monotonic()
    r = lab.ctl_send({"cmd": "insert", "text": "Hello wayland"})
    got, wait_ms = lab.wait_field(lambda s: s and s.get("text") == "Hello wayland")
    lat = round(got["t"] - t0 * 1000, 1) if got else None
    lab.verdict("B gtk-insert", bool(got) and r.get("ok"), ctl_reply_ms=r.get("t_ms"),
                visible_after_ms=wait_ms, send_to_field_ms=lat, pos=(got or {}).get("pos"))

    before = lab.field()
    r = lab.ctl_send({"cmd": "replace", "before": len(" wayland".encode()), "text": "IM v2"})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == "HelloIM v2")
    edits = (lab.field() or {}).get("cseq", 0) - before.get("cseq", 0)
    lab.verdict("C gtk-correct", bool(got) and edits in (1, 2),
                text=(got or {}).get("text"), document_edits=edits,
                ctl_reply_ms=r.get("t_ms"), pos=(got or {}).get("pos"),
                note="exact text; GTK applies delete+insert as 1-2 internal changed signals in one commit cycle")

    before = lab.field()
    h_none = lab.shot("shot-gtk-nopreedit.png")
    time.sleep(0.4)
    h_none2 = lab.shot("shot-gtk-nopreedit2.png")
    lab.ctl_send({"cmd": "preedit", "text": "draft …"})
    time.sleep(0.4)
    h_pre = lab.shot("shot-gtk-preedit.png")
    time.sleep(0.4)
    h_pre2 = lab.shot("shot-gtk-preedit2.png")
    edits = (lab.field() or {}).get("cseq", 0) - before.get("cseq", 0)
    stable = h_none == h_none2 and h_pre == h_pre2 and bool(h_pre)
    lab.verdict("D gtk-preedit", edits == 0,
                document_edits=edits, shots_stable=stable,
                screen_changed_with_preedit=stable and h_pre != h_none)
    lab.ctl_send({"cmd": "endpreedit", "text": ""})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == "HelloIM v2")
    lab.verdict("D2 gtk-preedit-clear", bool(got),
                document_edits=(lab.field() or {}).get("cseq", 0) - before.get("cseq", 0))
    lab.ctl_send({"cmd": "preedit", "text": "one two three"})
    time.sleep(0.5)
    before = lab.field()
    lab.ctl_send({"cmd": "endpreedit", "text": "one two three"})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == "HelloIM v2one two three")
    edits = (lab.field() or {}).get("cseq", 0) - before.get("cseq", 0)
    lab.verdict("D3 gtk-preedit-final", bool(got) and edits in (0, 1),
                text=(got or {}).get("text"), document_edits=edits,
                note="0 = zero visible edit; 1 = single atomic preedit->commit transition")

    before = lab.field()
    time.sleep(0.4)
    lab.verdict("E gtk-zero-diff", lab.field().get("cseq") == before.get("cseq"),
                document_edits=lab.field().get("cseq", 0) - before.get("cseq", 0))

    # Reset the field to a known base so later rows don't depend on earlier text.
    cur = (got or {}).get("text") or "HelloIM v2"
    lab.ctl_send({"cmd": "replace", "before": len(cur.encode()), "text": "Base "})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == "Base ")
    lab.ctl_send({"cmd": "insert", "text": UNICODE})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == "Base " + UNICODE)
    lab.verdict("F gtk-unicode", bool(got), text=(got or {}).get("text"))

    lab.ctl_send({"cmd": "insert", "text": " " + BIG})
    expected = "Base " + UNICODE + " " + BIG
    got, _ = lab.wait_field(lambda s: s and s.get("text") == expected)
    lab.verdict("G gtk-951B", bool(got), bytes=len(expected.encode()))

    fixed = SPAN.replace("word01", "WORD-ONE")
    before = lab.field()
    r = lab.ctl_send({"cmd": "replace", "before": len(expected.encode()), "text": fixed})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == fixed, 4)
    edits = (lab.field() or {}).get("cseq", 0) - before.get("cseq", 0)
    lab.verdict("G2 gtk-whole-span-correct", bool(got) and edits in (1, 2),
                replaced_bytes=len(expected.encode()), document_edits=edits,
                text=(got or {}).get("text"))

    hbase = len(lab.log_rows())
    lab.ctl_send({"cmd": "insert", "text": " probe"})
    lab.wait_field(lambda s: s and s.get("text", "").endswith("probe"), 3)
    lab.wait_log_since(hbase, lambda r: r.get("ev") == "surrounding_text", 2)
    all_sur = [r for r in lab.log_rows() if r.get("ev") == "surrounding_text"]
    best = max(all_sur, key=lambda r: r.get("bytes", 0), default=None)
    lab.verdict("H gtk-surrounding-text", bool(best), cursor=(best or {}).get("cursor"),
                anchor=(best or {}).get("anchor"), max_bytes=(best or {}).get("bytes"),
                head=(best or {}).get("head"), n_events=len(all_sur))


def term_rows(lab: Lab, spawn_args, app_id: str, tag: str):
    base = len(lab.log_rows())
    for f in ("term.json", "term.final", "term.ready"):
        (lab.root / f).unlink(missing_ok=True)
    proc = lab.spawn(spawn_args + [sys.executable, str(Path(__file__).parent / "field_term.py"),
                                   str(lab.root)], stderr_name=f"term-{tag.replace(' ', '_')}.err")
    if not until(lambda: (lab.root / "term.ready").exists(), 8):
        lab.verdict(f"{tag} text-input", False,
                    error="terminal field never became ready",
                    stderr=lab.err_head(f"term-{tag.replace(' ', '_')}.err"))
        return
    fid = lab.focus(f'[app_id="{app_id}"]')
    activated = lab.wait_log_since(base, lambda r: r.get("ev") == "activate", 4)
    lab.verdict(f"{tag} text-input", bool(activated), focused=fid,
                note="terminal enabled text-input (IME route live)" if activated
                else "terminal did NOT enable text-input — IM route blocked here")
    if activated:
        lab.wait_log_since(base, lambda r: r.get("ev") == "done", 3)
        r = lab.ctl_send({"cmd": "insert", "text": "hello from im"})
        got, wait_ms = lab.wait_field(lambda s: s and s.get("line") == "hello from im",
                                      4, field="term.json")
        lab.verdict(f"{tag} insert", bool(got), ctl_reply_ms=r.get("t_ms"),
                    visible_after_ms=wait_ms, line=(got or {}).get("line"))
        # Diagnostic: some toolkits only deliver IME text through a preedit cycle.
        prev = (lab.field("term.json") or {}).get("line", "")
        lab.ctl_send({"cmd": "preedit", "text": "XYZ"})
        time.sleep(0.3)
        lab.ctl_send({"cmd": "endpreedit", "text": "XYZ"})
        got2, _ = lab.wait_field(lambda s: s and s.get("line") == prev + "XYZ", 3,
                                 field="term.json")
        lab.verdict(f"{tag} insert-via-preedit", bool(got2), line=(got2 or {}).get("line"))
        r = lab.ctl_send({"cmd": "replace", "before": len(" im".encode()), "text": "v2"})
        got, _ = lab.wait_field(lambda s: s and s.get("line") == "hello fromv2", 4,
                                field="term.json")
        note = ""
        if not got:
            note = f"line after replace attempt: {lab.field('term.json')!r}"
        lab.verdict(f"{tag} correct", bool(got), note=note, line=(got or {}).get("line"))
        before = lab.field("term.json")
        lab.ctl_send({"cmd": "preedit", "text": "wip"})
        time.sleep(0.4)
        h_pre = lab.shot(f"shot-{tag.replace(' ', '_')}_preedit.png")
        time.sleep(0.4)
        h_pre2 = lab.shot(f"shot-{tag.replace(' ', '_')}_preedit2.png")
        after = lab.field("term.json")
        lab.ctl_send({"cmd": "endpreedit", "text": ""})
        time.sleep(0.4)
        h_none = lab.shot(f"shot-{tag.replace(' ', '_')}_nopreedit.png")
        time.sleep(0.4)
        h_none2 = lab.shot(f"shot-{tag.replace(' ', '_')}_nopreedit2.png")
        stable = h_pre == h_pre2 and h_none == h_none2 and bool(h_pre)
        lab.verdict(f"{tag} preedit", after is not None
                    and after.get("line") == (before or {}).get("line"),
                    app_saw_no_bytes=(after.get("seq", 0) == (before or {}).get("seq", 0)
                                      if after and before else None),
                    screen_changed_with_preedit=stable and h_pre != h_none,
                    shots_stable=stable)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def grab_rows(lab: Lab):
    base = len(lab.log_rows())
    lab.ctl_send({"cmd": "grab"})
    keymap_ev = lab.wait_log_since(base, lambda r: r.get("ev") == "keymap", 3)
    before = lab.field()
    time.sleep(0.4)
    lab.cmd(["xdotool", "key", "--delay", "10", "b"])
    key_ev = lab.wait_log_since(base, lambda r: r.get("ev") == "grab_key", 3)
    time.sleep(0.4)
    after = lab.field()
    lab.verdict("O grab-takeover", bool(keymap_ev) and bool(key_ev) and before and after
                and after.get("cseq") == before.get("cseq"),
                grab_engaged=bool(keymap_ev), keycode=(key_ev or {}).get("key"),
                field_untouched=after.get("cseq") == before.get("cseq") if before and after else None)
    n0 = len([r for r in lab.log_rows() if r.get("ev") == "grab_key"])
    lab.ctl_send({"cmd": "insert", "text": "no self trigger"})
    got, _ = lab.wait_field(lambda s: s and s.get("text", "").endswith("no self trigger"), 3)
    n1 = len([r for r in lab.log_rows() if r.get("ev") == "grab_key"])
    lab.verdict("O2 grab-no-self-trigger", bool(got) and n1 == n0, field_changed=bool(got),
                grab_keys_during_delivery=n1 - n0)


def run(root: Path) -> None:
    if not (root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
            and root.name.startswith("imlab-") and os.environ.get("WLR_BACKENDS") == "x11"):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    lab = Lab(root)
    try:
        start_desktop(lab)
        try:
            gtk_rows(lab)
        except Exception as e:  # noqa: BLE001 - one bad block must not kill the run
            lab.verdict("gtk-block", False, error=repr(e))
        for args, app_id, tag in (
                (["foot", "-T", "imlab-foot"], "foot", "I foot"),
                (["kitty", "--class", "imlab-kitty"], "imlab-kitty", "K kitty"),
                (["ghostty", "--gtk-single-instance=false", "--shell-integration=none", "-e"],
                 "com.mitchellh.ghostty", "L ghostty")):
            try:
                term_rows(lab, args, app_id, tag)
            except Exception as e:  # noqa: BLE001
                lab.verdict(f"{tag} block", False, error=repr(e))
        try:
            lab.focus('[title="imlab-field-gtk"]')

            def activated_state():
                s = lab.ctl_send({"cmd": "state"})
                return s if s.get("activated") else None

            st = until(activated_state, 5)
            if st:
                grab_rows(lab)
            else:
                lab.verdict("O grab-takeover", None, note="GTK field no longer activatable")
        except Exception as e:  # noqa: BLE001
            lab.verdict("O grab block", False, error=repr(e))
    finally:
        lab.teardown()
    fails = [v["row"] for v in lab.verdicts if v["pass"] is False]
    print(json.dumps({"rows": len(lab.verdicts), "passed": sum(1 for v in lab.verdicts if v["pass"] is True),
                      "failed": len(fails), "failed_rows": fails}), flush=True)
    if fails:
        raise SystemExit(1)


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        run(Path(sys.argv[2]))
        return
    if len(sys.argv) == 1 or (len(sys.argv) == 3 and sys.argv[1] == "--keep"):
        keep = Path(sys.argv[2]) if len(sys.argv) == 3 else None
        if keep:
            keep.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="imlab-") as folder:
            root = Path(folder)
            bus = root / "private-bus.conf"
            bus.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + folder + '</listen>'
                           '<policy context="default"><allow send_destination="*"/><allow own="*"/>'
                           '<allow receive_sender="*"/></policy></busconfig>')
            env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": folder, "XDG_RUNTIME_DIR": folder,
                   "XDG_CONFIG_HOME": folder, "TMPDIR": folder, "GDK_BACKEND": "wayland", "WLR_BACKENDS": "x11",
                   "WLR_LIBINPUT_NO_DEVICES": "1", "WLR_RENDERER": "pixman", "LIBGL_ALWAYS_SOFTWARE": "1",
                   "MESA_SHADER_CACHE_DISABLE": "true",
                   "XDG_SESSION_TYPE": "wayland", "LANG": "C.UTF-8", "GTK_A11Y": "none", "GIO_USE_VFS": "local"}
            try:
                sp.run(["xvfb-run", "-a", "dbus-run-session", f"--config-file={bus}", "--",
                        sys.executable, str(Path(__file__).resolve()), "run", folder],
                       env=env, check=False, timeout=140)
            except sp.TimeoutExpired:
                print(json.dumps({"row": "harness", "pass": False, "error": "outer timeout"}))
            if keep:
                for f in root.iterdir():
                    if f.is_file() and (f.suffix == ".png" or f.name in ("im.jsonl", "gtk.err", "verdicts.jsonl")):
                        f.replace(keep / f.name)
        return
    raise SystemExit("Run without arguments (optionally: --keep DIR)")


if __name__ == "__main__":
    main()
