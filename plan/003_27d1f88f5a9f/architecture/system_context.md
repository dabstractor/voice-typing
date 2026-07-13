# System Context — Delta 003: Lazy Model Loading + Idle Unload + Bounded Teardown

## Current state

The voice-typing project is a fully-implemented RealtimeSTT-based voice typing daemon for Linux/Hyprland. It was built across plans 001 and 002, and is a working systemd user service with:
- RealtimeSTT-based speech-to-text with live partials + final transcription
- wtype/ydotool/tmux typing backends
- Hyprland feedback (state.json + hyprctl notify)
- voicectl CLI control over a unix socket
- Idempotent install.sh, systemd unit, tests (pytest fast suite + heavy shell integration tests)

**The current daemon eagerly builds the recorder at boot** in `VoiceTypingDaemon.__init__` (~line 447), loading ~1.5-3 GB of VRAM on every login, even when voice typing is never used.

## Delta 003 goal

Three changes, with an explicit prerequisite chain:

1. **Bounded teardown (PREREQUISITE):** Fix the ~90s `recorder.shutdown()` hang so that idle-unload won't wedge the daemon every 30 minutes. Root cause: RealtimeSTT's `shutdown_recorder()` calls `.join()` without timeouts on two daemon threads (see `realtimestt_shutdown_analysis.md`). Fix: hard timeout + force-cleanup of spawn processes.

2. **Lazy-load lifecycle:** Defer recorder construction to the first `voicectl start`/`toggle`. Boot state: `unloaded` (~0 VRAM). First arm: `loading` (~1-3s) → `loaded`. Subsequent arms: instant. State machine: `unloaded → loading → loaded` with `models_loaded: bool` surfaced in status/feedback.

3. **Idle unload:** After `auto_unload_idle_seconds` (default 1800s = 30 min) of disarmed idle, tear down the recorder → back to `unloaded` (~0 VRAM). Uses the same bounded teardown from (1) and the same single-flight lock as the load from (2).

## Architecture decisions

### Recorder lifecycle state machine

```
unloaded ──(first arm)──► loading ──(success)──► loaded/not-listening
    ▲                        │                        │  ▲
    │                     (fail)                  arm  │  │ disarm
    │                        ▼                        ▼  │
    └──────────────── idle-unload ──── loaded/listening ─┘
              (30 min disarm)
```

States surfaced in `status_snapshot()` and `state.json`:
- `models_loaded: bool` — false until first successful load; false again after idle-unload
- `phase`: `unloaded` | `loading` | `idle` | `listening` | `speaking` (existing `idle`/`listening`/`speaking` preserved; `unloaded`/`loading` added for the not-loaded lifecycle)

### Single-flight lock pattern

Both load and teardown must run under the SAME lock so:
- A second arm while `loading` waits on the in-flight load (no double-load)
- An arm racing an idle-unload teardown waits for teardown, then loads fresh
- Load failure: revert to `unloaded`, return `{"ok":false}`, no half-built recorder

The existing `self._lock` already serializes start/stop/toggle. The load/teardown should use this same lock (or a dedicated lock held by the same code paths). **Critical**: the model-load takes ~1-3s; if called under `_lock` while held by `_arm()`, concurrent `voicectl stop`/`toggle` would time out. Design decision: `_load_recorder()` acquires `_lock` itself, sets `_loading = True`, releases the lock while the heavy construction runs, then re-acquires to install the recorder. This keeps `status` responsive and prevents the control-socket handlers from wedging.

### Guarding 8 recorder call sites

All `self._recorder.*` call sites must handle `None`:

| Method | Call | When reached |
|--------|------|-------------|
| `run()` | `set_microphone(False)` | Boot — guard with `if self._recorder is not None` |
| `run()` | `text(self.on_final)` | Only when listening — safe if load happens before `_listening.set()` |
| `_arm()` | `set_microphone(True)` | After load completes — trigger point for lazy load |
| `_disarm()` | `set_microphone(False)` | Guard with `if self._recorder is not None` |
| `_maybe_auto_stop()` | `abort()` | Guard |
| `stop()` | `abort()` | Guard |
| `toggle()` | `abort()` | Guard |
| `request_shutdown()` | `abort()` | Guard |
| `shutdown()` | `shutdown()` | Guard + bounded teardown |

### Idle-unload watchdog (modeled on _idle_watchdog)

Template: `daemon.py:650-659` — `_idle_watchdog` ticks via `self._shutdown.wait(1.0)`, re-checks deadline under `_lock`.

New `_idle_unload_watchdog`:
- Clock starts when mic disarms (manual stop, toggle-off, or auto-stop)
- Resets on any arm
- When `auto_unload_idle_seconds` elapses: tears down recorder under single-flight lock, transitions to `unloaded`, logs the event
- `0` disables

### Construction-failure CPU fallback migration

Currently in `main()` (~line 1301): catches `VoiceTypingDaemon.__init__` failure, retries with `force_cpu=True`. With lazy load, construction moves to `_load_recorder()` inside the daemon. The CPU fallback must move with it:
- `_load_recorder()` tries CUDA first
- If construction fails AND device was cuda: retries with `force_cpu=True`
- If both fail: reverts to `unloaded`, returns error + CPU-fallback hint

## External dependencies

| Dependency | Version | Purpose | Change for delta? |
|-----------|---------|---------|-------------------|
| RealtimeSTT | 1.0.2 | STT engine | No version change; shutdown internals documented |
| faster-whisper/ctranslate2 | (via realtimestt extras) | CUDA inference | No change |
| wtype/ydotool | system | Typing backends | No change |
| systemd | system | Service management | Add `TimeoutStopSec=15` |

## Files touched by this delta

| File | Change |
|------|--------|
| `voice_typing/daemon.py` | Lazy load lifecycle, bounded teardown, idle-unload watchdog, None guards, status_snapshot phase/models_loaded |
| `voice_typing/config.py` | Add `auto_unload_idle_seconds` to AsrConfig |
| `voice_typing/feedback.py` | Add `models_loaded` to _state; add `unloaded`/`loading` phase boot default |
| `voice_typing/ctl.py` | Surface phase/models_loaded in status output |
| `config.toml` | Add `auto_unload_idle_seconds` with self-documenting comment |
| `systemd/voice-typing.service` | Add `TimeoutStopSec=15` |
| `tests/test_daemon.py` | Add lifecycle + single-flight + load-failure + idle-unload tests |
| `tests/test_idle_and_gpu.sh` | Rewrite T6 section to 4-part lazy-load lifecycle assertions |
| `README.md` | Sweep for lazy-load behavior, config table, bounded teardown note |
