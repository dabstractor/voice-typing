"""voicectl — command-line client for the voice-typing daemon (PRD §4.8, §4 architecture).

Connects to the daemon's AF_UNIX control socket ($XDG_RUNTIME_DIR/voice-typing/control.sock,
P1.M4.T2.S1), sends ONE JSON line {"cmd": <cmd>}, reads ONE JSON-line response, prints a
human-readable result, and exits:

    0  success            (daemon replied {"ok": true, ...})
    1  logical failure    (daemon replied {"ok": false, "error": ...})
    2  daemon not running (socket absent / connection refused / XDG_RUNTIME_DIR unset) — EXCLUSIVE
    64 usage error        (unknown or missing command — BSD EX_USAGE)

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
import threading

from voice_typing.daemon import _default_control_socket_path  # canonical resolver (P1.M4.T2.S1); reuse, do not duplicate

_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite")
# BSD sysexits.h: command-line usage error. Usage errors (unknown/missing command) exit 64
# so exit 2 stays exclusive to "daemon not running" (PRD §4.8, bugfix Issue 7).
_EX_USAGE: int = 64
# Seconds an arm command (start/toggle) may block before voicectl prints a 'loading models…' hint to stderr.
# The FIRST arm blocks ~1–3 s while the daemon lazy-loads models (PRD §4.2bis); a resident arm replies in ms,
# so this fires ONLY on a real load (no flicker on instant arms). Tuned well below the ~1 s minimum load and
# well above local socket round-trip latency. (P1.M2.T1.S2.)
_LOADING_HINT_DELAY: float = 0.3


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
        phase = response.get("phase", "") or ""                       # P1.M2.T2.S1: lifecycle phase (§4.2bis)
        mode = response.get("mode", "normal") or "normal"              # PRD §4.2ter: normal | lite
        partial = response.get("partial", "") or ""
        last_final = response.get("last_final", "") or ""
        uptime = response.get("uptime_s", 0.0)
        device = response.get("device", "unknown")
        compute_type = response.get("compute_type", "unknown")
        final_model = response.get("final_model", "unknown")
        realtime_model = response.get("realtime_model", "unknown")
        models_loaded = response.get("models_loaded", False)          # P1.M2.T2.S1: models resident?
        load_error = response.get("load_error", "") or ""            # P1.M2.T2.S1: last load failure
        mic_ok = response.get("mic_ok", True)             # bugfix Issue 2 / P1.M1.T2.S2: default True
        mic_error = response.get("mic_error", "") or ""   #   so a missing key never looks broken
        if mic_ok:
            mic_line = "mic: ok"
        elif mic_error:
            mic_line = f"mic: unavailable ({mic_error})"
        else:
            mic_line = "mic: unavailable"
        loaded_marker = "loaded" if models_loaded else "not loaded"   # distinguishes loaded from loading/unloaded
        text = (
            f"listening: {listening}\n"
            f"mode: {mode}\n"
            f"phase: {phase}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"models: {final_model} + {realtime_model} ({loaded_marker})\n"
            f"{mic_line}"
        )
        if load_error:                                     # surface §4.2bis load failures (absent on the happy path)
            text += f"\nload error: {load_error}"
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


def _send_command_with_loading_hint(socket_path: str, cmd: str) -> dict:
    """send_command for start/toggle: print a 'loading models…' hint to stderr if the daemon doesn't reply
    within _LOADING_HINT_DELAY (PRD §4.2bis — "voicectl prints a loading models… hint" while the first arm blocks).

    Why CLIENT-SIDE: start()/toggle() block inside the daemon's _load_recorder() (~1–3 s), so the JSON response
    is produced only AFTER the load completes — an in-band 'loading' signal is impossible under the one-line-
    request/one-line-response protocol. Why a Timer (not socket timeout): send_command uses makefile('r'),
    which is incompatible with settimeout. The hint goes to STDERR so stdout (the structured result) stays
    clean for scripts; the Timer is cancelled in `finally`, so a fast (resident) arm never prints it.
    """
    timer = threading.Timer(
        _LOADING_HINT_DELAY,
        lambda: print("loading models… (first arm, ~1–3 s)", file=sys.stderr, flush=True),
    )
    timer.daemon = True
    timer.start()
    try:
        return send_command(socket_path, cmd)
    finally:
        timer.cancel()


def _build_parser() -> argparse.ArgumentParser:
    """argparse with one optional positional `cmd`. choices validation is intentionally NOT done
    here — main() validates against _COMMANDS so usage errors map to exit 64 (EX_USAGE), not
    argparse's SystemExit(2) which would collide with the daemon-not-running code (PRD §4.8)."""
    parser = argparse.ArgumentParser(
        prog="voicectl",
        description=(
            "Control the voice-typing daemon. Connects to the control socket, sends one command, "
            "prints the result. Exits 0 on success, 1 on a logical failure, 2 if the daemon is not "
            "running, 64 on a usage error (unknown/missing command)."
        ),
        epilog="subcommands: toggle, start, stop, status, quit  (see the project README for the full usage table)",
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        help="toggle | start | stop | status | quit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """voicectl entry point: parse -> validate command -> resolve socket -> send -> format -> print.

    Returns 0 (success), 1 (logical failure / protocol error), 2 (daemon not running), or
    64 (usage error — unknown/missing command, BSD EX_USAGE). NEVER raises on the usage path:
    every path returns an int (the [project.scripts] wrapper does sys.exit(main())). The command
    is validated HERE (not by argparse choices) so usage errors map to 64 while 2 stays exclusive
    to daemon-not-running (PRD §4.8, bugfix Issue 7). --help still exits 0 via argparse as usual.
    """
    args = _build_parser().parse_args(argv)
    cmd: str | None = args.cmd          # None when no command given (positional is nargs='?')
    if cmd not in _COMMANDS:            # missing (None) or unknown string -> usage error
        if cmd is None:
            print(f"voicectl: a command is required; choose from {', '.join(_COMMANDS)}", file=sys.stderr)
        else:
            print(f"voicectl: invalid command {cmd!r}; choose from {', '.join(_COMMANDS)}", file=sys.stderr)
        return _EX_USAGE

    # 1. Resolve the socket path. XDG_RUNTIME_DIR unset -> RuntimeError -> daemon can't be running.
    try:
        socket_path = _default_control_socket_path()
    except RuntimeError:
        print("voicectl: daemon not running (XDG_RUNTIME_DIR is not set)", file=sys.stderr)
        return 2

    # 2. Talk to the daemon. Connect OSError -> exit 2; protocol ValueError -> exit 1.
    #    start/toggle (and their lite variants) may block ~1–3 s on a cold arm or a mode-switch
    #    reload (PRD §4.2bis/§4.2ter) while the daemon lazy-loads models; route them through
    #    _send_command_with_loading_hint so voicectl prints a 'loading models…' hint if the reply is
    #    slow (resident, same-mode arms reply in ms → no hint). stop/status/quit use plain send_command.
    try:
        if cmd in ("start", "toggle", "start-lite", "toggle-lite"):
            response = _send_command_with_loading_hint(socket_path, cmd)
        else:
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
