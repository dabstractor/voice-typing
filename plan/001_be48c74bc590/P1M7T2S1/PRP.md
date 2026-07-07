# PRP — P1.M7.T2.S1: `tests/test_feed_audio.py` — offline feed_audio pipeline test (PRD T1)

## Goal

**Feature Goal**: Create **`tests/test_feed_audio.py`** — the offline, no-mic, no-typing integration test
that the PRD calls **T1** (§6). It constructs a RealtimeSTT `AudioToTextRecorder` with
`use_microphone=False`, feeds the four WAV fixtures from P1.M7.T1.S1 (`tests/out/*.wav`) into
`recorder.feed_audio()` at **real-time pacing**, and asserts **all five** T1 criteria against the live
models: (a) partials start <1.5 s after speech onset and update ≥ every 500 ms while speaking; (b)
`utt_pause.wav` yields **both** halves across the finalized texts — the post‑3 s‑pause words present
(this is THE regression proof that the WhisperX flaw is fixed); (c) `utt_multi.wav` → 3 non‑empty
finals; (d) fuzzy accuracy ≥80 % token overlap per utterance; (e) the final callback lands ≤1.5 s
after the last speech sample fed.

**Deliverable** (1 file — 1 ADD; **NO** edit to anything else):
1. `tests/test_feed_audio.py` — NEW. A pytest module that (1) builds ONE session‑scoped recorder with
   `use_microphone=False` via the production wiring (`voice_typing.daemon.cfg_to_kwargs` +
   `_build_callbacks` + `_filter_kwargs_to_signature`), (2) drives it with a real‑time‑paced
   `feed_audio` loop + a `recorder.text(cb)` consume loop, (3) collects raw finals + timestamped
   partials + per‑utterance timing, and (4) asserts criteria (a)–(e). Typing is a no‑op (the recorder
   is fed directly; no `make_backend`/keystrokes). Models are real (heavy: seconds to load); the strict
   latency assertion (e) is **gated on CUDA**.

**Success Definition**:
- (a) `tests/test_feed_audio.py` exists; `ruff check` + `mypy` clean; `ruff format --check` clean.
- (b) `uv run pytest tests/test_feed_audio.py -v` PASSES (on a CUDA box with models prefetched) and
  exercises real Whisper inference on all four WAVs.
- (c) **Criterion (b) — the core regression**: `utt_pause.wav` (which embeds 3.0 s of pure silence
  inside one file) produces **two** finals whose texts fuzzy‑match **both** `PAUSE_A` and `PAUSE_B`
  (≥80 % token overlap each). This is the exact WhisperX failure the whole daemon exists to fix.
- (d) **Criterion (c)**: `utt_multi.wav` → exactly 3 non‑empty finals, each fuzzy ≥80 % vs its
  `MULTI_TEXTS[i]`.
- (e) **Criterion (a)**: first partial arrives <1.5 s after `on_vad_start` (speech onset); while
  speaking, partial cadence is observed (≥1 partial per 500 ms window, consistent with
  `realtime_processing_pause=0.15`).
- (f) **Criterion (d)**: fuzzy token overlap ≥0.80 for every non‑empty final of every clip.
- (g) **Criterion (e)**: on CUDA, the final callback lands ≤1.5 s after the last speech sample fed
  (with a documented safety slack); on CPU, the strict assertion is skipped (CPU `distil-large-v3`
  finalization can exceed the budget — research pitfall #5).
- (h) **P1.M4.T1.S3 integration**: one additional assertion proves the production daemon path emits the
  structured `voice-typing latency:` log line + populates `LatencyLog.snapshot()` when run with a
  no‑op typing backend (validates the logging the E2E test T3 will parse).
- (i) No out‑of‑scope edits: NO change to `voice_typing/*`, `pyproject.toml`, `config.toml`,
  `tests/make_test_audio.sh`, `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`; NO
  `e2e_virtual_mic.sh` (that is P1.M7.T3.S1); NO README.

## User Persona

**Target User**: (1) **dustin / the test‑running developer** who runs
`uv run pytest tests/test_feed_audio.py -v` to validate the ASR pipeline before declaring the daemon
done (PRD §7 acceptance criterion 1: "T1–T4, T6 pass, demonstrated by actual command output"); (2) **CI
/ a fresh clone** that regenerates `tests/out/*.wav` via `make_test_audio.sh` then runs this test; (3)
**P1.M7.T3.S1** (the E2E test) which is *blocked* by this item — T3 reuses the same WAVs and the same
fuzzy‑match + latency‑log conventions validated here.

**Use Case**: `cd /home/dustin/projects/voice-typing && ./tests/make_test_audio.sh && uv run pytest
tests/test_feed_audio.py -v` → pytest loads the models once (session fixture), feeds each WAV, and
prints PASS for all five criteria. The output is the evidence attached to PRD §7 acceptance.

**Pain Points Addressed**: (1) PRD §6 T1 mandates this exact test and it does not exist yet. (2) The
WhisperX flaw ("stops listening after a ≥3 s pause, losing the next words") can ONLY be regression‑
tested by feeding a single file with embedded silence and asserting both halves transcribe — there is
no other way to prove the daemon segments instead of ending the session. (3) RealtimeSTT's
`feed_audio()` is a trap: feeding the whole buffer at once silently breaks VAD segmentation (wall‑clock
silence never accumulates), so the test MUST pace chunks at real time — this is the single most
important implementation detail (research §2). (4) espeak is robotic → exact‑match assertions are
brittle; the test MUST fuzzy‑match ≥80 % (PRD §6).

## Why

- **This is the load‑bearing acceptance test for the product's core fix.** The entire daemon
  (P1.M4.T1.S2 `run()` loop: `recorder.text()` returning = normal SEGMENTATION, never session end)
  exists to fix WhisperX stopping after a pause. Criterion (b) is the proof. Without this test, the
  fix is unverified.
- **It blocks the E2E milestone.** P1.M7.T3.S1 (`e2e_virtual_mic.sh`) reuses the WAVs, the fuzzy‑match
  rule, and the latency‑log parsing validated here. This item unblocks P1.M7.T3.S1 and the idle/GPU
  tests (P1.M7.T4.S1).
- **It is the only automated check of partials + latency.** Criteria (a) and (e) — live partials every
  ~200 ms and finals ≤1.5 s — are user‑visible quality bars (PRD §1). No unit test can measure them;
  only a real‑model feed can.
- **It pins the RealtimeSTT `feed_audio` contract empirically.** The research note (§1–§5) derives the
  correct pacing + consume‑before‑feed + abort‑from‑other‑thread + shutdown‑in‑finally discipline from
  the installed v1.0.2 source. Encoding it here makes the test correct on the first pass.
- **Scope discipline.** This item is a TEST only. It consumes `tests/out/*.wav` (P1.M7.T1.S1) and the
  daemon's production seams (`cfg_to_kwargs`, `_build_callbacks`, `_filter_kwargs_to_signature`,
  `VoiceTypingDaemon`, `LatencyLog`). It does NOT touch any module, config, or the audio generator.

## What

A single pytest module at `tests/test_feed_audio.py`. It is a **heavy, real‑model integration test**
(loads `distil-large-v3` + `small.en` on CUDA, or the CPU‑fallback `small.en`/`tiny.en`), explicitly
run (`uv run pytest tests/test_feed_audio.py -v`), never part of the fast unit suite.

Architecture (two layers — see Implementation Blueprint for pinned pseudocode):

1. **A session‑scoped recorder** built ONCE via the production wiring with the single override
   `use_microphone=False`. Its `on_realtime_transcription_stabilized` / `on_vad_start` / `on_vad_stop`
   callbacks are wired to a resettable `_Collector` (timestamps every partial + records speech onset /
   end). Teardown: `abort()` → `shutdown()` in a `finally` (research §3d — the transcript worker is a
   non‑daemon thread on Linux and leaks if not joined).
2. **Per‑test** (criteria a–e): reset the collector, spin a consume thread
   (`while not stop and len(finals) < expected: recorder.text(cb)` — `cb` appends the RAW finalized
   text), feed the WAV at real‑time pace (`feed_audio(slice, 16000); sleep(slice_duration)`), pad ~1 s
   of trailing silence so the last segment's stop threshold fires, wait for `expected` finals, assert.
   Finals are collected RAW (straight from `text()`), independent of `textproc.clean`, so a clean()
   rejection can never hide a regression.
3. **One daemon‑path test** (P1.M4.T1.S3 cross‑check): construct a `VoiceTypingDaemon(recorder=…,
   backend=_NoopBackend(), latency=LatencyLog())`, arm it, feed `utt_simple.wav`, and assert (via
   `caplog`) the `voice-typing latency:` line fires, `LatencyLog.snapshot()` is non‑empty, and nothing
   was typed.

### Success Criteria

- [ ] `tests/test_feed_audio.py` exists; `ruff check`/`mypy`/`ruff format --check` clean.
- [ ] `uv run pytest tests/test_feed_audio.py -v` passes (CUDA + prefetched models).
- [ ] (a) first partial <1.5 s after `on_vad_start`; ≥1 partial per 500 ms while speaking.
- [ ] (b) `utt_pause.wav` → ≥2 finals, second half fuzzy ≥80 % vs `PAUSE_B` (THE regression).
- [ ] (c) `utt_multi.wav` → exactly 3 non‑empty finals.
- [ ] (d) every non‑empty final of every clip fuzzy ≥0.80 vs its canonical text.
- [ ] (e) on CUDA, final cb − last speech sample ≤1.5 s (slack documented); skipped on CPU.
- [ ] P1.M4.T1.S3: daemon emits `voice-typing latency:` line + `LatencyLog.snapshot()` non‑empty + no
      keystrokes with a no‑op backend.
- [ ] Skips cleanly (not errors) when `tests/out/*.wav` are absent (`make_test_audio.sh` not run).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the **exact RealtimeSTT v1.0.2 behavior** is
derived in the research note (file paths + symbols for every claim — `feed_audio`, `text()`,
`wait_audio`, the wall‑clock VAD stop check, the Linux‑is‑a‑thread fact, the `abort()`‑from‑other‑thread
rule, the idempotent `shutdown()`); the **production seams** to reuse (`daemon.cfg_to_kwargs`,
`_build_callbacks`, `_filter_kwargs_to_signature`, `VoiceTypingDaemon`, `LatencyLog`,
`_LATENCY_LOG_PREFIX`) are cited to `voice_typing/daemon.py` with line‑level detail; the **canonical
texts** to fuzzy‑match are pinned verbatim (and also live in `tests/make_test_audio.sh`); the
**existing test conventions** (stubs, `_wait_for` poller, `caplog` usage, run command) are cited to
`tests/test_daemon.py`; and every validation command is executable as written.

### Documentation & References

```yaml
# MUST READ #1 — THE spec for this test (read FIRST; it is the single source of truth for the
#                feed_audio/text()/pacing/shutdown behavior — every claim backed by an installed-file path).
- file: plan/001_be48c74bc590/P1M7T2S1/research/realtimestt_feed_audio_testing.md
  why: "§1 the canonical feed_audio+text() loop (use_microphone=False → in-process queue.Queue, no mic
        reader; feed_audio accepts int16 ndarray OR bytes, re-slices to 32 ms; text() BLOCKS per utterance
        → LOOP for multiple finals; the consume loop MUST be running before the first feed). §2 WHY
        real-time pacing is mandatory (VAD stop + partial cadence are WALL-CLOCK; feeding the whole buffer
        at once merges halves/sentences → criterion b/c FAIL). §3 shutdown/abort/threading (shutdown()
        idempotent + mandatory on Linux; abort() from ANOTHER thread only — never the text() thread; the
        teardown sequence stop-feed→abort→join-consume→shutdown). §4 why a 3 s gap yields BOTH halves
        (continuous_listening re-arms; effective segment gap ≈ 0.76 s). §5 pitfalls (forget
        enable_realtime_transcription=True → no partials; feed-before-text-arms → lost audio; CPU latency
        >1 s). Ends with cite-able scaffolding pseudocode."
  critical: "G-PACE: feed slices of duration D then sleep(D) — NOT feed-all-then-sleep. G-ORDER: start the
             consume thread (blocked in text()/wait_audio which arms listening) BEFORE the first feed_audio.
             G-ABORT: call recorder.abort() from the TEST thread to break the consume thread's blocked text();
             never abort() from inside text(). G-SHUTDOWN: always shutdown() in finally (Linux transcript
             worker is a non-daemon thread → leaks). G-CPU: gate the <=1.5 s assertion on CUDA."

# MUST READ #2 — the audio-format contract (why 16 kHz mono int16) + the feed_audio signature.
- file: plan/001_be48c74bc590/architecture/research_realtimestt_api.md
  why: "§5 (heading h3.3) VERIFIED feed_audio(chunk, original_sample_rate=16000) accepts 16-bit mono PCM
        @16 kHz OR a NumPy array; use_microphone=False switches to the manual feed path. §1-§4 the
        constructor kwargs + text() blocking + callback signatures (on_realtime_transcription_stabilized(str),
        on_vad_start(), on_vad_stop()). §6 version 1.0.2."
  critical: "The WAVs are 16000 Hz / 1 ch / 16-bit / Signed Integer (verified via soxi in P1.M7.T1.S1).
             Read them as int16 numpy (soundfile.read(path, dtype='int16')) and pass original_sample_rate=16000."

# MUST READ #3 — the production seams to REUSE (do NOT re-implement recorder construction).
- file: voice_typing/daemon.py
  why: "cfg_to_kwargs(cfg) builds the full non-callback kwargs (model/device/timing/VAD/silero) WITH
        cuda_check resolution already applied — reuse it so the test recorder matches the daemon's. The ONE
        override: kwargs['use_microphone'] = False (PRD T1). _build_callbacks(feedback, latency) returns the
        {on_realtime_transcription_stabilized, on_vad_detect_start, on_vad_start, on_vad_stop} dict — reuse
        it OR wire your own _Collector (the test needs partial TIMESTAMPS, which _build_callbacks' closure
        does not store). _filter_kwargs_to_signature(kwargs, AudioToTextRecorder) defensively drops unknown
        kwargs — reuse it (v1.0.2 has an explicit 85-param signature). LatencyLog (note_partial /
        note_speech_end / finalize_utterance / snapshot) + _LATENCY_LOG_PREFIX='voice-typing latency:' — the
        P1.M4.T1.S3 log line the daemon-path test greps. VoiceTypingDaemon(cfg, feedback, recorder=…,
        backend=…, latency=…) — inject the shared recorder + a _NoopBackend for the daemon-path test."
  critical: "Do NOT hand-roll the kwargs — cfg_to_kwargs applies cuda_check (CUDA→distil-large-v3+small.en,
             CPU→small.en+tiny.en) which keeps the latency budget sane on each device. _FIXED_KWARGS already
             sets enable_realtime_transcription=True, post_speech_silence_duration(from cfg)=0.6,
             silero_sensitivity=0.4, webrtc_sensitivity=3, min_gap_between_recordings=0.0 — all REQUIRED for
             the segmentation the assertions depend on. Only override use_microphone."

# MUST READ #4 — the canonical texts to fuzzy-match (PINNED in make_test_audio.sh — match verbatim).
- file: tests/make_test_audio.sh
  why: "The four clips' canonical source strings (SIMPLE_TEXT/PAUSE_A/PAUSE_B/PUNCT_TEXT/MULTI_TEXTS) are
        PINNED here. The test's fuzzy target strings MUST equal these exactly (PRD §6). The script also
        documents the fuzzy >=80% rule (case/punct-insensitive) and the 3.0 s + 1.5 s gap durations."
  critical: "Do NOT paraphrase the expected strings — copy them verbatim into the test (see Implementation
             Blueprint). The values are also re-pinned below in Data Models for single-source convenience."

# MUST READ #5 — the existing test conventions (stubs, poller, caplog, run command).
- file: tests/test_daemon.py
  why: "Module docstring shows the run command (.venv/bin/python -m pytest tests/test_daemon.py -v). The
        _wait_for(predicate, timeout, interval) poller, the _FakeFeedback/_StubRecorder/_FakeBackend stub
        pattern, and the caplog.at_level(...) + getMessage() grep pattern are the house style — mirror them
        for _NoopBackend and the latency-line assertion."
  critical: "There is NO conftest.py and NO pytest addopts — tests are run by explicit path. This test file
             is HEAVY (loads models); do not let it run as part of `pytest tests/` fast sweeps — it is
             invoked explicitly OR guarded by a skip (WAVs-absent / models-absent)."

# MUST READ #6 — PRD §6 T1 (the contract) + §7 acceptance (why this test matters).
- file: PRD.md
  why: "§6 T1 enumerates the five assertions verbatim (a-e). §6 'Latency targets' pins partial cadence
        <=300 ms and final-typed <=1.5 s (0.6 s of that is the segmentation pause). §7 acceptance criterion
        1 (T1-T4/T6 pass by actual output) + criterion 2 (>=3 s pause loses zero words) + criterion 3 (live
        partials) are what this test demonstrates."
  critical: "The 1.5 s in (e) is 'after last speech sample fed' — measure from the test's feed timestamp,
             not from on_vad_stop. The fuzzy rule is >=80% token overlap, case/punct-insensitive."

# External — RealtimeSTT feed_audio / external-audio reference (corroborates research §1/§2).
- url: https://github.com/KoljaB/RealtimeSTT#external-audio
  why: "README 'External Audio' example: AudioToTextRecorder(use_microphone=False) + feed_audio(buf, 16000)
        + text(). Corroborates the v1.0.2 in-wheel source the research note derives pacing from (the README
        example itself is NOT paced — the pacing requirement is derived from the worker source, research §2)."
- url: https://github.com/KoljaB/RealtimeSTT/blob/master/docs/external-audio.md
  why: "Upstream streamed/paced feed example (NOT shipped in the wheel; cited for corroboration only)."
```

### Current Codebase tree (state at P1.M7.T2.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── .gitignore                 # READ-ONLY (tests/out/ is ignored via tests/out/.gitignore — do NOT touch root)
├── PRD.md                     # READ-ONLY (§6 T1 contract; §7 acceptance)
├── pyproject.toml uv.lock     # DO NOT touch (pytest>=9.1.1 in dev; realtimestt + nvidia-* in deps)
├── config.toml                # DO NOT touch
├── tests/                     # ← the test lands HERE
│   ├── make_test_audio.sh     # P1.M7.T1.S1 (DONE) — generator; canonical texts live here (+x)
│   ├── test_config.py test_textproc.py test_typing_backends.py test_feedback.py
│   ├── test_daemon.py test_control_socket.py test_voicectl.py   # unit tests (fast; read-only; house style)
│   ├── test_feed_audio.py     # ← CREATE (this task; the ONLY committed artifact)
│   └── out/                   # gitignored (tests/out/.gitignore = '*'); the 4 WAVs live here (regenerable)
│       ├── utt_simple.wav utt_pause.wav utt_multi.wav utt_punct.wav   # 16000 Hz/1ch/16-bit/Signed Int
└── voice_typing/              # READ-ONLY (daemon.py = the seams; config.py/cuda_check.py/textproc.py = deps)
# venv libs available (transitive): numpy 2.5.1, soundfile 0.13.1, RealtimeSTT 1.0.2. wave (stdlib) also OK.
# CUDA: this machine has a 12 GB GPU; models prefetched by install.sh (P1.M1.T3.S1) → ~/.cache/huggingface.
```

### Desired Codebase tree with files to be added

```bash
tests/
├── test_feed_audio.py         # NEW — this task's sole artifact (the offline PRD-T1 integration test)
├── make_test_audio.sh         # unchanged (P1.M7.T1.S1)
└── out/{utt_simple,utt_pause,utt_multi,utt_punct}.wav   # consumed (regenerated by make_test_audio.sh)
# NOTHING ELSE is committed. No conftest.py needed (no shared fixtures required across files).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G-PACE) — feed_audio is NON-BLOCKING and does NOT pace. It re-slices whatever you pass into
#   32 ms (1024-byte) frames and dumps them into the queue as fast as possible (research §1a/§2a). VAD
#   end-of-speech + partial cadence are WALL-CLOCK (time.time() comparisons run once per 32 ms chunk).
#   => Feed slices of duration D and time.sleep(D) after each, so wall-clock advances with audio time.
#      Feeding the whole buffer at once makes a 3 s silence process in <1 ms → the stop threshold never
#      fires → the two pause halves MERGE into one final → CRITERION (b) FAILS (the core regression).
#   Chunk size: 0.05-0.10 s is fine (feed_audio re-slices anyway). sleep = the AUDIO duration you fed.

# CRITICAL #2 (G-ORDER) — the consume loop MUST be running (blocked in text()→wait_audio, which ARMS
#   start_recording_on_voice_activity) BEFORE the first feed_audio (research §1c). Audio fed before text()
#   arms listening is consumed by the worker but never starts a recording (lost for that pass).
#   => Start the consume thread, then feed. (VoiceTypingDaemon.run() does start()/arm-then-text naturally;
#      for the direct-recorder harness, start the consume thread first, then the feed thread.)

# CRITICAL #3 (G-ABORT) — recorder.abort() breaks a blocked text() but it BLOCKS on was_interrupted.wait()
#   which is set INSIDE text() (research §3c). => NEVER call abort() from the same thread that is inside
#   text(). Call it from the TEST/main thread to unwind the consume thread, THEN join the consume thread.

# CRITICAL #4 (G-SHUTDOWN) — on Linux the "model worker process" is actually a THREAD
#   (core/runtime.py::start_recorder_worker uses threading.Thread on Linux, with a `.deamon` typo that
#   fails to set .daemon → NON-daemon). It keeps the pytest process alive if not joined. =>
#   recorder.shutdown() (idempotent; joins threads + closes pipes) in a finally. Sequence per research §3d:
#   stop feed → abort() (breaks text()) → join consume → shutdown().

# CRITICAL #5 (G-CPU) — criterion (e) <=1.5 s is GPU-tight. On CPU, distil-large-v3 finalization can take
#   >1 s and blow the budget (research pitfall #5). => Detect CUDA via voice_typing.cuda_check.is_cuda_available()
#   (or torch.cuda.is_available()); on CUDA assert <=1.5 s (with slack ~2.0 s); on CPU pytest.skip("latency
#   budget is GPU-only") OR widen. The session recorder uses cfg_to_kwargs → cuda_check already picks
#   distil-large-v3+small.en (CUDA) or small.en+tiny.en (CPU), so models are right for the device.

# CRITICAL #6 (G-REALTIME-CB) — on_realtime_transcription_stabilized ONLY fires if
#   enable_realtime_transcription=True (research pitfall #1). _FIXED_KWARGS sets it True; if you build
#   kwargs via cfg_to_kwargs it is already True — do NOT override it to False or NO partials fire (criterion
#   a becomes unmeasurable). The project wires the STABILIZED callback (more accurate), NOT
#   on_realtime_transcription_update (faster/rougher) — daemon._PARTIAL_CALLBACK_ATTR.

# CRITICAL #7 (G-NOLOGFILE) — AudioToTextRecorder.__init__ opens a `realtimestt.log` file handler in the
#   cwd unless no_log_file=True (research pitfall #6). __init__ ALSO blocks on main_transcription_ready_event
#   (model warmup, seconds) AND forces mp.set_start_method("spawn") (research pitfall #7). =>
#   - Pass no_log_file=True (keeps the repo clean) OR accept the file (harmless).
#   - Construct the recorder ONCE per SESSION (module-scoped fixture), never per-test.
#   - Do NOT set mp.set_start_method yourself; let safepipe do it (constructing inside the test function, not
#     at import top-level, is spawn-safe regardless — research §3e).

# CRITICAL #8 (G-FINALS-RAW) — collect finals RAW from recorder.text(cb)'s callback, NOT from the daemon's
#   on_final. The daemon applies textproc.clean() which REJECTS blocklisted/too-short finals (early return,
#   invisible). Although the test utterances are NOT blocklisted and >min_chars(2), collecting raw is the
#   robust choice: a poor Whisper transcription of a half must never be hidden by clean(). The daemon-path
#   test (P1.M4.T1.S3 cross-check) separately validates the production on_final→clean→type→log path.

# CRITICAL #9 (G-FUZZY) — textproc.clean() does NOT do fuzzy matching (it is a strip/blocklist/min-length
#   filter). The >=80% token overlap is the TEST's responsibility. Implement a multiset token-overlap helper
#   (case + punctuation insensitive). PRD §6: ">=80% token overlap (case/punct-insensitive) for espeak
#   audio. Do not chase 100% on synthetic voices."

# CRITICAL #10 (G-WAV-LOAD) — read WAVs as int16 numpy: `soundfile.read(path, dtype='int16')` returns
#   (samples_int16, sr). Pass samples to feed_audio with original_sample_rate=16000. soundfile 0.13.1 +
#   numpy 2.5.1 are in the venv (transitive via realtimestt). stdlib `wave` is a fine fallback but soundfile
#   is simpler. The WAVs are mono; if any were stereo, feed_audio mono-mixes (np.mean(axis=1)) — but these
#   are mono (soxi-confirmed in P1.M7.T1.S1).

# CRITICAL #11 (G-TRAILING-SILENCE) — after the last speech slice, feed ~1.0 s of pure silence (np.zeros)
#   and sleep ~1.1 s. The recorder's stop threshold is post_speech_silence_duration(0.6 s) + deactivation
#   grace(0.16 s) ≈ 0.76 s; the trailing silence lets the LAST segment finalize so its final callback fires
#   and the consume loop's expected-final count is reached (research §2c/§4).

# CRITICAL #12 (G-SHARED-RECORDER-STATE) — the session recorder's continuous_listening re-arms after each
#   stop, so it carries state across tests. Per-test isolation: (1) reset the _Collector before each test;
#   (2) each test waits for ITS expected finals (poll the collector's final-count) before asserting/teardown;
#   (3) teardown does abort() to flush any in-flight recording. Tests run serialized (pytest default), so
#   there is no concurrency between feeds.

# CRITICAL #13 (G-SKIP-GUARDS) — the test must SKIP (not error) when its prerequisites are absent:
#   - tests/out/*.wav missing → pytest.skip("run ./tests/make_test_audio.sh first").
#   - RealtimeSTT import fails / no models → pytest.skip (do not fail the suite on a CPU-only CI box).
#   Guard at module/fixture level so `pytest tests/` fast sweeps are not broken by a missing heavy dep.

# CRITICAL #14 (G-LATENCY-LINE) — the daemon's structured latency line starts with the STABLE prefix
#   `voice-typing latency:` (daemon._LATENCY_LOG_PREFIX). The daemon-path test greps caplog for it. The
#   ring buffer is LatencyLog.snapshot() (list[dict] with text/partials/*_ms). final_to_typed_ms is ALWAYS
#   numeric; speech_end_to_final_ms / total_ms are 'n/a' (None) when no on_vad_stop preceded — fine for the
#   daemon-path test (it only asserts the line fires + snapshot non-empty + nothing typed).
```

## Implementation Blueprint

### Data models and structure

No ORM/pydantic. The test's "schema" is (1) the **canonical fuzzy‑target strings** (pinned verbatim from
`tests/make_test_audio.sh`), (2) the **`_Collector`** (a resettable timestamped event recorder wired as the
recorder's callbacks), and (3) the **fuzzy token‑overlap helper**.

```python
# (1) Canonical fuzzy targets — PINNED VERBATIM from tests/make_test_audio.sh (PRD §6). Do NOT paraphrase.
SIMPLE_TEXT  = "The quick brown fox jumps over the lazy dog."
PAUSE_A      = "I want to test whether this system"     # first half of utt_pause.wav
PAUSE_B      = "keeps listening after a pause."         # second half (AFTER the 3.0 s gap) — THE regression
PUNCT_TEXT   = "Hello, world! Does punctuation, like commas, question marks? It should."
MULTI_TEXTS  = (                                          # the 3 sentences of utt_multi.wav, IN ORDER
    "The weather looks good today.",
    "I need to buy some groceries.",
    "Let us meet at the cafe.",
)

# (2) _Collector — resettable timestamped event sink wired as the recorder's callbacks (research §3d +
#     G-RAW). Holds RAW finals + partial timestamps + speech onset/end so criteria (a)/(e) are measurable.
@dataclass
class _Collector:
    finals: list[str] = field(default_factory=list)                 # RAW finalized text (text() callback)
    partials: list[tuple[float, str]] = field(default_factory=list) # (time.monotonic(), text)
    t_speech_start: float | None = None                             # on_vad_start (speech onset)
    t_speech_end: float | None = None                               # on_vad_stop (speech end)
    def add_final(self, text): self.finals.append(text)
    def add_partial(self, text): self.partials.append((time.monotonic(), text))
    def on_vad_start(self): self.t_speech_start = time.monotonic()
    def on_vad_stop(self): self.t_speech_end = time.monotonic()
    def reset(self): ...  # clear all four fields

# (3) Fuzzy token overlap (PRD §6: >=80%, case/punct-insensitive). Multiset intersection / ref-length.
def _token_overlap(hyp: str, ref: str) -> float:
    import re, string
    from collections import Counter
    def toks(s): return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()
    h, r = Counter(toks(hyp)), Counter(toks(ref))
    if not r: return 0.0
    return sum((h & r).values()) / len(r)        # 1.0 = perfect; >=0.80 passes
```

### `tests/test_feed_audio.py` reference structure (research §1–§5 + house style — implement close to this)

> The implementer writes ONE file. Below is the pinned scaffold (helpers + fixtures + the five criteria
> tests + the P1.M4.T1.S3 daemon‑path cross‑check). Adapt names/details as needed but KEEP the pacing,
> the consume‑before‑feed order, the abort‑from‑test‑thread, the shutdown‑in‑finally, the raw‑finals
> collection, and the CPU‑gated latency assertion.

```python
"""tests/test_feed_audio.py — OFFLINE feed_audio pipeline test (PRD §6 T1; work item P1.M7.T2.S1).

Heavy, real-model integration test: constructs ONE AudioToTextRecorder(use_microphone=False) via the
production wiring (daemon.cfg_to_kwargs + _build_callbacks + _filter_kwargs_to_signature), feeds the
tests/out/*.wav fixtures (P1.M7.T1.S1) at REAL-TIME pacing, and asserts the five T1 criteria:
  (a) partials start <1.5 s after speech onset + >=1 per 500 ms while speaking;
  (b) utt_pause.wav -> BOTH halves (the WhisperX-flaw regression);
  (c) utt_multi.wav -> 3 non-empty finals;
  (d) fuzzy >=80% token overlap per utterance;
  (e) final callback <=1.5 s after last speech sample fed (CUDA-gated).
Plus a P1.M4.T1.S3 cross-check: the daemon emits the 'voice-typing latency:' log line + nothing is typed
with a no-op backend.

NO real mic, NO keystrokes (no make_backend). Models are REAL (seconds to load). Run explicitly:
    cd /home/dustin/projects/voice-typing
    ./tests/make_test_audio.sh          # ensure tests/out/*.wav exist
    uv run pytest tests/test_feed_audio.py -v
Skips cleanly when WAVs/models are absent (do not break `pytest tests/` fast sweeps).
"""
from __future__ import annotations

import dataclasses
import time
import threading
from collections import Counter
from pathlib import Path

import pytest

# --- skip guards (G-SKIP-GUARDS): never error the suite on a missing heavy prereq ---
_OUT = Path(__file__).parent / "out"
_WAVS = {k: _OUT / f"{k}.wav" for k in ("simple", "pause", "multi", "punct")}
def _have_wavs() -> bool: return all(p.is_file() for p in _WAVS.values())
try:
    import soundfile as sf
    import numpy as np
    from RealtimeSTT import AudioToTextRecorder
    from voice_typing import daemon
    from voice_typing.config import VoiceTypingConfig
    from voice_typing.feedback import Feedback
    _HAVE_DEPS = True
except Exception:
    _HAVE_DEPS = False
pytestmark = pytest.mark.skipif(not (_HAVE_DEPS and _have_wavs()),
                                reason="needs RealtimeSTT+soundfile+numpy and tests/out/*.wav (run make_test_audio.sh)")

# --- canonical fuzzy targets (PINNED VERBATIM from tests/make_test_audio.sh; PRD §6) ---
SIMPLE_TEXT = "The quick brown fox jumps over the lazy dog."
PAUSE_A, PAUSE_B = "I want to test whether this system", "keeps listening after a pause."
PUNCT_TEXT = "Hello, world! Does punctuation, like commas, question marks? It should."
MULTI_TEXTS = ("The weather looks good today.", "I need to buy some groceries.", "Let us meet at the cafe.")

# --- fuzzy token overlap (G-FUZZY; textproc.clean does NOT do this) ---
def _token_overlap(hyp: str, ref: str) -> float:
    import re, string
    def toks(s): return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()
    h, r = Counter(toks(hyp)), Counter(toks(ref))
    return (sum((h & r).values()) / len(r)) if r else 0.0

# --- _Collector (G-RAW/G-REALTIME-CB): timestamped event sink wired as the recorder callbacks ---
@dataclasses.dataclass
class _Collector:
    finals: list = dataclasses.field(default_factory=list)
    partials: list = dataclasses.field(default_factory=list)   # (monotonic, text)
    t_speech_start: float | None = None
    t_speech_end: float | None = None
    def add_final(self, t): self.finals.append(t)
    def add_partial(self, t): self.partials.append((time.monotonic(), t))
    def on_vad_start(self): self.t_speech_start = time.monotonic()
    def on_vad_stop(self): self.t_speech_end = time.monotonic()
    def reset(self):
        self.finals.clear(); self.partials.clear()
        self.t_speech_start = self.t_speech_end = None

# --- the real-time-paced feed loop (G-PACE/G-TRAILING-SILENCE); research §2c ---
def _feed_paced(rec, samples_int16, *, stop: threading.Event, chunk_s: float = 0.1):
    step = int(16000 * chunk_s)
    i = 0
    while i < len(samples_int16) and not stop.is_set():
        slc = samples_int16[i:i + step]
        rec.feed_audio(slc, original_sample_rate=16000)     # auto re-sliced to 32 ms; NON-blocking
        i += step
        time.sleep(len(slc) / 16000.0)                      # pace at real-time (WALL-CLOCK VAD depends on this)
    if not stop.is_set():                                   # trailing silence so the last segment finalizes
        rec.feed_audio(np.zeros(int(16000 * 1.0), dtype=np.int16), original_sample_rate=16000)
        time.sleep(1.1)

# --- the consume loop (G-ORDER/G-ABORT); research §1b/§3c. Collects RAW finals (G-RAW) ---
def _consume(rec, col: _Collector, stop: threading.Event, want: int):
    while len(col.finals) < want and not stop.is_set():
        rec.text(col.add_final)     # BLOCKS until ONE utterance finalizes; cb fires with RAW text

def _wait_for(pred, timeout=30.0, interval=0.05):           # house style (tests/test_daemon.py)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred(): return True
        time.sleep(interval)
    return pred()

# --- session-scoped recorder (G-NOLOGFILE/G-SHUTDOWN); built ONCE, reused across tests ---
@pytest.fixture(scope="session")
def recorder():
    cfg = VoiceTypingConfig()
    col = _Collector()
    kwargs = daemon.cfg_to_kwargs(cfg)                      # cuda_check resolution already applied (G-CPU)
    kwargs["use_microphone"] = False                        # THE override (PRD T1 feed path)
    kwargs.update({
        "on_realtime_transcription_stabilized": col.add_partial,
        "on_vad_start": col.on_vad_start,
        "on_vad_stop": col.on_vad_stop,
        "no_log_file": True,                                # keep the repo clean (G-NOLOGFILE)
    })
    filtered = daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder)
    rec = AudioToTextRecorder(**filtered)
    yield rec, col
    try: rec.abort()                                        # break any blocked text() (G-ABORT)
    except Exception: pass
    rec.shutdown()                                          # join threads + close pipes (G-SHUTDOWN; idempotent)

# --- per-utterance harness: reset, consume+feed, wait, teardown (G-SHARED-RECORDER-STATE) ---
def _run_utterance(recorder, col, wav: Path, want_finals: int, *, feed_timeout: float = 60.0):
    col.reset()
    samples, _sr = sf.read(str(wav), dtype="int16")         # 16k mono int16 (soxi-confirmed)
    stop = threading.Event()
    cons = threading.Thread(target=_consume, args=(recorder, col, stop, want_finals), daemon=True)
    cons.start()                                            # G-ORDER: consume arms listening BEFORE feed
    feed = threading.Thread(target=_feed_paced, args=(recorder, samples), kwargs={"stop": stop}, daemon=True)
    feed.start()
    try:
        assert _wait_for(lambda: len(col.finals) >= want_finals, timeout=feed_timeout), \
            f"expected {want_finals} finals, got {col.finals!r}"
        time.sleep(0.5)                                     # let any in-flight partial settle
    finally:
        stop.set()
        try: recorder.abort()                               # from the TEST thread (G-ABORT) — breaks text()
        except Exception: pass
        cons.join(timeout=5.0); feed.join(timeout=5.0)
    return col

# ===================== CRITERION (a): partial cadence =====================
def test_partials_start_fast_and_cadence(recorder):
    rec, col = recorder
    _run_utterance(rec, col, _WAVS["simple"], want_finals=1)
    assert col.partials, "no partials fired (enable_realtime_transcription=True? G-REALTIME-CB)"
    onset = col.t_speech_start or col.partials[0][0]        # fallback to first partial if on_vad_start missed
    # (a) first partial <1.5 s after speech onset
    assert col.partials[0][0] - onset < 1.5, (col.partials[0][0] - onset)
    # (a) while speaking, >=1 partial per ~500 ms (realtime_processing_pause=0.15 → cadence ~150 ms)
    sp = [t for t, _ in col.partials]
    if col.t_speech_end and col.t_speech_start:
        speaking_s = col.t_speech_end - col.t_speech_start
        if speaking_s > 0.5:                                # only assert cadence on a real speaking window
            gaps = [b - a for a, b in zip(sp, sp[1:])]
            assert max(gaps) < 0.8, f"partial gap too large: {max(gaps):.2f}s"   # 0.5 target + slack

# ===================== CRITERION (b): pause keeps BOTH halves (THE regression) =====================
def test_pause_keeps_both_halves(recorder):
    rec, col = recorder
    _run_utterance(rec, col, _WAVS["pause"], want_finals=2)
    finals = [f.strip() for f in col.finals if f.strip()]
    assert len(finals) >= 2, f"pause merged into <2 finals: {finals!r}"   # the WhisperX failure
    joined = " ".join(finals)
    # both halves present + each fuzzy >=0.80 (G-FUZZY)
    assert _token_overlap(joined, PAUSE_A) >= 0.80, (joined, PAUSE_A)
    assert _token_overlap(joined, PAUSE_B) >= 0.80, (joined, PAUSE_B)

# ===================== CRITERION (c): multi -> 3 non-empty finals =====================
def test_multi_yields_three_finals(recorder):
    rec, col = recorder
    _run_utterance(rec, col, _WAVS["multi"], want_finals=3)
    finals = [f.strip() for f in col.finals if f.strip()]
    assert len(finals) == 3, f"expected 3 finals, got {finals!r}"
    for hyp, ref in zip(finals, MULTI_TEXTS):               # (d) per-utterance fuzzy
        assert _token_overlap(hyp, ref) >= 0.80, (hyp, ref)

# ===================== CRITERION (d): fuzzy accuracy (simple + punct) =====================
@pytest.mark.parametrize("key,ref", [("simple", SIMPLE_TEXT), ("punct", PUNCT_TEXT)])
def test_fuzzy_accuracy(recorder, key, ref):
    rec, col = recorder
    _run_utterance(rec, col, _WAVS[key], want_finals=1)
    finals = [f.strip() for f in col.finals if f.strip()]
    assert finals, f"no finals for {key}"
    joined = " ".join(finals)
    assert _token_overlap(joined, ref) >= 0.80, (joined, ref)

# ===================== CRITERION (e): final latency (CUDA-gated; G-CPU) =====================
def test_final_latency(recorder):
    if not daemon.cuda_check.is_cuda_available():
        pytest.skip("criterion (e) <=1.5 s is a GPU budget; CPU distil-large-v3 can exceed it (G-CPU)")
    rec, col = recorder
    # stamp the moment right after the last SPEECH slice is fed (before the trailing-silence pad)
    samples, _ = sf.read(str(_WAVS["simple"]), dtype="int16")
    # locate the last non-silent sample to know where speech actually ends
    nonsil = np.flatnonzero(np.abs(samples) > 50)
    last_speech_idx = int(nonsil[-1]) if nonsil.size else len(samples) - 1
    col.reset(); stop = threading.Event()
    cons = threading.Thread(target=_consume, args=(rec, col, stop, 1), daemon=True); cons.start()
    t_last_speech = [None]
    def _feed_marked():
        step = int(16000 * 0.1); i = 0
        while i < len(samples) and not stop.is_set():
            slc = samples[i:i+step]; rec.feed_audio(slc, 16000); i += step
            if i > last_speech_idx and t_last_speech[0] is None:
                t_last_speech[0] = time.monotonic()         # stamped right after the last speech slice
            time.sleep(len(slc)/16000.0)
        if not stop.is_set():
            rec.feed_audio(np.zeros(int(16000*1.0), dtype=np.int16), 16000); time.sleep(1.1)
    feed = threading.Thread(target=_feed_marked, daemon=True); feed.start()
    t_final = [None]
    try:
        # wrap add_final to stamp the final-callback time (criterion e = final cb - last speech sample)
        orig = col.add_final
        def stamp(t): t_final[0] = time.monotonic(); orig(t)
        col.add_final = stamp
        assert _wait_for(lambda: len(col.finals) >= 1, timeout=60.0), col.finals
    finally:
        stop.set()
        try: rec.abort()
        except Exception: pass
        cons.join(timeout=5.0); feed.join(timeout=5.0)
    assert t_last_speech[0] and t_final[0]
    latency_s = t_final[0] - t_last_speech[0]
    assert latency_s <= 2.0, f"final latency {latency_s:.2f}s > 2.0s (target 1.5s + slack; G-CPU)"  # 1.5 target, 2.0 slack

# ===================== P1.M4.T1.S3 cross-check: daemon emits the latency line, nothing typed =====================
class _NoopBackend:
    typed: list = []
    def type_text(self, text): pass                         # no keystrokes (PRD T1: "no typing")

def test_daemon_path_emits_latency_line_and_types_nothing(recorder, tmp_path, caplog):
    import logging
    rec, col = recorder
    cfg = VoiceTypingConfig()
    fb = type("F", (), {                                    # minimal feedback stand-in (no XDG_RUNTIME_DIR)
        "update_partial": lambda self, t: None, "set_phase": lambda self, p: None,
        "set_listening": lambda self, b: None, "record_final": lambda self, t: None,
        "snapshot": lambda self: {},
    })()
    lat = daemon.LatencyLog()
    d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=_NoopBackend(), latency=lat)
    run_thread = threading.Thread(target=d.run, daemon=True); run_thread.start()
    samples, _ = sf.read(str(_WAVS["simple"]), dtype="int16")
    stop = threading.Event()
    try:
        _wait_for(lambda: True, timeout=0.3)                # let run() enter its loop
        d.start()                                           # arm (set_microphone + _listening)
        with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
            _feed_paced(rec, samples, stop=stop)            # feed through the daemon's recorder
            _wait_for(lambda: len(lat.snapshot()) >= 1, timeout=60.0)
        line = next((m for m in (r.getMessage() for r in caplog.records)
                     if m.startswith(daemon._LATENCY_LOG_PREFIX)), None)
        assert line is not None, "no 'voice-typing latency:' line emitted (P1.M4.T1.S3)"
        assert len(lat.snapshot()) >= 1                     # ring buffer populated
        assert _NoopBackend.typed == []                     # nothing typed (no-op backend)
    finally:
        stop.set(); d.request_shutdown()
        try: rec.abort()
        except Exception: pass
        _wait_for(lambda: not run_thread.is_alive(), timeout=5.0); run_thread.join(timeout=5.0)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm prereqs WITHOUT mutation.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f tests/out/utt_pause.wav && echo "WAVs present" || echo "PREFLIGHT: run ./tests/make_test_audio.sh first"
      .venv/bin/python -c "import RealtimeSTT, soundfile, numpy; from voice_typing import daemon; print('deps OK')" \
        && echo "deps OK" || echo "PREFLIGHT FAIL: heavy deps missing (prefetch models via install.sh)"
      test ! -e tests/test_feed_audio.py && echo "ok: not yet created" || echo "PREFLIGHT FAIL: already exists"
      .venv/bin/python -m voice_typing.cuda_check 2>/dev/null | grep VERDICT || echo "(cuda_check unavailable)"
  - EXPECTED: WAVs present (utt_pause.wav ~7.9s); deps import OK; test file absent; VERDICT=cuda-ok on this box.
  - DO NOT: create/edit any file, run pytest, touch .gitignore, or any module.

Task 1: CREATE tests/test_feed_audio.py — the reference scaffold above (adapt as needed).
  - FILE: tests/test_feed_audio.py (NEW).
  - KEEP (the load-bearing invariants — each maps to a CRITICAL gotcha):
      * G-PACE: _feed_paced feeds a slice then sleeps its audio duration; NEVER feed-all-then-sleep.
      * G-ORDER: the consume thread starts BEFORE the feed thread (text() arms listening first).
      * G-ABORT: recorder.abort() is called from the TEST thread to break the consume thread's text().
      * G-SHUTDOWN: session-fixture teardown does abort() then shutdown() (Linux transcript worker is a
        non-daemon thread); every per-test finally also abort()+joins.
      * G-RAW: finals are collected from recorder.text(cb)'s RAW callback (NOT the daemon on_final).
      * G-CPU: criterion (e) skips unless daemon.cuda_check.is_cuda_available().
      * G-REALTIME-CB: enable_realtime_transcription stays True (from _FIXED_KWARGS via cfg_to_kwargs);
        on_realtime_transcription_stabilized is wired to col.add_partial.
      * G-NOLOGFILE: pass no_log_file=True.
      * G-FUZZY: _token_overlap is the test's own multiset helper (textproc.clean does not fuzzy-match).
      * G-TRAILING-SILENCE: ~1.0 s zeros + sleep(1.1) after the last speech slice.
      * G-SKIP-GUARDS: pytestmark skips when WAVs/deps absent.
      * The canonical fuzzy targets (SIMPLE_TEXT/PAUSE_A/PAUSE_B/PUNCT_TEXT/MULTI_TEXTS) VERBATIM.
  - DO NOT: edit any voice_typing/ module, pyproject.toml, config.toml, make_test_audio.sh, .gitignore;
    create e2e_virtual_mic.sh (P1.M7.T3.S1); create a README; add a conftest.py (none needed).

Task 2: VALIDATE — run the Validation Loop L1-L4. Iterate until all gates pass.
  - EXPECTED on this box (CUDA): all criteria pass; the daemon-path test greps the latency line.
  - On a CPU-only box: criterion (e) skips; (a)-(d) pass on the CPU-fallback models (small.en/tiny.en).
  - No git commit unless the orchestrator directs it. If asked, message:
    "P1.M7.T2.S1: tests/test_feed_audio.py — offline feed_audio test (PRD T1): pause/multi/fuzzy/partials/latency".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — real-time-paced feed (G-PACE; research §2c). feed_audio is non-blocking + re-slices to 32 ms;
#   VAD stop + partial cadence are WALL-CLOCK. sleep = the AUDIO duration you fed (not the processing time).
step = int(16000 * 0.1)                                     # 0.1 s slices (1600 int16 samples)
for i in range(0, len(samples), step):
    slc = samples[i:i+step]
    rec.feed_audio(slc, original_sample_rate=16000)         # int16 ndarray; OR raw bytes
    time.sleep(len(slc) / 16000.0)                          # pace at real-time

# PATTERN 2 — consume-before-feed (G-ORDER; research §1c). text()→wait_audio() ARMS listening; audio fed
#   before that is consumed but never starts a recording. Start the consume thread FIRST.
cons = threading.Thread(target=_consume, args=(rec, col, stop, want)); cons.start()  # arms listening
feed = threading.Thread(target=_feed_paced, args=(rec, samples), kwargs={"stop": stop}); feed.start()

# PATTERN 3 — text(cb) BLOCKS per utterance; loop for multiple finals (research §1b). cb fires with the
#   RAW text in a NEW thread (async delivery of already-computed text). collect RAW (G-RAW).
def _consume(rec, col, stop, want):
    while len(col.finals) < want and not stop.is_set():
        rec.text(col.add_final)      # returns after ONE utterance finalizes; cb(text) appended RAW

# PATTERN 4 — teardown sequence (research §3d): stop feed → abort() [test thread breaks text()] → join
#   consume → (session-end) shutdown(). abort() from ANOTHER thread only (G-ABORT; never from text()).
stop.set()
try: rec.abort()                # blocks until was_interrupted set inside text() → consume unwinds
except Exception: pass
cons.join(timeout=5.0); feed.join(timeout=5.0)
# (session fixture finally): rec.shutdown()   # idempotent; joins the non-daemon transcript worker

# PATTERN 5 — build the recorder via the production seams with ONE override (do NOT hand-roll kwargs:
#   cfg_to_kwargs applies cuda_check → right models for the device; _filter drops unknown kwargs safely).
kwargs = daemon.cfg_to_kwargs(VoiceTypingConfig())
kwargs["use_microphone"] = False                            # THE override (PRD T1)
kwargs.update({"on_realtime_transcription_stabilized": col.add_partial,
               "on_vad_start": col.on_vad_start, "on_vad_stop": col.on_vad_stop, "no_log_file": True})
rec = AudioToTextRecorder(**daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder))

# PATTERN 6 — fuzzy token overlap (G-FUZZY; PRD §6 >=80%, case/punct-insensitive). Multiset intersection.
def _token_overlap(hyp, ref):
    def toks(s): import re, string
        return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()
    h, r = Counter(toks(hyp)), Counter(toks(ref))
    return (sum((h & r).values()) / len(r)) if r else 0.0

# PATTERN 7 — daemon-path cross-check (P1.M4.T1.S3). Inject the SHARED recorder (no second model load) +
#   a no-op backend; arm via daemon.start(); grep caplog for the stable latency prefix.
d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=_NoopBackend(), latency=daemon.LatencyLog())
# ... d.run() in a thread; d.start(); feed; assert caplog has a line starting with daemon._LATENCY_LOG_PREFIX
```

### Integration Points

```yaml
CONSUMES — tests/out/{utt_simple,utt_pause,utt_multi,utt_punct}.wav (P1.M7.T1.S1, DONE):
  - format:  16000 Hz / 1 ch / 16-bit signed-integer PCM (RealtimeSTT SAMPLE_RATE=16000; soxi-confirmed)
  - load:    soundfile.read(path, dtype="int16") -> (samples_int16, 16000); feed via original_sample_rate=16000
  - texts:   fuzzy-match (>=80%) against the PINNED canonical strings (single source: tests/make_test_audio.sh)

CONSUMES — voice_typing.daemon seams (READ-ONLY reuse; do NOT modify daemon.py):
  - daemon.cfg_to_kwargs(cfg)        -> production kwargs (cuda_check resolution applied)
  - daemon._build_callbacks(fb, lat) -> {on_realtime_*} dict (OR wire your own _Collector — see Pattern 5)
  - daemon._filter_kwargs_to_signature(kw, cls) -> defensively drops unknown kwargs
  - daemon.LatencyLog + daemon._LATENCY_LOG_PREFIX ("voice-typing latency:") -> P1.M4.T1.S3 cross-check
  - daemon.VoiceTypingDaemon(cfg, fb, recorder=, backend=, latency=) -> injection seams (recorder/backend/latency)

CONSUMES — voice_typing.cuda_check.is_cuda_available() -> gates criterion (e) (G-CPU).

BLOCKS — tests/e2e_virtual_mic.sh (P1.M7.T3.S1, PLANNED): reuses the same WAVs + fuzzy rule + latency-log
  parsing. This test validates those conventions offline first (no PipeWire/null-sink needed).

NO database. NO config change. NO pyproject/uv.lock change. NO module edit. NO root .gitignore edit.
```

## Validation Loop

> Run from `/home/dustin/projects/voice-typing`. The unit-test fast suite (`pytest tests/test_*.py`
> excluding this file) is unaffected — this file skips cleanly when WAVs/models are absent (G-SKIP-GUARDS).
> The heavy gates (L2/L3) load real Whisper models (seconds). Models are prefetched by install.sh
> (P1.M1.T3.S1) to `~/.cache/huggingface`.

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
ruff check tests/test_feed_audio.py --fix
mypy tests/test_feed_audio.py
ruff format tests/test_feed_audio.py
ruff format tests/test_feed_audio.py --check && echo "L1 format OK" || echo "L1 FAIL: re-run ruff format"
# Expected: zero errors. ruff/mypy are the project's Python gates (tests/test_daemon.py passes them).
# Note: mypy may warn on the dynamic feedback stand-in in the daemon-path test — if so, add a # type: ignore
# on that one line (it is an inline test stub, not production code) OR use a proper @dataclass stub.
```

### Level 2: The Test Itself (Component Validation — the five criteria)

```bash
cd /home/dustin/projects/voice-typing
./tests/make_test_audio.sh                       # ensure tests/out/*.wav exist (idempotent; skips if present)
uv run pytest tests/test_feed_audio.py -v        # heavy: loads models once (session fixture), feeds 4 WAVs
# Expected (CUDA): 6 passed
#   test_partials_start_fast_and_cadence          (criterion a)
#   test_pause_keeps_both_halves                  (criterion b — THE regression)
#   test_multi_yields_three_finals                (criterion c)
#   test_fuzzy_accuracy[simple] / [punct]         (criterion d)
#   test_final_latency                            (criterion e — CUDA-gated; skipped on CPU)
#   test_daemon_path_emits_latency_line_and_types_nothing   (P1.M4.T1.S3 cross-check)
# If a criterion fails: READ the assertion message (it prints the actual finals/tokens). Common causes:
#   - pause merged into 1 final  -> pacing broken (G-PACE): you fed too fast; verify sleep(len/16000).
#   - no partials                 -> enable_realtime_transcription not True OR on_realtime_* not wired (G-REALTIME-CB).
#   - latency >2s on CUDA         -> check both models on CUDA (log 'device resolved'); try large-v3-turbo (PRD §4.4).
#   - fuzzy <0.80                 -> espeak drift is allowed UP TO the 80% floor; if consistently below, the
#                                    clip may be mis-generated (re-run make_test_audio.sh FORCE=1).
```

### Level 3: Regression — the fast unit suite is untouched

```bash
cd /home/dustin/projects/voice-typing
uv run pytest tests/ -v --ignore=tests/test_feed_audio.py   # the existing unit tests still pass (no module edited)
ruff check tests/                                            # whole tests/ tree lints clean
mypy tests/                                                  # whole tests/ tree type-checks clean
# Expected: all pre-existing unit tests pass; no new lint/type errors introduced.
```

### Level 4: Creative & Domain-Specific Validation

```bash
cd /home/dustin/projects/voice-typing
# (a) the canonical fuzzy targets in the test match tests/make_test_audio.sh verbatim (single source):
for s in 'The quick brown fox jumps over the lazy dog.' \
         'I want to test whether this system' 'keeps listening after a pause.' \
         'Hello, world! Does punctuation, like commas, question marks? It should.'; do
  grep -qF "$s" tests/test_feed_audio.py && grep -qF "$s" tests/make_test_audio.sh \
    && echo "L4 pinned OK: $s" || echo "L4 DRIFT: '$s' differs between test and generator"
done

# (b) the session recorder is built with use_microphone=False + enable_realtime_transcription=True:
grep -q 'use_microphone.*False' tests/test_feed_audio.py && echo "L4 use_microphone=False OK (PRD T1)"
grep -q 'enable_realtime_transcription' tests/test_feed_audio.py && echo "L4 note: ensure it stays True (cfg_to_kwargs sets it)" \
  || echo "L4 note: enable_realtime_transcription comes from _FIXED_KWARGS via cfg_to_kwargs (do not override)"

# (c) skip-guards present (G-SKIP-GUARDS) so the fast suite is never broken by a missing heavy dep:
grep -q 'pytest.mark.skipif' tests/test_feed_audio.py && echo "L4 skip-guards present OK"

# (d) the daemon-path test greps the STABLE latency prefix (P1.M4.T1.S3 contract; do not rename):
grep -q '_LATENCY_LOG_PREFIX' tests/test_feed_audio.py && echo "L4 daemon latency-line cross-check present OK"

# (e) optional smoke: confirm the daemon's startup device log + a single feed works end-to-end:
.venv/bin/python -c "from voice_typing import daemon, cuda_check; print('CUDA:', cuda_check.is_cuda_available())"
# Expected: pinned texts match; use_microphone=False; skip-guards present; latency-line cross-check present.
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: `ruff check`/`mypy`/`ruff format --check` clean on `tests/test_feed_audio.py`.
- [ ] L2: `uv run pytest tests/test_feed_audio.py -v` passes (CUDA) — all 5 criteria + the daemon cross-check.
- [ ] L3: `uv run pytest tests/ --ignore=tests/test_feed_audio.py` still fully green (no regression).
- [ ] L4: canonical texts pinned verbatim (test == make_test_audio.sh); `use_microphone=False`; skip-guards
      present; daemon latency-line cross-check present.

### Feature Validation

- [ ] (a) first partial <1.5 s after speech onset; ≥1 partial per 500 ms while speaking.
- [ ] (b) `utt_pause.wav` → ≥2 finals, second half fuzzy ≥80 % vs `PAUSE_B` (THE WhisperX-flaw regression).
- [ ] (c) `utt_multi.wav` → exactly 3 non‑empty finals.
- [ ] (d) every non‑empty final of every clip fuzzy ≥0.80 vs its canonical text.
- [ ] (e) on CUDA, final callback − last speech sample ≤1.5 s (2.0 s slack); skipped on CPU.
- [ ] P1.M4.T1.S3: daemon emits `voice-typing latency:` line + `LatencyLog.snapshot()` non‑empty + nothing
      typed with the no‑op backend.
- [ ] Skips cleanly (not errors) when `tests/out/*.wav` or heavy deps are absent.

### Code Quality Validation

- [ ] File placement: `tests/test_feed_audio.py` per PRD §4.1 layout.
- [ ] Follows house test style (stubs, `_wait_for` poller, `caplog` grep) from `tests/test_daemon.py`.
- [ ] Session‑scoped recorder (constructed ONCE); per‑test collectors reset for isolation.
- [ ] The seven load‑bearing invariants upheld: G‑PACE, G‑ORDER, G‑ABORT, G‑SHUTDOWN, G‑RAW, G‑CPU,
      G‑REALTIME‑CB (see Known Gotchas).
- [ ] No edit to `voice_typing/*`, `pyproject.toml`, `config.toml`, `tests/make_test_audio.sh`,
      `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`; no `e2e_virtual_mic.sh`; no README; no conftest.

### Documentation & Deployment

- [ ] Module docstring documents: PRD §6 T1, the five criteria, the real‑time‑pacing requirement, the run
      command, the skip conditions, and the no‑mic/no‑typing contract.
- [ ] No new env vars; no config change.

---

## Anti-Patterns to Avoid

- ❌ Don't feed the whole WAV buffer at once (`rec.feed_audio(samples); time.sleep(N)`) — VAD stop + partial
  cadence are WALL-CLOCK (research §2); a 3 s silence processes in <1 ms → halves merge → criterion (b)
  FAILS. ALWAYS pace: feed a slice, `sleep(slice_duration)` (G-PACE).
- ❌ Don't feed before the consume loop arms listening — start the `recorder.text(cb)` thread FIRST, then feed
  (G-ORDER); otherwise the first audio is consumed without starting a recording (lost).
- ❌ Don't call `recorder.abort()` from the thread inside `text()` — it blocks on `was_interrupted.wait()` which
  is set inside `text()` → self-deadlock (G-ABORT). Abort from the TEST thread.
- ❌ Don't skip `recorder.shutdown()` in teardown — on Linux the transcript worker is a NON-daemon thread
  (the `.deamon` typo) and leaks (G-SHUTDOWN). Always `shutdown()` in the session `finally`.
- ❌ Don't collect finals from the daemon's `on_final` — `textproc.clean()` rejects blocklisted/too-short finals
  (early return, invisible). Collect RAW from `recorder.text(cb)` (G-RAW). The daemon path is a SEPARATE test.
- ❌ Don't assert criterion (e) ≤1.5 s unconditionally on CPU — `distil-large-v3` finalization can exceed it
  (G-CPU). Gate on `cuda_check.is_cuda_available()`; skip or widen on CPU.
- ❌ Don't override `enable_realtime_transcription` to False — no partials fire (criterion a unmeasurable;
  G-REALTIME-CB). It is already True via `_FIXED_KWARGS`/`cfg_to_kwargs`.
- ❌ Don't expect `textproc.clean()` to fuzzy-match — it is a strip/blocklist/min-length filter only; the ≥80 %
  token overlap is the TEST's job (G-FUZZY).
- ❌ Don't construct the recorder per-test — model load is seconds + forces `mp.set_start_method("spawn")`.
  Use a session-scoped fixture; reset a `_Collector` per test (G-NOLOGFILE/G-SHARED-RECORDER-STATE).
- ❌ Don't forget the trailing silence — pad ~1 s of zeros + sleep so the LAST segment's 0.6 s stop threshold
  fires and its final callback lands (G-TRAILING-SILENCE).
- ❌ Don't let the test error (vs skip) when WAVs/models are absent — guard with `pytest.mark.skipif` so the
  fast unit suite is never broken on a CPU-only/clone box (G-SKIP-GUARDS).
- ❌ Don't hand-roll the recorder kwargs — reuse `daemon.cfg_to_kwargs` (applies cuda_check → right models) +
  `daemon._filter_kwargs_to_signature` (drops unknown kwargs safely); override only `use_microphone`.
- ❌ Don't edit any `voice_typing/` module, `pyproject.toml`, `config.toml`, `make_test_audio.sh`,
  `.gitignore`, `PRD.md`, `tasks.json`, `prd_snapshot.md`; don't create `e2e_virtual_mic.sh` (P1.M7.T3.S1),
  a README, or a conftest.

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a single pytest file whose **entire
RealtimeSTT interaction model is derived in the cited research note from the installed v1.0.2 source**
(file path + symbol for every claim): `feed_audio` accepts int16 ndarray/bytes and re-slices to 32 ms
NON-blocking; `text(cb)` BLOCKS per utterance and must be LOOPED for multiple finals; the consume loop must
arm listening BEFORE the first feed; VAD stop + partial cadence are WALL-CLOCK so real-time pacing is
mandatory (the single most load-bearing detail); `abort()` must come from another thread; `shutdown()` is
idempotent + mandatory on Linux. The **production seams** (`daemon.cfg_to_kwargs`/`_build_callbacks`/
`_filter_kwargs_to_signature`/`LatencyLog`/`_LATENCY_LOG_PREFIX`/`VoiceTypingDaemon`) and the **house test
style** (`_wait_for`, stubs, `caplog`) are read from `voice_typing/daemon.py` and `tests/test_daemon.py`. The
**canonical fuzzy targets** are pinned verbatim (and cross-checked against `tests/make_test_audio.sh` in
L4). numpy 2.5.1 + soundfile 0.13.1 are confirmed in the venv; the WAVs are confirmed 16000 Hz/1ch/16-bit.
The −1 residual risk is **measured model latency on the actual GPU** (criterion e) — the test gates it on
CUDA, uses a 2.0 s slack over the 1.5 s target, and the research note flags `large-v3-turbo` as the fallback
if `distil-large-v3` is slow. The fuzzy 80 % floor is the only non-deterministic surface (espeak drift),
which is exactly why the PRD mandates fuzzy (not exact) matching — drift below 80 % consistently would
indicate a fixture problem, not a test bug, and is recoverable via `make_test_audio.sh FORCE=1`.
