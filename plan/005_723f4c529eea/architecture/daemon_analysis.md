# Daemon & Recorder Architecture — Key Findings for Round 005

## cfg_to_kwargs() — The Single Wiring Point

Location: `voice_typing/daemon.py`, function `cfg_to_kwargs` (line ~158).

### Current Lite Mode Logic

```python
def cfg_to_kwargs(cfg, *, resolved=None, lite=False):
    if resolved is None:
        resolved = _resolve_device_config(cfg)
    if lite:
        resolved = dict(resolved)
        lite_model = "tiny.en" if resolved["device"] == "cpu" else cfg.asr.lite_model
        resolved["final_model"] = lite_model
        resolved["realtime_model"] = lite_model
    kwargs = {
        "model": resolved["final_model"],
        "realtime_model_type": resolved["realtime_model"],
        "language": cfg.asr.language,
        "device": resolved["device"],
        "compute_type": resolved["compute_type"],
        "realtime_processing_pause": cfg.asr.realtime_processing_pause,
        "post_speech_silence_duration": cfg.asr.post_speech_silence_duration,  # ← SAME for both!
    }
    kwargs.update(_FIXED_KWARGS)
    if lite:
        kwargs["use_main_model_for_realtime"] = True
    return kwargs
```

### Required Change

Add to the `if lite:` block at the end:

```python
    if lite:
        kwargs["use_main_model_for_realtime"] = True
        kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration
```

This is the ONLY code change in daemon.py. The kwargs dict already has the key set from the
common block; the lite override at the end replaces it. This mirrors the existing pattern where
`use_main_model_for_realtime` is overridden by the `if lite:` block after `_FIXED_KWARGS` sets it
to `False`.

### Why Not Set It Conditionally in the kwargs Dict?

The current pattern deliberately builds a common kwargs dict and then applies lite overrides in
the `if lite:` block. This makes the diff cleaner and mirrors the existing `use_main_model_for_realtime`
override pattern. Do NOT restructure the kwargs builder.

## Config Schema — AsrConfig

Location: `voice_typing/config.py`, class `AsrConfig`.

### Current Fields (9)

```python
final_model: str = "distil-large-v3"
realtime_model: str = "small.en"
lite_model: str = "small.en"
language: str = "en"
device: str = "cuda"
post_speech_silence_duration: float = 0.6
realtime_processing_pause: float = 0.15
auto_stop_idle_seconds: float = 30.0
auto_unload_idle_seconds: float = 1800.0
```

### Required Addition

```python
lite_post_speech_silence_duration: float = 0.5  # PRD §4.2ter: lite-mode silence threshold
```

Must be added to the `__post_init__` numeric validation tuple:

```python
for _name in (
    "post_speech_silence_duration",
    "lite_post_speech_silence_duration",   # ← ADD HERE
    "realtime_processing_pause",
    "auto_stop_idle_seconds",
    "auto_unload_idle_seconds",
):
```

## config.toml — Mirror

Location: `config.toml`, `[asr]` section.

Must add after `post_speech_silence_duration`:

```toml
lite_post_speech_silence_duration = 0.5  # PRD §4.2ter: lite-mode silence threshold (the silence gate, not the model, is the perceived-latency bottleneck). 0.3 = razor-snappy (may split a brief pause); 0.6 = safe.
```

The drift-guard test `test_repo_config_toml_equals_defaults` asserts that parsing config.toml yields
a config equal to the dataclass defaults. So config.py AND config.toml changes MUST land together.

## Test Impact Analysis

### test_config_repo_default.py

The `expected` dict lists the schema keys. Currently has 9 `[asr]` keys (17 total). Must add
`"lite_post_speech_silence_duration"` to the `[asr]` set (→ 10 keys, 18 total). The docstring
"17 schema keys" must become "18".

### test_config.py

Follows the pattern of `test_lite_model_round_trips_through_toml` and
`test_lite_model_wrong_type_raises`. Need:
1. Default assertion: `cfg.asr.lite_post_speech_silence_duration == 0.5`
2. TOML round-trip: override to 0.3, assert parsed value
3. Wrong-type: pass `True` / `"0.5"` → `TypeError`
4. Type assertion: `isinstance(..., float)`

### test_daemon.py — test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal

Currently asserts lite and normal differ ONLY in:
```python
differing = {"model", "realtime_model_type", "use_main_model_for_realtime"}
```

After the change, `post_speech_silence_duration` also differs. Must update:
```python
differing = {"model", "realtime_model_type", "use_main_model_for_realtime", "post_speech_silence_duration"}
```

And add an explicit assertion:
```python
assert lite["post_speech_silence_duration"] == 0.5  # lite_post_speech_silence_duration default
assert normal["post_speech_silence_duration"] == 0.6  # post_speech_silence_duration default
```

### test_daemon.py — New Test

Add `test_cfg_to_kwargs_lite_uses_shorter_silence_duration`:
- With default config, lite kwargs have `post_speech_silence_duration == 0.5`
- With a custom `lite_post_speech_silence_duration = 0.3`, lite kwargs use 0.3
- Normal mode is unaffected by `lite_post_speech_silence_duration`

### test_feed_audio.py — No Changes Needed

The `lite_recorder` fixture calls `cfg_to_kwargs(cfg, lite=True)` which will automatically pick up
the shorter silence duration. Existing T7 tests will pass (latency comparison only gets easier).
No new assertions needed at the feed_audio level — the kwargs unit test is the contract.

## Recorder-Host Propagation (No Changes Needed)

The recorder-host child process calls `build_recorder(cfg, ..., lite=lite)` →
`cfg_to_kwargs(cfg, ..., lite=lite)`. After the daemon fix, the child will automatically receive
the shorter `post_speech_silence_duration` in lite mode. The IPC protocol (`cmd_q`/`evt_q`) is
unchanged. No edits to `recorder_host.py`.

## Latency Impact

With `post_speech_silence_duration = 0.5` (lite) vs `0.6` (normal):
- Lite finals arrive ~100 ms sooner after end-of-speech
- Combined with the ~50 ms transcription speedup from small.en vs distil-large-v3
- Total perceived improvement: ~150 ms faster, making lite feel "instant" as the PRD intends

This is within the existing `_DRAIN_TIMEOUT_S = 5.0` budget (comfortably covers 0.5s silence +
transcription time).
