# PRP — P1.M1.T1.S1: Fix CPU-lite-fallback model (small.en → tiny.en) in cfg_to_kwargs + recorder_host

## Goal

**Feature Goal**: Make lite mode's model selection **device-aware** so that on the CPU path lite mode loads `tiny.en` (the CPU lite substitute) for BOTH the final and realtime model fields, instead of unconditionally loading `cfg.asr.lite_model` (`small.en`). This mirrors how normal CPU-fallback maps `small.en → tiny.en` (realtime) and `distil-large-v3 → small.en` (final), and satisfies delta PRD §3.2 BUG-A. On CUDA, lite mode is unchanged (`small.en`).

**Deliverable**: Two surgical code edits + two docstring updates, across exactly two files:
1. `voice_typing/daemon.py` — `cfg_to_kwargs` `if lite:` branch (lines 181-184): pick the lite model by `resolved["device"]`.
2. `voice_typing/recorder_host.py` — `_child_resolved_device` `if lite:` branch (lines 686-688): pick the lite model by `d["device"]`.
Plus the `lite` docstring paragraph in each function (Mode A — rides with the work).

**Success Definition**: (a) `cfg_to_kwargs(cfg, resolved=dict(CPU_FALLBACK), lite=True)` → `model == realtime_model_type == "tiny.en"`, `device == "cpu"`, `compute_type == "int8"`, `use_main_model_for_realtime is True`; (b) `cfg_to_kwargs(cfg, lite=True)` on CUDA → both `== "small.en"` (unchanged); (c) `_child_resolved_device(cfg, force_cpu=True, lite=True)` → `final_model == realtime_model == "tiny.en"`; (d) the existing `test_cfg_to_kwargs_lite_mode_uses_one_model` (CUDA path) and `test_cfg_to_kwargs_cpu_fallback` (normal CPU) still pass; (e) only `daemon.py` and `recorder_host.py` change.

## User Persona

**Target User**: A user running lite mode on a CPU-only host (or whose GPU failed construction and tripped the `force_cpu` retry). Without this fix, lite mode on CPU tries to load `small.en` for both fields — inconsistent with the normal-mode CPU fallback (which uses `tiny.en` for the realtime field) and heavier than the intended CPU lite substitute.

**Use Case**: `voicectl toggle-lite` on a machine where CUDA is unavailable → the recorder-host child builds the lite recorder with `force_cpu=True`; the models loaded must be `tiny.en` (fast, CPU-appropriate), not `small.en`.

**Pain Points Addressed**: Correctness/consistency of the CPU degraded path; `status` accuracy (the `_child_resolved_device` fix makes the reported models match what actually loaded).

## Why

- **Spec mandate (delta §3.2 BUG-A):** mode==lite + force_cpu → `model = realtime_model_type = "tiny.en"`. The current code ignores device in the lite branch and always uses `cfg.asr.lite_model` (`small.en`).
- **Mirrors normal CPU-fallback:** `cuda_check.CPU_FALLBACK = {device:cpu, compute_type:int8, final_model:small.en, realtime_model:tiny.en}`. Normal mode on CPU already downgrades the realtime model `small.en → tiny.en`. Lite mode must apply the SAME `small.en → tiny.en` downgrade (lite's single model plays the realtime role, so it gets the realtime CPU substitute).
- **Status accuracy:** `_child_resolved_device` feeds `status_snapshot()`'s model fields. Without the fix it would report `small.en` on a CPU-lite child that actually loaded `tiny.en` (once the construction fix lands) — or, worse, report a model that doesn't match a `force_cpu` build. The two functions must agree.
- **Pure/unit-testable, no mocks needed:** both functions are deterministic given a `resolved`/`force_cpu` input; `cfg_to_kwargs(resolved=dict(CPU_FALLBACK))` skips the cuda probe entirely, and `_child_resolved_device(force_cpu=True)` short-circuits to `dict(CPU_FALLBACK)`. So the fix is verifiable without CUDA.

## What

Replace the unconditional `cfg.asr.lite_model` assignment in each lite branch with a device-aware pick: `"tiny.en" if <dict>["device"] == "cpu" else cfg.asr.lite_model`. Apply to BOTH `cfg_to_kwargs` (daemon.py) and `_child_resolved_device` (recorder_host.py). Update each function's `lite` docstring to note the CPU `tiny.en` downgrade. No other behavior change (`use_main_model_for_realtime=True` stays; the kwargs structure is unchanged).

### Success Criteria

- [ ] `cfg_to_kwargs` lite branch selects `tiny.en` when `resolved["device"] == "cpu"`, else `cfg.asr.lite_model`.
- [ ] `_child_resolved_device` lite branch selects `tiny.en` when `d["device"] == "cpu"`, else `cfg.asr.lite_model`.
- [ ] `use_main_model_for_realtime=True` override (daemon.py ~line 198) untouched.
- [ ] Both `lite` docstrings note the CPU `tiny.en` downgrade.
- [ ] Existing tests `test_cfg_to_kwargs_lite_mode_uses_one_model` and `test_cfg_to_kwargs_cpu_fallback` still pass.
- [ ] Only `voice_typing/daemon.py` and `voice_typing/recorder_host.py` modified; no tests added/edited (S2 owns the new kwargs×mode×force_cpu tests).

## All Needed Context

### Context Completeness Check

_Pass._ The bug is verified present in the actual current code (re-verified per the contract's warning — the working tree has NOT yet fixed it). The exact current lines, the exact edits, the `CPU_FALLBACK` definition, the config field, the existing tests that must stay green, and the deterministic no-CUDA verification commands are all below.

### Verified Current State (re-verified — bug IS present)

**`voice_typing/daemon.py` `cfg_to_kwargs` (lines 158-200)** — the buggy branch (181-184):
```python
    if lite:
        resolved = dict(resolved)
        resolved["final_model"] = cfg.asr.lite_model      # ← UNCONDITIONAL (the bug)
        resolved["realtime_model"] = cfg.asr.lite_model   # ← UNCONDITIONAL (the bug)
    kwargs: dict[str, Any] = {
        "model": resolved["final_model"],
        "realtime_model_type": resolved["realtime_model"],
        ...
        "device": resolved["device"],
        "compute_type": resolved["compute_type"],
        ...
    }
    kwargs.update(_FIXED_KWARGS)
    if lite:
        kwargs["use_main_model_for_realtime"] = True   # ← stays (do NOT touch)
    return kwargs
```

**`voice_typing/recorder_host.py` `_child_resolved_device` (lines 661-689)** — the buggy branch (686-688):
```python
    if force_cpu:
        d = dict(cuda_check.CPU_FALLBACK)
    else:
        try:
            d = cuda_check.resolve_device_and_models({...})
        except Exception:
            d = dict(cuda_check.CPU_FALLBACK)
    if lite:
        d["final_model"] = cfg.asr.lite_model       # ← UNCONDITIONAL (the bug)
        d["realtime_model"] = cfg.asr.lite_model    # ← UNCONDITIONAL (the bug)
    return d
```

**`voice_typing/cuda_check.py` (lines 53-58):**
```python
CPU_FALLBACK: dict[str, str] = {
    "device": "cpu",
    "compute_type": "int8",
    "final_model": "small.en",
    "realtime_model": "tiny.en",
}
```

**Config field exists:** `voice_typing/config.py:54` → `lite_model: str = "small.en"` (PRD §4.2ter), validated in `__post_init__` (config.py:93).

### Documentation & References

```yaml
# AUTHORITATIVE JUSTIFICATION — the one-model fact + the CPU-lite BUG-A fix
- docfile: plan/004_607e9cca32b7/architecture/realtimestt_lite_mode_verification.md
  why: Confirms (a) use_main_model_for_realtime=True loads exactly ONE model (skips the realtime
       engine init — verified against installed v1.0.2 core/initialization.py ~453-455); (b) the
       "CPU-fallback for lite (delta §3.2 — the BUG-A fix)" section: on force_cpu, lite must use
       tiny.en for BOTH model fields, mirroring how normal CPU-fallback maps small.en→tiny.en.
  critical: "CPU lite substitute = tiny.en for BOTH fields. cuda_check.CPU_FALLBACK already encodes
            realtime_model:tiny.en — lite's single model plays the realtime role, so it inherits that."

- docfile: plan/004_607e9cca32b7/architecture/system_context.md
  why: §3.2 BUG-A documents the defect; lines 70-82 map every lite touchpoint (config.py:54
       lite_model; daemon.py:159 cfg_to_kwargs lite branch; recorder_host.py:661-688
       _child_resolved_device lite override). Confirms the two fix sites are the ONLY construction-
       layer places that pick the lite model.
  critical: "The construction-layer model pick happens in EXACTLY two places: cfg_to_kwargs (what the
            child builds) and _child_resolved_device (what status reports). Both must agree."

# THE FIX SITES
- file: voice_typing/daemon.py
  why: cfg_to_kwargs (158) builds the recorder kwargs; the lite branch (181-184) picks the model.
        _construct (~298) passes resolved=dict(CPU_FALLBACK) on the force_cpu path, so on that path
        resolved["device"]=="cpu" is True and the fix selects tiny.en.
  pattern: "Discriminate on resolved['device'] == 'cpu', NOT on a force_cpu flag (cfg_to_kwargs has
            no force_cpu param). device is the resolved truth and covers force_cpu + probe-failure +
            cuda_check-resolving-to-CPU."
  gotcha: "Keep the second `if lite:` block (~198) that sets use_main_model_for_realtime=True — do
           NOT touch it. Only the FIRST if-lite (model pick) changes."

- file: voice_typing/recorder_host.py
  why: _child_resolved_device (661) re-derives the device/models the child loaded, for status.
        force_cpu=True -> d=dict(CPU_FALLBACK) (device=cpu); probe-failure -> same; probe success on
        a no-GPU box -> resolve returns CPU_FALLBACK (device=cpu). So d['device']=='cpu' covers all
        CPU cases here too.
  pattern: "Same device-aware pick as cfg_to_kwargs. Discriminate on d['device']=='cpu'."
  gotcha: "Do NOT change the force_cpu/probe logic (672-685) — only the trailing if-lite (686-688)."

# THE CPU FALLBACK DEFINITION (the source of tiny.en)
- file: voice_typing/cuda_check.py
  why: CPU_FALLBACK (53) = {device:cpu, compute_type:int8, final_model:small.en, realtime_model:tiny.en}.
        tiny.en is the canonical CPU realtime substitute; lite inherits it.
  critical: "Do NOT edit cuda_check.py — CPU_FALLBACK is correct as-is. The bug is that the lite
            branch ignores it for the model fields."

# EXISTING TESTS THAT MUST STAY GREEN (compatibility) + S2's scope
- file: tests/test_daemon.py
  why: test_cfg_to_kwargs_lite_mode_uses_one_model (138) tests ONLY the CUDA lite path
       (_cuda_resolve(CUDA_DEFAULTS) -> device cuda -> asserts small.en). The fix leaves CUDA lite
       unchanged (small.en), so this stays GREEN. test_cfg_to_kwargs_cpu_fallback (162) tests NORMAL
       mode CPU (not lite) -> also unaffected. The CPU-LITE case (tiny.en) is what S2 adds.
  pattern: "_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS|CPU_FALLBACK) forces the path;
            cfg_to_kwargs(cfg, lite=True) reads the result."
  critical: "S1 does NOT add/edit tests. If any existing test asserted small.en for CPU-lite (none
            found), it would be S2's reconciliation — but grep shows no such test today."

# PRD CONTEXT
- docfile: plan/004_607e9cca32b7/prd_snapshot.md
  why: §4.2ter (lite mode: lite_model for both fields; CPU auto-downgrade via cuda_check, approved
        CPU lite substitute = tiny.en) and §4.4 (CPU fallback = tiny.en realtime) are the spec basis.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py            # cfg_to_kwargs @158; lite branch @181-184  ← EDIT (+ docstring lite para @174-179)
│   ├── recorder_host.py     # _child_resolved_device @661; lite branch @686-688  ← EDIT (+ docstring @667-669)
│   ├── cuda_check.py        # CPU_FALLBACK @53 (tiny.en)  ← READ ONLY (correct as-is)
│   └── config.py            # AsrConfig.lite_model @54 ("small.en")  ← READ ONLY
└── tests/
    └── test_daemon.py       # test_cfg_to_kwargs_lite_mode_uses_one_model @138 (CUDA; stays green); test_cfg_to_kwargs_cpu_fallback @162 (normal CPU; stays green)  ← NOT edited in S1
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py         # MODIFY: device-aware lite model pick + lite docstring note
voice_typing/recorder_host.py  # MODIFY: device-aware lite model pick + lite docstring note
# NO other files. No tests (S2), no config, no cuda_check.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DISCRIMINATE ON device, NOT force_cpu. cfg_to_kwargs has NO force_cpu parameter; its
# only signal is resolved["device"]. In _child_resolved_device, force_cpu is ONE of three ways to
# land on CPU (force_cpu=True, probe-failure except->CPU_FALLBACK, probe-returns-CPU). d["device"]
# is the resolved truth in ALL three. Checking force_cpu in _child_resolved_device would MISS the
# probe-failure and probe->cpu cases. Use `<dict>["device"] == "cpu"` in BOTH functions.

# CRITICAL #2 — TWO if-lite BLOCKS in cfg_to_kwargs; only the FIRST changes. The first (line 181)
# picks the model; the second (line ~198) sets kwargs["use_main_model_for_realtime"]=True. Leave the
# second EXACTLY as-is (the contract: "Keep use_main_model_for_realtime=True (unchanged)").

# CRITICAL #3 — BOTH FUNCTIONS MUST AGREE. cfg_to_kwargs decides what the child BUILDS;
# _child_resolved_device decides what status REPORTS. If you fix only one, status lies about the
# loaded model (or the build ignores the CPU substitute). Edit both in the same change.

# CRITICAL #4 — DO NOT EDIT cuda_check.CPU_FALLBACK. It is correct (realtime_model:tiny.en). The bug
# is purely that the lite branches ignore device when picking the model. CPU_FALLBACK already encodes
# the tiny.en substitute for the realtime field; lite just needs to USE it for both fields.

# GOTCHA #5 — RE-VERIFY BEFORE EDITING. The contract warns the working tree is a moving target. This
# PRP's author re-verified on 2026-07-14: the bug IS still present at daemon.py:181-184 and
# recorder_host.py:686-688. If a prior change already fixed it, STOP (the task is done) — re-run the
# L1 gate; if the device-aware expression is already there, no edit is needed.

# GOTCHA #6 — NO NEW TESTS IN S1. The CPU-lite regression test is S2 (P1.M1.T1.S2: "Add kwargs×mode×
# force_cpu unit tests"). S1's gate is: existing CUDA-lite + normal-CPU tests stay green, plus a
# one-off no-CUDA functional check (L3, not committed).

# GOTCHA #7 — PURE FUNCTIONS, NO MOCKS. cfg_to_kwargs(resolved=dict(CPU_FALLBACK), lite=True) skips
# the cuda probe entirely (resolved is given). _child_resolved_device(force_cpu=True, lite=True)
# short-circuits to dict(CPU_FALLBACK) (no probe). So both are unit-checkable WITHOUT CUDA/mocks.

# GOTCHA #8 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# pytest/one-off gates. No ruff/mypy in this project.
```

## Implementation Blueprint

### Data models and structure

None added. The change picks a different string value for two existing dict fields based on an existing key. No schema/type/API change.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: RE-VERIFY the bug is still present (the contract mandates this).
  - RUN: grep -n 'cfg.asr.lite_model' voice_typing/daemon.py voice_typing/recorder_host.py
  - EXPECT: daemon.py shows the unconditional assignment at the lite branch (~183-184);
    recorder_host.py shows it at ~687-688. If the lines already read "tiny.en" if ...["device"] ==
    "cpu" else cfg.asr.lite_model, the fix is ALREADY LANDED — stop (re-run L1; task done).

Task 1: EDIT voice_typing/daemon.py — cfg_to_kwargs lite branch (device-aware model pick).
  - FIND (lines 181-184):
        if lite:
            resolved = dict(resolved)
            resolved["final_model"] = cfg.asr.lite_model
            resolved["realtime_model"] = cfg.asr.lite_model
  - REPLACE WITH:
        if lite:
            resolved = dict(resolved)
            # CPU lite substitute is tiny.en — mirrors how CPU_FALLBACK maps small.en→tiny.en (the
            # realtime model) in normal mode. On CUDA keep cfg.asr.lite_model. Discriminate on
            # resolved["device"] (NOT a force_cpu flag — cfg_to_kwargs has none; device is the
            # resolved truth and also covers probe-failure / cuda_check→CPU). (§4.2ter; delta §3.2 BUG-A)
            lite_model = "tiny.en" if resolved["device"] == "cpu" else cfg.asr.lite_model
            resolved["final_model"] = lite_model
            resolved["realtime_model"] = lite_model
  - DO NOT touch the second `if lite:` block (~198, use_main_model_for_realtime=True).

Task 2: EDIT voice_typing/daemon.py — cfg_to_kwargs `lite` docstring paragraph (lines ~174-179).
  - FIND the paragraph starting "`lite` (PRD §4.2ter, default False): lite mode loads ONLY".
  - APPEND/REPLACE so it states: the lite model is cfg.asr.lite_model ("small.en") on CUDA, but
    downgrades to the CPU lite substitute "tiny.en" when resolved["device"] == "cpu" (mirrors normal
    CPU-fallback small.en→tiny.en; delta §3.2 BUG-A). Keep the use_main_model_for_realtime / one-model
    / large-never-constructed sentences.

Task 3: EDIT voice_typing/recorder_host.py — _child_resolved_device lite branch (lines 686-688).
  - FIND:
        if lite:
            d["final_model"] = cfg.asr.lite_model
            d["realtime_model"] = cfg.asr.lite_model
        return d
  - REPLACE WITH:
        if lite:
            # CPU lite substitute is tiny.en (mirrors CPU_FALLBACK small.en→tiny.en); on CUDA keep
            # cfg.asr.lite_model so status matches what the child actually loaded. Discriminate on
            # d["device"] (the resolved truth — covers force_cpu, probe-failure, probe→cpu).
            # (§4.2ter; delta §3.2 BUG-A)
            lite_model = "tiny.en" if d["device"] == "cpu" else cfg.asr.lite_model
            d["final_model"] = lite_model
            d["realtime_model"] = lite_model
        return d

Task 4: EDIT voice_typing/recorder_host.py — _child_resolved_device docstring (lines ~667-669).
  - FIND: "§4.2ter) the reported models are overridden to lite_model for both fields (what actually loaded)."
  - REPLACE so it states: the reported models are the lite model for both fields (what actually
    loaded) — cfg.asr.lite_model ("small.en") on CUDA, or the CPU lite substitute "tiny.en" when
    d["device"] == "cpu" (delta §3.2 BUG-A).

Task 5: VALIDATE (run the gates below). No git commit unless the orchestrator directs it. If asked,
  message: "P1.M1.T1.S1: fix CPU-lite-fallback model (small.en→tiny.en) in cfg_to_kwargs + recorder_host".
```

### Implementation Patterns & Key Details

```python
# The entire change is one expression in each of two functions:
#     lite_model = "tiny.en" if <dict>["device"] == "cpu" else cfg.asr.lite_model
# applied to BOTH the final_model and realtime_model fields. Why this is correct:
#
#  * cuda_check.CPU_FALLBACK already says realtime_model="tiny.en" — lite's single model plays the
#    realtime role, so it inherits the realtime CPU substitute. (normal mode: small.en→tiny.en on CPU;
#    lite mode: small.en→tiny.en on CPU for the one model. Symmetric.)
#  * resolved["device"] (cfg_to_kwargs) / d["device"] (_child_resolved_device) is the resolved truth:
#    it is "cpu" for force_cpu, probe-failure, AND cuda_check-resolving-to-CPU. Using it (not a
#    force_cpu flag) covers every CPU path uniformly. cfg_to_kwargs has no force_cpu param anyway.
#  * CUDA lite is unchanged: device!="cpu" -> cfg.asr.lite_model ("small.en"). So the existing
#    test_cfg_to_kwargs_lite_mode_uses_one_model (CUDA) stays green.
#  * use_main_model_for_realtime=True is set in a SEPARATE if-lite block and is NOT touched.
#
# cfg_to_kwargs and _child_resolved_device MUST agree (build vs status). Edit both.
```

### Integration Points

```yaml
CONSUMERS:
  - cfg_to_kwargs is called by _construct (daemon.py ~299: resolved=dict(CPU_FALLBACK) when force_cpu,
    else None) and by tests. With the fix, a force_cpu lite build produces model=realtime_model_type=
    tiny.en — exactly what build_recorder passes to AudioToTextRecorder.
  - _child_resolved_device is called in the recorder-host child (recorder_host.py ~498) to seed the
    status device/models. With the fix, a force_cpu lite child REPORTS tiny.en (matches the build).
  - The real child's build_recorder (recorder_host.py ~476/486) calls cfg_to_kwargs(lite=mode=="lite")
    on BOTH the primary (CUDA) path and the force_cpu retry — both now pick tiny.en on CPU.

CONFIG:
  - AsrConfig.lite_model (config.py:54, default "small.en") is UNCHANGED. It remains the CUDA lite
    model; the CPU substitute "tiny.en" is a code-level constant (mirrors cuda_check.CPU_FALLBACK's
    hardcoded tiny.en), NOT a new config field. Do NOT add a config knob.

CUDA_CHECK:
  - CPU_FALLBACK (cuda_check.py:53) is UNCHANGED and correct. No edit there.

REGRESSION TESTS (sibling subtask — NOT S1):
  - S2 (P1.M1.T1.S2) adds the kwargs×mode×force_cpu matrix: lite+CPU→tiny.en, lite+CUDA→small.en,
    normal+CPU→small.en/tiny.en, normal+CUDA→distil-large-v3/small.en; plus reconciles broken test
    factory closures. S1's fix makes those tests pass once written; S1 adds no tests itself.
```

## Validation Loop

> Full paths for python (machine aliases python3->uv run). No ruff/mypy in this project — gates are:
> static structure + existing pytest + a no-CUDA functional check. The committed CPU-lite regression
> is S2's test (not added here); L3 is a one-off confirmation.

### Level 1: The device-aware pick is present in both functions (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- daemon.py cfg_to_kwargs lite branch is device-aware ---"
grep -n '"tiny.en" if resolved\["device"\] == "cpu" else cfg.asr.lite_model' voice_typing/daemon.py && echo "L1a PASS" || echo "L1a FAIL"
echo "--- recorder_host.py _child_resolved_device lite branch is device-aware ---"
grep -n '"tiny.en" if d\["device"\] == "cpu" else cfg.asr.lite_model' voice_typing/recorder_host.py && echo "L1b PASS" || echo "L1b FAIL"
echo "--- use_main_model_for_realtime=True override still present (untouched) ---"
grep -c 'kwargs\["use_main_model_for_realtime"\] = True' voice_typing/daemon.py | grep -q '^1$' && echo "L1c PASS" || echo "L1c CHECK"
echo "--- no remaining UNCONDITIONAL cfg.asr.lite_model assignment in a lite branch ---"
grep -n 'resolved\["final_model"\] = cfg.asr.lite_model\|d\["final_model"\] = cfg.asr.lite_model' voice_typing/daemon.py voice_typing/recorder_host.py && echo "L1d FAIL: unconditional assignment remains" || echo "L1d PASS"
# Expected: L1a/L1b PASS (one match each), L1c PASS (exactly one use_main override), L1d PASS (no unconditional = lite_model left).
```

### Level 2: Existing lite + CPU-fallback tests stay green

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v -k "lite_mode_uses_one_model or cpu_fallback" 2>&1 | tail -8
# Expected: 2 passed:
#   test_cfg_to_kwargs_lite_mode_uses_one_model  (CUDA lite -> small.en; unchanged by the fix)
#   test_cfg_to_kwargs_cpu_fallback              (normal CPU -> small.en/tiny.en; lite untouched)
.venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q 2>&1 | tail -6
# Expected: all pass. (Catches any _child_resolved_device caller that broke; grep found no dedicated
# test, so this is the safety net.)
```

### Level 3: No-CUDA functional confirmation (one-off; S2 commits the regression)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing import cuda_check, daemon
from voice_typing.config import VoiceTypingConfig
from voice_typing import recorder_host

cfg = VoiceTypingConfig()

# (a) lite + CPU -> tiny.en for BOTH fields, cpu/int8, single-model flag on
kw = daemon.cfg_to_kwargs(cfg, resolved=dict(cuda_check.CPU_FALLBACK), lite=True)
assert kw["model"] == "tiny.en", kw["model"]
assert kw["realtime_model_type"] == "tiny.en", kw["realtime_model_type"]
assert kw["device"] == "cpu" and kw["compute_type"] == "int8"
assert kw["use_main_model_for_realtime"] is True
print("L3a PASS: lite+CPU -> tiny.en (both), cpu/int8, use_main_model_for_realtime=True")

# (b) lite + CUDA -> small.en for BOTH (unchanged)
kw2 = daemon.cfg_to_kwargs(cfg, resolved=dict(cuda_check.CUDA_DEFAULTS), lite=True)
assert kw2["model"] == "small.en" and kw2["realtime_model_type"] == "small.en"
assert kw2["device"] == "cuda" and kw2["use_main_model_for_realtime"] is True
print("L3b PASS: lite+CUDA -> small.en (both), unchanged")

# (c) _child_resolved_device: force_cpu (CPU) + lite -> tiny.en; CUDA + lite -> small.en
d_cpu = recorder_host._child_resolved_device(cfg, force_cpu=True, lite=True)
assert d_cpu["final_model"] == "tiny.en" and d_cpu["realtime_model"] == "tiny.en", d_cpu
print("L3c PASS: _child_resolved_device(force_cpu,lite) -> tiny.en (matches the build)")
print("ALL L3 functional checks PASS")
PY
# Expected: L3a/L3b/L3c PASS. (cfg_to_kwargs(resolved=...) and _child_resolved_device(force_cpu=True)
# skip the cuda probe -> no CUDA needed. S2 will commit an equivalent as a regression test.)
```

### Level 4: Scope — only daemon.py + recorder_host.py changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY voice_typing/daemon.py + voice_typing/recorder_host.py ---"
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/(daemon|recorder_host)\.py' | grep -E '\.py$|systemd/|tests/|config|cuda_check' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: only daemon.py + recorder_host.py"
# Expected: "only daemon.py + recorder_host.py". cuda_check.py / config.py / tests must NOT appear.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1a/L1b: device-aware `"tiny.en" if <dict>["device"] == "cpu" else cfg.asr.lite_model` present in both functions.
- [ ] L1c: `use_main_model_for_realtime=True` override intact (exactly one).
- [ ] L1d: no remaining unconditional `= cfg.asr.lite_model` model assignment in a lite branch.
- [ ] L2: `test_cfg_to_kwargs_lite_mode_uses_one_model` + `test_cfg_to_kwargs_cpu_fallback` pass; full `test_daemon.py`/`test_recorder_host.py` green.
- [ ] L3: no-CUDA functional check — lite+CPU→tiny.en, lite+CUDA→small.en, `_child_resolved_device(force_cpu,lite)`→tiny.en.
- [ ] L4: only `voice_typing/daemon.py` + `voice_typing/recorder_host.py` changed.

### Feature Validation
- [ ] Lite mode on CPU loads `tiny.en` for both model fields (mirrors normal CPU-fallback `small.en→tiny.en`).
- [ ] Lite mode on CUDA unchanged (`small.en`).
- [ ] `status` (`_child_resolved_device`) reports the same model the child built (build/status agree).
- [ ] `use_main_model_for_realtime=True` preserved (one-model guarantee intact).

### Code Quality Validation
- [ ] Discriminator is `device == "cpu"` in both functions (not `force_cpu`).
- [ ] Both `lite` docstrings note the CPU `tiny.en` downgrade.
- [ ] `cuda_check.CPU_FALLBACK` and `AsrConfig.lite_model` untouched.

### Scope Boundary Validation
- [ ] No tests added/edited (S2 owns kwargs×mode×force_cpu + factory reconciliation).
- [ ] No `cuda_check.py` / `config.py` / `config.toml` / `ctl.py` / `feedback.py` changes.
- [ ] No new config knob (`tiny.en` is a code-level constant mirroring `CPU_FALLBACK`).

---

## Anti-Patterns to Avoid

- ❌ Don't discriminate on `force_cpu` — `cfg_to_kwargs` has no such param, and in `_child_resolved_device` it misses probe-failure/probe→CPU. Use `<dict>["device"] == "cpu"`.
- ❌ Don't fix only ONE of the two functions — `cfg_to_kwargs` (build) and `_child_resolved_device` (status) must agree, or status lies about the loaded model.
- ❌ Don't touch `use_main_model_for_realtime=True` (the second `if lite:` block) — the contract says keep it; it's the one-model guarantee.
- ❌ Don't edit `cuda_check.CPU_FALLBACK` or add a `tiny.en` config knob — `tiny.en` is the canonical CPU realtime substitute already encoded in `CPU_FALLBACK`; the bug is only that lite ignores device.
- ❌ Don't add/edit tests in S1 — the CPU-lite regression + factory reconciliation are S2 (P1.M1.T1.S2).
- ❌ Don't skip Task 0 (re-verify) — the contract warns the tree is a moving target; if the fix already landed, stop.
- ❌ Don't invoke ruff/mypy — not configured; gates are pytest + the no-CUDA functional check.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is one device-aware expression copied into two verified locations (daemon.py:181-184, recorder_host.py:686-688), with the `CPU_FALLBACK`/`lite_model` facts, the existing-green tests (CUDA-lite, normal-CPU), and a no-CUDA functional check all verified. The −0.5 is the standard "moving tree" caveat the contract itself raises (mitigated by Task 0 re-verify + L1d catching any leftover unconditional assignment): if a concurrent change already altered these lines, the agent must re-confirm rather than blindly apply.
