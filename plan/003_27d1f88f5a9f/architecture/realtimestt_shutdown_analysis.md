# RealtimeSTT Shutdown Analysis — Root Cause of the ~90s Wedge

## Source version
`realtimestt[faster-whisper,silero-vad]` v1.0.2, installed in `.venv/lib/python3.12/site-packages/RealtimeSTT/`

## Process/Thread model (verified from source)

RealtimeSTT's `AudioToTextRecorder` spawns the following at construction:

| Entity | Type | Created in | Runs |
|--------|------|-----------|------|
| `transcript_process` | `mp.Process` (spawn) | `initialization.py:397` via `start_recorder_worker()` | `run_transcription_worker()` — final-pass transcription (loads distil-large-v3) |
| `reader_process` | `mp.Process` (spawn) | `initialization.py:433` via `start_recorder_worker()` | `run_audio_data_worker()` — PyAudio capture + audio queue |
| `recording_thread` | daemon `threading.Thread` | `initialization.py:614` | Recording loop (VAD + segment management) |
| `realtime_thread` | daemon `threading.Thread` | `initialization.py:621` | Realtime partial transcription loop |
| `ParentPipe._worker_thread` | daemon `threading.Thread` | `safepipe.py:~50` | Serialized pipe I/O for transcript_process communication |
| `stdout_thread` | daemon `threading.Thread` | `initialization.py:639` | stdout redirect from spawned workers |
| `shutdown_lock` | `threading.Lock` | `initialization.py:263` | Serializes `shutdown_recorder()` |

**Key**: `start_recorder_worker()` uses `mp.set_start_method("spawn")` (safepipe.py:14), so both processes are fully separate — they have their own CUDA context and GPU memory.

## shutdown_recorder() — exact sequence (core/shutdown.py)

```python
def shutdown_recorder(recorder):
    with recorder.shutdown_lock:
        if recorder.is_shut_down:
            return
        # Set shutdown flags FIRST
        recorder.is_shut_down = True
        recorder.continuous_listening = False
        recorder.start_recording_event.set()
        recorder.stop_recording_event.set()
        recorder.shutdown_event.set()
        recorder.is_recording = False
        recorder.is_running = False

        # 1. recording_thread — NO TIMEOUT
        if recorder.recording_thread:
            recorder.recording_thread.join()          # ← CAN HANG INDEFINITELY

        # 2. reader_process — 10s timeout + terminate
        if recorder.use_microphone.value:
            recorder.reader_process.join(timeout=10)  # bounded 10s
            if recorder.reader_process.is_alive():
                recorder.reader_process.terminate()   # force kill

        # 3. transcript_process — 10s timeout + terminate
        if recorder.transcript_process:
            recorder.transcript_process.join(timeout=10)  # bounded 10s
        if recorder.transcript_process and recorder.transcript_process.is_alive():
            recorder.transcript_process.terminate()       # force kill

        # 4. Close pipe
        if recorder.parent_transcription_pipe:
            recorder.parent_transcription_pipe.close()

        # 5. realtime_thread — NO TIMEOUT
        if recorder.realtime_thread:
            recorder.realtime_thread.join()           # ← CAN HANG INDEFINITELY

        # 6. Model cleanup
        if recorder.enable_realtime_transcription:
            if recorder.realtime_transcription_model:
                del recorder.realtime_transcription_model
                recorder.realtime_transcription_model = None
        gc.collect()
```

## Root cause of the ~90s hang

**The two daemon-thread `.join()` calls without timeouts (steps 1 and 5) are the root cause.**

- `recording_thread.join()` — NO timeout. If the recording loop is blocked on a non-cancellable operation (e.g., `queue.get()` without timeout, a blocking VAD model inference call, or a lock held by another thread), this join hangs forever.
- `realtime_thread.join()` — NO timeout. Same risk: if the realtime transcription loop is mid-inference on the GPU or blocked on a queue, this join blocks indefinitely.

While `shutdown_event.set()` IS called before the joins (so the threads should eventually see it and exit), a thread that is *already blocked inside a C extension or blocking queue call* at the moment `shutdown_event.set()` fires won't re-check the event until that call returns. On CUDA, a single Whisper inference on distil-large-v3 can take 1-5+ seconds, and if the thread re-enters the loop and hits another blocking call, it may not see the event for a long time.

The 90s exactly matches systemd's default `TimeoutStopSec=90s`. systemd sends SIGTERM → the daemon's signal handler spawns a shutdown thread → `daemon.shutdown()` → `recorder.shutdown()` → `shutdown_recorder()` hangs at a `.join()` → 90s passes → systemd sends SIGKILL.

## Mitigation: bounded teardown

Wrap the entire `recorder.shutdown()` call in a **hard timeout thread**. If it doesn't complete within the budget (e.g., 15s), force-clean the spawn-started processes so VRAM is actually released:

```python
def _bounded_shutdown(self, timeout: float = 15.0) -> None:
    """Shutdown recorder with a hard timeout + force-cleanup."""
    done = threading.Event()
    
    def _do_shutdown():
        try:
            self._recorder.shutdown()
        except Exception:
            pass
        finally:
            done.set()
    
    t = threading.Thread(target=_do_shutdown, daemon=True)
    t.start()
    
    if not done.wait(timeout=timeout):
        # Timeout exceeded — force-clean
        logger.warning("recorder.shutdown() exceeded %.1fs; force-cleaning", timeout)
        try:
            if self._recorder.transcript_process and self._recorder.transcript_process.is_alive():
                self._recorder.transcript_process.terminate()
        except Exception:
            pass
        try:
            if self._recorder.reader_process and self._recorder.reader_process.is_alive():
                self._recorder.reader_process.terminate()
        except Exception:
            pass
        # Daemon threads (recording_thread, realtime_thread) will die with the process;
        # we can't kill them, but they're daemon=True so they don't block exit.
        # Mark shut_down so a future idempotent call is a no-op.
        try:
            self._recorder.is_shut_down = True
        except Exception:
            pass
        # Delete model references to release VRAM
        try:
            self._recorder.realtime_transcription_model = None
        except Exception:
            pass
```

**Why this works:**
1. The spawn-started processes (`transcript_process`, `reader_process`) hold the GPU VRAM (CUDA contexts are per-process under spawn). Terminating them releases VRAM immediately.
2. The daemon threads (`recording_thread`, `realtime_thread`) cannot be killed, but they're daemon=True, so they die when the process exits — they don't block process termination.
3. Setting `is_shut_down = True` makes any future `.shutdown()` call idempotent (it returns early).
4. Deleting the realtime model reference helps Python GC reclaim host-side model state.

**systemd unit**: add `TimeoutStopSec=15` so systemd doesn't wait the full 90s. The daemon's own bounded teardown makes this safe.
