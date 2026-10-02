# daemon / control-socket / recorder-host structural map (HEAD 6b61db1)

Grounding for Rev 2: single-mode collapse, streamed partials, Backspace-cancel. Every claim cites `file:line`. Files read: `voice_typing/daemon.py` (2300L), `voice_typing/ctl.py` (219L), `voice_typing/recorder_host.py` (774L), `voice_typing/feedback.py` (262L), `voice_typing/config.py` (348L), `tests/test_daemon.py`, `tests/test_control_socket.py`, `tests/test_voicectl.py`.

## 1. Mode machinery in daemon.py

### `self._mode` lifecycle
- Declared `self._mode: str = "normal"` at `daemon.py:656`; doc comment at 653-655 ("normal" = two models, "lite" = lite_model only).
- Set ONLY at `daemon.py:778` (`self._mode = mode`) on a successful `_load_host()` publish (under `_lock`).
- Read at: `daemon.py:1039` (`_arm` → `self._feedback.set_mode(self._mode)`), 1473/1501 (`toggle`/`toggle_lite` read `mode` under `_lock`), 1632 (`status_snapshot` → `"mode": self._mode`).
- Never reset on disarm/unload/dead-host: `unload_host` (daemon.py:1299) and `_handle_dead_host` (daemon.py:926-940) leave `_mode` as the last resident mode.

### `cfg_to_kwargs()` (daemon.py:158-215)
Signature: `cfg_to_kwargs(cfg, *, resolved=None, lite=False)`.
- `resolved` defaults to `_resolve_device_config(cfg)` (daemon.py:141-155) which returns `{device, compute_type, final_model, realtime_model}` via `cuda_check.resolve_device_and_models(defaults)` (daemon.py:155).
- **lite branch pre-kwargs** (daemon.py:184-193): copies `resolved` (dict(resolved)); `lite_model = "tiny.en" if resolved["device"]=="cpu" else cfg.asr.lite_model`; sets `resolved["final_model"]=resolved["realtime_model"]=lite_model`.
- **common kwargs dict** (daemon.py:194-203): `model=resolved["final_model"]`, `realtime_model_type=resolved["realtime_model"]`, `language=cfg.asr.language`, `device=resolved["device"]`, `compute_type=resolved["compute_type"]`, `realtime_processing_pause=cfg.asr.realtime_processing_pause`, `post_speech_silence_duration=cfg.asr.post_speech_silence_duration`; then `kwargs.update(_FIXED_KWARGS)` (daemon.py:204).
- `_FIXED_KWARGS` (daemon.py:100-114) includes `"use_main_model_for_realtime": False` (daemon.py:101) and `"enable_realtime_transcription": True`.
- **lite overrides** (daemon.py:205-214): `kwargs["use_main_model_for_realtime"]=True` (209) and `kwargs["post_speech_silence_duration"]=cfg.asr.lite_post_speech_silence_duration` (213).
- Config defaults: `final_model="distil-large-v3"`, `realtime_model="small.en"`, `lite_model="small.en"` (config.py:52-54); `post_speech_silence_duration=0.6`, `lite_post_speech_silence_duration=0.5` (config.py:58-59).

### resolved[...] dict shape
`{device, compute_type, final_model, realtime_model}` — built at daemon.py:149-154 (defaults) / returned by cuda_check at 155. Also produced un-probed by `_unprobed_device_config()` (daemon.py:1669-1684) and by the child (`recorder_host.py` "ready" event, daemon.py:781 caches `host.device`).

### Mode-switch reload branch in `_load_host()` (daemon.py:710-805)
- Fast path / mismatch detect under `_lock` (727-736): if resident+alive AND `getattr(self._host,"mode","normal")==mode` → `return True` (733); else `switch_mode=True` (734). Single-flight wait at 735-737.
- Reload branch (748-754): if `switch_mode` → `_bounded_shutdown(timeout=5.0)` under `_lock`, `self._host=None`, `_models_loaded=False`.
- Spawn OUTSIDE `_lock` (755-772): real path passes `is_listening=self.is_listening, mode=mode` (762-767); test-fake path (`host_factory` set) omits `is_listening` (768-772).
- Publish (773-805): on ok → `_host=host`, `_models_loaded=True`, `_mode=mode` (778), `_resolved_device_cache=host.device` (782). On failure → `host.stop()`, `_load_error="recorder host spawn failed"` (795-798).
- `_load_recorder()` alias → `_load_host("normal")` (daemon.py:700-708).
- Callers: `start()` → `_load_host("normal")` (daemon.py:1434); `start_lite()` → `"lite"` (1448); `toggle()` arm branch → `"normal"` (1478); `toggle_lite()` → `"lite"` (1506). **This is the entire two-mode surface to collapse.**

### RecorderHost-side mode
`RecorderHost.__init__(..., mode: str = "normal")` (recorder_host.py:103,114); `self._mode=mode` (125); `mode` property (168-170); passed to the spawn child (`_worker_main(..., mode)` recorder_host.py:195, 421-427); child `lite = mode == "lite"` (recorder_host.py:458) → `build_recorder(..., lite=lite)` (470, 478). "mode is a spawn-time property of this child; it cannot change without a reload" (456-457).

## 2. Event flow child → daemon

### Queues & threads (recorder_host.py module docstring 18-52, code 133-160)
- `cmd_q` daemon→child: `("arm",{}) | ("disarm",{}) | ("text",{}) | ("shutdown",{})` (+ belt-and-suspenders `("abort",{})`, recorder_host.py:19-22, 549-552).
- `evt_q` child→daemon: `("ready",{device...}) | ("error",{msg}) | ("final",{text}) | ("partial",{text}) | ("speech",{}) | ("speech_end",{}) | ("vad",{phase}) | ("gone",{})` (recorder_host.py:23-30).
- Separate `abort_event` (mp.Event, recorder_host.py:146) because the child loop blocks in `text()` and can't read cmd_q (141-145).
- Daemon-side reader thread `_read_loop` (recorder_host.py:331-352) drains evt_q → `_dispatch` (354-392) → daemon callbacks: `final` → `self._on_final(text)` ON THE READER THREAD (362-369); `partial` → `self._on_partial(text)` (371-373); `speech` → `self._on_speech()` (= `_touch_speech`) (374-375); `vad` → `feedback.set_phase` gated by `is_listening` (377-390); `gone` → reader exits (341-345). EOF → `_dead=True` + `_final_evt.set()` + `_ready_evt.set()` (346-352).

### Partials TODAY — feedback only, NO typing
- Daemon `_on_partial` (daemon.py:1094-1103): `self._feedback.update_partial(text)` + `self._latency.note_partial(text)`. That is ALL — no backend call anywhere on the partial path. **This is the seam for Rev 2 streamed partials.**
- Child-side relay: `_RelayFeedback.update_partial` → `("partial",{text})` (recorder_host.py:32-42, 462-464).
- In-process mirror callback `_build_callbacks._partial` (daemon.py:233-240): `feedback.update_partial` + `latency.note_partial` + `on_speech()`.

### Finals → typing
- `on_final` (daemon.py:980-1040): listening gate 982-983 (`if not self._listening.is_set(): return`); `_on_final_lock` serialize (988); `cleaned = textproc.clean(text, self._cfg.filter)` (989); reject if empty (990) — textproc.clean returns None when `len < cfg.min_chars` (textproc.py:58) or blocklist match (textproc.py:61-66); `payload = cleaned + (" " if append_space)` (994); **`self._backend.type_text(payload)` at daemon.py:996**; `feedback.record_final(cleaned)` (1000); latency log (1005-1039).
- Run loop drives `host.text(self.on_final)` while `_listening` set (daemon.py:869-899); `_text_in_flight` set/cleared around it (896-899).

## 3. Stop / drain / abort

- `_request_stop` (daemon.py:1105-1130): if host alive AND `_text_in_flight` AND `_final_pending` → `_begin_drain()` (1124); else `_disarm()` under `_lock` + `_safe_abort()` (1125-1129).
- `_begin_drain` (1131-1140): sets `_drain`, arms `threading.Timer(_DRAIN_TIMEOUT_S=5.0, _drain_timeout)` (daemon.py:131-133 constant; 1134-1139).
- Run loop sees `_drain` after text() returns → `_complete_drain` (daemon.py:852-856 → 1142-1160): `_disarm()` + cancel timer.
- `_drain_timeout` watchdog (1162-1176): if still draining + in text() → `_safe_abort()` (1175).
- `_safe_abort` (1400-1428): **skips abort entirely unless `_text_in_flight`** (1423-1424) — RealtimeSTT abort blocks on `was_interrupted.wait()` otherwise; calls `self._host.abort()` (1426).
- `_handle_dead_host` (893-940): race-guard no-op if already unloaded (926-929); else host=None, `_models_loaded=False`, clear `_listening`, phase "unloaded", `_load_error="recorder-host child died unexpectedly"` (930-931), reseed device cache (936-939).
- **RecorderHost.abort() semantics** (recorder_host.py:237-246): sets `self._abort_event`; the child's `_abort_handler` thread (517-524) polls it and calls `recorder.abort()` (522). It does NOT discard buffered audio by itself — **discard happens on DISARM**: child command loop `("disarm",{})` → `set_microphone(False)` + `_clear_recorder_audio(recorder)` (recorder_host.py:549-554); `_clear_recorder_audio` (586-620) drains `clear_audio_queue()`, `recorded_audio_queue`, `frames`, `last_frames`, `audio` — kills the double-type bug.
- Abort-sentinel: `_run_text_and_emit_final` (recorder_host.py:~623; referenced 511-515, 544-548) guarantees a `("final",{...})` event even on the abort path (else host.text() would wedge).
- Child supervision: child does `os.setsid()` (recorder_host.py:443-449) → own group; `stop()` (272-330) is single-flight (`_stop_lock` 148-152), sets abort event (294-296), best-effort `("shutdown",{})` on a daemon thread (307-311), bounded join (`_STOP_JOIN_TIMEOUT_S` ~5s, 84), then `_terminate_group()` (394-411) = `os.killpg(pgid, SIGKILL)` (407).
- Daemon `_bounded_shutdown` (daemon.py:1685-1712) wraps `host.stop(timeout)`; `request_shutdown` (1519-1571) and `shutdown()` (1712-1798) coordinate single-flight via `_shutdown_done`/`_teardown_done`.

## 4. Control socket

- Daemon-side dispatch: `ControlServer._dispatch(line)` (daemon.py:1957-2020). Commands: `toggle` (1966-1988), `start` (1989-1991), `start-lite` (1989+2 lines: 1990 `start_lite()` → `_arm_response`), `toggle-lite` (1992-2013), `stop` (2014-2016), `status` (2017-2018), `quit` (2019+ → `request_shutdown()` + `on_quit` → `{"ok":true,"shutting_down":true}`). Unknown → `{"ok":false,"error":f"unknown command: {cmd!r}"}` (2020).
- Response shapes (protocol doc daemon.py:1801-1806): arm cmds → `_arm_response()` (1940-1955): `{"ok":False,"error":"model load failed: <_load_error>"}` when `_load_error` and not listening, else `{"ok":True, **status_snapshot()}`. `stop`/`status` → `{"ok":True, **status_snapshot()}`. Malformed JSON → `{"ok":false,"error":"malformed JSON: ..."}` (1960-1963); non-dict → `"request must be a JSON object"` (1964-1965).
- `status_snapshot()` (daemon.py:1613-1646): `{listening, mode, phase, models_loaded, load_error, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model, mic_ok, mic_error}` — mode key at 1632.
- Wire: `_handle` per-connection loop, one JSON per line (daemon.py:1909-1938); `makefile("r")` with NO read timeout (the AGENTS.md voicectl-hang root).
- ctl.py: `_COMMANDS = ("toggle","start","stop","status","quit","toggle-lite","start-lite")` (ctl.py:37); `_EX_USAGE=64` (ctl.py:39); argparse `_build_parser` with description+epilog listing all 7 subcommands (ctl.py:~151-165); `main()` validates `cmd not in _COMMANDS` → prints to stderr, returns 64 (ctl.py:~171-180); arm cmds (`start/toggle/start-lite/toggle-lite`) routed via `_send_command_with_loading_hint` (ctl.py:~199-200, 126-137) with `_LOADING_HINT_DELAY=0.3` (ctl.py:42); exit codes 0/1/2/64 (ctl.py:6-13).
- `format_result` renders status multi-line incl. `mode: {mode}` (ctl.py:69, 90) and `models: {final} + {realtime}` (ctl.py:96).

## 5. feedback.py + state.json

- Path: `$XDG_RUNTIME_DIR/voice-typing/state.json`, overridable via `feedback.state_file`; resolved lazily in `_write()` (feedback.py:10, 46-48).
- Schema (feedback.py:11, 95-102): `{"listening":bool, "phase":"unloaded|loading|idle|listening|speaking", "models_loaded":bool, "mode":"normal|lite", "partial":str, "last_final":str, "ts":epoch}`.
- `update_partial(text)` (109-120): always updates in-memory `partial` (115); disk write THROTTLED ≥10 Hz (`_PARTIAL_WRITE_MIN_INTERVAL=0.1`, feedback.py:74-76, 117-118); NEVER notifies (28).
- `record_final(text)` (153-~175): sets BOTH `last_final` and `partial` (156-158), always writes, maybe hyprctl toast gated by `notify_on_final`.
- `set_mode(mode)` (145-151): always writes, never notifies. `set_phase` (122-131), `set_models_loaded` (133-143), `set_listening` (toast "Recording"/"Recording Stopped" on transitions, 20-23).
- Atomic write: mkstemp + os.replace, 0600/0700 (feedback.py:34-37).

## 6. Test seams for new daemon unit tests (pattern to copy)

From tests/test_daemon.py:
- `_FakeFeedback` (test_daemon.py:32-58) + `_DaemonFakeFeedback` (451-464, adds `record_final`/`set_listening` recording lists).
- `_StubRecorder` (466-490): `text(on_transcription_finished)` / `set_microphone` / `abort` / `shutdown`, records calls.
- `_FakeBackend` (493-504): records `typed` list, optional `raise_on`.
- `_FakeHost` (532-613): mirrors real RecorderHost surface (`spawn/set_microphone/abort/text/stop/device/is_alive/pid/mode`), wraps a `_StubRecorder`, records `spawn_calls`/`stop_calls`, `mode` attribute settable (570).
- `_fake_host_factory(spawn_result, device, mode)` (615-632) — pass as `host_factory=`; `_load_host` calls it with `(cfg, feedback, latency, on_final, on_partial, on_speech, **kw)` (daemon.py:768-772).
- `_make_daemon(*, recorder, recorder_host, host_factory, backend, cfg)` (618-630): builds `daemon.VoiceTypingDaemon(cfg, fb, ..., mic_prober=_ok_probe)` — `mic_prober=_ok_probe` (506-513) is what keeps it PyAudio-free.
- `_make_lazy_daemon(cfg, host_factory)` (2859-2867): recorder=None + host_factory. `_cuda_resolve(monkeypatch, mapping)` (80-100) stubs `daemon.cuda_check.resolve_device_and_models`. `_wait_for(predicate)` (515-523) for async asserts.
- **Streaming unit tests should**: extend `_FakeHost`/`_StubRecorder` to capture the `on_partial` callback and drive committed/tail state-machine asserts through `daemon._on_partial` (daemon.py:1094) and a new cancel path; use `_FakeBackend.typed` for expected typed output; keep `mic_prober=_ok_probe`.

### Two-mode tests (grep results, `toggle_lite|start_lite|_mode|lite` in tests/):
tests/test_daemon.py: `test_cfg_to_kwargs_lite_mode_uses_one_model` (138), `..._lite_cpu_fallback_uses_tiny_en` (165), `..._lite_keeps_all_other_kwargs_equal` (185), `..._lite_uses_shorter_silence_duration` (216), `test_start_lite_loads_lite_host_and_arms` (2964), `test_mode_switch_normal_to_lite_reloads` (2976), `test_same_mode_arm_is_instant_no_reload` (2993), `test_toggle_lite_while_listening_in_lite_stops` (3005), `test_status_snapshot_reports_mode` (3019), `test_mode_switch_stops_outgoing_host` (3028), `test_start_lite_after_idle_unload_reloads_in_lite` (3052), `test_toggle_lite_while_idle_arms_in_lite` (3865), `test_toggle_lite_while_armed_in_lite_disarms` (3877), `test_toggle_lite_while_armed_in_normal_switches_to_lite` (3888), `test_toggle_while_armed_in_lite_switches_to_normal` (3922), `test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening` (3959), `test_toggle_while_armed_in_lite_failed_reload_clears_listening` (3978), `test_failed_cross_mode_toggle_status_snapshot_is_honest` (3995), `test_dispatch_toggle_cross_mode_lite_to_normal_failure_returns_ok_false` (4013), `test_dispatch_toggle_lite_cross_mode_normal_to_lite_failure_returns_ok_false` (4031), `test_toggle_lite_docstring_says_pressing_d_not_f` (4053). Plus lite kwargs asserts at test_daemon.py:147-149, 179-182, 206-212, 225, 229, 238, 2747/2769/2816, and `_construct/build_recorder` signature asserts `"lite" in sb` (2824-2835).
tests/test_control_socket.py: `test_dispatch_lite_commands_call_daemon` (131), `test_dispatch_status_response_carries_mode` (143).
tests/test_voicectl.py: `test_format_status_multiline_has_partial_and_models` (62), `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` (75).
tests/test_feedback.py: `test_set_mode_writes_mode_field` (138), `test_state_file_mode_0600` (172), `test_state_dir_mode_0700` (179).
tests/test_config.py: lite config asserts 43-49, 84, 254-276. tests/test_config_repo_default.py:56. tests/test_feed_audio.py:653, 679 (real CUDA — do not run per AGENTS.md). tests/test_idle_and_gpu.sh T7 (535-578) drives real mode-switch roundtrip.

## 7. Mode in status + consumers

- Produced: `status_snapshot()["mode"]` daemon.py:1632 (from `self._mode`); `feedback.set_mode` → state.json `"mode"` (daemon.py:1039 → feedback.py:145-151, schema line 99).
- Consumed:
  - `ctl.py:69` (`mode = response.get("mode","normal")`) → printed as `mode: {mode}` line (ctl.py:90).
  - `tests/test_idle_and_gpu.sh:543-578` (T7 polls `voicectl status | grep '^mode: lite'`).
  - Tests: test_control_socket.py:158, test_daemon.py:3019-3026, test_voicectl.py:75+, test_feedback.py:138.
  - `hypr-binds.conf:52`: `SUPER+ALT+D -> voicectl toggle-lite` (comment line 6) — the other keybind (`toggle`, presumably SUPER+ALT+F region) is the normal-mode entry. Rev 2 deleting lite commands must update this file + `tests/test_config_repo_default.py:56`.

## Key seams for Rev 2 (summary)

- **Mode collapse points**: `cfg_to_kwargs(lite=)` (daemon.py:158-215), `_FIXED_KWARGS["use_main_model_for_realtime"]` (101), `_load_host(mode)` + switch branch (710-805), `_mode` (656/778/1039/1632), `start_lite` (1441-1451), `toggle`/`toggle_lite` cross-mode logic (1458-1516), `_load_recorder` alias (700-708), `build_recorder/_construct(lite=)` (285-345), RecorderHost `mode` param (recorder_host.py:103-125, 427, 458-478), control cmds `start-lite`/`toggle-lite` (daemon.py:1989-2013), ctl `_COMMANDS` (ctl.py:37, 158-165), feedback `set_mode`/`"mode"` field, hypr-binds.conf:52, config `lite_model`/`lite_post_speech_silence_duration` (config.py:54,59).
- **Partial typing seam**: `VoiceTypingDaemon._on_partial` (daemon.py:1094-1103) — reader thread already delivers every partial; only feedback/latency consume it today. A committed/tail state machine belongs here (or between here and backend.type_text).
- **Cancel hook**: a new control command in `ControlServer._dispatch` (daemon.py:1957-2020, mirroring `stop` at 2014) → a daemon method alongside `_request_stop` (1105) that calls `_safe_abort()`/`_disarm()`; child-side discard is already `_clear_recorder_audio` on disarm (recorder_host.py:549-554, 586-620) — a cancel may reuse the `abort_event` (recorder_host.py:246) + `_run_text_and_emit_final` sentinel.
- **Test-double pattern**: `_make_lazy_daemon(host_factory=_fake_host_factory(...))` + `_FakeHost`/`_StubRecorder`/`_FakeBackend`/`_DaemonFakeFeedback` with `mic_prober=_ok_probe` (test_daemon.py:32-632, 2859-2867).
