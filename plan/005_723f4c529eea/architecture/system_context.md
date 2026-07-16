# System Context — voice-typing Round 005

## Project State

The voice-typing project is **NOT** a greenfield repo — it is a mature, ~12,600-line implementation
with 30+ git commits, a 2133-line daemon, a 755-line recorder-host child process, a comprehensive
239-test suite (all passing), and working systemd service + Hyprland keybinds. Previous planning
rounds (001–004) implemented the full PRD: lazy model lifecycle, graceful drain, idle auto-stop,
idle unload with bounded teardown, lite mode (single-model), control socket, feedback, typing
backends, and documentation.

## This Round's Scope

**One focused change:** Add the `lite_post_speech_silence_duration` config field (PRD §4.2ter, §4.5)
that was introduced into PRD.md in commit a66b9d4 ("Refine Lite mode latency via silence gate") but
**never implemented** in code.

### The Gap

The PRD §4.2ter "latency note" identifies that the silence gate (`post_speech_silence_duration`),
NOT the model size, is the perceived-latency bottleneck. Lite mode (single small.en model) is ~1.6×
faster at transcription than normal mode (distil-large-v3), but the ~50 ms transcription win is
**swamped** by the identical silence wait. The PRD therefore mandates that lite mode use its own
shorter `post_speech_silence_duration` (default 0.5 s vs normal's 0.6 s), cutting stop→text latency
from ~1.6 s to ~0.6 s.

**Current code:** `cfg_to_kwargs(cfg, lite=True)` in `daemon.py` (line 203) uses the SAME
`cfg.asr.post_speech_silence_duration` for both modes. The config field
`lite_post_speech_silence_duration` does NOT exist in `config.py`, `config.toml`, or any test.

### Files That Must Change

| File | Change |
|---|---|
| `voice_typing/config.py` | Add `lite_post_speech_silence_duration: float = 0.5` to `AsrConfig` + add to `__post_init__` numeric validation tuple |
| `config.toml` | Add the field with a self-documenting comment (must stay in lockstep with config.py per the repo-default drift-guard test) |
| `voice_typing/daemon.py` | In `cfg_to_kwargs()`, when `lite=True`, override `post_speech_silence_duration` kwarg with `cfg.asr.lite_post_speech_silence_duration` |
| `tests/test_config_repo_default.py` | Add `lite_post_speech_silence_duration` to the expected `[asr]` key set (18 keys total, was 17); update docstring count |
| `tests/test_config.py` | Add round-trip + default + wrong-type tests for the new field |
| `tests/test_daemon.py` | Update `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` to add `post_speech_silence_duration` to the `differing` set; add a dedicated assertion that lite uses the shorter value |
| `README.md` | Add `lite_post_speech_silence_duration` to the config tuning table; update Lite mode section to mention the silence-gate optimization |

### Files That Do NOT Need Changes (verified)

- `voice_typing/recorder_host.py` — `_worker_main` calls `build_recorder(cfg, ..., lite=lite)` which
  calls `cfg_to_kwargs(cfg, ..., lite=lite)`. The kwargs fix propagates automatically.
- `voice_typing/feedback.py`, `textproc.py`, `typing_backends.py`, `ctl.py` — no silence-duration
  awareness.
- `tests/test_feed_audio.py` — the `lite_recorder` fixture calls `cfg_to_kwargs(cfg, lite=True)`,
  so it will automatically receive the shorter silence duration after the daemon fix. The existing
  T7 tests (`test_lite_feed_audio_utt_simple`, `test_lite_latency_lower_than_normal`) will pass
  unchanged (latency comparison only becomes easier to satisfy).
- `tests/e2e_virtual_mic.sh`, `tests/test_idle_and_gpu.sh` — no silence-duration assertions.

## Architecture: Key Design Patterns to Follow

1. **Config schema is the single source of truth.** `config.py` dataclass defaults mirror
   `config.toml` EXACTLY. The drift-guard test `test_repo_config_toml_equals_defaults` asserts
   equality, so config.py and config.toml changes MUST land atomically.

2. **Type validation in `__post_init__`.** `AsrConfig.__post_init__` validates numeric fields reject
   `bool` and non-numeric types, raising `TypeError` at load time. `lite_post_speech_silence_duration`
   must be added to the numeric-fields validation tuple.

3. **`cfg_to_kwargs` is the single point where config flows into recorder kwargs.** The `lite`
   parameter already swaps model identity and `use_main_model_for_realtime`. The silence-duration
   override belongs in the same `if lite:` block.

4. **Tests follow TDD.** Every subtask implies: write the failing test → implement → pass.
   The `differing` set in `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` MUST be updated
   in the SAME commit as the kwargs change, or the test will fail.

5. **Unknown-key rejection.** `VoiceTypingConfig.from_toml` passes TOML keys as dataclass kwargs,
   so unknown keys raise `TypeError`. Adding `lite_post_speech_silence_duration` to the dataclass
   makes it a recognized config key automatically — no registry or allow-list to update beyond the
   repo-default test.

## Verified Machine Facts (relevant to this change)

- GPU: NVIDIA RTX 3080 Ti, 12 GB VRAM, driver 610.43.03
- Python: 3.12 via uv (.venv/bin/python); all 239 tests pass (160 fast + 79 heavy)
- The daemon is NOT currently running (systemctl --user status voice-typing → likely stopped)
- `lite_post_speech_silence_duration` is absent from the entire codebase (grep confirmed)
