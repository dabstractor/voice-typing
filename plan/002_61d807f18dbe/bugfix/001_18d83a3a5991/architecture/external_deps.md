# External Dependencies — Bugfix 001

## huggingface_hub Offline Behavior

### `HF_HUB_OFFLINE=1` — The Authoritative Flag

- Read at **import time** in `huggingface_hub/constants.py`:
  `HF_HUB_OFFLINE = os.getenv("HF_HUB_OFFLINE", "0").lower() in ("1", "true")`.
- When `True`, ALL network-touching code paths short-circuit to cache-only:
  - `hf_hub_download` / `snapshot_download` → resolve from
    `~/.cache/huggingface/hub` only, no HTTP.
  - The **freshness HEAD/GET request is SKIPPED** (this is the exact mechanism
    that prevents the `GET https://huggingface.co/api/models/.../revision/main`
    calls seen in the journal).
  - Anonymous telemetry is suppressed (subsumes `HF_HUB_DISABLE_TELEMETRY`).
- Source: https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables
  and `huggingface_hub/constants.py`.

### `TRANSFORMERS_OFFLINE=1` — Belt-and-Suspenders (No-Op for faster-whisper)

- Belongs to the `transformers` library, which faster-whisper does NOT depend on.
- faster-whisper's deps: `ctranslate2`, `huggingface-hub`, `tokenizers`,
  `onnxruntime`, `av`, `tqdm` — no `transformers`.
- Harmless to set; guards against a future dependency change.
- Source: faster-whisper `setup.py`.

### Model Cached + Offline → Loads Successfully (Zero Network)

- The daemon's `AudioToTextRecorder` resolves short-names (`distil-large-v3`,
  `small.en`, `tiny.en`) through faster-whisper's `_MODELS` dict to HF repo_ids,
  then calls `snapshot_download(repo_id)`. Under `HF_HUB_OFFLINE=1`, this resolves
  the cached snapshot dir from `~/.cache/huggingface/hub` with zero HTTP.
- The project ALREADY relies on the per-call equivalent
  (`snapshot_download(..., local_files_only=True)`) in `prefetch.py::_local_snapshot()`.

### Model NOT Cached + Offline → `LocalEntryNotFoundError` (Fail-Fast)

- `huggingface_hub.errors.LocalEntryNotFoundError` is raised. For the daemon,
  this surfaces at `AudioToTextRecorder` construction → caught by `daemon.py::main()`'s
  construction `try/except` → logged → `return 1` → systemd `Restart=on-failure`.
- **Tradeoff accepted:** this removes the daemon's lazy-download self-heal. An
  uncached model now fails fast instead of silently downloading at runtime.
  Models MUST be prefetched by `install.sh` → `prefetch.py`.

### ctranslate2 / RealtimeSTT

- **ctranslate2:** no networking at all. Loads weights from a directory path.
- **RealtimeSTT:** constructs faster-whisper's `WhisperModel` under the hood —
  inherits `huggingface_hub` offline behavior. No separate download code path.
- **Silero VAD** (used by RealtimeSTT): some paths download via `torch.hub`
  (NOT governed by `HF_HUB_OFFLINE`). Already mitigated independently by
  `_FIXED_KWARGS["silero_backend"] = "auto"` (prefers bundled CPU ONNX, avoids
  torch.hub download). Out of scope for this fix.

### Process Inheritance (export before exec)

- `export VAR=1` places the variable in the shell environment. `exec` issues
  `execve`, which copies the environment to the new process image.
- Python's `os.environ["HF_HUB_OFFLINE"] == "1"` from the first bytecode.
- `multiprocessing.spawn` children (RealtimeSTT workers) inherit `os.environ` too.
- **Strictly more correct** than setting `os.environ` inside Python after
  `huggingface_hub` may already be imported (the flag is captured at import time).
- This is the IDENTICAL, already-proven mechanism for `LD_LIBRARY_PATH`.

## PyAudio (Issue 3 — Mic Probe)

- `pyaudio.PyAudio()` initializes PortAudio and enumerates devices. The init +
  enumerate + terminate cycle takes ~39-43 ms on this host.
- This is the cost being cached by the TTL fix — the probe only needs to run
  once every ~30s (or once per daemon session if arms are infrequent).
- `pyaudio` is imported LAZILY inside `_probe_mic()` (not at module top) to
  preserve `import voice_typing.daemon` / `voice_typing.ctl` purity. The TTL
  fix must not change this import location.

## jq (Issue 2 — status.sh)

- jq exits with code 0 on success, 1 if no output, 2 on usage/parse error,
  5 if the input file is unreadable or the JSON is invalid.
- When `state.json` is missing: jq can't open the file → exit 2.
- When `state.json` is corrupt JSON: jq parse error → exit 5.
- tmux's `#(...)` substitution captures stdout and ignores the exit code, so
  the status line still renders blank on failure — but the documented contract
  ("exit 0") is violated.
