# Gap Report — P1.M2.T4.S1: Recorder Kwargs Construction vs PRD §4.4

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/daemon.py`'s **normal-path recorder-kwargs construction**
(`cfg_to_kwargs()` → `_FIXED_KWARGS` merge → `_build_callbacks()` → `_construct()` →
`_filter_kwargs_to_signature()` → `build_recorder()`) against **PRD §4.4** on the
**6 item clauses (a)–(f)**, PLUS the **live RealtimeSTT signature-compatibility probe**
(PRD §8 "RealtimeSTT API drift … Read the installed version's signature first" mitigation).
The audited code regions are: `_FIXED_KWARGS` (L99-119), `_PARTIAL_CALLBACK_ATTR` (L117),
`cfg_to_kwargs` (L158-216 — the 7 config-derived kwargs @196-204 + `_FIXED_KWARGS` merge @205 +
lite overrides @208-216), `_build_callbacks` (L217-253 — the 4 callbacks @246-249),
`_filter_kwargs_to_signature` (L253-283 — VAR_KEYWORD accept-all @263-264, strict-drop+WARNING
@277-281), `_construct` (L285-313 — kwargs build @311, callbacks merge @312, filter @313,
`recorder_cls(**filtered)` @313), and `build_recorder` (L317-345 — lazy RealtimeSTT import + thin
production wrapper). The config fields that feed `cfg_to_kwargs` are in `voice_typing/config.py`
`AsrConfig` (L49-114). Subtask **P1.M2.T4.S1** of verification round `006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `_FIXED_KWARGS` (L99-119: `enable_realtime_transcription` @100,
  `use_main_model_for_realtime=False` @102, `min_length_of_recording=0.3` @103, `min_gap_between_
  recordings=0.0` @104, `silero_sensitivity=0.4` @105, `silero_backend="auto"` @106,
  `webrtc_sensitivity=3` @107, `spinner=False` @108, `ensure_sentence_starting_uppercase=False`
  @109, `ensure_sentence_ends_with_period=False` @110, `no_log_file=True` @111,
  `use_microphone=True` @112); `_PARTIAL_CALLBACK_ATTR="on_realtime_transcription_stabilized"`
  @117; `cfg_to_kwargs` (L158: the 7 config-derived kwargs @196-204; `kwargs.update(_FIXED_KWARGS)`
  @205; lite overrides @208-216); `_build_callbacks` (L217: the 4 callbacks @246-249);
  `_filter_kwargs_to_signature` (L253: VAR_KEYWORD→return-all @263-264; strict-drop into `dropped[]`
  + `logger.warning(...)` @277-281); `_construct` (L285: `resolved` @308, `cfg_to_kwargs` @311,
  `kwargs.update(_build_callbacks(...))` @312, `_filter_kwargs_to_signature(kwargs, recorder_cls)`
  @313, `return recorder_cls(**filtered)` @313); `build_recorder` (L317: lazy
  `from RealtimeSTT import AudioToTextRecorder` + thin production wrapper). The legacy
  `silero_use_onnx=True` survives ONLY as a docstring instruction @41 ("DROP the legacy
  silero_use_onnx=True") — NOT a live kwarg.
- `voice_typing/config.py` — `AsrConfig` (L49: `final_model="distil-large-v3"` @52,
  `realtime_model="small.en"` @53, `language="en"` @56, `device="cuda"` @57,
  `post_speech_silence_duration=0.6` @58, `lite_post_speech_silence_duration=0.5` @59,
  `realtime_processing_pause=0.15` @64; the comment @20 explicitly states
  "`compute_type` is NOT a config field (it is a [cuda_check] concern)").
- `tests/test_daemon.py` — the construction slice
  `-k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"`
  (the contract's run target; the daemon fakes inject a fake `recorder_cls` so the tests NEVER import
  RealtimeSTT/load models/touch CUDA — the slice is mocked-CUDA at ~0.03s).
- `RealtimeSTT.audio_recorder.AudioToTextRecorder.__init__` — the **installed** constructor
  signature, introspected live via `inspect.signature` (the PRD §8 "read installed signature" check).

**Bottom line:** ✅ All 6 item clauses (a)–(f) are **COMPLIANT** (each with `voice_typing/daemon.py` /
`voice_typing/config.py` file:line evidence below). The **live RealtimeSTT signature probe** reports
**84 params (excl `self`), NO `**kwargs` (VAR_KEYWORD: False), MISSING: `[]`** — so ALL 23 kwargs
(20 PRD §4.4 params + 3 on_vad callbacks) are accepted by the installed signature and
`_filter_kwargs_to_signature` drops NOTHING on the current install. The contract's construction slice
is **32 passed, 161 deselected in 0.03s** (re-ran live; matches the verified baseline of
**32 passed, 161 deselected in 0.04s**). Six **non-defect nuances** are recorded so they are not
mistaken for gaps (§4). **No source files were modified** — the recorder kwargs construction is
PRD §4.4-compliant per this re-verification (no defect surfaced). The only new artifact is this report.

---

## 1. Method

Each of the 6 clauses was mapped to **specific `voice_typing/daemon.py` / `voice_typing/config.py`
file:line** via `grep -nE`, then re-verified by reading `_FIXED_KWARGS` (L99-119), `_PARTIAL_CALLBACK_ATTR`
(L117), `cfg_to_kwargs` (L158-216), `_build_callbacks` (L217-253), `_filter_kwargs_to_signature`
(L253-283), `_construct` (L285-313), and `build_recorder` (L317-345) against the **PRD §4.4** wording
(the exact 20 starting values incl. the two item corrections — `silero_backend="auto"` superseding
the legacy `silero_use_onnx=True`, and `ensure_sentence_*` both False — plus `no_log_file=True`
(bugfix Issue 1) and the "drop unknown kwargs rather than crash" API-drift rule from PRD §8). The
**live RealtimeSTT signature probe** (PRD §8) was then re-run against the installed wheel to confirm
all 23 kwargs are present in `AudioToTextRecorder.__init__`. The contract's construction test slice
was then re-run live (`tests/test_daemon.py -k "cfg_to_kwargs or filter_keeps or filter_drops or
filter_accepts or construct or build_recorder"`, §3). The 6 non-defect nuances (§4) were
cross-checked against the code comments (daemon.py:20-21 `_FIXED_KWARGS` rationale; config.py:20
"`compute_type` is NOT a config field"; daemon.py:41 docstring "DROP the legacy silero_use_onnx";
daemon.py:258-262 filter "defensive vs RealtimeSTT API drift" rationale; daemon.py:228-230
"`latency` is OPTIONAL … so S1's callers keep working").

### Commands run (re-verification)

```bash
# locate every kwargs-construction site (the fixed dict, the builder, the callbacks, the filter, the wrapper)
grep -nE 'def cfg_to_kwargs|def _build_callbacks|def _filter_kwargs_to_signature|def _construct|def build_recorder|_FIXED_KWARGS|_PARTIAL_CALLBACK_ATTR|silero_backend|no_log_file|ensure_sentence|silero_use_onnx|on_vad' voice_typing/daemon.py
# config fields that feed cfg_to_kwargs
grep -nE 'final_model|realtime_model|language|device|post_speech_silence_duration|realtime_processing_pause|compute_type' voice_typing/config.py
# LIVE RealtimeSTT signature compatibility probe (clause e — the PRD §8 API-drift check)
timeout 60 .venv/bin/python -c "import inspect; from RealtimeSTT import AudioToTextRecorder; p=inspect.signature(AudioToTextRecorder.__init__).parameters; need=['model','realtime_model_type','language','device','compute_type','enable_realtime_transcription','realtime_processing_pause','use_main_model_for_realtime','post_speech_silence_duration','min_length_of_recording','min_gap_between_recordings','silero_sensitivity','webrtc_sensitivity','silero_backend','spinner','use_microphone','ensure_sentence_starting_uppercase','ensure_sentence_ends_with_period','no_log_file','on_realtime_transcription_stabilized','on_vad_detect_start','on_vad_start','on_vad_stop']; print('params(excl self):', len(p)-1); print('VAR_KEYWORD:', any(v.kind==inspect.Parameter.VAR_KEYWORD for v in p.values())); print('MISSING:', [k for k in need if k not in p])"
# the contract's run target (re-ran live)
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
# scope guard — no source modified
git status --short
```

---

## 2. The 6 item clauses — per-clause compliance table

| # | Clause (PRD §4.4) | PRD §4.4 expected | Code actual (`voice_typing/daemon.py` / `config.py`) | Verdict |
|---|---|---|---|---|
| (a) | `cfg_to_kwargs` emits ALL 20 §4.4 kwargs from config + `_FIXED_KWARGS` | all 20 params present (7 config-derived + 12 fixed + partial-callback-attr wiring point) | The **7 config-derived** kwargs in `cfg_to_kwargs` **@196-204**: `model`←resolved.final_model @197, `realtime_model_type`←resolved.realtime_model @198, `language`←cfg.asr.language @199, `device`←resolved.device @200, `compute_type`←resolved.compute_type @201, `realtime_processing_pause`←cfg.asr.realtime_processing_pause @202, `post_speech_silence_duration`←cfg.asr.post_speech_silence_duration @203; then `kwargs.update(_FIXED_KWARGS)` **@205** merges the **12 fixed** values (`_FIXED_KWARGS` @99-119). The config fields live in `AsrConfig` @49 (`final_model` @52, `realtime_model` @53, `language` @56, `device` @57, `post_speech_silence_duration` @58, `realtime_processing_pause` @64). The 1 partial-callback attr `_PARTIAL_CALLBACK_ATTR="on_realtime_transcription_stabilized"` @117 is the wiring point used by `_build_callbacks` @246 (clause f). Total non-callback kwargs = 20 (7+12+`_PARTIAL_CALLBACK_ATTR`'s slot filled in `_build_callbacks`). | ✅ **COMPLIANT** |
| (b) | `silero_backend="auto"` (modern control; supersedes the legacy `silero_use_onnx=True`) | `silero_backend="auto"`; NO `silero_use_onnx` | `_FIXED_KWARGS["silero_backend"]="auto"` **@106** (comment "item correction (a); avoids torch-hub download"). The legacy `silero_use_onnx` is **ABSENT** from `_FIXED_KWARGS` + `cfg_to_kwargs` — it survives ONLY as a docstring instruction **@41** ("→ already avoids the torch-hub download. DROP the legacy silero_use_onnx=True"). Test `test_cfg_to_kwargs_silero_correction` @257 asserts `kw["silero_backend"]=="auto"` AND `"silero_use_onnx" not in kw`. | ✅ **COMPLIANT** |
| (c) | `no_log_file=True` (suppress the unbounded `realtimesst.log`) | `no_log_file=True` | `_FIXED_KWARGS["no_log_file"]=True` **@111** (comment "bugfix Issue 1: suppress RealtimeSTT's unbounded realtimesst.log (PRD §4.2 sole path = stderr→journald)"). Test `test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log` @247 asserts `"no_log_file" in kw` and `True`. | ✅ **COMPLIANT** |
| (d) | `ensure_sentence_starting_uppercase=False` + `ensure_sentence_ends_with_period=False` (textproc owns casing) | both `False` | `_FIXED_KWARGS["ensure_sentence_starting_uppercase"]=False` **@109** + `["ensure_sentence_ends_with_period"]=False` **@110** (comment "item correction (b); textproc owns cleanup"). Test `test_cfg_to_kwargs_textproc_owns_cleanup` @265 asserts both are `False`. | ✅ **COMPLIANT** |
| (e) | `_filter_kwargs_to_signature` handles RealtimeSTT API drift safely | unknown kwarg logged-and-skipped, NEVER a crash; accept-all when `**kwargs` | `_filter_kwargs_to_signature` **@253-283**: inspects `recorder_cls.__init__` params @262; if any `VAR_KEYWORD` (`**kwargs`) → `return dict(kwargs)` (accept-all) **@263-264**; else strict-drop unknown keys into `dropped[]` @272 + `logger.warning(...)` per dropped set **@277-281**. **LIVE PROBE:** the installed `AudioToTextRecorder.__init__` has **84 params (excl self), NO `**kwargs`** → strict-drop is the production path; **all 23 kwargs (20 PRD + 3 on_vad) are present → MISSING = `[]`** → nothing dropped on the current install. | ✅ **COMPLIANT** |
| (f) | callbacks wired: `on_realtime_transcription_stabilized`→`_partial`; `on_vad_detect_start`/`on_vad_start`→phase; `on_vad_stop`→`_vad_stop` | all 4 callbacks wired + present in the signature | `_build_callbacks` **@217-253** returns: `on_realtime_transcription_stabilized` (via `_PARTIAL_CALLBACK_ATTR` @117)→`_partial` **@246** (calls `feedback.update_partial(text)` + optional `latency.note_partial` + `on_speech`); `on_vad_detect_start`→`feedback.set_phase("listening")` **@247**; `on_vad_start`→`feedback.set_phase("speaking")` **@248**; `on_vad_stop`→`_vad_stop` **@249** (calls `feedback.set_phase("listening")` + optional `latency.note_speech_end`). `_construct` **@312** merges them (`kwargs.update(_build_callbacks(...))`), then **@313** filters + `recorder_cls(**filtered)`. All 4 present in the installed signature (LIVE PROBE OK). | ✅ **COMPLIANT** |

---

## 3. Test result — the contract's run target (the evidence)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q \
    -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
# → 32 passed, 161 deselected in 0.03s
```

**Recorded count: 32 passed, 161 deselected** (matches the verified baseline of
**32 passed, 161 deselected in 0.04s**; re-ran live during this audit). The slice is CUDA-free —
the tests pass a fake `recorder_cls` so they NEVER import RealtimeSTT/load models/touch CUDA
(`_construct` was split out from `build_recorder` precisely so the filter + callback wiring can be
exercised at ~0.03s). The `timeout 300` inner + bash-tool outer wrap are mandatory (AGENTS.md Rule 1).

### Clause → covering test mapping

| Clause | Covering test (`tests/test_daemon.py` file:line) | What it asserts |
|---|---|---|
| (a) | `test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set` @112 | the 20-key non-callback set is exact (no extra/missing) |
| (a) | `test_cfg_to_kwargs_passes_through_config_values` @281 | config values flow through into kwargs |
| (a) | `test_cfg_to_kwargs_calls_resolve_with_cfg_defaults` @300 | cfg defaults are threaded into cuda_check resolve |
| (b) | `test_cfg_to_kwargs_silero_correction` @257 | `silero_backend=="auto"` AND `"silero_use_onnx" not in kw` |
| (c) | `test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log` @247 | `"no_log_file" in kw` and `kw["no_log_file"] is True` |
| (d) | `test_cfg_to_kwargs_textproc_owns_cleanup` @265 | both `ensure_sentence_*` `False` |
| (e) | `test_filter_keeps_kwargs_in_signature` @357 | a known kwarg is kept |
| (e) | `test_filter_drops_unknown_kwargs` @363 | an unknown kwarg is dropped + a WARNING is logged (caplog) |
| (e) | `test_filter_accepts_all_when_var_keyword` @373 | a `**kwargs` class → everything is kept verbatim |
| (e) | `test_construct_drops_kwargs_not_in_strict_recorder` @409 | strict-drop is wired into `_construct` |
| (f) | `test_construct_callbacks_are_live` @398 | callbacks reach the recorder via `_construct` |
| (f) | `test_construct_wires_on_speech_into_partial_callback` @419 | `on_speech` is threaded into the `_partial` callback |

(The `-k` filter also pulls in the `test_construct_force_cpu_*` + `test_build_recorder_*` coverage
— all green; their clauses are owned by the cuda_check/force_cpu audits P1.M1.T4.S1, referenced not
re-audited here.)

---

## 4. Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for gaps)

### (i) `compute_type` is NOT a config field (config.py:20)

`compute_type` is NOT a key in `AsrConfig` — `config.py:20` explicitly comments
"`compute_type` is NOT a config field (it is a [cuda_check] concern)". It is **derived** in
`_resolve_device_config` (`"float16"` if `device=="cuda"` else `"int8"`) before cuda_check, then
flows into `cfg_to_kwargs` @201 via the `resolved` dict. PRD §4.5 has no `compute_type` key, so its
absence from `AsrConfig` is **correct**, not a gap. The cuda_check device/compute_type/model
**resolution** is owned by **P1.M1.T4.S1** (`gap_cuda_check.md`); this audit CONSUMES the resolution
and does not re-audit the driver.

### (ii) the 4 callbacks are wired in `_build_callbacks`, NOT in `_FIXED_KWARGS`/`cfg_to_kwargs`

The 4 RealtimeSTT→Feedback callbacks (`on_realtime_transcription_stabilized`, `on_vad_detect_start`,
`on_vad_start`, `on_vad_stop`) are deliberately NOT in `_FIXED_KWARGS` or `cfg_to_kwargs` — they
close over the `Feedback` instance (`_partial` calls `feedback.update_partial(text)`;
`_vad_stop` calls `feedback.set_phase("listening")`), so they need the Feedback object and are
built in `_build_callbacks` @217, merged into `kwargs` AFTER `cfg_to_kwargs` in `_construct` @312.
Correct layering: `cfg_to_kwargs` is the SINGLE source of truth for the 20 non-callback kwargs;
`_build_callbacks` owns the 4 callbacks. **Not** a gap.

### (iii) `silero_use_onnx` survives ONLY as a docstring instruction @41

`silero_use_onnx` appears at daemon.py **@41** SOLELY as a docstring instruction ("DROP the legacy
silero_use_onnx=True") documenting WHY `silero_backend="auto"` is used instead. It is NOT a live
kwarg anywhere — it is absent from `_FIXED_KWARGS` and `cfg_to_kwargs`, and the negative assertion
`"silero_use_onnx" not in kw` in `test_cfg_to_kwargs_silero_correction` @257 GUARDS its absence.
**Not** a stale reference to fix.

### (iv) `input_device_index` is intentionally UNSET

PRD §4.4 specifies "leave `input_device_index` unset → use the PipeWire default source". `cfg_to_kwargs`
does NOT emit `input_device_index`, so it is absent from kwargs — correct (the recorder falls back to
its default device selection). Pinned by `test_cfg_to_kwargs_no_device_index_overrides`. **Not** a gap.

### (v) on the current install `_filter_kwargs_to_signature` drops NOTHING

The LIVE probe (§5) confirms all 23 kwargs (20 PRD §4.4 params + 3 on_vad callbacks) are present in
the installed `AudioToTextRecorder.__init__` signature → `MISSING = []` → the strict-drop path drops
zero kwargs on this install. The filter is **forward-looking defense-in-depth** for a FUTURE
RealtimeSTT upgrade that renames/removes a kwarg (e.g. `silero_backend`→`silero_mode`, or
`no_log_file` dropped). Both code paths (strict-drop + accept-all) are unit-tested with fakes — the
real class has no `**kwargs`. **Not** a "the filter does nothing" gap — it is the PRD §8 prescribed
mitigation, just currently a no-op because the install matches the contract.

### (vi) `_PARTIAL_CALLBACK_ATTR` is a single tunable switch @117

`_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"` @117 is the PRD-preferred "more
accurate, slight delay" partial callback (used by `_build_callbacks` @246). A one-line swap to
`on_realtime_transcription_update` (faster, rougher) is the documented tuning knob — the constant
isolates that choice. **Not** a gap — a deliberate tuning point.

---

## 5. API-drift compatibility note (the PRD §8 mitigation)

PRD §8 risk table: *"RealtimeSTT API drift vs this doc → Read the installed version's signature
first; kwargs here are v1.0.x-era, adjust names not intent."* The code realization is
`_filter_kwargs_to_signature` @253-283 (drop unknown kwargs rather than crash) + the
`_construct` call site @313 that gates every construction through it. This audit re-ran the live
signature probe against the installed wheel:

```
AudioToTextRecorder.__init__ signature (installed):
  param count (excl self): 84
  has **kwargs (VAR_KEYWORD): False
  MISSING from the 23 contract kwargs: []     # ← ALL 23 accepted; _filter drops NOTHING on this install
```

All 20 PRD §4.4 params + the 3 on_vad callbacks (`on_vad_detect_start` / `on_vad_start` /
`on_vad_stop`) are **OK** (present). The item corrections — `silero_backend`, `no_log_file`,
`ensure_sentence_starting_uppercase`, `ensure_sentence_ends_with_period` — are all accepted,
confirming the modern-vs-legacy control and the casing-cleanup-OFF settings are valid against THIS
installed version. (The `RealtimeSTT` package exposes no `__version__` attr; the signature itself is
the compatibility proof — exactly what PRD §8 prescribes.)

**Implication:** the contract's kwargs and the installed signature currently agree, so the strict-drop
path is dormant. If a future upgrade renames/drops a kwarg, `_filter_kwargs_to_signature` will log a
`WARNING` ("dropping N unsupported kwarg(s) … construction proceeds without them") and proceed rather
than raising `TypeError` at arm time — the daemon stays up (degraded) instead of wedging on a
RealtimeSTT version bump. That is the §8 mitigation realized.

---

## Conclusion

The recorder kwargs construction faithfully implements **PRD §4.4** on all 6 clauses (a)–(f):
`cfg_to_kwargs` emits **all 20 §4.4 kwargs** (7 config-derived @196-204 + 12 fixed via
`kwargs.update(_FIXED_KWARGS)` @205, with the partial-callback slot filled by `_build_callbacks`
@246) (a); `silero_backend="auto"` @106 is set and the legacy `silero_use_onnx` is **absent**
(surviving only as a docstring instruction @41) (b); `no_log_file=True` @111 suppresses the
unbounded `realtimesst.log` (c); both `ensure_sentence_*` are `False` @109-110 so textproc owns
casing (d); `_filter_kwargs_to_signature` @253-283 provides the **API-drift safety** (strict-drop +
WARNING + accept-all-when-`**kwargs`) — and the **live signature probe** confirms all 23 kwargs are
accepted by the installed `AudioToTextRecorder.__init__` (84 params, no `**kwargs`, `MISSING=[]`)
(e); and the 4 callbacks are wired in `_build_callbacks` @246-249 and merged in `_construct` @312
(f). All with `voice_typing/daemon.py` / `voice_typing/config.py` file:line evidence; the
construction slice is **32 passed, 161 deselected in 0.03s**.

This certifies the project's acceptance criteria:
- The daemon constructs `AudioToTextRecorder` with **EXACTLY the PRD §4.4 kwargs** (the two item
  corrections `silero_backend="auto"` + `ensure_sentence_*` False applied, and bugfix Issue 1
  `no_log_file=True` applied) — clauses (a)–(d).
- An unknown/renamed kwarg from a RealtimeSTT upgrade is **logged-and-skipped** rather than crashing
  the daemon at arm time (PRD §8 "API drift" mitigation) — clause (e) + §5.
- The partial + VAD callbacks are **correctly wired to feedback** (+ the per-utterance latency log)
  — clause (f).

**Verdict: ✅ COMPLIANT on all 6 clauses — no fix needed.** **No source files were modified** (this
is a read-only audit — the recorder kwargs construction is PRD §4.4 + §8-compliant per this
re-verification). The only artifact produced by this subtask is this report. Adjacent concerns are
correctly deferred: the **lite delta** (the 4 fields lite changes) is **P1.M2.T3.S1** (`gap_lite.md`,
which REFERENCES this audit's common-block findings); the **cuda_check device/compute_type/model
resolution** feeding `cfg_to_kwargs` is **P1.M1.T4.S1** (`gap_cuda_check.md`); the
**construction-failure → CPU retry** is **P1.M1.T3.S1/S2**.