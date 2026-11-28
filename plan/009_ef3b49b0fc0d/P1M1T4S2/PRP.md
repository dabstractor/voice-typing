# PRP — P1.M1.T4.S2: Enforce one sequenced offer and verified ACK

## Goal

**Feature Goal**: Add `OfferQueue` to `voice_typing/editor_session.py` — the native-v1 FIFO policy that
delivers accepted finals to the editor as **one outstanding sequenced offer at a time** and settles it only
on an **exact verified ACK**: eight unsettled finals max (pending + the one outstanding), each ≤ 4 KiB
UTF-8, monotonic `seq` from 1, 5 s ACK deadline owned by the queue, the write **attempt recorded before the
write**, duplicate-of-last-ACK harmless (no extension, no replay), and malformed / stale / uncertain /
failed delivery **revoking** (sticky). Overflow retains for recovery and revokes — never a truncated
insert. Pure transitions, injected clock, injected write result — no socket wait inside a state change.

**Deliverable** (append to 1 module, 1 new test file):
1. `voice_typing/editor_session.py` — APPEND `OfferQueue` (+ `EnqueueOutcome`, `AckOutcome`, `OfferAttempt`
   enums/dataclass), extend `__all__`, add a Mode A module-docstring paragraph on queue/attempt semantics
   and deadline ownership. T3.S4's reservation classes are NOT edited.
2. `tests/test_editor_offer_queue.py` — hermetic tests over the real `NativeRecovery`, a fake clock and a
   fake write result.

**Success Definition**:
- (a) Sequential delivery: a second final is never offered while one is outstanding; after the exact ACK
  the next is offered with `seq` = previous + 1.
- (b) Attempt-before-write: `recovery.mark_offer_attempted` is true for the outstanding seq before the
  caller's write runs; the deadline is stamped at the attempt (write cap inside the ACK budget).
- (c) Only exact ACK settles (`id` + `seq` == outstanding). Exact duplicate of the last ACK → no-op that
  does not alter a new outstanding's deadline. Malformed / wrong id / stale / never-offered seq → revoke.
- (d) Deadline: `now >= deadline` with the offer still outstanding → revoke `timeout`. Failed write →
  revoke `delivery_failed` — unless a verified ACK already settled it (ACK wins).
- (e) Capacity: the 9th unsettled final (8 queued incl. outstanding) is retained in recovery and revokes
  (`delivery_failed`); no truncated insert. Oversize/lone-surrogate text → same path.
- (f) Revoke is sticky: later `enqueue` retains only, `begin_offer` returns `None`.
- (g) `timeout 300 .venv/bin/python -m pytest tests/test_editor_offer_queue.py tests/test_editor_session.py tests/test_editor_protocol_vectors.py tests/test_session_recovery.py tests/test_native_recovery.py -q` → all green.
- (h) `git diff --name-only` == `{voice_typing/editor_session.py, tests/test_editor_offer_queue.py}`.

## User Persona

**Target User**: the dictation user in a native editor (Pi prompt, Neovim) — and the editors' authors.
**Use Case**: finals stream from the daemon to the editor over the owner socket; the editor ACKs each
`final` event with `{"cmd":"applied","seq":n}`.
**Pain Points Addressed**: duplicated or missing text from re-sends after a lost ACK, unbounded
outstanding text, and silent truncation — the queue makes "bytes sent" ≠ "delivered" explicit and keeps
undelivered text recoverable instead of guessing.

## Why

- PRD §4.8.1 B/C (delta 009): delivery is verified by ACK only; `system_context.md` "Buffer ownership and
  recovery" specifies the eight-slot FIFO, mark-before-write, exact-ACK settle, harmless duplicate ACK,
  revoke-on-uncertainty, 5 s ACK deadline, and "no waits/writes on the daemon control lock or recorder
  reader". This task is that policy as a reusable leaf.
- T4.S4 (route native finals), T4.S5 (stop/cancel/drain) and T4.S7 (socket activation) all consume these
  operations; without the leaf each would re-implement the state machine.

## What

### Success Criteria
- [ ] `OfferQueue` API: `enqueue`, `begin_offer`, `finish_offer`, `ack`, `check_deadline`, `revoke`,
      `clear_pending`, `drain_pending`, `close`; read-only `outstanding`, `revoked`, `revocation_reason`,
      `last_ack_seq`, `session_id`, `pending_count`.
- [ ] Every transition is pure: no lock taken inside, no I/O, no threads; `clock` and the write result are
      injected. All reasons are `END_REASONS` codes; no text leaks into reasons.
- [ ] (a)–(h) above hold; T3.S4's `tests/test_editor_session.py` stays green.

## All Needed Context

### Context Completeness Check
_Pass._ Protocol validators, enums, helper names and the write-path return types are listed with line
numbers; T3.S4's module discipline is quoted; the T4.S1 recovery method contract is given; the full state
machine, the begin/finish split and every outcome are specified below with a verbatim test list.

### Documentation & References

```yaml
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S2/research/offer_queue_policy.md
  why: "§1 protocol facts (validators :277/:322, EndReason :129, LossCause :414, send_line_capped -> bool,
        OwnerPump.send_event -> None), §2 T3.S4's module discipline + the begin/finish split rationale,
        §3 NativeRecovery contract, §4 the design decisions."
  critical: "ACK arriving between begin_offer and finish_offer settles normally; a then-failed write must
            NOT revoke — the verified ACK wins."
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Buffer ownership and recovery' paragraph = the spec; 'Control/recorder boundaries' = the lock rule."
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S1/PRP.md
  why: "NativeRecovery (appended to voice_typing/session_recovery.py): retain_final(sid, seq, text)->bool
        (auto-creates the active session if none), mark_offer_attempted(sid, seq)->bool,
        settle_final(sid, seq)->bool (removes), end_session(sid, reason), active_id(), counts(), clear()."
  critical: "retain_final auto-creates a session — the queue MUST refuse enqueue after close() so a late
            final cannot resurrect an ended session."
- file: voice_typing/editor_protocol.py
  why: "Reuse, don't re-implement: validate_request (:277, raises ProtocolError), validate_event (:322),
        MAX_FINAL_TEXT_BYTES, is_uuid_v4, utf8_len, has_lone_surrogates (:170-184), END_REASONS (:145)."
  pattern: "from voice_typing.editor_protocol import (END_REASONS, MAX_FINAL_TEXT_BYTES, ProtocolError,
            has_lone_surrogates, utf8_len, validate_event, validate_request)  # extend the existing import"
  gotcha: "READ ONLY (T3.S2/T3.S3 own it). seq minimum is 1 in both validators."
- file: voice_typing/editor_session.py
  why: "APPEND after NativeReservation (:115). Match the header discipline: 'pure transition ... under the
        CALLER's lock; nothing here takes a lock', injected clock, fixed codes only."
  pattern: "@dataclass(frozen=True) + str-enum outcomes, as Stage/EndRecord/NativeReserveResult do (:28-62)."
  gotcha: "Do NOT edit :28-115. `__all__` (:26) gains the new names only. T3.S4 must be complete first."
- file: tests/test_editor_pump.py
  why: "Style reference for hermetic tests with an injected clock/fake conn (no sockets)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/editor_protocol.py    # T3.S2/S3 — READ ONLY (validators, enums, helpers, pump)
voice_typing/editor_session.py     # T3.S4 reservation (in flight) — APPEND ONLY                  ← EDIT
voice_typing/session_recovery.py   # T4.S1 NativeRecovery (in flight) — READ ONLY, consumed
tests/test_editor_session.py       # T3.S4 — do not touch
tests/test_editor_offer_queue.py   # NEW                                                           ← CREATE
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DEPENDENCY GATE: both P1.M1.T3.S4 (NativeReservation in editor_session.py +
# tests/test_editor_session.py) and P1.M1.T4.S1 (class NativeRecovery in session_recovery.py +
# tests/test_native_recovery.py) must be present. If either is missing → STOP and report.
# CRITICAL #2 — NO LOCK INSIDE OfferQueue, and the caller must NOT hold the daemon _lock across the
# write: begin_offer() -> write(event) outside the lock -> finish_offer(ok).
# CRITICAL #3 — MARK BEFORE WRITE: recovery.mark_offer_attempted(sid, seq) and the deadline stamp happen
# in begin_offer, before the caller writes. A failed/uncertain write therefore leaves possibly_applied
# set in recovery — correct; never clear it, never resend.
# CRITICAL #4 — CAPACITY COUNTS UNSETTLED ITEMS (pending + outstanding) <= 8; settle_final frees a slot.
# CRITICAL #5 — REASONS ARE CODES: "timeout" | "delivery_failed" | (T4.S5 passes "cancelled"). Never
# text, never a ProtocolError detail in a reason.
# CRITICAL #6 — pytest under `timeout 300` with the bash-tool timeout above it; .venv/bin/python (zsh
# aliases shadow python3). No daemon, no sockets, no threads in tests.
# CRITICAL #7 — DO NOT EDIT editor_protocol.py, session_recovery.py, daemon.py, test_editor_session.py,
# any plan file, PRD.md, tasks.json, README.
```

## Implementation Blueprint

### Data models and structure

```python
ACK_TIMEOUT_S: float = 5.0          # §4.8.1: offer ACK deadline (code constant, not config)
MAX_UNSETTLED: int = 8              # eight finals total INCLUDING the one outstanding

class EnqueueOutcome(str, enum.Enum):
    QUEUED = "queued"; REVOKED = "revoked"; CLOSED = "closed"
class AckOutcome(str, enum.Enum):
    SETTLED = "settled"; DUPLICATE = "duplicate"; REVOKED = "revoked"; IGNORED = "ignored"

@dataclass(frozen=True)
class _Item: seq: int; text: str
@dataclass(frozen=True)
class OfferAttempt:                 # begin_offer's result; the event is pre-validated
    seq: int; text: str; deadline: float
    def event(self) -> dict: return {"event": "final", "id": self.session_id, "seq": self.seq, "text": self.text}

class OfferQueue:
    def __init__(self, session_id: str, recovery, *, clock=time.monotonic,
                 ack_timeout_s: float = ACK_TIMEOUT_S, max_unsettled: int = MAX_UNSETTLED) -> None
    # state: _pending: deque[_Item]; _outstanding: _Item | None; _deadline: float | None;
    #        _next_seq = 1; _last_ack = 0; _revoked = False; _reason = None; _closed = False
```

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT — grep -n "class NativeReservation" voice_typing/editor_session.py;
        grep -n "class NativeRecovery" voice_typing/session_recovery.py; ls tests/test_editor_session.py
        tests/test_native_recovery.py. All four present, else STOP (Gotcha #1).

Task 1: CREATE tests/test_editor_offer_queue.py (RED first) — hermetic, fake clock, real NativeRecovery:
  - harness: `class Clock: t=0.0; __call__ -> t`; `mk()` -> (OfferQueue, NativeRecovery, Clock) with
    sid = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b" (uuid v4).
  - test_sequential_offers_settle_on_exact_ack — enqueue a,b; begin -> seq1; begin again -> None;
    ack({"cmd":"applied","id":sid,"seq":1}) SETTLED; begin -> seq2; recovery.counts()[1] == 1 then 0.
  - test_attempt_recorded_and_deadline_stamped_before_write — after begin: recovery snapshot
    possibly_applied True; attempt.deadline == 5.0.
  - test_only_exact_ack_settles — outstanding seq1: ack seq2 -> REVOKED("delivery_failed"); fresh queue:
    ack with other id -> REVOKED; ack seq 0 / "1" / missing -> REVOKED (validate_request).
  - test_duplicate_last_ack_is_harmless — settle seq1, begin seq2 at t=10, ack seq1 again -> DUPLICATE,
    queue.outstanding still seq1.. (i.e. seq2) with deadline 15.0, not revoked.
  - test_deadline_revokes_timeout — begin at t=0; check_deadline(4.9) False; check_deadline(5.0) True,
    revoked "timeout"; recovery still holds the final (possibly_applied True).
  - test_failed_write_revokes_unless_already_settled — begin; finish_offer(False) -> revoked
    "delivery_failed"; begin; ack exact; finish_offer(False) -> NOT revoked.
  - test_overflow_retains_and_revokes — 8 enqueues QUEUED; 9th -> REVOKED, recovery final_count == 9,
    no truncation (texts intact); begin -> None.
  - test_oversize_and_invalid_text_revoke — 4097-byte text, lone surrogate "\ud800" -> REVOKED.
  - test_revoke_is_sticky_and_close_blocks_enqueue — revoke("cancelled"); enqueue -> REVOKED but retained;
    close(); enqueue -> CLOSED, recovery counts unchanged.
  - test_clear_pending_and_drain_pending — clear_pending drops unattempted only; drain_pending True while
    outstanding/pending, False after settle + clear.
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_editor_offer_queue.py -q  -> ImportError/RED.

Task 2: EDIT voice_typing/editor_session.py — extend the editor_protocol import; APPEND OfferQueue:
  - enqueue(text) -> EnqueueOutcome: if _closed -> CLOSED (no retain). seq=_next_seq; _next_seq+=1.
    invalid = (not text.strip()) or has_lone_surrogates(text) or utf8_len(text) > MAX_FINAL_TEXT_BYTES.
    retained = recovery.retain_final(sid, seq, text.strip())  (always try — retain-before-offer).
    if _revoked: return REVOKED.  if invalid or not retained: revoke("delivery_failed"); return REVOKED.
    if len(_pending) + (1 if _outstanding else 0) >= max_unsettled: revoke("delivery_failed"); REVOKED.
    _pending.append(_Item(seq, text.strip())); return QUEUED.
  - begin_offer(now=None) -> OfferAttempt | None: None if _revoked/_closed/_outstanding/not _pending.
    item=_pending.popleft(); recovery.mark_offer_attempted(sid, item.seq);
    attempt=OfferAttempt(sid, item.seq, item.text, clock()+ack_timeout_s);
    try validate_event(attempt.event()) except ProtocolError: revoke("delivery_failed"); return None.
    _outstanding=item; _deadline=attempt.deadline; return attempt.
  - finish_offer(ok: bool) -> None: if not ok and _outstanding: revoke("delivery_failed").
  - ack(obj, now=None) -> AckOutcome: if _revoked: IGNORED. try validate_request(obj) except
    ProtocolError: revoke("delivery_failed"); return REVOKED. if obj["cmd"] != "applied": IGNORED.
    if obj["id"] != sid: revoke("delivery_failed"); REVOKED. seq=obj["seq"];
    if _outstanding and seq == _outstanding.seq: recovery.settle_final(sid, seq); _outstanding=None;
    _deadline=None; _last_ack=seq; SETTLED.  elif seq == _last_ack: DUPLICATE.
    else revoke("delivery_failed"); REVOKED.
  - check_deadline(now=None) -> bool: True (after revoke("timeout")) iff _outstanding and now >= _deadline.
  - revoke(reason) -> str|None: first call sets _revoked/_reason and returns reason; later None.
    Does NOT clear _pending or touch recovery.
  - clear_pending() -> int; drain_pending() -> bool; close() -> None (sets _closed; revoke noop-safe).
  - Mode A docstrings: queue/attempt semantics (mark-before-write, possibly_applied survives), deadline
    ownership (the queue stamps at attempt; the caller's timer calls check_deadline; write cap is inside
    the ACK budget), no-lock discipline (begin -> write outside lock -> finish).

Task 3: EDIT the module docstring + __all__ (one paragraph; add OfferQueue, OfferAttempt,
        EnqueueOutcome, AckOutcome, ACK_TIMEOUT_S, MAX_UNSETTLED).

Task 4: VERIFY: the Task-1 file green; T3.S4 + protocol + recovery suites green (Success (g)).
Task 5: VALIDATE L1–L3. Commit only if the orchestrator directs.
```

### Implementation Patterns & Key Details

```python
# CALLER PATTERN (T4.S4/S5/S7 — documented in the docstring):
with d._lock:
    attempt = q.begin_offer(now)
if attempt is not None:                      # write OUTSIDE the lock (2 s whole-frame cap)
    ok = send_line_capped(conn, encode_line(attempt.event()))
    with d._lock: q.finish_offer(ok)
# reader thread: with d._lock: q.enqueue(text)      # retains + queues, never writes
# pump on_command: with d._lock: q.ack(obj)          # exact-ACK settle / revoke
# timer: with d._lock: q.check_deadline(now)         # revoke("timeout") at the deadline
```

### Integration Points

```yaml
CONSUMED BY: P1.M1.T4.S4 (enqueue from the reader thread after the gates), P1.M1.T4.S5
  (drain_pending / clear_pending / revoke("cancelled")), P1.M1.T4.S7 (ack via on_command,
  check_deadline via the pump timer, send_line_capped as the write).
NO CONFIG / SOCKET / STATUS CHANGES. Reasons map 1:1 onto EndReason for T4.S6's `ended` frame.
```

## Validation Loop

### Level 1: Static
```bash
cd /home/dustin/projects/voice-typing
grep -nE "^class OfferQueue|^class OfferAttempt|^class EnqueueOutcome|^class AckOutcome|^ACK_TIMEOUT_S|^MAX_UNSETTLED" voice_typing/editor_session.py
grep -n "Lock()" voice_typing/editor_session.py || echo "L1 PASS: no lock in the module"
.venv/bin/python -m py_compile voice_typing/editor_session.py && echo "L1 PASS"
```
### Level 2: Tests
```bash
PY=.venv/bin/python
timeout 300 "$PY" -m pytest tests/test_editor_offer_queue.py -q
timeout 300 "$PY" -m pytest tests/test_editor_session.py tests/test_editor_protocol_vectors.py tests/test_session_recovery.py tests/test_native_recovery.py -q 2>&1 | tail -2
```
### Level 3: Scope
```bash
git diff --name-only   # == voice_typing/editor_session.py, tests/test_editor_offer_queue.py
git diff -- voice_typing/editor_session.py | grep -c "^-[^-]"   # only the __all__/import/docstring lines changed
```

## Final Validation Checklist
- [ ] L1–L3 pass; Success (a)–(h) hold; T3.S4/T4.S1/T3.S2 suites unchanged-green.
- [ ] No lock/I/O/threads in the queue; reasons are codes only; `ended`-ready.
- [ ] Mode A docstring covers queue/attempt semantics + deadline ownership + the caller pattern.

## Anti-Patterns to Avoid
- ❌ Resending, extending a deadline, or replaying on duplicate/late ACK; ❌ locking inside the queue or
  writing under the daemon `_lock`; ❌ truncating an oversize final instead of retain+revoke; ❌ clearing
  `possibly_applied` on failure; ❌ editing T3.S4's classes or any read-only file; ❌ un-timed pytest.

## Confidence Score
**9/10** — protocol validators/enums and both dependency contracts are pinned with line numbers; the
one residual is the parallel T3.S4/T4.S1 landing shape, gated by Task 0.
