# Research — git staging allowlist & commit safety (the highest-risk step)

## Why this note exists

The final commit is the task's deliverable AND its highest-risk step: a wrong `git add` sweeps in
`PRD.md` (contract: never modify/commit) or `plan/.../tasks.json` (orchestrator-owned) or untracked
plan PRPs. The contract's staging list is an EXPLICIT ALLOWLIST; `git add -A` / `git add .` is FORBIDDEN.

## 1. The allowlist (contract clause d, verbatim intent)

Stage these lite-mode files (only those actually modified; `git add` on a clean file is a no-op):
- `config.toml`                 (lite_model config — likely already committed/clean)
- `hypr-binds.conf`             (SUPER+ALT+F → toggle-lite)
- `voice_typing/*.py`           (daemon/config/ctl/feedback — likely already committed/clean;
                                 include `daemon.py config.py ctl.py feedback.py status.sh recorder_host.py`)
- `tests/test_feed_audio.py`    (T7 lite tests, P1.M2.T1.S1)
- `tests/test_idle_and_gpu.sh`  (T7 section, P1.M2.T1.S1)
- `README.md`                   (lite sections, P1.M2.T2.S1)
- `tests/ACCEPTANCE.md`         (#9/#10 rows + this task's #10 flip)

## 2. The EXCLUSIONS (MUST NOT be staged — verify after `git add`, before `commit`)

- `PRD.md` — contract: "Do NOT modify PRD.md." It IS modified in the working tree (research time);
  LEAVE IT UNSTAGED. The lite commit must not contain PRD.md changes.
- `plan/004_607e9cca32b7/tasks.json` — orchestrator-owned (and any `**/tasks.json`,
  `**/prd_snapshot.md`). Leave unstaged.
- `plan/004_607e9cca32b7/P1M2T1S1/`, `plan/004_607e9cca32b7/P1M2T2S1/`, `plan/004_607e9cca32b7/P1M2T3S1/`
  (untracked PRP/research dirs) — plan artifacts, committed by the orchestrator separately, NOT part of
  the lite-feature commit.
- ANYTHING under `plan/001_be48c74bc590/` (the prior bugfix plan — contract: "Do NOT touch plan/001").

## 3. The safe staging + verification command sequence

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain          # (1) RE-VERIFY the exact uncommitted set (contract requirement)

# (2) Stage ONLY the allowlist — EXPLICIT file args; NEVER `git add -A` / `git add .`
git add hypr-binds.conf config.toml README.md tests/ACCEPTANCE.md \
        tests/test_feed_audio.py tests/test_idle_and_gpu.sh \
        voice_typing/daemon.py voice_typing/config.py voice_typing/ctl.py \
        voice_typing/feedback.py voice_typing/status.sh voice_typing/recorder_host.py

# (3) VERIFY the staged set BEFORE committing — MUST list ONLY allowlisted files:
git diff --cached --name-only
#    MUST contain a subset of: hypr-binds.conf config.toml README.md tests/ACCEPTANCE.md
#      tests/test_feed_audio.py tests/test_idle_and_gpu.sh voice_typing/*.py voice_typing/status.sh
#    MUST NOT contain: PRD.md, plan/004_607e9cca32b7/tasks.json, anything under plan/
#    If it DOES contain an exclusion, unstage it: `git restore --staged <file>`, then re-verify.

# (4) Commit on main:
git commit -m 'Add lite mode: single-small-model quick dictation (PRD §4.2ter)'

# (5) Post-commit verification:
git show --stat HEAD            # the commit's file list (confirm only lite-mode files)
git log --oneline -1            # confirm on main
git status --porcelain          # PRD.md + tasks.json remain UNSTAGED (expected); plan/ still untracked
```

## 4. Commit message

Contract-suggested (use verbatim): `Add lite mode: single-small-model quick dictation (PRD §4.2ter)`.
Optionally add a body bullet-listing the verification (full suite green; T6/T7 GPU lifecycle PASS;
lite-VRAM < normal-VRAM; criterion-8 offline). Keep the subject line exactly as suggested.

## 5. What "done" looks like

- `main` has a NEW commit whose `--stat` lists ONLY lite-mode files (no PRD.md, no tasks.json, no plan/).
- `git status --porcelain` post-commit still shows `PRD.md` + `tasks.json` as unstaged mods (the
  orchestrator/human owns those) and the plan/ PRP dirs as untracked. That is the EXPECTED end state —
  the lite feature is committed; everything else is left alone.
- The full suite is green; T6/T7/criterion-8 all `[PASS]`; ACCEPTANCE #10 = `PASS` with real evidence.
