# Research — P1.M2.T7.S1 cancel: control socket + recorder abort/discard + ctl + keybind + install

Scout session notes (read-only). Line numbers verified against HEAD.

## recorder_host.py (child + host IPC)

- `RecorderHost.abort()` (recorder_host.py:237-246): sets `self._abort_event` only. Does NOT discard audio.
- Child `_abort_handler` thread (recorder_host.py:517-524): polls `abort_event` every 0.2s, clears it,
  sets local `aborted` event, calls `recorder.abort()`. This is the ONLY thing that unblocks a child
  blocked in `recorder.text()` — a queued `('cancel',{})` cmd would NOT be read while the loop blocks
  in text() (comment at recorder_host.py:528-531 states this explicitly). ⇒ cancel MUST reuse the
  event-polling mechanism, not (only) the command queue.
- Child command loop (recorder_host.py:526-561): 'text' → clears abort_event + `aborted`, calls
  `_run_text_and_emit_final(recorder, evt_q, _child_on_final, aborted)`; 'disarm' → `set_microphone(False)`
  + `_clear_recorder_audio(recorder)` (:549-554); 'abort' → belt-and-suspenders `recorder.abort()`.
- `_clear_recorder_audio(recorder)` (recorder_host.py:586-620): drains `clear_audio_queue()`,
  `recorded_audio_queue`, `frames`, `last_frames`, sets `recorder.audio = None`. Every clear wrapped
  defensively (version drift never breaks disarm). This is the discard primitive cancel needs.
- `_run_text_and_emit_final` (recorder_host.py:~623-646): runs `recorder.text(on_final)`; if
  `aborted.is_set()` OR return value non-None → `_safe_put(evt_q, ("final", {"text": ""}))` sentinel.
  VT-007 dual-signal contract. The event payload is a plain dict — we can add a `"cancelled": True`
  key without breaking any existing consumer (daemon reader only reads `.get("text")`).
- Host `text()` (recorder_host.py:248-278): puts `("text",{})`, blocks on `_final_evt`; reader thread
  invokes `self._on_final(text)` when a 'final' event arrives.
- Host events are multiprocessing Events created where? abort_event is a MP event shared daemon↔child
  (abort works across processes). A cancel flag must live on the same cross-process channel.

## daemon.py

- `ControlServer._dispatch` (daemon.py:1852+, commands at :1874 'stop', :1877 'status', :1879 'quit').
  Protocol docstring :1696-1697. Response shapes: 'stop' → `{"ok":True, **status_snapshot()}`.
  Unknown → `{"ok":False,"error":f"unknown command: {cmd!r}"}`.
- `status_snapshot()` (daemon.py:1613-1646) — reuse for cancel response; contract wants
  `{"ok":true,"listening":true}` minimum.
- `_safe_abort` (daemon.py:1400-1428): SKIPS abort unless `_text_in_flight` (abort otherwise blocks on
  `was_interrupted.wait()`). Cancel must respect the same gate.
- `on_final` pipeline: listening gate (daemon.py:982-983) → `_on_final_lock` (988) →
  `textproc.clean` (989) → `_backend.type_text` (996) → `feedback.record_final` (1000).
  Streaming (P1.M2.T6) will add committed/tail state here; cancel needs a suppression flag so a
  REAL final racing the cancel is dropped (clean('') rejection alone is not race-safe).
- `_lock` usage around arm/disarm transitions (`_request_stop` :1105-1130) — cancel takes `_lock`.
- backend: `press_backspace(n)` exists on the ABC + wtype/ydotool/null (typing_backends.py:69-171),
  batched, added by P1.M1.T3.S1 (complete).

## ctl.py

- `_COMMANDS` (ctl.py:37): currently `("toggle","start","stop","status","quit")` with a comment noting
  'cancel' is appended by P1.M2.T7.S1. Docstring Subcommands block + "Usage:" line (~:26-28) list
  commands; argparse `_build_parser` epilog mirrors it.
- `format_result` (ctl.py:~47+): ok-check → shutting_down branch → status branch → default
  "listening: on/off". A cancel reply `{"ok":True,"listening":True,...}` renders via the default
  branch as "listening: on" — no renderer change strictly needed, but add explicit doc.
- Exit codes 0/1/2/64; cancel is NOT an arm command (no loading hint).

## hypr-binds.conf + install.sh

- hypr-binds.conf already contains commented placeholder lines for the cancel bind:
  `# (P1.M2.T7.S1) cancel fallback bind — ADDED by that task:` + the commented `bind = SUPER ALT, Backspace...`
  — this task UNCOMMENTS/activates them and adds doc prose (evdev fallback rationale, PRD §4.2quater).
- install.sh usage lines :209-210:
  `echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit"` and the bind line :210.
  Both must gain `cancel`; add a Backspace-bind mention (R8).

## Tests seams (from architecture/daemon_control_map.md §6)

- tests/test_control_socket.py: `test_dispatch_lite_commands_call_daemon` (:131) pattern — fake daemon
  object with method stubs; `_dispatch` invoked directly.
- tests/test_daemon.py: `_FakeHost` (:532-613) mirrors RecorderHost surface — extend with `cancel()`;
  `_FakeBackend` (:493-504) records `typed` — extend to record `press_backspace` calls;
  `_make_lazy_daemon(cfg, host_factory)` (:2859-2867), `mic_prober=_ok_probe`.
- tests/test_recorder_host.py: fake recorder pattern exists for abort/sentinel tests — reuse for the
  cancelled-sentinel + `_clear_recorder_audio` discard test (assert clear_audio_queue called).
- tests/test_voicectl.py: `test_lite_commands_are_accepted_and_routable`-style tests for _COMMANDS list.

## Dependency note

P1.M2.T6 (streaming committed/tail state machine) is PLANNED, not implemented. The daemon cancel()
logic needs "is a tail pending?" + "reset tail". PRP defines a narrow seam: the streaming state
object exposes `pending_tail_len()` and `reset_after_cancel()`; if T6 has landed under different
names, adapt at the single call site in `cancel()`. When T6 is absent, cancel degrades to
abort+discard+suppress only (no backspaces) — tests use the seam, not concrete T6 internals.
