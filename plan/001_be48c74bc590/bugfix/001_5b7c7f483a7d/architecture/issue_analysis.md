# Issue Analysis & Fix Strategy

## Issue 1 (Major): Unbounded realtimesst.log to $HOME
**Root cause:** `_FIXED_KWARGS` in `daemon.py:96-108` has 10 keys but NOT `no_log_file`.
RealtimeSTT opens a DEBUG-level FileHandler at `realtimesst.log` (relative CWD = $HOME under
systemd) with no rotation, growing ~53 MB/day.

**Fix:** Add `"no_log_file": True` to `_FIXED_KWARGS`. One line. The daemon's own logging
(stderr → journald) already covers PRD §4.2. RealtimeSTT's console handler (StreamHandler →
stderr) still sends messages to journald. The `_filter_kwargs_to_signature` filter keeps
`no_log_file` because it IS in AudioToTextRecorder.__init__'s signature (line 180).

**Complexity:** 1 subtask, 0.5 SP. Test: assert `no_log_file=True` is in `cfg_to_kwargs()` output.

**PRD refs:** §4.2 (logging), §4.9 (24/7 systemd service).

---

## Issue 2 (Major): Mic-unavailable → silent failure + traceback spam
**Root cause:** Three intertwined problems:
1. `status_snapshot()` (daemon.py:538-559) has NO mic-health field. `listening` only reflects
   the threading.Event arm state, not actual mic capture status.
2. `set_microphone()` just flips a flag (audio_recorder.py:718-723) — no I/O check, no return.
3. RealtimeSTT's audio_input_worker.py retries mic connection in an infinite `while` loop with
   `time.sleep(3)`, `exc_info=True` on every attempt. No backoff, no max-retries. The daemon
   has no reference to this worker thread's state.

**Fix strategy (3 subtasks):**
1. **Mic health detection:** Add a lightweight PyAudio probe in the daemon. On `_arm()`, after
   `set_microphone(True)`, probe PyAudio for a valid default input device. Store result in
   `self._mic_ok` and `self._mic_error`. Also probe at startup to detect pre-arm failure.
2. **Surface mic health in status:** Add `mic_ok` and `mic_error` fields to `status_snapshot()`.
   These propagate to `voicectl status` and all control-socket responses automatically (via
   `**status_snapshot()` spread in `_dispatch()`). Update `ctl.py`'s `format_result()` to
   display mic status.
3. **Rate-limit traceback spam:** Wrap/redirect the RealtimeSTT `"realtimestt"` logger for the
   "Microphone connection failed" message. Detect recurring error and log a single summarized
   warning instead of a full traceback every 3 s. Use a `logging.Filter` or a custom handler
   that deduplicates within a time window.

**Complexity:** 3 subtasks, ~3 SP total.

**Key design decisions:**
- The PyAudio probe should NOT import pyaudio at module level (keeps `voice_typing.ctl` import
  pure — Issue 4 invariant). Import it lazily inside the probe function.
- The probe should catch all exceptions (PyAudio may not be installed, device may be gone).
- The `_mic_ok` flag should be updated on each `_arm()` call AND at startup. It should NOT
  require the mic to be working for the daemon to start (degraded mode is acceptable).

**PRD refs:** §4.4 (daemon MUST log clearly and say so in status), §8 risk "PyAudio picks wrong
device", §6 T5 (First run clear behavior), §1 (mic is the system's input).

---

## Issue 3 (Major): CUDA construction-failure → no CPU fallback
**Root cause:** `cuda_check.resolve_device_and_models()` only probes the CUDA driver
(`ctranslate2.get_cuda_device_count()`). If driver reports GPU but cuDNN init fails at
AudioToTextRecorder construction (WhisperModel load), `main()` catches the Exception at line 936,
logs "fatal error", and `return 1`. systemd's `Restart=on-failure` crash-loops forever.

The module docstring at daemon.py:25-29 explicitly acknowledges this is deferred.

**Fix strategy (2 subtasks):**
1. **Add force_cpu capability:** Thread a `force_cpu: bool = False` parameter through
   `_resolve_device_config()` / `cfg_to_kwargs()` / `_construct()` / `build_recorder()`. When
   `force_cpu=True`, skip the driver probe and build kwargs from `cuda_check.CPU_FALLBACK`
   directly. Alternatively, create a `build_recorder_forced_cpu()` helper. The cleanest seam is
   to add `force_cpu` to `build_recorder()` and have it override the resolved device dict.
2. **Construction-failure retry in main():** Wrap `VoiceTypingDaemon(cfg, ...)` construction so
   that on Exception (when the first attempt was on CUDA path), it logs the CUDA failure, retries
   once with `force_cpu=True` (or by temporarily setting cfg.asr.device="cpu" on a copy), logs
   the degradation clearly, and continues. If the CPU retry also fails, fall through to the
   existing `return 1`.

**Complexity:** 2 subtasks, ~3 SP total.

**Key design decisions:**
- The retry should only fire when the first attempt was CUDA (skip pointless double-failure
  when config already forces CPU).
- A partially-constructed daemon that raised may have allocated VRAM — but since
  `build_recorder` is called fresh in the retry, the half-built object is dropped (GC'd).
  Still, worth a comment about this.
- Must NOT change systemd unit, launch_daemon.sh, or cuda_check probe.

**PRD ref:** §4.4 ("If CUDA init fails entirely, daemon MUST log clearly and fall back to
device='cpu', compute_type='int8'... and say so in status").

---

## Issue 4 (Minor): pytest tests/ fast suite order-dependent failure
**Root cause:** `test_voicectl.py::test_ctl_module_present_and_imports_pure` asserts
torch/ctranslate2 absent from sys.modules. But `test_daemon.py` runs first (alphabetical) and
some tests call the REAL `cuda_check.resolve_device_and_models()` without monkeypatching
(importing ctranslate2 → torch into the process-global sys.modules).

Polluting tests:
- `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` (test_daemon.py:98-111) — no monkeypatch.
- `test_run_loop_not_listening_does_not_call_text` (test_daemon.py:517)
- `test_run_loop_calls_text_when_listening_then_exits_on_shutdown` (test_daemon.py:529)
- `test_run_sets_uptime_after_start` (test_daemon.py:543)

**Fix strategy (2 subtasks):**
1. **Fix polluters (Option A):** Add `monkeypatch` param + `_cuda_resolve(monkeypatch, ...)` call
   to the 4 polluting tests, mirroring their siblings and `test_run_logs_resolved_device_at_startup`.
2. **Harden purity test (Option B):** Rewrite the assertion to snapshot sys.modules before/after
   importing `voice_typing.ctl`, rather than asserting global absence.

**Complexity:** 2 subtasks, ~1.5 SP total.

**PRD refs:** §6, §7.1 (acceptance relies on documented test commands).

---

## Issue 5 (Minor): Incorrect "daemon serializes on_final" docstring claim
**Root cause:** typing_backends.py:19-23 and feedback.py:31-35 claim "daemon serializes
on_final calls". This is FALSE: RealtimeSTT's `text()` fires the callback via
`threading.Thread(...).start()` (transcription_api.py:40-42), and `on_final` in daemon.py:450-489
has NO lock. Two callbacks can run concurrently.

**Fix strategy (2 subtasks):**
1. **Add serialization lock:** Add a `self._on_final_lock = threading.Lock()` to
   `VoiceTypingDaemon.__init__`, and wrap the clean → type → record → log body in `on_final`
   with `with self._on_final_lock:`. Use a SEPARATE lock from `self._lock` (which guards
   arm/disarm/start/stop) to avoid coupling on_final latency to toggle latency.
2. **Correct docstrings:** Update typing_backends.py:19-23 and feedback.py:31-35 to state that
   on_final IS serialized via the daemon's `_on_final_lock`, making the invariant accurate.

**Complexity:** 2 subtasks, ~1.5 SP total.

**PRD refs:** §4.2 (on_final → type path), §4.3 (typing-backend thread safety).

---

## Issue 6 (Minor): install.sh skips portaudio check
**Root cause:** install.sh has no portaudio/pacman handling. PRD §5 step 2 mandates it.

**Fix:** Add a portaudio preflight after install.sh:42 (after systemctl check). Check
`pacman -Q portaudio`; if missing, print exact `sudo pacman -S portaudio` command and exit 1.
Mirror the non-interactive-sudo note from PRD §2.

**Complexity:** 1 subtask, 0.5 SP.

**PRD refs:** §5 step 2, §2 (portaudio possibly missing).

---

## Issue 7 (Minor): voicectl exit code 2 overlap
**Root cause:** argparse exits 2 for usage errors (unknown command, no command). PRD §4.8
reserves 2 for "daemon not running".

**Fix:** Drop `choices=_COMMANDS` from argparse. Validate `args.cmd` manually in `main()` after
`parse_args()`. Map usage errors to exit code 64 (EX_USAGE from BSD sysexits.h). Reserve 2 for
"daemon not running" only. Update `test_main_rejects_unknown_command`.

**Complexity:** 1 subtask, 1 SP.

**PRD ref:** §4.8 ("If daemon not running: clear message + exit 2").

---

## Dependency Graph

```
Issue 1 (log file) → independent
Issue 2 (mic health) → independent
Issue 3 (CUDA fallback) → independent
Issue 4 (test isolation) → independent
Issue 5 (concurrency) → independent (touch same files as Issue 2 daemon.py, but different functions)
Issue 6 (portaudio) → independent
Issue 7 (exit codes) → independent

Doc sync → depends on ALL implementing subtasks
```

No strict ordering required between issues. Milestone grouping:
- M1: Major Issues (1, 2, 3) — operational robustness
- M2: Minor Issues (4, 5, 6, 7) — quality/correctness
- M3: Documentation sync (changeset-level)
