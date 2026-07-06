# Research: CTranslate2 CUDA API verification (for `voice_typing/cuda_check.py`)

> Scope: Answer the 6 load-bearing API questions for a CUDA-availability smoke check that drives
> faster-whisper device/compute_type/model selection consumed by RealtimeSTT's `AudioToTextRecorder`.
>
> **Verification status:** Environment-specific facts (RealtimeSTT 1.0.2 internals, dependency graph,
> WhisperModel constructor signature) were **verified by reading installed source / `uv.lock`** on
> 2026-07-06 in this repo. CTranslate2 is **not installed** in this environment (see Gaps), so the
> CTranslate2-API specifics (Q1–Q4, Q6) come from the stable, long-standing public API and are marked
> **[docs, not live-fetched]**. Canonical doc URLs are cited from known locations; they were not
> re-fetched in this session because no web tool was available.

## Summary

`ctranslate2.get_cuda_device_count()` is the correct, lightweight, **module-level** probe: it returns
an `int` device count and **returns 0 when there is no CUDA-capable device/driver** — it does **not**
require cuDNN, so a missing `libcudnn_ops` does *not* make it raise or return 0 (that error surfaces
later at `WhisperModel` construction). Other CUDA-runtime load failures *can* raise, so **wrap it in
`try/except` and treat any exception as `count == 0 → CPU fallback`**. `cpu`+`int8` and `cuda`+`float16`
are the documented, known-good faster-whisper combinations.

**⚠ Material plan-affecting finding:** `ctranslate2` and `faster-whisper` are **NOT dependencies** in
this project's resolved `uv.lock`. RealtimeSTT 1.0.2 loads faster-whisper as an **optional extra**
(`RealtimeSTT[faster-whisper]`), lazily via `import_module("faster_whisper")`. So `import ctranslate2`
in `cuda_check.py` will raise `ImportError` today unless `faster-whisper` (which pins `ctranslate2`) is
added to `pyproject.toml`. See **Gaps / Risks**.

---

## Environment facts (verified locally — high confidence)

1. **RealtimeSTT 1.0.2 `AudioToTextRecorder.__init__` signature** (read from installed
   `RealtimeSTT/audio_recorder.py`) exposes exactly the knobs `cuda_check.py` must feed:
   - `transcription_engine: str = "faster_whisper"` (default)
   - `device: str = "cuda"` (default)
   - `compute_type: str = "default"`
   - `gpu_device_index: Union[int, List[int]] = 0`
   - `model` (main) and `realtime_model_type` (realtime model)
   These are passed straight through to the engine.

2. **`FasterWhisperEngine` consumes this exact API** (read from installed
   `RealtimeSTT/transcription_engines/faster_whisper_engine.py`):
   ```python
   model = faster_whisper.WhisperModel(
       model_size_or_path=self.config.model,
       device=self.config.device,                 # "cuda" | "cpu"
       compute_type=self.config.compute_type,     # "float16" | "int8" | "default" | ...
       device_index=self.config.gpu_device_index, # int or list, default 0
       download_root=self.config.download_root,
   )
   ```
   → `cuda_check.py`'s job is to decide `device`, `compute_type`, `gpu_device_index`, and the
   main/realtime model names; RealtimeSTT + faster-whisper do the rest.

3. **faster-whisper / ctranslate2 are optional extras** (verified in installed source):
   `_load_faster_whisper()` does `import_module("faster_whisper")` and, on `ModuleNotFoundError`,
   raises: *"Install it with `pip install "RealtimeSTT[faster-whisper]"`"*. Neither `faster-whisper`
   nor `ctranslate2` appears in `uv.lock`; `ctranslate2` is **not installed** in `.venv` (confirmed:
   `numpy` is present at `.venv/lib/python3.12/site-packages/`, `ctranslate2/__init__.py` is not).

4. **CUDA lib mix in the lock** (verified): project pins `nvidia-cublas-cu12`, `nvidia-cudnn-cu12==9.*`,
   but `torch==2.12.1` (a realtimestt dep) pulls the **cu13** variants (`nvidia-cudnn-cu13`,
   `nvidia-cublas`). A `ctranslate2` cu12 wheel would expect cu12 libs — potential runtime mismatch
   (see Risks).

---

## Findings — the 6 questions

### Q1. `ctranslate2.get_cuda_device_count()` — semantics & failure modes  [docs, not live-fetched]

- **It is a module-level function** in the `ctranslate2` package (not a class method): call it as
  `ctranslate2.get_cuda_device_count()`. Returns an `int`.
  [CTranslate2 Python API](https://opennmt.net/CTranslate2/python/ctranslate2.html)
- **(a) CUDA available & working → returns `>= 1`** (the number of visible devices).
- **(b) No GPU / no CUDA driver → returns `0`** (this is the normal "no CUDA" path; it does **not**
  raise in the standard pip-wheel, CUDA-capable build when the host simply lacks a GPU).
- **(c) cuDNN libs (`libcudnn_ops_*`) can't be loaded** — **important nuance:**
  `get_cuda_device_count()` queries the **CUDA driver/runtime only**; it does **not** load cuDNN.
  Therefore a *missing cuDNN* does **not** make it raise **and does not make it return 0** — it returns
  the true device count (≥1). The cuDNN error
  (`libcudnn_ops_infer.so.8: cannot open shared object file: No such file or directory`) surfaces
  **later**, when `WhisperModel(device="cuda", ...)` actually instantiates on the GPU.
  - Conversely, if the broader **CUDA runtime libs themselves** (`libcudart`, `libcublas`, the
    driver `libcuda.so`) fail to load, `get_cuda_device_count()` **can** raise a `RuntimeError` /
    low-level CUDA error.
- **Recommendation (the answer you need): YES — wrap in `try/except` and treat any exception as
  `count == 0 → CPU fallback`.** This is the standard faster-whisper/RealtimeSTT community pattern and
  is correct regardless of which failure mode occurs. Also: treat `count >= 1` as *not a guarantee* —
  `WhisperModel` can still fail later if cuDNN is missing, so log clearly and keep the fallback path
  callable from the recorder-construct site too.

### Q2. `ctranslate2.__version__`  [docs, not live-fetched]

- **Yes**, `ctranslate2.__version__` is the correct public string attribute. It is the documented way
  to read the version.
- There is **no** public `ctranslate2.version.__version__` accessor you should rely on (the package
  has an internal `version.py`, but `__version__` is re-exported at top level — use the top-level one).
- Robust alternative that never depends on internal layout:
  `importlib.metadata.version("ctranslate2")`.

### Q3. Does `import ctranslate2` trigger CUDA initialization?  [docs, not live-fetched]

- **No meaningful CUDA init at import time.** Importing `ctranslate2` loads the compiled extension
  and registers device support, but it does **lazy** CUDA context creation / cuDNN loading. A CUDA
  context is only created when you actually construct a model/translator with `device="cuda"`.
- So `import ctranslate2` normally succeeds even when cuDNN is absent; the cuDNN error appears at model
  construction, not at import.
- **Caveat:** in some wheel/env combinations the extension's `dlopen` can fail at import if a *core*
  shared lib is missing → that surfaces as `ImportError`/`OSError`. For `cuda_check.py`, the safest
  pattern is to do the `import ctranslate2` **inside** the same `try/except` that calls
  `get_cuda_device_count()`, so an import-time dlopen failure also degrades cleanly to CPU fallback.

### Q4. `torch.cuda.is_available()` for Silero VAD  [high confidence — stable PyTorch API]

- **Confirmed:** returns a plain `bool`; on a CPU-only torch build it returns `False` and **does not
  raise**.
- It is the right "nice-to-have" check for Silero VAD. Note: in this project Silero VAD is independent
  of the transcription device (RealtimeSTT creates it via `create_silero_vad_model`), and it runs fine
  on CPU regardless, so this check is informational, not load-bearing. `torch` *is* installed here
  (`torch==2.12.1`), so the check is usable today (unlike the ctranslate2 check).

### Q5. Known-good `device`/`compute_type` combinations for faster-whisper  [high confidence]

- **`device="cpu"`, `compute_type="int8"` — known-good CPU combo.** `int8` is faster-whisper's
  recommended CPU compute type (best speed/accuracy tradeoff on CPU).
- **`device="cuda"`, `compute_type="float16"` — known-good GPU combo.** `float16` is the recommended
  CUDA compute type.
- **`compute_type="default"`** auto-selects `float16` on cuda / `int8` on cpu — which is exactly why
  RealtimeSTT defaults `compute_type="default"`.
  [faster-whisper README](https://github.com/SYSTRAN/faster-whisper) (the README documents the
  `compute_type` choices and `device` values; `WhisperModel(device=..., compute_type=..., device_index=...)`
  matches the constructor consumed by `FasterWhisperEngine` above).

### Q6. Lightweight CUDA probe without initializing a full context?  [docs, not live-fetched]

- **`get_cuda_device_count()` itself is the lightweight probe.** It queries the driver for the device
  count **without** allocating GPU memory, creating a compute context, or loading a model (or cuDNN).
  There is no lighter/safer CTranslate2 API for this; the idiom is simply
  `ctranslate2.get_cuda_device_count() > 0`. CTranslate2 does not expose a separate boolean
  `is_cuda_available()`.
- (For comparison, `torch.cuda.is_available()` is the equivalent lightweight probe on the torch side
  and is independent of ctranslate2.)

---

## Recommended decision logic (`cuda_check.py`)

The function below resolves device + compute_type + main/realtime models per the task's pairing
(cuda → float16 + `distil-large-v3`/`small.en`; cpu → int8 + `small.en`/`tiny.en`), treats any
ctranslate2 failure (missing package, missing CUDA libs, raised exception) as CPU fallback, and keeps
`import ctranslate2` *inside* the probe so import-time failures also degrade gracefully.

```python
"""CUDA availability + device/compute_type/model resolution for the daemon."""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceConfig:
    device: str                 # "cuda" | "cpu"
    compute_type: str           # "float16" (cuda) | "int8" (cpu)
    main_model: str             # e.g. "distil-large-v3" (cuda) / "small.en" (cpu)
    realtime_model: str         # e.g. "small.en" (cuda) / "tiny.en" (cpu)
    gpu_device_index: int | list[int] = 0
    cuda_device_count: int = 0
    reason: str = ""


def _cuda_device_count() -> tuple[int, str]:
    """
    Return (count, reason). count==0 (or any failure) means: use CPU.

    Wrapping BOTH the import and the call means a missing 'ctranslate2' package
    (today: faster-whisper is an optional RealtimeSTT extra, see Gaps), a missing
    CUDA driver, OR a CUDA-runtime load failure all degrade to CPU fallback.
    """
    try:
        import ctranslate2  # local import: isolate optional/heavy dependency
    except Exception as exc:  # ImportError, OSError from dlopen, etc.
        return 0, f"ctranslate2 import failed: {exc!r}"
    try:
        # Lightweight driver query: does NOT load cuDNN or create a CUDA context.
        count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:  # RuntimeError / low-level CUDA errors
        return 0, f"get_cuda_device_count() raised: {exc!r}"
    if count <= 0:
        return 0, "no CUDA-capable device/driver visible to ctranslate2"
    return count, "cuda available"


def resolve_device_config() -> DeviceConfig:
    count, reason = _cuda_device_count()
    if count >= 1:
        log.info("CUDA available (%s) — using GPU.", reason)
        return DeviceConfig(
            device="cuda",
            compute_type="float16",
            main_model="distil-large-v3",
            realtime_model="small.en",
            gpu_device_index=0,
            cuda_device_count=count,
            reason=reason,
        )
    log.warning("Falling back to CPU (%s).", reason)
    return DeviceConfig(
        device="cpu",
        compute_type="int8",
        main_model="small.en",
        realtime_model="tiny.en",
        gpu_device_index=0,
        cuda_device_count=0,
        reason=reason,
    )


# Optional, independent nice-to-have for Silero VAD diagnostics. Returns bool, never raises.
def torch_cuda_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False
```

Consumption (matches `FasterWhisperEngine` + `AudioToTextRecorder`):
```python
cfg = resolve_device_config()
recorder = AudioToTextRecorder(
    model=cfg.main_model,
    realtime_model_type=cfg.realtime_model,
    transcription_engine="faster_whisper",
    device=cfg.device,
    compute_type=cfg.compute_type,
    gpu_device_index=cfg.gpu_device_index,
)
```

> Note: even when `resolve_device_config()` returns cuda, `WhisperModel(device="cuda", ...)`
> can still fail at construction if cuDNN is missing (Q1c). Consider catching that at the
> recorder-construction site and re-resolving to CPU.

---

## Sources

- **Kept (verified locally in this repo):**
  - `RealtimeSTT/audio_recorder.py` (installed) — `AudioToTextRecorder.__init__` defaults & kwargs
    (`device="cuda"`, `compute_type="default"`, `transcription_engine="faster_whisper"`,
    `gpu_device_index`, `model`, `realtime_model_type`).
  - `RealtimeSTT/transcription_engines/faster_whisper_engine.py` (installed) — exact
    `WhisperModel(model_size_or_path, device, compute_type, device_index=gpu_device_index,
    download_root)` call; lazy `import_module("faster_whisper")`; error string naming
    `RealtimeSTT[faster-whisper]` extra.
  - `RealtimeSTT/core/initialization.py` (installed) — `recorder.device/compute_type/gpu_device_index`
    plumbing.
  - `uv.lock` (resolved) — confirms `realtimestt==1.0.2` deps (no faster-whisper/ctranslate2);
    `torch==2.12.1`; cu12 vs cu13 lib mix; `.venv` synced (numpy present), ctranslate2 absent.
- **Cited from known canonical locations (not live-fetched this session):**
  - CTranslate2 Python API — `https://opennmt.net/CTranslate2/python/ctranslate2.html`
    (`get_cuda_device_count()`, `__version__`).
  - CTranslate2 repo — `https://github.com/OpenNMT/CTranslate2`.
  - faster-whisper README / `WhisperModel` — `https://github.com/SYSTRAN/faster-whisper`
    (`compute_type` guidance: int8 CPU / float16 GPU; `device`, `device_index` params).
- **Dropped:** generic Stack Overflow / blog hits on "ctranslate2 cuda check" — not authoritative;
  the verified package source + official docs supersede them.

## Gaps / Risks

1. **[BLOCKER for the plan as written] ctranslate2 / faster-whisper are not installed and not in
   `uv.lock`.** faster-whisper is an optional extra (`RealtimeSTT[faster-whisper]`). Without adding it,
   `import ctranslate2` and `import_module("faster_whisper")` both fail. Action: add
   `faster-whisper` (or `realtimestt[faster-whisper]`) to `pyproject.toml` `dependencies` and
   re-resolve; faster-whisper pins a compatible `ctranslate2` automatically.
2. **cuDNN/cuBLAS major-version mix.** Project pins cu12 libs; `torch` pulls cu13. A ctranslate2/faster-whisper
   cu12 build may fail to load cuDNN at `WhisperModel` construction even when `get_cuda_device_count()`
   returns ≥1 (Q1c). Verify by actually constructing the model on the target host; pin to one CUDA major.
3. **Could not live-verify the opennmt.net / faster-whisper doc URLs** (no web tool in this run). The
   API facts are stable and long-standing; re-confirm section anchors if a precise anchor is needed.
4. **`get_cuda_device_count()` exact exception types** on lib-load failure are version/wheel-dependent;
   the broad `except Exception` in the snippet is intentional and safe (it only ever forces CPU).

## Suggested next steps
- Add the faster-whisper extra as a project dependency, then write a unit test for `cuda_check.py`
  using a fake `ctranslate2` module (monkeypatch `get_cuda_device_count` to return 0 / raise /
  return 2) to lock in the three branches deterministically without a GPU.
