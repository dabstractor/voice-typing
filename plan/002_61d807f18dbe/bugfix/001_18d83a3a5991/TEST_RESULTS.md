# Bug Fix Requirements

## Overview

Creative end-to-end QA of the voice-typing implementation against the PRD. Testing covered: the full control-socket protocol lifecycle (toggle/start/stop/status/quit) with a real daemon + fake recorder, malformed/adversarial socket inputs, 50 concurrent clients + concurrent toggle spam, textproc edge cases (unicode/emoji/whitespace/blocklist/min_chars), config loading (unknown keys, wrong types, malformed TOML), typing-backend command construction + wtype→ydotool fallback, voicectl CLI exit codes (0/1/2/64), device-resolution paths (cuda/cpu/force_cpu), feedback throttle, idle auto-stop (enable/disable/fire), status.sh tmux helper, the live production systemd daemon, the live journal, and the heavy offline T1 feed_audio integration suite (all 7 tests pass — the core pause-keeps-listening requirement is verified working).

**Overall assessment:** The implementation is exceptionally thorough and well-tested. All 269 unit tests pass; T1 (the core WhisperX-flaw regression) passes; the live daemon runs correctly on CUDA, boots un-armed, reports correct state, and holds models resident in VRAM. The typing backends, control socket, config loader, and textproc are robust against every adversarial input I tried.

**However, one Critical defect was found:** the production daemon makes **network calls to huggingface.co on every startup**, directly violating PRD §1 ("100% local. No network calls at runtime") and acceptance criterion §7.8 ("No network access needed at runtime"). The T4 idle test *masks* this by forcing `HF_HUB_OFFLINE=1`, so the defect is invisible to the existing test suite and ships into production. A few minor polish items are also documented below.

---

## Critical Issues (Must Fix)

### Issue 1: Production daemon makes network calls at runtime (violates "100% local", PRD §1 + acceptance criterion §7.8)

**Severity**: Critical
**PRD Reference**: §1 ("100% local. No network calls at runtime (model downloads at install time are fine)"), §7 acceptance criterion 8 ("No network access needed at runtime (models cached by install)"), §4.9 (systemd unit). README lines 3 & 6 ("Fully-local voice typing", "nothing is sent to a cloud").

**Expected Behavior**: The daemon must run with zero network access at runtime. Models are prefetched at install time (install.sh → prefetch.py → `~/.cache/huggingface`), so the daemon must load them from cache with no network calls. This is an explicit acceptance criterion that must be true of the *deployed* systemd service, not just a test harness.

**Actual Behavior**: The production systemd service (`voice-typing.service` → `launch_daemon.sh`) does **not** set `HF_HUB_OFFLINE=1` (or `TRANSFORMERS_OFFLINE=1`). As a result, faster-whisper / huggingface_hub performs an online model-revision check on every startup, issuing HTTP GET requests to `https://huggingface.co`. The live journal proves this — two requests per startup, one per model, across every daemon restart observed:

```
Jul 11 14:47:37 ... HTTP Request: GET https://huggingface.co/api/models/Systran/faster-distil-whisper-large-v3/revision/main "HTTP/1.1 200 OK"
Jul 11 14:47:37 ... HTTP Request: GET https://huggingface.co/api/models/Systran/faster-whisper-small.en/revision/main "HTTP/1.1 200 OK"
```

Six such requests appear in the last 2 hours of journal (3 startups × 2 models). `systemctl --user show voice-typing -p Environment` returns `Environment=` (empty), and `/proc/<daemon-pid>/environ` contains no `HF_*`/offline variables.

**Why this matters (impact)**:
1. **Privacy**: every daemon startup phones home to huggingface.co, leaking that the user runs these specific Whisper models. The README explicitly promises "nothing is sent to a cloud" — that promise is false as shipped.
2. **Offline-startup risk**: with no network, huggingface_hub's online revision check must fail/time out before falling back to cache. Depending on the huggingface_hub version and local cache metadata, this can add tens of seconds of startup latency or, in failure modes, raise `LocalEntryNotFoundError`/`OSError` and crash the unit (which then `Restart=on-failure` loops). The whole point of the project is an always-available *local* dictation daemon.
3. **Acceptance criterion failure**: PRD §7.8 is a definition-of-done item. As deployed, the daemon does NOT meet it. The deliverable is not actually "done" per its own spec.

**Why the existing tests missed it (the masking)**: `tests/test_idle_and_gpu.sh` *does* set `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` (its `G-OFFLINE` invariant, line 206) and even asserts `[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 ...`. But that only proves the daemon *can* run offline — it does NOT assert the *production* unit runs offline. The test forces offline mode, so it never observes the production network calls. The criterion-8 "proof" is therefore circular: it passes because the test itself supplies the variable that production omits. No test exercises the real `systemctl --user start voice-typing` path for network behavior.

**Steps to Reproduce**:
1. Confirm models are cached: `ls ~/.cache/huggingface/hub/` → `models--Systran--faster-distil-whisper-large-v3` and `models--Systran--faster-whisper-small.en` are present (prefetched by install.sh).
2. Restart the production service: `systemctl --user restart voice-typing`.
3. Read the journal: `journalctl --user -u voice-typing -n 40 --no-pager | grep "HTTP Request"`.
4. Observe: `HTTP Request: GET https://huggingface.co/api/models/...` lines appear (one per model). These are runtime network calls made *after* install-time prefetch, while models are already on disk.

**Suggested Fix** (one-line, proven safe): export the offline env vars in `voice_typing/launch_daemon.sh` (the sanctioned single place for daemon-process environment, per the existing LD_LIBRARY_PATH pattern), so both the systemd unit and any manual launch inherit them:

```bash
# In launch_daemon.sh, before `exec "$PY" -m voice_typing.daemon`:
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

Both models are already cached (verified), and I confirmed the recorder constructs cleanly under exactly these two variables with **zero** `HTTP Request` log lines and no errors:
```
constructing recorder OFFLINE...
OFFLINE construction OK — models load from cache, zero network
```
(Prefetch already sets `HF_HUB_DISABLE_TELEMETRY=1`; the two `*_OFFLINE` vars complete the no-network guarantee.) Do NOT also bake the variables into the systemd unit's `Environment=` — keep the launch wrapper as the single source (consistent with the existing LD_LIBRARY_PATH design and the unit's own "DO NOT add Environment=LD_LIBRARY_PATH" comment).

**Recommended regression guard**: add an assertion that greps the daemon journal for `HTTP Request: GET https://huggingface.co` after a *production-path* start and fails if any are found — i.e. a test that does NOT pre-set `HF_HUB_OFFLINE` itself but instead invokes the real `launch_daemon.sh` (or sets it and asserts the variable flows through). This closes the circular-proof gap that let the bug ship.

---

## Major Issues (Should Fix)

None beyond Issue 1. (The related test-masking is documented under Issue 1 as it shares the single root cause and the same fix path.)

---

## Minor Issues (Nice to Fix)

### Issue 2: `status.sh` exits non-zero on missing/corrupt state.json, contradicting its own documented contract

**Severity**: Minor
**PRD Reference**: §4.6 (tmux status helper); `voice_typing/status.sh` header comment.

**Expected Behavior**: The script's own header comment states: *"NO `set -e`: a missing or malformed state.json must print an empty line with exit 0 (never abort) — otherwise tmux would show an error string in status-right."*

**Actual Behavior**: The script correctly prints an empty line on failure (good), but exits with the **jq exit code** (non-zero): exit 2 when the state file is absent, exit 5 when the JSON is corrupt. Verified:
```
$ XDG_RUNTIME_DIR=/tmp/empty voice_typing/status.sh; echo "exit=$?"   # no state file
[no output]
exit=2
$ echo 'not json{{}' > state.json && voice_typing/status.sh; echo "exit=$?"   # corrupt JSON
exit=5
```
**Impact**: negligible for the documented use case — tmux's `#(...)` substitution captures stdout and ignores the exit code, so the status line still renders blank on failure. The defect is the broken self-documented contract (the comment promises exit 0). A non-tmux caller (e.g. a script that checks `$?`) would be misled.

**Steps to Reproduce**: `XDG_RUNTIME_DIR=$(mktemp -d) voice_typing/status.sh; echo $?` → prints `2`.

**Suggested Fix**: end `status.sh` with an explicit `exit 0` after the `jq` call (or `jq ... "$STATE" 2>/dev/null || true`), so the script honors its documented "exit 0 (never abort)" contract. Optionally also soften the comment's "otherwise tmux would show an error string" claim (tmux ignores exit codes in `#(...)`).

### Issue 3: Synchronous PyAudio mic probe runs on every arm while holding the daemon lock (~40 ms)

**Severity**: Minor
**PRD Reference**: §4.2 ("construct once … instant toggle-on"); mic-health probe added as bugfix Issue 2.

**Expected Behavior**: Arming the mic (`voicectl start` / `toggle` → on) should feel instant (PRD §4.2 "instant toggle-on").

**Actual Behavior**: `_arm()` calls `_refresh_mic_status()` → `_probe_mic()` on every arm, which does `import pyaudio; pa = pyaudio.PyAudio(); <enumerate>; pa.terminate()`. Measured at ~39–43 ms per arm (vs ~4 ms with the probe stubbed out), and it runs **while holding the daemon `_lock`**, so it serializes all concurrent control commands. For a single user pressing a hotkey this is imperceptible (~40 ms). Under unrealistic adversarial load (5 processes spamming toggle concurrently) throughput collapses and connections time out, because every arm re-probes PyAudio/ALAS under the lock. (Disarm is fast, ~3 ms — no probe.)

**Steps to Reproduce (single-user, benign)**: time a toggle that arms vs one that disarms against the live daemon — arm is ~10× slower due to the probe. (Adversarial stall requires concurrent multi-process toggle spam and is not a realistic single-user scenario.)

**Suggested Fix**: cache the probe result for a short TTL (e.g. re-probe at most once every ~30 s, or only when a prior probe failed / `mic_error` is set), or move the probe off the lock / into the idle watchdog. This preserves the mic-health surface in `voicectl status` without paying the PyAudio-init cost on every keystroke.

### Issue 4: `install.sh` does not reflect the no-network requirement / does not set offline env for the installed unit

**Severity**: Minor (closely related to Issue 1 — same fix area)
**PRD Reference**: §5 (install steps), §7.8.

**Expected Behavior**: Since the project's headline requirement is "100% local, no network at runtime", the installer should ensure the installed service runs offline.

**Actual Behavior**: `install.sh` prefetches models (good) and `prefetch.py` sets `HF_HUB_DISABLE_TELEMETRY=1` (good), but neither install.sh, prefetch.py, the systemd unit, nor launch_daemon.sh set `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` for the *runtime* daemon. (Issue 1 is the user-visible consequence.) Once Issue 1's launch-wrapper fix lands, install.sh needs no other change (it copies the unit and the wrapper is in-tree), but a line in install.sh's summary confirming "daemon runs fully offline" would close the loop on the documented promise.

**Suggested Fix**: resolved by the Issue 1 fix (the wrapper carries the env vars). Optionally add a post-install journal grep in install.sh that asserts no `HTTP Request: GET https://huggingface.co` lines appear after the first restart.

---

## Testing Summary

- **Total tests performed**: ~120 manual/adversarial probes across 10 dimensions + the 269-test pytest suite + the 7-test T1 feed_audio integration suite.
- **Passing**: 269/269 unit tests; 7/7 T1 integration tests; ~118/120 manual probes. The live production daemon starts, runs on CUDA, boots un-armed, reports correct state.json (matches PRD §4.6 format exactly), and holds models resident (~2.8 GB VRAM, within the PRD's ~1–5 GB target).
- **Failing**: 1 Critical (Issue 1: runtime network calls). 3 Minor (Issues 2–4).
- **Areas with good coverage**: control-socket protocol & malformed inputs; textproc (unicode/emoji/blocklist/min_chars); config loader (unknown keys/types/malformed TOML); typing-backend command construction & fallback; voicectl exit codes; device resolution (cuda/cpu/force_cpu); the core pause-keeps-listening requirement (T1); GPU residency; un-armed boot; clean shutdown + VRAM release.
- **Areas needing more attention**: **production-path network behavior** (Issue 1 — the test suite's forced-offline T4 hides the production defect; a regression test that exercises the real launch_daemon.sh path without pre-setting the offline vars is needed). Test fidelity of T4's "120 s listening" claim vs the 30 s `auto_stop_idle_seconds` default is also worth noting — the idle test only exercises ~30 s of *active* listening before auto-stop disarms (the production code is correct per §4.5; this is a test-fidelity gap, not a code bug, and the implementer consciously documented the interaction).
