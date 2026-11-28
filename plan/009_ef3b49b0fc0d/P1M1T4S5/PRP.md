# PRP — P1.M1.T4.S5: Stop, cancel and drain one native utterance

## Goal

**Feature Goal**: Give the daemon's native editor session (PRD §4.8.1 B) **one bounded wind-down
policy with one terminal action**. While a native owner holds the mic, every way the session can end is
routed through native finishing — never through the generic `graceful_stop` heuristic:

| trigger | stage path | behaviour (PRD §4.8.1 B) |
|---|---|---|
| owner `stop`, `voicectl stop` / `toggle`-off, idle auto-stop | LISTENING → DRAINING(reason) | **at most the already-in-flight utterance** finishes (bounded ASR drain, `_DRAIN_TIMEOUT_S` = 5 s), then queued offers settle for **≤ 5 s aggregate** (`NATIVE_SETTLE_TIMEOUT_S`), only while the target is still valid; END carries the recorded reason, or `timeout` / `delivery_failed` |
| owner `cancel` | LISTENING → ENDED(`cancelled`) | **invalidate first** (revoke queue + drop unattempted finals + end), then abort in-flight audio; no drain, no new capture |
| owner `lost`, EOF, lease expiry | revoke first, then DRAINING → ENDED(loss reason) | at most the in-flight utterance drains **into recovery only** (no ACK can arrive) — no settlement wait; loss while STARTING ends without capture |
| shutdown, recorder-host death | any → ENDED | end at once; no recoverable-drain promise (existing `terminate_native` calls kept) |

No abort, cancel, drain wait or settlement wait runs under `self._lock` or on the recorder reader
thread. The terminal transition is idempotent when Stop / loss / exit / EOF race (first reason wins).

**Deliverable** (3 files edited, 1 created):
1. `voice_typing/daemon.py` — policy hooks `native_stop` / `native_cancel` / `native_lost` /
   `native_settle_kick`, the settlement step + watchdog, the DRAINING rule in `_native_final_verdict`,
   routing in `_request_stop` / `_maybe_auto_stop` / `_disarm` tail, `_end_native_locked` as THE terminal
   action, `_begin_drain` split; [Mode A] docstrings.
2. `voice_typing/editor_session.py` — **docstring-only** lifecycle updates.
3. `voice_typing/ctl.py` — **help-text-only** update for `stop` and `cancel`.
4. `tests/test_native_lifecycle.py` — hermetic CPU-only tests (new).

**Success Definition**:
- (a) Graceful stop with an utterance in flight: stage DRAINING, `_drain` True, mic still on, pump woken;
  the final of THAT utterance is retained + queued; any other utterance's final is rejected (`drain`).
- (b) Graceful stop with nothing in flight: mic off now, ENDED promptly with the stop reason, no abort,
  no cancel, no settlement timer.
- (c) After the ASR drain: settlement deadline = clock + 5 s on `self._native_clock()`, one watchdog
  handle on `self._native_timers`; ends early when the queue is settled; ends `timeout` at the deadline
  with unsettled work (queue revoked, text still recoverable).
- (d) Native stop drains **regardless of `cfg.asr.graceful_stop`**.
- (e) Cancel: queue revoked `cancelled` + pending cleared BEFORE the end; ENDED(`cancelled`,
  cause `cancel`); mic off; `host.cancel()` exactly once when `text()` is in flight, never otherwise,
  never under `_lock`; a late final is neither retained nor typed.
- (f) Loss: queue revoked with the loss reason + pending cleared first; in-flight utterance retained
  (recovery-only, `enqueue` → REVOKED, pump NOT woken); ENDED immediately after the drain, no
  settlement timer; loss while STARTING ends without capture.
- (g) Idle auto-stop tags/routes `idle` only when the idle condition actually holds (a non-idle native
  session stays LISTENING).
- (h) Second stop / stop-after-end / stale-token kick are no-ops; `on_end` fires exactly once per session.
- (i) Shutdown and host death end a settling session at once; the settle watchdog handle is cancelled.
- (j) With no native reservation every generic path behaves exactly as today (`tests/test_daemon.py`
  FAILED set == G1 baseline, set-diff).
- (k) `host.abort()` / `host.cancel()` are never called while `d._lock` is held; stop/cancel/lost/settle
  start no thread other than the existing drain watchdog `Timer`.
- (l) No new log line or `EndRecord` carries recognition text — codes, counts, ids only.
- (m) `timeout 300 .venv/bin/python -m pytest tests/test_native_lifecycle.py
  tests/test_editor_session.py tests/test_editor_offer_queue.py tests/test_native_recovery.py -q` → green.
- (n) `git diff --name-only` == `{voice_typing/daemon.py, voice_typing/editor_session.py,
  voice_typing/ctl.py, tests/test_native_lifecycle.py}` (+ a test that pins the old help text, if any).

## User Persona

**Target User**: the dictation user inside a native editor (Pi prompt, Neovim) — reached through the
T4.S7 owner-connection pump and the T4.S6 `ended` frame/hints.
**Use Case**: Start from the editor, speak several utterances, then Stop (finish the sentence in
progress), Cancel (drop what I am saying), or simply close/leave the editor (loss).
**Pain Points Addressed**: a stop that cuts the last word or hangs on the decoder; a cancelled
utterance still being inserted; a closed editor being waited on; `ended` arriving before the last
ACK or never; a stop/idle tag flipping the session to "finishing" while the user is still talking.

## Why

- PRD §4.8.1 B: "`stop` drains, retaining the editor as sink; `cancel` invalidates and aborts; `lost`
  invalidates and drains for recovery only." "Existing bounded ASR drain applies after Stop/loss; allow
  up to 5 s for outstanding ACKs **after** the ASR drain, total, then end." "Stop during startup aborts
  the reservation without opening capture. Cancel invalidates before sending and aborts in-flight audio
  … Loss/disconnect first revokes delivery, then gracefully drains at most the already-in-flight
  utterance into recovery only; loss while starting aborts without capture. Shutdown/host failure clean
  up without promising a recoverable drain." "No drain waiting/child abort under that lock or on the
  recorder reader thread." "Terminal transition is idempotent even if Stop, loss, exit, and EOF race."
- `architecture/system_context.md` → "Control/recorder boundaries": "Native needs its own policy:
  Stop/idle allows only the in-flight utterance and up to 5 s total ACK settlement after bounded ASR
  drain; loss revokes immediately, recovery-only for at most that utterance; Cancel aborts without
  waiting on the reader; startup termination prevents late capture. `_safe_abort` must run off-lock and
  off-reader."
- Chain: T3.S4 supplies `NativeReservation` (`begin_drain`, `end_reason`, `end_evt`, exactly-once
  `on_end` via `_flush_native_end`), the `_native_clock` / `_native_timers` seams and
  `_stop_native_start`; T4.S2 supplies `OfferQueue.revoke` / `clear_pending` / `drain_pending` /
  `ack` / `check_deadline` (docstrings already say "T4.S5 stop/cancel"); T4.S3 supplies
  `host.capture_boundary` / `relay_event`; T4.S4 supplies the acceptance route
  (`_native_fence`, `_native_queue`, `_native_offer_evt`, `_native_on_final`, `_native_final_verdict`)
  and documents this task's extension seam. `generic graceful_stop cannot dictate native semantics`.

## What

### Success Criteria
- [ ] New daemon surface: `NATIVE_SETTLE_TIMEOUT_S`, `NativeEndFacts`, `native_stop`, `native_cancel`,
      `native_lost`, `native_settle_kick`, `_native_settle_step_locked`, `_native_mic_closed_locked`,
      `_begin_drain_locked`, `_arm_drain_watchdog`; state `_native_drain_boundary`,
      `_native_settle_deadline`, `_native_settle_timer`, `_native_end_facts`.
- [ ] (a)–(n) hold.
- [ ] Not in scope (owned elsewhere): the `finishing` / `ended` **frames** and desktop hints (T4.S6),
      `NativeRecovery.end_session` (T4.S6), any socket / `editor-start` / pump wiring (T4.S7),
      `voicectl recover` (T5), generic `cancel()`/HALT/Backspace behaviour, config keys.

## All Needed Context

### Context Completeness Check

_Pass._ The current body of every edited function, the lock/thread of each seam, the reservation and
queue semantics, the host abort/cancel rules, the fake-host/clock/timer harness names and a verbatim
test list are given below. The implementer needs this PRP, `research/lifecycle_seam_findings.md`,
`research/control_surface_and_tests.md`, and the named slices of `daemon.py`.

### Documentation & References

```yaml
- url: https://docs.python.org/3/library/threading.html#threading.Event.wait
  why: "set_event / end_evt semantics used by the settlement; never waited on under _lock"
  critical: "no code in this task calls Event.wait() at all — waiting is a timer handle + kicks"
- url: https://docs.python.org/3/library/threading.html#threading.Timer
  why: "the existing drain watchdog (_begin_drain) and ThreadTimers are Timer-based; cancel() is a flag, a late fire must be fenced by owner token"
  critical: "Timer.start()/cancel() never block on other threads — the ONLY calls of that kind allowed inside the _disarm lock hold"
- url: https://docs.python.org/3/library/time.html#time.monotonic
  why: "deadlines must use a monotonic clock; this repo's injectable seam is self._native_clock()"
  critical: "never mix time.time() into a deadline"

- docfile: plan/009_ef3b49b0fc0d/P1M1T4S5/research/lifecycle_seam_findings.md
  why: "seam map (symbol → line → thread/lock), verbatim queue/reservation semantics, harness names, the premature-idle-tag defect"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S5/research/control_surface_and_tests.md
  why: "ctl.py help lines + exit codes, test precedents (drain, cancel, auto-stop), G1 baseline rule"
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Control/recorder boundaries' paragraph 3 is this task's spec; 'Buffer ownership and recovery' gives the monotonic-clock / 5 s budget rule"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S4/PRP.md
  why: "CONTRACT — the route this task extends: 'Implementation Patterns & Key Details' → CONSUMER CONTRACT for T4.S5/S6/S7; 'Data models' for the _native_* state"
  critical: "T4.S4 may still be landing while you start: every line number below DRIFTS — anchor by symbol name"
- file: voice_typing/daemon.py
  why: "THE module edited. Read before editing: _request_stop, _disarm, _maybe_auto_stop, cancel, _begin_drain,
        _complete_drain, _drain_timeout, _safe_abort, run() text() block, _native_final_verdict, _native_on_final,
        _end_native_locked, terminate_native, begin_native_drain, _stop_native_start, request_shutdown, __init__ native state"
  pattern: "off-lock funnels: reserve_native (arm timers OUTSIDE the lock), terminate_native / _stop_native_start
            (lock → _end_native_locked → release → _flush_native_end); reader thread touches only _on_final_lock
            plus a short _lock around enqueue"
  gotcha: "_disarm runs UNDER _lock on the caller's thread; its tail today ends the native session immediately
           (T3.S4) — that is the line this task replaces"
- file: voice_typing/editor_session.py
  why: "Stage :71-78 (DRAINING comment: 'T4.S5 owns the policy'); EndRecord :90-98 (cause vocabulary);
        NativeReservation :106-165 (begin_drain :139, end_reason :123, terminate :147);
        OfferQueue ack :353, check_deadline :385, revoke :397, clear_pending :410, drain_pending :418, close :423"
  pattern: "revoke is sticky, first reason wins; clear_pending drops UNATTEMPTED finals only; drain_pending is
            the 'let the in-flight offer finish' check"
  gotcha: "OfferQueue takes no lock internally — every mutation under d._lock. DOCSTRING EDITS ONLY in this task."
- file: voice_typing/editor_protocol.py
  why: "END_REASONS :144, START_CAP_S :398, ThreadTimers (production timer seam), LossCause vocabulary"
- file: voice_typing/recorder_host.py
  why: "_CaptureBoundary(host_generation, arm_seq, session_gen, utterance_id) :1473; capture_boundary property :430
        ('may be superseded by <=1 event off the reader thread'); RecorderHost.cancel() :630 ('sets _cancel_event
        AND THEN _abort_event … buffered audio is DISCARDED … sentinel emitted MARKED'); abort() :617"
  gotcha: "READ ONLY. abort()/cancel() block unless a thread is inside text() — the _safe_abort gate (:2744-2766).
           The boundary's close-order relative to the on_final dispatch is NOT verified — hence snapshot-at-stop."
- file: voice_typing/ctl.py
  why: "help text :21 (stop), :25 (cancel); _build_parser; exit codes 0/1/2/64"
- file: tests/test_editor_session.py
  why: "HARNESS PRECEDENT: `import test_daemon as td` (:7); FakeClock (:13) now()/advance(); ManualTimers (:19)
        armed/fired/cancelled + arm(deadline, fire)/cancel(h)/fire(h); `d._native_clock, d._native_timers = fc.now, mt`
        set right after _make_daemon (:62); _Ends on_end collector (:66); reserve→commit→_arm(native=True) flow"
- file: tests/test_daemon.py
  why: "_FakeHost (~:788): records mic, aborts, text_calls, cancel_calls; _make_daemon → (d, fb, rec, be);
        precedents :1059 (d._begin_drain(); d._drain_timeout(); assert rec.aborts == 1), :1003-1034, :1196-1240. Do NOT edit."
- file: tests/test_editor_offer_queue.py
  why: "copy the exact {'cmd':'applied','id':…,'seq':…} dict the ack tests use; Clock class"
- file: tests/G1_BASELINE.md
  why: "set-diff rule for tests/test_daemon.py (20 legacy reds)"
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py             # 4491 lines; seams listed in research/lifecycle_seam_findings.md   ← EDIT
voice_typing/editor_session.py     # Stage / NativeReservation / OfferQueue                             ← DOCSTRINGS ONLY
voice_typing/ctl.py                # voicectl CLI                                                       ← HELP TEXT ONLY
voice_typing/recorder_host.py      # capture_boundary, cancel(), abort()                                 READ ONLY
voice_typing/editor_protocol.py    # END_REASONS, ThreadTimers                                          READ ONLY
voice_typing/session_recovery.py   # NativeRecovery (end_session is T4.S6)                              READ ONLY
tests/test_daemon.py               # harness + G1 baseline                                              do NOT edit
tests/test_native_lifecycle.py                                                                         ← CREATE
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/daemon.py
  + NATIVE_SETTLE_TIMEOUT_S = 5.0                     (next to _DRAIN_TIMEOUT_S)
  + @dataclass(frozen=True) class NativeEndFacts      reason, revoked, recoverable — transcript-free, for T4.S6
  + __init__: _native_drain_boundary, _native_settle_deadline, _native_settle_timer, _native_end_facts
  + native_stop(reason="stopped", *, token=None) -> EndRecord | None      THE graceful funnel
  + native_cancel(*, token=None) -> EndRecord | None
  + native_lost(reason, cause=None, *, token=None) -> EndRecord | None
  + native_settle_kick(*, token=None) -> EndRecord | None                one settlement step (pump + watchdog)
  + _native_settle_step_locked(now) -> EndRecord | None
  + _native_mic_closed_locked() -> None                                 _disarm tail for a native owner
  + _begin_drain_locked() -> bool ; _arm_drain_watchdog() -> None       split out of _begin_drain
  ~ _end_native_locked      → THE terminal action (facts + settle-timer retire, then T4.S4 body)
  ~ _native_final_verdict   → DRAINING rule (verdict "drain")
  ~ _request_stop, _maybe_auto_stop, _disarm tail
  ~ docstrings: _request_stop, _disarm, _maybe_auto_stop, cancel, _begin_drain, _complete_drain, _drain_timeout
voice_typing/editor_session.py   ~ docstrings: Stage.DRAINING, EndRecord.cause, revoke/clear_pending/drain_pending
voice_typing/ctl.py              ~ help: stop (:21), cancel (:25)
tests/test_native_lifecycle.py   — (a)–(l)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — NO WAITING UNDER _lock OR ON THE READER. host.abort(), host.cancel() and any settlement wait run
# off-lock. Inside _disarm's lock hold the ONLY new calls are attribute stores, queue queries and
# self._native_timers.arm(...) (Timer construction/start — same class of call T3.S4 allows for cancel()).
# CRITICAL #2 — _disarm IS CALLED UNDER _lock. Never make it abort/cancel; never release the lock inside it.
# Its native tail must not END a DRAINING session straight away any more — it starts/finishes settlement.
# CRITICAL #3 — _native_drain_boundary IS THE LOCK-FREE "DRAINING" SENTINEL on the reader thread (a NamedTuple
# reference: None during LISTENING, set under _lock at native_stop/native_lost BEFORE anything else). Do not read
# self._native.stage on the reader (it is guarded by _lock).
# CRITICAL #4 — THE DRAIN SNAPSHOT IS TAKEN AT STOP TIME on the control/pump thread (whole value of
# host.capture_boundary). Inside on_final the boundary may already be closed by the relay, so never compare ev
# against host.capture_boundary read in the callback (T4.S4's wording) — compare against the snapshot.
# CRITICAL #5 — host.abort()/cancel() BLOCK FOREVER unless a thread is inside text(): gate on
# self._text_in_flight.is_set() exactly like _safe_abort (:2767). host.cancel() calls abort() internally.
# CRITICAL #6 — _begin_drain TAKES _lock ITSELF. Calling it from a lock-holding path deadlocks. Use
# _begin_drain_locked() inside the hold, _arm_drain_watchdog() after release.
# CRITICAL #7 — THE IDLE TAG TODAY FIRES BEFORE THE IDLE CHECK (_maybe_auto_stop: `self._native_drain_or_stop("idle")`
# is the first statement). With the DRAINING verdict in place that would reject every later final of a
# still-talking session. Move the tag under the lock, after the threshold check.
# CRITICAL #8 — OFFERQUEUE IS NOT THREAD-SAFE BY DESIGN: revoke/clear_pending/drain_pending/ack only under d._lock.
# Do NOT call q.close() yourself — T4.S4's _native_close_capture_locked (inside _end_native_locked) does it, and
# T4.S6 needs drain_pending() BEFORE that: read the facts in _end_native_locked ahead of the T4.S4 hook.
# CRITICAL #9 — LATE TIMER FIRE: Timer.cancel() is only a flag. Every watchdog callback is fenced by owner token
# (precedent: _native_start_expired(tok)). A settle fire for a previous owner must be a no-op.
# CRITICAL #10 — _complete_drain IS RUN-LOOP ONLY (main thread, after text() returns). Do not call it from
# control paths; in tests call it directly to simulate "text() returned".
# CRITICAL #11 — LOGS: codes/counts/ids only. Never text, seed, or a ProtocolError detail.
# CRITICAL #12 — AGENTS.md: every command under `timeout` with the bash-tool timeout above it; .venv/bin/python;
# tests/test_daemon.py = `timeout 500 … --tb=no` with bash timeout >= 560; never run the daemon or voicectl.
# CRITICAL #13 — DO NOT EDIT recorder_host.py, editor_protocol.py, session_recovery.py, tests/test_daemon.py,
# tests/test_editor_session.py, tests/test_editor_offer_queue.py, any plan file, PRD.md, tasks.json, README.md.
# Do not implement T4.S6 (frames, hints, end_session) or T4.S7 (socket/pump).
```

## Implementation Blueprint

### Data models and structure

```python
# module level, next to _DRAIN_TIMEOUT_S (:243)
NATIVE_SETTLE_TIMEOUT_S: float = 5.0   # §4.8.1 B: TOTAL post-drain ACK settlement budget (code constant)
_STOP_REASONS = frozenset({"stopped", "idle"})                    # native_stop
_LOSS_REASONS = frozenset({"target_lost", "disconnected", "timeout"})  # native_lost (lease expiry = "timeout")

@dataclasses.dataclass(frozen=True)
class NativeEndFacts:
    """Transcript-free facts stashed by _end_native_locked for T4.S6 (the `ended` frame + hints)."""
    reason: str            # EndRecord.reason actually recorded
    revoked: str | None    # OfferQueue.revocation_reason at end (None = delivery was never revoked)
    recoverable: bool      # OfferQueue.drain_pending() at end: some accepted final is not known applied

# __init__ — after self._native_end_delivered = False
self._native_drain_boundary = None       # whole-value snapshot of host.capture_boundary at graceful stop (reader sentinel)
self._native_settle_deadline: float | None = None   # self._native_clock() + NATIVE_SETTLE_TIMEOUT_S; None = not settling
self._native_settle_timer = None         # self._native_timers handle (same seam/handling as self._native_timer)
self._native_end_facts: NativeEndFacts | None = None
```

```python
# THE TERMINAL ACTION — _end_native_locked (T4.S4 body, extended; still idempotent, still under _lock)
def _end_native_locked(self, reason, cause, *, now=None):
    r = self._native
    if r is None or not r.live:
        return None
    rec = r.terminate(reason, cause, now=self._native_clock() if now is None else now)
    # P1.M1.T4.S5: stash facts BEFORE T4.S4's hook drops the queue; retire the settlement watchdog
    q = self._native_queue
    self._native_end_facts = NativeEndFacts(
        reason=rec.reason,
        revoked=q.revocation_reason if q is not None else None,
        recoverable=q.drain_pending() if q is not None else False,
    )
    handle, self._native_settle_timer = self._native_settle_timer, None
    if handle is not None:
        self._native_timers.cancel(handle)
    self._native_settle_deadline = None
    self._native_drain_boundary = None
    # ...existing T4.S4 lines unchanged: _native_close_capture_locked(), _native_timer cancel, r.end_evt.set(), log
    return rec
```

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only, bounded; record answers in the commit message or a scratch note, not in /tmp loops):
  git log --oneline -1; git status --short | head            # is T4.S4 committed? tests/test_native_final_route.py present?
  grep -nE "def (_request_stop|_disarm|_maybe_auto_stop|cancel|_begin_drain|_complete_drain|_drain_timeout|_safe_abort|
            _native_final_verdict|_native_on_final|_end_native_locked|terminate_native|begin_native_drain|
            _native_drain_or_stop|_stop_native_start|request_shutdown|run)\b" voice_typing/daemon.py
  grep -nE "_native_drain_or_stop\(|_end_native_locked\(|_native_fence|_native_offer_evt|import dataclasses|^from dataclasses" voice_typing/daemon.py
  sed -n '<_end_native_locked range>p;<_disarm tail range>p;<_request_stop range>p;<_maybe_auto_stop range>p' voice_typing/daemon.py
  grep -n "class ThreadTimers" -A 22 voice_typing/editor_protocol.py      # arm() must only construct+start a Timer
  grep -rn "LossCause" voice_typing/ | head -5                             # loss-cause vocabulary T4.S7 passes
  grep -n '"applied"' tests/test_editor_offer_queue.py | head -3           # copy the exact ACK dict shape
  grep -rnE "disarm the mic|drop the pending dictation" tests/             # any help-text assertion to update
  grep -c "Lock()" voice_typing/daemon.py                                  # record N — must equal N after the edit
  baseline: timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40   # bash timeout >= 560
  timeout 300 .venv/bin/python -m pytest tests/test_editor_session.py tests/test_editor_offer_queue.py -q   # must be green BEFORE you start

Task 1: CREATE tests/test_native_lifecycle.py (RED first). CPU-only; no threads, sockets or subprocess started by a test;
        hermetic_cfg/XDG via the test_daemon harness; nothing written under /tmp.
  HARNESS:
  - `import test_daemon as td` (precedent tests/test_editor_session.py:7); FakeClock + ManualTimers copied verbatim
    from tests/test_editor_session.py:13-27; set `d._native_clock, d._native_timers = fc.now, mt` right after
    `td._make_daemon(...)`.
  - SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"
  - class _BHost(td._FakeHost): generation = 3; arm_seq = 0; relay_event = None; capture_boundary = None;
      set_microphone(self, on): if on: self.arm_seq += 1;  super().set_microphone(on)
  - def _ev(uid, gen=1, host_gen=3, arm=1, cls=FinalClass.ACCEPTED): return _RelayEvent("final", cls, host_gen, arm, gen, uid)
  - def _listening_native(d, host, ends): d._host = host; res = d.reserve_native(None, SID, on_end=ends);
      assert res.accepted; with d._lock: assert d._native.commit(res.owner.token); d._arm(native=True);
      assert d._native.stage is Stage.LISTENING and d._native_fence == (3, 1)
  - def _in_flight(d, host, uid): host.capture_boundary = _CaptureBoundary(3, 1, 1, uid); d._text_in_flight.set()
  - def _text_returned(d): d._text_in_flight.clear(); d._complete_drain()      # what run() does when _drain is set
  - tripwire backend: subclass of td._FakeBackend whose type_text/press_backspace raise (pytest.fail on fire)
  - def _lock_free(host, name): wrap host.<name> so it asserts `not d._lock.locked()` when called
  TESTS (names fixed):
  - test_stop_without_utterance_in_flight_ends_promptly            (b): ENDED, reason "stopped", cause None; mic off;
      _listening clear; ends.records == [rec]; _native_fence None; _drain False; host.aborts == 0; cancel_calls == 0;
      mt.armed unchanged (no settle timer); d._native_end_facts == NativeEndFacts("stopped", None, False)
  - test_stop_with_utterance_in_flight_drains_then_settles          (a)(c): after native_stop → stage DRAINING,
      drain_reason "stopped", _drain True, _native_offer_evt.is_set(), mic still on, _listening set, ends empty;
      host.relay_event = _ev(7); d.on_final("hello world") → pending_count == 1, counts()[0] == 1, _final_pending False;
      _text_returned(d) → mic off, _native_settle_deadline == fc.now + 5.0, len(mt.armed) == 1 (deadline recorded),
      still DRAINING; pump: with d._lock: att = q.begin_offer(fc.now); q.ack(<applied dict seq=1>, fc.now) → SETTLED;
      d.native_settle_kick() → ENDED "stopped", handle in mt.cancelled, facts.recoverable False, ends length 1
  - test_drain_final_of_another_utterance_is_rejected             boundary uid 7, final uid 8 → counts()[0] == 0,
      _native_rejects["drain"] == 1, _final_pending False, nothing typed
  - test_drain_timeout_aborts_then_ends_with_stop_reason         in flight → native_stop → d._drain_timeout() →
      host.aborts == 1; _text_returned(d) → ENDED "stopped"; no settle timer armed
  - test_native_stop_drains_regardless_of_graceful_stop          parametrize graceful_stop False/True → _drain True
  - test_stop_is_idempotent_and_first_reason_wins                 native_stop("stopped") then ("idle") → None,
      drain_reason "stopped"; after ENDED a third call → None; ends length 1
  - test_idle_auto_stop_routes_only_when_actually_idle           (g): _last_speech_monotonic = time.monotonic() - 999 →
      _maybe_auto_stop() → ENDED "idle"; fresh session with _last_speech_monotonic = time.monotonic() → still LISTENING
  - test_generic_voicectl_stop_drains_a_native_session           in flight; d.stop() → DRAINING, _drain True, backend silent
  - test_settlement_deadline_ends_timeout                        pending un-offered final at drain end; fc.advance(5.0);
      mt.fire(<settle handle>) → ENDED "timeout", facts == ("timeout", "timeout", True), queue revoked
  - test_settlement_ends_early_on_delivery_failed                pending final; with d._lock: q.ack(<applied seq=99>) →
      REVOKED; d.native_settle_kick() → ENDED "delivery_failed"; handle cancelled
  - test_cancel_revokes_aborts_and_never_drains                  (e): in flight + 1 queued final → native_cancel() →
      ENDED "cancelled" cause "cancel"; q.revoked, revocation_reason "cancelled", pending_count == 0; mic off;
      ends length 1; cancel_calls == 1 (asserted AFTER return — it happens off-lock); _drain False; late final with
      matching identity → counts unchanged, backend silent
  - test_cancel_without_text_in_flight_never_touches_the_host    cancel_calls == 0, aborts == 0
  - test_lost_revokes_first_then_drains_recovery_only            (f): in flight uid 7 → native_lost("disconnected") →
      DRAINING, drain_reason "disconnected", q.revocation_reason "disconnected", _drain True; final uid 7 →
      pending_count 0, counts()[0] == 1, offer_evt NOT set; _text_returned(d) → ENDED "disconnected", no settle timer
  - test_lost_without_utterance_ends_immediately                  ENDED "disconnected" from the call itself
  - test_lost_while_starting_aborts_without_capture               reserve only → native_lost("target_lost") → ENDED
      "target_lost"; d.begin_native_start(token) is False; d._native_blockers_locked() is False
  - test_loss_during_settlement_ends_at_once                     settling → native_lost("disconnected") → ENDED, handle cancelled
  - test_shutdown_and_host_death_end_without_settlement          settling → terminate_native("shutdown", cause="shutdown")
      → ENDED "shutdown", handle cancelled; fresh settling session → terminate_native("disconnected", cause="host-died")
  - test_abort_and_cancel_never_run_under_the_lock               _lock_free(host, "abort"/"cancel") on stop-timeout,
      cancel, lost paths; threading.active_count() unchanged by cancel / lost / settle-kick
  - test_settle_kick_with_stale_token_is_a_noop                  session A ended; session B settling; kick(token=A) → B still DRAINING
  - test_generic_paths_unchanged_without_a_native_owner         no reservation: graceful_stop=True + in flight +
      _final_pending → _request_stop() sets _drain; graceful_stop=False → immediate disarm + abort; _maybe_auto_stop
      disarms; cancel() ok (mirror test_daemon.py:1003-1034 assertions — do not import its test functions)
  - test_logs_and_end_record_carry_no_text                       caplog lacks "hello world"; EndRecord fields are codes
  - test_ctl_help_distinguishes_native_behaviour                 parser = ctl._build_parser(); "native" in the stop and
      cancel help; "busy" in the cancel help
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_lifecycle.py -q   → RED (bash timeout 360)

Task 2: EDIT daemon.py — constants, NativeEndFacts, __init__ state (Blueprint "Data models").

Task 3: EDIT daemon.py — split _begin_drain (behaviour identical for generic callers):
    def _begin_drain(self):
        if not self._begin_drain_locked(): return          # already draining (hotkey re-press)
        self._arm_drain_watchdog()
    def _begin_drain_locked(self) -> bool:                 # caller holds _lock
        if self._drain: return False
        self._drain = True; return True
    def _arm_drain_watchdog(self) -> None:                 # caller must NOT hold _lock
        self._drain_timer = threading.Timer(_DRAIN_TIMEOUT_S, self._drain_timeout)
        self._drain_timer.daemon = True; self._drain_timer.start()
        logger.info("voice-typing drain: letting the final model finish the utterance before stop")
  (keep the original _begin_drain docstring on _begin_drain).

Task 4: EDIT daemon.py — _end_native_locked = THE terminal action (Blueprint), and the DRAINING rule in
        _native_final_verdict — insert AFTER the existing fence check and BEFORE `return "ok"`:
    if self._native_drain_boundary is not None:            # P1.M1.T4.S5: DRAINING — only the utterance in flight at stop
        b = self._native_drain_boundary
        if b.utterance_id is None or (ev.host_generation, ev.arm_seq, ev.session_gen, ev.utterance_id) != tuple(b):
            return "drain"
    return "ok"
  (replace T4.S4's "EXTENSION SEAM (documented, NOT implemented here)" comment with the rule's description).

Task 5: EDIT daemon.py — the policy (place after _stop_native_start, ~:3291):
  a) native_stop(self, reason="stopped", *, token=None) -> EndRecord | None        # NO _lock on entry; never waits
         if reason not in _STOP_REASONS: raise ValueError("unknown stop reason")
         timer_due = abort = flush = False; rec = None
         with self._lock:
             r = self._native
             if r is None or not r.live or (token is not None and r.owner.token != token): return None
             if r.stage is Stage.STARTING:
                 rec = self._end_native_locked(reason, "stop-during-start"); flush = True   # §4.8.1 B
             elif r.stage is Stage.LISTENING:
                 r.begin_drain(reason)
                 self._native_offer_evt.set()                 # wake the pump: it emits `finishing` before any offer
                 host = self._host
                 b = host.capture_boundary if host is not None else None
                 self._native_drain_boundary = b              # reader sentinel + the ONE utterance that may land
                 if self._text_in_flight.is_set() and b is not None and b.utterance_id is not None:
                     timer_due = self._begin_drain_locked()   # bounded ASR drain; run() completes it in _complete_drain
                 else:
                     self._disarm(); abort = True             # nothing in flight: mic off NOW; its tail ends/settles
             else:
                 return None                                  # DRAINING: already winding down — first reason wins
         if timer_due: self._arm_drain_watchdog()
         if flush: self._flush_native_end()
         if abort: self._safe_abort()
         return rec
  b) _native_mic_closed_locked(self) -> None               # called ONLY from _disarm's tail, under _lock; never waits
         r = self._native
         if r is None or not r.live: return
         q = self._native_queue
         if q is not None and q.revoked:                    # loss/cancel/pump already revoked → nothing can settle
             self._end_native_locked(q.revocation_reason, None); return
         if q is None or not q.drain_pending():             # fully settled (or nothing ever queued) → prompt `ended`
             self._end_native_locked(r.end_reason, None); return
         now = self._native_clock()                         # DRAINING with unsettled work: start the 5 s budget
         self._native_settle_deadline = now + NATIVE_SETTLE_TIMEOUT_S
         tok = r.owner.token
         self._native_settle_timer = self._native_timers.arm(
             self._native_settle_deadline, lambda tok=tok: self.native_settle_kick(token=tok))
         logger.info("voice-typing native: settling offers token=%d budget=%.0fs pending=%d",
                     tok, NATIVE_SETTLE_TIMEOUT_S, q.pending_count)
  c) _native_settle_step_locked(self, now) -> EndRecord | None
         r = self._native
         if r is None or r.stage is not Stage.DRAINING or self._native_settle_deadline is None: return None
         q = self._native_queue
         if q is not None and q.revoked: reason, cause = q.revocation_reason, None
         elif q is None or not q.drain_pending(): reason, cause = r.end_reason, None
         elif now >= self._native_settle_deadline:
             q.revoke("timeout"); reason, cause = "timeout", "settle-timeout"     # budget spent, work unsettled
         else: return None
         return self._end_native_locked(reason, cause, now=now)
  d) native_settle_kick(self, *, token=None) -> EndRecord | None     # pump after every ack/check_deadline; watchdog fire
         with self._lock:
             r = self._native
             if token is not None and (r is None or r.owner.token != token): return None   # late fire fence
             rec = self._native_settle_step_locked(self._native_clock())
         self._flush_native_end()
         return rec
  e) native_cancel(self, *, token=None) -> EndRecord | None         # invalidate FIRST, then abort; never drains
         rec = None
         with self._lock:
             r = self._native
             if r is None or not r.live or (token is not None and r.owner.token != token): return None
             q = self._native_queue
             if q is not None: q.revoke("cancelled"); q.clear_pending()
             rec = self._end_native_locked("cancelled", "cancel")    # token tombstoned; T4.S4 hook closes queue + fence
             if self._listening.is_set(): self._disarm()             # mic off in the SAME hold (tail is now a no-op)
         self._flush_native_end()
         host = self._host                                    # off-lock: discard the utterance's audio + unblock text()
         if host is not None and self._text_in_flight.is_set():
             try: host.cancel()
             except Exception: logger.exception("host.cancel() raised (best-effort; ignored)")
         return rec
  f) native_lost(self, reason, cause=None, *, token=None) -> EndRecord | None
         if reason not in _LOSS_REASONS: raise ValueError("unknown loss reason")
         timer_due = abort = flush = False; rec = None
         with self._lock:
             r = self._native
             if r is None or not r.live or (token is not None and r.owner.token != token): return None
             q = self._native_queue
             if q is not None: q.revoke(reason); q.clear_pending()   # revoke delivery FIRST
             if r.stage is Stage.STARTING or r.stage is Stage.DRAINING:
                 rec = self._end_native_locked(reason, cause); flush = True   # no capture / no settlement wait
             else:
                 r.begin_drain(reason)                              # LISTENING: recovery-only drain of the in-flight utterance
                 host = self._host
                 b = host.capture_boundary if host is not None else None
                 self._native_drain_boundary = b
                 if self._text_in_flight.is_set() and b is not None and b.utterance_id is not None:
                     timer_due = self._begin_drain_locked()
                 else:
                     self._disarm(); abort = True
         if timer_due: self._arm_drain_watchdog()
         if flush: self._flush_native_end()
         if abort: self._safe_abort()
         return rec

Task 6: EDIT daemon.py — routing (keep every generic line byte-identical apart from the stated changes):
  a) _disarm tail — replace the two T3.S4 lines (`if self._native_owner_live_locked():
     self._end_native_locked(self._native.end_reason, None)`) with:
         if self._native_owner_live_locked():
             self._native_mic_closed_locked()      # P1.M1.T4.S5: DRAINING settles (bounded, off-lock); else ends here
  b) _request_stop — DELETE the first statement `self._native_drain_or_stop("stopped")`; insert BEFORE the
     `if (self._cfg.asr.graceful_stop …` expression:
         with self._lock:
             r = self._native
             native_stage = r.stage if (r is not None and r.live) else None
         if native_stage is Stage.LISTENING:       # P1.M1.T4.S5: native stop ALWAYS drains the in-flight utterance
             self.native_stop("stopped"); return
         if native_stage is Stage.STARTING and self._stop_native_start(): return
         if native_stage is not None: return        # DRAINING: idempotent
     (generic branch below untouched: it no longer needs the tag because no native owner reaches it.)
  c) _maybe_auto_stop — DELETE `self._native_drain_or_stop("idle")`; add `native_idle = False` before the lock;
     inside the lock AFTER both early `return`s and BEFORE the generic log line:
         if self._native_owner_live_locked(): native_idle = True
         else:  <the existing log + self._disarm(); disarmed = True>
     after the lock: `if native_idle: self.native_stop("idle"); return`  (then the existing `if disarmed … _safe_abort()`).
  d) request_shutdown / shutdown() / _handle_dead_host: NO change (terminate_native → _end_native_locked ends a
     settling session at once). begin_native_drain / _native_drain_or_stop: keep (now unreferenced by the edited
     paths — leave them; tests/test_editor_session.py may still use them).

Task 7: EDIT docstrings [Mode A].
  - daemon.py: _request_stop ("NATIVE (P1.M1.T4.S5): a LISTENING native owner is routed to native_stop — always
    drains the in-flight utterance, independent of asr.graceful_stop; STARTING → _stop_native_start; DRAINING → no-op"),
    _disarm (tail description), _maybe_auto_stop (tag only when idle; native routes to native_stop("idle")),
    cancel ("while a native owner holds the mic: busy, no side effects — the owner's cancel is native_cancel"),
    _begin_drain/_complete_drain/_drain_timeout (one line each: also the native bounded ASR drain; a timeout
    loses the in-flight utterance — never recoverable, the end reason is unchanged), native_* docstrings quoting
    the table from the Goal section.
  - editor_session.py (DOCSTRINGS ONLY): Stage.DRAINING comment → "stop/idle/lost wind-down (finishing):
    P1.M1.T4.S5 — at most the in-flight utterance drains, then ≤ NATIVE_SETTLE_TIMEOUT_S of ACK settlement";
    EndRecord.cause vocabulary += "cancel" | "settle-timeout"; OfferQueue.revoke/clear_pending/drain_pending
    docstrings: replace "T4.S5" forward references with the actual caller (native_cancel / native_lost /
    _native_mic_closed_locked).
  - ctl.py help (:21, :25) — keep the leading verb text, append after a semicolon:
      stop     disarm the mic (stop listening); on a native editor session: emergency graceful stop (finishes
               the in-flight utterance, then ends the session)
      cancel   drop the pending dictation fragment and keep listening (Backspace keybind fallback); busy while
               a native editor session owns the mic - use the editor's Cancel
    If Task 0 found a test pinning the old strings, update that assertion (list the file in the diff check).

Task 8: VERIFY: Task-1 file green; Task-0 suites green; tests/test_daemon.py FAILED set == baseline (set-diff).
Task 9: VALIDATE L1–L4. Commit only if the orchestrator directs.
```

### Implementation Patterns & Key Details

```python
# PATTERN — every funnel is: one lock hold that only decides + stores, then off-lock side effects.
with self._lock:
    ... begin_drain / snapshot boundary / _begin_drain_locked or _disarm ...
if timer_due: self._arm_drain_watchdog()      # Timer start off-lock
if flush:     self._flush_native_end()        # on_end off-lock (T3.S4 exactly-once)
if abort:     self._safe_abort()              # host.abort() off-lock, gated on _text_in_flight

# GOTCHA — order inside native_cancel is the PRD's "invalidate before sending": revoke → clear_pending →
#          _end_native_locked (tombstone, close queue, clear fence) → _disarm → [off-lock] host.cancel().
# GOTCHA — a loss drain final goes through the normal route: verdict "ok" (matches the snapshot) → cleaned →
#          retained → enqueue returns REVOKED → _native_offer_evt is NOT set (T4.S4 sets it only for QUEUED).
# GOTCHA — _disarm for an already-ended owner is a no-op tail: _native_owner_live_locked() is False.

HANDOFF — CONSUMER CONTRACT (put it verbatim in the native_stop / native_settle_kick docstrings):
  T4.S7 (owner-connection pump), all with owner token:
    owner "stop"   → d.native_stop("stopped", token=tok)
    owner "cancel" → d.native_cancel(token=tok)
    owner "lost" / local invalidation → d.native_lost("target_lost", <LossCause>, token=tok)
    transport EOF / write failure        → d.native_lost("disconnected", <LossCause>, token=tok)
    lease expiry (6 s without valid ping) → d.native_lost("timeout", "lease-expired", token=tok)
    after EVERY d._lock-guarded q.ack(...) / q.check_deadline(...) → d.native_settle_kick() (off-lock); without the
      kick `ended` still arrives, but only at the 5 s deadline.
    d._native_offer_evt is ALSO set on LISTENING→DRAINING: on wake, under d._lock, if stage is DRAINING emit
      {"event":"finishing","id":…} ONCE before any begin_offer (PRD: ordered before any final of the drain).
      While DRAINING the queue stays open and unrevoked for stop/idle — keep offering pending finals.
  T4.S6 (ended frame + hints): read d._native_end_facts (reason, revoked, recoverable) when on_end fires;
    recoverable == q.drain_pending() at end (the queue itself is already closed and detached); then call
    d._native_recovery.end_session(sid, reason).
```

### Integration Points

```yaml
STATE:
  - add to: voice_typing/daemon.py __init__ (after _native_end_delivered)
  - pattern: "_native_drain_boundary | _native_settle_deadline | _native_settle_timer | _native_end_facts"
ARM:
  - unchanged: _arm(native=True) / _native_open_capture_locked (T4.S4); _stop_native_start (T3.S4)
END:
  - edit: _end_native_locked is the single terminal action (facts + settle-timer retire + T4.S4 hook)
DRAIN:
  - edit: _begin_drain → _begin_drain_locked + _arm_drain_watchdog (identical generic behaviour)
NO CHANGES: config, state.json shape, status fields, ControlServer handlers/replies, recorder_host.py,
editor_protocol.py, session_recovery.py, media ducking, idle unload, generic cancel(), run() loop body.
```

## Validation Loop

### Level 1: Syntax & Style
```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/editor_session.py voice_typing/ctl.py tests/test_native_lifecycle.py && echo "L1 PASS"
grep -c "Lock()" voice_typing/daemon.py        # == Task-0 count N (no new lock)
grep -nE "def (native_stop|native_cancel|native_lost|native_settle_kick|_native_settle_step_locked|_native_mic_closed_locked|_begin_drain_locked|_arm_drain_watchdog)\b" voice_typing/daemon.py   # 8 hits
grep -n "_native_drain_or_stop(" voice_typing/daemon.py | wc -l      # only its own definition (callers removed)
.venv/bin/ruff check voice_typing/daemon.py tests/test_native_lifecycle.py 2>&1 | tail -3   # only if ruff is configured
```

### Level 2: Unit Tests
```bash
PY=.venv/bin/python
timeout 300 "$PY" -m pytest tests/test_native_lifecycle.py -q                                        # bash timeout 360
timeout 300 "$PY" -m pytest tests/test_editor_session.py tests/test_editor_offer_queue.py tests/test_native_recovery.py -q 2>&1 | tail -2
timeout 300 "$PY" -m pytest tests/test_native_final_route.py -q 2>&1 | tail -2                        # T4.S4 suite, if present
timeout 500 "$PY" -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40                            # bash timeout >= 560
# Set-diff rule (tests/G1_BASELINE.md): FAILED set == Task-0 baseline — no new reds, no blanket skips.
# A 124 means wedged: do NOT retry — AGENTS.md "Cleanup".
```

### Level 3: Scope & Integration
```bash
git diff --name-only      # == voice_typing/daemon.py voice_typing/editor_session.py voice_typing/ctl.py tests/test_native_lifecycle.py
git diff -- voice_typing/editor_session.py | grep -E "^[+-]" | grep -vE "^(\+\+\+|---)" | grep -vE '^[+-]\s*(#|"""|[A-Za-z`(].*)$' | head   # docstring-only: expect no code lines
git diff -- voice_typing/daemon.py | grep -E "^\+.*(subprocess|type_text\(|press_backspace\(|record_final\(|time\.sleep|\.wait\()" | wc -l   # expect 0
git diff -- voice_typing/daemon.py | grep -E "^\+.*(begin_offer|send_line|end_session\()" | wc -l   # expect 0 (T4.S6/T4.S7)
git diff -- voice_typing/daemon.py | grep -nE "^\+.*logger\.(info|debug|warning)\(" | wc -l      # small; each audited by the caplog test
```

### Level 4: Creative & Domain-Specific Validation
```bash
# Identity contract still hermetic and green with the real relay:
timeout 120 .venv/bin/python -m pytest tests/test_recorder_identity_boundary.py -q      # bash timeout 180
# Negative proof — no desktop/injection tool reachable from the new native policy:
grep -nE "wtype|ydotool|wl-copy|notify-send|hyprctl" voice_typing/daemon.py | grep -i "native" || echo "L4 PASS"
# No abort/cancel inside a lock hold in the new code (manual read of the three funnels + _native_mic_closed_locked):
grep -nE "host\.(abort|cancel)\(\)" voice_typing/daemon.py
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 pass; Success (a)–(n) hold; `tests/test_daemon.py` FAILED set == G1 baseline (set-diff, not count).
- [ ] No wait/abort/cancel/timer-join under `_lock` or on the reader thread; no new `Lock()`; no new thread
      beyond the existing drain watchdog `Timer`.
- [ ] `_native_fence is None and _native_drain_boundary is None` ⇒ every generic callback runs today's lines.

### Feature Validation
- [ ] Stop / `voicectl stop` / idle: DRAINING → ≤ in-flight utterance → ≤ 5 s settlement → `ended` once.
- [ ] Cancel: revoke → end → mic off → `host.cancel()` (in flight only); late final dropped.
- [ ] Loss: revoke first → recovery-only drain → immediate end; loss while STARTING ends without capture.
- [ ] Shutdown / host death end a settling session at once; watchdog handles always retired.
- [ ] Idle tag only when idle (regression test present).

### Code Quality Validation
- [ ] Helpers placed with the other native helpers; names exactly as specified; `_end_native_locked` is the
      only place a native session reaches ENDED.
- [ ] `editor_session.py` diff is docstrings only; `ctl.py` diff is the two help strings only.
- [ ] [Mode A] docstrings + the HANDOFF contract verbatim.

### Documentation & Deployment
- [ ] No new config keys or environment variables. Logs carry codes/counts/ids only.

---

## Anti-Patterns to Avoid

- ❌ Reusing the generic `graceful_stop` heuristic, `_final_pending`, or the `~5 s` generic cancel-suppression
      window to decide a native drain — the snapshot of `host.capture_boundary` decides.
- ❌ Reading `self._native.stage` or `host.capture_boundary` on the reader thread for the verdict — use the
      lock-free `_native_drain_boundary` snapshot.
- ❌ Ending the session inside `_disarm` before the queued offers had their settlement window.
- ❌ Starting a settlement thread or calling `Event.wait()` anywhere; waiting is a timer handle + pump kicks.
- ❌ Calling `_begin_drain()` (self-locking) from a lock-holding path; calling `host.abort()`/`cancel()` under
      `_lock` or without the `_text_in_flight` gate.
- ❌ Calling `q.close()` yourself, or letting T4.S6 lose `drain_pending()` by not stashing `NativeEndFacts`.
- ❌ Leaving the premature `idle` tag in `_maybe_auto_stop`.
- ❌ Letting a late settle-watchdog fire end the NEXT session (fence by owner token).
- ❌ Logging recognition/seed text; un-timed pytest; foregrounding the daemon; editing read-only files;
      implementing frames/hints/`end_session`/socket wiring (T4.S6/T4.S7).

### Post-research addendum (verified after first publication — informational; changes no Success Criterion)

- `recorder_host.py`: the only `_capture_boundary = None` reset (:852) is inside the reader's `_dispatch`
  (a relay-state reset block that also sets `_ready_evt`) — **not** in `abort()` / `cancel()` /
  `set_microphone()`. Every final path closes the boundary with `utterance_id=None` (:893, accepted path).
  So an abort/cancel clears the boundary only ASYNCHRONOUSLY, via the relayed sentinel final. A stale open
  boundary can be read at stop time only inside the "superseded by <= 1 event" window (the previous
  utterance's sentinel still in flight): worst case one bounded 5 s ASR-drain timeout, never a wrong
  acceptance — the DRAINING verdict still requires the 4-field match against the snapshot.
- Optional hardening (one comparison, no new state): treat the snapshot as open only when it belongs to
  the current arm — `(b.host_generation, b.arm_seq) == self._native_fence` — in the `in_flight` decision
  of `native_stop` / `native_lost`. If adopted, add
  `test_stop_ignores_a_stale_capture_boundary` (boundary with `arm_seq` 0 + text in flight → prompt ENDED).
- A late research child (timed out before writing its note) independently reported the same queue contract:
  revoke/close leave an outstanding offer and its `possibly_applied` recovery flag intact — consistent
  with `NativeEndFacts.recoverable = q.drain_pending()` being True for a revoked-but-outstanding queue.

## Confidence Score
**8/10** — every edited function was read in the working tree, the reservation/queue/host semantics are
quoted from source, the harness names are verified, and the test list is verbatim with a G1 set-diff gate.
Residuals, each pinned to Task 0: `ThreadTimers.arm` being non-blocking (it runs inside the `_disarm` lock
hold), the exact `applied` request dict for tests, the `LossCause` vocabulary T4.S7 passes as `cause`, the
boundary close-order inside the relay (the design does not depend on it), and line-number drift while
T4.S4 lands (anchor by symbol name).
