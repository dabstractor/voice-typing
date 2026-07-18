# PRP — P1.M2.T3.S1: Audit lite recorder construction — single model, silence gate override

## Goal

**Feature Goal**: Produce the authoritative **lite recorder construction audit** as a new report
`plan/006_862ee9d6ef41/architecture/gap_lite.md`, cross-checking the lite-mode recorder build path
(`daemon.cfg_to_kwargs(lite=True)` → `build_recorder(lite=True)` ← `recorder_host._worker_main(mode="lite")`
← `daemon._load_host("lite")`) against **PRD §4.2ter + §4.4** on the **4 item clauses (a)-(d)**. This is
a **verification/audit** subtask of compliance round `006_862ee9d6ef41`: the deliverable is the report;
**code changes happen ONLY if a real defect is found — none is expected; this PRP's author has already
performed the audit and the lite construction is PRD §4.2ter/§4.4-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the lite recorder construction is COMPLIANT — no fix needed.**
> All 4 clauses (a)-(d) pass (file:line in the research note §0); the contract's run target
> `tests/test_recorder_host.py tests/test_daemon.py -q -k lite` = **15 passed, 204 deselected in 0.03s**
> (re-ran live). Lite loads ONLY `cfg.asr.lite_model` ("small.en") for BOTH realtime + final
> (`use_main_model_for_realtime=True` — the large `distil-large-v3` never constructs), uses its own snugger
> `post_speech_silence_duration` (`lite_post_speech_silence_duration`, 0.5 vs 0.6 — the perceived-latency
> lever), and the CPU lite substitute is `tiny.en` in BOTH the load path (`cfg_to_kwargs`) and the status
> path (`_child_resolved_device`).

**Deliverable** (ONE report file; NO source edits, NO test edits unless a real defect surfaces):
`plan/006_862ee9d6ef41/architecture/gap_lite.md` — a **NEW standalone file** (does not exist yet; siblings:
`gap_config.md`/`gap_textproc.md`/`gap_typing.md`/`gap_cuda_check.md`/`gap_daemon_loop.md`/
`gap_lifecycle.md`). Format mirrors `gap_lifecycle.md`: title + date + scope + audited artifacts
(file:line) + bottom-line verdict + §1 Method (grep + test commands) + §2 per-clause compliance table
(PRD expected vs code actual vs verdict) for (a)-(d) + §3 test evidence + §4 non-defect nuances +
conclusion tying the verdict to PRD §4.2ter/§4.4 + acceptance #10. **This PRP's author has already
performed the audit** (findings in the research note) — the implementing agent re-verifies, re-runs the
tests, and transcribes the report.

**Success Definition**:
- (a) `architecture/gap_lite.md` exists with the title `# Gap Report — P1.M2.T3.S1: Lite Recorder
  Construction vs PRD §4.2ter` and the 6 sub-parts (scope/artifacts, bottom line, §1 method, §2
  compliance table, §3 test evidence, §4 nuances, conclusion).
- (b) The recorded findings match the live re-verification: all 4 clauses (a)-(d) are **compliant**,
  each with `voice_typing/daemon.py` / `recorder_host.py` / `config.py` file:line.
- (c) `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite`
  → all pass (record the count; verified baseline: **15 passed, 204 deselected in 0.03s**).
- (d) **No source or test files are modified** (because no defect exists — lite construction is
  PRD-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and
  record the fix; otherwise record "none — compliant per audit."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lite.md` (new) — no
  `voice_typing/*`, no `tests/*`, no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore` change.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that lite mode (a) loads EXACTLY
ONE model (`lite_model`) so the large `distil-large-v3` never consumes VRAM (the ~half-VRAM acceptance
#10 guarantee), (b) actually FEELS faster because the silence gate is shortened (not just because the
small model transcribes faster — the §4.2ter latency-log finding), and (c) degrades correctly to `tiny.en`
on CPU. Also the downstream **P1.M5.T5** acceptance-criteria cross-check (maps acceptance #10 — "lite
arms using ONLY `lite_model`; its own shorter `post_speech_silence_duration`; observably snappier" — to
this audit's evidence).

**Use Case**: A future change to `cfg_to_kwargs`'s lite branch, to the `_worker_main` `lite = mode ==
"lite"` derivation, to `_child_resolved_device`'s lite CPU fallback, or to the `lite_post_speech_silence_
duration` default. The audit + the 4 lite kwargs tests are the reference that proves the change keeps (or
breaks) the one-model + snugger-silence contract.

**Pain Points Addressed**: Closes the "does lite REALLY load only one model, REALLY shorten the silence
gate, REALLY keep the one-model flag on CPU fallback, and is the mode REALLY threaded end-to-end from
`_load_host` into the child?" question with recorded, re-runnable evidence — not an assumption.

## Why

- **One-model is the load-bearing lite invariant (acceptance #10).** PRD §4.2ter + acceptance #10 require
  lite to arm "using ONLY `lite_model` (the large model never loads — verified ~half the VRAM)." The
  mechanism is `use_main_model_for_realtime=True` + `model=realtime_model_type=lite_model`, which verified
  against RealtimeSTT v1.0.2 to early-return out of `_initialize_realtime_transcription_model` so the
  separate realtime engine never spins up. The audit certifies `cfg_to_kwargs(lite=True)` sets all three.
  A future RealtimeSTT upgrade that regresses the early-return would silently load two models — this audit
  + the `test_cfg_to_kwargs_lite_*` tests fail loudly. (PRD §4.2ter "Recorder construction (lite)"; §7 #10.)
- **The silence gate, not the model, is the perceived-latency lever.** PRD §4.2ter's latency-log finding:
  the small model's ~50 ms final-pass win is swamped by the silence wait unless lite overrides
  `post_speech_silence_duration`. Lite MUST use its own snugger threshold (`lite_post_speech_silence_
  duration`, default 0.5 vs 0.6) to actually feel faster. The audit certifies `cfg_to_kwargs(lite=True)`
  overrides it. (PRD §4.2ter "The silence gate… is the perceived-latency bottleneck"; §4.4 lite note.)
- **CPU fallback must keep lite single-model + tiny.en.** The degraded lite substitute is `tiny.en`
  (mirrors how normal CPU-fallback maps `small.en`→`tiny.en`). The audit certifies the CPU fallback is
  applied consistently in BOTH the load path (`cfg_to_kwargs`) and the status path
  (`_child_resolved_device`) — so `voicectl status` reports what actually loaded. (PRD §4.2ter + §4.4
  "If CUDA init fails entirely…".)
- **Scope discipline.** This subtask owns the lite CONSTRUCTION kwargs + the mode→lite threading ONLY.
  The mode-switch RELOAD mechanic (`_load_host` `switch_mode` branch) is **P1.M2.T3.S2**; the T7 live
  test COVERAGE audit is **P1.M2.T3.S3**; the FULL common recorder kwargs (all §4.4 params, silero_backend,
  no_log_file, kwarg filtering) is **P1.M2.T4.S1**. THIS task audits the LITE DELTA (the 4 fields lite
  changes) + the end-to-end mode threading; it REFERENCES but does not re-audit the siblings' scopes.

## What

Re-verify the lite recorder construction against PRD §4.2ter + §4.4 by reading the cited code regions
(`daemon.cfg_to_kwargs` @158-216, `_construct` @285-311, `build_recorder` @323-345, `_load_host` @698-795,
`start_lite` @1376 / `toggle_lite` @1426; `recorder_host._worker_main` @421-510 esp. 456-498,
`_child_resolved_device` @680-715, `RecorderHost.mode` @168 + `spawn` @181-228; `config.py` `lite_model`
@54 + `lite_post_speech_silence_duration` @59), re-running the contract's `-k lite` slice, and creating
`architecture/gap_lite.md` in the `gap_*.md` format (mirror `gap_lifecycle.md`). The audit is expected to
confirm full compliance (no defects → no code changes). The report's compliance table maps each clause
(a)-(d) to PRD §4.2ter/§4.4 expected behavior vs the code's actual behavior (file:line).

### Success Criteria

- [ ] `architecture/gap_lite.md` exists with the `# Gap Report — P1.M2.T3.S1: Lite Recorder Construction
  vs PRD §4.2ter` title + the 6 sub-parts.
- [ ] Compliance table covers (a) `_load_host("lite")`→`lite=True` end-to-end; (b) `model`=
  `realtime_model_type`=`lite_model` + `use_main_model_for_realtime=True`; (c) `post_speech_silence_
  duration`=`lite_post_speech_silence_duration`; (d) `_child_resolved_device` lite CPU fallback (tiny.en) —
  each COMPLIANT with file:line.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite`
  → recorded pass count (baseline **15 passed, 204 deselected**).
- [ ] No source/test files modified (`git status --short` == the new `gap_lite.md` only).
- [ ] Conclusion ties the verdict to PRD §4.2ter/§4.4 + acceptance #10 (one-model ~half VRAM; own snugger
  silence gate; CPU tiny.en).

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §0: every clause mapped to
`daemon.py`/`recorder_host.py`/`config.py` file:line with the COMPLIANT verdict + the 15-test evidence +
the full mode→lite call chain §1 + the two-site CPU-fallback rationale §2 + the 4 non-defect nuances §4).
A developer new to this repo can re-verify from the research note + the cited code regions: the exact
line ranges, the grep commands to re-locate them, the test command, and the `gap_*.md` format (sibling
`gap_lifecycle.md`). The non-defect nuances (model identity lives in cfg_to_kwargs not _worker_main;
test_recorder_host has no lite tests; two-site lite-CPU-fallback; lite is spawn-time) are documented so
they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + test evidence + call chain)
- docfile: plan/006_862ee9d6ef41/P1M2T3S1/research/lite_construction_audit.md
  why: "§0 ★ THE 4-CLAUSE TABLE (each clause → daemon.py/recorder_host.py/config.py file:line + ✅ COMPLIANT).
        §1 the full mode→lite call chain (_load_host→RecorderHost→_worker_main→build_recorder→cfg_to_kwargs).
        §2 the two-site lite-CPU-fallback (cfg_to_kwargs LOAD path + _child_resolved_device STATUS path —
        intentional duplication). §3 the test evidence (15 passed -k lite; the 4 named lite kwargs tests).
        §4 the 4 non-defect nuances (model identity in cfg_to_kwargs not _worker_main; test_recorder_host
        has 0 lite tests; two-site duplication; lite is spawn-time). §5 the gap_lite.md structure. §6 scope
        boundaries (disjoint from S2/S3/T4.S1/P1.M2.T2.S4)."
  section: "ALL load-bearing. §0 (the table), §1 (the chain), §3 (the count), §5 (the report format)."

# MUST READ — the gap_*.md report format to mirror (structure + voice + per-clause table convention).
- docfile: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "The canonical gap-report format: title + Date/Scope/Audited-artifacts(file:line) + 'Bottom line:'
        verdict + §1 Method (grep + test commands run) + §2 per-property compliance table (PRD expected vs
        code actual vs Verdict) + §3 test pass/fail count + §4 non-defect nuances + conclusion. gap_lite.md
        is a STANDALONE new file in the SAME directory (NOT appended to gap_lifecycle.md — lite is its own
        audit area, like gap_config.md/gap_textproc.md)."
  critical: "gap_lite.md is a NEW file, not a §N-append to gap_lifecycle.md. Mirror the FORMAT, not the
             append-to-existing pattern (that was P1.M2.T2.S1-S4's pattern for the lifecycle area)."

# MUST READ — the primary audited source (the lite kwargs + the load chain live here).
- file: voice_typing/daemon.py
  why: "cfg_to_kwargs @158-216 (lite branch @184-192 sets resolved final/realtime=lite_model; @200-204 maps
        to model/realtime_model_type kwargs; @206-213 lite override use_main_model_for_realtime=True + post_
        speech_silence_duration=lite_post_speech_silence_duration). _construct @285-311 (calls cfg_to_kwargs
        with lite=). build_recorder @323-345 (the production wrapper; lite= threaded). _load_host @698-795
        (mode param; @715-718 switch_mode; @751-757 RecorderHost(...,mode=mode); @752 self._mode=mode).
        start_lite @1376 / toggle_lite @1426 (call _load_host('lite')). _FIXED_KWARGS @98-119 (use_main_
        model_for_realtime=False @101 — the value the lite override flips)."
  pattern: "cfg_to_kwargs is the SINGLE source of truth for model identity + the silence gate; lite flips
            3 kwargs (model, realtime_model_type, use_main_model_for_realtime) + 1 timing (post_speech_
            silence_duration) off the common block."
  gotcha: "Model identity is set in cfg_to_kwargs (daemon.py), NOT in _worker_main (recorder_host.py).
           _worker_main calls build_recorder(lite=lite)→cfg_to_kwargs(lite=True). Correct layering — do NOT
           flag the absence of a model= assignment in _worker_main as a gap (nuance §4.1)."

# MUST READ — the child half of the chain + the lite CPU-fallback status path.
- file: voice_typing/recorder_host.py
  why: "_worker_main @421-510 (mode param @425; @458 'lite = mode == \"lite\"'; @476 build_recorder(…,lite=
        lite); @481-494 the force_cpu RETRY PRESERVES lite — re-calls build_recorder(force_cpu=True,lite=
        lite)). _child_resolved_device @680-715 (@707-714 the lite CPU-fallback: tiny.en if device==cpu else
        cfg.asr.lite_model; sets d['final_model']/d['realtime_model']). RecorderHost.mode property @168 +
        spawn @181-228 (@194-196 ctx.Process(target=_worker_main,args=(…,self._mode)) — mode is the 6th arg)."
  pattern: "The child is a thin pass-through to daemon.build_recorder; the only lite LOGIC in the child is
            the one-line `lite = mode == 'lite'` derivation + the status-path CPU fallback."
  gotcha: "tests/test_recorder_host.py has ZERO lite tests (grep -c -i lite = 0). Not a gap — lite
           construction is unit-tested at the cfg_to_kwargs layer (test_daemon.py) + the child adds no
           model logic of its own (nuance §4.2). The child's _worker_main→build_recorder wiring is verified
           by reading + the live test_idle_and_gpu.sh T7."

# MUST READ — the lite config fields + their defaults.
- file: voice_typing/config.py
  why: "AsrConfig.lite_model: str = 'small.en' @54 (the single lite model). post_speech_silence_duration:
        float = 0.6 @58 (normal). lite_post_speech_silence_duration: float = 0.5 @59 (the snugger lite
        threshold — the perceived-latency lever). Both are real config keys (§4.5); the loader rejects
        unknown keys, so they must exist (they do)."
  gotcha: "The 0.5 default is what makes lite 'observably snappier' (acceptance #10); test_cfg_to_kwargs_
           lite_uses_shorter_silence_duration pins lite=0.5/normal=0.6 + confirms it's tunable (0.3)."

# MUST READ — the test file with the lite kwargs assertions (the 4 clause-specific tests live here).
- file: tests/test_daemon.py
  why: "test_cfg_to_kwargs_lite_mode_uses_one_model @138 (clause b: model=realtime_model_type=small.en +
        use_main_model_for_realtime=True; normal=distil-large-v3+False). test_cfg_to_kwargs_lite_cpu_
        fallback_uses_tiny_en @165 (clause d: CPU→tiny.en; one-model flag stays True). test_cfg_to_kwargs_
        lite_keeps_all_other_kwargs_equal @185 (isolation: ONLY the 4 lite fields differ).
        test_cfg_to_kwargs_lite_uses_shorter_silence_duration @216 (clause c: lite=0.5/normal=0.6/tunable)."
  critical: "The contract run target is `-k lite` which selects 15 (matches param ids lite_model/lite_post_
             speech_silence_duration too). Record '15 passed, 204 deselected' as the baseline; the 4 named
             tests above are the clause-specific assertions."

# CONTEXT — the PRD spec being audited against.
- docfile: PRD.md   # §4.2ter + §4.4 lite note + §7 acceptance #10
  why: "§4.2ter 'Recorder construction (lite)': model=lite_model, realtime_model_type=lite_model,
        use_main_model_for_realtime=True (one model; large never constructs); the silence-gate latency
        finding (lite MUST shorten post_speech_silence_duration). §4.4 lite note (same three kwargs + the
        snugger silence gate). §7 #10 (lite arms using ONLY lite_model; ~half VRAM; own shorter silence
        gate → observably snappier). Match these against the code in the compliance table."

# CONTEXT — the parallel task (DISJOINT file + topic — no conflict).
- docfile: plan/006_862ee9d6ef41/P1M2T2S4/PRP.md
  why: "P1.M2.T2.S4 appends a §4 section to gap_lifecycle.md about the idle AUTO-STOP watchdog (§4.5
        auto_stop_idle_seconds). DISJOINT topic (auto-stop vs lite construction) + DISJOINT file (it edits
        gap_lifecycle.md; this task CREATES gap_lite.md). No overlap."
```

### Current Codebase tree (relevant slice — audit reads these; writes ONLY gap_lite.md)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py          # READ: cfg_to_kwargs @158-216, _construct @285, build_recorder @323,
│   │                      #       _load_host @698-795, start_lite @1376, toggle_lite @1426, _FIXED_KWARGS @98
│   ├── recorder_host.py   # READ: _worker_main @421-510, _child_resolved_device @680-715, mode @168, spawn @181
│   └── config.py          # READ: lite_model @54, lite_post_speech_silence_duration @59, post_speech_silence @58
├── tests/
│   ├── test_daemon.py     # RUN: -k lite (the 4 lite kwargs tests + param-id matches = 15)
│   └── test_recorder_host.py  # RUN: -k lite (0 lite tests — all deselected; recorded as a nuance)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_lifecycle.md   # READ: the format to mirror
    └── gap_lite.md        # CREATE (new) — the deliverable
```

### Desired Codebase tree (what this task produces)

```bash
plan/006_862ee9d6ef41/architecture/gap_lite.md   # NEW — the lite construction audit report
# No source/test changes. git status --short == this one new file.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — FULL PATHS in every bash command (zsh aliases python3→uv run). Use .venv/bin/python,
#   NEVER bare python/pytest. The unit tests are mocked-CUDA (no real models) → ~0.03s; wrap in
#   `timeout 300` as the sibling gap reports do.

# CRITICAL #2 — Model identity is set in daemon.cfg_to_kwargs (daemon.py:184-204), NOT in
#   recorder_host._worker_main. _worker_main calls build_recorder(lite=lite)→cfg_to_kwargs(lite=True).
#   Do NOT flag the absence of a `model=` assignment in _worker_main as a gap — it is correct layering
#   (cfg_to_kwargs is the single source of truth; the child is a pass-through). (Nuance §4.1.)

# CRITICAL #3 — tests/test_recorder_host.py has ZERO lite tests (grep -c -i lite = 0). This is NOT a
#   coverage gap: lite construction is unit-tested at the cfg_to_kwargs layer (test_daemon.py, 4 tests)
#   + the child adds no model logic of its own (the one-line `lite = mode=="lite"` derivation @458 is
#   verified by reading) + the live test_idle_and_gpu.sh T7 + test_feed_audio.py lite tests exercise the
#   real child. Record it as a nuance, not a defect. (Nuance §4.2.)

# CRITICAL #4 — Two-site lite-CPU-fallback (tiny.en): daemon.cfg_to_kwargs:184-192 (LOAD path — what the
#   recorder constructs) AND recorder_host._child_resolved_device:707-714 (STATUS path — what voicectl
#   status reports). Both MUST agree; both discriminate on device=="cpu". Intentional duplication, NOT a
#   defect. (Nuance §4.3 / research §2.)

# CRITICAL #5 — gap_lite.md is a NEW STANDALONE file (like gap_config.md/gap_textproc.md), NOT a §N-append
#   to gap_lifecycle.md. Mirror gap_lifecycle.md's FORMAT, not the append-to-existing pattern.

# CRITICAL #6 — lite is a SPAWN-TIME property (recorder_host.py:456-458). The mode-switch RELOAD mechanic
#   (_load_host switch_mode branch @715-741) is P1.M2.T3.S2's scope — THIS task references the mode
#   threading (clause a) but does NOT audit the reload logic itself. Stay in scope.

# CRITICAL #7 — This is a RE-VERIFICATION of an already-compliant feature. Do NOT invent defects to look
#   thorough: if the 4 clauses pass (they do), the verdict is ✅ COMPLIANT and NO source/test files change.
#   Code changes occur ONLY if re-verification surfaces a REAL defect (record it + the fix).
```

## Implementation Blueprint

### Data models and structure

None (audit only). The "data" is the 4-clause compliance table + file:line evidence transcribed into
`gap_lite.md`.

### Implementation Tasks (ordered by dependencies — a re-verify + transcribe runbook)

```yaml
Task 1: RE-VERIFY clause (a) — _load_host('lite') → lite=True end-to-end
  - READ daemon.py _load_host @698-795: confirm `mode` param @698; RecorderHost(..., mode=mode) @751-757;
    self._mode = mode @752; start_lite @1376 / toggle_lite @1426 call _load_host("lite").
  - READ recorder_host.py RecorderHost.mode @168 + spawn @181-228: confirm @194-196 ctx.Process(target=
    _worker_main, args=(..., self._mode)) threads mode as the 6th arg.
  - READ recorder_host.py _worker_main @421-510: confirm @425 mode param; @458 `lite = mode == "lite"`;
    @476 build_recorder(..., lite=lite); @481-494 the force_cpu RETRY preserves lite.
  - READ daemon.py build_recorder @323-345 → _construct @285-311 → cfg_to_kwargs(cfg, resolved=, lite=) @311.
  - VERDICT: the chain is unbroken (research §1). Record file:line in gap_lite.md §2 row (a).

Task 2: RE-VERIFY clause (b) — one-model kwargs (model=realtime_model_type=lite_model + flag=True)
  - READ daemon.py cfg_to_kwargs @158-216: @184-192 lite branch sets resolved final/realtime=lite_model;
    @200-204 kwargs "model":resolved["final_model"], "realtime_model_type":resolved["realtime_model"]
    (both small.en on CUDA); @206-209 kwargs["use_main_model_for_realtime"]=True (overrides _FIXED_KWARGS
    False @101). config.py AsrConfig.lite_model="small.en" @54.
  - RUN test: test_cfg_to_kwargs_lite_mode_uses_one_model @138 (asserts all three).
  - VERDICT: compliant (research §0 row b). Record file:line in §2 row (b).

Task 3: RE-VERIFY clause (c) — post_speech_silence_duration override
  - READ daemon.py cfg_to_kwargs @203 (common block cfg.asr.post_speech_silence_duration, 0.6) + @206-213
    (lite override cfg.asr.lite_post_speech_silence_duration, 0.5). config.py @58 (0.6) + @59 (0.5).
  - RUN test: test_cfg_to_kwargs_lite_uses_shorter_silence_duration @216 (lite=0.5, normal=0.6, tunable 0.3).
  - VERDICT: compliant (research §0 row c). Record file:line in §2 row (c).

Task 4: RE-VERIFY clause (d) — _child_resolved_device lite CPU fallback (tiny.en) [BOTH sites]
  - READ recorder_host.py _child_resolved_device @680-715: @707-714 `if lite: lite_model="tiny.en" if
    d["device"]=="cpu" else cfg.asr.lite_model; d["final_model"]=d["realtime_model"]=lite_model`.
  - READ daemon.py cfg_to_kwargs @184-192 (the LOAD-path twin: "tiny.en" if resolved["device"]=="cpu").
    Confirm both sites agree (research §2 — intentional two-site duplication).
  - RUN test: test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en @165 (CPU→tiny.en; flag stays True).
  - VERDICT: compliant (research §0 row d). Record BOTH file:line sites in §2 row (d) + nuance §4.3.

Task 5: RUN the contract test target + record the count
  - CMD: timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite
  - EXPECTED: 15 passed, 204 deselected in ~0.03s (baseline; research §3). Record in gap_lite.md §3 +
    note test_recorder_host.py contributed 0 (all 15 from test_daemon.py).

Task 6: CREATE plan/006_862ee9d6ef41/architecture/gap_lite.md (mirror gap_lifecycle.md format)
  - TITLE: "# Gap Report — P1.M2.T3.S1: Lite Recorder Construction vs PRD §4.2ter"
  - Date + Scope (the 4 clauses) + Audited artifacts (file:line list from Tasks 1-4).
  - "Bottom line:" ✅ COMPLIANT (all 4 clauses) + the test count.
  - §1 Method: the grep commands + the test command (Task 5).
  - §2 per-clause compliance table (research §0): PRD §4.2ter/§4.4 expected | code actual (file:line) | ✅.
  - §3 test evidence (15 passed, 204 deselected; the 4 named tests + their clauses).
  - §4 non-defect nuances (research §4): (1) model identity in cfg_to_kwargs not _worker_main;
    (2) test_recorder_host has 0 lite tests; (3) two-site lite-CPU-fallback; (4) lite is spawn-time.
  - Conclusion: ties verdict to PRD §4.2ter/§4.4 + acceptance #10 (one-model ~half VRAM; own snugger
    silence gate → observably snappier; CPU tiny.en).

Task 7: SCOPE GUARD — verify no source/test files changed
  - CMD: git status --short
  - EXPECTED: ONLY `plan/006_862ee9d6ef41/architecture/gap_lite.md` (new). No voice_typing/*, no tests/*,
    no PRD.md/tasks.json/prd_snapshot.md/.gitignore. (If a real defect was found + fixed in Task X, that
    source change is ALSO expected — record it in the report; otherwise none.)
```

### Implementation Patterns & Key Details

```bash
# PATTERN — a re-verification audit: read the cited lines, run the -k lite slice, transcribe the report.

# 1. Re-locate every lite site (the grep the gap report's §1 will cite):
grep -nE 'def cfg_to_kwargs|def _construct|def build_recorder|def _load_host|def start_lite|def toggle_lite|lite|use_main_model_for_realtime|post_speech_silence_duration' voice_typing/daemon.py
grep -nE 'def _worker_main|def _child_resolved_device|lite = mode|lite=lite|tiny\.en|def mode|target=_worker_main' voice_typing/recorder_host.py
grep -nE 'lite_model|lite_post_speech_silence_duration|post_speech_silence_duration' voice_typing/config.py

# 2. Re-run the contract target (record the count for §3):
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite
#   → 15 passed, 204 deselected in 0.03s (test_recorder_host contributes 0; all 15 are test_daemon.py).

# 3. Create the report (mirror gap_lifecycle.md; standalone NEW file, NOT a §N-append):
#    plan/006_862ee9d6ef41/architecture/gap_lite.md

# 4. Scope guard:
git status --short   # → ONLY the new gap_lite.md (no voice_typing/*, no tests/*, no PRD/tasks.json).
```

### Integration Points

```yaml
CONSUMED (read-only — verify, don't change):
  - voice_typing/daemon.py: cfg_to_kwargs @158-216 (the lite delta), _construct @285-311, build_recorder
    @323-345, _load_host @698-795 (mode threading), start_lite @1376 / toggle_lite @1426.
  - voice_typing/recorder_host.py: _worker_main @421-510, _child_resolved_device @680-715, RecorderHost
    mode @168 + spawn @181-228.
  - voice_typing/config.py: AsrConfig.lite_model @54, lite_post_speech_silence_duration @59.
  - tests/test_daemon.py: the 4 lite kwargs tests (@138/@165/@185/@216) + param-id matches.
PRODUCED (this task):
  - plan/006_862ee9d6ef41/architecture/gap_lite.md (NEW) — the lite construction audit.
DOWNSTREAM CONSUMERS:
  - P1.M2.T3.S2 (mode-switch reload audit): references this audit's mode-threading (clause a) finding.
  - P1.M2.T3.S3 (T7 coverage audit): references this audit's "test_recorder_host has 0 lite tests" nuance.
  - P1.M5.T5 (acceptance cross-check): maps acceptance #10 to this audit's one-model + snugger-silence evidence.
DO NOT TOUCH:
  - voice_typing/* (no defect exists), tests/*, PRD.md, **/tasks.json, **/prd_snapshot.md, .gitignore,
    pyproject.toml, uv.lock. No new deps. gap_lifecycle.md is owned by P1.M2.T2.S1-S4 (do NOT append to it).
```

## Validation Loop

> Full paths in every command (CRITICAL #1). The unit tests are mocked-CUDA (~0.03s); wrap in `timeout 300`.

### Level 1: Re-verify the 4 clauses against the live source (read the cited lines)

```bash
cd /home/dustin/projects/voice-typing
grep -nE 'def cfg_to_kwargs|def _construct|def build_recorder|def _load_host|def start_lite|def toggle_lite|lite|use_main_model_for_realtime|post_speech_silence_duration|self\._mode' voice_typing/daemon.py | sed -n '1,60p'
grep -nE 'def _worker_main|def _child_resolved_device|lite = mode|lite=lite|tiny\.en|def mode|target=_worker_main|self\._mode' voice_typing/recorder_host.py
grep -nE 'lite_model|lite_post_speech_silence_duration|post_speech_silence_duration' voice_typing/config.py
# Expected: each clause's file:line from the research note §0 is present and reads as documented.
#   (a) _load_host("lite") → RecorderHost(mode=) → _worker_main(mode=) → lite=True → build_recorder(lite=).
#   (b) cfg_to_kwargs: model=realtime_model_type=lite_model + use_main_model_for_realtime=True.
#   (c) cfg_to_kwargs: post_speech_silence_duration=lite_post_speech_silence_duration (0.5).
#   (d) _child_resolved_device + cfg_to_kwargs: tiny.en on CPU lite fallback (two sites).
```

### Level 2: Run the contract test target (the acceptance gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite
# Expected: 15 passed, 204 deselected in ~0.03s. (test_recorder_host.py contributes 0 lite tests — a
#   nuance, not a gap. The 4 named clause-specific tests: test_cfg_to_kwargs_lite_mode_uses_one_model,
#   _lite_cpu_fallback_uses_tiny_en, _lite_keeps_all_other_kwargs_equal, _lite_uses_shorter_silence_duration.)
# On a real FAILURE: it would indicate a regression in the lite kwargs builder — debug the root cause
#   (do NOT weaken the assertion); record the defect + fix in gap_lite.md. (None expected.)
```

### Level 3: Transcribe the report + scope guard

```bash
cd /home/dustin/projects/voice-typing
# CREATE plan/006_862ee9d6ef41/architecture/gap_lite.md (mirror gap_lifecycle.md; standalone NEW file).
ls -la plan/006_862ee9d6ef41/architecture/gap_lite.md   # exists
head -1 plan/006_862ee9d6ef41/architecture/gap_lite.md   # → "# Gap Report — P1.M2.T3.S1: Lite Recorder Construction vs PRD §4.2ter"
git status --short
# Expected: ONLY `?? plan/006_862ee9d6ef41/architecture/gap_lite.md` (new). No voice_typing/*, no tests/*,
#   no PRD.md/tasks.json/prd_snapshot.md/.gitignore change.
```

### Level 4: Report completeness check (the deliverable quality gate)

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
grep -qE '^# Gap Report — P1.M2.T3.S1: Lite Recorder Construction' "$F" && echo "title OK"
grep -qE 'Bottom line.*COMPLIANT|✅' "$F" && echo "verdict OK"
grep -qE '15 passed' "$F" && echo "test evidence OK"
grep -qE 'cfg_to_kwargs|_child_resolved_device|_worker_main|_load_host' "$F" && echo "file:line evidence OK"
grep -qiE 'nuance|non-defect' "$F" && echo "nuances section OK"
# Expected: all 5 checks pass → the report has title + verdict + test count + file:line evidence + nuances.
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1: all 4 clauses' file:line present in the live source and read as documented (research §0).
- [ ] Level 2: `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite`
      → `15 passed, 204 deselected` (recorded in the report).
- [ ] Level 3: `architecture/gap_lite.md` created; `git status --short` == the new report only.
- [ ] Level 4: report has title + ✅ verdict + test count + file:line evidence + nuances section.

### Feature (Audit) Validation
- [ ] (a) `_load_host("lite")`→`lite=True` chain verified end-to-end (daemon→RecorderHost→_worker_main→build_recorder).
- [ ] (b) `model`=`realtime_model_type`=`lite_model` + `use_main_model_for_realtime=True` (one-model).
- [ ] (c) `post_speech_silence_duration`=`lite_post_speech_silence_duration` (the snugger silence gate).
- [ ] (d) `_child_resolved_device` (+ `cfg_to_kwargs`) lite CPU fallback = tiny.en (both sites).
- [ ] Compliance table maps each clause to PRD §4.2ter/§4.4 expected vs code actual (file:line) vs ✅.

### Code Quality / Scope Validation
- [ ] No source/test files modified (no defect exists → no fix; the lite construction is compliant).
- [ ] gap_lite.md is a NEW standalone file (NOT appended to gap_lifecycle.md).
- [ ] Report follows the gap_*.md format (mirror gap_lifecycle.md).

### Forbidden-Operations Compliance
- [ ] `voice_typing/*` NOT modified. `tests/*` NOT modified.
- [ ] `PRD.md`, `**/tasks.json`, `**/prd_snapshot.md`, `.gitignore` NOT modified.
- [ ] `gap_lifecycle.md` NOT modified (owned by P1.M2.T2.S1-S4 — parallel/auto-stop audits).
- [ ] No new deps; no `pyproject.toml`/`uv.lock` change.

---

## Anti-Patterns to Avoid

- ❌ Don't invent defects to look thorough — the lite construction is COMPLIANT (pre-verified). If the 4
  clauses pass (they do) + the 15 tests pass, the verdict is ✅ and NO source/test files change. Record
  nuances, not phantom gaps.
- ❌ Don't flag the absence of a `model=` assignment in `_worker_main` as a gap — model identity lives in
  `cfg_to_kwargs` (the single source of truth); the child is a pass-through (CRITICAL #2 / nuance §4.1).
- ❌ Don't flag `test_recorder_host.py` having 0 lite tests as a coverage gap — lite construction is
  unit-tested at the cfg_to_kwargs layer + the child adds no model logic (CRITICAL #3 / nuance §4.2).
- ❌ Don't flag the two-site lite-CPU-fallback (cfg_to_kwargs + _child_resolved_device) as duplication to
  remove — it is intentional (load path + status path must agree) (CRITICAL #4 / nuance §4.3).
- ❌ Don't append to `gap_lifecycle.md` — lite construction is its own audit area; create a NEW
  `gap_lite.md` (CRITICAL #5).
- ❌ Don't audit the mode-switch RELOAD mechanic — that's P1.M2.T3.S2 (clause a references the mode
  threading only; the `switch_mode` branch is S2's scope) (CRITICAL #6).
- ❌ Don't use bare `python`/`pytest` (zsh aliases). Full paths: `.venv/bin/python`.
- ❌ Don't modify `gap_lifecycle.md` (parallel auto-stop audits own it), `PRD.md`, `tasks.json`, or any
  `voice_typing/*`/`tests/*` file.

---

## Confidence Score

**9.5/10** for one-pass success. This is a re-verification audit with every fact pre-verified against the
live tree: the 4-clause compliance table with exact file:line (research §0), the full mode→lite call chain
(§1), the verified test baseline (`15 passed, 204 deselected in 0.03s` — re-ran live), the gap_*.md report
format to mirror, and the 4 non-defect nuances documented so they are not mistaken for gaps. Residual risk
(−0.5): a future code shift between this PRP's research and implementation could move a line number — the
implementer re-runs the greps + the test, so the report always reflects the live tree (the line numbers
are re-derived, not copy-pasted).