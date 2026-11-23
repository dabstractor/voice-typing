# Research Note — P1.M2.T2.S4: Failure discipline wrappers (non-blocking, bounded, idempotent)

## §0 — What landed so far (D1 chain state at research time)

| Item | Artifact | State |
|---|---|---|
| P1.M2.T1.S1 | `AudioConfig` in config.py/config.toml (24→26 keys) | ✅ landed |
| P1.M2.T2.S1 | `voice_typing/audio_ducking.py` (183 L): `PlayerState` + `DuckBackend` protocol + `AudioDucker` bookkeeping | ✅ landed, **FROZEN** (do not edit) |
| P1.M2.T2.S2 | `voice_typing/ducking_mpris.py`: `BusctlMprisBackend` (timeout=1.0 busctl; volume methods stubbed) | ✅ landed |
| P1.M2.T2.S3 | `voice_typing/ducking_volume.py`: `WpctlVolumeBackend` (node-id pin; MPRIS stubs) | 🔨 implementing per its PRP (treat as contract; do NOT import in tests — parallel) |
| **S4 (this)** | async-dispatch discipline wrappers | research done here |
| P1.M2.T3.S1/S2 | daemon wiring at `_arm()`/`_disarm()`/`request_shutdown()` + crash safety (`ducked` flag, ExecStopPost) | planned — CONSUMES S4 |

## §1 — Why a wrapper is needed (the lock discipline, verified)

- **The arm toast site runs UNDER `self._lock`.** `_arm()` (daemon.py ~1410, docstring: "set_listening(True) fires the transient 'Recording' start toast") is called under `self._lock` by `start()` (~2124) and `toggle()` (~2150). `_disarm()` likewise. A ducking engage called inline would hold the CONTROL LOCK while running ≤1 s subprocess calls (up to ~2 s+ for mpris with several players) — the exact NEW-2 wedge class: a blocking call under `_lock` serializes every later start/stop/toggle → `voicectl` hits `timeout` → exit 124. Precedent: `abort()` was moved OUT of `_lock` for this reason (`_disarm` docstring ~1422-1436; `_safe_abort` docstring ~2086-2114 "Never re-raises").
- **The prescribed shape** (seams doc §1c, and the item's RESEARCH NOTE): fire-and-forget spawn — "a short-lived daemon thread, same shape as the signal handler's spawn (daemon.py:2738-2742, the `voice-typing-signal-shutdown` thread)". Threads at the call sites today: control-socket per-connection workers (~2604/2657), the idle watchdog, the KeyListener reader thread, SIGTERM thread (~2741). `Feedback` methods are lock-free (feedback.py:44-52) — irrelevant here but confirms no hidden lock.
- **S1's AudioDucker is already internally idempotent + lock-serialized + swallow-wrapped** (`_call` turns any backend exception into ONE warning). What it does NOT give: (a) non-blocking entry for the caller, (b) dispatch-level coalescing, (c) ordering across rapid arm→disarm→arm.

## §2 — ★ The design: single-flight latest-wins dispatcher ( AsyncDucker )

**File:** `voice_typing/ducking_async.py` (new; `audio_ducking.py` stays frozen; S2/S3 files untouched → parallel-safe, 2-file git scope).

**Why NOT naive per-call threads:** three racing threads (engage, release, engage) contend on the inner ducker's `threading.Lock` in ARRIVAL order, not request order. A release that lands before the first engage leaves media ducked while disarmed (stale engage applied last). Idempotence of the inner ducker does not fix ORDER. The fix: the wrapper keeps the LATEST desired state; at most ONE worker thread is alive; the worker loop applies pending states until none remain.

```python
class AsyncDucker:
    """Failure-discipline wrapper (PRD §4.2quinquies): non-blocking, bounded, idempotent.

    Wraps an AudioDucker for the daemon's arm/disarm seams (T3). engage()/release()
    NEVER block the caller (they only record desired state + maybe spawn one daemon
    worker), never raise, and coalesce: repeated arms apply the backend once.
    """
    def __init__(self, ducker) -> None:
        self._ducker = ducker
        self._lock = threading.Lock()       # tiny, never held across backend calls
        self._desired: bool | None = None   # True=engage, False=release, None=idle
        self._alive = False
        self._applied = threading.Event()   # set each time the worker drains the queue

    def engage(self) -> None:   self._dispatch(True)
    def release(self) -> None:  self._dispatch(False)

    def _dispatch(self, engaged: bool) -> None:
        # Never a gate: any failure here is one WARNING and we move on.
        try:
            spawn = False
            with self._lock:
                if self._desired is None and self._alive and engaged == self._last_applied_or_pending():
                    ...
```
(Refined below — implement EXACTLY this state machine:)
```python
    def _dispatch(self, engaged: bool) -> None:
        try:
            spawn = False
            with self._lock:
                if self._desired == engaged:
                    # same state already pending (or None and worker about to idle):
                    # coalesce — do nothing. (Covers repeated engage under slow worker.)
                    if self._desired is not None:
                        return
                self._desired = engaged
                self._applied.clear()
                if not self._alive:
                    self._alive = True
                    spawn = True
            if spawn:
                threading.Thread(target=self._worker, name="vt-ducking", daemon=True).start()
        except Exception:
            logger.warning("ducking: async dispatch failed; continuing")

    def _worker(self) -> None:
        while True:
            with self._lock:
                state, self._desired = self._desired, None
                if state is None:
                    self._alive = False
                    self._applied.set()
                    return
            try:
                if state:
                    self._ducker.engage()
                else:
                    self._ducker.release()
            except Exception:
                logger.warning("ducking: async %s failed; continuing",
                               "engage" if state else "release")
            with self._lock:
                self._applied.set()
```
Notes:
- **Caller bound:** `_dispatch` is O(µs): one uncontended tiny-lock acquire + optional thread spawn. Even with the backend hung 5 s, engage() returns instantly (case d).
- **Idempotence (case e):** repeated `engage()` while pending → coalesced to one desired=True. Even if the worker already TOOK True (desired=None) and a second engage arrives, it re-queues True; the inner `AudioDucker.engage()` no-ops (already `_engaged`) → ZERO extra backend calls in both layers. Belt and suspenders.
- **Ordering:** latest-wins. engage→release→engage quickly: the worker may coalesce to a single final state (e.g. ends engaged, one duck application) or apply each in order — either way the FINAL state matches the LAST request and no stale engage survives. Test asserts final-state correctness, not intermediate counts, EXCEPT the plain repeated-engage case (exactly one backend application).
- **Hung backend semantics:** a hung call violates the tiers' own ≤1 s contract (S2/S3 enforce `timeout=1.0`); the wrapper's job is only that the CALLER never waits (case d) and the desired state is eventually applied. No watchdog-kill of the worker — thread murder adds risk for zero product value (crash safety is T3.S2's `ducked` flag + ExecStopPost).
- **`flush(timeout=2.0)` for T3's quit path:** best-effort bounded join — wait until `self._desired is None and not self._alive` (all pending applied) or timeout; returns bool; NEVER raises. Daemon threads die at process exit, so quit wants a bounded flush before teardown; the `ducked` latch + ExecStopPost still backstop a hard exit (T3.S2's scope).
- **`engaged` property:** proxies `self._ducker.engaged` (read-only, T3/status may consume).
- **Constructor takes the ducker (or any object with engage/release)** — duck-typed; tests inject S1's real `AudioDucker` over the `_FakeBackend` pattern from tests/test_ducking.py (mutating players/volume, optional `fail`, plus a new `sleep` set for the hung-backend tests).

## §3 — The hung-backend fake (test seam extension)

Reuse S1's `_FakeBackend` shape (tests/test_ducking.py:34-80) + add `slow={"get_sink_volume_pct": 5.0}` style map: `_enter` sleeps before answering (NO real subprocess, NO CUDA). Poll helper `_wait_until(pred, timeout, interval=0.02)` mirrors test_daemon.py's `_wait_for`. All timing asserts use generous bounds: caller-return < 0.5 s (PRD: arm latency must not measurably change; tier budget is 1 s), flush < 2.5 s. Total suite wall time ≪ the 300 s pytest timeout.

## §4 — PRD test-case mapping (§4.2quinquies "Tests")

| PRD case | S4 test | Assertion |
|---|---|---|
| (d) hung backend (mocked 5 s sleep) does not delay arm beyond bound | `test_engage_returns_promptly_with_hung_backend` + release variant | `t(engage()) < 0.5 s` with `get_sink_volume_pct` sleeping 5 s; arm-equivalent caller unaffected |
| (e) engage/release idempotence | `test_repeated_arms_do_not_stack_*` (mpris + volume) | 3× engage → ONE pause round / ONE volume set (coalesced + inner no-op); release-without-engage → ZERO backend calls |
| — (order) | `test_arm_disarm_arm_latest_state_wins` | rapid E,R,E ends ENGAGED (volume at duck pct, no restore write pending); rapid E,R,R ends RELEASED |
| — (never a gate) | `test_dispatch_never_raises` | backend `fail` on everything → engage/release return normally, exactly ≤1 WARNING per failure path |
| — (off mode) | `test_off_mode_zero_backend_calls` | inner ducker mode="off": engage+release+flush → 0 backend calls |
| — (quit seam) | `test_flush_bounded_and_true_when_drained` / `test_flush_bounded_false_when_hung` | flush returns True fast when idle; returns False within bound with a hung backend (never hangs) |
| — (thread shape) | `test_worker_is_short_lived_daemon_thread` | during a hung engage, exactly one `vt-ducking` thread exists and `daemon=True`; after drain, gone |

Target: **10 tests** in `tests/test_ducking_async.py`, all CUDA/subprocess/daemon-free.

## §5 — Scope guards

- DO NOT edit `audio_ducking.py` / `test_ducking.py` (S1 frozen), `ducking_mpris.py` / `ducking_volume.py` (S2 landed / S3 parallel), daemon/config/feedback/systemd (T3/T4 + landed), PRD/tasks/snapshot/.gitignore.
- DO NOT import `ducking_volume` in tests (S3 may not have landed when S4 runs) — fakes only. `ducking_mpris` importable but unnecessary; keep zero tier imports → the module works with ANY engage/release pair.
- AGENTS.md: every pytest under `timeout N` + bash-tool timeout; FULL paths `.venv/bin/python -m pytest`; no daemon ever runs in these tests.
- Mode A docs: module docstring carries the design (lock-discipline rationale w/ NEW-2 + signal-spawn precedents, latest-wins rationale, flush contract, T3/T4 handoff, ownership map).

## §6 — Validation (verified commands, matching sibling PRPs)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_ducking_async.py -v          # 10 passed
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # no NEW failures vs tests/G1_BASELINE.md
/home/dustin/.local/bin/ruff check voice_typing/ducking_async.py tests/test_ducking_async.py   # optional
git status --short   # == the 2 new files only (+ parallel siblings' files)
```
