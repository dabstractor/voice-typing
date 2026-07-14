# Research — dead recorder-host child recovery (P1.M2.T2.S1 / bugfix Issue 3)

This note pins the defect, the exact edit sites, the no-breakage proof, the
design decisions (no host.stop(); pid log in run()), and the validated feature
behavior. The PRP (../PRP.md) references it as the single source of truth.

## 1. The defect (bugfix Issue 3, bug_analysis.md §Issue 3)

`run()` (daemon.py:739) checks `self._host is None` but **never `host.is_alive`**.
When the recorder-host child crashes (CUDA OOM / segfault / OOM-killer):
1. `self._host` is still the (dead) host object (not None), `_listening` True,
   `_models_loaded` True.
2. `host.text()` returns immediately (dead child → `_dead=True`).
3. After 30 s auto-stop, `_models_loaded` STAYS True.
4. Next `start()` → `_load_host()` short-circuits on `if self._models_loaded:
   return True` → dead host reused → voice typing silently + permanently broken
   until `voicectl quit` + restart.

`RecorderHost.is_alive` (recorder_host.py:~135) ALREADY exists and correctly
returns False when `_proc is None / not proc.is_alive() / _dead is True`.
`_handle_dead_host()` does NOT exist yet.

## 2. Task boundary (S1 vs S2 vs S3)

- **S1 (THIS task):** run() liveness check + `_handle_dead_host()` recovery method.
- **S2 (P1.M2.T2.S2):** `_load_host()` early-return guard →
  `if self._models_loaded and self._host is not None and self._host.is_alive: return True`
  (defense-in-depth — separate task).
- **S3 (P1.M2.T2.S3):** committed pytest (dead-child detection, recovery, status).
- **P1.M2.T1.S2 (parallel):** `tests/test_daemon.py` phase-after-disarm tests.
- **P1.M2.T1.S1:** `_disarm()` set_phase('idle') line (daemon.py:~875).

S1 ALONE fixes the run()-detected case: `_handle_dead_host()` sets
`_models_loaded=False`, so `_load_host()`'s existing `if self._models_loaded`
guard does NOT short-circuit → the next arm re-spawns. S2's is_alive guard is
complementary (covers races where the host dies between the run() check and the
arm). Do NOT do S2/S3 work here.

## 3. Exact edit sites in `voice_typing/daemon.py`

### 3.1 `run()` while-loop (line 739) — add liveness check at the TOP of the body
Current:
```
739:        while not self._shutdown.is_set():
740:            if self._host is None:
741:                time.sleep(0.05)   # no models loaded yet → idle, ~0 VRAM (PRD §4.2(1)/§4.2bis)
742:                continue
```
Insert the liveness check BEFORE `if self._host is None` (item LOGIC (b), verbatim):
`if self._host is not None and not self._host.is_alive:` → log WARNING with pid
(via `getattr(self._host, "pid", "?")`) → `self._handle_dead_host()` → `continue`.

### 3.2 NEW `_handle_dead_host()` — place AFTER `run()` (before `_configure_log_level`)
Anchor: `logger.info("shutdown requested; run() loop exiting")\n\n    def
_configure_log_level`. Cleanup UNDER `self._lock` (item LOGIC (a), verbatim):
`self._host=None; _models_loaded=False; _listening.clear();
feedback.set_phase("unloaded"); feedback.set_models_loaded(False);
feedback.set_listening(False); _load_error="recorder-host child died
unexpectedly"; _disarmed_monotonic=None; _last_speech_monotonic=None`.

## 4. ★ DESIGN DECISIONS ★

### 4.1 The pid-bearing WARNING lives in run(), NOT in `_handle_dead_host()`
The item lists "Log a WARNING with the dead host's pid" under BOTH (a) the method
and (b) the run() code. They cannot both log without double-logging, AND the pid
is only readable BEFORE `_handle_dead_host()` sets `self._host=None` (after that,
`self._host` is None → pid="?"). Resolution: the WARNING (with pid) goes in run()
(item (b)'s verbatim code, where `self._host` is still the dead host);
`_handle_dead_host()` is PURE cleanup (no log). This is the literal reading of
(b) and avoids both problems. (Documented in the PRP gotcha.)

### 4.2 `_handle_dead_host()` does NOT call `host.stop()` (the child is already dead)
The structural analog `_unload_host()` (daemon.py:~975) calls `self._host.stop()`
to tear down a LIVE child. But here the child is ALREADY dead (`is_alive` False →
`_dead=True` / proc gone), so there is nothing to tear down, and `stop()` on a
dead host could block or error. `_handle_dead_host()` only DROPS the reference +
resets state. The dead host's reader thread exits on its own when the dead pipe
closes (RecorderHost handles pipe EOF/errors). Mirrors `_unload_host()`'s
CLEANUP half, minus the teardown.

### 4.3 Composes with idle-unload (no conflict)
`_unload_host()` re-checks `not self._models_loaded` as its FIRST under-lock
condition. Since `_handle_dead_host()` sets `_models_loaded=False`, a racing
`_unload_host()` no-ops. And `_handle_dead_host()` clears `_disarmed_monotonic`,
so the idle-unload clock resets too. No double-teardown, no deadlock.

### 4.4 Detection latency
The check runs at the TOP of every while-iteration. When idle/disarmed the loop
sleeps 0.05 s → detection within ~50 ms. When listening + blocked in `text()`,
the dead child makes `text()` return IMMEDIATELY (`_dead=True`) → next iteration's
top check catches it (sub-50 ms). So the "~50 ms" claim holds for both paths.

## 5. ★ NO-BREAKAGE PROOF (validated live) ★

The risk: `_FakeHost._alive` defaults to **False** (test_daemon.py:459) and
`is_alive` returns it; if a run-loop test injected such a host, the new check
would fire `_handle_dead_host()` and nuke it. Verified NOT the case:
- **All run-loop tests** (`test_stop_while_run_loop_idle…`, `test_run_loop_not_
  listening…`, `test_run_loop_calls_text…`, the SIGTERM-race test, etc.) call
  `_make_daemon()` with NO `recorder_host=` → inject `recorder=_StubRecorder()`
  → wrapped in `_LegacyRecorderHostAdapter` whose `is_alive` returns **True
  always** → `not self._host.is_alive` is always False → the check is DORMANT.
- **The `recorder_host=` tests** (`_CountingHost`/`_GatedHost`/`_FakeHost` at
  1635+, the lazy-load tests) do NOT call `d.run()` (they drive
  `request_shutdown()`/`shutdown()`/`_load_host()` directly) → the check never
  fires.
- `_LegacyRecorderHostAdapter` HAS `is_alive` (→True) and `pid` (→None), so
  `self._host.is_alive` and `getattr(self._host,"pid","?")` never AttributeError
  on an injected-recorder daemon.

**Empirical proof:** applied both edits to a full-repo scratch copy →
`.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` →
**345 passed** (baseline 345). Zero regressions.

## 6. ★ FEATURE-BEHAVIOR PROOF (validated live, throwaway test) ★

Injected a `_KillableHost` (is_alive flips to False) via `recorder_host=`, ran
`d.run()` in a thread, armed, killed the host, polled. Confirmed:
- WARNING logged: `recorder-host child (pid=12345) died; transitioning to unloaded`.
- `d._host is None` ✓  `d._models_loaded is False` ✓  `d.is_listening() is False` ✓
  (cleared — died WHILE listening)  `d._load_error == "recorder-host child died
  unexpectedly"` ✓  `fb.phases[-1] == "unloaded"` ✓  `fb.listening_states[-1] is
  False` ✓  `_disarmed_monotonic is None` + `_last_speech_monotonic is None` ✓.
- Clean shutdown after recovery (`request_shutdown()` → run() thread exits).

(The throwaway assertion `fb.models_loaded[-1]` failed ONLY because the
`_FakeFeedback.set_models_loaded` stub is a **no-op** in this bugfix instance —
it does not record to a list. The daemon's `set_models_loaded(False)` call itself
succeeds. S3's committed tests assert `models_loaded` via the REAL Feedback /
state.json, not the stub. Not a daemon defect.)

## 7. Attrs/lock facts (verified)

- `self._lock` is set in `VoiceTypingDaemon.__init__` (used by `_load_host`/
  `_unload_host`/`Condition(self._lock)` at ~596). `_handle_dead_host()` uses
  `with self._lock:` like its siblings.
- All cleared/reset attrs exist: `_host` (585-591), `_models_loaded` (593),
  `_listening` (548), `_load_error` (595), `_disarmed_monotonic` (575),
  `_last_speech_monotonic` (570), `_feedback`.
- The construction (603-605) already calls `set_phase` + `set_models_loaded`
  (P1.M2.T2.S1 landed) → the feedback surface `_handle_dead_host()` uses exists.

## 8. Tooling & validation (verified)

- pytest 9.1.1 in `.venv`; baseline fast suite = **345 passed**.
  `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`.
- ruff 0.14.13 at `/home/dustin/.local/bin/ruff` (NOT in .venv); optional lint.
- mypy NOT installed — do NOT list it. FULL paths (zsh aliases).

## 9. Scope boundaries (do / don't)

DO: edit `voice_typing/daemon.py` ONLY — run() liveness check + `_handle_dead_host()`.
DON'T: edit `_load_host()` (S2), write committed tests (S3), edit `test_daemon.py`
(P1.M2.T1.S2, parallel), edit `_disarm()` (P1.M2.T1.S1), edit `recorder_host.py`
(`is_alive` already works), edit `feedback.py`/`config.py`/README, call
`host.stop()` from `_handle_dead_host()` (child already dead). No new deps. No
`PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.
