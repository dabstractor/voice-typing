# PRP — P1.M1.T1.S2: Resolve & install dependencies; verify torch CUDA (best-effort)

> **RE-PLAN (attempt 2/3).** Attempt 1 halted correctly: bare `realtimestt==1.0.2` does **not** pull `faster-whisper`/`ctranslate2` — they are gated behind an optional **extra**. This PRP authorizes and prescribes the **root-cause fix**: correct the `realtimestt` dependency in `pyproject.toml` so `uv sync` reproduces the full CUDA-inference closure. See **§ Re-Plan: Root-Cause Fix** below — it is the single load-bearing change.

---

## Re-Plan: Root-Cause Fix (READ FIRST)

**Why attempt 1 failed.** The original contract assumed `uv add realtimestt` pulls `faster-whisper + ctranslate2 + onnxruntime + av + tokenizers` *transitively*. That is **false for `realtimestt==1.0.2`**. Verified empirically from the installed wheel's `METADATA`:

```
Name: realtimestt
Version: 1.0.2
Requires-Dist: PyAudio==0.2.14              # unconditional ↓
Requires-Dist: webrtcvad-wheels==2.0.14
Requires-Dist: halo==0.0.31
Requires-Dist: torch
Requires-Dist: torchaudio
Requires-Dist: scipy==1.17.1
Requires-Dist: websockets==16.0
Requires-Dist: websocket-client==1.9.0
Requires-Dist: soundfile==0.13.1
Provides-Extra: faster-whisper
Requires-Dist: faster-whisper==1.2.1; extra == "faster-whisper"     # ← GATED
Provides-Extra: silero-vad
Requires-Dist: silero-vad>=6.2.1; ... ; extra == "silero-vad"        # ← GATED
... (whisper-cpp, openai-whisper, sherpa-onnx, silero-onnx[-cpu/-gpu], transformers, ...)
```

So bare `realtimestt` resolves to ~9 unconditional packages and **no CUDA inference backend at all**. `faster-whisper==1.2.1` (→ `ctranslate2>=4.0,<5` + `onnxruntime` + `av` + `tokenizers`, the entire load-bearing CUDA stack) lives behind `extra == "faster-whisper"`.

**Why attempt 1's recommended fix is also wrong.** Attempt 1 suggested `realtimestt[default]` / `realtimestt[recommended]`. **Neither extra exists in 1.0.2** (see `Provides-Extra` list above). uv would error on `default`. The valid, version-correct extras are `faster-whisper` and `silero-vad` (plus the onnx/sherpa/transformers variants).

**The fix (this PRP's central task).** Edit `pyproject.toml`: change the `realtimestt` dependency line to request the extras. This is the only edit to `pyproject.toml` that is **unconditional** (no longer gated on the torch-cu126 branch). It is required to satisfy the contract's own OUTPUT clause ("A populated .venv with realtimestt + faster-whisper + ctranslate2 + nvidia-cublas-cu12 + nvidia-cudnn-cu12(9.x) [+ torch]").

**Scope deviation — justified.** The original contract forbade touching `pyproject.toml` except on the cu126 branch. That rule is **suspended for this one edit** because S1's pyproject is the defective input. S1 is already Complete and will not be re-run; S2 is the resolve/install task where this correction naturally belongs. Everything else in S2's original contract (UV_HTTP_TIMEOUT, CUDA gates, lockfile, no models/config/install.sh, commit) is unchanged.

**Current repo state (verified July 7 2026 — do NOT trust it as "done"):**
- `.venv` currently imports `faster_whisper` 1.2.1 / `ctranslate2` 4.8.1 / `onnxruntime` 1.27.0 / `av` / `tokenizers` and `ctranslate2.get_cuda_device_count()==1`, `torch.cuda.is_available()==True`. **But this was installed out-of-band** (e.g. `uv pip install`).
- `uv.lock` has **only 66 packages and does NOT track** `faster-whisper`, `ctranslate2`, `onnxruntime`, `silero-vad`, `tokenizers`, or `av`. A fresh `uv sync` / CI / clean checkout **cannot reproduce** the working stack until `pyproject.toml` is corrected and the lock regenerated.
- `pyproject.toml` still has bare `"realtimestt"`.
- **`silero-vad` is NOT installed** and RealtimeSTT 1.0.2 ships `core/silero_vad.py` but **no bundled `.onnx` model** — the daemon's `silero_backend="auto"` needs the `silero-vad` package (or a runtime download). Adding the `silero-vad` extra closes that gap (see Tasks).

---

## Goal

**Feature Goal**: Produce a **reproducible** populated `.venv` whose resolution is fully captured by `pyproject.toml` + `uv.lock`, containing the complete RealtimeSTT CUDA-inference closure (`realtimestt` + `faster-whisper` + `ctranslate2` + `nvidia-cublas-cu12` + `nvidia-cudnn-cu12==9.*` + `onnxruntime` + `av` + `tokenizers` + `silero-vad` + `torch`), with **`ctranslate2` CUDA verified ≥1** and `torch.cuda` best-effort True.

**Deliverable**: (1) corrected `pyproject.toml` (`realtimestt[faster-whisper,silero-vad]`), (2) regenerated `uv.lock` that **tracks** faster-whisper/ctranslate2/onnxruntime/tokenizers/av/silero-vad, (3) a synced `.venv`, (4) all committed to git on `main`. Consumed verbatim by P1.M1.T2.* and P1.M1.T3.S1.

**Success Definition**:
- `uv lock --check` passes (lockfile matches the corrected `pyproject.toml`).
- `.venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` prints **≥1** (record the number).
- `.venv/bin/python -c "import torch; print(torch.cuda.is_available())"` prints `True` (if `False`, take the cu126 branch in Task 5; do NOT block on it).
- All 11 closure packages import (Task 3 gate).
- `git status` clean; `pyproject.toml`, `uv.lock` committed.

## User Persona

N/A — developer/agent-facing install/resolution subtask. No end-user surface. (Docs surface is P1.M6 `install.sh`; this task is installation-level only.)

## Why

- **Every downstream module depends on this closure.** `daemon.py` (P1.M4) imports `RealtimeSTT`, which imports `faster_whisper`/`ctranslate2` for inference and `silero_vad` for VAD. If these aren't resolved by the lockfile, P1.M1.T3 (prefetch), P1.M1.T2 (CUDA smoke), and P1.M7 (tests) silently rely on an out-of-band `.venv` that breaks on any clean checkout.
- **Reproducibility is the deliverable, not a side effect.** Attempt 1 left a `.venv` that "works" but a `uv.lock` that can't rebuild it. CI / a fresh clone / `rm -rf .venv && uv sync` would all fail. The lockfile must be the source of truth.
- **Locks the CUDA-correctness decision.** `nvidia-cudnn-cu12==9.*` (pinned by S1) + the `faster-whisper` extra (→ `ctranslate2>=4.0,<5`) together guarantee the cuDNN-9/ctranslate2-4 pairing the research requires. Bare `realtimestt` gave none of this.
- **Scope discipline preserved.** Still NO models downloaded here (P1.M1.T3), NO `install.sh` (P1.M6), NO `config.toml`/source modules beyond what S1 created, NO systemd. Only pyproject + lock + venv + commit.

## What

Correct the single defective dependency, regenerate the lock, sync, and verify the CUDA gates. No runtime behavior change, no new source files, no models, no docs.

### Success Criteria

- [ ] `pyproject.toml` `[project].dependencies` lists `realtimestt[faster-whisper,silero-vad]` (exact string; the `nvidia-cublas-cu12`, `nvidia-cudnn-cu12==9.*`, `huggingface_hub>=0.23` lines unchanged).
- [ ] `uv.lock` regenerated; `grep '^name = "faster-whisper"' uv.lock` AND `ctranslate2` AND `onnxruntime` AND `tokenizers` AND `av` AND `silero-vad` all return a `[[package]]` match (currently they return nothing).
- [ ] `uv lock --check` exits 0.
- [ ] `.venv` synced; all 11 closure packages import (Task 3 one-liner).
- [ ] **MUST-HAVE gate:** `ctranslate2.get_cuda_device_count()` ≥ 1.
- [ ] **Best-effort gate:** `torch.cuda.is_available()` is True (if False → Task 5 cu126 branch; not blocking).
- [ ] `.venv/bin/voicectl` and `.venv/bin/voice-typing-daemon` wrapper scripts EXIST (do not need to run — target modules land in P1.M4/M5).
- [ ] `portaudio` NOT reinstalled (already `1:19.7.0-4`).
- [ ] NO models, NO `install.sh`, NO `config.toml`, NO new `voice_typing/*.py` created.
- [ ] `pyproject.toml` + `uv.lock` committed to `main`; working tree clean.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement this from the verified `uv`/`realtimestt` facts below. Every command uses full paths (machine has zsh aliases shadowing `python3`/`pip`/`tmux`). The one non-obvious fact — that `faster-whisper`/`ctranslate2` are extras, not transitive deps — is proven above from the wheel METADATA.

### Documentation & References

```yaml
# MUST READ — the extras truth (do NOT trust stale prose that says "transitive")
- file: .venv/lib/python3.12/site-packages/realtimestt-1.0.2.dist-info/METADATA
  why: Authoritative proof that faster-whisper/silero-vad are gated behind `extra ==`.
  pattern: "Requires-Dist: faster-whisper==1.2.1; extra == \"faster-whisper\""
  critical: "There is NO `default`/`recommended` extra in 1.0.2. Attempt 1's suggested fix would error. Use exactly `faster-whisper` and `silero-vad`."

- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md
  why: "§3 = CUDA smoke-check table (ctranslate2.get_cuda_device_count MUST ≥1; torch CUDA nice-to-have; VAD runs on CPU). §2 = cuDNN-9 pin rationale + LD_LIBRARY_PATH (T2's job, not S2). §4 = cu126 index recommendation. §6 = faster-whisper pins ctranslate2>=4.0,<5."
  critical: "§3's 'ctranslate2 CUDA is the must-have' is the hard gate. §6 contains the now-REFUTED line 'RealtimeSTT pulls faster-whisper transitively, so these are handled by uv add realtimestt' — DISREGARD that sentence; trust the wheel METADATA instead. The cuDNN-9 pin and ctranslate2 pin are still correct."

- file: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§6 (Version) confirms v1.0.2 target. Multiprocessing `__main__` guard note is P1.M4's concern, not S2."
  critical: "If this doc repeats the 'pulls faster-whisper transitively' claim, it is stale prose — the METADATA wins."

- file: plan/001_be48c74bc590/P1M1T1S2/research/uv_dependency_resolution_findings.md
  why: "Empirically verified uv 0.7.11 behaviors: Finding 2 (MUST set UV_HTTP_TIMEOUT=600 for multi-hundred-MB CUDA wheels), Finding 1 (uv add --index writes an ANONYMOUS non-exclusive [[tool.uv.index]] — escape hatch = named+explicit+sources), Finding 7 (uv lock --check is the lockfile gate), Finding 4 (uv sync builds voice_typing + console wrappers; wrappers exist but error at runtime until P1.M4/M5)."
  critical: "WITHOUT UV_HTTP_TIMEOUT=600 the large nvidia wheels time out at the 30s default mid-download — this is a download timeout, NOT a resolution error. Finding 1's escape hatch is needed IF the plain cu126 --index shifts an nvidia-cu12 version."

- file: plan/001_be48c74bc590/P1M1T1S1/PRP.md
  why: "What S1 produced: the 4-dep pyproject (the defective `realtimestt` line), hatchling build-system, 2 console scripts, the cuDNN-9 pin. S2 inherits this verbatim and edits one line."
  critical: "Do NOT alter the build-system, scripts, hatch wheel target, requires-python, or the nvidia-cudnn-cu12==9.* pin. Edit ONLY the `realtimestt` dependency token."

- file: PRD.md
  why: "§2 verified machine facts (uv at /home/dustin/.local/bin/uv, zsh aliases → full paths, RTX 3080 Ti driver 610.43.02, portaudio already installed). §5 install steps. §4.4 recorder config (silero_use_onnx — but daemon uses silero_backend='auto', see daemon.py)."
  critical: "PRD §5 step 4 'uv add realtimestt nvidia-cublas-cu12 nvidia-cudnn-cu12 — pulls torch, faster-whisper, pyaudio, webrtcvad, etc.' is the stale claim that caused attempt 1's halt. The METADATA refutes it; S2 corrects it via the extra."
```

### Current Codebase tree (verified)

```bash
/home/dustin/projects/voice-typing/
├── .git/                         # branch main; HEAD = bde0a56 (P1.M7.T1.S1)
├── .gitignore                    # ignores .venv, __pycache__, etc. (correct — do NOT touch)
├── .venv/                        # Python 3.12.10; HAS faster-whisper/ctranslate2 OUT-OF-BAND (not in lock)
├── PRD.md                        # READ-ONLY
├── config.toml                   # P1.M2 output — leave as-is (not your concern)
├── install.sh                    # P1.M6 output — leave as-is
├── plan/001_be48c74bc590/...     # architecture/, docs/, P1M1T1S2/{PRP.md,research/}
├── pyproject.toml                # S1 output — THE FILE YOU EDIT (one token: realtimestt → realtimestt[faster-whisper,silero-vad])
├── systemd/                      # P1.M6 output — leave as-is
├── tests/                        # P1.M2/M3/M4/M7 tests — leave as-is
├── uv.lock                       # 66 pkgs; DOES NOT track faster-whisper/ctranslate2 — YOU REGENERATE
└── voice_typing/                 # P1.M2–M5 source — leave as-is (do NOT add files)
```

### Desired Codebase tree (delta only)

```bash
pyproject.toml    # MODIFIED: one dependency token changed (realtimestt → realtimestt[faster-whisper,silero-vad])
uv.lock           # REGENERATED: now tracks ~70+ pkgs incl. faster-whisper, ctranslate2, onnxruntime, av, tokenizers, silero-vad
.venv/            # SYNCED (gitignored) — reproducible from pyproject+uv.lock alone
# (no new files. no deletions.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: realtimestt==1.0.2 gates faster-whisper behind an EXTRA.
#   Bare `realtimestt` → 9 packages, NO inference backend, NO ctranslate2 → CUDA gate can never pass.
#   Fix = `realtimestt[faster-whisper,silero-vad]`. Do NOT use `[default]`/`[recommended]` (don't exist).

# CRITICAL: uv's DEFAULT 30s HTTP timeout aborts multi-hundred-MB nvidia wheels mid-download.
#   The error reads "Failed to download ... due to network timeout" — that is NOT a resolution error.
#   Fix = prefix every sync/add with `UV_HTTP_TIMEOUT=600`.

# GOTCHA: This machine's zsh aliases `python3`→`uv run` and `pip`→(wrapped). In ALL bash calls use
#   /home/dustin/.local/bin/uv   and   .venv/bin/python   (never bare `python`/`pip`/`uv`).

# GOTCHA: `uv sync` will BUILD voice_typing and create .venv/bin/{voicectl,voice-typing-daemon}.
#   Those wrappers ERROR at runtime ("ModuleNotFoundError: voice_typing.ctl") until P1.M4/M5 —
#   that is EXPECTED. Verify they EXIST, do not run them.

# GOTCHA: silero-vad is NOT bundled as a .onnx asset in RealtimeSTT 1.0.2 (only core/silero_vad.py).
#   The daemon uses silero_backend="auto" → needs the silero-vad package (the extra) to avoid a
#   runtime model fetch. Hence silero-vad is in the extras, not just faster-whisper.

# GOTCHA: torch PyPI default is cu130 (CUDA 13). It bundles its OWN cuda runtime, so torch.cuda
#   works fine even though ctranslate2 links cu12 libs — they coexist via soname versioning
#   (libcublas.so.12 vs .so.13). cu126 torch is only needed IF torch.cuda.is_available()==False.

# CRITICAL: portaudio is ALREADY installed system-wide (1:19.7.0-4). Do NOT run pacman for it.
```

## Implementation Blueprint

### Data models and structure

N/A — no data models. This task edits one dependency token and regenerates a lockfile.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT (verify the defective input + environment — no writes)
  - RUN: /home/dustin/.local/bin/uv --version   # expect 0.7.x
  - RUN: grep '^    "realtimestt' pyproject.toml # CONFIRM it is the bare token (the defect). If it already
          # reads realtimestt[faster-whisper,...] someone fixed it; still proceed to Task 2.
  - RUN: pacman -Q portaudio                      # expect 1:19.7.0-4; do NOT install if present
  - RUN: .venv/bin/python -c "import sys; print(sys.version)"   # expect 3.12.x
  - RUN (record baseline): .venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())" 2>&1 | tail -1
  - NOTE the current uv.lock package count: grep -c '^\[\[package\]\]' uv.lock  # currently 66 (defective)

Task 1: CORRECT pyproject.toml — the root-cause fix (ONE edit)
  - FILE: pyproject.toml
  - CHANGE the single dependency token:
      FROM:  "realtimestt",
      TO:    "realtimestt[faster-whisper,silero-vad]",
  - PRESERVE exactly (do NOT touch): [build-system] (hatchling), name, version, requires-python
      (>=3.12,<3.13), the nvidia-cublas-cu12 line, the nvidia-cudnn-cu12==9.* line, the
      huggingface_hub>=0.23 line, BOTH [project.scripts], [tool.hatch.build.targets.wheel],
      [dependency-groups] dev=[pytest>=9.1.1].
  - WHY both extras: faster-whisper→ctranslate2+onnxruntime+av+tokenizers (MUST-HAVE CUDA inference);
      silero-vad→silero-vad>=6.2.1 (the daemon's silero_backend="auto"; RealtimeSTT ships no bundled ONNX).
  - VERIFY: .venv/bin/python -c "import tomllib;d=tomllib.load(open('pyproject.toml','rb'));print([x for x in d['project']['dependencies'] if 'realtimestt' in x])"
      → must print ['realtimestt[faster-whisper,silero-vad]']

Task 2: REGENERATE uv.lock + SYNC (the multi-GB download)
  - RUN (single command, timeout-budget ~10-20 min on first run):
      UV_HTTP_TIMEOUT=600 /home/dustin/.local/bin/uv lock      # re-resolve against corrected pyproject
      UV_HTTP_TIMEOUT=600 /home/dustin/.local/bin/uv sync       # build voice_typing + install closure into .venv
  - GOTCHA: if `uv sync` dies with "Failed to download ... due to network timeout", it is a TRANSFER
      timeout, not a resolver error — re-run with UV_HTTP_TIMEOUT=900. Resolution itself is correct.
  - EXPECT: uv.lock package count rises from 66 to ~70+ (adds faster-whisper, ctranslate2, onnxruntime,
      av, tokenizers, silero-vad, and their transitive deps like pyaho-corasick, etc.).
  - EXPECT: .venv now resolves everything from the lock (the prior out-of-band installs are reconciled).

Task 3: VERIFY the install closure (all 11 contract + companion packages import)
  - RUN (one-liner, expect "ALL IMPORT OK"):
      .venv/bin/python - <<'PY'
      import importlib, sys
      pkgs = ["realtimestt","faster_whisper","ctranslate2","onnxruntime","av","tokenizers",
              "silero_vad","nvidia.cublas","nvidia.cudnn","torch","torchaudio"]
      miss = []
      for p in pkgs:
          try: importlib.import_module(p)
          except Exception as e: miss.append((p, repr(e)))
      print("ALL IMPORT OK" if not miss else f"MISSING: {miss}")
      import faster_whisper, ctranslate2
      print("faster_whisper", faster_whisper.__version__, "| ctranslate2", ctranslate2.__version__)
      PY
  - EXPECT: "ALL IMPORT OK"; faster_whisper 1.2.1; ctranslate2 4.x (>=4.0,<5).
  - VERIFY lock now tracks them: for p in faster-whisper ctranslate2 onnxruntime tokenizers av silero-vad;
        do grep -q "^name = \"$p\"" uv.lock && echo "$p: in lock" || echo "$p: MISSING FROM LOCK"; done

Task 4: CUDA GATES — the contract's must-have + best-effort
  - MUST-HAVE (record the number; if 0 see P1.M1.T2.S2 degraded path — do NOT silently proceed):
      .venv/bin/python -c "import ctranslate2; print('CTRANSLATE2_CUDA_DEVICES', ctranslate2.get_cuda_device_count())"
      → expect CTRANSLATE2_CUDA_DEVICES 1   (RTX 3080 Ti)
  - BEST-EFFORT:
      .venv/bin/python -c "import torch; print('TORCH_CUDA', torch.cuda.is_available())"
      → expect TORCH_CUDA True
  - IF torch.cuda is True: SKIP Task 5. Commit in Task 6.
  - IF torch.cuda is False AND a CUDA torch is desired: run Task 5 (best-effort; do NOT block).

Task 5: CONDITIONAL — cu126 torch fallback (ONLY if Task 4 torch.cuda == False)
  - RUN: /home/dustin/.local/bin/uv add torch --index https://download.pytorch.org/whl/cu126
      (this adds `torch` to [project].dependencies AND an anonymous [[tool.uv.index]]; expected)
  - RE-SYNC: UV_HTTP_TIMEOUT=600 /home/dustin/.local/bin/uv sync
  - RE-CHECK: .venv/bin/python -c "import torch; print(torch.cuda.is_available())"   # expect True now
  - ESCAPE HATCH (only if the anonymous cu126 index mis-resolves an nvidia-cu12 wheel, e.g. shifts
      nvidia-cudnn-cu12 away from 9.x): replace the anonymous [[tool.uv.index]] block with:
        [[tool.uv.index]]
        name = "pytorch-cu126"
        url = "https://download.pytorch.org/whl/cu126"
        explicit = true
        [tool.uv.sources]
        torch = { index = "pytorch-cu126" }
      then re-run `UV_HTTP_TIMEOUT=600 /home/dustin/.local/bin/uv lock && uv sync`.
  - DO NOT block the project on this: VAD runs on CPU and ctranslate2 CUDA (Task 4) is the real gate.
      If cu126 torch still fails, leave torch as PyPI default, record torch.cuda=False in the commit msg.

Task 6: LOCKFILE + WRAPPER GATES
  - RUN: /home/dustin/.local/bin/uv lock --check            # MUST exit 0 (lock matches pyproject)
  - RUN: test -x .venv/bin/voicectl && test -x .venv/bin/voice-typing-daemon && echo "wrappers exist"
      (do NOT execute them — they error until P1.M4/M5; existence is the gate)
  - RUN: grep -n 'uv.lock' .gitignore || echo "uv.lock NOT gitignored (correct)"   # must NOT be ignored

Task 7: COMMIT
  - RUN: git add pyproject.toml uv.lock
  - RUN: git commit -m "P1.M1.T1.S2: pin realtimestt[faster-whisper,silero-vad]; regenerate uv.lock with CUDA inference closure; ctranslate2 CUDA=N, torch.cuda=True"
      (replace N with the recorded device count; if torch.cuda False, say so and note cu126 outcome)
  - DO NOT commit: .venv (gitignored), any other file. git status must be clean afterward.
```

### Implementation Patterns & Key Details

```python
# The pyproject.toml edit — minimal, surgical. Before:
#   dependencies = [
#       "realtimestt",
#       "nvidia-cublas-cu12",
#       "nvidia-cudnn-cu12==9.*",
#       "huggingface_hub>=0.23",
#   ]
# After (only the first line changes):
#   dependencies = [
#       "realtimestt[faster-whisper,silero-vad]",
#       "nvidia-cublas-cu12",
#       "nvidia-cudnn-cu12==9.*",
#       "huggingface_hub>=0.23",
#   ]

# Closure reasoning (why this one token fixes everything):
#   realtimestt[faster-whisper]  → faster-whisper==1.2.1   (RealtimeSTT's own pin)
#       faster-whisper           → ctranslate2>=4.0,<5, onnxruntime, av, tokenizers, huggingface_hub>=0.23
#   realtimestt[silero-vad]      → silero-vad>=6.2.1        (daemon's silero_backend="auto")
#   nvidia-cublas-cu12 + nvidia-cudnn-cu12==9.*            (explicit; cuDNN-9 required by ctranslate2 4.x)
#   torch (unconditional dep of realtimestt)               (PyPI default cu130; bundles own CUDA runtime)
```

### Integration Points

```yaml
PYPROJECT:
  - edit: "[project].dependencies" — replace the `"realtimestt"` token with `"realtimestt[faster-whisper,silero-vad]"`.
  - preserve: build-system, requires-python, both scripts, hatch wheel target, cuDNN-9 pin, dev group.
  - conditional (Task 5 only, if torch.cuda False): add `torch` dep + `[[tool.uv.index]]` cu126 (or named+explicit escape hatch).

LOCKFILE:
  - regenerate: uv.lock must now contain [[package]] entries for faster-whisper, ctranslate2, onnxruntime, av, tokenizers, silero-vad (currently absent).
  - gate: `uv lock --check` exit 0.

CONSUMERS (downstream, do NOT touch — listed for awareness):
  - P1.M1.T2.S1 launch_daemon.sh: reads nvidia.cublas.lib / nvidia.cudnn.lib from THIS .venv to set LD_LIBRARY_PATH.
  - P1.M1.T2.S2 CUDA smoke: calls ctranslate2.get_cuda_device_count() (the Task 4 must-have gate).
  - P1.M1.T3.S1 prefetch: uses huggingface_hub + faster_whisper to snapshot_download Systran models.
  - P1.M4.T1.S1 daemon: imports RealtimeSTT, faster_whisper, uses silero_backend="auto".
```

## Validation Loop

### Level 1: Syntax & Style (after Task 1)

```bash
# pyproject must still parse + retain structure
.venv/bin/python -c "import tomllib; d=tomllib.load(open('pyproject.toml','rb')); assert 'realtimestt[faster-whisper,silero-vad]' in d['project']['dependencies']; assert d['project']['requires-python']=='>=3.12,<3.13'; assert len(d['project']['scripts'])==2; print('pyproject structurally valid')"
# ruff/mypy do not apply to .toml; no python source changed.
```

### Level 2: Resolution & Install (after Task 2)

```bash
UV_HTTP_TIMEOUT=600 /home/dustin/.local/bin/uv lock --check     # exit 0 = lock matches pyproject
/home/dustin/.local/bin/uv sync --frozen                         # exit 0 = .venv matches lock, nothing missing
for p in faster-whisper ctranslate2 onnxruntime tokenizers av silero-vad; do
  grep -q "^name = \"$p\"" uv.lock && echo "$p tracked" || echo "$p NOT TRACKED"
done   # all six must print "tracked"
```

### Level 3: CUDA Smoke (the contract gates — after Task 4)

```bash
# MUST-HAVE
.venv/bin/python -c "import ctranslate2; n=ctranslate2.get_cuda_device_count(); print('devices',n); assert n>=1, 'CTRANSLATE2 CUDA GATE FAILED'"
# BEST-EFFORT
.venv/bin/python -c "import torch; print('torch.cuda', torch.cuda.is_available())"
# closure import sweep (Task 3 one-liner) must print ALL IMPORT OK
```

### Level 4: Reproducibility (the real deliverable — after Task 6)

```bash
# Prove a clean re-sync reproduces the closure from pyproject+uv.lock ALONE (no out-of-band installs):
UV_HTTP_TIMEOUT=600 /home/dustin/.local/bin/uv sync --reinstall-package faster-whisper 2>/dev/null
.venv/bin/python -c "import faster_whisper, ctranslate2; print('reproducible import OK', ctranslate2.__version__)"
# wrappers exist (do not run):
test -x .venv/bin/voicectl && test -x .venv/bin/voice-typing-daemon && echo "wrappers present"
# git clean:
git status --short    # only pyproject.toml + uv.lock staged/committed; nothing else
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1: pyproject parses, retains requires-python + 2 scripts + cuDNN-9 pin.
- [ ] Level 2: `uv lock --check` exit 0; `uv sync --frozen` exit 0; faster-whisper/ctranslate2/onnxruntime/tokenizers/av/silero-vad all tracked in uv.lock.
- [ ] Level 3: `ctranslate2.get_cuda_device_count()` ≥ 1 (recorded); `torch.cuda.is_available()` checked.
- [ ] Level 4: clean re-sync imports the closure; console wrappers exist; `git status` clean.
- [ ] Closure import sweep prints `ALL IMPORT OK`.

### Feature / Contract Validation
- [ ] pyproject.toml `[project].dependencies` contains exactly `realtimestt[faster-whisper,silero-vad]`.
- [ ] uv.lock regenerated (package count > 66; the 6 previously-absent packages now tracked).
- [ ] portaudio NOT reinstalled; no pacman invocations.
- [ ] NO models downloaded; NO install.sh/config.toml/source-module edits; NO systemd changes.
- [ ] Commit message records the ctranslate2 device count and torch.cuda result.

### Re-Plan-Specific Validation (guards against repeating attempt 1)
- [ ] Did NOT use `realtimestt[default]` or `realtimestt[recommended]` (they don't exist in 1.0.2).
- [ ] Did NOT assume bare `realtimestt` pulls faster-whisper transitively (it doesn't).
- [ ] uv.lock genuinely tracks the inference backend (grep proof in Level 2), not just the 9 unconditional realtimestt deps.
- [ ] If torch.cuda was False, the cu126 branch (Task 5) was attempted best-effort; project not blocked on it.

---

## Anti-Patterns to Avoid

- ❌ Don't "just fix the venv" with `uv pip install faster-whisper` and call it done — that reproduces attempt 1's non-reproducible state. The lockfile MUST track the closure.
- ❌ Don't use `realtimestt[default]` / `[recommended]` — those extras do not exist in 1.0.2 (uv errors). Use `faster-whisper` and `silero-vad`.
- ❌ Don't run `uv sync` / `uv add` without `UV_HTTP_TIMEOUT=600` — multi-hundred-MB nvidia wheels time out at the 30s default (looks like a resolver error but isn't).
- ❌ Don't reinstall portaudio (already `1:19.7.0-4`).
- ❌ Don't execute `.venv/bin/voicectl` / `voice-typing-daemon` as a gate — they error at runtime until P1.M4/M5; verify existence only.
- ❌ Don't touch the cuDNN-9 pin (`nvidia-cudnn-cu12==9.*`), build-system, scripts, requires-python, or any source file. Edit exactly one dependency token.
- ❌ Don't block the project on torch CUDA — ctranslate2 CUDA is the must-have; VAD and (if needed) torch run on CPU.
- ❌ Don't commit `.venv` (gitignored) or any file other than `pyproject.toml` + `uv.lock`.
