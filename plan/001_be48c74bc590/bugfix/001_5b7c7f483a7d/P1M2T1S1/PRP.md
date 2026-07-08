# PRP — P1.M2.T1.S1: Monkeypatch cuda_check.resolve_device_and_models in polluting tests

## Goal

**Feature Goal**: Fix bugfix **Issue 4** (test-isolation, order-dependent) at its **root cause** (the suggested-fix option (a)): make the 4 tests in `tests/test_daemon.py` that currently call the REAL `cuda_check.resolve_device_and_models()` monkeypatch it instead, so they no longer pollute `sys.modules` with `ctranslate2`/`torch`. This stops the cross-module pollution that makes `pytest tests/ --ignore=tests/test_feed_audio.py` fail `tests/test_voicectl.py::test_ctl_module_present_and_imports_pure` (which runs later, alphabetically) with `assert not ['torch', 'ctranslate2']`.

**Deliverable** (test-only; 4 edits to ONE file, no new files/imports/fixtures):
1. `tests/test_daemon.py` — add a `monkeypatch` parameter + a single `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` line at the top of the body in each of these 4 tests:
   - `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` (line ~98; signature `def ...(cfg):` → `def ...(cfg, monkeypatch):`)
   - `test_run_loop_not_listening_does_not_call_text` (line ~537; `def ...():` → `def ...(monkeypatch):`)
   - `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (line ~549; `def ...():` → `def ...(monkeypatch):`)
   - `test_run_sets_uptime_after_start` (line ~563; `def ...():` → `def ...(monkeypatch):`)

**Success Definition**:
- (a) All 4 tests now take a `monkeypatch` fixture and call `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` as their first body line, mirroring their already-hermetic siblings (`test_cfg_to_kwargs_cuda_path` @~113 and `test_run_logs_resolved_device_at_startup` @~701).
- (b) The exact bug-trigger command passes: `.venv/bin/python -m pytest "tests/test_daemon.py::test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set" "tests/test_voicectl.py::test_ctl_module_present_and_imports_pure" -q` → **2 passed** (currently `1 failed`).
- (c) The full fast suite passes with **0 failures**: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py` → all green (currently `1 failed`; collection is ~246 tests).
- (d) The 4 tests' own assertions are UNCHANGED (key-set, text-call counts, uptime) — only the resolver is stubbed, which returns the same cfg-derived values.
- (e) No source files (`daemon.py`, `cuda_check.py`, …) are touched; `test_voicectl.py` is NOT touched (that is P1.M2.T1.S2's job — option (b), defense-in-depth).

## User Persona

Not applicable (test-only change; no user-facing/config/API surface change — DOCS: none).

## Why

- **The documented fast suite must be green.** PRD §6/§7.1 acceptance relies on `pytest tests/` (every test module's docstring and the README point users at it). A red fast suite erodes trust in the whole test harness and blocks CI-style validation of every future change. (bugfix Issue 4; PRD §6.)
- **Root cause > symptom.** The polluting tests call the real CUDA driver probe, which imports `ctranslate2` + `torch` (heavy, GPU-side) into the test process for no test-relevant reason — the assertions don't even read the resolved values. Stubbing the resolver (as the hermetic siblings already do) makes them deterministic, fast, CPU-only, and order-safe. The sibling P1.M2.T1.S2 hardens the purity test (option (b)) as defense-in-depth, but THIS task removes the pollution at the source so neither the purity test NOR any future test that touches `sys.modules` is order-fragile.
- **Hermeticity is the project's established convention.** The file already has the `_cuda_resolve(monkeypatch, mapping)` helper (line 66-91) and ~10 sibling tests that use it. The 4 targets are simply the ones missed. Bringing them in line is the smallest, most consistent change.

## What

Add `monkeypatch` to the signature and call `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` as the first body line in each of the 4 tests. `_cuda_resolve` (test_daemon.py:66-91) does `monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)` — the exact attribute `_resolve_device_config` (daemon.py:131) calls — so neither the `cfg_to_kwargs` path nor the `run()` → `_log_resolved_device()` → `_resolved_device()` path imports `ctranslate2`/`torch`. pytest auto-restores the patch at teardown.

### Success Criteria

- [ ] All 4 tests have `monkeypatch` in their signature and a `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` first body line.
- [ ] Bug-trigger command (polluting test THEN purity test, one session) → `2 passed`.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py` → `0 failed`.
- [ ] The 4 tests' assertions are unchanged (only the stubbed resolver + fixture are added).
- [ ] No source files touched; `test_voicectl.py` untouched; no new tests/fixtures/imports added.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the referenced research. The bug is reproduced live (root cause + minimal trigger given), the fix mechanism is proven live (monkeypatching `resolve_device_and_models` leaves `sys.modules` clean), all 4 verbatim edits are given as exact oldText→newText against the current file, and the established hermetic pattern (`_cuda_resolve` + the sibling tests) is referenced with line numbers.

### Documentation & References

```yaml
# MUST READ — root-cause chain + proven fix mechanism + exact edit targets (load-bearing)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T1S1/research/polluting_tests_root_cause.md
  why: "§1 reproduces the bug (minimal trigger). §2 maps the two call chains (cfg_to_kwargs->_
        resolve_device_config->resolve_device_and_models; run()->_log_resolved_device()->_resolved_device()->
        _resolve_device_config->resolve_device_and_models) with line numbers. §3 is the helper + the PROVEN
        mechanism (patching daemon.cuda_check.resolve_device_and_models leaves sys.modules clean). §4 the scope
        boundaries (don't touch test_voicectl.py=S2; don't touch main() tests=T3.S2). §5 the validation strategy."
  section: "§2 (call chains) and §3 (the helper + proof) are load-bearing."

# MUST READ — the helper the fix reuses (verbatim, with its exact monkeypatch target)
- file: tests/test_daemon.py
  why: "_cuda_resolve(monkeypatch, mapping) @66-91: does monkeypatch.setattr(daemon.cuda_check,
        'resolve_device_and_models', _resolve). The cuda-path closure echoes dict(defaults) (cfg-derived
        values) so the assertions still observe the same values. The 4 targets @98,537,549,563 are the ONLY
        tests that call the real resolver. Hermetic siblings @113-165 (cfg_to_kwargs) + @701
        (test_run_logs_resolved_device_at_startup) show the exact pattern to mirror."
  critical: "The helper patches daemon.cuda_check.resolve_device_and_models — the attribute _resolve_device_config
             calls at daemon.py:131. Do NOT patch daemon._resolve_device_config instead (that is T3.S2's pattern for
             the main() tests; the cfg_to_kwargs/run-loop tests should reuse the EXISTING _cuda_resolve helper for
             consistency). Do NOT redefine _cuda_resolve or add imports."

# THE POLLUTION SOURCE — why the real resolver imports ctranslate2/torch
- file: voice_typing/cuda_check.py
  why: "resolve_device_and_models() -> is_cuda_available() -> _cuda_device_count() does `import ctranslate2`
        (cuda_check.py local import), which transitively imports torch. _resolve_device_config (daemon.py:117-131)
        calls resolve_device_and_models(defaults); cfg_to_kwargs (daemon.py:151) and _resolved_device() (the cache
        read by _log_resolved_device at daemon.py:467) both reach it. CUDA_DEFAULTS = {device:'cuda',
        compute_type:'float16', final_model:'distil-large-v3', realtime_model:'small.en'} — the mapping to pass to
        _cuda_resolve for the cuda path."
  critical: "CUDA_DEFAULTS and CPU_FALLBACK are module constants on cuda_check (imported into daemon as
             daemon.cuda_check). _cuda_resolve's `is_fallback = mapping is daemon.cuda_check.CPU_FALLBACK` uses
             identity, so ALWAYS pass the actual constant (daemon.cuda_check.CUDA_DEFAULTS), never a copy/dict."

# THE FAILING ASSERTION (the symptom this fixes; NOT to be edited here — S2's job)
- file: tests/test_voicectl.py
  why: "test_ctl_module_present_and_imports_pure @200-203 asserts `not [m for m in ('RealtimeSTT','torch',
        'ctranslate2') if m in sys.modules]` — a GLOBAL sys.modules assertion that fails when ANY earlier test
        imported those. This task fixes the polluters so the global stays clean; S2 (P1.M2.T1.S2) hardens this
        assertion separately. DO NOT EDIT THIS FILE."
  critical: "This file is OUT OF SCOPE (S2). Editing it here would conflict with S2."

# THE DEFECT (Issue 4) + the option-(a) decision this task implements
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2.3 Issue 4: suggested fix (a) 'make the polluting daemon tests monkeypatch
        cuda_check.resolve_device_and_models (as the _cuda_resolve fixture already does)' — option (a), the smaller
        change. This PRP implements exactly that."

# PARALLEL CONTEXT — T3.S2 (already handling the main() tests; do NOT duplicate)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T3S2/PRP.md
  why: "T3.S2 PART A makes test_main_returns_one_on_daemon_construction_failure (@~979) hermetic (monkeypatches
        daemon._resolve_device_config + daemon.build_recorder) and PART B ADDS 5 main()-retry tests (all hermetic).
        Those are DISTINCT from the 4 targets here. The current daemon.py ALREADY reflects T3.S2 (_log_resolved_device
        reads self._resolved_device() @471; main() has the cuda-retry @1144) — this does NOT change the fix
        (_resolved_device() still calls _resolve_device_config on its cache-miss first call). No edit overlap."
  critical: "Do NOT edit any main()-lifecycle test (T3.S2 owns them). The 4 targets are cfg_to_kwargs + run-loop only."
```

### Current Codebase tree (relevant slice — the only file this task edits)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── test_daemon.py     # EDIT (Task 1: 4 tests gain monkeypatch + _cuda_resolve line). NO other change.
│   │                      #   _cuda_resolve helper @66-91 — REUSED (not redefined). _make_daemon @411 — unchanged.
│   └── test_voicectl.py   # OUT OF SCOPE (P1.M2.T1.S2). Do NOT edit.
└── voice_typing/
    ├── daemon.py          # UNCHANGED. _resolve_device_config @117-131, cfg_to_kwargs @134-151, run() @438,
    │                      #   _log_resolved_device @467 (reads self._resolved_device() — T3.S2-landed).
    └── cuda_check.py      # UNCHANGED. CUDA_DEFAULTS / resolve_device_and_models (the import-polluter).
# No new files. No source edits. No pyproject/uv.lock/.gitignore changes. No new tests/fixtures/imports.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py       # EDIT ONLY — 4 test functions: +monkeypatch param, +_cuda_resolve(...) first line.
# NOTHING ELSE. (test_voicectl.py is P1.M2.T1.S2; daemon.py/cuda_check.py are source; main() tests are T3.S2.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — PASS THE ACTUAL CONSTANT, not a copy. _cuda_resolve uses IDENTITY:
#   `is_fallback = mapping is daemon.cuda_check.CPU_FALLBACK`. So call
#   _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS) — pass daemon.cuda_check.CUDA_DEFAULTS directly
#   (the module constant). Never a dict(...) copy or a literal; `is` would be False and the closure would take the
#   cuda branch (still correct here, but CPU_FALLBACK identity matters for the cpu-fallback siblings — be consistent).

# CRITICAL #2 — THE MONKEYPATCH MUST PRECEDE d.run(). The 3 run-loop tests thread d.run(), whose first iteration
#   calls _log_resolved_device() -> _resolved_device() (cache-miss) -> _resolve_device_config -> the resolver.
#   Put _cuda_resolve(...) as the FIRST body line (before _make_daemon() is fine — construction is already clean
#   via _StubRecorder + _ok_probe; the patch just needs to be live before run() probes). Mirrors
#   test_run_logs_resolved_device_at_startup @701.

# CRITICAL #3 — pytest RESTORES monkeypatch at teardown automatically. No manual cleanup. The patch is scoped to
#   the single test function, so it cannot leak to other tests (that is the whole point). Do NOT use
#   monkeypatch.setattr yourself — call the existing _cuda_resolve helper (single source of truth).

# CRITICAL #4 — DO NOT edit test_voicectl.py. The purity assertion (test_ctl_module_present_and_imports_pure) is
#   the SYMPTOM; S2 (P1.M2.T1.S2) hardens it (option b). This task fixes the CAUSE (option a). Editing the purity
#   test here would conflict with S2. (research §4; prd_snapshot Issue 4.)

# CRITICAL #5 — DO NOT edit the main()-lifecycle tests (test_main_* / _patch_main_lifecycle / BoomDaemon /
#   test_main_returns_one_on_daemon_construction_failure @~979). T3.S2 owns those. The 4 targets here are the
#   cfg_to_kwargs key-set test + the 3 run-loop tests — distinct functions, no overlap. (research §4.)

# CRITICAL #6 — DO NOT add new tests, fixtures, or imports. The 4 edits reuse the EXISTING _cuda_resolve helper
#   (test_daemon.py:66-91) and pytest's BUILTIN monkeypatch fixture (already used by ~30 tests in the file). Adding
#   a conftest autouse fixture would over-reach (it would also change T3.S2's tests' behavior — scope bleed).

# CRITICAL #7 — THE RESOLVED VALUES DON'T MATTER FOR THESE ASSERTIONS. The 4 tests assert the KEY SET of
#   cfg_to_kwargs (not values), text-call counts, and uptime — none read device/compute_type. So stubbing the
#   resolver to return dict(defaults) (the cuda-path closure) changes nothing observable. Do NOT try to "also
#   assert the resolved device" — that is out of scope and would couple these tests to the resolver's return.

# GOTCHA #8 — LINE NUMBERS DRIFT. The item description cited lines 98/517/529/543; the CURRENT tree has them at
#   98/537/549/563 (T3.S2/other work shifted later lines). FIND BY UNIQUE FUNCTION NAME, not line number. The
#   edit tool matches on exact text (the `def <name>(...):\n    <first body line>` block), which is line-number-
#   independent. (Verified current line numbers: 98, 537, 549, 563.)

# GOTCHA #9 — FULL PATHS in every bash command. This machine aliases python3->uv run, pip->alias, tmux->zsh plugin.
#   Invoke .venv/bin/python and .venv/bin/python -m pytest explicitly. Never bare python/pytest/uv.
#   (system_context.md §1; T3.S2 PRP Gotcha #10.)

# GOTCHA #10 — THIS PROJECT USES pytest, NOT ruff/mypy. pyproject has [dependency-groups] dev=["pytest>=9.1.1"]
#   and NO [tool.ruff]/[tool.mypy]. Do NOT invent ruff/mypy validation commands. Validation = py_compile (n/a here,
#   test file) + pytest. (T3.S2 PRP Gotcha #11.)
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/types/imports change. This is a 4×(signature + 1 body line) edit to a test file, reusing an existing helper and a builtin pytest fixture.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT tests/test_daemon.py — add monkeypatch + _cuda_resolve to the 4 polluting tests
  - FIND BY UNIQUE FUNCTION NAME (line numbers ~98/537/549/563 are approximate; match on the def + first body line).
  - Apply these 4 exact oldText -> newText edits (in ONE edit call with 4 entries; each oldText is unique in the file):

    EDIT 1 — test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set (cfg_to_kwargs path):
      OLD:
        def test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set(cfg):
            kw = daemon.cfg_to_kwargs(cfg)
      NEW:
        def test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set(cfg, monkeypatch):
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: avoid the real cuda_check probe
            kw = daemon.cfg_to_kwargs(cfg)

    EDIT 2 — test_run_loop_not_listening_does_not_call_text (run() path):
      OLD:
        def test_run_loop_not_listening_does_not_call_text():
            d, fb, rec, be = _make_daemon()
      NEW:
        def test_run_loop_not_listening_does_not_call_text(monkeypatch):
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
            d, fb, rec, be = _make_daemon()

    EDIT 3 — test_run_loop_calls_text_when_listening_then_exits_on_shutdown (run() path):
      OLD:
        def test_run_loop_calls_text_when_listening_then_exits_on_shutdown():
            d, fb, rec, be = _make_daemon()
      NEW:
        def test_run_loop_calls_text_when_listening_then_exits_on_shutdown(monkeypatch):
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
            d, fb, rec, be = _make_daemon()

    EDIT 4 — test_run_sets_uptime_after_start (run() path):
      OLD:
        def test_run_sets_uptime_after_start():
            d, fb, rec, be = _make_daemon()
      NEW:
        def test_run_sets_uptime_after_start(monkeypatch):
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # hermetic: run()->_log_resolved_device() probes cuda
            d, fb, rec, be = _make_daemon()

  - WHY each: the helper does monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve) — the
    exact attribute _resolve_device_config (daemon.py:131) calls. For the cfg_to_kwargs test, cfg_to_kwargs() ->
    _resolve_device_config() -> resolver; for the run-loop tests, run() -> _log_resolved_device() -> _resolved_device()
    (cache-miss) -> _resolve_device_config() -> resolver. Patching it once at the top covers both paths; pytest
    restores at teardown (hermetic + order-safe). cuda-path closure returns dict(defaults) so the cfg-derived values
    the assertions (don't) read are unchanged. (research §2-3; Gotchas #1-#3.)
  - DO NOT: pass a dict(...) copy to _cuda_resolve (pass daemon.cuda_check.CUDA_DEFAULTS — identity matters, Gotcha
    #1); put the _cuda_resolve call after d.run() (must precede the probe, Gotcha #2); edit test_voicectl.py (Gotcha
    #4); edit main()-lifecycle tests (Gotcha #5); add imports/fixtures/tests (Gotcha #6); change any assertion
    (Gotcha #7).

Task 2: VALIDATE — run the Validation Loop L1-L4 below; fix until all green. No git commit unless the orchestrator
  directs it. If asked, message:
  "P1.M2.T1.S1: monkeypatch cuda_check.resolve_device_and_models in 4 polluting test_daemon.py tests (Issue 4 root-cause fix)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — the established hermetic idiom this task brings 4 stragglers in line with. _cuda_resolve patches the
# exact attribute _resolve_device_config calls; the cuda closure echoes dict(defaults) so cfg values flow through.
def test_<something>(monkeypatch):                       # was: def test_<something>():  (no fixture)
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)   # FIRST body line; patches resolve_device_and_models
    d, fb, rec, be = _make_daemon()                       # construction already clean (StubRecorder + _ok_probe)
    ...                                                   # run()/cfg_to_kwargs() now use the STUB resolver -> no import

# The helper (test_daemon.py:66-91) — REUSED, not redefined:
def _cuda_resolve(monkeypatch, mapping):
    is_fallback = mapping is daemon.cuda_check.CPU_FALLBACK   # identity -> pass the constant, not a copy
    def _resolve(defaults=None):
        if is_fallback: return dict(mapping)
        return dict(defaults) if defaults is not None else dict(mapping)   # cuda path: echo cfg-derived defaults
    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)  # the attribute daemon.py:131 calls
```

### Integration Points

```yaml
SIBLING — P1.M2.T1.S2 (harden the purity test; option b): COMPLEMENTARY, no overlap.
  - S2 edits tests/test_voicectl.py::test_ctl_module_present_and_imports_pure to snapshot sys.modules before/after the
    import (order-independent). THIS task (S1) edits 4 tests in test_daemon.py (root cause). Together: no pollution
    AND a robust purity test. Do NOT touch test_voicectl.py here.

PARALLEL — P1.M1.T3.S2 (main()-lifecycle hermeticity): COMPLEMENTARY, no overlap.
  - T3.S2 makes test_main_returns_one_on_daemon_construction_failure (@~979) + adds 5 main()-retry tests hermetic
    (monkeypatches daemon._resolve_device_config + daemon.build_recorder). The current daemon.py already reflects T3.S2.
    The 4 targets here are DISTINCT (cfg_to_kwargs + run-loop). Do NOT edit any test_main_* test.

UNCHANGED (source):
  - daemon.py (_resolve_device_config @117, cfg_to_kwargs @134, run() @438, _log_resolved_device @467), cuda_check.py
    (resolve_device_and_models, CUDA_DEFAULTS), config.py, ctl.py, typing_backends.py, feedback.py, control-socket,
    install.sh, systemd, launch_daemon.sh, pyproject.toml, uv.lock, .gitignore.

BUILD ARTIFACTS:
  - This task creates NO new files, NO dist/, NO pyproject/uv.lock/.venv changes. It is a 4-edit test patch. No
    `uv sync`/`uv build`. Validation = pytest only.
```

## Validation Loop

> Full paths in every command (zsh aliases — system_context.md §1; Gotcha #9). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy — Gotcha #10). All gates are
> fast/unit (no real CUDA/model load — the resolver is stubbed).

### Level 1: the 4 edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- each of the 4 tests now takes monkeypatch + calls _cuda_resolve ---"
for fn in test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set \
          test_run_loop_not_listening_does_not_call_text \
          test_run_loop_calls_text_when_listening_then_exits_on_shutdown \
          test_run_sets_uptime_after_start; do
  grep -qE "def ${fn}\(.*monkeypatch" tests/test_daemon.py && echo "L1 PASS: $fn has monkeypatch param" || echo "L1 FAIL: $fn missing monkeypatch"
done
echo "--- exactly 4 _cuda_resolve calls in the 4 target bodies (no stray additions) ---"
COUNT=$(grep -cE "_cuda_resolve\(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS\)" tests/test_daemon.py)
echo "total _cuda_resolve(...CUDA_DEFAULTS) calls in file: $COUNT (expect >= the existing siblings + 4 new)"
# Sanity: the 4 target defs each immediately precede a _cuda_resolve line:
grep -A1 -E "def (test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set|test_run_loop_not_listening_does_not_call_text|test_run_loop_calls_text_when_listening_then_exits_on_shutdown|test_run_sets_uptime_after_start)\(" tests/test_daemon.py | grep -c "_cuda_resolve"
# Expected: the param check prints PASS x4; the grep -A1 shows _cuda_resolve right under each def.
```

### Level 2: the bug-trigger passes (the minimal order reproduction)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# THIS IS THE EXACT BUG: polluting test run FIRST, purity test run SECOND in one session.
# Currently (pre-fix): "FAILED ... assert not ['torch', 'ctranslate2']". After fix: 2 passed.
"$PY" -m pytest \
  "tests/test_daemon.py::test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set" \
  "tests/test_daemon.py::test_run_loop_not_listening_does_not_call_text" \
  "tests/test_daemon.py::test_run_loop_calls_text_when_listening_then_exits_on_shutdown" \
  "tests/test_daemon.py::test_run_sets_uptime_after_start" \
  "tests/test_voicectl.py::test_ctl_module_present_and_imports_pure" -q
# Expected: 5 passed, 0 failed. If the purity test STILL fails with ['torch','ctranslate2'], a polluter remains
# (re-check Level 1; confirm _cuda_resolve precedes every d.run()/cfg_to_kwargs call).
```

### Level 3: the full fast suite is green (the PRD §6/§7.1 documented sweep)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed (currently 1 failed — the purity test). Collection is ~246 tests (NOT 211 — the item's
# "211/211" predates T3.S2/other additions; assert by pass/fail, not a hard count). test_feed_audio.py is the
# heavy GPU/offline suite, intentionally ignored on a fast sweep (its own docstring says so).
```

### Level 4: no pollution from test_daemon.py + no regression in the 4 tests' own assertions

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) Running test_daemon.py alone leaves sys.modules clean (the purity test, run right after, passes):
"$PY" -m pytest tests/test_daemon.py tests/test_voicectl.py -q
# Expected: 0 failed. (test_daemon.py alphabetically precedes test_voicectl.py -> reproduces the real order.)
# (b) The 4 tests still pass INDIVIDUALLY with their ORIGINAL assertions intact (no value/behavior change):
"$PY" -m pytest \
  "tests/test_daemon.py::test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set" \
  "tests/test_daemon.py::test_run_loop_not_listening_does_not_call_text" \
  "tests/test_daemon.py::test_run_loop_calls_text_when_listening_then_exits_on_shutdown" \
  "tests/test_daemon.py::test_run_sets_uptime_after_start" -v
# Expected: 4 passed. (Assertions unchanged: key set, text_calls==0/>=2, uptime>=0.0. Only the resolver is stubbed.)
# (c) Scope guard: only test_daemon.py changed; test_voicectl.py + all source untouched:
git status --short
# Expected: ONLY tests/test_daemon.py modified. No daemon.py/cuda_check.py/test_voicectl.py/pyproject/uv.lock.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: all 4 tests have `monkeypatch` in their signature and a `_cuda_resolve(...)` first body line.
- [ ] L2: bug-trigger command (4 polluting tests + purity test, one session) → `5 passed`.
- [ ] L3: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] L4: `pytest tests/test_daemon.py tests/test_voicectl.py -q` → 0 failed (real alphabetical order); the 4 tests pass individually with original assertions; `git status` shows ONLY `tests/test_daemon.py` modified.

### Feature Validation
- [ ] The 4 tests no longer import `ctranslate2`/`torch` (the purity test passes when run after them).
- [ ] The 4 tests' own assertions are unchanged (key set, text-call counts, uptime).
- [ ] No new tests/fixtures/imports added; `_cuda_resolve` reused, not redefined.

### Code Quality Validation
- [ ] Mirrors the existing hermetic pattern (`_cuda_resolve` + sibling tests @113-165, @701).
- [ ] Monkeypatch precedes every `d.run()` / `cfg_to_kwargs()` call in the 4 tests.
- [ ] Full paths used in every bash command (`.venv/bin/python`, no bare python/pytest/uv).

### Scope Boundary Validation
- [ ] No source files touched (`daemon.py`, `cuda_check.py`, `config.py`, `ctl.py`, …).
- [ ] `test_voicectl.py` NOT edited (P1.M2.T1.S2 owns it — option b).
- [ ] No `test_main_*` / main()-lifecycle test edited (P1.M1.T3.S2 owns them).
- [ ] No `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md` changes.

---

## Anti-Patterns to Avoid

- ❌ Don't edit `test_voicectl.py` — the purity test is the SYMPTOM (S2 hardens it); this task fixes the CAUSE.
- ❌ Don't edit the main()-lifecycle tests (`test_main_*`, `test_main_returns_one_on_daemon_construction_failure`) — T3.S2 owns them; the 4 targets are cfg_to_kwargs + run-loop only.
- ❌ Don't add an autouse conftest fixture to "globally" stub the resolver — it would change T3.S2's tests' behavior (scope bleed) and over-reach. Fix the 4 tests in place.
- ❌ Don't patch `daemon._resolve_device_config` instead of using `_cuda_resolve` — the cfg_to_kwargs/run-loop tests should reuse the EXISTING `_cuda_resolve` helper (patches `daemon.cuda_check.resolve_device_and_models`) for consistency with their siblings. (`_resolve_device_config` patching is T3.S2's idiom for the main() tests.)
- ❌ Don't pass a `dict(...)` copy to `_cuda_resolve` — it uses `mapping is daemon.cuda_check.CPU_FALLBACK` (identity); pass `daemon.cuda_check.CUDA_DEFAULTS` directly.
- ❌ Don't place `_cuda_resolve(...)` after `d.run()` — it must precede the probe (run() → _log_resolved_device() resolves on the first iteration).
- ❌ Don't change any of the 4 tests' assertions — only the resolver is stubbed (returns the same cfg-derived values); the assertions don't even read device/compute_type.
- ❌ Don't redefine `_cuda_resolve` or add imports — reuse the helper at test_daemon.py:66-91 and pytest's builtin `monkeypatch`.
- ❌ Don't invent ruff/mypy commands — this project uses pytest only (no `[tool.ruff]`/`[tool.mypy]`).
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases shadow them) — use `.venv/bin/python -m pytest`.
- ❌ Don't edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.

---

## Confidence Score

**10/10** for one-pass implementation success. The bug is reproduced live (minimal trigger → `assert not ['torch', 'ctranslate2']`), the fix mechanism is proven live (monkeypatching `daemon.cuda_check.resolve_device_and_models` leaves `sys.modules` clean on both the `cfg_to_kwargs` and `run()` paths), all 4 edits are given as exact oldText→newText against the current file, and the fix reuses an existing helper + builtin fixture already used by ~10 sibling tests in the same file. The only residual nuance is that line numbers drift (T3.S2/other work) — mitigated by editing via unique function-name text matches, not line numbers. This is the smallest possible root-cause fix for a well-understood test-isolation defect.
