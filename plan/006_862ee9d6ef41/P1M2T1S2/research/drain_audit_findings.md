# Audit findings: graceful drain (P1.M2.T1.S2) — `gap_daemon_loop.md` §2 evidence

Audit of `voice_typing/daemon.py` **graceful-drain state machine** (`_request_stop` /
`_begin_drain` / `_complete_drain` / `_drain_timeout` / `_safe_abort` + the `run()` drain branch +
the `on_final` gate + `_final_pending`/`_text_in_flight` tracking) against **PRD §4.2 #2** (the
"Stop is graceful (drain)" contract) on the 6 item properties (a)-(f). This is the evidence the
implementing agent transcribes into the **§2 Graceful Drain** section appended to
`plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md` (which P1.M2.T1.S1 creates with the §1
main-loop audit).

**VERIFIED VERDICT: the graceful drain is PRD §4.2 #2 COMPLIANT on all 6 properties — no fix needed.**
Test baseline: `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'`
→ **29 passed, 164 deselected in 0.54s** (re-ran live).

---

## 0. The drain state machine (one-paragraph map)

`stop()` (daemon.py:1388→1391) and `toggle()`-off (1393→1410 normal / 1438 lite) BOTH route through
`_request_stop()` (1053). `_request_stop` branches on whether an utterance is **in flight**
(`self._host is not None and self._text_in_flight.is_set() and self._final_pending`, 1065):
- **in flight** → `_begin_drain()` (1073): sets `self._drain=True` (1078) + arms a
  `threading.Timer(_DRAIN_TIMEOUT_S=5.0, _drain_timeout)` (1079-1081). The run loop is still blocked
  in `text()`; when it returns (natural final via `on_final`, OR the watchdog's abort), the loop's
  TOP-OF-ITERATION `if self._drain: self._complete_drain(); continue` (850-854, checked BEFORE the
  `_listening` re-entry) disarms.
- **not in flight** → `with self._lock: self._disarm()` + `self._safe_abort()` (1067-1069): immediate
  disarm + abort (responsive when there's nothing to wait for).
`_complete_drain()` (1084): clears `_drain` (1096), `_disarm()` (1097), cancels the watchdog Timer
(1098-1101). `_drain_timeout()` (1104, runs on the Timer thread): if still draining + in-flight
(1112) → `_safe_abort()` (1117) breaks the blocked `text()` so the loop re-iterates → `_complete_drain`.
`_safe_abort()` (1335): aborts the host ONLY when `_text_in_flight.is_set()` (1358) — never when the
loop is idle in `sleep()` (which would hang forever on `was_interrupted.wait()`; validation Issue 1);
never re-raises. `on_final()` (942): FIRST thing `if not self._listening.is_set(): return` (944-945)
+ clears `_final_pending` (954).

## 1. The 6 drain properties — code mapping (all COMPLIANT)

| # | Property (PRD §4.2 #2 / item) | Code actual (daemon.py) | Verdict |
|---|---|---|---|
| (a) | `_request_stop` checks if speech is in flight | `_request_stop()` 1065 `if self._host is not None and self._text_in_flight.is_set() and self._final_pending:` ("in flight" = loop in `text()` AND speech since last final) | ✅ COMPLIANT |
| (b) | in flight → `_begin_drain` sets flag, loop lets `text()` return the natural final | 1066 `_begin_drain()`; `_begin_drain` 1078 `self._drain=True` + watchdog Timer 1079-1081; run loop 850-854 `if self._drain: self._complete_drain(); continue` (BEFORE the `_listening` re-entry) | ✅ COMPLIANT |
| (c) | `_complete_drain` disarms after the final | `_complete_drain()` 1084: 1096 `self._drain=False` → 1097 `self._disarm()` (mic off, listen clear, phase idle) → 1098-1101 cancel the watchdog Timer | ✅ COMPLIANT |
| (d) | bounded watchdog aborts if no final fires (few seconds) | `_drain_timeout()` 1104 on the Timer thread (`Timer(_DRAIN_TIMEOUT_S=5.0, …)` 1079/138): 1112 `if self._drain and self._host is not None and self._text_in_flight.is_set():` → 1117 `self._safe_abort()` (breaks the blocked `text()`) | ✅ COMPLIANT (`_DRAIN_TIMEOUT_S=5.0`) |
| (e) | NOT in flight → immediate disarm + abort | `_request_stop()` else 1067-1069: `with self._lock: self._disarm()` + 1069 `if self._host is not None: self._safe_abort()` | ✅ COMPLIANT |
| (f) | `on_final` checks the listen flag before typing ("gate inside on_final too") | `on_final()` 944-945 `if not self._listening.is_set(): return` (FIRST statement, outside `on_final_lock`) + 954 `self._final_pending=False` | ✅ COMPLIANT (PRD §4.2 #2 last sentence / §8 race row) |

## 2. Nuances (NON-blocking — record so they aren't mistaken for defects)

- **The "in flight" predicate is a 3-way AND** (1065): `host is not None` AND `_text_in_flight.is_set()`
  (the run loop is blocked inside `text()`, set/cleared at 865/869) AND `_final_pending` (speech
  occurred since the last final — set by `_touch_speech` 1040, cleared in `on_final` 954). This is
  the precise realization of PRD §4.2 #2's "an utterance is in flight (speech occurred since the last
  final and the loop is blocked in `recorder.text()`)". The `_final_pending` heuristic prevents a
  drain (and its 5 s wait) when the loop is in `text()` but nothing was actually said (idle
  re-listen) — so stop stays responsive. Note: `_drain_timeout` (1112) re-checks `_text_in_flight`
  before aborting, so a final that landed between the Timer firing and here is left alone.
- **`_DRAIN_TIMEOUT_S = 5.0`** (daemon.py:138) — the bounded watchdog window. PRD §4.2 #2 says "a few
  seconds"; 5.0 s is comfortably above the ≤1.5 s final-latency target (PRD §6) so a normal final
  always lands before the watchdog, while still bounding the worst case so a stop can never hang.
- **`_safe_abort` is `_text_in_flight`-gated** (1335/1358) — the validation Issue 1 fix. `abort()` is
  invoked ONLY when a thread is blocked in `text()`; when the loop is idle in `sleep(0.05)` it is
  SKIPPED (it would block forever on `was_interrupted.wait()`, set only inside `text()`). This is
  correct, not just safe: correctness does NOT depend on `abort()` (the listening Event gate in
  `on_final` + the run loop + `set_microphone(False)` already guarantee the instant disarm takes
  effect); `abort()` is merely a best-effort nudge to unblock a sleeping `text()`. Never re-raises.
- **Run-loop ordering** (850-854): the `if self._drain:` check precedes `if self._listening.is_set():`
  (856) so a drained session disarms instead of re-listening — the "lets text() return the natural
  final … after which the loop disarms" guarantee. (`_disarm()` itself is the Issue 2 phase-idle fix
  site — audited separately in the prior bugfix round; noted here only because `_complete_drain`
  calls it.)
- **`_begin_drain` is idempotent** (1076-1077): a re-press of the hotkey mid-drain (`if self._drain:
  return`) starts no second watchdog.
- **stop/toggle-off both route through `_request_stop`** (1391 / 1410 / 1438) — so the drain applies
  uniformly to `voicectl stop` AND `voicectl toggle`-off (PRD §4.2 #2 "an explicit stop/toggle-off").
  `_maybe_auto_stop` (the 30 s idle auto-stop) calls `_disarm()` directly (NOT `_request_stop`) — by
  design, since idle auto-stop only fires when there is NO speech, so there is never anything to drain.

## 3. Test → property mapping (the `-k 'drain or stop or abort or graceful'` set, 29 passed)

| Property | Covering test (tests/test_daemon.py) | What it asserts |
|---|---|---|
| (a)+(b) in-flight → drain | `test_stop_drains_when_utterance_in_flight`; `test_toggle_off_drains_when_utterance_in_flight` | stop/toggle-off while speech in flight → `_drain` set, text() returns the final, THEN disarm (no abort mid-final) |
| (c) _complete_drain disarm | `test_stop_drains_when_utterance_in_flight` (asserts disarm AFTER the drain completes) | the final lands + is typed, then mic off / listen clear |
| (d) watchdog abort | `test_drain_timeout_aborts_blocked_text`; `test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final` | no final within `_DRAIN_TIMEOUT_S` → `_safe_abort` breaks the blocked text() → loop completes the drain |
| (e) immediate disarm+abort | `test_stop_disarms_immediately_when_idle`; `test_stop_aborts_immediately_when_text_idle_no_speech`; `test_stop_skips_abort_when_no_text_in_flight`; `test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang` | not in flight → disarm now; abort only if `_text_in_flight` (never hangs when idle) |
| (f) on_final gate | `test_on_final_gate_when_not_listening` (in the `-k 'loop…'` set — S1's §1) | a final arriving after `_listening` cleared is dropped (not typed) |
| stop never shuts down the recorder | `test_stop_never_calls_recorder_shutdown`; `test_stop_and_toggle_never_shutdown_but_request_shutdown_does` | stop = disarm/drain, NOT a recorder shutdown (only quit/shutdown tears down) |

**Baseline: 29 passed, 164 deselected, 0.54s** (CUDA-free; the fakes inject a `_LegacyRecorderHostAdapter`
whose `text()`/`abort()` are controllable, so the drain branches are exercised directly).

## 4. Audit conclusion

The graceful-drain state machine faithfully implements PRD §4.2 #2 on all 6 properties: an explicit
stop/toggle-off with an utterance in flight lets the final model finish + emit its text before
disarming (the §1 #1 "pressing the hotkey mid-sentence does NOT drop the words already spoken"
guarantee); a stop with nothing in flight disarms immediately + aborts; a bounded 5 s watchdog
guarantees a stop can never hang; and `on_final` is gated so a straggler final after disarm is
dropped (the §4.2 #2 / §8 race row). This underpins **acceptance criterion #2** (≥3 s pause loses
zero words — the drain means a mid-utterance stop still types the in-flight final) and **#4**
(nothing typed while toggled off — the on_final gate + the immediate-disarm path). **No source
changes needed.** Append a "§2 Graceful Drain (P1.M2.T1.S2)" section to `gap_daemon_loop.md` with
the per-property table (§1) + the nuances (§2) + the test baseline (29 passed) + this conclusion.