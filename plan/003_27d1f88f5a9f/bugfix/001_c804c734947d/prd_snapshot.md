# Bug Fix Requirements

## Overview

Creative end-to-end QA validation of the voice-typing implementation against the
original PRD scope. Testing was performed against the **live systemd-managed daemon**
(full lifecycle: boot → arm → partials → disarm → auto-stop → idle-unload → quit/
SIGTERM), the offline transcription pipeline (test_feed_audio.py / T1), the control
socket (adversarial/malformed/concurrent inputs), the typing backends, the config
loader, and direct code analysis of the recorder-host subprocess lifecycle.

**Overall assessment:** The core PRD requirements are largely met — lazy GPU load at
boot (~0 VRAM until first arm, verified via `nvidia-smi`), instant re-arm (resident
models, 0.047s), the WhisperX-flaw fix (T1 `test_pause_keeps_both_halves` passes),
live partials in `state.json`, robust control-socket error handling, `voicectl` exit
codes, no network at runtime (`HF_HUB_OFFLINE=1`), and the fast pytest suite (340
tests green). **However, one critical regression and two major robustness gaps were
found** that the existing test suite does not catch, centered on the **bounded-teardown
requirement (PRD §4.2bis / §8 / §7.9)** which is the explicit prerequisite for the
idle-unload feature, and on **status/state correctness**.

The single most severe issue: `systemctl --user stop voice-typing` (the SIGTERM path)
while the daemon is **armed** consistently takes the full `TimeoutStopSec=15` and is
**SIGKILLed with "Failed with result 'timeout'"** — the exact symptom PRD §8 calls out
as the failure that MUST be eliminated. The `voicectl quit` path was previously
patched (commit `84f03e8` "tear down child on shutdown to fix SIGTERM hang") but the
SIGTERM path remains broken.

---

## Critical Issues (Must Fix)

### Issue 1: `systemctl stop` (SIGTERM) while armed hangs 15s → SIGKILL + "Failed with result 'timeout'"
**Severity**: Critical
**PRD Reference**: §4.2bis (Idle unload prerequisite: "the `recorder.shutdown()` call … MUST be non-blocking … It MUST NOT reproduce the ~90 s teardown hang"); §8 risk row ("`recorder.shutdown()` hangs ~90s … `SIGKILL` after systemd `TimeoutStopSec`" → mitigation "The teardown MUST be bounded/non-blocking"); Acceptance §7.9 ("the teardown is bounded (completes in seconds, no 90 s hang)"); §4.9 (systemd user service must auto-restart / stop cleanly)
**Expected Behavior**: `systemctl --user stop voice-typing` (and any session logout, which systemd signals with SIGTERM) must complete the daemon teardown **bounded in seconds, well under `TimeoutStopSec=15`**, exiting cleanly (code 0) with no SIGKILL and no "Failed with result 'timeout'". The PRD makes bounded teardown a hard prerequisite for the idle-unload feature.
**Actual Behavior**: When the daemon is **armed** (recorder-host child alive), `systemctl --user stop` consistently blocks for the **full 15.2s** and is then **SIGKILLed** by systemd, logging exactly `Failed with result 'timeout'`. This is reproduced deterministically (2/2 runs, 15.217s and 15.164s). When the daemon is **unarmed** (boot / no child), stop completes cleanly in ~0.6s — so the regression is specifically in the armed-child teardown on the SIGTERM path.

Concrete journal evidence (armed stop):
```
02:05:18.780 INFO  received signal 15; requesting clean shutdown
02:05:19.276 INFO  shutdown requested; run() loop exiting        # run() exits promptly (0.5s)
02:05:33      systemd voice-typing.service: State 'stop-sigterm' timed out. Killing.
02:05:33      systemd Killing process … with signal SIGKILL.
02:05:33      systemd voice-typing.service: Failed with result 'timeout'.
```
Note `run()` exits at +0.5s, then ~13.7s of silence until SIGKILL — the hang is in `main()`'s `finally` block (`daemon.shutdown()`), not in `run()`.

**Steps to Reproduce**:
1. `systemctl --user start voice-typing` (boots at ~0 VRAM, phase `unloaded`).
2. `.venv/bin/voicectl start` — arms the mic, spawns the recorder-host child (~2.3s model load). Confirm `status` shows `listening: on`, and `pgrep -P <MainPID>` shows the child.
3. `time systemctl --user stop voice-typing` → **~15.2s, exit shows the unit failed**.
4. `journalctl --user -u voice-typing --since "1 min ago" | grep -E 'SIGKILL|timeout|Failed with result'` → shows the SIGKILL + `Failed with result 'timeout'`.
5. Contrast: repeat from step 1 but **skip step 2** (leave it unarmed) → stop completes in ~0.6s cleanly.

**Root Cause** (verified in code): The SIGTERM handler spawns a daemon thread running `request_shutdown()`, which calls `_bounded_shutdown()` → `RecorderHost.stop(timeout=10)` (join 10s + SIGKILL group + join 2s ≈ up to 12s when the child's `recorder.shutdown()` wedges in RealtimeSTT's unbounded thread joins). Critically, `request_shutdown()` deliberately does **NOT** set the `_shutdown_done` idempotency flag (its docstring states it routes "through `_bounded_shutdown()` (NOT shutdown()'s `_shutdown_done` guard)"), expecting `main()`'s `finally`-block `daemon.shutdown()` to be a no-op because the child's `host._proc` is already `None`. That assumption holds for the `voicectl quit` path (where `request_shutdown()` + `daemon.shutdown()` run **sequentially on the same socket-worker thread**), but **breaks on the SIGTERM path**: there, `request_shutdown()` runs on the signal-handler thread while `main()`'s `daemon.shutdown()` runs **concurrently on the main thread**. Because `_shutdown_done` is still `False` when `main()` reaches `daemon.shutdown()`, it calls `_bounded_shutdown()` → `host.stop(timeout=10)` **a second time, concurrently**, while the child is still wedged. Two parallel ~12s teardowns plus `ControlServer.stop()`'s join blow the 15s `TimeoutStopSec`. (The `voicectl quit` path works because its `daemon.shutdown()` runs strictly after `request_shutdown()`'s `host.stop()` has already nulled `host._proc`, making the second call a genuine no-op.)

**Suggested Fix**: Make the SIGTERM teardown single-flight so `main()`'s `daemon.shutdown()` does not re-enter a multi-second `host.stop()` while the signal thread is already tearing down. Concretely (any one or a combination):
  - Have `request_shutdown()` set `self._shutdown_done = True` under `self._lock` after launching its teardown, so `main()`'s `daemon.shutdown()` short-circuits on the existing guard. (Caveat: a pure flag set races the concurrent read — pair with a join/wait so `main()` does not proceed until the in-flight teardown is observed finished.)
  - Make `RecorderHost.stop()` (and/or `_bounded_shutdown`) **single-flight under a lock**: a concurrent second caller shares the ONE in-progress join+SIGKILL rather than starting a second 10s join. This also directly fixes the "two parallel host.stop" race.
  - **Reduce the budget so a single teardown + `server.stop()` is comfortably under `TimeoutStopSec`**: the child's `recorder.shutdown()` wedge is real, so a `host.stop` timeout of e.g. 5s (join 5 + join 2 ≈ 7s) plus a smaller `TimeoutStopSec` margin leaves headroom. The current `timeout=10` + the double-call has no margin.
  - Verify with a new test that drives the SIGTERM path (send SIGTERM to a live armed daemon subprocess) and asserts exit within e.g. 8s with no SIGKILL — the existing fast pytest only exercises `voicectl quit` and legacy stub shutdowns, never a real armed SIGTERM.

---

## Major Issues (Should Fix)

### Issue 2: `phase` field stays `listening`/`speaking` after stop (never returns to `idle`)
**Severity**: Major
**PRD Reference**: §4.6 ("once loaded, `phase` cycles `idle`/`listening`/`speaking`"); §4.2bis lifecycle states (`loaded / not listening` ⇒ phase `idle`; `loaded / listening` ⇒ phase `listening`)
**Expected Behavior**: After the mic is disarmed (manual `stop`, `toggle`-off, or the 30s auto-stop), the `phase` field in `state.json` and the `voicectl status` `phase:` line should transition back to **`idle`** (the "loaded / not listening" state).
**Actual Behavior**: `_disarm()` clears `_listening` and calls `feedback.set_listening(False)`, but it **never calls `feedback.set_phase("idle")`**. The `phase` is only ever advanced by the child's VAD callbacks (`on_vad_detect_start`→`listening`, `on_vad_start`→`speaking`) and there is no path that resets it on disarm. As a result `phase` is **stuck at the last VAD value** (`listening` or `speaking`) indefinitely after any stop, producing a contradictory status.

Reproduced against the live daemon:
```
$ voicectl start    # then voicectl stop
$ voicectl status
listening: off
phase: listening          # BUG: listening is off, phase must be idle
$ jq . state.json
{ "listening": false, "phase": "listening", "models_loaded": true, ... }
```
If VAD had reached `speaking` before the stop, `phase` instead freezes at `speaking` while `listening: off` — even more clearly wrong. The same stale phase persists through the 30s auto-stop disarming.

**Steps to Reproduce**:
1. `systemctl --user start voice-typing && .venv/bin/voicectl start`
2. Wait ~2s for the child's VAD to set `phase: listening`.
3. `.venv/bin/voicectl stop`
4. `.venv/bin/voicectl status` → shows `listening: off` / `phase: listening` (contradiction). Or `jq .phase "$XDG_RUNTIME_DIR/voice-typing/state.json"` → `listening`.

**Impact**: `voicectl status` reports a self-contradictory state. Any consumer keying off `phase` rather than `listening` (e.g. a future overlay UI, or a script rendering the lifecycle) is misled. The `voice_typing/status.sh` tmux helper happens to key off `.listening`, so the visible tmux line is unaffected — but the documented state contract (§4.6) is violated.

**Suggested Fix**: In `VoiceTypingDaemon._disarm()`, after `self._feedback.set_listening(False)`, call `self._feedback.set_phase("idle")` to reflect the "loaded / not listening" lifecycle state. (A stray late VAD event from the child could transiently re-flip it; if that is observed, also gate the child's `("vad", …)` relay to ignore phases while not listening.)

### Issue 3: No detection/recovery when the recorder-host child crashes → daemon silently stuck "listening: on"
**Severity**: Major
**PRD Reference**: §4.2bis ("If the load fails … the daemon returns to `unloaded` … It MUST NOT leave a half-constructed recorder behind"); §4.2 robustness spirit; §7.6 (`voicectl status` must accurately report state)
**Expected Behavior**: If the recorder-host child process dies unexpectedly while armed (CUDA OOM, segfault, an uncaught exception, or the system OOM-killer), the daemon should detect the dead child, transition to an error/`unloaded` state (clearing `models_loaded`), and re-spawn on the next arm — or at minimum surface the failure in `voicectl status` instead of pretending everything is fine.
**Actual Behavior**: The `run()` main loop checks only `self._host is None` and `self._listening.is_set()` — it **never checks `host.is_alive`**. When the child dies, `self._host` is still the (dead) host object (not `None`), `_listening` is still `True`, and `_models_loaded` is still `True` (never cleared on child death). Consequences:
  1. `run()` keeps calling `host.text()`, which returns immediately (the child is gone), so the daemon spins in a no-op loop reporting `listening: on, models: loaded`.
  2. After 30s the auto-stop fires (no partials arrive), disarming the mic — but `models_loaded` stays `True`.
  3. A subsequent `voicectl start` calls `_load_host()`, which short-circuits on `if self._models_loaded: return True` **without checking whether the child is alive** — so it does **not** re-spawn the child. The dead host is reused and `host.text()` continues to return immediately.
  4. Net effect: voice typing is **silently and permanently broken** (status shows `listening: on` / `models: loaded`, but nothing is ever transcribed) until a full `voicectl quit` + service restart. The user receives no error.

**Steps to Reproduce** (simulated; no live crash needed to confirm the code path): The behavior is provable by inspection — `grep -n "is_alive" voice_typing/daemon.py` shows the `run()` loop and both watchdogs (`_idle_watchdog`, `_idle_unload_watchdog`) never consult `host.is_alive`; `_load_host()` returns `True` purely on `self._models_loaded`. To trigger on the live daemon: arm, then `kill -9 <child-pid>` (the recorder-host grandchild under the MainPID), then observe `voicectl status` still reports `listening: on, models: loaded` and a `voicectl start`/`toggle` does not bring transcription back.

**Suggested Fix**: Add a liveness check — e.g. in the `run()` loop (and/or a watchdog), detect `self._host is not None and not self._host.is_alive` while `_models_loaded`, then clear the host (`self._host = None`, `self._models_loaded = False`, `feedback.set_phase("unloaded")` / `set_models_loaded(False)`, set a `_load_error`) so the next arm re-spawns via `_load_host()`. Optionally surface the crash in `status` (`load_error`). Add a test that injects a `RecorderHost` fake whose `is_alive` flips to `False` and asserts the daemon recovers on the next arm.

---

## Minor Issues (Nice to Fix)

### Issue 4: Config numeric fields accept wrong types silently, breaking the feature at runtime
**Severity**: Minor
**PRD Reference**: §4.5 (config schema; "Unknown keys raise TypeError … a typo'd config key surfaces loudly"); robustness
**Expected Behavior**: A malformed config value of the wrong type (e.g. `auto_stop_idle_seconds = "thirty"`) should fail fast at load with a clear error, the same way an unknown key does today.
**Actual Behavior**: The dataclass overlay (`VoiceTypingConfig.from_toml`) only rejects **unknown keys**; it does no type validation. A string where a float is expected loads silently:
```
auto_stop_idle_seconds = "thirty"   # in config.toml
-> AsrConfig.auto_stop_idle_seconds == 'thirty'  (a str, loaded with NO error)
```
At runtime this surfaces as a `TypeError` inside `_maybe_auto_stop` (`time.monotonic() - ts < threshold` with `threshold="thirty"`), which the `_idle_watchdog` swallows via its `except Exception` — so the **auto-stop feature silently stops working** (and likewise `auto_unload_idle_seconds` would silently disable idle-unload) with only a repeating exception in the journal, rather than a load-time error. The daemon does not crash (the watchdog catches it), but the feature is broken with no clear cause.

**Steps to Reproduce**: Put `auto_stop_idle_seconds = "thirty"` in `~/.config/voice-typing/config.toml`, restart the daemon, arm it, and stay silent — auto-stop never fires; `journalctl` shows repeated `TypeError` tracebacks from the idle watchdog.

**Suggested Fix**: Add lightweight type coercion/validation in `from_toml` (e.g. `float(section["auto_stop_idle_seconds"])`, or `pydantic`/`__post_init__` checks) so a wrong-typed value raises a clear `ConfigError` at load, mirroring the existing unknown-key behavior.

### Issue 5: Stale 43 MiB `realtimesst.log` committed-era artifact left in the repo
**Severity**: Minor
**PRD Reference**: §4.2 (sole log path = stderr→journald); §4.1 repo layout (gitignored `*.log` under repo)
**Actual Behavior**: A 43 MiB `realtimesst.log` sits in the repo root (from a pre-`no_log_file=True` run). It is correctly gitignored and `install.sh` deletes it, so it is harmless — but it is present in the working tree and could confuse a reader. No action required beyond awareness; `install.sh` already cleans it.

---

## Testing Summary
- Total tests performed: ~25 distinct manual/integration probes against the live daemon + 340 automated pytest (all green) + 7 T1 feed_audio tests (all green).
- Passing: lazy-load at boot (~0 VRAM, verified via `nvidia-smi`), instant re-arm (0.047s), resident-after-disarm (T6c), auto-stop (fires at ~32s, correct journal line), `voicectl quit` clean exit, control-socket robustness (malformed/non-object/unknown/missing-cmd/empty-line), `voicectl` exit codes (0/1/2/64), no network at runtime (0 HTTP/silero-download lines in journal), typing backends send no newline, config unknown-key rejection, the WhisperX-flaw fix (T1 pause test).
- Failing: **SIGTERM teardown (Issue 1, Critical)**, **phase-after-stop (Issue 2, Major)**, **child-crash recovery (Issue 3, Major)**, config type validation (Issue 4, Minor).
- Areas with good coverage: lazy-load lifecycle, control-socket protocol, textproc, typing backends, offline transcription pipeline (T1).
- Areas needing more attention: **the SIGTERM/systemctl-stop teardown path** (the existing tests only cover `voicectl quit` and legacy stub shutdowns, never a real armed SIGTERM — which is exactly why Issue 1 slipped through), **status/state consistency on disarm** (phase), and **child-process liveness monitoring**.
