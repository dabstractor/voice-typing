# Owner connection pump — research notes (P1.M1.T3.S3)

## 1. On-disk state (checked this session)
- `voice_typing/editor_protocol.py` exists with S1 only: `MAX_FRAME_BYTES`, `FrameError`, `FrameReader`
  (`read_frame_bytes`, `unread`, `_drain_runaway`), `encode_line`. `daemon.py:3527` `_handle` uses
  `FrameReader(conn.recv)`; connections are thread-per-connection (`daemon.py:3505`).
- **S2 (validators) NOT on disk yet** (`validate_request`, `ProtocolError`, `native_error_reply` absent) →
  Task 0 of the PRP gates on its symbols; STOP if absent (never author S2's code).
- Python 3.12.10 (`socket.timeout is TimeoutError`, subclass of `OSError`).

## 2. Spec extraction (PRD §4.8.1 B, prd_snapshot.md:448-475)
| Timer | Value | Owner | Pump's role |
|---|---|---|---|
| Start cap incl. load/priming | 30 s | session (T3.S4/T4.S7) | export `START_CAP_S` reference only |
| client ping cadence | 2 s | client | export `PING_INTERVAL_S` (client deadline reference) |
| lease without valid ping | 6 s | **pump** | enforced (timer + late-ping check) |
| whole-frame bounded write | 2 s | **pump** | enforced per encoded line (absolute deadline) |
| offer ACK deadline | 5 s | session (T4.S2) | export `ACK_DEADLINE_S` reference only |
Pump must service ping/stop/cancel/lost/EOF during cold load → reader and writer are pump-owned threads,
independent of the session's start worker. Loss causes → `ended.reason`: lease→`timeout`,
bad request/id/seq→`delivery_failed`, everything else→`disconnected`.

## 3. Design decisions
- D1 Two pump threads (`owner-pump-read`, `owner-pump-write`) + an injectable timer for the lease. Reader
  = `FrameReader` loop (handoff: pass the existing reader so `unread` survives). Writer = bounded
  `queue.Queue` of **encoded bytes**; `send_event` does `encode_line` on the caller thread (so an oversize
  event is the caller's synchronous error) and a non-blocking `put_nowait` — safe from the control lock /
  recorder reader thread (contract: no socket I/O there).
- D2 Absolute monotonic deadlines everywhere: `deadline = clock() + budget` computed once; waits use
  `remaining = max(0, deadline - clock())`. Injectable `clock`.
- D3 Lease: armed at `start()` (`last_ping_at + LEASE_S`), re-armed per valid ping with a generation
  counter so a stale timer fire is ignored; a ping arriving after the deadline is loss (strict: the
  timer thread may be scheduled late). Works with `ManualTimers` — no real waiting in unit tests.
- D4 Sticky loss: `_on_loss` returns False if already lost/closing; first cause wins; shutdown(SHUT_RDWR)
  wakes both threads; `on_loss` runs exactly once on the detecting thread with no lock held.
- D5 **`settimeout` is per socket OBJECT** — a writer calling it on the shared socket would make the
  reader's blocking `recv` time out (`FrameError("io")` → spurious loss). Writer uses `conn.dup()`
  (new object, default blocking, same socket). Pinned by a fake whose shared-object `settimeout` is logged
  and asserted empty.
- D6 Write cap via manual `send` loop with byte offset (`sendall` after a timeout may have sent an
  unspecified prefix → never retry from byte 0).
- D7 Graceful end: `shutdown(terminal)` queues the `ended` line then closes write side → "last frame then
  EOF"; EOF after that is NOT loss. `write_reject(conn, code)` = `native_error_reply` + EOF for a rejected
  first frame (T4.S7 calls it).
- D8 Scope: NOT wired into `_handle`/`_dispatch` (T4.S7). No daemon import.

## 4. Probes
- SO_SNDBUF 4608 on a socketpair → effective 9216; `send` blocks after 9088 bytes and raises `TimeoutError`
  (OSError) under `settimeout(0.4)`. ⇒ a 30 KiB event to a non-reading peer deterministically trips the cap.

## 5. Cross-item note
- PRD table: `{"ok":true,"event":"starting","id":"..."}`; S2's `validate_event` spec for `starting` is
  `{event,id}` (closed schema → `ok` would be rejected). The pump does not validate outbound events
  (T4.S2 does) so S3 is unaffected, but T4.S2/T4.S7 must reconcile (allow optional `ok` on `starting`,
  or emit without it).
