# Research: huggingface_hub prefetch — API, repo inventories, traps (VERIFIED)

**Status:** VERIFIED live against the installed `.venv` (`huggingface_hub==1.22.0`) and the live
HF API on 2026-07-06. This note is the load-bearing source for `P1M1T3S1/PRP.md`.
**Method:** direct probes under `/home/dustin/projects/voice-typing/.venv/bin/python` (no mocking).

---

## 1. INPUT dependency is satisfied (independent of P1.M1.T2.S2)

- `.venv/bin/python` → Python 3.12.10.
- `huggingface_hub==1.22.0` IS importable in `.venv` right now (declared in pyproject by
  S1; installed by the S2 sync). **`from huggingface_hub import snapshot_download` works today.**
- `ctranslate2` and `faster_whisper` are **NOT** installed yet (T2.S2 still in progress).
  **This does NOT matter for prefetch:** `snapshot_download` only needs `huggingface_hub`. It
  moves bytes into the cache; it never touches ctranslate2. So **T3.S1 has zero hard dependency on
  T2.S2** — prefetch can run and populate `~/.cache/huggingface` regardless of CUDA state. The
  cached weights become loadable only once ctranslate2 lands (T2.S2 → daemon P1.M4.T1.S1).

> This is the key scope-coupling fact: prefetch = "files in cache"; construction = "load files".
> They are decoupled by the shared HF cache.

---

## 2. `snapshot_download` signature — VERIFIED for huggingface_hub 1.22.0

```
snapshot_download(
    repo_id,               # REQUIRED — e.g. "Systran/faster-distil-whisper-large-v3"
    repo_type=None,        # "model" inferred from repo for model repos; pass explicitly to be safe
    revision=None,         # None → "main"
    cache_dir=None,        # None → HF_HUB_CACHE (default ~/.cache/huggingface/hub)  ← WANT THIS
    local_dir=None,        # None → snapshot-style cache layout (symlinks under cache) ← WANT THIS
    etag_timeout=10,
    force_download=False,  # False → cache-aware, IDEMPOTENT (re-runs skip present files)
    token=None,            # None → anonymous; repos are PUBLIC/ungated → no token needed
    local_files_only=False,
    allow_patterns=None,   # None → download EVERYTHING in the repo
    ignore_patterns=None,  # could skip *.md, .gitattributes, but they're tiny → not worth it
    max_workers=8,         # parallel file downloads; default is fine
    tqdm_class=None,       # per-file progress bars shown automatically (tqdm is bundled)
    dry_run=False,
)
```

**Return value:** `str` — the local path to the resolved snapshot dir, e.g.
`/home/dustin/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/snapshots/<rev>`.

**Load-bearing facts:**
- `cache_dir=None` + `local_dir=None` (the defaults) → the canonical HF hub cache layout. **This is
  exactly what faster-whisper reads.** Do NOT set `local_dir` (it writes a flat copy faster-whisper
  won't auto-find) and do NOT override `cache_dir` (breaks the default resolution). Just call
  `snapshot_download(repo_id=...)`.
- **Idempotent by default** (`force_download=False`): re-running skips files whose cached etag
  matches. This is precisely the property `install.sh` (P1.M6.T1.S1) relies on to "re-invoke
  idempotently". Do NOT pass `force_download=True`.
- **No HF token:** all 4 target repos are public. `token=None` (default) works. Verified.
- **Progress:** tqdm per-file bars render automatically to stderr. We layer our own
  `=== [<short>] <repo_id> ===` headers on stdout for human/cli greppability.

---

## 3. Repo inventories — VERIFIED via `HfApi.repo_info` (live, 2026-07-06)

All four target repos are **CTranslate2 format** (contain `model.bin`, NO `pytorch_model.bin` /
`.safetensors` / `.pt`). This confirms the repo IDs from
`research_faster_whisper_cuda.md §1`.

| short name | repo_id | files | CT2 (`model.bin`)? |
|---|---|---|---|
| `distil-large-v3` | `Systran/faster-distil-whisper-large-v3` | `.gitattributes`, `README.md`, `config.json`, **`model.bin`**, `preprocessor_config.json`, `tokenizer.json`, `vocabulary.json` | ✅ |
| `small.en` | `Systran/faster-whisper-small.en` | `.gitattributes`, `README.md`, `config.json`, **`model.bin`**, `tokenizer.json`, `vocabulary.txt` | ✅ |
| `tiny.en` | `Systran/faster-whisper-tiny.en` | `.gitattributes`, `README.md`, `config.json`, **`model.bin`**, `tokenizer.json`, `vocabulary.txt` | ✅ |
| `large-v3-turbo` | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` | `.gitattributes`, `README.md`, `config.json`, **`model.bin`**, `preprocessor_config.json`, `tokenizer.json`, `vocabulary.json` | ✅ |

**Approx model.bin sizes (for expectation-setting; multi-minute download):**
- `distil-large-v3` ≈ **1.5 GB**, `large-v3-turbo` ≈ **1.6 GB**, `small.en` ≈ **240 MB**, `tiny.en` ≈ **75 MB**.
- Core 3 total ≈ **1.8 GB**; with turbo ≈ **3.4 GB**. Disk: 237 GB free on `/home` — ample.

### ⚠️ THE TRAP — do NOT prefetch this repo (confirmed)

`distil-whisper/distil-large-v3` (note: `distil-whisper/` owner, raw PyTorch checkpoint) has **NO
`model.bin`**. Its 27 files are `model.safetensors`, `model.fp32.safetensors`, `flax_model.msgpack`,
`onnx/*`, etc. CTranslate2 cannot load these. The CTranslate2-converted weights live under the
**`Systran/`** owner (`Systran/faster-distil-whisper-large-v3`). The contract's repo list uses the
correct `Systran/` (and `mobiuslabsgmbh/` for turbo) IDs — do not "fix" them to the
`distil-whisper/` raw repo.

> Note on the two vocabulary extensions: `distil-large-v3` + `large-v3-turbo` ship `vocabulary.json`
> + `preprocessor_config.json`; `small.en`/`tiny.en` ship `vocabulary.txt` (no preprocessor). This is
> just Systran's packaging; faster-whisper handles both. `snapshot_download` fetches whatever the
> repo contains — no special handling needed.

---

## 4. Cache layout & how the daemon consumes it (the whole point)

Default cache: `~/.cache/huggingface/hub/`. A repo lands as:
```
~/.cache/huggingface/hub/
└── models--Systran--faster-distil-whisper-large-v3/
    ├── blobs/<sha>            # the actual bytes (model.bin lives here)
    ├── refs/main              # → current revision sha
    └── snapshots/<sha>/       # symlinks into blobs/ — the "resolved model dir"
        ├── config.json  model.bin  tokenizer.json  ...
```

Consumption path (P1.M4.T1.S1, verified in `research_realtimestt_api.md §1`):
`AudioToTextRecorder(model="distil-large-v3", realtime_model_type="small.en", ...)` → faster-whisper
`WhisperModel("distil-large-v3")` → resolves short name via its `_MODELS` table to the repo_id →
`huggingface_hub` cache lookup → **instant if prefetched, else multi-GB download at first daemon
run**. Same for `small.en` / `tiny.en` (CPU fallback) and `large-v3-turbo` (substitute). Prefetching
all of them means: (a) first daemon start is instant, (b) the CPU-fallback + turbo-substitute paths
are already on disk if the daemon needs them (no network at runtime — "100% local").

---

## 5. Network + disk + idempotency — VERIFIED

- **Network:** `HfApi().repo_info('Systran/faster-whisper-tiny.en')` returned 6 files (live probe).
  HF reachable from this host. No proxy / token needed.
- **Disk:** `df -h /home` → 237 GB avail. Plenty for ~3.4 GB of models.
- **Existing cache:** `~/.cache/huggingface/hub/` already holds unrelated repos
  (`models--ResembleAI--chatterbox`, `models--sentence-transformers--all-MiniLM-L6-v2`). None of the
  four whisper repos are present yet — prefetch is a clean cold download.
- **Idempotency re-run:** `snapshot_download(force_download=False)` (default) re-checks etags and
  skips present blobs. Re-invoking `python -m voice_typing.prefetch` after a successful run completes
  in seconds with no re-download. → safe for `install.sh` (P1.M6.T1.S1) to re-invoke.

---

## 6. Design decisions for prefetch.py (locked by this research)

1. **Repos:** `CORE_REPOS = {distil-large-v3, small.en, tiny.en}` (3, the contract's required set) +
   `OPTIONAL_REPOS = {large-v3-turbo}` (the approved substitute). Download CORE always; download
   turbo too by default (disk is ample; gives the substitute + a second FINAL option ready).
2. **API:** one `snapshot_download(repo_id=..., repo_type="model")` per repo, **defaults kept**
   (`cache_dir`/`local_dir`/`token`/`force_download` all default). No `allow_patterns` — fetch the
   whole repo (every file is small except model.bin, and config/tokenizer/vocabulary are all needed).
3. **Progress:** stdout `=== [<short>] <repo_id> ===` header per repo + the returned snapshot path on
   completion; huggingface_hub's bundled tqdm renders per-file bars to stderr automatically.
4. **Error semantics:** a CORE repo failure → script exits non-zero (the daemon cannot start without
   them). A turbo (optional) failure → warning, non-fatal (exit reflects core success only).
5. **Post-download verify:** for each repo, stat `model.bin` in the returned snapshot path and print
   its size — proves the CT2 weights landed (not just metadata). Cheap, catches partial/empty repos.
6. **CLI vs importable:** `python -m voice_typing.prefetch` is the CLI (matches `cuda_check.py`'s
   `-m` convention — NOT added to `[project.scripts]`; install.sh calls `-m`). A `prefetch(...)`
   function is importable for future programmatic use, but the only documented caller is the CLI.
7. **No CUDA / ctranslate2 import:** prefetch.py imports ONLY `huggingface_hub` (lazily, inside the
   function — so `import voice_typing.prefetch` never triggers a network call or heavy import).
8. **No LD_LIBRARY_PATH:** irrelevant here (no CUDA). prefetch.py runs with plain `.venv/bin/python`.
9. **Telemetry:** set `HF_HUB_DISABLE_TELEMETRY=1` at the top of `_main()` (local-first ethos; no-op
   if already set).
