# Lite-Mode Recon: Implementation-Site Verification + Existing Test Coverage

Read-only recon for PRD §4.2ter (lite mode). Repo root: `/home/dustin/projects/voice-typing`.
**Caveat:** P1.M1.T2.S1 is concurrently editing `daemon.py` (toggle/toggle_lite), so `daemon.py`
line numbers are MOVING. Numbers below are current as of this read; they may shift.
**Full suite status:** `277 passed in 9.71s` (all 5 target files green).

---

## PART 1 — Implementation-Site Verification (9 sites)

| # | Site | Status | File:Line | Key quote |
|---|------|--------|-----------|-----------|
| 1 | `_mode` boot default | ✅ CORRECT | `daemon.py:632` | `self._mode: str = "normal"` (in `__init__`, with the §4.2ter comment at 628-631) |
| 2 | `_load_host(mode)` switch-mode | ✅ CORRECT | `daemon.py:686-775` | def `_load_host(self, mode="normal")`; detection `switch_mode = True` at **706**; teardown `_bounded_shutdown(timeout=5.0)` under `_lock` at **724-729**; factory called with `mode=mode` at **740** (real, `is_listening=...`) + **745** (fake); `self._mode = mode` on success at **754** |
| 3 | `_arm()` → `set_mode` | ✅ CORRECT | `daemon.py:980` | `self._feedback.set_mode(self._mode)   # PRD §4.2ter: publish the armed mode to state.json` |
| 4 | `status_snapshot()["mode"]` | ✅ CORRECT | `daemon.py:1501` | `"mode": self._mode,                     # PRD §4.2ter: "normal" \| "lite"` |
| 5 | `start_lite` / `toggle_lite` | ✅ CORRECT | `daemon.py:1326-1337` / `1368-1390` | both call `_load_host("lite")` then `_arm()`; `toggle_lite` condition is `if listening and mode == "lite": _request_stop() else: _load_host("lite")` |
| 6 | `_dispatch` lite arms | ✅ CORRECT | `daemon.py:1829-1834` | `if cmd == "start-lite": self._daemon.start_lite(); return self._arm_response()` + `if cmd == "toggle-lite": ... self._daemon.toggle_lite()` (mirrors the toggle/start pattern, `_arm_response()` when arming) |
| 7 | `status.sh` ⚡/🎤 render | ✅ CORRECT (mechanism differs from PRD wording) | `status.sh:42-51` | `(if (.listening // false) then ((if (.mode == "lite") then "⚡" else "" end) + "🎤 " + (.partial // "")) else "" end)` |
| 8 | `ctl.py` `_COMMANDS` + mode render | ✅ CORRECT | `ctl.py:35` / `:67` / `:88` | `_COMMANDS = (..., "toggle-lite", "start-lite")`; `mode = response.get("mode", "normal") or "normal"`; `f"mode: {mode}\n"` in the status block |
| 9 | `feedback.py` `_state` + `set_mode` | ✅ CORRECT | `feedback.py:99` / `:145-150` | `"mode": "normal"` in `_state` init (line 99); `def set_mode(self, mode): self._state["mode"] = mode; self._write()` |

### Verbatim quotes (the load-bearing branches)

**Site 2 — switch-mode branch** (`daemon.py:703-729`):
```python
if self._models_loaded and self._host is not None and self._host.is_alive:
    if getattr(self._host, "mode", "normal") == mode:
        return True                       # resident + alive + SAME mode → instant
    switch_mode = True                   # resident but WRONG mode → reload below
else:
    switch_mode = False
...
if switch_mode and self._host is not None:
    logger.info("voice-typing mode switch → %s; reloading recorder-host child", mode)
    with self._lock:
        self._bounded_shutdown(timeout=5.0)
        self._host = None
        self._models_loaded = False
```
Factory call (`daemon.py:738-747`) — note the real/fake split (only the real `RecorderHost` takes `is_listening=`):
```python
if self._host_factory is None:
    host = factory(self._cfg, self._feedback, self._latency, self.on_final,
                   self._on_partial, self._touch_speech, is_listening=self.is_listening, mode=mode)
else:
    host = factory(self._cfg, self._feedback, self._latency,
                   self.on_final, self._on_partial, self._touch_speech, mode=mode)
```

**Site 5 — bodies:**
- `start_lite` (`daemon.py:1326-1337`): `if not self._load_host("lite"): return` then `with self._lock: self._arm()`.
- `toggle_lite` (`daemon.py:1368-1390`):
```python
with self._lock:
    listening = self._listening.is_set()
    mode = self._mode
if listening and mode == "lite":
    self._request_stop()           # armed-in-lite → disarm
else:
    if not self._load_host("lite"):
        return
    with self._lock:
        self._arm()
```

**Site 6 — dispatch arms** (`daemon.py:1829-1834`):
```python
if cmd == "start-lite":              # PRD §4.2ter
    self._daemon.start_lite()
    return self._arm_response()
if cmd == "toggle-lite":             # PRD §4.2ter
    was_listening = self._daemon.is_listening()
    self._daemon.toggle_lite()
    if not was_listening:
        return self._arm_response()
    return {"ok": True, **self._daemon.status_snapshot()}
```

**Site 7 — status.sh jq** (`status.sh:42-51`):
```jq
(if (.listening // false)
   then ((if (.mode == "lite") then "⚡" else "" end) + "🎤 " + (.partial // ""))
   else "" end) as $line
```

---

## PART 2 — Existing Test Coverage

### `tests/test_daemon.py` — **lite coverage is COMPREHENSIVE; a few gaps remain**

Lite/mode tests that ALREADY EXIST:
| Test | Line | What it pins |
|------|------|--------------|
| `test_cfg_to_kwargs_lite_mode_uses_one_model` | 138 | lite kwargs: one model, `use_main_model_for_realtime=True` |
| `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` | 165 | lite + CPU → tiny.en both fields |
| `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` | 185 | only model fields diverge lite vs normal |
| `test_start_lite_loads_lite_host_and_arms` | 2756 | `host.mode=="lite"`, `_mode=="lite"`, `fb.modes==["lite"]` |
| `test_mode_switch_normal_to_lite_reloads` | 2766 | normal→lite tears down + respawns (asserts NEW host `spawn_calls==1`) |
| `test_same_mode_arm_is_instant_no_reload` | 2782 | resident lite + arm lite → same host object (no reload) |
| `test_toggle_lite_while_listening_in_lite_stops` | 2793 | armed-in-lite + toggle_lite → disarm |
| `test_status_snapshot_reports_mode` | 2824 | `status_snapshot()["mode"]` → "normal" at boot, "lite" after start_lite |
| `test_toggle_lite_while_idle_arms_in_lite` | 3483 | idle + F → lite, one spawn |
| `test_toggle_lite_while_armed_in_lite_disarms` | 3494 | armed-in-lite + F → disarm, one spawn |
| `test_toggle_lite_while_armed_in_normal_switches_to_lite` | 3503 | **BUG-B**: armed-in-normal + F → switch to lite (2 spawns, `_mode=="lite"`) |
| `test_toggle_while_idle_arms_in_normal` | 3518 | idle + D → normal |
| `test_toggle_while_armed_in_normal_disarms` | 3529 | armed-in-normal + D → disarm |
| `test_toggle_while_armed_in_lite_switches_to_normal` | 3540 | **BUG-B**: armed-in-lite + D → switch to normal (2 spawns) |
| `test_cold_arm_after_idle_unload_refires_loading_toast` | 2839 | idle-unload → `start()` (normal) reloads cold ("Loading…" refires) |

**Matrix gaps vs the plan's required test list:**
- **MISSING: mode-switch TEARDOWN assertion.** `test_mode_switch_normal_to_lite_reloads` (2766) verifies the NEW host's `spawn_calls==1` but does NOT assert the OLD host's `stop()`/`_bounded_shutdown` was called — `_fake_host_factory` returns a fresh `_FakeHost` per call, so the previous instance's `stop_calls` is never read. The switch_mode branch's teardown is exercised but its effect on the outgoing host is unasserted.
- **MISSING: idle-unload → `start_lite()` reload.** Only the normal `start()` path is covered (2739/2839); the lite reload after idle-unload is not. (Low risk — same `_load_host("lite")` code path — but it's in the matrix.)
- boot `_mode=="normal"`: **covered indirectly** (status_snapshot at boot, line 2827; toggle_lite idle precondition at 3486). No dedicated boot-attr test, but functionally pinned.
- start_lite/toggle_lite set mode + arm: **EXISTS** (2756, 3483-3547).
- status_snapshot `["mode"]`: **EXISTS** (2824).

**Fakes / fixtures (signatures + capabilities):**
- `_FakeHost` (`test_daemon.py:510-567`) — ctor: `__init__(self, cfg, feedback, latency, on_final, on_partial, on_speech, *, force_cpu=False, is_listening=None, mode="normal")`. **YES takes `mode=`; YES has `.mode` (530), `.spawn_calls` (532), `.stop_calls` (534), `.is_alive` (545), `.device`.** `.is_alive` is a `@property` (not a method). `stop(timeout=5.0)` bumps `stop_calls` + best-effort-joins the wrapped recorder.
- `_fake_host_factory(spawn_result=True, device=None, mode=None)` (`test_daemon.py:579-594`) — returns `_factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)`; passes `**kw` through to `_FakeHost` (so the real `_load_host` `mode=mode` kwarg is respected), then **overrides `host.mode = mode` ONLY if `mode is not None`** (the "mode=None-respects-kwarg" detail: leave the fake's default when None, else pin). Sets `spawn_result` + `device`.
- `_make_lazy_daemon(cfg=None, host_factory=None)` (`test_daemon.py:2663-2673`) — builds a `VoiceTypingDaemon(cfg, _DaemonFakeFeedback(), recorder=None, host_factory=host_factory, backend=_FakeBackend(), mic_prober=_ok_probe)` (lazy boot; `_host None`, `_models_loaded False`). Returns `(d, fb)`.
- `_make_daemon(*, recorder=None, recorder_host=None, host_factory=None, backend=None, cfg=None)` (`test_daemon.py:596-606`) — injected/loaded variant. Returns `(d, fb, rec, be)`.
- `_spawning_factory(spawns)` (`test_daemon.py:3472-3480`) — a host_factory that **appends each built `_FakeHost` to `spawns`** and passes `**kw` through (respects the `mode` kwarg — NO closure override). Used by all the cross-mode reload tests to count spawns. **This is the right fake to extend for the teardown gap** (track the old host's `stop_calls` via the `spawns` list).
- `_DaemonFakeFeedback` (`test_daemon.py:429-442`) extends `_FakeFeedback` (`:32-58`): records `.partials`, `.phases`, `.notifies`, `.modes` (via `set_mode` at 53-54), `.finals`, `.listening_states`. Its `snapshot()` returns ONLY `{"phase": ...}` (no mode/models_loaded) — fine because `status_snapshot()` reads `self._mode` directly, not the feedback snapshot.

### `tests/test_control_socket.py` — **dispatch arms covered; status-payload mode NOT verified**
- `_StubDaemon` (`test_control_socket.py:27-47`): has `start_lite`/`toggle_lite` (40-41) that append `"start-lite"`/`"toggle-lite"` to `self.calls`; `status_snapshot()` returns `dict(self._snapshot)` with `listening` overlay — **the default `_snapshot` OMITS `mode`, `phase`, `models_loaded`, `load_error`, `mic_ok`, `mic_error`**.
- `test_dispatch_lite_commands_call_daemon` (`:131-140`) — **EXISTS**: asserts `_dispatch({"cmd":"start-lite"})["ok"] is True` + `calls==["start-lite"]`, and same for `toggle-lite`. Quote:
```python
def test_dispatch_lite_commands_call_daemon(monkeypatch):
    d = _StubDaemon(); srv = daemon.ControlServer(d)
    assert srv._dispatch(json.dumps({"cmd": "start-lite"}))["ok"] is True
    assert d.calls == ["start-lite"]
    d2 = _StubDaemon(); srv2 = daemon.ControlServer(d2)
    assert srv2._dispatch(json.dumps({"cmd": "toggle-lite"}))["ok"] is True
    assert d2.calls == ["toggle-lite"]
```
- **GAP / NUANCE:** `test_dispatch_status_has_all_keys` (`:120-123`) asserts `set(r) == {9 keys}` and **`mode` is NOT in that set** — because `_StubDaemon.status_snapshot()` doesn't emit it. So the dispatch layer does NOT verify the real daemon's `mode` key flows through to the wire response. If dispatch-layer mode coverage is wanted, `_StubDaemon`'s `_snapshot` must gain `mode` (and the 9-key assertion must widen).

### `tests/test_voicectl.py` — **mode render + command-acceptance covered**
- `_STATUS_ON` fixture (`:30-37`): **does NOT include `"mode"`** (so the default-normal branch is the one exercised by the generic status test).
- `test_format_status_multiline_has_partial_and_models` (`:62-72`) — **EXISTS**: asserts `"mode: normal" in text` (the default-when-key-absent path). Quote:
```python
text, code = ctl.format_result("status", _STATUS_ON)
assert code == 0
assert "listening: on" in text
assert "mode: normal" in text                   # PRD §4.2ter: mode rendered (defaults normal)
```
- `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` (`:75-79`) — **EXISTS**: asserts `("toggle-lite","start-lite") ⊆ ctl._COMMANDS` AND `format_result("status", {**_STATUS_ON, "mode":"lite"})` → `"mode: lite" in text`. Quote:
```python
def test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode():
    assert set(("toggle-lite", "start-lite")).issubset(set(ctl._COMMANDS))
    text, code = ctl.format_result("status", {**_STATUS_ON, "mode": "lite"})
    assert code == 0 and "mode: lite" in text
```

### `tests/test_feedback.py` — **mode fully covered (state shape + set_mode)**
- `test_state_shape_has_the_documented_fields` (`:125-129`) — **EXISTS**: `assert set(state.keys()) == {"listening","phase","models_loaded","mode","partial","last_final","ts"}` (the "six fields" question is resolved: it's **seven** fields now, with `mode`).
- `test_set_mode_writes_mode_field` (`:138-143`) — **EXISTS**: default `"normal"` at construction; `set_mode("lite")` writes `"mode":"lite"` to disk.
- `test_snapshot_returns_a_copy_with_the_state_keys` (`:438-441`) — **EXISTS**: `mode` in the snapshot key set.
- `_STATUS_ON`-style fixture: N/A here (tests use the `feedback` fixture → real `Feedback` with mocked `subprocess.run`/`time.monotonic` + `tmp_path` state file; `_read_state` reads it back). Quote of the shape test:
```python
def test_state_shape_has_the_documented_fields(feedback, tmp_path):
    fb, _rec, _clock = feedback
    fb.update_partial("x")
    state = _read_state(tmp_path)
    assert set(state.keys()) == {"listening", "phase", "models_loaded", "mode", "partial", "last_final", "ts"}
```

### `tests/test_status_sh.py` — **all three mode branches covered**
Runs the REAL `status.sh` via subprocess (env-controlled `XDG_RUNTIME_DIR`). Tests:
- `test_status_sh_missing_state_file_exits_zero_with_empty_stdout` — no file → exit 0, empty.
- `test_status_sh_corrupt_state_file_exits_zero_with_empty_stdout` — bad JSON → exit 0, empty.
- `test_status_sh_listening_renders_partial_and_exits_zero` (`:~`) — happy path: writes `{"listening": true, "partial": "hello world"}` (**NO mode key**) → asserts `out.startswith("🎤")` ⇒ **absent mode → 🎤 (no ⚡) COVERED**.
- `test_status_sh_lite_mode_prefixes_bolt` — writes `{"listening":true,"mode":"lite",...}` → `out.startswith("⚡🎤")`; then `"mode":"normal"` → `not out2.startswith("⚡")` and `out2.startswith("🎤")` ⇒ **lite→⚡🎤 + normal→🎤 COVERED**.
- `test_status_sh_not_listening_renders_empty_and_exits_zero` — idle → empty.

**All three required status.sh cases (lite→⚡, normal→🎤, absent→🎤) ARE covered.**

---

## PART 3 — Correctness Concerns / Residual Risks

1. **status.sh mechanism vs PRD wording (NOT a bug — note for test fidelity).** Site 7 implements the lite prefix as `(if (.mode == "lite") then "⚡" else "" end)` — i.e. an equality test, NOT `(.mode // "normal") == "lite"`. Functionally equivalent: in jq `null == "lite"` is `false`, so an absent `mode` key renders `🎤` with no bolt (verified by `test_status_sh_listening_renders_partial_and_exits_zero`, which writes no `mode`). Tests should assert the observed behavior (`⚡` only when `mode` is literally `"lite"`), not assume a `// "normal"` default exists.
2. **dispatch-layer status payload `mode` is unverified (load-bearing gap).** `_StubDaemon.status_snapshot()` (`test_control_socket.py:27-47`) omits `mode`/`phase`/`models_loaded`/`load_error`/`mic_ok`/`mic_error`, and `test_dispatch_status_has_all_keys` (`:120`) hard-pins exactly 9 keys (no `mode`). The cmd→method routing for `start-lite`/`toggle-lite` IS tested, but the `{"ok":True, **status_snapshot()}` payload's `mode` key is not asserted at the dispatch layer. → If you want it, extend `_StubDaemon._snapshot` with `"mode"` and widen the key-set assertion.
3. **mode-switch teardown (`stop_calls`) is unasserted (gap).** `test_mode_switch_normal_to_lite_reloads` (2766) and the BUG-B cross-mode tests (3503/3540) count `spawns`/`spawn_calls` but never read the OUTGOING host's `stop_calls` to prove `_bounded_shutdown` ran. `_fake_host_factory` returns a fresh instance per call, so the old host's counter is dropped. Use `_spawning_factory(spawns)` (which retains every built host) and assert `spawns[0].stop_calls == 1` on a switch. (The `_bounded_shutdown` itself is well-tested in the SIGTERM/teardown suite with different fakes — the gap is only the mode-switch path.)
4. **idle-unload → `start_lite()` reload untested.** Only normal `start()` after idle-unload is covered (2839). The lite path is the same `_load_host("lite")` mechanism, so risk is low, but it's in the required matrix.
5. **`toggle_lite` is under concurrent edit (S1).** The `if listening and mode == "lite"` condition is stable as of this read (1368-1390), but S1 may rewrite it. Re-confirm before finalizing any toggle_lite-targeted test.

## Start Here
`tests/test_daemon.py:3472` (`_spawning_factory`) + `:2663` (`_make_lazy_daemon`) — these two are the seam for any new lite tests (mode-switch teardown count, idle-unload→lite). For dispatch-layer mode coverage, start at `tests/test_control_socket.py:27` (`_StubDaemon`).
