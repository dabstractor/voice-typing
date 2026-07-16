# PRP — P1.M2.T3.S1: Run full suite + GPU lifecycle + verify acceptance #10, then git commit

## Goal

**Feature Goal**: Close out the lite-mode feature (PRD §4.2ter) with a **clean git commit on `main`**
containing the complete, tested, documented feature. The lite-mode SOURCE is already committed
(`656de1c`/`2d11496`/`172fbf2`); this task (a) runs the FULL pytest suite green (incl. the heavy
`test_feed_audio.py` + the T7 lite tests), (b) runs the GPU lifecycle test (`tests/test_idle_and_gpu.sh`)
and verifies **acceptance #10 against REAL output** (lite ≈ half VRAM; mode-switch roundtrip;
`status`/`state.json` report `mode`; shared graceful drain), (c) confirms no network access at runtime,
then (d) flips `tests/ACCEPTANCE.md` #10 `pending T7 → PASS` and commits the lite-mode changeset.

**Deliverable**: a single new commit on `main` whose `--stat` lists ONLY lite-mode files, after a green
full suite and a GPU-lifecycle run whose real output demonstrates acceptance #10. No source changes;
this is verification + one doc-status flip + the commit.

**Success Definition**:
- (a) `.venv/bin/python -m pytest tests/ -q` → **0 failed** (the T7 lite tests PASS on this GPU box,
  not merely skip).
- (b) `bash tests/test_idle_and_gpu.sh` → `[PASS]` for T6(a/b/c/d), criterion 5 (idle), criterion 6
  (un-armed boot + toggle + unit), criterion 8 (offline), **and the T7 section**: `[PASS] T7
  mode-switch: toggle-lite -> mode: lite`, `[PASS] T7 VRAM≈half: lite < normal`, `[PASS] T7 disarm`,
  `[PASS] T7 mode-switch: toggle -> mode: normal`, `[PASS] T7 status: mode: normal`.
- (c) Criterion-8 grep: daemon.log has ZERO `HTTP Request: GET https://huggingface.co` lines (models
  cached; offline at runtime via `launch_daemon.sh` exports).
- (d) `tests/ACCEPTANCE.md` `| 10 |` row flipped `pending T7 → PASS` with the real T7 VRAM + mode-switch
  evidence pasted; no other ACCEPTANCE row / README touched by this task.
- (e) `git commit -m 'Add lite mode: single-small-model quick dictation (PRD §4.2ter)'` on `main`;
  `git show --stat HEAD` lists ONLY lite-mode files; `PRD.md`, `plan/.../tasks.json`, and `plan/` PRP
  dirs are **NOT** in the commit (left unstaged/untracked).

## User Persona

Not applicable (internal finalization + release commit). Beneficiaries: the maintainer (a clean,
verifiable commit on `main`) and the acceptance record (`tests/ACCEPTANCE.md` reflects real #10 PASS).

## Why

- **#10 is the lite feature's definition-of-done** (PRD §7 #10). Until it is demonstrated against REAL
  output (not "pending T7"), the feature is unfinished. This task runs the GPU/T7 evidence and flips
  the record to PASS.
- **A clean, scoped commit is the release artifact.** The incremental lite commits already landed the
  source; this finalizes the docs/tests/acceptance in one verifiable commit on `main`, with the full
  suite green as the safety net.
- **Staging discipline protects the contract's invariants** — `PRD.md` must never be modified/committed
  and `tasks.json`/`plan/` are orchestrator-owned. An explicit allowlist (no `git add -A`) is the only
  safe path.

## What

An ordered verification→commit runbook (no source edits):
1. Preflight: stop the live daemon; ensure WAV assets exist.
2. Full pytest suite (incl. heavy `test_feed_audio.py` + T7 lite tests) → green.
3. GPU lifecycle test (`tests/test_idle_and_gpu.sh`, quiet room) → all `[PASS]` incl. T7 + criterion-8.
4. Capture the `=== ACCEPTANCE EVIDENCE ===` block (T7 normal-vs-lite VRAM numbers + mode-switch PASS).
5. Flip `tests/ACCEPTANCE.md` `| 10 |` `pending T7 → PASS` with the real evidence.
6. `git status --porcelain` RE-VERIFY; stage ONLY the lite-mode allowlist; verify the staged set; commit on `main`.

### Success Criteria

- [ ] `.venv/bin/python -m pytest tests/ -q` → `0 failed`.
- [ ] `bash tests/test_idle_and_gpu.sh` → T6(a/b/c/d), criterion 5/6/8, and T7 all `[PASS]`.
- [ ] T7 evidence shows `lite-armed VRAM < normal-armed VRAM` (≈ half; the large model never loads).
- [ ] No-network confirmed (criterion-8 grep = 0 hits, OR direct `grep -c … <daemon.log>` = 0).
- [ ] `tests/ACCEPTANCE.md` `| 10 |` row status = `PASS` with real evidence; README untouched.
- [ ] New commit on `main` with the contract message; `git show --stat HEAD` lists ONLY lite-mode files.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo can run this from the PRP + the two research notes. The decisive
facts are verified live: the current git changeset (incl. the `PRD.md`/`tasks.json` exclusions), the
exact GPU-test preconditions + the exact `[PASS]` lines it emits for acceptance #10, the evidence-block
fields (T7 normal/lite VRAM), the WAV-build prereq, the full-path invariant, and the safe staging +
post-stage verification command sequence.

### Documentation & References

```yaml
# MUST READ — the full runbook: git state, GPU-test behavior/output, #10 verification matrix, the flip,
# the no-network proof, the plan/001 do-not-touch note, the parallel-context (T2.S1) contract.
- docfile: plan/004_607e9cca32b7/P1M2T3S1/research/finalization_runbook.md
  why: "§1 the LIVE git changeset (what's committed-clean vs to-stage vs EXCLUDE). §2 the GPU test's
        preconditions (stop daemon; quiet room) + every [PASS]/[FAIL] line + the T7 steps (575-700) +
        the evidence-block fields (745-762: T7_NORMAL_VRAM, T7_LITE_VRAM). §3 the full-suite prereqs
        (build WAVs; stop daemon; .venv/bin/python). §4 the #10 clause→evidence matrix. §5 no-network.
        §6 the ACCEPTANCE #10 flip. §7 do-not-touch plan/001. §8 T2.S1 outputs to consume."
  section: "ALL (§0–§8)."

# MUST READ — the staging allowlist + the forbidden `git add -A`, the EXCLUSIONS, the verification cmd.
- docfile: plan/004_607e9cca32b7/P1M2T3S1/research/git_staging_allowlist.md
  why: "§1 the allowlist (config.toml, hypr-binds.conf, voice_typing/*.py, tests/*.py, README.md,
        tests/ACCEPTANCE.md). §2 the EXCLUSIONS (PRD.md, tasks.json, plan/ PRPs, plan/001). §3 the
        exact safe staging + `git diff --cached --name-only` verification + commit + post-commit check."
  critical: "NEVER `git add -A`/`git add .` — it sweeps PRD.md + tasks.json + plan/ into the commit.
             Use explicit file args; verify the staged set before committing."

# MUST READ — the GPU test being driven (its preflight, T7 section, evidence block).
- file: tests/test_idle_and_gpu.sh
  why: "Lines 575-700 = the T7 section (acceptance #10 evidence: toggle-lite→mode:lite, VRAM≈half,
        disarm, toggle→mode:normal, status). Lines 745-762 = the === ACCEPTANCE EVIDENCE === block
        (prints T7 normal-armed + lite-armed VRAM). Lines 382 + 116 = PREFLIGHT refusal if a daemon
        is active. Line 573 = criterion-8 [PASS] (no-network). Heavy (~5-8 min); needs GPU + quiet room."
  pattern: "Read its stdout: every T6/T7/criterion prints [PASS]/[FAIL]; the fenced evidence block at
            the end is the real output to paste into ACCEPTANCE.md #10."
  gotcha: "PREFLIGHT refuses if `voicectl status` answers OR the unit is active — run
           `systemctl --user stop voice-typing` first. T4 listens to AMBIENT silence for 120 s → run in
           a QUIET room or criterion 5 false-fails. Full paths: /usr/bin/tmux, /usr/bin/nvidia-smi."

# MUST READ — the heavy pytest file (its skip-guards + the T7 lite tests added by T1.S1).
- file: tests/test_feed_audio.py
  why: "The lite tests (test_lite_feed_audio_utt_simple: rec.use_main_model_for_realtime is True +
        _token_overlap >= 0.70; test_lite_latency_lower_than_normal: lite_ms < normal_ms) are CUDA-gated
        and PASS on this GPU box (they skip on CPU/no-WAVs). It builds the recorder DIRECTLY (no daemon)
        → the daemon 'voice-typing latency:' log never fires; latency is measured directly."
  gotcha: "Needs tests/out/utt_simple.wav (build via tests/make_test_audio.sh if absent). Stop the live
           daemon before running (GPU contention)."

# SHOULD READ — the acceptance record being flipped.
- file: tests/ACCEPTANCE.md
  why: "P1.M2.T2.S1 (parallel docs task) ADDS the | 10 | row marked 'pending T7' + fixes the intro
        '1-8 -> 1-10'. THIS task flips | 10 | status 'pending T7' -> 'PASS' and pastes the real T7/GPU
        evidence. Re-verify the exact | 10 | row text against the LIVE file before editing (T2.S1
        authored it). Do NOT touch any other row or README."
  critical: "Flip the status cell ONLY; do not rewrite the criterion text. The evidence = the real
             T7 VRAM numbers + 'mode-switch roundtrip PASS' from this run's GPU-test output."

# MUST READ — the invariants (full paths; drain is shared/out-of-scope; daemon stays CUDA-free).
- docfile: plan/004_607e9cca32b7/architecture/system_context.md
  why: "§1: the graceful drain (_request_stop/_begin_drain/_complete_drain) is ALREADY IMPLEMENTED and
        OUT OF SCOPE (commits 5f32d74/495bdd2/5c83567) — applies identically in lite mode, so #10's
        'both modes honor the drain' is satisfied by shared machinery (no separate lite-drain test).
        §4 invariants: #3 use_main_model_for_realtime=True ⇒ ONE model; #4 on_final gate + drain apply
        identically in lite; #5 ALWAYS full paths (.venv/bin/python, /home/dustin/.local/bin/uv,
        /usr/bin/tmux)."

# CONTEXT — the parallel docs task (consume its outputs; flip its #10 row).
- docfile: plan/004_607e9cca32b7/P1M2T2S1/PRP.md
  why: "T2.S1 lands README ## Lite mode + lifecycle note, and ACCEPTANCE.md #9/#10 rows (#10 = 'pending
        T7') + the 1-8->1-10 / evidence-header fixes. THIS task (T3.S1) flips #10 'pending T7' -> 'PASS'
        and commits the whole lite changeset (incl. T2.S1's edits). Non-overlapping: T2.S1 ADDS the row;
        T3.S1 flips its STATUS only."
  critical: "Precondition: when THIS task runs, README has '## Lite mode' and ACCEPTANCE.md has a
             '| 10 |' row. If either is missing, the docs task isn't done — flag it (cannot commit
             incomplete docs). RE-VERIFY via grep before committing."

# CONTEXT — the PRD acceptance spec (the bar to demonstrate).
- docfile: PRD.md   # §7 #10 + §6 T7 + §4.2ter + §4.2bis
  why: "§7 #10 = the lite definition-of-done (toggle-lite uses ONLY lite_model; large never loads; ~half
        VRAM; toggle normal; one bounded reload; status+state.json report mode; both honor drain). §6 T7
        = the lite test spec. Match these against the REAL GPU-test output."
```

### Current Codebase tree (relevant slice — no source edits; verify + commit only)

```bash
/home/dustin/projects/voice-typing/
├── README.md                 # (P1.M2.T2.S1: +## Lite mode +lifecycle note) — STAGE
├── hypr-binds.conf           # (SUPER+ALT+F) — STAGE
├── config.toml               # tracked, likely CLEAN (committed) — allowlist no-op
├── voice_typing/*.py         # tracked, CLEAN (committed in 656de1c/2d11496/172fbf2) — allowlist no-op
├── tests/
│   ├── test_feed_audio.py    # (P1.M2.T1.S1: +lite_recorder +2 lite tests) — STAGE
│   ├── test_idle_and_gpu.sh  # (P1.M2.T1.S1: +T7 section) — STAGE + RUN
│   └── ACCEPTANCE.md         # (P1.M2.T2.S1: +#9/#10 rows) THEN this task flips #10 → PASS — STAGE
├── PRD.md                    # EXCLUDE (do NOT stage/commit)
└── plan/004_607e9cca32b7/{tasks.json, P1M2T1S1/, P1M2T2S1/, P1M2T3S1/}  # EXCLUDE (orchestrator/plan)
```

### Desired Codebase tree (what this task produces)

```bash
# ONE new commit on main:
git show --stat HEAD   # → hypr-binds.conf, config.toml(no-op), README.md, tests/ACCEPTANCE.md,
                       #   tests/test_feed_audio.py, tests/test_idle_and_gpu.sh, voice_typing/*(no-op)
# No source changes. tests/ACCEPTANCE.md #10 = PASS (real evidence). PRD.md + tasks.json left unstaged.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — FULL PATHS in EVERY bash command (system_context §4 #5; PRD §2). zsh aliases
#   python3→uv run, pip, tmux. Use: .venv/bin/python, /home/dustin/.local/bin/uv, /usr/bin/tmux,
#   /usr/bin/nvidia-smi, /usr/bin/systemctl (or `systemctl --user`). NEVER bare python/pytest/uv/tmux.

# CRITICAL #2 — GPU TEST PREFLIGHT: tests/test_idle_and_gpu.sh REFUSES if a voice-typing daemon is
#   already running (voicectl status answers OR the unit is active). Run `systemctl --user stop
#   voice-typing` FIRST. Its T4 listens to AMBIENT silence on the real mic for 120 s → run in a QUIET
#   room or criterion 5 (no-hallucination) false-fails. ~5-8 min; needs GPU + systemd user stack.

# CRITICAL #3 — NEVER `git add -A` / `git add .`. PRD.md IS modified in the working tree but the
#   contract FORBIDS committing it; tasks.json + plan/ PRPs are orchestrator-owned. Use EXPLICIT file
#   args from the allowlist, then `git diff --cached --name-only` to verify NO exclusion slipped in.

# CRITICAL #4 — DO NOT touch plan/001_be48c74bc590/ (the prior bugfix plan). Do NOT add/commit/modify
#   anything under it. This commit is the lite-mode feature files only.

# CRITICAL #5 — test_feed_audio.py builds the recorder DIRECTLY (no daemon) → the daemon's
#   'voice-typing latency:' log NEVER fires in pytest. The T7 latency test measures last-speech→final
#   directly. Do NOT grep the daemon log for pytest latency.

# CRITICAL #6 — The graceful drain (#10 'both modes honor the drain') is SHARED machinery
#   (_request_stop/_begin_drain/_complete_drain), already implemented + OUT OF SCOPE (system_context §1).
#   Do NOT add a separate lite-drain test (duplicates proven shared behavior). An OPTIONAL manual smoke
#   (arm lite → utter → voicectl stop mid-utterance → final types) is fine but NOT a hard gate.

# CRITICAL #7 — ACCEPTANCE.md #10 flip: flip the STATUS cell 'pending T7' → 'PASS' and fill evidence
#   with REAL output. Re-verify the exact | 10 | row text against the LIVE file (T2.S1 authored it).
#   Do NOT rewrite the criterion text or touch other rows / README.

# CRITICAL #8 — pytest is the runner (NO ruff/mypy in this repo). The "full suite" INCLUDES the heavy
#   test_feed_audio.py — ensure WAVs exist (`ls tests/out/utt_simple.wav || bash tests/make_test_audio.sh`)
#   and stop the live daemon before running (GPU contention).
```

## Implementation Blueprint

### Data models and structure

None. No source/schema/config change. The "data" is the real GPU-test output (T7 VRAM numbers +
mode-switch PASS lines) captured into `tests/ACCEPTANCE.md` #10, and the git changeset staged + committed.

### Implementation Tasks (ordered by dependencies — a verification→commit runbook)

```yaml
Task 0: PREFLIGHT
  - Stop any live daemon (frees GPU; satisfies the GPU-test preflight): systemctl --user stop voice-typing
  - Ensure WAV assets for the heavy pytest file:
      ls tests/out/utt_simple.wav 2>/dev/null || bash tests/make_test_audio.sh
  - Confirm branch: git branch --show-current  # MUST be main
  - Re-verify the lite docs landed (P1.M2.T2.S1 precondition):
      grep -q '^## Lite mode' README.md && grep -q '^| 10 ' tests/ACCEPTANCE.md
      # If either is missing → docs task incomplete; flag (cannot commit incomplete docs) and stop.

Task 1: FULL PYTEST SUITE (acceptance gate a) — run AFTER stopping the daemon
  - CMD: .venv/bin/python -m pytest tests/ -q
  - INCLUDES tests/test_feed_audio.py (heavy, real models) + the T7 lite tests
    (test_lite_feed_audio_utt_simple, test_lite_latency_lower_than_normal) — they PASS on this GPU box.
  - GATE: 0 failed. (Skips only for legitimately-gated tests; the lite tests should RUN+PASS on GPU.)

Task 2: GPU LIFECYCLE + ACCEPTANCE #10 (gate b) — quiet room; daemon stopped
  - CMD: bash tests/test_idle_and_gpu.sh 2>&1 | tee /tmp/p1m2t3s1_idle_gpu.log
  - Capture the fenced === ACCEPTANCE EVIDENCE (...) === block (lines 745-762) — esp.
    'T7 normal-armed VRAM (MiB)' + 'T7 lite-armed VRAM (MiB)' (lite < normal = the ~half proof).
  - GATE: every one of these lines is [PASS] (grep the log):
      T6 (a)/(b)/(c)/(d) lifecycle ; criterion 5 (idle) ; criterion 6 (un-armed boot/toggle/unit) ;
      criterion 8 (no network) ;
      '[PASS] T7 mode-switch: toggle-lite -> mode: lite' ;
      '[PASS] T7 VRAM≈half: lite … < normal …'  (a [WARN] here is non-fatal but investigate;
        if lite >= normal, the one-model invariant may have regressed — check before committing) ;
      '[PASS] T7 disarm' ; '[PASS] T7 mode-switch: toggle -> mode: normal' ; '[PASS] T7 status: mode: normal'.
  - On any [FAIL]: the script prints the daemon.log tail; debug the ROOT CAUSE (do NOT weaken assertions;
    per the script's own notes a T6(d-gone) FAIL is a PRODUCTION bug, not a test bug).

Task 3: NO-NETWORK CONFIRMATION (gate c)
  - Already proven by Task 2's criterion-8 [PASS] line (daemon.log ZERO 'HTTP Request: GET
    https://huggingface.co' — production path, non-circular).
  - Optional direct corroboration: grep -c 'HTTP Request: GET https://huggingface.co' <daemon.log> → 0.

Task 4: FLIP tests/ACCEPTANCE.md #10  pending T7 → PASS  (the ONE doc edit this task owns)
  - grep -n '^| 10 ' tests/ACCEPTANCE.md  → locate the row (P1.M2.T2.S1 added it as 'pending T7').
  - EDIT: change the status cell 'pending T7' → 'PASS'; set the evidence cell to the REAL T7/GPU output
    (lite-armed VRAM < normal-armed VRAM numbers from the evidence block + 'mode-switch roundtrip PASS
    (toggle-lite→mode:lite; toggle→mode:normal; status mode: normal)' + cite 'bash tests/test_idle_and_gpu.sh'
    + '.venv/bin/python -m pytest tests/test_feed_audio.py -k lite -v').
  - Re-verify the exact | 10 | oldText against the LIVE file before editing (T2.S1 authored it).
  - Do NOT touch any other row, the README, or the evidence BLOCK beyond #10's evidence cell.

Task 5: STAGE + COMMIT (gate d) — explicit allowlist; verify staged set; commit on main
  - RE-VERIFY the uncommitted set: git status --porcelain
  - Stage ONLY the allowlist (EXPLICIT file args; NEVER git add -A/.):
      git add hypr-binds.conf config.toml README.md tests/ACCEPTANCE.md \
              tests/test_feed_audio.py tests/test_idle_and_gpu.sh \
              voice_typing/daemon.py voice_typing/config.py voice_typing/ctl.py \
              voice_typing/feedback.py voice_typing/status.sh voice_typing/recorder_host.py
  - VERIFY staged set: git diff --cached --name-only
      MUST be a subset of the allowlist; MUST NOT list PRD.md, tasks.json, or anything under plan/.
      If an exclusion slipped in: git restore --staged <file>; re-verify.
  - COMMIT: git commit -m 'Add lite mode: single-small-model quick dictation (PRD §4.2ter)'
  - POST-COMMIT: git show --stat HEAD  (confirm only lite-mode files); git log --oneline -1 (on main);
      git status --porcelain  (PRD.md + tasks.json remain unstaged; plan/ untracked — EXPECTED).
```

### Implementation Patterns & Key Details

```bash
# PATTERN — drive the GPU test, capture real output, paste #10 evidence, then commit. Full paths always.

# 1. Full suite (GPU; daemon stopped):
systemctl --user stop voice-typing
ls tests/out/utt_simple.wav 2>/dev/null || bash tests/make_test_audio.sh
.venv/bin/python -m pytest tests/ -q                      # → 0 failed (lite tests PASS on GPU)

# 2. GPU lifecycle + acceptance #10 (quiet room):
bash tests/test_idle_and_gpu.sh 2>&1 | tee /tmp/p1m2t3s1_idle_gpu.log
grep -E '\[PASS\]|\[FAIL\]|T7|criterion 8|ACCEPTANCE EVIDENCE' /tmp/p1m2t3s1_idle_gpu.log | head -40
#   → every T6/T7/criterion line is [PASS]; the evidence block lists T7 normal-vs-lite VRAM (lite<half).

# 3. No-network: criterion-8 [PASS] (ZERO HF HTTP lines). (Optional direct grep on the daemon.log = 0.)

# 4. Flip ACCEPTANCE #10 (re-verify the exact live row text first):
#    | 10 | Lite mode (§4.2ter): … | pending T7 | … |   →   | 10 | … | PASS | <real T7 VRAM+mode-switch evidence> |

# 5. Stage the allowlist (explicit args) + verify + commit:
git add hypr-binds.conf config.toml README.md tests/ACCEPTANCE.md tests/test_feed_audio.py \
        tests/test_idle_and_gpu.sh voice_typing/daemon.py voice_typing/config.py voice_typing/ctl.py \
        voice_typing/feedback.py voice_typing/status.sh voice_typing/recorder_host.py
git diff --cached --name-only          # → ONLY lite-mode files; NO PRD.md/tasks.json/plan/
git commit -m 'Add lite mode: single-small-model quick dictation (PRD §4.2ter)'
git show --stat HEAD ; git log --oneline -1
```

### Integration Points

```yaml
CONSUMED (already landed — verify, don't rebuild):
  - lite source: voice_typing/{daemon,config,ctl,feedback,status,recorder_host}.py + config.toml
    (committed 656de1c/2d11496/172fbf2). hypr-binds.conf SUPER+ALT+F (working-tree mod).
  - tests: tests/test_feed_audio.py (lite tests), tests/test_idle_and_gpu.sh (T7 section) — P1.M2.T1.S1.
  - docs: README.md ## Lite mode + lifecycle note; tests/ACCEPTANCE.md #9/#10 rows (#10 'pending T7')
    + 1-8→1-10 fixes — P1.M2.T2.S1.
PRODUCED (this task):
  - tests/ACCEPTANCE.md #10 flipped 'pending T7' → 'PASS' with real evidence.
  - ONE new commit on main: the complete lite-mode changeset (docs + tests + the flip), full suite green,
    acceptance #10 demonstrated by real output.
DO NOT TOUCH:
  - PRD.md (leave unstaged), **/tasks.json, **/prd_snapshot.md, .gitignore, plan/ (PRPs/dirs),
    plan/001_be48c74bc590/ (prior plan), pyproject.toml, uv.lock. No source edits, no new deps.
```

## Validation Loop

> Full paths in every command (CRITICAL #1). Run from `/home/dustin/projects/voice-typing`. pytest is the
> runner (NO ruff/mypy). The GPU test needs the daemon stopped + a quiet room (CRITICAL #2).

### Level 1: Full pytest suite (acceptance gate a)

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true       # free GPU; GPU-test preflight needs this
ls tests/out/utt_simple.wav 2>/dev/null || bash tests/make_test_audio.sh   # WAV prereq for the heavy file
.venv/bin/python -m pytest tests/ -q
# Expected: 0 failed. The lite tests (test_lite_feed_audio_utt_simple: use_main_model_for_realtime is
#   True + _token_overlap >= 0.70; test_lite_latency_lower_than_normal: lite_ms < normal_ms) PASS on GPU.
#   If a lite test FAILS: it's a real regression (one-model invariant / accuracy / latency) — debug it
#   BEFORE committing; do not skip. (If it SKIPs only because CUDA/WAVs absent on a non-GPU box, that's
#   expected elsewhere — but THIS box has CUDA, so they must RUN+PASS.)
```

### Level 2: GPU lifecycle + acceptance #10 (gate b) + no-network (gate c)

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true       # PREFLIGHT: script refuses if a daemon is active
bash tests/test_idle_and_gpu.sh 2>&1 | tee /tmp/p1m2t3s1_idle_gpu.log
# Expected (quiet room, GPU): every line below is [PASS]:
grep -E '\[PASS\]|\[FAIL\]' /tmp/p1m2t3s1_idle_gpu.log | grep -E 'T6|criterion 5|criterion 6|criterion 8|T7'
#   T6(a) boot absent; criterion 8 no-network; criterion 6 un-armed boot/toggle/unit; T6(b) armed;
#   criterion 5 idle (no finals/no crash/CPU<25%); T6(c) disarmed resident; T7 mode-switch toggle-lite→lite;
#   T7 VRAM≈half (lite<normal); T7 disarm; T7 toggle→normal; T7 status mode:normal; T6(d) gone+reload.
# Acceptance #10 real evidence (the ~half-VRAM proof):
grep -E 'T7 normal-armed VRAM|T7 lite-armed VRAM' /tmp/p1m2t3s1_idle_gpu.log
#   → T7 lite-armed VRAM (MiB) < T7 normal-armed VRAM (MiB). Paste these into ACCEPTANCE #10.
# No-network (gate c): criterion-8 [PASS] = ZERO 'HTTP Request: GET https://huggingface.co' (offline via
#   launch_daemon.sh, non-circular).
# On any [FAIL]: read the daemon.log tail the script prints; fix the ROOT CAUSE (a T6(d-gone) FAIL is a
#   PRODUCTION bug per the script notes, not a test bug — do NOT weaken the assertion).
```

### Level 3: ACCEPTANCE #10 flip (gate d, doc side)

```bash
cd /home/dustin/projects/voice-typing
grep -n '^| 10 ' tests/ACCEPTANCE.md          # locate the row (P1.M2.T2.S1 left it 'pending T7')
# EDIT the row: status cell 'pending T7' -> 'PASS'; evidence cell -> real T7 VRAM (lite<normal) +
#   'mode-switch roundtrip PASS' + cite the commands (bash tests/test_idle_and_gpu.sh; pytest -k lite).
# Re-verify the exact | 10 | oldText against the LIVE file first (T2.S1 authored it).
grep -n '| 10 ' tests/ACCEPTANCE.md           # confirm status is now PASS
grep -q '^## Lite mode' README.md && echo "README lite section present (T2.S1)" || echo "WARN: README lite section missing"
```

### Level 4: Stage + commit + post-commit verification (gate d, the deliverable)

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain                        # RE-VERIFY the exact uncommitted set
git add hypr-binds.conf config.toml README.md tests/ACCEPTANCE.md \
        tests/test_feed_audio.py tests/test_idle_and_gpu.sh \
        voice_typing/daemon.py voice_typing/config.py voice_typing/ctl.py \
        voice_typing/feedback.py voice_typing/status.sh voice_typing/recorder_host.py
git diff --cached --name-only                 # MUST list ONLY lite-mode files (no PRD.md/tasks.json/plan/)
git commit -m 'Add lite mode: single-small-model quick dictation (PRD §4.2ter)'
git show --stat HEAD                          # confirm the commit's file list
git log --oneline -1                          # confirm on main
git status --porcelain                        # PRD.md + tasks.json remain UNSTAGED (expected); plan/ untracked
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1: `.venv/bin/python -m pytest tests/ -q` → `0 failed` (lite tests PASS on GPU).
- [ ] Level 2: `bash tests/test_idle_and_gpu.sh` → T6(a/b/c/d), criterion 5/6/8, and T7 all `[PASS]`.
- [ ] Level 2: T7 `lite-armed VRAM < normal-armed VRAM` (the ~half proof; large model never loads).
- [ ] Level 2/c: no-network confirmed (criterion-8 [PASS]; ZERO HF HTTP lines).
- [ ] Level 4: `git diff --cached --name-only` (pre-commit) lists ONLY lite-mode files.

### Feature (Acceptance #10) Validation
- [ ] `toggle-lite` → `mode: lite` in `voicectl status` (T7 step 2 [PASS]).
- [ ] nvidia-smi daemon-tree PID shows ~half VRAM in lite vs normal (T7 VRAM≈half [PASS] + evidence numbers).
- [ ] `toggle` (switch) → one bounded reload → `mode: normal` (T7 step 4 [PASS], 30 s ceiling).
- [ ] `status` + `state.json` report `mode` (T7 step 5 [PASS]; feedback.py set_mode).
- [ ] Both modes honor the graceful drain — shared `_request_stop` machinery (out of scope; identical in lite).
- [ ] `tests/ACCEPTANCE.md` `| 10 |` status = `PASS` with real evidence.

### Code Quality / Scope Validation
- [ ] No source edits (config.toml/voice_typing/*.py untouched — verified clean via `git status`).
- [ ] Only `tests/ACCEPTANCE.md` doc-edit by this task (the #10 flip); README untouched (P1.M2.T2.S1 owns it).
- [ ] New commit on `main` with the exact contract message.
- [ ] `git show --stat HEAD` lists ONLY: hypr-binds.conf, config.toml(no-op), README.md, tests/ACCEPTANCE.md,
      tests/test_feed_audio.py, tests/test_idle_and_gpu.sh, voice_typing/*(no-op).

### Forbidden-Operations Compliance
- [ ] `PRD.md` NOT staged (left unstaged working-tree mod).
- [ ] `**/tasks.json`, `**/prd_snapshot.md`, `.gitignore` NOT staged.
- [ ] Nothing under `plan/` (PRP/research dirs) or `plan/001_be48c74bc590/` staged/touched.
- [ ] No `git add -A` / `git add .` used (explicit allowlist only).

---

## Anti-Patterns to Avoid

- ❌ Don't `git add -A` / `git add .` — it sweeps `PRD.md` (never commit) + `tasks.json` + `plan/` into the commit. Use explicit file args from the allowlist; verify `git diff --cached --name-only` first.
- ❌ Don't commit `PRD.md` (contract: never modify/commit). Don't touch `tasks.json`/`prd_snapshot.md`/`.gitignore`/`plan/`/`plan/001_*`.
- ❌ Don't skip the heavy GPU test (Level 2) — acceptance #10's ~half-VRAM + mode-switch evidence comes ONLY from its REAL output. "It should work" is not verification.
- ❌ Don't pre-claim ACCEPTANCE #10 `PASS` before the GPU test's T7 lines are `[PASS]` — flip the row to PASS with the REAL evidence only after the run.
- ❌ Don't weaken a `[FAIL]` assertion to force green — a T6(d-gone)/T7 FAIL is a production regression; debug the root cause (the script prints the daemon.log tail + diagnostics).
- ❌ Don't run the GPU test while a daemon is active — PREFLIGHT refuses; stop it first. Don't run T4 in a noisy room — ambient speech false-fails criterion 5.
- ❌ Don't use bare `python`/`pytest`/`uv`/`tmux` (zsh aliases). Full paths always.
- ❌ Don't grep the daemon log for pytest latency — test_feed_audio builds the recorder directly (no daemon); the latency test measures last-speech→final directly.
- ❌ Don't add a separate lite-drain test — the drain is shared/out-of-scope machinery (system_context §1); an optional manual smoke is fine, not a gate.
- ❌ Don't rewrite the README or other ACCEPTANCE rows — this task flips ONLY the `| 10 |` status cell + its evidence cell (P1.M2.T2.S1 owns the rest).
- ❌ Don't touch `pyproject.toml`/`uv.lock` or add deps — no source/dependency changes in this finalization task.

---

## Confidence Score

**9/10** for one-pass success. This is a verification + commit runbook with every fact verified live:
the exact git changeset (incl. the `PRD.md`/`tasks.json` exclusions), the GPU test's preconditions and
the exact `[PASS]` lines + evidence-block fields it emits for acceptance #10, the WAV-build prereq, the
full-path invariant, the safe explicit staging + post-stage verification, and the single #10 status flip.
Residual risk (−1): the heavy GPU test can be environment-sensitive (a noisy room false-fails T4; GPU
variance could make the best-effort T7 VRAM≈half print `[WARN]` — non-fatal but should be investigated
before committing if lite ≥ normal). Both are flagged as CRITICAL gotchas with concrete handling.
