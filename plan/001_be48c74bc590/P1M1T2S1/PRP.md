# PRP — P1.M1.T2.S1: Create launch_daemon.sh (LD_LIBRARY_PATH for cuBLAS+cuDNN)

## Goal

**Feature Goal**: Produce a single, executable, idempotent bash launcher wrapper — `voice_typing/launch_daemon.sh` — that dynamically computes the cuBLAS + cuDNN 9 shared-library directories from the **live installed** `nvidia-*-cu12` wheels, exports them on `LD_LIBRARY_PATH`, and `exec`s `python -m voice_typing.daemon` so the dynamic linker sees the CUDA libs **before** Python starts. This is the sanctioned fix for faster-whisper/ctranslate2's `cannot load libcudnn_ops` runtime failure (PRD §8 risk row #1).

**Deliverable** (exactly one file):
1. `voice_typing/launch_daemon.sh` — `chmod +x`, `#!/usr/bin/env bash`, header comment block (the DOCS requirement), the guarded `LD_LIBRARY_PATH` computation, and a final `exec "$PY" -m voice_typing.daemon "$@"`.

**Success Definition**:
- (a) File exists at `voice_typing/launch_daemon.sh`, is executable (`test -x`), passes `bash -n` (syntax) and `shellcheck` (if installed).
- (b) The `nvidia.cublas.lib` / `nvidia.cudnn.lib` path computation, run against S2's populated `.venv`, prints exactly `<…>/nvidia/cublas/lib:<…>/nvidia/cudnn/lib`.
- (c) Setting `LD_LIBRARY_PATH` to that value makes **`ctranslate2.get_cuda_device_count() >= 1`** — proving the wrapper's path is *sufficient* for CUDA (the load-bearing integration gate; this is S2's gate re-run through the wrapper's exact path).
- (d) The CPU-fallback branch works: when the nvidia import fails, the script prints a clear stderr warning and **still `exec`s python** without the override (does not `exit`).
- (e) `daemon.py` does NOT set `LD_LIBRARY_PATH` or use `os.execv` — the wrapper is the single sanctioned place (constraint from the contract + research_faster_whisper_cuda.md §2).
- (f) No out-of-scope artifacts (no daemon.py, no cuda_smoke script, no install.sh, no systemd unit, no model prefetch).

## User Persona

Not applicable (developer/system-facing launcher; no end-user surface). Surfaced to the user only later via `install.sh` (P1.M6.T1.S1) and the systemd unit (P1.M6.T1.S2), which point `ExecStart=` at this wrapper.

## Why

- **Unblocks the daemon's CUDA path.** faster-whisper/ctranslate2 load the cuBLAS + cuDNN 9 `.so`s that live inside the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` pip wheels. The cuDNN 9 split sub-libs (`libcudnn_ops.so.9`, `libcudnn_cnn.so.9`, `libcudnn_eng.so.9`, …) are resolved **transitively** by the dynamic linker, and the wheels do not reliably embed a `$ORIGIN` `RUNPATH` for them — so without `LD_LIBRARY_PATH` the daemon crashes at startup with `cannot open shared object file: libcudnn_ops.so.9` (PRD §8 risk row #1; verified — see research_faster_whisper_cuda.md §2 and the wrapper research Q6).
- **`LD_LIBRARY_PATH` is read at `exec`, not at runtime.** The dynamic loader (`ld.so(8)`) processes `LD_LIBRARY_PATH` during its own initialization as part of `execve`. Mutating `os.environ["LD_LIBRARY_PATH"]` inside an already-running Python has **no effect** on that process (only on subsequently-`exec`'d children). Therefore the path MUST be exported **before** `python` starts. A wrapper that `exec`s python is the documented fix (faster-whisper README; research §2 option 1). The contract explicitly **forbids** the `os.execv`-re-exec-in-daemon.py approach (fragile, race-prone).
- **Idempotent + survives `uv sync`.** Because the lib dirs are recomputed from the installed wheels on every launch, the wrapper never goes stale when `uv sync` reinstalls wheels, bumps versions, or moves the venv. This beats the alternative (a literal `Environment=LD_LIBRARY_PATH=…` baked into the systemd unit by `install.sh`, which breaks if the venv path or wheel version changes).
- **Graceful CPU fallback.** On a no-GPU host (or before the nvidia wheels are installed), the wrapper logs a clear warning and still launches python; the daemon (P1.M4.T1.S1 / P1.M1.T2.S2) then detects CUDA failure and falls back to `device="cpu", compute_type="int8"` (PRD §4.4). The wrapper never hard-aborts on a missing lib — it only aborts if python itself is missing.
- **Scope discipline.** This subtask creates ONLY the launcher. It does NOT write `daemon.py` (P1.M4.T3.S1), the CUDA-smoke decision script (P1.M1.T2.S2), `install.sh` (P1.M6.T1.S1), or the systemd unit (P1.M6.T1.S2). It assumes S2 has populated `.venv` with the nvidia wheels and treats that as its input contract.

## What

Create `voice_typing/launch_daemon.sh` with: a `#!/usr/bin/env bash` shebang; a header comment block explaining the `LD_LIBRARY_PATH`-at-exec requirement and a `libcudnn_ops` debug runbook (links PRD §8 risk row); `set -euo pipefail`; CWD-independent resolution of the repo root + venv python; a guarded computation of the cuBLAS+cuDNN lib dirs (warn-and-continue on failure); export of `LD_LIBRARY_PATH`; and a final unconditional `exec "$PY" -m voice_typing.daemon "$@"` so Python becomes systemd's main service PID and receives SIGTERM directly.

### Success Criteria

- [ ] `voice_typing/launch_daemon.sh` exists and `test -x` passes (executable bit set).
- [ ] `bash -n voice_typing/launch_daemon.sh` exits 0 (syntax valid). `shellcheck` (if present) clean.
- [ ] First line is `#!/usr/bin/env bash`; `set -euo pipefail` present.
- [ ] Header comment block documents: the at-exec requirement, the dynamic-linker rationale, the `libcudnn_ops` debug steps, and references PRD §8 risk row #1.
- [ ] The exact one-liner `$PY -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))'`, run against S2's `.venv`, prints two `:`-separated dirs ending `/nvidia/cublas/lib` and `/nvidia/cudnn/lib`.
- [ ] `LD_LIBRARY_PATH="<that value>" $PY -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"` prints `>= 1` (the load-bearing sufficiency gate).
- [ ] Fallback branch: when the import fails, a warning containing "CPU fallback" goes to stderr AND the script proceeds to `exec` (non-zero exit comes from the exec'd process, not from `set -e`).
- [ ] Script ends in `exec "$PY" -m voice_typing.daemon "$@"` (NOT a backgrounded child) — verified by the fallback test reaching exec.
- [ ] No `daemon.py`, no `cuda_smoke*`, no `install.sh`, no `systemd/`, no model prefetch, no edits to `pyproject.toml`/`PRD.md`/`tasks.json`/`.gitignore`.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement T2.S1 from this PRP + the referenced research files. The exact script is given verbatim; every shell/systemd/loader behavior it depends on has been **empirically verified** (see the wrapper-research note); all commands use full paths (the machine's zsh aliases shadow `python3`→`uv run`, `pip`, `tmux`).

### Documentation & References

```yaml
# MUST READ — the authoritative source for the LD_LIBRARY_PATH trick + the cuDNN-9 requirement
- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md
  why: §2 confirms cuBLAS+cuDNN REQUIRED, "LD_LIBRARY_PATH must be set before launching Python",
       and ranks the wrapper (option 1) over systemd Environment= (option 2) and os.execv (option 3).
       Gives the exact faster-whisper one-liner this script implements.
  critical: "LD_LIBRARY_PATH is read at process exec, NOT mutable after import → the wrapper is the
       sanctioned approach; os.execv inside daemon.py is FORBIDDEN. cuDNN MUST be 9.x."

# MUST READ — this subtask's empirically-verified shell/systemd/loader behaviors
- docfile: plan/001_be48c74bc590/P1M1T2S1/research/launch_wrapper_bash_systemd_best_practices.md
  why: Answers the 7 load-bearing questions: exec→main-PID signal propagation (Q1), env-bash
       shebang reliability under systemd (Q2), set -euo pipefail + if-guard exemption (Q3), the
       nvidia.*.lib dir trick covering ALL cuDNN 9 split sub-libs incl libcudnn_ops.so.9 (Q4), the
       libcudnn_ops debug runbook (ldd/LD_DEBUG=libs/strace) + ld.so at-exec confirmation (Q5), when
       the wrapper is genuinely required despite ctranslate2 auto-dlopen (Q6), robust script-dir
       resolution (Q7).
  section: "Q3 (if-guard is exempt from set -e; ${LD_LIBRARY_PATH:+:…} is set -u safe) and Q4
       (single nvidia/cudnn/lib dir covers libcudnn_ops/cnn/eng/…) are the load-bearing ones."

# MUST READ — the INPUT contract: S2's populated .venv
- file: plan/001_be48c74bc590/P1M1T1S2/PRP.md
  why: Defines what S2 leaves behind — a .venv in which `import nvidia.cublas.lib` /
       `import nvidia.cudnn.lib` WORK and nvidia-cudnn-cu12 is 9.x; ctranslate2.get_cuda_device_count()
       recorded >= 1 (or flagged 0 → degraded path). T2.S1's success gate (c) re-runs S2's CUDA check
       THROUGH the wrapper's computed LD_LIBRARY_PATH.
  critical: "T2.S1 RUNS IN PARALLEL with S2 per the plan. At implementation time, if .venv is NOT yet
       populated (nvidia import fails), the wrapper's FALLBACK branch must still behave correctly —
       that is exactly what validation L4 tests. The happy-path gate (L2/L3) requires S2 done."

# Background — product spec (READ-ONLY)
- file: PRD.md
  why: §4.4 (the cuDNN/cuBLAS paragraph + the cpu/int8 degraded fallback) and §8 risk row #1
       ("cuDNN 'cannot load libcudnn_ops' at runtime → LD_LIBRARY_PATH wrapper per §4.4; set in
       systemd unit"). The wrapper's header comment must reference §8 risk row #1.
  critical: "PRD §4.9 ExecStart currently reads `.venv/bin/python -m voice_typing.daemon`; P1.M6.T1.S2
       will REPPOINT it at this wrapper. §4.4's degraded path (device=cpu) is the daemon's job, not
       the wrapper's — the wrapper only ensures the libs are findable."

# Background — system facts (READ-ONLY)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: §1 — uv 0.7.11 at /home/dustin/.local/bin/uv; .venv Python 3.12.10; shell aliases → ALWAYS
       use full paths; Arch Linux (bash at /usr/bin/bash, /bin→/usr/bin symlink). §2 target file map
       puts launch_daemon.sh inside voice_typing/. §4 decision #2: "LD_LIBRARY_PATH via launcher
       wrapper, NOT os.execv in-process."
  critical: "Do NOT use bare python/pip/uv/tmux in any command. /usr/bin/env bash resolves correctly
       under systemd (PATH includes /usr/bin) AND Arch (/bin is a symlink to /usr/bin)."
```

### Current Codebase tree (S1 complete, S2 in progress — the state at T2.S1 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*'` from repo root. Expected:

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores .venv, __pycache__, dist/, build/ (DO NOT touch)
├── .venv/                      # Python 3.12.10 — S2 populates this (realtimestt, faster-whisper,
│   │                             ctranslate2, nvidia-cublas-cu12, nvidia-cudnn-cu12(9.x), torch, …)
│   │                             AT T2.S1 TIME it MAY be empty (S2 parallel) OR populated.
│   └── bin/python              # the PY the wrapper execs (exists even pre-S2 from S1)
├── PRD.md                      # READ-ONLY
├── pyproject.toml              # ← S1's output (4 deps + build-system + 2 scripts) — UNCHANGED by T2.S1
├── uv.lock                     # ← S2's output (may not exist yet if S2 still running)
└── voice_typing/
    └── __init__.py             # ← S1's output (module docstring only) — voice_typing/ package dir EXISTS
# NO voice_typing/launch_daemon.sh yet — T2.S1 creates it (the ONLY new file).
# NO voice_typing/daemon.py (P1.M4.T3.S1), NO cuda_smoke (P1.M1.T2.S2), NO install.sh/systemd (P1.M6).
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── launch_daemon.sh        # ← CREATE (executable; the only new file)
# NOTHING ELSE. daemon.py is P1.M4.T3.S1; install.sh/systemd are P1.M6; cuda_smoke is P1.M1.T2.S2.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — LD_LIBRARY_PATH IS READ AT exec, NOT AT import. The dynamic linker (ld.so(8))
# processes it during its own init as part of execve. os.environ["LD_LIBRARY_PATH"]=... inside
# daemon.py has NO effect on the running process. HENCE the wrapper exports it BEFORE exec.
# (ld.so(8); research Q5.) This is the entire reason this file exists.

# CRITICAL #2 — DO NOT use os.execv / re-exec inside daemon.py. The contract + research §2 forbid it
# (fragile, race-prone, double-starts the process). The wrapper is the SINGLE sanctioned place to
# set LD_LIBRARY_PATH. daemon.py (P1.M4.T3.S1) must NOT touch LD_LIBRARY_PATH.

# CRITICAL #3 — cuDNN 9 split sub-libs are the actual failure point. The error is almost always
# `libcudnn_ops.so.9` (cuDNN 9 dropped the `_infer` suffix that cuDNN 8 had: libcudnn_ops_infer.so.8).
# When libcudnn.so.9 loads, its NEEDED entries (libcudnn_ops.so.9, libcudnn_cnn.so.9, libcudnn_eng.so.9,
# …) are resolved by the loader against the search path. The wheels don't ship $ORIGIN RUNPATH for
# these → "not found" without LD_LIBRARY_PATH. ONE path entry (nvidia/cudnn/lib) covers ALL of them
# (they live in the same dir). (research Q4/Q6.)

# CRITICAL #4 — the nvidia.*.lib dir trick is the documented faster-whisper incantation.
#   import os, nvidia.cublas.lib, nvidia.cudnn.lib
#   os.path.dirname(nvidia.cublas.lib.__file__)  →  …/site-packages/nvidia/cublas/lib   (libcublas.so.12)
#   os.path.dirname(nvidia.cudnn.lib.__file__)   →  …/site-packages/nvidia/cudnn/lib    (libcudnn.so.9 + ops/cnn/eng/…)
# This is verbatim from the faster-whisper README (CUDA/GPU install note). Do NOT "improve" it by
# hardcoding paths or globbing — computing from the live import is what makes it survive uv sync.

# CRITICAL #5 — set -euo pipefail IS SAFE here because the only fallible command (the nvidia import)
# sits inside `if CUDA_LIBS=$(…); then … else … fi`. Bash's errexit does NOT fire for a command
# "part of the test following the if reserved word" (Bash manual, The Set Builtin). The failed
# command-substitution routes to the else branch. ${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} is the
# set -u-safe append idiom (returns "" when LD_LIBRARY_PATH is unset). (research Q3.)

# CRITICAL #6 — exec (not a child) makes python systemd's MAIN PID. systemd execs the wrapper by
# absolute path (ExecStart=); the wrapper's final `exec "$PY" …` calls execve, REPLACING the bash
# image with python in the SAME PID. systemd (Type=simple, the default) tracks that PID as the main
# service process and delivers SIGTERM (KillSignal=) directly to python → clean shutdown. If python
# were a child, bash would be the main PID and would NOT forward SIGTERM (only the later cgroup
# SIGKILL). So the LAST line MUST be `exec "$PY" -m voice_typing.daemon "$@"`, never `"$PY" … &`.
# (research Q1; systemd.service Type=/KillSignal=.)

# GOTCHA #7 — CWD-independence. systemd may set WorkingDirectory= to anything (or nothing). The
# contract's literal `VENV_DIR="$(dirname "$0")/.."` works under systemd's absolute $0, but the
# robust form `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"; VENV_DIR="$(dirname "$SCRIPT_DIR")"`
# also works for MANUAL `./launch_daemon.sh` from any dir (which the implementer WILL do during
# validation). This PRP uses the robust form; both are verified CWD-independent under systemd.
# (research Q7.)

# GOTCHA #8 — `2>/dev/null` on the import one-liner suppresses the expected ImportError/traceback
# noise when the wheels are absent, so the wrapper's OWN clear warning is the only stderr output.
# Drop it temporarily during debugging if you want python's traceback. (Optional; documented in Task 2.)

# GOTCHA #9 — the wrapper is invoked by ABSOLUTE PATH from the repo checkout
# (/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh), NOT from site-packages. Even
# though [tool.hatch.build.targets.wheel] packages=["voice_typing"] would bundle the .sh into the
# wheel, systemd/install.sh call the SOURCE-TREE path. Packaging behavior is irrelevant to T2.S1.

# GOTCHA #10 — FULL PATHS in every bash CALL THE PRP MAKES (validation commands). This machine
# aliases python3→uv run, pip→alias, tmux→zsh plugin. Invoke /home/dustin/.local/bin/uv and
# .venv/bin/python explicitly. (Inside launch_daemon.sh itself, $PY is the venv python by
# construction — that's correct, not an alias issue.) (system_context.md §1.)

# GOTCHA #11 — daemon.py does NOT exist at T2.S1 time (P1.M4.T3.S1). So `exec "$PY" -m
# voice_typing.daemon` will FAIL with ModuleNotFoundError if you run the wrapper end-to-end now.
# That is EXPECTED. Validate the wrapper's LD_LIBRARY_PATH logic and exec-reach WITHOUT requiring
# daemon.py (validation L2/L3/L4 do exactly this). Full end-to-end daemon launch is P1.M4.T3.S1's
# gate, not T2.S1's.

# GOTCHA #12 — do NOT create a cuda_smoke script, install.sh, systemd unit, or prefetch models.
# Those are P1.M1.T2.S2, P1.M6.T1.S1, P1.M6.T1.S2, P1.M1.T3.S1 respectively. T2.S1 is ONE file.
```

## Implementation Blueprint

### Data models and structure

None. This subtask creates no Python code, no types, no schemas. The only "structure" is the `launch_daemon.sh` shell script (a linear sequence: shebang → comment block → `set` → path resolution → guarded `LD_LIBRARY_PATH` export → `exec`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs + that the target file does not yet exist (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/__init__.py && echo "voice_typing/ package dir exists (S1 ok)" \
        || echo "PREFLIGHT FAIL: voice_typing/ missing — S1 not complete"
      test ! -e voice_typing/launch_daemon.sh && echo "ok: launch_daemon.sh not yet created" \
        || echo "PREFLIGHT FAIL: launch_daemon.sh already exists"
      test -x .venv/bin/python && echo "ok: .venv/bin/python exists" \
        || echo "PREFLIGHT FAIL: .venv/bin/python missing"
      # S2 may still be running in parallel — check whether nvidia wheels landed (informational only):
      if .venv/bin/python -c 'import nvidia.cublas.lib, nvidia.cudnn.lib' 2>/dev/null; then
          echo "ok: nvidia wheels present (S2 done) — happy-path gates L2/L3 runnable"
      else
          echo "note: nvidia wheels NOT yet importable (S2 may be in progress) — happy-path gates L2/L3 will be SKIPPED/DEFERRED; L1/L4 (syntax + fallback) still runnable"
      fi
  - EXPECTED: voice_typing/ exists; launch_daemon.sh absent; .venv/bin/python executable. The nvidia
    check is informational — T2.S1 must create the wrapper correctly regardless (the fallback branch
    is the contract's answer to "wheels not present").
  - DO NOT: create daemon.py, install anything, or modify pyproject.toml.

Task 2: CREATE voice_typing/launch_daemon.sh (use the `write` tool with EXACTLY this content)
  - FILE: voice_typing/launch_daemon.sh
  - CONTENT (verbatim, including the leading #! and the trailing exec line):
    ----- BEGIN voice_typing/launch_daemon.sh -----
    #!/usr/bin/env bash
    #
    # launch_daemon.sh — LD_LIBRARY_PATH wrapper for the voice-typing daemon.
    #
    # WHY: faster-whisper / ctranslate2 load the cuBLAS + cuDNN 9 shared libraries that ship
    # inside the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` pip wheels. The dynamic linker
    # reads LD_LIBRARY_PATH ONLY at process exec (ld.so(8)), so it must be exported BEFORE
    # python starts — mutating os.environ inside daemon.py has NO effect on the running
    # process. This wrapper is the sanctioned fix (PRD §8 risk row #1:
    # "cuDNN 'cannot load libcudnn_ops' at runtime → LD_LIBRARY_PATH wrapper per §4.4").
    #
    # The lib dirs are recomputed from the LIVE installed wheels on every launch, so this
    # script survives `uv sync` reinstalls and version bumps without edits.
    #
    # DEBUGGING "cannot open shared object file: libcudnn_ops.so.9" (also libcudnn.so.9,
    # libcublas.so.12): cuDNN 9's split sub-libs (libcudnn_ops/cnn/eng/...) are resolved
    # transitively by the loader and the wheels lack a $ORIGIN RUNPATH for them, so they
    # MUST be on LD_LIBRARY_PATH. Triage, fastest first:
    #   1. journalctl --user -u voice-typing -e                  # wrapper stderr + python logs
    #   2. systemctl --user show voice-typing -p Environment     # is LD_LIBRARY_PATH set?
    #   3. LD_DEBUG=libs voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
    #   4. ldd .venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9   # NEEDED not found?
    #   5. strace -f -e openat voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn
    # (See PRD §8 "cuDNN cannot load libcudnn_ops" risk row.)
    #
    # CPU FALLBACK: if the nvidia wheels aren't importable (no-GPU host / not yet installed),
    # this script logs a clear warning and execs python WITHOUT the override. The daemon then
    # detects CUDA failure and runs device="cpu", compute_type="int8" (PRD §4.4; the
    # degraded-mode DECISION is made in P1.M1.T2.S2, not here).
    set -euo pipefail

    # Resolve own location CWD-independently (systemd calls us via absolute ExecStart; this
    # also works for a manual `./launch_daemon.sh` from any working directory).
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"   # .../voice_typing  (this file's dir)
    VENV_DIR="$(dirname "$SCRIPT_DIR")"            # repo root          (parent of voice_typing/)
    PY="$VENV_DIR/.venv/bin/python"

    if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))' 2>/dev/null)"; then
        export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    else
        echo "voice-typing: WARNING — could not import nvidia.cublas.lib / nvidia.cudnn.lib;" \
             "continuing WITHOUT the LD_LIBRARY_PATH override (CPU fallback path)." \
             "Expect CUDA init to fail; the daemon should fall back to device=cpu." >&2
    fi

    exec "$PY" -m voice_typing.daemon "$@"
    ----- END voice_typing/launch_daemon.sh -----
  - WHY each part:
      * shebang `#!/usr/bin/env bash`: systemd passes a PATH containing /usr/bin, and on Arch
        /bin is a symlink to /usr/bin, so env-bash resolves reliably (research Q2).
      * comment block: the contract's DOCS requirement ([Mode A]) — explains the at-exec
        requirement + the libcudnn_ops debug runbook + links PRD §8 risk row #1.
      * `set -euo pipefail`: safety; the only fallible command is inside the if-guard (exempt
        from errexit — research Q3); ${LD_LIBRARY_PATH:+:…} is the set-u-safe append.
      * SCRIPT_DIR via `cd "$(dirname "$0")" && pwd`: CWD-independent absolute path (research
        Q7). Equivalent to the contract's `$(dirname "$0")/..` under systemd but also robust
        for manual runs during validation.
      * the `if CUDA_LIBS="$(… 2>/dev/null)"; then … else warn >&2; fi`: the contract's guard.
        2>/dev/null suppresses the expected ImportError traceback so our warning is the only
        stderr noise (Gotcha #8 — drop it while debugging if you want python's traceback).
      * `exec "$PY" -m voice_typing.daemon "$@"`: replaces bash with python in the same PID →
        python becomes systemd's main PID, SIGTERM hits it directly (Gotcha #6, research Q1).
  - DO NOT: add a trailing newline-only line, remove the comment block, swap exec for a child,
    add os.execv guidance for daemon.py, or create any other file.

Task 3: chmod +x the wrapper
  - RUN: chmod +x voice_typing/launch_daemon.sh
  - VERIFY: test -x voice_typing/launch_daemon.sh && echo "executable bit set"
  - NOTE: `uv sync`/wheel-build does NOT preserve the exec bit reliably across reinstalls, and
    systemd ExecStart REQUIRES the executable bit. install.sh (P1.M6.T1.S1) will re-chmod +x
    idempotently; git tracks the mode bit in the source tree so the committed file is executable.
    Setting it here ensures validation L1 passes and the source tree is correct.

Task 4: VALIDATE — run the Validation Loop L1–L5 below. Fix until all applicable gates pass.
  - If S2 is NOT yet done (nvidia wheels absent — see preflight), SKIP L2/L3 (happy-path) but STILL
    run L1 (syntax/exec-bit) and L4 (fallback branch) and L5 (scope). Note in the report that L2/L3
    are deferred to "after S2 completes" (they are the load-bearing CUDA-sufficiency proof).
  - No git commit from T2.S1 unless the orchestrator directs it. If asked: message
    "P1.M1.T2.S1: launch_daemon.sh wrapper — sets cuBLAS+cuDNN LD_LIBRARY_PATH before exec'ing python".
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — the guarded LD_LIBRARY_PATH computation (the whole point of this file).
#   The failed command-substitution inside `if …; then` is EXEMPT from `set -e` (Bash manual,
#   The Set Builtin: errexit does not apply to commands "part of the test following the if").
#   So a missing-nvidia host falls through to the else branch, logs a warning, and still execs.
if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))' 2>/dev/null)"; then
    export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"   # set -u-safe append
else
    echo "voice-typing: WARNING … CPU fallback path." >&2                      # systemd → journald
fi

# PATTERN 2 — exec, not a child (signal propagation).
#   `exec "$PY" -m voice_typing.daemon "$@"` replaces bash with python in the SAME PID.
#   systemd (Type=simple default) tracks that PID as the service's main process and delivers
#   KillSignal= (default SIGTERM) directly to python → clean shutdown. A child python would be
#   SIGKILL'd only later via the cgroup, losing the clean-shutdown path P1.M4.T2.S2 needs.
exec "$PY" -m voice_typing.daemon "$@"

# PATTERN 3 — `-m voice_typing.daemon` sets __name__=="__main__" (RealtimeSTT multiprocessing guard).
#   The wrapper execs the MODULE (`-m`), not the console-script wrapper. `-m` sets __name__ to
#   "__main__", which RealtimeSTT REQUIRES for its multiprocessing (research_realtimestt_api.md
#   line 63/153). daemon.py (P1.M4.T3.S1) must still wrap main() in
#   `if __name__ == "__main__": main()` — the `-m` invocation makes that guard fire correctly.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M4.T3.S1 (daemon entry point):
  - The wrapper execs `python -m voice_typing.daemon`. daemon.py MUST define `main()` AND wrap it
    in `if __name__ == "__main__": main()` (RealtimeSTT multiprocessing). The `-m` form sets
    __name__=="__main__" correctly.
  - CRITICAL CONSTRAINT: daemon.py MUST NOT set LD_LIBRARY_PATH or use os.execv. The wrapper is the
    single sanctioned place. daemon.py may READ os.environ["LD_LIBRARY_PATH"] for logging but must
    not try to (re)set it (no effect — Gotcha #1). If CUDA init fails at runtime, daemon.py decides
    the cpu/int8 degraded path (P1.M1.T2.S2's decision logic, implemented in P1.M4.T1.S1).

DOWNSTREAM — P1.M6.T1.S2 (systemd/voice-typing.service):
  - ExecStart= MUST point at the ABSOLUTE source-tree path of this wrapper:
        ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
    (NOT .venv/bin/python -m voice_typing.daemon as in PRD §4.9's placeholder — the wrapper replaces
    that line. NOT the site-packages copy.)
  - Type=simple (the default) is correct — exec makes python the main PID (Gotcha #6).
  - The unit's commented-out `# Environment=LD_LIBRARY_PATH=...` placeholder (PRD §4.9) becomes
    UNNECESSARY — the wrapper computes it dynamically. P1.M6.T1.S2 should REMOVE that placeholder
    line (or leave it commented with a note "set by launch_daemon.sh, not here").

DOWNSTREAM — P1.M6.T1.S1 (install.sh):
  - install.sh does NOT need to compute or write LD_LIBRARY_PATH anywhere — the wrapper does it at
    runtime. install.sh only needs to: (a) `chmod +x voice_typing/launch_daemon.sh` (idempotent —
    git tracks the bit but re-asserting is safe), (b) write the systemd unit with ExecStart pointing
    at the wrapper's absolute path, (c) run the CUDA smoke (P1.M1.T2.S2) which may itself invoke
    this wrapper or replicate its LD_LIBRARY_PATH computation.

DOWNSTREAM — P1.M1.T2.S2 (CUDA smoke verification + degraded-mode decision):
  - T2.S2 decides device="cuda" vs the cpu/int8 degraded path. It consumes the SAME LD_LIBRARY_PATH
    computation this wrapper uses (S2's PRP Gotcha #3 documents the inline equivalent). If this
    wrapper's computed path yields ctranslate2.get_cuda_device_count()>=1 (validation L3 here), the
    daemon runs device="cuda"; if 0 even WITH the path, T2.S2 selects the degraded path. T2.S1 only
    proves the path is SUFFICIENT; T2.S2 makes the decision.

CONDITIONAL — nothing in T2.S1 modifies pyproject.toml, .gitignore, PRD.md, tasks.json, or any
source file other than creating voice_typing/launch_daemon.sh and setting its exec bit.

BUILD ARTIFACTS:
  - T2.S1 creates NO dist/, no uv.lock changes, no .venv changes. The wrapper is a plain text file
    (+x) in the source tree. `uv build`/`uv sync` are NOT run by T2.S1.
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases). Run from `/home/dustin/projects/voice-typing`. L2/L3
> require S2 to have populated `.venv` with the nvidia wheels; if S2 is still in progress
> (preflight reports "nvidia wheels NOT yet importable"), run L1/L4/L5 now and DEFER L2/L3 until S2
> completes (re-run this whole loop then). L1/L4/L5 are always runnable.

### Level 1: Syntax, exec-bit, shebang, structure (no deps, no network)

```bash
cd /home/dustin/projects/voice-typing
test -f voice_typing/launch_daemon.sh && echo "L1 file present" || echo "L1 FAIL: file missing"
test -x voice_typing/launch_daemon.sh && echo "L1 exec bit OK" || echo "L1 FAIL: not executable"
head -1 voice_typing/launch_daemon.sh | grep -qx '#!/usr/bin/env bash' && echo "L1 shebang OK" || echo "L1 FAIL: shebang"
bash -n voice_typing/launch_daemon.sh && echo "L1 bash -n OK (syntax valid)" || echo "L1 FAIL: syntax error"
grep -q '^set -euo pipefail$' voice_typing/launch_daemon.sh && echo "L1 set -euo pipefail OK" || echo "L1 FAIL: missing set"
grep -q '^exec "\$PY" -m voice_typing.daemon "\$@"$' voice_typing/launch_daemon.sh && echo "L1 final-exec OK" || echo "L1 FAIL: no exec line"
grep -qi 'cpu fallback' voice_typing/launch_daemon.sh && echo "L1 fallback comment OK" || echo "L1 FAIL: no CPU fallback doc"
grep -qi 'PRD §8' voice_typing/launch_daemon.sh && echo "L1 PRD §8 ref OK" || echo "L1 FAIL: no PRD §8 risk-row reference"
grep -qi 'LD_DEBUG' voice_typing/launch_daemon.sh && echo "L1 debug runbook OK" || echo "L1 FAIL: no LD_DEBUG debug hint"
# shellcheck (optional — if installed):
command -v shellcheck >/dev/null && shellcheck voice_typing/launch_daemon.sh && echo "L1 shellcheck clean" || echo "L1 shellcheck skipped/not-installed (non-blocking)"
# Expected: file present, executable, shebang #!/usr/bin/env bash, bash -n clean, set -euo pipefail
# present, final exec line present, CPU-fallback + PRD §8 + LD_DEBUG mentioned in the comment block.
```

### Level 2: Happy-path computation — the nvidia.*.lib one-liner returns the two lib dirs

> **Requires S2 done** (nvidia wheels installed). If preflight said "NOT yet importable", SKIP L2/L3
> and defer; run L1/L4/L5 now.

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
OUT=$("$PY" -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))')
echo "L2 computed LD_LIBRARY_PATH = $OUT"
# Assert exactly two colon-separated dirs, ending in nvidia/cublas/lib and nvidia/cudnn/lib:
echo "$OUT" | grep -q 'nvidia/cublas/lib$' && echo "first dir ok" || echo "L2 FAIL: no cublas/lib"
echo "$OUT" | grep -q ':.*/nvidia/cudnn/lib$' && echo "second dir ok" || echo "L2 FAIL: no cudnn/lib"
# Confirm the cudnn dir actually holds the ops sub-lib that is the usual failure point:
ls "$(/usr/bin/python3 -c 'import os,nvidia.cudnn.lib as m,sys; sys.path.insert(0,".venv/lib/python3.12/site-packages"); print(os.path.dirname(m.__file__))' 2>/dev/null || echo ".venv/lib/python3.12/site-packages/nvidia/cudnn/lib")" | grep -E 'libcudnn_ops\.so|libcudnn\.so' && echo "L2 cudnn ops/cnn sub-libs present in one dir" || echo "L2 note: list the cudnn/lib dir manually"
# Expected: OUT = "<…>/site-packages/nvidia/cublas/lib:<…>/site-packages/nvidia/cudnn/lib"; the cudnn
# dir contains libcudnn.so.9 AND libcudnn_ops.so.9 (+ cnn/eng/…) — one path entry covers all of them.
```

### Level 3: Sufficiency (the load-bearing CUDA gate) — wrapper's path makes ctranslate2 see the GPU

> **Requires S2 done.** This re-runs S2's ctranslate2 gate THROUGH the wrapper's exact LD_LIBRARY_PATH,
> proving the wrapper's computation is sufficient for CUDA (not just syntactically correct).

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
CUDA_LIBS=$("$PY" -c 'import os,nvidia.cublas.lib,nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))')
# (a) with the wrapper's LD_LIBRARY_PATH:
CT2_WITH=$(LD_LIBRARY_PATH="$CUDA_LIBS" "$PY" -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())")
echo "L3a CT2_CUDA_DEVICES with wrapper path = $CT2_WITH"
# (b) sanity: WITHOUT the path (auto-dlopen only) — may be lower/fail; documents why the wrapper exists:
CT2_BARE=$("$PY" -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())" 2>/dev/null || echo "(bare import failed — libcudnn_ops not found, as expected without LD_LIBRARY_PATH)")
echo "L3b CT2_CUDA_DEVICES bare (no override) = $CT2_BARE"
[ "${CT2_WITH:-0}" -ge 1 ] && echo "L3 PASS: wrapper's LD_LIBRARY_PATH is SUFFICIENT for CUDA (>=1 device)" || echo "L3 *** MUST INVESTIGATE ***: even WITH the path, ctranslate2 sees 0 devices — flag P1.M1.T2.S2 (real CUDA/driver problem, not a wrapper bug)"
# Expected L3a: >= 1 (the whole project's must-have). L3b may be 0 or a failed import — that is
# PRECISELY why this wrapper exists (auto-dlopen doesn't cover cuDNN 9 split sub-libs — research Q6).
```

### Level 4: Fallback branch — import failure warns + still execs (does NOT exit on the failed import)

> Always runnable (deliberately simulates "wheels absent" with a fake python — non-destructive, no
> real uninstall). This is the deterministic proof the guard survives `set -e` and reaches `exec`.

```bash
cd /home/dustin/projects/voice-typing
# Make a fake "python" that always exits 1 (simulates the nvidia import failing inside the -c):
FAKEBIN=$(mktemp -d)
printf '#!/usr/bin/env bash\nexit 1\n' > "$FAKEBIN/python"
chmod +x "$FAKEBIN/python"
# Copy the wrapper, repoint PY at the fake python (the guard then sees a failing import → else branch):
sed "s#^PY=.*#PY=\"$FAKEBIN/python\"#" voice_typing/launch_daemon.sh > /tmp/vt_launcher_test.sh
chmod +x /tmp/vt_launcher_test.sh
# Run it: fake python exits 1 on the -c → else branch → warning to stderr → exec fake python (exit 1).
OUT=$(/tmp/vt_launcher_test.sh 2>&1; echo "exit=$?")
echo "$OUT"
echo "$OUT" | grep -qi 'cpu fallback' && echo "L4a PASS: fallback warning emitted to stderr" || echo "L4 FAIL: no CPU-fallback warning"
echo "$OUT" | grep -q 'exit=1' && echo "L4b PASS: exec was reached (process replaced by PY; non-zero exit from exec'd process, NOT from set -e)" || echo "L4 FAIL: did not reach exec"
# Structural floor (in case the dynamic test is skipped): confirm the if/else/fi + >&2 are present:
grep -q 'if CUDA_LIBS=' voice_typing/launch_daemon.sh && grep -q '>&2' voice_typing/launch_daemon.sh && echo "L4c PASS: guard structure (if/else + >&2) present" || echo "L4 FAIL: guard structure missing"
rm -rf "$FAKEBIN" /tmp/vt_launcher_test.sh
# Expected: warning printed, exec reached (exit=1 from the fake python), guard structure present.
```

### Level 5: Scope guards — only launch_daemon.sh created; nothing out of scope touched

```bash
cd /home/dustin/projects/voice-typing
# The ONE new file:
test -x voice_typing/launch_daemon.sh && echo "L5 PASS: launch_daemon.sh exists + executable" || echo "L5 FAIL"
# Nothing else created:
for f in voice_typing/daemon.py voice_typing/cuda_smoke.py launch_daemon.sh install.sh \
         systemd/voice-typing.service config.toml README.md; do
  test ! -e "$f" && echo "absent (ok): $f" || echo "L5 SCOPE WARNING: $f exists (out of scope?)"
done
# Models NOT prefetched (T3's job):
ls ~/.cache/huggingface/hub 2>/dev/null | grep -iq whisper && echo "L5 SCOPE WARNING: models prefetched (T3's job)" || echo "absent (ok): no whisper models"
# Read-only files UNCHANGED:
git status --short
git diff --exit-code -- PRD.md plan/001_be48c74bc590/tasks.json .gitignore pyproject.toml && echo "L5 PASS: read-only files unchanged" || echo "L5 FAIL: a read-only file was modified"
# git status should show ONLY: voice_typing/launch_daemon.sh (new, mode 100755).
# Expected: launch_daemon.sh is the sole new file; no daemon.py/cuda_smoke/install.sh/systemd/models;
# PRD.md/tasks.json/.gitignore/pyproject.toml byte-identical to before.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: file exists, `test -x`, shebang `#!/usr/bin/env bash`, `bash -n` clean, `set -euo pipefail` + final `exec` line present, comment block has CPU-fallback + PRD §8 + LD_DEBUG.
- [ ] L2 (if S2 done): the nvidia.*.lib one-liner prints `<…>/nvidia/cublas/lib:<…>/nvidia/cudnn/lib`; the cudnn dir holds `libcudnn_ops.so.9`.
- [ ] L3 (if S2 done): `LD_LIBRARY_PATH="<L2 value>"` → `ctranslate2.get_cuda_device_count() >= 1` (wrapper path is SUFFICIENT for CUDA).
- [ ] L4: fallback branch emits "CPU fallback" warning to stderr AND reaches exec (exit from exec'd process, not set -e); guard structure (if/else + `>&2`) present.
- [ ] L5: `voice_typing/launch_daemon.sh` is the SOLE new file; no out-of-scope artifacts; read-only files unchanged.

### Feature Validation
- [ ] `LD_LIBRARY_PATH` is exported BEFORE `exec "$PY"` (at-exec, per ld.so(8)) — verified by L3.
- [ ] The path is computed from the LIVE installed wheels (survives `uv sync`) — verified by L2 using `import nvidia.*.lib`, not a hardcoded path.
- [ ] CPU fallback: missing nvidia wheels → clear stderr warning + still execs python (no hard abort) — verified by L4.
- [ ] `exec` (not a child) so python becomes systemd's main PID for clean SIGTERM — verified structurally (L1 final-exec line) + by L4 reaching exec.
- [ ] daemon.py is NOT expected to set LD_LIBRARY_PATH / use os.execv (constraint documented for P1.M4.T3.S1).

### Code Quality / Scope Validation
- [ ] Only `voice_typing/launch_daemon.sh` created (+ exec bit); no other source files.
- [ ] No `daemon.py`, `cuda_smoke*`, `install.sh`, `systemd/`, model prefetch, `config.toml`, `README.md`.
- [ ] `pyproject.toml`, `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md` UNCHANGED.
- [ ] No bare `python`/`pip`/`uv`/`tmux` in any validation command (all full-pathed; `$PY` inside the script is the venv python by construction).
- [ ] No `uv sync` / `uv add` / `uv build` / `uv lock` executed (resolve+install is S2; build is S1).

### Documentation & Deployment
- [ ] Header comment block explains: the at-exec requirement, the dynamic-linker rationale, the `libcudnn_ops` debug runbook (journalctl / systemctl show / LD_DEBUG=libs / ldd / strace), and references PRD §8 risk row #1.
- [ ] CPU-fallback behavior documented in the comment block (degraded-mode DECISION is P1.M1.T2.S2's, not the wrapper's — noted).
- [ ] If asked to commit: message "P1.M1.T2.S1: launch_daemon.sh wrapper — sets cuBLAS+cuDNN LD_LIBRARY_PATH before exec'ing python".

---

## Anti-Patterns to Avoid

- ❌ Don't set `LD_LIBRARY_PATH` inside `daemon.py` (or via `os.execv` re-exec) — it has no effect on the running process and the contract forbids it. The wrapper is the single sanctioned place (Gotcha #1/#2).
- ❌ Don't hardcode the lib paths — computing from the live `nvidia.*.lib` import is what makes the wrapper survive `uv sync` (Gotcha #4).
- ❌ Don't run python as a child (`"$PY" …` without `exec`, or backgrounded) — bash would be systemd's main PID and would NOT forward SIGTERM; the daemon loses clean shutdown. The last line MUST be `exec "$PY" -m voice_typing.daemon "$@"` (Gotcha #6, research Q1).
- ❌ Don't drop the `if CUDA_LIBS=…; then … else warn; fi` guard — without it a missing-nvidia host crashes instead of falling back to CPU (the contract's explicit guard requirement).
- ❌ Don't fear `set -euo pipefail` — the failed command-substitution inside the `if`-condition is exempt from errexit (Bash manual; research Q3). `${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` is the set-u-safe append.
- ❌ Don't use `#!/bin/sh` — the script uses bash-isms (`set -o pipefail`, `[[ ]]`-style `${var:+…}`); `#!/usr/bin/env bash` is correct and verified reliable under systemd (research Q2).
- ❌ Don't drop the comment block — the contract's DOCS requirement ([Mode A]) mandates the LD_LIBRARY_PATH explanation + `libcudnn_ops` debug hints + PRD §8 link.
- ❌ Don't create daemon.py / cuda_smoke / install.sh / systemd / config.toml / README / models — those are P1.M4.T3.S1 / P1.M1.T2.S2 / P1.M6 / later. T2.S1 is ONE file.
- ❌ Don't run the wrapper end-to-end expecting `python -m voice_typing.daemon` to succeed — daemon.py doesn't exist yet (P1.M4.T3.S1); ModuleNotFoundError is EXPECTED. Validate the LD_LIBRARY_PATH logic and exec-reach via L1–L5 (Gotcha #11).
- ❌ Don't use bare `python`/`pip`/`uv`/`tmux` in validation commands (zsh aliases shadow them); use `.venv/bin/python` and `/home/dustin/.local/bin/uv` (Gotcha #10).
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or `pyproject.toml` (READ-ONLY / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a single ~40-line bash script whose entire content is given verbatim, and **every shell/systemd/dynamic-loader behavior it depends on has been empirically verified** in `research/launch_wrapper_bash_systemd_best_practices.md`: `exec`→main-PID→SIGTERM propagation under `Type=simple` (Q1, systemd.service docs); `#!/usr/bin/env bash` reliability under systemd's PATH (Q2); `set -euo pipefail` + `if`-guard errexit exemption + `${LD_LIBRARY_PATH:+:…}` set-u-safety (Q3, Bash manual); the `nvidia.cublas.lib`/`nvidia.cudnn.lib` `dirname(__file__)` trick covering ALL cuDNN 9 split sub-libs incl. `libcudnn_ops.so.9` in one dir (Q4, faster-whisper README + PyPI wheel layout); the `ldd`/`LD_DEBUG=libs`/`strace` debug runbook + ld.so at-exec confirmation (Q5); why the wrapper is required despite ctranslate2 auto-dlopen (Q6, cuDNN 9 sub-libs resolved transitively, no `$ORIGIN` RUNPATH); and CWD-independent `SCRIPT_DIR` resolution (Q7). The nvidia one-liner is taken verbatim from the faster-whisper README and is functionally identical to the contract's specification. The −1 residual risk is **scheduling**, not correctness: T2.S1 runs in parallel with S2, so the load-bearing happy-path gates (L2/L3) require S2 to have populated `.venv` with the nvidia wheels — if S2 is still in progress at implementation time, L2/L3 are deferred (the PRP says so explicitly) and only L1/L4/L5 run now. The fallback branch (L4) is deterministically testable WITHOUT S2 (via a fake-python simulation), so the wrapper's correctness is provable independent of S2's timing. No Python code is written, so there is no "implementation bug" surface beyond the script text — which is specified character-for-character.
