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

---

# §2 — Recorder-Host IPC (P1.M2.T2.S2) vs PRD §4.2bis

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/recorder_host.py`'s **IPC mechanism** against **PRD §4.2bis** (the
recorder-host subprocess model) on the **6 item properties (a)-(f)**. The mechanism comprises:
`RecorderHost.spawn` / `set_microphone` / `abort` / `text` / `stop` (L181-329) + the two
multiprocessing queues + the abort `mp.Event` (L135-160) + the child `_worker_main` (L421-575,
incl. `os.setsid` @446 + the command loop @533-571 + `_run_text_and_emit_final` @630-677) + the
daemon reader thread `_read_loop` (L331-353) + `_dispatch` (L354-392) + `_terminate_group`
(L394-413, `os.killpg` @407) + the child-local `_RelayFeedback` (L718-750) / `_RelayLatency`
(L760-774) relay stand-ins. Subtask **P1.M2.T2.S2** of verification round `006_862ee9d6ef41` —
**appended** to this report (§1 above is P1.M2.T2.S1's lazy-load state-machine audit; this §2 owns
the IPC 6 properties, a different contract — queues/commands/events/relay/abort, not load states).
**Audited artifacts (all read-only):**
- `voice_typing/recorder_host.py` — `__init__` queues+Event (L139/140/146); `spawn()` (L181-228,
  `ctx.Process(target=_worker_main,…)` @193-200); `set_microphone()` (L230-235, `cmd_q.put` @233);
  `abort()` (L237-248, `_abort_event.set()` @246); `text()` (L250-271, `cmd_q.put` @261,
  `_final_evt.wait` loop @264-268); `stop()` (L272-329, shutdown best-effort @309, `join` @315,
  `_terminate_group` @321); `_read_loop()` (L331-353); `_dispatch()` (L354-392); `_terminate_group()`
  (L394-413, `os.killpg` @407); `_worker_main()` (L421-575, `os.setsid` @446, relay stand-ins
  @464-465, `_abort_handler` @517-531, command loop @533-571, belt+suspenders `("abort",{})` @564);
  `_run_text_and_emit_final()` (L630-677, VT-007 sentinel `("final",{text:""})` @677);
  `_RelayFeedback` (L718-750, partial relay @733, vad relay @737, no-ops @735/738/741);
  `_RelayLatency` (L760-774, `speech_end` relay @768, no-ops @759/772/774). Also the module docstring's
  IPC PROTOCOL block (L18-31) + CALLBACK RELAY block (L33-43).
- `tests/test_recorder_host.py` + `tests/test_daemon.py` — the
  `-k 'host or relay or queue or ipc or worker'` slice (the contract's run target; 30 tests; the
  fakes mock CUDA so the slice is fast and exercises the IPC directly without a model load).

**Bottom line:** ✅ All 6 PRD §4.2bis IPC properties are **compliant** (each with file:line evidence
below). The `-k 'host or relay or queue or ipc or worker'` slice is **30 passed, 189 deselected in
1.66s** (re-ran live; matches the verified baseline of 30 passed, 1.65s). Five **non-blocking**
nuances are recorded so they are not mistaken for defects (§4): the IPC vocabulary is
richer/safer than the item's shorthand but fully satisfies PRD §4.2bis's intent
("arm/disarm/text/abort/shutdown proxied; partials/finals/VAD streamed back; setsid+killpg for
VRAM release"). **No source files were modified** (this is a read-only audit — the IPC is
PRD §4.2bis-compliant per the re-verification; no defect was found).

---

## §2.1 Method

Each of the 6 IPC properties was mapped to **specific `voice_typing/recorder_host.py` file:line**
via `grep -nE`, then re-verified by reading `__init__` (L135-160), `spawn` (L181-228),
`set_microphone`/`abort`/`text`/`stop` (L230-329), `_read_loop` (L331-353), `_dispatch` (L354-392),
`_terminate_group` (L394-413), `_worker_main` (L421-575, incl. `os.setsid` @446 + the command loop
@533-571 + the relay stand-ins @464-465 + `_abort_handler` @517-531), `_run_text_and_emit_final`
(L630-677), `_RelayFeedback` (L718-750), and `_RelayLatency` (L760-774). The contract's test target
was then re-run live (`tests/test_recorder_host.py tests/test_daemon.py -k 'host or relay or queue
or ipc or worker'`, §2.3). The module docstring's IPC PROTOCOL (L18-31) + CALLBACK RELAY (L33-43)
blocks were cross-checked against the code's actual vocabulary. The 5 non-defect nuances
(abort-via-Event; richer vocabulary; intentional no-op relays; VT-007 sentinel; vad is_listening
gate) were confirmed against the code comments (recorder_host.py:141-145 abort-Event rationale;
L96-100 killpg rationale; L735/738/741 daemon-owned no-ops; L630-676 VT-007 sentinel; L380-388
Issue-2 residual gate).

### Commands run (re-verification)

```bash
# locate every IPC site (queues, commands, events, relay, abort, setsid/killpg, the VT-007 sentinel)
grep -nE 'def spawn|def set_microphone|def abort|def text|def stop|def _read_loop|def _dispatch|\
def _terminate_group|def _worker_main|def _run_text_and_emit_final|os\.setsid|os\.killpg|_cmd_q\.put|\
_abort_event|class _RelayFeedback|class _RelayLatency|_safe_put' voice_typing/recorder_host.py
# the contract's run target (re-ran live)
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py \
    -q -k 'host or relay or queue or ipc or worker'
# scope guard — no source modified
git status --short
```

---

## §2.2 The 6 IPC properties — per-property compliance table

| # | Property (PRD §4.2bis) | Code actual (`voice_typing/recorder_host.py`) | Verdict |
|---|---|---|---|
| (a) | daemon **spawns a managed child** (`Process(target=_worker_main)`) that owns the recorder; model load happens IN THE CHILD (daemon stays CUDA-free) | `spawn()` **L193-200**: `self._proc = ctx.Process(target=_worker_main, args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event, self._force_cpu, self._mode), name=…, daemon=True)` then `self._proc.start()` (**L201**). Reader thread started @203-205 BEFORE the `_ready_evt` wait @207-213 so load-time events drain. The heavy load is in `_worker_main` (build_recorder @473/483) | ✅ **COMPLIANT** |
| (b) | child calls `os.setsid()` (own process group) + daemon `os.killpg` releases ALL VRAM incl. grandchildren | `_worker_main` **L446**: `os.setsid()` (first syscall; comment L443-445). Daemon `_terminate_group()` **L394-413**: `os.killpg(os.getpgid(pid), signal.SIGKILL)` (**L407**) — the child is its own group leader → killpg reaches its RealtimeSTT-spawned grandchildren (transcript_process/reader_process). `stop()` calls it @321 after a bounded `join(timeout)` @315 | ✅ **COMPLIANT** (the VRAM-release mechanism PRD §4.2bis mandates) |
| (c) | arm/disarm/text/shutdown **proxied over a command queue**; abort interrupts a blocked text() | `cmd_q` = `ctx.Queue()` (**L139**). `set_microphone(on)` **L233** puts `("arm"/"disarm", {})`; `text()` **L261** puts `("text", {})`; `stop()` **L309** best-effort puts `("shutdown", {})`. **abort is primarily a dedicated `mp.Event`** (`_abort_event` @142/146; `abort()` sets it @246), polled by a SEPARATE child thread `_abort_handler` @517-531 that calls `recorder.abort()`. `("abort",{})` IS still handled on cmd_q (**L564**) as belt-and-suspenders (see nuance §4.1) | ✅ **COMPLIANT** (abort-via-Event nuance — STRONGER than a plain cmd_q abort) |
| (d) | partials/finals/VAD (and load/error) **events stream back to a daemon reader thread** | `evt_q` = `ctx.Queue()` (**L140**). Child emits via `_safe_put`: `("ready",{device,…})` @499, `("error",{msg})` @479/501, `("final",{text})` @508 + VT-007 sentinel @677, `("partial",{text})` @733, `("speech",{})` @468, `("vad",{phase})` @737, `("speech_end",{})` @768, `("gone",{})` @575. Daemon `_read_loop` (L331-353) drains → `_dispatch` (L354-392) handles every kind; unknown WARN-logged @391 | ✅ **COMPLIANT** (vocabulary richer than shorthand — see nuance §4.2) |
| (e) | `text(on_final)` puts the text command + **blocks until a final event** arrives (unblocked by the reader thread) | `text()` **L250-271**: sets `_on_final` @255, clears `_final_evt` @256, puts `("text",{})` @261, then BLOCKS in `while not self._final_evt.wait(timeout=0.5):` (**L264-268**) — the loop also detects child death (`_dead or not _proc.is_alive()` → return @267-268). Reader `_dispatch` on `"final"` (L369-377) invokes `self._on_final(text)` @374 + sets `_final_evt` @377 → unblocks `text()`. Dead-child: `_read_loop` finally (L351-353) sets `_dead=True` + `_final_evt.set()` | ✅ **COMPLIANT** (the VT-007 sentinel @677 GUARANTEES a final even on the abort path — nuance §4.4) |
| (f) | child callbacks **relay** partials/VAD/speech_end to the daemon (daemon drives Feedback/LatencyLog/on_final) | `_RelayFeedback` (L718-750): `update_partial` @725-728 → `("partial",{text})`; `set_phase` @730-733 → `("vad",{phase})` (listening/speaking only); `set_models_loaded` @735 / `record_final` @738 / `set_listening` @741 are INTENTIONAL no-ops. `_RelayLatency` (L760-774): `note_speech_end` @755/768 → `("speech_end",{})`; `note_partial` @749 / `finalize_utterance` @772 / `snapshot` @774 are no-ops | ✅ **COMPLIANT** (relay covers only child-unique observations; daemon-owned transitions are correctly no-ops — nuance §4.3) |

---

## §2.3 Test result — the contract's run target (the evidence)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py \
    -q -k 'host or relay or queue or ipc or worker'
# → 30 passed, 189 deselected in 1.66s
```

**Recorded count: 30 passed, 189 deselected** (matches the verified baseline of 30 passed, 1.65s;
re-ran live during this audit). The slice is CUDA-free (the fakes mock the recorder) → fast (~1.7s),
but the `timeout 300` inner + bash-tool outer wrap are mandatory (AGENTS.md Rule 1).

### Test → property mapping

| Property | Covering test(s) | What it asserts |
|---|---|---|
| (a) spawn → Process + ready/error | `test_spawn_ready_seeds_device_via_dispatch`; `test_spawn_error_sets_error_via_dispatch` | `ctx.Process(target=_worker_main)` built + started; the 'ready'/'error' event seeds `_device`/`_error` via `_dispatch` |
| (b) setsid + killpg teardown | `test_concurrent_stop_calls_share_one_teardown`; `test_stop_is_noop_when_no_process`; `test_stop_with_dead_process_is_noop` | `stop()` SIGKILLs the process group under single-flight; idempotent; no-op when no/dead process |
| (c) cmd_q commands + abort-Event | `test_set_microphone_puts_arm_or_disarm_command`; `test_abort_sets_abort_event`; `test_text_blocks_until_final_event_then_returns` | arm/disarm/text put commands; abort sets the dedicated `_abort_event` (not a cmd_q put) |
| (d) evt_q events dispatched | `test_dispatch_partial_calls_on_partial`; `test_dispatch_speech_calls_on_speech`; `test_dispatch_speech_end_stamps_latency`; `test_dispatch_vad_drives_feedback_phase`; `test_dispatch_final_calls_on_final_and_sets_final_event`; `test_dispatch_ready_seeds_device_and_sets_ready_event`; `test_dispatch_error_sets_error_and_ready_event`; `test_dispatch_unknown_event_is_ignored`; `test_read_loop_drains_events_until_gone`; `test_read_loop_eof_marks_dead_and_unblocks_waiters` | every event kind (ready/error/final/partial/vad/speech/speech_end/gone) is handled by `_dispatch`; unknown is ignored; `_read_loop` drains until 'gone'/EOF |
| (e) text blocks on final + dead-child + abort-sentinel | `test_text_blocks_until_final_event_then_returns`; `test_text_returns_promptly_if_child_already_dead`; `test_abort_sentinel_unblocks_blocked_host_text` | `text()` blocks until the reader sets `_final_evt`; returns promptly on child death; the VT-007 sentinel unblocks it on abort |
| (f) relay + VT-007 sentinel | `test_run_text_emits_sentinel_final_on_abort_path`; `test_run_text_does_not_double_emit_on_normal_path`; `test_run_text_emits_sentinel_when_abort_flag_set_even_if_return_is_none`; `test_run_text_no_sentinel_on_normal_path_when_abort_flag_unset` | `_run_text_and_emit_final` emits exactly one `("final",…)` (sentinel on abort, real on normal) — never double, never missing, robust to `text()` returning None |

---

## §2.4 Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for gaps)

### (i) abort is a dedicated `mp.Event`, not (primarily) a cmd_q command

The child's command loop BLOCKS in `recorder.text()` while listening, so a `("abort", {})`
command queued on `cmd_q` would NOT be read until `text()` returns (too late). The dedicated
`_abort_event` (`mp.Event`, L142/146) is polled by a SEPARATE child thread (`_abort_handler`
L517-531) that calls `recorder.abort()` the instant it is set — this is how `stop()` /
`toggle(off)` / idle-auto-stop interrupt a blocked `text()`. `("abort", {})` IS still handled on
cmd_q (L564-565) as belt-and-suspenders. The item listing "abort" among the cmd_q commands is
TECHNICALLY satisfied (belt-and-suspenders) but the PRIMARY path is the Event — a STRONGER design,
**not** a defect. (recorder_host.py:141-145 documents this rationale.)

### (ii) the evt_q vocabulary is richer than the item's shorthand

The item lists "partial, final, vad_start, vad_stop, device, loaded, error". The actual vocabulary
(module docstring L23-31; `_dispatch` L354-392):
- `"ready"` (combines device + loaded into one event carrying `{device,compute_type,final_model,
  realtime_model}` — L499) sets `_ready_evt` (the `spawn()` load-completion gate).
- `"vad"{phase}` (a SINGLE event keyed on a `phase` field ∈ {"listening","speaking"} — L737)
collapses vad_start + vad_stop.
- EXTRA events beyond the item's list: `"speech"` (on_speech → idle-auto-stop reset, L468),
  `"speech_end"` (on_vad_stop latency stamp, L768), `"gone"` (clean shutdown ack, L575).

PRD §4.2bis only requires "partials/finals/VAD events stream back to a daemon reader thread" — the
actual vocabulary fully satisfies this (and adds latency/speech/shutdown-ack signals the PRD's
lifecycle + latency logging needs). Naming drift, **not** a defect.

### (iii) `_RelayFeedback.set_models_loaded`/`record_final`/`set_listening` are INTENTIONAL no-ops

The child does NOT own the `models_loaded` / `listening` / lifecycle-phase / `record_final` /
`finalize` transitions — those live in the DAEMON (which has the real Feedback/LatencyLog objects).
The relay stand-ins only relay what the CHILD uniquely observes: partials (realtime transcription)
+ VAD phase + speech_end. Everything else is correctly a no-op (L735/738/741; L749/772/774) so the
daemon remains the single source of truth for lifecycle state. This is the RIGHT design (the child
can't drive daemon-owned transitions), **not** a missing relay. (recorder_host.py:721-724 + 751-754
document this.)

### (iv) VT-007 abort-sentinel — the unblock guarantee (do NOT "simplify" it away)

`_run_text_and_emit_final` (L630-677) GUARANTEES a `("final", {text:""})` event on the abort path
(L677). Without it, an abort (stop / toggle-off / auto-stop) leaves `host.text()` blocked forever
(the child is still alive), wedging the run() loop so no further utterance transcribes. The empty
text is handled safely by the daemon (a disarm already cleared `_listening` → the `on_final` gate
returns early; textproc.clean('') rejects it regardless → nothing is typed). Detected via TWO
independent signals (the `aborted` Event WE control @L509/676 + the legacy non-None return marker
@L676) so it survives RealtimeSTT API drift (a future `text()` returning None on abort still trips
it). Guarded by 4 unit tests. This is a critical IPC robustness detail that EXCEEDS the item's
shorthand — record it so a maintainer doesn't "simplify" it away.

### (v) the "vad" event is gated by an `is_listening` predicate (Issue 2 residual)

`_dispatch`'s `"vad"` branch (L380-388): if the daemon provided an `is_listening` predicate and the
daemon is NOT listening, the stray VAD event (a late `on_vad_stop`/`on_vad_start` racing a disarm)
is DROPPED so phase doesn't flip to listening/speaking while `listening: off`. This is P1.M2.T1's
phase-lifecycle concern; recorded here only because it lives on the IPC dispatch path. **Not** a
gap in the IPC mechanism.

---

## §2.5 Conclusion

The recorder-host IPC faithfully implements **PRD §4.2bis's recorder-host subprocess model** on all
6 properties (a)-(f): the daemon spawns a managed child (`Process(target=_worker_main)`, property
(a)); the child calls `os.setsid()` and the daemon `os.killpg`s the child's process group — the
**VRAM-release mechanism** that lets the idle-unload teardown reach ~0 VRAM incl. the realtime-model
context (property (b)); arm/disarm/text/shutdown are proxied over `cmd_q` and abort is a dedicated
`mp.Event` polled by a separate child thread — STRONGER than a plain cmd_q abort (property (c));
partials/finals/VAD/load/error events stream back over `evt_q` to a daemon reader thread that
dispatches them to the real Feedback/LatencyLog/on_final (property (d)); `text()` puts the command
and blocks on a `threading.Event` set by the reader on the "final" event, with the VT-007 sentinel
guaranteeing an unblock even on the abort path (property (e)); and the child callbacks relay only
the child-unique observations while leaving daemon-owned transitions as no-ops (property (f)).

This is the spine the entire GPU-VRAM-reclamation model (PRD §4.2bis) depends on: lazy load
(§1) arms the child; idle-unload / quit (S3) SIGKILLs its process group; the bounded teardown + the
abort path + the VT-007 sentinel together guarantee the run() loop never wedges on a blocked
`text()`. The IPC is richer/safer than the item's shorthand (nuances §4.1-4.4) but fully satisfies
PRD §4.2bis's intent.

This certifies the project's acceptance criteria:
- **#6 (starts un-loaded, ~0 VRAM until first arm)** — depends on the daemon NEVER touching CUDA;
  property (a) confirms the recorder loads in the CHILD, and property (b) confirms `setsid`+
  `killpg` is wired so the child's CUDA context is releasable on teardown.
- **#9 (idle-unload → reload)** — depends on a clean teardown + a re-armable child; property (b)'s
  `killpg` + property (a)'s `spawn` are the mechanism, and property (e)'s VT-007 sentinel ensures
  the run() loop isn't wedged across the unload/reload cycle.

**Verdict: ✅ COMPLIANT on all 6 properties — no fix needed.** **No source files were modified**
(this is a read-only audit — the IPC is PRD §4.2bis-compliant per the re-verification; no defect
was found). The only artifact produced by this subtask is this appended §2 section. Adjacent
concerns are correctly deferred: the **lazy-load state machine** is §1 above (P1.M2.T2.S1); the
**bounded teardown TIMING** (join(5s)+killpg budget, idle-unload watchdog) is S3; the **phase
lifecycle** (the vad `is_listening` gate's home) is P1.M2.T1; **lite/mode-switch** is M2.T3;
**status** (VT-001/VT-002) is M3.

---

# §3 — Bounded Teardown (P1.M2.T2.S3) vs PRD §4.2bis Idle-unload (resolved) + §8 risk row

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit the teardown **TIMING/orchestration** against **PRD §4.2bis's "Hard requirement —
bounded teardown"** (resolved paragraph: *the daemon `killpg`s the child group after a 5 s join, so
VRAM is force-released regardless of `recorder.shutdown()`'s behavior*) + the **§8 risk row**
("`recorder.shutdown()` hangs ~90 s" → mitigate with a hard timeout + force-cleanup). §3 owns: the
**daemon-side single-flight lock** around teardown, the **bounded join(5 s)+killpg budget** that
SUPERSEDES the ~90 s RealtimeSTT wedge, the **idle-unload watchdog** that triggers it, and the
**`request_shutdown` BUG-1 fix** that unblocks a wedged `host.text()` on the SIGTERM path. §1 above
is P1.M2.T2.S1's lazy-load **state machine**; §2 is P1.M2.T2.S2's recorder-host **IPC MECHANISM**
(stop@272-329 + `_terminate_group`@394-413 + `killpg`@407 — the primitive this §3 certifies the
TIMING of). **§3 references §2's stop/killpg; it does NOT re-audit the IPC vocabulary** (S2) or the
lazy-load states (S1). Subtask **P1.M2.T2.S3** of verification round `006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/recorder_host.py` — `_STOP_JOIN_TIMEOUT_S: float = 5.0` (**L87**); `stop(timeout=…)`
  (**L272**, the bounded teardown primitive): abort_event.set @300-302, detached `"shutdown"` cmd
  thread @311-316 (never waited on), `self._proc.join(timeout=timeout)` **@318**, `_terminate_group()`
  @323 + `join(timeout=2.0)` @325 on still-alive, `_dead=True`@327 + `_proc=None`@328; SINGLE-FLIGHT
  under `self._stop_lock` @297; `_terminate_group` (**L394**): `os.getpgid(pid)` **@406** +
  `os.killpg(pgid, SIGKILL)` **@407** (best-effort catch @409); child `os.setsid()` (**L446**, makes
  the child its own group leader so `getpgid(pid)==pid` and killpg reaches the RealtimeSTT
  grandchildren).
- `voice_typing/daemon.py` — `_idle_unload_watchdog` (**L1160**, ticks `self._shutdown.wait(1.0)`
  @1168 → `_maybe_idle_unload` @1170); `_maybe_idle_unload` (**L1172**, **lock-free** pre-check @1181-
  1187, short-circuits `threshold<=0` @1182, returns if `not _models_loaded` / `_listening.is_set()` /
  `_disarmed_monotonic is None` / `elapsed < threshold` @1183-1187 → `_unload_recorder` @1188);
  `_unload_recorder` (**L1197**, back-compat alias → `_unload_host` @1201); `_unload_host` (**L1204**,
  the idle-unload teardown): `with self._lock` **@1222** (the SAME lock `_load_host` takes @714 —
  single-flight), full-condition re-check UNDER the lock @1224-1231 (a racing arm ABORTS the unload),
  `_bounded_shutdown(timeout=5.0)` **@1240**, reset `_host=None`/`_models_loaded=False`/
  `set_phase("unloaded")`/`set_models_loaded(False)` + device-cache reseed @1243-1247; `_bounded_shutdown`
  (**L1620**, → `self._host.stop(timeout=timeout)` **@1643**, None-host no-op @1632, best-effort try/
  except @1644-1645); `shutdown` (**L1647**, idempotent + single-flight via `_shutdown_done` under
  `_lock` @1684-1686 + `_teardown_done` Event coordination on the SIGTERM path @1689/1709);
  `request_shutdown` (**L1454**, the BUG-1 fix): `_shutdown.set()` @1486, drain-timer cancel @1489-1492,
  None-host early-return @1494-1495, CLAIMs `_shutdown_done` under `_lock` @1498-1503,
  `_safe_abort()` @1505 (OUTSIDE `_lock`), `_bounded_shutdown()` @1510 (kills the child group →
  `host.text()`'s wait-loop detects child death → unblocks `run()`), `_teardown_done.set()` @1514 in
  try/finally.
- `tests/test_daemon.py` + `tests/test_recorder_host.py` — the
  `-k 'unload or teardown or shutdown or killpg or terminate or bounded'` slice (the contract's run
  target; the daemon fakes inject a `_LegacyRecorderHostAdapter` so the teardown branches are
  exercised directly without a model load).

**Bottom line:** ✅ All 5 properties (a)-(e) are **COMPLIANT** (each with file:line evidence below).
The `-k` slice is **42 passed, 177 deselected in 2.12s** (re-ran live; matches the verified
baseline of 42 passed, 2.12s). The teardown is **bounded**: `host.stop(timeout=5)` → `join(5)` +
`_terminate_group()` (killpg) + `join(2)` = ~7 s max per call, plus `ControlServer.stop()` join(2)
≈ ~2 s, and with daemon single-flight exactly ONE `_bounded_shutdown()` runs on the SIGTERM path
→ ≤ ~9 s total — comfortable headroom under systemd `TimeoutStopSec=15`. It therefore **CANNOT
reproduce** RealtimeSTT's ~90 s `recorder.shutdown()` wedge. **No source/test files were modified**
(the teardown is PRD §4.2bis + §8-compliant per this re-verification; no defect surfaced). The only
new artifact is this appended §3 report.

---

## §3.1 Method

Each of the 5 item properties was mapped to **specific `voice_typing/recorder_host.py` /
`voice_typing/daemon.py` file:line** via `grep -nE`, then re-verified by reading `stop` (L272-329),
`_terminate_group` (L394-413), `_STOP_JOIN_TIMEOUT_S` (L87), the child `os.setsid` (L446); and
`_idle_unload_watchdog` (L1160), `_maybe_idle_unload` (L1172), `_unload_recorder` (L1197),
`_unload_host` (L1204-1247), `_bounded_shutdown` (L1620-1646), `shutdown` (L1647-1711), and
`request_shutdown` (L1454-1514) against the **PRD §4.2bis resolved-paragraph wording** (killpg
after a 5 s join) + the **§8 risk-row** mitigation (hard timeout + force-cleanup of the recorder's
worker threads / `transcript_process` so VRAM is released). The contract's test target was then
re-run live (`tests/test_daemon.py tests/test_recorder_host.py -k 'unload or teardown or shutdown
or killpg or terminate or bounded'`, §3.3). The 7 non-defect nuances (§3.4) were cross-checked
against the code/docstring evidence (recorder_host.py:282-289 "cannot reproduce the ~90 s wedge";
L311-316 detached-cmd rationale; daemon.py:1210-1213 `_unload_host` under-`_lock` rationale;
daemon.py:1628-1635 budget math; daemon.py:1463-1476 BUG-1 + single-flight rationale).

### Commands run (re-verification)

```bash
# locate every teardown site (join budget, stop, killpg, setsid, the daemon orchestration)
grep -nE '_STOP_JOIN_TIMEOUT_S|def stop\b|def _terminate_group|os\.killpg|os\.getpgid|os\.setsid|\
def _idle_unload_watchdog|def _maybe_idle_unload|def _unload_recorder|def _unload_host|\
def _bounded_shutdown|def shutdown\b|def request_shutdown|host\.stop\(|_teardown_done|_shutdown_done' \
voice_typing/recorder_host.py voice_typing/daemon.py
# the contract's run target (re-ran live)
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py \
    -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'
# scope guard — no source modified
git status --short
```

---

## §3.2 The 5 teardown properties — per-property compliance table

| # | item property | PRD §4.2bis / §8 expected | code actual (`voice_typing/*.py`) | verdict |
|---|---|---|---|---|
| (a) | **`stop()` joins child w/ timeout, then `_terminate_group()` (killpg)** | "killpg's the child group after a 5 s join" (§4.2bis resolved ¶); "hard timeout + force-cleanup" (§8) | recorder_host.py: `_STOP_JOIN_TIMEOUT_S = 5.0` **@87**; `stop(timeout=…)` **@272**; `self._proc.join(timeout=timeout)` **@318**; `if self._proc.is_alive(): logger.warning(…); self._terminate_group(); self._proc.join(timeout=2.0)` **@319-325**; `_terminate_group` (L394): `pgid = os.getpgid(pid)` **@406** + `os.killpg(pgid, signal.SIGKILL)` **@407** (best-effort catch @409); child `os.setsid()` **@446** (own group leader → killpg reaches grandchildren) | ✅ **COMPLIANT** |
| (b) | **`_unload_host` acquires the SAME single-flight lock as load** | "Teardown runs under the SAME single-flight lock as load" (§4.2bis) | daemon.py: `_unload_host` `with self._lock:` **@1222** == `_load_host` `with self._lock:` **@714** (same `threading.Lock` instantiated **@591**; `_load_cond = threading.Condition(self._lock)` **@665** uses the same lock); full-condition re-check UNDER the lock @1224-1231 incl. `self._listening.is_set()` (a racing arm ABORTS the unload) | ✅ **COMPLIANT** |
| (c) | **idle-unload watchdog tears down after `auto_unload_idle_seconds` of loaded+not-listening** | "after `auto_unload_idle_seconds` (default 1800) of loaded/not-listening" (§4.2bis Idle unload) | daemon.py: `_idle_unload_watchdog` ticks `self._shutdown.wait(1.0)` **@1168** → `_maybe_idle_unload` @1170; pre-check `threshold = self._cfg.asr.auto_unload_idle_seconds` **@1181**, short-circuit `threshold <= 0` @1182, return if `not self._models_loaded` / `self._listening.is_set()` / `self._disarmed_monotonic is None` / `elapsed < threshold` @1183-1187 → `_unload_recorder()` @1188 → `_unload_host()` @1201 | ✅ **COMPLIANT** |
| (d) | **teardown is bounded (seconds), NEVER 90 s** | "MUST NOT reproduce the ~90 s teardown hang" (§8 risk row; §4.2bis hard req) | recorder_host.py: `stop()` join(5)+killpg+join(2)=~7 s max @318-325 (killpg is UNCONDITIONAL after the join budget — cannot wedge); daemon.py: `_bounded_shutdown(timeout=5.0)`@1620 → `self._host.stop(timeout=timeout)` **@1643**; `stop()` docstring @282-289 "cannot reproduce RealtimeSTT's ~90 s shutdown wedge; we do NOT wait on its unbounded thread joins"; `shutdown()` docstring @1657-1666 confirms the wedge is superseded; budget math @1628-1635 (~7 s/call + ~2 s ControlServer, single-flight → ≤~9 s < `TimeoutStopSec=15`) | ✅ **COMPLIANT** |
| (e) | **`request_shutdown` kills the child group so a blocked `text()` unblocks (BUG-1 fix)** | "Killing the child guarantees `host.text()` returns" (BUG-1; §4.2) | daemon.py: `request_shutdown` **@1454**: `_shutdown.set()` @1486 → drain-timer cancel @1489-1492 → CLAIMs `_shutdown_done` under `_lock` @1498-1503 → `_safe_abort()` @1505 (outside `_lock`) → `_bounded_shutdown()` **@1510** (kills the group) → `_teardown_done.set()` @1514 (try/finally); docstring @1463-1472 "Killing the child (`host.stop()`) guarantees `host.text()`'s loop sees a dead child and returns within ~0.5 s"; git: `84f03e8 P1.M4.BUG1: tear down child on shutdown to fix SIGTERM hang` + `4526870 P1.M1.T2.S3: end-to-end SIGTERM race regression test` | ✅ **COMPLIANT** |

---

## §3.3 Test result — the contract's run target (the evidence)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py \
    -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'
# → 42 passed, 177 deselected in 2.12s
```

**Recorded count: 42 passed, 177 deselected** (matches the verified baseline of 42 passed, 2.12s;
re-ran live during this audit). The slice is CUDA-free (the daemon fakes inject a
`_LegacyRecorderHostAdapter`; the recorder-host tests drive `stop`/`_terminate_group` directly) →
fast (~2 s), but the `timeout 300` inner + bash-tool outer wrap are mandatory (AGENTS.md Rule 1).

### Test → property mapping

| Property | Covering test(s) (`tests/test_daemon.py` unless noted) | What it asserts |
|---|---|---|
| (a) stop join+killpg | `test_concurrent_stop_calls_share_one_teardown`; `test_stop_is_noop_when_no_process`; `test_stop_with_dead_process_is_noop` (`tests/test_recorder_host.py`); `test_terminate_group_sigkills_process_group`; `test_terminate_group_uses_getpgid_for_pid` | `stop()` joins up to the timeout, then SIGKILLs the process group; idempotent; no-op when no/dead process; `_terminate_group` uses `getpgid` + `killpg` |
| (b) `_unload_host` same lock as load | `test_load_and_unload_serialize_on_the_same_single_flight_lock`; `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded`; `test_armed_state_aborts_unload_via_listening_recheck` | unload acquires the same `_lock` as load (a racing arm waits); teardown routes through `_bounded_shutdown` (the arm's wait is bounded); an armed state aborts the unload via the under-lock re-check |
| (c) idle-unload watchdog | `test_idle_unload_fires_when_disarmed_beyond_threshold`; `test_idle_unload_keeps_resident_within_threshold`; `test_idle_unload_noop_when_listening`; `test_idle_unload_noop_when_not_loaded`; `test_idle_unload_noop_when_never_disarmed`; `test_idle_unload_disabled_when_threshold_zero`; `test_arm_resets_idle_unload_clock`; `test_cold_arm_after_idle_unload_refires_loading_toast` | the watchdog fires after the threshold, noops within threshold / while listening / when not loaded / never disarmed, disables at threshold<=0; the clock resets on arm; a post-unload arm is cold (reloads) |
| (d) bounded (never 90 s) | `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded`; `test_bounded_shutdown_best_effort_never_raises`; the idle-unload + SIGTERM-race tests above | teardown routes through the bounded `host.stop(timeout=5)`; `_bounded_shutdown` is best-effort + never re-raises; the SIGTERM-race concurrent teardown fits ONE bounded `_bounded_shutdown` under `TimeoutStopSec` |
| (e) BUG-1 SIGTERM path | `test_request_shutdown_aborts_and_tears_down_child`; `test_shutdown_is_idempotent_and_single_flight`; `test_sigterm_concurrent_teardown_shares_one_bounded_shutdown` (`4526870` e2e regression) | `request_shutdown` sets `_shutdown` + aborts + calls `_bounded_shutdown` (kills the group); `shutdown` is idempotent + single-flight (`_shutdown_done` + `_teardown_done`); concurrent teardown shares ONE bounded teardown |

---

## §3.4 Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for gaps)

### (i) Two single-flight layers (both intentional, neither redundant)
The daemon `self._lock` (daemon.py:591) serializes **arm-vs-teardown** (`_load_host`@714 vs
`_unload_host`@1222) — a racing arm blocks on this lock, waits for teardown, then spawns fresh (it
never sees a half-torn-down host). `RecorderHost._stop_lock` (recorder_host.py) serializes
**concurrent `stop()` calls** — on the SIGTERM path `request_shutdown()` (signal thread) +
`shutdown()` (main-thread finally) BOTH reach `host.stop()`; under `_stop_lock` the second caller
blocks until the first sets `_proc=None`, then returns immediately (bugfix Issue 1 / P1.M1.T1.S1) —
exactly ONE process-group teardown runs. Both layers are needed; neither is redundant.

### (ii) `_unload_host` calls `_bounded_shutdown(timeout=5.0)`, NOT `host.stop()` directly
`_unload_host`@1240 routes through `_bounded_shutdown`@1620 (a thin router → `host.stop(timeout=5)`
@1643 + a None-host no-op guard @1632 + best-effort try/except @1644-1645). The indirection is
PINNED by `test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded` (so a future
refactor that calls `host.stop()` directly fails the test). Net effect == `host.stop(timeout=5)`.

### (iii) The graceful `"shutdown"` cmd is sent on a DETACHED daemon thread and NEVER waited on
`stop()` puts `("shutdown", {})` on a SEPARATE daemon thread @311-316 (never joined). The child's
command loop BLOCKS in `recorder.text()` while listening, so it does NOT drain `cmd_q` until an
abort unblocks it; and an `mp.Queue.put` could block indefinitely on a wedged child's feeder
thread. The detached thread swallows all errors and dies with the daemon; the `join`+`killpg` is
the ACTUAL teardown. This is WHY teardown is bounded — we never block on the queue.

### (iv) `abort_event.set()` is called BEFORE the join
`stop()`@300-302 sets the abort event BEFORE `proc.join(timeout)`@318 so a child blocked in
`text()` unblocks COOPERATIVELY and the join can complete fast (often << 5 s). The killpg is the
belt-and-suspenders for a child that ignores the abort — both the cooperative nudge AND the hard
kill are deliberate.

### (v) The idle-unload watchdog pre-check is LOCK-FREE
`_maybe_idle_unload`@1181-1187 reads `self._models_loaded` / `self._listening.is_set()` /
`self._disarmed_monotonic` / `time.monotonic()` WITHOUT acquiring `_lock` (atomic CPython reads)
so the common "not time yet" path does NOT contend `_lock` every 1 s tick.
`_unload_host`@1224-1231 does the authoritative re-check UNDER `_lock`. This is a performance design
(don't hammer `_lock` from a background thread every second), not a gap.

### (vi) `request_shutdown` runs abort + `_bounded_shutdown` OUTSIDE `_lock`
`request_shutdown` calls `_safe_abort()`@1505 and `_bounded_shutdown()`@1510 OUTSIDE `_lock`; only
the `_shutdown_done` CLAIM @1498-1503 is under `_lock` (a short critical section). So a slow
teardown cannot wedge the shutdown signal or block concurrent `start`/`stop`/`toggle` (validation
NEW-2).

### (vii) The budget math (~9 s < `TimeoutStopSec=15`)
`host.stop(timeout=5)` → `proc.join(5)` + `_terminate_group()` (killpg) + `join(2)` = ~7 s max per
call (only if the child wedges the FULL join budget; normally far less); + `ControlServer.stop()`
`join(2)` ≈ ~2 s. With daemon single-flight (exactly ONE `_bounded_shutdown` on the SIGTERM path)
the total is ≤ ~9 s — comfortable headroom under systemd `TimeoutStopSec=15`. The default was 10.0
(→ ~12 s/call, ~14 s total, no margin); `5.0` makes the single-teardown path fit (bugfix Issue 1 /
Fix 1C, P1.M1.T2.S2).

---

## §3.5 Conclusion

The bounded teardown faithfully implements **PRD §4.2bis's "Hard requirement — bounded teardown"**
(resolved paragraph) on all 5 properties (a)-(e): `stop()` joins the child for 5 s then SIGKILLs its
process group via `_terminate_group()`/`os.killpg` (a); `_unload_host` tears the resident child down
under the **SAME single-flight lock as load** so a racing arm waits then loads fresh (b); the
`_idle_unload_watchdog` fires `_unload_host` after `auto_unload_idle_seconds` of loaded+not-listening
(c); the teardown is **bounded** (`join(5)`+`killpg`+`join(2)` ≈ ~7 s/call, ≤~9 s total single-flight
< `TimeoutStopSec=15`) so it **CANNOT reproduce RealtimeSTT's ~90 s `recorder.shutdown()` wedge** (d);
and `request_shutdown` kills the child group so a run() loop blocked in `host.text()` returns within
~0.5 s on the SIGTERM path — the BUG-1 fix (e). All with `voice_typing/recorder_host.py` +
`voice_typing/daemon.py` file:line evidence; the `-k` slice is **42 passed, 177 deselected**.

This is the spine the **Idle unload** feature (PRD §4.2bis) depends on: because teardown is bounded
(killpg after a 5 s join — VRAM is force-released regardless of `recorder.shutdown()`'s behavior),
the idle-unload watchdog can fire every 30 min WITHOUT re-triggering the ~90 s wedge AND without
blocking a racing arm under the single-flight lock. The §8 risk row's mitigation (hard timeout +
force-cleanup of the recorder's worker threads / `transcript_process`) is satisfied by the
`setsid`+`killpg` group teardown, which reaches the RealtimeSTT-spawned grandchildren directly.

This certifies the project's acceptance criteria:
- **#9 (idle-unload → reload, bounded teardown)** — "the recorder unloads (~0 VRAM) and a later arm
  reloads it; the teardown is bounded (completes in seconds, no 90 s hang)." Certified by (a)+(b)+
  (c)+(d): the watchdog fires after the threshold (c), teardown shares the load single-flight lock
  so a racing arm waits then loads fresh (b), the join(5)+killpg budget keeps it bounded (a)+(d), and
  the next arm reloads via `_load_host` (~1–3 s, same as a session's first arm).
- **BUG-1 (SIGTERM/systemctl-stop exit)** — "a clean, prompt SIGTERM exit (no SIGKILL after
  `TimeoutStopSec`)." Certified by (e): `request_shutdown` kills the child group so `host.text()`'s
  wait-loop detects child death and returns within ~0.5 s → `run()` exits → `main()`'s finally runs
  → clean exit. The `setsid`+`killpg` group teardown guarantees the VRAM release the §8 risk row
demands.

**Verdict: ✅ COMPLIANT on all 5 properties — no fix needed.** **No source/test files were
modified** (this is a read-only audit — the teardown is PRD §4.2bis + §8-compliant per this
re-verification; no defect was found). The only artifact produced by this subtask is this appended
§3 section. Adjacent concerns are correctly deferred: the **lazy-load state machine** is §1 above
(P1.M2.T2.S1); the **recorder-host IPC mechanism** (incl. the `stop`/`_terminate_group`/`killpg`/
`setsid` primitives this §3 certifies the timing of) is §2 (P1.M2.T2.S2); the **graceful drain** is
P1.M2.T1.S2; the **phase lifecycle** is P1.M2.T1; **lite/mode-switch** is M2.T3; **status** (VT-001/
VT-002) is M3.

---

# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4) vs PRD §4.5 `auto_stop_idle_seconds`

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py`'s **idle AUTO-STOP watchdog**
(`_idle_watchdog` → `_maybe_auto_stop` → `_disarm`) against **PRD §4.5** (`asr.auto_stop_idle_seconds`,
default `30.0`) on the **6 item properties (a)-(f) + the partial-reset hook**. Subtask
**P1.M2.T2.S4** of verification round `006_862ee9d6ef41` — **appended** to this report. §1 above is
P1.M2.T2.S1's lazy-load **state machine**; §2 is S2's recorder-host **IPC mechanism**; §3 is S3's
idle-**UNLOAD** watchdog + bounded teardown (the clock §4 STARTS, §3 READS). This §4 owns the
**auto-stop watchdog** only: disarms the **MIC** after `auto_stop_idle_seconds` (30s) of no recognized
speech **while LISTENING** — it does NOT tear down models (that is §3's job).

**Two-watchdog table (do not confuse §3 and §4):**

| | idle AUTO-STOP (§4, THIS) | idle UNLOAD (§3, S3) |
|---|---|---|
| PRD clause | §4.5 `auto_stop_idle_seconds` (30.0) | §4.2bis Idle-unload `auto_unload_idle_seconds` (1800.0) |
| Fires when | LISTENING, no partial for 30s | DISARMED, no re-arm for 30min |
| Action | `_disarm()` (mic off; models STAY) | `_unload_host()` (models torn DOWN; VRAM freed) |
| Thread | `_idle_watchdog` (daemon.py L1148) | `_idle_unload_watchdog` (daemon.py L1160) |
| Method | `_maybe_auto_stop` (daemon.py L1119) | `_maybe_idle_unload` (daemon.py L1176) |
| Clock | `_last_speech_monotonic` (daemon.py L621) | `_disarmed_monotonic` (daemon.py L626) |
| Composition | auto-stop's `_disarm` stamps `_disarmed_monotonic` (L1022) → starts unload clock for FREE | unload reads `_disarmed_monotonic` |

They COMPOSE: auto-stop's `_disarm` stamps `_disarmed_monotonic`, starting the 30min unload clock
for free. They do NOT overlap — re-auditing the unload watchdog / bounded teardown is §3's job.

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `_idle_watchdog` (L1148-1157, `while not self._shutdown.wait(1.0)` @L1154,
  `try/except` swallow @L1155-1156); `_maybe_auto_stop` (L1119-1147, threshold≤0 return @L1127-1128
  BEFORE lock, `with self._lock` @L1129, not-listening/clock-None guard @L1131, deadline re-check
  @L1133, `logger.info` journal line @L1134-1137, `_disarm` @L1139, `_safe_abort` @L1147 OUT of lock);
  `_disarm` (L1002-1027, `_last_speech_monotonic = None` @L1021, `_disarmed_monotonic =
  time.monotonic()` @L1022 the HAND-OFF, `_feedback.set_listening(False)` @L1026 the toast); `_arm`
  (L987-1000, `_last_speech_monotonic = time.monotonic()` @L994, `_disarmed_monotonic = None` @L995);
  `_touch_speech` (L1029-1040, `_last_speech_monotonic = time.monotonic()` @L1039,
  `_final_pending = True` @L1040); `_build_callbacks._partial` (L217-239, `on_speech` param @L219,
  `on_speech()` call @L237-238); `_load_host` wiring (L751/L757 — `self._touch_speech` as the 5th
  positional `on_speech` arg to the RecorderHost factory, real + fake); `_safe_abort` (L1335-1362,
  gated on `_text_in_flight` @L1355 — returns if not in flight). Also the clock comments @L616-625
  (`_last_speech_monotonic`@L621 + `_disarmed_monotonic`@L626 documenting the atomic-CPython-float
  rationale + the hand-off).
- `voice_typing/config.py` — `auto_stop_idle_seconds: float = 30.0` (L65, the default — PRD §4.5
  match); strict-loader guard @L76 (rejects e.g. string `"thirty"`); in validated-keys list @L89.
- `tests/test_daemon.py` — the `-k 'idle or auto_stop or watchdog'` slice (the contract's run target;
  the 7 auto-stop tests mock CUDA so the slice is fast (~1s) and exercises the watchdog directly).

**Bottom line:** ✅ All 6 item properties (a)-(f) **+ the partial-reset hook** are **COMPLIANT**
(each with file:line evidence in §4.2 below). The `-k 'idle or auto_stop or watchdog'` slice is
**27 passed, 166 deselected in 1.08s** (re-ran live; matches the verified baseline of 27 passed,
1.07s). Seven **non-defect nuances** are recorded in §4.4 so they are not mistaken for gaps (two
watchdogs/two clocks; atomic float store not lock-guarded; `_shutdown.wait(1.0)` not `time.sleep`;
watchdog swallows its own exceptions; abort-after-autostop effectively skipped; INFO line + toast
via `_disarm`; 0-disable before lock). **No source or test files were modified** (this is a
read-only audit — the auto-stop watchdog is PRD §4.5-compliant per the re-verification; no defect
was found). The only artifact produced by this subtask is this appended §4 section.

## §4.1 Method

The audit re-verified each property by:
1. Re-locating the ~6 auto-stop regions (grep, to catch line-number drift — none found; line
   numbers match the research note exactly):
   ```bash
   grep -nE 'def _idle_watchdog|def _maybe_auto_stop|def _disarm|def _arm\b|def _touch_speech|\
   def _build_callbacks|on_speech|def _safe_abort|_last_speech_monotonic|_disarmed_monotonic|\
   auto_stop_idle_seconds|_shutdown\.wait' voice_typing/daemon.py voice_typing/config.py
   ```
2. Reading each region (`_idle_watchdog`@1148, `_maybe_auto_stop`@1119, `_disarm`@1002,
   `_arm`@987, `_touch_speech`@1029, `_build_callbacks`@219/237-238, `_load_host` wiring@751/757,
   `_safe_abort`@1335 in daemon.py; `auto_stop_idle_seconds=30.0`@65 in config.py) and confirming
   the behavior matches PRD §4.5's wording.
3. Re-running the auto-stop test slice (§4.3) and recording the live count.

## §4.2 The 6 auto-stop properties + partial-reset hook — per-point compliance table

| # | item property (LOGIC a-f) | PRD §4.5 expected | code actual (`daemon.py` unless noted) | test (§4.3) | verdict |
|---|---|---|---|---|---|
| (a) | `_idle_watchdog` ticks ~1s | "a background `_idle_watchdog` thread ticks ~1s" | `_idle_watchdog` **L1148-1157**: `while not self._shutdown.wait(1.0):` (**L1154**) → sleeps ~1s PER tick AND returns the instant `_shutdown` is set (no `time.sleep`). `try/except` @L1155-1156 swallows so a transient error never kills the watchdog. | `test_idle_watchdog_actually_disarms_in_background` | ✅ COMPLIANT |
| (b) | deadline re-check under listen lock (late partial cancels stop) | "re-checks the deadline under the listen lock so a late partial cancels the stop" | `_maybe_auto_stop` **L1129** `with self._lock:` → re-reads `self._last_speech_monotonic` under the lock at **L1131** (`is None` guard) + **L1133** (`time.monotonic() - self._last_speech_monotonic < threshold` → return, no disarm). A partial landing between the 1s tick and lock-acq updates `_last_speech_monotonic` (atomic float store via `_touch_speech`@1039); the lock-gated re-read sees the fresh value → stop cancelled. | `test_auto_stop_keeps_alive_with_recent_speech`, `test_auto_stop_noop_when_not_listening`, `test_disarm_clears_the_idle_clock` | ✅ COMPLIANT |
| (c) | `_maybe_auto_stop` disarms IMMEDIATE (not drain) | "auto-disarms immediately (no drain — by definition no utterance is in flight after this long silent)" | **L1139** `self._disarm()` (immediate). Comment **L1142-1145**: "Auto-stop fires only after `auto_stop_idle_seconds` of NO speech, so the last utterance finalized long ago — nothing to drain, an immediate disarm+abort is correct." (Contrast with `_request_stop`'s graceful-drain path — `_drain`/`_final_pending` never set here.) | `test_auto_stop_disarms_when_idle_beyond_threshold`, `test_idle_watchdog_actually_disarms_in_background` | ✅ COMPLIANT |
| (d) | writes journal INFO line | "writes a journal INFO line (`voice-typing auto-stop: 30.0s of no recognized speech; disarming`)" | **L1134-1137** `logger.info("voice-typing auto-stop: %.1fs of no recognized speech; disarming (set [asr] auto_stop_idle_seconds=0 to disable)", threshold)` — emitted UNDER `_lock` (before `_disarm`), so the line precedes the disarm's state changes. `%.1f` formats the configured threshold (30.0). | (covered by the auto-stop tests asserting the disarm) | ✅ COMPLIANT |
| (e) | starts idle-unload clock (hands off to `_idle_unload_watchdog`) | "Auto-stop disarms the mic but does NOT unload models by itself — it starts the slower idle-unload clock" | `_disarm()` **L1022** `self._disarmed_monotonic = time.monotonic()` — stamps the clock that `_idle_unload_watchdog`/`_maybe_idle_unload` reads (§3 @L1191-1192). So 30s auto-stop → 30min idle-unload composes for FREE. Comment @L622-625 documents the hand-off. | `test_disarm_clears_the_idle_clock` | ✅ COMPLIANT |
| (f) | 0 disables (watchdog skips) | "`0` disables" | `_maybe_auto_stop` **L1127-1128** `threshold = self._cfg.asr.auto_stop_idle_seconds; if threshold <= 0: return` — short-circuits BEFORE acquiring `_lock`, so the watchdog's 1s tick is a cheap no-op when disabled (no lock contention). (`auto_stop_idle_seconds` default = `30.0`, config.py L65.) | `test_auto_stop_disabled_when_threshold_zero` | ✅ COMPLIANT |
| (+) | **partial-reset hook** ("Partials reset the clock") | "Partials reset the clock" | `_touch_speech` @**L1039** (`self._last_speech_monotonic = time.monotonic()`) ← `on_speech` param ← `_build_callbacks._partial` @**L237-238** (`on_speech()` after `update_partial`) ← `_load_host` @**L751/L757** (`self._touch_speech` as 5th positional arg to the RecorderHost factory, real + fake) ← child's `('speech', {})` event ← RealtimeSTT realtime partial callback. Finals are always preceded by partials, so this single hook covers all active speech. | `test_touch_speech_resets_the_idle_clock` | ✅ COMPLIANT |

## §4.3 Test evidence

Re-ran the contract's run target live (AGENTS.md Rule 1: inner `timeout 300` + outer harness timeout;
mocked CUDA so the slice is fast):

```bash
$ timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'
...........................                                              [100%]
27 passed, 166 deselected in 1.08s
```

Key evidence tests (`tests/test_daemon.py`):
- `test_auto_stop_disarms_when_idle_beyond_threshold` — 31s silent (> 30.0) → `is_listening()` False. **(c)**
- `test_auto_stop_keeps_alive_with_recent_speech` — 5s silent → stays armed. **(b)/(partial)**
- `test_touch_speech_resets_the_idle_clock` — 60s idle, `_touch_speech()` → stays armed. **(partial reset)**
- `test_auto_stop_disabled_when_threshold_zero` — threshold 0, 9999s idle → stays armed. **(f)**
- `test_auto_stop_noop_when_not_listening` — boot (not listening, clock None) → clean no-op. **(b) guard**
- `test_disarm_clears_the_idle_clock` — `_disarm` clears `_last_speech_monotonic` → stale tick is no-op. **(b)/(e)**
- `test_idle_watchdog_actually_disarms_in_background` — REAL thread, 1.0s threshold, disarms within 4s. **(a)+(c)**

## §4.4 Non-defect nuances (recorded so they are not mistaken for gaps)

1. **Two watchdogs, two clocks.** `_idle_watchdog` (auto-stop, fires while LISTENING) and
   `_idle_unload_watchdog` (idle-unload, fires while DISARMED) are SEPARATE threads with SEPARATE
   clocks (`_last_speech_monotonic` @L621 vs `_disarmed_monotonic` @L626). §3 owns the unload
   watchdog; §4 owns the auto-stop watchdog. They COMPOSE (auto-stop's `_disarm` stamps
   `_disarmed_monotonic` @L1022 → unload reads it @L1191-1192); they do not overlap. (See the
   two-watchdog table at the top of this section.)
2. **`_last_speech_monotonic` is an atomic float store, NOT lock-guarded.** `_touch_speech`@1029
   writes it from the host reader thread WITHOUT `_lock`; `_arm`@994 and `_disarm`@1021 write it
   under `_lock`. The watchdog re-reads it UNDER `_lock` (L1131/L1133). CPython float stores are
   atomic → the watchdog always sees a complete value; the lock serializes the DISARM decision
   against concurrent start/stop/toggle, guaranteeing a partial that landed just before
   lock-acquisition cancels the stop. **This IS the PRD §4.5 "re-check under the listen lock"
   mechanism** — not a missing-lock bug.
3. **`_idle_watchdog` uses `_shutdown.wait(1.0)`, not `time.sleep(1.0)`.** So it both ticks ~1s AND
   exits promptly on shutdown (no orphan thread lingering past `quit`). Mirrors
   `_idle_unload_watchdog`'s tick (§3 @L1166).
4. **The watchdog swallows its own exceptions** (L1155-1156 `except Exception: logger.exception(...)`).
   A transient error in `_maybe_auto_stop` never kills the watchdog — it logs and ticks again next
   second.
5. **abort() after auto-stop is effectively always SKIPPED.** `_maybe_auto_stop` calls
   `_safe_abort()`@1147 ONLY `if disarmed and self._host is not None`, and `_safe_abort`@L1355
   returns immediately `if not self._text_in_flight.is_set()`. After 30s of silence the run() loop
   is in `time.sleep(0.05)` (idle), so `_text_in_flight` is clear → abort() is skipped (correct:
   nothing to wake). The path exists for symmetry with stop/toggle; for auto-stop it is a no-op.
   This is NOT a defect — abort() is "best-effort nudge" per `_safe_abort`'s docstring.
6. **The INFO line + the "Recording Stopped" toast.** `logger.info(...)`@L1134-1137 is the journal
   INFO line (property d). The "Recording Stopped" toast fires via `_disarm()`@L1026 →
   `_feedback.set_listening(False)` → feedback.py fires "Recording Stopped" on the True→False
   transition. This is the SAME disarm path as stop/toggle — the toast wiring itself is a P1.M3.T1
   (feedback) concern, not §4's. §4 certifies only that auto-stop REACHES `_disarm`.
7. **The 0-disable check is BEFORE the lock** (L1127-1128 `if threshold <= 0: return`, before
   `with self._lock`). So a disabled auto-stop never acquires `_lock` on its 1s tick — a cheap
   no-op, no contention with arm/stop/toggle.

## §4.5 Conclusion

**Verdict: ✅ COMPLIANT — all 6 item properties (a)-(f) + the partial-reset hook pass** (daemon.py +
config.py file:line in §4.2). Test slice = **27 passed, 166 deselected in 1.08s**. No defect found →
**NO source or test changes.** The only artifact produced by this subtask is this appended §4 section.

This certifies **PRD §4.5** (Idle auto-stop) in full: the watchdog ticks ~1s (a), re-checks the
deadline under the listen lock so a late partial cancels the stop (b), disarms IMMEDIATELY rather
than draining (c — by definition nothing is in flight after 30s of silence), writes the journal
INFO line (d), starts the slower idle-unload clock via `_disarm` stamping `_disarmed_monotonic` (e —
§3 reads it), and respects `0`-disable as a cheap no-op before the lock (f). Partials reset the
clock via the `_touch_speech` ← `on_speech` ← `_partial` ← `_load_host` hook.

**Acceptance #5 linkage:** PRD §7 #5 = "Daemon survives ≥2 min of silence with no hallucinated output
and trivial CPU use." The idle auto-stop watchdog is the **forgotten-hot-mic guard**: after 30s of
no recognized speech it DISARMS (mic off, models stay), capping the hot-mic exposure window so a mic
left armed cannot hallucinate for minutes (the blocklist filter §4.5/§4.7 catches the classic
hallucinations; auto-stop removes the exposure). Trivial CPU: when disarmed the run() loop is in
`time.sleep(0.05)`; the watchdog itself is a 1s-tick thread. The 2min silence test (T4) exceeds the
30s auto-stop threshold, so it also EXERCISES the armed→auto-stopped disarm transition as a side
effect — §4 certifies that transition is correct (mic disarmed, no hallucination typed, daemon
stable across armed→auto-stopped→unload-clock-running for the full 2min).

Adjacent concerns are correctly deferred: the **lazy-load state machine** is §1 above (P1.M2.T2.S1);
the **recorder-host IPC mechanism** (incl. the `('speech', {})` event that drives `_touch_speech`) is
§2 (P1.M2.T2.S2); the **idle-UNLOAD watchdog + bounded teardown** (the clock §4 STARTS, §3 READS)
is §3 (P1.M2.T2.S3); the **graceful drain** (contrast: stop-with-in-flight drains; auto-stop never
has in-flight → immediate) is P1.M2.T1.S2; the **phase lifecycle** is P1.M2.T1; **lite/mode-switch**
is M2.T3; the **toast wiring** (feedback.py's "Recording Stopped" on the True→False transition) is
M3.
