# Daemon Core & Recorder-Host Architecture

Deep scout of the voice-typing CORE DAEMON lifecycle and the recorder-host subprocess
architecture. All four files read in full: `daemon.py` (2221 lines), `recorder_host.py`
(774 lines), `config.py` (308 lines), `cuda_check.py` (168 lines). Reference supporting
files (`feedback.py`, `ctl.py`) read for cross-module protocol verification.

---

## Files Retrieved

1. `voice_typing/daemon.py` (lines 1-2221, full) — the listen-forever daemon core: recorder
   construction, callback wiring, lazy-load lifecycle, idle watchdogs, listening gate,
   control socket, and entry point `main()`.
2. `voice_typing/recorder_host.py` (lines 1-774, full) — the AudioToTextRecorder in a managed
   spawn child subprocess; full IPC protocol, process-group teardown, single-flight lock.
3. `voice_typing/config.py` (lines 1-308, full) — TOML config dataclasses + loader.
4. `voice_typing/cuda_check.py` (lines 1-168, full) — CUDA probe + CPU-fallback decision.
5. `voice_typing/feedback.py` (lines 1-160) — read to verify the phase state machine
   (`unloaded`/`loading`/`idle`/`listening`/`speaking`) the daemon drives.
6. `voice_typing/ctl.py` (lines 1-219) — read to confirm the client side of the control
   socket protocol.

---

## config.py — Full Config Schema (PRD §4.5)

Pure stdlib module (os, pathlib, dataclasses, tomllib). Deliberately does NOT import
cuda_check/ctranslate2/torch — loads in CPU-only/test contexts.

### `AsrConfig` — `[asr]`
| Field | Default | Notes |
|---|---|---|
| `final_model` | `"distil-large-v3"` | large Whisper (cuda) |
| `realtime_model` | `"small.en"` | realtime partials model |
| `lite_model` | `"small.en"` | §4.2ter lite mode (CPU substitute: `"tiny.en"`) |
| `language` | `"en"` | |
| `device` | `"cuda"` | `"cuda"` \| `"cpu"` — validated at load (VT-005) |
| `post_speech_silence_duration` | `0.6` | VAD finalize silence (s) |
| `lite_post_speech_silence_duration` | `0.5` | §4.2ter lite silence gate |
| `realtime_processing_pause` | `0.15` | partial cadence (s) |
| `auto_stop_idle_seconds` | `30.0` | auto-disarm after no speech; 0 disables |
| `auto_unload_idle_seconds` | `1800.0` | §4.2bis idle-unload VRAM reclaim; 0 disables |

`__post_init__` enforces types (rejects bool for numerics, validates `device` value).

### `OutputConfig` — `[output]`
- `backend: str = "wtype"` (`"wtype"` | `"ydotool"` | `"tmux"`)
- `tmux_target: str = ""`
- `append_space: bool = True`

### `FeedbackConfig` — `[feedback]`
- `state_file: str = ""` → lazily resolved via `resolved_state_file()` to
  `$XDG_RUNTIME_DIR/voice-typing/state.json` (raises RuntimeError if XDG_RUNTIME_DIR unset)
- `hypr_notify: bool = True`
- `notify_ms: int = 2500` (validated as int)
- `notify_on_final: bool = True`

### `FilterConfig` — `[filter]`
- `min_chars: int = 2`
- `blocklist: list[str] = ["thank you.", "thanks for watching.", "bye.", "thank you for watching"]`
  (VT-006: bare `"you"` was REMOVED — it silenced the legitimate standalone word)

### `LogConfig` — `[log]`
- `level: str = "INFO"` (`"INFO"` | `"DEBUG"`, case-insensitive at apply time)

### `VoiceTypingConfig` (top-level aggregator)
- Class methods: `from_toml(data)`, `from_toml_file(path)`, `load(path=None)`
- Search order (first existing file wins): `$XDG_CONFIG_HOME/voice-typing/config.toml` →
  `<repo>/config.toml` → built-in dataclass defaults
- `load(path)` explicit → bypasses search
- Module-level `load(path=None)` convenience wrapper
- Unknown keys → `TypeError` (loud failure, not silent)

---

## cuda_check.py — CUDA Probe + CPU Fallback (PRD §4.4)

### Constants
```python
CUDA_DEFAULTS = {"device": "cuda", "compute_type": "float16",
                 "final_model": "distil-large-v3", "realtime_model": "small.en"}
CPU_FALLBACK  = {"device": "cpu",   "compute_type": "int8",
                 "final_model": "small.en",     "realtime_model": "tiny.en"}
```

### Key Functions
- `is_cuda_available() -> bool` — MUST-HAVE check: `ctranslate2.get_cuda_device_count() >= 1`
- `resolve_device_and_models(defaults=None) -> dict[str, str]` — returns CUDA_DEFAULTS copy
  if cuda available, else CPU_FALLBACK (regardless of defaults)
- `_cuda_device_count() -> tuple[int, str]` — wrapped probe returning `(count, reason)`; any
  failure (missing ctranslate2, driver error) → `(0, reason)`
- `_torch_cuda_available() -> bool` — NICE-TO-HAVE (Silero VAD diagnostics only; does NOT
  gate the verdict)
- `_main() -> int` — CLI: prints diagnostics + `VERDICT=<cuda-ok|cpu-fallback-required>`,
  exit 0=cuda-ok / 1=cpu-fallback

### CRITICAL LIMITATION (documented, not a bug)
`get_cuda_device_count()` probes the **CUDA driver only** — it does NOT load cuDNN. A
missing `libcudnn_ops.so.9` yields "cuda-ok" but fails later at WhisperModel construction.
The construction-failure → CPU retry now lives in the recorder-host child
(`recorder_host.py` `_worker_main`), keeping the daemon process CUDA-free.

---

## recorder_host.py — Subprocess IPC Architecture

The WHOLE point: GPU-VRAM reclamation. RealtimeSTT's realtime model acquires a CUDA primary
context (~100–300 MiB) that is UNRELEASABLE until the process exits (`del`/`gc.collect()`/
`torch.cuda.empty_cache()` do NOT release it). FIX: construct the recorder in a CHILD
subprocess (spawn) that the daemon spawns on first arm and terminates on idle-unload/quit.
Terminating the child PROCESS GROUP releases ALL VRAM → daemon tree ABSENT on nvidia-smi.

### Constants
- `_SPAWN_READY_TIMEOUT_S = 180.0` — child ready/error wait budget
- `_STOP_JOIN_TIMEOUT_S = 5.0` — join budget before SIGKILL

### `class RecorderHost` — public surface (daemon calls these)
**Constructor:**
```python
def __init__(self, cfg, feedback, latency, on_final, on_partial, on_speech,
             *, force_cpu=False, is_listening=None, mode="normal")
```
- `is_listening` — optional predicate; the `('vad', ...)` dispatch consults it to drop stray
  VAD events racing a disarm (Issue 2 residual gate)
- `mode` — `"normal"` (distil-large-v3 + small.en) or `"lite"` (lite_model only, §4.2ter)

**IPC primitives created in `__init__` (all spawn-context):**
- `_cmd_q = ctx.Queue()` (daemon → child)
- `_evt_q = ctx.Queue()` (child → daemon)
- `_abort_event = ctx.Event()` (daemon → child, polled by separate child thread)
- `_stop_lock = threading.Lock()` — single-flight for `stop()` (Plain Lock, not RLock)

**Methods:**
- `spawn(timeout=180.0) -> bool` — start child + reader thread + wait for ready/error
- `set_microphone(on: bool)` → put `("arm"|"disarm", {})` on cmd_q (best-effort)
- `abort()` → set `_abort_event` (interrupts blocked text())
- `text(on_final)` → put `("text", {})`, block on `_final_evt` (0.5s poll loop, unblocks on
  child death)
- `stop(timeout=5.0)` → single-flight: set abort, best-effort "shutdown" on detached thread,
  `proc.join(timeout)`, then `os.killpg(SIGKILL)` if still alive
- `_read_loop()` → daemon reader thread: drains evt_q, dispatches, swallows child death
- `_dispatch(kind, payload)` → routes events to daemon callbacks
- `_terminate_group()` → `os.killpg(os.getpgid(pid), SIGKILL)`

**Properties:** `device` (from child's "ready"), `mode`, `is_alive`, `pid`

### IPC Protocol
**cmd_queue (daemon → child):**
| Command | Child Action |
|---|---|
| `("arm", {})` | `recorder.set_microphone(True)` |
| `("disarm", {})` | `recorder.set_microphone(False)` + `_clear_recorder_audio(recorder)` |
| `("text", {})` | `_run_text_and_emit_final(recorder, evt_q, child_on_final, aborted)` — BLOCKS |
| `("abort", {})` | `recorder.abort()` (belt-and-suspenders; primary path is `_abort_event`) |
| `("shutdown", {})` | `recorder.shutdown()` + put `("gone", {})` + exit |

**event_queue (child → daemon):**
| Event | Payload | Daemon Action |
|---|---|---|
| `ready` | `{device, compute_type, final_model, realtime_model}` | set `_ready_evt`, cache device |
| `error` | `{msg}` | set `_ready_evt`, set `_error` |
| `final` | `{text}` | call `_on_final(text)` on reader thread, set `_final_evt` |
| `partial` | `{text}` | call `_on_partial(text)` |
| `speech` | `{}` | call `_on_speech()` (resets idle auto-stop clock) |
| `vad` | `{phase: "listening"|"speaking"}` | call `feedback.set_phase(phase)` (gated by is_listening) |
| `speech_end` | `{}` | `latency.note_speech_end()` |
| `gone` | `{}` | reader thread exits cleanly |

**abort_event:** separate `multiprocessing.Event` polled by a dedicated child thread
(`_abort_handler`) because the child's command loop BLOCKS in `recorder.text()` while
listening. Setting it calls `recorder.abort()` to unblock text(). The `aborted` flag
(VT-007) marks so `_run_text_and_emit_final` emits a `('final', {text:''})` sentinel on the
abort path — without this, `host.text()` blocks forever on abort (the run-loop wedge fix).

### `_worker_main(cfg, cmd_q, evt_q, abort_event, force_cpu, mode="normal")` — CHILD entry point
1. `os.setsid()` → child is its own session/group leader (killpg reaches grandchildren)
2. Lazy import `from voice_typing.daemon import build_recorder`
3. Build `_RelayFeedback` + `_RelayLatency` (relay callbacks → evt_q)
4. `build_recorder(cfg, relay_fb, relay_lat, on_speech=_child_on_speech, lite=lite)`
   - On construction failure: retry ONCE with `force_cpu=True` (CPU fallback, PRD §4.4)
   - Report `("ready", resolved_device)` or `("error", {msg})`
5. Command loop: `("text", {})` → blocks in `recorder.text()`; abort-handler thread watches
   `_abort_event`
6. `("shutdown", {})` → `recorder.shutdown()` + `("gone", {})` + exit

### `_run_text_and_emit_final(recorder, evt_q, on_final, aborted=None)` — VT-007
Guarantees a `('final', ...)` event on BOTH paths (real final via on_final, OR abort via
sentinel `('final', {text:''})`). The abort path is detected via TWO independent signals:
1. `aborted.is_set()` — the threading.Event set around `recorder.abort()` (version-independent)
2. `result is not None` — legacy non-None return marker (v1.0.2 contract)

### `_RelayFeedback` / `_RelayLatency` — child-local stand-ins
- `_RelayFeedback.update_partial(text)` → `("partial", {text})`
- `_RelayFeedback.set_phase(phase)` → `("vad", {phase})` (only listening/speaking)
- `_RelayLatency.note_speech_end()` → `("speech_end", {})`
- Other methods are no-ops (driven by daemon)

---

## daemon.py — Complete Control Flow

### Module-Level Constants
- `_FIXED_KWARGS` — VAD/timing/silero values NOT in config (silero_sensitivity=0.4,
  webrtc_sensitivity=3, silero_backend="auto", spinner=False, use_microphone=True, etc.)
- `_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"` (preferred; swap to
  `"on_realtime_transcription_update"` for faster/rougher)
- `_MIC_PROBE_TTL_S = 30.0` — mic probe cache window
- `_COLD_LOAD_NOTIFY_LOADING = "Loading…"` — cold first-arm toast
- `_DRAIN_TIMEOUT_S = 5.0` — graceful stop drain timeout
- `_LATENCY_LOG_PREFIX = "voice-typing latency:"` — STABLE prefix (T1 greps this)
- `_LATENCY_RING_SIZE = 64`
- `_TEARDOWN_WAIT_TIMEOUT = 8.0` — SIGTERM double-teardown wait

### Module-Level Functions
- `_resolve_device_config(cfg) -> dict[str, str]` — wraps cuda_check (NOTE: only called in
  the CHILD now; daemon process never probes — VT-001)
- `cfg_to_kwargs(cfg, *, resolved=None, lite=False) -> dict[str, Any]` — builds
  AudioToTextRecorder kwargs; lite mode sets `use_main_model_for_realtime=True` + uses
  `lite_post_speech_silence_duration`
- `_build_callbacks(feedback, latency=None, on_speech=None) -> dict[str, Callable]` — wires
  RealtimeSTT → Feedback (+ latency + on_speech)
- `_filter_kwargs_to_signature(kwargs, recorder_cls) -> dict` — defensive vs API drift
  (drops unknown kwargs, logs WARNING)
- `_construct(cfg, feedback, recorder_cls, latency=None, force_cpu=False, on_speech=None, lite=False) -> Any`
  — testable build (tests pass fake recorder_cls)
- `build_recorder(cfg, feedback, latency=None, force_cpu=False, on_speech=None, lite=False) -> Any`
  — production build (lazy RealtimeSTT import)
- `_default_control_socket_path() -> str` — `$XDG_RUNTIME_DIR/voice-typing/control.sock`
- `_ms(seconds) -> float` — seconds → ms (rounded 0.1)
- `install_shutdown_signal_handlers(daemon, *, signals=None) -> Callable` — SIGTERM/SIGINT →
  spawned daemon thread calls `request_shutdown()` (NEVER abort/shutdown from handler —
  deadlock)
- `_resolve_log_level(level_name) -> int`
- `_setup_logging(level_name)` — basicConfig + mic-retry rate limiter
- `main() -> int` — entry point

### `class LatencyLog`
Per-utterance latency capture (ring buffer maxlen=64). Thread-safe (`_lock`).
- `note_partial(_text)` — count
- `note_speech_end()` — stamp `t_speech_end`
- `finalize_utterance(*, text, t_final_ready, t_typed) -> dict` — build record, reset
- `snapshot() -> list[dict]`

### `class _LegacyRecorderHostAdapter`
Wraps a legacy stub recorder (`set_microphone`/`abort`/`text`/`shutdown`) as a host-shaped
surface so the existing ~50 tests inject stubs unchanged. Production never uses this.

### `class VoiceTypingDaemon` — the CORE

**Constructor:**
```python
def __init__(self, cfg, feedback, *, recorder=None, recorder_host=None,
             host_factory=None, backend=None, latency=None, mic_prober=None)
```

**State Variables:**
| Variable | Type | Purpose |
|---|---|---|
| `_host` | RecorderHost \| None | the recorder-host child (None = lazy/unloaded) |
| `_lock` | threading.Lock | main lock |
| `_on_final_lock` | threading.Lock | serialize on_final (SEPARATE from _lock, no deadlock) |
| `_listening` | threading.Event | cleared at boot = NOT listening (PRD §4.9) |
| `_shutdown` | threading.Event | run() loop exit signal |
| `_teardown_done` | threading.Event | SIGTERM double-teardown coordination |
| `_text_in_flight` | threading.Event | True while run() blocked in host.text() |
| `_load_cond` | Condition(_lock) | single-flight load wait |
| `_models_loaded` | bool | models resident? |
| `_loading` | bool | load in progress? |
| `_load_error` | str \| None | last load failure |
| `_mode` | str | "normal" \| "lite" |
| `_last_speech_monotonic` | float \| None | idle auto-stop clock |
| `_disarmed_monotonic` | float \| None | idle unload clock |
| `_final_pending`, `_drain`, `_drain_timer` | bool/Timer | graceful stop drain |
| `_resolved_device_cache` | dict | VT-001 device cache (NEVER probes CUDA) |
| `_mic_ok`, `_mic_error`, `_mic_probe_at` | bool/str/float | mic health (TTL 30s) |

### State Machine — Lifecycle Phases (driven via `feedback.set_phase()`)
```
unloaded ──[first arm: _load_host()]──> loading ──[spawn ready]──> idle
   ▲                                         │                        │
   │                                    [spawn fail]              [arm: _arm()]
   │                                         │                        │
   └─────────────────────────────────────────┘                        ▼
   │                                                              listening
   │ [idle-unload]                                                     │
   │ [_handle_dead_host]                                          [VAD detect]
   │                                                                    ▼
   └──────────────────────────────────────────── speaking ◄──────────┘
                                                  │
                                           [on_vad_stop]
                                                  ▼
                                             listening (back to)
```
- `unloaded` — boot / failed load / dead host / idle-unloaded
- `loading` — first arm in progress (spawning child)
- `idle` — models resident, NOT listening (armed = off)
- `listening` — armed, VAD active, no speech / after speech ended
- `speaking` — VAD detected voice

### `run()` — the listen-forever loop (main thread, BLOCKS)
```python
self._start_monotonic = time.monotonic()
self._configure_log_level()
self._feedback.set_listening(False)  # PRD §4.9: starts NOT listening
if self._host is not None:
    self._host.set_microphone(False)  # gate audio queueing while idle
# Start watchdog threads
threading.Thread(target=self._idle_watchdog, ...).start()       # auto-stop
threading.Thread(target=self._idle_unload_watchdog, ...).start() # idle-unload

while not self._shutdown.is_set():
    # Liveness check: detect crashed child
    if self._host is not None and not self._host.is_alive:
        self._handle_dead_host(); continue
    if self._host is None:
        time.sleep(0.05); continue          # idle (~0 VRAM)
    if self._drain:
        self._complete_drain(); continue     # graceful stop drain
    if self._listening.is_set():
        self._text_in_flight.set()
        try:
            self._host.text(self.on_final)   # BLOCKS until one final
        finally:
            self._text_in_flight.clear()
    else:
        time.sleep(0.05)
```
Key invariant: `recorder.text()` returning is NORMAL SEGMENTATION, never session end
(WhisperX-flaw fix). `_text_in_flight` gates `_safe_abort()` so abort() never hangs.

### Lazy Load Lifecycle (§4.2bis)
- `_load_recorder()` — alias for `_load_host("normal")`
- `_load_host(mode="normal") -> bool` — single-flight lazy spawn:
  1. Fast path under `_lock`: resident + alive + SAME mode → return True
  2. Mode mismatch → `switch_mode=True` (tear down resident, respawn)
  3. If `_loading` → wait on `_load_cond` for in-flight spawn
  4. Set `_loading=True`, phase → "loading", models_loaded → False
  5. Fire "Loading…" toast (`feedback.notify`)
  6. Mode switch teardown (bounded 5s) under `_lock`
  7. **Heavy spawn OUTSIDE _lock** (status/stop stay responsive): `host.spawn()`
  8. Re-acquire `_lock`: on success seed device cache, phase → "idle", models_loaded → True;
     on failure stop half-spawned host, phase → "unloaded", set `_load_error`

### Idle Auto-Stop Watchdog (§4.2 `auto_stop_idle_seconds`)
- `_idle_watchdog()` — background daemon thread, ticks via `_shutdown.wait(1.0)`, calls
  `_maybe_auto_stop()`
- `_maybe_auto_stop()` — re-checks idle deadline UNDER `_lock`; disarms if
  `time.monotonic() - _last_speech_monotonic >= auto_stop_idle_seconds` (default 30s);
  threshold ≤ 0 disables. abort() moved OUT of _lock (validation NEW-2).
- `_last_speech_monotonic` refreshed by `_touch_speech()` (wired to host's "speech" event)

### Idle UNLOAD Watchdog (§4.2bis `auto_unload_idle_seconds`)
- `_idle_unload_watchdog()` — background daemon thread, same tick pattern
- `_maybe_idle_unload()` — lock-free pre-check (avoid hammering _lock); delegates to
  `_unload_host()` if conditions met
- `_unload_host()` — single-flight: re-checks full condition UNDER `_lock` (race guard vs
  concurrent arm); calls `_bounded_shutdown(timeout=5.0)` UNDER _lock (safe — host.stop()
  never touches _lock); sets `_host=None`, `_models_loaded=False`, phase → "unloaded",
  reseeds device cache to un-probed config (VT-002). Default 1800s (30 min).

### Lite Mode Support (§4.2ter)
- `start_lite()` / `toggle_lite()` — arm in lite mode (`_load_host("lite")`)
- `_load_host(mode)` detects mode mismatch and does ONE bounded reload (~1–3s)
- `cfg_to_kwargs(lite=True)` sets `use_main_model_for_realtime=True` + uses
  `lite_post_speech_silence_duration` (the silence gate, not the model, is the latency
  bottleneck)
- Toggle semantics: each key only toggles its own mode; cross-mode press = one reload
- `feedback.set_mode(self._mode)` publishes armed mode to state.json

### Graceful Drain (§4.2 #2)
- `_request_stop()` — if utterance in flight (`_text_in_flight` + `_final_pending`): begin
  drain; else disarm immediately + abort
- `_begin_drain()` — set `_drain=True`, arm `_drain_timer` (5s watchdog)
- `_complete_drain()` — called from run loop after text() returns while `_drain` set;
  disarms + cancels watchdog
- `_drain_timeout()` — watchdog: abort blocked text() if no final fires within 5s

### `_arm()` / `_disarm()` (private, called under `_lock`)
- `_arm()`: set `_listening`, stamp `_last_speech_monotonic`, clear `_disarmed_monotonic`,
  `host.set_microphone(True)`, `feedback.set_mode`, `feedback.set_listening(True)`,
  `_refresh_mic_status()` (TTL 30s)
- `_disarm()`: clear `_listening`, clear `_last_speech_monotonic`, stamp
  `_disarmed_monotonic`, `host.set_microphone(False)`, `feedback.set_listening(False)`,
  `feedback.set_phase("idle")`. NOTE: `host.abort()` deliberately NOT called here — caller
  must call `_safe_abort()` AFTER releasing `_lock` (validation NEW-2: avoids control-lock
  wedge under rapid toggling)

### `_safe_abort()` (validation Issue 1)
Gates `host.abort()` on `_text_in_flight.is_set()`. RealtimeSTT's `abort()` blocks on
`was_interrupted.wait()` (set only inside `text()`); when loop is idle in `sleep()` it would
hang forever. Never re-raises.

### `_handle_dead_host()` (bugfix Issue 3)
Called from run() when `is_alive` is False (child crashed: CUDA OOM, segfault). Does NOT
call host.stop() (child already gone); drops reference, resets to "unloaded" UNDER _lock,
clears `_listening`, sets `_load_error`, reseeds device cache (VT-002).

### `_probe_mic()` (bugfix Issue 2)
Lazy PyAudio probe (imported inside method). Suppresses ALSA C-lib stderr chatter by
temporarily `dup2`-ing devnull over fd 2 during enumeration only (not globally). Returns
`(ok, error)`. `_refresh_mic_status()` TTL-caches at 30s.

### Shutdown Path
- `request_shutdown()` — set `_shutdown`, cancel drain timer, abort (gated), tear down child
  via `_bounded_shutdown()`. Single-flight via `_shutdown_done` (under _lock) +
  `_teardown_done` (Event) so concurrent shutdown() WAITS instead of double-tearing.
- `shutdown()` — idempotent + single-flight: claims `_shutdown_done` or waits on
  `_teardown_done` (bounded 8s); falls back to own teardown (safe via RecorderHost._stop_lock)
- `_bounded_shutdown(timeout=5.0)` — routes to `self._host.stop(timeout)`; no-op if host None

### `status_snapshot() -> dict`
Returns: `listening`, `mode`, `phase`, `models_loaded`, `load_error`, `partial`,
`last_final`, `uptime_s`, `device`, `compute_type`, `final_model`, `realtime_model`,
`mic_ok`, `mic_error`. Device from `_resolved_device_cache` (NEVER probes CUDA — VT-001).

### `_resolved_device()` (VT-001)
ONLY returns the cache; NEVER calls cuda_check. Cache seeded in `__init__` to un-probed
config values, replaced by child's "ready" dict on successful `_load_host()`, reseeded to
un-probed config on host death/idle-unload (VT-002). The daemon process NEVER imports
ctranslate2/torch/creates a CUDA context — the recorder-host subprocess architecture's core
invariant.

---

## Control Socket Protocol (daemon.py `ControlServer`)

AF_UNIX SOCK_STREAM at `$XDG_RUNTIME_DIR/voice-typing/control.sock` (dir 0700, socket 0600).
One JSON object per line. Accept loop uses `select()` polling (NOT close-to-unblock —
unreliable on Linux).

**Requests → Responses:**
| Command | Response |
|---|---|
| `{"cmd":"toggle"}` | `{"ok":true, **status}` or `{"ok":false,"error":...}` (arm attempted) |
| `{"cmd":"start"}` | `_arm_response()` (ok:false+error if load failed) |
| `{"cmd":"start-lite"}` | `_arm_response()` (§4.2ter) |
| `{"cmd":"toggle-lite"}` | `_arm_response()` (§4.2ter) |
| `{"cmd":"stop"}` | `{"ok":true, **status}` |
| `{"cmd":"status"}` | `{"ok":true, **status}` |
| `{"cmd":"quit"}` | `{"ok":true,"shutting_down":true}` + `request_shutdown()` + `on_quit` |
| malformed JSON | `{"ok":false,"error":"malformed JSON: ..."}` |
| non-dict JSON | `{"ok":false,"error":"request must be a JSON object"}` |
| unknown cmd | `{"ok":false,"error":"unknown command: ..."}` |

---

## `main()` — Entry Point Lifecycle (P1.M4.T3.S1)
```
1. cfg = VoiceTypingConfig.load()         # fatal on failure
2. _setup_logging(cfg.log.level)
3. from voice_typing.feedback import Feedback
4. feedback = Feedback(cfg.feedback)
5. latency = LatencyLog()
6. daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)  # FAST — no models
7. server = ControlServer(daemon, on_quit=daemon.shutdown)
8. restore = install_shutdown_signal_handlers(daemon)
9. server.start()
10. daemon.run()                          # BLOCKS until quit/signal
finally:
    restore()                             # reinstate signal handlers
    daemon.shutdown()                     # idempotent
    server.stop()                         # main thread only
return 0
```

---

## Mic-Retry Rate Limiting (`MicRetryRateLimitFilter`)
Attached to "realtimestt" logger (idempotent). Rate-limits the per-~3s "Microphone
connection failed" ERROR+traceback spam: first occurrence passes through; subsequent within
`dedup_seconds=60s` suppressed; on every 20th occurrence OR 60s elapsed → rewrite to WARNING
summary (no traceback). Match key: message contains "Microphone connection failed".

---

## Notable Markers / Findings (severity-tagged)

### Stale / Incomplete (low severity — documentation drift)
- **daemon.py:12** — module docstring says "LATER: precise per-utterance latency timestamps
  (P1.M4.T1.S3). These are NOT in this module yet." — **STALE**: `LatencyLog` is fully
  implemented (lines 432-526) and wired into `_build_callbacks` + `on_final`. The docstring
  was not updated when T1.S3 landed. Informational only; no functional gap.

### KNOWN LIMITATIONS (documented, accepted trade-offs — not bugs)
- **daemon.py:27** — `cuda_check` probes CUDA driver only (not cuDNN). Construction-failure
  → CPU retry now handled in the child (`recorder_host.py` `_worker_main`), keeping the
  daemon process CUDA-free.
- **daemon.py:812** — `set_microphone(False)` toggles a shared `use_microphone` flag that
  gates QUEUEING; it does NOT cork/close the underlying PyAudio capture stream (residual
  physical-capture-while-idle). Accepted trade-off for instant toggle-on (closing the
  stream would require full recorder reconstruction = seconds of model reload).

### Design-Decision Markers (not bugs — explanatory)
- **VT-001** (daemon.py:566, 1585) — daemon process MUST NEVER probe CUDA; device cache
  seeded to un-probed config, replaced by child's "ready" dict
- **VT-002** (daemon.py:899, 1244) — dead/unloaded child's resolved device is stale; reseed
  cache to un-probed config (not None — would reintroduce VT-001)
- **VT-005** (config.py:105) — device value validation (only "cuda"|"cpu")
- **VT-006** (config.py:191) — bare "you" removed from blocklist defaults
- **VT-007** (recorder_host.py:511, 660) — abort-path unblock sentinel keyed on `aborted`
  flag OR legacy non-None return (version-independent)
- **BUG-A** (daemon.py:180, recorder_host.py:689, 711) — lite CPU substitute "tiny.en"
  mapping (mirrors CPU_FALLBACK small.en→tiny.en)
- **BUG-1** (daemon.py:1455, 1497) — SIGTERM wedge fix: kill child to unblock text()
- **Issue 1** (recorder_host.py:151) — single-flight `_stop_lock` for stop()
- **Issue 2** (daemon.py:1009) — abort() outside _lock (control-lock wedge fix)
- **Issue 3** (daemon.py:679, _handle_dead_host) — child death recovery
- **Issue 5** (daemon.py:595) — `_on_final_lock` serializes concurrent on_final threads

### No TODO/FIXME/HACK/BUG(standalone) Markers
A grep for `TODO|FIXME|HACK|XXX|STUB` across `voice_typing/*.py` found ZERO genuine markers.
All "BUG-" references are to documented, already-fixed issues (BUG-1, BUG-A). The codebase
is remarkably well-documented with inline rationale; there is no stubbed or incomplete
functionality in these four files.

---

## Residual Risks

1. **daemon.py:12 stale docstring** — says latency timestamps are "NOT in this module yet"
   but they are (LatencyLog). A future agent editing the docstring could be misled. Fix:
   update the docstring to reflect the implemented LatencyLog. (Low severity.)
2. **cuDNN load failure** surfaces only at recorder construction (in the child). The child
   retries with force_cpu=True, so this is handled, but the failure mode is not detectable
   at startup time (only at first arm). Documented, accepted.
3. **PyAudio stream stays open while idle** — set_microphone(False) gates queueing, not the
   physical capture stream. PipeWire still lists an active source-output. Accepted
   trade-off for instant toggle.
4. **`_load_host` mode-switch teardown happens while NOT listening** — if a toggle arrives
   mid-drain (text() returning), the mode-switch path could race. The `_lock` +
   `_load_cond` single-flight serialize this, but the interaction is subtle. Well-tested.
5. **abort() outside _lock** (Issue 2) — a fast re-arm races the delayed abort() harmlessly
   (abort is a no-op when no text() is blocked). Documented as correct.

---

## Start Here

**`voice_typing/recorder_host.py`** — open this first. The entire architecture's core
invariant (daemon process never touches CUDA) is enforced here. The IPC protocol table
(cmd_queue + event_queue + abort_event) is the single most important reference for any
agent modifying the daemon/recorder boundary. Then **`voice_typing/daemon.py`** lines
651-870 (`VoiceTypingDaemon.__init__` + `_load_host`) for the lazy-load lifecycle and lines
838-870 (`run()` main loop) for the control flow.
