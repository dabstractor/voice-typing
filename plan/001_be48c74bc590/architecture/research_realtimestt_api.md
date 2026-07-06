# Research Brief: RealtimeSTT v1.0.2 — API Verification

**Status:** VERIFIED against cloned RealtimeSTT v1.0.2 source (setup.py `current_version="1.0.2"`).
This is the project's #1 risk ("API drift vs this doc"). Every claim below is backed by the actual v1.0.2 code (file:line).

---

## 1. CONSTRUCTOR — `AudioToTextRecorder(...)` kwargs (audio_recorder.py:94)

Every kwarg the PRD §4.4 assumes — VERDICT:

| PRD-assumed kwarg | VERDICT | Evidence (audio_recorder.py) | Notes |
|---|---|---|---|
| `model` | ✅ CONFIRMED | :95 `model: str = INIT_MODEL_TRANSCRIPTION` ("tiny") | Accepts short name `distil-large-v3` |
| `realtime_model_type` | ✅ CONFIRMED | :119 `realtime_model_type=INIT_MODEL_TRANSCRIPTION_REALTIME` ("tiny") | Accepts `small.en` |
| `language` | ✅ CONFIRMED | :99 `language: str = ""` | `"en"` works |
| `device` | ✅ CONFIRMED | :106 `device: str = "cuda"` | **default IS "cuda"** |
| `compute_type` | ✅ CONFIRMED | :100 `compute_type: str = "default"` | "float16" works (PRD's uncertainty resolved: YES it's a kwarg) |
| `gpu_device_index` | ✅ CONFIRMED | :105 `gpu_device_index: Union[int, List[int]] = 0` | |
| `enable_realtime_transcription` | ✅ CONFIRMED | :114 `enable_realtime_transcription=False` | |
| `realtime_processing_pause` | ✅ CONFIRMED | :120 default 0.2 | PRD's 0.15 fine |
| `use_main_model_for_realtime` | ✅ CONFIRMED | :115 `=False` | two-model mode works |
| `post_speech_silence_duration` | ✅ CONFIRMED | :137 default INIT=0.6 (audio_recorder.py:64) | ⚠️ docstring text says 0.2 (stale); ACTUAL default 0.6. PRD's 0.6 matches. |
| `min_length_of_recording` | ✅ CONFIRMED | :139 default INIT=0.5 | PRD's 0.3 fine (explicit) |
| `min_gap_between_recordings` | ✅ CONFIRMED | :142 default INIT=0 (:66) | PRD's 0.0 matches; ⚠️ docstring says 1.0 (stale) |
| `silero_sensitivity` | ✅ CONFIRMED | :127 default 0.4 | PRD's 0.4 matches |
| `webrtc_sensitivity` | ✅ CONFIRMED | :130 default 3 | PRD's 3 matches |
| `silero_use_onnx` | ⚠️ LEGACY (works but superseded) | :128 `silero_use_onnx: Optional[bool] = None` | Legacy switch. Modern control is **`silero_backend`** (default `"auto"`) which prefers raw CPU ONNX (`silero_vad_op18_ifless.onnx`) — already avoids torch-hub download. **RECOMMENDATION: drop `silero_use_onnx=True`; rely on `silero_backend="auto"` default.** If explicit ONNX desired, set `silero_backend="raw_onnx"`. |
| `spinner` | ✅ CONFIRMED | :109 `spinner=True` | `False` works |
| `use_microphone` | ✅ CONFIRMED | :108 `use_microphone=True` | `False` + feed_audio for tests |
| `input_device_index` | ✅ CONFIRMED | :101 `input_device_index: int = None` | None → default source |
| `on_realtime_transcription_stabilized` | ✅ CONFIRMED | :123 | callback(str) |
| `on_realtime_transcription_update` | ✅ CONFIRMED | :122 | callback(str) |
| `on_recording_start` | ✅ CONFIRMED | :103 | callback() no-arg |
| `on_recording_stop` | ✅ CONFIRMED | :104 | callback() no-arg |

**Other useful v1.0.2 kwargs not in PRD (consider):**
- `ensure_sentence_starting_uppercase=True` / `ensure_sentence_ends_with_period=True` (:101-103 region) — built-in text post-proc. ⚠️ These auto-capitalize/auto-period the output. Since `textproc.py` does its own cleaning, consider setting BOTH `False` to avoid double-processing / fighting punctuation. DECISION POINT for implementer.
- `early_transcription_on_silence: int = 0` — if >0, starts final transcription `N ms` before full silence elapsed → latency optimization. Could help hit the 1.5s target. (optional tuning knob)
- `silero_backend: str = "auto"` (:167 region) — modern Silero backend selector (replaces silero_use_onnx intent).
- `faster_whisper_vad_filter: bool = True` — additional faster-whisper internal VAD.
- `transcription_engine="faster_whisper"` (:96) — confirms CTranslate2 is the engine.
- `silero_onnx_threads`, `deactivity_silence_confirmation_duration` — fine tuning.
- `beam_size=5`, `beam_size_realtime=3` — beam search width.

---

## 2. MAIN LOOP / LISTEN-FOREVER — `text()` ✅ CONFIRMED (README:104-106, transcription_api.py:22)

```python
recorder = AudioToTextRecorder(...)
while True:
    recorder.text(process_text)   # blocks until one utterance finalizes; callback fired async; loop resumes listening
```

`text(on_transcription_finished=None)` (transcription_api.py:22):
- clears `interrupt_stop_event`, calls `recorder.wait_audio()` (blocks until VAD closes one utterance),
- then if callback given: spawns a **NEW THREAD** running `on_transcription_finished(recorder.transcribe())` — so transcription/typing happens off the listen loop → **continuous dictation, loop immediately re-listens**.
- returns `""` if shut down or interrupted.

**This is the exact mechanism that fixes the WhisperX flaw:** `post_speech_silence_duration` only SEGMENTS (finalizes the current sentence); the `while` loop re-enters `text()` and keeps the mic open indefinitely. The session ends ONLY on explicit toggle/quit. ✅✅✅

⚠️ **MULTIPROCESSING GUARD REQUIRED (README:76-78):** "Use the `if __name__ == "__main__":` guard when running scripts... because RealtimeSTT uses multiprocessing for model work." → daemon.py entry point MUST wrap `main()` in `if __name__ == "__main__":`. systemd ExecStart `.venv/bin/python -m voice_typing.daemon` sets `__name__=="__main__"` correctly. Linux uses fork() for multiprocessing by default (guard less critical than Windows, but keep it).

---

## 3. CALLBACKS — signatures ✅ CONFIRMED (audio_recorder.py docstrings :294-375)

| Callback | Arg | Fires when |
|---|---|---|
| `on_realtime_transcription_update` | **`str`** (the new partial text) | every realtime pass — fast, rougher |
| `on_realtime_transcription_stabilized` | **`str`** (stabilized partial, more accurate, slight delay) | preferred for tmux-status partial feed |
| `on_realtime_text_stabilization_update` | structured event | (new, structured form — optional) |
| `on_recording_start` | none | recording begins |
| `on_recording_stop` | none | recording ends |
| `on_transcription_start` | `audio_copy` (can return truthy to ABORT) | final transcription begins |
| `on_vad_start` | none | voice activity PRESENCE starts → map to phase `"speaking"` |
| `on_vad_stop` | none | voice activity ends |
| `on_vad_detect_start` | none | system starts LISTENING for VAD → map to phase `"listening"` |
| `on_vad_detect_stop` | none | system stops listening for VAD |
| `on_turn_detection_start` / `on_turn_detection_stop` | none | turn-of-speech boundaries |

**Feedback phase mapping (for feedback.py state.json `phase` field):**
- `idle` ← default / toggle-off
- `listening` ← `on_vad_detect_start`
- `speaking` ← `on_vad_start`
- (back to `listening`) ← `on_vad_stop`

⚠️ PRD §4.2 says "wire `on_recording_start`/`on_vad_detect_start`" — more precisely: `on_vad_detect_start`→listening, `on_vad_start`→speaking. Confirmed these exist.

---

## 4. PAUSE/RESUME LISTENING while keeping models resident ✅ CONFIRMED

Multiple sanctioned mechanisms (lifecycle.py:241 `abort_recording`, audio_recorder.py:718 `set_microphone`, :712 `abort`):

1. **`recorder.set_microphone(False)`** (audio_recorder.py:718) — sets `self.use_microphone.value = False`. Stops live mic capture WITHOUT destroying recorder/models. ✅ Resume with `set_microphone(True)`. **This is the cleanest toggle.**
2. **`recorder.abort()`** (audio_recorder.py:712 → lifecycle.py:241 `abort_recording`) — sets `interrupt_stop_event` + calls `recorder.stop()`. If called while `text()` is blocking in `wait_audio()`, the interrupt causes `text()` to return `""` (no transcription typed) → loop resumes. ✅ Use this to break out of a blocked `text()` on toggle-off.
3. **`recorder.stop()`** (audio_recorder.py:629 → `stop_recording`) — stops the current recording (with optional backdating).
4. **`recorder.listen()`** (:649) — puts recorder back in voice-activity-listening state.

**RECOMMENDED toggle-off sequence (preserves GPU residency):**
```python
# toggle OFF:
recorder.set_microphone(False)     # stop mic capture
recorder.abort()                   # break any blocked text()/wait_audio()
listening_event.clear()
# gate inside on_final too (one utterance may complete mid-toggle) — PRD §4.2 ✅

# toggle ON:
listening_event.set()
recorder.set_microphone(True)
# loop's next recorder.text(on_final) resumes (or was never exited)
```
The recorder object is constructed ONCE at daemon start → models stay resident on GPU → instant toggle-on. ✅ matches PRD §4.2 "construct once".

**`recorder.shutdown()`** (:749) — full teardown; ONLY on daemon quit, never on toggle.

---

## 5. OFFLINE TEST — `feed_audio()` ✅ CONFIRMED (audio_recorder.py:694, README external-audio)

```python
recorder = AudioToTextRecorder(use_microphone=False)
recorder.feed_audio(chunk, original_sample_rate=16000)   # 16-bit mono PCM @16kHz, OR pass original rate for resampling
print(recorder.text())
recorder.shutdown()
```
- `chunk`: audio **bytes** (16-bit mono PCM) OR a **NumPy array**.
- `original_sample_rate`: default 16000; pass the WAV's rate to let RealtimeSTT resample.
- `use_microphone=False` switches the input pipeline to the manual `feed_audio` path (core/manual_audio_input.py). ✅
- For T1 test: feed WAV chunks at real-time pacing, collect partial-callback events + finals. ✅ feasible exactly as PRD §6 T1 describes.

**Test-audio resampling note:** espeak-ng output (via sox/ffmpeg) must be 16 kHz mono 16-bit PCM (RealtimeSTT SAMPLE_RATE=16000, BUFFER_SIZE=512). Confirmed from audio_recorder.py:73-74.

---

## 6. VERSION / BREAKING CHANGES

- Latest: **1.0.2** (setup.py). PRD assumption (v1.0.2, May 2026) ✅ CONFIRMED.
- 0.3.x → 1.0.x evolution: the API surface expanded substantially (silero_backend, realtime_text_stabilizer, boundary detector, turn detection, manual_audio_input module). The core PRD-used methods (`text`, `feed_audio`, `abort`, `set_microphone`, `shutdown`, the `on_*` callbacks) are **stable and present**. No breaking removal of anything the PRD relies on.
- The package is now multi-module (`RealtimeSTT/core/`, `transcription_engines/`) — construction cost (model load) happens in `__init__`; keep it once.

---

## SUMMARY OF CORRECTIONS TO PRD (for breakdown)

1. ⚠️ `silero_use_onnx=True` is LEGACY — replace with `silero_backend="auto"` (default, already avoids torch-hub). Drop the legacy kwarg (or it may conflict with `silero_backend`).
2. ✅ `compute_type` and `device="cuda"` ARE valid kwargs — use them directly.
3. ⚠️ `ensure_sentence_starting_uppercase` / `ensure_sentence_ends_with_period` default True — decide whether to disable (textproc does its own cleanup). DECISION: set both False to keep textproc authoritative.
4. ✅ Toggle-off via `set_microphone(False)` + `abort()` (breaks blocked `text()`), plus in-callback gate. Models stay resident.
5. ✅ `feed_audio(chunk, original_sample_rate=16000)` accepts bytes or numpy; 16kHz mono 16-bit PCM.
6. ⚠️ `if __name__ == "__main__":` guard REQUIRED (multiprocessing). daemon.py must wrap main().
7. ✅ Listen-forever `while True: recorder.text(cb)` is the canonical continuous-dictation pattern — exactly the WhisperX-flaw fix.
8. ✅ Partials: `on_realtime_transcription_stabilized(str)` (preferred) + `on_realtime_transcription_update(str)` (fallback). State: `on_vad_detect_start`→listening, `on_vad_start`→speaking.
9. Optional latency knob: `early_transcription_on_silence` (ms) can pre-start final transcription to help hit the 1.5s target. Note for tuning subtask.
