#!/usr/bin/env python3
"""g5_timing_lab — THE G5 timing gate harness (P1.M6.T4.S1). NOT collected by
pytest (no test_ prefix; env-gated). Run by hand against a PRIVATE disposable
desktop ONLY — it never touches the live desktop, the real clipboard, the
default microphone, the user's service, or any live socket (private
XDG_RUNTIME_DIR isolates the control socket + state file; the recorder child
runs use_microphone=False and is fed synthetic replay audio at the feed seam;
R.7 hygiene, Gotcha #10/#12):

    timeout -k 2 1500 env G5_TIMING_LAB=1 \
        .venv/bin/python tests/g5_timing_lab.py --route im-gtk
    timeout -k 2 1500 env G5_TIMING_LAB=1 \
        .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty

R.8 paired arms (P1.M2.T1.S4): --partial-source plain|stabilized selects the
partial callback the SPAWN CHILD installs (S1's spawn-boundary seam). The
flag is LAB-ONLY; omitting it keeps the production source (stabilized
today) — the daemon seam materializes the default, argparse never does.
Each (route, source) is ONE private CLI run; the warm line, the artifact
and every record carry the requested-vs-effective provenance (the child's
ready payload is the ONLY effective-source truth — a mismatch refuses to
measure and exits 1):

    timeout -k 2 1500 env G5_TIMING_LAB=1 \
        .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain
    timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN=~/.local/bin/pi \
        .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty --partial-source plain

Scaffold smoke (feed seam + real models + control socket, NO compositor;
NOT a measurement — run both arms to validate the wiring):

    timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
        .venv/bin/python tests/g5_timing_lab.py --route im-gtk
    timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
        .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain

A missing preflight binary/fixture (sway/xvfb-run/python3; ghostty/PI_BIN
for pi-ghostty; aligned clips) is an honest BLOCKED outcome:
{"stage":"preflight","verdict":"blocked",…} + exit 1, nothing spawned.
Stage observations are daemon-receipt g5.ReadyEvents (stage="daemon",
gen/utt/seq where the boundary provides them); stdout log lines carry
counts and provenance ONLY — no transcript text ever reaches stdout.

What it measures (PRD §4.2sexies R.7 G5): the wired bulk path (P1.M6.T2.S1)
mic→reader→BulkController→TargetAdapter→field, with the SPEECH CLOCK =
word-aligned replay of the real-voice clips (tools/asr-lab/voice/*.wav +
committed <name>.words.json fixtures) paced at 1× with zero-slice silence
(test_feed_audio.py G-silence; paced_poll.py monotonic sleep-to-target). The
GPU is WARM (resident recorder, auto_unload=0, ONE discarded warmup replay).
Visibility truth = the FIELD's own change events (R.5 value #3): the GTK
field app's G5_FIELD_TIMING=1 JSONL log (tests/ime_g3_field_gtk.py), or the
pi editor read-poll for the pi-ghostty route. All clocks are
time.monotonic(); a (mono, wall) heartbeat sanity check guards clock-source
mixing. Misses are misses (never 0 ms samples); a sustained ≥5-word backlog
or a sentence-end dump fails the route regardless of medians (Gotcha #8);
count floors (≥100 insertions AND ≥100 corrections) loop replays under
REPLAY_BUDGET and a shortfall is a REPORTED failure (Gotcha #9).

Boot skeleton copied from tests/ime_g3_lab.py (xvfb-run -a + dbus-run-session
private bus + sway x11 backend; disposable HOME/XDG_RUNTIME_DIR/TMPDIR; ONE
TemporaryDirectory; killpg teardown of OWN session groups; env-gating; exit
codes 0/1/2). The pi route boots Ghostty+pi per tests/pi_g3_row_lab.py WITH
THE DOCUMENTED HOME DELTA (pi needs its real HOME; every Wayland surface +
XDG_RUNTIME_DIR/XDG_CONFIG_HOME/TMPDIR stay isolated). The daemon runs
IN-PROCESS on a private seat and is controlled ONLY through its real control
socket (the voicectl surface; no daemon internals for control).

Exit codes: 0 every selected route passed, 1 any route failed honestly,
2 env-gate/usage misuse.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import platform
import shutil
import signal
import subprocess as sp
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import g5_timing_support as g5  # noqa: E402

GATE_ENV = "G5_TIMING_LAB"
NO_DESKTOP_ENV = "G5_NO_DESKTOP"
PREFIX = "g5-timing-lab-"
FIELD_APP = REPO / "tests" / "ime_g3_field_gtk.py"
FIELD_TITLE = "imlab-g3-field-gtk"
VOICE_DIR = REPO / "tools" / "asr-lab" / "voice"
SYSTEM_PY = shutil.which("python3") or "python3"
SAMPLE_RATE = 16000
CHUNK_S = 0.032
SETTLE_S = 4.0  # quiescence window after the last ready event: a clip's later
# utterance finals arrive seconds apart (each needs its own text() roundtrip),
# so a short window cuts the replay after utterance #1 and loses their counts.
ARM_TIMEOUT_S = 180.0  # first arm loads CUDA models (cold cuDNN can be minutes)
WARM_WAIT_S = 90.0
FINAL_TIMEOUT_S = 45.0
PI_EXT_SRC = REPO / ".pi" / "extensions" / "voice-editor.ts"

PROVENANCE_ENV_KEYS = ("G5_TIMING_LAB", "G5_NO_DESKTOP")


def log(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def until(probe, seconds: float, interval: float = 0.05):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        v = probe()
        if v:
            return v
        time.sleep(interval)
    return None


# --- audio + pacing (the speech clock's enforcer; Gotcha #1/#2) ----------------


def load_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        if (
            w.getframerate() != SAMPLE_RATE
            or w.getnchannels() != 1
            or w.getsampwidth() != 2
        ):
            raise RuntimeError(
                f"{path.name}: expected 16 kHz mono 16-bit (got {w.getframerate()} Hz)"
            )
        return w.readframes(w.getnframes())


def paced_feed(
    feed_fn,
    pcm: bytes,
    chunk_s: float = CHUNK_S,
    trailing_s: float = g5.TRAILING_SILENCE_S,
) -> float:
    """Feed 16-bit mono @16k slices sleep-to-target on time.monotonic() so
    audio-time t hits the wall at feed_start + t (paced_poll.py pattern — the
    QUEUE never paces). Trailing silence is FED as zero slices at pace (the
    test_feed_audio G-silence law). Returns feed_start."""
    import numpy as np

    step = int(SAMPLE_RATE * chunk_s)
    buf = np.frombuffer(pcm, dtype=np.int16)
    n = len(buf)
    feed_start = time.monotonic()
    i = 0
    while i < n:
        target = feed_start + i / SAMPLE_RATE
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)
        feed_fn(buf[i : i + step], SAMPLE_RATE)
        i += step
    zeros = np.zeros(step, dtype=np.int16)
    k = 0
    while k * chunk_s < trailing_s:
        target = feed_start + n / SAMPLE_RATE + k * chunk_s
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)
        feed_fn(zeros, SAMPLE_RATE)
        k += 1
    return feed_start


# --- field-log drain (bounded incremental read) --------------------------------


class FieldLog:
    """Incremental JSONL reader with a byte cursor; events capped (RAM rule)."""

    def __init__(self, path: Path, cap: int = 4000):
        self.path = path
        self.offset = 0
        self.events: collections.deque = collections.deque(maxlen=cap)

    def drain(self) -> list[g5.FieldEvent]:
        try:
            with self.path.open("rb") as fh:
                fh.seek(self.offset)
                data = fh.read()
                self.offset = fh.tell()
        except OSError:
            return []
        out = []
        for line in data.splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = g5.FieldEvent(
                t=float(rec["t_mono"]),
                text=str(rec.get("text", "")),
                kind=str(rec.get("kind", "")),
            )
            self.events.append(ev)
            out.append(ev)
        return out

    def anchor(self) -> int:
        """Normalized-token count of the field text as of the last event —
        the positional floor for the NEXT replay's visibility matching."""
        return len(g5.normalize_tokens(self.events[-1].text)) if self.events else 0

    def anchor_text(self) -> str:
        """Full field text at the last event ("" when empty) — the seed for
        the S3 changed-span diffs (ReplayRecord.anchor_text); reset edits are
        excluded downstream by matching against this pre-replay state."""
        return self.events[-1].text if self.events else ""


# --- routes ---------------------------------------------------------------------


class _Route:
    """One delivery route: boots its field instrument + builds the bundle."""

    name = ""
    needs_pi = False

    def __init__(self, lab: "_Lab"):
        self.lab = lab

    def boot(self) -> None:  # sway is already up; boot the field instrument
        raise NotImplementedError

    def field_log(self) -> FieldLog:
        raise NotImplementedError

    def bulk_target_factory(self):
        """closure (cfg) -> bundle for the daemon seam; None = the DEFAULT
        route (daemon._build_default_bulk_target: ImeProcess+ImeTarget)."""
        return None

    def preflight_note(self) -> str:
        return ""


class _Lab:
    """Private-session lab: bounded spawns, killpg teardown of OWN groups."""

    def __init__(self, root: Path):
        self.root = root
        self.procs: list[sp.Popen] = []

    def spawn(self, args: list[str], env=None, err_name: str | None = None) -> sp.Popen:
        err = (self.root / err_name).open("wb") if err_name else sp.DEVNULL  # noqa: SIM115
        p = sp.Popen(
            args,
            stdin=sp.DEVNULL,
            stdout=sp.DEVNULL,
            stderr=err,
            env=env or os.environ,
            cwd=str(REPO),
            start_new_session=True,
        )
        self.procs.append(p)
        return p

    def kill(self, p: sp.Popen) -> None:
        """One bounded killpg of an OWN session group (g3 Lab.kill shape)."""
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

    def kill_all(self) -> None:
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

    def err_head(self, name: str, n: int = 300) -> str:
        try:
            return (self.root / name).read_text(errors="replace")[:n]
        except OSError:
            return ""


def boot_sway(lab: _Lab) -> None:
    conf = lab.root / "sway.conf"
    conf.write_text("xwayland disable\nfocus_follows_mouse no\n")
    lab.spawn(["sway", "-c", str(conf)])
    if not until(lambda: next(lab.root.glob("sway-ipc.*.sock"), None), 10):
        raise RuntimeError("private Sway failed to start")
    os.environ["SWAYSOCK"] = str(next(lab.root.glob("sway-ipc.*.sock")))
    os.environ["WAYLAND_DISPLAY"] = (
        until(
            lambda: next(
                (p.name for p in lab.root.glob("wayland-*") if p.is_socket()), None
            ),
            10,
        )
        or ""
    )


class GtkRoute(_Route):
    """im-gtk: the DEFAULT bulk route (ImeProcess + ImeTarget) over the private
    seat; field = the G3 GTK app with its G5_FIELD_TIMING=1 change log (the
    visibility truth).

    Lifetime wiring: the FIELD boots ONCE (focused) and lives across lifetimes;
    each delivery lifetime spawns a FRESH IM child and waits for ITS activate
    (the enable circuit fires ~100 ms after the IM binds, against the already-
    focused field — verified live). Per-lifetime activate counting (baseline
    read BEFORE the spawn) keeps re-arms honest.

    P1.M2.T1.S4: the lab-side bridge is GONE — bulk_target_factory()
    inherits _Route's None (the DEFAULT route), so the route exercises the
    PRODUCTION startup path (daemon._build_default_bulk_target +
    _BulkTargetBundle.start(), landed in P1.M2.T1.S2): the daemon spawns its
    own IM child and runs the 2 s read-only activation pump on the arm
    worker. The lab's 3-attempt arm() retry compensates cold GTK-loop stalls
    (exactly what it exists for); a persistent activation failure is an
    HONEST route fail — no lab-side spawn/activation seam may be re-added.
    The default ImeProcess carries no log_path, so the lab-side
    ime_host.jsonl capture is lost on this route (daemon INFO +
    set_delivery_state reasons remain).
    """

    name = "im-gtk"

    def __init__(self, lab):
        super().__init__(lab)
        self.field_proc: sp.Popen | None = None

    def boot(self) -> None:
        self._spawn_field()

    def _spawn_field(self) -> None:
        if self.field_proc is not None:
            self.lab.kill(self.field_proc)
            self.field_proc = None
        # CLEAN env: the CUDA LD_LIBRARY_PATH (set later for the recorder CHILD)
        # freezes the GTK field's frame clock (mesa/GL dlopen conflicts) — the
        # IM activate handshake rides that clock and never lands without this.
        env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        env["G5_FIELD_TIMING"] = "1"
        p = self.lab.spawn(
            [SYSTEM_PY, str(FIELD_APP), str(self.lab.root)], env=env, err_name="gtk.err"
        )
        self.field_proc = p
        if (
            not until(lambda: (self.lab.root / "field.ready").exists(), 10)
            or p.poll() is not None
        ):
            raise RuntimeError(
                f"GTK field never became ready: {self.lab.err_head('gtk.err')}"
            )
        try:
            sp.run(
                ["swaymsg", "-r", f'[title="{FIELD_TITLE}"] focus'],
                stdin=sp.DEVNULL,
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL,
                timeout=5,
                check=False,
                env=os.environ,
            )
        except (sp.TimeoutExpired, OSError):
            pass

    def field_log(self) -> FieldLog:
        return FieldLog(self.lab.root / "field_timing.jsonl")


class PiGhosttyRoute(_Route):
    """pi-ghostty: pi's prompt via the S1 extension socket (tests/pi_g3_row_lab.py
    recipe, WITH THE DOCUMENTED HOME DELTA). Field truth = a 10 ms read-poll
    of the editor's own state (the extension exposes no render callback — the
    poll IS the editor's read op, R.5 #3; granularity documented in the report)."""

    name = "pi-ghostty"
    needs_pi = True

    def __init__(self, lab: _Lab):
        super().__init__(lab)
        self.sock = lab.root / "voice-typing" / "pi-editor.sock"
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None

    def boot(self) -> None:
        proj = self.lab.root / "proj"
        (proj / ".pi" / "extensions").mkdir(parents=True, exist_ok=True)
        shutil.copy(PI_EXT_SRC, proj / ".pi" / "extensions" / "voice-editor.ts")
        pi_bin = os.environ.get("PI_BIN") or shutil.which("pi")
        if not pi_bin:
            raise RuntimeError("pi binary not found (set PI_BIN)")
        shell = f"cd {proj}; exec {pi_bin} 2>{self.lab.root / 'pi.err'}"
        # ghostty renders via GL — same CUDA-LD conflict as the GTK field.
        ghostty_env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        self.lab.spawn(
            [
                "ghostty",
                "--gtk-single-instance=false",
                "--shell-integration=none",
                "-e",
                "sh",
                "-c",
                shell,
            ],
            env=ghostty_env,
            err_name="ghostty.err",
        )
        if not until(self.sock.exists, 30.0):
            raise RuntimeError(
                f"pi socket never appeared: {self.lab.err_head('pi.err')} {self.lab.err_head('ghostty.err')}"
            )
        if not until(self._editor_ready, 30.0):
            raise RuntimeError(
                f"pi editor never became ready: {self.lab.err_head('pi.err')}"
            )
        time.sleep(1.0)  # grace: let late session_start waves settle
        self._focus_ghostty()
        self._log_editor_state()
        from voice_typing.pi_editor import PiEditorClient

        self._poll_client = PiEditorClient(str(self.sock))
        self._poll_client.connect(timeout=5.0)
        self._log_path = self.lab.root / "field_timing.jsonl"
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="g5-pi-poll", daemon=True
        )
        self._poll_thread.start()

    def _focus_ghostty(self) -> None:
        """Focus the private Ghostty window (the G3 pi-row lab's takeover
        step — the editor slot acks only when pi's prompt is focused/rendered;
        without focus the shows apply text but never confirm)."""
        try:
            sp.run(
                ["swaymsg", "-r", '[app_id="ghostty"] focus'],
                stdin=sp.DEVNULL,
                stdout=sp.DEVNULL,
                stderr=sp.DEVNULL,
                timeout=5,
                check=False,
                env=os.environ,
            )
        except (sp.TimeoutExpired, OSError):
            pass

    def _log_editor_state(self) -> None:
        """The editor's exact state at each lifetime boot (stranded-fragment
        ground truth for the acquire refusals). Diagnostics only; never raises."""
        try:
            import socket as sk

            probe = sk.socket(sk.AF_UNIX, sk.SOCK_STREAM)
            probe.settimeout(3.0)
            probe.connect(str(self.sock))
            probe.sendall(b'{"op":"read"}\n')
            buf = b""
            while b"\n" not in buf:
                chunk = probe.recv(4096)
                if not chunk:
                    break
                buf += chunk
            probe.close()
            r = json.loads(buf.split(b"\n")[0])
            log(
                {
                    "stage": "pi-editor-state",
                    "owned": r.get("owned"),
                    "dirty": r.get("dirty"),
                    "text_len": len(str(r.get("text", ""))),
                }
            )
        except Exception as exc:  # noqa: BLE001
            log({"stage": "pi-editor-state", "error": repr(exc)})

    def _editor_ready(self) -> bool:
        import socket as sk

        probe = sk.socket(sk.AF_UNIX, sk.SOCK_STREAM)
        probe.settimeout(2.0)
        try:
            probe.connect(str(self.sock))
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

    def _poll_loop(self) -> None:
        """10 ms read-poll → JSONL (t_mono, t_wall, text) on change. Bounded."""
        import time as _t

        writes = 0
        last = None
        fh = self._log_path.open("a", encoding="utf-8")
        try:
            while not self._poll_stop.is_set() and writes < g5.MAX_REPORT_LINES * 200:
                try:
                    r = self._poll_client.request("read", timeout=0.25)
                    text = (r or {}).get("text")
                    if isinstance(text, str) and text != last:
                        last = text
                        writes += 1
                        fh.write(
                            json.dumps(
                                {
                                    "t_mono": round(_t.monotonic(), 6),
                                    "t_wall": round(_t.time(), 6),
                                    "text": text,
                                    "kind": "poll",
                                }
                            )
                            + "\n"
                        )
                        fh.flush()
                except Exception:  # noqa: BLE001 — a dead poll must not kill the lab
                    time.sleep(0.2)
                self._poll_stop.wait(0.01)
        finally:
            fh.close()

    def field_log(self) -> FieldLog:
        return FieldLog(self._log_path)

    def bulk_target_factory(self):
        from voice_typing.pi_editor import (
            PiEditorClient,
            PiEditorTarget,
            PiEditorTakeoverWatch,
        )

        sock_str = str(self.sock)

        class _CancelOnLeaveTarget:
            """Instrument reset: on leave(), cancel the owned span FIRST (the
            extension removes what it owns while the binding is still alive),
            then the real leave(). ctrl.stop calls target.leave() — a teardown-
            time cancel would be too late (leave clears the binding, and a
            stranded owned range makes the NEXT acquire refuse). Post-stop the
            prompt is clean for the next measured lifetime."""

            def __init__(self, inner):
                self._inner = inner

            def leave(self):
                try:
                    r = self._inner.cancel()
                    log(
                        {
                            "stage": "pi-leave-cancel",
                            "result": getattr(r, "name", str(r)),
                            "reason": getattr(self._inner, "last_reason", ""),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    log({"stage": "pi-leave-cancel", "error": repr(exc)})
                # the utterance-close design clears the target's span bookkeeping
                # but the EXTENSION's owned range persists until an explicit
                # cancel op (the trace_07 pin skips it when nothing is pending).
                # The lab's instrument reset sends the raw op so the next
                # lifetime's acquire starts from a clean prompt.
                try:
                    self._client.request("cancel", timeout=3.0)
                except Exception as exc:  # noqa: BLE001
                    log({"stage": "pi-leave-cancel-raw", "error": repr(exc)})
                self._inner.leave()

            def __getattr__(self, name):
                return getattr(self._inner, name)

        class _G5PiBundle:
            """The daemon-seam bundle for the pi-editor route (P1.M6.T2.S1 shape)."""

            def __init__(self):
                self.client = PiEditorClient(sock_str)
                self.target = _CancelOnLeaveTarget(PiEditorTarget(self.client))
                self.proc = None
                self._watch = None

            def attach(self, controller):
                self._watch = PiEditorTakeoverWatch(
                    controller=controller, target=self.target
                )
                self._watch.attach(self.client)

            def teardown(self):
                try:
                    self.client.close()
                except Exception:  # noqa: BLE001 — teardown never raises into the stopper
                    pass

        return lambda cfg: _G5PiBundle()

    def preflight_note(self) -> str:
        return "10 ms read-poll granularity (extension exposes no render callback)"


ROUTES = {"im-gtk": GtkRoute, "pi-ghostty": PiGhosttyRoute}


def preflight(route_name: str) -> str | None:
    """Blocked-outcome gate, run BEFORE any spawn (P1.M2.T1.S4): every missing
    binary or fixture is an honest BLOCKED result — never a mid-run crash.
    Returns the reason string, or None when the route may run."""
    route_cls = ROUTES[route_name]
    missing: list[str] = []
    for binname in ("sway", "xvfb-run"):
        if not shutil.which(binname):
            missing.append(binname)
    if not SYSTEM_PY:
        missing.append("python3")
    if route_cls.needs_pi:
        if not shutil.which("ghostty"):
            missing.append("ghostty")
        if not (os.environ.get("PI_BIN") or shutil.which("pi")):
            missing.append("pi (or set PI_BIN)")
    wavs = sorted(VOICE_DIR.glob("*.wav")) if VOICE_DIR.is_dir() else []
    if not wavs:
        missing.append(f"replay clips ({VOICE_DIR} has no *.wav)")
    else:
        unaligned = [
            p.name for p in wavs if not p.with_suffix(".words.json").exists()
        ]
        if unaligned:
            missing.append(
                "alignments for "
                + ", ".join(unaligned[:3])
                + (" …" if len(unaligned) > 3 else "")
            )
    if missing:
        return "missing: " + "; ".join(missing)
    return None


def build_inner_argv(
    folder: str, route_name: str, smoke: bool, partial_source: str | None
) -> list[str]:
    """The inner `run` invocation (extracted so the outer phase and its unit
    tests build the EXACT same argv). partial_source is the LAB-ONLY R.8 arm
    selector: the flag is present ONLY when set (omitted ⇒ the daemon seam
    keeps the production source; argparse never defaults it to a source)."""
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run",
        str(folder),
        "--route",
        route_name,
    ]
    if smoke:
        argv.append("--smoke")
    if partial_source:
        argv += ["--partial-source", partial_source]
    return argv


# --- private-session daemon -----------------------------------------------------


def build_cfg(smoke: bool) -> "object":
    from voice_typing.config import VoiceTypingConfig

    if smoke:
        # scaffold smoke: stream-edit + null backend (no bulk target needed);
        # still proves the feed seam, use_microphone=False child, control socket.
        # cancel.devices → nonexistent path: the evdev listener takes its
        # sanctioned log-once fallback (a lab NEVER reads real keyboards, R.7).
        # duck off: the ducker must never reach live MPRIS/PipeWire (R.7).
        return VoiceTypingConfig.from_toml(
            {
                "output": {"backend": "null"},
                "feedback": {"hypr_notify": False},
                "cancel": {"devices": ["/nonexistent/vt-g5-no-keyboard"]},
                "audio": {"duck_mode": "off"},
                "asr": {"auto_stop_idle_seconds": 0.0},
            }
        )
    # The measured path (Gotcha #10): precondition triple + inert surfaces.
    return VoiceTypingConfig.from_toml(
        {
            "output": {"delivery": "bulk-text", "backend": "null"},
            "feedback": {"hypr_notify": False},
            "cancel": {"devices": ["/nonexistent/vt-g5-no-keyboard"]},
            "audio": {"duck_mode": "off"},
            "asr": {
                "auto_stop_idle_seconds": 0.0,
                "auto_unload_idle_seconds": 0.0,
            },
        }
    )


def control_send(cmd: str, timeout: float = 30.0, extra: dict | None = None) -> dict:
    """ONE JSON line over the REAL private control socket (the voicectl surface).

    `timeout` is the TOTAL deadline (retries on transient connect/recv errors);
    per-recv socket timeout 10 s. `start` may legitimately block the reply for
    the whole cold model load (voicectl does the same) — pass a long timeout.
    """
    import socket as sk

    path = Path(os.environ["XDG_RUNTIME_DIR"]) / "voice-typing" / "control.sock"
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        s = sk.socket(sk.AF_UNIX, sk.SOCK_STREAM)
        s.settimeout(min(10.0, max(1.0, deadline - time.monotonic())))
        try:
            s.connect(str(path))
            s.sendall(
                (json.dumps({"cmd": cmd, **(extra or {})}) + "\n").encode("utf-8")
            )
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n")[0]
            if line:
                return json.loads(line)
        except (OSError, json.JSONDecodeError) as exc:
            last_err = exc
        finally:
            s.close()
        time.sleep(0.2)
    raise RuntimeError(f"control socket no reply for {cmd!r}: {last_err!r}")


def wait_listening(want: bool, timeout: float) -> bool:
    def ok():
        r = control_send("status", timeout=10)
        return r.get("listening") is want

    return until(ok, timeout, interval=0.2) is not None


def start_daemon(smoke: bool, factory, partial_source: str | None = None):
    """Feedback → VoiceTypingDaemon (in-process) → ControlServer → run thread.

    partial_source is S1's spawn-boundary selector; None is materialized to
    "stabilized" HERE (the daemon seam) — NEVER passed as None into the chain
    (S1's selector chain ValueErrors on None deep inside the child, where the
    failure would surface only after spawn)."""
    from voice_typing.daemon import ControlServer, LatencyLog, VoiceTypingDaemon
    from voice_typing.feedback import Feedback

    cfg = build_cfg(smoke)
    fb = Feedback(cfg.feedback)
    d = VoiceTypingDaemon(
        cfg,
        fb,
        latency=LatencyLog(),
        mic_prober=lambda: (True, None),  # hermetic: never probe live audio (R.7)
        bulk_target_factory=factory,
        feed_input=True,  # THE G5 seam (inert in production; lab-only here)
        partial_source=partial_source or "stabilized",
    )
    srv = ControlServer(d, on_quit=d.shutdown)
    srv.start()
    th = threading.Thread(target=d.run, daemon=True)
    th.start()
    return d, srv, th


def _resolve_partial_source(host, requested: str | None) -> str:
    """Fail-closed provenance (Gotcha #3): the ONLY ground truth for the
    effective source is host.partial_callback (the child's ready payload).
    Returns the selector name; raises BEFORE any measured replay when the
    child never reported ready, installed an unknown key, or installed
    anything other than what was requested — a mislabeled arm must never
    produce numbers."""
    from voice_typing.daemon import _PARTIAL_SOURCES

    installed = getattr(host, "partial_callback", "")
    if not installed:
        raise RuntimeError("recorder host never reported partial_callback (not ready?)")
    rev = {key: sel for sel, key in _PARTIAL_SOURCES.items()}
    effective = rev.get(installed)
    if effective is None:
        raise RuntimeError(
            f"unknown partial_callback {installed!r} installed in the spawn child"
        )
    if requested is not None and _PARTIAL_SOURCES.get(requested) != installed:
        raise RuntimeError(
            f"partial_source={requested!r} requested but {installed!r} installed — "
            "refusing to measure a mislabeled arm"
        )
    return effective


def wrap_ready(d, ready: collections.deque, lock: threading.Lock) -> None:
    """Wrap on_final/_on_partial with monotonic g5.ReadyEvent captures (the S3
    replay contract: stage="daemon" receipts; gen/utt via d._bulk_identity()
    INSIDE the reader-thread window — the snapshot is valid only there; seq
    read from d._bulk_seq AFTER the orig call, which assigns it on the bulk
    path). Identity/seq degrade to None via getattr + try/except: a stamping
    hiccup must NEVER crash the reader thread. Append-only observers (a list
    append is ns-scale and cannot perturb 50-100 ms budgets). MUST run BEFORE
    the first arm: _load_host reads self.on_final/_on_partial at spawn time,
    so the wrapped attributes are what the child relays to."""
    orig_final = d.on_final
    orig_partial = d._on_partial

    def _identity():
        try:
            ident = d._bulk_identity()
        except Exception:  # noqa: BLE001 — never crash the reader thread
            return None, None
        return (
            getattr(ident, "session_gen", None),
            getattr(ident, "utterance_id", None),
        )

    def _seq_after(gen, utt):
        try:
            seq_map = getattr(d, "_bulk_seq", {})
            return (
                seq_map.get((gen, utt))
                if gen is not None and utt is not None
                else None
            )
        except Exception:  # noqa: BLE001
            return None

    def wrapped_final(text, *a, **kw):
        gen, utt = _identity()
        try:
            return orig_final(text, *a, **kw)
        finally:
            seq = _seq_after(gen, utt)
            with lock:
                ready.append(
                    g5.ReadyEvent(
                        t=time.monotonic(), text=text, kind="final", stage="daemon",
                        gen=gen, utt=utt, seq=seq,
                    )
                )

    def wrapped_partial(text, *a, **kw):
        gen, utt = _identity()
        try:
            return orig_partial(text, *a, **kw)
        finally:
            seq = _seq_after(gen, utt)
            with lock:
                ready.append(
                    g5.ReadyEvent(
                        t=time.monotonic(), text=text, kind="partial", stage="daemon",
                        gen=gen, utt=utt, seq=seq,
                    )
                )

    d.on_final = wrapped_final
    d._on_partial = wrapped_partial


def _check_capture_bounds(ready: collections.deque, flog: "FieldLog") -> bool:
    """Truncation is evidence, not noise (Gotcha #6). Checked AFTER each
    replay window, BEFORE the record appends: a READY window at cap is
    unattributable → raise (honest harness fail); a FIELD log at cap is
    reportable → True (the record is flagged capped, never imputed)."""
    if ready.maxlen is not None and len(ready) >= ready.maxlen:
        raise RuntimeError(
            f"update-ready capture hit its cap ({ready.maxlen}) — window unattributable"
        )
    return flog.events.maxlen is not None and len(flog.events) >= flog.events.maxlen


def _build_record(
    route_name: str,
    clip_name: str,
    feed_start: float,
    words,
    field_events,
    win,
    anchor: int,
    *,
    partial_source: str,
    anchor_text: str,
    capped: bool,
    heartbeats,
) -> g5.ReplayRecord:
    """One measured replay (ReadyEvent attribute access; S3 provenance
    fields — partial_source/anchor_text/capped/heartbeats)."""
    return g5.ReplayRecord(
        route=route_name,
        clip=clip_name,
        feed_start=feed_start,
        words=words,
        field_events=field_events,
        update_ready=win,
        finals_ts=[e.t for e in win if e.kind == "final"],
        anchor=anchor,
        partial_source=partial_source,
        anchor_text=anchor_text,
        capped=capped,
        heartbeats=list(heartbeats),
    )


# --- the measured run -----------------------------------------------------------


def run_inner(
    root: Path, route_name: str, smoke: bool, partial_source: str | None = None
) -> int:
    """Inner phase (our own `run` invocation): disposable env, in-process
    daemon, warmup + measured replays. partial_source is the R.8 arm selector
    threaded from the CLI (None = the production source)."""
    if not (
        root == Path(os.environ["XDG_RUNTIME_DIR"])
        and root.name.startswith(PREFIX)
        and (smoke or os.environ.get("WLR_BACKENDS") == "x11")
    ):
        raise RuntimeError("Refusing to run outside the disposable environment")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    # Daemon INFO lines are the lab's only window into arm/load/bulk-lifecycle —
    # configure logging HERE (the in-process daemon never runs daemon.main()).
    import logging

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    lab = _Lab(root)
    route = None
    d = None
    srv = None
    hb = [(time.monotonic(), time.time())]
    try:
        Path(os.environ["XDG_RUNTIME_DIR"], "voice-typing").mkdir(
            parents=True, exist_ok=True
        )
        if not smoke:
            boot_sway(lab)
            route = ROUTES[route_name](lab)
            route.boot()
            # CUDA dirs for the recorder CHILD only — set AFTER the desktop is
            # up so sway/GTK never see them (see desktop_env NOTE).
            os.environ["LD_LIBRARY_PATH"] = (
                os.environ.get("LD_LIBRARY_PATH", "") + ":" + cuda_ld_library_path()
            ).strip(":")
        else:
            route = ROUTES[route_name](lab)
        d, srv, _th = start_daemon(
            smoke, route.bulk_target_factory() if route else None, partial_source
        )
        ready: collections.deque = collections.deque(maxlen=20000)
        rlock = threading.Lock()
        wrap_ready(d, ready, rlock)
        host_holder: dict = {}

        def wait_delivery_active(timeout: float = 150.0) -> bool:
            """Bulk-only gate: feed only inside an ACTIVE delivery lifetime
            (updates dispatched before acquire are dropped by the controller —
            by design). status is the REAL ctl surface."""

            def ok():
                r = control_send("status", timeout=10)
                return r.get("delivery_state") == "active"

            return until(ok, timeout, interval=0.25) is not None

        def delivery_state() -> str:
            r = control_send("status", timeout=10)
            return str(r.get("delivery_state", ""))

        def wait_delivery_state(state: str, timeout: float) -> bool:
            """Gate on the REAL ctl status surface.

            'active' before feeding (updates dispatched before acquire are
            dropped by the controller — by design); 'inactive' after stop —
            the stopper writes it AFTER bundle.teardown() completes, so it
            also proves the old IM child is FULLY dead before the next spawn
            (a racing rebind gets no text-input enable and never activates).
            """

            def ok():
                return delivery_state() == state

            return until(ok, timeout, interval=0.25) is not None

        def wait_delivery_gone(timeout: float) -> bool:
            """Any non-active delivery state — the stopper finished the teardown."""

            def ok():
                return delivery_state() != "active"

            return until(ok, timeout, interval=0.25) is not None

        def arm() -> bool:
            """Arm + wait for an ACTIVE bulk delivery lifetime, retrying on a
            warm daemon: the FIRST arm races the model load (its CPU spike can
            stall the field's GTK loop mid-activate-handshake); by attempt 2 the
            models are resident and activation is fast. All through the ctl."""
            for attempt in range(1, 4):
                # the reply waits out the whole cold model load (voicectl semantics)
                control_send("start", timeout=ARM_TIMEOUT_S)
                ok = wait_listening(True, 120)
                if ok and "host" not in host_holder:
                    host_holder["host"] = d._host
                if ok and not smoke:
                    ok = wait_delivery_state("active", 60.0)
                if ok:
                    return True
                log(
                    {
                        "stage": "arm-retry",
                        "attempt": attempt,
                        "delivery": delivery_state(),
                    }
                )
                control_send("stop", timeout=30)
                wait_delivery_gone(45)
            return False

        flog = route.field_log() if route else FieldLog(root / "no.log")
        clips = [
            (p.stem, load_pcm(p), g5.load_alignments(p.with_suffix(".words.json")))
            for p in sorted(VOICE_DIR.glob("*.wav"))
        ]
        if not clips:
            raise RuntimeError(
                "no aligned clips (run tests/g5_make_alignments.py first)"
            )

        host = None

        def feed_fn(pcm_slice, sr):
            host.feed(pcm_slice, sr)

        # ---- arm + WARMUP (models load here; ONE discarded replay, Gotcha #3)
        if not arm():
            try:
                status = control_send("status", timeout=10)
            except Exception as exc:  # noqa: BLE001
                status = {"error": repr(exc)}
            raise RuntimeError(f"daemon never armed; status={status}")
        host = host_holder.get("host") or d._host
        hb.append((time.monotonic(), time.time()))
        wname, wpcm, _w = clips[0]
        paced_feed(feed_fn, wpcm)
        until(lambda: any(e.kind == "final" for e in list(ready)), WARM_WAIT_S)
        with rlock:
            wkinds: dict = {}
            for e in list(ready):
                wkinds[e.kind] = wkinds.get(e.kind, 0) + 1
        flog.drain()  # discard warmup events entirely
        with rlock:
            ready.clear()
        hb.append((time.monotonic(), time.time()))
        # Fail-closed provenance (Gotcha #3): the child's ready payload is the
        # ONLY effective-source truth — refuse to measure a mislabeled arm.
        resolved_source = _resolve_partial_source(host, partial_source)
        log(
            {
                "stage": "warm",
                "clip": wname,
                "device": dict(getattr(host, "device", {})),
                "ready_kinds": wkinds,
                "partial_source_requested": partial_source or "default",
                "partial_callback_effective": getattr(host, "partial_callback", ""),
            }
        )

        if smoke:
            # scaffold smoke done: feed seam + models + control socket proven.
            log({"stage": "smoke", "pass": True, "route": route_name})
            return 0

        # ---- measured replays (fresh stop/start re-arm per replay)
        records: list[g5.ReplayRecord] = []
        ins = cor = 0
        misses = 0
        for rep in range(g5.REPLAY_BUDGET):
            control_send("stop", timeout=30)
            if not wait_listening(False, 30):
                raise RuntimeError("daemon never disarmed")
            # the stopper writes 'inactive' AFTER bundle.teardown() — the old IM
            # child is dead; spawning before that races the seat rebind.
            if not wait_delivery_gone(45):
                raise RuntimeError("bulk delivery never tore down")
            control_send("start", timeout=30)
            if not wait_listening(True, 60):
                raise RuntimeError("daemon never re-armed (warm)")
            if not wait_delivery_state("active", 150.0):
                raise RuntimeError("bulk delivery never re-armed")
            name, pcm, words = clips[rep % len(clips)]
            anchor = flog.anchor()
            flog.drain()  # events before feed_start are the anchor baseline
            anchor_text = flog.anchor_text()  # pre-replay field state (S3 seed)
            fs = paced_feed(feed_fn, pcm)

            # wait: ≥1 final after fs, then quiescence (no ready events for SETTLE_S)
            def got_final():
                with rlock:
                    return any(e.kind == "final" and e.t >= fs for e in list(ready))

            until(got_final, FINAL_TIMEOUT_S)

            def quiet():
                with rlock:
                    win_now = [e.t for e in list(ready) if e.t >= fs]
                return (not win_now) or (time.monotonic() - max(win_now)) >= SETTLE_S

            until(quiet, len(pcm) / SAMPLE_RATE + 30, interval=0.2)
            end_t = time.monotonic()
            evs = [e for e in flog.drain() if fs - 0.5 <= e.t <= end_t]
            with rlock:
                win = [e for e in list(ready) if fs - 0.5 <= e.t <= end_t]
            wk: dict = {}
            for e in win:
                wk[e.kind] = wk.get(e.kind, 0) + 1
            # Truncation is evidence (Gotcha #6): a ready-window at cap aborts
            # (unattributable); a field log at cap flags the record capped.
            capped = _check_capture_bounds(ready, flog)
            rec = _build_record(
                route_name,
                name,
                fs,
                words,
                evs,
                win,
                anchor,
                partial_source=resolved_source,
                anchor_text=anchor_text,
                capped=capped,
                heartbeats=hb,
            )
            records.append(rec)
            m = g5.aggregate(records, route=route_name)
            ins, cor, misses = m.insertions, m.corrections, m.misses
            log(
                {
                    "stage": "replay",
                    "n": rep + 1,
                    "clip": name,
                    "insertions": ins,
                    "corrections": cor,
                    "misses": misses,
                    "events": len(evs),
                    "updates": len(win),
                    "kinds": wk,
                }
            )
            if ins >= g5.MIN_COUNT and cor >= g5.MIN_COUNT:
                break

        hb.append((time.monotonic(), time.time()))
        metrics = g5.aggregate(records, route=route_name)
        # heartbeat: the FIELD's (mono, wall) pairs must agree pairwise (Gotcha #4)
        pairs = []
        try:
            with flog.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    r = json.loads(line)
                    pairs.append((float(r["t_mono"]), float(r["t_wall"])))
        except (OSError, json.JSONDecodeError, KeyError):
            pass
        hb_ok = g5.heartbeat_ok(pairs, tol_s=0.5) and g5.heartbeat_ok(hb, tol_s=0.5)
        artifact = {
            "route": route_name,
            "metrics": json.loads(g5.render_report_row(metrics)),
            "replays": [r.clip for r in records],
            "heartbeat_ok": hb_ok,
            "field_log_pair_count": len(pairs),
            "provenance": {
                "kernel": platform.release(),
                "python": sys.version.split()[0],
                "partial_source_requested": partial_source or "default",
                "partial_callback_effective": getattr(host, "partial_callback", ""),
                "device": dict(getattr(host, "device", {})),
                "warm": "resident (auto_unload_idle_seconds=0; one discarded warmup)",
                "clips": sorted(p.name for p in VOICE_DIR.glob("*.wav")),
                "route_note": route.preflight_note() if route else "",
                "field_instrument": "GTK field G5_FIELD_TIMING change log"
                if route_name == "im-gtk"
                else "pi editor 10 ms read-poll",
            },
        }
        (root / f"artifact-{route_name}.json").write_text(
            json.dumps(artifact, indent=2)
        )
        # The final metrics line carries the arm provenance too (counts only,
        # never transcript text — Gotcha #5).
        log(
            {
                **artifact["metrics"],
                "partial_source_requested": partial_source or "default",
                "partial_callback_effective": getattr(host, "partial_callback", ""),
            }
        )
        if not hb_ok:
            log(
                {
                    "stage": "heartbeat",
                    "pass": False,
                    "note": "mono/wall deltas disagree",
                }
            )
            return 1
        return 0 if metrics.verdict == "pass" else 1
    except Exception as e:  # noqa: BLE001 — one bad block still tears down honestly
        log({"stage": "harness", "pass": False, "route": route_name, "error": repr(e)})
        return 1
    finally:
        try:
            if d is not None:
                try:
                    control_send("quit", timeout=15)
                except Exception:  # noqa: BLE001
                    pass
                d.shutdown()
            if srv is not None:
                srv.stop()
        except Exception:  # noqa: BLE001
            pass
        if route is not None and hasattr(route, "_poll_stop"):
            route._poll_stop.set()
        lab.kill_all()  # killpg our OWN session groups — never a pattern sweep


# --- desktop_env / main (ime_g3_lab.py skeleton) ---------------------------------


def desktop_env(folder: str, needs_pi: bool) -> dict:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
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
        "HOME": folder,
        # torch/OMP thread caps: the recorder child's load spike would otherwise
        # spread across all cores and starve the desktop's GTK main loop during
        # the first arm (the IM activate handshake stalls — observed live).
        "OMP_NUM_THREADS": "4",
        "MKL_NUM_THREADS": "4",
    }
    if needs_pi:
        # THE DOCUMENTED HOME DELTA (pi_g3_row_lab.py): pi's node install +
        # ~/.pi are home-resident — HOME stays REAL; everything else isolated.
        env["HOME"] = os.environ.get("HOME") or str(Path.home())
        pi_bin = os.environ.get("PI_BIN") or shutil.which("pi") or ""
        env["PI_BIN"] = pi_bin
        env["PATH"] = (
            env["PATH"] + ":" + str(Path(pi_bin).parent) if pi_bin else env["PATH"]
        )
    for key in PROVENANCE_ENV_KEYS + (NO_DESKTOP_ENV,):
        if os.environ.get(key):
            env[key] = os.environ[key]
    # NOTE: NO CUDA LD_LIBRARY_PATH here. The compositor + the GTK field must
    # boot in the same clean env as the G3 labs (an earlier draft exported the
    # CUDA dirs chain-wide and the field's frame clock froze after one paint —
    # the IM activate handshake rides that clock and never landed). The recorder
    # CHILD is what needs the CUDA dirs; run_inner sets them on os.environ AFTER
    # the desktop is up, so the child inherits them at its spawn (the daemon
    # process itself stays CUDA-free — the recorder_host architecture).
    return env


def cuda_ld_library_path() -> str:
    """The asr-lab README recipe: cuBLAS/cuDNN lib dirs from the daemon venv."""
    import nvidia.cublas.lib as a
    import nvidia.cudnn.lib as b

    def _d(m):
        f = getattr(m, "__file__", None)
        return os.path.dirname(f) if f else next(iter(m.__path__))

    return _d(a) + ":" + _d(b)


def run_route(route_name: str, smoke: bool, partial_source: str | None = None) -> int:
    """Outer phase: preflight gate → xvfb-run -a + dbus-run-session → our own
    `run` invocation. A preflight miss is a BLOCKED outcome: one JSON line,
    exit 1, NOTHING spawned (the tmpdir context never even opens)."""
    needs_pi = ROUTES[route_name].needs_pi
    reason = preflight(route_name)
    if reason:
        log(
            {
                "stage": "preflight",
                "verdict": "blocked",
                "route": route_name,
                "reason": reason,
            }
        )
        return 1
    with tempfile.TemporaryDirectory(
        prefix=PREFIX, ignore_cleanup_errors=True
    ) as folder:
        root = Path(folder)
        bus = root / "private-bus.conf"
        bus.write_text(
            "<busconfig><type>session</type><listen>unix:tmpdir=" + folder + "</listen>"
            '<policy context="default"><allow send_destination="*"/><allow own="*"/>'
            '<allow receive_sender="*"/></policy></busconfig>'
        )
        argv = build_inner_argv(folder, route_name, smoke, partial_source)
        timeout_s = 240 if smoke else 1440
        try:
            if smoke:
                # no compositor at all: run in-place under the private runtime dir.
                # Scrub the real session bus: NOTHING in this lab may reach live
                # DBus services (MPRIS ducking, portals) — R.7 hygiene.
                env_delta = desktop_env(folder, False)
                for k in ("DBUS_SESSION_BUS_ADDRESS", "DBusActivatable"):
                    env_delta.pop(k, None)
                env_delta["DBUS_SESSION_BUS_ADDRESS"] = (
                    ""  # a lab must never find the live bus
                )
                os.environ.update(env_delta)
                # the recorder CHILD needs the CUDA dirs (desktop_env is clean)
                os.environ["LD_LIBRARY_PATH"] = (
                    os.environ.get("LD_LIBRARY_PATH", "") + ":" + cuda_ld_library_path()
                ).strip(":")
                os.environ["XDG_RUNTIME_DIR"] = folder
                Path(folder, "voice-typing").mkdir(parents=True, exist_ok=True)
                rc = run_inner(
                    root, route_name, smoke=True, partial_source=partial_source
                )  # type: ignore[arg-type]
            else:
                proc = sp.Popen(
                    [
                        "xvfb-run",
                        "-a",
                        "dbus-run-session",
                        f"--config-file={bus}",
                        "--",
                        *argv,
                    ],
                    env=desktop_env(folder, needs_pi),
                    cwd=str(REPO),
                    start_new_session=True,
                )
                try:
                    rc = proc.wait(timeout=timeout_s)
                except sp.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except sp.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
                    log({"stage": "harness", "pass": False, "error": "outer timeout"})
                    rc = 1
        finally:
            if os.environ.get("G5_KEEP_SCRATCH") == "1":
                log({"stage": "scratch-kept", "root": str(root)})
            else:
                for attempt in range(10):
                    try:
                        shutil.rmtree(root, ignore_errors=True)
                        break
                    except OSError:
                        time.sleep(0.5)
    return rc


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        # INNER run invocation (our own argv carries the tmpdir path)
        ap = argparse.ArgumentParser()
        ap.add_argument("run")
        ap.add_argument("root")
        ap.add_argument("--route", required=True, choices=sorted(ROUTES))
        ap.add_argument("--smoke", action="store_true")
        ap.add_argument(
            "--partial-source",
            choices=("plain", "stabilized"),
            default=None,
            help="lab-only R.8 arm selector; omit for the production source",
        )
        ns = ap.parse_args(sys.argv[1:])
        raise SystemExit(run_inner(Path(ns.root), ns.route, ns.smoke, ns.partial_source))
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", required=True, choices=sorted(ROUTES) + ["all"])
    ap.add_argument(
        "--partial-source",
        choices=("plain", "stabilized"),
        default=None,
        help="lab-only R.8 arm selector; omit for the production source",
    )
    ns = ap.parse_args()
    if os.environ.get(GATE_ENV) != "1":
        log({"gate": GATE_ENV, "pass": None, "note": f"skipped (set {GATE_ENV}=1)"})
        return
    smoke = os.environ.get(NO_DESKTOP_ENV) == "1"
    routes = sorted(ROUTES) if ns.route == "all" else [ns.route]
    results = {}
    for r in routes:
        if smoke:
            log({"stage": "smoke-start", "route": r})
        results[r] = run_route(r, smoke, ns.partial_source)
    if any(rc not in (0,) for rc in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
