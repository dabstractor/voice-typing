# Research — finalization runbook (full suite + GPU lifecycle + acceptance #10 + commit)

## 0. What this task IS

P1.M2.T3.S1 is a **finalization/validation + commit** task, NOT a feature-build task. The lite-mode
SOURCE is already committed (`656de1c Add Lite mode CPU-fallback`, `2d11496 Fix toggle semantics`,
`172fbf2 Add mode-switch teardown`). What remains: (a) run the full suite green, (b) run the GPU
lifecycle test + verify acceptance #10 against REAL output, (c) confirm offline at runtime,
(d) flip ACCEPTANCE #10 `pending T7 → PASS`, then (e) stage the lite-mode changeset and commit on
`main`. The deliverable is a clean git commit.

## 1. Git state (verified live at research time; RE-VERIFY at impl time per the contract)

`git status --porcelain` at research time (P1.M2.T2.S1 still in progress):
```
 M PRD.md                              # EXCLUDE — contract: do NOT modify/commit PRD.md
 M README.md                           # lite sections (P1.M2.T2.S1) — STAGE
 M hypr-binds.conf                     # SUPER+ALT+F keybind — STAGE
 M plan/004_607e9cca32b7/tasks.json    # EXCLUDE — orchestrator-owned
 M tests/test_feed_audio.py            # lite tests (P1.M2.T1.S1) — STAGE
 M tests/test_idle_and_gpu.sh          # T7 section (P1.M2.T1.S1) — STAGE
?? plan/004_607e9cca32b7/P1M2T1S1/     # EXCLUDE — plan PRPs (orchestrator)
?? plan/004_607e9cca32b7/P1M2T2S1/     # EXCLUDE — plan PRPs (orchestrator)
```
- Source files CLEAN (already committed): `config.toml`, `voice_typing/daemon.py`,
  `config.py`, `ctl.py`, `feedback.py`, `status.sh`, `recorder_host.py` (all tracked, no ` M`).
  → `git add` on them is a harmless no-op; include them in the explicit allowlist for completeness.
- `tests/ACCEPTANCE.md` is tracked; at research time it is STALE (`criteria 1–8`, NO `| 10 |` row,
  evidence header `criteria 5, 6, 8, 9`). P1.M2.T2.S1 (parallel) ADDS the `| 10 |` row marked
  `pending T7` + fixes `1–8 → 1–10`. When THIS task runs, ACCEPTANCE.md will show the `| 10 |` row
  as `pending T7`; THIS task flips it to `PASS`.
- `.gitignore` does NOT ignore `plan/`; the PRP subdirs are simply untracked (never `git add` them).
- Branch: `main`. Last 3 commits are the incremental lite source.

## 2. The GPU lifecycle test (tests/test_idle_and_gpu.sh) — what it covers + its output

Run explicitly (NOT in pytest): `bash tests/test_idle_and_gpu.sh`. Heavy (~5-8 min: 2 cold inits +
120 s T4 silence + idle-unload waits). PRECONDITIONS:
- Stop any live daemon first: `systemctl --user stop voice-typing` (the script PREFLIGHT refuses if
  `voicectl status` answers or the unit is active — `G-PREFLIGHT`, line 116/382).
- Run in a QUIET room: T4 listens to AMBIENT silence on the real default mic for 120 s (no null-sink,
  `G-NOSOURCE`). Ambient speech → spurious final → false FAIL.
- Needs the GPU + the systemd user stack. Full paths: `.venv/bin/python`, `/usr/bin/tmux`,
  `/usr/bin/nvidia-smi`.

What it proves (each prints `[PASS]`/`[FAIL]` + real numbers):
- **T6(a)** boot un-armed → daemon tree ABSENT from nvidia-smi (lazy load, ~0 VRAM).  ← criterion 6/9
- **criterion 8** daemon.log has ZERO `HTTP Request: GET https://huggingface.co` lines (OFFLINE via
  launch_daemon.sh's exports, NON-circular — `G-OFFLINE`).  ← acceptance #8 / no-network
- **criterion 6** boots `listening: off`; voicectl toggle on/off ok; unit `ExecStart`→launch_daemon.sh
  + `Restart=on-failure`.
- **T6(b)** armed → tree PRESENT, Σ∈[1024,5120] MiB.
- **criterion 5 / T4** 120 s silence: no finals typed, no crash, avg CPU < 25%/core (/proc tree sum).
- **T6(c)** stop → tree STILL PRESENT (instant re-arm; stop ≠ unload).
- **T7** (LANDED by P1.M2.T1.S1, lines 575-700): the acceptance-#10 evidence —
    1. re-arm normal, snapshot normal-armed VRAM (`T7_NORMAL_VRAM`).
    2. `voicectl toggle-lite` → POLL `status` until `^mode: lite` (30 s ceiling) → `[PASS] T7 mode-switch`.
       snapshot lite-armed VRAM (`T7_LITE_VRAM`); assert `lite_total < normal_total` →
       `[PASS] T7 VRAM≈half` (best-effort; `[WARN]` not fatal).
    3. `voicectl toggle-lite` → disarm → `[PASS] T7 disarm` (`listening: off`).
    4. `voicectl toggle` → POLL `status` until `^mode: normal` (one bounded reload).
    5. `voicectl status` → assert `^mode: normal`.
- **T6(d)** RUN 2 (5 s idle-unload override): absent→start→present→stop→POLL absent (~25 s,
  process-group teardown releases ALL VRAM incl. the realtime context) → re-arm → present. ← criterion 9

**Evidence block** (lines 745-762): the script prints a fenced `=== ACCEPTANCE EVIDENCE (...) ===`
block containing the T6(a/b/c/d) states, `T7 normal-armed VRAM (MiB)` + `T7 lite-armed VRAM (MiB)`,
`cpu_avg_pct_of_one_core`, `voicectl_status`, `systemd_unit`. → THIS is the real output to paste into
ACCEPTANCE.md #10's evidence (lite ≈ half normal VRAM + mode-switch PASS).

## 3. The full pytest suite (acceptance gate a)

`.venv/bin/python -m pytest tests/ -q` — INCLUDES `tests/test_feed_audio.py` (heavy, builds REAL
models) + the lite tests added by P1.M2.T1.S1 (`test_lite_feed_audio_utt_simple`,
`test_lite_latency_lower_than_normal`). MUST be all-pass (`0 failed`; skips only for legitimately-
gated tests). The lite tests are CUDA-gated: they SKIP on no-CPU/no-WAVs but PASS on this GPU box.

Prereqs:
- Build WAV assets if absent: `ls tests/out/utt_simple.wav || bash tests/make_test_audio.sh`.
- Stop the live daemon first (frees GPU; avoids contention): `systemctl --user stop voice-typing`.
- Full path `.venv/bin/python` (zsh aliases `python3`→`uv run` — invariant #5).

test_feed_audio.py builds the recorder DIRECTLY (no daemon), so the `voice-typing latency:` log line
never fires there — latency is measured directly. (system_context.md §4 invariant #4.)

## 4. Acceptance #10 verification matrix (contract clause b) — what proves each clause

| #10 clause | Proven by | REAL evidence |
|---|---|---|
| toggle-lite → `mode: lite` | T7 step 2 `[PASS] T7 mode-switch` | GPU test stdout + `voicectl status` |
| nvidia-smi daemon PID ~half VRAM (large never loads) | T7 step 2 `[PASS] T7 VRAM≈half` + `T7_LITE_VRAM` < `T7_NORMAL_VRAM` | evidence-block VRAM numbers |
| toggle (switch) → one bounded reload, `mode: normal` | T7 step 4 `[PASS] T7 mode-switch` (30 s POLL) | GPU test stdout |
| `status` + `state.json` report `mode` | T7 step 5 + feedback.py `set_mode`/`_state['mode']` | `voicectl status` `mode:` line |
| both modes honor the graceful drain | SHARED `_request_stop`/`_begin_drain`/`_complete_drain` (system_context §1: out of scope, already implemented, commits `5f32d74`/`495bdd2`/`5c83567`) | shared path; optional manual smoke |

→ The GPU test (T7 + T6) covers #10 EXCEPT a lite-specific mid-utterance drain. The drain is shared
machinery (same `on_final` clean→type path in both modes), so it is NOT re-tested here (system_context
§1 says drain is OUT OF SCOPE). An OPTIONAL manual lite-drain smoke: arm lite → utter → `voicectl stop`
mid-utterance → confirm the final types. Not a hard gate (would duplicate proven shared behavior).

## 5. No-network-at-runtime confirmation (contract clause c)

Already proven by the GPU test's **criterion 8** grep (line 573: `[PASS] criterion 8 (no network):
daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines`). It launches the daemon via
the PRODUCTION path (`launch_daemon.sh`, no pre-set env) — a non-circular proof. Direct corroboration:
`grep -c 'HTTP Request: GET https://huggingface.co' <daemon.log>` → 0.

## 6. ACCEPTANCE.md #10 flip (the one doc edit this task owns)

P1.M2.T2.S1 leaves ACCEPTANCE.md with a `| 10 | … | pending T7 | …` row. THIS task flips the status
cell `pending T7 → PASS` and fills the evidence with the REAL T7/GPU output (lite-VRAM < normal-VRAM
numbers + "mode-switch roundtrip PASS"). DO NOT touch the README (P1.M2.T2.S1) or any other ACCEPTANCE
row. Re-verify the exact `| 10 |` row text against the live file before editing (P1.M2.T2.S1 authored
it). The evidence-block header in the script still says "criteria 5/6/8/9" (line 745) — that's a
script comment, not a hard gate; the block DOES print the T7 VRAM numbers regardless.

## 7. The contract explicitly says: "Do NOT touch plan/001 (the prior plan)."

There is a SEPARATE prior plan dir `plan/001_be48c74bc590/` (the bugfix plan from the previous work).
Do NOT add/commit/modify anything under `plan/001_*`. This task's commit is the lite-mode feature
files only. (Not relevant to staging since plan/001 isn't in the lite changeset — just don't go near it.)

## 8. Parallel-context contract: P1.M2.T2.S1 produces (consume, don't redo)

P1.M2.T2.S1 (parallel docs task) lands, in the working tree (uncommitted):
- README.md `## Lite mode` subsection (between Hotkey and tmux-status-line) + a lifecycle lite note.
- tests/ACCEPTANCE.md: `| 9 |` (idle-unload, PASS) + `| 10 |` (lite, `pending T7`) rows; intro
  `1–8 → 1–10`; evidence header `5, 6, 8, 9 → 5, 6, 8, 9, 10`; #7 stale-ref fix.
THIS task (T3.S1): runs T7, flips `| 10 |` `pending T7 → PASS` with real evidence, commits the whole
lite changeset (incl. T2.S1's README/ACCEPTANCE edits + T1.S1's tests). No overlap/conflict: the only
shared file is tests/ACCEPTANCE.md, where T2.S1 adds the row and T3.S1 flips its status — sequential,
non-overlapping edits.
