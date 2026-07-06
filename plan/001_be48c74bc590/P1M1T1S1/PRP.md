# PRP — P1.M1.T1.S1: Scaffold pyproject.toml + package layout + console scripts

## Goal

**Feature Goal**: Turn the empty `voice-typing` git repo into a valid, buildable uv/Python 3.12 project that declares the runtime dependency set (RealtimeSTT + CUDA cuDNN-9 wheels) and the two console-script entry points, with an importable `voice_typing` package skeleton — but WITHOUT installing any heavy dependencies (that is the next subtask, S2).

**Deliverable**: Two files, both committed-ready:
1. `pyproject.toml` — a complete, PEP 621-compliant project file: `[build-system]` (hatchling), `[project]` (name, version, `requires-python`, the 4 runtime deps, the 2 `[project.scripts]`), and `[tool.hatch.build.targets.wheel]`.
2. `voice_typing/__init__.py` — empty package marker (module docstring only).

**Success Definition**: (a) `uv init --bare --python 3.12` runs cleanly; (b) the authored `pyproject.toml` parses with stdlib `tomllib` and passes the structural assertions in Validation L1; (c) `import voice_typing` works from the repo root with no install; (d) `uv build` produces a wheel whose `entry_points.txt` contains both console scripts and whose `METADATA` lists `Requires-Python: <3.13,>=3.12` plus all 4 `Requires-Dist`. The heavy `uv sync` (resolve + install realtimestt/cuda) is explicitly deferred to **S2** and is NOT run here.

## User Persona

Not applicable (developer/agent-facing build artifact; no end-user surface). This is a pure project-bootstrap subtask.

## Why

- **Enables every later module.** All downstream code (`daemon.py`, `ctl.py`, `config.py`, …) is imported as `voice_typing.*`. The package skeleton + importable name must exist before P1.M2 onward.
- **Locks the CUDA correctness decision early.** `nvidia-cudnn-cu12==9.*` is pinned here (research-corrected from PRD §4.4, which left it unpinned). faster-whisper/CTranslate2 require cuDNN 9; an unpinned cuDNN can pull 10/11 and break CUDA init in S2/T2. Declaring it now makes S2's resolution deterministic.
- **Declares the two installed entry points** that the system depends on at runtime: `.venv/bin/voicectl` (called by `hypr-binds.conf` in Phase 2 and by the user) and `voice-typing-daemon`.
- **Scope discipline:** S1 scaffolds/declares only. S2 resolves+installs. Keeping install out of S1 means a fast, deterministic, network-light gate that cannot fail on a flaky multi-GB CUDA download.

## What

Produce a valid, buildable Python 3.12 uv project with the dependency + script declarations, and the package `__init__`. No runtime behavior change, no config, no README, no systemd, no source modules beyond `__init__.py`.

### Success Criteria

- [ ] `uv init --bare --python 3.12` succeeds and leaves a minimal `pyproject.toml`.
- [ ] `pyproject.toml` is authored to: `name="voice-typing"`, `version="0.1.0"`, `requires-python=">=3.12,<3.13"`, the exact 4 `dependencies`, and the 2 `[project.scripts]` (`voicectl`, `voice-typing-daemon`).
- [ ] `pyproject.toml` includes `[build-system]` (hatchling) + `[tool.hatch.build.targets.wheel] packages=["voice_typing"]` (REQUIRED — see Known Gotchas).
- [ ] `voice_typing/__init__.py` exists (module docstring only; no logic).
- [ ] Validation L1 (tomllib structure), L2 (import), L3 (`uv build` entry_points/METADATA) all pass.
- [ ] NO `uv sync` / `uv lock` / `uv add` / torch / README / config.toml created (those are out of scope).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement this from the contract + the verified `uv` behaviors documented below. Every command is given with full paths (machine has zsh aliases that shadow `python3`/`pip`/`tmux`).

### Documentation & References

```yaml
# MUST READ before authoring pyproject.toml
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: §1 verified machine facts (.venv Python 3.12.10 NO packages, uv 0.7.11 at /home/dustin/.local/bin/uv, shell aliases → full paths), §2 target file map, §4 the authoritative cuDNN-9 correction.
  critical: "Always use explicit paths in bash: /home/dustin/.local/bin/uv, .venv/bin/python, /usr/bin/tmux. uv at 0.7.11."

- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md
  why: §2 is the source for the cuDNN pin. faster-whisper README (authoritative): 'latest ctranslate2 supports CUDA 12 and cuDNN 9'. Shows `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*`.
  critical: "cuDNN MUST be pinned to 9.x. PRD §4.4 left it unpinned — this PRP corrects it. Unpinned pulls cuDNN 10/11 → CTranslate2 mismatch → S2/T2 CUDA init fails."

- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md
  why: §6 lists faster-whisper requirements.txt pins → `huggingface_hub>=0.23`. That is the source of the `huggingface_hub>=0.23` lower bound used here.
  critical: "huggingface_hub lower bound is from faster-whisper's own requirements.txt; do not drop or raise without re-checking."

- file: PRD.md
  why: §4.1 repo layout (flat voice_typing/ package, pyproject.toml, uv.lock), §4.4 (cuDNN unpinned — to be corrected), §4.8 ('installed console-script entry point'), §5 install steps (step 3 = `uv init --bare --python 3.12`).
  critical: "PRD §4.8 explicitly wants an INSTALLED console-script entry point → pyproject MUST be a buildable package, not a bare app (see Gotchas)."

- docfile: plan/001_be48c74bc590/P1M1T1S1/research/uv_build_system_verification.md
  why: Empirical transcript of the uv experiments that PROVE the build-system requirement and the entry-points-to-nonexistent-modules behavior. Read if anything about hatchling/scripts feels uncertain.
  section: "Findings #2 and #3 are the load-bearing ones."
```

### Current Codebase tree

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*'` in repo root. Current verified state:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main, 2 commits
├── .gitignore                  # ignores .venv, __pycache__, dist/, build/, .pi-subagents/ (ALREADY correct — do NOT touch)
├── .venv/                      # Python 3.12.10, NO packages installed, bin/python -> uv-managed 3.12.10
├── PRD.md                      # product spec (READ-ONLY)
├── plan/001_be48c74bc590/      # architecture/, prd_snapshot.md, tasks.json
└── (NO pyproject.toml yet, NO voice_typing/ yet, NO uv.lock yet)
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── pyproject.toml              # ← CREATE (full authored version, overwrites the uv init --bare stub)
└── voice_typing/
    └── __init__.py             # ← CREATE (module docstring only)
# NOTHING ELSE. uv.lock is created by S2 (uv sync). Do not create it here.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — CONSOLE SCRIPTS REQUIRE A BUILDABLE PACKAGE (empirically verified).
# `uv init --bare` produces a pyproject.toml with NO [build-system]. uv then treats
# the project as a "virtual application": `uv sync` installs deps into the venv but
# does NOT build/install voice_typing itself, and [project.scripts] are IGNORED →
# .venv/bin/voicectl is NEVER created. That breaks PRD §4.8 ("installed console-
# script entry point") and the hypr-binds.conf call to .venv/bin/voicectl.
# FIX: add [build-system] hatchling + [tool.hatch.build.targets.wheel] packages
# =["voice_typing"]. Verified: with it, `uv sync` builds voice_typing and creates
# both script wrappers. (Experiment 2 in research/ transcript.)

# CRITICAL #2 — ENTRY POINTS MAY TARGET MODULES THAT DON'T EXIST YET.
# voice_typing/ctl.py (P1.M5) and voice_typing/daemon.py (P1.M4) do NOT exist at
# S1 time. hatchling/wheel entry points are NOT validated at build or install time;
# the wrapper only does `from voice_typing.ctl import main` at RUNTIME. Verified:
# `uv sync` with deps=[] built voice_typing (only __init__.py present) and created
# working .venv/bin/voicectl + .venv/bin/voice-typing-daemon wrappers. So declare
# the scripts NOW; they become functional once the modules land + a re-sync.

# CRITICAL #3 — REQUIRES-PYTHON MUST BE EDITED, not left as-is.
# `uv init --bare` sets requires-python = ">=3.12". The contract requires
# ">=3.12,<3.13" (PRD: python >=3.12,<3.13). Edit it. The existing .venv is 3.12.10,
# which satisfies both bounds.

# CRITICAL #4 — cuDNN PIN. Declare `nvidia-cudnn-cu12==9.*` EXACTLY (9.* prefix).
# Do NOT write `nvidia-cudnn-cu12` (unpinned) and do NOT pin to 10/11. faster-whisper
# README: ctranslate2 supports 'CUDA 12 and cuDNN 9' only.

# CRITICAL #5 — DO NOT ADD TORCH HERE. torch CUDA index (cu126) is S2's best-effort
# concern (research_faster_whisper_cuda.md §3/§4: torch CUDA is nice-to-have for
# Silero VAD; ctranslate2 CUDA is the must-have, arrives transitively via realtimestt).
# Adding torch here would muddy S1's deterministic gate.

# CRITICAL #6 — FULL PATHS in every bash call. This machine aliases python3→uv run,
# pip→alias, tmux→zsh plugin. Invoke /home/dustin/.local/bin/uv and .venv/bin/python
# explicitly. Never bare `python`, `pip`, `uv`, or `tmux`.

# GOTCHA #7 — `uv sync --no-deps` is NOT a valid flag in uv 0.7.11 (only --no-dev).
# Do not attempt it for a "skip-deps build". For an offline build soundness check use
# `uv build` instead (isolated build env installs ONLY hatchling, never realtimestt).

# GOTCHA #8 — NAME. `uv init --bare` derives name from the directory → "voice-typing".
# The authored pyproject.toml sets name="voice-typing" explicitly, so the stub's name
# is irrelevant after the overwrite. (PEP 503 distribution name allows dashes.)

# GOTCHA #9 — huggingface_hub underscore form. Write `huggingface_hub>=0.23` in deps
# (matches faster-whisper requirements.txt + the contract). Metadata normalizes it to
# `huggingface-hub` (PEP 503) — both are the same package. Either form resolves.

# GOTCHA #10 — version is REQUIRED. PEP 621 + hatchling require [project] version
# when a build-system is present. `uv init --bare` gives version="0.1.0"; keep it.
```

## Implementation Blueprint

### Data models and structure

None. This subtask creates no code, no types, no schemas. The only "structure" is the `pyproject.toml` TOML document.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: INITIALIZE the uv project (creates the stub pyproject.toml)
  - RUN: cd /home/dustin/projects/voice-typing && /home/dustin/.local/bin/uv init --bare --python 3.12
  - EXPECTED: prints "Initialized project `voice-typing`"; creates pyproject.toml ONLY
    (NO .python-version, NO uv.lock, NO .venv changes, NO sample app). The existing
    .venv (3.12.10) is reused/untouched.
  - VERIFY the stub: pyproject.toml should contain [project] name="voice-typing"
    version="0.1.0" requires-python=">=3.12" dependencies=[] and NO [build-system].
  - GOTCHA: if `uv init` refuses because the dir is non-empty, that is fine — the
    --bare path still writes pyproject.toml. Do NOT pass --no-readme / --package.
    Do NOT delete the existing .venv.

Task 2: AUTHOR the complete pyproject.toml (overwrite the stub)
  - USE the `write` tool to replace pyproject.toml with EXACTLY this content:
    ----- BEGIN pyproject.toml -----
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"

    [project]
    name = "voice-typing"
    version = "0.1.0"
    requires-python = ">=3.12,<3.13"
    dependencies = [
        "realtimestt",
        "nvidia-cublas-cu12",
        "nvidia-cudnn-cu12==9.*",
        "huggingface_hub>=0.23",
    ]

    [project.scripts]
    voicectl = "voice_typing.ctl:main"
    voice-typing-daemon = "voice_typing.daemon:main"

    [tool.hatch.build.targets.wheel]
    packages = ["voice_typing"]
    ----- END pyproject.toml -----
  - WHY each block:
      * [build-system]: REQUIRED for console scripts to be built/installed (Gotcha #1).
      * requires-python "<3.13": contract + PRD; 3.12.10 .venv satisfies it.
      * nvidia-cudnn-cu12==9.*: the corrected cuDNN-9 pin (Gotcha #4). Do not change.
      * [project.scripts]: the two installed entry points (PRD §4.8). Targets don't
        exist yet — that is fine (Gotcha #2); they're runtime-resolved.
      * [tool.hatch...packages]: tells hatchling the flat-layout package is voice_typing/
        (NOT src/voice_typing/). Matches PRD §4.1 flat layout.
  - DO NOT add: torch, dev/test deps, [tool.uv] index config, optional-dependencies,
    [tool.ruff]/[tool.pytest] config. Those belong to later subtasks.

Task 3: CREATE the package skeleton
  - USE the `write` tool to create voice_typing/__init__.py with EXACTLY:
    ----- BEGIN voice_typing/__init__.py -----
    """voice-typing: fully-local voice typing for Linux (tmux/Wayland) via RealtimeSTT."""
    ----- END voice_typing/__init__.py -----
  - That is the ENTIRE package at S1. Do NOT create ctl.py, daemon.py, config.py,
    typing_backends.py, feedback.py, textproc.py, status.sh, launch_daemon.sh, etc.

Task 4: VALIDATE (run the Validation Loop L1–L3 below). Fix until all pass.
  - No git commit is performed in this subtask unless the orchestrator directs it
    (the orchestrator manages commits between subtasks). If asked to commit, message:
    "P1.M1.T1.S1: scaffold pyproject.toml + voice_typing package + console scripts".
```

### Implementation Patterns & Key Details

```python
# There are no runtime code patterns here. The only "pattern" is the pyproject
# convention, given verbatim in Task 2. Two non-obvious facts to internalize:
#
# 1) A bare `uv init` project is NOT installable as a package. The presence of
#    [build-system] is what flips uv/pip from "virtual app" to "built package".
#    Without it, [project.scripts] are dead text. (Verified empirically.)
#
# 2) Wheel entry points are resolved lazily. `uv sync` will happily build+install
#    voice_typing and create .venv/bin/voicectl even while voice_typing/ctl.py is
#    absent; the wrapper errors only when actually executed. This is why S1 can
#    declare scripts whose target modules land in P1.M4/P1.M5.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMER (S2 — P1.M1.T1.S2 "Resolve & install deps"):
  - S2 runs `uv sync` against THIS pyproject.toml. It will: resolve realtimestt +
    transitive (torch, faster-whisper, ctranslate2, pyaudio, webrtcvad, onnxruntime,
    av, tokenizers), install nvidia-cublas-cu12 + nvidia-cudnn-cu12(9.x) + huggingface_hub,
    BUILD voice_typing, and create .venv/bin/voicectl + .venv/bin/voice-typing-daemon.
  - S2 then does best-effort torch CUDA (uv add torch --index https://download.pytorch.org/whl/cu126
    IF torch arrived CPU-only) and the must-have ctranslate2 CUDA check.
  - IMPLICATION FOR S1: keep deps EXACTLY as specified so S2's resolution is the one
    the research validated. Adding/dropping deps here shifts S2's outcome.

DOWNSTREAM CONSUMER (P1.M4 daemon.py, P1.M5 ctl.py):
  - These modules provide the `main` callables referenced by [project.scripts].
    Until they exist, the wrappers exist-but-error-on-run. Re-running `uv sync`
    after they land (S2/install.sh) refreshes the installed package.

DOWNSTREAM CONSUMER (install.sh / systemd in P1.M6):
  - systemd ExecStart uses `.venv/bin/python -m voice_typing.daemon` (PRD §4.9), NOT
    the voice-typing-daemon console script. Both entry styles are declared for
    flexibility. Neither is consumed until those later subtasks.

BUILD ARTIFACTS:
  - `uv build` (Validation L3) writes dist/*.whl + dist/*.tar.gz. dist/ is gitignored
    (already in .gitignore). Safe to leave or `rm -rf dist/` after validating.
```

## Validation Loop

> All commands use FULL PATHS (machine has zsh aliases). Run from repo root
> `/home/dustin/projects/voice-typing`. These gates are deliberately NETWORK-LIGHT:
> they prove the scaffold is sound WITHOUT downloading realtimestt/cuda (that is S2).

### Level 1: Structure (TOML parses + exact content) — no deps, no network

```bash
cd /home/dustin/projects/voice-typing
/home/dustin/projects/voice-typing/.venv/bin/python - <<'PY'
import tomllib
d = tomllib.load(open("pyproject.toml", "rb"))
p = d["project"]
assert p["name"] == "voice-typing", p["name"]
assert p["version"], "version missing"
assert p["requires-python"] == ">=3.12,<3.13", p["requires-python"]
assert p["dependencies"] == [
    "realtimestt", "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*", "huggingface_hub>=0.23",
], p["dependencies"]
assert p["scripts"]["voicectl"] == "voice_typing.ctl:main"
assert p["scripts"]["voice-typing-daemon"] == "voice_typing.daemon:main"
assert d["build-system"]["build-backend"] == "hatchling.build"
assert "hatchling" in d["build-system"]["requires"]
assert d["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["voice_typing"]
print("L1 PASS: pyproject.toml structure OK")
PY
# Expected: "L1 PASS: pyproject.toml structure OK". Any AssertionError → fix the file.
```

### Level 2: Package importable (no install needed; cwd is on sys.path for `-c`)

```bash
cd /home/dustin/projects/voice-typing
/home/dustin/projects/voice-typing/.venv/bin/python -c "import voice_typing; print('L2 PASS:', voice_typing.__file__)"
# Expected: "L2 PASS: /home/dustin/projects/voice-typing/voice_typing/__init__.py"
# (Proves the package dir + __init__.py are correctly placed for import.)
```

### Level 3: Build soundness (uv build → inspect wheel metadata) — installs ONLY hatchling

```bash
cd /home/dustin/projects/voice-typing
rm -rf dist/
/home/dustin/.local/bin/uv build                                   # isolated env installs hatchling only
WHL=$(ls dist/voice_typing-*.whl | head -1)
/home/dustin/projects/voice-typing/.venv/bin/python - "$WHL" <<'PY'
import sys, zipfile
w = zipfile.ZipFile(sys.argv[1])
ep = w.read("voice_typing-0.1.0.dist-info/entry_points.txt").decode()
md = w.read("voice_typing-0.1.0.dist-info/METADATA").decode()
assert "voicectl = voice_typing.ctl:main" in ep, ep
assert "voice-typing-daemon = voice_typing.daemon:main" in ep, ep
assert "Requires-Python: <3.13,>=3.12" in md, md
for need in ["Requires-Dist: realtimestt", "Requires-Dist: nvidia-cublas-cu12",
             "Requires-Dist: nvidia-cudnn-cu12==9.*",
             "Requires-Dist: huggingface-hub>=0.23"]:
    assert need in md, (need, md)
print("L3 PASS: wheel entry_points + metadata correct")
PY
rm -rf dist/        # cleanup (dist/ is gitignored anyway)
# Expected: "L3 PASS: ...". If `uv build` fails to find hatchling offline, retry with
# network (it only needs the tiny hatchling wheel, nothing heavy). This gate proves
# the build-system + scripts + deps are wired exactly as intended.
```

### Level 4: Out-of-scope guardrails (NEGATIVE checks — ensure we did NOT do S2's job)

```bash
cd /home/dustin/projects/voice-typing
test ! -f uv.lock && echo "L4 PASS: no uv.lock (deferred to S2)" || echo "L4 FAIL: uv.lock exists"
test -z "$(ls voice_typing)" && echo "(voice_typing has only __init__.py)" || ls voice_typing/
# Also confirm we did NOT create out-of-scope files:
for f in README.md config.toml install.sh voice_typing/ctl.py voice_typing/daemon.py \
         voice_typing/config.py systemd/voice-typing.service hypr-binds.conf; do
  test ! -e "$f" && echo "absent (ok): $f" || echo "L4 FAIL: $f should not exist yet"
done
# git status should show ONLY: pyproject.toml (new/modified) + voice_typing/__init__.py (new).
git status --short
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 tomllib structural assertions pass (exact deps, requires-python, scripts, build-system, hatch packages).
- [ ] L2 `import voice_typing` succeeds from repo root with no install.
- [ ] L3 `uv build` wheel contains both console_scripts + correct Requires-Python + all 4 Requires-Dist.
- [ ] L4 negative checks: no `uv.lock`, no out-of-scope files created.

### Feature Validation
- [ ] `uv init --bare --python 3.12` ran without error and left the repo otherwise intact (.venv preserved).
- [ ] `pyproject.toml` pins `nvidia-cudnn-cu12==9.*` (the corrected cuDNN-9 pin — not unpinned, not 10/11).
- [ ] `requires-python` is `>=3.12,<3.13` (not the `>=3.12` stub).
- [ ] torch is NOT declared (deferred to S2).
- [ ] Both console scripts declared with the exact `module:function` targets from the contract.

### Code Quality Validation
- [ ] `voice_typing/__init__.py` is a one-line module docstring (no logic, no imports).
- [ ] `.gitignore` was NOT modified (already correct: ignores .venv, __pycache__, dist/, build/).
- [ ] PRD.md, tasks.json, prd_snapshot.md were NOT modified (read-only).
- [ ] No bare `python`/`pip`/`uv`/`tmux` used in any command (all full-pathed).

### Scope Boundary Validation
- [ ] No `uv sync` / `uv lock` / `uv add` executed (resolve+install is S2).
- [ ] No realtimestt/cuda/torch downloaded (would be a multi-GB, flaky, S2-level operation).
- [ ] Only `pyproject.toml` and `voice_typing/__init__.py` were added to the repo.

---

## Anti-Patterns to Avoid

- ❌ Don't run `uv sync` / `uv lock` / `uv add` — that resolves+installs and is S2's job; it pulls GB of CUDA wheels and is non-deterministic for THIS gate.
- ❌ Don't omit `[build-system]` — `[project.scripts]` are silently ignored without it; `.venv/bin/voicectl` will never be created.
- ❌ Don't use `src/voice_typing/` layout — PRD §4.1 is a flat `voice_typing/` package; the `[tool.hatch.build.targets.wheel] packages=["voice_typing"]` line pins that.
- ❌ Don't pin/omit torch here — S2 owns the best-effort CUDA torch index.
- ❌ Don't leave cuDNN unpinned or pin it to 10/11 — must be `==9.*` (faster-whisper/ctranslate2 requirement).
- ❌ Don't create ctl.py/daemon.py/config.py/etc. to "satisfy" the script targets — entry points resolve lazily; the modules land in P1.M4/P1.M5.
- ❌ Don't edit `.gitignore`, PRD.md, tasks.json, or prd_snapshot.md.
- ❌ Don't use bare `python`/`pip`/`uv`/`tmux` (zsh aliases shadow them on this machine).

---

## Confidence Score

**9/10** for one-pass implementation success. The task surface is tiny (two files), all commands are given verbatim with full paths, and every non-obvious behavior (build-system requirement, lazy entry-point resolution, requires-python edit, cuDNN pin, `uv sync --no-deps` invalidity) has been empirically verified in throwaway experiments and documented in `research/uv_build_system_verification.md`. The one residual uncertainty (−1) is whether S2's full `uv sync` resolves the exact unpinned `realtimestt` + `nvidia-cublas-cu12` versions cleanly on THIS network/GPU — but that risk belongs to S2, not S1, and S1's `uv build` gate already proves the project is structurally valid independent of resolution.
