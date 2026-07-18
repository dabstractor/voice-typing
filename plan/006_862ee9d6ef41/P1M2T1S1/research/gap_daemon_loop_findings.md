# Audit findings: daemon main loop (P1.M2.T1.S1) — gap_daemon_loop evidence

Audit of `voice_typing/daemon.py` `VoiceTypingDaemon.run()` (+ `on_final`/`_arm`/`_disarm`) against
**PRD §4.2 #1 (recorder loop) + #2 (listening gate)** on the 6 contract points. This is the evidence
the implementing agent transcribes into `plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md`.

**VERIFIED VERDICT: the main loop is PRD §4.2 #1-2 COMPLIANT on all 6 contract points — no fix needed.**
Test baseline: `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'`
→ **40 passed, 153 deselected in 1.30s** (re-ran live).

---

## 0. The KEY architectural nuance (read first) — `self._recorder` → `self._host`

The contract + PRD §4.2 #1 pseudocode describe the loop in terms of `recorder` / `self._recorder.text()`.
The **actual code** uses **`self._host`** (a `RecorderHost` subprocess — the lazy-load/crash-recovery
architecture moved the `AudioToTextRecorder` into a managed CHILD process; daemon.py:575 "self._host
replaces self._recorder. The daemon process NEVER imports RealtimeSTT"). `run()` checks/calls
`self._host` throughout (not `self._recorder`). A `_LegacyRecorderHostAdapter` (daemon.py:654) wraps
any `recorder=` injected in tests so `self._host` is a UNIFORM surface — hence the unit tests (which
inject a fake recorder) exercise the SAME `self._host.text()`/`is_alive` loop the production
RecorderHost uses. **The semantics are identical to PRD §4.2 #1** (no models → idle; listening →
text() blocks); only the attribute name + the process boundary changed. The audit maps each contract
property to the `self._host`-based code below. (Mirrors the cuda_check audit's VT-001 nuance: the
daemon process never touches the recorder/CUDA — the child does.)

## 1. The 6 contract points — code mapping (all COMPLIANT)

| # | Contract property (PRD §4.2) | Code actual (file:line) | Verdict |
|---|---|---|---|
| (a) | recorder is None → sleep+continue (no models → idle, ~0 VRAM) | `run()` daemon.py:847-848 `if self._host is None: time.sleep(0.05); continue` | ✅ COMPLIANT (`self._host is None` ≡ "no recorder") |
| (b) | listening set → text(on_final) blocks until one utterance finalizes | `run()` daemon.py:856 `if self._listening.is_set():` → 867 `self._host.text(self.on_final)` (wrapped in `_text_in_flight` set/clear, 863-868) | ✅ COMPLIANT |
| (c) | listening clear → sleep (loop never exits on silence) | `run()` daemon.py:870-871 `else: time.sleep(0.05)` | ✅ COMPLIANT (the WhisperX-flaw fix — text() returning is segmentation, not session end) |
| (d) | on_final gated on the listen flag ("gate inside on_final too") | `on_final()` daemon.py:944-945 `if not self._listening.is_set(): return` (BEFORE the on_final_lock; read-only race guard) | ✅ COMPLIANT (PRD §4.2 #2 / §8 race row) |
| (e) | shutdown_requested breaks the loop | `run()` daemon.py:834 `while not self._shutdown.is_set():` → exits → 873 `logger.info("shutdown requested; run() loop exiting")` | ✅ COMPLIANT |
| (f) | recorder.shutdown() on exit if not None | NOT inline in `run()` — DELEGATED to `shutdown()` → `_bounded_shutdown()` (daemon.py:~504-512 `rec.shutdown()` under a hard timeout + killpg force-cleanup), invoked by `main()`'s finally block + the quit `on_quit` handler | ✅ COMPLIANT-WITH-NUANCE (see §2) |

## 2. Nuance on (f) — teardown is delegated to bounded `shutdown()`, not inline in `run()`

PRD §4.2 #1 pseudocode shows `if recorder is not None: recorder.shutdown()` as the last line of the
loop body. The actual `run()` does NOT call shutdown inline — it just logs "run() loop exiting". The
teardown is owned by `shutdown()` (the bounded path: `_bounded_shutdown()` runs `host.stop()`/`rec.shutdown()`
in a daemon thread under a hard timeout, then force-terminates the spawn worker processes if it exceeds
budget). `main()`'s `finally` block calls `daemon.shutdown()` after `run()` returns (and the quit
handler calls it via `on_quit`). **This satisfies the contract (the recorder IS shut down on exit, iff
not None) via a STRONGER path** — the bounded teardown is the §4.2bis/§8 prerequisite that eliminated
the ~90 s SIGKILL hang a plain inline `recorder.shutdown()` would reintroduce. The audit records this
as compliant-with-architectural-nuance, NOT a gap. (`shutdown()` is itself audited in P1.M2.T2.S3
bounded-teardown — this audit only confirms run() hands off to it correctly.)

## 3. Additional loop behaviors NOT in the 6 contract points (note, don't flag as gaps)

The loop has three behaviors beyond the contract's 6 points, all intentional and owned by sibling audits:
- **Dead-host detection** (daemon.py:840-846): `if self._host is not None and not self._host.is_alive`
  → `_handle_dead_host()` (resets to 'unloaded', clears _listening, sets _load_error; the next arm
  re-spawns). This is Issue 3 crash recovery → **P1.M2.T2.S1** (child-crash recovery audit). Dormant in
  unit tests (the legacy adapter's `is_alive` is always True).
- **Graceful drain** (daemon.py:856-860): `if self._drain: self._complete_drain(); continue` — checked
  BEFORE the `_listening` re-entry so a drained session disarms instead of re-listening. This is PRD
  §4.2 #2's drain → **P1.M2.T1.S2** (graceful-drain audit). S1 only notes it EXISTS in the loop ordering.
- **`_text_in_flight` tracking** (daemon.py:863-868): set just before `text()`, cleared in `finally` —
  so `_safe_abort()` never invokes `abort()` when the loop is idle in `time.sleep(0.05)` (which would
  block forever on `was_interrupted.wait()`). Validation Issue 1 fix. Note as a correctness refinement.

## 4. Boot setup run() does BEFORE the loop (context for the audit)

`run()` (daemon.py:797-833) before the `while`: stamps `_start_monotonic`; `_configure_log_level`;
`_log_resolved_device()` ONLY `if self._host is not None` (lazy — no device to log at boot);
`feedback.set_listening(False)` (PRD §4.9 no hot-mic on boot); `host.set_microphone(False)` ONLY
`if self._host is not None` (boot disarm — idle audio queueing halted); logs "daemon ready (not
listening)"; starts the `_idle_watchdog` (auto-stop) + `_idle_unload_watchdog` (VRAM reclaim) daemon
threads. All conditional on `self._host is not None` → a lazy boot (no arm) skips the device log +
set_microphone + correctly reports "models lazy (not yet loaded)". Compliant with §4.2bis boot state.

## 5. Test → property mapping (the `-k 'loop or idle or run or main'` set, 40 passed)

| Property | Covering test (tests/test_daemon.py) | What it asserts |
|---|---|---|
| (a) host-None idle | `test_run_loop_not_listening_does_not_call_text` (1337) + the lazy-load boot tests | not-listening → no text() call (host-None is exercised by the lazy-load suite) |
| (b) listening → text() | `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (1371) | text() called ≥2× while listening |
| (c) not-listening → sleep | `test_run_loop_not_listening_does_not_call_text` (1337) | rec.text_calls == 0 when not listening |
| (d) on_final gate | `test_on_final_gate_when_not_listening` (641) | on_final drops text when _listening cleared |
| (e) shutdown breaks loop | `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (1371) + `test_request_shutdown_*` (988/1001/1129) + `test_main_*` (2200+) | loop exits on _shutdown; main returns |
| (f) teardown on exit | `test_shutdown_delegates_to_bounded_shutdown` (1856) + `test_request_shutdown_*` (988) | shutdown()→bounded teardown; child torn down |
| boot not-listening | `test_fresh_daemon_not_listening` (633) + `test_run_closes_capture_stream_at_boot_while_not_listening` (1350) | _listening cleared at boot; set_microphone(False) at boot |
| loop+abort safety | `test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang` (1023) + `test_stop_while_text_in_flight_aborts_and_unblocks_loop` (1081) | abort() not called when idle in sleep (the _text_in_flight guard) |

**Baseline: 40 passed, 153 deselected, 1.30s** (CUDA-free; the fakes inject a _LegacyRecorderHostAdapter
so self._host is non-None + is_alive always True → the dead-host branch is dormant).

## 6. Audit conclusion

The main loop faithfully implements PRD §4.2 #1 (recorder loop: idle when no models, text() blocks on
listening, never exits on silence) + #2 (listening gate, on_final gate). The only "deviation" from the
contract's literal `self._recorder` wording is the `self._host` subprocess evolution (semantically
identical; uniform via the legacy adapter) — record as an architectural note, NOT a defect. The (f)
teardown is delegated to bounded `shutdown()` (stronger than inline; eliminates the 90s hang) —
compliant-with-nuance. **No source changes needed.** Produce `gap_daemon_loop.md` with the per-point
table (§1) + the two nuances (§0 host-vs-recorder, §2 delegated teardown) + the test baseline (40
passed) + this conclusion.