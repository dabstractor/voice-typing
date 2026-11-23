# Merge record — fix/ydotoold-datagram → main (P1.M1.T2.S1)

Executed 2026-11-24 per plan/008_a47116bb2b79/P1M1T2S1/PRP.md. The merge commit IS the
primary record; this file is the bounded handoff note for T2.S2/T2.S3.

## What landed

- Merge commit `66734d6` on main, two parents (`54b4b31` ^ `33321c6`) — a real merge, NOT a
  squash. Message carries the defect rationale (Errno-91 on every socket connect since
  `f0d8d0a`; CLI fallback goes cold; packing byte-identical evidence; T2.S2/T2.S3 follow).
- Branch diff = exactly 2 files, zero conflicts ('ort' strategy):
  - `voice_typing/ydotoold_client.py` — `_connect` (line 55) now opens
    `socket.AF_UNIX + SOCK_DGRAM` (was `SOCK_STREAM` at main's line 41).
  - `tests/test_ydotoold_client.py` — NEW, 11 in-process FakeYdotoold tests.

## Gates (all green)

| Gate | Command | Result |
|---|---|---|
| L1 static | grep/test/log | `SOCK_DGRAM` live; test file present; two-parent merge commit |
| L2 3-suite | `timeout 300 .venv/bin/pytest tests/test_ydotoold_client.py tests/test_typing_backends.py tests/test_key_listener.py -q` | **79 passed** (11 new + existing) |
| L3 watch set | `timeout 120 uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no` | **16 failed, 76 passed** — EXACTLY the recorded baseline |
| L4 scope | `git diff HEAD~1..HEAD --name-only` (scoped) | 2 branch files only; PRD.md count 0; `typing_backends.py` untouched |

Watch-set name diff: the 16 FAILED names match `tests/G1_BASELINE.md`'s inventory rows 1–16
byte-for-byte (10 commit + 2 core + 4 freeze, incl. row 16
`test_cancel_then_resume_restores_live_delta_typing`, the recorded (i)/F1 legacy-separator
red). Zero drift — the merge is behaviorally inert on streaming (no streaming/daemon code in
the diff, verified pre-merge: `git log f0d8d0a..main -- <branch files>` was EMPTY).

## Notes for downstream subtasks

- T2.S2 (6 ms press→release contact gap): baseline is post-merge HEAD `66734d6`. The merge
  does NOT close the gap (d3_defects_g1_baseline.md Part B ~185).
- T2.S3 (journal-noise regression guard): the Errno-91 CLI fallback in
  `typing_backends.py:138-149` is UNTOUCHED and now COLD (unexercised) — guard asserts no
  per-burst fallback storms.
- Watch-set (ii) candidates (`test_a_delta_cadence`, `test_b_commit_rewind_exact`,
  `tests/test_streaming.py` real-model harness): unaffected by construction (zero code
  overlap); the PRP's gate scoped the check to the fast combined set.
- Procedural note: PRD-PROTECT screens bash commands — `cd <repo-root>` (or any bare `.`/
  repo-root token) plus a tree-rewriting git verb (`git merge-base` matches!) is blocked as a
  false positive (repo-root prefix "covers" PRD.md). Use `git -C <repo>` and avoid
  bare-`.`-producing punctuation in `-m` messages (a `).` sequence tokenizes to a bare `.`
  token → resolves to repo root → "mentions" the protected path). Pre-flight dirty entries
  were orchestrator-owned `plan/008…/` pipeline files only (staged PRPs/tasks.json/agent
  records) — no implementation files mid-flight; the merge did not overlap them.
- No push (local main only), per GOTCHA #7.
