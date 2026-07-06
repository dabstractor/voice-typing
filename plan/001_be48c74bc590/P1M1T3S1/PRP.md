# PRP — P1.M1.T3.S1: Model prefetch script + run download

## Goal

**Feature Goal**: Produce `voice_typing/prefetch.py` — an importable + CLI module that calls `huggingface_hub.snapshot_download(repo_id=...)` for the 3 core faster-whisper CTranslate2 model repos (`Systran/faster-distil-whisper-large-v3`, `Systran/faster-whisper-small.en`, `Systran/faster-whisper-tiny.en`) and the approved substitute (`mobiuslabsgmbh/faster-whisper-large-v3-turbo`), populating `~/.cache/huggingface/hub` so the daemon's `AudioToTextRecorder` construction (P1.M4.T1.S1) is instant. It prints per-repo progress + post-download verification (stat each `model.bin`) and is **idempotent** (re-runs skip already-cached blobs) so `install.sh` (P1.M6.T1.S1) can re-invoke it cheaply. **Mock nothing — this performs the real ~1.8 GB core download (≈3.4 GB with turbo) on this machine now.**

**Deliverable** (exactly three artifacts):
1. `voice_typing/prefetch.py` — the importable + CLI module (verbatim code in Implementation Blueprint → Task 2).
2. **Populated HF cache** — `~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/`, `.../models--Systran--faster-whisper-small.en/`, `.../models--Systran--faster-whisper-tiny.en/` (core, REQUIRED) + `.../models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/` (optional). Produced by **running** `python -m voice_typing.prefetch`.
3. `plan/001_be48c74bc590/P1M1T3S1/prefetch_results.md` — a recorded run log: per-repo snapshot path, `model.bin` size, total bytes, pass/fail per repo (core must pass; turbo failure recorded as a warning).

**Success Definition**:
- (a) `voice_typing/prefetch.py` exists, parses (`py_compile`), and `python -c "import voice_typing.prefetch"` succeeds and triggers **no network call** (the `snapshot_download` import + call are local to the function).
- (b) Public API: `prefetch(short_to_repo: dict[str,str] | None = None) -> dict[str,str]` returning `{short_name: local_snapshot_path}` for successfully downloaded repos; module constants `CORE_REPOS` (3 entries) + `OPTIONAL_REPOS` (1 entry: `large-v3-turbo → mobiuslabsgmbh/...`).
- (c) `python -m voice_typing.prefetch` downloads the 3 CORE repos + turbo, prints `=== [<short>] <repo_id> ===` headers, the resolved snapshot path per repo, and a per-repo `model.bin` size line; exits 0 iff all CORE repos succeeded (turbo failure is a non-fatal warning).
- (d) **No mocking.** A real network download runs now (research verified HF is reachable, 237 GB free disk). After it, each repo's snapshot dir contains `model.bin` + `config.json` + `tokenizer.json` + the vocabulary file.
- (e) **Idempotent:** a second `python -m voice_typing.prefetch` run completes in seconds (no re-download; `snapshot_download` defaults to `force_download=False`).
- (f) prefetch.py imports ONLY `huggingface_hub` (NOT ctranslate2/faster_whisper/torch) — so the task is **independent of T2.S2** (which may still be installing ctranslate2). No CUDA, no LD_LIBRARY_PATH.
- (g) No out-of-scope artifacts (no `daemon.py`, no recorder construction, no `install.sh`, no `pyproject.toml` edit, no systemd unit, no `[project.scripts]` entry).

## User Persona

Not applicable (developer/agent-facing install-time tooling; no end-user surface — DOCS: "none — internal tooling"). The only documented caller is `install.sh` (P1.M6.T1.S1), which re-invokes `python -m voice_typing.prefetch` idempotently.

## Why

- **Construction latency = the first-run UX cliff.** RealtimeSTT's `AudioToTextRecorder` lazily loads the model via faster-whisper's `WhisperModel(size_or_path)`, which resolves the short name to a HF repo_id and pulls it into the cache **on first construction**. If the cache is empty, the daemon's first start blocks on a multi-GB download (distil-large-v3 alone is ≈1.5 GB). Prefetching NOW means daemon construction (P1.M4.T1.S1) is instant and the systemd service starts cleanly. (PRD §4.4: "First construction downloads models to `~/.cache/huggingface`. `install.sh` MUST prefetch ... so first real run is instant.")
- **100% local at runtime.** The PRD's headline requirement. With all four repos prefetched, the daemon + the CPU-fallback path + the turbo-substitute path are ALL on disk — no network at runtime, no fallback needs a surprise download. (system_context.md §1: "100% local at runtime.")
- **Reused by install.sh (one source of truth).** `install.sh` (P1.M6.T1.S1) re-invokes `python -m voice_typing.prefetch` rather than re-implementing the repo list. Keeping the repo IDs + download logic in ONE module (`prefetch.py`) means the repo list can never drift between "the dev-time download" and "the install.sh download". Idempotency (`snapshot_download` default `force_download=False`) makes the re-invocation free.
- **Decoupled from CUDA state.** Prefetch only moves bytes into the HF cache — it needs `huggingface_hub` (installed, v1.22.0) and NOTHING CUDA-related. So it can run and succeed whether or not T2.S2 has landed ctranslate2. The cached weights only become *loadable* once ctranslate2 arrives, but the cache-population step has no CUDA dependency. This is the clean parallel boundary.

## What

Create `voice_typing/prefetch.py` (verbatim source in Implementation Blueprint → Task 2): a module with two module-level repo dicts (`CORE_REPOS`, `OPTIONAL_REPOS`), a `prefetch()` function that iterates and calls `snapshot_download`, and a `__main__` CLI that downloads CORE (always) + OPTIONAL (turbo), verifies each `model.bin`, prints a summary, and writes/returns results. Then **run** `python -m voice_typing.prefetch` and **record** the result into `prefetch_results.md`.

### Success Criteria

- [ ] `voice_typing/prefetch.py` exists and `python -m py_compile voice_typing/prefetch.py` exits 0.
- [ ] `python -c "import voice_typing.prefetch as m; print(m.CORE_REPOS, m.OPTIONAL_REPOS, m.prefetch)"` succeeds with NO network activity (the `huggingface_hub` import + `snapshot_download` call are inside the function).
- [ ] `CORE_REPOS` == `{"distil-large-v3": "Systran/faster-distil-whisper-large-v3", "small.en": "Systran/faster-whisper-small.en", "tiny.en": "Systran/faster-whisper-tiny.en"}`.
- [ ] `OPTIONAL_REPOS` == `{"large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo"}` (DIFFERENT owner than Systran — the trap-avoidance).
- [ ] `python -m voice_typing.prefetch` downloads all 4 repos; each repo's snapshot dir contains `model.bin` + `config.json` + `tokenizer.json` + a vocabulary file (`vocabulary.json` or `vocabulary.txt`).
- [ ] The script exits 0 (all CORE + turbo succeed on this host; network verified reachable, disk ample).
- [ ] Re-running `python -m voice_typing.prefetch` completes in seconds (no re-download) — idempotency.
- [ ] prefetch.py does NOT import `ctranslate2`/`faster_whisper`/`torch` anywhere (grep clean).
- [ ] prefetch.py does NOT set `LD_LIBRARY_PATH`, `cache_dir`, `local_dir`, or `token` (defaults are correct; setting them breaks faster-whisper's auto-resolution).
- [ ] `prefetch.py` is NOT added to `[project.scripts]` (the `-m` invocation is the CLI).
- [ ] `plan/001_be48c74bc590/P1M1T3S1/prefetch_results.md` exists, records per-repo snapshot path + `model.bin` size + total + pass/fail, and matches a fresh run.
- [ ] No `daemon.py`, no recorder construction, no `install.sh`, no `systemd/`, no `pyproject.toml`/`PRD.md`/`tasks.json`/`.gitignore` changes.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement T3.S1 from this PRP + the referenced research. The full module source is given verbatim; every `snapshot_download` parameter + return + idempotency behavior is documented against huggingface_hub 1.22.0 (verified live); the exact repo IDs + file inventories are verified against the live HF API; and the network/disk preconditions are confirmed on this machine.

### Documentation & References

```yaml
# MUST READ — the authoritative repo IDs + the prefetch pattern (the source of this task's contract)
- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md
  why: "§1 is the verified repo-ID table (sourced from faster-whisper/utils.py _MODELS): short name →
        HF repo_id. §5 gives the prefetch code pattern: snapshot_download(repo_id=repo) →
        ~/.cache/huggingface/hub; 'Systran + mobiuslabsgmbh repos are public, ungated — no HF auth
        token needed.' §6: huggingface_hub>=0.23 is faster-whisper's requirement (satisfied: 1.22.0)."
  critical: "§1's BIG WARNING: do NOT prefetch distil-whisper/distil-large-v3 (raw PyTorch checkpoint,
             won't load in CTranslate2). The CT2 weights are under Systran/ (faster-distil-...) and
             turbo under mobiuslabsgmbh/. The repo IDs in CORE_REPOS/OPTIONAL_REPOS are CORRECT —
             do not 'correct' the owner."

# MUST READ — the live-verified API + repo inventories (this task's own research; load-bearing)
- docfile: plan/001_be48c74bc590/P1M1T3S1/research/huggingface_hub_prefetch_verification.md
  why: "§2: snapshot_download signature verified for huggingface_hub 1.22.0 — the load-bearing params
        are repo_id (required), cache_dir/local_dir/token/force_download (ALL default; DO NOT set),
        max_workers=8, tqdm per-file bars auto-render. Returns the local snapshot path (str).
        §3: live repo inventories — all 4 repos are CTranslate2 (model.bin present, NO pytorch
        weights); the distil-whisper/distil-large-v3 TRAP confirmed (27 files, no model.bin).
        §4: cache layout + how the daemon consumes it (why cache_dir MUST stay default).
        §6: the 9 locked design decisions (CORE vs OPTIONAL, error semantics, verify model.bin, etc.)."
  section: "§2 (API), §3 (inventories + the trap), §4 (cache consumption), §6 (design). All load-bearing."

# Background — how the daemon consumes the prefetched cache (so the short-name → repo_id mapping is right)
- docfile: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§1 confirms AudioToTextRecorder kwargs model= (final, accepts short name 'distil-large-v3') and
        realtime_model_type= (realtime, accepts 'small.en'); faster-whisper resolves the SHORT name to
        the repo_id internally. So prefetch.py keys dicts by the SHORT NAME (matches what the daemon
        passes) and stores the repo_id as the value (what snapshot_download needs)."
  critical: "The daemon passes SHORT NAMES ('distil-large-v3','small.en'); faster-whisper's _MODELS
             maps them to the repo_ids we prefetch. Do not change the short-name keys."

# Background — machine facts (READ-ONLY)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: shell aliases → ALWAYS full paths (.venv/bin/python, /home/dustin/.local/bin/uv). Python 3.12.
        '100% local at runtime' (the ethos prefetch serves). §4 decision #8: the exact repo IDs (this
        task's source of truth, matching research_faster_whisper_cuda.md §1)."
  critical: "Use .venv/bin/python explicitly; never bare python/uv. Python 3.12 → PEP 604 `X | None`
             unions are fine in annotations with `from __future__ import annotations`."

# Background — the upstream decision module whose MODEL NAMES this prefetch must match
- file: plan/001_be48c74bc590/P1M1T2S2/PRP.md
  why: "cuda_check.py defines CUDA_DEFAULTS = {final_model:'distil-large-v3', realtime_model:'small.en'}
        and CPU_FALLBACK = {final_model:'small.en', realtime_model:'tiny.en'}. prefetch.py MUST cache
        exactly these short names (distil-large-v3, small.en, tiny.en) + the approved substitute
        (large-v3-turbo) so both the CUDA path and the CPU-fallback path are on disk. The repo-id
        mapping in prefetch.py is the materialization of those short names."
  critical: "If prefetch.py's CORE_REPOS short-name keys ever drift from cuda_check's model names, a
             fallback or substitute path would trigger a runtime download. Keep them identical."

# Downstream — the consumer that turns this into an instant daemon start
- file: PRD.md
  why: "§4.4: 'First construction downloads models to ~/.cache/huggingface. install.sh MUST prefetch
        ... so first real run is instant.' §3 model decision (distil-large-v3 final, small.en realtime,
        large-v3-turbo substitute). §5 step 6: 'Prefetch models' is an explicit install step."
  critical: "This task IS the §4.4/§5 prefetch. The 'substitute if distil downloads/runs poorly' is
             why we ALSO prefetch large-v3-turbo (the substitute must already be local if needed)."
```

### Current Codebase tree (S1 + T2.S1 + T2.S2 done; S2 (ctranslate2) + T3.S1 in progress — the state at T3.S1 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*'` from repo root. Expected:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores .venv, __pycache__, dist/, build/ (DO NOT touch)
├── .venv/                      # Python 3.12.10
│   │                             AT T3.S1 TIME: huggingface_hub==1.22.0 IS installed (verified).
│   │                             ctranslate2 / faster_whisper are NOT installed yet (T2.S2 in
│   │                             progress) — IRRELEVANT to prefetch (only huggingface_hub needed).
│   └── bin/python              # the python the prefetch runs under
├── PRD.md                      # READ-ONLY
├── pyproject.toml              # ← S1's output (4 deps incl. huggingface_hub>=0.23) — UNCHANGED by T3.S1
├── uv.lock                     # S2's output (may exist) — UNCHANGED by T3.S1
└── voice_typing/
    ├── __init__.py             # ← S1's output (module docstring)
    ├── launch_daemon.sh        # ← T2.S1's output (LD_LIBRARY_PATH wrapper — NOT used by prefetch)
    └── cuda_check.py           # ← T2.S2's output (the decision module; defines the short names we cache)
# NO voice_typing/prefetch.py yet — T3.S1 creates it (the only new SOURCE file).
# prefetch_results.md is created by RUNNING the script (under plan/001.../P1M1T3S1/).
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── prefetch.py             # ← CREATE (the importable + CLI module; the only new SOURCE file)
plan/001_be48c74bc590/P1M1T3S1/
└── prefetch_results.md         # ← CREATE (recorded run log; produced by RUNNING the script)
# SIDE EFFECT (not a repo file): ~/.cache/huggingface/hub/models--Systran--faster-distil-whisper-large-v3/
#   (+ small.en, tiny.en, mobiuslabsgmbh large-v3-turbo). This is the DELIVERABLE cache. It is NOT
#   committed (it's a machine-local cache, gitignored-by-nature — lives outside the repo).
# NOTHING ELSE. daemon.py is P1.M4.T3.S1; recorder wiring is P1.M4.T1.S1; install.sh/systemd are P1.M6;
# pyproject edits are S2's job (NOT T3.S1). prefetch.py is NOT added to [project.scripts] (the `-m`
# invocation is the CLI; install.sh calls `python -m voice_typing.prefetch` — see Anti-Patterns).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT SET cache_dir / local_dir / token / force_download.
# snapshot_download's DEFAULTS are exactly what faster-whisper expects: cache_dir=None →
# HF_HUB_CACHE (~/.cache/huggingface/hub), local_dir=None → snapshot symlink layout under that cache.
# faster-whisper's WhisperModel resolves the repo_id via huggingface_hub's DEFAULT cache lookup. If you
# set cache_dir or local_dir, the weights land somewhere faster-whisper won't auto-find → the daemon
# re-downloads at construction (defeating the entire prefetch). token=None is correct (repos are public).
# force_download=False (default) is the idempotency install.sh relies on — DO NOT set True.
# (research/huggingface_hub_prefetch_verification.md §2, §4.)

# CRITICAL #2 — DOWNLOAD WHOLE REPOS (no allow_patterns / ignore_patterns).
# Each repo's file set is tiny except model.bin, and EVERY other file is load-bearing: config.json,
# tokenizer.json, the vocabulary file (vocabulary.json for distil-large-v3/large-v3-turbo;
# vocabulary.txt for small.en/tiny.en), and preprocessor_config.json (distil-large-v3/turbo only).
# Excluding any of them → WhisperModel construction fails. The .gitattributes + README.md are harmless.
# snapshot_download(repo_id=...) with no patterns fetches exactly the right set. (Research §3.)

# CRITICAL #3 — THE REPO-ID OWNER TRAP. CORE/OPTIONAL repos use THREE different owners:
#   distil-large-v3 / small.en / tiny.en  → Systran/
#   large-v3-turbo                        → mobiuslabsgmbh/   (NOT Systran!)
# Do NOT "normalize" the turbo owner to Systran (no such repo). Do NOT swap distil-large-v3 to
# distil-whisper/distil-large-v3 (raw PyTorch, 27 files, NO model.bin — CTranslate2 can't load it).
# The repo IDs in CORE_REPOS/OPTIONAL_REPOS are VERIFIED CORRECT (live HF probe, research §3).
# (research_faster_whisper_cuda.md §1 WARNING; system_context.md §4 decision #8.)

# CRITICAL #4 — prefetch.py MUST NOT import ctranslate2/faster_whisper/torch.
# Only `huggingface_hub` is needed to move bytes. A top-level `import ctranslate2` would make
# `import voice_typing.prefetch` raise while T2.S2 is still installing ctranslate2. Keep the
# `from huggingface_hub import snapshot_download` INSIDE the prefetch() function (lazy import), so
# `import voice_typing.prefetch` (and the module-constant access) never touches the network or any
# heavy dep. This mirrors cuda_check.py's lazy-import discipline (Gotcha #2 there).
# (research §1: T3.S1 is independent of T2.S2; research §6 decision #7.)

# CRITICAL #5 — NO LD_LIBRARY_PATH, NO CUDA. prefetch.py runs with plain `.venv/bin/python`. It does
# NOT need launch_daemon.sh's wrapper (that's for the daemon's cuDNN load, irrelevant to file download).
# Do NOT source launch_daemon.sh, do NOT compute nvidia lib dirs. Running prefetch under the wrapper
# would be harmless but pointless and confusing. (cuda_check.py PRP Gotcha #1; research §6 decision #8.)

# GOTCHA #6 — THE DOWNLOAD IS REAL AND MULTI-MINUTE. core ≈1.8 GB (distil-large-v3 ≈1.5 GB dominates),
# turbo ≈1.6 GB extra. On a typical connection this is minutes, not seconds. The PRP's Validation L3
# runs it for real (mock nothing). The implementer should let it run to completion (do not set a short
# timeout). huggingface_hub's tqdm renders per-file progress bars to stderr automatically — if you see
# no bars, stderr may be redirected; the stdout `=== [<short>] <repo> ===` headers still show progress.
# (Research §3 sizes; contract "Run it now".)

# GOTCHA #7 — IDEMPOTENCY IS THE INSTALL.SH CONTRACT. snapshot_download(force_download=False) (default)
# re-checks etags and skips present blobs. A second `python -m voice_typing.prefetch` run must complete
# in seconds with no re-download. Validation L5 verifies this. install.sh (P1.M6.T1.S1) re-invokes this
# module and relies on it being free. Do NOT add a `force_download=True` default or a `--force` flag that
# install.sh might trip over. (Research §2, §5; PRD §4.4.)

# GOTCHA #8 — EXIT-CODE SEMANTICS. Exit 0 iff all CORE repos succeeded (distil-large-v3, small.en,
# tiny.en — the daemon cannot start without them). A turbo (OPTIONAL) failure is a WARNING, not fatal:
# record it, continue, exit 0 if core is OK. This lets install.sh `python -m voice_typing.prefetch` under
# `set -e` without aborting on a substitute-model hiccup. (Research §6 decision #4.)

# GOTCHA #9 — VERIFY model.bin AFTER DOWNLOAD (catch partial repos). For each repo, stat
# <snapshot_path>/model.bin and print its size. A repo whose download silently produced only
# config.json/tokenizer.json (e.g., model.bin interrupted) would make the daemon fail at construction
# with a confusing "file not found" — the size line surfaces it immediately at prefetch time. Cheap and
# high-signal. (Research §6 decision #5.)

# GOTCHA #10 — DO NOT ADD prefetch TO [project.scripts]. The CLI is `python -m voice_typing.prefetch`
# (matches cuda_check.py's `-m` convention). A console-script entry would require editing pyproject.toml
# (S1's output — out of scope) + a re-sync. install.sh calls `-m`. (cuda_check.py PRP Gotcha #11; S1 PRP
# Gotcha #2.)

# GOTCHA #11 — PYTHON 3.12 + `from __future__ import annotations`. Use it so `dict[str, str] | None`
# annotations are stringized (valid on 3.12). `sys`, `os`, `pathlib` are stdlib. Do not use 3.13-only
# syntax. (system_context.md §1; cuda_check.py PRP Gotcha #10.)

# GOTCHA #12 — FULL PATHS in every bash CALL. This machine aliases python3→uv run, pip→alias, tmux→zsh
# plugin. Invoke `.venv/bin/python` and `/home/dustin/.local/bin/uv` explicitly. Never bare python/uv.
# (system_context.md §1.)

# GOTCHA #13 — HF_HUB_DISABLE_TELEMETRY. Set os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY","1") at the
# top of _main(). huggingface_hub sends anonymous telemetry by default; a local-first tool should opt
# out. setdefault() respects a user-provided value. (system_context.md §1 "100% local" ethos.)

# GOTCHA #14 — SNAPSHOT PATH IS A STR (not pathlib.Path). snapshot_download returns a str. Join with
# os.path / pathlib as needed. The returned path is the resolved snapshot dir containing symlinks into
# blobs/ — model.bin is directly under it. (Research §2 return value, §4 layout.)
```

## Implementation Blueprint

### Data models and structure

No ORM / pydantic. The "data model" is two plain-dict module constants (short name → repo_id) and the
`prefetch()` return shape (`{short_name: snapshot_path}`). Plain dicts (not a dataclass) keep the
module dependency-free and match the contract's `-> dict`. The short-name keys are deliberately the
REALTIMESTT/faster-whisper short names (`distil-large-v3`, `small.en`, `tiny.en`, `large-v3-turbo`)
so they align with `cuda_check.py`'s `final_model`/`realtime_model` values.

```python
# Module-level repo registry — short name → HF repo_id (VERIFIED, research §3).
CORE_REPOS: dict[str, str] = {
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",  # FINAL (CUDA default)
    "small.en":        "Systran/faster-whisper-small.en",          # REALTIME/partials (+ CPU-fallback FINAL)
    "tiny.en":         "Systran/faster-whisper-tiny.en",           # CPU-fallback REALTIME
}
OPTIONAL_REPOS: dict[str, str] = {
    "large-v3-turbo":  "mobiuslabsgmbh/faster-whisper-large-v3-turbo",  # approved FINAL substitute
}
# Return contract of prefetch(): {short_name: local_snapshot_path(str)} for each SUCCESSFUL repo.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the input dependency + that the target file does not yet exist (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/__init__.py && echo "ok: voice_typing/ package exists (S1)" \
        || echo "PREFLIGHT FAIL: voice_typing/ missing"
      test ! -e voice_typing/prefetch.py && echo "ok: prefetch.py not yet created" \
        || echo "PREFLIGHT FAIL: prefetch.py already exists"
      test -x .venv/bin/python && echo "ok: .venv/bin/python exists" \
        || echo "PREFLIGHT FAIL: .venv/bin/python missing"
      # THE LOAD-BEARING INPUT: huggingface_hub must be importable (it's the ONLY dep prefetch needs):
      .venv/bin/python -c "import huggingface_hub; print('huggingface_hub', huggingface_hub.__version__)" \
        && echo "ok: huggingface_hub importable (INPUT satisfied)" \
        || echo "PREFLIGHT FAIL: huggingface_hub NOT importable — cannot prefetch"
      # Informational (NOT a blocker): ctranslate2/faster_whisper state (T2.S2 may be in progress).
      # Prefetch does NOT need them — this is just a note for the results log:
      .venv/bin/python -c "import ctranslate2" 2>/dev/null && echo "note: ctranslate2 present (T2.S2 done)" \
        || echo "note: ctranslate2 NOT yet present (T2.S2 in progress) — IRRELEVANT to prefetch"
      # Network + disk preconditions (should pass on this host; verifies the real download can run):
      .venv/bin/python -c "from huggingface_hub import HfApi; print('HF reachable, tiny.en files:', len(HfApi().repo_info('Systran/faster-whisper-tiny.en').siblings))" \
        && echo "ok: HF reachable" || echo "WARN: HF not reachable — the real download in Task 3 may fail"
      df -h ~/.cache/huggingface | tail -1
  - EXPECTED: voice_typing/ exists; prefetch.py absent; .venv/bin/python present; huggingface_hub 1.22.0
    importable; HF reachable; ≥3 GB free on /home (237 GB expected). The ctranslate2 line is informational.
  - DO NOT: create daemon.py, edit pyproject.toml, run uv sync/add, or install anything.

Task 2: CREATE voice_typing/prefetch.py (use the `write` tool with EXACTLY the content below)
  - FILE: voice_typing/prefetch.py
  - CONTENT (verbatim — see "why each part" after):
    ----- BEGIN voice_typing/prefetch.py -----
    """Pre-download faster-whisper CTranslate2 models into the HF cache.

    Populates ~/.cache/huggingface/hub so the daemon's AudioToTextRecorder
    construction (P1.M4.T1.S1) is instant: RealtimeSTT/faster-whisper resolve
    the short model names to these HF repo_ids and find the weights already
    cached. With all four repos local, the CUDA path (distil-large-v3 +
    small.en), the CPU-fallback path (small.en + tiny.en), AND the approved
    substitute (large-v3-turbo) are all on disk — no network at runtime.

    This is INTERNAL install-time tooling (no user-facing surface). The only
    documented caller is the CLI `python -m voice_typing.prefetch`, re-invoked
    idempotently by install.sh (P1.M6.T1.S1) — snapshot_download skips blobs
    whose cached etag already matches, so re-runs are free.

    Repo IDs are VERIFIED against faster-whisper/utils.py _MODELS
    (research_faster_whisper_cuda.md §1) and the live HF API
    (research/huggingface_hub_prefetch_verification.md §3). All four are
    CTranslate2 format (model.bin present). NOTE the three different owners:
    Systran/ (distil-large-v3, small.en, tiny.en) and mobiuslabsgmbh/ (turbo).
    Do NOT prefetch distil-whisper/distil-large-v3 (raw PyTorch — CTranslate2
    cannot load it).

    This module imports ONLY huggingface_hub (lazily, inside prefetch()), so
    `import voice_typing.prefetch` triggers NO network call and needs NO CUDA
    / ctranslate2 / faster_whisper — it can run (and this task can complete)
    before T2.S2 installs ctranslate2.
    """
    from __future__ import annotations

    import os
    import sys

    # Short name -> HF repo_id. The short-name KEYS match what RealtimeSTT passes
    # (model="distil-large-v3", realtime_model_type="small.en", ...) and what
    # cuda_check.py returns (final_model/realtime_model) — faster-whisper's _MODELS
    # resolves them to these repo_ids. Keeping the keys aligned guarantees the
    # daemon finds a cached weight for every name it can be told to load.
    CORE_REPOS: dict[str, str] = {
        "distil-large-v3": "Systran/faster-distil-whisper-large-v3",  # FINAL model (CUDA default)
        "small.en": "Systran/faster-whisper-small.en",  # REALTIME/partials (also CPU-fallback FINAL)
        "tiny.en": "Systran/faster-whisper-tiny.en",  # CPU-fallback REALTIME (degraded mode)
    }

    OPTIONAL_REPOS: dict[str, str] = {
        # Approved FINAL substitute (PRD §3: "if distil-large-v3 downloads/runs poorly").
        # DIFFERENT owner (mobiuslabsgmbh, NOT Systran) — the trap-avoidance.
        "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    }


    def prefetch(short_to_repo: dict[str, str] | None = None) -> dict[str, str]:
        """Download each repo into the HF cache via huggingface_hub.snapshot_download.

        Args:
            short_to_repo: {short_name: hf_repo_id}. Defaults to CORE+OPTIONAL (all four).

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
            short_to_repo = {**CORE_REPOS, **OPTIONAL_REPOS}

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
        """CLI: prefetch CORE (required) + OPTIONAL (turbo); report; exit by core success.

        Exit 0 iff ALL CORE repos succeeded. OPTIONAL (turbo) failures are WARNINGS —
        recorded and skipped, never fatal — so install.sh can run under `set -e`.
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

        # OPTIONAL repos: failures are warnings, never fatal.
        opt_ok: list[str] = []
        opt_fail: dict[str, str] = {}
        for short, repo_id in OPTIONAL_REPOS.items():
            try:
                prefetch({short: repo_id})
                opt_ok.append(short)
            except Exception as exc:
                opt_fail[short] = f"{type(exc).__name__}: {exc}"
                print(f"\n!!! OPTIONAL warn [{short}] {repo_id}: {opt_fail[short]}", file=sys.stderr, flush=True)

        # Summary. Sum model.bin sizes from the cache via a no-download re-resolve
        # (local_files_only=True → cache hit; robust even if a repo partially downloaded earlier).
        total = 0
        for short in core_ok + opt_ok:
            repo_id = {**CORE_REPOS, **OPTIONAL_REPOS}[short]
            sp = _local_snapshot(repo_id)
            total += (_model_bin_size(sp) or 0) if sp else 0

        print("\n=== summary ===", flush=True)
        print(f"core ok:    {core_ok or '(none)'}", flush=True)
        print(f"core FAIL:  {list(core_fail) or '(none)'}", flush=True)
        print(f"opt  ok:    {opt_ok or '(none)'}", flush=True)
        print(f"opt  warn:  {list(opt_fail) or '(none)'}", flush=True)
        print(f"total model.bin bytes cached: {_human_bytes(total)}", flush=True)
        if core_fail:
            print(f"\nFAILED CORE repos — daemon cannot start until fixed: {list(core_fail)}", flush=True)
            return 1
        if opt_fail:
            print("\nNOTE: optional (turbo) repo failed — the substitute path is not cached.", flush=True)
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
    ----- END voice_typing/prefetch.py -----
  - WHY each part:
      * module docstring: states the purpose (instant construction), the idempotent install.sh reuse,
        the verified repo IDs + the three-owner trap + the distil-whisper trap, and the decoupling from
        CUDA/ctranslate2 (so the implementer knows it can run before T2.S2).
      * `from __future__ import annotations`: stringizes `dict[str, str] | None` (3.12-safe). (Gotcha #11.)
      * `CORE_REPOS` / `OPTIONAL_REPOS`: verified repo IDs; short-name KEYS align with cuda_check's
        model names (Gotcha: scope coupling) + RealtimeSTT kwargs. turbo owner is mobiuslabsgmbh. (Gotcha #3.)
      * `prefetch()`: lazy import of snapshot_download inside the fn (Gotcha #4); defaults preserved
        (Gotcha #1); whole-repo download (Gotcha #2); returns {short: path}; per-repo header + size line.
      * `_model_bin_size()`: the post-download verify (Gotcha #9) — None signals a broken/partial repo.
      * `_human_bytes()`: readable sizes (pure helper; TiB cap avoids float drift).
      * `_main()`: telemetry opt-out (Gotcha #13); CORE fatal / OPTIONAL warning (Gotcha #8); exit 0 iff
        core ok; summary table; total bytes from cache.
      * `_local_snapshot()` + the summary re-resolve: computes total from the cache via
        local_files_only=True (no re-download) — robust even if a repo partially downloaded earlier.
        The verbatim `_main()` is clean and correct as written; write it verbatim, no edits needed.
  - DO NOT: add top-level `import ctranslate2`/`torch`; set LD_LIBRARY_PATH/cache_dir/local_dir/token/
    force_download; rename the short-name keys; add a [project.scripts] entry (Gotcha #10); add a
    `--force` default; narrow the per-repo except (it MUST be broad — any failure → that repo's branch).

Task 3: RUN the prefetch (the real ~1.8 GB core + ~1.6 GB turbo download) — NO mocking
  - This produces the SECOND + THIRD deliverables: the populated cache + prefetch_results.md.
  - RUN (from /home/dustin/projects/voice-typing; multi-minute, do not short-timeout):
      cd /home/dustin/projects/voice-typing
      PY=.venv/bin/python
      OUT=$("$PY" -m voice_typing.prefetch 2>&1; echo "exit=$?")
      echo "$OUT"
      echo "---"
      echo "$OUT" | grep -E '^(=== \[|    -> |    model.bin:|core ok|core FAIL|opt  ok|opt  warn|total model.bin|FAILED CORE)'
  - EXPECTED: 4 `=== [<short>] <repo_id> ===` headers (distil-large-v3, small.en, tiny.en, large-v3-turbo),
    4 `    -> .../models--.../snapshots/<rev>` lines, 4 `    model.bin: <size>` lines, a summary block,
    `total model.bin bytes cached: ~3.4 GiB`, and `exit=0`. (huggingface_hub's tqdm per-file bars also
    render on stderr — captured in $OUT.)
  - IF a CORE repo fails (network blip, etc.): the script prints `!!! CORE FAIL [...]` and exits 1. RE-RUN
    `python -m voice_typing.prefetch` — snapshot_download resumes from the cache (already-downloaded
    blobs are skipped), so a re-run only re-fetches the interrupted repo. Retry until core exits 0.
  - IF only the turbo (OPTIONAL) repo fails: the script exits 0 (turbo is a warning) but the substitute
    path won't be cached. Record this in prefetch_results.md; do NOT block on it (the daemon's primary
    CUDA path uses distil-large-v3, which succeeded).
  - DO NOT: mock anything, set a short timeout, run under launch_daemon.sh (Gotcha #5), or `force_download`.

Task 4: RECORD plan/001_be48c74bc590/P1M1T3S1/prefetch_results.md from the run
  - WRITE the file from the captured $OUT (fill in ACTUAL values — do NOT invent them):
        --- BEGIN prefetch_results.md ---
        # Prefetch results — voice-typing STT models

        **Recorded:** <YYYY-MM-DD>  •  **Run as:** `.venv/bin/python -m voice_typing.prefetch`
        **Cache root:** `~/.cache/huggingface/hub` (default; faster-whisper reads this)

        ## Per-repo result

        | short name | repo_id | snapshot path | model.bin size | status |
        |---|---|---|---|---|
        | distil-large-v3 | Systran/faster-distil-whisper-large-v3 | <path> | <size> | <ok/FAIL> |
        | small.en | Systran/faster-whisper-small.en | <path> | <size> | <ok/FAIL> |
        | tiny.en | Systran/faster-whisper-tiny.en | <path> | <size> | <ok/FAIL> |
        | large-v3-turbo | mobiuslabsgmbh/faster-whisper-large-v3-turbo | <path> | <size> | <ok/warn/FAIL> |

        ## Summary (from the run)

        ```
        <paste the === summary === block + total model.bin bytes line + exit= line>
        ```

        ## Full run output

        ```
        <paste the full $OUT, including any tqdm/!FAIL lines>
        ```

        ## Meaning for the daemon (P1.M4.T1.S1)

        - All CORE repos cached → `AudioToTextRecorder(model=final_model, realtime_model_type=realtime_model)`
          construction is instant (no download). cuda_check.py's CUDA path (distil-large-v3 + small.en)
          and CPU-fallback path (small.en + tiny.en) are both satisfied.
        - <If turbo ok: the approved substitute is also local — if distil-large-v3 ever runs poorly, the
           daemon can switch to large-v3-turbo with no network. If turbo failed: note the substitute is
           NOT cached; primary CUDA path is unaffected.>

        ## Idempotency check

        - A re-run of `.venv/bin/python -m voice_typing.prefetch` completes in seconds (etags match,
          no re-download) — safe for install.sh (P1.M6.T1.S1) to re-invoke.
        --- END prefetch_results.md ---
  - DO NOT: write to any path other than plan/001_be48c74bc590/P1M1T3S1/prefetch_results.md; invent sizes.

Task 5: VALIDATE — run the Validation Loop L1–L5 below. Fix until all applicable gates pass.
  - No git commit from T3.S1 unless the orchestrator directs it. If asked: message
    "P1.M1.T3.S1: prefetch.py + downloaded faster-whisper CT2 models to HF cache".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the lazy snapshot_download call (side-effect-free import + whole-repo default download).
#   The import is INSIDE prefetch() so `import voice_typing.prefetch` never touches the network or any
#   heavy dep (it can run before ctranslate2 lands — Gotcha #4). Defaults preserved (Gotcha #1).
def prefetch(short_to_repo=None):
    from huggingface_hub import snapshot_download  # lazy
    mapping = short_to_repo if short_to_repo is not None else {**CORE_REPOS, **OPTIONAL_REPOS}
    results = {}
    for short, repo_id in mapping.items():
        print(f"\n=== [{short}] {repo_id} ===", flush=True)
        local_path = snapshot_download(repo_id=repo_id, repo_type="model")  # defaults: cache/token/force all correct
        results[short] = local_path
        print(f"    -> {local_path}\n    model.bin: {_human_bytes(_model_bin_size(local_path) or 0)}")
    return results

# PATTERN 2 — CORE-fatal / OPTIONAL-warning exit semantics (install.sh runs under `set -e`).
#   CORE repos are required for the daemon to start → any failure → exit 1. turbo is an approved
#   SUBSTITUTE → failure is a warning, exit 0. Per-repo try/except isolates failures (one bad repo
#   doesn't abort the rest), and re-running resumes from the cache (idempotent).
try:
    prefetch({short: repo_id}); core_ok.append(short)
except Exception as exc:                    # broad: network/HTTP/disk
    core_fail[short] = f"{type(exc).__name__}: {exc}"   # → exit 1 at the end
return 0 if not core_fail else 1

# PATTERN 3 — post-download verify (catch a partial repo before the daemon hits it at construction).
#   model.bin is the bulk of every repo (~95% of bytes). If it's absent after "success", the download
#   was interrupted or the repo is wrong — surface it NOW with a size line, not later as a confusing
#   WhisperModel "file not found".
def _model_bin_size(snapshot_path):
    try: return os.path.getsize(os.path.join(snapshot_path, "model.bin"))
    except OSError: return None   # caller prints WARNING + (in _main) counts the repo as failed/short
```

### Integration Points

```yaml
DOWNSTREAM — P1.M6.T1.S1 (install.sh; THE re-user):
  - install.sh re-invokes `.venv/bin/python -m voice_typing.prefetch` (idempotent — re-runs skip cached
    blobs). It does NOT re-implement the repo list. It reads the exit code: 0 = models ready; 1 = a CORE
    repo failed (install.sh should surface this prominently — the daemon will not start).
  - install.sh MUST treat the turbo-warning case (exit 0 with an OPTIONAL note) as non-fatal.

DOWNSTREAM — P1.M4.T1.S1 (daemon recorder wiring; THE consumer):
  - Constructs AudioToTextRecorder(model=cfg["final_model"], realtime_model_type=cfg["realtime_model"], ...)
    where cfg comes from cuda_check.resolve_device_and_models(). faster-whisper resolves those short
    names to the repo_ids prefetched here via the DEFAULT HF cache. Construction is instant BECAUSE this
    task populated the cache. If construction ever triggers a download, prefetch was incomplete (re-run it).

PARALLEL — P1.M1.T2.S2 (ctranslate2 install / cuda_check):
  - T3.S1 has NO hard dependency on T2.S2. prefetch.py imports only huggingface_hub (already installed).
    The cached weights become loadable only once ctranslate2 lands (T2.S2), but the cache-population
    step runs independently. Do NOT block T3.S1 on T2.S2 and do NOT import ctranslate2 in prefetch.py.
  - The short-name KEYS in CORE_REPOS/OPTIONAL_REPOS MUST stay identical to cuda_check.py's
    final_model/realtime_model values (distil-large-v3, small.en, tiny.en) + the PRD-approved substitute
    (large-v3-turbo). Drift = a fallback/substitute path triggers a runtime download.

CONDITIONAL — nothing in T3.S1 modifies pyproject.toml, .gitignore, PRD.md, tasks.json, prd_snapshot.md,
uv.lock, or any file under voice_typing/ other than creating voice_typing/prefetch.py, plus the recorded
plan/001_be48c74bc590/P1M1T3S1/prefetch_results.md. The cache under ~/.cache/huggingface is a machine-local
SIDE EFFECT (lives outside the repo; never committed).

BUILD ARTIFACTS:
  - T3.S1 creates NO dist/, NO uv.lock changes, NO .venv changes, NO [project.scripts] addition. prefetch.py
    is a plain source module invoked via `python -m`. `uv sync`/`uv build` are NOT run.
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases). Run from `/home/dustin/projects/voice-typing`. L1/L2 are
> instant (no network). L3 is the REAL multi-minute download (mock nothing — the contract). L4 verifies
> the cache. L5 verifies idempotency.

### Level 1: Syntax + import-cleanness (no deps/network needed)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f voice_typing/prefetch.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile voice_typing/prefetch.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
# THE KEY TEST: importing the module triggers NO network call (snapshot_download is lazy):
"$PY" -c "import voice_typing.prefetch as m; print('L1 import OK'); print(' CORE:', list(m.CORE_REPOS)); print(' OPT:', list(m.OPTIONAL_REPOS)); print(' fn:', m.prefetch)" \
  && echo "L1 PASS: importable, constants + fn visible, no network" \
  || echo "L1 FAIL: import raised (lazy import leaked? ctranslate2 pulled in?)"
# No heavy/top-level imports (snapshot_download must be INSIDE prefetch()):
! grep -nE '^(import|from) (ctranslate2|faster_whisper|torch|huggingface_hub)' voice_typing/prefetch.py \
  && echo "L1 PASS: no top-level heavy imports (all lazy)" \
  || echo "L1 FAIL: top-level heavy import found (move inside the fn — Gotcha #4)"
# Expected: file present, py_compile clean, import OK with CORE {distil-large-v3,small.en,tiny.en} +
# OPTIONAL {large-v3-turbo}, no network activity (the import prints instantly).
```

### Level 2: API contract + repo-ID correctness (no network — exercises constants + return shape)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" - <<'PYEOF'
from voice_typing.prefetch import CORE_REPOS, OPTIONAL_REPOS, prefetch, _model_bin_size, _human_bytes
# (1) exact repo IDs (the contract — incl. the mobiuslabsgmbh owner for turbo):
assert CORE_REPOS == {
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
    "small.en": "Systran/faster-whisper-small.en",
    "tiny.en": "Systran/faster-whisper-tiny.en",
}, CORE_REPOS
assert OPTIONAL_REPOS == {"large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo"}, OPTIONAL_REPOS
# (2) trap-avoidance: NO distil-whisper/ raw repo, turbo is NOT under Systran:
assert all(r.startswith("Systran/") for r in CORE_REPOS.values()), "core owner drift"
assert "mobiuslabsgmbh/" in OPTIONAL_REPOS["large-v3-turbo"], "turbo owner wrong"
assert "distil-whisper/" not in (*CORE_REPOS.values(), *OPTIONAL_REPOS.values()), "raw PT repo leaked in"
# (3) signature: prefetch(short_to_repo=None) -> dict
import inspect
sig = inspect.signature(prefetch)
assert list(sig.parameters) == ["short_to_repo"], list(sig.parameters)
assert sig.parameters["short_to_repo"].default is None
# (4) short-name KEYS align with cuda_check's model names (scope coupling):
from voice_typing.cuda_check import CUDA_DEFAULTS, CPU_FALLBACK
cuda_names = {CUDA_DEFAULTS["final_model"], CUDA_DEFAULTS["realtime_model"],
              CPU_FALLBACK["final_model"], CPU_FALLBACK["realtime_model"]}
assert cuda_names <= set(CORE_REPOS), ("cuda_check model not prefetched:", cuda_names - set(CORE_REPOS))
# (5) helpers behave:
assert _model_bin_size("/nonexistent/path") is None, "_model_bin_size should return None on missing"
assert _human_bytes(0) == "0 B" and _human_bytes(2048).endswith("KiB")
print("L2 PASS: repo IDs + signature + cuda_check alignment + helpers OK")
PYEOF
# Expected: "L2 PASS: ...". The cuda_check alignment check is the scope-coupling guard (Integration).
# (If voice_typing.cuda_check is absent because T2.S2 hasn't landed yet, comment out block (4) and note it;
#   blocks (1)-(3),(5) are self-contained and always runnable.)
```

### Level 3: The REAL download (run prefetch end-to-end — mock nothing) — multi-minute

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# Pre-check the load-bearing preconditions (should pass on this host; if HF is down, retry later):
"$PY" -c "from huggingface_hub import HfApi; print('HF reachable, tiny.en files:', len(HfApi().repo_info('Systran/faster-whisper-tiny.en').siblings))" \
  || { echo "L3 BLOCKED: HF not reachable — retry when network is up"; exit 0; }
# THE DOWNLOAD (no timeout cap — this is ~1.8 GB core + ~1.6 GB turbo; minutes, not seconds):
OUT=$("$PY" -m voice_typing.prefetch 2>&1; echo "exit=$?")
echo "$OUT"
# Structural assertions on the output:
echo "$OUT" | grep -qE '^=== \[distil-large-v3\] Systran/faster-distil-whisper-large-v3 ===' && echo "L3a PASS: distil header" || echo "L3 FAIL: no distil header"
echo "$OUT" | grep -qE '^=== \[small.en\] Systran/faster-whisper-small.en ===' && echo "L3b PASS: small.en header" || echo "L3 FAIL"
echo "$OUT" | grep -qE '^=== \[tiny.en\] Systran/faster-whisper-tiny.en ===' && echo "L3c PASS: tiny.en header" || echo "L3 FAIL"
echo "$OUT" | grep -qE '^=== \[large-v3-turbo\] mobiuslabsgmbh/faster-whisper-large-v3-turbo ===' && echo "L3d PASS: turbo header" || echo "L3 FAIL"
echo "$OUT" | grep -qE '^    model\.bin: [0-9.]+ (B|KiB|MiB|GiB)' && echo "L3e PASS: model.bin size lines present" || echo "L3 FAIL: no model.bin sizes"
echo "$OUT" | grep -qE '^total model\.bin bytes cached:' && echo "L3f PASS: summary total line" || echo "L3 FAIL: no total line"
EXIT=$(echo "$OUT" | grep -oE 'exit=[0-9]+$' | cut -d= -f2)
# CORE must all succeed → exit 0 (turbo failure would still be exit 0 per Gotcha #8):
[ "$EXIT" = "0" ] && echo "L3g PASS: exit 0 (all CORE ok)" || echo "L3 FAIL: exit $EXIT (a CORE repo failed — re-run; it resumes from cache)"
# Expected: 4 repo headers, 4 model.bin size lines, summary total, exit=0. tqdm bars may interleave on stderr.
```

### Level 4: Cache verification (the deliverable: weights actually landed in the right place)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
CACHE=~/.cache/huggingface/hub
# (a) each repo dir exists under the DEFAULT cache (faster-whisper reads this):
for d in models--Systran--faster-distil-whisper-large-v3 \
         models--Systran--faster-whisper-small.en \
         models--Systran--faster-whisper-tiny.en \
         models--mobiuslabsgmbh--faster-whisper-large-v3-turbo; do
  test -d "$CACHE/$d" && echo "L4a PASS: $d cached" || echo "L4 FAIL: $d MISSING"
done
# (b) each resolved snapshot contains model.bin + config.json + tokenizer.json + a vocabulary file:
"$PY" - <<'PYEOF'
from huggingface_hub import snapshot_download
from pathlib import Path
repos = {"distil-large-v3":"Systran/faster-distil-whisper-large-v3",
         "small.en":"Systran/faster-whisper-small.en",
         "tiny.en":"Systran/faster-whisper-tiny.en",
         "large-v3-turbo":"mobiuslabsgmbh/faster-whisper-large-v3-turbo"}
for short, rid in repos.items():
    p = Path(snapshot_download(repo_id=rid, local_files_only=True))  # cache hit — NO download
    need = ["model.bin", "config.json", "tokenizer.json"]
    have = {f: (p/f).is_file() for f in need}
    vocab = (p/"vocabulary.json").is_file() or (p/"vocabulary.txt").is_file()
    assert all(have.values()), (short, "missing core files:", [f for f in have if not have[f]])
    assert vocab, (short, "missing vocabulary.json/.txt")
    print(f"L4b PASS: [{short}] model.bin={ (p/'model.bin').stat().st_size } bytes; vocab ok")
print("L4 PASS: all 4 repos fully cached + loadable (CT2 files present)")
PYEOF
# (c) the cache is non-trivial (sanity: total > ~1 GB — core alone is ~1.8 GB):
CORE_BYTES=$("$PY" - <<'PYEOF'
from huggingface_hub import snapshot_download
from pathlib import Path
tot=0
for rid in ["Systran/faster-distil-whisper-large-v3","Systran/faster-whisper-small.en","Systran/faster-whisper-tiny.en"]:
    p=Path(snapshot_download(repo_id=rid, local_files_only=True))
    tot+=(p/"model.bin").stat().st_size
print(tot)
PYEOF
)
[ "$CORE_BYTES" -gt 1800000000 ] && echo "L4c PASS: core model.bin total $CORE_BYTES > ~1.8 GB (real weights)" \
  || echo "L4 FAIL: core total $CORE_BYTES too small (partial download?)"
# Expected: all 4 dirs present, each snapshot has model.bin+config+tokenizer+vocab, core > ~1.8 GB.
```

### Level 5: Idempotency (re-run is free — the install.sh contract)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# Time a second run — it must NOT re-download (etags match). Should be seconds, not minutes.
START=$(date +%s)
OUT2=$("$PY" -m voice_typing.prefetch 2>&1; echo "exit=$?")
END=$(date +%s)
ELAPSED=$((END-START))
echo "$OUT2" | tail -8
echo "L5 second-run elapsed: ${ELAPSED}s"
EXIT2=$(echo "$OUT2" | grep -oE 'exit=[0-9]+$' | cut -d= -f2)
# A cache-hit re-run resolves each repo near-instantly (no multi-GB transfer). Allow generous bound
# for HF metadata round-trips on a slow link, but it must be FAR under a fresh download (~minutes):
[ "$EXIT2" = "0" ] && [ "$ELAPSED" -lt 120 ] \
  && echo "L5 PASS: idempotent re-run (exit 0, ${ELAPSED}s < 120s — no re-download)" \
  || echo "L5 FAIL/WARN: exit=$EXIT2 elapsed=${ELAPSED}s (if >120s, etag check was slow — investigate, but exit 0 still ok)"
# Expected: exit 0, elapsed well under 120s (typically <30s). Confirms install.sh can re-invoke for free.
```

### Level 6: Scope guards — only prefetch.py + prefetch_results.md created; read-only files untouched

```bash
cd /home/dustin/projects/voice-typing
# Only NEW source file is voice_typing/prefetch.py:
ls voice_typing/  # expect: __init__.py  cuda_check.py  launch_daemon.sh  prefetch.py
# Read-only / out-of-scope files UNCHANGED:
for f in PRD.md pyproject.toml uv.lock .gitignore plan/001_be48c74bc590/tasks.json \
         plan/001_be48c74bc590/prd_snapshot.md voice_typing/daemon.py voice_typing/install.sh \
         systemd/voice-typing.service; do
  test ! -e "$f" && echo "absent (ok): $f" || echo "present (verify unchanged): $f"
done
# prefetch_results.md exists + is faithful:
F=plan/001_be48c74bc590/P1M1T3S1/prefetch_results.md
test -f "$F" && echo "L6 PASS: prefetch_results.md exists" || echo "L6 FAIL: prefetch_results.md missing"
grep -qiE 'distil-large-v3|model.bin' "$F" && echo "L6 PASS: results log records repos/sizes" || echo "L6 FAIL: results log empty"
git status --short
# Expected: git status shows ONLY voice_typing/prefetch.py (new) — the cache is OUTSIDE the repo (not shown).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 `py_compile` clean + `import voice_typing.prefetch` succeeds with NO network (lazy import).
- [ ] L2 repo-ID + signature + cuda_check-alignment + helper assertions pass.
- [ ] L3 real download: 4 repo headers + 4 `model.bin` size lines + summary + exit 0.
- [ ] L4 all 4 repos fully cached (model.bin+config+tokenizer+vocab) in DEFAULT cache; core > ~1.8 GB.
- [ ] L5 idempotent re-run: exit 0 in <120s (no re-download).
- [ ] L6 only `voice_typing/prefetch.py` created; read-only files untouched; prefetch_results.md faithful.

### Feature Validation
- [ ] `python -m voice_typing.prefetch` populates `~/.cache/huggingface/hub` with all 4 repos.
- [ ] Every cached repo is CTranslate2-loadable (model.bin present, no pytorch weights).
- [ ] CORE repos (distil-large-v3, small.en, tiny.en) all succeed → daemon can start (CUDA + fallback).
- [ ] Re-running the script is free (idempotent) → install.sh (P1.M6.T1.S1) can re-invoke safely.
- [ ] `prefetch_results.md` records per-repo paths/sizes/status + total + the full run output.

### Code Quality Validation
- [ ] `prefetch.py` imports ONLY `huggingface_hub` (lazy); no ctranslate2/faster_whisper/torch.
- [ ] No top-level heavy imports (snapshot_download is inside `prefetch()`).
- [ ] Defaults preserved: cache_dir/local_dir/token/force_download all unset (correct for faster-whisper).
- [ ] Short-name KEYS match cuda_check's `final_model`/`realtime_model` values (scope coupling intact).
- [ ] Full paths used in every bash command (`.venv/bin/python`, no bare python/uv).
- [ ] `from __future__ import annotations` present (3.12-safe unions).

### Documentation & Deployment
- [ ] Module docstring documents: purpose, idempotent install.sh reuse, repo-ID verification + the
      three-owner trap + the distil-whisper trap, and the decoupling from CUDA/ctranslate2.
- [ ] `prefetch_results.md` is self-contained (a reader can see what landed + what it means for the daemon).
- [ ] No new env vars required by the daemon (HF_HUB_DISABLE_TELEMETRY is a local-only nicety, set in `_main`).

### Scope Boundary Validation
- [ ] No `daemon.py`, no recorder construction, no `install.sh`, no systemd, no config.toml created.
- [ ] No `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md` changes.
- [ ] `prefetch.py` NOT added to `[project.scripts]` (the `-m` invocation is the CLI).
- [ ] No `uv sync`/`uv build`/`uv add` run (dependencies are S2's job; prefetch needs only huggingface_hub).

---

## Anti-Patterns to Avoid

- ❌ Don't set `cache_dir`/`local_dir`/`token`/`force_download` on `snapshot_download` — the defaults are exactly what faster-whisper's auto-resolution expects; overriding breaks it or kills idempotency.
- ❌ Don't use `allow_patterns`/`ignore_patterns` to "trim" repos — every non-README file is load-bearing; just download the whole repo.
- ❌ Don't "fix" the turbo owner to `Systran/` (it's `mobiuslabsgmbh/`), and don't swap `distil-large-v3` to the `distil-whisper/` raw PyTorch repo (no model.bin — CTranslate2 can't load it).
- ❌ Don't import `ctranslate2`/`faster_whisper`/`torch` in prefetch.py (top-level OR to "verify") — prefetch only moves bytes; it must run before T2.S2 installs ctranslate2.
- ❌ Don't run prefetch under `launch_daemon.sh` or set `LD_LIBRARY_PATH` — irrelevant to a file download.
- ❌ Don't make CORE repo failures non-fatal (exit must be 1 if any CORE repo fails — the daemon can't start). Conversely, don't make the turbo (OPTIONAL) failure fatal (it's an approved substitute, not required).
- ❌ Don't mock the download or skip it "to save time" — the populated cache IS the deliverable.
- ❌ Don't add `prefetch` to `[project.scripts]` — the CLI is `python -m voice_typing.prefetch` (matches cuda_check.py; install.sh calls `-m`).
- ❌ Don't add a `--force`/`force_download=True` default — it breaks the idempotency install.sh relies on.
- ❌ Don't edit `.gitignore`, `PRD.md`, `tasks.json`, `pyproject.toml`, or `prd_snapshot.md`.
- ❌ Don't use bare `python`/`pip`/`uv`/`tmux` (zsh aliases shadow them on this machine).

---

## Confidence Score

**9/10** for one-pass implementation success. The module source is given verbatim (with one explicitly-flagged cleanup block), the `snapshot_download` API is verified live against the installed huggingface_hub 1.22.0, the four repo IDs + their file inventories are verified against the live HF API (and the distil-whisper trap is confirmed), and the network/disk preconditions are confirmed on this machine (HF reachable, 237 GB free). The residual uncertainty (−1) is the real-world download itself: a transient network blip on the ~1.8 GB core transfer could fail a repo — but the script is idempotent (re-run resumes from cache) and the PRP's L3 explicitly instructs re-running on CORE failure, so recovery is mechanical, not a re-design.
