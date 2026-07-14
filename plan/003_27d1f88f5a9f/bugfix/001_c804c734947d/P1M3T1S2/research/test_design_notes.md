# P1.M3.T1.S2 — Test Design Notes (wrong-typed config values raise TypeError at load)

**Goal:** Add committed pytest to `tests/test_config.py` proving wrong-typed config values raise
`TypeError` at LOAD time (via `VoiceTypingConfig.from_toml`), hardening bugfix Issue 4 / PRD §4.5.
This is a **test-only** subtask; it consumes the `AsrConfig.__post_init__` + `FeedbackConfig.__post_init__`
that P1.M3.T1.S1 implements. **VERIFIED:** the 7-test section below passes against the real
`config.py` (S1 has landed) — full copied file ran **28 passed** (21 prior + 7 new) on 2026-07-14.

---

## 1. The contract under test (S1 / P1.M3.T1.S1 — landed in config.py)

`AsrConfig.__post_init__` (config.py:65) + `FeedbackConfig.__post_init__` (config.py:121) validate
field types at construction (= load time, when `from_toml._overlay` does `section_cls(**section)`):

| Field(s) | Accepts | Rejects | Message shape |
|---|---|---|---|
| AsrConfig floats: `post_speech_silence_duration`, `realtime_processing_pause`, `auto_stop_idle_seconds`, `auto_unload_idle_seconds` | int OR float (NOT bool) | str, bool, None, list | `f"[asr] {field} expects a number (int or float), got {type}: {value!r}"` |
| AsrConfig strs: `final_model`, `realtime_model`, `language`, `device` | str | int, float, bool, None | `f"[asr] {field} expects str, got {type}: {value!r}"` |
| FeedbackConfig `notify_ms` | int (NOT bool, NOT float) | bool, float, str, None | `f"[feedback] notify_ms expects int, got {type}: {value!r}"` |

The field name ALWAYS appears in the message → tests assert `match="<field>"`. `from_toml` does NOT
catch the `TypeError` → it propagates out (fail-fast at load, before models load, before systemd loops).

**The bool gotcha (load-bearing):** `isinstance(True, int)` is `True` (bool subclasses int). S1 rejects
bool FIRST (`isinstance(_v, bool) or not isinstance(_v, (int, float))`). Test (b) pins this: `True`
for a float field raises. `notify_ms=True` also raises (test g).

---

## 2. Test design (7 tests; (a)–(e) are the item's prescribed core, f/g are supporting)

| # | Test | Clause | Asserts |
|---|---|---|---|
| a | `test_string_for_float_field_raises` | item (a) | `from_toml({"asr":{"auto_stop_idle_seconds":"thirty"}})` → TypeError; message names field + bad value |
| b | `test_bool_for_float_field_raises` | item (b) | `from_toml({"asr":{"post_speech_silence_duration":True}})` → TypeError (bool gotcha) |
| c | `test_int_for_string_field_raises` | item (c) | `from_toml({"asr":{"device":123}})` → TypeError naming `device` |
| d | `test_valid_types_still_load` | item (d) | `from_toml({"asr":{"auto_stop_idle_seconds":30.0,"post_speech_silence_duration":0.6}})` succeeds; values correct |
| e | `test_int_accepted_for_float` | item (e) | `from_toml({"asr":{"auto_stop_idle_seconds":30}})` succeeds; stays int (not coerced) |
| f | `test_none_for_float_field_raises` | supporting | `None` (a common real-world wrong value) → TypeError; covers the `auto_unload_idle_seconds` field |
| g | `test_notify_ms_wrong_type_raises` | supporting | FeedbackConfig `notify_ms` float/bool/str rejected; int OK (same Issue 4 fix S1 made) |

All use `VoiceTypingConfig.from_toml({...})` (the item's prescribed construction path) — NO direct
`AsrConfig(...)` calls, so the test proves the fail-fast propagates through the LOAD path, not just
construction. The existing `test_from_toml_unknown_key_raises` is the style template.

---

## 3. Insertion point + style

- **Insert** in the `# from_toml / from_toml_file` section, immediately AFTER
  `test_from_toml_section_not_a_table_raises` (tests/test_config.py ~line 125) and BEFORE
  `test_from_toml_file_reads_toml` (~line 128) — right next to the sibling validation tests
  (`test_from_toml_unknown_key_raises`, `test_from_toml_section_not_a_table_raises`).
- **Style** mirrors the file: section-divider comment block + one-line docstring per test;
  `pytest.raises(TypeError)` / `pytest.raises(TypeError, match=...)` / `pytest.raises(...) as excinfo`;
  no new imports (`pytest`, `VoiceTypingConfig`, `AsrConfig`, `FeedbackConfig` already imported).
- **DO NOT** create a new test file; **DO NOT** edit `config.py` (S1 owns it); **DO NOT** add
  `tests/__init__.py`.

---

## 4. Tooling reality (confirmed live 2026-07-14)

- **Run:** `.venv/bin/python -m pytest tests/test_config.py -v` (zsh aliases `python`→`uv run`; ALWAYS
  `.venv/bin/python`). Baseline `tests/test_config.py` = **21 passed**; after S2 = **28 passed**.
- **No mypy** (skip). **ruff** optional at `/home/dustin/.local/bin/ruff` (a uv tool, NOT in `.venv`).
- **VERIFIED:** copying test_config.py + appending the 7-test section → `28 passed in 0.03s` against
  the real `voice_typing/config.py`. The verbatim source in the PRP is proven correct.
