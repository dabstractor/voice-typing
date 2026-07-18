# Gap Report — P1.M2.T1.S1: Daemon Main Loop vs PRD §4.2 #1-2

**Date:** 2025-01 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py` `VoiceTypingDaemon.run()` (the listen-forever loop, L797-872)
**plus** `on_final` (L942), `_arm` (L987), and `_disarm` (L1002) against **PRD §4.2 #1 (recorder loop)**
and **PRD §4.2 #2 (listening gate + on_final gate)** — the 6 basic-loop contract points
((a) recorder/host is None → sleep+continue; (b) listening set → `text(on_final)` blocks; (c) listening
clear → sleep; (d) `on_final` gated on the listen flag; (e) `shutdown_requested` breaks the loop;
(f) `recorder.shutdown()` on exit if not None). Subtask **P1.M2.T1.S1** of verification round
`006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `run()` (L797, incl. the `while` @834, host-None idle @847-848,
  listening→`text()` @856/867, not-listening→sleep @870-871, post-loop log @872); `on_final()`
  (L942, the `_listening` gate @945); `_arm()` (L987, sets `_listening`); `_disarm()` (L1002, clears
  `_listening`); the delegated teardown path `shutdown()` (L1647) → `_bounded_shutdown()` (L1620).
- `tests/test_daemon.py` — the `-k 'loop or idle or run or main'` slice (the contract's run target;
  40 tests; the fakes inject a `_LegacyRecorderHostAdapter` so `self._host` is uniform + `is_alive`
  always True → the dead-host branch is dormant).

**Bottom line:** ✅ All 6 PRD §4.2 #1-2 contract points are **compliant** (each with file:line evidence
below). The `-k 'loop or idle or run or main'` slice is **40 passed, 153 deselected in 1.32s**
(re-ran live; matches the verified baseline). Two **non-blocking** architectural nuances are recorded
so they are not mistaken for defects: **(i)** the contract's `self._recorder` wording maps to
`self._host` (a `RecorderHost` subprocess; uniform via `_LegacyRecorderHostAdapter`); **(ii)** the
point-(f) teardown is **delegated** to bounded `shutdown()` (hard timeout + killpg), not inlined in
`run()` — stronger than the PRD pseudocode. **No source files were modified.** The only new artifact is
this report.

---

## 1. Method

Each of the 6 contract points was mapped to **specific `voice_typing/daemon.py` file:line** via
`grep -nE`, then re-verified by reading the loop body (L834-872), `on_final` (L942-953), `_arm` (L987),
`_disarm` (L1002), and the teardown delegation (`shutdown` @L1647 → `_bounded_shutdown` @L1620). The
contract's test target was then re-run live (`tests/test_daemon.py -k 'loop or idle or run or main'`,
§3). The two architectural nuances were cross-checked against the module's docstrings
(daemon.py:575 "self._host replaces self._recorder"; the `_LegacyRecorderHostAdapter` @654; the
`_bounded_shutdown` rationale @1620).

### Commands run (re-verification)

```bash
# locate every contract site in the loop + the gate + the arm/disarm + the teardown
grep -nE 'while not self._shutdown|self._host is None|self._listening.is_set\(\):|self._host.text|time.sleep\(0.05\)|loop exiting|def on_final|if not self._listening.is_set|def _arm|def _disarm|def shutdown|def _bounded_shutdown' voice_typing/daemon.py
# the contract's run target (re-ran live)
timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'
# scope guard — no source modified
git status --short
```

---

## 2. The 6 contract points — per-point compliance table

| # | Contract (PRD §4.2 #1-2) | Code actual (`voice_typing/daemon.py`) | Verdict |
|---|---|---|---|
| (a) | recorder is None → `sleep` + `continue` (no models → idle, ~0 VRAM) | `run()` **L847-848**: `if self._host is None: time.sleep(0.05); continue` | ✅ **COMPLIANT** (`self._host is None` ≡ "no recorder loaded") |
| (b) | listening set → `text(on_final)` blocks until one utterance finalizes | `run()` **L856** `if self._listening.is_set():` → **L867** `self._host.text(self.on_final)` (wrapped in the `_text_in_flight` set/clear @863-868) | ✅ **COMPLIANT** |
| (c) | listening clear → `sleep` (loop **never exits on silence**) | `run()` **L870-871**: `else: time.sleep(0.05)` — `text()` returning is normal segmentation, not session end | ✅ **COMPLIANT** (the WhisperX-flaw fix, PRD §1 #1) |
| (d) | `on_final` gated on the listen flag ("gate inside on_final too") | `on_final()` **L945-946**: `if not self._listening.is_set(): return` — the **first** thing on_final does, OUTSIDE the `_on_final_lock` (read-only race guard) | ✅ **COMPLIANT** (PRD §4.2 #2 / §8 race row) |
| (e) | `shutdown_requested` breaks the loop | `run()` **L834**: `while not self._shutdown.is_set():` → loop exits → **L872** `logger.info("shutdown requested; run() loop exiting")` | ✅ **COMPLIANT** |
| (f) | `recorder.shutdown()` on exit if not None | NOT inlined in `run()` — **DELEGATED** to `shutdown()` (L1647) → `_bounded_shutdown()` (L1620-1631: `host.stop(timeout=...)` under a hard budget, then killpg force-cleanup), invoked by `main()`'s `finally` block + the quit `on_quit` handler | ✅ **COMPLIANT-WITH-NUANCE** (see §4.ii) |

---

## 3. Test result — the contract's run target (the evidence)

```bash
timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'
# → 40 passed, 153 deselected in 1.32s
```

**Recorded count: 40 passed, 153 deselected** (matches the verified baseline of 40 passed, 1.30s;
re-ran live during this audit). The suite is CUDA-free — the fakes inject a
`_LegacyRecorderHostAdapter` so `self._host` is non-None and `is_alive` is always True, which keeps the
dead-host branch (L840-846) dormant and exercises the **same** `self._host.text()` / `is_alive` loop
the production `RecorderHost` uses.

### Test → property mapping

| Property | Covering test (`tests/test_daemon.py`) | What it asserts |
|---|---|---|
| (a) host-None idle | `test_run_loop_not_listening_does_not_call_text` (1337) + the lazy-load boot tests | not-listening → no `text()` call (host-None is exercised by the lazy-load suite) |
| (b) listening → `text()` | `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (1371) | `text()` called ≥2× while listening |
| (c) not-listening → sleep | `test_run_loop_not_listening_does_not_call_text` (1337) | `rec.text_calls == 0` when not listening |
| (d) on_final gate | `test_on_final_gate_when_not_listening` (641) | `on_final` drops text when `_listening` cleared |
| (e) shutdown breaks loop | `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (1371) + `test_request_shutdown_*` (988/1001/1129) + `test_main_*` (2200+) | loop exits on `_shutdown`; `main()` returns |
| (f) teardown on exit | `test_shutdown_delegates_to_bounded_shutdown` (1856) + `test_request_shutdown_*` (988) | `shutdown()` → bounded teardown; child torn down |
| boot not-listening | `test_fresh_daemon_not_listening` (633) + `test_run_closes_capture_stream_at_boot_while_not_listening` (1350) | `_listening` cleared at boot; `set_microphone(False)` at boot |
| loop + abort safety | `test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang` (1023) + `test_stop_while_text_in_flight_aborts_and_unblocks_loop` (1081) | `abort()` not called when idle in `sleep` (the `_text_in_flight` guard) |

---

## 4. Architectural nuances (NON-blocking — recorded so they are not mistaken for defects)

### (i) `self._recorder` → `self._host`: the loop proxies to a `RecorderHost` subprocess

The contract + PRD §4.2 #1 pseudocode describe the loop in terms of `recorder` / `self._recorder.text()`.
The **actual code** uses **`self._host`** — a `RecorderHost` subprocess (the lazy-load / crash-recovery
architecture moved the `AudioToTextRecorder` into a managed CHILD process; daemon.py:575 notes
"`self._host` replaces `self._recorder`. The daemon process NEVER imports RealtimeSTT"). `run()` checks
and calls `self._host` throughout (not `self._recorder`): the host-None idle (L847), the liveness probe
(L840), the `text()` call (L867). A `_LegacyRecorderHostAdapter` (daemon.py:654) wraps any `recorder=`
injected in tests so `self._host` is a **uniform** surface — hence the unit tests exercise the **same**
`self._host.text()` / `is_alive` loop the production `RecorderHost` uses. **The semantics are identical
to PRD §4.2 #1** (no models → idle; listening → `text()` blocks); only the attribute name + the process
boundary changed. This audit maps the contract's "`recorder`" wording to `self._host` at every site —
this is the deliberate design it is, **not** a defect. (Mirrors the cuda_check audit's VT-001 nuance:
the daemon process never touches the recorder / CUDA — the child does.)

### (ii) Point (f) teardown is DELEGATED to bounded `shutdown()`, not inlined in `run()`

PRD §4.2 #1 pseudocode shows `if recorder is not None: recorder.shutdown()` as the last line of the loop
body. The actual `run()` does **not** call shutdown inline — it only logs "run() loop exiting" (L872).
The teardown is owned by `shutdown()` (L1647) → `_bounded_shutdown()` (L1620-1631): `host.stop(timeout=…)`
runs under a hard budget, then force-terminates the spawn worker process group (`os.killpg`) if it
exceeds budget. `main()`'s `finally` block calls `daemon.shutdown()` after `run()` returns, and the
quit handler calls it via `on_quit`. **This satisfies the contract (the recorder IS shut down on exit,
iff not None) via a STRONGER path** — the bounded teardown is the §4.2bis / §8 prerequisite that
eliminated the ~90 s SIGKILL hang a plain inline `recorder.shutdown()` would reintroduce. Recorded as
**compliant-with-architectural-nuance**, not a gap. (`shutdown()` is itself audited in detail in
**P1.M2.T2.S3** — bounded teardown; this audit only confirms `run()` hands off to it correctly.)

### (iii) Additional loop branches noted present, detail deferred to sibling audits

The loop also contains three behaviors beyond the 6 basic contract points, all intentional and owned
by sibling audits — noted present here, **not** flagged as gaps:
- **Dead-host detection** (L840-846): `if self._host is not None and not self._host.is_alive` →
  `_handle_dead_host()` (resets to 'unloaded', clears `_listening`, sets `_load_error`; the next arm
  re-spawns). → **P1.M2.T2.S1** (child-crash recovery). Dormant in unit tests.
- **Graceful drain** (L856-860): `if self._drain: self._complete_drain(); continue` — checked BEFORE
  the `_listening` re-entry so a drained session disarms instead of re-listening. → **P1.M2.T1.S2**
  (graceful-drain audit).
- **`_text_in_flight` tracking** (L863-868): set just before `text()`, cleared in `finally` — so
  `_safe_abort()` never invokes `abort()` when the loop is idle in `time.sleep(0.05)` (which would
  block forever on `was_interrupted.wait()`). Validation Issue 1 fix — a correctness refinement.

---

## 5. Conclusion

The daemon main loop faithfully implements **PRD §4.2 #1** (recorder loop: idle when no models,
`text()` blocks on listening, never exits on silence — the WhisperX-flaw fix, §1 #1) **and §4.2 #2**
(the listening gate, plus the `on_final` stop-drop gate). All 6 contract points (a)-(f) are
**COMPLIANT** with `voice_typing/daemon.py` file:line evidence, and the contract's run target
(`-k 'loop or idle or run or main'`) is **40 passed, 153 deselected**. The two architectural "deviations"
from the contract's literal wording are deliberate, documented evolutions, **not** defects: the
`self._host` subprocess surface (semantically identical; uniform via the legacy adapter) and the
delegated bounded teardown (stronger than the inline pseudocode — eliminates the 90 s hang).

**No source files were modified.** The only artifact produced by this subtask is this report.

---

# §2 — Graceful Drain (P1.M2.T1.S2): stop during in-flight utterance, drain watchdog, abort-on-idle

**Date:** 2025-01 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py`'s **graceful-drain state machine** against **PRD §4.2 #2**
("Stop is graceful (drain)") on the **6 drain properties (a)-(f)**. The state machine comprises:
`_request_stop` (L1053) / `_begin_drain` (L1073) / `_complete_drain` (L1084) / `_drain_timeout`
(L1104) / `_safe_abort` (L1335) + the `run()` drain branch (L850-854) + the `on_final` listen-flag
gate (L945) + the `_final_pending`/`_text_in_flight` tracking (`_text_in_flight` set/cleared around
`text()` @865/869; `_final_pending` set by `_touch_speech` @1040, cleared in `on_final` @954).
Subtask **P1.M2.T1.S2** of verification round `006_862ee9d6ef41` — **appended** to this report (§1
above is P1.M2.T1.S1's main-loop audit; this §2 owns the drain 6 properties, a different contract).
**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `_request_stop()` (L1053, predicate @1065, branch @1066/1067-1069);
  `_begin_drain()` (L1073; `_drain=True` @1078, watchdog `Timer` @1079-1081, idempotent @1076-1077);
  `_complete_drain()` (L1084; `_drain=False` @1096, `_disarm()` @1097, cancel timer @1098-1101);
  `_drain_timeout()` (L1104, runs on the Timer thread; guard @1112, `_safe_abort` @1117);
  `_safe_abort()` (L1335; `_text_in_flight` gate @1358); `run()` drain branch (L850-854, BEFORE the
  `_listening` re-entry @858); `on_final()` (L942; gate @945-946, `_final_pending=False` @954);
  `_touch_speech()` (L1029; `_final_pending=True` @1040); `_DRAIN_TIMEOUT_S = 5.0` (@138); entry points
  `stop()` (L1388 → `_request_stop` @1391), `toggle()`-off (L1393 → `_request_stop` @1410),
  `toggle_lite()`-off (L1426 → `_request_stop` @1438); `_maybe_auto_stop()` (L1119 → `_disarm()`
  @1139 directly, NOT `_request_stop` — by design).
- `tests/test_daemon.py` — the `-k 'drain or stop or abort or graceful'` slice (the contract's run
  target; 29 tests; the fakes inject a `_LegacyRecorderHostAdapter` whose `text()`/`abort()` are
  controllable, so the drain branches are exercised directly without CUDA).

**Bottom line:** ✅ All 6 PRD §4.2 #2 drain properties are **compliant** (each with file:line
evidence below). The `-k 'drain or stop or abort or graceful'` slice is **29 passed, 164 deselected
in 0.55s** (re-ran live; matches the verified baseline of 29 passed, 0.54s). Six **non-blocking**
nuances are recorded so they are not mistaken for defects (§4). **No source files were modified**
(this is a read-only audit — the drain is PRD §4.2 #2-compliant per the re-verification).

---

## §2.1 Method

Each of the 6 drain properties was mapped to **specific `voice_typing/daemon.py` file:line** via
`grep -nE`, then re-verified by reading `_request_stop` (L1053-1071), `_begin_drain` (L1073-1082),
`_complete_drain` (L1084-1102), `_drain_timeout` (L1104-1118), `_safe_abort` (L1335-1363), the
`run()` drain branch (L850-854), `on_final` (L942-954), and the entry points `stop()`/`toggle()`/
`toggle_lite()` (L1388/1393/1426) + `_maybe_auto_stop()` (L1119). The contract's test target was
then re-run live (`tests/test_daemon.py -k 'drain or stop or abort or graceful'`, §2.3). The 3-way
in-flight predicate + the `_safe_abort` gate + the run-loop ordering were cross-checked against the
method docstrings (daemon.py:1056 "utterance is in flight … blocked inside text() AND speech has
occurred since the last final"; daemon.py:1336 "validation Issue 1"; daemon.py:850 "Checked BEFORE
the _listening re-entry").

### Commands run (re-verification)

```bash
# locate every drain site + the entry points + the watchdog bound
 grep -nE 'def _request_stop|def _begin_drain|def _complete_drain|def _drain_timeout|def _safe_abort|def on_final|def _touch_speech|def stop|def toggle|_DRAIN_TIMEOUT_S|self\._drain|self\._text_in_flight|self\._final_pending' voice_typing/daemon.py
# the contract's run target (re-ran live)
timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'
# scope guard — no source modified
git status --short
```

---

## §2.2 The 6 drain properties — per-property compliance table

| # | Property (PRD §4.2 #2 / item) | Code actual (`voice_typing/daemon.py`) | Verdict |
|---|---|---|---|
| (a) | `_request_stop` checks if an utterance is **in flight** before choosing drain vs immediate disarm | `_request_stop()` **L1065** `if self._host is not None and self._text_in_flight.is_set() and self._final_pending:` (3-way AND: host live + run loop blocked in `text()` + speech occurred since the last final) | ✅ **COMPLIANT** (the precise realization of PRD §4.2 #2's "utterance is in flight" wording; see nuance §4.i) |
| (b) | in flight → `_begin_drain` sets the flag; the run loop **lets `text()` return the natural final** (no mid-final abort) | **L1066** `self._begin_drain()`; `_begin_drain` **L1078** `self._drain = True` + arms watchdog `Timer(_DRAIN_TIMEOUT_S, self._drain_timeout)` **L1079-1081**; run loop **L850-854** `if self._drain: self._complete_drain(); continue` — checked BEFORE the `_listening` re-entry (@858) | ✅ **COMPLIANT** |
| (c) | `_complete_drain` **disarms after** the final lands | `_complete_drain()` **L1084**: **L1096** `self._drain = False` → **L1097** `self._disarm()` (mic off, listen gate cleared, phase idle) → **L1098-1101** cancel the watchdog `Timer` | ✅ **COMPLIANT** |
| (d) | bounded watchdog **aborts** if no final fires ("a few seconds") | `_drain_timeout()` **L1104** on the Timer thread (`Timer(_DRAIN_TIMEOUT_S=5.0, …)` @1079/138): **L1112** `if self._drain and self._host is not None and self._text_in_flight.is_set():` → **L1117** `self._safe_abort()` (breaks the blocked `text()`; the run loop then completes the drain) | ✅ **COMPLIANT** (`_DRAIN_TIMEOUT_S = 5.0`) |
| (e) | NOT in flight → **immediate disarm + abort** | `_request_stop()` else **L1067-1069**: `with self._lock: self._disarm()` + **L1069** `if self._host is not None: self._safe_abort()` | ✅ **COMPLIANT** |
| (f) | `on_final` checks the listen flag before typing ("gate inside on_final too") | `on_final()` **L945-946** `if not self._listening.is_set(): return` — the **first** thing `on_final` does, OUTSIDE the `_on_final_lock` (read-only race guard); then **L954** `self._final_pending = False` | ✅ **COMPLIANT** (PRD §4.2 #2 last sentence / §8 race row — a straggler final after disarm is dropped, not typed) |

---

## §2.3 Test result — the contract's run target (the evidence)

```bash
timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'
# → 29 passed, 164 deselected in 0.55s
```

**Recorded count: 29 passed, 164 deselected** (matches the verified baseline of 29 passed, 0.54s;
re-ran live during this audit). The slice is CUDA-free — the fakes inject a
`_LegacyRecorderHostAdapter` whose `text()` / `abort()` are controllable, so the drain branches are
exercised directly (in-flight → drain; not-in-flight → immediate disarm; watchdog abort; on_final
gate; stop-never-shuts-down-the-recorder).

### Test → property mapping

| Property | Covering test (`tests/test_daemon.py`) | What it asserts |
|---|---|---|
| (a)+(b) in-flight → drain (no mid-final abort) | `test_stop_drains_when_utterance_in_flight`; `test_toggle_off_drains_when_utterance_in_flight` | stop/toggle-off while speech in flight → `_drain` set, `text()` returns the final, THEN disarm (no abort mid-final) |
| (c) `_complete_drain` disarm-after-final | `test_stop_drains_when_utterance_in_flight` (asserts disarm AFTER the drain completes) | the final lands + is typed, then mic off / listen clear |
| (d) watchdog abort | `test_drain_timeout_aborts_blocked_text`; `test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final` | no final within `_DRAIN_TIMEOUT_S` → `_safe_abort` breaks the blocked `text()` → loop completes the drain |
| (e) immediate disarm+abort (idle) | `test_stop_disarms_immediately_when_idle`; `test_stop_aborts_immediately_when_text_idle_no_speech`; `test_stop_skips_abort_when_no_text_in_flight`; `test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang` | not in flight → disarm now; `abort()` only if `_text_in_flight` (never hangs when idle) |
| (f) `on_final` gate | `test_on_final_gate_when_not_listening` (in the `-k 'loop…'` set — §1's §2.3 above) | a final arriving after `_listening` is cleared is dropped (not typed) |
| stop never shuts down the recorder | `test_stop_never_calls_recorder_shutdown`; `test_stop_and_toggle_never_shutdown_but_request_shutdown_does` | stop = disarm/drain, NOT a recorder shutdown (only quit/shutdown tears down) |

---

## §2.4 Nuances (NON-blocking — recorded so they are not mistaken for defects)

### (i) The "in flight" predicate is a 3-way AND, not just `_text_in_flight`

`_request_stop` (L1065) checks `self._host is not None and self._text_in_flight.is_set() and
self._final_pending`. The three terms:
- `_text_in_flight` — the run loop is blocked **inside** `text()` (set @865, cleared @869).
- `_final_pending` — **speech occurred since the last final** (set by `_touch_speech` @1040 on the
  host's `'speech'` event; cleared in `on_final` @954).
- `host is not None` — a recorder is actually loaded.

This is the precise realization of PRD §4.2 #2's wording ("an utterance is in flight: speech
occurred since the last final and the loop is blocked in `recorder.text()`"). The third term
(`_final_pending`) is **not** "extra" — it prevents a 5 s drain wait when the loop is in `text()`
but nothing was actually said (idle re-listen), so a stop stays responsive. Note: `_drain_timeout`
(L1112) re-checks `_text_in_flight` before aborting, so a final that landed between the Timer firing
and the abort is left alone.

### (ii) `_DRAIN_TIMEOUT_S = 5.0` (daemon.py:138) is the bounded watchdog window

PRD §4.2 #2 says "a bounded drain watchdog (a few seconds) aborts the rare case where no final ever
fires, so a stop can never hang." `_DRAIN_TIMEOUT_S = 5.0` (daemon.py:138) is comfortably above the
≤1.5 s final-latency target (PRD §6), so a normal final always lands before the watchdog fires,
while still bounding the worst case so **a stop can never hang**. This is correct, not a defect — do
**not** flag 5.0 s as "too long" or "too short."

### (iii) `_safe_abort` is `_text_in_flight`-gated (daemon.py:1335/1358) — the validation Issue 1 fix

`abort()` is invoked ONLY when a thread is blocked in `text()` (`if not self._text_in_flight.is_set():
return`, L1358); when the loop is idle in `time.sleep(0.05)` it is **skipped** — it would block
forever on `was_interrupted.wait()` (an event set only inside `text()`). This is **correct, not
just safe**: correctness does NOT depend on `abort()` (the `_listening` Event gate in `on_final` +
the run loop + `set_microphone(False)` already guarantee the instant disarm takes effect); `abort()`
is merely a best-effort nudge to unblock a sleeping `text()`. `abort()` never re-raises either
(wrapped in try/except @1360-1362). Recorded as a nuance — do **not** flag the gate as a defect.

### (iv) Run-loop ordering: the drain check precedes the `_listening` re-entry

`run()` checks `if self._drain:` (L850) BEFORE `if self._listening.is_set():` (L858), so a drained
session **disarms** instead of re-listening — this IS the "lets `text()` return the natural final …
after which the loop disarms" guarantee (property (b)+(c)). Do **not** flag the early drain check as
"skipping the listen gate." (The dead-host check @840-846 precedes both; the host-None idle @847
precedes the drain check — see §1's §4.iii for the full loop ordering.)

### (v) `_begin_drain` is idempotent

`_begin_drain` (L1073) guards with `if self._drain: return` (L1076-1077) — a re-press of the hotkey
mid-drain starts no second watchdog `Timer`. Both `stop()` and `toggle()`-off route through
`_request_stop` (L1391 / L1410 / L1438), so the drain applies uniformly to `voicectl stop` AND
`voicectl toggle`-off (PRD §4.2 #2 "an explicit stop/toggle-off").

### (vi) `_maybe_auto_stop` bypasses the drain BY DESIGN

The 30 s idle auto-stop (`_maybe_auto_stop`, L1119) calls `_disarm()` **directly** (L1139), NOT
`_request_stop()`. This is intentional: idle auto-stop only fires after
`cfg.asr.auto_stop_idle_seconds` of NO recognized speech, so the last utterance finalized long ago —
there is **never anything to drain**. An immediate disarm+abort is correct. This is NOT a
missing-drain gap; the drain applies to explicit stop/toggle-off only.

---

## §2.5 Conclusion

The graceful-drain state machine faithfully implements **PRD §4.2 #2** ("Stop is graceful
(drain)") on all 6 properties (a)-(f): an explicit `stop`/`toggle`-off with an utterance in flight
lets the final model finish + emit its text **before** disarming (property (b)+(c) — the §1 #1
"pressing the hotkey mid-sentence does NOT drop the words already spoken" guarantee); a stop with
nothing in flight disarms immediately + aborts (property (e)); a bounded **5 s watchdog** guarantees
a stop can never hang (property (d)); and `on_final` is gated so a straggler final after disarm is
dropped, not typed (property (f) — PRD §4.2 #2 last sentence / §8 race row).

This underpins the project's acceptance criteria:
- **#2 (a ≥3 s pause loses zero words)** — the drain means a mid-utterance stop still types the
  in-flight final before disarming (the run loop's `if self._drain:` branch @850-854 lets `text()`
  return its natural final, then `_complete_drain` disarms). Certified by (b)+(c).
- **#4 (nothing is typed while toggled off)** — the `on_final` listen-flag gate (@945-946) drops any
  straggler final that arrives after disarm; the not-in-flight path (@1067-1069) disarms + aborts
  immediately. Certified by (e)+(f).

**Verdict: COMPLIANT on all 6 properties — no fix needed.** **No source files were modified**
(this is a read-only audit). The only artifact produced by this subtask is this appended §2 section.