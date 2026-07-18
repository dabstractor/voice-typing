# Gap Report — P1.M2.T2.S1: Lazy-Load Lifecycle vs PRD §4.2bis

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py`'s **lazy-load state machine** against **PRD §4.2bis**
on the **5 item properties (a)–(e)** + the **boot-VRAM / teardown-lock / mode-switch** extras.
The audited code regions are: `VoiceTypingDaemon.__init__` boot state (L648-671), `_load_host`
(L698-795 — single-flight lock + success/failure transitions + mode-switch reload),
`_handle_dead_host` (L874-902 — child-crash recovery), and the `run()` liveness check
(L840-845 — top-of-loop dead-host detection). The `_load_recorder` back-compat alias (L688) and
the idle-unload teardown `_unload_host` (L1204, shares the load single-flight lock) are also
examined for the teardown-lock point. Subtask **P1.M2.T2.S1** of verification round
`006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `__init__` (boot state: `self._host = None` @657, `loaded = False`
  @657, `self._models_loaded = loaded`→False @659, `self._loading = False` @660,
  `self._load_error = None` @661, `self._load_cond = threading.Condition(self._lock)` @665,
  `set_phase("idle" if loaded else "unloaded")`→**"unloaded"** @670,
  `set_models_loaded(loaded)`→**False** @671); `_load_recorder` alias (@688 → `_load_host("normal")`);
  `_load_host` (L698: fast-path/mode-mismatch @715-718, single-flight wait @721-724, loading
  transition @727-728, mode-switch teardown @736-741, heavy spawn OUTSIDE `_lock` @744-759,
  success publish @765-774, failure cleanup @781-794, return @795); `_handle_dead_host` (L874:
  reset under `_lock` @890-902); `run()` liveness (L840-845); `_unload_host` (L1204: teardown under
  `_lock` @1208, full-condition re-check @1225-1231, bounded `host.stop` @1236, reset @1240-1243).
- `tests/test_daemon.py` + `tests/test_recorder_host.py` — the
  `-k 'load or spawn or dead or unload or boot or unloaded'` slice (the contract's run target;
  43 tests; the daemon fakes inject a `_LegacyRecorderHostAdapter` so `self._host` is uniform and
  the lifecycle branches are exercised directly without CUDA; the recorder-host tests drive the
  spawn/ready/error/dead dispatch directly).

**Bottom line:** ✅ All 5 item properties (a)–(e) + the boot-VRAM / teardown-lock / mode-switch
extras are **compliant** (each with file:line evidence below). The
`-k 'load or spawn or dead or unload or boot or unloaded'` slice is
**43 passed, 176 deselected in 1.08s** (re-ran live; matches the verified baseline of 43 passed,
1.13s). Five **non-defect nuances** are recorded so they are not mistaken for gaps (§4).
**No source files were modified** — the lifecycle is PRD §4.2bis-compliant per this re-verification
(no defect surfaced). The only new artifact is this report.

---

## 1. Method

Each of the 5 item properties + the 3 extras was mapped to **specific `voice_typing/daemon.py`
file:line** via `grep -nE`, then re-verified by reading `__init__` (L648-671), `_load_host`
(L698-795), `_handle_dead_host` (L874-902), the `run()` liveness branch (L840-845), and the
teardown path `_unload_host` (L1204-1244) against the **PRD §4.2bis** wording (the 4 lifecycle
states, the single-flight concurrency rule, the failure-cleanup "no half-built recorder" rule,
the dead-host robustness, and the "teardown under the SAME single-flight lock" rule). The
contract's test target was then re-run live
(`tests/test_daemon.py tests/test_recorder_host.py -k 'load or spawn or dead or unload or boot or unloaded'`,
§3). The non-defect nuances were cross-checked against the module docstrings (daemon.py:688
"`_load_recorder` … back-compat alias"; daemon.py:875 "`_handle_dead_host` … does NOT call
host.stop()"; daemon.py:1205 "`_unload_host` … Acquires _lock (the SAME lock _load_host uses)").

### Commands run (re-verification)

```bash
# locate every lifecycle site: boot state + single-flight + transitions + dead-host + unload
grep -nE 'def _load_host|def _handle_dead_host|def _load_recorder|def _unload_host|self._load_cond|self._loading|self._models_loaded|set_phase\("(loading|idle|unloaded)"\)|set_models_loaded|not self._host.is_alive|self._host = None' voice_typing/daemon.py
# the contract's run target (re-ran live)
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or spawn or dead or unload or boot or unloaded'
# scope guard — no source modified
git status --short
```

---

## 2. The 5 item properties + extras — per-property compliance table

| # | Property (PRD §4.2bis) | Code actual (`voice_typing/daemon.py`) | Verdict |
|---|---|---|---|
| (a) | **Boot state is `unloaded`** — "daemon starts with no recorder, no CUDA context, ~0 VRAM" | `__init__` lazy branch (no `recorder`/`recorder_host` injected → production): `self._host = None` (**L657**), `loaded = False` (**L657**), `self._models_loaded = loaded`→False (**L659**), `self._loading = False` (**L660**), `self._load_error = None` (**L661**), then `set_phase("idle" if loaded else "unloaded")`→**"unloaded"** (**L670**) + `set_models_loaded(loaded)`→**False** (**L671**). The injected branch sets `loaded=True`/`phase="idle"` (correct for tests/pre-built; the PRD boot requirement applies to the no-injection production path). | ✅ **COMPLIANT** (boot = `unloaded`, models_loaded=False, ~0 VRAM — the recorder is never constructed in the daemon process) |
| (b) | **Single-flight under a lock** — "a second arm while `loading` MUST NOT start a second load — it waits on the in-flight one" | `self._load_cond = threading.Condition(self._lock)` (**L665**) — the SAME `_lock` `_load_host` takes. Under `with self._lock` (**L714**): a second caller hitting `if self._loading:` (**L721**) loops `while self._loading: self._load_cond.wait()` (**L722-723**) and returns the in-flight result (`return self._models_loaded and ...`, **L724**) — it **NEVER** starts a 2nd spawn. The heavy `host.spawn()` runs OUTSIDE `_lock` (**L744-759**) so concurrent status/stop stay responsive during the ~1–3 s load. | ✅ **COMPLIANT** (2nd arm waits, returns the in-flight result; load is single-flight under the lock) |
| (c) | **Success transitions** unloaded→loading→loaded/not-listening; "`status` reports `models_loaded: bool`" | Load start (under lock): `set_phase("loading")` + `set_models_loaded(False)` (**L727-728**). On success (under lock): `self._host = host` + `self._models_loaded = True` (**L765**) + `self._mode = mode` (**L766**) + `set_phase("idle")` + `set_models_loaded(True)` (**L772-773**) + `notify_all()` (**L774**). Transition is exactly **unloaded → loading → idle** with `models_loaded` False→True. (`_mode` @766 + device-cache seed @770 are the §4.2ter/status refinements — correct, not defects.) | ✅ **COMPLIANT** |
| (d) | **Failure cleanup** — "returns to `unloaded`, the arm returns `{ok:false,error}`, MUST NOT leave a half-constructed recorder behind"; "`status` reports the error" | On spawn failure (under lock): `host.stop()` best-effort in try/except (**L781-783** → **NO half-built recorder** — §4.2bis), `self._load_error = "recorder host spawn failed"` (**L782**), `self._models_loaded = False` (**L783**), `self._host = None` (**L784**), `set_phase("unloaded")` (**L785**), `set_models_loaded(False)` (**L786**), `notify_all()` (**L787**), `success = False` (**L788**); returns `False` (**L794**). The arm path then returns `{ok:false,error}`; `status_snapshot` surfaces `_load_error`. | ✅ **COMPLIANT** (no half-built recorder; returns to unloaded; error surfaced) |
| (e) | **Dead-host recovery** — (robustness; bugfix Issue 3) child death → `unloaded` → re-spawn on next arm | `run()` top-of-loop liveness check (**L840**): `if self._host is not None and not self._host.is_alive:` → WARNING with pid (**L841-844**) → `_handle_dead_host()` → `continue` (**L845**). `_handle_dead_host` (**L874**): under `self._lock` sets `_host=None` (**L890**), `_models_loaded=False` (**L891**), `_listening.clear()` (**L892**), `set_phase("unloaded")` (**L893**), `set_models_loaded(False)` (**L894**), `set_listening(False)` (**L895**), `_load_error="recorder-host child died unexpectedly"` (**L896**), clears both idle clocks (**L897-898**) + reseeds the device cache (**L902**, VT-002). The `_models_loaded=False` reset defeats `_load_host`'s fast-path short-circuit (**L715**), so the next arm re-spawns. Does NOT call `host.stop()` (child already dead — correct). | ✅ **COMPLIANT** (child crash → unloaded → next arm re-spawns) |
| (+i) | **Boot ~0 VRAM** — "the daemon process is intended to never import RealtimeSTT/torch/ctranslate2 and never create a CUDA context" | The daemon NEVER constructs the `AudioToTextRecorder` — the child owns all CUDA contexts (PRD §4.2bis "Implementation note"). `self._host = None` at boot (**L657**); `run()` idles when `self._host is None` (**L847-848**). (VT-001 caveat: `voicectl status` once probed CUDA in the daemon — a STATUS concern audited in M3, NOT a lifecycle/boot-state defect; the device-cache seed on load @770 + the reseed on dead/unload @902/1243 keep status consistent without daemon-side CUDA.) | ✅ **COMPLIANT** (daemon process boots at ~0 VRAM; the recorder-host child is the only CUDA owner) |
| (+ii) | **Teardown under the SAME single-flight lock** — "an arm that races an in-flight teardown waits for it, then loads fresh — an arm can never see a half-torn-down recorder" | `_unload_host` (**L1204**) acquires `with self._lock` (**L1208** — the SAME lock `_load_host` takes), re-checks the FULL unload condition UNDER the lock incl. `_listening.is_set()` (**L1225-1231** → a racing arm ABORTS the unload), runs the bounded `_bounded_shutdown(timeout=5.0)` (**L1236**) under `_lock`, then resets `_host=None`/`_models_loaded=False`/`phase="unloaded"`/`models_loaded=False` (**L1240-1243**). The mode-switch teardown (@738) likewise runs `with self._lock`. So a concurrent arm's `_load_host()` blocks on this lock, waits for teardown, then spawns fresh. | ✅ **COMPLIANT** (teardown shares the load single-flight lock; bounded-join detail is S3's audit — this confirms the LOCKING) |
| (+iii) | **Mode-switch reload (§4.2ter)** — reuses the same single-flight + lifecycle path | `_load_host` detects a wrong-mode resident under the lock (`switch_mode=True` @**L718**), then AFTER releasing the single-flight block tears it down + respawns in the requested mode (`_bounded_shutdown(timeout=5.0)` @**L738** + `self._host = None` / `self._models_loaded = False` @**L740-741**), then the normal spawn+success path. The reload is bounded (5 s join + killpg, same as idle-unload). | ✅ **COMPLIANT** (mode switch = one bounded reload via the same lifecycle path — detailed lite/mode-switch audit is M2.T3) |

---

## 3. Test result — the contract's run target (the evidence)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'load or spawn or dead or unload or boot or unloaded'
# → 43 passed, 176 deselected in 1.08s
```

**Recorded count: 43 passed, 176 deselected** (matches the verified baseline of 43 passed, 1.13s;
re-ran live during this audit). The slice is CUDA-free — the daemon fakes inject a
`_LegacyRecorderHostAdapter` so `self._host` is a uniform surface and the lifecycle branches are
exercised directly (boot-unloaded, single-flight, dead-host detection + respawn + status,
total-failure-stays-unloaded, idle-unload fire/noop/disable, arm-racing-unload, mode-switch
reload); the recorder-host tests drive the spawn/ready/error dispatch and the dead/eof paths
directly.

### Test → property mapping

| Property | Covering test (`tests/test_daemon.py` unless noted) | What it asserts |
|---|---|---|
| (a) boot unloaded | `test_lazy_daemon_boots_unloaded_with_no_recorder`; `test_lazy_boot_records_unloaded_phase` | no-injection construction → `_host is None`, `_models_loaded=False`, phase="unloaded"; `set_phase("unloaded")` recorded |
| (a) injected = loaded | `test_injected_recorder_is_loaded_at_construction` | the `recorder=`/`recorder_host=` branch sets `loaded=True`/phase="idle" (correct for tests/pre-built) |
| (b) single-flight | `test_load_recorder_single_flight_one_build_under_concurrency`; `test_load_and_unload_serialize_on_the_same_single_flight_lock`; `test_arm_racing_unload_waits_then_loads_fresh` | N concurrent arms → exactly ONE spawn; a racing unload serializes on the same lock; an arm racing an in-flight unload waits then loads fresh |
| (c) success transitions | `test_start_on_lazy_daemon_triggers_load_then_arms`; `test_cold_first_arm_fires_loading_toast`; `test_warm_arm_fires_no_loading_toast`; `test_load_recorder_success_loads_and_marks_loaded`; `test_load_recorder_is_noop_once_loaded` | first arm → loading toast → models_loaded=True → arm; warm arm fires no loading toast (already resident) |
| (d) failure cleanup | `test_load_recorder_total_failure_stays_unloaded`; `test_load_recorder_cpu_fallback_on_cuda_failure`; `test_start_suppressed_when_load_fails` | spawn failure → `_host is None`, `_models_loaded=False`, phase="unloaded", `_load_error` set; arm suppressed (`{ok:false}`); no half-built recorder |
| (e) dead-host recovery | `test_run_loop_detects_dead_host_and_transitions_to_unloaded`; `test_load_host_respawns_after_dead_child`; `test_status_reports_unloaded_after_child_death`; `test_text_returns_promptly_if_child_already_dead` (`tests/test_recorder_host.py`) | run loop detects `is_alive=False` → transitions to unloaded; next arm re-spawns; status reports unloaded; text() on an already-dead host returns promptly |
| (+i) boot ~0 VRAM | `test_lazy_daemon_boots_unloaded_with_no_recorder` (+ the recorder-host dispatch tests assert the daemon never imports the recorder) | the daemon process boots with no host constructed (the child is the only CUDA owner) |
| (+ii) teardown under same lock | `test_load_and_unload_serialize_on_the_same_single_flight_lock`; `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded`; `test_armed_state_aborts_unload_via_listening_recheck`; `test_status_device_reseeded_not_stale_after_idle_unload` | unload acquires the same `_lock` as load; teardown routes through bounded shutdown (a racing arm's wait is bounded); an armed state aborts the unload via the under-lock re-check; the device cache is reseeded after unload |
| (+iii) mode-switch reload | `test_mode_switch_normal_to_lite_reloads`; `test_start_lite_loads_lite_host_and_arms`; `test_start_lite_after_idle_unload_reloads_in_lite`; `test_same_mode_arm_is_instant_no_reload`; `test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening` | wrong-mode resident → teardown + respawn in requested mode (~1–3 s); same-mode arm is instant; a failed reload clears `_listening` (no half-armed state) |
| idle-unload lifecycle | `test_idle_unload_fires_when_disarmed_beyond_threshold`; `test_idle_unload_keeps_resident_within_threshold`; `test_idle_unload_noop_when_listening`; `test_idle_unload_noop_when_not_loaded`; `test_idle_unload_noop_when_never_disarmed`; `test_idle_unload_disabled_when_threshold_zero`; `test_arm_resets_idle_unload_clock`; `test_cold_arm_after_idle_unload_refires_loading_toast` | the 30-min watchdog fires/noops/disables correctly; the clock resets on arm; a post-unload arm is cold (reloads) |
| recorder-host spawn | `test_spawn_ready_seeds_device_via_dispatch`; `test_spawn_error_sets_error_via_dispatch`; `test_read_loop_eof_marks_dead_and_unblocks_waiters`; `test_stop_with_dead_process_is_noop` (`tests/test_recorder_host.py`) | the child's ready/error/dead/eof dispatch feeds the lifecycle transitions correctly |

---

## 4. Non-defect nuances (NON-blocking — recorded so they are not mistaken for gaps)

### (i) `recorder` → `self._host`: the lifecycle proxies to a `RecorderHost` subprocess

PRD §4.2/§4.2bis describes the lifecycle in terms of `recorder` / "the recorder". The **actual
code** uses **`self._host`** — a `RecorderHost` subprocess (the lazy-load / crash-recovery
architecture moved the `AudioToTextRecorder` into a managed CHILD process; daemon.py:575 notes
"`self._host` replaces `self._recorder`"). `_load_host` spawns the child (`host.spawn()`,
L759) rather than constructing a recorder in-process; `is_alive` (L840) is the child's
`proc.is_alive()` + dead flag. A `_LegacyRecorderHostAdapter` (daemon.py:654) wraps any `recorder=`
injected in tests so `self._host` is a **uniform** surface. **The lifecycle semantics are identical
to PRD §4.2bis** (boot unloaded → loading → loaded/not-listening → loaded/listening; single-flight;
failure → unloaded; dead → unloaded → respawn); only the attribute name + the process boundary
changed. This audit maps the contract's "`recorder`" wording to `self._host` at every site — this is
the deliberate design it is, **not** a defect.

### (ii) `_load_recorder` is a back-compat alias for `_load_host("normal")`

`_load_recorder` (daemon.py:688) is a one-line back-compat alias: `return self._load_host("normal")`
(L697). It is kept so `start()`/`toggle()`'s call sites and the existing tests' `recorder=` injection
seam are unchanged (daemon.py:692 docstring). `start_lite`/`toggle_lite` call `_load_host("lite")`
directly. **Not a defect** — the real implementation is `_load_host`; the alias is a stable shim.

### (iii) Mode-switch reload & lite mode are §4.2ter — audited in M2.T3

Property (+iii) confirms the mode-switch reload (`_load_host`'s `switch_mode` branch, L718/736-741)
**reuses the §4.2bis single-flight + transitions** (it sets `switch_mode` under the single-flight
lock, tears the wrong-mode child down + respawns, then the normal success path). The **detailed**
lite/mode-switch audit (which model loads, the `post_speech_silence_duration` override, the
`mode` field) is **P1.M2.T3** (§4.2ter). This audit confirms only that the reload sits correctly
relative to the §4.2bis lifecycle — it does not audit lite's model set.

### (iv) Bounded teardown detail (5 s join + killpg) is S3's audit

Property (+ii) confirms teardown (`_unload_host` L1236, the mode-switch teardown L738) runs under
the **SAME single-flight lock** as load — the §4.2bis concurrency rule ("an arm can never see a
half-torn-down recorder"). The **bounded-ness** of that teardown (`_bounded_shutdown` → `host.stop`
→ `proc.join(5s)` then `os.killpg` the group) is **P1.M2.T2.S3**'s audit. This audit confirms the
LOCKING is shared (so a racing arm waits), not the join/kill bound.

### (v) VT-001 / VT-002 (status CUDA probe / device-cache reseed) are STATUS concerns — M3

PRD §4.2bis's "Implementation note" flags that `voicectl status` once probed CUDA in the daemon
(VT-001, BUGS.md) — violating the "daemon never creates a CUDA context" intent. The lifecycle
itself never probes CUDA: the device cache is seeded from the **child's** `'ready'` dict on load
(L770) and **reseeded** to the un-probed config on dead-host (L902) and unload (L1243) so status
never needs to probe (VT-002). VT-001/VT-002 are STATUS concerns audited in **P1.M3** — they are
**not** lifecycle/boot-state defects. This audit confirms the lifecycle path keeps status
consistent without daemon-side CUDA.

---

## 5. Conclusion

The lazy-load lifecycle faithfully implements **PRD §4.2bis** on all 5 item properties (a)–(e):
the daemon **boots `unloaded`** with no recorder and ~0 VRAM (a); the first arm is **single-flight
under a lock** so a racing second arm waits and reuses the in-flight result — never starting a
second spawn (b); the success transition is exactly **unloaded → loading → idle** with
`models_loaded` False→True (c); a failed load **returns to `unloaded` with `{ok:false,error}` and
NO half-built recorder** (d); and a crashed child is **detected on the idle loop, reset to
`unloaded`, and re-spawned on the next arm** (e). The three §4.2bis extras also pass: the daemon
process boots at **~0 VRAM** (the child is the only CUDA owner) (+i); teardown **shares the load
single-flight lock** so a racing arm never sees a half-torn-down recorder (+ii); and the
mode-switch reload **reuses the same single-flight + lifecycle path** (+iii). All with
`voice_typing/daemon.py` file:line evidence; the `-k` slice is **43 passed, 176 deselected**.

This certifies the project's acceptance criteria:
- **#6 (starts un-loaded, ~0 VRAM until first arm)** — `__init__`'s no-injection branch sets
  `_host=None` / `models_loaded=False` / `phase="unloaded"` (L657-671), and `run()` idles when
  `_host is None` (L847-848). The daemon process never constructs the recorder — the child owns all
  CUDA contexts. Certified by (a) + (+i).
- **#9 (idle-unload → reload)** — `_unload_host` (L1204) tears the resident child down under the
  single-flight lock after `auto_unload_idle_seconds` disarmed, transitions to `unloaded`, and the
  next arm reloads via `_load_host` (~1–3 s, same as a session's first arm). Certified by (+ii) +
  the idle-unload lifecycle tests in §3.

**Verdict: ✅ COMPLIANT on all 5 properties + the 3 extras — no fix needed.** **No source files
were modified** (this is a read-only audit — the lifecycle is PRD §4.2bis-compliant per this
re-verification). The only artifact produced by this subtask is this report. Adjacent concerns are
correctly deferred: the **graceful drain** is P1.M2.T1.S2 (§2 of `gap_daemon_loop.md`); the
**recorder-host IPC** is S2; the **bounded teardown** detail is S3; **lite/mode-switch** is M2.T3;
**status/feedback** (incl. VT-001/VT-002) is M3.