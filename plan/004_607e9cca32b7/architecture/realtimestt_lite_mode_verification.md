# RealtimeSTT Lite-Mode Verification — the one-model fact

> **Load-bearing fact:** Constructing `AudioToTextRecorder` with
> `use_main_model_for_realtime=True` loads **exactly ONE model** — the separate realtime
> transcription engine is NEVER initialized. This is what makes lite mode load only `lite_model`
> (`small.en`) for both partials and finals. **CONFIRMED against the installed version, not assumed.**

## Verification (read-only, performed on this machine)

Installed: RealtimeSTT v1.0.2 (`.venv/lib/python3.12/site-packages/RealtimeSTT/`).

`core/initialization.py`, function `_initialize_realtime_transcription_model(recorder)` — the guard at
lines ~453-455:

```python
def _initialize_realtime_transcription_model(recorder):
    """
    Initializes the realtime transcription backend.
    """
    if (
        recorder.enable_realtime_transcription
        and not recorder.use_main_model_for_realtime
        and not recorder._uses_external_realtime_transcription_executor
    ):
        try:
            logger.info(
                f"Initializing {recorder.realtime_transcription_engine} realtime "
                f"transcription model {recorder.realtime_model_type}, "
                ...
```

When `use_main_model_for_realtime=True`, the `and not recorder.use_main_model_for_realtime` clause is
**False**, so the whole `if` is False → the body (constructing the realtime engine) is **skipped
entirely**. The realtime engine is therefore never built; the single main model (passed as `model=`)
services both the partials stream and the final pass.

(The delta PRD cited line 447; the guard sits at ~453-455 in this exact checkout — identical logic.
The line number drift is cosmetic; the behavior is identical.)

## What this means for the recorder kwargs

| Mode | `model` | `realtime_model_type` | `use_main_model_for_realtime` | Models resident |
|---|---|---|---|---|
| normal | `distil-large-v3` | `small.en` | `False` | **2** (large final + small realtime) |
| lite | `lite_model` (`small.en`) | `lite_model` (`small.en`) | `True` | **1** (small only — large never constructed) |

The lite kwargs are built in `voice_typing/daemon.py::cfg_to_kwargs(cfg, *, resolved=None, lite=False)`:
when `lite=True`, set `model = realtime_model_type = cfg.asr.lite_model` and override
`use_main_model_for_realtime=True` (it's `False` in the `_FIXED_KWARGS` default). All OTHER kwargs
(device, compute_type, language, VAD timing, silero, `enable_realtime_transcription`) are IDENTICAL to
normal mode.

## CPU-fallback for lite (delta §3.2 — the BUG-A fix)

On the `force_cpu` path (`_construct` passes `resolved = dict(cuda_check.CPU_FALLBACK)`), lite must use
the **CPU lite substitute `tiny.en`** for BOTH model fields — mirroring how normal CPU-fallback maps
`small.en`→`tiny.en` (the realtime model) and `distil-large-v3`→`small.en` (the final model).
`cuda_check.CPU_FALLBACK` = `{device:cpu, compute_type:int8, final_model:small.en,
realtime_model:tiny.en}`.

**Current code is buggy:** `cfg_to_kwargs`'s lite branch unconditionally sets both model fields to
`cfg.asr.lite_model` ("small.en"), ignoring the device. Fix: when `resolved["device"] == "cpu"`, use
`"tiny.en"` instead.

## How T7 asserts the one-model invariant

T7 (the lite feed-audio integration test) must assert the large model never loads. The cleanest
CUDA-free proxy available to a unit test is to assert `use_main_model_for_realtime=True` reached the
recorder kwargs (via `cfg_to_kwargs(lite=True)`). The integration-grade assertion (T7a) compares a lite
`nvidia-smi` VRAM snapshot ≈ half of normal and/or greps the child log for the absence of a
`distil-large-v3` model-init line. If a future RealtimeSTT upgrade regresses the early-return, T7a
fails loudly — never silently load two models.
