# System Context — voice-typing Rev 2 (plan/007)

**Session type:** Delta breakdown. Base PRD `PRD.md` @ `6b61db1` (already Rev-2-revised); Rev 1 fully
implemented + audited (plan/006, `tests/ACCEPTANCE.md` rows 1–10 PASS). HEAD at research time:
`6b61db1`; prior landing `ccf95eb` already removed the tmux surface (`status.sh` gone,
`NullBackend` in place, e2e uses `backend="null"` + `state.json` asserts).

**Scope:** exactly the Rev 2 delta — (R1) single-mode collapse, (R2) `press_backspace(n)`,
(R3) streaming committed/tail output engine, (R4) Backspace-cancel + evdev listener,
(R5) rolling context prompt, (R6) textproc guards, (R7) config schema delta, (R8) evdev dep.
Everything else in PRD.md is implemented and verified — reference plan/006, do not rebuild.

## Research reports (this directory — downstream agents MUST read the relevant one)

| File | What it grounds |
|---|---|
| `daemon_control_map.md` | Mode machinery seams, partial/final IPC, drain/abort, control socket, state.json, test-double pattern (`_FakeHost`/`_StubRecorder`/`_FakeBackend`/`_make_lazy_daemon`) |
| `substrate_map.md` | config schema + validation patterns, cuda_check, prefetch, typing backends, textproc, binds, install.sh, packaging, full test inventory, README sweep list |
| `realtimestt_internals.md` | Installed RealtimeSTT 1.0.2 prompt plumbing, realtime pipeline, abort/buffer semantics |
| `external_deps.md` | evdev API + version, wtype/ydotool key batching, KEY_BACKSPACE=14, machine perms |

## PRD vs reality — corrections downstream agents MUST honor

1. **R4's "existing `RecorderHost.abort()` discards its buffered audio" is WRONG.**
   `abort()` (recorder_host.py:237-246) only unblocks `text()`; the child still queues the utterance
   frames and `_run_text_and_emit_final` emits a SENTINIAL `("final", ...)` event. Buffer discard is
   `_clear_recorder_audio` (recorder_host.py:586-620), currently called only on DISARM
   (:549-554). **Cancel must:** abort + clear the child's buffers + mark/suppress the sentinel
   final so nothing is typed or recorded after a cancel (T8e's "no late commit").
2. **R5's "attribute poke" only works when `use_main_model_for_realtime=False`.** Our single-model
   construction uses `=True`, so BOTH partial and final decodes go through the transcription WORKER
   SUBPROCESS whose `TranscriptionEngineConfig` bakes `initial_prompt` at worker start
   (installed `core/transcription.py:93-107`); the worker pipe protocol carries no prompt updates.
   The child must implement dynamism via a fork-inherited shared value + monkeypatch applied before
   recorder construction (Linux fork propagates it into the worker), verified by a startup
   capability probe; on probe failure degrade to context-free decoding and log ONCE (never crash).
   T8d asserts prompts when dynamic mode is active, else asserts the degrade log.
3. **wtype has no `--help`**; repeatability of `-k` verified via its man page synopsis
   (`wtype [OPTION_OR_TEXT]... -- [TEXT]...`) — see `external_deps.md`. Batching = ONE subprocess.
4. **Decision (PRD R1 leaves it open): status/state.json KEEPS `mode`, constant `"lite"`.**
   Smaller blast radius: §4.6 schema stable, `ctl.py:69/90` rendering, `feedback.set_mode`,
   `test_feedback.py` untouched. Daemon writes the constant at arm.
5. **`test_config_repo_default.py` pins the exact key set AND comment text** (asserts the
   `lite_model` line mentions `SUPER+ALT+D`). With the bind collapse (one `CTRL SUPER ALT, D`
   toggle bind + new `SUPER ALT, Backspace` cancel bind), both the config.toml comment and the
   test's expected text must change together (T1.S1 ↔ T2.S4 end-state).
6. **transient red between T2.S1 (cuda_check contract) and T2.S2 (daemon consumers):** intended;
   each subtask keeps its OWN tests green. See T2.S1 context_scope.

## Where things live (seam index, from the research reports)

- **Mode collapse:** `daemon.py` `cfg_to_kwargs`:158-215 (lite pre-kwargs 184-193, common
  194-203, `_FIXED_KWARGS`:100-114 with `use_main_model_for_realtime:False` @101, lite overrides
  205-214), `_load_host`:710-805 (switch_mode 748-754), `self._mode`:656/778/1039/1632,
  `start_lite`:1441-1451, `toggle`/`toggle_lite`:1458-1516, `_load_recorder` alias:700-708,
  dispatch `start-lite`/`toggle-lite`:1989-2013, `status_snapshot` model keys:1641-1642;
  `recorder_host.py` mode param:103-125/427/458-478, ready payload 681-714;
  `cuda_check.py` `CUDA_DEFAULTS`/`CPU_FALLBACK`:46-59; `ctl.py:37`+158-165+69/90/96;
  `prefetch.py`:36-47; `config.py`:52-53/59; `hypr-binds.conf`:57/59; `install.sh`:205-210.
- **Streaming seams:** partials land on reader thread → `_on_partial` daemon.py:1094-1103 (the
  typing seam; today feedback+latency only); `on_final`:980-1040 (listening gate 982,
  `textproc.clean` 989, `backend.type_text(cleaned+" ")` 996, `record_final` 1000);
  drain: `_request_stop`:1105-1130, `_begin_drain`:1131-1140, `_complete_drain`:1142-1160,
  `_drain_timeout`:1162-1176, `_safe_abort`:1400-1428; `_handle_dead_host`:893-940;
  `_clear_recorder_audio` recorder_host.py:586-620; evt_q events recorder_host.py:23-30;
  cmd_q commands :19-22; `_abort_handler`:517-524 (side-thread pattern for prompt watcher).
- **Control socket:** `ControlServer._dispatch` daemon.py:1957-2020 (`stop` @2014 is the template
  for `cancel`), `_arm_response`:1940-1955; `ctl.py` `_COMMANDS`:37, exit-64 path 174-183.
- **Test doubles to copy:** test_daemon.py:32-632 (`_FakeFeedback`/`_StubRecorder`/`_FakeBackend`/
  `_FakeHost`/`_fake_host_factory`/`_make_daemon`/`_make_lazy_daemon` @2859-2867, `mic_prober=_ok_probe`).
- **Mode/two-model test family to delete/rewrite:** test_daemon.py (list in daemon_control_map §6),
  test_control_socket.py:131/143, test_voicectl.py:62/75, test_config*.py field pins,
  test_idle_and_gpu.sh:535-578.

## Machine facts (verified this session)

- venv Python 3.12.10; `uv.lock` present; evdev NOT yet installed (system python either);
  user `dustin` in group `input` (994); `/dev/input/event*` `crw-rw---- root:input` → evdev
  open works with no permission changes.
- `KEY_BACKSPACE = 14` (`/usr/include/linux/input-event-codes.h:90`).
- ydotool installed: `ydotool key [OPTION]... [KEYCODES]...`, `-d/--key-delay`, raw `14:1 14:0`.
- wtype installed: `-k KEY` press+release, named keys via libxkbcommon, options repeat per
  man synopsis (parse probe in external_deps.md).

## Operating constraints for ALL downstream agents

- AGENTS.md is binding: every bash command under an inner `timeout`; harness timeout above it;
  NEVER foreground the daemon; `voicectl` always under `timeout 30`; pytest per-file under
  `timeout 600` (CUDA loads); the two shell E2E suites only when the task is literally about them.
- Implicit TDD: every subtask = failing test → implement → pass. No separate test subtasks.
- Docs: Mode A rides with each implementing subtask (see each context_scope DOCS line); the final
  Mode B task (`P1.M3.T10`) sweeps README + install usage and depends on everything.
- Full-path binaries (`/home/dustin/.local/bin/uv`, `.venv/bin/python`) — shell aliases are traps (PRD §5).

## Process notes (for the record)

- Async/background subagent children are broken in this harness (host npm package missing);
  research ran as sequential foreground `scout` children (one per turn), whose in-chat reports were
  persisted to this directory. The web `researcher` child cannot load MCP tools in foreground
  mode; the parent performed the two web checks directly (evdev version/API).
- No verbatim `@include` lines remained in the delivered PRD — nothing unresolved.
