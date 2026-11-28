# P1.M1.T4.S7 — seam census (verified first-hand at HEAD `0c2a50c`, 2026-11-28)

Line numbers are from the tree at HEAD `0c2a50c` ("Native stop/cancel/drain wind-down (P1.M1.T4.S5)").
`git status --short` at research time: only plan/ files dirty — S6 had NOT yet touched `daemon.py`.
S6 lands concurrently and will shift every line below: **anchor by symbol**, not by number.

## voice_typing/daemon.py

| symbol | line | notes |
|---|---|---|
| `NATIVE_SETTLE_TIMEOUT_S` | 250 | 5.0 s ACK-settlement window after the ASR drain (S5) |
| `ArmOutcome` | 304 | frozen: `ok, listening, reason, context_seeded: bool\|None, tokens: int\|None, arm_seq` — NO prompt-text field |
| `_default_control_socket_path()` | 595 | `$XDG_RUNTIME_DIR/voice-typing/control.sock` |
| `VoiceTypingDaemon.__init__` native block | 1040-1074 | `_native_seq`, `_native_timer` (Start-cap watchdog), `_native_clock = time.monotonic`, `_native_timers = ThreadTimers(time.monotonic)` (tests inject FakeClock/ManualTimers), `_native_end_cb`, `_native_end_delivered`, `_native_drain_boundary`, `_native_settle_timer`, `_native_recovery = session_recovery.NativeRecovery()` (:1071), **`_native_offer_evt = threading.Event()` (:1074)** |
| `VoiceTypingDaemon.cancel()` | 2463 | **:2491 `if self._native_owner_live_locked():` "cancel is not an owner command" (S4)** → a generic `cancel` under a live owner already returns busy; expect NO `_dispatch` change (Task 0 confirms) |
| `_unload_host` | 2695 | :2906 never supersedes/joins a native owner |
| `_native_owner_live_locked()` | 3067 | |
| `_native_blockers_locked()` | 3072 | generic arm loading/listening/draining → busy |
| `_native_open_capture_locked` / `_native_close_capture_locked` | 3078 / 3116 | builds `OfferQueue(native.owner.id, self._native_recovery)` (:3108); `_native_offer_evt.clear()` at :3110 and :3125 |
| `_native_on_final(text)` | 3180 | **CONSUMER CONTRACT :3190-3204** (quoted in contract_chain.md). `with self._lock: q.enqueue(cleaned)`; **only `EnqueueOutcome.QUEUED` sets `_native_offer_evt` (:3234-3235)**; REVOKED = recovery-only, no wake. Logs outcome code + pending count only. |
| `native_id_known(sid)` | 3242 | duplicate_id predicate |
| `reserve_native(conn, session_id, *, on_end=None) -> NativeReserveResult` | 3247 | docstring: "INTERNAL (T4.S7 wires `editor-start` to it). ATOMIC check-and-reserve under _lock, in this order: shutdown → busy; id active/retained → duplicate_id; native owner live → busy; any generic arm … → busy. On acceptance mints the owner token, installs the STARTING reservation, registers the id, and (outside the lock) arms the 30 s Start-cap watchdog. **Spawns nothing — call begin_native_start(token) after emitting `starting`. Never writes.**" Non-uuid id → `NativeReserveResult(False, None, "invalid_request")`. |
| `_native_start_expired(token)` | 3277 | timer thread; ends as `("timeout", "start-cap")` only if still the current STARTING owner past its deadline, then `_flush_native_end()` |
| `_native_can_commit_locked(token)` | 3308 | |
| `begin_native_start(token, *, seed=None, streaming=None) -> bool` | 3289 | docstring: "INTERNAL (T4.S7): spawn the session's lifecycle thread … False if the token is no longer the current STARTING owner inside its cap … or a worker already exists. Idempotent per token." Spawns `native-start-{token}` daemon thread → `_native_start_worker`. **S7 adds `on_committed=None` here.** |
| `_end_native_locked` / `_claim_native_end_locked` / `_flush_native_end` | 3322 / 3358 / 3366 | S5 terminal action / exactly-once claim / off-lock flush (S6 restructures the flush) |
| `terminate_native(reason, *, cause=None, token=…)` | 3381 | |
| `_native_drain_or_stop` | 3401 | |
| `native_stop(reason="stopped", *, token=None) -> EndRecord \| None` | 3422 | **CONSUMER CONTRACT :3442-3453**. STARTING → end `("stopped","stop-during-start")`; LISTENING → `r.begin_drain(reason)` + **`self._native_offer_evt.set()` ("wake the pump: `finishing` before any offer", :3464)** under `_lock`, then bounded ASR drain or mic-off now; DRAINING → None. |
| `_native_mic_closed_locked` | 3485 | `_disarm` tail: revoked queue → end with the revocation reason; nothing unsettled → end now; else arm the ≤5 s settlement window |
| `_native_settle_step_locked(now)` / `native_settle_kick(*, token=None)` | 3514 / 3534 | **CONTRACT :3539-3543**: "without the kick `ended` still arrives, but only at the 5 s deadline; a stale set after close is harmless (q is None); while DRAINING the queue stays open and unrevoked for stop/idle — keep offering pending finals." |
| `native_cancel(*, token=None) -> EndRecord \| None` | 3551 | revoke + clear_pending → end `("cancelled","cancel")` → mic off in the same hold → off-lock `host.cancel()` (gated on `_text_in_flight`). Never drains. |
| `native_lost(reason, cause=None, *, token=…) -> EndRecord \| None` | 3579 | loss funnel; :3585 "the queue is already revoked, so its enqueue returns REVOKED and the pump is …" |
| `_native_start_worker(token, *, seed, streaming)` | 3623 | `_start_fenced(seed, streaming=, timeout=remaining(owner.deadline), reject_busy=True, native_tok=token)`; on failure maps `_NATIVE_START_FAILURE`; `committed = out.ok and self._native is r and r.stage is Stage.LISTENING`; `self._flush_native_end()`; **if committed: `r.end_evt.wait()`** then flush again. **S7 hook point: call `on_committed(out)` off-lock right after `committed` is True (before the park).** |
| `start_context` / `_context_reply` | 3657-3715 | the `context_seeded` / `context_reason` (`empty`/`disabled`/`unavailable`) derivation to MIRROR in the `listening` frame; `confirmed = out.context_seeded is True` |
| `status_snapshot()` | 3931 | S6 adds the always-present `native` block `{state,id,reason,recoverable,hint}` |
| `_normalize_context(text)` | 4197 | seed normalisation (whitespace → empty) |
| `_cmd_streaming(cmd)` | 4214 | None for plain commands |
| `class ControlServer` | 4226 | docstring :4227-4250 (protocol list; already names "the native v1 owner/lease is P1.M1.T3.S4 / P1.M1.T4.S7" :4249) |
| `ControlServer.__init__(daemon, *, socket_path=None, on_quit=None, accept_timeout=0.3)` | 4272 | `_daemon, _socket_path, _on_quit, _accept_timeout, _sock, _thread, _stop, _lock` |
| `ControlServer.start()` | 4291 | dir 0700, unlink stale sock, bind, chmod 0600, listen(8), accept thread (idempotent) |
| `ControlServer.stop()` | 4329 | stop Event + close socket + join ≤2 s + unlink |
| `ControlServer._handle(conn)` | 4373 | **the edit point.** `reader = FrameReader(conn.recv)` (:4401); `wfile = conn.makefile("wb")`; loop: `read_frame_bytes()` → `FrameError` eof/partial (`{"ok":False,"error":"partial frame at EOF"}`) / frame-too-large (one reply, resync) / io (break); strict `raw.decode("utf-8")` → `{"ok":False,"error":"invalid UTF-8 frame"}` and CONTINUE; `response = self._dispatch(line.strip())`; `wfile.write(encode_line(response)); flush`; break on `shutting_down`. `finally`: close wfile, close conn. "no read deadline exists here by design". |
| `ControlServer._dispatch(line: str) -> dict` | 4457 | json.loads → malformed reply; non-dict → error; `toggle*`/`start*` → `getattr(out,"reason",None)=="busy"` → `{"ok":False,"listening":False,"busy":True,"error":"busy: a native editor session owns the mic"}` (S4); `start-context` (S5); `stop` → `d.stop()` + status; `cancel` → `d.cancel()`; `status`; `quit` → `request_shutdown()` + on_quit → `{"ok":True,"shutting_down":True}`; `session`; else `{"ok":False,"error":f"unknown command: {cmd!r}"}` |
| `main()` | 4732 | `ControlServer(daemon, on_quit=daemon.shutdown)` :4782 |

## voice_typing/editor_protocol.py (T3.S1–S3; DOCS ONLY in S7)

| symbol | line | notes |
|---|---|---|
| `MAX_FRAME_BYTES` | 22 | 32 KiB incl. newline |
| `FrameError(reason, detail="")` | 25 | |
| `FrameReader(recv, …)` | 34 | `unread()` :50 (handoff bytes), `read_frame_bytes()` :53, `_drain_runaway` :76 |
| `encode_line(obj)` | 98 | `json.dumps(ensure_ascii=False)` + `\n`; FrameError("frame-too-large") |
| `PROTOCOL_VERSION = 1` | 113 | |
| `MAX_CONTEXT_BYTES = 4096`, `MAX_FINAL_TEXT_BYTES = 4096` | 115-116 | |
| `NativeErrorCode` | 119 | invalid_request, too_large, unsupported_version, busy, duplicate_id (last two "emitted elsewhere") |
| `EndReason` | 129 | stopped, idle, cancelled, target_lost, disconnected, timeout, delivery_failed, load_failed, shutdown |
| `ContextReason` | 137 | empty, disabled, unavailable |
| `ProtocolError(code, detail="")` | 156 | |
| `native_error_reply(code)` | 165 | the refusal reply body (`{"ok":False,"error":<code>}`) |
| `is_uuid_v4` / `utf8_len` | 170 / 175 | |
| `_REQUEST_SPECS` | 258 | CLOSED schemas: `editor-start {cmd,version,id,context}`, `ping {cmd,id}`, `applied {cmd,id,seq}`, `stop {cmd,id}`, `cancel {cmd,id}`, `lost {cmd,id}` — **plain `stop`/`cancel` are native cmds too ⇒ never branch on `request_kind` for first-frame detection** |
| `request_kind(obj)` | 270 | |
| `validate_request(obj)` | 277 | precedence: shape → `invalid_request`; version value → `unsupported_version` (editor-start only); context > 4 KiB → `too_large`; `applied.seq` int ≥ 1 |
| `_EVENT_SPECS` | 306 | `starting {event,id}` (**no `ok` key**), `listening {event,id,context_seeded,context_reason?}`, `pong {event,id}`, `final {event,id,seq,text}`, `finishing {event,id}`, `ended {event,id,reason,recoverable}` |
| `validate_event(obj)` | 322 | `context_reason` only when `context_seeded` is False; `final.text` ≤ 4 KiB; `ended.reason ∈ END_REASONS` |
| `PING_INTERVAL_S=2.0, LEASE_S=6.0, WRITE_CAP_S=2.0, START_CAP_S=30.0, ACK_DEADLINE_S=5.0, OUTBOUND_QUEUE_MAX=64, _PUMP_POLL_S=0.1` | 395-401 | START_CAP_S / ACK_DEADLINE_S are SESSION-owned (exported constants only) |
| `LossCause` | 414 | EOF, IO, FRAME → `end_reason == "disconnected"`; REQUEST → `"delivery_failed"`; LEASE → `"timeout"`; WRITE → `"disconnected"` |
| `PumpClosed(cause)` | 433 | raised by `send_event` after loss/closing or on a full queue (`.cause`) |
| `send_line_capped(conn, line, *, cap_s, clock) -> bool` | 472 | offset-tracked, never resends; SO_SNDTIMEO, never settimeout |
| `ThreadTimers(clock)` | 501 | `arm(deadline, fire) -> handle`, `cancel(handle)` (static) |
| `write_reject(conn, code, *, cap_s)` | 518 | "A REJECTED FIRST request (**T4.S7 calls this**; S2's code): write native_error_reply(code) under the write cap, then EOF … never raises, never echoes the request." |
| `OwnerPump(conn, session_id, *, on_command, on_loss, reader=None, clock=time.monotonic, timers=None, lease_s=LEASE_S, write_cap_s=WRITE_CAP_S, queue_max=OUTBOUND_QUEUE_MAX)` | 533 / 564 | threads `owner-pump-read` (FrameReader loop, validate_request, routes ping→pong+lease, applied/stop/cancel/lost→`on_command(obj)`; never writes) and `owner-pump-write` (the ONLY writer, on `conn.dup()`); lease timer via `timers` (ThreadTimers or the test's ManualTimers). `on_command` runs on the reader thread: "must not block / raise / do I/O"; a raise → REQUEST loss. `on_loss(cause)` EXACTLY ONCE on the detecting thread after `SHUT_RDWR`, no pump lock held. |
| `OwnerPump.start()` | 615 | arms lease, spawns threads; once per pump |
| `OwnerPump.send_event(obj)` | 628 | encode on caller thread + `put_nowait`; non-blocking, no I/O; `PumpClosed` when lost/closing or queue full (→ WRITE loss) |
| `OwnerPump.shutdown(terminal=None)` | 645 | graceful: queue `terminal` as the LAST line then EOF; idempotent; no-op once lost |
| `OwnerPump.wait(timeout=None) -> bool` | 669 | both threads exited |
| `_handle_frame(raw)` | 743 | bad UTF-8/JSON → FRAME loss; ProtocolError → REQUEST loss; id mismatch → REQUEST; 2nd editor-start → REQUEST ("duplicate start on owner connection") |
| `_write_loop` / `_finished` | 776 / 809 | write cap exceeded → WRITE loss; OSError → IO loss; closes `conn` when both threads are done |

## voice_typing/editor_session.py (READ ONLY)

| symbol | line | notes |
|---|---|---|
| `Stage` | 73 | STARTING / LISTENING / DRAINING / ENDED |
| `Owner(id, token, created_at, deadline)` | 85 | frozen; `deadline = created_at + START_CAP_S` |
| `EndRecord(owner, stage, reason, cause, ended_at)` | 93 | fixed codes only |
| `NativeReserveResult(accepted, owner, error)` | 103 | error ∈ busy \| duplicate_id \| invalid_request \| None |
| `NativeReservation(owner, conn, *, now)` | 109 | `.live` :123, `.terminate(reason, cause, *, now)` :150, `.stage`, `.owner`, `.end_evt`, `.begin_drain(reason)` |
| `OfferQueue(session_id, recovery, *, clock, ack_timeout_s=ACK_TIMEOUT_S, max_unsettled=MAX_UNSETTLED)` | 213 / 244 | "every method is a pure transition under the CALLER's lock — nothing here takes a lock, waits, or does I/O". Lock discipline: `with d._lock: attempt = q.begin_offer(now)` → write OUTSIDE the lock → `with d._lock: q.finish_offer(ok)`. `begin_offer` stamps `deadline = clock() + ack_timeout_s`; `check_deadline(now)` revokes `"timeout"`; a failed/uncertain write revokes `"delivery_failed"` unless a verified ACK already settled it. |
| properties | 270-291 | `session_id`, `outstanding: OfferAttempt\|None`, `revoked: bool`, `revocation_reason: str\|None`, `last_ack_seq`, `pending_count` |
| `enqueue(text) -> EnqueueOutcome` | 296 | retain-before-offer; overflow/invalid REVOKES sticky but still retains |
| `begin_offer(now=None) -> OfferAttempt\|None` | 326 | `attempt.event()` builds the `final` frame; UNVERIFIED whether `OfferAttempt` exposes `deadline` (read :213-435 in Task 0) |
| `finish_offer(ok)` | 348 | |
| `ack(obj, now=None) -> AckOutcome` | 356 | exact outstanding seq only; duplicate of last ACK harmless |
| `check_deadline(now=None) -> bool` | 388 | |
| `revoke(reason) -> str\|None`, `clear_pending() -> int`, `drain_pending() -> bool`, `close()` | 400-430 | |

## Open verification points for Task 0 (UNVERIFIED here)

1. Does an **overflow** (`enqueue` → REVOKED while LISTENING and no `_disarm` runs) already end the session in S5/S6? Grep `revoked` in `daemon.py` :3180-3620 and read `_native_mic_closed_locked` :3485-3533 and `native_lost` :3579-3622. If not, S7's session tick ends it (`native_lost("delivery_failed", "overflow", token=…)`).
2. `OfferAttempt` fields (`event()`, deadline?) — `editor_session.py` :213-345.
3. Whether `tests/test_control_socket.py` has an exact reply pin that the new first-frame branch could disturb (it should not: the branch only fires on `cmd == "editor-start"`).
