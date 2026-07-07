# Research: Writing an OFFLINE `feed_audio()` test for RealtimeSTT v1.0.2

> Audience: the PRP/implementation for `tests/test_feed_audio.py` (voice-typing daemon).
> Method: read the **installed** RealtimeSTT 1.0.2 source in `.venv/lib/python3.12/site-packages/RealtimeSTT/`
> (no web access available; the source is the ground truth, and it is more authoritative than the README).
> Every claim below is backed by a file path + symbol. Version verified from
> `realtimestt-1.0.2.dist-info/METADATA` (Name: realtimestt, Version: 1.0.2, Home-page: https://github.com/KoljaB/RealTimeSTT).

## Summary

`recorder.text(cb)` **blocks until exactly one utterance finalizes** (it internally calls
`wait_audio()`, which blocks on a per-segment `stop_recording_event`); to collect MULTIPLE finals
you **loop `text()`** (the production daemon does `while …: recorder.text(on_final)`). Feeding a
whole buffer at once **silently breaks VAD segmentation**, because the end-of-speech check is
**wall-clock** (`time.time() - speech_end_silence_start >= post_speech_silence_duration`) and only
runs once per *queue chunk* — so you **must pace chunks at real-time** (feed a slice, sleep its
audio-duration). On Linux the model "worker" is actually a **thread**, not a spawned process, and
`use_microphone=False` skips the mic reader entirely — but `recorder.shutdown()` is still mandatory
to join the threads + close the pipes. The 0.6 s `post_speech_silence_duration` cleanly segments a
3 s embedded silence into two halves because the recorder re-arms listening
(`continuous_listening=True`) after each stop.

---

## 1. The canonical `feed_audio()` + `text()` loop pattern (offline, no mic)

### 1a. Construction + feeding
`AudioToTextRecorder(use_microphone=False, ...)` is the entry point. With `use_microphone=False`:
- the audio queue is a plain **in-process `queue.Queue`**, not an `mp.Queue`
  (`core/initialization.py`, `_assign_initial_attributes`: `recorder.audio_queue = mp.Queue() if init_args["use_microphone"] else queue.Queue()`); and
- the mic **reader worker is never started** (`_start_audio_reader` is a no-op: `if recorder.use_microphone.value: …`).
  So no audio device is opened and no mic permission is needed. All audio enters via `feed_audio()`.

`feed_audio(chunk, original_sample_rate=16000)` — `audio_recorder.py` (delegates to
`core/manual_audio_input.py::feed_audio`):
- Accepts a **NumPy int16 array OR raw bytes**. If a NumPy array is passed it is mono-mixed
  (`np.mean(axis=1)` if 2-D), resampled to 16 kHz if `original_sample_rate != 16000`
  (`scipy.signal.resample`), cast to `int16`, and `tobytes()`'d.
- It **accumulates** into `recorder.buffer` (bytearray) and emits **Silero-sized chunks** of
  `buf_size = 2 * recorder.buffer_size` (= `2 * 512 = 1024 bytes = 512 samples = 32 ms`), putting
  each into `recorder.audio_queue`. It is **non-blocking** and **does not pace** — it dumps every
  32 ms slice into the queue as fast as possible.
- **Implication:** whatever chunk size you *pass in*, it is internally re-sliced to 32 ms frames.
  Pass larger slices (e.g. 0.1 s) for convenience; the 32 ms granularity is fixed by `buffer_size`.

### 1b. `text()` is BLOCKING and returns once per utterance
`core/transcription_api.py::text(recorder, on_transcription_finished=None)`:
```python
def text(recorder, on_transcription_finished=None):
    recorder.interrupt_stop_event.clear(); recorder.was_interrupted.clear()
    recorder.wait_audio()                      # <-- BLOCKS until ONE segment finalizes
    if recorder.is_shut_down or recorder.interrupt_stop_event.is_set():
        if recorder.interrupt_stop_event.is_set(): recorder.was_interrupted.set()
        return ""
    if on_transcription_finished:
        threading.Thread(target=on_transcription_finished,
                         args=(recorder.transcribe(),)).start()   # async delivery of ALREADY-computed text
    else:
        return recorder.transcribe()                               # synchronous return of the text
```
- **Yes, `text(cb)` blocks** — it blocks in `wait_audio()` until one utterance's recording is
  finalized, AND it blocks again inside `recorder.transcribe()` until the **final** model returns
  the text (that transcription runs on the *calling* thread). Only after both does it (a) fire the
  callback in a brand-new thread and (b) return.
- The callback is therefore **purely an async-delivery convenience** for already-computed text; it
  does NOT make `text()` non-blocking and it does NOT itself loop.
- **For MULTIPLE finals from one long feed you must LOOP `text()`.** This mirrors the production
  daemon (`voice_typing/daemon.py`, `VoiceTypingDaemon.run()`):
  `while not self._shutdown.is_set(): if self._listening.is_set(): self._recorder.text(self.on_final)`.
  This is the documented "Automatic Recording Loop" pattern from the README too:
  `while True: recorder.text(process_text)`.

### 1c. `wait_audio()` arms VAD listening and blocks per-segment
`core/lifecycle.py::wait_for_recorded_audio`:
1. Pops any already-queued finalized recording (`get_next_recorded_audio`).
2. If none and not recording → **arms voice activity** (`start_recording_on_voice_activity=True`)
   and **blocks** on `start_recording_event.wait(timeout=0.02)` until the worker detects speech.
3. If recording in progress → sets `stop_recording_on_voice_deactivity=True` and **blocks** on
   `stop_recording_event.wait(timeout=0.02)` until the worker detects end-of-speech.

**Critical ordering rule (test design):** the consumer loop that calls `text()` must be running
(blocked in `wait_audio`, which arms listening) **before / concurrently with** the first
`feed_audio()`. Audio fed before `text()` ever arms `start_recording_on_voice_activity` is consumed
by the worker but **never starts a recording** (it just updates VAD state), i.e. it is effectively
lost for that pass. So: start the consume thread first, then feed.

### 1d. Reference README patterns (from `realtimestt-1.0.2.dist-info/METADATA`, the embedded README)
- **Microphone / single utterance:** `with AudioToTextRecorder() as r: print(r.text())`
- **Automatic loop (multi-utterance):**
  ```python
  def process_text(text): print(text)
  recorder = AudioToTextRecorder()
  while True: recorder.text(process_text)
  ```
- **External audio (the simple — and subtly wrong-for-segmentation — example):**
  ```python
  recorder = AudioToTextRecorder(use_microphone=False)
  with open("audio_chunk.pcm", "rb") as f:
      recorder.feed_audio(f.read(), original_sample_rate=16000)
  print(recorder.text())
  recorder.shutdown()
  ```
  README also states: *"Feed 16-bit mono PCM chunks at 16 kHz, or pass the original sample rate so
  RealtimeSTT can resample."* It references `docs/external-audio.md` and `docs/quick-start.md`
  (these are source-only, **not shipped in the wheel**).

---

## 2. Real-time pacing is MANDATORY (the single most important finding)

### 2a. Why: both VAD segmentation and partial cadence are WALL-CLOCK based
End-of-speech stop logic — `core/recording.py::run_recording_worker`, recording branch
("Stop only after the post-speech silence threshold passes"):
```python
if (self.speech_end_silence_start and
    time.time() - self.speech_end_silence_start >= self.post_speech_silence_duration):
    ...
    self.stop()           # finalize the segment -> sets stop_recording_event
```
`self.speech_end_silence_start` is set to `time.time()` when sustained silence is confirmed. The
threshold is measured in **wall-clock seconds**, and this `if` only executes **once per 32 ms
queue chunk pulled** by the worker (`data = self.audio_queue.get(timeout=0.01)`); on `queue.Empty`
the worker does `continue` and **skips the check entirely**.

Partial cadence — `core/realtime.py::run_realtime_worker` (timer path, the default since
`realtime_transcription_use_syllable_boundaries=False`):
```python
realtime_processing_pause = _safe_get_realtime_pause()   # default 0.2; daemon uses cfg 0.15
while time.time() - last_transcription_time < realtime_processing_pause:
    _sleep_briefly()                                    # time.sleep(0.001)
    if not self.is_running or not self.is_recording: break
_run_realtime_transcription("timer")
```
Partials fire on a **wall-clock timer** every `realtime_processing_pause` (0.15 s in this project),
only while `is_recording`. There is also a publish gate
`completed_at_wall_time - recording_start_time > init_realtime_after_seconds` (default 0.2 s).

### 2b. What breaks if you feed the whole buffer at once
The worker drains every 32 ms chunk microseconds apart (a 3 s silence ≈ 93 chunks processed in
<1 ms). The wall-clock `time.time() - speech_end_silence_start` therefore **never reaches 0.6 s**
during the silent region; then the queue empties and the worker spins on `get(timeout=0.01)`
(`continue`, no check). Concretely:
- **The pause-regression test (criterion b) fails:** the two halves around the 3 s silence merge
  into ONE recording (the silence never triggers a stop), so you get a single final, not both
  halves. This is the core regression you are trying to prove is fixed.
- **The multi-sentence test (criterion c) fails similarly:** no segmentation → 1 final, not 3.
- **The partial-cadence assertions (a) become meaningless:** few/no partials fire for a
  near-instant feed, and `<1.5 s after speech onset` / `every 500 ms` can't be measured.
- The README's single-shot example (`feed_audio(file.read()); text()`) is misleading here — it
  only behaves for trivial single-utterance clips and effectively relies on streaming in practice.

### 2c. The correct pace
Feed slices of duration D and **sleep(D)** after each feed, so wall-clock advances in lock-step
with audio time. `feed_audio` re-slices internally, but across the sleeps the wall-clock silence
accumulates and the threshold fires on the last silence slice of each segment.
- **Chunk size:** anything ≥ ~0.03 s works. A common, simple choice is **0.05–0.10 s slices**
  (e.g. 0.1 s = 1600 int16 samples = 3200 bytes) with `time.sleep(0.1)`. Even feeding at the
  native **0.032 s (512-sample) granularity** with `time.sleep(0.032)` is fine and most faithful.
  Match `sleep` to the *audio duration you fed*, not the processing time.
- **You may feed slightly faster than real-time** (e.g. sleep 0.5×) only if you don't care about
  exact latency numbers, but for the segmentation/latency assertions feed at ~1.0× real-time.
- The effective silence needed to segment is ≈ `deactivity_silence_confirmation_duration (0.16 s)`
  + `post_speech_silence_duration (0.6 s)` ≈ **0.76 s** (see §4). A 3 s gap is ~4× that — robustly
  yields the first half, then resumes. Feeding at exactly real-time is what makes the gap "count".

---

## 3. Clean shutdown (no leaked workers) + threading

### 3a. `shutdown()` is the canonical teardown — and it is idempotent
`core/shutdown.py::shutdown_recorder`:
- Guarded by `recorder.shutdown_lock` + `if recorder.is_shut_down: return` (**idempotent — safe to
  call twice**; the production `VoiceTypingDaemon.shutdown()` also has its own `_shutdown_done` flag).
- Sets `is_shut_down=True`, `is_running=False`, and **sets both `start_recording_event` and
  `stop_recording_event`** to wake any caller blocked in `wait_audio()`/`text()`.
- **Joins** `recording_thread`, `realtime_thread`, and `transcript_process`; closes
  `parent_transcription_pipe`; deletes the realtime model; `gc.collect()`.
- The mic `reader_process` join/terminate is **guarded by `if recorder.use_microphone.value:`** —
  skipped entirely for `use_microphone=False` (and `reader_process` is never even created).
- Also usable as a context manager: `__exit__` calls `self.shutdown()` (`audio_recorder.py`).

### 3b. On Linux the "model worker process" is actually a THREAD
`core/runtime.py::start_recorder_worker` (used for BOTH the transcript worker and the mic reader):
```python
if platform.system() == 'Linux':
    thread = threading.Thread(target=target, args=args)
    thread.deamon = True          # <-- TYPO: sets a junk attr ".deamon", NOT ".daemon"
    thread.start(); return thread
else:
    thread = mp.Process(target=target, args=args); thread.start(); return thread
```
Two consequences for a Linux test (this project targets Linux/systemd):
1. **No `mp.Process` is spawned at all** — `recording_thread`, `realtime_thread`, and
   `transcript_process` are all threads. The daemon.py docstring narrative of "spawn-started model
   worker processes" is true on Windows only; on Linux it is threads. (`mp.Pipe()`/`mp.Event()`/
   `mp.Value()` are still used as in-process sync primitives.)
2. The transcript thread is **non-daemon** due to the `deamon` typo, so it can keep the process
   alive if not joined — i.e. **`shutdown()` really is required**, and a forced-terminate fallback
   (`transcript_process.terminate()`) would actually raise `AttributeError` on a Thread (latent bug;
   harmless in practice because the worker exits promptly once `shutdown_event` is set).

### 3c. `abort()` breaks a blocked `text()` — but call it from ANOTHER thread
`core/lifecycle.py::abort_recording`:
```python
recorder.interrupt_stop_event.set()
if recorder.state != "inactive":
    recorder.was_interrupted.wait()     # <-- BLOCKS until text() notices + sets was_interrupted
```
`was_interrupted` is set inside `text()` after `wait_audio()` returns (when it sees
`interrupt_stop_event` is set). So `abort()` blocks until the thread blocked in `text()` unwinds.
**Never call `abort()` from the same thread that is inside `text()`** (self-deadlock). The
production daemon calls it from the socket thread / a signal-spawned thread, never the main thread
(see `voice_typing/daemon.py` docstring on `install_shutdown_signal_handlers`).

### 3d. Recommended test teardown sequence
1. Stop the **feed thread** (set a done flag; join it).
2. From the **test thread**, call `recorder.abort()` to break the consume thread's blocked
   `text()` (this blocks until `was_interrupted` is set — i.e. until the consume thread unwinds).
3. Join the consume thread.
4. Call `recorder.shutdown()` (joins the worker threads + closes pipes; idempotent).
   Belt-and-suspenders: a `finally:` that calls `shutdown()` even on assertion failure.

### 3e. The `if __name__ == "__main__":` guard
- **For the pytest test on Linux: not exercised.** No `mp.Process` spawn occurs (workers are
  threads; §3b). `mp.set_start_method("spawn")` *is* forced on Linux by `core/safepipe.py` at import
  (`if sys.platform.startswith('linux') or sys.platform == 'darwin': mp.set_start_method("spawn")`),
  but that only affects the *context* used by `mp.Pipe/Event/Value`, which work in-process.
- The guard is relevant for the **production entry point** (`python -m voice_typing.daemon`) and on
  **Windows** (real spawn → child re-imports `__main__`). The test constructs the recorder **inside a
  test function** (never at module import top-level), which is the correct spawn-safe discipline
  regardless.

---

## 4. `post_speech_silence_duration` (0.6 s) vs. a 3 s embedded silence — confirmed two-segment behavior

Default/`config.toml` value is **0.6 s** (`voice_typing/config.py::AsrConfig.post_speech_silence_duration`,
mirrored in `config.toml`; also `audio_recorder.py::INIT_POST_SPEECH_SILENCE_DURATION = 0.6`).
Deactivity confirmation grace is **0.16 s** (`DEACTIVITY_SILENCE_CONFIRMATION_DURATION`, ctor param
`deactivity_silence_confirmation_duration`). Effective gap-to-segment ≈ **0.76 s**.

The full stop decision (`core/recording.py`, recording branch, `stop_recording_on_voice_deactivity`):
1. Per 32 ms chunk, while recording: `is_speech = is_webrtc_speech(...)` (WebRTC by default, since
   `silero_deactivity_detection=False`).
2. If speech → reset `speech_end_silence_start = 0` (and a 0.16 s "candidate silence" grace keeps
   brief pauses from counting: `if now - candidate_start < deactivity_silence_confirmation_duration:
   is_speech = True`).
3. After ~0.16 s of sustained silence → set `speech_end_silence_start = time.time()` (only if
   `time.time() - recording_start_time > min_length_of_recording`, 0.3–0.5 s).
4. Once `time.time() - speech_end_silence_start >= post_speech_silence_duration (0.6 s)` →
   `self.stop()` finalizes the segment.

**Re-arming / resume (the core of the regression):** `wait_for_recorded_audio` sets
`recorder.continuous_listening = True` (and re-arms `start_recording_on_voice_activity`) the first
time it arms listening (no wake-words path). In the worker, after each stop:
```python
if not self.is_recording and was_recording:
    if self.continuous_listening:
        self.start_recording_on_voice_activity = True
        self.stop_recording_on_voice_deactivity = True
```
So **after segmenting the first half at ~0.76 s into the 3 s silence, the recorder immediately
re-listens**, the worker buffers the remaining silence in the pre-roll buffer, detects the second
half's speech, starts a new recording, and segments it at its trailing silence. **Net: a 3 s gap
yields BOTH halves (two finals), exactly the regression behavior to assert.** (Confirmed by code
flow, not just docs.) `min_gap_between_recordings` is **0.0** in this project
(`voice_typing/daemon.py::_FIXED_KWARGS`), so there is no artificial inter-segment delay.

---

## 5. Common pitfalls

1. **Forgetting `enable_realtime_transcription=True`.** The realtime worker exits immediately if it
   is False (`core/realtime.py`: `if not self.enable_realtime_transcription: … return`), and the
   realtime model is never loaded (`_initialize_realtime_transcription_model` guards on it). **No
   `on_realtime_transcription_stabilized` partials will ever fire.** This is set in
   `voice_typing/daemon.py::_FIXED_KWARGS`; the test must ensure the same. Likewise
   `on_realtime_transcription_stabilized` (preferred) vs `on_realtime_transcription_update` (faster,
   rougher) must be wired — the project uses the stabilized one
   (`_PARTIAL_CALLBACK_ATTR`).
2. **Feeding too fast** (whole buffer at once) → wall-clock silence never accumulates → no
   segmentation, halves/sentences merge, partials cadence is meaningless (see §2). **Always pace at
   ~real-time.**
3. **Feeding before `text()` arms listening** → first audio is consumed without starting a
   recording (lost). Start the consume loop, then feed (see §1c).
4. **VAD sensitivity vs synthetic espeak/TTS audio.** Start-detection uses WebRTC (10 ms frames,
   `frame_length = 16000*0.01`; `is_webrtc_speech` returns True if **any** frame is speech at
   `webrtc_sensitivity=3`) then a Silero confirmation thread; Silero threshold is
   `vad_prob > (1 - silero_sensitivity)` = `> 0.6` at the project's `silero_sensitivity=0.4`
   (`core/voice_activity.py`). Clean espeak speech is detected reliably, but: (a) the WAV must begin
   with actual speech shortly after a short lead-in (a few hundred ms of silence is fine — VAD is
   armed and waiting); (b) the inter-sentence/inter-half silence must be **truly silent** (exact
   zero samples) so WebRTC registers silence; (c) very low-volume synth audio may need
   `silero_sensitivity` bumped or `normalize_audio=True`.
5. **GPU vs CPU model load differences (latency).** `final_model="distil-large-v3"`,
   `realtime_model="small.en"`, `device="cuda"` (`config.toml`). `_initialize_transcription_runtime`
   downgrades to `"cpu"` if `device=="cuda" and not torch.cuda.is_available()`. On CPU, final
   transcription of `distil-large-v3` can take **>1 s**, which can blow the
   `final-latency <=1.5 s` assertion (criterion e). For deterministic CI, either (a) gate the strict
   latency assertion on CUDA availability, or (b) use the CPU-fallback smaller models
   (`small.en`/`tiny.en`) for the test, or (c) widen the budget on CPU. The `cuda_check` CPU
   fallback (`voice_typing/cuda_check`) selects `cpu/int8/small.en/tiny.en`.
6. **Construction takes seconds + writes `realtimesst.log`.** `__init__` blocks on
   `main_transcription_ready_event.wait()` (model warmup) and, unless `no_log_file=True`, opens a
   `realtimestt.log` file handler in the cwd (`_configure_logger`). For tests, prefer
   `no_log_file=True` (or accept the file) and construct **once per session** (module-scoped
   fixture) — do not construct per-test. `warmup_vad=True` (default) already primes VAD so the first
   chunk doesn't pay lazy setup.
7. **Construction also forces `mp.set_start_method("spawn")`** (`core/safepipe.py`, Linux+macOS).
   If the test process has already set a different method it raises `RuntimeError` (caught + logged
   in safepipe) — harmless, but means recorder init has a process-global side effect; construct at
   most one recorder per process and don't fight the start method.
8. **`abort()` from the wrong thread = deadlock.** Call it only from a thread that is NOT blocked
   in `text()`/`wait_audio()` (§3c).
9. **Not calling `shutdown()` = the transcript thread + pipes linger.** On Linux the transcript
   worker is a **non-daemon thread** (the `.deamon` typo, §3b), so it can keep the pytest process
   alive / leak resources. Always `shutdown()` in `finally`.

---

## Concrete test scaffolding (cite-able pseudocode)

```python
# tests/test_feed_audio.py — OFFLINE integration test (real models; heavy; ~1 per process)
import threading, time, numpy as np, soundfile as sf, pytest

def _feed_paced(recorder, samples_int16, *, stop, chunk_s=0.1):
    """Feed 16-bit mono @16k at ~real-time so VAD wall-clock timing behaves."""
    n = int(16000 * chunk_s)
    i = 0
    while i < len(samples_int16) and not stop.is_set():
        slc = samples_int16[i:i+n]
        recorder.feed_audio(slc, original_sample_rate=16000)   # int16 array; auto-sliced to 32ms
        i += n
        time.sleep(len(slc) / 16000.0)                          # pace at real-time
    # pad trailing silence so the last segment's stop threshold can fire
    tail = np.zeros(int(16000 * 1.0), dtype=np.int16)
    recorder.feed_audio(tail, original_sample_rate=16000); time.sleep(1.1)

def _consume(recorder, finals, stop, max_finals):
    while len(finals) < max_finals and not stop.is_set():
        # text(cb) BLOCKS per utterance; cb fires async with already-computed text
        recorder.text(lambda t: finals.append(t))

@pytest.fixture(scope="session")
def recorder():
    from RealtimeSTT import AudioToTextRecorder
    r = AudioToTextRecorder(
        use_microphone=False,
        enable_realtime_transcription=True,
        model="small.en", realtime_model_type="tiny.en",   # CPU-friendly for CI
        device=("cuda" if _cuda() else "cpu"), compute_type=("float16" if _cuda() else "int8"),
        post_speech_silence_duration=0.6, realtime_processing_pause=0.15,
        silero_sensitivity=0.4, webrtc_sensitivity=3, silero_backend="auto",
        ensure_sentence_starting_uppercase=False, ensure_sentence_ends_with_period=False,
        no_log_file=True, spinner=False,
        on_realtime_transcription_stabilized=_collect_partial,
    )
    yield r
    try: r.abort()
    except Exception: pass
    r.shutdown()                                  # joins threads, closes pipes (idempotent)

def test_pause_keeps_both_halves(recorder, wav_pause):  # criterion (b)
    finals, stop = [], threading.Event()
    c = threading.Thread(target=_consume, args=(recorder, finals, stop, 2)); c.start()
    samples, sr = sf.read(wav_pause, dtype="int16")      # 16k mono int16, 3s gap mid-file
    try:
        _feed_paced(recorder, samples, stop=stop)
        _wait_until(lambda: len(finals) >= 2, timeout=...)
        assert len(finals) >= 2                        # BOTH halves -> core regression fixed
    finally:
        stop.set(); recorder.abort(); c.join(timeout=5)
```
Notes for the PRP: keep the recorder in a **session-scoped fixture** (construction is slow); feed
**at real-time**; start the consume thread **before** feeding; tear down with **abort() → join →
shutdown()** in a `finally`; gate the strict `<=1.5 s` latency assertions on CUDA (or use small
models on CPU).

---

## Source map (file → symbol → what it proves)

Installed at `.venv/lib/python3.12/site-packages/RealtimeSTT/` (v1.0.2):
- `audio_recorder.py` — `AudioToTextRecorder.__init__` (full ~85-param signature; defaults
  `INIT_POST_SPEECH_SILENCE_DURATION=0.6`, `INIT_REALTIME_PROCESSING_PAUSE=0.2`,
  `INIT_SILERO_SENSITIVITY=0.4`, `BUFFER_SIZE=512`, `SAMPLE_RATE=16000`,
  `DEACTIVITY_SILENCE_CONFIRMATION_DURATION=0.16`); `feed_audio()`, `text()`, `abort()`,
  `set_microphone()`, `shutdown()`, `__exit__`.
- `core/manual_audio_input.py::feed_audio` — buffering + 32 ms (1024-byte) re-slicing into
  `audio_queue`; non-blocking; resample-to-16k.
- `core/transcription_api.py::text` — BLOCKS in `wait_audio()` + `transcribe()`; callback is async
  delivery of already-computed text; loop for multiple finals.
- `core/lifecycle.py::wait_for_recorded_audio` — per-segment block on
  `start/stop_recording_event`; arms `continuous_listening`. `abort_recording` — sets
  `interrupt_stop_event` then blocks on `was_interrupted.wait()`.
- `core/recording.py::run_recording_worker` — one chunk/loop; wall-clock
  `post_speech_silence_duration` stop check; `deactivity_silence_confirmation_duration` 0.16 s
  grace; `min_length_of_recording` gate; re-arm after stop when `continuous_listening`.
- `core/realtime.py::run_realtime_worker` — early-returns if `!enable_realtime_transcription`;
  wall-clock `realtime_processing_pause` timer cadence; `init_realtime_after_seconds` publish gate.
- `core/initialization.py` — `audio_queue = mp.Queue() if use_microphone else queue.Queue()`;
  mic reader only if `use_microphone.value`; `_start_worker_threads` (daemon threads);
  realtime model only if `enable_realtime_transcription`; `__init__` blocks on
  `main_transcription_ready_event`.
- `core/runtime.py::start_recorder_worker` — Linux=Thread (`.deamon` typo), else `mp.Process`.
- `core/shutdown.py::shutdown_recorder` — idempotent; wakes blocked `text()`; joins threads +
  transcript_process (skips mic reader); closes pipe.
- `core/safepipe.py` — forces `mp.set_start_method("spawn")` on Linux/macOS at import;
  `SafePipe()` wraps `mp.Pipe()` in a thread-serialized `ParentPipe`.
- `core/voice_activity.py` — `is_webrtc_speech` (10 ms frames, any-frame-True);
  `is_silero_speech` threshold `vad_prob > 1 - silero_sensitivity`; VAD warmup.
- `realtimestt-1.0.2.dist-info/METADATA` — version 1.0.2; embedded README (Microphone / Automatic
  Recording Loop / External Audio examples; `if __name__ == "__main__":` note for Windows spawn).
- `voice_typing/daemon.py` — production loop `while …: recorder.text(self.on_final)`;
  `_FIXED_KWARGS` (enable_realtime_transcription=True, post_speech_silence via cfg, min_gap=0.0);
  `shutdown()` idempotent; `abort()`-from-other-thread discipline.
- `voice_typing/config.py` / `config.toml` — `post_speech_silence_duration=0.6`,
  `realtime_processing_pause=0.15`, `final_model="distil-large-v3"`, `realtime_model="small.en"`.

External (repo-only, not in wheel — cited for the PRP, URLs): KoljaB/RealTimeSTT GitHub
`README.md` "External Audio" section; `docs/external-audio.md`; `docs/quick-start.md`;
`docs/testing.md` ("keeps fast unit tests separate from opt-in real-model tests");
`tests/realtimestt_test.py` (CLI demo).

---

## Gaps / residual uncertainty

- **Exact README "External Audio" pacing example** (`docs/external-audio.md`, `docs/quick-start.md`)
  is NOT shipped in the wheel and could not be fetched (no web access). The README's single-shot
  example is the only in-wheel reference and is *not* paced; the pacing requirement is derived
  rigorously from the worker source (§2) rather than from an example. If a streamed/paced example
  exists upstream it would corroborate §2c but is not needed for correctness.
- **Measured latencies on the actual deployment GPU** are not characterized here (no model load
  performed — this is a read-only research pass). Recommend a one-off smoke run to pick the
  `distil-large-v3` final-latency budget vs. CPU-fallback budgets before pinning the `<=1.5 s`
  assertion (criterion e).
- **`transcript_process.terminate()` AttributeError on Linux** if the thread doesn't exit within
  the 10 s join (§3b, latent bug) — observed-by-code only, not reproduced. If a test ever hangs at
  shutdown, this is the first place to look.
