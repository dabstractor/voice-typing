# Research — P1.M3.T3.S1: output.delivery key + precondition triple enforcement

## §0. What exists at start (verified live)

- `voice_typing/config.py:140-168` — `OutputConfig` dataclass: `backend` ("wtype"|"ydotool"|"null"),
  `append_space: bool = True`, `streaming: bool = True`. `__post_init__` (config.py:148) validates:
  backend value → **ValueError** ("the TYPE is correct, the VALUE is not — mirrors AsrConfig's device
  validation"); streaming type → TypeError (bool fields reject int).
- **`graceful_stop` lives in `[asr]`** (AsrConfig field, config.py:~96-99; config.toml:31) — NOT in
  `[output]` as PRD §4.5's listing shows. **`keypress_action` lives in `[cancel]`** (CancelConfig,
  config.py:~176-177; config.toml:53). So the precondition triple spans THREE sections — it CANNOT be
  validated inside OutputConfig.__post_init__ (which never sees asr/cancel).
- `VoiceTypingConfig` (top-level) has **NO `__post_init__`** — only the 6 sub-configs do. Cross-section
  validation needs a NEW top-level `__post_init__` on `VoiceTypingConfig` (runs after all field
  default_factory constructions + after from_toml's overlay → both load paths covered).
- `tests/test_config_repo_default.py:37-63` — `test_repo_config_toml_has_no_extra_keys`: expected set
  currently **26 keys**; `"output": {"backend", "append_space", "streaming"}` (line ~52). Goes 26→27
  with `delivery` added to the output set. Also `test_repo_config_toml_equals_defaults` (repo
  config.toml must equal dataclass defaults — so config.py and config.toml MUST change in lockstep or
  this test fails).
- `config.toml` — 7 tables, 26 keys total (asr 11, output 3, cancel 3, audio 2, feedback 4, filter 2,
  log 1). `[output]` at lines 45-50. `[audio]` already landed (P1.M2.T1.S1 did 24→26).
- `tests/test_config.py` — the config test conventions: plain functions, direct constructor calls
  (`OutputConfig(backend="wtyp")`) for value-validation tests (e.g. `test_invalid_backend_value_raises`
  :384, `test_duck_mode_rejects_unknown_value` :258), `pytest.raises` with match, TOML round-trip via
  `from_toml` dict literals for happy paths. No fixtures beyond monkeypatch.
- Validation-style precedent: **TypeError = wrong type / unknown key; ValueError = right type, wrong
  value** (device VT-005, backend Issue 3 — both cited in OutputConfig.__post_init__ comments).

## §1. The contract (PRD §4.5 [output] + §4.2sexies)

PRD §4.5:
```toml
delivery = "stream-edit"  # Rev 4 §4.2sexies: "bulk-text" = paste-as-policy output path
                          # ... "stream-edit" = today's behavior (default until G6 graduation).
                          # bulk-text requires streaming=true, graceful_stop=false, keypress_action="disarm".
```
Item contract: default stays `"stream-edit"` (opt-in until G6); enforcement at LOAD: `bulk-text` with
any of the triple violated → a clear **ValueError naming all three violated keys** (name the violated
ones; collect ALL violations into ONE error, don't fail on the first). Value validation:
`delivery not in ("stream-edit", "bulk-text")` → ValueError (device/backend precedent). Type: must be
str → TypeError (string-field precedent).

## §2. Design pinned

1. **OutputConfig** gains `delivery: str = "stream-edit"` + in its `__post_init__`:
   - str type check → TypeError;
   - value ∈ ("stream-edit","bulk-text") → ValueError.
2. **NEW `VoiceTypingConfig.__post_init__`**: if `self.output.delivery == "bulk-text"`, collect
   violated preconditions from the three sections:
   - `not self.output.streaming` → violated: `output.streaming`
   - `self.asr.graceful_stop` (note: **[asr]**, not [output]!) → violated: `asr.graceful_stop`
   - `self.cancel.keypress_action != "disarm"` → violated: `cancel.keypress_action`
   If any: raise `ValueError` naming all violated keys, e.g.:
   `output.delivery="bulk-text" requires [output] streaming=true (got false), [asr] graceful_stop=false (got true), [cancel] keypress_action="disarm" (got "freeze")` — build the message from the collected list, prefix with `output.delivery="bulk-text" requires`, one clause per violation with section-qualified key + got-value.
   Why top-level post-init: single-flight for both construction paths (`VoiceTypingConfig()` defaults
   and `from_toml` overlay), sees all three sections, and default config (delivery="stream-edit")
   short-circuits → zero behavior change at default (the item's "no legacy config behavior change"
   input constraint).
3. **config.toml [output]**: add `delivery = "stream-edit"` line after `streaming` with a Mode A
   comment: opt-in status ("default until G6 graduation" — PRD §4.2sexies), the bulk-text triple
   precondition, "stream-edit" = today's behavior.
4. **Key-set pin** 26→27: add `"delivery"` to the output set in
   `test_repo_config_toml_has_no_extra_keys` + update the docstring "the 26 schema keys" → 27.
5. **tests/test_config.py** additions (follow existing conventions): value-validation tests via
   direct constructor (invalid delivery string → ValueError; non-str delivery → TypeError);
   precondition-matrix tests via `VoiceTypingConfig(...)` / `from_toml` dict: bulk-text + all three OK
   → loads; each single violation → ValueError naming exactly that key; two violations → names both;
   stream-edit + any violation combination → loads fine (no enforcement outside bulk-text); default
   VoiceTypingConfig() → delivery == "stream-edit" (defaults test update: test_defaults_match_prd_4_5
   asserts per-field defaults — add delivery).
   Edge: constructing `VoiceTypingConfig(output=OutputConfig(delivery="bulk-text"))` with default
   asr/cancel → streaming default True ok, graceful_stop default False ok, keypress_action default
   "disarm" ok → LOADS (all-defaults satisfy the triple). Good — the guard only fires on explicit
   opt-out combos.

## §3. Coordination / boundaries

- Parallel item **P1.M3.T2.S3** (G2 gate) touches `bulk_controller.py`/tests — disjoint from config.
  Do NOT touch bulk_controller/bulk_delivery.
- **P1.M3.T3.S2** (next): delivery status surface — feedback fields + voicectl status. Do NOT touch
  feedback.py/ctl.py here.
- The daemon does NOT consume `delivery` yet (wiring is P1.M6.T2.S1); this task is config surface +
  load-time gate only. `grep -rn 'output.delivery\|cfg.output.delivery' voice_typing/` currently has
  no consumer — expected; do not add one.
- P1.M2.T1.S1 already landed [audio] 24→26; this takes 26→27. No conflict.

## §4. Validation commands (verified style)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q
timeout 60 .venv/bin/python -c "from voice_typing.config import VoiceTypingConfig; VoiceTypingConfig().from_toml({'output': {'delivery': 'bulk-text'}}) if False else None; print('import ok')"
# negative smoke: bulk-text + streaming=false must raise ValueError naming output.streaming:
timeout 60 .venv/bin/python -c "
from voice_typing.config import VoiceTypingConfig
try:
    VoiceTypingConfig.from_toml({'output': {'delivery': 'bulk-text', 'streaming': False}})
    print('FAIL: no error')
except ValueError as e:
    print('ok:', 'output.streaming' in str(e))"
```
Full-suite scope check: `git status --porcelain` → only voice_typing/config.py, config.toml,
tests/test_config.py, tests/test_config_repo_default.py.
