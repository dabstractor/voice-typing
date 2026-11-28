# PRP — P1.M1.T3.S3: Build the owner connection pump and timers

## Goal

**Feature Goal**: Give the native v1 owner connection its **transport**: a pump that, once a connection
has been handed to it (after the first `editor-start` frame is accepted), owns exactly two threads — a
**reader** that keeps servicing `ping` / `applied` / `stop` / `cancel` / `lost` / EOF on the owner's
socket while the session is busy (cold load, drain, a blocked write), and a **single serialized writer**
that pushes encoded event lines under a **whole-frame 2 s write cap** — plus the **2 s ping / 6 s lease
contract** (lease enforced here; ping cadence exported as the client reference) and one **sticky loss
signal** on EOF, framing, write, request and lease errors. All deadlines are **absolute monotonic**
values over an injectable clock and timer source, so every race is tested with barriers and a fake
event source instead of sleeps. The pump is a **disconnected transport**: it exposes event/loss/command
hooks and never imports the daemon — P1.M1.T4.S7 activates it on `ControlServer._handle`.

**Deliverable** (1 source file appended — S1/S2's module; 1 test file created):
1. `voice_typing/editor_protocol.py` — **APPEND** below S2's section (never touch S1's framing or S2's
   validation symbols): constants `PING_INTERVAL_S=2.0`, `LEASE_S=6.0`, `WRITE_CAP_S=2.0`,
   `START_CAP_S=30.0`, `ACK_DEADLINE_S=5.0`, `OUTBOUND_QUEUE_MAX=64`; `deadline_after`, `remaining`;
   `LossCause` (+ `.end_reason`); `PumpClosed`; `send_line_capped`; `ThreadTimers`; `write_reject`;
   `OwnerPump` (`start`, `send_event`, `shutdown`, `wait`, `lost`, `loss_cause`, `loss_detail`, `closed`,
   `last_ping_at`, `lease_deadline`). Mode A docstrings: thread ownership, absolute deadlines, the
   terminal callback contract.
2. `tests/test_editor_pump.py` — **NEW**, hermetic: a duck-typed `FakeConn` (scripted recv/send,
   `dup()` twin), `FakeClock`, `ManualTimers`, `threading.Event` barriers; plus three real
   `socket.socketpair()` integration tests (real timers, 0.5 s budgets, shrunk `SO_SNDBUF`).

**Success Definition**:
- (a) **Concurrent reception across load/blocking:** with the writer blocked inside `send`, a `ping`
  arriving on the socket renews the lease (observable `last_ping_at`) and queues a `pong` — the reader
  never waits on the writer, the daemon control lock, or the recorder reader thread.
- (b) **Lease contract:** lease = `last_valid_ping + 6 s`; re-armed per valid ping; a stale timer fire is
  ignored (generation counter); a ping arriving **after** the deadline is loss (`timeout`), not a
  renewal; no traffic → the timer fires → exactly one loss.
- (c) **Whole-frame write cap:** one absolute 2 s deadline per encoded line; partial progress resumes at
  the byte offset (never resends); the per-attempt socket timeout is the *remaining* budget; exceeded →
  one loss (`disconnected`). The writer sets timeouts on `conn.dup()` only — never on the shared socket
  object (a shared `settimeout` would make the reader's blocking `recv` time out).
- (d) **Sticky loss:** first cause wins; `on_loss` is called **exactly once** under concurrent EOF +
  lease-fire + write failure; loss shuts the socket so both threads exit; `send_event` then raises
  `PumpClosed`. Causes map to `ended.reason`: lease → `timeout`, invalid request/id/duplicate start →
  `delivery_failed`, EOF/io/frame/write → `disconnected`.
- (e) **Graceful end:** `shutdown(terminal)` writes the terminal line (the session's `ended`) under the
  same cap, then EOF; idempotent; EOF after it is **not** loss. `write_reject(conn, code)` emits
  `{"ok":false,"error":code}` + EOF for a rejected first frame.
- (f) **Non-blocking enqueue:** `send_event` performs `encode_line` + `put_nowait` only (no socket I/O on
  the caller thread — safe from the control lock / recorder reader thread); a full queue is loss.
- (g) Scope: `git diff --name-only` ⊆ {`voice_typing/editor_protocol.py`, `tests/test_editor_pump.py`};
  S1's and S2's symbols unchanged; `timeout 300 .venv/bin/python -m pytest tests/test_editor_pump.py
  tests/test_editor_protocol.py tests/test_editor_protocol_vectors.py -q` → 0 failures.

## User Persona

**Target User**: the implementers of P1.M1.T4.S7 (activation on the existing control socket), T4.S2
(sequenced offers / ACK deadline), T4.S5 (stop/cancel/drain), T4.S6 (`ended` + failure hints), T3.S4
(startup fence, 30 s cap) and the TS/Lua clients (P1.M2.T1.S2 / T2.S1 mirror the ping/lease constants).
**Use Case**: an editor connects, sends `editor-start`; the daemon spends up to 30 s loading models;
throughout, the editor pings every 2 s and may send `stop` or vanish. Today nothing owns that socket
after the first frame. **Pain Points Addressed**: a pump built on the connection thread would stop
reading pings during the load (false lease expiry) or during a blocked write; a writer sharing the
socket object would corrupt the reader's timeouts; relative sleeps drift; a non-sticky loss fires twice.

## Why

- **PRD §4.8.1 B is normative** (prd_snapshot.md:453-472): "Cap Start at 30 s; active lease expires at
  6 s without valid ping/pong on the respective side; ACK deadline is 5 s from offer write. Use monotonic
  time and bounded socket writes (at most 2 s) … The daemon must be able to service EOF/stop/lost/
  heartbeat during cold load; a cancelled reservation cannot resume/arm when the worker returns."
  "Client sends every 2 s while reserved, including during load and drain."
- **architecture/system_context.md** ("Control/recorder boundaries", "Buffer ownership"): "Ensure one
  writer, deadline on the whole frame (not just each fragment), no waits/joins/writes on daemon control
  lock or recorder reader thread … Use a monotonic clock for deadlines: owner ping every 2 s, lease 6 s,
  whole write 2 s, offer ACK 5 s … Reader/lease/ACK/worker can race; make revocation sticky".
  Proposed ownership: "`editor_protocol.py` owns codec, lease and serialized socket writer;
  `editor_session.py` owns reservation/ordered delivery state." This task delivers the lease + writer
  half; reservation/offer state is T3.S4/T4.*.
- **S1's Integration Points name this task**: "P1.M1.T3.S3 takes over a connection via `reader.unread`
  (the handoff seam) and adds deadlines AROUND `FrameReader` (the reader itself stays deadline-free)."
  **S2's**: "validate_request on every decoded dict; native_error_reply + EOF on a rejected first frame;
  request_kind to route native vs legacy."
- **Scope discipline.** The pump is NOT wired into `_handle`/`_dispatch` (T4.S7). The 30 s start cap and
  the 5 s ACK deadline are **session-owned** ("offer timeout belongs to session, not ping path") — this
  task only exports the constants as the single client/session reference and the deadline helpers.

## What

Append the pump to `voice_typing/editor_protocol.py`; add `tests/test_editor_pump.py`. No daemon, ctl,
config, recorder or existing-test change. The 2 s/6 s/2 s/30 s/5 s constants and the `LossCause →
ended.reason` mapping become the documented reference for every downstream item.

### Success Criteria

- [ ] `editor_protocol.py` exports every symbol in the Deliverable; S1's four and S2's nineteen symbols
      are byte-identical (append-only diff: zero deleted lines).
- [ ] Reader + writer are pump-owned daemon threads (`owner-pump-read`, `owner-pump-write`); `start()`
      returns immediately; `wait(timeout)` returns True once both exited.
- [ ] Lease: armed at `start()` (`last_ping_at + 6 s`), re-armed per valid ping (old timer cancelled),
      stale fire ignored, late ping → loss `LEASE` (`timeout`); `ManualTimers` tests never sleep.
- [ ] Writer: one absolute 2 s deadline per line, offset-tracked `send` loop, timeouts set on the `dup()`
      twin only (asserted: shared-object `settimeout` log stays empty); cap/io → one loss.
- [ ] `on_loss` exactly once under a 3-way race; loss shuts down the socket; `send_event` → `PumpClosed`.
- [ ] `shutdown(ended_frame)` → last line then `SHUT_WR` + EOF; idempotent; no loss. `write_reject`
      → `{"ok": false, "error": code}` + EOF.
- [ ] Valid requests: `ping` → `pong` + lease renewal; `applied`/`stop`/`cancel`/`lost` → `on_command`
      (validated dict, in order, on the reader thread); wrong id / duplicate `editor-start` /
      `ProtocolError` → loss `REQUEST`; bad UTF-8 / JSON / oversize → loss `FRAME` (detail never carries
      raw bytes or request text).
- [ ] Three socketpair tests pass with real timers (lease expiry, blocked receiver → write cap,
      ping→pong→graceful `ended`), each under ~3 s.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_editor_pump.py tests/test_editor_protocol.py
      tests/test_editor_protocol_vectors.py -q` → 0 failures; diff ⊆ the two files.

## All Needed Context

### Context Completeness Check

_Pass._ The complete pump, helpers and test harness are given verbatim (transcribed from the design in
`research/owner_pump_design.md`, incl. the probe-validated `SO_SNDBUF` technique); the thread/ownership
rules, the absolute-deadline arithmetic, the sticky-loss contract, the `dup()` timeout hazard, the
handoff seam and every downstream consumer are named; the upstream contracts (S1, S2) are quoted with
their exact symbol names; the file boundary (append-only, Task 0 gate) is explicit. Pure stdlib.

### Documentation & References

```yaml
# MUST READ — this task's own research: spec extraction table, design decisions D1–D8, probes
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S3/research/owner_pump_design.md
  why: "§2 which timer belongs to whom (pump enforces lease + write cap; start cap and ACK deadline are
        session-owned constants). §3 D1–D8 (threads, absolute deadlines, lease generation counter, sticky
        loss, the dup() timeout hazard, offset-tracked send, graceful end, scope). §4 the SO_SNDBUF probe."
  critical: "D5 is load-bearing: socket timeouts are PER SOCKET OBJECT shared by both threads — the
            writer MUST use conn.dup(); a shared settimeout would turn the reader's blocking recv into
            FrameError('io') and a spurious loss."

# THE SPEC — PRD §4.8.1 B (wire v1: timers, lease, bounded writes, loss semantics, end reasons)
- file: PRD.md
  why: "prd_snapshot.md:448-475. :453 '32 KiB wire limit per request and live event'; :456 ping 'every
        2 s while reserved, including during load and drain. No renewal after local invalidation.';
        :461 stop/cancel/lost semantics; :463 ended reasons; :465 'Every post-start frame is scoped to
        the owner connection and same id … other unexpected ids/seqs/commands terminate safely with
        delivery_failed'; :467 'Cap Start at 30 s; active lease expires at 6 s …; ACK deadline is 5 s
        … Use monotonic time and bounded socket writes (at most 2 s) … EOF, client failure, or expired
        lease is loss'; :469 'The daemon must be able to service EOF/stop/lost/heartbeat during cold
        load'; :471 'enqueue it without socket I/O under the control lock or on the recorder reader
        thread'."
  critical: "'scoped to the owner connection and same id' is why the pump itself rejects a wrong id and a
            second editor-start (stateless checks); reservation busy/duplicate_id stay in T3.S4/T4.S7."

# THE ARCHITECTURE NOTES the item names
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Control/recorder boundaries' + 'Buffer ownership and recovery': one writer, whole-frame
        deadline, no waits/joins/writes on the control lock or recorder reader thread, monotonic clock,
        sticky revocation; proposed module ownership (editor_protocol.py = codec, lease, serialized
        writer). 'Treat the 30-second native cap as a total start deadline' (session-owned here)."
- docfile: plan/009_ef3b49b0fc0d/architecture/verification.md
  why: "T10b row: 'deterministic events/barriers plus injected monotonic clock' — exactly this task's
        test discipline (no sleeps for races)."

# THE UPSTREAM CONTRACTS (parallel/landed siblings — append-only boundary)
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S1/PRP.md
  why: "LANDED on disk: MAX_FRAME_BYTES, FrameError(reason, detail) with reasons frame-too-large|eof|io,
        FrameReader(recv) with read_frame_bytes()/unread, encode_line(obj)->bytes. 'T3.S3 takes over a
        connection via reader.unread … adds deadlines AROUND FrameReader (the reader stays deadline-free).'"
  gotcha: "FrameReader raises FrameError('io') for ANY OSError from recv — including TimeoutError. That is
          exactly why the writer must never settimeout() the shared socket object (D5)."
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S2/PRP.md
  why: "IMPLEMENTING (not on disk at research time): validate_request(obj)->dict (raises ProtocolError
        .code/.detail), request_kind, native_error_reply(code)->{'ok':False,'error':code}, PROTOCOL_VERSION.
        Its Integration Points: 'P1.M1.T3.S3 (owner pump): validate_request on every decoded dict;
        native_error_reply + EOF on a rejected first frame; request_kind to route native vs legacy.'"
  gotcha: "Task 0 gates on S2's symbols. S2's L4 gate asserts editor_protocol.py has NO time./threading —
          that check is S2's, run before this task appends; after S3 the grep is non-zero by design."
- file: voice_typing/daemon.py
  why: ":3505 thread-per-connection (`threading.Thread(target=self._handle, …)`); :3527 `_handle` builds
        `FrameReader(conn.recv)` and closes conn in its finally. T4.S7 will branch there on
        `request_kind` and construct the pump with that reader (handoff). This task does NOT edit it."
  pattern: "The pump is designed to be constructed on the connection thread with the live reader, started,
        and waited on — `_handle`'s existing conn.close() in finally is idempotent with the pump's."

# THE TEST CONVENTIONS
- file: tests/test_editor_protocol.py
  why: "S1's hermetic style: a scripted fake recv (FakeSock popping chunks, b'' at exhaustion); header
        'NO live socket listener, NO CUDA'. Mirror it: byte-level cases on the fake conn; socketpair only
        for the three integration tests."
  gotcha: "S1 found handoff assertions over a real socketpair timing-dependent — never assert intermediate
          buffers on a real socket here either."
- file: voice_typing/bulk_delivery.py
  why: ":77 `class ShowResult(str, Enum)` — repo convention for code sets → `LossCause(str, enum.Enum)`."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/editor_protocol.py   # S1 landed: MAX_FRAME_BYTES, FrameError, FrameReader, encode_line (lines 18-110).
                                  # S2 (implementing) appends validators below. THIS TASK APPENDS BELOW S2.
voice_typing/daemon.py            # _handle :3507 (FrameReader at :3527) — NOT edited here (T4.S7).
tests/test_editor_protocol.py     # S1's suite — do not touch.
tests/test_editor_protocol_vectors.py + tests/fixtures/editor_v1.json   # S2's — do not touch.
tests/                            # NO test_editor_pump.py yet.
```

### Desired Codebase tree with files to be added

```bash
voice_typing/editor_protocol.py   # APPEND §"owner connection pump" (constants, helpers, LossCause, PumpClosed,
                                  # send_line_capped, ThreadTimers, write_reject, OwnerPump) + ONE docstring sentence.
tests/test_editor_pump.py         # CREATE: Hold/FakeClock/ManualTimers/FakeConn harness + 22 tests (32 cases; 3 on socketpair).
# Nothing else. daemon.py / ctl.py / config.py / recorder_host.py / existing tests: untouched. No new dependency.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — APPEND, NEVER REWRITE. S1 (landed) and S2 (implementing, parallel) both live in
# editor_protocol.py. Put this task's code at the END under its banner; Task 0 verifies S2's symbols first
# (STOP if absent). The L1 gate: `git diff -- voice_typing/editor_protocol.py | grep -c '^-[^-]'` == 0.

# CRITICAL #2 — settimeout() IS PER SOCKET OBJECT, SHARED BY ALL THREADS. The writer's bounded send must
# run on `conn.dup()` (a new object, default blocking, same underlying socket). Calling settimeout on the
# shared object would make the reader's blocking recv raise TimeoutError → FrameError("io") → spurious loss.

# CRITICAL #3 — NEVER sendall() AFTER A TIMEOUT. socket.sendall leaves "unspecified how much was sent";
# retrying it would duplicate bytes on the wire. Track the offset with socket.send(view[sent:]).

# CRITICAL #4 — ABSOLUTE DEADLINES ONLY. deadline = clock() + budget, computed ONCE per frame; every
# wait uses remaining = max(0, deadline - clock()). Never time.sleep(relative) or re-arm with a fresh
# budget — drift turns a 2 s cap into unbounded.

# CRITICAL #5 — LEASE IS STRICT ON BOTH SIDES. Timer fire → loss only if its generation is current; a
# ping received AFTER last_ping_at + 6 s is loss ("ping after lease deadline"), never a renewal — the
# timer thread can be scheduled late, so the receive path must re-check the deadline itself.

# CRITICAL #6 — STICKY LOSS. _on_loss returns False if already lost/closing; the first cause wins. It
# calls conn.shutdown(SHUT_RDWR) (wakes a blocked recv → b"" and a blocked send → OSError) BEFORE invoking
# on_loss, outside the internal lock, on the detecting thread. Both loops exit without a second callback.

# CRITICAL #7 — EOF AFTER A GRACEFUL shutdown() IS NOT LOSS. `_closing` is checked in _on_loss. Order in
# shutdown(): under one lock hold set _closing, bump the lease generation (cancels the timer's effect),
# queue the terminal line — so send_event can never queue AFTER the terminal (it checks _closing under the
# same lock) and the writer's "closing and empty → exit" check can never skip the terminal line.

# CRITICAL #8 — A REAL Timer FIRE RACES A PING. _lease_fired checks gen/lost/closing under the lock;
# _renew_lease re-checks the deadline under the lock. Either order is correct (see CRITICAL #5).

# CRITICAL #9 — FrameError REASONS FROM S1: "eof" (detail "" clean / "partial"), "frame-too-large", "io".
# Map: eof→EOF, frame-too-large→FRAME, io→IO. The reader never decodes inside FrameReader (S1 rule).

# CRITICAL #10 — NO ECHO. ProtocolError.detail (S2) names field + class only; this task's details are
# fixed strings ("frame too large", "id mismatch", …). Never put frame bytes, request text or the seed
# into a loss detail, a callback argument or a log line.

# CRITICAL #11 — THE WRITER POLL. The writer waits on queue.get(timeout=0.1) and re-checks lost/closing —
# a sentinel is unsafe because the bounded queue may be full at shutdown. 10 wakeups/s on a daemon thread.

# GOTCHA #12 — Full paths + two timeouts: `timeout 300 .venv/bin/python -m pytest <files> -q` (bash-tool
# ≥ 360). pytest only (no ruff/mypy configured). Never bare python/pytest/uv. test_daemon.py is NOT
# required (daemon.py untouched) — if run anyway, use `timeout 500` and the G1_BASELINE name set-diff.

# GOTCHA #13 — Python 3.12: socket.timeout IS TimeoutError (an OSError). Catch TimeoutError BEFORE
# OSError in the send loop. AF_UNIX: data written before close() stays readable by the peer (last frame
# then EOF is safe); SO_SNDBUF 4608 → effective 9216 → a 30 KiB line to a non-reading peer blocks.

# GOTCHA #14 — DOWNSTREAM FILES ARE NOT YOURS. Do not edit daemon.py/_handle/_dispatch, create
# editor_session.py, or add integrations/. Keep names EXACTLY as specified (T4.S5/S6/S7 import them).

# CROSS-ITEM NOTE (report, do not fix here): the PRD's first daemon→editor frame is
# {"ok":true,"event":"starting","id":"..."} but S2's validate_event spec for `starting` is the closed set
# {event,id} — `ok` would be rejected as unknown. The pump does not validate outbound events (T4.S2 does),
# so S3 is unaffected; T4.S2/T4.S7 must allow an optional `ok` on `starting` or emit it without `ok`.
```

## Implementation Blueprint

### Data models and structure

Stdlib only. One `str, Enum` (`LossCause`) with an `end_reason` property; one `Exception` (`PumpClosed`);
two small timer classes (`ThreadTimers` production, test-local `ManualTimers`); one class (`OwnerPump`)
holding the conn, its `dup()` twin, an S1 `FrameReader`, a bounded `queue.Queue[bytes]`, a `Lock` that
guards only the flags/lease fields (never held during I/O or callbacks), and two daemon threads.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREREQUISITE GATE — S1 and S2 have landed
  - RUN: test -f voice_typing/editor_protocol.py && grep -c 'def validate_request\|class ProtocolError\|def native_error_reply\|def request_kind' voice_typing/editor_protocol.py
  - EXPECT: 4. If S1's symbols are missing → STOP "P1.M1.T3.S1 not landed". If S2's are missing → STOP
    "P1.M1.T3.S2 not landed" (do not author either sibling's code).

Task 1: APPEND to voice_typing/editor_protocol.py (verbatim). Add ONE sentence to the END of the module
        docstring: "Also owns the owner connection pump: 2 s/6 s ping-lease, the single serialized bounded
        writer and the sticky terminal-loss contract (P1.M1.T3.S3; PRD §4.8.1 B)." Then append:
  - CONTENT:
    # --- owner connection pump (P1.M1.T3.S3; PRD §4.8.1 B: lease, bounded writes, terminal callbacks) ---
    # Transport ONLY: no daemon import, no reservation/offer state (T3.S4/T4.*), no ACK deadline (T4.S2).
    import enum
    import json
    import queue
    import socket
    import threading
    import time

    PING_INTERVAL_S: float = 2.0    # §4.8.1 B: client pings every 2 s while reserved (incl. load + drain) — client reference
    LEASE_S: float = 6.0            # §4.8.1 B: owner lease expires 6 s after the last valid ping (three missed pings)
    WRITE_CAP_S: float = 2.0        # §4.8.1 B: "bounded socket writes (at most 2 s)" — per WHOLE encoded line
    START_CAP_S: float = 30.0       # §4.8.1 B: total Start budget incl. load/priming — SESSION-owned (T3.S4/T4.S7)
    ACK_DEADLINE_S: float = 5.0     # §4.8.1 B: offer ACK deadline from offer write — SESSION-owned (T4.S2), never the ping path
    OUTBOUND_QUEUE_MAX: int = 64    # bounded writer queue (the 8-final live cap is the session's FIFO, not this)
    _PUMP_POLL_S: float = 0.1


    def deadline_after(budget: float, now: float | None = None) -> float:
        """Absolute monotonic deadline = now + budget (every timer in this module is expressed this way)."""
        return (time.monotonic() if now is None else now) + budget


    def remaining(deadline: float, now: float | None = None) -> float:
        """Remaining budget to an ABSOLUTE deadline, clamped at 0 — the only way this module waits."""
        return max(0.0, deadline - (time.monotonic() if now is None else now))


    class LossCause(str, enum.Enum):
        """Why an owner connection ended abnormally (sticky; first cause wins). `.end_reason` is the
        §4.8.1 B `ended.reason` the session SHOULD report (T4.S6 owns the actual `ended` frame)."""
        EOF = "eof"            # clean EOF / partial frame at EOF  -> disconnected
        IO = "io"              # recv/send OSError                 -> disconnected
        FRAME = "frame"        # oversize, invalid UTF-8, bad JSON  -> disconnected
        REQUEST = "request"    # ProtocolError, wrong id, 2nd start -> delivery_failed
        LEASE = "lease"        # 6 s without a valid ping          -> timeout
        WRITE = "write"        # 2 s whole-frame cap / full queue  -> disconnected

        @property
        def end_reason(self) -> str:
            if self is LossCause.LEASE:
                return "timeout"
            if self is LossCause.REQUEST:
                return "delivery_failed"
            return "disconnected"


    class PumpClosed(Exception):
        """send_event() after the pump is lost or gracefully closing."""

        def __init__(self, cause: object) -> None:
            super().__init__(f"owner pump closed ({cause})")
            self.cause = cause


    def send_line_capped(conn, line: bytes, *, cap_s: float = WRITE_CAP_S,
                         clock=time.monotonic) -> bool:
        """Send ONE whole encoded line under an ABSOLUTE cap (default 2 s). True = fully sent; False = cap
        exceeded; raises OSError on a hard socket error (caller maps it). Never resends: a timed-out partial
        send resumes at the byte offset (socket.send, NOT sendall — its sent count after a timeout is
        unspecified). `conn` must be a socket object dedicated to the writer (see OwnerPump: settimeout is
        per object and would leak into the reader's recv on a shared one)."""
        deadline = clock() + cap_s
        view = memoryview(line)
        sent = 0
        while sent < len(line):
            left = deadline - clock()
            if left <= 0:
                return False
            conn.settimeout(left)
            try:
                n = conn.send(view[sent:])
            except TimeoutError:          # subset of OSError: cap not yet reached, retry with the remainder
                continue
            if n > 0:
                sent += n                 # n == 0: loop is bounded by the deadline
        return True


    class ThreadTimers:
        """Production timer source: one daemon threading.Timer per arm, relative to the injected clock."""

        def __init__(self, clock=time.monotonic) -> None:
            self._clock = clock

        def arm(self, deadline: float, fire) -> object:
            timer = threading.Timer(max(0.0, deadline - self._clock()), fire)
            timer.daemon = True
            timer.start()
            return timer

        @staticmethod
        def cancel(handle) -> None:
            handle.cancel()


    def write_reject(conn, code: str, *, cap_s: float = WRITE_CAP_S) -> None:
        """A REJECTED FIRST request (T4.S7 calls this; S2's code): write native_error_reply(code) under the
        write cap, then EOF. Best effort on the connection thread BEFORE any pump exists — never raises,
        never echoes the request."""
        try:
            send_line_capped(conn, encode_line(native_error_reply(code)), cap_s=cap_s)
            conn.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


    class OwnerPump:
        """Owner connection pump (PRD §4.8.1 B). Transport for ONE native v1 session after its first
        `editor-start` was accepted; T4.S7 constructs it on the connection thread with the live FrameReader
        (so S1's `unread` handoff bytes are preserved), queues `starting`, calls start(), then waits.

        THREAD OWNERSHIP (Mode A):
          * `owner-pump-read`  — FrameReader loop: decodes, validate_request (S2), routes. ping -> pong +
                                 lease renewal; applied/stop/cancel/lost -> on_command(obj). Never writes.
          * `owner-pump-write` — the ONLY writer: drains a bounded queue of encoded lines through
                                 send_line_capped on `conn.dup()`. Never reads.
          * the lease timer's thread — ThreadTimers (or the test's ManualTimers) fires _lease_fired.
        NOTHING here runs on the daemon control lock or the recorder reader thread, and nothing here takes
        a daemon lock. send_event() is non-blocking and does no socket I/O (encode_line + put_nowait), so
        the session may call it from any thread, including under the control lock or on the recorder
        reader thread (§4.8.1 B: "enqueue it without socket I/O").

        ABSOLUTE DEADLINES (Mode A): lease_deadline = last_ping_at + LEASE_S (armed at start(), re-armed
        per valid ping; a stale timer fire is ignored via a generation counter; a ping AFTER the deadline
        is loss, never a renewal). Each outbound line gets ONE deadline = clock() + write_cap_s; every
        send attempt uses the REMAINING budget as its socket timeout. The Start cap (30 s) and ACK
        deadline (5 s) belong to the session and are exported as constants only.

        TERMINAL CALLBACK CONTRACT (Mode A): on_loss(cause) is called EXACTLY ONCE, on the thread that
        first detected the failure (reader, writer or timer thread), after the socket has been shut down
        (so both I/O threads wake) and with NO pump lock held. Callbacks must not block, raise, or do
        socket I/O; queue the work elsewhere. After loss, send_event raises PumpClosed. A graceful
        shutdown(terminal) is NOT a loss: the terminal line (the session's `ended`) is written under the
        same cap, then the write side closes — "last frame then EOF"; an EOF observed afterwards is ignored.
        """

        def __init__(self, conn, session_id: str, *, on_command, on_loss, reader=None,
                     clock=time.monotonic, timers=None, lease_s: float = LEASE_S,
                     write_cap_s: float = WRITE_CAP_S, queue_max: int = OUTBOUND_QUEUE_MAX) -> None:
            self._conn = conn                      # duck type: recv, dup, shutdown, close (writer twin: send, settimeout)
            self._wconn = conn.dup()               # D5: the writer's OWN object — settimeout must not touch the reader's
            self._id = session_id
            self._reader = reader if reader is not None else FrameReader(conn.recv)
            self._on_command = on_command
            self._on_loss_cb = on_loss
            self._clock = clock
            self._timers = timers if timers is not None else ThreadTimers(clock)
            self._lease_s = float(lease_s)
            self._write_cap_s = float(write_cap_s)
            self._q: queue.Queue = queue.Queue(maxsize=int(queue_max))
            self._lock = threading.Lock()          # guards ONLY the fields below; never held during I/O/callbacks
            self._lost = False
            self._closing = False
            self._cause = None
            self._detail = ""
            self._last_ping_at = float(clock())
            self._lease_gen = 0
            self._lease_timer = None
            self._threads: list = []
            self._done = 0
            self._all_done = threading.Event()

        @property
        def lost(self) -> bool:
            return self._lost

        @property
        def loss_cause(self):
            return self._cause

        @property
        def loss_detail(self) -> str:
            return self._detail

        @property
        def closed(self) -> bool:
            return self._closing

        @property
        def last_ping_at(self) -> float:
            return self._last_ping_at

        @property
        def lease_deadline(self) -> float:
            return self._last_ping_at + self._lease_s

        def start(self) -> None:
            """Arm the lease and spawn the reader + writer threads. Returns immediately. Once per pump."""
            with self._lock:
                if self._threads or self._lost or self._closing:
                    raise RuntimeError("owner pump already started or closed")
                self._arm_lease()
                self._threads = [
                    threading.Thread(target=self._read_loop, name="owner-pump-read", daemon=True),
                    threading.Thread(target=self._write_loop, name="owner-pump-write", daemon=True),
                ]
            for t in self._threads:
                t.start()

        def send_event(self, obj: dict) -> None:
            """Queue ONE daemon->editor event (encode on the CALLER's thread; FrameError propagates for an
            oversize event). Non-blocking, no socket I/O. Raises PumpClosed when lost/closing; a full queue
            is a WRITE loss (the peer stopped reading long ago) and raises PumpClosed."""
            line = encode_line(obj)
            full = False
            with self._lock:
                if self._lost or self._closing:
                    raise PumpClosed(self._cause or "closing")
                try:
                    self._q.put_nowait(line)
                except queue.Full:
                    full = True
            if full:
                self._on_loss(LossCause.WRITE, "outbound queue full")
                raise PumpClosed(LossCause.WRITE)

        def shutdown(self, terminal: dict | None = None) -> None:
            """Graceful end: queue `terminal` (the session's `ended` frame) as the LAST line, then EOF.
            Idempotent; no-op once lost. The terminal is queued under the same lock hold that sets
            _closing, so nothing can be queued after it and the writer cannot exit before it."""
            line = encode_line(terminal) if terminal is not None else None
            timer = None
            full = False
            with self._lock:
                if self._lost or self._closing:
                    return
                self._closing = True
                self._lease_gen += 1
                timer, self._lease_timer = self._lease_timer, None
                try:
                    if line is not None:
                        self._q.put_nowait(line)
                except queue.Full:
                    self._closing = False
                    full = True
            if timer is not None:
                self._timers.cancel(timer)
            if full:
                self._on_loss(LossCause.WRITE, "outbound queue full at shutdown")

        def wait(self, timeout: float | None = None) -> bool:
            """Block until BOTH pump threads exited. True if they did within `timeout`."""
            return self._all_done.wait(timeout)

        # --- lease (all under _lock) ---
        def _arm_lease(self) -> None:
            self._lease_gen += 1
            gen = self._lease_gen
            if self._lease_timer is not None:
                self._timers.cancel(self._lease_timer)
            self._lease_timer = self._timers.arm(self._last_ping_at + self._lease_s,
                                                 lambda: self._lease_fired(gen))

        def _lease_fired(self, gen: int) -> None:
            with self._lock:
                if gen != self._lease_gen or self._lost or self._closing:
                    return
            self._on_loss(LossCause.LEASE, "lease expired")

        def _renew_lease(self) -> None:
            with self._lock:
                if self._lost or self._closing:
                    return
                now = self._clock()
                if now > self._last_ping_at + self._lease_s:
                    expired = True          # a ping after the deadline never revives the lease
                else:
                    expired = False
                    self._last_ping_at = now
                    self._arm_lease()
            if expired:
                self._on_loss(LossCause.LEASE, "ping after lease deadline")

        # --- sticky loss ---
        def _on_loss(self, cause: LossCause, detail: str = "") -> bool:
            with self._lock:
                if self._lost or self._closing:
                    return False
                self._lost = True
                self._cause = cause
                self._detail = detail
                self._lease_gen += 1
                timer, self._lease_timer = self._lease_timer, None
            if timer is not None:
                self._timers.cancel(timer)
            try:
                self._conn.shutdown(socket.SHUT_RDWR)   # wakes recv (-> b"") and send (-> OSError)
            except OSError:
                pass
            self._on_loss_cb(cause)                    # exactly once; no lock held; detecting thread
            return True

        # --- reader thread ---
        def _read_loop(self) -> None:
            try:
                while True:
                    with self._lock:
                        if self._lost or self._closing:
                            return
                    try:
                        raw = self._reader.read_frame_bytes()
                    except FrameError as fe:
                        if fe.reason == "eof":
                            self._on_loss(LossCause.EOF, fe.detail)
                        elif fe.reason == "frame-too-large":
                            self._on_loss(LossCause.FRAME, "frame too large")
                        else:
                            self._on_loss(LossCause.IO, fe.detail)
                        return
                    if not self._handle_frame(raw):
                        return
            finally:
                self._finished()

        def _handle_frame(self, raw: bytes) -> bool:
            try:
                obj = json.loads(raw.decode("utf-8"))
                validate_request(obj)
            except (UnicodeDecodeError, ValueError):     # bad UTF-8 / bad JSON (JSONDecodeError is a ValueError)
                self._on_loss(LossCause.FRAME, "undecodable or malformed frame")
                return False
            except ProtocolError as exc:                 # right JSON, not a valid v1 request
                self._on_loss(LossCause.REQUEST, exc.detail)
                return False
            if obj["id"] != self._id:
                self._on_loss(LossCause.REQUEST, "id mismatch")
                return False
            cmd = obj["cmd"]
            if cmd == "editor-start":
                self._on_loss(LossCause.REQUEST, "duplicate start on owner connection")
                return False
            if cmd == "ping":
                self._renew_lease()
                try:
                    self.send_event({"event": "pong", "id": self._id})
                except PumpClosed:
                    pass
            else:                                       # applied | stop | cancel | lost
                try:
                    self._on_command(obj)                # reader thread; must not block / raise / do I/O
                except Exception:
                    self._on_loss(LossCause.REQUEST, "command handler failed")
                    return False
            with self._lock:
                return not self._lost and not self._closing

        # --- writer thread ---
        def _write_loop(self) -> None:
            try:
                while True:
                    with self._lock:
                        if self._lost or (self._closing and self._q.empty()):
                            return
                    try:
                        item = self._q.get(timeout=_PUMP_POLL_S)
                    except queue.Empty:
                        continue
                    try:
                        sent = send_line_capped(self._wconn, item, cap_s=self._write_cap_s, clock=self._clock)
                    except OSError as exc:
                        self._on_loss(LossCause.IO, type(exc).__name__)
                        return
                    if not sent:
                        self._on_loss(LossCause.WRITE, "write cap exceeded")
                        return
            finally:
                try:
                    self._wconn.shutdown(socket.SHUT_WR)     # peer sees EOF AFTER the last frame
                except OSError:
                    pass
                try:
                    self._wconn.shutdown(socket.SHUT_RDWR)   # wakes our reader
                except OSError:
                    pass
                try:
                    self._wconn.close()
                except OSError:
                    pass
                self._finished()

        def _finished(self) -> None:
            with self._lock:
                self._done += 1
                done = self._done >= len(self._threads)
            if done:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._all_done.set()
  - DO NOT: import voice_typing.daemon; open/listen on sockets; add reservation/offer/ACK state; validate
    outbound events (T4.S2's job); set a timeout on the shared conn; use sendall; use relative sleeps.

Task 2: CREATE tests/test_editor_pump.py (hermetic; harness and all 22 tests verbatim)
  - HEADER: "Owner connection pump (PRD §4.8.1 B; P1.M1.T3.S3). NO live listener, NO CUDA, NO daemon import.
    Byte-level and race cases run on a duck-typed FakeConn with a fake clock and manual timers (no sleeps);
    three integration cases use socket.socketpair() with real timers and 0.5 s budgets. Run: timeout 300
    .venv/bin/python -m pytest tests/test_editor_pump.py -q"
  - HARNESS (verbatim):
    from __future__ import annotations
    import json, socket, threading, time
    import pytest
    from voice_typing import editor_protocol as ep

    ID = "123e4567-e89b-42d3-a456-426614174000"
    OTHER = "123e4567-e89b-42d3-a456-426614174001"

    class Hold:
        """A recv chunk that blocks the reader until the test sets .go — a monotonic barrier, never a sleep."""
        def __init__(self) -> None: self.go = threading.Event()

    class FakeClock:
        def __init__(self, now: float = 100.0) -> None: self.now = now
        def __call__(self) -> float: return self.now
        def advance(self, s: float) -> None: self.now += s

    class _Handle:
        def __init__(self, deadline, fire): self.deadline, self.fire, self.cancelled = deadline, fire, False

    class ManualTimers:
        """Deterministic timer source: records arms; the TEST decides what fires (never a real wait)."""
        def __init__(self) -> None: self.armed: list[_Handle] = []
        def arm(self, deadline, fire):
            h = _Handle(deadline, fire); self.armed.append(h); return h
        @staticmethod
        def cancel(handle): handle.cancelled = True
        def live(self): return [h for h in self.armed if not h.cancelled]

    class _Twin:
        """What conn.dup() returns: its OWN settimeout log (a real dup does not share the timeout)."""
        def __init__(self, parent): self._p = parent; self.timeouts: list[float] = []
        def settimeout(self, t): self.timeouts.append(t)
        def send(self, buf): return self._p._send(buf)
        def shutdown(self, how): self._p.shutdowns.append(("twin", how))
        def close(self): self._p.twin_closed = True

    class FakeConn:
        """Duck-typed socket: scripted recv chunks (a Hold blocks until .go), scripted send outcomes, logs
        settimeout/shutdown/close. send_script steps: int = bytes accepted, ("timeout", advance_s),
        "block" (waits for `release`, then TimeoutError), an OSError instance; exhausted -> accept all."""
        def __init__(self, *chunks, send_script=(), clock=None):
            self._chunks = list(chunks); self._script = list(send_script); self._clock = clock
            self.sent: list[bytes] = []; self.sent_from: list[str] = []
            self.timeouts: list[float] = []; self.shutdowns: list = []
            self.closed = False; self.twin_closed = False
            self.release = threading.Event(); self.in_send = threading.Event()
            self.twin = _Twin(self)
        def recv(self, n):
            chunk = self._chunks.pop(0) if self._chunks else b""
            if isinstance(chunk, Hold):
                chunk.go.wait(5)
                return self.recv(n)
            return chunk
        def dup(self): return self.twin
        def settimeout(self, t): self.timeouts.append(t)
        def send(self, buf): return self._send(buf)
        def _send(self, buf):
            self.sent.append(bytes(buf)); self.sent_from.append(threading.current_thread().name)
            step = self._script.pop(0) if self._script else None
            if step == "block":
                self.in_send.set(); self.release.wait(5); raise TimeoutError
            if isinstance(step, tuple):
                if self._clock is not None: self._clock.advance(step[1])
                raise TimeoutError
            if isinstance(step, OSError): raise step
            return len(buf) if step is None else step
        def shutdown(self, how): self.shutdowns.append(("conn", how))
        def close(self): self.closed = True

    def frame(obj) -> bytes: return ep.encode_line(obj)
    def ping(sid=ID) -> bytes: return frame({"cmd": "ping", "id": sid})

    def mk(conn, *, clock=None, timers=None, on_command=None, **kw):
        clock, timers = clock or FakeClock(), timers or ManualTimers()
        cmds, losses = [], []
        pump = ep.OwnerPump(conn, ID, on_command=on_command or cmds.append, on_loss=losses.append,
                            clock=clock, timers=timers, **kw)
        return pump, clock, timers, cmds, losses

    def settle(pump, *holds, timeout=5.0):
        """Open every barrier, then wait for BOTH threads; asserts they actually exited."""
        for h in holds: h.go.set()
        assert pump.wait(timeout), "pump threads did not exit"

    def wait_until(pred, timeout=5.0):
        """Bounded poll (<= 5 s, returns immediately once true) for a state another THREAD produces."""
        deadline = time.monotonic() + timeout
        while not pred() and time.monotonic() < deadline: time.sleep(0.005)
        return pred()
  - TESTS (verbatim):
    # --- constants / helpers (the client + session deadline reference) ---
    def test_deadline_reference_constants():
        assert (ep.PING_INTERVAL_S, ep.LEASE_S, ep.WRITE_CAP_S, ep.START_CAP_S, ep.ACK_DEADLINE_S) == (2.0, 6.0, 2.0, 30.0, 5.0)
        assert ep.LEASE_S == 3 * ep.PING_INTERVAL_S          # a lease tolerates exactly two missed pings
        assert ep.deadline_after(2.5, now=10.0) == 12.5 and ep.remaining(12.5, now=10.0) == 2.5
        assert ep.remaining(12.5, now=20.0) == 0.0             # clamped, never negative
        assert {c.end_reason for c in ep.LossCause} == {"timeout", "delivery_failed", "disconnected"}
        assert ep.LossCause.LEASE.end_reason == "timeout" and ep.LossCause.REQUEST.end_reason == "delivery_failed"
        assert all(c.end_reason == "disconnected" for c in (ep.LossCause.EOF, ep.LossCause.IO, ep.LossCause.FRAME, ep.LossCause.WRITE))

    # --- ping / pong / lease renewal (the reader is held at a Hold until the test moves the clock) ---
    def test_ping_queues_pong_and_renews_lease_with_new_timer():
        h1, h2 = Hold(), Hold(); conn = FakeConn(h1, ping(), h2); pump, clock, timers, cmds, losses = mk(conn)
        pump.start(); assert pump.lease_deadline == 106.0           # armed at start(): 100 + 6
        clock.advance(1.0); h1.go.set()                             # the ping is read at t = 101
        assert wait_until(lambda: conn.sent == [frame({"event": "pong", "id": ID})])
        assert pump.last_ping_at == 101.0 and pump.lease_deadline == 107.0 and not pump.lost and cmds == []
        assert [h.deadline for h in timers.armed] == [106.0, 107.0]  # re-armed: new absolute deadline
        assert timers.armed[0].cancelled and timers.live() == [timers.armed[1]]
        assert conn.sent_from == ["owner-pump-write"]
        h2.go.set(); settle(pump, h2)
        assert losses == [ep.LossCause.EOF] and timers.live() == []   # the loss retired the live timer

    def test_lease_timer_fire_without_traffic_is_loss_once():
        hold = Hold(); conn = FakeConn(hold); pump, clock, timers, cmds, losses = mk(conn)
        pump.start(); timers.live()[0].fire()                         # 6 s passed with no ping
        assert losses == [ep.LossCause.LEASE] and pump.loss_cause is ep.LossCause.LEASE
        assert ("conn", socket.SHUT_RDWR) in conn.shutdowns           # both I/O threads are woken
        timers.armed[0].fire()                                        # a second fire of the same handle: ignored
        assert losses == [ep.LossCause.LEASE]
        settle(pump, hold)                                            # the EOF this caused is NOT a second loss
        assert losses == [ep.LossCause.LEASE] and timers.live() == []

    def test_ping_after_lease_deadline_is_loss_not_renewal():
        hold = Hold(); conn = FakeConn(hold, ping()); pump, clock, timers, cmds, losses = mk(conn)
        pump.start(); clock.advance(6.5); hold.go.set(); settle(pump, hold)
        assert losses == [ep.LossCause.LEASE] and pump.loss_detail == "ping after lease deadline"
        assert pump.loss_cause.end_reason == "timeout" and conn.sent == [] and pump.last_ping_at == 100.0

    def test_stale_lease_timer_fire_is_ignored_after_renewal():
        h1, h2 = Hold(), Hold(); conn = FakeConn(h1, ping(), h2); pump, clock, timers, cmds, losses = mk(conn)
        pump.start(); clock.advance(1.0); h1.go.set()
        assert wait_until(lambda: pump.last_ping_at == 101.0)         # renewed: gen 2, deadline 107
        timers.armed[0].fire()                                         # the superseded timer fires late: ignored
        assert losses == [] and timers.live() == [timers.armed[1]]
        settle(pump, h2)
        assert losses == [ep.LossCause.EOF] and timers.armed[0].cancelled

    # --- loss taxonomy on the read path (details never carry request bytes) ---
    @pytest.mark.parametrize("chunks, cause", [
        ((b"",), ep.LossCause.EOF),
        ((b'{"cmd":"pi',), ep.LossCause.EOF),                                 # partial frame at EOF -> detail "partial"
        ((b"x" * (ep.MAX_FRAME_BYTES + 1) + b"\n",), ep.LossCause.FRAME),     # oversize
        ((b"\xff\xfe{\n",), ep.LossCause.FRAME),                              # invalid UTF-8
        ((b"{not json}\n",), ep.LossCause.FRAME),
        ((frame({"cmd": "toggle"}),), ep.LossCause.REQUEST),                  # S2: a legacy cmd is not native
        ((frame({"cmd": "applied", "id": ID, "seq": True}),), ep.LossCause.REQUEST),
        ((ping(OTHER),), ep.LossCause.REQUEST),                               # wrong id
        ((frame({"cmd": "editor-start", "version": 1, "id": ID, "context": ""}),), ep.LossCause.REQUEST),
        ((frame([1, 2]),), ep.LossCause.REQUEST),                             # JSON, but not an object
    ])
    def test_read_path_loss_causes(chunks, cause):
        pump, clock, timers, cmds, losses = mk(FakeConn(*chunks)); pump.start(); settle(pump)
        assert losses == [cause] and pump.loss_cause is cause and pump.lost and cmds == []
        if cause is ep.LossCause.REQUEST: assert pump.loss_cause.end_reason == "delivery_failed"
        if chunks == (b'{"cmd":"pi',): assert pump.loss_detail == "partial"

    def test_recv_oserror_is_io_loss():
        conn = FakeConn()
        def recv(n): raise OSError("boom")
        conn.recv = recv
        pump, clock, timers, cmds, losses = mk(conn); pump.start(); settle(pump)
        assert losses == [ep.LossCause.IO] and pump.loss_detail == "boom"

    def test_loss_details_never_echo_request_bytes():
        secret = "private editor text"
        conn = FakeConn(frame({"cmd": "ping", "id": ID, "extra": secret}))   # S2's detail names the FIELD only
        pump, clock, timers, cmds, losses = mk(conn); pump.start(); settle(pump)
        assert losses == [ep.LossCause.REQUEST] and secret not in pump.loss_detail and secret not in pump.loss_cause.value

    # --- commands reach on_command in order, on the reader thread; they do NOT end the pump ---
    def test_commands_are_delivered_in_order_on_reader_thread():
        names, got = [], []
        def on_cmd(obj): got.append(obj); names.append(threading.current_thread().name)
        conn = FakeConn(frame({"cmd": "applied", "id": ID, "seq": 1}), frame({"cmd": "stop", "id": ID}),
                        frame({"cmd": "cancel", "id": ID}), frame({"cmd": "lost", "id": ID}), b"")
        pump, clock, timers, _, losses = mk(conn, on_command=on_cmd)
        pump.start(); assert pump.wait(5)
        assert [o["cmd"] for o in got] == ["applied", "stop", "cancel", "lost"] and got[0]["seq"] == 1
        assert names == ["owner-pump-read"] * 4 and losses == [ep.LossCause.EOF]   # the session ends it, not the command

    def test_crashing_command_handler_ends_as_request_loss():
        def boom(obj): raise RuntimeError("handler bug")
        conn = FakeConn(frame({"cmd": "stop", "id": ID}), b"")
        pump, clock, timers, _, losses = mk(conn, on_command=boom); pump.start(); assert pump.wait(5)
        assert losses == [ep.LossCause.REQUEST] and pump.loss_detail == "command handler failed"

    # --- writer: whole-frame absolute cap, offset tracking, dup()-only timeouts ---
    def test_write_cap_is_whole_frame_and_never_resends():
        hold = Hold(); clock = FakeClock(); conn = FakeConn(hold, send_script=[5, ("timeout", 2.0)], clock=clock)
        pump, clock, timers, cmds, losses = mk(conn, clock=clock)
        ev = {"event": "final", "id": ID, "seq": 1, "text": "hello"}
        pump.send_event(ev); pump.start()
        assert wait_until(lambda: pump.lost)                 # the WRITER alone decides (the reader is held)
        assert losses == [ep.LossCause.WRITE] and pump.loss_detail == "write cap exceeded"
        line = frame(ev)
        assert conn.sent == [line, line[5:]]                  # resumed at the offset; never resent from byte 0
        assert conn.twin.timeouts == [2.0, 2.0]               # ONE absolute deadline; the clock did not move
        assert conn.timeouts == []                            # CRITICAL #2: the shared object never got a timeout
        assert conn.sent_from == ["owner-pump-write"] * 2
        settle(pump, hold)                                    # the EOF after the loss is NOT a second loss
        assert losses == [ep.LossCause.WRITE] and conn.twin_closed
        assert ("conn", socket.SHUT_RDWR) in conn.shutdowns and ("twin", socket.SHUT_WR) in conn.shutdowns

    def test_write_cap_remaining_budget_shrinks():
        hold = Hold(); clock = FakeClock(); conn = FakeConn(hold, send_script=[5, ("timeout", 1.0), 3, ("timeout", 5.0)], clock=clock)
        pump, *_ = mk(conn, clock=clock); pump.send_event({"event": "pong", "id": ID}); pump.start()
        assert wait_until(lambda: pump.lost); settle(pump, hold)
        line = frame({"event": "pong", "id": ID})
        assert conn.twin.timeouts == [2.0, 2.0, 1.0] and conn.sent == [line, line[5:], line[8:]]
        assert pump.loss_cause is ep.LossCause.WRITE           # 1 s + 5 s > the 2 s cap

    def test_send_oserror_is_io_loss():
        hold = Hold(); conn = FakeConn(hold, send_script=[BrokenPipeError()]); pump, *_ = mk(conn)
        pump.send_event({"event": "pong", "id": ID}); pump.start()
        assert wait_until(lambda: pump.lost); settle(pump, hold)
        assert pump.loss_cause is ep.LossCause.IO and pump.loss_detail == "BrokenPipeError"

    def test_lease_is_read_while_write_is_blocked():            # THE cold-load / blocked-receiver requirement
        h1, h2 = Hold(), Hold(); clock = FakeClock()
        conn = FakeConn(h1, ping(), h2, send_script=["block", ("timeout", 5.0)], clock=clock)
        pump, clock, timers, cmds, losses = mk(conn, clock=clock)
        ev = {"event": "final", "id": ID, "seq": 1, "text": "x" * 50}
        pump.send_event(ev); pump.start()
        assert conn.in_send.wait(5) and not pump.lost           # the writer IS blocked inside send
        clock.advance(1.0); h1.go.set()                         # ... while the reader takes the ping at t = 101
        assert wait_until(lambda: pump.last_ping_at == 101.0) and not pump.lost
        assert pump.lease_deadline == 107.0                     # lease renewed DURING the block
        conn.release.set(); settle(pump, h2)                    # unblock the writer: cap exceeded at its absolute deadline
        assert losses == [ep.LossCause.WRITE] and pump.loss_detail == "write cap exceeded"
        assert conn.twin.timeouts == [2.0, 1.0] and conn.sent == [frame(ev), frame(ev)]   # pong never written
        assert conn.timeouts == []

    def test_send_event_is_nonblocking_and_refuses_after_loss():
        hold = Hold(); clock = FakeClock(); conn = FakeConn(hold, send_script=["block", ("timeout", 5.0)], clock=clock)
        pump, *_ = mk(conn, clock=clock); pump.send_event({"event": "pong", "id": ID}); pump.start()
        assert conn.in_send.wait(5)
        t0 = time.monotonic(); pump.send_event({"event": "pong", "id": ID}); assert time.monotonic() - t0 < 0.05
        assert "MainThread" not in conn.sent_from              # the CALLER never touches the socket
        conn.release.set(); settle(pump, hold)                 # writer: TimeoutError, clock -> 105 > deadline 102
        assert pump.loss_cause is ep.LossCause.WRITE
        with pytest.raises(ep.PumpClosed): pump.send_event({"event": "pong", "id": ID})

    def test_outbound_queue_full_is_write_loss():
        hold = Hold(); clock = FakeClock(); conn = FakeConn(hold, send_script=["block"], clock=clock)
        pump, *_ = mk(conn, clock=clock, queue_max=2)
        pump.send_event({"event": "pong", "id": ID}); pump.start(); assert conn.in_send.wait(5)   # 1st is in send
        pump.send_event({"event": "pong", "id": ID}); pump.send_event({"event": "pong", "id": ID})  # 2 of 2 queued
        with pytest.raises(ep.PumpClosed): pump.send_event({"event": "pong", "id": ID})
        assert pump.loss_cause is ep.LossCause.WRITE and pump.loss_detail == "outbound queue full"
        conn.release.set(); settle(pump, hold)

    def test_loss_is_sticky_under_three_way_race():
        hold = Hold(); clock = FakeClock()
        conn = FakeConn(hold, send_script=["block", ("timeout", 5.0)], clock=clock)
        pump, clock, timers, cmds, losses = mk(conn, clock=clock)
        pump.send_event({"event": "pong", "id": ID}); pump.start(); assert conn.in_send.wait(5)
        barrier = threading.Barrier(3)
        def race(fn): barrier.wait(); fn()
        racers = [threading.Thread(target=race, args=(timers.live()[0].fire,)),   # lease expiry
                  threading.Thread(target=race, args=(hold.go.set,)),             # reader -> EOF
                  threading.Thread(target=race, args=(conn.release.set,))]        # writer -> cap exceeded
        for t in racers: t.start()
        for t in racers: t.join(5)
        settle(pump, hold)
        assert len(losses) == 1 and pump.loss_cause is losses[0]
        assert losses[0] in (ep.LossCause.LEASE, ep.LossCause.EOF, ep.LossCause.WRITE)   # first detector wins

    # --- graceful end ---
    def test_shutdown_writes_terminal_then_eof_is_idempotent_and_not_loss():
        hold = Hold(); conn = FakeConn(hold); pump, clock, timers, cmds, losses = mk(conn); pump.start()
        ended = {"event": "ended", "id": ID, "reason": "stopped", "recoverable": False}
        pump.shutdown(ended); pump.shutdown({"event": "ended", "id": ID, "reason": "idle", "recoverable": False})
        with pytest.raises(ep.PumpClosed): pump.send_event({"event": "pong", "id": ID})
        settle(pump, hold)                                       # the reader's EOF AFTER shutdown is not a loss
        assert conn.sent == [frame(ended)] and losses == [] and not pump.lost and pump.closed
        assert conn.shutdowns[0] == ("twin", socket.SHUT_WR)     # EOF only AFTER the last frame
        assert timers.live() == []                               # the lease timer was retired by shutdown

    def test_shutdown_after_loss_is_noop():
        pump, clock, timers, cmds, losses = mk(FakeConn(b"")); pump.start(); settle(pump)
        pump.shutdown({"event": "ended", "id": ID, "reason": "stopped", "recoverable": False})
        assert losses == [ep.LossCause.EOF] and not pump.closed and conn.sent == []

    def test_wait_returns_false_on_timeout():
        hold = Hold(); conn = FakeConn(hold); pump, *_ = mk(conn); pump.start()
        assert pump.wait(0.2) is False
        settle(pump, hold); assert pump.wait(1) is True and conn.closed

    def test_start_twice_raises():
        hold = Hold(); conn = FakeConn(hold); pump, *_ = mk(conn); pump.start()
        with pytest.raises(RuntimeError): pump.start()
        settle(pump, hold)

    # --- write_reject (the rejected-first-frame path T4.S7 calls before any pump exists) ---
    def test_write_reject_sends_error_then_eof():
        conn = FakeConn(); ep.write_reject(conn, "busy")
        assert conn.sent == [frame({"ok": False, "error": "busy"})] and conn.shutdowns == [("conn", socket.SHUT_WR)]
        assert conn.closed and conn.timeouts == [2.0]            # the connection thread may use the shared object here
        ep.write_reject(FakeConn(send_script=[BrokenPipeError()]), "unsupported_version")   # never raises

    # --- handoff: an existing FrameReader's unread bytes (S1's seam) are consumed before any socket read ---
    def test_handoff_reader_unread_is_consumed_first():
        go = threading.Event()                                  # the real socket stays silent until released, then EOF
        class Sock:
            def __init__(self, *c): self.c = list(c)
            def recv(self, n):
                if self.c: return self.c.pop(0)
                go.wait(5); return b""
        start = frame({"cmd": "editor-start", "version": 1, "id": ID, "context": ""})
        reader = ep.FrameReader(Sock(start + ping()).recv)     # editor-start + an immediate ping coalesced in ONE recv
        assert reader.read_frame_bytes() == start.rstrip(b"\n") and reader.unread == ping()   # what T4.S7 hands over
        conn = FakeConn(b"")                                     # its recv is never used: `reader=` wins
        pump, clock, timers, got, losses = mk(conn, reader=reader); pump.start()
        assert wait_until(lambda: conn.sent == [frame({"event": "pong", "id": ID})])   # answered from `unread`, no socket read
        assert got == [] and not pump.lost and [h.deadline for h in timers.armed] == [106.0, 106.0]   # lease re-armed (same instant)
        go.set(); assert pump.wait(5)
        assert losses == [ep.LossCause.EOF] and timers.live() == []

    # --- real socketpair, real timers (ThreadTimers), 0.4 s budgets ---
    def test_socketpair_lease_expires_without_ping():
        a, b = socket.socketpair(); losses = []
        pump = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=losses.append, lease_s=0.4)
        t0 = time.monotonic(); pump.start(); assert pump.wait(5)
        assert losses == [ep.LossCause.LEASE] and time.monotonic() - t0 < 3
        assert b.recv(1) == b""                                      # the peer saw EOF (shutdown); nothing was written
        b.close()

    def test_socketpair_blocked_receiver_trips_write_cap():
        a, b = socket.socketpair(); a.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4608); losses = []
        pump = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=losses.append, lease_s=5.0, write_cap_s=0.4)
        pump.send_event({"event": "final", "id": ID, "seq": 1, "text": "x" * 30000})   # > the ~9 KiB the peer can buffer
        t0 = time.monotonic(); pump.start(); assert pump.wait(5)
        assert losses == [ep.LossCause.WRITE] and pump.loss_detail == "write cap exceeded" and time.monotonic() - t0 < 3
        b.close()                                                    # never read from: the cap fired, not the lease

    def test_socketpair_ping_pong_then_graceful_ended():
        a, b = socket.socketpair(); b.settimeout(5); losses = []
        pump = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=losses.append, lease_s=5.0)
        pump.send_event({"ok": True, "event": "starting", "id": ID}); pump.start()
        assert json.loads(b.recv(4096)) == {"ok": True, "event": "starting", "id": ID}
        b.sendall(ping()); assert json.loads(b.recv(4096)) == {"event": "pong", "id": ID}
        ended = {"event": "ended", "id": ID, "reason": "stopped", "recoverable": False}
        pump.shutdown(ended)
        assert b.recv(4096) == frame(ended) and b.recv(4096) == b""   # last frame, then EOF
        assert pump.wait(5) and losses == [] and pump.closed; b.close()
  - DO NOT: open a listening socket; use real sleeps to order events (the only real waits are `wait_until` /
    `Event.wait(5)` bounded joins for state another THREAD produces, and the three socketpair tests); access
    pump internals (`_q`, `_lock`, `_on_loss_cb` …) from tests — drive everything through the public surface;
    modify S1's or S2's tests; weaken an assertion to pass.

Task 3: VALIDATE (L1–L4). If committing: "P1.M1.T3.S3: owner connection pump — 2 s/6 s ping-lease,
  single serialized bounded writer (2 s whole-frame cap via dup()), sticky loss + terminal callbacks,
  absolute monotonic deadlines; deadline constants exported for session and clients".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — absolute deadline per frame; the socket timeout is the REMAINING budget (CRITICAL #3/#4):
deadline = clock() + cap_s
while sent < len(line):
    left = deadline - clock()
    if left <= 0: return False            # cap exceeded -> one WRITE loss
    conn.settimeout(left)                 # conn is the dup() twin — never the shared object
    try: n = conn.send(view[sent:])       # offset-tracked; never sendall (CRITICAL #3)
    except TimeoutError: continue

# PATTERN 2 — lease with a generation counter (CRITICAL #5/#8):
with lock: gen += 1; cancel(old); timer = arm(last_ping_at + LEASE_S, lambda: _lease_fired(gen))
def _lease_fired(gen): with lock: if gen != self._lease_gen or lost or closing: return; _on_loss(LEASE)
def _renew_lease(): with lock: now > last_ping_at + LEASE_S -> expired (loss) else last_ping_at = now; _arm_lease()

# PATTERN 3 — sticky loss, wake both threads, callback once outside the lock (CRITICAL #6):
with lock: if lost or closing: return False; lost = True; cause = …
conn.shutdown(SHUT_RDWR); on_loss_cb(cause)      # recv -> b"" -> eof -> _on_loss returns False; send -> OSError -> same

# PATTERN 4 — graceful terminal cannot be overtaken (CRITICAL #7): ONE lock hold sets _closing AND queues
# the terminal; send_event checks _closing under the same lock; the writer exits on "_closing and empty".
```

### Integration Points

```yaml
UPSTREAM CONSUMED — P1.M1.T3.S1 (landed): FrameReader (read_frame_bytes/unread; FrameError eof|frame-too-large|io),
  encode_line, MAX_FRAME_BYTES. P1.M1.T3.S2 (implementing; Task 0 gate): validate_request, ProtocolError(.code/.detail),
  native_error_reply. Nothing in those sections is modified.

DOWNSTREAM CONSUMERS (keep names EXACT):
  - P1.M1.T4.S7 (activation in ControlServer._handle): after the first frame, request_kind == "editor-start" ->
    validate_request -> busy/duplicate checks -> write_reject(conn, code) on rejection; on acceptance construct
    OwnerPump(conn, id, reader=<the live FrameReader>, on_command=…, on_loss=…), send_event({"ok": True,
    "event": "starting", "id": id}), start(), run the session start on the connection thread (cold load up to
    START_CAP_S — the pump services ping/stop/EOF meanwhile), then wait().
  - P1.M1.T4.S2 (sequenced offers): send_event(final) from any thread (non-blocking); ACK_DEADLINE_S is its
    5 s reference; on_command delivers {"cmd":"applied","seq":n}.
  - P1.M1.T4.S5 (stop/cancel/drain): on_command stop|cancel|lost on the reader thread — enqueue, never block.
  - P1.M1.T4.S6 (ended + hints): shutdown(ended_frame) exactly once; LossCause.end_reason for the reason.
  - P1.M1.T3.S4 (startup fence): START_CAP_S reference; "Stop during startup" arrives via on_command while
    the start worker is still running.
  - P1.M2.T1.S2 / P1.M2.T2.S1 (TS/Lua clients): mirror PING_INTERVAL_S=2 / LEASE_S=6 (client side: pong
    deadline 6 s; ping every 2 s incl. load + drain; close on expiry).

UNCHANGED: daemon.py, ctl.py, config.py, recorder_host.py, every existing test; no new dependency.
```

## Validation Loop

> Full paths; two timeouts on every pytest (inner `timeout`, bash-tool ≥ +60). pytest only. No listener.

### Level 1: Siblings intact + this task's symbols exported

```bash
cd /home/dustin/projects/voice-typing
test -f voice_typing/editor_protocol.py && grep -c 'def validate_request\|class ProtocolError\|def native_error_reply\|class FrameReader\|def encode_line' voice_typing/editor_protocol.py   # 5
git diff -- voice_typing/editor_protocol.py | grep -c '^-[^-]'    # 0 (append-only; a docstring sentence is an addition)
timeout 60 .venv/bin/python - <<'PY'
import inspect
from voice_typing import editor_protocol as ep
assert ep.MAX_FRAME_BYTES == 32768 and {"read_frame_bytes"} <= {n for n,_ in inspect.getmembers(ep.FrameReader, inspect.isfunction)}
assert callable(ep.validate_request) and callable(ep.native_error_reply) and issubclass(ep.ProtocolError, Exception)   # S2 intact
for n in ["PING_INTERVAL_S","LEASE_S","WRITE_CAP_S","START_CAP_S","ACK_DEADLINE_S","OUTBOUND_QUEUE_MAX","deadline_after",
          "remaining","LossCause","PumpClosed","send_line_capped","ThreadTimers","write_reject","OwnerPump"]:
    assert hasattr(ep, n), n
for m in ["start","send_event","shutdown","wait","lost","loss_cause","loss_detail","closed","last_ping_at","lease_deadline"]:
    assert hasattr(ep.OwnerPump, m), m
assert (ep.PING_INTERVAL_S, ep.LEASE_S, ep.WRITE_CAP_S, ep.START_CAP_S, ep.ACK_DEADLINE_S) == (2.0, 6.0, 2.0, 30.0, 5.0)
print("L1 PASS: S1/S2 intact; pump surface exported")
PY
timeout 60 .venv/bin/python -m py_compile voice_typing/editor_protocol.py tests/test_editor_pump.py && echo "L1 PASS: compiles"
```

### Level 2: The new suite + the sibling suites (unchanged)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_editor_pump.py -q 2>&1 | tail -3          # green, < 30 s
timeout 300 .venv/bin/python -m pytest tests/test_editor_protocol.py tests/test_editor_protocol_vectors.py -q 2>&1 | tail -3   # S1 + S2 green UNMODIFIED
```

### Level 3: The behavioral proof (inline, real socketpair + real timers — no files)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python - <<'PY'
import json, socket, time
from voice_typing import editor_protocol as ep
ID = "123e4567-e89b-42d3-a456-426614174000"
# (1) lease: no ping -> exactly one LEASE loss, peer sees EOF, nothing written
a, b = socket.socketpair(); L = []
p = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=L.append, lease_s=0.4); p.start(); assert p.wait(5)
assert L == [ep.LossCause.LEASE] and L[0].end_reason == "timeout" and b.recv(1) == b""; b.close()
# (2) blocked receiver: write cap, not lease
a, b = socket.socketpair(); a.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4608); L = []
p = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=L.append, lease_s=5.0, write_cap_s=0.4)
p.send_event({"event": "final", "id": ID, "seq": 1, "text": "x" * 30000}); p.start(); assert p.wait(5)
assert L == [ep.LossCause.WRITE] and p.loss_detail == "write cap exceeded"; b.close()
# (3) ping -> pong -> graceful ended -> EOF, no loss; reader keeps working while a write is slow
a, b = socket.socketpair(); b.settimeout(5); L = []
p = ep.OwnerPump(a, ID, on_command=lambda o: None, on_loss=L.append, lease_s=5.0); p.start()
b.sendall(ep.encode_line({"cmd": "ping", "id": ID})); assert json.loads(b.recv(4096)) == {"event": "pong", "id": ID}
p.shutdown({"event": "ended", "id": ID, "reason": "stopped", "recoverable": False})
assert json.loads(b.recv(4096))["event"] == "ended" and b.recv(4096) == b"" and p.wait(5) and L == []; b.close()
print("L3 PASS: lease, write cap, ping/pong + graceful end")
PY
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only; git status --short | grep '^??'        # ⊆ {voice_typing/editor_protocol.py, tests/test_editor_pump.py}
git diff --exit-code -- voice_typing/daemon.py voice_typing/ctl.py voice_typing/config.py voice_typing/recorder_host.py pyproject.toml tests/test_editor_protocol.py tests/test_editor_protocol_vectors.py tests/fixtures/editor_v1.json && echo "L4 PASS: out-of-scope files untouched"
grep -c 'import voice_typing.daemon\|from voice_typing.daemon\|sendall(' voice_typing/editor_protocol.py   # 0
grep -n 'ACK_DEADLINE_S\|START_CAP_S' voice_typing/editor_protocol.py | grep -v 'float = \|^.*#\|"""' | grep -v '^\s*$' | wc -l   # 0 uses beyond the constant definitions (reference only)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: S1's and S2's symbols intact (append-only diff, zero deletions); all 15 new symbols + 10 members exported; compiles.
- [ ] L2: `test_editor_pump.py` green (< 30 s); S1's and S2's suites green unmodified.
- [ ] L3: inline proof — lease expiry, blocked receiver → write cap, ping/pong → graceful `ended` → EOF.
- [ ] L4: diff ⊆ the two files; no daemon import; no `sendall`; no ACK/start-cap enforcement in the module.

### Feature Validation
- [ ] Lease: armed at start, re-armed per valid ping (old timer cancelled), stale fire ignored, late ping = loss, timer fire = loss.
- [ ] Writer: one absolute 2 s deadline per line, offset-tracked sends, timeouts only on the `dup()` twin (asserted), cap/io → one loss.
- [ ] Sticky loss exactly once under a 3-way race; socket shut down; `send_event` → `PumpClosed` afterwards.
- [ ] Reader services ping/commands while the writer is blocked (asserted mid-block, not after).
- [ ] Graceful `shutdown(ended)` → last line then EOF, idempotent, no loss; `write_reject` → error line + EOF.
- [ ] Loss taxonomy: EOF/IO/FRAME → `disconnected`, REQUEST → `delivery_failed`, LEASE → `timeout`; details never echo bytes.

### Code Quality / Scope Validation
- [ ] No `_handle`/`_dispatch` wiring (T4.S7), no reservation/offer/ACK state (T3.S4/T4.S2), no daemon import.
- [ ] Callbacks documented: exactly once / detecting thread / no lock / must not block, raise, or do I/O.
- [ ] Tests hermetic: fake conn + fake clock + manual timers for races; socketpair only for the three integration cases; no sleeps for ordering.

### Documentation & Deployment
- [ ] Mode A docstrings on the section and `OwnerPump`: thread ownership, absolute deadlines, terminal callback contract.
- [ ] Module docstring gained the one-sentence pump note; constants carry their §4.8.1 clause and owner.

---

## Anti-Patterns to Avoid

- ❌ Don't `settimeout()` the shared socket object from the writer — it leaks into the reader's blocking `recv` (`FrameError("io")` → spurious loss). Use `conn.dup()`. (CRITICAL #2.)
- ❌ Don't retry `sendall()` after a timeout — an unspecified prefix may already be on the wire. Track the offset with `send`. (CRITICAL #3.)
- ❌ Don't use relative sleeps or re-arm a timer with a fresh budget — compute one absolute deadline per frame/lease and wait on the remainder. (CRITICAL #4.)
- ❌ Don't let a late ping renew an expired lease, or let a superseded timer fire a loss — generation counter + deadline re-check. (CRITICAL #5/#8.)
- ❌ Don't call `on_loss` twice (EOF after lease, OSError after shutdown) or under the pump lock — sticky flag, shutdown first, callback outside the lock. (CRITICAL #6.)
- ❌ Don't queue anything after the terminal `ended`, or treat EOF after a graceful `shutdown()` as loss. (CRITICAL #7.)
- ❌ Don't enforce the 30 s Start cap or the 5 s ACK deadline in the pump ("offer timeout belongs to session, not ping path") — export the constants only.
- ❌ Don't wire the pump into `daemon.py`, create `editor_session.py`, validate outbound events, or add a dependency — T4.S7 / T3.S4 / T4.S2 own those.
- ❌ Don't put frame bytes, request text or seed text into loss details, callbacks or logs. (CRITICAL #10.)
- ❌ Don't run pytest without both timeouts, invent ruff/mypy gates, or modify existing tests.

---

## Confidence Score

**9/10** for one-pass implementation success. The transport is fully specified as verbatim code with
its two non-obvious hazards identified up front and pinned by assertions: the per-object `settimeout`
leak (fixed by `dup()`, asserted by an empty shared-object timeout log) and the `sendall`-after-timeout
resend (fixed by an offset-tracked `send` loop, asserted on the recorded byte slices). Every race in the
item's description (lease during cold load, lease during a blocked write, three-way sticky loss, stale
timer) has a deterministic test built on a fake clock, manual timers and per-`Hold` barriers — no sleeps —
and the write cap is additionally proven on a real socketpair with the probe-validated `SO_SNDBUF`
technique. The −1 is the dependency on S2 landing first (Task 0 gates; append-only makes the merge safe)
and the inherent fragility of any threaded test-suite: the design removes timing dependence from every
race (per-`Hold` barriers, a fake clock, manual timers), but a socketpair kernel buffer or a loaded CI
box can still slow the three real-timer cases — they use 0.4 s budgets under 3 s asserts.
