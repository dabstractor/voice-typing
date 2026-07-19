# Test Results — P1.M5.T1.S1: pure-Python unit tests (no CUDA)

**Date:** 2025-01-24
**Scope:** the 9 pure-Python unit-test files (config, textproc, typing_backends, feedback, voicectl,
control socket, status_sh, systemd). **Excludes** test_daemon.py / test_recorder_host.py (P1.M5.T1.S2,
mocked CUDA) and test_feed_audio.py (P1.M5.T2, real CUDA models).
**Verdict:** ✅ GREEN — 196 passed, 0 failed, 0 errors, 0 skipped.

## Command run (AGENTS.md two-timeout discipline)

```bash
timeout 120 .venv/bin/python -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_feedback.py tests/test_voicectl.py \
  tests/test_control_socket.py tests/test_status_sh.py tests/test_systemd_unit.py -q
# (bash-tool outer `timeout` set to 150 — the backstop above the inner 120.)
```

**Live result:** `196 passed in 4.70s`, exit 0.

## Per-file results

| file | tests | result | module under test | PRD ref |
|---|---|---|---|---|
| test_config.py | 34 | ✅ pass | voice_typing.config | §4.5 |
| test_config_repo_default.py | 3 | ✅ pass | config.toml ↔ dataclass drift guard | §4.5 |
| test_textproc.py | 21 | ✅ pass | voice_typing.textproc.clean | §4.7 / T2 |
| test_typing_backends.py | 27 | ✅ pass | voice_typing.typing_backends | §4.3 |
| test_feedback.py | 38 | ✅ pass | voice_typing.feedback | §4.6 |
| test_voicectl.py | 32 | ✅ pass | voice_typing.ctl | §4.8 |
| test_control_socket.py | 21 | ✅ pass | voice_typing.daemon.ControlServer | §4.2#3 |
| test_status_sh.py | 5 | ✅ pass | voice_typing/status.sh | §4.6 |
| test_systemd_unit.py | 15 | ✅ pass | systemd/voice-typing.service + install.sh + hypr-binds.conf | §4.9 |
| **TOTAL** | **196** | **✅ all pass (4.70s)** | | |

Per-file isolation run (each file run individually) confirmed every file green with the expected count:
34 / 3 / 21 / 27 / 38 / 32 / 21 / 5 / 15, each completing in well under 1s except the socket round-trip
files (voicectl 2.18s, control_socket 2.73s — expected, they exercise a real AF_UNIX socket + thread).

## Fixes applied

_None._ The suite was green on first run (196 passed in 4.70s, exit 0). No source or test file was
modified. (If a failure had surfaced, record it here as: `file | change | root-cause class (A-E) |
test unblocked`.)

## Notes

- Wall time 4.70s confirms every file is genuinely pure-Python (a CUDA/model load would add minutes).
- Drift guards (config_repo_default / status_sh / systemd_unit) READ committed files — green = no drift
  between audit and execution.
- Import-purity spot-check (Level 4): importing the pure-Python layer
  (`config`, `textproc`, `typing_backends`, `feedback`, `ctl`, `daemon`) pulled in NONE of
  `RealtimeSTT` / `torch` / `ctranslate2` — no CUDA leak at import.
- Scope-boundary check (Level 4): `--collect-only` on the 9-file set reports exactly `196 tests
  collected`; test_daemon.py / test_recorder_host.py / test_feed_audio.py were NOT added to this run.
- Out of scope (other leaves): test_daemon.py (193) + test_recorder_host.py (26) → P1.M5.T1.S2;
  test_feed_audio.py (9) → P1.M5.T2.