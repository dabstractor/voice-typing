# Bug Fix Requirements

## Overview

Creative end-to-end QA of the voice-typing daemon against PRD §4–§7. The core
functionality is solid and largely meets the spec: the offline acceptance test
(T1) passes in full (7/7), the WhisperX-flaw regression is fixed (a ≥3 s
mid-dictation pause keeps both halves), partials arrive on time, fuzzy accuracy
and latency targets are met, `voicectl toggle/start/stop/status/quit` all work
against the live systemd daemon, the daemon boots un-armed on CUDA, and models
are GPU-resident (2.8 GB). The hallucination filter, control-socket protocol,
and config loader are robust.

The issues below are real defects found by probing the live daemon, the
installed RealtimeSTT library, and adversarial code paths the unit tests (which
mock the recorder) do not exercise. None crash a correctly-configured system,
but several fail the PRD's robustness/operational MUSTs and would bite a 24/7
systemd deployment or a user whose mic/CUDA environment changes.

Verification basis: the systemd unit was active (pid 1787, uptime >2 h,
`device: cuda`), the offline `test_feed_audio.py` suite passed 7/7, the
RealtimeSTT constructor signature and `text()/abort()/set_microphone()` methods
were verified against the installed wheel, and the live daemon was driven via
`voicectl` and raw socket JSON.

## Critical Issues (Must Fix)

None. On a correctly-configured machine (CUDA working, default mic present)
every PRD acceptance criterion is met. The issues below are Major (operational
/ robustness) and Minor.

## Major Issues (Should Fix)

### Issue 1: Production daemon writes an unbounded `realtimesst.log` to `$HOME`
**Severity**: Major
**PRD Reference**: §4.2 ("Logging: python `logging` to stderr (journald picks it
up under systemd) at INFO" — the intended logging path; RealtimeSTT's separate
file log is an unintended side effect), §4.9 (24/7 systemd service).
**Expected Behavior**: A long-running systemd daemon should emit logs only via
Python's `logging` → stderr → journald. No separate, unbounded log file should
be written to the user's home directory.
**Actual Behavior**: RealtimeSTT opens its own `FileHandler` log at
`realtimesst.log` in the process CWD unless `no_log_file=True` is passed. The
production daemon never sets `no_log_file` (only the offline test does, in
`tests/test_feed_audio.py`). The systemd unit has no `WorkingDirectory=`, so the
daemon's CWD is `$HOME`. Verified live: `pid 1787` holds fd 22 open to
`/home/dustin/realtimesst.log` (5.6 MB and growing); it grew 1861 bytes in 3 s
(~620 B/s ≈ 53 MB/day, unbounded). A second 44 MB copy exists in the repo root
from test/manual runs. RealtimeSTT does not rotate or cap this file.
**Steps to Reproduce**:
1. `systemctl --user status voice-typing` (note the Main PID).
2. `ls -la /proc/<pid>/fd | grep realtimesst` → shows an open handle to
   `$HOME/realtimesst.log`.
3. `s=$(stat -c %s ~/realtimesst.log); sleep 5; echo $(( $(stat -c %s ~/realtimesst.log) - s ))`
   → nonzero and growing every interval, even with `listening: off`.
4. `grep -n no_log_file voice_typing/daemon.py` → no match (not set in production).
**Suggested Fix**: Add `"no_log_file": True` to the `_FIXED_KWARGS` dict in
`voice_typing/daemon.py` (it is a confirmed, accepted kwarg of
`AudioToTextRecorder.__init__`). The daemon's own `logging` → stderr → journald
path already covers PRD §4.2. (The unit tests already pass `no_log_file=True`,
so the production path simply needs to match.)

### Issue 2: Mic-unavailable → indefinite traceback-spamming retry loop with no user-facing indication and no recovery
**Severity**: Major
**PRD Reference**: §4.4 spirit ("daemon MUST log clearly … and say so in
status"), §8 risk row "PyAudio picks wrong device", §6 T5 ("First run" expects
clear behavior), §1 (the mic is the system's input; silent failure defeats the
product).
**Expected Behavior**: When the default/configured mic is unavailable
(disconnect, source change, device gone), the daemon should log the condition
clearly, surface it in `voicectl status`, and ideally back off — not silently
report "listening: on" while the user speaks into a dead mic.
**Actual Behavior**: RealtimeSTT's `AudioInputWorker._initialize_stream`
(`core/audio_input_worker.py:161-165`) retries the mic connection in an
infinite `while` loop with a fixed `time.sleep(3)`, no max-retries, no backoff,
and logs a full traceback (`exc_info=True`) on every attempt. The daemon binds
the PyAudio device ONCE at construction; `set_microphone()` only flips a flag,
so a mid-run mic change is never re-resolved. Observed on the live daemon: the
webcam mic (the PRD's only real mic) disconnected, and the daemon entered a
retry loop logging `Microphone connection failed: Selected device validation
failed. Retrying...` every 3 s — 2822+ errors and counting. Meanwhile
`voicectl status` reports a healthy `device: cuda`, and `voicectl start`
returns `listening: on` (exit 0) with no hint that capture is broken. The user
would arm, speak, get nothing, and have to dig into `journalctl` to learn the
mic is gone. The daemon cannot recover without a full restart.
**Steps to Reproduce**:
1. With the daemon running, change/remove the default source, e.g.
   `pactl unload-module <index-of-webcam-module>` or physically unplug the mic.
2. `journalctl --user -u voice-typing -f` → repeated `Microphone connection
   failed … Retrying...` with tracebacks every ~3 s.
3. `.venv/bin/voicectl status` → shows `device: cuda`, `listening: off`,
   nothing about the mic. `.venv/bin/voicectl start` → `listening: on` (exit 0),
   but no audio is captured.
4. Count: `journalctl --user -u voice-typing | grep -c "Microphone connection
   failed"` grows without bound.
**Suggested Fix**: (a) Detect mic/PyAudio open failure at or after construction
and reflect it in `status_snapshot()` (e.g. add a `mic_ok`/`error` field so
`voicectl status` and the tmux status show the problem). (b) Rate-limit or
suppress the per-attempt traceback (wrap/redirect the RealtimeSTT logger for
this message, or detect the recurring error and log a single summarized
warning). (c) Optionally, on a sustained mic failure, attempt to re-resolve the
default device (the loop already sets `input_device_index = None`, so reopening
on the new default after a restart-free re-init could recover). At minimum,
make the failure user-visible instead of silent.

### Issue 3: CUDA construction-failure does not fall back to CPU (PRD §4.4 MUST partially unmet)
**Severity**: Major
**PRD Reference**: §4.4 ("If CUDA init fails entirely, daemon MUST log clearly
and fall back to `device='cpu', compute_type='int8'` … — degraded but
functional — and say so in `status`.").
**Expected Behavior**: If CUDA initialization fails at any point (including at
`AudioToTextRecorder` construction / WhisperModel load), the daemon should fall
back to the CPU degraded config and keep running.
**Actual Behavior**: `cuda_check.resolve_device_and_models()` only probes the
CUDA **driver** (`ctranslate2.get_cuda_device_count()`). If the driver reports a
GPU (verdict `cuda-ok`) but actual CUDA/cuDNN init fails later at
`AudioToTextRecorder` construction (e.g. `libcudnn_ops.so.9` not loadable
despite the GPU being visible), there is no construction-failure → CPU retry.
`main()` constructs `VoiceTypingDaemon(cfg, Feedback(...))` inside a
`try/except Exception` that logs `"fatal error during daemon lifecycle; exiting"`
and `return 1`; systemd's `Restart=on-failure` then crash-loops the unit on the
GPU path forever instead of degrading to CPU. The daemon's own module docstring
acknowledges this is deferred: "A construction-failure→CPU retry is a
robustness hook for main() … or a future task; S1 applies ONLY the
verdict-based fallback above." On this machine cuDNN loads (via
`launch_daemon.sh`'s `LD_LIBRARY_PATH`), so it does not trigger today — but the
PRD's MUST is only satisfied for the "no GPU visible" sub-case, not the "CUDA
init fails entirely" case.
**Steps to Reproduce**:
1. Simulate a CUDA load failure: temporarily break the cuDNN path, e.g.
   `LD_LIBRARY_PATH= voice_typing/launch_daemon.sh` after removing the override
   (or run on a host where the nvidia wheels are absent but a GPU/driver is
   present so `get_cuda_device_count() >= 1`).
2. `systemctl --user status voice-typing` → `Restart=on-failure` loop; the unit
   never settles into CPU mode. `journalctl` shows the construction traceback
   repeating.
**Suggested Fix**: In `main()` (or `build_recorder()`), wrap recorder
construction in a try/except; on failure with a resolved `device=="cuda"`,
re-resolve with `cuda_check.CPU_FALLBACK`, reconstruct, log the degradation
clearly, and continue. The existing `resolve_device_and_models()` +
`CPU_FALLBACK` machinery already provides the target config — only the
construction-layer retry is missing.

## Minor Issues (Nice to Fix)

### Issue 4: `pytest tests/` fast suite fails due to test-isolation (order-dependent)
**Severity**: Minor
**PRD Reference**: §6 / §7.1 (acceptance relies on the documented test commands;
every test module's docstring and the README point users at `pytest tests/`).
**Expected Behavior**: `pytest tests/` (the documented fast sweep, with the heavy
`test_feed_audio.py` ignored on a CPU box) is green.
**Actual Behavior**: `pytest tests/ --ignore=tests/test_feed_audio.py` reports
`1 failed, 210 passed`. `tests/test_voicectl.py::test_ctl_module_present_and_imports_pure`
asserts that `torch`/`ctranslate2` are absent from `sys.modules`, but it runs
AFTER `tests/test_daemon.py` (alphabetical order). Three daemon tests call the
REAL `cuda_check.resolve_device_and_models()` without monkeypatching it
(`test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set`, plus the run-loop
tests via `run()` → `_log_resolved_device()`), which imports `ctranslate2` (→
`torch`), polluting `sys.modules` and failing the later purity assertion.
Running `test_voicectl.py` alone (or first) passes.
**Steps to Reproduce**:
1. `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` →
   `FAILED tests/test_voicectl.py::test_ctl_module_present_and_imports_pure`.
2. `.venv/bin/python -m pytest tests/test_voicectl.py -q` → passes.
**Suggested Fix**: Either (a) make the polluting daemon tests monkeypatch
`cuda_check.resolve_device_and_models` (as the `_cuda_resolve` fixture already
does for other tests), or (b) make `test_ctl_module_present_and_imports_pure`
robust by checking that importing `voice_typing.ctl` does not *add* heavy
modules (snapshot `sys.modules` before/after the import, rather than asserting
global absence). Option (a) is the smaller change.

### Issue 5: Incorrect "daemon serializes on_final calls" docstring claim (latent concurrent-typing race)
**Severity**: Minor
**PRD Reference**: §4.2 (the on_final → type path), §4.3 (typing-backend thread
safety).
**Expected Behavior**: Documentation should accurately describe the concurrency
model so maintainers rely on the right invariant.
**Actual Behavior**: `voice_typing/typing_backends.py:22` ("The daemon serializes
on_final calls, so no locking is needed") and `voice_typing/feedback.py:35`
("The daemon serializes on_final anyway") state that on_final calls are
serialized. This is false for the installed RealtimeSTT: `transcribe_text()`
runs `recorder.transcribe()` (the heavy final-model inference) in the calling
(main) thread, then does
`threading.Thread(target=on_transcription_finished, args=(...)).start()` and
returns immediately — so the next `recorder.text()` call re-enters `wait_audio()`
while the previous on_final callback is still running. Two on_final callbacks
can therefore run concurrently (the typing-backend `subprocess.run` per call is
reentrant, so it does not crash, but typed text could interleave or land
out-of-order if typing is slower than the next transcription cycle). The
likelihood is low in practice (GPU transcription ≫ wtype latency), but the
stated invariant is wrong and there is no actual serialization/lock.
**Steps to Reproduce** (code inspection): `.venv/bin/python -c "import inspect,
RealtimeSTT.audio_recorder as a; print(inspect.getsource(a.transcribe_text))"`
shows the callback branch is `threading.Thread(...).start()` with no `.join()`.
**Suggested Fix**: Either add a lock around the on_final → type sequence (e.g. a
`self._final_lock` in `VoiceTypingDaemon.on_final` held across clean/type/record)
to actually serialize, or correct the docstrings to state that on_final may run
concurrently and that the backends are individually reentrant (and accept the
low-probability ordering caveat).

### Issue 6: `install.sh` skips the PRD-mandated `portaudio` check
**Severity**: Minor
**PRD Reference**: §5 step 2 ("Ensure portaudio: `pacman -Q portaudio || sudo
pacman -S --noconfirm portaudio`").
**Expected Behavior**: The installer ensures the PyAudio system dependency
(`portaudio`) is present, per the PRD install steps.
**Actual Behavior**: `install.sh` has no `portaudio`/`pacman` handling
(`grep -in portaudio install.sh` → no match). On this machine `portaudio
1:19.7.0-4` is already installed so it works, but on a fresh clone without
portaudio, `uv sync` installs the PyAudio wheel, the daemon then fails at
PyAudio construction (missing `libportaudio`), and `install.sh` prints only
"voice-typing.service: NOT active — check journalctl" — a confusing failure
instead of the actionable "install portaudio first".
**Steps to Reproduce**: On a host without portaudio, run `./install.sh`; the
service fails to start with a PyAudio/dlopen error and no guidance.
**Suggested Fix**: Add a portaudio preflight to `install.sh` (check
`pacman -Q portaudio`; if missing, print the exact `sudo pacman -S portaudio`
command for the user to run, mirroring the PRD's non-interactive-sudo note).

### Issue 7: `voicectl` exit code 2 overlaps argparse usage errors with "daemon not running"
**Severity**: Minor
**PRD Reference**: §4.8 ("exit code 0/1. … If daemon not running: clear message
+ exit 2").
**Expected Behavior**: Exit code 2 unambiguously means "daemon not running" (so
scripts/wrappers can distinguish).
**Actual Behavior**: `argparse` exits 2 for usage errors (`voicectl` with no
command, or `voicectl frobnicate`), the same code reserved by PRD §4.8 for
"daemon not running". A caller checking `$? -eq 2` cannot tell a usage error
from a down daemon.
**Steps to Reproduce**: `.venv/bin/voicectl frobnicate; echo $?` → 2 (same as a
down daemon).
**Suggested Fix**: Acceptable as-is for an interactive CLI (standard argparse
behavior), but if programmatic distinction is wanted, parse manually instead of
relying on argparse `choices` so usage errors can map to a different code (e.g.
64/65), reserving 2 for "daemon not running". Low priority.

## Testing Summary
- Total tests performed: ~30 distinct checks across offline unit/integration,
  live-daemon control-plane, raw-socket protocol, textproc edge cases, CLI exit
  codes, RealtimeSTT API verification, journal/log inspection, and GPU/resource
  accounting.
- Passing: T1 offline suite (7/7), all 210 fast unit tests except the 1
  isolation failure, live `voicectl toggle/start/stop/status/quit`, raw-socket
  malformed/unknown/non-dict handling, textproc blocklist/whitespace/unicode,
  un-armed boot, CUDA residency (2.8 GB), config loader search-order + drift
  guard.
- Failing: 1 fast-suite test (Issue 4, test-isolation only).
- Areas with good coverage: control-socket protocol, config loading, textproc
  filter, typing-backend fallback, feedback state file/notifications, offline
  ASR pipeline (T1), un-armed boot, GPU residency.
- Areas needing more attention: live-environment robustness — unbounded
  `realtimesst.log` (Issue 1), mic-unavailable handling (Issue 2), and
  CUDA-construction-failure CPU fallback (Issue 3); the on_final concurrency
  invariant (Issue 5); installer portaudio preflight (Issue 6).
