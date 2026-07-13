# Implementation Issue Feedback (Attempt 1/3)

The previous implementation attempt encountered an issue that requires re-planning.

## Issue Details

PRP P1.M3.T2.S2 implemented: tests/test_idle_and_gpu.sh rewritten to the 4-part T6 lazy-load lifecycle (2-run structure, POLL-based helpers, idempotent stop_daemon_run) and tests/ACCEPTANCE.md updated. All validation gates pass (L1 bash -n + shellcheck clean; L3 scope = only the 2 test files; L4 T4 regression green). Two necessary in-scope deviations (auto-stop-aware stop skip to avoid the pre-existing control-lock wedge; voicectl timeout wrapper) are documented in-code. The test runs end-to-end in ~6 min and is deterministic across 2 runs. HOWEVER: T6(d-gone) deterministically FAILS, surfacing a PRODUCTION BUG in the M1.T1/M3.T1 idle-unload path — after unload, a 258 MiB CUDA context remains resident on the daemon PID (violating PRD §7.9 '~0 VRAM' and §6 T6(d) 'the PID disappears from nvidia-smi again'). The armed-state tree contains only the daemon PID + the multiprocessing resource_tracker (no separate spawn-worker PIDs hold the VRAM), so _bounded_shutdown's force-terminate of transcript_process/reader_process has nothing to reclaim. Per the PRP's explicit Critical #1/#5 + Anti-Pattern #1, this is a production bug to REPORT, not fix: I did NOT weaken the T6(d-gone) assertion or touch voice_typing/*. The test correctly exits 1 (T6_OK=1) with a fail-loud diagnostic; every other clause (T6 a/b/c/d-reload, T4/criterion-5 at 1.67% CPU, criterion 6/8) PASSES. The idle-unload production path needs fixing so it actually releases the residual ~258 MiB CUDA context on the daemon process.

## Full Agent Output

All validation is complete. Let me provide the final result.

## Summary

I executed PRP **P1.M3.T2.S2** — rewriting `tests/test_idle_and_gpu.sh` T6 to the 4-part lazy-load lifecycle + confirming T4, and updating `tests/ACCEPTANCE.md`.

### What was delivered

**`tests/test_idle_and_gpu.sh`** (rewritten into a 2-run structure):
- **Refactored helpers**: `vram_tree_state`/`assert_vram_absent`/`assert_vram_present`/`wait_vram_absent`/`wait_vram_present` (POLL-based, not fixed-sleep) + `launch_daemon_run`/`wait_daemon_ready`/`stop_daemon_run` (idempotent, trap-shared). Kept `daemon_tree_pids`/`cpu_tree_seconds`/`capture_pane`.
- **RUN 1** (default 1800s): T6(a) boot-absent → criterion-8 → criterion-6 → T6(b) armed-present → T4 (120s, unchanged) → T6(c) disarmed-still-present → criterion-6 unit.
- **RUN 2** (5s override): boot-absent → armed-present → T6(d-gone) idle-unload-absent → T6(d-reload) re-arm-present.
- Header rewritten to document the 4-part lifecycle; `T6_OK`+`IDLE_OK` aggregate into the verdict.

**`tests/ACCEPTANCE.md`**: evidence block, per-criterion lines, criterion-1/5/6 rows, and the T6 explanatory paragraph all updated to the 4-part lifecycle with real measured nvidia-smi numbers.

### Two necessary in-scope deviations (both test-only, documented in-code)

1. **Auto-stop-aware stop skip**: After T4's 120s window, the default `auto_stop_idle_seconds=30` has already disarmed the mic. Calling `voicectl stop` on an already-disarmed daemon **wedges the control lock** (the pre-existing production wedge documented in `daemon.py` `_disarm()`). The test skips the redundant stop when status shows `listening: off`. T6(c) is still valid (daemon is disarmed + resident).
2. **`voicectl` timeout wrapper**: `voicectl`'s socket `readline()` has no timeout, so a wedge would hang forever. Control commands now run under `timeout 30` so a wedge fails loud (exit 124) instead of stalling.

### ⚠️ Production bug discovered (reported, NOT patched — per PRP Critical #1/#5)

**T6(d-gone) deterministically FAILS**: after idle-unload, VRAM drops 2804→**258 MiB** but the daemon PID stays listed at 258 MiB (never reaches ~0). The watchdog fires correctly (`voice-typing idle-unload: 5.0s disarmed; unloading models`), `voicectl status` shows `phase: unloaded` + `(not loaded)`, but a **258 MiB CUDA context remains on the daemon process itself**. This violates PRD §7.9 ("~0 VRAM, verified via nvidia-smi") and §6 T6(d) ("the PID disappears from nvidia-smi again"). Root cause: the armed-state tree contains only the daemon PID + the multiprocessing resource_tracker — there are **no separate spawn-worker PIDs** holding the VRAM, so `_bounded_shutdown`'s force-terminate of `transcript_process`/`reader_process` has nothing to reclaim. This is a bug in the M1.T1/M3.T1 unload path. **The test correctly asserts the §7.9 contract and exits 1; I did NOT weaken the assertion or touch `voice_typing/*`.**

Every other clause passes: T6(a/b/c/d-reload), T4/criterion-5 (1.67% CPU), criterion 6/8.

```json
{
   "result": "issue",
   "message": "PRP P1.M3.T2.S2 implemented: tests/test_idle_and_gpu.sh rewritten to the 4-part T6 lazy-load lifecycle (2-run structure, POLL-based helpers, idempotent stop_daemon_run) and tests/ACCEPTANCE.md updated. All validation gates pass (L1 bash -n + shellcheck clean; L3 scope = only the 2 test files; L4 T4 regression green). Two necessary in-scope deviations (auto-stop-aware stop skip to avoid the pre-existing control-lock wedge; voicectl timeout wrapper) are documented in-code. The test runs end-to-end in ~6 min and is deterministic across 2 runs. HOWEVER: T6(d-gone) deterministically FAILS, surfacing a PRODUCTION BUG in the M1.T1/M3.T1 idle-unload path — after unload, a 258 MiB CUDA context remains resident on the daemon PID (violating PRD §7.9 '~0 VRAM' and §6 T6(d) 'the PID disappears from nvidia-smi again'). The armed-state tree contains only the daemon PID + the multiprocessing resource_tracker (no separate spawn-worker PIDs hold the VRAM), so _bounded_shutdown's force-terminate of transcript_process/reader_process has nothing to reclaim. Per the PRP's explicit Critical #1/#5 + Anti-Pattern #1, this is a production bug to REPORT, not fix: I did NOT weaken the T6(d-gone) assertion or touch voice_typing/*. The test correctly exits 1 (T6_OK=1) with a fail-loud diagnostic; every other clause (T6 a/b/c/d-reload, T4/criterion-5 at 1.67% CPU, criterion 6/8) PASSES. The idle-unload production path needs fixing so it actually releases the residual ~258 MiB CUDA context on the daemon process."
}
```

## Instructions

Review this feedback and create a revised PRP that addresses the issue.
If the issue is fundamentally impossible to resolve, output `"result": "fail"` with an explanation.
