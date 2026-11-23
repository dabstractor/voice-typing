#!/usr/bin/env python3
"""ime_g3_matrix_lab — the G3 FIELD-CLASS matrix gate (P1.M4.T5.S2). NOT
collected by pytest (no test_ prefix; env-gated). Run by hand against a
PRIVATE disposable desktop ONLY — it never touches the live desktop, the real
clipboard, the default microphone, or the user's service (owns its
ImeProcess; no control-socket/authority calls anywhere; every nested
compositor-IPC call is --sig-scoped to the PRIVATE instance):

    timeout 420 env IME_G3_MATRIX_LAB=1 .venv/bin/python tests/ime_g3_matrix_lab.py

Re-runs the R.2 field-class matrix rows at the INSTALLED versions (foot /
kitty / ghostty drift since the 2026-11-22 im-lab measurement) through the
PRODUCT IM transport (ImeProcess -> ime_host), and makes the first isolated
real-Hyprland relay attempt (research/matrix-rerun-mechanics.md §4: the
nested failure inherited wlroots' WLR_BACKENDS=x11 — aquamarine has NO x11
backend; drm/headless/wayland only). Capability findings are MEASUREMENTS,
not gate failures: exit 1 fires ONLY on infra/assertion violations (a
terminal never ready, an outcome outside the pre-declared legal sets, a
global-invariant breach). Exit codes: 0 all rows measured legally, 1 any
harness failure, 2 gate/env misuse.

Rows (one JSON verdict line each, mirrored to <root>/verdicts.jsonl; t_ms is
mechanism-level info — NEVER G5; insert-only rows NEVER run as full
dictation; terminal verification is APP-SIDE ONLY via term.json — terminals
never send surrounding_text, so rows are driven at the HOST transport level
proc.request("acquire"/"show"), NOT via ImeTarget, whose policy refuses
without a surrounding-text snapshot BY DESIGN (R.3)):
  T1 term-foot       activation / acquire reason / ASCII insert / Unicode
                     insert / correct probe (delete " im" -> "v2") at the
                     installed foot. Branches from LEGAL_TERM_OUTCOMES only.
  T2 term-kitty      same probes at the installed kitty (0.51 dropped X11 —
                     plain wayland spawn, the proven im-lab recipe).
  T3 term-ghostty    same probes at the installed ghostty; insert
                     not-delivered is the EXPECTED 1.4.0 branch (PR #15246 is
                     milestone 1.5.0) — a measurement, not a failure.
  T4 hypr-relay      the isolated Hyprland ladder: nested-wayland (clean env,
                     no x11/wlroots/DISPLAY inheritance) -> aq-headless
                     (AQ_NO_KMS_REQUIREMENT=1, AQ_DRM_DEVICES pinned empty) ->
                     legacy-x11 (2026-11-22 posture verbatim, provenance).
                     On boot: S1's field app (system python3) + a SECOND
                     ImeProcess bound to the HYPR socket, insert/correct/
                     surrounding probes via hyprctl --sig focus. blocked(...)
                     with the error head is a legitimate deliverable.
  T5 live-registry   OPTIONAL (default OFF): passive registry listing of the
                     LIVE Hyprland socket (im-lab README posture: connect,
                     list globals, exit — no binds, no input). Gated behind
                     IME_G3_MATRIX_LIVE_REGISTRY=1; never flips a row status.

The preedit diagnostic of the im-lab era is recorded as NOT exercised: the
product host transport serves acquire/show/cancel/grab/verify/leave/ping
only — it has no preedit command (ime_host.py _dispatch); the honest note is
carried per row instead of a fake branch.

Boot pattern forked from tests/ime_g3_lab.py (itself from
tests/ime_correction_lab.py / tools/im-lab/imlab_run.py — READ-ONLY evidence
records, never edited): xvfb-run -a + dbus-run-session --config-file=
<private bus> + sway x11 backend on a disposable HOME/XDG_RUNTIME_DIR/TMPDIR;
terminals run tests/ime_g3_field_term.py (fork of tools/im-lab/
field_term.py, same {line, seq, t} schema, 2000-write cap); the Hyprland row
spawns S1's tests/ime_g3_field_gtk.py on SYSTEM python3 (venv has no gi).
Scratch stays in ONE TemporaryDirectory (RAM-backed tmpfs); host event logs
are EventLogWriter-capped at 64 KiB; term.json caps at 2000 writes; hypr.err
heads are capped at 400 B; verdicts are one line per row. Teardown killpgs
our own session groups and never pattern-sweeps. Without IME_G3_MATRIX_LAB=1:
prints usage, exits 2.
"""

from __future__ import annotations

import collections
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

from voice_typing.ime.manager import ImeProcess  # noqa: E402

from ime_g3_matrix_support import (  # noqa: E402
    ASCII_INSERT_LINE,
    CORRECT_APPLIED_LINE,
    CORRECT_IGNORED_LINE,
    HYPR_LADDER,
    PREEDIT_NOTE,
    TERM_PAYLOADS,
    attempts_from_verdict,
    first_version_line,
    hypr_row_status,
    outcome_from_verdict,
    pacman_versions,
    term_row_status,
)

REPO = Path(__file__).resolve().parents[1]
GATE_ENV = "IME_G3_MATRIX_LAB"
LIVE_REG_ENV = "IME_G3_MATRIX_LIVE_REGISTRY"
PREFIX = "ime-g3-matrix-"
FIELD_APP = REPO / "tests" / "ime_g3_field_gtk.py"
FIELD_TERM = REPO / "tests" / "ime_g3_field_term.py"
FIELD_APP_ID = "org.imlab.g3field"
SYSTEM_PY = shutil.which("python3") or "python3"

# The im-lab spawn recipes verbatim (imlab_run.py run():387-390) — proven at
# the measured set; kitty 0.51 dropped X11 (irrelevant on the wayland seat).
TERM_SPAWNS = (
    ("foot", ["foot", "-T", "imlab-foot"], "foot"),
    ("kitty", ["kitty", "--class", "imlab-kitty"], "imlab-kitty"),
    (
        "ghostty",
        ["ghostty", "--gtk-single-instance=false", "--shell-integration=none", "-e"],
        "com.mitchellh.ghostty",
    ),
)


def until(probe, seconds: float):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        v = probe()
        if v is not None and v is not False and v != "":
            return v
        time.sleep(0.02)
    return None


class _EventCollector:
    """on_event callback: bounded deque (never unbounded). The DURABLE event
    record is each host's capped EventLogWriter file; this is row convenience."""

    def __init__(self, cap: int = 4096):
        self.items: collections.deque = collections.deque(maxlen=cap)

    def __call__(self, ev: dict) -> None:
        self.items.append(ev)

    def count(self, name: str) -> int:
        return sum(1 for e in self.items if e.get("ev") == name)


class Lab:
    def __init__(self, root: Path):
        self.root = root
        self.env = os.environ.copy()
        self.procs: list[sp.Popen] = []
        self.verdicts: list[dict] = []
        self.events = _EventCollector()

    def spawn(
        self, args, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr_name=None, env=None
    ):
        err = (self.root / stderr_name).open("wb") if stderr_name else sp.DEVNULL  # noqa: SIM115
        p = sp.Popen(
            args,
            stdin=stdin,
            stdout=stdout,
            stderr=err,
            env=env or self.env,
            start_new_session=True,
        )
        self.procs.append(p)
        return p

    def kill(self, p: sp.Popen) -> None:
        if p in self.procs:
            self.procs.remove(p)
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        try:
            p.wait(timeout=2)
        except sp.TimeoutExpired:
            pass

    def cmd(self, args, timeout=5, env=None):
        return sp.run(
            args,
            stdin=sp.DEVNULL,
            stdout=sp.PIPE,
            stderr=sp.DEVNULL,
            env=env or self.env,
            timeout=timeout,
        ).stdout

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

    def verdict(self, row: str, ok, sub: str = "", checks=(), t_ms=None, **kw):
        v = {"row": row, "sub": sub, "pass": ok, "checks": list(checks), "t_ms": t_ms}
        v.update(kw)
        self.verdicts.append(v)
        print(json.dumps(v, ensure_ascii=False), flush=True)
        try:
            with (self.root / "verdicts.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(v, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def shot(self, name: str) -> str | None:
        """Optional per-row screenshot: sha256[:16] ONLY — the image is deleted
        immediately (bounded scratch; evidence stays capped)."""
        if not shutil.which("grim"):
            return None
        png = self.root / f"{name}.png"
        try:
            sp.run(
                ["grim", str(png)],
                env=self.env,
                timeout=5,
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL,
                check=False,
            )
            if not png.exists():
                return None
            import hashlib

            return hashlib.sha256(png.read_bytes()).hexdigest()[:16]
        except (sp.TimeoutExpired, OSError):
            return None
        finally:
            try:
                png.unlink()
            except OSError:
                pass

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


# --- boot (forked from tests/ime_g3_lab.py) -------------------------------------


def start_desktop(lab: Lab) -> str:
    conf = lab.root / "sway.conf"
    conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
    sway = lab.spawn(["sway", "-c", str(conf)])
    if (
        not until(lambda: next(lab.root.glob("sway-ipc.*.sock"), None), 7)
        or sway.poll() is not None
    ):
        raise RuntimeError("private Sway failed to start")
    lab.env["SWAYSOCK"] = str(next(lab.root.glob("sway-ipc.*.sock")))
    sock = until(
        lambda: next(
            (p.name for p in lab.root.glob("wayland-*") if p.is_socket()), None
        ),
        7,
    )
    if not sock:
        raise RuntimeError("private Sway never opened a wayland socket")
    lab.env["WAYLAND_DISPLAY"] = sock
    lab.env["PYTHONPATH"] = str(REPO)
    return sock


def start_adapter(lab: Lab, log_name="ime_host.jsonl", on_event=None, seat_env=None):
    """Spawn the REAL adapter: ImeProcess (venv python; cwd=repo root inherited;
    PYTHONPATH=REPO set by start_desktop). seat_env (the Hyprland row) swaps
    os.environ for the spawn because ImeProcess children inherit it — restored
    before returning. Readiness = spawn ping + 'globals' in the host log."""
    saved = None
    if seat_env is not None:
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(seat_env)
    try:
        host_log = lab.root / log_name
        proc = ImeProcess(log_path=str(host_log), on_event=on_event or lab.events)
        if not proc.spawn(timeout=15):
            raise RuntimeError(
                f"ImeProcess spawn failed (state={proc.state}): "
                f"events={list((on_event or lab.events).items)[-3:]}"
            )
        if not until(
            lambda: host_log.exists()
            and "globals" in host_log.read_text(errors="replace"),
            7,
        ):
            raise RuntimeError(
                f"{log_name}: ime_host never became the seat's input method"
            )
        return proc
    finally:
        if saved is not None:
            os.environ.clear()
            os.environ.update(saved)


def wait_host_event(collector, proc, base_count, name, seconds):
    """Wait for one host event since base_count, pumping pings around the
    passive wait (never block on a passive event read — adapter-api §3)."""
    deadline = time.monotonic() + seconds
    last_pump = 0.0
    while time.monotonic() < deadline:
        if collector.count(name) > base_count:
            return True
        now = time.monotonic()
        if now - last_pump >= 0.25:
            last_pump = now
            try:
                proc.request("ping", timeout=1)
            except Exception:  # noqa: BLE001 — a lost ping never fails a row
                pass
        time.sleep(0.02)
    return False


def sig_scoped_ipc(lab: Lab, sig: str, *args: str) -> None:
    """The ONLY compositor-IPC seam: a bare hyprctl call without --sig reaches
    the operator's live instance (isolation breach) — the audit gate enforces
    the pairing on every occurrence."""
    lab.cmd(["hyprctl", "--sig", sig, *args])


# --- app-side witnesses ------------------------------------------------------------


def term_dump(root: Path) -> dict | None:
    try:
        return json.loads((root / "term.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def field_dump(root: Path) -> dict | None:
    try:
        return json.loads((root / "field.ready").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def wait_term_line(root: Path, probe, seconds: float) -> dict | None:
    return until(lambda: probe(term_dump(root)), seconds)


_SHOW_SEQ = {"n": 0}


def host_show(
    proc: ImeProcess, text: str, before: int = 0, timeout: float = 3
) -> dict | None:
    """ONE host-level show request in the FULL wire envelope the protocol
    validates (protocol.validate_request SHOW_FIELDS: session, utterance, seq,
    expected_revision, text — the host handler consumes only text/before but
    the envelope is REQUIRED; a bare request draws a protocol-error reply).
    seq increments per show; the error key (a protocol/transport rejection) is
    a HARNESS BUG — callers turn it into an out-of-legal row failure, never
    into a capability branch."""
    _SHOW_SEQ["n"] += 1
    r = proc.request(
        "show",
        timeout=timeout,
        session="ime-g3-matrix",
        utterance=1,
        seq=_SHOW_SEQ["n"],
        expected_revision=0,
        text=text,
        before=before,
    )
    if r is not None and "error" in r:
        return {"harness_error": r["error"]}
    return r


# --- T1–T3: terminal rows at the HOST transport level -------------------------------


def _fail_row(lab, row, version, branches, t_ms, reasons, msg):
    lab.verdict(
        row,
        False,
        terminal=row.removeprefix("term-"),
        version=version,
        branches=branches,
        t_ms=t_ms,
        reasons=reasons,
        checks=(msg,),
        evidence=[lab.err_head("term-" + row.removeprefix("term-") + ".err")],
    )


def run_term_row(
    lab: Lab, proc: ImeProcess, name: str, spawn_args: list, app_id: str, version: str
) -> None:
    row = f"term-{name}"
    err_name = f"term-{name}.err"
    for f in ("term.json", "term.final", "term.ready"):
        (lab.root / f).unlink(missing_ok=True)
    tproc = None
    branches: dict = {}
    t_ms: dict = {}
    reasons: dict = {}
    try:
        tproc = lab.spawn(
            spawn_args + [sys.executable, str(FIELD_TERM), str(lab.root)],
            stderr_name=err_name,
        )
        if (
            not until(lambda: (lab.root / "term.ready").exists(), 8)
            or tproc.poll() is not None
        ):
            lab.verdict(
                row,
                None,
                terminal=name,
                version=version,
                branches=branches,
                checks=("terminal field never became ready",),
                evidence=[lab.err_head(err_name)],
            )
            return
        lab.focus(f'[app_id="{app_id}"]')
        base = lab.events.count("activate")
        activated = wait_host_event(lab.events, proc, base, "activate", 4)
        branches["activate"] = "activated" if activated else "not_activated"

        # acquire: the surrounding-text channel evidence — terminals never send
        # a snapshot, so the reply's reason string IS the row's evidence (R.7).
        acq = proc.request("acquire", timeout=3)
        reasons["acquire"] = (acq or {}).get("reason", "no reply")
        branches["surround"] = "sent" if (acq or {}).get("ok") else "never_sent"

        # ASCII insert probe — BOTH branches legal; an unchanged "" buffer is
        # the not_delivered branch, ANY other line is a harness bug (the probe
        # invariant: byte-exactly one of the pre-declared legal outcome strings).
        r = host_show(proc, ASCII_INSERT_LINE)
        if r is not None and "harness_error" in r:
            _fail_row(
                lab,
                row,
                version,
                branches,
                t_ms,
                reasons,
                f"show request rejected by the transport: {r['harness_error']!r}",
            )
            return
        t_ms["insert"] = (r or {}).get("t_ms")
        got = wait_term_line(
            lab.root, lambda d: d is not None and d.get("line") == ASCII_INSERT_LINE, 4
        )
        cur = (term_dump(lab.root) or {}).get("line", "")
        if got is not None:
            branches["insert"] = "delivered"
        elif cur == "":
            branches["insert"] = "not_delivered"
        else:
            _fail_row(
                lab,
                row,
                version,
                branches,
                t_ms,
                reasons,
                f"insert probe produced an out-of-legal buffer {cur!r}",
            )
            return

        if branches["insert"] == "delivered":
            # Correct probe — ONLY if the insert delivered (skip-deps pinned
            # by TermProbeOutcome): delete " im" (3 UTF-8 BYTES) + commit
            # "v2", run BEFORE the unicode probe so the baseline is
            # byte-pinned to "hello from im" and the legal strings are exact
            # (delete_applied eats an ASCII tail; a multi-byte tail would
            # mojibake under the 3-byte delete and pin no legal string).
            r = host_show(
                proc,
                TERM_PAYLOADS["correct_replacement"],
                before=len(TERM_PAYLOADS["correct_delete"].encode("utf-8")),
            )
            if r is not None and "harness_error" in r:
                _fail_row(
                    lab,
                    row,
                    version,
                    branches,
                    t_ms,
                    reasons,
                    f"show request rejected by the transport: {r['harness_error']!r}",
                )
                return
            t_ms["correct"] = (r or {}).get("t_ms")
            reasons["show_correct"] = (r or {}).get("result", "no reply")
            got_c = wait_term_line(
                lab.root,
                lambda d: d is not None
                and d.get("line") in (CORRECT_APPLIED_LINE, CORRECT_IGNORED_LINE),
                4,
            )
            cur = (term_dump(lab.root) or {}).get("line", "")
            if got_c is None:
                _fail_row(
                    lab,
                    row,
                    version,
                    branches,
                    t_ms,
                    reasons,
                    f"correct probe produced an out-of-legal buffer {cur!r}",
                )
                return
            branches["correct"] = (
                "delete_applied" if cur == CORRECT_APPLIED_LINE else "delete_ignored"
            )
            # Unicode insert probe — LAST, baseline-relative (skip-deps: only
            # after a delivered insert): delivered <=> line == baseline +
            # payload; unchanged <=> line == baseline; ANY other line is a
            # harness bug, not a capability branch.
            baseline = cur
            r = host_show(proc, TERM_PAYLOADS["insert_unicode"])
            if r is not None and "harness_error" in r:
                _fail_row(
                    lab,
                    row,
                    version,
                    branches,
                    t_ms,
                    reasons,
                    f"show request rejected by the transport: {r['harness_error']!r}",
                )
                return
            t_ms["insert_unicode"] = (r or {}).get("t_ms")
            got_u = wait_term_line(
                lab.root,
                lambda d: d is not None
                and d.get("line")
                in (baseline + TERM_PAYLOADS["insert_unicode"], baseline),
                4,
            )
            cur = (term_dump(lab.root) or {}).get("line", "")
            if got_u is not None and cur == baseline + TERM_PAYLOADS["insert_unicode"]:
                branches["unicode"] = True
            elif cur == baseline:
                branches["unicode"] = False
            else:
                _fail_row(
                    lab,
                    row,
                    version,
                    branches,
                    t_ms,
                    reasons,
                    f"unicode probe produced an out-of-legal buffer {cur!r}",
                )
                return

        # Preedit diagnostic: NOT exercised — the product host transport has no
        # preedit command (ime_host _dispatch). Honest note, zero bytes sent,
        # so the app-side seq is trivially unchanged.
        evidence = [
            f"line after probes: {cur!r}",
            f"preedit: {PREEDIT_NOTE}",
        ]
        shot8 = lab.shot(f"shot-{name}")
        if shot8:
            evidence.append(f"screenshot sha256[:16]: {shot8}")
        o = outcome_from_verdict(
            {
                "terminal": name,
                "version": version,
                "branches": branches,
                "t_ms": t_ms,
                "reasons": reasons,
                "evidence": evidence,
            }
        )
        lab.verdict(
            row,
            True,
            terminal=name,
            version=version,
            branches=branches,
            t_ms=t_ms,
            reasons=reasons,
            evidence=evidence,
            status=term_row_status(o),
        )
    except Exception as e:  # noqa: BLE001 — one bad block must not kill the run
        lab.verdict(
            row,
            None,
            terminal=name,
            version=version,
            branches=branches,
            t_ms=t_ms,
            reasons=reasons,
            checks=(f"row exception: {e!r}",),
        )
    finally:
        if tproc is not None:
            lab.kill(tproc)


# --- T4: the isolated Hyprland ladder ------------------------------------------------


def build_hypr_env(base: dict, spec: dict, sway_sock: str) -> dict:
    """A FRESH env dict per the ladder spec — the inherited sway values
    (WLR_BACKENDS=x11, DISPLAY from xvfb-run, …) are explicitly dropped per
    variant (research §4: that inheritance is the recorded failure's suspect;
    aquamarine reads NONE of the WLR_* vars — drm/headless/wayland only)."""
    env = dict(base)
    for key in spec["unset"]:
        env.pop(key, None)
    for key, val in spec["set"].items():
        env[key] = sway_sock if val == "@SWAY_SOCK@" else val
    return env


def hypr_field_rows(lab: Lab, hypr_seat: dict, sig: str):
    """Field rows against the booted private instance. Returns
    (rows_measured | None, pass_flag, evidence). pass False ONLY on
    out-of-legal/assertion violations; 'field never ready' is a recorded
    measurement (rows None), not a failure."""
    evidence: list[str] = []
    hypr_events = _EventCollector()
    hypr_proc: ImeProcess | None = None
    field_proc = None
    try:
        # Passive registry advertisement of the PRIVATE instance (read-only).
        try:
            g = sp.run(
                [sys.executable, str(REPO / "tools" / "im-lab" / "globals.py"), "json"],
                env=hypr_seat,
                capture_output=True,
                timeout=10,
            )
            adv = json.loads(g.stdout.decode() or "{}").get("text_injection", {})
            evidence.append(
                f"private registry advertisement: {json.dumps(adv, sort_keys=True)}"
            )
        except (sp.TimeoutExpired, OSError, json.JSONDecodeError, ValueError) as e:
            evidence.append(f"registry listing unavailable: {e!r}")

        # S1's GTK field oracle on SYSTEM python3 against the HYPR socket.
        field_proc = lab.spawn(
            [SYSTEM_PY, str(FIELD_APP), str(lab.root)],
            stderr_name="gtk-hypr.err",
            env=hypr_seat,
        )
        if (
            not until(lambda: (lab.root / "field.ready").exists(), 8)
            or field_proc.poll() is not None
        ):
            evidence.append(f"field never ready: {lab.err_head('gtk-hypr.err')}")
            return None, True, evidence

        # The SECOND ImeProcess binds the HYPR socket (one IM per SEAT — the
        # sway host stays bound to sway's socket; this one is Hyprland's).
        hypr_proc = start_adapter(
            lab,
            log_name="hypr_ime_host.jsonl",
            on_event=hypr_events,
            seat_env=hypr_seat,
        )
        # a bare hyprctl call without --sig is an isolation breach.
        for _ in range(5):
            try:
                sig_scoped_ipc(
                    lab, sig, "dispatch", "focuswindow", f"class:{FIELD_APP_ID}"
                )
            except (sp.TimeoutExpired, OSError):
                pass
            if wait_host_event(hypr_events, hypr_proc, 0, "activate", 2):
                break
        activated = hypr_events.count("activate") > 0
        branches = {"activate": "activated" if activated else "not_activated"}
        t_ms: dict = {}
        reasons: dict = {}
        acq = hypr_proc.request("acquire", timeout=3)
        reasons["acquire"] = (acq or {}).get("reason", "no reply")
        branches["surround"] = "sent" if (acq or {}).get("ok") else "never_sent"

        def fdump():
            try:
                return json.loads((lab.root / "field.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        def wait_text(target, seconds):
            return until(
                lambda: (d := fdump()) is not None and d.get("text") == target, seconds
            )

        r = host_show(hypr_proc, ASCII_INSERT_LINE)
        if r is not None and "harness_error" in r:
            evidence.append(
                f"show request rejected by the transport: {r['harness_error']!r}"
            )
            return None, False, evidence
        t_ms["insert"] = (r or {}).get("t_ms")
        got = wait_text(ASCII_INSERT_LINE, 4)
        cur = (fdump() or {}).get("text", "")
        if got is not None:
            branches["insert"] = "delivered"
        elif cur == "":
            branches["insert"] = "not_delivered"
        else:
            evidence.append(f"insert probe out-of-legal buffer {cur!r}")
            return None, False, evidence
        if branches["insert"] == "delivered":
            r = host_show(
                hypr_proc,
                TERM_PAYLOADS["correct_replacement"],
                before=len(TERM_PAYLOADS["correct_delete"].encode("utf-8")),
            )
            if r is not None and "harness_error" in r:
                evidence.append(
                    f"show request rejected by the transport: {r['harness_error']!r}"
                )
                return None, False, evidence
            t_ms["correct"] = (r or {}).get("t_ms")
            reasons["show_correct"] = (r or {}).get("result", "no reply")
            got_c = wait_text(CORRECT_APPLIED_LINE, 4)
            cur = (fdump() or {}).get("text", "")
            if got_c is not None:
                branches["correct"] = "delete_applied"
            elif cur == CORRECT_IGNORED_LINE:
                branches["correct"] = "delete_ignored"
            else:
                evidence.append(f"correct probe out-of-legal buffer {cur!r}")
                return None, False, evidence
        rows = {"preedit": PREEDIT_NOTE, **branches}
        return rows, True, evidence
    finally:
        if hypr_proc is not None:
            try:
                hypr_proc.stop(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        if field_proc is not None:
            lab.kill(field_proc)


def run_hyprland(lab: Lab, sway_sock: str) -> None:
    attempts: list[dict] = []
    pass_flag: bool | None = True
    stale_sigs: set[str] = set()
    for spec in HYPR_LADDER:
        variant = spec["variant"]
        env = build_hypr_env(lab.env, spec, sway_sock)
        err_name = f"hypr-{variant}.err"
        for p in lab.root.glob("hypr/*/.wl_socket"):
            stale_sigs.add(p.parent.name)  # only accept NEW sockets this attempt
        hypr = lab.spawn(["Hyprland"], stderr_name=err_name, env=env)
        sig = until(
            lambda: next(
                (
                    p.parent.name
                    for p in lab.root.glob("hypr/*/.wl_socket")
                    if p.is_socket() and p.parent.name not in stale_sigs
                ),
                None,
            ),
            25,
        )
        if not sig or hypr.poll() is not None:
            head = lab.err_head(err_name, 400)
            attempts.append(
                {
                    "variant": variant,
                    "env": env,
                    "booted": False,
                    "err_head": head,
                    "rows_measured": None,
                }
            )
            print(
                json.dumps(
                    {
                        "row": "hypr-attempt",
                        "variant": variant,
                        "booted": False,
                        "err_head": head,
                    }
                ),
                flush=True,
            )
            lab.kill(hypr)
            continue
        hypr_seat = dict(env)
        hypr_seat["HYPRLAND_INSTANCE_SIGNATURE"] = sig
        hypr_seat["WAYLAND_DISPLAY"] = f"hypr/{sig}/.wl_socket"
        rows, ok, evidence = hypr_field_rows(lab, hypr_seat, sig)
        attempts.append(
            {
                "variant": variant,
                "env": env,
                "booted": True,
                "err_head": "",
                "rows_measured": rows,
            }
        )
        print(
            json.dumps(
                {
                    "row": "hypr-attempt",
                    "variant": variant,
                    "booted": True,
                    "rows": rows,
                    "evidence": evidence,
                }
            ),
            flush=True,
        )
        if not ok:
            pass_flag = False  # out-of-legal buffer = harness bug
        break  # first boot wins — the ladder exists for BOOT failures
    hypr_status = hypr_row_status(attempts_from_verdict({"attempts": attempts}))
    lab.verdict("hypr-relay", pass_flag, attempts=attempts, status=hypr_status)


# --- T5: optional passive live-registry listing (default OFF) ------------------------


def run_live_registry(lab: Lab) -> None:
    """The ONE documented live-session posture (im-lab README:79-84): connect
    to the live Hyprland socket, list globals, exit. No binds, no input, no
    compositor IPC of any kind. Opt-in via IME_G3_MATRIX_LIVE_REGISTRY=1;
    NEVER flips a row."""
    live_sock = os.environ.get("IME_G3_LIVE_SOCK", "")
    live_sig = os.environ.get("IME_G3_LIVE_SIG", "")
    if os.environ.get(LIVE_REG_ENV) != "1" or not live_sock or not live_sig:
        lab.verdict(
            "live-registry",
            None,
            note=(
                "skipped (passive live-registry listing is opt-in: set "
                f"{LIVE_REG_ENV}=1 with a live Hyprland session; posture: "
                "connect/list/exit only, never flips a row status)"
            ),
        )
        return
    env = dict(lab.env)
    env["WAYLAND_DISPLAY"] = live_sock
    env["HYPRLAND_INSTANCE_SIGNATURE"] = live_sig
    try:
        g = sp.run(
            [sys.executable, str(REPO / "tools" / "im-lab" / "globals.py"), "json"],
            env=env,
            capture_output=True,
            timeout=15,
        )
        data = json.loads(g.stdout.decode() or "{}")
        lab.verdict(
            "live-registry",
            True,
            advertisement=data.get("text_injection", {}),
            note="passive listing only — no row status derives from this",
        )
    except (sp.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        lab.verdict("live-registry", None, note=f"live registry listing failed: {e!r}")


# --- versions + invariants ------------------------------------------------------------


def capture_versions(lab: Lab) -> dict:
    versions = {"kernel": platform.uname().release}
    for name, args in (
        ("sway", ["sway", "--version"]),
        ("foot", ["foot", "--version"]),
        ("kitty", ["kitty", "--version"]),
        ("ghostty", ["ghostty", "--version"]),
        ("hyprland", ["Hyprland", "--version"]),
    ):
        try:
            versions[name] = first_version_line(
                lab.cmd(args, timeout=5).decode(errors="replace")
            )
        except (sp.TimeoutExpired, OSError, sp.SubprocessError):
            versions[name] = "unknown"
    try:
        pacman = (
            lab.cmd(
                [
                    "pacman",
                    "-Q",
                    "foot",
                    "kitty",
                    "ghostty",
                    "hyprland",
                    "sway",
                    "gtk4",
                ],
                timeout=5,
            )
            .decode(errors="replace")
            .strip()
        )
        versions["pacman"] = " | ".join(pacman.splitlines())
        versions["pkg"] = pacman_versions(pacman)
    except (sp.TimeoutExpired, OSError, sp.SubprocessError):
        versions["pacman"] = versions["pkg"] = "unknown"
    print(json.dumps({"row": "versions", **versions}, ensure_ascii=False), flush=True)
    try:
        (lab.root / "versions.json").write_text(json.dumps(versions))
    except OSError:
        pass
    return versions


def check_global_invariants(
    lab: Lab, host_logs: list[str], collectors: list[_EventCollector]
) -> None:
    """Whole-run assertions: zero grab_key events in every host event log and
    collector (IM commits generate ZERO key events — delivery cannot
    self-trigger takeover), and every terminal verdict's branches still
    validate against the closed legal sets."""
    bad: list[str] = []
    for log in host_logs:
        try:
            if '"grab_key"' in (lab.root / log).read_text(errors="replace"):
                bad.append(f"grab_key-in-{log}")
        except OSError:
            pass
    for i, c in enumerate(collectors):
        if c.count("grab_key"):
            bad.append(f"grab_key-in-collector-{i}")
    for v in lab.verdicts:
        if v.get("branches") and v.get("terminal"):
            try:
                outcome_from_verdict(v)
            except (ValueError, KeyError) as e:
                bad.append(f"illegal-branches:{v['row']}:{e!r}")
    lab.verdict("global-invariants", not bad, checks=bad)


# --- phases -----------------------------------------------------------------------------


def run(root: Path) -> None:
    if not (
        root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
        and root.name.startswith(PREFIX)
        and os.environ.get("WLR_BACKENDS") == "x11"
    ):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    lab = Lab(root)
    proc = None
    hypr_host_log = "hypr_ime_host.jsonl"
    try:
        sway_sock = start_desktop(lab)
        os.environ.update(lab.env)  # the ImeProcess child inherits the SEAT env
        proc = start_adapter(lab)
        versions = capture_versions(lab)
        pkg = versions.get("pkg") if isinstance(versions.get("pkg"), dict) else {}
        for name, spawn_args, app_id in TERM_SPAWNS:
            run_term_row(
                lab,
                proc,
                name,
                spawn_args,
                app_id,
                pkg.get(name) or versions.get(name, "unknown"),
            )
        run_hyprland(lab, sway_sock)
        run_live_registry(lab)
        check_global_invariants(lab, ["ime_host.jsonl", hypr_host_log], [lab.events])
    except Exception as e:  # noqa: BLE001 — one bad block still tears down honestly
        lab.verdict("harness", False, error=repr(e))
    finally:
        try:
            if proc is not None:
                proc.stop(timeout=5)  # bounded SIGTERM -> killpg SIGKILL
        except Exception:  # noqa: BLE001
            pass
        lab.teardown()  # killpg our own session groups — never a pattern sweep
    fails = [v["row"] for v in lab.verdicts if v["pass"] is False]
    print(
        json.dumps(
            {
                "rows": len(lab.verdicts),
                "passed": sum(1 for v in lab.verdicts if v["pass"] is True),
                "skipped": sum(1 for v in lab.verdicts if v["pass"] is None),
                "failed": len(fails),
                "failed_rows": fails,
            }
        ),
        flush=True,
    )
    if fails:
        raise SystemExit(1)


def _cleanup_stale_dirs() -> None:
    """Remove scratch dirs from an aborted earlier run (bounded tmpfs scratch).
    NO pattern sweep over processes — killpg owns OUR session groups only."""
    for stale in Path("/tmp").glob(PREFIX + "*"):
        shutil.rmtree(stale, ignore_errors=True)


def main() -> None:
    if os.environ.get(GATE_ENV) != "1":
        print(
            json.dumps(
                {
                    "row": "gate",
                    "pass": None,
                    "note": f"refusing to run live: set {GATE_ENV}=1 "
                    f"(usage: {GATE_ENV}=1 {sys.executable} {sys.argv[0]})",
                }
            ),
            flush=True,
        )
        raise SystemExit(2)
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        # INNER run invocation: our own argv carries the tmpdir path.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        run(Path(sys.argv[2]))
        return
    if len(sys.argv) != 1:
        print(f"usage: {GATE_ENV}=1 {sys.executable} {sys.argv[0]}", file=sys.stderr)
        raise SystemExit(2)
    _cleanup_stale_dirs()
    with tempfile.TemporaryDirectory(prefix=PREFIX) as folder:
        root = Path(folder)
        bus = root / "private-bus.conf"
        bus.write_text(
            "<busconfig><type>session</type><listen>unix:tmpdir="
            + folder
            + '</listen><policy context="default">'
            '<allow send_destination="*"/><allow own="*"/>'
            '<allow receive_sender="*"/></policy></busconfig>'
        )
        # The LIVE-registry posture inputs, captured BEFORE the re-exec (the
        # inner env is disposable; only the driver sees the operator session).
        live_sock = ""
        live_sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("XDG_RUNTIME_DIR"):
            cand = Path(os.environ["XDG_RUNTIME_DIR"]) / os.environ["WAYLAND_DISPLAY"]
            if cand.is_socket():
                live_sock = str(cand)
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": folder,
            "XDG_RUNTIME_DIR": folder,
            "XDG_CONFIG_HOME": folder,
            "XDG_CACHE_HOME": folder,  # Hyprland crash reports use passwd-home otherwise
            "TMPDIR": folder,
            "GDK_BACKEND": "wayland",
            "WLR_BACKENDS": "x11",
            "WLR_LIBINPUT_NO_DEVICES": "1",
            "WLR_RENDERER": "pixman",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "MESA_SHADER_CACHE_DISABLE": "true",
            "XDG_SESSION_TYPE": "wayland",
            "LANG": "C.UTF-8",
            "GTK_A11Y": "none",
            "GIO_USE_VFS": "local",
            GATE_ENV: "1",  # forward the driver's own opt-in gate
            "IME_G3_LIVE_SOCK": live_sock,
            "IME_G3_LIVE_SIG": live_sig,
            "PYTHONPATH": str(REPO),
        }
        # Own the WHOLE session process group: on timeout kill the group so the
        # dbus session cannot survive reparented to init and hold pipes open.
        proc = sp.Popen(
            [
                "xvfb-run",
                "-a",
                "dbus-run-session",
                f"--config-file={bus}",
                "--",
                sys.executable,
                str(Path(__file__).resolve()),
                "run",
                folder,
            ],
            env=env,
            cwd=str(REPO),
            start_new_session=True,
        )
        try:
            proc.wait(timeout=390)  # bounded well inside the outer `timeout 420`
        except sp.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except sp.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            print(
                json.dumps({"row": "harness", "pass": False, "error": "outer timeout"}),
                flush=True,
            )
            raise SystemExit(1)
        # forward the INNER verdict exit code — proc.wait() alone would mask it
        if proc.returncode not in (0, None):
            raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
