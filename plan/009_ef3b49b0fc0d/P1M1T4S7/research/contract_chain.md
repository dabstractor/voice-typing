# P1.M1.T4.S7 — contract chain (verbatim excerpts; PRD.md at HEAD `0c2a50c`)

## A. PRD §4.8.1 B — Native wire protocol v1 (same owner-only Unix socket) — `PRD.md:448-468`, verbatim

> The adapters use the socket directly, not a subprocess per utterance. UTF-8 newline-delimited JSON objects, with a **32 KiB wire limit per request and live event** (including newline); enforce byte limits while reading, before unbounded buffering, and reject invalid UTF-8, malformed frames, invalid types, oversized fields, or unsupported protocol before arming. Every successful native Start reserves an exclusive connection-owned session; status/stop/quit remain available, but all other start/toggle/cancel attempts (including legacy ones) return busy while the native reservation exists. Native Start likewise returns busy if **any** other arm is loading, listening, or draining. `voicectl stop` is an emergency graceful stop of the active session using its existing delivery route; `quit` shuts down. A start rejected as busy never queues for later. Keep existing one-request commands and status/recovery behavior backward-compatible outside native mode.

| Direction | Frame | Meaning |
|---|---|---|
| Editor → daemon, first frame | `{"cmd":"editor-start","version":1,"id":"<UUIDv4>","context":"..."}` | The client generates and remembers the opaque session id before connecting. Reject an id already active or retained. No target name/path, editor buffer contents beyond the seed, or output-mode option. |
| Daemon → editor | `{"ok":true,"event":"starting","id":"..."}` | Reservation acquired; capture not open yet. A failed initial request instead gets `{"ok":false,"error":"<code>"}` and EOF. Native error codes: `invalid_request`, `too_large`, `unsupported_version`, `busy`, `duplicate_id`. An old daemon's unknown-command reply means unsupported. |
| Daemon → editor | `{"event":"listening","id":"...","context_seeded":true}` | Arm succeeded; include `context_reason` if unseeded. Must precede any final. |
| Editor → daemon / reply | `{"cmd":"ping","id":"..."}` / `{"event":"pong","id":"..."}` | Client sends every 2 s while reserved, including during load and drain. No renewal after local invalidation. |
| Daemon → editor | `{"event":"final","id":"...","seq":1,"text":"..."}` | Accepted, cleaned recognition text (no editor padding); start at seq 1, monotonic, one offer outstanding at a time. |
| Editor → daemon | `{"cmd":"applied","id":"...","seq":1}` | Sent only after verifying a native edit and its new caret/checkpoint; no resend of offers or automatic replay on any error. |
| Editor → daemon | `{"cmd":"stop","id":"..."}` (also `cancel` or `lost`) | `stop` drains, retaining the editor as sink; `cancel` invalidates and aborts; `lost` invalidates and drains for recovery only. |
| Daemon → editor | `{"event":"finishing","id":"..."}` | Capture winding down after a graceful stop (including idle auto-stop); ordered before any final accepted during that drain. |
| Daemon → editor | `{"event":"ended","id":"...","reason":"<code>","recoverable":true}` | Last frame then EOF; recoverable means some accepted text is not known applied and is retained. Reasons: `stopped`, `idle`, `cancelled`, `target_lost`, `disconnected`, `timeout`, `delivery_failed`, `load_failed`, `shutdown`. |

> - Every post-start frame is scoped to the owner connection and same id. Accept an `applied` only for the outstanding seq, advance the contiguous acknowledgement watermark once, and ignore an exact duplicate of the last ACK; other unexpected ids/seqs/commands terminate safely with `delivery_failed`. Clients never insert duplicate, skipped, stale, or out-of-generation offers. A final outside Listening/Finishing, seq other than the next expected one, unknown event, failed edit, uncertain edit outcome, or timeout invalidates locally first, warns, and abandons delivery, never retries. Cancel/Lost immediately disable local delivery even before the transport processes the command; a transport close or abnormal terminal event invalidates any not-yet-executed UI callback. Terminal transition is idempotent even if Stop, loss, exit, and EOF race.
> - Cap Start (including model load/priming) at 30 s; active lease expires at 6 s without valid ping/pong on the respective side; ACK deadline is 5 s from offer write. Use monotonic time and bounded socket writes (at most 2 s). Existing bounded ASR drain applies after Stop/loss; allow up to 5 s for outstanding ACKs **after** the ASR drain, total, then end. Clients close on expired deadline. EOF, client failure, or expired lease is loss, never permission to send text anywhere else. The daemon must be able to service EOF/stop/lost/heartbeat during cold load; a cancelled reservation cannot resume/arm when the worker returns. Check reservation before opening capture and fence every recorder event by arm generation/utterance identity.
> - Native sessions bypass `StreamingOutput`, bulk target acquisition, focus injectors, evdev typing/cancel guards, and transcript-bearing desktop/state feedback. Use only lifecycle status/warnings, not native transcript in generic status/state or `voicectl session`. Daemon-side ASR callbacks run the existing final cleaning/filtering, deduplicate by recorder generation/utterance id (reject missing/stale identity), record the accepted final for recovery, and enqueue it without socket I/O under the control lock or on the recorder reader thread. No drain waiting/child abort under that lock. Pending live delivery is capped at 8 finals (including the outstanding offer) and 4 KiB UTF-8 per final; if a limit is exceeded, do not truncate and insert—switch once to recovery-only drain with `delivery_failed`. The daemon may update rolling context from accepted finals without waiting for a socket ACK; app-side checkpoint validation governs all writes.
> - Stop (including idle auto-stop) accepts at most the already-in-flight final and allows queued offers to settle **only** while the original target remains valid. Stop during startup aborts the reservation without opening capture. Cancel invalidates before sending and aborts in-flight audio; no new recognition accepted or inserted after cancellation, previously accepted/unconfirmed text may still be recovered. Loss/disconnect first revokes delivery, then gracefully drains at most the already-in-flight utterance into recovery only; loss while starting aborts without capture. Shutdown/host failure clean up without promising a recoverable drain. A successful native session uses the same media duck/un-duck and idle unload policies as other sessions.

**Known discrepancy (resolved in decisions.md §2):** the table's `starting` frame carries `"ok":true`, but the shipped
codec closes `starting` to `{event,id}` (`editor_protocol._EVENT_SPECS` :306) and both clients validate with
`validate_event`; T3.S4's handoff prescribes `{'event':'starting','id':id}`. The codec wins.

## B. PRD §4.8.1 C / D — `PRD.md:469-485` (read in Task 0)

Quoted by S6's PRP from C: "Always retain transcript-free last abnormal end reason and recovery hint in
`voicectl status` and log same diagnostic, even if notifier succeeds." Warning example: "Dictation stopped: draft
or caret changed. Start again here. Unconfirmed text: `voicectl recover <id>`." "No durable recovery promised
after daemon restart." D fixes implementation boundaries: "A public in-editor control … optional user mappings";
adapters are P1.M2.T1/T2 — not this item.

## C. PRD §6 T10b (from `architecture/verification.md`), verbatim

> | T10b | Production `ControlServer` on temporary private socket, fake host/feedback/backend, deterministic events/barriers plus injected monotonic clock. Never call a live `voicectl`, clipboard, media/mic/display tool or evdev from these cases. | Shared JSONL + spacing fixtures; partial/merged frames, encoded boundaries, busy races through all ownership phases, responsive status/stop/quit, phase order, deadlines including absolute write and finishing bounds; FIFO/one offer and exact duplicate ACK only, no resends, overflows, EOF/cancel/late-start races, stale/unidentified events, no output even on failure, bounded separate recovery and warning semantics. Validate no unintended desktop subprocess/global output (test tripwires). |

Bounds (`verification.md`): "Repository `AGENTS.md`: inner GNU `timeout`, plus a larger bash tool timeout on every
invocation; never run the foreground daemon. Ensure child editors/fake server processes get bounded shutdown and
process-group teardown on every exit. Use private short runtime/socket paths (Unix pathname length limit), bounded
stdout/artifacts and deterministic race barriers, rather than sleeps or ever-growing logs."

## D. Sibling handoffs that name T4.S7 (verbatim)

**T3.S3 → S7** (`OwnerPump` docstring, `editor_protocol.py:543-546`):
> "T4.S7 constructs it on the connection thread with the live FrameReader (so S1's `unread` handoff bytes are preserved), queues `starting`, calls start(), then waits."

**T3.S4 → S7** (`P1M1T3S4/PRP.md:195-198`):
> "T4.S7's sequence is: `res = d.reserve_native(conn, id, on_end=…)`; rejected → `write_reject(conn, res.error)`; else `pump.send_event({'event': 'starting','id':id})` (PumpClosed → `d.terminate_native('disconnected', cause=exc.cause.value, token=res.owner.token)`), then `d.begin_native_start(res.owner.token, seed=ctx or None)`."

and (`P1M1T3S4/PRP.md:291-292, 755-756`):
> "S2's validate_event closes `starting` to {event,id}. T4.S2/T4.S7 own that." / "SOCKET: NONE in this task (T4.S7: `_handle` branches on request_kind → validate_request → reserve_native → `starting` → begin_native_start; on_loss → terminate_native('disconnected', cause=…))." — **note:** "branches on request_kind" is unsafe as literally written (plain `stop`/`cancel` are native cmds too); see decisions.md §1.

**T4.S2 → S7** (`OfferQueue` docstring, `editor_session.py:214-243`):
> "The socket write happens BETWEEN begin_offer and finish_offer, OUTSIDE the lock: `with d._lock: attempt = q.begin_offer(now)` / `if attempt is not None: ok = send_line_capped(conn, encode_line(attempt.event()))` / `with d._lock: q.finish_offer(ok)`." … "begin_offer stamps deadline = clock() + ack_timeout_s (the 2 s write cap sits INSIDE the ACK budget); the caller's timer calls check_deadline(now) … Duplicate ACK of the last settled seq is harmless (no extension, no replay). A failed/uncertain write revokes "delivery_failed" — unless a verified ACK already settled the offer (the ACK wins)."

**T4.S4 → S7** (`daemon.py:3200-3204`):
> "T4.S7 (pump): wait on d._native_offer_evt (bounded by the 2 s ping tick); on wake: evt.clear(); loop `with d._lock: attempt = q.begin_offer(now)` → send_line_capped OUTSIDE the lock → `with d._lock: q.finish_offer(ok)`; `with d._lock: q.ack(obj)` on "applied"; `with d._lock: q.check_deadline(now)` on the timer. A stale set after close is harmless (q is None). Only QUEUED enqueues set the event; REVOKED = recovery-only (T4.S6 surfaces delivery_failed)."

**T4.S5 → S7** (`daemon.py:3442-3453`, `native_stop`):
> "CONSUMER CONTRACT (T4.S7 owner-connection pump, all with owner token): owner "stop" → d.native_stop("stopped", token=tok); owner "cancel" → d.native_cancel(token=tok); owner "lost" / local invalidation → d.native_lost("target_lost", <LossCause>, token=tok); transport EOF / write failure → d.native_lost("disconnected", <LossCause>, token=tok); lease expiry (6 s without valid ping) → d.native_lost("timeout", "lease-expired", token=tok); after EVERY d._lock-guarded q.ack(...) / q.check_deadline(...) → d.native_settle_kick() (off-lock); without the kick `ended` still arrives, but only at the 5 s deadline."

and (`daemon.py:3539-3543`, `native_settle_kick`): "without the kick `ended` still arrives, but only at the 5 s deadline; a stale set after close is harmless (q is None); while DRAINING the queue stays open and unrevoked for stop/idle — keep offering pending finals."

**T4.S6 → S7** (`P1M1T4S6/PRP.md:585-600`, HANDOFF — CONSUMER CONTRACT, verbatim):
> T4.S7 (owner-connection pump):
>   d.set_native_teardown(cb)  — ONE daemon-level hook; cb(NativeEndState) fires exactly once per ended session, off-lock, AFTER on_end(EndRecord) and AFTER NativeRecovery.end_session — i.e. recover(id) is final.
>   In cb: `pump.send_event(state.frame())` (the `ended` frame — EXACTLY {"event","id","reason","recoverable"}), then close the owner connection / retire pump timers. Do NOT build the frame yourself.
>   `finishing` stays the pump's: emit {"event":"finishing","id":…} ONCE on _native_offer_evt wake while d._native.stage is DRAINING (S5 handoff). The daemon core never writes to the socket.
>   Keep passing on_end=… to reserve_native if you need the raw EndRecord (cause, stage, ended_at).
> d.native_last_end() → NativeEndState | None (lock-free) for diagnostics; status["native"] for the CLI.

(Resolution in S6 `research/decisions.md` row 1: S6 **builds** `ended` via `NativeEndState.frame()` and hands it to S7's
teardown callback; S7's `OwnerPump.send_event` **writes** it — in practice `pump.shutdown(state.frame())`, which
queues it as the LAST line then EOF; `finishing` stays S7's.)

**architecture/system_context.md → S7**: "Keep old one-shot/persistent ordinary commands and structured failures,
with a single connection owner for v1." "Ensure one writer, deadline on the whole frame (not just each fragment),
no waits/joins/writes on daemon control lock or recorder reader." "Keep status/stop/quit responsive while the owner
starts, blocks on reads/writes, drains or is lost."
