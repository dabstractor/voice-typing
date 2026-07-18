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