# PRP — P1.M1.T2.S2: daemon.py + recorder_host.py mode collapse (single-path Rev 2 substrate)

## Goal

**Feature Goal**: Collapse the two-mode (normal/lite) recorder machinery to the Rev 2 **single-mode** path: `toggle`/`start` arm the ONE single-model recorder (`small.en` for partials+finals; `tiny.en` on CPU), `stop` disarms. Delete the mode-switch reload, `start_lite`/`toggle_lite`, the `start-lite`/`toggle-lite` socket commands, `self._mode`, and the `lite=` construction threading — while **keeping `mode` in status/state.json as the CONSTANT `"lite"`** (§4.6 schema stable; ctl rendering untouched). This also repairs the current red-transient: T1.S1 removed `AsrConfig.final_model/realtime_model`, so `daemon.py:152-153` raises AttributeError today; and it consumes S1's 3-key `{device, compute_type, model}` cuda_check contract.

**Deliverable** (2 source files + 3 test files rewritten):
1. `voice_typing/daemon.py` — single-branch `cfg_to_kwargs` (no `lite` param), 3-key `_resolve_device_config`/`_unprobed_device_config`/`_log_resolved_device`, modeless `_load_host()`, deleted `_load_recorder`/`start_lite`/`toggle_lite`/lite-dispatch, collapsed `toggle()`, constant `mode:"lite"` in status/feedback, single `model` key in `status_snapshot`, `lite=`-less `build_recorder`/`_construct`, module docstring (Mode A).
2. `voice_typing/recorder_host.py` — `mode` param/property/spawn-arg/`_worker_main(mode)`/`lite=` threading deleted; `_child_resolved_device` + ready payload → 3-key; module docstring (Mode A).
3. `tests/test_daemon.py` — the ~25-test two-mode family → single-path equivalents (TDD: tests FIRST).
4. `tests/test_control_socket.py` — delete the lite-dispatch test; keep status-carries-mode.
5. `tests/test_recorder_host.py` — lite-flag/spawn-args asserts → modeless.

**Success Definition**:
- (a) `grep -c 'final_model\|realtime_model\|_mode\b\|start_lite\|toggle_lite\|start-lite\|toggle-lite' voice_typing/daemon.py voice_typing/recorder_host.py` → 0 (module docstrings included).
- (b) `cfg_to_kwargs(cfg)` (no kwargs) returns `model == realtime_model_type == "small.en"`, `use_main_model_for_realtime is True`, `post_speech_silence_duration == cfg.asr.lite_post_speech_silence_duration`, device/compute_type/language/pause passthrough; with `resolved=dict(CPU_FALLBACK)` both model slots are `"tiny.en"` (S1's re-pinned tests go green).
- (c) `_load_host()` takes no mode param; a resident+alive host short-circuits `True` (no switch branch); `_FakeHost` fakes are spawned with NO `mode` kwarg.
- (d) `toggle()` disarms iff `listening` (bare condition); `start()` arms; `stop()` disarms; socket `toggle-lite`/`start-lite` now get `{"ok":false,"error":"unknown command: ..."}`.
- (e) `status_snapshot()` has `"mode": "lite"` (constant) and a single `"model"` key (13 keys total); `_arm` calls `self._feedback.set_mode("lite")`.
- (f) Full fast suite green: `timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh` → 0 failures (S1's red-transient sites included).
- (g) No edits to `ctl.py` (S3), `prefetch.py`/`hypr-binds.conf`/`tests/ACCEPTANCE.md` (S4), `feedback.py`/`config.py`/`config.toml` (settled), `cuda_check.py` (S1's).

## User Persona

**Target User**: the end user — one keybind (`toggle`) arms the single-model dictation engine; ~half the VRAM, faster finals, no mode juggling. (Rev 2 streaming lands on this substrate: P1.M2.T5/T6/T7.)
**Pain Points Addressed**: the two-mode substrate is dead weight after the Rev 2 decision (PRD §4.2ter/§4.2quater) — the large `distil-large-v3` never runs; mode-switch reloads, dual keybinds, and the 4-key resolve shape are the removed complexity. Also repairs the live AttributeError from T1.S1's schema change.

## Why

- **Rev 2 single-mode collapse is the plan's substrate milestone** (P1.M1.T2). T1.S1 already made `lite_model` the only model field; S1 collapses cuda_check to `{device, compute_type, model}`. The daemon+host are the last two-mode consumers — this subtask finishes the collapse so P1.M2 (streaming engine) builds on one path.
- **The transient is already red — this fixes it.** T1.S1 removed `AsrConfig.final_model/realtime_model`; `daemon._resolve_device_config` (daemon.py:152-153) raises AttributeError, and S1's re-pinned tests expect the 3-key end state. Landing T2.S2 turns the whole plan's red window green.
- **One-place model mapping.** Post-collapse, the CPU substitute mapping (`small.en`→`tiny.en`) lives ONLY in cuda_check's `CPU_FALLBACK` (which overrides defaults wholesale on no-CUDA). cfg_to_kwargs just fills BOTH model slots from `resolved["model"]` — the old daemon-side `"tiny.en" if device=="cpu"` discrimination is deleted.
- **Scope discipline.** ctl.py's command surface is S3; prefetch/binds/ACCEPTANCE are S4; feedback.py keeps `set_mode` (the constant flows through the existing call); the heavy GPU tests' lite sections are P1.M3.T9.S1's adjustments.

## What

Rewrite `cfg_to_kwargs` to a single branch; make `_load_host()` modeless; delete `start_lite`/`toggle_lite`/`_load_recorder`/the lite dispatch arms; collapse `toggle()`; constant `"lite"` mode in `_arm`/`status_snapshot`; single `model` status key; drop `lite=` from `build_recorder`/`_construct`; collapse `RecorderHost`'s mode surface; rewrite the test family single-path (tests first). Verbatim line numbers below were verified against HEAD `7eed2bb` + S1-as-contract (line numbers move as S1 lands — navigate by symbol).

### Success Criteria

- [ ] (a) zero stale refs (the grep above) in both files.
- [ ] (b) single-path kwargs contract (small.en both slots CUDA; tiny.en both slots via `resolved=CPU_FALLBACK`).
- [ ] (c) modeless `_load_host` (no param, no switch branch, no `mode=` at the factory call sites).
- [ ] (d) `toggle/start/stop` single-path; lite socket cmds → unknown-command.
- [ ] (e) `"mode": "lite"` constant + single `"model"` key in status; `set_mode("lite")` in `_arm`.
- [ ] (f) full fast suite 0 failures.
- [ ] (g) sibling files untouched (`git diff --name-only` ⊆ the 5 deliverable files).

## All Needed Context

### Context Completeness Check

_Pass._ Every edit site is line-cited in the research note with its end state; the test family is enumerated (map §6); the S1 3-key contract and T1.S1 schema are pinned; the fakes seam (`_FakeHost`/`_fake_host_factory`/`_make_lazy_daemon`/`_cuda_resolve`) is documented. An agent new to the repo can implement from this PRP + the research note + `daemon_control_map.md`.

### Documentation & References

```yaml
# MUST READ — the structural map (every claim cites file:line)
- docfile: plan/007_cfc245548aec/architecture/daemon_control_map.md
  why: "§1 the full mode-machinery map (cfg_to_kwargs 158-215, _FIXED_KWARGS 100-114, _load_host 710-805,
        _mode lifecycle 656/778/1039/1632, RecorderHost mode sites); §4 dispatch + status_snapshot key
        list + _arm_response; §6 the COMPLETE two-mode test list (~25 daemon tests w/ line numbers +
        control_socket/voicectl/recorder_host/feedback sites); §7 mode consumers (ctl.py:69/90,
        hypr-binds.conf:52, test_idle_and_gpu T7); 'Key seams' summary."
  critical: "§6 IS the rewrite list. §7's ctl.py consumer stays working BECAUSE mode stays constant 'lite'."

# MUST READ — the input contracts + verified live-state
- docfile: plan/007_cfc245548aec/P1M1T2S2/research/mode_collapse_edit_sites.md
  why: "The verified edit-site tables for BOTH files (with end states), the landing-state analysis
        (T1.S1 landed ⇒ daemon.py:152-153 AttributeError-red TODAY; S1 not yet landed ⇒ gate on it),
        the one-place-CPU-mapping simplification, the full test-family disposition, sibling boundaries."
  critical: "§1 sequencing: S1's cuda_check 3-key MUST land first — cfg_to_kwargs reads resolved['model'].
            Gate: grep '\"model\": \"small.en\"' voice_typing/cuda_check.py."

# MUST READ — the 3-key resolve contract (S1, parallel; treat as landed)
- docfile: plan/007_cfc245548aec/P1M1T2S1/PRP.md
  why: "Defines CUDA_DEFAULTS={cuda,float16,small.en} / CPU_FALLBACK={cpu,int8,tiny.en}; resolve()
        CPU-override-wins-over-defaults + fresh-dict semantics (UNCHANGED); the two test_daemon sites it
        re-pinned to END-state expectations (tiny.en both slots) that go GREEN when this subtask lands;
        its Downstream section names THIS task's exact rewrite points."
  critical: "If cuda_check.py still shows 4-key dicts at implementation time, S1 hasn't landed — STOP and
            flag (do NOT collapse daemon against a 4-key resolver)."

# THE SCHEMA (landed) — lite_model is THE model; lite_post is THE duration
- file: voice_typing/config.py
  why: "AsrConfig.lite_model @52 ('THE model — loads once'), post_speech_silence_duration @57 (0.6,
        now unused by kwargs — leave the field; schema churn is settled), lite_post… @58 (0.8, THE
        endpointer duration per §4.2quater)."
  gotcha: "Do NOT remove cfg.asr.post_speech_silence_duration (57) even though nothing reads it after
           the collapse — T1.S1 settled the schema; removing it rewrites config.toml/tests for no gain."
```

### Current Codebase tree (relevant slice — T1.S1 landed; S1 parallel)

```bash
voice_typing/daemon.py         # ← EDIT (the big one): 95-219 kwargs region; 285-345 build_recorder/_construct;
#                                #   656 _mode; 700-708 _load_recorder; 710-805 _load_host; 1039 set_mode;
#                                #   1430-1516 start/start_lite/toggle/toggle_lite; 1613-1646 status_snapshot;
#                                #   1669-1684 _unprobed; 957-975 _log_resolved; 1989-2013 dispatch.
voice_typing/recorder_host.py  # ← EDIT: 23 docstring; 114 mode param; 125 _mode; 168-170 property;
#                                #   195 spawn args; 427 _worker_main(mode); 458-478 lite=; 681-714 _child_resolved_device.
tests/test_daemon.py           # ← EDIT: rewrite the §6 family (138-313 kwargs; 2964-3070 + 3865-4060 mode family).
tests/test_control_socket.py   # ← EDIT: delete @131 lite dispatch; keep @143 mode-carries.
tests/test_recorder_host.py    # ← EDIT: lite-flag/spawn-args asserts.
# UNTOUCHED: ctl.py (S3), prefetch.py/hypr-binds.conf/ACCEPTANCE (S4), feedback.py/config.py/config.toml/cuda_check.py.
```

### Desired Codebase tree with files to be changed

```bash
# (same 5 files, MODIFIED — no new files, no deletions of files)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — SEQUENCE: S1 (cuda_check 3-key) MUST LAND FIRST. cfg_to_kwargs reads resolved["model"];
# against S1's pre-collapse 4-key dicts that KeyErrors. Gate before starting:
#   grep -q '"model": "small.en"' voice_typing/cuda_check.py || { echo "S1 not landed — STOP"; exit 1; }
# Also expect the tree to be RED on entry (daemon.py:152-153 cfg.asr.final_model AttributeError from
# T1.S1) — that red is yours to fix, not to investigate.

# CRITICAL #2 — TDD ORDER: REWRITE THE TESTS FIRST (the contract's "Implicit TDD"). Concretely: rewrite
# the test family to the single-path expectations, watch them fail against the current source, THEN
# collapse the source and watch them pass. This pins the end-state contract before touching daemon.py.

# CRITICAL #3 — THE FAKE-FACTORY CALL SITE. _load_host currently passes mode=mode to BOTH the real
# RecorderHost ctor (762-767) and the host_factory fake path (768-772). After collapse pass NEITHER.
# _FakeHost's ctor keeps its `mode="normal"` DEFAULT (harmless; fakes may retain the attr) — but every
# test that FORCED a mode via _fake_host_factory(mode=...) or asserted host.mode dies with the family.

# CRITICAL #4 — MODE STAYS AS A CONSTANT, NOT DELETED FROM THE SURFACE. status_snapshot()["mode"]="lite"
# (constant literal — no self._mode), _arm → feedback.set_mode("lite"). feedback.py:99's "normal" default
# remains the pre-arm value in state.json until the first arm — harmless (§4.6 schema stable; ctl.py:69
# `response.get("mode","normal")` renders either). Do NOT touch feedback.py or ctl.py.

# CRITICAL #5 — THE CPU MAPPING MOVES (dies) IN THE DAEMON. The old lite branch's
# `"tiny.en" if resolved["device"]=="cpu" else cfg.asr.lite_model` is DELETED — cuda_check's
# CPU_FALLBACK override already yields model="tiny.en" wholesale on no-CUDA. cfg_to_kwargs NEVER
# discriminates on device for the model; it just fills both slots from resolved["model"].

# CRITICAL #6 — status_snapshot KEY COUNT 14→13. Replace the final_model/realtime_model pair with ONE
# "model" key (dev.get("model", "unknown")). S1 re-pinned test_daemon's resolved-dict sites to 3-key
# expectations — those go green here; any OTHER test pinning the 14-key set gets the 13-key update.

# CRITICAL #7 — HEAVY TESTS ARE NOT YOURS. test_feed_audio.py (653/679) and test_idle_and_gpu.sh T7
# (535-578, the real mode-switch roundtrip) break with the collapse — P1.M3.T9.S1 adjusts them. Do NOT
# run or edit them here (AGENTS.md: heavy GPU tests run separately; T7 needs a quiet room + GPU).

# GOTCHA #8 — _load_recorder IS AN ALIAS, NOT A METHOD CALLER. Its own docstring says it aliases
# _load_host("normal"). Check for external callers (grep '_load_recorder' across the repo) before
# deleting; if only daemon-internal + its tests reference it, delete freely (tests in the §6 family).

# GOTCHA #9 — MODULE DOCSTRINGS ARE MODE-A DOCS. daemon.py + recorder_host.py module docstrings carry
# two-mode prose (e.g. recorder_host.py:23's 4-key ready shape, :4-5's two-model rationale) — rewrite to
# the single-model story (small.en both slots; tiny.en on CPU; 3-key ready payload). The grep gate (a)
# includes docstrings.

# GOTCHA #10 — FULL PATHS + INNER TIMEOUTS (AGENTS.md): `timeout 600 .venv/bin/python -m pytest ...`.
# No ruff/mypy configured. Machine aliases python3→uv run.
```

## Implementation Blueprint

### Data models and structure

The single remaining "model" is the 3-key `dict[str, str]` (`{device, compute_type, model}`) flowing: `cuda_check.resolve` → `_resolve_device_config`/`_unprobed_device_config` → `cfg_to_kwargs` (fills `model` + `realtime_model_type`) / child's `_child_resolved_device` → ready payload → `_resolved_device_cache` → `status_snapshot["model"]` / `_log_resolved_device`. No config/schema changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — confirm S1 landed (cuda_check 3-key) + survey the red baseline
  - RUN:
      cd /home/dustin/projects/voice-typing
      grep -q '"model": "small.en"' voice_typing/cuda_check.py && echo "S1 landed — proceed" || echo "STOP: S1 not landed"
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -2   # expect RED (AttributeError @152)
  - If S1 has NOT landed: STOP and report (collapsing against a 4-key resolver creates a second transient).

Task 1: REWRITE tests/test_daemon.py — the single-path family FIRST (TDD)
  - REWRITE the cfg_to_kwargs tests (@138/165/185/216 region) into ONE (+variants):
        def test_cfg_to_kwargs_single_model_fills_both_slots():
            cfg = VoiceTypingConfig()
            kw = daemon.cfg_to_kwargs(cfg, resolved={"device": "cuda", "compute_type": "float16", "model": "small.en"})
            assert kw["model"] == "small.en" and kw["realtime_model_type"] == "small.en"
            assert kw["use_main_model_for_realtime"] is True
            assert kw["post_speech_silence_duration"] == cfg.asr.lite_post_speech_silence_duration
            assert kw["device"] == "cuda" and kw["compute_type"] == "float16"
            assert kw["language"] == cfg.asr.language

        def test_cfg_to_kwargs_cpu_resolved_tiny_en_both_slots():
            kw = daemon.cfg_to_kwargs(VoiceTypingConfig(), resolved=dict(daemon.cuda_check.CPU_FALLBACK))
            assert kw["model"] == "tiny.en" and kw["realtime_model_type"] == "tiny.en"
            assert kw["device"] == "cpu" and kw["compute_type"] == "int8"
  - DELETE the mode/toggle family (@2964-3070, @3865-4060 — the map §6 list: mode_switch_*, toggle_lite_*,
    toggle_while_armed_in_lite_*, failed_cross_mode_*, dispatch_*_cross_mode_*, toggle_lite_docstring_*,
    start_lite_*, same_mode_arm_is_instant) and REPLACE with single-path equivalents:
        def test_start_arms_single_construction_and_sets_lite_mode():
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start()
            assert d.is_listening() and len(spawns) == 1 and d._mode is None-or-absent  # no _mode attr
            assert d._feedback… / d.status_snapshot()["mode"] == "lite"
        def test_toggle_is_involution_single_mode():   # on→off→on, no reload on same-mode re-arm
        def test_status_snapshot_has_single_model_key():  # 13 keys; "model" present; no final_model/realtime_model
        def test_start_after_idle_unload_reloads():    # rename of the lite variant; single path
        def test_dispatch_lite_commands_now_unknown(): # {"cmd":"toggle-lite"} → ok:False "unknown command"
  - FIX the helpers: `_cuda_resolve` stub (@80-100) returns 3-key dicts; drop `mode=` forcing from any
    surviving _fake_host_factory call; `_construct/build_recorder` signature asserts (@2824-2835) drop "lite".
  - KEEP: S1's re-pinned CPU sites (@2747/2769/2816 — end-state expectations, go green with the source edit).

Task 2: EDIT voice_typing/daemon.py — the single-path source (the core)
  - cfg_to_kwargs (158-215): drop the `lite` param + the pre-kwargs block (184-193) + the overrides block
    (205-214). New body (verbatim shape):
        if resolved is None:
            resolved = _resolve_device_config(cfg)
        kwargs: dict[str, Any] = {
            # Rev 2 single model (§4.2ter/§4.2quater): ONE model fills BOTH the final and realtime
            # slots (use_main_model_for_realtime=True skips the separate realtime engine — verified
            # against RealtimeSTT v1.0.2). The CPU substitute (tiny.en) comes from cuda_check's
            # CPU_FALLBACK wholesale override — no device discrimination here.
            "model": resolved["model"],
            "realtime_model_type": resolved["model"],
            "use_main_model_for_realtime": True,
            "language": cfg.asr.language,
            "device": resolved["device"],
            "compute_type": resolved["compute_type"],
            "realtime_processing_pause": cfg.asr.realtime_processing_pause,
            "post_speech_silence_duration": cfg.asr.lite_post_speech_silence_duration,
        }
        kwargs.update(_FIXED_KWARGS)
        return kwargs
    (use_main_model_for_realtime in the literal is safe — Task 3 removes it from _FIXED_KWARGS.)
  - _resolve_device_config (141-155): defaults → {"device": cfg.asr.device, "compute_type": derived, "model": cfg.asr.lite_model}.
  - _FIXED_KWARGS (100-114): DELETE the "use_main_model_for_realtime": False entry (+ its comment).
  - build_recorder/_construct (285-345): drop the `lite:` param; the single cfg_to_kwargs(cfg) call.
  - _mode decl (656) DELETE; _load_recorder alias (700-708) DELETE (check callers first — Gotcha #8).
  - _load_host (710-805): signature `def _load_host(self) -> bool:`; the fast path becomes
    `if self._models_loaded and self._host is not None and self._host.is_alive: return True` (DELETE the
    mode comparison + switch_mode flag); DELETE the reload branch (748-754); the real spawn (762-767)
    drops `mode=mode`; the fake path (768-772) drops it too; publish drops `self._mode = mode` (778).
  - start() (1430-1439): `self._load_host()` (no arg). start_lite (1441-1451): DELETE.
  - toggle() (1458-1516): collapse to `with self._lock: listening = self._listening.is_set()` →
    `if listening: self._request_stop() else: if not self._load_host(): return; with self._lock: self._arm()`.
    toggle_lite: DELETE. (Keep the lock discipline: read under _lock, _load_host OUTSIDE, _arm under.)
  - _arm (1039): `self._feedback.set_mode("lite")  # Rev 2 single-mode constant (schema stable, §4.6)`.
  - status_snapshot (1613-1646): `"mode": "lite",` (constant literal); replace the final_model +
    realtime_model lines with `"model": dev.get("model", "unknown"),`.
  - _unprobed_device_config (1669-1684): 3-key {"device","compute_type","model": cfg.asr.lite_model}.
  - _log_resolved_device (957-975): log "device=%s compute_type=%s model=%s" with resolved["model"].
  - dispatch (1989-2013): DELETE the `start-lite` and `toggle-lite` arms (unknown-cmd reply covers them).
  - Module docstring + any two-mode comments: rewrite to the single-model story (Mode A; Gotcha #9).

Task 3: EDIT voice_typing/recorder_host.py — modeless host
  - __init__ (103-125): drop `mode: str = "normal"` param + `self._mode = mode`.
  - `mode` property (168-170): DELETE. `device` property docstring (164): 3-key shape.
  - Spawn args (195): drop `self._mode` from the args tuple. _worker_main signature (427): drop `mode`.
  - Child (456-478): DELETE `lite = mode == "lite"` + the mode comment; `build_recorder(...)` no lite kwarg
    (both the primary + force_cpu paths).
  - _child_resolved_device (681-714): 3-key — {device, compute_type, model}; the CPU path yields
    model="tiny.en" (mirroring cuda_check's CPU_FALLBACK — keep whatever force_cpu mechanism exists,
    collapsed to the single model).
  - Module docstring (18-52, esp. :23's ready shape): `("ready", {device,compute_type,model})` + the
    single-model rationale.

Task 4: EDIT tests/test_control_socket.py + tests/test_recorder_host.py
  - test_control_socket: DELETE test_dispatch_lite_commands_call_daemon (@131); KEEP @143
    (status-carries-mode — mode constant still flows); verify the _StubDaemon/status key assertions
    match the 13-key snapshot (drop final_model/realtime_model if pinned).
  - test_recorder_host: drop `mode` from RecorderHost constructions + spawn-args asserts; the lite-flag
    tests collapse to the single construction (no mode anywhere in args).

Task 5: VALIDATE — the Validation Loop below. No git commit unless directed. If asked:
  "P1.M1.T2.S2: collapse daemon+recorder_host to the single-mode path (small.en both slots; mode='lite'
  constant; delete start_lite/toggle_lite/lite-dispatch/mode-switch) — turns T1.S1+S1's red window green".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the single kwargs literal (the whole construction contract). ONE model fills both slots;
# the CPU substitute arrives via cuda_check's wholesale CPU_FALLBACK override — never discriminated here:
    "model": resolved["model"],
    "realtime_model_type": resolved["model"],
    "use_main_model_for_realtime": True,          # verified: skips the separate realtime engine init
    "post_speech_silence_duration": cfg.asr.lite_post_speech_silence_duration,   # §4.2quater: 0.8

# PATTERN 2 — modeless _load_host fast path (the switch branch dies entirely):
    if self._models_loaded and self._host is not None and self._host.is_alive:
        return True          # resident + alive → instant (there is only ONE mode)

# PATTERN 3 — mode as a CONSTANT on the surfaces (NOT deleted): status_snapshot["mode"] == "lite";
# _arm → feedback.set_mode("lite"). state.json keeps the §4.6 schema; ctl.py:69/90 renders untouched.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S3 (ctl command surface) / S4 (prefetch/binds/ACCEPTANCE):
  - After this task, socket toggle-lite/start-lite are unknown commands; ctl.py STILL lists them (dead
    entries) until S3 drops _COMMANDS/argparse/loading-hint. hypr-binds.conf:52's toggle-lite bind is
    S4's. prefetch's distil-large-v3 CORE_REPOS entry is S4's. NOT yours.
DOWNSTREAM — P1.M2.T5/T6/T7 (streaming engine):
  - Builds on the single path: _on_partial (daemon.py:1094) is the streaming seam; the cancel hook goes
    in _dispatch alongside stop; the child's dynamic-prompt work threads through the modeless
    _worker_main. The 3-key resolved dict is the stable substrate contract.
DOWNSTREAM — P1.M3.T9.S1 (heavy-test adjustments):
  - test_feed_audio.py (653/679) + test_idle_and_gpu.sh T7 (535-578 mode-switch roundtrip) are adjusted
    THERE. This task leaves them untouched (and does not run them).
SIBLING — S1 (cuda_check): must land FIRST (Task 0 gate). Its re-pinned test_daemon sites go green here.
NO CHANGES: feedback.py (set_mode stays), config.py/config.toml (T1.S1 settled), cuda_check.py (S1's),
ctl.py (S3's), pyproject/uv.lock (T1.S2's).
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic fast suite only. Run from `/home/dustin/projects/voice-typing`.

### Level 1: The collapse is complete (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L1a: zero stale refs in both files (docstrings included) ---"
for f in voice_typing/daemon.py voice_typing/recorder_host.py; do
  n=$(grep -c 'final_model\|realtime_model\|_mode\b\|start_lite\|toggle_lite\|start-lite\|toggle-lite' "$f")
  echo "$f: $n"; [ "$n" -eq 0 ] || echo "  ^ L1a FAIL (finish the sweep)"
done
echo "--- L1b: mode constant + single model key ---"
grep -q '"mode": "lite"' voice_typing/daemon.py && grep -q '"model": dev.get' voice_typing/daemon.py && echo "L1b PASS" || echo "L1b FAIL"
echo "--- L1c: both parse ---"
timeout 60 .venv/bin/python -c "import ast; ast.parse(open('voice_typing/daemon.py').read()); ast.parse(open('voice_typing/recorder_host.py').read()); print('L1c PASS')"
# Expected: 0/0 stale; constant mode + dev.get model; both parse. (Note: '_mode\b' also matches docstring prose — sweep it.)
```

### Level 2: The single-path contract (focused tests)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or single or toggle or status_snapshot or idle_unload or dispatch" 2>&1 | tail -3
timeout 600 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_recorder_host.py -q 2>&1 | tail -3
# Expected: all pass — single-model kwargs (small.en/tiny.en both slots), modeless toggle involution,
# status mode='lite' + 13 keys, lite dispatch unknown, host spawns with no mode in args.
# If a kwargs test fails on use_main_model_for_realtime: the _FIXED_KWARGS entry wasn't deleted (it
# overrides the literal via kwargs.update AFTER the dict — order matters; the literal must WIN or the
# fixed entry must be gone).
```

### Level 3: Full fast suite green (the transient closes)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh 2>&1 | tail -3
# Expected: 0 failures — including S1's re-pinned CPU sites (tiny.en both slots) and test_cuda_check.
# Remaining red means a missed consumer of the 4-key shape or a missed _mode reader — grep L1a again.
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/daemon.py|voice_typing/recorder_host.py|tests/test_daemon.py|tests/test_control_socket.py|tests/test_recorder_host.py' \
  && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only the 5 deliverables"
git diff --quiet voice_typing/ctl.py voice_typing/prefetch.py voice_typing/feedback.py voice_typing/config.py voice_typing/cuda_check.py config.toml hypr-binds.conf tests/ACCEPTANCE.md pyproject.toml \
  && echo "L4 PASS: sibling files untouched" || echo "L4 FAIL: a sibling file was modified"
git diff --exit-code -- PRD.md plan/007_cfc245548aec/tasks.json plan/007_cfc245548aec/prd_snapshot.md .gitignore \
  && echo "L4 PASS: read-only files unchanged" || echo "L4 NOTE: tasks.json orchestrator bookkeeping (M) is not this subtask"
# Expected: only the 5 files; siblings untouched; read-only unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: zero stale refs in both files (incl. docstrings); `"mode": "lite"` + `dev.get("model",...)`; both parse.
- [ ] L2: single-path contract tests pass (kwargs both-slots, toggle involution, status 13-key, dispatch unknown-lite).
- [ ] L3: full fast suite 0 failures (S1's red-transient sites green; test_cuda_check green).
- [ ] L4: diff ⊆ the 5 deliverables; siblings/read-only untouched.

### Feature Validation
- [ ] `toggle`/`start` arm the single small.en recorder (`use_main_model_for_realtime=True`, `lite_post` duration); `stop` disarms.
- [ ] CPU path: tiny.en fills both slots via cuda_check's wholesale fallback (no daemon-side discrimination).
- [ ] `status_snapshot` → `{ok, ..., mode:"lite", model:"small.en"|"tiny.en", ...}`; state.json mode 'lite' after arm.
- [ ] Socket `toggle-lite`/`start-lite` → `{"ok":false,"error":"unknown command: ..."}`.
- [ ] Modeless `_load_host` (no switch branch; fakes spawned without `mode=`).

### Code Quality Validation
- [ ] Lock discipline preserved (toggle reads under `_lock`; `_load_host` outside; `_arm` under).
- [ ] Module docstrings tell the single-model story (Mode A); no dead `post_speech_silence_duration` removal (schema settled).
- [ ] Tests rewritten FIRST (TDD); fakes updated (`_cuda_resolve` 3-key; no forced modes).

### Scope Boundary Validation
- [ ] No ctl.py/prefetch/binds/ACCEPTANCE (S3/S4); no feedback/config/cuda_check edits; no heavy-test edits (P1.M3.T9.S1).
- [ ] S1 gate honored (cuda_check 3-key landed before starting).

### Documentation & Deployment
- [ ] Mode A: both module docstrings rewritten; commit message names the transient closure.

---

## Anti-Patterns to Avoid

- ❌ Don't start before S1 lands — cfg_to_kwargs reads `resolved["model"]` (Task 0 gate; a 4-key resolver KeyErrors).
- ❌ Don't write the source first — rewrite the tests first (the contract's implicit TDD; pins the end state).
- ❌ Don't leave the `use_main_model_for_realtime: False` entry in `_FIXED_KWARGS` — `kwargs.update(_FIXED_KWARGS)` runs AFTER the literal and would override `True` back to `False` (the silent killer; L2 catches it).
- ❌ Don't delete `mode` from the status/state surfaces — it stays as the CONSTANT `"lite"` (§4.6 schema stability; ctl rendering; test_feedback/test_voicectl stay green).
- ❌ Don't keep any daemon-side tiny.en discrimination — the CPU mapping lives ONLY in cuda_check's CPU_FALLBACK.
- ❌ Don't touch ctl.py/prefetch/hypr-binds/ACCEPTANCE (S3/S4), feedback.py/config.py (settled), or the heavy GPU tests (P1.M3.T9.S1).
- ❌ Don't pass `mode=` to host factories in surviving tests — `_load_host` no longer sends it.
- ❌ Don't remove `cfg.asr.post_speech_silence_duration` from config — unused now, but schema churn is T1.S1's settled ground.
- ❌ Don't run test_feed_audio.py / the shell tests (AGENTS.md heavy tests; they're P1.M3.T9.S1's to adjust).
- ❌ Don't modify PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**9/10** for one-pass implementation success. The collapse is large but fully mapped: every edit site is line-cited with its verified current text and end state (research note tables + the map's §1/§4/§6/§7 + the cfg_to_kwargs region read verbatim); the test family is enumerated test-by-test with line numbers and its rewrite disposition; both input contracts are pinned (T1.S1 landed — `lite_model`/`lite_post` exist; S1's 3-key shape specified verbatim with a hard Task-0 gate); and the end-state kwargs literal is given word-for-word, including the one silent trap (`_FIXED_KWARGS` overriding `use_main_model_for_realtime` back to `False` — called out in L2). The transient philosophy is already proven in-plan (T1.S1 and S1 both left intentional red that this task closes), so the entry-state red is expected, not ambiguous. The −1 is the usual parallel-execution residual: S1 must land first (gated), and daemon.py/recorder_host.py line numbers shift as it does — mitigated by symbol navigation + the L1a zero-stale-refs sweep that proves completion independent of line numbers. The heavy GPU tests are explicitly out of scope (P1.M3.T9.S1), so every gate here is hermetic and fast.
