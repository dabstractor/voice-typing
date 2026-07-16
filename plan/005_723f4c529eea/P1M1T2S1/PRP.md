# PRP — P1.M1.T2.S1: Config unit tests for `lite_post_speech_silence_duration`

## Goal

**Feature Goal**: Add the config unit-test coverage for the new `AsrConfig.lite_post_speech_silence_duration` field (PRD §4.2ter / §4.5, added by P1.M1.T1.S1). Pin its **default** (`0.5`), its **TOML round-trip** (override works), its **wrong-type rejection** (bool/str/None/list raise `TypeError` with the field name), and its **type** (`float`, not `int`). These mirror the existing `lite_model` and `post_speech_silence_duration` test patterns exactly, locking the field's contract into the fast pytest suite so a future edit (rename, type change, dropped validation, altered default) fails the build before it can silently break lite mode's silence override (the load-bearing latency lever per §4.2ter).

**Deliverable**: Edits to ONE file — `tests/test_config.py` — only:
1. One new assertion line in `test_defaults_match_prd_4_5` (the default value).
2. One new assertion line in `test_field_types_are_tomllib_natural_types` (the `float` type check).
3. One new test `test_lite_post_speech_silence_duration_round_trips_through_toml` (TOML override).
4. One new test `test_lite_post_speech_silence_duration_wrong_type_raises` (wrong-type loop).

No source file (`config.py`/`config.toml`/`daemon.py`), no other test file. This is a **test-only** subtask.

**Success Definition**:
- (a) `.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -v` → **0 failures** (all existing tests stay green + the 2 new tests + 2 new assertion lines pass).
- (b) `VoiceTypingConfig().asr.lite_post_speech_silence_duration == 0.5` is asserted (default).
- (c) `isinstance(cfg.asr.lite_post_speech_silence_duration, float)` is asserted (type check).
- (d) `VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": 0.3}})` yields `== 0.3` (round-trip override).
- (e) For each bad value in `[True, "0.5", None, [0.5]]`, `from_toml({"asr": {"lite_post_speech_silence_duration": bad}})` raises `TypeError` with `match="lite_post_speech_silence_duration"` (wrong-type rejection).
- (f) `git diff --name-only` == `tests/test_config.py` (only this one file).

## User Persona

**Target User**: The maintainer of the config schema / lite-mode plumbing — anyone editing `AsrConfig`, the `__post_init__` validation tuple, or the lite-mode `cfg_to_kwargs` override (P1.M2.T1). The tests fail the build before a change can silently break the field's default, type, validation, or TOML parse.

**Use Case**: A future edit renames the field, changes its default, drops it from the validation tuple, or alters its type. The default/type/round-trip/wrong-type tests catch it immediately in the fast pytest suite (milliseconds, no CUDA/daemon/models), forcing a conscious decision rather than a silent regression that would resurface as "lite mode feels no faster than normal" (§4.2ter) or a swallowed `TypeError` in the idle watchdog at runtime.

**Pain Points Addressed**: The field shipped (P1.M1.T1.S1) WITHOUT dedicated unit tests — its default, type, and validation rest on the drift-guard test alone (which only checks config.py↔config.toml parity, not the field's own contract). These tests close that gap with the same four-angle coverage `lite_model` and `post_speech_silence_duration` already have.

## Why

- **Pins the field's contract as a committed regression.** S1 added the field + validation + config.toml mirror + the repo-default drift guard atomically. But the drift guard only proves config.py and config.toml AGREE; it does not pin the default VALUE (`0.5`), the TYPE (`float`), the round-trip override, or the wrong-type rejection as standalone assertions. A future refactor could change the default to `0.6` (silently making lite feel like normal — the exact failure §4.2ter warns about) while keeping config.py↔config.toml parity, and the drift guard would stay green. These tests catch that.
- **Validation parity with the sibling fields.** `post_speech_silence_duration` (the normal-mode analogue) has the bool/wrong-type guard pinned by `test_bool_for_float_field_raises`. `lite_model` has its round-trip + wrong-type pinned (`test_lite_model_round_trips_through_toml`, `test_lite_model_wrong_type_raises`). `lite_post_speech_silence_duration` — a PRD §4.5 default + a validated numeric field — has NEITHER. S1 adds it to the validation tuple; T2.S1 (this) pins that for the new field too, mirroring the siblings.
- **Fast, hermetic, no CUDA.** All new tests are pure (`VoiceTypingConfig()` / `from_toml({...})`), run in milliseconds, and never import RealtimeSTT/torch/the daemon — they belong in the fast pytest suite that gates every commit.
- **Scope discipline.** T2.S1 owns ONLY `tests/test_config.py`. It does NOT touch `config.py`/`config.toml` (S1 owns those), does NOT wire the field into `cfg_to_kwargs`'s lite override (P1.M2.T1), does NOT touch the repo-default drift guard (`tests/test_config_repo_default.py` — S1 owns it), and does NOT update README/ACCEPTANCE (P1.M3).

## What

Add 2 assertion lines to 2 existing tests + 2 new test functions, all in `tests/test_config.py`. No runtime behavior change, no schema change, no API change.

### Success Criteria

- [ ] `test_defaults_match_prd_4_5` asserts `cfg.asr.lite_post_speech_silence_duration == 0.5`.
- [ ] `test_field_types_are_tomllib_natural_types` asserts `isinstance(cfg.asr.lite_post_speech_silence_duration, float)`.
- [ ] `test_lite_post_speech_silence_duration_round_trips_through_toml` exists, asserts `from_toml({...,0.3}) == 0.3`.
- [ ] `test_lite_post_speech_silence_duration_wrong_type_raises` exists, loops `[True, "0.5", None, [0.5]]` each raising `TypeError(match="lite_post_speech_silence_duration")`.
- [ ] `.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -v` → 0 failures.
- [ ] `git diff --name-only` == `tests/test_config.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact existing test patterns to mirror (verbatim, with line numbers), the field's verified state in `config.py` (default `0.5`, in the numeric-validation tuple, message contains the field name), the validation rule (accept int/float; reject bool + everything else), the exact `match=` string, and the no-conflict boundary with S1 are all below. An agent new to this repo can implement T2.S1 from this PRP alone. No CUDA/daemon/models needed.

### Documentation & References

```yaml
# THE INPUT CONTRACT — the field under test (S1, landing now)
- docfile: plan/005_723f4c529eea/P1M1T1S1/PRP.md
  why: S1 adds AsrConfig.lite_post_speech_silence_duration: float = 0.5 (config.py:59), registers it in
       the __post_init__ numeric-validation tuple (config.py:87), mirrors it in config.toml, and updates
       the repo-default drift guard. S1's PRP explicitly defers the dedicated field unit tests to T2
       ("no dedicated field unit tests (T2)"). T2.S1 IS that deferred coverage.
  critical: "S1's config.py edits (the field + the validation-tuple entry) are ALREADY in the live tree
       (config.py:59 + :87 — verified). So T2.S1's tests pass first run. S1's config.toml/repo-default-
       test edits may still be in flight, but T2.S1's tests only need the config.py FIELD, which exists."

# THE FIELD + VALIDATION RULE (verified in the live config.py)
- file: voice_typing/config.py
  why: AsrConfig L49-65 (lite_post_speech_silence_duration: float = 0.5 @ L59, right after
       post_speech_silence_duration @ L58). __post_init__ L72-110: the numeric-fields loop
       (L86-97) checks `if isinstance(_v, bool) or not isinstance(_v, (int, float)): raise TypeError(
       f"[asr] {_name} expects a number (int or float), got {type(_v).__name__}: {_v!r}")` — and
       lite_post_speech_silence_duration is in that tuple (L87). So: int/float ACCEPTED; bool/str/
       None/list REJECTED; the TypeError MESSAGE contains the field name -> match= works.
  pattern: "The validation accepts int OR float (test_int_accepted_for_float confirms int is taken
            as-is). So the wrong-type loop must use values that are NEITHER int NOR float: [True, '0.5',
            None, [0.5]]. Do NOT include a bare int (e.g. 1) — it would NOT raise (int is accepted)."
  critical: "match='lite_post_speech_silence_duration' works because the f-string includes {_name}. Verified."

# THE PATTERNS TO MIRROR (verbatim, in tests/test_config.py)
- file: tests/test_config.py
  why: Four existing patterns map 1:1 to the four deliverables:
       * DEFAULT: test_defaults_match_prd_4_5 (L38-47) — already asserts lite_model (L44) + post_speech
         (L47); ADD the lite_post assertion next to the post_speech one.
       * TYPE CHECK: test_field_types_are_tomllib_natural_types (L79-87) — already asserts
         isinstance(post_speech_silence_duration, float) @ L82; ADD the lite_post one next to it.
       * ROUND-TRIP: test_lite_model_round_trips_through_toml (L167-171) — the template for the new
         round-trip test.
       * WRONG-TYPE: test_lite_model_wrong_type_raises (L174-179) — the template for the new wrong-type
         loop. ALSO test_bool_for_float_field_raises (L148-151) shows the float-field match= pattern.
  pattern: "Mirror the lite_model tests' naming + structure exactly: test_<field>_round_trips_through_toml
            + test_<field>_wrong_type_raises. Place them right after test_lite_model_wrong_type_raises
            (~L179) so all lite-mode config tests cluster together."
  critical: "The wrong-type loop's bad list is [True, '0.5', None, [0.5]] — NOT the lite_model list
            ([123, 1.5, True, None, [...]]), because this is a FLOAT field (int/float accepted). A bare
            int in the list would NOT raise -> a vacuous/wrong test."

# THE ANALYSIS (research note referenced by the contract)
- docfile: plan/005_723f4c529eea/architecture/daemon_analysis.md
  why: §Test Impact Analysis points at these exact existing tests as the patterns. Confirms the
       four-angle coverage (default / round-trip / wrong-type / type) is the established convention
       for config fields in this file.
  section: "Test Impact Analysis — the lite_post_speech_silence_duration test-addition row."
```

### Current Codebase tree (relevant slice — S1's config.py field already landed)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── config.py            # AsrConfig.lite_post_speech_silence_duration: float = 0.5 @ L59;
│   │                        #   in the __post_init__ numeric tuple @ L87. READ-ONLY for T2.S1 (S1 owns it).
└── tests/
    └── test_config.py       # ← EDIT (the ONLY file). test_defaults_match_prd_4_5 @ L38; test_field_types
                             #   @ L79; test_lite_model_round_trips @ L167; test_lite_model_wrong_type @ L174.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_config.py         # MODIFY: +1 assert in test_defaults_match_prd_4_5; +1 assert in
#                            #   test_field_types_are_tomllib_natural_types; +2 new test fns. NO new files.
# No config.py / config.toml / daemon.py / other test files. (S1 owns config.py+config.toml+test_config_repo_default.py.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE WRONG-TYPE BAD LIST MUST BE NON-NUMERIC. The __post_init__ numeric validation
# (config.py L86-97) ACCEPTS int OR float and rejects bool + everything else. So the wrong-type loop
# for lite_post_speech_silence_duration must use [True, "0.5", None, [0.5]] (bool/str/None/list — NONE
# is an accepted int/float). Do NOT copy lite_model's list ([123, 1.5, ...]) — 123 and 1.5 would NOT
# raise for a FLOAT field (they're valid), making the test vacuous/wrong. (test_int_accepted_for_float
# confirms int is accepted as-is.)

# CRITICAL #2 — bool IS REJECTED even though isinstance(True, int). The validation explicitly checks
# `isinstance(_v, bool)` FIRST (the "bool is an int subclass" gotcha, config.py L94). So True raises.
# Keep True in the bad list — it's the load-bearing case (a user writing `= true` in TOML, which
# tomllib parses to Python True). test_bool_for_float_field_raises pins this for post_speech; mirror it.

# CRITICAL #3 — match= THE FIELD NAME, not the full message. The TypeError f-string is
# `f"[asr] {_name} expects a number (int or float), got {type(_v).__name__}: {_v!r}"`. The substring
# "lite_post_speech_silence_duration" (== {_name}) is in EVERY bad-value message, so
# `match="lite_post_speech_silence_duration"` asserts reliably across all four bad values. Do NOT
# match on the type name (it varies: bool/str/NoneType/list) or the value repr.

# CRITICAL #4 — DEFAULT 0.5, NOT 0.6. lite_post_speech_silence_duration defaults to 0.5 (the snugger
# lite threshold — §4.2ter), distinct from post_speech_silence_duration's 0.6. Asserting == 0.5 pins
# that lite is snugger; a future edit that copies the 0.6 default (silently making lite feel like
# normal — the exact §4.2ter failure) would fail this test. Do NOT assert 0.6.

# GOTCHA #5 — DON'T DUPLICATE assertions. test_defaults_match_prd_4_5 and test_field_types_are_tomllib_
# natural_types do NOT currently mention lite_post_speech_silence_duration (verified: the field is new).
# Add ONE line to each. Do NOT also add a standalone default test (the contract allows either; adding to
# the existing tests is the consistent choice — lite_model is already asserted in test_defaults_match).

# GOTCHA #6 — PLACE THE 2 NEW TESTS IN THE LITE-MODEL CLUSTER. test_lite_model_round_trips_through_toml
# (L167) + test_lite_model_wrong_type_raises (L174) are the siblings; put the 2 new tests immediately
# after test_lite_model_wrong_type_raises (~L179) so the lite-mode config tests group together + the
# file stays readable. (The post_speech tests at L148-151 are the float-field wrong-type precedent but
# live in the generic wrong-type section — the lite cluster is the better home for lite-named tests.)

# GOTCHA #7 — DON'T TOUCH config.py / config.toml / test_config_repo_default.py. S1 owns those. T2.S1
# is tests/test_config.py ONLY. If a test reveals the field is missing from config.py, that's an S1
# regression (flag it), NOT a T2.S1 edit. (As verified, the field IS present: config.py:59 + :87.)

# GOTCHA #8 — FULL PATHS. `.venv/bin/python -m pytest` (the machine aliases python3 -> uv run).
# No ruff/mypy configured in this project — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

None. No ORM/pydantic/dataclass changes. The only "structure" is four pytest assertions (2 inline additions + 2 new functions), all consuming the existing `VoiceTypingConfig` / `AsrConfig` / `from_toml` API.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY tests/test_config.py — add the default-value assertion (test_defaults_match_prd_4_5)
  - FIND test_defaults_match_prd_4_5 (L38-47). Its current tail:
        assert cfg.asr.lite_model == "small.en"   # PRD §4.2ter: the single model loaded in lite mode
        ...
        assert cfg.asr.post_speech_silence_duration == 0.6
  - EDIT: add ONE line immediately after the post_speech assertion:
        assert cfg.asr.post_speech_silence_duration == 0.6
        assert cfg.asr.lite_post_speech_silence_duration == 0.5  # PRD §4.2ter: lite-mode silence threshold (snugger than 0.6)
  - WHY: pins the default 0.5 (CRITICAL #4 — distinct from post_speech's 0.6; a copy to 0.6 would fail this).
  - DO NOT: assert 0.6; add a standalone default test (the inline addition is the consistent choice).

Task 2: MODIFY tests/test_config.py — add the type-check assertion (test_field_types_are_tomllib_natural_types)
  - FIND test_field_types_are_tomllib_natural_types (L79-87). Its current relevant line:
        assert isinstance(cfg.asr.post_speech_silence_duration, float)  # 0.6, not int 0
  - EDIT: add ONE line immediately after it:
        assert isinstance(cfg.asr.post_speech_silence_duration, float)  # 0.6, not int 0
        assert isinstance(cfg.asr.lite_post_speech_silence_duration, float)  # 0.5, not int 0 (PRD §4.2ter)
  - WHY: pins the float type (tomllib parses `0.5` as float; a bare `1` would parse as int — this guards
    the default staying a float so the cfg_to_kwargs lite override + downstream float math hold).
  - DO NOT: assert int (the field is float-typed; int default would be a regression).

Task 3: ADD tests/test_config.py — the TOML round-trip test (mirrors test_lite_model_round_trips_through_toml)
  - PLACE: immediately after test_lite_model_wrong_type_raises (~L179), in the lite-mode config cluster.
  - ADD EXACTLY this function (mirrors the lite_model round-trip verbatim in shape):
        def test_lite_post_speech_silence_duration_round_trips_through_toml():
            """[asr] lite_post_speech_silence_duration parses from TOML and overrides the default (PRD §4.2ter)."""
            cfg = VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": 0.3}})
            assert cfg.asr.lite_post_speech_silence_duration == 0.3   # overridden (0.5 default -> 0.3)
  - WHY: 0.3 (≠ default 0.5) proves the override took effect, not a silent default fallback. Matches the
    lite_model round-trip's structure (override to a distinct value, assert equality).
  - DO NOT: override to 0.5 (== default — wouldn't prove the override parsed).

Task 4: ADD tests/test_config.py — the wrong-type rejection test (mirrors test_lite_model_wrong_type_raises)
  - PLACE: immediately after the Task-3 round-trip test (still in the lite-mode cluster).
  - ADD EXACTLY this function:
        def test_lite_post_speech_silence_duration_wrong_type_raises():
            """A non-numeric lite_post_speech_silence_duration is rejected at load (mirrors the
            post_speech_silence_duration numeric guard; bool/str/None/list all raise TypeError)."""
            for bad in [True, "0.5", None, [0.5]]:
                with pytest.raises(TypeError, match="lite_post_speech_silence_duration"):
                    VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": bad}})
  - WHY: the bad list is NON-NUMERIC only (CRITICAL #1 — int/float are accepted, so a bare int would NOT
    raise; bool is explicitly rejected via the isinstance(_v, bool) check first — CRITICAL #2). The match
    string is the field name (present in every bad-value message — CRITICAL #3).
  - DO NOT: use lite_model's bad list ([123, 1.5, ...]) — those are numeric and would NOT raise for a
    float field; do NOT match on the type name (varies per bad value); do NOT drop True (the bool gotcha
    is the load-bearing case).

Task 5: VALIDATE — run the Validation Loop L1–L3; fix until all green. No git commit unless the orchestrator
  directs it. If asked, message:
  "P1.M1.T2.S1: config unit tests for lite_post_speech_silence_duration (default/round-trip/wrong-type/type)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the float-field wrong-type loop (distinct from the string-field one). The __post_init__
# numeric validation accepts int OR float, rejects bool + everything else. So a FLOAT field's wrong-type
# bad list is NON-NUMERIC: [True, "0.5", None, [0.5]]. (A string field like lite_model uses a different
# list: [123, 1.5, True, None, [...]] — do NOT copy it.) bool is the load-bearing case (TOML `= true`).
for bad in [True, "0.5", None, [0.5]]:
    with pytest.raises(TypeError, match="lite_post_speech_silence_duration"):
        VoiceTypingConfig.from_toml({"asr": {"lite_post_speech_silence_duration": bad}})

# PATTERN 2 — match= the FIELD NAME. The TypeError f-string embeds {_name}, so the field name appears in
# every bad-value message regardless of the bad type. match="lite_post_speech_silence_duration" is stable
# across all four iterations. (Do NOT match the type name — it's bool/str/NoneType/list, varying.)

# PATTERN 3 — default + type live in the shared aggregate tests; round-trip + wrong-type are dedicated.
# test_defaults_match_prd_4_5 already aggregates ALL field defaults (lite_model is there); add the lite_post
# default there. test_field_types_are_tomllib_natural_types aggregates ALL type checks; add the isinstance
# there. The round-trip + wrong-type get their own dedicated tests (mirroring lite_model's pair).
```

### Integration Points

```yaml
TEST SUITE:
  - The 2 new tests + 2 new assertion lines join the existing tests/test_config.py suite. Run:
    `.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -v` -> 0 failures.
    T2.S1 only ADDS assertions/tests, so no existing test can regress.

DEPENDS ON (S1 — P1.M1.T1.S1, landing in parallel):
  - T2.S1's tests pass only because S1 added the field (config.py:59) + the validation-tuple entry
    (config.py:87). Both are ALREADY in the live tree (verified). If a future change reverts S1's
    config.py edits, T2.S1's default/round-trip tests fail with AttributeError — exactly the intended
    behavior. S1 (field+config.toml+drift guard) + T2.S1 (field unit tests) form a coverage pair.

DOWNSTREAM (P1.M2.T1 — wire the field into cfg_to_kwargs's lite override):
  - M2.T1 consumes lite_post_speech_silence_duration in cfg_to_kwargs (the lite override of
    post_speech_silence_duration). T2.S1's tests pin the field's contract (default/type/round-trip/
    validation) so M2.T1 can rely on it. T2.S1 does NOT touch cfg_to_kwargs (M2.T1 owns it).

NO INTERFACE CHANGES:
  - config.py, config.toml, daemon.py, ctl.py, recorder_host.py: UNCHANGED by T2.S1.
  - No runtime behavior change — test-only.
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST unit tests — NO GPU/models/daemon/network.
> No ruff/mypy configured. Run from `/home/dustin/projects/voice-typing`.

### Level 1: The edits are in place + the file parses + pytest discovers the new tests

```bash
cd /home/dustin/projects/voice-typing
echo "--- test_config.py parses ---"
.venv/bin/python -c "import ast; ast.parse(open('tests/test_config.py').read()); print('L1a PASS: parses')"
echo "--- the 2 new tests are discovered ---"
.venv/bin/python -m pytest tests/test_config.py --collect-only -q | grep -E 'lite_post_speech_silence_duration_(round_trips_through_toml|wrong_type_raises)' \
  && echo "L1b PASS: both new tests collected" || echo "L1b FAIL: a new test is missing"
echo "--- the 2 inline assertions are present ---"
grep -q 'lite_post_speech_silence_duration == 0.5' tests/test_config.py && echo "L1c PASS: default assert present" || echo "L1c FAIL"
grep -q 'isinstance(cfg.asr.lite_post_speech_silence_duration, float)' tests/test_config.py && echo "L1d PASS: type assert present" || echo "L1d FAIL"
# Expected: parses; both new tests collected; both inline assertions present.
```

### Level 2: The 4 deliverables pass (default + type + round-trip + wrong-type)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the 2 new tests PASS ---"
.venv/bin/python -m pytest tests/test_config.py -v \
  -k "lite_post_speech_silence_duration_round_trips or lite_post_speech_silence_duration_wrong_type" 2>&1 | tail -6
echo "--- the 2 aggregate tests (with the new inline asserts) PASS ---"
.venv/bin/python -m pytest tests/test_config.py -v -k "defaults_match_prd_4_5 or field_types_are_tomllib" 2>&1 | tail -6
# Expected: all 4 PASS. If wrong_type fails on a specific bad value: check CRITICAL #1 (a numeric value
# in the list would not raise) + CRITICAL #2 (bool must be rejected). If round_trip fails: the field may
# be absent from config.py (S1 regression — re-check config.py:59) or the override value == default.
```

### Level 3: No regression — full config suites green + scope clean

```bash
cd /home/dustin/projects/voice-typing
echo "--- full config suites (T2.S1's gate) ---"
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -v 2>&1 | tail -8
echo "--- broader sanity: no other suite broke ---"
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -4
echo "--- scope: ONLY tests/test_config.py changed ---"
git diff --name-only | grep -vxE 'tests/test_config.py' && echo "L3 FAIL: out-of-scope file changed" || echo "L3 PASS: only tests/test_config.py"
git diff --quiet voice_typing/config.py config.toml voice_typing/daemon.py tests/test_config_repo_default.py \
  && echo "L3 PASS: config.py/config.toml/daemon.py/repo-default-test unchanged" || echo "L3 FAIL: a source/sibling file was modified"
# Expected: both config suites 0 failures; broader suite green; diff = tests/test_config.py only;
# config.py/config.toml/daemon.py/test_config_repo_default.py unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `tests/test_config.py` parses; both new tests collected; both inline assertions present.
- [ ] L2: 2 new tests + 2 aggregate tests (with new asserts) PASS.
- [ ] L3: `pytest tests/test_config.py tests/test_config_repo_default.py` → 0 failures; broader suite green; diff = `tests/test_config.py` only.

### Feature Validation
- [ ] Default asserted `== 0.5` (not 0.6 — the snugger lite threshold).
- [ ] Type asserted `isinstance(..., float)`.
- [ ] Round-trip: `from_toml({...,0.3}) == 0.3` (override parsed, distinct from default).
- [ ] Wrong-type: `[True, "0.5", None, [0.5]]` each raise `TypeError(match="lite_post_speech_silence_duration")`.

### Code Quality Validation
- [ ] New tests mirror the `lite_model` pair's naming + structure (`_round_trips_through_toml` / `_wrong_type_raises`).
- [ ] Inline asserts placed next to their `post_speech_silence_duration` siblings in the aggregate tests.
- [ ] Wrong-type bad list is NON-NUMERIC only (int/float accepted; bool/str/None/list rejected) — CRITICAL #1.
- [ ] `match=` uses the field name (stable across all bad values) — CRITICAL #3.
- [ ] New tests placed in the lite-mode cluster (after `test_lite_model_wrong_type_raises`) — Gotcha #6.

### Scope Boundary Validation
- [ ] `voice_typing/config.py` unmodified (S1 owns the field + validation).
- [ ] `config.toml`, `voice_typing/daemon.py`, `tests/test_config_repo_default.py` unmodified.
- [ ] No `cfg_to_kwargs`/`recorder_host.py`/`ctl.py` changes (M2.T1 owns the wiring).
- [ ] No README/ACCEPTANCE edits (P1.M3 owns Mode B docs).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] (No user-facing docs — test-only subtask, contract §5 "DOCS: none".) The test docstrings are the durable explanation.
- [ ] If asked to commit: message references lite_post_speech_silence_duration config tests for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't use `lite_model`'s wrong-type bad list (`[123, 1.5, ...]`) for this FLOAT field — 123/1.5 are valid numbers and would NOT raise, making the test vacuous/wrong. Use NON-NUMERIC values only: `[True, "0.5", None, [0.5]]` (CRITICAL #1).
- ❌ Don't drop `True` from the bad list — bool is the load-bearing case (TOML `= true` → Python `True`), explicitly rejected via the `isinstance(_v, bool)` check (CRITICAL #2). `test_bool_for_float_field_raises` pins this for `post_speech_silence_duration`; mirror it.
- ❌ Don't `match=` the type name or value repr — they vary per bad value (bool/str/NoneType/list). Match the FIELD NAME (`lite_post_speech_silence_duration`), which is in every message via `{_name}` (CRITICAL #3).
- ❌ Don't assert the default is `0.6` — that's `post_speech_silence_duration`'s default. Lite's is `0.5` (snugger — §4.2ter). Asserting `0.5` catches a future copy-to-0.6 regression that would silently make lite feel like normal (CRITICAL #4).
- ❌ Don't override to `0.5` in the round-trip test — use a DISTINCT value (`0.3`) so the test proves the override parsed rather than silently falling back to the default.
- ❌ Don't edit `config.py`/`config.toml`/`test_config_repo_default.py` — S1 owns those. T2.S1 is `tests/test_config.py` ONLY (Gotcha #7).
- ❌ Don't add a standalone default test when the contract allows an inline addition to `test_defaults_match_prd_4_5` — the inline addition is the consistent choice (`lite_model` is already asserted there) (Gotcha #5).
- ❌ Don't place the new tests in the generic wrong-type section — put them in the lite-mode cluster after `test_lite_model_wrong_type_raises` (Gotcha #6).
- ❌ Don't use bare `python`/`pytest` or invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest` (Gotcha #8).

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a small, fully-specified test-only addition with copy-ready reference implementations mirroring four existing patterns verbatim. Every load-bearing fact is verified against the live repo: the field exists with default `0.5` (config.py:59) and is in the numeric-validation tuple (config.py:87); the validation rule accepts int/float and rejects bool/str/None/list with a message containing the field name (so `match=` works + the non-numeric bad list is correct); the four existing patterns (`test_defaults_match_prd_4_5`, `test_field_types_are_tomllib_natural_types`, `test_lite_model_round_trips_through_toml`, `test_lite_model_wrong_type_raises`) are read in full at their cited line numbers; and the no-conflict boundary with S1 (config.py/config.toml/test_config_repo_default.py vs tests/test_config.py) is explicit — plus S1's config.py field is already landed, so T2.S1's tests pass first run. The −0.5 is solely the small risk of a stale line number (the contract cites "~167/~174/~44-47/~82" and the file may shift if S1's parallel work touches it — but S1 owns different files, so tests/test_config.py is stable), mitigated by the L1 collection gate that fails fast if a new test isn't discovered.
