# PRP — P1.M5.T2.S1: Audit T1 test coverage & verify test audio assets exist

## Goal

**Feature Goal**: Produce a **complete coverage + pass/fail report** for PRD §6 **T1 — the offline
feed_audio pipeline test** (`tests/test_feed_audio.py`), by (1) verifying the 4 test WAV assets
exist with the correct format + the toolchain that generates them, (2) statically auditing that the
test suite asserts **all five T1 criteria (a)–(e)** against the production recorder wiring, and
(3) executing the heavy real-model suite LIVE to record per-test pass/fail/skip. The report is the
**real-model evidence** for Acceptance #1 (transcription accuracy / WhisperX pause fix), the
real-model backstop for #2 (drain) and #5 (no hallucination), and the real-model T7 proof for #10
(lite mode).

**Verified baseline (LIVE this round — NO model load):**
- **All 4 WAVs present + correctly formatted** (`soxi`): utt_simple 3.44 s, utt_pause 7.92 s
  (incl. 3.0 s embedded silence), utt_multi 9.26 s (3 sentences + 2×1.5 s gaps), utt_punct 6.68 s —
  all 16 kHz mono 16-bit signed PCM. Toolchain present: espeak-ng 1.52.0 + sox 14.8.0.1 (+ ffmpeg optional).
- **`pytest --collect-only` = 9 tests** (the contract said "8"; the LIVE count is **9** because
  `test_fuzzy_accuracy` is parametrized into `[simple]` + `[punct]`). Collection is 0.01 s (lazy
  imports → no CUDA/torch at collection time).
- **Coverage is COMPLETE for T1(a)–(e)**: every criterion has a dedicated assertion. Two threshold
  nuances exist (see §What + research §3): (a) cadence gate is `max(gaps) < 0.8 s` vs PRD's "≥ every
  500 ms"; (e) latency gate is `<= 2.0 s` vs PRD's "≤1.5 s" (documented +0.5 s slack, CUDA-gated).
  Both are *more permissive* than the strict PRD number with documented rationale — neither is a gap.
- **`test_feed_audio_debug.py` does NOT exist as source** — only a stale `.pyc` in `__pycache__`
  (Jul 7). Finding to report (harmless; gitignored).

**Deliverable** (1 artifact — CREATE; **NO source/test edit** — this is a REPORT item):
- `plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md` — a self-contained report with: asset
  verification table, collected-count note (9, not 8), the T1(a)–(e) coverage matrix (with the 2
  threshold nuances flagged), the 3 beyond-T1 tests identified, the `test_feed_audio_debug` finding,
  and the LIVE per-test pass/fail/skip from the heavy run. No existing `test_results_t1.md`.

**Success Definition**:
- (a) The 4 WAV assets are re-verified LIVE (`soxi`/`ffprobe`) as 16 kHz mono 16-bit signed PCM;
  if any is missing, `./tests/make_test_audio.sh` is run to regenerate it (the contract authorizes
  this) and the regeneration is recorded.
- (b) The static coverage audit maps each T1(a)–(e) to its test function + exact assertion and
  records the 2 threshold nuances as "documented tolerances, not gaps."
- (c) The heavy suite is executed LIVE under AGENTS.md two-timeout discipline; per-test
  pass/fail/skip is recorded. Exit 124 (wedged) is diagnosed (single-test `-k -vv`), NOT retried blind.
- (d) `test_results_t1.md` is self-contained and records a clear VERDICT: "T1(a)–(e) coverage =
  COMPLETE; real-model run = <pass/fail counts>."
- (e) Scope respected: ONLY `test_feed_audio.py` is run; the mocked daemon/recorder_host set
  (P1.M5.T1.S2) and the pure-Python set (P1.M5.T1.S1) are NOT added.

## User Persona

**Target User**: Internal — the plan orchestrator + downstream leaves:
1. **P1.M5.T5.S1** (acceptance-criteria cross-check) consumes this report as the **real-model
   evidence** for Acceptance **#1** (WhisperX pause fix / transcription accuracy), the real-model
   backstop for **#2** (drain ≥3 s pause loses zero words) + **#5** (no hallucination on fed
   silence), and the real-model T7 proof for **#10** (lite mode).
2. **P1.M5.T1.S2** (mocked daemon/recorder_host tests, in parallel) covers the daemon *logic*
   green; THIS item adds the real-recorder + real-CUDA-models proof, so a transcription/pause
   failure here is cleanly attributable to the ASR integration rather than daemon lifecycle logic.
3. **Operators/reviewers** read `test_results_t1.md` as the signed-off evidence that the offline
   pipeline (feed_audio, no mic, no typing) actually transcribes the canonical synthetic utterances
   to ≥80% fuzzy accuracy with the WhisperX pause flaw demonstrably fixed.

**Use Case**: The compliance round (006) finished auditing every module (the `gap_*.md` reports).
P1.M5.T1.* converted the *unit* audits into "tests pass" (mocked + pure-Python). THIS item
converts the PRD §6 T1 spec into "the heavy real-model offline test passes + asserts every
criterion": it is the integration-grade gate that the synthetic espeak WAVs (a) get partials in
time, (b) survive the 3 s pause, (c) split into 3 finals, (d) hit ≥80% fuzzy, (e) finalize in
budget — against the REAL distil-large-v3 + small.en models.

**Pain Points Addressed**: (1) The unit tests prove lifecycle logic; this proves the *ASR* works.
(2) Catches a RealtimeSTT/model regression that unit tests can't (e.g. a feed_audio API change, a
silero VAD threshold drift, the WhisperX pause-merge flaw regressing). (3) Flags the 2 threshold
nuances so the acceptance cross-check sees them explicitly rather than discovering them later.

## Why

- **This is the ONLY real-model offline gate.** The mocked daemon tests (P1.M5.T1.S2) prove the
  lifecycle; the pure-Python tests (P1.M5.T1.S1) prove the deps. Neither loads a model or feeds
  audio. T1 (`test_feed_audio.py`) is the cheapest way to prove the REAL recorder transcribes
  correctly — minutes, one file, no mic, no typing.
- **It is the primary real-model evidence for 4 acceptance criteria** (#1, #2, #5, #10). The
  WhisperX pause fix (#1/#2), the no-hallucination-on-silence guard (#5), and lite mode (#10) are
  all exercised here against real models + real feed_audio.
- **It surfaces the 2 threshold nuances** (cadence 0.8 vs 0.5; latency 2.0 vs 1.5) as explicit
  findings — so the acceptance cross-check (P1.M5.T5.S1) can decide whether to tighten them, rather
  than treating the test as a black box.
- **The assets + coverage are already in place** (verified LIVE). So this item is low-risk:
  re-verify assets, run the suite, document. The value is the evidence artifact + the explicit
  coverage matrix + the threshold-nuance flags — not heroic debugging.

## What

Three phases, in order: **(1) re-verify assets + toolchain**, **(2) static coverage audit**, **(3)
LIVE heavy run + report**. Output = `test_results_t1.md`.

### Success Criteria

- [ ] All 4 WAVs re-verified LIVE as 16 kHz mono 16-bit signed PCM (`soxi` or `ffprobe`); any
      missing WAV regenerated via `./tests/make_test_audio.sh` and the regeneration recorded.
- [ ] espeak-ng + sox confirmed present (PRD §2 requires them; `make_test_audio.sh` `need`s them).
- [ ] T1(a)–(e) coverage matrix recorded: criterion → test → exact assertion → verdict, INCLUDING
      the 2 threshold nuances ((a) `max(gaps) < 0.8` vs "≥500 ms"; (e) `<= 2.0` vs "≤1.5").
- [ ] Collected count recorded as **9** (not the contract's "8") with the parametrize explanation.
- [ ] The 3 beyond-T1 tests identified (daemon-path latency-log cross-check + T7 lite pair).
- [ ] The `test_feed_audio_debug.py` finding recorded (source removed; stale `.pyc`; harmless).
- [ ] Heavy suite executed LIVE: `timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q`
      (bash-tool outer `timeout` > 600, e.g. 650); per-test pass/fail/skip recorded.
- [ ] Exit 124 (wedged) — if it occurs — diagnosed via single-test `timeout 120 … -k <name> -vv`,
      NOT retried blind; the diagnosis + outcome recorded.
- [ ] Scope respected: ONLY `test_feed_audio.py` run (NOT the mocked daemon set or pure-Python set).
- [ ] `test_results_t1.md` written to the work-item path, self-contained, with a clear VERDICT.

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the LIVE-verified asset table (4 WAVs + format + toolchain),
the LIVE collected count (9) with the parametrize explanation, the complete T1(a)–(e) coverage
matrix with the 2 threshold nuances pre-analyzed, the 3 beyond-T1 tests identified, the
`test_feed_audio_debug` finding, the exact run command (two-timeout form), the exit-code decision
tree (124 = wedged → localize, don't retry), the scope boundaries, and a verbatim
`test_results_t1.md` scaffold. No inference required.

### Documentation & References

```yaml
# MUST READ — the LIVE-verified audit (THIS is the spec / evidence base).
- file: plan/006_862ee9d6ef41/P1M5T2S1/research/t1_coverage_audit.md
  why: "§1 LIVE asset+toolchain table (4 WAVs soxi-confirmed 16kHz/mono/s16le; espeak-ng 1.52.0 +
        sox 14.8.0.1 present). §2 LIVE collected count = 9 (NOT the contract's 8; test_fuzzy_accuracy
        is parametrized → simple+punct). §3 the T1(a)–(e) coverage matrix WITH the 2 threshold
        nuances: (a) cadence gate `max(gaps) < 0.8` vs PRD '≥500 ms'; (e) latency gate `<=2.0` vs PRD
        '≤1.5' (+0.5 s documented slack, CUDA-gated). §4 the 3 beyond-T1 tests (daemon-path latency
        cross-check P1.M4.T1.S3 + T7 lite pair). §5 production-wiring confirmation (cfg_to_kwargs +
        _filter_kwargs_to_signature + cuda_check.is_cuda_available + _LATENCY_LOG_PREFIX all used).
        §6 skip-guard behavior (graceful; never errors the suite). §7 the test_feed_audio_debug
        FINDING (no source; stale .pyc Jul 7; gitignored; harmless). §8 the exact run command + exit
        decision tree. §9 acceptance-evidence map (#1/#2/#5/#10). §10 what the report MUST contain."
  critical: "The coverage is ALREADY COMPLETE; the 2 threshold nuances are documented tolerances
             (more permissive than the strict PRD number), NOT gaps. Do NOT 'fix' them unless a
             real-model run shows a genuine regression — they have explicit rationale in the test
             comments. The heavy run is the only genuinely LIVE part; everything else here is
             verified-static and should be copied into the report as-is + re-checked lightly."

# MUST READ — AGENTS.md (the repo's hard rules; this is a test-run item, the timeout rules bind directly).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on EVERY non-trivial command — this is THE heavy suite, minutes). The
        hang-vectors table: `uv run pytest …` / `.venv/bin/pytest …` = `timeout 600 uv run pytest
        <file>`; the contract specifies `.venv/bin/python -m pytest` form — use THAT. Rule 2 (never
        foreground the daemon — these tests don't need it; they build the recorder DIRECTLY, no
        daemon). Rule 3 (bound scratch; /tmp is RAM-backed tmpfs — the report goes under plan/, not /tmp)."
  critical: "zsh aliases python/pytest → ALWAYS `.venv/bin/python -m pytest`. Inner `timeout 600`
             (contract value; HEAVY — 2 model loads) + outer bash-tool `timeout` > 600 (e.g. 650).
             Exit 124 = wedged (a recorder/text() deadlock — see the test's G-ABORT/G-SHUTDOWN
             gotchas) → diagnose a SINGLE test under `timeout 120 … -k <name> -vv`, do NOT retry-blind.
             mypy is NOT installed; ruff is optional — pytest is the gate."

# MUST READ — the test file under audit (read it; it is the subject, not just the runner).
- file: tests/test_feed_audio.py
  why: "The module docstring maps the 5 T1 criteria (a)–(e) to their tests. The G-* load-bearing
        invariants (G-PACE real-time feed, G-TRAILING-SILENCE paced silence so the 0.6 s stop fires,
        G-ORDER consume-before-feed, G-ABORT helper-thread abort, G-SHUTDOWN helper-thread shutdown,
        G-RAW finals collected from recorder.text(cb), G-CPU CUDA-gate on criterion (e)+T7,
        G-FUZZY _token_overlap multiset helper) explain WHY the tests are shaped as they are + what
        a hang/flake means. The 2 threshold nuances are in the assertions: (a) `max(gaps) < 0.8` and
        (e) `latency_s <= 2.0` — both with inline rationale comments."
  critical: "The fixtures set `kwargs['use_microphone'] = False` (THE T1 override) and call
             `daemon.cfg_to_kwargs(cfg)` / `cfg_to_kwargs(cfg, lite=True)` + `_filter_kwargs_to_*`.
             So the test exercises the PRODUCTION wiring against the REAL recorder — this is
             integration-grade, not mocked. If a test SKIPS (not fails) on criterion (e) or T7, that
             is the CUDA-gate firing on a CPU box — record it as skip, not failure."

# MUST READ — the WAV generator (the asset producer the audit verifies).
- file: tests/make_test_audio.sh
  why: "Confirms the 4 WAVs are generated per PRD §6: espeak-ng en-us 150 wpm → sox resample 22050→16k
        mono s16le; utt_pause embeds 3.0 s PURE SILENCE inside one file (concat, no gap/crossfade);
        utt_multi = 3 sentences + 1.5 s gaps. Idempotent (skips existing; FORCE=1 regen). Writes a
        self-contained tests/out/.gitignore. If a WAV is missing at audit time, RUN THIS (the contract
        authorizes it)."
  critical: "`need espeak-ng` + `need sox` hard-fail if absent (PRD §2 guarantees them). Do NOT
             hand-edit the canonical strings (SIMPLE_TEXT/PAUSE_A/PAUSE_B/PUNCT_TEXT/MULTI_TEXTS) —
             they are PINNED and the test fuzzy-matches against them verbatim."

# MUST READ (cross-ref, cite-don't-re-audit) — the daemon functions the test calls into.
- file: voice_typing/daemon.py      # cfg_to_kwargs(:158), _filter_kwargs_to_signature(:253), _LATENCY_LOG_PREFIX(:377), LatencyLog(:393)
- file: voice_typing/cuda_check.py  # is_cuda_available(:105), resolve_device_and_models(:114)
  why: "The test uses cfg_to_kwargs (lite flag sets model=realtime_model_type=lite_model +
        use_main_model_for_realtime=True + snugger lite_post_speech_silence_duration), the kwarg
        filter (drops unknown kwargs, never crashes), and cuda_check.is_cuda_available (gates (e)+T7).
        If a test fails because a kwarg was DROPPED, that's a source-drift issue to report (the
        filter logs a WARNING per dropped key) — but the coverage AUDIT is about whether the test
        ASSERTS the criteria, not whether the source is perfect (the gap_*.md already audited source)."

# MUST READ — the merged PRD (the spec these tests encode; the oracle for the coverage verdict).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§6 T1 (the 5 criteria a–e) is the spec being audited; §4.2ter/T7 (lite: one model, ≥70%
        accuracy, snappier latency) for the lite tests; §4.4 (recorder kwargs) for the wiring; §7
        acceptance #1/#2/#5/#10 for the evidence map. When judging whether an assertion 'covers' a
        criterion, the PRD wording is the source of truth."

# MUST READ — the parallel previous PRP (the CONTRACT this item consumes + avoids duplicating).
- file: plan/006_862ee9d6ef41/P1M5T1S2/PRP.md
  why: "S2 runs the MOCKED daemon + recorder_host unit tests (219 tests, ~5 s, NO models). This item
        assumes that baseline: a real-model failure HERE is attributable to the ASR integration /
        feed_audio path, not daemon lifecycle logic (which S2 already proved green). S2 also sets the
        house format for the results doc — this item's test_results_t1.md mirrors it under the
        contract's name. DO NOT add S2's files to this run (scope boundary)."
  critical: "S2 is running IN PARALLEL. Do NOT edit S2's files or its test_results_daemon.md. The
             only shared surface is the SOURCE modules both depend on (daemon.py/cuda_check.py) — if
             a real-model test fails because a source module regressed, that may be S2's locus;
             coordinate rather than editing source (and this item is a REPORT item — it does NOT fix
             source anyway; it records the finding for a remediation task)."

# External — the API the tests exercise (cite for the report's "how it works" note).
- url: https://github.com/KoljaB/RealtimeSTT
  why: "RealtimeSTT README 'External Audio': 'Set use_microphone=False when audio comes from a file,
        stream, websocket, or another process. Feed 16-bit mono PCM chunks via feed_audio()'. This is
        exactly the T1 mechanism — confirms the test's `use_microphone=False` + `feed_audio(...,
        original_sample_rate=16000)` is the documented offline path."
  critical: "feed_audio is NON-blocking + re-slices to 32 ms internally; the WALL-CLOCK pacing in
             _feed_paced (feed a slice, sleep its duration) is what lets the VAD post_speech_silence
             stop threshold fire — that's the test's G-PACE/G-TRAILING-SILENCE invariant. A hang in
             the run is almost always a pacing/shutdown race, not a model bug."
```

### Current Codebase tree (relevant slice — state at P1.M5.T2.S1)

```bash
tests/
├── test_feed_audio.py            ( 9 collected) ← IN SCOPE: real-model T1 offline pipeline (feed_audio, no mic, no typing)
│                                   6 = T1(a)–(e) core + daemon-path latency cross-check; 3 = T7 lite pair
├── make_test_audio.sh            (generator)   ← IN SCOPE: verify it produces the 4 WAVs per PRD §6
├── out/                          (assets)      ← IN SCOPE: verify utt_{simple,pause,multi,punct}.wav (16kHz mono s16le)
│   ├── utt_simple.wav   (3.44 s) ✅ present
│   ├── utt_pause.wav    (7.92 s) ✅ present (3.0 s embedded silence)
│   ├── utt_multi.wav    (9.26 s) ✅ present (3 sentences + 2×1.5 s gaps)
│   ├── utt_punct.wav    (6.68 s) ✅ present
│   └── .gitignore                 (self-contained: generated audio not committed)
├── __pycache__/test_feed_audio_debug.cpython-312-pytest-9.1.1.pyc  ← STALE (source removed; finding)
├── test_daemon.py        (193) ┐ OUT — P1.M5.T1.S2 (parallel): mocked daemon/recorder_host (the logic-green baseline)
├── test_recorder_host.py ( 26) ┘
└── (9 pure-Python files)        OUT — P1.M5.T1.S1 (parallel): config/textproc/typing_backends/feedback/ctl/socket/status_sh/systemd
voice_typing/{daemon,cuda_check,config,textproc,...}.py   # modules the test calls into (cfg_to_kwargs, is_cuda_available, ...)
plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md         # ← OUTPUT (NEW; this item creates it)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md   # NEW — the report (the SOLE deliverable)
# (source/test files edited ONLY if a WAV is missing and make_test_audio.sh is run to regenerate —
#  that regenerates an ASSET, not source. NO source/test code edit; this is a REPORT item.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (AGENTS.md) — TWO timeouts, no exceptions. The contract value is `timeout 600` (HEAVY:
#   2 model loads = distil-large-v3 + small.en, minutes on first cold init). Set the bash tool's own
#   `timeout` param ABOVE 600 (e.g. 650) as the harness backstop. Exit 124 = the inner timeout KILLED
#   the process (wedged — a recorder/text()/shutdown deadlock; these tests use threads) → diagnose a
#   SINGLE test under `timeout 120 … -k <name> -vv`, do NOT retry-blind. (research §8; AGENTS.md Rule 1.)

# CRITICAL #2 (AGENTS.md) — zsh aliases `python`/`pytest`. ALWAYS `.venv/bin/python -m pytest` (full
#   venv path). Bare `python`/`pytest` may resolve to a zsh shim/wrapper. The contract's exact form is
#   `timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q` — use that verbatim.
#   mypy is NOT installed — do NOT run it; ruff is optional. pytest is the gate.

# CRITICAL #3 — this is a REAL-MODEL run, NOT mocked. It loads distil-large-v3 + small.en into VRAM
#   (and for lite, small.en-only). It builds the recorder via the PRODUCTION wiring (cfg_to_kwargs +
#   _filter_kwargs_to_signature + use_microphone=False + feed_audio). It does NOT start the daemon
#   (one test, test_daemon_path_*, constructs a VoiceTypingDaemon with a _NoopBackend + _StubFeedback
#   directly — still no real mic/keystrokes). Do NOT start voice-typing-daemon / arm the mic
#   (AGENTS.md forbids foregrounding it anyway).

# CRITICAL #4 — the tests use THREADS (consume/feed/abort/shutdown helper threads) + RealtimeSTT's
#   non-daemon transcript worker. A HANG is almost always a shutdown/abort race (see the test's
#   G-ABORT / G-SHUTDOWN / G-TRAILING-SILENCE comments), NOT a model bug. The session fixture tears
#   down via `threading.Thread(target=_safe_shutdown, ...).join(timeout=30.0)` — so a wedged shutdown
#   is bounded to 30 s. If the WHOLE suite exceeds ~600 s, kill + localize per-test with -k.

# CRITICAL #5 — COUNT DISCREPANCY. The contract said "8 tests"; LIVE `--collect-only` = 9 (because
#   test_fuzzy_accuracy is @parametrize over simple+punct → 2 cases). Record the LIVE count (9) in
#   the report, not the contract's "8". Re-confirm with --collect-only at execution time.

# CRITICAL #6 — the 2 THRESHOLD NUANCES are DOCUMENTED TOLERANCES, not bugs to fix:
#   (a) PRD §6 T1(a): "update at least every 500 ms". The test asserts `max(gaps) < 0.8` (800 ms).
#       Empirically fine (realtime_processing_pause=0.15 → ~150 ms cadence) but the GATE is wider
#       than the PRD number. Report it; do NOT tighten it unless the acceptance cross-check asks.
#   (e) PRD §6 T1(e): "final callback ≤ 1.5 s after last speech sample fed". The test asserts
#       `latency_s <= 2.0` (1.5 target + 0.5 s documented slack; CUDA-gated, skips on CPU). Report
#       it; the slack is intentional (GPU scheduling/variance on a 9-word utterance).
#   Both are MORE PERMISSIVE than the strict PRD number with inline rationale. Neither is a coverage
#   gap (the behavior IS asserted). Flag them so P1.M5.T5.S1 sees them explicitly.

# CRITICAL #7 — CUDA-GATED tests may SKIP, not FAIL. test_final_latency + test_lite_* call
#   `if not daemon.cuda_check.is_cuda_available(): pytest.skip(...)`. On a CPU-only box these SKIP
#   (exit 0, 0 failed, N skipped). On THIS box CUDA is present (verified: is_cuda_available uses
#   ctranslate2 device count ≥1), so they RUN. A skip is a VALID outcome to record, not a failure.
#   If the WHOLE file skips (WAVs missing OR deps absent), that means a prerequisite is off —
#   re-verify assets/deps before concluding.

# CRITICAL #8 — `test_feed_audio_debug.py` does NOT exist as source. Only a stale `.pyc`
#   (tests/__pycache__/test_feed_audio_debug.cpython-312-pytest-9.1.1.pyc, Jul 7). The source was
#   removed (an exploratory debug script superseded by the committed test_feed_audio.py). Report it
#   as: source removed, stale .pyc present, harmless (__pycache__ gitignored). Do NOT restore the
#   source. Optionally `rm -f tests/__pycache__/test_feed_audio_debug.*` to clean (non-load-bearing).

# CRITICAL #9 — scope boundary. Run ONLY `tests/test_feed_audio.py`. Do NOT add the mocked
#   daemon/recorder_host set (P1.M5.T1.S2, parallel) or the pure-Python set (P1.M5.T1.S1, parallel).
#   Mixing them in blows the timeout budget (this file alone is minutes) + blurs attribution across
#   the three M5.T1/T2 leaves. The other sets are hermetic + fast; this one is the heavy one.

# CRITICAL #10 — this is a REPORT item. It does NOT fix source or tests. If the heavy run fails on a
#   REAL bug (e.g. a WhisperX pause-merge regression, a feed_audio API change), RECORD the failure +
#   root-cause hypothesis in test_results_t1.md for a downstream REMEDIATION task. The ONLY asset
#   action authorized: if a WAV is missing, run `./tests/make_test_audio.sh` to regenerate it (the
#   contract explicitly allows this). Do NOT edit daemon.py / cuda_check.py / the test file.
```

## Implementation Blueprint

### Data models and structure

N/A — no code models. The deliverable is one Markdown report. The only "data" is the asset table +
the coverage matrix + the per-test run results.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY assets + toolchain (LIVE, cheap — no model load).
  - RUN (from /home/dustin/projects/voice-typing):
      for w in utt_simple utt_pause utt_multi utt_punct; do soxi tests/out/$w.wav; done
      command -v espeak-ng && espeak-ng --version | head -1
      command -v sox && sox --version | head -1
    (wrap in `timeout 30` if you like; these are instant.)
  - VERIFY each WAV: Channels=1, Sample Rate=16000, Precision=16-bit, Encoding=Signed Integer PCM.
    Expected durations (research §1): simple 3.44s, pause 7.92s, multi 9.26s, punct 6.68s.
  - IF any WAV is missing OR malformed (wrong rate/depth/channels): run
      timeout 300 ./tests/make_test_audio.sh     # regenerate (idempotent; FORCE=1 to overwrite)
    (bash-tool `timeout` 320). Record the regeneration in the report. Re-verify with soxi.
  - EXPECT (verified this round): all 4 present + correct format; espeak-ng 1.52.0 + sox 14.8.0.1.
  - GO to Task 2.

Task 2: STATIC COVERAGE AUDIT — map T1(a)–(e) → test → assertion (read tests/test_feed_audio.py).
  - For each criterion, find the test function + the EXACT assertion line. The research §3 matrix is
    the pre-filled answer — CONFIRM it against the live file (line numbers may have drifted) and copy
    it into the report. The 5 mappings:
      (a) onset  → test_partials_start_fast_and_cadence: `first_delay = partials[0][0] - onset; assert first_delay < 1.5`
      (a) cadence→ same test: `assert max(gaps) < 0.8`   ← THRESHOLD NUANCE (0.8 vs PRD 0.5)
      (b) pause  → test_pause_keeps_both_halves: `assert len(finals) >= 2` + `_token_overlap(joined, PAUSE_A|B) >= 0.80`
      (c) multi  → test_multi_yields_three_finals: `assert len(finals) == 3`
      (d) fuzzy  → _token_overlap multiset helper ≥0.80 in test_fuzzy_accuracy[simple|punct] + pause + multi
      (e) latency→ test_final_latency: `assert latency_s <= 2.0` (CUDA-gated)  ← THRESHOLD NUANCE (2.0 vs PRD 1.5)
  - IDENTIFY the 3 beyond-T1 tests: test_daemon_path_emits_latency_line_and_types_nothing (P1.M4.T1.S3
    cross-check) + test_lite_feed_audio_utt_simple + test_lite_latency_lower_than_normal (T7 pair).
  - CONFIRM production wiring: cfg_to_kwargs / cfg_to_kwargs(lite=True) + _filter_kwargs_to_signature
    + use_microphone=False + cuda_check.is_cuda_available gate. (research §5.)
  - RECORD the test_feed_audio_debug.py finding (no source; stale .pyc; harmless). (research §7.)
  - CONFIRM collected count: `timeout 120 .venv/bin/python -m pytest tests/test_feed_audio.py
    --collect-only -q | tail -3` → expect "9 tests collected". (bash-tool `timeout` 130.)

Task 3: RUN the heavy suite LIVE (AGENTS.md two-timeout discipline) — the gate.
  - RUN (from /home/dustin/projects/voice-typing):
      timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q
    (set the bash tool `timeout` to 650 — the outer backstop above the inner 600.)
  - EXPECT: `9 passed` (or `N passed, M skipped` if a CUDA-gate skips on CPU — on THIS box CUDA is
    present so all 9 should run). Minutes of wall time (2 cold model loads on first run).
  - CAPTURE the last ~20 lines (the pytest summary: "X passed in Ys" or the failure block).
  - IF exit 0 → record the pass counts + timing in the report; go to Task 4.
  - IF exit 1 (failures) → record the failing test name(s) + the assertion message; DO NOT fix (report
    item) — go to Task 4 with the failure recorded as a finding for a remediation task.
  - IF exit 124 (timeout/wedged) → do NOT retry-blind; localize: run the suspected test under
    `timeout 120 .venv/bin/python -m pytest tests/test_feed_audio.py -k <name> -vv` (bash-tool 130).
    A hang is a recorder/text()/shutdown race (G-ABORT/G-SHUTDOWN) — record the diagnosis + outcome.
  - IF exit 2 (collection error) → a module won't import or a WAV is gone → re-check assets/deps;
    record + (if a WAV is missing) run make_test_audio.sh (Task 1) then re-run.
  - DO NOT add other files (scope boundary, CRITICAL #9).

Task 4: WRITE plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md (the SOLE deliverable).
  - CREATE the file (NEW; no existing test_results_t1.md). Use the verbatim scaffold in "Task 4 SOURCE".
  - CONTENT: asset table (Task 1), coverage matrix + 2 nuances + beyond-T1 tests + debug finding
    (Task 2), collected count (9, not 8), the LIVE run command + per-test pass/fail/skip + timing
    (Task 3), and the VERDICT ("T1(a)–(e) coverage COMPLETE; real-model run <result>").
  - PLACEMENT: plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md.
  - DO NOT edit PRD.md / tasks.json / prd_snapshot.md / .gitignore / source / tests. REPORT item only.

Task 5: (NONE) — no source/test changes, no new tests. This is an audit + execution + documentation item.
```

#### Task 4 SOURCE — `test_results_t1.md` verbatim scaffold (pre-fill the static parts; edit the LIVE run results at execution)

```markdown
# Test Results — P1.M5.T2.S1: T1 offline pipeline test coverage audit (test_feed_audio.py)

**Date:** <YYYY-MM-DD>
**Scope:** PRD §6 T1 — the offline feed_audio pipeline test (`tests/test_feed_audio.py`), real
models, no mic, no typing. **Excludes** the mocked daemon/recorder_host set (P1.M5.T1.S2) and the
pure-Python set (P1.M5.T1.S1).
**Verdict:** ✅ T1(a)–(e) coverage = COMPLETE (all 5 criteria asserted). Real-model run: <9 passed |
N passed, M skipped | failures listed>.

## 1. Asset + toolchain verification (LIVE)

| asset | format (soxi) | duration | status |
|---|---|---|---|
| tests/out/utt_simple.wav | 16kHz mono 16-bit signed PCM | 3.44 s | ✅ |
| tests/out/utt_pause.wav  | 16kHz mono 16-bit signed PCM | 7.92 s (incl. 3.0 s silence) | ✅ |
| tests/out/utt_multi.wav  | 16kHz mono 16-bit signed PCM | 9.26 s (3 sentences + 2×1.5 s) | ✅ |
| tests/out/utt_punct.wav  | 16kHz mono 16-bit signed PCM | 6.68 s | ✅ |
| espeak-ng | 1.52.0 (/usr/bin/espeak-ng) | — | ✅ present |
| sox | SoX_ng v14.8.0.1 (/usr/bin/sox) | — | ✅ present |
| make_test_audio.sh | idempotent generator (PRD §6) | — | ✅ (no regen needed) |

(If a WAV was regenerated, note it here: "ran `./tests/make_test_audio.sh` — regenerated <which>")

## 2. Collected test count (LIVE `--collect-only`)

**9 tests collected** (NOT the contract's "8" — `test_fuzzy_accuracy` is `@parametrize` over
`simple` + `punct` → 2 cases). 6 = T1(a)–(e) core + the daemon-path latency-log cross-check; 3 =
the T7 lite pair.

## 3. T1(a)–(e) coverage matrix (static audit — confirmed against live file)

| PRD criterion | test | exact assertion | verdict |
|---|---|---|---|
| (a) partials onset `<1.5 s` | test_partials_start_fast_and_cadence | `assert first_delay < 1.5` | ✅ exact |
| (a) partial cadence `≥500 ms` | same | `assert max(gaps) < 0.8` | ⚠️ NUANCE: gate 0.8 s vs PRD 0.5 s (documented tolerance; empirically ~150 ms via realtime_processing_pause=0.15) |
| (b) pause keeps BOTH halves (WhisperX fix) | test_pause_keeps_both_halves | `assert len(finals) >= 2` + `_token_overlap(joined, PAUSE_A\|B) >= 0.80` | ✅ the regression test |
| (c) multi → 3 finals | test_multi_yields_three_finals | `assert len(finals) == 3` | ✅ exact (strict ==) |
| (d) fuzzy `≥80%` | _token_overlap in test_fuzzy_accuracy[simple\|punct] + pause + multi | `assert _token_overlap(...) >= 0.80` | ✅ all 4 WAVs |
| (e) final latency `≤1.5 s` | test_final_latency (CUDA-gated) | `assert latency_s <= 2.0` | ⚠️ NUANCE: gate 2.0 s vs PRD 1.5 s (+0.5 s documented slack; skips on CPU) |

**Coverage verdict: COMPLETE.** All 5 criteria (a)–(e) have a dedicated assertion. The 2 threshold
nuances are MORE PERMISSIVE than the strict PRD number with inline rationale in the test — they are
documented tolerances, not gaps. Flagged here for the acceptance cross-check (P1.M5.T5.S1).

## 4. Beyond-T1 tests in the same file (also run)

- `test_daemon_path_emits_latency_line_and_types_nothing` — P1.M4.T1.S3 cross-check: the REAL daemon
  path emits the `voice-typing latency:` log line + the _NoopBackend types nothing (PRD T1 "no typing").
- `test_lite_feed_audio_utt_simple` — T7(a,b): lite = ONE model (`use_main_model_for_realtime=True`)
  + finals fuzzy `≥0.70` (lower bar; small.en is the final model). CUDA-gated.
- `test_lite_latency_lower_than_normal` — T7(c): lite latency `<= normal_best * 1.25` (best-of-3 min;
  catches a two-model regression). CUDA-gated.

## 5. `test_feed_audio_debug.py` finding

**No source file** `tests/test_feed_audio_debug.py`. A stale compiled artifact remains:
`tests/__pycache__/test_feed_audio_debug.cpython-312-pytest-9.1.1.pyc` (Jul 7). Source was removed
(exploratory debug script, superseded by the committed test_feed_audio.py). Harmless —
`__pycache__` is gitignored. (Optionally `rm -f tests/__pycache__/test_feed_audio_debug.*` to clean.)

## 6. Real-model run (LIVE)

```bash
timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q
# (bash-tool outer `timeout` set to 650 — backstop above the inner 600.)
```

| test | result | notes |
|---|---|---|
| test_partials_start_fast_and_cadence | <PASS\|FAIL\|SKIP> | |
| test_pause_keeps_both_halves | <…> | the WhisperX regression |
| test_multi_yields_three_finals | <…> | |
| test_fuzzy_accuracy[simple-…] | <…> | |
| test_fuzzy_accuracy[punct-…] | <…> | |
| test_final_latency | <…> | CUDA-gated |
| test_daemon_path_emits_latency_line_and_types_nothing | <…> | P1.M4.T1.S3 cross-check |
| test_lite_feed_audio_utt_simple | <…> | T7; CUDA-gated |
| test_lite_latency_lower_than_normal | <…> | T7; CUDA-gated |

**Summary:** <X passed, Y skipped, Z failed> in <T s>. (paste the pytest summary line)

(If any FAIL/124: record the failing test + assertion message + root-cause hypothesis as a finding
for a downstream REMEDIATION task. This item is a REPORT item — it does not fix source.)

## 7. Acceptance-criteria evidence (this item is the real-model proof for)

- **#1** (WhisperX pause fix / transcription accuracy) — test_pause_keeps_both_halves + multi + fuzzy.
- **#2** (drain / ≥3 s pause loses zero words) — test_pause_keeps_both_halves (real-model backstop).
- **#5** (no hallucination) — feed_audio tests feed real silence (3 s pause, 1.5 s gaps, ~1.6 s
  trailing) and assert ONLY spoken text returns. (Full 2-min idle = T4 / P1.M5.T4.)
- **#10** (lite mode) — test_lite_feed_audio_utt_simple + test_lite_latency_lower_than_normal (T7).
```

### Implementation Patterns & Key Details

```python
# The coverage verdict logic (Task 2): for each T1 criterion, does the test ASSERT it?
#   YES (all 5 do) → coverage = COMPLETE. Record the exact assertion + any threshold nuance.
#   The 2 nuances ((a) cadence 0.8 vs 0.5; (e) latency 2.0 vs 1.5) are NOT gaps — the behavior IS
#   asserted, just with a wider gate + documented rationale. Flag, don't "fix" (this is a report item).

# The exit-code decision tree (Task 3):
#   exit 0  → record pass counts + timing; write report (the expected case).
#   exit 1  (FAILURES) → record the failing test + assertion msg; DO NOT fix (report item); the
#                finding goes to a remediation task. Common real-model flakes: a fuzzy score just
#                under 0.80 on a noisy GPU (espeak is robotic) — check whether it's a true regression
#                (pause merged, words dropped) vs a 1-token-under threshold; record either way.
#   exit 2  (COLLECTION) → a module won't import OR a WAV is gone → re-check assets/deps (Task 1);
#                if a WAV is missing, run make_test_audio.sh, then re-run.
#   exit 124 (TIMEOUT) → wedged → recorder/text()/shutdown race (threads + non-daemon worker) →
#                localize a SINGLE test under `timeout 120 … -k <name> -vv`; record the diagnosis.

# What "skip" means (vs fail): test_final_latency + the T7 pair call
#   `if not daemon.cuda_check.is_cuda_available(): pytest.skip(...)`. On a CPU box they SKIP (valid).
#   On THIS box CUDA is present (ctranslate2 device count ≥1) so they RUN. A skip is NOT a failure —
#   record it as skip with the reason. If the WHOLE file skips, a prerequisite (WAVs/deps) is off.

# The _token_overlap multiset helper (the fuzzy matcher) — case/punctuation-insensitive, multiset
# intersection / ref-length. 1.0 = perfect; PRD §6 mandates ≥0.80 for espeak synthetic audio. The
# test's own helper (textproc.clean does NOT fuzzy-match). A fuzzy FAIL = the ASR dropped/merged too
# many tokens — a real transcription regression to report.
```

### Integration Points

```yaml
CONSUMES (read-only):
  - tests/test_feed_audio.py                                  # the subject (audit + run)
  - tests/make_test_audio.sh                                  # the asset generator (verify; regen if missing)
  - tests/out/utt_{simple,pause,multi,punct}.wav              # the assets (verify format)
  - voice_typing/{daemon,cuda_check}.py                       # functions the test calls (cfg_to_kwargs, is_cuda_available, ...)
  - plan/006_862ee9d6ef41/prd_snapshot.md                     # §6 T1 + §4.2ter/T7 + §4.4 + §7 AC#1/#2/#5/#10
  - plan/006_862ee9d6ef41/P1M5T1S2/PRP.md                     # parallel S2 (mocked logic-green baseline; results-doc format precedent)

PRODUCES (the SOLE output):
  - plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md         # NEW report (coverage matrix + asset table + LIVE run results)

FEEDS (downstream consumers):
  - P1.M5.T5.S1 (acceptance cross-check)                      # consumes the report as real-model evidence for AC #1/#2/#5/#10
  - P1.M5.T4.*  (T4 idle stability)                           # this item's silence-feeding partial evidence for #5

PARALLEL-SAFE:
  - P1.M5.T1.S1 (pure-Python tests, in flight) = ZERO file overlap (different test files; report goes to P1M5T2S1/).
  - P1.M5.T1.S2 (mocked daemon/recorder_host, in flight) = ZERO test-file overlap (test_daemon.py / test_recorder_host.py
    vs test_feed_audio.py). Shared surface = SOURCE modules (daemon.py/cuda_check.py) — if a real-model test fails
    because a SOURCE module regressed, that may be S2's locus; this item RECORDS the finding, it does not edit source
    (report item). Expected: this file runs green independently because the ASR integration is sound.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown report — validate structure, not code.
test -f plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md && echo "EXISTS"
grep -q 'P1.M5.T2.S1' plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md && echo "titled"
grep -qi 'COMPLETE'   plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md && echo "coverage verdict present"
grep -q  '9 tests'    plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md && echo "count recorded"
grep -qi 'nuance'     plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md && echo "threshold nuances flagged"
# Expected: EXISTS; title + COMPLETE verdict + count 9 + at least one "nuance" flag present.
```

### Level 2: Unit Tests (Component Validation) — THE gate (heavy, real models)

```bash
# RUN the suite LIVE (two timeouts per AGENTS.md Rule 1):
timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q
# (set the bash tool `timeout` to 650 — the outer backstop above the inner 600.)
# Expected: `9 passed` (or N passed + M skipped on CPU); minutes (2 cold model loads). Record the
# ACTUAL per-test result + timing in test_results_t1.md (do not copy this PRP's expected verbatim).
```

### Level 3: Integration Testing (System Validation)

```bash
# Collected-count sanity (NO model load — confirms the 9 count + that collection stays import-pure):
timeout 130 .venv/bin/python -m pytest tests/test_feed_audio.py --collect-only -q 2>&1 | tail -3
#   expect "9 tests collected in <0.1s". If it imports torch at collection → fixture/lazy-import bug
#   (would break test_voicectl.py's import-purity check in a full sweep) — record as a finding.

# Per-test isolation (if a single test hangs/fails, run it alone to localize — under timeout):
#   timeout 180 .venv/bin/python -m pytest tests/test_feed_audio.py -k test_pause_keeps_both_halves -vv
# Expected: collect-only is sub-second + import-pure; a single -k run stays under its timeout.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Asset format spot-check (BOTH confirm 16kHz mono 16-bit signed PCM = RealtimeSTT SAMPLE_RATE=16000):
for w in utt_simple utt_pause utt_multi utt_punct; do
  soxi tests/out/$w.wav | grep -E 'Channels|Sample Rate|Precision|Sample Encoding'
done
# Expected: Channels=1, Sample Rate=16000, Precision=16-bit, Sample Encoding=16-bit Signed Integer PCM.

# Generator idempotency (safe — skips existing WAVs; verifies make_test_audio.sh runs cleanly):
timeout 300 ./tests/make_test_audio.sh 2>&1 | tail -8
#   expect "skip utt_simple.wav (exists; FORCE=1 to regenerate)" x4 + the summary table. (bash-tool 320.)
# Expected: all 4 skip (idempotent); the summary prints durations. No regeneration occurs.
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 WAVs re-verified LIVE (16 kHz mono 16-bit signed PCM); any missing regenerated + recorded.
- [ ] espeak-ng + sox confirmed present.
- [ ] Heavy suite executed LIVE: `timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q`
      (outer bash-tool `timeout` 650); per-test pass/fail/skip recorded.
- [ ] Collected count recorded as **9** (not 8); collect-only stays import-pure (no torch at collection).
- [ ] `test_results_t1.md` exists at the work-item path; title + COMPLETE verdict + count + nuances present.

### Feature Validation

- [ ] All success criteria from "What" section met.
- [ ] T1(a)–(e) coverage matrix complete; the 2 threshold nuances flagged explicitly (not silently).
- [ ] The 3 beyond-T1 tests + the test_feed_audio_debug finding recorded.
- [ ] Exit 124 (if any) diagnosed via single-test `-k -vv`, not retried blind; diagnosis recorded.
- [ ] Scope respected: ONLY test_feed_audio.py run (NOT the mocked or pure-Python sets).

### Code Quality Validation

- [ ] `test_results_t1.md` is self-contained (asset table + matrix + LIVE run results + verdict).
- [ ] Re-verified LIVE asset durations recorded (not copied from this PRP verbatim).
- [ ] No source/test edited (report item); the only asset action = make_test_audio.sh if a WAV is missing.

### Documentation & Deployment

- [ ] Report placed at `plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md`.
- [ ] Feeds P1.M5.T5.S1 (Acceptance #1/#2/#5/#10 real-model evidence).

---

## Anti-Patterns to Avoid

- ❌ Don't run with a single timeout or no timeout — AGENTS.md Rule 1 mandates inner `timeout 600` +
  outer bash-tool `timeout` (>600, e.g. 650); exit 124 (wedged) must be diagnosable, not swallowed.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — always `.venv/bin/python -m pytest`.
- ❌ Don't add the mocked daemon/recorder_host set (S2) or the pure-Python set (S1) — scope boundary;
  they're hermetic + fast; this file is the heavy one and mixing blurs attribution + blows the budget.
- ❌ Don't "fix" the 2 threshold nuances ((a) cadence 0.8 vs 0.5; (e) latency 2.0 vs 1.5) — they are
  DOCUMENTED tolerances with inline rationale in the test. This is a REPORT item; flag them, don't
  edit them. (Tightening belongs to a remediation task if the acceptance cross-check decides to.)
- ❌ Don't treat a SKIP as a FAIL — test_final_latency + the T7 pair are CUDA-gated; a skip is valid.
- ❌ Don't start the daemon / arm the mic — the tests build the recorder DIRECTLY (one test constructs
  a VoiceTypingDaemon with a _NoopBackend + _StubFeedback, still no real mic/keystrokes). AGENTS.md
  forbids foregrounding the daemon anyway.
- ❌ Don't assume a minutes-long run is "broken" — it loads 2 real models (distil-large-v3 + small.en)
  cold; minutes is expected on first run. Only worry if it exceeds the 600 s timeout (exit 124).
- ❌ Don't restore `test_feed_audio_debug.py` source — it was an exploratory debug script, superseded
  by the committed test_feed_audio.py. Record the stale .pyc finding; optionally rm it (non-load-bearing).
- ❌ Don't edit the parallel S1/S2 leaves' files or their results docs — if a real-model test fails
  because a SOURCE module regressed, that may be S2's locus; coordinate. This item RECORDS, not fixes.
- ❌ Don't edit PRD.md / tasks.json / prd_snapshot.md / .gitignore / source / tests.
- ❌ Don't copy this PRP's expected durations / pass counts into the report verbatim — re-verify LIVE.

---

## Confidence Score

**9/10** — one-pass success likelihood. The assets are ALREADY present + correctly formatted (verified
LIVE via soxi: 4 WAVs, 16 kHz mono s16le), the toolchain is present (espeak-ng 1.52.0 + sox 14.8.0.1),
the coverage is ALREADY COMPLETE (all 5 T1 criteria asserted, verified via `--collect-only` + static
read; the 2 threshold nuances are pre-analyzed), the production wiring is confirmed (cfg_to_kwargs +
_filter_kwargs_to_signature + cuda_check.is_cuda_available + _LATENCY_LOG_PREFIX all present + used),
the collected count is confirmed (9, not the contract's 8), and the deliverable is a single
self-contained report with a verbatim scaffold. The exit-code decision tree (CRITICAL #1/#4/#7)
covers the only genuinely LIVE unknown — the heavy real-model run (a hang = recorder/shutdown race →
localize per-test; a fail = real ASR regression to record for remediation; a skip = CUDA-gate firing).
Residual -1: the real-model run could surface a genuine flake on a noisy GPU (espeak is robotic; a
fuzzy score landing just under 0.80, or the lite latency band tripping) — but those are recorded
findings, not blockers to delivering the report, and the research §3 matrix gives the agent the exact
assertion + rationale to classify each outcome correctly.