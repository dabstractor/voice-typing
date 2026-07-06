# Research Note: uv Dependency-Resolution Findings for S2 (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED on this exact machine (uv 0.7.11, Python 3.12.10, RTX 3080 Ti, July 6 2026).
**Method:** throwaway `uv init --bare` dirs under `/tmp`. The voice-typing project itself was NOT modified.
**Purpose:** de-risk the S2 `uv sync` / `uv add torch --index cu126` steps by pinning down exact uv 0.7.11 behavior the contract relies on.

---

## Finding 1 — `uv add <pkg> --index <url>` writes an ANONYMOUS, NON-EXCLUSIVE index to pyproject.toml

Probe: `uv add six --index https://download.pytorch.org/whl/cu126` (six = tiny/fast).

Resulting `pyproject.toml` diff (uv 0.7.11):

```toml
[project]
...
dependencies = [
    "six>=1.17.0",
]

[[tool.uv.index]]
url = "https://download.pytorch.org/whl/cu126"
```

- It appends the package to `[project] dependencies` (with a `>=` lower bound).
- It appends a `[[tool.uv.index]]` table with ONLY `url =` — **no `name`, no `explicit = true`, no `[tool.uv.sources]` entry.**
- Consequence: the index is GLOBAL/non-exclusive. uv MAY consult `download.pytorch.org/whl/cu126` when resolving ANY package (e.g. the `nvidia-*` CUDA wheels), not just `torch`. Usually harmless (the pytorch index 404s for non-torch packages and uv falls back to PyPI), but it can pull `nvidia-*-cu12` wheels from the pytorch index at versions that differ from PyPI's.

**Contract implication:** the contract's command `/home/dustin/.local/bin/uv add torch --index https://download.pytorch.org/whl/cu126` (only run on the `torch.cuda.is_available()==False` branch) will (a) add `torch` to `[project] dependencies`, and (b) add the anonymous `[[tool.uv.index]]`. This **MODIFIES the `pyproject.toml` that S1 authored** — expected, conditional on the fallback path only.

**Escape hatch** (if the anonymous index causes a resolution conflict with the pinned `nvidia-cudnn-cu12==9.*` or shifts a `nvidia-*` version): replace the anonymous block with an EXPLICIT named index + a source mapping so ONLY `torch` resolves from it:

```toml
[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true            # restricts this index to packages that source from it

[tool.uv.sources]
torch = { index = "pytorch-cu126" }
```

This is the recommended hardened form if the contract's plain `--index` command mis-resolves.

---

## Finding 2 — Large CUDA wheels exceed uv's DEFAULT 30s HTTP timeout (set UV_HTTP_TIMEOUT)

Full (non-dry-run) `uv add torch --index https://download.pytorch.org/whl/cu126` FAILED mid-download with:

```
× Failed to download `nvidia-cuda-nvrtc-cu12==12.6.85`
├─▶ Failed to extract archive: ...whl
╰─▶ Failed to download distribution due to network timeout.
   Try increasing UV_HTTP_TIMEOUT (current value: 30s).
```

- This is **NOT a resolution error** — the packages resolve correctly. uv's per-file HTTP timeout (30s default) is too short for multi-hundred-MB CUDA wheels on a flaky link.
- **FIX:** `export UV_HTTP_TIMEOUT=600` (or per-command prefix `UV_HTTP_TIMEOUT=600 ...`) before `uv sync` / `uv add`. uv honors the env var (`uv --help`: `[env: UV_HTTP_TIMEOUT=]`).
- Side observation that VALIDATES the research: the cu126-torch download pulled `nvidia-curand-cu12`, `nvidia-cusolver-cu12`, `nvidia-cusparse-cu12`, `nvidia-nvjitlink-cu12`, `nvidia-cuda-nvrtc-cu12`, `nvidia-cuda-cupti-cu12` — **ALL cu12**. So cu126 torch's CUDA deps are cu12-family and cohabit cleanly with S1's explicit `nvidia-cublas-cu12` + `nvidia-cudnn-cu12==9.*`.

---

## Finding 3 — Network reachability CONFIRMED (July 6 2026)

- `curl -sI https://download.pytorch.org/whl/cu126/torch/` → **HTTP/2 200**, `last-modified: Mon, 06 Jul 2026 22:33:35 GMT`. The cu126 index is LIVE and current (updated today).
- `curl -sI https://pypi.org/simple/realtimestt/` → **HTTP/2 200**. PyPI reachable.

→ S2 can proceed online; the cu126 fallback target is reachable.

---

## Finding 4 — `uv sync` builds the project package and creates console-script wrappers (inherited from S1)

Confirmed by S1's empirical research (`P1M1T1S1/research/uv_build_system_verification.md`): with `[build-system]` hatchling present (S1's contract), `uv sync` builds `voice_typing` and creates `.venv/bin/voicectl` + `.venv/bin/voice-typing-daemon`. The target modules (`voice_typing/ctl.py`, `voice_typing/daemon.py`) do NOT exist yet (P1.M4/M5) — the wrappers are created but **error only at RUNTIME** (lazy entry-point resolution).

→ S2 should **VERIFY the wrappers EXIST**, not that they run. A wrapper that errors with `ModuleNotFoundError: voice_typing.ctl` at this stage is EXPECTED and correct.

---

## Finding 5 — cu12 vs cu13 nvidia wheels coexist (version-suffixed sonames)

`nvidia-cublas-cu12` installs `libcublas.so.12`; a hypothetical `nvidia-cublas-cu13` (transitively from cu130 PyPI-default torch, if any) installs `libcublas.so.13`. They coexist under `site-packages/nvidia/cublas/lib/` via version-suffixed sonames — **no file overwrite**. ctranslate2 links `libcublas.so.12`; torch cu130 links `libcublas.so.13`.

→ The runtime LD_LIBRARY_PATH scoping (point the daemon at the cu12 dirs) is **T2's concern** (launch_daemon.sh, P1.M1.T2.S1), NOT S2's. S2's gates are independent per-library smoke checks (`import ctranslate2; get_cuda_device_count()` and `import torch; cuda.is_available()`).

---

## Finding 6 — `uv add --no-build` does NOT skip wheel downloads

`--no-build` only suppresses building from SOURCE distributions; pre-built wheels are STILL downloaded. It cannot be used to "record the pyproject config without downloading." uv's suggested `--frozen` skips locking/syncing but is NOT guaranteed to write the dep entry for `uv add` — do NOT rely on it.

→ For S2 there is no shortcut: the full multi-GB CUDA download must complete (with `UV_HTTP_TIMEOUT=600`).

---

## Finding 7 — lockfile verification commands available in uv 0.7.11

- `uv lock --check` → "Check if the lockfile is up-to-date" (fails non-zero if `uv.lock` would change). `[env: UV_LOCKED=]`.
- `uv lock --check-exists` → "Assert that a `uv.lock` exists without checking if it is up-to-date". `[env: UV_FROZEN=]`.

→ S2's lockfile gate = `uv lock --check` (authoritative: lockfile matches pyproject.toml). Lightweight existence gate = `uv lock --check-exists`.

---

## SUMMARY (what S2 can rely on)

1. ✅ `uv sync` against S1's pyproject builds voice_typing + creates the 2 console-script wrappers (verify existence, not runtime).
2. ✅ cu126 index is live/reachable; cu126 torch pulls cu12-family nvidia wheels (cohabits with S1's cu12 pins).
3. ⚠️ MUST set `UV_HTTP_TIMEOUT=600` before `uv sync`/`uv add` or large CUDA wheels time out at the 30s default.
4. ⚠️ `uv add torch --index <url>` writes an anonymous non-exclusive `[[tool.uv.index]]` + adds `torch` to deps (modifies S1's pyproject). Escape hatch = explicit `name`+`explicit=true`+`[tool.uv.sources]`.
5. ✅ `uv lock --check` asserts the generated lockfile is in sync with pyproject (S2's lockfile gate).
6. ✅ cu12/cu13 nvidia libs coexist via soname versioning; runtime LD_LIBRARY_PATH is T2, not S2.
7. ✅ No shortcut to avoid the full download.
