# PRP — P1.M4.T1.S1: daemon.py recorder wiring (cfg_to_kwargs + build_recorder + callbacks + CPU fallback)

## Goal

**Feature Goal**: Ship the **recorder-construction surface** of `voice_typing/daemon.py` (PRD §4.2 + §4.4) — a pure `cfg_to_kwargs(cfg)->dict` that turns a `VoiceTypingConfig` into `AudioToTextRecorder` kwargs (with PRD §4.4 CPU fallback already applied via `cuda_check.resolve_device_and_models()`), a `_build_callbacks(feedback)->dict` that wires the four RealtimeSTT callbacks to `Feedback`, a defensive `_filter_kwargs_to_signature()` that drops unknown kwargs (logged-and-skipped, never a crash), and a `build_recorder(cfg, feedback)->AudioToTextRecorder` factory that constructs the recorder **ONCE** (models load here, stay resident for the daemon's lifetime). This is the *construction* half of the daemon — **no main loop, no `on_final`, no socket, no `main()`** (those are S2 / S2 / T2 / T3 respectively).

**Deliverable** (TWO artifacts):
1. `voice_typing/daemon.py` — module docstring + `cfg_to_kwargs` + `_resolve_device_config` + `_build_callbacks` + `_filter_kwargs_to_signature` + `_construct` (testable core) + `build_recorder` (production entry). Verbatim source in Implementation Blueprint → Task 3.
2. `tests/test_daemon.py` — unit tests: cfg_to_kwargs cuda/cpu paths + fixed values + cfg passthrough + the silero correction + the defensive filter (accept/drop/var-kw) + callback wiring + `_construct` end-to-end. Uses a `_FakeFeedback` stub (decoupled from the still-in-progress `feedback.py`) and a `_FakeRecorder` (no RealtimeSTT import, no model load, no CUDA). Verbatim source in Task 4.

**Success Definition**:
- (a) `voice_typing/daemon.py` exists, `py_compile`-clean; `import voice_typing.daemon` succeeds WITHOUT importing RealtimeSTT / torch / ctranslate2 (RealtimeSTT is imported lazily inside `build_recorder` only).
- (b) `cfg_to_kwargs(cfg)` returns a dict with the **22 non-callback kwargs** the item enumerates; `compute_type` and `device` come from `cuda_check.resolve_device_and_models()`; `model`←resolved `final_model`, `realtime_model_type`←resolved `realtime_model`.
- (c) **CPU fallback works:** when `cuda_check.resolve_device_and_models` returns `CPU_FALLBACK`, `cfg_to_kwargs` yields `device="cpu"`, `compute_type="int8"`, `model="small.en"`, `realtime_model_type="tiny.en"`; when it returns the cuda config, `device="cuda"`, `compute_type="float16"`, `model="distil-large-v3"`, `realtime_model_type="small.en"`.
- (d) **Item correction (a) honored:** `kwargs["silero_backend"] == "auto"` (explicit) AND `"silero_use_onnx" NOT in kwargs` (legacy dropped). **Item correction (b) honored:** `ensure_sentence_starting_uppercase is False` and `ensure_sentence_ends_with_period is False`.
- (e) `cfg_to_kwargs` returns **NO `on_*` keys** (callbacks are wired in `build_recorder`, which needs the `Feedback`).
- (f) `_build_callbacks(feedback)` returns exactly `{on_realtime_transcription_stabilized, on_vad_detect_start, on_vad_start, on_vad_stop}`; calling `["on_vad_start"]()` → `feedback.set_phase("speaking")`; `["on_vad_detect_start"]()`/`["on_vad_stop"]()` → `set_phase("listening")`; `["on_realtime_transcription_stabilized"]("hi")` → `update_partial("hi")`.
- (g) `_filter_kwargs_to_signature` keeps kwargs that are in the recorder's `__init__` signature, **drops + WARN-logs** the rest, and **accepts all** when the class declares `**kwargs` (VAR_KEYWORD).
- (h) `build_recorder(cfg, feedback)` constructs a real `AudioToTextRecorder` (lazy import) by delegating to `_construct(cfg, feedback, AudioToTextRecorder)`; `_construct` is the unit-test seam that takes a fake recorder class.
- (i) `tests/test_daemon.py` passes via `.venv/bin/python -m pytest tests/test_daemon.py -v` with **no RealtimeSTT import, no model load, no CUDA, no real `feedback.py` dependency**.
- (j) **No out-of-scope code:** NO main loop / `while` / `recorder.text()` / `on_final` / typing / listening gate / `set_microphone` / `abort` / socket / `main()` / `if __name__ == "__main__":` / signals / logging.basicConfig. NO edits to config.py / cuda_check.py / feedback.py / typing_backends.py / textproc.py / config.toml / pyproject.toml / uv.lock / PRD.md / tasks.json / prd_snapshot.md / .gitignore.

## User Persona

**Target User**: Internal — the daemon main loop (P1.M4.T1.S2) is the sole caller of `build_recorder(cfg, feedback)`. There is no end-user surface in S1; the user-facing payoff (instant toggle-on, correct device) arrives when S2 drives this recorder.

**Use Case**: At daemon startup, the main loop calls `build_recorder(cfg, feedback)` once. Models load into resident memory (GPU VRAM on cuda, RAM on cpu). The loop then reuses that single recorder for the daemon's lifetime so a later `voicectl toggle` arms the mic instantly (PRD §4.2 "construct once"). Partials stream to `feedback` → the tmux status line; VAD phase transitions update `feedback` → the state file.

**Pain Points Addressed**: (1) RealtimeSTT API drift (PRD §8 risk #5) — the defensive filter means an unknown kwarg is logged-and-skipped, not a startup crash. (2) CUDA absent / cuDNN missing — `cuda_check`-gated CPU fallback builds a working (if slower) recorder instead of dying. (3) Double text post-processing — `ensure_sentence_*` disabled so `textproc` stays authoritative.

## Why

- **It is the GPU/ASR entry point of the whole daemon.** PRD §4 architecture: `RealtimeSTT AudioToTextRecorder → VAD → realtime model → partials → state file`, and `final model → final → typing`. Every downstream task (S2 loop, T2 socket, T3 entry point, P1.M7 tests) needs a constructed, correctly-configured recorder. Nothing else can run until this exists.
- **Construct-once = instant toggle-on + no per-utterance model reload.** `AudioToTextRecorder.__init__` loads BOTH whisper models (final + realtime) — seconds of work on cold cache. Building it once at startup and reusing it (PRD §4.2) is what makes `voicectl toggle` feel instant and keeps VRAM resident (acceptance T6). S1 is where that single construction lives.
- **CPU fallback is a PRD MUST, not a nice-to-have.** PRD §4.4: *"If CUDA init fails entirely, daemon MUST ... fall back to `device='cpu', compute_type='int8'` ... and say so in status."* The cuda-check-verdict-based fallback (no GPU ⇒ `resolve_device_and_models` returns `CPU_FALLBACK`) is applied in `cfg_to_kwargs` so the recorder is built for the right device the first time. (A deeper cuDNN-load failure at construction is documented as a limitation for a future hook — see Gotcha #9.)
- **Defensive kwargs = survives RealtimeSTT upgrades.** PRD §4.4 note + §8 risk #5: kwargs here are v1.0.2-era; a future version renaming/dropping one must not brick the daemon. `inspect.signature` filtering + a per-key WARN log turns a hard `TypeError` crash into a visible degradation.
- **Small, well-bounded, unblocks S2 + P1.M7.** Pure construction + wiring; no threading, no IO beyond model load. S2 (the loop) and P1.M7.T2.S1 (`feed_audio` offline test) both consume `build_recorder`/`cfg_to_kwargs`.

## What

One module `voice_typing/daemon.py` exposing:

- `cfg_to_kwargs(cfg: VoiceTypingConfig) -> dict[str, Any]` — builds the **22 non-callback** kwargs. Resolves device/models/compute_type via `cuda_check.resolve_device_and_models()` (CPU fallback applied here). Pulls `language`/`post_speech_silence_duration`/`realtime_processing_pause` from `cfg.asr`; the remaining fixed VAD/timing values from a module `_FIXED_KWARGS` constant. Returns NO `on_*` keys.
- `_resolve_device_config(cfg) -> dict[str,str]` — helper: builds the cuda_check `defaults` mapping from `cfg` (deriving `compute_type` since config has no such field), calls `cuda_check.resolve_device_and_models(defaults)`.
- `_build_callbacks(feedback) -> dict[str, Callable]` — the 4 callbacks (partial + 3 VAD phases) wired to `feedback.update_partial` / `feedback.set_phase`.
- `_filter_kwargs_to_signature(kwargs, recorder_cls) -> dict[str, Any]` — defensive drop of unknown kwargs (inspect.signature; VAR_KEYWORD ⇒ accept-all); WARN-log dropped keys.
- `_construct(cfg, feedback, recorder_cls) -> Any` — kwargs + callbacks + filter + `recorder_cls(**filtered)`. The unit-test seam.
- `build_recorder(cfg, feedback) -> AudioToTextRecorder` — production entry: `from RealtimeSTT import AudioToTextRecorder` (lazy) then `_construct(cfg, feedback, AudioToTextRecorder)`.

Plus `tests/test_daemon.py` (unit tests; verbatim in Task 4).

### Success Criteria

- [ ] `voice_typing/daemon.py` exists; `.venv/bin/python -m py_compile voice_typing/daemon.py` exits 0.
- [ ] `import voice_typing.daemon` succeeds; `voice_typing.daemon.__dict__` has NO top-level `RealtimeSTT`/`torch`/`ctranslate2` binding (lazy import inside `build_recorder` only).
- [ ] `cfg_to_kwargs(VoiceTypingConfig())` returns exactly these 22 keys: `model, realtime_model_type, language, device, compute_type, enable_realtime_transcription, realtime_processing_pause, use_main_model_for_realtime, post_speech_silence_duration, min_length_of_recording, min_gap_between_recordings, silero_sensitivity, webrtc_sensitivity, silero_backend, spinner, use_microphone, ensure_sentence_starting_uppercase, ensure_sentence_ends_with_period` — wait, that's 18 model/timing keys; the full set is enumerated in Task 3's source and asserted in `test_cfg_to_kwargs_keys`. (Count is fixed by the source; the test pins the exact set.)
- [ ] CUDA path (mocked `resolve_device_and_models`→CUDA_DEFAULTS): `device=="cuda"`, `compute_type=="float16"`, `model=="distil-large-v3"`, `realtime_model_type=="small.en"`.
- [ ] CPU path (mocked→CPU_FALLBACK): `device=="cpu"`, `compute_type=="int8"`, `model=="small.en"`, `realtime_model_type=="tiny.en"`.
- [ ] `kwargs["silero_backend"] == "auto"`; `"silero_use_onnx" not in kwargs`.
- [ ] `kwargs["ensure_sentence_starting_uppercase"] is False`; `kwargs["ensure_sentence_ends_with_period"] is False`.
- [ ] `kwargs["use_microphone"] is True`; `"input_device_index" not in kwargs`; `"gpu_device_index" not in kwargs`.
- [ ] cfg passthrough: a `VoiceTypingConfig(asr=AsrConfig(language="es", post_speech_silence_duration=0.9, realtime_processing_pause=0.2))` is reflected in the kwargs.
- [ ] `_build_callbacks` returns exactly 4 keys; each callback calls the right `Feedback` method with the right arg (stub-asserted).
- [ ] `_filter_kwargs_to_signature` drops unknown keys + WARN-logs them (caplog); accepts all when the fake has `**kwargs`.
- [ ] `_construct(cfg, stub, _FakeRecorder)` returns an instance whose captured kwargs include all cfg values + the 4 callbacks; calling the captured `on_vad_start` flips the stub's phase to `"speaking"`.
- [ ] `tests/test_daemon.py` passes; `.venv/bin/python -m pytest tests/ -q` still green (no regressions to the 5 existing test files).
- [ ] ONLY `voice_typing/daemon.py` + `tests/test_daemon.py` are created/changed. Nothing else.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this codebase: the consumed contracts (`VoiceTypingConfig.asr` field names, `cuda_check.resolve_device_and_models`/`CPU_FALLBACK`/`CUDA_DEFAULTS`, `Feedback.update_partial`/`set_phase`) are read at preflight; the RealtimeSTT v1.0.2 signature is verified live (all 22 kwargs present, incl. the `silero_backend` resolution) in research §1; the defensive-filter + test-seam design is pinned in research §3–4; verbatim module + test source is in Tasks 3–4; and the validation commands (py_compile, import-purity grep, pytest) are executable as written. The parallel in-progress `feedback.py` is handled via a `_FakeFeedback` stub so S1 tests never import it.

### Documentation & References

```yaml
# MUST READ — the authoritative behavior + kwargs spec. NOTE THE TWO CORRECTIONS (Gotcha #1, #2).
- file: PRD.md
  why: "§4.2 (daemon): recorder = AudioToTextRecorder(**cfg_to_kwargs(cfg)); construct once;
        wire on_realtime_transcription_stabilized -> feedback.update_partial; on_vad_* -> feedback.
        §4.4 (exact kwargs): the starting-values block + 'verify each kwarg against the installed
        version; drop unknown rather than crash' note + the CUDA-fail -> cpu/int8/small.en/tiny.en
        fallback + 'silero_use_onnx avoids torch-hub download' (SUPERSEDED — see Gotcha #1).
        §4.5 [asr]: the config fields cfg_to_kwargs reads. §8 risk #5 (API drift) -> the defensive filter."
  critical: "PRD §4.4 lists silero_use_onnx=True. THAT IS SUPERSEDED by the item + verified research:
             pass silero_backend='auto' (a real v1.0.2 kwarg), DROP silero_use_onnx. PRD §4.4 also
             hedges on compute_type ('if it is a supported kwarg') — it IS (verified), pass it directly.
             PRD §4.2's on_final/listening-gate/socket/main-loop are OUT OF SCOPE for S1 (Gotcha #8)."

# MUST READ — the verified RealtimeSTT v1.0.2 API (this task's research, live-checked 2026-07-06).
- docfile: plan/001_be48c74bc590/P1M4T1S1/research/daemon_recorder_wiring_verification.md
  why: "§1: the authoritative 85-param signature + a per-kwarg table confirming all 22 we pass are
        present, AND the definitive silero resolution (silero_backend IS a kwarg, default 'auto';
        silero_use_onnx default None is legacy). §2: the 3 consumed contracts (config/cuda_check/
        feedback) with exact field/method names + the cuda_check semantics (resolve returns your
        defaults when CUDA present, CPU_FALLBACK when absent). §3: the defensive-filter design
        (inspect.signature + VAR_KEYWORD accept-all). §4: the test strategy (FakeRecorder via the
        _construct seam; FakeFeedback stub; monkeypatch cuda_check). §5: scope boundaries. §6: pyproject
        facts (no mypy; .venv/bin/python; voice-typing-daemon script is inert until T3 adds main())."
  section: "ALL sections load-bearing. §1 (signature/silero), §2 (contracts), §3 (filter), §4 (tests)."

# MUST READ — the architecture-level RealtimeSTT research (callbacks, lifecycle, feed_audio).
- docfile: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§1: the original per-kwarg verdict (CONFIRMED model/realtime_model_type/language/device/
        compute_type/use_microphone/spinner/all on_* + the silero recommendation). §3: callback
        signatures — on_realtime_transcription_stabilized(str), on_vad_detect_start/on_vad_start/
        on_vad_stop are no-arg; phase mapping on_vad_detect_start->listening, on_vad_start->speaking,
        on_vad_stop->listening. §2/§4: text()/set_microphone/abort/shutdown (S2 uses these, NOT S1).
        §5: feed_audio (P1.M7.T2.S1, NOT S1). §6: the 9 corrections-to-PRD summary."
  critical: "§4 (set_microphone/abort) and §2 (text loop) belong to P1.M4.T1.S2 — do NOT implement
             them here. §6 correction #1 (silero) and #3 (ensure_sentence_*) ARE S1's job."

# MUST READ — the consumed contract (config). READ, do NOT edit.
- file: voice_typing/config.py
  why: "AsrConfig fields: final_model, realtime_model, language, device ('cuda'|'cpu'),
        post_speech_silence_duration, realtime_processing_pause. compute_type is NOT a field
        (cuda_check concern) -> cfg_to_kwargs derives it from cfg.asr.device. The daemon does NOT
        mutate cfg (cuda_check resolution builds a SEPARATE dict)."
  critical: "Do NOT add compute_type to config.py. Do NOT import cuda_check/torch/realtimestt into
             config.py. cfg_to_kwargs READS cfg; it never writes to it."

# MUST READ — the consumed contract (cuda_check). READ, do NOT edit.
- file: voice_typing/cuda_check.py
  why: "resolve_device_and_models(defaults)->dict returns dict(defaults) when is_cuda_available()
        else dict(CPU_FALLBACK). CUDA_DEFAULTS + CPU_FALLBACK constants are the two resolution
        outcomes. The function is the SINGLE source of the device/compute_type/model decision."
  critical: "Tests monkeypatch voice_typing.cuda_check.resolve_device_and_models to force cuda/cpu
             deterministically (the real fn probes ctranslate2 — heavy + machine-dependent).
             daemon.py imports cuda_check as a MODULE (`from voice_typing import cuda_check`) and
             calls cuda_check.resolve_device_and_models(...) so the patch target is stable. Do NOT
             do `from voice_typing.cuda_check import resolve_device_and_models` (would force patching
             voice_typing.daemon.resolve_device_and_models instead)."

# MUST READ — the sibling module style + its test harness (mirror EXACTLY).
- file: voice_typing/typing_backends.py
  why: "The house style for a daemon-adjacent module: module docstring (plain present-tense,
        CONSUMES/CONSUMED BY sections, scope/deferred notes, PRD cross-refs not duplication),
        `from __future__ import annotations`, `logger = logging.getLogger(__name__)`,
        module-level constants for pinned values, private `_lowercase` helpers. daemon.py mirrors
        this shape."
  critical: "Mirror the docstring CONSUMES/CONSUMED BY + SCOPE/DEFERRED pattern. daemon.py CONSUMES
             VoiceTypingConfig + cuda_check + (TYPE_CHECKING) Feedback; CONSUMED BY the main loop
             (P1.M4.T1.S2) + install.sh CUDA smoke."

# Background — the Feedback contract (in progress; daemon only touches update_partial + set_phase).
- file: plan/001_be48c74bc590/P1M3T2S1/PRP.md
  why: "Defines Feedback.update_partial(text) + set_phase(phase) (the ONLY two methods S1 wires).
        record_final/set_listening are S2's. Confirms the duck-typed contract a _FakeFeedback stub
        must satisfy. NOTE: feedback.py is NOT yet present at research time (TDD RED) -> S1 tests use
        a stub, never import voice_typing.feedback at runtime."
  critical: "Do NOT depend on feedback.py existing for S1 tests. daemon.py uses a TYPE_CHECKING import
             of Feedback (never executed at runtime) so importing daemon.py is safe while feedback.py
             is absent. The stub must implement update_partial(text) + set_phase(phase)."

# Downstream — the consumers this item feeds (future work, do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M4.T1.S2 (listen-forever loop): calls build_recorder(cfg, feedback) once, then
        while-not-shutdown: recorder.text(on_final); on_final -> textproc + typing + feedback.
        record_final; toggle -> set_microphone/abort + feedback.set_listening. P1.M4.T3.S1: adds
        main()/__main__/signals. P1.M7.T2.S1: feed_audio offline test (real recorder,
        use_microphone=False). Confirms build_recorder/cfg_to_kwargs are the contract S1 must expose."
  critical: "Do NOT add the loop/on_final/main/feed_audio here. The signatures cfg_to_kwargs(cfg) and
             build_recorder(cfg, feedback) are the contract; do not rename or re-shape them."
```

### Current Codebase tree (state at P1.M4.T1.S1 start)

Run `find . -maxdepth 2 -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*'` from repo root. Expected (config/cuda_check/textproc/typing_backends + their tests landed; feedback.py + its test in TDD-RED progress; NO daemon.py yet):

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # ignores dist/, *.pyc, __pycache__/, .venv/, .pytest_cache/, .pi-subagents/ (DO NOT touch)
├── .venv/                      # Python 3.12.10; pytest 9.1.1 (dev); realtimestt + nvidia-cublas/cudnn-cu12 installed
├── PRD.md                      # READ-ONLY (§4.2 + §4.4 + §4.5 + §8)
├── config.toml                 # P1.M2.T1.S2 output (the [asr] table). DO NOT touch.
├── pyproject.toml              # [project.scripts] voice-typing-daemon = "voice_typing.daemon:main" (main() ABSENT until T3). DO NOT touch.
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py             # package docstring
│   ├── cuda_check.py           # P1.M1.T2.S2 (CONSUMED: resolve_device_and_models/CPU_FALLBACK). READ, DO NOT EDIT.
│   ├── launch_daemon.sh        # P1.M1.T2.S1 (unrelated)
│   ├── prefetch.py             # P1.M1.T3.S1 (unrelated)
│   ├── config.py               # P1.M2.T1.S1 (CONSUMED: VoiceTypingConfig.asr). READ, DO NOT EDIT.
│   ├── textproc.py             # P1.M2.T2.S1 (unrelated to S1; S2 uses it)
│   ├── typing_backends.py      # P1.M3.T1.S1 (STYLE TEMPLATE). DO NOT EDIT.
│   └── feedback.py             # P1.M3.T2.S1 (IN PROGRESS / may be ABSENT). CONSUMED (TYPE_CHECKING only). DO NOT EDIT.
└── tests/
    ├── test_config.py                # P1.M2.T1.S1. DO NOT EDIT.
    ├── test_config_repo_default.py   # P1.M2.T1.S2. DO NOT EDIT.
    ├── test_textproc.py              # P1.M2.T2.S1. DO NOT EDIT.
    ├── test_typing_backends.py       # P1.M3.T1.S2 (HARNESS TEMPLATE — _Recorder/monkeypatch/caplog style). DO NOT EDIT.
    └── test_feedback.py              # P1.M3.T2.S1 (TDD RED — feedback.py may be absent). DO NOT EDIT.
# NO voice_typing/daemon.py yet — Task 3 creates it.
# NO tests/test_daemon.py yet — Task 4 creates it.
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py               # ← CREATE (Task 3): cfg_to_kwargs + build_recorder + callbacks + filter (NO main loop)
└── tests/
    └── test_daemon.py          # ← CREATE (Task 4): unit tests (FakeFeedback stub + FakeRecorder; cuda_check mocked)
# NOTHING ELSE. No main()/loop/socket/on_final. No edits to any existing file.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — silero: pass silero_backend="auto", DROP silero_use_onnx (item correction (a)).
#   PRD §4.4 lists silero_use_onnx=True. v1.0.2 SUPERSEDES it: silero_backend is the modern control
#   (default "auto", prefers a bundled CPU ONNX -> already avoids the torch-hub download, PRD §8 risk).
#   silero_use_onnx is LEGACY (default None = "let silero_backend decide"). VERIFIED LIVE: silero_backend
#   IS a constructor kwarg (research §1). ACTION: kwargs["silero_backend"]="auto" (explicit, pins intent);
#   do NOT pass silero_use_onnx (leave None). An implementer reading only PRD §4.4 will pass the wrong one.

# CRITICAL #2 — ensure_sentence_* = False (item correction (b)). v1.0.2 defaults both to True (auto-cap /
#   auto-period). textproc.py (P1.M2.T2.S1) owns cleanup; leaving these True would double-process /
#   fight punctuation. SET BOTH False. (research/architecture §6 correction #3.)

# CRITICAL #3 — compute_type IS a valid kwarg (PRD §4.4 hedged "if supported"). VERIFIED. Pass it
#   directly from the cuda_check resolution (float16 cuda / int8 cpu). Do not special-case its absence.

# CRITICAL #4 — import cuda_check as a MODULE, not a name. `from voice_typing import cuda_check` then
#   `cuda_check.resolve_device_and_models(...)`. This makes the test patch target
#   `voice_typing.cuda_check.resolve_device_and_models` stable. A bare
#   `from voice_typing.cuda_check import resolve_device_and_models` would force patching
#   `voice_typing.daemon.resolve_device_and_models` instead (and CPU_FALLBACK/CUDA_DEFAULTS would need a
#   second import). Module import is cleaner.

# CRITICAL #5 — RealtimeSTT import MUST be LAZY (inside build_recorder). `from RealtimeSTT import
#   AudioToTextRecorder` at module top would import torch/faster_whisper/ctranslate2 on `import
#   voice_typing.daemon` -> heavy + couples test import to GPU deps. Importing it lazily inside
#   build_recorder keeps `import voice_typing.daemon` cheap and lets unit tests never touch RealtimeSTT
#   (they call _construct with a fake class). The import-purity gate (Success (a)) checks no top-level
#   RealtimeSTT/torch/ctranslate2 binding.

# CRITICAL #6 — _construct is the unit-test seam; build_recorder is the production entry. Splitting
#   `build_recorder(cfg, feedback)` into `_construct(cfg, feedback, recorder_cls)` + a thin lazy-import
#   wrapper means tests pass a _FakeRecorder and NEVER import RealtimeSTT. Do NOT inline the
#   construction into build_recorder (would force monkeypatching RealtimeSTT.AudioToTextRecorder, which
#   requires importing the heavy module). build_recorder's ENTIRE body is: lazy import + return _construct(...).

# CRITICAL #7 — _filter_kwargs_to_signature MUST handle **kwargs (VAR_KEYWORD). A class declaring
#   `def __init__(self, **kwargs)` accepts ANY name -> return all kwargs verbatim (no drop). This is
#   correct (the class accepts them) AND makes the _FakeRecorder trivial. The real AudioToTextRecorder
#   has NO **kwargs (explicit 85-param signature) -> the strict-filter path drops unknowns. The DROP test
#   uses a fake with an explicit param list (no **kwargs) missing some of our keys. (research §3.)

# CRITICAL #8 — SCOPE: S1 is construction + wiring ONLY. Do NOT add: the `while not shutdown` loop,
#   recorder.text(on_final), on_final/textproc/typing, the listening gate, set_microphone/abort, the
#   control socket, main(), `if __name__ == "__main__":`, signal handlers, logging.basicConfig. Those are
#   P1.M4.T1.S2 / P1.M4.T2.S1 / P1.M4.T3.S1. The pyproject `voice-typing-daemon = "voice_typing.daemon:main"`
#   entry point is INERT until T3 adds main() — do NOT add main() here (would violate scope + the entry
#   point still won't run without the loop). (research §5; item "Use __main__ guard later (P1.M4.T3.S1)".)

# CRITICAL #9 — cuda_check LIMITATION (do NOT try to fix in S1). resolve_device_and_models() probes the
#   CUDA DRIVER only (ctranslate2.get_cuda_device_count) — it does NOT load cuDNN. So a missing
#   libcudnn_ops.so.9 still yields "cuda-ok" and the failure surfaces at recorder CONSTRUCTION
#   (WhisperModel load), not at resolve. PRD §4.4 says the daemon "MUST fall back" on full CUDA init
#   failure — a construction-failure -> CPU retry is a robustness enhancement for main() (P1.M4.T3.S1) or
#   a future task, NOT S1. S1 applies ONLY the verdict-based fallback (in cfg_to_kwargs). Document this
#   in the module docstring as a known limitation. (cuda_check.py module docstring; research §2b.)

# CRITICAL #10 — Feedback may be ABSENT at S1 test time (P1.M3.T2.S1 runs in parallel; feedback.py was
#   NOT present at research time, only its test). S1 unit tests use a _FakeFeedback stub (duck-typed:
#   update_partial(text) + set_phase(phase)) so they NEVER import voice_typing.feedback. daemon.py uses a
#   TYPE_CHECKING import of Feedback for the type hint (never executed at runtime -> importing daemon.py is
#   safe while feedback.py is absent). The runtime call `feedback.update_partial(text)` works against the
#   real Feedback once P1.M3.T2.S1 lands (same method names — it is the contract).

# CRITICAL #11 — callbacks capture `feedback` by closure; keep them SIMPLE (direct delegation, no
#   try/except). RealtimeSTT fires them from its own threads; a feedback method that raises would
#   propagate, but Feedback (P1.M3.T2.S1) is designed robust (notify swallows errors; _write only raises
#   on genuine disk/XDG failure, which is exceptional). Adding try/except here would mask real bugs and
#   is out of scope. The on_final callback (S2) is where typing-error handling belongs. (Gotcha: do not
#   over-engineer the partial/VAD callbacks.)

# CRITICAL #12 — the partial callback signature is `str`; VAD callbacks are NO-ARG. VERIFIED (research
#   architecture §3): on_realtime_transcription_stabilized(str), on_vad_detect_start(), on_vad_start(),
#   on_vad_stop(). Wire `lambda text: feedback.update_partial(text)` for the partial and
#   `lambda: feedback.set_phase("...")` for the VAD ones. Do NOT give the VAD callbacks a `text` arg.

# GOTCHA #13 — FULL PATHS for tooling (zsh aliases python/pytest). Always
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest). mypy is
#   NOT installed — do NOT list it as a gate. ruff is optional (/home/dustin/.local/bin/ruff); py_compile
#   + pytest are the authoritative gates. (system_context §1; prior tasks' research.)

# GOTCHA #14 — do NOT pass input_device_index or gpu_device_index. PRD §4.4: "input_device_index: leave
#   unset -> PipeWire default source". gpu_device_index defaults to 0 (single GPU). Passing them would
#   override correct defaults. Assert their absence in tests.
```

## Implementation Blueprint

### Data models and structure

No new data model. The module consumes the existing `VoiceTypingConfig` (config.py), `cuda_check` constants, and (duck-typed) `Feedback`. It produces a plain `dict[str, Any]` of kwargs and a constructed recorder. The in-module structure:

```python
# Module-level pinned values (PRD §4.4 — not in config.toml; tuning is a deliberate code change):
_FIXED_KWARGS = {
    "enable_realtime_transcription": True,
    "use_main_model_for_realtime": False,   # two models — avoid contention
    "min_length_of_recording": 0.3,
    "min_gap_between_recordings": 0.0,      # resume listening immediately
    "silero_sensitivity": 0.4,
    "webrtc_sensitivity": 3,
    "silero_backend": "auto",               # item correction (a); avoids torch-hub download
    "spinner": False,
    "use_microphone": True,                 # False + feed_audio() in tests (P1.M7.T2.S1)
    "ensure_sentence_starting_uppercase": False,  # item correction (b); textproc owns cleanup
    "ensure_sentence_ends_with_period": False,
}
_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"  # swap to "..._update" if too laggy (PRD §4.2)

def cfg_to_kwargs(cfg: VoiceTypingConfig) -> dict[str, Any]: ...
def _resolve_device_config(cfg: VoiceTypingConfig) -> dict[str, str]: ...
def _build_callbacks(feedback: "Feedback") -> dict[str, Callable[..., None]]: ...
def _filter_kwargs_to_signature(kwargs: dict[str, Any], recorder_cls: type) -> dict[str, Any]: ...
def _construct(cfg: VoiceTypingConfig, feedback: "Feedback", recorder_cls: type) -> Any: ...
def build_recorder(cfg: VoiceTypingConfig, feedback: "Feedback") -> Any: ...   # lazy-imports RealtimeSTT
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs exist, targets do not, and the consumed APIs are callable.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/config.py     && echo "ok: config.py (VoiceTypingConfig)"    || echo "PREFLIGHT FAIL"
      test -f voice_typing/cuda_check.py && echo "ok: cuda_check.py (resolve_device_and_models)" || echo "PREFLIGHT FAIL"
      test -f voice_typing/typing_backends.py && echo "ok: typing_backends.py (style template)"  || echo "PREFLIGHT FAIL"
      test ! -e voice_typing/daemon.py   && echo "ok: daemon.py not yet created"         || echo "PREFLIGHT FAIL: target exists"
      test ! -e tests/test_daemon.py     && echo "ok: tests/test_daemon.py not yet created" || echo "PREFLIGHT FAIL: target exists"
      .venv/bin/python -c "
from voice_typing.config import VoiceTypingConfig, AsrConfig
c = VoiceTypingConfig()
print('asr:', c.asr.final_model, c.asr.realtime_model, c.asr.language, c.asr.device, c.asr.post_speech_silence_duration, c.asr.realtime_processing_pause)
from voice_typing import cuda_check
print('cuda_check:', cuda_check.CUDA_DEFAULTS, cuda_check.CPU_FALLBACK)
print('resolve sig ok:', callable(cuda_check.resolve_device_and_models))
" || echo "PREFLIGHT FAIL"
      .venv/bin/python -c "import inspect, RealtimeSTT; p=inspect.signature(RealtimeSTT.AudioToTextRecorder.__init__).parameters; print('silero_backend present:', 'silero_backend' in p); print('on_vad_start present:', 'on_vad_start' in p)" || echo "PREFLIGHT FAIL: RealtimeSTT import"
  - EXPECTED: both source files present; both targets absent; the asr line prints the 6 defaults;
    cuda_check prints CUDA_DEFAULTS + CPU_FALLBACK; RealtimeSTT prints `silero_backend present: True`
    and `on_vad_start present: True`.
  - DO NOT: create any target file, run uv sync/add, or touch any other file. (feedback.py may be
    absent — that's fine; S1 does not import it at runtime.)

Task 2: WRITE tests/test_daemon.py FIRST (TDD — RED until daemon.py lands in Task 3).
        Use the `write` tool with EXACTLY the content in "Task 4 SOURCE" below.
  - FILE: tests/test_daemon.py
  - CONTENT: module docstring + _FakeFeedback + _FakeRecorder + _StrictFakeRecorder + all test funcs.
  - DO NOT: import RealtimeSTT/torch/ctranslate2 (Gotcha #5/#6); import voice_typing.feedback
    (Gotcha #10 — use the stub); call real cuda_check (monkeypatch it — Gotcha #4).

Task 3: CREATE voice_typing/daemon.py — use the `write` tool with EXACTLY the content in
        "Task 3 SOURCE" below (verbatim). This turns the Task 2 tests GREEN.
  - FILE: voice_typing/daemon.py
  - CONTENT: module docstring + `from __future__ import annotations` + imports (inspect/logging/
    typing + cuda_check + VoiceTypingConfig + TYPE_CHECKING Feedback) + _FIXED_KWARGS +
    _PARTIAL_CALLBACK_ATTR + the 6 functions above.
  - DO NOT: pass silero_use_onnx (Critical #1); leave ensure_sentence_* True (Critical #2); import
    RealtimeSTT at module top (Critical #5); inline construction into build_recorder (Critical #6);
    forget the VAR_KEYWORD branch in the filter (Critical #7); add the loop/main/socket (Critical #8);
    add a construction-failure retry (Critical #9); import feedback at runtime (Critical #10);
    wrap callbacks in try/except (Critical #11); give VAD callbacks a text arg (Critical #12).

Task 4: VALIDATE — run the Validation Loop L1 (py_compile + import purity), L2 (pytest daemon + full
        suite), L3 (defensive-filter live smoke against the REAL signature), L4 (scope guard). Iterate
        until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M4.T1.S1: daemon.py cfg_to_kwargs + build_recorder + callback wiring + CPU fallback + tests".
```

#### Task 3 SOURCE — `voice_typing/daemon.py` (write verbatim)

```python
"""voice_typing.daemon — recorder construction + callback wiring (PRD §4.2, §4.4).

SCOPE (P1.M4.T1.S1): cfg_to_kwargs() + build_recorder() factory + RealtimeSTT→Feedback
callback wiring + cuda_check-gated CPU fallback. The listen-forever loop, on_final→typing,
the listening gate (mic arming + interrupting in-flight audio), the control socket, and the
main()/__main__ entry point ALL land in later subtasks (P1.M4.T1.S2 / P1.M4.T2.S1 /
P1.M4.T3.S1). This module currently exposes ONLY the recorder-construction surface the
main loop will call.

CONSTRUCT ONCE (PRD §4.2 "construct once"): AudioToTextRecorder.__init__ loads BOTH whisper
models (final + realtime) into resident memory (GPU VRAM on cuda, RAM on cpu) — seconds of
work. build_recorder() constructs exactly ONE recorder; the main loop (S2) reuses it for the
daemon's lifetime so a later voicectl toggle arms the mic instantly and VRAM stays resident.

CPU FALLBACK (PRD §4.4): cfg_to_kwargs() resolves device/compute_type/models via
voice_typing.cuda_check.resolve_device_and_models(), which returns the cuda config when
ctranslate2 sees a GPU, else the PRD §4.4 CPU_FALLBACK (cpu/int8/small.en/tiny.en). This is
applied BEFORE construction so the recorder is built for the right device the first time.

  KNOWN LIMITATION (not fixed here): resolve_device_and_models() probes the CUDA DRIVER only
  (ctranslate2.get_cuda_device_count) — it does NOT load cuDNN. A missing libcudnn_ops.so.9
  therefore still yields "cuda-ok", and the failure surfaces later at recorder CONSTRUCTION
  (WhisperModel load), not at resolve. A construction-failure→CPU retry is a robustness hook for
  main() (P1.M4.T3.S1) or a future task; S1 applies ONLY the verdict-based fallback above.

DEFENSIVE KWARGS (PRD §4.4 note + §8 risk "API drift"): RealtimeSTT's constructor changes across
versions. _filter_kwargs_to_signature() inspects AudioToTextRecorder.__init__'s signature and
DROPS any kwarg we computed that isn't accepted, logging a WARNING per dropped key — so an
unknown kwarg is logged-and-skipped, never a TypeError crash.

TWO ITEM CORRECTIONS vs PRD §4.4 (verified against installed RealtimeSTT v1.0.2 — see
plan/.../P1M4T1S1/research/daemon_recorder_wiring_verification.md §1):
  (a) silero: pass silero_backend="auto" (modern control; default, prefers a bundled CPU ONNX
      → already avoids the torch-hub download). DROP the legacy silero_use_onnx=True.
  (b) ensure_sentence_starting_uppercase=False + ensure_sentence_ends_with_period=False so
      textproc (P1.M2.T2.S1) owns cleanup (avoid double capitalization/period processing).

CONSUMES:
  - voice_typing.config.VoiceTypingConfig (P1.M2.T1.S1): cfg.asr.* (READ ONLY — never mutated).
  - voice_typing.cuda_check (P1.M1.T2.S2): resolve_device_and_models(), CUDA_DEFAULTS, CPU_FALLBACK.
  - voice_typing.feedback.Feedback (P1.M3.T2.S1): update_partial(text), set_phase(phase)
    (duck-typed; only these two methods are touched in S1).
CONSUMED BY:
  - the daemon main loop (P1.M4.T1.S2): build_recorder(cfg, feedback) once at startup.
  - install.sh CUDA smoke (P1.M6.T1.S1): may import cfg_to_kwargs.
PURE IMPORTS at module top (inspect, logging, typing, voice_typing.config, voice_typing.cuda_check).
RealtimeSTT is imported LAZILY inside build_recorder so `import voice_typing.daemon` stays cheap and
unit tests never touch torch/ctranslate2. Feedback is imported only under TYPE_CHECKING.
"""
from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable

from voice_typing import cuda_check
from voice_typing.config import VoiceTypingConfig

if TYPE_CHECKING:
    # Type hint only — never executed at runtime, so importing daemon.py is safe even while
    # feedback.py (P1.M3.T2.S1) is still absent. S1 wires only update_partial + set_phase.
    from voice_typing.feedback import Feedback

logger = logging.getLogger(__name__)

# PRD §4.4 — fixed VAD/timing/silero values NOT exposed in config.toml. Tuning these is a
# deliberate code change (they are tightly coupled to the segmentation UX + the torch-hub
# avoidance). Mirrors the PRD §4.4 block with the two item corrections applied.
_FIXED_KWARGS: dict[str, Any] = {
    "enable_realtime_transcription": True,
    "use_main_model_for_realtime": False,   # two models — avoid contention (PRD §4.4)
    "min_length_of_recording": 0.3,
    "min_gap_between_recordings": 0.0,      # resume listening immediately
    "silero_sensitivity": 0.4,
    "webrtc_sensitivity": 3,
    "silero_backend": "auto",               # item correction (a); avoids torch-hub download
    "spinner": False,
    "use_microphone": True,                 # False + feed_audio() in tests (P1.M7.T2.S1)
    "ensure_sentence_starting_uppercase": False,  # item correction (b); textproc owns cleanup
    "ensure_sentence_ends_with_period": False,
}

# Which realtime-partial callback to wire. PREFERRED: stabilized (more accurate, slight delay).
# If stabilized proves too laggy, change this constant to "on_realtime_transcription_update"
# (faster, rougher) — single source so the swap is a one-line change (PRD §4.2; item contract).
_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"


def _resolve_device_config(cfg: VoiceTypingConfig) -> dict[str, str]:
    """Build cuda_check defaults from cfg, then resolve (applies PRD §4.4 CPU fallback).

    Returns {device, compute_type, final_model, realtime_model}. compute_type is DERIVED from
    cfg.asr.device (config.py has no compute_type field — it is a cuda_check concern) before being
    handed to cuda_check. cuda_check.resolve_device_and_models() then either keeps these defaults
    (cuda available) or overrides wholesale with CPU_FALLBACK (no cuda).
    """
    defaults = {
        "device": cfg.asr.device,
        "compute_type": "float16" if cfg.asr.device == "cuda" else "int8",
        "final_model": cfg.asr.final_model,
        "realtime_model": cfg.asr.realtime_model,
    }
    return cuda_check.resolve_device_and_models(defaults)


def cfg_to_kwargs(cfg: VoiceTypingConfig) -> dict[str, Any]:
    """Build the AudioToTextRecorder kwargs from cfg (CPU fallback already applied).

    Returns the NON-callback kwargs (model/device/timing/VAD/silero). The on_* callbacks are wired
    separately in build_recorder() (they need the Feedback instance). The only side effect is
    cuda_check.resolve_device_and_models() probing CUDA; tests monkeypatch
    voice_typing.cuda_check.resolve_device_and_models to force a path deterministically.
    """
    resolved = _resolve_device_config(cfg)
    kwargs: dict[str, Any] = {
        # model identity — cuda_check-resolved (final_model/realtime_model may be the CPU-fallback
        # small.en/tiny.en when no GPU is visible)
        "model": resolved["final_model"],
        "realtime_model_type": resolved["realtime_model"],
        "language": cfg.asr.language,
        "device": resolved["device"],
        "compute_type": resolved["compute_type"],
        # tunables that ARE in config.toml (PRD §4.5 [asr])
        "realtime_processing_pause": cfg.asr.realtime_processing_pause,
        "post_speech_silence_duration": cfg.asr.post_speech_silence_duration,
    }
    kwargs.update(_FIXED_KWARGS)
    return kwargs


def _build_callbacks(feedback: "Feedback") -> dict[str, Callable[..., None]]:
    """Wire RealtimeSTT callbacks -> Feedback (PRD §4.2; item contract point 3).

      on_realtime_transcription_stabilized(str) -> feedback.update_partial(text)
      on_vad_detect_start() -> feedback.set_phase("listening")   # system starts listening for VAD
      on_vad_start()        -> feedback.set_phase("speaking")    # voice activity detected
      on_vad_stop()         -> feedback.set_phase("listening")   # voice ended -> back to listening

    Callbacks are simple direct delegations (no try/except) — Feedback is designed robust and the
    on_final typing-error handling belongs to S2, not these partial/VAD hooks.
    """
    return {
        _PARTIAL_CALLBACK_ATTR: lambda text: feedback.update_partial(text),
        "on_vad_detect_start": lambda: feedback.set_phase("listening"),
        "on_vad_start": lambda: feedback.set_phase("speaking"),
        "on_vad_stop": lambda: feedback.set_phase("listening"),
    }


def _filter_kwargs_to_signature(
    kwargs: dict[str, Any], recorder_cls: type
) -> dict[str, Any]:
    """Drop kwargs not accepted by recorder_cls.__init__ (defensive vs RealtimeSTT API drift).

    PRD §4.4 note + item contract: an unknown kwarg must be logged-and-skipped, never a crash.
    Inspects the constructor signature; logs a WARNING per dropped key. If the class declares
    **kwargs (VAR_KEYWORD) it accepts ANY name -> return everything verbatim (correct, and makes
    fakes trivial). The real AudioToTextRecorder has an explicit 85-param signature (no **kwargs),
    so the strict-drop path applies in production.
    """
    params = inspect.signature(recorder_cls.__init__).parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(kwargs)  # class accepts arbitrary kwargs — nothing to filter
    valid = set(params) - {"self"}
    accepted: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in kwargs.items():
        if key in valid:
            accepted[key] = value
        else:
            dropped.append(key)
    if dropped:
        logger.warning(
            "AudioToTextRecorder: dropping %d unsupported kwarg(s) %r "
            "(not in the installed constructor signature); construction proceeds without them.",
            len(dropped),
            dropped,
        )
    return accepted


def _construct(
    cfg: VoiceTypingConfig, feedback: "Feedback", recorder_cls: type
) -> Any:
    """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

    Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
    RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
    supplies the real AudioToTextRecorder via a lazy import.
    """
    kwargs = cfg_to_kwargs(cfg)
    kwargs.update(_build_callbacks(feedback))
    filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
    return recorder_cls(**filtered)


def build_recorder(cfg: VoiceTypingConfig, feedback: "Feedback") -> Any:
    """Construct ONE AudioToTextRecorder wired to feedback (PRD §4.2, §4.4).

    Resolves device/models (CPU fallback), builds kwargs + callbacks, defensively filters to the
    installed RealtimeSTT signature, then constructs the recorder. Model load happens HERE (in
    __init__) and stays resident — the main loop (P1.M4.T1.S2) reuses this single recorder for the
    daemon's lifetime. Returns the constructed AudioToTextRecorder.

    Heavy: imports RealtimeSTT + loads models on first call (seconds). Unit tests call _construct()
    with a fake class instead; this function is exercised by the feed_audio test (P1.M7.T2.S1) and
    the real daemon startup (P1.M4.T1.S2).
    """
    from RealtimeSTT import AudioToTextRecorder  # lazy: keeps `import voice_typing.daemon` cheap

    return _construct(cfg, feedback, AudioToTextRecorder)
```

#### Task 4 SOURCE — `tests/test_daemon.py` (write verbatim — TDD, RED until Task 3 lands)

```python
"""Unit tests for voice_typing.daemon — cfg_to_kwargs + build_recorder wiring (P1.M4.T1.S1).

NO real RealtimeSTT / NO model load / NO CUDA / NO real feedback.py dependency:
  - cfg_to_kwargs is tested directly (pure dict; cuda_check.resolve_device_and_models is mocked).
  - _construct (build_recorder's testable core) is tested with a _FakeRecorder that captures **kwargs.
  - _filter_kwargs_to_signature is tested with strict fakes (drop path) + a **kwargs fake (accept-all).
  - callbacks are tested by calling _build_callbacks(_FakeFeedback())[name](...) and asserting state.

Decoupled from the in-progress feedback.py (P1.M3.T2.S1): a _FakeFeedback stub records calls instead
of importing voice_typing.feedback. Decoupled from RealtimeSTT: _construct takes a fake recorder class.

Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_daemon.py -v
"""
from __future__ import annotations

import logging

import pytest

from voice_typing import daemon
from voice_typing.config import AsrConfig, VoiceTypingConfig


# ---------------------------------------------------------------------------
# Stubs — duck-typed stand-ins so tests never import RealtimeSTT or feedback.py.
# ---------------------------------------------------------------------------


class _FakeFeedback:
    """Records update_partial/set_phase calls. Matches the Feedback contract S1 wires."""

    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)


class _FakeRecorder:
    """Accepts ANY kwargs (VAR_KEYWORD) and captures them. Filter returns all verbatim."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)


class _StrictFakeRecorder:
    """Explicit param list (no **kwargs) missing most of our kwargs -> exercises the DROP path."""

    # Accepts only these three of our kwargs; everything else must be filtered out.
    def __init__(self, model: str = "", language: str = "", device: str = "") -> None:
        self.kwargs = {"model": model, "language": language, "device": device}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _cuda_resolve(monkeypatch, mapping: dict[str, str]) -> None:
    """Force voice_typing.cuda_check.resolve_device_and_models to return `mapping` (a copy)."""
    monkeypatch.setattr(
        daemon.cuda_check,
        "resolve_device_and_models",
        lambda defaults=None: dict(mapping),
    )


@pytest.fixture
def cfg() -> VoiceTypingConfig:
    return VoiceTypingConfig()


# ---------------------------------------------------------------------------
# cfg_to_kwargs — keys + model/timing identity
# ---------------------------------------------------------------------------


def test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set(cfg):
    kw = daemon.cfg_to_kwargs(cfg)
    # No on_* callbacks here (they are wired in build_recorder).
    assert not any(k.startswith("on_") for k in kw), sorted(kw)
    expected = {
        "model", "realtime_model_type", "language", "device", "compute_type",
        "realtime_processing_pause", "post_speech_silence_duration",
        "enable_realtime_transcription", "use_main_model_for_realtime",
        "min_length_of_recording", "min_gap_between_recordings", "silero_sensitivity",
        "webrtc_sensitivity", "silero_backend", "spinner", "use_microphone",
        "ensure_sentence_starting_uppercase", "ensure_sentence_ends_with_period",
    }
    assert set(kw) == expected, sorted(set(kw) ^ expected)


def test_cfg_to_kwargs_cuda_path(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["device"] == "cuda"
    assert kw["compute_type"] == "float16"
    assert kw["model"] == "distil-large-v3"
    assert kw["realtime_model_type"] == "small.en"


def test_cfg_to_kwargs_cpu_fallback(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CPU_FALLBACK)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["device"] == "cpu"
    assert kw["compute_type"] == "int8"
    assert kw["model"] == "small.en"
    assert kw["realtime_model_type"] == "tiny.en"


def test_cfg_to_kwargs_fixed_values(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    assert kw["enable_realtime_transcription"] is True
    assert kw["use_main_model_for_realtime"] is False
    assert kw["min_length_of_recording"] == 0.3
    assert kw["min_gap_between_recordings"] == 0.0
    assert kw["silero_sensitivity"] == 0.4
    assert kw["webrtc_sensitivity"] == 3
    assert kw["spinner"] is False
    assert kw["use_microphone"] is True


def test_cfg_to_kwargs_silero_correction(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    # item correction (a): explicit silero_backend="auto"; legacy silero_use_onnx dropped.
    assert kw["silero_backend"] == "auto"
    assert "silero_use_onnx" not in kw


def test_cfg_to_kwargs_textproc_owns_cleanup(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    # item correction (b): both False so textproc is authoritative.
    assert kw["ensure_sentence_starting_uppercase"] is False
    assert kw["ensure_sentence_ends_with_period"] is False


def test_cfg_to_kwargs_no_device_index_overrides(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    kw = daemon.cfg_to_kwargs(cfg)
    # PRD §4.4: leave input_device_index unset (PipeWire default); gpu_device_index defaults to 0.
    assert "input_device_index" not in kw
    assert "gpu_device_index" not in kw


def test_cfg_to_kwargs_passes_through_config_values(monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    custom = VoiceTypingConfig(asr=AsrConfig(
        language="es",
        post_speech_silence_duration=0.9,
        realtime_processing_pause=0.2,
        final_model="large-v3-turbo",
        realtime_model="medium.en",
        device="cuda",
    ))
    kw = daemon.cfg_to_kwargs(custom)
    assert kw["language"] == "es"
    assert kw["post_speech_silence_duration"] == 0.9
    assert kw["realtime_processing_pause"] == 0.2
    # final_model/realtime_model flow through the resolver (CUDA_DEFAULTS here keeps them).
    assert kw["model"] == "large-v3-turbo"
    assert kw["realtime_model_type"] == "medium.en"


def test_cfg_to_kwargs_calls_resolve_with_cfg_defaults(cfg, monkeypatch):
    """cfg_to_kwargs builds cuda_check defaults FROM cfg (respects an explicit device='cpu')."""
    seen: list[dict] = []

    def fake(defaults=None):
        seen.append(dict(defaults) if defaults else {})
        return dict(daemon.cuda_check.CUDA_DEFAULTS)

    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", fake)
    daemon.cfg_to_kwargs(cfg)
    assert seen, "resolve_device_and_models was not called"
    d = seen[0]
    assert d["final_model"] == cfg.asr.final_model
    assert d["realtime_model"] == cfg.asr.realtime_model
    assert d["device"] == cfg.asr.device
    assert d["compute_type"] == "float16"  # derived from device=='cuda'


# ---------------------------------------------------------------------------
# _build_callbacks — wiring
# ---------------------------------------------------------------------------


def test_build_callbacks_keys():
    cb = daemon._build_callbacks(_FakeFeedback())
    assert set(cb) == {
        "on_realtime_transcription_stabilized",
        "on_vad_detect_start",
        "on_vad_start",
        "on_vad_stop",
    }


def test_callback_partial_updates_feedback():
    fb = _FakeFeedback()
    daemon._build_callbacks(fb)["on_realtime_transcription_stabilized"]("hello world")
    assert fb.partials == ["hello world"]
    assert fb.phases == []


@pytest.mark.parametrize("attr,phase", [
    ("on_vad_detect_start", "listening"),
    ("on_vad_start", "speaking"),
    ("on_vad_stop", "listening"),
])
def test_callback_vad_phases(attr, phase):
    fb = _FakeFeedback()
    daemon._build_callbacks(fb)[attr]()
    assert fb.phases == [phase]
    assert fb.partials == []


# ---------------------------------------------------------------------------
# _filter_kwargs_to_signature — defensive drop
# ---------------------------------------------------------------------------


def test_filter_keeps_kwargs_in_signature():
    kw = {"model": "x", "language": "en", "device": "cpu"}
    out = daemon._filter_kwargs_to_signature(kw, _StrictFakeRecorder)
    assert out == kw  # all three are accepted params of _StrictFakeRecorder


def test_filter_drops_unknown_kwargs(caplog):
    kw = {"model": "x", "language": "en", "device": "cpu", "bogus_kw": 1, "also_bogus": 2}
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        out = daemon._filter_kwargs_to_signature(kw, _StrictFakeRecorder)
    assert out == {"model": "x", "language": "en", "device": "cpu"}
    # the two unknown kwargs are named in a WARNING log line
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "bogus_kw" in joined and "also_bogus" in joined


def test_filter_accepts_all_when_var_keyword():
    # _FakeRecorder declares **kwargs -> VAR_KEYWORD -> accept everything.
    kw = {"model": "x", "anything": 1, "on_vad_start": lambda: None}
    out = daemon._filter_kwargs_to_signature(kw, _FakeRecorder)
    assert out == kw


# ---------------------------------------------------------------------------
# _construct — end-to-end wiring through the testable seam (no RealtimeSTT)
# ---------------------------------------------------------------------------


def test_construct_passes_filtered_kwargs_to_recorder(cfg, monkeypatch):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder)
    kw = rec.kwargs
    # cfg values present
    assert kw["model"] == "distil-large-v3"
    assert kw["device"] == "cuda"
    assert kw["language"] == "en"
    # callbacks present
    assert "on_realtime_transcription_stabilized" in kw
    assert "on_vad_detect_start" in kw and "on_vad_start" in kw and "on_vad_stop" in kw


def test_construct_callbacks_are_live(cfg, monkeypatch):
    """A callback captured by the constructed recorder actually drives the feedback."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    fb = _FakeFeedback()
    rec = daemon._construct(cfg, fb, _FakeRecorder)
    rec.kwargs["on_vad_start"]()           # simulate RealtimeSTT firing on_vad_start
    rec.kwargs["on_realtime_transcription_stabilized"]("live partial")
    assert fb.phases == ["speaking"]
    assert fb.partials == ["live partial"]


def test_construct_drops_kwargs_not_in_strict_recorder(cfg, monkeypatch, caplog):
    """A strict recorder (no **kwargs) forces the defensive drop of most of our kwargs."""
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
    with caplog.at_level(logging.WARNING, logger="voice_typing.daemon"):
        rec = daemon._construct(cfg, _FakeFeedback(), _StrictFakeRecorder)
    # _StrictFakeRecorder accepts only model/language/device -> only those survive filtering.
    assert set(rec.kwargs) == {"model", "language", "device"}
    assert any("dropping" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# build_recorder — the production entry is a thin lazy-import wrapper (smoke only)
# ---------------------------------------------------------------------------


def test_build_recorder_is_callable_and_documented():
    # We do NOT call build_recorder() here (it would import RealtimeSTT + load models — heavy,
    # and that is P1.M7.T2.S1's job via feed_audio). We only assert the contract surface exists.
    assert callable(daemon.build_recorder)
    assert daemon.build_recorder.__doc__, "build_recorder must have a docstring"
```

### Implementation Patterns & Key Details

```python
# PATTERN: cfg_to_kwargs resolves device/models FIRST (CPU fallback), then merges fixed values.
#   cuda_check.resolve_device_and_models(defaults) is the SINGLE decision point; cfg_to_kwargs
#   only maps its 4 outputs onto the recorder kwarg names (final_model->model=, realtime_model->
#   realtime_model_type=). compute_type is derived from cfg.asr.device because config has no field.
resolved = _resolve_device_config(cfg)      # {device, compute_type, final_model, realtime_model}
kwargs = {"model": resolved["final_model"], "realtime_model_type": resolved["realtime_model"], ...}
kwargs.update(_FIXED_KWARGS)                # PRD §4.4 fixed block + the two corrections

# PATTERN: lazy RealtimeSTT import inside build_recorder; _construct takes the class as a param.
#   This is the ONE detail that makes the module unit-testable without torch/ctranslate2/models.
def build_recorder(cfg, feedback):
    from RealtimeSTT import AudioToTextRecorder
    return _construct(cfg, feedback, AudioToTextRecorder)

# GOTCHA: _filter_kwargs_to_signature's VAR_KEYWORD branch. A `def __init__(self, **kwargs)` class
#   accepts any name -> return all kwargs (correct + makes fakes trivial). The real recorder has no
#   **kwargs (explicit 85 params) -> strict-drop path applies in production.
if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
    return dict(kwargs)
```

### Integration Points

```yaml
CONFIG:
  - read: cfg.asr.{final_model, realtime_model, language, device, post_speech_silence_duration,
          realtime_processing_pause} (VoiceTypingConfig, P1.M2.T1.S1). READ ONLY — never mutate.
  - note: "compute_type is NOT a config field; cfg_to_kwargs derives it from cfg.asr.device."

CUDA_CHECK (voice_typing.cuda_check, P1.M1.T2.S2):
  - call: cuda_check.resolve_device_and_models(defaults) -> {device, compute_type, final_model, realtime_model}
  - constants: cuda_check.CUDA_DEFAULTS, cuda_check.CPU_FALLBACK (the two resolution outcomes)
  - import shape: "from voice_typing import cuda_check" (module import — stable monkeypatch target)

FEEDBACK (voice_typing.feedback, P1.M3.T2.S1):
  - call: feedback.update_partial(text:str), feedback.set_phase(phase:str)  # the ONLY two S1 wires
  - type hint: TYPE_CHECKING import of Feedback (runtime-safe while feedback.py is absent)

REALTIMESTT (lazy, inside build_recorder):
  - import: "from RealtimeSTT import AudioToTextRecorder"
  - construct: AudioToTextRecorder(**filtered_kwargs)  # models load HERE, stay resident

NO INTEGRATION POINTS (out of scope): main loop, on_final, typing backends, listening gate
(set_microphone/abort), control socket, main(), signals, logging.basicConfig.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
# After creating daemon.py (Task 3) — fix before proceeding.
.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py

# Import-purity gate: importing daemon.py must NOT bind RealtimeSTT/torch/ctranslate2 at top level
# (RealtimeSTT is imported lazily inside build_recorder). None of these names should appear as a
# module-level binding (a string hit inside a docstring/comment is fine; a real import is not).
.venv/bin/python -c "
import ast, voice_typing.daemon as d, inspect
src = inspect.getsource(d)
mod = ast.parse(src)
top_imports = []
for node in mod.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module or '']
        top_imports.extend(names)
heavy = [n for n in top_imports if n and ('RealtimeSTT' in n or 'torch' in n or 'ctranslate2' in n or 'faster_whisper' in n)]
print('top-level heavy imports:', heavy)
assert not heavy, f'forbidden top-level import(s): {heavy}'
print('OK: daemon.py imports are pure at module top; RealtimeSTT is lazy')
"
# Optional (ruff is at /home/dustin/.local/bin/ruff, NOT in the venv — skip if absent):
command -v ruff >/dev/null && ruff check voice_typing/daemon.py tests/test_daemon.py || echo "(ruff absent — py_compile is the gate)"
# Expected: py_compile exits 0; the purity script prints the two OK lines; no heavy top-level import.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing
# The new daemon tests (RED after Task 2, GREEN after Task 3):
.venv/bin/python -m pytest tests/test_daemon.py -v

# Full suite — confirm no regressions to the 5 existing test files
# (test_config, test_config_repo_default, test_textproc, test_typing_backends, test_feedback):
.venv/bin/python -m pytest tests/ -q
# Expected: all pass. If test_feedback is still RED (P1.M3.T2.S1 in progress in parallel), that is
# NOT a regression caused by S1 — confirm with: .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feedback.py
# S1's own tests (test_daemon.py) MUST be green regardless of feedback.py's state (stub decouples them).
```

### Level 3: Defensive-Filter Smoke Against the REAL Signature (no model load)

```bash
cd /home/dustin/projects/voice-typing
# Confirm _filter_kwargs_to_signature drops NOTHING against the installed RealtimeSTT v1.0.2 signature
# (all 22 of our kwargs are valid -> the WARN-drop path must NOT fire). This does NOT construct the
# recorder (no model load, no CUDA) — it only inspects the signature.
.venv/bin/python -c "
import logging
from RealtimeSTT import AudioToTextRecorder
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig

# Capture any WARNING so we can assert NONE fire for our full kwarg set.
records = []
class _H(logging.Handler):
    def emit(self, r): records.append(r)
h = _H(); h.setLevel(logging.WARNING)
daemon.logger.addHandler(h)

kw = daemon.cfg_to_kwargs(VoiceTypingConfig())
kw.update(daemon._build_callbacks(type('F', (), {'update_partial': lambda self, t: None, 'set_phase': lambda self, p: None})()))
out = daemon._filter_kwargs_to_signature(kw, AudioToTextRecorder)
dropped = [r.getMessage() for r in records if 'dropping' in r.getMessage()]
print('full kwarg count:', len(kw), '| accepted:', len(out), '| dropped warnings:', dropped)
assert not dropped, f'unexpected drops: {dropped}'
assert len(out) == len(kw), 'some kwargs were dropped against the real signature'
print('OK: all kwargs accepted by the installed AudioToTextRecorder signature')
"
# Expected: 'full kwarg count: 22 | accepted: 22 | dropped warnings: []' + the OK line.
# (If this reports drops, an item-corrected kwarg name is wrong — re-verify against the signature.)
```

### Level 4: Scope & Boundary Checks

```bash
cd /home/dustin/projects/voice-typing
# Scope guard: daemon.py must NOT contain any S2/T2/T3 constructs.
.venv/bin/python -c "
src = open('voice_typing/daemon.py').read()
forbidden = ['recorder.text(', 'while not ', 'set_microphone', '.abort(', 'shutdown_requested',
             'def main(', \"if __name__\", 'signal.', 'socket.socket', 'json.loads', 'basicConfig',
             'textproc.clean', 'make_backend', 'record_final', 'set_listening']
hits = [f for f in forbidden if f in src]
print('forbidden tokens present:', hits)
assert not hits, f'S1 scope violation — these belong to later subtasks: {hits}'
print('OK: daemon.py contains only S1 construction+wiring (no loop/main/socket/gate)')
"
# git status guard: ONLY daemon.py + tests/test_daemon.py changed/added.
git status --porcelain | grep -E 'voice_typing/daemon.py|tests/test_daemon.py' || echo "OK: targets tracked"
git status --porcelain | grep -vE 'voice_typing/daemon.py|tests/test_daemon.py' | grep -E '^\s?[MA]' && echo "SCOPE LEAK: unexpected modified files" || echo "OK: no other files touched"
# Expected: the forbidden-tokens list is empty; only the two target files are modified/added.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 passed: `py_compile` clean on `voice_typing/daemon.py` + `tests/test_daemon.py`.
- [ ] L1 passed: import-purity script confirms NO top-level RealtimeSTT/torch/ctranslate2 import.
- [ ] L2 passed: `.venv/bin/python -m pytest tests/test_daemon.py -v` all green.
- [ ] L2 passed: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_feedback.py` green (no regressions; feedback.py may be RED in parallel — not S1's concern).
- [ ] L3 passed: defensive-filter smoke reports `accepted: 22 | dropped warnings: []` against the real signature.
- [ ] L4 passed: scope guard finds no forbidden tokens; only the two target files changed.

### Feature Validation
- [ ] `cfg_to_kwargs` cuda path: device/compute_type/model/realtime_model_type correct.
- [ ] `cfg_to_kwargs` cpu fallback path: cpu/int8/small.en/tiny.en.
- [ ] Item correction (a): `silero_backend=="auto"`, no `silero_use_onnx`.
- [ ] Item correction (b): both `ensure_sentence_*` are `False`.
- [ ] `_build_callbacks`: 4 keys; partial→update_partial(str); VAD→set_phase(listening/speaking/listening).
- [ ] `_filter_kwargs_to_signature`: drops+logs unknowns; accepts all under `**kwargs`.
- [ ] `_construct` (seam): passes filtered kwargs + live callbacks to the fake recorder.
- [ ] `build_recorder`: callable, documented, lazy-imports RealtimeSTT (not invoked in unit tests).

### Code Quality Validation
- [ ] Mirrors `typing_backends.py` house style (docstring CONSUMES/CONSUMED BY + SCOPE/DEFERRED, `from __future__ import annotations`, `logger = logging.getLogger(__name__)`, module constants).
- [ ] File placement matches the desired tree (only `voice_typing/daemon.py` + `tests/test_daemon.py`).
- [ ] Anti-patterns avoided (see below): no main loop, no eager RealtimeSTT import, no scope creep.
- [ ] cuda_check imported as a module (stable monkeypatch target); no `from … import resolve_device_and_models`.

### Documentation & Deployment
- [ ] Module docstring documents scope (S1 only), the construct-once rationale, CPU fallback, the defensive filter, the two item corrections, the cuDNN-construction limitation, and CONSUMES/CONSUMED BY.
- [ ] `_PARTIAL_CALLBACK_ATTR` constant documents the stabilized→update fallback swap.
- [ ] No new env vars / config keys (compute_type stays a cuda_check concern, not a config field).

---

## Anti-Patterns to Avoid

- ❌ Don't add the listen-forever loop / `on_final` / typing / listening gate / socket / `main()` — those are S2 / S2 / S2 / T2 / T3. S1 is construction + wiring ONLY.
- ❌ Don't import RealtimeSTT at module top (eager) — it drags in torch/ctranslate2 and couples test import to GPU deps. Import lazily inside `build_recorder`.
- ❌ Don't inline construction into `build_recorder` — split `_construct(cfg, feedback, recorder_cls)` so tests pass a fake class and never touch RealtimeSTT.
- ❌ Don't pass `silero_use_onnx=True` (legacy) or omit `silero_backend` — the item correction is explicit: `silero_backend="auto"`, drop `silero_use_onnx`.
- ❌ Don't leave `ensure_sentence_starting_uppercase`/`ensure_sentence_ends_with_period` True — textproc owns cleanup.
- ❌ Don't use `try/except TypeError` for the defensive filter — `inspect.signature` tells you WHICH kwarg is unknown (loggable) and lets construction proceed with the rest.
- ❌ Don't forget the VAR_KEYWORD branch in `_filter_kwargs_to_signature` — a `**kwargs` class accepts everything; returning all is correct.
- ❌ Don't give the VAD callbacks a `text` arg — `on_vad_detect_start`/`on_vad_start`/`on_vad_stop` are no-arg; only the partial callback takes `str`.
- ❌ Don't depend on `voice_typing.feedback` existing at S1 test time — use a `_FakeFeedback` stub (P1.M3.T2.S1 runs in parallel; feedback.py may be absent).
- ❌ Don't add a construction-failure→CPU retry in S1 — cuda_check's verdict-based fallback is S1's job; the cuDNN-load-failure case is a documented limitation for main() (P1.M4.T3.S1).
- ❌ Don't mutate `cfg` or add `compute_type` to `config.py` — read `cfg.asr` only; derive `compute_type` locally.

---

## Confidence Score

**9 / 10** for one-pass implementation success.

Rationale: every consumed contract (VoiceTypingConfig.asr fields, cuda_check.resolve_device_and_models/CPU_FALLBACK/CUDA_DEFAULTS, Feedback.update_partial/set_phase) is verified present and read at preflight; the RealtimeSTT v1.0.2 signature is verified LIVE (all 22 kwargs confirmed, including the previously-ambiguous `silero_backend` resolution); the two item corrections (silero, ensure_sentence) are pinned with live-checked defaults; the defensive-filter design and the `_construct` test seam eliminate the two hardest failure modes (API-drift crash, untestable heavy construction); verbatim module + test source is provided; and the validation gates (py_compile, import-purity AST check, pytest, real-signature filter smoke, scope token guard) are all executable as written. The -1 reserves for: (a) the stub-vs-real Feedback surface — if P1.M3.T2.S1 renames `update_partial`/`set_phase` the runtime call would break (but the contract PRP pins those names, and the stub documents them); (b) the untested real `build_recorder()` construction (deferred to P1.M7.T2.S1's feed_audio test by design, so a cuDNN-load surprise could surface there rather than here).
