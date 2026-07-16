# PRP — P1.M1.T1.S1: Add `lite_post_speech_silence_duration` to AsrConfig + config.toml + repo-default test (atomic)

## Goal

**Feature Goal**: Add the `lite_post_speech_silence_duration` config knob (PRD §4.2ter / §4.5) — the snugger silence threshold lite mode overrides `post_speech_silence_duration` with so lite actually *feels* instant (the silence gate, not the model, is the perceived-latency bottleneck). This is the **foundational, atomic schema change**: the field, its default, its numeric validation, its config.toml mirror, and the drift-guard test's expected key set must ALL land in one commit or the drift-guard test fails.

**Deliverable**: Four atomic edits across three files:
1. `voice_typing/config.py` — `AsrConfig`: add `lite_post_speech_silence_duration: float = 0.5` after `post_speech_silence_duration`.
2. `voice_typing/config.py` — `AsrConfig.__post_init__`: add `"lite_post_speech_silence_duration"` to the numeric-fields validation tuple.
3. `config.toml` — `[asr]`: add `lite_post_speech_silence_duration = 0.5` after `post_speech_silence_duration = 0.6` (with the self-documenting comment).
4. `tests/test_config_repo_default.py` — add `"lite_post_speech_silence_duration"` to `expected["asr"]` and fix the stale count in the docstring.

**Success Definition**: (a) `VoiceTypingConfig().asr.lite_post_speech_silence_duration == 0.5`; (b) wrong-typed values raise `TypeError` at construction (`=True`/`="0.5"`); (c) the drift-guard test passes BOTH assertions (`test_repo_config_toml_equals_defaults` requires config.toml's `0.5` == the dataclass default `0.5`; `test_repo_config_toml_has_no_extra_keys` requires config.toml's `[asr]` key set == `expected["asr"]`); (d) only the three files above change.

## User Persona

**Target User**: The end user tuning lite mode via `config.toml` (the comment added in step 3 IS the user-facing doc — Mode A), and the downstream subtasks that consume the field: M2.T1.S1 (wire it into `cfg_to_kwargs`'s lite override) and T2.S1 (config unit tests).

**Use Case**: User wants lite mode to feel snappier → edits `lite_post_speech_silence_duration` in `config.toml` (e.g. `0.3`); or it's wrong-typed (`= "0.5"`) and the daemon fails fast at config load with a clear `TypeError` instead of silently breaking auto-stop-style logic at runtime.

**Pain Points Addressed**: Gives lite mode its own silence threshold (the load-bearing latency lever per §4.2ter); extends the existing numeric-type validation to the new field (bugfix Issue 4 hardening); keeps config.toml and the dataclass in lockstep via the drift guard.

## Why

- **PRD §4.2ter load-bearing:** "lite MUST use its own shorter `post_speech_silence_duration` (default `0.5`) … that is what makes lite actually FEEL instant, cutting stop→text latency from ~1.6 s to ~0.6 s." Without this knob existing in the schema, M2 cannot wire the override.
- **Atomicity is non-negotiable:** the repo drift-guard test (`test_repo_config_toml_equals_defaults`) asserts `from_toml_file(config.toml) == VoiceTypingConfig()`, and `test_repo_config_toml_has_no_extra_keys` asserts config.toml's `[asr]` key set EXACTLY equals `expected["asr"]`. Adding the field to the dataclass without mirroring it in config.toml (same default), or adding it to config.toml without the expected-set update, fails one of these. All four edits are one commit.
- **Validation parity:** the existing numeric fields reject bool/non-numeric at load (bugfix Issue 4). The new field must join that tuple so `lite_post_speech_silence_duration = True` or `= "0.5"` raises `TypeError` at construction — mirroring `post_speech_silence_duration`.
- **Foundational + low-risk:** pure schema addition with a default; no behavior changes yet (the field is unused until M2 wires it). No daemon logic, no models, no socket — just config plumbing.

## What

Add one float field (`0.5`) to `AsrConfig`, register it in the numeric-validation tuple, mirror it in `config.toml` with a self-documenting comment, and update the drift-guard test's expected `[asr]` key set + docstring. No daemon wiring (M2), no dedicated field unit tests (T2), no README (M3) — those are sibling subtasks.

### Success Criteria

- [ ] `AsrConfig.lite_post_speech_silence_duration` exists, type `float`, default `0.5`.
- [ ] It is in the `__post_init__` numeric validation tuple (rejects bool/non-numeric).
- [ ] `config.toml` `[asr]` has `lite_post_speech_silence_duration = 0.5` with the §4.2ter comment.
- [ ] `tests/test_config_repo_default.py` `expected["asr"]` includes the key; docstring count is accurate.
- [ ] Both drift-guard assertions PASS; the value `0.5` is identical in config.py and config.toml.
- [ ] Only `config.py`, `config.toml`, `test_config_repo_default.py` change.

## All Needed Context

### Context Completeness Check

_Pass._ All four edit sites are quoted verbatim below with exact current line numbers (re-verified). The drift-guard test's two assertions, the exact `expected` dict structure, the verbatim config.toml `[asr]` block, and the empirical current key count (19 → 20) are all confirmed. An agent new to this codebase can apply the four edits from this PRP alone.

### Verified Current State (re-verified — field is absent everywhere)

`grep -rn lite_post_speech_silence voice_typing/ tests/ config.toml` → no matches. Clean addition.

**`voice_typing/config.py` — `AsrConfig` (lines 49-65, 9 fields):**
```python
class AsrConfig:
    """[asr] — ASR model + device settings. `device` may be overridden by cuda_check."""
    final_model: str = "distil-large-v3"
    realtime_model: str = "small.en"
    lite_model: str = "small.en"            # PRD §4.2ter: the SINGLE model loaded in lite mode
                                          # (used for both partials + finals; large model never loads)
    language: str = "en"
    device: str = "cuda"  # "cuda" | "cpu" (daemon may override via cuda_check at startup)
    post_speech_silence_duration: float = 0.6  # VAD: finalize after this much silence (seconds)
    realtime_processing_pause: float = 0.15    # partials cadence (seconds)
    auto_stop_idle_seconds: float = 30.0       # ...
    auto_unload_idle_seconds: float = 1800.0   # ...
```
`__post_init__` numeric tuple (lines 80-85):
```python
        for _name in (
            "post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",
        ):
```

**`config.toml` — `[asr]` (lines 37-38 are the insertion point):**
```
post_speech_silence_duration = 0.6                 # seconds of silence after speech before a final is emitted. ...
realtime_processing_pause    = 0.15                # seconds between live partial updates. ...
```

**`tests/test_config_repo_default.py` (full, 2 tests):**
- `test_repo_config_toml_equals_defaults`: `assert from_toml_file(config.toml) == VoiceTypingConfig()` — requires config.toml's `0.5` to equal the dataclass default `0.5`.
- `test_repo_config_toml_has_no_extra_keys`: builds an `expected = {"asr": {...9 keys...}, "output": {...}, ...}` and asserts `set(data[section].keys()) == keys` per section. The `expected["asr"]` set currently has 9 keys; the docstring says "17 schema keys" (**already STALE** — the actual total is 19, confirmed empirically).

**Empirical key count (verified this session):** config.toml has **19** keys total (asr 9, output 3, feedback 4, filter 2, log 1). After this edit: **20** (asr 10). The docstring's "17" is wrong NOW; do NOT follow the contract's "17→18" — use the verified-correct **20** (see Gotcha #5).

### Documentation & References

```yaml
# THE LINE-NUMBER REFERENCE DOC (corroborates the contract)
- docfile: plan/005_723f4c529eea/architecture/daemon_analysis.md
  why: "Config Schema — AsrConfig" section gives the exact 9 current fields + the required addition
       (`lite_post_speech_silence_duration: float = 0.5  # PRD §4.2ter`) and confirms it must join the
       __post_init__ numeric tuple. (Its cfg_to_kwargs section is M2's scope, NOT S1's.)
  critical: "daemon_analysis.md prescribes the field default (0.5) + the validation-tuple addition.
            S1 does ONLY the schema/test; the cfg_to_kwargs override it also describes is M2.T1.S1."

# THE FIX SITES
- file: voice_typing/config.py
  why: AsrConfig (49) holds the schema; __post_init__ (66) validates numeric types. Add the field
        after post_speech_silence_duration (58) and the name to the numeric tuple (80-85).
  pattern: "Mirror post_speech_silence_duration exactly: `: float = <default>` + inline `# PRD §4.2ter`
            comment, and one entry in the numeric `for _name in (...)` tuple."
  gotcha: "The DEFAULT (0.5) MUST equal config.toml's value (0.5) or the equals-defaults test fails."

- file: config.toml
  why: The [asr] block (30-40) mirrors AsrConfig field-for-field (the drift guard enforces it). Add the
        key after post_speech_silence_duration (37) with the self-documenting comment (Mode A doc).
  pattern: "Every line is `key = value  # comment`. Comments are the user-facing field docs."
  gotcha: "lite_post_speech_silence_duration (33 chars) is LONGER than the block's `=` alignment
           column (set by post_speech_silence_duration, 29 chars). Use a SINGLE space before `=` —
           do NOT realign the whole block. This matches the PRD §4.5 canonical form
           (`lite_post_speech_silence_duration = 0.5`)."

- file: tests/test_config_repo_default.py
  why: The permanent drift guard. expected['asr'] (33-43) must EXACTLY equal config.toml's [asr] keys,
        so adding the key to config.toml REQUIRES adding it to expected['asr'] in the same commit.
  pattern: "expected is `{section: set(keys)}`; assertions are set-equality per section + on the
            section-name set. Add the key to expected['asr']; the docstring count is informational."
  critical: "The docstring count is NOT asserted — but keep it accurate. Verified actual: 19 now → 20
            after. (The contract said 17→18; that baseline was stale — use 20.)"

# PRD CONTEXT
- docfile: plan/005_723f4c529eea/prd_snapshot.md
  why: §4.2ter ("lite MUST use its own shorter post_speech_silence_duration, default 0.5") and §4.5
        (the config.toml block already shows `lite_post_speech_silence_duration = 0.5` as canonical)
        are the spec basis + the exact default + comment phrasing.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/config.py                       # AsrConfig @49 (9 fields); __post_init__ numeric tuple @80  ← EDIT (field + tuple)
├── config.toml                                  # [asr] @30; post_speech_silence_duration @37  ← EDIT (add key after)
└── tests/test_config_repo_default.py            # expected["asr"] set @33; "17 schema keys" docstring @28  ← EDIT (key + count)
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/config.py                  # MODIFY: +1 field (after post_speech_silence_duration) +1 name in numeric tuple
config.toml                             # MODIFY: +1 key/value/comment line (after post_speech_silence_duration)
tests/test_config_repo_default.py       # MODIFY: +1 key in expected["asr"] + docstring count 17→20
# NO other files. NO daemon.py wiring (M2), NO test_config.py unit tests (T2), NO README (M3).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ATOMIC. All four edits land in ONE commit. The drift-guard test
# test_repo_config_toml_equals_defaults asserts from_toml_file(config.toml) == VoiceTypingConfig();
# test_repo_config_toml_has_no_extra_keys asserts config.toml's [asr] keys == expected["asr"] exactly.
# Field-without-config.toml (or a different value) fails the first; config.toml-without-expected-key
# fails the second. Edit config.py + config.toml + the test together.

# CRITICAL #2 — DEFAULT MUST MATCH. AsrConfig default 0.5 and config.toml value 0.5 must be IDENTICAL
# (same float). 0.5 == 0.5 → True. If you set one to 0.50 and the other to 0.5, TOML parses both to
# the float 0.5, so still equal — but keep them literally "0.5" in both for clarity.

# CRITICAL #3 — VALIDATION TUPLE, not the string tuple. AsrConfig.__post_init__ has TWO loops: a
# NUMERIC tuple (post_speech_silence_duration, realtime_processing_pause, auto_stop_idle_seconds,
# auto_unload_idle_seconds) and a STRING tuple (final_model, realtime_model, lite_model, language,
# device). lite_post_speech_silence_duration is a FLOAT → add it to the NUMERIC tuple only. Adding it
# to the string tuple would wrongly reject the valid float 0.5.

# CRITICAL #4 — config.toml ALIGNMENT. lite_post_speech_silence_duration (33 chars) exceeds the
# block's `=` column (set by post_speech_silence_duration, 29 chars). Use a SINGLE space before `=`
# for this line (matches PRD §4.5 canonical). Do NOT realign the whole [asr] block — that's a bigger
# diff and the drift guard is value/key-based, not whitespace-based (so single-space is safe).

# CRITICAL #5 — DOCSTRING COUNT: use 20, NOT the contract's "18". The docstring currently says
# "17 schema keys" but the ACTUAL verified count is 19 (asr 9 + output 3 + feedback 4 + filter 2 +
# log 1). The contract's "17→18" was based on a stale baseline. After adding this field the actual
# count is 20 (asr 10). The docstring is NOT asserted by any test, but keep it accurate → "20".

# GOTCHA #6 — PLACEMENT after post_speech_silence_duration. The contract (and §4.2ter's symmetry:
# lite's knob is the lite analogue of the normal post_speech_silence_duration) both want it adjacent.
# In config.py it goes field-after-field; in config.toml line-after-line; in the validation tuple
# name-after-name. Keeps the diff coherent and the analogy obvious.

# GOTCHA #7 — SCOPE. S1 is SCHEMA + DRIFT GUARD only. Do NOT wire the field into cfg_to_kwargs
# (that's M2.T1.S1: `kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration`
# in the lite branch). Do NOT add test_config.py unit tests for the field (T2.S1). Do NOT touch
# README/ACCEPTANCE (M3). The field is intentionally UNUSED after S1 — that's correct (M2 consumes it).

# GOTCHA #8 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# pytest/one-off gates. No ruff/mypy in this project.
```

## Implementation Blueprint

### Data models and structure

The data model change IS this task: one new `float` field on the `AsrConfig` dataclass (`lite_post_speech_silence_duration: float = 0.5`), validated as numeric in `__post_init__`. No other model/schema change.

### Implementation Tasks (ordered by dependencies — all atomic, one commit)

```yaml
Task 1: EDIT voice_typing/config.py — add the AsrConfig field.
  - FIND (line 58):
        post_speech_silence_duration: float = 0.6  # VAD: finalize after this much silence (seconds)
        realtime_processing_pause: float = 0.15    # partials cadence (seconds)
  - INSERT the new field between them:
        post_speech_silence_duration: float = 0.6  # VAD: finalize after this much silence (seconds)
        lite_post_speech_silence_duration: float = 0.5  # PRD §4.2ter: lite-mode silence threshold —
                                                       # the silence gate, not the model, is the
                                                       # perceived-latency bottleneck (see §4.2ter).
                                                       # 0.3 = razor-snappy (may split a brief pause);
                                                       # 0.6 = safe.
        realtime_processing_pause: float = 0.15    # partials cadence (seconds)

Task 2: EDIT voice_typing/config.py — add to the __post_init__ NUMERIC validation tuple.
  - FIND (lines 80-85):
        for _name in (
            "post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",
        ):
  - REPLACE WITH (one new line after post_speech_silence_duration):
        for _name in (
            "post_speech_silence_duration",
            "lite_post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",
        ):
  - DO NOT add it to the STRING tuple (line ~93). It is a float → numeric tuple only (Gotcha #3).

Task 3: EDIT config.toml — add the [asr] key + self-documenting comment (Mode A doc).
  - FIND (lines 37-38):
        post_speech_silence_duration = 0.6                 # seconds of silence after speech before a final is emitted. Lower = snappier but can cut off pauses; higher = fewer false finals but slower.
        realtime_processing_pause    = 0.15                # seconds between live partial updates. Lower = more responsive status; higher = less CPU.
  - INSERT between them (single space before `=` — Gotcha #4; value MUST be 0.5 — Gotcha #2):
        post_speech_silence_duration = 0.6                 # seconds of silence after speech before a final is emitted. Lower = snappier but can cut off pauses; higher = fewer false finals but slower.
        lite_post_speech_silence_duration = 0.5            # PRD §4.2ter: lite-mode silence threshold (the silence gate, not the model, is the perceived-latency bottleneck). 0.3 = razor-snappy (may split a brief pause); 0.6 = safe.
        realtime_processing_pause    = 0.15                # seconds between live partial updates. Lower = more responsive status; higher = less CPU.

Task 4: EDIT tests/test_config_repo_default.py — expected["asr"] key + docstring count.
  - (a) In expected["asr"] (the set literal ~lines 34-43), add "lite_post_speech_silence_duration"
        immediately after "post_speech_silence_duration":
            "post_speech_silence_duration",
            "lite_post_speech_silence_duration",   # PRD §4.2ter: lite-mode silence threshold
            "realtime_processing_pause",
  - (b) Fix the docstring of test_repo_config_toml_has_no_extra_keys: change "17 schema keys" to
        "20 schema keys" (verified actual: 19 now → 20 after; NOT "18" — Gotcha #5).

Task 5: VALIDATE (run the gates below — all four edits must be in place or L2 fails). No git commit
  unless the orchestrator directs it; if it does, the four edits are ONE commit (atomicity, Gotcha #1).
  Suggested message: "P1.M1.T1.S1: add lite_post_speech_silence_duration to AsrConfig + config.toml + drift guard".
```

### Implementation Patterns & Key Details

```python
# The whole task is: one float field + one tuple entry + one TOML line + one test-set entry.
# Correctness rests on TWO invariants the drift guard enforces:
#   (1) config.toml value (0.5) == dataclass default (0.5)   [test_repo_config_toml_equals_defaults]
#   (2) config.toml [asr] keys == expected["asr"] keys        [test_repo_config_toml_has_no_extra_keys]
# Both hold iff all four edits land together with value 0.5 on both sides.
#
# The __post_init__ numeric tuple edit means: AsrConfig(lite_post_speech_silence_duration=True)
# raises TypeError ("expects a number (int or float), got bool: True"), and = "0.5" raises TypeError
# ("got str"). This mirrors post_speech_silence_duration — the bugfix-Issue-4 hardening. (Dedicated
# unit tests for these are T2.S1; L3 below is a one-off confirmation.)
#
# The field is UNUSED after S1 — that's intended. M2.T1.S1 wires it into cfg_to_kwargs's lite branch:
#   kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration
# (per daemon_analysis.md). Do NOT add that wiring here.
```

### Integration Points

```yaml
CONFIG SCHEMA (voice_typing/config.py):
  - AsrConfig gains its 10th field. from_toml() / load() accept the new key; unknown-key rejection
    is unaffected (the key is now KNOWN). __post_init__ validates it as numeric.

CONFIG FILE (config.toml):
  - The [asr] block mirrors the new field (the drift guard enforces exact mirror). The comment IS the
    user-facing doc (Mode A). install.sh copies this config.toml to XDG, so users get the knob + doc.

DOWNSTREAM CONSUMERS (sibling subtasks — NOT S1):
  - M2.T1.S1 (daemon wiring): cfg_to_kwargs lite branch sets kwargs["post_speech_silence_duration"] =
    cfg.asr.lite_post_speech_silence_duration. S1 makes that attribute exist; M2 uses it.
  - T2.S1 (config unit tests): adds default/round-trip/wrong-type/type-check tests for the field in
    tests/test_config.py. S1's __post_init__ tuple edit is what makes T2's wrong-type test pass.
  - M3.T1.S1 (README) / M3.T1.S2 (ACCEPTANCE): document the knob + criterion #10. Not S1.

DRIFT GUARD (tests/test_config_repo_default.py):
  - This test is the reason the change is ATOMIC. After S1 it asserts the new 10-key [asr] set and
    the 0.5==0.5 value equality. Future schema changes must update all four sites the same way.
```

## Validation Loop

> Full paths for python (machine aliases python3->uv run). No ruff/mypy. The drift-guard test (L2) is
> the load-bearing gate — it transitively proves all four edits are consistent. L3 is a one-off
> functional check (T2 commits the dedicated unit tests).

### Level 1: All four edits are present (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- config.py: field exists, default 0.5 ---"
grep -n 'lite_post_speech_silence_duration: float = 0.5' voice_typing/config.py && echo "L1a PASS" || echo "L1a FAIL"
echo "--- config.py: in the NUMERIC validation tuple (and NOT a duplicate) ---"
test "$(grep -c '"lite_post_speech_silence_duration"' voice_typing/config.py)" -eq 2 && echo "L1b PASS (field decl + tuple entry = 2)" || echo "L1b CHECK: count=$(grep -c '"lite_post_speech_silence_duration"' voice_typing/config.py)"
echo "--- config.toml: key present, value 0.5 ---"
grep -n '^lite_post_speech_silence_duration = 0.5' config.toml && echo "L1c PASS" || echo "L1c FAIL"
echo "--- test_config_repo_default.py: expected[asr] has the key; docstring says 20 ---"
grep -q '"lite_post_speech_silence_duration"' tests/test_config_repo_default.py && echo "L1d PASS" || echo "L1d FAIL"
grep -q '20 schema keys' tests/test_config_repo_default.py && echo "L1e PASS (docstring=20)" || echo "L1e CHECK (docstring count)"
# Expected: L1a–L1e PASS. (L1b: exactly 2 occurrences — the field declaration and the tuple entry.)
```

### Level 2: The drift-guard test passes BOTH assertions (the atomicity gate)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_config_repo_default.py -v 2>&1 | tail -8
# Expected: 2 passed:
#   test_repo_config_toml_equals_defaults   (config.toml 0.5 == default 0.5; no drift)
#   test_repo_config_toml_has_no_extra_keys (config.toml [asr] 10 keys == expected["asr"] 10 keys)
# If the first FAILS: the config.toml value != the dataclass default (Gotcha #2).
# If the second FAILS: expected["asr"] and config.toml [asr] disagree (Task 4 vs Task 3 mismatch).
```

### Level 3: Field accessible + numeric validation works (one-off; T2 commits the unit tests)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from dataclasses import replace
from voice_typing.config import VoiceTypingConfig, AsrConfig
cfg = VoiceTypingConfig()
assert cfg.asr.lite_post_speech_silence_duration == 0.5, cfg.asr.lite_post_speech_silence_duration
print("L3a PASS: default == 0.5")
# wrong types raise TypeError at construction (the numeric-tuple edit):
for bad in (True, "0.5"):
    try:
        AsrConfig(lite_post_speech_silence_duration=bad)
        print(f"L3b FAIL: {bad!r} did NOT raise")
    except TypeError:
        print(f"L3b PASS: {bad!r} -> TypeError (as expected)")
# config.toml round-trips the value (drift guard already covers equality; this confirms attribute):
from voice_typing.config import from_toml_file if False else None  # placeholder
import tomllib
from voice_typing.config import _repo_config_path
with open(_repo_config_path(), "rb") as fh:
    raw = tomllib.load(fh)
assert raw["asr"]["lite_post_speech_silence_duration"] == 0.5
print("L3c PASS: config.toml carries lite_post_speech_silence_duration = 0.5")
PY
# Expected: L3a/L3b(×2)/L3c PASS. (Wrong-type rejection is the bugfix-Issue-4 parity; T2 commits a
# dedicated test in tests/test_config.py.)
```

### Level 4: Scope — only the three files changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY config.py + config.toml + test_config_repo_default.py ---"
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/config\.py|config\.toml|tests/test_config_repo_default\.py' | grep -E '\.py$|\.toml$|\.md$|systemd/|tests/' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: only the 3 schema files"
# Expected: "only the 3 schema files". daemon.py (M2), tests/test_config.py (T2), README (M3) absent.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1a: `lite_post_speech_silence_duration: float = 0.5` in AsrConfig.
- [ ] L1b: exactly 2 `"lite_post_speech_silence_duration"` occurrences in config.py (decl + numeric tuple), 0 in the string tuple.
- [ ] L1c: `lite_post_speech_silence_duration = 0.5` in config.toml `[asr]`.
- [ ] L1d/L1e: expected `["asr"]` has the key; docstring says "20 schema keys".
- [ ] L2: drift-guard test 2/2 PASS (the atomicity proof).
- [ ] L3: default 0.5; `True`/`"0.5"` raise TypeError; config.toml raw value 0.5.
- [ ] L4: only `config.py`, `config.toml`, `test_config_repo_default.py` changed.

### Feature Validation
- [ ] `VoiceTypingConfig().asr.lite_post_speech_silence_duration == 0.5`.
- [ ] Numeric validation rejects bool/str (mirrors `post_speech_silence_duration`).
- [ ] config.toml and dataclass default agree (0.5 == 0.5); `[asr]` key set matches `expected["asr"]`.

### Code Quality Validation
- [ ] Field placed adjacent to `post_speech_silence_duration` in all three sites (coherent analogy).
- [ ] config.toml comment is self-documenting (Mode A) and matches the contract's phrasing.
- [ ] Docstring count is accurate (20, not the stale 17 or the contract's 18).

### Scope Boundary Validation
- [ ] No `daemon.py` / `cfg_to_kwargs` edit (M2.T1.S1 wires the override).
- [ ] No `tests/test_config.py` field unit tests (T2.S1).
- [ ] No README / ACCEPTANCE.md (M3).
- [ ] All four edits in ONE commit (atomicity — the drift guard demands it).

---

## Anti-Patterns to Avoid

- ❌ Don't land a partial change (e.g. config.py without config.toml, or config.toml without the test's expected set) — the drift-guard test fails on the mismatch. All four edits are one commit.
- ❌ Don't set the default to anything other than `0.5` in either config.py or config.toml — they must be IDENTICAL or `test_repo_config_toml_equals_defaults` fails.
- ❌ Don't add the field to the STRING validation tuple — it's a float; it goes in the NUMERIC tuple (else the valid `0.5` is wrongly rejected).
- ❌ Don't realign the whole `[asr]` block in config.toml to fit the longer name — use a single space before `=` on this line (matches PRD §4.5 canonical); the drift guard is value/key-based, not whitespace-based.
- ❌ Don't use the contract's "18" for the docstring — the verified actual is 19 now → 20 after (the "17" was already stale). Use 20.
- ❌ Don't wire the field into `cfg_to_kwargs` here — that's M2.T1.S1; S1 leaves the field intentionally unused.
- ❌ Don't add `tests/test_config.py` unit tests for the field here — that's T2.S1. S1 updates only the drift-guard test (which MUST be updated atomically with the schema).
- ❌ Don't reorder existing fields — insert adjacent to `post_speech_silence_duration`; keep the diff minimal.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is four small, verbatim edits at re-confirmed locations, with the drift-guard test (L2) serving as a strict atomicity oracle: it fails loudly if any of the four edits is missing or inconsistent (value mismatch → first assertion; key-set mismatch → second assertion). The default value (0.5), the validation tuple (numeric, not string), the config.toml alignment (single space), and the empirical key count (19→20) are all verified. The −0.5 is the standard "moving tree" caveat: if a concurrent change touched AsrConfig / config.toml / the drift-guard test, the agent must re-confirm the exact oldText before applying (the L1/L2 gates catch any mismatch).
