name: "P1.M1.T1.S3 — Close the circular-proof gap in test_idle_and_gpu.sh"
description: >

---

## Goal

**Feature Goal**: Convert `tests/test_idle_and_gpu.sh`'s criterion-8 ("no network at runtime") check from a **circular proof** (the test pre-sets `HF_HUB_OFFLINE=1` at line 206, then "proves" the daemon runs offline) into a **non-circular production-path proof**: the test no longer pre-sets the offline vars (they now come from `launch_daemon.sh`, the S1 fix), invokes the real production launch path, and asserts the daemon's own log contains ZERO `HTTP Request: GET https://huggingface.co` lines. This closes the exact masking gap that let bugfix **Issue 1** (production daemon phoning home to huggingface.co on every startup) ship undetected.

**Deliverable**: One file edited — `tests/test_idle_and_gpu.sh` — with five coordinated changes: (1) remove the line-206 `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` pre-set; (2) add a post-ready regression-guard grep over `$WORK/daemon.log`; (3) update the criterion-8 PASS message + its comment to cite the grep (not the pre-set); (4) update the `offline_env:` evidence line; (5) update the file's header + G-OFFLINE invariant comments to document the new non-circular approach. No other file is touched.

**Success Definition**:
- (a) `bash -n tests/test_idle_and_gpu.sh` exits 0 (syntax valid).
- (b) `grep -n 'export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1' tests/test_idle_and_gpu.sh` returns **nothing** — the pre-set line is gone.
- (c) The file contains a new assertion block that runs `grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"` and calls `die` on a match, placed AFTER the ready-wait loop and BEFORE the criterion-6 boot capture.
- (d) The criterion-8 PASS message and the `offline_env:` evidence line both reflect the new grep-based proof (no longer claim the test pre-set the vars).
- (e) The header (L3-5) and G-OFFLINE invariant (L51-52) comments describe the non-circular approach (production path via wrapper; grep is the proof).
- (f) `git diff --name-only` == `tests/test_idle_and_gpu.sh` only.
- (g) **The guard would actually fire on regression**: the grep target string `HTTP Request: GET https://huggingface.co` is verified to be a literal prefix of the verbatim journal lines in the bug report (TEST_RESULTS.md L25-26), and the daemon's stderr logging (root `StreamHandler` via `logging.basicConfig`) is verified to land in `$WORK/daemon.log` via the test's `2>&1` redirect.

> **Note on live validation:** this is a ~400-line manual bash integration test requiring CUDA + prefetched models + ~3-4 min + a quiet room. It is NOT collected by pytest and CANNOT run in CI. Its validation is therefore: `bash -n` syntax check + shellcheck + static verification of the grep target against the journal format + scope check. The CI safety net for the offline guarantee is the SIBLING task **S2** (static drift-guard in `tests/test_systemd_unit.py`), which runs in pytest and fails if the exports leave `launch_daemon.sh`. S3 is the runtime guard; S2 is the configuration guard.

## User Persona

**Target User**: The maintainer (human or AI agent) who will run this heavy integration test before shipping a daemon change, and who must trust that a `[PASS] criterion 8` line means the *production* daemon is offline — not merely that the test harness forced it to be.

**Use Case**: A future change regresses `launch_daemon.sh` (removes or reorders the offline exports). The maintainer runs `./tests/test_idle_and_gpu.sh`. Because the test no longer pre-sets the vars, the daemon launches via the real (regressed) wrapper, makes online HF requests, httpx logs them to stderr → daemon.log, and the new grep fails the test with a clear message pointing at `launch_daemon.sh`. Under the OLD circular test, this regression would have printed `[PASS] criterion 8`.

**Pain Points Addressed**: Issue 1 shipped because the only "offline" test *itself* supplied `HF_HUB_OFFLINE=1` (line 206), masking the production defect. The criterion-8 "proof" passed because the test supplied the very variable production omitted. This subtask removes that self-deception.

## Why

- **Closes the masking gap at the runtime layer.** S1 fixed the root cause (exports in the wrapper). S2 added a static guard (exports present in the wrapper text). S3 closes the loop with a **runtime** guard that exercises the real `launch_daemon.sh` path and observes the daemon's actual network behavior. Together the three subtasks make Issue 1 impossible to reintroduce silently.
- **Makes `[PASS] criterion 8` mean what it says.** PRD §7 criterion 8 ("No network access needed at runtime") is a definition-of-done item. As shipped, the daemon violated it while the test claimed compliance. S3 makes the test's claim truthful.
- **Cheap and surgical.** A handful of coordinated comment/code edits to one test file. No daemon code, no config, no new dependencies.
- **Scope discipline.** S3 owns ONLY `tests/test_idle_and_gpu.sh`. It does NOT touch `launch_daemon.sh` (S1 owns it), `tests/test_systemd_unit.py` (S2 owns it — **being implemented in parallel right now**), `install.sh` (T2), or docs (M3).

## What

Five coordinated edits to `tests/test_idle_and_gpu.sh`, all documented in the file's own comments (Mode A — no external docs files):

1. **Remove the circular pre-set** — delete line 206 `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` (optionally replace with a one-line comment noting the wrapper provides them).
2. **Add the runtime regression guard** — after the daemon is confirmed ready, grep `$WORK/daemon.log` for `HTTP Request: GET https://huggingface.co` and `die` if any match; echo a PASS line if none.
3. **Update the criterion-8 message** (L386-388) — the proof is now the grep (no HF HTTP lines), not a pre-set env var.
4. **Update the evidence line** (L404 `offline_env:`) — reflect that the vars come from `launch_daemon.sh` and the log grep is clean.
5. **Update the documentation comments** — header (L3-5), G-OFFLINE invariant (L51-52), and the launch-section comment block (L200-205) describe the non-circular production-path approach.

### Success Criteria

- [ ] `bash -n tests/test_idle_and_gpu.sh` → exit 0.
- [ ] No `export HF_HUB_OFFLINE` directive remains in the test file.
- [ ] A `grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"` assertion exists, calls `die` on match, and is positioned after the ready-wait loop.
- [ ] The criterion-8 PASS message + `offline_env:` evidence line reference the grep-based proof.
- [ ] Header + G-OFFLINE comments describe the non-circular approach.
- [ ] `git diff --name-only` == `tests/test_idle_and_gpu.sh`.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement S3 from this PRP alone: the exact file, the exact edit sites with verified line numbers, the verbatim contract-specified grep code, the load-bearing explanation of WHY the grep works (httpx → root stderr handler → daemon.log), the validation commands that are actually runnable (this test cannot run in CI — that constraint and its mitigation are explicit), and the scope boundaries (what NOT to touch). The reference implementation in the Blueprint is copy-ready. No prior knowledge required.

### Documentation & References

```yaml
# THE INPUT CONTRACT — S1's deliverable (the precondition for S3)
- file: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M1T1S1/PRP.md
  why: Defines the verbatim export strings S1 produced in launch_daemon.sh:
       `export HF_HUB_OFFLINE=1` + `export TRANSFORMERS_OFFLINE=1` before `exec "$PY" -m voice_typing.daemon`.
       S1 L259-260 explicitly scopes S3: "removes the line-206 pre-set and adds a production-path
       journal grep for 'HTTP Request: GET https://huggingface.co' -> fail if found. S1 makes that
       grep pass." This is the contract S3 fulfills.
  critical: "S1 is ALREADY APPLIED in the live file (exports at launch_daemon.sh L71-72, exec L74).
       So removing the test's pre-set does NOT break the test — the daemon still inherits both vars
       via the wrapper at execve(2). S3 is expected to pass a syntax check and (on a GPU host) a live run."

# THE PARALLEL SIBLING — S2 (being implemented concurrently; do NOT collide)
- file: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M1T1S2/PRP.md
  why: S2 adds the STATIC drift-guard test (test_systemd_unit.py::test_launch_daemon_exports_offline_vars)
       that fails if the exports leave launch_daemon.sh. S3 is the RUNTIME complement. The two are
       independently auditable and own DIFFERENT files.
  critical: "S2 is running IN PARALLEL. S3 must NOT edit tests/test_systemd_unit.py or launch_daemon.sh.
       S3 owns ONLY tests/test_idle_and_gpu.sh."

# THE FILE UNDER EDIT
- file: tests/test_idle_and_gpu.sh
  why: ~410-line manual bash integration test. The masking line is 206; the launch is 207; the
       ready-wait loop ends ~222; the criterion-8 message is 386-388; the evidence line is 404;
       the header is 1-5; the G-OFFLINE invariant is 51-52; the launch-section comment is 200-205.
  pattern: "Heavy test driven by G-* gotcha invariants documented in the header. Each guard echoes a
            [PASS]/[FAIL] line; on FAIL it calls die(). An === ACCEPTANCE EVIDENCE === block is
            printed for paste into tests/ACCEPTANCE.md."
  gotcha: "Line 207 redirects BOTH streams: \"$LAUNCH\" > \"$WORK/daemon.log\" 2>&1 &. The 2>&1 folds
           stderr (where httpx logs) into daemon.log — this is WHY the grep works. Do not change the
           redirect."

# WHY THE GREP WORKS — the daemon's stderr logging config
- file: voice_typing/daemon.py
  why: _setup_logging (L1149-1173) calls logging.basicConfig(stream=sys.stderr, ...) installing a
       root-level StreamHandler. httpx logs 'HTTP Request: GET https://huggingface.co' via
       logging.getLogger('httpx') (a child of root) -> propagates to the root handler -> stderr ->
       daemon.log (via the test's 2>&1). This is verified: the production systemd journal captured
       the same lines (journald captures unit stderr).
  section: "_setup_logging (L1149-1173) is the load-bearing fact. Do NOT edit daemon.py (read-only)."

# THE GREP TARGET — verbatim journal format from the bug report
- file: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/TEST_RESULTS.md
  why: L25-26 are the verbatim journal lines proving the exact log format:
       'HTTP Request: GET https://huggingface.co/api/models/Systran/.../revision/main "HTTP/1.1 200 OK"'.
       The grep substring 'HTTP Request: GET https://huggingface.co' is a literal prefix of both.
  critical: "Use EXACTLY this substring. Tightening to '/api/models/' risks missing future variants;
             loosening to 'huggingface' risks false positives."

# SCOUT RESEARCH — the masking + recommended fix
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/scout_launch_status_install.md
  why: §6 documents the G-OFFLINE masking (test_idle_and_gpu.sh:206) and the recommended fix
       (remove the pre-set, rely on launch_daemon.sh exports, add a journal grep).
  section: "§6 is the load-bearing section for S3."

# HF OFFLINE BEHAVIOR RESEARCH (why zero lines under HF_HUB_OFFLINE=1)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/research_hf_offline.md
  why: "Validation of Proposed Diff" confirms the recorder constructs cleanly under exactly the two
       offline vars with ZERO 'HTTP Request' lines and no errors — i.e. the grep is expected to be
       CLEAN when S1's exports are present (the PASS path).

# PRD CONTEXT (READ-ONLY) — the requirement this guard protects
- file: PRD.md
  why: §1 ("100% local. No network calls at runtime") + §7 acceptance criterion 8 ("No network
       access needed at runtime, models cached by install"). The test comments cite these.
  critical: "The guard protects a definition-of-done criterion. Cite §1 + §7.8 in the new comment."

# SCOPE-BOUNDARY references (owned by SIBLING subtasks — do NOT touch)
- file: voice_typing/launch_daemon.sh
  why: Owned by S1 (already applied). S3 READS it to understand the contract; does NOT edit it.
- file: tests/test_systemd_unit.py
  why: Owned by S2 (in parallel). S3 does NOT touch it.
- file: install.sh
  why: Owned by T2. S3 does NOT touch it.
```

### Current Codebase tree (relevant slice — S1 already applied; S2 in parallel)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── test_idle_and_gpu.sh    # 410 lines — the ONLY file S3 edits (this PRP)
│   └── test_systemd_unit.py    # UNTOUCHED by S3 (S2 owns it; in parallel)
├── voice_typing/
│   ├── launch_daemon.sh        # READ-ONLY for S3. S1 applied: exports at L71-72, exec at L74.
│   └── daemon.py               # READ-ONLY for S3. _setup_logging (L1149-1173) explains the grep.
├── systemd/voice-typing.service # untouched
└── plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/
    ├── TEST_RESULTS.md          # L25-26 = verbatim journal format (grep target source of truth)
    └── architecture/scout_launch_status_install.md  # §6 = the masking + recommended fix
```

### Desired Codebase tree with files to be changed

```bash
tests/test_idle_and_gpu.sh   # MODIFY: remove L206 pre-set; add post-ready grep guard; update
                             #          criterion-8 msg (L386-388) + offline_env line (L404) +
                             #          header (L3-5) + G-OFFLINE invariant (L51-52) + launch
                             #          comment (L200-205) + ready echo (L209).
# NOTHING ELSE. No new files. No edits to launch_daemon.sh / test_systemd_unit.py / daemon.py /
# the systemd unit / install.sh / README.md / ACCEPTANCE.md.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — DO NOT re-add the pre-set "to be safe." The ENTIRE point of S3 is to remove line 206's
# `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`. Keeping it re-introduces the circular proof that
# masked Issue 1. After S1, launch_daemon.sh exports both vars before exec, so the daemon inherits
# them at execve(2) WITHOUT the test pre-setting anything. Verify removal: grep must return nothing.

# CRITICAL #2 — THE GREP TARGET STRING IS LOAD-BEARING AND EXACT. Use EXACTLY:
#     'HTTP Request: GET https://huggingface.co'
# This is the httpx INFO-log prefix, verified as a literal prefix of BOTH bug-report journal lines
# (TEST_RESULTS.md L25-26). Do NOT tighten to '/api/models/' (risks missing variants) or loosen to
# 'huggingface' (risks false positives from unrelated logs / cache paths).

# CRITICAL #3 — WHY THE GREP CAN SEE THE LINES. The daemon's _setup_logging (daemon.py L1149-1173)
# does `logging.basicConfig(stream=sys.stderr, ...)` → a root-level StreamHandler on stderr. httpx
# logs 'HTTP Request: GET https://huggingface.co' via the 'httpx' child logger → propagates to root
# → stderr. The test launch (L207) is `"$LAUNCH" > "$WORK/daemon.log" 2>&1 &` → stderr folds into
# daemon.log. So the grep sees the lines IFF the daemon made online HF requests. This chain is
# verified by the production journal (journald captures the same stderr). Do NOT alter the redirect.

# CRITICAL #4 — PLACEMENT OF THE GREP. It MUST run AFTER the daemon is confirmed ready (after the
# ready-wait loop, L218: `[ "$ready" = 1 ] || die ...`) and BEFORE the criterion-6 boot capture
# (`# --- criterion 6: un-armed boot`). The HF online checks happen at model-load/startup, so the
# log lines exist by the time the daemon is ready. Placing it before ready is premature; placing it
# at the very end (near L386) delays a fast FAIL. The contract specifies "after the ready-wait loop."

# GOTCHA #5 — NETWORK-FAILURE NUANCE (non-blocking, do not over-engineer). On a host WITH network
# (the typical dev machine, and exactly the case where the regression would "succeed" silently),
# the online freshness check completes and httpx logs the GET → grep matches → FAIL (correct). On a
# host WITHOUT network AND a regressed wrapper, huggingface_hub's check may time out before httpx
# logs the request line; in that case startup latency spikes and the daemon may hit the 180s
# ready-wait timeout or raise LocalEntryNotFoundError → caught by the EXISTING `die "daemon not
# ready in 180s"` / `die "daemon exited during startup"` guards. Either way the test does not
# silently pass. Do NOT add a `curl`/`wget` network probe — the contract says "Do NOT make it require
# network." The grep of a LOCAL log file is the guard.

# GOTCHA #6 — THIS TEST IS NOT COLLECT BY PYTEST. It is a manual .sh script (header L33). Do NOT add
# a pytest wrapper or conftest hook. Validation is `bash -n` + shellcheck + static analysis + scope
# check (see Validation Loop). The CI safety net is S2.

# GOTCHA #7 — THE DAEMON LOG PATH IS $WORK/daemon.log (NOT the journal). This test launches the
# daemon DIRECTLY via launch_daemon.sh (not via systemctl), so `journalctl` would NOT see it. The
# grep target is the FILE redirected at L207. Do not grep the journal in this test.

# GOTCHA #8 — PARALLEL EXECUTION WITH S2. S2 (test_systemd_unit.py) is being implemented
# concurrently. S3 and S2 own DIFFERENT files and must not collide. S3 edits ONLY
# tests/test_idle_and_gpu.sh. If you find yourself editing test_systemd_unit.py or launch_daemon.sh,
# STOP — that is out of scope.

# GOTCHA #9 — KEEP THE die() CONTRACT. The file's `die()` helper (L172) does `echo "FAIL: $*" >&2;
# exit 1` and the EXIT trap prints the daemon.log tail on failure. The new grep's die() message should
# point at launch_daemon.sh (the likely regressed file) and reference $WORK/daemon.log for triage.

# GOTCHA #10 — bash, grep, git are fine as-is; no full-path needed (no zsh python alias involved).
```

## Implementation Blueprint

### Data models and structure

None. This is a pure bash-script edit: comment rewording + one directive deletion + one new guard block. No data models, no Python, no config.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: REMOVE the circular pre-set at line 206 + update the launch-section comment (L200-209)
  - FILE: tests/test_idle_and_gpu.sh
  - DELETE line 206: `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`
    (REPLACE with a one-line comment so the rationale is visible at the launch site, e.g.:
     `# offline vars come from launch_daemon.sh (bugfix Issue 1 fix) — do NOT pre-set here (that
      # masked Issue 1; the grep guard below is the non-circular proof).`)
  - REWORD the comment block L200-205 to describe the NEW approach. Current text says "HF_HUB_OFFLINE=1
    TRANSFORMERS_OFFLINE=1 -> criterion 8 proof: if the daemon STARTS ... that is empirical proof the
    models load from cache with ZERO network." Replace with: the test launches via the PRODUCTION
    path (launch_daemon.sh) WITHOUT pre-setting the vars; the wrapper exports them (S1); the
    criterion-8 proof is the post-ready grep over $WORK/daemon.log (added in Task 2).
  - REWORD line 209 echo: current `echo "daemon launched OFFLINE (HF_HUB_OFFLINE=1) pid=$DAEMON_PID;
    waiting for ready (up to 180s)..."` -> e.g. `echo "daemon launched via launch_daemon.sh
    (production path; offline vars via wrapper) pid=$DAEMON_PID; waiting for ready (up to 180s)..."`
  - DO NOT change line 207 (the `> "$WORK/daemon.log" 2>&1 &` redirect — Gotcha #3).
  - CONSTRAINT: keep `set -euo pipefail` behavior intact; the removed export has no fallthrough.

Task 2: ADD the post-ready regression guard (the load-bearing change)
  - FILE: tests/test_idle_and_gpu.sh
  - PLACE: immediately AFTER `[ "$ready" = 1 ] || die "daemon not ready in 180s; see $WORK/daemon.log"`
    (L218) and BEFORE the blank line + `# --- criterion 6: un-armed boot — capture BEFORE start` (L220).
  - CODE (copy-ready; the grep string and die message are load-bearing — Gotchas #2/#9):
        # --- criterion 8 (no-network): NON-CIRCULAR regression guard (bugfix Issue 1) ---
        # The test did NOT pre-set HF_HUB_OFFLINE (that masked Issue 1). launch_daemon.sh exports it
        # (S1); this grep proves the PRODUCTION path is offline by asserting the daemon log contains
        # ZERO online huggingface.co requests. httpx logs 'HTTP Request: GET https://huggingface.co'
        # to stderr (root StreamHandler from daemon._setup_logging) -> folded into daemon.log by the
        # 2>&1 redirect at launch. Missing exports => online freshness check => match => FAIL.
        if grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"; then
          die "FAIL: daemon made network calls to huggingface.co (offline exports missing from launch_daemon.sh?); see $WORK/daemon.log"
        fi
        echo "[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)"
  - CONSTRAINTS:
      * Use EXACTLY the grep substring 'HTTP Request: GET https://huggingface.co' (Gotcha #2).
      * The `die` message must mention launch_daemon.sh and $WORK/daemon.log (Gotcha #9).
      * Quote "$WORK/daemon.log" (set -u; WORK is always set by setup, but quote for safety).
      * `grep -q` returns 1 (no match) on the PASS path — under `set -e` this is fine because it is
        the condition of an `if` (command's exit status is consumed by the if, not triggering set -e).

Task 3: UPDATE the criterion-8 PASS message + its comment (L386-388)
  - FILE: tests/test_idle_and_gpu.sh
  - REWORD L386-387 comment from "# --- criterion 8 (no-network): restate — the WHOLE run was under
    HF_HUB_OFFLINE=1 --- / (ready=1 + survived the 120s window = empirical proof ...)" to:
        # --- criterion 8 (no-network): NON-CIRCULAR proof — the daemon.log grep (Task 2 guard) found
        # ZERO 'HTTP Request: GET https://huggingface.co' lines. The test never pre-set the offline
        # vars; launch_daemon.sh exports them (production path), so this proves the DEPLOYED path is
        # offline (not just that the daemon CAN run offline).
  - REWORD L388 echo from:
        echo "[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded cached models"
    to:
        echo "[PASS] criterion 8 (no network): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (offline via launch_daemon.sh, not a test pre-set)"

Task 4: UPDATE the offline_env evidence line (L404)
  - FILE: tests/test_idle_and_gpu.sh
  - REWORD L404 from:
        echo "offline_env: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1"
    to:
        echo "offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN"
  - WHY: the evidence block is pasted into tests/ACCEPTANCE.md; it must not claim the test pre-set
    the vars. The new line documents the production-path source + the grep verdict.

Task 5: UPDATE the header + G-OFFLINE documentation comments (L3-5, L51-52)
  - FILE: tests/test_idle_and_gpu.sh
  - REWORD the header L3-5 from "Stands up the REAL daemon (launch_daemon.sh, launched OFFLINE with
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 so the run itself PROVES PRD §7 criterion 8 ...)" to
    describe the production-path launch + wrapper-provided vars + grep-as-proof. Suggested:
        # Stands up the REAL daemon via the PRODUCTION path (launch_daemon.sh — no pre-set env, so the
        # test exercises the real systemd -> wrapper flow). launch_daemon.sh exports HF_HUB_OFFLINE=1 +
        # TRANSFORMERS_OFFLINE=1 (bugfix Issue 1 fix); this test asserts ZERO 'HTTP Request: GET
        # https://huggingface.co' lines in the daemon log as the criterion-8 proof (no circular pre-set).
  - REWORD the G-OFFLINE invariant L51-52 from "launch with HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 —
    the run itself is the criterion-8 proof ..." to:
        #   G-OFFLINE:           do NOT pre-set HF_HUB_OFFLINE (that masked Issue 1). Rely on
        #                        launch_daemon.sh's exports (production path); grep daemon.log for ZERO
        #                        'HTTP Request: GET https://huggingface.co' lines as the NON-CIRCULAR
        #                        criterion-8 proof.
  - WHY (Mode A docs): the file's own header is the durable documentation of the test's invariants.
    Leaving the old wording would contradict the new code and mislead future readers.

Task 6: VALIDATE — run the Validation Loop L1-L4 below. No git commit unless the orchestrator
  directs it. If asked to commit, message:
  "P1.M1.T1.S3: close circular-proof gap in test_idle_and_gpu.sh (Issue 1 runtime guard)".
```

### Implementation Patterns & Key Details

```bash
# The single most important change: the post-ready grep. This is what converts a circular proof
# (test supplies the var) into a non-circular one (observe the daemon's real network behavior).

# The guard block (Task 2) — copy-ready:
if grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"; then
  die "FAIL: daemon made network calls to huggingface.co (offline exports missing from launch_daemon.sh?); see $WORK/daemon.log"
fi
echo "[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)"

# PATTERN NOTE — `grep -q` under `set -e`: grep exits 1 when there is NO match, but because it is the
# condition of an `if`, its non-zero status is consumed by the `if` and does NOT trigger `set -e`.
# This is the standard idiom elsewhere in this file (e.g. `if "$VOICECTL" status >/dev/null 2>&1`).
# Do NOT wrap it in `|| true` — that would mask a real grep error.

# PATTERN NOTE — the `die()` helper (L172): `die() { echo "FAIL: $*" >&2; exit 1; }`. The EXIT trap
# (cleanup) already prints `tail -n 30 "$WORK/daemon.log"` on failure, so the die message just needs
# to point at the likely root cause (launch_daemon.sh) — the trap shows the log tail automatically.
```

### Integration Points

```yaml
DEPENDS ON (S1 — P1.M1.T1.S1, ALREADY APPLIED):
  - S3's grep PASSES only because S1 put the exports in launch_daemon.sh (L71-72), so the daemon
    runs offline and emits zero HF HTTP lines. If a future change reverts S1, S3's grep goes RED —
    which is the intended behavior. S1 (config fix) + S2 (static guard) + S3 (runtime guard) form the
    complete fix+guard set for Issue 1.

PARALLEL WITH (S2 — P1.M1.T1.S2, IN PROGRESS):
  - S2 owns tests/test_systemd_unit.py (static drift-guard). S3 owns tests/test_idle_and_gpu.sh
    (runtime guard). Different files; no collision. S3 does NOT read or write test_systemd_unit.py.

FILES NOT TOUCHED (scope boundary):
  - voice_typing/launch_daemon.sh (S1 owns; S3 reads only).
  - tests/test_systemd_unit.py (S2 owns; in parallel).
  - systemd/voice-typing.service, voice_typing/daemon.py (read-only reference).
  - install.sh (T2), README.md / ACCEPTANCE.md (M3).

TEST DISCOVERY:
  - tests/test_idle_and_gpu.sh is a MANUAL bash script — NOT collected by pytest. It is invoked
    directly: `./tests/test_idle_and_gpu.sh` (preflight refuses if a daemon is already running).
    The pytest suite (run elsewhere) is unaffected by S3 because S3 edits no .py file.
```

## Validation Loop

> All commands run from `/home/dustin/projects/voice-typing`. This test CANNOT run in CI (requires
> CUDA + prefetched models + ~3-4 min + a quiet room). Validation is therefore static + scope checks.
> The CI safety net for the offline guarantee is S2.

### Level 1: Syntax + style (the primary automated gate)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L1a: bash syntax check (the gate that matters) ---"
bash -n tests/test_idle_and_gpu.sh && echo "L1a PASS: syntax valid" || echo "L1a FAIL: syntax error"
# Expected: L1a PASS. If FAIL, read the bash error, fix, re-run.

echo "--- L1b: shellcheck (if available; non-blocking but recommended) ---"
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck tests/test_idle_and_gpu.sh && echo "L1b PASS: shellcheck clean" || echo "L1b WARN: shellcheck findings (review; the new grep block should be clean)"
else
  echo "L1b SKIP: shellcheck not installed (non-blocking)"
fi
# Expected: the new `if grep -q ...` block introduces no SC errors. An SC2086 on "$WORK/daemon.log"
# would be a false positive (single quoted token) — but we quote it, so it should be clean.
```

### Level 2: The pre-set is gone + the guard is present (static structural checks)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L2a: the circular pre-set is GONE (line 206 removed) ---"
if grep -nE '^[[:space:]]*export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1[[:space:]]*$' tests/test_idle_and_gpu.sh; then
  echo "L2a FAIL: the pre-set export is still present (circular proof not closed)"
else
  echo "L2a PASS: no standalone pre-set export of the offline vars"
fi
# Expected: L2a PASS (grep returns nothing). NOTE: a COMMENTED-OUT line like
# `# export HF_HUB_OFFLINE=1 ...` is acceptable per the contract — the regex above anchors to a
# real directive, so a comment passes. If you commented it out, also confirm with:
#   ! grep -nE '^[[:space:]]*export HF_HUB_OFFLINE' tests/test_idle_and_gpu.sh

echo "--- L2b: the regression-guard grep is PRESENT with the exact target string ---"
grep -nF "grep -q 'HTTP Request: GET https://huggingface.co'" tests/test_idle_and_gpu.sh \
  && echo "L2b PASS: guard grep present with exact target" \
  || echo "L2b FAIL: guard grep missing or target string altered"

echo "--- L2c: the guard calls die() on match ---"
# Find the grep line, then check the next few lines contain a die() referencing launch_daemon.sh.
awk '/grep -q .HTTP Request: GET https:\/\/huggingface\.co./{hit=NR} END{exit !(hit>0)}' tests/test_idle_and_gpu.sh \
  && echo "L2c(i): grep located" || echo "L2c FAIL: grep not located"
grep -A4 "grep -q 'HTTP Request: GET https://huggingface.co'" tests/test_idle_and_gpu.sh \
  | grep -q 'die.*launch_daemon\.sh' \
  && echo "L2c PASS: die() references launch_daemon.sh" \
  || echo "L2c FAIL: die() message does not point at launch_daemon.sh"
```

### Level 3: Placement + proof semantics (the guard is in the right place and means what it says)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L3a: the guard runs AFTER the ready-wait loop and BEFORE criterion-6 boot capture ---"
READY_LINE=$(grep -n 'daemon not ready in 180s' tests/test_idle_and_gpu.sh | head -1 | cut -d: -f1)
GUARD_LINE=$(grep -n "grep -q 'HTTP Request: GET https://huggingface.co'" tests/test_idle_and_gpu.sh | head -1 | cut -d: -f1)
BOOT_LINE=$(grep -n 'criterion 6: un-armed boot' tests/test_idle_and_gpu.sh | head -1 | cut -d: -f1)
echo "  ready-loop-end line: $READY_LINE; guard line: $GUARD_LINE; criterion-6 boot line: $BOOT_LINE"
[ -n "$READY_LINE" ] && [ -n "$GUARD_LINE" ] && [ -n "$BOOT_LINE" ] \
  && [ "$READY_LINE" -lt "$GUARD_LINE" ] && [ "$GUARD_LINE" -lt "$BOOT_LINE" ] \
  && echo "L3a PASS: ready < guard < boot (correct placement)" \
  || echo "L3a FAIL: guard is misplaced (must be after ready-loop, before criterion-6 boot)"

echo "--- L3b: the grep target matches the verbatim bug-report journal format ---"
# TEST_RESULTS.md L25-26 are the real journal lines; our grep substring must be their literal prefix.
if grep -qF 'HTTP Request: GET https://huggingface.co' plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/TEST_RESULTS.md; then
  echo "L3b PASS: grep substring is a literal substring of the bug-report journal lines"
else
  echo "L3b FAIL: grep substring does not match the documented journal format"
fi

echo "--- L3c: criterion-8 message + offline_env line no longer claim a pre-set ---"
grep -n 'criterion 8 (no network)' tests/test_idle_and_gpu.sh | grep -qi 'pre-set\|ran under HF_HUB_OFFLINE' \
  && echo "L3c FAIL: criterion-8 message still claims a pre-set" \
  || echo "L3c(i) PASS: criterion-8 message reflects grep-based proof"
grep -n 'offline_env:' tests/test_idle_and_gpu.sh | grep -q 'launch_daemon\.sh' \
  && echo "L3c(ii) PASS: offline_env line cites launch_daemon.sh" \
  || echo "L3c(ii) FAIL: offline_env line still claims a test pre-set"
```

### Level 4: Scope + suite integrity (only the test file changed; nothing else regressed)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L4a: git diff touches ONLY tests/test_idle_and_gpu.sh ---"
if git diff --name-only | grep -vxE 'tests/test_idle_and_gpu.sh'; then
  echo "L4a FAIL: out-of-scope file(s) changed"
else
  echo "L4a PASS: only tests/test_idle_and_gpu.sh changed"
fi

echo "--- L4b: sibling-scope files are UNTOUCHED ---"
git diff --quiet voice_typing/launch_daemon.sh tests/test_systemd_unit.py systemd/voice-typing.service voice_typing/daemon.py install.sh README.md tests/ACCEPTANCE.md \
  && echo "L4b PASS: all sibling-scope files unchanged" \
  || echo "L4b FAIL: a sibling-scope file was modified"

echo "--- L4c: the pytest suite is unaffected (S3 edits no .py file) ---"
.venv/bin/python -m pytest tests/test_systemd_unit.py -q
# Expected: all pass (S3 touches no .py; S2's new test, if landed, is also green). This is a
# sanity check that S3 did not accidentally collide with S2's file.
```

### Level 5: Manual live validation (OPTIONAL — requires the GPU host; not a gate)

> Only if the implementer is on the CUDA host with prefetched models and a quiet room. This is the
> real proof the guard works end-to-end. It is NOT required for S3 acceptance (the static gates above
> are sufficient per the item contract).

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true   # preflight refuses a running daemon
./tests/test_idle_and_gpu.sh
# Expected (S1 applied): the new guard echoes
#   "[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines ..."
# and the run ends "=== IDLE+GPU PASS (criteria 5, 6, 8) ===".

# OPTIONAL mutation proof (proves the guard FIRES on regression — temporarily revert S1, then restore):
cp voice_typing/launch_daemon.sh /tmp/launch_daemon.sh.bak
sed -i '/^export HF_HUB_OFFLINE=1$/d' voice_typing/launch_daemon.sh    # remove the export
./tests/test_idle_and_gpu.sh
# Expected: the guard FAILs with "FAIL: daemon made network calls to huggingface.co ..." (the grep
# now matches the online freshness-check lines in daemon.log).
cp /tmp/launch_daemon.sh.bak voice_typing/launch_daemon.sh             # RESTORE S1
git diff --quiet voice_typing/launch_daemon.sh && echo "restored to S1 state" || git checkout voice_typing/launch_daemon.sh
rm -f /tmp/launch_daemon.sh.bak
```

## Final Validation Checklist

### Technical Validation
- [ ] L1a: `bash -n tests/test_idle_and_gpu.sh` → exit 0 (syntax valid).
- [ ] L1b: shellcheck clean on the new grep block (if shellcheck available).
- [ ] L2a: no standalone `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` directive remains.
- [ ] L2b: the guard grep is present with the EXACT target `HTTP Request: GET https://huggingface.co`.
- [ ] L2c: the guard's `die()` references `launch_daemon.sh` (points at the likely regressed file).
- [ ] L3a: guard placement is ready-loop-end < guard < criterion-6-boot.
- [ ] L3b: grep substring verified against the bug-report journal format (TEST_RESULTS.md L25-26).
- [ ] L3c: criterion-8 message + `offline_env:` line reflect the grep-based proof (no pre-set claim).
- [ ] L4a: `git diff --name-only` == `tests/test_idle_and_gpu.sh`.
- [ ] L4b: sibling-scope files (launch_daemon.sh, test_systemd_unit.py, unit, daemon.py, install.sh, README, ACCEPTANCE) unchanged.
- [ ] L4c: pytest suite unaffected (S3 edits no .py file).

### Feature Validation
- [ ] The test no longer pre-sets `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` (circular proof removed).
- [ ] The test relies on `launch_daemon.sh`'s exports (S1) — the daemon inherits them at execve(2).
- [ ] A regression (exports removed from launch_daemon.sh) is caught by the daemon.log grep → FAIL.
- [ ] The new guard runs after the daemon is ready (so the startup HF lines, if any, are already logged).
- [ ] Header + G-OFFLINE invariant comments document the non-circular production-path approach.

### Code Quality Validation
- [ ] Follows the file's existing conventions: G-* invariant comments, `[PASS]`/`[FAIL]` echoes, `die()` on failure, fenced `=== ACCEPTANCE EVIDENCE ===` block.
- [ ] The `grep -q` idiom under `set -e` is correct (exit status consumed by `if`).
- [ ] `"$WORK/daemon.log"` is quoted.
- [ ] The launch redirect (`> "$WORK/daemon.log" 2>&1 &`) is UNCHANGED (Gotcha #3).

### Scope Boundary Validation
- [ ] `voice_typing/launch_daemon.sh` unmodified (S1 owns; S3 reads only).
- [ ] `tests/test_systemd_unit.py` unmodified (S2 owns; in parallel — no collision).
- [ ] `systemd/voice-typing.service`, `voice_typing/daemon.py`, `install.sh`, `README.md`, `tests/ACCEPTANCE.md` unmodified.
- [ ] No pytest wrapper or conftest hook added for this `.sh` script (it is a manual test).

### Documentation & Deployment
- [ ] Mode A: the test file's own header (L3-5), G-OFFLINE invariant (L51-52), launch comment (L200-205), criterion-8 comment (L386-387), and evidence line (L404) all document the new non-circular proof approach.
- [ ] No external docs files created or edited (that is M3's scope).
- [ ] If asked to commit: message references bugfix Issue 1 for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't keep the line-206 pre-set "to be safe" — that re-introduces the circular proof that masked Issue 1. The whole point of S3 is to remove it. After S1, the wrapper exports the vars. (Gotcha #1.)
- ❌ Don't alter the grep target string — `HTTP Request: GET https://huggingface.co` is the exact httpx log prefix verified against the bug report. Tightening (`/api/models/`) or loosening (`huggingface`) both break the guard. (Gotcha #2.)
- ❌ Don't change the launch redirect (`> "$WORK/daemon.log" 2>&1 &`) — the `2>&1` is WHY the grep can see httpx's stderr logs. (Gotcha #3.)
- ❌ Don't place the grep before the ready-wait loop completes (the startup HF lines may not be logged yet) or at the very end (delays a fast FAIL). Place it right after `[ "$ready" = 1 ]`. (Gotcha #4.)
- ❌ Don't add a `curl`/`wget` network probe — the contract says "Do NOT make it require network." The guard greps a LOCAL log file. (Gotcha #5.)
- ❌ Don't add a pytest wrapper for this `.sh` script — it is a manual test by design (header L33). The CI safety net is S2. (Gotcha #6.)
- ❌ Don't grep the systemd journal — this test launches the daemon directly (not via systemctl), so the lines are in `$WORK/daemon.log`, not journald. (Gotcha #7.)
- ❌ Don't edit `tests/test_systemd_unit.py` or `launch_daemon.sh` — S2 (in parallel) and S1 own those. S3 owns ONLY `tests/test_idle_and_gpu.sh`. (Gotcha #8.)
- ❌ Don't wrap the `grep -q` in `|| true` — that would mask a real grep error; the `if` already consumes its exit status under `set -e`. (Pattern note.)
- ❌ Don't modify `install.sh` (T2), `README.md`/`ACCEPTANCE.md` (M3), the systemd unit, or `daemon.py`.

---

## Confidence Score

**9/10** for one-pass implementation success. This is a small, surgical, contract-specified edit set to a single test file. Every load-bearing fact is empirically verified against the live repo: S1's exports are present (launch_daemon.sh L71-72, exec L74), the masking line is confirmed at test_idle_and_gpu.sh:206, the ready-wait loop end (~L222) and all other edit sites are located by `grep -n`, the daemon's stderr logging chain (`_setup_logging` → root `StreamHandler` → httpx propagation → `2>&1` → daemon.log) is read in full and explains why the grep works, and the grep target string is verified as a literal prefix of the verbatim bug-report journal lines (TEST_RESULTS.md L25-26). The contract provides copy-ready code for the guard block. The validation gates are all static/runnable (bash -n, grep structural checks, scope checks) and correctly acknowledge the test cannot run in CI. The −1 is for two residual risks the implementer must honor: (1) the grep is most reliable on a host WITH network (the network-down + regressed-wrapper case relies on the existing ready-wait timeout as a backstop — acceptable but worth knowing), and (2) S2 is running in parallel, so the implementer must hold the scope boundary strictly (edit ONLY test_idle_and_gpu.sh) to avoid a collision — the L4 gates enforce this.
