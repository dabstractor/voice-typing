# Research: T7 lite feed-audio integration test (P1.M2.T1.S1)

Target: the PRD §6 **T7** lite-mode integration test. Two complementary parts:
- **Part A** — `tests/test_feed_audio.py`: a CUDA-gated pytest that builds the REAL lite recorder, proves ONE model (`use_main_model_for_realtime=True` reached the real recorder), feeds `utt_simple.wav`, asserts finals + fuzzy-accuracy ≥70%, and asserts lite final-latency is materially lower than normal.
- **Part B** — `tests/test_idle_and_gpu.sh`: a voicectl-driven mode-switch roundtrip (toggle-lite→lite, toggle-lite→disarm, toggle→reload normal, status→mode) + an optional VRAM≈half comparison. (The contract's "OR drive voicectl" option — avoids complex pytest daemon+subprocess-host construction.)

This is a **test-only** task. All lite source interfaces are LANDED (P1.M1.T1 + the parallel P1.M1.T2).

---

## 1. What's already landed (consume, don't rebuild) — verified in the code

- `cfg_to_kwargs(cfg, *, resolved=None, lite=False)` (daemon.py:158) — lite branch (184/206) sets `model = realtime_model_type = lite_model` + `use_main_model_for_realtime=True`; CPU lite substitute `tiny.en`. **`lite_model` config field = "small.en"** (config.py AsrConfig:54).
- `build_recorder(cfg, feedback, latency=None, force_cpu=False, on_speech=None, lite=False)` (daemon.py:313) → `_construct(..., lite=lite)`.
- Daemon mode-switch: `_load_host(mode="normal")` (686) spawns the RecorderHost with `mode`, sets `self._mode` (632/754); `start_lite()` (1326), `toggle_lite()` (1368); `_arm()` calls `feedback.set_mode(self._mode)` (980); `status_snapshot()` carries `mode` (~1501).
- Socket `_dispatch` handles `toggle-lite`/`start-lite` (~1829); `ctl.py _COMMANDS` has them (35) + renders `mode` (67/88); `feedback.set_mode` (145) + `_state["mode"]` (99); `status.sh` ⚡/🎤 render (42-51).
- The **one-model fact is VERIFIED** (architecture/realtimestt_lite_mode_verification.md): `use_main_model_for_realtime=True` → RealtimeSTT v1.0.2 `_initialize_realtime_transcription_model` early-returns → exactly ONE model loads (large final never constructed).

## 2. Non-duplication boundaries (DO NOT re-test what siblings own)

- **P1.M1.T1.S2 (Complete)** = "kwargs×mode×force_cpu unit tests" → `cfg_to_kwargs(lite=True)` one-model KWARGS are already unit-tested. T7 does NOT re-assert kwargs in isolation; instead it asserts the REAL constructed recorder carries `use_main_model_for_realtime=True` (the integration-grade proof that the lite kwargs reached the actual AudioToTextRecorder, not just the dict).
- **P1.M1.T2.S2 (parallel, Implementing)** = UNIT mode-switch tests with MOCKED hosts (test_daemon.py mode-switch teardown stop_calls; idle-unload→start_lite; test_control_socket.py dispatch status carries `mode`). T7's Part B is the INTEGRATION counterpart (REAL daemon + REAL voicectl + REAL model reload) — the only thing unit tests can't prove (a real mode-switch reload actually tears down + respawns with real models + status reports the mode end-to-end).

## 3. test_feed_audio.py structure (the file Part A extends) — verified

- **Skip guards**: `pytestmark = pytest.mark.skipif(not _have_wavs())` (~123) — skips the whole file when WAVs/deps absent (keeps the fast sweep green on a CPU/clone box). Heavy deps imported lazily in `_load_deps()` (~81) + the `recorder` fixture (~253), NEVER at module top (preserves test_voicectl.py import purity).
- **`recorder` session fixture** (253-300): `cfg_to_kwargs(cfg)` → `use_microphone=False` → wire `on_realtime_transcription_stabilized/on_vad_start/on_vad_stop` + `no_log_file=True` → `_filter_kwargs_to_signature` → construct `AudioToTextRecorder(**filtered)` → yield `(rec, col)` → `_safe_shutdown` on a helper thread (join 30s). **A lite variant mirrors this with `cfg_to_kwargs(cfg, lite=True)`.**
- **`_Collector`** (157): `finals`, `partials`, `t_speech_start/end`, `add_partial/on_vad_start/on_vad_stop/add_final/reset`.
- **`_run_utterance(rec, col, wav, want_finals)`** (306): resets, starts consume+feed threads, waits for `want_finals`, aborts on a helper thread. **Reusable as-is for the lite test.**
- **`_token_overlap(hyp, ref)`** (142): multiset intersection / ref-length, case+punct-insensitive. **The ≥70% assertion uses this (lower bar than normal's 0.80).**
- **`SIMPLE_TEXT`** + **`_WAVS["simple"]`** (the canonical utt_simple target + path).
- **`test_final_latency`** (414, CUDA-gated): measures `t_final - t_last_speech` directly (it does NOT parse the daemon log — test_feed_audio builds the recorder DIRECTLY, so the daemon's `voice-typing latency:` line is never emitted here). **The lite latency test mirrors this direct measurement for normal+lite and compares.**
- **Latency log line** (daemon.py:951): `"voice-typing latency: event=%s speech_end_to_final_ms=%s final_to_typed_ms=%s total_ms=%s ..."`. Emitted by the DAEMON's on_final — relevant only to Part B (live daemon), NOT to the pytest (direct recorder).

## 4. Part A design (test_feed_audio.py) — CUDA-gated, real lite recorder

- **`lite_recorder` session fixture**: copy `recorder`, swap `cfg_to_kwargs(cfg)` → `cfg_to_kwargs(cfg, lite=True)`. Same teardown. (Both fixtures are session-scoped → normal + lite recorders coexist for the latency-comparison test.)
- **`test_lite_feed_audio_utt_simple`** (CUDA-gated via `daemon.cuda_check.is_cuda_available()` like test_final_latency): `rec, col = lite_recorder`; **assert `rec.use_main_model_for_realtime is True`** (the real recorder got the one-model flag — the integration one-model proof); `_run_utterance(rec, col, _WAVS["simple"], want_finals=1)`; assert finals non-empty + `_token_overlap(joined, SIMPLE_TEXT) >= 0.70` (lower bar — small.en is the final model).
- **`test_lite_latency_lower_than_normal`** (CUDA-gated): run utt_simple through BOTH the shared `recorder` (normal) and `lite_recorder`, measuring `t_final - t_last_speech` each (the test_final_latency timing wrap), assert `lite_ms < normal_ms` (the small model is genuinely faster). No rigid ratio (espeak/GPU variance) — strict `<` is the materially-lower bar.

## 5. Part B design (test_idle_and_gpu.sh) — voicectl mode-switch roundtrip + optional VRAM

The contract's "OR drive voicectl" option. test_idle_and_gpu.sh already stands up the REAL daemon (launch_daemon.sh) + drives voicectl + nvidia-smi tree checks. Add a **T7 section at the END of Run 1** (after T6(c), when the daemon is up + was armed in normal mode — placing it last avoids corrupting the existing T6 assertions):

1. `voicectl toggle-lite` → assert the response (or a follow-up `voicectl status`) reports `mode: lite` / `"mode":"lite"`. (This triggers a real mode-switch reload: tear down the normal host, spawn the lite host.)
2. VRAM snapshot (optional, "if cheap"): `vram_tree_state "$DAEMON_PID"` while lite-armed; later compare to the normal-armed snapshot — lite should be materially lower (≈half; small.en only vs distil-large-v3+small.en). Use `daemon_tree_pids`/`vram_tree_state` helpers (227). Assert lite_total < normal_total (best-effort; no rigid ratio).
3. `voicectl toggle-lite` → disarm (listening off; mode stays lite).
4. `voicectl toggle` → mode-switch reload to normal. Assert `voicectl status` reports `mode: normal`. (One reload — the transition lite→normal is exactly one host respawn; assert via the mode field + optionally a journal grep for a single reload line.)
5. `voicectl status` → assert `mode: normal`.

Helpers available: `vram_tree_state` (227), `daemon_tree_pids` (205), `assert_vram_present` (263), voicectl wrapped with a timeout (153). The mode field renders in `voicectl status` (ctl.py format_result @67/88) + the socket response (`{"ok":true,...,"mode":"lite"}`). **Document the T7 section's purpose in a comment (Mode A).**

## 6. CUDA-gating + suite hygiene (verified conventions)

- Part A tests are CUDA-gated (skip when `not daemon.cuda_check.is_cuda_available()`) — mirrors test_final_latency (G-CPU). The non-CPU `lite_recorder` fixture + the accuracy/latency assertions only run on GPU.
- The `use_main_model_for_realtime is True` assertion is CUDA-FREE (it's a constructed-recorder attribute) but lives in the CUDA-gated test (grouped with T7; the whole file skips without WAVs/deps anyway).
- test_feed_audio.py is NOT collected by the fast sweep when WAVs/deps are absent (pytestmark). The new tests inherit that skip → the fast `pytest tests/ --ignore=tests/test_feed_audio.py` (and even `pytest tests/`) stays green on a CPU/clone box.
- test_idle_and_gpu.sh is a heavy shell test (NOT in pytest) — run explicitly. Adding the T7 section keeps it out of the fast sweep.

## 7. Scope + parallel context

- **Files edited**: `tests/test_feed_audio.py` (Part A) + `tests/test_idle_and_gpu.sh` (Part B). **NO source** (daemon.py/recorder_host.py/ctl.py/feedback.py/status.sh/config.py — all landed by P1.M1). NO new files.
- **P1.M1.T2.S2 (parallel)**: owns UNIT mode-switch tests (test_daemon.py + test_control_socket.py). NO file overlap with Part A (test_feed_audio.py) or Part B (test_idle_and_gpu.sh). T7 is the integration counterpart.
- **Consumed by**: P1.M2.T2 (docs reference T7) + P1.M2.T3 (final verify runs T7).
- pytest>=9.1.1 (NO ruff/mypy). Full paths in bash (`.venv/bin/python`, zsh aliases: python3→uv run).
