# PRP — P1.M1.T4.S7: Activate native v1 on the existing control socket

## Goal

**Feature Goal**: Make the **production** `ControlServer` (`voice_typing/daemon.py`) speak PRD §4.8.1 B
on the **existing** `$XDG_RUNTIME_DIR/voice-typing/control.sock`: an editor (Pi / Neovim adapter) connects,
sends `{"cmd":"editor-start","version":1,"id":"<UUIDv4>","context":"…"}` as its first frame, and from then
on that ONE connection is the live **owner** of a native session — `starting` → `listening` → `final`
offers verified by `applied` ACKs → `finishing` → `ended` then EOF — with pings/lease, `stop`/`cancel`/`lost`,
one live owner, **no fallback** to any generic output, and ordinary `voicectl` clients (status/stop/quit)
still served on their own connections.

**Deliverable** (2 source files edited, 1 test file created, 1 doc touch):
1. `voice_typing/daemon.py` — `ControlServer` gains the native handshake in `_handle` (first-frame
   detection → `validate_request` → `reserve_native` → `write_reject` on refusal), a `_NativeSession`
   owner-connection driver (constructs `OwnerPump` with the live `FrameReader`, emits `starting`,
   `begin_native_start`, then runs the session loop: `listening`, offers, ACK/deadline, `finishing`,
   loss/stop/cancel/lost routing, teardown → `ended`), the daemon-level teardown hook registration,
   bounded `stop()` retirement of live sessions; `begin_native_start(..., on_committed=)` so the
   `listening` frame carries `context_seeded`/`context_reason` from the committed `ArmOutcome`;
   [Mode A] `ControlServer` docstring (protocol table + message lifecycle), `_handle`/`_dispatch` docstrings.
2. `voice_typing/editor_protocol.py` — **docs only**: module docstring + `OwnerPump`/`write_reject`
   docstrings describe the S7 dispatch and the message lifecycle (who emits which event, ordering, timers).
3. `tests/test_native_socket.py` — hermetic CPU-only tests of the **production** `ControlServer` on a
   private temp socket with the fake host/feedback/tripwire backend and injected clock/timers (new).
4. `tests/G1_BASELINE.md` / `tests/test_daemon.py` — untouched unless Task 0 finds an exact pin that
   must move (then one line, like S6's `"native"` key).

**Success Definition**:
- (a) **Handshake**: `editor-start` as the first frame on a fresh connection → `starting` written BEFORE
  `begin_native_start`; every refusal (`invalid_request`, `unsupported_version`, `too_large` from
  `validate_request`; `busy`, `duplicate_id`, `invalid_request` from `reserve_native`) is written as
  `native_error_reply(code)` then EOF via `write_reject`, with **nothing reserved** and the daemon
  byte-identical to before the attempt. Any other first frame keeps today's generic behaviour exactly
  (one reply per line; `{"cmd":"ping","id":…}` without a start on a non-owner connection gets the
  ordinary `unknown command` reply — the PRD's "old daemon ⇒ unsupported" signal).
- (b) **Lifecycle on the wire**: exactly one `starting`; exactly one `listening` (with
  `context_seeded` and `context_reason` only when false) before any `final`; `final` offers seq
  1..n monotonic, one outstanding, each ≤ 4 KiB; `pong` per valid `ping`; `finishing` exactly once on a
  graceful stop and ordered before any final accepted during the drain; `ended` is the LAST frame then
  EOF; every daemon→editor line passes `editor_protocol.validate_event`.
- (c) **Commands** (owner token fenced): `applied` only for the outstanding seq advances the watermark;
  an exact duplicate ACK is harmless (no extension, no replay); `stop` → `native_stop("stopped")`;
  `cancel` → `native_cancel` (no drain, `ended.reason=="cancelled"`); `lost` → `native_lost("target_lost")`.
  Never a resend, never a replay, never a second offer for the same seq — on any error.
- (d) **Loss**: EOF / IO / bad frame / bad request → `native_lost(cause.end_reason, cause.value)`;
  lease expiry (6 s without a valid ping) → `ended.reason=="timeout"`; a write cap / full outbound
  queue → `disconnected`. Loss revokes delivery first (no `final` after loss) and never sends text
  anywhere else.
- (e) **Deadlines** (monotonic, injected clock in tests): Start cap 30 s → `ended{timeout,
  cause=start-cap}`; ACK 5 s → revoke `timeout`; stop during STARTING → `ended{stopped}` without
  opening capture; a late worker return never arms.
- (f) **Overflow**: a 9th unsettled final (MAX_UNSETTLED = 8) → `ended.reason=="delivery_failed"`,
  no truncated final on the wire, text retained for recovery.
- (g) **One live owner, old clients intact**: while an owner is live, a second connection's
  `status` → `ok` with the `native` block; `start`/`toggle` → `busy` (existing S4 branch); `stop` →
  graceful stop of the native session; `cancel` → busy (Task 0 verifies; add the branch if missing);
  `quit` → `ended{shutdown}`. After the session ends the next arm works normally.
- (h) **No global output, ever**: across every case the typing backend is a tripwire (0 calls), no
  paste/clipboard/evdev/subprocess is touched (patch `subprocess.run` to raise in the test process),
  feedback/state/`session` never carry native transcript, and `caplog` carries only codes/counts/ids.
- (i) **Thread/lock discipline**: no socket I/O, wait, join or callback under `d._lock`; the
  recorder reader thread never writes; exactly ONE writer (the pump's) per owner socket; `on_command`
  and `on_loss` never block on I/O; `ControlServer.stop()` retires a live session in ≤ 3 s.
- (j) `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no` FAILED set == G1 CPU
  addendum (set-diff); `tests/test_control_socket.py`, S2/S3 protocol/pump suites, S4/S5/S6 suites green.
- (k) `git diff --name-only` ⊆ `{voice_typing/daemon.py, voice_typing/editor_protocol.py,
  tests/test_native_socket.py}` (+ one-line pin fixes only if Task 0 finds one).

## User Persona

**Target User**: the dictation user inside a pinned native editor (Pi prompt, Neovim) — via the P1.M2
adapters — and the same user at a bare terminal running `voicectl status|stop` while an editor session is live.
**Use Case**: The adapter opens the control socket, starts a session, shows live words as verified
single edits, and stops/cancels from the editor; if the editor dies, the daemon ends the session,
keeps unconfirmed words for `voicectl recover`, and never types into whatever window is focused next.
**User Journey**: adapter connects → `editor-start` → `starting` (models may load) → `listening` →
`final`/`applied` … → `stop` → `finishing` → `ended` → EOF. At any point `voicectl status` shows
`native: state/listening id=…`; `voicectl stop` ends it gracefully; nothing is ever typed system-wide.
**Pain Points Addressed**: the v1 protocol existed only as unexercised library pieces (codec, pump,
reservation, queue); no production route accepted an editor; an old daemon answered `unknown command`.

## Why

- PRD §4.8.1 B: "Every successful native Start reserves an exclusive connection-owned session;
  status/stop/quit remain available, but all other start/toggle/cancel attempts (including legacy ones)
  return busy while the native reservation exists." "A failed initial request instead gets
  `{"ok":false,"error":"<code>"}` and EOF." "EOF, client failure, or expired lease is loss, never
  permission to send text anywhere else." "The daemon must be able to service EOF/stop/lost/heartbeat
  during cold load; a cancelled reservation cannot resume/arm when the worker returns."
- `architecture/system_context.md`: "Existing server uses a thread per connection. Keep old
  one-shot/persistent ordinary commands and structured failures, with a single connection owner for
  v1." "Separate a 32 KiB byte-bounded strict UTF-8 reader/live writer from the exceptional recovery
  reply, with no reuse of generic output as fallback. Ensure one writer, deadline on the whole frame
  (not just each fragment), no waits/joins/writes on daemon control lock or recorder reader."
- Chain (all landed at HEAD `0c2a50c` unless noted): T3.S1 `FrameReader` (byte bound + `unread`
  handoff) → T3.S2 `validate_request`/`validate_event`/`write_reject`/`native_error_reply` →
  T3.S3 `OwnerPump` (reader/writer threads, ping→pong+lease, sticky loss, `shutdown(terminal)`) →
  T3.S4 `reserve_native` / `begin_native_start` / terminate funnels / Start-cap watchdog → T4.S2
  `OfferQueue` (`begin_offer`/`finish_offer`/`ack`/`check_deadline`, 8 × 4 KiB) → T4.S4 final route
  (`_native_on_final` → enqueue → `_native_offer_evt`) → T4.S5 `native_stop` / `native_cancel` /
  `native_lost` / `native_settle_kick` → **T4.S6 (implementing now; CONTRACT)** `NativeEndState`,
  `set_native_teardown(cb)`, `native_last_end()`, `status["native"]`. Every one of those docstrings
  says "T4.S7 wires this". This item is the wiring.

## What

### Success Criteria
- [ ] `ControlServer._handle` recognises `editor-start` as a first frame and hands the connection to
      `_NativeSession` with the live `FrameReader` (coalesced bytes preserved through `reader.unread`).
- [ ] `_NativeSession` emits `starting`, calls `begin_native_start(token, seed=, on_committed=)`, emits
      `listening` from the committed `ArmOutcome`, drives offers/ACKs/deadlines via the pump's single
      writer, emits `finishing` on DRAINING, routes `stop`/`cancel`/`lost`/loss, and delivers `ended`
      through S6's teardown callback (`pump.shutdown(state.frame())`).
- [ ] The daemon-level teardown hook is registered by the `ControlServer` (ONE hook — S6 contract);
      `ControlServer.stop()` retires live sessions (`shutdown` reason) within budget.
- [ ] (a)–(k) hold; docs [Mode A] updated in `ControlServer` and `editor_protocol.py`.
- [ ] **Not in scope**: `voicectl recover` (T5.S1/S2); adapter-side behaviour (P1.M2.T1/T2);
      `editor_protocol.py` code changes (docs only here); `editor_session.py`, `session_recovery.py`,
      `recorder_host.py`, `feedback.py`, `ctl.py` (read-only — `status` already renders `native` from S6);
      config keys; README (P1.M2.T4.S1).

## All Needed Context

### Context Completeness Check

_Pass._ Below: the exact current bodies of `_handle`/`_dispatch`, the `OwnerPump` API and thread
contract, `reserve_native`/`begin_native_start`/`_native_start_worker`, every T4.S7 consumer contract
verbatim, S6's handoff, the PRD §4.8.1 B grammar, and the resolutions of every open design question.
The implementer needs this PRP plus `research/seam_census.md`, `research/contract_chain.md`,
`research/decisions.md` (line-numbered, from the current tree).

### Documentation & References

```yaml
- url: https://docs.python.org/3/library/socket.html#socket.socket.shutdown
  why: "the pump already shuts the socket down on loss; the session must NEVER call shutdown/send itself"
  critical: "one writer = OwnerPump._write_loop on conn.dup(); the session thread only calls pump.send_event (queue put)"
- url: https://docs.python.org/3/library/socket.html#socket.socket.makefile
  why: "_handle's generic path writes via conn.makefile('wb'); the native path must close wfile BEFORE the pump dups conn"
  critical: "wfile.close() flushes+releases its dup; do it before constructing OwnerPump so no third fd holds the socket"
- url: https://docs.python.org/3/library/threading.html#threading.Event.wait
  why: "the session loop waits on d._native_offer_evt with a bounded timeout (tick) — never an unbounded wait"
  critical: "wait(timeout) returns bool; a spurious wake is harmless (begin_offer returns None); never wait under d._lock"
- url: https://docs.python.org/3/library/json.html#json.loads
  why: "_handle must detect editor-start on the PARSED object; keep _dispatch(line: str) signature (tests call it directly)"
  critical: "parse once in _handle for detection, pass the original line to _dispatch (its own parse is the error path for malformed JSON)"

- docfile: plan/009_ef3b49b0fc0d/P1M1T4S7/research/seam_census.md
  why: "line-numbered census of ControlServer, every _native_* seam, OwnerPump, OfferQueue, test harnesses (current tree)"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S7/research/contract_chain.md
  why: "verbatim PRD §4.8.1 B/C/D + T10b, and every S2–S6 handoff line that names T4.S7"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S7/research/decisions.md
  why: "the open design questions and their resolutions (first-frame rule, starting shape, listening source, finishing ordering, overflow, old clients, stop())"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S6/PRP.md
  why: "CONTRACT — 'HANDOFF — CONSUMER CONTRACT' (T4.S7 pump section) and NativeEndState.frame()/set_native_teardown"
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S4/PRP.md
  why: "lines 191–198: the prescribed T4.S7 sequence reserve → write_reject | starting → begin_native_start; PumpClosed → terminate_native('disconnected')"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S5/PRP.md
  why: "native_stop/native_cancel/native_lost/native_settle_kick consumer contracts (quoted below from the landed source)"
- file: voice_typing/daemon.py
  why: "THE module edited. ControlServer :4226-4630 (docstring :4227, __init__ :4272, start :4291, stop :4329,
        _handle :4373, _dispatch :4457); reserve_native :3247; _native_start_expired :3277; begin_native_start :3289;
        _native_start_worker :3623; _native_on_final :3180 (consumer contract :3190-3204); native_stop :3422
        (contract :3442-3453); _native_mic_closed_locked :3485; native_settle_kick :3534; native_cancel :3551;
        native_lost :3579; _normalize_context :4197; _default_control_socket_path :595; main :4732 (ControlServer(daemon, on_quit=daemon.shutdown) :4782)"
  pattern: "connection thread = handshake, then session loop until the pump threads are joined; no I/O under d._lock"
  gotcha: "line numbers are at HEAD 0c2a50c; S6 lands concurrently and shifts them — anchor by symbol"
- file: voice_typing/editor_protocol.py
  why: "FrameReader :34 (unread :50), encode_line :98, PROTOCOL_VERSION :113, NativeErrorCode/EndReason :119/:129,
        native_error_reply :165, is_uuid_v4 :170, request_kind :270, validate_request :277, _REQUEST_SPECS :258,
        _EVENT_SPECS :306, validate_event :322, LossCause :414 (.end_reason), PumpClosed :433 (.cause),
        send_line_capped :472, ThreadTimers :501, write_reject :518, OwnerPump :533 (__init__ :564, start :615,
        send_event :628, shutdown :645, wait :669, _on_loss :703, _handle_frame :743)"
  pattern: "OwnerPump(conn, sid, *, on_command, on_loss, reader=None, clock=time.monotonic, timers=None, lease_s, write_cap_s, queue_max)"
  gotcha: "DOCS ONLY in this item — no code change; `_handle_frame` routes ping→pong+lease itself and treats a 2nd editor-start / id mismatch / ProtocolError as REQUEST loss (delivery_failed)"
- file: voice_typing/editor_session.py
  why: "Stage :73, Owner :85 (id, token, created_at, deadline), EndRecord :93, NativeReserveResult :103
        (accepted, owner, error), NativeReservation :109 (live :123, terminate :150), OfferQueue :213 —
        begin_offer(now=None)→OfferAttempt|None, attempt.event(), finish_offer(ok), ack(obj, now=None)→AckOutcome,
        check_deadline(now)→bool, outstanding: OfferAttempt|None, revoked: bool, revocation_reason, last_ack_seq,
        pending_count, revoke(reason), clear_pending(), drain_pending(), close()"
  gotcha: "READ ONLY. Every OfferQueue mutation happens under d._lock; the queue takes no lock and does no I/O"
- file: tests/test_daemon.py
  why: "the harness to import (`import test_daemon as td`): _FakeFeedback, _FakeHost (capture_boundary, relay_event,
        abort/cancel/stop), _FakeBackend/tripwire, _make_daemon; test_control_socket.py: how ControlServer is
        started on a temp socket path with a stub daemon (COPY that pattern)"
- file: tests/test_native_lifecycle.py   # S5's harness — COPY helpers, do not edit
  why: "FakeClock + ManualTimers (d._native_clock, d._native_timers), _BHost(td._FakeHost), _ev(), _listening_native(),
        _in_flight(), tripwire backend — reuse verbatim in test_native_socket.py"
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py             # ~4800 lines; ControlServer :4226; native seams :3067-3716        ← EDIT
voice_typing/editor_protocol.py    # codec + validators + OwnerPump (T3.S1-S3)                        ← DOCS ONLY
voice_typing/editor_session.py     # Stage/Owner/EndRecord/NativeReservation/OfferQueue (T3.S4, T4.S2) READ ONLY
voice_typing/session_recovery.py   # NativeRecovery (T4.S1)                                          READ ONLY
voice_typing/ctl.py                # voicectl: status renders `native` (S6); send_command has VOICECTL_TIMEOUT  READ ONLY
tests/test_control_socket.py       # ControlServer on a temp socket with a stub daemon                 KEEP GREEN
tests/test_daemon.py               # harness + exact status key set (:2211 + "native" from S6)         KEEP GREEN
tests/test_native_lifecycle.py     # S5 harness (FakeClock/ManualTimers/_BHost/tripwire)              COPY helpers
tests/test_native_teardown.py      # S6 (landing now)                                                 KEEP GREEN
tests/test_native_socket.py                                                                          ← CREATE
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/daemon.py
  + @dataclass class _NativeSession        # per owner connection: id, token, pump, inbox, flags, done Event, owner thread
  + def _listening_frame(sid, out: ArmOutcome, cfg) -> dict           # pure: context_seeded/context_reason from the committed ArmOutcome
  + VoiceTypingDaemon.begin_native_start(token, *, seed=None, streaming=None, on_committed=None)  # + on_committed(out) off-lock when committed
  ~ VoiceTypingDaemon._native_start_worker  # call on_committed(out) after `committed` (off-lock, before parking on end_evt)
  ~ ControlServer.__init__   + _sessions: dict[str, _NativeSession], _sessions_lock; register daemon.set_native_teardown(self._on_native_ended) if present
  ~ ControlServer.start      + no change beyond docstring
  ~ ControlServer.stop       + _retire_sessions(timeout=3.0): terminate_native("shutdown", cause="shutdown") for live ones, wait bounded
  ~ ControlServer._handle    + first-frame detection → _native_handshake(conn, reader, obj) → _run_native_session(...); wfile closed before handoff
  ~ ControlServer._dispatch  + `cancel` under a live native owner → busy (ONLY if Task 0 shows d.cancel() does not already return busy)
  + ControlServer._native_handshake(conn, reader, obj) -> _NativeSession | None
  + ControlServer._on_native_ended(state: NativeEndState)            # S6 teardown hook: pump.shutdown(state.frame()); session.done.set()
  + ControlServer._run_native_session(sess) / _NativeSession.step()   # the loop; step() is unit-testable
  + ControlServer._native_on_command(sess, obj) / _native_on_loss(sess, cause)   # pump callbacks (never block on I/O)
  ~ docstrings [Mode A]: ControlServer (protocol table + native row), _handle, _dispatch, _native_start_worker
voice_typing/editor_protocol.py   ~ module docstring + OwnerPump/write_reject docstrings: S7 dispatch & message lifecycle  ← DOCS ONLY
tests/test_native_socket.py       — (a)–(i) on the production ControlServer, private socket, fake host, tripwires
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — FIRST-FRAME RULE. `request_kind()` returns "stop"/"cancel" for PLAIN voicectl frames too
# (they are in _REQUEST_SPECS). Do NOT branch on request_kind. A connection becomes an owner ONLY when its
# first frame is a dict with cmd == "editor-start". Everything else on a non-owner connection stays generic
# (one reply per line, BUG-005 lockstep). After the handoff the generic loop never runs on that connection again.
# CRITICAL #2 — ONE WRITER. OwnerPump._write_loop is the only sender (conn.dup()). The session thread NEVER
# calls conn.send/sendall/shutdown. Offers go through pump.send_event(attempt.event()) — "ok" for
# q.finish_offer(ok) means QUEUED; a real write failure surfaces as on_loss(WRITE|IO) → native_lost, which
# revokes the queue (the ACK-wins rule still holds: an ACK can only arrive after the write).
# CRITICAL #3 — MARK-BEFORE-WRITE ORDER (T4.S2): with d._lock: attempt = q.begin_offer(now) → release →
# pump.send_event(attempt.event()) (PumpClosed ⇒ ok=False) → with d._lock: q.finish_offer(ok). Never hold
# d._lock across send_event; never offer when attempt is None.
# CRITICAL #4 — ORDERING UNDER ONE LOCK HOLD: in each step() decide, under ONE d._lock hold: stage transitions
# (emit `listening` / `finishing`) AND begin_offer. If DRAINING is observed in the same hold as a pending
# offer, queue `finishing` FIRST and defer the offer to the next iteration (PRD: finishing is "ordered before
# any final accepted during that drain"). `listening` is emitted by the on_committed callback the moment the
# arm commits (no tick delay) — before any final can be enqueued (capture opens only after LISTENING).
# CRITICAL #5 — THE ENDED FRAME IS S6'S. Never build {"event":"ended",…} here. Register ONE daemon-level hook:
# daemon.set_native_teardown(self._on_native_ended); in it: pump.shutdown(state.frame()) (last line, then EOF;
# no-op if the pump is already lost), session.done.set(). Do NOT call shutdown() yourself elsewhere.
# If S6 has not landed (no set_native_teardown at HEAD) STOP and report — do not reimplement S6.
# CRITICAL #6 — REGISTER BEFORE BEGIN. Insert the session into self._sessions BEFORE begin_native_start so a
# synchronous end (stop-during-start, shutdown, Start-cap fire) always finds its pump. An end that arrives
# before the pump exists (handshake race) is logged at debug and dropped — the socket is gone anyway.
# CRITICAL #7 — `starting` IS {"event":"starting","id":sid} — NOT the PRD table's {"ok":true,"event":…}:
# _EVENT_SPECS closes it to {event,id} and validate_event (used by BOTH clients) rejects an extra key.
# Refusals use native_error_reply(code) via write_reject ({"ok":false,"error":code} then EOF) — S2's shape.
# CRITICAL #8 — PUMP CALLBACKS RUN ON PUMP THREADS (reader / writer / lease timer) with no pump lock held.
# on_command: `with d._lock: q.ack(obj)` / native_stop / native_cancel / native_lost are short lock holds and
# do no socket I/O (pump.shutdown is a queue put). on_loss → native_lost(cause.end_reason, cause.value, token=tok).
# A callback that raises is turned into REQUEST loss by the pump — wrap defensively anyway.
# CRITICAL #9 — NEVER BLOCK UNDER d._lock; NEVER WRITE ON THE RECORDER READER THREAD. The session loop waits on
# d._native_offer_evt with a bounded tick (≤ 0.5 s) so check_deadline and the revoked-queue safety net run;
# nothing in this item waits on end_evt (S6 CRITICAL: end_evt.set() already happened in _end_native_locked).
# CRITICAL #10 — THE HANDOFF READER. Pass the SAME FrameReader to OwnerPump(reader=reader): it holds bytes
# past the first frame's newline (unread). Close the generic wfile (makefile) BEFORE constructing the pump.
# CRITICAL #11 — wfile/close OWNERSHIP. After handoff the connection thread stays inside the session loop until
# the pump threads are joined (pump.wait ≤ WRITE_CAP_S + 1 s); only then return to _handle's finally (conn.close
# is then a harmless second close). Never close conn while the pump's reader is alive.
# CRITICAL #12 — LOSS ⇒ NO OUTPUT. A revoked queue (loss/cancel/overflow) accepts no ACK and offers nothing;
# REVOKED enqueues do NOT set _native_offer_evt (T4.S4). The session tick must notice `q.revoked` while the
# owner is still live and end it with delivery_failed (Task 0 decides whether S5/S6 already do this).
# CRITICAL #13 — CLOCK/TIMERS: construct the pump with clock=d._native_clock, timers=d._native_timers so tests'
# FakeClock/ManualTimers drive the lease too. Fallback via getattr(...) for stub daemons.
# CRITICAL #14 — LOGS: codes/counts/ids only. Never context text, final text, or a ProtocolError detail.
# CRITICAL #15 — AGENTS.md: every command under `timeout` with the bash-tool timeout above it; .venv/bin/python;
# tests/test_daemon.py = `timeout 500 … --tb=no`, bash timeout ≥ 560; never run the daemon/voicectl live;
# temp socket dirs under /tmp are RAM — mkdtemp with an EXIT trap; short paths (UNIX sun_path 108 bytes).
# CRITICAL #16 — DO NOT EDIT editor_session.py, session_recovery.py, recorder_host.py, feedback.py, ctl.py,
# config*, README, any plan file, PRD.md, tasks.json; no code change in editor_protocol.py; no T5 work.
```

## Implementation Blueprint

### Data models and structure

```python
@dataclasses.dataclass
class _NativeSession:
    """ONE owner connection's live native v1 session (P1.M1.T4.S7). Created on the connection thread by
    ControlServer._native_handshake; the same thread runs _run_native_session until the pump threads exit."""
    sid: str                          # the client's UUIDv4 (== NativeReservation.owner.id)
    token: int                        # daemon owner token — THE fence on every daemon call
    pump: "editor_protocol.OwnerPump"
    inbox: "collections.deque[dict]"  # validated owner commands from on_command (reader thread → session thread)
    inbox_evt: threading.Event        # set by on_command; cleared by step()
    started: bool = False             # begin_native_start() returned True
    listening_sent: bool = False
    finishing_sent: bool = False
    ended: "NativeEndState | None" = None   # set by the S6 teardown hook
    done: threading.Event = dataclasses.field(default_factory=threading.Event)
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)   # guards the flags only

def _listening_frame(sid: str, out: ArmOutcome, *, seed_empty: bool,
                    context_prompt_enabled: bool) -> dict:
    """PRD §4.8.1 B `listening` — same reason derivation as VoiceTypingDaemon.start_context
    (daemon.py `_context_reply`): empty seed → 'empty'; prompting disabled → 'disabled'; else 'unavailable'.
    `context_seeded` is True ONLY on a CONFIRMED seed (out.context_seeded is True); None (unconfirmed)
    is reported as False + 'unavailable'. Never carries the seed text."""
    if out.context_seeded is True:
        return {"event": "listening", "id": sid, "context_seeded": True}
    reason = "empty" if seed_empty else ("disabled" if not context_prompt_enabled else "unavailable")
    return {"event": "listening", "id": sid, "context_seeded": False, "context_reason": reason}
```

`seed_empty` = the handshake's normalized seed was empty (`_normalize_context(context)` → `""`), so
`begin_native_start(seed=None)`; `context_prompt_enabled` = `d._cfg.asr.context_prompt`.

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only, bounded; bash timeout ≥ 560 where noted):
  git log --oneline -1; git status --short | head            # S6 must have LANDED: grep -n "def set_native_teardown" voice_typing/daemon.py
  grep -nE "def (reserve_native|begin_native_start|_native_start_worker|native_stop|native_cancel|native_lost|native_settle_kick|terminate_native|_native_owner_live_locked|set_native_teardown|native_last_end|_normalize_context|_handle|_dispatch|start|stop)\b" voice_typing/daemon.py
  sed -n '<_native_start_worker range>p' voice_typing/daemon.py            # the `committed = …` line to hook on_committed after
  sed -n '<OfferQueue 213-430>p' voice_typing/editor_session.py            # begin_offer/finish_offer/ack/check_deadline exact semantics + OfferAttempt fields
  grep -n "def cancel" -A 25 voice_typing/daemon.py | grep -nE "native|busy"  # generic cancel under a live owner already returns busy (S4, :2491) — confirm; expect NO _dispatch change
  grep -n "revoked" voice_typing/daemon.py                               # does an overflow (REVOKED enqueue) already end the session?
  grep -nE "subprocess|run\(" tests/test_control_socket.py | head -3; sed -n '1,60p' tests/test_control_socket.py   # temp-socket + stub pattern to copy
  grep -nE "ruff|mypy|\[tool\." pyproject.toml | head                    # which linters exist (Level 1 commands below are conditional)
  ls tests | grep -E "protocol|pump|frame|native|editor|control|voicectl" # exact S2/S3/S4/S5/S6 suite names for Level 2
  grep -rnE "set\(s\) ==|unknown command" tests/test_control_socket.py tests/test_daemon.py | head   # exact pins that the native row must not break
  timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_native_lifecycle.py tests/test_editor_session.py -q   # green BEFORE you start
  timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40                  # baseline FAILED set (bash ≥ 560)

Task 1: CREATE tests/test_native_socket.py (RED first). CPU-only; the ONLY sockets are a private temp
  AF_UNIX path; the ONLY threads are the ControlServer's + the session's + the fake host's; no subprocess.
  HARNESS: `import test_daemon as td`; copy FakeClock/ManualTimers/_BHost/_ev/_listening_native/tripwire
  from tests/test_native_lifecycle.py; `d._native_clock, d._native_timers = fc.now, mt` right after
  `td._make_daemon(...)`; `srv = td_daemon_control_server(d, sock_dir)` — ControlServer(d, socket_path=<mkdtemp
  under /tmp, prefix "vt-ns-", EXIT trap rm -rf>, accept_timeout=0.05); srv.start(); a client helper
  `Client(path)` with settimeout(2.0), send(obj), recv() → dict | None(EOF), and `drain()`.
  Patch `subprocess.run`/`Popen` to raise AssertionError for the whole module (no notify/wtype/pactl).
  CASES (each asserts the FULL ordered list of daemon→editor frames + d.native_last_end() + tripwires):
   1 happy: editor-start → [starting, listening(context_seeded=false, reason=empty)] → fake final →
     [final seq=1] → applied(seq=1) → stop → [finishing] → [ended stopped] → EOF. Zero backend calls.
   2 context_seeded=true path via a confirming fake host (prime_prompt ack) and context_reason=disabled
     when cfg.asr.context_prompt=false.
   3 refusals (parametrized): bad version → unsupported_version; context 4 KiB+1 → too_large; unknown field /
     non-uuid id / wrong types → invalid_request; generic arm listening → busy; same id again → duplicate_id.
     Each: one {"ok":false,"error":code} line then EOF; d._native is None; nothing armed.
   4 non-owner frames unchanged: {"cmd":"status"} → generic reply; {"cmd":"ping","id":…} first → unknown command.
   5 lease: client never pings; fc.advance(6.0); mt.fire_due() → ended{timeout}; EOF; status native.state=ended.
   6 stalled write: client stops reading; push >64 KiB of finals (fake host) → WRITE loss → native_last_end
     reason disconnected; no backend call; session thread exits ≤ 3 s.
   7 late/duplicate/wrong ACK: applied(seq=1) twice → one offer, no replay; applied(seq=2) early →
     delivery_failed (REQUEST loss) and NO further final; ACK after 5 s (fc.advance) → ended{timeout}, then
     the late applied is ignored (no resend, no second ended).
   8 concurrent old clients: owner live → second connection status (ok, native.state=listening),
     start → busy, toggle → busy, cancel → busy (daemon.cancel() :2491), stop → owner gets
     finishing+ended{stopped}; afterwards a generic start works again.
   9 overflow: 9 finals, no ACKs → ended{delivery_failed}; exactly 8 final frames max on the wire; recovery
     retains (d._native_recovery.recover(sid) non-None); no truncated final.
  10 loss barriers: EOF mid-frame → disconnected; `lost` cmd → target_lost; `cancel` cmd → cancelled with
     host.cancel called and NO drain; 2nd editor-start on the owner connection → delivery_failed.
  11 stop during cold load (fake host spawn blocks on an Event) → ended{stopped} cause stop-during-start;
     release the Event → worker returns, mic NOT opened (d.is_listening() False).
  12 Start cap: fc.advance(30); mt.fire_due() → ended{timeout}; EOF.
  13 quit: generic `quit` on another connection → owner gets ended{shutdown}; srv.stop() joins ≤ 3 s;
     socket file unlinked; no thread named owner-pump-* alive afterwards.
  14 content tripwires on EVERY case: caplog + feedback snapshot + state.json + frames contain neither the
     context string nor the final text; logs carry only codes/counts/ids.
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_socket.py -q   → RED (bash timeout 360)

Task 2: EDIT voice_typing/daemon.py — daemon side (small, non-overlapping with S6's regions):
  - begin_native_start(self, token, *, seed=None, streaming=None, on_committed=None) -> bool; pass
    on_committed into the worker kwargs.
  - _native_start_worker: after `committed = …` and its _flush_native_end(), if committed and
    on_committed is not None: try: on_committed(out) except Exception: logger.warning("native on_committed
    raised (%s)", type(exc).__name__)  — off-lock, BEFORE r.end_evt.wait(). [Mode A] docstring line.
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_socket.py -q -k "happy or listen" → still RED

Task 3: EDIT voice_typing/daemon.py — ControlServer native route:
  - __init__: self._sessions = {}; self._sessions_lock = threading.Lock();
    if callable(getattr(daemon, "set_native_teardown", None)): daemon.set_native_teardown(self._on_native_ended)
  - _handle: after the strict UTF-8 decode: peek = json-parse (ValueError → None);
    if isinstance(peek, dict) and peek.get("cmd") == "editor-start": close wfile; sess =
    self._native_handshake(conn, reader, peek); if sess is not None: self._run_native_session(sess); return
    (else fall through to the generic reply path — the handshake already wrote the refusal).
  - _native_handshake: validate_request(peek) → ProtocolError → write_reject(conn, exc.code); return None.
    res = self._daemon.reserve_native(conn, peek["id"], on_end=None); if not res.accepted →
    write_reject(conn, res.error); return None. sess = _NativeSession(sid, res.owner.token, pump=None, …)
    pump = OwnerPump(conn, sid, on_command=lambda o: self._native_on_command(sess, o),
                     on_loss=lambda c, detail="": self._native_on_loss(sess, c), reader=reader,
                     clock=getattr(d, "_native_clock", time.monotonic), timers=getattr(d, "_native_timers", None))
    sess.pump = pump; with self._sessions_lock: self._sessions[sid] = sess   # BEFORE begin (CRITICAL #6)
    try: pump.send_event({"event": "starting", "id": sid})
    except (PumpClosed, FrameError) as exc: self._daemon.terminate_native("disconnected",
        cause=getattr(exc, "cause", "write"), token=sess.token); self._drop(sess); return None
    seed = _normalize_context(peek["context"]) or None
    pump.start()
    sess.started = self._daemon.begin_native_start(sess.token, seed=seed, on_committed=sess.on_committed)
    if not sess.started: # ended between reserve and begin (stop/shutdown/cap) — the hook already/soon delivers ended
        pass
    return sess
  - _run_native_session(sess): loop: while not sess.done.is_set(): sess.step(self._daemon); if done: break;
      d._native_offer_evt.wait(0.5)  (the FIRST `starting` is already queued; `listening` comes from
      on_committed). Finally: pump.wait(WRITE_CAP_S + 1.0); self._drop(sess); log one line (codes only).
  - _NativeSession.step(d) [unit-testable, no sleeping]: process inbox (applied → with d._lock: q.ack →
      d.native_settle_kick(); stop/cancel/lost → the S5 funnels with token=tok); then ONE lock hold:
      r = d._native; live = d._native_owner_live_locked(); stage = r.stage if live else None; q = d._native_queue;
      due_listen = stage is LISTENING and not listening_sent; due_finish = stage is DRAINING and not finishing_sent;
      attempt = None if (due_finish or q is None) else q.begin_offer(d._native_clock()); revoked = q.revoked if q else False
      → release → if due_listen: (normally already sent by on_committed; if not — e.g. the callback was
      lost — send it now from d.status/native… NO: without the ArmOutcome you cannot know context_seeded;
      so REQUIRE on_committed and treat "LISTENING but never committed-callbacked" as impossible — assert/log)
      if due_finish: send finishing; if attempt: send_event(attempt.event()) → finish_offer(ok);
      if revoked and live: d.native_lost("delivery_failed", "overflow", token=tok)  (CRITICAL #12, per Task 0);
      with d._lock: q.check_deadline(d._native_clock()) → d.native_settle_kick()   (only when q has an outstanding offer)
  - _on_native_ended(state): sess = self._sessions.get(state.session_id); if None → debug log, return;
      sess.ended = state; try: sess.pump.shutdown(state.frame()) except Exception: log type name; sess.done.set()
  - _on_command(sess, obj)/_on_loss(sess, cause): append to inbox + inbox_evt.set() / native_lost(
      cause.end_reason, cause.value, token=tok) + sess.done? (no — the end arrives via the hook)
  - stop(): after joining the accept thread: self._retire_sessions(3.0) → for each live session:
      terminate_native("shutdown", cause="shutdown", token=tok) (idempotent), wait sess.done ≤ remaining budget.
  - dispatch: `cancel` under a live owner → busy. EXPECTED NO CHANGE: VoiceTypingDaemon.cancel() (daemon.py :2491, S4) already returns busy under a live owner; only add a _dispatch branch if Task 0 shows otherwise.
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_socket.py -q → GREEN (bash timeout 360)

Task 4: EDIT voice_typing/editor_protocol.py — DOCS ONLY (no behaviour change; `git diff` shows comments only):
  module docstring: "Dispatch (P1.M1.T4.S7): ControlServer._handle routes a first frame with cmd
  editor-start → validate_request → reserve_native → write_reject | OwnerPump…"; OwnerPump docstring:
  MESSAGE LIFECYCLE table — starting (session, before begin_native_start) · listening (on_committed, once,
  before any final) · final (begin_offer → send_event → finish_offer; one outstanding) · pong (pump) ·
  finishing (session, once, on DRAINING, before drain finals) · ended (S6 hook → shutdown(terminal), last
  frame then EOF); timers: lease 6 s (pump) · Start cap 30 s (daemon watchdog) · ACK 5 s (q.check_deadline
  on the session tick ≤ 0.5 s) · write cap 2 s (writer). ControlServer docstring gets the same table + the
  native first-frame row; _handle/_dispatch docstrings updated. [Mode A]
  RUN: timeout 120 .venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/editor_protocol.py tests/test_native_socket.py && echo L1 PASS

Task 5: FULL GATES (Level 2/3 below) + `git diff --name-only` check (k).
```

### Implementation Patterns & Key Details

```python
# THE SESSION STEP — one lock hold decides; everything that can block or write happens after release
def step(self, d) -> None:
    self._drain_inbox(d)                       # applied/stop/cancel/lost from the pump reader (S5 contracts)
    with d._lock:
        live = d._native_owner_live_locked()
        r = d._native
        stage = r.stage if live else None
        q = d._native_queue if live else None
        now = d._native_clock()
        due_finish = stage is Stage.DRAINING and not self.finishing_sent
        attempt = None if (q is None or due_finish) else q.begin_offer(now)   # finishing FIRST (CRITICAL #4)
        revoked = bool(q.revoked) if q is not None else False
        outstanding = q.outstanding is not None if q is not None else False   # OfferQueue.outstanding: OfferAttempt | None
    if due_finish:
        self._send({"event": "finishing", "id": self.sid}); self.finishing_sent = True
    if attempt is not None:
        ok = True
        try: self.pump.send_event(attempt.event())
        except PumpClosed: ok = False
        with d._lock: d._native_queue.finish_offer(ok) if d._native_queue is not None else None   # mark-before-write
    if outstanding or attempt is not None:
        with d._lock:
            q = d._native_queue
            if q is not None: q.check_deadline(d._native_clock())
        d.native_settle_kick()                 # off-lock; without it `ended` waits for the 5 s watchdog
    if revoked and live:
        d.native_lost("delivery_failed", "overflow", token=self.token)   # CRITICAL #12 — per Task 0

# on_committed — runs on the native-start worker thread, off-lock, the moment the arm commits
def on_committed(self, out: ArmOutcome) -> None:
    if self.listening_sent or self.ended is not None: return
    self._send(_listening_frame(self.sid, out, self.context_prompt_enabled)); self.listening_sent = True

def _send(self, obj: dict) -> None:            # EVERY daemon→editor line is codec-validated first
    validate_event(obj)
    try: self.pump.send_event(obj)
    except (PumpClosed, FrameError): pass      # loss is the pump's business (on_loss already fired / will fire)
```

```yaml
INTEGRATION POINTS:
  SOCKET:   none new — the existing ControlServer path ($XDG_RUNTIME_DIR/voice-typing/control.sock, 0700/0600, listen(8))
  CONFIG:   none (all bounds are code constants in editor_protocol.py / editor_session.py)
  GENERIC:  start/toggle → busy under an owner (S4, exists); cancel → busy (Task 0); status/stop/quit unchanged
  HOOKS:    daemon.set_native_teardown(ControlServer._on_native_ended) — ONE registration, at ControlServer construction
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
timeout 120 .venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/editor_protocol.py tests/test_native_socket.py && echo "L1 PASS"
# Only if pyproject configures them (Task 0): else print "not configured — skipped"
timeout 120 uv run ruff check voice_typing/daemon.py voice_typing/editor_protocol.py tests/test_native_socket.py
timeout 120 uv run ruff format --check voice_typing/daemon.py voice_typing/editor_protocol.py tests/test_native_socket.py
# Expected: zero errors; editor_protocol.py diff is comments/docstrings only: git diff -w --stat voice_typing/editor_protocol.py
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_native_socket.py -q                 # bash timeout 360
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_editor_session.py \
    tests/test_native_lifecycle.py tests/test_native_teardown.py tests/test_editor_offer_queue.py \
    tests/test_native_final_route.py tests/test_native_recovery.py -q                   # + S2/S3 suites named in Task 0
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40 # bash timeout ≥ 560; FAILED set == G1 CPU addendum
# Expected: all green; any NEW test_daemon failure blocks (set-diff against tests/G1_BASELINE.md)
```

### Level 3: Integration Testing (System Validation)

```bash
# Production boundary WITHOUT the live daemon: the suite above drives the real ControlServer on a private
# socket with the real VoiceTypingDaemon + fake host. Explicitly:
timeout 300 .venv/bin/python -m pytest tests/test_native_socket.py -q -k "happy or refuse or lease or overflow or quit or tripwire" -v
# After the run: no leftover threads/sockets —
pgrep -af "owner-pump|voice-typing-daemon" || echo "no stray processes"      # must print the fallback
ls /tmp | grep -c "^vt-ns-" || true                                           # must be 0 (EXIT trap ran)
# Expected: the wire traces match PRD §4.8.1 B exactly; nothing typed, nothing notified, no subprocess.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Protocol cross-check against the codec vectors (both clients share validate_event/validate_request):
timeout 120 .venv/bin/python - <<'EOF'
from voice_typing import editor_protocol as ep
for ev in ({"event":"starting","id":"x"*8+"-1234-4abc-8def-0123456789ab"},
           {"event":"finishing","id":"x"*8+"-1234-4abc-8def-0123456789ab"}):
    try: ep.validate_event(ev); print("ok", ev["event"])
    except ep.ProtocolError as e: print("INVALID", ev["event"], e.code, e.detail)
EOF
# (the id above is deliberately NOT a v4 uuid for brevity — expect invalid_request; rerun with a real UUIDv4 for "ok")
# Thread/lock audit (manual, 2 min): grep -nE "with self\._daemon\._lock|with d\._lock" voice_typing/daemon.py | sed -n '<ControlServer range>'
#   → inside every hold: attribute stores, OfferQueue transitions, native_* calls only; no send/wait/join/sleep.
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1–4 completed; `timeout 300 .venv/bin/python -m pytest tests/test_native_socket.py -q` green
- [ ] `tests/test_daemon.py` FAILED set == G1 CPU addendum (set-diff); control-socket + S2–S6 suites green
- [ ] No lint/type/format regressions (where configured); `editor_protocol.py` diff is docs-only
- [ ] `git diff --name-only` ⊆ `{voice_typing/daemon.py, voice_typing/editor_protocol.py, tests/test_native_socket.py}`

### Feature Validation
- [ ] (a)–(k) hold; every case's full frame trace asserted; EOF after `ended`
- [ ] Error cases: refusals are one `{"ok":false,"error":code}` line + EOF; loss never produces output
- [ ] One live owner; old generic clients unchanged except `busy` where the PRD says so
- [ ] `ControlServer.stop()` and `quit` retire the session in ≤ 3 s with no stray threads/sockets

### Code Quality Validation
- [ ] Patterns follow S5/S6 (lock hold decides → off-lock side effects); no new lock types; no new config
- [ ] File placement matches the tree above; no edits to read-only modules
- [ ] Logs are codes/counts/ids only

### Documentation & Deployment
- [ ] [Mode A] `ControlServer` docstring protocol table + lifecycle; `editor_protocol.py` lifecycle docs
- [ ] No new environment variables; no README change (P1.M2.T4.S1)

## Anti-Patterns to Avoid

- ❌ Branching on `request_kind()` for first-frame detection (plain `stop`/`cancel` are native cmds too)
- ❌ Writing to the socket from the session/daemon thread, or a second writer beside the pump
- ❌ Holding `d._lock` across `send_event`, `native_settle_kick`, any wait, or a callback
- ❌ Building the `ended` frame or calling `pump.shutdown()` outside S6's teardown hook
- ❌ Resending/replaying an offer on timeout, duplicate ACK, or write uncertainty
- ❌ Falling back to `StreamingOutput`/typing/paste/clipboard/evdev on any native failure
- ❌ Emitting `{"ok":true,"event":"starting"}` (fails `validate_event`) or `listening` after a `final`
- ❌ Running the live daemon or `voicectl` in tests; unbounded logs/scratch under `/tmp`
