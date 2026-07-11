# Research: HF Hub Offline Mode (from researcher subagent)

## Summary

`HF_HUB_OFFLINE=1` is the single authoritative flag that makes `huggingface_hub`
(and therefore faster-whisper's model resolution and RealtimeSTT's
`AudioToTextRecorder`) read **exclusively** from the local cache
(`~/.cache/huggingface/hub`) with **zero HTTP** — including skipping the
freshness HEAD request that online mode makes even for fully-cached files.

## Key Findings

### Q1: Does HF_HUB_OFFLINE=1 fully prevent all network calls?
**Yes.** Read at import time in `huggingface_hub/constants.py`:
`os.getenv("HF_HUB_OFFLINE", "0").lower() in ("1", "true")`. When set, every
network-touching code path short-circuits to cache-only. The freshness HEAD
request is skipped entirely.
Source: https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables

### Q2: Does it make snapshot_download / model loading cache-only?
**Yes.** Resolves the cached commit hash from
`~/.cache/huggingface/hub/models--<owner>--<name>/refs/main`, reads the snapshot
tree, returns the snapshot path. No GET, no HEAD, no resolve call.
ctranslate2 itself performs no network I/O — loads weights from a directory path.

### Q3: Model cached + offline → loads successfully, zero network?
**Yes.** The prefetch-then-offline pattern is exactly what the daemon is designed
for. install.sh step [3/7] runs prefetch.py → populates cache. At runtime,
HF_HUB_OFFLINE=1 resolves repos from cache.

### Q4: Model NOT cached + offline → LocalEntryNotFoundError?
**Yes.** `huggingface_hub.errors.LocalEntryNotFoundError` raised at construction.
Surfaces at `AudioToTextRecorder.__init__` → caught by `daemon.py::main()` →
`return 1` → systemd `Restart=on-failure`.

**⚠️ Behavior change:** removes lazy-download self-heal. Uncached model = fail-fast
crash-loop instead of silent download. Intended design (prefetch at install time).

### Q5: Does faster-whisper / RealtimeSTT respect HF_HUB_OFFLINE?
**Yes (all three).**
- faster-whisper: `WhisperModel.__init__` → `download_model()` → `snapshot_download()`.
- ctranslate2: no networking at all.
- RealtimeSTT: constructs faster-whisper's `WhisperModel` — inherits offline behavior.
- Silero VAD: separate mechanism (torch.hub), already mitigated by `silero_backend="auto"`.

### Q6: Is TRANSFORMERS_OFFLINE needed for faster-whisper?
**No.** faster-whisper has no `transformers` dependency. Harmless belt-and-suspenders.

### Q7: Is export-before-exec inherited by Python?
**Yes.** `export` places var in shell env; `execve` copies env to new process.
Python's `os.environ` has it from first bytecode. `multiprocessing.spawn`
children inherit too. **Strictly more correct** than setting inside Python
(huggingface_hub captures flag at import time).
Source: POSIX `execve(2)` / bash `export`.

## Validation of Proposed Diff

```bash
# In voice_typing/launch_daemon.sh, before exec "$PY" -m voice_typing.daemon "$@":
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

**Correct and sufficient:**
- HF_HUB_OFFLINE=1 ⇒ all huggingface_hub calls cache-only (§1-3, §5)
- TRANSFORMERS_OFFLINE=1 ⇒ no-op-but-harmless (§6)
- export …; exec python ⇒ inherited by Python + spawn workers (§7)
- Telemetry suppressed (subsumes HF_HUB_DISABLE_TELEMETRY)
