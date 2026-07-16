# Delta PRD: Lite Mode — Small-Model-Only Quick Dictation

**Status:** Approved for implementation. This delta targets the **already-implemented** voice-typing project (lazy load, idle-unload, bounded teardown, and graceful stop drain are all landed and tested). It adds exactly ONE feature: a second arming mode that loads a single small model for low-latency snippets.

---

## 1. What changed in the PRD (scope of THIS delta)

The PRD gained two logical changes versus the previous version. They are handled differently here:

### 1a. Graceful stop drain — ALREADY IMPLEMENTED, out of scope
The PRD edits to §1, §4.2(1)–(2), §4.5 (idle auto-stop disarms immediately, no drain), and §4.6 (toasts: `Recording` / `Recording Stopped` / cold-load `Loading…`) **already match the code on `main`**. Evidence (do not re-implement):
- `voice_typing/daemon.py`: `_DRAIN_TIMEOUT_S`, `_request_stop()`, `_begin_drain()`, `_complete_drain()`, `_text_in_flight`, `_final_pending`.
- `voice_typing/feedback.py` module docstring (lines 20–26) + `set_listening()`: `Recording`/`Recording Stopped`/`Loading…` toasts, `Loading…` fires once before a cold first arm.
- `_maybe_auto_stop()`: "Auto-stop fires only after [silence] — drain, an immediate disarm+abort is correct."
- Commits `5f32d74` (Graceful stop preserves in-flight final text), `495bdd2` (cold-load toast), `5c83567` (document graceful drain semantics).

**No tasks are created for the drain.** The only reason it appears here is that it rides along in the same PRD diff; the code already satisfies it.

### 1b. Lite mode — THE WORK (§4.2ter, new; touches §4.2(3), §4.2bis, §4.4, §4.5, §4.6, §4.8, §4.10, §6 T7, §7 #10)
A second arming mode for short, speed-critical snippets (URLs, shell commands, short replies) where latency matters more than accuracy. **Zero `lite` references exist in the code today** (verified). This delta implements it end to end.

---

## 2. Architecture context for the implementer (read this first)

The recorder does NOT live in the daemon process — it lives in a **spawned child subprocess** (`voice_typing/recorder_host.py`). Everything below is already true and is load-bearing for this delta:

- `VoiceTypingDaemon._load_host()` (daemon.py) is the **single-flight** lazy spawn of the `RecorderHost` child on first arm. It runs the heavy `host.spawn()` *outside* `_lock`, then re-acquires `_lock` to publish the result, seed `self._resolved_device_cache = host.device`, set `_models_loaded=True`, phase `idle`.
- `VoiceTypingDaemon._unload_host()` is the **single-flight** bounded teardown (reclaims VRAM; same `_lock` as `_load_host`, so a racing arm waits then spawns fresh).
- `RecorderHost.spawn()` → `mp.Process(target=_worker_main, args=(cfg, cmd_q, evt_q, abort_event, force_cpu))`. The child lazy-imports `build_recorder` and constructs the recorder IN THE CHILD (only the child touches CUDA).
- `build_recorder(cfg, feedback, latency, force_cpu=, on_speech=)` → `_construct(...)` → `cfg_to_kwargs(cfg, resolved=)` builds the kwargs; `_FIXED_KWARGS` sets `use_main_model_for_realtime=False`. Callbacks come from `_build_callbacks`.
- `_child_resolved_device(cfg, force_cpu)` (in the child) reports `{device,compute_type,final_model,realtime_model}` on the `ready` event → the daemon seeds its status cache from it (the daemon itself stays CUDA-free).
- `ControlServer._dispatch(line)` routes `toggle`/`start`/`stop`/`status`/`quit`; `start`/`toggle` go through `_arm_response()`. `status_snapshot()` returns the JSON the socket emits.
- `Feedback._state` (feedback.py) is the on-disk `state.json` shape; `set_listening`/`set_phase`/`set_models_loaded`/`update_partial`/`record_final` mutate + write it. `status.sh` jq-renders it for tmux.
- `ctl.py` `_COMMANDS` + `format_result()` + `main()` validate commands and render the reply.

**Verified against the installed RealtimeSTT v1.0.2** (`.venv/.../RealtimeSTT/core/initialization.py:447`): with `enable_realtime_transcription=True` AND `use_main_model_for_realtime=True`, `_initialize_realtime_transcription_model()` **early-returns** (the `and not recorder.use_main_model_for_realtime` clause fails) — so the separate realtime engine is NEVER constructed. Constructing the recorder with `model=<X>`, `realtime_model_type=<X>`, `use_main_model_for_realtime=True` therefore loads **exactly ONE model** (`<X>`) used for both partials and finals. This is the load-bearing fact for lite mode and it is confirmed, not assumed.

Prior research of interest: `plan/003_27d1f88f5a9f/architecture/realtimesttt_shutdown_analysis*.md` (bounded teardown — lite's mode-switch reload reuses this exact machinery).

---

## 3. Lite mode — the spec

### 3.1 Config (§4.5)
- Add `lite_model: str = "small.en"` to `AsrConfig` (`voice_typing/config.py`), validated as a string field in `__post_init__` (mirror the existing `final_model`/`realtime_model` string check).
- Add the line to `config.toml [asr]` (after `realtime_model`), self-documenting comment, default `"small.en"`: the SINGLE model loaded in lite mode (used for BOTH partials + finals).
- **CPU fallback for lite:** the normal models auto-downgrade via `cuda_check` when no CUDA device is visible. The approved CPU lite substitute is `tiny.en` (mirror how the normal path maps `distil-large-v3`→`small.en` and `small.en`→`tiny.en`). The lite recorder's CPU-fallback path must use `lite_model`→`tiny.en`.

### 3.2 Recorder construction (§4.4 / §4.2ter) — a `mode` parameter
Add a `mode: str = "normal"` parameter (values `"normal"` | `"lite"`) threaded through the construction layer:
- `cfg_to_kwargs(cfg, *, resolved=None, mode="normal")`: in `mode=="lite"`, set `model = lite_model`, `realtime_model_type = lite_model`, and override `use_main_model_for_realtime=True`. All OTHER kwargs (device/compute_type from `resolved`, language, timing, silero, `enable_realtime_transcription`, etc.) are IDENTICAL to normal mode. NOTE: `model`/`realtime_model_type` in lite must come from `lite_model`, NOT from `resolved["final_model"]`/`resolved["realtime_model"]` — so the lite branch builds its own model-identity pair regardless of `resolved`.
- `_construct(..., mode="normal")` and `build_recorder(..., mode="normal")`: pass `mode` through to `cfg_to_kwargs`. The `force_cpu` interaction: `force_cpu` still selects the CPU device dict; `mode=="lite"` + `force_cpu` selects `device=cpu, compute_type=int8` with `model=realtime_model_type="tiny.en"` (the CPU lite substitute) and `use_main_model_for_realtime=True`.

### 3.3 Mode is a spawn-time property of the child; daemon tracks `self._mode`
- `RecorderHost.__init__(..., mode: str = "normal")` stores `self._mode`; `spawn()` passes `mode` into `_worker_main` (add it to the `args` tuple, after `force_cpu`).
- `_worker_main(cfg, cmd_q, evt_q, abort_event, force_cpu, mode)`: pass `mode` into `build_recorder(cfg, relay_fb, relay_lat, force_cpu=..., mode=mode, on_speech=...)` on BOTH the primary and force_cpu retry paths. The child otherwise behaves identically (same command loop, same callbacks).
- `_child_resolved_device(cfg, force_cpu, mode)`: in lite mode report `final_model=realtime_model=lite_model` (CPU-fallback → `tiny.en`), so the daemon's `ready`-seeded status cache reports the lite model. The device/compute_type resolution is unchanged.
- `VoiceTypingDaemon` gains `self._mode: str = "normal"` (boot state — the daemon is not armed, mode is "normal" by default until a lite command is issued). Add a `set_mode` to feedback (see §3.5) and call it on every arm/disarm.

### 3.4 Mode switching + arming rules (§4.2ter) — reuse the single-flight machinery
Introduce a single entry point the arm paths use, e.g. `VoiceTypingDaemon._ensure_host(mode: str) -> bool`, that wraps the existing `_load_host()`/`_unload_host()` with mode awareness:

- **Resident child is mode X, arm in mode X** → instant (no reload). (`_load_host()` already short-circuits when resident + alive.)
- **Resident child is mode Y (≠ X), arm in mode X** → teardown the resident child via the existing bounded `_unload_host()` machinery, then spawn in mode X (~1–3 s reload, "Loading…" toast). This is the SAME bounded teardown idle-unload uses — reuse it, do not write a second teardown path. (Implementation note: the current `_load_host` short-circuits on `_models_loaded and _host is not None and _host.is_alive`; the mode-switch must FIRST tear down when `self._mode != requested_mode`, then fall through to spawn. Keep it under `_lock` so a racing arm/idle-unload serializes correctly — the teardown already holds `_lock` across `host.stop()`.)
- **Unloaded, arm in mode X** → spawn in mode X (same as a session's first arm).

On a successful spawn set `self._mode = mode` and seed the device cache from the child's mode-aware `ready` payload (`host.device` already carries the right models once `_child_resolved_device` takes `mode`).

Arm routing (all under the existing `_arm()`/`_disarm()` + graceful drain):
- `start()` / `toggle()` (normal) → `_ensure_host("normal")` then `_arm()`.
- `start_lite()` / `toggle_lite()` (lite) → `_ensure_host("lite")` then `_arm()`.
- `stop()` disarms either mode (no mode change). The idle auto-stop and idle-unload apply identically in lite mode (idle-unload tears down whichever mode is resident; the next arm reloads in whatever mode that arm requests).
- **toggle-lite semantics (pin these down):** `toggle_lite()` arms lite if the daemon is NOT currently armed-in-lite (covers both "fully off" and "armed-in-normal" → the latter is a one-reload switch to lite); disarms if already armed-in-lite. `toggle()` arms normal if not armed-in-normal (switching from lite is one reload); disarms if armed-in-normal. Each keybind is unambiguous.

### 3.5 Control socket + status + feedback (§4.2(3), §4.6, §4.8)
- `ControlServer._dispatch`: add `toggle-lite` → `daemon.toggle_lite()` (arm path → `_arm_response()`); `start-lite` → `daemon.start_lite()` → `_arm_response()`. `stop` disarms either. The arm response already carries `**status_snapshot()`.
- `VoiceTypingDaemon.status_snapshot()`: add `"mode": self._mode` ("normal" | "lite").
- `Feedback`: add `mode` to `_state` (default `"normal"`), add `set_mode(mode)` that writes on every arm/disarm. `state.json` gains `"mode": "normal" | "lite"`.
- `status.sh`: when `mode == "lite"`, prefix the listening line with `⚡` instead of `🎤` so the user sees at a glance which mode is armed. (One jq tweak in the existing render.)
- Start/stop toasts stay `Recording` / `Recording Stopped` in either mode (the keybind disambiguates); finals still toast `✔ <text>` per `notify_on_final`. No new toasts.

### 3.6 voicectl + keybind (§4.8, §4.10)
- `ctl.py`: add `"toggle-lite"` and `"start-lite"` to `_COMMANDS`; `format_result()` prints `mode:` (and reflects mode in the status block). Keep exit-code semantics (0 ok / 1 logical fail / 2 daemon down / 64 usage). Update the usage/epilog strings.
- `hypr-binds.conf`: add `bind = SUPER ALT, F, exec, <venv>/bin/voicectl toggle-lite` (F = "fast"). Keep the existing `SUPER ALT, D` normal bind. Update the file's header comment to document both binds.

---

## 4. Documentation impact (two modes — mirror the breakdown agent)

**Mode A — doc-with-work (ride with the implementing subtask):**
- `config.toml` `lite_model` line + comment (with the config task).
- `voice_typing/config.py` `AsrConfig` docstring + `__post_init__` string-validation list (with the config task).
- `voice_typing/daemon.py` `cfg_to_kwargs`/`build_recorder`/`_construct` docstrings + `VoiceTypingDaemon` mode-tracking comments (with the construction/daemon tasks).
- `voice_typing/recorder_host.py` `RecorderHost.__init__`/`spawn`/`_worker_main`/`_child_resolved_device` docstrings (with the host-mode task).
- `voice_typing/feedback.py` module-top state-shape comment + `set_mode` docstring (with the feedback task).
- `voice_typing/status.sh` header comment (with the status.sh task).
- `voice_typing/ctl.py` module docstring + `_COMMANDS`/usage/epilog (with the ctl task).
- `hypr-binds.conf` header comment (with the keybind task).

**Mode B — changeset-level documentation (final task, depends on all above):** `README.md` sweep — add `lite_model` to the config-tuning table; add a short "Lite mode" subsection (what it is, `voicectl toggle-lite` / `SUPER ALT, F`, ~half the VRAM, lower accuracy, one bounded reload to switch); extend the Hotkey section to list both binds; note lite in the Model-lifecycle section (~half VRAM when armed in lite). Cross-check `tests/ACCEPTANCE.md` references T7.

---

## 5. Test plan additions (§6 T7 + unit tests)

All new tests are ADDITIVE (do not change existing passing tests). Reuse the existing fakes (`_StubRecorder`-style host fakes, `_make_daemon()`, `_host_factory` injection).

**Unit tests (fast, CUDA-free — add to `tests/test_daemon.py` / `tests/test_config.py` / `tests/test_control_socket.py` / `tests/test_voicectl.py` / `tests/test_recorder_host.py`):**
- `config.py`: `lite_model` default `"small.en"`, parsed from TOML, rejected if non-string (`__post_init__`).
- `cfg_to_kwargs(mode="lite")`: asserts `model == realtime_model_type == cfg.asr.lite_model`, `use_main_model_for_realtime == True`, and all other kwargs equal to the normal-mode kwargs. `mode="normal"` unchanged. `mode="lite", force_cpu` → `tiny.en`.
- recorder-host: `RecorderHost(..., mode="lite")` stores it and passes `mode` into the spawn `args`; `_child_resolved_device(cfg, False, "lite")` reports `final_model == realtime_model == lite_model` (monkeypatched `cuda_check`).
- daemon: `self._mode` boot `"normal"`; `start_lite()`/`toggle_lite()` set mode `"lite"` + arm; arming lite while resident-in-normal triggers teardown-then-respawn (use a fake host factory that records spawns/teardowns and asserts exactly one reload + the new mode); arming lite while resident-in-lite is instant (no spawn); `status_snapshot()["mode"]` reflects `self._mode`; idle-unload then arm-lite reloads in lite.
- control socket: `toggle-lite`/`start-lite` dispatch → `toggle_lite`/`start_lite`; response carries `mode`.
- ctl: `toggle-lite`/`start-lite` are accepted (not exit 64); `format_result` renders `mode:`.

**T7 — Lite mode (§6 T7; `tests/test_feed_audio.py` lite variant + `voicectl`):** construct the lite recorder (`model = realtime_model_type = lite_model`, `use_main_model_for_realtime = True`) via `use_microphone=False` + `feed_audio` of `utt_simple.wav`; assert (a) **exactly ONE model is resident** — assert the large final model never initializes (the cleanest CUDA-free proxy: assert `use_main_model_for_realtime=True` reached the recorder and, where feasible, grep the child log / compare a lite VRAM snapshot ≈ half of normal via `nvidia-smi` in the existing `test_idle_and_gpu.sh` if cheap); (b) finals still arrive over the normal clean→type→record path and fuzzy-accuracy ≥ 70 % (lower bar than normal's 80 %, since `small.en` is the final model); (c) final-typed latency is materially lower than normal mode on the same utterance. Then over the socket: `toggle-lite` arms with `mode:"lite"`; `toggle-lite` again disarms; a subsequent `toggle` reloads into `mode:"normal"` (one reload); `status` reports the current `mode`.

---

## 6. Acceptance criteria additions (§7 #10)

10. **Lite mode (§4.2ter):** `voicectl toggle-lite` arms in lite mode using ONLY `lite_model` (the large model never loads — verified ≈ half the VRAM of normal mode on `nvidia-smi`); `voicectl toggle` arms in normal mode; switching between them costs one bounded reload; `status` and `state.json` report `mode`; both modes honor the graceful drain (§4.2 #2 — already landed).

---

## 7. Known risks & mitigations (additive)

| Risk | Mitigation |
|---|---|
| `use_main_model_for_realtime=True` does NOT actually skip the realtime engine on the installed version | Already VERIFIED against RealtimeSTT v1.0.2 (`initialization.py:447` early-returns). T7(a) re-asserts it (one-model resident). If a future RealtimeSTT upgrade regresses this, T7(a) fails loudly — do not silently load two models. |
| Mode-switch (teardown + respawn) races an arm or idle-unload | Reuse the EXISTING single-flight `_unload_host()`/`_load_host()` under `_lock` (no new lock). `_ensure_host(mode)` tears down under `_lock` then spawns; a concurrent arm waits, then spawns fresh in its own mode. Add a unit test (fake host factory) asserting exactly one reload + correct resident mode. |
| Lite CPU fallback forgets to downgrade `lite_model` to `tiny.en` | `cfg_to_kwargs(mode="lite", force_cpu=True)` must set `model=realtime_model_type="tiny.en"`; unit-test the force_cpu×lite combination. |
| `status` reports the normal models while armed in lite (stale cache) | `_child_resolved_device(mode)` reports the lite model on `ready`; `_load_host` re-seeds `self._resolved_device_cache = host.device` on every successful spawn (already does) → status reflects the resident mode. Unit-test `status_snapshot` model fields in lite. |
| `status.sh` breaks when `mode` is absent (older state.json during a rolling restart) | jq default `.mode // "normal"` so the ⚡ prefix only renders for an explicit `"lite"`. |

---

## 8. Suggested breakdown (proportionality: medium feature → 1 phase, 2 milestones)

- **Phase P1 — Lite mode.**
  - **M1 — Core lite mode (end-to-end feature).**
    - T1 — Config `lite_model` + recorder-construction `mode` plumbing (config.py + config.toml; cfg_to_kwargs/build_recorder/_construct; RecorderHost.__init__/spawn; _worker_main; _child_resolved_device). *(Mode A docs: config.toml, config.py, daemon.py construction docstrings, recorder_host.py docstrings.)*
    - T2 — Daemon mode-tracking + mode-switch + control-socket + feedback + status.sh + ctl + keybind (`self._mode`, `_ensure_host(mode)`, `start_lite`/`toggle_lite`; `_dispatch` toggle-lite/start-lite + status_snapshot `mode`; Feedback `set_mode`/state `mode`; status.sh ⚡; ctl `_COMMANDS`/format_result; hypr-binds SUPER ALT F). *(Mode A docs: daemon.py, feedback.py, status.sh, ctl.py, hypr-binds.conf.)*
  - **M2 — Tests + changeset-level docs.**
    - T1 — Unit tests (config, kwargs×mode×force_cpu, host mode threading, daemon mode-switch reload, control socket, ctl, status) + T7 lite feed-audio + VRAM/one-model assertion.
    - T2 — Mode B README sweep (config table, Lite-mode subsection, Hotkey section, lifecycle note) + `tests/ACCEPTANCE.md` T7 cross-check.
