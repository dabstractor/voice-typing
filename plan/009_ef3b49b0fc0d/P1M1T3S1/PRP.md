# PRP — P1.M1.T3.S1: Bound control framing while reading bytes

## Goal

**Feature Goal**: Replace `ControlServer._handle`'s **unbounded text readline** (`conn.makefile("r", encoding="utf-8")` + `for line in rfile`) with a **byte-bounded strict-UTF-8 JSONL frame reader** that enforces the PRD §4.8.1 B wire limit — **32 KiB per frame including the newline, enforced WHILE reading, before unbounded buffering** — and preserves unread bytes for protocol handoff. Deliver a new `voice_typing/editor_protocol.py` holding `FrameReader` (bytes-only, recv-injectable, `unread` handoff buffer), `encode_line()` (the live/event encoder with the same bound), `FrameError` (a replyable, never-crashing error), and `MAX_FRAME_BYTES`; wire the reader at `ControlServer` ingress with **framed error replies and zero raw-request echo**; keep the ordinary one-shot/persistent lockstep (one reply per request line) and the BUG-005 empty-line error reply byte-compatible.

**Deliverable** (2 source files — 1 new, 1 edited — plus tests):
1. `voice_typing/editor_protocol.py` — **NEW**: `MAX_FRAME_BYTES = 32 * 1024`; `FrameError(reason, detail)`; `FrameReader(recv, *, max_bytes, chunk_size)` with `read_frame_bytes() -> bytes`, `unread` property, and the **resync drain** (`_drain_runaway`); `encode_line(obj) -> bytes`.
2. `voice_typing/daemon.py` — **EDIT** `ControlServer._handle` body (replace the makefile read loop with the reader; add UTF-8 strict decode + the three frame-error replies) + the `_handle`/`ControlServer` docstrings (Mode A: framing, bounds, error behavior, the handoff seam).
3. `tests/test_editor_protocol.py` — **NEW**: codec + reader cases via a **deterministic fake recv** + `_handle`-level cases via `socket.socketpair()`.
4. `tests/test_control_socket.py` — the existing BUG-005 / multi-line / quit / malformed tests stay green UNCHANGED (additive section optional).

**Success Definition**:
- (a) `FrameReader` never buffers more than `MAX_FRAME_BYTES` before raising: a frame of exactly `MAX-1` payload bytes + `\n` (== MAX) parses; a `MAX`-byte payload + `\n` raises `frame-too-large`; a runaway sender with NO newline raises once the next byte would exceed the cap — never after unbounded growth.
- (b) **Resync correctness (the probe-caught invariant):** after an oversize frame the reader consumes THROUGH its terminating newline, so the next `read_frame_bytes()` lands on a **real frame boundary** — exactly ONE error per bad request (no phantom empty frame → no second spurious reply). Verified for: oversize+`\n` then valid; oversize coalesced with the next frame in one chunk; two consecutive oversize frames then valid; oversize-without-newline then EOF (one error, then clean eof).
- (c) **Handoff preservation:** bytes after a frame's newline are kept in `unread` (never discarded) — `{"cmd":"editor-start",...}\n{"event":"applied",...}\n` in one recv → frame 1 returned, `unread == frame 2 bytes`; the next call re-arms from `unread` with no socket read.
- (d) **Strict UTF-8, never a crash:** invalid bytes (`b"\xff\xfe{\n"`) → ONE `{"ok":false,"error":"invalid UTF-8 frame"}` reply, connection continues; `recv` raising `OSError` → `FrameError("io")`; EOF clean → `eof("")`; EOF with buffered bytes → `eof("partial")` → one `partial frame at EOF` reply, then close.
- (e) **Lockstep preserved:** one reply per request line (valid, empty, malformed, oversize, invalid-UTF-8 alike); BUG-005's empty-line → `malformed JSON:` reply is byte-identical (it still flows through `_dispatch("")`); `quit` → reply then close; all existing `test_control_socket.py` tests green unmodified.
- (f) **No raw-request echo:** every frame-error reply carries a fixed reason string (+ bound) — never the offending bytes.
- (g) `encode_line` is the live/event encoder: `json.dumps(ensure_ascii=False).encode("utf-8") + b"\n"`, raising `FrameError("frame-too-large")` when the encoded line exceeds MAX.
- (h) **Hermetic tests only:** fake-recv for byte-level assertions (handoff/partial are TIMING-DEPENDENT over a real socketpair — observed flaky); `socketpair` only for `_handle`-level tests; fake clocks only if a deadline existed (none in this task — T3.S3 owns timers). No live listener, no E2E.
- (i) `git diff --name-only` == `{voice_typing/editor_protocol.py, voice_typing/daemon.py, tests/test_editor_protocol.py}` (+ `tests/test_control_socket.py` only if an additive section was added).

> **PROBE-VALIDATED (this PRP's research):** the complete `FrameReader` + `encode_line` implementation below was executed as a throwaway probe against 12 scenarios — partial reads across 3 chunks, coalesced frames, handoff, oversize+newline resync, oversize coalesced resync, two consecutive oversize, oversize-without-newline→EOF, clean/partial EOF, io error, exact MAX-1/MAX boundary, bounded 4096 recv sizes, Unicode — **all green**. The probe caught one real design flaw (the phantom-empty-frame lockstep violation fixed by `_drain_runaway`) and one test-harness hazard (socketpair timing) — both are baked into the PRP as CRITICAL gotchas.

## User Persona

**Target User**: the daemon maintainer + the downstream native-protocol implementers (P1.M1.T3.S2 validation, T3.S3 the owner connection pump/timers, T5.S1 the capped recovery reply). **Use Case**: a client (or a bug) sends a 100 MiB line, invalid UTF-8, or a partial frame then disconnects — today the server buffers without bound (or dies on `UnicodeDecodeError`, which is NOT an `OSError` and so escapes `_handle`'s only except). After: a bounded, framed error reply and the worker survives. **Pain Points Addressed**: the §4.8.1 B mandate "enforce byte limits while reading, before unbounded buffering" is currently unmet; and a native owner pump could never take over a connection because `makefile` swallows coalesced follow-up frames.

## Why

- **PRD §4.8.1 B is normative** (PRD.md:448-450): "UTF-8 newline-delimited JSON objects, with a 32 KiB wire limit per request and live event (including newline); enforce byte limits while reading, before unbounded buffering, and reject invalid UTF-8, malformed frames, invalid types, oversized fields, or unsupported protocol before arming." This task delivers the framing half (types/fields/versioning are T3.S2's).
- **Three concrete hazards in the current ingress** (daemon.py:3386-3438): (1) `for line in rfile` buffers without any byte cap — a newline-less client grows memory forever; (2) `makefile(encoding="utf-8")` raises `UnicodeDecodeError` (a `ValueError`) out of the iterator — `_handle` catches only `OSError`, so the worker thread dies silently with NO reply to the client; (3) `makefile`'s internal buffer consumes any coalesced bytes past the newline — the protocol handoff T3.S3 needs is impossible.
- **Lockstep is the contract the existing tests pin** (`test_round_trip_empty_line_mid_connection`: valid, empty, valid → exactly 3 replies). A naive oversize handling that just drops the buffer would emit TWO replies for ONE bad request — the probe demonstrated this; the resync drain is the fix and is asserted.
- **The reader is bytes-only + recv-injectable by design.** Byte caps can only be enforced on raw bytes before decode; strict decode lives in the handler so a decode failure never corrupts the handoff buffer; `recv` injection makes every byte-level case deterministic and hermetic (no live socket).
- **Scope discipline.** Only the ingress read path + codec. NOT: `_dispatch` (T2.S5, in flight, adds a `start-context` route there — disjoint; its PRP explicitly leaves `_handle` untouched), message validation/versioning (T3.S2), timers/deadlines (T3.S3), the recovery output cap (T5.S1), the 0700/0600 socket permissions (unchanged).

## What

Create `voice_typing/editor_protocol.py` (verbatim in the Blueprint), rewrite `ControlServer._handle`'s read loop on top of it with the three framed error replies, update the two docstrings (Mode A), and add `tests/test_editor_protocol.py`. No dispatch, permission, or protocol-semantics change.

### Success Criteria

- [ ] `voice_typing/editor_protocol.py` exists with `MAX_FRAME_BYTES`, `FrameError`, `FrameReader` (`read_frame_bytes`, `unread`, `_drain_runaway`), `encode_line` — verbatim per the Blueprint.
- [ ] `ControlServer._handle` uses `FrameReader(conn.recv)`; no `makefile("r")` read remains; the write path (`json` line + flush; `shutting_down` → break) unchanged.
- [ ] Frame-error replies are exactly: `frame too large (max 32768 bytes)`, `invalid UTF-8 frame`, `partial frame at EOF` — each ONE per offending frame; nothing echoes the request bytes.
- [ ] Resync invariant (b), handoff invariant (c), strict-UTF-8/EOF/io behavior (d) all asserted in `tests/test_editor_protocol.py` with a deterministic fake recv.
- [ ] All pre-existing `tests/test_control_socket.py` tests pass UNMODIFIED (BUG-005 lockstep included).
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_editor_protocol.py tests/test_control_socket.py -q` → 0 failures; `tests/test_daemon.py` shows no NEW failure names vs `tests/G1_BASELINE.md`'s CPU addendum (the 20-name set-diff rule).
- [ ] `git diff --name-only` ⊆ the four files in Success Definition (i).

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim, probe-validated implementation of every new symbol is given; the exact `_handle` text being replaced and its replacement are given; the PRD framing clause is cited by line; the existing test shapes that must stay green are enumerated; the two probe-caught hazards (resync, socketpair timing) are documented with their fixes; the parallel sibling's file boundaries are verified disjoint. Pure stdlib (`json`, `socket`); no CUDA/daemon/live socket.

### Documentation & References

```yaml
# MUST READ — the probe-validated algorithm, the resync fix, the harness lesson, the full test plan (this task's own research)
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S1/research/bounded_framing_design.md
  why: "§1 the three concrete hazards in the current _handle (unbounded buffering; UnicodeDecodeError is a
        ValueError that escapes `except OSError` and kills the worker with NO reply; makefile swallows
        coalesced frames). §2 the PRD clause. §3 the FrameReader algorithm WITH the _drain_runaway resync
        (the probe-caught lockstep fix) + the FrameError reason codes + why decode lives in the handler.
        §4 the verbatim new _handle. §5 the full test plan (fake-recv for byte-level; socketpair for
        handler-level). §6 scope."
  critical: "§3's _drain_runaway is load-bearing: a naive 'drop the buffer' on oversize leaves the runaway
            frame's tail + newline unread; the next read then returns a PHANTOM EMPTY frame -> a second,
            spurious malformed-JSON reply (two replies for one bad request). §5's harness rule is equally
            load-bearing: handoff assertions over a real socketpair are TIMING-DEPENDENT (three sendalls may
            coalesce into one recv) — byte-level tests MUST use the scripted fake recv."

# THE SPEC — PRD §4.8.1 B (the framing contract)
- file: PRD.md
  why: "Lines 448-450: 'UTF-8 newline-delimited JSON objects, with a 32 KiB wire limit per request and live
        event (including newline); enforce byte limits while reading, before unbounded buffering, and reject
        invalid UTF-8, malformed frames ... Keep existing one-request commands and status/recovery behavior
        backward-compatible outside native mode.' Line 575 (T10a) names the cases: '4 KiB/32 KiB boundaries,
        invalid UTF-8 and JSON, split/coalesced frames and partial EOF.'"
  critical: "INCLUDING newline is the bound semantics (payload MAX-1 + '\n' == MAX passes). 'Before unbounded
            buffering' is why the cap is checked on raw bytes per recv, not after a full readline."

# THE EDIT SITE — ControlServer._handle + its docstrings
- file: voice_typing/daemon.py
  why: "_handle :3386-3438 (verbatim in research §1) is the ONLY code to replace; _dispatch :3440+ stays the
        validator/dispatcher (BUG-005: '' -> malformed JSON reply); the ControlServer class docstring
        (protocol block) and _handle's docstring get the Mode A framing lines."
  pattern: "Keep the write side exactly: wfile.write(json line + '\\n'); wfile.flush(); if
            response.get('shutting_down'): break. Keep the outer `except OSError: pass` + the conn.close()
            finally. Only the READ side changes."
  gotcha: "Do NOT touch _dispatch (T2.S5 is adding a start-context route there in parallel). Do NOT add a
           read deadline/timer (T3.S3). Do NOT change the 0700/0600 permission code. UnicodeDecodeError must
           be caught explicitly — it is a ValueError, NOT an OSError."

# THE SIBLING CLIENT READER (the repo's existing bounded-read idiom to mirror in spirit)
- file: voice_typing/ctl.py
  why: ":244-275 send_command: `sock.settimeout`, `buf = bytearray()`, `while b'\\n' not in buf: chunk =
        sock.recv(4096) ...` — the client-side precedent for bounded 4096-byte recv loops and the
        'makefile ignores settimeout' hazard this module's docstrings already name. Match the 4096 chunk
        size and the bytearray-accumulate style."
  pattern: "4096-byte recv chunks into a bytearray; find(b'\\n'); split at the first newline."
  gotcha: "The client is one-shot; the server reader must additionally (1) cap total bytes, (2) resync after
           oversize, (3) expose `unread` for handoff — none of which ctl.py needs."

# THE EXISTING TESTS THAT MUST STAY GREEN (read-only reference)
- file: tests/test_control_socket.py
  why: "test_dispatch_malformed_json (:187), test_dispatch_empty_line (:192), test_dispatch_non_dict_json
        (:201), test_round_trip_malformed_over_wire (:221), test_round_trip_multi_line_one_connection (:227),
        test_round_trip_empty_line_gets_error_reply (:235), test_round_trip_empty_line_mid_connection (:247),
        test_round_trip_quit (:271), plus the `server` fixture (:~62-125) whose _send/_send_lines helpers
        BLOCK until a reply line (they double as hang repros)."
  critical: "Run the file UNMODIFIED after the _handle rewrite. If any flips red, the rewrite broke lockstep
            or an error-string prefix (`malformed JSON:`) — fix the rewrite, never the tests."

# THE PARALLEL SIBLING — disjoint
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S5/PRP.md
  why: "T2.S5 (implementing) edits daemon.py (_start_fenced, start_context, a start-context route in
        _dispatch, protocol docstring lines) + ctl.py + 3 test files. Its scope guard states `_handle` is
        NOT touched. This task edits _handle + creates a new module + a new test file."
  critical: "Both tasks edit daemon.py but in DISJOINT regions (_handle vs _dispatch/start_context). Merge
            order does not matter. Do NOT edit _dispatch or the start-context code here."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py                 # ControlServer :3260; _handle :3386-3438 (the unbounded makefile loop — EDIT);
│                             # _dispatch :3440+ (T2.S5's route lands here — DO NOT TOUCH).
│                             # NO editor_protocol.py exists yet.
├── ctl.py                    # send_command :244-275 — the client-side bounded-recv idiom (reference).
└── pi_editor.py              # another JSONL peer (recv(4096) + json.loads(raw.decode("utf-8")) :298-320) — reference.
tests/
├── test_control_socket.py    # the existing suite that MUST stay green unmodified.
└── (no test_editor_protocol.py yet)
```

### Desired Codebase tree with files to be added

```bash
voice_typing/editor_protocol.py    # CREATE: MAX_FRAME_BYTES, FrameError, FrameReader (read_frame_bytes/unread/_drain_runaway), encode_line.
voice_typing/daemon.py             # EDIT: ControlServer._handle body (+ its docstring + the class protocol docstring).
tests/test_editor_protocol.py      # CREATE: codec + reader (fake recv) + _handle (socketpair) cases.
tests/test_control_socket.py       # UNCHANGED (or an additive section only — optional).
# Nothing else. No _dispatch, config, ctl.py, recorder_host, or permission changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — RESYNC AFTER OVERSIZE (the probe-caught lockstep bug). When a frame exceeds the cap, its
# terminating '\n' is usually STILL UNREAD in the socket (recv chunks are 4096; the cap trip happens mid-
# chunk). If you merely drop the buffer and raise, the next read sees the stray '\n' -> returns b"" ->
# the handler dispatches "" -> a SECOND, spurious "malformed JSON" reply. TWO replies for ONE bad request
# breaks the one-reply-per-line lockstep the existing tests pin. FIX: _drain_runaway keeps recv'ing until
# it consumes THROUGH the offending newline, then hands the bytes after it to `unread`. Asserted for
# oversize+nl, oversize coalesced with the next frame, and two consecutive oversize frames.

# CRITICAL #2 — UnicodeDecodeError IS A ValueError, NOT AN OSError. The current `_handle` only catches
# OSError, so invalid UTF-8 from makefile(encoding="utf-8") would kill the worker thread with NO reply.
# The new handler catches UnicodeDecodeError explicitly and replies `invalid UTF-8 frame`, then CONTINUES.

# CRITICAL #3 — BYTE-LEVEL TESTS USE A FAKE recv, NOT socketpair. The handoff assertion `unread ==
# <exact bytes>` depends on how many sendalls coalesced into one recv — timing-dependent over a real
# socketpair (observed flipping between two probe runs). Script exact chunks with an in-memory fake
# (`FakeSock(*chunks)` whose recv pops the next chunk, b"" at exhaustion). Reserve socketpair for the
# _handle-level tests where you only assert REPLY CONTENT/COUNT, never intermediate buffers.

# CRITICAL #4 — THE BOUND IS "INCLUDING NEWLINE". len(frame) + 1 > MAX_FRAME_BYTES raises. So payload
# MAX-1 + '\n' (== MAX total) PASSES; payload MAX + '\n' FAILS. The no-newline trip is `len(buf) + 1 >
# max_bytes` (the NEXT byte would exceed) — checked BEFORE each recv so the buffer never exceeds the cap.

# CRITICAL #5 — WRITE FIXTURES FROM THE REAL FRAME. The probe's one spurious failure was a fixture typo
# (b'pus"}' where 'stop"}' needs b'p"}'). Build split-chunk fixtures by SLICING a real frame
# (frame[:10], frame[10:20], ...) rather than hand-typing fragments.

# CRITICAL #6 — DECODE LIVES IN THE HANDLER, NOT THE READER. The reader is bytes-only so `unread` is never
# corrupted by a decode error and the same reader serves the native handoff (T3.S3). A frame that fails
# strict decode was still fully consumed (its newline eaten) — the handler replies and CONTINUES; the next
# frame is independent.

# CRITICAL #7 — NO RAW-REQUEST ECHO. A rejected frame may be binary garbage or a 32 KiB blob; error replies
# carry ONLY the fixed reason (+ the bound). Never include frame bytes in an error string or a log line.

# GOTCHA #8 — `_dispatch(line.strip())` IS UNCHANGED. The empty line still reaches _dispatch as "" and gets
# the existing `malformed JSON:` reply (BUG-005). Do NOT special-case empties in the handler — that would
# change the error text the existing tests pin (`startswith("malformed JSON:")`).

# GOTCHA #9 — NO DEADLINE IN THIS TASK. The reader blocks on recv exactly as before (the control socket has
# no server-side read timeout by design; clients bound themselves with VOICECTL_TIMEOUT). T3.S3 adds the
# owner-pump timers. Do NOT add settimeout/fake-clock plumbing here.

# GOTCHA #10 — FULL PATHS + two timeouts: `timeout 300 .venv/bin/python -m pytest ...` (bash-tool ≥ 360).
# test_daemon.py: bounded `timeout 500`, compare FAILED NAMES against tests/G1_BASELINE.md's CPU addendum
# (20 legacy names) — no NEW names. pytest only (no ruff/mypy configured). Never bare python/pytest.

# GOTCHA #11 — T2.S5 IS EDITING daemon.py IN PARALLEL (disjoint regions). If `git status` shows daemon.py
# already modified by it, apply this task's _handle edit on top (non-overlapping text). Re-run both suites.
```

## Implementation Blueprint

### Data models and structure

No ORM/pydantic. The "model" is: one module constant (`MAX_FRAME_BYTES: int = 32 * 1024`), one exception
(`FrameError` with `reason: str` ∈ {"invalid-utf8" is handler-level; reader reasons: "frame-too-large",
"eof", "io"} and `detail: str`), one class (`FrameReader` with `__init__(recv, *, max_bytes, chunk_size)`,
`read_frame_bytes() -> bytes`, `unread -> bytes`), one function (`encode_line(obj: dict) -> bytes`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/editor_protocol.py (verbatim — PROBE-VALIDATED, research §3)
  - CONTENT:
    """Byte-bounded strict-UTF-8 JSONL framing for the owner-only control socket (PRD §4.8.1 B).

    MAX_FRAME_BYTES is the wire limit PER FRAME INCLUDING the terminating newline (32 KiB). FrameReader
    enforces it WHILE READING raw bytes (before any unbounded buffering) over an injectable recv(), keeps
    bytes past a frame's newline in `unread` so a later protocol (the native owner pump) can take the
    connection over without losing coalesced frames, and RESYNCS after an oversized frame by consuming
    through its newline (one error per bad request — the one-reply-per-line lockstep). Strict UTF-8
    decoding is the HANDLER's job (daemon.ControlServer._handle): this module is bytes-only so a decode
    failure never corrupts the handoff buffer. encode_line() is the live/event encoder with the same bound.
    Errors are replyable (FrameError carries a stable reason) — never a crash, never a raw-request echo.
    Pure stdlib (json). No sockets are opened here; tests inject recv.
    """
    from __future__ import annotations
    import json
    from collections.abc import Callable

    MAX_FRAME_BYTES: int = 32 * 1024   # PRD §4.8.1 B: per request and live event, INCLUDING newline

    class FrameError(Exception):
        """A framed, replyable protocol error. `reason` is a stable code; `detail` is short, never raw bytes."""

        def __init__(self, reason: str, detail: str = "") -> None:
            super().__init__(reason)
            self.reason = reason
            self.detail = detail

    class FrameReader:
        """Bytes-only JSONL frame reader: byte-bounded while reading; preserves post-newline bytes."""

        def __init__(
            self,
            recv: Callable[[int], bytes],
            *,
            max_bytes: int = MAX_FRAME_BYTES,
            chunk_size: int = 4096,
        ) -> None:
            self._recv = recv
            self._max = int(max_bytes)
            self._chunk = int(chunk_size)
            self._unread = b""   # bytes after the last consumed newline — the protocol-handoff seam

        @property
        def unread(self) -> bytes:
            return self._unread

        def read_frame_bytes(self) -> bytes:
            """Return one frame (sans newline). Raises FrameError; never buffers past the cap."""
            buf = bytearray(self._unread)
            self._unread = b""
            while True:
                i = buf.find(b"\n")
                if i != -1:
                    frame = bytes(buf[:i])
                    self._unread = bytes(buf[i + 1 :])   # resynced: the buffer already sits past this frame
                    if len(frame) + 1 > self._max:       # INCLUDING the newline
                        raise FrameError("frame-too-large")
                    return frame
                if len(buf) + 1 > self._max:             # no newline yet; the NEXT byte would exceed the cap
                    self._drain_runaway(buf)             # resync THROUGH the offending newline
                    raise FrameError("frame-too-large")
                try:
                    chunk = self._recv(self._chunk)
                except OSError as exc:
                    raise FrameError("io", str(exc)) from exc
                if not chunk:
                    raise FrameError("eof", "partial" if buf else "")
                buf += chunk

        def _drain_runaway(self, buf: bytearray) -> None:
            """Consume an oversized frame through its newline so the next read starts at a real boundary.

            Without this, the runaway frame's tail + newline stay unread and the next read returns a
            PHANTOM EMPTY frame -> a second, spurious reply (two replies for one bad request).
            """
            while True:
                i = buf.find(b"\n")
                if i != -1:
                    self._unread = bytes(buf[i + 1 :])
                    return
                try:
                    chunk = self._recv(self._chunk)
                except OSError:
                    self._unread = b""
                    return
                if not chunk:                            # EOF mid-runaway: nothing to resync to
                    self._unread = b""
                    return
                buf += chunk

    def encode_line(obj: dict) -> bytes:
        """Encode one reply/event as ONE UTF-8 JSON line (ensure_ascii=False) + '\\n'. Bounded by MAX_FRAME_BYTES."""
        line = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(line) > MAX_FRAME_BYTES:
            raise FrameError("frame-too-large")
        return line

  - DO NOT: decode inside FrameReader; add settimeout/deadlines; log frame bytes; change chunk semantics.

Task 2: EDIT voice_typing/daemon.py — ControlServer._handle (verbatim replacement) + docstrings
  - ADD the import next to the module's other voice_typing imports: `from voice_typing.editor_protocol import
    FrameError, FrameReader, encode_line` (keep import purity: editor_protocol is stdlib-only).
  - REPLACE the read loop (the body between `rfile = wfile = None` and the outer `except OSError`) with:
        reader = FrameReader(conn.recv)   # byte-bounded (32 KiB incl. newline); preserves unread for handoff
        wfile = None
        try:
            wfile = conn.makefile("w", encoding="utf-8", newline="\n")
            while True:
                try:
                    raw = reader.read_frame_bytes()
                except FrameError as fe:
                    if fe.reason == "eof":
                        if fe.detail == "partial":       # bytes without a newline, then EOF
                            wfile.write(encode_line({"ok": False, "error": "partial frame at EOF"}))
                            wfile.flush()
                        break                            # clean EOF: client closed — done
                    if fe.reason == "frame-too-large":
                        text = f"frame too large (max {MAX_FRAME_BYTES} bytes)"
                    else:                                 # "io": recv failed — nothing more to read
                        break
                    wfile.write(encode_line({"ok": False, "error": text}))   # no raw echo
                    wfile.flush()
                    continue                             # lockstep: one reply per bad frame, then resynced
                try:
                    line = raw.decode("utf-8")           # strict; never errors="replace"
                except UnicodeDecodeError:
                    wfile.write(encode_line({"ok": False, "error": "invalid UTF-8 frame"}))
                    wfile.flush()
                    continue
                response = self._dispatch(line.strip())  # "" still -> malformed JSON (BUG-005, unchanged)
                wfile.write(encode_line(response))
                wfile.flush()                            # CRITICAL: makefile("w") buffers; flush every reply
                if response.get("shutting_down"):
                    break                                # quit -> reply sent, then close this connection
        except OSError:
            pass  # client gone mid-frame; worker exits cleanly
        finally:
            if wfile is not None:
                try: wfile.close()
                except OSError: pass
            try: conn.close()
            except OSError: pass
    (import MAX_FRAME_BYTES too, or reference editor_protocol.MAX_FRAME_BYTES).
  - DOCSTRINGS (Mode A): _handle — "Reads via editor_protocol.FrameReader: 32 KiB byte bound per frame
    INCLUDING newline, enforced while reading (before unbounded buffering); oversized -> ONE 'frame too
    large (max 32768 bytes)' reply then resync at the next frame boundary; invalid UTF-8 -> ONE 'invalid
    UTF-8 frame' reply, connection continues; partial frame at EOF -> ONE reply then close; no raw request
    echo; reader.unread preserves coalesced bytes for the native protocol handoff (P1.M1.T3.S3)." Add the
    same framing/bounds/error summary to the ControlServer class protocol docstring.
  - DO NOT: touch _dispatch, the permission code, or add timers.

Task 3: CREATE tests/test_editor_protocol.py (hermetic — fake recv for bytes; socketpair for _handle)
  - Header: "NO live socket listener, NO CUDA. Byte-level cases use a scripted fake recv (handoff assertions
    are timing-dependent over a real socketpair); _handle cases use socket.socketpair(). Run: timeout 120
    .venv/bin/python -m pytest tests/test_editor_protocol.py -q".
  - HARNESS:
        class FakeSock:
            """Scripted recv: pops one chunk per call, b'' once exhausted (EOF). Records requested sizes."""
            def __init__(self, *chunks: bytes) -> None:
                self._chunks = list(chunks); self.calls: list[int] = []
            def recv(self, n: int) -> bytes:
                self.calls.append(n)
                return self._chunks.pop(0) if self._chunks else b""

    and build split fixtures by SLICING real frames at deliberate boundaries (Gotcha #5 — slice from the
    real frame; the fake returns chunks VERBATIM regardless of n, so a slice that lands mid-frame-2 leaves
    exactly those post-newline bytes in `unread`, which IS the handoff case — assert against that):
        f1 = b'{"cmd":"stop"}\n'; f2 = b'{"cmd":"status"}\n'
        FakeSock(f1[:10], f1[10:14], f1[14:] + f2)     # frame 1 split twice; its tail + ALL of frame 2 in one recv
        # -> read_frame_bytes() == b'{"cmd":"stop"}'; unread == f2; next read == frame 2; unread == b""
  - READER/CODEC TESTS (assert exact values):
        test_encode_line_round_trips_unicode_and_appends_newline   # ensure_ascii=False; endswith b"\n"; json.loads round-trip
        test_encode_line_rejects_oversize                          # {"x": "y"*MAX} -> FrameError("frame-too-large")
        test_reader_partial_reads_reassemble                        # f1 split across 2 recvs -> b'{"cmd":"stop"}'
        test_reader_preserves_unread_for_handoff                   # after frame 1: unread == f2 (frame 2 IN FULL); next read == frame 2, unread == b""
        test_reader_coalesced_frames_in_one_recv                   # one chunk with 2 frames -> 2 reads, no extra recv
        test_reader_recv_requests_are_bounded                      # all FakeSock.calls == 4096
        test_reader_exact_boundary_passes                          # payload MAX-1 + b"\n" -> returned, len == MAX-1
        test_reader_max_payload_fails                              # b"x"*MAX + b"\n" -> FrameError("frame-too-large")
        test_reader_oversize_with_newline_resyncs_then_next_frame  # ONE error, then b'{"cmd":"ok"}' (CRITICAL #1)
        test_reader_oversize_coalesced_with_next_frame_resyncs     # b"x"*(MAX+10)+b"\n{"cmd":"ok"}\n" in ONE chunk -> error then ok
        test_reader_two_oversize_frames_then_valid_lockstep        # exactly 2 errors then the valid frame
        test_reader_oversize_without_newline_then_eof              # b"x"*40960 -> error, then eof("")
        test_reader_eof_clean / test_reader_eof_partial            # eof("") / eof("partial")
        test_reader_recv_oserror_is_frame_error_io
  - HANDLER TESTS (socketpair; drive `ControlServer._handle` in a daemon thread with a _StubDaemon from
    test_control_socket's shape — or import it):
        test_handle_invalid_utf8_gets_one_reply_and_continues      # send b"\xff\xfe{\n" + a valid status line -> replies[0] error=="invalid UTF-8 frame"; replies[1] ok
        test_handle_oversize_gets_one_reply_then_resyncs           # b"x"*(MAX+1)+b"\n" + valid -> exactly 1 error reply then the valid reply (count == 2)
        test_handle_partial_eof_gets_one_reply_then_closes         # send b'{"partial"' + SHUT_WR -> one "partial frame at EOF" reply then EOF
        test_handle_error_replies_never_echo_request_bytes         # the oversize/invalid payloads' bytes absent from every reply
        test_handle_quit_replies_then_closes (parity with the existing suite)
  - DO NOT: use a live listening socket; add real clocks; modify existing tests.

Task 4: VALIDATE (L1–L4). If committing: "P1.M1.T3.S1: byte-bounded JSONL framing at ControlServer ingress
  (editor_protocol.FrameReader/encode_line; 32 KiB incl. newline; resync; handoff buffer; framed errors)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the bound is checked on RAW BYTES before each recv (never after a full readline):
if len(buf) + 1 > self._max:        # the next byte would exceed the cap and there is still no newline
    self._drain_runaway(buf)        # resync THROUGH the offending newline (CRITICAL #1)
    raise FrameError("frame-too-large")

# PATTERN 2 — handoff: bytes after the newline are preserved, and the next read re-arms from them:
self._unread = bytes(buf[i + 1:])   # set when a frame is returned
buf = bytearray(self._unread); self._unread = b""   # re-arm at the top of read_frame_bytes

# PATTERN 3 — the handler's reply discipline: one reply per frame, then continue; never echo bytes:
except FrameError as fe:
    if fe.reason == "eof": ... break
    wfile.write(encode_line({"ok": False, "error": text})); wfile.flush(); continue
except UnicodeDecodeError:
    wfile.write(encode_line({"ok": False, "error": "invalid UTF-8 frame"})); wfile.flush(); continue
response = self._dispatch(line.strip())   # "" -> malformed JSON (BUG-005) — UNCHANGED
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (the contract's OUTPUT):
  - P1.M1.T3.S2 (versioned message validation + shared vectors): validates the DICT the handler parsed;
    consumes FrameError reason codes + encode_line for its vectors (4 KiB/32 KiB boundaries, invalid UTF-8,
    split/coalesced frames, partial EOF — exactly this task's cases).
  - P1.M1.T3.S3 (owner connection pump + timers): takes over a connection via reader.unread (the handoff
    seam) and adds deadlines AROUND FrameReader (the reader itself stays deadline-free — Gotcha #9).
  - P1.M1.T5.S1 (capped recovery reply): uses encode_line's bound (raises on oversize — it must chunk/cap).
PARALLEL — P1.M1.T2.S5 (implementing): edits daemon.py's _dispatch/start_context + ctl.py — DISJOINT
  regions from _handle. Merge order irrelevant.
UPSTREAM — the existing ControlServer permissions (0700 dir / 0600 socket) and the write path: UNCHANGED.
```

## Validation Loop

> Full paths; two timeouts on every pytest (inner `timeout`, bash-tool ≥ +60). pytest only (no ruff/mypy).
> No live socket listener is ever opened by the new tests (socketpair only).

### Level 1: The edits landed

```bash
cd /home/dustin/projects/voice-typing
test -f voice_typing/editor_protocol.py && grep -c 'MAX_FRAME_BYTES\|class FrameError\|class FrameReader\|def encode_line\|_drain_runaway' voice_typing/editor_protocol.py   # >= 5
grep -n 'makefile("r"' voice_typing/daemon.py | grep -v ctl || echo "L1 PASS: no unbounded makefile read loop remains in daemon.py"
grep -n 'FrameReader(conn.recv)' voice_typing/daemon.py
.venv/bin/python -m py_compile voice_typing/editor_protocol.py voice_typing/daemon.py && echo "L1 PASS: compiles"
.venv/bin/python -c "import voice_typing.editor_protocol as ep; print(ep.MAX_FRAME_BYTES == 32768)"
```

### Level 2: The new tests + the existing control-socket suite

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_editor_protocol.py -q 2>&1 | tail -3
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py -q 2>&1 | tail -3
# Expected: both green. The control-socket suite UNMODIFIED proves lockstep + BUG-005 parity.
```

### Level 3: The behavioral proof (hermetic, inline — no files)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python - <<'PY'
from voice_typing.editor_protocol import FrameReader, FrameError, encode_line, MAX_FRAME_BYTES
class FS:
    def __init__(self,*c): self.c=list(c)
    def recv(self,n): return self.c.pop(0) if self.c else b""
f1=b'{"cmd":"stop"}\n'; f2=b'{"cmd":"status"}\n'
r=FrameReader(FS(f1[:10],f1[10:14],f1[14:]+f2).recv)   # f1 split across 2 recvs; f1's tail coalesced with ALL of f2
assert r.read_frame_bytes()==b'{"cmd":"stop"}' and r.unread==f2   # frame 2 preserved in full (handoff)
assert r.read_frame_bytes()==b'{"cmd":"status"}' and r.unread==b""
r=FrameReader(FS(b"x"*(MAX_FRAME_BYTES+1)+b"\n"+b'{"cmd":"ok"}\n').recv)
try: r.read_frame_bytes(); raise SystemExit("FAIL")
except FrameError as e: assert e.reason=="frame-too-large"
assert r.read_frame_bytes()==b'{"cmd":"ok"}'                    # resync (CRITICAL #1)
r=FrameReader(FS(b"x"*40960).recv)
try: r.read_frame_bytes()
except FrameError as e: assert e.reason=="frame-too-large"
try: r.read_frame_bytes()
except FrameError as e: assert e.reason=="eof" and e.detail==""
assert encode_line({"ok":True,"u":"héllo"})==b'{"ok": true, "u": "h\xc3\xa9llo"}\n'
print("L3 PASS: handoff, resync, oversize->eof, encoder")
PY
```

### Level 4: No daemon regression + scope guards

```bash
cd /home/dustin/projects/voice-typing
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | grep '^FAILED' | sed 's/FAILED //;s/ - .*//' | sort > /tmp/vt_daemon_after.txt
# Compare against tests/G1_BASELINE.md's CPU-addendum 20-name list: NO new names (the set-diff rule).
git diff --name-only   # ⊆ {editor_protocol.py (new), daemon.py, test_editor_protocol.py (new), test_control_socket.py?}
git diff --exit-code -- voice_typing/ctl.py voice_typing/config.py voice_typing/recorder_host.py config.toml && echo "L4 PASS: out-of-scope files untouched" || echo "L4 NOTE: ctl.py may be T2.S5's parallel edit — not this task's"
grep -c 'settimeout\|time.monotonic' voice_typing/editor_protocol.py   # 0 — no deadline in this task (Gotcha #9)
rm -f /tmp/vt_daemon_after.txt
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 editor_protocol.py present; no `makefile("r")` read loop remains; `FrameReader(conn.recv)` at ingress; compiles.
- [ ] L2 new tests + the UNMODIFIED control-socket suite green.
- [ ] L3 inline proof: handoff preserved; oversize resync; oversize→eof; encoder Unicode + bound.
- [ ] L4 test_daemon.py failure NAMES == the G1 CPU-addendum set (no new names); diff ⊆ the four files; no timers added.

### Feature Validation
- [ ] 32 KiB bound INCLUDING newline enforced while reading (exact boundary both sides asserted).
- [ ] Resync invariant: exactly one error per oversize frame, next read lands on a real frame (3 scenarios).
- [ ] Handoff: `unread` preserves coalesced bytes; next read re-arms without a socket read.
- [ ] Strict UTF-8 → one framed reply + continue; partial EOF → one reply then close; io → handled; clean EOF → close.
- [ ] Lockstep + BUG-005 empty-line `malformed JSON:` reply byte-identical; quit parity.

### Code Quality / Scope Validation
- [ ] Reader is bytes-only; decode in the handler; no raw-request echo anywhere (replies or logs).
- [ ] No `_dispatch`, permission, timer, or validation changes (T2.S5/T3.S2/T3.S3 own those).
- [ ] Tests hermetic: fake recv for byte-level; socketpair for handler-level; fixtures sliced from real frames.

### Documentation & Deployment
- [ ] Mode A: `_handle` + `ControlServer` docstrings state framing, the bound (incl. newline), the three error replies, and the handoff seam.

---

## Anti-Patterns to Avoid

- ❌ Don't handle oversize by just dropping the buffer — the stray newline yields a phantom empty frame and a second spurious reply (lockstep violation). Use the resync drain. (CRITICAL #1.)
- ❌ Don't rely on `except OSError` for decode failures — `UnicodeDecodeError` is a `ValueError`; catch it explicitly and reply. (CRITICAL #2.)
- ❌ Don't assert exact `unread` contents over a real socketpair — kernel coalescing makes it timing-dependent (observed flaky). Use the scripted fake recv. (CRITICAL #3.)
- ❌ Don't check the bound AFTER a full readline or excluding the newline — check raw bytes before each recv, `len(frame) + 1 > MAX`. (CRITICAL #4.)
- ❌ Don't hand-type split-chunk fixtures — slice a real frame. (CRITICAL #5.)
- ❌ Don't decode inside the reader (corrupts `unread` on failure; breaks the handoff seam). (CRITICAL #6.)
- ❌ Don't echo request bytes in errors/logs; don't special-case empty lines in the handler (BUG-005 text is pinned). (Gotchas #7/#8.)
- ❌ Don't add `settimeout`/deadlines/fake clocks (T3.S3) or touch `_dispatch`/permissions (T2.S5). (Gotchas #9/#11.)
- ❌ Don't run pytest without both timeouts; don't invent ruff/mypy gates; don't modify existing tests to pass.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The complete implementation was **executed as a throwaway probe against 12 scenarios and passed** — the PRP's code is a transcription of proven code, not a design sketch. The probe surfaced two non-obvious hazards (the phantom-empty-frame lockstep violation → the resync drain; socketpair timing flakiness → the fake-recv harness rule) that a from-scratch implementation would most likely have shipped as latent bugs; both are now CRITICAL gotchas with asserted fixes. The `_handle` replacement preserves the write path and `_dispatch("")` exactly, so the existing lockstep/BUG-005 tests are the regression gate. The −0.5 is merge friction with T2.S5's parallel daemon.py edits (disjoint regions, explicitly scoped) and the inherent chance a reviewer re-introduces the naive drop — which the three resync tests catch immediately.
