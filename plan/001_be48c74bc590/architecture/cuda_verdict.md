# CUDA verdict — voice-typing machine state

**Recorded:** 2026-07-06  •  **Host:** ghost  •  **GPU:** NVIDIA GeForce RTX 3080 Ti
**Run as:** `LD_LIBRARY_PATH=<launch_daemon.sh value> .venv/bin/python -m voice_typing.cuda_check`
(LD_LIBRARY_PATH replicated from voice_typing/launch_daemon.sh — P1.M1.T2.S1.)

## Raw smoke-check output

```
ctranslate2_version=<not installed>
cuda_device_count=0
torch_cuda_available=True
VERDICT=cpu-fallback-required
# ctranslate2 import failed: ModuleNotFoundError("No module named 'ctranslate2'")
# resolved: device=cpu compute_type=int8 final_model=small.en realtime_model=tiny.en
exit=1
```

## VERDICT

**cpu-fallback-required**  (PROVISIONAL — see below)

Resolved daemon config: device=cpu  compute_type=int8  final_model=small.en  realtime_model=tiny.en

## Meaning for the daemon (P1.M4.T1.S1)

- The recorder wiring calls `resolve_device_and_models()` once at startup and feeds the
  result into `AudioToTextRecorder(model=final_model, realtime_model_type=realtime_model,
  device=device, compute_type=compute_type)`.
- cpu-fallback-required: degraded CPU mode; daemon MUST log it and surface
  device="cpu" in status (PRD §4.4). The current reason is that `ctranslate2` is not yet
  installed — see the PROVISIONAL note below.

## PROVISIONAL — ctranslate2 not installed (S2 re-plan pending)

This verdict is **provisional**. At T2.S2 implementation time, `import ctranslate2`
raises `ModuleNotFoundError` because S2 (P1.M1.T1.S2) has not yet completed its re-plan to
declare the `faster-whisper` RealtimeSTT extra (bare `realtimestt` does not pull
`faster-whisper`/`ctranslate2` — they are optional extras `RealtimeSTT[faster-whisper]`).

- `torch.cuda.is_available() = True` here — the RTX 3080 Ti **is** visible to torch, a
  positive indicator that the CUDA path will likely be usable once ctranslate2 lands.
- `is_cuda_available()` correctly returned `False` (it gates on ctranslate2, the whisper
  inference engine, NOT torch — the script behaved exactly as designed).
- **RE-RUN** this smoke check after S2's successful re-plan (realtimestt →
  realtimestt[faster-whisper] or +faster-whisper) to capture the definitive verdict:
  ```bash
  cd /home/dustin/projects/voice-typing
  # replicate launch_daemon.sh's LD_LIBRARY_PATH export, then:
  .venv/bin/python -m voice_typing.cuda_check
  ```
  On this host (RTX 3080 Ti, driver 610.x, cu12 wheels via back-compat) the expected
  definitive verdict is `cuda-ok`.

## Notes / caveats

- "cuda-ok" means ctranslate2 SEES the GPU (get_cuda_device_count is a driver query; it
  does NOT load cuDNN). cuDNN load failures surface later at WhisperModel construction;
  the launch_daemon.sh LD_LIBRARY_PATH wrapper is what makes cuDNN findable.
- torch.cuda.is_available() is informational only (Silero VAD); it does not gate the verdict.
- In this run the nvidia.*.lib wheels were not importable either (S2 pending), so the
  smoke check ran WITHOUT an LD_LIBRARY_PATH override. This does not affect the verdict
  (ctranslate2 is absent regardless); the wrapper's value matters only once ctranslate2
  is present and the daemon constructs a WhisperModel.
