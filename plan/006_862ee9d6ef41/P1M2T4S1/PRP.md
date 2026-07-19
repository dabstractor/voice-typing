# PRP — P1.M2.T4.S1: Audit recorder kwargs construction vs PRD §4.4

## Goal

**Feature Goal**: Produce the authoritative **recorder kwargs construction audit** as a new report
`plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md`, cross-checking the NORMAL-path
recorder-kwargs build (`daemon.cfg_to_kwargs()` → `_FIXED_KWARGS` merge → `_build_callbacks()` →
`_construct()` → `_filter_kwargs_to_signature()` → `build_recorder()`) against **PRD §4.4** on the
**6 item clauses (a)–(f)**, PLUS a **live RealtimeSTT signature-compatibility probe** (PRD §8 "API
drift" mitigation). This is a **verification/audit** subtask of compliance round `006_862ee9d6ef41`:
the deliverable is the report; **code changes happen ONLY if a real defect is found — none is
expected; this PRP's author has already performed the audit and the kwargs construction is
PRD §4.4-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the recorder kwargs construction is COMPLIANT — no fix needed.**
> All 6 clauses (a)–(f) pass (file:line in the research note §0); the **live signature probe**
> confirms the installed `AudioToTextRecorder.__init__` has **84 params (no `**kwargs`)** and **ALL 23
> kwargs (20 PRD §4.4 params + 3 on_vad callbacks) are present — MISSING = `[]`**, so
> `_filter_kwargs_to_signature` drops NOTHING on the current install. The contract's construction
> test slice (`tests/test_daemon.py -q -k "cfg_to_kwargs or filter_keeps or filter_drops or
> filter_accepts or construct or build_recorder"`) = **32 passed, 161 deselected in 0.04s** (re-ran live).

**Deliverable** (ONE report file; NO source edits, NO test edits unless a real defect surfaces):
`plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md` — a **NEW standalone file** (does not exist
yet; siblings: `gap_config.md`/`gap_textproc.md`/`gap_typing.md`/`gap_cuda_check.md`/`gap_daemon_loop.md`
/`gap_lifecycle.md`/`gap_lite.md`). Format mirrors `gap_lifecycle.md`: title + date + scope + audited
artifacts (file:line) + bottom-line verdict + §1 Method (grep + the live signature probe + test
commands) + §2 per-clause compliance table (PRD §4.4 expected vs code actual vs verdict) for (a)–(f) +
§3 test evidence + §4 non-defect nuances + §5 the API-drift compatibility note + conclusion tying the
verdict to PRD §4.4 + §8. **This PRP's author has already performed the audit** (findings in the
research note) — the implementing agent re-verifies, re-runs the probe + tests, and transcribes the report.

**Success Definition**:
- (a) `architecture/gap_recorder_kwargs.md` exists with the title `# Gap Report — P1.M2.T4.S1: Recorder
  Kwargs Construction vs PRD §4.4` and the sub-parts (scope/artifacts, bottom line, §1 method, §2
  compliance table, §3 test evidence, §4 nuances, §5 API-drift note, conclusion).
- (b) The recorded findings match the live re-verification: all 6 clauses (a)–(f) are **compliant**,
  each with `voice_typing/daemon.py` / `config.py` file:line.
- (c) The **live signature probe** is reproduced in the report: 84 params, no `**kwargs`, MISSING=[].
- (d) `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or
  filter_keeps or filter_drops or filter_accepts or construct or build_recorder"` → all pass (record
  the count; verified baseline: **32 passed, 161 deselected in 0.04s**).
- (e) **No source or test files are modified** (no defect exists). If — and only if — re-verification
  surfaces a REAL defect (e.g. the live probe reports a MISSING kwarg), fix it and record the fix;
  otherwise record "none — compliant per audit."
- (f) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md` (new).

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that the daemon constructs
`AudioToTextRecorder` with EXACTLY the PRD §4.4 kwargs (the two item corrections applied —
`silero_backend="auto"` not the legacy `silero_use_onnx=True`; `no_log_file=True`; casing cleanup
OFF because textproc owns it), that an unknown/renamed kwarg from a RealtimeSTT upgrade is
logged-and-skipped rather than crashing the daemon at arm time, and that the partial + VAD callbacks
are correctly wired to feedback. Also the downstream **P1.M5.T5** acceptance-criteria cross-check
(maps acceptance criteria + PRD §8 "API drift" mitigation to this audit's evidence).

**Use Case**: A future RealtimeSTT upgrade renames `silero_backend`→`silero_mode` (or drops
`no_log_file`). The audit + `_filter_kwargs_to_signature` + the live signature probe are the reference
that proves the daemon (a) still constructs, and (b) logs the dropped kwarg instead of crashing.

**Pain Points Addressed**: Closes "does the daemon REALLY pass all 20 PRD §4.4 params? Is
`silero_use_onnx` REALLY dropped? Does `no_log_file` REALLY suppress realtimesst.log? Does the
filter REALLY survive API drift? Are the on_vad/partial callbacks REALLY wired?" with recorded,
re-runnable evidence — not an assumption.

## Why

- **PRD §4.4 is the load-bearing recorder contract.** The exact VAD/timing/silero/casing values
  determine segmentation UX, partial cadence, the torch-hub-download avoidance, and the textproc
  ownership boundary. The audit certifies `cfg_to_kwargs` + `_FIXED_KWARGS` emit all 20 with the two
  item corrections (silero_backend, ensure_sentence_*) and bugfix-1 (no_log_file) applied.
  (PRD §4.4 "exact starting values"; §8 risk table "RealtimeSTT API drift vs this doc".)
- **API-drift safety is a PRD §8 prescribed mitigation.** PRD §8: "RealtimeSTT API drift vs this doc →
  Read the installed version's README/source first; kwargs here are v1.0.x-era, adjust names not
  intent." `_filter_kwargs_to_signature` is the code realization of "drop unknown kwargs rather than
  crash." The audit certifies the filter (a) inspects the live signature, (b) logs-and-skips unknowns,
  (c) accepts-all when the class has `**kwargs`, and (d) — via the live probe — currently drops NOTHING.
- **The two item corrections are correctness, not preference.** `silero_backend="auto"` avoids a
  torch-hub network download at boot (a 24/7 systemd unit must not depend on network); casing cleanup
  OFF means textproc's `clean()` is the single owner (no double capitalization). The audit certifies
  both are set and the legacy `silero_use_onnx` is absent.
- **Scope discipline.** This subtask owns the COMMON (normal-path) recorder kwargs + the API-drift
  filter. The LITE DELTA (4 fields) is **P1.M2.T3.S1**; the cuda_check device/compute_type/model
  RESOLUTION that feeds `cfg_to_kwargs` is **P1.M1.T4.S1**; the construction-failure → CPU retry is
  **P1.M1.T3.S1/S2**. THIS task audits the kwargs builder + the filter + the callback wiring; it
  REFERENCES but does not re-audit the siblings' scopes.

## What

Re-verify the normal-path recorder kwargs construction against PRD §4.4 by reading the cited code
regions (`daemon._FIXED_KWARGS` @98-119, `cfg_to_kwargs` @158-216, `_build_callbacks` @217-253,
`_filter_kwargs_to_signature` @253-283, `_construct` @285-313, `build_recorder` @323-345;
`config.py` `AsrConfig` fields @49-114), running the **live RealtimeSTT signature probe** (PRD §8
"read the installed signature"), re-running the construction test slice, and creating
`architecture/gap_recorder_kwargs.md` in the `gap_*.md` format (mirror `gap_lifecycle.md`). The audit
is expected to confirm full compliance (no defects → no code changes). The report's compliance table
maps each clause (a)–(f) to PRD §4.4 expected behavior vs the code's actual behavior (file:line).

### Success Criteria

- [ ] `architecture/gap_recorder_kwargs.md` exists with the title `# Gap Report — P1.M2.T4.S1: Recorder
  Kwargs Construction vs PRD §4.4` + the sub-parts.
- [ ] Compliance table covers (a) all 20 §4.4 kwargs emitted from config+_FIXED; (b) `silero_backend="auto"`
  + `silero_use_onnx` absent; (c) `no_log_file=True`; (d) both `ensure_sentence_*` False; (e)
  `_filter_kwargs_to_signature` API-drift safety (strict-drop + accept-all); (f) the 4 callbacks wired —
  each COMPLIANT with file:line.
- [ ] The **live signature probe** is reproduced (84 params, no `**kwargs`, MISSING=[]).
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or filter_keeps
  or filter_drops or filter_accepts or construct or build_recorder"` → recorded pass count (baseline
  **32 passed, 161 deselected**).
- [ ] No source/test files modified (`git status --short` == the new report only).
- [ ] Conclusion ties the verdict to PRD §4.4 + §8 "API drift" mitigation.

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §0: every clause mapped
to `daemon.py`/`config.py` file:line with the COMPLIANT verdict + the live signature-probe result +
the 32-test evidence + the construction call chain §1 + the 6 non-defect nuances §4). A developer new
to this repo can re-verify from the research note + the cited code regions: the exact line ranges, the
grep commands + the signature probe to re-locate them, the test command, and the `gap_*.md` format
(sibling `gap_lifecycle.md`). The non-defect nuances (`compute_type` not a config field; callbacks in
`_build_callbacks` not `_FIXED_KWARGS`; `silero_use_onnx` survives only as a docstring instruction;
`input_device_index` intentionally unset; the filter drops nothing on the current install; the partial-
callback attr switch) are documented so they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + signature probe + tests).
- docfile: plan/006_862ee9d6ef41/P1M2T4S1/research/recorder_kwargs_audit.md
  why: "§0 ★ THE 6-CLAUSE TABLE (each clause → daemon.py/config.py file:line + ✅ COMPLIANT). §1 the
        construction call chain (build_recorder→_construct→cfg_to_kwargs+_build_callbacks→_filter→cls).
        §2 the LIVE RealtimeSTT signature probe (84 params, no **kwargs, MISSING=[]). §3 test evidence
        (32 passed; the 12 clause-specific tests with file:line). §4 the 6 non-defect nuances.
        §5 the gap report structure. §6 the re-verification commands. §7 scope boundaries."
  section: "ALL load-bearing. §0 (the table), §2 (the probe), §3 (the count), §5 (the report format)."

# MUST READ — the gap_*.md report format to mirror (structure + voice + per-clause table convention).
- docfile: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "The canonical gap-report format: title + Date/Scope/Audited-artifacts(file:line) + 'Bottom line:'
        verdict + §1 Method (grep + test commands run) + §2 per-property compliance table (PRD expected
        vs code actual vs Verdict) + §3 test pass/fail count + §4 non-defect nuances + conclusion.
        gap_recorder_kwargs.md is a STANDALONE new file in the SAME directory (NOT appended to any
        existing gap report — recorder kwargs is its own audit area, like gap_config.md/gap_lite.md)."
  critical: "gap_recorder_kwargs.md is a NEW file, not a §N-append to gap_lifecycle.md or gap_lite.md.
             Mirror the FORMAT, not an append-to-existing pattern."

# MUST READ — the primary audited source (the kwargs builder + filter + callbacks live here).
- file: voice_typing/daemon.py
  why: "_FIXED_KWARGS @98-119 (the 12 fixed §4.4 values incl. silero_backend='auto' @106, no_log_file=True
        @111, ensure_sentence_* False @109-110). cfg_to_kwargs @158-216 (the 7 config-derived kwargs:
        model/realtime_model_type/language/device/compute_type/realtime_processing_pause/post_speech_
        silence_duration @198-204; kwargs.update(_FIXED_KWARGS) @205). _PARTIAL_CALLBACK_ATTR @117.
        _build_callbacks @217-253 (on_realtime_transcription_stabilized→_partial @246, on_vad_* @247-249).
        _filter_kwargs_to_signature @253-283 (VAR_KEYWORD→accept-all @257; strict-drop+WARNING @277-281).
        _construct @285-313 (merge kwargs+callbacks @311-312, filter @313, cls(**filtered) @313).
        build_recorder @323-345 (lazy RealtimeSTT import @341; thin production wrapper)."
  pattern: "cfg_to_kwargs is the SINGLE source of truth for the 20 non-callback kwargs; the 4 callbacks
            are wired separately in _build_callbacks (they need the Feedback instance); _filter is the
            last gate before construction."
  gotcha: "compute_type is NOT a config field — it is derived in _resolve_device_config @160-170
           ('float16' if cuda else 'int8') before cuda_check. Its absence from AsrConfig is correct
           (PRD §4.5 has no compute_type key) — do NOT flag it as a gap (nuance §4.1)."

# MUST READ — the config fields that feed cfg_to_kwargs (clause a).
- file: voice_typing/config.py
  why: "AsrConfig @49: final_model='distil-large-v3' @52, realtime_model='small.en' @53, language='en'
        @56, device='cuda' @57, post_speech_silence_duration=0.6 @58, realtime_processing_pause=0.15
        @64. The comment @20 explicitly states 'compute_type is NOT a config field'. These 6 fields +
        the derived compute_type are the 7 config-derived kwargs."
  gotcha: "device VALUE validation @112-114 (only 'cuda'|'cpu') feeds _resolve_device_config — owned by
           cuda_check audit P1.M1.T4.S1; referenced, not re-audited here."

# MUST READ — the test file with the kwargs-construction assertions (the 12 clause-specific tests).
- file: tests/test_daemon.py
  why: "test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set @112 (clause a: the 20-key set is exact);
        test_cfg_to_kwargs_silero_correction @257 (clause b: silero_backend='auto' AND silero_use_onnx
        absent); test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log @247 (clause c);
        test_cfg_to_kwargs_textproc_owns_cleanup @265 (clause d); test_filter_keeps_kwargs_in_signature
        @357 + test_filter_drops_unknown_kwargs @363 + test_filter_accepts_all_when_var_keyword @373
        (clause e: strict-drop + WARNING + accept-all); test_construct_callbacks_are_live @398 +
        test_construct_wires_on_speech_into_partial_callback @419 (clause f)."
  critical: "The contract run target is the construction slice: -k 'cfg_to_kwargs or filter_keeps or
             filter_drops or filter_accepts or construct or build_recorder' → 32 passed, 161 deselected.
             Record that count. The 3 filter tests are NAMED test_filter_keeps/drops/accepts (NOT
             test_filter_kwargs_*) — use the exact names in the -k filter or they are deselected."

# SHOULD READ — the PRD spec being audited against (READ-ONLY).
- docfile: PRD.md   # §4.4 (exact kwargs) + §8 (API-drift mitigation)
  why: "§4.4: the 20 exact starting values incl. the 2 item corrections (silero_backend='auto'
        supersedes silero_use_onnx=True; ensure_sentence_* False) + no_log_file=True. §8 risk table:
        'RealtimeSTT API drift vs this doc → Read the installed version's signature first; drop unknown
        kwargs rather than crash.' Match these against the code in the compliance table."

# CONTEXT — the parallel task (DISJOINT topic + files — no conflict).
- docfile: plan/006_862ee9d6ef41/P1M2T3S3/PRP.md
  why: "P1.M2.T3.S3 (in flight) audits T7 lite E2E test COVERAGE (single model resident, ≥70% accuracy,
        snappier latency). DISJOINT topic (lite coverage vs common kwargs construction) + DISJOINT file
        (it touches test scripts/gap_lite-adjacent evidence; this task CREATES gap_recorder_kwargs.md).
        No overlap."
```

### Current Codebase tree (relevant slice — audit reads these; writes ONLY the report)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py          # READ: _FIXED_KWARGS @98-119, cfg_to_kwargs @158-216, _build_callbacks @217-253,
│   │                      #       _filter_kwargs_to_signature @253-283, _construct @285-313, build_recorder @323-345
│   └── config.py          # READ: AsrConfig @49 (final_model @52, realtime_model @53, language @56,
│                          #       device @57, post_speech_silence @58, realtime_processing_pause @64)
├── tests/
│   └── test_daemon.py     # RUN: the construction slice -k (cfg_to_kwargs|filter|construct|build_recorder)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_lifecycle.md   # READ: the format to mirror
    └── gap_recorder_kwargs.md   # CREATE (new) — the deliverable
```

### Desired Codebase tree (what this task produces)

```bash
plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md   # NEW — the recorder kwargs audit report
# No source/test changes. git status --short == this one new file.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — FULL PATHS in every bash command (zsh aliases python3→uv run). Use .venv/bin/python,
#   NEVER bare python/pytest. The construction tests are mocked-CUDA (no real models) → ~0.04s; wrap
#   in `timeout 300` (and the signature probe in `timeout 60`) as the sibling gap reports do.

# CRITICAL #2 — The 3 clause-(e) filter tests are NAMED test_filter_keeps_kwargs_in_signature /
#   test_filter_drops_unknown_kwargs / test_filter_accepts_all_when_var_keyword (i.e. the name token is
#   "filter_keeps"/"filter_drops"/"filter_accepts", NOT "filter_kwargs"). The -k filter MUST use those
#   exact tokens or the 3 tests are deselected. The canonical slice uses:
#     -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
#   (recorded 32 passed). Do NOT use bare "-k filter_kwargs" — it matches NONE of the 3.

# CRITICAL #3 — compute_type is NOT a config field (config.py:20 comment). It is DERIVED in
#   _resolve_device_config ('float16' if device=='cuda' else 'int8'). PRD §4.5 has no compute_type key,
#   so its absence from AsrConfig is CORRECT — do NOT flag it as a gap (nuance §4.1). cuda_check device
#   RESOLUTION is owned by P1.M1.T4.S1 (gap_cuda_check.md) — referenced, not re-audited here.

# CRITICAL #4 — The 4 callbacks are wired in _build_callbacks, NOT in _FIXED_KWARGS/cfg_to_kwargs.
#   They close over the Feedback instance (feedback.update_partial / set_phase), so they are merged
#   AFTER cfg_to_kwargs in _construct (@312). Correct layering — do NOT flag their absence from
#   _FIXED_KWARGS as a gap (nuance §4.2).

# CRITICAL #5 — silero_use_onnx survives ONLY as a docstring instruction @41 ("DROP the legacy …"). It
#   is NOT a live kwarg; the negative assertion @262 guards its absence. Not a stale reference to fix
#   (nuance §4.3).

# CRITICAL #6 — On the CURRENT install _filter_kwargs_to_signature drops NOTHING (all 23 kwargs present
#   per the live probe). The filter is forward-looking defense for a RealtimeSTT upgrade. Both code
#   paths (strict-drop + accept-all) are unit-tested with fakes; the real class has no **kwargs.
#   Record this as a nuance + the §5 API-drift note, NOT as a "the filter does nothing" gap (nuance §4.5).

# CRITICAL #7 — gap_recorder_kwargs.md is a NEW STANDALONE file (like gap_config.md/gap_lite.md), NOT a
#   §N-append to gap_lifecycle.md or gap_cuda_check.md. Mirror gap_lifecycle.md's FORMAT, not the
#   append-to-existing pattern.

# CRITICAL #8 — This is a RE-VERIFICATION of an already-compliant feature. Do NOT invent defects: if
#   the 6 clauses pass (they do) AND the live probe reports MISSING=[] (it does) AND the 32 tests pass,
#   the verdict is ✅ COMPLIANT and NO source/test files change. Code changes occur ONLY if
#   re-verification surfaces a REAL defect (e.g. the probe reports a MISSING kwarg — then fix + record).
```

## Implementation Blueprint

### Data models and structure

None (audit only). The "data" is the 6-clause compliance table + the live signature-probe result +
file:line evidence transcribed into `gap_recorder_kwargs.md`.

### Implementation Tasks (ordered by dependencies — a re-verify + transcribe runbook)

```yaml
Task 1: RE-VERIFY clause (a) — cfg_to_kwargs emits ALL 20 §4.4 kwargs
  - READ daemon.py cfg_to_kwargs @158-216: @198-204 the 7 config-derived kwargs
    (model←resolved.final_model, realtime_model_type←resolved.realtime_model, language←cfg.asr.language,
    device←resolved.device, compute_type←resolved.compute_type, realtime_processing_pause←cfg.asr.realtime_
    processing_pause, post_speech_silence_duration←cfg.asr.post_speech_silence_duration); @205
    kwargs.update(_FIXED_KWARGS) merges the 12 fixed. READ _FIXED_KWARGS @98-119 (the 12 keys).
  - READ config.py AsrConfig @49 (final_model @52, realtime_model @53, language @56, device @57,
    post_speech_silence_duration @58, realtime_processing_pause @64). Confirm compute_type is NOT a
    config field (@20 comment) — it's derived in _resolve_device_config (nuance §4.1).
  - RUN test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set @112 + _passes_through_config_values
    @281 + _calls_resolve_with_cfg_defaults @300.
  - VERDICT: compliant (research §0 row a). Record file:line in gap report §2 row (a).

Task 2: RE-VERIFY clause (b) — silero_backend='auto'; legacy silero_use_onnx dropped
  - READ daemon.py _FIXED_KWARGS @106 ("silero_backend": "auto"). Confirm silero_use_onnx is ABSENT
    from _FIXED_KWARGS + cfg_to_kwargs (survives only as the docstring instruction @41).
  - RUN test_cfg_to_kwargs_silero_correction @257 (asserts silero_backend=="auto" AND
    "silero_use_onnx" not in kw @262).
  - VERDICT: compliant (research §0 row b). Record file:line in §2 row (b).

Task 3: RE-VERIFY clause (c) — no_log_file=True
  - READ daemon.py _FIXED_KWARGS @111 ("no_log_file": True; comment "bugfix Issue 1").
  - RUN test_cfg_to_kwargs_no_log_file_suppresses_realtimesst_log @247 (asserts present + True).
  - VERDICT: compliant (research §0 row c). Record in §2 row (c).

Task 4: RE-VERIFY clause (d) — ensure_sentence_* both False (textproc owns casing)
  - READ daemon.py _FIXED_KWARGS @109-110 (both False; comment "textproc owns cleanup").
  - RUN test_cfg_to_kwargs_textproc_owns_cleanup @265 (asserts both False).
  - VERDICT: compliant (research §0 row d). Record in §2 row (d).

Task 5: RE-VERIFY clause (e) — _filter_kwargs_to_signature API-drift safety + LIVE probe
  - READ daemon.py _filter_kwargs_to_signature @253-283: @257 VAR_KEYWORD→accept-all; @263-273
    strict-drop unknowns into dropped[]; @277-281 logger.warning per dropped set.
  - RUN the LIVE signature probe (research §2/§6 cmd 3): confirm 84 params, no **kwargs, MISSING=[].
  - RUN test_filter_keeps_kwargs_in_signature @357 + test_filter_drops_unknown_kwargs @363 (caplog
    WARNING) + test_filter_accepts_all_when_var_keyword @373 + test_construct_drops_kwargs_not_in_
    strict_recorder @409.
  - VERDICT: compliant (research §0 row e + §2 probe). Record the probe result in §2 row (e) + §5.

Task 6: RE-VERIFY clause (f) — callbacks wired (on_realtime_transcription_stabilized→_partial, on_vad_*)
  - READ daemon.py _build_callbacks @217-253: @246 _PARTIAL_CALLBACK_ATTR→_partial; @247 on_vad_detect_
    start→listening; @248 on_vad_start→speaking; @249 on_vad_stop→_vad_stop. READ _construct @311-313
    (kwargs.update(callbacks) @312 → filter @313 → cls(**filtered) @313). READ _PARTIAL_CALLBACK_ATTR
    @117 = "on_realtime_transcription_stabilized".
  - RUN test_construct_callbacks_are_live @398 + test_construct_wires_on_speech_into_partial_callback @419.
  - VERDICT: compliant (research §0 row f). Record in §2 row (f).

Task 7: RUN the contract construction slice + record the count
  - CMD: timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q \
         -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
  - EXPECTED: 32 passed, 161 deselected in ~0.04s (baseline; research §3). Record in gap report §3.

Task 8: CREATE plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md (mirror gap_lifecycle.md)
  - TITLE: "# Gap Report — P1.M2.T4.S1: Recorder Kwargs Construction vs PRD §4.4"
  - Date + Scope (the 6 clauses + the live probe) + Audited artifacts (file:line list from Tasks 1-6).
  - "Bottom line:" ✅ COMPLIANT (all 6 clauses) + the probe (84 params, no **kwargs, MISSING=[]) + the
    32-test count.
  - §1 Method: the grep commands + the live probe command + the test command (Tasks 1-7).
  - §2 per-clause compliance table (research §0): PRD §4.4 expected | code actual (file:line) | ✅.
  - §3 test evidence (32 passed, 161 deselected; the 12 clause-specific tests + their clauses).
  - §4 non-defect nuances (research §4): compute_type not a config field; callbacks in _build_callbacks;
    silero_use_onnx docstring-only; input_device_index unset; filter drops nothing on current install;
    _PARTIAL_CALLBACK_ATTR switch.
  - §5 API-drift compatibility note (the §2 probe — all 23 kwargs accepted; defense is forward-looking).
  - Conclusion: ties verdict to PRD §4.4 + §8 "API drift" mitigation (read installed signature first;
    drop unknown kwargs rather than crash).

Task 9: SCOPE GUARD — verify no source/test files changed
  - CMD: git status --short
  - EXPECTED: ONLY `plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md` (new). No voice_typing/*,
    no tests/*, no PRD.md/tasks.json/prd_snapshot.md/.gitignore. (If a real defect was found + fixed,
    that source change is ALSO expected — record it; otherwise none.)
```

### Implementation Patterns & Key Details

```bash
# PATTERN — a re-verification audit: read the cited lines, run the LIVE signature probe, run the
# construction test slice, transcribe the report.

# 1. Re-locate every kwargs-construction site (the grep the gap report's §1 will cite):
grep -nE 'def cfg_to_kwargs|def _build_callbacks|def _filter_kwargs_to_signature|def _construct|def build_recorder|_FIXED_KWARGS|_PARTIAL_CALLBACK_ATTR|silero_backend|no_log_file|ensure_sentence|silero_use_onnx|on_vad' voice_typing/daemon.py
grep -nE 'final_model|realtime_model|language|device|post_speech_silence_duration|realtime_processing_pause|compute_type' voice_typing/config.py

# 2. LIVE RealtimeSTT signature compatibility probe (clause e — the PRD §8 "read installed signature"):
timeout 60 .venv/bin/python -c "import inspect; from RealtimeSTT import AudioToTextRecorder; p=inspect.signature(AudioToTextRecorder.__init__).parameters; need=['model','realtime_model_type','language','device','compute_type','enable_realtime_transcription','realtime_processing_pause','use_main_model_for_realtime','post_speech_silence_duration','min_length_of_recording','min_gap_between_recordings','silero_sensitivity','webrtc_sensitivity','silero_backend','spinner','use_microphone','ensure_sentence_starting_uppercase','ensure_sentence_ends_with_period','no_log_file','on_realtime_transcription_stabilized','on_vad_detect_start','on_vad_start','on_vad_stop']; print('VAR_KEYWORD:', any(v.kind==inspect.Parameter.VAR_KEYWORD for v in p.values())); print('MISSING:', [k for k in need if k not in p])"
#   → VAR_KEYWORD: False | MISSING: []

# 3. Re-run the contract construction slice (record the count for §3):
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
#   → 32 passed, 161 deselected in 0.04s

# 4. Create the report (mirror gap_lifecycle.md; standalone NEW file):
#    plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md

# 5. Scope guard:
git status --short   # → ONLY the new gap_recorder_kwargs.md (no voice_typing/*, no tests/*, no PRD/tasks.json).
```

### Integration Points

```yaml
CONSUMED (read-only — verify, don't change):
  - voice_typing/daemon.py: _FIXED_KWARGS @98-119, cfg_to_kwargs @158-216, _build_callbacks @217-253,
    _filter_kwargs_to_signature @253-283, _construct @285-313, build_recorder @323-345.
  - voice_typing/config.py: AsrConfig @49 (final_model @52, realtime_model @53, language @56, device @57,
    post_speech_silence_duration @58, realtime_processing_pause @64).
  - tests/test_daemon.py: the 12 clause-specific kwargs/filter/callback tests.
  - RealtimeSTT.audio_recorder.AudioToTextRecorder.__init__ (the installed signature — via the live probe).
PRODUCED (this task):
  - plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md (NEW) — the recorder kwargs audit.
DOWNSTREAM CONSUMERS:
  - P1.M1.T4.S1 (cuda_check audit): this audit REFERENCES the device/compute_type/model resolution it owns.
  - P1.M2.T3.S1 (lite audit): REFERENCES this audit's common-block (20 kwargs) findings; audits only the
    lite delta (4 fields).
  - P1.M5.T5 (acceptance cross-check): maps PRD §4.4 + §8 "API drift" mitigation to this audit's evidence.
DO NOT TOUCH:
  - voice_typing/* (no defect exists), tests/*, PRD.md, **/tasks.json, **/prd_snapshot.md, .gitignore,
    pyproject.toml, uv.lock. No new deps. gap_lifecycle.md (P1.M2.T2.x), gap_lite.md (P1.M2.T3.S1),
    gap_cuda_check.md (P1.M1.T4.S1) — owned by siblings; do NOT append to them.
```

## Validation Loop

> Full paths in every command (CRITICAL #1). The construction tests are mocked-CUDA (~0.04s); wrap in
> `timeout 300`. The signature probe is a stdlib inspect call (~instant); `timeout 60` is a generous backstop.

### Level 1: Re-verify the 6 clauses against the live source (read the cited lines)

```bash
cd /home/dustin/projects/voice-typing
grep -nE 'def cfg_to_kwargs|def _build_callbacks|def _filter_kwargs_to_signature|def _construct|def build_recorder|_FIXED_KWARGS|_PARTIAL_CALLBACK_ATTR|silero_backend|no_log_file|ensure_sentence|silero_use_onnx|on_vad' voice_typing/daemon.py
grep -nE 'final_model|realtime_model|language|device|post_speech_silence_duration|realtime_processing_pause|compute_type' voice_typing/config.py
# Expected: each clause's file:line from research §0 is present and reads as documented.
#   (a) cfg_to_kwargs @198-204 emits the 7 config-derived kwargs; @205 merges _FIXED_KWARGS (12).
#   (b) _FIXED_KWARGS @106 silero_backend='auto'; silero_use_onnx only @41 docstring.
#   (c) _FIXED_KWARGS @111 no_log_file=True.
#   (d) _FIXED_KWARGS @109-110 both ensure_sentence_* False.
#   (e) _filter_kwargs_to_signature @253-283 (VAR_KEYWORD→all; strict-drop+WARNING).
#   (f) _build_callbacks @246-249 wires the 4 callbacks; _construct @312 merges them.
```

### Level 2: The LIVE RealtimeSTT signature probe (PRD §8 API-drift check — clause e)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -c "import inspect; from RealtimeSTT import AudioToTextRecorder; p=inspect.signature(AudioToTextRecorder.__init__).parameters; need=['model','realtime_model_type','language','device','compute_type','enable_realtime_transcription','realtime_processing_pause','use_main_model_for_realtime','post_speech_silence_duration','min_length_of_recording','min_gap_between_recordings','silero_sensitivity','webrtc_sensitivity','silero_backend','spinner','use_microphone','ensure_sentence_starting_uppercase','ensure_sentence_ends_with_period','no_log_file','on_realtime_transcription_stabilized','on_vad_detect_start','on_vad_start','on_vad_stop']; print('params(excl self):', len(p)-1); print('VAR_KEYWORD:', any(v.kind==inspect.Parameter.VAR_KEYWORD for v in p.values())); print('MISSING:', [k for k in need if k not in p])"
# Expected: params(excl self): 84 | VAR_KEYWORD: False | MISSING: []
#   → all 23 kwargs accepted; _filter_kwargs_to_signature drops NOTHING on the current install.
# On a NON-empty MISSING: it indicates a RealtimeSTT API drift (a kwarg renamed/dropped). That is the
#   one case where a REAL defect surfaces — record it + the fix (rename the kwarg / drop it) in the
#   report. (None expected on the current install.)
```

### Level 3: Run the contract construction slice (the acceptance gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or filter_keeps or filter_drops or filter_accepts or construct or build_recorder"
# Expected: 32 passed, 161 deselected in ~0.04s. (The 12 clause-specific tests: test_cfg_to_kwargs_
#   keys_are_exactly_the_non_callback_set / _silero_correction / _no_log_file_suppresses_realtimesst_log /
#   _textproc_owns_cleanup / _passes_through_config_values / _calls_resolve_with_cfg_defaults;
#   test_filter_keeps_kwargs_in_signature / _drops_unknown_kwargs / _accepts_all_when_var_keyword;
#   test_construct_callbacks_are_live / _drops_kwargs_not_in_strict_recorder / _wires_on_speech_into_partial_callback.)
# On a real FAILURE: it would indicate a regression in the kwargs builder/filter/wiring — debug the root
#   cause (do NOT weaken the assertion); record the defect + fix in the report. (None expected.)
```

### Level 4: Transcribe the report + scope guard

```bash
cd /home/dustin/projects/voice-typing
# CREATE plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md (mirror gap_lifecycle.md; standalone NEW file).
ls -la plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md   # exists
head -1 plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md   # → "# Gap Report — P1.M2.T4.S1: Recorder Kwargs Construction vs PRD §4.4"
git status --short
# Expected: ONLY `?? plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md` (new). No voice_typing/*,
#   no tests/*, no PRD.md/tasks.json/prd_snapshot.md/.gitignore change.
```

### Level 5: Report completeness check (the deliverable quality gate)

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md
grep -qE '^# Gap Report — P1.M2.T4.S1: Recorder Kwargs Construction' "$F" && echo "title OK"
grep -qE 'Bottom line.*COMPLIANT|✅' "$F" && echo "verdict OK"
grep -qE '32 passed' "$F" && echo "test evidence OK"
grep -qE 'MISSING.*\[\]|VAR_KEYWORD' "$F" && echo "signature probe OK"
grep -qE 'cfg_to_kwargs|_filter_kwargs_to_signature|_build_callbacks|_FIXED_KWARGS' "$F" && echo "file:line evidence OK"
grep -qiE 'nuance|non-defect' "$F" && echo "nuances section OK"
# Expected: all 6 checks pass → the report has title + verdict + test count + probe + file:line + nuances.
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1: all 6 clauses' file:line present in the live source and read as documented (research §0).
- [ ] Level 2: the live signature probe reports `84 params, VAR_KEYWORD: False, MISSING: []` (recorded in the report §5).
- [ ] Level 3: `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs or
      filter_keeps or filter_drops or filter_accepts or construct or build_recorder"` → `32 passed, 161
      deselected` (recorded in the report §3).
- [ ] Level 4: `architecture/gap_recorder_kwargs.md` created; `git status --short` == the new report only.
- [ ] Level 5: report has title + ✅ verdict + test count + probe result + file:line evidence + nuances.

### Feature (Audit) Validation
- [ ] (a) `cfg_to_kwargs` emits all 20 §4.4 kwargs (7 config-derived + 12 fixed + the partial-callback attr).
- [ ] (b) `silero_backend="auto"` + legacy `silero_use_onnx` absent.
- [ ] (c) `no_log_file=True`.
- [ ] (d) both `ensure_sentence_*` False (textproc owns casing).
- [ ] (e) `_filter_kwargs_to_signature` API-drift safety (strict-drop + WARNING + accept-all); live probe MISSING=[].
- [ ] (f) the 4 callbacks wired (on_realtime_transcription_stabilized→_partial; on_vad_detect_start/on_vad_start/on_vad_stop).
- [ ] Compliance table maps each clause to PRD §4.4 expected vs code actual (file:line) vs ✅.

### Code Quality / Scope Validation
- [ ] No source/test files modified (no defect exists → no fix; the construction is compliant).
- [ ] gap_recorder_kwargs.md is a NEW standalone file (NOT appended to any existing gap report).
- [ ] Report follows the gap_*.md format (mirror gap_lifecycle.md).

### Forbidden-Operations Compliance
- [ ] `voice_typing/*` NOT modified. `tests/*` NOT modified.
- [ ] `PRD.md`, `**/tasks.json`, `**/prd_snapshot.md`, `.gitignore` NOT modified.
- [ ] `gap_lifecycle.md` (P1.M2.T2.x), `gap_lite.md` (P1.M2.T3.S1), `gap_cuda_check.md` (P1.M1.T4.S1) NOT modified.
- [ ] No new deps; no `pyproject.toml`/`uv.lock` change.

---

## Anti-Patterns to Avoid

- ❌ Don't invent defects to look thorough — the kwargs construction is COMPLIANT (pre-verified). If the 6
  clauses pass + the live probe reports MISSING=[] + the 32 tests pass, the verdict is ✅ and NO
  source/test files change. Record nuances, not phantom gaps.
- ❌ Don't flag `compute_type`'s absence from `config.py` as a gap — it is DERIVED in `_resolve_device_config`
  (a cuda_check concern; PRD §4.5 has no compute_type key) (CRITICAL #3 / nuance §4.1).
- ❌ Don't flag the 4 callbacks' absence from `_FIXED_KWARGS`/`cfg_to_kwargs` as a gap — they are wired in
  `_build_callbacks` (they need the Feedback instance; correct layering) (CRITICAL #4 / nuance §4.2).
- ❌ Don't flag `silero_use_onnx` @41 as a stale live reference — it is a docstring INSTRUCTION to drop the
  legacy control; it is not a kwarg (negative test @262 guards its absence) (CRITICAL #5 / nuance §4.3).
- ❌ Don't flag "_filter drops nothing on the current install" as a gap — the filter is forward-looking
  API-drift defense (PRD §8); both code paths are unit-tested with fakes (CRITICAL #6 / nuance §4.5).
- ❌ Don't append to `gap_lifecycle.md`/`gap_cuda_check.md`/`gap_lite.md` — recorder kwargs is its own audit
  area; create a NEW `gap_recorder_kwargs.md` (CRITICAL #7).
- ❌ Don't use bare `python`/`pytest` (zsh aliases) or `-k filter_kwargs` (matches NONE of the 3 filter
  tests — use the exact `filter_keeps/filter_drops/filter_accepts` tokens) (CRITICAL #1/#2).
- ❌ Don't modify `voice_typing/*`, `tests/*`, `PRD.md`, `tasks.json`, any sibling gap report, or run the
  daemon/recorder in the foreground (this audit is read-only introspection + mocked tests).

---

## Confidence Score

**9.5/10** for one-pass success. This is a re-verification audit with every fact pre-verified against the
live tree: the 6-clause compliance table with exact file:line (research §0), the construction call chain
(§1), the **live RealtimeSTT signature probe** (84 params, no `**kwargs`, MISSING=[] — re-ran), the
verified test baseline (`32 passed, 161 deselected in 0.04s` — re-ran live), the gap_*.md report format
to mirror, and the 6 non-defect nuances documented so they are not mistaken for gaps. Residual risk
(−0.5): a RealtimeSTT upgrade between this PRP's research and implementation could rename a kwarg → the
live probe (Level 2) would then report a non-empty MISSING, surfacing a REAL defect the agent must fix +
record (the one sanctioned code-change path); otherwise the report always reflects the live tree.