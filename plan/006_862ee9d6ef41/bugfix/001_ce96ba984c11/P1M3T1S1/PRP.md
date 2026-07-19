# PRP — P1.M3.T1.S1: Add `backend` value validation to `OutputConfig.__post_init__()` + load-time tests

## Goal

**Feature Goal**: Make an invalid `output.backend` value (e.g. a typo like `"wtyp"`) fail FAST at config **load time** with a clear `ValueError`, instead of loading silently and crashing later in `typing_backends.make_backend()` (which under systemd is a `Restart=on-failure` crash-loop discoverable only via `journalctl`). This mirrors the existing `asr.device` enum validation (VT-005) and closes the code-quality inconsistency the bug report (Issue 3) flags. PRD §4.5 robustness.

**Deliverable** (TDD — tests RED first, then the one-method fix; 2 files, no new files):
1. `tests/test_config.py` — add TWO tests (`test_invalid_backend_value_raises`, `test_valid_backend_values_load`) mirroring the VT-005 device tests (L172-183) EXACTLY. Written FIRST; the invalid-value test FAILS (RED) until the fix lands.
2. `voice_typing/config.py` — add `__post_init__(self)` to `OutputConfig` that raises `ValueError(f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}')` when `self.backend not in ("wtype", "ydotool", "tmux")`. Mirrors `AsrConfig.__post_init__`'s `device` validation line-for-line.

**Success Definition**:
- (a) `VoiceTypingConfig.from_toml({"output": {"backend": "wtyp"}})` raises `ValueError` at LOAD time (before the daemon starts); the message names `backend` and the bad value.
- (b) `wtype`, `ydotool`, `tmux` each load normally and round-trip (`cfg.output.backend == good`).
- (c) RED→GREEN: after adding the tests but BEFORE the fix, `test_invalid_backend_value_raises` FAILS (no validation); after the fix, BOTH new tests PASS.
- (d) `make_backend()` in `typing_backends.py` is UNCHANGED (retains its own `ValueError` as a defensive second gate).
- (e) `tests/test_typing_backends.py::test_make_backend_unknown_raises_value_error` STAYS GREEN without modification (the `OutputConfig(backend="bogus")` it constructs now raises ValueError at construction; `pytest.raises(ValueError, match="bogus")` still catches it).
- (f) `timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_typing_backends.py -q` → all pass.
- (g) No out-of-scope files: NOT `typing_backends.py`, NOT `test_typing_backends.py`, NOT README (P1.M4.T1 verifies consistency), NOT daemon.py/test_daemon.py (parallel P1.M2.T1.S1 owns the `_final_pending` reset there), NOT `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps. config.py stays stdlib-only.

## User Persona

**Target User**: the operator who hand-edits `~/.config/voice-typing/config.toml` and typos the backend (`backend = "wtyp"`).

**Use Case**: Today the daemon boots, loads the bad config silently, then crash-loops under systemd (`make_backend` raises `ValueError: unknown output.backend: 'wtyp'` in `__init__`) — the user must find it via `journalctl`. After this fix: `systemctl --user restart voice-typing` fails immediately with `[output] backend must be "wtype", "ydotool", or "tmux", got 'wtyp'` — the user corrects the typo and restarts.

**Pain Points Addressed**: a silent load → crash-loop → journal-only diagnosis becomes a loud, load-time error naming the field + bad value, exactly when the user is editing config. Consistent with how `device = "gpu"` is already rejected (VT-005).

## Why

- **Closes the VT-005 inconsistency (PRD §4.5 spirit).** `asr.device` is already enum-validated at load; `output.backend` is not — the same class of user typo (a bad enum value) surfaces at totally different times. This makes the fast-fail posture uniform.
- **Cheap, surgical, stdlib-only.** One 3-line method mirroring an existing one + two mirroring tests. No new deps, no coercion, no public-API change. The error surfaces at `from_toml._overlay` → `OutputConfig(**section)` → `__post_init__`, i.e. at daemon load — before models, before systemd loops.
- **`make_backend`'s ValueError stays as defense-in-depth.** The contract mandates keeping it (unchanged). With `__post_init__`, it becomes unreachable via normal construction, but it is a harmless defensive second gate (and its test stays green — §3.4 of research).
- **Parallel-safe.** The in-flight P1.M2.T1.S1 edits `daemon.py` + `test_daemon.py` (the `_final_pending` reset); this task edits `config.py` + `test_config.py`. Zero file overlap.

## What

A `__post_init__` on `OutputConfig` that validates `backend ∈ {"wtype", "ydotool", "tmux"}` and raises `ValueError` otherwise (mirroring `AsrConfig.__post_init__`'s `device` check). Two TDD tests in `tests/test_config.py` mirroring the VT-005 device tests. `make_backend()` and its test are unchanged.

### Success Criteria

- [ ] `OutputConfig.__post_init__` exists; `OutputConfig()` (default `backend="wtype"`) constructs with NO error.
- [ ] `OutputConfig(backend="wtyp")` raises `ValueError` whose message contains `backend` and `'wtyp'`.
- [ ] `wtype`/`ydotool`/`tmux` each construct + round-trip through `from_toml`.
- [ ] `from_toml({"output": {"backend": "wtyp"}})` raises `ValueError` at load.
- [ ] The two new tests mirror the VT-005 device tests (`for bad in (...)` + `match=`; `for good in (...)` + `assert`).
- [ ] RED→GREEN: the invalid-value test fails before the fix, passes after.
- [ ] `make_backend()` (typing_backends.py) UNCHANGED; `test_make_backend_unknown_raises_value_error` stays GREEN.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_typing_backends.py -q` → all pass.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the precedent (`AsrConfig.__post_init__` device validation, verbatim) + the exact edit anchors (OutputConfig L118-125; the VT-005 tests L172-183) are pinned; the RED→GREEN flow is explained; the make_backend-test-stays-green proof is given; the regression scan (no other test breaks) is verified; every edit is byte-exact oldText→newText; and the validation commands are executable as written.

### Documentation & References

```yaml
# MUST READ — the precedent, the edit sites, the RED→GREEN flow, the make_backend-test proof, scope
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/P1M3T1S1/research/output_backend_validation.md
  why: "§1 the AsrConfig device-validation precedent (verbatim — mirror it line-for-line). §2 the edit
        sites (OutputConfig L118-125 has NO __post_init__; @dataclass IS on it L118 so __post_init__
        auto-fires; from_toml._overlay L238-4 calls OutputConfig(**section) -> fires at LOAD time; the
        VT-005 device tests L172-183 to mirror). §3 the RED->GREEN TDD flow. §4 the make_backend test
        STAYS GREEN (OutputConfig(backend='bogus') raises at construction; pytest.raises catches it;
        match='bogus' holds) -> NO edit to test_typing_backends.py. §5 regression scan (all other
        OutputConfig() constructions use valid backends). §6 scope + tooling."
  section: "ALL load-bearing. §1 (precedent), §2 (edit sites), §4 (make_backend test), §5 (regression)."

# MUST READ — the file being edited (OutputConfig + the AsrConfig.__post_init__ precedent)
- file: voice_typing/config.py
  why: "AsrConfig.__post_init__ device validation (the precedent to mirror): `if self.device not in
        ('cuda','cpu'): raise ValueError(f'[asr] device must be \"cuda\" or \"cpu\", got {self.device!r}')`.
        OutputConfig (L118-125): backend/tmux_target/append_space, NO __post_init__ — add the method
        after append_space, before @dataclass FeedbackConfig. from_toml._overlay (L238-244) calls
        section_cls(**section) -> __post_init__ fires at load."
  critical: "Use ValueError (NOT TypeError) — the TYPE is correct (str), the VALUE is not (mirrors device).
             Message must contain 'backend' (tests match='backend') AND the bad value (make_backend test
             match='bogus'). @dataclass IS on OutputConfig (L118) so __post_init__ auto-fires. Reproduce
             the — (em dash) in surrounding oldText EXACTLY if the anchor includes it (the chosen anchor
             does not)."

# MUST READ — the test file being edited (the VT-005 device tests to mirror, L172-183)
- file: tests/test_config.py
  why: "test_invalid_device_value_raises (L172) + test_valid_device_values_load (L179) are the EXACT
        pattern to mirror: `for bad in (...): with pytest.raises(ValueError, match='device'): from_toml(...)`
        and `for good in (...): cfg = from_toml(...); assert cfg.asr.device == good`. The two NEW backend
        tests substitute output/backend/wtype/ydotool/tmux. Place them right after test_valid_device_values_load."
  critical: "Mirror the for-loop + pytest.raises(ValueError, match=...) idiom EXACTLY. The bad list per the
             contract: ('wtyp','xterm','WTYPE','','auto','gpu'). The good list: ('wtype','ydotool','tmux').
             match='backend' (the message contains 'backend'). Anchor on test_valid_device_values_load's
             3-line body (avoids the blank-line-count ambiguity before the lite_model section)."

# MUST READ — the downstream gate (make_backend) + its test (DO NOT EDIT either — verify they stay green)
- file: voice_typing/typing_backends.py
  why: "make_backend (L142) raises `ValueError(f'unknown output.backend: {backend!r}')` — the defensive
        second gate the contract says to KEEP UNCHANGED. With __post_init__, make_backend can no longer
        receive an invalid-backend OutputConfig (construction rejects it first), but it is retained as
        defense-in-depth."
  critical: "DO NOT modify make_backend(). Its ValueError is now unreachable via normal construction but
             stays as a defensive gate (contract mandate)."
- file: tests/test_typing_backends.py
  why: "test_make_backend_unknown_raises_value_error (L236-238): `with pytest.raises(ValueError, match='bogus'):
        make_backend(OutputConfig(backend='bogus'))`. After __post_init__, OutputConfig(backend='bogus')
        raises ValueError at CONSTRUCTION (before make_backend) — the test STILL PASSES (pytest.raises
        catches it; match='bogus' holds because the message is '… got 'bogus''). NO edit needed."
  critical: "DO NOT edit this test. It stays GREEN. (Research §4.) If you 'fix' it you are changing a
             passing test for no reason."

# CONTEXT — the bug-report source (READ-ONLY)
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/prd_snapshot.md
  why: "§2.3/§3.2 Issue 3: the silent-load → make_backend crash-loop root cause + the prescribed
        OutputConfig.__post_init__ fix (verbatim). Confirms the approach + the ValueError choice."
  critical: "Do NOT edit the prd_snapshot (READ-ONLY). The fix code in the report is the contract."

# CONTEXT — the parallel task (DISJOINT; confirms config.py is NOT edited by it)
- file: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/P1M2T1S1/PRP.md
  why: "P1.M2.T1.S1 (IN PARALLEL) edits voice_typing/daemon.py + tests/test_daemon.py (the _final_pending
        reset in _arm/_disarm). It does NOT touch config.py / test_config.py / typing_backends.py /
        test_typing_backends.py. Zero overlap with this task."
  critical: "No conflict. This task = config.py + test_config.py; P1.M2.T1.S1 = daemon.py + test_daemon.py."
```

### Current Codebase tree (state at P1.M3.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── config.py            # <-- EDIT: OutputConfig.__post_init__ (mirror AsrConfig device validation).
│   └── typing_backends.py   # UNCHANGED (make_backend keeps its ValueError as the defensive 2nd gate).
└── tests/
    ├── test_config.py       # <-- EDIT: +2 tests (mirror VT-005 device tests L172-183). TDD RED first.
    └── test_typing_backends.py  # UNCHANGED (test_make_backend_unknown stays GREEN — no edit).
# daemon.py/test_daemon.py: P1.M2.T1.S1 (parallel — _final_pending reset). README: P1.M4.T1 (consistency).
```

### Desired Codebase tree with files to be added

```bash
voice_typing/config.py      # MODIFIED: +OutputConfig.__post_init__ (backend enum validation, ValueError).
tests/test_config.py        # MODIFIED: +test_invalid_backend_value_raises + test_valid_backend_values_load.
# NOTHING ELSE. typing_backends.py / test_typing_backends.py UNCHANGED. No new files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — USE ValueError (NOT TypeError). The TYPE is correct (str); the VALUE is not. This mirrors
#   the AsrConfig device validation (`if self.device not in ('cuda','cpu'): raise ValueError(...)`). The
#   tests use `pytest.raises(ValueError, match='backend')`. A TypeError would be wrong + fail the tests.
#   (Research §1.)

# CRITICAL #2 — THE MESSAGE MUST CONTAIN 'backend' AND THE BAD VALUE. The new tests use match='backend';
#   the existing test_make_backend_unknown_raises_value_error uses match='bogus'. The message
#   f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}' satisfies BOTH
#   (contains 'backend' AND renders the bad value, e.g. 'bogus'). Do NOT reword it to drop either.

# CRITICAL #3 — test_make_backend_unknown_raises_value_error STAYS GREEN; DO NOT EDIT IT. After __post_init__,
#   OutputConfig(backend='bogus') raises ValueError at CONSTRUCTION (before make_backend). The test's
#   `pytest.raises(ValueError, match='bogus')` still catches it. Verify it passes; do NOT modify it.
#   (Research §4.) Likewise DO NOT modify make_backend() — it stays as the defensive second gate.

# CRITICAL #4 — TDD: TESTS FIRST (RED), THEN THE FIX (GREEN). Add the 2 tests to test_config.py FIRST,
#   run, and confirm test_invalid_backend_value_raises FAILS (OutputConfig has no __post_init__ -> from_toml
#   loads 'wtyp' without raising -> pytest.raises sees no exception -> FAIL). Then add OutputConfig.__post_init__
#   -> both new tests pass. (Research §3.) Do not add the fix before the tests.

# CRITICAL #5 — VALID LIST IS EXACTLY ('wtype','ydotool','tmux'). These are the 3 backends make_backend
#   builds (_WtypeWithFallback / YdotoolBackend / TmuxBackend). Do NOT add 'auto' or any sentinel.
#   config.toml uses backend='wtype' (valid) -> test_repo_config_toml_equals_defaults stays green.

# CRITICAL #6 — @dataclass IS ON OutputConfig (config.py L118, verified). So __post_init__ auto-fires on
#   every OutputConfig(**section). No extra wiring. (Research §2.1.)

# GOTCHA #7 — config.py IS STDLIB-ONLY (os, tomllib, dataclasses, pathlib). The __post_init__ adds ZERO
#   imports (a tuple literal + an f-string). Do NOT import cuda/torch/realtimestt. (Research §6.)

# GOTCHA #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest).
#   timeout 60 wrapper (the contract's form). mypy NOT installed — do NOT run it. ruff optional
#   (/home/dustin/.local/bin/ruff, NOT in .venv).
```

## Implementation Blueprint

### Data models and structure

No data-model change. One new method (`OutputConfig.__post_init__`) that validates the existing `backend` field's value at construction. No new fields, no coercion, no new classes.

### Implementation Tasks (ordered — TDD: tests RED first, then fix GREEN)

```yaml
Task 1: EDIT tests/test_config.py — add the 2 backend tests (TDD RED step, written FIRST)
  - PLACE: immediately after test_valid_device_values_load (the VT-005 device test, L179-183). Anchor on
    its 3-line body (unique; avoids blank-line-count ambiguity).
  - ADD (mirror the device tests EXACTLY): a section comment + test_invalid_backend_value_raises +
    test_valid_backend_values_load. Verbatim newText in "Edit T1" below.
  - RED CHECK: run `timeout 60 .venv/bin/python -m pytest tests/test_config.py -q -k backend` —
    test_invalid_backend_value_raises FAILS (no validation yet); test_valid_backend_values_load PASSES.
  - EXACT oldText→newText: see Edit T1.

Task 2: EDIT voice_typing/config.py — OutputConfig.__post_init__ (GREEN step)
  - PLACE: after the append_space field, before @dataclass FeedbackConfig.
  - BODY: `if self.backend not in ('wtype','ydotool','tmux'): raise ValueError(f'[output] backend must be
    "wtype", "ydotool", or "tmux", got {self.backend!r}')` + a comment naming the VT-005 precedent +
    make_backend-as-2nd-gate note.
  - GREEN CHECK: re-run the Task-1 tests — both PASS.
  - EXACT oldText→newText: see Edit C1.

Task 3: VERIFY — no regression in the downstream gate + the repo-default drift guard
  - RUN: timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_typing_backends.py -q
  - EXPECTED: all pass. test_make_backend_unknown_raises_value_error STAYS GREEN (no edit). The repo-default
    drift guard stays green (config.toml backend='wtype' is valid).
  - DO NOT edit typing_backends.py / test_typing_backends.py.

Task 4: VALIDATE (no further file change — see Validation Loop)
  - No git commit unless the orchestrator directs it.
```

### Edits — verbatim oldText → newText

#### Edit T1 — `tests/test_config.py` add 2 backend tests after `test_valid_device_values_load`

`oldText` (the device test's body — unique):
```
    for good in ("cuda", "cpu"):
        cfg = VoiceTypingConfig.from_toml({"asr": {"device": good}})
        assert cfg.asr.device == good
```
`newText` (the same body + the new section comment + 2 tests):
```
    for good in ("cuda", "cpu"):
        cfg = VoiceTypingConfig.from_toml({"asr": {"device": good}})
        assert cfg.asr.device == good


# ---------------------------------------------------------------------------
# output.backend enum validation (bugfix Issue 3 / VT-005 precedent): only "wtype" |
# "ydotool" | "tmux" are valid. A typo such as "wtyp" is a valid str but would otherwise
# flow into typing_backends.make_backend() and raise there — under systemd a
# Restart=on-failure crash-loop. Reject at load with a clear ValueError (TYPE correct,
# VALUE not — mirrors asr.device). make_backend() keeps its own ValueError as a 2nd gate.
# ---------------------------------------------------------------------------


def test_invalid_backend_value_raises():
    """bugfix Issue 3: a backend value outside {wtype, ydotool, tmux} is rejected at load with a ValueError naming it."""
    for bad in ("wtyp", "xterm", "WTYPE", "", "auto", "gpu"):
        with pytest.raises(ValueError, match="backend"):
            VoiceTypingConfig.from_toml({"output": {"backend": bad}})


def test_valid_backend_values_load():
    """bugfix Issue 3: 'wtype', 'ydotool', 'tmux' are the accepted backend values and round-trip through TOML."""
    for good in ("wtype", "ydotool", "tmux"):
        cfg = VoiceTypingConfig.from_toml({"output": {"backend": good}})
        assert cfg.output.backend == good
```

#### Edit C1 — `voice_typing/config.py` `OutputConfig.__post_init__`

`oldText` (the append_space field + the blanks + the FeedbackConfig header — unique):
```
    append_space: bool = True  # daemon appends one trailing space after each final


@dataclass
class FeedbackConfig:
```
`newText` (insert __post_init__ between append_space and @dataclass FeedbackConfig):
```
    append_space: bool = True  # daemon appends one trailing space after each final

    def __post_init__(self) -> None:
        # backend VALUE validation (bugfix Issue 3 / VT-005 precedent): only "wtype" | "ydotool" |
        # "tmux" are valid. A typo such as backend="wtyp" is a valid str, but it would otherwise flow
        # into typing_backends.make_backend() -> VoiceTypingDaemon.__init__() and raise there — under
        # systemd that is a Restart=on-failure crash-loop discoverable only via journalctl. Reject it
        # here at load time with a clear ValueError (the TYPE is correct, the VALUE is not — mirrors
        # AsrConfig's device validation). make_backend() retains its own ValueError as a defensive
        # second gate.
        if self.backend not in ("wtype", "ydotool", "tmux"):
            raise ValueError(
                f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}'
            )


@dataclass
class FeedbackConfig:
```

> **Why these edits:** Edit T1 is the TDD RED step (the invalid-value test fails until the fix). Edit C1 mirrors AsrConfig's device validation line-for-line (ValueError, `[output] backend…`, the `not in (...)` guard). The message contains both `backend` (for the new tests' `match="backend"`) and the bad value (for the existing `match="bogus"`). `make_backend()` and its test are deliberately UNCHANGED — the contract keeps make_backend as the defensive second gate, and its test stays green because the ValueError now fires at `OutputConfig` construction (still caught by `pytest.raises`). No other files change.

### Implementation Patterns & Key Details

```python
# (1) The validation mirrors AsrConfig's device check EXACTLY (Critical #1):
if self.backend not in ("wtype", "ydotool", "tmux"):
    raise ValueError(f'[output] backend must be "wtype", "ydotool", or "tmux", got {self.backend!r}')
#   ValueError (not TypeError): the TYPE is correct (str), the VALUE is not.

# (2) __post_init__ fires at LOAD time via from_toml._overlay -> OutputConfig(**section):
#     VoiceTypingConfig.from_toml({"output": {"backend": "wtyp"}}) -> raises ValueError BEFORE the daemon
#     starts. Fail-fast at the config layer (not in make_backend at daemon init).

# (3) The message must satisfy TWO match= checks: 'backend' (new tests) + the bad value (make_backend test
#     uses match='bogus' -> OutputConfig(backend='bogus') now raises '… got 'bogus'' at construction;
#     pytest.raises catches it; the test STAYS GREEN with no edit). (Critical #2/#3.)

# (4) TDD order: tests FIRST (Edit T1) -> RED -> fix (Edit C1) -> GREEN. (Critical #4.)
```

### Integration Points

```yaml
CONFIG (OutputConfig):
  - add method: "__post_init__ — validates backend ∈ {wtype,ydotool,tmux}; raises ValueError otherwise"
LOAD PATH (VoiceTypingConfig.from_toml._overlay):
  - unchanged: "section_cls(**section) -> OutputConfig(**section) now triggers __post_init__ -> ValueError propagates (not caught)"
DOWNSTREAM (typing_backends.make_backend):
  - unchanged: "retains its own ValueError as a defensive second gate (now unreachable via normal construction; kept per contract)"
TESTS:
  - test_config.py: "+test_invalid_backend_value_raises + test_valid_backend_values_load (mirror VT-005 device tests)"
  - test_typing_backends.py: "UNCHANGED (test_make_backend_unknown_raises_value_error stays GREEN)"
CONSUMERS: none changed (valid configs load identically; invalid configs now fail at load with a clear message)
```

## Validation Loop

> pytest is the gate (.venv/bin/python). FULL PATHS (zsh aliases). `timeout 60` wrapper (the contract's
> form). mypy NOT installed (skip). ruff optional (/home/dustin/.local/bin/ruff, NOT in .venv).

### Level 1: Syntax + wiring

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/config.py tests/test_config.py && echo "L1 py_compile OK"
grep -n "def __post_init__" voice_typing/config.py   # expect: now present in OutputConfig (was: only AsrConfig + FeedbackConfig)
grep -nE 'def test_invalid_backend_value_raises|def test_valid_backend_values_load' tests/test_config.py  # expect: both present
grep -nE 'backend must be' voice_typing/config.py     # expect: the ValueError message
# Expected: py_compile OK; OutputConfig has __post_init__; both new tests present; the message present.
```

### Level 2: Unit Tests (THE gate — TDD RED then GREEN, then no regression)

```bash
cd /home/dustin/projects/voice-typing
# (RED step — after Edit T1, BEFORE Edit C1): the invalid-value test FAILS.
timeout 60 .venv/bin/python -m pytest tests/test_config.py -q -k backend
# Expected (RED): test_invalid_backend_value_raises FAILS (no validation yet); test_valid_backend_values_load passes.
# (GREEN step — after Edit C1): both pass.
timeout 60 .venv/bin/python -m pytest tests/test_config.py -q -k backend
# Expected (GREEN): both pass.
# No regression — config + drift guard + the downstream typing-backend tests:
timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_typing_backends.py -q
# Expected: all pass. test_repo_config_toml_equals_defaults (config.toml backend='wtype' is valid);
#   test_make_backend_unknown_raises_value_error STAYS GREEN (ValueError now fires at OutputConfig construction).
```

### Level 3: The contract proof (load-time fail-fast)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import pytest
from voice_typing.config import VoiceTypingConfig, OutputConfig
# (a) invalid -> ValueError at LOAD time, message names 'backend' + the bad value
with pytest.raises(ValueError, match="backend") as e:
    VoiceTypingConfig.from_toml({"output": {"backend": "wtyp"}})
assert "wtyp" in str(e.value), str(e.value)
# (b) valid backends load + round-trip
for good in ("wtype", "ydotool", "tmux"):
    assert VoiceTypingConfig.from_toml({"output": {"backend": good}}).output.backend == good
# (c) the default still constructs fine
OutputConfig(); assert OutputConfig().backend == "wtype"
# (d) the make_backend path: OutputConfig(backend='bogus') raises at construction now
with pytest.raises(ValueError, match="bogus"):
    OutputConfig(backend="bogus")
print("L3 OK: invalid backend -> ValueError at load (names field+value); valid backends load; default OK; bogus caught")
PY
# Expected: prints "L3 OK: ..."; exit 0.
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY config.py + test_config.py changed by THIS task ---"
git status --porcelain
# Expected: " M voice_typing/config.py" + " M tests/test_config.py" (this task). daemon.py/test_daemon.py
#   (if present) belong to P1.M2.T1.S1 (parallel) — NOT this task. typing_backends.py / test_typing_backends.py
#   MUST be absent (UNCHANGED). Any M to those = scope violation.
echo "--- typing_backends.py + its test UNCHANGED ---"
git status --porcelain voice_typing/typing_backends.py tests/test_typing_backends.py   # expect: empty
echo "--- make_backend still has its own ValueError (defensive 2nd gate) ---"
grep -n 'unknown output.backend' voice_typing/typing_backends.py   # expect: still present (unchanged)
```

## Final Validation Checklist

### Technical Validation
- [ ] `.venv/bin/python -m py_compile voice_typing/config.py tests/test_config.py` exits 0.
- [ ] `grep 'def __post_init__' voice_typing/config.py` → present in OutputConfig.
- [ ] TDD: after Edit T1 (before C1) `test_invalid_backend_value_raises` FAILS; after Edit C1 BOTH pass.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_typing_backends.py -q` → all pass.

### Feature Validation
- [ ] `from_toml({"output": {"backend": "wtyp"}})` → `ValueError` at load, message contains `backend` + `wtyp`.
- [ ] `wtype`/`ydotool`/`tmux` each load + round-trip.
- [ ] `make_backend()` UNCHANGED; `test_make_backend_unknown_raises_value_error` stays GREEN.
- [ ] The L3 contract-proof script prints `L3 OK`.

### Code Quality Validation
- [ ] `ValueError` (not TypeError); message mirrors AsrConfig's device-validation format.
- [ ] `__post_init__` placed after the fields, before `@dataclass FeedbackConfig`.
- [ ] config.py stays stdlib-only (no new imports).
- [ ] Only `voice_typing/config.py` + `tests/test_config.py` modified; `typing_backends.py`/`test_typing_backends.py` UNCHANGED.

### Documentation & Deployment
- [ ] The `__post_init__` comment names the VT-005 precedent + the make_backend-2nd-gate note.
- [ ] No README edit here (already documents valid values; P1.M4.T1 verifies changeset consistency).

---

## Anti-Patterns to Avoid

- ❌ Don't raise TypeError — the TYPE (str) is correct; the VALUE is not → ValueError (mirrors device) (Critical #1).
- ❌ Don't add the fix before the tests — TDD: Edit T1 (RED) first, then Edit C1 (GREEN) (Critical #4).
- ❌ Don't edit `test_typing_backends.py::test_make_backend_unknown_raises_value_error` — it STAYS GREEN (the ValueError now fires at `OutputConfig` construction; `pytest.raises(match="bogus")` still catches it) (Critical #3).
- ❌ Don't edit `typing_backends.py::make_backend` — it keeps its ValueError as the defensive second gate (contract mandate) (Critical #3).
- ❌ Don't reword the message to drop `backend` or the bad value — both are matched by tests (`match="backend"` + `match="bogus"`) (Critical #2).
- ❌ Don't add `auto`/sentinels to the valid list — exactly `("wtype","ydotool","tmux")` (Critical #5).
- ❌ Don't import cuda/torch/realtimestt into config.py — it stays stdlib-only (Gotcha #7).
- ❌ Don't edit daemon.py/test_daemon.py (P1.M2.T1.S1 parallel) or README (P1.M4.T1) — out of scope.
- ❌ Don't run `mypy` — not installed; pytest is the gate (Gotcha #8).

---

**Confidence Score: 9.5/10** for one-pass success. The change is small and fully bounded: a 3-line `__post_init__` mirroring an existing precedent (AsrConfig device validation, verbatim) + two tests mirroring the VT-005 device tests (verbatim bad/good lists). The RED→GREEN flow is explicit; the one tricky point (`test_make_backend_unknown_raises_value_error` staying green because the ValueError now fires at construction) is proven + flagged as a NON-EDIT; the regression scan verified no other `OutputConfig(...)` construction breaks; and the edit anchors are byte-exact + unique. The −0.5 reserves: an implementer could instinctively "fix" the (still-passing) make_backend test or add the fix before the tests — but the Critical-#3/#4 guardrails + the grep gates (only config.py + test_config.py modified; typing_backends.py unchanged; both new tests pass) catch those structurally.