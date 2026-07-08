# PRP — P1.M1.T3.S1: Add force_cpu capability to the device resolution and recorder build path

## Goal

**Feature Goal**: Add a `force_cpu: bool = False` parameter to `build_recorder()` and `_construct()` (and a supporting keyword-only `resolved=` injection point on `cfg_to_kwargs()`) so that, when `force_cpu=True`, an `AudioToTextRecorder` is constructed with the exact PRD §4.4 degraded config (`device="cpu"`, `compute_type="int8"`, `final_model="small.en"`, `realtime_model="tiny.en"`) **without ever calling `_resolve_device_config`/`cuda_check`** — i.e. the driver probe / ctranslate2 import is genuinely *skipped*, not overridden after the fact. This is the *capability* half of bugfix Issue 3 (CUDA construction-failure → CPU fallback); the *retry* half is P1.M1.T3.S2 (main()), which consumes `build_recorder(cfg, feedback, latency, force_cpu=True)`.

**Deliverable** (2 files edited, no new files):
1. `voice_typing/daemon.py` — three small edits: `cfg_to_kwargs` gains `*, resolved=None`; `_construct` gains `force_cpu=False` and computes `resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None` before building kwargs; `build_recorder` gains `force_cpu=False` and threads it to `_construct`. **No change** to `_resolve_device_config`, `cuda_check.py`, `VoiceTypingDaemon.__init__`, `main()`, or any other function.
2. `tests/test_daemon.py` — one ADDITIVE test section (banner + ~7 tests) covering the force_cpu path. **No existing test changed.**

**Success Definition**:
- (a) `build_recorder(cfg, feedback, latency, force_cpu=True)` (and `_construct(..., force_cpu=True)`) build a recorder whose kwargs are `device="cpu"`, `compute_type="int8"`, `model="small.en"`, `realtime_model_type="tiny.en"` — regardless of what `cuda_check.resolve_device_and_models()` would return.
- (b) The non-device kwargs still come from `cfg` + `_FIXED_KWARGS` unchanged on the force_cpu path (language, realtime_processing_pause, post_speech_silence_duration, no_log_file, silero_backend, …).
- (c) **The cuda_check path is genuinely skipped** when `force_cpu=True`: `_resolve_device_config` is NOT called (provable by monkeypatching it to raise — force_cpu succeeds, default raises).
- (d) **100% backward-compatible**: `force_cpu=False` (the default) and the omitted-arg call are byte-identical to today's behavior. All existing tests pass unmodified.
- (e) `_resolve_device_config`, `cuda_check.py`, `VoiceTypingDaemon.__init__`, `main()` are untouched (the contract's negative constraints).
- (f) `force_cpu` is the LAST keyword param on both `_construct` and `build_recorder` (after `latency`), so existing positional callers (`build_recorder(cfg, fb, latency)` → `_construct(cfg, fb, cls, latency)`) are unaffected.

## User Persona

Not applicable (internal API change — DOCS: "none — internal API change, no user-facing/config surface change"). The only consumer is P1.M1.T3.S2 (main()'s construction-failure retry), which will build a forced-CPU recorder and inject it via the existing `recorder=` kwarg on `VoiceTypingDaemon`. No config.toml field, no control-socket protocol change, no voicectl/README change.

## Why

- **Bugfix Issue 3 (Major) is the source.** PRD §4.4: "If CUDA init fails entirely, daemon MUST log clearly and fall back to `device='cpu', compute_type='int8'` … — degraded but functional — and say so in `status`." Today `cuda_check.resolve_device_and_models()` only probes the CUDA *driver* (`ctranslate2.get_cuda_device_count()`); if the driver reports a GPU (verdict `cuda-ok`) but cuDNN init fails later at `AudioToTextRecorder` construction (e.g. `libcudnn_ops.so.9` unloadable), there is NO construction-failure → CPU retry — `main()` logs "fatal error", `return 1`, and systemd's `Restart=on-failure` crash-loops on the GPU path forever. T3.S1 provides the capability the retry (T3.S2) needs; without it, T3.S2 has no clean way to build a CPU recorder that doesn't re-probe the GPU it just failed on.
- **The capability must *skip* cuda_check, not override it.** Re-probing the driver during a CPU retry is both pointless (the GPU path already failed) and risky (`resolve_device_and_models` imports ctranslate2 + probes the driver — a probe that may itself fail or re-touch a broken CUDA state). `force_cpu` must build the device kwargs straight from `cuda_check.CPU_FALLBACK` without entering `_resolve_device_config` at all.
- **Scope discipline: capability ≠ retry.** T3.S1 only adds the `force_cpu` knob and proves it works. The actual try/except retry logic in `main()` is T3.S2's job (it needs to decide whether the first attempt was CUDA, log the degradation, surface `device="cpu"` in status). Keeping them separate means T3.S1 is a small, fully-unit-testable change with no daemon-lifecycle entanglement.
- **Backward-compatible by construction.** `force_cpu=False` is the default, so the daemon's normal startup path (`VoiceTypingDaemon.__init__` → `build_recorder(cfg, feedback, latency)`) is unchanged until T3.S2 explicitly opts into the retry. No risk of accidentally forcing CPU on healthy GPU hosts.

## What

Three small edits to `voice_typing/daemon.py` (verbatim old→new in Implementation Blueprint → Task 1–3) + one additive test section in `tests/test_daemon.py` (Task 4). The mechanism: `_construct` computes `resolved = dict(cuda_check.CPU_FALLBACK) when force_cpu else None`, and `cfg_to_kwargs` uses an injected `resolved` instead of calling `_resolve_device_config(cfg)` when one is provided. No other function is touched.

### Success Criteria

- [ ] `cfg_to_kwargs(cfg, *, resolved=None)` exists; `resolved=None` (default) calls `_resolve_device_config(cfg)` exactly as today; a given `resolved` dict is used instead (no `_resolve_device_config` call).
- [ ] `_construct(cfg, feedback, recorder_cls, latency=None, force_cpu=False)` exists; `force_cpu=True` sets `resolved = dict(cuda_check.CPU_FALLBACK)` and passes it to `cfg_to_kwargs`.
- [ ] `build_recorder(cfg, feedback, latency=None, force_cpu=False)` exists; threads `force_cpu=force_cpu` into `_construct`.
- [ ] `force_cpu` is the LAST param on `_construct` and `build_recorder` (after `latency`); both default `False`.
- [ ] `_construct(cfg, fb, _FakeRecorder, force_cpu=True)` yields kwargs: `device="cpu"`, `compute_type="int8"`, `model="small.en"`, `realtime_model_type="tiny.en"`.
- [ ] With `force_cpu=True`, `_resolve_device_config` is NOT called (monkeypatch-to-raise proof); with `force_cpu=False` (default/omitted), it IS called.
- [ ] With `force_cpu=True`, the non-device kwargs (`language="en"`, `realtime_processing_pause=0.15`, `post_speech_silence_duration=0.6`, `no_log_file=True`, `silero_backend="auto"`, …) are present and correct.
- [ ] `force_cpu=True` overrides a forced-cuda monkeypatch (`_cuda_resolve(monkeypatch, CUDA_DEFAULTS)`) — force_cpu wins unconditionally.
- [ ] `_resolve_device_config`, `cuda_check.py`, `VoiceTypingDaemon.__init__`, `main()`, `_build_callbacks`, `_filter_kwargs_to_signature`, `_FIXED_KWARGS` are unchanged.
- [ ] All existing `tests/test_daemon.py` tests pass unmodified; the new additive section passes.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement T3.S1 from this PRP + the referenced research note. Every edit is given as verbatim old→new text against the current file (exact line numbers verified), the design rationale (why the resolved-injection approach beats the alternatives) is documented, and the test plan mirrors the existing `_cuda_resolve`/`_FakeRecorder`/`_construct` idioms already proven in the suite. No CUDA/RealtimeSTT/model-load is needed for any gate.

### Documentation & References

```yaml
# MUST READ — the verified design decision + the alternatives-rejected rationale + exact edit sites
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T3S1/research/force_cpu_design_and_test_plan.md
  why: "§1 maps the exact device-resolution call chain (__init__→build_recorder→_construct→cfg_to_kwargs→
        _resolve_device_config→cuda_check) with current line numbers. §2 LOCKS the design (resolved-injection
        on cfg_to_kwargs + force_cpu on _construct/build_recorder) and explains WHY alternatives B/C/D are
        rejected (B doesn't skip cuda_check; C violates the 'don't modify _resolve_device_config' constraint;
        D duplicates the kwargs map). §3 is the non-device-kwargs invariant table (what still comes from cfg).
        §4 is the test plan. §5 notes this project uses pytest (NO ruff/mypy in pyproject). §6 parallel-task
        awareness (disjoint from T2.S3's _setup_logging region)."
  section: "§2 (design + alternatives) and §3 (invariant table) are load-bearing."

# MUST READ — the authoritative target config (the exact values force_cpu must produce)
- file: voice_typing/cuda_check.py
  why: "CPU_FALLBACK = {device:'cpu', compute_type:'int8', final_model:'small.en', realtime_model:'tiny.en'}.
        resolve_device_and_models(defaults) returns dict(defaults) on cuda, else dict(CPU_FALLBACK). T3.S1
        reuses CPU_FALLBACK verbatim — it does NOT redefine or re-derive these values."
  critical: "force_cpu builds dict(cuda_check.CPU_FALLBACK) — import cuda_check (already a module-top import
             in daemon.py) and reference the constant. Do NOT hardcode {'device':'cpu',...} (drift risk)."

# THE EDIT SITES — the three functions to change (verbatim text in Task 1–3)
- file: voice_typing/daemon.py
  why: "cfg_to_kwargs @134 (resolved = _resolve_device_config(cfg) @~144); _construct @224
        (kwargs = cfg_to_kwargs(cfg)); build_recorder @243 (return _construct(cfg, feedback, cls, latency)).
        These are the ONLY edits. _resolve_device_config @117 is the function force_cpu must SKIP — it stays
        byte-identical (do NOT add force_cpu to it)."
  pattern: "cfg_to_kwargs maps resolved dict keys to RealtimeSTT kwargs (final_model→model=,
            realtime_model→realtime_model_type=). _construct calls cfg_to_kwargs + _build_callbacks +
            _filter_kwargs_to_signature + recorder_cls(**filtered). Keep this order."
  gotcha: "force_cpu must be the LAST param (after latency) on _construct + build_recorder so existing
           positional calls (build_recorder passes latency as 4th positional to _construct) keep working.
           `resolved` on cfg_to_kwargs is KEYWORD-ONLY (`*, resolved=None`) so cfg stays the sole positional."

# THE TEST FILE — the idioms to mirror (ADDITIVE; do not change existing tests)
- file: tests/test_daemon.py
  why: "_cuda_resolve(monkeypatch, mapping) @~69 forces cuda/cpu hermetically; _FakeRecorder(**kwargs) @~48
        captures kwargs (VAR_KEYWORD → _filter returns all); _StrictFakeRecorder @~56 exercises the drop
        path; _FakeFeedback @~37 records calls; cfg fixture @~93. The _construct seam is tested at @~290
        (test_construct_passes_filtered_kwargs_to_recorder) — mirror it. build_recorder is only smoke-checked
        (test_build_recorder_is_callable_and_documented @~330) because calling it is heavy."
  pattern: "ADD a new section at the END under a banner comment (additive). Tests call
            daemon._construct(cfg, fb, _FakeRecorder, force_cpu=...) and inspect rec.kwargs; assert the skip
            via monkeypatch.setattr(daemon, '_resolve_device_config', <raiser>). No real CUDA/RealtimeSTT."
  critical: "Do NOT call build_recorder() with force_cpu=True in tests (it imports RealtimeSTT + loads
             models — heavy, and that's P1.M7.T2.S1's job). Test the force_cpu LOGIC via _construct + a
             signature smoke-check via inspect.signature(build_recorder)."

# THE CONTRACT — the authoritative task spec (negative constraints are load-bearing)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/tasks.json
  why: "P1.M1.T3.S1 item: 'Add force_cpu: bool = False parameter to build_recorder() and _construct() ...
        Do NOT modify cuda_check.py or _resolve_device_config — the force_cpu override happens in
        _construct/build_recorder only.' This PRP implements exactly that scope."
  critical: "The constraint 'Do NOT modify cuda_check.py or _resolve_device_config' + 'override happens in
             _construct/build_recorder only' is why force_cpu does NOT get added to _resolve_device_config
             (issue_analysis.md floated that as one option; the task CONTRACT overrides it). See research §2."

# THE DEFECT — Issue 3 (the bug this enables fixing) + the consumer (T3.S2)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2 Issue 3 (Major): CUDA construction-failure does not fall back to CPU. The Suggested Fix:
        'In main() (or build_recorder()), wrap recorder construction in a try/except; on failure with a
        resolved device=="cuda", re-resolve with cuda_check.CPU_FALLBACK, reconstruct, log the degradation.'
        T3.S1 provides the force_cpu capability the retry (T3.S2) calls; T3.S2 owns the main() try/except."
  critical: "T3.S1 = capability only. Do NOT implement the main() retry (that's T3.S2). T3.S1 does NOT touch
             main(), __init__, or status_snapshot(). The downstream consumption pattern is documented in
             Integration Points so T3.S2 knows exactly how to call build_recorder(force_cpu=True)."

# THE ORIGINAL DESIGN INTENT (background — why _construct/cfg_to_kwargs are split this way)
- file: plan/001_be48c74bc590/P1M4T1S1/PRP.md
  why: "The _construct/build_recorder split exists so unit tests pass a fake recorder_cls and NEVER import
        RealtimeSTT. force_cpu extends that same seam cleanly (tests assert force_cpu via _construct + a
        fake). The cuda_check-gated CPU fallback (the EXISTING verdict-based fallback) is what force_cpu
        provides a manual override for."
```

### Current Codebase tree (relevant slice — T2.S3 landing in parallel, disjoint region)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py              # cfg_to_kwargs @134; _construct @224; build_recorder @243.        ← EDIT (3 edits)
│   │                            _resolve_device_config @117 — UNCHANGED (force_cpu skips it).
│   │                            _FIXED_KWARGS (incl. no_log_file) — UNCHANGED.
│   │                            NOTE: T2.S3 (parallel) edits _setup_logging @~980+ + adds the rate-limit
│   │                            filter — DISJOINT region; no line-level conflict with T3.S1's @134-260.
│   └── cuda_check.py         # CPU_FALLBACK + resolve_device_and_models — UNCHANGED (force_cpu reads it).
└── tests/
    └── test_daemon.py         # _construct seam @~290; _FakeRecorder @~48; _cuda_resolve @~69.        ← EDIT (additive section)
# No ruff/mypy config (pyproject has only [dependency-groups] dev = pytest). Validation = pytest.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py         # EDIT cfg_to_kwargs (+*, resolved=None); _construct (+force_cpu=False,
#                              resolved=dict(CPU_FALLBACK) injection); build_recorder (+force_cpu=False).
#                              NO other function touched. No new imports (cuda_check already module-top).
tests/test_daemon.py           # ADD one banner section: ~7 force_cpu tests (additive; no existing test changed).
# No new files. No cuda_check.py / config.py / ctl.py / README / systemd / launch_daemon / main() / __init__ changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — force_cpu must SKIP _resolve_device_config/cuda_check, not override kwargs after the fact.
# If you instead call cfg_to_kwargs(cfg) and then mutate the 4 device keys, cfg_to_kwargs STILL calls
# _resolve_device_config → cuda_check.resolve_device_and_models → imports ctranslate2 + probes the driver.
# On a CPU-fallback retry we specifically want to AVOID re-touching a GPU whose construction just failed.
# The resolved-injection design (cfg_to_kwargs takes resolved=; _construct passes dict(CPU_FALLBACK))
# genuinely skips the resolve call — this is the core requirement and a test asserts it. (research §2.)
# (research §2.)

# CRITICAL #2 — DO NOT MODIFY _resolve_device_config OR cuda_check.py. The contract is explicit:
# "Do NOT modify cuda_check.py or _resolve_device_config — the force_cpu override happens in
# _construct/build_recorder only." (issue_analysis.md floated threading force_cpu into _resolve_device_config
# as ONE option; the task CONTRACT overrides it — do not.) cfg_to_kwargs is permitted to change (it's where
# the resolved dict lives) but gets `resolved=`, NOT `force_cpu` (the decision stays in _construct).

# CRITICAL #3 — force_cpu is the LAST param on _construct + build_recorder (after latency). Both default
# False. Existing callers pass `latency` positionally (build_recorder: `return _construct(cfg, feedback,
# AudioToTextRecorder, latency)`). Adding force_cpu after latency keeps that call valid; the new call
# `_construct(..., latency, force_cpu=force_cpu)` is the production wiring. `resolved` on cfg_to_kwargs is
# KEYWORD-ONLY (`*, resolved=None`) so `cfg` stays the sole positional arg (no call-site ambiguity).

# CRITICAL #4 — BUILD dict(cuda_check.CPU_FALLBACK), DON'T hardcode {'device':'cpu',...}. Reference the
# cuda_check constant so the CPU config has ONE source of truth (PRD §4.4). cuda_check is already imported
# module-top in daemon.py (`from voice_typing import cuda_check`). `dict(...)` gives a fresh copy so the
# module constant can't be mutated by the kwargs-builder. (cuda_check.py CPU_FALLBACK.)

# CRITICAL #5 — THE NON-DEVICE KWARGS MUST STILL COME FROM cfg on the force_cpu path. language,
# realtime_processing_pause, post_speech_silence_duration, and ALL _FIXED_KWARGS (no_log_file=True,
# silero_backend="auto", spinner, use_microphone, ensure_sentence_* False, …) are cfg/_FIXED_KWARGS
# concerns, NOT device concerns. force_cpu overrides ONLY device/compute_type/final_model/realtime_model.
# This is WHY cfg_to_kwargs stays the single kwargs-builder (it owns language/timing/_FIXED_KWARGS) and is
# merely handed a different resolved dict. A test asserts the non-device kwargs survive. (research §3.)

# CRITICAL #6 — BACKWARD COMPAT IS NON-NEGOTIABLE. force_cpu=False / resolved=None MUST be byte-identical to
# today's behavior. The daemon's normal startup (VoiceTypingDaemon.__init__ → build_recorder(cfg, feedback,
# latency)) must NOT accidentally force CPU. Every existing tests/test_daemon.py test passes unmodified.
# (research §4 test #5 is the regression guard.)

# GOTCHA #7 — DO NOT add force_cpu to VoiceTypingDaemon.__init__. The contract scopes it to build_recorder +
# _construct only. The consumer (T3.S2) builds a forced-CPU recorder via build_recorder(force_cpu=True) and
# injects it through the EXISTING `recorder=` kwarg on __init__. No __init__ change is needed or wanted.
# (research §2 scope discipline; Integration Points.)

# GOTCHA #8 — DO NOT implement the main() retry (T3.S2's job). T3.S1 = capability + proof only. main(),
# the try/except, the "device=cpu in status" surfacing, and the degradation logging are ALL out of scope.
# Touching main() would conflict with T3.S2 and violate scope.

# GOTCHA #9 — DO NOT call build_recorder() with force_cpu=True in unit tests. It lazy-imports RealtimeSTT +
# loads models (seconds, heavy). Test the force_cpu LOGIC via _construct(cfg, fb, _FakeRecorder,
# force_cpu=True) (the testable seam — _FakeRecorder accepts **kwargs, no models) + a signature smoke-check
# via inspect.signature(build_recorder). This mirrors the existing test_build_recorder_is_callable_and_
# documented (which also does NOT call build_recorder). (test_daemon.py @~330.)

# GOTCHA #10 — FULL PATHS in every bash command. This machine aliases python3→uv run, pip→alias, tmux→zsh
# plugin. Invoke .venv/bin/python and .venv/bin/python -m pytest explicitly. Never bare python/pytest/uv.
# (system_context.)

# GOTCHA #11 — THIS PROJECT USES pytest, NOT ruff/mypy. pyproject.toml has NO [tool.ruff]/[tool.mypy] —
# only [dependency-groups] dev=["pytest>=9.1.1"]. Do NOT invent ruff/mypy validation commands (the PRP
# template's Level 1 ruff/mypy lines are N/A here). Validation = py_compile + pytest. (research §5.)

# GOTCHA #12 — `from __future__ import annotations` is ALREADY at daemon.py's top (the `dict[str, str] |
# None` annotation on the new `resolved` param is valid as-is — stringized). No new import needed.
```

## Implementation Blueprint

### Data models and structure

No config/schema/pydantic changes. No new types. The only "data" change is one new keyword-only parameter
(`resolved: dict[str, str] | None = None`) and one new keyword parameter (`force_cpu: bool = False`),
both with defaults that reproduce today's behavior exactly. The resolved dict's shape (`{device,
compute_type, final_model, realtime_model}`) is unchanged — it's the same shape `_resolve_device_config`
already returns and `cuda_check.CPU_FALLBACK` already provides.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — cfg_to_kwargs: add keyword-only `resolved=None` + branch
  - FIND cfg_to_kwargs (@~134). Current signature + first line:
        def cfg_to_kwargs(cfg: VoiceTypingConfig) -> dict[str, Any]:
            """Build the AudioToTextRecorder kwargs from cfg (CPU fallback already applied).
            ...
            """
            resolved = _resolve_device_config(cfg)
  - EDIT (oldText → newText):
      OLD:
        def cfg_to_kwargs(cfg: VoiceTypingConfig) -> dict[str, Any]:
            """Build the AudioToTextRecorder kwargs from cfg (CPU fallback already applied).

            Returns the NON-callback kwargs (model/device/timing/VAD/silero). The on_* callbacks are wired
            separately in build_recorder() (they need the Feedback instance). The only side effect is
            cuda_check.resolve_device_and_models() probing CUDA; tests monkeypatch
            voice_typing.cuda_check.resolve_device_and_models to force a path deterministically.
            """
            resolved = _resolve_device_config(cfg)
      NEW:
        def cfg_to_kwargs(
            cfg: VoiceTypingConfig, *, resolved: dict[str, str] | None = None
        ) -> dict[str, Any]:
            """Build the AudioToTextRecorder kwargs from cfg (CPU fallback already applied).

            Returns the NON-callback kwargs (model/device/timing/VAD/silero). The on_* callbacks are wired
            separately in build_recorder() (they need the Feedback instance).

            `resolved` ({device,compute_type,final_model,realtime_model} | None): when given, use it
            INSTEAD of calling _resolve_device_config(cfg). The force_cpu path (bugfix Issue 3 /
            P1.M1.T3.S1) passes dict(cuda_check.CPU_FALLBACK) here so the cuda_check driver probe is
            SKIPPED entirely and kwargs are built straight from the PRD §4.4 CPU config (no ctranslate2
            import / no driver probe during a CPU retry). Default None resolves via cuda_check (the
            normal path — the only side effect is cuda_check.resolve_device_and_models() probing CUDA;
            tests monkeypatch it to force a path deterministically).
            """
            if resolved is None:
                resolved = _resolve_device_config(cfg)
  - WHY: `resolved` is the injection point for the force_cpu override. KEYWORD-ONLY (`*,`) so `cfg` stays
    the sole positional arg (no call-site ambiguity; all existing `cfg_to_kwargs(cfg)` calls unchanged).
    Default None → the `if resolved is None: resolved = _resolve_device_config(cfg)` branch is byte-
    identical to today. The docstring documents the force_cpu contract (DOCS: internal API doc).
  - DO NOT: rename `resolved`; add `force_cpu` here (force_cpu lives on _construct/build_recorder); touch
    any other line of cfg_to_kwargs; hardcode the CPU dict (the caller passes dict(cuda_check.CPU_FALLBACK)).

Task 2: EDIT voice_typing/daemon.py — _construct: add `force_cpu=False` + resolved injection
  - FIND _construct (@~224). Current:
        def _construct(
            cfg: VoiceTypingConfig,
            feedback: "Feedback",
            recorder_cls: type,
            latency: "LatencyLog | None" = None,
        ) -> Any:
            """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

            Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
            RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
            supplies the real AudioToTextRecorder via a lazy import. `latency` (optional, default None) is
            threaded into _build_callbacks so on_vad_stop/partial feed the per-utterance latency log.
            """
            kwargs = cfg_to_kwargs(cfg)
            kwargs.update(_build_callbacks(feedback, latency))
            filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
            return recorder_cls(**filtered)
  - EDIT (oldText → newText):
      OLD:
        def _construct(
            cfg: VoiceTypingConfig,
            feedback: "Feedback",
            recorder_cls: type,
            latency: "LatencyLog | None" = None,
        ) -> Any:
            """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

            Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
            RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
            supplies the real AudioToTextRecorder via a lazy import. `latency` (optional, default None) is
            threaded into _build_callbacks so on_vad_stop/partial feed the per-utterance latency log.
            """
            kwargs = cfg_to_kwargs(cfg)
            kwargs.update(_build_callbacks(feedback, latency))
            filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
            return recorder_cls(**filtered)
      NEW:
        def _construct(
            cfg: VoiceTypingConfig,
            feedback: "Feedback",
            recorder_cls: type,
            latency: "LatencyLog | None" = None,
            force_cpu: bool = False,
        ) -> Any:
            """Build kwargs + callbacks, defensively filter to the signature, construct recorder_cls.

            Split out from build_recorder() so unit tests pass a fake recorder_cls and NEVER import
            RealtimeSTT / load models / touch CUDA. build_recorder() is the thin production wrapper that
            supplies the real AudioToTextRecorder via a lazy import. `latency` (optional, default None) is
            threaded into _build_callbacks so on_vad_stop/partial feed the per-utterance latency log.

            force_cpu (bugfix Issue 3 / P1.M1.T3.S1, default False): when True, replace the resolved
            device dict with dict(cuda_check.CPU_FALLBACK) BEFORE building kwargs — this SKIPS the
            _resolve_device_config / cuda_check path entirely (no driver probe, no ctranslate2 import)
            so the CPU retry in main() (P1.M1.T3.S2) never re-touches a GPU whose construction just
            failed. The recorder is then built with the exact PRD §4.4 degraded config (device=cpu,
            compute_type=int8, final_model=small.en, realtime_model=tiny.en). The NON-device kwargs
            (language, timing, _FIXED_KWARGS) still come from cfg as usual; only device/compute_type/
            models are overridden. Consumed via build_recorder(..., force_cpu=True).
            """
            resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None
            kwargs = cfg_to_kwargs(cfg, resolved=resolved)
            kwargs.update(_build_callbacks(feedback, latency))
            filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)
            return recorder_cls(**filtered)
  - WHY: `resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None` IS "replace the resolved dict
    with dict(CPU_FALLBACK) before building kwargs" — done IN _construct, exactly as the contract words it.
    Passing `resolved=resolved` to cfg_to_kwargs routes it to the injection point (Task 1); when None,
    cfg_to_kwargs resolves normally (default path). `dict(...)` gives a fresh copy (CRITICAL #4). force_cpu
    is LAST (after latency) so positional callers are unaffected (CRITICAL #3).
  - DO NOT: add force_cpu to _resolve_device_config; hardcode the CPU dict; mutate cuda_check.CPU_FALLBACK;
    reorder latency/force_cpu (latency stays 4th positional, force_cpu 5th keyword).

Task 3: EDIT voice_typing/daemon.py — build_recorder: add `force_cpu=False` + thread to _construct
  - FIND build_recorder (@~243). Current:
        def build_recorder(
            cfg: VoiceTypingConfig, feedback: "Feedback", latency: "LatencyLog | None" = None
        ) -> Any:
            """Construct ONE AudioToTextRecorder wired to feedback (+ optional latency) (PRD §4.2, §4.4).
            ...
            Heavy: imports RealtimeSTT + loads models on first call (seconds). Unit tests call _construct()
            with a fake class instead; this function is exercised by the feed_audio test (P1.M7.T2.S1) and
            the real daemon startup (P1.M4.T1.S2).
            """
            from RealtimeSTT import AudioToTextRecorder  # lazy: keeps `import voice_typing.daemon` cheap

            return _construct(cfg, feedback, AudioToTextRecorder, latency)
  - EDIT (two changes in one edit — the signature + the _construct call + a docstring line):
      OLD:
        def build_recorder(
            cfg: VoiceTypingConfig, feedback: "Feedback", latency: "LatencyLog | None" = None
        ) -> Any:
      NEW:
        def build_recorder(
            cfg: VoiceTypingConfig,
            feedback: "Feedback",
            latency: "LatencyLog | None" = None,
            force_cpu: bool = False,
        ) -> Any:
      AND (the _construct call at the end of build_recorder):
      OLD:
            return _construct(cfg, feedback, AudioToTextRecorder, latency)
      NEW:
            return _construct(cfg, feedback, AudioToTextRecorder, latency, force_cpu=force_cpu)
      AND (append one sentence to the docstring, after the "...real daemon startup (P1.M4.T1.S2)." line):
      ADD:
            `force_cpu=True` (bugfix Issue 3 / P1.M1.T3.S1) builds a CPU-only recorder from
            cuda_check.CPU_FALLBACK without probing CUDA — the construction-failure retry hook for
            main() (P1.M1.T3.S2). Default False (the normal CUDA/CPU-fallback path).
  - WHY: build_recorder is the PUBLIC entry the consumer (T3.S2) calls as
    `build_recorder(cfg, feedback, latency, force_cpu=True)`. Threading force_cpu through to _construct
    (where the resolved-dict replacement happens) completes the chain. force_cpu LAST, default False.
  - DO NOT: change the lazy import; change the docstring's existing content (only append); call
    _construct with force_cpu positionally (use force_cpu=force_cpu kwarg for readability).

Task 4: ADD tests/test_daemon.py — one ADDITIVE force_cpu test section (no existing test changed)
  - PLACE: a new section at the END of the file, under a clear banner comment:
        # ===========================================================================
        # bugfix P1.M1.T3.S1 — force_cpu capability on _construct / build_recorder / cfg_to_kwargs
        # (ADDITIVE: the force_cpu path builds CPU kwargs WITHOUT calling _resolve_device_config/cuda_check.
        #  Uses S1's _FakeRecorder (VAR_KEYWORD → captures kwargs) + _FakeFeedback + _cuda_resolve. ZERO
        #  real CUDA/RealtimeSTT/model-load — force_cpu LOGIC is tested via the _construct seam.)
        # ===========================================================================
  - ADD (verbatim; `cfg` fixture, `_FakeRecorder`, `_FakeFeedback`, `_cuda_resolve`, `_StrictFakeRecorder`
    are already defined earlier in the file — reuse, do not redefine):
        import inspect  # noqa: E402 (kept local to this section to match the file's additive-section style)


        def test_construct_force_cpu_uses_cpu_fallback(cfg):
            """force_cpu=True builds the exact PRD §4.4 CPU config regardless of cfg.asr.device."""
            rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
            kw = rec.kwargs
            assert kw["device"] == "cpu"
            assert kw["compute_type"] == "int8"
            assert kw["model"] == "small.en"
            assert kw["realtime_model_type"] == "tiny.en"


        def test_construct_force_cpu_skips_resolve(cfg, monkeypatch):
            """force_cpu=True NEVER calls _resolve_device_config (the cuda_check probe is skipped)."""
            def _boom(_cfg=None):
                raise AssertionError("_resolve_device_config must NOT be called when force_cpu=True")
            monkeypatch.setattr(daemon, "_resolve_device_config", _boom)
            # force_cpu=True: no raise -> the skip works (cfg_to_kwargs used the injected resolved dict)
            rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
            assert rec.kwargs["device"] == "cpu"
            # force_cpu=False (default): _resolve_device_config IS called -> the AssertionError fires
            with pytest.raises(AssertionError):
                daemon._construct(cfg, _FakeFeedback(), _FakeRecorder)


        def test_construct_force_cpu_overrides_cuda_path(cfg, monkeypatch):
            """force_cpu wins even when cuda_check is monkeypatched to the CUDA path."""
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)  # force cuda
            rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
            assert rec.kwargs["device"] == "cpu"            # force_cpu overrides the cuda verdict
            assert rec.kwargs["model"] == "small.en"
            assert rec.kwargs["realtime_model_type"] == "tiny.en"


        def test_construct_force_cpu_keeps_non_device_kwargs(cfg):
            """force_cpu overrides ONLY device/models; language/timing/_FIXED_KWARGS still come from cfg."""
            rec = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=True)
            kw = rec.kwargs
            # non-device tunables from cfg (default cfg):
            assert kw["language"] == "en"
            assert kw["realtime_processing_pause"] == 0.15
            assert kw["post_speech_silence_duration"] == 0.6
            # _FIXED_KWARGS survive (P1.M1.T1.S1's no_log_file + the silero correction):
            assert kw["no_log_file"] is True
            assert kw["silero_backend"] == "auto"
            assert kw["use_microphone"] is True
            assert kw["enable_realtime_transcription"] is True
            # _build_callbacks STILL runs on the force_cpu path (on_* wired as on the normal path —
            # _construct always calls _build_callbacks after cfg_to_kwargs; mirrors the existing
            # test_construct_passes_filtered_kwargs_to_recorder). NOT a no-callback assertion: _construct
            # output legitimately contains the on_* callbacks (cfg_to_kwargs is the no-callback surface).
            assert "on_realtime_transcription_stabilized" in kw
            assert "on_vad_detect_start" in kw and "on_vad_start" in kw and "on_vad_stop" in kw


        def test_construct_force_cpu_false_is_default_behavior(cfg, monkeypatch):
            """force_cpu=False (explicit) and omitted behave exactly as the pre-change code (cuda path)."""
            _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS)
            explicit = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder, force_cpu=False)
            omitted = daemon._construct(cfg, _FakeFeedback(), _FakeRecorder)
            # _build_callbacks builds FRESH closure/lambda objects on every call, so the on_* VALUES are
            # never == across two _construct calls — do NOT compare the whole dict. Compare the NON-callback
            # kwargs (the device/models/timing/_FIXED_KWARGS surface, which must be identical) + the callback
            # KEY set (which must match):
            def _noncb(d):
                return {k: v for k, v in d.items() if not k.startswith("on_")}
            assert _noncb(explicit.kwargs) == _noncb(omitted.kwargs)
            assert omitted.kwargs["device"] == "cuda"       # the normal cuda path, untouched
            assert omitted.kwargs["model"] == "distil-large-v3"
            assert {k for k in explicit.kwargs if k.startswith("on_")} == \
                   {k for k in omitted.kwargs if k.startswith("on_")}


        def test_cfg_to_kwargs_accepts_resolved_override(cfg, monkeypatch):
            """cfg_to_kwargs(resolved=...) uses the injected dict and skips _resolve_device_config."""
            def _boom(_cfg=None):
                raise AssertionError("must not resolve when resolved= is given")
            monkeypatch.setattr(daemon, "_resolve_device_config", _boom)
            kw = daemon.cfg_to_kwargs(
                cfg, resolved={"device": "cpu", "compute_type": "int8",
                               "final_model": "small.en", "realtime_model": "tiny.en"}
            )
            assert kw["device"] == "cpu" and kw["model"] == "small.en"
            assert kw["realtime_model_type"] == "tiny.en" and kw["compute_type"] == "int8"


        def test_build_recorder_and_construct_force_cpu_in_signature():
            """The public surface has force_cpu (default False), last after latency. (Smoke; no heavy call.)"""
            sb = inspect.signature(daemon.build_recorder).parameters
            assert "force_cpu" in sb and sb["force_cpu"].default is False
            assert list(sb) == ["cfg", "feedback", "latency", "force_cpu"], list(sb)
            sc = inspect.signature(daemon._construct).parameters
            assert "force_cpu" in sc and sc["force_cpu"].default is False
            assert list(sc) == ["cfg", "feedback", "recorder_cls", "latency", "force_cpu"], list(sc)
            # cfg_to_kwargs got the keyword-only resolved injection point (default None):
            sk = inspect.signature(daemon.cfg_to_kwargs).parameters
            assert "resolved" in sk and sk["resolved"].default is None
            assert sk["resolved"].kind is inspect.Parameter.KEYWORD_ONLY
  - DO NOT: modify any existing test; call build_recorder() with force_cpu=True (heavy); redefine
    _FakeRecorder/_FakeFeedback/_cuda_resolve/cfg (they're already in the file); add real CUDA/mic.

Task 5: VALIDATE — run the Validation Loop L1–L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T3.S1: add force_cpu capability to build_recorder/_construct (+ resolved= on cfg_to_kwargs)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the resolved-dict injection (the force_cpu mechanism). _construct makes the force_cpu
# DECISION and computes the resolved dict; cfg_to_kwargs builds kwargs from whatever resolved dict it's
# given. This keeps force_cpu scoped to _construct/build_recorder (the contract) while genuinely skipping
# the cuda_check path (the requirement). Default None = byte-identical to today.
def _construct(cfg, feedback, recorder_cls, latency=None, force_cpu=False):
    resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None   # the skip: None -> cfg_to_kwargs resolves
    kwargs = cfg_to_kwargs(cfg, resolved=resolved)
    ...

def cfg_to_kwargs(cfg, *, resolved=None):
    if resolved is None:
        resolved = _resolve_device_config(cfg)     # the NORMAL cuda-check path (untouched)
    kwargs = {"model": resolved["final_model"], ...}   # same mapping as today

# PATTERN 2 — build_recorder is the thin public wrapper that threads force_cpu to _construct.
def build_recorder(cfg, feedback, latency=None, force_cpu=False):
    from RealtimeSTT import AudioToTextRecorder    # lazy (unchanged)
    return _construct(cfg, feedback, AudioToTextRecorder, latency, force_cpu=force_cpu)

# PATTERN 3 — force_cpu produces CPU kwargs with non-device kwargs intact (the invariant). Only
# device/compute_type/models come from CPU_FALLBACK; language/timing/_FIXED_KWARGS still from cfg.
# force_cpu=True:  model=small.en, realtime_model_type=tiny.en, device=cpu, compute_type=int8,
#                  language=en, realtime_processing_pause=0.15, no_log_file=True, silero_backend="auto", ...
```

### Integration Points

```yaml
DOWNSTREAM CONSUMER — P1.M1.T3.S2 (main() construction-failure retry; THE consumer):
  - T3.S2 wraps VoiceTypingDaemon(cfg, Feedback(...)) construction (or build_recorder) in a try/except.
    On construction failure when the first attempt was CUDA, it retries ONCE with the CPU path. The
    SANCTIONED call (this task provides it):
        rec = build_recorder(cfg, feedback, latency, force_cpu=True)   # CPU config, no cuda_check
        daemon = VoiceTypingDaemon(cfg, feedback, recorder=rec, ...)   # inject via EXISTING recorder= kwarg
    (latency is the daemon's LatencyLog; T3.S2 passes it as today.) The recorder= injection point already
    exists on __init__ — NO __init__ change is needed for the retry.
  - T3.S2 also owns: deciding whether the first attempt was CUDA (so it doesn't pointlessly retry when
    config already forces CPU), logging the degradation clearly, and surfacing device="cpu" in status
    (status_snapshot already reads _resolved_device, which calls cuda_check — T3.S2 may need to make the
    daemon's self-reported device reflect the actual built recorder; that's T3.S2's concern, NOT T3.S1's).

PARALLEL — P1.M1.T2.S3 (rate-limit filter; landing in parallel):
  - T2.S3 edits _setup_logging (@~980+) + adds the MicRetryRateLimitFilter/helpers near it. T3.S1 edits
    cfg_to_kwargs(@134)/_construct(@224)/build_recorder(@243) — DISJOINT regions of daemon.py. No
    line-level conflict. The two changes are independent (T2.S3 is logging; T3.S1 is device resolution).

UPSTREAM — _resolve_device_config + cuda_check (UNCHANGED):
  - _resolve_device_config(@117) and cuda_check.py stay byte-identical. force_cpu BYPASSES them, never
    modifies them. The normal path (force_cpu=False) still calls _resolve_device_config → cuda_check.

VOICE_TYPING_CONFIG / config.toml / control-socket protocol / ctl.py / status_snapshot() / launch_daemon.sh
/ systemd unit / README:
  - ALL unchanged. force_cpu is an internal build-path knob with NO config field, NO protocol surface,
    NO user-visible documentation (DOCS: "none"). status_snapshot() reads _resolved_device (cuda_check),
    which is unaffected by force_cpu — the status device-string question is T3.S2's to resolve if needed.

BUILD ARTIFACTS:
  - T3.S1 creates NO new files, NO dist/, NO uv.lock/pyproject changes, NO .venv changes. It is a 3-edit
    source patch to daemon.py + an additive test section. `uv sync`/`uv build` are NOT run.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy in pyproject — Gotcha #11);
> the gates below are the project's actual tooling. All gates are pure/unit: NO real CUDA, NO model load,
> NO real RealtimeSTT (the force_cpu path is tested via the _construct seam + a _FakeRecorder).

### Level 1: The three edits are in place (static + signature)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- signatures have force_cpu / resolved ---"
"$PY" - <<'PY'
import inspect
from voice_typing import daemon
# _construct + build_recorder gained force_cpu (default False, LAST param):
for fn in (daemon._construct, daemon.build_recorder):
    p = inspect.signature(fn).parameters
    assert "force_cpu" in p, (fn.__name__, list(p))
    assert p["force_cpu"].default is False, (fn.__name__, p["force_cpu"].default)
    assert list(p)[-1] == "force_cpu", (fn.__name__, list(p))
    print("L1 PASS:", fn.__name__, "force_cpu default", p["force_cpu"].default, "(last)")
# cfg_to_kwargs gained keyword-only resolved (default None):
p = inspect.signature(daemon.cfg_to_kwargs).parameters
assert "resolved" in p and p["resolved"].default is None
assert p["resolved"].kind is inspect.Parameter.KEYWORD_ONLY
print("L1 PASS: cfg_to_kwargs resolved is keyword-only, default None")
PY
echo "--- _resolve_device_config + cuda_check are UNCHANGED (the contract's negative constraints) ---"
"$PY" - <<'PY'
import inspect
from voice_typing import daemon, cuda_check
# _resolve_device_config must NOT take force_cpu (force_cpu bypasses it, never enters it):
assert "force_cpu" not in inspect.signature(daemon._resolve_device_config).parameters
print("L1 PASS: _resolve_device_config has no force_cpu (unchanged)")
# cuda_check.resolve_device_and_models unchanged (defaults arg still present):
assert "defaults" in inspect.signature(cuda_check.resolve_device_and_models).parameters
assert cuda_check.CPU_FALLBACK == {"device":"cpu","compute_type":"int8",
                                   "final_model":"small.en","realtime_model":"tiny.en"}
print("L1 PASS: cuda_check.CPU_FALLBACK + resolve_device_and_models unchanged")
PY
echo "--- daemon.py compiles + imports cleanly (no new top-level heavy imports) ---"
"$PY" -m py_compile voice_typing/daemon.py && echo "L1 PASS: py_compile OK" || echo "L1 FAIL: syntax error"
PY=.venv/bin/python
"$PY" -c "import voice_typing.daemon as m; print('L1 PASS: import OK', m.build_recorder.__name__)" || echo "L1 FAIL"
# Expected: both signatures have force_cpu (default False, last); cfg_to_kwargs has keyword-only resolved;
# _resolve_device_config + cuda_check unchanged; py_compile + import clean.
```

### Level 2: The new additive force_cpu test section passes (the capability proof)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_daemon.py -v -k force_cpu -p no:cacheprovider 2>&1 | tail -20
# Expected: all 7 force_cpu tests pass (the -k force_cpu selector also catches the cfg_to_kwargs resolved
# test by name). If any fails, READ the assertion + fix the implementation (NOT the test — the tests are
# the spec). Specifically: force_cpu=True must yield device=cpu/int8/small.en/tiny.en AND skip _resolve_device_config.
echo "--- also run the resolved-injection test directly (its name has no 'force_cpu') ---"
"$PY" -m pytest tests/test_daemon.py -v -k "resolved_override or force_cpu_in_signature" -p no:cacheprovider 2>&1 | tail -8
# Expected: the 2 name-mismatched tests (resolved override + signature smoke) also pass.
```

### Level 3: No regression — the FULL test_daemon.py suite passes (backward compat)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_daemon.py -v -p no:cacheprovider 2>&1 | tail -25
# Expected: ALL tests pass (the pre-existing _construct/cfg_to_kwargs/build_recorder tests unchanged +
# the new force_cpu section). This is the backward-compat proof (CRITICAL #6). If a pre-existing test
# fails, the default path changed — re-check that force_cpu=False / resolved=None is byte-identical.
echo "--- full fast suite (all of tests/) to catch any cross-file regression ---"
"$PY" -m pytest tests/ -p no:cacheprovider 2>&1 | tail -15
# Expected: full suite green. (Note: tests/test_feed_audio.py is the heavy RealtimeSTT test — if it is
# slow/needs audio assets, that is pre-existing and not caused by this change; the relevant signal is
# that test_daemon.py + test_config + test_textproc + test_typing_backends + test_feedback + test_voicectl
# all pass. If the orchestrator's environment runs the full suite, ensure it's green.)
```

### Level 4: Scope guards — only the 3 edits + the additive test section; read-only files untouched

```bash
cd /home/dustin/projects/voice-typing
echo "--- _resolve_device_config body is byte-identical (no force_cpu branch added there) ---"
grep -c 'force_cpu' voice_typing/daemon.py   # EXPECT exactly: 5 (sig x2 [construct+build_recorder] + 1 in
                                             #   _construct body + 1 build_recorder call + docstrings). If
                                             #   _resolve_device_config contains force_cpu, that's a scope violation.
"$PY" - <<'PY'
import re, pathlib
src = pathlib.Path("voice_typing/daemon.py").read_text()
# _resolve_device_config must NOT mention force_cpu:
m = re.search(r"def _resolve_device_config\(.*?\n(?=def |\Z)", src, re.S)
assert m and "force_cpu" not in m.group(0), "scope violation: _resolve_device_config touches force_cpu"
print("L4 PASS: _resolve_device_config unchanged (no force_cpu)")
# cuda_check.py unchanged (CPU_FALLBACK / resolve_device_and_models only):
cc = pathlib.Path("voice_typing/cuda_check.py").read_text()
assert "force_cpu" not in cc, "scope violation: cuda_check.py was modified"
print("L4 PASS: cuda_check.py unchanged")
PY
echo "--- git status shows ONLY daemon.py + test_daemon.py ---"
git status --short
echo "--- read-only files untouched ---"
for f in PRD.md pyproject.toml uv.lock .gitignore voice_typing/cuda_check.py voice_typing/config.py \
         voice_typing/ctl.py voice_typing/feedback.py README.md systemd/voice-typing.service \
         voice_typing/launch_daemon.sh; do
  git diff --quiet -- "$f" 2>/dev/null && echo "unchanged (ok): $f" || echo "L4 CHECK: $f has changes (verify expected)"
done
# Expected: git status shows ONLY voice_typing/daemon.py + tests/test_daemon.py modified; all read-only/
# out-of-scope files unchanged. force_cpu appears in daemon.py only in _construct/build_recorder/cfg_to_kwargs
# (resolved) — NOT in _resolve_device_config, NOT in cuda_check.py, NOT in __init__/main().
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 signatures correct (force_cpu on _construct/build_recorder default False last; resolved keyword-only on cfg_to_kwargs); `_resolve_device_config` + `cuda_check.py` verified unchanged; py_compile + import clean.
- [ ] L2 all 7 force_cpu/resolved tests pass (capability proof: CPU kwargs + skip + override + non-device kwargs + default-behavior + resolved-injection + signature).
- [ ] L3 full `tests/test_daemon.py` green (backward compat) + the rest of the fast suite green.
- [ ] L4 scope guards: only daemon.py + test_daemon.py modified; `_resolve_device_config` + `cuda_check.py` + all read-only files untouched.

### Feature Validation
- [ ] `force_cpu=True` builds a recorder with `device="cpu"`, `compute_type="int8"`, `model="small.en"`, `realtime_model_type="tiny.en"`.
- [ ] `force_cpu=True` does NOT call `_resolve_device_config` (the skip is proven by monkeypatch-to-raise).
- [ ] `force_cpu=True` overrides a forced-cuda monkeypatch unconditionally.
- [ ] Non-device kwargs (language/timing/`_FIXED_KWARGS` incl. `no_log_file`/`silero_backend`) survive on the force_cpu path.
- [ ] `force_cpu=False` (default + omitted) is byte-identical to the pre-change behavior.

### Code Quality Validation
- [ ] `force_cpu` is the LAST param on `_construct` + `build_recorder`; `resolved` is keyword-only on `cfg_to_kwargs`.
- [ ] The CPU config is `dict(cuda_check.CPU_FALLBACK)` (single source of truth), NOT hardcoded.
- [ ] Backward-compatible defaults (`force_cpu=False`, `resolved=None`); all existing tests pass unmodified.
- [ ] New tests are ADDITIVE (a banner section at the end; no existing test changed); they use the existing `_FakeRecorder`/`_FakeFeedback`/`_cuda_resolve`/`cfg` fixtures (no redefinition, no real CUDA/RealtimeSTT).

### Scope Boundary Validation
- [ ] No change to `_resolve_device_config`, `cuda_check.py`, `VoiceTypingDaemon.__init__`, `main()`, `_build_callbacks`, `_filter_kwargs_to_signature`, `_FIXED_KWARGS`.
- [ ] No `config.toml`/`config.py` field, no control-socket protocol change, no `ctl.py`/`README`/`status_snapshot()` change.
- [ ] No main() retry logic implemented (that's P1.M1.T3.S2).
- [ ] No new files; no `pyproject.toml`/`uv.lock`/`.gitignore` changes; no `uv sync`/`uv build` run.

---

## Anti-Patterns to Avoid

- ❌ Don't override kwargs *after* `cfg_to_kwargs(cfg)` returns — that still calls `_resolve_device_config`/cuda_check (violates "skip the normal path"). Inject `resolved=` so the resolve call is bypassed entirely.
- ❌ Don't add `force_cpu` to `_resolve_device_config` or `cuda_check.py` — the contract explicitly forbids it (CRITICAL #2). `force_cpu` lives on `_construct`/`build_recorder`; `_resolve_device_config` is bypassed, not modified.
- ❌ Don't add `force_cpu` to `VoiceTypingDaemon.__init__` — the consumer (T3.S2) injects a forced-CPU recorder via the existing `recorder=` kwarg. No `__init__` change is needed or wanted.
- ❌ Don't implement the `main()` retry — that's T3.S2's job. T3.S1 is capability + proof only.
- ❌ Don't hardcode `{"device":"cpu", ...}` — use `dict(cuda_check.CPU_FALLBACK)` (single source of truth for the PRD §4.4 CPU config).
- ❌ Don't drop the non-device kwargs on the force_cpu path — only device/compute_type/models come from `CPU_FALLBACK`; language/timing/`_FIXED_KWARGS` still come from `cfg`.
- ❌ Don't reorder `latency`/`force_cpu` (latency stays positional-4th; force_cpu keyword-last) — existing positional callers must keep working.
- ❌ Don't call `build_recorder(force_cpu=True)` in unit tests (heavy: imports RealtimeSTT + loads models). Test via `_construct(..., _FakeRecorder, force_cpu=True)` + a signature smoke-check.
- ❌ Don't invent ruff/mypy gates (this project uses pytest only — Gotcha #11).
- ❌ Don't modify any existing test (the new section is ADDITIVE; backward compat is non-negotiable).
- ❌ Don't edit `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or use bare `python`/`pytest`/`uv`.

---

## Confidence Score

**9/10** for one-pass implementation success. The change is tiny (3 surgical edits to daemon.py + an additive test section), the design is locked and justified against three rejected alternatives (research §2), the exact old→new text is given verbatim against the current file, the test plan mirrors idioms already proven in the suite, and the negative scope constraints (don't touch `_resolve_device_config`/`cuda_check`/`__init__`/`main()`) are explicit and gated. The residual uncertainty (−1) is the parallel landing of T2.S3 — but its edit region (`_setup_logging` @~980+) is disjoint from T3.S1's (`cfg_to_kwargs`/`_construct`/`build_recorder` @134–260), so the only practical risk is a git-textual merge, which the verbatim old→new blocks make trivially resolvable. The consuming task (T3.S2) is decoupled by the documented `build_recorder(..., force_cpu=True)` + `recorder=` injection pattern.
