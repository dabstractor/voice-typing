# PRP — P1.M3.T1.S2: Test wrong-typed config values raise TypeError at load

## Goal

**Feature Goal**: Add a committed pytest section to `tests/test_config.py` proving that wrong-typed
config values raise `TypeError` at LOAD time (via `VoiceTypingConfig.from_toml`), hardening bugfix
Issue 4 / PRD §4.5. This is a **test-only** subtask: it VERIFIES the `AsrConfig.__post_init__` +
`FeedbackConfig.__post_init__` type validation that P1.M3.T1.S1 implements. It produces NO production
code. Today's regression coverage only rejects *unknown keys* (`test_from_toml_unknown_key_raises`);
this adds the *wrong-type* coverage so a value like `auto_stop_idle_seconds = "thirty"` is proven to
fail fast at load (instead of loading silently and silently breaking auto-stop at runtime).

**Deliverable** (ONE artifact — insert a test section; do NOT create a new file):
1. `tests/test_config.py` — INSERT a `# from_toml — wrong-TYPED values raise TypeError at load`
   section (after `test_from_toml_section_not_a_table_raises`, before `test_from_toml_file_reads_toml`)
   containing **7 tests** (verbatim source in Implementation Blueprint → Task 2). No new imports.

**Success Definition**:
- (a) `tests/test_config.py` parses; `.venv/bin/python -m pytest tests/test_config.py -v` → all prior
  21 tests still pass + **7 new tests pass** (28 total), in well under 1s (pure-Python, no I/O).
- (b) **Item clause (a)** — `test_string_for_float_field_raises`: `from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})` raises `TypeError` whose message contains `auto_stop_idle_seconds` AND `thirty` (the bad value).
- (c) **Item clause (b)** — `test_bool_for_float_field_raises`: `from_toml({"asr": {"post_speech_silence_duration": True}})` raises `TypeError` (the `isinstance(True, int)` gotcha is caught).
- (d) **Item clause (c)** — `test_int_for_string_field_raises`: `from_toml({"asr": {"device": 123}})` raises `TypeError` naming `device`.
- (e) **Item clause (d)** — `test_valid_types_still_load`: correctly-typed values load fine and override the defaults (no false positives).
- (f) **Item clause (e)** — `test_int_accepted_for_float`: `from_toml({"asr": {"auto_stop_idle_seconds": 30}})` succeeds; the value stays an `int` (TOML allows bare integers; not coerced).
- (g) **Supporting** — `test_none_for_float_field_raises` (None rejected; covers `auto_unload_idle_seconds`) + `test_notify_ms_wrong_type_raises` (`FeedbackConfig.notify_ms` float/bool/str rejected at load, int OK — the same Issue 4 fix S1 made).
- (h) No out-of-scope files: NO edit to `voice_typing/config.py` (S1 owns it), no new test file, no `tests/__init__.py`, no edits to `daemon.py`/`feedback.py`/`ctl.py`/`config.toml`/`README.md`/`PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps.

## User Persona

**Target User**: None directly (test-only; item DOCS: "none"). Its "users" are the maintainer running
`pytest` and the orchestrator gating P1.M3 (config hardening) complete on a proven fail-fast contract.

**Use Case**: `cd voice-typing && .venv/bin/python -m pytest tests/test_config.py -v` → 7 new wrong-type
tests green → Issue 4's "fail fast at load with a clear error" guarantee is regression-proof in CI.

**Pain Points Addressed**: Issue 4 is a *silent* feature break — `auto_stop_idle_seconds = "thirty"`
loads with no error, then auto-stop silently dies at runtime (a `TypeError` the `_idle_watchdog`
swallows, leaving only a repeating journal traceback). S1 makes it fail loud at load; S2 pins that
loudness as a committed regression test so a future refactor that drops the `__post_init__` cannot
silently reintroduce the bug.

## Why

- **It is the verification gate for Issue 4.** S1 ships the `__post_init__` validation + a non-committed
  L3 smoke; S2 hardens the fail-fast claim into committed, deterministic pytest so the design cannot
  silently regress. The PRD §4.5 spirit ("a typo'd config key surfaces loudly") now extends to types,
  and these tests prove it.
- **Tests ride with the work (SOW §3).** This is the dedicated wrong-type pytest the plan splits out
  of S1 (S1 = impl + config.toml doc; S2 = the committed wrong-type tests).
- **Cheap, additive, GPU-free, no new deps, disjoint from S1.** Pure pytest, no new imports. S1 edits
  `voice_typing/config.py` + `config.toml`; S2 edits ONLY `tests/test_config.py` — a different file.
  Zero overlap; no merge conflict.
- **Covers the load path, not just construction.** Every test goes through `VoiceTypingConfig.from_toml`
  (the item's prescribed path), proving the `TypeError` propagates out of `_overlay`'s
  `section_cls(**section)` and out of `from_toml` — i.e. it fails at daemon load, not just at a direct
  `AsrConfig(...)` call the daemon never makes.

## What

Insert a `# from_toml — wrong-TYPED values raise TypeError at load` section into `tests/test_config.py`
containing 7 tests: the 5 item-prescribed cases (string-for-float, bool-for-float, int-for-string,
valid-types-load, int-accepted-for-float) plus 2 supporting cases (None-for-float, notify_ms wrong
type). All use `VoiceTypingConfig.from_toml({...})` + `pytest.raises(TypeError, ...)` / `as excinfo`,
mirroring the existing `test_from_toml_unknown_key_raises`. No new imports. Verbatim source in
Implementation Blueprint → Task 2.

### Success Criteria

- [ ] `tests/test_config.py` parses (`.venv/bin/python -m py_compile` + `ast.parse`).
- [ ] `.venv/bin/python -m pytest tests/test_config.py -v` → 28 passed (21 prior + 7 new), 0 failed.
- [ ] `test_string_for_float_field_raises`: TypeError; message contains `auto_stop_idle_seconds` + `thirty`.
- [ ] `test_bool_for_float_field_raises`: `post_speech_silence_duration: True` → TypeError.
- [ ] `test_int_for_string_field_raises`: `device: 123` → TypeError naming `device`.
- [ ] `test_none_for_float_field_raises`: `auto_unload_idle_seconds: None` → TypeError.
- [ ] `test_valid_types_still_load`: `30.0`/`0.6` load; values correct.
- [ ] `test_int_accepted_for_float`: `30` (int) loads; stays int (not coerced).
- [ ] `test_notify_ms_wrong_type_raises`: `notify_ms` float/bool/str → TypeError; int (9999) loads.
- [ ] ONLY `tests/test_config.py` modified (`git status --short` shows only that file).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the CONTRACT under test (S1's `__post_init__` —
which fields, the accept/reject rules, the bool gotcha, the exact message shape with the field name
always present) is pinned from `P1M3T1S1/PRP.md` and mirrored in research §1; the consumed `from_toml`
construction path (`_overlay` → `section_cls(**section)` → `__post_init__` → TypeError propagates, not
caught) is pinned with line numbers; the existing style template (`test_from_toml_unknown_key_raises`)
is reproduced; the exact insertion point is named; the verbatim 7-test source is in Implementation
Blueprint → Task 2 — and is **pre-validated** (it ran `28 passed` against the real `config.py` on
2026-07-14). The baseline (`tests/test_config.py` = 21 passed) is verified live.

### Documentation & References

```yaml
# MUST READ — the contract under test (S1's deliverable). READ to align field names + message shape.
- file: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M3T1S1/PRP.md
  why: "Defines EXACTLY what AsrConfig.__post_init__ + FeedbackConfig.__post_init__ validate: 4 float
        fields (int|float, not bool), 4 str fields (str), notify_ms (int, not bool/float); raise
        TypeError with f\"[asr] {field} expects ..., got {type}: {value!r}\" (field name ALWAYS in the
        message). from_toml._overlay does section_cls(**section) -> __post_init__ runs at LOAD ->
        TypeError propagates (not caught)."
  critical: "S1 has LANDED (config.py:65 AsrConfig.__post_init__, :121 FeedbackConfig.__post_init__).
             The field name appears in EVERY message -> the tests assert match=\"<field>\". from_toml
             does NOT coerce (a wrong type is rejected, not converted)."

# MUST READ — this task's research (contract table + test design + validation result + insertion point)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M3T1S2/research/test_design_notes.md
  why: "§1 the contract table (fields, accept/reject, message shape) + the bool gotcha. §2 the 7 tests
        mapped to item clauses (a)-(e) + 2 supporting. §3 insertion point + style. §4 tooling +
        the VERIFIED result (28 passed against real config.py)."
  section: "ALL load-bearing. §1 (contract), §2 (test->clause), §3 (insertion point)."

# MUST READ — the file being edited (the style template + the insertion anchor + existing imports)
- file: tests/test_config.py
  why: "STYLE TEMPLATE: test_from_toml_unknown_key_raises (~line 116) is the exact pattern to mirror
        (with pytest.raises(TypeError): VoiceTypingConfig.from_toml({...})). IMPORTS already present:
        pytest, VoiceTypingConfig, AsrConfig, FeedbackConfig, cfgmod — NO new imports. INSERTION POINT:
        the `# from_toml / from_toml_file` section, after test_from_toml_section_not_a_table_raises
        (~line 125) and before test_from_toml_file_reads_toml (~line 128) — right next to the sibling
        validation tests."
  critical: "INSERT, do NOT create a new file. APPEND the section between two existing tests (anchor:
             the blank lines + `def test_from_toml_file_reads_toml(tmp_path):`). Do NOT edit any other
             test. Do NOT add tests/__init__.py."

# MUST READ — the consumed contract (AsrConfig/FeedbackConfig fields + from_toml). READ, do NOT edit.
- file: voice_typing/config.py
  why: "AsrConfig (49-66): 4 str + 4 float fields (the names the tests reference). FeedbackConfig (~99):
        notify_ms (int). from_toml._overlay (~212-218): section_cls(**section) -> __post_init__ triggers
        -> TypeError propagates. READ to confirm field names; S1 owns this file (do NOT edit)."
  critical: "Do NOT edit config.py (S1 owns it). Field names are stable (S1 only ADDED __post_init__,
             it did not rename fields). The tests reference: auto_stop_idle_seconds, post_speech_
             silence_duration, auto_unload_idle_seconds, device, notify_ms."

# CONTEXT — the bug-analysis root cause + recommended approach (READ-ONLY)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 4: the from_toml(**section) no-type-check root cause + 'Recommended: Approach B-lite
        (__post_init__ + isinstance + TypeError)'. Confirms S1's approach; S2 tests that approach."
  critical: "Do NOT edit the bug_analysis (READ-ONLY)."

# CONTEXT — the test-infrastructure map (READ-ONLY)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/test_infrastructure.md
  why: "Lists tests/test_config.py as the config-loader test file and 'Config type validation' as a
        known coverage gap (only test_unknown_key_raises exists today). S2 closes that gap."
  critical: "Do NOT edit (READ-ONLY)."

# THE PRD (the robustness promise) — READ-ONLY
- docfile: PRD.md
  why: "§4.5: 'Unknown keys raise TypeError ... a typo surfaces loudly.' Issue 4 extends the same
        loud-failure promise to wrong TYPES — these tests pin that extension."
  critical: "Do NOT edit PRD.md (forbidden)."
```

### Current Codebase tree (state at P1.M3.T1.S2 start — S1 LANDED)

> S1 (P1.M3.T1.S1) has LANDED: `config.py:65` (AsrConfig.__post_init__) + `config.py:121`
> (FeedbackConfig.__post_init__) are present and match the S1 PRP contract. So S2's tests are GREEN
> against the current code (verified: 28 passed). If S1 were reverted, the 5 wrong-type tests would
> fail (TDD RED) — that is the regression signal.

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── config.py       # S1 LANDED: AsrConfig.__post_init__ (:65) + FeedbackConfig.__post_init__ (:121).
│                       #   CONSUME (read field names); DO NOT EDIT (S1 owns it).
└── tests/
    └── test_config.py  # <-- EDIT (INSERT the 7-test wrong-type section). 21 tests currently; baseline GREEN.
# NO new files. NO tests/__init__.py. NO config.py/daemon.py/feedback.py/ctl.py/config.toml edits.
```

### Desired Codebase tree with files to be added

```bash
tests/test_config.py   # MODIFIED: INSERT `# from_toml — wrong-TYPED values raise TypeError at load`
                       #          section (7 tests) between test_from_toml_section_not_a_table_raises
                       #          and test_from_toml_file_reads_toml. No new imports.
# NOTHING ELSE. No new files. No config.py/daemon.py/feedback.py/ctl.py/config.toml edits. No new deps.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A TEST-ONLY SUBTASK; DO NOT EDIT config.py. S1 (P1.M3.T1.S1) owns config.py.
#   This task's ONLY edit is INSERTING into tests/test_config.py. If a test reveals an S1 bug, raise
#   it — do NOT patch the impl here. (Item OUTPUT; research §3.)

# CRITICAL #2 — THE TESTS REQUIRE S1 TO HAVE LANDED. They assert from_toml raises TypeError for wrong
#   types, which only happens once AsrConfig/FeedbackConfig __post_init__ exist (S1). S1 HAS landed
#   (config.py:65/:121) — verified. If S1 is reverted, the 5 wrong-type tests fail (the intended TDD
#   RED regression signal). The 2 "valid load" tests pass regardless. (Research §1, §4.)

# CRITICAL #3 — GO THROUGH from_toml, NOT direct AsrConfig(...). The item INPUT prescribes
#   VoiceTypingConfig.from_toml({'asr': {...}}) as the construction path. That proves the TypeError
#   propagates through _overlay (section_cls(**section) -> __post_init__) and out of from_toml — i.e.
#   fail-fast at daemon LOAD, not just at a direct construction the daemon never makes. Every test
#   calls from_toml. (Research §2; item INPUT/LOGIC.)

# CRITICAL #4 — THE FIELD NAME IS ALWAYS IN THE MESSAGE. S1's messages are f"[asr] {field} expects
#   ..., got {type}: {value!r}" / f"[feedback] notify_ms expects int, ...". So pytest.raises(TypeError,
#   match="<field>") is safe (match uses re.search). For clause (a), ALSO assert the bad value is in
#   the message (via `as excinfo` + `"thirty" in str(excinfo.value)`) to pin the helpful-message
#   contract. Do NOT over-constrain the exact wording (it may evolve); assert substrings only.
#   (Research §1; S1 PRP Edit A/B.)

# CRITICAL #5 — THE BOOL GOTCHA IS A TEST, NOT A PITFALL FOR THE TEST. S1 rejects bool FIRST
#   (isinstance(True,int) is True). test_bool_for_float_field_raises (True for a float field) and the
#   notify_ms=True case PIN that rejection — they would FAIL if S1 forgot the bool-first idiom. Do NOT
#   write a test that expects bool to be accepted. (Research §1; S1 Critical #1.)

# CRITICAL #6 — test_int_accepted_for_float: assert the value STAYS int, not coerced. S1 does NOT
#   coerce (Approach B-lite: validate + raise, never float()-convert). So from_toml({"asr":
#   {"auto_stop_idle_seconds": 30}}) leaves the value as int 30. Assert isinstance(..., int) to prove
#   no silent coercion (a coercion would be Approach A, which S1 explicitly did NOT choose). This also
#   documents that TOML bare integers are valid for float fields. (Research §1; item clause (e).)

# CRITICAL #7 — INSERT, DO NOT CREATE A NEW FILE. The section goes in tests/test_config.py's
#   `# from_toml / from_toml_file` section, between test_from_toml_section_not_a_table_raises and
#   test_from_toml_file_reads_toml (next to the sibling validation tests). No new imports (pytest,
#   VoiceTypingConfig, AsrConfig, FeedbackConfig already imported at the top). No tests/__init__.py.
#   (Research §3.)

# GOTCHA #8 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always
#   `.venv/bin/python -m pytest ...` / `.venv/bin/python -m py_compile ...`. mypy NOT installed (skip).
#   ruff at /home/dustin/.local/bin/ruff is an OPTIONAL lint (not in .venv; not a gate). (Research §4.)

# GOTCHA #9 — THE VERBATIM SOURCE IS PRE-VALIDATED. The 7-test block in Implementation Blueprint →
#   Task 2 was run (copied test_config.py + appended) against the real config.py on 2026-07-14:
#   `28 passed in 0.03s`. Use it verbatim (do not "improve" it — it is proven). (Research §4.)
```

## Implementation Blueprint

### Data models and structure

No data model. The section consumes the existing `VoiceTypingConfig.from_toml` classmethod and the
`AsrConfig`/`FeedbackConfig` dataclasses. No new imports, no new fixtures, no helpers.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the contract + file state (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f tests/test_config.py && echo "ok: test_config.py exists" || echo "PREFLIGHT FAIL"
      grep -n "def __post_init__" voice_typing/config.py   # expect 2 (AsrConfig + FeedbackConfig) -> S1 landed
      grep -n "def test_from_toml_unknown_key_raises\|def test_from_toml_section_not_a_table_raises\|def test_from_toml_file_reads_toml" tests/test_config.py
      grep -n "def test_string_for_float\|def test_notify_ms_wrong_type" tests/test_config.py && echo "PREFLIGHT NOTE: section already present" || echo "ok: section absent (will insert)"
      .venv/bin/python -m pytest tests/test_config.py -q --no-header 2>&1 | tail -2
  - EXPECTED: test_config.py present; 2 __post_init__ in config.py (S1 landed); the 3 anchor tests found
    in test_config.py; the section absent; baseline prints "21 passed".
  - DO NOT: insert the section yet, edit config.py, run uv sync/add, or touch any other file.

Task 2: INSERT the wrong-type section into tests/test_config.py — use the `edit` tool with the
        verbatim block from "Task 2 SOURCE" below, anchored between
        test_from_toml_section_not_a_table_raises and test_from_toml_file_reads_toml.
  - FILE: tests/test_config.py
  - ANCHOR oldText:
        def test_from_toml_section_not_a_table_raises():
            """A scalar where a TOML table is expected must raise (not silently default)."""
            with pytest.raises(TypeError):
                VoiceTypingConfig.from_toml({"asr": "not-a-table"})


        def test_from_toml_file_reads_toml(tmp_path):
  - newText: that same block UNCHANGED (through `VoiceTypingConfig.from_toml({"asr": "not-a-table"})`)
    + a blank line + the ENTIRE Task 2 SOURCE block + a blank line + `def test_from_toml_file_reads_toml(tmp_path):`.
    (Equivalently: replace the two blank lines between the two tests with blank + section + blank.)
  - DO NOT: edit config.py (Critical #1); create a new file / tests/__init__.py (Critical #7); add
    imports (none needed); go through direct AsrConfig(...) instead of from_toml (Critical #3).

Task 3: VALIDATE — run the Validation Loop L1 (py_compile) + L2 (pytest, the primary gate).
        Iterate until 28 passed. L3/L4 are scope guards. No git commit unless the orchestrator
        directs it. If asked: message "P1.M3.T1.S2: wrong-typed config values raise TypeError at
        load (7 tests, pure-Python, no CUDA)".
```

#### Task 2 SOURCE — insert verbatim into `tests/test_config.py`

```python


# ---------------------------------------------------------------------------
# from_toml — wrong-TYPED values raise TypeError at load (bugfix Issue 4 / PRD §4.5)
#
# Unknown keys already raise TypeError (test_from_toml_unknown_key_raises). A wrong TYPE
# (e.g. auto_stop_idle_seconds = "thirty") used to load silently and break the feature at
# runtime (a TypeError the _idle_watchdog swallowed -> auto-stop silently died).
# AsrConfig/FeedbackConfig __post_init__ (P1.M3.T1.S1) now validates types at construction
# (= load time). These pin that fail-fast contract.
# ---------------------------------------------------------------------------


def test_string_for_float_field_raises():
    """A string where a float is expected raises TypeError naming the field + bad value."""
    with pytest.raises(TypeError) as excinfo:
        VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})
    assert "auto_stop_idle_seconds" in str(excinfo.value)
    assert "thirty" in str(excinfo.value)


def test_bool_for_float_field_raises():
    """A bool where a float is expected raises TypeError (the isinstance(True, int) gotcha)."""
    with pytest.raises(TypeError, match="post_speech_silence_duration"):
        VoiceTypingConfig.from_toml({"asr": {"post_speech_silence_duration": True}})


def test_int_for_string_field_raises():
    """An int where a str is expected raises TypeError naming the field."""
    with pytest.raises(TypeError, match="device"):
        VoiceTypingConfig.from_toml({"asr": {"device": 123}})


def test_none_for_float_field_raises():
    """None is not a valid numeric value -> TypeError (a common real-world wrong value)."""
    with pytest.raises(TypeError, match="auto_unload_idle_seconds"):
        VoiceTypingConfig.from_toml({"asr": {"auto_unload_idle_seconds": None}})


def test_valid_types_still_load():
    """Correctly-typed values load fine and override the defaults (no false positives)."""
    cfg = VoiceTypingConfig.from_toml(
        {"asr": {"auto_stop_idle_seconds": 30.0, "post_speech_silence_duration": 0.6}}
    )
    assert cfg.asr.auto_stop_idle_seconds == 30.0
    assert cfg.asr.post_speech_silence_duration == 0.6


def test_int_accepted_for_float():
    """A bare int is acceptable for a float field (TOML allows bare integers); not coerced."""
    cfg = VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": 30}})
    assert cfg.asr.auto_stop_idle_seconds == 30
    assert isinstance(cfg.asr.auto_stop_idle_seconds, int)  # accepted as-is, not coerced to float


def test_notify_ms_wrong_type_raises():
    """FeedbackConfig.notify_ms: a float/bool/str is rejected at load (same Issue 4 fix); int OK."""
    for bad in (2500.0, True, "2500"):
        with pytest.raises(TypeError, match="notify_ms"):
            VoiceTypingConfig.from_toml({"feedback": {"notify_ms": bad}})
    cfg = VoiceTypingConfig.from_toml({"feedback": {"notify_ms": 9999}})
    assert cfg.feedback.notify_ms == 9999
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — go through the LOAD path (from_toml), not direct construction (the item's INPUT):
with pytest.raises(TypeError, match="auto_stop_idle_seconds"):
    VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})
# Proves TypeError propagates: _overlay -> section_cls(**section) -> __post_init__ -> out of from_toml.

# PATTERN 2 — assert substrings, not exact wording (the message may evolve; the field name is the contract):
with pytest.raises(TypeError) as excinfo:
    VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})
assert "auto_stop_idle_seconds" in str(excinfo.value)   # field name
assert "thirty" in str(excinfo.value)                   # bad value (helpful-message contract)

# PATTERN 3 — the bool gotcha is a TEST (pins S1's bool-first rejection; would fail if S1 forgot it):
with pytest.raises(TypeError, match="post_speech_silence_duration"):
    VoiceTypingConfig.from_toml({"asr": {"post_speech_silence_duration": True}})  # bool, not a number

# PATTERN 4 — no-coercion guard (int accepted as-is for a float field; S1 validates, never converts):
cfg = VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": 30}})
assert isinstance(cfg.asr.auto_stop_idle_seconds, int)   # stays int, NOT coerced to 30.0
```

### Integration Points

```yaml
TEST FILE:
  - insert into: "tests/test_config.py (# from_toml / from_toml_file section, between
                  test_from_toml_section_not_a_table_raises and test_from_toml_file_reads_toml)"
  - new symbols: "7 test functions (module-level; no fixtures beyond pytest.raises)"
REUSED (no new imports):
  - "pytest, VoiceTypingConfig, AsrConfig, FeedbackConfig (all already imported at top of file)"
CONSUMED CONTRACT (do NOT edit — S1/landed):
  - config.py: "AsrConfig.__post_init__ (:65), FeedbackConfig.__post_init__ (:121), from_toml._overlay
                (~212-218: section_cls(**section) -> __post_init__ -> TypeError propagates)"
DEPENDENCIES: none new (stdlib + pytest only). dev=["pytest>=9.1.1"].
```

## Validation Loop

> pytest is the gate (`.venv/bin/python`). FULL PATHS (zsh aliases). mypy NOT installed (skip). ruff
> optional (`/home/dustin/.local/bin/ruff`, NOT in `.venv`). These are pure-Python tests (< 0.1s).

### Level 1: Syntax

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f tests/test_config.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile tests/test_config.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
"$PY" -c "import ast; ast.parse(open('tests/test_config.py').read()); print('L1 ast.parse OK')"
# Expected: file present; py_compile OK; ast.parse OK.
```

### Level 2: Unit Tests (THE gate — 7 new tests pass; 28 total)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python

# 2a — collect (does the section parse + are the 7 tests discovered?).
"$PY" -m pytest tests/test_config.py --collect-only -q 2>&1 | tail -3
# Expected: collects 28 tests (21 prior + 7 new), NO collection errors.

# 2b — run just the new section.
"$PY" -m pytest tests/test_config.py -v -k "string_for_float or bool_for_float or int_for_string or none_for_float or valid_types_still_load or int_accepted or notify_ms_wrong"
# Expected: 7 passed. If any FAIL: the most likely cause is S1 not having landed (the 5 wrong-type
#   tests would fail with "DID NOT RAISE TypeError") — confirm `grep -n "__post_init__" voice_typing/
#   config.py` shows 2. If S1 landed but a test fails, READ the assertion, reconcile against S1's
#   __post_init__ message shape, and fix the TEST (not S1 — S1 owns config.py; raise the discrepancy).

# 2c — full test_config.py regression (nothing else broke).
"$PY" -m pytest tests/test_config.py -q
# Expected: 28 passed, 0 failed.

# 2d — whole fast suite (no regression elsewhere; test_feed_audio.py is GPU-gated — exclude it).
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed.
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
# ONLY tests/test_config.py changed; config.py untouched (S1 owns it).
git status --porcelain
# Expected: ONLY " M tests/test_config.py" (one modified file). Any change to voice_typing/config.py,
#   config.toml, daemon.py, feedback.py, ctl.py, README.md, PRD.md, tasks.json is a SCOPE VIOLATION.
git diff --name-only
# Expected: tests/test_config.py
# Confirm the section landed in the right place + no new files:
test ! -e tests/test_config_wrong_type.py && echo "L3 ok: no stray new test file"
grep -n "wrong-TYPED values raise TypeError at load" tests/test_config.py
# Expected: one match (the section header).
```

### Level 4: Determinism / message-substring check

```bash
cd /home/dustin/projects/voice-typing
# Re-run several times — pure-Python tests must never flake.
for i in 1 2 3; do
  .venv/bin/python -m pytest tests/test_config.py -q -k "string_for_float or bool_for_float or int_for_string or none_for_float or valid_types_still_load or int_accepted or notify_ms_wrong" 2>&1 | tail -1
done
# Expected: "7 passed" on every run.

# Confirm the helpful-message contract (field name + bad value) directly:
.venv/bin/python - <<'PY'
import pytest
from voice_typing.config import VoiceTypingConfig
with pytest.raises(TypeError) as e:
    VoiceTypingConfig.from_toml({"asr": {"auto_stop_idle_seconds": "thirty"}})
msg = str(e.value)
assert "auto_stop_idle_seconds" in msg and "thirty" in msg, msg
print("L4 OK:", msg)
PY
# Expected: prints the L4 OK line with the full message (proves the field name + bad value are surfaced).
```

## Final Validation Checklist

### Technical Validation
- [ ] `.venv/bin/python -m py_compile tests/test_config.py` → exit 0.
- [ ] `.venv/bin/python -m pytest tests/test_config.py --collect-only -q` → 28 collected, no errors.
- [ ] `.venv/bin/python -m pytest tests/test_config.py -v -k "string_for_float or bool_for_float or int_for_string or none_for_float or valid_types_still_load or int_accepted or notify_ms_wrong"` → **7 passed**.
- [ ] `.venv/bin/python -m pytest tests/test_config.py -q` → 28 passed.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L3 scope guard: ONLY `tests/test_config.py` modified; config.py untouched.

### Feature Validation
- [ ] Clause (a): string-for-float → TypeError; message names field + bad value.
- [ ] Clause (b): bool-for-float → TypeError (bool gotcha caught).
- [ ] Clause (c): int-for-string → TypeError naming `device`.
- [ ] Clause (d): valid types load; values correct.
- [ ] Clause (e): int accepted for float; stays int (no coercion).
- [ ] Supporting: None-for-float → TypeError; notify_ms float/bool/str → TypeError, int OK.
- [ ] Every wrong-type test goes through `VoiceTypingConfig.from_toml` (the load path), not direct construction.

### Code Quality Validation
- [ ] Section header + one-line docstrings mirror the file's style (Issue 4 / PRD §4.5 cross-ref).
- [ ] No new imports (pytest/VoiceTypingConfig/AsrConfig/FeedbackConfig already present); no new deps.
- [ ] Assertions are substring-based (`match=` / `in str(excinfo.value)`), not exact-wording (robust to message evolution).
- [ ] Only `tests/test_config.py` modified; insert-only (no edits to earlier tests).

### Documentation & Deployment
- [ ] Section header documents: the Issue 4 root cause, the load-time fail-fast contract, the S1 cross-ref.
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none — test-only").

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/config.py` — S1 owns it; this subtask is test-only. If a test reveals an impl bug, raise it, don't patch it here (Critical #1).
- ❌ Don't create a new test file or `tests/__init__.py` — INSERT into `tests/test_config.py` (Critical #7).
- ❌ Don't go through direct `AsrConfig(...)` — the item prescribes `VoiceTypingConfig.from_toml({...})`; that proves the TypeError propagates through the LOAD path (Critical #3).
- ❌ Don't write a test that expects bool to be accepted for a numeric field — bool is rejected (the `isinstance(True, int)` gotcha); the bool test pins the REJECTION (Critical #5).
- ❌ Don't assert exact message wording — assert substrings (field name + bad value) so the tests survive a message rewording (Critical #4).
- ❌ Don't write a test that expects int to be coerced to float — S1 validates but never coerces (Approach B-lite); assert the value stays int (Critical #6).
- ❌ Don't run `mypy` (not installed) or bare `python`/`pytest` (zsh aliases) — use `.venv/bin/python -m pytest` (Gotcha #8).
- ❌ Don't "improve" the verbatim source — it is pre-validated (28 passed against the real config.py); use it as-is (Gotcha #9).

---

## Confidence Score

**9.5/10** for one-pass success. The 7 tests are ~50 lines of straightforward pytest + `from_toml`,
mirroring the existing `test_from_toml_unknown_key_raises` exactly. The CONTRACT under test (S1's
`__post_init__` — fields, accept/reject rules, bool gotcha, message shape with the field name always
present) is pinned from `P1M3T1S1/PRP.md` AND confirmed against the landed `config.py` (lines 65/121).
**Most importantly, the verbatim source is pre-validated**: copying `tests/test_config.py` + appending
the section ran `28 passed in 0.03s` against the real `voice_typing/config.py` on 2026-07-14. Every
test maps to an item clause (a)–(e) plus 2 supporting cases (None, notify_ms). S1 has landed, so the
tests are GREEN on the current code.

The −0.5 reserves: (a) if S1's message wording were ever changed to omit the field name (breaking the
contract), the `match=`/substring tests would need a one-line update — but that is itself the intended
regression signal (the field name SHOULD be in the message). (b) The insertion relies on the anchor
text matching byte-for-byte (the `test_from_toml_section_not_a_table_raises` + blank lines +
`test_from_toml_file_reads_toml` block) — pinned verbatim in Task 2; if a sibling task reorders the
from_toml section first, the anchor is trivially re-found. Both are bounded, one-line fixes gated by
the L2 pytest output, not architectural risks.
