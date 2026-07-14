# Research — P1.M3.T1.S1 __post_init__ type validation for AsrConfig (+ FeedbackConfig.notify_ms)

Ground truth verified by reading config.py / config.toml / the tests / architecture/bug_analysis.md
on 2026-07-14. This is bugfix Issue 4 (Minor): wrong-typed config values load silently today and break
the feature at runtime (a TypeError the idle watchdog swallows). Fix = fail fast at LOAD time with a
clear TypeError, mirroring the existing unknown-key rejection.

---

## 1. Root cause (architecture/bug_analysis.md §Issue 4, confirmed)

`VoiceTypingConfig.from_toml()` overlays each TOML table via `section_cls(**section)` (config.py
~from_toml `_overlay`). Python dataclasses do NOT enforce type annotations at runtime. So
`auto_stop_idle_seconds = "thirty"` (a str) loads into `AsrConfig` with NO error. At runtime
`_maybe_auto_stop` does `time.monotonic() - ts < threshold` with `threshold="thirty"` → TypeError,
which `_idle_watchdog` swallows (`except Exception`) → **auto-stop silently dies** (and
`auto_unload_idle_seconds` would silently disable idle-unload the same way). The daemon does not
crash; the feature just stops working with only a repeating traceback in the journal.

**Chosen fix (bug_analysis "Recommended: Approach B-lite"):** `__post_init__` on AsrConfig that
validates with isinstance and raises TypeError at construction (= load time, exactly when from_toml
calls `AsrConfig(**section)`). More robust than a key-name coercion list (which can drift) and
catches ALL type mismatches, not just the named numeric ones. The item CONTRACT prescribes this
approach verbatim (the fields, the isinstance rules, the bool gotcha, the TypeError message shape).

**Consistency:** the existing unknown-key rejection ALSO uses TypeError (dataclass `__init__`
rejects unknown kwargs → TypeError). So wrong-type → TypeError is consistent (both surface as a
load-time TypeError the daemon propagates → fails before models load, before systemd loops).

---

## 2. The bool gotcha (load-bearing)

`isinstance(True, int)` is `True` — **bool is a subclass of int in Python.** So:
- A naive `isinstance(value, int)` accepts `True`/`False` for a numeric field. WRONG here: a bool
  is not a valid numeric config value (tomllib parses `true`/`false` to bool, not a number).
- The validate rule for NUMERIC fields is: `isinstance(value, (int, float)) AND NOT isinstance(value,
  bool)` — i.e. reject bool FIRST, then require int-or-float.
- For the INT field notify_ms: `isinstance(value, int) AND NOT isinstance(value, bool)` — accept int,
  reject bool AND reject float (`2500.0` from tomllib must NOT silently pass for an int field).

Implementation idiom (reject bool first, short-circuit):
```python
if isinstance(_v, bool) or not isinstance(_v, (int, float)):   # numeric (int or float), not bool
    raise TypeError(...)
if isinstance(_v, bool) or not isinstance(_v, int):            # int only, not bool, not float
    raise TypeError(...)
```

---

## 3. The fields + expected types (config.py AsrConfig lines 49-66, FeedbackConfig ~73)

AsrConfig (validate ALL 8 fields):
- str: `final_model`, `realtime_model`, `language`, `device`
- float (accept int|float, reject bool): `post_speech_silence_duration`, `realtime_processing_pause`,
  `auto_stop_idle_seconds`, `auto_unload_idle_seconds`

FeedbackConfig (validate ONLY `notify_ms` — the item's optional clause; the only runtime-numeric field):
- int (accept int, reject bool + float): `notify_ms`
- DO NOT validate `state_file`/`hypr_notify`/`notify_on_final` (out of scope; not silent-break risks —
  a wrong-typed state_file fails at file-open with a clear error; a wrong-typed bool is merely truthy).

Defaults all pass (verified): floats 0.6/0.15/30.0/1800.0, strs, notify_ms 2500 (int) — none are bool.

---

## 4. Regression scan — NO existing construction breaks (verified)

Grepped `AsrConfig(` and `FeedbackConfig(` across voice_typing/ + tests/. Every construction uses
correctly-typed values:
- `tests/test_config.py:73-75` `AsrConfig().final_model/realtime_model/device` — defaults, pass.
- `tests/test_daemon.py:185` `AsrConfig(language="es", post_speech_silence_duration=0.9,
  realtime_processing_pause=0.2, final_model="large-v3-turbo", realtime_model="medium.en",
  device="cuda")` — ALL correctly typed (str/float/str) → passes __post_init__.
- `tests/test_feedback.py` + `test_daemon.py`: `FeedbackConfig(state_file=..., hypr_notify=True/False,
  notify_ms=2500/9999)` — notify_ms always int → passes.
- `tests/test_config_repo_default.py`: parses `<repo>/config.toml` (correctly-typed values) →
  `AsrConfig(**section)` → __post_init__ runs on valid values → passes. The drift guard stays green.
- `tests/test_config.py:81-86` asserts default VALUE types (isinstance checks on the values) — my
  change does NOT mutate values, so these still pass.

→ S1 touches NO test files. The committed wrong-type test is S2 (P1.M3.T1.S2). S1 = config.py +
config.toml only.

## 5. The parallel task (P1.M2.T2.S3) is DISJOINT

It is a TEST-ONLY task (child-crash-recovery tests in a new test file). Its PRP explicitly lists
config.py under "UNCHANGED" / "do NOT edit config.py". Zero overlap with this task. (Confirmed by
grep: it references FeedbackConfig only inside its own new test's `cfg=VoiceTypingConfig(feedback=
FeedbackConfig(state_file=...))` constructions — correctly typed, unaffected.)

## 6. config.toml doc edit (Mode A)

The "SCHEMA SOURCE" comment (config.toml ~line 25-28) currently says only "Unknown keys are REJECTED
at load time (a typo raises an error instead of being silently ignored)." Append a sentence noting
wrong-TYPED values are also rejected (the item's DOCS clause). Anchor is unique; ASCII-only new text.

## 7. Tooling / scope
- pytest is the gate (.venv/bin/python -m pytest). FULL PATHS (zsh aliases). ruff optional
  (/home/dustin/.local/bin/ruff, NOT in .venv). mypy NOT installed — do NOT run it.
- S1 edits: voice_typing/config.py (AsrConfig.__post_init__ + FeedbackConfig.__post_init__) +
  config.toml (one comment sentence). NO test files (S2 owns the wrong-type pytest). NO daemon.py /
  feedback.py / ctl.py / README (other tasks). NO PRD.md/tasks.json/prd_snapshot.md/.gitignore.
- `__post_init__` runs on EVERY construction (defaults, from_toml, direct). Defaults pass (§3).
