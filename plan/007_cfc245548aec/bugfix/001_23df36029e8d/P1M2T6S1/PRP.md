# PRP — P1.M2.T6.S1 (bugfix plan 001_23df36029e8d): Config — reject unknown top-level TOML tables (BUG-006)

## Goal

**Feature Goal**: Make `VoiceTypingConfig.from_toml` raise a loud `TypeError` for any unknown
top-level TABLE (e.g. `[outpt]`, `[cancell]`, `[asr ]`) exactly as it already does for unknown
KEYS, so a typo'd section name can never silently disable an entire feature section.

**Deliverable**: A small change in `voice_typing/config.py` (`from_toml` unknown-table check)
+ unit tests in `tests/test_config.py` (+ one row note in `tests/ACCEPTANCE.md` is NOT required
— documentation sync is P1.M3.T9's scope; do not touch README here).

**Success Definition**: `VoiceTypingConfig.from_toml({"outpt": {"backend": "ydotool"}})`
raises `TypeError` naming the unknown table; the six known tables and all existing
`test_config.py` / `test_config_repo_default.py` tests still pass; the repo's own
`config.toml` still loads.

## Why

- BUG-006 (bugfix PRD §Minor Issue 2): `config.toml`'s header documents "Unknown keys are
  REJECTED at load time", and `_overlay` enforces it per-key via dataclass `__init__`. But
  `from_toml` (config.py:327-354) only reads the six known table names and never checks for
  extras — a typo'd TABLE has a WORSE blast radius than a typo'd key (an entire feature
  silently disabled vs. one loud failure), contradicting the documented fail-fast contract.
- Verified bug: `{'outpt': {'backend': 'ydotool'}}` loads with defaults (backend stays
  `wtype`); `{'output': {'bakend': 'ydotool'}}` raises `TypeError`.

## What

Add an unknown top-level table check to `from_toml`, raising `TypeError` with a message
naming the offending table(s) and the known set, mirroring the existing unknown-key
rejection style.

### Success Criteria

- [ ] `from_toml({"outpt": {...}})` → `TypeError` mentioning `outpt`
- [ ] `from_toml({"asr": {...valid...}, "cancell": {...}})` → `TypeError` (mixed known+unknown)
- [ ] All six known tables alone (`asr`, `output`, `cancel`, `feedback`, `filter`, `log`)
      still load; a subset or empty mapping still loads (defaults)
- [ ] Repo `config.toml` still loads (`test_config_repo_default.py` green)
- [ ] No behavior change outside `from_toml` (loader/search-order/`__post_init__` untouched)

## All Needed Context

### Context Completeness Check

The change is one guarded loop plus tests; everything needed — exact function, line anchors,
known-table list, error-message style, test patterns to copy — is below. No external research
required (stdlib `tomllib`/dataclasses only).

### Documentation & References

```yaml
- file: voice_typing/config.py
  why: THE change site. VoiceTypingConfig.from_toml (:327-354): `_overlay(section_cls,
        table_name)` per section; `cls(asr=_overlay(AsrConfig, "asr"), ...)` for exactly six
        tables: asr, output, cancel, feedback, filter, log. Docstring (:331-338) already
        documents the unknown-KEY TypeError — extend it to mention unknown TABLES.
  pattern: raise TypeError with a bracketed table name, e.g. mirror _overlay's own
        f"[{table_name}] must be a TOML table, got ..." style.
  gotcha: from_toml receives an ALREADY-PARSED mapping (tomllib output) — the check is a
        set difference `set(data) - _KNOWN_TABLES`, not TOML syntax validation. Also
        from_toml_file (:357-362) and load (:367-382) funnel through from_toml, so ONE
        check covers files, explicit paths, and the search order.

- file: tests/test_config.py
  why: Copy the existing unknown-KEY test (:244-248) —
        def test_cancel_unknown_key_raises():
            with pytest.raises(TypeError):
                VoiceTypingConfig.from_toml({"cancel": {"on_backspce": True}})
        Header comment (:1-6) documents run command; imports (:13-22) already include
        VoiceTypingConfig + pytest.
  pattern: pytest.raises(TypeError) + from_toml on a dict literal; optionally
        pytest.raises(..., match=...) to pin the table name in the message.

- file: tests/test_config_repo_default.py
  why: Guards that the repo config.toml itself still loads after the change — this file is
        the regression tripwire for false positives in the new check.
  gotcha: run it after the change; if it fails, your known-table set or check is wrong
        (e.g. you rejected a table config.toml legitimately uses).

- file: config.toml
  why: The shipped default — contains exactly the six known tables; also update its header
        comment line that says "Unknown keys are REJECTED at load time" to say unknown
        keys AND unknown tables (one-line doc sync; the full README sweep stays P1.M3.T9).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/config.py        # from_toml :327-354 (change site); _overlay :340-348
config.toml                   # six tables: asr/output/cancel/feedback/filter/log
tests/test_config.py          # :244-248 unknown-key pattern to mirror
tests/test_config_repo_default.py  # repo-default load tripwire
```

### Desired Codebase tree with files to be added

```bash
voice_typing/config.py        # MODIFIED: from_toml gains unknown-table check (+ module
                              #   constant for the known-table set) + docstring line
config.toml                   # MODIFIED: header comment mentions tables (one line)
tests/test_config.py          # EXTENDED: ~5 new tests
# No new files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# KNOWN-TABLE SET: derive it, don't hand-type it twice — define once, e.g.
#   _KNOWN_TABLES = frozenset({"asr", "output", "cancel", "feedback", "filter", "log"})
# (or derive from the cls field names via dataclasses.fields(VoiceTypingConfig) minus
# classmethods — a literal frozenset is simpler and matches the file's explicitness).
# Order-independent: report ALL unknown tables, or the first — either is fine; naming one
# (sorted first) with the known list in the message is the most actionable.

# ERROR TYPE MUST BE TypeError (not ValueError): the established unknown-key rejection
# surfaces as TypeError via dataclass __init__, and tests + docs describe "raises TypeError".
# Keep the class consistent so callers catch one type.

# EMPTY MAPPING still valid: from_toml({}) -> all defaults (search-order fallback path
# relies on from_toml_file, but unit tests pass {} sometimes). The check must be a
# difference, not a whitelist match requiring all tables present.

# DO NOT validate table CONTENT here (types/values are each section's __post_init__ /
# dataclass __init__ job). This change is purely about top-level keys of the mapping.

# toml comment keys like "# ..." never reach from_toml (tomllib strips them) — no need to
# special-case.
```

## Implementation Blueprint

### Data models and structure

No new models. One module constant:

```python
_KNOWN_TABLES: Final[frozenset[str]] = frozenset(
    {"asr", "output", "cancel", "feedback", "filter", "log"}
)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/config.py — from_toml unknown-table check
  - ADD _KNOWN_TABLES frozenset near VoiceTypingConfig (module level, above the class or
    just inside from_toml's file section; follow the file's ALL-CAPS constant style, cf.
    textproc._TRAILING_PUNCT).
  - ADD at the TOP of from_toml (before _overlay/cls(...)):
        unknown = set(data) - _KNOWN_TABLES
        if unknown:
            raise TypeError(
                "unknown config table(s): "
                + ", ".join(f"[{t}]" for t in sorted(unknown))
                + f"; known tables: {', '.join(sorted(_KNOWN_TABLES))}"
            )
  - EXTEND the from_toml docstring: one sentence noting unknown top-level tables raise
    TypeError the same way unknown keys do (BUG-006).
  - PRESERVE: _overlay, from_toml_file, load, _candidate_paths, all __post_init__ validators.

Task 2: MODIFY config.toml header comment
  - FIND the line documenting "Unknown keys are REJECTED at load time ...".
  - UPDATE to "Unknown keys AND unknown tables are rejected at load time (a typo raises an
    error instead of being silently ignored)". Comment-only change.

Task 3: EXTEND tests/test_config.py
  - ADD tests following the :244-248 pattern (test_<scenario> naming, from_toml on dict
    literals):
    * test_unknown_top_level_table_raises — {"outpt": {"backend": "ydotool"}} ->
      pytest.raises(TypeError, match="outpt")
    * test_unknown_table_alongside_known_raises — {"asr": {...valid minimal...},
      "cancell": {"on_backspace": True}} -> TypeError (proves mixed case, the real-world
      typo scenario from BUG-006's repro)
    * test_unknown_table_empty_mapping_content_raises — {"typo": {}} -> TypeError (a bare
      typo'd section with no keys still fails)
    * test_all_known_tables_load — a mapping containing ALL six tables (each with one
      harmless valid override, e.g. {"asr": {"device": "cuda"}, "output": {"backend":
      "null"}, ...}) loads and reflects one override
    * test_empty_mapping_still_defaults — from_toml({}) == defaults (compare a field)
    * test_known_subset_loads — {"log": {"level": "DEBUG"}} only -> defaults elsewhere
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q

Task 4: FULL FAST-SUITE REGRESSION
  - RUN: timeout 600 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_daemon.py tests/test_control_socket.py -q
    (AGENTS.md: inner timeout + harness timeout above it; single files, not the whole suite)
```

### Implementation Patterns & Key Details

```python
# The whole change (config.py), house style:
_KNOWN_TABLES = frozenset({"asr", "output", "cancel", "feedback", "filter", "log"})

@classmethod
def from_toml(cls, data):
    unknown = set(data) - _KNOWN_TABLES
    if unknown:
        # CRITICAL: TypeError (matches the unknown-key rejection class); message names the
        # typo'd table bracketed like _overlay's own errors so journalctl output is uniform.
        raise TypeError(
            f"unknown config table(s): {', '.join(f'[{t}]' for t in sorted(unknown))}; "
            f"known tables: {', '.join(sorted(_KNOWN_TABLES))}"
        )
    ...  # existing _overlay / cls(...) body unchanged
```

### Integration Points

```yaml
CONFIG:
  - voice_typing/config.py from_toml only. Callers affected (all beneficially):
    from_toml_file, load (search order), tests, install-time smoke. No signature change.
DAEMON/CTL: none — they call config.load(); a typo'd user config now fails loudly at daemon
  start (systemd journal shows the TypeError) instead of silently misconfiguring.
ACCEPTANCE/README: intentionally NOT touched here (P1.M3.T9 owns doc sync).
```

## Validation Loop

### Level 1: Syntax & Style

```bash
timeout 60 .venv/bin/python -c "
from voice_typing.config import VoiceTypingConfig
try:
    VoiceTypingConfig.from_toml({'outpt': {'backend': 'ydotool'}})
    raise SystemExit('FAIL: no error')
except TypeError as e:
    print('OK:', e)
print(VoiceTypingConfig.from_toml({'log': {'level': 'DEBUG'}}).log.level)
"
# Expected: OK: unknown config table(s): [outpt] ... then DEBUG
```

### Level 2: Unit Tests

```bash
timeout 120 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -v
```

### Level 3: Integration

```bash
# Repo default config still loads through the real search order:
timeout 60 .venv/bin/python -c "from voice_typing.config import load; c = load(); print(c.output.backend)"
# Expected: wtype
# A live-daemon check is unnecessary for this pure-loader change; never foreground the daemon (AGENTS.md).
```

### Level 4: Domain-Specific

Not applicable (pure-python loader change; no keystrokes/audio/CUDA).

## Final Validation Checklist

### Technical Validation
- [ ] Level 1 probe prints the TypeError and `DEBUG`
- [ ] tests/test_config.py + tests/test_config_repo_default.py green
- [ ] tests/test_daemon.py + tests/test_control_socket.py green (they load configs)

### Feature Validation
- [ ] Unknown table (alone or mixed with known) raises TypeError naming the table
- [ ] Empty mapping / known subset / all-known-tables still load
- [ ] Repo config.toml loads; its header comment updated (keys AND tables)

### Code Quality
- [ ] `_KNOWN_TABLES` defined once; message style matches existing config errors
- [ ] No changes outside from_toml + the one comment line + tests
- [ ] No new files, no config keys added

## Anti-Patterns to Avoid

- ❌ Don't use ValueError — the established rejection class is TypeError.
- ❌ Don't check unknown tables inside `_overlay` per-section (it only sees known names).
- ❌ Don't make the check require all six tables to be present — subsets/{} must load.
- ❌ Don't sweep README/ACCEPTANCE here — P1.M3.T9.S1/S2 own documentation sync.
- ❌ Don't validate table contents in the new check — that's each section's existing job.
