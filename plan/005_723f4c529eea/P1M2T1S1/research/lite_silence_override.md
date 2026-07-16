# Research: lite post_speech_silence_duration override in cfg_to_kwargs (P1.M2.T1.S1)

Target: make lite mode's `cfg_to_kwargs` override `post_speech_silence_duration` with
`cfg.asr.lite_post_speech_silence_duration` (default 0.5) — the load-bearing perceived-latency
lever per PRD §4.2ter (the silence gate, not the model, is the bottleneck). Plus update the
existing drift-guard test + add a dedicated test + fix a stale comment. PRD §4.2ter / §4.5 / §4.4.

---

## 1. The change is one source line + one comment + two test changes

The config field `AsrConfig.lite_post_speech_silence_duration: float = 0.5` is LANDED (config.py:59,
P1.M1.T1.S1 Complete; in the numeric-validation tuple config.py:87). The daemon's `cfg_to_kwargs`
(daemon.py:158) builds the common kwargs dict with `"post_speech_silence_duration":
cfg.asr.post_speech_silence_duration` (the 0.6 normal value) for BOTH modes, then the `if lite:`
block (daemon.py:205-208) overrides ONLY `use_main_model_for_realtime=True`. **Lite never overrides
the silence duration** → lite currently inherits 0.6, so it feels no faster than normal (the exact
failure §4.2ter warns about). The fix: add one line in the lite block.

## 2. Exact edit sites (verified line numbers in the current tree)

**(a) daemon.py `cfg_to_kwargs` lite block (205-208).** Current:
```python
    if lite:
        # Lite mode (§4.2ter): ONE model for both realtime + final. Overrides the
        # use_main_model_for_realtime=False from _FIXED_KWARGS; verified to skip the realtime engine.
        kwargs["use_main_model_for_realtime"] = True
    return kwargs
```
Add after the `use_main_model_for_realtime` line:
`kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration`
This OVERRIDES the common-block value (set first at ~196) — mirroring the existing
`use_main_model_for_realtime` override pattern (False in `_FIXED_KWARGS`, overridden to True in the
lite block). The common block sets it for both modes; the lite block overrides for lite only. Normal
mode is untouched (still 0.6).

**(b) daemon.py `_DRAIN_TIMEOUT_S` comment (line 136).** `_DRAIN_TIMEOUT_S: float = 5.0` (line 138).
The comment at line 136 says "post_speech_silence_duration (~1.5s trailing silence to trigger
finalization)" — STALE: the actual value is 0.6 (normal) / 0.5 (lite), not ~1.5s. (The ~1.5s was an
old default that has since become 0.6.) Update to "~0.6s normal / ~0.5s lite". Mode A (comment in a
file being edited, directly about the value being changed). NOTE: the contract cited "~line 94"; the
actual location is line 136 (line drift) — find by the `_DRAIN_TIMEOUT_S` symbol, not line number.

## 3. Test changes (tests/test_daemon.py)

**(c) Update `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` (185-213)** — the drift guard that
asserts lite changes ONLY specific keys. Current `differing = {"model", "realtime_model_type",
"use_main_model_for_realtime"}` (197). After the fix, lite ALSO differs in
`post_speech_silence_duration` (0.5 vs 0.6), so WITHOUT updating `differing` the test FAILS (the
"remaining dicts byte-identical" assertion would see the 0.5/0.6 mismatch). Required updates:
- Add `"post_speech_silence_duration"` to the `differing` set.
- Add `assert lite["post_speech_silence_duration"] == 0.5` and `assert normal["post_speech_silence_duration"] == 0.6`.
- Update the "3 differing keys" comment → "4 differing keys"; update the docstring.

**(d) Add `test_cfg_to_kwargs_lite_uses_shorter_silence_duration`** (new). Asserts: default → lite
kw `== 0.5`, normal kw `== 0.6`; override `cfg.asr.lite_post_speech_silence_duration = 0.3` → lite kw
`== 0.3`; normal still `== 0.6`. Uses the existing `cfg` fixture (function-scoped → safe to mutate)
+ `_cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)` (the sibling pattern at test:80).

## 4. Regression scan — NO other test breaks (verified)

`grep post_speech_silence_duration tests/test_daemon.py` → 4 sites:
- line 119: the kwargs-KEY-set assertion (`post_speech_silence_duration` in the expected key set). The
  fix OVERRIDES the value, not the key → the key set is unchanged → unaffected. ✓
- line 263/271: `test_cfg_to_kwargs_passes_through_config_values` — NORMAL mode (`cfg_to_kwargs(custom)`,
  no `lite=True`), asserts a custom 0.9 flows through. Normal is untouched → unaffected. ✓
- line 2583: `test_construct_force_cpu_keeps_non_device_kwargs` — `force_cpu=True` (NOT lite), asserts
  default 0.6. Lite-only change → unaffected. ✓
- line 197: the target test (updated in (c)).
The 3 `cfg_to_kwargs(..., lite=True)` call sites (146/176/195): 146 (`_uses_one_model`) + 176
(`_cpu_fallback_uses_tiny_en`) assert MODEL picks, NOT post_speech_silence_duration → unaffected. Only
195 (the drift guard) needs the update. **No other test asserts lite's post_speech_silence_duration.**

## 5. Scope + parallel context

- **Files edited**: `voice_typing/daemon.py` (1 line + 1 comment) + `tests/test_daemon.py` (update 1
  test + add 1 test). NO config.py/config.toml (P1.M1.T1.S1 owns the field), NO test_config.py.
- **P1.M1.T2.S1 (parallel, Implementing)**: config unit tests in `tests/test_config.py` for the field
  (default/round-trip/wrong-type/type). NO file overlap (it's test_config.py; this is daemon.py +
  test_daemon.py). The field's existence + default 0.5 + validation are its dependency (landed by
  P1.M1.T1.S1, which T2.S1 only tests). Clean boundary.
- **DOCS**: Mode A — the `_DRAIN_TIMEOUT_S` comment update. The user-facing config field doc is the
  config.toml comment (P1.M1.T1.S1). README/ACCEPTANCE = P1.M3 (separate).
- pytest>=9.1.1 (NO ruff/mypy). Full paths in bash (`.venv/bin/python`, zsh aliases: python3→uv run).
  Validate: `.venv/bin/python -m pytest tests/test_daemon.py -k 'lite' -v`.
