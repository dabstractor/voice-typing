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

---

## Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)

**Date:** 2025-01 (audit re-verified against the live tree)
**Scope:** Verify `config.toml` ↔ `voice_typing/config.py` **lockstep (zero drift)** + **blocklist
correctness** (VT-006) + **Mode A comment accuracy** (config.toml as the user-facing config
reference per PRD §4.5). This is a **verification/audit** subtask — the deliverable is this recorded
section; source changes happen **only** if a real drift is found (none exists).

**Distinct from S1.** S1 = PRD §4.5 field/default **compliance** (does `config.py` match the spec?).
S2 = `config.toml` ↔ `config.py` **lockstep** (drift) + blocklist correctness + Mode A doc accuracy.
This section does **not** duplicate S1's field-compliance table (§2); it appends a focused
lockstep/blocklist/Mode-A result.

**Bottom line:** ✅ **No drift.** `config.toml` mirrors `config.py` exactly.
Blocklist is the documented **VT-006 4-entry** version in **both** files (no bare `"you"`).
Mode A comments are accurate (`SUPER+ALT+D` correct, no stale refs). **No source files modified.**

> **Minor cross-reference note.** S1's report header + §2 + §8 say **"19 scalar fields"**, but the
> live `dataclasses.fields` count (verified here, Task 1) is **20** (asr:10, output:3, feedback:4,
> filter:2, log:1 = 20). The §2 table itself lists all **20** rows correctly — the "19" figure is a
> prose typo in S1, not a field-count gap. S2 uses **20** (the verified count).

### S2.1 Drift-guard test result (the lockstep proof)

```bash
.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q
.....................................                                    [100%]
37 passed in 0.02s
```

**37 passed.** `tests/test_config_repo_default.py` carries **3 lockstep tests**, each asserting a
distinct facet of the agreement:

| Test (file:line) | Asserts |
|---|---|
| `test_repo_config_toml_equals_defaults` | `VoiceTypingConfig.from_toml_file(repo) == VoiceTypingConfig()` — **THE lockstep proof** (parsed `config.toml` == dataclass defaults). |
| `test_repo_config_toml_has_no_extra_keys` | the **exact 20-key set**: asr `{final_model, realtime_model, lite_model, language, device, post_speech_silence_duration, lite_post_speech_silence_duration, realtime_processing_pause, auto_stop_idle_seconds, auto_unload_idle_seconds}` (10), output `{backend, tmux_target, append_space}` (3), feedback `{state_file, hypr_notify, notify_ms, notify_on_final}` (4), filter `{min_chars, blocklist}` (2), log `{level}` (1) = **20**. A stray/renamed key fails here. |
| `test_repo_config_lite_model_comment_names_correct_keybind` | raw-text scan of `config.toml`: the `lite_model` line cites `SUPER+ALT+D`, **not** the stale `SUPER+ALT+F`. (Reads **raw text**, not the parsed dict — `tomllib` drops comments.) |

**Coverage boundary (recorded so it is not over-trusted).** The drift guard checks **agreement**
(`config.py` ↔ `config.toml`), **NOT PRD §4.5 compliance**. If **both** files drifted from the PRD
together — or both carry an intentional deviation, as the blocklist does (VT-006) — the guard stays
green. **S1 is the PRD-compliance check; S2 is the lockstep check.** This boundary is also recorded
in S1's §7.

### S2.2 Direct comparison (independent of the test)

```bash
.venv/bin/python - <<'PY'
import dataclasses, tomllib
from voice_typing.config import VoiceTypingConfig, _repo_config_path
from voice_typing import config as c
repo  = VoiceTypingConfig.from_toml_file(_repo_config_path())
print("LOCKSTEP (toml==py defaults):", repo == VoiceTypingConfig())   # True
with open(_repo_config_path(), "rb") as fh: data = tomllib.load(fh)
print("blocklist t==p:", data["filter"]["blocklist"] == VoiceTypingConfig().filter.blocklist)  # True
nfields = sum(len(dataclasses.fields(cls)) for cls in
             (c.AsrConfig, c.OutputConfig, c.FeedbackConfig, c.FilterConfig, c.LogConfig))
print("config.py fields:", nfields, "| config.toml keys:", sum(len(v) for v in data.values()))  # 20 | 20
PY
```

Observed:

- `VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig()` → **True** (no drift).
- `config.py` **20 scalar fields** (`dataclasses.fields` across the 5 config dataclasses) == `config.toml` **20 keys**. Match.
- Per-section key counts: asr 10, output 3, feedback 4, filter 2, log 1 → **20**. (Matches the exact
  set pinned by `test_repo_config_toml_has_no_extra_keys`.)

### S2.3 Blocklist correctness — VT-006, in BOTH files

**This is the most important paragraph of the S2 section:** it records the blocklist as
**compliant-by-design** so that no future agent re-adds `"you"` (which would break the test,
contradict the VT-006 decision, and re-introduce the silent-drop-of-`"you"` UX bug).

**The 4-entry blocklist** (identical in `config.py`, `config.toml`, and `tests/test_config.py:_PRD_BLOCKLIST`):

```python
["thank you.", "thanks for watching.", "bye.", "thank you for watching"]
```

| Check | Result |
|---|---|
| `config.py` `FilterConfig.blocklist` (`voice_typing/config.py:184-200`, `field(default_factory=lambda: [...])`, values at `:186-189`) | 4 entries ✓ |
| `config.toml` `[filter].blocklist` (`config.toml:62-66`, values at `:63-66`) | 4 entries ✓ (identical) |
| `config.py` blocklist == `config.toml` blocklist | **True** (no inter-file drift) |
| All 4 contract-required entries present (`{thank you., thanks for watching., bye., thank you for watching}`) | ✓ |
| Bare `"you"` absent from BOTH files (VT-006) | ✓ |

**VT-006 is documented in three places and pinned by a test** (so re-adding `"you"` would fail the
suite):

| Location | What it says |
|---|---|
| `voice_typing/config.py:191-200` | `NOTE (VT-006)` — bare `"you"` removed; common word users want to type; blocklist matches the punctuation/case-normalized form, so a blanket `"you"` silently dropped dictating the single word; recommends a hallucination-pattern heuristic instead. |
| `config.toml:67` | `# NOTE (VT-006): the bare "you" entry was removed — it is a common word users want to type, not a hallucination.` |
| `tests/test_config.py:24-26` | `_PRD_BLOCKLIST` defined as the 4-entry list with a `# VT-006:` comment above it. |
| `tests/test_config.py:64` | `assert cfg.filter.blocklist == _PRD_BLOCKLIST` — **the pin**. (`:99` re-asserts it after a mutation test.) |

**Verdict: compliant-by-design — NOT a gap.** The PRD §4.5 literal text lists 5 entries incl.
`"you"`; the implementation intentionally omits `"you"` per VT-006. The test's `_PRD_BLOCKLIST`
constant **is** the authoritative pin (despite its name). Do **not** reconcile `config.py` toward
PRD §4.5's 5-entry literal — that is the single most likely error and is forbidden (see S1 §3 and
Anti-Patterns).

### S2.4 Mode A comment accuracy (config.toml as the user-facing reference)

`config.toml` is the file users edit; per PRD §4.5 (Mode A) it doubles as documentation. Its
comments must be accurate — a stale keybind letter or a removed-field reference sends users to a
dead key / confuses them. The scan:

| Check (raw-text scan; `tomllib` drops comments) | Result |
|---|---|
| All **20** keys carry a trailing `#` comment (`grep -cE '^[a-z_]+\s*=' config.toml` = 20) | ✓ every key documented |
| `lite_model` comment cites `SUPER+ALT+D` (`config.toml:34`) | ✓ matches `hypr-binds.conf:52` `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` (the source of truth) |
| No stale `SUPER+ALT+F` reference (`grep -nE 'SUPER\+ALT\+F' config.toml`) | ✓ clean (no match) |
| No stale `compute_type` reference (`grep -nE 'compute_type' config.toml`) | ✓ clean — `compute_type` is correctly **absent** (it's a `cuda_check` concern, `config.py:20`, not a config field) |
| Comment content spot-check vs §4.5 (device cpu auto-fallback, `append_space`, `state_file` XDG_RUNTIME_DIR, idle-stop vs idle-unload, etc.) | ✓ accurate; no inaccuracies found |

> **Why the keybind check reads raw text, not the parsed dict.** `tomllib.load` **drops comments**,
> so any comment-accuracy assertion (`SUPER+ALT+D` vs the stale `SUPER+ALT+F`) must read
> `config.toml` via `open(...).read()` / `grep`. The existing test
> (`test_repo_config_lite_model_comment_names_correct_keybind`) already does this; S2's scan mirrors
> it. (CRITICAL #4 in the PRP.)

### S2.5 Keybind source-of-truth cross-check

`hypr-binds.conf` is the real Hyprland keybind source:

- `hypr-binds.conf:50` — `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` (normal toggle).
- `hypr-binds.conf:52` — `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` (**lite** toggle).

`config.toml:34`'s `lite_model` comment correctly says `SUPER+ALT+D` (the lite bind), not the
`CTRL+SUPER+ALT+D` normal-toggle bind and not the stale `SUPER+ALT+F`. ✅

### S2.6 Conclusion

**No drift.** `config.toml` mirrors `voice_typing/config.py` exactly:

- **Lockstep:** `from_toml_file(repo) == VoiceTypingConfig()` → **True**; drift-guard test =
  **37 passed**; 20 `config.py` fields == 20 `config.toml` keys (exact set).
- **Blocklist:** the VT-006 **4-entry** version in **both** files (no bare `"you"`); documented at
  `config.py:191-200`, `config.toml:67`, `tests/test_config.py:24-26`; pinned by
  `tests/test_config.py:64`. Compliant-by-design.
- **Mode A doc:** 20 keys, 20 trailing comments; `lite_model` cites `SUPER+ALT+D`
  (matches `hypr-binds.conf:52`); no `SUPER+ALT+F` / `compute_type` stale refs.

**No code changes required and none made.** `config.py`, `config.toml`, the test files, and
`hypr-binds.conf` are all **unchanged** — the verification confirms they are already in lockstep.
(This is the expected outcome: the contract's "fix any drift" branch is **not** taken because no
non-VT-006 drift exists.) This closes P1.M1.T1.S2.