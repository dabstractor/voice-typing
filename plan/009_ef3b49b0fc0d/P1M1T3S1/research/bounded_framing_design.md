# Research: bounded control framing — ingress facts, reader design, test plan (VERIFIED)

**Status:** Verified against live `voice_typing/daemon.py` (ControlServer._handle :3386-3438,
_dispatch :3440+), `tests/test_control_socket.py`, `voice_typing/ctl.py` (the client-side bounded
reader sibling), and PRD.md:448-464 (§4.8.1 B). Read-only. Load-bearing source for P1M1T3S1/PRP.md.

## 1. The current ingress (verbatim facts)

`ControlServer._handle` (daemon.py:3386-3438): `rfile = conn.makefile("r", encoding="utf-8", newline="\n")`
then `for line in rfile:` — an **unbounded text readline**. Three properties the new reader must replace:
- **Unbounded buffering**: a client that never sends `\n` makes `for line in rfile` buffer forever
  (no byte cap) — exactly the PRD §4.8.1 B hazard ("enforce byte limits while reading, before unbounded
  buffering").
- **Permissive decode**: `encoding="utf-8"` on a makefile raises `UnicodeDecodeError` (a ValueError)
  out of the iterator — caught only by the outer `except OSError`? NO: UnicodeDecodeError is NOT an
  OSError → it would propagate out of `_handle` and kill the worker thread silently (no reply to the
  client). The new reader must REJECT invalid UTF-8 with a framed error reply, never crash the worker.
- **No protocol handoff**: the makefile's internal buffer swallows any bytes past the first newline
  (coalesced frames) — a native owner pump (P1.M1.T3.S3) taking over the connection could never see
  them. The reader must preserve unread bytes.

The response path (`wfile.write(json.dumps(response) + "\n"); wfile.flush()`) stays as-is (one JSON
line per request; `shutting_down` breaks the loop). `_dispatch(line: str) -> dict` stays the
validator/dispatcher (BUG-005: empty line → `_dispatch("")` → `malformed JSON:` reply — PRESERVE).

Existing test shapes that MUST stay green (test_control_socket.py): `test_round_trip_malformed_over_wire`
(`garbled\n` → ok False), `test_round_trip_empty_line_gets_error_reply` (`\n`, `   \n` → error startswith
`malformed JSON:`), `test_round_trip_empty_line_mid_connection` (valid, empty, valid → 3 replies, lockstep),
`test_round_trip_multi_line_one_connection`, `test_round_trip_quit`, plus the `server` fixture's real
AF_UNIX round trips (`_send`/`_send_lines` helpers block until a reply line — they double as hang repros).

## 2. PRD §4.8.1 B — the framing contract (PRD.md:448-450)

"UTF-8 newline-delimited JSON objects, with a **32 KiB wire limit per request and live event
(including newline)**; enforce byte limits while reading, before unbounded buffering, and reject invalid
UTF-8, malformed frames, invalid types, oversized fields, or unsupported protocol before arming."
+ "Keep existing one-request commands and status/recovery behavior backward-compatible outside native mode."

## 3. The reader design (voice_typing/editor_protocol.py — NEW module)

```python
MAX_FRAME_BYTES = 32 * 1024          # 32 KiB INCLUDING the terminating newline (PRD §4.8.1 B)

class FrameError(Exception):         # a framed, replyable protocol error (never a crash)
    def __init__(self, reason: str, *, detail: str = "") -> None: ...   # reason is a stable code

# reasons (stable lowercase codes; the reply carries reason + a SHORT detail, never raw bytes):
#   "invalid-utf8" | "frame-too-large" | "eof" (partial frame at EOF) | "io"

class FrameReader:
    """Byte-bounded strict-UTF-8 JSONL frame reader over a recv()-style callable.
    feed bytes via read_frame(); preserves bytes past the frame's newline (unread buffer) so a
    later protocol (native owner pump) can take the connection over without losing coalesced frames."""
    def __init__(self, recv, *, max_bytes: int = MAX_FRAME_BYTES, chunk_size: int = 4096) -> None
    def read_frame(self) -> dict          # raises FrameError; returns the parsed JSON object (must be a dict? NO —
                                           #   non-dict JSON is _dispatch's job: "request must be a JSON object")
    @property
    def unread(self) -> bytes             # bytes after the last consumed newline (handoff)
    def read_frame_bytes(self) -> bytes   # the raw frame (sans newline) — for the handler to pass to _dispatch

def encode_line(obj) -> bytes:            # json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n";
                                           #   raises FrameError("frame-too-large") if > MAX_FRAME_BYTES
                                           #   (the live/event encoder bound; replies are small but the cap is the contract)
```

**Algorithm (read_frame_bytes) — the load-bearing discipline (PROBE-VALIDATED, 12 cases):**
```
buf = bytearray(); buf += self._unread; self._unread = b""   # re-arm from the handoff buffer
while True:
    i = buf.find(b"\n")
    if i != -1:
        frame = bytes(buf[:i]); self._unread = bytes(buf[i+1:])
        if len(frame) + 1 > max_bytes: raise FrameError("frame-too-large")   # incl. newline; buffer ALREADY resynced
        return frame
    if len(buf) + 1 > max_bytes:            # no newline yet and the NEXT byte would exceed the cap
        self._drain_runaway(buf)            # RESYNC: consume THROUGH the offending newline (see below)
        raise FrameError("frame-too-large")
    chunk = self._recv(chunk_size)          # OSError -> FrameError("io"); b"" -> EOF
    if not chunk:
        raise FrameError("eof", "partial" if buf else "")   # PRD T10a "partial EOF"
    buf += chunk

def _drain_runaway(buf):                    # THE PROBE-CAUGHT FIX. A naive "drop the buffer" leaves the
    while True:                             # runaway frame's TAIL + newline still unread in the socket;
        i = buf.find(b"\n")                # the next read then sees that stray '\n' -> a PHANTOM EMPTY frame
        if i != -1:                         # -> a second (spurious) malformed-JSON reply: TWO replies for ONE
            self._unread = bytes(buf[i+1:]); return   # bad request = a lockstep violation. So: keep recv'ing
        chunk = self._recv(chunk_size)      # until the offending newline is consumed, and hand the bytes
        if not chunk: self._unread = b""; return       # AFTER it to the next read (a real frame boundary).
        buf += chunk                        # OSError mid-drain -> unread=b"" (nothing to resync to).
```
Strict UTF-8 decode happens in the HANDLER (not the reader) so the reader stays bytes-only and the
handoff buffer is never corrupted by a decode failure: `frame.decode("utf-8")` → UnicodeDecodeError →
reply `{"ok":false,"error":"invalid UTF-8 frame"}` and CONTINUE (lockstep preserved — the frame was
fully consumed; the next frame is independent).

**TEST-HARNESS LESSON (probe-caught):** handoff/partial-read assertions on the exact `unread` contents
are TIMING-DEPENDENT over a real `socket.socketpair()` (the kernel may coalesce three `sendall`s into
one `recv`, so `unread` legitimately differs run-to-run — observed flipping between two probe runs).
Byte-level tests MUST use a deterministic in-memory fake `recv` scripted with exact chunks; reserve
`socketpair` for the `_handle`-level tests (invalid-UTF8 reply + continue, oversize reply + continue,
partial-EOF reply then close). Also: the probe's one "failure" was a FIXTURE TYPO (`b'pus"}'` vs the
correct `b'p"}'` for `stop"}`) — the reader logic was correct throughout; write fixtures from the real frame.

**Why the reader is bytes + recv rather than makefile:** (1) the byte cap can only be enforced on
raw bytes before decode; (2) `recv` is injectable → tests use `socket.socketpair()` + partial sends +
fake clocks (contract), never a live listener; (3) the `unread` buffer is the protocol-handoff seam
T3.S3 needs. The `_handle` change is minimal: replace the `makefile("r")` iteration with
`reader = FrameReader(conn.recv)` + `while True: frame = reader.read_frame_bytes() → decode → _dispatch → reply`.

**Error replies (framed, lockstep, no raw echo):** `{"ok":false,"error":"frame too large (max 32768 bytes)"}`
· `{"ok":false,"error":"invalid UTF-8 frame"}` · `{"ok":false,"error":"partial frame at EOF"}`. NEVER
echo the request bytes (a rejected frame may be garbage/binary). After `frame-too-large` the connection
CONTINUES at the NEXT real frame boundary (the resync drain guarantees this — verified: oversize+newline
then valid → exactly ONE error then the valid frame; two consecutive oversize frames → exactly two errors
then the valid frame; oversize-without-newline then EOF → one error then clean eof).

## 4. _handle (the compatible ordinary handler) — the edit

```python
def _handle(self, conn):
    reader = FrameReader(conn.recv)        # byte-bounded, handoff-preserving (P1.M1.T3.S1)
    try:
        wfile = conn.makefile("w", encoding="utf-8", newline="\n")
        try:
            while True:
                try:
                    raw = reader.read_frame_bytes()
                except FrameError as fe:
                    if fe.reason == "eof":
                        if fe.detail == "partial":   # bytes without a newline, then EOF
                            wfile.write(encode_line({"ok": False, "error": "partial frame at EOF"})); wfile.flush()
                        break                        # clean EOF: client closed — done
                    wfile.write(encode_line({"ok": False, "error": _frame_error_text(fe)})); wfile.flush()
                    continue
                try:
                    line = raw.decode("utf-8")
                except UnicodeDecodeError:
                    wfile.write(encode_line({"ok": False, "error": "invalid UTF-8 frame"})); wfile.flush()
                    continue
                response = self._dispatch(line.strip())   # unchanged: "" → malformed JSON (BUG-005)
                wfile.write(encode_line(response)); wfile.flush()
                if response.get("shutting_down"):
                    break
        finally: wfile.close()
    except OSError:
        pass  # client gone mid-frame; worker exits cleanly (existing behavior)
    finally:
        try: conn.close()
        except OSError: pass
```
Keep the existing `ControlServer` class docstring + `_handle` docstring updated (Mode A): framing =
32 KiB byte-bounded JSONL incl. newline; bounds enforced while reading; the three frame errors; no raw
echo; `reader.unread` is the native-handoff seam (T3.S3 consumes it).

## 5. Test plan (tests/test_editor_protocol.py NEW + test_control_socket.py additive)

All hermetic: `socket.socketpair()` for real recv semantics; partial reads via `sendall` splits; fake
clocks only if a deadline is added (this task adds NO read deadline — T3.S3's timers own that).

Codec (pure): encode_line round-trip incl. Unicode (ensure_ascii=False) + trailing `\n`; oversize
encode raises; exactly MAX_FRAME_BYTES-1 payload + `\n` == MAX passes; MAX payload (no room for `\n`) raises.
Reader (DETERMINISTIC FAKE-RECV — scripted exact chunks; NEVER a real socket for these): (a) partial reads —
frame split across 3 scripted recvs reassembles; (b) coalesced — two frames in ONE recv → two
read_frame_bytes calls + `unread` empty; (c) handoff — after frame 1, `unread` holds frame 2's exact bytes;
(d) oversize WITH newline then a valid frame → ONE error, then the valid frame (resync — the probe-caught
case); (d2) oversize coalesced with the next frame in ONE chunk → same; (e) oversize WITHOUT newline then
EOF → ONE error then clean eof; (f) EOF clean → eof(""); (g) EOF partial → eof("partial"); (h) recv raising
OSError → FrameError("io"); (i) exact boundary: payload MAX-1 + `\n` passes, payload MAX fails; (j) two
consecutive oversize frames → exactly two errors then the valid frame (lockstep); (k) all recv requests are
4096 (bounded reads, never unbounded). Fake clocks: NOT needed here (no deadline in this task — T3.S3's).
ControlServer._handle (SOCKETPAIR-level, in a thread — the existing `server` fixture also works): invalid
UTF-8 (`b"\xff\xfe{\n"`) → ONE `invalid UTF-8 frame` reply, connection continues; oversize → reply +
continue; partial EOF → one reply then close; all existing BUG-005/multi-line/quit tests green.

## 6. Scope

Files: CREATE `voice_typing/editor_protocol.py`; EDIT `voice_typing/daemon.py` (`_handle` body +
ControlServer/_handle docstrings); CREATE `tests/test_editor_protocol.py`; ADDITIVE section in
`tests/test_control_socket.py` if convenient (optional — the new module's tests can drive `_handle`
via socketpair directly). NOT: `_dispatch` (T2.S5 adds a route there — disjoint), any deadline/timer
(T3.S3), message validation/versioning (T3.S2), recovery caps (T5.S1). No live socket, no E2E.
