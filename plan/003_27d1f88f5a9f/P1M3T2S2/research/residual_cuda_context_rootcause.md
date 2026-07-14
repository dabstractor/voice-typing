# Research — P1.M3.T2.S2 (RE-PLAN attempt 2): the 258 MiB residual CUDA context

Re-verifies the production bug that deterministically failed T6(d-gone) in attempt 1, by reading the
INSTALLED RealtimeSTT v1.0.2 source + `voice_typing/daemon.py` + `voice_typing/cuda_check.py` +
`tests/test_daemon.py` + `tests/test_idle_and_gpu.sh` on 2026-07-13. **Attempt 1's premise (spawn-
worker termination releases all VRAM) is FALSIFIED.** This note pins the true root cause and the only
viable fix.

---

## 1. The failed premise of attempt 1 (and the M1.T1.S2 architecture doc it copied)

`plan/003.../architecture/realtimestt_shutdown_analysis_confirmed.md` §2 claimed:

> **Spawn start method:** `mp.set_start_method("spawn")` … each `mp.Process` has its **own CUDA
> context and GPU memory**. This is the basis for S2's force-cleanup: **terminating the processes
> releases their VRAM**.

That is true ONLY for the two entities that are `mp.Process`: `transcript_process` (final Whisper
model) and `reader_process` (audio reader — no GPU). It is FALSE for the realtime model and the
VAD, which the doc did NOT examine. Attempt 1's PRP §4 (the risk analysis) extrapolated "all VRAM is
in spawn workers" from that doc — and T6(d-gone) failed on exactly that extrapolation.

## 2. What actually holds GPU memory in the daemon process (installed source, verbatim)

| Entity | Type | Where it lives | Holds a CUDA context in the DAEMON process? |
|---|---|---|---|
| `transcript_process` | `mp.Process` (spawn) | **child process** (initialization.py:397) | NO — its own process (released by terminate) |
| `reader_process` | `mp.Process` (spawn) | **child process** (initialization.py:433) | NO — audio only |
| `recording_thread` | `threading.Thread` (daemon) | **parent/daemon** (initialization.py:614) | no (PyAudio, not CUDA) |
| `realtime_thread` | `threading.Thread` (daemon) | **parent/daemon** (initialization.py:621-626) | **YES** |
| `realtime_transcription_model` | faster-whisper (ctranslate2) | **constructed in parent** via `_initialize_realtime_transcription_model` (initialization.py:447-490 → `create_transcription_engine` at :466) | **YES** — model load initializes CUDA in the daemon |
| silero VAD | torch/ONNX | **parent** (initialization.py:558 `create_silero_vad_model`) | maybe — config `silero_backend="auto"` prefers CPU ONNX; likely NOT the GPU holder |
| cuda_check probe | `ctranslate2.get_cuda_device_count()` | **parent** (`voice_typing/cuda_check.py:_cuda_device_count`, called from `_resolve_device_config` during `build_recorder`) | possibly — driver query; may init the CUDA runtime |

**Decisive fact:** `recorder.realtime_transcription_model` (the `small.en` realtime Whisper model,
PRD §4.4) is constructed **inside the daemon process** and driven by `realtime_thread`, a plain
`threading.Thread` in that same process. Constructing it calls `ctranslate2`/faster-whisper, which
**creates a CUDA primary context in the daemon process**. This is the ~258 MiB residual.

## 3. Why the residual is UNRELEASABLE in-process (hard CUDA constraint)

A CUDA **primary context**, once created in a process by the first CUDA-bearing operation
(faster-whisper/ctranslate2 model construction here), persists **until the process exits**. None of
these release it:

- `del recorder.realtime_transcription_model` + `gc.collect()` — frees the *model's allocations*, not
  the context.
- `torch.cuda.empty_cache()` — frees the *caching allocator's* free blocks, not the context.
- terminating `transcript_process`/`reader_process` (attempt 1's `_bounded_shutdown`) — releases
  *their* (child-process) contexts, NOT the daemon's own context.

This is standard CUDA behavior, documented across NVIDIA/PyTorch: the per-process context + runtime
footprint (≈100–300 MiB on modern GPUs; **258 MiB measured here**) cannot be returned without process
exit. Attempt 1's `_bounded_shutdown` correctly released the *models* (2804→258 MiB, ~91%) but
physically cannot reach 0 while the daemon PID lives.

## 4. No RealtimeSTT config knob moves the realtime model out of the daemon

`realtime_transcription_executor` (audio_recorder.py:192, initialization.py:290-297, realtime.py:284-
328, recorder_config.py:87/185) is an **Optional[Callable]** — a function hook for *external*
transcription (e.g. a cloud API callable), NOT a process/executor-pool that isolates the model's CUDA
context. The guard at initialization.py:455 (`and not recorder._uses_external_realtime_transcription_
executor`) skips in-process model init only when such a callable is supplied — but the callable still
runs (and thus still holds CUDA) wherever it is invoked, which for realtime is the parent realtime
thread. There is **no** RealtimeSTT option to run the realtime model in a separate process.

Disabling realtime (`enable_realtime_transcription=False`) would remove the daemon's realtime-model
context — but PRD §7.3 + criterion 3 **require live partials**, so that is not an option.

## 5. The ONLY way to make the daemon PID reach ~0 MiB while alive: host the WHOLE recorder in a child process

If the entire `AudioToTextRecorder` (final model + realtime model + VAD + cuda_check) is constructed
and owned inside a **managed child subprocess** that the daemon spawns, then the **daemon process
never touches CUDA** — all CUDA contexts live in the child. Then:

- idle-unload = terminate the child subprocess → **all** VRAM (including the realtime-model context)
  is released → daemon PID is **truly absent** from nvidia-smi (~0 MiB) while the daemon keeps running.
- re-arm = respawn the child → reload.

This is the design the strict PRD §7.9 + §6 T6(d) contract actually requires. Attempt 1's in-process
approach is structurally incapable of it. This is the **production fix** the issue feedback demands.

## 6. The daemon's recorder call-surface is SMALL (the IPC layer is bounded)

Every `self._recorder.*` call site in `voice_typing/daemon.py` (grep-confirmed):

| line | call | IPC equivalent (child↔daemon) |
|---|---|---|
| 606 | `self._recorder.set_microphone(False)` | cmd `disarm` → child |
| 631 | `self._recorder.text(self.on_final)` | child runs `recorder.text(...)`, sends `final{text}` event → daemon; daemon's `text()` blocks on the event then calls `on_final` |
| 724 | `self._recorder.set_microphone(True)` | cmd `arm` → child |
| 749 | `self._recorder.set_microphone(False)` | cmd `disarm` |
| 958 | `self._recorder.abort()` | cmd `abort` |
| 1104 | `self._recorder.shutdown()` | cmd `shutdown` (graceful) → then SIGTERM/SIGKILL the child |
| 1135/1139 | `is_shut_down` / `realtime_transcription_model = None` (force-cleanup attrs) | N/A — terminating the child replaces these entirely |

Plus the callback events that originate in the child and must cross to the daemon: `partial{text}`
(realtime callback), `speech{}` (on_speech / `_touch_speech`), `device{...}` (resolved device for
status/logging), `ready{}`, `error{msg}` (load failure → CPU-fallback path).

So the IPC surface = **5 commands + ~6 event types** — bounded and tractable.

## 7. Test seam to PRESERVE (so the fast pytest stays hermetic)

`VoiceTypingDaemon.__init__` takes `recorder=None` (daemon.py:465) — injected recorders skip the lazy
load. `tests/test_daemon.py` builds the daemon via `_make_daemon(recorder=...)` with fakes
(`_FakeRecorder`, `_StubRecorder`, `_RaisingRecorder`, `_FakeSlowRecorder`) at lines 427-432, 1108,
1169-1185, 1229, 1284, 1307, 1703-1713. The host refactor MUST keep an injection seam
(`recorder_host=` / `host_factory=`) so these unit tests stay CUDA-free and fast. `_construct` /
`build_recorder` (daemon.py:274-300) stay as the production child-side construction path (unchanged
interface — just called inside the worker instead of the daemon).

## 8. Why NOT the cheaper alternatives

- **`gc.collect()` + `torch.cuda.empty_cache()` in the unload path:** reduces the residual toward the
  bare-context floor (~150-258 MiB) but NEVER to 0. The CUDA primary context stays. Would still fail
  the strict T6(d-gone). (Worth adding as a belt-and-braces inside the child, but it does not satisfy
  §7.9 on the daemon PID.)
- **Move only the realtime model to CPU / patch RealtimeSTT:** RealtimeSTT uses ONE `device` for both
  models (initialization.py:466 `device=recorder.device`); splitting requires patching the vendored
  wheel (fragile, breaks on bump). And it would degrade partial latency (PRD §6 target ≤300 ms) —
  violates §7.3. Rejected.
- **`os.execv` daemon self-restart on idle-unload:** keeps the PID + releases VRAM, but races the
  control-socket rebind, drops in-flight voicectl commands, and changes the idle-unload mechanism from
  "tear down recorder" (§4.2bis) to "restart the process" (not what §6 T6(d) "the PID reappears"
  envisions, and very race-prone). Rejected as too risky for a re-plan.
- **Declare `result: fail`:** not warranted — the subprocess host IS feasible (small IPC surface,
  RealtimeSTT already uses spawn internally) and is the correct fix. The issue is expensive, not
  impossible.

## 9. Latency impact of the subprocess host (must verify, expected negligible)

T1 (≤300 ms partial cadence) + T1e (≤1.5 s final) + criterion-5 (<25% CPU) cross a `multiprocessing`
queue. Same-host `mp.Queue`/`Pipe` hop is sub-millisecond to low-millisecond — negligible against the
300 ms / 1.5 s budgets. The child's `recorder.text()` still blocks the same way (just inside the
child). The L2/L4 validation gates re-run T1 + T3 to PROVE no regression. This is the main risk of
the fix and it is explicitly gated.

## 10. Bottom line

Attempt 1 was correctly scoped as test-only and correctly refused to weaken the assertion — but its
premise (in-process VRAM release) was wrong. The residual ~258 MiB is an inherent, unreleasable CUDA
primary context held by the daemon process because RealtimeSTT v1.0.2 loads the realtime model
in-process. The strict PRD §7.9 / §6 T6(d) contract is achievable ONLY by moving the entire recorder
into a managed child subprocess (so the daemon never touches CUDA). The revised PRP implements that
subprocess host (a bounded IPC refactor over the small recorder call-surface) + keeps the strict 4-
part test (now passes naturally) + updates the docs.
