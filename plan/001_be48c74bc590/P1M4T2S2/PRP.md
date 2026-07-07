# PRP — P1.M4.T2.S2: quit / clean-shutdown wiring (recorder.shutdown + SIGTERM/SIGINT)

## Goal

**Feature Goal**: Add the **full daemon teardown** to `voice_typing/daemon.py` so that a `quit`
command, a `SIGTERM` (systemd stop/restart), or a `SIGINT` (Ctrl-C) all route to ONE clean path that
**releases the GPU model-worker processes** (no orphans, no leaked VRAM) and lets the main thread exit.
This closes the two gaps the prior subtasks deliberately left open: (1) `recorder.shutdown()` — the
ONLY sanctioned full teardown (PRD §4.2 `{"cmd":"quit"}` → clean shutdown) — is never called anywhere
today (`request_shutdown()` sets a flag + `abort()` but explicitly skips `shutdown()`, verified in
`test_request_shutdown_..._not_shutdown`); (2) there are no signal handlers, so systemd's default
`SIGTERM` kills the parent instantly while the spawn-started `transcript_process`/`reader_process`
**orphan** (hold VRAM + the mic) — exactly the failure the item contract forbids.

**Deliverable** (2 files — 1 MODIFY source, 1 MODIFY tests; **NO new module**):
1. `voice_typing/daemon.py` — ADD `import signal` (one line); ADD `VoiceTypingDaemon.shutdown()`
   (idempotent, defensive `recorder.shutdown()`); ADD module-level
   `install_shutdown_signal_handlers(daemon, *, signals=None) -> restore`. **Do NOT touch**
   `__init__`/`run`/`on_final`/`_arm`/`_disarm`/`start`/`stop`/`toggle`/`request_shutdown`/
   `_build_callbacks`/`_construct`/`build_recorder`/`cfg_to_kwargs`/`_resolve_device_config`/
   `LatencyLog`/`_configure_log_level`/`_log_resolved_device`/`uptime_s` (M4.T1.S1/S2/S3 own them);
   do NOT touch `ControlServer`/`_default_control_socket_path`/`status_snapshot`/`_resolved_device`
   (M4.T2.S1 owns them). All edits are **100% additive** → zero merge conflict with the in-flight
   S1-of-T2 (which adds `json/os/select/socket` imports + `ControlServer` + 2 status methods).
2. `tests/test_daemon.py` — **APPEND** a `shutdown()` + `install_shutdown_signal_handlers()` test
   section that reuses `_make_daemon()` / `_StubRecorder` / `_wait_for` (do NOT edit S1/S2/S3 bodies).

**Success Definition**:
- (a) `voice_typing/daemon.py` + `tests/test_daemon.py` `py_compile`-clean; `import voice_typing.daemon`
  stays import-pure (only stdlib `signal` added at module top; `RealtimeSTT`/`torch`/`ctranslate2` NOT
  in `sys.modules` after import); `VoiceTypingDaemon.shutdown` and `install_shutdown_signal_handlers`
  are module attributes.
- (b) `VoiceTypingDaemon.shutdown()` calls `self._recorder.shutdown()` **exactly once** (verified via
  `_StubRecorder.shutdowns`), is **idempotent** (a `_shutdown_done` flag set under `self._lock` via
  `getattr` — **no `__init__` edit** — so a second call is a no-op), and is **defensive** (a recorder
  whose `shutdown()` raises is logged-and-swallowed, never re-raised — teardown is best-effort).
- (c) `request_shutdown()` / `stop()` / `toggle()` STILL never call `recorder.shutdown()` — the
  existing tests `test_stop_never_calls_recorder_shutdown` and `test_request_shutdown_..._not_shutdown`
  pass **UNCHANGED** (regression proof shutdown() is a brand-new, separate path).
- (d) `install_shutdown_signal_handlers(d)` registers handlers for `SIGTERM`+`SIGINT` that, when fired,
  **spawn a daemon thread** calling `d.request_shutdown()` (NOT `abort()` directly — research §3:
  `abort()` blocks on `was_interrupted.wait()`, set only by the main thread's `text()`, so calling it
  from a main-thread signal handler deadlocks). Returns a `restore()` callable reinstaling the prior
  handlers. Must be callable from the main thread only (`signal.signal` requirement).
- (e) The handler is **idempotent-vs-reentry**: a second signal while `_shutdown` is already set does
  not spawn another abort thread.
- (f) The **teardown sequence** this enables is documented (Integration Points) for P1.M4.T3.S1
  `main()`: `srv = ControlServer(d, on_quit=d.shutdown)` (quit → `recorder.shutdown()` after
  `request_shutdown()` broke `text()`, research §4) → `srv.start()` → `install_shutdown_signal_handlers(d)`
  → `try: d.run() finally: d.shutdown(); srv.stop(); restore()` (idempotent `shutdown()` covers the
  signal path; `srv.stop()` closes the socket + unlinks — S1, NEVER from `on_quit`).
- (g) **Backward compat**: the existing 146 tests pass UNCHANGED; ~8–10 new tests pass;
  `.venv/bin/python -m pytest tests/ -q` green (~155+ passed). Coexists with the in-flight S1-of-T2
  (disjoint symbols + one new stdlib import → no merge conflict).
- (h) **No out-of-scope code:** NO `main()`/`if __name__ == "__main__":` (P1.M4.T3.S1), NO
  `ControlServer` edits, NO `logging.basicConfig`/handler config, NO `ctl.py` (P1.M5.T1.S1), NO edits
  to `config.py`/`config.toml`/`pyproject.toml`/`uv.lock`/`PRD.md`/`tasks.json`/`.gitignore`/
  `feedback.py`/`cuda_check.py`/`textproc.py`/`typing_backends.py`.

## User Persona

**Target User**: Internal — three future consumers read this surface:
1. **P1.M4.T3.S1 (`main()` entry point)** — constructs `ControlServer(d, on_quit=d.shutdown)`, calls
   `install_shutdown_signal_handlers(d)`, runs `d.run()`, and in `finally` calls `d.shutdown()` +
   `srv.stop()` + `restore()`. T2.S2 PROVIDES `shutdown()` + the signal installer; T3.S1 wires them.
2. **P1.M6.T1.S2 (systemd `voice-typing.service`)** — `Restart=on-failure` sends `SIGTERM` to stop
   the old instance; the new instance can start only cleanly if the old one ran `recorder.shutdown()`
   (released VRAM). T2.S2's SIGTERM handler + `shutdown()` make that reliable.
3. **Operators / devs** — `voicectl quit` (P1.M5.T1.S1) and `Ctrl-C` / `systemctl --user stop` all
   drain the daemon without orphaning the ctranslate2 worker.

**Use Case**: The daemon runs as a systemd user service. The user runs `voicectl quit` (or systemd
sends SIGTERM on restart, or the dev hits Ctrl-C). The main thread is blocked in `recorder.text()`.
The teardown breaks `text()` (`abort()` off the main thread), `run()` exits, `recorder.shutdown()`
terminates the spawn-started `transcript_process`/`reader_process` (GPU VRAM + mic released), the
control socket is closed + unlinked, and the process exits 0. `nvidia-smi` shows no leftover
voice-typing VRAM; the mic device is free for the next start.

**Pain Points Addressed**: (1) No `recorder.shutdown()` anywhere today → every "quit" today would
orphan the model worker (VRAM leak across restarts). (2) No SIGTERM handler → systemd stop = hard
kill = orphaned workers + leaked VRAM. (3) Naively wiring `abort()`/`shutdown()` into a signal
handler deadlocks (research §3) — T2.S2 ships the verified-safe spawn-thread pattern.

## Why

- **This is the difference between a clean restart and a VRAM-leaking one.** RealtimeSTT's
  `transcript_process` is a **`mp.Process`** started with `mp.set_start_method("spawn")`
  (verified `core/initialization.py:354-355,397,433`). spawn-started children are independent OS
  processes; if the parent dies without `recorder.shutdown()`, they orphan. PRD §4.2 + the item
  contract explicitly require "no orphaned model worker processes." `recorder.shutdown()` (verified
  `core/shutdown.py`) is the ONLY call that `join`s + `terminate`s them.
- **SIGTERM's default is silent orphaning.** Python's default SIGTERM = immediate process death (no
  `KeyboardInterrupt`, no `finally`, no `atexit`). systemd stop/restart sends SIGTERM. Without a
  handler, the parent dies and the workers orphan. The item contract mandates SIGTERM/SIGINT → the
  SAME clean path. T2.S2 installs it.
- **The obvious wiring deadlocks; the correct wiring is subtle.** `recorder.abort()` blocks on
  `was_interrupted.wait()` (set only by `text()` in the main thread, verified `core/lifecycle.py` +
  `core/transcription_api.py`). CPython runs signal handlers **in the main thread**
  (https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers). So a SIGTERM
  handler that calls `abort()` directly deadlocks (CPython #121649 documents this exact class of
  bug). T2.S2 defers the blocking `abort()` to a **spawned daemon thread** (research §3/§6c).
- **`on_quit` ordering makes quit self-contained.** S1's `_dispatch("quit")` calls
  `request_shutdown()` (blocks until `abort()` returns, i.e. until `text()` has returned) **then**
  `on_quit()`. So `on_quit = daemon.shutdown` runs only after the main thread is safely out of
  `text()` → `recorder.shutdown()` from the worker thread is safe (research §4). No fragile timing.
- **Idempotency lets two call sites coexist.** `recorder.shutdown()` is itself idempotent
  (`is_shut_down` + `shutdown_lock`, verified `core/shutdown.py`); T2.S2 adds a `_shutdown_done` flag
  too. So `on_quit=shutdown` (quit path) AND `main()` finally `shutdown()` (signal path) can both fire
  — the first wins, the second is a no-op.

## What

Two small, additive pieces (the exact code is pinned in "Implementation Blueprint" — copy-pasteable,
verified against the live source + the installed RealtimeSTT):

1. `VoiceTypingDaemon.shutdown()` — the sanctioned `recorder.shutdown()` teardown (idempotent,
   defensive). Called by the quit `on_quit` hook (T3.S1) and `main()`'s `finally`.
2. `install_shutdown_signal_handlers(daemon)` — registers SIGTERM/SIGINT → spawn-thread →
   `request_shutdown()`. Called once from the main thread in `main()` (T3.S1). Returns `restore()`.

### Success Criteria

- [ ] `VoiceTypingDaemon.shutdown` + `install_shutdown_signal_handlers` exist and are callable.
- [ ] `shutdown()` → `_StubRecorder.shutdowns == 1`; idempotent (2 calls → still 1); defensive
      (raising recorder → no re-raise, log only).
- [ ] `request_shutdown()`/`stop()`/`toggle()` STILL never call `recorder.shutdown()` (existing
      tests unchanged → regression proof).
- [ ] Signal handler spawns a thread calling `request_shutdown()` (assert `_shutdown.is_set()` + abort
      within ~1 s); a second signal while `_shutdown` set spawns no further abort (idempotent-vs-reentry).
- [ ] `install_...` returns `restore()` that reinstalls prior handlers.
- [ ] Import purity preserved (only stdlib `signal` added).
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~155+ passed); S1/S2/S3 test bodies UNCHANGED.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the exact `shutdown()` +
`install_shutdown_signal_handlers()` source is pinned below (verified against the live `daemon.py` +
installed RealtimeSTT 1.0.2). The consumed daemon surface (`_recorder`, `_lock`, `_shutdown`,
`request_shutdown`, `logger`) + the `_StubRecorder` test stub (already has `shutdown()`) + the
`_make_daemon()`/`_wait_for` helpers are read at preflight against the LIVE source below. The deadlock
analysis (the single highest-risk detail) is fully documented (research §3) with the exact RealtimeSTT
code that causes it. The validation commands are executable as written.

### Documentation & References

```yaml
# MUST READ — the work-item design + empirical verification (THIS is the spec).
- file: plan/001_be48c74bc590/P1M4T2S2/research/shutdown_signals_design.md
  why: "§2 what recorder.shutdown() releases (transcript_process/reader_process are mp.Process spawn-
        started — orphan = VRAM leak). §3 THE deadlock: abort() blocks on was_interrupted.wait(), set
        only by text() in the main thread -> a main-thread signal handler calling abort() deadlocks
        (CPython #121649); FIX = spawn a daemon thread -> request_shutdown(). §4 why on_quit=d.shutdown
        is safe (request_shutdown blocks until text() returns). §5 why a SIGTERM handler is MANDATORY
        (default = silent orphaning under systemd). §6 the verbatim code. §7 the test strategy."
  critical: "The signal handler MUST spawn a thread that calls daemon.request_shutdown() — it MUST NOT
             call recorder.abort() (blocks -> deadlock) and MUST NOT call recorder.shutdown() (joins the
             worker threads the main thread is still inside). The handler body is 3 lines: check the
             _shutdown flag, log, spawn. Verified safe because the main thread blocked in text() does not
             hold threading's _active_limbo_lock."

# MUST READ — the module being EXTENDED (live S1+S2+S3 state; 146 tests green).
- file: voice_typing/daemon.py
  why: "The exact starting point. Consumed daemon surface: self._recorder (has .shutdown()/.abort()/
        .set_microphone()/.text()), self._lock (threading.Lock; serializes arm/disarm/abort), self.
        _shutdown (threading.Event; run() loop gate), request_shutdown() (sets _shutdown + abort under
        _lock; BLOCKS until abort returns), logger (module-level logging.getLogger(__name__)). Module-top
        imports (post-S3): collections, inspect, logging, threading, time, typing + voice_typing.*. S1-of-
        T2 (parallel, merged before T2.S2 runs) ADDS json/os/select/socket + ControlServer + 2 status
        methods. T2.S2 ADDS signal + shutdown() + install_shutdown_signal_handlers (all additive, disjoint
        symbols from S1-of-T2)."
  critical: "Do NOT modify __init__/run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown/
             _build_callbacks/_construct/build_recorder/cfg_to_kwargs/_resolve_device_config/_filter_
             kwargs_to_signature/_FIXED_KWARGS/_PARTIAL_CALLBACK_ATTR/LatencyLog/_configure_log_level/
             _log_resolved_device/uptime_s. ALL T2.S2 edits are ADDITIVE (1 new import, 1 new method on
             VoiceTypingDaemon placed at the end of the class, 1 new module fn at module end). Do NOT add
             self._shutdown_done in __init__ — use getattr() in shutdown() (research §6b) so __init__ is
             untouched."

# MUST READ — the S1-of-T2 ControlServer contract (on_quit hook this PRP relies on).
- file: plan/001_be48c74bc590/P1M4T2S1/PRP.md
  why: "S1's _dispatch('quit') calls self._daemon.request_shutdown() THEN self._on_quit() (if set), then
        replies {ok:true,shutting_down:true}. Because request_shutdown() blocks until abort() returns
        (until text() returned), on_quit runs AFTER the main thread is out of text() -> on_quit=d.shutdown
        is SAFE. S1's ControlServer.stop() closes the socket + unlinks the file + joins the accept thread
        (<=2 s). T2.S2 PROVIDES daemon.shutdown() for the on_quit wiring; T2.S2 does NOT touch ControlServer."
  critical: "srv.stop() MUST run on the MAIN thread (main() finally) — it joins the accept thread, and
             on_quit runs ON a worker of that thread -> calling srv.stop() from on_quit would self-join-
             deadlock. T2.S2 documents this; T3.S1 wires srv.stop() into finally. Do NOT call srv.stop()
             from anywhere in daemon.py."

# MUST READ — the installed RealtimeSTT internals (authoritative for THIS machine).
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/shutdown.py
  why: "shutdown_recorder(): idempotent (is_shut_down + shutdown_lock); sets wake-events; joins
        recording_thread + realtime_thread; join(timeout=10)+terminate() the reader_process + transcript_
        process (the spawn-started mp.Process workers that HOLD GPU VRAM + the mic); closes the pipe;
        del realtime_transcription_model; gc.collect(). THIS is the 'no orphaned workers' guarantee."
  critical: "It is the ONLY sanctioned full teardown. It is safe to call twice (is_shut_down guard). It
             must be called from a context where the main thread is NOT inside recorder.text() (request_
             shutdown()/abort() guarantees that — research §3/§4). T2.S2 wraps it defensively (try/except,
             log-not-raise) so a broken teardown never masks the shutdown reason."

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/lifecycle.py
  why: "abort_recording(): sets interrupt_stop_event, then if state != 'inactive' calls recorder.
        was_interrupted.wait() (BLOCKS until text() sets it). This is why abort() MUST run off the main
        thread (signal handler spawns a thread)."
  critical: "Calling abort() from a main-thread signal handler that preempted text() deadlocks (was_
            interrupted is set by text(), which is suspended). CPython #121649 documents the class."

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/transcription_api.py
  why: "text(): wait_audio() then checks interrupt_stop_event -> sets was_interrupted -> returns ''.
        Confirms was_interrupted is set ONLY by the main thread inside text()."

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py
  why: "transcript_process + reader_process are mp.Process started with mp.set_start_method('spawn')
        (lines 354-355, 397, 433). spawn children orphan if the parent dies without shutdown()."

# MUST READ — the S1/S2/S3 tests (regression baseline T2.S2 must NOT break + the stubs to reuse).
- file: tests/test_daemon.py
  why: "_StubRecorder already implements def shutdown(self): self.shutdowns += 1 (and abort/mic/text) —
        REUSE it for shutdown() tests. _make_daemon(*, recorder=None, backend=None, cfg=None) builds a
        daemon with a _StubRecorder + _DaemonFakeFeedback + _FakeBackend. _wait_for(predicate, timeout=2.0)
        polls. The existing tests test_stop_never_calls_recorder_shutdown + test_request_shutdown_..._
        _not_shutdown assert shutdowns==0 for stop/request_shutdown — they MUST stay green (T2.S2 adds a
        SEPARATE shutdown() path)."
  critical: "APPEND the new section; do NOT edit S1/S2/S3 test bodies. Reuse _make_daemon/_StubRecorder/
             _wait_for (imported/defined earlier in the same file). For a raising-recorder test, add a tiny
             _RaisingRecorder stub (shutdown raises) in the new section."

# Background — the preceding subtask PRPs (house style + the daemon surface).
- file: plan/001_be48c74bc590/P1M4T1S2/PRP.md
  why: "The VoiceTypingDaemon design: request_shutdown (set _shutdown + abort under _lock; NO shutdown),
        _disarm (set_microphone+abort; models stay resident), _lock, _recorder. Confirms shutdown() must be
        a NEW path, not folded into request_shutdown/stop."

# Downstream — the consumer T2.S2 feeds (do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T3.S1 (main entry point): wires ControlServer(on_quit=d.shutdown) + install_shutdown_signal_
        handlers(d) + try/finally d.shutdown()/srv.stop()/restore(). P1.M6.T1.S2 (systemd unit): relies on
        SIGTERM -> clean path + recorder.shutdown() releasing VRAM before Restart. Confirms the contract."
  critical: "Do NOT build main()/ControlServer/systemd unit here. shutdown() + install_shutdown_signal_
            handlers are the contract T3.S1 + systemd rely on — do not rename them."

# External — authoritative Python signal semantics + the deadlock class.
- url: https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers
  why: "'Python signal handlers are always executed in the main Python thread of the main interpreter' —
        the reason abort()/shutdown() cannot be called directly from the handler (they would re-enter the
        main thread's blocked text())."
- url: https://github.com/python/cpython/issues/121649
  why: "Deadlock shutting down a ThreadPoolExecutor from inside a SIGTERM handler (the _shutdown_lock was
        held by the main thread). The exact failure mode T2.S2 avoids by deferring blocking work to a
        spawned thread."
- url: https://oneuptime.com/blog/post/2025-01-06-python-graceful-shutdown-kubernetes/view
  why: "Production pattern: register a SIGTERM handler that sets a flag / defers teardown off the handler;
        do the real cleanup in the main loop's finally."
```

### Current Codebase tree (state at P1.M4.T2.S2 start — S1+S2+S3 of M4.T1 merged, 146 passing; +S1-of-T2 when it lands)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§4.2 quit/clean-shutdown, §4.9 systemd, §8 risks)
├── config.toml pyproject.toml uv.lock   # DO NOT touch (no new deps; stdlib signal only)
├── voice_typing/
│   ├── __init__.py                # DO NOT touch
│   ├── cuda_check.py config.py textproc.py typing_backends.py status.sh launch_daemon.sh prefetch.py
│   ├── feedback.py                # DO NOT touch (S1-of-T2 adds snapshot(); not T2.S2's concern)
│   └── daemon.py                  # ← MODIFY (Task 1): ADD `import signal` + VoiceTypingDaemon.shutdown()
│                                  #   + install_shutdown_signal_handlers(). (NO existing-symbol edit.)
└── tests/
    ├── test_config.py test_config_repo_default.py test_textproc.py test_typing_backends.py test_feedback.py
    ├── test_control_socket.py     # (S1-of-T2 NEW; not T2.S2's concern) — DO NOT touch
    └── test_daemon.py             # ← MODIFY (Task 2): APPEND shutdown() + signal-handler tests.
```

### Desired Codebase tree with files to be added/modified

```bash
voice_typing/daemon.py             # +import signal, +VoiceTypingDaemon.shutdown(), +install_shutdown_signal_handlers()
tests/test_daemon.py               # +shutdown()/signal-handler test section (appended)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — abort() BLOCKS; never call it (or shutdown()) from a main-thread signal handler.
#   RealtimeSTT abort_recording() does `recorder.was_interrupted.wait()` (core/lifecycle.py).
#   was_interrupted is set ONLY by text() (core/transcription_api.py) in the MAIN thread. CPython runs
#   signal handlers IN the main thread (docs.python.org signal.html). So a SIGTERM/SIGINT handler that
#   calls abort() (or shutdown(), which joins those threads) deadlocks — the main thread can't return to
#   text() to set was_interrupted (CPython #121649 documents the class). FIX: the handler spawns a daemon
#   thread that calls daemon.request_shutdown() (abort OFF the main thread = safe); the handler returns
#   immediately. (research §3/§6c — verbatim code.)

# CRITICAL #2 — SIGTERM default = silent orphaning. Python's default SIGTERM terminates the process
#   immediately (NO KeyboardInterrupt, NO finally, NO atexit). systemd stop/restart sends SIGTERM. The
#   spawn-started transcript_process/reader_process (mp.Process, core/initialization.py:354-355,397,433)
#   then ORPHAN (hold GPU VRAM + the mic). T2.S2 MUST install a SIGTERM handler -> the clean path. (§5.)

# CRITICAL #3 — recorder.shutdown() is the ONLY sanctioned full teardown AND is idempotent. It
#   join(timeout=10)+terminate() the transcript_process + reader_process (core/shutdown.py) — releasing
#   VRAM + the mic. It guards on is_shut_down + shutdown_lock -> safe to call twice. NEVER call it on
#   toggle/stop (models must stay resident — _disarm uses set_microphone+abort only). T2.S2 wraps it
#   defensively (try/except, log-not-raise) so a broken teardown doesn't mask the shutdown reason.

# CRITICAL #4 — request_shutdown() BLOCKS until text() returns. It calls abort() (under self._lock),
#   which waits on was_interrupted (set when text() notices interrupt_stop_event). Therefore, by the time
#   request_shutdown() RETURNS (e.g. in S1's quit handler, before on_quit fires), the main thread has
#   already exited text() and is leaving run(). So on_quit=d.shutdown (calling recorder.shutdown() from
#   the ControlServer worker thread) is SAFE — the main thread is no longer inside any recorder call.
#   (§4.) This is what makes the quit path self-contained without fragile sleeps.

# CRITICAL #5 — ControlServer.stop() MUST run on the main thread. It joins the accept thread (S1's
#   ControlServer). on_quit runs ON a worker spawned by that accept thread -> calling srv.stop() from
#   on_quit would self-join-deadlock. T2.S2 does NOT call srv.stop() anywhere; T3.S1 wires srv.stop()
#   into main()'s finally (after run() returns). T2.S2 only documents this. (§6d.)

# CRITICAL #6 — do NOT edit __init__. S1/S2/S3 of M4.T1 own __init__ (and _build_callbacks/_construct/
#   build_recorder have the optional latency param from S3). T2.S2's shutdown() uses getattr(self,
#   '_shutdown_done', False) so it needs NO __init__ attribute. Additive-only -> zero merge conflict.

# CRITICAL #7 — import purity. T2.S2 adds only `import signal` (stdlib). RealtimeSTT/torch/ctranslate2
#   stay lazily imported inside build_recorder (unchanged). The import-purity grep must still pass.
#   install_shutdown_signal_handlers references signal/threading/logging — all stdlib (already imported).

# CRITICAL #8 — backward compat is non-negotiable. The existing tests test_stop_never_calls_recorder_
#   shutdown + test_request_shutdown_..._not_shutdown assert shutdowns==0 for stop()/request_shutdown().
#   T2.S2's shutdown() is a NEW, SEPARATE method — it must NOT be called from stop()/request_shutdown()/
#   _disarm(). Those keep using set_microphone+abort (models stay resident). (Regression proof.)

# CRITICAL #9 — the signal handler must be installed from the MAIN thread. signal.signal() raises
#   ValueError if called from a non-main thread. T3.S1's main() (main thread) calls install_shutdown_
#   signal_handlers(d). Tests that register handlers also run in the main thread (pytest's main thread) —
#   fine. Always restore() at the end so pytest's own SIGINT handling is untouched.

# CRITICAL #10 — be defensive vs a handler firing during process exit. The handler checks
#   daemon._shutdown.is_set() first and returns if already shutting down (idempotent-vs-reentry — no
#   thread spam on repeated signals). Spawning a daemon thread means it won't block process exit even if
#   request_shutdown is slow.

# CRITICAL #11 — FULL PATHS for tooling (zsh aliases python/pytest). ALWAYS
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest).
#   mypy is NOT installed — do NOT list it. ruff is optional (/home/dustin/.local/bin/ruff);
#   py_compile + pytest are the authoritative gates.

# GOTCHA #12 — when adding `import signal` to the module-top block, S1-of-T2 (parallel, merged first)
#   will already have added json/os/select/socket. Place `signal` alphabetically BETWEEN `select` and
#   `socket` (s-e-l < s-i-g < s-o-c). If the live block differs from the anchor, merge the one new
#   stdlib import preserving alphabetical order. Do NOT reorder existing imports.
```

## Implementation Blueprint

### Data models and structure

No new data model. Two callables + one lazy flag:

```python
VoiceTypingDaemon._shutdown_done: bool   # lazy via getattr (NO __init__ edit); guards idempotent teardown
install_shutdown_signal_handlers._restore: Callable[[], None]  # reinstalls prior handlers (returned)
```

`install_shutdown_signal_handlers` holds only transient state (the `previous` dict + the `_handler`
closure), captured in the returned `restore()`.

### `VoiceTypingDaemon.shutdown()` reference implementation (research §6b — implement verbatim)

```python
    # ADD to class VoiceTypingDaemon (at the END of the class, after the uptime_s property).
    # Pure addition — do not modify __init__/run/on_final/request_shutdown/anything else.

    def shutdown(self) -> None:
        """Full recorder teardown (PRD §4.2; P1.M4.T2.S2). Idempotent + defensive.

        Calls self._recorder.shutdown(), which terminates the spawn-started transcript_process +
        reader_process (releases GPU VRAM + the mic device — the "no orphaned model worker processes"
        guarantee). IDEMPOTENT: a getattr-guarded flag (no __init__ edit) plus RealtimeSTT's own
        is_shut_down guard make a double call (quit on_quit + main() finally) a no-op the second time.
        DEFENSIVE: a recorder.shutdown() failure is logged, NOT re-raised — the daemon is exiting and
        teardown is best-effort (a broken teardown must not mask the original shutdown reason).

        NEVER call this on toggle/stop (models must stay resident — those use set_microphone+abort).
        The sanctioned callers are the quit on_quit hook (after request_shutdown() broke text()) and
        main()'s finally block (after run() returns; covers the signal path). Must NOT run while the
        main thread is inside recorder.text() — request_shutdown()/abort() guarantees it has exited
        text() before this is reached.
        """
        with self._lock:
            if getattr(self, "_shutdown_done", False):
                return
            self._shutdown_done = True
        try:
            self._recorder.shutdown()
            logger.info("recorder shutdown complete (GPU workers released)")
        except Exception:
            logger.exception("recorder.shutdown() failed during teardown (best-effort; ignored)")
```

### `install_shutdown_signal_handlers()` reference implementation (research §6c — implement verbatim)

```python
# ADD at module END (after class VoiceTypingDaemon, after any ControlServer S1-of-T2 added).
# A module function (not a method) — takes the daemon; uses only stdlib (signal/threading/logging).


def install_shutdown_signal_handlers(
    daemon: "VoiceTypingDaemon",
    *,
    signals: "tuple[int, ...] | None" = None,
) -> "Callable[[], None]":
    """Install SIGTERM/SIGINT handlers that request clean daemon shutdown (PRD §4.2/§4.9; P1.M4.T2.S2).

    systemd stop/restart sends SIGTERM (Python's default = immediate process death, NO Python cleanup
    -> the spawn-started model workers orphan + VRAM leaks). Ctrl-C sends SIGINT. Both route to the
    SAME clean path. The handler runs in the MAIN thread (CPython signal semantics) and therefore MUST
    NOT call recorder.abort() or recorder.shutdown() directly: abort() blocks on was_interrupted.wait(),
    set only by text() in the main thread -> deadlock (CPython #121649); shutdown() joins the very
    worker threads the main thread is still inside. Instead the handler spawns a daemon THREAD that
    calls daemon.request_shutdown() (abort OFF the main thread = safe); the handler returns at once.
    The spawned thread breaks text(); run() exits; main()'s finally calls daemon.shutdown() +
    ControlServer.stop() (T3.S1 wires; T2.S2 provides this fn).

    Must be called from the MAIN thread (signal.signal() requires it; raises ValueError otherwise).
    Returns a restore() callable that reinstalls the previous handlers (tests + clean uninstall).
    Idempotent-vs-reentry: a signal received while _shutdown is already set is ignored (no thread spam).
    """
    sigs = signals if signals is not None else (signal.SIGTERM, signal.SIGINT)
    previous: dict[int, Any] = {}

    def _handler(signum: int, frame: Any) -> None:
        # Runs in the MAIN thread. Do NOT call abort()/shutdown() here (deadlock, research §3).
        if daemon._shutdown.is_set():
            return  # already tearing down — ignore further signals
        logger.info("received signal %s; requesting clean shutdown", signum)
        threading.Thread(
            target=daemon.request_shutdown,
            name="voice-typing-signal-shutdown",
            daemon=True,
        ).start()

    for s in sigs:
        previous[s] = signal.signal(s, _handler)

    def restore() -> None:
        for s, prev in previous.items():
            signal.signal(s, prev)

    return restore
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the live state + consumed surface + the baseline.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/daemon.py && echo ok
      .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1      # expect "146 passed" (or ~159+ if S1-of-T2 landed)
      .venv/bin/python -c "
import sys, voice_typing.daemon as d
assert hasattr(d,'VoiceTypingDaemon') and hasattr(d.VoiceTypingDaemon,'request_shutdown')
assert hasattr(d.VoiceTypingDaemon,'_lock')          # consumed by shutdown()
assert not hasattr(d.VoiceTypingDaemon,'shutdown'), 'shutdown() already present (unexpected)'
assert not hasattr(d,'install_shutdown_signal_handlers'), 'installer already present (unexpected)'
assert 'signal' not in [m.split('.')[0] for m in ([] )], 'noop'
bad=[m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
assert not bad, f'import purity broken pre-task: {bad}'
print('daemon surface + import purity OK; baseline green')
"
      grep -n '^import \|^from ' voice_typing/daemon.py | head   # confirm current import block (anchor for Task 1a)
  - EXPECTED: 146 passed (S1+S2+S3 of M4.T1; +~13 if S1-of-T2 merged -> ~159); VoiceTypingDaemon has
    request_shutdown/_lock/_shutdown/_recorder; shutdown()/install_shutdown_signal_handlers NOT yet
    present; import purity holds. NOTE the exact import-block lines for the Task 1a anchor (S1-of-T2
    may have already added json/os/select/socket — place `signal` between select and socket).
  - DO NOT create/edit any file, run uv sync/add, or touch other modules.

Task 1: MODIFY voice_typing/daemon.py — ADD `import signal` + VoiceTypingDaemon.shutdown() +
        install_shutdown_signal_handlers().
  - FILE: voice_typing/daemon.py.
  - (1a) ADD `import signal` to the module-top stdlib import block, alphabetically BETWEEN `select`
         and `socket` (s-e-l < s-i-g < s-o-c). If S1-of-T2 has not yet merged (no json/os/select/
         socket), insert `signal` after `logging` / before `threading` to stay alphabetical — see
         "Task 1a edit" for both cases. Do NOT reorder existing imports.
  - (1b) ADD the `shutdown()` method verbatim (above) to class VoiceTypingDaemon, at the END of the
         class (right after the `uptime_s` property; before `class ControlServer` if S1-of-T2 added
         one, otherwise at module end of the class). Pure addition.
  - (1c) ADD the `install_shutdown_signal_handlers()` module function verbatim (above) at MODULE END
         (after class VoiceTypingDaemon; after `class ControlServer` if S1-of-T2 added one). It
         consumes the daemon; uses only stdlib.
  - DO NOT: modify __init__/run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown/_build_
    callbacks/_construct/build_recorder/cfg_to_kwargs/_resolve_device_config/_filter_kwargs_to_
    signature/LatencyLog/_configure_log_level/_log_resolved_device/uptime_s; add self._shutdown_done
    in __init__ (use getattr in shutdown()); add main()/__main__/basicConfig; touch ControlServer/
    _default_control_socket_path/status_snapshot/_resolved_device (S1-of-T2 owns them); edit
    config.py/config.toml/pyproject.toml/feedback.py.

Task 2: MODIFY tests/test_daemon.py — APPEND the shutdown() + signal-handler test section.
  - FILE: tests/test_daemon.py. APPEND only; do NOT edit S1/S2/S3 bodies. See "Task 2 SOURCE" below.
  - PATTERNS: reuse _make_daemon()/_StubRecorder/_wait_for (defined earlier in the file). For the
    raising-recorder case, add a tiny _RaisingRecorder stub (shutdown raises) in the new section.
    For signal tests, capture the handler via signal.getsignal, invoke it directly handler(signum,
    None) (no real signals — hermetic), and assert the spawned thread called request_shutdown within
    ~1 s (_shutdown.is_set() + rec.aborts >= 1). Always install + restore handlers so pytest's own
    signal handling is untouched.
  - COVERAGE (Layer A — shutdown): shutdown() -> rec.shutdowns==1; idempotent (2 calls -> 1);
    raising recorder -> no re-raise (log only); stop/toggle/request_shutdown STILL shutdowns==0
    (the existing tests already assert this — just confirm they still pass). (Layer B — signals):
    install registers a handler for SIGTERM+SIGINT (getsignal is ours, not SIG_DFL); restore()
    reinstalls previous; invoking the handler spawns a thread -> _shutdown.is_set()+abort within ~1 s;
    a second invocation while _shutdown set spawns no further abort (idempotent-vs-reentry); custom
    signals= honored (e.g. (SIGUSR1,)).
  - DO NOT: import RealtimeSTT/torch; send real SIGTERM/SIGINT in unit tests (use SIGUSR1 or invoke
    the handler directly); edit S1/S2/S3 test bodies; depend on XDG_RUNTIME_DIR; sleep() gratuitously
    (use _wait_for).

Task 3: VALIDATE — run the Validation Loop L1–L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M4.T2.S2: clean-shutdown wiring (VoiceTypingDaemon.shutdown + SIGTERM/SIGINT handlers)".
```

#### Task 1a edit — `voice_typing/daemon.py` import block

**Case A — S1-of-T2 has merged (json/os/select/socket present):**
```
oldText:
import select
import socket
newText:
import select
import signal
import socket
```
**Case B — S1-of-T2 has NOT merged (no json/os/select/socket; current post-S3 block):**
```
oldText:
import logging
import threading
newText:
import logging
import signal
import threading
```
(Inspect the live block at Task 0 and apply the matching case. If neither anchor is unique, insert
`import signal` in alphabetical position among the existing `import X` lines. Never reorder.)

#### Task 2 SOURCE — `tests/test_daemon.py` APPEND section (skeleton; expand to ~8–10 tests)

```python
# ===========================================================================
# P1.M4.T2.S2 — clean-shutdown wiring: VoiceTypingDaemon.shutdown() + SIGTERM/SIGINT handlers
# (ADDITIVE — everything above is S1/S2/S3/(S1-of-T2); do not change it.)
# ===========================================================================
# Reuses _make_daemon() / _StubRecorder / _wait_for from earlier in this file.
import signal as _signal


# --- Layer A: VoiceTypingDaemon.shutdown() ------------------------------------------------

def test_shutdown_calls_recorder_shutdown_once():
    d, fb, rec, be = _make_daemon()
    assert rec.shutdowns == 0
    d.shutdown()
    assert rec.shutdowns == 1


def test_shutdown_is_idempotent():
    d, fb, rec, be = _make_daemon()
    d.shutdown(); d.shutdown(); d.shutdown()
    assert rec.shutdowns == 1                       # our _shutdown_done flag (RealtimeSTT's is also idempotent)


class _RaisingRecorder(_StubRecorder):
    """shutdown() always raises — proves daemon.shutdown() is defensive (best-effort)."""
    def shutdown(self):
        self.shutdowns += 1
        raise RuntimeError("boom (test)")


def test_shutdown_swallows_recorder_failure(caplog):
    d, fb, rec, be = _make_daemon(recorder=_RaisingRecorder())
    with caplog.at_level(logging.ERROR, logger="voice_typing.daemon"):
        d.shutdown()                               # must NOT raise
    assert rec.shutdowns == 1                       # it was called once
    assert any("recorder.shutdown() failed" in r.getMessage() for r in caplog.records)


def test_stop_and_request_shutdown_still_never_shutdown():
    # Regression proof: shutdown() is a NEW path; stop/toggle/request_shutdown keep NOT tearing down.
    d, fb, rec, be = _make_daemon()
    d.start(); d.stop(); d.toggle(); d.request_shutdown()
    assert rec.shutdowns == 0


# --- Layer B: install_shutdown_signal_handlers() -------------------------------------------

def _install(daemon, **kw):
    return daemon_module().install_shutdown_signal_handlers(daemon, **kw)


def daemon_module():
    from voice_typing import daemon as _d
    return _d


def test_install_registers_handler_for_sigterm_and_sigint():
    d, _, _, _ = _make_daemon()
    prev_term = _signal.getsignal(_signal.SIGTERM)
    prev_int = _signal.getsignal(_signal.SIGINT)
    try:
        restore = _install(d)
        assert _signal.getsignal(_signal.SIGTERM) is not _signal.SIG_DFL
        assert _signal.getsignal(_signal.SIGINT) is not _signal.SIG_DFL
        restore()
        assert _signal.getsignal(_signal.SIGTERM) is prev_term
        assert _signal.getsignal(_signal.SIGINT) is prev_int
    finally:
        _signal.signal(_signal.SIGTERM, prev_term)
        _signal.signal(_signal.SIGINT, prev_int)


def test_handler_invocation_requests_shutdown_via_spawned_thread():
    d, _, rec, _ = _make_daemon()
    prev = _signal.getsignal(_signal.SIGUSR1)
    try:
        _install(d, signals=(_signal.SIGUSR1,))
        handler = _signal.getsignal(_signal.SIGUSR1)
        handler(_signal.SIGUSR1, None)             # invoke directly (no real signal) — spawns a thread
        assert _wait_for(lambda: d._shutdown.is_set() and rec.aborts >= 1, timeout=2.0), \
            (d._shutdown.is_set(), rec.aborts)
    finally:
        _signal.signal(_signal.SIGUSR1, prev)


def test_handler_is_idempotent_vs_reentry():
    d, _, rec, _ = _make_daemon()
    prev = _signal.getsignal(_signal.SIGUSR1)
    try:
        _install(d, signals=(_signal.SIGUSR1,))
        handler = _signal.getsignal(_signal.SIGUSR1)
        handler(_signal.SIGUSR1, None)
        assert _wait_for(lambda: d._shutdown.is_set(), timeout=2.0)
        aborts_after_first = rec.aborts
        handler(_signal.SIGUSR1, None)             # _shutdown already set -> no new thread
        handler(_signal.SIGUSR1, None)
        _time.sleep(0.1)
        assert rec.aborts == aborts_after_first    # no further abort spawned
    finally:
        _signal.signal(_signal.SIGUSR1, prev)


def test_install_custom_signals_set_honored():
    d, _, _, _ = _make_daemon()
    prev = _signal.getsignal(_signal.SIGUSR2)
    try:
        restore = _install(d, signals=(_signal.SIGUSR2,))
        assert _signal.getsignal(_signal.SIGUSR2) is not _signal.SIG_DFL
        assert _signal.getsignal(_signal.SIGTERM) is _signal.SIG_DFL or \
               _signal.getsignal(_signal.SIGTERM) is prev   # SIGTERM NOT touched (custom set)
        restore()
    finally:
        _signal.signal(_signal.SIGUSR2, prev)
```

### Integration Points

```yaml
ENTRY POINT (P1.M4.T3.S1 — NOT this task; T2.S2 only documents the contract):
  - main() will (in the MAIN thread):
      cfg = load_config(...); fb = Feedback(cfg.feedback)
      d = VoiceTypingDaemon(cfg, fb)
      srv = ControlServer(d, on_quit=d.shutdown)      # quit -> request_shutdown() then recorder.shutdown()
      srv.start()
      restore_signals = install_shutdown_signal_handlers(d)   # SIGTERM/SIGINT -> spawn-thread -> request_shutdown
      try:
          d.run()                                     # blocks until shutdown requested (quit or signal)
      finally:
          d.shutdown()                                # idempotent: no-op if on_quit already did it (covers signal path)
          srv.stop()                                  # close socket + unlink (S1) — NEVER from on_quit (self-join)
          restore_signals()
      return 0

SYSTEMD (P1.M6.T1.S2 — NOT this task):
  - Restart=on-failure sends SIGTERM to stop the old instance -> the SIGTERM handler -> request_shutdown
    -> run() exits -> main() finally d.shutdown() (release VRAM) -> clean restart. The new instance can
    bind the socket (S1 unlinks stale .sock) + allocate VRAM without double-booking.

CONFIG:
  - none. No new config field (signal set is fixed at SIGTERM+SIGINT; teardown is unconditional).
    Do NOT edit config.py/config.toml.

SOCKET:
  - none new. S1's ControlServer.stop() already closes + unlinks; T3.S1 calls it from main()'s finally.
    T2.S2 does NOT touch the socket.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
# Per-file syntax check after the edit:
.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py

# Import purity (the hard gate): importing daemon must NOT pull RealtimeSTT/torch/ctranslate2.
.venv/bin/python -c "
import sys; import voice_typing.daemon
bad=[m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
assert not bad, f'import purity broken: {bad}'
from voice_typing.daemon import VoiceTypingDaemon, install_shutdown_signal_handlers
assert callable(getattr(VoiceTypingDaemon, 'shutdown', None))
assert callable(install_shutdown_signal_handlers)
print('imports + symbols + purity OK')
"

# Optional lint/format (ruff optional at /home/dustin/.local/bin/ruff; mypy NOT installed):
/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py 2>/dev/null || true
# Expected: zero errors. Fix anything reported before proceeding.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing
# The new shutdown/signal section:
.venv/bin/python -m pytest tests/test_daemon.py -v -k "shutdown or signal or handler or reentry"
# Expected: all green (~8-10 tests: shutdown x4 + signal-handler x4).

# Regression — the stop/request_shutdown shutdowns==0 invariants must STILL hold:
.venv/bin/python -m pytest tests/test_daemon.py -v -k "stop_never_calls_recorder_shutdown or request_shutdown"

# Full suite (regression — S1/S2/S3 unchanged; +S1-of-T2 when merged):
.venv/bin/python -m pytest tests/ -q
# Expected: ~155+ passed (146 S1+S2+S3 + ~13 S1-of-T2 + ~9 new), 0 failed.
```

### Level 3: Integration Testing (the safe teardown ordering, with the stub recorder)

```bash
cd /home/dustin/projects/voice-typing
# Simulate the T3.S1 main() flow with a stub recorder: quit-style on_quit + signal-style spawn-thread
# both reach recorder.shutdown() exactly once, and run() exits cleanly.
.venv/bin/python - <<'PY'
import threading, time
from voice_typing import daemon as D

class StubRec:
    def __init__(self): self.text_calls=0; self.aborts=0; self.shutdowns=0
    def text(self, cb=None): self.text_calls+=1; return ""
    def set_microphone(self, on=True): pass
    def abort(self): self.aborts+=1
    def shutdown(self): self.shutdowns+=1

from voice_typing.config import VoiceTypingConfig
class FakeFB:
    def __init__(self): self.finals=[]; self.ls=[]
    def record_final(self,t): self.finals.append(t)
    def set_listening(self,b): self.ls.append(b)
    def update_partial(self,t): pass
    def set_phase(self,p): pass

d = D.VoiceTypingDaemon(VoiceTypingConfig(), FakeFB(), recorder=StubRec())
# (a) quit path: on_quit=d.shutdown fires AFTER request_shutdown returned (text() already broken)
d.request_shutdown()       # sets _shutdown + abort (stub: instant)
d.shutdown()               # on_quit equivalent
print("after quit-path shutdown: shutdowns =", d._recorder.shutdowns)   # 1

# (b) signal path: handler spawns a thread -> request_shutdown
d2 = D.VoiceTypingDaemon(VoiceTypingConfig(), FakeFB(), recorder=StubRec())
restore = D.install_shutdown_signal_handlers(d2, signals=(__import__('signal').SIGUSR1,))
import signal
handler = signal.getsignal(signal.SIGUSR1)
handler(signal.SIGUSR1, None)               # simulate SIGTERM
time.sleep(0.5)
print("after signal: _shutdown set =", d2._shutdown.is_set(), "aborts =", d2._recorder.aborts)
d2.shutdown()                                # main() finally equivalent -> idempotent
print("after finally shutdown: shutdowns =", d2._recorder.shutdowns)    # 1
restore()
print("OK")
PY
# Expected:
#   after quit-path shutdown: shutdowns = 1
#   after signal: _shutdown set = True aborts >= 1
#   after finally shutdown: shutdowns = 1
#   OK
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Reentrancy + robustness: hammer the handler from many "signals" at once; assert no thread spam and
# exactly one teardown (idempotent-vs-reentry), and that a raising recorder never propagates.
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import signal, threading, time
from voice_typing import daemon as D
from voice_typing.config import VoiceTypingConfig
class StubRec:
    def __init__(self): self.aborts=0; self.shutdowns=0
    def text(self, cb=None): return ""
    def set_microphone(self, on=True): pass
    def abort(self): self.aborts+=1
    def shutdown(self): self.shutdowns+=1
class FakeFB:
    def record_final(self,t): pass
    def set_listening(self,b): pass
    def update_partial(self,t): pass
    def set_phase(self,p): pass
d = D.VoiceTypingDaemon(VoiceTypingConfig(), FakeFB(), recorder=StubRec())
restore = D.install_shutdown_signal_handlers(d, signals=(signal.SIGUSR1,))
h = signal.getsignal(signal.SIGUSR1)
def poke(): 
    for _ in range(20): h(signal.SIGUSR1, None)
ts=[threading.Thread(target=poke) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
time.sleep(0.5)
print("concurrent 80 pokes -> aborts =", d._recorder.aborts, "(bounded; _shutdown gate)")
restore()
print("OK")
PY
# Expected: concurrent 80 pokes -> aborts = 1  (the _shutdown.is_set() gate prevents thread spam)
#           OK
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 validation levels completed successfully.
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~155+ passed; S1/S2/S3 test bodies UNCHANGED).
- [ ] `.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py` clean.
- [ ] Import purity: `RealtimeSTT`/`torch`/`ctranslate2` NOT in `sys.modules` after `import
      voice_typing.daemon`.
- [ ] `ruff check` (optional) reports zero errors on the changed files.

### Feature Validation

- [ ] All success criteria from "What" met (a–h).
- [ ] `shutdown()` calls `recorder.shutdown()` exactly once; idempotent; defensive (no re-raise).
- [ ] `stop()`/`toggle()`/`request_shutdown()` STILL never call `recorder.shutdown()` (regression).
- [ ] SIGTERM/SIGINT handler spawns a thread → `request_shutdown()` within ~1 s; idempotent-vs-reentry.
- [ ] Level 3 (quit + signal → exactly one teardown) and Level 4 (concurrent pokes → no spam) pass.
- [ ] The T3.S1 main() contract (Integration Points) is documented and internally consistent.

### Code Quality Validation

- [ ] Follows existing codebase patterns (stubs, tmp_path/monkeypatch, `_wait_for`, additive-only
      edits, module-level helpers, `logger = logging.getLogger(__name__)`, defensive try/except).
- [ ] File placement matches the desired tree (no new module; shutdown() on VoiceTypingDaemon;
      install_shutdown_signal_handlers at module end).
- [ ] Anti-patterns avoided (no abort/shutdown from the signal handler; no __init__ edit; no
      srv.stop() from on_quit; no scope creep into main/ControlSystem/systemd).
- [ ] No new dependencies (stdlib `signal` only); pyproject.toml/uv.lock untouched.

### Documentation & Deployment

- [ ] Code is self-documenting (clear docstrings on shutdown() + install_shutdown_signal_handlers
      explaining the WHY: idempotent+defensive teardown, spawn-thread-not-abort-from-handler, the
      "no orphaned workers" guarantee).
- [ ] No new env vars or config.
- [ ] Logs are informative (signal received INFO; recorder.shutdown() complete INFO; teardown-failure
      logged at EXCEPTION level but swallowed).

---

## Anti-Patterns to Avoid

- ❌ Don't call `recorder.abort()` or `recorder.shutdown()` from the signal handler body — both run in
  the main thread and would re-enter the blocked `text()` (abort blocks on `was_interrupted` set by
  `text()`; shutdown joins the worker threads the main thread is inside) → deadlock (CPython #121649).
  Spawn a daemon thread → `request_shutdown()` instead.
- ❌ Don't fold `recorder.shutdown()` into `request_shutdown()` or `stop()`/`_disarm()` — those are
  used on toggle/stop where models must stay resident; `shutdown()` is the quit/exit-only teardown.
- ❌ Don't edit `__init__` to add `self._shutdown_done` — use `getattr(self, "_shutdown_done", False)`
  inside `shutdown()` so `__init__` (owned by M4.T1.S1/S2/S3) is untouched.
- ❌ Don't call `ControlServer.stop()` from `on_quit` — it joins the accept thread, and `on_quit` runs
  on a worker OF that thread → self-join-deadlock. `srv.stop()` runs in `main()`'s finally (T3.S1).
- ❌ Don't rely on Python's default SIGTERM — it's immediate process death (no cleanup) → orphaned
  `mp.Process` workers + leaked VRAM. Install the handler.
- ❌ Don't send real SIGTERM/SIGINT in unit tests (disturbs pytest's own handling); use SIGUSR1/SIGUSR2
  or invoke the captured handler directly, and always `restore()` in a `finally`.
- ❌ Don't re-raise from `shutdown()` on a recorder failure — teardown is best-effort; log and swallow.
- ❌ Don't build `main()`/`ControlServer`/systemd unit/`ctl.py` — those are T3.S1/S1-of-T2/T6/T5.

---

## Confidence Score

**9/10** — one-pass implementation success is highly likely. The complete, verified `shutdown()` +
`install_shutdown_signal_handlers()` source is pinned above (validated against the live `daemon.py`
post-S3 state + the installed RealtimeSTT 1.0.2 `core/shutdown.py` / `core/lifecycle.py` /
`core/transcription_api.py`). The single highest-risk detail — "don't call abort()/shutdown() from the
signal handler; spawn a thread instead" — is proven by reading the RealtimeSTT source (`abort()` blocks
on `was_interrupted`, set only by the main thread's `text()`) and corroborated by CPython #121649. The
two residual risks: (1) the exact import-block text after S1-of-T2 merges — mitigated by the Task 1a
dual-case anchor (Case A if json/os/select/socket present, Case B otherwise); (2) `threading.Thread()`
spawn-from-signal-handler touching `_active_limbo_lock` — low (the main thread blocked in `text()` does
not hold it) and the standard pattern. The validation gates (py_compile, import-purity grep, pytest,
the Level 3/4 integration scripts asserting exactly-one-teardown + no-thread-spam) are executable as
written and catch regressions immediately.
