"""voicectl — command-line client for the voice-typing daemon (PRD §4.8, §4 architecture).

Connects to the daemon's AF_UNIX control socket ($XDG_RUNTIME_DIR/voice-typing/control.sock,
P1.M4.T2.S1), sends ONE JSON line {"cmd": <cmd>}, reads ONE JSON-line response, prints a
human-readable result, and exits:

    0  success            (daemon replied {"ok": true, ...})
    1  logical failure    (daemon replied {"ok": false, "error": ...})
    2  daemon not running (socket absent / connection refused / XDG_RUNTIME_DIR unset)

Subcommands (PRD §4.8):

    toggle   arm/disarm the mic (flip the listening gate)
    start    arm the mic (start listening)
    stop     disarm the mic (stop listening)
    status   pretty-print listening + partial + last final + uptime + device + loaded models
    quit     request a clean daemon shutdown (releases GPU workers)

Usage:  voicectl <toggle|start|stop|status|quit>
        (the full usage table is in the project README; this is the user-facing CLI surface.)

Stdlib-only: argparse, json, socket, sys + the shared socket-path resolver from voice_typing.daemon.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys

from voice_typing.daemon import _default_control_socket_path  # canonical resolver (P1.M4.T2.S1); reuse, do not duplicate

_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit")


def format_result(cmd: str, response: dict) -> tuple[str, int]:
    """Render a daemon JSON response as (human-readable text, exit code) — PURE, no I/O.

    Exit code: 0 if response["ok"] is true, else 1 (logical failure). The text:
      - ok:false                      -> the daemon's error text ("error: <...>")
      - quit ({"ok":true,"shutting_down":true}) -> "shutting down"  (NO listening key -> branch first)
      - status                        -> multi-line: listening, partial, last_final, uptime, device,
                                        compute_type, final_model, realtime_model, mic  (PRD §4.8 "incl.
                                        partial and models loaded"; mic health per bugfix Issue 2)
      - toggle/start/stop             -> "listening: on" / "listening: off"

    Defensive .get(...) everywhere so a missing key never raises (the protocol guarantees the 8-key
    block for toggle/start/stop/status, but .get keeps the unit tests + future shapes safe).
    """
    if response.get("ok") is not True:
        return f"error: {response.get('error', 'unknown error')}", 1
    if response.get("shutting_down"):           # quit reply (no listening key) -> branch BEFORE .get("listening")
        return "shutting down", 0
    if cmd == "status":
        listening = "on" if response.get("listening") else "off"
        partial = response.get("partial", "") or ""
        last_final = response.get("last_final", "") or ""
        uptime = response.get("uptime_s", 0.0)
        device = response.get("device", "unknown")
        compute_type = response.get("compute_type", "unknown")
        final_model = response.get("final_model", "unknown")
        realtime_model = response.get("realtime_model", "unknown")
        mic_ok = response.get("mic_ok", True)             # bugfix Issue 2 / P1.M1.T2.S2: default True
        mic_error = response.get("mic_error", "") or ""   #   so a missing key never looks broken
        if mic_ok:
            mic_line = "mic: ok"
        elif mic_error:
            mic_line = f"mic: unavailable ({mic_error})"
        else:
            mic_line = "mic: unavailable"
        text = (
            f"listening: {listening}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"models: {final_model} + {realtime_model}\n"
            f"{mic_line}"
        )
        return text, 0
    # toggle / start / stop
    return f"listening: {'on' if response.get('listening') else 'off'}", 0


def send_command(socket_path: str, cmd: str) -> dict:
    """Open the control socket, send {"cmd": <cmd>}\\n, read ONE JSON line, return the parsed dict.

    Raises OSError (FileNotFoundError / ConnectionRefusedError / PermissionError) if the daemon is
    unreachable at connect time — caller maps to exit 2. Raises ValueError if the daemon replies with
    an empty or non-JSON line (a protocol error) — caller maps to exit 1. Uses makefile("r") (NOT
    settimeout — makefile raises if the socket has a timeout, P1.M4.T2.S1 §3). Reads exactly ONE line
    then closes (voicectl is one-shot).
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(socket_path)   # raises FileNotFoundError/ConnectionRefusedError/PermissionError
        sock.sendall((json.dumps({"cmd": cmd}) + "\n").encode("utf-8"))
        with sock.makefile("r", encoding="utf-8", newline="\n") as rfile:
            line = rfile.readline()
    if not line:
        raise ValueError("daemon closed the connection without replying")
    return json.loads(line)         # json.JSONDecodeError is a ValueError subclass


def _build_parser() -> argparse.ArgumentParser:
    """argparse with one positional `cmd` over the 5 subcommands (Mode A doc surface)."""
    parser = argparse.ArgumentParser(
        prog="voicectl",
        description=(
            "Control the voice-typing daemon. Connects to the control socket, sends one command, "
            "prints the result. Exits 0 on success, 1 on a logical failure, 2 if the daemon is not running."
        ),
        epilog="subcommands: toggle, start, stop, status, quit  (see the project README for the full usage table)",
    )
    parser.add_argument(
        "cmd",
        choices=_COMMANDS,
        help="toggle | start | stop | status | quit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """voicectl entry point: parse -> resolve socket -> send -> format -> print -> return exit code.

    Returns 0 (success), 1 (logical failure / protocol error), or 2 (daemon not running). NEVER
    raises: every path returns an int (the [project.scripts] wrapper does sys.exit(main())). argparse
    handles usage errors itself (SystemExit 2 on an unknown choice — a usage error, not a daemon
    status; G7).
    """
    args = _build_parser().parse_args(argv)
    cmd: str = args.cmd

    # 1. Resolve the socket path. XDG_RUNTIME_DIR unset -> RuntimeError -> daemon can't be running.
    try:
        socket_path = _default_control_socket_path()
    except RuntimeError:
        print("voicectl: daemon not running (XDG_RUNTIME_DIR is not set)", file=sys.stderr)
        return 2

    # 2. Talk to the daemon. Connect OSError -> exit 2; protocol ValueError -> exit 1.
    try:
        response = send_command(socket_path, cmd)
    except OSError as exc:                       # FileNotFoundError / ConnectionRefusedError / PermissionError
        print(f"voicectl: daemon not running ({exc.strerror or exc})", file=sys.stderr)
        return 2
    except ValueError as exc:                    # empty / malformed response line
        print(f"voicectl: {exc}", file=sys.stderr)
        return 1

    # 3. Format + print the human result; return the exit code.
    text, code = format_result(cmd, response)
    print(text)
    return code


if __name__ == "__main__":
    # Console-script-style guard (matches voice_typing/cuda_check.py). sys.exit propagates main()'s
    # exit code to the shell. (The [project.scripts] `voicectl` wrapper already does sys.exit(main()).)
    sys.exit(main())
