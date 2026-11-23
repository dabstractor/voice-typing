# PRP — P1.M1.T2.S1: Merge `fix/ydotoold-datagram` onto main

## Goal

**Feature Goal**: Land the known ydotoold socket fix on main via a **normal reviewable merge** (no squash): branch `fix/ydotoold-datagram` is a single commit (`33321c6`, "fix(ydotoold_client): open SOCK_DGRAM — ydotoold's socket is a datagram socket") on merge-base `f0d8d0a`. It fixes the defect where `ydotoold_client.py` opened `SOCK_STREAM` against ydotoold's `SOCK_DGRAM` socket — EVERY connection since f0d8d0a failed with **Errno 91**, silently degrading to per-burst CLI spawns (56 journal warnings/week). After the merge, the datagram socket path is live and the Errno-91 CLI fallback path goes cold.

**Deliverable**: One merge commit on `main` (`git merge fix/ydotoold-datagram`, default message adjusted per Docs below), bringing in exactly 2 files: the `voice_typing/ydotoold_client.py` `_connect` fix (SOCK_STREAM→SOCK_DGRAM; bug site on main = `ydotoold_client.py:41`) + the new `tests/test_ydotoold_client.py` (11 tests, in-process `FakeYdotoold`). No other files change — verified zero overlap (Part B: `git log f0d8d0a..main -- <branch files>` is EMPTY; main's 39 changed files since f0d8d0a — `.gitignore`, `PRD.md`, `config.toml`, `tools/paste-lab/…` — do not include the branch's two).

**Success Definition**:
- (a) `git merge fix/ydotoold-datagram` completes **clean** (zero conflicts — verified none possible); the merge commit is a real merge (two parents), NOT a squash.
- (b) `timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py tests/test_key_listener.py -q` → all green (the 11 new + existing suites).
- (c) The M1.T1.S2 watch set re-run shows **no new reds** vs the recorded baseline: `timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no` → exactly the recorded `16 failed, 76 passed` (the pre-existing lazy-separator legacy reds — the merge must not perturb them), and the two watch-set (ii) candidates unchanged.
- (d) `grep -n 'SOCK_DGRAM' voice_typing/ydotoold_client.py` hits the `_connect` site (the datagram socket is live); the CLI-fallback code in `typing_backends.py:138-149` is UNTOUCHED (it stays as the cold path — removing/hardening it is T2.S3, not this task).
- (e) `git diff f0d8d0a..HEAD --name-only` limited to the merge's 2 files + whatever S1/S2 already committed; **PRD.md is NOT in the merge's diff** (it can't be — zero overlap; verify and assert).
- (f) No push (local main only, unless the orchestrator directs).

## User Persona

**Target User**: Every user of the ydotool typing path — since f0d8d0a every socket attempt failed (Errno 91) and fell back to spawning the CLI per burst. Post-merge the persistent socket works, cutting process churn and the 56 journal warnings/week.

**Use Case**: `voice-typing` types via ydotool (the wtype fallback or an explicit `output.backend="ydotool"`); post-merge the daemon's `ydotoold_client` connects over SOCK_DGRAM and events flow without CLI spawns.

**Pain Points**: the silent 100% socket failure (PRD §8 Known defects: "EVERY connection since f0d8d0a failed with Errno 91 and degraded to per-burst CLI spawns").

## Why

- **PRD §8 mandates it**: the Known-defects triage says "Fix exists: branch `fix/ydotoold-datagram` (commit 33321c6, 11 tests; packing proven byte-identical to the real CLI by two independent captures). MERGE + add the 6 ms press→release contact gap." This subtask is the MERGE; the 6 ms gap is T2.S2; the journal-noise guard is T2.S3.
- **Zero-risk by construction**: single commit, two files, no overlap with main's changes since the merge-base → `git merge` cannot conflict (Part B: "git-level merge conflict risk: none"). The fix is already proven (11 in-process tests + byte-identical packing evidence).
- **Unblocks T2.S2/S3**: the 6 ms contact gap and the no-fallback-storm guard both build on the datagram path being live on main.
- **Reviewable history**: a normal merge (not squash) keeps the branch's commit message — which carries the defect rationale — visible in `git log`.

## What

Pre-flight (clean tree, baseline in place) → `git merge fix/ydotoold-datagram` (no squash; adjust the message) → run the three affected suites + the watch set → verify the socket fix + scope. No code edits of any kind — the content arrives whole from the branch.

### Success Criteria

- [ ] Pre-flight passes: working tree clean (or only the parallel S1/S2 `tests/G1_BASELINE.md` doc state, committed), branch verified = single commit `33321c6` on merge-base `f0d8d0a`.
- [ ] `git merge fix/ydotoold-datagram` → clean, no conflicts, no editor squat (`-m` message).
- [ ] Merge commit message (Docs: "commit message carries it") states: merge fix/ydotoold-datagram (33321c6): ydotoold_client SOCK_STREAM→SOCK_DGRAM — fixes Errno-91 on every socket connect since f0d8d0a; CLI fallback path goes cold (11 in-process tests; packing byte-identical to real CLI).
- [ ] The 3-suite gate green; the watch-set re-run matches the recorded baseline exactly (`16 failed, 76 passed` — no new reds).
- [ ] `SOCK_DGRAM` live at `_connect`; `typing_backends.py` untouched by the merge.
- [ ] PRD.md / tasks.json / prd_snapshot.md NOT in the merge diff.

## All Needed Context

### Context Completeness Check

_Pass._ The git topology, the exact file set, the zero-overlap proof, the bug site on main, the test gates (with exact recorded numbers), and the S1/S2 baseline contract are all verified below (Part B of the research record + live greps). An agent new to this repo can execute the merge from this PRP alone. Note: several `git diff`/`git log` invocations that enumerate PRD.md are blocked by PRD-PROTECT in this repo — use `-- <path>` scoping or `--name-only` filters that exclude protected paths (Gotcha #4).

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: Part B is the verified git topology: branch tip 33321c6, merge-base f0d8d0a (2026-10-31,
       "Send backspaces over a socket"), the 2-file diff (ydotoold_client.py + NEW
       tests/test_ydotoold_client.py), the zero-overlap proof ("git log f0d8d0a..main -- <those
       files> is EMPTY"; main's 39 changed files exclude them; "merge conflict risk: none"), the
       11 in-process FakeYdotoold tests, and the note that the 6 ms gap is NOT closed by this
       merge (T2.S2).
  critical: "Line ~185: 'merging 33321c6 does NOT close that gap' — do NOT scope-creep the 6 ms
            contact gap or the journal guard into this merge."
  section: "Part B (ydotoold datagram merge analysis)."

- docfile: plan/008_a47116bb2b79/P1M1T1S1/PRP.md
  why: The G1 baseline contract: tests/G1_BASELINE.md records the 15-suite numbers (379P/20F at
        2335a9e); this merge's post-check re-runs the streaming subset and MUST NOT drift it.
- docfile: plan/008_a47116bb2b79/P1M1T1S2/PRP.md
  why: The watch set this task re-runs: combined
        `pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no`
        → exactly `16 failed, 76 passed` (18 legacy lazy-separator reds + the 2 (ii) watch
        candidates). No new reds = the merge is behaviorally inert on streaming.

- file: voice_typing/ydotoold_client.py
  why: The bug site on main — line 41: `s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)`.
        The branch flips it to SOCK_DGRAM. Post-merge grep gate.
- file: voice_typing/typing_backends.py
  why: Lines ~138-149 hold the Errno-91 CLI fallback path that goes COLD (unexercised) once the
        socket works. The code STAYS — T2.S3 adds the journal-noise regression guard around it.
  gotcha: "Do not remove/modify the fallback in this merge — out of scope."
- file: tests/test_ydotoold_client.py   # (arrives WITH the merge — 11 tests, in-process FakeYdotoold)
  why: The branch's proof suite; runs green immediately post-merge.
```

### Current / Desired tree

```bash
# BEFORE: main has ydotoold_client.py:41 SOCK_STREAM (broken); no tests/test_ydotoold_client.py.
# AFTER (merge brings both; nothing else):
voice_typing/ydotoold_client.py      # _connect: SOCK_DGRAM (from 33321c6)
tests/test_ydotoold_client.py        # NEW (from 33321c6): 11 in-process FakeYdotoold tests
# tests/G1_BASELINE.md — S1/S2's doc, NOT touched by the merge (zero overlap).
```

### Known Gotchas

```python
# CRITICAL #1 — CLEAN TREE BEFORE MERGING. S1 (baseline doc) and S2 (classification appendix) run in
# parallel and commit tests/G1_BASELINE.md. git merge refuses/wedges on a dirty tree. Pre-flight:
# `git status --porcelain` must be EMPTY (or only untracked scratch); if S1/S2's doc is mid-flight,
# coordinate — commit/stash anything pending first, THEN merge.

# CRITICAL #2 — NO SQUASH, NO REBASE. A normal `git merge fix/ydotoold-datagram -m "<message>"` —
# two-parent merge commit, branch history preserved (the commit message carries the defect
# rationale). Do not `--squash`, do not cherry-pick (loses the branch identity the PRD cites).

# CRITICAL #3 — DON'T SCOPE-CREEP. The 6 ms press→release contact gap is T2.S2; the journal-noise
# regression guard is T2.S3; touching either in this merge breaks the reviewable-one-change rule and
# T2.S2/S3's baselines. The merge brings EXACTLY 33321c6's two files.

# CRITICAL #4 — PRD-PROTECT BLOCKS BROAD GIT DIFF/LOG. This repo's guard rejects commands whose
# diff/log enumerates PRD.md (a protected component). Scope every git inspection: `--name-only`, or
# `-- voice_typing/ tests/` path-limits. `git merge` itself is fine (zero overlap with PRD.md);
# post-merge, assert PRD.md's absence from the diff via a scoped path-limited invocation.

# CRITICAL #5 — THE WATCH-SET NUMBERS ARE THE GATE. The streaming suites carry 16 pre-existing
# legacy reds (lazy-separator contract). The merge must leave them EXACTLY as recorded
# (`16 failed, 76 passed` combined). Any drift (17F, name changes) = a NEW regression from the
# merge — investigate before committing the merge. (Mechanically impossible — the merge touches no
# streaming code — but the gate proves it.)

# GOTCHA #6 — FULL PATHS + TIMEOUTS (AGENTS.md). `timeout 300 .venv/bin/pytest …` for the 3-suite
# gate (bash-tool timeout ≥360); `timeout 120 /home/dustin/.local/bin/uv run pytest …` for the
# watch set (S2's exact invocation). No ruff/mypy configured. Do NOT run the CUDA/daemon suites
# (test_daemon/test_recorder_host/test_feed_audio/test_cuda_check are contract-excluded).
# GOTCHA #7 — NO PUSH. Local main only; the orchestrator owns push timing.
```

## Implementation Blueprint

### Tasks

```yaml
Task 1: PRE-FLIGHT — topology + clean tree + baseline present
  - git status --porcelain  → empty (CRITICAL #1; coordinate with S1/S2's doc commits).
  - git log --oneline -1 fix/ydotoold-datagram | cat            → 33321c6 (SOCK_DGRAM message).
  - git merge-base main fix/ydotoold-datagram | cat             → f0d8d0a.
  - git diff --stat main...fix/ydotoold-datagram -- voice_typing/ tests/ | tail -3   → the 2 files.
  - test -f tests/G1_BASELINE.md && echo "baseline present (S1)".  (If absent: S1 not landed —
    the watch-set comparison uses plan/.../d3_defects_g1_baseline.md Part A numbers instead.)

Task 2: MERGE — normal two-parent merge, message carries the rationale (CRITICAL #2/#3)
  - git merge fix/ydotoold-datagram -m "Merge fix/ydotoold-datagram (33321c6): ydotoold_client
    SOCK_STREAM -> SOCK_DGRAM — fixes Errno-91 on every socket connect since f0d8d0a (2026-10-31);
    per-burst CLI fallback path goes cold. 11 in-process FakeYdotoold tests; packing proven
    byte-identical to the real CLI (two independent captures). 6 ms contact gap + journal guard
    follow in T2.S2/T2.S3."
  - Expect: "Merge made by the 'ort' strategy", 2 files changed, zero conflicts.

Task 3: GATES — three-suite + watch set + static
  - timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py tests/test_key_listener.py -q
    → all green (11 new + existing). bash-tool timeout ≥360.
  - timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no
    → exactly "16 failed, 76 passed" (CRITICAL #5; compare names vs tests/G1_BASELINE.md S2 table).
  - grep -n "SOCK_DGRAM" voice_typing/ydotoold_client.py | head -2   → the _connect site.
  - git diff HEAD~1..HEAD --name-only -- voice_typing/ tests/ | cat  → exactly the 2 branch files.
  - git diff HEAD~1..HEAD --name-only -- PRD.md | wc -l              → 0 (PRD untouched; CRITICAL #4).

Task 4: REPORT + handoff. No push (GOTCHA #7). Findings → plan/008_a47116bb2b79/architecture (not
  into protected docs). If asked to commit-note: the merge commit IS the record (Docs: "commit
  message carries it").
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S2 (6 ms press→release contact gap): builds on the live datagram path this
  merge lands; its baseline is post-merge HEAD.
DOWNSTREAM — P1.M1.T2.S3 (journal-noise regression guard): guards the now-cold CLI fallback
  (typing_backends.py:138-149 stays; the guard asserts no per-burst fallback storms).
WATCH-SET PROTOCOL (S2): every D3 change re-runs the streaming watch set — this merge is the first
  consumer, proving the protocol end-to-end.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1 post-merge static:
grep -q SOCK_DGRAM voice_typing/ydotoold_client.py && test -f tests/test_ydotoold_client.py && echo "L1 PASS"
git log --oneline -1 | grep -q "Merge fix/ydotoold-datagram" && echo "L1b merge-commit PASS"
# L2 the 3-suite gate:
timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py tests/test_key_listener.py -q 2>&1 | tail -2
# L3 the watch set (must equal the recorded baseline):
timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no 2>&1 | tail -2
#   → "16 failed, 76 passed" exactly.
# L4 scope:
git diff HEAD~1..HEAD --name-only -- voice_typing/ tests/ | cat   # → the 2 branch files only
git diff HEAD~1..HEAD --name-only -- PRD.md | wc -l               # → 0
```

## Final Validation Checklist

- [ ] L1: SOCK_DGRAM live; test file present; merge commit (not squash) on main.
- [ ] L2: 3-suite gate green.
- [ ] L3: watch set exactly `16 failed, 76 passed` — no new reds.
- [ ] L4: merge diff = the 2 branch files; PRD.md untouched; typing_backends.py untouched by the merge.
- [ ] No push; no 6 ms gap / journal-guard scope creep (T2.S2/T2.S3 own them).

## Anti-Patterns

- ❌ Don't squash/cherry-pick — a normal two-parent merge preserves the PRD-cited branch identity (CRITICAL #2).
- ❌ Don't merge on a dirty tree or race S1/S2's doc commit (CRITICAL #1).
- ❌ Don't "improve" the fallback path, add the 6 ms gap, or touch streaming code — reviewable one change (CRITICAL #3).
- ❌ Don't run unscoped `git diff`/`git log` that enumerates PRD.md — PRD-PROTECT blocks it (CRITICAL #4).
- ❌ Don't accept watch-set drift ("16F is probably fine") — exact match is the gate (CRITICAL #5).
- ❌ No bare pytest/python; inner `timeout` + full paths; no CUDA suites; no push (GOTCHA #6/#7).

## Confidence Score

**9.5/10** — a pre-proven, single-commit, zero-overlap merge whose only risk is procedural (dirty tree / parallel doc commits), fully mitigated by the pre-flight; all gates have exact recorded numbers to compare against.
