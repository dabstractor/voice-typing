# T1 Coverage Audit — P1.M5.T2.S1 evidence base

LIVE-verified this round (no model load — `--collect-only` + static read + `soxi`). The heavy
real-model RUN is left to the implementing agent (AGENTS.md two-timeout discipline; minutes).

## 1. Asset + toolchain verification (LIVE)

| asset / tool | status | evidence |
|---|---|---|
| tests/out/utt_simple.wav | ✅ present, 3.44 s | 16kHz, 1ch, 16-bit Signed Integer PCM, 110k |
| tests/out/utt_pause.wav | ✅ present, 7.92 s | 16kHz mono s16le — includes the 3.0 s embedded silence |
| tests/out/utt_multi.wav | ✅ present, 9.26 s | 16kHz mono s16le — 3 sentences + 2×1.5 s gaps |
| tests/out/utt_punct.wav | ✅ present, 6.68 s | 16kHz mono s16le |
| espeak-ng | ✅ 1.52.0 | /usr/bin/espeak-ng (PRD §2 requires it) |
| sox | ✅ SoX_ng v14.8.0.1 | /usr/bin/sox (resample 22050→16k, synth silence, concat) |
| ffmpeg | ✅ present (optional) | resample fallback only — not required |
| tests/make_test_audio.sh | ✅ present, executable | idempotent (skips existing WAVs; FORCE=1 to regen); writes self-contained tests/out/.gitignore |

**All 4 WAVs exist with the correct format** (16 kHz mono 16-bit signed PCM = RealtimeSTT
SAMPLE_RATE=16000). `make_test_audio.sh` is idempotent and matches PRD §6 (en-us, 150 wpm, 3.0 s
embedded pause silence, 1.5 s multi gaps). **No regeneration needed** (assets present); the PRP has
the agent re-verify with `soxi` (in case of drift) and run `make_test_audio.sh` ONLY if a WAV is
absent/stale.

## 2. test_feed_audio.py — collected test count (LIVE `--collect-only`, 0.01 s, NO model load)

```
tests/test_feed_audio.py::test_partials_start_fast_and_cadence
tests/test_feed_audio.py::test_pause_keeps_both_halves
tests/test_feed_audio.py::test_multi_yields_three_finals
tests/test_feed_audio.py::test_fuzzy_accuracy[simple-…]
tests/test_feed_audio.py::test_fuzzy_accuracy[punct-…]
tests/test_feed_audio.py::test_final_latency
tests/test_feed_audio.py::test_daemon_path_emits_latency_line_and_types_nothing
tests/test_feed_audio.py::test_lite_feed_audio_utt_simple
tests/test_feed_audio.py::test_lite_latency_lower_than_normal
9 tests collected in 0.01s
```

**COUNT DISCREPANCY:** the work-item contract said "8 tests"; the LIVE count is **9** (because
`test_fuzzy_accuracy` is `@pytest.mark.parametrize` over `simple` + `punct` → 2 collected cases).
Record the LIVE count (9) in `test_results_t1.md`, not the contract's "8". 6 of the 9 are the core
T1 criteria; the other 3 are a P1.M4.T1.S3 daemon-path cross-check + the T7 lite pair (see §4).

## 3. Coverage matrix — PRD §6 T1(a)–(e) → test → assertion → verdict

| PRD T1 criterion | test function(s) | exact assertion | coverage verdict |
|---|---|---|---|
| **(a)** partials start `<1.5 s` after speech onset | `test_partials_start_fast_and_cadence` | `first_delay = partials[0][0] - onset; assert first_delay < 1.5` (onset = `on_vad_start` stamp, fallback to first partial) | ✅ **EXACT MATCH** to PRD |
| **(a)** partials update `≥ every 500 ms` while speaking | `test_partials_start_fast_and_cadence` | `gaps = [b-a for a,b in zip(stamps,stamps[1:])]; assert max(gaps) < 0.8` (only when `speaking_s > 0.5`) | ⚠️ **LOOSER than PRD**: gate is `0.8 s` (800 ms) max gap, but PRD wording is "≥ every 500 ms" (i.e. gaps ≤500 ms). A 0.6–0.8 s gap would PASS the test yet VIOLATE the strict PRD number. Empirically fine (`realtime_processing_pause=0.15` → ~150 ms cadence) but the assertion gate is more permissive than the spec. **Document as a coverage nuance, not a failure.** |
| **(b)** `utt_pause.wav` yields the words AFTER the 3 s pause (the WhisperX failure) | `test_pause_keeps_both_halves` | `want_finals=2`; `assert len(finals) >= 2` (the merge-guard); `assert _token_overlap(joined, PAUSE_A) >= 0.80 AND …PAUSE_B >= 0.80` | ✅ **THE regression test** — asserts BOTH halves across the finalized texts |
| **(c)** `utt_multi.wav` → 3 non-empty finals | `test_multi_yields_three_finals` | `want_finals=3`; `assert len(finals) == 3` | ✅ **EXACT** (note `==` not `>=` — strict 3) |
| **(d)** fuzzy accuracy `≥80%` per utterance | `_token_overlap` multiset helper (case/punct-insensitive), used in: `test_fuzzy_accuracy[simple]`, `test_fuzzy_accuracy[punct]`, `test_pause_keeps_both_halves` (both halves), `test_multi_yields_three_finals` (per-utterance zip) | `assert _token_overlap(joined, ref) >= 0.80` | ✅ **COVERED** across all 4 WAVs (simple/punct explicit; pause both halves; multi per-sentence) |
| **(e)** final callback `≤1.5 s` after last speech sample fed | `test_final_latency` (CUDA-gated: `pytest.skip` if `not daemon.cuda_check.is_cuda_available()`) | `latency_s = t_final[0] - t_last_speech[0]; assert latency_s <= 2.0` | ⚠️ **DEVIATION with rationale**: test asserts `≤2.0 s`, not PRD's `≤1.5 s`. Code comment: "1.5 s target (PRD §6) + 0.5 s documented slack (research pitfall #5)". CUDA-gated (skips on CPU — distil-large-v3 on CPU can exceed it). **Document as a documented-tolerance deviation, not a failure.** |

**Verdict:** ALL FIVE T1 criteria (a)–(e) have a dedicated assertion. Two have a threshold nuance
((a) cadence gate 0.8 vs 0.5; (e) latency gate 2.0 vs 1.5) — both are *more permissive* than the
strict PRD number, both have documented rationale, neither is a coverage GAP (the behavior IS
asserted; the gate is just wider). The report should list these as "threshold nuances to flag" so
the acceptance cross-check (P1.M5.T5.S1) sees them explicitly.

## 4. Tests BEYOND the core T1 (also collected, also run)

| test | purpose | PRD ref | gate |
|---|---|---|---|
| `test_daemon_path_emits_latency_line_and_types_nothing` | P1.M4.T1.S3 cross-check: the REAL daemon path (`VoiceTypingDaemon(recorder=rec, backend=_NoopBackend())`) emits the `voice-typing latency:` log line (`daemon._LATENCY_LOG_PREFIX`) AND the no-op backend types nothing (PRD T1 "no typing"). | §4.2 + P1.M4.T1.S3 | greps `r.getMessage().startswith(daemon._LATENCY_LOG_PREFIX)`; asserts `backend.typed == []` |
| `test_lite_feed_audio_utt_simple` | T7(a,b): lite recorder (`cfg_to_kwargs(cfg, lite=True)`) loads ONE model (`assert rec.use_main_model_for_realtime is True`) + finals fuzzy `≥0.70` (lower bar than normal's 0.80 — small.en is the final model). | §4.2ter / T7 | CUDA-gated (`is_cuda_available()`) |
| `test_lite_latency_lower_than_normal` | T7(c): lite final-typed latency is NOT materially higher than normal on `utt_simple`. Best-of-3 min per recorder; `assert lite_best <= normal_best * 1.25` (tolerance band; catches a two-model regression which is ~1.5–2× slower). | §4.2ter / T7 | CUDA-gated (both models on GPU) |

These are in-scope for the run (they're in the same file) but are NOT T1(a)–(e) — they're the T7
lite contract + the daemon-path latency-log cross-check. The report should separate "T1 core (6
cases)" from "T7 lite + daemon-path cross-check (3 cases)".

## 5. Production wiring (the test uses the REAL code paths)

Confirmed by reading `voice_typing/daemon.py` + `voice_typing/cuda_check.py`:
- `daemon.cfg_to_kwargs(cfg)` / `cfg_to_kwargs(cfg, lite=True)` (daemon.py:158) — builds the
  NON-callback kwargs; `lite=True` sets `model=realtime_model_type=lite_model` +
  `use_main_model_for_realtime=True` + the snugger `lite_post_speech_silence_duration`. ✅ used by
  both fixtures.
- `daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder)` (daemon.py:253) — drops unknown
  kwargs (defensive vs RealtimeSTT API drift); logged-and-skipped, never a crash. ✅ used.
- `daemon.cuda_check.is_cuda_available()` (cuda_check.py:105) — `ctranslate2` device count ≥1; gates
  criterion (e) + T7. ✅ used.
- `daemon._LATENCY_LOG_PREFIX = "voice-typing latency:"` (daemon.py:377) — the stable prefix the
  daemon-path test greps. ✅ matches the test's `m.startswith(...)`.
- `recorder`/`lite_recorder` fixtures set `kwargs["use_microphone"] = False` (THE T1 override) +
  wire `on_realtime_transcription_stabilized`/`on_vad_start`/`on_vad_stop` to a `_Collector` +
  `no_log_file=True`. ✅ matches PRD T1 ("construct recorder with `use_microphone=False`, feed WAV
  chunks via `recorder.feed_audio()`").

So the test exercises the **production wiring end-to-end against the REAL recorder** (no mocked
recorder) — this is the integration-grade evidence for AC #1 (transcription accuracy / WhisperX
pause fix), and the real-model backstop for AC #2/#5 (drain, no hallucination) that the mocked
daemon tests (P1.M5.T1.S2) cover logically.

## 6. Skip-guard behavior (degrades gracefully — won't error the suite)

- `pytestmark = pytest.mark.skipif(not _have_wavs(), …)` — skips if any of the 4 WAVs is missing
  (WAVs ARE present here → no skip).
- `recorder` / `lite_recorder` fixtures `_load_deps()` lazily; if `faster_whisper` /
  `RealtimeSTT` / `numpy` / `soundfile` are absent, OR `AudioToTextRecorder(**filtered)`
  construction fails (models/engine missing), the fixture `pytest.skip(...)` — **never errors**.
- Heavy imports are LAZY (in `_load_deps` / the fixture), guarded by `if TYPE_CHECKING:` at module
  top — so collecting this file does NOT pollute `sys.modules` with RealtimeSTT/torch (preserves
  `test_voicectl.py`'s import-purity check during a full `pytest tests/` sweep).

On THIS box: WAVs present + deps present + CUDA present → the run executes the REAL models
(distil-large-v3 + small.en; lite = small.en-only). Expect minutes, not seconds.

## 7. `test_feed_audio_debug.py` — FINDING (stale build artifact)

- **No source file** `tests/test_feed_audio_debug.py` exists.
- A **stale compiled artifact** remains: `tests/__pycache__/test_feed_audio_debug.cpython-312-pytest-9.1.1.pyc` (dated Jul 7).
- The source was deleted at some point; the `.pyc` lingers. `tests/__pycache__` is gitignored, so
  this does not affect the repo, but it's the artifact the contract asked about ("seen in
  __pycache__"). **Report it as: source removed, stale .pyc present, harmless (gitignored), can be
  cleaned with `rm -f tests/__pycache__/test_feed_audio_debug.*` if desired.** Do NOT restore the
  source — it was an exploratory debug script, superseded by the committed `test_feed_audio.py`.

## 8. Run command + AGENTS.md discipline (for the implementing agent)

```bash
cd /home/dustin/projects/voice-typing
# inner GNU timeout 600 (contract value; HEAVY — 2 model loads, minutes) + outer bash-tool timeout > 600 (e.g. 650):
timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q
```
- AGENTS.md Rule 1: inner `timeout` + outer bash-tool `timeout` on EVERY invocation. Exit `124` =
  wedged (a recorder/text() deadlock) → do NOT retry-blind; re-run a SINGLE test under
  `timeout 120 … -k <name> -vv` to localize.
- AGENTS.md: zsh aliases `python`/`pytest` → ALWAYS `.venv/bin/python -m pytest`. Never bare.
- Do NOT add other files (scope boundary): this item runs ONLY `test_feed_audio.py`. The mocked
  daemon/recorder_host set is P1.M5.T1.S2; the pure-Python set is P1.M5.T1.S1.
- Expected outcome (if CUDA healthy): `9 passed` (some may `skip` if a GPU threshold gate fires —
  e.g. criterion (e) / T7 skip on CPU). Record the LIVE per-test result in `test_results_t1.md`.

## 9. Acceptance-criteria evidence (this item is the real-model proof for)

- **#1** (transcription accuracy / WhisperX pause fix) — `test_pause_keeps_both_halves` +
  `test_multi_yields_three_finals` + `test_fuzzy_accuracy[*]` (real models, real feed_audio).
- **#2** (drain / ≥3 s pause loses zero words) — `test_pause_keeps_both_halves` is the real-model
  backstop for the mocked drain tests in P1.M5.T1.S2.
- **#5** (no hallucination) — partial: the feed_audio tests feed REAL silence (the 3 s embedded
  pause, the 1.5 s gaps, the ~1.6 s trailing silence) and assert ONLY the spoken text comes back,
  not silence-hallucinated words. (Full 2-min idle = PRD T4 / P1.M5.T4.)
- **#10** (lite mode) — `test_lite_feed_audio_utt_simple` + `test_lite_latency_lower_than_normal`
  (the real-model T7 contract; P1.M2.T3.S3 already confirmed T7 *unit* coverage).

## 10. What the report (`test_results_t1.md`) MUST contain

1. Asset verification table (4 WAVs + format + toolchain) — §1.
2. Collected count (LIVE: 9) + the contract "8" discrepancy note — §2.
3. T1(a)–(e) coverage matrix with the 2 threshold nuances ((a) cadence 0.8 vs 0.5; (e) latency 2.0
   vs 1.5) flagged explicitly — §3.
4. The 3 beyond-T1 tests identified (daemon-path cross-check + T7 lite pair) — §4.
5. The `test_feed_audio_debug.py` finding (source removed, stale .pyc, harmless) — §7.
6. The LIVE per-test pass/fail/skip from the heavy run (§8 command) — filled at execution.
7. Verdict: coverage = COMPLETE for T1(a)–(e) (all 5 criteria asserted); the 2 threshold nuances
   are documented tolerances, NOT gaps.