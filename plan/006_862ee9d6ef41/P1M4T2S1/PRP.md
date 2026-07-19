# PRP — P1.M4.T2.S1: Audit launch_daemon.sh — lib discovery, HF_HUB_OFFLINE, WAYLAND_DISPLAY import (vs PRD §4.4)

## Goal

**Feature Goal**: Produce the authoritative **`voice_typing/launch_daemon.sh` compliance audit** as a NEW
`gap_launch_daemon.md` report — verifying **ALL** work-item contract points + PRD §4.4 against the LIVE
wrapper: (a) **dynamically discovers** `nvidia.cublas.lib` + `nvidia.cudnn.lib` lib dirs (NOT baked);
(b) **prepends** them to `LD_LIBRARY_PATH`; (c) **exports `HF_HUB_OFFLINE=1`** (acceptance #8 no-network);
(d) **re-fetches `WAYLAND_DISPLAY`/`DISPLAY`** from `systemctl --user show-environment`; (e) **execs**
`python -m voice_typing.daemon`; and **NO baked/stale `LD_LIBRARY_PATH`**. This is a **READ-ONLY AUDIT**:
the deliverable is the report file; NO source is modified (the wrapper is compliant — this PRP's research
verified all 5 points + 15/15 tests pass + the live lib-discovery probe resolves both dirs; the audit
re-confirms live). Satisfies **Acceptance #8** ("no network at runtime — `HF_HUB_OFFLINE=1` is the
mechanism the wrapper exports").

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md` — a NEW self-contained `# Gap Report —
  P1.M4.T2.S1: …` file (there is NO existing `gap_launch_daemon.md`; this subtask creates it). Format
  mirrors `gap_typing.md` / `gap_systemd.md` / `gap_cuda_check.md`. Verbatim content in Implementation
  Blueprint → Task 3 (the evidence is pre-filled from verified file:line + pinning tests + the live
  lib probe; the auditor re-confirms the line numbers live + records the live pytest count).

> **VERIFIED VERDICT (this PRP's research): `launch_daemon.sh` is COMPLIANT with PRD §4.4 + the work-item
> contract — no fix needed.** All 5 contract points present + correct: dynamic discovery (`CUDA_LIBS="$PY
> -c 'import … nvidia.cublas.lib … nvidia.cudnn.lib …'"` :48-52, with the `_d()` namespace-package
> fallback `__file__ is None → __path__[0]` :50-51); `export LD_LIBRARY_PATH="$CUDA_LIBS…"` (:53);
> `export HF_HUB_OFFLINE=1` (:71) + `export TRANSFORMERS_OFFLINE=1` (:72); the `for _v in WAYLAND_DISPLAY
> DISPLAY; do … systemctl --user show-environment …` loop (:93-95); `exec "$PY" -m voice_typing.daemon
> "$@"` (:103); and NO baked `LD_LIBRARY_PATH` (the only assignment is the dynamic `$CUDA_LIBS` :53; the
> only `/home/`/`site-packages` literal is a comment :22). The live lib-discovery probe resolves BOTH
> dirs + confirms `libcudnn_ops*.so` + `libcublas*.so` are present inside them. `tests/test_systemd_unit.py`
> = **15 passed in 0.01s** (re-run live this round).
>
> **The audit's value-add (HEADLINE NUANCE):** the wrapper's *NAMESAKE* feature — the dynamic cuBLAS/cuDNN
> discovery + `LD_LIBRARY_PATH` prepend (contract points a+b, the wrapper's reason-to-exist per PRD §4.4) —
> has **NO test coverage**. The two cross-file tests pin only the LATER bugfix additions (offline vars
> `:115`; WAYLAND fetch `:164`). The audit confirms a+b by direct read + the live probe + records the
> coverage gap (§5.1) so a regression (a reverted `import nvidia.cublas.lib`, a stale baked path) cannot
> ship silently. This mirrors `gap_systemd.md`'s `KillMode=mixed` nuance.

**Success Definition**:
- (a) The report verifies **all 5** work-item contract points + the "no baked `LD_LIBRARY_PATH`" check
  against the LIVE `voice_typing/launch_daemon.sh` (re-grep — not trusting this PRP's line numbers blindly)
  and records a ✅ verdict + file:line evidence + a pinning test (or "coverage gap §5.x") for each.
- (b) The live **lib-discovery probe** (the exact `python -c` the wrapper runs) is re-run under `timeout 60`
  + the resolved cublas/cudnn dirs + the `libcudnn_ops`/`libcublas` presence are recorded in §3 — the
  runtime proof the dynamic path works (which NO test exercises).
- (c) The contract's mandated test command — `.venv/bin/python -m pytest tests/test_systemd_unit.py -q` —
  is re-run live (under `timeout 60`, per AGENTS.md Rule 1) and the pass count recorded in §4 (do NOT
  hard-code; record what the live run prints; this research: **15 passed in 0.01s**).
- (d) The report documents the **headline nuance — the lib-discovery + LD_LIBRARY_PATH coverage gap**
  (§5.1): the two cross-file tests pin offline-vars (`:115`) + WAYLAND-fetch (`:164`) + the exec target,
  but NEITHER references `nvidia.cublas.lib`/`CUDA_LIBS`/`LD_LIBRARY_PATH` — so the wrapper's primary
  function is the LEAST tested part of it (coverage gap, NOT a code defect).
- (e) The report documents the other non-defect nuances (§5.2 read-at-execve semantics; §5.3 WAYLAND
  belt-and-suspenders for the cold-boot race; §5.4 the CPU-fallback `else` branch; + §2 the robustness
  extras `set -euo pipefail`/CWD-resolution/`_d()` fallback/`${:+:}` idiom).
- (f) **No source files are modified** — `voice_typing/launch_daemon.sh` / `tests/test_systemd_unit.py` /
  `systemd/voice-typing.service` / `install.sh` / `PRD.md` are compliant + read-only; the only artifact
  change is creating `gap_launch_daemon.md`. `git status --short` shows ONLY
  `plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md`.
- (g) The report's scope is **`launch_daemon.sh` ONLY** — NOT the systemd unit directives (P1.M4.T1.S1 →
  `gap_systemd.md`), NOT `install.sh` (P1.M4.T3.S1), NOT `hypr-binds.conf` (P1.M4.T4.S1), NOT cuda_check's
  probe (P1.M1.T4.S1 → `gap_cuda_check.md`, which records the cuDNN limitation this wrapper REMEDIATES),
  NOT the daemon teardown (P1.M2.T2.S3 → `gap_lifecycle.md`). The cross-file tests are cited as evidence
  the wrapper's ExecStart wiring + offline/WAYLAND behavior are exercised.

## User Persona

**Target User**: the verification-round maintainer (and the downstream P1.M5.T5 acceptance cross-check,
which maps Acceptance #8 "no network at runtime" to this audit's `HF_HUB_OFFLINE=1` evidence) who needs an
authoritative, file:line-evidenced record that the LD_LIBRARY_PATH wrapper matches PRD §4.4 on every
contract point — incl. the dynamic (not baked) cuDNN discovery, the `HF_HUB_OFFLINE=1` no-network guarantee,
and the boot-order-robust WAYLAND re-fetch — so a regression (a hardcoded lib path that goes stale on
`uv sync`, a dropped `HF_HUB_OFFLINE` that re-enables the huggingface.co startup GET, a reverted WAYLAND
fetch that re-breaks wtype on cold boot) cannot ship silently.

**Use Case**: A reviewer asks "does the wrapper (1) compute cuBLAS/cuDNN lib dirs from the live wheels,
(2) prepend them to LD_LIBRARY_PATH, (3) set HF_HUB_OFFLINE=1, (4) fetch WAYLAND_DISPLAY from the user
manager, (5) exec the daemon — exactly as PRD §4.4 + the contract say, with NO baked path?" The report
answers yes/no per point with the exact source line + the pinning test (or the coverage-gap note) + the
live lib-probe proof.

**Pain Points Addressed**: Without this audit, the wrapper's PRIMARY function (the cuDNN/cuBLAS discovery)
is invisible — no test pins it, so a stale-path regression or a broken namespace-package fallback would
pass CI and surface only as "cannot open shared object file: libcudnn_ops.so.9" in production (PRD §8 risk
row #1). The audit pins contract points a+b to PRD §4.4 with read + live-probe evidence + records the
coverage gap, closing the verification hole the test suite leaves open.

## Why

- **The wrapper is the ExecStart** (systemd `voice-typing.service` `ExecStart=__REPO__/voice_typing/
  launch_daemon.sh`), so what lives in the repo IS what runs on every daemon launch. A drift here ships
  straight to a cuDNN-load failure or a network-phone-home. The audit + the 15-test suite (the offline +
  WAYLAND parts) are the guard; this audit ADDS the lib-discovery coverage the suite lacks.
- **`LD_LIBRARY_PATH` + `HF_HUB_OFFLINE` are read at execve/import time** (ld.so(8) / huggingface_hub
  `constants.py`) — they CANNOT live in `daemon.py` (`os.environ` mutation has no effect post-start).
  The wrapper is the ONLY sanctioned place. The audit certifies both are exported BEFORE `exec` (the
  cross-file tests enforce this ordering; the audit confirms by read).
- **The dynamic discovery is the load-bearing correctness detail.** PRD §4.4 explicitly forbids a baked
  `Environment=LD_LIBRARY_PATH=` in the unit ("it would go stale on `uv sync`"); the wrapper recomputes
  from the live wheels every launch. The audit proves the discovery is dynamic (`$PY -c 'import
  nvidia.cublas.lib …'`) + records the non-obvious `_d()` namespace-package fallback (without it the
  faster-whisper README one-liner `os.path.dirname(nvidia.cublas.lib.__file__)` would CRASH — `__file__`
  is `None` for the namespace-package `nvidia/cublas/lib`).
- **Acceptance #8 (no network at runtime) is satisfied BY this wrapper's `HF_HUB_OFFLINE=1` export.** The
  audit ties the verdict to that acceptance criterion (P1.M5.T5 maps it here).
- **Read-only + parallel-safe.** The audit reads `voice_typing/launch_daemon.sh` + `tests/test_systemd_unit.py`
  and CREATES `gap_launch_daemon.md`. No source edits → no conflict with the in-flight P1.M4.T1.S1
  (systemd-unit audit, disjoint file).
- **The research already did the work.** This PRP's research note pre-maps every contract point to its
  file:line + verdict + pinning test + the live probe, so the implementing agent re-verifies + writes the
  report in one pass.

## What

A read-only verification of `voice_typing/launch_daemon.sh` (the 103-line bash ExecStart wrapper, PRD §4.4
+ §4.9 `ExecStart`) — re-confirmed live via grep + the live lib-discovery probe + the pytest re-run, then
documented as a new `gap_launch_daemon.md` (mirroring `gap_typing.md`'s format). The 5 contract points +
the no-baked-path check + the live probe + the headline lib-discovery coverage gap + the other nuances.

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md` exists, titled `# Gap Report — P1.M4.T2.S1: launch_daemon.sh LD_LIBRARY_PATH wrapper & cuDNN discovery vs PRD §4.4`.
- [ ] The report records a ✅ verdict + `voice_typing/launch_daemon.sh` file:line + a pinning test (or
  "coverage gap §5.x") for each of the 5 contract points + the no-baked-path check.
- [ ] The live lib-discovery probe (`timeout 60 .venv/bin/python -c '...'` — the exact `python -c` the
  wrapper runs) is re-run; the resolved cublas/cudnn dirs + `libcudnn_ops`/`libcublas` presence are
  recorded in §3.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` is re-run live; its pass count
  (baseline 15) is recorded (not hard-coded).
- [ ] The headline nuance (§5.1: lib-discovery + LD_LIBRARY_PATH coverage gap — the wrapper's namesake
  feature is the LEAST tested part of it) is documented.
- [ ] The other nuances (§5.2 read-at-exec; §5.3 WAYLAND belt-and-suspenders; §5.4 CPU-fallback else) +
  the robustness extras (§2) are documented.
- [ ] The report ties the verdict to Acceptance #8 (no network at runtime — `HF_HUB_OFFLINE=1`).
- [ ] `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md` — NO source modified.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the task
nature (read-only audit → new report file), the `gap_typing.md` / `gap_systemd.md` FORMAT template, the
verified verdict (compliant) + the file:line evidence + the pinning test for all 5 contract points + the
no-baked-path check, the live lib-probe command + its expected output, the headline lib-discovery coverage
gap, the other nuances, the exact test command, the verbatim report body (Task 3), and the scope boundaries
are all pinned. The audit re-verifies live (re-grep + re-run + re-probe) rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the audit's verdict + file:line evidence + the nuances + scope boundaries
- docfile: plan/006_862ee9d6ef41/P1M4T2S1/research/launch_daemon_audit.md
  why: "§0 THE VERIFIED VERDICT: wrapper COMPLIANT (15/15 tests + live lib probe). §1 the 5-point contract
        table (each -> launch_daemon.sh:line -> ✅ -> pinning test or 'coverage gap §5.x'). §2 the robustness
        extras (set -euo pipefail / CWD-resolution / the _d() namespace fallback / ${:+:} idiom / CPU-fallback
        else). §3 the live lib-discovery probe (the exact python -c + observed cublas/cudnn dirs). §4 the 4
        non-defect nuances (§4.1 the HEADLINE lib-discovery coverage gap; §4.2 read-at-exec; §4.3 WAYLAND
        belt-and-suspenders; §4.4 CPU-fallback else). §5 scope boundaries. §6 output + format. §7 tooling."
  section: "ALL load-bearing. §1 (verdict+evidence), §3 (live probe), §4.1 (the headline nuance), §5 (scope)."

# MUST READ — the file being audited (voice_typing/launch_daemon.sh — the 5 contract points)
- file: voice_typing/launch_daemon.sh
  why: "AUDIT TARGET (read-only, 103 lines). set -euo pipefail :30. CWD-resolution SCRIPT_DIR/VENV_DIR/PY
        :34-36. The dynamic discovery CUDA_LIBS=\"$PY -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib
        as b ...'\" :48-52 with the _d() namespace fallback (f=getattr(m,__file__,None); return os.path.dirname(f)
        if f else next(iter(m.__path__))) :50-51. export LD_LIBRARY_PATH=\"$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\"
        :53. The CPU-fallback else (WARNING + exec without override) :54-58. export HF_HUB_OFFLINE=1 :71 +
        export TRANSFORMERS_OFFLINE=1 :72. The WAYLAND/DISPLAY fetch loop (for _v in WAYLAND_DISPLAY DISPLAY;
        systemctl --user show-environment -p \"$_v\" --value) :93-95. exec \"$PY\" -m voice_typing.daemon \"$@\"
        :103. The header comment (lines 1-28) documents the WHY (ld.so reads LD_LIBRARY_PATH at exec; the cuDNN
        libcudnn_ops split-sublib triage)."
  critical: "RE-VERIFY by grep (`grep -nE 'CUDA_LIBS=|export LD_LIBRARY_PATH|export HF_HUB_OFFLINE|export
             TRANSFORMERS_OFFLINE|show-environment|exec \"\\$PY\"' voice_typing/launch_daemon.sh`) — do NOT
             trust the line numbers blindly (re-locate them live). Confirm the only LD_LIBRARY_PATH
             ASSIGNMENT is the dynamic $CUDA_LIBS (:53) — `grep -nE '^[^#]*LD_LIBRARY_PATH' voice_typing/
             launch_daemon.sh` must show :53 as the sole non-comment assignment (the rest are comments).
             The audit READS this file; it does NOT edit it (compliant code = no modification). NEVER exec
             this script (AGENTS.md Rule 2 — it blocks forever as the daemon)."

# MUST READ — the test file (coverage to cite per contract point; the contract's run command)
- file: tests/test_systemd_unit.py
  why: "440-line suite, 15 tests, pure-stdlib re+pathlib (parses the unit + wrapper/install/binds files; NO
        live systemd/GPU/CUDA/daemon/mic). _launch_daemon_path() (:56) resolves voice_typing/launch_daemon.sh.
        The 2 launch_daemon cross-file tests: test_launch_daemon_exports_offline_vars (:115) — asserts ^export
        HF_HUB_OFFLINE=1 (:140) + ^export TRANSFORMERS_OFFLINE=1 (:144) present + BEFORE exec (:150-152, the
        ordering assertion); test_launch_daemon_fetches_wayland_display_from_manager (:164) — asserts systemctl
        --user show-environment (:186) + WAYLAND_DISPLAY (:193) present + BEFORE exec (:196). test_execstart_
        points_at_launch_daemon_wrapper (:71) is the unit-side test (ExecStart -> wrapper). Run it + record
        the count."
  critical: "Characterize coverage accurately. The 2 cross-file tests pin contract points (c) offline vars +
            (d) WAYLAND fetch + (e) the exec target + the BEFORE-exec ordering. They do NOT pin (a) the
            dynamic discovery, (b) the LD_LIBRARY_PATH prepend, or the no-baked-path check — that is the
            HEADLINE coverage gap (§5.1). Do NOT invent coverage that isn't there."

# MUST READ — the gap-report FORMAT template (mirror its structure for the new file)
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md
  why: "The format template. Structure: title (# Gap Report — P1.Mx.Tx.Sx: <area> vs PRD §X) + Date + Scope +
        Audited artifacts (read-only) + Bottom line (✅) + §1 Method (commands run + observed output) + §2
        per-point compliance TABLE (contract req | expected | actual | file:line | pinning test | ✅) + §3 the
        live probe + §4 Test results (the live count) + §5 Non-defect nuances + §6 Conclusion (PASS; ties to
        acceptance). Mirror it EXACTLY. gap_launch_daemon.md is a NEW file (CREATE, not append)."
  critical: "Mirror the structure. Cite voice_typing/launch_daemon.sh:line + a tests/test_systemd_unit.py test
             per contract point. gap_systemd.md (P1.M4.T1S1) + gap_cuda_check.md (P1.M1.T4.S1) are the closest
             siblings (same single-file CREATE pattern; gap_cuda_check.md even cross-references THIS wrapper
             as cuDNN's remediation)."

# CONTEXT — the PRD contract being audited against (READ-ONLY)
- docfile: PRD.md
  why: "§4.4 cuDNN/cuBLAS note — the authoritative contract: 'ship nvidia-cublas-cu12 and nvidia-cudnn-cu12 as
        deps and ... prepend their lib dirs to the process's dynamic loader path ... must happen via os.execv
        re-exec or in a launcher wrapper, because LD_LIBRARY_PATH is read at process start. Realized approach:
        voice_typing/launch_daemon.sh recomputes the cuBLAS/cuDNN lib dirs from the LIVE installed nvidia-*-cu12
        wheels on every launch ... so no baked Environment=LD_LIBRARY_PATH= is used in the unit (it would go
        stale on uv sync).' §8 risk row #1 (the cuDNN libcudnn_ops failure -> LD_LIBRARY_PATH wrapper). §1
        '100% local' + §7.8 acceptance #8 (no network -> HF_HUB_OFFLINE=1). §4.9 ExecStart=__REPO__/voice_typing/
        launch_daemon.sh + ExecStartPre import-environment. This is the spec each contract point is verified against."
  critical: "Do NOT edit PRD.md (forbidden). The report cites §4.4 + §8 + §1/§7.8 + §4.9 as the contract."

# CONTEXT — the sibling audit PRP (the CREATE-new-gap-file precedent + the parallel contract)
- docfile: plan/006_862ee9d6ef41/P1M4T1S1/PRP.md
  why: "The systemd-unit audit (P1.M4.T1S1) is the EXACT sibling: same single-file-CREATE pattern, same
        read-only-audit discipline, same gap-report structure, same 'headline coverage-gap nuance' framing
        (its KillMode=mixed == this task's lib-discovery gap). It defines gap_systemd.md; this task defines
        gap_launch_daemon.md — DISJOINT files (systemd/voice-typing.service vs voice_typing/launch_daemon.sh),
        no merge conflict. The 2 launch_daemon cross-file tests are cited by BOTH (corroborating for the
        unit's ExecStart; primary for this audit). Treat it as a contract (it is being implemented in parallel)."
  critical: "gap_launch_daemon.md is INDEPENDENT of gap_systemd.md (different files, different audit areas).
             CREATE the file fresh. Do NOT duplicate the systemd findings. The ExecStart=__REPO__/voice_typing/
             launch_daemon.sh wiring is gap_systemd.md's; the wrapper's INTERNALS are THIS task's."

# CONTEXT — the cuda_check audit this report cross-references (the wrapper is cuDNN's remediation)
- docfile: plan/006_862ee9d6ef41/architecture/gap_cuda_check.md
  why: "§6-obs1 (P1.M1.T4.S1) records the cuDNN limitation: cuda_check probes the CUDA DRIVER only
        (get_cuda_device_count) — it does NOT load cuDNN, so a missing libcudnn_ops.so.9 still yields
        VERDICT=cuda-ok and surfaces later at WhisperModel construction. It explicitly cross-references
        'launch_daemon.sh LD_LIBRARY_PATH wrapper (P1.M4.T2) is what makes cuDNN findable.' THIS audit is
        that remediation's compliance check. Cross-reference gap_cuda_check.md §6-obs1; do NOT re-audit
        cuda_check."
  critical: "Do NOT re-audit cuda_check's probe/fallback (P1.M1.T4.S1 owns gap_cuda_check.md). Cite the wrapper
             as cuDNN's remediation + cross-reference §6-obs1."
```

### Current Codebase tree (state at P1.M4.T2.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── launch_daemon.sh          # AUDIT TARGET (read-only — the 5 contract points + robustness extras, 103 lines)
├── systemd/voice-typing.service  # CROSS-FILE (ExecStart points here; audited by P1.M4.T1.S1 — NOT this task)
├── install.sh                    # CROSS-FILE (audited by P1.M4.T3.S1 — NOT this task)
├── hypr-binds.conf               # CROSS-FILE (audited by P1.M4.T4.S1 — NOT this task)
├── voice_typing/cuda_check.py    # CROSS-FILE (the cuDNN limitation; audited by P1.M1.T4.S1 — NOT this task)
└── tests/
    └── test_systemd_unit.py      # AUDIT (cite the pinning test per contract point; the contract's run command) — 440 lines, 15 tests
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_typing.md             # FORMAT TEMPLATE (mirror its structure)
    ├── gap_systemd.md            # SIBLING REFERENCE (P1.M4.T1S1 — same single-file CREATE pattern; being created in parallel)
    ├── gap_cuda_check.md         # CROSS-REFERENCE (§6-obs1 cuDNN limitation; the wrapper is its remediation)
    └── gap_launch_daemon.md      # <-- CREATE (NEW file; no prior launch_daemon gap report exists)
# NO source/test/doc files modified. The only artifact change is creating gap_launch_daemon.md.
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md   # CREATE (NEW): the P1.M4.T2.S1 launch_daemon.sh audit
                                                          #   (5-contract-point + no-baked-path compliance table + live lib-probe
                                                          #    + live pytest count + 4 nuances [lib-discovery coverage-gap headline /
                                                          #    read-at-exec / WAYLAND belt-and-suspenders / CPU-fallback else]
                                                          #    + conclusion tied to acceptance #8).
# NOTHING ELSE. No code/test/doc changes. Read-only audit.
```

### Known Gotchas of our codebase & Library Quirks

```sh
# CRITICAL #1 — THIS IS A READ-ONLY AUDIT; DO NOT EDIT voice_typing/launch_daemon.sh /
#   tests/test_systemd_unit.py / systemd/voice-typing.service / install.sh / cuda_check.py / PRD.md /
#   any source. The wrapper is COMPLIANT (this PRP's research verified all 5 contract points + 15/15 tests +
#   the live lib probe). The ONLY artifact change is CREATING gap_launch_daemon.md. If a contract point
#   fails on re-read, document it as a real gap for a SEPARATE remediation task — do NOT fix the wrapper here
#   (consistent with every round-006 audit). (Research §0/§5.)

# CRITICAL #2 — RE-VERIFY THE LINE NUMBERS LIVE. This PRP cites the wrapper's elements at :30/:34-36/:48-52/
#   :50-51/:53/:54-58/:71/:72/:93-95/:103 + the test functions at :71/:115/:164. These were correct at
#   research time but the file may have shifted — re-grep
#   (`grep -nE 'CUDA_LIBS=|export LD_LIBRARY_PATH|export HF_HUB_OFFLINE|export TRANSFORMERS_OFFLINE|show-environment|exec "\$PY"' voice_typing/launch_daemon.sh`)
#   and record the ACTUAL line numbers in the report. Do NOT copy the PRP's numbers blind.

# CRITICAL #3 — THE LIB-DISCOVERY + LD_LIBRARY_PATH COVERAGE GAP IS THE HEADLINE NUANCE (§5.1), NOT a defect.
#   The wrapper's NAMESAKE function (the dynamic cuBLAS/cuDNN discovery + LD_LIBRARY_PATH prepend — PRD §4.4)
#   has NO test: the 2 cross-file tests pin ONLY the offline vars (:115) + the WAYLAND fetch (:164) + the exec
#   target. NEITHER references nvidia.cublas.lib / CUDA_LIBS / LD_LIBRARY_PATH. The code IS correct (read §1 +
#   live probe §3); record the gap as a coverage observation (§5.1), NOT a code gap. Do NOT add a test here
#   (read-only audit). (Research §4.1.)

# CRITICAL #4 — RECORD THE LIVE PYTEST COUNT; DO NOT HARD-CODE IT. The contract's run command is
#   `.venv/bin/python -m pytest tests/test_systemd_unit.py -q` (FULL PATH — zsh aliases python/pytest). Run it
#   (under `timeout 60` per AGENTS.md Rule 1) + paste the actual "N passed in Xs" line into §4. This research:
#   15 passed in 0.01s. (Critical #4 in the sibling gap_systemd.md PRP; same discipline.)

# CRITICAL #5 — RUN THE LIVE LIB-DISCOVERY PROBE (§3), NOT JUST THE TESTS. The probe (`timeout 60 .venv/bin/
#   python -c '...'` — the EXACT python -c the wrapper runs) is the RUNTIME proof contract points a+b work,
#   which NO test exercises. It imports ONLY nvidia.cublas.lib / nvidia.cudnn.lib (cheap namespace packages;
#   ~0.1s — NOT ctranslate2/torch, no model load) + globs for libcudnn_ops/libcublas. Paste the resolved dirs
#   + the presence booleans into §3. (Research §3.)

# CRITICAL #6 — CHARACTERIZE TEST COVERAGE ACCURATELY. The 2 cross-file tests pin: HF_HUB_OFFLINE=1 +
#   TRANSFORMERS_OFFLINE=1 present + BEFORE exec (:115); systemctl --user show-environment + WAYLAND_DISPLAY
#   present + BEFORE exec (:164); ExecStart -> wrapper (:71, unit-side). They do NOT pin: the dynamic
#   discovery (a), the LD_LIBRARY_PATH prepend (b), the no-baked-path check, set -euo pipefail, the CWD
#   resolution, the _d() namespace fallback, the CPU-fallback else. Cite the untested ones as coverage
#   observations (§2/§5.1), do NOT invent pinning tests. Do NOT add a test here (read-only audit).

# CRITICAL #7 — SCOPE IS launch_daemon.sh ONLY. Do NOT audit the systemd unit directives (P1.M4.T1S1),
#   install.sh (P1.M4.T3.S1), hypr-binds.conf (P1.M4.T4.S1), cuda_check's probe (P1.M1.T4.S1 ->
#   gap_cuda_check.md §6-obs1, which this wrapper REMEDIATES — cross-reference, do NOT re-audit), or the
#   daemon teardown (P1.M2.T2.S3). The cross-file tests CORROBORATE the ExecStart wiring end-to-end — cite
#   them as evidence, do NOT re-audit those files.

# GOTCHA #8 — NEVER EXEC launch_daemon.sh (AGENTS.md Rule 2). It ends in `exec "$PY" -m voice_typing.daemon`
#   which BLOCKS FOREVER (the daemon run loop). The audit READS the file + runs the pure-stdlib test suite +
#   one python -c lib-discovery probe (NO daemon, NO mic, NO model load). Do NOT run `bash launch_daemon.sh`
#   or `voice-typing-daemon` to "test" it.

# GOTCHA #9 — RUN VIA .venv/bin/python (zsh aliases python -> uv run). Always `.venv/bin/python -m pytest ...`
#   / `.venv/bin/python -c '...'`. mypy NOT installed (skip). ruff at /home/dustin/.local/bin/ruff is
#   OPTIONAL (not a gate; the wrapper is bash — ruff/mypy do not apply to it; shellcheck if present is a
#   nice-to-have, not a gate). (Research §7.)

# GOTCHA #10 — TWO TIMEOUTS PER AGENTS.md RULE 1. The test is sub-second + pure-stdlib, and the lib probe
#   imports only cheap namespace packages (~0.1s) — but STILL wrap: `timeout 60 .venv/bin/python -m pytest
#   tests/test_systemd_unit.py -q` + `timeout 60 .venv/bin/python -c '...'` (inner GNU timeout) + set the
#   bash-tool `timeout` param above each (outer harness backstop). This research did exactly that.

# GOTCHA #11 — THE ONLY LD_LIBRARY_PATH ASSIGNMENT IS THE DYNAMIC $CUDA_LIBS (:53). Confirm by grep:
#   `grep -nE '^[^#]*LD_LIBRARY_PATH' voice_typing/launch_daemon.sh` -> the single :53 export; all other
#   LD_LIBRARY_PATH mentions are comments (the triage hints). The only /home/ or site-packages literal is a
#   COMMENT (:22, the ldd hint), never an assignment -> no baked/stale path. (Research §0 point 6.)
```

## Implementation Blueprint

### Data models and structure

No production data model. The deliverable is a Markdown gap-report file mirroring `gap_typing.md`'s
structure. No code changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — re-verify the contract + locate the live line numbers (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/launch_daemon.sh && test -f tests/test_systemd_unit.py && echo "ok: files present" || echo "PREFLIGHT FAIL"
      # the 5 contract points (line-numbered):
      grep -nE 'CUDA_LIBS=|nvidia\.cublas\.lib|nvidia\.cudnn\.lib|__path__' voice_typing/launch_daemon.sh   # (a) dynamic discovery
      grep -nE 'export LD_LIBRARY_PATH' voice_typing/launch_daemon.sh                                        # (b) LD_LIBRARY_PATH prepend
      grep -nE 'export HF_HUB_OFFLINE=1|export TRANSFORMERS_OFFLINE=1' voice_typing/launch_daemon.sh         # (c) offline vars
      grep -nE 'for _v in WAYLAND_DISPLAY DISPLAY|show-environment' voice_typing/launch_daemon.sh            # (d) WAYLAND fetch
      grep -nE 'exec "\$PY" -m voice_typing\.daemon' voice_typing/launch_daemon.sh                           # (e) exec
      # the no-baked-path check — the ONLY LD_LIBRARY_PATH assignment must be the dynamic $CUDA_LIBS:
      grep -nE '^[^#]*LD_LIBRARY_PATH' voice_typing/launch_daemon.sh                                         # expect: :53 export only
      grep -nE '/home/|site-packages' voice_typing/launch_daemon.sh | grep -v '^[0-9]*:#' || echo "ok: no non-comment /home or site-packages literal (no baked path)"
      # the 2 launch_daemon cross-file test functions (coverage to cite):
      grep -nE '^def test_(execstart_points_at_launch_daemon_wrapper|launch_daemon_exports_offline_vars|launch_daemon_fetches_wayland_display_from_manager)' tests/test_systemd_unit.py
      # confirm the lib-discovery has NO test (the headline coverage gap §5.1):
      grep -qE 'def test_.*(cuda_lib|cublas|cudnn|LD_LIBRARY|CUDA_LIBS)' tests/test_systemd_unit.py && echo "note: a lib-discovery test EXISTS (update §5.1)" || echo "ok: no lib-discovery/LD_LIBRARY_PATH test (coverage gap §5.1 confirmed)"
  - EXPECTED: both files present; the discovery grep hits :48-52 (+ the _d() fallback :50-51); the
    LD_LIBRARY_PATH export hits :53 ONLY (no other assignment); offline vars :71/:72; WAYLAND fetch :93-95;
    exec :103; the no-baked-path check confirms :53 is the sole non-comment LD_LIBRARY_PATH assignment +
    no non-comment /home/site-packages literal; the 3 test functions located; the no-lib-discovery-test
    grep confirms the §5.1 coverage gap. RECORD the actual line numbers.
  - DO NOT: edit anything yet, exec launch_daemon.sh, or touch any source/test/doc file.

Task 2: RUN the live lib-discovery probe + the suite (record §3 + §4) — TWO TIMEOUTS per AGENTS.md Rule 1
  - RUN: timeout 60 .venv/bin/python -c '
            import os, nvidia.cublas.lib as a, nvidia.cudnn.lib as b
            def _d(m):
                f=getattr(m,"__file__",None)
                return os.path.dirname(f) if f else next(iter(m.__path__))
            import glob
            print("cublas:", _d(a)); print("cudnn :", _d(b))
            print("libcudnn_ops present:", bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
            print("libcublas present:", bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))'
    (this is the EXACT python -c the wrapper runs — the runtime proof contract points a+b work)
  - RUN: timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
    (and set the bash-tool `timeout` param to 90 — above the inner 60s backstop)
  - EXPECTED: probe resolves BOTH dirs (e.g. .venv/lib/python3.12/site-packages/nvidia/cublas/lib +
    .../nvidia/cudnn/lib) + libcudnn_ops present: True + libcublas present: True (RECORD the actual paths);
    suite all pass (~0.01s). RECORD the exact "N passed in Xs" line. This research: "15 passed in 0.01s"
    + the dirs above. If the probe can't import the wheels (no-GPU host) OR a test FAILS: READ it — if it
    is a REAL wrapper defect, document it as a gap in §5 (do NOT fix the wrapper here); if it is an
    environment issue (no nvidia wheels installed), note it + the wrapper's CPU-fallback else (§5.4) still
    applies. (Research §3; Critical #5; Gotcha #10.)

Task 3: CREATE plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md — write the report body from
        "Task 3 SOURCE" below, REPLACING the <...> placeholders with the LIVE line numbers from Task 1,
        the LIVE probe output from Task 2 (§3), and the LIVE pass count from Task 2 (§4). Mirror
        gap_typing.md's structure exactly.
  - FILE: plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md (NEW — CREATE, do not append).
  - DO NOT: edit voice_typing/launch_daemon.sh/test_systemd_unit.py/systemd/voice-typing.service/install.sh/
    cuda_check.py/PRD.md (Critical #1); hard-code the pass count or probe paths (Critical #4/#5); flag the
    lib-discovery coverage gap as a code defect (Critical #3); invent pinning tests for untested points
    (Critical #6); audit the systemd unit/install.sh/hypr-binds/cuda_check/daemon-teardown (Critical #7).

Task 4: VALIDATE — L1 (file exists + markdown sanity) + L2 (the pytest count is in §4 + probe in §3) + L3
        (scope guard: ONLY gap_launch_daemon.md created; no source modified) + L4 (evidence spot-check).
        No git commit unless the orchestrator directs it. If asked: message
        "P1.M4.T2.S1: launch_daemon.sh audit (compliant; gap_launch_daemon.md created; no code changes)".
```

#### Task 3 SOURCE — `gap_launch_daemon.md` (write this body; replace `<...>` with LIVE values from Task 1/2)

````markdown
# Gap Report — P1.M4.T2.S1: launch_daemon.sh LD_LIBRARY_PATH wrapper & cuDNN discovery vs PRD §4.4

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/launch_daemon.sh` — the systemd ExecStart LD_LIBRARY_PATH wrapper (PRD §4.4
"Realized approach" + §4.9 `ExecStart=__REPO__/voice_typing/launch_daemon.sh` + §8 risk row #1) — against
ALL work-item contract points: (a) **dynamically discovers** `nvidia.cublas.lib` + `nvidia.cudnn.lib` lib
dirs (not baked); (b) **prepends** them to `LD_LIBRARY_PATH`; (c) **exports `HF_HUB_OFFLINE=1`** (acceptance
#8 no-network); (d) **re-fetches `WAYLAND_DISPLAY`/`DISPLAY`** from `systemctl --user show-environment`;
(e) **execs** `python -m voice_typing.daemon`; + **NO baked/stale `LD_LIBRARY_PATH`** — re-verified live
via grep + a live lib-discovery probe (the exact `python -c` the wrapper runs) + the pure-Python
`tests/test_systemd_unit.py` re-run. Subtask **P1.M4.T2.S1** of verification round `006_862ee9d6ef41`.
Satisfies **Acceptance #8** ("no network at runtime — `HF_HUB_OFFLINE=1` is the mechanism the wrapper exports").
**Audited artifacts (all read-only):**
- `voice_typing/launch_daemon.sh` — the 103-line bash wrapper. `set -euo pipefail` (`:<L30>`); CWD-independent
  resolution `SCRIPT_DIR`/`VENV_DIR`/`PY` (`:<L34>`-`:<L36>`); the dynamic discovery
  `CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b ...')"` (`:<L48>`-`<L52>`)
  with the `_d()` namespace-package fallback (`__file__ is None → __path__[0]`, `:<L50>`-`<L51>`);
  `export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"` (`:<L53>`); the CPU-fallback
  `else` (WARNING + exec without override, `:<L54>`-`<L58>`); `export HF_HUB_OFFLINE=1` (`:<L71>`) +
  `export TRANSFORMERS_OFFLINE=1` (`:<L72>`); the `for _v in WAYLAND_DISPLAY DISPLAY; do ... systemctl --user
  show-environment -p "$_v" --value ...` loop (`:<L93>`-`<L95>`); `exec "$PY" -m voice_typing.daemon "$@"`
  (`:<L103>`). The header comment (`:1`-`28`) documents the WHY (`ld.so` reads `LD_LIBRARY_PATH` at exec;
  the cuDNN `libcudnn_ops` split-sublib triage).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib
  (parses the unit + wrapper/install/binds files; NO live systemd/GPU/CUDA/daemon/mic).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.4 (the cuDNN/cuBLAS "launcher wrapper" contract +
  "no baked `Environment=LD_LIBRARY_PATH=`") + §8 risk row #1 (the cuDNN load failure) + §1/§7.8 (100% local /
  acceptance #8) + §4.9 (`ExecStart=__REPO__/voice_typing/launch_daemon.sh`).

**Bottom line:** ✅ `voice_typing/launch_daemon.sh` is **COMPLIANT** with PRD §4.4 + the work-item contract
— all 5 contract points present + correct, NO baked/stale `LD_LIBRARY_PATH` (the only assignment is the
dynamic `$CUDA_LIBS`), the live lib-discovery probe resolves BOTH lib dirs + confirms `libcudnn_ops`/
`libcublas` are present inside them, and the suite is green (**<N> passed in <X>s**, re-run live).
**No source files were modified** — the wrapper faithfully implements the spec. The audit's value-add = the
**headline nuance (§5.1)**: the wrapper's *NAMESAKE* feature (the dynamic cuBLAS/cuDNN discovery +
`LD_LIBRARY_PATH` prepend — PRD §4.4) has **NO test coverage** (the 2 cross-file tests pin only the later
offline-vars + WAYLAND-fetch additions) — so this audit IS the PRD-§4.4 compliance check the suite cannot
perform, recording the gap so a regression (a reverted `import nvidia.cublas.lib`, a stale baked path) cannot
ship silently. Acceptance #8 (no network at runtime) is met: `HF_HUB_OFFLINE=1` (`:<L71>`) is exported
BEFORE `exec` (pinned by `test_launch_daemon_exports_offline_vars`).

---

## 1. Method

Each of the 5 work-item contract points + the no-baked-path check was mapped 1:1 to its
`voice_typing/launch_daemon.sh` implementation by `grep -nE` (the file:line evidence), the header comment
explaining the non-obvious parts (`ld.so` reads `LD_LIBRARY_PATH` at exec; the namespace-package `_d()`
fallback) was read directly, and the dynamic discovery was verified **empirically** — the exact `python -c`
the wrapper runs (`launch_daemon.sh:<L48>-<L52>`) was re-executed live to resolve both lib dirs + confirm the
`libcudnn_ops`/`libcublas` shared objects exist inside them (§3). The full `tests/test_systemd_unit.py` suite
was then **re-run live** to record the actual pass count + timing. Nothing was assumed from the PRP's
embedded numbers — every line number + the pass count + the probe output below was re-verified this round
(the suite is pure-stdlib `re`/`pathlib`; the probe imports only the cheap `nvidia.cublas.lib`/`nvidia.cudnn.lib`
namespace packages — no GPU/CUDA/daemon/mic/model-load required).

### Commands run (re-verification)

```bash
# (a)-(e): launch_daemon.sh — the 5 contract points (line-numbered)
grep -nE 'CUDA_LIBS=|nvidia\.cublas\.lib|nvidia\.cudnn\.lib|__path__' voice_typing/launch_daemon.sh          # (a) dynamic discovery + _d() fallback
grep -nE 'export LD_LIBRARY_PATH' voice_typing/launch_daemon.sh                                                # (b) LD_LIBRARY_PATH prepend
grep -nE 'export HF_HUB_OFFLINE=1|export TRANSFORMERS_OFFLINE=1' voice_typing/launch_daemon.sh                 # (c) offline vars
grep -nE 'for _v in WAYLAND_DISPLAY DISPLAY|show-environment' voice_typing/launch_daemon.sh                    # (d) WAYLAND fetch
grep -nE 'exec "\$PY" -m voice_typing\.daemon' voice_typing/launch_daemon.sh                                   # (e) exec
# the no-baked-path check — the ONLY LD_LIBRARY_PATH assignment must be the dynamic $CUDA_LIBS:
grep -nE '^[^#]*LD_LIBRARY_PATH' voice_typing/launch_daemon.sh                                                 # expect: the :<L53> export ONLY
grep -nE '/home/|site-packages' voice_typing/launch_daemon.sh | grep -v '^[0-9]*:#' || echo "ok: no non-comment /home or site-packages literal"
# the launch_daemon cross-file test functions (coverage to cite):
grep -nE '^def test_(execstart_points_at_launch_daemon_wrapper|launch_daemon_exports_offline_vars|launch_daemon_fetches_wayland_display_from_manager)' tests/test_systemd_unit.py
# confirm the lib-discovery has NO test (the headline coverage gap §5.1):
grep -qE 'def test_.*(cuda_lib|cublas|cudnn|LD_LIBRARY|CUDA_LIBS)' tests/test_systemd_unit.py && echo "a test exists (update §5.1)" || echo "no lib-discovery/LD_LIBRARY_PATH test (coverage gap §5.1)"
# the LIVE lib-discovery probe (the exact python -c the wrapper runs) + the contract's run command (two timeouts per AGENTS.md Rule 1)
timeout 60 .venv/bin/python -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None); return os.path.dirname(f) if f else next(iter(m.__path__))
import glob
print("cublas:",_d(a)); print("cudnn :",_d(b))
print("libcudnn_ops present:",bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
print("libcublas present:",bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))'
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
```

### Observed output (abridged — replace with the LIVE re-verification)

```
set -euo pipefail                                                                     :<L30>
CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b ...')   :<L48>-<L52>
    return os.path.dirname(f) if f else next(iter(m.__path__))   # _d() ns-pkg fallback :<L50>-<L51>
export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"              :<L53>   (ONLY assignment)
export HF_HUB_OFFLINE=1                                                               :<L71>
export TRANSFORMERS_OFFLINE=1                                                         :<L72>
for _v in WAYLAND_DISPLAY DISPLAY; do ... systemctl --user show-environment ...       :<L93>-<L95>
exec "$PY" -m voice_typing.daemon "$@"                                                :<L103>
(no non-comment /home or site-packages literal — no baked path)
(no lib-discovery/LD_LIBRARY_PATH test — coverage gap §5.1)
cublas: <…/site-packages/nvidia/cublas/lib>
cudnn : <…/site-packages/nvidia/cudnn/lib>
libcudnn_ops present: True
libcublas present: True
<N> passed in <X>s
```

---

## 2. Per-contract-point Compliance Table (work-item contract / PRD §4.4 vs `voice_typing/launch_daemon.sh`)

| # | contract requirement | expected | actual (file:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| (a) | **discover** `nvidia.cublas.lib` + `nvidia.cudnn.lib` paths **dynamically** (not baked) | a `python -c` import computing the dirs from the LIVE wheels (survives `uv sync`) | `CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b …')"` (`:<L48>`-`<L52>`) + the `_d()` namespace-package fallback (`:<L50>`-`<L51>`) | (none — **coverage gap §5.1**, the HEADLINE nuance) | ✅ |
| (b) | **prepend** those dirs to `LD_LIBRARY_PATH` | `export LD_LIBRARY_PATH="<dirs>${existing:+:$existing}"` | `export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"` (`:<L53>`) — prepends `$CUDA_LIBS`, preserves any existing path (the `:+` idiom avoids a spurious trailing `:`) | (none — **coverage gap §5.1**) | ✅ |
| (c) | **export `HF_HUB_OFFLINE=1`** (acceptance #8) | `export HF_HUB_OFFLINE=1` BEFORE exec | `export HF_HUB_OFFLINE=1` (`:<L71>`) + `export TRANSFORMERS_OFFLINE=1` (`:<L72>`, belt-and-suspenders) | `test_launch_daemon_exports_offline_vars` (`:<L115>`) — asserts BOTH present (`^export`-anchored) + BEFORE `exec` | ✅ |
| (d) | **re-fetch** `WAYLAND_DISPLAY`/`DISPLAY` from `systemctl --user show-environment` | a fetch loop reading the user-manager env | `for _v in WAYLAND_DISPLAY DISPLAY; do … _val="$(systemctl --user show-environment -p "$_v" --value …)" …` (`:<L93>`-`<L95>`) — idempotent (`${!_v:-}`) + non-fatal (`|| true`) | `test_launch_daemon_fetches_wayland_display_from_manager` (`:<L164>`) — asserts the fetch + `WAYLAND_DISPLAY` + BEFORE `exec` | ✅ |
| (e) | **exec** `python -m voice_typing.daemon` | `exec "$PY" -m voice_typing.daemon "$@"` | `exec "$PY" -m voice_typing.daemon "$@"` (`:<L103>`) | `test_execstart_points_at_launch_daemon_wrapper` (`:<L71>`, unit-side) + the exec-line assertion in BOTH `:<L115>` + `:<L164>` | ✅ |
| (f) | **NO baked/stale `LD_LIBRARY_PATH`** | the only `LD_LIBRARY_PATH` assignment is the dynamic `$CUDA_LIBS`; no literal lib path | CONFIRMED: `grep -nE '^[^#]*LD_LIBRARY_PATH'` → the `:<L53>` export ONLY; the only `/home/`/`site-packages` literal is a COMMENT (`:<L22>`, the `ldd` triage hint), never an assignment | (none — coverage gap §5.1, but provable by grep) | ✅ |

> All contract points **PASS**. The file:line numbers above are `grep -n`-verified against the live tree this round.
> The two untested points (a)+(b)+(f) are confirmed correct by direct read + the live lib probe (§3); the
> gap is recorded as a non-blocking coverage observation in §5.1.

### Robustness extras (compliant, beyond the 5 contract points — recorded so they are not "simplified" away)

| extra | actual (file:line) | why it matters | tested? |
|---|---|---|---|
| `set -euo pipefail` | `:<L30>` | fail-fast on any error / unset var / broken pipe (the AGENTS.md PATH-shim anti-pattern this prevents) | no |
| CWD-independent path resolution (`SCRIPT_DIR`/`VENV_DIR`/`PY`) | `:<L34>`-`<L36>` | works whether systemd calls the absolute ExecStart or a user runs `./launch_daemon.sh` from any cwd | no |
| the `_d()` namespace-package fallback (`__file__ is None → __path__[0]`) | `:<L50>`-`<L51>` | WITHOUT it the faster-whisper README one-liner `os.path.dirname(nvidia.cublas.lib.__file__)` would CRASH (`TypeError`: `__file__` is `None` for the namespace-package `nvidia/cublas/lib`) → cuDNN would never load | no |
| `${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}` idiom | `:<L53>` | appends `:$existing` only if non-empty (no spurious trailing `:`); `os.pathsep`-correct | no |
| CPU-fallback `else` branch (WARNING + exec without override) | `:<L54>`-`<L58>` | if the nvidia wheels aren't importable (no-GPU host), exec python WITHOUT the override → the daemon falls back to `device=cpu` (PRD §4.4) | no |
| TRANSFORMERS_OFFLINE=1 | `:<L72>` | belt-and-suspenders (faster-whisper has no transformers dep, but harmless + future-proof) | yes (`:<L115>`) |

---

## 3. Live lib-discovery probe (the runtime proof contract points (a)+(b) work — which NO test exercises)

```
$ timeout 60 .venv/bin/python -c '
import os, nvidia.cublas.lib as a, nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None); return os.path.dirname(f) if f else next(iter(m.__path__))
import glob
print("cublas:", _d(a)); print("cudnn :", _d(b))
print("libcudnn_ops present:", bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
print("libcublas present:", bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))'
cublas: <paste the live resolved cublas lib dir>
cudnn : <paste the live resolved cudnn lib dir>
libcudnn_ops present: <True/False>
libcublas present: <True/False>
```

→ The exact `python -c` the wrapper runs (`launch_daemon.sh:<L48>-<L52>`) resolves BOTH lib dirs on the live
machine, AND the `libcudnn_ops*.so` + `libcublas*.so` the daemon's cuDNN/cuBLAS load NEEDS are present inside
them. The dirs the wrapper would compute (printed above) are exactly the two `LD_LIBRARY_PATH` entries it
prepends. **This is the runtime proof contract points (a)+(b) actually work** — which no unit test exercises
(§5.1). (If the probe can't import the wheels on this host — no nvidia packages installed — record that +
note the wrapper's CPU-fallback `else` branch §5.4 still applies; the daemon would then run `device=cpu`.)

---

## 4. Test results (the contract's run command, LIVE)

```
$ timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
.<paste the live summary line, e.g. "15 passed in 0.01s">.
```

The suite (440 lines, 15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
`voice_typing/launch_daemon.sh` + `install.sh` + `hypr-binds.conf` — no GPU/CUDA/daemon/mic. **3 tests pin
this wrapper's behavior**: `test_launch_daemon_exports_offline_vars` (`:<L115>`, contract point (c) +
BEFORE-exec ordering), `test_launch_daemon_fetches_wayland_display_from_manager` (`:<L164>`, contract point
(d) + BEFORE-exec ordering), `test_execstart_points_at_launch_daemon_wrapper` (`:<L71>`, the unit-side
ExecStart→wrapper assertion). **Coverage gap**: NO test pins contract points (a) the dynamic discovery,
(b) the `LD_LIBRARY_PATH` prepend, or (f) the no-baked-path check (§5.1) — the wrapper's PRIMARY function.

---

## 5. Non-defect nuances (so they are not mistaken for gaps)

### 5.1 THE HEADLINE — the cuBLAS/cuDNN discovery + `LD_LIBRARY_PATH` prepend has NO test coverage (coverage gap, NOT a code defect)
The wrapper exists *for* the `LD_LIBRARY_PATH` override (PRD §4.4 + §8 risk row #1 "cuDNN 'cannot load
libcudnn_ops' at runtime"). Yet the two cross-file tests in `test_systemd_unit.py` pin ONLY:
`test_launch_daemon_exports_offline_vars` (`:<L115>`) → `^export HF_HUB_OFFLINE=1` + `^export
TRANSFORMERS_OFFLINE=1` present + BEFORE `exec` (contract point (c)); and
`test_launch_daemon_fetches_wayland_display_from_manager` (`:<L164>`) → `systemctl --user show-environment`
+ `WAYLAND_DISPLAY` present + BEFORE `exec` (contract point (d)). **NEITHER references `nvidia.cublas.lib` /
`nvidia.cudnn.lib` / `CUDA_LIBS` / `LD_LIBRARY_PATH`.** So a regression on the wrapper's PRIMARY function —
a reverted `import nvidia.cublas.lib`, a stale hardcoded lib path, a broken `_d()` namespace fallback, a
dropped `export LD_LIBRARY_PATH=` — would pass the 15-test suite silently. **This is a coverage gap, not a
code defect**: the code is correct (verified by read §2 + live probe §3). This audit (S1) IS the PRD-§4.4
compliance check the suite cannot perform — exactly the role `gap_systemd.md`'s `KillMode=mixed` nuance plays
for the untested unit directives. A future test-hardening pass COULD add a
`test_launch_daemon_discovers_cuda_libs_dynamically` (grep for `import … nvidia.cublas.lib` +
`export LD_LIBRARY_PATH="$CUDA_LIBS` + the absence of a literal lib path) — **out of scope for this
read-only audit** (do NOT add a test here; consistent with every round-006 audit's "read-only, no new tests"
discipline). ✅

### 5.2 `LD_LIBRARY_PATH` + `HF_HUB_OFFLINE` are read at execve/import time — why they MUST live in the wrapper, not `os.environ`
The dynamic linker (`ld.so(8)`) reads `LD_LIBRARY_PATH` ONLY at process start. Mutating `os.environ` inside
`daemon.py` (after python has started) has NO effect on the already-loaded process — so the override CANNOT
live in daemon.py. The wrapper exports it BEFORE `exec "$PY"` (`:<L53>` → `:<L103>`), which is the execve
point. This is why PRD §4.4 prescribes "a launcher wrapper" and forbids baking
`Environment=LD_LIBRARY_PATH=` in the systemd unit (it would go stale on `uv sync`). Same read-at-start
semantics apply to `HF_HUB_OFFLINE=1` (`huggingface_hub` latches it at IMPORT TIME, `constants.py`) — hence
it lives in the wrapper, not daemon.py. Both cross-file tests (`:<L115>` / `:<L164>`) enforce the BEFORE-exec
ordering for this reason. ✅

### 5.3 The WAYLAND `show-environment` fetch is belt-and-suspenders for the cold-boot race
The systemd unit (PRD §4.9, VT-004) is `After=graphical-session.target` + `ExecStartPre=import-environment
WAYLAND_DISPLAY DISPLAY`. But the wrapper's `show-environment` fetch (`:<L93>`-`<L95>`) is the *real*
workaround regardless of boot order: the wrapper is exec'd at daemon start, by which point the compositor
has invariably imported the vars. It is also robust to a manual launch from a stripped environment. Each var
is only set if unset (`${!_v:-}`, `:<L97>`), so an explicit override wins; a missing var is non-fatal
(`|| true`, `:<L95>`). Pinned (`:<L164>`) — this is the validation-Issue-1 wtype-on-cold-boot fix. ✅

### 5.4 The CPU-fallback `else` branch is the no-GPU escape hatch
If the nvidia wheels aren't importable (no-GPU host / pre-`install.sh`), the `if CUDA_LIBS=…; then …; else
…; fi` (`:<L48>`-`<L58>`) logs a clear WARNING + execs python WITHOUT the override. The daemon then probes
`cuda_check` → `device=cpu, compute_type=int8` (PRD §4.4; the degraded DECISION is cuda_check/daemon's,
P1.M1.T4.S1 → `gap_cuda_check.md` — NOT the wrapper's). This keeps the wrapper from hard-failing on a
CPU-only box. Untested but low-risk (the `else` is a single `echo` warning; the `exec` still runs). ✅

---

## 6. Conclusion

**PASS.** `voice_typing/launch_daemon.sh` is compliant with PRD §4.4 + the work-item contract on all 5
points + the no-baked-path check. It dynamically discovers the cuBLAS/cuDNN lib dirs from the LIVE installed
wheels (`:<L48>`-`<L52>`, with the `_d()` namespace-package fallback `:<L50>`-`<L51>`), prepends them to
`LD_LIBRARY_PATH` (`:<L53>`), exports `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` (`:<L71>`-`<L72>`),
re-fetches `WAYLAND_DISPLAY`/`DISPLAY` from the user manager (`:<L93>`-`<L95>`), and execs the daemon
(`:<L103>`) — with NO baked `LD_LIBRARY_PATH` (the only assignment is the dynamic `$CUDA_LIBS`). The live
lib-discovery probe (§3) resolves both dirs + confirms `libcudnn_ops`/`libcublas` are present; the 15-test
suite pins the offline vars + WAYLAND fetch + ExecStart→wrapper (the BEFORE-exec ordering enforced). The
**headline nuance (§5.1)**: the wrapper's PRIMARY function (the cuBLAS/cuDNN discovery + `LD_LIBRARY_PATH`
prepend) has NO test coverage — this audit IS that compliance check. **No source files were modified**
(read-only audit); the sole artifact is this report.

Acceptance #8 ("no network at runtime") is met: `HF_HUB_OFFLINE=1` (`:<L71>`) is the mechanism. Scope is
`launch_daemon.sh` ONLY — the systemd unit directives are P1.M4.T1.S1 (`gap_systemd.md`), `install.sh` is
P1.M4.T3.S1, `hypr-binds.conf` is P1.M4.T4.S1, cuda_check's probe is P1.M1.T4.S1 (`gap_cuda_check.md` §6-obs1,
which records the cuDNN limitation THIS wrapper remediates), and the daemon teardown is P1.M2.T2.S3
(`gap_lifecycle.md`).
````

> NOTE for the implementer: replace every `<L...>` placeholder with the ACTUAL line number from your Task-1
> greps, paste the LIVE lib-probe output (resolved dirs + presence booleans) into §3, and paste the LIVE
> pytest summary line into §4. The body above is the verified-compliant verdict pre-filled from research —
> re-confirm each file:line + the probe + the pass count live (Critical #2, #4, #5).

### Implementation Patterns & Key Details

```sh
# PATTERN 1 — the audit is READ-ONLY. The ONLY file created is gap_launch_daemon.md. voice_typing/launch_daemon.sh
#   / test_systemd_unit.py / systemd/voice-typing.service / install.sh / cuda_check.py are compliant + untouched.
#   If a contract point fails on re-read, document it as a gap for a SEPARATE remediation task (do NOT fix the
#   wrapper here). (Critical #1.)

# PATTERN 2 — re-verify line numbers live (grep -nE 'CUDA_LIBS=|export LD_LIBRARY_PATH|export HF_HUB_OFFLINE|
#   export TRANSFORMERS_OFFLINE|show-environment|exec "\$PY"' voice_typing/launch_daemon.sh), then paste them
#   into the report's <L...> slots. Do NOT copy the PRP's numbers blindly. (Critical #2.)

# PATTERN 3 — THE LIB-DISCOVERY COVERAGE GAP IS THE HEADLINE NUANCE. The wrapper's namesake feature (the dynamic
#   cuBLAS/cuDNN discovery + LD_LIBRARY_PATH prepend) has NO test. Record as coverage gap §5.1, NOT a code gap.
#   Do NOT add a test here. (Critical #3.)

# PATTERN 4 — RUN THE LIVE LIB PROBE (§3), not just the tests. The probe is the runtime proof contract points
#   a+b work (no test exercises them). It imports only cheap namespace packages (~0.1s; NO ctranslate2/torch/
#   model load). Paste the resolved dirs + presence booleans into §3. (Critical #5.)

# PATTERN 5 — run the suite live (timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q) + paste
#   the actual count into §4. Do NOT hard-code a number. TWO TIMEOUTS (inner GNU + outer bash-tool). (Critical #4.)

# PATTERN 6 — characterize test coverage accurately: the 2 cross-file tests pin offline-vars + WAYLAND-fetch +
#   the exec target + BEFORE-exec ordering; they do NOT pin the dynamic discovery (a), LD_LIBRARY_PATH (b), or
#   the no-baked-path check. Cite the gap as §5.1; do NOT invent pinning tests. (Critical #6.)

# PATTERN 7 — scope = launch_daemon.sh ONLY. The cross-file tests corroborate the ExecStart wiring but the unit
#   directives / install.sh / hypr-binds / cuda_check / daemon-teardown are other tasks' scope. Cite as evidence,
#   do NOT re-audit. (Critical #7.)
```

### Integration Points

```yaml
REPORT FILE:
  - create: "plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md (NEW — mirror gap_typing.md / gap_systemd.md / gap_cuda_check.md structure)"
CONSUMED (read-only — NO edits):
  - voice_typing/launch_daemon.sh: "the 5 contract points + robustness extras (the audit target)"
  - tests/test_systemd_unit.py: "cite the pinning test per contract point; the contract's run command"
DISJOINT FROM SIBLINGS:
  - P1.M4.T1.S1: "systemd unit directives (different file — systemd/voice-typing.service; the 2 cross-file tests corroborate ExecStart→wrapper but this audit owns the wrapper INTERNALS)"
  - P1.M4.T3.S1: "install.sh idempotency/prefetch/service-install (different file)"
  - P1.M4.T4.S1: "hypr-binds.conf keybinds (different file)"
  - P1.M1.T4.S1: "cuda_check probe/fallback (gap_cuda_check.md §6-obs1 records the cuDNN limitation THIS wrapper remediates — cross-reference, do NOT re-audit)"
  - P1.M2.T2.S3: "daemon bounded-teardown mechanism (gap_lifecycle.md) — disjoint"
CONSUMERS:
  - P1.M5.T5: "acceptance cross-check maps Acceptance #8 (no network at runtime) to this report's HF_HUB_OFFLINE=1 evidence"
  - future maintainers: "the reference for any launch_daemon.sh change (a reverted import, a stale baked path, a dropped HF_HUB_OFFLINE/WAYLAND fetch)"
DEPENDENCIES: none new (read-only audit + the existing pytest suite + grep + one python -c lib probe).
```

## Validation Loop

> This is a READ-ONLY AUDIT. The gate is: the report exists with ✅ verdicts + live file:line evidence + the
> live lib-probe output (§3) + the live pytest count (§4) + the headline lib-discovery coverage-gap nuance
> (§5.1), and NO source file is modified. No GPU/CUDA/daemon/mic/model-load (the suite parses files; the probe
> imports only cheap namespace packages).

### Level 1: Report exists + structure sanity

```bash
cd /home/dustin/projects/voice-typing
test -f plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L1 report present" || echo "L1 FAIL: report missing"
# Structure mirrors gap_typing.md / gap_systemd.md:
head -1 plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md | grep -q '^# Gap Report — P1.M4.T2.S1: launch_daemon' && echo "L1 title ok" || echo "L1 FAIL: title"
grep -q '^## 2\. Per-contract-point Compliance Table' plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L1 §2 ok" || echo "L1 FAIL: §2 table"
grep -q '^## 3\. Live lib-discovery probe' plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L1 §3 ok" || echo "L1 FAIL: §3"
grep -q '^## 4\. Test results' plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L1 §4 ok" || echo "L1 FAIL: §4"
grep -q '^## 5\. Non-defect nuances' plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L1 §5 ok" || echo "L1 FAIL: §5"
# No leftover <L...> placeholders (all replaced with live line numbers):
! grep -q '<L[0-9]' plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L1 placeholders resolved" || echo "L1 FAIL: leftover <L...> placeholder"
# Expected: report present; title/§2/§3/§4/§5 headings present; NO <L...> placeholders remain.
```

### Level 2: The contract's run commands (re-run live; probe recorded in §3 + count recorded in §4) — TWO TIMEOUTS

```bash
cd /home/dustin/projects/voice-typing
# The live lib-discovery probe (the exact python -c the wrapper runs):
timeout 60 .venv/bin/python -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None); return os.path.dirname(f) if f else next(iter(m.__path__))
import glob
print("cublas:",_d(a)); print("cudnn :",_d(b))
print("libcudnn_ops present:",bool(glob.glob(os.path.join(_d(b),"libcudnn_ops*.so*"))))
print("libcublas present:",bool(glob.glob(os.path.join(_d(a),"libcublas*.so*"))))' | tee /tmp/launch_probe.log
# Confirm the report's §3 pasted THIS probe's resolved dirs + presence:
grep -q "libcudnn_ops present: True" plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L2 probe recorded" || echo "L2 FAIL: probe output not in §3"
# The suite:
timeout 60 .venv/bin/python -m pytest tests/test_systemd_unit.py -q | tee /tmp/launch_audit_run.log
echo "exit: ${PIPESTATUS[0]}"
COUNT=$(grep -oE '[0-9]+ passed' /tmp/launch_audit_run.log | head -1)
grep -q "$COUNT passed" plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md && echo "L2 count recorded" || echo "L2 FAIL: live count not in §4"
# (one-shot tees of <2KB summaries; remove after the check)
rm -f /tmp/launch_probe.log /tmp/launch_audit_run.log
# Expected: probe prints both dirs + both "present: True"; pytest exit 0 + "N passed in Xs"; report §3 + §4 hold the LIVE values.
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected: ONLY "?? plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md" (new untracked file). Any change to
#   voice_typing/launch_daemon.sh, tests/test_systemd_unit.py, systemd/voice-typing.service, install.sh,
#   cuda_check.py, PRD.md, tasks.json, prd_snapshot.md, .gitignore, or any source is a SCOPE VIOLATION.
git diff --name-only   # Expected: empty (the report is a NEW untracked file, not a modification)
! git status --porcelain | grep -qE 'voice_typing/launch_daemon|tests/|systemd/|install\.sh|cuda_check|PRD\.md|tasks.json|prd_snapshot.md' && echo "L3 ok: no source/test/doc modified" || echo "L3 FAIL: source/test/doc modified"
# Confirm the report is disjoint from its siblings (different filenames, no overlap):
for f in gap_launch_daemon gap_systemd gap_typing gap_cuda_check gap_lifecycle; do test -f plan/006_862ee9d6ef41/architecture/$f.md && echo "L3 ok: $f.md coexists (disjoint)" || echo "L3 note: $f.md not present"; done
```

### Level 4: Evidence spot-check (the contract points cited are real, not hand-waved)

```bash
cd /home/dustin/projects/voice-typing
# Each contract point cited in the report must actually exist + match the claimed value (re-verify the line numbers):
grep -nE 'CUDA_LIBS="\("\$PY" -c' voice_typing/launch_daemon.sh                          # (a) dynamic discovery
grep -nE 'nvidia\.cublas\.lib as a' voice_typing/launch_daemon.sh                        # (a) the import
grep -nE 'next\(iter\(m\.__path__\)\)' voice_typing/launch_daemon.sh                     # (a) the _d() namespace fallback
grep -nE 'export LD_LIBRARY_PATH="\$CUDA_LIBS' voice_typing/launch_daemon.sh             # (b) the prepend
grep -nE 'export HF_HUB_OFFLINE=1' voice_typing/launch_daemon.sh                         # (c) offline guarantee
grep -nE 'export TRANSFORMERS_OFFLINE=1' voice_typing/launch_daemon.sh                  # (c) belt-and-suspenders
grep -nE 'systemctl --user show-environment' voice_typing/launch_daemon.sh              # (d) the WAYLAND fetch
grep -nE 'for _v in WAYLAND_DISPLAY DISPLAY' voice_typing/launch_daemon.sh              # (d) the var list
grep -nE 'exec "\$PY" -m voice_typing\.daemon' voice_typing/launch_daemon.sh             # (e) exec
# (f) no-baked-path: the ONLY non-comment LD_LIBRARY_PATH assignment is the dynamic $CUDA_LIBS:
test "$(grep -cE '^[^#]*LD_LIBRARY_PATH=' voice_typing/launch_daemon.sh)" -eq 1 && echo "L4 ok: exactly 1 LD_LIBRARY_PATH assignment (the dynamic export)" || echo "L4 FAIL: baked/extra LD_LIBRARY_PATH assignment"
# Confirm the lib-discovery really has no test (the §5.1 framing):
grep -qE 'def test_.*(cuda_lib|cublas|cudnn|LD_LIBRARY|CUDA_LIBS)' tests/test_systemd_unit.py && echo "L4 UNEXPECTED: a lib-discovery test now EXISTS (update §5.1)" || echo "L4 ok: no lib-discovery/LD_LIBRARY_PATH test (coverage gap §5.1)"
# Expected: each grep hits; the no-baked-path test == 1 (the dynamic export only); the no-test check confirms §5.1.
```

## Final Validation Checklist

### Technical Validation
- [ ] `plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md` exists with the correct title + §1-§6 structure mirroring `gap_typing.md`.
- [ ] No leftover `<L...>` placeholders (all replaced with live `grep -n` line numbers).
- [ ] §3 holds the LIVE lib-probe output (resolved cublas/cudnn dirs + `libcudnn_ops`/`libcublas` present).
- [ ] §4 holds the LIVE pytest summary line (not hard-coded).
- [ ] `git status --short` shows ONLY `?? plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md` — no source modified.

### Feature Validation
- [ ] All 5 contract points (a-e) + the no-baked-path check (f) recorded with ✅ + file:line + pinning test (or coverage gap §5.x).
- [ ] The headline nuance (§5.1: lib-discovery + LD_LIBRARY_PATH coverage gap) documented.
- [ ] The other nuances (§5.2 read-at-exec; §5.3 WAYLAND belt-and-suspenders; §5.4 CPU-fallback else) documented.
- [ ] The report ties the verdict to Acceptance #8 (no network at runtime — `HF_HUB_OFFLINE=1`).
- [ ] L4 evidence spot-check: each cited contract point exists in the live file; exactly 1 non-comment `LD_LIBRARY_PATH` assignment.

### Code Quality Validation
- [ ] Read-only audit — NO source/test/doc files modified (the wrapper is compliant).
- [ ] Report structure + tone mirror `gap_typing.md` / `gap_systemd.md` / `gap_cuda_check.md`.
- [ ] Coverage characterized accurately (no invented pinning tests; the lib-discovery gap honestly recorded).
- [ ] Scope respected (launch_daemon.sh ONLY; siblings cross-referenced, not re-audited).

### Documentation & Deployment
- [ ] The report is self-contained (a maintainer can act on it without reading the PRP).
- [ ] File:line evidence is grep-verifiable (re-runnable commands in §1).
- [ ] Cross-references to `gap_systemd.md` / `gap_cuda_check.md` are accurate.

---

## Anti-Patterns to Avoid

- ❌ Don't EDIT `launch_daemon.sh` / `test_systemd_unit.py` / any source — read-only audit (the wrapper is compliant).
- ❌ Don't EXEC `launch_daemon.sh` or `voice-typing-daemon` to "test" it — it blocks forever (AGENTS.md Rule 2); read + probe instead.
- ❌ Don't copy the PRP's line numbers blindly — re-grep live (Critical #2).
- ❌ Don't hard-code the pytest count or the probe paths — paste the LIVE values (Critical #4/#5).
- ❌ Don't flag the lib-discovery coverage gap (§5.1) as a code defect — it's correct-by-read + live-probe; it's a COVERAGE gap, not a code gap.
- ❌ Don't invent pinning tests for the untested contract points — characterize the gap honestly (§5.1).
- ❌ Don't add a test here (read-only audit; "no new tests" discipline like every round-006 audit).
- ❌ Don't audit out-of-scope files (systemd unit → P1.M4.T1.S1; install.sh → P1.M4.T3.S1; cuda_check → P1.M1.T4.S1).
- ❌ Don't skip the live lib probe — it's the runtime proof contract points (a)+(b) work, which NO test exercises.
- ❌ Don't trust the wrapper "looks right" — re-grep the no-baked-path check (exactly 1 non-comment `LD_LIBRARY_PATH` assignment).

---

## Confidence Score

**9/10** — one-pass success is highly likely. The wrapper is verified-compliant (all 5 contract points by
read + the live lib-discovery probe + 15/15 tests); the verbatim gap-report body is pinned (with `<L...>`
placeholders for the implementer to fill from live greps + the live probe/pytest output); the headline
lib-discovery coverage gap is the clear value-add (mirroring `gap_systemd.md`'s `KillMode=mixed` nuance).
The single residual risk is line-number drift between research time and audit time — mitigated by the
Task-1 PREFLIGHT greps + the L4 evidence spot-check (re-verify each cited line live). The validation gates
(report structure, live probe recorded, live count recorded, scope guard, evidence spot-check) are executable
as written and catch any regression immediately.