# External Dependencies — Delta 003

## RealtimeSTT v1.0.2 (no version change)

### Shutdown internals (root-caused)

See `realtimestt_shutdown_analysis.md` for the full analysis. Summary:

- `shutdown_recorder()` (core/shutdown.py) calls `.join()` WITHOUT timeouts on `recording_thread` and `realtime_thread` (both daemon threads). These joins can hang if a thread is blocked in a non-cancellable operation.
- The two `mp.Process` spawns (`transcript_process`, `reader_process`) have 10s timeouts + terminate — bounded.
- **Mitigation**: wrap `recorder.shutdown()` in a hard timeout thread; if it exceeds budget, terminate the spawn processes to release VRAM (they hold the CUDA contexts).

### Lifecycle API surface (for lazy load)

Relevant `AudioToTextRecorder` methods/attributes for the lazy-load feature:

| Method/Attr | Purpose | Thread safety |
|-------------|---------|---------------|
| `set_microphone(bool)` | Toggle audio capture queueing | Safe from any thread |
| `text(callback)` | Block until one utterance finalizes | Main loop only |
| `abort()` | Unblock a sleeping `text()` | Safe from any thread |
| `shutdown()` | Full teardown (threads + processes) | Guarded by `shutdown_lock` |
| `is_shut_down` | Idempotency flag for shutdown | Read/write under shutdown_lock |
| `transcript_process` | `mp.Process` — holds CUDA context for final model | Access for force-terminate |
| `reader_process` | `mp.Process` — PyAudio capture | Access for force-terminate |
| `use_microphone` | `mp.Value` — mic capture toggle | Atomic value access |

### Construction cost

`AudioToTextRecorder.__init__` loads both models (~1-3s on this RTX 3080 Ti):
- `small.en` (realtime) via faster-whisper/CTranslate2
- `distil-large-v3` (final) via faster-whisper/CTranslate2

VRAM budget: ~1.5-3 GB float16 total. Fine on 12 GB VRAM.

## systemd

Current unit has NO `TimeoutStopSec` → default 90s applies → matches the observed hang.

**Change**: Add `TimeoutStopSec=15` (generous beyond the daemon's own ~10s bounded teardown budget). This means systemd sends SIGKILL at 15s if the daemon hasn't exited, but the daemon's own `_bounded_shutdown(timeout=10)` should complete well within that.

## Config schema addition

New field in `[asr]`:

```toml
auto_unload_idle_seconds = 1800.0  # after this many seconds disarmed (loaded, not listening),
                                   # tear down models to free VRAM; 0 disables (§4.2bis Idle unload)
```

Dataclass: `AsrConfig.auto_unload_idle_seconds: float = 1800.0`

Search order unchanged: XDG_CONFIG_HOME → repo config.toml → dataclass defaults.

## Feedback state schema change

Current `_state`:
```json
{"listening": false, "phase": "idle", "partial": "", "last_final": "", "ts": 0.0}
```

New `_state` (additive — `models_loaded` added, boot `phase` changes to `unloaded`):
```json
{"listening": false, "phase": "unloaded", "models_loaded": false, "partial": "", "last_final": "", "ts": 0.0}
```

Phase lifecycle:
- Boot: `unloaded` (models_loaded=false)
- During first arm: `loading` (models_loaded=false)
- After successful load: `idle` (models_loaded=true)
- When armed: `listening` / `speaking` (models_loaded=true)
- After idle-unload: `unloaded` (models_loaded=false)

## No new runtime dependencies

This delta is pure Python logic changes in the daemon — no new packages, no new system tools. All infrastructure (uv, RealtimeSTT, wtype, ydotool, tmux, nvidia-smi, hyprctl) is already in place.
