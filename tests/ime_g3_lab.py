#!/usr/bin/env python3
"""ime_g3_lab — THE G3 real-field harness (P1.M4.T5.S1): GTK-class row matrix
R1–R5 driven through the REAL takeover-complete IM-v2 adapter
(voice_typing/ime ImeProcess + ImeTarget), with frame-level single-edit
instrumentation. NOT collected by pytest (no test_ prefix; env-gated). Run by
hand against a PRIVATE disposable desktop ONLY — it never touches the live
desktop, the real clipboard, the default microphone, or the user's service
(owns its ImeProcess; no control-socket/authority calls anywhere):

    timeout 300 env IME_G3_LAB=1 .venv/bin/python tests/ime_g3_lab.py

Rows (one JSON verdict line each, mirrored to <root>/verdicts.jsonl; t_ms is
mechanism-level info — NEVER G5; R.7: "Assert editor contents + cursor + the
visible prompt; no transient delete/retype frames"):
  R1 gtk-short-updates      6 short insert show()s: APPLIED, byte-exact, cursor
                            at end, cseq delta in (1,2), frame oracle = exactly
                            ONE text transition, zero transient frames.
  R2 gtk-firstword-20sent   ~1.2–2 KB 20-sentence span inserted, then its FIRST
                            word corrected (delete_surrounding + commit, ONE
                            wire commit): byte-exact, single visible edit,
                            reach beyond one utterance, pre-op recheck() ok.
  R3 gtk-identical-finals   the same final span show()n 3x: UNCHANGED each,
                            cseq delta 0, zero frame transitions, host dones
                            unchanged — the zero-diff law on a real field.
  R4 gtk-long-unicode       (a) 951 B multilingual insert; (b) ~3.5 KB mixed
                            insert; (c) >4 KB payload REFUSED at the 4000 B
                            commit cap (never chunked), field untouched.
  R5 gtk-refusing-readonly  the field app booted --readonly: no visible edit
                            under any branch; the ACTUAL branch (acquire
                            refuses / show refused / show unknown /
                            applied-but-ignored) is recorded honestly, then a
                            fresh writable field takes one insert (adapter not
                            wedged).

Boot pattern copied from tests/ime_correction_lab.py (itself from
tools/im-lab/imlab_run.py — READ-ONLY evidence records, never edited):
xvfb-run -a + dbus-run-session --config-file=<private bus> + sway x11 backend
on a disposable HOME/XDG_RUNTIME_DIR/TMPDIR; the field is
tests/ime_g3_field_gtk.py on SYSTEM python3 (the venv has no gi); the adapter
is ImeProcess (venv python, cwd=repo root) driving ImeTarget. The frame oracle
and payload/status vocabulary live in tests/ime_g3_support.py (pure stdlib).
Scratch stays in ONE TemporaryDirectory (RAM-backed tmpfs); the host event log
is EventLogWriter-capped at 64 KiB; field dumps cap at 2000 writes; teardown
kills our own session groups (killpg) and never pattern-sweeps. Without
IME_G3_LAB=1: prints skipped, exits 0. Exit codes: 0 all rows pass, 1 any
row failed, 2 gate/env misuse.
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

from voice_typing.bulk_delivery import ShowResult
from voice_typing.ime.manager import ImeProcess
from voice_typing.ime.target import ImeTarget, FieldBinding

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ime_g3_support import build_payloads, single_edit_analysis  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
GATE_ENV = "IME_G3_LAB"
PREFIX = "ime-g3-lab-"
FIELD_APP = REPO / "tests" / "ime_g3_field_gtk.py"
FIELD_TITLE = "imlab-g3-field-gtk"
SYSTEM_PY = shutil.which("python3") or "python3"


def until(probe, seconds: float):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        v = probe()
        if v is not None and v is not False and v != "":
            return v
        time.sleep(0.02)
    return None


def _field(lab: "Lab", tag: str = "") -> dict | None:
    try:
        return json.loads(
            (lab.root / f"field{('-' + tag) if tag else ''}.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return None


class _EventCollector:
    """on_event callback: bounded deque (never unbounded), plus a count helper.
    The DURABLE event record is the host's capped EventLogWriter file; this is
    row-convenience only."""

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
        self.field_proc: sp.Popen | None = None
        self.verdicts: list[dict] = []
        self.events = _EventCollector()

    def spawn(self, args, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr_name=None):
        err = (self.root / stderr_name).open("wb") if stderr_name else sp.DEVNULL  # noqa: SIM115
        p = sp.Popen(
            args,
            stdin=stdin,
            stdout=stdout,
            stderr=err,
            env=self.env,
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

    def cmd(self, args, timeout=5):
        return sp.run(
            args,
            stdin=sp.DEVNULL,
            stdout=sp.PIPE,
            stderr=sp.DEVNULL,
            env=self.env,
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

            digest = hashlib.sha256(png.read_bytes()).hexdigest()[:16]
            return digest
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


def start_desktop(lab: Lab) -> None:
    conf = lab.root / "sway.conf"
    conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
    sway = lab.spawn(["sway", "-c", str(conf)])
    if (
        not until(lambda: next(lab.root.glob("sway-ipc.*.sock"), None), 7)
        or sway.poll() is not None
    ):
        raise RuntimeError("private Sway failed to start")
    lab.env["SWAYSOCK"] = str(next(lab.root.glob("sway-ipc.*.sock")))
    lab.env["WAYLAND_DISPLAY"] = until(
        lambda: next(
            (p.name for p in lab.root.glob("wayland-*") if p.is_socket()), None
        ),
        7,
    )
    lab.env["PYTHONPATH"] = str(REPO)


def spawn_field(lab: Lab, tag: str = "", readonly: bool = False) -> sp.Popen:
    """Boot the field app on SYSTEM python3 (PyGObject lives there — d2 map §6).
    The adapter stays on the venv python; they share only the private seat."""
    args = [SYSTEM_PY, str(FIELD_APP), str(lab.root)]
    if readonly:
        args.append("--readonly")
    if tag:
        args += ["--tag", tag]
    err_name = f"gtk{('-' + tag) if tag else ''}.err"
    p = lab.spawn(args, stderr_name=err_name)
    lab.field_proc = p  # R5 kills THE FIELD — never a generic alive-proc match
    suffix = f"-{tag}" if tag else ""
    if (
        not until(lambda: (lab.root / f"field{suffix}.ready").exists(), 8)
        or p.poll() is not None
    ):
        raise RuntimeError(
            f"field{suffix} never became ready: {lab.err_head(err_name)}"
        )
    return p


def _verify_agrees(proc: ImeProcess, expected: str, ev: dict) -> bool:
    """Assertion family 6: target-CONFIRMED text vs the field dump.

    GTK caps the client-side surrounding_text window near the cursor (~4 KiB,
    measured 3999 B on this stack): for fields beyond the cap, FULL agreement
    is impossible by toolkit design and agreement is asserted on the overlap —
    the caret sits at the END, so the snapshot must be a byte-exact SUFFIX of
    the expected field text. The measured cap is recorded either way."""
    v = proc.request("verify", timeout=2.5) or {}
    vtext = v.get("text") or ""
    exp = expected.encode("utf-8")
    got = vtext.encode("utf-8")
    ev["verify_bytes"] = v.get("bytes")
    ev["expected_bytes"] = len(exp)
    if v.get("snapshot_truncated"):
        ev["verify_note"] = "host head cap"
        return False
    if len(got) < len(exp):
        if not got or not exp.endswith(got):
            ev["verify_head"] = vtext[:40]
            ev["verify_tail"] = vtext[-40:]
            return False
        ev["verify_note"] = (
            f"snapshot window {len(got)} B < field {len(exp)} B — GTK caps "
            f"surrounding_text near the cursor; suffix agreement verified"
        )
        return True
    if got != exp:
        ev["verify_head"] = vtext[:40]
        ev["verify_tail"] = vtext[-40:]
        return False
    return True


def _focused_title(lab: "Lab") -> str | None:
    """Title of the focused sway node (focus evidence for the readonly row)."""
    try:
        tree = json.loads(lab.cmd(["swaymsg", "-r", "-t", "get_tree"]).decode())
    except (sp.TimeoutExpired, OSError, json.JSONDecodeError, ValueError):
        return None
    stack = [tree]
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        # WINDOW nodes only — a focused WORKSPACE (named e.g. "1") is not focus
        if n.get("type") in ("con", "floating_con") and n.get("focused"):
            return n.get("name")
        stack.extend(n.get("nodes") or [])
        stack.extend(n.get("floating_nodes") or [])
    return None


def start_adapter(lab: Lab) -> ImeProcess:
    """Spawn the REAL adapter: ImeProcess (venv python; cwd=repo root is
    inherited from the outer spawn; PYTHONPATH=REPO set by start_desktop)."""
    host_log = lab.root / "ime_host.jsonl"  # EventLogWriter-capped at 64 KiB
    proc = ImeProcess(log_path=str(host_log), on_event=lab.events)
    if not proc.spawn(timeout=15):
        raise RuntimeError(
            f"ImeProcess spawn failed (state={proc.state}): "
            f"{lab.err_head('im_host.err')} events={list(lab.events.items)[-3:]}"
        )
    if not until(
        lambda: host_log.exists() and "globals" in host_log.read_text(errors="replace"),
        7,
    ):
        raise RuntimeError("ime_host never became the seat's input method")
    return proc


def _ping(proc: ImeProcess) -> dict:
    r = proc.request("ping", timeout=1.0) or {}
    return {"activated": bool(r.get("activated")), "dones": int(r.get("dones", 0))}


def wait_activated(proc: ImeProcess, seconds: float = 8.0) -> bool:
    """Pump pings until the IM reports activation (the host drains wire events
    around request handling; the manager's reader thread needs the pump)."""
    return until(lambda: _ping(proc)["activated"], seconds) is not None


def wait_deactivated(proc: ImeProcess, seconds: float = 2.0) -> bool:
    return until(lambda: not _ping(proc)["activated"], seconds) is not None


def _show(
    target: ImeTarget,
    rev_box: list[int],
    session: int,
    utterance: str,
    seq: int,
    span: str,
) -> ShowResult:
    """One controller-shaped show call; bumps expected_revision on applied
    (the host's dones +1 per wire commit)."""
    r = target.show(session, utterance, seq, rev_box[0], span)
    if r is ShowResult.APPLIED:
        rev_box[0] += 1
    return r


def _stable_dump(
    lab: Lab,
    expect_text: str,
    tag: str = "",
    seconds: float = 5.0,
    painted: bool = False,
) -> dict | None:
    """Wait until the field's own dump shows the settled expected text (the
    field dump — NOT a signal count — is the visible-field witness).
    painted=True additionally requires the dump to be POST-PAINT
    (kind == "frame"): signal-time dumps precede the frame the commit paints,
    and a change op with no paint in its window is NO visibility witness at
    all — G3 must fail it, not vacuously pass it."""

    def ok():
        f = _field(lab, tag)
        if f is None or f.get("text") != expect_text:
            return None
        if f.get("pos") != len(f.get("text", "")):
            return None
        if painted and f.get("kind") != "frame":
            return None
        return f

    return until(ok, seconds)


def _check_oracle(
    before: dict, after: dict, expect: str, bad: list[str], ev: dict
) -> dict:
    a = single_edit_analysis(before, after, expect=expect)
    ev["oracle"] = {
        k: a[k] for k in ("frames", "transitions", "transient_hashes", "painted_final")
    }
    if not a["ok"]:
        bad.append(f"oracle-{expect}")
    return a


# --- rows ----------------------------------------------------------------------


def row_r1_short_updates(lab: Lab, proc: ImeProcess, payloads) -> None:
    """R1: 6 short inserts (growing span, INSERT path, delta-only wire)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        lab.focus(f'[title="{FIELD_TITLE}"]')
        if not wait_activated(proc):
            lab.verdict(
                "gtk-short-updates",
                None,
                error="input method never activated",
                stderr=lab.err_head("gtk.err"),
            )
            return
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "gtk-short-updates", False, error=f"acquire refused: {a.reason!r}"
            )
            return
        rev = [a.revision]
        before = _field(lab)
        expected = ""
        dones = _ping(proc)["dones"]
        for i, span in enumerate(payloads["short"], start=1):
            expected = span  # cumulative — payloads["short"] IS the growing list
            r = _show(target, rev, 1, "r1", i, span)
            if r is not ShowResult.APPLIED:
                bad.append(f"op{i}-not-applied")
                ev[f"op{i}"] = r.name
                break
            after = _stable_dump(lab, expected, painted=True)
            if after is None:
                bad.append(f"op{i}-never-settled")
                break
            if after["text"].encode("utf-8") != expected.encode("utf-8"):
                bad.append(f"op{i}-byte-exact")
            if after["pos"] != len(after["text"]):
                bad.append(f"op{i}-cursor-end")
            if not 1 <= after["cseq"] - before["cseq"] <= 2:
                bad.append(f"op{i}-cseq-delta")  # GTK fires 1–2 changed per commit
            _check_oracle(before, after, "change", bad, ev)
            d2 = _ping(proc)["dones"]
            ev[f"op{i}_dones"] = d2 - dones
            if d2 - dones < 1:
                # ≥1: the commit landed AND the client acked. GTK's done-event
                # count is NOT 1:1 with wire commits (measured 1–3 per cycle —
                # the same decomposition that fires 1–2 changed signals); the
                # hard bounds live on the zero side (R3/R4c: == 0).
                bad.append(f"op{i}-wire-commits")
            dones = d2
            before = after
        v = proc.request("verify", timeout=2.5) or {}
        ev["verify_bytes"] = v.get("bytes")
        if (v.get("text") or "").encode("utf-8") != expected.encode("utf-8"):
            bad.append("target-confirmed-text")
        ok = not bad
        lab.verdict(
            "gtk-short-updates",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            ops=len(payloads["short"]),
            shot=lab.shot("r1"),
            **ev,
        )
        target.leave()
    except Exception as e:  # noqa: BLE001 — one bad row never kills the run
        lab.verdict("gtk-short-updates", None, error=repr(e))


def row_r2_firstword_20sent(lab: Lab, proc: ImeProcess, payloads) -> ImeTarget | None:
    """R2: insert the committed 20-sentence span, then correct its FIRST word
    via ONE atomic replacement (the CORRECTION path). Returns the still-bound
    target for R3 (the zero-diff law needs the same acquisition)."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    target = None
    try:
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "gtk-firstword-20sent", False, error=f"acquire refused: {a.reason!r}"
            )
            return None
        binding: FieldBinding = a.handle
        rev = [a.revision]
        committed = payloads["twenty_committed"]
        corrected = payloads["twenty_corrected"]
        pre = _f.get("text", "") if (_f := _field(lab)) else ""
        expected_insert = pre + committed
        before = _stable_dump(lab, pre)
        r = _show(
            target, rev, 2, "r2", 1, committed
        )  # INSERT path (delta = whole span)
        if r is not ShowResult.APPLIED:
            lab.verdict(
                "gtk-firstword-20sent",
                False,
                error=f"20-sentence insert not applied: {r.name}",
                reason=target.last_reason,
            )
            target.leave()
            return None
        after = _stable_dump(lab, expected_insert, painted=True)
        if after is None:
            lab.verdict(
                "gtk-firstword-20sent",
                False,
                error="field never settled after 20-sentence insert",
            )
            target.leave()
            return None
        _check_oracle(before, after, "change", bad, ev)
        if after["text"].encode("utf-8") != expected_insert.encode("utf-8"):
            bad.append("insert-byte-exact")
        # the utterance-reach witness: the span lives far beyond ONE utterance
        ev["span_bytes"] = len(committed.encode("utf-8"))
        # pre-op recheck (R.5): the correction verifies the world BEFORE the
        # wire — with OUR cumulative inserted bytes (the 20-sentence insert
        # moved the caret; inserted_bytes=0 would spuriously say "caret moved")
        ok_rc, why_rc, _rev = target.recheck(binding, target._inserted_bytes)
        ev["recheck"] = "ok" if ok_rc else f"refused ({why_rc})"
        if not ok_rc:
            bad.append("pre-op-recheck")
        dones = _ping(proc)["dones"]
        before = after
        expected_corrected = pre + corrected
        r = _show(target, rev, 2, "r2", 2, corrected)  # CORRECTION path
        if r is not ShowResult.APPLIED:
            bad.append("correction-not-applied")
            ev["correction"] = f"{r.name} ({target.last_reason})"
        else:
            after = _stable_dump(lab, expected_corrected, painted=True)
            if after is None:
                bad.append("correction-never-settled")
            else:
                if after["text"].encode("utf-8") != expected_corrected.encode("utf-8"):
                    bad.append("correction-byte-exact")
                if after["pos"] != len(after["text"]):
                    bad.append("correction-cursor-end")
                if not 1 <= after["cseq"] - before["cseq"] <= 2:
                    bad.append("correction-cseq-delta")
                _check_oracle(before, after, "change", bad, ev)
                d2 = _ping(proc)["dones"]
                ev["correction_dones"] = d2 - dones
                if d2 - dones < 1:
                    # ≥1 acked commit (see R1's dones note); the ONE-atomic-
                    # commit wire fact is the CORRECTION path itself.
                    bad.append("correction-wire-commits")
        if not _verify_agrees(proc, expected_corrected, ev):
            bad.append("target-confirmed-text")
        ok = not bad
        lab.verdict(
            "gtk-firstword-20sent",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            shot=lab.shot("r2"),
            **ev,
        )
        return target if ok else target.leave() or None
    except Exception as e:  # noqa: BLE001
        lab.verdict("gtk-firstword-20sent", None, error=repr(e))
        return None


def row_r3_identical_finals(
    lab: Lab, proc: ImeProcess, target: ImeTarget | None, payloads
) -> None:
    """R3: the same final span show()n 3x — UNCHANGED each time, zero events,
    zero edits, zero frame transitions. CONTINUES R2's acquisition: the
    zero-diff guard (rendered_equal on _last_applied_span) only hits while the
    same binding owns the span, so R2+R3 share one acquire/leave cycle."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        if target is None:
            lab.verdict(
                "gtk-identical-finals",
                None,
                error="skipped (R2 did not leave a bound target)",
            )
            return
        span = payloads["twenty_corrected"]
        before = _field(lab)
        dones = _ping(proc)["dones"]
        results = []
        for i in range(3):
            r = target.show(2, "r2", 10 + i, _rev_for(proc, target), span)
            results.append(r.name)
            if r is not ShowResult.UNCHANGED:
                bad.append(f"repeat{i}-not-unchanged")
        after = _field(lab)
        d2 = _ping(proc)["dones"]
        if after is None or before is None:
            bad.append("field-dump-missing")
        else:
            if after["cseq"] != before["cseq"]:
                bad.append("cseq-delta-nonzero")
            if after["text"].encode("utf-8") != before["text"].encode("utf-8"):
                bad.append("text-changed")
            _check_oracle(before, after, "noop", bad, ev)
        if d2 != dones:
            bad.append("wire-commits-nonzero")  # identical ⇒ ZERO events
        ev["results"] = results
        ev["dones_before"], ev["dones_after"] = dones, d2
        ok = not bad
        lab.verdict(
            "gtk-identical-finals",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
        target.leave()
    except Exception as e:  # noqa: BLE001
        lab.verdict("gtk-identical-finals", None, error=repr(e))


def _rev_for(proc: ImeProcess, target: ImeTarget) -> int:
    """A revision that satisfies the no-regression guard: the binding's revision
    floor (dones never decreases; identical finals emit no commits, so the
    caller-side counter is unchanged — the floor stays valid)."""
    binding = target._binding
    return binding.revision if binding is not None else int(_ping(proc)["dones"])


def row_r4_long_unicode(lab: Lab, proc: ImeProcess, payloads) -> None:
    """R4: (a) 951 B Unicode insert; (b) ~3.5 KB mixed insert; (c) >4 KB
    payload REFUSED at the 4000 B commit cap — never chunked, field untouched."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        target = ImeTarget(proc)
        a = target.acquire()
        if not a.ok:
            lab.verdict(
                "gtk-long-unicode", False, error=f"acquire refused: {a.reason!r}"
            )
            return
        rev = [a.revision]
        pre = _f.get("text", "") if (_f := _field(lab)) else ""
        unicode_ = payloads["unicode_951b"]
        mixed = payloads["mixed_3500b"]
        overcap = payloads["overcap_4500b"]
        subs = []
        # (a) 951 B multilingual insert
        before = _stable_dump(lab, pre, painted=True)
        r = _show(target, rev, 4, "r4", 1, unicode_)
        if r is not ShowResult.APPLIED:
            bad.append("unicode-951b-not-applied")
            ev["a"] = f"{r.name} ({target.last_reason})"
        else:
            after = _stable_dump(lab, pre + unicode_)
            if after is None or after["text"].encode("utf-8") != (
                pre + unicode_
            ).encode("utf-8"):
                bad.append("unicode-951b-byte-exact")
            elif not 1 <= after["cseq"] - before["cseq"] <= 2:
                bad.append("unicode-951b-cseq-delta")
            else:
                _check_oracle(before, after, "change", bad, ev)
            subs.append(
                (
                    "unicode-951b",
                    "FAIL" if any(b.startswith("unicode-951b") for b in bad) else "ok",
                )
            )
        # (b) ~3.5 KB mixed insert (extension of the owned span)
        before = _field(lab)  # settled post-(a) — never an unbound-variable read
        span_b = unicode_ + mixed
        r = _show(target, rev, 4, "r4", 2, span_b)
        if r is not ShowResult.APPLIED:
            bad.append("mixed-3500b-not-applied")
            ev["b"] = f"{r.name} ({target.last_reason})"
        else:
            expected_b = pre + span_b
            after = _stable_dump(lab, expected_b, painted=True)
            if after is None or after["text"].encode("utf-8") != expected_b.encode(
                "utf-8"
            ):
                bad.append("mixed-3500b-byte-exact")  # UTF-8 boundary round-trip
            elif not 1 <= after["cseq"] - before["cseq"] <= 2:
                bad.append("mixed-3500b-cseq-delta")
            else:
                _check_oracle(before, after, "change", bad, ev)
            subs.append(
                (
                    "mixed-3500b",
                    "FAIL" if any(b.startswith("mixed-3500b") for b in bad) else "ok",
                )
            )
        # (c) >4 KB — REFUSED by design, field untouched (behavior row PASSES)
        before = _field(lab)
        dones = _ping(proc)["dones"]
        r = _show(target, rev, 4, "r4", 3, span_b + overcap)
        if r is not ShowResult.REFUSED:
            bad.append("overcap-not-refused")  # refused, NEVER chunked
            ev["c"] = r.name
        else:
            after = _field(lab)
            if after is None or before is None:
                bad.append("overcap-field-dump-missing")
            else:
                if after["cseq"] != before["cseq"] or after["text"].encode(
                    "utf-8"
                ) != before["text"].encode("utf-8"):
                    bad.append("overcap-field-touched")
                _check_oracle(before, after, "noop", bad, ev)
            if _ping(proc)["dones"] != dones:
                bad.append("overcap-wire-commits")  # cap check precedes the wire
            ev["overcap_bytes"] = len((span_b + overcap).encode("utf-8"))
            subs.append(
                (
                    "overcap-4500b",
                    "refused-by-design"
                    if not any(b.startswith("overcap") for b in bad)
                    else "FAIL",
                )
            )
        if not _verify_agrees(proc, pre + span_b, ev):
            bad.append("target-confirmed-text")
        ev["subrows"] = subs
        ok = not bad
        lab.verdict(
            "gtk-long-unicode",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            shot=lab.shot("r4"),
            **ev,
        )
        target.leave()
    except Exception as e:  # noqa: BLE001
        lab.verdict("gtk-long-unicode", None, error=repr(e))


def row_r5_refusing_readonly(lab: Lab, proc: ImeProcess, payloads) -> None:
    """R5: the field app booted --readonly. Whatever branch the platform takes
    (acquire refuses / show refused / show unknown / applied-but-ignored), NO
    visible edit may land; the ACTUAL branch is recorded verbatim. Then a
    fresh WRITABLE field takes one insert — the adapter-not-wedged witness."""
    t0 = time.monotonic()
    bad: list[str] = []
    ev: dict = {}
    try:
        if lab.field_proc is not None and lab.field_proc.poll() is None:
            lab.kill(lab.field_proc)  # remove the writable field: focus unambiguous
        wait_deactivated(proc)  # tolerate the stale-activation window (bounded)
        ro = spawn_field(lab, tag="ro", readonly=True)
        lab.focus(f'[title="{FIELD_TITLE}-ro"]')
        # bounded wait until the RO WINDOW is provably the focused one — focus
        # evidence must be solid before "activation-refused" may be concluded

        def _focused_ro():
            t = _focused_title(lab)
            return t if t is not None and t.endswith("-ro") else None

        focused = until(_focused_ro, 3)
        ev["focused"] = focused
        branch = ""
        if focused is None or not focused.endswith("-ro"):
            # focus infrastructure failure — an honest infra skip, never a pass
            lab.verdict(
                "gtk-refusing-readonly",
                None,
                error=f"readonly field never got focus (focused={focused!r})",
                stderr=lab.err_head("gtk-ro.err"),
                **ev,
            )
            lab.kill(ro)
            return
        if not wait_activated(proc):
            # GTK disables the input method for a non-editable entry — the
            # refusing behavior manifests at ACTIVATION level. Record the
            # branch and prove the adapter recovers below; never a silent skip.
            branch = "activation-refused (readonly entry never enabled text-input)"
        else:
            target = ImeTarget(proc)
            a = target.acquire()
            if not a.ok:
                branch = f"acquire-refused ({a.reason})"
            else:
                before = _field(lab, "ro")
                r = _show(target, [a.revision], 5, "r5", 1, "must not land")
                if r is ShowResult.APPLIED:
                    after = _stable_dump(
                        lab, before["text"] if before else "", "ro", seconds=1.5
                    ) or _field(lab, "ro")
                    unchanged = (
                        after is not None
                        and before is not None
                        and after["text"].encode("utf-8")
                        == before["text"].encode("utf-8")
                        and after["cseq"] == before["cseq"]
                    )
                    branch = (
                        "applied-but-ignored-by-field"
                        if unchanged
                        else "applied-and-FIELD-CHANGED"
                    )
                    if not unchanged:
                        bad.append("readonly-field-changed")
                    elif before is not None:
                        _check_oracle(before, after, "noop", bad, ev)
                elif r is ShowResult.REFUSED:
                    branch = f"show-refused ({target.last_reason})"
                elif r is ShowResult.UNKNOWN:
                    branch = "show-unknown (host never saw the compositor done)"
                else:
                    branch = "show-unchanged"
                target.leave()
        after = _field(lab, "ro")
        ev["branch"] = branch
        if after is not None and after.get("keys", 0) != 0:
            bad.append("readonly-field-saw-keys")
        # --- recovery witness: a fresh WRITABLE field takes one insert ------
        lab.kill(ro)
        wait_deactivated(proc)
        spawn_field(lab, tag="w2")
        lab.focus(f'[title="{FIELD_TITLE}"]')
        if not wait_activated(proc):
            bad.append("recovery-field-never-activated")
        else:
            t2 = ImeTarget(proc)
            a2 = t2.acquire()
            if not a2.ok:
                bad.append(f"recovery-acquire-refused ({a2.reason})")
            else:
                r2 = _show(t2, [a2.revision], 5, "r5", 2, "recovered.")
                if r2 is not ShowResult.APPLIED:
                    bad.append(f"recovery-insert-not-applied ({r2.name})")
                elif _stable_dump(lab, "recovered.", "w2", painted=True) is None:
                    bad.append("recovery-never-settled")
                ev["recovery"] = r2.name
            t2.leave()
        ok = not bad
        lab.verdict(
            "gtk-refusing-readonly",
            ok,
            checks=bad,
            t_ms=int((time.monotonic() - t0) * 1000),
            **ev,
        )
    except Exception as e:  # noqa: BLE001
        lab.verdict("gtk-refusing-readonly", None, error=repr(e))


# --- global invariants + summary -------------------------------------------------


def check_global_invariants(lab: Lab, proc: ImeProcess | None) -> None:
    """Asserted across the WHOLE run: zero grab_key events (IM commits generate
    zero key events — delivery cannot self-trigger takeover), and every field
    witnessed zero received keys and zero Enter/activate submissions."""
    bad: list[str] = []
    try:
        log = (lab.root / "ime_host.jsonl").read_text(errors="replace")
        if '"grab_key"' in log:
            bad.append("grab_key-in-host-log")
    except OSError:
        pass
    if lab.events.count("grab_key"):
        bad.append("grab_key-in-event-stream")
    for f in sorted(lab.root.glob("field*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("keys", 0) != 0:
            bad.append(f"keys-nonzero:{f.name}")
        if d.get("activated", 0) != 0:
            bad.append(f"activated-nonzero:{f.name}")
    lab.verdict("global-invariants", not bad, checks=bad)


def capture_versions(lab: Lab) -> dict:
    versions = {"kernel": platform.uname().release}
    try:
        versions["sway"] = (
            sp.run(
                ["sway", "--version"],
                env=lab.env,
                timeout=5,
                stdout=sp.PIPE,
                stderr=sp.DEVNULL,
            )
            .stdout.decode()
            .strip()
        )
    except (sp.TimeoutExpired, OSError):
        versions["sway"] = "unknown"
    ready = lab.root / "field.ready"
    try:
        r = json.loads(ready.read_text(encoding="utf-8"))
        versions["gtk"] = r.get("gtk", "unknown")
        versions["pygobject"] = r.get("pygobject", "unknown")
    except (OSError, json.JSONDecodeError):
        versions["gtk"] = versions["pygobject"] = "unknown"
    try:
        out = (
            sp.run(
                ["pacman", "-Q", "gtk4", "sway"],
                env=lab.env,
                timeout=5,
                stdout=sp.PIPE,
                stderr=sp.DEVNULL,
            )
            .stdout.decode()
            .strip()
        )
        for line in out.splitlines():
            name, _, ver = line.partition(" ")
            if name == "gtk4":
                versions["pacman_gtk4"] = ver
            elif name == "sway":
                versions["pacman_sway"] = ver
    except (sp.TimeoutExpired, OSError):
        pass
    print(json.dumps({"row": "versions", **versions}, ensure_ascii=False), flush=True)
    try:
        (lab.root / "versions.json").write_text(json.dumps(versions))
    except OSError:
        pass
    return versions


# --- phases ----------------------------------------------------------------------

ROWS = (
    ("gtk-short-updates", row_r1_short_updates),
    ("gtk-firstword-20sent", row_r2_firstword_20sent),
    ("gtk-identical-finals", None),  # consumes R2's returned target
    ("gtk-long-unicode", row_r4_long_unicode),
    ("gtk-refusing-readonly", row_r5_refusing_readonly),
)


def run(root: Path) -> None:
    if not (
        root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path.home()
        and root.name.startswith(PREFIX)
        and os.environ.get("WLR_BACKENDS") == "x11"
    ):
        raise RuntimeError("Refusing to run outside the disposable desktop")
    lab = Lab(root)
    proc = None
    target_r2 = None
    try:
        start_desktop(lab)
        os.environ.update(lab.env)  # the ImeProcess child inherits the SEAT env
        proc = start_adapter(lab)
        spawn_field(lab)
        lab.focus(f'[title="{FIELD_TITLE}"]')
        capture_versions(lab)
        payloads = build_payloads()
        for row_id, fn in ROWS:
            if row_id == "gtk-identical-finals":
                row_r3_identical_finals(lab, proc, target_r2, payloads)
            elif row_id == "gtk-firstword-20sent":
                target_r2 = fn(lab, proc, payloads)
            else:
                fn(lab, proc, payloads)
        check_global_invariants(lab, proc)
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
                {"row": "gate", "pass": None, "note": f"skipped (set {GATE_ENV}=1)"}
            ),
            flush=True,
        )
        return
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
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": folder,
            "XDG_RUNTIME_DIR": folder,
            "XDG_CONFIG_HOME": folder,
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
            GATE_ENV: "1",
            "PYTHONPATH": str(REPO),
        }  # forward the driver's own opt-in gate
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
            proc.wait(timeout=280)  # bounded well inside the outer `timeout 300`
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
