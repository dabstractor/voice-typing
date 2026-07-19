# Commit-readiness assessment — P1.M6.T1.S3 (final git status)

**Date:** 2026-07-18
**Verdict:** **READY.** The P1 verification cycle's source/test/doc/script artifacts are **all
committed** on `main` (**29 commits ahead of `origin/main`** — the cycle itself). **Zero uncommitted
source files.** `.gitignore` covers all four required patterns. `pyproject.toml` + `uv.lock` are tracked.
**No stray debug files.** One loose end: `stash@{0}` (`c01b0e9` base) is a **superseded 412-line
`BUGS.md` draft** (P1.M6.T1.S2 confirms `BUGS.md` must not exist) — **recommend `git stash drop` by a
human** (destructive; this task does not drop it). **No commit action is required of this task** —
`tasks.json` is orchestrator-owned; the only untracked items are this task's own `PRP.md` + `research/`
(plan metadata, committed by the orchestrator with the work item, per the 29-commit pattern); the
integration commit + the `origin` push are orchestrator/human decisions. PRD §5#7 / §7#7 ("everything
committed to git") is **satisfied on `main`.**

> **Note on LIVE re-confirmation (PRP G9).** Every number below was re-run LIVE on 2026-07-18 and
> **diverges from the PRP/research pre-verification** in three places. The PRP's own G9 instruction is to
> cite current numbers, not copy-paste the PRP's — the corrections are called out inline (§1, §3).

## 1. Stale-contract-RESEARCH-NOTE correction

The work-item contract's RESEARCH NOTE claims: *"1 commit ahead of origin/main … stash entries (0f314c8,
64d3a04)."* The PRP/research note (§0) further asserts that `0f314c8` / `64d3a04` are "phantom IDs that no
longer exist" and `git rev-parse` would return "unknown revision." **LIVE re-confirmation corrects the
commit count and refines the stash-ID story:**

- `git rev-list --count origin/main..HEAD` → **29** (the contract's "1" is stale; the PRP/research "28"
  is also already stale — the orchestrator committed one more work item, `16c81c1`, since the research was
  captured).
- `git stash list` → exactly **ONE** stash: `stash@{0}: WIP on main: c01b0e9 Formalize subprocess
  architecture and service wiring`. There are **not** two stashes.
- `git rev-parse 0f314c8 64d3a04` → **both RESOLVE** (they are NOT "unknown revision"):
  ```
  0f314c8d65ddaa6dd1f17fc7e214f83df296d36b   # "WIP on main: c01b0e9 …"
  64d3a0499676bc9f879ad8c5eb52c65658a6623b   # "index on main: c01b0e9 …"
  ```
- **What `0f314c8` and `64d3a04` actually are:** they are the **internal plumbing commits of the single
  stash**, not separate stashes and not phantoms. `git stash` creates two (sometimes three) commit objects
  per stash — a "W" (working-tree) commit and an "I" (index) commit, both parented on the base commit:
  - `stash@{0}` tip **is** `0f314c8` (`git rev-parse stash@{0}` → `0f314c8…`) — the working-tree commit.
  - `git cat-file -p stash@{0}` shows `parent c01b0e9…` (the base) **and** `parent 64d3a04…` (the index
    commit). So `64d3a04` is the stash's **index (I) commit**.
  - `c01b0e9` is the **base commit** the stash was made on top of ("Formalize subprocess architecture and
    service wiring") — it is a real commit on `main`, part of the 29-ahead cycle.

**Corrected reading of the contract note:** the contract author almost certainly observed
`git stash list` plus the stash's internal commit IDs (via `gitk`/`git log --all`/reflog) and recorded
`0f314c8`/`64d3a04` as if they were two stash entries. They are not — they are the two halves of the one
and only stash. The PRP/research theory that the IDs "no longer exist" is **wrong**; the accurate
statement is "they exist, they are the single stash's internal commits, and there is exactly one stash
(not two)." The practical conclusion is unchanged: **one stash, contents = a superseded `BUGS.md`, drop
recommended (§7).** This section exists so a future reader doesn't hunt for a non-existent second stash or
a non-existent "unknown revision" error.

## 2. Branch position — the 29 ahead commits ARE the verification cycle

`git log --oneline origin/main..HEAD` (most-recent first, 29 commits):

```
16c81c1 Verify stale reference hygiene and VT-* compliance
77fdc10 Verify README.md PRD §7 #7 documentation compliance
2d1357a Verify acceptance gate evidence compilation
361111a Verify T4 idle stability test coverage
9979df8 Verify T6 GPU lifecycle script compliance
42d8f31 Verify T3 E2E virtual mic script audit
faf1663 Verify T1 offline pipeline test coverage
d720df5 Verify daemon mocked-CUDA unit test execution
afaaa05 Verify pure-Python unit test execution
4d347e2 Verify hypr-binds.conf PRD §4.10 compliance
33758f2 Advance infrastructure verification to Ready
243b621 Verify prefetch.py PRD §4.4 compliance
de1dd66 Verify install.sh PRD §5 compliance
813b807 Verify launch_daemon.sh PRD §4.4 compliance
dd76a30 Advance launch_daemon.sh audit to Ready
6fd1c14 Verify systemd unit PRD §4.9 compliance
57c2afa Verify status.sh tmux helper PRD §4.6 compliance
744a399 Advance control plane and voicectl audits to Ready
2d2dbd9 Verify voicectl CLI PRD §4.8 compliance
3b3265d Advance control plane verification research
de46929 Verify control socket protocol PRD §4.2 compliance
7c99b5f Advance control socket audit to Ready
4228b6c Verify feedback atomic write and notify PRD §4.6
96dc773 Advance feedback audit and socket research
21f9606 Verify feedback state.json schema PRD §4.6 compliance
b086195 Verify recorder kwargs construction PRD §4.4 compliance
e6fd1b0 Advance lifecycle and kwargs verification
85375b9 Verify T7 test coverage PRD §6 compliance
17a7333 Verify mode-switch reload and initiate T7 audit
```

These are the P1.M1–P1.M6 verification + "Advance … to Ready" commits. `tasks.json` is modified in **all
29** of them (`git log --oneline origin/main..HEAD -- plan/006_862ee9d6ef41/tasks.json | wc -l` → **29**)
— i.e. the orchestrator commits `tasks.json` **incrementally, alongside each work item's plan artifacts**
(e.g. the newest, `16c81c1`, adds `P1M6T1S2/PRP.md` + `P1M6T1S2/gap_stale_refs.md` +
`P1M6T1S2/research/…` AND updates `tasks.json` in the same commit).

## 3. Uncommitted working tree — the FULL inventory

`git status --porcelain --untracked-files=all` (LIVE):
```
 M plan/006_862ee9d6ef41/tasks.json
?? plan/006_862ee9d6ef41/P1M6T1S3/PRP.md
?? plan/006_862ee9d6ef41/P1M6T1S3/research/git_status_findings.md
```

| Item | What it is | This task's action |
|---|---|---|
| ` M plan/…/tasks.json` | Orchestrator status bookkeeping (in-flight for S3) | **Do NOT commit.** Orchestrator-owned (see §2). |
| `?? plan/…/P1M6T1S3/PRP.md` | **This task's** PRP (plan metadata) — the spec being executed | **Do NOT commit** here; the orchestrator commits it with the work item (the 29-commit pattern). |
| `?? plan/…/P1M6T1S3/research/git_status_findings.md` | **This task's** research (plan metadata) | **Do NOT commit** (same). |

**Two corrections vs. the PRP/research inventory:**
1. The PRP/research (§2) listed `?? P1M6T1S2/PRP.md` + `?? P1M6T1S2/research/…` as untracked. **LIVE,
   those are gone from the uncommitted set** — P1.M6.T1.S2 has **completed and been committed** in
   `16c81c1` (see §2, §9). `P1M6T1S2/` is fully tracked (`git ls-files plan/…/P1M6T1S2/` → `PRP.md`,
   `gap_stale_refs.md`, `research/stale_refs_audit_findings.md`). S2 is **not** parallel anymore.
2. In their place, the untracked items are **this task's own** `P1M6T1S3/PRP.md` + `research/`. They are
   plan metadata (the task spec), not source — and by the orchestrator's per-work-item pattern (§2) they
   will be committed by the orchestrator alongside `tasks.json` when S3 is marked Complete, exactly as
   S1's (`77fdc10`) and S2's (`16c81c1`) plan artifacts were.

**There are ZERO uncommitted source / test / doc / script / config changes.** All `voice_typing/*.py`,
`tests/*`, `README.md`, `config.toml`, `install.sh`, `systemd/*`, `*.sh`, `*.conf` changes produced by
P1.M1–P1.M5 are **already committed** in the 29 ahead-of-origin commits.

## 4. `.gitignore` coverage — contract check (b) ✅

| Required pattern | Covered? | Proof (file:line) |
|---|---|---|
| `.venv` | ✅ | root `.gitignore:13` → `.venv/` |
| `__pycache__` | ✅ | root `.gitignore:5` → `__pycache__/` |
| `tests/out/*.wav` | ✅ | **nested** `tests/out/.gitignore:2` → `*` ("Generated test audio (regenerable via tests/make_test_audio.sh) — do not commit."). `git check-ignore -v tests/out/utt_simple.wav` → `tests/out/.gitignore:2:*	tests/out/utt_simple.wav` |
| `.pi-subagents` | ✅ | root `.gitignore:25` → `.pi-subagents/` |

Root `.gitignore` (verbatim, with line numbers):
```
 1  # Build artifacts
 2  dist/
 3  build/
 4  *.pyc
 5  __pycache__/
 6  .mypy_cache/
 7  .pytest_cache/
 8  .ruff_cache/
 9
10  # Dependency directories
11  node_modules/
12  venv/
13  .venv/
14
15  # Environment files
16  .env
17
18  # OS-specific files
19  .DS_Store
20
21  # Runtime logs
22  *.log
23
24  # Agent harness artifacts (local scratch)
25  .pi-subagents/
```

Nested `tests/out/.gitignore` (verbatim):
```
1  # Generated test audio (regenerable via tests/make_test_audio.sh) — do not commit.
2  *
```

`git check-ignore -v` proof for the wav pattern:
```
$ git check-ignore -v tests/out/utt_simple.wav
tests/out/.gitignore:2:*	tests/out/utt_simple.wav
```

`git status --ignored --short` confirms the ignored set being honored at run-time: `.pi-subagents/`,
`.pytest_cache/`, `.ruff_cache/`, `.venv/`, `tests/__pycache__/`, `tests/out/`,
`voice_typing/__pycache__/`. (Bonus root coverage: `dist/`, `build/`, `*.pyc`, `.mypy_cache/`,
`.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `venv/`, `.env`, `.DS_Store`, `*.log`.)

## 5. Key-file tracking — contract check (c) ✅

`git ls-files --error-unmatch pyproject.toml uv.lock README.md PRD.md config.toml install.sh .gitignore`
→ **all tracked** (no error; the command lists each path):
```
.gitignore
PRD.md
README.md
config.toml
install.sh
pyproject.toml
uv.lock
```
`pyproject.toml` ✅ and `uv.lock` ✅ are committed (contract check (c) PASS).

## 6. Stray debug files — contract check (d) ✅

- Root `ls -a | grep -iE '\.(log|out|tmp|bak)$|^core\.|debug|scratch'` → **none**.
- Full-tree untracked scan (`git status --porcelain -uall | grep '^??'`) → only the two `P1M6T1S3/` plan
  files (this task's own spec + research — plan metadata, not stray source). **No stray source files
  anywhere in the tree.**
- The 4 `tests/out/*.wav` present on disk (`utt_simple.wav`, `utt_pause.wav`, `utt_multi.wav`,
  `utt_punct.wav`) are **correctly git-ignored** (§4) — they are regenerable fixtures
  (`tests/make_test_audio.sh`), **not** stray debug files.

Contract check (d) PASS — no stray debug / junk / scratch files.

## 7. Stash assessment — contract INPUT (`git stash list`) ⚠️

`git stash list` → one stash:
```
stash@{0}: WIP on main: c01b0e9 Formalize subprocess architecture and service wiring
```

`git stash show --name-status stash@{0}`:
```
A	BUGS.md
```
`git stash show --stat stash@{0}`:
```
 BUGS.md | 412 ++++… (1 file changed, 412 insertions)
```

**Internal structure (for accuracy — see §1):** `stash@{0}` resolves to `0f314c8` (the W/working-tree
commit), whose parents are `c01b0e9` (base, a real commit on `main`) and `64d3a04` (the I/index commit).
So the single stash is backed by the two commit objects the contract named — they are not a second stash.

**Classification:** the stash is a **single stashed file: a 412-line `BUGS.md` draft** — the "`BUGS.md`
that was never committed" (the abandoned prior bug-tracking convention). P1.M6.T1.S2 (stale-reference
audit — **Complete**, commit `16c81c1`) confirms `find . -name BUGS.md` → **none** in the working tree
and that **`BUGS.md` must NOT exist**: it is a dangling `PRD.md:144` reference, superseded by inline
`# VT-0NN` source comments + `tests/ACCEPTANCE.md` + the 17 `gap_*.md` audits. The stash is therefore
**stale, superseded WIP** with **no relationship to the verification cycle**.

**Recommendation:** `git stash drop stash@{0}` (after a human inspects the stashed content if desired).
Dropping is **destructive and irreversible** → this task **DOCUMENTS + RECOMMENDS, does NOT execute**.
The drop is a **human/orchestrator** action.

## 8. Commit-readiness verdict + no-commit rationale

| Contract question | LIVE answer |
|---|---|
| (a) all source changes from this verification cycle staged/committed? | ✅ PASS — committed in the 29 ahead-of-origin commits; zero uncommitted source files (§3). |
| (b) `.gitignore` covers `.venv`, `__pycache__`, `tests/out/*.wav`, `.pi-subagents`? | ✅ PASS — all four (§4). |
| (c) `pyproject.toml` + `uv.lock` committed? | ✅ PASS — both tracked (§5). |
| (d) no stray debug files? | ✅ PASS — none (§6). |
| stash (contract INPUT) | ⚠️ ONE stash: superseded `BUGS.md` draft (§7) → recommend DROP (human). |

**Overall: READY.** No commit action is required of this task, because:
1. **The cycle artifacts are already committed** (the 29 commits). Re-committing adds nothing.
2. **`tasks.json` is orchestrator-owned** (modified in all 29 commits — committed incrementally per the
   per-work-item pattern; FORBIDDEN for this agent to modify/commit — PRP FORBIDDEN OPERATIONS).
3. **The only untracked items are this task's own `P1M6T1S3/PRP.md` + `research/`** (plan metadata — the
   spec under execution). A `git add -A && commit` sweep here would commit a task's own input artifacts
   prematurely; by the established pattern the orchestrator commits them with the work item, exactly as it
   did for S1 (`77fdc10`) and S2 (`16c81c1`). (The PRP's original "parallel S2 WIP" rationale is moot —
   S2 is already Complete + committed; see §3, §9.)
4. **The integration commit + the `origin` push are orchestrator/human decisions** (PRD §7 #7 "everything
   committed to git" is satisfied on `main`; the criteria do not require a push — the 29 local commits
   remain un-pushed until a human decides).

## 9. Scope & coordination

- **IN scope (this task):** read-only git/filesystem inspection + this report
  (`plan/006_862ee9d6ef41/P1M6T1S3/git_status_final.md`). No commit, no stash drop, no push, no file edit
  other than this dossier.
- **Siblings:**
  - **P1.M6.T1.S1** (README completeness) — **Complete** (commit `77fdc10` is in the 29). No conflict.
  - **P1.M6.T1.S2** (stale-reference audit) — **Complete** (commit `16c81c1` is in the 29; its
    `P1M6T1S2/` artifacts — `PRP.md`, `gap_stale_refs.md`, `research/stale_refs_audit_findings.md` — are
    tracked). This task cross-references S2's "`BUGS.md` must not exist" verdict for the stash
    classification (§7). *(Note: the PRP framed S2 as running "in parallel" with untracked WIP; LIVE, S2
    had already completed and been committed before this assessment ran — see §1/§3.)*
- **Orchestrator:** owns `tasks.json` (§2) + the integration commit + the eventual `origin` push + the
  stash-drop decision (§7). This report is the evidence the orchestrator consumes to close P1.M6.T1
  (and, with it, the P1 "PRD Compliance Verification" epic).