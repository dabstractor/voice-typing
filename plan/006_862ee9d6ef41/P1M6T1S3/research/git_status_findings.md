# git status research — P1.M6.T1.S3 (commit readiness)

**Date captured:** (run-time)
**Purpose:** Pre-verify the LIVE git state so the PRP's contract checks resolve deterministically. The
implementer MUST re-confirm these live (numbers drift) — this is the starting evidence, not gospel.

---

## 0. The contract's RESEARCH NOTE is STALE — correct it in the report

The work-item contract's RESEARCH NOTE says: *"The repo is on branch main, **1 commit ahead** of
origin/main … The stash entries (**0f314c8, 64d3a04**) suggest WIP work."*

**LIVE reality (re-confirmed):**
- Branch `main` is **28 commits ahead** of `origin/main` (not 1). Those 28 ARE the P1 verification cycle.
- There is **ONE** stash: `stash@{0}: WIP on main: c01b0e9 Formalize subprocess architecture and service wiring`.
  The commits `0f314c8` / `64d3a04` the contract names **no longer exist** (the stash was re-created on
  top of `c01b0e9`). `git rev-parse 0f314c8` / `64d3a04` → "unknown revision."

**Implication for the report:** cite the LIVE numbers; explicitly note the contract note's staleness so a
future reader isn't misled. Do NOT trust the contract's commit count or stash IDs.

---

## 1. Branch position — the 28 ahead commits ARE the verification cycle

`git log --oneline origin/main..HEAD` (28 commits). Representative sample (most-recent first):

```
77fdc10 Verify README.md PRD §7 #7 documentation compliance
2d1357a Verify acceptance gate evidence compilation
361111a Verify T4 idle stability test coverage
9979df8 Verify T6 GPU lifecycle script compliance
42d8f31 Verify T3 E2E virtual mic script audit
faf1663 Verify T1 offline pipeline test coverage
d720df5 Verify daemon mocked-CUDA unit test execution
afaaa05 Verify pure-Python unit test execution
… (P1.M1–P1.M5 verification + "Advance … to Ready" commits) …
```

**Critical pattern:** `tasks.json` is modified in **every one** of these 28 commits
(`git log origin/main..HEAD -- plan/006_862ee9d6ef41/tasks.json` → 28 hits). The orchestrator commits
`tasks.json` **incrementally, alongside each work item's plan artifacts** (e.g. commit `77fdc10` adds
`P1M6T1S1/PRP.md` + `P1M6T1S1/gap_readme.md` + `P1M6T1S1/research/…` AND updates `tasks.json`).

**Implication:** `tasks.json` is **orchestrator-owned bookkeeping**. It is FORBIDDEN for this agent to
modify (PRP FORBIDDEN OPERATIONS). The currently-uncommitted `tasks.json` modification is the
orchestrator's in-flight bookkeeping for S2/S3 — it will be committed by the orchestrator when those work
items complete, exactly as it was for all 28 prior commits. **This task does NOT commit `tasks.json`.**

## 2. Uncommitted working tree — the FULL picture

`git status --porcelain --untracked-files=all`:
```
 M plan/006_862ee9d6ef41/tasks.json
?? plan/006_862ee9d6ef41/P1M6T1S2/PRP.md
?? plan/006_862ee9d6ef41/P1M6T1S2/research/stale_refs_audit_findings.md
```

That is the **entire** uncommitted set. Breaking it down:

| Item | What it is | This task's action |
|---|---|---|
| ` M plan/…/tasks.json` | Orchestrator status bookkeeping (in-flight for S2/S3) | **Do NOT commit.** Orchestrator-owned. Will be committed with S2/S3 completion (the 28-commit pattern). |
| `?? plan/…/P1M6T1S2/PRP.md` | **P1.M6.T1.S2** work-in-progress (PRP) | **Do NOT commit.** S2 runs in **PARALLEL** to this task (see parallel_execution_context); its artifacts are not finalized. Plan metadata, not source. |
| `?? plan/…/P1M6T1S2/research/stale_refs_audit_findings.md` | S2 research WIP | **Do NOT commit** (same — S2 parallel WIP). |

**There are ZERO uncommitted source / test / doc / script / config changes.** Every
`voice_typing/*.py`, `tests/*`, `README.md`, `config.toml`, `install.sh`, `systemd/*`, `*.sh`, `*.conf`
change produced by P1.M1–P1.M5 is **already committed** in the 28 ahead-of-origin commits. Contract
check (a) "all source changes from this verification cycle are staged/committed" → **PASS (already
committed)**.

## 3. `.gitignore` coverage — contract check (b)

**Root `.gitignore` (tracked):**
```
# Build artifacts
dist/
build/
*.pyc
__pycache__/
.mypy_cache/
.pytest_cache/
.ruff_cache/
# Dependency directories
node_modules/
venv/
.venv/
# Environment files
.env
# OS-specific files
.DS_Store
# Runtime logs
*.log
# Agent harness artifacts (local scratch)
.pi-subagents/
```

**Nested `tests/out/.gitignore` (tracked):**
```
# Generated test audio (regenerable via tests/make_test_audio.sh) — do not commit.
*
```

Contract-requirement → coverage map:

| Required pattern | Covered? | Where |
|---|---|---|
| `.venv` | ✅ YES | root `.gitignore` → `.venv/` |
| `__pycache__` | ✅ YES | root `.gitignore` → `__pycache__/` |
| `tests/out/*.wav` | ✅ YES | nested `tests/out/.gitignore` → `*` (ignores ALL of `tests/out/`, incl. the 4 fixtures `utt_{simple,paused,punct,multi}.wav`). Verified: `git check-ignore -v tests/out/test.wav` → `tests/out/.gitignore:2:*`. |
| `.pi-subagents` | ✅ YES | root `.gitignore` → `.pi-subagents/` |

**Bonus coverage** (not required, noted for completeness): `dist/`, `build/`, `*.pyc`, `.mypy_cache/`,
`.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `venv/`, `.env`, `.DS_Store`, `*.log`.

`git status --ignored --short` confirms the ignored set actually being ignored at run-time:
`.pi-subagents/`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, `tests/__pycache__/`, `tests/out/`,
`voice_typing/__pycache__/`.

**Contract check (b) → PASS (all four required patterns covered; `tests/out/*.wav` via a deliberate
nested per-directory `.gitignore` with an explanatory comment — a stronger pattern than a root glob
because it also ignores the regenerable fixtures and signals intent).**

## 4. Key-file tracking — contract check (c)

`git ls-files --error-unmatch` → ALL tracked:
- `pyproject.toml` ✅ tracked (committed)
- `uv.lock` ✅ tracked (committed)
- `README.md`, `PRD.md`, `config.toml`, `install.sh`, `.gitignore` ✅ tracked

**Contract check (c) → PASS.**

## 5. Stray debug files — contract check (d)

- Root `ls` scan for `*.log *.out *.tmp *.bak debug scratch core.*` → **NONE**.
- Full-tree untracked scan (`git status --porcelain -uall | grep '^??'` minus the S2 plan WIP) →
  **empty** (the grep exits non-zero = no matches). No stray source files anywhere.
- The 4 `tests/out/*.wav` are present on disk but **correctly git-ignored** (§3) — they are regenerable
  test fixtures (`tests/make_test_audio.sh`), not stray debug files.

**Contract check (d) → PASS (no stray debug/junk files).**

## 6. Stash assessment — contract INPUT (`git stash list`)

`git stash list`:
```
stash@{0}: WIP on main: c01b0e9 Formalize subprocess architecture and service wiring
```

`git stash show --name-status stash@{0}`:
```
A	BUGS.md
```
`git stash show --stat stash@{0}`: `BUGS.md | 412 +++++++ (1 file, 412 insertions)`.

**Classification:** the stash is a **single stashed file: a 412-line `BUGS.md` draft.** This is the
"BUGS.md that was never committed" — the abandoned prior bug-tracking convention.

**Cross-reference with P1.M6.T1.S2** (the stale-reference audit, running in parallel): S2 confirms
`find . -name BUGS.md` → **none** in the working tree, and that **BUGS.md must NOT be created** (it is a
dangling `PRD.md` reference; the convention was replaced by inline `# VT-0NN` source comments +
`tests/ACCEPTANCE.md` + the 17 `gap_*.md` audits). The stashed `BUGS.md` is therefore **stale,
superseded WIP** with **no relationship to the verification cycle**.

**Verdict / recommendation:** the stash should be **dropped** (`git stash drop stash@{0}`) — but
**dropping a stash is destructive and irreversible**, so this task **DOCUMENTS + RECOMMENDS, does NOT
execute** the drop. The report records: (a) the stash exists; (b) its sole content is a superseded
`BUGS.md`; (c) the recommendation to drop it (with the rationale + the S2 cross-reference); (d) that the
final drop is a **human/orchestrator** action (this task does not run `git stash drop`).

## 7. Commit readiness verdict

| Contract question | LIVE answer |
|---|---|
| (a) all source changes from this verification cycle staged/committed? | ✅ **YES** — all source/test/doc/script changes are committed in the 28 ahead-of-origin commits; zero uncommitted source files. |
| (b) `.gitignore` covers `.venv`, `__pycache__`, `tests/out/*.wav`, `.pi-subagents`? | ✅ **YES** — all four (the `tests/out/*.wav` via a deliberate nested `tests/out/.gitignore`). |
| (c) `pyproject.toml` + `uv.lock` committed? | ✅ **YES** — both tracked. |
| (d) no stray debug files? | ✅ **YES** — none. |
| stash check (contract INPUT) | ⚠️ ONE stash: a **superseded `BUGS.md` draft** (c01b0e9). Recommend drop by a human; this task does not drop it. |

**Overall: READY.** The verification cycle's code+doc artifacts are fully committed on `main` (28 commits
ahead of origin). The only uncommitted items are (i) orchestrator-owned `tasks.json` bookkeeping
(committed incrementally by the orchestrator per the 28-commit pattern — FORBIDDEN for this agent) and
(ii) the **parallel** P1.M6.T1.S2 plan WIP (not finalized; plan metadata). **No commit action is required
of this task** — committing a sweep here would (1) violate the `tasks.json` ownership rule, (2) race the
parallel S2 run by committing incomplete plan WIP, and (3) add nothing (the cycle artifacts are already
committed). The final push of the 28 local commits to `origin/main` is a **separate, human/orchestrator**
decision (PRD §7 #7 "everything committed to git" is satisfied on `main`; the criteria do not require a
push).

## 8. What this task actually DOES (scope)

- **WRITE ONE file:** `plan/006_862ee9d6ef41/P1M6T1S3/git_status_final.md` — the commit-readiness
  assessment report.
- **RUN (fast, safe, no AGENTS.md timeout needed):** `git status`, `git log`, `git stash list/show`,
  `git ls-files --error-unmatch`, `git check-ignore`, `find . -name '*.wav'`, root `ls`. Pure read-only
  git + filesystem inspection.
- **DO NOT RUN:** `git add`, `git commit`, `git push`, `git stash drop`, `git reset`, any
  `git ... --amend`. (The orchestrator owns the integration commit + the push; this task assesses, it
  does not mutate.) NO pytest, NO heavy shell script (AGENTS.md) — irrelevant to a git-readiness check.

## 9. Coordination with siblings

- **P1.M6.T1.S1** (README-completeness): **Complete.** Its commit `77fdc10` is in the 28. No conflict.
- **P1.M6.T1.S2** (stale-reference audit): **running in PARALLEL.** Its `P1M6T1S2/` dir is the untracked
  WIP. This task references S2's verdict (BUGS.md absent / must-not-exist) for the stash classification
  but does **not** depend on S2's file existing at run-time — the stash's sole content (`BUGS.md`) is
  self-evidently a superseded draft independent of S2. **Do NOT commit S2's WIP** (race).
- **Orchestrator:** owns `tasks.json` + the integration commit + the eventual push. This task's report
  is the evidence the orchestrator consumes to close P1.M6.T1 (and, with it, P1).