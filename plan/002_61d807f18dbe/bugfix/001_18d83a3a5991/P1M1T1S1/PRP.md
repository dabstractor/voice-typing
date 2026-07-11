# PRP — P1.M1.T1.S1: Export `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in launch_daemon.sh

## Goal

**Feature Goal**: Make the production voice-typing daemon load its (already-cached) Whisper models with **zero network calls**, by exporting the two HuggingFace offline env vars in `voice_typing/launch_daemon.sh` before the `exec`. This satisfies PRD §1 ("100% local. No network calls at runtime") and acceptance criterion §7.8 — closing the Critical defect (bugfix Issue 1) where every daemon startup phoned home to `https://huggingface.co` (2 GET requests per startup, one per model, proven in the live journal).

**Deliverable**: `voice_typing/launch_daemon.sh` edited to add (a) a WHY comment block and (b) two `export` lines (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) between the `fi` (line 58) closing the CUDA-libs block and the final `exec` (line 60). No other file is touched.

**Success Definition**: (a) `bash -n voice_typing/launch_daemon.sh` passes; (b) both `export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1` are present; (c) they appear **before** the `exec "$PY" -m voice_typing.daemon` line (env vars are read at `execve`); (d) the existing `LD_LIBRARY_PATH` export (line 53) and all other lines are unchanged; (e) nothing is added to the systemd unit's `Environment=`.

## User Persona

**Target User**: The end user of an always-available local dictation daemon — and, secondarily, anyone who reads the README's "Fully-local voice typing / nothing is sent to a cloud" promise (lines 3 & 6) and expects it to be literally true of the deployed systemd service.

**Use Case**: User installs once (models prefetched to `~/.cache/huggingface/hub`), then runs the daemon 24/7 under systemd — including on a laptop with no network, or where privacy demands no model-revision phone-home.

**Pain Points Addressed**: (1) Privacy — every startup currently leaks (to huggingface.co) that the user runs these specific Whisper models. (2) Offline-startup risk — without the flag, huggingface_hub's online revision check must fail/timeout before falling back to cache, adding latency or crash-looping the unit. (3) Acceptance — PRD §7.8 is a definition-of-done item the deployed service currently fails.

## Why

- **Critical bugfix (bugfix Issue 1):** the live journal proves two `HTTP Request: GET https://huggingface.co/api/models/<repo>/revision/main` per startup (3 startups × 2 models in 2h). `systemctl --user show voice-typing -p Environment` is empty; `/proc/<pid>/environ` has no `HF_*` vars. The daemon is NOT offline as shipped.
- **PRD §1 + §7.8 compliance:** "100% local. No network calls at runtime (model downloads at install time are fine)." Models ARE already cached (install.sh → `prefetch.py`); the daemon merely needs to be told to use the cache exclusively.
- **Why here (the wrapper, not the unit):** the systemd unit is *by design* environment-free — line 29 says `DO NOT add Environment=LD_LIBRARY_PATH=...`, and `launch_daemon.sh` is the sanctioned single source for the daemon process environment (the existing `LD_LIBRARY_PATH` pattern). Adding the offline vars next to that export keeps one consistent source and is inherited by both `systemctl` starts and manual launches.
- **Why export-before-exec (not `os.environ` in Python):** `huggingface_hub/constants.py` captures `HF_HUB_OFFLINE` **at import time** (`os.getenv("HF_HUB_OFFLINE", "0")`). It must be in the environment *before* Python starts. `export …; exec python` (POSIX `execve(2)`) guarantees this; mutating `os.environ` inside `daemon.py` is too late.
- **Lowest-risk fix:** two `export` lines + a comment. Verified by the researcher (research_hf_offline.md "Validation of Proposed Diff"): the recorder constructs cleanly under exactly these two vars with zero `HTTP Request` lines and no errors.

## What

Add a WHY comment block + two `export` lines to `voice_typing/launch_daemon.sh`, placed after the CUDA-libs `fi` and before the final `exec`. The daemon (and its `multiprocessing.spawn` RealtimeSTT workers) inherit the vars. No code, no test, no systemd edit, no README edit in this subtask.

### Success Criteria

- [ ] `voice_typing/launch_daemon.sh` contains `export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1`.
- [ ] Both exports are positioned **before** `exec "$PY" -m voice_typing.daemon "$@"`.
- [ ] `bash -n voice_typing/launch_daemon.sh` passes (valid bash).
- [ ] The `LD_LIBRARY_PATH` export and every other existing line are unchanged; total `^export ` count goes from 1 → 3.
- [ ] `systemd/voice-typing.service` is NOT modified (no new `Environment=`).
- [ ] No test file is created or modified in S1 (the drift-guard test is S2; the test_idle_and_gpu.sh gap is S3).

## All Needed Context

### Context Completeness Check

_Pass._ Every claim is verified against the actual file (line-numbered `cat -n`), the installed library behavior (researcher subagent), and the official HuggingFace docs. The exact edit anchor, the comment style to follow, the scope boundaries (what S1 does NOT do), and the deterministic validation commands are all specified below. No prior knowledge of this codebase is required.

### Documentation & References

```yaml
# AUTHORITATIVE RESEARCH — read before editing
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/research_hf_offline.md
  why: Proves HF_HUB_OFFLINE=1 is read at IMPORT TIME in huggingface_hub/constants.py
       (os.getenv("HF_HUB_OFFLINE","0")), makes ALL huggingface_hub paths cache-only (no GET,
       no HEAD, no resolve), is inherited via export+exec (POSIX execve) by python + spawn
       workers, and that TRANSFORMERS_OFFLINE=1 is harmless belt-and-suspenders (faster-whisper
       has no transformers dep). Validates the exact proposed diff as "correct and sufficient".
  critical: "export-before-exec is STRICTLY MORE CORRECT than os.environ in daemon.py — HF
            captures the flag at import time. Do NOT move this into Python."

- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/scout_launch_status_install.md
  why: §2 confirms the EXACT fix anchor (insert between line 58 `fi` and line 60 `exec`; the
       only existing export is LD_LIBRARY_PATH at line 53). §3 confirms the unit has NO
       Environment= and the line-29 'DO NOT add' comment. §5 documents the S2 drift-guard test
       pattern (tests/test_systemd_unit.py). §6 documents the S3 masking (test_idle_and_gpu.sh:206).
  critical: "§5 (drift-guard test) and §6 (test_idle_and_gpu.sh gap) are S2/S3 — NOT this subtask."

# THE FIX SITE — the file + exact lines
- file: voice_typing/launch_daemon.sh
  why: 60-line bash wrapper. Line 53 exports LD_LIBRARY_PATH; line 58 is `fi`; line 59 blank;
       line 60 is `exec "$PY" -m voice_typing.daemon "$@"`. Insert the comment + 2 exports in
       the line-59 gap, keeping a blank line before `exec`.
  pattern: "Every section in this file opens with a multi-line `# WHY ...` comment block (see the
            header lines 1-29 and the CUDA-libs block lines 38-47). Follow that style for the new
            comment — explain WHY offline, cite PRD §1/§7.8 + bugfix Issue 1."
  gotcha: "The exports MUST precede `exec` (env vars are read at execve). Keep them in the
           wrapper, NOT the systemd unit Environment= (unit line 29 forbids it)."

# THE DESIGN CONSTRAINT — why NOT the systemd unit
- file: systemd/voice-typing.service
  why: Line 29 comment 'DO NOT add Environment=LD_LIBRARY_PATH=...'; ExecStart (line 39) points
       at launch_daemon.sh; no active Environment= directive. The wrapper is the single source.
  critical: "Do NOT edit this file in S1. The offline vars belong in the wrapper alongside the
            LD_LIBRARY_PATH export, by the same design."

# OFFICIAL LIBRARY DOCS (the mechanism)
- url: https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables
  why: Documents HF_HUB_OFFLINE (and TRANSFORMERS_OFFLINE) — read at import, cache-only, skips
       the freshness HEAD/GET. Authoritative source for the behavior the fix relies on.
  critical: "HF_HUB_OFFLINE=1 skips the freshness request ENTIRELY (not just on cache miss)."

# ALREADY-HANDLED TELEMETRY (companion var — do NOT duplicate)
- file: voice_typing/prefetch.py
  why: Line 110 sets os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1") at PREFETCH time
       (install). The two *_OFFLINE vars complete the no-network guarantee at RUNTIME. Do not
       add HF_HUB_DISABLE_TELEMETRY to the wrapper — it is already handled and is subsumed.
  pattern: "prefetch-time telemetry var + runtime offline vars = full no-network guarantee."

# SCOPE-BOUNDARY references (what S1 does NOT do — owned by sibling subtasks)
- file: tests/test_systemd_unit.py
  why: The static drift-guard pattern (reads unit/wrapper files as text, asserts content). S2
       (P1.M1.T1.S2) will add a test here that read_text()'s launch_daemon.sh and asserts it
       contains the two export lines. S1 does NOT write that test.
- file: tests/test_idle_and_gpu.sh
  why: Line 206 `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` is the G-OFFLINE masking that
       hid the bug (the test pre-sets the vars instead of exercising the production path). S3
       (P1.M1.T1.S3) closes that circular-proof gap. S1 does NOT touch this file.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── launch_daemon.sh      # 60-line bash wrapper; ONLY edit target for S1 (insert exports before exec)
│   ├── daemon.py             # NOT edited (vars must be in env before python starts — see Why)
│   └── prefetch.py           # already sets HF_HUB_DISABLE_TELEMETRY=1 at install (line 110) — companion, not duplicate
├── systemd/voice-typing.service  # NOT edited (line 29 forbids Environment=; wrapper is single source)
├── install.sh                # NOT edited in S1 (T2/P1.M1.T2 owns the install offline-confirmation)
└── tests/
    ├── test_systemd_unit.py  # NOT edited in S1 (S2 owns the drift-guard test)
    └── test_idle_and_gpu.sh  # NOT edited in S1 (S3 owns the circular-proof-gap fix)
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/launch_daemon.sh   # MODIFY: +1 WHY comment block +2 export lines (before exec). NO new files.
# Nothing else. No code, no tests, no unit, no README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — ORDERING. The two exports MUST appear BEFORE `exec "$PY" -m voice_typing.daemon`.
# Environment variables are read by the kernel at execve(2) when exec replaces the process; an
# export after exec runs in the wrong (replaced) process. The before-exec ordering gate (L2) checks this.

# CRITICAL #2 — WHY THE WRAPPER, NOT PYTHON. huggingface_hub/constants.py captures HF_HUB_OFFLINE
# at IMPORT TIME (os.getenv at module load). By the time daemon.py could set os.environ, the flag
# is already latched to "0". export+exec puts it in the env before the interpreter starts. This is
# the same reason LD_LIBRARY_PATH is in this wrapper (ld.so reads it at exec, not later).

# CRITICAL #3 — WHY NOT THE SYSTEMD UNIT. The unit is environment-free BY DESIGN (line 29: 'DO NOT
# add Environment=LD_LIBRARY_PATH=...'). launch_daemon.sh recomputes lib dirs from LIVE wheels and
# is the single source for the daemon env. Put the offline vars here, next to the LD_LIBRARY_PATH
# export, so manual launches ALSO get them (not just systemctl starts).

# CRITICAL #4 — BEHAVIOR CHANGE (intended). With HF_HUB_OFFLINE=1, an UNCACHED model raises
# huggingface_hub.errors.LocalEntryNotFoundError at construction -> daemon.py main() returns 1 ->
# systemd Restart=on-failure. This is fail-fast BY DESIGN (no lazy download). Models are prefetched
# at install (prefetch.py), so a correctly-installed daemon never hits this. Do NOT add a fallback
# download — that would reintroduce runtime network calls.

# GOTCHA #5 — TRANSFORMERS_OFFLINE=1 is belt-and-suspenders. faster-whisper has NO transformers
# dependency (research_hf_offline.md §6). The var is a harmless no-op here, but free insurance if a
# transitive dep ever reads it. Keep both vars (the contract specifies both; the test in S2 asserts both).

# GOTCHA #6 — DO NOT add HF_HUB_DISABLE_TELEMETRY here. prefetch.py:110 already sets it at install
# time, and HF_HUB_OFFLINE=1 subsumes the telemetry suppression at runtime. Duplicating it is noise.

# GOTCHA #7 — DON'T touch sibling-scope files. S2 owns the tests/test_systemd_unit.py drift-guard;
# S3 owns the tests/test_idle_and_gpu.sh circular-proof gap; T2 owns install.sh; M3 owns README.
# S1 edits launch_daemon.sh ONLY.

# GOTCHA #8 — full-path discipline on this machine (zsh aliases: python3->uv run, pip->alias,
# tmux->zsh plugin). For bash/python invocations use .venv/bin/python explicitly where needed;
# `bash -n` and `grep`/`awk` are fine as-is.
```

## Implementation Blueprint

### Data models and structure

None. This is a bash-wrapper edit: one comment block + two `export` statements. No data models, no Python, no schema.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/launch_daemon.sh — insert the offline exports before exec
  - The file's tail currently is (verified via cat -n):
        58  fi
        59
        60  exec "$PY" -m voice_typing.daemon "$@"
  - Using the edit tool, replace the unique anchor:
        oldText:
        fi

        exec "$PY" -m voice_typing.daemon "$@"
  - with (newText) — a WHY comment block + the two exports + a blank line + the unchanged exec.
    Match the file's existing comment style (multi-line `# ` blocks, ~78-char wrap). Suggested text:
        fi

        # HF offline guarantee (PRD §1 "100% local" + acceptance §7.8; bugfix Issue 1). Models are
        # prefetched at install time (install.sh -> prefetch.py -> ~/.cache/huggingface/hub), so the
        # daemon loads them from cache with ZERO network. HF_HUB_OFFLINE=1 makes huggingface_hub
        # (hence faster-whisper / RealtimeSTT) cache-only — it skips the freshness GET to
        # https://huggingface.co that online mode fires every startup (journal proved 2 GETs/startup,
        # one per model). huggingface_hub reads this flag at IMPORT TIME (constants.py), so it MUST be
        # in the env BEFORE python starts; exporting here is strictly more correct than os.environ in
        # daemon.py (same reason LD_LIBRARY_PATH lives here). Uncached model -> fail-fast
        # LocalEntryNotFoundError by design (no lazy download). TRANSFORMERS_OFFLINE=1 is harmless
        # belt-and-suspenders (faster-whisper has no transformers dep). Keep in the wrapper, NOT the
        # systemd unit Environment= (unit line 29 forbids it; wrapper is the single env source).
        export HF_HUB_OFFLINE=1
        export TRANSFORMERS_OFFLINE=1

        exec "$PY" -m voice_typing.daemon "$@"
  - CONSTRAINTS: the two `export` lines MUST be the verbatim strings `export HF_HUB_OFFLINE=1` and
    `export TRANSFORMERS_OFFLINE=1` (S2's drift-guard test will grep for these exact strings). Do NOT
    merge them onto one line. Do NOT change the exec line. Do NOT touch lines 1-58.

Task 2: VALIDATE — run the gates in the Validation Loop below. No git commit unless the orchestrator
  directs it (it manages commits between subtasks). If asked to commit, message:
  "P1.M1.T1.S1: export HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE in launch_daemon.sh (offline guarantee)".
```

### Implementation Patterns & Key Details

```bash
# The entire change is a comment block + two exports inserted in the line-59 gap. After the edit the
# tail of the file reads:
#   fi
#   <blank>
#   # HF offline guarantee ... (comment block)
#   export HF_HUB_OFFLINE=1
#   export TRANSFORMERS_OFFLINE=1
#   <blank>
#   exec "$PY" -m voice_typing.daemon "$@"
#
# Why this is correct and sufficient (research_hf_offline.md "Validation of Proposed Diff"):
#   * HF_HUB_OFFLINE=1      -> every huggingface_hub call is cache-only; freshness GET skipped.
#   * TRANSFORMERS_OFFLINE=1 -> no-op-but-harmless insurance.
#   * export ...; exec python -> inherited by python AND multiprocessing.spawn RealtimeSTT workers.
#   * Telemetry already handled at install (prefetch.py:110 HF_HUB_DISABLE_TELEMETRY=1).
# Net: the daemon + its worker processes load cached models with zero HTTP, on the production path.
```

### Integration Points

```yaml
DAEMON PROCESS ENV (launch_daemon.sh -> exec python -> multiprocessing.spawn workers):
  - The exports are inherited by the python process (execve) and by every RealtimeSTT worker spawned
    from it. huggingface_hub in EACH process reads HF_HUB_OFFLINE=1 at import -> cache-only. This is
    why a per-process os.environ set is insufficient and the wrapper is required.

SYSTEMD UNIT (systemd/voice-typing.service):
  - NOT modified. ExecStart (line 39) already points at launch_daemon.sh; the vars flow through the
    wrapper. `systemctl --user show voice-typing -p Environment` STAYS empty by design (the wrapper is
    the single env source; unit line 29 'DO NOT add Environment=...').

MODEL PREFETCH (install.sh -> voice_typing/prefetch.py):
  - Unchanged. prefetch.py populates ~/.cache/huggingface/hub AND sets HF_HUB_DISABLE_TELEMETRY=1
    (line 110). The runtime *_OFFLINE vars + the install-time telemetry var = full no-network guarantee.
  - BEHAVIOR CHANGE: an uncached model now fails fast (LocalEntryNotFoundError) instead of silently
    downloading. This is intended; a correctly-installed daemon has both models cached.

REGRESSION GUARDS (sibling subtasks — NOT S1):
  - S2 (tests/test_systemd_unit.py drift-guard): static assert that launch_daemon.sh contains the two
    exact export strings. S1's exports use those verbatim strings so S2 passes once written.
  - S3 (tests/test_idle_and_gpu.sh): removes the line-206 pre-set and adds a production-path journal
    grep for 'HTTP Request: GET https://huggingface.co' -> fail if found. S1 makes that grep pass.
```

## Validation Loop

> Full paths where relevant (machine aliases python3->uv run). All gates here are static/fast except
> the optional L3 runtime confirmation. The deterministic proof of correctness is L1+L2 (syntax +
> presence + before-exec ordering); the authoritative runtime proof is L3 (journal grep, per the contract).

### Level 1: Syntax + content (deterministic)

```bash
cd /home/dustin/projects/voice-typing
echo "--- bash syntax check (must pass) ---"
bash -n voice_typing/launch_daemon.sh && echo "L1a PASS: bash -n OK" || echo "L1a FAIL"
echo "--- both offline exports present, verbatim ---"
grep -qx 'export HF_HUB_OFFLINE=1' voice_typing/launch_daemon.sh && echo "L1b PASS: HF_HUB_OFFLINE" || echo "L1b FAIL"
grep -qx 'export TRANSFORMERS_OFFLINE=1' voice_typing/launch_daemon.sh && echo "L1c PASS: TRANSFORMERS_OFFLINE" || echo "L1c FAIL"
echo "--- export count went 1 -> 3 (LD_LIBRARY_PATH + 2 offline); LD_LIBRARY_PATH still present ---"
test "$(grep -c '^export ' voice_typing/launch_daemon.sh)" -eq 3 && echo "L1d PASS: 3 exports" || echo "L1d FAIL: got $(grep -c '^export ' voice_typing/launch_daemon.sh)"
grep -q '^export LD_LIBRARY_PATH=' voice_typing/launch_daemon.sh && echo "L1e PASS: LD_LIBRARY_PATH intact" || echo "L1e FAIL: LD_LIBRARY_PATH missing"
# Expected: L1a–L1e all PASS. (grep -qx anchors the full line; the export strings must be verbatim.)
```

### Level 2: The exports precede `exec` (deterministic — the critical ordering gate)

```bash
cd /home/dustin/projects/voice-typing
awk '
  /^export HF_HUB_OFFLINE=1/      { hf = NR }
  /^export TRANSFORMERS_OFFLINE=1/{ tf = NR }
  /^exec "\$PY" -m voice_typing\.daemon/ { ex = NR }
  END {
    ok = (hf && tf && ex && hf < ex && tf < ex)
    print "HF_line=" hf, "TRANS_line=" tf, "EXEC_line=" ex
    exit (ok ? 0 : 1)
  }
' voice_typing/launch_daemon.sh && echo "L2 PASS: both exports before exec" || echo "L2 FAIL: ordering wrong"
# Expected: "L2 PASS: both exports before exec". Env vars are read at execve, so this ordering is load-bearing.
```

### Level 3: Runtime no-network confirmation (authoritative; optional/manual)

> This is the contract's prescribed verification. It needs the full daemon stack (cached models +
> GPU). It is the SAME check S3 will harden into an automated regression on the production path
> (without pre-setting the vars). For S1, run it once manually to confirm zero `HTTP Request` lines.

```bash
cd /home/dustin/projects/voice-typing
# Models must be cached first (install-time prefetch):
ls ~/.cache/huggingface/hub/ | grep -E 'models--Systran--faster-distil-whisper-large-v3|models--Systran--faster-whisper-small.en' \
  || echo "WARN: a model is not cached — under HF_HUB_OFFLINE=1 the daemon will fail-fast (expected for an uninstalled box)."
# If the systemd unit is the deployed path, restart and read the journal (do NOT pre-set the vars —
# the wrapper must supply them):
systemctl --user restart voice-typing
sleep 8   # allow construction (model load from cache)
journalctl --user -u voice-typing --since "1 min ago" --no-pager | grep -c 'HTTP Request: GET https://huggingface.co'
# Expected: 0 (ZERO). Before the fix this printed 2 per startup. Any nonzero count = the exports are
# not reaching the daemon process (re-check L2 ordering and that ExecStart points at launch_daemon.sh).
# Also confirm the vars are in the daemon's actual environment:
PID=$(systemctl --user show voice-typing -p MainPID --value); tr '\0' '\n' < /proc/$PID/environ | grep -E 'HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE'
# Expected: HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1.
```

### Level 4: No out-of-scope edits

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff must touch ONLY voice_typing/launch_daemon.sh ---"
git diff --stat
echo "--- confirm the unit, daemon.py, prefetch.py, tests, install.sh are UNTOUCHED ---"
git diff --name-only | grep -E 'systemd/|daemon\.py|prefetch\.py|tests/|install\.sh|README' && echo "L4 FAIL: out-of-scope file edited" || echo "L4 PASS: only launch_daemon.sh changed"
# Expected: "only launch_daemon.sh changed". (Pre-existing orchestrator entries under plan/ are fine.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1a: `bash -n voice_typing/launch_daemon.sh` passes.
- [ ] L1b/L1c: verbatim `export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1` present.
- [ ] L1d/L1e: exactly 3 `^export ` lines; `LD_LIBRARY_PATH` export intact.
- [ ] L2: both offline exports appear before `exec "$PY" -m voice_typing.daemon` (awk ordering gate).
- [ ] L3 (manual): zero `HTTP Request: GET https://huggingface.co` lines after a production-path start; both vars in `/proc/<pid>/environ`.
- [ ] L4: `git diff` touches only `voice_typing/launch_daemon.sh`.

### Feature Validation
- [ ] Daemon loads cached models with no runtime network calls (PRD §1 + §7.8 satisfied on the deployed path).
- [ ] Both `systemctl` starts and manual `launch_daemon.sh` launches inherit the offline vars (single-source wrapper).
- [ ] Fail-fast behavior for an uncached model is preserved (LocalEntryNotFoundError), not silently re-downloaded.

### Code Quality Validation
- [ ] New comment block follows the file's existing `# WHY` style and cites PRD §1/§7.8 + bugfix Issue 1.
- [ ] Export strings are verbatim (S2's drift-guard test will grep for them exactly).
- [ ] No duplication of `HF_HUB_DISABLE_TELEMETRY` (already in `prefetch.py:110`).

### Scope Boundary Validation
- [ ] `systemd/voice-typing.service` unmodified (no new `Environment=`).
- [ ] `voice_typing/daemon.py` unmodified (vars must be in env before Python starts).
- [ ] No test files created/edited (drift-guard = S2; circular-proof gap = S3).
- [ ] `install.sh` (T2) and `README.md`/`ACCEPTANCE.md` (M3) unmodified.

---

## Anti-Patterns to Avoid

- ❌ Don't put the exports AFTER `exec`, or inside `daemon.py` via `os.environ` — `huggingface_hub` latches `HF_HUB_OFFLINE` at import time; it would be too late. Export-before-exec is mandatory.
- ❌ Don't add `Environment=HF_HUB_OFFLINE=1` to the systemd unit — the unit is environment-free by design (line 29); the wrapper is the single source. Duplicating it splits the source of truth.
- ❌ Don't merge the two exports onto one line or rename them — S2's drift-guard test will assert the verbatim strings `export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1`.
- ❌ Don't drop `TRANSFORMERS_OFFLINE=1` as "unnecessary" — it's intentional belt-and-suspenders and the contract/tests specify both.
- ❌ Don't add `HF_HUB_DISABLE_TELEMETRY=1` here — `prefetch.py:110` already sets it at install time and it's subsumed by `HF_HUB_OFFLINE=1` at runtime.
- ❌ Don't add a network fallback for uncached models — the fail-fast `LocalEntryNotFoundError` is intended; a fallback would reintroduce runtime network calls (the exact bug being fixed).
- ❌ Don't write the drift-guard test (S2) or edit `test_idle_and_gpu.sh` (S3) in this subtask — respect the sibling boundaries.
- ❌ Don't edit `install.sh` (T2) or `README.md`/`ACCEPTANCE.md` (M3) here.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is two `export` lines + a comment, at a verified anchor (line-59 gap before the line-60 exec), with the exact strings prescribed verbatim. Every behavioral claim (import-time capture, cache-only resolution, export+exec inheritance, fail-fast on uncached models, telemetry already handled) is documented in the researcher's `research_hf_offline.md` and confirmed against the official HuggingFace env-vars docs. The deterministic L1+L2 gates (syntax, verbatim presence, before-exec ordering) catch every way a two-line edit can go wrong; L3 provides the authoritative runtime journal-grep the contract asks for. The −0.5 is solely that L3's full runtime confirmation depends on the daemon stack being present (cached models + GPU), which is true on this machine but is environmental, not code, risk.
