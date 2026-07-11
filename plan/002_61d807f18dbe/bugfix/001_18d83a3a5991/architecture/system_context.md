# System Context — Bugfix 001 (Production QA Defects)

## Scope

End-to-end creative QA of the voice-typing implementation surfaced **1 Critical**
and **3 Minor** defects. This document maps the system architecture relevant to all
four issues and how they interconnect.

## Architecture Overview

```
User hotkey (Hyprland)
    │
    ▼
voicectl (voice_typing/ctl.py)  ──control socket──▶  VoiceTypingDaemon (voice_typing/daemon.py)
                                                         │
                              ┌──────────────────────────┼──────────────────────┐
                              ▼                          ▼                      ▼
                    RealtimeSTT AudioToTextRecorder   TypingBackend          state.json
                    (faster-whisper + ctranslate2)    (wtype → ydotool)    (XDG_RUNTIME_DIR/
                              │                                              voice-typing/)
                              ▼                                                    │
                    huggingface_hub model cache                           status.sh (jq read)
                    (~/.cache/huggingface/hub)                                 (tmux status-right)
```

### Process Launch Chain (the Issue 1 / Issue 4 target)

```
systemd/voice-typing.service  (no Environment= directives)
    │  ExecStart=
    ▼
voice_typing/launch_daemon.sh  (the SANCTIONED env wrapper)
    │  export LD_LIBRARY_PATH=...  (CUDA libs — already present)
    │  export HF_HUB_OFFLINE=1     ← MISSING (Issue 1 fix adds this)
    │  export TRANSFORMERS_OFFLINE=1 ← MISSING (Issue 1 fix adds this)
    │  exec "$PY" -m voice_typing.daemon
    ▼
Python daemon process (inherits all exported env vars via execve)
```

**Key design invariant:** the systemd unit intentionally has NO `Environment=` directives
(verified: `systemctl --user show voice-typing -p Environment` returns empty). The launch
wrapper is the **single source of truth** for the daemon process environment — this is
the established pattern (LD_LIBRARY_PATH already lives there, with an explicit "DO NOT add
Environment=LD_LIBRARY_PATH" comment in the unit). The offline env vars MUST follow the
same pattern.

## Issue-to-Code Mapping

| Issue | Severity | File(s) | Fix Site | Root Cause |
|-------|----------|---------|----------|------------|
| 1: Runtime network calls | **Critical** | `voice_typing/launch_daemon.sh` | Add 2 export lines before `exec` | Missing `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` → huggingface_hub makes freshness HEAD/GET to huggingface.co on every startup |
| 2: status.sh exit code | Minor | `voice_typing/status.sh` | Append `exit 0` after jq call | No explicit `exit 0` → jq's non-zero exit propagates, violating the documented "exit 0 (never abort)" contract |
| 3: Mic probe on every arm | Minor | `voice_typing/daemon.py` (`_refresh_mic_status`) | Add TTL cache to probe | `_arm()` → `_refresh_mic_status()` → `_probe_mic()` runs full PyAudio init+enumerate (~40 ms) while holding `self._lock` on every arm |
| 4: install.sh offline | Minor | `install.sh` | Add post-restart journal grep + summary line | install.sh doesn't assert the installed service runs offline (resolved primarily by Issue 1 fix) |

## Issue Interconnections

- **Issue 1 ↔ Issue 4** are the SAME fix area. Issue 1 is the code fix (launch_daemon.sh);
  Issue 4 is the install-time confirmation. Once Issue 1 lands, install.sh needs no code
  change to the service (it copies the unit + wrapper), but SHOULD add a post-install
  assertion that the running daemon makes no network calls.
- **Issue 1 ↔ test masking**: `tests/test_idle_and_gpu.sh` line 206 pre-sets
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` before launching the daemon, which HIDES the
  production defect. The regression guard must close this circular-proof gap by either
  (a) removing the pre-set and relying on launch_daemon.sh's exports, or (b) asserting
  the variable flows through the wrapper.
- **Issue 2 ↔ Issue 3** are independent of each other and of Issue 1/4.
- **Issue 3's fix** preserves the mic-health surface in `voicectl status` (the `_mic_ok` /
  `_mic_error` fields) — the TTL cache just avoids re-probing within the window.

## Key Constraints

1. **No `Environment=` in the systemd unit** — all runtime env vars go in launch_daemon.sh.
2. **`import voice_typing.daemon` must stay pure** — `_probe_mic` imports pyaudio lazily
   (inside the method), not at module top. The TTL fix must not change this.
3. **All `_arm`/`_disarm`/`_refresh_mic_status` calls happen under `self._lock`** (or in
   `__init__`, single-threaded). The TTL cache fields are lock-protected for free — no
   extra locking needed.
4. **`time` is already imported** in daemon.py (line 76); `time.monotonic()` is used in
   9+ places. The existing `_fixed_clock(monkeypatch, t)` test helper freezes it
   deterministically.
5. **Offline tradeoff**: setting `HF_HUB_OFFLINE=1` removes the daemon's lazy-download
   self-heal. An uncached model now raises `LocalEntryNotFoundError` at construction
   (fail-fast crash-loop) instead of silently downloading. This is the INTENDED design
   (models are prefetched by install.sh → prefetch.py).

## Test Architecture

| Test File | Type | Runs In | What It Covers |
|-----------|------|---------|----------------|
| `tests/test_systemd_unit.py` | Static (pytest) | Fast suite | Greps unit file text for ExecStart/ExecStartPre/Restart directives |
| `tests/test_daemon.py` | Unit (pytest) | Fast suite | Mic probe injection, _arm/_disarm, TTL-ready (`_fixed_clock` helper exists) |
| `tests/test_idle_and_gpu.sh` | Integration (bash) | Manual (heavy) | Real daemon, CUDA, 120s idle, GPU residency, offline (criterion 8) |
| `tests/ACCEPTANCE.md` | Evidence doc | Manual | Paste-target for acceptance evidence blocks |

**Gap identified**: no test exercises the *production-path* network behavior (Issue 1's
masking). No test exists for `status.sh` (Issue 2). Both need regression guards.
