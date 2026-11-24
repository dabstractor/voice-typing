# Acceptance evidence — voice-typing (PRD §7 definition of done)

This document records the verified evidence for PRD §7 criteria 1–13 plus the §4.2quinquies
media-ducking row (D1 — a §4.2quinquies criterion, deliberately NOT numbered §7.14). It is the
human-readable record criterion 1 requires ("T1–T4, T6 pass, demonstrated by actual command output").

Regenerate the **5 / 6 / 8 / 9 / 10** block by running `./tests/test_idle_and_gpu.sh` and pasting its
`=== ACCEPTANCE EVIDENCE ===` output into the fenced block below. Criteria **1–4** are demonstrated
by the sibling test commands (T1/T2/T3); criterion **7** by `git status` + the README task.

## How to reproduce the 5 / 6 / 8 evidence

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true   # preflight refuses if it is running
./tests/test_idle_and_gpu.sh                              # ~5–8 min (2 cold inits + 120 s idle + unload waits)
# → prints per-clause PASS/FAIL lines + an '=== ACCEPTANCE EVIDENCE ===' block. Exits 0: every
#   clause PASSES (T6 a/b/c/d lifecycle, T4/criterion 5, criterion 6/8, and the T7 single-model
#   block: one-model greps, mode: lite, VRAM ∈ [512,3072] MiB, armed no-op cancel smoke).
```

Preconditions: models prefetched (`./install.sh`), a CUDA GPU, `jq` +
`/usr/bin/nvidia-smi` present, and a **quiet room** (the test listens to ambient silence on the
real default mic — it does NOT swap the audio source, so ambient speech could produce a real final
and spuriously fail the "no finals" assertion).

> **Cross-checked dossier (single source of truth):** `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md` — the P1.M5.T5.S1 go/no-go gate. Every row below is cross-referenced there with verdict + evidence + evidence-type (LIVE / STATIC / PAST-LIVE) + source artifact. **Overall verdict: GO — 9/10 PASS on substance; #7 PASS-on-substance (commit sign-off → the Final sign-off (P1.M7.T2.S3) section below); 17/17 source gap audits COMPLIANT; **424 LIVE-green test executions recorded that round (plan 006 dossier — superseded by the re-measured row-1 totals at HEAD `8778fb2` below)**.

## Criteria

| # | Criterion (PRD §7) | Status | Evidence |
|---|--------------------|--------|----------|
| 1 | T1–T4, T6 pass, demonstrated by actual command output | **PARTIAL — 21 NEW failures at HEAD, named in Evidence** (T4/T6 shell proof unchanged) | **LIVE re-measured 2026-11-23 @ HEAD `8778fb2`** (the plan-006 round's arithmetic was 9 + 196 + 219 = **424 LIVE-green** — recorded that round, now superseded): T1 `test_feed_audio.py` **6 passed / 3 failed** (147.2s, real models — `test_daemon_path_emits_latency_line_and_types_nothing` stable-RED at HEAD, NEW: `no 'voice-typing latency:' line emitted`; `test_single_model_construction` + `test_single_model_final_latency_within_budget` red once under machine load (fuzzy-overlap < 0.70 / `t_last_speech=None`), **green on the focused re-run** (117.4s) → FLAKY class, single observations prove nothing); T2 `test_textproc.py` **31/31** (0.02s — the 006 round's "unit 196" grouping is not reproducible, superseded by this standalone count); daemon+recorder mocked **267 passed / 20 failed** (15.5s) — **none of the 20 is G1-classified** (`tests/G1_BASELINE.md`'s 20-row table covers the streaming suites only): 15 fail on the eager-separator shape (expected a standalone `' '` op or trailing-space placement; e.g. `test_on_final_happy_path_appends_space`, `test_on_final_streaming_commit_types_via_engine`, `test_on_final_emits_structured_latency_line`) and 5 on compute-type/device expectations (`float16` vs `float32` — `test_cfg_to_kwargs_cuda_path`, `test_cfg_to_kwargs_calls_resolve_with_cfg_defaults`, `test_resolved_device_unaffected_by_cuda_check_failure`, `test_status_device_reseeded_not_stale_after_child_death`, `test_status_device_reseeded_not_stale_after_idle_unload`) → **all 21 (20 daemon + 1 stable T1, plus 2 T1 flakes green-on-rerun) are NEW failures: reported, escalated, never reconciled away**. Net this session: **304 passed / 23 failed** across the row-1 suites — NOT all-green at HEAD; the T4/T6 lifecycle shell evidence (STATIC, block below) is unaffected. **STATIC + past-live:** T4 + T6 (a/b/c/d lifecycle) via `./tests/test_idle_and_gpu.sh` (block below); T3 via `./tests/e2e_virtual_mic.sh`. Evidence-TYPE split (LIVE vs STATIC vs PAST-LIVE) in the dossier §2. |
| 2 | A pause mid-dictation of ≥3 s loses zero words and does not end the session | **PASS** | `test_pause_keeps_both_halves` **LIVE** real-model (T1b — PAUSE_A + PAUSE_B both transcribed across the 3.0s gap). Drain logic COMPLIANT + 29 mocked drain tests **LIVE**. E2E `utt_pause.wav` halves fuzzy-matched through the real mic **STATIC** (`./tests/e2e_virtual_mic.sh`). Drain-clause caveat: E2E stop lands after all finals → drain guard never fires (test-COVERAGE gap, not source). |
| 3 | Live partials observable in `state.json` while audio plays | **PASS** | `feedback.py` COMPLIANT (38 unit tests **LIVE**); E2E `partials.log` non-empty via `jq -r .partial` DURING playback **STATIC** (`./tests/e2e_virtual_mic.sh`). |
| 4 | Only the daemon's typed output reaches the target — Rev 2: live partial text plus commits (§4.2quater); nothing typed while toggled off (the `listening` gates on partial and commit paths are unchanged) | **PASS** (disarm gate + Rev 2 streaming typing) | Disarm gate: the `listening` flag gates BOTH the partial and commit paths — the commit gate is on_final's first line; the partial gate is `_on_partial`'s first line (BUG-004 / P1.M1.T4.S1), pinned by `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` (mocked **LIVE** in tests/test_daemon.py). E2E CRIT4 `before==after` after `voicectl stop` + one more WAV **STATIC** (`./tests/e2e_virtual_mic.sh`). Rev 2 streaming typing **LIVE** (CUDA-gated real model) — re-measured 2026-11-23 @ `8778fb2`: the suite is **3 passed / 4 failed** (row 11 has the full reconciliation); `test_a_delta_cadence` + `test_b_commit_rewind_exact` are now the **(ii) watch-set reds** of `tests/G1_BASELINE.md` (cadence/rewind properties — NOT typed-output regressions); the LIVE typed-content proof at HEAD is `test_c_pause_join` (typed pieces join fuzzy ≥ 0.80 across the 3 s pause; ends `screen == committed + tail`) + `test_e_cancel` (Backspace rewinds the already-typed text exactly). |
| 5 | Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use | **PASS** | `textproc.clean()` blocklist PASS (21 unit tests **LIVE**). T4 shell **STATIC = authoritative**: `IDLE_SECS=120`, no-finals double-signal, CPU `avg < 25%` of one core, `kill -0` no-crash (`./tests/test_idle_and_gpu.sh`). Mocked guard **LIVE** (`test_on_final_rejects_hallucination` L667). Past-live CPU **1.67–14 %** (< 25 %). Two-layer mitigation VAD + blocklist. (Block below.) |
| 6 | `voicectl toggle/start/stop/status/quit` all work; systemd user service; starts un-armed; auto-restarts on failure | **PASS** | socket (31) + voicectl (54) COMPLIANT, all **LIVE** unit tests (re-measured 2026-11-23 @ HEAD, G1 re-run — the plan-006 counts socket 35 / voicectl 32 / systemd 15 / status_sh 5 predate the delta tests and are round-attributed to the plan-006 dossier). systemd unit suite at HEAD = **15 passed / 1 failed** — the 1 is `test_hypr_binds_use_portable_home_launcher`, a **PRE-EXISTING red** (the Rev-3 halt bind `SUPER ALT, Escape → systemctl --user stop` landed pre-baseline in `0e7dd05` and invokes systemctl directly, so the every-bind-launches-voicectl assert trips; named + escalated in the sign-off, never reclassified, never "fixed" by a docs task). daemon lazy-boot/status/dead-child **mocked LIVE**. Unit `ExecStart → launch_daemon.sh` + `Restart=on-failure` **STATIC** grep in `./tests/test_idle_and_gpu.sh`. VT-003/VT-004 fixed in-source; VT-001 = doc-drift only (→ P1.M6.T1.S2). (Block below.) |
| 7 | Everything committed to git; README documents install / hotkey / config / troubleshooting / CPU-only mode | **PASS-on-substance** (commit sign-off → the `## Final sign-off (P1.M7.T2.S3)` section below) | README sections PRESENT + committed (line map re-swept at HEAD: Install :22, Hotkey :82, Upgrading-from-Rev-1 :117, Streaming :134, Media ducking :204, Bulk text delivery :251, Feedback :324, Configuration :343, CPU-only :405, Troubleshooting :432–531, Logs/status :532). Impl + tests committed (verify commits `361111a`…`d720df5`; the delta changeset sits on `main` — see the sign-off below). `git status --short`: tree clean of shipped impl/doc files. Formal "everything committed" sign-off: the `## Final sign-off (P1.M7.T2.S3)` section below (incl. this gate's deliverables). |
| 8 | No network access needed at runtime (models cached by install) | **PASS** | install/prefetch/launch_daemon COMPLIANT. `./tests/test_idle_and_gpu.sh` L455-458 greps daemon log (launched via production path — no pre-set env) for ZERO `HTTP Request: GET https://huggingface.co` lines (**non-circular**; offline vars from `launch_daemon.sh` exports L71/L72). HF cache 4 repos ≈3.69 GB live. (Block below.) |
| 9 | After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM via `nvidia-smi`) and a later arm reloads; teardown is bounded (seconds, no 90 s hang) | **PASS** | lifecycle COMPLIANT (all 4 sub-audits). T6(d) 4-state **STATIC** = sole real-CUDA proof (`./tests/test_idle_and_gpu.sh`): daemon tree ABSENT after idle-unload (`total=0`), PRESENT again after re-arm reload. daemon idle-unload/bounded-shutdown/single-flight/concurrent-stop **mocked LIVE**. BUG-1 SIGTERM hang FIXED (`84f03e8`); teardown ≤~9s < `TimeoutStopSec=15`. (Block below.) |
| 10 | **Single-model arming (Rev 2, §4.2quater):** `voicectl toggle` arms the engine using ONLY `lite_model` — small.en is the sole model (it produces BOTH the live partial text and the finals; the large-model worker never loads, ~half the old two-model VRAM); there is no second mode and no mode switch; the silence gate is `asr.lite_post_speech_silence_duration` (Rev 2 default `0.8`); the graceful drain is unchanged; `status` + `state.json` report `mode` (constant `"lite"`) | **PASS** (unit + mocked LIVE + real-model LIVE; VRAM evidence REGENERATED — block below) | Single-model suite COMPLIANT (S1/S2 landed; S3 trimmed ctl to the then-5-command surface (Rev 2; seven commands today — `cancel` and `session` landed later)). Mocked **LIVE** (fast suite): `test_cfg_to_kwargs_single_model_fills_both_slots`, `test_cfg_to_kwargs_uses_lite_post_speech_silence_duration`, `test_start_arms_single_construction_and_sets_lite_mode`, `test_toggle_is_involution_single_mode`, `test_status_snapshot_has_single_model_key`, `test_dispatch_lite_commands_are_now_unknown` (all `tests/test_daemon.py`) + `test_repo_config_lite_model_comment_names_end_state_binds` (`tests/test_config_repo_default.py`). Real-model one-model invariant **LIVE** (CUDA-gated): `tests/test_feed_audio.py::test_single_model_construction` (filtered kwargs: `model == realtime_model_type`, `use_main_model_for_realtime=True` on the REAL recorder) + finals ≥ 0.70 fuzzy on small.en; `test_single_model_final_latency_within_budget` final ≤ 1500 ms best-of-3 (PRD §6 T1e; re-measured 2026-11-23 @ `8778fb2`: both tests red once under machine load — `test_single_model_construction` fuzzy-overlap, `test_single_model_final_latency_within_budget` `t_last_speech=None` — and **green on the focused re-run** (1 failed / 2 passed, 117.4s) → FLAKY class per the G1 discipline; row 1 names them). Real-process VRAM proof **REGENERATED (LIVE)** — the `./tests/test_idle_and_gpu.sh` T7 single-model block: startup line `voice-typing device resolved: device=cuda compute_type=float16 model=small.en` present, ZERO `distil-large-v3` anywhere in daemon.log (no large-model worker), `mode: lite` in status, armed VRAM **890 MiB** ∈ [512,3072] MiB (evidence block below). Silence gate = `asr.lite_post_speech_silence_duration` (default 0.8); graceful drain unchanged (29 mocked drain tests in `tests/test_daemon.py` — the shell test cannot prove drain without speech); `status` + `state.json` report `mode` (constant `"lite"`). The old T7 ≥70% finals bar is **subsumed** by `tests/test_streaming.py`'s ≥0.80 typed-screen-content asserts (same real small.en — stronger bar; that suite's 0.80 contract is untouched). |
| 11 | **Streaming (§4.2quater):** while speaking, words are typed into the focused window continuously (≥1 update/500 ms, T8a); commits revise in place (T8b); a mid-paragraph fragment never starts with a capital nor ends with a spurious period (T8c); Backspace mid-fragment cancels it — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only behavior | **PARTIAL — 2 NEW failures** (all other reds = the pre-classified `tests/G1_BASELINE.md` set; nothing hidden, nothing skipped) | Re-measured 2026-11-23 @ HEAD `8778fb2` — the row's former all-green claims ("7 of 7 streaming", "77 trio-green") were measured at an earlier HEAD and are **superseded**; every red is reconciled **by name** against `tests/G1_BASELINE.md`'s 20-row classification (no parity faking: no skips, no expectation edits). **CUDA-gated `tests/test_streaming.py` = 3 passed / 4 failed** (105.7s, real small.en — matches G1's 3-run flake-table baseline): `test_c_pause_join` / `test_d_decode_prompts` / `test_e_cancel` pass; `test_a_delta_cadence` (typed deltas ≥1 per 500 ms) + `test_b_commit_rewind_exact` (in-place revision) red = the two **(ii) watch-set** reds — stable red in ALL recorded G1 observations; `test_f_user_key_freeze` red = **(i)/F1** legacy lazy-separator (the deferred separator, got `[]`); `test_g_stranded_tail` red = **(i)/F5 FLAKY** class (5F/2P over the recorded population — single observations prove nothing). **Mocked trio** (`timeout 120 uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=line`) = **76 passed / 16 failed** (0.05s): the 16 reds are **exactly** G1's classified (i) fast set (commit×10, core×2, freeze×4; names match the 20-row table byte-for-byte) — zero NEW (the research note's predicted 76/18 did NOT reproduce at this HEAD; this session's measurement is authoritative). Rollback hatch (`output.streaming=false` → Rev 1 append-only) green: `test_on_final_streaming_false_is_verbatim_rev1_hatch` (`tests/test_daemon.py:4747`) + `test_commit_disabled_is_a_noop` (`tests/test_streaming_commit.py:329`). **Daemon `-k` regression run** (`timeout 300 uv run pytest tests/test_daemon.py -q -k "rejected_final_recovers or cancel_then_next_utterance or stop_after_cancel or on_partial_gated or user_keypress_frozen or cancel_suppression_drops or next_utterance_after_cancel" --tb=no`) = **5 passed / 2 failed**; the 2 reds are **NEW failures — not in G1's 20-row table** (G1 covers the streaming suites only), reported + escalated to the G1 owners, never reclassified here: `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` (expected `['fresh sentence', ' ']`, got `['fresh sentence ']`) + `test_on_final_user_keypress_frozen_commit_absorbs_then_unfreezes` (expected `['hello wor', ' ']`, got `['hello wor']`) — both eager-separator-shaped (HEAD's lazy separator glues the space into the next payload). Still green in that run: rejected-final recovery `test_rejected_final_recovers_at_next_speech_with_cue` + `test_on_final_streaming_rejected_final_freezes_tail_and_keeps_bookkeeping` (BUG-001; T8g tail frozen as-is, never auto-deleted, typing resumes at next speech); the re-said sentence after Backspace-cancel streams live — `test_cancel_then_next_utterance_streams_live_daemon_level` (BUG-002; T8a/T8e; the engine pins sit in the trio: `test_resume_clears_post_cancel_suppression` green, `test_cancel_then_resume_restores_live_delta_typing` (i)/F1 RED); extends-match case-insensitive pins `test_capitalized_partial_equal_length_case_only_diff_is_noop` (core) + `test_commit_extend_matches_case_insensitively` (commit) green (BUG-008; T8a; `test_mid_sentence_capitalized_partials_extend_case_insensitively` is (i)/F1 RED). The (i)-RED bugfix pins fail only on their eager-separator EXPECTATIONS, not their behaviors — e.g. `test_rejected_final_freeze_lives_until_resume_then_next_utterance_types` (`assert 3 > 3`: the post-resume empty-delta commit now types zero keystrokes by the lazy contract); reconciling them is G1's separately-decided change, never a side effect of a task. |
| 12 | **Cancel fallback:** with evdev unavailable, `voicectl cancel` performs the same rewind over the socket (T8e) and the daemon logs the listener failure once at arm | **PASS with 3 NEW daemon-level reds named in Evidence** (core cancel claims all green) | Same rewind over the socket: `tests/test_streaming.py::test_e_cancel` (cancel performs the identical rewind — `press_backspace(len(tail)−1)`, buffered audio dropped, `listening` stays on, a second cancel is a no-op) + socket surface `test_dispatch_cancel_routes_to_daemon_cancel_and_returns_shape` (`tests/test_control_socket.py:326`, green). Evdev-unavailable fallback: `voicectl cancel` armed no-op smoke — **REGENERATED shell evidence** (`[PASS] T7 cancel smoke` line + evidence block below; recorded run). Listener failure logged once at arm: `test_zero_keyboard_warning_fires_once_at_first_arm` (`tests/test_key_listener.py:459`, green). Re-said sentence after a cancel streams live (BUG-002): `test_cancel_then_next_utterance_streams_live_daemon_level` + `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` (tests/test_daemon.py, mocked **LIVE** — they drive `daemon.cancel()`, the same path `voicectl cancel` routes to). Cancel-then-stop disarms immediately — no ~5 s drain (BUG-007): `test_stop_after_cancel_disarms_immediately` + `test_next_utterance_after_cancel_rearms_final_pending` (tests/test_daemon.py); re-measured 2026-11-23 @ `8778fb2`: `timeout 300 uv run pytest tests/test_daemon.py -q -k "cancel_then_next_utterance or cancel_suppression_drops or stop_after_cancel or next_utterance_after_cancel"` → **3 passed / 1 failed** — the 1 is `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`, the NEW eager-separator-shaped red named in row 11. **D3 regression coverage (names verified at HEAD, re-measured)** — D3.2 auto-repeat compensation: `test_autorepeat_ignored` + `test_repeated_backspace_presses_route_one_cancel_each` (`tests/test_key_listener.py`, green); D3.3 suppression-window latch bound (the 4× incident sequence → drop-cap force-close + sentinel self-heal): `test_cancel_suppression_drop_cap_force_closes_window_and_processes_final`, `test_arm_clears_stale_cancel_suppression`, `test_fresh_arm_clears_suppress_since`, `test_cancel_suppression_repress_restamp_does_not_reset_drop_counter`, `test_cancel_suppression_drop_counter_resets_on_sentinel_close` (green); one re-run command: `timeout 300 uv run pytest tests/test_daemon.py tests/test_key_listener.py -q -k "autorepeat or suppression or sentinel or repeated_backspace" --tb=no` → **7 passed / 3 failed**; the 3 reds are **NEW failures, not in G1's table** (same eager-separator shape — the post-close/self-heal commit types the glued-separator payload instead of the eager standalone `' '` op), named + escalated, never reclassified: `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` (row 11's NEW red) + `test_lost_sentinel_self_heals_after_timeout` (the self-heal itself fired — `suppression window open >5.0s … closing the window and processing this final` WARNING logged — the typed-list assert carries the separator expectation) + `test_sentinel_consume_clears_suppress_since` (same shape). Core claims re-verified unchanged: socket rewind identical (`tests/test_streaming.py::test_e_cancel` green), second cancel a no-op (green), listener failure logged once at arm (`test_zero_keyboard_warning_fires_once_at_first_arm`, `tests/test_key_listener.py:459` — whole file green in the 2026-11-23 re-run: key_listener + control_socket = **64 passed**). |
| D1 | **Media ducking (§4.2quinquies — NOT a §7 row):** music playing → arm → pauses ≤~1 s and resumes at stop; `duck_mode="volume"` ducks to `duck_volume_pct` and restores exactly; user media/volume changes mid-dictation never overridden; `duck_mode="off"` byte-identical to pre-D1; flipped default engages with no `[audio]` key | **PASS** | Scripted-LIVE 2026-11-23 (HEAD `b9da1eb` at recording): `timeout 900 bash tests/d1_duck_evidence.sh` → exit 0, **12/12 scenario checks** — the five §4.2quinquies acceptance rows mapped to scripted checks incl. **107 ms** MPRIS pause after arm-return (resume at stop, also 107 ms) and the exact 40%→15%→40% volume cycle; sovereignty ×4 (user-resume honored, user-paused stays paused, mid-arm 60% kept); `off` = zero `ducking:` journal lines; default engages with `[audio]` omitted (post-flip default `mpris`). Evidence: `tests/D1_DUCK_EVIDENCE.md` (journal-line excerpts verbatim; re-runnable command above). Unit: mocked-backend `tests/test_ducking.py` + `test_ducking_mpris.py` + `test_ducking_volume.py` + `test_ducking_async.py` = **69 passed** (17.6s, re-measured @ `8778fb2`). |
| 13 | **Bulk text (§4.2sexies):** with `delivery="bulk-text"` every recognition update is visible in the focused field with no character-typing fallback; corrections replace verified owned text in one visible edit; unchanged results emit zero edits; any takeover/refusal/unknown stops delivery without retries or post-stop writes; `voicectl session [--copy]` recovers the last nonempty session; graduation to default requires G3+G6 — until then opt-in with claims reported unverified | **PASS-as-specified: shipped OPT-IN, claims reported UNVERIFIED** (G6: STAY OPT-IN) | Mode live behind `output.delivery="bulk-text"` (default `"stream-edit"` unchanged — the G6 consequence executed). Evidence (recorded lab registers, read-only): G2 controller gate **13/13** fake-target traces (`plan/008_a47116bb2b79/architecture/g2_gate_record.md`); G3 field matrix with honest rows — GTK-class full, pi-prompt **not verified** (visibility instrumentation absent; `passed:true` still counts unverified per R.2), browser insert-only (correction **REFUSED** by the ownership guard), `edit-count-law` **FAILED** ("warm-up overcount") (`g3_field_matrix.md`, `pi_row_verdicts.jsonl` 24 rows, `editor_browser_row_verdicts.jsonl` 17 rows); G4 clipboard gate L1 unprovable → refuse, L2–L6 verified (`g4_clipboard_verdicts.jsonl`); G5 timing BOTH routes failing — im-gtk backlog sustained (20 inserts / 0 corrections < 100 floor), pi-ghostty speech→visible 12.6 s median (`tests/G5_TIMING_EVIDENCE.md`); **`G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)`** — 0 of ≥3 operator writing sessions (`tests/G6_WRITING_SESSIONS.md`; decision line verbatim from `tests/G6_GRADUATION.md`); re-derive: `timeout 60 .venv/bin/python tests/g6_assessment.py`. `voicectl session [--copy]`: unit-tested (`tests/test_voicectl.py` session block), prints the recovered text exactly (no added newline), exit 1 when no completed session exists, `--copy` stages the Wayland clipboard + prints `copied N chars` and is a usage error (64) with any non-session command. |

### Evidence block — criteria 5, 6, 8, 9, 10 (verbatim from a passing `./tests/test_idle_and_gpu.sh`)

Captured on Arch Linux, kernel 7.2.7-arch1-1, NVIDIA GeForce RTX 3080 Ti (driver 615.71.09), all
faster-whisper repos prefetched under `~/.cache/huggingface/hub/` by `./install.sh`.

```
=== ACCEPTANCE EVIDENCE (paste into tests/ACCEPTANCE.md, criteria 5/6/8/9/10) ===
run1_daemon_log: /tmp/tmp.8OEnmIJcem/daemon.log
run2_daemon_log: /tmp/tmp.8OEnmIJcem/daemon2.log
idle_seconds: 120
cpu_avg_pct_of_one_core: 2.83
T6 (a) boot (absent):        0 
T6 (b) armed (present):      890 3099301
T6 (c) disarmed (present):   890 3099301
T6 (d) run2 boot (absent):   0 
T6 (d) active at stop:       890 3113149
T6 (d) after idle-unload:    0 
T6 (d) after re-arm reload:  890 3114222
T7 one-model grep:            2026-10-03 21:00:57,779 INFO __main__: voice-typing device resolved: device=cuda compute_type=float16 model=small.en (no distil-large-v3 in daemon.log)
T7 armed VRAM (single-model): 890 3099301
T7 mode:                      mode: lite
T7 cancel smoke:              ok (no-op, listening on)
voicectl_status (run 1 post-run):
  listening: off
  mode: lite
  phase: idle
  partial: 
  last: 
  uptime: 122.888s
  device: cuda (float32)
  mic: ok
  context-prompt: on
systemd_unit:
  ExecStart=__REPO__/voice_typing/launch_daemon.sh
  Restart=on-failure
offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN
=== END ACCEPTANCE EVIDENCE ===
```

Each `T6 (...)` line is `<total_MiB> <matched_pids_csv>` from `nvidia-smi --query-compute-apps`
filtered to the daemon's descendant tree: `total=0` (empty pids) = ABSENT (~0 VRAM); `total` in
[512, 3072] MiB = PRESENT (the ONE small.en model resident — Rev 2 single-mode; 890 MiB measured
this run). The `T7` lines are the single-model arming proof (criterion #10) + the armed no-op
cancel smoke (criterion #12's shell evidence); `voicectl status` NO LONGER prints a `models:`
line — the field order is listening / mode / phase / partial / last / uptime / device / mic /
context-prompt. (Regenerate with `./tests/test_idle_and_gpu.sh`.)

**T6(d-gone) PASSES via the subprocess recorder host (P1.M3.T2.S2 re-plan).** The daemon process
NEVER touches CUDA — the entire `AudioToTextRecorder` (final model + realtime model + VAD +
cuda_check) is constructed + owned in a managed CHILD subprocess (`voice_typing/recorder_host.py`
`RecorderHost`). The daemon spawns the child on first arm and terminates the child PROCESS GROUP
(`os.setsid` in the child + `os.killpg` in the daemon) on idle-unload/quit. Terminating the child
releases ALL VRAM (including the realtime-model CUDA primary context that previously stayed
resident on the daemon PID — the root cause of the 258 MiB residual). The daemon tree is therefore
ABSENT from nvidia-smi after idle-unload (`total = 0`) while the daemon keeps running, satisfying
PRD §7.9 + §6 T6(d). A re-arm respawns the child → reloads → PRESENT again.

Per-criterion PASS lines printed by the same run:

```
[PASS] T6 (a) boot: lazy-load ~0 VRAM: daemon tree ABSENT from nvidia-smi (~0 VRAM) [0 ]
[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)
[PASS] criterion 6 (un-armed boot): daemon started NOT-listening
[PASS] criterion 6 (voicectl toggle): toggle on/off ok
[PASS] T6 (b) armed: resident: daemon tree PRESENT, total=890 MiB (512-3072) [890 3099301]
[PASS] criterion 5 (no hallucination): no finals, last_final unchanged across 120s
[PASS] criterion 5 (no crash): daemon alive after 120s
[PASS] criterion 5 (CPU): avg 2.83% of one core (< 25%)
[PASS] T6 (c) disarmed: still resident: daemon tree PRESENT, total=890 MiB (512-3072) [890 3099301]
[PASS] criterion 6 (unit ExecStart): ExecStart=__REPO__/voice_typing/launch_daemon.sh
[PASS] criterion 6 (unit Restart): Restart=on-failure
[PASS] criterion 8 (no network): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (offline via launch_daemon.sh, not a test pre-set)
[PASS] T6 (boot, run 2): daemon tree ABSENT from nvidia-smi (~0 VRAM) [0 ]
[PASS] T6 (armed, run 2): daemon tree PRESENT, total=890 MiB (512-3072) [890 3113149]
[PASS] T6 (d) after 5s idle-unload: ~0 VRAM reclaimed (daemon still alive): daemon tree ABSENT from nvidia-smi (~0 VRAM) [0 ]
[PASS] T6 (d) re-arm reloads: resident again: daemon tree PRESENT, total=890 MiB (512-3072) [890 3114222]
[PASS] T7 one-model (log): device=cuda compute_type=float16 model=small.en
[PASS] T7 one-model: small.en sole model (no distil-large-v3 anywhere in daemon.log)
[PASS] T7 status: mode: lite (constant single-mode)
[PASS] T7 armed VRAM (single-model): 890 MiB in [512,3072] [890 3099301]
[PASS] T7 cancel smoke: voicectl cancel ok (no-op, no tail in flight), listening stays on
=== IDLE+GPU PASS (criteria 5, 6, 8; T6 a/b/c/d lifecycle; T7 single-model arming) ===
```

## Notes on the method

- **T4 CPU sampling** uses `/proc/<pid>/stat` (utime + stime, fields 14/15 via the last-`)` split,
  summed over the daemon's process tree, divided by `CLK_TCK` and elapsed wall-seconds). `pidstat`
  / `sysstat` is not installed; `/proc` is the zero-dependency path. The percentage is of **one**
  core (not divided by `nproc`) — PRD §6 T4 says "< 25 % of one core".
- **T6 GPU residency** is the **4-part lazy-load lifecycle** (PRD §6 T6 a/b/c/d + §4.2bis + §7.9),
  observed via `nvidia-smi --query-compute-apps=pid,used_memory` (a comma-safe 2-column query —
  `process_name` is deliberately omitted because it can contain commas) filtered to the daemon's
  **descendant process tree**: (a) at boot with NO arm the tree is **ABSENT** (~0 VRAM — the lazy-load
  guarantee; the recorder is built on the first arm, not at boot); (b) after `voicectl start` it is
  **PRESENT** with Σ used_memory ∈ [512, 3072] MiB (the ONE small.en model resident — Rev 2
  single-mode; 890 MiB measured on the regenerated run); (c) after `voicectl stop` it is
  **STILL PRESENT** (models stay resident for instant re-arm — stop does NOT unload); (d) after
  `auto_unload_idle_seconds` of disarmed idle it is **GONE** (~0 VRAM reclaimed), then a later
  `voicectl start` **reloads** → **PRESENT** again. PID presence/absence is the hard signal (the CUDA
  context); the memory range is secondary corroboration. The test runs **two daemon invocations**:
  run 1 uses the default 1800 s threshold (so T4's 120 s armed window never triggers unload and T6(c)
  stays resident) for T6(a/b/c) + T4; run 2 overrides `[asr] auto_unload_idle_seconds = 5.0` (a second
  `XDG_CONFIG_HOME` dir — only that one key differs, every other `[asr]` field inherits the same
  defaults) for T6(d). The GPU routinely hosts unrelated compute apps (e.g. a browser GPU process, or
  a parallel test daemon), so only rows whose PID is in the daemon tree are counted. The (d-gone)
  transition is **polled** (every 0.5 s up to a ~25 s ceiling), not a fixed `sleep 7` — the contract's
  literal "7 s" under-budgets the 1 s watchdog tick + 5 s threshold + ≤5 s single-flight teardown + driver
  accounting lag. T6(d-gone) relies on the daemon terminating the recorder-host CHILD PROCESS
  GROUP (the child owns ALL CUDA contexts — the daemon process never touches CUDA, so killing the
  child releases ALL VRAM while the daemon lives); if it ever FAILS, a grandchild orphaned — debug
  the process-group teardown (os.setsid/os.killpg in voice_typing/recorder_host.py), do NOT weaken
  the assertion.
- **T7 single-model arming (acceptance #10/#12)** re-arms the daemon after T6(c) and asserts the
  collapsed Rev 2 reality on the REAL host: the startup line `voice-typing device resolved:
  device=cuda compute_type=float16 model=small.en` (fires ONCE at startup via the cuda_check
  driver probe) with ZERO `distil-large-v3` matches anywhere in daemon.log (no large-model
  worker), `mode: lite` in `voicectl status` while armed (a Rev 2 constant — there is no second
  mode and no mode switch), armed VRAM inside the single-model [512, 3072] MiB window (one
  small.en ≈ 0.5–3 GB; the old two-model [1024, 5120] window would spuriously fail the low end
  and admit a two-model regression at the high end), and an armed no-op `voicectl cancel` smoke
  (cancel with no tail in flight returns ok and keeps `listening: on`, idempotent — PRD
  §4.2quater; acceptance #12's shell evidence).
- **Criterion 8** is a **non-circular** proof (bugfix Issue 1): the test does NOT pre-set the offline
  env vars. It launches the daemon via `launch_daemon.sh` (the production path — the wrapper exports
  `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`), then greps the daemon log for
  `HTTP Request: GET https://huggingface.co` and fails if any are found. Because the test itself does
  not supply the variable, a regression that removes the wrapper exports surfaces here. (The earlier
  "ran under HF_HUB_OFFLINE=1" framing was circular — it passed only because the test set the variable
  production omitted.)
- **Cleanup** (`tests/test_idle_and_gpu.sh` trap) guarantees the daemon process is gone
  and the temp dir is removed on every exit path — PASS, error, and
  Ctrl-C (`SIGINT`). The default audio source is never touched (this test listens to ambient room
  silence on the real mic).

- **Regression-test coverage (bugfix Issues 1–3).** The SIGTERM/systemctl-stop teardown path now has
  explicit automated coverage — `test_concurrent_request_shutdown_and_shutdown_only_one_stop`
  (`tests/test_daemon.py`) drives `request_shutdown()` (the signal-handler thread) and `shutdown()`
  (the main-thread `finally`) **concurrently** against a live armed daemon and asserts that exactly
  ONE `host.stop()` runs and the teardown stays bounded in time (the daemon single-flight of
  P1.M1.T2.S1 + the ≤5 s per-call budget of P1.M1.T2.S2; the recorder-host-level single-flight is
  covered by `test_concurrent_stop_calls_share_one_teardown` in `tests/test_recorder_host.py`).
  Previously only the `voicectl quit` path was exercised — which is exactly why Issue 1 (the SIGTERM
  double-teardown hang → SIGKILL + `Failed with result 'timeout'`) slipped through. Issue 2 (`phase`
  stuck `listening`/`speaking` after disarm) and Issue 3 (silent recorder-host child crash leaving
  `listening: on`) likewise now have regression tests in `tests/test_daemon.py`:
  `test_disarm_resets_phase_to_idle`, `test_toggle_off_resets_phase_to_idle`, and
  `test_auto_stop_resets_phase_to_idle` (Issue 2); `test_run_loop_detects_dead_host_and_transitions_to_unloaded`,
  `test_load_host_respawns_after_dead_child`, and `test_status_reports_unloaded_after_child_death`
  (Issue 3).
