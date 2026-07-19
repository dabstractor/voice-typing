# Research — P1.M3.T1.S1 OutputConfig.__post_init__ backend value validation (bugfix Issue 3)

Ground truth verified by reading `voice_typing/config.py` + `tests/test_config.py` +
`tests/test_typing_backends.py` + `voice_typing/typing_backends.py` on 2026-07-19. This is bugfix
**Issue 3 (Minor)**: an invalid `output.backend` (e.g. typo `"wtyp"`) loads silently today and only
fails later in `make_backend()` (a systemd crash-loop). Fix = fast-fail at LOAD time with a clear
`ValueError`, mirroring the existing `asr.device` validation (VT-005). TDD: tests RED first, then
the one-method fix.

---

## 1. The precedent (AsrConfig.__post_init__ device validation — mirror it EXACTLY)

`voice_typing/config.py` AsrConfig.__post_init__ already validates the `device` enum at load time:
```python
        if self.device not in ("cuda", "cpu"):
            raise ValueError(
                f'[asr] device must be "cuda" or "cpu", got {self.device!r}'
            )
```
**ValueError (not TypeError)** — the TYPE is correct (str), the VALUE is not. The OutputConfig
backend validation mirrors this line-for-line (`("wtype","ydotool","tmux")` + `[output] backend…`).

## 2. The edit sites (verified live)

### 2.1 config.py OutputConfig (line 118-125) — currently has NO __post_init__
```
@dataclass                              # L118
class OutputConfig:                     # L119
    """[output] — typing-output backend selection."""
    backend: str = "wtype"              # L121
    tmux_target: str = ""
    append_space: bool = True
                                        # (blank)
@dataclass                              # → FeedbackConfig
class FeedbackConfig:
```
`@dataclass` IS on OutputConfig (L118 — verified), so a `__post_init__` auto-fires on every
`OutputConfig(**section)` construction. Insert the method after `append_space`, before `@dataclass
FeedbackConfig`. The `from_toml._overlay` path (config.py:238-244 `return section_cls(**section)`)
calls `OutputConfig(**section)` → `__post_init__` fires at LOAD time. ✓

### 2.2 test_config.py — the VT-005 device tests to MIRROR (L172-183, VERIFIED present)
```python
def test_invalid_device_value_raises():
    """VT-005: a device value outside {cuda, cpu} is rejected at load with a ValueError naming it."""
    for bad in ("gpu", "cud", "CUDA", "cuda ", "auto", ""):
        with pytest.raises(ValueError, match="device"):
            VoiceTypingConfig.from_toml({"asr": {"device": bad}})

def test_valid_device_values_load():
    """VT-005: 'cuda' and 'cpu' are the accepted device values and round-trip through TOML."""
    for good in ("cuda", "cpu"):
        cfg = VoiceTypingConfig.from_toml({"asr": {"device": good}})
        assert cfg.asr.device == good
```
(The contract's claimed names/lines were ACCURATE — my first grep pattern was just too narrow.)
The two NEW backend tests mirror these EXACTLY: `for bad in ("wtyp","xterm","WTYPE","","auto","gpu")`
+ `match="backend"`; `for good in ("wtype","ydotool","tmux")` + `assert cfg.output.backend == good`.
Place them right after `test_valid_device_values_load` (anchor on its 3-line body — avoids the
blank-line-count ambiguity before the lite_model section).

## 3. The RED → GREEN TDD flow (the contract mandates tests FIRST)

- **RED (test_config.py added, config.py unchanged):** `test_invalid_backend_value_raises` does
  `from_toml({"output": {"backend": "wtyp"}})` expecting ValueError. OutputConfig has no
  `__post_init__` → from_toml loads `"wtyp"` WITHOUT raising → `pytest.raises(ValueError)` sees NO
  exception → the test FAILS (RED). `test_valid_backend_values_load` passes even in RED (valid
  backends load today). So: add tests → run → exactly ONE new test fails (the invalid-value one).
- **GREEN (add OutputConfig.__post_init__):** the invalid value now raises ValueError at
  construction → from_toml propagates it → `pytest.raises` catches it + `match="backend"` holds
  (the message is `[output] backend must be …`). Both new tests pass.

## 4. The make_backend downstream test STAYS GREEN (no edit needed — verified)

`tests/test_typing_backends.py:236-238`:
```python
def test_make_backend_unknown_raises_value_error():
    with pytest.raises(ValueError, match="bogus"):
        make_backend(OutputConfig(backend="bogus"))
```
With the new `__post_init__`, `OutputConfig(backend="bogus")` raises ValueError at CONSTRUCTION
(before `make_backend` is called — Python evaluates the arg first). The test STILL PASSES:
`pytest.raises(ValueError, match="bogus")` catches it (the message `… got 'bogus'` contains
"bogus"). **No edit to this test or to `make_backend()`** — the contract says keep make_backend as
the defensive second gate. (make_backend's own ValueError is now unreachable via any OutputConfig
construction, but it is retained as defense-in-depth per the contract.)

## 5. Regression scan — NO other test breaks (verified)

Grepped every `OutputConfig(...)` construction in tests/. ALL use a VALID backend (`"tmux"`,
`"wtype"`, `"ydotool"`) EXCEPT the one `"bogus"` in §4 (stays green). config.toml uses
`backend = "wtype"` (valid) → `test_repo_config_toml_equals_defaults` stays green. → The ONLY test
files this task touches: `tests/test_config.py` (adds 2 tests). `tests/test_typing_backends.py` is
UNCHANGED (its `backend="bogus"` test stays green). `config.py` gets the one method. No other files.

## 6. Scope + tooling

- **config.py is stdlib-only** (os, tomllib, dataclasses, pathlib). NO cuda/torch/realtimestt imports.
  The `__post_init__` adds zero imports (a tuple literal + an f-string).
- **Files touched:** `voice_typing/config.py` (OutputConfig + 1 method) + `tests/test_config.py`
  (+ 2 tests). NOT `typing_backends.py` (make_backend unchanged), NOT `test_typing_backends.py`
  (stays green), NOT README (already documents valid values — P1.M4.T1 verifies consistency),
  NOT daemon.py/test_daemon.py (the parallel P1.M2.T1.S1 owns the `_final_pending` reset there —
  DISJOINT: it edits daemon.py + test_daemon.py, never config.py).
- **Validation:** `timeout 60 .venv/bin/python -m pytest tests/test_config.py -q` +
  `tests/test_config_repo_default.py -q` + `tests/test_typing_backends.py -q`. All pass. FULL PATHS
  (.venv/bin/python — zsh aliases). mypy NOT installed — do NOT run it. ruff optional
  (/home/dustin/.local/bin/ruff).
- **Error message must contain "backend"** (the tests use `match="backend"`) AND the bad value
  (the make_backend test uses `match="bogus"`). The message `f'[output] backend must be "wtype",
  "ydotool", or "tmux", got {self.backend!r}'` satisfies BOTH. ✓