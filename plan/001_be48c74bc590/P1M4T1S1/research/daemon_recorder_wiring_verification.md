# Research Brief: daemon.py recorder wiring — cfg_to_kwargs + build_recorder (P1.M4.T1.S1)

**Status:** VERIFIED live against the installed RealtimeSTT (venv) + the consumed
sibling modules on 2026-07-06. Every kwarg, default, and consumed-API signature below
was confirmed by running `.venv/bin/python` in this repo (not from docs).

---

## 1. AudioToTextRecorder.__init__ — the authoritative signature (installed v1.0.2)

`inspect.signature(AudioToTextRecorder.__init__)` → **85 parameters** (excl. `self`).

### Every kwarg this task plans to pass — VERIFIED PRESENT:

| kwarg we pass | present? | default in v1.0.2 | our value |
|---|---|---|---|
| `model` | ✅ | `"tiny"` | resolved `final_model` (distil-large-v3 / small.en) |
| `realtime_model_type` | ✅ | `"tiny"` | resolved `realtime_model` (small.en / tiny.en) |
| `language` | ✅ | `""` | cfg.asr.language ("en") |
| `device` | ✅ | `"cuda"` | resolved device (cuda / cpu) |
| `compute_type` | ✅ | `"default"` | resolved (float16 / int8) |
| `enable_realtime_transcription` | ✅ | `False` | `True` |
| `realtime_processing_pause` | ✅ | `0.2` | cfg.asr.realtime_processing_pause (0.15) |
| `use_main_model_for_realtime` | ✅ | `False` | `False` |
| `post_speech_silence_duration` | ✅ | `0.6` | cfg.asr.post_speech_silence_duration (0.6) |
| `min_length_of_recording` | ✅ | `0.5` | `0.3` |
| `min_gap_between_recordings` | ✅ | `0.0` | `0.0` |
| `silero_sensitivity` | ✅ | `0.4` | `0.4` |
| `webrtc_sensitivity` | ✅ | `3` | `3` |
| `silero_backend` | ✅ | `"auto"` | `"auto"` (EXPLICIT — item correction (a)) |
| `spinner` | ✅ | `True` | `False` |
| `use_microphone` | ✅ | `True` | `True` (False + feed_audio in tests, P1.M7.T2.S1) |
| `ensure_sentence_starting_uppercase` | ✅ | `True` | `False` (item correction (b)) |
| `ensure_sentence_ends_with_period` | ✅ | `True` | `False` (item correction (b)) |
| `on_realtime_transcription_stabilized` | ✅ | `None` | callback(str) → feedback.update_partial |
| `on_vad_detect_start` | ✅ | `None` | callback() → feedback.set_phase("listening") |
| `on_vad_start` | ✅ | `None` | callback() → feedback.set_phase("speaking") |
| `on_vad_stop` | ✅ | `None` | callback() → feedback.set_phase("listening") |

**We do NOT pass** (deliberate): `silero_use_onnx` (legacy, default None — item says DROP),
`gpu_device_index` (default 0), `input_device_index` (default None → PipeWire default source,
PRD §4.4 "leave unset"). All other 60+ params keep their defaults.

### THE silero resolution (item correction (a) — VERIFIED, resolves a docstring ambiguity):

The architecture research note `research_realtimestt_api.md §1` listed `silero_backend` as
"(:167 region)" but flagged it as "not a constructor kwarg" in one reading. **DEFINITIVE
live check:** `silero_backend` IS a constructor kwarg (default `"auto"`), and it sits in the
signature BETWEEN `silero_deactivity_detection` and `silero_onnx_model_path`:

```
silero_sensitivity        default 0.4
silero_use_onnx           default None     ← LEGACY switch; None ⇒ silero_backend decides
silero_deactivity_detection default False
silero_backend            default "auto"   ← MODERN control
silero_onnx_model_path    default None
silero_onnx_threads       default 2
```

The `__init__` docstring (verified via `inspect.getsource`) confirms the semantics:
- `silero_use_onnx` (default `None`): *"Legacy Silero backend switch... If None, `silero_backend`
  controls backend selection and defaults to the fastest accurate backend."*
- `silero_backend` (default `"auto"`): *"Silero VAD runtime backend. [auto] tries... `silero_vad_op18_ifless.onnx`,
  then raw `silero_vad.onnx`, then [PyTorch]"* — i.e. **auto prefers a bundled CPU ONNX and AVOIDS
  the torch-hub PyTorch download** (PRD §8 risk "torch-hub download at runtime").

**ACTION (item correction (a)):** pass `silero_backend="auto"` EXPLICITLY (pins intent against a
future default change; harmless since it equals the default), and do NOT pass `silero_use_onnx`
(leave it None so silero_backend is authoritative). This replaces PRD §4.4's `silero_use_onnx=True`.

---

## 2. Consumed contracts (READ at preflight — DO NOT edit)

### 2a. `voice_typing/config.py` → `VoiceTypingConfig` (P1.M2.T1.S1 — DONE, present)
- `cfg.asr: AsrConfig` with fields: `final_model="distil-large-v3"`, `realtime_model="small.en"`,
  `language="en"`, `device="cuda"` ("cuda"|"cpu"), `post_speech_silence_duration=0.6`,
  `realtime_processing_pause=0.15`.
- **`compute_type` is NOT a config field** (cuda_check concern per §4.4). cfg_to_kwargs derives it
  from `cfg.asr.device` ("float16" if cuda else "int8") before handing to cuda_check.
- Verified live: `from voice_typing.config import VoiceTypingConfig; VoiceTypingConfig().asr.device == "cuda"`.

### 2b. `voice_typing/cuda_check.py` → `resolve_device_and_models` + `CPU_FALLBACK` (P1.M1.T2.S2 — DONE, present)
- `resolve_device_and_models(defaults: Mapping[str,str] | None = None) -> dict[str,str]`:
  returns `dict(defaults)` when `is_cuda_available()` (ctranslate2 sees ≥1 GPU), else
  returns `dict(CPU_FALLBACK)` regardless of `defaults`. Always a FRESH dict.
- `CUDA_DEFAULTS = {device:"cuda", compute_type:"float16", final_model:"distil-large-v3", realtime_model:"small.en"}`
- `CPU_FALLBACK   = {device:"cpu",  compute_type:"int8",   final_model:"small.en",        realtime_model:"tiny.en"}`
- **Semantics that matter for cfg_to_kwargs:** passing `defaults` derived from cfg means a user who
  explicitly sets `device="cpu"` is RESPECTED when CUDA is available (resolve returns their defaults);
  CUDA is only FORCED when it's absent (resolve returns CPU_FALLBACK). Correct.
- **cuda_check LIMITATION (not this task's job to fix):** `get_cuda_device_count()` probes the driver
  only — it does NOT load cuDNN, so a missing `libcudnn_ops.so.9` still yields "cuda-ok" and the
  failure surfaces at recorder CONSTRUCTION (WhisperModel load), not at resolve. PRD §4.4 says the
  daemon "MUST fall back" — that construction-failure retry is OUT OF SCOPE for S1 (documented as a
  known limitation / future hook for main() P1.M4.T3.S1). S1 applies ONLY the verdict-based fallback.

### 2c. `voice_typing/feedback.py` → `Feedback` (P1.M3.T2.S1 — IN PROGRESS, NOT yet present)
- **STATE AT RESEARCH TIME:** `voice_typing/feedback.py` does NOT exist yet; only
  `tests/test_feedback.py` exists (TDD RED phase). **Therefore daemon unit tests MUST use a stub
  feedback** (`_FakeFeedback`) so they don't import a not-yet-existing module.
- The CONTRACT (from P1.M3.T2.S1 PRP) — daemon touches ONLY these two methods:
  - `feedback.update_partial(text: str) -> None`  (throttled state-file write; never notifies)
  - `feedback.set_phase(phase: str) -> None`       ("idle"|"listening"|"speaking")
- `record_final` / `set_listening` are P1.M4.T1.S2's concern (on_final + listening gate) — NOT used here.
- daemon.py uses a `TYPE_CHECKING` import of `Feedback` for the type hint ONLY (never executed at
  runtime ⇒ importing daemon.py is safe even while feedback.py is absent).

---

## 3. Defensive kwargs filtering — design (`_filter_kwargs_to_signature`)

PRD §4.4 note + item contract: *"drop any kwarg absent in the installed version defensively...
wrap construction so an unknown kwarg is logged-and-skipped, not a crash."*

**Mechanism (chosen over try/except TypeError):** inspect `AudioToTextRecorder.__init__`'s
signature; keep only kwargs whose names are accepted params; `logger.warning(...)` per dropped key.

```python
def _filter_kwargs_to_signature(kwargs, recorder_cls):
    params = inspect.signature(recorder_cls.__init__).parameters
    # A class declaring **kwargs accepts ANY name → nothing to filter (also makes fakes easy).
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(kwargs)
    valid = set(params) - {"self"}
    accepted = {k: v for k, v in kwargs.items() if k in valid}
    dropped = [k for k, v in kwargs.items() if k not in valid]
    if dropped:
        logger.warning("AudioToTextRecorder: dropping unsupported kwargs %r", dropped)
    return accepted
```

**Why inspect.signature over try/except:** it tells us WHICH kwarg is unknown (loggable), and it
lets the construction succeed with the rest rather than all-or-nothing. **VAR_KEYWORD branch:** a
`def __init__(self, **kwargs)` class accepts everything — returning all kwargs verbatim is correct
(and makes unit-test fakes trivial). All 22 of our planned kwargs are verified present, so the drop
path is PURELY defensive against future API drift (PRD §8 risk #5) — exercised in tests with a strict fake.

---

## 4. Test strategy — NO real recorder, NO model load, NO CUDA

| Concern | How tested | Real deps? |
|---|---|---|
| `cfg_to_kwargs` cuda path | monkeypatch `voice_typing.cuda_check.resolve_device_and_models` → CUDA_DEFAULTS | none |
| `cfg_to_kwargs` cpu fallback | monkeypatch same → CPU_FALLBACK | none |
| fixed values + cfg passthrough | assert dict contents | none |
| silero correction | assert `kwargs["silero_backend"]=="auto"` and `"silero_use_onnx" not in kwargs` | none |
| defensive filter (accept / drop / var-kw) | `_filter_kwargs_to_signature(kwargs, _FakeRecorder)` with strict + loose fakes | none |
| callback wiring | `_build_callbacks(_FakeFeedback())[name](...)` → assert stub recorded the call/arg | none |
| `build_recorder` end-to-end | `_construct(cfg, stub, _FakeRecorder)` seam → assert captured kwargs + call a captured callback | none |

**Test seams (no monkeypatching of RealtimeSTT needed):**
1. `_construct(cfg, feedback, recorder_cls)` — build_recorder's testable core; tests pass `_FakeRecorder`
   (a plain class capturing `**kwargs`) so RealtimeSTT is never imported. `build_recorder(cfg, feedback)`
   is the production entry that does `from RealtimeSTT import AudioToTextRecorder` lazily then calls `_construct`.
2. `_FakeFeedback` stub — records `update_partial(text)` / `set_phase(phase)` calls. Decouples from
   the not-yet-present feedback.py (P1.M3.T2.S1 parallel).
3. monkeypatch `voice_typing.cuda_check.resolve_device_and_models` — forces cuda/cpu deterministically
   (no GPU needed in CI; the real function probes ctranslate2 which is heavy + machine-dependent).

**`_FakeRecorder` note:** declare `def __init__(self, **kwargs)` → VAR_KEYWORD → the filter's
accept-all branch returns every kwarg (correct). For the DROP-path test, declare a STRICT fake with
an explicit param list missing a few of our kwargs and NO `**kwargs`.

**Out of scope for these tests (separate tasks):** the real recorder construction + `feed_audio`
offline pipeline = **P1.M7.T2.S1** (`tests/test_feed_audio.py`). The listen-forever loop + on_final +
listening gate = **P1.M4.T1.S2**. `main()`/`__main__`/signals = **P1.M4.T3.S1**. Do NOT add them here.

---

## 5. Scope boundaries (what S1 is NOT)

- **No main loop / `while` / `recorder.text()`.** That is P1.M4.T1.S2. S1 only constructs the recorder
  + wires callbacks; it does not drive it.
- **No `on_final` callback, no typing, no listening gate, no `set_microphone`/`abort`.** All P1.M4.T1.S2.
- **No control socket.** P1.M4.T2.S1.
- **No `main()` / `if __name__ == "__main__":` / signal handlers / logging.basicConfig.** P1.M4.T3.S1.
  (The item explicitly defers the `__main__` guard to P1.M4.T3.S1 because RealtimeSTT uses
  multiprocessing — README:76-78 — and the guard must wrap the eventual `main()`.)
- **No construction-failure → CPU retry.** cuda_check's verdict-based fallback (in cfg_to_kwargs) is
  S1's job; a cuDNN-load failure at construction is a documented limitation (see §2b) for a future hook.
- **No feed_audio test, no real model load in tests.** P1.M7.T2.S1.
- **No edits** to config.py / cuda_check.py / feedback.py / typing_backends.py / textproc.py /
  config.toml / pyproject.toml / uv.lock / PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## 6. pyproject.toml facts (verified)

- `[project.scripts]` already declares `voice-typing-daemon = "voice_typing.daemon:main"` — but `main()`
  does NOT exist yet (lands in P1.M4.T3.S1). That entry point is inert until then; S1 does NOT add
  `main()` (would break the "no main in S1" scope). No pyproject edit needed.
- `packages = ["voice_typing"]` (hatchling) — daemon.py is auto-included; no packaging change.
- dev group = `pytest>=9.1.1` only. **No mypy in the venv; ruff is optional** (`/home/dustin/.local/bin/ruff`).
  Authoritative gates: `py_compile` + `pytest`. Validate with `.venv/bin/python -m ...` (zsh aliases bare python).
- No `conftest.py`; pytest discovers `tests/test_*.py` directly.
