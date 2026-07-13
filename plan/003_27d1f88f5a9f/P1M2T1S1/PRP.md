# PRP — P1.M2.T1.S1: Extract `_load_recorder()` single-flight method + guard all recorder call sites + migrate CPU fallback

## Goal

**Feature Goal**: Implement the lazy-load lifecycle core (PRD §4.2bis / delta_prd D1, D2): defer `AudioToTextRecorder` construction from daemon boot (`VoiceTypingDaemon.__init__`) to the **first arm** (`start`/`toggle`), via a new **single-flight** `_load_recorder() -> bool` method that owns the load + the **migrated CPU-fallback** (moved out of `main()`). Boot a session that never arms at `self._recorder = None` + ~0 VRAM; the first arm blocks ~1–3 s loading models, then arms; subsequent arms are instant (resident); a load failure leaves **no half-built recorder** and suppresses the arm. Guard all 8 unguarded `self._recorder.*` call sites against `None`.

**Deliverable** (edits to `voice_typing/daemon.py` + `tests/test_daemon.py`; no new files, no feedback.py):
1. `voice_typing/daemon.py` — (a) `__init__`: replace eager `build_recorder()` with `self._recorder = recorder` (None=lazy) + `self._models_loaded`/`self._loading`/`self._load_error`/`self._load_cond` attrs + boot phase; (b) NEW `_load_recorder()` single-flight method (Condition-wait + heavy-build-outside-lock + migrated CPU fallback); (c) hoist the load into `start()`/`toggle()` (NOT `_arm()` — deadlock); (d) `None`-guard the 8 call sites; (e) `run()`: guard boot `set_microphone(False)` + `_log_resolved_device()` + loop-top `None` check; (f) `main()`: delete the construction try/except CPU-retry block (now fast/lazy); (g) docstring updates (module-top "CONSTRUCT ONCE" + `__init__` → "lazy on first arm §4.2bis").
2. `tests/test_daemon.py` — REMOVE the 4 obsolete plan-001 `main()`-CPU-fallback tests + their banner/factory (the behavior moved to `_load_recorder`); CLEAN the BoomDaemon test (drop 2 now-dead monkeypatch lines); ADD a new `_load_recorder` test section (lazy boot, success, no-op-once-loaded, CPU fallback, total failure, start-triggers-load, start-suppressed-on-fail, injected-is-loaded). KEEP `test_log_resolved_device_reads_cache_after_cpu_fallback`.

**Success Definition**:
- (a) `VoiceTypingDaemon(cfg, feedback)` with NO `recorder=` boots with `self._recorder is None`, `self._models_loaded is False`, `self._loading is False`, `self._load_error is None`, feedback phase `'unloaded'` — NO `build_recorder()` call, NO RealtimeSTT import at construction.
- (b) `_load_recorder()` returns `True` and installs a recorder on success (`self._models_loaded=True`, phase `'idle'`); returns `False` on total failure with `self._load_error` set and `self._recorder` left `None` (no half-built recorder).
- (c) Single-flight: a concurrent second caller while `_loading` WAITS on the in-flight load and returns its result (never starts a 2nd `build_recorder`).
- (d) CPU fallback lives in `_load_recorder()`: first (cuda) build failure → retry once with `force_cpu=True` → on success seed `_resolved_device_cache=CPU_FALLBACK` + log degradation. `main()` does NOT retry on construction (it just constructs fast + runs).
- (e) All 8 unguarded `self._recorder.*` call sites are `None`-guarded; `shutdown()`'s existing guard is untouched.
- (f) **All existing `test_daemon.py` tests pass unchanged** except the 4 migrated main()-fallback tests (removed) + the BoomDaemon test (cleaned). `_make_daemon` always injects a recorder → those daemons boot `_models_loaded=True` → the lazy path is dormant for them.
- (g) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.

## User Persona

**Target User**: the operator of the 24/7 systemd user service. The daemon autostarts on every login but is used rarely; today it parks ~2.8 GB VRAM 24/7. After this: a boot that never arms uses ~0 VRAM; the first arm pays a ~1–3 s load; models stay resident for instant re-arms.

**Pain Points Addressed**: PRD §1 GPU decision + §4.2bis — stop taxing the GPU on boots where voice typing is never used. (Lazy load is the foundation; idle-UNLOAD after 30 min is P1.M3, built on this + the landed M1 bounded teardown.)

## Why

- **PRD §4.2bis is the mandate.** "Models MUST NOT load at daemon boot. The daemon starts with no recorder, no CUDA context, and ~0 VRAM. Construction … is deferred to the **first** `start`/`toggle`." This task is the load core (D1/D2). delta_prd M2.T1.S1: "Extract a `_load_recorder()` single-flight method … wire `start`/`toggle` to **await** it before arming. No double-load; no half-built recorder on failure."
- **The CPU-fallback must move with the load.** Today `main()` retries construction on a cuda build failure (bugfix Issue 3). Once construction is lazy (no models at boot), `main()` has nothing to retry — the fallback MUST live in `_load_recorder()` (the new construction site). Migrating it keeps the §4.4 robustness guarantee at the right place.
- **Single-flight is a hard concurrency requirement.** The control server spawns one thread per connection (daemon.py:1039), so two `voicectl` arms can race the ~1–3 s load. PRD §4.2bis: "A second arm while `loading` … waits on the in-flight one." It also future-proofs P1.M3's arm-vs-idle-unload teardown race (same lock/Condition).
- **M1 (bounded teardown) already landed** — `shutdown()`/`_bounded_shutdown()` already handle `self._recorder is None` (daemon.py:~911), so a lazy daemon that never armed shuts down cleanly. This task builds on that.

## What

A daemon that boots lazy (`self._recorder=None`, phase `'unloaded'`, ~0 VRAM). `start`/`toggle` call `_load_recorder()` (outside `_lock`) before arming; `_load_recorder()` single-flights the load (Condition-wait), builds outside `_lock`, retries CPU on failure, installs under `_lock`, logs the resolved device. The 8 recorder call sites tolerate `None`. `main()` constructs fast (no models) and runs. `run()` idles (`sleep 0.05; continue`) while `self._recorder is None` (PRD §4.2(1)).

### Success Criteria

- [ ] `VoiceTypingDaemon(cfg, fb)` (no `recorder=`) → `self._recorder is None`, `_models_loaded is False`, `_loading is False`, `_load_error is None`; NO `build_recorder`/RealtimeSTT at construction.
- [ ] `_load_recorder()` success → `_recorder` installed, `_models_loaded=True`, phase `'idle'`, returns True; the cuda probe (`_log_resolved_device`) runs at LOAD time not boot.
- [ ] `_load_recorder()` total failure → returns False, `_recorder` stays None, `_load_error` set, phase `'unloaded'`.
- [ ] CPU fallback: first build `Exception` → one `force_cpu=True` retry → success seeds `_resolved_device_cache=CPU_FALLBACK` (status reports `device=cpu`) + logs the degradation WARNING.
- [ ] Single-flight: 2 concurrent `_load_recorder()` → exactly 1 `build_recorder` call; the 2nd returns the 1st's result.
- [ ] `start()`/`toggle()` arm path calls `_load_recorder()` BEFORE taking `_lock`; failed load → arm suppressed (stays not-listening).
- [ ] All 8 unguarded call sites `None`-guarded; `shutdown()`'s existing guard untouched.
- [ ] `main()`: no construction try/except CPU-retry; `daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)` then `run()`.
- [ ] The 4 obsolete main()-fallback tests removed; BoomDaemon test cleaned; new `_load_recorder` tests added; `test_log_resolved_device_reads_cache_after_cpu_fallback` kept.
- [ ] Fast suite green; `git status` == `voice_typing/daemon.py` + `tests/test_daemon.py` only.

## All Needed Context

### Context Completeness Check

_Pass._ The 8 call sites are derived from the live code (table below); the deadlock (load cannot nest in lock-held `_arm`) is analyzed and resolved (hoist to start/toggle — matches delta_prd "await it before arming"); the single-flight Condition design is specified; the CPU-fallback migration + its test impact (4 obsolete tests + BoomDaemon cleanup) are enumerated; the feedback.py boundary (do NOT edit — T2 owns `models_loaded`) is drawn; and the reason all `_make_daemon` tests pass unchanged (always inject a recorder → `_models_loaded=True` → lazy path dormant) is documented. Verbatim old→new is given for every concurrency-critical source edit.

### Documentation & References

```yaml
# MUST READ — deadlock analysis, single-flight design, CPU-fallback migration + TEST IMPACT, feedback boundary
- docfile: plan/003_27d1f88f5a9f/P1M2T1S1/research/load_recorder_single_flight.md
  why: "§1 the 8 call-site table. §2 DEADLOCK: _arm holds _lock → _load_recorder (acquire-release-reacquire) CANNOT be
        called from _arm; hoist to start/toggle (matches delta_prd 'await it before arming'). §3 single-flight Condition
        over self._lock with WAIT semantics (per-connection threading model). §4 CPU-fallback migration main()->_load_recorder
        + the 5 main()-fallback tests that BREAK (remove 4, keep test_log_resolved_device_reads_cache, clean BoomDaemon).
        §5 feedback boundary: do NOT edit feedback.py (T2 owns models_loaded); reuse existing set_phase + daemon attrs.
        §6 why _make_daemon tests pass unchanged (always inject recorder). §7 _log_resolved_device boot->load-time.
        §8 main() final shape. §9 tooling."
  section: "§2 (deadlock), §3 (Condition), §4 (test impact), §5 (feedback boundary) are load-bearing."

# THE AUTHORITATIVE FEATURE SPEC — lazy load lifecycle + the exact task boundary
- docfile: plan/003_27d1f88f5a9f/delta_prd.md
  why: "M2.T1.S1: 'Extract a _load_recorder() single-flight method (lock-guarded) returning success/failure; wire
        start/toggle to AWAIT it before arming. No double-load; no half-built recorder on failure.' M2.T2 OWNS 'Add
        models_loaded: bool to the feedback state' + status_snapshot/ctl exposure — so T1.S1 must NOT edit feedback.py.
        D1/D2 (lazy load, state machine), §4.2bis (single-flight wait, no half-built recorder)."
  critical: "T1.S1 = load LOGIC + daemon-side state; T2.S1 = feedback models_loaded + status/ctl EXPOSURE. Don't cross."

# THE PRD LIFECYCLE (the contract this implements)
- file: PRD.md
  why: "§4.2(1) the idle loop pseudocode (recorder is None -> sleep 0.05; continue). §4.2bis: unloaded->loading->loaded,
        single-flight wait, load failure returns to unloaded with ok:false + NO half-built recorder. §4.4 the CPU fallback
        config (cpu/int8/small.en/tiny.en). §4.9 starts not-listening AND now not-loaded."

# THE LANDED PREREQUISITE — bounded teardown already handles _recorder is None
- file: voice_typing/daemon.py
  why: "_bounded_shutdown (818) + shutdown (876) ALREADY guard self._recorder is None (shutdown returns early — the
        'M2 lazy-load prep' comment at ~911). Do NOT touch them. _construct (241) + build_recorder (272) already support
        force_cpu + on_speech — _load_recorder reuses them. _resolved_device() (795) caches via _resolved_device_cache
        (getattr) — _load_recorder seeds it on the CPU-fallback path."
  critical: "shutdown() at ~911 already does `if self._recorder is None: return` — it is the ONE already-guarded site;
             do NOT re-add a guard there. The 8 sites needing NEW guards are run(2), _arm, _disarm, _maybe_auto_stop, stop,
             toggle, request_shutdown (see research §1)."

# THE CPU-FALLBACK ORIGIN (the logic being migrated) + the test-seam patterns
- file: tests/test_daemon.py
  why: "_make_daemon (424) ALWAYS injects _StubRecorder -> _models_loaded=True at boot -> lazy path dormant (existing tests
        pass). _StubRecorder (365), _DaemonFakeFeedback (350, inherits _FakeFeedback.set_phase line 42 — so __init__'s
        set_phase call works with fakes). _patch_main_lifecycle (1321) patches VoiceTypingDaemon/ControlServer/Feedback.
        The 4 main()-fallback tests to REMOVE: test_main_falls_back_to_cpu_on_cuda_construction_failure (1930),
        test_main_skips_cpu_retry_when_resolved_device_not_cuda (1962), test_main_returns_one_when_cpu_build_also_fails (1989),
        test_main_fallback_warning_message_matches_prd_44 (2020) + banner(1893)+_raise_once_daemon_factory(~1910). KEEP
        test_log_resolved_device_reads_cache_after_cpu_fallback (2006). CLEAN test_main_returns_one_on_daemon_construction_failure
        (1417, drop the 2 dead _resolve_device_config/build_recorder monkeypatch lines)."
  critical: "Find tests by NAME (line numbers drift). The removed tests assert main() retries — obsolete once the fallback
             moves to _load_recorder. The NEW tests assert _load_recorder's fallback instead."

# PARALLEL CONTEXT — P1.M1.T2.S1 (systemd TimeoutStopSec; NO overlap)
- docfile: plan/003_27d1f88f5a9f/P1M1T2S1/PRP.md
  why: "T2.S1 edits systemd/voice-typing.service (TimeoutStopSec) — does NOT touch daemon.py or test_daemon.py. No overlap.
        M1 (bounded teardown) is LANDED (Complete); this task relies on shutdown() being None-safe (it is)."
```

### The 8 recorder call sites needing `None` guards (derived from the live code)

| # | Method (~line) | Call | Guard |
|---|---|---|---|
| 1 | `run()` ~488 | `set_microphone(False)` (boot) | `if self._recorder is not None:` |
| 2 | `run()` ~495 | `text(self.on_final)` (loop) | `if self._recorder is None: sleep(0.05); continue` at loop top |
| 3 | `_arm()` ~588 | `set_microphone(True)` | `if self._recorder is not None:` |
| 4 | `_disarm()` ~601 | `set_microphone(False)` | `if self._recorder is not None:` |
| 5 | `_maybe_auto_stop()` ~647 | `abort()` | `if disarmed and self._recorder is not None:` |
| 6 | `stop()` ~727 | `abort()` | `if self._recorder is not None:` |
| 7 | `toggle()` ~741 | `abort()` | `if self._recorder is not None:` |
| 8 | `request_shutdown()` ~751 | `abort()` | `if self._recorder is not None:` |
| (9) | `shutdown()` ~911 | `shutdown()` | **ALREADY guarded — do NOT touch** |

### Current Codebase tree (relevant slice — the 2 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py     # EDIT: __init__(447), NEW _load_recorder, run(467), _arm/_disarm/_maybe_auto_stop, start/stop/
│                     #       toggle/request_shutdown, main(1304), module docstring(14-18,49). feedback.py UNCHANGED.
└── tests/
    └── test_daemon.py # EDIT: remove 4 main()-fallback tests + banner/factory; clean BoomDaemon; ADD _load_recorder section.
# M1 bounded teardown LANDED (shutdown None-safe). P1.M1.T2.S1 (parallel) edits systemd/ only — no overlap. No new files.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py    # EDIT — lazy __init__ + _load_recorder + 8 guards + start/toggle hoist + main() simplification + docstrings.
tests/test_daemon.py      # EDIT — migrate the CPU-fallback tests from main() to _load_recorder; add lazy-load tests.
# NOTHING ELSE. feedback.py = P1.M2.T2.S1. config.py/config.toml/auto_unload = P1.M3. README = P1.M3.T3. systemd = P1.M1.T2.S1.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DEADLOCK: do NOT call _load_recorder() from inside _arm(). _arm() runs UNDER self._lock (called by
# start/toggle with `with self._lock:`). _load_recorder() must acquire-release-reacquire that SAME lock (single-flight +
# build-outside-lock). Nesting → deadlock (threading.Lock is non-reentrant). HOIST the load into start()/toggle() BEFORE
# they take _lock. This matches delta_prd M2.T1.S1 "wire start/toggle to await it before arming". The contract's literal
# "(c) Wire _arm() to call _load_recorder" is implemented as "start/toggle call it before _arm" — the only deadlock-free
# reading. (research §2.)

# CRITICAL #2 — SINGLE-FLIGHT MUST WAIT, not return-immediately. ControlServer spawns ONE THREAD PER CONNECTION
# (daemon.py:1039), so concurrent arms are possible. PRD §4.2bis: a 2nd arm while loading "waits on the in-flight one".
# Use threading.Condition(self._lock): waiters do `while self._loading: self._load_cond.wait()` then return
# self._models_loaded; the loader notify_all()s after install. Condition(self._lock) shares the existing lock (existing
# `with self._lock:` code is unaffected). (research §3.)

# CRITICAL #3 — THE HEAVY build_recorder() MUST RUN OUTSIDE _lock. _load_recorder takes _lock only to (a) check/set
# _loading + phase, (b) install the recorder + notify. The ~1-3s model load runs between (release lock) and (re-acquire),
# so status/stop/toggle stay responsive. Mirrors the abort()-out-of-_lock discipline (validation NEW-2). (research §3.)

# CRITICAL #4 — DO NOT EDIT feedback.py. T2 (P1.M2.T2.S1) owns "Add models_loaded: bool to the feedback state" +
# status_snapshot/ctl exposure. T1 tracks self._models_loaded (daemon attr) + drives the lifecycle PHASE via the EXISTING
# feedback.set_phase("unloaded"/"loading"/"idle") (set_phase exists on real Feedback AND the test fakes _FakeFeedback
# line 42 / _DaemonFakeFeedback). No feedback.py edit = no merge conflict with T2. (research §5.)

# CRITICAL #5 — _make_daemon ALWAYS injects a _StubRecorder (test_daemon.py:427), so every test-built daemon has
# _models_loaded=True at construction -> _load_recorder is a no-op for them + all 8 guards see non-None -> the ENTIRE
# existing suite passes unchanged (except the 4 migrated main()-fallback tests). Do NOT change _make_daemon. (research §6.)

# CRITICAL #6 — MIGRATING THE CPU FALLBACK BREAKS 4 TESTS. main() no longer retries on construction -> the plan-001 tests
# test_main_falls_back_to_cpu_on_cuda_construction_failure, test_main_skips_cpu_retry_when_resolved_device_not_cuda,
# test_main_returns_one_when_cpu_build_also_fails, test_main_fallback_warning_message_matches_prd_44 (all ~1930-2030)
# assert main()'s retry -> they BREAK. REMOVE them (+ their banner + _raise_once_daemon_factory) and REPLACE with _load_recorder
# fallback tests. KEEP test_log_resolved_device_reads_cache_after_cpu_fallback (2006, tests _log_resolved_device directly).
# CLEAN test_main_returns_one_on_daemon_construction_failure (drop the 2 dead _resolve_device_config/build_recorder patches).
# (research §4.)

# CRITICAL #7 — shutdown() (~911) ALREADY handles self._recorder is None (returns early; "M2 lazy-load prep" comment).
# _bounded_shutdown is only reached AFTER that guard. Do NOT add another None guard in shutdown/_bounded_shutdown. The 8
# NEW guards are sites 1-8 only. (research §1.)

# CRITICAL #8 — _log_resolved_device MOVES from boot to load-time. At a lazy boot (no recorder) it would probe cuda_check
# (import ctranslate2) + log "device=cuda" when nothing is loaded (misleading + against the ~0-VRAM-boot spirit). GUARD it
# in run() with `if self._recorder is not None:` and call it in _load_recorder's SUCCESS path (logs the ACTUAL device).
# test_run_logs_resolved_device_at_startup still passes (it injects a recorder -> run()'s guard fires). (research §7.)

# CRITICAL #9 — LEAVE NO HALF-BUILT RECORDER on failure. _load_recorder's failure path sets self._recorder = None
# explicitly (a build_recorder that raised produced no object, but be explicit) + self._models_loaded=False. PRD §4.2bis.

# GOTCHA #10 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest/uv.

# GOTCHA #11 — pytest>=9.1.1 is the runner; NO ruff/mypy. Validation = py_compile + pytest. (research §9.)

# GOTCHA #12 — `from __future__ import annotations` is at daemon.py top; threading.Condition needs no new import
# (threading is imported). cuda_check / build_recorder / _resolve_device_config / logger are module globals.
```

## Implementation Blueprint

### Data models and structure

No schema/config/pydantic change. New daemon instance state: `self._recorder` (None=lazy), `self._models_loaded: bool`, `self._loading: bool`, `self._load_error: str | None`, `self._load_cond: threading.Condition` (over `self._lock`). The `_resolved_device_cache` extension point is reused (seeded on the CPU-fallback path). No new types.

### Implementation Tasks (ordered by dependencies — source first, then tests, then validate)

```yaml
Task 1: EDIT __init__ — lazy recorder + lifecycle attrs + boot phase
  - FIND the eager-construction block (daemon.py ~447-451). Current:
        # construct-once (PRD §4.2): build recorder ONCE so models stay resident + toggle/start/stop
        # can arm the mic immediately. Injectable for unit tests (fakes → cheap, no RealtimeSTT).
        # Pass self._latency so on_vad_stop/partial feed the latency log (PRD §4.2; P1.M4.T1.S3).
        self._recorder = (
            recorder if recorder is not None
            else build_recorder(cfg, feedback, self._latency, on_speech=self._touch_speech)
        )
  - REPLACE WITH:
        # Lazy load (PRD §4.2bis / delta D1,D2): the recorder is NOT built at boot — it is built on the FIRST arm
        # (start/toggle) via _load_recorder(), so a session that never arms stays at ~0 VRAM. recorder= injected
        # (unit tests / a pre-built recorder) → already loaded; None → lazy (self._recorder is None until the first
        # successful _load_recorder()). self._latency is threaded into build_recorder by _load_recorder().
        self._recorder = recorder
        self._models_loaded = recorder is not None
        self._loading = False
        self._load_error: str | None = None
        # Single-flight load wait (PRD §4.2bis "waits on the in-flight one"): a Condition over the SAME _lock so a
        # second arm while _loading blocks on the in-flight load, then sees its result. Condition(_lock) shares the
        # existing lock; existing `with self._lock:` code is unaffected.
        self._load_cond = threading.Condition(self._lock)
        # Boot lifecycle phase (delta D2/D3): 'idle' if a recorder was injected (loaded), else 'unloaded' (the lazy
        # boot state). _load_recorder() drives loading->idle; a failed load returns to 'unloaded'. (The feedback
        # models_loaded FIELD + status_snapshot/ctl exposure is P1.M2.T2.S1; T1 tracks the daemon-side
        # self._models_loaded + drives phase via the existing set_phase — no feedback.py edit.)
        self._feedback.set_phase("idle" if recorder is not None else "unloaded")
  - WHY: defers construction (None when not injected) + adds the single-flight state + sets the boot phase. Injected
    recorders (tests, a pre-built recorder) → _models_loaded=True + phase 'idle' (the safety net, CRITICAL #5).
  - DO NOT: call build_recorder here; set _models_loaded=True unconditionally (only when recorder injected); edit feedback.py.

Task 2: ADD the _load_recorder() method — insert it IMMEDIATELY AFTER __init__ (before run()), so it reads naturally.
  - INSERT (verbatim):
        def _load_recorder(self) -> bool:
            """Single-flight lazy load of the recorder on first arm (PRD §4.2bis). True iff a recorder is ready.

            Called by start()/toggle() BEFORE arming — NOT inside _arm() (which holds self._lock; this method
            acquire-release-reacquires that same lock, so nesting would deadlock). Idempotent once loaded: a
            resident recorder → immediate True. Single-flight via _load_cond (Condition over self._lock): a second
            caller while _loading WAITS for the in-flight load and returns ITS result (never starts a 2nd load). The
            heavy build_recorder() runs OUTSIDE _lock so concurrent status/stop stay responsive during the ~1–3 s load
            (mirrors the abort()-out-of-_lock discipline, validation NEW-2).

            CPU fallback (migrated from main() / bugfix Issue 3, P1.M1.T3.S2): if the first (cuda) build raises,
            retry ONCE with force_cpu=True (build_recorder force_cpu skips the cuda_check probe). On success: install
            self._recorder, _models_loaded=True, phase='idle', seed _resolved_device_cache with cuda_check.CPU_FALLBACK
            on the fallback path (so status reports device=cpu), log the resolved device, return True. On total
            failure: _load_error set, self._recorder stays None (NO half-built recorder — §4.2bis), phase='unloaded',
            return False.
            """
            with self._lock:
                if self._models_loaded:
                    return True                       # resident → instant (second+ arm)
                if self._loading:
                    while self._loading:               # wait for the in-flight load (spurious-wake safe)
                        self._load_cond.wait()
                    return self._models_loaded         # its result (True=loaded, False=failed)
                self._loading = True                   # we are the loader
                self._load_error = None
                self._feedback.set_phase("loading")
            # --- heavy build OUTSIDE _lock (status/stop stay responsive during the ~1–3 s load) ---
            recorder = None
            fell_back_to_cpu = False
            load_error: str | None = None
            try:
                recorder = build_recorder(
                    self._cfg, self._feedback, self._latency, on_speech=self._touch_speech
                )
            except Exception as exc:
                # Migrated CPU fallback (was main()): cuda_check can say "cuda-ok" while cuDNN/cuBLAS fails inside
                # AudioToTextRecorder.__init__. Retry ONCE on the PRD §4.4 CPU config (force_cpu skips cuda_check).
                logger.warning(
                    "CUDA recorder construction failed (%s); falling back to CPU "
                    "(device=cpu, compute_type=int8, models=small.en/tiny.en) — degraded but functional",
                    exc,
                )
                try:
                    recorder = build_recorder(
                        self._cfg, self._feedback, self._latency, force_cpu=True, on_speech=self._touch_speech,
                    )
                    fell_back_to_cpu = True
                except Exception as exc2:
                    load_error = f"CUDA load failed: {exc!r}; CPU fallback also failed: {exc2!r}"
                    recorder = None
            # --- re-acquire _lock to publish the result + wake any waiters ---
            with self._lock:
                self._loading = False
                if recorder is not None:
                    self._recorder = recorder
                    self._models_loaded = True
                    self._load_error = None
                    if fell_back_to_cpu:
                        # Status must report the ACTUAL cpu device, not the driver probe (still sees the GPU).
                        # Migrated from main()'s `daemon._resolved_device_cache = dict(CPU_FALLBACK)` seed.
                        self._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)
                    self._feedback.set_phase("idle")
                    self._load_cond.notify_all()
                    success = True
                else:
                    self._load_error = load_error or "unknown load error"   # NO half-built recorder (§4.2bis)
                    self._models_loaded = False
                    self._recorder = None
                    self._feedback.set_phase("unloaded")
                    self._load_cond.notify_all()
                    success = False
            # Log OUTSIDE _lock (_log_resolved_device's cuda_check probe is ~ms; don't hold the lock for it).
            if success:
                self._log_resolved_device()   # log the ACTUAL loaded device (moved here from boot — CRITICAL #8)
                if fell_back_to_cpu:
                    logger.info("models loaded in degraded CPU mode (construction-failure fallback)")
                logger.info("voice-typing models loaded (lazy load complete); recorder resident")
            else:
                logger.error("voice-typing model load failed (%s); staying unloaded", self._load_error)
            return success
  - WHY: single-flight + wait (CRITICAL #2), build outside lock (CRITICAL #3), migrated CPU fallback (CRITICAL #6),
    no half-built recorder (CRITICAL #9), device log at load time (CRITICAL #8).
  - DO NOT: call this from _arm (CRITICAL #1); build inside _lock; forget notify_all (waiters would hang); seed the
    cache on the non-fallback path (let _resolved_device lazily probe cuda for a real cuda load).

Task 3: GUARD the 8 call sites + HOIST the load into start/toggle (6 small edits).
  EDIT 3a — _arm() set_microphone(True) guard:
    OLD:   self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh\n        self._recorder.set_microphone(True)
    NEW:   self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh\n        if self._recorder is not None:\n            self._recorder.set_microphone(True)
  EDIT 3b — _disarm() set_microphone(False) guard:
    OLD:   self._last_speech_monotonic = None  # not listening → idle clock is inactive\n        self._recorder.set_microphone(False)
    NEW:   self._last_speech_monotonic = None  # not listening → idle clock is inactive\n        if self._recorder is not None:\n            self._recorder.set_microphone(False)
  EDIT 3c — _maybe_auto_stop() abort guard:
    OLD:   if disarmed:\n            self._recorder.abort()
    NEW:   if disarmed and self._recorder is not None:\n            self._recorder.abort()
  EDIT 3d — start() HOIST the load (CRITICAL #1):
    OLD:   def start(self) -> None:\n        with self._lock:\n            self._arm()
    NEW:   def start(self) -> None:\n        # Lazy load (PRD §4.2bis): build the recorder on the first arm. _load_recorder() is a single-flight no-op\n        # once resident. Called OUTSIDE _lock (it acquire-release-reacquires that lock; under _lock it would deadlock).\n        if not self._load_recorder():\n            return  # load failed → stay unarmed (phase already 'unloaded'; _load_error set)\n        with self._lock:\n            self._arm()
  EDIT 3e — stop() abort guard:
    OLD:   def stop(self) -> None:\n        with self._lock:\n            self._disarm()\n        # abort() moved OUT of _lock to avoid the control-lock wedge (validation NEW-2; see\n        # _disarm docstring). Only disarm needs to wake a blocked text(); start/_arm does not.\n        self._recorder.abort()
    NEW:   def stop(self) -> None:\n        with self._lock:\n            self._disarm()\n        # abort() moved OUT of _lock to avoid the control-lock wedge (validation NEW-2; see\n        # _disarm docstring). Only disarm needs to wake a blocked text(); start/_arm does not.\n        if self._recorder is not None:\n            self._recorder.abort()
  EDIT 3f — toggle() HOIST the load (arm path) + abort guard (CRITICAL #1): the arm path needs the load BEFORE _lock;
    the disarm path is fast. Restructure to read listening under lock, then act.
    OLD:   def toggle(self) -> None:\n        with self._lock:\n            disarmed = self._listening.is_set()\n            if disarmed:\n                self._disarm()\n            else:\n                self._arm()\n        # abort() moved OUT of _lock (validation NEW-2). Only call it when we disarmed — arming\n        # must not abort a sibling text() that's about to start transcribing.\n        if disarmed:\n            self._recorder.abort()
    NEW:   def toggle(self) -> None:\n        # Decide arm vs disarm, then act. Disarm is fast; the ARM path lazy-loads FIRST (outside _lock —\n        # _load_recorder acquire-release-reacquires that lock; calling it under _lock deadlocks). The read/act split\n        # is race-tolerant exactly like the abort()-outside-_lock design (the listening Event + on_final gate are\n        # the source of truth; toggle is user-paced).\n        with self._lock:\n            disarmed = self._listening.is_set()\n        if disarmed:\n            with self._lock:\n                self._disarm()\n            # abort() moved OUT of _lock (validation NEW-2). Only on disarm — arming must not abort a sibling\n            # text() that's about to start transcribing.\n            if self._recorder is not None:\n                self._recorder.abort()\n        else:\n            if not self._load_recorder():\n                return  # load failed → stay unarmed\n            with self._lock:\n                self._arm()
  EDIT 3g — request_shutdown() abort guard:
    OLD:   self._shutdown.set()\n        self._recorder.abort()    # break any blocked text() so run() can return (NOT under _lock)
    NEW:   self._shutdown.set()\n        if self._recorder is not None:\n            self._recorder.abort()    # break any blocked text() so run() can return (NOT under _lock)
  - DO NOT: guard shutdown()/_bounded_shutdown (already None-safe, CRITICAL #7); call _load_recorder from _arm.

Task 4: EDIT run() — guard the 2 boot recorder touches + the loop-top None check + conditional ready log.
  EDIT 4a — boot _log_resolved_device guard (skip at lazy boot; CRITICAL #8):
    OLD:   self._log_resolved_device()           # PRD §4.2/acceptance T6: prove CUDA residency at startup
    NEW:   if self._recorder is not None:        # lazy load (§4.2bis): no device to log at boot; _load_recorder logs it\n            self._log_resolved_device()           # PRD §4.2/acceptance T6: prove CUDA residency (at LOAD time now)
  EDIT 4b — boot set_microphone(False) guard + conditional ready log. FIND:
        self._recorder.set_microphone(False)\n        logger.info("voice-typing daemon ready (not listening); recorder resident")
    REPLACE WITH:
        if self._recorder is not None:\n            self._recorder.set_microphone(False)\n        logger.info(\n            "voice-typing daemon ready (not listening); %s",\n            "recorder resident" if self._recorder is not None else "models lazy (not yet loaded)",\n        )
  EDIT 4c — loop-top None check (PRD §4.2(1)). FIND:
        while not self._shutdown.is_set():\n            if self._listening.is_set():
    REPLACE WITH:
        while not self._shutdown.is_set():\n            if self._recorder is None:\n                time.sleep(0.05)   # no models loaded yet → idle, ~0 VRAM (PRD §4.2(1)/§4.2bis)\n                continue\n            if self._listening.is_set():
  - WHY: a lazy boot must not touch a None recorder (boot disarm + device log) and must idle the loop until loaded.
  - DO NOT: change the watchdog start (it no-ops when not listening); change the listening/text branch.

Task 5: EDIT main() — DELETE the construction try/except CPU-retry block (CRITICAL #6).
  - FIND (the block spanning latency creation through the fallback, daemon.py ~1349-1380):
        # One LatencyLog shared by the recorder callbacks (on_vad_stop/partial, wired in build_recorder)
        # and the daemon's on_final.finalize_utterance. Created here (not left to __init__) so the
        # construction-failure CPU retry below can build a forced-CPU recorder wired to this SAME
        # collector before re-constructing the daemon. (bugfix Issue 3 / P1.M1.T3.S2.)
        latency = LatencyLog()

        # bugfix Issue 3 / P1.M1.T3.S2 (PRD §4.4): the cuda_check driver probe can say "cuda-ok" while
        [... the entire try/except CPU-retry block ...]
            logger.info("daemon started in degraded CPU mode (construction-failure fallback)")
        # quit path: ControlServer._dispatch("quit") -> request_shutdown() (blocks until text()
  - REPLACE THE WHOLE BLOCK (from the `# One LatencyLog...` comment through `logger.info("daemon started in degraded CPU mode (construction-failure fallback)")`) WITH:
        # One LatencyLog shared by _load_recorder()'s build_recorder (recorder on_vad_stop/partial callbacks) and the
        # daemon's on_final.finalize_utterance. (bugfix Issue 3 CPU-fallback now lives in _load_recorder — P1.M2.T1.S1
        # lazy load — so main() no longer retries here; construction is fast and model-free.)
        latency = LatencyLog()
        daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)   # FAST — no models loaded (lazy, §4.2bis)
  - (Leave the following `# quit path: ...` comment + `server = ControlServer(...)` + restore/start/run UNCHANGED.)
  - WHY: construction is lazy (no models, no GPU work) → no retry is possible or needed; _load_recorder owns the fallback.
  - DO NOT: change the outer try/except/finally; change the teardown order; remove the latency (still shared with _load_recorder).

Task 6: EDIT docstrings — module-top "CONSTRUCT ONCE" + "CONSUMED BY" + the VoiceTypingDaemon class docstring + __init__.
  EDIT 6a — module-top "CONSTRUCT ONCE" (daemon.py ~14-18). FIND:
        CONSTRUCT ONCE (PRD §4.2 "construct once"): AudioToTextRecorder.__init__ loads BOTH whisper
        models (final + realtime) into resident memory (GPU VRAM on cuda, RAM on cpu) — seconds of
        work. build_recorder() constructs exactly ONE recorder; VoiceTypingDaemon reuses it for the
        daemon's lifetime so a later voicectl toggle arms the mic instantly and VRAM stays resident.
  REPLACE WITH:
        LAZY LOAD (PRD §4.2bis): AudioToTextRecorder.__init__ loads BOTH whisper models (final + realtime) into
        resident memory (GPU VRAM on cuda, RAM on cpu) — seconds of work + ~1.5-3 GB VRAM. To avoid taxing the GPU on
        boots where voice typing is never used, the recorder is NOT built at daemon boot — it is built lazily on the
        FIRST arm (start/toggle) via VoiceTypingDaemon._load_recorder() (single-flight). A session that never arms
        stays at ~0 VRAM; after the first arm the recorder stays resident so re-arms are instant. _load_recorder() also
        owns the construction-failure CPU fallback (migrated from main(), bugfix Issue 3).
  EDIT 6b — module-top "CONSUMED BY" (~49). FIND: "the daemon main loop (P1.M4.T1.S2): build_recorder(cfg, feedback) once in VoiceTypingDaemon.__init__."
  REPLACE WITH: "the daemon main loop (P1.M4.T1.S2 + P1.M2.T1.S1): VoiceTypingDaemon builds the recorder LAZILY on first arm via _load_recorder() (§4.2bis), not in __init__."
  EDIT 6c — VoiceTypingDaemon class docstring (~407-409). FIND: "start/stop/toggle arm/disarm the mic via set_microphone+abort (models stay resident → instant\ntoggle-on)."
  REPLACE WITH: "start/stop/toggle arm/disarm the mic via set_microphone+abort; the FIRST arm lazily loads the models\nvia _load_recorder() (§4.2bis) — subsequent arms are instant (resident)."
  - DO NOT: rewrite the whole docstrings; touch other comment blocks.

Task 7: EDIT tests/test_daemon.py — migrate the CPU-fallback tests from main() to _load_recorder.
  PART A — REMOVE (find by NAME; the behavior moved to _load_recorder, CRITICAL #6):
    - the banner comment block starting "# bugfix P1.M1.T3.S1/S2 — main() retries once with build_recorder(force_cpu=True)..."
    - the `_raise_once_daemon_factory()` function
    - `test_main_falls_back_to_cpu_on_cuda_construction_failure`
    - `test_main_skips_cpu_retry_when_resolved_device_not_cuda`
    - `test_main_returns_one_when_cpu_build_also_fails`
    - `test_main_fallback_warning_message_matches_prd_44`
  PART B — KEEP `test_log_resolved_device_reads_cache_after_cpu_fallback` (it tests _log_resolved_device directly, still valid).
  PART C — CLEAN `test_main_returns_one_on_daemon_construction_failure`: remove the now-dead hermeticity lines (main() no
    longer calls _resolve_device_config/build_recorder during construction). FIND + DELETE the comment + 2 monkeypatch lines:
        # bugfix P1.M1.T3.S2: main() now RETRIES on cuda. Without these hermeticity patches, a GPU
        # host would hit the REAL build_recorder(force_cpu=True) (loads CPU models) inside the retry.
        # Force the resolved device to cuda (so the retry branch is entered deterministically) and
        # stub build_recorder (so no RealtimeSTT/model load). BoomDaemon still raises on BOTH
        # constructions -> "both CUDA and CPU fail" -> return 1 (the assertion is unchanged).
        _patch_main_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
        monkeypatch.setattr(
            daemon, "_resolve_device_config",
            lambda _cfg: dict(daemon.cuda_check.CUDA_DEFAULTS),
        )
        monkeypatch.setattr(daemon, "build_recorder", lambda *a, **k: _StubRecorder())
    REPLACE WITH:
        # P1.M2.T1.S1: main() no longer retries construction (lazy load — the CPU fallback moved to _load_recorder).
        # BoomDaemon raises in __init__ -> main()'s outer except -> return 1. (No GPU/build_recorder hermeticity needed:
        # construction is model-free now.) The == 1 assertion is unchanged.
        _patch_main_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
  PART D — ADD a new section at the END of the file (verbatim in "Task 7 SOURCE" below).

Task 7 SOURCE — ADD at END of tests/test_daemon.py (verbatim; reuses _StubRecorder/_DaemonFakeFeedback/_FakeBackend/
                _ok_probe/VoiceTypingConfig/daemon/logging already imported; NO real CUDA/models — build_recorder stubbed):
    (see "Task 7 SOURCE" block below)

Task 8: VALIDATE — run the Validation Loop L1-L5; fix until green. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S1: lazy _load_recorder() single-flight + CPU-fallback migration + 8 None-guards".
```

#### Task 7 SOURCE — append at END of `tests/test_daemon.py` (verbatim)

```python
# ===========================================================================
# P1.M2.T1.S1 — lazy load: _load_recorder() single-flight + CPU-fallback migration
# (The CPU fallback MOVED here from main(); main() no longer retries on construction. These tests
#  build a recorder=None daemon + monkeypatch daemon.build_recorder — ZERO real CUDA/models.)
# ===========================================================================


def _make_lazy_daemon(cfg=None):
    """A daemon with NO injected recorder: self._recorder is None, _models_loaded False (the lazy boot state).

    Mirrors production lazy boot. Tests that exercise _load_recorder monkeypatch daemon.build_recorder
    themselves (so construction stays hermetic)."""
    cfg = cfg or VoiceTypingConfig()
    fb = _DaemonFakeFeedback()
    return daemon.VoiceTypingDaemon(cfg, fb, recorder=None, backend=_FakeBackend(), mic_prober=_ok_probe), fb


def test_lazy_daemon_boots_unloaded_with_no_recorder():
    """A recorder-less daemon boots lazy: _recorder None, _models_loaded False (§4.2bis)."""
    d, _fb = _make_lazy_daemon()
    assert d._recorder is None
    assert d._models_loaded is False
    assert d._loading is False
    assert d._load_error is None


def test_load_recorder_success_loads_and_marks_loaded(monkeypatch):
    """_load_recorder() builds via build_recorder + flips _models_loaded; returns True."""
    d, fb = _make_lazy_daemon()
    built = {"n": 0, "force_cpu": None}

    def fake_build(cfg, feedback, latency=None, force_cpu=False, on_speech=None):
        built["n"] += 1
        built["force_cpu"] = force_cpu
        return _StubRecorder()

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    assert d._load_recorder() is True
    assert built["n"] == 1 and built["force_cpu"] is False
    assert d._recorder is not None and d._models_loaded is True
    assert d._load_error is None
    assert fb.phases[-1] == "idle"          # phase driven to 'idle' on success


def test_load_recorder_is_noop_once_loaded(monkeypatch):
    """A second _load_recorder() after success does NOT call build_recorder again (resident)."""
    d, _fb = _make_lazy_daemon()
    built = {"n": 0}

    def fake_build(*a, **k):
        built["n"] += 1
        return _StubRecorder()

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    assert d._load_recorder() is True
    assert d._load_recorder() is True       # resident -> no-op
    assert built["n"] == 1                  # build_recorder called exactly ONCE


def test_load_recorder_cpu_fallback_on_cuda_failure(monkeypatch, caplog):
    """First (cuda) build fails -> retry with force_cpu=True -> loaded (migrated from main())."""
    d, _fb = _make_lazy_daemon()
    attempts = {"n": 0, "force_cpu": []}

    def fake_build(cfg, feedback, latency=None, force_cpu=False, on_speech=None):
        attempts["n"] += 1
        attempts["force_cpu"].append(force_cpu)
        if not force_cpu:
            raise RuntimeError("cuda construction failed")
        return _StubRecorder()

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
        assert d._load_recorder() is True
    assert attempts["n"] == 2                           # cuda attempt + cpu retry
    assert attempts["force_cpu"] == [False, True]
    assert d._recorder is not None and d._models_loaded is True
    assert d._resolved_device()["device"] == "cpu"      # cache seeded -> status reports the ACTUAL cpu device
    msgs = [r.getMessage() for r in caplog.records]
    assert any("falling back to CPU" in m and "degraded but functional" in m for m in msgs), msgs


def test_load_recorder_total_failure_stays_unloaded(monkeypatch):
    """Both cuda + cpu builds fail -> False, NO half-built recorder, _load_error set (§4.2bis)."""
    d, _fb = _make_lazy_daemon()

    def fake_build(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    assert d._load_recorder() is False
    assert d._recorder is None                           # NO half-built recorder
    assert d._models_loaded is False
    assert d._load_error is not None and "CPU fallback" in d._load_error


def test_start_on_lazy_daemon_triggers_load_then_arms(monkeypatch):
    """start() on an unloaded daemon loads the recorder, then arms (set_microphone True)."""
    d, _fb = _make_lazy_daemon()
    rec = _StubRecorder()
    monkeypatch.setattr(daemon, "build_recorder", lambda *a, **k: rec)
    d.start()
    assert d._models_loaded is True
    assert d.is_listening() is True
    assert rec.mic == [True]                             # armed


def test_start_suppressed_when_load_fails(monkeypatch):
    """A failed load -> start() returns without arming (stays not-listening, §4.2bis)."""
    d, _fb = _make_lazy_daemon()

    def fake_build(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    d.start()
    assert d._models_loaded is False
    assert d.is_listening() is False                     # stayed unarmed


def test_injected_recorder_is_loaded_at_construction():
    """A pre-injected recorder (the _make_daemon pattern) -> _models_loaded True at boot (no lazy)."""
    d, _fb, _rec, _be = _make_daemon()
    assert d._recorder is not None
    assert d._models_loaded is True                      # tests that inject get a loaded daemon immediately


def test_load_recorder_single_flight_one_build_under_concurrency(monkeypatch):
    """Two concurrent _load_recorder() calls -> exactly ONE build_recorder (the 2nd waits, §4.2bis)."""
    import threading as _t
    d, _fb = _make_lazy_daemon()
    built = {"n": 0}
    started = _t.Event()
    release = _t.Event()

    def fake_build(cfg, feedback, latency=None, force_cpu=False, on_speech=None):
        built["n"] += 1
        started.set()
        release.wait(2.0)            # make the load slow so the 2nd caller arrives while _loading
        return _StubRecorder()

    monkeypatch.setattr(daemon, "build_recorder", fake_build)
    results = []

    def caller():
        results.append(d._load_recorder())

    t1 = _t.Thread(target=caller)
    t2 = _t.Thread(target=caller)
    t1.start()
    assert started.wait(2.0)         # ensure the loader is mid-build before the 2nd starts
    t2.start()
    release.set()                    # let the load finish
    t1.join(2.0)
    t2.join(2.0)
    assert built["n"] == 1           # exactly ONE build (single-flight)
    assert results == [True, True]   # both callers see success (2nd waited for the 1st)
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — single-flight load with WAIT (Condition over _lock). Waiters block on the in-flight load; the loader
# builds OUTSIDE _lock then publishes + notify_all under _lock. A resident recorder short-circuits to True.
with self._lock:
    if self._models_loaded: return True
    if self._loading:
        while self._loading: self._load_cond.wait()
        return self._models_loaded
    self._loading = True; self._feedback.set_phase("loading")
recorder = build_recorder(...)                 # OUTSIDE _lock (~1-3s; status/stop stay responsive)
with self._lock:
    self._loading = False; install...; self._load_cond.notify_all()

# PATTERN 2 — load hoisted to start/toggle (NOT _arm). _arm holds _lock; _load_recorder can't nest in it (deadlock).
def start(self):
    if not self._load_recorder(): return       # outside _lock
    with self._lock: self._arm()

# PATTERN 3 — migrated CPU fallback. First build Exception -> one force_cpu=True retry -> seed _resolved_device_cache
# on success (status reports cpu). On total failure: _recorder stays None (no half-built recorder).
try: recorder = build_recorder(...)
except Exception as exc:
    logger.warning("...falling back to CPU..."); recorder = build_recorder(..., force_cpu=True); fell_back=True
```

### Integration Points

```yaml
UPSTREAM CONSUMED — build_recorder/_construct (UNCHANGED): force_cpu + on_speech already supported; _load_recorder calls
  build_recorder(self._cfg, self._feedback, self._latency, on_speech=self._touch_speech) (+ force_cpu=True on the retry).
  _resolved_device_cache extension point reused (seeded on the CPU-fallback path).

DOWNSTREAM — P1.M2.T1.S2 (loading hint through ctl): consumes the phase ('loading') + will read self._models_loaded /
  _load_error in status to print 'loading models…'. T1.S1 drives phase via set_phase + maintains self._models_loaded/
  _load_error; T1.S2 surfaces them. No overlap (T1.S2 edits ctl.py + status rendering).

DOWNSTREAM — P1.M2.T2.S1 (feedback models_loaded + status_snapshot/ctl exposure): OWNS adding models_loaded to feedback +
  exposing phase/models_loaded in status_snapshot/ctl. T1.S1 does NOT edit feedback.py (it drives phase via the existing
  set_phase + tracks daemon-side self._models_loaded). T2.S1 reads self._models_loaded (daemon attr) or adds a setter.

DOWNSTREAM — P1.M3 (idle-unload watchdog): will reuse self._load_cond (Condition over _lock) for the teardown-vs-load race
  (an arm racing an idle-unload teardown waits, then loads fresh). T1.S1 establishes the Condition; M3 adds the unload.

UNCHANGED: _construct/build_recorder/cfg_to_kwargs, cuda_check.py, _resolve_device_config, _bounded_shutdown/shutdown
  (already None-safe), config.py/config.toml, feedback.py, ctl.py, typing_backends.py, systemd unit, ControlServer protocol.

PARALLEL — P1.M1.T2.S1 (systemd TimeoutStopSec): edits systemd/ only; NO overlap with daemon.py/test_daemon.py.

BUILD ARTIFACTS: NO new files, NO pyproject/uv.lock/.venv changes, NO new deps. Validation = py_compile + pytest.
```

## Validation Loop

> Full paths in every bash command (zsh aliases — Gotcha #10). Run from `/home/dustin/projects/voice-typing`. pytest is
> the runner (NO ruff/mypy — Gotcha #11). All gates are hermetic/unit (build_recorder stubbed; NO real CUDA/models).

### Level 1: source compiles + the structural changes are present

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/daemon.py && echo "L1 PASS: py_compile" || echo "L1 FAIL"
echo "--- _load_recorder exists; __init__ no longer eagerly builds ---"
grep -q "def _load_recorder" voice_typing/daemon.py && echo "L1 PASS: _load_recorder present" || echo "L1 FAIL"
grep -qE "self\._recorder = recorder$" voice_typing/daemon.py && echo "L1 PASS: lazy __init__ (self._recorder = recorder)" || echo "L1 FAIL: still eager"
grep -q "self._models_loaded = recorder is not None" voice_typing/daemon.py && echo "L1 PASS: _models_loaded attr" || echo "L1 FAIL"
grep -q "threading.Condition(self._lock)" voice_typing/daemon.py && echo "L1 PASS: _load_cond Condition" || echo "L1 FAIL"
echo "--- main() no longer retries on construction ---"
! grep -q "daemon started in degraded CPU mode (construction-failure fallback)" voice_typing/daemon.py && echo "L1 PASS: main() retry removed" || echo "L1 FAIL: main() retry still present"
echo "--- 8 None-guards (shutdown's existing guard NOT re-added) ---"
grep -c "if self._recorder is not None:" voice_typing/daemon.py   # expect >= 8 new + the run()/start/toggle hoist
# Expected: py_compile clean; _load_recorder + lazy __init__ + _models_loaded + Condition present; main() retry gone.
```

### Level 2: the new lazy-load tests + the full fast suite

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_daemon.py -k "load_recorder or lazy_daemon or start_on_lazy or start_suppressed or injected_recorder or single_flight" -v
# Expected: the new _load_recorder section passes (boot unloaded, success, no-op-once-loaded, CPU fallback, total
# failure, start-triggers-load, start-suppressed, injected-is-loaded, single-flight).
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (The 4 obsolete main()-fallback tests are GONE; BoomDaemon cleaned; everything else unchanged.)
```

### Level 3: hermetic lazy-boot proof (no build_recorder / no RealtimeSTT at construction)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" - <<'PYEOF'
import sys, importlib
# A recorder-less daemon must construct with NO build_recorder call + NO RealtimeSTT import.
import voice_typing.daemon as d
from voice_typing.config import VoiceTypingConfig
calls = {"n": 0}
def spy(*a, **k):
    calls["n"] += 1
    raise AssertionError("build_recorder must NOT run at construction (lazy)")
d.build_recorder = spy
class FakeFB:
    def set_phase(self, p): pass
    def set_listening(self, x): pass
    def update_partial(self, t): pass
    def record_final(self, t): pass
    def snapshot(self): return {}
daemon = d.VoiceTypingDaemon(VoiceTypingConfig(), FakeFB(), recorder=None)
assert daemon._recorder is None and daemon._models_loaded is False, "must boot lazy"
assert calls["n"] == 0, "build_recorder ran at construction!"
assert "RealtimeSTT" not in sys.modules, "RealtimeSTT imported at construction!"
print("L3 PASS: lazy boot — no build_recorder, no RealtimeSTT, _recorder is None")
PYEOF
```

### Level 4: existing behavior preserved for injected-recorder daemons (regression)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_daemon.py -k "test_start_arms or test_stop_disarms or test_toggle or test_run_loop or test_run_logs_resolved_device or test_shutdown or test_request_shutdown or status_snapshot" -v
# Expected: all pass UNCHANGED — _make_daemon injects a recorder -> _models_loaded=True -> lazy path dormant -> the 8
# guards see non-None -> identical behavior to pre-change.
```

### Level 5: scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY voice_typing/daemon.py (modified) + tests/test_daemon.py (modified). No feedback.py, no config, no
# systemd, no ctl.py, no README, no pyproject/uv.lock. (P1.M1.T2.S1 edits systemd/ in parallel — separate file.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: py_compile clean; `_load_recorder` + lazy `__init__` + `_models_loaded` + `Condition` present; main() retry gone.
- [ ] L2: new `_load_recorder` tests pass; full fast suite 0 failed.
- [ ] L3: a recorder-less daemon constructs with NO `build_recorder` call + NO RealtimeSTT import.
- [ ] L4: injected-recorder tests (start/stop/toggle/run-loop/shutdown/status) pass unchanged.
- [ ] L5: `git status` == `voice_typing/daemon.py` + `tests/test_daemon.py` only.

### Feature Validation
- [ ] Boot lazy (`_recorder None`, `_models_loaded False`, phase `'unloaded'`); first arm loads (~1-3s) then arms; subsequent arms instant.
- [ ] CPU fallback lives in `_load_recorder()` (first build fail → `force_cpu=True` retry → seed cache → status `device=cpu`).
- [ ] Total load failure → `_recorder` stays None (no half-built recorder), `_load_error` set, arm suppressed.
- [ ] Single-flight: concurrent `_load_recorder()` → exactly one `build_recorder`; 2nd waits + returns 1st's result.
- [ ] All 8 unguarded call sites None-guarded; `shutdown()` untouched.

### Code Quality Validation
- [ ] Load hoisted to start/toggle (NOT `_arm`) — deadlock-free.
- [ ] Heavy `build_recorder()` runs outside `_lock`.
- [ ] feedback.py NOT edited (T2 boundary); phase driven via existing `set_phase`; `_models_loaded` is a daemon attr.
- [ ] Docstrings updated (module-top LAZY LOAD, CONSUMED BY, class docstring).

### Scope Boundary Validation
- [ ] No feedback.py / config.py / config.toml / ctl.py / systemd / README / pyproject / uv.lock changes.
- [ ] The 4 obsolete main()-fallback tests removed; BoomDaemon cleaned; `test_log_resolved_device_reads_cache_after_cpu_fallback` kept.

---

## Anti-Patterns to Avoid

- ❌ Don't call `_load_recorder()` from inside `_arm()` — `_arm` holds `_lock`; `_load_recorder` acquire-release-reacquires that lock → deadlock. Hoist to start/toggle.
- ❌ Don't build the recorder inside `_lock` — the ~1-3s load would wedge status/stop/toggle. Build outside, install under.
- ❌ Don't implement single-flight as "return False if loading" — the PRD requires WAIT (per-connection threading model). Use the Condition.
- ❌ Don't edit `feedback.py` — T2 (P1.M2.T2.S1) owns `models_loaded` there. Drive `phase` via the existing `set_phase`; track `_models_loaded` on the daemon.
- ❌ Don't leave the 4 main()-CPU-fallback tests in place — migrating the fallback makes them assert obsolete behavior (they break). Remove + replace with `_load_recorder` tests.
- ❌ Don't re-add a `None`-guard in `shutdown()`/`_bounded_shutdown()` — already None-safe (M1 landed).
- ❌ Don't call `_log_resolved_device()` at a lazy boot — it probes cuda_check + logs a misleading "device=cuda". Guard it in `run()`; call it on load success.
- ❌ Don't seed `_resolved_device_cache` on the non-fallback (cuda) success path — let `_resolved_device()` lazily probe cuda (the loaded recorder IS cuda).
- ❌ Don't change `_make_daemon` — it always injects a recorder (the safety net that keeps the existing suite green).
- ❌ Don't forget `notify_all()` after install/fail — waiters would hang.
- ❌ Don't invent ruff/mypy commands — pytest only. Don't use bare python/pytest/uv (zsh aliases).

---

## Confidence Score

**9/10** for one-pass implementation success. The lazy-load design is fully specified with verbatim source for every concurrency-critical edit (`__init__`, `_load_recorder`, start/toggle/stop/run/main); the deadlock (load-can't-nest-in-`_arm`) is analyzed and resolved (hoist to start/toggle — matching delta_prd "await it before arming"); the single-flight Condition design is concrete; the CPU-fallback migration + its exact test impact (4 obsolete tests removed, BoomDaemon cleaned, `test_log_resolved_device_reads_cache` kept, new `_load_recorder` tests added verbatim) are enumerated; and the reason the entire existing suite stays green (`_make_daemon` always injects a recorder → `_models_loaded=True` → lazy path dormant) is documented. The residual uncertainty (−1): the toggle read/act split introduces a benign race window (acceptable, mirrors the existing abort-outside-`_lock` discipline) and the `_load_cond` Condition semantics must be implemented exactly as written (a missed `notify_all` would hang a waiter) — both are called out as CRITICAL gotchas with verbatim code.
