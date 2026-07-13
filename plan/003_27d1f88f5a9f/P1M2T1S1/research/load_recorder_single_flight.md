# Research: _load_recorder() single-flight lazy load + CPU-fallback migration (P1.M2.T1.S1)

Target: `voice_typing/daemon.py` — defer recorder construction from boot (`__init__`)
to the first arm (`start`/`toggle`), via a new single-flight `_load_recorder()` method
that also owns the CPU-fallback (migrated out of `main()`). PRD §4.2bis / delta_prd D1/D2.

---

## 1. The 8 recorder call sites that need `None` guards (derived from the code — the contract's codebase_analysis.md §1.5 does not exist in the tree)

`grep -n "self._recorder" voice_typing/daemon.py` yields exactly these use sites (all must survive `self._recorder is None`):

| # | Method (line) | Call | Guard required |
|---|---|---|---|
| 1 | `run()` ~488 | `self._recorder.set_microphone(False)` (boot disarm) | `if self._recorder is not None:` (contract e) |
| 2 | `run()` ~495 | `self._recorder.text(self.on_final)` (loop) | skip whole iteration when None (PRD §4.2(1)) |
| 3 | `_arm()` ~588 | `self._recorder.set_microphone(True)` | `if self._recorder is not None:` |
| 4 | `_disarm()` ~601 | `self._recorder.set_microphone(False)` | `if self._recorder is not None:` |
| 5 | `_maybe_auto_stop()` ~647 | `self._recorder.abort()` (outside lock) | `if self._recorder is not None:` |
| 6 | `stop()` ~727 | `self._recorder.abort()` (outside lock) | `if self._recorder is not None:` |
| 7 | `toggle()` ~741 | `self._recorder.abort()` (outside lock) | `if self._recorder is not None:` |
| 8 | `request_shutdown()` ~751 | `self._recorder.abort()` (outside lock) | `if self._recorder is not None:` |
| (9) | `shutdown()` ~911 | `self._recorder.shutdown()` | **ALREADY guarded** (`if self._recorder is None: return` — the M1 bounded-teardown landed this; do NOT re-add). `_bounded_shutdown` also uses `self._recorder.shutdown()` but is only reached after the None-guard in `shutdown()`. |

So: 8 NEW guards (sites 1-8); site 9 is already done.

## 2. DEADLOCK ANALYSIS — the load MUST be hoisted to start/toggle, NOT inside _arm (contract c is impossible as literally written)

- `_arm()` is invoked UNDER `self._lock` by `start()` (`with self._lock: self._arm()`) and `toggle()`.
- The contract (b) requires `_load_recorder()` to **acquire self._lock, set _loading, RELEASE it for the heavy build_recorder(), RE-ACQUIRE to install** (acquire-release-reacquire). 
- If `_arm()` (holding `_lock`) called `_load_recorder()` (which acquires `_lock`) → **deadlock** (threading.Lock is non-reentrant).

**Resolution (matches delta_prd M2.T1.S1 verbatim: "wire `start`/`toggle` to await it before arming"):** hoist `_load_recorder()` into `start()` and `toggle()` (the arm-pathway callers) BEFORE they take `_lock` + call `_arm()`. `_arm()` stays a pure under-lock mutator and does NOT call `_load_recorder()` (its callers guarantee a loaded recorder; the set_microphone guard is defense-in-depth). This honors contract (b) fully and contract (c)'s INTENT (load-on-arm-pathway) without the deadlock. The PRP documents this as an explicit deviation from the literal "(c) Wire _arm() to call _load_recorder", justified by the deadlock.

## 3. Single-flight with WAIT semantics (Condition over self._lock) — required by PRD §4.2bis + the per-connection threading model

- `ControlServer._accept_loop` (daemon.py:1027) spawns **one daemon worker thread PER connection** (`threading.Thread(target=self._handle, ...).start()`). So two `voicectl` processes connecting within the ~1–3 s load window CAN issue concurrent arms.
- PRD §4.2bis: "A second arm while `loading` MUST NOT start a second load — it **waits** on the in-flight one." delta_prd M2.T1.S1: "wire start/toggle to **await** it". So the single-flight must WAIT (not return-immediately).
- **Design:** add `self._load_cond = threading.Condition(self._lock)` (shares the SAME underlying lock as `with self._lock:`). `_load_recorder()`:
  - `with self._lock:` → if `_models_loaded`: return True; if `_loading`: `while _loading: _load_cond.wait()` then `return self._models_loaded` (the in-flight load's result); else set `_loading=True`, `feedback.set_phase("loading")`, release lock (exit `with`).
  - heavy `build_recorder()` OUTSIDE the lock (status/toggle/stop stay responsive during the ~1–3 s load — mirrors the abort()-out-of-_lock discipline, validation NEW-2).
  - `with self._lock:` → `_loading=False`; install recorder + `_models_loaded=True` + phase='idle' + `_load_cond.notify_all()` (success) OR null recorder + `_load_error` + phase='unloaded' + notify (failure); return bool.
- `Condition(self._lock).wait()` releases `self._lock` while waiting and re-acquires before returning; `notify_all()` requires holding the lock (satisfied inside `with self._lock:`). Existing `with self._lock:` code is unaffected. This also future-proofs M3's arm-vs-teardown race (same Condition).

## 4. CPU-fallback migration (main() → _load_recorder) — AND its test impact

**main() today** (daemon.py:~1351-1380): wraps `VoiceTypingDaemon(cfg, feedback, latency=latency)` in a try/except; on Exception with resolved device==cuda, retries via `build_recorder(force_cpu=True)` + `recorder=` injection + seeds `daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)`. 

**After migration:** main() just does `daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)` (fast — __init__ no longer builds the recorder) → `ControlServer(...)` → `daemon.run()`. The try/except CPU-retry block is DELETED. `_load_recorder()` owns the fallback: on the first (cuda) `build_recorder` Exception, it retries once with `force_cpu=True`; on success it seeds `self._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)` (so status reports device=cpu) + logs the degradation. On total failure it sets `_load_error`, leaves `self._recorder=None`, returns False (PRD §4.2bis "no half-built recorder").

**TEST IMPACT (critical):** the plan-001 bugfix added 5 main()-CPU-fallback tests (test_daemon.py:1893-2030) that assert main() retries with force_cpu. With the fallback migrated, main() no longer retries → these BREAK. They MUST be migrated to test `_load_recorder()`'s CPU fallback instead (the behavior moved; the tests move with it):
- REMOVE: banner (1893-1897), `_raise_once_daemon_factory` (~1910), `test_main_falls_back_to_cpu_on_cuda_construction_failure` (1930), `test_main_skips_cpu_retry_when_resolved_device_not_cuda` (1962), `test_main_returns_one_when_cpu_build_also_fails` (1989), `test_main_fallback_warning_message_matches_prd_44` (2020).
- KEEP: `test_log_resolved_device_reads_cache_after_cpu_fallback` (2006) — tests `_log_resolved_device` directly (manually sets the cache), independent of main(); still valid.
- CLEAN: `test_main_returns_one_on_daemon_construction_failure` (1417, BoomDaemon) — still passes (construction failure → main()==1), but its hermeticity monkeypatches (`_resolve_device_config` + `build_recorder` at 1435-1438) are now dead (main() no longer calls them during construction). Remove those 2 dead lines + their comment; keep BoomDaemon + `assert main()==1`.
- ADD: a new `_load_recorder` test section (lazy load: success, single-flight wait, CPU fallback, total failure, no-half-built-recorder, injected-recorder-is-loaded).

## 5. Feedback coupling resolution (T1.S1 ↔ T2.S1 boundary — do NOT edit feedback.py)

- The contract (b) says `_load_recorder` sets "feedback models_loaded=True, phase='loading'/'idle'". But `Feedback` has **no `set_models_loaded`** / no `models_loaded` state (verified: feedback.py state = {listening, phase, partial, last_final, ts}).
- delta_prd M2.T2 explicitly OWNS "Add `models_loaded: bool` to the feedback state (feedback.py:85–88)" + exposing phase/models_loaded in status_snapshot/ctl.
- **Resolution:** T1.S1 does NOT edit feedback.py. It (a) tracks `self._models_loaded`/`self._loading`/`self._load_error` as DAEMON attributes (contract point a); (b) drives the lifecycle `phase` via the EXISTING `feedback.set_phase("unloaded"/"loading"/"idle")` (set_phase exists on both real Feedback AND the test fakes `_FakeFeedback`/`_DaemonFakeFeedback` — verified line 42; reusing it for lifecycle phases needs NO feedback.py edit). The feedback `models_loaded` field + status_snapshot/ctl exposure is T2.S1's deliverable; T2 will either read `self._models_loaded` in status_snapshot or add a setter. The contract's "feedback models_loaded=True" is satisfied in spirit by the daemon attribute; the feedback/state.json EXPOSURE is T2. **This keeps T1.S1 out of feedback.py entirely (no merge conflict with T2).**

## 6. Why ALL existing _make_daemon tests pass UNCHANGED (the safety net)

`_make_daemon` (test_daemon.py:424) ALWAYS injects a recorder: `rec = recorder if recorder is not None else _StubRecorder()`. So every daemon built by `_make_daemon` / `_make_daemon_with_feedback` has `recorder != None` → with the new `__init__`, `self._recorder = recorder` + `self._models_loaded = True`. Therefore:
- `start()`/`toggle()`'s `_load_recorder()` is a no-op (returns True immediately — `_models_loaded` already True); the arm proceeds exactly as today.
- All 8 `None`-guards see `self._recorder is not None` → fire exactly as today.
- `_load_recorder()`'s heavy `build_recorder()` is NEVER called by these tests → no RealtimeSTT import.
So the entire existing test_daemon.py suite (except the 5 migrated main()-fallback tests in §4) passes unchanged. The lazy path (recorder=None) is exercised ONLY by the NEW `_load_recorder` tests (which construct `VoiceTypingDaemon(..., recorder=None, ...)` explicitly + monkeypatch `daemon.build_recorder`). This is the contract OUTPUT point 4 guarantee.

## 7. _log_resolved_device: boot → load-time (don't probe CUDA at boot)

`run()` currently calls `self._log_resolved_device()` at boot, which reads `self._resolved_device()` → `_resolve_device_config()` → `cuda_check.resolve_device_and_models()` (imports ctranslate2 + probes the driver). At a lazy boot (no recorder) this (a) imports ctranslate2 against the "~0 VRAM / no CUDA context at boot" spirit and (b) logs "device=cuda" when nothing is loaded — misleading.
**Fix:** guard both boot-time recorder touches in `run()` with `if self._recorder is not None:` — the `set_microphone(False)` AND `_log_resolved_device()`. Call `_log_resolved_device()` in `_load_recorder()`'s SUCCESS path instead (logs the ACTUAL loaded device; on a CPU fallback the seeded cache makes it log cpu). `test_run_logs_resolved_device_at_startup` still passes (it injects a recorder → run()'s guard fires). Also update the "recorder resident" log line to be conditional ("models lazy (not yet loaded)" when None).

## 8. main() final shape (after migration) + the latency comment

main()'s construction becomes:
```python
feedback = Feedback(cfg.feedback)
latency = LatencyLog()           # shared by _load_recorder's build_recorder + on_final
daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)   # FAST — no models (lazy)
server = ControlServer(daemon, on_quit=daemon.shutdown)
restore = install_shutdown_signal_handlers(daemon)
server.start()
daemon.run()
```
The old `latency` comment ("so the construction-failure CPU retry below can build a forced-CPU recorder...") referenced the now-removed retry; update it to reference `_load_recorder` (the daemon carries latency; _load_recorder uses `self._latency`). The outer `try/except Exception → return 1` + the `finally` teardown (restore/shutdown/srv.stop) are UNCHANGED. Construction failure (e.g. BoomDaemon) still → return 1 (no retry in main(); a CPU config has nothing to fall back to and the lazy load's CPU fallback only triggers on the cuda path at arm time).

## 9. Tooling / conventions (verified)

- pytest>=9.1.1 (project runner; NO ruff/mypy). Run: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` (fast suite; test_feed_audio.py is the heavy GPU suite).
- Full paths in every bash call (zsh aliases: python3→uv run, etc.): `.venv/bin/python`, never bare python/pytest/uv.
- `from __future__ import annotations` is at daemon.py top; `threading`/`time`/`logging`/`cuda_check`/`build_recorder`/`_resolve_device_config`/`logger` all already in scope. No new imports needed (threading.Condition is `threading.Condition`).
- `_bounded_shutdown`/`shutdown` (M1, LANDED) already handle `_recorder is None` (shutdown returns early). Do NOT touch them.
