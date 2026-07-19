# Research — P1.M2.T4.S1: Recorder kwargs construction audit (vs PRD §4.4)

> Pre-verified audit of `voice_typing/daemon.py` recorder-kwargs construction against **PRD §4.4**
> on the **6 item clauses (a)–(f)**. **VERDICT: ✅ COMPLIANT — no defect, no code/test change.**
> The deliverable is `plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md` (a NEW standalone
> gap report mirroring `gap_lifecycle.md`'s format). This note holds every fact the implementing
> agent re-verifies + transcribes.

---

## §0 ★ THE 6-CLAUSE COMPLIANCE TABLE (each clause → file:line + ✅)

| # | Clause | PRD §4.4 expected | Code actual (file:line) | ✅ |
|---|--------|-------------------|-------------------------|---|
| **a** | cfg_to_kwargs produces ALL §4.4 kwargs from config | all 20 params present | The 7 **config-derived** kwargs from `cfg_to_kwargs` @198-204: `model`←resolved.final_model, `realtime_model_type`←resolved.realtime_model, `language`←cfg.asr.language, `device`←resolved.device, `compute_type`←resolved.compute_type, `realtime_processing_pause`←cfg.asr.realtime_processing_pause, `post_speech_silence_duration`←cfg.asr.post_speech_silence_duration. The 12 **fixed** VAD/timing/silero kwargs from `_FIXED_KWARGS` @98-119 (merged `kwargs.update(_FIXED_KWARGS)` @205). The 1 **partial callback** via `_PARTIAL_CALLBACK_ATTR` @117. Total = 20. | ✅ |
| **b** | `silero_backend='auto'` (modern control; supersedes legacy `silero_use_onnx=True`) | silero_backend="auto"; no silero_use_onnx | `_FIXED_KWARGS["silero_backend"]="auto"` @106. Legacy `silero_use_onnx` is **ABSENT** from `_FIXED_KWARGS`+`cfg_to_kwargs` — it survives ONLY as a docstring instruction @41 ("DROP the legacy silero_use_onnx=True"). Test @262 asserts `"silero_use_onnx" not in kw`. | ✅ |
| **c** | `no_log_file=True` (suppress realtimesst.log) | no_log_file=True | `_FIXED_KWARGS["no_log_file"]=True` @111 (comment: "bugfix Issue 1: suppress RealtimeSTT's unbounded realtimesst.log"). Test @253-254 asserts present + True. | ✅ |
| **d** | `ensure_sentence_starting_uppercase=False` + `ensure_sentence_ends_with_period=False` (textproc owns casing) | both False | `_FIXED_KWARGS["ensure_sentence_starting_uppercase"]=False` @109, `["ensure_sentence_ends_with_period"]=False` @110 (comment: "item correction (b); textproc owns cleanup"). Test @269-270 asserts both False. | ✅ |
| **e** | `_filter_kwargs_to_signature` handles API drift safely | unknown kwarg logged-and-skipped, never crash | `_filter_kwargs_to_signature` @253-283: inspects `recorder_cls.__init__` params; if any `VAR_KEYWORD` (**kwargs) → return everything @257; else strict-drop unknown keys into `dropped[]` + `logger.warning(...)` @277-281. The installed `AudioToTextRecorder.__init__` has **84 params (excl self), NO \*\*kwargs** → strict-drop is the production path. **LIVE PROBE: all 23 kwargs (20 PRD + 3 on_vad) are present in the signature → MISSING = []** (nothing dropped on the current install). | ✅ |
| **f** | callbacks wired: on_realtime_transcription_stabilized→_partial, on_vad_stop→_vad_stop, on_vad_detect_start/on_vad_start→phase | all 4 callbacks wired + in signature | `_build_callbacks` @217-253 returns: `on_realtime_transcription_stabilized`→`_partial` @246, `on_vad_detect_start`→`feedback.set_phase("listening")` @247, `on_vad_start`→`feedback.set_phase("speaking")` @2448, `on_vad_stop`→`_vad_stop` @249. `_construct` @311-313 merges them then filters. All 4 present in the installed signature (LIVE PROBE OK). | ✅ |

---

## §1 The construction call chain (how kwargs flow to AudioToTextRecorder)

```
build_recorder(cfg, feedback, latency, force_cpu, on_speech, lite)   # daemon.py @323-345 — production wrapper
  └─ lazy: from RealtimeSTT import AudioToTextRecorder               # @341 (keeps `import daemon` cheap)
  └─ _construct(cfg, feedback, AudioToTextRecorder, latency, force_cpu, on_speech, lite)  # @285-313
       ├─ resolved = dict(cuda_check.CPU_FALLBACK) if force_cpu else None                 # @308
       ├─ kwargs   = cfg_to_kwargs(cfg, resolved=resolved, lite=lite)                     # @311 (the 20 non-callback kwargs)
       ├─ kwargs.update(_build_callbacks(feedback, latency, on_speech))                   # @312 (+ 4 callbacks)
       ├─ filtered = _filter_kwargs_to_signature(kwargs, recorder_cls)                    # @313 (API-drift defense)
       └─ return recorder_cls(**filtered)                                                  # @313 — AudioToTextRecorder(**filtered)
```

- `cfg_to_kwargs` @158-216: the SINGLE source of truth for the 20 non-callback kwargs (model identity,
  device, timing, VAD, silero, spinner, casing, no_log_file). Splits into 7 config-derived + 12 fixed.
- `_FIXED_KWARGS` @98-119: the 12 PRD §4.4 "do not expose in config.toml" values (enable_realtime,
  use_main_model_for_realtime=False, min_length_of_recording=0.3, min_gap=0.0, silero_sensitivity=0.4,
  webrtc_sensitivity=3, silero_backend="auto", spinner=False, use_microphone=True,
  ensure_sentence_starting_uppercase=False, ensure_sentence_ends_with_period=False, no_log_file=True).
- `_build_callbacks` @217-253: the 4 RealtimeSTT→Feedback callbacks (need the Feedback instance, so
  NOT in _FIXED_KWARGS). `_PARTIAL_CALLBACK_ATTR="on_realtime_transcription_stabilized"` @117.
- `_filter_kwargs_to_signature` @253-283: the API-drift safety net (clause e).

---

## §2 LIVE RealtimeSTT signature probe (the clause-(e) compatibility check)

Ran live against the installed wheel (`RealtimeSTT.audio_recorder.AudioToTextRecorder`):

```
param count (excl self): 84
has **kwargs (VAR_KEYWORD): False
MISSING from installed signature: []     # ← ALL 23 kwargs accepted; _filter drops NOTHING on this install
```

All 20 PRD §4.4 params + the 3 on_vad callbacks (on_vad_detect_start / on_vad_start / on_vad_stop)
are **OK** (present). `silero_backend`, `no_log_file`, `ensure_sentence_starting_uppercase`,
`ensure_sentence_ends_with_period` are all accepted → confirms the item corrections (a)(b) and the
modern vs legacy control are valid against THIS version. (No `__version__` attr on the package; the
signature itself is the compatibility proof — exactly what PRD §8 "RealtimeSTT API drift … Read the
installed version's signature first" prescribes.)

**Implication:** on the current install `_filter_kwargs_to_signature` drops zero kwargs — the
strict-drop path is pure defense-in-depth for a FUTURE RealtimeSTT upgrade that renames/removes a
kwarg. The accept-all (`VAR_KEYWORD`) early-return @257 is exercised only by the accept-all fake test.

---

## §3 Test evidence (the contract's acceptance gate — re-ran live)

```bash
# Canonical "recorder kwargs construction" slice (mocked-CUDA, ~0.03s):
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q \
  -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
# → 32 passed, 161 deselected in 0.04s
```

Clause-specific tests (all in `tests/test_daemon.py`):

| Clause | Test (file:line) | Asserts |
|--------|------------------|---------|
| a | `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` @112 | the 20-key non-callback set is exact (no extra/missing) |
| a | `test_cfg_to_kwargs_passes_through_config_values` @281 | config values flow through |
| a | `test_cfg_to_kwargs_calls_resolve_with_cfg_defaults` @300 | cfg defaults → cuda_check |
| b | `test_cfg_to_kwargs_silero_correction` @257 | `silero_backend=="auto"` AND `"silero_use_onnx" not in kw` |
| c | `test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log` @247 | `"no_log_file" in kw` and `True` |
| d | `test_cfg_to_kwargs_textproc_owns_cleanup` @265 | both ensure_sentence_* `False` |
| e | `test_filter_keeps_kwargs_in_signature` @357 | known kwarg kept |
| e | `test_filter_drops_unknown_kwargs` @363 | unknown kwarg dropped + WARNING (caplog) |
| e | `test_filter_accepts_all_when_var_keyword` @373 | **kwargs class → everything kept |
| e | `test_construct_drops_kwargs_not_in_strict_recorder` @409 | strict-drop wired in _construct |
| f | `test_construct_callbacks_are_live` @398 | callbacks reach the recorder |
| f | `test_construct_wires_on_speech_into_partial_callback` @419 | on_speech threaded into _partial |

(The `-k` filter also pulls in the 5 `test_construct_force_cpu_*` tests + `test_build_recorder_*` —
all green; they are construction-path coverage but their clauses are owned by cuda_check/force_cpu
audits P1.M1.T4.S1, referenced not re-audited here.)

---

## §4 Non-defect nuances (record so they are NOT mistaken for gaps)

1. **`compute_type` is NOT a config field (config.py:20)** — it is a cuda_check concern, derived in
   `_resolve_device_config` @160-170 (`"float16" if device=="cuda" else "int8"`) before cuda_check.
   PRD §4.5 has no `compute_type` key, so its absence from `AsrConfig` is correct, NOT a gap.
2. **The 4 callbacks are wired in `_build_callbacks`, not `_FIXED_KWARGS`/`cfg_to_kwargs`** — they
   need the `Feedback` instance (the partial callback closes over `feedback.update_partial`). Correct
   layering; `cfg_to_kwargs` deliberately returns only the 20 non-callback kwargs.
3. **`silero_use_onnx` survives only as a docstring instruction** @41 ("DROP the legacy …"). It is NOT
   a live kwarg anywhere; the negative assertion @262 guards its absence. Not a stale reference to fix.
4. **`input_device_index` is intentionally UNSET** (PRD §4.4 "leave unset → PipeWire default source").
   `test_cfg_to_kwargs_no_device_index_overrides` @273 pins this. Not a gap.
5. **On the current install `_filter_kwargs_to_signature` drops nothing** (all 23 kwargs present). The
   defense is forward-looking (a RealtimeSTT upgrade renaming a kwarg). Both code paths (strict-drop +
   accept-all) are unit-tested with fakes — the real class has no `**kwargs`.
6. **`_PARTIAL_CALLBACK_ATTR` is a single switch** @117 (`on_realtime_transcription_stabilized`; the
   PRD-preferred "more accurate, slight delay" callback). A one-line swap to
   `on_realtime_transcription_update` (faster, rougher) is documented @114-116. Not a gap — a tuning knob.

---

## §5 The `gap_recorder_kwargs.md` report structure (mirror `gap_lifecycle.md`)

- **Title:** `# Gap Report — P1.M2.T4.S1: Recorder Kwargs Construction vs PRD §4.4`
- **Date** + **Scope** (the 6 clauses) + **Audited artifacts** (file:line list from §1).
- **"Bottom line:"** ✅ COMPLIANT (all 6 clauses) + the test count (32 passed) + the live signature
  probe (84 params, no \*\*kwargs, MISSING=[]).
- **§1 Method:** the grep commands (§6) + the live signature probe (§2) + the test command (§3).
- **§2 per-clause compliance table** (§0): PRD §4.4 expected | code actual (file:line) | ✅.
- **§3 test evidence** (32 passed, 161 deselected in 0.04s; the 12 clause-specific tests).
- **§4 non-defect nuances** (§4 above).
- **§5 API-drift compatibility note** (the §2 probe — all 23 kwargs accepted by the installed signature).
- **Conclusion:** ties verdict to PRD §4.4 + §8 "API drift" mitigation (read installed signature first;
  drop unknown kwargs rather than crash).

**NEW standalone file** in `plan/006_862ee9d6ef41/architecture/` (like `gap_lite.md`/`gap_config.md`),
NOT appended to an existing gap report.

---

## §6 Re-verification commands (the §1 "Commands run" block)

```bash
cd /home/dustin/projects/voice-typing
# 1. Locate every kwargs-construction site:
grep -nE 'def cfg_to_kwargs|def _build_callbacks|def _filter_kwargs_to_signature|def _construct|def build_recorder|_FIXED_KWARGS|_PARTIAL_CALLBACK_ATTR|silero_backend|no_log_file|ensure_sentence|silero_use_onnx|on_vad' voice_typing/daemon.py
# 2. Config fields that feed cfg_to_kwargs:
grep -nE 'final_model|realtime_model|language|device|post_speech_silence_duration|realtime_processing_pause|compute_type' voice_typing/config.py
# 3. LIVE RealtimeSTT signature compatibility probe (clause e):
timeout 60 .venv/bin/python -c "import inspect; from RealtimeSTT import AudioToTextRecorder; p=inspect.signature(AudioToTextRecorder.__init__).parameters; need=['model','realtime_model_type','language','device','compute_type','enable_realtime_transcription','realtime_processing_pause','use_main_model_for_realtime','post_speech_silence_duration','min_length_of_recording','min_gap_between_recordings','silero_sensitivity','webrtc_sensitivity','silero_backend','spinner','use_microphone','ensure_sentence_starting_uppercase','ensure_sentence_ends_with_period','no_log_file','on_realtime_transcription_stabilized','on_vad_detect_start','on_vad_start','on_vad_stop']; print('VAR_KEYWORD:', any(v.kind==inspect.Parameter.VAR_KEYWORD for v in p.values())); print('MISSING:', [k for k in need if k not in p])"
# 4. The construction test slice:
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
#   → 32 passed, 161 deselected in 0.04s
# 5. Scope guard:
git status --short   # → ONLY plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md (new)
```

---

## §7 Scope boundaries (disjoint from siblings — no conflict)

- **This task** = the COMMON recorder kwargs construction (all 20 §4.4 params + 4 callbacks +
  `_filter_kwargs_to_signature` API-drift safety) for the NORMAL (non-lite) path.
- **P1.M2.T3.S1** = the LITE DELTA (the 4 fields lite changes: model, realtime_model_type,
  use_main_model_for_realtime, post_speech_silence_duration) — it REFERENCES this audit's common-block
  findings but does not re-audit them. (`gap_lite.md`.)
- **P1.M2.T3.S3** (parallel, in flight) = T7 lite E2E test COVERAGE — disjoint topic + disjoint files.
- **P1.M1.T4.S1** = `cuda_check` probe + CPU-fallback RESOLUTION (the `resolved` dict that feeds
  `cfg_to_kwargs`'s device/compute_type/models) — `gap_cuda_check.md`. This audit CONSUMES that
  resolution; it does not re-audit the cuda_check driver.
- **DO NOT TOUCH:** `gap_lifecycle.md` (owned by P1.M2.T2.x), `gap_lite.md` (P1.M2.T3.S1),
  `gap_cuda_check.md` (P1.M1.T4.S1), `voice_typing/*`, `tests/*`, `PRD.md`, `**/tasks.json`,
  `**/prd_snapshot.md`, `.gitignore`.