"""Pre-download faster-whisper CTranslate2 models into the HF cache.

Populates ~/.cache/huggingface/hub so the daemon's AudioToTextRecorder
construction (P1.M4.T1.S1) is instant: RealtimeSTT/faster-whisper resolve
the short model names to these HF repo_ids and find the weights already
cached. With both repos local, the SINGLE Rev 2 model (small.en) and the
CPU-fallback model (tiny.en) are on disk — no network at runtime.

Rev 2 (P1.M1.T2.S4) collapsed the daemon to ONE dictation mode: small.en
is THE model — it produces BOTH the live partial text and the finals
(streaming, PRD §4.2quater) — and cuda_check's CPU fallback (P1.M1.T2.S1)
downgrades to tiny.en when no usable CUDA is found. Those are the only two
names the daemon can ever be told to load, so they are the only repos
prefetched.

This is INTERNAL install-time tooling (no user-facing surface). The only
documented caller is the CLI `python -m voice_typing.prefetch`, re-invoked
idempotently by install.sh (P1.M6.T1.S1) — snapshot_download skips blobs
whose cached etag already matches, so re-runs are free.

Repo IDs are VERIFIED against faster-whisper/utils.py _MODELS
(research_faster_whisper_cuda.md §1) and the live HF API
(research/huggingface_hub_prefetch_verification.md §3). Both are
CTranslate2 format (model.bin present), both owned by Systran/.

This module imports ONLY huggingface_hub (lazily, inside prefetch()), so
`import voice_typing.prefetch` triggers NO network call and needs NO CUDA
/ ctranslate2 / faster_whisper.
"""
from __future__ import annotations

import os
import sys

# Short name -> HF repo_id. The short-name KEYS match what RealtimeSTT passes
# (model=<cfg.asr.lite_model>, the ONE Rev 2 model) and what cuda_check.py
# returns (S1 contract: small.en on CUDA, tiny.en on the CPU-fallback path) —
# faster-whisper's _MODELS resolves them to these repo_ids. Keeping the keys
# aligned guarantees the daemon finds a cached weight for every name it can be
# told to load.
CORE_REPOS: dict[str, str] = {
    "small.en": "Systran/faster-whisper-small.en",  # THE single model (Rev 2): partials + finals
    "tiny.en": "Systran/faster-whisper-tiny.en",    # CPU fallback (cuda_check downgrade path)
}


def prefetch(short_to_repo: dict[str, str] | None = None) -> dict[str, str]:
    """Download each repo into the HF cache via huggingface_hub.snapshot_download.

    Args:
        short_to_repo: {short_name: hf_repo_id}. Defaults to CORE_REPOS (both Rev 2 repos).

    Returns:
        {short_name: local_snapshot_path} for each SUCCESSFULLY downloaded repo.

    Raises:
        Exception: re-raises whatever snapshot_download raises on the FIRST failing
        repo (the CLI catches per-repo so a single failure doesn't abort the rest).

    Defaults are load-bearing: cache_dir/local_dir/token stay None (so the weights
    land in the default ~/.cache/huggingface/hub that faster-whisper reads) and
    force_download stays False (idempotent re-runs). Do NOT set these (see Gotchas).
    """
    from huggingface_hub import snapshot_download  # lazy: keeps import-time side-effect-free

    if short_to_repo is None:
        short_to_repo = dict(CORE_REPOS)

    results: dict[str, str] = {}
    for short, repo_id in short_to_repo.items():
        print(f"\n=== [{short}] {repo_id} ===", flush=True)
        local_path = snapshot_download(repo_id=repo_id, repo_type="model")
        # local_path is a str: .../models--<owner>--<name>/snapshots/<rev>
        results[short] = local_path
        size = _model_bin_size(local_path)
        print(f"    -> {local_path}", flush=True)
        print(f"    model.bin: {_human_bytes(size)}" if size is not None
              else "    WARNING: model.bin NOT FOUND in snapshot", flush=True)
    return results


def _model_bin_size(snapshot_path: str) -> int | None:
    """Return model.bin size in bytes, or None if absent (signals a broken/partial repo)."""
    p = os.path.join(snapshot_path, "model.bin")
    try:
        return os.path.getsize(p)
    except OSError:
        return None


def _human_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def _main() -> int:
    """CLI: prefetch the CORE repos; report; exit 0 iff all succeeded.

    Exit 0 iff ALL CORE repos succeeded — any failure is fatal (the daemon
    cannot start without a model), so install.sh can run under `set -e`.
    """
    # Local-first: opt out of huggingface_hub's anonymous telemetry (no-op if already set).
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

    print("voice-typing model prefetch", flush=True)
    print("cache: ~/.cache/huggingface/hub (default — faster-whisper reads it)", flush=True)

    # CORE repos: any failure is fatal (the daemon cannot start without them).
    core_ok: list[str] = []
    core_fail: dict[str, str] = {}
    for short, repo_id in CORE_REPOS.items():
        try:
            prefetch({short: repo_id})
            core_ok.append(short)
        except Exception as exc:  # network / HTTP / disk errors
            core_fail[short] = f"{type(exc).__name__}: {exc}"
            print(f"\n!!! CORE FAIL [{short}] {repo_id}: {core_fail[short]}", file=sys.stderr, flush=True)

    # Summary. Sum model.bin sizes from the cache via a no-download re-resolve (local_files_only).
    total = 0
    for short in core_ok:
        repo_id = CORE_REPOS[short]
        sp = _local_snapshot(repo_id)
        total += (_model_bin_size(sp) or 0) if sp else 0

    print("\n=== summary ===", flush=True)
    print(f"core ok:    {core_ok or '(none)'}", flush=True)
    print(f"core FAIL:  {list(core_fail) or '(none)'}", flush=True)
    print(f"total model.bin bytes cached: {_human_bytes(total)}", flush=True)
    if core_fail:
        print(f"\nFAILED CORE repos — daemon cannot start until fixed: {list(core_fail)}", flush=True)
        return 1
    return 0


def _local_snapshot(repo_id: str) -> str | None:
    """Resolve the local snapshot path for a cached repo WITHOUT downloading (cache hit)."""
    from huggingface_hub import snapshot_download
    try:
        return snapshot_download(repo_id=repo_id, repo_type="model", local_files_only=True)
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(_main())
