# P1.M1.T4.S5 — first-hand lifecycle seam findings (research lead)

Source: working tree of `/home/dustin/projects/voice-typing` at research time — HEAD `cc203ce`
**with P1.M1.T4.S4 partially applied** (`_arm(..., native=False)`, `_native_*` helpers already
present). Line numbers therefore DRIFT; the PRP anchors by symbol name. Re-grep before editing.

## Research status (evidence)

| child | agent | result |
|---|---|---|
| task-3 control surface + tests | nim-scout | done → `control_surface_and_tests.md` |
| task-4 PRD quotes + external | nim-general | **timed out at 30 min, 35-byte output, no file** |
| task-1 daemon lifecycle map | nim-research | **timed out at 45 min, no file**; steer not consumed |
| task-2 contract extraction | nim-research | **timed out at 45 min, no file**; steer not consumed; last preview matched the lead's findings |

The daemon/contract facts below were therefore verified directly by the research lead (bounded
`sed`/`grep` slices), not by the stalled children. PRD §4.8.1 B/C was read first-hand from
`plan/009_ef3b49b0fc0d/prd_snapshot.md:432-483`.

## daemon.py seam map (as read)

| symbol | line | thread / lock | load-bearing facts |
|---|---|---|---|
| `_DRAIN_TIMEOUT_S = 5.0` | :243 | const | bounded ASR drain watchdog |
| `_text_in_flight` | :888 | Event | set around `host.text()` in `run()` |
| `_native`, `_native_end_delivered` | :1014, :1022 | under `_lock` | reservation + exactly-once end delivery latch |
| `run()` | :1274 | main thread, no lock | :1352 `if self._drain: self._complete_drain()`; :1370-1378 `_utterance_finalized=False; _text_in_flight.set(); try: host.text(on_final) finally: _text_in_flight.clear()`; dead host → `_freeze_stranded_tail` + `_handle_dead_host()` :1344-1345 |
| `_handle_dead_host` | :1383 | main thread | :1440-1441 `terminate_native("load_failed" if starting else "disconnected", cause="host-died")` |
| `on_final` | :1481 | reader, `_on_final_lock` | `_listening` gate, then T4.S4 `if self._native_fence is not None: self._native_on_final(text); return` |
| `_arm(…, native=False)` | :1837 | control, `_lock` held | T4.S4 latches fence after `set_microphone(True)` |
| `_disarm` | :1940 | **caller holds `_lock`** | mic off, `_listening.clear()`, `_stop_seq += 1`, duck release, feedback idle; tail :1997-1998 `if self._native_owner_live_locked(): self._end_native_locked(self._native.end_reason, None)` ← ends the native session IMMEDIATELY on every disarm |
| `_request_stop` | :2074 | control thread | :2096 `self._native_drain_or_stop("stopped")` FIRST; then graceful only if `cfg.asr.graceful_stop and host and _text_in_flight and _final_pending` → `_begin_drain()`, else `with _lock: _disarm()` + `_safe_abort()` |
| `cancel()` | :2398 | control | native owner live → `{"ok":False,"busy":True,...}` no side effects (T3.S4); generic uses `host.cancel()` when `_text_in_flight` |
| `_begin_drain` | :2453 | takes `_lock` | `_drain=True` + `threading.Timer(_DRAIN_TIMEOUT_S, _drain_timeout)` |
| `_complete_drain` | :2467 | run loop | `_drain=False; _disarm(); timer.cancel()` |
| `_drain_timeout` | :2486 | Timer thread | if `_drain and host and _text_in_flight`: `_freeze_stranded_tail(...)` + `_safe_abort()` |
| `_maybe_auto_stop` | :2509 | watchdog | **`:2515 self._native_drain_or_stop("idle")` runs BEFORE the idle threshold check** → a native LISTENING owner is flipped to DRAINING/'idle' on the first tick even when not idle. Must move under the lock after the check. |
| `_safe_abort` | :2744 | any, **off-lock** | no-op unless `_text_in_flight`; `host.abort()`; never re-raises |
| `_start_fenced` | :2774 | worker | commits reservation + `_arm(native=…)` in one lock hold |
| `_native_owner_live_locked` | :2968 | `_lock` | `self._native is not None and self._native.live` |
| `_native_blockers_locked` | :2973 | `_lock` | `_arming is not None or _loading or _listening.is_set() or _drain` |
| `_native_open/close_capture_locked` | :2979 / :3017 | `_lock` | T4.S4: latch fence+queue / clear fence + `q.close()` |
| `_native_final_verdict` | :3028 | reader | codes `ok|missing|kind|class:<v>|fence|filtered|ended`; doc :3042-3044 = the T4.S5 EXTENSION SEAM |
| `_native_on_final` | :3073 | reader | doc :3084-3091 = CONSUMER CONTRACT handed to T4.S5/S6/S7 |
| `reserve_native` | :3140 | control | arms Start-cap timer OUTSIDE the lock via `self._native_timers.arm(deadline, lambda tok=…: self._native_start_expired(tok))` |
| `_end_native_locked` | :3215 | `_lock` | `r.terminate(...)` → `_native_close_capture_locked()` → cancel `_native_timer` → `r.end_evt.set()` → log. Idempotent. **The natural single terminal action.** |
| `_claim_native_end_locked` / `_flush_native_end` | :3236 / :3246 | off-lock flush | exactly-once `on_end` delivery |
| `terminate_native` | :3258 | no lock on entry | shutdown / host-died entry |
| `begin_native_drain` / `_native_drain_or_stop` | :3270 / :3278 | takes `_lock` | LISTENING→DRAINING, records `drain_reason` |
| `_stop_native_start` | :3282 | no lock on entry | STARTING → ended `stopped`/`stop-during-start` |
| `stop()` / `toggle()` | :3404 / :3412 | control | `stop`: `_stop_native_start()` then `_request_stop()`; `toggle` off path → `_request_stop()` :3432 |
| `request_shutdown` | :3436 | any | `terminate_native("shutdown", cause="shutdown")`; also :3760 in `shutdown()` |

## editor_session.py contracts (verbatim semantics)

- `Stage`: STARTING → LISTENING → DRAINING → ENDED; `ACTIVE_STAGES` includes DRAINING (so start/toggle/cancel stay `busy` during wind-down). Comment on DRAINING: "stop/idle/lost wind-down ('finishing'); T4.S5 owns the policy".
- `EndRecord(owner, stage, reason, cause, ended_at)` — `cause` vocabulary documented as `"start-cap" | "stop-during-start" | "host-died" | "shutdown" | a LossCause value | None`.
- `NativeReservation.begin_drain(reason)`: only from LISTENING, `reason in END_REASONS`, records `drain_reason`; `end_reason` = `drain_reason or "stopped"`; `terminate()` idempotent from any live stage; `end_evt` per reservation.
- `END_REASONS = frozenset(c.value for c in EndReason)` (`editor_protocol.py:144`); `START_CAP_S = 30.0` (`editor_protocol.py:398`); `ThreadTimers` is the production timer seam.
- `OfferQueue.ack(obj, now)` → `SETTLED | DUPLICATE | REVOKED | IGNORED` (malformed/foreign id/stale seq → sticky revoke `delivery_failed`); `check_deadline(now)` → revoke `timeout`; `revoke(reason)` sticky, first reason wins; `clear_pending()` drops UNATTEMPTED finals (outstanding stands, recovery untouched); `drain_pending()` = outstanding or pending; `close()` → later `enqueue` is CLOSED without retaining.

## recorder_host.py identity + abort facts

- `_CaptureBoundary(host_generation, arm_seq, session_gen, utterance_id)`; property `capture_boundary` "OPENS at the identified speech event; CLOSES (utterance_id → None) at every final path … off the reader thread it may be superseded by ≤1 event". Writes at :852, :893, :942, :965 (close-order relative to the `on_final` dispatch NOT verified → the design snapshots the boundary at Stop time instead of reading it inside the callback).
- `relay_event` valid only inside the callbacks; `_RelayEvent(kind, final_class, host_generation, arm_seq, session_gen, utterance_id)`.
- `RecorderHost.cancel()` (:630): sets `_cancel_event` THEN `abort()`; child discards the buffered audio, unblocks `text()`, emits the marked CANCELLED sentinel → exactly "abort in-flight audio". It calls `abort()`, so it carries the same "only while `text()` is in flight" rule as `_safe_abort` (see `_safe_abort` docstring :2744-2766: `abort()` blocks on `was_interrupted.wait()` set only inside `text()`).

## Test harness facts

- `tests/test_editor_session.py`: `import test_daemon as td`; `FakeClock(t=1000.0)` `.now()/.advance(s)`; `ManualTimers` `.armed/.fired/.cancelled`, `.arm(deadline, fire)`, `.cancel(h)`, `.fire(h)`; `_native_daemon(...)`; sets `d._native_clock, d._native_timers = fc.now, mt` right after `_make_daemon`; `_Ends` on_end collector.
- `tests/test_daemon.py`: `_FakeHost` (~:788) records `mic`, `aborts`, `text_calls`, `cancel_calls`; `set_microphone/abort/cancel/text`; `_make_daemon` → `(d, fb, rec, be)`. Precedents: `:1059 d._begin_drain(); d._drain_timeout(); assert rec.aborts == 1`; `:1003-1034` graceful_stop; `:1196-1240` auto-stop; `:4782-4822` cancel.
- `tests/test_ducking.py:271-276` imports fakers from `test_daemon` (cross-test-module import precedent).
- `tests/G1_BASELINE.md`: set-diff rule; 20 legacy reds.
- `ctl.py` help: `:21 stop     disarm the mic (stop listening)`; `:25 cancel   drop the pending dictation fragment and keep listening (Backspace keybind fallback)`.

## Open items left to Task 0 of the PRP

1. `ThreadTimers.arm` body (`editor_protocol.py` ~:398-430): confirm it only constructs + starts a `threading.Timer` (non-blocking), since the settlement watchdog is armed inside the `_disarm` lock hold.
2. The exact `{"cmd":"applied", …}` dict shape used by `tests/test_editor_offer_queue.py` (copy it for lifecycle tests).
3. `grep -rn LossCause voice_typing/` for the loss-cause vocabulary T4.S7 will pass as `cause`.
4. `grep -rn "disarm the mic\|drop the pending dictation" tests/` for help-text assertions.

## Update (workflow closed)

- Final workflow state: 1 completed (nim-scout), 3 failed by timeout (nim-general 30 min / 35-byte output;
  nim-research ×2 at 45 min / no file). No child left files outside `research/`.
- Verified afterwards: all four `_capture_boundary` writes live in the reader's `_dispatch` (:816). :852 is the
  relay-state reset (`_capture_boundary = None`, also sets `_ready_evt`); :893 closes the boundary with
  `utterance_id=None` on the accepted-final path. `abort()` / `cancel()` / `set_microphone()` do not reset it —
  it clears only via a relayed final path. The PRP carries this as a post-research addendum.
- At close, `tasks.json` showed this item `Researching → Implementing` and the working tree held edits to
  `voice_typing/daemon.py`, `voice_typing/editor_session.py`, `voice_typing/ctl.py` and a new
  `tests/test_native_lifecycle.py` — the implementer's, not the research lead's (which wrote only plan files).
