# RealtimeSTT Shutdown Wedge — CONFIRMED Root Cause (P1.M1.T1.S1)

**Verdict (one line):** The ~90s shutdown wedge is an **unbounded `threading.Thread.join()` inside
RealtimeSTT v1.0.2 `shutdown_recorder()`**; the 90s is **systemd's default `TimeoutStopSec=90s`**
(the unit sets none), which fires `SIGKILL` at 90s.

> This is a **sibling** to `realtimestt_shutdown_analysis.md` (the precursor). It corroborates the
> precursor against the *installed* wheel, adds the **ordering / practical-first-blocker**
> determination, records the **systemd-default-90s** link, and hands off to **S2** (bounded
> teardown). **It does not modify any source/config/systemd file** — research only.

---

## 1. Source version & paths

- **Library:** `realtimestt[faster-whisper,silero-vad]` **v1.0.2**, installed in the project venv.
- **Authoritative proof source (the shutdown implementation):**
  `.venv/lib/python3.12/site-packages/RealtimeSTT/core/shutdown.py` — the single function
  `shutdown_recorder(recorder)`.
- **Process/thread model source:**
  `.venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py`
  (and `core/safepipe.py` for the spawn start method).
- **Daemon call site (the place S2 will wrap):** `voice_typing/daemon.py:818-844`
  (`VoiceTypingDaemon.shutdown()`).
- **systemd unit (the 90s source):** `systemd/voice-typing.service` — **no `TimeoutStopSec=`**
  directive.

All claims below are verified verbatim against these installed files (see the Level-3 regression
gates in §8).

---

## 2. Process / thread model (cited from the installed wheel)

| Entity | Type | Created at (installed `initialization.py`) | Daemon? | In `shutdown_recorder()` |
|---|---|---|---|---|
| `transcript_process` | `mp.Process` (**spawn**) | created via `start_recorder_worker(target=run_transcription_worker, …)` in `_initialize_transcription_runtime()` (PRP-cited `:397`) | n/a (process) | `join(timeout=10)` + `terminate()` — **BOUNDED** |
| `reader_process` | `mp.Process` (**spawn**) | created via `start_recorder_worker(target=run_audio_data_worker, …)` in `_start_audio_reader()` (PRP-cited `:433`); gated on `use_microphone.value` | n/a (process) | `join(timeout=10)` + `terminate()` (gated on `use_microphone.value`) — **BOUNDED** |
| `recording_thread` | `threading.Thread` | `_start_worker_threads()`: `recording_thread = threading.Thread(target=run_recording_worker, …)` (PRP-cited `:614`); `.daemon = True` (PRP-cited `:618`) | **yes** | `.join()` — **NO TIMEOUT** |
| `realtime_thread` | `threading.Thread` | `_start_worker_threads()`: `realtime_thread = threading.Thread(target=run_realtime_worker, …)` (PRP-cited `:621`); `.daemon = True` (PRP-cited `:625`) | **yes** | `.join()` — **NO TIMEOUT** |

The `recording_thread`/`realtime_thread` assignments + `.daemon = True` lines, verified verbatim in
`_start_worker_threads()`:

```python
recorder.recording_thread = threading.Thread(target=run_recording_worker, args=(recorder,))
recorder.recording_thread.daemon = True
recorder.recording_thread.start()

recorder.realtime_thread = threading.Thread(target=run_realtime_worker, args=(recorder,))
recorder.realtime_thread.daemon = True
recorder.realtime_thread.start()
```

**Spawn start method:** `mp.set_start_method("spawn")` at `core/safepipe.py:17-19` and again
(defensively) in `core/initialization.py`'s `_configure_multiprocessing_start_method()`. Because the
start method is **spawn**, each `mp.Process` has its **own CUDA context and GPU memory**. This is the
basis for S2's force-cleanup: **terminating the processes releases their VRAM**.

`shutdown_lock` (`threading.Lock`) serializes the whole of `shutdown_recorder()` (the `with
recorder.shutdown_lock:` at the top of the function).

---

## 3. CONFIRMED CLAIMS (the three contract claims, verbatim in `core/shutdown.py`)

The whole function is reproduced verbatim in the precursor analysis. The three load-bearing facts
are confirmed against the installed `core/shutdown.py`:

### (a) `recording_thread.join()` — **NO timeout** ✅ CONFIRMED

`core/shutdown.py:33-34`:
```python
if recorder.recording_thread:
    recorder.recording_thread.join()
```
No `timeout=` argument → **unbounded**.

### (b) `realtime_thread.join()` — **NO timeout** ✅ CONFIRMED

`core/shutdown.py:62-63`:
```python
if recorder.realtime_thread:
    recorder.realtime_thread.join()
```
No `timeout=` argument → **unbounded**.

### (c) Both `mp.Process` joins ARE bounded (`timeout=10` + `terminate()`) ✅ CONFIRMED

`core/shutdown.py:38-42` (reader — **mic-gated**):
```python
if recorder.use_microphone.value:
    recorder.reader_process.join(timeout=10)
    if recorder.reader_process.is_alive():
        recorder.reader_process.terminate()
```

`core/shutdown.py:46-52` (transcript):
```python
if recorder.transcript_process:
    recorder.transcript_process.join(timeout=10)
if recorder.transcript_process and recorder.transcript_process.is_alive():
    recorder.transcript_process.terminate()
```

The installed file contains **exactly two** `join(timeout=10)` and **exactly two** `.terminate()`
calls (Level-3 gate, §8). So the **two process joins are bounded (10s + force terminate)**, and the
**two thread joins are the only unbounded operations** in the shutdown path.

> **Mic-gate note (gotcha #7).** The `reader_process` teardown runs **only** `if
> recorder.use_microphone.value`. Production uses the mic (`use_microphone=True`), so the reader
> step applies in the live daemon; the offline `feed_audio` tests set `use_microphone=False`, so the
> reader step is skipped there. Do **not** read this as "the reader is always torn down".

---

## 4. Shutdown ordering & practical-first-blocker determination

The exact step ordering inside `shutdown_recorder()` (verified in `core/shutdown.py`):

1. Set flags + `shutdown_event.set()` (wakes `wait_audio()` / `text()` callers).
   (`is_shut_down=True`, `continuous_listening=False`, `start_recording_event.set()`,
   `stop_recording_event.set()`, `shutdown_event.set()`, `is_recording=False`, `is_running=False`.)
2. **`recording_thread.join()` — UNBOUNDED ← first reachable blocker.**
3. `reader_process.join(timeout=10)` + `terminate()` — **bounded** (mic-gated).
4. `transcript_process.join(timeout=10)` + `terminate()` — **bounded**.
5. `parent_transcription_pipe.close()`.
6. **`realtime_thread.join()` — UNBOUNDED ← second blocker; only reached after step 2 returns.**
7. `del realtime_transcription_model` + `gc.collect()` (gated on `enable_realtime_transcription`).

**Practical-first-blocker determination.** Because steps 3/4/5 are bounded, the wedge is
**guaranteed** to be at **step 2 (`recording_thread.join()`)** or **step 6
(`realtime_thread.join()`)** — the only unbounded calls. By ordering, **step 2 is the first
candidate**: the call sequence reaches `recording_thread.join()` before any bounded step and before
`realtime_thread.join()`. Step 6 is reached **only if step 2 returns**.

**What source analysis can and cannot pin.** Static source analysis proves the *category* of the
blocker — an unbounded `threading.Thread.join()` — but **cannot pin which thread blocks in a given
run** without a live timed-log probe (see §6). This is **not a problem for S2** (§7): S2 wraps the
*whole* `recorder.shutdown()` in a hard timeout and force-terminates the processes regardless of
which internal join hangs.

---

## 5. Daemon-side call site: **no bound added**

`VoiceTypingDaemon.shutdown()` at `voice_typing/daemon.py:818-844` calls `self._recorder.shutdown()`
with **no timeout**:

```python
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

This call site is:
- **Idempotent** — a `getattr(self, "_shutdown_done", False)` guard plus RealtimeSTT's own
  `is_shut_down` guard (the early `if recorder.is_shut_down: return` at the top of
  `shutdown_recorder()`) make a double call a no-op the second time.
- **Defensive** — a `recorder.shutdown()` failure is logged, not re-raised.
- **Unbounded** — it adds **no time bound**. A hang inside `recorder.shutdown()` propagates
  indefinitely through `daemon.shutdown()`. **This is the function S2 will wrap with a hard timeout;
  S1 documents it only.**

---

## 6. The systemd link: **90s = default `TimeoutStopSec`** (not a RealtimeSTT constant)

`systemd/voice-typing.service` defines `ExecStartPre`, `ExecStart=.../launch_daemon.sh`,
`Restart=on-failure`, `RestartSec=2`, and **no `TimeoutStopSec=` directive** (Level-3 gate: `grep
TimeoutStopSec systemd/voice-typing.service` → none).

→ systemd applies its **default `TimeoutStopSec=90s`**: on stop it sends `SIGTERM`, and if the unit
hasn't stopped within **90s** it sends **`SIGKILL`**. **There is no 90s constant anywhere in the
RealtimeSTT source**; the 90s comes entirely from this systemd default.

**This exactly matches the observed wedge:** `voicectl quit` (or `systemctl --user stop`) → `SIGTERM`
→ daemon signal handler → `daemon.shutdown()` → `recorder.shutdown()` → `shutdown_recorder()` blocks
at an unbounded `threading.Thread.join()` (step 2 or step 6) → ~90s elapse → systemd
`TimeoutStopSec=90s` default fires → **`SIGKILL`** → `Failed with result 'timeout'`. The process is
then killed by the supervisor; the spawn processes (which hold the VRAM) die with it.

**End-to-end causal chain:**
```
voicectl quit / systemctl stop
   └─> SIGTERM
         └─> daemon signal handler / main() finally
               └─> VoiceTypingDaemon.shutdown()            (daemon.py:818-844; no timeout)
                     └─> self._recorder.shutdown()
                           └─> shutdown_recorder()         (core/shutdown.py; shutdown_lock held)
                                 └─> blocks at unbounded   recording_thread.join()  (step 2)
                                                            OR realtime_thread.join() (step 6)
                                       └─> ~90s elapse
                                             └─> systemd TimeoutStopSec=90s (default) ──> SIGKILL
```

This link justifies **T2.S1** lowering the unit's `TimeoutStopSec` to ~15s once S2 gives the daemon a
bounded teardown that completes well inside 15s.

---

## 7. Handoff to S2 (P1.M1.T1.S2 — bounded teardown)

S2 owns the implementation; this section only confirms the *premise* and states the handoff crisply.
S2's fix is the **correct shape regardless of which internal join hangs**, because:

1. **Wrap the WHOLE `recorder.shutdown()` in a hard timeout thread** (the unbounded work is inside
   `shutdown_recorder()`, reached via `self._recorder.shutdown()`). A worker thread runs the call;
   the caller `done.wait(timeout=…)`; on timeout, proceed to force-cleanup. (A sketch already exists
   in the precursor analysis — S2 owns the real implementation.)
2. **On timeout, force-terminate the spawn processes** (`transcript_process` and `reader_process`).
   These are the **VRAM holders** (spawn → per-process CUDA context, §2), so terminating them is the
   real release strategy.
3. **Set `is_shut_down = True`** so a future `recorder.shutdown()` is idempotent (early return).
4. **Do NOT try to kill the daemon threads** (`recording_thread`, `realtime_thread`). They are
   `.daemon = True` (§2), Python offers no `thread.kill()`, and they die **with the process** when it
   exits — they neither need nor can receive explicit killing. S2's force-cleanup terminates the
   **processes** (VRAM) and lets the daemon threads die with the process.

**Key handoff fact:** S2 does **not** depend on knowing *which* thread blocks (§4). It bounds the
entire call and force-terminates the processes unconditionally on timeout.

---

## 8. Validation gates (regression-proof against the installed source)

Level-3 regression gates, run against the installed wheel at write time — all **PASS**:

```text
# recording_thread.join() has NO timeout in the installed source
$ grep -A1 recording_thread .venv/.../core/shutdown.py | grep -E 'recording_thread\.join\(\)$'
            recorder.recording_thread.join()      →  L3a PASS

# realtime_thread.join() has NO timeout
$ grep -A1 realtime_thread  .venv/.../core/shutdown.py | grep -E 'realtime_thread\.join\(\)$'
            recorder.realtime_thread.join()      →  L3b PASS

# both processes join(timeout=10) + terminate()
$ grep -c 'join(timeout=10)' .venv/.../core/shutdown.py  →  2   (expect 2)
$ grep -c '\.terminate()'    .venv/.../core/shutdown.py  →  2   (expect 2)

# systemd unit sets no TimeoutStopSec → default 90s applies
$ grep TimeoutStopSec systemd/voice-typing.service       →  (none)
```

If a future `RealtimeSTT` bump changes any of these (e.g., adds `timeout=` to the thread joins, or
drops the process timeouts), **this doc must be re-confirmed** — that is exactly what the Level-3
gate catches.

---

## 9. Live timed-log test — **OPTIONAL** (source is conclusive)

The contract permits skipping the live test when the analysis is conclusive. **It is conclusive:**
the only unbounded operations in the shutdown path are the two `threading.Thread.join()` calls
(claims a/b), and the two `mp.Process` joins are provably bounded (claim c). No live daemon probe is
required to establish the *root-cause category* (unbounded thread join), and the *category* is all
S2 needs (§7).

**Methodology, if an agent wants extra evidence (pinning the *exact* thread):**

1. Wrap each shutdown step with `time.monotonic()`-based logs — either by monkey-patching
   `shutdown_recorder`, or by adding temporary `logger.debug("step X enter/exit t=…")` timestamps
   before/after each `.join()` in a local checkout of `core/shutdown.py`.
2. Run `voicectl quit` against a **live** daemon (mic armed), then read the timestamps:
   `journalctl --user -u voice-typing -b -o short-precise | grep -iE 'finishing|realtime|reader|transcript'`.
3. The step whose "enter" has no matching "exit" before the 90s SIGKILL is the blocking thread.

**This subtask declines to run the live probe** as a required gate — it is disruptive (it forces a
real ~90s hang on the user's running daemon) and unnecessary. The source is conclusive.

---

## 10. Summary of confirmed facts

| # | Confirmed fact | Evidence | Pinned? |
|---|---|---|---|
| a | `recording_thread.join()` has **no timeout** | `core/shutdown.py:33-34` | yes (source) |
| b | `realtime_thread.join()` has **no timeout** | `core/shutdown.py:62-63` | yes (source) |
| c | both `mp.Process` joins are bounded (`timeout=10` + `terminate()`); reader is mic-gated | `core/shutdown.py:38-52` (2× each) | yes (source) |
| — | wedge category = **unbounded `threading.Thread.join()`** in `shutdown_recorder()` | a/b/c (process joins bounded) | yes (source) |
| — | first candidate blocker = `recording_thread.join()` (step 2); `realtime_thread.join()` (step 6) only after step 2 returns | §4 ordering | category yes; **exact thread not pinned** (optional live probe) |
| — | daemon adds **no bound** at the call site | `daemon.py:818-844` | yes (source) |
| — | 90s = systemd **default** `TimeoutStopSec=90s` (unit sets none); no 90s in RealtimeSTT | `systemd/voice-typing.service` (no directive) | yes (config) |
| — | S2 wraps the whole `recorder.shutdown()` + force-terminates the spawn processes; threads die with the process | §7 handoff | — (S2 owns code) |

**Bottom line for S2/T2.S1/M3:** the root cause is an **unbounded thread join** inside
`shutdown_recorder()`, surfaced as a **~90s** wedge by systemd's **default `TimeoutStopSec`**. S2's
bounded-teardown (whole-call hard timeout + force-terminate the spawn VRAM-holder processes) is the
correct and complete fix; the daemon threads need no (and can get no) explicit killing; T2.S1's
`TimeoutStopSec=15` is justified once S2 lands; M3's idle-unload can then call the teardown path
without hanging every 30 min.
