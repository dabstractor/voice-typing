# RealtimeSTT v1.0.2 internals — prompts, realtime pipeline, audio abort

Installed package: `/home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/RealtimeSTT/`
(dist-info: `.venv/lib/python3.12/site-packages/realtimestt-1.0.2.dist-info/METADATA` — `Version: 1.0.2`; PRD claim **confirmed**).
All paths below are relative to that package dir unless they start with `voice_typing/`.

## 1. Version
`realtimestt-1.0.2.dist-info/METADATA:2` → `Version: 1.0.2`.

## 2. Constructor kwargs (audio_recorder.py)
`AudioToTextRecorder.__init__` signature at `audio_recorder.py:115-580` (all kwargs documented at lines 263-500). Confirmed present:
- `initial_prompt: Optional[Union[str, Iterable[int]]] = None` — `audio_recorder.py:174`
- `initial_prompt_realtime: Optional[Union[str, Iterable[int]]] = None` — `audio_recorder.py:175`
- `post_speech_silence_duration: float = INIT_POST_SPEECH_SILENCE_DURATION (0.2)` — `audio_recorder.py:132-134`, doc default 0.2 at `:339`
- `use_main_model_for_realtime=False` — `audio_recorder.py:116`
- `on_realtime_transcription_update=None` — `audio_recorder.py:122`; plus `on_realtime_transcription_stabilized` (stabilized variant)

## 3. initial_prompt consumption — VERDICT: constructor-static (both)
Storage: `core/initialization.py:246-247` sets `recorder.initial_prompt` / `recorder.initial_prompt_realtime` from init args.

**Final (main) model — fully static, unreachable after construction:**
- `core/initialization.py:403-419`: `_start_transcription_worker` passes `recorder.initial_prompt` as a *process argument* to `start_recorder_worker(run_transcription_worker, ...)`.
- `core/transcription.py:30-48`: `TranscriptionWorker.__init__` stores it; `core/transcription.py:93-107` bakes it into a `TranscriptionEngineConfig` **once, in a separate worker process**, then the loop (`core/transcription.py:134-142`) calls `engine.transcribe(audio, language, use_prompt)` per request — the config object is never rebuilt.
- ⇒ Setting `recorder.initial_prompt` after construction has **zero effect** on finals. The engine lives in the worker subprocess; the recorder holds no reference. The worker pipe protocol is `(audio, language, use_prompt)` tuples only (`core/transcription.py:226`) — no prompt-update channel.

**Realtime model — static default, but the live engine config is mutable in place:**
- `core/initialization.py:428-476`: `_initialize_realtime_transcription_model` bakes `recorder.initial_prompt_realtime` into `TranscriptionEngineConfig(initial_prompt=...)` of `recorder.realtime_transcription_model` (an engine object living **in the recorder's own process**). Skipped entirely when `use_main_model_for_realtime=True` (init guard at `core/initialization.py:434-437`).
- Per-chunk read path: `core/realtime.py:279-310` `_transcribe_with_realtime_model` → `model.transcribe(audio, language, use_prompt=True)` → `transcription_engines/faster_whisper_engine.py:60-64` builds kwargs per call with `"initial_prompt": self._get_prompt(use_prompt)` → `transcription_engines/base.py:163-166` `_get_prompt` returns `self.config.initial_prompt` **read on every transcribe call**.
- ⇒ **Dynamic poke for realtime partials: `recorder.realtime_transcription_model.config.initial_prompt = <str>`** (the engine holds `self.config` — `base.py:117-119`). Takes effect on the next realtime pass (≤ `realtime_processing_pause`, default 0.2 s).
- Setting `recorder.initial_prompt_realtime` itself is inert post-construction (it is only read at `initialization.py:475`).
- **Lite mode trap:** our lite mode uses `use_main_model_for_realtime=True` (`voice_typing/daemon.py:209`), so realtime partials go through `_transcribe_with_main_model` (`core/realtime.py:239-275`) → the **worker subprocess** pipe → the static worker config. In lite mode, *neither* prompt is pokable without recorder rebuild.

**When consumed:**
- Final prompt: once at worker start (config build), applied per final-transcribe request (every `.text()` final).
- Realtime prompt: re-read from engine config per realtime pass (every ~`realtime_processing_pause` s while recording, or per syllable boundary when `realtime_transcription_use_syllable_boundaries`).

## 4. Realtime pipeline
- `core/realtime.py:30` `run_realtime_worker(recorder)` runs on `recorder.realtime_thread` (a daemon thread started by init).
- Loop at `core/realtime.py:915-967`: while `is_recording`, wait `realtime_processing_pause` (default 0.2 s, `core/realtime.py:58`) then `_run_realtime_transcription("timer")` (`core/realtime.py:649`). Skips while `awaiting_speech_end`.
- `use_main_model_for_realtime=True`: `_transcribe_with_main_model` (`core/realtime.py:239-275`) grabs `transcription_lock` and round-trips `(audio, language, True)` over `parent_transcription_pipe` to the same `TranscriptionWorker` engine that does finals — 5 s poll timeout, serialized with finals via the lock.
- `=False`: dedicated `realtime_transcription_model` engine object, called in-thread.
- Stabilization: `core/realtime.py:509-633` `_publish_realtime_text` feeds a `RealtimeTextStabilizer` (`core/realtime_text_stabilizer.py`, 1060 lines) which accepts/rejects observations and emits stable deltas; callbacks fired via `core/realtime_callbacks.py:13-24`: `on_realtime_transcription_update(text)` gets raw text, `on_realtime_transcription_stabilized(text)` gets stabilized text — both only while `is_recording`.

## 5. Audio flow / abort
- `feed_audio(chunk, original_sample_rate=16000)` — `audio_recorder.py:694` → `core/manual_audio_input.py:9-31`: resamples to 16 kHz, accumulates `recorder.buffer` (bytearray), slices into Silero-sized chunks onto `recorder.audio_queue` (a plain `queue.Queue`; single-consumer recording thread — our usage is mic-driven, so not on this path).
- Utterance end: VAD speech-end → `core/recording.py:371-394` after `post_speech_silence_duration` of silence → `stop()` → `core/lifecycle.py:110` `queue_recorded_audio` deep-copies frames into `recorded_audio_queue` and clears `recorder.frames` (`core/recording_buffers.py:68-84`). `wait_audio()` pops it, `transcribe()` deep-copies into `recorder.audio` and submits to the worker (`core/transcription_api.py:46-58, 72-115`).
- **Abort primitive exists natively:** `recorder.abort()` (`audio_recorder.py:712-716`) → `core/lifecycle.py:241-256` `abort_recording`: sets `interrupt_stop_event`, waits `was_interrupted`, forces state to "transcribing", and calls `stop()` if still recording. A blocked `.text()` returns `""` when `interrupt_stop_event` is set (`core/transcription_api.py:26-34`); an in-flight final loop bails and returns `""` (`core/transcription_api.py:99-104`).
- **BUT abort does NOT discard buffered audio:** it still calls `stop()` → the utterance frames are *queued* into `recorded_audio_queue`, and leftover `frames`/`last_frames` remain — a later `text()` will transcribe that stale audio (this is exactly the double-type bug `voice_typing/recorder_host.py:587-622 _clear_recorder_audio` works around). `clear_audio_queue()` (`audio_recorder.py:728-732`) drains only `audio_queue` + pre-recording buffer.
- **Mid-utterance discard:** no single native primitive; the recipe is `abort()` + manual clears of `recorded_audio_queue` / `frames` / `last_frames` / `audio` / `buffer` (what `_clear_recorder_audio` does). An in-flight worker transcription result already sent is dropped because `perform_final_transcription` returns `""` when `interrupt_stop_event` is set.
- `shutdown()` (`audio_recorder.py:749` → `core/shutdown.py:12-69`): sets `shutdown_event`, joins reader/recorder processes (10 s then terminate), closes pipes, joins realtime thread, deletes the realtime engine. Not a per-utterance tool.

## 6. post_speech_silence_duration
Enforced by the recorder thread's VAD loop: `core/recording.py:371-374` — when `time.time() - self.speech_end_silence_start >= self.post_speech_silence_duration`, fires `on_vad_stop`, appends the final chunk, and stops the recording (→ final decode begins). Realtime partials keep flowing independently during this window (realtime loop only pauses during `awaiting_speech_end`), so finals lag partials by ~this duration + final-model decode time. It is read from `self` each iteration (`recording.py:373`), so it IS dynamically mutable per utterance.

## 7. Our usage (voice_typing)
- `voice_typing/daemon.py:160-216 cfg_to_kwargs`: builds kwargs from `cfg.asr` (`model`, `realtime_model_type`, `language`, `device`, `compute_type`, `realtime_processing_pause`, `post_speech_silence_duration` — `daemon.py:200-207`) + `_FIXED_KWARGS` (`daemon.py:99-112`: `enable_realtime_transcription=True`, `use_main_model_for_realtime=False`, VAD tunables, `use_microphone=True`…). **No `initial_prompt`/`initial_prompt_realtime` is passed today** (defaults None). Lite mode: `use_main_model_for_realtime=True`, `post_speech_silence_duration=cfg.asr.lite_post_speech_silence_duration` (`daemon.py:209-213`).
- `voice_typing/recorder_host.py:440-620 _child_main`: child subprocess builds the recorder via `build_recorder(cfg, relay_fb, relay_lat, on_speech, lite)`; command loop over `cmd_q` handles `text` (blocks in `recorder.text(child_on_final)`), `arm`/`disarm` (`set_microphone` + `_clear_recorder_audio` on disarm), `abort`, `shutdown`. A dedicated `_abort_handler` thread watches `abort_event` → `recorder.abort()` (unblocks the sleeping `text()`).
- Partials/finals ship to the daemon over `evt_q`: `("partial", {text})` (via `_RelayFeedback.update_partial`, wired to `on_realtime_transcription_stabilized` — `daemon.py:120-124 _PARTIAL_CALLBACK_ATTR`), `("final", {text})`, `("speech", {})`. Reader thread dispatches at `recorder_host.py:332-382`.
- **Poke slot:** a new `("prompt", {"text": ...})` command in the child command loop → set `recorder.realtime_transcription_model.config.initial_prompt` (guard for None/lite). It is *not* deliverable while the loop is blocked in `text()` — same constraint as `abort`; a prompt update needs either a second watcher thread (mirror of `_abort_handler`) or a `mp.Event`+shared-value side channel. Best time to apply: on final emission / between utterances.
- For **finals**, the only dynamic-prompt options are (a) rebuild the recorder (expensive), or (b) upstream a prompt-update message to the worker protocol — not available in v1.0.2 as installed. Rolling-context for finals must therefore rely on constructor-time `initial_prompt` (per recorder build), or accept partials-only dynamism.

## Summary table
| Item | Value |
|---|---|
| `initial_prompt` (finals) | Constructor-static; baked into worker-process engine config at `core/transcription.py:93-107`. Not pokable. |
| `initial_prompt_realtime` | Baked into in-process engine config at `core/initialization.py:475`; **live-pokable via `realtime_transcription_model.config.initial_prompt`** (read per pass at `base.py:163-166`), except lite mode (main-model path). |
| Mid-utterance discard | Native `abort()` exists but does NOT drop buffers; must pair with clears of `recorded_audio_queue`/`frames`/`last_frames`/`audio` (our `_clear_recorder_audio` already implements this). |
