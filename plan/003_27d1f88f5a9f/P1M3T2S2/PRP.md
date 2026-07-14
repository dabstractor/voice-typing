# PRP — P1.M3.T2.S2 (RE-PLAN, attempt 2): subprocess recorder host so the daemon PID reaches ~0 VRAM on idle-unload; rewrite T6 + confirm T4

> **STATUS: RE-PLAN.** Attempt 1 scoped this item as **test-only** and (correctly) refused to weaken
> the T6(d-gone) assertion; T6(d-gone) then **deterministically failed** because the idle-unload path
> leaves a **258 MiB CUDA context resident on the daemon PID**, violating PRD §7.9 + §6 T6(d). Root-
> cause analysis (`research/residual_cuda_context_rootcause.md`) **falsifies attempt 1's premise**
> (that spawn-worker termination releases all VRAM): RealtimeSTT v1.0.2 loads the **realtime model
> in-process** (a `threading.Thread`), so the daemon process itself holds an **unreleasable CUDA
> primary context** until it exits. The feedback explicitly says **fix the production path, do not
> weaken the test.** Therefore this PRP **expands scope** to the only fix that can satisfy the strict
> PRD contract: **host the entire `AudioToTextRecorder` in a managed child subprocess** so the daemon
> process never touches CUDA. The 4-part T6 test then passes naturally and stays strict.

---

## Goal

**Feature Goal:** Make `voice_typing`'s idle-unload actually release **all** GPU VRAM (the daemon PID
disappears from `nvidia-smi` to ~0 MiB while the daemon keeps running), by moving the entire
RealtimeSTT `AudioToTextRecorder` into a managed child subprocess that the daemon spawns on first arm
and terminates on idle-unload/quit. Then keep the **strict 4-part** T6 lifecycle test
(`tests/test_idle_and_gpu.sh`) — which now passes — and confirm T4 still holds.

**Deliverable:**
1. **NEW `voice_typing/recorder_host.py`** — a `RecorderHost` class that owns a spawn-started child
   process running the `AudioToTextRecorder`, with a minimal IPC layer (commands arm/disarm/abort/
   text/shutdown; events partial/final/speech/ready/error/device). Terminating the child releases
   **all** VRAM (daemon process never touches CUDA).
2. **MODIFY `voice_typing/daemon.py`** — replace the in-process recorder (`self._recorder` direct
   construction/calls) with `self._host: RecorderHost`. Lazy-load becomes single-flight **spawn**;
   idle-unload / `_bounded_shutdown` becomes **terminate the child process** (bounded + complete).
   Preserve the `recorder=`/`host_factory=` test seam so `tests/test_daemon.py` stays hermetic.
3. **REWRITE `tests/test_idle_and_gpu.sh` T6** — the strict 4-part lifecycle (a/b/c/d + d-reload);
   **unchanged from attempt 1** (it was correct) but now PASSES because the production path is fixed.
4. **UPDATE `tests/ACCEPTANCE.md`** — remove the "KNOWN PRODUCTION BUG" block; record the real ~0
   post-unload numbers.

**Success Definition:**
- `./tests/test_idle_and_gpu.sh` exits **0**, printing `[PASS] T6 (d) … ~0 VRAM reclaimed` with a
  real `nvidia-smi` total of **0** on the daemon tree after idle-unload (RUN 2).
- `uv run pytest tests/test_daemon.py -v` green (lifecycle/single-flight/load-failure/idle-unload
  tests, now driven through a fake `RecorderHost` — CUDA-free + fast).
- `uv run pytest tests/test_feed_audio.py -v` green (T1 latency regression — proves the IPC hop did
  not break partial cadence / final latency).
- `./tests/e2e_virtual_mic.sh` green (T3 — proves the host still drives typing end-to-end).
- `uv run ruff check voice_typing tests && uv run mypy voice_typing` clean.

---

## Why

- **PRD §7.9 + §6 T6(d) are unachievable in-process.** The feedback's measured 2804→258 MiB drop
  proves the *models* unload (~91% reclaimed) but a ~258 MiB CUDA primary context stays on the daemon
  PID. This is a **hard CUDA constraint**: once a process initializes the CUDA runtime (here, when
  RealtimeSTT constructs the realtime `small.en` model in the daemon's `realtime_thread`), the context
  persists until process exit. `del`+`gc.collect()`+`torch.cuda.empty_cache()`+force-terminating
  `transcript_process`/`reader_process` **cannot** release it. (See
  `research/residual_cuda_context_rootcause.md` §2-3, with verbatim RealtimeSTT source citations.)
- **The feedback mandates fixing the production path, not weakening the test.** Attempt 1 correctly
  refused to weaken T6(d-gone); the only way to keep that strict assertion AND make the test pass is
  to fix the production path so the daemon process holds **no** CUDA context.
- **The architecturally correct fix is process isolation.** Move the entire recorder (final model +
  realtime model + VAD + cuda_check) into a child subprocess. Then the daemon PID never appears on
  `nvidia-smi` for CUDA; idle-unload = kill the child → truly ~0 VRAM; re-arm = respawn → reload.
- **Integration with existing features:** this *replaces* the in-process lazy-load (P1.M2.T1) +
  in-process idle-unload teardown (P1.M3.T1.S1) + `_bounded_shutdown` (P1.M1.T1.S2) with a cleaner,
  process-level equivalent. It preserves every external behavior (voicectl commands, status/phase/
  models_loaded, latency logging, CPU fallback) — only the *internal* recorder ownership changes.

## What

**User-visible behavior:** unchanged. `voicectl toggle/start/stop/status/quit` behave identically;
`status` still reports `phase: unloaded/loading/idle/listening` + `models: … (loaded|not loaded)`;
first arm still pays a ~1–3 s load (now a subprocess spawn + model load); later arms are instant
(child stays resident); idle-unload still logs `voice-typing idle-unload: …s disarmed; unloading
models` and transitions to `unloaded`.

**New internal behavior (the fix):**
- The daemon process NEVER imports `RealtimeSTT`/`torch`/`ctranslate2` and NEVER creates a CUDA
  context. All of that lives in the child subprocess.
- First arm → `_spawn_host()` (single-flight) starts the child; the child constructs the recorder
  (cuda_check + both models) and signals `ready` (or `error` → CPU-fallback retry inside the child).
- `text()` / partials / on_speech cross a `multiprocessing` queue from child → daemon.
- Idle-unload / quit → `_stop_host()` sends `shutdown` (graceful), waits bounded (~5 s), then
  `SIGTERM`→`SIGKILL` the child **process group** → all VRAM released, daemon PID off `nvidia-smi`.

### Success Criteria

- [ ] **T6(d-gone) PASSES strictly:** after `auto_unload_idle_seconds` disarmed idle, the daemon tree
  is **ABSENT** from `nvidia-smi` (total **0** MiB) while the daemon process stays alive.
- [ ] T6(a) boot-absent, T6(b) armed-present [1024,5120] MiB, T6(c) disarmed-still-present, T6(d-
  reload) re-arm-present all PASS.
- [ ] T4 (120 s silence, default 1800 s) still green: no finals, no crash, CPU < 25% of one core.
- [ ] `tests/test_daemon.py` lifecycle/single-flight/load-failure/idle-unload tests green via a fake
  `RecorderHost` (CUDA-free).
- [ ] `tests/test_feed_audio.py` (T1) partial cadence ≤ 300 ms + final ≤ 1.5 s — **no latency
  regression** from the IPC hop.
- [ ] `tests/e2e_virtual_mic.sh` (T3) green — typing still reaches the tmux pane end-to-end.
- [ ] ruff + mypy clean; `bash -n` + shellcheck clean on the test.

---

## All Needed Context

### Context Completeness Check

Someone who knows nothing about this codebase can implement this because the PRP gives: (a) the exact
root cause with verbatim RealtimeSTT source citations; (b) the complete recorder call-surface to
proxy; (c) the test seam to preserve; (d) the lifecycle/feedback/status surfaces to keep working; (e)
project-specific validation commands. Read `research/residual_cuda_context_rootcause.md` FIRST.

### Documentation & References

```yaml
# MUST READ FIRST — the root cause (attempt 1's premise is FALSIFIED here)
- docfile: plan/003_27d1f88f5a9f/P1M3T2S2/research/residual_cuda_context_rootcause.md
  why: Pins WHY in-process VRAM release is impossible + the only viable fix (subprocess host).
  critical: §2 (which entity holds the daemon's CUDA context — realtime_thread/model), §3 (CUDA
    primary context is unreleasable without process exit), §6 (the recorder call-surface to proxy).

# The FAILED premise attempt 1 copied — read it to know what NOT to assume
- docfile: plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md
  why: §2's "spawn → each mp.Process has its own CUDA context" is true ONLY for transcript_process
    + reader_process; it does NOT cover the realtime model (a thread). Do not re-extrapolate it.
  gotcha: The doc never examined where realtime_transcription_model / silero VAD live.

# RealtimeSTT v1.0.2 INSTALLED source — the ground truth for the child-side recorder
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py
  why: §process model. transcript_process (:397) + reader_process (:433) are mp.Process(spawn);
    realtime_thread (:621-626) is a THREAD; realtime_transcription_model built in-process (:447-490,
    create_transcription_engine at :466). This is WHY the daemon holds a context.
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/shutdown.py
  why: shutdown_recorder() is what recorder.shutdown() calls — the ~90s wedge (unbounded
    recording_thread.join() :33 + realtime_thread.join() :62) the host must NOT reproduce by
    blocking the daemon on it. The host bounds it by terminating the child PROCESS (§Implementation).
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/audio_recorder.py
  why: AudioToTextRecorder.__init__ signature (the 85-param ctor that _filter_kwargs_to_signature
    feeds). The child constructs it exactly as build_recorder() does today (unchanged).

# The production code to MODIFY
- file: voice_typing/daemon.py
  why: THE call sites to convert to IPC. See §6 of the research note (the 7 self._recorder.* sites).
  pattern: lazy load _load_recorder() (:495-578), _unload_recorder() (:838-873), _bounded_shutdown()
    (:1085-1140), run() loop (:581-636 incl. recorder.text(self.on_final) at :631), _arm/_disarm
    (:699-707, :948-958), abort/_safe_abort. status/phase via self._feedback (set_phase/set_models_
    loaded) — KEEP these surfaces unchanged.
- file: voice_typing/daemon.py   # build_recorder / _construct / cfg_to_kwargs (UNCHANGED interface)
  why: Lines 124-300 — the production child-side recorder construction. Move it INSIDE the child
    worker unchanged; _construct stays the testable core (test_daemon.py tests it with a fake class).
- file: voice_typing/cuda_check.py
  why: resolve_device_and_models() probes CUDA via ctranslate2.get_cuda_device_count(). Today this
    runs in the DAEMON (during build_recorder) — another daemon-side CUDA touch. Moving build_recorder
    into the child moves this probe into the child too (daemon stays CUDA-clean).
- file: voice_typing/ctl.py
  why: voicectl status rendering (:85-92) — phase/models_loaded/listening lines. KEEP the surface;
    the host must still drive feedback.set_phase/set_models_loaded so status is unchanged.
- file: voice_typing/feedback.py
  why: set_phase / set_models_loaded / update_partial / state.json — the host's events feed these
    exactly as the in-process callbacks do today. No feedback changes needed.

# The tests to WRITE / PRESERVE / RE-RUN
- file: tests/test_idle_and_gpu.sh
  why: THE deliverable test (T6 4-part + T4). Attempt 1's structure is CORRECT — keep it; it now
    passes. See Implementation Task 5.
- file: tests/test_daemon.py
  why: The fast pytest (lifecycle/single-flight/load-failure/idle-unload) — MUST stay green + CUDA-
    free. Injection seam _make_daemon(recorder=...) (:427-432) → extend to recorder_host= / host_-
    factory=. _FakeRecorder/_StubRecorder/_RaisingRecorder/_FakeSlowRecorder become fake hosts.
- file: tests/test_feed_audio.py
  why: T1 latency regression gate. It calls recorder.feed_audio() — decide: (a) keep feeding the
    REAL recorder in-process in a test-only mode (feed_audio is an offline path), OR (b) feed via the
    host. SIMPLEST: feed_audio() drives the recorder WITHOUT the mic/typing loop, so keep it pointing
    at a real AudioToTextRecorder built in-process (test-only) — it does NOT exercise idle-unload, so
    the daemon-CUDA-clean invariant is irrelevant to it. Verify T1 still meets latency targets.
- file: tests/ACCEPTANCE.md
  why: Remove the "KNOWN PRODUCTION BUG" block (lines ~17-18, 30, 55, 77-93, 107-109); record the
    real ~0 post-unload numbers once the host lands.

# Process-isolation references (multiprocessing spawn + process-group teardown)
- url: https://docs.python.org/3/library/multiprocessing.html#multiprocessing.Process
  why: Process.start/terminate/join + the spawn start method (RealtimeSTT already sets spawn). The
    child is started with start_method 'spawn' (its own CUDA context — the whole point).
  critical: terminate() sends SIGTERM; on the ~90s RealtimeSTT shutdown wedge, SIGTERM may not be
    enough → use a process GROUP (os.setsid in the child) + os.killpg(SIGKILL) to guarantee the child
    + its OWN spawn-grandchildren (transcript_process/reader_process) die and release VRAM.
- url: https://docs.python.org/3/library/multiprocessing.html#pipes-and-queues
  why: mp.Queue / mp.Pipe for the command/event channels. Queue.put serializes strings/dicts (fine).
  gotcha: a Queue feeder thread + a worker blocked on recorder.text() — on child terminate, the
    queue's background feeder thread is a daemon thread and dies with the child; the daemon reader
    gets EOFError/BrokenPipeError — handle as "child gone" (idempotent, never re-raise).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # THE file to modify (recorder ownership → host ownership)
├── cuda_check.py        # resolve_device_and_models() — moves into the child at runtime
├── ctl.py               # voicectl status rendering — KEEP surface (no change)
├── feedback.py          # set_phase/set_models_loaded/update_partial — KEEP (no change)
├── config.py            # AsrConfig.auto_unload_idle_seconds (:60) — KEEP (no change)
├── launch_daemon.sh     # exports LD_LIBRARY_PATH/HF_HUB_OFFLINE — KEEP (child inherits via spawn env)
├── typing_backends.py   # tmux/wtype/ydotool — KEEP (daemon-side; unaffected)
└── textproc.py          # text filter — KEEP (daemon-side; unaffected)
tests/
├── test_idle_and_gpu.sh # REWRITE T6 (4-part) + confirm T4 — attempt 1's structure is correct
├── test_daemon.py       # ADAPT injection seam to recorder_host=/host_factory=
├── test_feed_audio.py   # T1 latency regression gate (re-run; likely no change)
├── e2e_virtual_mic.sh   # T3 regression gate (re-run; likely no change)
└── ACCEPTANCE.md        # REMOVE the "KNOWN PRODUCTION BUG" block; record ~0 post-unload
systemd/voice-typing.service  # TimeoutStopSec=15 already set (M1.T2.S1) — KEEP
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/
├── recorder_host.py     # NEW — RecorderHost (child-process owner + IPC) + _worker_main entrypoint
├── daemon.py            # MODIFIED — self._host replaces self._recorder; lazy-load→spawn; unload→terminate
└── (all others unchanged)
tests/
├── test_recorder_host.py # NEW (optional but recommended) — unit tests for the host IPC (fake child)
├── test_idle_and_gpu.sh  # REWRITTEN T6 (4-part) — attempt 1's version, now PASSING
├── test_daemon.py        # ADAPTED — fake RecorderHost seam
└── ACCEPTANCE.md         # UPDATED — remove KNOWN-BUG block; record ~0
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL — CUDA primary context is PER-PROCESS and unreleasable.
# Once ANY code in a process constructs a faster-whisper/ctranslate2 model (or otherwise inits the
# CUDA runtime), that process holds a ~100-300 MiB context until it EXITS. del/gc/empty_cache do NOT
# release it. This is WHY the recorder MUST live in a child process (not a thread) for idle-unload to
# reach ~0 on the daemon PID. (research/residual_cuda_context_rootcause.md §3.)

# CRITICAL — RealtimeSTT's shutdown can wedge ~90s (the original quit hang).
# core/shutdown.py recording_thread.join() (:33) + realtime_thread.join() (:62) are UNBOUNDED. The
# host MUST NOT block the daemon on recorder.shutdown(); it bounds teardown by TERMINATING THE CHILD
# PROCESS GROUP (os.killpg), which releases VRAM immediately and cannot wedge the daemon. This
# supersedes the in-process _bounded_shutdown timeout thread (P1.M1.T1.S2) — killing the process is
# strictly stronger + simpler.

# CRITICAL — the child spawns ITS OWN grandchildren (transcript_process/reader_process).
# RealtimeSTT uses mp.set_start_method("spawn") internally, so the host's child will spawn
# transcript_process + reader_process as GRANDCHILDREN of the daemon. daemon_tree_pids() walks the
# full descendant tree, so T6's tree-match still works. On teardown, kill the child's PROCESS GROUP
# (os.setsid() in the child + os.killpg(os.getpgid(child), SIGKILL)) so grandchildren die too —
# otherwise they orphan and hold VRAM (the EXACT bug attempt 1 hit, now at the grandchild level).

# CRITICAL — the daemon's run() loop blocks on recorder.text(self.on_final) (daemon.py:631).
# In the host model the child blocks on recorder.text(); the daemon's text() proxy must block on the
# child's 'final' event (a threading.Event set by the host's reader thread) then call self.on_final.
# Partials arrive async via the realtime callback → child sends 'partial' → host reader thread →
# feedback.update_partial. DO NOT poll the event queue from the main text()-blocking loop only, or
# partials stall until the next final.

# GOTCHA — mp.Queue/Pipe raise BrokenPipeError/EOFError when the child dies.
# The host's reader thread must treat those as "child gone" (idempotent, log at INFO, never re-raise).
# The daemon's text() proxy returns (no final) if the child died mid-utterance.

# GOTCHA — spawn children do NOT inherit the daemon's working set the same way fork does.
# build_recorder() lazy-imports RealtimeSTT inside the CHILD — fine (the child is a fresh python that
# imports it). cuda_check + the LD_LIBRARY_PATH cuDNN libs MUST reach the child: launch_daemon.sh
# exports LD_LIBRARY_PATH in the daemon's env; mp.spawn inherits the parent env by default, so the
# child gets it. VERIFY this (the host's 'device' event must report cuda; if it reports cpu-fallback,
# the child lost LD_LIBRARY_PATH → set it explicitly on the child's env / preexec).

# GOTCHA — feed_audio (T1) is an OFFLINE path; it does NOT go through the host.
# tests/test_feed_audio.py builds a real AudioToTextRecorder with use_microphone=False and feeds WAV
# chunks directly. Keep that test in-process (it does not exercise idle-unload, so the daemon-CUDA-
# clean invariant does not apply to it). Do NOT route feed_audio through the host.

# GOTCHA — the auto-stop-aware stop + voicectl timeout wrapper from attempt 1 are STILL NEEDED.
# The pre-existing control-lock wedge (daemon.py _disarm() docstring) and voicectl's no-timeout
# readline() are unrelated to this fix. KEEP attempt 1's `voicectl()` timeout wrapper + the auto-stop-
# aware stop skip in the test (they are documented in-code in test_idle_and_gpu.sh).
```

---

## Implementation Blueprint

### Data models / IPC protocol (the host's wire format)

```python
# voice_typing/recorder_host.py — IPC is two channels: cmd (daemon→child) + events (child→daemon).
# Keep it dumb, serializable, typed. No pydantic needed (stdlib dataclasses / tuples).

# Commands the daemon sends to the child (put on cmd_queue):
Cmd = tuple[str, dict]      # ("arm", {}) | ("disarm", {}) | ("abort", {}) | ("text", {}) | ("shutdown", {})

# Events the child sends to the daemon (put on event_queue):
#   ("ready",   {"device": "cuda", "compute_type": "float16", "final_model": "...", "realtime_model": "..."})
#   ("error",   {"msg": "CUDA load failed: ..."})          # child could not construct the recorder
#   ("final",   {"text": "...", "ts_speech_end": 12.34, "ts_ready": 12.35})  # from recorder.text() callback
#   ("partial", {"text": "..."})                           # from the realtime stabilized callback
#   ("speech",  {})                                        # on_speech → daemon._touch_speech (resets idle auto-stop)
#   ("gone",    {})                                        # child is shutting down cleanly (ack of shutdown cmd)

# Latency: the child stamps ts_speech_end/ts_ready (time.monotonic()) exactly as on_vad_stop/on_final
# do today, so LatencyLog (daemon.py LatencyLog) is fed identically. The queue hop adds <1 ms.
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/recorder_host.py (the child-process owner + IPC)
  - IMPLEMENT class RecorderHost with the SAME public surface the daemon uses today:
      __init__(cfg, feedback, latency, on_final, on_partial, on_speech)  # stores refs; does NOT spawn
      spawn() -> bool            # single-flight; starts the child (mp.Process, start_method 'spawn');
                                  # child runs _worker_main; waits for 'ready'/'error'; True iff ready
      set_microphone(on: bool)   # put ('arm' if on else 'disarm', {}) on cmd_queue
      abort()                    # put ('abort', {})  (best-effort; never blocks — see _safe_abort)
      text(on_final)             # put ('text', {}); block on self._final_event; call on_final; return
      stop(timeout=5.0)          # put ('shutdown', {}); wait bounded; then SIGTERM/SIGKILL the child
                                  # PROCESS GROUP (os.killpg) so grandchildren die; idempotent
      poll_events()              # drain event_queue non-blocking; dispatch partial/speech to callbacks
                                  # (called by a daemon reader THREAD started in spawn(), NOT the main loop)
      is_alive / pid / device    # introspection for status/logging
  - IMPLEMENT module-level _worker_main(cfg_dict, cmd_queue, event_queue, feedback_state_dir, latency_config):
      - os.setsid() so the child is its own session/group leader (enables killpg teardown).
      - construct the recorder via build_recorder(cfg, ...) (UNCHANGED — same path as today, now in
        the child). Wire on_final→put('final'), realtime partial→put('partial'), on_speech→put('speech').
      - on success put ('ready', {device, compute_type, final_model, realtime_model}); on failure put
        ('error', {msg}) then exit non-zero (the daemon's spawn() retries once with force_cpu=True,
        mirroring _load_recorder's CPU-fallback — OR do the retry INSIDE the child; pick ONE and
        document it; child-side retry is cleaner because only the child touches CUDA).
      - main loop: read cmd_queue; on 'text' call recorder.text(child_on_final) (BLOCKS until a
        final, which puts 'final' then returns); on 'arm'/'disarm' call set_microphone; on 'abort'
        call recorder.abort(); on 'shutdown' call recorder.shutdown() (best-effort, the daemon will
        SIGKILL the group anyway), put 'gone', exit 0.
  - FOLLOW pattern: the IPC discipline mirrors voice_typing/ctl.py's ControlServer (request/response
    over a socket) but over mp.Queue — same "never block the responder" + "idempotent teardown" ideas.
  - GOTCHA: the reader thread (drains event_queue → on_partial/on_speech) MUST be daemon=True so it
    never blocks daemon shutdown. BrokenPipeError/EOFError → log + exit the reader thread cleanly.
  - GOTCHA: text() must release self._final_event AFTER calling on_final is queued, OR call on_final
    from the READER thread (cleaner: reader thread calls on_final for 'final' events; the main-loop
    text() proxy just blocks on the event then returns). CHOOSE the reader-thread-dispatches-finals
    design so the main loop's text() is a trivial wait — matches how on_final runs today (a worker
    thread, not the text() caller).
  - NAMING: RecorderHost (CamelCase class); _worker_main (module fn); cmd_queue/event_queue (fields).
  - PLACEMENT: voice_typing/recorder_host.py.

Task 2: MODIFY voice_typing/daemon.py — host replaces in-process recorder
  - REPLACE self._recorder (AudioToTextRecorder | None) with self._host (RecorderHost | None).
  - REWRITE _load_recorder() (:495-578) → _load_host(): single-flight spawn of self._host; on
    'ready' set phase 'idle' + models_loaded True + seed _resolved_device_cache from the 'ready'
    device dict (replaces _log_resolved_device's in-process cuda_check probe); on 'error' retry once
    with force_cpu=True (inside the child) else phase 'unloaded' + _load_error (NO half-built host).
  - REWRITE _unload_recorder() (:838-873) → _unload_host(): under _lock re-check the unload condition
    (unchanged logic), then self._host.stop(timeout=5.0) (terminates the child GROUP — releases ALL
    VRAM), self._host=None, models_loaded False, phase 'unloaded'. This is the line that makes
    T6(d-gone) pass: killing the child drops the daemon tree off nvidia-smi.
  - REPLACE _bounded_shutdown() (:1085-1140): the host's stop() IS the bounded teardown (process
    terminate + killpg). DELETE the transcript_process/reader_process force-terminate loop (the
    grandchildren die with the child group). Keep shutdown() (:1141+) delegating to _unload_host.
  - ADAPT run() loop (:581-636): `if self._host is None: idle/sleep; continue` else `self._host.text
    (self.on_final)` (the proxy blocks on the child's 'final' event, then on_final runs on the host's
    reader thread). set_microphone calls (:606,:724,:749) → self._host.set_microphone(...). abort
    (:958) → self._host.abort(). The realtime partial/speech dispatch is now the host's reader thread
    calling self.on_partial/self._touch_speech (set in __init__) — REMOVE the in-process _build_
    callbacks realtime wiring from the daemon path (build_recorder still wires it, but inside the child).
  - PRESERVE: every self._feedback.set_phase/set_models_loaded call (status surface unchanged);
    LatencyLog feeding (the child stamps ts_*; the host reader thread calls latency.finalize_utterance
    exactly as on_final does today); _safe_abort's _text_in_flight gate (the proxy text() must set/
    clear it identically so abort() never blocks); the CPU-fallback _resolved_device_cache seeding.
  - PRESERVE the test seam: __init__ keeps recorder=None BUT now ALSO accepts recorder_host=None
    (a pre-built/fake host) + host_factory=None (callable → host). When recorder_host is given, skip
    _load_host (already loaded) — mirrors today's `recorder is not None → already loaded`. When
    host_factory is given, _load_host calls it (tests inject a fake). DEFAULT host_factory = RecorderHost.
  - FOLLOW pattern: the single-flight Condition(_lock) discipline of _load_recorder (:502-520) is
    PRESERVED verbatim — only "build_recorder" → "host.spawn()" changes.
  - GOTCHA: do NOT import RealtimeSTT/torch/ctranslate2 at daemon module top level (the lazy import
    inside build_recorder already keeps import voice_typing.daemon cheap + CUDA-free — VERIFY the
    daemon process no longer imports them at all; recorder_host.py imports RecorderHost but NOT the
    recorder, which is only imported inside _worker_main in the child).

Task 3: ADAPT tests/test_daemon.py — fake RecorderHost seam (keep it CUDA-free + fast)
  - RENAME/ADD fakes: _FakeRecorder → _FakeHost (same surface: set_microphone/abort/text/stop/poll_
    events/is_alive); _StubRecorder → _StubHost; _RaisingRecorder → _RaisingHost (spawn() returns
    False / stop raises); _FakeSlowRecorder → _FakeSlowHost (text() blocks then completes).
  - CHANGE _make_daemon(*, recorder=None, …) (:427-432) → _make_daemon(*, recorder_host=None,
    host_factory=None, …); pass host_factory=lambda: recorder_host to VoiceTypingDaemon.
  - ADAPT the lifecycle/single-flight/load-failure/idle-unload tests (P1.M3.T2.S1 added them) to the
    host seam: a "load" is now host.spawn(); an "unload" is host.stop(); single-flight = a second
    spawn() while one is in-flight returns the first's result. The ASSERTIONS are unchanged (phase
    transitions, models_loaded, no half-built state, idle-unload fire/reset/disable) — only the
    driver fakes change.
  - KEEP test_construct_passes_filtered_kwargs / test_build_recorder_is_callable (build_recorder +
    _construct are unchanged) green.
  - COVERAGE: spawn happy path, spawn failure → unload, single-flight (2 concurrent spawns → 1
    child), idle-unload fires after threshold, idle-unload disabled (threshold<=0), arm racing unload
    (waits then spawns fresh), stop is idempotent, stop kills the group (fake asserts killpg called).
  - NAMING: test_host_{scenario}; fakes _FakeHost/_StubHost/_RaisingHost/_FakeSlowHost.

Task 4 (OPTIONAL but recommended): CREATE tests/test_recorder_host.py — host IPC unit tests
  - IMPLEMENT: a fake child (a mp.Process or an in-process stand-in) that consumes cmd_queue + emits
    canned events; assert the host dispatches partial/final/speech correctly, text() blocks-unblocks,
    stop() terminates the group, BrokenPipeError is swallowed.
  - FOLLOW pattern: tests/test_daemon.py's hermetic style (no CUDA, no RealtimeSTT import).

Task 5: REWRITE tests/test_idle_and_gpu.sh T6 (4-part) — KEEP attempt 1's structure (it was correct)
  - The test from attempt 1 is ALREADY correct and needs NO logic change to PASS once Task 2 lands:
    it asserts the strict 4-part lifecycle via real nvidia-smi. RE-VERIFY it end-to-end; the ONLY
    expected change is the RESULT: T6(d-gone) now prints [PASS] with total=0.
  - KEEP: the 2-run structure (RUN 1 default 1800s for T6 a/b/c + T4; RUN 2 5s override for T6 d +
    d-reload); POLL-based helpers (vram_tree_state/assert_vram_absent/assert_vram_present/wait_vram_
    absent/wait_vram_present); launch_daemon_run/wait_daemon_ready/stop_daemon_run; the auto-stop-
    aware stop skip + the voicectl() timeout wrapper (both still needed — see GOTCHA).
  - VERIFY the header comment still documents the 4-part lifecycle accurately; if it mentions the
    "production bug / do-not-weaken" note, UPDATE it to "FIXED via subprocess recorder host (P1.M3.
    T2.S2 re-plan) — the daemon process holds no CUDA context; idle-unload terminates the host child
    so the daemon tree drops to ~0 MiB on nvidia-smi."
  - THE HARD ASSERTION (unchanged, now passing): after the 5s idle-unload on RUN 2, wait_vram_absent
    (ceiling 25s) then assert_vram_absent → total MUST be 0 (daemon tree ABSENT). Do NOT weaken.

Task 6: UPDATE tests/ACCEPTANCE.md — remove the KNOWN-BUG block; record ~0
  - REMOVE: the "KNOWN PRODUCTION BUG — T6(d-gone) FAILS" block (lines ~17-18, 30, 55, 77-93, 107-
    109) and the criterion-1 "partial — T6(d) FAIL" → restore to "PASS".
  - RECORD: the real post-fix numbers from a fresh run (T6(d) after idle-unload = 0; d-reload present
    again). Update the per-criterion rows (1/5/6/8/9) + the T6 explanatory paragraph to reflect the
    subprocess-host fix (daemon process CUDA-free; idle-unload = terminate host child).
  - KEEP: the comma-safe nvidia-smi query note, the tree-filter note, the 2-run note, the unrelated-
    apps note (all still true).
```

### Implementation Patterns & Key Details

```python
# === voice_typing/recorder_host.py — the child owner (sketch; fill per Task 1) ===
import multiprocessing as mp, os, signal, threading, time
from typing import Any, Callable

class RecorderHost:
    """Owns the AudioToTextRecorder in a spawn child; IPC for arm/disarm/abort/text/shutdown.

    WHY a child process: the recorder's realtime model + cuda_check create a CUDA primary context in
    WHICHEVER process constructs them. Constructing in a CHILD keeps the DAEMON process CUDA-free, so
    terminating the child on idle-unload releases ALL VRAM (daemon PID -> ~0 on nvidia-smi). This is
    the only way to satisfy PRD §7.9 + §6 T6(d). See research/residual_cuda_context_rootcause.md.
    """
    def __init__(self, cfg, feedback, latency, on_final, on_partial, on_speech, *, force_cpu=False):
        self._cfg = cfg; self._feedback = feedback; self._latency = latency
        self._on_final = on_final; self._on_partial = on_partial; self._on_speech = on_speech
        self._force_cpu = force_cpu
        self._cmd_q: mp.Queue = mp.Queue(); self._evt_q: mp.Queue = mp.Queue()
        self._proc: mp.Process | None = None
        self._final_evt = threading.Event(); self._reader: threading.Thread | None = None
        self._device: dict = {}

    def spawn(self, timeout: float = 180.0) -> bool:
        # single-flight is enforced by the CALLER (_load_host) under the daemon _lock.
        ctx = mp.get_context("spawn")
        self._proc = ctx.Process(target=_worker_main, args=(..., self._cmd_q, self._evt_q, ...),
                                 daemon=True)
        self._proc.start()
        # reader thread dispatches events (partials/speech/finals) -> never block the main loop.
        self._reader = threading.Thread(target=self._read_loop, name="vt-host-reader", daemon=True)
        self._reader.start()
        # wait for the child's 'ready'/'error' (the model load happens in the child).
        return self._await_ready(timeout)

    def _read_loop(self):
        try:
            while True:
                kind, payload = self._evt_q.get()
                if kind == "final":
                    self._latency.finalize_utterance(payload)      # SAME feeding as on_final today
                    self._on_final(payload["text"]); self._final_evt.set()
                elif kind == "partial": self._on_partial(payload["text"])
                elif kind == "speech":  self._on_speech()
                elif kind == "ready":   self._device = payload; self._ready_evt.set()
                elif kind == "error":   self._error = payload; self._ready_evt.set()
                elif kind == "gone":    return
        except (EOFError, BrokenPipeError, OSError):
            return  # child died — idempotent; spawn()/stop()/text() handle it

    def text(self, on_final) -> None:
        # PATTERN: mirror the daemon's blocking text() (daemon.py:631). The child blocks on its own
        # recorder.text(); the 'final' event unblocks us. on_final is invoked by the READER thread
        # (set self._on_final=on_final first), so the main loop just waits.
        self._on_final = on_final; self._final_evt.clear()
        try: self._cmd_q.put(("text", {}))
        except (BrokenPipeError, OSError): return
        self._final_evt.wait()   # unblocked by reader thread on 'final' (or child death)

    def stop(self, timeout: float = 5.0) -> None:
        # THE bounded teardown. Killing the child PROCESS GROUP releases ALL VRAM (daemon stays
        # CUDA-free) and cannot reproduce RealtimeSTT's ~90s shutdown wedge (we don't wait on its
        # unbounded thread joins — we SIGKILL the group). Idempotent.
        if not self._proc: return
        try: self._cmd_q.put(("shutdown", {}))
        except Exception: pass
        self._proc.join(timeout=timeout)
        if self._proc.is_alive():
            try: os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)  # child did setsid() -> own group
            except (ProcessLookupError, PermissionError, OSError): pass
            self._proc.join(timeout=2.0)
        self._proc = None

def _worker_main(cfg_dict, cmd_q, evt_q, ...):
    os.setsid()                       # own session/group -> killpg teardown reaches grandchildren
    from voice_typing.daemon import build_recorder   # lazy: only the child imports RealtimeSTT
    # ... build_recorder(...) (UNCHANGED) with on_final=lambda t: evt_q.put(("final",{...})),
    #     realtime partial -> ("partial",{...}), on_speech -> ("speech",{})
    # ... on success evt_q.put(("ready", {device,...})); on failure ("error", {msg}) + retry/exit
    # ... loop: cmd = cmd_q.get(); dispatch arm/disarm/abort/text/shutdown
```

```python
# === voice_typing/daemon.py — _load_host / _unload_host (replace _load_recorder/_unload_recorder) ===

def _load_host(self) -> bool:
    # PATTERN: identical single-flight Condition(_lock) discipline as _load_recorder (:502-578);
    # only "build_recorder()" -> "self._host.spawn()" changes.
    with self._lock:
        if self._models_loaded: return True
        if self._loading:
            while self._loading: self._load_cond.wait()
            return self._models_loaded
        self._loading = True; self._feedback.set_phase("loading"); self._feedback.set_models_loaded(False)
    # heavy spawn OUTSIDE _lock (status/stop stay responsive during the ~1-3s child load)
    host = (self._host_factory or RecorderHost)(self._cfg, self._feedback, self._latency,
                                                self.on_final, self._on_partial, self._touch_speech)
    ok = host.spawn()
    with self._lock:
        self._loading = False
        if ok:
            self._host = host; self._models_loaded = True; self._load_error = None
            self._resolved_device_cache = host.device          # status reports the CHILD's device
            self._feedback.set_phase("idle"); self._feedback.set_models_loaded(True)
        else:
            host.stop()                                         # NO half-built host (§4.2bis)
            self._host = None; self._models_loaded = False; self._load_error = "spawn failed"
            self._feedback.set_phase("unloaded"); self._feedback.set_models_loaded(False)
        self._load_cond.notify_all(); return ok

def _unload_host(self) -> None:
    # PATTERN: same under-_lock re-check as _unload_recorder (:850-873); teardown = host.stop()
    # (terminates the child GROUP -> ALL VRAM released -> daemon tree ABSENT on nvidia-smi).
    with self._lock:
        if (not self._models_loaded or self._listening.is_set() or self._disarmed_monotonic is None
                or self._cfg.asr.auto_unload_idle_seconds <= 0
                or time.monotonic() - self._disarmed_monotonic < self._cfg.asr.auto_unload_idle_seconds):
            return
        logger.info("voice-typing idle-unload: %.1fs disarmed; unloading models",
                    self._cfg.asr.auto_unload_idle_seconds)
        self._host.stop(timeout=5.0)       # <-- kills the child group; releases ALL VRAM
        self._host = None; self._models_loaded = False
        self._feedback.set_phase("unloaded"); self._feedback.set_models_loaded(False)
```

### Integration Points

```yaml
PROCESS MODEL:
  - daemon process: NEVER imports RealtimeSTT/torch/ctranslate2; owns RecorderHost (a handle to a
    child) + the control socket + feedback + typing backends + the run() loop.
  - child process (spawn, own session/group via setsid): owns AudioToTextRecorder (final + realtime
    models + VAD + cuda_check). Spawned on first arm; terminated on idle-unload/quit.
  - grandchildren (transcript_process/reader_process): spawned by the child (RealtimeSTT internals);
    die with the child's process group on teardown.

CONFIG:
  - NO new config knob. auto_unload_idle_seconds (config.py:60) is consumed unchanged. The host's
    stop() timeout (5.0s) is an internal constant, not user-facing.

FEEDBACK / STATUS (UNCHANGED surface):
  - phase: unloaded/loading/idle/listening (driven by _load_host/_unload_host/_arm/_disarm).
  - models_loaded: bool (set_models_loaded in _load_host/_unload_host).
  - voicectl status (ctl.py:85-92): renders identically — the host feeds the same feedback calls.
  - state.json partials: update_partial driven by the host reader thread on 'partial' events.

LATENCY (must not regress):
  - LatencyLog fed identically (child stamps ts_*; host reader thread calls finalize_utterance).
  - T1 (test_feed_audio.py) + T3 (e2e_virtual_mic.sh) are the regression gates — re-run both.

SYSTEMD:
  - TimeoutStopSec=15 (M1.T2.S1) stays valid (host.stop() is bounded at ~5s; quit completes fast).
  - launch_daemon.sh LD_LIBRARY_PATH export is inherited by the spawn child (verify in L3).
```

---

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
uv run ruff check voice_typing tests --fix
uv run mypy voice_typing
uv run ruff format voice_typing tests
bash -n tests/test_idle_and_gpu.sh
shellcheck tests/test_idle_and_gpu.sh 2>/dev/null || echo "(shellcheck optional)"
# Expected: zero errors. The daemon module must NOT import RealtimeSTT/torch/ctranslate2 at top level
# (grep-verify: `grep -nE 'import (RealtimeSTT|torch|ctranslate2)' voice_typing/daemon.py voice_typing/recorder_host.py`
# — daemon.py must show NONE; recorder_host.py must show NONE at module scope, only inside _worker_main).
```

### Level 2: Unit Tests (Component Validation — CUDA-free + fast)

```bash
# Host IPC unit tests (Task 4) — hermetic, fake child.
uv run pytest tests/test_recorder_host.py -v

# The fast lifecycle regression (Task 3) — fake host seam; lifecycle/single-flight/load-failure/idle-unload.
uv run pytest tests/test_daemon.py -v

# build_recorder / _construct / cfg_to_kwargs still green (unchanged interface).
uv run pytest tests/test_daemon.py -k "construct or build_recorder or kwargs" -v

# T1 latency regression — proves the IPC hop did not break partial cadence / final latency.
uv run pytest tests/test_feed_audio.py -v
# Expected: all green. partial cadence <= 300ms; final <= 1.5s (PRD §6).
```

### Level 3: Integration Testing (System Validation — REAL CUDA stack)

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true   # preflight: refuse if a daemon is running

# 3a. Manual lifecycle + status surface (proves voicectl behavior unchanged):
XDG_CONFIG_HOME=$(mktemp -d) mkdir -p "$XDG_CONFIG_HOME/voice-typing"   # (write a minimal config.toml)
voice_typing/launch_daemon.sh > /tmp/vt.log 2>&1 &
DPID=$!
.venv/bin/voicectl status | grep -E '^phase:|^models:|^listening:'      # expect: phase: unloaded, (not loaded), off
.venv/bin/voicectl start                                                # first arm -> spawns host child (~1-3s)
.venv/bin/voicectl status | grep -E '^phase:|^models:|^listening:'      # expect: phase: listening, (loaded), on
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader    # daemon TREE present, 1-5 GiB
ps -o pid,ppid,pgid,sess,cmd -g $(ps -o sid= -p $DPID | tr -d ' ') | head # verify child + grandchildren in the daemon's session/group
.venv/bin/voicectl stop
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader    # STILL present (stop does not unload)
.venv/bin/voicectl quit
wait $DPID 2>/dev/null || true

# 3b. Verify the DAEMON process is CUDA-free at runtime (the core invariant of the fix):
#     after the above, the daemon PID must NOT appear in nvidia-smi at any point — only its CHILD does.
#     (grep the run log for 'device resolved: device=cuda' coming from the CHILD, not the daemon.)

# Expected: status surface unchanged; the daemon PID never holds VRAM; only the child tree does.
```

### Level 4: The real T6 + T4 gate (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
systemctl --user stop voice-typing 2>/dev/null || true
./tests/test_idle_and_gpu.sh
# Expected: exit 0. Evidence block shows:
#   T6 (a) boot (absent):       0
#   T6 (b) armed (present):     <1024-5120> <child pids>
#   T6 (c) disarmed (present):  <1024-5120> <child pids>
#   T6 (d) after idle-unload:   0            # <-- THE FIX: was 258, now 0
#   T6 (d) after re-arm reload: <1024-5120> <new child pids>
#   + criterion 5/6/8 PASS + T4 CPU < 25%.

# T3 end-to-end regression (typing still reaches the tmux pane through the host):
./tests/e2e_virtual_mic.sh
# Expected: exit 0; fuzzy-matched text of all segments incl. post-pause half; nothing typed when off.
```

---

## Final Validation Checklist

### Technical Validation
- [ ] L1: `uv run ruff check voice_typing tests` + `uv run mypy voice_typing` + `ruff format --check` clean.
- [ ] L1: `bash -n` + shellcheck clean on `tests/test_idle_and_gpu.sh`.
- [ ] L1: `grep` confirms `voice_typing/daemon.py` does NOT import RealtimeSTT/torch/ctranslate2 at module scope.
- [ ] L2: `uv run pytest tests/test_recorder_host.py tests/test_daemon.py -v` green.
- [ ] L2: `uv run pytest tests/test_feed_audio.py -v` green (T1 latency — NO regression from IPC).
- [ ] L3: manual lifecycle (L3a) shows status surface unchanged; daemon PID never on nvidia-smi.
- [ ] L4: `./tests/test_idle_and_gpu.sh` exits 0 with T6(d) post-unload total = **0**.
- [ ] L4: `./tests/e2e_virtual_mic.sh` exits 0 (T3 typing regression).

### Feature Validation
- [ ] T6(d-gone) PASSES strictly: daemon tree ABSENT (total 0) after idle-unload, daemon alive.
- [ ] T6(a/b/c/d-reload) all PASS.
- [ ] T4 (120s silence) still green; CPU < 25% of one core.
- [ ] PRD §7.9 + §6 T6(d) satisfied (the 258 MiB residual is gone — daemon process is CUDA-free).
- [ ] voicectl toggle/start/stop/status/quit all work; status phase/models_loaded unchanged.
- [ ] First arm ~1-3s (child spawn + load); later arms instant; idle-unload ~5s bounded; quit bounded.

### Code Quality Validation
- [ ] RecorderHost follows the codebase's "never block the responder" + "idempotent teardown" discipline (ctl.py ControlServer pattern).
- [ ] The single-flight Condition(_lock) discipline of _load_recorder is preserved in _load_host.
- [ ] The test seam (recorder_host=/host_factory=) keeps test_daemon.py hermetic + CUDA-free.
- [ ] No new user-facing config knob (auto_unload_idle_seconds unchanged); the stop() timeout is internal.

### Documentation & Deployment
- [ ] tests/test_idle_and_gpu.sh header documents the subprocess-host fix (replaces the "production bug / do-not-weaken" note).
- [ ] tests/ACCEPTANCE.md: KNOWN-BUG block removed; criterion-1 restored to PASS; real ~0 numbers recorded.
- [ ] (If README's GPU-lifecycle section claims in-process unload, leave it — the EXTERNAL behavior is unchanged; only the internal mechanism changed. No README edit required for behavior. Optionally add a one-line architecture note that the recorder runs in a child process.)

---

## Anti-Patterns to Avoid

- ❌ **Do NOT weaken T6(d-gone).** Attempt 1 correctly refused; the fix is the production change
  (subprocess host), not a looser assertion. `assert_vram_absent` (total == 0) stays.
- ❌ **Do NOT block the daemon on `recorder.shutdown()`.** RealtimeSTT's shutdown can wedge ~90s
  (unbounded thread joins, core/shutdown.py:33/62). The host bounds teardown by TERMINATING THE CHILD
  PROCESS GROUP — never by waiting on the recorder's own shutdown.
- ❌ **Do NOT terminate only the child PID.** The child spawns grandchildren (transcript_process/
  reader_process). Kill the PROCESS GROUP (os.setsid in the child + os.killpg) or grandchildren orphan
  and hold VRAM — the exact failure mode attempt 1 hit, just moved one level down.
- ❌ **Do NOT import RealtimeSTT/torch/ctranslate2 in the daemon process** (even at module top level of
  recorder_host.py). Importing them can initialize CUDA in the daemon. The recorder is imported ONLY
  inside `_worker_main` (the child). The daemon imports only the RecorderHost handle.
- ❌ **Do NOT route feed_audio (T1) through the host.** It's an offline test path that builds a real
  recorder with use_microphone=False directly; it does not exercise idle-unload. Keep it in-process.
- ❌ **Do NOT change the external surface.** voicectl status, phase/models_loaded, latency log format,
  config knobs, systemd unit — all unchanged. Only the internal recorder ownership changes.
- ❌ **Do NOT repeat attempt 1's in-process approach.** gc.collect()+empty_cache() in the unload path
  reduces the residual toward the bare-context floor but NEVER to 0 (the CUDA primary context is
  unreleasable without process exit). It will fail T6(d-gone) again.

---

## Confidence Score & Notes

**Confidence: 7/10** for one-pass success. The fix is architecturally correct and the IPC surface is
small + well-bounded, but it is a non-trivial refactor over recently-"Complete" work (M2.T1 lazy
load, M3.T1.S1 idle-unload, M1.T1.S2 bounded teardown). The two real risks are: (1) the daemon run()
loop's blocking `text()` ↔ host proxy ↔ reader-thread-final-dispatch wiring (get the threading right
or partials/finals stall — T1/T3 catch this); (2) process-group teardown correctness (killpg must
reach grandchildren — L3a + T6(d-gone) catch this). Both are explicitly gated in L2/L3/L4. The strict
T6(d-gone) assertion is the ultimate proof the fix worked; if it still shows a residual, a grandchild
is orphaning — debug the group teardown, do NOT weaken the assertion.

**Scope note for the orchestrator:** this PRP expands P1.M3.T2.S2 from "rewrite the test" to
"subprocess recorder host (production fix) + rewrite the test," because the issue feedback
established that the in-process idle-unload path structurally cannot satisfy PRD §7.9 and explicitly
asked to fix the production path rather than weaken the test. The alternative (declare `result: fail`)
was rejected: the fix is feasible (small IPC surface; RealtimeSTT already uses spawn internally), not
fundamentally impossible. The re-opens of M2.T1/M3.T1.S1/M1.T1.S2 are confined to the recorder-
ownership layer; their external behavior (lazy load, idle-unload watchdog, bounded teardown) is
preserved.
