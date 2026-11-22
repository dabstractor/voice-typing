"""Nested-Hyprland probe: run the im-lab GTK rows against Hyprland, the
operator's real compositor, inside the disposable desktop.

Run: timeout -k 2 150 python3 hypr_nest.py

Chain: Xvfb seat -> private Sway (x11 backend) -> nested Hyprland (Wayland
backend) -> GTK4 field + im_probe connected to the HYPR socket. If Hyprland
fails to come up the script prints an "untested" verdict instead of hanging.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from imlab_run import Lab, until  # noqa: E402


def hypr_rows(lab: Lab, hypr_env: dict) -> None:
    base = len(lab.log_rows())
    # im_probe and the field must speak to the HYPR socket, not sway's.
    probe_env = dict(lab.env)
    probe_env["WAYLAND_DISPLAY"] = hypr_env["WAYLAND_DISPLAY"]
    p = sp.Popen([sys.executable, str(Path(__file__).parent / "im_probe.py"), str(lab.root)],
                 stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=open(lab.root / "im_probe_hypr.err", "wb"),
                 env=probe_env, start_new_session=True)
    lab.procs.append(p)
    if not until(lambda: (lab.root / "ctl.sock").exists(), 7):
        lab.verdict("HY boot", False, error="probe never started",
                    stderr=lab.err_head("im_probe_hypr.err"))
        return
    lab.ctl = __import__("socket").socket(__import__("socket").AF_UNIX, __import__("socket").SOCK_STREAM)
    lab.ctl.connect(str(lab.root / "ctl.sock"))

    p = sp.Popen([sys.executable, str(Path(__file__).parent / "field_gtk.py"), str(lab.root)],
                 stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=open(lab.root / "gtk_hypr.err", "wb"),
                 env=probe_env, start_new_session=True)
    lab.procs.append(p)
    if not until(lambda: (lab.root / "field.ready").exists(), 8):
        lab.verdict("HY boot", False, error="GTK field never ready under Hyprland",
                    stderr=lab.err_head("gtk_hypr.err"))
        return
    for _ in range(5):
        sp.run(["hyprctl", "--sig", hypr_env["HYPRLAND_INSTANCE_SIGNATURE"],
                "dispatch", "focuswindow", "class:org.imlab.field"],
               env=hypr_env, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=5)
        if lab.wait_log_since(base, lambda r: r.get("ev") == "activate", 2):
            break
    act = lab.wait_log_since(base, lambda r: r.get("ev") == "activate", 2)
    if not act:
        lab.verdict("HY text-input", False, error="input method never activated under Hyprland")
        return
    lab.wait_log_since(base, lambda r: r.get("ev") == "done", 3)
    lab.verdict("HY text-input", True, note="Hyprland relayed text-input activation")

    r = lab.ctl_send({"cmd": "insert", "text": "Hello hypr"})
    got, wait_ms = lab.wait_field(lambda s: s and s.get("text") == "Hello hypr")
    lab.verdict("HY insert", bool(got), ctl_reply_ms=r.get("t_ms"), visible_after_ms=wait_ms,
                pos=(got or {}).get("pos"))

    before = lab.field()
    r = lab.ctl_send({"cmd": "replace", "before": len(" hypr".encode()), "text": "Hyprland"})
    got, _ = lab.wait_field(lambda s: s and s.get("text") == "HelloHyprland")
    edits = (lab.field() or {}).get("cseq", 0) - before.get("cseq", 0)
    lab.verdict("HY correct", bool(got) and edits in (1, 2), document_edits=edits,
                text=(got or {}).get("text"), pos=(got or {}).get("pos"))

    before = lab.field()
    lab.ctl_send({"cmd": "preedit", "text": "draft …"})
    time.sleep(0.5)
    h_pre = lab.shot("shot-hypr-preedit.png")
    time.sleep(0.4)
    h_pre2 = lab.shot("shot-hypr-preedit2.png")
    edits = (lab.field() or {}).get("cseq", 0) - before.get("cseq", 0)
    lab.verdict("HY preedit", edits == 0, document_edits=edits,
                shots_stable=bool(h_pre) and h_pre == h_pre2)
    lab.ctl_send({"cmd": "endpreedit", "text": ""})

    hbase = len(lab.log_rows())
    lab.ctl_send({"cmd": "insert", "text": " probe"})
    lab.wait_field(lambda s: s and s.get("text", "").endswith("probe"), 3)
    lab.wait_log_since(hbase, lambda r: r.get("ev") == "surrounding_text", 2)
    all_sur = [r for r in lab.log_rows() if r.get("ev") == "surrounding_text" and r.get("bytes", 0) > 0]
    lab.verdict("HY surrounding-text", bool(all_sur),
                max_bytes=max((r.get("bytes", 0) for r in all_sur), default=0),
                n_events=len(all_sur))


def run(root: Path) -> None:
    if os.environ.get("WLR_BACKENDS") != "x11" or Path(os.environ["XDG_RUNTIME_DIR"]) != root:
        raise RuntimeError("Refusing to run outside the disposable desktop")
    lab = Lab(root)
    try:
        conf = root / "sway.conf"
        conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
        sway = lab.spawn(["sway", "-c", str(conf)])
        if not until(lambda: next(root.glob("sway-ipc.*.sock"), None), 7):
            raise RuntimeError("parent Sway failed to start")
        lab.env["SWAYSOCK"] = str(next(root.glob("sway-ipc.*.sock")))
        sway_display = until(lambda: next((p.name for p in root.glob("wayland-*") if p.is_socket()), None), 7)
        window = lab.cmd(["xdotool", "search", "--onlyvisible", "--maxdepth", "1", "--name", ".*"]
                         ).splitlines()[-1].decode()
        lab.cmd(["xdotool", "windowfocus", window])

        hypr_env = dict(lab.env)
        hypr_env["WAYLAND_DISPLAY"] = sway_display
        hypr_env["XDG_CURRENT_DESKTOP"] = "Hyprland"
        hypr_err = open(root / "hypr.err", "wb")
        hypr = sp.Popen(["Hyprland"], stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=hypr_err,
                        env=hypr_env, start_new_session=True)
        lab.procs.append(hypr)
        sig = until(lambda: next((p.parent.name for p in root.glob("hypr/*/.wl_socket")
                                  if p.is_socket()), None), 25)
        if not sig or hypr.poll() is not None:
            lab.verdict("HY boot", False, error="nested Hyprland failed to start",
                        stderr=lab.err_head("hypr.err", 400))
            return
        # Focus the nested compositor's window inside sway so it gets keyboard.
        try:
            lab.cmd(['swaymsg', '[app_id="hyprland"] focus'], check=True)
        except sp.CalledProcessError:
            try:
                lab.cmd(["swaymsg", "focus tiling"], check=True)
            except sp.CalledProcessError:
                pass
        hypr_env["HYPRLAND_INSTANCE_SIGNATURE"] = sig
        hypr_env["WAYLAND_DISPLAY"] = f"hypr/{sig}/.wl_socket"
        g = sp.run([sys.executable, str(Path(__file__).parent / "globals.py"), "json"],
                   env=hypr_env, capture_output=True, timeout=10)
        try:
            adv = json.loads(g.stdout).get("text_injection", {})
        except json.JSONDecodeError:
            adv = {}
        lab.verdict("HY globals", adv.get("zwp_input_method_manager_v2") == 1,
                    text_injection=adv)
        hypr_rows(lab, hypr_env)
    finally:
        lab.teardown()
    fails = [v["row"] for v in lab.verdicts if v["pass"] is False]
    print(json.dumps({"rows": len(lab.verdicts), "passed": sum(1 for v in lab.verdicts if v["pass"] is True),
                      "failed": len(fails), "failed_rows": fails}), flush=True)
    if fails:
        raise SystemExit(1)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="imlab-hypr-") as folder:
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


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        run(Path(sys.argv[2]))
    elif len(sys.argv) == 1:
        main()
    else:
        raise SystemExit("no arguments expected")
