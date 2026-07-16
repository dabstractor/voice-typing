# Research Note: kwargs×mode×force_cpu unit tests + factory reconciliation (P1.M1.T1.S2)

**Status:** EMPIRICALLY RE-VERIFIED against the live repo on July 16 2026 (per the contract's §1 "RE-VERIFY first" mandate — the working tree is a moving target).
**Purpose:** Pin exactly which of the contract's three deliverables are ALREADY DONE vs. still needed, with the exact patterns + line numbers for the new tests.

---

## §1. CRITICAL: the contract's premise is PARTLY STALE — re-verification results

The contract (§1) said "as of analysis time, `pytest ... --ignore=tests/test_feed_audio.py` had 3 remaining failures" in factory closures. **LIVE RE-RUN today: `pytest tests/test_daemon.py tests/test_config.py -q` → 203 passed, 0 failures.** A concurrent process already reconciled the factories. Concretely:

| Contract deliverable | Status | Evidence |
|---|---|---|
| **(§2a) Reconcile broken factory closures** (`test_load_recorder_single_flight_one_build_under_concurrency` @L2817, `test_recorder_never_half_torn_down_during_race` @L2946, `test_concurrent_start_calls_build_recorder_once` @L3100) | **DONE** — factories use `**kw` which swallows the `mode=` kwarg | `def factory(cfg, feedback, latency, on_final, on_partial, on_speech, **kw):` @L2831 + L3116; `_fake_host_factory(mode=None)` inner `_factory(..., **kw)` @L532-538; `_FakeHost.__init__(..., mode="normal")` @L472. Suite 203/0. |
| **S1 (CPU-lite fix)** | **APPLIED** | `daemon.py:190` `lite_model = "tiny.en" if resolved["device"] == "cpu" else cfg.asr.lite_model"` (docstring @178). `recorder_host.py` likewise. |
| **(§2b) CUDA-lite kwargs test** (`model==realtime==small.en`, `use_main_model_for_realtime=True`, lite=False→distil-large-v3) | **EXISTS** | `test_cfg_to_kwargs_lite_mode_uses_one_model` @L138-153. |
| **(§2b) CPU-lite kwargs test** (`lite=True + CPU_FALLBACK → tiny.en`) | **MISSING → WRITE** | No test passes `resolved=dict(CPU_FALLBACK), lite=True`. This is the core S1-pinning regression. |
| **(§2b) "all other kwargs equal normal" drift guard** | **MISSING → WRITE** | The existing lite test checks 5 fields but NOT that the full kwargs dict (minus the 3 lite-touched keys) is byte-identical to normal. |
| **(§2c) Config `lite_model` tests** (default/TOML/non-string) | **MISSING → WRITE** | `grep lite test_config.py` → ZERO matches. config.py HAS the field (L54) + validation (L93) but no test pins it. |

→ **The actual NEW work for S2 is exactly 4 things**: 2 new daemon kwargs tests + 1 config-defaults assertion + 2 new config tests. The factory reconciliation (§2a) is VERIFIED DONE (implementer re-confirms, does NOT redo).

## §2. cfg_to_kwargs contract (the function the new kwargs tests drive)

`voice_typing/daemon.py:160` — `cfg_to_kwargs(cfg, *, resolved: dict | None = None, lite: bool = False) -> dict`:
- **`resolved=` is a real param**: when passed, the cuda_check probe is SKIPPED entirely → `cfg_to_kwargs(cfg, resolved=dict(CPU_FALLBACK), lite=True)` is deterministic WITHOUT CUDA/mocks (the clean way to test CPU-lite).
- **`resolved=None`** → calls `_resolve_device_config(cfg)` → `cuda_check.resolve_device_and_models`; tests force the path via `_cuda_resolve(monkeypatch, CUDA_DEFAULTS|CPU_FALLBACK)`.
- **Lite logic (S1-applied):**
  - First `if lite:` (L184-191): `lite_model = "tiny.en" if resolved["device"]=="cpu" else cfg.asr.lite_model`; `resolved["final_model"]=resolved["realtime_model"]=lite_model`.
  - kwargs: `model, realtime_model_type, language, device, compute_type, realtime_processing_pause, post_speech_silence_duration` then `kwargs.update(_FIXED_KWARGS)`.
  - Second `if lite:` (L~207): `kwargs["use_main_model_for_realtime"] = True`.
- **→ lite mode differs from normal in EXACTLY 3 keys:** `model`, `realtime_model_type`, `use_main_model_for_realtime`. Everything else is identical. (The "all-other-kwargs-equal" test pins this.)

`cuda_check.CPU_FALLBACK = {device:cpu, compute_type:int8, final_model:small.en, realtime_model:tiny.en}` (cuda_check.py:53). `CUDA_DEFAULTS = {device:cuda, compute_type:float16, final_model:distil-large-v3, realtime_model:small.en}`.

## §3. test_daemon.py patterns to mirror (the kwargs-test region L88-170)

- **`_cuda_resolve(monkeypatch, mapping)`** @L88: forces `cuda_check.resolve_device_and_models` to return `dict(mapping)` (CPU) or `dict(defaults)` (CUDA). `mapping is daemon.cuda_check.CPU_FALLBACK` triggers the CPU branch.
- **`cfg` fixture** @L102: `VoiceTypingConfig()` (defaults: `asr.lite_model == "small.en"`, `final_model == "distil-large-v3"`, `realtime_model == "small.en"`).
- **`test_cfg_to_kwargs_lite_mode_uses_one_model`** @L138 — the CUDA-lite test to NOT duplicate; it asserts model/realtime/use_main/device/compute for lite=True (CUDA) + the lite=False normal contrast. S2 ADDS the CPU-lite + all-other-kwargs tests alongside it.
- **`test_cfg_to_kwargs_cpu_fallback`** @L162 — NORMAL CPU (not lite): model=small.en, realtime=tiny.en. The pattern for asserting a CPU-resolved kwargs dict.

## §4. config.py + test_config.py patterns (for the lite_model tests)

- **config.py L54**: `lite_model: str = "small.en"` (PRD §4.2ter). **L93 `__post_init__`**: `lite_model` is in the string-validation list `("final_model","realtime_model","lite_model","language","device")` → a non-string raises `TypeError(f"[asr] lite_model expects str, got ...")` (the error message CONTAINS the field name `lite_model`).
- **test_config.py `test_defaults_match_prd_4_5`** @L34 — THE canonical defaults pin; asserts `final_model/realtime_model/language/device/...` but **NOT** `lite_model` (the gap to close). Idiomatic home for a one-line `assert cfg.asr.lite_model == "small.en"`.
- **`test_int_for_string_field_raises`** @L~150 — EXACT pattern for non-string rejection: `with pytest.raises(TypeError, match="device"): from_toml({"asr":{"device":123}})`. Mirror it for lite_model: `match="lite_model"`.
- **`test_from_toml_partial_table_keeps_other_defaults`** @L~76 — TOML override pattern. Mirror for lite_model round-trip.
- **`test_log_config_default_and_override`** @end — a round-trip-through-TOML pattern (`from_toml({...})` then assert). Mirror.

## §5. The 3 named concurrent tests (§2a) — VERIFIED RECONCILED

All three exist and pass. Their factory closures accept `**kw`:
- `test_load_recorder_single_flight_one_build_under_concurrency` @L2817 → local `factory(..., **kw)` @L2831.
- `test_concurrent_start_calls_build_recorder_once` @L3100 → local `factory(..., **kw)` @L3116.
- `test_recorder_never_half_torn_down_during_race` @L2946 → uses `_fake_host_factory(mode=...)` (inner `_factory(..., **kw)` @L538) or equivalent.
- `_FakeHost.__init__(..., mode="normal")` @L472 accepts `mode=`.

→ The `mode=` kwarg `_load_host` passes (`daemon.py:~737 factory(..., mode=mode)`) is absorbed by every factory via `**kw`. **No edit needed.** The implementer re-confirms via L2 (`pytest -k` on the 3 names → 3 passed).

## SUMMARY (what S2 actually does)

1. ✅ **(§2a) VERIFY, don't redo.** Factories are reconciled (suite 203/0). L2 confirms the 3 named tests pass.
2. ✅ S1 applied (CPU-lite fix in cfg_to_kwargs + recorder_host). Tests will reflect it.
3. ➕ **NEW test (daemon): `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en`** — `cfg_to_kwargs(cfg, resolved=dict(CPU_FALLBACK), lite=True)` → model==realtime==tiny.en, cpu/int8, use_main=True. (No monkeypatch — `resolved=` skips the probe.) PINS S1.
4. ➕ **NEW test (daemon): `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal`** — lite vs normal differ in EXACTLY {model, realtime_model_type, use_main_model_for_realtime}; all else byte-identical. Drift guard.
5. ➕ **Config (test_config.py):** extend `test_defaults_match_prd_4_5` (+1 line: `lite_model == "small.en"`) + ADD `test_lite_model_round_trips_through_toml` + `test_lite_model_wrong_type_raises` (mirror `test_int_for_string_field_raises`).
6. ✅ Run `pytest tests/test_daemon.py tests/test_config.py -q` → 0 failures (~206 passed).
7. ✅ Never import RealtimeSTT in the new tests (cfg_to_kwargs is pure; pass `resolved=` or mock `cuda_check`).
