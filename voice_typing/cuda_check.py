"""CUDA smoke check + degraded-mode decision for the voice-typing daemon.

Decides whether the daemon runs on GPU (device="cuda", compute_type="float16",
final_model="distil-large-v3", realtime_model="small.en") or falls back to CPU
(device="cpu", compute_type="int8", final_model="small.en",
realtime_model="tiny.en"), per PRD §4.4.

This is a REAL smoke check (no mocking). It is meant to run under
launch_daemon.sh's environment so LD_LIBRARY_PATH (the cuBLAS + cuDNN 9 lib
dirs) is already set. This module MUST NOT set LD_LIBRARY_PATH itself: the
dynamic linker reads it only at process exec (ld.so(8)), so setting it inside
the running process has no effect. launch_daemon.sh (P1.M1.T2.S1) is the single
sanctioned place to export it; to run this check manually, reproduce that
wrapper's LD_LIBRARY_PATH export in the shell first (see Validation L3).

THE DEGRADED-MODE KNOB  (PRD §4.4 — the user-facing surface):
  When ctranslate2.get_cuda_device_count() == 0 — or ctranslate2 cannot be
  imported, or its CUDA init raises for any reason — the daemon MUST run:
      device="cpu", compute_type="int8",
      final_model="small.en", realtime_model="tiny.en"
  and surface device="cpu" in its status (feedback.py state.json, written in
  P1.M3.T2.S1; the daemon status string is wired in P1.M4.T1.S1). The CUDA path
  is the CUDA_DEFAULTS below. Resolve the active config ONCE at daemon startup
  via resolve_device_and_models() and pass the result into the
  AudioToTextRecorder: P1.M4.T1.S1 maps  final_model -> model=  and
  realtime_model -> realtime_model_type=.

The MUST-HAVE check is ctranslate2 CUDA (the whisper inference engine).
torch.cuda.is_available() is a NICE-TO-HAVE (only Silero VAD uses torch, and it
runs fine on CPU); it is reported for diagnostics but does NOT gate the verdict.

LIMITATION: a "cuda-ok" verdict means ctranslate2 can SEE the GPU.
get_cuda_device_count() queries the CUDA driver only — it does NOT load cuDNN,
so a missing libcudnn_ops.so.9 will NOT change this verdict. cuDNN load failures
surface later, at WhisperModel construction in the daemon. The launch_daemon.sh
LD_LIBRARY_PATH wrapper is what makes cuDNN findable; if construction still
fails, the daemon (P1.M4.T1.S1) should re-resolve to CPU.
"""
from __future__ import annotations

import sys
from typing import Mapping

# PRD §4.4 — the config the daemon WANTS when CUDA works.
CUDA_DEFAULTS: dict[str, str] = {
    "device": "cuda",
    "compute_type": "float16",
    "final_model": "distil-large-v3",
    "realtime_model": "small.en",
}

# PRD §4.4 — the degraded config applied when ctranslate2 sees no CUDA device.
CPU_FALLBACK: dict[str, str] = {
    "device": "cpu",
    "compute_type": "int8",
    "final_model": "small.en",
    "realtime_model": "tiny.en",
}


def _cuda_device_count() -> tuple[int, str]:
    """Return (count, reason). count == 0 on ANY failure means: use CPU.

    Both the import and the call are wrapped so that a missing 'ctranslate2'
    package (faster-whisper is an optional RealtimeSTT extra), a missing CUDA
    driver, or a CUDA-runtime load failure all degrade cleanly to CPU fallback.
    Note: get_cuda_device_count() queries the driver only — it does NOT load
    cuDNN, so a missing libcudnn_ops will NOT make it return 0 here (that error
    surfaces later, at WhisperModel construction in the daemon).
    """
    try:
        import ctranslate2  # local import: isolate the optional/heavy dependency
    except Exception as exc:  # ImportError, OSError from a failed dlopen, ...
        return 0, f"ctranslate2 import failed: {exc!r}"
    try:
        count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:  # RuntimeError / low-level CUDA errors
        return 0, f"get_cuda_device_count() raised: {exc!r}"
    if count <= 0:
        return 0, "no CUDA-capable device/driver visible to ctranslate2"
    return count, f"{count} cuda device(s) visible to ctranslate2"


def _ctranslate2_version() -> str:
    """ctranslate2 version string, or '<not installed>' if it can't be imported."""
    try:
        import ctranslate2
        return getattr(ctranslate2, "__version__", "<unknown>")
    except Exception:
        return "<not installed>"


def _torch_cuda_available() -> bool:
    """Nice-to-have probe for Silero VAD diagnostics. False on any failure.

    Does NOT gate the verdict — Silero VAD runs fine on CPU.
    """
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def is_cuda_available() -> bool:
    """True iff ctranslate2 sees >= 1 CUDA device.

    This is the MUST-HAVE check (the whisper inference engine). It does NOT
    consider torch.cuda — see module docstring.
    """
    return _cuda_device_count()[0] >= 1


def resolve_device_and_models(
    defaults: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve {device, compute_type, final_model, realtime_model} for the daemon.

    If ctranslate2 CUDA is available, return a copy of `defaults` (or
    CUDA_DEFAULTS when `defaults` is None). Otherwise apply the PRD §4.4 CPU
    fallback (CPU_FALLBACK) REGARDLESS of `defaults`. Always returns a fresh
    dict the caller may mutate freely.

    Consumed once at daemon startup by the recorder wiring (P1.M4.T1.S1),
    which maps final_model -> model= and realtime_model -> realtime_model_type=.
    """
    if defaults is None:
        defaults = CUDA_DEFAULTS
    if is_cuda_available():
        return dict(defaults)
    return dict(CPU_FALLBACK)


def _verdict() -> str:
    return "cuda-ok" if is_cuda_available() else "cpu-fallback-required"


def _main() -> int:
    """CLI smoke check. Prints diagnostics + a one-line VERDICT.

    Output lines (greppable):
      ctranslate2_version=<ver|<not installed>>
      cuda_device_count=<int>
      torch_cuda_available=<True|False>
      VERDICT=<cuda-ok|cpu-fallback-required>
      # <reason>
      # resolved: device=.. compute_type=.. final_model=.. realtime_model=..

    Exit code mirrors the verdict: 0 = cuda-ok, 1 = cpu-fallback-required.
    NOTE: cpu-fallback-required is a VALID degraded mode, not an error —
    callers under `set -e` should capture the VERDICT= line or `|| true`.
    """
    count, reason = _cuda_device_count()
    print(f"ctranslate2_version={_ctranslate2_version()}")
    print(f"cuda_device_count={count}")
    print(f"torch_cuda_available={_torch_cuda_available()}")
    print(f"VERDICT={_verdict()}")
    print(f"# {reason}")
    cfg = resolve_device_and_models()
    print(
        f"# resolved: device={cfg['device']} compute_type={cfg['compute_type']} "
        f"final_model={cfg['final_model']} realtime_model={cfg['realtime_model']}"
    )
    return 0 if is_cuda_available() else 1


if __name__ == "__main__":
    sys.exit(_main())
