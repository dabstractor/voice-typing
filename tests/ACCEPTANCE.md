# Acceptance evidence — voice-typing (PRD §7 definition of done)

This document records the verified evidence for PRD §7 criteria 1–12. It is the human-readable
record criterion 1 requires ("T1–T4, T6 pass, demonstrated by actual command output").

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

> **Cross-checked dossier (single source of truth):** `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md` — the P1.M5.T5.S1 go/no-go gate. Every row below is cross-referenced there with verdict + evidence + evidence-type (LIVE / STATIC / PAST-LIVE) + source artifact. **Overall verdict: GO — 9/10 PASS on substance; #7 PASS-on-substance (commit sign-off → P1.M6.T1.S3); 17/17 source gap audits COMPLIANT; 424 LIVE-green test executions this round.**

## Criteria

| # | Criterion (PRD §7) | Status | Evidence |
|---|--------------------|--------|----------|
| 1 | T1–T4, T6 pass, demonstrated by actual command output | **PASS** | **LIVE this round:** T1 `test_feed_audio.py` 9/9 (82.09s, real models); T2 unit 196 (`test_textproc.py` 21 of 196, 4.70s); daemon+recorder mocked 219 (4.79s) = **424 LIVE-green**. **STATIC + past-live:** T4 + T6 (a/b/c/d lifecycle) via `./tests/test_idle_and_gpu.sh` (block below); T3 via `./tests/e2e_virtual_mic.sh`. Evidence-TYPE split (LIVE vs STATIC vs PAST-LIVE) in the dossier §2. |
| 2 | A pause mid-dictation of ≥3 s loses zero words and does not end the session | **PASS** | `test_pause_keeps_both_halves` **LIVE** real-model (T1b — PAUSE_A + PAUSE_B both transcribed across the 3.0s gap). Drain logic COMPLIANT + 29 mocked drain tests **LIVE**. E2E `utt_pause.wav` halves fuzzy-matched through the real mic **STATIC** (`./tests/e2e_virtual_mic.sh`). Drain-clause caveat: E2E stop lands after all finals → drain guard never fires (test-COVERAGE gap, not source). |
| 3 | Live partials observable in `state.json` while audio plays | **PASS** | `feedback.py` COMPLIANT (38 unit tests **LIVE**); E2E `partials.log` non-empty via `jq -r .partial` DURING playback **STATIC** (`./tests/e2e_virtual_mic.sh`). |
| 4 | Only the daemon's typed output reaches the target — Rev 2: live partial text plus commits (§4.2quater); nothing typed while toggled off (the `listening` gates on partial and commit paths are unchanged) | **PASS** (disarm gate + Rev 2 streaming typing) | Disarm gate: the `listening` flag gates BOTH the partial and commit paths — the commit gate is on_final's first line; the partial gate is `_on_partial`'s first line (BUG-004 / P1.M1.T4.S1), pinned by `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` (mocked **LIVE** in tests/test_daemon.py). E2E CRIT4 `before==after` after `voicectl stop` + one more WAV **STATIC** (`./tests/e2e_virtual_mic.sh`). Rev 2 streaming typing **LIVE** (CUDA-gated real model): `tests/test_streaming.py::test_a_delta_cadence` (partial text typed into the target ≥1 update per 500 ms while speaking) + `test_b_commit_rewind_exact` (finals commit and revise the already-typed text in place); suite 7/7 green via `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v`. |
| 5 | Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use | **PASS** | `textproc.clean()` blocklist PASS (21 unit tests **LIVE**). T4 shell **STATIC = authoritative**: `IDLE_SECS=120`, no-finals double-signal, CPU `avg < 25%` of one core, `kill -0` no-crash (`./tests/test_idle_and_gpu.sh`). Mocked guard **LIVE** (`test_on_final_rejects_hallucination` L667). Past-live CPU **1.67–14 %** (< 25 %). Two-layer mitigation VAD + blocklist. (Block below.) |
| 6 | `voicectl toggle/start/stop/status/quit` all work; systemd user service; starts un-armed; auto-restarts on failure | **PASS** | socket (35) + voicectl (32) + systemd (15) + status_sh (5) COMPLIANT, all **LIVE** unit tests. daemon lazy-boot/status/dead-child **mocked LIVE**. Unit `ExecStart → launch_daemon.sh` + `Restart=on-failure` **STATIC** grep in `./tests/test_idle_and_gpu.sh`. VT-003/VT-004 fixed in-source; VT-001 = doc-drift only (→ P1.M6.T1.S2). (Block below.) |
| 7 | Everything committed to git; README documents install / hotkey / config / troubleshooting / CPU-only mode | **PASS-on-substance** (commit sign-off → **P1.M6.T1.S3**) | README **9/9** sections PRESENT + committed (Install L23, Hotkey L79, Lite mode L118, Configuration L152, CPU-only L202, cuDNN L231, Wrong microphone L258, wtype vs ydotool L276). Impl + tests committed (verify commits `361111a`…`d720df5`). `git status --short`: tree clean of shipped impl/doc files. Formal "everything committed" sign-off owned by **P1.M6.T1.S3** (incl. this gate's deliverables). |
| 8 | No network access needed at runtime (models cached by install) | **PASS** | install/prefetch/launch_daemon COMPLIANT. `./tests/test_idle_and_gpu.sh` L455-458 greps daemon log (launched via production path — no pre-set env) for ZERO `HTTP Request: GET https://huggingface.co` lines (**non-circular**; offline vars from `launch_daemon.sh` exports L71/L72). HF cache 4 repos ≈3.69 GB live. (Block below.) |
| 9 | After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM via `nvidia-smi`) and a later arm reloads; teardown is bounded (seconds, no 90 s hang) | **PASS** | lifecycle COMPLIANT (all 4 sub-audits). T6(d) 4-state **STATIC** = sole real-CUDA proof (`./tests/test_idle_and_gpu.sh`): daemon tree ABSENT after idle-unload (`total=0`), PRESENT again after re-arm reload. daemon idle-unload/bounded-shutdown/single-flight/concurrent-stop **mocked LIVE**. BUG-1 SIGTERM hang FIXED (`84f03e8`); teardown ≤~9s < `TimeoutStopSec=15`. (Block below.) |
| 10 | **Single-model arming (Rev 2, §4.2quater):** `voicectl toggle` arms the engine using ONLY `lite_model` — small.en is the sole model (it produces BOTH the live partial text and the finals; the large-model worker never loads, ~half the old two-model VRAM); there is no second mode and no mode switch; the silence gate is `asr.lite_post_speech_silence_duration` (Rev 2 default `0.8`); the graceful drain is unchanged; `status` + `state.json` report `mode` (constant `"lite"`) | **PASS** (unit + mocked LIVE + real-model LIVE; VRAM evidence REGENERATED — block below) | Single-model suite COMPLIANT (S1/S2 landed; S3 trimmed ctl to the 5-command surface). Mocked **LIVE** (fast suite): `test_cfg_to_kwargs_single_model_fills_both_slots`, `test_cfg_to_kwargs_uses_lite_post_speech_silence_duration`, `test_start_arms_single_construction_and_sets_lite_mode`, `test_toggle_is_involution_single_mode`, `test_status_snapshot_has_single_model_key`, `test_dispatch_lite_commands_are_now_unknown` (all `tests/test_daemon.py`) + `test_repo_config_lite_model_comment_names_end_state_binds` (`tests/test_config_repo_default.py`). Real-model one-model invariant **LIVE** (CUDA-gated): `tests/test_feed_audio.py::test_single_model_construction` (filtered kwargs: `model == realtime_model_type`, `use_main_model_for_realtime=True` on the REAL recorder) + finals ≥ 0.70 fuzzy on small.en; `test_single_model_final_latency_within_budget` final ≤ 1500 ms best-of-3 (PRD §6 T1e). Real-process VRAM proof **REGENERATED (LIVE)** — the `./tests/test_idle_and_gpu.sh` T7 single-model block: startup line `voice-typing device resolved: device=cuda compute_type=float16 model=small.en` present, ZERO `distil-large-v3` anywhere in daemon.log (no large-model worker), `mode: lite` in status, armed VRAM **890 MiB** ∈ [512,3072] MiB (evidence block below). Silence gate = `asr.lite_post_speech_silence_duration` (default 0.8); graceful drain unchanged (29 mocked drain tests in `tests/test_daemon.py` — the shell test cannot prove drain without speech); `status` + `state.json` report `mode` (constant `"lite"`). The old T7 ≥70% finals bar is **subsumed** by `tests/test_streaming.py`'s ≥0.80 typed-screen-content asserts (same real small.en — stronger bar; that suite's 0.80 contract is untouched). |
| 11 | **Streaming (§4.2quater):** while speaking, words are typed into the focused window continuously (≥1 update/500 ms, T8a); commits revise in place (T8b); a mid-paragraph fragment never starts with a capital nor ends with a spurious period (T8c); Backspace mid-fragment cancels it — text rewound, mic still armed (T8e); stranded fragments freeze, never auto-delete (T8g); `output.streaming=false` restores Rev 1 append-only behavior | **PASS** | `tests/test_streaming.py` — CUDA-gated real-model suite, 7/7 green via `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v`: `test_a_delta_cadence` (typed deltas ≥1 per 500 ms while speaking), `test_b_commit_rewind_exact` (commits revise the typed text in place, exact rewind), `test_c_pause_join` (joined fragment: no mid-paragraph capital, no spurious trailing period), `test_e_cancel` (Backspace mid-fragment: text rewound, mic stays armed), `test_g_stranded_tail` (stranded fragments freeze, never auto-delete). Rollback hatch (`output.streaming=false` → Rev 1 append-only): `test_on_final_streaming_false_is_verbatim_rev1_hatch` (`tests/test_daemon.py:4510`) + `test_commit_disabled_is_a_noop` (disabled-engine commit no-op, `tests/test_streaming_commit.py:307`). |
| 12 | **Cancel fallback:** with evdev unavailable, `voicectl cancel` performs the same rewind over the socket (T8e) and the daemon logs the listener failure once at arm | **PASS** | Same rewind over the socket: `tests/test_streaming.py::test_e_cancel` (cancel performs the identical rewind — `press_backspace(len(tail)−1)`, buffered audio dropped, `listening` stays on, a second cancel is a no-op) + socket surface `test_dispatch_cancel_routes_to_daemon_cancel_and_returns_shape` (`tests/test_control_socket.py:278`). Evdev-unavailable fallback: `voicectl cancel` armed no-op smoke — **REGENERATED shell evidence** (`[PASS] T7 cancel smoke` line + evidence block below). Listener failure logged once at arm: `test_zero_keyboard_warning_fires_once_at_first_arm` (`tests/test_key_listener.py:459`). |

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
  device: cuda (float16)
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
