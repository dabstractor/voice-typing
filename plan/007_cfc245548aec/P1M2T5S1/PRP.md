name: "P1.M2.T5.S1 — Child-side dynamic context-prompt mechanism (capability probe + degrade)"
description: Make every decode in the recorder_host child condition on a mutable rolling initial_prompt via RealtimeSTT 1.0.2 external transcription executors, with a startup capability probe and safe degrade to context-free decoding.

---

## Goal

**Feature Goal**: The recorder-host child's single `small.en` model accepts a **runtime-mutable** `initial_prompt` so every decode (realtime partials AND commit/final passes) is conditioned on the rolling committed context — updated between utterances, never requiring a recorder rebuild.

**Deliverable**:
1. New module `voice_typing/prompt_engine.py` — a `PromptedExecutor` object-style transcription executor (owns one `faster_whisper.WhisperModel`, a thread-safe mutable prompt, `transcribe(audio, language=None, use_prompt=True) -> TranscriptionResult`).
2. `voice_typing/recorder_host.py` wiring: pass the executor via `transcription_executor=` + `realtime_transcription_executor=` when `cfg.asr.context_prompt` is true; new `("prompt", {"text": ...})` child command; startup **capability probe** (construct + warmup) with **degrade** (stock kwargs, context-free) + a `context_prompt` flag in the `("ready", ...)` IPC payload; a defensive ~200-token prompt cap (code constant).
3. `tests/test_prompt_engine.py` — pure-python unit tests (monkeypatched `faster_whisper`, no CUDA).

**Success Definition**: Probe passes on this machine (GPU) → both partial and final decodes carry the current prompt; probe fails (or `context_prompt=false`) → child still comes up fully functional on the stock path, logs one degrade line, `ready` payload reports `context_prompt: false`; no code path crashes the child; all unit tests + existing fast suites pass.

**Scope boundary (NEXT task P1.M2.T5.S2 does this — do NOT implement here)**: computing the prompt *text* (rolling committed context back to last sentence boundary) daemon-side and sending `("prompt", ...)` at commit time. This PRP delivers the mechanism + probe + degrade + cap only. A minimal manual sanity path (e.g. test sets the prompt directly) is in scope.

## User Persona (if applicable)

**Target User**: End user of voice-typing (the developer dictating into Hyprland windows).

**Use Case**: Dictating a multi-sentence paragraph without mid-paragraph fragments starting capitalized or acquiring spurious trailing periods (PRD §4.2quater "Rolling context prompt").

**Pain Points Addressed**: Whisper decodes each utterance as a fresh sentence; without context, mid-paragraph fragments come out capitalized with trailing punctuation the user never said.

## Why

- PRD §4.2quater: "the decoder is told it is *continuing*, not starting" — the primary fix for mid-sentence casing/punctuation artifacts. Verified constraint: `initial_prompt`/`initial_prompt_realtime` are constructor-static in installed RealtimeSTT 1.0.2, and on our single-mode path (`use_main_model_for_realtime=True`) even the realtime-engine poke is unavailable — hence a real mechanism is needed, not attribute assignment.
- Enables P1.M2.T6 (streaming state machine) and T8c/T8d assertions (pause-join coherence, prompt-carrying decodes).
- Degrade requirement is explicit in PRD §8 risk table: "on failure degrade to context-free decoding + log, never crash".

## What

### Success Criteria

- [ ] With `asr.context_prompt = true`: child constructs ONE `faster_whisper.WhisperModel` inside a `PromptedExecutor` and passes it as BOTH `transcription_executor` and `realtime_transcription_executor`; RealtimeSTT's spawned TranscriptionWorker is NOT created (`recorder.transcript_process is None` path — `core/initialization.py:387-395`).
- [ ] A `("prompt", {"text": "..."} , )` command on the child's `cmd_queue` updates the executor's prompt; the next partial AND final decode pass it to `faster_whisper` as `initial_prompt` (unit-verified via monkeypatched model capturing kwargs).
- [ ] Prompt is defensively trimmed to ≤ `_PROMPT_TOKEN_CAP = 200` tokens in the child (word-split heuristic is fine; Whisper budget ≈224).
- [ ] Capability probe at child startup: build executor, `transcribe` 1 s of 16 kHz float32 zeros; on success → executor path; on ANY exception → log one line (`voice-typing context-prompt: probe failed (<err>); degrading to context-free decoding`), rebuild recorder kwargs WITHOUT executors, child still reaches `("ready", ...)`.
- [ ] `("ready", {...})` payload gains `"context_prompt": true|false` (daemon/`status` consumption is T5.S2 — do not change ctl here).
- [ ] `context_prompt = false` config → identical to degrade path (stock kwargs), no probe.
- [ ] Prompt update failures never raise out of `transcribe` or the command loop (swallow + log).
- [ ] `timeout 600 .venv/bin/pytest tests/test_prompt_engine.py -q` passes; `ruff check` / `ruff format --check` / `mypy` clean on touched files.

## All Needed Context

### Context Completeness Check

A fresh agent needs: the exact RealtimeSTT executor contract (verified line numbers below), where the child builds the recorder, the IPC protocol, and the repo's timeout discipline (AGENTS.md). All provided here.

### Documentation & References

```yaml
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/audio_recorder.py
  why: constructor kwargs `transcription_executor` / `realtime_transcription_executor` (lines ~191-192, forwarded ~595-596)
  pattern: pass our executor object to BOTH kwargs; same object = one model instance
  gotcha: kwargs are validated positionally-agnostic; do NOT also pass initial_prompt when using executors (harmless but dead)

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/transcription.py
  why: executor call contract — `call_transcription_executor` lines 176-190: `executor.transcribe(audio, language=None, use_prompt=True)`; external-final thread runs IN the recorder process and puts ("success", result) on `_external_transcription_results` (lines 193-236)
  pattern: return object with `.text` (str) and `.info.language` / `.info.language_probability` — i.e. `TranscriptionResult` from transcription_engines/base.py:21-27
  gotcha: executor is called from the realtime thread AND external-final threads concurrently → internal lock around the model

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/realtime.py
  why: `_realtime_transcription_target` lines 282-291 — external realtime executor is checked FIRST, even with `use_main_model_for_realtime=True`; `_transcribe_with_main_model` lines 245-250 branches to the executor before the worker pipe
  pattern: confirms one executor covers partials on our single-mode path
  gotcha: `_streaming_realtime_target` returns None under use_main_model_for_realtime — irrelevant/OK (we are not a streaming-session engine)

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py
  why: lines 387-395 — with executor set, the TranscriptionWorker process is never spawned (`main_transcription_ready_event.set()` immediately); lines 291-298 set `_uses_external_*_executor` flags
  pattern: verify in the probe that no second model/proc exists; also simplifies teardown
  gotcha: executor warmup is OUR job (built-in warmup lives in the unused worker, core/transcription.py:120-128)

- file: .venv/lib/python3.12/site-packages/RealtimeSTT/transcription_engines/base.py
  why: `TranscriptionResult` dataclass (lines 21-27: text + TranscriptionInfo) — construct and return this exact type
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/transcription_engines/faster_whisper_engine.py
  why: lines 40-64 — the model call shape to mirror: faster_whisper `model.transcribe(audio, language=..., initial_prompt=..., beam_size=..., vad_filter=...)`

- file: voice_typing/recorder_host.py
  why: `_worker_main` (~line 474) builds the recorder in the child and runs the cmd loop (`arm/disarm/text/abort/shutdown`); `_child_resolved_device` (~761) resolves device/compute via cuda_check; `_RelayFeedback`/`_RelayLatency` relay pattern; `_clear_recorder_audio` (~656) shows child-side recorder surgery conventions
  pattern: add the executor construction + probe here (inside the child — NEVER in the daemon: spawn pickles and the daemon must stay CUDA-free); add `("prompt", {...})` to the cmd loop
  gotcha: cmd loop blocks inside `text()` — prompt commands are only delivered between utterances, which is exactly when they are sent (commit time). Document this; do NOT add a watcher thread.

- file: voice_typing/daemon.py
  why: `cfg_to_kwargs` (~160-216) + `_FIXED_KWARGS` (~99-112) build recorder kwargs today (single mode: `use_main_model_for_realtime=True`, `model=cfg.asr.lite_model`, `post_speech_silence_duration=cfg.asr.lite_post_speech_silence_duration`)
  pattern: executor kwargs must be injected CHILD-side (executors hold CUDA objects; kwargs dict from daemon is fine only for plain values) — either extend cfg_to_kwargs with a placeholder the child swaps, or add the kwargs inside _worker_main after receiving cfg. Prefer the latter; keep cfg_to_kwargs executor-free.
  gotcha: `_FIXED_KWARGS` includes `use_microphone=True` — tests use feed_audio; don't touch.

- file: voice_typing/config.py
  why: `AsrConfig.context_prompt: bool = True` already exists (line ~63) with bool validation — just READ it, no schema change

- file: tests/test_textproc.py
  why: pure-python pytest pattern (fast, no CUDA) to follow for tests/test_prompt_engine.py
- file: tests/test_recorder_host.py
  why: heavy CUDA suite — only for optional integration proof; always `timeout 600`
- file: plan/007_cfc245548aec/P1M2T5S1/research/dynamic_prompt_mechanism.md
  why: the full verified internals write-up this PRP distills (line-anchored)
- file: plan/007_cfc245548aec/architecture/realtimestt_internals.md
  why: prior internals map — NOTE its §7 conclusion ("finals not pokable without rebuild") predates the executor discovery; the research note above supersedes it for this task
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── config.py            # AsrConfig.context_prompt exists (bool, default True)
├── daemon.py            # cfg_to_kwargs, _FIXED_KWARGS, run loop, reader thread dispatch
├── recorder_host.py     # RecorderHost (daemon side) + _worker_main (child side)
├── typing_backends.py   # untouched
└── textproc.py          # untouched (guards are T4.S1, done)
tests/
├── test_recorder_host.py  # heavy CUDA integration patterns
└── test_textproc.py       # fast pure pytest pattern
```

### Desired Codebase tree with files to be added

```bash
voice_typing/
├── prompt_engine.py     # NEW — PromptedExecutor + prompt cap + probe helper (child-only module; imports faster_whisper lazily inside functions)
└── recorder_host.py     # MODIFIED — executor wiring, ("prompt") cmd, probe + degrade, ready payload flag
tests/
└── test_prompt_engine.py # NEW — monkeypatched faster_whisper; pure, fast
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL (repo discipline, AGENTS.md): every test/CLI under GNU `timeout` + bash-tool timeout.
#   voicectl always `timeout 30`; pytest `timeout 600 ...`; NEVER foreground the daemon.
# CRITICAL: the daemon process must NEVER import faster_whisper/RealtimeSTT or create CUDA
#   contexts (recorder_host docstring "IMPORT PURITY"). prompt_engine is imported ONLY inside
#   _worker_main / the child process.
# CRITICAL: RealtimeSTT spawns its workers with mp "spawn" — anything pickled must stay picklable;
#   construct the executor INSIDE the child, never pass it across process boundaries.
# GOTCHA: executor.transcribe is called with positional audio + keyword language/use_prompt;
#   accept **_kwargs defensively (upstream may add args) and never raise — upstream catches
#   exceptions into ("error", ...) but our contract is degrade-not-fail.
# GOTCHA: faster_whisper transcribe returns (segments, info); build TranscriptionResult
#   (text=" ".join(seg.text for seg in segments).strip(), info=info) — mirror
#   faster_whisper_engine.py's text assembly.
# GOTCHA: warmup on 1 s of float32 zeros at 16 kHz (np.zeros(16000, dtype="float32")) —
#   exercises CUDA init + encoder so probe failures surface at READY time, not first arm.
# GOTCHA: `context_prompt` config gate and probe-failure degrade must take the SAME code path
#   (stock kwargs) so there is exactly one non-prompt configuration.
# GOTCHA: logging in the child goes to stderr → journald (systemd unit); use module logger, INFO
#   for probe result, DEBUG for prompt updates (prompt text at DEBUG only — it contains user text).
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/prompt_engine.py
from dataclasses import dataclass

_PROMPT_TOKEN_CAP = 200  # Whisper ~224-token prompt budget; code constant (PRD §4.2quater)

@dataclass(frozen=True)
class PromptProbeResult:
    ok: bool
    error: str | None = None

def trim_prompt(text: str, cap: int = _PROMPT_TOKEN_CAP) -> str:
    """Whitespace-split trim, newest tokens kept (context tail matters most)."""
    # pure function — unit-tested

class PromptedExecutor:
    """Object-style RealtimeSTT executor owning ONE faster-whisper model + a mutable prompt."""
    def __init__(self, model_name: str, device: str, compute_type: str, beam_size: int = 5): ...
        # lazy: self._model = None; built on first use or warmup()
    def set_prompt(self, text: str | None) -> None:   # thread-safe plain attribute store (CPython-atomic)
        self._prompt = trim_prompt(text) if text else None
    @property
    def prompt(self) -> str | None: ...
    def warmup(self) -> None:
        # build model + transcribe np.zeros(16000, float32); raises on failure
    def transcribe(self, audio, language=None, use_prompt=True, **_):
        # lock-guarded; never raises (swallow+log → return empty TranscriptionResult)
        # kwargs: language=language, initial_prompt=self._prompt if use_prompt else None,
        #         beam_size=..., vad_filter=..., condition_on_previous_text=False
        # returns RealtimeSTT TranscriptionResult-shaped object (.text, .info)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/prompt_engine.py
  - IMPLEMENT: trim_prompt (pure), PromptProbeResult, PromptedExecutor per blueprint
  - FOLLOW pattern: faster_whisper call shape from RealtimeSTT faster_whisper_engine.py (transcribe kwargs, text assembly); result type = TranscriptionResult from transcription_engines/base.py
  - NAMING: PromptedExecutor, set_prompt/trim_prompt/warmup/transcribe; module constant _PROMPT_TOKEN_CAP
  - GOTCHA: import faster_whisper INSIDE methods (module importable daemon-side without CUDA for the pure helpers)
  - GOTCHA: transcribe must swallow ALL exceptions (log + return empty result) — degrade-not-fail contract

Task 2: MODIFY voice_typing/recorder_host.py (child side only)
  - IMPLEMENT in _worker_main: when cfg.asr.context_prompt → exec = PromptedExecutor(cfg.asr.lite_model, *resolved device/compute from _child_resolved_device); exec.warmup() (probe); on failure: log one INFO degrade line + exec = None
  - INJECT kwargs: if exec: kwargs["transcription_executor"] = exec; kwargs["realtime_transcription_executor"] = exec (add in the CHILD after cfg_to_kwargs — never in the daemon)
  - VERIFY in probe-success path: recorder.transcript_process is None (worker skipped) — assert/log
  - ADD cmd: ("prompt", {"text": ...}) in the child cmd loop → guarded getattr on recorder's executors or a kept reference: exec.set_prompt(text) (no-op + log if degraded). Loop only runs between text() blocks — document that delivery is commit-time only (sufficient by design)
  - READY payload: ("ready", {device, compute_type, model, context_prompt: bool}) — extend the existing dict; daemon-side dispatch unchanged (extra key is additive)
  - FOLLOW pattern: existing cmd-loop style + _child_resolved_device usage in recorder_host.py; logger conventions (module logger, INFO probe line)
  - GOTCHA: keep the executor reference in a local the cmd loop closes over; do not attach unpicklable state anywhere the daemon touches

Task 3: CREATE tests/test_prompt_engine.py
  - IMPLEMENT (monkeypatch a fake faster_whisper.WhisperModel recording transcribe kwargs; follow tests/test_textproc.py fast pattern):
    - test_trim_prompt_caps_and_keeps_tail
    - test_set_prompt_stores_trimmed / clears on None
    - test_transcribe_passes_initial_prompt (captures initial_prompt kwarg == current prompt; language passthrough; use_prompt=False → initial_prompt None)
    - test_transcribe_never_raises (fake model raises → empty .text result, no exception)
    - test_warmup_failure_raises (probe signal)
    - test_executor_kwargs_injection: a small pure helper (extract the child kwargs-augmentation into a module-level function `augment_kwargs_with_executor(kwargs, cfg, resolved, logger)` in recorder_host.py so it is unit-testable WITHOUT spawning CUDA) — assert stock kwargs untouched on context_prompt=False / probe failure, executor kwargs present on success (inject a fake executor factory)
    - test_ready_payload_flag: the pure helper returns/executes the (context_prompt, ready-dict) merge
  - PLACEMENT: tests/test_prompt_engine.py; NO CUDA, no RealtimeSTT import beyond the result dataclass (or a local duck-typed stand-in)

Task 4: VERIFY integration (optional manual, not committed as test)
  - Run the existing heavy suite once to prove no regression: `timeout 600 .venv/bin/pytest tests/test_recorder_host.py -q` (bash-tool timeout 700)
  - If a live daemon is used for a smoke check: systemd unit only, `timeout 30 .venv/bin/voicectl ...`, cleanup per AGENTS.md
```

### Implementation Patterns & Key Details

```python
# Child wiring sketch (recorder_host._worker_main) — the load-bearing lines:
kwargs = cfg_to_kwargs(cfg)                       # unchanged, executor-free
ctx = None
if cfg.asr.context_prompt:
    try:
        resolved = _child_resolved_device(cfg, force_cpu)
        ctx = prompt_engine.PromptedExecutor(cfg.asr.lite_model,
                                             resolved["device"], resolved["compute_type"])
        ctx.warmup()                              # CAPABILITY PROBE (raises on failure)
        kwargs["transcription_executor"] = ctx
        kwargs["realtime_transcription_executor"] = ctx
        logger.info("voice-typing context-prompt: dynamic executor armed")
    except Exception as e:                        # noqa: BLE001 — deliberate broad degrade
        ctx = None
        logger.info("voice-typing context-prompt: probe failed (%s); degrading to context-free decoding", e)
# build_recorder(**kwargs) ... ("ready", {**existing, "context_prompt": ctx is not None})

# transcribe core:
def transcribe(self, audio, language=None, use_prompt=True, **_):
    try:
        with self._lock:
            segments, info = self._model.transcribe(
                audio, language=language or None,
                initial_prompt=self._prompt if use_prompt else None,
                beam_size=self._beam_size, vad_filter=True,
                condition_on_previous_text=False)   # WE own context; disable whisper's own
            return TranscriptionResult(text=" ".join(s.text for s in segments).strip(), info=info)
    except Exception:
        logger.warning("context-prompt transcribe failed; returning empty", exc_info=True)
        return TranscriptionResult(text="")
```

### Integration Points

```yaml
IPC:
  - cmd_queue adds: ("prompt", {"text": str})           # daemon sends at commit time (T5.S2 implements the sender)
  - event_queue "ready" payload adds: "context_prompt": bool
CONFIG:
  - no schema change; read existing [asr] context_prompt (config.py:63)
DEPENDENTS (do not break):
  - P1.M2.T6 (streaming state machine) consumes ready.context_prompt for T8d assertions
  - P1.M2.T5.S2 (daemon prompt computation) is the SENDER of ("prompt", ...)
LOGS:
  - one INFO line at probe success/degrade; DEBUG for prompt updates (never log user text at INFO)
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/ruff check voice_typing/prompt_engine.py voice_typing/recorder_host.py tests/test_prompt_engine.py --fix
.venv/bin/ruff format voice_typing/prompt_engine.py voice_typing/recorder_host.py tests/test_prompt_engine.py
.venv/bin/mypy voice_typing/prompt_engine.py voice_typing/recorder_host.py   # if mypy is configured; skip silently if absent
# Expected: zero errors
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 600 .venv/bin/pytest tests/test_prompt_engine.py -q        # bash-tool timeout 700
timeout 120 .venv/bin/pytest tests/test_textproc.py tests/test_config.py -q   # adjacent pure suites still green
# Expected: all pass. Heavy optional: timeout 600 .venv/bin/pytest tests/test_recorder_host.py -q
```

### Level 3: Integration (bounded, daemon via systemd only)

```bash
systemctl --user restart voice-typing 2>/dev/null || true
timeout 30 .venv/bin/voicectl start   # first arm loads models (~1-3 s)
journalctl --user -u voice-typing --since '-2 min' | grep -i 'context-prompt'   # expect the armed/degrade INFO line
timeout 30 .venv/bin/voicectl status; timeout 30 .venv/bin/voicectl stop
nvidia-smi --query-compute-apps=pid,used_memory --format=csv   # executor path = still ONE model proc (child only)
# Cleanup if anything wedges: per AGENTS.md (timeout 30 voicectl quit; systemctl --user stop; pkill -TERM/-KILL -f ...)
```

### Level 4: Domain-Specific Validation

```bash
# Probe/degrade determinism (no GPU code needed in unit tests — this is the fake-model suite):
timeout 120 .venv/bin/pytest tests/test_prompt_engine.py -k "degrade or never_raises or caps" -v
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1 clean (ruff check/format, mypy if configured)
- [ ] `tests/test_prompt_engine.py` all green; adjacent pure suites green
- [ ] Heavy suite (test_recorder_host.py) unchanged-or-run-once under `timeout 600`
- [ ] No daemon-process import of faster_whisper/RealtimeSTT (grep daemon.py for prompt_engine import = absent)

### Feature Validation
- [ ] context_prompt=true + healthy GPU → executor path, worker process skipped, prompt live for partials+finals
- [ ] Probe failure OR context_prompt=false → stock path, one INFO degrade line, ready payload `context_prompt:false`
- [ ] `("prompt", {...})` cmd updates the prompt; ≤200-token cap enforced
- [ ] transcribe never raises; child never crashes from prompt machinery

### Code Quality Validation
- [ ] Follows recorder_host cmd-loop and logger conventions; no new config surface
- [ ] Executor constructed inside the child only; nothing unpicklable crosses IPC
- [ ] User text never logged at INFO

## Anti-Patterns to Avoid

- ❌ Don't try `recorder.initial_prompt = ...` post-construction — inert (worker copies it at spawn; verified).
- ❌ Don't poke `realtime_transcription_model.config.initial_prompt` — doesn't exist on our single-mode path (`use_main_model_for_realtime=True` skips that engine).
- ❌ Don't spawn a watcher thread for prompt commands — updates only happen at commit time, when the cmd loop is free.
- ❌ Don't construct the executor in the daemon process (CUDA purity / pickling).
- ❌ Don't let the executor raise — the contract with upstream is a result tuple; ours with the PRD is degrade-not-fail.
- ❌ Don't run pytest/voicectl without GNU `timeout`; never foreground the daemon (AGENTS.md).

---

**Confidence Score: 9/10** — the executor mechanism was verified line-by-line against the installed RealtimeSTT 1.0.2 source (both the finals path and the realtime path route to external executors even under `use_main_model_for_realtime=True`, and the worker process is skipped); the only residual risk is behavioral (latency of an in-process executor under the transcription_lock discipline), covered by the degrade path and the existing heavy suite.
