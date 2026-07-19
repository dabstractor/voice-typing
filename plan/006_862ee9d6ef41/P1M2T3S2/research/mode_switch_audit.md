# Research Note — P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking Audit

> Pre-verified audit of the daemon's mode-switch lifecycle against PRD §4.2ter arming rules.
> This is an AUDIT (not an implementation): the deliverable is the `gap_lite.md` section.
> **VERDICT: all 6 clauses (a)-(f) are ✅ COMPLIANT — no source/test fix needed.**
> Contract test (re-run live): `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q
> -k 'mode or toggle_lite or start_lite or switch'` → **15 passed, 178 deselected in 0.04s.**

---

## §0 — THE 6-CLAUSE COMPLIANCE TABLE (file:line + verdict)

| Clause | PRD §4.2ter expected | Code actual (file:line) | Verdict |
|---|---|---|---|
| **(a)** command→mode routing | `toggle`/`start`→`_load_host("normal")`; `toggle-lite`/`start-lite`→`_load_host("lite")` | `daemon.py start()@1365→1370 _load_host("normal")`; `start_lite()@1376→1384 _load_host("lite")`; `toggle()@1393→1415 _load_host("normal")`; `toggle_lite()@1426→1447 _load_host("lite")`; socket `_dispatch@1892` "toggle"→`toggle()`@1903, "start"→`start()`@1914, "start-lite"→`start_lite()`@1917, "toggle-lite"→`toggle_lite()`@1921, "stop"→`stop()`@1927, "status"→`status_snapshot()`@1929; `ctl.py _COMMANDS@37` = all 7 + routing@199-202 (loading-hint for the 4 arm cmds) | ✅ COMPLIANT |
| **(b)** same-mode resident → instant arm | arm mode X while resident=X → instant (models already resident) | `_load_host@715 if self._models_loaded and self._host is not None and self._host.is_alive:` → `@716 if getattr(self._host,"mode","normal")==mode:` → `@717 return True` (instant, NO reload). `RecorderHost.mode@property@168-170`; `is_alive@173-175`. Test `test_same_mode_arm_is_instant_no_reload@2892` (asserts `d._host is host1`, no teardown) | ✅ COMPLIANT |
| **(c)** different-mode resident → tear down + respawn in new mode | arm mode X while resident=OTHER → tear down + respawn in X (~1-3s reload) | `_load_host@718 switch_mode=True` (resident but WRONG mode) → `@736 if switch_mode and self._host is not None:` → `@738 with self._lock: self._bounded_shutdown(timeout=5.0); @740 self._host=None; @741 self._models_loaded=False` → falls through to `@749-757 factory(..., mode=mode)` spawn. Tests `test_mode_switch_normal_to_lite_reloads@2875` (new host mode=='lite') + `test_mode_switch_stops_outgoing_host@2927` (outgoing host.stop_calls==1) | ✅ COMPLIANT |
| **(d)** self._mode updated on arm | resident child's mode tracked in self._mode | `_load_host@766 self._mode=mode` (on successful spawn ONLY); field init `@644 self._mode:str="normal"`; `status_snapshot@1567 "mode":self._mode`. Tests `test_start_lite_loads_lite_host_and_arms@2863` (`d._mode=="lite"`) + `test_status_snapshot_reports_mode@2918` (boot normal, post-arm-lite lite) | ✅ COMPLIANT |
| **(e)** feedback.set_mode on arm/disarm | state.json "mode" written on every arm/disarm | `_arm@998 self._feedback.set_mode(self._mode)` (arm path); `feedback.set_mode@145-150` writes `_state["mode"]`+`_write()`. `_disarm@1041-1051` does NOT call set_mode (only set_listening(False)+set_phase("idle")). **De-facto correct:** disarm does not change `self._mode` (resident child unchanged), so the value from the most recent `_arm` persists and is already current. Test `test_start_lite_loads_lite_host_and_arms@2863` (`fb.modes==["lite"]`) | ✅ COMPLIANT (nuance §4.1) |
| **(f)** stop disarms regardless of mode | stop disarms either mode | `stop()@1388→_request_stop()@1054`; `_request_stop@1056 if self._host is not None and self._text_in_flight.is_set() and self._final_pending:`→drain, else `@1062-1064 with self._lock: self._disarm(); ... self._safe_abort()`. **NO mode check** — mode-agnostic. `_dispatch@1926 "stop"→self._daemon.stop()`. Test `test_toggle_lite_while_listening_in_lite_stops@2904` (disarms lite) | ✅ COMPLIANT |

---

## §1 — THE COMMAND→MODE→LOAD CHAIN (end-to-end)

```
voicectl toggle   → ctl.send_command("toggle")   → socket {"cmd":"toggle"}
  → ControlServer._dispatch("toggle")@1892       → self._daemon.toggle()@1903
    → toggle()@1393: read (listening, mode) under _lock@1411-1412
      → if listening and mode=="normal": _request_stop()@1414 (disarm-in-normal)
      → else: _load_host("normal")@1415 → (if ok) _arm()@1418

voicectl toggle-lite → ctl.send_command("toggle-lite") → socket {"cmd":"toggle-lite"}
  → _dispatch("toggle-lite")@1919 → self._daemon.toggle_lite()@1921
    → toggle_lite()@1426: read (listening, mode) under _lock@1436-1437
      → if listening and mode=="lite": _request_stop()@1439 (disarm-in-lite)
      → else: _load_host("lite")@1447 → (if ok) _arm()@1450

voicectl start / start-lite → start()@1365 / start_lite()@1376
  → _load_host("normal"|"lite")@1370/@1384 → _arm()@1372/@1386

voicectl stop → _dispatch("stop")@1926 → stop()@1388 → _request_stop()@1054 (mode-AGNOSTIC)
voicectl status → _dispatch("status")@1929 → status_snapshot() (carries "mode"@1567)
voicectl quit  → _dispatch("quit")@1931 → request_shutdown() + on_quit
```

**_load_host mode switch internals** (`_load_host@698-795`):
1. `@713-720` fast path under `_lock`: resident+alive+SAME mode → `return True` (instant); resident+WRONG mode → `switch_mode=True`; nothing resident → `switch_mode=False`.
2. `@721-725` single-flight: if `_loading`, wait on `_load_cond` + return whether the in-flight spawn ended in the requested mode.
3. `@727-728` we are the loader: set `_loading=True`, `_load_error=None`, phase "loading", models_loaded False.
4. `@729-730` cold-load "Loading…" toast (`_COLD_LOAD_NOTIFY_LOADING`) — fires for cold loads AND mode switches.
5. `@736-742` **switch teardown**: `if switch_mode and self._host is not None:` → log → `with self._lock: self._bounded_shutdown(timeout=5.0); self._host=None; self._models_loaded=False`.
6. `@749-757` heavy spawn OUTSIDE `_lock` (status/stop stay responsive): `factory(..., mode=mode)`.
7. `@759-766` re-acquire `_lock`: on `ok` → publish `_host`, `_models_loaded=True`, **`self._mode=mode`@766**, phase idle, models_loaded True.
8. `@769-786` on failure → stop the half-built host, `_load_error=...`, `_models_loaded=False`, `_host=None`, phase unloaded.

---

## §2 — THE BOUNDED-RELOAD GUARANTEE (acceptance #10)

Acceptance #10: "switching modes costs **one bounded reload**." The mechanism:

- `_load_host@736-742` switch branch calls **`_bounded_shutdown(timeout=5.0)`@738** (the SAME bounded
  teardown primitive `_unload_host@1239` uses for idle-unload — NOT `_unload_host` itself, which has
  idle-threshold guards that would no-op during an armed/discharged switch).
- `_bounded_shutdown@1620-1645` → `self._host.stop(timeout=timeout)` → for a REAL RecorderHost,
  `os.killpg` (terminates the child PROCESS GROUP, releases ALL VRAM incl. grandchildren) bounded by
  `proc.join(5)` + `_terminate_group()` + `join(2)` = ~7s max; SIGKILL the group if it wedges.
- So a mode switch = exactly ONE bounded teardown (≤~7s) + ONE spawn (~1-3s on CUDA) = the "one bounded
  reload" of acceptance #10. Pinned by `test_mode_switch_stops_outgoing_host@2927`
  (outgoing host.stop_calls==1, new host.stop_calls==0).

---

## §3 — TEST EVIDENCE (the 15 tests the contract command selects)

Command: `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'`
Result (re-run live, 2026): **15 passed, 178 deselected in 0.04s.**

The 15 selected tests (by `-k` matching `mode`/`toggle_lite`/`start_lite`/`switch` in name OR params):
- `test_start_lite_loads_lite_host_and_arms@2863` — (a)+(d): start_lite→lite host; d._mode=="lite"; fb.modes==["lite"]
- `test_mode_switch_normal_to_lite_reloads@2875` — (c): normal→lite reloads; new host mode=="lite"
- `test_same_mode_arm_is_instant_no_reload@2892` — (b): re-arm same mode = SAME host object, no reload
- `test_toggle_lite_while_listening_in_lite_stops@2904` — (f): stop disarms lite
- `test_status_snapshot_reports_mode@2918` — (d): status_snapshot["mode"] boot=normal, post-arm-lite=lite
- `test_mode_switch_stops_outgoing_host@2927` — (c)+#10: outgoing host.stop_calls==1 (bounded teardown)
- `test_start_lite_after_idle_unload_reloads_in_lite@2951` — (c): reload-in-lite after idle-unload
- `test_toggle_lite_while_idle_arms_in_lite@3696`, `_while_armed_in_lite_disarms@3708`,
  `_while_armed_in_normal_switches_to_lite@3719` — (a)+(c): toggle_lite semantics
- `test_toggle_while_armed_in_lite_switches_to_normal@3753` — (a)+(c): toggle normal-switch semantics
- `test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening@3790` +
  `test_toggle_while_armed_in_lite_failed_reload_clears_listening@3809` +
  `test_failed_cross_mode_toggle_status_snapshot_is_honest@3826` — (e) edge: failed cross-mode switch
  → _disarm clears listening, status honest (listening:off + load_error), mode persists
- `test_toggle_lite_docstring_says_pressing_d_not_f@3851` — (a) docstring guard
- (+ param-id matches like `lite_post_speech_silence_duration` captured by `-k switch`/`-k mode`)

---

## §4 — NON-DEFECT NUANCES (record; do NOT flag as gaps)

### §4.1 — set_mode is called in _arm, NOT in _disarm (clause e nuance)
`_arm@998` calls `self._feedback.set_mode(self._mode)`; `_disarm@1041-1051` does NOT. This is
**correct, not a gap**: disarm does not change `self._mode` (it only clears `_listening` + sets phase
"idle"; the resident child is unchanged), so the mode value from the most recent `_arm` persists in
state.json and is already current. PRD §4.2ter "written on every arm/disarm" describes the OUTCOME
(state.json mode stays current), satisfied de facto. The ONE edge — a FAILED cross-mode switch
(resident X torn down, Y load failed, then `_disarm`) — leaves `self._mode` at the prior value with
`_models_loaded=False`; `status_snapshot` is still honest via `listening:off` + `load_error`
(`test_failed_cross_mode_toggle_status_snapshot_is_honest@3826`). Do NOT add a redundant set_mode to
_disarm — it would be a no-op and the resident mode is genuinely unchanged on disarm.

### §4.2 — the switch uses _bounded_shutdown, NOT _unload_host (clause c nuance)
`_load_host@738` calls `_bounded_shutdown(timeout=5.0)` directly, NOT `_unload_host()`. `_unload_host
@1204` is the IDLE-triggered wrapper: it re-checks the full unload condition (not resident / listening /
threshold) and would NO-OP during a mode switch (the daemon is not past the idle threshold when the
user switches modes). The switch reuses the bounded-teardown PRIMITIVE (`_bounded_shutdown`, the same
one `_unload_host` delegates to @1239) — correct factoring, not a gap. Both paths terminate the child
process group and are bounded (~7s).

### §4.3 — mode is read+acted OUTSIDE _lock in toggle/toggle_lite (race-tolerance nuance)
`toggle@1411-1412` / `toggle_lite@1436-1437` read `(listening, mode)` together under `_lock`, then call
`_load_host` OUTSIDE `_lock` (it acquire-release-reacquires that lock; under _lock it would deadlock).
This is the SAME race-tolerant read/act split as the abort()-outside-_lock design: the `_listening`
Event + `on_final` gate are the source of truth; toggle is user-paced. Not a gap — documented in the
toggle docstring @1393-1410. Tested by the toggle_lite/toggle semantics tests @3696-3826.

### §4.4 — set_mode default "normal" at boot (clause d nuance)
`self._mode@644` defaults to "normal"; `feedback._state["mode"]@99` defaults to "normal".
`status_snapshot["mode"]@1567` reports "normal" at boot before any arm. Correct — the daemon boots in
normal mode (the first arm of either mode overwrites it). `test_status_snapshot_reports_mode@2918`
pins boot=="normal".

### §4.5 — self._mode set on SUCCESS only (clause d nuance)
`_load_host@766 self._mode=mode` runs ONLY in the success branch (`if ok`). On failure, `self._mode`
is left unchanged (the prior value). This is intentional: a failed load leaves the daemon with no
resident child (`_models_loaded=False`, `_host=None`), so `self._mode` reflects the last SUCCESSFUL
mode, and `status_snapshot` pairs it with `models_loaded:False` + `load_error` so the state is honest.
Not a gap — covered by the failed-cross-mode-switch tests @3790-3826.

---

## §5 — gap_lite.md SECTION STRUCTURE (what S2 appends)

S2 APPENDS a section to `gap_lite.md` (the file S1 creates with title "# Gap Report — P1.M2.T3.S1:
Lite Recorder Construction vs PRD §4.2ter"). The S2 section is a `## ` (H2) — a SIBLING of S1's H1
content, NOT a new file (the item says "Append to gap_lite.md"). Format mirrors `gap_lifecycle.md`'s
per-subtask section pattern (S1-S4 each appended a §N to gap_lifecycle.md).

**Section layout** (mirror gap_lifecycle.md's voice + table convention):
1. `## Gap Report — P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking vs PRD §4.2ter`
2. **Date + Scope** (the 6 clauses a-f) + **Audited artifacts** (file:line list).
3. **Bottom line:** ✅ COMPLIANT (all 6 clauses) + the 15-test count + acceptance #10 (one bounded reload).
4. **§1 Method:** the grep commands + the contract test command.
5. **§2 per-clause compliance table:** PRD §4.2ter expected | code actual (file:line) | ✅ — for (a)-(f).
6. **§3 test evidence:** the 15 tests + their clauses (from research §3).
7. **§4 non-defect nuances:** (1) set_mode in _arm not _disarm; (2) switch uses _bounded_shutdown not
   _unload_host; (3) read/act outside _lock; (4) default "normal" at boot; (5) set_mode on success only.
8. **Conclusion:** ties verdict to PRD §4.2ter arming rules + acceptance #10 (switching = one bounded
   reload; same-mode instant; cross-mode teardown+respawn; stop mode-agnostic; self._mode tracks resident).

---

## §6 — SCOPE BOUNDARIES (disjoint from siblings)

- **P1.M2.T3.S1** (lite CONSTRUCTION kwargs — the lite delta: one-model, silence gate, CPU fallback):
  CREATES `gap_lite.md` (the H1 file). S2 APPENDS to it. Disjoint TOPIC (construction kwargs vs reload
  mechanic) but SAME FILE (lite audit area — mirrors gap_lifecycle.md accumulating S1-S4 sections).
- **P1.M2.T3.S3** (T7 lite test COVERAGE audit): references S2's reload tests. Disjoint (test coverage
  vs reload mechanic).
- **P1.M2.T4.S1** (FULL common recorder kwargs — all §4.4 params): disjoint (kwargs vs lifecycle).
- **P1.M2.T2.S3** (bounded teardown — killpg after join(5s)): S2 REFERENCES `_bounded_shutdown` (the
  reload's teardown primitive) but does NOT re-audit the teardown itself (that's S3's gap_lifecycle.md
  §3 section). S2 cites line numbers only.

---

## §7 — RE-GREP COMMANDS (re-locate the audited lines on the live tree)

```bash
cd /home/dustin/projects/voice-typing
grep -nE 'def start|def start_lite|def stop|def toggle|def toggle_lite|_load_host\(|switch_mode|self\._mode|set_mode|_bounded_shutdown|def _dispatch|"toggle"|"start"|"stop"|"status"|"quit"|"toggle-lite"|"start-lite"' voice_typing/daemon.py
grep -nE 'def set_mode|"mode"|self\._state\["mode"\]' voice_typing/feedback.py
grep -nE 'def mode|is_alive|self\._mode|target=_worker_main' voice_typing/recorder_host.py
grep -nE '_COMMANDS|toggle-lite|start-lite|def send_command|def _send_command_with_loading_hint' voice_typing/ctl.py
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'
```