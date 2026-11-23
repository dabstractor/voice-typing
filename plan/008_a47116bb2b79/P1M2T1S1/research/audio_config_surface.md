# Research: [audio] config surface (P1.M2.T1.S1, D1 ducking — first subtask)

## 1. The recipe (architecture/d1_ducking_seams.md §3 — verified against HEAD)

5 config.py code points + config.toml table + 2 test sites. **Ships `duck_mode="off"`** (default
flips to `"mpris"` in P1.M2.T4 when the ducker lands).

| # | Site (HEAD) | Edit |
|---|---|---|
| 1 | `AudioConfig` after `CancelConfig` (its `__post_init__` ends ~:213, before `@dataclass FeedbackConfig` ~:216) | New dataclass: `duck_mode: str = "off"`, `duck_volume_pct: int = 15` + `__post_init__` guards |
| 2 | `VoiceTypingConfig` fields (:341-346) | `audio: AudioConfig = field(default_factory=AudioConfig)` (after `cancel`) |
| 3 | `_KNOWN_TABLES` frozenset (:337) | add `"audio"` (else `[audio]` → "unknown config table(s)" TypeError) |
| 4 | `from_toml` cls(...) (:385-391) | `audio=_overlay(AudioConfig, "audio"),` (after `cancel=...`); docstring table list gains `[audio]` |
| 5 | config.toml after `[cancel]` (before `[feedback]`, ~:55-60) | `[audio]` table, both keys inline-commented (Mode A) |

## 2. Guard patterns (verbatim from the actual code — the seams doc's "ValueError" sketch is superseded by the REAL keypress_action code, which raises TypeError)

- **duck_mode** (enum) — mirror CancelConfig's keypress_action (config.py:201-206):
  `if self.duck_mode not in ("off", "mpris", "volume"): raise TypeError(f"[audio] duck_mode expects 'off', 'mpris', or 'volume', got {self.duck_mode!r}")`
- **duck_volume_pct** (non-bool int) — mirror the on_backspace bool guard's message shape
  (config.py:~195-199): reject `isinstance(..., bool)` AND require `isinstance(..., int)` →
  `raise TypeError(f"[audio] duck_volume_pct expects int, got {type(...).__name__}: {...!r}")`.
  Type-only (no 0-100 range check — not in the contract; `15` default).

## 3. Key-set pin (verified 24 at HEAD → 26)

`tests/test_config_repo_default.py::test_repo_config_toml_has_no_extra_keys` (:37-63) is the ONLY
key-set pin (grep `expected = {` in test_config.py → 0 hits). Docstring :38 says "only the 24
schema keys". Current: asr 11 + output 3 + cancel 3 + feedback 4 + filter 2 + log 1 = 24. Add
`"audio": {"duck_mode", "duck_volume_pct"}` (placed after "cancel", matching the toml order) → 26;
docstring 24→26. `test_repo_config_toml_equals_defaults` (:16-26) then pins `("off", 15)`
automatically once both sides land (toml table == dataclass defaults).

## 4. Guard tests (tests/test_config.py, beside the wrong-typed region :143-201)

Add a 5-test `[audio]` section: unknown duck_mode value raises (match="duck_mode"); all three enum
values accepted; duck_volume_pct rejects bool; rejects str/float/None/list; defaults are
("off", 15). Pattern precedents: `test_string_for_float_field_raises` (:148-154) and
`_REV2_BOOL_FIELDS` loops (:184+).

## 5. TDD order + why the guard tests are RED pre-implementation

(1) Extend the pin test → RED (config.toml has no `[audio]` → key-set assertion fails).
(2) Add guard tests → RED (`from_toml({"audio": ...})` raises "unknown config table(s): [audio]"
BEFORE reaching duck_mode matching, so `match="duck_mode"` fails; defaults test → AttributeError).
(3) Implement config.py + config.toml → GREEN. Run:
`timeout 300 .venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q`.

## 6. Scope + parallel

Files: `voice_typing/config.py`, `config.toml`, `tests/test_config_repo_default.py`,
`tests/test_config.py`. NOT in scope: feedback `ducked` flag, `audio_ducking.py`, daemon wiring,
ExecStopPost (later D1 subtasks per the seams checklist #4-#8). Parallel P1.M1.T4.S2 touches ONLY
`tests/test_daemon.py` — no overlap. pytest>=9.1.1; full paths + functional `timeout` (AGENTS.md).
