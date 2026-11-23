#!/usr/bin/env python3
"""pi-seam proof lab (P1.M5.T1.S1) — env-gated, NOT pytest-collected.

Drives a REAL `pi` in a detached tmux pane through the pi-editor.sock op matrix
and asserts buffer truth + visible render. This is the "prove FIRST" artifact:
proof that our own seam works (a failure here is a bug in the extension, not an
external measurement).

Usage:
    timeout 240 env PI_SEAM_LAB=1 .venv/bin/python tests/pi_seam_lab.py   # full matrix
    timeout 240 env PI_SEAM_LAB=1 PI_SEAM_LAB_PHASE=minimal …            # insert/read only

House discipline (AGENTS.md): inner GNU timeout (caller) + this lab bounds every
wait; ONE mktemp scratch dir under /tmp removed in `finally`; teardown on EVERY
exit path (tmux kill-server + socket unlink); no unbounded logs (reply lines are
truncated before printing); isolation — no daemon control, service manager, audio-tool, or clipboard calls.

Matrix (full phase; capture happens BEFORE cancel because cancel removes the
owned text — the PRP's step-8 "capture contains 'edge seam'" assertion is
preserved, just ordered honestly):

    1  insert ascii      -> applied; read endswith probe
    2  insert unicode    -> read round-trips EXACTLY (UTF-16 units intact)
    3  replace owned     -> applied; read text exact ("pi seam" -> "edge seam")
    4  replace zero-diff -> unchanged; changes == 0 (R.1: zero-diff = zero events)
    5  replace outside   -> refused (out_of_bounds / not owned)
    6  capture-pane      -> contains "edge seam" (buffer is REALLY rendered)
    7  cancel            -> applied; read: owned == null; buffer == pre-cancel minus owned
    8  insert "again" + delegated tmux send-keys "x"
                         -> ONE takeover event <= 3s; read dirty == true;
                            our own writes never emitted takeover
    9  read final        -> recorded for the evidence doc
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests"))

from pi_seam_support import (  # noqa: E402
    ASCII_PROBE,
    OpRequest,
    build_probe_payloads,
    classify_event,
    classify_reply,
    expected_matrix,
    is_event,
)

GATE_ENV = "PI_SEAM_LAB"
PHASE_ENV = "PI_SEAM_LAB_PHASE"  # "minimal" | "full" (default full)
PHASE_MINIMAL = "minimal"
SOCK_REL = "voice-typing/pi-editor.sock"
TMUX_SOCK = "vtseam"  # dedicated tmux server socket — hermetic vs the user's sessions
SESS = "vtseam"
SOCK_WAIT_S = 20
SETTLE_S = 6  # pi re-fires session_start (resume wave) for a few seconds after the socket appears
EVENT_WAIT_S = 3
CAPTURE_WAIT_S = 15
EVIDENCE_LINE_CAP = 240  # chars per printed evidence line (bounded output)
PROOF_TABLE_CAP = 120

failures: list[str] = []
results: list[dict[str, str]] = []


def check(step: str, request: str, cond: bool, detail: str) -> None:
    results.append(
        {
            "step": step,
            "request": request,
            "result": "pass" if cond else "FAIL",
            "detail": detail[:EVIDENCE_LINE_CAP],
        }
    )
    line = f"[{'ok ' if cond else 'FAIL'}] {step}: {request} — {detail[:EVIDENCE_LINE_CAP]}"
    print(line, flush=True)
    if not cond:
        failures.append(f"{step}: {request} — {detail[:EVIDENCE_LINE_CAP]}")


def ev(*parts: object) -> None:
    print("   ", " ".join(str(p) for p in parts)[:EVIDENCE_LINE_CAP], flush=True)


# ---------------------------------------------------------------------------
# JSONL client (reader thread; unrequested event lines are queued, never lost)
# ---------------------------------------------------------------------------


class SeamClient:
    def __init__(self, sock_path: str):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        self.sock.connect(sock_path)
        self.lines: queue.Queue[str] = queue.Queue()
        self.seen_events: list[dict] = []  # every unrequested event line observed
        self._alive = True
        self._t = threading.Thread(target=self._pump, daemon=True)
        self._t.start()

    def _pump(self) -> None:
        f = self.sock.makefile("r", encoding="utf-8", newline="\n")
        try:
            for line in f:
                self.lines.put(line.rstrip("\n"))
        except OSError:
            pass
        finally:
            self._alive = False

    def request(self, req: OpRequest, timeout: float = 10.0) -> dict:
        """Send one op; return the classified reply (raises on vocabulary violation)."""
        self.sock.sendall((req.encode() + "\n").encode("utf-8"))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            raw = json.loads(line)
            if is_event(raw):
                self.seen_events.append(classify_event(raw).__dict__)
                continue
            return classify_reply(raw)  # validates closed vocabularies
        raise TimeoutError(f"no reply for {req.encode()!r} within {timeout}s")

    def wait_event(self, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            raw = json.loads(line)
            if is_event(raw):
                classified = classify_event(raw)
                self.seen_events.append(classified.__dict__)
                return {"raw": raw, "classified": classified, "line": line}
            ev("non-event line while waiting for event:", line[:EVIDENCE_LINE_CAP])
        return None

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# tmux helpers
# ---------------------------------------------------------------------------


def tmux(*args: str, timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["tmux", "-L", TMUX_SOCK, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def spawn_pi(sock_path: str) -> None:
    pi_bin = os.environ.get("PI_BIN") or shutil.which("pi")
    if not pi_bin:
        raise SystemExit("pi not found on PATH — set PI_BIN")
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env_cmd = [
        "env",
        "TERM=xterm-256color",
        f"XDG_RUNTIME_DIR={xdg}",  # G7: the tmux server may predate the shell env
        f"HOME={os.environ.get('HOME', os.path.expanduser('~'))}",
        f"PATH={os.environ.get('PATH', '')}",
        pi_bin,
    ]
    res = tmux(
        "-f",
        "/dev/null",
        "new-session",
        "-d",
        "-s",
        SESS,
        "-x",
        "140",
        "-y",
        "45",
        "-c",
        str(REPO),
        " ".join(env_cmd),
    )
    if res.returncode != 0:
        raise SystemExit(f"tmux new-session failed: {res.stderr.strip()}")


def wait_for_socket(sock_path: str) -> bool:
    deadline = time.monotonic() + SOCK_WAIT_S
    while time.monotonic() < deadline:
        if os.path.exists(sock_path):
            try:  # must actually accept, not merely exist as a stale file
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                probe.settimeout(1.0)
                probe.connect(sock_path)
                probe.close()
                return True
            except OSError:
                pass
        time.sleep(0.4)
    return False


def capture_pane() -> str:
    res = tmux("capture-pane", "-t", SESS, "-p")
    return res.stdout


def teardown(sock_path: str, scratch: str | None) -> None:
    subprocess.run(
        ["tmux", "-L", TMUX_SOCK, "kill-server"], capture_output=True, timeout=15
    )
    try:
        os.unlink(sock_path)
    except OSError:
        pass
    if scratch:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------


def run_matrix(client: SeamClient, phase: str) -> None:
    oracle = expected_matrix()
    base = client.request(OpRequest("read"))
    prefix = base.text or ""
    p = build_probe_payloads(prefix)
    check(
        "0",
        "read",
        base.ok and base.units == "utf-16" and base.owned is None,
        f"baseline text={prefix!r} cursor={base.cursor} owned={base.owned} dirty={base.dirty} units={base.units}",
    )

    # 1 — insert ascii
    r1 = client.request(OpRequest("insert", text=p["ascii"]))
    ok1 = str(r1.result) in oracle["insert"] and r1.cursor is not None
    rd = client.request(OpRequest("read"))
    check(
        "1",
        "insert ascii",
        ok1 and (rd.text or "").endswith(p["ascii"]),
        f"reply={r1.result} cursor={r1.cursor} changes={r1.changes} read_tail={(rd.text or '')[-40:]!r}",
    )

    # 2 — insert unicode (round-trip, UTF-16 units intact)
    r2 = client.request(OpRequest("insert", text=p["unicode"]))
    rd = client.request(OpRequest("read"))
    expected = prefix + p["ascii"] + p["unicode"]
    check(
        "2",
        "insert unicode",
        r2.result == "applied" and rd.text == expected,
        f"exact round-trip ok={rd.text == expected} cursor={rd.cursor}",
    )

    if phase == PHASE_MINIMAL:
        cap = wait_for_capture(ASCII_PROBE)
        check(
            "m",
            "capture-pane",
            ASCII_PROBE in cap,
            "visible render contains ascii probe",
        )
        return

    # 3 — replace owned tail
    r3 = client.request(
        OpRequest(
            "replace",
            text=p["replace_new"],
            start=p["replace_start"],
            end=p["replace_end"],
        )
    )
    rd = client.request(OpRequest("read"))
    expected = (
        prefix + p["ascii"].replace(p["replace_old"], p["replace_new"]) + p["unicode"]
    )
    check(
        "3",
        "replace owned",
        r3.result == "applied" and rd.text == expected,
        f"reply={r3} exact={rd.text == expected}",
    )

    # 4 — zero-diff replace (identical text, same range) -> unchanged, changes == 0
    r4 = client.request(
        OpRequest(
            "replace",
            text=p["zero_diff_text"],
            start=p["zero_diff_start"],
            end=p["zero_diff_end"],
        )
    )
    check(
        "4",
        "replace zero-diff",
        r4.result == "unchanged" and r4.changes == 0,
        f"reply={r4}",
    )

    # 5 — replace outside owned -> refused
    r5 = client.request(
        OpRequest(
            "replace", text=p["replace_new"], start=p["oob_start"], end=p["oob_end"]
        )
    )
    check(
        "5",
        "replace outside owned",
        r5.result == "refused" and r5.reason is not None,
        f"reply={r5}",
    )

    # 6 — visible render BEFORE cancel (cancel removes the owned text)
    cap = wait_for_capture(p["replace_new"])
    check(
        "6",
        "capture-pane",
        p["replace_new"] in cap,
        f"visible render contains {p['replace_new']!r}",
    )

    # 7 — cancel removes the owned range in ONE op
    pre = client.request(OpRequest("read"))
    r7 = client.request(OpRequest("cancel"))
    rd = client.request(OpRequest("read"))
    pre_text, pre_owned = pre.text or "", pre.owned
    expect_after = (
        pre_text[: pre_owned[0]] + pre_text[pre_owned[1] :] if pre_owned else pre_text
    )
    check(
        "7",
        "cancel",
        r7.result == "applied"
        and rd.owned is None
        and rd.dirty is False
        and rd.text == expect_after,
        f"reply={r7.result} owned={rd.owned} dirty={rd.dirty} buffer_after={rd.text!r} expected={expect_after!r}",
    )

    # 8 — re-own, then a delegated REAL keystroke must push exactly one takeover event
    zero_own_events = (
        not client.seen_events
    )  # our own socket writes must never emit takeover
    r8 = client.request(OpRequest("insert", text=p["owned_after_cancel_probe"]))
    owned_rd = client.request(OpRequest("read"))
    had_owned = (
        r8.result == "applied"
        and owned_rd.owned is not None
        and owned_rd.dirty is False
    )
    subprocess.run(
        ["tmux", "-L", TMUX_SOCK, "send-keys", "-t", SESS, "-l", "x"],
        capture_output=True,
        timeout=15,
    )
    evt = client.wait_event(EVENT_WAIT_S)
    rd = client.request(OpRequest("read"))
    check(
        "8",
        "send-keys x -> takeover",
        zero_own_events
        and had_owned
        and evt is not None
        and evt["classified"].event == "takeover"
        and evt["classified"].source == "key"
        and rd.dirty is True,
        f"own-writes-tookover={not zero_own_events} "
        f"event={evt['line'][:EVIDENCE_LINE_CAP] if evt else None} dirty={rd.dirty} text={rd.text!r}",
    )

    # 9 — final state for the evidence record
    check(
        "9",
        "read final",
        rd.ok,
        f"text={rd.text!r} cursor={rd.cursor} owned={rd.owned} dirty={rd.dirty}",
    )


def wait_for_capture(needle: str) -> str:
    deadline = time.monotonic() + CAPTURE_WAIT_S
    cap = ""
    while time.monotonic() < deadline:
        cap = capture_pane()
        if needle in cap:
            return cap
        time.sleep(0.5)
    return cap


def main() -> int:
    if os.environ.get(GATE_ENV) != "1":
        print(__doc__.strip().splitlines()[0])
        print(
            f"refusing to run without {GATE_ENV}=1 (spawns tmux + a real pi)",
            file=sys.stderr,
        )
        return 2
    phase = os.environ.get(PHASE_ENV, "full")
    if phase not in {PHASE_MINIMAL, "full"}:
        print(f"{PHASE_ENV} must be 'minimal' or 'full'", file=sys.stderr)
        return 2

    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    sock_path = os.path.join(xdg, SOCK_REL)
    scratch = tempfile.mkdtemp(prefix="vtseam-")  # ONE bounded scratch dir
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    print(
        f"phase={phase} sock={sock_path} scratch={scratch} start={started}", flush=True
    )
    try:
        spawn_pi(sock_path)
        if not wait_for_socket(sock_path):
            cap = capture_pane()
            check(
                "install",
                "socket appears",
                False,
                f"no socket within {SOCK_WAIT_S}s; pane tail: {cap[-600:]!r}",
            )
            return 1
        check(
            "install",
            "socket appears",
            True,
            f"{sock_path} accepts within {SOCK_WAIT_S}s budget",
        )

        time.sleep(
            SETTLE_S
        )  # let pi's startup waves (splash/resume/extension re-asserts) settle
        client = SeamClient(sock_path)
        try:
            run_matrix(client, phase)
        finally:
            client.close()
        return 1 if failures else 0
    finally:
        teardown(sock_path, scratch)
        leftover = subprocess.run(
            ["tmux", "-L", TMUX_SOCK, "ls"], capture_output=True, text=True
        )
        gone = leftover.returncode != 0  # "no server running on …" => clean
        print(
            f"teardown: tmux-server-gone={gone} scratch-removed={not os.path.exists(scratch)}",
            flush=True,
        )


if __name__ == "__main__":
    # SIGALRM backstop: even if a wait misbehaves, the process cannot outlive 200s.
    signal.alarm(200)
    try:
        sys.exit(main())
    except SystemExit as e:
        sys.exit(int(e.code or 0))
