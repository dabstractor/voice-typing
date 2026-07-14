# PRP — P1.M3.T1.S1: `__post_init__` type validation for AsrConfig (+ FeedbackConfig.notify_ms)

## Goal

**Feature Goal**: Make wrong-typed config values fail FAST at load time with a clear `TypeError`, instead of loading silently and breaking the feature at runtime. Today `auto_stop_idle_seconds = "thirty"` (a str) loads into `AsrConfig` with no error; at runtime `time.monotonic() - ts < "thirty"` raises `TypeError`, which the `_idle_watchdog` swallows → auto-stop silently dies (and `auto_unload_idle_seconds` would silently disable idle-unload the same way). Fix = an `isinstance`-based `__post_init__` on `AsrConfig` (all 8 fields) + `FeedbackConfig.notify_ms`, raising `TypeError` at construction (= load time, when `from_toml` calls `AsrConfig(**section)`). Bugfix Issue 4 (Minor); PRD §4.5 robustness.

**Deliverable** (edits to `voice_typing/config.py` + `config.toml`; no new files, no test files):
1. `config.py` — `AsrConfig.__post_init__`: validate the 4 float fields (`post_speech_silence_duration`, `realtime_processing_pause`, `auto_stop_idle_seconds`, `auto_unload_idle_seconds`) as int-or-float-but-NOT-bool; validate the 4 str fields (`final_model`, `realtime_model`, `language`, `device`) as str; raise `TypeError(f"[asr] {field} expects ..., got {type}: {value!r}")` on mismatch.
2. `config.py` — `FeedbackConfig.__post_init__`: validate `notify_ms` as int (not bool, not float); raise `TypeError(f"[feedback] notify_ms expects int, got {type}: {value!r}")`.
3. `config.toml` — [Mode A] append one sentence to the "Unknown keys are REJECTED" comment noting wrong-typed values are also rejected at load.

**Success Definition**:
- (a) `AsrConfig()` (defaults) constructs with NO error; `AsrConfig(**{"auto_stop_idle_seconds": 30.0})` and `AsrConfig(**{"auto_stop_idle_seconds": 30})` (int) construct fine; `AsrConfig(**{"auto_stop_idle_seconds": "thirty"})` raises `TypeError` whose message names `auto_stop_idle_seconds` and the bad value `'thirty'`.
- (b) `AsrConfig(**{"device": 1})` (int where str expected) raises `TypeError` naming `device`.
- (c) `AsrConfig(**{"auto_stop_idle_seconds": True})` (bool where float expected) raises `TypeError` (bool is an int subclass but is rejected).
- (d) `FeedbackConfig()` (default notify_ms=2500) constructs fine; `FeedbackConfig(**{"notify_ms": 2500.0})` (float) and `FeedbackConfig(**{"notify_ms": True})` (bool) raise `TypeError` naming `notify_ms`.
- (e) `VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})` raises `TypeError` (propagates from `AsrConfig(**section)` → fail-fast at LOAD time, before models load, before systemd loops) — the daemon's config load does not catch/swallow it.
- (f) `<repo>/config.toml` still parses to NO overrides over the defaults (the drift guard `test_repo_config_toml_equals_defaults` stays green — all repo values are correctly typed).
- (g) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (no regression; the existing `AsrConfig`/`FeedbackConfig` constructions all use correct types).
- (h) No out-of-scope files: NO test files (the wrong-type pytest is P1.M3.T1.S2), no daemon.py/feedback.py/ctl.py/README, no PRD.md/tasks.json/prd_snapshot.md/.gitignore/pyproject.toml/uv.lock. No new deps.

## User Persona

**Target User**: the operator who hand-edits `~/.config/voice-typing/config.toml` and fat-fingers a value (e.g. quotes a number, or copies a `2500.0` where an int is expected).

**Use Case**: `auto_stop_idle_seconds = "thirty"` in config.toml. Today the daemon boots, arms, and silently never auto-stops (only a repeating TypeError traceback in the journal gives a clue). After this fix: `systemctl --user restart voice-typing` fails immediately with `[asr] auto_stop_idle_seconds expects a number (int or float), got str: 'thirty'` — the user corrects the value and restarts.

**Pain Points Addressed**: a silent feature break with an obscure journal traceback → a loud, load-time error naming the exact field and bad value, exactly when the user is editing config.

## Why

- **Closes a silent-failure robustness gap (PRD §4.5 spirit).** §4.5 already promises "Unknown keys raise TypeError … a typo'd config key surfaces loudly." A wrong-TYPED value is the same class of user error but today surfaces as a silent runtime break. This makes the loud-failure promise cover types too.
- **Cheap, surgical, fail-fast.** Two `__post_init__` methods (isinstance checks, no new deps, no coercion that could mask a value). The error surfaces at `from_toml` → `AsrConfig(**section)`, i.e. at daemon load — before models load, before systemd `Restart=on-failure` can loop it. The user sees the message on the journal line immediately.
- **Consistent with the existing rejection.** Unknown keys already raise `TypeError` (dataclass `__init__`). Wrong types raising `TypeError` too means a single `except`/message style covers both user-error classes; the daemon's config-load path already propagates `TypeError` (it does not catch it).
- **The bool gotcha is real and tested.** `isinstance(True, int)` is `True`; without the explicit bool rejection, `auto_stop_idle_seconds = true` (a TOML bool) would pass validation and break at runtime. The fix rejects bool explicitly.

## What

Add `__post_init__` to `AsrConfig` (validate 4 float fields as int|float-not-bool + 4 str fields as str) and to `FeedbackConfig` (validate `notify_ms` as int-not-bool-not-float). Both raise `TypeError` with a message naming the section, field, expected type, and bad value. Append one sentence to the config.toml schema comment noting wrong-typed values are also rejected. No coercion (a wrong type is a user error to surface, not silently convert).

### Success Criteria

- [ ] `AsrConfig.__post_init__` exists; `AsrConfig()` (defaults) constructs with no error.
- [ ] `AsrConfig` rejects: a str/None/bool/list for any float field; a non-str for any str field. Accepts int and float for float fields; str for str fields.
- [ ] bool is rejected for float fields (`isinstance(True, int)` is True, but bool is not valid here).
- [ ] `FeedbackConfig.__post_init__` validates `notify_ms`: accepts int, rejects bool and float (and str/None).
- [ ] The `TypeError` messages match `f"[asr] {field} expects ..., got {type(value).__name__}: {value!r}"` / `f"[feedback] notify_ms expects int, got {type(value).__name__}: {value!r}"`.
- [ ] `VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})` raises `TypeError` (propagates from construction).
- [ ] `<repo>/config.toml` parses to equal the defaults (drift guard green); `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] config.toml schema comment notes wrong-typed values are rejected at load.
- [ ] Only `voice_typing/config.py` + `config.toml` modified (`git status --short`).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the research note: the root cause + the chosen approach (bug_analysis "Approach B-lite") are documented; the bool gotcha (`isinstance(True, int)`) and the exact validate idioms are pinned; every field + expected type is listed; the regression scan (no existing construction breaks) is verified; every edit is byte-exact oldText→newText against the current file; and the validation commands are executable as written.

### Documentation & References

```yaml
# MUST READ — root cause, chosen approach, the bool gotcha, the regression scan, scope
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M3T1S1/research/config_type_validation.md
  why: "§1 root cause (from_toml **section -> no type check -> silent runtime break) + the chosen
        Approach B-lite (__post_init__ + isinstance + TypeError). §2 THE BOOL GOTCHA (isinstance(True,
        int) is True -> reject bool FIRST). §3 the 8 AsrConfig fields + notify_ms + expected types +
        the validate idioms. §4 the regression scan (every existing AsrConfig/FeedbackConfig construction
        uses correct types -> S1 touches NO test files). §5 the parallel task is disjoint. §6 the
        config.toml doc edit. §7 tooling/scope."
  section: "ALL load-bearing. §2 (bool gotcha), §3 (fields/idioms), §4 (no test edits in S1)."

# MUST READ — the file being edited (AsrConfig + FeedbackConfig + the exact edit anchors)
- file: voice_typing/config.py
  why: "AsrConfig (lines 49-66): add __post_init__ after auto_unload_idle_seconds (the last field).
        FeedbackConfig (~73): add __post_init__ after notify_on_final / before resolved_state_file,
        validating notify_ms ONLY. from_toml._overlay does section_cls(**section) -> __post_init__ runs
        at load; TypeError propagates (not caught). Defaults are all correctly typed -> pass."
  critical: "Reject bool FIRST in each numeric check (isinstance(v, bool) or not isinstance(v, ...)).
             Validate ONLY notify_ms in FeedbackConfig (NOT state_file/hypr_notify/notify_on_final — out
             of scope). Reproduce the §/✔/●/■ Unicode in oldText EXACTLY where the anchor includes it
             (the chosen anchors AVOID those lines — see Edits)."

# MUST READ — the config.toml doc-edit anchor (the 'Unknown keys are REJECTED' comment)
- file: config.toml
  why: "The SCHEMA SOURCE comment (~line 25-28) is the [Mode A] doc surface. Append one ASCII sentence
        noting wrong-typed values are also rejected at load. Anchor: the '(a typo raises an error
        instead of being silently ignored).' line (unique)."
  critical: "Keep the new text ASCII (no em-dash) to avoid Unicode reproduction issues. The line is the
             doc (item DOCS) — keep it terse + match the surrounding comment voice."

# MUST READ — the bug-analysis root cause + the recommended approach (READ-ONLY context)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 4 (line 166+): the from_toml(**section) no-type-check root cause + 'Recommended:
        Approach B-lite — Add __post_init__ to AsrConfig that validates float fields with isinstance,
        raising TypeError on mismatch.' Confirms the approach the item prescribes."
  critical: "Do NOT edit the bug_analysis (READ-ONLY research). Approach A (coercion via float()) is
             NOT chosen — do NOT coerce; a wrong type is a user error to SURFACE, not silently convert."

# CONTEXT — the parallel task contract (DISJOINT; confirms config.py is NOT edited by it)
- file: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S3/PRP.md
  why: "P1.M2.T2.S3 is a TEST-ONLY task (child-crash-recovery tests in a new test file); its PRP
        explicitly lists config.py under UNCHANGED / 'do NOT edit config.py'. Zero overlap with S1.
        Its FeedbackConfig(...) constructions use correct types (notify_ms omitted/int) -> unaffected."
  critical: "No conflict. S1 edits config.py + config.toml; P1.M2.T2.S3 edits a new test file only."

# CONTEXT — the PRD (the robustness promise) — READ-ONLY
- docfile: PRD.md
  why: "§4.5: 'Unknown keys raise TypeError ... a typo surfaces loudly.' Issue 4 extends the same
        loud-failure promise to wrong TYPES."
  critical: "Do NOT edit PRD.md (forbidden)."
```

### Current Codebase tree (state at P1.M3.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── config.py     # <-- EDIT: AsrConfig.__post_init__ + FeedbackConfig.__post_init__ (notify_ms).
└── config.toml       # <-- EDIT: append one sentence to the SCHEMA SOURCE comment.
# NO test files edited in S1 (the wrong-type pytest is P1.M3.T1.S2). NO other source files.
```

### Desired Codebase tree with files to be added

```bash
voice_typing/config.py   # MODIFIED: +AsrConfig.__post_init__ (8 fields) + FeedbackConfig.__post_init__ (notify_ms).
config.toml             # MODIFIED: +1 sentence in the SCHEMA SOURCE comment (wrong-typed values rejected).
# NOTHING ELSE. No new files. No tests (S2). No daemon/feedback/ctl/README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE BOOL GOTCHA. isinstance(True, int) is True (bool subclasses int). A naive
#   `isinstance(value, int)` accepts True/False for a numeric field. The validate rule MUST reject
#   bool FIRST: `if isinstance(v, bool) or not isinstance(v, (int, float))` for float fields; `if
#   isinstance(v, bool) or not isinstance(v, int)` for notify_ms. TOML `true`/`false` parse to bool —
#   they must NOT silently pass for a numeric field. (Research §2.)

# CRITICAL #2 — __post_init__ RUNS ON EVERY CONSTRUCTION (defaults, from_toml, direct). The defaults
#   (0.6/0.15/30.0/1800.0 floats, strs, notify_ms 2500 int — NONE bool) all pass. Verified. Do NOT add
#   validation that the defaults themselves would fail. (Research §3/§4.)

# CRITICAL #3 — VALIDATE ONLY notify_ms IN FeedbackConfig. The item's optional clause names notify_ms
#   only. Do NOT validate state_file (str) / hypr_notify (bool) / notify_on_final (bool) — out of scope
#   and not silent-break risks. (Research §3.)

# CRITICAL #4 — RAISE TypeError (NOT ValueError/ConfigError). The existing unknown-key rejection uses
#   TypeError (dataclass __init__), and the item CONTRACT says "use TypeError too for consistency."
#   from_toml propagates it (not caught) -> fail-fast at daemon load. (Research §1.)

# CRITICAL #5 — S1 TOUCHES NO TEST FILES. The committed wrong-type pytest is P1.M3.T1.S2. S1's safety
#   net is (a) the existing fast suite stays green (regression scan: every existing construction uses
#   correct types — Research §4) + (b) the non-committed L3 wiring smoke. Do NOT add tests/test_config.py
#   wrong-type cases here (S2 owns them).

# CRITICAL #6 — REPRODUCE UNICODE IN oldText. config.py uses § (in the auto_unload comment) and
#   FeedbackConfig's notify_on_final comment uses ✔ ● ■. The chosen edit anchors AVOID the ✔/●/■ lines
#   (anchor on the blank line + `def resolved_state_file` instead). Copy the verbatim oldText from the
#   Implementation Blueprint. (Research §6.)

# GOTCHA #7 — NO COERCION. Do NOT `float(value)` a str to "fix" it (Approach A). A wrong type is a user
#   error to SURFACE with a clear message, not silently convert (which could mask a genuinely wrong
#   value). The item + bug_analysis chose Approach B-lite (validate + raise), not coercion.

# GOTCHA #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest).
#   Optional ruff at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed — do NOT run it.
```

## Implementation Blueprint

### Data models and structure

No data-model change. Two new methods (`AsrConfig.__post_init__`, `FeedbackConfig.__post_init__`) that validate existing fields at construction. No new fields, no coercion, no new classes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/config.py — AsrConfig.__post_init__ (Edit A)
  - ADD __post_init__ after the auto_unload_idle_seconds field (the last AsrConfig field), before
    @dataclass class OutputConfig.
  - Validates: 4 float fields (int|float, not bool) + 4 str fields (str). Raises TypeError.
  - EXACT oldText→newText: see Edit A.

Task 2: EDIT voice_typing/config.py — FeedbackConfig.__post_init__ (Edit B)
  - ADD __post_init__ before resolved_state_file (anchor: blank line + `def resolved_state_file`).
  - Validates: notify_ms (int, not bool, not float). Raises TypeError.
  - EXACT oldText→newText: see Edit B.

Task 3: EDIT config.toml — SCHEMA SOURCE comment (Edit C, [Mode A])
  - Append one ASCII sentence: wrong-typed values are also rejected at load.
  - EXACT oldText→newText: see Edit C.

Task 4: VALIDATE (no file change — see Validation Loop)
  - py_compile + tomllib parse + the existing fast suite (no regression) + the L3 wiring smoke.
  - No git commit unless the orchestrator directs it.
```

### Edits — verbatim oldText → newText

#### Edit A — `voice_typing/config.py` `AsrConfig.__post_init__`

`oldText` (the tail of AsrConfig — the `# 0 disables ...` comment + blanks + the next class header; unique, no ✔/●/■):
```
                                               # 0 disables (models stay resident until quit)


@dataclass
class OutputConfig:
```
`newText`:
```
                                               # 0 disables (models stay resident until quit)

    def __post_init__(self) -> None:
        """Validate field types at construction (bugfix Issue 4 / PRD §4.5 robustness).

        dataclasses do NOT enforce annotations at runtime, so a wrong-typed TOML value (e.g.
        auto_stop_idle_seconds = "thirty") loaded via from_toml(**section) would pass silently and
        break the feature at runtime — _maybe_auto_stop's `time.monotonic() - ts < threshold` raises
        TypeError, which the _idle_watchdog swallows, so auto-stop silently dies. This raises
        TypeError at LOAD time (construction = when from_toml calls AsrConfig(**section); before
        models load, before systemd loops), mirroring the existing unknown-key rejection (also
        TypeError). bool is rejected even for numeric fields: bool is an int subclass in Python but
        is not a valid config value here.
        """
        # Numeric fields: accept int or float, reject bool (int subclass) + everything else.
        for _name in (
            "post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",
        ):
            _v = getattr(self, _name)
            if isinstance(_v, bool) or not isinstance(_v, (int, float)):
                raise TypeError(
                    f"[asr] {_name} expects a number (int or float), "
                    f"got {type(_v).__name__}: {_v!r}"
                )
        # String fields: must be str.
        for _name in ("final_model", "realtime_model", "language", "device"):
            _v = getattr(self, _name)
            if not isinstance(_v, str):
                raise TypeError(
                    f"[asr] {_name} expects str, got {type(_v).__name__}: {_v!r}"
                )


@dataclass
class OutputConfig:
```

#### Edit B — `voice_typing/config.py` `FeedbackConfig.__post_init__` (notify_ms only)

`oldText` (anchor on the blank line + `def resolved_state_file` — AVOIDS the ✔/●/■ lines above; unique):
```

    def resolved_state_file(self) -> str:
```
`newText`:
```

    def __post_init__(self) -> None:
        """Validate notify_ms is an int (bugfix Issue 4 / PRD §4.5 robustness).

        notify_ms is the only runtime-numeric FeedbackConfig field. tomllib parses a bare `2500` as
        int (correct); `2500.0` parses as float and `true`/`"2500"` as bool/str. Reject all but a
        genuine int (and reject bool, an int subclass) at load time, mirroring AsrConfig.__post_init__
        and the unknown-key TypeError. Only notify_ms is validated here — the other fields are out of
        scope (a wrong-typed state_file fails at file-open with a clear error; a wrong-typed bool is
        merely truthy).
        """
        _v = self.notify_ms
        if isinstance(_v, bool) or not isinstance(_v, int):
            raise TypeError(
                f"[feedback] notify_ms expects int, got {type(_v).__name__}: {_v!r}"
            )

    def resolved_state_file(self) -> str:
```

#### Edit C — `config.toml` SCHEMA SOURCE comment ([Mode A])

`oldText` (unique):
```
#   a default in code, change it here too. Unknown keys are REJECTED at load time
#   (a typo raises an error instead of being silently ignored).
```
`newText` (ASCII-only added sentence):
```
#   a default in code, change it here too. Unknown keys are REJECTED at load time
#   (a typo raises an error instead of being silently ignored). Wrong-typed values are
#   rejected at load too: a string where a number is expected raises TypeError (so
#   `auto_stop_idle_seconds = "thirty"` fails fast, not silently).
```

> **Why these edits:** Edit A/B are the validation (fail-fast at construction = load). The bool-first idiom handles the `isinstance(True, int)` gotcha. The message shape (`[asr] {field} expects ..., got {type}: {value!r}`) matches the item contract and names the field + bad value. Edit C is the [Mode A] doc surface. No coercion (Approach B-lite, not A). No test edits (S2 owns the committed wrong-type pytest).

### Implementation Patterns & Key Details

```python
# (1) The bool-first numeric idiom (Critical #1) — bool is an int subclass, so reject it FIRST:
if isinstance(_v, bool) or not isinstance(_v, (int, float)):   # float field: int|float, not bool
    raise TypeError(...)
if isinstance(_v, bool) or not isinstance(_v, int):            # notify_ms: int only, not bool/float
    raise TypeError(...)

# (2) __post_init__ runs at EVERY construction (defaults pass — verified). from_toml's
#     section_cls(**section) triggers it -> TypeError propagates out of from_toml -> out of load
#     -> daemon fails to load (fail-fast, before models/systemd loop). No catch anywhere.

# (3) Raise TypeError (NOT ValueError) — consistency with the unknown-key rejection (Critical #4).

# (4) NO COERCION. Do NOT float() a str to "fix" it — surface the user error (Critical #7).
```

### Integration Points

```yaml
CONFIG (AsrConfig):
  - add method: "__post_init__ — validates 4 float + 4 str fields; raises TypeError on mismatch"
CONFIG (FeedbackConfig):
  - add method: "__post_init__ — validates notify_ms (int, not bool/float); raises TypeError"
LOAD PATH (VoiceTypingConfig.from_toml._overlay):
  - unchanged: "section_cls(**section) now triggers __post_init__ -> TypeError propagates (not caught)"
DOCS (config.toml):
  - append sentence: "wrong-typed values rejected at load (TypeError)"
CONSUMERS: none changed (the dataclass values are unchanged for valid configs; wrong configs now fail at load)
```

## Validation Loop

> pytest is the gate (.venv/bin/python). FULL PATHS (zsh aliases). mypy NOT installed (skip).
> ruff optional (/home/dustin/.local/bin/ruff, NOT in .venv). S1 touches NO test files.

### Level 1: Syntax + parse

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/config.py && echo "L1 py_compile OK"
"$PY" - <<'PY'
import tomllib
with open("config.toml","rb") as f: tomllib.load(f)
print("L1 config.toml parses OK")
PY
grep -n "__post_init__" voice_typing/config.py   # expect 2 (AsrConfig + FeedbackConfig)
grep -n "Wrong-typed values" config.toml          # expect 1 (the [Mode A] sentence)
# Expected: py_compile OK; config.toml parses; 2 __post_init__; 1 doc sentence.
```

### Level 2: Existing fast suite (THE regression gate — S1 adds no tests)

```bash
cd /home/dustin/projects/voice-typing
# The config + drift-guard + feedback + daemon suites (the ones that construct AsrConfig/FeedbackConfig):
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_feedback.py -v
# Expected: GREEN. test_repo_config_toml_equals_defaults (repo config.toml values are correctly typed ->
#   __post_init__ passes); test_repo_config_toml_has_no_extra_keys (unaffected); test_defaults_match_*
#   (defaults pass __post_init__); test_daemon's AsrConfig(:185) + FeedbackConfig constructions (correct types).
# Whole fast suite (no regression anywhere):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py is GPU-gated; excluded.)
```

### Level 3: Wiring smoke (the contract — non-committed; S2 hardens it into pytest)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import pytest
from voice_typing.config import AsrConfig, FeedbackConfig, VoiceTypingConfig

# (a) defaults + valid values construct fine (regression guard)
AsrConfig(); FeedbackConfig()
AsrConfig(**{"auto_stop_idle_seconds": 30.0}); AsrConfig(**{"auto_stop_idle_seconds": 30})  # int OK for float
AsrConfig(**{"device": "cpu"}); FeedbackConfig(**{"notify_ms": 2500})
print("L3a OK: defaults + valid (int/float/str) construct fine")

# (b) wrong-typed numeric -> TypeError naming the field + bad value (the Issue 4 contract)
for bad in ("thirty", True, None, [30.0]):
    with pytest.raises(TypeError) as e:
        AsrConfig(**{"auto_stop_idle_seconds": bad})
    assert "auto_stop_idle_seconds" in str(e.value) and repr(bad) in str(e.value), str(e.value)
print("L3b OK: auto_stop_idle_seconds wrong types (str/bool/None/list) -> TypeError naming field+value")

# (c) wrong-typed str field -> TypeError
with pytest.raises(TypeError) as e:
    AsrConfig(**{"device": 1})
assert "device" in str(e.value) and "expects str" in str(e.value), str(e.value)
print("L3c OK: device=1 (int where str expected) -> TypeError")

# (d) bool rejected for a float field (the bool gotcha — isinstance(True,int) is True)
with pytest.raises(TypeError):
    AsrConfig(**{"post_speech_silence_duration": True})
print("L3d OK: bool rejected for a float field")

# (e) notify_ms: int OK; bool/float/str rejected
FeedbackConfig(**{"notify_ms": 2500})                      # int OK
for bad in (True, 2500.0, "2500"):
    with pytest.raises(TypeError) as e:
        FeedbackConfig(**{"notify_ms": bad})
    assert "notify_ms" in str(e.value), str(e.value)
print("L3e OK: notify_ms accepts int, rejects bool/float/str")

# (f) from_toml propagates the TypeError at LOAD time (the fail-fast guarantee)
with pytest.raises(TypeError):
    VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})
with pytest.raises(TypeError):
    VoiceTypingConfig.from_toml({"feedback": {"notify_ms": 2500.0}})
print("L3f OK: from_toml raises TypeError at load (fail-fast, before models/systemd)")
PY
# Expected: prints all six "L3 OK" lines; exit 0. This is the structural proof S2 hardens into
# committed pytest. It exercises every branch of both __post_init__ methods (no GPU, no daemon).
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-daemon/GPU path. The end-to-end "wrong config fails at daemon load" guarantee is proven by
# Level 3f (from_toml raises) + the fact that the daemon's config load does not catch TypeError (it
# propagates -> systemd marks the unit failed with the message on the journal). An OPTIONAL live smoke
# (manual) is:
#   printf '[asr]\nauto_stop_idle_seconds = "thirty"\n' > /tmp/badcfg.toml
#   # point the daemon at it (or append to the XDG config) and:
#   systemctl --user restart voice-typing
#   journalctl --user -u voice-typing -e | grep 'auto_stop_idle_seconds expects a number'
# This is out of scope for S1's automated gate (it's a deployment smoke). S1's correctness is proven by
# Level 2 (no regression) + Level 3 (every validation branch).
```

## Final Validation Checklist

### Technical Validation
- [ ] `.venv/bin/python -m py_compile voice_typing/config.py` exits 0; `config.toml` parses via tomllib.
- [ ] `grep -c "__post_init__" voice_typing/config.py` → 2 (AsrConfig + FeedbackConfig).
- [ ] `grep "Wrong-typed values" config.toml` → 1 match.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/config.py` → clean.

### Feature Validation
- [ ] `AsrConfig()` / `FeedbackConfig()` (defaults) construct with no error.
- [ ] A str/bool/None for any AsrConfig float field → `TypeError` naming the field + value.
- [ ] A non-str for any AsrConfig str field → `TypeError`.
- [ ] bool rejected for float fields (the `isinstance(True, int)` gotcha).
- [ ] `FeedbackConfig(notify_ms=...)` accepts int, rejects bool/float/str.
- [ ] `VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})` → `TypeError` (load-time fail-fast).
- [ ] `<repo>/config.toml` still equals the defaults (drift guard green).

### Code Quality Validation
- [ ] bool rejected FIRST in each numeric check (`isinstance(v, bool) or ...`).
- [ ] Only `notify_ms` validated in FeedbackConfig (not state_file/hypr_notify/notify_on_final).
- [ ] `TypeError` raised (not ValueError/ConfigError) — consistency with unknown-key rejection.
- [ ] No coercion (Approach B-lite: validate + raise, not `float(value)`).
- [ ] Only `voice_typing/config.py` + `config.toml` modified (`git status --short`).

### Documentation & Deployment
- [ ] [Mode A] config.toml SCHEMA SOURCE comment notes wrong-typed values are rejected at load.
- [ ] `__post_init__` docstrings explain the bool gotcha + the load-time fail-fast rationale.
- [ ] No new env vars; no README/ACCEPTANCE edits; no test files (S2 owns the wrong-type pytest).

---

## Anti-Patterns to Avoid

- ❌ Don't write `isinstance(value, int)` alone for a numeric field — `isinstance(True, int)` is True; reject bool FIRST (Critical #1).
- ❌ Don't coerce wrong types with `float(value)` (Approach A) — surface the user error, don't silently convert (Gotcha #7).
- ❌ Don't raise ValueError/ConfigError — the contract is TypeError (consistency with the unknown-key rejection) (Critical #4).
- ❌ Don't validate FeedbackConfig fields other than `notify_ms` (state_file/hypr_notify/notify_on_final are out of scope) (Critical #3).
- ❌ Don't add wrong-type tests to tests/test_config.py here — that's P1.M3.T1.S2 (Critical #5). S1's safety net is the existing-fast-suite-no-regression + the L3 smoke.
- ❌ Don't mangle the §/✔/●/■ Unicode in oldText — the chosen anchors avoid the ✔/●/■ lines; copy verbatim (Critical #6).
- ❌ Don't catch the TypeError in `from_toml` — it must propagate (fail-fast at daemon load) (Critical #4).
- ❌ Don't edit any file other than `voice_typing/config.py` + `config.toml` — daemon/feedback/ctl/tests/README are out of scope.
- ❌ Don't run `mypy` — not installed; pytest is the gate (Gotcha #8).

---

**Confidence Score: 9.5/10** for one-pass success. The change is small and fully bounded: two `__post_init__` methods with explicit isinstance checks (the bool-first idiom pinned) + one config.toml sentence. The regression scan verified NO existing construction uses a wrong type (so the fast suite stays green with zero test edits), the parallel task is disjoint, every edit is byte-exact oldText→newText with Unicode-safe anchors, and the L3 smoke exercises every validation branch (str/bool/None/list for floats; non-str for strs; bool/float/str for notify_ms; the from_toml load-time propagation). The −0.5 reserves: the committed wrong-type pytest lives in S2 (not S1), so S1's automated coverage is the existing-suite-no-regression + the non-committed L3 smoke — by design, per the plan's S1/S2 split.
