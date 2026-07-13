# Research — P1.M3.T1.S1 idle-unload watchdog + auto_unload_idle_seconds config knob

Ground truth verified by reading daemon.py / config.py / config.toml / the tests on 2026-07-13.
This is the VRAM-reclamation half of the lazy-load feature (PRD §4.2bis Idle unload): a background
watchdog tears down the resident recorder after the mic has been DISARMED this long, composing with
the existing idle auto-stop. P1.M1 (bounded teardown) + P1.M2.T1 (lazy load) are COMPLETE
prerequisites; P1.M2.T2.S1 (lifecycle state surface) is IN PARALLEL and provides the feedback calls
this task consumes.

---

## 1. The templates (verbatim patterns to mirror)

### 1.1 `_idle_watchdog` (daemon.py:759-770) — the watchdog TICK template
```
def _idle_watchdog(self) -> None:
    while not self._shutdown.wait(1.0):          # ticks ~1s + exits promptly on shutdown
        try:
            self._maybe_auto_stop()
        except Exception:
            logger.exception("idle auto-stop check raised; continuing")
```
`_idle_unload_watchdog` mirrors this EXACTLY (same `self._shutdown.wait(1.0)` tick, same try/except,
calls `_maybe_idle_unload`). Started from `run()` as a daemon thread (see §5).

### 1.2 `_maybe_auto_stop` (daemon.py:733-757) — the deadline-under-lock template
```
def _maybe_auto_stop(self) -> None:
    threshold = self._cfg.asr.auto_stop_idle_seconds
    if threshold <= 0:                  # DISABLED guard
        return
    disarmed = False
    with self._lock:
        if not self._listening.is_set() or self._last_speech_monotonic is None:
            return                      # not applicable
        if time.monotonic() - self._last_speech_monotonic < threshold:
            return                      # not yet
        logger.info("voice-typing auto-stop: ...", threshold)
        self._disarm()
        disarmed = True
    if disarmed and self._recorder is not None:
        self._recorder.abort()          # heavy/nudge OUTSIDE _lock
```
PATTERN: `threshold<=0` disables; re-check the deadline UNDER `_lock`; do the guarded transition
under the lock; heavy work (`abort()`) outside. The idle-unload analog differs in ONE way: the heavy
work (`_bounded_shutdown`) runs UNDER `_lock` (single-flight so a racing arm waits — see §3), NOT
outside. This is deliberate and is the core design decision.

---

## 2. What I CONSUME (prerequisites — COMPLETE or parallel; do NOT edit)

### 2.1 `_load_recorder()` (daemon.py:481-563) — P1.M2.T1.S1, COMPLETE
- Single-flight via `self._load_cond = threading.Condition(self._lock)` (a Condition OVER the SAME
  `_lock`). Under `_lock`: if `_models_loaded` → return True; if `_loading` → wait on `_load_cond`,
  return its result; else set `_loading=True`, RELEASE the lock, run the heavy `build_recorder()`
  OUTSIDE `_lock`, then RE-ACQUIRE `_lock` to publish (`_recorder`/`_models_loaded`/phase/notify).
- So `_load_recorder` acquire-release-reacquires `_lock`. Calling it WHILE holding `_lock` DEADLOCKS
  (Condition.wait needs to release the lock; nested acquire on a non-reentrant Lock blocks forever).
  → `_unload_recorder` must NOT call `_load_recorder`; and `_load_recorder` is called by start/toggle
  OUTSIDE `_lock` (confirmed: start():832 `if not self._load_recorder(): return` BEFORE `with self._lock: self._arm()`).

### 2.2 `_bounded_shutdown(timeout=10.0)` (daemon.py:947-1003) — P1.M1.T1.S2, COMPLETE
- Runs `self._recorder.shutdown()` in a daemon thread under a hard `timeout` (default 10s). On timeout
  it force-terminates `transcript_process` + `reader_process` (the VRAM holders), sets
  `is_shut_down=True`, drops `realtime_transcription_model`. NEVER re-raises. Best-effort throughout.
- READS `self._recorder` directly (e.g. `self._recorder.shutdown()`, `getattr(self._recorder, attr,
  None)`). → the caller MUST still have `self._recorder` set when calling it; null `_recorder` AFTER.
- Does NOT acquire the daemon's `_lock` (it uses its own `done = threading.Event()`). → SAFE to call
  UNDER `_lock` (no reentrancy / no deadlock). This is what makes idle-unload-under-lock viable.
- Bounded ≈ ≤10s. PRD §4.2bis: teardown "MUST be non-blocking and complete in well under the arm-
  latency budget" — 10s worst case (normally faster). A racing arm waits ≤ this. Acceptable per PRD.

### 2.3 The feedback lifecycle surface — P1.M2.T2.S1, IN PARALLEL (treat as contract)
- `self._feedback.set_phase("unloaded")` and `self._feedback.set_models_loaded(False)` both exist
  (P1.M2.T2.S1 adds `set_models_loaded`; `set_phase` already exists). `_unload_recorder` calls BOTH
  after tearing down (mirrors `_load_recorder`'s failure branch: phase 'unloaded' + models_loaded
  False). status_snapshot/ctl already surface phase/models_loaded (P1.M2.T2.S1) → an idle-unload
  transition is visible in `voicectl status` for free.

### 2.4 `run()` (daemon.py:566-610) — starts `_idle_watchdog` at the end of setup
The watchdog-start site (run() ~597-598):
```
        # Idle auto-stop watchdog: disarms after cfg.asr.auto_stop_idle_seconds of no speech.
        threading.Thread(target=self._idle_watchdog, name="voice-typing-idle", daemon=True).start()
```
Add the `_idle_unload_watchdog` thread start IMMEDIATELY AFTER this line (same idiom).

---

## 3. The concurrency model (the core design — read carefully)

**Single-flight under `_lock`:** `_unload_recorder()` acquires `_lock`, re-checks the unload
condition, runs `_bounded_shutdown()` UNDER the lock, then nulls `_recorder` + flips `_models_loaded`.
Because `_load_recorder()`'s FIRST action is `with self._lock:` (to check `_models_loaded`/`_loading`),
an arm that arrives while unload holds the lock BLOCKS there, waits for teardown to release, then sees
`_models_loaded=False`/`_recorder=None` and builds FRESH. An arm can never see a half-torn-down
recorder (PRD §4.2bis). This is exactly the item's clause (g).

**The TOCTOU re-check (load-bearing):** the watchdog's pre-check (`_maybe_idle_unload`) reads state
WITHOUT the lock (atomic bool/float/Event reads — safe in CPython) to avoid acquiring the lock every
1s tick. Between that pre-check and `_unload_recorder` acquiring the lock, an arm could happen. So
`_unload_recorder` MUST re-check the FULL condition under the lock — critically including
`self._listening.is_set()` — so an arm that raced in aborts the unload. (Item clause d says "if not
self._models_loaded → return"; the `_listening` re-check is the race-safety addition. The dedicated
race test is S2 / P1.M3.T1.S2; the re-check makes it correct.)

**Why teardown-under-lock is OK:** `_bounded_shutdown` is bounded (≤10s) and never touches the
daemon's `_lock`. The only callers that block are: the auto-stop watchdog (1s tick — a 10s delay is
harmless), and a racing arm (which is the designed wait-then-load). Control `status` is lock-free
(stays responsive). `on_final` takes `_on_final_lock` (separate) and is gated by `_listening` (cleared
during unload) → no access to a torn-down recorder.

**`_disarmed_monotonic` wiring (composition with auto-stop):**
- `__init__`: `self._disarmed_monotonic: float | None = None` (never disarmed at boot).
- `_arm()`: `self._disarmed_monotonic = None` (armed → unload clock inactive; time listening doesn't count).
- `_disarm()`: `self._disarmed_monotonic = time.monotonic()` (start the unload clock).
- `_disarm` is called by stop(), toggle()-disarm, AND `_maybe_auto_stop()` → so a MANUAL stop, a
  toggle-off, OR the 30s auto-stop ALL start the unload clock. This is the composition the item wants:
  auto-stop disarms at 30s → sets `_disarmed_monotonic` → idle-unload counts 1800s from there →
  unloads at ~30.5 min. (PRD §4.5: "Auto-stop disarms ... starts the slower idle-unload clock.")

---

## 4. The config knob + the REQUIRED test fix

### 4.1 config.py AsrConfig (config.py:49-57) — add the field
Current:
```
    auto_stop_idle_seconds: float = 30.0       # auto-disarm after this many seconds of no recognized
                                               # speech (partials reset the clock); 0 disables
```
Add after it:
```
    auto_unload_idle_seconds: float = 1800.0    # PRD §4.2bis: after this many seconds DISARMED with
                                               # models loaded, tear down the recorder to free VRAM
                                               # (~0); 0 disables (models stay resident until quit)
```

### 4.2 config.toml [asr] — add the line after `auto_stop_idle_seconds` (align the `=` column)
The existing `auto_stop_idle_seconds` line uses an em-dash (—); reproduce exactly in oldText. New line:
```
auto_unload_idle_seconds     = 1800.0             # after this many seconds DISARMED (models loaded, not listening), tear down the recorder to free VRAM (~0). Clock starts on disarm (manual stop, toggle-off, or the auto-stop above); resets on any arm; time listening does NOT count. 0 disables (models stay resident until quit). (PRD 4.2bis Idle unload)
```
(Align the `=` under the other [asr] keys — cosmetic; TOML ignores whitespace, so mis-alignment never
breaks parsing, only the file's tidy style.)

### 4.3 REQUIRED TEST FIX — tests/test_config_repo_default.py
`test_repo_config_toml_has_no_extra_keys()` asserts the EXACT `asr` key set (7 keys). Adding
`auto_unload_idle_seconds` to config.toml BREAKS it unless the expected set is updated. Add the key:
```
        "asr": {
            "final_model", "realtime_model", "language", "device",
            "post_speech_silence_duration", "realtime_processing_pause",
            "auto_stop_idle_seconds", "auto_unload_idle_seconds",
        },
```
Also the test's docstring says "only the 16 schema keys" → now 17; update the count in the docstring.
`test_repo_config_toml_equals_defaults()` STAYS GREEN as long as config.py + config.toml both = 1800.0.

### 4.4 OPTIONAL — tests/test_config.py defaults test (line ~48)
Add `assert cfg.asr.auto_unload_idle_seconds == 1800.0` after the `auto_stop_idle_seconds` assertion.
Not required (the existing test doesn't assert field count), but good coverage. Safe + additive.

---

## 5. Scope boundaries (S1 vs S2 vs T2.S1)

- **P1.M3.T1.S1 (THIS task):** implementation — config knob (config.py + config.toml) + `_disarmed_monotonic`
  wiring (init/_arm/_disarm) + `_idle_unload_watchdog` + `_maybe_idle_unload` + `_unload_recorder` +
  run() thread start + the REQUIRED `test_config_repo_default.py` key-set fix (+ optional test_config
  assertion). [Mode A] AsrConfig docstring + the config.toml comment ARE the documentation.
- **P1.M3.T1.S2 (NEXT):** the dedicated teardown-vs-load RACE-safety test (arm racing idle-unload
  teardown waits then loads fresh). Do NOT write it here.
- **P1.M3.T2.S1 (LATER):** the fast pytest for "idle-unload fire/reset/disable" + lifecycle. Do NOT
  write the full behavior suite here (T2.S1 owns it).
- → S1 ships the implementation + the one required config-test fix, validates via py_compile + the
  existing fast suite (no regression) + a non-committed L3 wiring smoke. The committed idle-unload
  behavior tests are S2/T2.S1.

---

## 6. Validation reality (tooling)
- pytest IS the gate (.venv/bin/python -m pytest). FULL PATHS (zsh aliases python/pytest).
- ruff is a uv tool at /home/dustin/.local/bin/ruff (NOT in .venv) — optional. mypy NOT installed —
  do NOT run it. (Same as every prior task.)
- The fast suite baseline (pre-S1) is green; S1 must keep it green (the only test S1 must touch is
  test_config_repo_default.py). test_feed_audio.py is GPU-gated (excluded via --ignore).

## 7. The log line (pinned verbatim by PRD §4.2bis + the item)
`voice-typing idle-unload: 1800.0s disarmed; unloading models` — use `%.1fs` with the threshold so it
reads the configured value (1800.0 by default). PRD §4.2bis quotes this string exactly.
