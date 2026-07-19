# External Research — huggingface_hub snapshot_download / cache / offline semantics

**Purpose:** authoritative backing for the prefetch.py audit (P1.M4.T3.S2). prefetch.py calls
`snapshot_download(repo_id=repo_id, repo_type="model")` with all other args at DEFAULT
(cache_dir=None, local_dir=None, token=None, force_download=False, local_files_only defaults False).
This note pins the official semantics for each load-bearing behavior + the exact doc URLs (live
web-search-verified 2026-07-19). All URLs confirmed reachable via web_search_prime this round.

---

## 1. Default cache location (cache_dir=None → `~/.cache/huggingface/hub`)

**Verdict:** with `cache_dir=None` AND `local_dir=None`, snapshot_download writes to the **default
central cache** `$HF_HOME/hub` (default `HF_HOME=~/.cache/huggingface` → `~/.cache/huggingface/hub`).
This is the cache faster-whisper reads from at runtime. **prefetch.py leaving cache_dir=None is
CORRECT** (the load-bearing default — docstring prefetch.py:64-66).

**Cache folder structure** (blobs + snapshots, symlink-deduplicated):
```
~/.cache/huggingface/hub/models--<owner>--<name>/
├── blobs/<sha>              # the ACTUAL file bytes (content-addressed; dedup'd across revisions)
├── snapshots/<rev>/         # one dir per pinned commit
│   ├── model.bin -> ../../blobs/<sha>   # SYMLINKS into blobs/
│   ├── config.json -> ...
│   └── ...
└── refs/main                # the resolved rev pointer
```

**URLs (authoritative):**
- https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache — *"The blobs folder contains
  the actual files that we have downloaded. The snapshots folder contains symlinks to the blobs."*
  (the blobs/snapshots/symlink structure + how to inspect/clean the cache).
- https://huggingface.co/docs/huggingface_hub/en/guides/download — *"You can specify a custom cache
  location using the cache_dir parameter ... or by setting the HF_HOME environment variable."*
  (confirms cache_dir=None ⇒ default HF_HOME/hub).
- LIVE-VERIFIED this repo: `~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/`
  etc. all present (see prefetch_audit.md §0).

**Gotcha:** a bare `find -name model.bin -printf '%s'` reports the **symlink stub size** (~76 B = the
`../../../blobs/<sha>` path string), NOT the blob. Use `os.path.getsize` (follows symlinks) or
`stat -L`. prefetch.py's `_model_bin_size()` uses `os.path.getsize` (correct).

---

## 2. Idempotency / re-run with force_download=False (default) — skips cached blobs

**Verdict:** `force_download=False` (the default) ⇒ snapshot_download **does NOT re-download** a blob
whose cached etag already matches; it reuses the cached file. It DOES still make a lightweight
per-file **HEAD/etag freshness check** over the network (to learn the latest commit + each file's
etag) UNLESS `HF_HUB_OFFLINE=1` is set. Re-runs are therefore "cheap" (metadata only) but not
zero-network unless offline mode is on. **prefetch.py leaving force_download=False is CORRECT** (the
idempotent default — contract point (d)).

**URLs:**
- https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download — the
  snapshot_download reference: `force_download` ("Whether to download all files even if they are
  already present in the cache"); `local_files_only` ("If True, do not perform any HTTP call ... if
  the files are missing, raise LocalEntryNotFoundError").
- https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/_snapshot_download.py
  — the source (the per-file hf_hub_download loop that honors force_download / etag).

**Gotcha for the audit:** "idempotent" here means "no redundant re-download", NOT "zero network on
every run". The zero-network guarantee comes from `HF_HUB_OFFLINE=1` at RUNTIME (launch_daemon.sh),
not from prefetch.py's re-run semantics. prefetch.py's own summary uses `local_files_only=True`
(prefetch.py:162) so the summary itself never hits the network.

---

## 3. local_files_only=True — cache-hit-only resolution; LocalEntryNotFoundError if absent

**Verdict:** `local_files_only=True` ⇒ snapshot_download resolves the snapshot **from cache with NO
HTTP call**; if any requested file/repo is absent from the cache it raises **`LocalEntryNotFoundError`**
(a subclass of the offline/cache-miss family). prefetch.py's `_local_snapshot()` (prefetch.py:159-165)
wraps this in try/except → None (a cache-miss probe for the summary). **CORRECT usage.**

**URLs:**
- https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download —
  *"local_files_only: ... If True, ... if the files are missing ... raise LocalEntryNotFoundError."*
- https://huggingface.co/docs/huggingface_hub/en/guides/download — hf_hub_download / the
  local_files_only pattern (cache-or-raise, no download).
- LIVE-VERIFIED: the `HF_HUB_OFFLINE=1 ... local_files_only=True` offline-resolution test in
  prefetch_audit.md §6 resolves all 4 repos (proves Acceptance #8 with zero network).

---

## 4. HF_HUB_OFFLINE=1 — read at IMPORT TIME; fully cache-only; fail-fast on miss

**Verdict:** `HF_HUB_OFFLINE=1` is read by huggingface_hub **at import time** from the env var
(`constants.py: HF_HUB_OFFLINE = _is_true(os.environ.get("HF_HUB_OFFLINE") or
os.environ.get("TRANSFORMERS_OFFLINE"))`). Once set before process start, **all** HTTP requests raise
`OfflineModeIsEnabledError`; a cache-miss raises `LocalEntryNotFoundError` (NO silent/lazy download).
`TRANSFORMERS_OFFLINE=1` is honored as a synonym. launch_daemon.sh sets both (:71-72) before exec'ing
python — this is the runtime guarantee of "no network at runtime" (Acceptance #8's runtime half).

**URLs:**
- https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables — the
  `HF_HUB_OFFLINE` entry: *"If HF_HUB_OFFLINE=1 is set ... will not make any HTTP request to the
  Hub ... only access cached files."* (also TRANSFORMERS_OFFLINE alias, HF_HOME, HF_HUB_CACHE).
- https://huggingface.co/docs/huggingface_hub/en/package_reference/utilities —
  *"You can programmatically check if offline mode is enabled using is_offline_mode. Offline mode is
  enabled by setting HF_HUB_OFFLINE=1 as environment variable."*
- https://github.com/huggingface/huggingface_hub/issues/2590 — *"If HF_HUB_OFFLINE=1 is set ... and
  you call any method of HfApi, an OfflineModeIsEnabled exception will be raised."* (confirms the
  fail-fast behavior; the env var is read at import, so it must be set BEFORE process start — exactly
  why launch_daemon.sh exports it pre-exec).
- LIVE-VERIFIED in this repo's venv: `.venv/lib/python3.12/site-packages/huggingface_hub/constants.py`
  line `HF_HUB_OFFLINE = _is_true(os.environ.get("HF_HUB_OFFLINE") or os.environ.get("TRANSFORMERS_OFFLINE"))`
  + `def is_offline_mode() -> bool: return HF_HUB_OFFLINE`.

**Gotcha (cross-file, NOT prefetch.py):** because HF_HUB_OFFLINE=1 forbids runtime download, a missing
cache entry **fail-fasts** (LocalEntryNotFoundError) rather than lazy-downloading. install.sh's
warning message ("the daemon will download missing models on first run", install.sh:103) is therefore
technically inaccurate under HF_HUB_OFFLINE=1 — but that is install.sh's message, not prefetch.py's
logic (P1.M4.T3.S1 scope).

---

## 5. cache_dir (legacy, central) vs local_dir (newer, plain copy) — which does faster-whisper read?

**Verdict:**
- `cache_dir` (the DEFAULT prefetch.py uses) → the **central blob+snapshot symlink cache** that
  huggingface_hub, transformers, AND **faster-whisper** all read from. Deduplicated across revisions.
- `local_dir` (NOT set by prefetch.py) → materializes a **plain folder copy** (no symlinks, no dedup;
  historically 2× disk — see issue #2284). faster-whisper does NOT read a `local_dir` copy unless you
  point `WhisperModel(download_root=...)` or a path at it.

⇒ **prefetch.py leaving BOTH cache_dir=None AND local_dir=None is the CORRECT choice** (docstring
prefetch.py:64-66: "cache_dir/local_dir/token stay None (so the weights land in the default
~/.cache/huggingface/hub that faster-whisper reads)"). Setting local_dir would land weights in a
folder faster-whisper does NOT auto-read → the daemon would re-download to the central cache. Setting
cache_dir to a non-default would land them somewhere faster-whisper only reads if HF_HOME matches.

**URLs:**
- https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache — the central cache model
  (blobs/snapshots/symlinks) — what cache_dir populates.
- https://github.com/huggingface/huggingface_hub/issues/2284 — *"This process copies the files from
  ~/.cache/huggingface/hub to local_dir, resulting in 2X the disk space"* (the local_dir-vs-cache_dir
  distinction + the dedup argument for the central cache).

---

## 6. faster-whisper (CTranslate2) reads the SAME default HF cache

**Verdict:** faster-whisper's `WhisperModel(model_size_or_path)` — when given a SHORT name like
`"distil-large-v3"` / `"small.en"` / `"tiny.en"` / `"large-v3-turbo"` — resolves it via its internal
`_MODELS` dict to a HF repo_id and pulls it from **the SAME `~/.cache/huggingface/hub`** via
huggingface_hub. Therefore a model pre-downloaded by a standalone `snapshot_download(...)` call (as
prefetch.py does) is **found already cached at runtime** — no re-download. This is the load-bearing
fact behind contract (a) ("the daemon finds a cached weight for every name it can be told to load").
LIVE-VERIFIED: prefetch.py's 4 short names ALL map to the same repo_id faster-whisper's `_MODELS`
resolves them to (see prefetch_audit.md §3).

**URLs:**
- https://github.com/SYSTRAN/faster-whisper — *"When loading a model from its size such as
  WhisperModel('large-v3'), the corresponding CTranslate2 model is automatically downloaded from the
  Hugging Face Hub."* (the short-name → auto-download-from-HF behavior).
- https://github.com/SYSTRAN/faster-whisper/discussions/1173 — *"it's downloaded from huggingface to
  the huggingface cache dir ... /home/user/.cache/huggingface/"* (confirms faster-whisper uses the
  DEFAULT HF cache, not a private one).
- https://github.com/SYSTRAN/faster-whisper/issues/116 — *"The Whisper models are automatically
  downloaded from the Hugging Face Hub. To run the library offline, you should first download a model
  locally"* (the prefetch→offline pattern: pre-download with snapshot_download, then run offline).

**Gotcha (trap-avoidance, already handled in prefetch.py):** the raw-PyTorch repo
`distil-whisper/distil-large-v3` is NOT CTranslate2-format (no model.bin) — CTranslate2 cannot load
it. prefetch.py correctly uses `Systran/faster-distil-whisper-large-v3` (the CT2 conversion), and the
docstring (prefetch.py:18-20) explicitly warns against the raw-PyTorch repo. (NUANCE: there are also
OTHER turbo repos on HF, e.g. `deepdml/faster-whisper-large-v3-turbo-ct2`; prefetch.py correctly uses
`mobiuslabsgmbh/faster-whisper-large-v3-turbo` — the one faster-whisper's `_MODELS["large-v3-turbo"]`
points to.)

---

## Summary — are prefetch.py's defaults subtly wrong anywhere?

**No.** Every default is the load-bearing-correct choice for the "prefetch so the daemon never hits
the network" goal:
- `cache_dir=None` ✓ (lands in the central cache faster-whisper reads — §1, §5, §6)
- `local_dir=None` ✓ (no 2×-disk plain copy faster-whisper wouldn't auto-read — §5)
- `token=None` ✓ (all 4 repos are public; anonymous access suffices)
- `force_download=False` ✓ (idempotent re-runs — §2)
- `repo_type="model"` ✓ (cache path is `models--<owner>--<name>` — §1)
- the 4-repo SUPERSET ✓ (covers CUDA + CPU-fallback + substitute — Nuance §4.1)
- the CORE/OPTIONAL split ✓ (mandatory=fatal, substitute=warn-only — §4.2)
- `local_files_only=True` in the summary ✓ (no re-download on the size tally — §3)
- the lazy huggingface_hub-only import ✓ (runs before ctranslate2 is installed — §4.3)
The runtime offline half is launch_daemon.sh's `HF_HUB_OFFLINE=1` (§4, §5 of prefetch_audit.md).