# Research findings — P1.M3.T9.S1 (existing-suite adjustments + ACCEPTANCE.md rows)

Collected by direct codebase inspection (git @ 64c57fa, post-T8).

## 1. Verified breakage / staleness (the reason this item exists)

### tests/test_feed_audio.py (881 lines, last touched pre-Rev2)
- L311–348 `lite_recorder` fixture calls `daemon.cfg_to_kwargs(cfg, lite=True)` → **TypeError**:
  `cfg_to_kwargs(cfg, *, resolved=None)` is the collapsed signature (daemon.py:169). The suite is
  currently BROKEN at fixture setup for any test requesting `lite_recorder`.
- L253 `recorder` fixture calls `daemon.cfg_to_kwargs(cfg)` — under the collapse this ALREADY
  produces the single-model kwargs: `model == realtime_model_type == resolved["model"]` (small.en),
  `use_main_model_for_realtime=True`, endpointer `lite_post_speech_silence_duration` (daemon.py:185-199).
- L653 `test_lite_feed_audio_utt_simple` (T7 a/b: one model + finals ≥0.70) and L679
  `test_lite_latency_lower_than_normal` (T7 c: lite vs normal best-of-3 ≤1.25×) — both lite-vs-normal
  comparisons; normal mode no longer exists.
- L447 `test_fuzzy_accuracy` asserts ≥0.80 — that was the distil-large-v3 finals bar (PRD §6 T1d).
  Post-collapse finals come from small.en; PRD's small.en bar is ≥0.70 (PRD §6 T7b: "fuzzy-accuracy
  ≥70% ... since small.en is the final model"). Same for any other ≥0.80 finals asserts in this file.

### tests/test_idle_and_gpu.sh (740 lines)
- L535–~L633: the **T7 lite mode-switch roundtrip** block — `voicectl toggle-lite` (now exit 64
  usage error; ctl.py `_COMMANDS = {toggle,start,stop,status,cancel,quit}`), polls `mode: normal`
  (mode is now constant `lite` — daemon.py:2128). Script currently dies at L562.
- L137-138 `VRAM_MIN_MIB=1024 / VRAM_MAX_MIB=5120` — two-model window; single small.en ≈ 0.5–3 GB
  (contract: widen to ~0.5–3 GB → 512/3072).
- Evidence block (~L700) prints `T7 normal-armed VRAM` / `T7 lite-armed VRAM`; final result gate
  includes `$T7_OK`; final PASS banner mentions "T7 lite mode-switch". All stale.
- Header comments still describe T7 as lite mode-switch (L~30, L90-96 mention criteria 5/6/8/9 only).

### tests/ACCEPTANCE.md
- Rows 1–10 only; header says "criteria 1–10". Rev 2 PRD §7 has 12 criteria.
- Row #4: "streaming-typing evidence PENDING → P1.M3.T8/T9" — T8 is now Complete; evidence exists.
- Row #10: text already rewritten (single-model) but Status says "VRAM evidence regenerates →
  P1.M3.T9.S1" and the evidence block is explicitly "the pre-Rev-2 historical capture — T9.S1 owns
  regeneration".
- Rows #11 (streaming) and #12 (cancel fallback) do not exist.
- Evidence-block template prints `models: distil-large-v3 + small.en (loaded)` — **stale**: status
  no longer prints a models line. Current `voicectl status` output (ctl.py:105-115):
  `listening / mode / phase / partial / last / uptime / device: cuda (float16) / mic: … /
  context-prompt: …`.

## 2. New-world API truths to assert against (verified in source)

- `voicectl` surface: `toggle|start|stop|status|cancel|quit` (ctl.py:21,45-46). `cancel` is NOT an
  arm command (no loading hint; plain send_command — ctl.py:122,230).
- Daemon status payload: `"mode": "lite"` constant (daemon.py:2128), plus `context_prompt` label
  (on / off (disabled by config) / off (degraded) / off (models not loaded) — ctl.py:100-103).
- Startup log line (daemon.py:1106-1109): `voice-typing device resolved: device=%s compute_type=%s
  model=%s` logged ONCE at startup (driver probe, not model load). On the CUDA box: `device=cuda
  compute_type=float16 model=small.en`. → grep target for the one-model invariant;
  `distil-large-v3` must appear NOWHERE in daemon.log.
- `cfg_to_kwargs` (daemon.py:169-199): single model fills both slots; `use_main_model_for_realtime=
  True`; CPU fallback swaps wholesale to tiny.en via cuda_check.CPU_FALLBACK.
- Config schema (config.toml / config.py): `[asr] lite_model` is the only model key;
  `lite_post_speech_silence_duration=0.8` default; `[output] streaming=true` default; `[cancel]
  on_backspace/devices`.
- Rollback hatch (`streaming=false`) coverage EXISTS: test_streaming_commit.py:304-308 (disabled
  engine → commit no-op), test_streaming_core.py:299, test_daemon.py:4510
  `test_on_final_streaming_false_is_verbatim_rev1_hatch` + :4544.
- T8 suite (tests/test_streaming.py, CUDA-gated, real models): test_a_delta_cadence, test_b_commit_
  rewind_exact, test_c_pause_join, test_d_decode_prompts, test_e_cancel, test_f_user_key_freeze,
  test_g_stranded_tail. Fuzzy asserts are ≥0.80 on TYPED SCREEN content vs pinned refs (lines
  979, 1136-1138, 1254, 1477) — this SUBSUMES the old T7 ≥0.70 finals bar (0.80 > 0.70, same real
  small.en models). → "verify ≥70% lives in test_streaming.py" resolves to YES-at-0.80; no new test.
- Mocked cancel/listener coverage for row #12: tests/test_key_listener.py (synthetic evdev parser),
  tests/test_control_socket.py (cancel cmd), tests/test_streaming.py test_e_cancel (socket cancel →
  press_backspace(len(tail)−1), audio dropped, listening stays on).
- Drain coverage: 29 mocked drain tests in tests/test_daemon.py (per ACCEPTANCE row #2) — row #10's
  "drain unchanged" clause points there; the shell test cannot prove drain without speech.

## 3. validate.sh inventory gap (adjacent, flag in PRP)

validate.sh phase 2 runs 16 pytest files but was written (1022277, Oct 2 21:39) BEFORE
tests/test_context_prompt_refresh.py (Oct 3 01:11) landed — that suite is not in any phase.
tests/test_streaming.py (T8, CUDA) is also not in phase 3 (which runs only test_feed_audio.py).
Contract names only the three files; the PRP marks the phase-2 one-liner as a low-risk addition
justified by the item OUTPUT ("all suites green under the single-mode + streaming world") and
leaves phase-3/validate.sh CUDA additions out of scope.

## 4. Run-environment constraints (AGENTS.md — must be encoded in the PRP)

- Two timeouts on every non-trivial command (inner GNU `timeout` + bash-tool timeout above it).
- `voicectl` ALWAYS under `timeout 30` (control socket has no read timeout).
- Never foreground the daemon; the shell suite stands up its own daemon via launch_daemon.sh and
  tears it down via trap — give the harness timeout **900**, stop the systemd unit first, never
  interrupt mid-run.
- Preflight refuses if `voicectl status` answers or the unit is active.
- QUIET ROOM precondition for the 120 s armed-silence window (real default mic, ambient speech risk).
- Shell suite ≈ 5–8 min: 2 cold inits + 120 s idle + idle-unload waits.
- CUDA pytest: `timeout 600-900 .venv/bin/python -m pytest <file> -q`; prefer single files.
- Explicit paths: `.venv/bin/python`, `/home/dustin/.local/bin/uv` (shell aliases exist).

## 5. Line-number map (test_idle_and_gpu.sh @ HEAD)

- L137-138 VRAM_MIN_MIB/VRAM_MAX_MIB
- L535 T7 banner; L548 `T7_OK=0`; L562 first `toggle-lite`; L599 `toggle` reload poll; ~L631
  final `voicectl stop || true` ending the block; ~L700-701 evidence `T7 …VRAM` echo lines;
  ~L737-745 final result gate `IDLE_OK/T6_OK/T7_OK` + PASS banner text.
