# Gap Report — P1.M1.T1.S1: Config Dataclass Fields & Defaults vs PRD §4.5

**Date:** 2025-01 (audit re-verified against live tree)
**Scope:** Audit `voice_typing/config.py` dataclasses + repo `config.toml` against the PRD §4.5
config schema. Subtask **P1.M1.T1.S1** of verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/config.py` — `AsrConfig`, `OutputConfig`, `FeedbackConfig`, `FilterConfig`,
  `LogConfig`, `VoiceTypingConfig` dataclasses + `__post_init__` validation + `from_toml` loader.
- `config.toml` — repo default config.
- `tests/test_config.py` — `_PRD_BLOCKLIST` pin (`:24`) + field/default tests.
- `tests/test_config_repo_default.py` — drift guard (config.py ↔ config.toml agreement).

**Bottom line:** ✅ All 19 scalar fields are **compliant** with PRD §4.5. The single divergence —
`filter.blocklist` omitting the bare `"you"` entry — is the **intentional, documented VT-006 design
decision**, not a gap. **No source files were modified.** `config.toml` mirrors `config.py`.

---

## 1. Method

Three sources were compared for every field: **PRD §4.5** (spec), **`config.py` default**
(implementation), and **`config.toml`** value (repo default). Defaults were dumped programmatically
with `dataclasses.fields(...)` (not read-and-assumed from the PRD); `config.toml` was parsed with
`tomllib`. The config test suite was re-run to confirm the existing guards reproduce.

### Commands run (re-verification)

```bash
# (a) Dump every dataclass field (name/type/default) + config.toml blocklist
.venv/bin/python - <<'PY'
import dataclasses, tomllib
from voice_typing import config as c
from voice_typing.config import _repo_config_path
for cls in (c.AsrConfig, c.OutputConfig, c.FeedbackConfig, c.FilterConfig, c.LogConfig):
    print(f"[{cls.__name__}]")
    for f in dataclasses.fields(cls):
        d = f"<factory {f.default_factory()!r}>" if f.default_factory is not dataclasses.MISSING else repr(f.default)
        print(f"  {f.name:38} : {f.type!s:12} = {d}")
with open(_repo_config_path(), "rb") as fh: data = tomllib.load(fh)
print("config.toml [filter].blocklist:", data["filter"]["blocklist"])
PY

# (b) Re-run the config + drift-guard tests
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q
```

### Observed output (abridged)

```
[AsrConfig]   final_model:str='distil-large-v3'  realtime_model:str='small.en'  lite_model:str='small.en'
              language:str='en'  device:str='cuda'  post_speech_silence_duration:float=0.6
              lite_post_speech_silence_duration:float=0.5  realtime_processing_pause:float=0.15
              auto_stop_idle_seconds:float=30.0  auto_unload_idle_seconds:float=1800.0
[OutputConfig]    backend:str='wtype'  tmux_target:str=''  append_space:bool=True
[FeedbackConfig]  state_file:str=''  hypr_notify:bool=True  notify_ms:int=2500  notify_on_final:bool=True
[FilterConfig]    min_chars:int=2  blocklist:list[str]=<factory ['thank you.','thanks for watching.','bye.','thank you for watching']>
[LogConfig]       level:str='INFO'
config.toml [filter].blocklist: ['thank you.', 'thanks for watching.', 'bye.', 'thank you for watching']

.....................................   [100%]
37 passed in 0.02s
```

---

## 2. Field / Default Compliance Table (PRD §4.5 vs config.py vs config.toml)

| Section.field | PRD §4.5 | `config.py` default | `config.toml` | Match |
|---|---|---|---|---|
| `asr.final_model` | `"distil-large-v3"` | `'distil-large-v3'` (`:71`) | `"distil-large-v3"` | ✅ |
| `asr.realtime_model` | `"small.en"` | `'small.en'` (`:72`) | `"small.en"` | ✅ |
| `asr.lite_model` | `"small.en"` | `'small.en'` (`:73`) | `"small.en"` | ✅ |
| `asr.language` | `"en"` | `'en'` (`:75`) | `"en"` | ✅ |
| `asr.device` | `"cuda"` | `'cuda'` (`:76`) | `"cuda"` | ✅ |
| `asr.post_speech_silence_duration` | `0.6` | `0.6` (`:77`) | `0.6` | ✅ |
| `asr.lite_post_speech_silence_duration` | `0.5` | `0.5` (`:79`) | `0.5` | ✅ |
| `asr.realtime_processing_pause` | `0.15` | `0.15` (`:82`) | `0.15` | ✅ |
| `asr.auto_stop_idle_seconds` | `30.0` | `30.0` (`:83`) | `30.0` | ✅ |
| `asr.auto_unload_idle_seconds` | `1800.0` | `1800.0` (`:85`) | `1800.0` | ✅ |
| `output.backend` | `"wtype"` | `'wtype'` (`:125`) | `"wtype"` | ✅ |
| `output.tmux_target` | `""` | `''` (`:126`) | `""` | ✅ |
| `output.append_space` | `true` | `True` (`:127`) | `true` | ✅ |
| `feedback.state_file` | `""` | `''` (`:135`) | `""` | ✅ |
| `feedback.hypr_notify` | `true` | `True` (`:136`) | `true` | ✅ |
| `feedback.notify_ms` | `2500` | `2500` (int, `:137`) | `2500` | ✅ |
| `feedback.notify_on_final` | `true` | `True` (`:138`) | `true` | ✅ |
| `filter.min_chars` | `2` | `2` (int, `:180`) | `2` | ✅ |
| `filter.blocklist` | PRD §4.5 lists **5** (incl. `"you"`) | **4-entry** (NO `"you"`) (`:184-190`) | **4-entry** (NO `"you"`) | ⚠️ **INTENTIONAL DEV (VT-006)** — see §3 |
| `log.level` | `"INFO"` | `'INFO'` (`:212`) | `"INFO"` | ✅ |

> `config.py` line numbers are `grep -n`-verified against the live tree. `config.toml` keys mirror
> each dataclass field one-for-one (the drift guard in `tests/test_config_repo_default.py` enforces
> both equality and the exact key set). The blocklist uses `field(default_factory=lambda: [...])`
> (`config.py:184-190`) — a mutable-default guard, not a plain default.

---

## 3. Intentional Deviation: `filter.blocklist` (VT-006) — Compliant-by-Design, NOT a Gap

This is the single most important section of this report: it records the one place the
implementation **intentionally diverges** from PRD §4.5's literal text, so that no future agent
mistakes it for drift and "fixes" it (which would break a test **and** re-introduce a UX bug).

**The difference.** PRD §4.5's literal blocklist has **5** entries including a bare `"you"`. The
implementation (`config.py` + `config.toml` + `tests/test_config.py:_PRD_BLOCKLIST`) uses **4**
entries — `"you"` is deliberately **omitted**.

**The 4-entry blocklist in all three sources:**
```python
["thank you.", "thanks for watching.", "bye.", "thank you for watching"]
```

**The reason (VT-006).** `"you"` is a common English word a user frequently wants to type as a
standalone utterance. The blocklist matches on the punctuation/case-normalized form produced by
`textproc.clean`, so a blanket `"you"` entry **silently dropped** dictating the single word "you"
with no feedback. The blocklist's purpose is suppressing genuine Whisper silence hallucinations (the
other entries — "thank you.", "thanks for watching.", etc. — are real hallucinations); a single-word
"you" is not a hallucination and should pass through.

**Documented in THREE places:**
| Location | What it says |
|---|---|
| `voice_typing/config.py:191` | `NOTE (VT-006)` comment on the `blocklist` field explaining the removal, the rationale, and the recommended alternative (a hallucination-pattern heuristic rather than blanket suppression). |
| `config.toml:67` | `# NOTE (VT-006): the bare "you" entry was removed — it is a common word users want to type, not a hallucination.` |
| `tests/test_config.py:24` | `_PRD_BLOCKLIST` is defined as the 4-entry list with the `# VT-006:` comment above it (lines 23-26). |

**Pinned by a test.** `tests/test_config.py:64` asserts `cfg.filter.blocklist == _PRD_BLOCKLIST`,
and `tests/test_config.py:99` re-asserts it in `test_blocklist_not_shared_between_instances`. The
test's `_PRD_BLOCKLIST` constant — despite its name saying "PRD §4.5 authoritative blocklist" — **is
the VT-006-corrected 4-entry version**. It is the authoritative pin, not PRD §4.5's raw 5-entry text.

**Why "fixing" this is forbidden.** Re-adding `"you"` would (a) **break** `test_config.py:64`,
(b) **contradict** the documented VT-006 decision, and (c) **re-introduce** the silent-drop-of-"you"
UX bug. The deviation is therefore **compliant-by-design** and is recorded here so the trap is
visible. ✅

---

## 4. Validation Logic Audit

All PRD §4.5 validation requirements are present and correct:

### 4.1 `AsrConfig.__post_init__` — `voice_typing/config.py:72`

- **Numeric tuple** (`config.py:86`, the `for _name in (...)` loop starting at `:85`): validates
  `post_speech_silence_duration`, `lite_post_speech_silence_duration`,
  `realtime_processing_pause`, `auto_stop_idle_seconds`, `auto_unload_idle_seconds`. Rejects `bool`
  (an `int` subclass) **and** any non-numeric with `TypeError`.
- **String tuple** (`config.py:99`): validates `final_model`, `realtime_model`, `lite_model`,
  `language`, `device`. Rejects non-`str` with `TypeError`.
- **Device value validation (VT-005)** (`config.py:117`): additionally enforces
  `device in ("cuda", "cpu")` with a `ValueError` (the type is correct, the value is not — hence
  `ValueError`, not `TypeError`). This is a VT-005 hardening, beyond the PRD §4.5 type check.

### 4.2 `FeedbackConfig.__post_init__` — `voice_typing/config.py:140`

- Validates `notify_ms` is a **genuine** `int` (rejects `bool`, which is an `int` subclass) with
  `TypeError` (`config.py:157`). This is the only runtime-numeric FeedbackConfig field.

### 4.3 Unknown-key rejection — `voice_typing/config.py:232` / `:240` / `:242`

- `from_toml`'s docstring (`config.py:232`) documents "Unknown keys raise TypeError (dataclass
  `__init__` rejects them)" — a typo'd key raises `TypeError` at **load time**.
- The `Mapping` check at `config.py:240` (`if not isinstance(section, Mapping)`) raises
  `TypeError` (`config.py:242`, "must be a TOML table") when a scalar appears where a table is
  expected.

### 4.4 `compute_type` correctly NOT a config field

- `config.py:20` documents that `compute_type` is **NOT** a config field — it is a `cuda_check`
  concern (PRD §4.4), resolved at daemon startup by `cuda_check.resolve_device_and_models()`. Its
  absence from `AsrConfig` is **by design**, not a missing-field gap. ✅

---

## 5. Test Results

```
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q
.....................................   [100%]
37 passed in 0.02s
```

**37 passed, 0 failed, 0 errors.** This matches the PRP's expected count. The suite includes:
- `tests/test_config.py:39` `test_defaults_match_prd_4_5` — pins all PRD §4.5 defaults.
- `tests/test_config.py:64` — pins `blocklist == _PRD_BLOCKLIST` (the VT-006 4-entry list).
- `tests/test_config.py:93` `test_blocklist_not_shared_between_instances` — pins the
  `default_factory` mutable-default guard.
- `tests/test_config.py:120` `test_from_toml_unknown_key_raises` — pins unknown-key rejection.
- `tests/test_config.py:151`/`:222`/`:244` — pin the `__post_init__` type rejections
  (bool/None/wrong-type for float/int fields).
- `tests/test_config_repo_default.py` — the drift guard (see §7).

---

## 6. Mismatches Requiring Action

**None.** All 19 scalar fields are compliant with PRD §4.5. The blocklist divergence is the
documented VT-006 design decision (§3), not a real mismatch. `config.toml` mirrors `config.py` per
the audit (and the drift guard). **No source files (`config.py`, `config.toml`, test files) were
modified.**

---

## 7. Coverage Boundary: Drift Guard ≠ PRD Compliance

The existing `tests/test_config_repo_default.py` drift guard is **green**, but it only proves:

- `test_repo_config_toml_equals_defaults` — `config.py` defaults **equal** `config.toml` values, and
- `test_repo_config_toml_has_no_extra_keys` — the exact key set matches.

It does **NOT** check **PRD §4.5 compliance**. If **both** `config.py` and `config.toml` drifted
from the PRD together (or both carried an intentional deviation, as the blocklist does), the guard
would stay green. **This audit (S1) is the PRD-compliance check the guard cannot perform** — it is
the human/agent verification that closes that gap. This boundary should be understood before relying
on the green drift guard as evidence of spec compliance.

---

## 8. Conclusion

The config layer is **PRD §4.5-compliant**. Every one of the 19 scalar fields matches the spec in
both `config.py` and `config.toml`; the `__post_init__` type-validation (numeric/string tuples,
`notify_ms` int) and the unknown-key rejection are present and correct; `compute_type` is correctly
absent by design. The one divergence — `filter.blocklist` omitting `"you"` — is the intentional,
documented, and test-pinned **VT-006** design decision (compliant-by-design, recorded in §3 to
prevent a future agent from re-adding `"you"`). **No code changes were required and none were made.**

This closes P1.M1.T1.S1. Sibling subtask P1.M1.T1.S2 (lockstep + blocklist-correctness
confirmation) can rely on this report's findings; P1.M1.T1.S3 (search-order / XDG resolution) is a
separate concern not covered here.