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
    toggle-block | start-block     arm in BLOCK mode: nothing typed until the utterance ends,
             then the whole final typed once (the tool's original output behavior)
    toggle-stream | start-stream   arm in STREAM mode: live partials typed as you speak
             (the configured default). Plain toggle/start follow [output] streaming, so a
             second keybind can select either mode against the SAME daemon.
    stop     disarm the mic (stop listening)
    status   pretty-print listening + mode + phase + partial + last final + uptime + device + mic
             + context-prompt + delivery (mode/state, reason/op when present)
    quit     request a clean daemon shutdown (releases GPU workers)
    cancel   drop the pending dictation fragment and keep listening (Backspace keybind fallback)
    session  print the most recent COMPLETED dictation session (arm→disarm recovery,
             R.6; never a moving draft). --copy stages it on the Wayland CLIPBOARD
             instead — exact bytes, no added newline, PRIMARY untouched, never
             types/erases/submits. Exit 1 when no completed session exists.

Usage:  voicectl <toggle|start|stop|status|cancel|quit|session>
        toggle-block | start-block   arm in BLOCK mode (whole final typed once at the end)
        toggle-stream| start-stream  arm in STREAM mode (live partials) — the config default
        (the full usage table is in the project README; this is the user-facing CLI surface.)

Stdlib-only: argparse, json, os, shutil, socket, subprocess, sys, threading, time + the shared
socket-path resolver from voice_typing.daemon.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

from voice_typing.daemon import (
    _default_control_socket_path,
)  # canonical resolver (P1.M4.T2.S1); reuse, do not duplicate

_COMMANDS: tuple[str, ...] = (
    "toggle",
    "start",
    "toggle-block",
    "toggle-stream",
    "start-block",
    "start-stream",
    "stop",
    "status",
    "quit",
    "cancel",
    "session",
)  # Rev 2 single-mode (P1.M1.T2.S3); 'cancel' = Backspace-cancel fallback (P1.M2.T7.S1);
# 'session' = R.6 recovery surface (P1.M6.T2.S3)
# Per-session output mode (2026-11-27): toggle-block / start-block arm in BLOCK mode (nothing
# typed until the utterance ends, then the whole final once); toggle-stream / start-stream arm
# in STREAM mode (live partials). Plain toggle/start keep the configured default ([output]
# streaming) — so two keybinds can share one daemon. The toggle-*/start-* commands take the
# SAME arm path as toggle/start (loading hint included); only the arm side honors the suffix.
# Migration shim (validation Issue 2): Rev 1's two-mode CLI survives in the wild — e.g. this
# machine's own pre-Rev-2 Hyprland keybind wrapper still ends in `voicectl toggle-lite`.
# main() remaps it to the canonical command BEFORE the _COMMANDS validation so stale callers
# keep working. Deliberately NOT a member of _COMMANDS and NOT listed in any help surface
# (--help / module docstring): the documented Rev 2 surface stays the six commands above.
_ALIASES: dict[str, str] = {"toggle-lite": "toggle"}

# BSD sysexits.h: command-line usage error. Usage errors (unknown/missing command) exit 64
# so exit 2 stays exclusive to "daemon not running" (PRD §4.8, bugfix Issue 7).
_EX_USAGE: int = 64
# Seconds an arm command (start/toggle) may block before voicectl prints a 'loading models…' hint to stderr.
# The FIRST arm blocks ~1–3 s while the daemon lazy-loads models (PRD §4.2bis); a resident arm replies in ms,
# so this fires ONLY on a real load (no flicker on instant arms). Tuned well below the ~1 s minimum load and
# well above local socket round-trip latency. (P1.M2.T1.S2.)
_LOADING_HINT_DELAY: float = 0.3
# VT-009 (2026-10): how long ANY voicectl command may block on the control socket before
# giving up (connect + read). The old makefile("r") read IGNORED the socket timeout, so a
# wedged daemon hung the keybind's `voicectl toggle` forever — the "stops responding to my
# shortcut" report. Overridable: VOICECTL_TIMEOUT=<seconds> (tests use it).
_SOCKET_TIMEOUT_S: float = 10.0

# P1.M6.T2.S3 (--copy): wl-clipboard tools + subprocess bounds. Absolute paths preferred
# (verified present on this machine) with a PATH fallback via shutil.which; a missing
# binary is a REPORTED copy failure (exit 1), never a typing fallback (PRD §4.2sexies R.3).
_WL_COPY = "/usr/bin/wl-copy"
_WL_PASTE = "/usr/bin/wl-paste"
_WL_STAGE_TIMEOUT_S = 5.0  # wl-copy subprocess timeout (fork-mode parent)
_WL_VERIFY_DEADLINE_S = 2.0  # total wl-paste verify poll budget
_WL_PASTE_TIMEOUT_S = 1.0  # each wl-paste attempt
_WL_VERIFY_POLL_S = 0.025  # poll interval


def _socket_timeout_s() -> float:
    """Resolve the socket timeout: $VOICECTL_TIMEOUT (seconds, parsed defensively) or the default."""
    raw = os.environ.get("VOICECTL_TIMEOUT")
    if not raw:
        return _SOCKET_TIMEOUT_S
    try:
        val = float(raw)
    except ValueError:
        return _SOCKET_TIMEOUT_S
    return val if val > 0 else _SOCKET_TIMEOUT_S


def format_result(cmd: str, response: dict) -> tuple[str, int]:
    """Render a daemon JSON response as (human-readable text, exit code) — PURE, no I/O.

    Exit code: 0 if response["ok"] is true, else 1 (logical failure). The text:
      - ok:false                      -> the daemon's error text ("error: <...>")
      - quit ({"ok":true,"shutting_down":true}) -> "shutting down"  (NO listening key -> branch first)
      - status                        -> multi-line: listening, mode, phase, partial, last_final, uptime,
                                        device, compute_type, mic, context-prompt, delivery +
                                        delivery reason/delivery op (only when non-empty)
                                        (PRD §4.8; mic per bugfix Issue 2; context-prompt P1.M2.T5.S2;
                                        delivery P1.M3.T3.S2 — PRD §4.2sexies R.5 status surface)
      - session                       -> the recovered session text, exactly (print adds the
                                        single terminal newline; P1.M6.T2.S3 — truncation is
                                        reported on stderr by main(), never here)
      - toggle/start/stop/cancel      -> "listening: on" / "listening: off"

    Defensive .get(...) everywhere so a missing key never raises (the protocol guarantees the 8-key
    block for toggle/start/stop/status, but .get keeps the unit tests + future shapes safe).
    """
    if response.get("ok") is not True:
        return f"error: {response.get('error', 'unknown error')}", 1
    if response.get(
        "shutting_down"
    ):  # quit reply (no listening key) -> branch BEFORE .get("listening")
        return "shutting down", 0
    if cmd == "status":
        listening = "on" if response.get("listening") else "off"
        phase = (
            response.get("phase", "") or ""
        )  # P1.M2.T2.S1: lifecycle phase (§4.2bis)
        mode = (
            response.get("mode", "normal") or "normal"
        )  # Rev 2: daemon constant "lite" (P1.M1.T2.S2); default kept defensive
        partial = response.get("partial", "") or ""
        last_final = response.get("last_final", "") or ""
        uptime = response.get("uptime_s", 0.0)
        device = response.get("device", "unknown")
        compute_type = response.get("compute_type", "unknown")
        load_error = (
            response.get("load_error", "") or ""
        )  # P1.M2.T2.S1: last load failure
        mic_ok = response.get(
            "mic_ok", True
        )  # bugfix Issue 2 / P1.M1.T2.S2: default True
        mic_error = (
            response.get("mic_error", "") or ""
        )  #   so a missing key never looks broken
        # P1.M2.T5.S2: rolling context-prompt state — the daemon sends the human label
        # (on / off (disabled by config) / off (degraded — context-free decoding) /
        # off (models not loaded)); a missing key (old daemon) reads as 'unknown'.
        context_prompt = response.get("context_prompt", "") or "unknown"
        # P1.M3.T3.S2: bulk-delivery status surface (PRD §4.2sexies R.5). Missing/empty keys
        # (old daemon / surface unwired) read as 'unknown' — the context_prompt tolerance
        # precedent. reason/op render ONLY when non-empty.
        delivery_mode = response.get("delivery_mode", "") or "unknown"
        delivery_state = response.get("delivery_state", "") or "unknown"
        delivery_reason = response.get("delivery_reason", "") or ""
        delivery_op = response.get("last_confirmed_op", "") or ""
        if mic_ok:
            mic_line = "mic: ok"
        elif mic_error:
            mic_line = f"mic: unavailable ({mic_error})"
        else:
            mic_line = "mic: unavailable"
        text = (
            f"listening: {listening}\n"
            f"mode: {mode}\n"
            f"output: {response.get('output_mode') or 'unknown'}\n"
            f"phase: {phase}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"{mic_line}\n"
            f"context-prompt: {context_prompt}\n"
            f"delivery: {delivery_mode} ({delivery_state})"
        )
        if delivery_reason:
            text += f"\ndelivery reason: {delivery_reason}"
        if delivery_op:
            text += f"\ndelivery op: {delivery_op}"
        if load_error:  # surface §4.2bis load failures (absent on the happy path)
            text += f"\nload error: {load_error}"
        return text, 0
    if cmd == "session":
        # P1.M6.T2.S3 (§4.2sexies R.6): stdout is EXACTLY the recovered text (print adds
        # the single terminal newline); truncation is reported on stderr by main(); the
        # ok:false none-case never reaches here (first branch → exit 1).
        session = response.get("session") or {}
        return session.get("text", "") or "", 0
    # toggle / start / stop / cancel (cancel is NOT an arm command: no loading hint, falls through
    # to the default branch — P1.M2.T7.S1)
    return f"listening: {'on' if response.get('listening') else 'off'}", 0


def send_command(socket_path: str, cmd: str, extra: dict | None = None) -> dict:
    """Open the control socket, send {"cmd": <cmd>}\\n, read ONE JSON line, return the parsed dict.

    `extra` payload keys are merged after 'cmd' (P1.M6.T2.S3: {"copy": true} for session
    --copy); the daemon ignores unknown keys, so old daemons fail safe (unknown command
    -> exit 1, clipboard untouched).

    Raises OSError (FileNotFoundError / ConnectionRefusedError / PermissionError) if the daemon is
    unreachable at connect time — caller maps to exit 2. Raises ValueError if the daemon replies with
    an empty or non-JSON line (a protocol error) — caller maps to exit 1 — or if the daemon accepts
    the connection but never replies within the socket timeout (WEDGED — previously this hung
    FOREVER: makefile("r") silently ignores settimeout). Reads exactly ONE line then closes
    (voicectl is one-shot).
    """
    timeout = _socket_timeout_s()
    line = ""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)  # bounds connect AND every recv (the wedge guard)
        sock.connect(
            socket_path
        )  # raises FileNotFoundError/ConnectionRefusedError/PermissionError
        sock.sendall((json.dumps({"cmd": cmd, **(extra or {})}) + "\n").encode("utf-8"))
        buf = bytearray()
        try:
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
        except socket.timeout:
            raise ValueError(
                f"daemon wedged: no reply within {timeout:.0f}s "
                "(systemctl --user restart voice-typing to recover)"
            ) from None
        line = bytes(buf).split(b"\n", 1)[0].decode("utf-8", errors="replace")
    if not line:
        raise ValueError("daemon closed the connection without replying")
    return json.loads(line)  # json.JSONDecodeError is a ValueError subclass


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
        lambda: print(
            "loading models… (first arm, ~1–3 s)", file=sys.stderr, flush=True
        ),
    )
    timer.daemon = True
    timer.start()
    try:
        return send_command(socket_path, cmd)
    finally:
        timer.cancel()


def _resolve_tool(preferred: str, name: str) -> str | None:
    """Absolute-path-first tool resolver (P1.M6.T2.S3): use the pinned path when it exists,
    else fall back to $PATH via shutil.which. None = not installed (a REPORTED copy failure).
    """
    return preferred if os.path.exists(preferred) else shutil.which(name)


def _copy_session_to_clipboard(text: str) -> tuple[bool, str]:
    """Stage `text` on the Wayland CLIPBOARD — exact UTF-8 bytes, NO added newline —
    and verify the round-trip. Returns (ok, error detail).

    Stage: wl-copy FORK MODE (no --foreground — it blocks until the selection is
    replaced; a CLI hang risk). Source-verified: wl-copy's parent exits 0 only AFTER
    set_selection + roundtrip, so exit 0 means the selection is registered; the
    forked child serves it until the next selection (normal paste UX). Verify:
    `wl-paste --no-newline` stdout must BYTE-EQUAL the staged bytes (wl-paste always
    appends \\n without --no-newline); bounded poll — a fresh connection can see the
    new selection one event-loop turn later. PRIMARY untouched (no --primary); no
    --paste-once (a history-manager read would consume the offer); no --trim-newline
    (we add no newline). NEVER types/erases/submits: the only subprocesses are
    wl-copy and wl-paste (PRD §4.2sexies R.6; research/wlclipboard_external.md).
    """
    wl_copy = _resolve_tool(_WL_COPY, "wl-copy")
    if wl_copy is None:
        return False, "wl-copy not found (install wl-clipboard)"
    wl_paste = _resolve_tool(_WL_PASTE, "wl-paste")
    if wl_paste is None:
        return False, "wl-paste not found (install wl-clipboard)"
    payload = text.encode("utf-8")
    try:
        staged = subprocess.run(
            [wl_copy, "--type", "text/plain;charset=utf-8"],
            input=payload,
            capture_output=True,
            timeout=_WL_STAGE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, "wl-copy timed out staging the clipboard"
    if staged.returncode != 0:
        lines = staged.stderr.decode("utf-8", errors="replace").strip().splitlines()
        first = lines[0] if lines else f"exit {staged.returncode}"
        return False, f"wl-copy failed: {first}"
    deadline = time.monotonic() + _WL_VERIFY_DEADLINE_S
    while True:
        try:
            readback = subprocess.run(
                [wl_paste, "--no-newline"],
                capture_output=True,
                timeout=_WL_PASTE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return False, "wl-paste timed out verifying the clipboard"
        if readback.returncode == 0 and readback.stdout == payload:
            return True, ""
        if time.monotonic() >= deadline:
            return False, (
                "clipboard verification failed (content did not match within "
                f"{_WL_VERIFY_DEADLINE_S:.0f}s)"
            )
        time.sleep(_WL_VERIFY_POLL_S)


def _build_parser() -> argparse.ArgumentParser:
    """argparse with one optional positional `cmd`. choices validation is intentionally NOT done
    here — main() validates against _COMMANDS so usage errors map to exit 64 (EX_USAGE), not
    argparse's SystemExit(2) which would collide with the daemon-not-running code (PRD §4.8)."""
    parser = argparse.ArgumentParser(
        prog="voicectl",
        # Raw: the help text is rendered verbatim. The default formatter re-wraps the epilog
        # and textwrap splits hyphenated tokens at a line boundary (toggle-\nblock), so the
        # per-session mode commands could vanish from `--help` on narrow terminals.
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Control the voice-typing daemon. Connects to the control socket, sends one command, "
            "prints the result. Exits 0 on success, 1 on a logical failure, 2 if the daemon is not "
            "running, 64 on a usage error (unknown/missing command)."
        ),
        epilog=(
            "subcommands: toggle, start, stop, status, quit, cancel, session [--copy]"
            "  (see the project README for the full usage table)\n"
            "per-session output mode: toggle-block | start-block   arm in BLOCK mode (nothing typed\n"
            "until the utterance ends, then the whole final once); toggle-stream | start-stream\n"
            "arm in STREAM mode (live partials — the configured default). Plain toggle/start\n"
            "follow [output] streaming, so two keybinds can pick either mode on one daemon."
        ),
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        help="toggle | start | stop | status | quit | cancel | session",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="with 'session': copy the recovered text to the Wayland clipboard (exact "
        "bytes, no added newline, PRIMARY untouched) instead of printing it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """voicectl entry point: parse -> validate command -> resolve socket -> send -> format -> print.

    Returns 0 (success), 1 (logical failure / protocol error), 2 (daemon not running), or
    64 (usage error — unknown/missing command, BSD EX_USAGE). NEVER raises on the usage path:
    every path returns an int (the [project.scripts] wrapper does sys.exit(main())). The command
    is validated HERE (not by argparse choices) so usage errors map to 64 while 2 stays exclusive
    to daemon-not-running (PRD §4.8, bugfix Issue 7). --help still exits 0 via argparse as usual.

    Migration (validation Issue 2): a command found in _ALIASES ('toggle-lite') is remapped to
    its canonical name BEFORE validation, so a Rev 1 caller arms dictation instead of dying
    with exit 64. Unknown names are untouched by the remap and still exit 64.

    session (P1.M6.T2.S3): prints the most recent COMPLETED dictation session; --copy stages
    it on the Wayland clipboard instead (exact bytes, byte-verified via wl-paste --no-newline)
    and prints 'copied N chars'. Exit 1 when no completed session exists (clipboard untouched —
    the ok:false reply rides format_result's error branch before any copy code runs). --copy
    with a non-session command is a usage error (64). Truncation (store cap) is reported on
    stderr only; stdout stays the exact recovered text.
    """
    args = _build_parser().parse_args(argv)
    cmd: str | None = args.cmd  # None when no command given (positional is nargs='?')
    if cmd is not None:
        cmd = _ALIASES.get(
            cmd, cmd
        )  # deprecated Rev 1 names -> canonical (validation Issue 2); unknown names pass through
    if cmd not in _COMMANDS:  # missing (None) or unknown string -> usage error
        if cmd is None:
            print(
                f"voicectl: a command is required; choose from {', '.join(_COMMANDS)}",
                file=sys.stderr,
            )
        else:
            print(
                f"voicectl: invalid command {cmd!r}; choose from {', '.join(_COMMANDS)}",
                file=sys.stderr,
            )
        return _EX_USAGE
    if args.copy and cmd != "session":
        print("voicectl: --copy applies only to the 'session' command", file=sys.stderr)
        return _EX_USAGE

    # 1. Resolve the socket path. XDG_RUNTIME_DIR unset -> RuntimeError -> daemon can't be running.
    try:
        socket_path = _default_control_socket_path()
    except RuntimeError:
        print(
            "voicectl: daemon not running (XDG_RUNTIME_DIR is not set)", file=sys.stderr
        )
        return 2

    # 2. Talk to the daemon. Connect OSError -> exit 2; protocol ValueError -> exit 1.
    #    start/toggle may block ~1–3 s on the COLD FIRST ARM (PRD §4.2bis lazy load of the single
    #    model); route them through _send_command_with_loading_hint so voicectl prints a 'loading
    #    models…' hint if the reply is slow (resident arms reply in ms → no hint).
    #    stop/status/quit/cancel/session use plain send_command (cancel is NOT an arm command;
    #    P1.M2.T7.S1). session passes {"copy": true} on the wire when --copy was given (the
    #    daemon logs it; the copy itself is CLIENT-side — P1.M6.T2.S3).
    try:
        extra = {"copy": True} if (cmd == "session" and args.copy) else None
        # Per-session mode commands (toggle-*/start-*) take the SAME arm path -> loading hint.
        if cmd in ("start", "toggle") or cmd.startswith(("start-", "toggle-")):
            response = _send_command_with_loading_hint(socket_path, cmd)
        else:
            response = send_command(socket_path, cmd, extra=extra)
    except (
        OSError
    ) as exc:  # FileNotFoundError / ConnectionRefusedError / PermissionError
        print(f"voicectl: daemon not running ({exc.strerror or exc})", file=sys.stderr)
        return 2
    except ValueError as exc:  # empty / malformed response line
        print(f"voicectl: {exc}", file=sys.stderr)
        return 1

    # 3. Format + print the human result; return the exit code.
    text, code = format_result(cmd, response)
    if cmd == "session" and code == 0:
        # P1.M6.T2.S3: truncation warning -> STDERR (stdout purity); then either the
        # --copy flow (stage + verify + 'copied N chars') or the plain print below. The
        # none-case never gets here: ok:false -> code 1 from format_result's first branch.
        session = response.get("session") or {}
        if session.get("truncated"):
            dropped = session.get("finals_dropped", 0)
            print(
                f"voicectl: session was truncated ({dropped} finals dropped by the "
                "1 MiB cap; the newest text that fits is shown)",
                file=sys.stderr,
            )
        if args.copy:
            copied, detail = _copy_session_to_clipboard(text)
            if not copied:
                print(f"voicectl: {detail}", file=sys.stderr)
                return 1
            print(f"copied {len(text)} chars")
            return 0
    print(text)
    return code


if __name__ == "__main__":
    # Console-script-style guard (matches voice_typing/cuda_check.py). sys.exit propagates main()'s
    # exit code to the shell. (The [project.scripts] `voicectl` wrapper already does sys.exit(main()).)
    sys.exit(main())
