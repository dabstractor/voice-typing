# Issue Analysis & Fix Design — Bugfix 001

## Issue 1 (Critical): Production daemon makes network calls at runtime

### Root Cause
`voice_typing/launch_daemon.sh` does NOT export `HF_HUB_OFFLINE=1` or
`TRANSFORMERS_OFFLINE=1`. As a result, when faster-whisper resolves its model
short-names (`distil-large-v3`, `small.en`) via `huggingface_hub.snapshot_download`,
huggingface_hub runs in ONLINE mode and makes a freshness-check HTTP GET to
`https://huggingface.co/api/models/<repo>/revision/main` for each model — even
though the models are fully cached locally. The journal proves this: 2 requests
per startup (one per model).

### Fix Design
**File:** `voice_typing/launch_daemon.sh`
**Location:** Before `exec "$PY" -m voice_typing.daemon "$@"` (line 60, the
final line of the file).

Insert two export lines:
```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

**Why here (not the systemd unit):**
- The systemd unit has NO `Environment=` directives by design — the unit comment
  explicitly says "DO NOT add `Environment=LD_LIBRARY_PATH=...`".
- The launch wrapper is the sanctioned single source for the daemon's process
  environment (the LD_LIBRARY_PATH pattern already lives here).
- `export` before `exec` ensures the env vars are inherited by the Python process
  via `execve` (same mechanism as LD_LIBRARY_PATH). `huggingface_hub` reads
  `HF_HUB_OFFLINE` at IMPORT TIME into `constants.HF_HUB_OFFLINE`, so the env
  must be set before the interpreter starts — exactly what the wrapper does.

**Why both vars:**
- `HF_HUB_OFFLINE=1` is the AUTHORITATIVE flag — it makes ALL huggingface_hub
  calls cache-only (skips freshness HEAD/GET, no downloads, no telemetry). This
  is sufficient for faster-whisper (which has no `transformers` dependency).
- `TRANSFORMERS_OFFLINE=1` is harmless belt-and-suspenders (no-op for
  faster-whisper today, but guards against a future dependency pulling in
  transformers).

### Behavior Change (Tradeoff)
With `HF_HUB_OFFLINE=1`, an UNcached model now raises `LocalEntryNotFoundError`
at construction (fail-fast crash → systemd `Restart=on-failure` loop) instead of
silently downloading. This is the INTENDED design: models are prefetched at
install time (`install.sh` → `prefetch.py`). The daemon should NOT auto-download
at runtime — that would violate the "100% local, no network" requirement.

### Regression Guards Needed
1. **Static drift-guard** (fast pytest): grep `launch_daemon.sh` for both export
   lines — mirrors the existing `test_systemd_unit.py` text-grep pattern.
2. **Close the circular-proof gap**: `tests/test_idle_and_gpu.sh` line 206
   currently pre-sets `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` before launching
   the daemon. This HIDES the production defect. Fix: remove the pre-set, rely
   on launch_daemon.sh's exports, and add a journal grep asserting NO
   `HTTP Request: GET https://huggingface.co` lines appear after startup.

---

## Issue 2 (Minor): status.sh exits non-zero on missing/corrupt state.json

### Root Cause
`voice_typing/status.sh` has NO `set -e` and NO explicit `exit 0`. The script's
exit status is therefore the exit status of its last command — the `jq` call
(line 39). When `state.json` is missing or malformed, jq exits non-zero (2 for
missing file, 5 for corrupt JSON), which becomes the script's exit code. This
contradicts the documented contract at lines 23-24: *"must print an empty line
with exit 0 (never abort)"*.

### Fix Design
**File:** `voice_typing/status.sh`
**Location:** After the jq call (line 39).

Append `exit 0` after the jq call. This honors the documented contract.
Optionally soften the comment's "otherwise tmux would show an error string"
claim (tmux's `#(...)` substitution ignores exit codes).

### Regression Guard
Add a new test (pytest or bash smoke) that runs `status.sh` against a missing
state file and a corrupt state file, asserting exit code 0 in both cases.

---

## Issue 3 (Minor): Synchronous PyAudio mic probe on every arm (~40 ms under lock)

### Root Cause
`_arm()` (daemon.py:575-581) calls `_refresh_mic_status()` on every arm.
`_refresh_mic_status()` (daemon.py:633-648) calls the prober, which in
production is `_probe_mic()` (daemon.py:650-672) — a full `import pyaudio;
pa = pyaudio.PyAudio(); <enumerate all devices>; pa.terminate()`. This takes
~39-43 ms and runs WHILE HOLDING `self._lock`, serializing all concurrent
control commands.

### Fix Design
**File:** `voice_typing/daemon.py`
**Approach:** TTL cache — re-probe at most once every N seconds (30s default).

**Implementation:**
1. Add module-level constant `_MIC_PROBE_TTL_S = 30.0` near the top-level constants.
2. Add field `self._mic_probe_at: float = 0.0` in `__init__` next to
   `_mic_ok`/`_mic_error` (lines 453-455). `0.0` = never probed (sentinel
   convention matching `MicRetryRateLimitFilter._last_seen`).
3. Modify `_refresh_mic_status()` to accept `force: bool = False` and gate the
   probe body: only re-probe if `self._mic_probe_at == 0.0` (never) OR
   `time.monotonic() - self._mic_probe_at >= _MIC_PROBE_TTL_S` OR `force`.
4. After a successful probe, stamp `self._mic_probe_at = time.monotonic()`.
5. `__init__`'s call passes `force=True` (always probe at construction).

**Why TTL (not alternatives):**
- "Only re-probe on failure" (if `_mic_error` is set) is simpler but doesn't
  detect a mic being plugged back in after a failure.
- "Move off the lock / into idle watchdog" is more invasive and changes the
  threading model.
- TTL preserves the mic-health surface in `voicectl status` (status updates
  within 30s) while eliminating the per-arm PyAudio cost. Single-user arm goes
  from ~40 ms to ~0 ms (cached).

**Thread safety:** All `_arm`/`_disarm`/`_refresh_mic_status` calls happen
under `self._lock` (or in `__init__`, single-threaded). The cache fields
(`_mic_probe_at`, `_mic_ok`, `_mic_error`) are ONLY ever read/written under the
lock. No extra locking needed.

### Test Impact
- `test_arm_refreshes_mic_status` (test_daemon.py:1506) currently asserts
  `len(calls) == 2` after init + start. With TTL, the 2nd call is cached
  (within window) → must assert `== 1` OR use `force=True`.
- New TTL test: use `_fixed_clock(monkeypatch, t)` (test_daemon.py:1551) to
  advance the clock past the TTL and assert re-probe happens.
- `test_init_initializes_mic_status_and_calls_probe` (line 1495) still passes
  (init uses `force=True`).

---

## Issue 4 (Minor): install.sh does not reflect the no-network requirement

### Root Cause
`install.sh` prefetches models (good) and `prefetch.py` sets
`HF_HUB_DISABLE_TELEMETRY=1` (good), but neither sets
`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` for the runtime daemon. The runtime
fix is Issue 1 (launch_daemon.sh carries the vars). install.sh just needs
a post-install assertion and summary confirmation.

### Fix Design
**File:** `install.sh`
**Location:** After step 4/7 (`systemctl --user restart`, line 116) and in
step 7/7 (summary, line 149).

1. After the restart + a brief sleep for model load, grep the daemon journal
   for `HTTP Request: GET https://huggingface.co` and fail/warn if found.
2. Add a summary line confirming "daemon runs fully offline (HF_HUB_OFFLINE=1)".

This closes the loop: install.sh asserts the deployed service actually honors
the no-network promise, not just that the code is present.

---

## Dependencies Between Fixes

```
Issue 1 (launch_daemon.sh exports)  ────┐
    │                                    ├──▶ Issue 4 (install.sh journal grep
    │                                    │    can only pass if exports are present)
    ▼                                    │
test_idle_and_gpu.sh update ─────────────┘
(circular-proof gap closure relies on Issue 1's exports)

Issue 2 (status.sh)  ─── independent
Issue 3 (mic probe)  ─── independent
```
