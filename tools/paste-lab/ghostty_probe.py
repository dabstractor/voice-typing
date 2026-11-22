"""Bulk-paste acceptance probe. Run: timeout -k 2 25 /usr/bin/python tools/paste-lab/ghostty_probe.py

Starts a PRIVATE headless Sway, Wayland clipboard and Ghostty with a byte reader
instead of a shell. Never uses the desktop display, active clipboard, microphone,
live terminal or daemon. Requires sway, ghostty, wl-clipboard, xvfb-run, xdotool
and dbus-run-session. Xvfb supplies a private seat with a normal PC keyboard map;
Ghostty and the clipboard clients inside Sway are all native Wayland clients.
This tests the terminal transport, not whether a particular editor accepts a paste.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import signal
import subprocess as sp
import sys
import tempfile
import termios
import time
import tty


# Fixed synthetic samples bound every file and transfer in the probe. The second
# exercises a real clipboard transfer of a Backspace byte, not an injected key.
SAMPLES = [("Words arrive in one paste. " * 35 + "Café.").encode(), b"\x08\x08end"]
START, END = b"\x1b[200~", b"\x1b[201~"


def receive(root: Path) -> None:
    saved = termios.tcgetattr(0)
    try:
        tty.setraw(0)
        os.write(1, b"\x1b[?2004h")  # Ask the terminal to mark paste boundaries.
        (root / "ready").touch()
        for i in range(len(SAMPLES)):
            buf = bytearray()
            while not buf.endswith(END) and len(buf) < 8192:
                if buf and not select.select([0], [], [], 1)[0]:
                    break  # Report unexpected input even if it has no paste terminator.
                chunk = os.read(0, 8192 - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
            # Publish atomically so the harness cannot observe a partial result.
            tmp = root / "result.tmp"
            tmp.write_bytes(buf)
            tmp.rename(root / f"result{i}")
    finally:
        os.write(1, b"\x1b[?2004l")
        termios.tcsetattr(0, termios.TCSANOW, saved)


def until(probe, seconds: float = 3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := probe():
            return value
        time.sleep(0.02)
    raise RuntimeError(f"Timed out waiting for {probe.__name__}")


def run(root: Path) -> None:
    if not (root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
            and root.name.startswith("paste-lab-") and (root / "private-bus.conf").is_file()
            and os.environ.get("WLR_BACKENDS") == "x11" and Path(os.environ.get("XAUTHORITY", "/")).is_relative_to(root)):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    env = os.environ.copy()
    procs = []

    def spawn(args, *, writable=False):
        p = sp.Popen(args, stdin=sp.PIPE if writable else sp.DEVNULL, stdout=sp.DEVNULL,
                     stderr=sp.DEVNULL, env=env, start_new_session=True)
        procs.append(p)
        return p

    def cmd(args):
        return sp.check_output(args, stdin=sp.DEVNULL, stderr=sp.DEVNULL, env=env, timeout=2)

    try:
        conf = root / "sway.conf"
        conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
        sway = spawn(["sway", "-c", str(conf)])

        def private_socket():
            if sway.poll() is not None:
                raise RuntimeError("Private headless Sway failed to start")
            return next(root.glob("sway-ipc.*.sock"), None)

        env["SWAYSOCK"] = str(until(private_socket))
        env["WAYLAND_DISPLAY"] = until(lambda: next((p.name for p in root.glob("wayland-*") if p.is_socket()), None))
        term = spawn(["ghostty", "--gtk-single-instance=false", "--shell-integration=none",
                      "-e", sys.executable, str(Path(__file__).resolve()), "receive", str(root)])
        until(lambda: (root / "ready").exists(), 7)
        # Focus the private compositor's X window, not a desktop application.
        window = cmd(["xdotool", "search", "--onlyvisible", "--maxdepth", "1", "--name", ".*"]).splitlines()[-1].decode()
        cmd(["xdotool", "windowfocus", window])
        for i, data in enumerate(SAMPLES):
            # Inspect only the private compositor's clipboard. No
            # --paste-once: a read by a history manager isn't a target acknowledgement.
            owner = spawn(["wl-copy", "--foreground", "--type", "text/plain;charset=utf-8"], writable=True)
            assert owner.stdin is not None
            owner.stdin.write(data)
            owner.stdin.close()

            def offered():
                try:
                    return cmd(["wl-paste", "--no-newline"]) == data
                except sp.CalledProcessError:
                    return False

            until(offered)
            start = time.monotonic()
            cmd(["xdotool", "key", "--delay", "10", "ctrl+shift+v"])
            result = root / f"result{i}"
            until(result.exists)
            payload = result.read_bytes()
            if i == 0 and payload != START + data + END:
                raise RuntimeError(f"Expected one ordinary bracketed paste, got {len(payload)} bytes starting with {payload[:24]!r}")
            print(json.dumps({"sample": "text" if i == 0 else "backspace bytes", "source_bytes": len(data),
                              "one_exact_bracketed_paste": payload == START + data + END,
                              "received_hex": payload.hex() if i else None,
                              "trigger_to_observed_ms": round(1000 * (time.monotonic() - start))}), flush=True)
        term.wait(timeout=2)
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            p.wait(timeout=2)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "receive":
        receive(Path(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == "run":
        # Unwind the child cleanup block even if the enclosing GNU timeout fires.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        run(Path(sys.argv[2]))
    elif len(sys.argv) == 1:
        # No inherited compositor, D-Bus session, user config or notifications.
        # TemporaryDirectory owns cleanup; no debug logs, fixed sample count.
        with tempfile.TemporaryDirectory(prefix="paste-lab-") as folder:
            root = Path(folder)
            bus = root / "private-bus.conf"
            bus.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + folder + '</listen>'
                           '<policy context="default"><allow send_destination="*"/><allow own="*"/>'
                           '<allow receive_sender="*"/></policy></busconfig>')
            # Put the sub-compositor's HOME and config in the disposable directory.
            env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": folder, "XDG_RUNTIME_DIR": folder,
                   "XDG_CONFIG_HOME": folder, "TMPDIR": folder, "GDK_BACKEND": "wayland", "WLR_BACKENDS": "x11",
                   "WLR_LIBINPUT_NO_DEVICES": "1", "WLR_RENDERER": "pixman", "LIBGL_ALWAYS_SOFTWARE": "1",
                   "MESA_SHADER_CACHE_DISABLE": "true",
                   "XDG_SESSION_TYPE": "wayland", "LANG": "C.UTF-8", "GTK_A11Y": "none", "GIO_USE_VFS": "local"}
            sp.run(["xvfb-run", "-a", "dbus-run-session", f"--config-file={bus}", "--", sys.executable, str(Path(__file__).resolve()), "run", folder],
                   env=env, check=True, timeout=21)
    else:
        sys.exit("Run this probe without arguments.")
