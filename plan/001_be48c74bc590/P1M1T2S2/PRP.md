# PRP — P1.M1.T2.S2: CUDA smoke verification script + degraded-mode decision

## Goal

**Feature Goal**: Produce a single Python module — `voice_typing/cuda_check.py` — that is both importable (`from voice_typing.cuda_check import is_cuda_available, resolve_device_and_models`) and a CLI smoke check (`python -m voice_typing.cuda_check`). It runs the two PRD §5-step-4 checks (the **must-have** `ctranslate2.get_cuda_device_count() >= 1` and the **nice-to-have** `torch.cuda.is_available()`), prints ctranslate2 version + device count + torch-CUDA bool + a one-line parseable `VERDICT=`, and exposes the decision as `is_cuda_available() -> bool` and `resolve_device_and_models(defaults) -> dict` which applies the **PRD §4.4 CPU fallback** (`device="cpu", compute_type="int8", final_model="small.en", realtime_model="tiny.en"`) whenever ctranslate2 sees zero CUDA devices (or is unavailable). The module is the single decision point the daemon's recorder wiring (P1.M4.T1.S1) calls once at startup to pick `device`/`compute_type`/`final_model`/`realtime_model`.

**Deliverable** (exactly two artifacts):
1. `voice_typing/cuda_check.py` — the importable + CLI module (verbatim code given below; DOCS [Mode A] degraded-mode knob documented in the module docstring + an inline comment).
2. `plan/001_be48c74bc590/architecture/cuda_verdict.md` — a recorded **actual** verdict file capturing this machine's CUDA state (the VERDICT line, the raw checks, the resolved config, and how it was run). This is produced by **running** the script under `launch_daemon.sh`'s `LD_LIBRARY_PATH` env.

**Success Definition**:
- (a) `voice_typing/cuda_check.py` exists, parses (`py_compile`), and `python -c "import voice_typing.cuda_check"` succeeds **even with no ctranslate2/torch installed** (all heavy imports are local + wrapped — see Gotcha #2).
- (b) Public API is exactly: `is_cuda_available() -> bool`, `resolve_device_and_models(defaults: Mapping|None=None) -> dict`. `resolve_device_and_models()` returns `{device, compute_type, final_model, realtime_model}` with exactly the CUDA values when `is_cuda_available()` is True and exactly the PRD §4.4 CPU-fallback values when False.
- (c) `python -m voice_typing.cuda_check` prints four greppable lines ending in `VERDICT=cuda-ok` or `VERDICT=cpu-fallback-required` (exit 0 for cuda-ok, exit 1 for cpu-fallback-required).
- (d) **No mocking.** The check probes the real machine under `launch_daemon.sh`'s env (`LD_LIBRARY_PATH` set). When ctranslate2 IS importable and CUDA works, the recorded verdict is `cuda-ok`; when the count is 0 / import fails, it is `cpu-fallback-required`.
- (e) `cuda_check.py` does **not** set `LD_LIBRARY_PATH` (that is `launch_daemon.sh`'s sole responsibility — T2.S1's invariant, research_faster_whisper_cuda.md §2). It assumes the caller already set it.
- (f) The actual machine verdict is recorded in `plan/001_be48c74bc590/architecture/cuda_verdict.md`. **If `ctranslate2` is not yet importable at implementation time** (S2 re-plan pending — see Known Gotchas #7 / the S2 issue), record a **provisional** `cpu-fallback-required` verdict that flags the blocker and DEFER the definitive verdict until S2 completes (re-run the smoke check then). This mirrors T2.S1's parallel-with-S2 deferral pattern.
- (g) No out-of-scope artifacts (no `daemon.py`, no recorder construction, no `install.sh`, no systemd unit, no pyproject edit, no model prefetch).

## User Persona

Not applicable (developer/agent-facing decision module; no end-user surface). The user-visible "device=cpu" status string and config knob are surfaced later by the daemon (P1.M4.T1.S1) and `feedback.py` (P1.M3.T2.S1); this task only supplies the **decision** and documents the knob.

## Why

- **One decision point, no drift.** PRD §4.4 mandates a degraded CPU fallback when CUDA init fails; without a single resolver, the daemon (P1.M4.T1.S1) and `install.sh` (P1.M6.T1.S1) would each re-implement the ctranslate2 probe and could disagree. `resolve_device_and_models()` is the contract the recorder wiring imports — it returns the exact `{device, compute_type, final_model, realtime_model}` quad the `AudioToTextRecorder` needs (mapped `final_model -> model=`, `realtime_model -> realtime_model_type=` by P1.M4.T1.S1; verified against RealtimeSTT v1.0.2 `FasterWhisperEngine` — see research note).
- **The must-have is ctranslate2, not torch.** faster-whisper's inference runs on CTranslate2 (the `transcription_engine="faster_whisper"` default). torch is only for Silero VAD and runs fine on CPU (research_faster_whisper_cuda.md §3). So `is_cuda_available()` gates on `ctranslate2.get_cuda_device_count()`, and the torch probe is **informational only** — it must NOT flip the verdict.
- **Robust to a known-broken dependency state.** S2 (P1.M1.T1.S2) **failed its first attempt**: bare `realtimestt` does not pull `faster-whisper`/`ctranslate2` (they are optional extras `RealtimeSTT[faster-whisper]`). ctranslate2 is therefore **not importable** in `.venv` right now. The smoke check must degrade cleanly to `cpu-fallback-required` when `import ctranslate2` raises, and the verdict-recording step must record a provisional state rather than crash (Gotcha #7). This is exactly the failure mode the contract's "Mock nothing, real smoke check" is meant to expose and document.
- **`get_cuda_device_count()` is the lightweight probe (no model load).** Per the ctranslate2 API (research note Q6), it queries the CUDA driver for the device count **without** allocating GPU memory, creating a context, loading cuDNN, or constructing a model. So it is cheap and safe to call once at startup and once in the smoke check. (Caveat documented in the module: a `cuda-ok` verdict means the GPU is *visible*; cuDNN load failures surface later at `WhisperModel` construction — that is the daemon's concern, mitigated by `launch_daemon.sh`'s `LD_LIBRARY_PATH`.)

## What

Create `voice_typing/cuda_check.py` (verbatim code in Implementation Blueprint → Task 2): a self-documenting module with two module-level config constants (`CUDA_DEFAULTS`, `CPU_FALLBACK`), private probes (`_cuda_device_count`, `_ctranslate2_version`, `_torch_cuda_available`), the two public functions, and a `__main__` CLI that prints `ctranslate2_version=`, `cuda_device_count=`, `torch_cuda_available=`, `VERDICT=` plus two `#`-prefixed detail lines (reason + resolved config). Then **run** it under `launch_daemon.sh`'s env and **record** the verdict into `plan/001_be48c74bc590/architecture/cuda_verdict.md`.

### Success Criteria

- [ ] `voice_typing/cuda_check.py` exists and `python -m py_compile voice_typing/cuda_check.py` exits 0.
- [ ] `python -c "import voice_typing.cuda_check as m; print(m.is_cuda_available, m.resolve_device_and_models)"` succeeds **with the current (ctranslate2-absent) `.venv`** — imports must be lazy/wrapped.
- [ ] Public API: `is_cuda_available() -> bool`; `resolve_device_and_models(defaults=None) -> dict` returning exactly keys `{device, compute_type, final_model, realtime_model}`.
- [ ] When `is_cuda_available()` is True, `resolve_device_and_models()` returns `{device:"cuda", compute_type:"float16", final_model:"distil-large-v3", realtime_model:"small.en"}` (a copy of `CUDA_DEFAULTS` / the passed `defaults`).
- [ ] When `is_cuda_available()` is False, `resolve_device_and_models()` returns `{device:"cpu", compute_type:"int8", final_model:"small.en", realtime_model:"tiny.en"}` (a copy of `CPU_FALLBACK`) **regardless of `defaults`**.
- [ ] `resolve_device_and_models()` always returns a fresh dict (mutating the result does not mutate the module constants).
- [ ] `python -m voice_typing.cuda_check` (run with `LD_LIBRARY_PATH` set per launch_daemon.sh) prints `ctranslate2_version=`, `cuda_device_count=`, `torch_cuda_available=`, `VERDICT=` lines; last VERDICT is `cuda-ok` or `cpu-fallback-required`; exit 0 / 1 respectively.
- [ ] `cuda_check.py` does NOT reference `os.environ["LD_LIBRARY_PATH"]` for setting it (may read/log it for diagnostics, but must NOT assign to it).
- [ ] Module docstring documents the degraded-mode knob (PRD §4.4) — the DOCS [Mode A] requirement.
- [ ] `plan/001_be48c74bc590/architecture/cuda_verdict.md` exists and records the actual (or provisional) verdict + raw checks + resolved config + run method.
- [ ] No `daemon.py`, no recorder construction, no `install.sh`, no `systemd/`, no model prefetch, no `pyproject.toml`/`PRD.md`/`tasks.json`/`.gitignore` changes.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement T2.S2 from this PRP + the referenced research files. The full module source is given verbatim; every ctranslate2/torch API behavior it depends on is documented (and the ctranslate2 specifics are cross-checked against the public API in `research/ctranslate2_cuda_api_verification.md`); the LD_LIBRARY_PATH repro is the exact one-liner `launch_daemon.sh` (T2.S1) uses; and the known dependency hole (S2's extras issue) is handled by the deferral pattern rather than left as a surprise.

### Documentation & References

```yaml
# MUST READ — the authoritative CUDA-check spec (the two checks + the degraded fallback)
- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md
  why: "§3 is the source for BOTH checks: ctranslate2.get_cuda_device_count() MUST be >=1
        (the whisper inference path); torch.cuda.is_available() is nice-to-have (Silero VAD,
        runs fine on CPU so does NOT gate the verdict). §3 also states the degraded-mode
        fallback (device='cpu', compute_type='int8', realtime tiny.en, final small.en) and that
        the daemon MUST log it clearly and report device='cpu' in status."
  critical: "is_cuda_available() gates on CTRANSLATE2, not torch. torch probe is informational.
             The verdict must be 'cuda-ok' only when ctranslate2 device count >= 1."

# MUST READ — the ctranslate2 Python API specifics (verified against the public surface)
- docfile: plan/001_be48c74bc590/P1M1T2S2/research/ctranslate2_cuda_api_verification.md
  why: "Answers the 6 load-bearing API questions: (Q1) get_cuda_device_count() is module-level,
        returns int, returns 0 with no GPU, does NOT load cuDNN (so a missing libcudnn_ops will
        NOT make it return 0 here — that surfaces later at WhisperModel construction) BUT can RAISE
        on CUDA-runtime load failures → wrap BOTH import and call in try/except == CPU fallback;
        (Q2) ctranslate2.__version__ is the correct version attr; (Q3) import is lazy / no CUDA init;
        (Q4) torch.cuda.is_available() returns bool, never raises; (Q5) cpu+int8 and cuda+float16
        are known-good faster-whisper combos; (Q6) get_cuda_device_count() IS the lightweight probe.
        ALSO verifies the exact WhisperModel(device, compute_type, device_index=gpu_device_index)
        call consumed by RealtimeSTT's FasterWhisperEngine — confirming the key names the daemon maps."
  section: "Q1 (try/except == fallback) and 'Recommended decision logic' code snippet are load-bearing.
            Note the BLOCKER callout: ctranslate2 is an optional RealtimeSTT extra — it is NOT
            installed yet (S2 issue). The lazy import + broad except is what makes the module safe today."

# MUST READ — the LD_LIBRARY_PATH wrapper this script runs under (and must NOT replicate)
- file: plan/001_be48c74bc590/P1M1T2S1/PRP.md
  why: "Defines launch_daemon.sh's exact LD_LIBRARY_PATH computation (the nvidia.cublas.lib /
        nvidia.cudnn.lib dirname one-liner) which the smoke check MUST reproduce when run, AND the
        invariant that LD_LIBRARY_PATH is set in exactly ONE place (the wrapper). cuda_check.py must
        NOT set it (no effect at runtime; ld.so(8) reads it at exec)."
  critical: "To RUN the smoke check faithfully, replicate launch_daemon.sh's LD_LIBRARY_PATH export
             in the shell BEFORE invoking python -m voice_typing.cuda_check (see Validation L3).
             Do NOT put that logic inside cuda_check.py."

# Background — the degraded-mode fallback values + the cuDNN risk row
- file: PRD.md
  why: "§4.4 defines BOTH configs verbatim: CUDA path (device='cuda', compute_type='float16',
        distil-large-v3 + small.en) and the CPU fallback (device='cpu', compute_type='int8',
        small.en + tiny.en). §8 risk row #1 (cuDNN 'cannot load libcudnn_ops') is what the
        LD_LIBRARY_PATH wrapper mitigates and what the smoke check's cuDNN caveat refers to."
  critical: "The CPU_FALLBACK values are FIXED by PRD §4.4 — do not derive them from `defaults`.
             `defaults` only matters when CUDA IS available."

# Background — system facts (READ-ONLY)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1 verified machine facts: RTX 3080 Ti 12 GiB, driver 610.x (cu12 wheels run via back-compat);
        uv 0.7.11 at /home/dustin/.local/bin/uv; .venv Python 3.12.10; shell aliases → ALWAYS use
        full paths. §4 decision #2: LD_LIBRARY_PATH via launcher wrapper, NOT os.execv in-process."
  critical: "Use .venv/bin/python and /home/dustin/.local/bin/uv explicitly; never bare python/uv.
             Python 3.12 → PEP 604 `X | None` unions are fine (no __future__ needed for types, but
             `from __future__ import annotations` is used for `Mapping | None` in annotations)."

# Background — the downstream consumer's mapping (so the returned keys are right)
- docfile: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "Confirms AudioToTextRecorder kwargs: model= (final), realtime_model_type= (realtime),
        device=, compute_type=, gpu_device_index=. The daemon's cfg_to_kwargs (P1.M4.T1.S1) will map
        cuda_check's returned final_model->model= and realtime_model->realtime_model_type=."
  critical: "cuda_check returns keys named final_model/realtime_model (per the contract), NOT
             model/realtime_model_type — the daemon does the rename. Do not 'helpfully' rename here."
```

### Current Codebase tree (S1 complete, S2 re-planning, T2.S1 in progress — the state at T2.S2 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*'` from repo root. Expected:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores .venv, __pycache__, dist/, build/ (DO NOT touch)
├── .venv/                      # Python 3.12.10
│   │                             AT T2.S2 TIME: torch==2.12.1+cu130 IS installed and
│   │                             torch.cuda.is_available()==True (verified). BUT ctranslate2 is
│   │                             NOT importable (S2's realtimestt[faster-whisper] extras issue).
│   └── bin/python              # the python the smoke check runs under
├── PRD.md                      # READ-ONLY
├── pyproject.toml              # ← S1's output (4 deps) — UNCHANGED by T2.S2 (realtimestt, NOT realtimestt[faster-whisper])
├── uv.lock                     # may or may not exist (S2's output)
└── voice_typing/
    ├── __init__.py             # ← S1's output (module docstring)
    └── launch_daemon.sh        # ← T2.S1's output (the LD_LIBRARY_PATH wrapper) — ASSUMED PRESENT per parallel context
# NO voice_typing/cuda_check.py yet — T2.S2 creates it (the only new SOURCE file).
# cuda_verdict.md is created by RUNNING the script (under plan/001.../architecture/), not by editing source.
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── cuda_check.py           # ← CREATE (the importable + CLI module; the only new SOURCE file)
plan/001_be48c74bc590/architecture/
└── cuda_verdict.md             # ← CREATE (recorded actual/provisional verdict; produced by RUNNING the script)
# NOTHING ELSE. daemon.py is P1.M4.T3.S1; recorder wiring is P1.M4.T1.S1; install.sh/systemd are P1.M6;
# pyproject edits are S2's re-plan (NOT T2.S2). cuda_check.py is NOT added to [project.scripts] (the `-m`
# invocation is the CLI; a console-script entry is out of scope — see Anti-Patterns).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — LD_LIBRARY_PATH IS SET BY launch_daemon.sh, NOT BY THIS MODULE.
# cuda_check.py must NOT assign os.environ["LD_LIBRARY_PATH"]. The dynamic linker (ld.so(8))
# reads it at process exec; mutating it inside the already-running python has NO effect on that
# process. launch_daemon.sh (T2.S1) is the single sanctioned place. To RUN the smoke check, the
# caller reproduces launch_daemon.sh's export in the shell, then runs `python -m voice_typing.cuda_check`.
# (research_faster_whisper_cuda.md §2; T2.S1 PRP Gotcha #1/#2.)

# CRITICAL #2 — ALL HEAVY IMPORTS MUST BE LOCAL + WRAPPED (lazy import pattern).
# `import ctranslate2` and `import torch` MUST happen INSIDE the probe functions, inside try/except —
# NOT at module top level. Reason 1: S2's re-plan is pending; ctranslate2 is NOT installed yet, so a
# top-level `import ctranslate2` would make `import voice_typing.cuda_check` itself raise ImportError,
# breaking import even when the caller only wants resolve_device_and_models() logic. Reason 2: a
# top-level import that triggers a dlopen failure (missing libcudart) would crash at import. Keeping
# imports local + wrapped means the module ALWAYS imports cleanly and degrades to CPU fallback.
# (research note Q3; the S2 issue.)

# CRITICAL #3 — THE VERDICT GATES ON CTRANSLATE2, NOT TORCH. is_cuda_available() returns True IFF
# ctranslate2.get_cuda_device_count() >= 1. torch.cuda.is_available() is reported by the CLI but does
# NOT affect is_cuda_available() or resolve_device_and_models(). If you gate on torch you will give a
# false "cuda-ok" on a host where torch sees the GPU but ctranslate2 (the actual inference engine) does
# not — exactly the wrong call. (research_faster_whisper_cuda.md §3; research note Q4.)

# CRITICAL #4 — WRAP BOTH THE IMPORT AND THE CALL IN try/except, treat ANY exception as count==0.
# get_cuda_device_count() returns 0 with no GPU (does not raise) BUT can RAISE on CUDA-runtime load
# failures; and `import ctranslate2` itself can raise ImportError (today: not installed) or OSError
# (failed dlopen). A broad `except Exception` here is CORRECT and intentional — its only effect is to
# force CPU fallback, which is the safe degradation. Do NOT narrow it to ImportError only.
# (research note Q1.)

# CRITICAL #5 — get_cuda_device_count() DOES NOT LOAD cuDNN. It queries the CUDA driver only. So a
# missing libcudnn_ops.so.9 will NOT make this check return 0 or raise — that failure surfaces LATER,
# at WhisperModel construction in the daemon (P1.M4.T1.S1). Therefore a "cuda-ok" verdict means "GPU
# visible to ctranslate2", NOT "WhisperModel will definitely construct". The daemon's recorder wiring
# should still be prepared to catch a construction failure and re-resolve to CPU. Document this
# limitation in the module docstring (it is). (research note Q1c, Gap #2.)

# CRITICAL #6 — S2 IS RE-PLANNING (ctranslate2 NOT INSTALLED). This is a KNOWN state, not a bug in
# T2.S2. At implementation time `import ctranslate2` will raise ImportError → is_cuda_available()
# returns False → VERDICT=cpu-fallback-required. That is CORRECT behavior (the script works). The
# recorded cuda_verdict.md must flag this as PROVISIONAL and note: (a) torch.cuda.is_available()==True
# (GPU visible to torch, so the cuda path is LIKELY once ctranslate2 lands), (b) re-run the smoke check
# after S2's successful re-plan (realtimestt -> realtimestt[faster-whisper] or +faster-whisper) to
# capture the definitive verdict. Do NOT attempt to fix pyproject.toml here (S1/S2's job).
# (S2 issue_feedback.md; T2.S1's parallel-with-S2 deferral pattern.)

# GOTCHA #7 — resolve_device_and_models() RETURNS COPIES. Use `dict(defaults)` / `dict(CPU_FALLBACK)`,
# NOT the constant itself, so a caller that mutates the result cannot corrupt the module-level
# constants (and a second call returns the pristine values). The contract says "returns the chosen
# {...}" — always a fresh dict.

# GOTCHA #8 — THE FALLBACK IS CONSTANT, NOT DERIVED FROM `defaults`. When is_cuda_available() is False,
# return CPU_FALLBACK verbatim regardless of what `defaults` contains. `defaults` only flows through on
# the CUDA-available branch. (PRD §4.4 fixes the fallback values.)

# GOTCHA #9 — KEY NAMES: final_model / realtime_model (the contract's terms), NOT model /
# realtime_model_type (RealtimeSTT's kwargs). The daemon's cfg_to_kwargs (P1.M4.T1.S1) does the rename.
# Returning RealtimeSTT kwarg names here would couple this decision module to the recorder API and
# break the contract. (research_realtimestt_api.md §1 for the downstream mapping.)

# GOTCHA #10 — PYTHON 3.12. `X | None` union syntax works at runtime for annotations only with
# `from __future__ import annotations` (stringized). Use it. `Mapping` comes from `typing` (or
# collections.abc in 3.9+; `typing.Mapping` is safe). Do not use 3.13-only syntax.

# GOTCHA #11 — DO NOT ADD cuda_check TO [project.scripts]. The contract says "importable + CLI script";
# `python -m voice_typing.cuda_check` IS the CLI. Adding a console-script entry would require editing
# pyproject.toml (S1's output — out of scope) and a re-sync. install.sh (P1.M6.T1.S1) and the verdict
# step invoke via `-m`. (S1 PRP Gotcha #2; this PRP's Anti-Patterns.)

# GOTCHA #12 — EXIT CODE. `_main()` returns 0 for cuda-ok and 1 for cpu-fallback-required so shell
# callers (install.sh) can branch. BUT cpu-fallback is a VALID degraded mode, not an error: install.sh
# must treat exit 1 as a warning (capture the VERDICT= line / `|| true`), not a hard abort under `set -e`.
# The VERDICT= stdout line is the canonical signal. (Documented in the module + Validation L3.)

# GOTCHA #13 — FULL PATHS in every bash CALL THE PRP MAKES. This machine aliases python3→uv run,
# pip→alias, tmux→zsh plugin. Invoke .venv/bin/python and /home/dustin/.local/bin/uv explicitly.
# (system_context.md §1.)
```

## Implementation Blueprint

### Data models and structure

No ORM / pydantic. The "data model" is two plain-dict constants and the function return shape. Keeping it plain-dict (not a dataclass) is deliberate: the contract specifies `-> dict` and the daemon reads `cfg["device"]` etc.; a dataclass would require the daemon to import `voice_typing.cuda_check.DeviceConfig`, coupling it. The four keys are fixed: `device`, `compute_type`, `final_model`, `realtime_model`.

```python
# Module-level config constants (PRD §4.4 — verbatim).
CUDA_DEFAULTS = {"device": "cuda", "compute_type": "float16",
                 "final_model": "distil-large-v3", "realtime_model": "small.en"}
CPU_FALLBACK  = {"device": "cpu",  "compute_type": "int8",
                 "final_model": "small.en",     "realtime_model": "tiny.en"}

# Return contract of resolve_device_and_models() — always these 4 keys, values per branch:
#   cuda-ok       → copy of CUDA_DEFAULTS (or the caller's `defaults`)
#   cpu-fallback  → copy of CPU_FALLBACK
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs + that the target file does not yet exist (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/__init__.py && echo "ok: voice_typing/ package exists (S1)" \
        || echo "PREFLIGHT FAIL: voice_typing/ missing"
      test ! -e voice_typing/cuda_check.py && echo "ok: cuda_check.py not yet created" \
        || echo "PREFLIGHT FAIL: cuda_check.py already exists"
      test -x .venv/bin/python && echo "ok: .venv/bin/python exists" \
        || echo "PREFLIGHT FAIL: .venv/bin/python missing"
      # Informational — the load-bearing dependency state (S2 may be re-planning):
      if .venv/bin/python -c 'import ctranslate2' 2>/dev/null; then
          echo "ok: ctranslate2 importable (S2 done) — definitive verdict recordable"
      else
          echo "note: ctranslate2 NOT importable (S2 re-plan pending) — record PROVISIONAL verdict, defer definitive"
      fi
      .venv/bin/python -c 'import torch; print("torch.cuda.is_available() =", torch.cuda.is_available())' 2>&1 | tail -1
      # launch_daemon.sh may or may not exist (T2.S1 parallel) — the smoke check only needs its
      # LD_LIBRARY_PATH *computation*, replicated inline in Task 4, so its absence does not block us:
      test -f voice_typing/launch_daemon.sh && echo "ok: launch_daemon.sh present (T2.S1)" \
        || echo "note: launch_daemon.sh not yet present (T2.S1 parallel) — will replicate its LD_LIBRARY_PATH inline"
  - EXPECTED: voice_typing/ exists; cuda_check.py absent; .venv/bin/python present. The ctranslate2
    check is informational — T2.S2 must produce a correct module + a (possibly provisional) verdict
    regardless. torch.cuda.is_available() is expected True on this RTX 3080 Ti host.
  - DO NOT: create daemon.py, edit pyproject.toml, or run uv sync/add.

Task 2: CREATE voice_typing/cuda_check.py (use the `write` tool with EXACTLY the content below)
  - FILE: voice_typing/cuda_check.py
  - CONTENT (verbatim — the module docstring satisfies DOCS [Mode A]; see "why each part" after):
    ----- BEGIN voice_typing/cuda_check.py -----
    """CUDA smoke check + degraded-mode decision for the voice-typing daemon.

    Decides whether the daemon runs on GPU (device="cuda", compute_type="float16",
    final_model="distil-large-v3", realtime_model="small.en") or falls back to CPU
    (device="cpu", compute_type="int8", final_model="small.en",
    realtime_model="tiny.en"), per PRD §4.4.

    This is a REAL smoke check (no mocking). It is meant to run under
    launch_daemon.sh's environment so LD_LIBRARY_PATH (the cuBLAS + cuDNN 9 lib
    dirs) is already set. This module MUST NOT set LD_LIBRARY_PATH itself: the
    dynamic linker reads it only at process exec (ld.so(8)), so setting it inside
    the running process has no effect. launch_daemon.sh (P1.M1.T2.S1) is the single
    sanctioned place to export it; to run this check manually, reproduce that
    wrapper's LD_LIBRARY_PATH export in the shell first (see Validation L3).

    THE DEGRADED-MODE KNOB  (PRD §4.4 — the user-facing surface):
      When ctranslate2.get_cuda_device_count() == 0 — or ctranslate2 cannot be
      imported, or its CUDA init raises for any reason — the daemon MUST run:
          device="cpu", compute_type="int8",
          final_model="small.en", realtime_model="tiny.en"
      and surface device="cpu" in its status (feedback.py state.json, written in
      P1.M3.T2.S1; the daemon status string is wired in P1.M4.T1.S1). The CUDA path
      is the CUDA_DEFAULTS below. Resolve the active config ONCE at daemon startup
      via resolve_device_and_models() and pass the result into the
      AudioToTextRecorder: P1.M4.T1.S1 maps  final_model -> model=  and
      realtime_model -> realtime_model_type=.

    The MUST-HAVE check is ctranslate2 CUDA (the whisper inference engine).
    torch.cuda.is_available() is a NICE-TO-HAVE (only Silero VAD uses torch, and it
    runs fine on CPU); it is reported for diagnostics but does NOT gate the verdict.

    LIMITATION: a "cuda-ok" verdict means ctranslate2 can SEE the GPU.
    get_cuda_device_count() queries the CUDA driver only — it does NOT load cuDNN,
    so a missing libcudnn_ops.so.9 will NOT change this verdict. cuDNN load failures
    surface later, at WhisperModel construction in the daemon. The launch_daemon.sh
    LD_LIBRARY_PATH wrapper is what makes cuDNN findable; if construction still
    fails, the daemon (P1.M4.T1.S1) should re-resolve to CPU.
    """
    from __future__ import annotations

    import sys
    from typing import Mapping

    # PRD §4.4 — the config the daemon WANTS when CUDA works.
    CUDA_DEFAULTS: dict[str, str] = {
        "device": "cuda",
        "compute_type": "float16",
        "final_model": "distil-large-v3",
        "realtime_model": "small.en",
    }

    # PRD §4.4 — the degraded config applied when ctranslate2 sees no CUDA device.
    CPU_FALLBACK: dict[str, str] = {
        "device": "cpu",
        "compute_type": "int8",
        "final_model": "small.en",
        "realtime_model": "tiny.en",
    }


    def _cuda_device_count() -> tuple[int, str]:
        """Return (count, reason). count == 0 on ANY failure means: use CPU.

        Both the import and the call are wrapped so that a missing 'ctranslate2'
        package (faster-whisper is an optional RealtimeSTT extra), a missing CUDA
        driver, or a CUDA-runtime load failure all degrade cleanly to CPU fallback.
        Note: get_cuda_device_count() queries the driver only — it does NOT load
        cuDNN, so a missing libcudnn_ops will NOT make it return 0 here (that error
        surfaces later, at WhisperModel construction in the daemon).
        """
        try:
            import ctranslate2  # local import: isolate the optional/heavy dependency
        except Exception as exc:  # ImportError, OSError from a failed dlopen, ...
            return 0, f"ctranslate2 import failed: {exc!r}"
        try:
            count = int(ctranslate2.get_cuda_device_count())
        except Exception as exc:  # RuntimeError / low-level CUDA errors
            return 0, f"get_cuda_device_count() raised: {exc!r}"
        if count <= 0:
            return 0, "no CUDA-capable device/driver visible to ctranslate2"
        return count, f"{count} cuda device(s) visible to ctranslate2"


    def _ctranslate2_version() -> str:
        """ctranslate2 version string, or '<not installed>' if it can't be imported."""
        try:
            import ctranslate2
            return getattr(ctranslate2, "__version__", "<unknown>")
        except Exception:
            return "<not installed>"


    def _torch_cuda_available() -> bool:
        """Nice-to-have probe for Silero VAD diagnostics. False on any failure.

        Does NOT gate the verdict — Silero VAD runs fine on CPU.
        """
        try:
            import torch
            return bool(torch.cuda.is_available())
        except Exception:
            return False


    def is_cuda_available() -> bool:
        """True iff ctranslate2 sees >= 1 CUDA device.

        This is the MUST-HAVE check (the whisper inference engine). It does NOT
        consider torch.cuda — see module docstring.
        """
        return _cuda_device_count()[0] >= 1


    def resolve_device_and_models(
        defaults: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Resolve {device, compute_type, final_model, realtime_model} for the daemon.

        If ctranslate2 CUDA is available, return a copy of `defaults` (or
        CUDA_DEFAULTS when `defaults` is None). Otherwise apply the PRD §4.4 CPU
        fallback (CPU_FALLBACK) REGARDLESS of `defaults`. Always returns a fresh
        dict the caller may mutate freely.

        Consumed once at daemon startup by the recorder wiring (P1.M4.T1.S1),
        which maps final_model -> model= and realtime_model -> realtime_model_type=.
        """
        if defaults is None:
            defaults = CUDA_DEFAULTS
        if is_cuda_available():
            return dict(defaults)
        return dict(CPU_FALLBACK)


    def _verdict() -> str:
        return "cuda-ok" if is_cuda_available() else "cpu-fallback-required"


    def _main() -> int:
        """CLI smoke check. Prints diagnostics + a one-line VERDICT.

        Output lines (greppable):
          ctranslate2_version=<ver|<not installed>>
          cuda_device_count=<int>
          torch_cuda_available=<True|False>
          VERDICT=<cuda-ok|cpu-fallback-required>
          # <reason>
          # resolved: device=.. compute_type=.. final_model=.. realtime_model=..

        Exit code mirrors the verdict: 0 = cuda-ok, 1 = cpu-fallback-required.
        NOTE: cpu-fallback-required is a VALID degraded mode, not an error —
        callers under `set -e` should capture the VERDICT= line or `|| true`.
        """
        count, reason = _cuda_device_count()
        print(f"ctranslate2_version={_ctranslate2_version()}")
        print(f"cuda_device_count={count}")
        print(f"torch_cuda_available={_torch_cuda_available()}")
        print(f"VERDICT={_verdict()}")
        print(f"# {reason}")
        cfg = resolve_device_and_models()
        print(
            f"# resolved: device={cfg['device']} compute_type={cfg['compute_type']} "
            f"final_model={cfg['final_model']} realtime_model={cfg['realtime_model']}"
        )
        return 0 if is_cuda_available() else 1


    if __name__ == "__main__":
        sys.exit(_main())
    ----- END voice_typing/cuda_check.py -----
  - WHY each part:
      * module docstring: the DOCS [Mode A] requirement — documents the degraded-mode knob
        (the four CPU values), the user-facing surfaces (feedback.py / daemon status), the
        must-have-vs-nice-to-have distinction, the LD_LIBRARY_PATH invariant, and the
        cuda-ok-does-not-mean-model-constructs limitation.
      * `from __future__ import annotations`: makes `Mapping[str, str] | None` a stringized
        annotation (valid on 3.12 without runtime evaluation). (Gotcha #10.)
      * `CUDA_DEFAULTS` / `CPU_FALLBACK`: PRD §4.4 verbatim. (Gotcha #8.)
      * `_cuda_device_count()`: the lazy-import + double try/except probe (Gotcha #2, #4).
        Returns a reason string for the verdict detail line + cuda_verdict.md.
      * `_ctranslate2_version()` / `_torch_cuda_available()`: lazy + wrapped; safe when the
        deps are absent (the S2 state). (Gotcha #2.)
      * `is_cuda_available()`: gates on ctranslate2 ONLY (Gotcha #3).
      * `resolve_device_and_models()`: the contract signature; returns copies (Gotcha #7);
        fallback is constant (Gotcha #8); keys are final_model/realtime_model (Gotcha #9).
      * `_main()` / `__main__`: the CLI; prints greppable lines + VERDICT; exit 0/1 (Gotcha #12).
  - DO NOT: add top-level `import ctranslate2`/`import torch`; set LD_LIBRARY_PATH; rename keys
    to model/realtime_model_type; return the constants directly (return copies); add a
    [project.scripts] entry (out of scope — Gotcha #11); narrow the except to ImportError.

Task 3: RUN the smoke check under launch_daemon.sh's env + RECORD the verdict
  - This produces the SECOND deliverable: plan/001_be48c74bc590/architecture/cuda_verdict.md.
  - STEP 3a — compute LD_LIBRARY_PATH EXACTLY as launch_daemon.sh does (replicate its one-liner):
      cd /home/dustin/projects/voice-typing
      PY=.venv/bin/python
      if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))' 2>/dev/null)"; then
          echo "LD_LIBRARY_PATH computed: $CUDA_LIBS"
      else
          CUDA_LIBS=""   # nvidia wheels not installed (S2 pending) — run without override; verdict will be cpu-fallback
          echo "note: nvidia wheels not importable — running smoke check WITHOUT LD_LIBRARY_PATH (verdict unaffected; ctranslate2 not installed anyway)"
      fi
  - STEP 3b — run the smoke check with that env, capturing output:
      OUT=$(LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$PY" -m voice_typing.cuda_check 2>&1; echo "exit=$?")
      echo "$OUT"
      # The VERDICT line is the load-bearing artifact:
      echo "$OUT" | grep '^VERDICT='
  - STEP 3c — WRITE plan/001_be48c74bc590/architecture/cuda_verdict.md from the captured output.
      Content template (fill in the ACTUAL values from $OUT — do NOT invent them):
        --- BEGIN cuda_verdict.md ---
        # CUDA verdict — voice-typing machine state

        **Recorded:** <YYYY-MM-DD>  •  **Host:** <from `hostname`>  •  **GPU:** <from `nvidia-smi --query-gpu=name --format=csv,noheader`>
        **Run as:** `LD_LIBRARY_PATH=<launch_daemon.sh value> .venv/bin/python -m voice_typing.cuda_check`
        (LD_LIBRARY_PATH replicated from voice_typing/launch_daemon.sh — P1.M1.T2.S1.)

        ## Raw smoke-check output

        ```
        <paste the full $OUT here, including the exit= line>
        ```

        ## VERDICT

        **<cuda-ok | cpu-fallback-required>**

        Resolved daemon config: device=<..>  compute_type=<..>  final_model=<..>  realtime_model=<..>

        ## Meaning for the daemon (P1.M4.T1.S1)

        - The recorder wiring calls `resolve_device_and_models()` once at startup and feeds the
          result into `AudioToTextRecorder(model=final_model, realtime_model_type=realtime_model,
          device=device, compute_type=compute_type)`.
        - <If cuda-ok: GPU path; ~2-4 GB VRAM budget on the RTX 3080 Ti per system_context.md §1.
           If cpu-fallback-required: degraded CPU mode; daemon MUST log it and surface
           device="cpu" in status (PRD §4.4).>
        - <If PROVISIONAL (ctranslate2 not installed — S2 re-plan pending): state so here. The
           torch.cuda line shows whether the GPU is visible to torch (a positive indicator for
           the eventual cuda path). RE-RUN this smoke check after S2 completes to capture the
           definitive verdict.>

        ## Notes / caveats

        - "cuda-ok" means ctranslate2 SEES the GPU (get_cuda_device_count is a driver query; it
          does NOT load cuDNN). cuDNN load failures surface later at WhisperModel construction;
          the launch_daemon.sh LD_LIBRARY_PATH wrapper is what makes cuDNN findable.
        - torch.cuda.is_available() is informational only (Silero VAD); it does not gate the verdict.
        --- END cuda_verdict.md ---
  - IF ctranslate2 is NOT importable (S2 pending — Task 1 preflight said so): the script will
    print VERDICT=cpu-fallback-required with reason "ctranslate2 import failed: ...". Record that
    PROVISIONALLY and fill the "If PROVISIONAL" block: note torch.cuda.is_available()'s actual value
    (expected True on this host), the S2 blocker, and that the definitive verdict requires re-running
    after S2's successful re-plan. This is the deferral pattern (Gotcha #6) — NOT a failure of T2.S2.
  - DO NOT: edit pyproject.toml to "fix" the missing ctranslate2 (S1/S2's job); mock anything; or
    write the verdict to any path other than plan/001_be48c74bc590/architecture/cuda_verdict.md.

Task 4: VALIDATE — run the Validation Loop L1–L5 below. Fix until all applicable gates pass.
  - If S2 is NOT yet done (ctranslate2 absent), L4 (real cuda-ok verdict) is necessarily provisional;
    L1/L2/L5 still fully apply and the module's correctness is provable WITHOUT ctranslate2 (the
    try/except path IS the cpu-fallback logic the contract requires). Note the provisional state in
    the implementation report.
  - No git commit from T2.S2 unless the orchestrator directs it. If asked: message
    "P1.M1.T2.S2: cuda_check.py smoke check + resolve_device_and_models + recorded verdict".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the lazy-import + double try/except probe (the heart of the module).
#   Wrapping BOTH the import and the call means: missing package (today's S2 state),
#   failed dlopen, missing driver, or a raised RuntimeError ALL route to count==0 → CPU
#   fallback. The broad `except Exception` is INTENTIONAL (its only effect is the safe
#   degradation). Do NOT narrow it.
def _cuda_device_count() -> tuple[int, str]:
    try:
        import ctranslate2
    except Exception as exc:
        return 0, f"ctranslate2 import failed: {exc!r}"
    try:
        count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        return 0, f"get_cuda_device_count() raised: {exc!r}"
    return (count, "...") if count >= 1 else (0, "no CUDA device visible")

# PATTERN 2 — the resolver: defaults flow through ONLY on the cuda branch; fallback is constant.
def resolve_device_and_models(defaults=None):
    if defaults is None:
        defaults = CUDA_DEFAULTS
    if is_cuda_available():
        return dict(defaults)      # caller's desired CUDA config (or CUDA_DEFAULTS)
    return dict(CPU_FALLBACK)      # PRD §4.4 fixed values — NOT derived from defaults

# PATTERN 3 — greppable CLI output + verdict-mirroring exit code.
#   Downstream (install.sh P1.M6.T1.S1) does `... | grep '^VERDICT='`. The exit code lets
#   shell `if`-branch, but cpu-fallback is valid so `set -e` callers must `|| true`.
print(f"VERDICT={'cuda-ok' if is_cuda_available() else 'cpu-fallback-required'}")
return 0 if is_cuda_available() else 1
```

### Integration Points

```yaml
DOWNSTREAM — P1.M4.T1.S1 (daemon recorder wiring; THE consumer):
  - Imports: `from voice_typing.cuda_check import resolve_device_and_models, is_cuda_available`.
  - Calls resolve_device_and_models() ONCE at startup (before constructing AudioToTextRecorder);
    caching is unnecessary (one call). Maps the returned dict:
        recorder_kwargs["model"]               = cfg["final_model"]
        recorder_kwargs["realtime_model_type"] = cfg["realtime_model"]
        recorder_kwargs["device"]              = cfg["device"]
        recorder_kwargs["compute_type"]        = cfg["compute_type"]
  - MUST surface cfg["device"] (cpu|cuda) in the daemon status (PRD §4.4) via feedback.py (P1.M3.T2.S1).
  - CRITICAL: even when cfg["device"]=="cuda", WhisperModel construction can still fail if cuDNN is
    missing (cuda-ok does not guarantee construction — see Limitation). P1.M4.T1.S1 should catch a
    construction RuntimeError and re-resolve to CPU (call resolve_device_and_models() with a
    force-cpu flag, or just construct with CPU_FALLBACK). That recovery logic is P1.M4.T1.S1's, not T2.S2's.

DOWNSTREAM — P1.M6.T1.S1 (install.sh):
  - Runs the smoke check (possibly via launch_daemon.sh's env or by replicating its LD_LIBRARY_PATH)
    and reads the VERDICT= line to print a user-facing "GPU mode" / "CPU (degraded) mode" notice.
  - MUST treat exit 1 (cpu-fallback) as a warning, not a hard failure (|| true / capture stdout).

DOWNSTREAM — P1.M3.T2.S1 (feedback.py / status):
  - The daemon writes cfg["device"] into state.json's status so voicectl status + tmux status.sh can
    show "cpu" vs "cuda". T2.S2 only supplies the decision; the surfacing is the daemon/feedback's job.

PARALLEL — P1.M1.T2.S1 (launch_daemon.sh):
  - T2.S2 runs UNDER launch_daemon.sh's LD_LIBRARY_PATH (replicated inline in Task 3). It does NOT
    modify or import launch_daemon.sh. If launch_daemon.sh is not yet present at T2.S2 time (parallel),
    the inline replication in Task 3a is self-sufficient.

CONDITIONAL — nothing in T2.S2 modifies pyproject.toml, .gitignore, PRD.md, tasks.json, prd_snapshot.md,
or any file under voice_typing/ other than creating voice_typing/cuda_check.py, plus the recorded
plan/001_be48c74bc590/architecture/cuda_verdict.md.

BUILD ARTIFACTS:
  - T2.S2 creates NO dist/, NO uv.lock changes, NO .venv changes, NO [project.scripts] addition.
    cuda_check.py is a plain source module invoked via `python -m`. `uv sync`/`uv build` are NOT run.
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases). Run from `/home/dustin/projects/voice-typing`. L1/L2/L5 are
> ALWAYS runnable (the module is correct independent of ctranslate2 being installed — that is the point
> of the lazy-import design). L3 (the real smoke check) and L4 (definitive verdict) require ctranslate2
> to be importable; if S2's re-plan is not yet done, run L3 (it will print cpu-fallback-required — which
> IS the correct output for the current state) and record L4 PROVISIONALLY, deferring the definitive verdict.

### Level 1: Syntax + import-cleanness (no deps needed)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f voice_typing/cuda_check.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile voice_typing/cuda_check.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
# THE KEY TEST: the module imports cleanly EVEN WHEN ctranslate2 is absent (lazy imports):
"$PY" -c "import voice_typing.cuda_check as m; print('L1 import OK'); print(' public:', m.is_cuda_available, m.resolve_device_and_models)" \
  && echo "L1 PASS: module importable with current (ctranslate2-absent) venv" \
  || echo "L1 FAIL: a top-level heavy import leaked (must be local+wrapped — Gotcha #2)"
# Expected: file present, py_compile clean, import OK with the public API visible. NO top-level
# `import ctranslate2`/`import torch` (grep must find them only INSIDE functions).
! grep -nE '^(import|from) (ctranslate2|torch)' voice_typing/cuda_check.py && echo "L1 PASS: no top-level heavy imports" \
  || echo "L1 FAIL: top-level heavy import found (move it inside the function — Gotcha #2)"
```

### Level 2: API contract + decision logic (no ctranslate2 needed — exercises the False branch live)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" - <<'PYEOF'
from voice_typing.cuda_check import (
    is_cuda_available, resolve_device_and_models, CUDA_DEFAULTS, CPU_FALLBACK,
)
# (1) signatures / return types
assert callable(is_cuda_available) and isinstance(is_cuda_available(), bool), "is_cuda_available -> bool"
# (2) return shape: exactly the 4 contract keys
cfg = resolve_device_and_models()
assert set(cfg.keys()) == {"device", "compute_type", "final_model", "realtime_model"}, cfg.keys()
# (3) branch consistency: verdict drives the values
import voice_typing.cuda_check as m
if is_cuda_available():
    assert cfg == CUDA_DEFAULTS, ("cuda branch should return CUDA_DEFAULTS", cfg)
else:
    assert cfg == CPU_FALLBACK, ("cpu branch should return CPU_FALLBACK", cfg)
# (4) fallback is CONSTANT regardless of defaults (Gotcha #8)
assert resolve_device_and_models({"device": "cuda", "compute_type": "float16",
        "final_model": "large-v3-turbo", "realtime_model": "X"}) == (CUDA_DEFAULTS if is_cuda_available() else CPU_FALLBACK)
# (5) returns COPIES (Gotcha #7): mutating the result does not corrupt the constant
c = resolve_device_and_models(); c["device"] = "MUTATED"
assert CPU_FALLBACK["device"] == "cpu" and CUDA_DEFAULTS["device"] == "cuda", "constant corrupted (not a copy)"
# (6) defaults flow through ONLY on the cuda branch
custom = {"device":"cuda","compute_type":"float16","final_model":"large-v3-turbo","realtime_model":"small.en"}
if is_cuda_available():
    assert resolve_device_and_models(custom) == custom, "cuda branch should honor caller defaults"
else:
    assert resolve_device_and_models(custom) == CPU_FALLBACK, "cpu branch must ignore caller defaults"
print("L2 PASS: API contract + decision logic OK (verdict branch =", is_cuda_available(), ")")
PYEOF
# Expected: "L2 PASS: ...". On the current ctranslate2-absent venv, is_cuda_available() is False, so
# this live-exercises the CPU_FALLBACK branch — which is exactly the path the contract requires.
```

### Level 3: The REAL smoke check (CLI output + exit code) — run under launch_daemon.sh's env

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# Replicate launch_daemon.sh's LD_LIBRARY_PATH computation (the nvidia.*.lib one-liner):
if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))' 2>/dev/null)"; then
    echo "L3 LD_LIBRARY_PATH computed: $CUDA_LIBS"
else
    CUDA_LIBS=""; echo "L3 note: nvidia wheels not importable (S2 pending) — running WITHOUT LD_LIBRARY_PATH override"
fi
OUT=$(LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$PY" -m voice_typing.cuda_check 2>&1; echo "exit=$?")
echo "$OUT"
echo "$OUT" | grep -qE '^ctranslate2_version='  && echo "L3a PASS: ctranslate2_version line"  || echo "L3 FAIL: no ctranslate2_version line"
echo "$OUT" | grep -qE '^cuda_device_count=[0-9]+$' && echo "L3b PASS: cuda_device_count line" || echo "L3 FAIL: no cuda_device_count line"
echo "$OUT" | grep -qE '^torch_cuda_available=(True|False)$' && echo "L3c PASS: torch_cuda_available line" || echo "L3 FAIL: no torch line"
echo "$OUT" | grep -qE '^VERDICT=(cuda-ok|cpu-fallback-required)$' && echo "L3d PASS: VERDICT line well-formed" || echo "L3 FAIL: no/ malformed VERDICT line"
# exit code mirrors verdict (Gotcha #12):
VERDICT=$(echo "$OUT" | grep -oE '^VERDICT=(cuda-ok|cpu-fallback-required)$' | cut -d= -f2)
EXIT=$(echo "$OUT" | grep -oE 'exit=[0-9]+$' | cut -d= -f2)
{ [ "$VERDICT" = "cuda-ok" ] && [ "$EXIT" = "0" ]; } || { [ "$VERDICT" = "cpu-fallback-required" ] && [ "$EXIT" = "1" ]; } \
  && echo "L3e PASS: exit code ($EXIT) matches verdict ($VERDICT)" || echo "L3 FAIL: exit/verdict mismatch"
# Cross-check the verdict against a DIRECT ctranslate2 probe (the must-have), when importable:
if "$PY" -c 'import ctranslate2' 2>/dev/null; then
    DIRECT=$("$PY" -c "import ctranslate2; print('cuda-ok' if ctranslate2.get_cuda_device_count()>=1 else 'cpu-fallback-required')")
    [ "$DIRECT" = "$VERDICT" ] && echo "L3f PASS: verdict matches direct ctranslate2 probe ($VERDICT)" || echo "L3 FAIL: verdict disagrees with direct probe"
else
    echo "L3f note: ctranslate2 not importable (S2 pending) — verdict=cpu-fallback-required is CORRECT for this state; definitive verdict deferred"
fi
# Expected: all 4 output lines present + well-formed; VERDICT is cpu-fallback-required UNTIL S2 lands
# ctranslate2, then cuda-ok (RTX 3080 Ti visible). exit matches verdict.
```

### Level 4: Recorded verdict file exists + is faithful to the smoke output

```bash
cd /home/dustin/projects/voice-typing
F=plan/001_be48c74bc590/architecture/cuda_verdict.md
test -f "$F" && echo "L4a PASS: cuda_verdict.md exists" || echo "L4 FAIL: cuda_verdict.md missing"
grep -qi 'VERDICT' "$F" && echo "L4b PASS: mentions VERDICT" || echo "L4 FAIL: no VERDICT recorded"
grep -qiE 'cuda-ok|cpu-fallback-required' "$F" && echo "L4c PASS: records a verdict value" || echo "L4 FAIL: no verdict value"
# Faithfulness: the verdict value in the file must MATCH what the script prints right now:
PY=.venv/bin/python
NOW=$("$PY" -c "from voice_typing.cuda_check import _verdict; print(_verdict())")
grep -q "$NOW" "$F" && echo "L4d PASS: recorded verdict ($NOW) matches current script output" || echo "L4 FAIL: recorded verdict stale vs current ($NOW)"
grep -qi 'resolve_device_and_models\|final_model\|device=' "$F" && echo "L4e PASS: records resolved config" || echo "L4 FAIL: no resolved config"
# Provisional-state honesty (when S2 pending):
"$PY" -c 'import ctranslate2' 2>/dev/null || grep -qiE 'provisional|re-run|S2' "$F" \
  && echo "L4f PASS: provisional state flagged (ctranslate2 absent)" || echo "L4 note: ctranslate2 present, no provisional flag needed"
# Expected: file exists, records the actual (or provisional) verdict + resolved config + run method,
# and the recorded verdict matches a fresh run of the script.
```

### Level 5: Scope guards — only cuda_check.py + cuda_verdict.md created; read-only files untouched

```bash
cd /home/dustin/projects/voice-typing
# The TWO legitimate outputs:
test -f voice_typing/cuda_check.py && echo "L5 PASS: cuda_check.py exists" || echo "L5 FAIL"
test -f plan/001_be48c74bc590/architecture/cuda_verdict.md && echo "L5 PASS: cuda_verdict.md exists" || echo "L5 FAIL"
# Nothing else created:
for f in voice_typing/daemon.py voice_typing/config.py voice_typing/typing_backends.py \
         voice_typing/feedback.py voice_typing/textproc.py voice_typing/ctl.py install.sh \
         config.toml systemd/voice-typing.service; do
  test ! -e "$f" && echo "absent (ok): $f" || echo "L5 SCOPE WARNING: $f exists (out of scope?)"
done
# Models NOT prefetched (T3's job):
ls ~/.cache/huggingface/hub 2>/dev/null | grep -iq whisper && echo "L5 SCOPE WARNING: models prefetched (T3's job)" || echo "absent (ok): no whisper models"
# cuda_check.py is NOT registered as a console script (Gotcha #11):
grep -q 'cuda_check' pyproject.toml && echo "L5 FAIL: cuda_check leaked into pyproject [project.scripts]" || echo "L5 PASS: no cuda_check in pyproject"
# Read-only files UNCHANGED:
git status --short
git diff --exit-code -- PRD.md plan/001_be48c74bc590/tasks.json .gitignore pyproject.toml && echo "L5 PASS: read-only files unchanged" || echo "L5 FAIL: a read-only file was modified"
# git status should show ONLY: voice_typing/cuda_check.py (new) + plan/.../architecture/cuda_verdict.md (new).
# (uv.lock / launch_daemon.sh may show if S2/T2.S1 ran in parallel — those are NOT T2.S2's writes.)
# Expected: cuda_check.py + cuda_verdict.md are the sole T2.S2 new files; PRD/tasks/.gitignore/pyproject
# byte-identical to before; no daemon/config/typing_backends/feedback/textproc/ctl/install.sh/systemd/models.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: file present, `py_compile` clean, module imports with the ctranslate2-absent venv, NO top-level heavy imports.
- [ ] L2: `is_cuda_available() -> bool`; `resolve_device_and_models()` returns exactly `{device, compute_type, final_model, realtime_model}`; branch consistency; fallback is constant; results are copies; defaults flow through only on the cuda branch.
- [ ] L3: CLI prints `ctranslate2_version=`/`cuda_device_count=`/`torch_cuda_available=`/`VERDICT=`; VERDICT is `cuda-ok` or `cpu-fallback-required`; exit code mirrors it; (if ctranslate2 importable) verdict matches a direct `get_cuda_device_count()` probe.
- [ ] L4: `plan/001_be48c74bc590/architecture/cuda_verdict.md` records the verdict + resolved config + run method; recorded verdict matches a fresh run; provisional state flagged if ctranslate2 absent.
- [ ] L5: only `cuda_check.py` + `cuda_verdict.md` created; no out-of-scope files; read-only files unchanged; cuda_check NOT in pyproject.

### Feature Validation
- [ ] The verdict gates on **ctranslate2** (must-have), NOT torch (nice-to-have) — verified by L2/L3.
- [ ] The PRD §4.4 CPU fallback (`cpu`/`int8`/`small.en`/`tiny.en`) is applied whenever `is_cuda_available()` is False — verified by L2.
- [ ] The module runs under `launch_daemon.sh`'s `LD_LIBRARY_PATH` env (replicated in L3) and does NOT set it itself — verified by L1 grep + L3.
- [ ] No mocking — the check probes the real machine (L3 runs the actual ctranslate2/torch when present).
- [ ] The recorded verdict reflects the machine's actual state (or a clearly-flagged provisional state when S2 is pending) — verified by L4.

### Code Quality / Scope Validation
- [ ] Module docstring documents the degraded-mode knob (PRD §4.4) — the DOCS [Mode A] requirement.
- [ ] Public API is exactly the two contract functions (private helpers are `_`-prefixed).
- [ ] All heavy imports are local + wrapped (lazy) — module import never fails on a missing dep.
- [ ] No `daemon.py`/`config.py`/`typing_backends.py`/`feedback.py`/`textproc.py`/`ctl.py`/`install.sh`/`systemd`/model prefetch.
- [ ] `pyproject.toml`, `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md` UNCHANGED.
- [ ] No bare `python`/`pip`/`uv`/`tmux` in any validation command (all full-pathed; `$PY` is `.venv/bin/python`).
- [ ] No `uv sync` / `uv add` / `uv build` / `uv lock` executed (resolve+install is S2; build is S1).

### Documentation & Deployment
- [ ] cuda_verdict.md is self-contained: raw output, verdict, resolved config, meaning for the daemon, caveats.
- [ ] The provisional-verdict path (if taken) names the S2 blocker, the torch.cuda indicator, and the re-run instruction.
- [ ] If asked to commit: message "P1.M1.T2.S2: cuda_check.py smoke check + resolve_device_and_models + recorded verdict".

---

## Anti-Patterns to Avoid

- ❌ Don't gate the verdict on `torch.cuda.is_available()` — torch is nice-to-have (Silero VAD, CPU-fine); ctranslate2 is the must-have (the inference engine). Gating on torch yields false "cuda-ok" when torch sees the GPU but ctranslate2 doesn't (Gotcha #3, research §3).
- ❌ Don't put `import ctranslate2` / `import torch` at module top level — a missing dep (today's S2 state) or a dlopen failure makes `import voice_typing.cuda_check` itself raise, breaking the daemon import too. Keep them local + wrapped inside the probe functions (Gotcha #2).
- ❌ Don't narrow the `except` to `ImportError` only — `get_cuda_device_count()` can raise `RuntimeError`/low-level CUDA errors; `import` can raise `OSError` from dlopen. The broad `except Exception` is correct (its only effect is CPU fallback). (Gotcha #4.)
- ❌ Don't set `LD_LIBRARY_PATH` inside cuda_check.py — it has no effect at runtime (ld.so reads it at exec); launch_daemon.sh is the sole sanctioned place. Replicate the wrapper's export in the shell when running the check (Gotcha #1, research §2).
- ❌ Don't derive the fallback from `defaults` — CPU_FALLBACK is FIXED by PRD §4.4. `defaults` flows through only on the cuda branch (Gotcha #8).
- ❌ Don't return the module constants directly — return `dict(...)` copies so callers can't corrupt them (Gotcha #7).
- ❌ Don't rename the keys to `model`/`realtime_model_type` (RealtimeSTT's kwargs) — the contract specifies `final_model`/`realtime_model`; the daemon's cfg_to_kwargs (P1.M4.T1.S1) does the rename. Coupling here breaks the abstraction (Gotcha #9).
- ❌ Don't add a `cuda-check` entry to `[project.scripts]` — `python -m voice_typing.cuda_check` is the CLI; editing pyproject is out of scope and needs a re-sync (Gotcha #11).
- ❌ Don't mock the ctranslate2 probe in the smoke check — the contract says "Mock nothing (this is the real smoke check)". The try/except is for ROBUSTNESS (degrade to fallback), not for faking a result.
- ❌ Don't edit `pyproject.toml` to "fix" the missing ctranslate2 — that's S1/S2's re-plan (the `realtimestt[faster-whisper]` extra). T2.S2 records a provisional verdict and defers; it does not change the dependency declaration (Gotcha #6).
- ❌ Don't construct a `WhisperModel` in the smoke check to "really" verify CUDA — that is heavy (loads weights) and out of scope; `get_cuda_device_count()` is the sanctioned lightweight probe (research Q6). Model construction is the daemon's concern (P1.M4.T1.S1).
- ❌ Don't create `daemon.py`/`config.py`/`install.sh`/`systemd`/models — those are P1.M4/P1.M2/P1.M6/P1.M1.T3. T2.S2 is ONE source file + ONE recorded verdict file.
- ❌ Don't use bare `python`/`pip`/`uv`/`tmux` in validation commands (zsh aliases shadow them); use `.venv/bin/python` and `/home/dustin/.local/bin/uv` (Gotcha #13).
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or `pyproject.toml` (READ-ONLY / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a single ~140-line Python module whose entire content is given verbatim, plus a recorded-verdict file produced by running it. Every ctranslate2/torch API behavior the decision logic depends on is documented and cross-checked in `research/ctranslate2_cuda_api_verification.md` (Q1–Q6): `get_cuda_device_count()` is module-level, returns an int, returns 0 with no GPU, does NOT load cuDNN (so a missing libcudnn_ops doesn't change the verdict — it surfaces later at construction), and can RAISE on CUDA-runtime failures → the double try/except treating any exception as CPU fallback is correct and intentional; `ctranslate2.__version__` is the right attribute; `import` is lazy/no-init; `torch.cuda.is_available()` returns bool and never raises; `cpu`+`int8` and `cuda`+`float16` are known-good faster-whisper combos; and `get_cuda_device_count()` is itself the lightweight probe (no model load). The downstream key mapping (`final_model -> model=`, `realtime_model -> realtime_model_type=`) is verified against the installed RealtimeSTT v1.0.2 `FasterWhisperEngine`. The lazy-import + wrapped-probe design means the module is fully testable NOW (it returns `cpu-fallback-required` against the current ctranslate2-absent venv — L2 live-exercises the fallback branch), so the code's correctness is provable independent of S2's timing.

The −1 residual risk is **scheduling/dependency, not code correctness**: the definitive `cuda-ok` verdict (L4) requires S2's successful re-plan (the `realtimestt[faster-whisper]` extras fix) to make `ctranslate2` importable. If S2 is still pending at implementation time, L3 correctly prints `cpu-fallback-required` (the right output for the current state) and L4 records a provisional verdict that flags the S2 blocker and the re-run instruction — mirroring T2.S1's parallel-with-S2 deferral pattern. A secondary, documented risk: `cuda-ok` does not guarantee `WhisperModel` construction succeeds (cuDNN load is a separate, later step mitigated by launch_daemon.sh's LD_LIBRARY_PATH); the module docstring and Integration Points both state this, and the daemon (P1.M4.T1.S1) owns the construction-failure → CPU re-resolve recovery. No pyproject/build/install changes are made, so there is no build-surface risk.
