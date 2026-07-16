# PRP — P1.M1.T1.S2: Add kwargs×mode×force_cpu unit tests + reconcile broken test factory closures

## Goal

**Feature Goal**: Add the unit-test coverage that pins Lite mode's construction layer (PRD §4.2ter) and **re-verify** (not redo) the factory-closure reconciliation the contract flagged. Specifically: (1) a **CPU-lite kwargs test** that pins S1's `small.en → tiny.en` CPU-substitute fix (delta §3.2 BUG-A); (2) an **"all-other-kwargs-equal-normal" drift guard** proving lite mode touches exactly 3 keys and nothing else; (3) **config `lite_model` tests** (default / TOML round-trip / non-string rejected); and (4) **confirm the 3 named concurrent-test factory closures are already reconciled** (they are — the live suite is green; S2 verifies rather than re-edits).

**Deliverable**: ~4 new/extended tests across `tests/test_daemon.py` + `tests/test_config.py` only:
- `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` (NEW, daemon) — pins S1.
- `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` (NEW, daemon) — drift guard.
- `test_lite_model_round_trips_through_toml` (NEW, config) + `test_lite_model_wrong_type_raises` (NEW, config) + one added assertion line in `test_defaults_match_prd_4_5`.
No source file (`daemon.py`/`config.py`/`recorder_host.py`) is touched.

**Success Definition**:
- (a) `.venv/bin/python -m pytest tests/test_daemon.py tests/test_config.py -q` → **0 failures** (currently 203 passed → ~206 after the additions).
- (b) `cfg_to_kwargs(cfg, resolved=dict(CPU_FALLBACK), lite=True)` is asserted to yield `model == realtime_model_type == "tiny.en"`, `device == "cpu"`, `compute_type == "int8"`, `use_main_model_for_realtime is True` (pins S1).
- (c) Lite-vs-normal kwargs differ in EXACTLY `{model, realtime_model_type, use_main_model_for_realtime}`; all other keys are byte-identical (drift guard).
- (d) `AsrConfig.lite_model` default `== "small.en"`; round-trips through TOML; a non-string value raises `TypeError` matching `"lite_model"`.
- (e) The 3 named concurrent tests (`test_load_recorder_single_flight_one_build_under_concurrency`, `test_recorder_never_half_torn_down_during_race`, `test_concurrent_start_calls_build_recorder_once`) still pass (factories reconciled — verified, not re-edited).
- (f) `git diff --name-only` ⊆ `{tests/test_daemon.py, tests/test_config.py}`.

## User Persona

**Target User**: The maintainer of the Lite-mode construction layer — anyone editing `cfg_to_kwargs`, `AsrConfig`, or the daemon's factory wiring. The tests fail the build before a change can silently break lite mode's one-model guarantee, its CPU-substitute pick, or the config contract.

**Use Case**: A future edit to `cfg_to_kwargs` (e.g. adding a kwarg, changing the lite model pick, or touching `_FIXED_KWARGS`). The drift guard catches accidental divergence of lite from normal; the CPU-lite test catches a regression of S1's `tiny.en` substitution; the config tests catch a dropped/renamed/mistyped `lite_model`.

**Pain Points Addressed**: Lite mode shipped without a CPU-lite regression test (S1's fix was only verified by a one-off L3 check, never committed) and without a config-level pin on `lite_model`. The existing CUDA-lite test covers only the happy path. These tests close that gap deterministically, fast, and without CUDA.

## Why

- **Pins S1's fix as a committed regression.** S1 (P1.M1.T1.S1) made the lite model device-aware (`tiny.en` on CPU). S1's PRP explicitly deferred the committed CPU-lite test to S2 ("S1 does NOT add tests"). Without S2, S1's correctness rests on an un-merged one-off check — a future refactor could revert it silently.
- **Closes the kwargs-drift blind spot.** The existing `test_cfg_to_kwargs_lite_mode_uses_one_model` asserts 5 fields. It does NOT prove lite mode leaves device/compute_type/language/timing/VAD/silero identical to normal mode. A future `_FIXED_KWARGS` edit could silently diverge. The all-other-kwargs-equal test makes that impossible to miss.
- **Config parity.** `final_model`/`realtime_model`/`device` are pinned in `test_defaults_match_prd_4_5` + `test_int_for_string_field_raises`; `lite_model` (a PRD §4.2ter default + a validated string field) is pinned by neither. S2 adds the same coverage for parity.
- **Fast, hermetic, no CUDA.** All new tests are pure (pass `resolved=` or mock `cuda_check`), run in milliseconds, and never import RealtimeSTT — they belong in the fast pytest suite that gates every commit.
- **Scope discipline.** S2 does NOT touch source (`daemon.py`/`config.py`/`recorder_host.py` — S1 owns those), does NOT build the T7 integration test (P1.M2.T1 owns that), and does NOT redo the already-reconciled factories. The contract's "RE-VERIFY first" mandate is honored: the live suite is green, so S2 verifies rather than re-edits the factories.

## What

Add ~4 tests + 1 assertion line, across the two test files. Verify (don't re-edit) the reconciled factory closures. No runtime behavior change, no config schema change, no API change.

### Success Criteria

- [ ] `tests/test_daemon.py` contains `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en(cfg)` asserting lite+CPU→tiny.en (both fields), cpu/int8, use_main=True.
- [ ] `tests/test_daemon.py` contains `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal(cfg, monkeypatch)` asserting lite differs from normal in EXACTLY 3 keys; all else equal.
- [ ] `tests/test_config.py` `test_defaults_match_prd_4_5` asserts `cfg.asr.lite_model == "small.en"`.
- [ ] `tests/test_config.py` contains `test_lite_model_round_trips_through_toml` and `test_lite_model_wrong_type_raises` (mirror `test_int_for_string_field_raises`).
- [ ] The 3 named concurrent tests pass (factories reconciled — L2 confirms).
- [ ] `pytest tests/test_daemon.py tests/test_config.py -q` → 0 failures (~206 passed).
- [ ] `git diff --name-only` ⊆ `{tests/test_daemon.py, tests/test_config.py}`.

## All Needed Context

### Context Completeness Check

_Pass._ The contract's "RE-VERIFY first" mandate has been honored against the live tree (suite 203/0). The exact status of each deliverable (done vs. missing), the exact functions/signatures (`cfg_to_kwargs(cfg, *, resolved=None, lite=False)`), the exact test patterns to mirror (`_cuda_resolve`, `test_int_for_string_field_raises`, `test_defaults_match_prd_4_5`), and copy-ready reference implementations are all below. An agent new to this repo can implement S2 from this PRP alone. No CUDA/RealtimeSTT needed.

### Documentation & References

```yaml
# THE INPUT CONTRACT (S1 — ALREADY APPLIED)
- file: plan/004_607e9cca32b7/P1M1T1S1/PRP.md
  why: Defines S1's device-aware lite pick (`tiny.en` if resolved["device"]=="cpu" else lite_model) and
       EXPLICITLY defers the committed CPU-lite + config tests to S2 ("S1 does NOT add tests"). S2 is
       that deferred coverage. S1 is already applied (daemon.py:190) so S2's tests pass first run.
  critical: "S1 made cfg_to_kwargs + _child_resolved_device device-aware. S2 PINS that for cfg_to_kwargs
       (the _child_resolved_device side has no dedicated test today — leave it; S2's contract is kwargs
       + config, and the daemon-level status test at test_daemon.py:1551 already covers CPU status)."

# THE FUNCTION UNDER TEST (kwargs)
- file: voice_typing/daemon.py
  why: cfg_to_kwargs @160 — `cfg_to_kwargs(cfg, *, resolved=None, lite=False)`. Passing `resolved=` SKIPS
       the cuda probe (deterministic, no mock). Lite logic: first if-lite (L184) sets both model fields
       to the device-aware pick; kwargs built L193-202 + _FIXED_KWARGS; second if-lite (L~207) sets
       use_main_model_for_realtime=True. → lite differs from normal in EXACTLY {model, realtime_model_type,
       use_main_model_for_realtime}.
  pattern: "CPU-lite test: pass resolved=dict(cuda_check.CPU_FALLBACK) (no monkeypatch). All-other-kwargs
           test: use _cuda_resolve(monkeypatch, CUDA_DEFAULTS) then compare lite vs normal dicts."
  gotcha: "Do NOT import RealtimeSTT — cfg_to_kwargs is pure. Do NOT re-edit cfg_to_kwargs (S1 owns it)."

# THE FALLBACK CONSTANTS (the tiny.en source)
- file: voice_typing/cuda_check.py
  why: CPU_FALLBACK @53 = {device:cpu, compute_type:int8, final_model:small.en, realtime_model:tiny.en}.
        CUDA_DEFAULTS = {device:cuda, compute_type:float16, final_model:distil-large-v3, realtime_model:small.en}.
        The CPU-lite test uses CPU_FALLBACK; the all-other test uses CUDA_DEFAULTS.
  critical: "READ ONLY — do not edit cuda_check.py. CPU_FALLBACK is the canonical CPU config."

# THE CONFIG FIELD + VALIDATION (the config tests)
- file: voice_typing/config.py
  why: AsrConfig.lite_model @54 (default 'small.en'); __post_init__ @93 validates lite_model IS a str
        (in the same list as final_model/realtime_model/language/device) → non-str raises TypeError
        whose message contains 'lite_model'.
  pattern: "Mirror test_int_for_string_field_raises (device→123): from_toml({'asr':{'lite_model':123}})
            raises TypeError match='lite_model'. Mirror the defaults test: assert lite_model=='small.en'."
  gotcha: "READ ONLY — do not edit config.py. The field + validation already exist; S2 only TESTS them."

# THE TEST FILE — kwargs patterns to mirror (tests/test_daemon.py)
- file: tests/test_daemon.py
  why: _cuda_resolve(monkeypatch, mapping) @88 (forces cuda/cpu); cfg fixture @102;
       test_cfg_to_kwargs_lite_mode_uses_one_model @138 (CUDA-lite — DO NOT duplicate);
       test_cfg_to_kwargs_cpu_fallback @162 (normal CPU pattern). Place the 2 new kwargs tests right
       after test_cfg_to_kwargs_cpu_fallback (~L170), in the existing cfg_to_kwargs region.
  pattern: "kwargs tests take (cfg) or (cfg, monkeypatch). _cuda_resolve for the probe path; resolved=
            for the no-probe path. Assert dict fields directly. No RealtimeSTT import."
  critical: "Do NOT modify _cuda_resolve / cfg fixture / the 20 existing kwargs tests. ADDITIVE only.
             Do NOT duplicate test_cfg_to_kwargs_lite_mode_uses_one_model — it covers CUDA-lite."

# THE FACTORY CLOSURES (§2a — VERIFIED RECONCILED, do NOT re-edit)
- file: tests/test_daemon.py
  why: The 3 named concurrent tests (@2817/@2946/@3100) use factory closures with **kw (@2831/@3116) or
       _fake_host_factory(mode=) (@532-538); _FakeHost.__init__(..., mode='normal') @472. The mode= kwarg
       _load_host passes (daemon.py:~737) is absorbed. Suite is 203/0 → reconciled.
  critical: "S2 VERIFIES (L2 -k the 3 names) but does NOT edit these tests. If L2 shows a failure, a
             concurrent process reverted them — re-apply ONLY the **kw acceptance (add **kw to the
             factory def). But as of this PRP they are GREEN."

# THE TEST FILE — config patterns to mirror (tests/test_config.py)
- file: tests/test_config.py
  why: test_defaults_match_prd_4_5 @34 (THE defaults pin — add the lite_model assertion here);
       test_int_for_string_field_raises (device→123 raises TypeError match='device') — EXACT pattern
       for test_lite_model_wrong_type_raises; test_from_toml_partial_table_keeps_other_defaults — TOML
       override pattern; test_log_config_default_and_override — round-trip pattern. 314 lines, ~30 tests.
  pattern: "Config tests are pure (no fixtures beyond tmp_path). from_toml({...}) for the override path;
            pytest.raises(TypeError, match='<field>') for type rejection. Place the 2 new lite_model tests
            in the existing wrong-typed-values section (near test_int_for_string_field_raises) or a new
            lite subsection."
  critical: "Do NOT modify the existing wrong-typed tests. ADDITIVE: extend test_defaults_match_prd_4_5
             with ONE assert line + add 2 new functions."

# THIS SUBTASK'S OWN RESEARCH NOTE — the re-verification + exact patterns
- docfile: plan/004_607e9cca32b7/P1M1T1S2/research/lite_kwargs_and_config_tests_findings.md
  why: §1 the done-vs-missing table (the load-bearing re-verification); §2 cfg_to_kwargs contract;
       §3/§4 the exact patterns + line numbers; §5 the factory reconciliation proof.
  section: "§1 (re-verification) and §2 (cfg_to_kwargs lite logic) are load-bearing."

# PRD CONTEXT
- docfile: plan/004_607e9cca32b7/prd_snapshot.md
  why: §4.2ter (lite mode: lite_model for both fields, use_main_model_for_realtime=True, CPU substitute
       tiny.en) + §4.5 (config defaults) are the spec basis. Cite §4.2ter in the new test docstrings.
```

### Current Codebase tree (relevant slice — S1 applied, suite green)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py          # cfg_to_kwargs @160 (S1 device-aware lite pick @190)  ← READ ONLY for S2
│   ├── config.py          # AsrConfig.lite_model @54 + str-validation @93         ← READ ONLY for S2
│   ├── cuda_check.py      # CPU_FALLBACK @53, CUDA_DEFAULTS                       ← READ ONLY
│   └── recorder_host.py   # _child_resolved_device (S1-applied)                    ← READ ONLY for S2
└── tests/
    ├── test_daemon.py     # _cuda_resolve @88, cfg fixture @102, lite test @138, cpu_fallback @162; factory closures @2831/@3116 (RECONCILED)  ← EDIT (add 2 kwargs tests)
    └── test_config.py     # test_defaults_match_prd_4_5 @34, test_int_for_string_field_raises  ← EDIT (add 1 line + 2 tests)
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py   # MODIFY: +test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en +test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal. NO new files.
tests/test_config.py   # MODIFY: +1 assert in test_defaults_match_prd_4_5 +test_lite_model_round_trips_through_toml +test_lite_model_wrong_type_raises. NO new files.
# NOTHING ELSE. No source (daemon/config/recorder_host/cuda_check), no config.toml, no ctl/feedback.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — RE-VERIFY BEFORE EDITING (the contract mandates this). The live suite is 203/0 GREEN
# and S1 is applied (daemon.py:190). The 3 named factory closures are ALREADY reconciled (**kw). If a
# re-run shows failures, a concurrent process reverted something — re-confirm before editing. Do NOT
# blindly re-apply the factory reconciliation (it would duplicate/conflict).

# CRITICAL #2 — PASS resolved= TO SKIP THE PROBE (CPU-lite test). cfg_to_kwargs(cfg, resolved=dict(
# CPU_FALLBACK), lite=True) does NOT call cuda_check.resolve_device_and_models → no monkeypatch needed,
# fully deterministic. Do NOT use _cuda_resolve for this test (it would be redundant). Use _cuda_resolve
# ONLY for the all-other-kwargs test (which needs the normal CUDA probe path).

# CRITICAL #3 — LITE DIFFERS FROM NORMAL IN EXACTLY 3 KEYS. The drift-guard test must assert that
# {model, realtime_model_type, use_main_model_for_realtime} is the COMPLETE diff set — i.e. the dicts
# with those keys REMOVED are equal. Asserting only "model differs" would miss a silent drift in e.g.
# post_speech_silence_duration. Compute the symmetric-difference of the key SETS first (assert empty
# after removing the 3), then compare the remaining values.

# CRITICAL #4 — DON'T DUPLICATE test_cfg_to_kwargs_lite_mode_uses_one_model (@138). It covers CUDA-lite
# (model/realtime==small.en, use_main=True, lite=False→distil-large-v3). S2 ADDS the CPU-lite path +
# the full-kwargs drift guard — it does not re-test the CUDA-lite happy path.

# CRITICAL #5 — DON'T EDIT SOURCE. S2 touches ONLY the two test files. cfg_to_kwargs / config.py /
# cuda_check.CPU_FALLBACK / recorder_host are all correct as-is (S1 applied them). Editing source here
# would conflict with S1's scope and risk the green suite.

# GOTCHA #6 — NEVER IMPORT REALTIMESTT in the new tests. cfg_to_kwargs is pure (returns a dict); the
# recorder class is never constructed. The existing kwargs tests already honor this — mirror them.

# GOTCHA #7 — match= IN pytest.raises USES re.search. For test_lite_model_wrong_type_raises use
# match="lite_model" (the field name appears literally in the TypeError message "[asr] lite_model
# expects str, ..."). re.search treats it as a substring — no special chars to escape.

# GOTCHA #8 — lite_model DEFAULT IS "small.en", the CUDA lite model. The CPU substitute "tiny.en" is a
# CODE constant (mirrors CPU_FALLBACK), NOT a config default. The config test asserts the DEFAULT
# ("small.en"); the kwargs CPU-lite test asserts the runtime CPU pick ("tiny.en"). Don't conflate.

# GOTCHA #9 — cfg.asr.lite_model DEFAULTS TO "small.en". The all-other-kwargs test uses the cfg
# fixture (defaults), so lite model = small.en on CUDA. Don't set cfg.asr.lite_model to anything else
# in that test (it would muddy the "all other kwargs equal" comparison — though only model/realtime
# change anyway).

# GOTCHA #10 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python -m pytest.
# No ruff/mypy in this project — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

None added. The new tests assert on existing dicts (`cfg_to_kwargs` return) and existing config fields. No schema/type/API change.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: RE-VERIFY the live state (the contract mandates this — do it FIRST).
  - RUN: cd /home/dustin/projects/voice-typing && .venv/bin/python -m pytest tests/test_daemon.py tests/test_config.py -q
  - EXPECT: ~203 passed, 0 failures (as of this PRP). If a different number, note it but proceed (the
    new tests are additive). If the 3 named concurrent tests FAIL here, a concurrent process reverted
    the factory reconciliation — re-apply ONLY by adding **kw to the offending factory def, then proceed.
    Do NOT proceed to add new tests on top of a red suite without understanding why.

Task 1: ADD test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en to tests/test_daemon.py
  - PLACE: in the cfg_to_kwargs region, right after test_cfg_to_kwargs_cpu_fallback (~L170), before
    test_cfg_to_kwargs_fixed_values.
  - CODE (reference implementation — copy-ready):
        def test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en(cfg):
            """lite + CPU → tiny.en for BOTH model fields (pins S1 / delta §3.2 BUG-A; PRD §4.2ter).

            On the CPU path lite mode loads the CPU lite substitute 'tiny.en' for BOTH the final and
            realtime model — mirroring how normal CPU-fallback maps small.en→tiny.en for the realtime
            field. Passing resolved=CPU_FALLBACK skips the cuda_check probe, so this is deterministic
            with NO CUDA and NO monkeypatch. use_main_model_for_realtime stays True (one-model guarantee
            holds on CPU too). This is the committed regression for S1 (P1.M1.T1.S1), which S1's PRP
            explicitly deferred to S2.
            """
            kw = daemon.cfg_to_kwargs(
                cfg, resolved=dict(daemon.cuda_check.CPU_FALLBACK), lite=True
            )
            assert kw["model"] == "tiny.en", kw["model"]
            assert kw["realtime_model_type"] == "tiny.en", kw["realtime_model_type"]
            assert kw["device"] == "cpu"
            assert kw["compute_type"] == "int8"
            assert kw["use_main_model_for_realtime"] is True   # one-model guarantee on CPU too
  - CONSTRAINTS: signature is `(cfg)` — NO monkeypatch (resolved= skips the probe, Gotcha #2). Assert
    BOTH model fields == tiny.en + device/compute/use_main. Do not assert anything about normal mode
    here (that's the next test + the existing lite test).

Task 2: ADD test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal to tests/test_daemon.py
  - PLACE: immediately after Task 1's test.
  - CODE (reference implementation — copy-ready):
        def test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal(cfg, monkeypatch):
            """Lite mode changes ONLY model/realtime_model_type/use_main_model_for_realtime — nothing else.

            Drift guard (PRD §4.2ter): device/compute_type/language/timing/VAD/silero must be IDENTICAL
            between lite and normal mode on CUDA, so a future cfg_to_kwargs / _FIXED_KWARGS edit can't
            silently diverge lite from normal. The CUDA-lite model pick itself is pinned by
            test_cfg_to_kwargs_lite_mode_uses_one_model; this test guards the REST of the kwargs dict.
            """
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
            normal = daemon.cfg_to_kwargs(cfg)
            lite = daemon.cfg_to_kwargs(cfg, lite=True)

            differing = {"model", "realtime_model_type", "use_main_model_for_realtime"}
            # 1) the key SETS are identical (no kwarg silently added/dropped by lite):
            assert set(normal) == set(lite)
            # 2) after removing the 3 allowed-to-differ keys, the remaining dicts are byte-identical:
            assert {k: v for k, v in lite.items() if k not in differing} == \
                   {k: v for k, v in normal.items() if k not in differing}
            # 3) and the 3 differing keys differ EXACTLY as the spec requires:
            assert lite["model"] == cfg.asr.lite_model == "small.en"        # lite_model as the final model
            assert lite["realtime_model_type"] == "small.en"                # AND the realtime model (one model)
            assert lite["use_main_model_for_realtime"] is True              # skips the realtime engine
            assert normal["model"] == "distil-large-v3"
            assert normal["realtime_model_type"] == "small.en"
            assert normal["use_main_model_for_realtime"] is False
  - CONSTRAINTS: signature `(cfg, monkeypatch)` — uses _cuda_resolve(CUDA_DEFAULTS) (the probe path).
    The load-bearing assertion is #2 (the dict-comprehension equality after removing the 3 keys). The
    set-equality (#1) guards against a kwarg being silently added/dropped. Do NOT modify _cuda_resolve.

Task 3: EXTEND test_defaults_match_prd_4_5 in tests/test_config.py (+1 assertion line)
  - FIND: the `[asr]` block in test_defaults_match_prd_4_5 (asserts final_model/realtime_model/
    language/device/...).
  - ADD one line in the [asr] block (right after the realtime_model or lite_model neighbor):
        assert cfg.asr.lite_model == "small.en"   # PRD §4.2ter: the single model loaded in lite mode
  - WHY here: test_defaults_match_prd_4_5 is THE canonical "defaults match PRD §4.5 exactly" pin;
    lite_model is a PRD §4.2ter default and belongs here for parity with final_model/realtime_model.

Task 4: ADD test_lite_model_round_trips_through_toml + test_lite_model_wrong_type_raises to tests/test_config.py
  - PLACE: in the existing wrong-typed-values section (near test_int_for_string_field_raises) OR a new
    "# [asr] lite_model (PRD §4.2ter)" subsection right after it.
  - CODE (reference implementation — copy-ready):
        def test_lite_model_round_trips_through_toml():
            """[asr] lite_model parses from TOML and overrides the default (PRD §4.2ter)."""
            cfg = VoiceTypingConfig.from_toml({"asr": {"lite_model": "tiny.en"}})
            assert cfg.asr.lite_model == "tiny.en"               # overridden
            assert cfg.asr.final_model == "distil-large-v3"      # other defaults kept

        def test_lite_model_wrong_type_raises():
            """A non-string lite_model is rejected at load (mirrors device/final_model type guard)."""
            for bad in (123, 12.0, True, None, ["small.en"]):
                with pytest.raises(TypeError, match="lite_model"):
                    VoiceTypingConfig.from_toml({"asr": {"lite_model": bad}})
  - CONSTRAINTS: mirror test_int_for_string_field_raises exactly (pytest.raises(TypeError, match=...)).
    The loop over several bad types (int/float/bool/None/list) is stronger than a single case and
    matches the file's thoroughness (cf. test_notify_ms_wrong_type_raises iterating bad values).
    match="lite_model" works via re.search (Gotcha #7). Do NOT modify existing type tests.

Task 5: VALIDATE — run the Validation Loop L1–L4. No git commit unless the orchestrator directs it.
  If asked to commit, message:
  "P1.M1.T1.S2: add lite kwargs×mode×force_cpu + lite_model config unit tests; verify factory reconciliation".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — deterministic CPU-lite kwargs WITHOUT a mock (Task 1):
# cfg_to_kwargs(cfg, resolved=dict(cuda_check.CPU_FALLBACK), lite=True) passes resolved=, which makes
# cfg_to_kwargs SKIP the cuda_check probe entirely (no ctranslate2 import, no driver probe). The lite
# branch then sees resolved["device"]=="cpu" → picks tiny.en for both fields. Fully deterministic, no
# monkeypatch. This is the cleanest way to pin S1's CPU substitution.

# PATTERN 2 — comprehensive kwargs drift guard (Task 2):
# Lite mode is ONLY allowed to differ from normal on {model, realtime_model_type, use_main_model_for_
# realtime}. Pinning that the dicts-minus-those-keys are EQUAL catches any future _FIXED_KWARGS /
# cfg_to_kwargs edit that silently diverges lite (e.g. someone "optimizes" lite by changing a VAD
# threshold). First assert the KEY SETS are equal (no silent add/drop), then the value dicts.

# PATTERN 3 — config parity (Tasks 3-4):
# final_model/realtime_model/device are pinned in test_defaults_match_prd_4_5 + a wrong-type test each.
# lite_model is a PRD §4.2ter default + a __post_init__-validated str field; give it the SAME coverage:
# one assertion in the canonical defaults test + a round-trip + a wrong-type test.

# GOTCHA: never construct the recorder in these tests. cfg_to_kwargs returns a plain dict; AsrConfig is
# a dataclass. Both are pure — no RealtimeSTT, no CUDA, no subprocess.
```

### Integration Points

```yaml
TEST SUITE:
  - The new tests join the existing kwargs + config suites. `pytest tests/test_daemon.py
    tests/test_config.py -q` → ~206 passed. S2 is purely additive (1 assertion line + 4 new functions),
    so no existing test can regress.

DEPENDS ON (S1 — P1.M1.T1.S1):
  - Task 1's CPU-lite test PASSES only because S1 made the lite model device-aware (tiny.en on CPU).
    S1 is already applied. If a future change reverts S1, Task 1's test goes RED — exactly intended.
    S1 (fix) + S2 Task 1 (proof) form a pair.

DOWNSTREAM (P1.M2.T1.S1 — T7 lite integration):
  - T7 exercises the REAL recorder (one-model resident, accuracy, latency, socket mode-switch). S2's
    unit tests are the fast, hermetic precursor that pin the construction-layer contract T7 relies on.
    S2 does NOT touch T7's scope.

FACTORY RECONCILIATION (§2a — VERIFIED, not edited):
  - The 3 named concurrent tests already accept mode= via **kw. S2 confirms (L2) but does not re-edit.
    If a concurrent process reverts them, re-apply ONLY the **kw acceptance on the factory def.

FILES NOT TOUCHED (scope boundary):
  - voice_typing/{daemon,config,recorder_host,cuda_check}.py (S1/source-owned; all correct as-is).
  - config.toml, ctl.py, feedback.py, systemd/ (other milestones).
```

## Validation Loop

> All commands use FULL PATHS (machine aliases python3→uv run). Run from `/home/dustin/projects/voice-typing`.
> All gates are FAST unit tests — NO GPU/CUDA/RealtimeSTT/network. No ruff/mypy in this project.

### Level 0: Re-verify the live baseline (the contract's §1 mandate — run FIRST)

```bash
cd /home/dustin/projects/voice-typing
echo "--- baseline (before S2's edits): must be GREEN ---"
.venv/bin/python -m pytest tests/test_daemon.py tests/test_config.py -q 2>&1 | tail -4
# Expected: ~203 passed, 0 failures. If the 3 named concurrent tests FAIL here, a concurrent process
# reverted the factory reconciliation — re-apply **kw to the offending factory def before proceeding.
```

### Level 1: The new tests are well-formed + discovered

```bash
cd /home/dustin/projects/voice-typing
echo "--- both test files parse ---"
.venv/bin/python -c "import ast; ast.parse(open('tests/test_daemon.py').read()); ast.parse(open('tests/test_config.py').read()); print('L1a PASS: parse')"
echo "--- new kwargs tests collected ---"
.venv/bin/python -m pytest tests/test_daemon.py --collect-only -q | grep -E 'test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en|test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal' \
  && echo "L1b PASS" || echo "L1b FAIL"
echo "--- new config tests collected ---"
.venv/bin/python -m pytest tests/test_config.py --collect-only -q | grep -E 'test_lite_model_round_trips_through_toml|test_lite_model_wrong_type_raises' \
  && echo "L1c PASS" || echo "L1c FAIL"
# Expected: parses; all 4 new tests + the extended defaults test collected.
```

### Level 2: The new tests PASS + factory reconciliation confirmed + existing tests green

```bash
cd /home/dustin/projects/voice-typing
echo "--- the 2 new kwargs tests ---"
.venv/bin/python -m pytest tests/test_daemon.py -v -k "lite_cpu_fallback_uses_tiny_en or lite_keeps_all_other_kwargs_equal" 2>&1 | tail -6
echo "--- the new config tests + the extended defaults test ---"
.venv/bin/python -m pytest tests/test_config.py -v -k "lite_model or defaults_match_prd" 2>&1 | tail -8
echo "--- factory reconciliation CONFIRMED (the 3 named concurrent tests pass unchanged) ---"
.venv/bin/python -m pytest tests/test_daemon.py -q -k "single_flight_one_build_under_concurrency or never_half_torn_down_during_race or concurrent_start_calls_build_recorder_once" 2>&1 | tail -4
echo "--- the existing CUDA-lite + normal-CPU tests still green (not duplicated/broken) ---"
.venv/bin/python -m pytest tests/test_daemon.py -q -k "lite_mode_uses_one_model or cfg_to_kwargs_cpu_fallback" 2>&1 | tail -4
# Expected: all PASS. If lite_cpu_fallback_uses_tiny_en FAILS (got small.en not tiny.en), S1's device-aware
# pick was reverted — re-check daemon.py:190. If lite_keeps_all_other_kwargs_equal FAILS on the dict
# equality, a future _FIXED_KWARGS edit diverged lite from normal (investigate the diff).
```

### Level 3: Full affected suites green + the S1-pinning assertion is load-bearing

```bash
cd /home/dustin/projects/voice-typing
echo "--- full daemon + config suites ---"
.venv/bin/python -m pytest tests/test_daemon.py tests/test_config.py -q 2>&1 | tail -4
echo "--- OPTIONAL: prove Task 1 catches an S1 regression (no source commit) ---"
# Temporarily revert S1's device-aware pick to the unconditional lite_model, confirm Task 1 goes RED:
cp voice_typing/daemon.py /tmp/daemon.py.bak
.venv/bin/python - <<'PY'
import re, pathlib
p = pathlib.Path("voice_typing/daemon.py")
s = p.read_text()
s2 = s.replace(
    'lite_model = "tiny.en" if resolved["device"] == "cpu" else cfg.asr.lite_model',
    'lite_model = cfg.asr.lite_model  # MUTATION: defeat the CPU substitution',
)
p.write_text(s2 if s2 != s else s)
print("mutation applied" if s2 != s else "WARN: anchor not found (S1 shape changed)")
PY
.venv/bin/python -m pytest tests/test_daemon.py::test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en -q 2>&1 | tail -5
echo "    exit after mutation: $? (expect NON-zero / FAILED — model would be small.en not tiny.en)"
cp /tmp/daemon.py.bak voice_typing/daemon.py && rm -f /tmp/daemon.py.bak   # RESTORE S1
git diff --quiet voice_typing/daemon.py && echo "L3b PASS: daemon.py restored (S1 intact)" || echo "L3b FAIL: daemon.py differs — git checkout it"
# Expected: full suites green; Task 1 FAILS under the mutation (small.en != tiny.en); daemon.py restored.
# (This proves the CPU-lite test is not vacuous — it pins S1's actual behavior.)
```

### Level 4: Scope — only the two test files changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY tests/test_daemon.py + tests/test_config.py ---"
git diff --name-only | grep -vE 'tests/(test_daemon|test_config)\.py' | grep -E '\.py$|systemd/|config|cuda_check|ctl|feedback|recorder_host' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: only the 2 test files changed"
echo "--- source files UNTOUCHED (esp. daemon.py after the L3 mutation+restore) ---"
git diff --quiet voice_typing/daemon.py voice_typing/config.py voice_typing/recorder_host.py voice_typing/cuda_check.py \
  && echo "L4 PASS: all source files unchanged" || echo "L4 FAIL: a source file was modified"
# Expected: only the 2 test files in the diff; all source byte-identical to git.
```

## Final Validation Checklist

### Technical Validation
- [ ] L0: baseline `pytest tests/test_daemon.py tests/test_config.py -q` green (~203 passed) BEFORE editing.
- [ ] L1: both test files parse; the 4 new tests collected.
- [ ] L2: 2 new kwargs tests pass; 2 new config tests + extended defaults test pass; the 3 named concurrent tests pass (factories reconciled); existing CUDA-lite + normal-CPU tests green.
- [ ] L3: full suites green (~206 passed); Task 1 FAILS under the S1-revert mutation (small.en≠tiny.en) then daemon.py restored (S1 intact).
- [ ] L4: `git diff --name-only` ⊆ `{tests/test_daemon.py, tests/test_config.py}`; all source unchanged.

### Feature Validation
- [ ] CPU-lite kwargs test asserts `model == realtime_model_type == "tiny.en"`, cpu/int8, use_main=True (pins S1).
- [ ] All-other-kwargs-equal test proves lite differs from normal in EXACTLY 3 keys; rest byte-identical.
- [ ] `AsrConfig.lite_model` default `== "small.en"`; round-trips through TOML; non-string raises `TypeError` matching `lite_model`.
- [ ] Factory reconciliation CONFIRMED (3 named tests pass) — not re-edited.

### Code Quality Validation
- [ ] New kwargs tests mirror `_cuda_resolve`/`cfg` fixture patterns; CPU-lite test uses `resolved=` (no monkeypatch).
- [ ] New config tests mirror `test_int_for_string_field_raises` / `test_from_toml_partial_table` patterns.
- [ ] No new imports of RealtimeSTT; no CUDA/subprocess; tests are pure + fast.
- [ ] Additive only (1 assertion line + 4 new functions); no existing test modified beyond the 1-line defaults extension.

### Scope Boundary Validation
- [ ] `voice_typing/{daemon,config,recorder_host,cuda_check}.py` unmodified (source-owned; S1 applied).
- [ ] No config.toml / ctl.py / feedback.py / systemd edits.
- [ ] Factory reconciliation VERIFIED, not redone (no edit to the 3 named tests' factory closures).
- [ ] No bare `python`/`pytest` (full-pathed `.venv/bin/python -m pytest`); no ruff/mypy invoked.

### Documentation & Deployment
- [ ] (No user-facing docs — test-only subtask.) New test docstrings cite PRD §4.2ter / delta §3.2 BUG-A.
- [ ] If asked to commit: message references lite kwargs×mode×force_cpu + config tests + factory verification.

---

## Anti-Patterns to Avoid

- ❌ Don't skip L0 (re-verify baseline) — the contract mandates it; the tree moves. If the 3 named tests fail at baseline, a concurrent process reverted the factories — re-apply `**kw`, don't ignore.
- ❌ Don't re-edit the already-reconciled factory closures — they use `**kw` and the suite is green. S2 VERIFIES (L2) only. Editing them duplicates/conflicts with prior work.
- ❌ Don't duplicate `test_cfg_to_kwargs_lite_mode_uses_one_model` (@138) — it covers CUDA-lite. S2 adds the CPU-lite path + the full-kwargs drift guard.
- ❌ Don't use `_cuda_resolve` for the CPU-lite test — pass `resolved=dict(CPU_FALLBACK)` instead (skips the probe, no monkeypatch, deterministic). Use `_cuda_resolve` only for the all-other-kwargs test (CUDA path).
- ❌ Don't assert only "model differs" in the drift guard — assert the dicts-minus-3-keys are EQUAL (and the key SETS are equal). A weak assertion misses silent drift in timing/VAD/silero.
- ❌ Don't edit source (`daemon.py`/`config.py`/`cuda_check.py`/`recorder_host.py`) — S1 applied them; they're correct. S2 is test-only. (The L3 mutation is transient + restored.)
- ❌ Don't import RealtimeSTT in the new tests — `cfg_to_kwargs` is pure; `AsrConfig` is a dataclass. No CUDA, no subprocess.
- ❌ Don't build the T7 integration test here — that's P1.M2.T1.S1 (real recorder, accuracy, latency). S2 is the fast unit precursor.
- ❌ Don't conflate the config DEFAULT (`lite_model == "small.en"`) with the runtime CPU pick (`tiny.en`). The config test pins the default; the kwargs CPU-lite test pins the CPU substitution.
- ❌ Don't use bare `python`/`pytest` or invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest`.

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a small, fully-specified, purely-additive test task with copy-ready reference implementations for all 4 new tests + 1 assertion line. Every load-bearing fact is empirically re-verified against the live tree (the contract's §1 mandate): the suite is 203/0 green (factories reconciled), S1 is applied (daemon.py:190), the CUDA-lite test exists (@138), the exact `cfg_to_kwargs` signature/`resolved=` param + lite logic are confirmed, and the config field + `__post_init__` validation + the `test_int_for_string_field_raises` mirror pattern are all read in full. The L0 gate enforces the re-verification first; L2 proves the new tests pass + the existing ones stay green + the factories stay reconciled; L3 proves the CPU-lite test is not vacuous (it catches an S1 revert). The −0.5 is the standard "moving tree" caveat the contract itself raises (mitigated by L0 re-verify + the additive-only scope): if a concurrent change alters `cfg_to_kwargs`'s lite shape or the config field between now and implementation, the agent must re-confirm the anchors rather than blindly apply.
