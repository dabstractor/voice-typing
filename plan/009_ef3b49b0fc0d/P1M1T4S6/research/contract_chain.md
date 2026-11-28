# P1.M1.T4.S6 contract chain (PRP-only)

Summary: S6 consumes exactly-once off-lock `on_end(EndRecord)`, `NativeEndFacts`, and the reservation connection; calls `end_session(sid,reason)`; and exposes transcript-free ended/hint state. Recoverability and several surface details conflict or remain unspecified below.

Keys (all existing, under `plan/009_ef3b49b0fc0d/`): **R**=P1M1T3S4; **C**=P1M1T4S1; **Q**=P1M1T4S2; **I**=P1M1T4S3; **F**=P1M1T4S4; **L**=P1M1T4S5; **Seed**=P1M1T2S4; **Ctx**=P1M1T2S5 (each `/PRP.md`).

## A. Requirements/ownership for T4.S6 (verbatim)

* **R — Goal / Persona / Scope / blueprint:** “T4.S6 (`ended` frame + private failure hints — consumes `EndRecord` via `on_end`)”; “no `ended` frame construction or status hints (T4.S6) … `status_snapshot()` is unchanged.” Its hooks support “the `ended` frame and failure hints (T4.S6)”; `EndRecord` is “What T4.S6 turns into the `ended` frame. Fixed codes only.”
* **C — Goal / Why / CONSUMERS:** “immutable `recover()` snapshots feed T4.S6 (failure hints)”; “T4.S6 ends sessions”; “P1.M1.T4.S6 (finalize ownership + failure hints): calls end_session(id, reason) with the EndRecord's reason; reads recover(id) for the "recoverable" flag on the `ended` frame + the hint.” Warning: “Unconfirmed text: voicectl recover <id>”.
* **Q — Integration Points:** “NO CONFIG / SOCKET / STATUS CHANGES. Reasons map 1:1 onto EndReason for T4.S6's `ended` frame.”
* **I — Integration Points:** “P1.M1.T4.S6 (ended cause): FinalClass/relay_event give fixed codes for "what landed last".”
* **F — Goal / scope / Gotchas / CONSUMER CONTRACT:** “The route exposes the **wakeups** T4.S5 (stop/cancel/drain), T4.S6 (ended) and T4.S7 (socket pump) hang off.” S4 excludes “`NativeRecovery.end_session` and the `ended` frame (T4.S6)”. Its contract says: “T4.S6 (ended): recoverable = q.drain_pending(); call self._native_recovery.end_session(sid, reason) at end. The queue is already closed and the fence cleared by _native_close_capture_locked.” Also: “Only QUEUED enqueues set the event; REVOKED = recovery-only (T4.S6 surfaces delivery_failed).”
* **L — Success Criteria / HANDOFF — CONSUMER CONTRACT:** S5 excludes “the `finishing` / `ended` **frames** and desktop hints (T4.S6), `NativeRecovery.end_session` (T4.S6)”. Its handoff says: “T4.S6 (ended frame + hints): read d._native_end_facts (reason, revoked, recoverable) when on_end fires; recoverable == q.drain_pending() at end (the queue itself is already closed and detached); then call d._native_recovery.end_session(sid, reason).” S5 warns: “Do NOT call q.close() yourself — T4.S4's _native_close_capture_locked (inside _end_native_locked) does it, and T4.S6 needs drain_pending() BEFORE that: read the facts in _end_native_locked ahead of the T4.S4 hook.”

## B. Downstream expectations from S6 (verbatim)

* **S7 / ended transport:** R: reservation `conn` is “kept for T4.S6/T4.S7; never used here”. L: user reached “through the T4.S7 owner-connection pump and the T4.S6 `ended` frame/hints.” No separate teardown-callback signature or named S6 method is specified.
* **S7 / lifecycle (L — HANDOFF):** stop→`native_stop("stopped",token=tok)`; cancel→`native_cancel(token=tok)`; loss→`native_lost`; after guarded `q.ack`/`q.check_deadline`, `native_settle_kick()` off-lock. On DRAINING S7 emits `{"event":"finishing","id":…}` once before `begin_offer`; stop/idle DRAINING: “keep offering pending finals.”
* **T5.S1 (C — CONSUMERS):** “P1.M1.T5.S1 (owner-only capped recovery reply): `active_id() == id` → busy; recover(id or None) → None → not_found; else {ok:true,id,text,truncated,possibly_applied} from the snapshot, escaped ≤7 MiB.” F's state is “daemon-wide: outlives sessions (T5.S1 serves it after end)”.
* **T5.S2 (C):** text plus “a stderr warning that it may already be in the buffer (`possibly_applied`) — never auto-replayed, never duplicated”; “consumers warn, never auto-replay (a lost ACK must not become a second insert).” S6's `end_session` finalizes the snapshot source.

## C. Exact interfaces to consume

### Reservation/end/fencing (R — Data models; daemon hooks; Patterns)

```python
@dataclass(frozen=True)
class Owner:
    id: str; token: int; created_at: float; deadline: float
@dataclass(frozen=True)
class EndRecord:
    owner: Owner
    stage: Stage                 # immediately before ENDED
    reason: str                  # END_REASONS member
    cause: str | None            # start-cap|stop-during-start|host-died|shutdown|LossCause|None
    ended_at: float
class NativeReservation:
    def __init__(self, owner: Owner, conn: object, *, now: float): ...
    # owner, conn, stage=STARTING, drain_reason=None, end=None, end_evt=threading.Event()
    live; end_reason
    can_commit(token, now); commit(token); begin_drain(reason)
    terminate(reason, cause, *, now) -> EndRecord | None
    tombstoned(token)
```

“Any live stage -> ENDED (tombstones the token). Idempotent: None once ended.” `can_commit`: own token+STARTING+`now<deadline`; `commit` shares capture's lock hold. Reasons: “stopped, idle, cancelled, target_lost, disconnected, timeout, delivery_failed, load_failed, shutdown”; L adds causes `cancel|settle-timeout`.

Daemon signatures: `reserve_native(conn, session_id, *, on_end=None)`; `begin_native_start(token, *, seed=None, streaming=None)`; `_end_native_locked(reason, cause, *, now=None) -> EndRecord | None`; `terminate_native(reason, *, cause=None, token=None) -> EndRecord | None`; `_stop_native_start() -> bool`. `terminate_native` “Must be called WITHOUT _lock held” and token-restricts to that owner. `_stop_native_start` ends STARTING as `stopped`/`stop-during-start`. `_end_native_locked` retires timers, wakes `end_evt`, and is idempotent.

Exactly once: `_claim_native_end_locked` flips `_native_end_delivered`; `_flush_native_end()` runs “NEVER under _lock”, swallows exceptions by type name; per-reservation `end_evt` wakes the worker. R: “on_end exactly once, off-lock, per owner; raising callbacks swallowed.” `ThreadTimers(clock).arm(deadline,fire)->handle`, `.cancel(handle)`; recheck clock/token under `_lock`: cancel is only a flag, late fires must not end the next owner.

### S5 terminal facts (L — Data models / terminal action)

```python
@dataclasses.dataclass(frozen=True)
class NativeEndFacts:
    reason: str            # actual EndRecord.reason
    revoked: str | None    # queue revocation_reason; None if never revoked
    recoverable: bool      # q.drain_pending() at end
self._native_end_facts: NativeEndFacts | None = None
```

`_end_native_locked` stashes facts before capture close, retires timers, clears settlement/drain state, closes capture, sets `end_evt`. `native_stop(reason="stopped",*,token=None)`, `native_cancel(*,token=None)`, `native_lost(reason,cause=None,*,token=None)`, `native_settle_kick(*,token=None)` return `EndRecord|None`. Stop=`stopped|idle`; loss=`target_lost|disconnected|timeout`.

### Recovery (C — Data models / signatures)

`NativeRecovery(max_sessions=2, max_session_bytes=1<<20, clock=time.monotonic)` is keyed by strict UUIDv4, one active session, unacknowledged accepted finals only (no partials/seed/tail). Methods: `retain_final(session_id,seq,text)->bool`; `mark_offer_attempted(session_id,seq)->bool`; `settle_final(session_id,seq)->bool`; `end_session(session_id,reason)->None`; `recover(session_id=None)->NativeRecoverySnapshot|None`; `active_id()->str|None`; `counts()->tuple[int,int]`; `clear()->None`.

`end_session` only ends the matching active id, recording reason/monotonic time; empty/fully-ACKed endings discard without eviction; otherwise retain ≤2 nonempty ended (oldest evicted), free active; unknown/ended is no-op. Snapshot: `session_id,text,truncated,possibly_applied,final_count,end_reason,ended_monotonic`. Cap=1 MiB UTF-8/session including separators on every retain; drop oldest whole finals, codepoint-safely clip lone oversize keeping its START, set `truncated`. `clear()` drops all and is reusable: “no persistence (clear at exit)”; no call site specified.

### Seed (Seed — Goal / Data models / Gotchas; F — native route)

State: `_seed_handoff_pending`, `_seed_handoff_done`, `_session_accepted`; no seed text on daemon beyond S3's `_seed_active` boolean. Applied prime sets pending beside `_seed_active=True`. First accepted final calls `_handoff_context_prompt(cleaned)` before typing/native return: append accepted text, replace seed once with session-only rolling context (or `""`), clear pending/set done; rejected/ended finals never call it. `_arm` resets accumulator/done, **not** pending; never write `_seed_active` there. R: late capped startup “an installed seed is cleaned up by the existing `_abort_start`.” No general per-end S6 seed-clear API is stated.

### OfferQueue (Q — API / implementation; L — locking)

`OfferQueue(session_id,recovery,*,clock=time.monotonic,ack_timeout_s=5.0,max_unsettled=8)`: `enqueue`, `begin_offer`, `finish_offer`, `ack`, `check_deadline`, `revoke`, `clear_pending`, `drain_pending`, `close`; read-only `outstanding,revoked,revocation_reason,last_ack_seq,session_id,pending_count`. Close blocks enqueue/retention; revoke is sticky/first-reason-wins, preserving pending/recovery; clear drops unattempted only; drain is true while outstanding/pending. Recovery's `possibly_applied`=any attempted offer, survives truncation/end, clears only via ACK removal. Queue is lock-free internally: mutate under `d._lock`, write outside. S6 uses stashed facts, not the detached queue.

## D. Status, feedback, hints/logs, duck/idle/responsiveness

* R: “`status_snapshot()` and `stop()` return within 1 s while the worker is blocked inside `spawn`”; heavy waits outside `_lock`; “Keep status/stop/quit responsive while the owner starts”. Ctx: “status/stop stay responsive”. End callbacks off-lock avoid status deadlock.
* R's S4 scope left `status_snapshot()` unchanged; F and L both say “NO CHANGES … status …” (L explicitly “status fields, ControlServer handlers/replies”). Seed: “Seed text absent from logs/status/feedback/recovery/replies”; normal status `context_prompt` label unchanged. F: native finals do not reach `state.json` / `voicectl session` / toasts, `feedback.record_final`, generic recovery, latency or transcript log; lifecycle `feedback.set_listening` remains.
* Logs: R: “EndRecord/log/reply content is fixed codes + the owner token/id. Never the seed, request text, frame bytes or exception messages (`type(exc).__name__` only).” F/L/I: codes/counts/ids only; no text/seed/ProtocolError detail.
* Desktop: F explicitly bans hypr notify on native final route and requires no generic toast transcript. C supplies the only verbatim user-facing recovery warning, “Unconfirmed text: voicectl recover <id>”; no selected PRP specifies the neutral editor-gone warning wording or trigger beyond S6 owning desktop hints.
* Duck/mic: F requires native `_arm` to retain “mic, listening gate, lifecycle feedback and ducking” and says media ducking unchanged. R locates existing `_disarm` as clearing `_listening`, `set_microphone(False)`, `_duck_release`; native end routes through disarm where capture was open. No selected PRP adds a separate duck-release API or literally says “on every disarm path”; preserve existing `_disarm` behavior.
* Idle: L: idle auto-stop routes `idle` only after the idle threshold actually holds; non-idle native stays LISTENING. F/L say idle auto-stop/unload unchanged. R makes all generic starts busy while native is STARTING/LISTENING/DRAINING, but **none of the selected PRPs states whether the idle-unload watchdog may tear down a host during those stages**. Do not infer such a rule.

## E. Test files created by each requested PRP; G1 rule

R: `tests/test_editor_session.py`. C: `tests/test_native_recovery.py`. Q: `tests/test_editor_offer_queue.py`. I: `tests/test_recorder_identity_boundary.py`. F: `tests/test_native_final_route.py`. L: `tests/test_native_lifecycle.py`. Seed created **none** (edited `tests/test_daemon.py`). Ctx created **none** (edited `tests/test_voicectl.py`, `tests/test_control_socket.py`, `tests/test_daemon.py`).

G1 is a name-set comparison, not a count: R requires `tests/test_daemon.py` FAILED-name set-diff versus `tests/G1_BASELINE.md` CPU addendum with no NEW failures. F/L state the stronger verbatim rule: “the FAILED set must EQUAL the Task-0 baseline set — no new reds, no blanket skips” / “FAILED set == G1 baseline (set-diff, not count).” Ctx likewise says diff FAILED names against the CPU addendum; no NEW reds.

## F. Open questions / contradictions

1. **Finishing-frame owner conflict:** L Success Criteria assigns both `finishing` and `ended` frames to S6, but L HANDOFF instructs S7 to emit `{"event":"finishing","id":…}`. Resolve emission ownership/callback split; do not implement duplicate sends.
2. **Recoverability source:** C says S6 reads `recover(id)` for ended `recoverable`; F/L define it as `q.drain_pending()` stashed in `NativeEndFacts`. Latest S5 handoff explicitly says read facts on `on_end`; how/if snapshot contents may override that boolean is unspecified.
3. **Failure mapping:** F says REVOKED recovery-only means “T4.S6 surfaces delivery_failed”, while facts preserve actual `EndRecord.reason` plus separate `revoked`. The ended schema and when to substitute/add `delivery_failed` are not specified.
4. **Hints/status:** Exact ended fields beyond id/reason/recoverable, stable status field names, hint mapping by reason/cause/revoked, and neutral editor-gone warning text are absent. Normal status was previously unchanged; S6 must define its additive safe surface without exposing transcript text.
5. **Teardown callback:** Task language expects one for S7/T5.S1, but selected PRPs specify only `on_end(EndRecord)`, reservation `conn`, facts, and recovery methods—no named teardown callback or `end_session` callback signature beyond `(sid, reason)`.
6. **Seed/buffers:** Only late-start `_abort_start` cleanup and recovery `clear()` “at daemon exit” are stated; no general per-end seed clear or shutdown call site. Idle-unload versus live native is unstated (D).
