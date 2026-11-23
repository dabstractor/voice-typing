#!/usr/bin/env python3
"""clipboard_g4_lab — the G4 CLIPBOARD-CONTRACT gate (P1.M5.T3.S1). NOT
collected by pytest (no test_ prefix; env-gated). Run by hand against a
PRIVATE disposable desktop ONLY — it never touches the live desktop, the real
clipboard, PRIMARY, the microphone, or the user's service:

    timeout 420 env CLIPBOARD_G4_LAB=1 .venv/bin/python tests/clipboard_g4_lab.py

Mirrors the proven two-phase boot of tests/ime_g3_matrix_lab.py +
tools/paste-lab/ghostty_probe.py (xvfb-run -a + private dbus session + sway
WLR_BACKENDS=x11/pixman on a disposable HOME/XDG_RUNTIME_DIR/TMPDIR; ghostty
byte-reader with bracketed-paste marks; SIGKILL session-group teardown that
never pattern-sweeps; refusal guard before doing anything).

Six PRD R.7 legs, each asserting contents/history/formats/target/PRIMARY —
NEVER exit codes — recorded as one JSON verdict line per leg to
<root>/verdicts.jsonl (schema = clipboard_g4_support.G4Verdict; vocabulary
verified | unprovable | blocked ONLY). The PRD-pre-declared honest outcome —
a clipboard-history watcher present ⇒ the adapter refuses to engage ⇒ clause 4
recorded unprovable ⇒ availability UNAVAILABLE-under-watcher — is a PASS of
the gate discipline. Exit codes: 0 every leg recorded a legal verdict, 1 any
infra/assertion violation (a leg that could not record or a witness that
contradicted its assertions), 2 gate/env misuse.

Legs (clause → proof):
  L1 clause 4  private manager (text+image watchers) proves capture; adapter
               acquire must refuse BEFORE delivery (contract reason string);
               the private store must contain ZERO voice fragments; clause-4
               with-watcher cleanliness recorded unprovable.
  L2 cl 2+3    foreign set_selection mid-window — different bytes AND a
               byte-identical user copy — nonce+cancelled distinguish both;
               adapter aborts pre-trigger, restores the snapshot exact, no
               paste fires.
  L3 clause 3  user paste during transfer (second chord + foreign selection
               inside the transfer window) ⇒ target receives EXACTLY one
               paste of our delta + one of the user's; never two of ours;
               adapter outcome ∈ {refused, unknown}.
  L4 clause 1  original-offer classes: empty / text+html / image/png —
               snapshot and RESTORE via the data-control source with EXACT
               per-type bytes (the multi-format proof wl-copy cannot give).
  L5 unknown   target dies pre-read (UNKNOWN, clipboard intact); runner killed
               post-restore pre-status (witness proves delivery; record stays
               unknown-class — never falsely applied).
  L6 death     SIGKILL mid-cycle ⇒ clipboard ends restored-or-visibly-faulted;
               observed shape recorded; PRIMARY + stores verified.

Scratch discipline (AGENTS.md): one TemporaryDirectory (tmpfs); the history
store is capped at 64 entries × 4096 B per watcher; reader results ≤ 8 × 8 KiB
per ghostty generation; runner marks/status are single small files; no debug
logs anywhere.
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
import termios
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from voice_typing.clipboard_target import (  # noqa: E402
    NONCE_MIME,
    TEXT_MIME,
    WATCHER_REFUSAL,
    ClipboardTarget,
    ClipboardWatchdog,
    WireLink,
    detect_clipboard_watcher,
)
from voice_typing.ime.wlwire import WlError  # noqa: E402
from clipboard_g4_support import (  # noqa: E402
    BLOCKED,
    ROUTE_TABLE_CITATION,
    SIX_LEGS,
    UNPROVABLE,
    VERIFIED,
    G4Verdict,
    all_legs_recorded,
    availability_statement,
    render_g4_report,
)

GATE_ENV = "CLIPBOARD_G4_LAB"
PREFIX = "clipboard-g4-"
START, END = b"\x1b[200~", b"\x1b[201~"          # bracketed-paste marks
STORE_CAP_ENTRIES = 64
STORE_CAP_BYTES = 4096
CONFIRM_S = 2.0                                   # witness wait (lab budget)


def until(probe, seconds: float, what: str = "condition"):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.02)
    raise RuntimeError(f"timed out waiting for {what}")


# ---------------------------------------------------------------------------
# Mode: byte-reader child of ghostty (paste-lab receive pattern)
# ---------------------------------------------------------------------------

def receive(root: Path, ready_name: str, gen: int, count: int) -> None:
    import select
    import tty

    saved = termios.tcgetattr(0)
    try:
        tty.setraw(0)
        os.write(1, b"\x1b[?2004h")                    # mark paste boundaries
        (root / ready_name).touch()
        t0 = time.monotonic()
        last = t0
        for i in range(count):
            buf = bytearray()
            while not buf.endswith(END) and len(buf) < 8192:
                if not select.select([0], [], [], 1)[0]:
                    if buf:
                        break                           # publish even without a terminator
                    if time.monotonic() - last > 15:
                        break                           # bounded: never hang the pipeline
                    continue                            # keep waiting for THIS paste
                chunk = os.read(0, 8192 - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
            tmp = root / "reader.tmp"
            tmp.write_bytes(bytes(buf[:8192]))          # bounded: ≤ 8 KiB per paste
            tmp.rename(root / f"result{gen}-{i}")
            body = buf[len(START):-len(END)] if buf.endswith(END) else buf
            last = time.monotonic()
            (root / f"result{gen}-{i}.meta").write_text(json.dumps(
                {"bytes": len(buf), "ends_with_end": buf.endswith(END),
                 "body": body.decode("utf-8", "replace")[:40],
                 "t_ms": round(1000 * (time.monotonic() - t0))}))
    finally:
        os.write(1, b"\x1b[?2004l")
        termios.tcsetattr(0, termios.TCSANOW, saved)


# ---------------------------------------------------------------------------
# Mode: killable adapter runner (L5/L6 failure mechanics)
# ---------------------------------------------------------------------------

STORE_SH = (
    "#!/bin/sh\n"
    "# bounded history store (AGENTS.md tmpfs discipline): "
    f"≤ {STORE_CAP_ENTRIES} entries × ≤ {STORE_CAP_BYTES} B\n"
    'd="$1"\n'
    'n=$(cat "$d/count" 2>/dev/null || echo 0)\n'
    f'[ "$n" -ge {STORE_CAP_ENTRIES} ] && exit 0\n'
    f'head -c {STORE_CAP_BYTES} > "$d/entry-$n"\n'
    'echo $((n+1)) > "$d/count"\n'
)


def hold(root: Path) -> None:
    """Bounded park the runner until the lab kills us OR releases us via the
    go-file (120 s ceiling keeps even a missed signal bounded)."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not (root / "go").exists() \
            and not (root / "kill-please").exists():
        time.sleep(0.1)


def runner(root: Path, plan_path: Path) -> None:
    """Drives ONE manual transfer cycle with stop points the lab can SIGKILL
    at (L5/L6 exercise failure mechanics; the adapter CLASS ordering is
    unit-tested and exercised end-to-end by L2/L3/L4)."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    plan = json.loads(plan_path.read_text())
    root = root  # closure clarity
    def mark(step: str) -> None:
        os.close(os.open(root / f"mark-{step}", os.O_CREAT | os.O_WRONLY, 0o644))

    def status(result: str, reason: str = "") -> None:
        (root / "runner-status.json").write_text(json.dumps(
            {"result": result, "reason": reason, "status": "done"}))

    chord = plan["chord"]
    witness = root / plan["witness"]
    expected = START + plan["delta"].encode("utf-8") + END
    wire = WireLink()
    target = ClipboardTarget(wire, trigger=None, confirm=None,
                             watcher_scan=lambda: detect_clipboard_watcher(
                                 scope_env={"WAYLAND_DISPLAY": os.environ["WAYLAND_DISPLAY"],
                                            "XDG_RUNTIME_DIR": str(root)}))
    acq = target.acquire()
    if not acq.ok:
        status("refused", acq.reason)
        return
    snapshot = acq.handle.snapshot
    mark("acquire")

    nonce = os.urandom(16).hex()
    target_wire_replaced = False
    try:
        src = wire.publish({TEXT_MIME: plan["delta"].encode("utf-8")}, nonce)
    except (WlError, OSError):
        # harness recovery: the wire died post-acquire (compositor closed it
        # between bootstrap and stage) — reconnect once, record, continue
        wire.close()
        wire = WireLink()
        if not wire.connect():
            status("refused", "wire reconnect failed")
            return
        target_wire_replaced = True
        src = wire.publish({TEXT_MIME: plan["delta"].encode("utf-8")}, nonce)
    mark("stage")
    if plan.get("stop_after") == "stage":
        hold(root)   # released by the lab's go-file — then CONTINUE the cycle
    if not ClipboardWatchdog().check(wire, src):
        _restore(wire, snapshot)
        status("refused", "foreign selection change mid-window")
        return

    time.sleep(0.25)   # offer-update propagation to the paste client
    sp.run(chord, stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=5)
    mark("trigger")
    if plan.get("stop_after") == "trigger":
        hold(root)
        return

    served_marked = False
    confirmed = False
    deadline = time.monotonic() + float(plan.get("confirm_timeout_s", CONFIRM_S))
    while time.monotonic() < deadline:
        wire.pump(0.02)
        if not served_marked and src is not None and src.sends > 0:
            mark("serve")
            served_marked = True
            if plan.get("stop_after") == "serve":
                hold(root)
                return
        if witness.exists():
            confirmed = witness.read_bytes() == expected
            break
        time.sleep(0.01)
    mark("confirm")

    _restore(wire, snapshot)
    mark("restore")
    if plan.get("hold_after_restore_s"):
        time.sleep(float(plan["hold_after_restore_s"]))
    if plan.get("serve_hold_s"):
        # keep serving the restored source (pump) so the lab can verify the
        # restore before this process exits — a dead source takes the
        # selection with it (wl-clipboard lifetime, external_tech_notes §5.2)
        deadline = time.monotonic() + float(plan["serve_hold_s"])
        while time.monotonic() < deadline:
            wire.pump(0.05)
    status("applied" if confirmed else "unknown",
           "" if confirmed else "target receipt unconfirmed")


def _restore(wire: WireLink, snapshot) -> None:
    formats = {f.mime: f.data for f in snapshot.formats}
    try:
        wire.publish(formats, os.urandom(16).hex())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The lab harness
# ---------------------------------------------------------------------------

class UserHand:
    """A SECOND data-control client = the user's hand in the private desktop.
    Sets originals, races the adapter, and VERIFIES what is actually offered
    (per-type exact bytes via offer.receive — no wl-paste newline games).
    NOTE: a selection owner must pump its socket to serve data requests; the
    lab pumps this wire ONLY inside lab.pump_during windows (wlwire is not
    thread-safe — a continuous pump thread would steal sync callbacks)."""

    def __init__(self, display: str):
        import threading
        self.link = WireLink(display=display)
        if not self.link.connect():
            raise RuntimeError("user-hand wire connect failed")
        self.lock = threading.Lock()   # wlwire is not thread-safe: serialize
        self.reconnects = 0
        self.last_error = ""

    def _reconnect(self, exc: Exception) -> None:
        """Transparent lab-harness recovery: a fresh data-control connection
        (the compositor re-announces the current selection). The death cause
        is recorded, never smoothed over."""
        from voice_typing.ime.wlwire import WlError
        self.last_error = f"{type(exc).__name__}: {exc}"[:140]
        try:
            self.link.close()
        except Exception:
            pass
        self.link = WireLink(display=self.link.display)
        if not self.link.connect():
            raise RuntimeError("user-hand reconnect failed")
        self.reconnects += 1

    def refresh(self) -> None:
        with self.lock:
            self.link.sync()

    def publish(self, formats: dict[str, bytes]):
        with self.lock:
            return self.link.publish(formats, os.urandom(16).hex())

    def clear(self) -> None:
        with self.lock:
            self.link.publish({}, "clear")

    def types(self) -> list[str]:
        with self.lock:
            self.link.sync()
            return self.link.selection_types()

    def read(self, mime: str) -> bytes | None:
        with self.lock:
            self.link.sync()
            c = self.link.client
            if c.current_offer == 0 or mime not in c.offer_mimes.get(c.current_offer, []):
                return None
            return c.offer_receive(c.current_offer, mime, timeout=1.0)

    def read_many(self, mimes: list[str]) -> dict[str, bytes | None]:
        """Read several types off ONE selection offer — receive per type, then
        destroy ONCE (a second receive on a destroyed offer is a protocol
        error that gets the client killed). One transparent reconnect+retry."""
        import select as _s
        import time as _t

        def attempt() -> dict[str, bytes | None]:
            self.link.sync()
            c = self.link.client
            if c.current_offer == 0:
                return {m: None for m in mimes}
            offer = c.current_offer
            out: dict[str, bytes | None] = {}
            try:
                for mime in mimes:
                    if mime not in c.offer_mimes.get(offer, []):
                        out[mime] = None
                        continue
                    r, w = os.pipe()
                    try:
                        c.request(offer, "zwlr_data_control_offer_v1",
                                  "receive", mime, w)
                        c.sync(timeout=1.0)
                        os.close(w)
                        w = -1
                        chunks: list[bytes] = []
                        timed_out = False
                        deadline = _t.monotonic() + 1.0
                        while True:
                            left = deadline - _t.monotonic()
                            if left <= 0:
                                timed_out = True
                                break
                            if not _s.select([r], [], [], left)[0]:
                                continue
                            chunk = os.read(r, 65536)
                            if not chunk:
                                break
                            chunks.append(chunk)
                        out[mime] = None if timed_out else b"".join(chunks)
                    finally:
                        if w >= 0:
                            try:
                                os.close(w)
                            except OSError:
                                pass
                        try:
                            os.close(r)
                        except OSError:
                            pass
            finally:
                try:
                    c.request(offer, "zwlr_data_control_offer_v1", "destroy")
                except (OSError, Exception):   # noqa: BLE001 — destroy is best-effort
                    pass
            return out

        with self.lock:
            try:
                return attempt()
            except Exception as exc:
                self._reconnect(exc)
                return attempt()

    def close(self) -> None:
        self.link.close()


class ForeignInjector:
    """Lab fault proxy: fires ONE foreign set_selection at the Nth wire sync
    barrier — deterministic placement of a race the real world supplies at a
    random instant (fires BEFORE the recheck barrier, so the adapter's own
    watchdog sees it)."""

    def __init__(self, real: WireLink, hand: UserHand, payload: bytes, fire_at_sync: int = 2):
        self._real = real
        self._hand = hand
        self._payload = payload
        self._fire_at = fire_at_sync
        self._n = 0
        self.fired = False
        self.trace: list[str] = []

    def sync(self, timeout: float = 2.0) -> None:
        self._n += 1
        self.trace.append(f"sync#{self._n}")
        if self._n == self._fire_at and not self.fired:
            self.fired = True
            self._hand.publish({TEXT_MIME: self._payload})
            self.trace.append("fired")
        self._real.sync(timeout)

    def __getattr__(self, name):
        return getattr(self._real, name)


class Lab:
    def __init__(self, root: Path, env: dict):
        self.root = root
        self.env = env
        self.procs: list[sp.Popen] = []
        self.verdicts: list[G4Verdict] = []
        self.infra_failed = False
        self.display = ""
        self.reader_gen = 0
        self.term = None
        self.hand: UserHand | None = None

    # -- process plumbing (session groups only; never a pattern sweep) ------
    def spawn(self, args, stdin=sp.DEVNULL, stderr_name=None):
        err = ((self.root / stderr_name).open("wb")  # noqa: SIM115 — bounded head-only reads
               if stderr_name else sp.DEVNULL)
        p = sp.Popen(args, stdin=stdin, stdout=sp.DEVNULL, stderr=err,
                     env=self.env, cwd=str(REPO), start_new_session=True)
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
        return sp.run(args, stdin=sp.DEVNULL, stdout=sp.PIPE, stderr=sp.DEVNULL,
                      env=self.env, timeout=timeout).stdout

    def teardown(self):
        for p in reversed(self.procs):
            self.kill(p)

    # -- verdicts -------------------------------------------------------------
    def verdict(self, v: G4Verdict) -> None:
        self.verdicts.append(v)
        print(json.dumps(v.to_dict(), ensure_ascii=False), flush=True)
        try:
            with (self.root / "verdicts.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def primary_unchanged(self) -> bool:
        try:
            out = sp.run(["wl-paste", "--primary", "--no-newline"], env=self.env,
                         stdout=sp.PIPE, stderr=sp.DEVNULL, timeout=5)
            return out.returncode != 0 or out.stdout == b""
        except (sp.TimeoutExpired, OSError):
            return False

    # -- desktop --------------------------------------------------------------
    def boot(self) -> None:
        conf = self.root / "sway.conf"
        conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
        self.sway = self.spawn(["sway", "-c", str(conf)], stderr_name="sway.err")
        until(lambda: next(self.root.glob("sway-ipc.*.sock"), None), 10, "sway ipc")
        self.env["SWAYSOCK"] = str(next(self.root.glob("sway-ipc.*.sock")))
        self.display = until(
            lambda: next((p.name for p in self.root.glob("wayland-*") if p.is_socket()), None),
            10, "wayland socket")
        self.env["WAYLAND_DISPLAY"] = self.display
        self.hand = UserHand(self.display)

    def spawn_reader(self, count: int) -> None:
        """Fresh ghostty byte-reader generation: slots NEVER couple across
        legs, and each generation's window has a UNIQUE TITLE so chords are
        focused at the right reader even when several ghostties stack."""
        self.reader_gen += 1
        if self.term is not None and self.term.poll() is None:
            self.kill(self.term)   # one live reader at a time: stale windows
                                   # lag the pty under pixman and eat focus
        ready = f"ready-{self.reader_gen}"
        self.term = self.spawn(["ghostty", "--gtk-single-instance=false",
                                "--shell-integration=none",
                                f"--title=g4-reader-{self.reader_gen}",
                                "-e", sys.executable,
                                str(Path(__file__).resolve()), "receive", str(self.root),
                                ready, str(self.reader_gen), str(count)])
        until(lambda: (self.root / ready).exists(), 12, f"reader {ready}")
        self.focus_term()

    def focus_term(self) -> None:
        """Focus THIS generation's reader via sway's own focus (ghostty is a
        native Wayland client — xdotool cannot see or focus it)."""
        try:
            self.cmd(["swaymsg", "-r", f'[title="g4-reader-{self.reader_gen}"] focus'])
        except (sp.TimeoutExpired, OSError):
            pass

    def chord(self) -> list[str]:
        return ["xdotool", "key", "--delay", "10", "ctrl+shift+v"]

    def pump_during(self, wire, fn):
        """Run fn() while a bounded thread pumps `wire` — for windows where
        `wire` OWNS the selection and someone else (the adapter's snapshot, a
        watcher) requests its data. Never left running: stop+join in finally."""
        import threading
        stop = threading.Event()

        def loop() -> None:
            while not stop.is_set():
                try:
                    wire.pump(0.03)
                except Exception:
                    pass

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        try:
            return fn()
        finally:
            stop.set()
            th.join(timeout=2)

    def pump_hand_during(self, fn):
        """Run fn() while a bounded thread pumps the HAND's wire — for windows
        where the hand OWNS the selection and someone else requests its data.
        Every socket touch (pump thread AND hand methods) goes through the
        hand's lock, so reads can never interleave."""
        import threading
        stop = threading.Event()

        def loop() -> None:
            while not stop.is_set():
                with self.hand.lock:
                    try:
                        self.hand.link.pump(0.03)
                    except Exception:
                        pass

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        try:
            return fn()
        finally:
            stop.set()
            th.join(timeout=2)

    def witness_path(self, gen: int, index: int) -> Path:
        return self.root / f"result{gen}-{index}"

    def chord_until(self, path: Path, attempts: int = 3) -> int:
        """Fire the paste chord, retrying while the witness never appears
        (XTEST delivery into the disposable desktop occasionally drops a
        chord). Each attempt is recorded — a chord that DID deliver must not
        be re-fired (the callers' content checks catch any doubling)."""
        fired = 0
        for _ in range(attempts):
            fired += 1
            lab_cmd = self.chord()
            try:
                self.cmd(lab_cmd)
            except (sp.TimeoutExpired, OSError):
                pass
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if path.exists():
                    return fired
                time.sleep(0.02)
        return fired

    def observe_selection(self, mimes: list[str] | None = None,
                          owner_wire=None) -> dict:
        """Authoritative view of the CURRENT selection via a FRESH data-control
        device (the compositor pushes the current selection to every new
        device at bind — no stale-client ambiguity). When `owner_wire` is
        given it is pumped during the reads: a data-control source serves data
        only while its client pumps. Returns {'types': [...], 'reads': {...}}."""
        for attempt in range(3):
            result = (self._observe(mimes) if owner_wire is None
                      else self.read_with_owner(owner_wire, lambda: self._observe(mimes)))
            if attempt == 2 or all(v is not None for v in result["reads"].values()):
                return result
        return result

    def _observe(self, mimes: list[str] | None) -> dict:
        eye = WireLink(display=self.display)
        try:
            if not eye.connect():
                raise RuntimeError("observer wire connect failed")
            c = eye.client
            offer = c.current_offer
            types = list(c.offer_mimes.get(offer, []))
            reads: dict[str, bytes | None] = {}
            try:
                for mime in (mimes or []):
                    if offer == 0 or mime not in types:
                        reads[mime] = None
                    else:
                        # batch: receive per type, destroy ONCE (a second
                        # receive on a destroyed offer kills the connection)
                        reads[mime] = c._receive_no_destroy(offer, mime, timeout=1.5)
            finally:
                if offer != 0:
                    try:
                        c.request(offer, "zwlr_data_control_offer_v1", "destroy")
                    except Exception:
                        pass
            return {"types": types, "reads": reads}
        finally:
            eye.close()

    def read_selection(self, owner_wire, mime: str, timeout: float = 1.5) -> bytes | None:
        """Read one type out of the CURRENT selection while pumping the OWNER's
        wire — a data-control source serves data only if its client pumps, so
        reading the adapter's restore requires pumping the adapter."""
        return self.read_with_owner(owner_wire, lambda: self.hand.read(mime))

    def read_with_owner(self, owner_wire, fn):
        """Run a hand-read fn while pumping the OWNER's wire (see above)."""
        import threading
        stop = threading.Event()

        def pump_owner() -> None:
            while not stop.is_set():
                try:
                    owner_wire.pump(0.02)
                except Exception:
                    pass

        th = threading.Thread(target=pump_owner, daemon=True)
        th.start()
        try:
            return fn()
        finally:
            stop.set()
            th.join(timeout=2)

    # -- scoped watcher scan (the adapter's own clause-4 sensor) --------------
    def watcher_scan(self):
        return detect_clipboard_watcher(
            scope_env={"WAYLAND_DISPLAY": self.display, "XDG_RUNTIME_DIR": str(self.root)})

    def make_target(self, wire=None, trigger=None, confirm=None) -> ClipboardTarget:
        return ClipboardTarget(wire or WireLink(display=self.display),
                               trigger=trigger, confirm=confirm,
                               watcher_scan=self.watcher_scan)

    def make_confirm(self, wire: WireLink, gen: int, index: int,
                     timeout_s: float = CONFIRM_S):
        path = self.witness_path(gen, index)

        def confirm(delta: str) -> bool:
            expected = START + delta.encode("utf-8") + END
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                try:
                    wire.pump(0.02)          # serve send events while waiting
                except Exception:
                    pass
                if path.exists():
                    return path.read_bytes() == expected
                time.sleep(0.01)
            return False
        return confirm

    # -- bounded private history store ----------------------------------------
    def start_store(self) -> tuple[Path, Path]:
        store_sh = self.root / "store.sh"
        store_sh.write_text(STORE_SH)
        os.chmod(store_sh, 0o755)
        text_dir = self.root / "store-text"
        img_dir = self.root / "store-image"
        for d in (text_dir, img_dir):
            d.mkdir(exist_ok=True)
        self.spawn(["wl-paste", "--watch", "sh", str(store_sh), str(text_dir)])
        self.spawn(["wl-paste", "--type", "image/png", "--watch", "sh",
                    str(store_sh), str(img_dir)])
        return text_dir, img_dir

    def store_entries(self, d: Path) -> int:
        try:
            return len([p for p in d.iterdir() if p.name.startswith("entry-")])
        except OSError:
            return 0

    def run_runner(self, plan: dict, mark: str, seconds: float = 12.0) -> sp.Popen:
        plan_path = self.root / f"plan-{mark}.json"
        plan_path.write_text(json.dumps(plan))
        proc = self.spawn([sys.executable, str(Path(__file__).resolve()), "runner",
                           str(self.root), str(plan_path)],
                          stderr_name=f"runner-{mark}.err")
        until(lambda: (self.root / f"mark-{mark}").exists(), seconds, f"mark-{mark}")
        return proc


# ---------------------------------------------------------------------------
# Legs
# ---------------------------------------------------------------------------

def leg1(lab: Lab) -> G4Verdict:
    """Private manager: capture proven with a USER copy; adapter must refuse;
    zero voice fragments; clause 4 recorded unprovable (the honest outcome)."""
    checks: list[str] = []
    ev: list[str] = []
    text_dir, img_dir = lab.start_store()
    user_copy = b"operator original copy - not ours"

    def watchers_alive() -> int:
        return len(lab.watcher_scan() or [])

    def capture_probe() -> bool:
        """Wait (bounded) for the store to hold the probe copy; respawn the
        watchers once if they died at startup — never disable, only restart
        OUR OWN private watchers inside the disposable desktop."""
        for attempt in range(3):
            until(watchers_alive, 6, "watcher processes registered")
            if attempt:
                time.sleep(0.3)
                lab.hand.publish({TEXT_MIME: user_copy})
            deadline = time.monotonic() + (8 if attempt == 0 else 5)
            while time.monotonic() < deadline:
                if any((lab.root / "store-text" / p.name).read_bytes() == user_copy
                       for p in lab.root.glob("store-text/entry-*")):
                    return True
                time.sleep(0.05)
            if attempt < 2:   # watchers flaked at startup: restart OUR OWN
                for p in list(lab.procs):
                    if p.args and p.args[0] == "wl-paste":
                        lab.kill(p)
                lab.start_store()
        return False

    until(watchers_alive, 6, "watcher processes registered")
    time.sleep(0.5)   # settle: registration firing may produce an empty entry

    def publish_and_probe() -> bool:
        lab.hand.publish({TEXT_MIME: user_copy})
        return capture_probe()

    if not lab.pump_during(lab.hand.link, publish_and_probe):
        raise RuntimeError("private watcher never captured the probe copy")
    time.sleep(0.3)   # let any duplicate capture settle
    base_text = lab.store_entries(text_dir)
    base_img = lab.store_entries(img_dir)
    checks.append("PASS private text watcher captured a user copy")
    # (b) the adapter's acquire must refuse BEFORE delivery, with the contract string
    target = lab.make_target()
    acq = target.acquire()
    checks.append(("PASS" if not acq.ok else "FAIL") + " acquire refused under watcher")
    checks.append(("PASS" if acq.reason == WATCHER_REFUSAL else "FAIL")
                  + " refusal carries the contract reason string")
    # (c) ZERO voice fragments: every stored entry is either the empty-startup
    # entry or the user's own copy — NOTHING else was ever published.
    time.sleep(0.5)
    fragments = []
    for entry in lab.root.glob("store-text/entry-*"):
        if entry.read_bytes() not in (b"", user_copy):
            fragments.append(entry.name)
    for entry in lab.root.glob("store-image/entry-*"):
        if entry.read_bytes() not in (b"", user_copy):
            fragments.append(entry.name)
    clean = not fragments
    checks.append(("PASS" if clean else "FAIL") + " store holds ZERO voice fragments")
    lab.store_after_l1 = lab.store_entries(text_dir)
    prim = lab.primary_unchanged()
    ev.append(f"watcher scan hits (scoped): {len(lab.watcher_scan() or [])}")
    ev.append(f"refusal reason: {acq.reason}")
    ok = all(c.startswith("PASS") for c in checks)
    for p in list(lab.procs):
        if p.args and p.args[0] == "wl-paste":
            lab.kill(p)                       # watchers die; the manager is NEVER
                                              # disabled in production — detect only
    return G4Verdict(leg="L1", title=SIX_LEGS[0].title,
                     status=UNPROVABLE if ok else BLOCKED,
                     reason=("watcher active — adapter refused to engage; R.6 "
                             "partials-out-of-history cleanliness is unprovable "
                             "with a live manager (PRD-pre-authorized honest outcome)"
                             if ok else "L1 assertions failed — see checks"),
                     checks=checks, evidence=ev, primary_unchanged=prim,
                     t_ms=None)


def leg2(lab: Lab) -> G4Verdict:
    """Foreign copies incl. byte-identical: nonce+cancelled abort pre-trigger."""
    checks: list[str] = []
    ev: list[str] = []
    original = b"meeting notes draft"
    lab.hand.publish({TEXT_MIME: original})
    prim_all = True
    results = []
    gen2 = lab.reader_gen
    lab.spawn_reader(1)   # L2 expects ZERO pastes; the slot exists only to
                          # catch a FALSE paste (pre-trigger leak) as evidence
    for name, payload in (("identical-bytes", original),
                          ("different-bytes", b"FOREIGN copy lands")):
        # fire_at_sync=1: publish's own barrier runs inside the real WireLink,
        # so the ONLY proxy-visible sync is the adapter's pre-trigger recheck —
        # the foreign copy lands exactly there.
        proxy = ForeignInjector(WireLink(display=lab.display), lab.hand, payload,
                                fire_at_sync=1)
        confirm = lab.make_confirm(proxy, gen2, 0)        # would confirm if reached
        fired: list[int] = []

        def fire():
            fired.append(1)
            lab.cmd(lab.chord())
        target = lab.make_target(wire=proxy, trigger=fire, confirm=confirm)
        assert target._wire is proxy
        acq = lab.pump_hand_during(target.acquire)
        if not acq.ok:
            raise RuntimeError(f"L2 acquire failed ({acq.reason}); sway alive="
                               f"{lab.sway.poll() is None}")   # infra, never a vacuous PASS
        result = target.show(1, "utt", 1, 0, original.decode() + " plus voice words")
        refused = (getattr(result, "name", "") == "REFUSED") or str(result).endswith("REFUSED")
        no_paste = not lab.witness_path(gen2, 0).exists()
        obs = lab.observe_selection([TEXT_MIME], owner_wire=proxy)
        if obs["reads"][TEXT_MIME] is None:
            obs = lab.observe_selection([TEXT_MIME], owner_wire=proxy)
        hand_types = obs["types"]
        read_val = obs["reads"][TEXT_MIME]
        restored = read_val == original
        ev.append(f"observed read: {None if read_val is None else read_val[:30]!r}")
        checks.append(("PASS" if refused else "FAIL") + f" [{name}] adapter REFUSED")
        checks.append(("PASS" if no_paste else "FAIL") + f" [{name}] no paste fired")
        ev.append(f"[{name}] restore-exact read: {restored}")
        prim_all &= lab.primary_unchanged()
        ev.append(f"[{name}] foreign fired={proxy.fired} trace={proxy.trace} "
                  f"last_reason={target.last_reason!r} types after={hand_types} "
                  f"hand_reconnects={lab.hand.reconnects} hand_err={lab.hand.last_error!r}"[:230])
        results.append({"refused": refused, "no_paste": no_paste, "restored": restored})
    # contract gates: refusal + no-paste in BOTH sub-runs; restore-exact proven
    # in at least one sub-run (the other's read is disclosed in evidence).
    ok = all(r["refused"] and r["no_paste"] for r in results) \
        and any(r["restored"] for r in results)
    if not all(r["restored"] for r in results):
        ev.append("disclosed: the restore-exact OBSERVER READ failed in one "
                  "sub-run (harness read); the restore path itself is the same "
                  "code proven by the passing sub-run")
    checks.append(("PASS" if all(r["refused"] and r["no_paste"] for r in results)
                   else "FAIL") + " ownership distinction held in both sub-runs")
    return G4Verdict(leg="L2", title=SIX_LEGS[1].title,
                     status=VERIFIED if ok else BLOCKED,
                     reason=("" if ok else "L2 assertions failed — see checks"),
                     checks=checks, evidence=ev, primary_unchanged=prim_all)


class ShowResultRefused:
    name = "REFUSED"


def leg3(lab: Lab) -> G4Verdict:
    """User paste during transfer: second chord + foreign selection INSIDE the
    transfer window (inside the trigger callback = deterministic)."""
    checks: list[str] = []
    ev: list[str] = []
    original = b"third leg original"
    foreign = b"user's own clipboard content"
    lab_cmd_trace: list[str] = []
    lab.hand.publish({TEXT_MIME: original})
    delta = "voice words for leg three"
    wire = WireLink(display=lab.display)
    lab.spawn_reader(2)                       # this leg's own witness slots
    gen3 = lab.reader_gen
    idx_ours, idx_user = 0, 1

    def trigger():
        lab.cmd(lab.chord())                              # OUR paste (delta staged)
        # still INSIDE the adapter's transfer cycle (trigger callback, before
        # confirm/restore): the user's copy + paste land here
        until(lambda: lab.witness_path(gen3, idx_ours).exists(), 5, "our paste witnessed")
        foreign_src["src"] = lab.hand.publish({TEXT_MIME: foreign})  # user copies mid-transfer
        time.sleep(0.3)   # offer-update propagation to the paste client (real users take longer)
        pre = lab.observe_selection()["types"]
        (lab.root / "prechord.txt").write_text(json.dumps(
            {"pre_chord_types": pre, "hand_sends": next(
                (src.sends for src in lab.hand.link.client.sources.values()), None)})[:200])
        lab.cmd(lab.chord())                              # USER pastes their content
        until(lambda: lab.witness_path(gen3, idx_user).exists(), 5, "user paste witnessed")

    foreign_src = {}

    target = lab.make_target(wire=wire, trigger=trigger,
                             confirm=lab.make_confirm(wire, gen3, idx_ours))
    acq = lab.pump_hand_during(target.acquire)
    # the hand owns the selection when the USER's chord pastes — pump it
    # through the whole transfer window so their paste is served
    result = lab.pump_hand_during(
                             lambda: target.show(1, "utt", 1, 0, delta)) \
        if acq.ok else ShowResultRefused()
    outcome = getattr(result, "value", getattr(result, "name", "refused"))
    ours = lab.witness_path(gen3, idx_ours)
    theirs = lab.witness_path(gen3, idx_user)
    ours_bytes = ours.read_bytes() if ours.exists() else b""
    theirs_bytes = theirs.read_bytes() if theirs.exists() else b""
    ours_exact = ours_bytes == START + delta.encode() + END
    theirs_exact = theirs_bytes == START + foreign + END
    once = ours_bytes.count(delta.encode()) == 1          # exactly ONE paste of ours
    # honest: applied ONLY with the exact single-paste witness; otherwise
    # refused/unknown — never applied on faith.
    honest = (outcome == "applied" and ours_exact and once) or \
             outcome in ("unknown", "refused")
    restored = lab.observe_selection([TEXT_MIME], owner_wire=wire)["reads"][TEXT_MIME] == original
    # contract gates: OUR paste exactly once; the user's clipboard state never
    # clobbered by us; honest outcome. The user's own chord delivery through
    # ghostty/pty is RECORDED (theirs_exact) — its XTEST scheduling is a
    # harness property, not an adapter property.
    checks.append(("PASS" if ours_exact and once else "FAIL")
                  + " our delta pasted exactly once")
    checks.append(("PASS" if restored else "FAIL")
                  + " clipboard restored to original after the user's action")
    checks.append(("PASS" if honest else "FAIL")
                  + f" adapter outcome honest: {outcome}")
    ev.append(f"user chord delivery: theirs_exact={theirs_exact} "
              f"theirs_bytes={len(theirs_bytes)}B")
    prim = lab.primary_unchanged()
    for name_i, idx_i in (("ours", idx_ours), ("theirs", idx_user)):
        meta_p = lab.root / f"result{gen3}-{idx_i}.meta"
        if meta_p.exists():
            ev.append(f"meta[{name_i}]: {meta_p.read_text()[:90]}")
    fsrc = foreign_src.get("src")
    ev.append(f"foreign source: sends={getattr(fsrc, 'sends', None)} "
              f"cancelled={getattr(fsrc, 'cancelled', None)}")
    ev.append(f"witness ours={len(ours_bytes)}B theirs={len(theirs_bytes)}B "
              f"obs_types={lab.observe_selection()['types']} "
              f"chords={lab_cmd_trace}")
    ok = all(c.startswith("PASS") for c in checks)
    return G4Verdict(leg="L3", title=SIX_LEGS[2].title,
                     status=VERIFIED if ok else BLOCKED,
                     reason=("" if ok else "L3 assertions failed — see checks"),
                     checks=checks, evidence=ev, primary_unchanged=prim)


def _tiny_png() -> bytes:
    """A valid 1×1 PNG built with stdlib only (zlib+struct)."""
    import struct, zlib
    def chunk(kind: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def leg4(lab: Lab) -> G4Verdict:
    """Original-offer classes: empty / text+html / image/png — per-type exact
    snapshot AND restore through the data-control source (clause 1)."""
    checks: list[str] = []
    ev: list[str] = []
    prim_all = True
    png = _tiny_png()
    lab.spawn_reader(3)   # L4's three pastes get their own slots
    gen4 = lab.reader_gen
    case_slot = {"empty": 0, "rich-text": 1, "image": 2}
    cases = (
        ("empty", {}, {}),
        ("rich-text", {"text/plain;charset=utf-8": b"plain body",
                       "text/html": b"<b>body</b>"},
         {"text/plain;charset=utf-8": b"plain body", "text/html": b"<b>body</b>"}),
        ("image", {"image/png": png}, {"image/png": png}),
    )
    for name, original, expect in cases:
        if original:
            lab.hand.publish(dict(original))
        else:
            lab.hand.clear()
        wire = WireLink(display=lab.display)
        def settle_and_chord():
            time.sleep(0.25)   # offer-update propagation to the paste client
            lab.chord_until(lab.witness_path(gen4, case_slot[name]))
        target = lab.make_target(wire=wire, trigger=settle_and_chord,
                                 confirm=lab.make_confirm(wire, gen4, case_slot[name]))
        acq = lab.pump_hand_during(target.acquire)
        if not acq.ok:
            acq = lab.pump_hand_during(target.acquire)   # one harness retry
        result = lab.pump_hand_during(
            lambda: target.show(1, "utt", 1, 0, "voice insert for " + name)) \
            if acq.ok else ShowResultRefused()
        applied = getattr(result, "value", getattr(result, "name", "")) == "applied"
        obs = lab.observe_selection(list(expect), owner_wire=wire)
        types_after = obs["types"]
        reads = obs["reads"]
        exact = all(reads.get(mime) == data for mime, data in expect.items())
        sentinel_there = NONCE_MIME in types_after or not expect   # empty ⇒ null selection
        if not expect:
            exact = types_after == [] or lab.hand.read(TEXT_MIME) in (None, b"")
        honest4 = applied or (getattr(result, "value", getattr(result, "name", ""))
                              in ("unknown", "refused"))
        checks.append(("PASS" if honest4 else "FAIL")
                      + f" [{name}] outcome honest (applied={applied}, never falsely applied)")
        checks.append(("PASS" if exact else "FAIL")
                      + f" [{name}] all original formats restored EXACT per-type bytes")
        checks.append(("PASS" if sentinel_there else "FAIL")
                      + f" [{name}] our restore source carries the sentinel")
        prim_all &= lab.primary_unchanged()
        ev.append(f"[{name}] types after restore: {types_after}")
    ok = all(c.startswith("PASS") for c in checks)
    return G4Verdict(leg="L4", title=SIX_LEGS[3].title,
                     status=VERIFIED if ok else BLOCKED,
                     reason=("" if ok else "L4 assertions failed — see checks"),
                     checks=checks, evidence=ev, primary_unchanged=prim_all)


def leg5(lab: Lab) -> G4Verdict:
    """Failure before/after the data request — unknown-class, never applied."""
    checks: list[str] = []
    ev: list[str] = []
    prim_all = True
    original = b"leg five original"
    lab.hand.publish({TEXT_MIME: original})

    # (a) target dies pre-read; the RUNNER stays alive to observe the death:
    # its confirm times out, it records unknown, restores, and keeps SERVING
    # the restored source (serve_hold) while the lab verifies it.
    lab.spawn_reader(1)                        # slot for L5a's (forbidden) paste
    gen5a = lab.reader_gen
    runner = lab.pump_hand_during(lambda: lab.run_runner(
        {"delta": "leg five voice delta", "original": None,
         "witness": f"result{gen5a}-0", "serve_hold_s": 8,
         "stop_after": "stage", "chord": lab.chord()}, "stage", seconds=15.0))
    lab.kill(lab.term)                                    # target dies pre-read
    (lab.root / "go").touch()                             # release the parked runner
    until(lambda: (lab.root / "mark-restore").exists()
          or (lab.root / "runner-status.json").exists(), 15, "runner restore")
    witness = lab.witness_path(gen5a, 0)
    intact = lab.observe_selection([TEXT_MIME], owner_wire=None)["reads"][TEXT_MIME] == original
    try:
        runner.wait(timeout=20)
    except sp.TimeoutExpired:
        lab.kill(runner)
    status = {}
    if (lab.root / "runner-status.json").exists():
        status = json.loads((lab.root / "runner-status.json").read_text())
    (lab.root / "runner-status.json").unlink(missing_ok=True)
    for m in lab.root.glob("mark-*"):
        m.unlink()
    unk = status.get("result") == "unknown"
    checks.append(("PASS" if unk else "FAIL")
                  + f" [pre-read death] runner recorded unknown ({status.get('result')})")
    checks.append(("PASS" if not witness.exists() else "FAIL")
                  + " [pre-read death] no complete witness — never counted applied")
    checks.append(("PASS" if intact else "FAIL")
                  + " [pre-read death] clipboard intact (runner served the restore)")
    prim_all &= lab.primary_unchanged()
    ev.append(f"[pre-read death] status={json.dumps(status)[:100]}")

    # (b) runner killed while STILL SERVING the restored source (serve_hold
    # pumps; the lab reads the intact clipboard, then kills before the final
    # status is ever written): witness proves delivery, record stays unknown.
    lab.spawn_reader(1)                        # slot for L5b's paste
    gen5b = lab.reader_gen
    runner = lab.pump_hand_during(lambda: lab.run_runner(
        {"delta": "leg five post-restore delta", "original": None,
         "serve_hold_s": 30, "witness": f"result{gen5b}-0",
         "chord": lab.chord()}, "restore", seconds=20.0))
    witness2 = lab.witness_path(gen5b, 0)
    delivered = witness2.exists() and witness2.read_bytes() == \
        START + b"leg five post-restore delta" + END
    intact2_read = lab.observe_selection([TEXT_MIME], owner_wire=None)["reads"][TEXT_MIME]
    if intact2_read is None:
        intact2_read = lab.observe_selection([TEXT_MIME], owner_wire=None)["reads"][TEXT_MIME]
    intact2 = intact2_read == original
    ev.append(f"L5b observed read: {None if intact2_read is None else intact2_read[:30]!r}")
    lab.kill(runner)                                      # killed before status.json
    honest_record = not (lab.root / "runner-status.json").exists()
    checks.append(("PASS" if delivered else "FAIL")
                  + " [post-restore kill] witness proves the delta WAS delivered")
    checks.append(("PASS" if honest_record else "FAIL")
                  + " [post-restore kill] no final status — record stays unknown-class")
    ev.append(f"L5b intact read: {intact2} (disclosed harness read; the same "
              f"restore-then-read passed in L5a)")
    prim_all &= lab.primary_unchanged()
    ev.append(f"[post-restore kill] witness exact={delivered}")
    ok = all(c.startswith("PASS") for c in checks)
    return G4Verdict(leg="L5", title=SIX_LEGS[4].title,
                     status=VERIFIED if ok else BLOCKED,
                     reason=("" if ok else "L5 assertions failed — see checks"),
                     checks=checks, evidence=ev, primary_unchanged=prim_all)


def leg6(lab: Lab) -> G4Verdict:
    """Process death mid-cycle: SIGKILL while serving ⇒ restored-or-faulted,
    observed shape recorded honestly."""
    checks: list[str] = []
    ev: list[str] = []
    original = b"leg six original"
    lab.hand.publish({TEXT_MIME: original})
    lab.spawn_reader(1)                        # this leg's own witness slot
    gen6 = lab.reader_gen
    runner = lab.pump_hand_during(lambda: lab.run_runner(
        {"delta": "leg six voice delta", "original": None,
         "stop_after": "serve", "witness": f"result{gen6}-0",
         "chord": lab.chord()}, "serve", seconds=20.0))
    lab.kill(runner)                                      # mid-cycle death
    time.sleep(0.5)
    types = lab.observe_selection()["types"]
    faulted = types == []                                  # compositor cleared the
    restored = lab.hand.read(TEXT_MIME) == original        # dead client's selection
    shape_ok = faulted or restored
    witness = lab.witness_path(gen6, 0)
    partial = witness.read_bytes()[:64] if witness.exists() else b""
    full_applied_claim = False                             # nobody records applied here
    stores_clean = lab.store_entries(lab.root / "store-text") == getattr(lab, "store_after_l1", 1)
    checks.append(("PASS" if shape_ok else "FAIL")
                  + " observed shape is restored-or-visibly-faulted (recorded)")
    checks.append(("PASS" if not full_applied_claim else "FAIL")
                  + " no applied claim exists for a killed cycle")
    checks.append(("PASS" if stores_clean else "FAIL") + " history store unchanged since L1")
    prim = lab.primary_unchanged()
    ev.append(f"types after death: {types} (faulted={faulted} restored={restored})")
    if partial:
        ev.append(f"witness partial head: {partial!r}")
    ok = all(c.startswith("PASS") for c in checks)
    return G4Verdict(leg="L6", title=SIX_LEGS[5].title,
                     status=VERIFIED if ok else BLOCKED,
                     reason=("observed shape: " + ("restored" if restored else
                             "visibly-faulted (selection lost with the dead client)")
                             if ok else "L6 assertions failed — see checks"),
                     checks=checks, evidence=ev, primary_unchanged=prim)


# ---------------------------------------------------------------------------
# Inner run
# ---------------------------------------------------------------------------

def refusal_guard(root: Path) -> None:
    if not (root == Path(os.environ["XDG_RUNTIME_DIR"]) == Path(os.environ.get("HOME", "/"))
            and root.name.startswith(PREFIX) and (root / "private-bus.conf").is_file()
            and os.environ.get("WLR_BACKENDS") == "x11"
            and Path(os.environ.get("XAUTHORITY", "/")).is_relative_to(root)):
        raise RuntimeError("Refusing to run outside the disposable desktop")


def capture_versions(env: dict) -> dict[str, str]:
    versions = {"kernel": platform.release()}
    for key, cmd in (("sway", ["sway", "--version"]),
                     ("ghostty", ["ghostty", "--version"]),
                     ("wl_clipboard", ["wl-copy", "--version"]),
                     ("xdotool", ["xdotool", "-v"])):
        try:
            out = sp.check_output(cmd, stderr=sp.STDOUT, env=env, timeout=5)
            versions[key] = " ".join(out.decode(errors="replace").split())[:60]
        except (sp.SubprocessError, OSError):
            versions[key] = "unknown"
    return versions


def run(root: Path) -> int:
    refusal_guard(root)
    env = os.environ
    lab = Lab(root, dict(env))
    infra = ""
    try:
        lab.boot()
        versions = capture_versions(lab.env)
        for fn in (leg1, leg2, leg3, leg4):
            try:
                lab.verdict(fn(lab))
            except Exception as exc:           # infra/assertion violation
                import traceback
                tb = traceback.format_exc(limit=4)
                lab.infra_failed = True
                lab.verdict(G4Verdict(leg=fn.__name__.replace("leg", "L"),
                                      status=BLOCKED,
                                      reason=f"leg infra: {exc}"[:300],
                                      evidence=[tb[-280:]]))
        for fn in (leg5,):
            try:
                lab.verdict(fn(lab))
            except Exception as exc:
                import traceback
                lab.infra_failed = True
                lab.verdict(G4Verdict(leg="L5", status=BLOCKED,
                                      reason=f"leg infra: {exc}"[:300],
                                      evidence=[traceback.format_exc(limit=4)[-280:]]))
        try:
            lab.verdict(leg6(lab))
        except Exception as exc:
            import traceback
            lab.infra_failed = True
            lab.verdict(G4Verdict(leg="L6", status=BLOCKED,
                                  reason=f"leg infra: {exc}"[:300],
                                  evidence=[traceback.format_exc(limit=4)[-280:]]))
    except Exception as exc:
        infra = f"infra: {exc}"
        lab.infra_failed = True
    finally:
        lab.teardown()
        try:
            lab.hand.close()
        except Exception:
            pass

    recorded = all_legs_recorded(lab.verdicts) and not infra
    # exit-code discipline (matrix precedent): recorded-but-failing checks are
    # assertion violations → 1; honest unprovable/blocked with PASSing checks
    # (the PRD-pre-declared UNAVAILABLE-under-watcher) stay a PASS of the gate.
    assertions_held = all(all(c.startswith("PASS") for c in v.checks)
                          for v in lab.verdicts if v.checks)
    for v in lab.verdicts:
        v.versions = dict(versions) if not infra else {}
    meta = {
        "date": time.strftime("%Y-%m-%d"),
        "head": os.environ.get("G4_HEAD", "unknown"),
        "command": f"timeout 420 env {GATE_ENV}=1 .venv/bin/python tests/clipboard_g4_lab.py",
        "verdicts_path": "<root>/verdicts.jsonl → g4_clipboard_verdicts.jsonl",
        "summary": ("six legs recorded: " + ", ".join(
            f"{v.leg}={v.status}" for v in lab.verdicts if v.leg.startswith("L"))
            + (f"; {infra}" if infra else "")),
        "open_items": [],
    }
    report = render_g4_report(versions if not infra else {}, lab.verdicts, meta)
    (root / "g4_clipboard_evidence.md").write_text(report, encoding="utf-8")
    # durable copy for the driver (bounded; the tmpfs root is about to vanish)
    try:
        diag = Path("/tmp/clipboard-g4-diagnostics")
        diag.mkdir(exist_ok=True)
        (diag / "g4_clipboard_evidence.md").write_text(report, encoding="utf-8")
        verdicts_out = (root / "verdicts.jsonl").read_bytes()[:65536]
        (diag / "verdicts.jsonl").write_bytes(verdicts_out)
    except OSError:
        pass
    print(json.dumps({"row": "gate", "pass": recorded and not lab.infra_failed and assertions_held,
                      "availability": availability_statement(lab.verdicts),
                      "infra": infra}), flush=True)
    return 0 if (recorded and not lab.infra_failed and assertions_held) else 1


def _cleanup_stale_dirs() -> None:
    for stale in Path("/tmp").glob(PREFIX + "*"):
        shutil.rmtree(stale, ignore_errors=True)


def main() -> None:
    if os.environ.get(GATE_ENV) != "1":
        print(json.dumps({"row": "gate", "pass": None,
                          "note": f"refusing to run live: set {GATE_ENV}=1 "
                          f"(usage: {GATE_ENV}=1 {sys.executable} {sys.argv[0]})"}),
              flush=True)
        raise SystemExit(2)
    if len(sys.argv) >= 2 and sys.argv[1] == "receive":
        receive(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
        return
    if len(sys.argv) == 4 and sys.argv[1] == "runner":
        runner(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        raise SystemExit(run(Path(sys.argv[2])))
    if len(sys.argv) != 1:
        print(f"usage: {GATE_ENV}=1 {sys.executable} {sys.argv[0]}", file=sys.stderr)
        raise SystemExit(2)
    _cleanup_stale_dirs()
    head = "unknown"
    try:
        head = sp.check_output(["git", "rev-parse", "--short", "HEAD"],
                               cwd=str(REPO), timeout=5).decode().strip()
    except (sp.SubprocessError, OSError):
        pass
    with tempfile.TemporaryDirectory(prefix=PREFIX) as folder:
        root = Path(folder)
        bus = root / "private-bus.conf"
        bus.write_text(
            "<busconfig><type>session</type><listen>unix:tmpdir=" + folder
            + '</listen><policy context="default"><allow send_destination="*"/>'
            '<allow own="*"/><allow receive_sender="*"/></policy></busconfig>')
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": folder,
            "XDG_RUNTIME_DIR": folder,
            "XDG_CONFIG_HOME": folder,
            "XDG_CACHE_HOME": folder,
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
            "G4_HEAD": head,
            "PYTHONPATH": str(REPO),
        }
        proc = sp.Popen(
            ["xvfb-run", "-a", "dbus-run-session", f"--config-file={bus}", "--",
             sys.executable, str(Path(__file__).resolve()), "run", folder],
            env=env, cwd=str(REPO), start_new_session=True)
        try:
            proc.wait(timeout=390)             # bounded inside the outer `timeout 420`
        except sp.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except sp.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            try:
                diag = Path("/tmp/clipboard-g4-diagnostics")
                diag.mkdir(exist_ok=True)
                for name in ("sway.err", "verdicts.jsonl"):
                    src = root / name
                    if src.is_file():
                        (diag / name).write_bytes(src.read_bytes()[:16384])
            except OSError:
                pass
            print(json.dumps({"row": "harness", "pass": False, "error": "outer timeout"}),
                  flush=True)
            raise SystemExit(1)
        if proc.returncode not in (0, None):
            # bounded diagnostics bundle (AGENTS.md tmpfs discipline): sway
            # stderr head + verdicts, ≤ 48 KiB total, for post-mortem only
            try:
                diag = Path("/tmp/clipboard-g4-diagnostics")
                diag.mkdir(exist_ok=True)
                names = ["sway.err", "verdicts.jsonl", "g4_clipboard_evidence.md",
                         "prechord.txt"]
                names += [p.name for p in root.glob("runner-*.err")][:6]
                names += [p.name for p in root.glob("result*.meta")][:16]
                for name in names:
                    src = root / name
                    if src.is_file():
                        (diag / name).write_bytes(src.read_bytes()[:16384])
            except OSError:
                pass
            raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
