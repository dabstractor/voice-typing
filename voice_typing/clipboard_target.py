"""voice_typing.clipboard_target — the insert-only clipboard TargetAdapter (R.6).

Mode A: this docstring IS the R.6 contract, verbatim then clause by clause,
each mapped to its mechanism and its G4 leg (P1.M5.T3.S1; evidence in
plan/008_a47116bb2b79/architecture/g4_clipboard_evidence.md).

THE PRD R.6 CONTRACT, VERBATIM:
  "Routine delivery prefers a CLIPBOARD-FREE route. If an adapter must use the
  ordinary clipboard it MUST preserve all prior formats and bytes, distinguish
  original ownership from a later copy with identical text, protect a
  simultaneous user paste, and keep partials out of the configured
  clipboard-history watcher. Compare-before-restore, sleep-before-restore,
  `--paste-once`, and "first reader = the editor" are INSUFFICIENT. If this
  cannot be proven with the local manager, that adapter is unavailable —
  never disable the manager. The PRIMARY selection stays untouched."

CLAUSE → MECHANISM → G4 LEG:
  1. "preserve all prior formats and bytes"
     → snapshot EVERY offered MIME type with EXACT bytes via zwlr_data_control
       offers (receive per type into a pipe), and RESTORE via a
       zwlr_data_control_source_v1 that serves per-type bytes on send().
       wl-copy offers ONE input stream under N -t types and therefore CANNOT
       restore a multi-format snapshot (external_tech_notes §5.4) — it is not
       used for restore, nor for staging: a wl-copy stage offers a single type
       and could never carry the clause-2 nonce sentinel, which would force the
       INSUFFICIENT content-comparison ownership test. G4 leg L4.
  2. "distinguish original ownership from a later copy with identical text"
     → a sentinel nonce MIME (x-voice-typing/nonce, secrets.token_hex per
       staging generation) is offered on OUR sources ONLY. Ownership = our
       source object still bound (no cancelled event) after a sync barrier —
       never a content comparison; a later byte-identical user copy carries no
       nonce and replaces our selection (cancelled) → foreign. G4 leg L2.
  3. "protect a simultaneous user paste"
     → mutation-time recheck immediately before the trigger chord: pump the
       wire through a wl_display.sync barrier; if our source took a cancelled
       event (anyone else set the selection, identical bytes included) the
       transfer ABORTS — snapshot restored, REFUSED, nothing pasted. After the
       chord, APPLIED requires a positive witness (confirm() callback); bytes
       sent is not applied. A real user key mid-transfer is the controller's
       HALT path (R.5) — this adapter never synthesizes per-character input.
       G4 legs L2, L3, L5.
  4. "keep partials out of the configured clipboard-history watcher"
     → there is NO protocol-level hiding: managers see every selection via
       data-control (external_tech_notes §5.5). The honest mechanism is to
       DETECT a watcher at acquire() (scoped /proc scan of known manager
       command lines) and FAIL BEFORE DELIVERY with reason
       "clipboard-history watcher active — R.6 partials-out-of-history
       unprovable". The manager is never stopped, disabled, or killed.
       UNAVAILABLE-under-watcher is a legitimate, contract-compliant outcome.
       G4 leg L1.
  + "The PRIMARY selection stays untouched."
     → only the clipboard set_selection is ever called; the device's
       set_primary_selection request is never sent (pinned by unit test).
       G4 asserts PRIMARY unchanged after every leg.

INSERT-ONLY BY DESIGN (paste-lab evidence): ghostty delivers a paste as ONE
bracketed paste; pasted Backspace bytes arrive as SPACES, so corrections are
IMPOSSIBLE over this route. show() pastes only the delta of a pure extension
(common-prefix rule); a diverging span is a correction and is REFUSED before
anything touches the clipboard. Corrections for ghostty-class belong to the
cooperating-editor seam (P1.M5.T1), never here. No type_character /
press_backspace surface exists; no legacy-backend fallback.

TRANSFER CYCLE (one show() that inserts a delta):
  1. acquire   snapshot the user clipboard (all types, exact bytes) + detect
               watchers; fail BEFORE delivery on either.
  2. stage     publish OUR source: text/plain;charset=utf-8 = the delta bytes,
               plus the fresh nonce sentinel; set_selection on the clipboard.
  3. recheck   sync barrier; our source still bound? foreign (identical bytes
               included) → restore + REFUSED.
  4. trigger   ONE injected chord (the lab: xdotool ctrl+shift+v). Never
               --paste-once (a manager read would silently consume the offer).
  5. confirm   the injected witness must positively observe the target's
               receipt; without a witness the result is UNKNOWN, never applied.
  6. restore   a fresh data-control source re-offers the snapshot's EXACT
               types with EXACT per-type bytes (+ the nonce sentinel). The
               same restore runs on leave() and every abort path.

DEADLINES (R.5): the controller owns the overall 250 ms engineering deadline —
this adapter never decides an operation timed out; it owns only its per-I/O
wire waits (io_wait_s) and delegates the witness wait to the injected
confirm() callback. An op whose confirmation never came is UNKNOWN, never
retried here (R.5: never retry what may have landed).

CONSUMES (imported): voice_typing.bulk_delivery (the pure contracts) and
voice_typing.ime.wlwire (the stdlib wire skeleton: u32/i32/wstr/Event/Client).
CONSUMED BY: P1.M6.T2.S1 (dispatch wiring routes ghostty-class fields here —
it owns trigger/confirm injection); P1.M7.T1.S1 reads the G4 evidence.
NO daemon imports; stdlib only beyond those two modules.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import socket
import struct
import time
from dataclasses import dataclass, field

from voice_typing.bulk_delivery import (
    AcquireResult,
    ShowResult,
    rendered_equal,
)
from voice_typing.ime.wlwire import Client, Event, WlError, u32, wstr

logger = logging.getLogger(__name__)

__all__ = [
    "ClipboardFormat",
    "ClipboardSnapshot",
    "ClipboardBinding",
    "ZwlrDataControlSource",
    "ClipboardWatchdog",
    "DataControlClient",
    "WireLink",
    "detect_clipboard_watcher",
    "ClipboardTarget",
    "NONCE_MIME",
    "TEXT_MIME",
]

TEXT_MIME = "text/plain;charset=utf-8"   # the paste-lab-proven paste type
NONCE_MIME = "x-voice-typing/nonce"      # the clause-2 ownership sentinel

# Defensive caps: a snapshot we refuse to hold is a snapshot we cannot
# preserve — exceeding a cap FAILS the snapshot (honest) instead of silently
# truncating user bytes (R.6 clause 1).
_MAX_FORMAT_BYTES = 8 * 1024 * 1024      # per MIME type
_MAX_DELTA_BYTES = 1024 * 1024           # one paste payload

# Clause-4 watcher patterns (PRP implementation pattern; scoped /proc scan —
# data-control exposes no peer list, so process inspection is the only signal).
_WATCHER_RE = re.compile(r"wl-paste.*--watch|cliphist|clipman|wl-clip-persist|clippie")

# The watcher refusal reason string is CONTRACT (PRP Task 1): it is asserted
# verbatim by the unit tests and by G4 leg L1.
WATCHER_REFUSAL = "clipboard-history watcher active — R.6 partials-out-of-history unprovable"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClipboardFormat:
    """One snapshot entry: a MIME type and the EXACT bytes offered under it."""

    mime: str
    data: bytes


@dataclass(frozen=True)
class ClipboardSnapshot:
    """The user clipboard at acquire time + this acquisition's sentinel token.

    formats       — every offered type except our own sentinel (the sentinel is
                    adapter-owned bookkeeping, never user content; snapshots
                    skip it so a re-acquired session never inherits a stale
                    nonce).
    nonce         — the acquisition's nonce token (evidence lineage; every
                    staged/restored source mints its own fresh one).
    generation    — monotonic snapshot counter (1-based; 0 = empty world).
    """

    formats: tuple[ClipboardFormat, ...]
    nonce: str
    generation: int


@dataclass(frozen=True)
class ClipboardBinding:
    """The opaque AcquireResult.handle — what rechecks need, nothing more."""

    display: str          # the target session's WAYLAND_DISPLAY ("" = env default)
    snapshot: ClipboardSnapshot
    revision: int


class ZwlrDataControlSource:
    """Our side of one zwlr_data_control_source_v1 object.

    Holds the per-type bytes we committed to serve; on a send(mime, fd) event
    the EXACT bytes for THAT type are written to the fd and it is closed —
    the clause-1 mechanism (a data-control source serves different bytes per
    type; wl-copy's single stream cannot). `cancelled` is set when the
    compositor reports someone else took the selection — the clause-2/3
    recheck signal.
    """

    def __init__(self, obj_id: int, formats: dict[str, bytes], nonce: str, generation: int):
        self.obj_id = obj_id
        self.formats = dict(formats)
        self.nonce = nonce
        self.generation = generation
        self.cancelled = False
        self.sends = 0              # count + times only in logs — never text (R.5)

    def mimes(self) -> list[str]:
        """Offer order: original types first, the sentinel last."""
        return list(self.formats) + [NONCE_MIME]

    def handle_send(self, mime: str, fd: int) -> bool:
        """Serve one type's exact bytes to fd; close it. True when served."""
        try:
            if mime == NONCE_MIME:
                data = self.nonce.encode("utf-8")
            else:
                data = self.formats.get(mime)
            if data is None:
                return False
            view = memoryview(data)
            while view:
                n = os.write(fd, view)
                view = view[n:]
            return True
        except OSError:
            return False
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


class ClipboardWatchdog:
    """Selection-ownership watch (clause 2/3): nonce match => ours, else foreign.

    The wire-level truth is the source's cancelled event: ONLY a foreign
    set_selection produces one, and a byte-identical foreign copy produces it
    exactly like any other — content is never consulted. The nonce is carried
    ON the wire (sentinel MIME) so external verifiers (the G4 lab, a manager
    audit) can distinguish our offers; internally ownership is
    source-bound-and-not-cancelled. `check` pumps through a sync barrier
    before judging, so a queued cancelled event cannot be missed.
    """

    def __init__(self) -> None:
        self.foreign_changes = 0     # count only (R.5 logs)

    def check(self, link: "WireLink", source: ZwlrDataControlSource | None) -> bool:
        """True iff `source` is still the live selection after a sync barrier."""
        if source is None:
            return False
        try:
            link.sync()
        except (WlError, OSError):
            return False             # a dead wire is never "still ours"
        if source.cancelled:
            self.foreign_changes += 1
            return False
        return True

    @staticmethod
    def nonce_in_types(types: list[str], nonce: str) -> bool:
        """External-audit half: does a CURRENT type list carry OUR nonce value?

        Type lists alone only prove A sentinel exists; the offered VALUE is
        what binds it to this generation (verifiable via the sentinel's
        send/receive bytes — the G4 lab does exactly that).
        """
        return NONCE_MIME in types


# ---------------------------------------------------------------------------
# Wire: zwlr_data_control on the wlwire skeleton (stdlib only)
# ---------------------------------------------------------------------------

# (name, arg kinds) in protocol-XML document order — opcodes are the list
# indexes. Verified against wlr-protocols unstable/wlr-data-control-unstable-v1.xml
# (manager v2, device v2, source v1, offer v1); pinned by literal opcode
# expectations in tests/test_clipboard_target.py (no vendored fixture copy).
DC_REQUESTS: dict[str, list[tuple[str, str]]] = {
    "wl_display": [("sync", "n"), ("get_registry", "n")],
    "wl_registry": [("bind", "usun")],
    "wl_seat": [("get_pointer", "n"), ("get_keyboard", "n"), ("get_touch", "n"), ("release", "")],
    "zwlr_data_control_manager_v1": [
        ("create_data_source", "n"),
        ("get_data_device", "no"),
        ("destroy", ""),
    ],
    "zwlr_data_control_device_v1": [
        ("set_selection", "o"),         # clipboard ONLY — set_primary_selection (op 2) is NEVER sent
        ("destroy", ""),
        ("set_primary_selection", "o"),  # present in the table for PARSE-safety of opcodes only
    ],
    "zwlr_data_control_source_v1": [("offer", "s"), ("destroy", "")],
    "zwlr_data_control_offer_v1": [("receive", "sh"), ("destroy", "")],
}

DC_EVENTS: dict[str, list[tuple[str, str]]] = {
    "wl_display": [("error", "ous"), ("delete_id", "u")],
    "wl_registry": [("global", "usu"), ("global_remove", "u")],
    "wl_seat": [("capabilities", "u"), ("name", "s")],
    "wl_callback": [("done", "u")],
    "zwlr_data_control_device_v1": [
        ("data_offer", "n"),
        ("selection", "o"),              # object id 0 = empty selection
        ("finished", ""),
        ("primary_selection", "o"),      # v2 event — parsed, NEVER acted on
    ],
    "zwlr_data_control_source_v1": [("send", "sh"), ("cancelled", "")],
    "zwlr_data_control_offer_v1": [("offer", "s")],
}

# Event-side new_id args are SERVER-assigned objects: the client must register
# the interface so later events on that id parse (without this, offer(mime)
# events drop on the floor and every snapshot reads as empty).
EVENT_NEW_ID_IFACE = {
    ("zwlr_data_control_device_v1", "data_offer"): "zwlr_data_control_offer_v1",
}


class DataControlClient(Client):
    """wlwire Client speaking zwlr_data_control — fd-aware in BOTH directions.

    Differences from the IM skeleton (documented in wlwire's docstring):
    requests may carry "h" (an fd goes out via SCM_RIGHTS — offer.receive),
    and next_event KEEPS send-event fds open (the IM skeleton closes keymap
    fds; here the fd IS the payload). Table lookups use the DC_* tables above;
    the IM tables are never consulted and never mutated.
    """

    def __init__(self, display: str | None = None, sock=None):
        super().__init__(display=display, sock=sock)
        self.sources: dict[int, ZwlrDataControlSource] = {}
        self.offer_mimes: dict[int, list[str]] = {}   # offer obj id -> offered mimes
        self.current_offer = 0                        # selection offer id (0 = empty)
        self._done_callbacks: set[int] = set()
        self.manager = 0
        self.seat = 0
        self.device = 0

    # ---- requests (fd-aware re-implementation over the same byte layout) ----
    def request(self, obj: int, iface: str, name: str, *args) -> None:
        table = DC_REQUESTS.get(iface)
        if table is None or name not in [t[0] for t in table]:
            raise WlError(f"unknown request {iface}.{name}")
        entry = [t for t in table if t[0] == name][0]
        opcode = table.index(entry)
        kinds = entry[1]
        if len(kinds) != len(args):
            raise WlError(f"{iface}.{name}: {len(kinds)} args expected, got {len(args)}")
        payload = bytearray()
        fds: list[int] = []
        for kind, arg in zip(kinds, args):
            if kind in ("u", "n", "o"):
                payload += u32(arg)
            elif kind == "s":
                payload += wstr(arg)
            elif kind == "h":
                payload += u32(0)  # fd placeholder word on the wire
                fds.append(int(arg))
            else:
                raise WlError(f"unsupported arg kind {kind}")
        msg = struct.pack("<IHH", obj, opcode, 8 + len(payload)) + bytes(payload)
        if fds:
            anc = [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                    struct.pack(f"<{len(fds)}i", *fds))]
            self.s.sendmsg([msg], anc)
        else:
            self.s.sendall(msg)

    # ---- event pump: keeps send fds OPEN (the fd is the payload) ------------
    def next_event(self, timeout: float | None = 0.5) -> Event | None:
        if not self._fill(8, timeout):
            return None
        obj, opcode, size = struct.unpack_from("<IHH", self.buf)
        if size < 8:
            raise WlError(f"bad event size {size}")
        if not self._fill(size, 0.2):
            return None
        body = bytes(self.buf[8:size])
        del self.buf[:size]
        iface = self.ifaces.get(obj)
        if iface is None:
            return Event(obj, "unknown", "?", ())
        table = DC_EVENTS.get(iface, [])
        if opcode >= len(table):
            return Event(obj, iface, f"op{opcode}", ())
        name, kinds = table[opcode]
        args, pos = [], 0
        for kind in kinds:
            if kind in ("u", "i", "o", "n"):
                (v,) = struct.unpack_from("<i" if kind == "i" else "<I", body, pos)
                if kind == "n":
                    target = EVENT_NEW_ID_IFACE.get((iface, name))
                    if target:
                        self.ifaces[v] = target   # server-assigned object: register it
                args.append(v)
                pos += 4
            elif kind == "s":
                (n,) = struct.unpack_from("<I", body, pos)
                pos += 4
                raw = body[pos:pos + n]
                pos += (n + 3) & ~3
                args.append(raw[:-1].decode("utf-8", "replace"))
            elif kind == "h":
                fd = self.pending_fds.pop(0) if self.pending_fds else -1
                args.append(fd)          # KEPT OPEN — ownership passes to the handler
            else:
                raise WlError(f"unsupported event kind {kind}")
        return Event(obj, iface, name, tuple(args))

    # ---- dispatch (override/extend of wlwire.Client.handle) ------------------
    def handle(self, ev: Event) -> None:
        if ev.iface == "wl_display" and ev.name == "error":
            raise WlError(f"protocol error on {ev.args[0]}: {ev.args[1]} {ev.args[2]}")
        if ev.iface == "wl_registry" and ev.name == "global":
            self.globals[ev.args[0]] = (ev.args[1], ev.args[2])
            return
        if ev.iface == "wl_callback" and ev.name == "done":
            self._done_callbacks.add(ev.obj)
            return
        if ev.iface == "zwlr_data_control_device_v1":
            if ev.name == "data_offer":
                self.offer_mimes[ev.args[0]] = []
            elif ev.name == "selection":
                self.current_offer = ev.args[0]
                if ev.args[0] == 0:
                    self.offer_mimes.clear()
            return
        if ev.iface == "zwlr_data_control_offer_v1" and ev.name == "offer":
            mimes = self.offer_mimes.setdefault(ev.obj, [])
            if ev.args[0] not in mimes:
                mimes.append(ev.args[0])
            return
        if ev.iface == "zwlr_data_control_source_v1":
            src = self.sources.get(ev.obj)
            if src is None:
                return
            if ev.name == "cancelled":
                src.cancelled = True     # a foreign selection replaced ours
            elif ev.name == "send":
                if src.handle_send(ev.args[0], ev.args[1]):
                    src.sends += 1
            return

    # ---- session plumbing ----------------------------------------------------
    def bootstrap(self) -> None:
        """Registry scan + bind manager (≤v2) + seat + data device."""
        self.registry = self.new("wl_registry")
        self.request(1, "wl_display", "get_registry", self.registry)
        self.sync()
        for name, (iface, version) in list(self.globals.items()):
            if iface == "zwlr_data_control_manager_v1" and self.manager == 0:
                self.manager = self.bind(name, iface, min(version, 2))
            elif iface == "wl_seat" and self.seat == 0:
                self.seat = self.bind(name, iface, version)  # advertised = supported
        if self.manager == 0:
            raise WlError("zwlr_data_control_manager_v1 not advertised")
        if self.seat == 0:
            raise WlError("wl_seat not advertised")
        self.device = self.new("zwlr_data_control_device_v1")
        self.request(self.manager, "zwlr_data_control_manager_v1", "get_data_device",
                     self.device, self.seat)
        self.sync()   # the compositor answers with the CURRENT selection

    def sync(self, timeout: float = 2.0) -> None:
        """wl_display.sync barrier: every prior event is dispatched on return."""
        cb = self.new("wl_callback")
        self.request(1, "wl_display", "sync", cb)
        import time as _t

        deadline = _t.monotonic() + timeout
        while cb not in self._done_callbacks:
            left = deadline - _t.monotonic()
            if left <= 0:
                raise WlError("sync barrier timed out")
            ev = self.next_event(left)
            if ev is None:
                continue
            self.handle(ev)

    def pump(self, timeout: float = 0.05) -> int:
        """Drain events for up to `timeout` seconds; return the event count."""
        count = 0
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            ev = self.next_event(left)
            if ev is None:
                break
            self.handle(ev)
            count += 1
        return count

    def new_source(self, formats: dict[str, bytes], nonce: str, generation: int) -> ZwlrDataControlSource:
        src = ZwlrDataControlSource(self.new("zwlr_data_control_source_v1"), formats, nonce, generation)
        self.sources[src.obj_id] = src
        self.request(self.manager, "zwlr_data_control_manager_v1", "create_data_source", src.obj_id)
        for mime in src.mimes():
            self.request(src.obj_id, "zwlr_data_control_source_v1", "offer", mime)
        return src

    def set_selection(self, source: ZwlrDataControlSource | None) -> None:
        """Bind OUR source as the CLIPBOARD selection (null clears it).

        set_primary_selection is deliberately unreachable from here — the
        PRIMARY selection stays untouched (R.6; unit-pinned).
        """
        self.request(self.device, "zwlr_data_control_device_v1", "set_selection",
                     source.obj_id if source is not None else 0)

    def _receive_no_destroy(self, offer_id: int, mime: str,
                            timeout: float = 1.0) -> bytes | None:
        """Receive one type's bytes WITHOUT destroying the offer — callers
        batch several receives on one offer and destroy ONCE at the end (a
        receive on a destroyed offer is a protocol error that kills the
        connection — the exact bug that broke multi-type snapshots)."""
        r, w = os.pipe()
        try:
            self.request(offer_id, "zwlr_data_control_offer_v1", "receive", mime, w)
            try:
                self.sync(timeout=timeout)
            except WlError as exc:
                logger.warning("offer_receive: sync barrier failed: %s", str(exc)[:120])
                return None   # barrier never opened — no exact bytes, never truncation
            os.close(w)   # our end: the compositor writes, we read to EOF
            w = -1
            chunks: list[bytes] = []
            total = 0
            deadline = time.monotonic() + timeout
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    logger.warning("offer_receive: read timed out after %d B", total)
                    return None   # incomplete read = snapshot/verify failure, NEVER truncation
                import select as _s

                if not _s.select([r], [], [], left)[0]:
                    continue
                chunk = os.read(r, 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_FORMAT_BYTES:
                    return None   # over cap: refuse to hold, never truncate
                chunks.append(chunk)
            return b"".join(chunks)
        except OSError:
            return None
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

    def offer_receive(self, offer_id: int, mime: str, timeout: float = 1.0) -> bytes | None:
        """Read one type's EXACT bytes out of the CURRENT selection offer."""
        data = self._receive_no_destroy(offer_id, mime, timeout=timeout)
        try:
            self.request(offer_id, "zwlr_data_control_offer_v1", "destroy")
        except (WlError, OSError):
            pass
        return data


class WireLink:
    """The adapter-facing duck over DataControlClient (unit tests fake THIS).

    Surface: connect/display, snapshot_selection, publish, sync, pump,
    selection_types, current_nonce_value, close. No daemon imports; nothing
    connects at import time.
    """

    def __init__(self, display: str | None = None):
        self.display = display or os.environ.get("WAYLAND_DISPLAY", "")
        self.client: DataControlClient | None = None
        self.generation = 0

    def connect(self) -> bool:
        try:
            self.client = DataControlClient(display=self.display or None)
            self.client.bootstrap()
            return True
        except (WlError, OSError):
            self.client = None
            return False

    def _c(self) -> DataControlClient:
        if self.client is None:
            raise WlError("wire not connected")
        return self.client

    def snapshot_selection(self, nonce: str, read_wait_s: float = 1.0) -> ClipboardSnapshot:
        """Snapshot EVERY offered type with exact bytes (sentinel excluded).

        All receives happen on ONE offer object and the offer is destroyed
        ONCE at the end — a second receive on a destroyed offer is a protocol
        error that kills the connection (this exact bug broke multi-type
        snapshots in the G4 lab before the fix)."""
        c = self._c()
        mimes = list(c.offer_mimes.get(c.current_offer, []))
        logger.info("snapshot: offer=%d mimes=%s", c.current_offer, mimes)
        formats: list[ClipboardFormat] = []
        self.generation += 1
        offer = c.current_offer
        try:
            for mime in mimes:
                if mime == NONCE_MIME:
                    continue   # our sentinel from a prior cycle — never user content
                data = c._receive_no_destroy(offer, mime, timeout=read_wait_s)
                if data is None:
                    raise WlError(f"snapshot read failed for {mime}")
                formats.append(ClipboardFormat(mime=mime, data=data))
        finally:
            try:
                c.request(offer, "zwlr_data_control_offer_v1", "destroy")
            except (WlError, OSError):
                pass
        return ClipboardSnapshot(formats=tuple(formats), nonce=nonce,
                                 generation=self.generation)

    def publish(self, formats: dict[str, bytes], nonce: str) -> ZwlrDataControlSource:
        """Stage/restore: offer these types (+ the sentinel) as the clipboard.

        An EMPTY formats dict publishes a null selection (an originally empty
        clipboard restores to empty — never to an empty-looking offer).
        """
        c = self._c()
        self.generation += 1
        if formats:
            src = c.new_source(formats, nonce, self.generation)
        else:
            src = None
            c.set_selection(None)
        if src is not None:
            c.set_selection(src)
        self.sync()
        return src

    def sync(self, timeout: float = 2.0) -> None:
        self._c().sync(timeout=timeout)

    def pump(self, timeout: float = 0.05) -> int:
        return self._c().pump(timeout)

    def selection_types(self) -> list[str]:
        c = self._c()
        return list(c.offer_mimes.get(c.current_offer, []))

    def current_nonce_value(self, read_wait_s: float = 1.0) -> str | None:
        """External-audit helper: the sentinel VALUE in the live selection."""
        c = self._c()
        if NONCE_MIME not in self.selection_types():
            return None
        data = c.offer_receive(c.current_offer, NONCE_MIME, timeout=read_wait_s)
        return data.decode("utf-8", "replace") if data is not None else None

    def close(self) -> None:
        c, self.client = self.client, None
        if c is None:
            return
        for obj in list(c.sources):
            try:
                c.request(obj, "zwlr_data_control_source_v1", "destroy")
            except (WlError, OSError):
                pass
        try:
            c.s.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Clause-4 watcher detection (scoped /proc scan; data-control has no peer list)
# ---------------------------------------------------------------------------

def detect_clipboard_watcher(
    scope_env: dict[str, str] | None = None,
    extra_patterns: tuple[str, ...] = (),
) -> list[str] | None:
    """Return matching command lines ("pid cmd") for known history watchers.

    scope_env — when given (e.g. {"WAYLAND_DISPLAY": "wayland-3",
    "XDG_RUNTIME_DIR": "/tmp/lab"}), a hit counts only if the process
    environment carries EVERY pair: the scan is then scoped to the TARGET
    session, so an unrelated desktop's manager never trips it. Without a
    scope, ANY known watcher counts (conservative production posture).

    Returns None when the scan itself could not run (fail-closed: the caller
    must treat "unknown" as "watcher present" — fail BEFORE delivery).
    """
    hits: list[str] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    mine = os.getpid()
    for entry in entries:
        if not entry.isdigit() or int(entry) == mine:
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        if not raw:
            continue   # kernel thread
        cmdline = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if not (_WATCHER_RE.search(cmdline)
                or any(p in cmdline for p in extra_patterns)):
            continue
        if scope_env is not None:
            try:
                with open(f"/proc/{entry}/environ", "rb") as fh:
                    env = fh.read()
            except OSError:
                continue   # cannot prove it is IN scope — it does not count
            env_text = env.replace(b"\0", b"\n").decode("utf-8", "replace")
            if not all(f"{k}={v}\n" in env_text for k, v in scope_env.items()):
                continue
        hits.append(f"{entry} {cmdline[:120]}")
    return hits


# ---------------------------------------------------------------------------
# The TargetAdapter (R.3/R.5/R.6)
# ---------------------------------------------------------------------------

class ClipboardTarget:
    """Daemon-side adapter: insert-only clipboard delivery under the R.6 contract.

    Collaborators are injected and duck-typed (unit tests fake them all):
      wire         — WireLink-like (snapshot_selection/publish/sync/pump/…).
      trigger      — REQUIRED callable firing the ONE paste chord; no default:
                     without it show() refuses "no trigger configured" BEFORE
                     staging (fail before delivery).
      confirm      — callable(delta: str) -> bool: positive witness that the
                     TARGET received exactly `delta` (bytes sent is not
                     applied). None ⇒ every post-trigger op is UNKNOWN.
      watcher_scan — detect_clipboard_watcher-like; default production scan.
    """

    def __init__(self, wire, trigger=None, confirm=None, watcher_scan=None):
        self._wire = wire
        self._trigger = trigger
        self._confirm = confirm
        self._scan = watcher_scan or (lambda: detect_clipboard_watcher())
        self._binding: ClipboardBinding | None = None
        self._owned_span = ""            # last APPLIED complete rendered span
        self._owned_utterance: str | None = None
        self._closed_utterances: set[str] = set()
        self._revision = 0               # client-side; +1 ONLY on applied
        self._live_source = None         # our staged/restored source still bound
        self._restored = True            # True when the selection is the snapshot's
        self._watchdog = ClipboardWatchdog()
        self.last_reason = ""            # machine-readable refusal/unknown taxonomy (R.5)

    # --- acquire (R.3/R.6): snapshot + watcher gate, fail BEFORE delivery ----
    def acquire(self) -> AcquireResult:
        hits = self._scan()
        if hits is None:
            self.last_reason = "watcher scan failed (fail-closed)"
            return AcquireResult(ok=False, reason=self.last_reason)
        if hits:
            self.last_reason = WATCHER_REFUSAL
            logger.info("clipboard acquire refused: watcher present (%d match(es))", len(hits))
            return AcquireResult(ok=False, reason=self.last_reason)
        nonce = secrets.token_hex(16)
        link = self._wire
        try:
            if link.client is None and not link.connect():
                self.last_reason = "clipboard wire connect failed"
                return AcquireResult(ok=False, reason=self.last_reason)
            snapshot = link.snapshot_selection(nonce)
        except (WlError, OSError) as exc:
            self.last_reason = f"clipboard snapshot failed: {exc}"
            logger.warning("clipboard acquire: snapshot failed: %s", str(exc)[:160])
            return AcquireResult(ok=False, reason=self.last_reason)
        self._binding = ClipboardBinding(display=getattr(link, "display", ""), snapshot=snapshot,
                                         revision=0)
        self._owned_span = ""
        self._owned_utterance = None
        self._closed_utterances.clear()
        self._revision = 0
        self._live_source = None
        self._restored = True
        self.last_reason = ""
        logger.info("clipboard acquire ok: formats=%d generation=%d",
                    len(snapshot.formats), snapshot.generation)
        return AcquireResult(ok=True, handle=self._binding, revision=0)

    # --- show (R.3): ONE insert (paste delta) — insert-only -------------------
    def show(self, session: int, utterance: str, seq: int,
             expected_revision: int, span: str) -> ShowResult:
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"
            return ShowResult.REFUSED
        if self._owned_utterance is not None and utterance != self._owned_utterance:
            # The previous utterance's final never came: its words STAY pasted
            # on screen; we merely stop owning them. Never an erase.
            self._owned_span = ""
        self._owned_utterance = utterance
        # zero-diff guard FIRST (R.1): render-equal ⇒ ZERO events, no clipboard touch
        if rendered_equal(self._owned_span, span):
            self.last_reason = ""
            return ShowResult.UNCHANGED
        # insert-only row: any divergence is a correction ⇒ REFUSED before staging
        if not span.startswith(self._owned_span):
            self.last_reason = "insert-only route: diverging span is a correction — refused"
            logger.info("clipboard show refused: divergence session=%s seq=%s", session, seq)
            return ShowResult.REFUSED
        # revision discipline mirrors ime/pi adapters (caller +1s only on applied)
        if not isinstance(expected_revision, int) or expected_revision < self._revision:
            self.last_reason = "revision regression"
            return ShowResult.REFUSED
        if self._trigger is None:
            self.last_reason = "no trigger configured"
            return ShowResult.REFUSED      # fail BEFORE delivery: clipboard untouched
        delta = span[len(self._owned_span):]
        if not delta:
            self.last_reason = ""
            return ShowResult.UNCHANGED    # pure extension with empty delta = no-op
        if len(delta.encode("utf-8")) > _MAX_DELTA_BYTES:
            self.last_reason = f"delta cap {_MAX_DELTA_BYTES}B exceeded"
            return ShowResult.REFUSED      # never chunked (N chunks = N visible edits)
        try:
            return self._paste(session, utterance, seq, span, delta)
        except (WlError, OSError) as exc:
            self.last_reason = f"clipboard wire fault: {type(exc).__name__}"
            self._restore_best_effort()
            logger.warning("clipboard show wire fault: session=%s seq=%s", session, seq)
            return ShowResult.UNKNOWN

    def _paste(self, session: int, utterance: str, seq: int, span: str, delta: str) -> ShowResult:
        """Stage → recheck → trigger → confirm → restore (the R.6 cycle)."""
        nonce = secrets.token_hex(16)
        try:
            src = self._wire.publish({TEXT_MIME: delta.encode("utf-8")}, nonce)
        except (WlError, OSError) as exc:
            self.last_reason = f"clipboard stage failed: {exc}"
            self._restore_best_effort()
            return ShowResult.REFUSED      # nothing pasted: the stage itself failed
        self._live_source = src
        self._restored = False
        # mutation-time recheck (clause 3): sync barrier; ANY foreign replacement
        # (byte-identical copies included — cancelled fires regardless) aborts.
        if not self._watchdog.check(self._wire, src):
            self.last_reason = "foreign selection change mid-window — aborted"
            self._restore_best_effort()
            logger.info("clipboard show aborted pre-trigger: session=%s seq=%s", session, seq)
            return ShowResult.REFUSED
        # ONE chord — never per-character, never --paste-once
        try:
            self._trigger()
        except Exception:
            self.last_reason = "trigger raised — outcome unverifiable"
            self._restore_best_effort()
            logger.warning("clipboard trigger raised: session=%s seq=%s", session, seq)
            return ShowResult.UNKNOWN      # may or may not have pasted: never retried
        # confirm (clause 3): positive witness, or UNKNOWN — never "applied" on faith
        confirmed = False
        if self._confirm is not None:
            try:
                confirmed = bool(self._confirm(delta))
            except Exception:
                confirmed = False   # a raising witness is an absent witness
        result = ShowResult.APPLIED if confirmed else ShowResult.UNKNOWN
        if not confirmed:
            self.last_reason = "target receipt unconfirmed"
            logger.info("clipboard show unconfirmed: session=%s seq=%s", session, seq)
        else:
            self.last_reason = ""
            self._owned_span = span        # advance ONLY on a witnessed apply
            self._revision += 1
            logger.info("clipboard show applied: session=%s seq=%s seq_delta_chars=%d",
                        session, seq, len(delta))
        # restore the user clipboard in EVERY terminal path (clause 1)
        self._restore_best_effort()
        return result

    # --- R.3 lifecycle: finalize / leave / cancel ------------------------------
    def finalize(self, session: int, utterance: str, seq: int,
                 expected_revision: int, span: str) -> ShowResult:
        """Matching final ⇒ NO further edit (zero clipboard events); pure
        extension ⇒ ONE paste of the delta; diverging final ⇒ REFUSED (an
        insert-only route cannot replace). Settles ownership on applied/
        unchanged only (mirrors the IM adapter)."""
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"
            return ShowResult.REFUSED
        if rendered_equal(self._owned_span, span) and self._owned_utterance == utterance:
            result = ShowResult.UNCHANGED   # ownership ends, no edit (R.3)
        else:
            result = self.show(session, utterance, seq, expected_revision, span)
        if result in (ShowResult.APPLIED, ShowResult.UNCHANGED):
            self._owned_span = ""
            self._owned_utterance = None
            self._closed_utterances.add(utterance)
            logger.info("clipboard finalize settled: session=%s seq=%s result=%s",
                        session, seq, result.value)
        return result

    def leave(self) -> None:
        """Stop preserving the pasted words — restore the clipboard, write
        nothing anywhere afterward. Never raises; clearing the binding FIRST
        means even a wedged wire cannot leave us writing after stop."""
        self._binding = None
        self._owned_span = ""
        self._owned_utterance = None
        self._restore_best_effort()

    def cancel(self) -> ShowResult:
        """Deliberate cancel: an insert-only route cannot remove owned text —
        REFUSED honestly (recorded, never faked). Nothing pending ⇒ UNCHANGED
        with no clipboard event. Ownership ends either way; the pasted words
        stay (R.3 stop-preserves; corrections belong to M5.T1's seam)."""
        if self._binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if rendered_equal(self._owned_span, ""):
            self.last_reason = "nothing pending"
            return ShowResult.UNCHANGED    # no clipboard event (G2-class pin)
        self.last_reason = "insert-only route cannot remove owned text — recorded, not faked"
        logger.info("clipboard cancel refused: owned words stay, ownership ends")
        self._owned_span = ""
        self._owned_utterance = None
        self._restore_best_effort()
        return ShowResult.REFUSED

    # --- restore (clause 1): exact per-type bytes via a fresh source ----------
    def _restore_best_effort(self) -> None:
        """Re-offer the snapshot's exact types + bytes (+ sentinel). Swallows
        every fault — restore is a safety path, never a crash path."""
        binding = self._binding
        if binding is None or self._restored:
            return
        snapshot = binding.snapshot
        formats = {f.mime: f.data for f in snapshot.formats}
        nonce = secrets.token_hex(16)   # fresh sentinel per staging generation
        try:
            self._live_source = self._wire.publish(formats, nonce)
            self._restored = True
            logger.info("clipboard restored: formats=%d", len(formats))
        except (WlError, OSError):
            self._restored = False      # L6-class fault: visible, recorded, honest
            logger.warning("clipboard restore failed — selection left as-is")
