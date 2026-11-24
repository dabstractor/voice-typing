# Research — P1.M2.T1.S2: Start the production IM route on the bulk arm worker

> All facts verified live at HEAD. Sources: `architecture/bulk_delivery_gate.md` §4 (feasibility),
> `voice_typing/daemon.py` (720-774, 1063-1073, 2085-2160), `voice_typing/ime/manager.py`,
> `voice_typing/ime/target.py`, `voice_typing/ime/ime_host.py`, `tests/g5_timing_lab.py` (GtkRoute
> bridge @303-311, 363+), `tests/conftest.py::hermetic_cfg` (P1.M1.T1.S2).

## 1. The gap (production GTK parity)

- `_build_default_bulk_target` (daemon.py:761-774) returns a **pure** `_BulkTargetBundle`
  (`ImeProcess(on_delivery_state=...)` + `ImeTarget(proc)`); its docstring *claims* "ImeProcess.spawn
  happens lazily inside acquire() on the vt-bulk-arm thread" — **that is false**.
- `ImeTarget.acquire` (ime/target.py) does `self._proc.request("acquire", timeout=...)`.
- `ImeProcess.request` (manager.py:219-229) returns **None unless `self._state == "running"`**
  (and spawn() is never called anywhere on the default route). ⇒ in production every
  `ctrl.acquire()` on the default route fails → `AcquireResult(ok=False, reason="ime no reply")` →
  the arm thread writes `delivery_state="unsupported"` and **production GTK can never acquire**.
- The G5 lab masks this: `tests/g5_timing_lab.py` GtkRoute (~303-311, comment verbatim: "builds the
  bundle PURE ('spawn is lazy inside acquire') but ImeTarget [request returns None unless running;
  the] child is never spawned. This factory therefore does the G3 start_adapter …") — a lab-only
  spawn/activation loop in `bulk_target_factory`. So route acceptance never exercised the real
  startup path. **P1.M2.T1.S4 must consume the production route in the disposable compositor.**

## 2. The machinery available for the fix (verified)

- `ImeProcess.spawn(timeout=None) -> bool` (manager.py:146-219): starts the child
  (`python -m voice_typing.ime.ime_host`, own session/pgroup) + **requires one id-echoing ping
  reply within `timeout`** → RUNNING. Semantics (docstring): True iff RUNNING; "starting" → False;
  **UNSUPPORTED/FAULT spawn is the sanctioned next-arm respawn** (implicit bounded stop of any
  leftover, fresh Popen — never two children); child `unavailable` during starting (fcitx5 holds
  the seat) → False with state UNSUPPORTED; readiness timeout/child death → bounded teardown →
  FAULT → False. Idempotent while RUNNING.
- `ImeProcess.state` property → `idle | starting | running | unsupported | fault`; `healthy()` →
  RUNNING + one short ping round-trip; `stop(timeout)` → bounded teardown (never two children).
- **Activation vs. ping echo**: spawn's ping requirement proves the *process* is up, but the IM
  must also be *activated* by the compositor before acquire can succeed — `ime_host._acquire`
  (ime_host.py:156-161) refuses when `not self.activated` (`ok=False, reason="not activated"`).
  The **read-only** way to observe activation: `request('ping')` — its reply carries
  `activated=self.activated` (ime_host.py:139-141). Hence: **spawn → bounded read-only ping pump
  until `activated=True` → acquire**. `self.activated` flips True on the `activate` event and False
  on `deactivate` (ime_host.py:86-96).
- The arm worker today (`_bulk_begin_delivery` → `_arm_work`, daemon.py:2085-2142): epoch check at
  entry → stop any stale active ctrl (`ctrl.stop(leave=True)`) → **fresh bundle per lifetime**
  (`self._bulk_target_factory(self._cfg)`) → `BulkController(...)` → `bundle.attach(ctrl)` (fresh
  TakeoverWatch; late-binds `proc._on_event = watch.on_event`, daemon.py:743-748 — works because
  attach precedes any spawn) → `ctrl.acquire()`; on failure → `set_delivery_state("unsupported",
  reason)` + return (recording STAYS armed, R.5) → post-round-trip **epoch+listening re-check**
  (superseded ⇒ `ctrl.stop(leave=True)` + `bundle.teardown()`, never ghost-arm) → `ctrl.arm(gen)`
  + `ctrl.start()` → `_bulk_delivery_active=True` + `set_delivery_state("active")`.
- `_bulk_schedule_stop` → `_stop_work` (daemon.py:2144-2180): epoch guard → `ctrl.stop(leave=True)`
  → `bundle.teardown()` (bounded, never raises; `_proc=None` ⇒ no-op — the fake/test-bundle guard
  at daemon.py:741-743).
- `_BulkTargetBundle.attach` already guards `if self._proc is None: return` (fake bundles carry no
  takeover feed) — the same guard pattern is needed for the new start step.
- Epoch/gen: `_bulk_gen` bumped in `_arm` (daemon.py:1759); `_bulk_epoch` bumped in `_arm` (:1760)
  and on the disarm side (:1865) — the stopper's G11 guard.
- Hermetic test seam (INPUT per the item): `tests/conftest.py::hermetic_cfg` (P1.M1.T1.S2 — duck
  off + private state) applied inside `_make_daemon` (test_daemon.py:687). `bulk_target_factory=`
  is the daemon ctor seam (daemon.py:800, 1063-1069) for fake bundles.

## 3. The fix design (construction stays pure; startup moves to the arm worker)

**New `_BulkTargetBundle.start(timeout) -> str | None`** (daemon.py, next to `attach`/`teardown`):

```python
_IME_ACTIVATE_TIMEOUT_S: float = 2.0   # bounded read-only activation pump deadline
_IME_ACTIVATE_POLL_S: float = 0.05     # ping poll interval (read-only; safe to repeat)

def start(self, timeout: float | None = None) -> "str | None":
    """Start the production IM child on the ARM thread (P1.M2.T1.S2). None = ready to acquire;
    a concise reason = start failed (caller writes delivery_state + tears down). Construction
    stays PURE (_build_default_bulk_target unchanged) — spawn+pump run HERE, out of _lock.
    Fake bundles (_proc is None) are a no-op success (the attach() precedent)."""
    if self._proc is None:
        return None                      # fake/test bundle — nothing to start (attach precedent)
    if not self._proc.spawn():           # lazy child start; idempotent while RUNNING
        st = self._proc.state            # 'unsupported' (seat held) | 'fault' | 'starting'/'idle'
        return "ime seat held (unsupported)" if st == "unsupported" else f"ime spawn failed ({st})"
    deadline = time.monotonic() + (timeout if timeout is not None else _IME_ACTIVATE_TIMEOUT_S)
    while time.monotonic() < deadline:   # read-only pump: ping replies carry activated=
        r = self._proc.request("ping", timeout=_IME_ACTIVATE_POLL_S)
        if r is not None and r.get("activated"):
            return None                  # activated → caller proceeds to acquire
        if epoch-stale-check is the caller's job (see below) ...
        time.sleep(_IME_ACTIVATE_POLL_S)
    return "ime not activated"           # never activated within the bound
```

**`_arm_work` wiring** (between `bundle.attach(ctrl)` and `ctrl.acquire()`, daemon.py:2116-2118):

```python
bundle.attach(ctrl)            # FRESH takeover watch per lifetime (G10) — BEFORE spawn (events!)
start_reason = bundle.start()  # production IM child start + bounded activation pump (P1.M2.T1.S2)
if start_reason is not None:
    bundle.teardown()          # bounded cleanup of any leftover child (idempotent, never raises)
    self._feedback.set_delivery_state("unsupported", start_reason)
    logger.info("bulk delivery start failed: gen=%d reason=%s", gen, start_reason)
    return                     # recording STAYS armed (R.5 — same shape as acquire failure)
if epoch != self._bulk_epoch or not self._listening.is_set():
    ctrl.stop(leave=True); bundle.teardown(); return   # stale/disarm race BEFORE acquire
if not ctrl.acquire():         # existing path, unchanged
    ...
```

Rationale per the rules:
- **Pure construction kept** — `_build_default_bulk_target` byte-identical (only its docstring
  corrected: spawn happens in `bundle.start()` on the arm thread, not "inside acquire()").
- **attach BEFORE start** — the TakeoverWatch late-binds `proc._on_event`; attaching before spawn
  guarantees no child event (incl. a takeover during activation) is missed.
- **Read-only pump** — ping is read-only, so polling/repeating it can never "retry an applied
  edit"; **acquire is still called exactly once** (no retry of possibly-applied mutations, R.5);
  spawn is called once per lifetime (idempotent-while-running; UNSUPPORTED/FAULT respawn is the
  sanctioned NEXT-arm path, so no in-flight replacement).
- **Held seat / unsupported preserved** — spawn's UNSUPPORTED (fcitx5 holds the seat; the reader
  already emitted the ONE reason) maps to the same `set_delivery_state("unsupported", reason)`
  shape as today's acquire failure; fault class from the child still flows through the existing
  `_on_event`/`on_delivery_state` seam.
- **Stale epoch / disarm race** — an explicit epoch+listening re-check right after the subprocess
  round-trips (before acquire) rejects ghost-arms early; the EXISTING post-acquire re-check stays
  (belt and suspenders) and still owns `ctrl.stop(leave=True) + bundle.teardown()` cleanup.
- **Bounded everything** — spawn timeout (ImeProcess's own `_spawn_timeout`), activation pump
  deadline (`_IME_ACTIVATE_TIMEOUT_S=2.0`), teardown bounded (killpg under join). The arm thread
  can never hang the daemon.

## 4. Test plan (hermetic; mock ImeProcess/request/time; fake target + recorder)

All in `tests/test_daemon.py` (additive section; `_make_daemon` + `hermetic_cfg` from conftest;
`bulk_target_factory=` seam for daemon-level cases; direct `_BulkTargetBundle` unit tests for
start()). NO real Popen — fake ImeProcess records spawn/request('ping')/stop and scripts replies.

1. **`test_default_bulk_target_factory_stays_pure`** — monkeypatch `subprocess.Popen` to explode;
   `_build_default_bulk_target(cfg)` returns the bundle with NO subprocess call (construction pure).
2. **`test_bundle_start_spawns_pumps_then_ready`** — fake proc: spawn→True; first k ping replies
   `activated=False`, then `activated=True` (monkeypatch time.monotonic/sleep to skip the waits) →
   `start()` returns None; spawn called once; ≥k pings.
3. **`test_bundle_start_never_activated`** — ping always `activated=False`; time advanced past the
   deadline → `start()` returns a reason containing "not activated"; teardown path exercised by the
   arm wiring.
4. **`test_bundle_start_held_seat`** — `spawn()`→False with `state="unsupported"` → reason contains
   "seat held"/"unsupported"; NO ping issued; NO acquire.
5. **`test_bundle_start_spawn_fault`** — `spawn()`→False with `state="fault"` → reason mentions
   spawn failed; teardown called once (idempotent).
6. **`test_fake_bundle_start_is_noop_success`** — `_BulkTargetBundle(target=fake)` (proc None) →
   `start()` → None (existing injected-fake tests unchanged — the guard).
7. **`test_arm_worker_writes_unsupported_and_stays_armed_on_start_failure`** — daemon in bulk mode,
   factory returns a bundle with the never-activated fake proc; `_arm()`; join the vt-bulk-arm
   thread (or drive `_arm_work` synchronously via a seam); assert `delivery_state=="unsupported"`
   + the concise reason, listening STILL set (R.5), teardown/stop called on the fake, and
   `ctrl.acquire` NEVER called.
8. **`test_arm_worker_rejects_stale_epoch_before_acquire`** — slow-activation fake (pings block on
   an Event); disarm during the pump (epoch bump); release; assert NO active publish
   (`_bulk_delivery_active` False, no "active" state write), teardown ran, no acquire.
9. **`test_fresh_rearm_spawns_fresh_child`** — full happy path (spawn→True, ping activated=True,
   acquire ok) → active; then `_disarm()`/stop (epoch bump, stopper teardown: fake proc.stop
   called); a second `_arm()` builds a NEW bundle (factory called again) and spawns the NEW proc
   → active again. (Never reuses a stopped ImeProcess — the docstring's dead-acquire warning.)
10. **`test_stop_during_startup_tears_down`** — stopper fires while the arm worker is mid-pump
    (epoch guard) → the stale worker's post-start re-check tears down; no double-teardown crash.

Run target: `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'bulk or bundle or
arm_worker'` then the full file (documented baseline) + the full pure sweep.

## 5. Docs (Mode A)

- `_BulkTargetBundle` + `_build_default_bulk_target` docstrings: spawn/activation runs on the
  vt-bulk-arm thread via `bundle.start()` (fix the stale "inside acquire()" claim); the bundle
  owns spawn + the bounded read-only activation pump.
- `README.md:487` "### Bulk delivery: the input-method seat is taken (fcitx5/ibus)" — update to
  the real behavior: the daemon starts its own IM child on first bulk arm and waits (bounded) for
  activation; a held seat surfaces as `delivery: unsupported` with the concise reason. Overview
  claims stay for P1.M2.T3.S2.

## 6. Scope boundaries

- **P1.M2.T1.S1 (parallel)**: the `partial_source` selector in daemon.py/recorder_host.py
  (`_build_callbacks`/`_construct`/`build_recorder`/`_load_host`/spawn args). NO overlap with the
  bulk bundle/arm worker (different functions). S1 lands first; my edits touch `_BulkTargetBundle`
  + `_bulk_begin_delivery._arm_work` + module constants — disjoint regions.
- **P1.M2.T1.S4 (downstream)**: consumes THIS route (the default factory + bundle.start) in the
  disposable compositor — no more lab bridge on the acceptance path.
- UNCHANGED: `_build_default_bulk_target`'s signature/body (docstring only), `ImeProcess`/
  `ImeTarget`/`ime_host`/`TakeoverWatch` internals, `BulkController`, `_on_bulk_stopped` fault
  paths, `_bulk_schedule_stop`, config (no knob), ctl.
