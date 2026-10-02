# PRP — P1.M1.T1.S1: config.py + config.toml schema delta (R1/R3/R4/R5/R7 fields)

## Goal

**Feature Goal**: Land the Rev 2 streaming-dictation config schema in one atomic delta: **remove** `final_model`/`realtime_model` (single-mode collapse), **bump** `lite_post_speech_silence_duration` 0.5→0.8, **add** `asr.context_prompt`, `output.streaming`, and a new `[cancel]` section (`CancelConfig`), extend `__post_init__` validation following the existing patterns, and mirror everything in `config.toml` + the two config test files. Consumed by P1.M1.T2.S2 (kwargs collapse), P1.M2.T5 (context_prompt), P1.M2.T6 (streaming), P1.M2.T7.S2 (cancel).

**Deliverable**: Four files changed, atomically:
1. `voice_typing/config.py` — AsrConfig field deltas + string-tuple edit; OutputConfig.streaming; new `CancelConfig`; `VoiceTypingConfig.cancel`; `_overlay(CancelConfig, "cancel")`; new type guards.
2. `config.toml` — delete 2 keys, revalue 1, add 3 keys + `[cancel]` section, end-state bind comments (Mode A doc).
3. `tests/test_config.py` — remove/replace removed-field asserts; add new default/type-guard/overlay/unknown-key cases.
4. `tests/test_config_repo_default.py` — expected key set → 21 keys/6 sections; docstring count; lite_model comment test → end-state binds.

**Success Definition**: (a) `VoiceTypingConfig()` exposes `cfg.asr.context_prompt=True`, `cfg.output.streaming=True`, `cfg.cancel.on_backspace=True`, `cfg.cancel.devices==[]`, `lite_post_speech_silence_duration==0.8`; (b) `final_model`/`realtime_model` are GONE from AsrConfig (AttributeError on access; `from_toml` with them raises TypeError as unknown keys); (c) both owned test files green; (d) repo config.toml parses to exactly the defaults (drift guard); (e) ONLY the four files change (downstream suites are EXPECTED to fail until P1.M1.T2 — see Gotcha #1).

## User Persona

**Target User**: The end user tuning streaming dictation via `config.toml` (Mode A — every key's comment IS the doc), and the downstream subtasks (T2.S2/M2.T5/T6/T7.S2) that consume the new fields.

**Use Case**: User enables/disables streaming (`output.streaming` rollback hatch), tunes the commit silence (0.8), or configures explicit keyboard nodes for Backspace-cancel.

**Pain Points Addressed**: Gives Rev 2 its schema substrate; removes the dead two-model fields; makes wrong-typed new keys fail at load (not crash-loop under systemd); keeps config.toml ↔ config.py ↔ tests in lockstep.

## Why

- **Rev 2 substrate (PRD §4.2quater/§4.5):** streaming partial typing, Backspace-cancel, and the rolling context prompt each need a knob; the single-mode collapse removes `final_model`/`realtime_model`; under streaming the endpointer only delays COMMIT so the default rises 0.5→0.8.
- **Atomicity is enforced by the drift guard:** `test_repo_config_toml_equals_defaults` (config.toml parse == defaults) + `test_repo_config_toml_has_no_extra_keys` (exact key set) fail loudly unless config.py, config.toml, and the expected set move together. Also `from_toml` rejects unknown keys — leaving `final_model` in config.toml after removing the field raises TypeError.
- **Staged plan:** S1 is the schema delta; the ~60 downstream references (daemon.py:152 reads `cfg.asr.final_model`; cuda_check CUDA_DEFAULTS/CPU_FALLBACK ×14; test_daemon ×29; ctl/prefetch/recorder_host/other tests) are collapsed by P1.M1.T2. S1 intentionally leaves those suites red (Gotcha #1).

## What

Schema-only delta per the contract: remove 2 fields, revalue 1, add 3 knobs + 1 new dataclass/section, extend validation (bools reject non-bool; `devices` must be list[str]), update config.toml (comments in the END-STATE bind vocabulary: one Ctrl+Alt+Super+D toggle bind + one Alt+Super+Backspace cancel bind), and update the two owned test files. No daemon/ctl/cuda_check/prefetch/binds changes (siblings).

### Success Criteria

- [ ] AsrConfig fields: `final_model`/`realtime_model` deleted; string guard tuple becomes `("lite_model", "language", "device")`; `context_prompt: bool = True` added (after `lite_post_speech_silence_duration`); `lite_post_speech_silence_duration: float = 0.8`.
- [ ] OutputConfig gains `streaming: bool = True`.
- [ ] New `CancelConfig` (`on_backspace: bool = True`, `devices: list[str] = field(default_factory=list)`) with `__post_init__` type guards; `VoiceTypingConfig.cancel` field; `cancel=_overlay(CancelConfig, "cancel")`.
- [ ] config.toml: 2 keys deleted; `lite_post_speech_silence_duration = 0.8` w/ PRD comment; `context_prompt`/`streaming`/`[cancel]` added w/ self-documenting comments in end-state bind vocabulary.
- [ ] `tests/test_config.py` + `tests/test_config_repo_default.py` green (21-key/6-section expected set).
- [ ] Only the four files changed.

## All Needed Context

### Context Completeness Check

_Pass._ All edit sites quoted verbatim with re-verified line numbers; the end-state key set is enumerated; validation patterns to copy are cited; the blast radius and its staging are quantified.

### Verified Current State (re-verified this session)

**`voice_typing/config.py`:** AsrConfig@48 (`final_model`:52, `realtime_model`:53, `lite_model`:54, `language`:56, `device`:57, `post_speech_silence_duration`:58, `lite_post_speech_silence_duration`:59=0.5, `realtime_processing_pause`:64, `auto_stop_idle_seconds`:65, `auto_unload_idle_seconds`:67). `__post_init__`@72: numeric tuple@85-92 (5 names, bool-rejection), **string tuple@99: `("final_model", "realtime_model", "lite_model", "language", "device")`**, device ValueError@~113. OutputConfig@118 (`backend`:122 — already `"wtype"|"ydotool"|"null"`, **`tmux_target` already gone**; `append_space`:123; `__post_init__`@125 backend ValueError). FeedbackConfig@139. FilterConfig@188 (`__post_init__`@213 — the list-of-str guard pattern for `blocklist`). LogConfig@242. VoiceTypingConfig@254 (asr:258, output:259, feedback:260, filter:261, log:262). `from_toml`@267 with `_overlay`@278 + five calls@287-291; unknown keys raise TypeError via `section_cls(**section)`.

**`config.toml`:** `[asr]` keys L32-41 (`final_model`:32, `realtime_model`:33, `lite_model`:34 — comment cites SUPER+ALT+D/toggle-lite, `lite_post_speech_silence_duration`:38=0.5, …); `[output]` L46-47 (backend, append_space — no tmux_target).

**`tests/test_config_repo_default.py`:** equals-defaults test; key-set test (docstring says "20 schema keys" — **already stale**, actual is 19) with `expected` asr-set incl. final_model/realtime_model; `test_repo_config_lite_model_comment_names_correct_keybind`@53-72 asserts `"SUPER+ALT+D" in` the lite_model line and `"SUPER+ALT+F" not in`.

**`tests/test_config.py`:** `test_defaults_match_prd_4_5`@39 (asserts `cfg.asr.final_model`@~43, `cfg.asr.realtime_model`@~44, and 0.5 for lite_post; add/remove here); `test_defaults_match_cuda_check`@66 (asserts `AsrConfig().final_model == CUDA_DEFAULTS["final_model"]`@~75, realtime_model@~76 — cuda_check still HAS the keys; drop only these two asserts, keep the `device` one); `test_from_toml_partial_table_keeps_other_defaults`@105 (asserts `cfg.asr.final_model`@~109 — replace with `lite_model`). Patterns to extend: `test_from_toml_unknown_key_raises`@119, wrong-type suite @142/150/156 (`pytest.raises(TypeError, match=...)`), value-validation @171.

**Blast radius of the removal (grep-verified):** daemon.py ×21 (line 152 `cfg.asr.final_model` → AttributeError at runtime), cuda_check ×14 (CUDA_DEFAULTS/CPU_FALLBACK keys — T2.S1 owns), ctl ×4 (status dict keys), prefetch ×2, recorder_host ×7; tests: test_daemon ×29, test_config ×9, test_recorder_host ×2, test_control_socket ×2, test_voicectl ×1, test_feed_audio ×1.

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/architecture/substrate_map.md
  why: §1 maps every config.py line + the merge mechanism ("adding asr.context_prompt/output.streaming/[cancel]
       requires (a) fields, (b) _overlay(CancelConfig,'cancel'), (c) config.toml keys, (d) the expected-key set;
       removing final_model/realtime_model also touches that set plus test_config.py 43-44/75-76").
- docfile: plan/007_cfc245548aec/prd_snapshot.md
  why: §4.5 Rev 2 canonical block = the exact end-state keys/defaults/comments (incl. the 0.8 comment text and
        [cancel] wording). NOTE: its [asr] block still lists final_model/realtime_model — the CONTRACT governs
        (remove them); its [output] correctly omits tmux_target (already gone).
  critical: "backend values are already wtype|ydotool|null in code — do not 'fix' the comment."
- file: voice_typing/config.py
  pattern: "AsrConfig.__post_init__ (72-114) = the validation idiom: TypeError for type (bool-rejection for
            numerics), ValueError for value. FilterConfig.__post_init__ (213-236) = the list-of-str guard for
            blocklist — copy it for CancelConfig.devices. There is NO existing bool-field type guard; add
            `if not isinstance(v, bool): raise TypeError(...)` in the same style."
- file: tests/test_config_repo_default.py
  why: the drift guard — key set + equals-defaults + the lite_model comment pin. All three move in lockstep.
- file: tests/test_config.py
  why: parity tests to update (43-44, 75-76, 109) + the wrong-type/unknown-key patterns to extend.
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/config.py                      # AsrConfig@48 (10 fields); OutputConfig@118; VoiceTypingConfig@254; from_toml/_overlay@267-291  ← EDIT
config.toml                                 # [asr]@30-41; [output]@44-47                              ← EDIT
tests/test_config.py                        # defaults/cuda_check/partial-table asserts; type-guard suite ← EDIT
tests/test_config_repo_default.py           # key set + comment pin                                       ← EDIT
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/config.py                      # MODIFY: -2 fields, 0.5→0.8, +context_prompt, +streaming, +CancelConfig+cancel+overlay, +guards
config.toml                                 # MODIFY: -2 keys, 0.8, +3 keys + [cancel] section, end-state comments
tests/test_config.py                        # MODIFY: assert deltas + new guard/overlay/unknown-key cases
tests/test_config_repo_default.py           # MODIFY: 21-key/6-section set, docstring count, comment test → end-state binds
# NOTHING ELSE. daemon/ctl/cuda_check/prefetch/recorder_host/hypr-binds/README = P1.M1.T2 / P1.M3.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — INTENTIONAL TRANSITIONAL BREAKAGE. Removing the fields breaks daemon.py:152
# (cfg.asr.final_model -> AttributeError) and ~55 references across cuda_check/ctl/prefetch/
# recorder_host + test_daemon(29)/test_recorder_host/test_control_socket/test_voicectl/test_feed_audio.
# Those suites are EXPECTED RED until P1.M1.T2 lands. DO NOT chase or "fix" them in S1 — S1's gates
# are ONLY tests/test_config.py + tests/test_config_repo_default.py. Scope-guard L4 asserts this.

# CRITICAL #2 — ATOMIC QUAD. The drift guard (config.toml parse == defaults) + exact key set +
# from_toml's unknown-key TypeError mean config.py, config.toml, AND both test files must move in
# ONE change. Leaving final_model in config.toml after removing the field = TypeError at load.

# CRITICAL #3 — END-STATE KEY SET. asr: lite_model, language, device, post_speech_silence_duration,
# lite_post_speech_silence_duration, context_prompt, realtime_processing_pause, auto_stop_idle_seconds,
# auto_unload_idle_seconds (9). output: backend, append_space, streaming (3). cancel: on_backspace,
# devices (2). feedback (4), filter (2), log (1). TOTAL 21 keys / 6 SECTIONS. Docstring: "21 schema
# keys" (the current "20" is stale — actual today is 19).

# CRITICAL #4 — END-STATE BIND VOCABULARY. config.toml comments must describe the POST-COLLAPSE
# binds: ONE toggle bind "Ctrl+Alt+Super+D" and ONE cancel bind "Alt+Super+Backspace". The lite_model
# comment must STOP citing toggle-lite/SUPER+ALT+D-as-lite-bind (toggle-lite is removed). The comment
# test (test_repo_config_lite_model_comment_names_correct_keybind) must be updated to pin the
# end-state strings — use the EXACT same phrasing in comment and assertions.

# CRITICAL #5 — tmux_target IS ALREADY GONE; backend already "wtype"|"ydotool"|"null". Do not
# re-add or re-comment. The PRD §4.5 [output] block matches the current code.

# CRITICAL #6 — VALIDATION PATTERNS. Numerics: keep the existing 5-name tuple (0.8 is still float —
# NO new numerics). New bool guards (context_prompt/streaming/on_backspace): `if not isinstance(v,
# bool): raise TypeError(f"[section] {name} expects bool, got {type(v).__name__}: {v!r}")`. devices:
# copy FilterConfig's blocklist list-of-str guard style (config.py:213-236 — read it before writing).
# TypeError for type, ValueError for value (device/backend precedent).

# GOTCHA #7 — SECTION ORDER. Follow PRD §4.5: [asr], [output], [cancel], [feedback], [filter], [log].
# CancelConfig dataclass goes between OutputConfig and FeedbackConfig; VoiceTypingConfig.cancel field
# + _overlay(CancelConfig, "cancel") go after output's.

# GOTCHA #8 — blocklist stays default_factory (per-instance list); CancelConfig.devices does too
# (`field(default_factory=list)`), mirroring FilterConfig.blocklist (test_blocklist_not_shared pins it).

# GOTCHA #9 — cuda_check parity test: drop ONLY the final_model/realtime_model asserts from
# test_defaults_match_cuda_check (keep the device assert — CUDA_DEFAULTS still has that key until
# T2.S1). Full parity migration is P1.M1.T2.S1's job.

# GOTCHA #10 — TIMEOUTS (repo AGENTS.md): wrap pytest in `timeout 120`; never run the live daemon.
```

## Implementation Blueprint

### Data models and structure

The data-model change IS the task. End state:

```python
@dataclass
class AsrConfig:            # 9 fields
    lite_model: str = "small.en"           # the single model (Rev 2 single-mode)
    language: str = "en"
    device: str = "cuda"
    post_speech_silence_duration: float = 0.6
    lite_post_speech_silence_duration: float = 0.8   # Rev 2 §4.2quater: endpointer only delays COMMIT
    context_prompt: bool = True                       # Rev 2: rolling context conditioning
    realtime_processing_pause: float = 0.15
    auto_stop_idle_seconds: float = 30.0
    auto_unload_idle_seconds: float = 1800.0
    # __post_init__: numeric tuple (5 names, unchanged) + bool guard for context_prompt
    #                + string tuple -> ("lite_model", "language", "device") + device ValueError

@dataclass
class OutputConfig:         # backend, append_space, streaming: bool = True + backend ValueError + streaming bool guard

@dataclass
class CancelConfig:         # on_backspace: bool = True; devices: list[str] = field(default_factory=list)
                            # __post_init__: bool guard + list-of-str guard (FilterConfig style)

@dataclass
class VoiceTypingConfig:    # asr, output, cancel, feedback, filter, log  (+ _overlay for cancel)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/config.py — AsrConfig.
  - DELETE lines 52-53 (final_model/realtime_model). At :59 change 0.5 -> 0.8 and update the trailing
    comment to the PRD text ("Rev 2 §4.2quater: the endpointer only delays COMMIT under streaming (words
    are already typed live) — 0.8 halves mid-thought cuts for +0.3 s commit latency. 0.5 = razor-snappy;
    1.0 = near-zero cuts."). ADD after it:
        context_prompt: bool = True  # Rev 2 §4.2quater: condition every decode on the rolling committed
                                     # context (back to the last sentence boundary, ~200-token cap)
  - __post_init__: string tuple :99 becomes ("lite_model", "language", "device"). ADD a bool guard for
    context_prompt (Gotcha #6 pattern) after the string guard.

Task 2: EDIT voice_typing/config.py — OutputConfig + new CancelConfig + VoiceTypingConfig + from_toml.
  - OutputConfig: add `streaming: bool = True` after append_space with the PRD comment ("type stabilized
    partials live + revise in place; false = append-only finals (rollback hatch)"); add its bool guard
    to __post_init__ (keep the backend ValueError).
  - ADD CancelConfig between OutputConfig and FeedbackConfig (fields + comments per Data-models block;
    __post_init__ guards: on_backspace bool; devices must be list and every element str).
  - VoiceTypingConfig: add `cancel: CancelConfig = field(default_factory=CancelConfig)` after output.
  - from_toml: add `cancel=_overlay(CancelConfig, "cancel"),` after the output line.

Task 3: EDIT config.toml.
  - DELETE the final_model (L32) and realtime_model (L33) lines.
  - lite_model comment (L34): rewrite for END state — single model, toggled with Ctrl+Alt+Super+D; NO
    toggle-lite/SUPER+ALT+D-as-lite-bind phrasing (Gotcha #4).
  - lite_post_speech_silence_duration (L38): 0.5 -> 0.8 with the Task-1 comment text.
  - ADD `context_prompt = true` (PRD comment) after it.
  - [output]: ADD `streaming = true` (PRD comment).
  - ADD `[cancel]` section after [output] (on_backspace, devices; PRD §4.5 wording incl. the
    Alt+Super+Backspace bind mention).
  - Keep every other key/comment untouched (tmux_target absent; backend comment already correct).

Task 4: EDIT tests/test_config.py.
  - test_defaults_match_prd_4_5: delete the final_model/realtime_model asserts; 0.5 -> 0.8; add
    context_prompt/streaming/on_backspace/devices default asserts.
  - test_defaults_match_cuda_check: delete ONLY the final_model/realtime_model asserts (keep device).
  - test_from_toml_partial_table_keeps_other_defaults: replace the final_model assert with
    `cfg.asr.lite_model == "small.en"`; add a `[cancel]` partial-table line (e.g. {"cancel": {"on_backspace": false}}
    -> devices stays []).
  - ADD cases (follow the existing idioms @119/142/150/156/171):
      * int-for-bool raises (context_prompt=1, streaming=1, on_backspace=0 -> TypeError naming the field)
      * devices wrong type (devices = "event3" -> TypeError) and list-with-non-str (["a", 3] -> TypeError)
      * unknown key in [cancel] raises (on_backspce typo)
      * lite_post_speech_silence_duration=0.8 round-trip via from_toml
  - grep the file for residual final_model/realtime_model references and clean all of them (9 today).

Task 5: EDIT tests/test_config_repo_default.py.
  - expected set -> the 21-key/6-section map (Critical #3), sections asr/output/cancel/feedback/filter/log.
  - docstring: "only the 21 schema keys".
  - test_repo_config_lite_model_comment_names_correct_keybind: repoint to the end-state binds — assert
    "Ctrl+Alt+Super+D" IS in the lite_model line, "Alt+Super+Backspace" IS in the file (cancel section
    or lite line), and "toggle-lite" is NOT in the lite_model line. Rename the test to match its new
    meaning (e.g. ..._names_end_state_binds).

Task 6: VALIDATE (gates below). No git commit unless the orchestrator directs. If asked, message:
  "P1.M1.T1.S1: Rev 2 config schema delta (remove 2-model fields, 0.8 endpointer, context_prompt/streaming/[cancel])".
```

### Implementation Patterns & Key Details

```python
# The whole task is the atomic quad (config.py + config.toml + 2 test files). Invariants:
#   (1) config.toml parse == VoiceTypingConfig()  [equals-defaults]
#   (2) config.toml key set == expected 21-key map [no-extra-keys]
#   (3) every wrong-typed new knob raises TypeError AT LOAD (before systemd loops)
#   (4) bool guard: isinstance(v, bool) — note int/bool asymmetry: numerics REJECT bool, bools REJECT int.
# devices guard shape (mirror FilterConfig.blocklist @213-236 — read it first):
#   if not isinstance(self.devices, list) or not all(isinstance(d, str) for d in self.devices):
#       raise TypeError(f"[cancel] devices expects a list of str, got ...")
# Transitional state (expected, by design): daemon.py:152 AttributeError; cuda_check keys intact;
# test_daemon/test_recorder_host/test_control_socket/test_voicectl/test_feed_audio RED until P1.M1.T2.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (NOT S1): P1.M1.T2.S2 (cfg_to_kwargs loses final/realtime kwargs), T2.S1 (cuda_check
  single-model contract — CUDA_DEFAULTS/CPU_FALLBACK still carry the old keys until then), T2.S3 (ctl),
  T2.S4 (binds/ACCEPTANCE — owns hypr-binds.conf; S1's config comments just PRE-describe the end state),
  P1.M2.T5 (context_prompt), P1.M2.T6 (streaming), P1.M2.T7.S2 (cancel.devices enumeration).
INSTALL/README: untouched in S1 (P1.M3.T10).
NO INTERFACE CHANGES beyond the schema itself; [cancel] is additive; removals are internal until T2.
```

## Validation Loop

> Repo AGENTS.md: wrap pytest in `timeout 120` + a bash-tool timeout above it; .venv/bin/python; never the live daemon. No ruff/mypy. S1 gates are ONLY the two owned test files (Gotcha #1).

### Level 1: Schema + file deltas landed (static)

```bash
cd /home/dustin/projects/voice-typing
grep -c "final_model\|realtime_model" voice_typing/config.py | grep -q '^1$' && echo "L1a PASS (only the string-tuple-less residue=1? see below)" || echo "L1a CHECK"
grep -q 'lite_post_speech_silence_duration: float = 0.8' voice_typing/config.py && echo ok1
grep -q 'context_prompt: bool = True' voice_typing/config.py && echo ok2
grep -q 'streaming: bool = True' voice_typing/config.py && echo ok3
grep -q 'class CancelConfig' voice_typing/config.py && grep -q 'cancel=_overlay(CancelConfig, "cancel")' voice_typing/config.py && echo ok4
grep -qE 'final_model|realtime_model' voice_typing/config.py && echo "L1b FAIL: residue in config.py" || echo "L1b PASS (fields fully removed)"
grep -qE 'final_model|realtime_model' config.toml && echo "L1c FAIL: stale keys in config.toml" || echo "L1c PASS"
# Expected: ok1-4 + L1b/L1c PASS (L1a may read 1 if the cuda_check-parity test docstring mentions them
# in tests/ — config.py itself must be clean per L1b).
```

### Level 2: The two owned test files are green (the S1 gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q 2>&1 | tail -5
# Expected: all passed. If equals-defaults fails -> a config.toml value != dataclass default (0.8 both
# sides?). If no-extra-keys fails -> the expected set is not the 21-key/6-section map.
```

### Level 3: Functional spot-check (one-off)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing.config import VoiceTypingConfig, AsrConfig, CancelConfig
import pytest if False else None
c = VoiceTypingConfig()
assert c.asr.lite_post_speech_silence_duration == 0.8 and c.asr.context_prompt is True
assert c.output.streaming is True and c.cancel.on_backspace is True and c.cancel.devices == []
assert not hasattr(c.asr, "final_model") and not hasattr(c.asr, "realtime_model")
for bad in ({"cancel": {"on_backspace": 1}}, {"cancel": {"devices": "x"}}, {"cancel": {"devices": [1]}},
            {"asr": {"context_prompt": 1}}, {"output": {"streaming": 0}}, {"cancel": {"on_backspce": True}}):
    try:
        VoiceTypingConfig.from_toml(bad); print("L3 FAIL:", bad)
    except TypeError: pass
print("L3 PASS: defaults + guards + unknown-key all behave")
PY
```

### Level 4: Scope — only the four files; transitional breakage left for T2

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/config\.py|config\.toml|tests/test_config\.py|tests/test_config_repo_default\.py' | grep -E '\.py$|\.toml$|\.conf$|\.md$|\.sh$' && echo "L4 FAIL: out of scope" || echo "L4 PASS: only the 4 files"
echo "--- confirm the transitional-break files are UNTOUCHED (T2 owns them) ---"
git diff --name-only | grep -E 'daemon\.py|cuda_check\.py|ctl\.py|prefetch\.py|recorder_host\.py|test_daemon\.py|test_recorder_host\.py' && echo "L4 FAIL: chased downstream refs" || echo "L4 PASS: downstream refs untouched"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: fields/keys landed exactly (0.8, context_prompt, streaming, CancelConfig+cancel+overlay); no final_model/realtime_model residue in config.py/config.toml.
- [ ] L2: `tests/test_config.py` + `tests/test_config_repo_default.py` green under `timeout 120`.
- [ ] L3: defaults + wrong-type guards + `[cancel]` unknown-key + partial-table overlay behave.
- [ ] L4: only the four files changed; daemon/cuda_check/ctl/prefetch/recorder_host/test_daemon untouched.

### Feature Validation
- [ ] End-state schema = PRD §4.5 Rev 2 (minus the two stale [asr] entries per contract): 21 keys / 6 sections.
- [ ] config.toml comments in the end-state bind vocabulary (Ctrl+Alt+Super+D toggle; Alt+Super+Backspace cancel), pinned by the updated comment test.
- [ ] New knobs fail fast on wrong types at load (systemd crash-loop prevention).

### Code Quality Validation
- [ ] Validation mirrors existing idioms (TypeError type / ValueError value; FilterConfig list-of-str style).
- [ ] `devices` uses `default_factory` (per-instance list, like blocklist).
- [ ] Section/field order follows PRD §4.5.

### Scope Boundary Validation
- [ ] No daemon/ctl/cuda_check/prefetch/recorder_host/hypr-binds/README/install.sh changes.
- [ ] Transitional red suites (test_daemon etc.) documented as expected, NOT chased (P1.M1.T2 owns).
- [ ] No live daemon run.

---

## Anti-Patterns to Avoid

- ❌ Don't chase the ~60 downstream references (daemon.py:152, cuda_check, test_daemon ×29…) — that's P1.M1.T2; S1's gates are the two config test files only.
- ❌ Don't leave final_model/realtime_model in config.toml after removing the fields — from_toml's unknown-key TypeError breaks the drift guard.
- ❌ Don't use int/bool loosely in guards — numerics REJECT bool; the NEW bool fields must REJECT non-bool (context_prompt=1 is a TypeError).
- ❌ Don't re-add tmux_target or rewrite the backend comment — the code is already at the Rev 2 [output] shape.
- ❌ Don't cite toggle-lite/SUPER+ALT+D-as-lite-bind in config.toml comments — write the END-state binds (toggle-lite is removed in the collapse; the cancel bind is Alt+Super+Backspace) and keep comment + test assertions in identical phrasing.
- ❌ Don't validate device VALUES beyond the existing wtype/ydotool/null + cuda/cpu sets (already done).
- ❌ Don't forget the docstring key count — "21 schema keys" (the current "20" is stale; actual today is 19, post-delta 21).
- ❌ Don't drop the `device` assert from test_defaults_match_cuda_check — only final_model/realtime_model go.
- ❌ Don't run unwrapped pytest or the live daemon — `timeout 120` on everything (repo AGENTS.md).

---

## Confidence Score

**9/10** for one-pass success. Every edit site is quoted verbatim with re-verified line numbers; the end-state schema (21 keys/6 sections), the validation idioms to copy, the atomicity invariants (drift guard + unknown-key rejection), and the blast radius/staging are all pinned. The −1 covers two residual risks: (a) the working tree moves — the cited line numbers can drift (mitigated: L1 grep gates assert content, not lines); (b) the end-state bind phrasing in config.toml comments must exactly match the updated comment test — Critical #4 prescribes identical strings for both, and L2's drift-guard failure mode names the mismatch.
