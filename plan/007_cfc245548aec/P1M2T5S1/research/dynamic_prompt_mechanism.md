# P1.M2.T5.S1 research — child-side dynamic initial_prompt in RealtimeSTT 1.0.2

Sources: installed venv `.venv/lib/python3.12/site-packages/RealtimeSTT/` (read directly),
`plan/007_cfc245548aec/architecture/realtimestt_internals.md` (prior deep-dive, still accurate),
`voice_typing/{recorder_host,daemon,config}.py`.

## The problem
- `initial_prompt` (finals) is baked into the **spawned** TranscriptionWorker process at start
  (`core/transcription.py:30-48,93-107`; worker started via `spawn` context —
  `core/initialization.py:355`, `core/safepipe.py:17`). Worker pipe protocol is only
  `(audio, language, use_prompt)` tuples (`core/transcription.py:226`) — no prompt-update channel.
  Post-construction `recorder.initial_prompt = ...` is inert.
- `initial_prompt_realtime` would be live-pokable via
  `recorder.realtime_transcription_model.config.initial_prompt` (read per pass,
  `transcription_engines/base.py:163-166`) — BUT our single mode uses
  `use_main_model_for_realtime=True` (`voice_typing/daemon.py:189`), which skips the realtime
  engine (`core/initialization.py:454-456`) and routes partials through the worker pipe
  (`core/realtime.py:239-275` → static prompt). Neither prompt is pokable on our path.

## The fix: external transcription executors (verified in installed v1.0.2)
`AudioToTextRecorder(transcription_executor=..., realtime_transcription_executor=...)`
(`audio_recorder.py:191-192`):
- `recorder._uses_external_transcription_executor = transcription_executor is not None`
  (`core/initialization.py:291-298`).
- When set, the worker process is **never spawned** (`core/initialization.py:387-395`:
  no SafePipe, `main_transcription_ready_event.set()` immediately) — no duplicate model, one less
  process to kill at teardown.
- Finals: `submit_transcription_request` (`core/transcription.py:193-236`) runs
  `call_transcription_executor(executor, audio, language, use_prompt)` on a daemon **thread in the
  recorder's own process** (= our recorder_host child) and puts `("success", result)` on
  `recorder._external_transcription_results`.
- Partials: `_realtime_transcription_target` (`core/realtime.py:282-291`) checks
  `_uses_external_realtime_transcription_executor` FIRST — even with
  `use_main_model_for_realtime=True` (`_transcribe_with_main_model`, `core/realtime.py:245-250`,
  branches to the executor before touching the pipe). So passing the SAME executor object to both
  kwargs handles partials + finals with one model instance.
- Executor protocol: object-style if it has `.transcribe` — called as
  `executor.transcribe(audio, language=<str|None>, use_prompt=True)`
  (`core/transcription.py:176-190`). Return value is consumed as
  `result.text`, `result.info.language`, `result.info.language_probability`
  (`core/transcription_api.py:106-113`) — i.e. the `TranscriptionResult` dataclass from
  `transcription_engines/base.py:21-27` (`text: str`, `info: TranscriptionInfo`). Exceptions are
  caught → `("error", str(exc))`.
- Executor must self-warm: the built-in warmup path (`core/transcription.py:120-128` warmup_audio)
  belongs to the worker we no longer use.
- Executor is called from ≥2 threads (realtime thread + external-final threads) → needs an
  internal lock around the faster_whisper model. Prompt is a plain attribute read per call —
  atomic in CPython, updated only between utterances.

## faster-whisper call
Executor loads `faster_whisper.WhisperModel(model_path, device=..., compute_type=...)` itself
(mirroring `transcription_engines/faster_whisper_engine.py:40-64`):
`model.transcribe(audio, language=..., initial_prompt=<current prompt>, beam_size=..., vad_filter=..., condition_on_previous_text=...)`.
Model path resolution: the engine resolves model ids via huggingface; ours is already resolved by
`cuda_check` / cfg (`voice_typing/daemon.py:155` uses `cfg.asr.lite_model`, CPU substitute via
cuda_check — `_child_resolved_device`, `recorder_host.py:761`).

## Where wiring lives in our code
- Child constructs recorder in `voice_typing/recorder_host.py` `_worker_main` / build path
  (kwargs come from `daemon.cfg_to_kwargs`, `daemon.py:160-216`; `_FIXED_KWARGS` at 99-112).
- Child command loop already handles `("arm"|"disarm"|"text"|"abort"|"shutdown")`; add
  `("prompt", {"text": ...})`. Loop is blocked during `text()` — but prompt updates only ever
  happen at commit time (daemon sends after a final lands, before next utterance) so delivery on
  the command loop is sufficient; no watcher thread needed (document this).
- Gate on `cfg.asr.context_prompt` (exists: `config.py:63`, bool-validated).
- Probe: construct executor + warmup transcribe on 1 s of silence (zeros float32 16 kHz); on any
  exception → degrade: rebuild kwargs WITHOUT executors (stock path, prompt=None, context-free
  decoding), log once (child stderr → journald), report `context_prompt: false` in the
  `("ready", {...})` payload so `status`/tests can see it.

## Gotchas
- `spawn` start method: executors are pickled into the child — but we create the executor INSIDE
  `_worker_main` (child), never across a boundary. Do not put unpicklable objects in kwargs built
  in the daemon.
- Prompt cap: Whisper ~224-token budget; cap ~200 tokens (code constant) — trim defensively in
  the child even though T5.S2 computes the context daemon-side.
- Never crash the child on prompt errors (PRD §4.2quater: "degrade to context-free decoding and
  log").
- AGENTS.md: pytest under `timeout 600`, two-layer timeouts; never foreground daemon; heavy
  CUDA suites (`test_recorder_host.py`) load real models — keep new tests pure/monkeypatched.

## Test seams observed
`tests/test_config.py`, `test_textproc.py` are pure fast pytest patterns to follow; heavy CUDA
suites exist (`test_recorder_host.py`, `test_feed_audio.py`, `test_daemon.py`). Runner:
`timeout 600 .venv/bin/pytest tests/test_prompt_engine.py -q`.
