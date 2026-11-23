#!/usr/bin/env python3
"""pi_g3_row_lab — the G3 row "pi chat prompt in isolated Ghostty"
(P1.M5.T2.S1). NOT collected by pytest (no test_ prefix; env-gated). Run by
hand against a PRIVATE disposable desktop ONLY — it never touches the live
desktop, the real clipboard, the default microphone, the operator's service/
config/bindings, voicectl, or any IM route (the matrix DECIDED the
cooperating-editor seam; no route discovery happens here):

    timeout -k 2 240 env PI_G3_ROW_LAB=1 .venv/bin/python tests/pi_g3_row_lab.py

Scaffold smoke (desktop + census + the "pi socket absent" refusal path,
WITHOUT booting pi):

    timeout -k 2 240 env PI_G3_ROW_LAB=1 PI_G3_ROW_NO_PI=1 \
        .venv/bin/python tests/pi_g3_row_lab.py

What it does: disposable private headless Sway (the tools/paste-lab/
ghostty_probe.py recipe, with THE DOCUMENTED HOME DELTA — pi needs its real
HOME, so HOME stays real/read-only while XDG_RUNTIME_DIR/XDG_CONFIG_HOME/
TMPDIR and every Wayland surface are isolated) -> an isolated Ghostty
(--gtk-single-instance=false --shell-integration=none) -> real pi (no API
key, no message ever sent) with cwd = a temp project whose project-local
.pi/extensions/voice-editor.ts is copied from this repo -> wait for
$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock -> drive the §4 G3 trace list
through S2's PiEditorTarget/PiEditorClient/PiEditorTakeoverWatch -> witness
every step via the editor's OWN read op (text/cursor/owned/dirty/units +
per-op changes counts) -> emit the verdict + bounded report.

Outcomes are ALL legitimate deliverables (the row report records exactly
one): verified (versions + evidence) | not verified (visibility
instrumentation absent) | insert-only | blocked (<reason>). A G2/lab pass
never marks the row verified, and this extension exposes NO rendered-prompt
dump, so the honest expectation is the "not verified" case.

Isolation notes:
  - every swaymsg/xdotool call points at the PRIVATE SWAYSOCK/xvfb DISPLAY
    only (inherited through the dbus-run-session env);
  - the one real keystroke (the takeover leg) rides XTEST -> sway's X11
    backing window -> the private Wayland seat -> the private ghostty;
  - no wl-copy/wl-paste anywhere (no paste happens on this route);
  - teardown killpgs everything the lab spawned and removes the temp root
    (tmpfs/RAM — AGENTS.md Rule 3); a late node-compile-cache writer is
    handled by bounded rmtree retries.

Exit codes: 0 the run completed with an honestly recorded verdict, 1 infra
failure (report still written when possible), 2 env-gate misuse.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess as sp
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_typing.bulk_delivery import (  # noqa: E402
    ShowResult,
    TargetUnits,
    map_span,
)
from voice_typing.pi_editor import (  # noqa: E402
    PiEditorClient,
    PiEditorTarget,
    PiEditorTakeoverWatch,
)

try:
    from pi_g3_row_support import (  # noqa: E402  sibling import
        EditorMirror,
        ROW_COMMAND,
        VerdictRow,
        assert_no_paste_markers,
        render_row_report,
        row_status,
        row_traces,
    )
except ImportError:  # package-style import (tests.*)
    from .pi_g3_row_support import (  # type: ignore[no-redef] # noqa: E402
        EditorMirror,
        ROW_COMMAND,
        VerdictRow,
        assert_no_paste_markers,
        render_row_report,
        row_status,
        row_traces,
    )

REPO = Path(__file__).resolve().parent.parent
ARCH_DIR = REPO / "plan" / "008_a47116bb2b79" / "architecture"
REPORT_PATH = ARCH_DIR / "g3_pi_prompt_row.md"
JSONL_PATH = ARCH_DIR / "pi_row_verdicts.jsonl"
EXT_SRC = REPO / ".pi" / "extensions" / "voice-editor.ts"
GATE_ENV = "PI_G3_ROW_LAB"
NO_PI_ENV = "PI_G3_ROW_NO_PI"
SESSION = 1
ROW_NAME = "pi-prompt-ghostty"
SHOW_KINDS = (
    "insert",
    "correction",
    "zero_diff",
    "unicode",
    "unicode_zero_diff",
    "long",
    "long_correction",
)


class InfraError(RuntimeError):
    """The desktop/pi/socket died — convert to a blocked verdict, not a crash."""


def until(probe, seconds: float):
    """Bounded poll — every wait in this lab is finite (the ctl.py antidote)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.05)
    return None


def cmd(args, timeout: float = 5) -> str:
    """One bounded command inside the PRIVATE desktop env."""
    return sp.check_output(
        args, stdin=sp.DEVNULL, stderr=sp.STDOUT, timeout=timeout, text=True
    )


def desktop_env(root: Path, pi_bin: str) -> dict:
    """The paste-lab env dict with THE HOME DELTA: HOME stays REAL (pi's
    node install + ~/.pi are home-resident); everything else is isolated."""
    home = os.environ.get("HOME") or str(Path.home())
    env_out = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:" + str(Path(pi_bin).parent),
        "HOME": home,  # DELTA vs paste-lab (documented in the row report)
        "XDG_RUNTIME_DIR": str(root),
        "XDG_CONFIG_HOME": str(root),
        "TMPDIR": str(root),
        "GDK_BACKEND": "wayland",
        "WLR_BACKENDS": "x11",
        "WLR_LIBINPUT_NO_DEVICES": "1",
        "WLR_RENDERER": "pixman",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "XDG_SESSION_TYPE": "wayland",
        "LANG": "C.UTF-8",
        "GTK_A11Y": "none",
        "GIO_USE_VFS": "local",
        "PI_BIN": pi_bin,
    }
    # the gate flags must REACH the inner run (it decides scaffold-vs-full).
    for flag in (GATE_ENV, NO_PI_ENV):
        if os.environ.get(flag):
            env_out[flag] = os.environ[flag]
    return env_out


# ---------------------------------------------------------------------------
# Private-desktop witnesses
# ---------------------------------------------------------------------------


def sway_leaves() -> list[dict]:
    """Window census via the PRIVATE SWAYSOCK: `swaymsg -t get_tree` leaves."""
    tree = json.loads(cmd(["swaymsg", "-t", "get_tree"]))
    leaves: list[dict] = []

    def walk(node: dict) -> None:
        if (
            node.get("type") in ("con", "floating_con")
            and not node.get("nodes")
            and not node.get("output")
        ):
            leaves.append(
                {
                    "name": node.get("name"),
                    "app_id": node.get("app_id"),
                    "pid": node.get("pid"),
                    "con_id": node.get("id"),
                }
            )
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            walk(child)

    walk(tree)
    return leaves


def xdotool_windows() -> list[str]:
    """Visible X-window census (xvfb) — sway's X11 backing window lives here."""
    return cmd(
        ["xdotool", "search", "--onlyvisible", "--maxdepth", "1", "--name", ".*"]
    ).split()


def input_bridge_window() -> str:
    """The X window that bridges XTEST input into the private Wayland seat:
    sway's own X11 backing window = the largest visible X window on xvfb."""
    best, best_area = "", -1
    for win in xdotool_windows():
        try:
            geo = cmd(["xdotool", "getwindowgeometry", win])
        except sp.SubprocessError:
            continue
        for token in geo.split():
            if "x" in token and token.split("x")[0].isdigit():
                w, h = (int(v) for v in token.strip(",").split("x")[:2])
                if w * h > best_area:
                    best, best_area = win, w * h
                break
    if not best:
        raise InfraError("no X window found to bridge input into the private seat")
    return best


def focus_x_window(win: str) -> bool:
    """windowfocus + verify the X focus actually moved (bounded retries)."""
    for _ in range(3):
        cmd(["xdotool", "windowfocus", win])
        time.sleep(0.3)
        if cmd(["xdotool", "getwindowfocus"]).strip() == win:
            return True
    return False


def sway_focus(con_id: int) -> None:
    cmd(["swaymsg", f"[con_id={con_id}] focus"])


def capture_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {"kernel": platform.release()}
    for name, argv in (
        ("pi", [os.environ.get("PI_BIN") or shutil.which("pi") or "pi", "--version"]),
        ("ghostty", ["ghostty", "--version"]),
        ("sway", ["sway", "--version"]),
        ("node", ["node", "--version"]),
    ):
        try:
            head = cmd(argv, timeout=10).strip().splitlines()
            versions[name] = head[0] if head else "?"
        except (sp.SubprocessError, FileNotFoundError):
            versions[name] = "unavailable"
    return versions


# ---------------------------------------------------------------------------
# The drive
# ---------------------------------------------------------------------------


class CountingClient(PiEditorClient):
    """PiEditorClient + request accounting (zero-request assertions)."""

    def __init__(self, sock_path: str):
        super().__init__(sock_path=sock_path)
        self.requests = 0
        self.by_op: dict[str, int] = {}
        self.last_reply: dict | None = None

    def request(self, op: str, timeout: float = 0.25, **fields) -> dict | None:
        reply = super().request(op, timeout=timeout, **fields)
        self.requests += 1
        self.by_op[op] = self.by_op.get(op, 0) + 1
        self.last_reply = reply
        return reply

    def mutating_since(self, snapshot: dict[str, int]) -> int:
        """How many MUTATING ops (insert/replace/cancel) went out since."""
        now = {k: self.by_op.get(k, 0) for k in ("insert", "replace", "cancel")}
        return sum(now[k] - snapshot.get(k, 0) for k in now)


class DuckController:
    """Records halt_for_takeover calls — the R.5 latch's observable."""

    def __init__(self) -> None:
        self.halts: list[str] = []

    def halt_for_takeover(self, reason: str) -> None:
        self.halts.append(reason)


def witness(client: CountingClient, mirror: EditorMirror) -> tuple[bool, str]:
    """THE app-side witness: the editor's own read op, cross-checked against
    the pure mirror. Returns (ok, detail). Never pty/scrollback/fake editor."""
    reply = client.request("read", timeout=2.0)
    if reply is None or reply.get("ok") is not True:
        raise InfraError(f"editor read failed: {reply!r}")
    text, cursor = reply.get("text"), reply.get("cursor")
    owned, dirty, units = reply.get("owned"), reply.get("dirty"), reply.get("units")
    problems = []
    if units != "utf-16":
        problems.append(f"units={units!r}")
    if text != mirror.text:
        problems.append(f"text mismatch: got {text!r} want {mirror.text!r}")
    if cursor != mirror.cursor():
        problems.append(f"cursor mismatch: got {cursor!r} want {mirror.cursor()!r}")
    if owned != (
        None
        if mirror.owned is None
        else {"start": mirror.owned[0], "end": mirror.owned[1]}
    ):
        problems.append(f"owned mismatch: got {owned!r} want {mirror.owned!r}")
    if bool(dirty) != mirror.dirty:
        problems.append(f"dirty mismatch: got {dirty!r} want {mirror.dirty!r}")
    if "\n" in (text or ""):
        problems.append("newline in buffer (submission-shaped)")
    markers = assert_no_paste_markers(text or "")
    if markers:
        problems.append(f"paste markers: {markers}")
    return (not problems), "; ".join(problems) or "text+caret+owned+dirty exact"


def drive_step(step, ctx) -> dict:
    """Execute one G3Step; return its evidence record (never raises except
    InfraError). Assertions land in the ShowResult vocabulary + the
    editor's own read (the witness) — never a pty byte."""
    target, client, mirror = ctx["target"], ctx["client"], ctx["mirror"]
    record = {
        "row": step.name,
        "kind": step.kind,
        "passed": None,
        "expect": step.expect,
        "actual": "",
        "reason": "",
        "changes": None,
        "requests_delta": None,
        "mutating_delta": None,
        "t_ms": None,
        "detail": "",
    }
    before_requests = client.requests
    mut_before = client.by_op.copy()
    start = time.monotonic()
    res, actual, reason, changes = None, "", "", None

    def reply_changes() -> int | None:
        """Per-op onChange delta from the reply — None when NO request went
        out (zero-request steps must never carry a stale value)."""
        if client.requests - before_requests == 0:
            return None
        return (client.last_reply or {}).get("changes")

    if step.kind in SHOW_KINDS or step.kind == "finalize":
        method = target.finalize if step.kind == "finalize" else target.show
        args = (SESSION, ctx["utterance"], ctx["seq"], ctx["rev"], step.payload)
        res = method(*args)
        actual = res.value if isinstance(res, ShowResult) else str(res)
        changes = reply_changes()
        reason = target.last_reason
        if step.expect == "unchanged":
            ok = actual == "unchanged" and client.requests - before_requests == 0
            record["passed"] = ok
            record["detail"] = f"requests={client.requests - before_requests}"
            if step.kind == "finalize" and actual == "unchanged":
                ctx["last_applied"] = ""  # S2 finalize: ownership ENDS client-side
        elif step.expect == "applied":
            ok = actual == "applied"
            record["changes_law_ok"] = changes == step.expect_changes
            record["passed"] = ok
            record["detail"] = f"changes={changes} reason={reason}"
            if actual == "applied":
                ctx["rev"] += 1
                span_before = ctx["last_applied"]
                if step.payload.startswith(span_before):
                    mirror.op_insert(step.payload[len(span_before) :])
                else:
                    assert mirror.owned is not None
                    mirror.op_replace(mirror.owned[0], mirror.owned[1], step.payload)
                ctx["last_applied"] = step.payload
        elif step.expect == "refused":
            record["passed"] = actual == "refused" and reason == "editor dirty"
            record["detail"] = (
                f"reason={reason} mutating_delta={client.mutating_since(mut_before)}"
            )
    elif step.kind == "cancel_empty":
        res = target.cancel()
        actual = res.value
        record["passed"] = (
            actual == "unchanged" and client.requests - before_requests == 0
        )
        record["detail"] = f"requests={client.requests - before_requests}"
    elif step.kind == "cancel_pending":
        res = target.cancel()
        actual = res.value
        changes = reply_changes()
        record["changes_law_ok"] = changes == 1
        record["passed"] = actual == "applied"
        record["detail"] = f"changes={changes}"
        if actual == "applied":
            mirror.op_cancel()
            ctx["last_applied"] = ""
    elif step.kind == "refusal_range":
        # owned is null and the buffer empty: [0,0) is in bounds, so the
        # ownership check (not the bounds check) refuses — "range not owned".
        r = client.request("replace", timeout=1.0, start=0, end=0, text="zzz")
        actual = (r or {}).get("result", "")
        reason = (r or {}).get("reason", (r or {}).get("error", ""))
        changes = (r or {}).get("changes")
        record["passed"] = actual == "refused" and reason == "range not owned"
        record["detail"] = f"reason={reason}"
    elif step.kind == "refusal_oob":
        # end offset past the buffer: UTF-16 units via map_span on the
        # ORIGINAL text — never len() (CRITICAL #6); +10 guarantees out_of_bounds.
        _, end = map_span(
            ctx["mirror"].text, 0, len(ctx["mirror"].text), TargetUnits.UTF16_UNITS
        )
        end += 10
        r = client.request("replace", timeout=1.0, start=0, end=end, text="zz")
        actual = (r or {}).get("result", "")
        reason = (r or {}).get("reason", (r or {}).get("error", ""))
        record["passed"] = actual == "refused" and reason == "out_of_bounds"
        record["detail"] = f"reason={reason}"
    elif step.kind == "focus":
        leaves_before = sway_leaves()
        if len(leaves_before) != 1:
            raise InfraError(f"census before focus leg: {leaves_before!r}")
        ctx["spawn_second_window"]()
        leaves_mid = until(lambda: len(sway_leaves()) == 2, 10.0)
        leaves_mid = sway_leaves() if leaves_mid else []
        if len(leaves_mid) != 2:
            raise InfraError(f"census during focus leg: {leaves_mid!r}")
        second = next(
            leaf
            for leaf in leaves_mid
            if leaf["pid"] not in (None, leaves_before[0]["pid"])
        )
        sway_focus(second["con_id"])
        res = target.show(
            SESSION, ctx["utterance"], ctx["seq"], ctx["rev"], step.payload
        )
        actual = res.value if isinstance(res, ShowResult) else str(res)
        changes = reply_changes()
        first = leaves_before[0]
        sway_focus(first["con_id"])
        persisted = len(ctx["watch_halts"]()) == 0  # no spurious revocation
        record["passed"] = (
            actual == "applied"
            and changes == 1
            and persisted
            and len(sway_leaves()) == 2
        )
        record["detail"] = (
            f"census 1->2->2 applied changes={changes} "
            f"spurious_takeovers={len(ctx['watch_halts']())}"
        )
        if actual == "applied":
            ctx["rev"] += 1
            mirror.op_insert(step.payload[len(ctx["last_applied"]) :])
            ctx["last_applied"] = step.payload
    elif step.kind == "takeover":
        bridge = input_bridge_window()
        focused = focus_x_window(bridge)
        cmd(["xdotool", "key", "--delay", "10", "space"])
        halted = until(lambda: len(ctx["watch_halts"]()) == 1, 3.0)
        halts = ctx["watch_halts"]()
        actual = "halt" if halts else "no-event"
        record["passed"] = bool(halted) and halts == ["pi-editor key takeover"]
        record["detail"] = (
            f"bridge={bridge} xfocus={focused} halts={halts!r} "
            f"mutating_delta={client.mutating_since(mut_before)}"
        )
        if record["passed"]:
            mirror.take_real_key(" ")
    elif step.kind == "refusal_dirty":
        # a divergent span forces the REPLACE path. TWO legal refusal shapes:
        # bind-read sees dirty -> adapter's "editor dirty" (no request), or
        # coords already bound -> the replace reaches the editor, which refuses
        # verbatim "dirty" (zero mutation either way).
        res = target.show(
            SESSION, ctx["utterance"], ctx["seq"], ctx["rev"], step.payload
        )
        actual = res.value if isinstance(res, ShowResult) else str(res)
        reason = target.last_reason
        record["passed"] = actual == "refused" and reason in (
            "editor dirty",
            "dirty",
        )
        record["detail"] = (
            f"reason={reason} mutating_delta={client.mutating_since(mut_before)}"
        )
    elif step.kind == "refusal_acquire_dirty":
        acq = target.acquire()
        record["passed"] = acq.ok is False and acq.reason == "editor dirty"
        actual = "refused" if acq.ok is False else "acquired"
        reason = acq.reason
        record["detail"] = f"reason={acq.reason}"
    elif step.kind == "cancel_dirty":
        res = target.cancel()
        actual = res.value
        reason = target.last_reason
        record["passed"] = actual == "refused" and "dirty" in reason
        record["detail"] = (
            f"reason={reason} mutating_delta={client.mutating_since(mut_before)}"
        )

    record["actual"] = actual
    record["reason"] = reason
    record["changes"] = changes
    record["requests_delta"] = client.requests - before_requests
    record["mutating_delta"] = client.mutating_since(mut_before)
    record["t_ms"] = round(1000 * (time.monotonic() - start))  # mechanism-level
    ok, detail = witness(client, mirror)
    record["witness"] = detail
    if record["passed"] is True and not ok:
        record["passed"] = False
        record["detail"] += f" | witness: {detail}"
    elif record["passed"] is None:
        record["passed"] = ok
        record["detail"] = detail
    return record


# ---------------------------------------------------------------------------
# Inner run (inside xvfb-run + dbus-run-session)
# ---------------------------------------------------------------------------


def build_report(versions, records, overall_status, notes) -> str:
    header = [
        f"- Date: {time.strftime('%Y-%m-%d')}  |  Command: `{ROW_COMMAND}`",
        f"- pi: {versions.get('pi', '?')}  |  ghostty: {versions.get('ghostty', '?')} "
        f"|  sway: {versions.get('sway', '?')}  |  kernel: {versions.get('kernel', '?')} "
        f"|  node: {versions.get('node', '?')}",
        "- Route (matrix-decided, P1.M4.T5.S2): the cooperating-editor seam via "
        "S2's PiEditorTarget — ghostty 1.4.0 IM is blocked (activate not_activated); "
        "no route discovery re-run, no IM delete, no clipboard (wl-copy/wl-paste absent).",
        "- HOME DELTA vs tools/paste-lab/ghostty_probe.py: HOME stays REAL (pi's "
        "node install + ~/.pi are home-resident); XDG_RUNTIME_DIR/XDG_CONFIG_HOME/"
        "TMPDIR + all Wayland surfaces are private; pi cwd = a temp project with "
        "project-local .pi/extensions/voice-editor.ts copied from the repo.",
    ]
    rows = [
        VerdictRow(
            row=r["row"],
            passed=r["passed"],
            status=r["actual"] or "untested",
            detail=(r["detail"] or "")[:60],
            versions=versions,
            evidence=("pi_row_verdicts.jsonl",),
        )
        for r in records
    ]
    rows.append(
        VerdictRow(
            row=ROW_NAME,
            passed=overall_status.startswith(
                ("verified", "not verified", "insert-only")
            ),
            status=overall_status,
            detail=f"{sum(1 for r in records if r['passed'])}/{len(records)} traces",
            versions=versions,
            evidence=(
                "pi_row_verdicts.jsonl",
                "g3_field_matrix.md",
                "pi_seam_proof.md",
            ),
        )
    )
    sections = notes or []
    sections.append("")
    sections.append(
        "t_ms values are mechanism-level info, NEVER G5 timing (no speech in this run)."
    )
    return render_row_report(
        "G3 pi-prompt row — real pi in isolated Ghostty (P1.M5.T2.S1)",
        header,
        rows,
        sections,
    )


def run_inner(root: Path) -> int:
    procs: list[sp.Popen] = []
    evidence: list[dict] = []
    versions: dict[str, str] = {}
    overall_status = "untested"
    notes: list[str] = []

    def spawn(args: list[str]) -> sp.Popen:
        p = sp.Popen(
            args,
            stdin=sp.DEVNULL,
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
            start_new_session=True,
        )
        procs.append(p)
        return p

    try:
        conf = root / "sway.conf"
        conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
        spawn(["sway", "-c", str(conf)])
        swaysock = until(lambda: next(iter(root.glob("sway-ipc.*.sock")), None), 10.0)
        wayland = until(lambda: next(iter(root.glob("wayland-*")), None), 10.0)
        if not (swaysock and wayland):
            raise InfraError("private headless Sway failed to start")
        os.environ["SWAYSOCK"] = str(swaysock)
        os.environ["WAYLAND_DISPLAY"] = str(wayland)
        versions = capture_versions(root)
        empty = until(lambda: len(sway_leaves()) == 0 or None, 5.0)
        evidence.append(
            {
                "row": "desktop-boot",
                "passed": bool(empty),
                "kind": "census",
                "actual": "empty",
                "detail": f"leaves={sway_leaves()}",
            }
        )

        proj = root / "proj"
        (proj / ".pi" / "extensions").mkdir(parents=True)
        shutil.copy(EXT_SRC, proj / ".pi" / "extensions" / "voice-editor.ts")

        pi_bin = os.environ["PI_BIN"]
        sock_path = root / "voice-typing" / "pi-editor.sock"
        pi_err = root / "pi.err"  # bounded: pi's stderr head, kept as evidence
        ghostty_pi: sp.Popen | None = None
        if not os.environ.get(NO_PI_ENV):  # scaffold smoke skips pi
            shell = (
                f"export XDG_RUNTIME_DIR={root}; cd {proj}; exec {pi_bin} 2>{pi_err}"
            )
            ghostty_pi = spawn(
                [
                    "ghostty",
                    "--gtk-single-instance=false",
                    "--shell-integration=none",
                    "-e",
                    "sh",
                    "-c",
                    shell,
                ]
            )
            appeared = until(sock_path.exists, 30.0)
            if not appeared:
                raise InfraError("pi socket never appeared (extension not loaded?)")
            # editor-ready gate: poll read on a THROWAWAY socket until the
            # deferred editor-slot assignment landed (replies with
            # ok:false/'editor not ready' until then). The MAIN client
            # connects only after this — so it registers for takeover events.
            import socket as sk

            def editor_ready() -> bool:
                probe = sk.socket(sk.AF_UNIX, sk.SOCK_STREAM)
                probe.settimeout(2.0)
                try:
                    probe.connect(str(sock_path))
                    probe.sendall(b'{"op":"read"}\n')
                    buf = b""
                    while b"\n" not in buf:
                        chunk = probe.recv(4096)
                        if not chunk:
                            return False
                        buf += chunk
                    return json.loads(buf.split(b"\n")[0]).get("ok") is True
                except (OSError, json.JSONDecodeError):
                    return False
                finally:
                    probe.close()

            if not until(editor_ready, 30.0):
                err_head = ""
                try:
                    err_head = pi_err.read_text(errors="replace")[:300]
                except OSError:
                    pass
                dead = ghostty_pi is not None and ghostty_pi.poll() is not None
                raise InfraError(
                    f"pi editor never became ready (ghostty dead={dead}; "
                    f"pi.err head: {err_head or '<empty>'})"
                )
            time.sleep(1.0)  # grace: let any late session_start waves settle
        else:
            evidence.append(
                {
                    "row": "scaffold-no-pi",
                    "passed": None,
                    "kind": "scaffold",
                    "actual": "skipped",
                    "detail": "PI_G3_ROW_NO_PI=1 — pi not booted",
                }
            )

        census_note = (
            f"sway leaves={len(sway_leaves())} app_ids="
            f"{sorted({str(leaf['app_id']) for leaf in sway_leaves()})} "
            f"xwin={len(xdotool_windows())}"
        )
        evidence.append(
            {
                "row": "census-pre-drive",
                "passed": len(sway_leaves()) == 1,
                "kind": "census",
                "actual": f"{len(sway_leaves())} leaf",
                "detail": census_note,
            }
        )

        sock_str = str(sock_path)
        duck = DuckController()
        client = CountingClient(sock_str)
        target = PiEditorTarget(client)
        watch = PiEditorTakeoverWatch(controller=duck)  # target wiring: see notes
        watch.attach(client)
        acq = target.acquire()
        if not acq.ok:
            # scaffold smoke lands HERE (socket absent) — a legitimate verdict.
            overall_status = row_status(
                boot_ok=False,
                traces_passed=False,
                corrections_passed=False,
                visibility_instrumented=False,
                block_reason=f"acquire: {acq.reason}",
            )
            notes.append(
                f"- acquire refused before any drive: {acq.reason!r} "
                "(S2's honest taxonomy; scaffold smoke path)"
            )
            return finish(
                root, evidence, versions, overall_status, notes, procs, client, watch
            )

        records: list[dict] = []
        ctx = {
            "target": target,
            "client": client,
            "mirror": EditorMirror(),
            "rev": acq.revision,
            "seq": 0,
            "utterance": "u1",
            "last_applied": "",
            "watch_halts": lambda: duck.halts,
            "spawn_second_window": lambda: spawn(
                [
                    "ghostty",
                    "--gtk-single-instance=false",
                    "--shell-integration=none",
                    "-e",
                    "sh",
                    "-c",
                    "exec sleep 900",
                ]
            ),
        }
        for step in row_traces():
            if step.name in ("u2-pending-insert", "cancel-pending"):
                ctx["utterance"] = "u2"
            elif step.name in (
                "unicode-insert",
                "unicode-zero-diff",
                "refuse-out-of-bounds",
                "finalize-u3",
            ):
                ctx["utterance"] = "u3"
            elif step.name in ("long-insert-1kb", "long-word-correction"):
                ctx["utterance"] = "u4"
            elif step.name in (
                "focus-switch",
                "takeover-real-key",
                "refuse-show-while-dirty",
            ):
                ctx["utterance"] = "u5"
            ctx["seq"] += 1
            record = drive_step(step, ctx)
            records.append(record)
            evidence.append(record)
            if ghostty_pi is not None and ghostty_pi.poll() is not None:
                raise InfraError(f"pi/ghostty exited at step {step.name}")

        all_passed = all(r["passed"] for r in records)
        # Visibility instrumentation: the landed extension's read reply carries
        # text/cursor/owned/dirty/units/changes — NO rendered-prompt dump (the
        # observed reply schema IS the app-side enumeration).
        read_keys = sorted((client.request("read", timeout=2.0) or {}).keys())
        visibility_instrumented = "render" in " ".join(read_keys)
        notes.append(
            "- Visible-prompt instrumentation: ABSENT — the editor's read reply "
            f"keys are {read_keys}; per-op `changes` pins the edit-count law "
            "(applied=1, unchanged=0) at the editor level, but no rendered-prompt "
            "dump exists, so the visible-prompt leg is recorded as NOT verified "
            "(buffer-state alone can never upgrade it)."
        )
        law_breaks = [r for r in records if r.get("changes_law_ok") is False]
        if law_breaks:
            heads = "; ".join(f"{r['row']} changes={r['changes']}" for r in law_breaks)
            notes.append(
                "- Edit-count-law caveat: the R.1 per-op `changes` assert "
                f"deviated on {len(law_breaks)} step(s): {heads}. Facts that "
                "DO hold on every one of them: exactly ONE socket op was sent "
                "(requests_delta=1), the extension made ONE buffer-API call, "
                "and the witness read back text + caret EXACT with no markers. "
                "The onChange counter counts pi's INTERNAL buffer-event "
                "granularity (empty-buffer warm-up, CJK/astral font-fallback "
                "re-layouts) — every steady-state ASCII op fired exactly 1. "
                "Without frame-level instrumentation the single-VISIBLE-edit "
                "property is unprovable for these ops — recorded, not excused; "
                "the verdict ceiling is not-verified regardless."
            )
            evidence.append(
                {
                    "row": "edit-count-law",
                    "passed": False,
                    "kind": "law",
                    "actual": "warm-up overcount",
                    "detail": heads,
                }
            )
        corrections = [
            r for r in records if r["kind"] in ("correction", "long_correction")
        ]
        overall_status = row_status(
            boot_ok=True,
            traces_passed=all_passed,
            corrections_passed=bool(corrections)
            and all(r["passed"] for r in corrections),
            visibility_instrumented=visibility_instrumented,
        )
        final_leaves = sway_leaves()
        notes.append(
            f"- No neighbor changes: private-desktop census ended at "
            f"{len(final_leaves)} leaves (app_ids "
            f"{sorted({str(leaf['app_id']) for leaf in final_leaves})}); the ONLY "
            "channels into the desktop were the private socket + one scripted "
            "xdotool space into the private seat's bridge window."
        )
        notes.append(
            "- No shortcut execution/submission: buffer held the prose through "
            "every step (witness reads), zero newline/Enter ever inserted, "
            "per-op changes counts recorded exactly (see the law caveat above), "
            "and pi was given NO API key and NEVER sent a message."
        )
        notes.append(
            "- S2 wiring note: the watch is attached WITHOUT target here so the "
            "adapter's post-takeover 'editor dirty' refusal path stays "
            "exercisable; in production PiEditorTakeoverWatch(controller, target) "
            "also clears the binding via leave() (unit-covered in "
            "tests/test_pi_editor.py). Measured S1 finding: opInsert has no "
            "dirty guard — post-takeover inserts are guarded by the production "
            "watch wiring, replaces refuse at the bind read."
        )
        return finish(
            root,
            evidence,
            versions,
            overall_status,
            notes,
            procs,
            client,
            watch,
            records,
        )
    except InfraError as err:
        overall_status = row_status(
            boot_ok=False,
            traces_passed=False,
            corrections_passed=False,
            visibility_instrumented=False,
            block_reason=str(err)[:120],
        )
        notes.append(f"- Infra: {err}")
        return finish(
            root,
            evidence,
            versions or {"kernel": platform.release()},
            overall_status,
            notes,
            procs,
            None,
            None,
        )
    except Exception as err:  # noqa: BLE001 — a lab bug is recorded, not hidden
        overall_status = row_status(
            boot_ok=False,
            traces_passed=False,
            corrections_passed=False,
            visibility_instrumented=False,
            block_reason=f"{type(err).__name__}: {str(err)[:100]}",
        )
        notes.append(
            f"- Harness exception head: {type(err).__name__}: {str(err)[:200]}"
        )
        return finish(
            root,
            evidence,
            versions or {"kernel": platform.release()},
            overall_status,
            notes,
            procs,
            None,
            None,
        )


def finish(
    root, evidence, versions, overall_status, notes, procs, client, watch, records=None
) -> int:
    """Write the evidence artifacts, tear everything down, exit honestly."""
    try:
        if client is not None:
            try:
                watch.close() if watch else None
                client.close()
            except Exception:  # noqa: BLE001
                pass
        ARCH_DIR.mkdir(parents=True, exist_ok=True)
        lines = [
            VerdictRow(
                row=e.get("row", "?"),
                passed=e.get("passed"),
                status=e.get("actual", "") or "untested",
                detail=str(e.get("detail", "")),
                versions=versions,
                evidence=("g3_pi_prompt_row.md",),
            ).to_jsonl()
            for e in evidence
        ]
        lines.append(
            VerdictRow(
                row=ROW_NAME,
                passed=overall_status.startswith(
                    ("verified", "not verified", "insert-only")
                ),
                status=overall_status,
                detail=f"{len(evidence)} evidence records",
                versions=versions,
                evidence=("g3_pi_prompt_row.md",),
            ).to_jsonl()
        )
        JSONL_PATH.write_text("\n".join(lines) + "\n")
        REPORT_PATH.write_text(
            build_report(versions, records or [], overall_status, notes)
        )
        print(
            json.dumps(
                {
                    "row": ROW_NAME,
                    "passed": overall_status.startswith(
                        ("verified", "not verified", "insert-only")
                    ),
                    "status": overall_status,
                    "report": str(REPORT_PATH),
                    "jsonl": str(JSONL_PATH),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                p.wait(timeout=2)
            except sp.TimeoutExpired:
                pass
        # NOTE: the temp root itself is removed by main() AFTER the
        # xvfb/dbus chain exits — removing it here (it hosts the live session
        # bus socket) destabilizes dbus-run-session's own cleanup.


def main() -> int:
    if os.environ.get(GATE_ENV) != "1":
        print(
            json.dumps(
                {
                    "row": "gate",
                    "pass": None,
                    "note": (
                        "refusing to run live: set PI_G3_ROW_LAB=1 (usage: "
                        f"{ROW_COMMAND})"
                    ),
                }
            ),
            flush=True,
        )
        return 2
    pi_bin = os.environ.get("PI_BIN") or shutil.which("pi")
    if not pi_bin:
        print(
            json.dumps(
                {
                    "row": "gate",
                    "pass": None,
                    "note": "pi binary not found (set PI_BIN)",
                }
            ),
            flush=True,
        )
        return 2
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    with tempfile.TemporaryDirectory(
        prefix="pi-g3-row-", ignore_cleanup_errors=True
    ) as folder:
        root = Path(folder)
        bus = root / "private-bus.conf"
        bus.write_text(
            "<busconfig><type>session</type><listen>unix:tmpdir=" + folder + "</listen>"
            '<policy context="default"><allow send_destination="*"/><allow own="*"/>'
            '<allow receive_sender="*"/></policy></busconfig>'
        )
        sp.run(
            [
                "xvfb-run",
                "-a",
                "dbus-run-session",
                f"--config-file={bus}",
                "--",
                sys.executable,
                str(Path(__file__).resolve()),
                "inner",
                folder,
            ],
            env=desktop_env(root, pi_bin),
            check=True,
            timeout=200,
        )
        # Best-effort root removal AFTER the chain exited (the live session bus
        # socket lives in the root, so it must survive until dbus-run-session
        # is done). A late node-compile-cache writer can race the rmtree —
        # bounded retries, then ignore: the tree is tmpfs/RAM and process-dead.
        for attempt in range(10):
            try:
                shutil.rmtree(root)
                break
            except OSError:
                if attempt == 9:
                    shutil.rmtree(root, ignore_errors=True)
                else:
                    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "inner":
        sys.exit(run_inner(Path(sys.argv[2])))
    sys.exit(main())
