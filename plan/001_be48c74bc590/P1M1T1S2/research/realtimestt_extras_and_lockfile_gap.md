# Research Note: realtimestt 1.0.2 Extras Truth & Lockfile Reproducibility Gap (RE-PLAN)

**Status:** EMPIRICALLY VERIFIED on this exact machine, July 7 2026 (uv 0.7.11, Python 3.12.10, RTX 3080 Ti driver 610.43.02).
**Why this note exists:** Attempt 1 of P1.M1.T1.S2 halted because bare `realtimestt` did not pull the CUDA inference backend. This note records the root cause and corrects attempt 1's own proposed fix, which was also wrong. It supersedes the stale "transitive" claims in `research_faster_whisper_cuda.md` §6 and `research_realtimestt_api.md` §6.

---

## Finding A — `faster-whisper` / `ctranslate2` are EXTRAS, not transitive deps

Source of truth: `.venv/lib/python3.12/site-packages/realtimestt-1.0.2.dist-info/METADATA` (the installed wheel).

**Unconditional `Requires-Dist` (what bare `realtimestt` gives you — 9 packages):**
```
PyAudio==0.2.14, webrtcvad-wheels==2.0.14, halo==0.0.31, torch, torchaudio,
scipy==1.17.1, websockets==16.0, websocket-client==1.9.0, soundfile==0.13.1
```

**Gated behind extras (the inference backends / VAD):**
```
Provides-Extra: faster-whisper  → faster-whisper==1.2.1; extra == "faster-whisper"
Provides-Extra: whisper-cpp / whispercpp → pywhispercpp
Provides-Extra: openai-whisper   → openai-whisper
Provides-Extra: sherpa-onnx / sherpa → sherpa-onnx
Provides-Extra: silero-vad / silero → silero-vad>=6.2.1
Provides-Extra: silero-onnx / silero-onnx-cpu / vad-onnx → silero-vad[onnx-cpu]>=6.2.1
Provides-Extra: silero-onnx-gpu / vad-onnx-gpu → silero-vad[onnx-gpu]>=6.2.1
Provides-Extra: transformers / moonshine / granite / cohere → transformers
Provides-Extra: parakeet / nvidia-parakeet → nemo_toolkit[asr]
```

**Consequence:** `uv add realtimestt` (bare) resolves to the 9 unconditional deps + their transitive leaves (numpy, etc.) and **NO** `faster-whisper`, `ctranslate2`, `onnxruntime`, `av`, or `tokenizers`. The CUDA inference path — the entire point of the project — is absent. This is exactly what attempt 1 observed.

**The transitive claim `faster-whisper` pulls `ctranslate2` IS still true** — but only once `faster-whisper` itself is pulled (via the extra). `faster-whisper==1.2.1`'s own deps include `ctranslate2>=4.0,<5`, `onnxruntime`, `av`, `tokenizers`, `huggingface_hub>=0.23`. Confirmed by the current `.venv` (installed out-of-band): `faster_whisper 1.2.1`, `ctranslate2 4.8.1`, `onnxruntime 1.27.0`, `av 18.0.0`, `tokenizers 0.23.1`.

---

## Finding B — Attempt 1's proposed fix (`realtimestt[default]`) is itself wrong

Attempt 1 recommended `realtimestt[default]` (or `[recommended]`). **Neither extra exists in 1.0.2** — see the `Provides-Extra` list above. `uv add realtimestt[default]` would error: `extra 'default' is not provided`.

**Valid, version-correct extras for this project:** `faster-whisper` and `silero-vad`. The PRP prescribes `realtimestt[faster-whisper,silero-vad]`:
- `faster-whisper` → `faster-whisper==1.2.1` → ctranslate2+onnxruntime+av+tokenizers (MUST-HAVE CUDA inference).
- `silero-vad` → `silero-vad>=6.2.1` (daemon uses `silero_backend="auto"`; see Finding D).

---

## Finding C — The committed `uv.lock` does NOT track the CUDA stack (reproducibility gap)

Verified state at HEAD (`bde0a56`):

| check | result |
|---|---|
| `grep -c '^\[\[package\]\]' uv.lock` | **66** |
| `grep '^name = "faster-whisper"' uv.lock` | (no match — NOT tracked) |
| `grep '^name = "ctranslate2"' uv.lock` | (no match — NOT tracked) |
| `grep '^name = "onnxruntime"' uv.lock` | (no match) |
| `grep '^name = "tokenizers"' uv.lock` | (no match) |
| `grep '^name = "av"' uv.lock` | (no match) |
| `grep '^name = "silero-vad"' uv.lock` | (no match) |
| `.venv` imports faster-whisper/ctranslate2/onnxruntime/av/tokenizers | **all import OK** |
| `ctranslate2.get_cuda_device_count()` | **1** |
| `torch.cuda.is_available()` | **True** |

**Interpretation:** the `.venv` was populated OUT-OF-BAND (e.g. `uv pip install faster-whisper ...`) after attempt 1, but `pyproject.toml`/`uv.lock` were never updated to match. A fresh `uv sync`, CI, or `rm -rf .venv && uv sync` from a clean checkout would produce the 66-package closure **without** the inference backend and would **fail** `ctranslate2.get_cuda_device_count()`.

**This is the real deliverable of S2:** make `pyproject.toml` + `uv.lock` the source of truth so the working stack is reproducible. PRP Task 1 (correct the dep token) + Task 2 (regenerate lock) close this gap; PRP Level 2 (`uv lock --check` + grep proof) verifies it.

---

## Finding D — silero-vad is NOT bundled in RealtimeSTT 1.0.2; daemon needs the package

- `find .venv/.../RealtimeSTT -iname '*.onnx'` → **none**. No bundled VAD model asset.
- RealtimeSTT ships `core/silero_vad.py` (the loader) but the `.onnx` weights must come from elsewhere.
- The daemon (`voice_typing/daemon.py`, P1.M4.T1.S1 — Complete) uses `silero_backend="auto"` (NOT the legacy `silero_use_onnx=True`). `auto` tries `silero_vad_op18_ifless.onnx` then `silero_vad.onnx`.
- `import silero_vad` currently **fails** (`ModuleNotFoundError`) in the out-of-band `.venv`.
- Hence the PRP includes the `silero-vad` extra (→ `silero-vad>=6.2.1`). This is not in the literal S2 OUTPUT list, but the daemon's VAD path depends on it and RealtimeSTT ships no weights; omitting it would surface as a runtime/recorder-construction failure in P1.M4/P1.M7.
- Note: `ctranslate2` CUDA (Finding C) remains the sole **hard** gate per the contract; silero-vad is the recommended companion (runs on CPU, ~1-2ms/frame).

---

## Finding E — torch CUDA is currently satisfied (cu126 branch NOT needed today)

- Installed torch `2.12.1` (PyPI default, cu130-bundled) → `torch.cuda.is_available() == True`.
- torch bundles its own CUDA runtime (cu13 nvidia libs present: `nvidia_cudnn_cu13`, `nvidia_cuda_nvrtc_cu13`, …). ctranslate2 links cu12 libs (`nvidia_cublas_cu12`, `nvidia_cudnn_cu12==9.*`). They **coexist** via soname versioning (`libcublas.so.12` vs `.so.13`) — no conflict.
- **Therefore:** the Task 5 cu126 conditional branch is NOT expected to run on this machine today. It is documented for reproducibility (a future resolve that yields a CPU-only torch). Per the contract, torch CUDA is nice-to-have and must not block the project.

---

## Correction of prior research (for the record)

| Source | Stale claim | Correction |
|---|---|---|
| `research_faster_whisper_cuda.md` §6 | "RealtimeSTT pulls faster-whisper transitively, so these are handled by `uv add realtimestt`." | False for 1.0.2 base install. Use `realtimestt[faster-whisper]`. |
| `research_realtimestt_api.md` §6 | (implies) realtimestt pulls torch + faster-whisper + pyaudio + webrtcvad + onnxruntime transitively. | faster-whisper/onnxruntime are extras, not transitive. torch/pyaudio/webrtcvad ARE transitive. |
| PRD.md §5 step 4 | "`uv add realtimestt …` — pulls torch, faster-whisper, pyaudio, webrtcvad, etc." | Incomplete: faster-whisper needs the extra. PRP Task 1 corrects it. |
| Attempt 1 issue_feedback | "change S1's pyproject dependency to `realtimestt[default]`" | `default` extra doesn't exist. Use `faster-whisper` (+ `silero-vad`). |

## SUMMARY (what the PRP relies on)

1. ✅ Root cause = bare `realtimestt` lacks the `faster-whisper` extra. Fix = `realtimestt[faster-whisper,silero-vad]`.
2. ✅ `[default]`/`[recommended]` extras do NOT exist in 1.0.2 — do not use them.
3. ✅ The committed `uv.lock` (66 pkgs) does not track the CUDA stack; S2 must regenerate it (PRP Task 2) and prove it via `uv lock --check` + grep (PRP Level 2).
4. ✅ silero-vad package is needed (no bundled ONNX) → include the extra.
5. ✅ torch.cuda already True → cu126 branch is conditional/not expected today.
6. ✅ Hard gate = `ctranslate2.get_cuda_device_count() >= 1`.
