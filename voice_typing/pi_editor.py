"""voice_typing.pi_editor — the cooperating-editor TargetAdapter: pi's prompt via the seam socket.

Binds the SPECIFIC editable field — pi's prompt editor, verified through the
extension's own ``read`` snapshot — and delivers ONE buffer op per recognition
update over the AF_UNIX JSONL socket the pi extension serves (P1.M5.T1.S1's
``voice-editor.ts``: ``$XDG_RUNTIME_DIR/voice-typing/pi-editor.sock``, protocol
v1 — one line in → one line out, replies mirror the ShowResult vocabulary, and
there is NO id echo). This is the SECOND real bulk-delivery route (PRD
§4.2sexies R.3) after the IM adapter: same DeliveryTarget contract, different
transport — and ownership verified AT THE TARGET: the extension refuses any
range outside what it wrote and reports takeover, so this adapter keeps its
client-side accounting honest against cheap server-side truth. Synthesized
typing is FORBIDDEN here (R.1): every primitive is one buffer op.

THE DELIVERY MODEL (R.3), one line per Protocol call:
  acquire()  bind the prompt editor via ONE ``read``; refuse dirty, non-empty
             owned, or malformed states BEFORE any delivery (never adopt a
             stranded prior-session fragment).
  show(...)  ONE insert (pure extension of the owned span, delta only) or ONE
             atomic replace over the owned UTF-16 range (any divergence);
             zero-diff ⇒ ZERO socket requests.
  finalize() a final matching the visible text settles ownership with NO edit;
             a differing final goes through show() (ONE op) then settles.
  leave()    stop preserves the last visible words; protocol v1 has NO leave
             op — send NOTHING (just hang up); idempotent, never raises.
  cancel()   remove the owned fragment in ONE op and keep listening;
             nothing pending ⇒ UNCHANGED with NO request (G2 trace_07 pin).

THE RESULT TAXONOMY (ShowResult): applied | unchanged | refused | unknown.
An operation whose outcome came back UNKNOWN (None/timeout reply) is NEVER
re-issued by this adapter (R.5: a may-have-landed op is never repeated — the
controller disarms). The CONTROLLER owns the 250 ms deadline
(bulk_controller.py op_deadline) — this adapter only reports honestly and
fast: socket timeouts are 0.25 s per op, 2.5 s for acquire.

THE EVENT-COUNT LAW (R.1): extension of the owned span ⇒ ONE insert; any
divergence ⇒ ONE replace; zero-diff (rendered_equal) ⇒ 0 requests; matching
finalize ⇒ no edit; cancel with nothing pending ⇒ no request.

UNITS: the wire speaks UTF-16 CODE UNITS (replies carry ``units:"utf-16"``;
JS ``String.length`` semantics — an astral char such as 🫡 counts as 2).
Every offset/length goes through bulk_delivery.map_span on the ORIGINAL
string — never a raw ``len()`` as an offset, never a normalized/lowercased
copy (R.3's index-desync rule).

ACQUIRE REFUSAL TAXONOMY (fail BEFORE delivery; each branch test-pinned in
tests/test_pi_editor.py):
  - "pi socket absent"         — ENOENT: no pi/extension serving the socket
  - "pi socket no reply"       — ECONNREFUSED/stale socket, or a read/ack
                                 that never arrived within the timeout
  - "read missing fields"      — ok reply without text/owned/dirty/units:"utf-16"
  - "editor dirty"             — a delegated keystroke already landed
                                 (takeover happened; the watch also halts)
  - "editor owns fragment"     — owned non-null at acquire: a stranded
                                 prior-session fragment is NEVER adopted
  - "inconsistent owned range" — owned malformed/out of bounds vs the text,
                                 or mismatching our client-side accounting
  - "<editor error/reason>"    — the extension's own error/refusal strings,
                                 propagated verbatim (machine-readable)
  - "revision regression"      — expected_revision below our counter
                                 (stale/desynced caller), refused pre-request
  - "not acquired" / "utterance closed" / "nothing pending" — lifecycle
                                 guards, mirrors the IM adapter

OWNERSHIP COORDINATES (the protocol's honest gap): ``insert`` is
caret-relative (no offsets on the wire), so the owned range's ABSOLUTE
UTF-16 start in the buffer is unknown at acquire (owned is null there —
stranded fragments are refused). The first applied op triggers ONE ``read``
that binds the absolute range and cross-checks it against our client-side
accounting (``end − start`` must equal our tracked length; mismatch ⇒
"inconsistent owned range", refused — verify, NEVER repair). A failed bind
stays unbound and is re-attempted before any later replace (a replace never
fires on guessed coordinates). Replacements then track client-side,
advancing ONLY on applied replies. ``read.cursor`` is ``{line,col}`` — a
screen position, NOT a buffer offset: it is parsed nowhere; owned-range
UTF-16 offsets are the only position truth.

DOCUMENTED LIMITATIONS (honest gaps, never guessed heuristics): protocol v1
exposes NO password/secret hint and NO selection state — R.3's password and
never-replace-a-selection rules are enforced where a signal exists (other
adapters own them). v1 has NO leave op: leave() sends nothing and the
extension's ownership ends at its own boundary (cancel / takeover / socket
close). The session/utterance/seq arguments are bookkeeping only — v1 ops
carry no session fields on the wire.

CONSUMES: a client duck — connect(timeout=…) -> bool, request(op,
timeout=…, **fields) -> dict | None, a settable ``on_event`` slot,
``.sock_path``, close() (the real PiEditorClient below; test fakes duck the
same surface — NEVER imported here), plus a controller duck with
halt_for_takeover(reason) for the watch (duck-typed, like ime/takeover.py).
CONSUMED BY: P1.M5.T2.S1 (the G3 pi-prompt row in isolated Ghostty) and
P1.M6.T2.S1 (daemon dispatch wiring behind output.delivery).
FENCES: no bulk_controller/daemon/ime imports (duck-typed seams only); no
config surface; the watch's event→reason map is fixed; this module never
self-times the controller's deadline and never re-issues an op after an
UNKNOWN outcome.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass

from voice_typing.bulk_delivery import (
    AcquireResult,
    ShowResult,
    TargetUnits,
    map_span,
    rendered_equal,
)

logger = logging.getLogger(__name__)

_ACQUIRE_TIMEOUT_S = (
    2.5  # connect + one read; the controller arms outside its op deadline
)
_SHOW_TIMEOUT_S = (
    0.25  # fits the controller's 250 ms op deadline (failure-complete M3.T2.S2)
)
_RECV_IDLE_S = (
    0.5  # reader-thread recv idle bound — no unbounded makefile reads (ctl.py hang)
)
_JOIN_S = 1.0  # close() joins the reader at most this long

_DEFAULT_SOCK_SUBPATH = ("voice-typing", "pi-editor.sock")


def _default_sock_path() -> str:
    """S1's socket location: $XDG_RUNTIME_DIR/voice-typing/pi-editor.sock."""
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return os.path.join(xdg, *_DEFAULT_SOCK_SUBPATH)


@dataclass(frozen=True)
class PiEditorBinding:
    """The opaque AcquireResult.handle — everything later ops re-check, nothing more.

    owned_start_u16 is −1 until the first applied op binds the absolute UTF-16
    start via one read (insert is caret-relative — the buffer position is
    unknown before that); owned_len_u16 is the cumulative UTF-16 length the
    extension owns for us. revision is a CLIENT-SIDE counter (protocol v1
    reports none): seeded 0 at each acquire and +1 only on applied — the
    controller seeds expected_revision from it and +1s ONLY on applied, so
    the two counters stay in lockstep (documented choice; R.3/R.5).
    """

    sock_path: str
    owned_start_u16: int
    owned_len_u16: int
    revision: int


class PiEditorClient:
    """AF_UNIX JSONL transport duck — strictly one request in flight, events split out.

    The ImeProcess request/event split (ime/manager.py) minus the child-process
    management: connect() dials S1's socket and starts a daemon reader
    thread; request() serializes the WHOLE send-and-wait cycle under one
    lock (the protocol has NO id echo, so one request in flight is the only
    correlation rule), and the reader dispatches on the ``"event"`` key
    FIRST — an id-less ``{"event":…}`` line never parses as a pending
    reply. Every recv is timeout-bounded on the reader thread (the ctl.py
    makefile-without-timeout hang is this repo's canonical bug; no
    unbounded reads here).

    Honesty rules: request() returns None on timeout/dead socket — never a
    resend. A timeout quarantines the connection (dead): an orphaned reply
    could alias the next request's reply, so the socket is marked dead and
    a fresh acquire() reconnects. connect() sets ``connect_error`` to the
    machine-readable refusal ("pi socket absent" for ENOENT, "pi socket no
    reply" for refusal/unavailable) so the target's taxonomy stays honest.
    """

    def __init__(self, sock_path: str | None = None, *, on_event=None):
        self.sock_path = sock_path if sock_path is not None else _default_sock_path()
        self.on_event = (
            on_event  # settable slot: PiEditorTakeoverWatch.attach() (or tests)
        )
        self.connect_error = ""
        self._sock: socket.socket | None = None
        self._state_lock = threading.Lock()  # _sock/_dead
        self._send_lock = threading.Lock()  # one request in flight (no id echo)
        self._reply_cv = threading.Condition()
        self._reply: dict | None = None
        self._reader: threading.Thread | None = None
        self._closing = threading.Event()

    # --- lifecycle -----------------------------------------------------------
    def connect(self, timeout: float = 1.0) -> bool:
        """Dial S1's socket (idempotent while healthy). False + connect_error on failure."""
        with self._state_lock:
            if self._sock is not None and not self._closing.is_set():
                return True  # already connected — a no-op, never a second dial
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(max(0.05, float(timeout)))
        try:
            sock.connect(self.sock_path)
        except FileNotFoundError:
            self.connect_error = "pi socket absent"  # no pi / extension not installed
            sock.close()
            return False
        except OSError:
            self.connect_error = (
                "pi socket no reply"  # stale file (ECONNREFUSED) / unavailable
            )
            sock.close()
            return False
        sock.settimeout(_RECV_IDLE_S)  # reader recv bound — the anti-hang discipline
        with self._state_lock:
            self._closing.clear()
            self._sock = sock
        self.start_events()
        return True

    def start_events(self) -> None:
        """Start the reader thread (idempotent); connect() does this automatically."""
        with self._state_lock:
            if self._reader is not None and self._reader.is_alive():
                return
            self._closing.clear()
        t = threading.Thread(
            target=self._read_loop, name="pi-editor-reader", daemon=True
        )
        with self._state_lock:
            self._reader = t
        t.start()

    def close(self) -> None:
        """Idempotent teardown: stop the reader, drop the socket. Sends nothing."""
        self._closing.set()
        with self._state_lock:
            sock, self._sock = self._sock, None
            reader = self._reader
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=_JOIN_S)

    # --- the request path ----------------------------------------------------
    def request(
        self, op: str, timeout: float = _SHOW_TIMEOUT_S, **fields
    ) -> dict | None:
        """One JSONL line in → the reply dict; None on timeout/dead socket (NEVER a resend).

        Strictly one request in flight: the send-lock is held across the
        whole send-and-wait. On timeout the connection is quarantined (an
        orphaned reply could alias the next request) — the caller treats
        None as UNKNOWN and the controller disarms; a fresh acquire()
        reconnects.
        """
        payload = {"op": op, **fields}  # closed op set: insert|replace|cancel|read
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._send_lock:
            with self._state_lock:
                sock = self._sock
            if sock is None or self._closing.is_set():
                return None
            with self._reply_cv:
                self._reply = None
            try:
                sock.sendall(line.encode("utf-8"))
            except OSError:
                logger.debug("pi-editor client: send failed (socket gone)")
                self._mark_dead(sock)
                return None
            deadline = time.monotonic() + max(0.0, float(timeout))
            with self._reply_cv:
                while self._reply is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._reply_cv.wait(remaining)
                reply = self._reply
            if reply is None:
                self._mark_dead(
                    sock
                )  # quarantine: the late reply must not alias the next op
            return reply

    # --- the reader path -------------------------------------------------------
    def _read_loop(self) -> None:
        """The ONLY recv consumer: timeout-bounded, never lets a bad line kill it."""
        with self._state_lock:
            sock = self._sock
        if sock is None:
            return
        buf = b""
        while not self._closing.is_set():
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue  # bounded idle spin — the ctl.py antidote
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line, buf = buf[:nl], buf[nl + 1 :]
                if line.strip():
                    self._on_line(line)
        self._mark_dead(
            sock
        )  # reader exit (EOF/error/close) ⇒ subsequent requests fail honestly

    def _on_line(self, raw: bytes) -> None:
        """Dispatch ONE line: events FIRST (CRITICAL #1 — never parse as a reply)."""
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("pi-editor reader: undecodable line dropped")
            return
        if not isinstance(obj, dict):
            return
        if (
            "event" in obj
        ):  # id-less, unsolicited → the takeover path, never the reply slot
            cb = self.on_event
            if cb is not None:
                try:
                    cb(obj)
                except Exception:  # noqa: BLE001 — a callback fault must not kill the reader
                    logger.warning("pi-editor reader: on_event raised", exc_info=True)
            return
        with self._reply_cv:
            self._reply = obj
            self._reply_cv.notify_all()

    def _mark_dead(self, sock: socket.socket) -> None:
        """Quarantine one socket (reader exit / send fault / request timeout)."""
        self._closing.set()
        with self._state_lock:
            if self._sock is sock:
                self._sock = None
        try:
            sock.close()
        except OSError:
            pass


class PiEditorTarget:
    """Daemon-side adapter: the DeliveryTarget over S1's socket (R.3/R.5).

    Guard-for-guard the ImeTarget pattern (ime/target.py) over a different
    wire: acquire verifies via the extension's ``read`` (read IS the verify —
    v1 has no separate verify op); show() re-checks lifecycle/revision at
    mutation time and picks ONE insert or ONE replace; state advances ONLY
    on applied replies; an op whose reply never came is reported UNKNOWN and
    left alone (the controller disarms — this adapter never repeats it).
    """

    units = (
        TargetUnits.UTF16_UNITS
    )  # the wire speaks UTF-16 code units (units:"utf-16")

    def __init__(
        self, client
    ):  # duck: PiEditorClient or a test fake — NEVER imported here
        self._client = client
        self._binding: PiEditorBinding | None = None
        self._last_applied_span = (
            ""  # the last APPLIED complete rendered span ("" until applied)
        )
        self._owned_utterance: str | None = None
        self._closed_utterances: set[str] = set()
        self._revision = (
            0  # client-side counter; +1 ONLY on applied (locks with the controller)
        )
        self._owned_start_u16 = (
            -1
        )  # absolute UTF-16 start of OUR fragment; −1 = unbound (unknown)
        self._owned_len_u16 = 0  # cumulative UTF-16 length the extension owns for us
        self.last_reason = ""  # machine-readable refusal/unknown taxonomy (R.5 logs)

    # --- acquire (R.3): bind the FIELD, verify via the extension's read -----
    def acquire(self) -> AcquireResult:
        """Bind the prompt editor or refuse BEFORE any delivery (the taxonomy above).

        read IS the verify in protocol v1: a clean read (owned null, not
        dirty) is the whole binding proof. A non-null owned range is a
        stranded prior-session fragment — never adopted.
        """
        if not self._client.connect(timeout=_ACQUIRE_TIMEOUT_S):
            reason = getattr(self._client, "connect_error", "") or "pi socket no reply"
            return AcquireResult(ok=False, reason=reason)
        r = self._client.request("read", timeout=_ACQUIRE_TIMEOUT_S)
        if r is None:
            return AcquireResult(ok=False, reason="pi socket no reply")
        if r.get("ok") is False:
            return AcquireResult(ok=False, reason=r.get("error", "editor refused"))
        text, owned, dirty = r.get("text"), r.get("owned"), r.get("dirty")
        if (
            not isinstance(text, str)
            or not isinstance(dirty, bool)
            or not isinstance(owned, (dict, type(None)))
            or r.get("units") != "utf-16"
        ):
            return AcquireResult(ok=False, reason="read missing fields")
        if dirty:
            return AcquireResult(ok=False, reason="editor dirty")
        if owned is not None:
            start, end = owned.get("start"), owned.get("end")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end < start
                or end > self._utf16_len(text)
            ):
                return AcquireResult(ok=False, reason="inconsistent owned range")
            return AcquireResult(ok=False, reason="editor owns fragment")
        binding = PiEditorBinding(
            sock_path=getattr(self._client, "sock_path", ""),
            owned_start_u16=-1,  # insert is caret-relative: the absolute start binds on first apply
            owned_len_u16=0,
            revision=0,  # client-side counter (v1 reports none — documented choice)
        )
        self._binding = binding
        self._last_applied_span = ""  # fresh acquisition: nothing applied yet
        self._owned_utterance = None
        self._closed_utterances.clear()  # nothing is closed in the newly bound field
        self._revision = 0
        self._owned_start_u16 = -1
        self._owned_len_u16 = 0
        self.last_reason = ""
        return AcquireResult(ok=True, handle=binding, revision=binding.revision)

    # --- show (R.3/R.5): ONE insert OR ONE atomic replace --------------------
    def show(
        self, session: int, utterance: str, seq: int, expected_revision: int, span: str
    ) -> ShowResult:
        """ONE buffer op per change; zero-diff ⇒ ZERO requests (R.1).

        Extension of the owned span ⇒ ONE ``insert`` (delta only). Any
        divergence ⇒ ONE atomic ``replace`` over the owned UTF-16 range
        (bound via one read first — never guessed coordinates). The reply
        maps honestly: None ⇒ UNKNOWN (the op is not re-issued); refused ⇒
        the editor's reason verbatim; state advances ONLY on applied (the
        controller +1s expected_revision only on applied).
        """
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if utterance in self._closed_utterances:
            self.last_reason = (
                "utterance closed"  # settled final/cancel — never a 2nd op
            )
            return ShowResult.REFUSED
        # Unlike the IM route there is no span reset on utterance switch: the
        # extension's owned range persists server-side until cancel/takeover,
        # so client-side accounting keeps matching server truth (the dropped-
        # final case leaves the visible words owned; a later insert extends
        # them or a later cancel removes them — never a client-side delete).
        self._owned_utterance = utterance
        # (1) zero-diff guard FIRST — render-equal ⇒ ZERO events, ZERO requests (R.1).
        if rendered_equal(self._last_applied_span, span):
            return ShowResult.UNCHANGED
        # (2) revision-regression guard: the caller seeds expected_revision
        #     from acquire's revision and +1s ONLY on applied; anything lower
        #     (or non-int) is a stale/desynced caller — refuse BEFORE any
        #     request (R.5).
        if not isinstance(expected_revision, int) or expected_revision < self._revision:
            self.last_reason = "revision regression"
            return ShowResult.REFUSED
        owned = self._last_applied_span
        correction = False
        if span.startswith(owned):
            # ---- INSERT path: pure extension — the delta only, at the caret ----
            delta = span[len(owned) :]
            r = self._client.request("insert", timeout=_SHOW_TIMEOUT_S, text=delta)
        else:
            # ---- REPLACE path: ONE atomic rewrite over the owned UTF-16 range ----
            if not self._bind_owned_coords():  # verify BEFORE any mutating request;
                return ShowResult.REFUSED  # nothing was sent on a bind failure
            start = self._owned_start_u16
            end = (
                start + self._owned_len_u16
            )  # UTF-16 units via map_span — never raw len()
            correction = True
            r = self._client.request(
                "replace", timeout=_SHOW_TIMEOUT_S, start=start, end=end, text=span
            )
        # ---- honest mapping (both paths; bytes-sent ≠ applied) ------------------
        if r is None:
            self.last_reason = "pi socket no reply"
            logger.warning(
                "pi-editor show: no reply (session=%s seq=%s span_chars=%d)",
                session,
                seq,
                len(span),
            )
            return (
                ShowResult.UNKNOWN
            )  # may have landed — the controller disarms; not re-issued here
        if r.get("ok") is False:
            self.last_reason = r.get("error", "editor refused")
            return ShowResult.REFUSED
        result = r.get("result")
        if result == "applied":
            self._last_applied_span = span
            self._revision += 1
            if correction:
                self._owned_len_u16 = self._utf16_len(
                    span
                )  # the range was rewritten in place
            else:
                self._owned_len_u16 += self._utf16_len(delta)
            if self._owned_start_u16 < 0 and not self._bind_owned_coords():
                # Best-effort first bind: the op APPLIED regardless; a later
                # replace re-attempts the bind lazily (never on guessed coords).
                logger.info("pi-editor show applied: owned-coords bind deferred")
            self.last_reason = ""
            logger.info(
                "pi-editor show applied: session=%s seq=%s op=%s owned_u16=%d t_ms=%s",
                session,
                seq,
                "replace" if correction else "insert",
                self._owned_len_u16,
                r.get("t_ms"),
            )
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = r.get(
                "reason", "editor refused"
            )  # editor's reason, verbatim
            return ShowResult.REFUSED
        if result == "unchanged":
            # The editor confirms render-equal — adopt the span so client view
            # stays aligned with what the editor last confirmed (no revision bump).
            self._last_applied_span = span
            return ShowResult.UNCHANGED
        self.last_reason = f"editor result {result!r}"
        logger.warning(
            "pi-editor show unknown: session=%s seq=%s result=%r", session, seq, result
        )
        return ShowResult.UNKNOWN

    # --- ownership-coords bind: ONE read; verify, never repair ---------------
    def _bind_owned_coords(self) -> bool:
        """Bind the owned range's absolute UTF-16 start via one ``read``.

        The extension's mutate replies carry no owned range, and insert is
        caret-relative — so the absolute start is learned here and
        cross-checked against our client-side length (mismatch ⇒ refused,
        stop, never repair). Called after the first applied op and before
        any replace that needs unbound coordinates.
        """
        if self._owned_start_u16 >= 0:
            return True
        r = self._client.request("read", timeout=_SHOW_TIMEOUT_S)
        if r is None:
            self.last_reason = "pi socket no reply"
            return False
        if r.get("ok") is False:
            self.last_reason = r.get("error", "editor refused")
            return False
        text, owned, dirty = r.get("text"), r.get("owned"), r.get("dirty")
        if (
            not isinstance(text, str)
            or not isinstance(dirty, bool)
            or "owned" not in r
            or r.get("units") != "utf-16"
        ):
            self.last_reason = "read missing fields"
            return False
        if dirty:
            self.last_reason = (
                "editor dirty"  # a keystroke landed — the watch also halts
            )
            return False
        if not isinstance(owned, dict):
            self.last_reason = (
                "inconsistent owned range"  # we applied ops — owned cannot be null
            )
            return False
        start, end = owned.get("start"), owned.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end < start
            or end - start != self._owned_len_u16
            or end > self._utf16_len(text)
        ):
            self.last_reason = "inconsistent owned range"
            return False
        self._owned_start_u16 = start
        return True

    # --- R.3 lifecycle: finalize / leave / cancel -----------------------------
    def finalize(
        self, session: int, utterance: str, seq: int, expected_revision: int, span: str
    ) -> ShowResult:
        """Settle the utterance.

        Matching final ⇒ NO further edit (zero requests — ownership ends).
        Differing final ⇒ the landed show() paths, delegated — never
        reimplemented. No preceding partial ⇒ inserts once. A duplicate
        final for a settled utterance refuses "utterance closed".
        """
        if self._binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"  # duplicate final — never a 2nd op
            return ShowResult.REFUSED
        live = bool(self._last_applied_span) and self._owned_utterance == utterance
        result = self.show(session, utterance, seq, expected_revision, span)
        if result in (ShowResult.APPLIED, ShowResult.UNCHANGED):
            self._last_applied_span = ""  # ownership ENDS (R.3); the owned
            self._owned_utterance = None  # RANGE stays server-side (no leave op)
            self._closed_utterances.add(utterance)
            logger.info(
                "pi-editor finalize settled: session=%s seq=%s result=%s live=%s",
                session,
                seq,
                result.value,
                live,
            )
        return result

    def leave(self) -> None:
        """Stop preserving the last visible words — NO post-stop writes anywhere.

        Protocol v1 has NO leave op: clear the binding FIRST (nothing may
        write after this line), then hang the socket up — ZERO requests.
        Never raises; idempotent. Post-leave every op refuses "not acquired"
        until a fresh acquire() re-binds (re-connecting through the same
        client duck).
        """
        binding = self._binding
        self._binding = None  # FIRST: nothing may write after this
        self._last_applied_span = ""
        self._owned_utterance = None
        self._owned_start_u16 = -1
        self._owned_len_u16 = 0
        if binding is None:
            return  # already left — pure no-op
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — dead client must not propagate
            logger.warning(
                "pi-editor leave: client close raised"
            )  # one line, no text (R.5)

    def cancel(self) -> ShowResult:
        """Remove the owned fragment in ONE op and keep listening.

        Nothing pending (no applied partial) ⇒ UNCHANGED with NO request
        (G2 trace_07 pin — the controller stays active). The ``cancel`` op
        carries no range: the extension removes what IT owns, so no
        coordinates are needed here; an uncertain editor state surfaces as
        a refused reply ⇒ REFUSED (stop, never repair). Applied cancel
        clears the server-owned range, so the coordinate bookkeeping resets
        and the next utterance's first op rebinds from scratch.
        """
        if self._binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if rendered_equal(self._last_applied_span, ""):
            self.last_reason = (
                "nothing pending"  # queued-but-undispatched partial ⇒ fine
            )
            return ShowResult.UNCHANGED  # NO request (G2 trace_07 pin)
        r = self._client.request("cancel", timeout=_SHOW_TIMEOUT_S)
        if r is None:
            self.last_reason = "pi socket no reply"
            logger.warning("pi-editor cancel: no reply")
            return ShowResult.UNKNOWN
        if r.get("ok") is False:
            self.last_reason = r.get("error", "editor refused")
            return ShowResult.REFUSED
        result = r.get("result")
        if result == "applied":
            u, self._owned_utterance = self._owned_utterance, None
            if u is not None:
                self._closed_utterances.add(u)
            self._last_applied_span = ""
            self._owned_start_u16 = -1  # the extension cleared owned —
            self._owned_len_u16 = 0  # the next utterance rebinds cleanly
            self.last_reason = ""
            logger.info("pi-editor cancel applied")
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = r.get("reason", "editor refused")
            return ShowResult.REFUSED
        if result == "unchanged":
            self.last_reason = "editor unchanged"
            return ShowResult.REFUSED  # we sent a real cancel; "unchanged" is
        self.last_reason = (
            f"editor result {result!r}"  # an unexpected editor state — stop
        )
        logger.warning("pi-editor cancel unknown: result=%r", result)
        return ShowResult.UNKNOWN

    # --- units plumbing (never hand-roll offsets) -----------------------------
    @staticmethod
    def _utf16_len(text: str) -> int:
        """Length of `text` in UTF-16 code units — astral chars count 2 (map_span ground truth)."""
        return map_span(text, 0, len(text), TargetUnits.UTF16_UNITS)[1]

    @staticmethod
    def to_u16_span(text: str, start_char: int, end_char: int) -> tuple[int, int]:
        """char span → UTF-16 unit span on the ORIGINAL string (thin map_span wrapper)."""
        return map_span(text, start_char, end_char, TargetUnits.UTF16_UNITS)


class PiEditorTakeoverWatch:
    """Wiring: client events → ONE halt_for_takeover + ONE reason (latched).

    Mirrors ime/takeover.py's TakeoverWatch latch: the FIRST
    ``{"event":"takeover","source":…}`` line maps to the fixed, machine-
    readable reason ``"pi-editor <source> takeover"`` (source defaults to
    "key"), latches the watch, and halts the controller ONCE. Second-and-
    later events are logged (counts/sources only — never recognition text,
    R.5) and dropped. on_event runs on the client's reader thread
    (single-threaded by construction — the latch needs no lock) and never
    raises outward. Op replies are dispatched to the request slot by the
    client (events first — CRITICAL #1), so our own writes can never
    trigger the halt.
    """

    def __init__(self, controller=None, target=None):
        self._controller = (
            controller  # duck: halt_for_takeover(reason) — never imported
        )
        self._target = target  # optional duck: leave() first, like the IM watch
        self._latched = False
        self.revocations = 0  # observable count (always 0 or 1)
        self.reason: str | None = None  # THE recorded reason (None until revoked)
        self._client = None

    # --- subscription ---------------------------------------------------------
    def attach(self, client) -> None:
        """Subscribe to a client's event feed (settable ``on_event`` slot)."""
        self._client = client
        client.on_event = self.on_event

    def detach(self) -> None:
        """Unsubscribe (close() calls this); harmless if never attached."""
        client, self._client = self._client, None
        if client is not None and getattr(client, "on_event", None) == self.on_event:
            client.on_event = None

    def close(self) -> None:
        """Detach from the feed (the controller owns the post-halt lifecycle)."""
        self.detach()

    # --- the feed ---------------------------------------------------------------
    def on_event(self, ev) -> None:
        """The takeover feed target. Never raises; latched after the first halt."""
        if self._latched:
            return  # latched: exactly one halt per watch
        if not isinstance(ev, dict) or ev.get("event") != "takeover":
            logger.info(
                "pi-editor takeover: non-takeover event dropped (%s)",
                ev.get("event", "?") if isinstance(ev, dict) else "?",
            )
            return
        source = ev.get("source", "key")
        self._revoke(f"pi-editor {source} takeover")

    # --- the halt action ----------------------------------------------------------
    def _revoke(self, reason: str) -> None:
        self._latched = True  # latch BEFORE acting: one halt, ever
        self.revocations += 1
        self.reason = reason
        logger.info(
            "pi-editor takeover: halt reason=%s", reason
        )  # R.5: reason only, no text
        if self._target is not None:
            try:
                self._target.leave()  # binding cleared AT THE TARGET; zero post-stop writes
            except Exception:  # noqa: BLE001 — a dead target must not block the halt
                logger.warning(
                    "pi-editor takeover: target.leave() raised", exc_info=True
                )
        if self._controller is not None:
            try:
                self._controller.halt_for_takeover(reason)
            except Exception:  # noqa: BLE001 — the halt seam must never break the feed
                logger.warning(
                    "pi-editor takeover: halt_for_takeover raised", exc_info=True
                )


__all__ = [
    "PiEditorBinding",
    "PiEditorClient",
    "PiEditorTarget",
    "PiEditorTakeoverWatch",
]
