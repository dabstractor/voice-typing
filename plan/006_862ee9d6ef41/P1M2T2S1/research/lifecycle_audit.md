# Research — lazy-load lifecycle audit (P1.M2.T2.S1 vs PRD §4.2bis)

This note records the **pre-verified audit findings** for the lazy-load model lifecycle.
The PRP (../PRP.md) embeds this verdict; the implementing agent re-verifies, re-runs the
tests, and transcribes `architecture/gap_lifecycle.md`. **Verdict: COMPLIANT — no defects,
no source changes.**

## 1. Audit target (the 5 item properties a–e + PRD §4.2bis)

| # | item property | PRD §4.2bis clause |
|---|---|---|
| a | `__init__`: recorder=None (host=None), phase='unloaded', models_loaded=False | "boot state is `unloaded`"; "starts with no recorder, no CUDA context, ~0 VRAM" |
| b | `_load_host` acquires the single-flight lock | "A second arm while `loading` MUST NOT start a second load — it waits on the in-flight one (single-flight under a lock)" |
| c | success → `set_models_loaded(True)`, `set_phase('loading' then 'idle')` | states unloaded→loading→loaded/not-listening; "`status` reports `models_loaded: bool`" |
| d | failure → cleanup, return False, feedback stays unloaded, status shows error | "returns to `unloaded`, the arm returns `{ok:false,error}`, MUST NOT leave a half-constructed recorder" |
| e | `_handle_dead_host` resets to unloaded | (robustness; bugfix Issue 3) child death → unloaded → re-spawn on next arm |
| + | boot ~0 VRAM; teardown under the SAME single-flight lock; mode-switch reload | "boot ~0 VRAM"; "Teardown … under the SAME single-flight lock as load"; §4.2ter reload |

## 2. ★ Pre-verified findings: ALL COMPLIANT (code file:line) ★

### (a) boot state — daemon.py:648-671
Lazy branch (no `recorder`/`recorder_host` injected → production): `self._host = None`
(657), `loaded = False` (657), `self._models_loaded = loaded`→False (659),
`self._loading = False` (660), `self._load_error = None` (661), then
`self._feedback.set_phase("idle" if loaded else "unloaded")`→**"unloaded"** (670) +
`self._feedback.set_models_loaded(loaded)`→**False** (671). ✅ Matches PRD §4.2bis boot.
(The injected branch sets loaded=True/phase="idle" — correct for tests/pre-built; the
PRD boot requirement applies to the no-injection production path.)
Tests: `test_lazy_daemon_boots_unloaded_with_no_recorder`, `test_lazy_boot_records_unloaded_phase`.

### (b) single-flight lock — daemon.py:665, 714-724
`self._load_cond = threading.Condition(self._lock)` (665) — the SAME lock `_load_host`
takes. Under `with self._lock` (714): a second caller hitting `if self._loading:` (721)
loops `while self._loading: self._load_cond.wait()` (722-723) and returns the in-flight
result (`return self._models_loaded and ...`, 724) — it NEVER starts a 2nd spawn. The
heavy `host.spawn()` runs OUTSIDE `_lock` (744-759) so concurrent status/stop stay
responsive. ✅ Matches "waits on the in-flight one; single-flight under a lock."
Tests: `test_load_recorder_single_flight_one_build_under_concurrency`,
`test_load_and_unload_serialize_on_the_same_single_flight_lock`,
`test_arm_racing_unload_waits_then_loads_fresh`.

### (c) success transitions — daemon.py:727-728, 772-773
Load start (under lock): `set_phase("loading")` + `set_models_loaded(False)` (727-728).
On success (under lock): `set_phase("idle")` + `set_models_loaded(True)` (772-773). So the
transition is exactly **unloaded → loading → idle**, with models_loaded False→True. ✅
Matches item (c) verbatim + PRD §4.2bis states. (`self._mode = mode` @766 + device-cache
seed @770 are the §4.2ter/status refinements — correct, not defects.)
Tests: `test_start_on_lazy_daemon_triggers_load_then_arms`, `test_cold_first_arm_fires_loading_toast`,
`test_warm_arm_fires_no_loading_toast`.

### (d) failure cleanup — daemon.py:781-794
On spawn failure (under lock): `host.stop()` best-effort (781-783, in a try/except → **NO
half-built recorder** — §4.2bis), `self._load_error = "recorder host spawn failed"` (782),
`self._models_loaded = False` (783), `self._host = None` (784), `set_phase("unloaded")`
(785), `set_models_loaded(False)` (786), `notify_all()` (787), `success = False` (788).
Returns False (794). The arm path then returns `{ok:false,error}` (control-socket layer).
`status_snapshot` surfaces `_load_error` (load_error field). ✅ Matches "returns to
unloaded; arm returns {ok:false,error}; NO half-built recorder; status reports the error."
Tests: `test_load_recorder_total_failure_stays_unloaded`.

### (e) dead-child recovery — daemon.py:840-846 (run()), 874-903 (_handle_dead_host)
run() top-of-loop liveness check (840): `if self._host is not None and not
self._host.is_alive:` → WARNING with pid (841-844) → `_handle_dead_host()` → `continue`
(845). `_handle_dead_host` (874): under `self._lock` sets `_host=None`, `_models_loaded=
False`, `_listening.clear()`, `set_phase("unloaded")`, `set_models_loaded(False)`,
`set_listening(False)`, `_load_error="recorder-host child died unexpectedly"`, clears both
idle clocks, + reseeds the device cache (VT-002). Next arm re-spawns
(`_models_loaded=False` defeats the fast-path short-circuit @715). ✅ Matches "resets to
unloaded; next arm re-spawns." Does NOT call `host.stop()` (child already dead) — correct.
Tests: `test_run_loop_detects_dead_host_and_transitions_to_unloaded`,
`test_load_host_respawns_after_dead_child`, `test_status_reports_unloaded_after_child_death`,
`test_text_returns_promptly_if_child_already_dead` (recorder_host).

### (+) boot ~0 VRAM / teardown under same lock / mode-switch
- Boot ~0 VRAM: the daemon process NEVER constructs the recorder — the child owns all CUDA
  contexts (PRD §4.2bis "Implementation note"). `_host=None` at boot. ✅ (VT-001 caveat:
  `voicectl status` once probed CUDA in the daemon — a STATUS concern, audited in M3, NOT
  a lifecycle/boot-state defect; `_handle_dead_host`'s VT-002 device-cache reseed + the
  status device-cache seed on load @770 keep status consistent without daemon-side CUDA.)
- Teardown under the SAME single-flight lock: `_unload_host` (1204) + the mode-switch
  teardown (738) both `with self._lock`. ✅ Tests: `test_load_and_unload_serialize...`,
  `test_arm_racing_unload_waits_then_loads_fresh`. (Bounded teardown detail — the 5 s join
  + killpg — is S3's audit; this audit confirms the LOCKING is shared, not the bound.)
- Mode-switch reload (§4.2ter): wrong-mode resident detected @716-718 (`switch_mode=True`),
  torn down + respawned @736-741. ✅ (Detailed lite/mode-switch audit is M2.T3; this audit
  confirms the reload reuses the same single-flight + lifecycle path.)

## 3. Test evidence (re-ran live)

```
$ timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py \
    -q -k 'load or spawn or dead or unload or boot or unloaded'
43 passed, 176 deselected in 1.13s
```
All 43 lifecycle tests pass. Key evidence tests (cited in §2): single-flight, dead-host
detection + respawn + status, total-failure-stays-unloaded, lazy-boot-unloaded, idle-unload
fire/noop/disable, arm-racing-unload, mode-switch reload.

## 4. Non-defect nuances to record (so they aren't mistaken for gaps)

- **`recorder` → `self._host`:** PRD §4.2/§4.2bis says `recorder`; the code uses `self._host`
  (a `RecorderHost` subprocess, uniform via `_LegacyRecorderHostAdapter` @654 for injected
  stubs). Naming drift, not a defect (the lifecycle semantics match).
- **`_load_recorder` is a back-compat alias** for `_load_host("normal")` (688-697). Not a
  defect — kept so start/toggle call sites + the `recorder=` test seam are unchanged.
- **Mode-switch reload & lite** are §4.2ter (audited in M2.T3); this audit confirms they
  reuse the §4.2bis single-flight + transitions, deferring lite detail.
- **Bounded teardown** (5 s join + killpg) is S3's audit; this audit confirms teardown
  shares the load single-flight lock (the §4.2bis concurrency rule).
- **VT-001/VT-002** (status CUDA probe / device-cache reseed) are STATUS concerns (M3),
  not lifecycle defects. The lifecycle itself never probes CUDA in the daemon.

## 5. Verdict

✅ **The lazy-load lifecycle is PRD §4.2bis-COMPLIANT.** All 5 item properties (a–e) + the
boot-VRAM/teardown-lock/mode-switch points pass with file:line evidence; 43 lifecycle
tests pass. **No source files need modification.** The only new artifact is
`architecture/gap_lifecycle.md` (the report). Adjacent concerns (lite mode, bounded
teardown detail, status reporting) are correctly deferred to M2.T3 / S3 / M3.

## 6. Scope boundary (disjoint from siblings)

- **P1.M2.T1.S2** (parallel): graceful-DRAIN audit (§4.2 #2), appends to
  `gap_daemon_loop.md`. It explicitly defers `_handle_dead_host` to THIS task and teardown
  to S3. Disjoint.
- **P1.M2.T2.S2** (S2): recorder-host IPC audit. **P1.M2.T2.S3** (S3): bounded teardown
  audit. **P1.M2.T3**: lite/mode-switch audit. **P1.M3**: status/feedback audit (incl.
  VT-001/VT-002). This task (S1) owns the lazy-load STATE MACHINE + single-flight + boot
  state + dead-host recovery ONLY.