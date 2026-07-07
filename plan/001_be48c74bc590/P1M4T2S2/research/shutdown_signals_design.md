# Research — P1.M4.T2.S2: quit / clean-shutdown wiring (recorder.shutdown + signals)

Scope: wire the **full daemon teardown** — `recorder.shutdown()` (release GPU workers), SIGTERM/
SIGINT → clean path, no orphaned model-worker processes. Consumes `ControlServer` + `on_quit` hook
from P1.M4.T2.S1 (in flight, treated as a contract) and the existing `VoiceTypingDaemon.request_
shutdown()` / `abort()` from P1.M4.T1.S2.

All findings below were verified against the **installed** RealtimeSTT 1.0.2 source
(`.venv/lib/python3.12/site-packages/RealtimeSTT/`) and CPython 3.12 — this machine's truth.

---

## §1. The teardown surface that already exists (do NOT rebuild)

`voice_typing/daemon.py` (post-S3, pre-S1-of-T2; 146 tests green) already has:

- `VoiceTypingDaemon.request_shutdown()` → `self._shutdown.set()` + `with self._lock:
  self._recorder.abort()`. **Blocks until `abort()` returns** (see §3). Does NOT call
  `recorder.shutdown()` (the S2 test `test_request_shutdown_..._not_shutdown` asserts `shutdowns==0`).
- `VoiceTypingDaemon._disarm()` (stop/toggle) → `set_microphone(False)` + `abort()` — models stay
  resident (PRD §4.2 construct-once). NEVER shutdown() here.
- `self._shutdown: threading.Event` (run() loop gate), `self._lock` (serializes arm/disarm/abort).
- `_StubRecorder` in `tests/test_daemon.py` already implements `def shutdown(self): self.shutdowns += 1`
  AND `abort()`/`set_microphone()`/`text()` — **reuse it** for the shutdown() unit tests.

P1.M4.T2.S1 (parallel, contract) adds `ControlServer` with an **`on_quit` hook**: `_dispatch("quit")`
calls `self._daemon.request_shutdown()` **then** `self._on_quit()` (if set), then replies
`{"ok":true,"shutting_down":true}`. S1's `ControlServer.stop()` closes the listening socket, joins the
accept thread (≤2 s), and **unlinks the socket file**. T2.S2 does NOT touch ControlServer.

So the **only** missing pieces are: (a) a sanctioned `recorder.shutdown()` teardown primitive on the
daemon, and (b) SIGTERM/SIGINT → clean-path handlers. That is T2.S2.

---

## §2. `recorder.shutdown()` — what it actually releases (the "no orphaned workers" guarantee)

`RealtimeSTT/core/shutdown.py` `shutdown_recorder(recorder)` (called by `AudioToTextRecorder.shutdown()`):

```python
with recorder.shutdown_lock:
    if recorder.is_shut_down:           # IDEMPOTENT — safe to call twice
        return
    recorder.is_shut_down = True
    recorder.continuous_listening = False
    recorder.start_recording_event.set() # wake wait_audio()/text() callers
    recorder.stop_recording_event.set()
    recorder.shutdown_event.set()
    recorder.is_running = False
    recorder.recording_thread.join()             # in-process thread
    if recorder.reader_process:                  # multiprocessing.Process (the mic reader)
        recorder.reader_process.join(timeout=10)
        if recorder.reader_process.is_alive():
            recorder.reader_process.terminate()  # SIGKILL the child
    if recorder.transcript_process:              # multiprocessing.Process (the ctranslate2/whisper worker — HOLDS GPU VRAM)
        recorder.transcript_process.join(timeout=10)
        if recorder.transcript_process.is_alive():
            recorder.transcript_process.terminate()
    recorder.parent_transcription_pipe.close()
    if recorder.realtime_thread: recorder.realtime_thread.join()
    if recorder.realtime_transcription_model: del recorder.realtime_transcription_model
    gc.collect()
```

Confirmed in `RealtimeSTT/core/initialization.py`: `transcript_process` + `reader_process` are
**`mp.Process`** started with `mp.set_start_method("spawn")` (lines 354–355, 397, 433). spawn-started
children are **independent OS processes** — if the parent dies without calling `shutdown()`, they
**ORPHAN** (the transcript_process keeps holding GPU VRAM; the reader_process keeps the mic device).
This is exactly PRD §4.2/contract "Ensure no orphaned model worker processes."

**Implications:**
- `recorder.shutdown()` is the ONLY sanctioned full teardown (PRD §4.2; item contract point 1).
- It is **idempotent** (`is_shut_down` + `shutdown_lock`) → safe to call from BOTH the quit `on_quit`
  hook AND `main()`'s `finally` block (T3.S1). Belt-and-suspenders.
- It is the thing systemd `Restart=on-failure` (P1.M6.T1.S2) needs the OLD instance to have run before
  the new one starts, else VRAM is double-booked.

---

## §3. The threading trap: `abort()` BLOCKS — never call it from a main-thread signal handler

`RealtimeSTT/core/lifecycle.py` `abort_recording(recorder)` (called by `recorder.abort()`):

```python
recorder.interrupt_stop_event.set()                 # mp.Event.set() — non-blocking
if recorder.state != "inactive":
    recorder.was_interrupted.wait()                  # *** BLOCKS ***
    set_recorder_state(recorder, "transcribing")
recorder.was_interrupted.clear()
if recorder.is_recording: recorder.stop()
```

`was_interrupted` is set ONLY by `text()` (`core/transcription_api.py`) — AFTER `wait_audio()` returns
and the loop notices `interrupt_stop_event`:

```python
recorder.wait_audio()
if recorder.is_shut_down or recorder.interrupt_stop_event.is_set():
    if recorder.interrupt_stop_event.is_set():
        recorder.was_interrupted.set()      # <-- only the MAIN thread, inside text(), sets this
    return ""
```

So `abort()` blocks until the **main thread** (the one inside `text()`) notices `interrupt_stop_event`
and sets `was_interrupted`. The existing `request_shutdown()` works because it runs on the
**ControlServer worker thread** (a DIFFERENT thread than the main thread blocked in `text()`) — so the
main thread is free to run, see the flag, set `was_interrupted`, and `abort()` returns.

**The deadlock:** CPython runs signal handlers **in the main thread**
(https://docs.python.org/3/library/signal.html : "Python signal handlers are always executed in the
main Python thread of the main interpreter"). If a SIGTERM/SIGINT handler (running in the main thread,
preempting `text()`) calls `recorder.abort()` directly, then `abort()` waits on `was_interrupted` which
can only be set by `text()` — but `text()` is suspended because the signal handler is running on the
same main thread. **Deadlock.** (Confirmed pattern: CPython issue #121649 — "SIGTERM handled in main
thread while `_shutdown_lock` already locked" deadlocks.)

**Resolution for T2.S2:** the signal handler does the absolute minimum and **defers the blocking
`abort()` to a freshly-spawned daemon thread**:

```python
def _handler(signum, frame):
    if daemon._shutdown.is_set():           # already tearing down -> ignore
        return
    logger.info("received signal %s; requesting clean shutdown", signum)
    threading.Thread(target=daemon.request_shutdown,
                     name="voice-typing-signal-shutdown", daemon=True).start()
```

The handler returns immediately; the spawned thread calls `request_shutdown()` (→ `abort()`) from a
**non-main** thread — no re-entrancy with `text()`, so `was_interrupted` can be set, `abort()` returns,
`text()` returns `""`, `run()`'s loop sees `_shutdown`, exits. `main()`'s `finally` then calls
`daemon.shutdown()` (§4) on the main thread (now safely out of `text()`).

**Why spawn-from-signal is safe here:** `threading.Thread.__init__`/`.start()` briefly acquire the
module-global `_active_limbo_lock`. The main thread, while blocked inside `text()`, is in a RealtimeSTT
`Event.wait(0.02)`/pipe-recv loop — it is NOT holding `_active_limbo_lock`. So acquiring it in the
handler does not deadlock. This is the standard "defer blocking work off the signal-handling main
thread" pattern (see OneUptime "graceful shutdown handler in Python"; g-loaded.eu "terminate threads
using signals").

**Rejected alternative** (reaching into `recorder.interrupt_stop_event.set()` directly from the
handler): avoids the thread spawn, but (a) touches a RealtimeSTT **private** attribute (PRD §8
"API drift" risk), (b) `_StubRecorder` lacks it → AttributeError in tests (needs getattr guard), (c)
bypasses the sanctioned `request_shutdown()`/`abort()` path. The thread-spawn approach uses the
PUBLIC, already-tested `request_shutdown()` and is recorder-agnostic. Prefer it.

---

## §4. `on_quit` ordering → safe to call `recorder.shutdown()` from the quit worker thread

S1's `_dispatch("quit")` (contract) is sequential:

```python
self._daemon.request_shutdown()     # BLOCKS until abort() returns (§3)
if self._on_quit is not None:
    self._on_quit()                 # runs AFTER request_shutdown() returns
return {"ok": True, "shutting_down": True}
```

Because `request_shutdown()` blocks until `abort()` returns (i.e. until `text()` has returned and set
`was_interrupted`), **by the time `on_quit` runs, the main thread has already exited `text()`** and is
checking `while not self._shutdown.is_set()` → which is now True → `run()` returns. The main thread is
no longer inside any recorder call. Therefore `on_quit = daemon.shutdown` (which calls
`recorder.shutdown()`) is **safe to run on the ControlServer worker thread** — it joins the recorder's
own internal threads/processes (§2), none of which the main thread holds.

This makes the **quit path self-contained**: `quit` → `request_shutdown` (S1: set flag + abort, main
exits `text()`/`run()`) → `on_quit=daemon.shutdown` (T2.S2: `recorder.shutdown()`, release GPU).
`main()`'s `finally` then only needs `srv.stop()` (close socket + unlink) — which MUST run on the main
thread (it `join`s the accept thread; calling it from `on_quit`, a worker OF that thread, would
self-join-deadlock).

So the full teardown is split across two call sites, both of which T2.S2 enables / documents:

| step                              | who runs it            | where                |
|-----------------------------------|------------------------|----------------------|
| `_shutdown.set()` + `abort()`     | ControlServer worker   | `request_shutdown()` (exists) — quit; OR signal-spawned thread |
| `recorder.shutdown()` (release GPU)| ControlServer worker   | `on_quit = daemon.shutdown` (T3.S1 wires; T2.S2 provides) |
| `recorder.shutdown()` (idempotent) | main thread            | `main()` finally `daemon.shutdown()` (T3.S1) — covers the signal path |
| close socket + unlink             | main thread            | `main()` finally `srv.stop()` (S1 provides) — NEVER from `on_quit` |

Idempotency (§2 `is_shut_down` + our own `_shutdown_done` flag) makes calling `shutdown()` from both
sites correct (first one wins).

---

## §5. Why a SIGTERM handler is MANDATORY (not optional)

- Python's default **SIGINT** → raises `KeyboardInterrupt` in the main thread. RealtimeSTT's `text()`
  and `wait_audio()` CATCH `KeyboardInterrupt`, call `recorder.shutdown()`, and **re-raise**. So a bare
  Ctrl-C during `text()` already runs `recorder.shutdown()` — but only if you're inside `text()` at
  that instant, and the re-raise propagates out of `run()` unless `main()` catches it (fragile).
- Python's default **SIGTERM** → **immediate process termination**. No `KeyboardInterrupt`, no `finally`
  blocks, no `atexit`. **systemd stop/restart sends SIGTERM by default** (PRD §4.9, P1.M6.T1.S2). With
  the default handler, the parent dies and the spawn-started `transcript_process`/`reader_process`
  **ORPHAN** (hold VRAM + mic) → the restarted instance double-books VRAM. **This is the failure mode
  the item contract explicitly forbids.** Hence T2.S2 MUST install a SIGTERM handler → clean path.

The handler must cover BOTH `signal.SIGTERM` (systemd) and `signal.SIGINT` (Ctrl-C / dev runs) and
route them to the SAME clean path (`request_shutdown` → spawn-thread → `main()` finally →
`daemon.shutdown()` + `srv.stop()`), per the contract "same clean path".

---

## §6. Design (what T2.S2 adds to `voice_typing/daemon.py` — 100% additive)

### 6a. `import signal` at module top (one line; S1-of-T2 adds json/os/select/socket concurrently)

Alphabetical position between `select` and `socket`: `... os, select, signal, socket, threading ...`.
No other new import (threading/logging already present).

### 6b. `VoiceTypingDaemon.shutdown()` — new method (NO `__init__` edit; lazy flag via getattr)

```python
def shutdown(self) -> None:
    """Full recorder teardown (PRD §4.2; P1.M4.T2.S2). Idempotent + defensive.

    Calls self._recorder.shutdown() which terminates the spawn-started transcript_process +
    reader_process (releases GPU VRAM + the mic device — the "no orphaned workers" guarantee,
    research §2). IDEMPOTENT: a getattr-guarded flag (no __init__ edit) + RealtimeSTT's own
    is_shut_down guard make double-call (quit on_quit + main() finally) a no-op the second time.
    DEFENSIVE: a recorder.shutdown() failure is logged, NOT re-raised — the daemon is exiting and
    teardown is best-effort (a broken teardown must not mask the original shutdown reason).

    NEVER call this on toggle/stop (models must stay resident). The sanctioned callers are:
      - the quit on_quit hook (after request_shutdown() has broken text(); research §4), and
      - main()'s finally block (after run() returns; covers the signal path).
    Must NOT run while the main thread is inside recorder.text() — request_shutdown()/abort()
    guarantees the main thread has exited text() before this is reached (research §3/§4).
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

### 6c. `install_shutdown_signal_handlers()` — new module function (called from main thread)

```python
def install_shutdown_signal_handlers(
    daemon: "VoiceTypingDaemon",
    *,
    signals: tuple[int, ...] | None = None,
) -> Callable[[], None]:
    """Install SIGTERM/SIGINT handlers that request clean daemon shutdown (PRD §4.2/§4.9; P1.M4.T2.S2).

    systemd stop/restart sends SIGTERM (default → immediate process death, NO Python cleanup →
    orphaned model workers + leaked VRAM, research §5); Ctrl-C sends SIGINT. Both route to the SAME
    clean path. The handler runs in the MAIN thread (CPython signal semantics) and therefore MUST NOT
    call recorder.abort() directly — abort() blocks on was_interrupted.wait(), set only by text() in
    the main thread → deadlock (research §3; CPython #121649). Instead the handler spawns a daemon
    THREAD that calls daemon.request_shutdown() (abort off the main thread = safe); the handler
    returns immediately. The spawned thread breaks text(); run() exits; main()'s finally calls
    daemon.shutdown() + ControlServer.stop() (T3.S1 wires; T2.S2 documents).

    Must be called from the MAIN thread (signal.signal() requires it). Returns a restore() callable
    that reinstalls the previous handlers (tests + clean uninstall). Idempotent-vs-reentry: a second
    signal while _shutdown is already set is ignored (no thread spam).
    """
    sigs = signals if signals is not None else (signal.SIGTERM, signal.SIGINT)
    previous: dict[int, Any] = {}

    def _handler(signum, frame):
        if daemon._shutdown.is_set():
            return  # already tearing down
        logger.info("received signal %s; requesting clean shutdown", signum)
        threading.Thread(
            target=daemon.request_shutdown, name="voice-typing-signal-shutdown", daemon=True
        ).start()

    for s in sigs:
        previous[s] = signal.signal(s, _handler)

    def restore() -> None:
        for s, prev in previous.items():
            signal.signal(s, prev)

    return restore
```

### 6d. The T3.S1 `main()` contract this enables (DOCUMENTED, not built by T2.S2)

```python
def main() -> int:
    cfg = load_config(...)
    fb = Feedback(cfg.feedback)
    d = VoiceTypingDaemon(cfg, fb)
    srv = ControlServer(d, on_quit=d.shutdown)     # quit → recorder.shutdown() (research §4)
    srv.start()
    restore_signals = install_shutdown_signal_handlers(d)
    try:
        d.run()                                    # blocks until shutdown requested
    finally:
        d.shutdown()                               # idempotent: no-op if quit/signal already did it
        srv.stop()                                 # close socket + unlink (S1) — NEVER from on_quit
        restore_signals()
    return 0
```

---

## §7. Test strategy (reuse existing stubs; hermetic; no real signals in unit tests)

Layer A — `VoiceTypingDaemon.shutdown()`:
- A1. `shutdown()` calls `recorder.shutdown()` exactly once → `_StubRecorder.shutdowns == 1`.
- A2. idempotent: `shutdown(); shutdown()` → `shutdowns == 1` (our flag) — reuse `_make_daemon()`.
- A3. defensive: inject a recorder whose `shutdown()` raises → `daemon.shutdown()` does NOT re-raise
      (log only); the daemon exit is unblocked. (A `_RaisingRecorder` stub.)
- A4. `stop()`/`toggle()`/`request_shutdown()` STILL never call `recorder.shutdown()` (the existing
      S2 tests `test_stop_never_calls_recorder_shutdown` + `test_request_shutdown_..._not_shutdown`
      stay green UNCHANGED — regression proof that shutdown() is a NEW, separate path).

Layer B — `install_shutdown_signal_handlers()`:
- B1. registers a handler for SIGTERM+SIGINT: `signal.getsignal(SIGTERM)` is our handler (not SIG_DFL).
- B2. `restore()` reinstalls the previous handlers.
- B3. invoking the handler directly `handler(SIGTERM, None)` spawns a thread that calls
      `daemon.request_shutdown()` → within ~1 s `_shutdown.is_set()` is True and `rec.aborts >= 1`
      (use a real `_make_daemon()` daemon + `_wait_for`).
- B4. a second handler invocation while `_shutdown` is already set does NOT spawn a second abort
      (idempotent-vs-reentry) — assert `rec.aborts` does not grow unboundedly (== 1 after N pokes).
- B5. custom `signals=` honored (e.g. only SIGUSR1) — used to avoid touching real SIGTERM in tests.
- (Optional) B6. a real end-to-end signal poke via `os.kill(os.getpid(), SIGUSR1)` with
      `signals=(SIGUSR1,)` — proves the wire-up; keep it isolated so it can't disturb pytest's own
      signal handling. Mark slow if flaky.

Placement: APPEND a new section to `tests/test_daemon.py` (reuse `_make_daemon`, `_StubRecorder`,
`_wait_for`); OR a focused `tests/test_shutdown_signals.py`. Prefer appending to test_daemon.py to keep
all daemon-lifecycle tests together and reuse the stubs without re-importing. Do NOT edit S1/S2/S3 test
bodies.

NO real RealtimeSTT / NO CUDA / NO real signals (except optional B6) — hermetic + fast.

---

## §8. References (URLs with anchors)

- Python `signal` module — "Python signal handlers are always executed in the main Python thread of
  the main interpreter":
  https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers
- CPython #121649 — deadlock shutting down a ThreadPoolExecutor from inside a SIGTERM handler (the
  lock-held-by-main-thread trap this design avoids): https://github.com/python/cpython/issues/121649
- OneUptime — "How to Build a Graceful Shutdown Handler in Python" (SIGTERM → flag → teardown):
  https://oneuptime.com/blog/post/2025-01-06-python-graceful-shutdown-kubernetes/view
- g-loaded.eu — "How to terminate running Python threads using signals" (defer blocking work off the
  signal handler): https://www.g-loaded.eu/2016/11/24/how-to-terminate-running-python-threads-using-signals/
- StackOverflow — "python SIGTERM handler is not invoked in multiprocessing" (spawned-process orphan
  concern that recorder.shutdown() explicitly resolves):
  https://stackoverflow.com/questions/53852360/python-sigterm-handler-is-not-invoked-in-multiprocessing
- Installed RealtimeSTT 1.0.2 source (authoritative for THIS machine):
  - `.venv/lib/python3.12/site-packages/RealtimeSTT/core/shutdown.py` (shutdown_recorder: terminates
    transcript_process/reader_process; idempotent)
  - `.../core/lifecycle.py` (abort_recording: blocks on was_interrupted.wait())
  - `.../core/transcription_api.py` (text(): sets was_interrupted after wait_audio)
  - `.../core/initialization.py` (transcript_process/reader_process are mp.Process, spawn start method)
