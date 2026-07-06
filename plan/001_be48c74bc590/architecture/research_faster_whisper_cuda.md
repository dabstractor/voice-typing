# Research Brief: faster-whisper / CTranslate2 / CUDA cuDNN Handling

**Status:** VERIFIED (sourced from cloned faster-whisper@master README + utils.py, + pytorch.org/whl index listing, July 2026)
**Purpose:** Drive the install, model-prefetch, and CUDA-bootstrap task breakdown for the voice-typing daemon.

---

## 1. Model repo IDs (EXACT — for prefetch + runtime)

Sourced verbatim from `faster-whisper/utils.py` `_MODELS` dict (the authoritative resolution table).
`WhisperModel(size_or_path)` and `RealtimeSTT(model=...)` accept the SHORT name (left column) and resolve it to the HF repo_id (right column). For explicit prefetch via `huggingface_hub.snapshot_download`, use the repo_id (right column).

| PRD short name | HF repo_id (for prefetch) | Use |
|---|---|---|
| `distil-large-v3` | **`Systran/faster-distil-whisper-large-v3`** | FINAL model (default) |
| `large-v3-turbo` | **`mobiuslabsgmbh/faster-whisper-large-v3-turbo`** | FINAL substitute |
| `small.en` | **`Systran/faster-whisper-small.en`** | REALTIME/partials model |
| `tiny.en` | **`Systran/faster-whisper-tiny.en`** | CPU-fallback realtime model (degraded mode) |
| `small.en` (final, CPU-fallback) | `Systran/faster-whisper-small.en` | CPU-fallback final model |

**VERDICT:** PRD §4.4 model choices (`distil-large-v3` final, `small.en` realtime) are CONFIRMED valid short names. The PRD's prefetch repo hints (`Systran/faster-distil-whisper-large-v3`, `Systran/faster-whisper-small.en`) are CORRECT. Note `large-v3-turbo` lives under `mobiuslabsgmbh/` (NOT Systran) — the PRD's prefetch call must use the right owner.

> NOTE on `distil-whisper/distil-large-v3` vs `Systran/faster-distil-whisper-large-v3`: these are DIFFERENT repos. The faster-whisper-CTranslate2-converted weights that RealtimeSTT/faster-whisper consume are under **`Systran/faster-distil-whisper-large-v3`**. Do NOT prefetch the raw `distil-whisper/distil-large-v3` (PyTorch checkpoint) — that will not load in CTranslate2.

---

## 2. cuDNN / cuBLAS — the #1 install risk (CONFIRMED REQUIRED)

From faster-whisper README (§GPU, authoritative):

> "The latest versions of `ctranslate2` only support **CUDA 12 and cuDNN 9**."
> "On Linux these libraries can be installed with `pip`. Note that **`LD_LIBRARY_PATH` must be set before launching Python.**"

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*
export LD_LIBRARY_PATH=`python3 -c 'import os; import nvidia.cublas.lib; import nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))'`
```

**CRITICAL CORRECTION to PRD §4.4:** the PRD lists `nvidia-cudnn-cu12` UNPINNED. faster-whisper requires **cuDNN 9**. Pin to `nvidia-cudnn-cu12==9.*` (or a known-good 9.x). Unpinned may pull cuDNN 10/11 which can mismatch ctranslate2. → The install task MUST pin cuDNN to 9.x.

**LD_LIBRARY_PATH must be set BEFORE Python starts** (read at process exec, not mutable at runtime). Options ranked:
1. **A launcher wrapper script** (e.g. `voice_typing/launch_daemon.sh`) that computes the path from the venv's installed `nvidia.cublas.lib`/`nvidia.cudnn.lib` and re-execs python with LD_LIBRARY_PATH set. systemd `ExecStart=` points at this wrapper. Most robust + idempotent (recomputes after `uv sync`).
2. systemd `Environment=LD_LIBRARY_PATH=...` computed by `install.sh` and written into the unit file. Works but stale if venv moves.
3. `os.execv` re-exec trick inside daemon.py — fragile, race-prone, NOT preferred.

→ **Recommendation: launcher wrapper (option 1).** install.sh writes `systemd/voice-typing.service` ExecStart to the wrapper, OR generates it. PRD §4.9 already leaves a placeholder for this.

**Do NOT attempt to set LD_LIBRARY_PATH inside daemon.py after import** — it does not work for already-loaded symbols. The PRD's "os.execv re-exec" note should be treated as fallback only.

---

## 3. CUDA availability smoke checks (must-pass)

Two checks per PRD §5 step 4:

| Check | Command | Must-have? | Purpose |
|---|---|---|---|
| ctranslate2 CUDA | `.venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` | **MUST ≥ 1** | whisper inference (the whole point) |
| torch CUDA | `.venv/bin/python -c "import torch; print(torch.cuda.is_available())"` | nice-to-have | only for Silero VAD |

**torch CUDA is NOT required for VAD to function** — Silero VAD runs fine on CPU (it's tiny, ~1-2ms/frame). So if torch arrives CPU-only and CUDA torch is hard to install, the daemon still works (VAD on CPU, whisper on GPU via ctranslate2). The PRD already notes this ("torch.cuda availability is nice-to-have; ctranslate2 CUDA is the must-have"). → Install task should: ensure ctranslate2 CUDA works (must), attempt CUDA torch (best-effort, do not block on it).

**Degraded-mode fallback** (PRD §4.4): if ctranslate2 CUDA init fails, set `device="cpu", compute_type="int8"`, realtime model `tiny.en`, final model `small.en`. Daemon MUST log this clearly and report `"device": "cpu"` in status.

---

## 4. Torch CUDA wheel index (if CUDA torch wanted)

download.pytorch.org/whl currently exposes (verified from the index listing): `cu124`, `cu126`, `cu128`, `cu129`, `cu130`, `cu132`, `cpu`.

- Recent torch **PyPI default wheel is cu130** (CUDA 13.0) for Linux x86_64. ctranslate2 wants CUDA 12 — but torch CUDA major version does NOT have to match ctranslate2's CUDA (separate libs, only torch needs its own bundled CUDA). However, to minimize conflicts, pin torch to a **cu12x** index.
- **Recommended index:** `https://download.pytorch.org/whl/cu126` (CUDA 12.6, widely available, driver 610.x is forward-compatible). cu128 also viable.
- Command (if CPU-only torch arrives): `uv add torch --index https://download.pytorch.org/whl/cu126`

PRD §5 suggested cu126 — CONFIRMED valid/current.

---

## 5. Model prefetch pattern

```python
from huggingface_hub import snapshot_download
for repo in ["Systran/faster-distil-whisper-large-v3",
             "Systran/faster-whisper-small.en"]:
    snapshot_download(repo_id=repo)   # → ~/.cache/huggingface/hub
```

- `install.sh` runs this (or constructs `AudioToTextRecorder` once with `use_microphone=False`) so first real run is instant.
- Systran + mobiuslabsgmbh repos are **public, ungated** — no HF auth token needed.
- RealtimeSTT downloads Silero VAD model too (torch hub or onnx). With `silero_use_onnx=True` it avoids a runtime torch-hub download; install.sh should still pre-trigger it.

---

## 6. faster-whisper dependency pins

From faster-whisper `requirements.txt`:
- `ctranslate2>=4.0,<5`
- `huggingface_hub>=0.23`
- `tokenizers>=0.13,<1`
- `onnxruntime>=1.14,<2`  (used for Silero ONNX VAD)
- `av>=11`  (PyAV — bundles ffmpeg, so NO system ffmpeg needed for whisper decode; but espeak/sox still needed for test-asset generation)

RealtimeSTT pulls faster-whisper transitively, so these are handled by `uv add realtimestt`. We add `nvidia-cublas-cu12` + `nvidia-cudnn-cu12==9.*` explicitly for the CUDA libs.

---

## SUMMARY OF PRD CORRECTIONS/CONFIRMATIONS (for breakdown)

1. ✅ Model short names `distil-large-v3`, `small.en`, `large-v3-turbo` CONFIRMED valid.
2. ✅ Prefetch repo IDs: `Systran/faster-distil-whisper-large-v3`, `Systran/faster-whisper-small.en`. ⚠️ `large-v3-turbo` → `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (different owner).
3. ⚠️ **cuDNN must be pinned to 9.x**: `nvidia-cudnn-cu12==9.*` (PRD left unpinned).
4. ⚠️ **LD_LIBRARY_PATH must be set BEFORE Python launches** — use a launcher wrapper script (NOT os.execv, NOT in-process). systemd ExecStart → wrapper.
5. ✅ torch CUDA index `cu126` confirmed valid.
6. ✅ ctranslate2 CUDA is the must-have; torch CUDA is optional (VAD runs on CPU).
7. ✅ No system ffmpeg needed for whisper (PyAV bundles it); sox/espeak-ng still needed for test assets.
