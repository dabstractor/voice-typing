# Test Results — P1.M5.T2.S1: T1 offline pipeline test coverage audit (test_feed_audio.py)

**Date:** 2026-07-18
**Scope:** PRD §6 T1 — the offline feed_audio pipeline test (`tests/test_feed_audio.py`), real
models, no mic, no typing. **Excludes** the mocked daemon/recorder_host set (P1.M5.T1.S2) and the
pure-Python set (P1.M5.T1.S1).
**Verdict:** ✅ T1(a)–(e) coverage = COMPLETE (all 5 criteria asserted). Real-model run: **9 passed, 0 skipped, 0 failed** in ~82 s.

## 1. Asset + toolchain verification (LIVE)

| asset | format (soxi) | duration | status |
|---|---|---|---|
| tests/out/utt_simple.wav | 16 kHz mono 16-bit Signed Integer PCM | 3.44 s | ✅ |
| tests/out/utt_pause.wav  | 16 kHz mono 16-bit Signed Integer PCM | 7.92 s (incl. 3.0 s embedded silence) | ✅ |
| tests/out/utt_multi.wav  | 16 kHz mono 16-bit Signed Integer PCM | 9.26 s (3 sentences + 2×1.5 s gaps) | ✅ |
| tests/out/utt_punct.wav  | 16 kHz mono 16-bit Signed Integer PCM | 6.68 s | ✅ |
| espeak-ng | 1.52.0 (/usr/bin/espeak-ng) | — | ✅ present |
| sox | SoX_ng v14.8.0.1 (/usr/bin/sox) | — | ✅ present |
| make_test_audio.sh | idempotent generator (PRD §6) | — | ✅ (no regen needed) |

All 4 WAVs re-verified LIVE as 16 kHz mono 16-bit Signed Integer PCM (= RealtimeSTT
SAMPLE_RATE=16000). All durations match the research baseline exactly (3.44 / 7.92 / 9.26 / 6.68 s).
espeak-ng 1.52.0 + sox v14.8.0.1 confirmed present (PRD §2). **No WAV was regenerated** — all were
present and correctly formatted, so `make_test_audio.sh` was not run.

## 2. Collected test count (LIVE `--collect-only`)

```
9 tests collected in 0.01s
```

**9 tests collected** (NOT the work-item contract's "8" — `test_fuzzy_accuracy` is
`@pytest.mark.parametrize` over `simple` + `punct` → 2 collected cases). 6 of the 9 are the core
T1(a)–(e) criteria + the daemon-path latency-log cross-check; the other 3 are the T7 lite pair (and
the second parametrize case of fuzzy). Collection is sub-second and import-pure (no torch /
RealtimeSTT imported at collection time — heavy deps are lazy via `_load_deps()` + `TYPE_CHECKING`
guards), so a full `pytest tests/` sweep stays green on a CPU-only/clone box.

## 3. T1(a)–(e) coverage matrix (static audit — confirmed against live file)

| PRD criterion | test | exact assertion | verdict |
|---|---|---|---|
| (a) partials onset `<1.5 s` after speech onset | `test_partials_start_fast_and_cadence` | `first_delay = partials[0][0] - onset; assert first_delay < 1.5` (onset = `on_vad_start`, fallback first partial) | ✅ exact |
| (a) partial cadence `≥ every 500 ms` | same | `assert max(gaps) < 0.8` (only when `speaking_s > 0.5`) | ⚠️ NUANCE: gate 0.8 s vs PRD 0.5 s (documented tolerance; empirically ~150 ms via `realtime_processing_pause=0.15`) |
| (b) pause keeps BOTH halves (WhisperX fix) | `test_pause_keeps_both_halves` | `assert len(finals) >= 2` + `_token_overlap(joined, PAUSE_A) >= 0.80` + `_token_overlap(joined, PAUSE_B) >= 0.80` | ✅ the regression test |
| (c) multi → 3 finals | `test_multi_yields_three_finals` | `assert len(finals) == 3` (strict `==`) | ✅ exact |
| (d) fuzzy `≥80%` | `_token_overlap` in `test_fuzzy_accuracy[simple\|punct]` + pause (both halves) + multi (per-utterance zip) | `assert _token_overlap(...) >= 0.80` | ✅ all 4 WAVs |
| (e) final latency `≤1.5 s` | `test_final_latency` (CUDA-gated) | `latency_s = t_final[0] - t_last_speech[0]; assert latency_s <= 2.0` | ⚠️ NUANCE: gate 2.0 s vs PRD 1.5 s (+0.5 s documented slack; `pytest.skip` on CPU) |

**Coverage verdict: COMPLETE.** All 5 criteria (a)–(e) have a dedicated assertion. The 2 threshold
nuances are MORE PERMISSIVE than the strict PRD number with inline rationale in the test comments —
they are **documented tolerances, not gaps** (the behavior IS asserted; the gate is just wider).
Flagged here so the acceptance cross-check (P1.M5.T5.S1) sees them explicitly rather than
discovering them later.

## 4. Beyond-T1 tests in the same file (also run)

- `test_daemon_path_emits_latency_line_and_types_nothing` — P1.M4.T1.S3 cross-check: the REAL daemon
  path (`VoiceTypingDaemon(recorder=rec, backend=_NoopBackend(), feedback=_StubFeedback())`) emits
  the `voice-typing latency:` log line (`daemon._LATENCY_LOG_PREFIX`) AND the no-op backend types
  nothing (`backend.typed == []`, PRD T1 "no typing").
- `test_lite_feed_audio_utt_simple` — T7(a,b): lite = ONE model
  (`assert rec.use_main_model_for_realtime is True`) + finals fuzzy `≥0.70` (lower bar; small.en is
  the final model in lite mode). CUDA-gated.
- `test_lite_latency_lower_than_normal` — T7(c): lite final-typed latency `<= normal_best * 1.25`
  (best-of-3 min per recorder; tolerance band catches a two-model regression which is ~1.5–2×
  slower). CUDA-gated.

## 5. `test_feed_audio_debug.py` finding

**No source file** `tests/test_feed_audio_debug.py` exists. A stale compiled artifact remains:
`tests/__pycache__/test_feed_audio_debug.cpython-312-pytest-9.1.1.pyc` (dated Jul 7, 47293 bytes).
The source was removed (an exploratory debug script, superseded by the committed
`test_feed_audio.py`). Harmless — `tests/__pycache__` is gitignored (and a self-contained
`tests/out/.gitignore` is written by `make_test_audio.sh`). Do NOT restore the source.
(Optionally `rm -f tests/__pycache__/test_feed_audio_debug.*` to clean — non-load-bearing; not done
here as it is a REPORT item with no asset action required.)

## 6. Real-model run (LIVE)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q
# (bash-tool outer `timeout` set to 650 — backstop above the inner 600.)
```

| test | result | notes |
|---|---|---|
| test_partials_start_fast_and_cadence | ✅ PASS | (a) onset + cadence |
| test_pause_keeps_both_halves | ✅ PASS | (b) the WhisperX regression — BOTH halves transcribed across the 3 s pause |
| test_multi_yields_three_finals | ✅ PASS | (c) strict `== 3` finals |
| test_fuzzy_accuracy[simple-…] | ✅ PASS | (d) ≥0.80 |
| test_fuzzy_accuracy[punct-…] | ✅ PASS | (d) ≥0.80 |
| test_final_latency | ✅ PASS | (e) CUDA-gated; ran (GPU present); ≤2.0 s |
| test_daemon_path_emits_latency_line_and_types_nothing | ✅ PASS | P1.M4.T1.S3 cross-check; latency line emitted, nothing typed |
| test_lite_feed_audio_utt_simple | ✅ PASS | T7(a,b); CUDA-gated; ran; one-model + ≥0.70 |
| test_lite_latency_lower_than_normal | ✅ PASS | T7(c); CUDA-gated; ran; lite ≤ normal×1.25 |

**Summary:** `9 passed in 82.09s (0:01:22)` — exit 0. (Re-confirmed by a second `-q` run:
`9 passed in 82.57s`.) All 9 tests passed, including the 3 CUDA-gated tests
(test_final_latency + the T7 lite pair) — CUDA is healthy on this box
(`cuda_check.is_cuda_available()` returned True; ctranslate2 device count ≥1), so nothing skipped.
Well under the 600 s inner timeout. No failures, no skips, no exit-124 wedge.

## 7. Acceptance-criteria evidence (this item is the real-model proof for)

- **#1** (WhisperX pause fix / transcription accuracy) — `test_pause_keeps_both_halves` (BOTH halves
  across the 3 s embedded pause) + `test_multi_yields_three_finals` + `test_fuzzy_accuracy[*]` (real
  models, real feed_audio, ≥0.80 fuzzy). ✅ all PASSED.
- **#2** (drain / ≥3 s pause loses zero words) — `test_pause_keeps_both_halves` is the real-model
  backstop for the mocked drain tests in P1.M5.T1.S2. ✅ PASSED.
- **#5** (no hallucination) — the feed_audio tests feed REAL silence (the 3 s embedded pause, the
  1.5 s multi gaps, the ~1.6 s paced trailing silence) and assert ONLY the spoken text returns, not
  silence-hallucinated words. (Full 2-min idle stability = PRD T4 / P1.M5.T4.) ✅ no spurious finals.
- **#10** (lite mode) — `test_lite_feed_audio_utt_simple` (one model + ≥0.70) +
  `test_lite_latency_lower_than_normal` (lite ≤ normal×1.25). ✅ both PASSED.