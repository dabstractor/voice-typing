# Test Results — P1.M5.T1.S2: daemon + recorder_host unit tests (mocked CUDA)

**Date:** 2026-07-18
**Scope:** the 2 mocked-CUDA unit-test files (daemon lifecycle + recorder-host IPC). **Excludes** the 9
pure-Python files (P1.M5.T1.S1, parallel) and test_feed_audio.py (P1.M5.T2, real CUDA models).
**Verdict:** ✅ GREEN — 219 passed, 0 failed, 0 errors, 0 skipped.

## Command run (AGENTS.md two-timeout discipline)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q
# (bash-tool outer `timeout` set to 320 — the backstop above the inner 300.)
```

## Per-file results

| file | tests | result | module under test | PRD ref | acceptance |
|---|---|---|---|---|---|
| test_daemon.py | 193 | ✅ pass (~3.3s) | voice_typing.daemon (lifecycle, lazy load, drain, idle-unload, lite, status) | §4.2/§4.2bis/§4.2ter/§4.4/§4.5/§4.6/§4.9 | #2,#4,#5,#6,#9,#10 |
| test_recorder_host.py | 26 | ✅ pass (~1.5s) | voice_typing.recorder_host (IPC dispatch, queues, teardown, abort sentinel) | §4.2bis | #2,#6,#9 |
| **TOTAL** | **219** | **✅ all pass (4.79s)** | | | |

Per-file counts and timings re-measured LIVE at execution (not copied from the PRP):
- `test_daemon.py` → `193 passed in 3.27s`, exit 0
- `test_recorder_host.py` → `26 passed in 1.53s`, exit 0
- combined 2-file run → `219 passed in 4.79s`, exit 0

## Acceptance-criteria evidence (this item is the primary unit-level coverage)

- **#2** (pause ≥3 s loses zero words, drain) — daemon drain tests + recorder_host abort-sentinel tests.
- **#4** (only finalized text typed; nothing when toggled off) — on_final gate tests.
- **#5** (idle silence, no hallucination) — idle-watchdog + hallucination-reject tests (unit guards;
  full 2-min silence = PRD T4 / P1.M5.T4).
- **#6** (voicectl cmds, systemd, boots un-armed + un-loaded ~0 VRAM, auto-restart) — lazy-boot +
  status + signal-handler + main-lifecycle + dead-child tests.
- **#9** (idle-unload ~0 VRAM, bounded teardown, no 90 s hang) — idle-unload + bounded-shutdown +
  single-flight + concurrent-stop tests.
- **#10** (lite mode) — toggle-lite + mode-switch + status-mode tests.

## Fixes applied

_None._ The suite was green on first run (219 passed in 4.79s, exit 0). No source or test file was
modified. (If a failure had surfaced, record it here as: `file | change | root-cause class (A-E) |
test unblocked`.)

## Notes

- Wall time ~4.8s confirms both modules keep CUDA out of module scope (daemon.py lazy-imports RealtimeSTT
  at line 341; recorder_host.py is lazy by design at line 54) and the tests inject fakes — no model load.
- Import-purity spot-check passed: importing `voice_typing.daemon` + `voice_typing.recorder_host` did NOT
  bring `RealtimeSTT`, `torch`, or `ctranslate2` into `sys.modules` (`CUDA-at-import leak: none`).
- No drift-guard tests here (unlike S1); a failure would be a logic/fixture/threading regression, not a
  committed-file drift.
- Out of scope (other leaves): 9 pure-Python files → P1.M5.T1.S1 (parallel); test_feed_audio.py → P1.M5.T2.