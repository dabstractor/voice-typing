# Acceptance evidence — voice-typing (PRD §7 definition of done)

This document records the verified evidence for PRD §7 criteria 1–8. It is the human-readable
record criterion 1 requires ("T1–T4, T6 pass, demonstrated by actual command output").

Regenerate the **5 / 6 / 8** block by running `./tests/test_idle_and_gpu.sh` and pasting its
`=== ACCEPTANCE EVIDENCE ===` output into the fenced block below. Criteria **1–4** are demonstrated
by the sibling test commands (T1/T2/T3); criterion **7** by `git status` + the README task.

## How to reproduce the 5 / 6 / 8 evidence

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true   # preflight refuses if it is running
./tests/test_idle_and_gpu.sh                              # ~3–4 min (model load + 120 s idle)
# → prints per-criterion PASS lines + an '=== ACCEPTANCE EVIDENCE ===' block; exit 0
```

Preconditions: models prefetched (`./install.sh`), a CUDA GPU, `jq` + `/usr/bin/tmux` +
`/usr/bin/nvidia-smi` present, and a **quiet room** (the test listens to ambient silence on the
real default mic — it does NOT swap the audio source, so ambient speech could produce a real final
and spuriously fail the "no finals" assertion).

## Criteria

| # | Criterion (PRD §7) | Status | Evidence |
|---|--------------------|--------|----------|
| 1 | T1–T4, T6 pass, demonstrated by actual command output | PASS | T4 + T6: `./tests/test_idle_and_gpu.sh` (block below, exit 0). T1: `uv run pytest tests/test_feed_audio.py -v`. T2: `uv run pytest tests/test_textproc.py -v`. T3: `./tests/e2e_virtual_mic.sh`. |
| 2 | A pause mid-dictation of ≥3 s loses zero words and does not end the session | PASS (via T3 / T1b) | `./tests/e2e_virtual_mic.sh` — `utt_pause.wav` halves PAUSE_A + PAUSE_B both fuzzy-matched across the 3.0 s gap (the WhisperX-flaw regression). |
| 3 | Live partials observable in `state.json` while audio plays | PASS (via T3) | `./tests/e2e_virtual_mic.sh` — ≥1 non-empty `partial` snapshot captured during playback. |
| 4 | Only finalized text reaches the target; nothing typed while toggled off | PASS (via T3) | `./tests/e2e_virtual_mic.sh` — capture-pane unchanged after `voicectl stop` while one more WAV plays. |
| 5 | Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — 120 s armed silence, no finals typed, `last_final` unchanged, avg **2.56 %** of one core. (Block below.) |
| 6 | `voicectl toggle/start/stop/status/quit` all work; systemd user service; starts un-armed; auto-restarts on failure | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — every subcommand returned `ok`; `listening: off` right after ready; unit `ExecStart → launch_daemon.sh` + `Restart=on-failure`. (Block below.) |
| 7 | Everything committed to git; README documents install / hotkey / tmux / config / troubleshooting / CPU-only mode | partial | `git status` — implementation committed on `main`; the README is task **P2.M1.T2.S1** (pending), which will document install, the hotkey snippet, the tmux status snippet, the config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and CPU-only mode. |
| 8 | No network access needed at runtime (models cached by install) | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — the daemon ran the entire test under `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` and loaded the cached models (went ready + survived 120 s armed idle). (Block below.) |

### Evidence block — criteria 5, 6, 8 (verbatim from a passing `./tests/test_idle_and_gpu.sh`)

Captured on Arch Linux, kernel 7.0.12-arch1-1, NVIDIA RTX 3080 Ti (driver 610.43.02), all four
faster-whisper repos prefetched under `~/.cache/huggingface/hub/` by `./install.sh`.

```
=== ACCEPTANCE EVIDENCE (paste into tests/ACCEPTANCE.md, criteria 5/6/8) ===
daemon_pid: 2499875
idle_seconds: 120
cpu_avg_pct_of_one_core: 2.56
nvidia_smi_compute_apps (daemon tree): matched=[(2499875, 2804)] total_MiB=2804
voicectl_status:
  listening: off
  partial:
  last:
  uptime: 120.476s
  device: cuda (float16)
  models: distil-large-v3 + small.en
systemd_unit:
  ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
  Restart=on-failure
offline_env: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
=== END ACCEPTANCE EVIDENCE ===
```

Per-criterion PASS lines printed by the same run:

```
[PASS] criterion 6 (un-armed boot): daemon started NOT-listening
[PASS] criterion 6 (voicectl toggle): toggle on/off ok
[PASS] criterion 5 (no hallucination): no finals typed, last_final unchanged across 120s
[PASS] criterion 5 (no crash): daemon alive after 120s
[PASS] criterion 5 (CPU): avg 2.56% of one core (< 25%)
[PASS] criterion 6/T6 (GPU residency): matched=[(2499875, 2804)] total_MiB=2804 (range 1024-5120 MiB)
[PASS] criterion 6 (unit ExecStart): ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
[PASS] criterion 6 (unit Restart): Restart=on-failure
[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded cached models
```

## Notes on the method

- **T4 CPU sampling** uses `/proc/<pid>/stat` (utime + stime, fields 14/15 via the last-`)` split,
  summed over the daemon's process tree, divided by `CLK_TCK` and elapsed wall-seconds). `pidstat`
  / `sysstat` is not installed; `/proc` is the zero-dependency path. The percentage is of **one**
  core (not divided by `nproc`) — PRD §6 T4 says "< 25 % of one core".
- **T6 GPU residency** matches the daemon's **descendant process tree** against
  `nvidia-smi --query-compute-apps=pid,used_memory` (a comma-safe 2-column query — `process_name`
  is deliberately omitted because it can contain commas). The GPU routinely hosts unrelated compute
  apps (e.g. a browser GPU process, or a parallel test daemon), so only rows whose PID is in the
  daemon tree are summed.
- **Criterion 8** is proven by the run itself: the daemon was launched with `HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1`, which is a hard offline switch. That it went ready and survived 120 s of
  armed idle is empirical proof the models load from the local cache with zero network access.
- **Cleanup** (`tests/test_idle_and_gpu.sh` trap) guarantees the daemon process is gone, the
  `vtidle` tmux session is gone, and the temp dir is removed on every exit path — PASS, error, and
  Ctrl-C (`SIGINT`). The default audio source is never touched (this test listens to ambient room
  silence on the real mic).
