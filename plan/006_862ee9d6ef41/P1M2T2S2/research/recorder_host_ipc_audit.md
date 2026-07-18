# Research — Recorder-Host IPC audit (P1.M2.T2.S2 / PRD §4.2bis)

This note pins the exact IPC mechanism in `voice_typing/recorder_host.py`, maps each of the
item's 6 properties (a)-(f) to the code's actual behavior (file:line), records the test
evidence, and lists the non-defect nuances. The PRP (../PRP.md) transcribes these findings
into the §2 IPC section appended to `gap_lifecycle.md`. All line numbers verified live on
2026-07-18. **Verdict: ✅ COMPLIANT — all 6 properties pass; the actual IPC vocabulary is
richer than the item's shorthand but fully satisfies PRD §4.2bis's intent.**

## 0. The IPC architecture (one sentence)

`RecorderHost` owns the `AudioToTextRecorder` in a managed **child subprocess** (spawn). The
daemon proxies arm/disarm/text/shutdown over a `cmd_queue`; a separate `abort_event` (mp.Event)
interrupts a child blocked in `text()`; the child relays partial/final/vad/speech events over an
`evt_queue` to a daemon **reader thread** that dispatches them to the real Feedback/LatencyLog/
on_final/on_partial/on_speech. `stop()` SIGKILLs the child's process group (the bounded teardown).

## 1. The two queues + the event (the IPC primitives)

- `cmd_q` (daemon→child): `mp.get_context("spawn").Queue()` — `recorder_host.py:139`.
  Carries `("arm", {}) | ("disarm", {}) | ("text", {}) | ("shutdown", {})`. The module docstring
  (L18-22) documents this exact vocabulary.
- `evt_q` (child→daemon): spawn-context `Queue()` — `recorder_host.py:140`. Carries the event
  vocabulary in §3 below.
- `abort_event` (daemon→child): spawn-context `mp.Event()` — `recorder_host.py:146`. A DEDICATED
  interrupt signal (NOT a cmd_q command) — see nuance §4.1.
- All three share the SAME `spawn` context as the `Process` (L135-143) to avoid the
  "SemLock created in a fork context..." error (comment L133-138).

## 2. The 6 item properties — file:line evidence + verdict

### (a) spawn() creates the child via multiprocessing.Process with target=_worker_main — ✅ COMPLIANT
`RecorderHost.spawn()` (`recorder_host.py:181-228`) builds the Process at **L193-200**:
```python
self._proc = ctx.Process(
    target=_worker_main,
    args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event, self._force_cpu, self._mode),
    name="voice-typing-recorder-host",
    daemon=True,
)
self._proc.start()   # L201
```
`ctx = mp.get_context("spawn")` (L189). It then starts the reader thread (L203-205) BEFORE the
ready-wait (L207-213) so load-time events drain. `spawn()` waits on `self._ready_evt` for the
child's 'ready'/'error' (the model load happens IN THE CHILD → the daemon stays CUDA-free).

### (b) child calls os.setsid() for process-group isolation — ✅ COMPLIANT
`_worker_main` calls `os.setsid()` at **L446** as its FIRST syscall (comment L443-445: "Must be
the first syscall so any RealtimeSTT-spawned mp.Process inherits our pgid"). The daemon's
`_terminate_group()` (**L394-413**) does `os.killpg(os.getpgid(pid), signal.SIGKILL)` (**L407**) —
the child is its own group leader → killpg reaches its RealtimeSTT-spawned grandchildren
(transcript_process/reader_process). `stop()` (L272-329) calls `_terminate_group()` (L321) after a
bounded `join(5s)` (L315). This is the VRAM-release mechanism PRD §4.2bis mandates.

### (c) cmd_q commands: arm, disarm, text, abort, shutdown — ✅ COMPLIANT (abort-via-Event nuance)
- `set_microphone(on)` (**L230-235**) puts `("arm" if on else "disarm", {})` (**L233**).
- `text(on_final)` (**L250-271**) puts `("text", {})` (**L261**).
- `stop()` (**L272-329**) best-effort puts `("shutdown", {})` on a detached thread (**L307-310**).
- **abort is NOT primarily a cmd_q command** — it's the dedicated `abort_event` (mp.Event, L146).
  `abort()` (**L237-248**) sets `self._abort_event.set()` (**L246**); a SEPARATE child thread
  `_abort_handler` (**L517-531**) polls it and calls `recorder.abort()`. The child's command loop
  DOES handle `("abort", {})` as belt-and-suspenders (**L564-565**: `elif kind == "abort":
  recorder.abort()`). See nuance §4.1 — the mp.Event design is STRONGER than a plain cmd_q abort.

### (d) evt_q events: partial, final, vad_start, vad_stop, device, loaded, error — ✅ COMPLIANT (naming nuance)
The ACTUAL event vocabulary (module docstring L23-31; `_dispatch` L354-392) is RICHER and
slightly differently named than the item's shorthand. The mapping:
- "device" + "loaded" → **`("ready", {device,compute_type,final_model,realtime_model})`** (L499).
  This single event IS the "loaded successfully" signal AND carries the device dict. `ready` sets
  `self._ready_evt` (the spawn() load-completion gate).
- "error" → **`("error", {msg})`** (L479/L501); sets `_ready_evt` + `_error`.
- "final" → **`("final", {text})`** (L508 / `_run_text_and_emit_final` L677).
- "partial" → **`("partial", {text})`** (L733, realtime stabilized partial).
- "vad_start"/"vad_stop" → a SINGLE **`("vad", {phase})`** where phase ∈ {"listening","speaking"}
  (L731-733). on_vad_detect_start→"listening"; on_vad_start→"speaking"; on_vad_stop→"listening".
  So both vad_start and vad_stop collapse to one "vad" event keyed on a phase field.
- EXTRA events beyond the item's list: **`("speech", {})`** (on_speech → idle-auto-stop reset,
  L468), **`("speech_end", {})`** (on_vad_stop latency stamp, L755), **`("gone", {})`** (clean
  shutdown ack, L575 — `_read_loop` exits on it).
- `_dispatch` (L354-392) handles every kind; unknown kinds are WARN-logged + ignored (L391).
See nuance §4.2 — the actual vocabulary fully satisfies PRD §4.2bis's "partials/finals/VAD events
stream back to a daemon reader thread."

### (e) text(on_final) puts text cmd, waits for final event on evt_q — ✅ COMPLIANT
`RecorderHost.text()` (**L250-271**): sets `self._on_final = on_final` (L255), clears
`self._final_evt` (L256), puts `("text", {})` (L261), then BLOCKS on
`self._final_evt.wait(timeout=0.5)` in a loop (**L264-268**) that also checks child death
(`self._dead or not self._proc.is_alive()` → returns). The reader thread's `_dispatch` on
"final" (**L369-377**) invokes `self._on_final(text)` (L374) and sets `self._final_evt` (L377) →
unblocks `text()`. on_final runs on the READER thread (matches the prior in-process worker-thread
model). Dead-child: `_read_loop`'s finally (L351-353) sets `_dead=True` + `_final_evt.set()` →
`text()` returns promptly (test: `test_text_returns_promptly_if_child_already_dead`).

### (f) _RelayFeedback.update_partial/set_phase/set_models_loaded/record_final relay to daemon — ✅ COMPLIANT (no-op nuance)
`_RelayFeedback` (**L718-750**, child-local stand-in passed to `build_recorder`):
- `update_partial(text)` (**L732-733**) → relays `("partial", {text})`. ✅ RELAYED.
- `set_phase(phase)` (**L735-738**) → relays `("vad", {phase})` ONLY for "listening"/"speaking";
  lifecycle phases (unloaded/loading/idle) are NOT relayed (daemon-owned). ✅ RELAYED (VAD only).
- `set_models_loaded(loaded)` (**L740-741**) → `pass`. **INTENTIONAL NO-OP** — models_loaded is
  driven by the DAEMON's `_load_host`/`_unload_host` (the child doesn't own that transition). See
  nuance §4.3.
- `record_final(text)` (**L743-744**) → `pass`. **INTENTIONAL NO-OP** — driven by the daemon's
  `on_final` (which the "final" event triggers via `_dispatch`). 
- `set_listening(listening)` (**L746-747**) → `pass`. **INTENTIONAL NO-OP** — daemon-owned.
`_RelayLatency` (**L750-774**): `note_speech_end()` (L767-768) → relays `("speech_end", {})`;
`note_partial` (L764-765) is a no-op (the daemon's reader calls the real one on the "partial"
event); `finalize_utterance`/`snapshot` are no-ops (daemon-driven).
See nuance §4.3 — the relay covers ONLY the events the CHILD uniquely observes (partial, VAD,
speech_end); daemon-owned transitions (models_loaded, listening, lifecycle phase, record_final,
finalize) are correctly no-ops.

## 3. Test evidence (the contract's run target)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py \
    -q -k 'host or relay or queue or ipc or worker'
```
**Result (re-ran live): 30 passed, 189 deselected in 1.65s.** Key tests per property:
- (a) spawn: `test_spawn_ready_seeds_device_via_dispatch`, `test_spawn_error_sets_error_via_dispatch`.
- (b) setsid/killpg teardown: `test_concurrent_stop_calls_share_one_teardown`, `test_stop_is_noop_when_no_process`,
  `test_stop_with_dead_process_is_noop`.
- (c) cmd_q: `test_set_microphone_puts_arm_or_disarm_command`, `test_abort_sets_abort_event`,
  `test_text_blocks_until_final_event_then_returns`.
- (d) evt_q: `test_dispatch_partial_calls_on_partial`, `test_dispatch_speech_calls_on_speech`,
  `test_dispatch_speech_end_stamps_latency`, `test_dispatch_vad_drives_feedback_phase`,
  `test_dispatch_final_calls_on_final_and_sets_final_event`, `test_dispatch_ready_seeds_device_and_sets_ready_event`,
  `test_dispatch_error_sets_error_and_ready_event`, `test_dispatch_unknown_event_is_ignored`,
  `test_read_loop_drains_events_until_gone`, `test_read_loop_eof_marks_dead_and_unblocks_waiters`.
- (e) text waits for final: `test_text_blocks_until_final_event_then_returns`,
  `test_text_returns_promptly_if_child_already_dead`, `test_abort_sentinel_unblocks_blocked_host_text`.
- (f) relay + VT-007 sentinel: `test_run_text_emits_sentinel_final_on_abort_path`,
  `test_run_text_does_not_double_emit_on_normal_path`,
  `test_run_text_emits_sentinel_when_abort_flag_set_even_if_return_is_none`,
  `test_run_text_no_sentinel_on_normal_path_when_abort_flag_unset`.
Mocked CUDA (no model load) → fast (~1.7s). The `timeout 300` inner + bash-tool outer wrap are
mandatory (AGENTS.md Rule 1).

## 4. Non-defect nuances (record so they are NOT mistaken for gaps)

### 4.1 abort is a dedicated mp.Event, not (primarily) a cmd_q command
The child's command loop BLOCKS in `recorder.text()` while listening, so a `("abort", {})` command
queued on cmd_q would NOT be read until `text()` returns (too late). The dedicated `abort_event`
(mp.Event) is polled by a SEPARATE child thread (`_abort_handler` L517-531) that calls
`recorder.abort()` the instant it is set — this is how stop()/toggle(off)/auto-stop interrupt a
blocked text(). `("abort", {})` IS still handled on cmd_q (L564-565) as belt-and-suspenders. The
item listing "abort" among cmd_q commands is TECHNICALLY satisfied (belt-and-suspenders) but the
PRIMARY path is the Event — a STRONGER design, not a defect.

### 4.2 the evt_q vocabulary is richer than the item's shorthand
The item lists "partial, final, vad_start, vad_stop, device, loaded, error". Actual: "ready"
(combines device + loaded), "vad"{phase} (combines vad_start + vad_stop), plus extras "speech",
"speech_end", "gone". PRD §4.2bis only requires "partials/finals/VAD events stream back to a daemon
reader thread" — the actual vocabulary fully satisfies this (and adds latency/speech/shutdown-ack
signals the PRD's lifecycle + latency logging needs). Naming drift, not a defect.

### 4.3 _RelayFeedback.set_models_loaded/record_final/set_listening are INTENTIONAL no-ops
The child does NOT own the models_loaded / listening / lifecycle-phase / record_final / finalize
transitions — those live in the DAEMON (which has the real Feedback/LatencyLog objects). The relay
stand-ins only relay what the CHILD uniquely observes: partials (realtime transcription) + VAD phase
+ speech_end. Everything else is correctly a no-op so the daemon remains the single source of truth
for lifecycle state. This is the RIGHT design (the child can't drive daemon-owned transitions), not
a missing relay.

### 4.4 VT-007 abort-sentinel (the unblock guarantee)
`_run_text_and_emit_final` (L630-677) GUARANTEES a `("final", {text:""})` event on the abort path
(else `host.text()` blocks forever after a stop/toggle-off/auto-stop, wedging run()). The empty
text is handled safely by the daemon (the on_final gate + textproc.clean('') reject it → nothing
typed). Detected via TWO independent signals (the `aborted` Event WE control + the legacy non-None
return marker) so it survives RealtimeSTT API drift. Guarded by 4 unit tests. This is a critical IPC
robustness detail that EXCEEDS the item's shorthand — record it so a maintainer doesn't "simplify"
it away.

### 4.5 the "vad" event is gated by an is_listening predicate (Issue 2 residual)
`_dispatch` "vad" branch (L380-388): if the daemon provided `is_listening` and the daemon is NOT
listening, the stray VAD event (a late on_vad racing a disarm) is DROPPED so phase doesn't flip to
listening/speaking while listening: off. Owned by P1.M2.T1 (phase lifecycle); recorded here because
it lives on the IPC dispatch path.

## 5. Verdict + scope boundary

**✅ COMPLIANT** — all 6 item properties (a)-(f) pass (file:line in §2); the IPC vocabulary is
richer/safer than the item's shorthand (nuances §4.1-4.4) but fully satisfies PRD §4.2bis's
recorder-host-subprocess model (arm/disarm/text/abort/shutdown proxied; partials/finals/VAD streamed
back; setsid+killpg for VRAM release). **No source/test files need modification.**

SCOPE: this audit owns the IPC MECHANISM (queues, commands, events, relay, the abort Event, the
VT-007 sentinel) ONLY. It is DISJOINT from:
- S1 (P1.M2.T2.S1) — the lazy-load STATE MACHINE (§1 of gap_lifecycle.md; this is §2).
- S3 (P1.M2.T2.S3) — the BOUNDED TEARDOWN detail (join(5s)+killpg timing, idle-unload watchdog).
- P1.M2.T1 — phase lifecycle (the vad is_listening gate's home).
- M2.T3 — lite/mode-switch.
- M3 — status reporting (VT-001/VT-002).

## 6. The append convention (where the report goes)

`gap_lifecycle.md` is the shared report file for P1.M2.T2. S1 (parallel) writes §1 (the lazy-load
audit) and creates the file; **S2 (THIS task) APPENDS a `# §2 — Recorder-Host IPC (P1.M2.T2.S2)`
section** — mirroring how P1.M2.T1.S2 appended `# §2 — Graceful Drain` to `gap_daemon_loop.md`
(that file's L156+ is the template). If `gap_lifecycle.md` does not yet exist when S2 runs (S1
parallel, not yet landed), S2 CREATES it with the §2 IPC section as its initial content (a
self-contained report); S1's §1 is produced in parallel and merged/prepended. The §2 heading makes
the two sections compose without conflict.