# Research: force_cpu capability — design decision, edit sites, test plan (VERIFIED)

**Status:** VERIFIED against the live `voice_typing/daemon.py` + `voice_typing/cuda_check.py` +
`tests/test_daemon.py` on 2026-07-08. This note is the load-bearing source for `P1M1T3S1/PRP.md`.
**Task:** bugfix Issue 3 / P1.M1.T3.S1 — "Add force_cpu capability to the device resolution and
recorder build path." This is the *capability* subtask; P1.M1.T3.S2 (main() retry) is the consumer.

---

## 1. The device-resolution call chain (the INPUT the contract names) — verified

The chain that builds an `AudioToTextRecorder` (exact current line numbers, daemon.py):

```
VoiceTypingDaemon.__init__ (@374)   # self._recorder = recorder or build_recorder(cfg, feedback, latency)
        │
        ▼
build_recorder(cfg, feedback, latency=None)  (@243)   # lazy-imports AudioToTextRecorder
        │  return _construct(cfg, feedback, AudioToTextRecorder, latency)
        ▼
_construct(cfg, feedback, recorder_cls, latency=None)  (@224)
        │  kwargs = cfg_to_kwargs(cfg)
        │  kwargs.update(_build_callbacks(feedback, latency))
        │  filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
        │  return recorder_cls(**filtered)
        ▼
cfg_to_kwargs(cfg)  (@134)
        │  resolved = _resolve_device_config(cfg)        # ← THE device decision
        │  kwargs = {model: resolved["final_model"],
        │            realtime_model_type: resolved["realtime_model"],
        │            language, device: resolved["device"], compute_type: resolved["compute_type"],
        │            realtime_processing_pause, post_speech_silence_duration}
        │  kwargs.update(_FIXED_KWARGS)
        │  return kwargs
        ▼
_resolve_device_config(cfg)  (@117)   # builds cfg defaults, calls cuda_check.resolve_device_and_models(defaults)
        │  defaults = {device: cfg.asr.device,
        │              compute_type: "float16" if cuda else "int8",   # DERIVED (no config field)
        │              final_model: cfg.asr.final_model,
        │              realtime_model: cfg.asr.realtime_model}
        │  return cuda_check.resolve_device_and_models(defaults)
        ▼
cuda_check.resolve_device_and_models(defaults)  (cuda_check.py)
        │  return dict(defaults) if is_cuda_available() else dict(CPU_FALLBACK)
```

`cuda_check.CPU_FALLBACK` (cuda_check.py, verified): `{"device":"cpu","compute_type":"int8",
"final_model":"small.en","realtime_model":"tiny.en"}` — the exact PRD §4.4 degraded quad.

**Key shape fact:** the "resolved dict" (keys `device`/`compute_type`/`final_model`/`realtime_model`)
is produced by `_resolve_device_config` and consumed by `cfg_to_kwargs`, which maps
`final_model → model=` and `realtime_model → realtime_model_type=` (the RealtimeSTT kwarg names).
`_construct` and `build_recorder` never touch the resolved dict directly today — only `cfg_to_kwargs` does.

---

## 2. The design decision (locked — and WHY it beats the alternatives)

**CONTRACT constraint (authoritative, from item_description):**
> "Add a `force_cpu: bool = False` parameter to `build_recorder()` and `_construct()`. When
> `force_cpu=True`, skip the normal `_resolve_device_config`/cuda_check path and instead build the
> device kwargs directly from `cuda_check.CPU_FALLBACK`. This means: in `_construct`, if
> `force_cpu`, replace the resolved dict with `dict(cuda_check.CPU_FALLBACK)` before building kwargs.
> ... Do NOT modify `cuda_check.py` or `_resolve_device_config` — the force_cpu override happens in
> `_construct`/`build_recorder` only."

**Chosen design** (satisfies EVERY clause):
- `cfg_to_kwargs(cfg, *, resolved=None)` — new keyword-only `resolved` param. When given, use it
  INSTEAD of calling `_resolve_device_config(cfg)` (so the cuda_check probe is genuinely skipped).
  Default `None` → the existing path (`_resolve_device_config(cfg)`) is byte-identical.
- `_construct(cfg, feedback, recorder_cls, latency=None, force_cpu=False)` — NEW `force_cpu` param
  (last, keyword-defaulted, preserves positional compat). When True it computes
  `resolved = dict(cuda_check.CPU_FALLBACK)` and passes it down:
  `kwargs = cfg_to_kwargs(cfg, resolved=resolved)`. **The resolved-dict replacement literally happens
  IN `_construct`, BEFORE kwargs are built** — matching "in _construct ... replace the resolved dict
  ... before building kwargs" word for word.
- `build_recorder(cfg, feedback, latency=None, force_cpu=False)` — NEW `force_cpu` param; threads it
  to `_construct(..., force_cpu=force_cpu)`.

**Why this design (vs the two alternatives considered):**

| alternative | why rejected |
|---|---|
| **B. Override kwargs post-hoc inside `_construct`** (call `cfg_to_kwargs(cfg)`, then mutate the 4 device keys) | VIOLATES "skip the normal `_resolve_device_config`/cuda_check path": `cfg_to_kwargs` still calls `_resolve_device_config` → `cuda_check.resolve_device_and_models` → imports ctranslate2 + probes the driver. On a CPU-fallback retry we specifically want to AVOID re-touching a GPU whose construction just failed. Also re-derives `final_model→model` mapping in two places. |
| **C. Thread `force_cpu` into `_resolve_device_config` too** | EXPLICITLY FORBIDDEN by the contract ("Do NOT modify ... `_resolve_device_config`"). (The `issue_analysis.md` mentioned this as one option; the task CONTRACT overrides it.) |
| **D. Duplicate kwargs-building in `_construct` when force_cpu** | Re-implements `cfg_to_kwargs`'s 8-key + `_FIXED_KWARGS` logic → drift risk, two sources of truth for the non-device kwargs (language/timing/silero/no_log_file). |

The chosen design is the ONLY one that (a) genuinely skips cuda_check, (b) keeps `force_cpu` scoped to
exactly `_construct`/`build_recorder` (cfg_to_kwargs gets `resolved`, not `force_cpu` — the *decision*
lives in `_construct`), (c) doesn't duplicate the kwargs map, and (d) is 100% backward-compatible
(default `force_cpu=False` / `resolved=None` = current behavior).

**Scope discipline (the contract's negative constraints):**
- Do NOT modify `cuda_check.py` (CPU_FALLBACK/resolve_device_and_models stay as-is).
- Do NOT modify `_resolve_device_config` (cfg still drives it on the normal path).
- Do NOT add `force_cpu` to `VoiceTypingDaemon.__init__` — the consumer (P1.M1.T3.S2 main() retry)
  builds the recorder via `build_recorder(cfg, feedback, latency, force_cpu=True)` and injects it with
  the EXISTING `recorder=` kwarg. No `__init__` change is needed or wanted (keeps the daemon's normal
  startup path untouched).

---

## 3. The non-device kwargs MUST still flow from cfg (the subtle invariant)

When `force_cpu=True`, ONLY the 4 device-related kwargs come from `CPU_FALLBACK`. The rest of the
recorder kwargs are still built from `cfg` exactly as today:

| kwarg | source when force_cpu=True | value (default cfg) |
|---|---|---|
| `model` | CPU_FALLBACK["final_model"] | `"small.en"` |
| `realtime_model_type` | CPU_FALLBACK["realtime_model"] | `"tiny.en"` |
| `device` | CPU_FALLBACK["device"] | `"cpu"` |
| `compute_type` | CPU_FALLBACK["compute_type"] | `"int8"` |
| `language` | cfg.asr.language | `"en"` |
| `realtime_processing_pause` | cfg.asr.realtime_processing_pause | `0.15` |
| `post_speech_silence_duration` | cfg.asr.post_speech_silence_duration | `0.6` |
| all `_FIXED_KWARGS` (no_log_file, silero_backend, spinner, use_microphone, …) | `_FIXED_KWARGS` | unchanged |

This is why `cfg_to_kwargs` stays the single kwargs-builder (it owns the language/timing/_FIXED_KWARGS
assembly) and is just handed a different `resolved` dict. A test MUST assert the non-device kwargs are
unchanged on the force_cpu path (guards against a future "helpful" refactor that drops them).

Default cfg values (verified, for test assertions): `asr.device='cuda'`, `asr.final_model='distil-large-v3'`,
`asr.realtime_model='small.en'`, `asr.language='en'`, `asr.realtime_processing_pause=0.15`,
`asr.post_speech_silence_duration=0.6`.

---

## 4. Test plan (follows the existing tests/test_daemon.py idioms) — verified hermetic

The existing suite NEVER imports RealtimeSTT / loads models / touches CUDA:
- `_cuda_resolve(monkeypatch, mapping)` monkeypatches `daemon.cuda_check.resolve_device_and_models`.
- `_FakeRecorder(**kwargs)` (VAR_KEYWORD) captures kwargs; `_StrictFakeRecorder(model, language, device)`
  exercises the drop path.
- `_construct(cfg, fb, _FakeRecorder)` is the testable seam (no heavy build_recorder call).
- `cfg_to_kwargs(cfg)` is tested directly.
- `build_recorder` is only smoke-checked (callable + documented) — calling it is heavy (P1.M7.T2.S1's job).

**New tests (ADDITIVE — a new banner section at the end; no existing test changed):**
1. `test_construct_force_cpu_uses_cpu_fallback` — `_construct(cfg, fb, _FakeRecorder, force_cpu=True)` →
   `rec.kwargs` has device=cpu, compute_type=int8, model=small.en, realtime_model_type=tiny.en.
2. `test_construct_force_cpu_skips_resolve` — monkeypatch `daemon._resolve_device_config` to raise;
   `force_cpu=True` does NOT raise (proves the skip — the resolve path is never entered), while
   `force_cpu=False` (default) DOES raise (proves the default still resolves). The cleanest skip proof.
3. `test_construct_force_cpu_overrides_cuda_path` — `_cuda_resolve(monkeypatch, CUDA_DEFAULTS)` (forcing
   cuda) BUT `force_cpu=True` still yields CPU kwargs → force_cpu wins over cuda_check unconditionally.
4. `test_construct_force_cpu_keeps_non_device_kwargs` — with `force_cpu=True`, `language`,
   `realtime_processing_pause`, `post_speech_silence_duration`, and ALL `_FIXED_KWARGS` (notably
   `no_log_file=True`, `silero_backend="auto"`) are still present + correct.
5. `test_construct_force_cpu_false_is_default_behavior` — `_construct(force_cpu=False)` (explicit) and
   `_construct()` (omitted) both behave exactly as today (cuda path when cuda resolves). Regression guard.
6. `test_cfg_to_kwargs_accepts_resolved_override` — `cfg_to_kwargs(cfg, resolved={device:cpu,...})` uses
   the injected dict WITHOUT calling `_resolve_device_config` (monkeypatch to raise; no raise = skip).
7. `test_build_recorder_force_cpu_in_signature` — `inspect.signature(build_recorder)` has `force_cpu`
   default `False`; `_construct` likewise. (Smoke; no heavy call — mirrors `test_build_recorder_is_callable_and_documented`.)

All gates are pure/unit: NO real CUDA, NO model load, NO real RealtimeSTT (the `_FakeRecorder` seam).

---

## 5. Validation tooling — what this project actually uses (verified)

`pyproject.toml` has NO `[tool.ruff]` / `[tool.mypy]` — only `[dependency-groups] dev = ["pytest>=9.1.1"]`.
So the Validation Loop is **pytest** (+ a `py_compile`/import sanity check), NOT ruff/mypy (the PRP
template's ruff/mypy lines are N/A here — do not invent them). The fast suite command:
`.venv/bin/python -m pytest tests/test_daemon.py -v` (full suite: `pytest tests/`). The repo is a
flat-layout uv/hatchling project; full paths required (zsh aliases shadow python3/pip).

---

## 6. Parallel-task awareness (no conflict)

- **P1.M1.T2.S3** (rate-limit filter, landing in parallel): edits `_setup_logging` + adds
  `MicRetryRateLimitFilter`/helpers near line ~980+. T3.S1 edits `cfg_to_kwargs`(@134)/`_construct`(@224)/
  `build_recorder`(@243) — **disjoint regions** of daemon.py. No line-level conflict.
- **P1.M1.T3.S2** (the consumer): will wrap `VoiceTypingDaemon(...)` construction in main() in a
  try/except, retry with `build_recorder(cfg, fb, latency, force_cpu=True)` + `recorder=` injection.
  T3.S1 provides the capability; T3.S2 uses it. T3.S1 does NOT touch main() or __init__.
