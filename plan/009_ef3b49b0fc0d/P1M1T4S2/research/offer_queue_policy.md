# Research — P1.M1.T4.S2: one sequenced offer + verified ACK (editor_session.py FIFO policy)

Sources (read this session, HEAD 4ed39cb-era working tree):
- `plan/009_ef3b49b0fc0d/architecture/system_context.md` — "Buffer ownership and recovery" (the 8-slot FIFO,
  mark-before-write, exact-ACK settle, duplicate-ACK harmless, deadlines: ping 2 s / lease 6 s / write 2 s /
  ACK 5 s) and "Control/recorder boundaries" (no waits/writes on the control lock or recorder reader).
- `plan/009_ef3b49b0fc0d/P1M1T4S1/PRP.md` — NativeRecovery contract (being implemented in parallel).
- `voice_typing/editor_protocol.py` (T3.S2/S3, at HEAD): constants, enums, validators, pump/write return types.
- `voice_typing/editor_session.py` (T3.S4, in flight, 115 lines): reservation classes + module discipline.

## 1. Protocol facts the policy reuses (editor_protocol.py)
- `validate_request(obj)` :277 — `{"cmd":"applied","id":<uuidv4>,"seq":int>=1}` closed field set; raises
  `ProtocolError(code, detail)`; `busy`/`duplicate_id` are STATE decisions never raised there.
- `validate_event(obj)` :322 — `final` event `{"event":"final","id","seq","text"}`, `text` <=
  `MAX_FINAL_TEXT_BYTES` (4 KiB UTF-8) else `too_large`; `ended.reason` must be in `END_REASONS`.
- Helpers: `is_uuid_v4`, `utf8_len`, `has_lone_surrogates` (:170-184).
- `EndReason` :129 — `stopped idle cancelled target_lost disconnected timeout delivery_failed load_failed
  shutdown`. `LossCause` :414 — REQUEST (ProtocolError/wrong id/2nd start) -> `delivery_failed`; LEASE ->
  `timeout`; WRITE -> `disconnected`.
- Write path: `send_line_capped(conn, line, cap_s=WRITE_CAP_S)` -> bool (:472); `OwnerPump.send_event(obj)
  -> None` (:628, enqueues to the serialized writer; `pump.closed`/`pump.lost` observable).

## 2. T3.S4's module discipline (editor_session.py header) — the policy MUST match it
- "No I/O, no sockets, no threads started, no daemon import. The only import is editor_protocol."
- "Every method is a PURE transition that MUST run under the CALLER's lock (the daemon's `_lock`);
  nothing here takes a lock."
- Injected monotonic clock; ABSOLUTE deadlines; fixed codes only — never request/seed/frame text.
- `__all__` is an explicit list at :26. Reservation classes :28-115 (Stage/Owner/EndRecord/
  NativeReserveResult/NativeReservation) — DO NOT EDIT them; APPEND only.
- Consequence for "no socket wait in state transitions": the socket write cannot sit inside a transition
  that the caller holds `_lock` around. Split the offer into `begin_offer` (pure transition: records the
  attempt + stamps the deadline) → caller writes OUTSIDE the lock → `finish_offer(ok)` (pure transition).
  An ACK arriving between the two finds `outstanding` already set and settles normally; a then-"failed"
  write must NOT revoke an already-settled offer (the verified ACK wins).

## 3. NativeRecovery operations consumed (T4.S1 contract)
- `retain_final(sid, seq, text) -> bool` (False on invalid text; auto-creates the active session if none —
  hence the queue needs a `closed` guard so a post-end late final cannot resurrect a session).
- `mark_offer_attempted(sid, seq) -> bool`, `settle_final(sid, seq) -> bool` (removes; budget reclaimed),
- `end_session(sid, reason)`, `active_id()`, `counts()`, `clear()`. All lock-protected, never raise.

## 4. Design decisions (this PRP)
- Class `OfferQueue` in editor_session.py; owns ALL recovery calls (T4.S4 only calls `enqueue`).
- seq: monotonic per session from 1 (validator minimum); assigned at enqueue; identity = (session_id, seq).
- Capacity counts UNSETTLED items (pending + the one outstanding): <= 8. Overflow: retain (recovery) and
  REVOKE (`delivery_failed`) — never insert truncated, never drop silently.
- Text > 4 KiB UTF-8 / lone surrogates / recovery rejects: retain if possible, REVOKE (`delivery_failed`).
- `begin_offer`: only if not revoked/closed, no outstanding, pending item exists. Order: mark attempted in
  recovery (BEFORE write), stamp `deadline = clock() + ACK_S` (so the 2 s write cap is inside the 5 s ACK
  budget), validate the event with `validate_event`, set `outstanding`, return `OfferAttempt`.
- `finish_offer(ok)`: ok → nothing more (outstanding stands); not ok and still outstanding → revoke
  (`delivery_failed`); already settled → no revoke.
- `ack(obj, now)`: malformed (validate_request raises / not a dict) → revoke `delivery_failed`; id != sid →
  revoke `delivery_failed`; seq == outstanding.seq → `settle_final`, clear outstanding, last_ack=seq →
  SETTLED; seq == last_ack → DUPLICATE (no-op; never touches the new outstanding's deadline); else →
  revoke `delivery_failed` (STALE: never offered, already settled older, or future).
- `check_deadline(now)`: outstanding and now >= deadline → revoke `timeout`. Deadline is OWNED by the
  queue (documented); the caller's timer calls this — no threads here.
- `revoke(reason)` sticky, first reason wins; `clear_pending()` drops unattempted items (recovery untouched);
  `close()` after `end_session` blocks further enqueues. `drain_pending()` = outstanding or pending exist.
- Tests: NEW `tests/test_editor_offer_queue.py` (T3.S4 owns `tests/test_editor_session.py`); real
  `NativeRecovery` + fake clock + fake write result; no sockets/threads.
