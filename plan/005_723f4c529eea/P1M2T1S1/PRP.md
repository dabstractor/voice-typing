# PRP — P1.M2.T1.S1: Override `post_speech_silence_duration` in `cfg_to_kwargs` lite path + kwargs tests

## Goal

**Feature Goal**: Wire the load-bearing lite-mode perceived-latency lever (PRD §4.2ter): in `cfg_to_kwargs`, the lite path must override `post_speech_silence_duration` with `cfg.asr.lite_post_silence_duration` (default `0.5`) instead of inheriting the normal-mode `0.6`. The silence gate — not the model — is the perceived-latency bottleneck (the small model's ~50 ms transcription win is swamped by the silence wait); without this override lite feels no faster than normal. This is a **one source line + one comment fix + one test update + one new test**.

**Deliverable** (2 files; no new files):
1. `voice_typing/daemon.py` — (a) in the `if lite:` block of `cfg_to_kwargs`, add `kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration` after the existing `use_main_model_for_realtime=True` line; (b) fix the stale `_DRAIN_TIMEOUT_S` comment ("~1.5s" → "~0.6s normal / ~0.5s lite"). Verbatim oldText→newText in Implementation Blueprint.
2. `tests/test_daemon.py` — (c) update `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` (add `post_speech_silence_duration` to the `differing` set + the two value assertions + docstring/comment); (d) add `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` (default 0.5, override 0.3, normal 0.6).

**Success Definition**:
- (a) `daemon.cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == 0.5` (default); an override (`cfg.asr.lite_post_speech_silence_duration = 0.3`) flows through to `== 0.3`.
- (b) `daemon.cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6` — normal mode UNAFFECTED.
- (c) `.venv/bin/python -m pytest tests/test_daemon.py -k 'lite' -v` → all lite tests pass (the updated drift guard + the new test + the existing lite model/cpu-fallback tests).
- (d) Full fast sweep `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (verified no other test asserts lite's silence duration — see Context).
- (e) Only `voice_typing/daemon.py` + `tests/test_daemon.py` modified.

## User Persona

Not applicable (internal wiring of a config field; no user-facing surface change beyond lite feeling snappier — DOCS: Mode A = the `_DRAIN_TIMEOUT_S` comment fix; the user-facing config field doc is the config.toml comment from P1.M1.T1.S1).

## Why

- **§4.2ter's load-bearing latency finding.** Live latency-log measurement showed the small model's final pass (~80 ms) is only ~50 ms faster than the large model (~130 ms) — swamped by the `post_speech_silence_duration` silence wait, which is identical across modes unless lite overrides it. A 1.5 s gate made lite feel "no faster than the big model". Lite MUST use its own snugger gate (default 0.5) to cut stop→text latency from ~1.6 s to ~0.6 s — that is what makes lite actually FEEL instant. The config field shipped (P1.M1.T1.S1); THIS task wires it into the recorder kwargs.
- **Drift guard correctness.** `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` currently asserts lite changes ONLY 3 keys; after this fix `post_speech_silence_duration` becomes a 4th allowed difference. The test MUST be updated in lockstep or it fails (the "remaining dicts byte-identical" check would see the 0.5/0.6 mismatch).
- **Acceptance #10.** "lite uses its own shorter `post_speech_silence_duration` … so it is observably snappier end-to-end, not just faster at transcription." This task is the kwargs-level half of that (the feed-audio latency proof is T7 / P1.M2 of the lite-mode plan).

## What

Lite kwargs carry `post_speech_silence_duration=0.5` (or the configured `lite_post_speech_silence_duration`); normal kwargs carry `0.6` (unchanged). The override mirrors the existing `use_main_model_for_realtime` override pattern (common block sets it, lite block overrides it). Plus a stale-comment fix + test updates.

### Success Criteria

- [ ] `cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == cfg.asr.lite_post_speech_silence_duration` (0.5 default; override flows through).
- [ ] `cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6` (normal unchanged).
- [ ] `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` updated (`differing` includes `post_speech_silence_duration`; +0.5/+0.6 assertions).
- [ ] `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` added + passes.
- [ ] `_DRAIN_TIMEOUT_S` comment corrected ("~0.6s normal / ~0.5s lite").
- [ ] `pytest tests/test_daemon.py -k 'lite' -v` all pass; full fast sweep 0 failed; only 2 files changed.

## All Needed Context

### Context Completeness Check

_Pass._ The exact edit sites (with verified current line numbers), the verbatim old→new for all 4 edits, the field's confirmed state (`AsrConfig.lite_post_speech_silence_duration: float = 0.5` at config.py:59, in the validation tuple at :87), the override-pattern rationale, the test-update necessity (drift guard would fail otherwise), and a verified regression scan (no other test asserts lite's silence duration) are all below. An agent new to this repo can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — exact edit sites + override pattern + regression scan + scope (load-bearing)
- docfile: plan/005_723f4c529eea/P1M2T1S1/research/lite_silence_override.md
  why: "§2 the exact daemon.py edit sites (cfg_to_kwargs lite block @205-208; _DRAIN_TIMEOUT_S comment @136 — NOTE the
        contract's '~line 94' drifted to 136; find by symbol). §3 the test changes. §4 the regression scan (lines 119/263/
        271/2583 are all NORMAL-mode or key-set assertions — unaffected; only line 197's drift guard needs updating). §5 scope."
  section: "§2 (edit sites) and §4 (no-regression scan) are load-bearing."

# THE FIELD (consume; LANDED by P1.M1.T1.S1)
- file: voice_typing/config.py
  why: "AsrConfig.lite_post_speech_silence_duration: float = 0.5 (@59) — the value the lite override reads. In the numeric-
        validation tuple (@87). Default 0.5 (the snugger gate); normal post_speech_silence_duration is 0.6 (@58). DO NOT edit
        config.py (P1.M1.T1.S1 owns the field)."
  critical: "Read cfg.asr.lite_post_speech_silence_duration in the lite block — NOT cfg.asr.post_speech_silence_duration (that's
             the 0.6 normal value). The two field names are easy to conflate."

# THE EDIT SITE (daemon.py)
- file: voice_typing/daemon.py
  why: "cfg_to_kwargs @158. The common kwargs dict sets `post_speech_silence_duration: cfg.asr.post_speech_silence_duration`
        (~196) for BOTH modes. The `if lite:` block @205-208 overrides use_main_model_for_realtime=True. ADD the silence override
        there (after the use_main_model line) — it overrides the common-block value, mirroring the use_main_model override pattern
        (False in _FIXED_KWARGS, overridden in lite). _DRAIN_TIMEOUT_S @138; its comment @132-137 has the stale '~1.5s' at @136."
  pattern: "common block sets the value for both modes → lite block overrides for lite only (same as use_main_model_for_realtime)."
  gotcha: "Place the override INSIDE `if lite:` (after use_main_model_for_realtime=True), NOT in the common dict — normal mode
           must keep 0.6."

# THE TEST FILE (test_daemon.py)
- file: tests/test_daemon.py
  why: "test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal @185 (differing set @197; the byte-identical assertion @201-202 would
        FAIL without adding post_speech_silence_duration to `differing`). The `cfg` fixture @103 (function-scoped -> safe to mutate
        cfg.asr.lite_post_speech_silence_duration in the new test). _cuda_resolve @80 (the sibling pattern: _cuda_resolve(monkeypatch,
        daemon.cuda_check.CUDA_DEFAULTS) before calling cfg_to_kwargs)."
  critical: "The drift-guard test MUST be updated in the SAME change as the source line — otherwise it fails (0.5 != 0.6 in the
             byte-identical check). Find the test by NAME (line numbers drift)."

# THE PRD CONTRACT (the latency lever)
- file: PRD.md
  why: "§4.2ter 'The silence gate, not the model, is the perceived-latency bottleneck' + 'lite MUST use its own shorter
        post_speech_silence_duration (default 0.5)'. §4.4 'Lite mode … AND a snugger post_speech_silence_duration =
        lite_post_speech_silence_duration'. §4.5 the config field. Acceptance #10 'lite uses its own shorter
        post_speech_silence_duration … observably snappier end-to-end'."

# PARALLEL CONTEXT — P1.M1.T2.S1 (config unit tests; NO overlap)
- docfile: plan/005_723f4c529eea/P1M1T2S1/PRP.md
  why: "T2.S1 (Implementing) adds config unit tests in tests/test_config.py for the field (default/round-trip/wrong-type/type).
        It does NOT touch daemon.py or test_daemon.py. No file overlap. It depends only on the field existing (P1.M1.T1.S1 landed
        it); this task wires the field into cfg_to_kwargs. Clean parallel boundary."
```

### Current Codebase tree (relevant slice — the 2 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py   # EDIT: cfg_to_kwargs lite block @205-208 (+1 line) + _DRAIN_TIMEOUT_S comment @136 (1-line fix).
└── tests/
    └── test_daemon.py   # EDIT: update test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal @185 + add test_cfg_to_kwargs_lite_uses_shorter_silence_duration.
# config.py (AsrConfig.lite_post_speech_silence_duration @59) — LANDED, UNCHANGED. config.toml — LANDED. test_config.py — P1.M1.T2.S1.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py    # EDIT — +1 line in cfg_to_kwargs lite block; 1-line _DRAIN_TIMEOUT_S comment fix.
tests/test_daemon.py      # EDIT — update 1 test (differing set + assertions + docstring) + add 1 test.
# NOTHING ELSE. (config.py/config.toml = P1.M1.T1.S1. test_config.py = P1.M1.T2.S1. README/ACCEPTANCE = P1.M3.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — READ cfg.asr.lite_post_speech_silence_duration (0.5), NOT cfg.asr.post_speech_silence_duration (0.6). The two
#   field names differ by only "lite_"; using the wrong one silently makes lite inherit 0.6 (the exact bug this fixes).

# CRITICAL #2 — PLACE THE OVERRIDE INSIDE `if lite:`, AFTER use_main_model_for_realtime=True. The common kwargs dict (~196) sets
#   post_speech_silence_duration for BOTH modes; the lite block overrides it for lite ONLY. Putting it in the common dict would
#   wrongly change normal mode to 0.5. Mirror the existing use_main_model_for_realtime override pattern.

# CRITICAL #3 — UPDATE THE DRIFT-GUARD TEST IN THE SAME CHANGE. test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal asserts the
#   non-differing keys are byte-identical; without adding post_speech_silence_duration to `differing`, it FAILS (lite 0.5 !=
#   normal 0.6). The source line + the test update are ONE atomic change.

# CRITICAL #4 — _DRAIN_TIMEOUT_S COMMENT IS AT LINE 136 (NOT ~94 as the contract approximated). Find by the `_DRAIN_TIMEOUT_S`
#   symbol. The stale text is "~1.5s trailing silence"; the actual is 0.6 (normal) / 0.5 (lite). Mode A doc fix.

# GOTCHA #5 — the `cfg` fixture is function-scoped (safe to mutate cfg.asr.lite_post_speech_silence_duration in the new test);
#   it does not leak across tests. _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS) must precede cfg_to_kwargs in the
#   new test (the sibling pattern) so the cuda path is deterministic.

# GOTCHA #6 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest/uv.

# GOTCHA #7 — pytest>=9.1.1 is the runner; NO ruff/mypy. Validation = py_compile + pytest.
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/source-logic change beyond reading an existing field into an existing kwargs key. This is a one-line kwargs override + a comment fix + test updates.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — cfg_to_kwargs lite block: add the post_speech_silence_duration override
  - FIND the `if lite:` block at the end of cfg_to_kwargs (the one with `kwargs["use_main_model_for_realtime"] = True`).
  - EDIT (oldText -> newText):
      OLD:
            if lite:
                # Lite mode (§4.2ter): ONE model for both realtime + final. Overrides the
                # use_main_model_for_realtime=False from _FIXED_KWARGS; verified to skip the realtime engine.
                kwargs["use_main_model_for_realtime"] = True
            return kwargs
      NEW:
            if lite:
                # Lite mode (§4.2ter): ONE model for both realtime + final. Overrides the
                # use_main_model_for_realtime=False from _FIXED_KWARGS; verified to skip the realtime engine.
                kwargs["use_main_model_for_realtime"] = True
                # §4.2ter latency lever: the silence gate (not the model) is the perceived-latency bottleneck, so lite
                # uses its own SNUGGER post_speech_silence_duration (default 0.5 vs normal 0.6) to actually feel faster.
                # Overrides the common-block value set above; mirrors the use_main_model_for_realtime override pattern.
                kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration
            return kwargs
  - WHY: overrides the common-block 0.6 with the lite 0.5 for lite mode only (CRITICAL #1, #2). Normal mode (no `if lite:`
    entry) keeps 0.6.
  - DO NOT: read cfg.asr.post_speech_silence_duration (that's 0.6); place the line in the common dict; change any other kwarg.

Task 2: EDIT voice_typing/daemon.py — fix the stale _DRAIN_TIMEOUT_S comment (Mode A)
  - FIND the _DRAIN_TIMEOUT_S comment block (line ~132-137; the constant is `_DRAIN_TIMEOUT_S: float = 5.0` at ~138).
  - EDIT (oldText -> newText) — the one stale line:
      OLD:
            # post_speech_silence_duration (~1.5s trailing silence to trigger finalization) + the final model's
      NEW:
            # post_speech_silence_duration (~0.6s normal / ~0.5s lite trailing silence to trigger finalization) + the final model's
  - WHY: the actual value is 0.6 (normal) / 0.5 (lite), not ~1.5s (an old default). Mode A (comment in an edited file, about
    the value being changed). Find by the `_DRAIN_TIMEOUT_S` symbol — the contract's "~line 94" drifted to ~136 (CRITICAL #4).
  - DO NOT: change the _DRAIN_TIMEOUT_S value (5.0) — only the comment.

Task 3: EDIT tests/test_daemon.py — update test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal (the drift guard)
  - FIND by NAME (test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal). Apply TWO edits:
  - EDIT 3a — the docstring's first line + a clarifying note:
      OLD:
            """Lite mode changes ONLY model/realtime_model_type/use_main_model_for_realtime — nothing else.

            Drift guard (PRD §4.2ter): device/compute_type/language/timing/VAD/silero must be IDENTICAL
            between lite and normal mode on CUDA, so a future cfg_to_kwargs / _FIXED_KWARGS edit can't
            silently diverge lite from normal. The CUDA-lite model pick itself is pinned by
            test_cfg_to_kwargs_lite_mode_uses_one_model; this test guards the REST of the kwargs dict.
            """
      NEW:
            """Lite mode changes ONLY model/realtime_model_type/use_main_model_for_realtime/post_speech_silence_duration.

            Drift guard (PRD §4.2ter): device/compute_type/language/timing/VAD/silero must be IDENTICAL
            between lite and normal mode on CUDA, so a future cfg_to_kwargs / _FIXED_KWARGS edit can't
            silently diverge lite from normal. The CUDA-lite model pick itself is pinned by
            test_cfg_to_kwargs_lite_mode_uses_one_model; this test guards the REST of the kwargs dict.
            (post_speech_silence_duration is the 4th allowed difference — §4.2ter: lite's snugger silence gate is the
            perceived-latency lever; its value is pinned by test_cfg_to_kwargs_lite_uses_shorter_silence_duration.)
            """
  - EDIT 3b — the differing set + the byte-identical comment + the value assertions:
      OLD:
            differing = {"model", "realtime_model_type", "use_main_model_for_realtime"}
            # 1) the key SETS are identical (no kwarg silently added/dropped by lite):
            assert set(normal) == set(lite)
            # 2) after removing the 3 allowed-to-differ keys, the remaining dicts are byte-identical:
            assert {k: v for k, v in lite.items() if k not in differing} == \
                   {k: v for k, v in normal.items() if k not in differing}
            # 3) and the 3 differing keys differ EXACTLY as the spec requires:
            assert lite["model"] == cfg.asr.lite_model == "small.en"        # lite_model as the final model
            assert lite["realtime_model_type"] == "small.en"                # AND the realtime model (one model)
            assert lite["use_main_model_for_realtime"] is True              # skips the realtime engine
            assert normal["model"] == "distil-large-v3"
            assert normal["realtime_model_type"] == "small.en"
            assert normal["use_main_model_for_realtime"] is False
      NEW:
            differing = {"model", "realtime_model_type", "use_main_model_for_realtime", "post_speech_silence_duration"}
            # 1) the key SETS are identical (no kwarg silently added/dropped by lite):
            assert set(normal) == set(lite)
            # 2) after removing the 4 allowed-to-differ keys, the remaining dicts are byte-identical:
            assert {k: v for k, v in lite.items() if k not in differing} == \
                   {k: v for k, v in normal.items() if k not in differing}
            # 3) and the 4 differing keys differ EXACTLY as the spec requires:
            assert lite["model"] == cfg.asr.lite_model == "small.en"        # lite_model as the final model
            assert lite["realtime_model_type"] == "small.en"                # AND the realtime model (one model)
            assert lite["use_main_model_for_realtime"] is True              # skips the realtime engine
            assert lite["post_speech_silence_duration"] == 0.5              # §4.2ter: snugger lite silence gate
            assert normal["model"] == "distil-large-v3"
            assert normal["realtime_model_type"] == "small.en"
            assert normal["use_main_model_for_realtime"] is False
            assert normal["post_speech_silence_duration"] == 0.6            # normal mode unchanged
  - WHY: without adding post_speech_silence_duration to `differing`, the byte-identical assertion (#2) FAILS (lite 0.5 !=
    normal 0.6). The new assertions pin the exact values. (CRITICAL #3.)
  - DO NOT: change the `set(normal) == set(lite)` assertion (key SET is unchanged); change the model/use_main assertions.

Task 4: EDIT tests/test_daemon.py — ADD test_cfg_to_kwargs_lite_uses_shorter_silence_duration
  - INSERT immediately AFTER test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal (before test_cfg_to_kwargs_fixed_values).
    Verbatim:
        def test_cfg_to_kwargs_lite_uses_shorter_silence_duration(cfg, monkeypatch):
            """Lite uses its own snugger post_speech_silence_duration (§4.2ter latency lever); normal is unaffected.

            The silence gate — not the model — is the perceived-latency bottleneck (PRD §4.2ter), so lite MUST shorten
            post_speech_silence_duration to actually feel faster. Pins: (a) the default lite value (0.5) reaches the kwargs;
            (b) an override flows through; (c) normal mode is unchanged (0.6).
            """
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
            # (a) default: lite carries the snugger 0.5; normal carries 0.6.
            assert daemon.cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == 0.5
            assert daemon.cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6
            # (b) override flows through lite only (cfg fixture is function-scoped -> safe to mutate):
            cfg.asr.lite_post_speech_silence_duration = 0.3
            assert daemon.cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == 0.3
            # (c) normal is unaffected by the lite override (still the normal cfg value):
            assert daemon.cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6
  - WHY: dedicated coverage for the override (default, override, normal-unaffected) — the drift guard only proves it's an
    allowed difference; this test pins the override MECHANISM. Reuses the `cfg` fixture + `_cuda_resolve` (sibling pattern).
  - DO NOT: add a separate fixture; mutate a shared/session cfg (the `cfg` fixture is function-scoped, safe).

Task 5: VALIDATE — run the Validation Loop L1-L3; fix until green. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S1: cfg_to_kwargs lite overrides post_speech_silence_duration (0.5) — the §4.2ter latency lever".
```

### Implementation Patterns & Key Details

```python
# PATTERN — the lite override mirrors the use_main_model_for_realtime override. The common kwargs dict sets the value for BOTH
# modes; the `if lite:` block overrides it for lite ONLY. Normal mode (no lite entry) keeps the common value.
# common dict (~196): "post_speech_silence_duration": cfg.asr.post_speech_silence_duration   # 0.6 for both
# lite block:
if lite:
    kwargs["use_main_model_for_realtime"] = True                                    # already there
    kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration   # NEW — overrides to 0.5

# PATTERN — the drift-guard test's `differing` set is the SINGLE SOURCE OF TRUTH for "what lite is allowed to change". Adding
# a lite override REQUIRES adding its key to `differing` in the same change, else the byte-identical assertion fails.
differing = {"model", "realtime_model_type", "use_main_model_for_realtime", "post_speech_silence_duration"}
```

### Integration Points

```yaml
UPSTREAM CONSUMED — AsrConfig.lite_post_speech_silence_duration (LANDED, config.py:59, P1.M1.T1.S1):
  - default 0.5; in the numeric-validation tuple (:87). Read in the lite block. DO NOT edit config.py.

DOWNSTREAM — the lite-mode latency proof:
  - T7 (test_feed_audio lite variant, lite-mode plan P1.M2) feeds utt_simple through the lite recorder and asserts materially-
    lower end-to-end latency — which holds ONLY because this override shortened the silence gate. Acceptance #10 references it.

UNCHANGED: normal-mode cfg_to_kwargs (0.6), _FIXED_KWARGS, _construct/build_recorder, cuda_check, config.py/config.toml,
  feedback.py, ctl.py, status.sh, the graceful-drain logic (_DRAIN_TIMEOUT_S value stays 5.0; only its comment is fixed).

PARALLEL — P1.M1.T2.S1 (config unit tests in tests/test_config.py): NO file overlap (it's test_config.py; this is daemon.py +
  test_daemon.py). It tests the field's default/type/validation; this task wires the field into cfg_to_kwargs. Clean boundary.

BUILD ARTIFACTS: NO new files, NO pyproject/uv.lock/.venv changes, NO new deps. Validation = py_compile + pytest.
```

## Validation Loop

> Full paths in every bash command (GOTCHA #6). Run from `/home/dustin/projects/voice-typing`. pytest is the runner
> (NO ruff/mypy — GOTCHA #7). All gates are fast/unit (no CUDA, no models — cfg_to_kwargs is pure).

### Level 1: source compiles + the override + comment are in place (static)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/daemon.py tests/test_daemon.py && echo "L1 PASS: py_compile" || echo "L1 FAIL"
grep -q 'kwargs\["post_speech_silence_duration"\] = cfg.asr.lite_post_speech_silence_duration' voice_typing/daemon.py && echo "L1 PASS: lite override present" || echo "L1 FAIL: override missing"
grep -q '~0.6s normal / ~0.5s lite' voice_typing/daemon.py && echo "L1 PASS: _DRAIN_TIMEOUT_S comment fixed" || echo "L1 FAIL: stale ~1.5s comment still present"
# the override reads the LITE field (not the normal one):
grep -q 'cfg.asr.lite_post_speech_silence_duration' voice_typing/daemon.py && ! grep -qE 'cfg\.asr\.post_speech_silence_duration.*lite|lite.*cfg\.asr\.post_speech' voice_typing/daemon.py && echo "L1 PASS: reads the lite field" || echo "L1 WARN: double-check it reads lite_post_speech_silence_duration"
```

### Level 2: the lite kwargs tests (the contract)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_daemon.py -k 'lite' -v
# Expected: all lite tests pass — the UPDATED test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal (now with the 4th differing
# key + 0.5/0.6 assertions) + the NEW test_cfg_to_kwargs_lite_uses_shorter_silence_duration + the existing
# test_cfg_to_kwargs_lite_mode_uses_one_model + test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en. 0 failed.
```

### Level 3: full fast sweep (no regression) + scope guard

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (Verified no other test asserts lite's post_speech_silence_duration: lines 119/263/271/2583 are all
# normal-mode or key-set assertions — unaffected. test_feed_audio.py is the heavy GPU suite, ignored.)
git status --short
# Expected: ONLY voice_typing/daemon.py (modified) + tests/test_daemon.py (modified). No config.py/config.toml (P1.M1.T1.S1),
# no test_config.py (P1.M1.T2.S1), no README/ACCEPTANCE (P1.M3).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: py_compile clean; the lite override line present; the `_DRAIN_TIMEOUT_S` comment fixed; reads `lite_post_speech_silence_duration`.
- [ ] L2: `pytest tests/test_daemon.py -k 'lite' -v` → all lite tests pass (updated drift guard + new test).
- [ ] L3: full fast sweep 0 failed; `git status` == `voice_typing/daemon.py` + `tests/test_daemon.py`.

### Feature Validation
- [ ] `cfg_to_kwargs(cfg, lite=True)["post_speech_silence_duration"] == 0.5` (default); override → 0.3.
- [ ] `cfg_to_kwargs(cfg)["post_speech_silence_duration"] == 0.6` (normal unchanged).
- [ ] `_DRAIN_TIMEOUT_S` comment no longer says ~1.5s.

### Code Quality Validation
- [ ] Override placed inside `if lite:` (mirrors `use_main_model_for_realtime`); reads the `lite_` field.
- [ ] Drift-guard `differing` set updated in lockstep with the source line.
- [ ] New test reuses the `cfg` fixture + `_cuda_resolve` (sibling pattern); function-scoped cfg mutation is safe.
- [ ] Full paths in every bash command.

### Scope Boundary Validation
- [ ] No config.py/config.toml (P1.M1.T1.S1); no test_config.py (P1.M1.T2.S1); no README/ACCEPTANCE (P1.M3).
- [ ] No new files; no new deps; no pyproject/uv.lock changes; `_DRAIN_TIMEOUT_S` value unchanged (5.0).

---

## Anti-Patterns to Avoid

- ❌ Don't read `cfg.asr.post_speech_silence_duration` (0.6) in the override — read `cfg.asr.lite_post_speech_silence_duration` (0.5). The names differ by only "lite_".
- ❌ Don't place the override in the common kwargs dict — it must be inside `if lite:` so normal mode keeps 0.6.
- ❌ Don't update the source line without updating `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal`'s `differing` set in the SAME change — the drift guard will fail (0.5 != 0.6 in the byte-identical check).
- ❌ Don't change the `_DRAIN_TIMEOUT_S` value (5.0) — only its stale "~1.5s" comment.
- ❌ Don't edit config.py/config.toml (P1.M1.T1.S1 owns the field) or test_config.py (P1.M1.T2.S1).
- ❌ Don't invent ruff/mypy commands — pytest only. Don't use bare python/pytest/uv (zsh aliases).
- ❌ Don't trust the contract's "~line 94" for `_DRAIN_TIMEOUT_S` — it's at ~136 (line drift); find by symbol.

---

## Confidence Score

**10/10** for one-pass implementation success. The change is a single source line (override `post_speech_silence_duration` in the existing `if lite:` block, mirroring the proven `use_main_model_for_realtime` override pattern), the config field is confirmed LANDED (`AsrConfig.lite_post_speech_silence_duration: float = 0.5` at config.py:59), the test update is mandatory and specified verbatim (the drift guard's `differing` set + value assertions), the new test reuses the existing `cfg` fixture + `_cuda_resolve` pattern, the stale-comment fix is a one-liner, and a verified regression scan confirms no other test asserts lite's silence duration (the 3 other `post_speech_silence_duration` references are all normal-mode or key-set assertions). All four edits are given as exact oldText→newText against the current file. No residual uncertainty.
