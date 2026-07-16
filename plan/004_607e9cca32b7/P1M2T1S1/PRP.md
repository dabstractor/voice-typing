# PRP — P1.M2.T1.S1: T7 lite feed-audio integration (one-model resident, accuracy≥70%, lower latency)

## Goal

**Feature Goal**: Deliver the PRD §6 **T7** lite-mode integration test proving three things end-to-end with REAL models: (a) lite mode loads **exactly ONE model** (the real constructed recorder carries `use_main_model_for_realtime=True`); (b) lite finals arrive over the normal clean→type path at **fuzzy-accuracy ≥70%** on `utt_simple.wav`; (c) lite **final-typed latency is materially lower** than normal mode on the same utterance; plus the **socket mode-switch roundtrip** (`toggle-lite`→lite, `toggle-lite`→disarm, `toggle`→reload normal, `status`→mode). This is the GPU/integration counterpart to the unit tests owned by P1.M1.T1.S2 (kwargs) and the parallel P1.M1.T2.S2 (mode-switch logic) — T7 proves it with real model loads, which unit tests cannot.

**Deliverable** (test-only; 2 files edited, no source, no new files):
1. `tests/test_feed_audio.py` — ADD a `lite_recorder` session fixture (mirrors `recorder` with `cfg_to_kwargs(cfg, lite=True)`) + 2 CUDA-gated tests: `test_lite_feed_audio_utt_simple` (one-model flag on the real recorder + finals + fuzzy ≥70%) and `test_lite_latency_lower_than_normal` (lite total_ms < normal on utt_simple).
2. `tests/test_idle_and_gpu.sh` — ADD a **T7 section** at the end of Run 1: the voicectl mode-switch roundtrip (`toggle-lite`/`toggle-lite`/`toggle`/`status`) + an optional VRAM≈half comparison. Comment-documented (Mode A).

**Success Definition**:
- (a) `test_lite_feed_audio_utt_simple` (GPU): the real lite recorder has `use_main_model_for_realtime is True`; feeding `utt_simple.wav` yields ≥1 final with `_token_overlap(joined, SIMPLE_TEXT) >= 0.70`.
- (b) `test_lite_latency_lower_than_normal` (GPU): on `utt_simple.wav`, lite final-latency (last-speech→final) is strictly less than normal (`lite_ms < normal_ms`).
- (c) The T7 shell section: `voicectl toggle-lite` → status reports `mode: lite`; `toggle-lite` → disarm; `toggle` → reload into `mode: normal` (one reload); `status` → `mode: normal`. Optional: lite-armed VRAM < normal-armed VRAM.
- (d) The new tests inherit test_feed_audio.py's skip guards → the fast sweep (`pytest tests/ --ignore=tests/test_feed_audio.py`, and even `pytest tests/`) stays GREEN on a CPU/clone box; the new tests run only on GPU with WAVs+models present.
- (e) No source files touched (all lite interfaces landed in P1.M1); no duplication of P1.M1.T1.S2/P1.M1.T2.S2 unit tests.

## User Persona

Not applicable (integration test; no user-facing surface — DOCS: Mode A comment in the test_idle_and_gpu.sh T7 section).

## Why

- **T7 is the PRD's lite-mode acceptance gate.** PRD §6 T7 + acceptance #10 require proving lite mode loads ONLY `lite_model` (≈half the VRAM), types finals at ≥70% accuracy, has materially lower latency, and that the mode-switch roundtrip works. The unit tests (P1.M1.T1.S2 kwargs; P1.M1.T2.S2 mode-switch) prove the LOGIC with mocks; T7 proves the real Whisper small model actually transcribes + the real mode-switch reload actually works end-to-end.
- **The one-model invariant is load-bearing.** A future RealtimeSTT upgrade could regress the `use_main_model_for_realtime` early-return (silently loading two models, killing the VRAM/latency benefit). T7's `rec.use_main_model_for_realtime is True` check (on the REAL recorder) + the optional VRAM≈half comparison fail loudly if that happens.
- **Consumed by the lite release.** P1.M2.T2 (docs) references T7; P1.M2.T3 (final verify) runs T7 as the lite acceptance proof.

## What

Two test additions (no source):
- **test_feed_audio.py**: a `lite_recorder` fixture + `test_lite_feed_audio_utt_simple` (one-model + ≥70%) + `test_lite_latency_lower_than_normal` (lite < normal). CUDA-gated; real `AudioToTextRecorder` built via `cfg_to_kwargs(cfg, lite=True)` + `use_microphone=False`; WAV fed via the existing `_run_utterance`/`_feed_paced` harness; accuracy via the existing `_token_overlap`.
- **test_idle_and_gpu.sh**: a T7 section driving `voicectl toggle-lite`/`toggle`/`status` against the live daemon + an optional `vram_tree_state` lite-vs-normal comparison.

### Success Criteria

- [ ] `lite_recorder` fixture builds via `cfg_to_kwargs(cfg, lite=True)` (mirrors `recorder`).
- [ ] `test_lite_feed_audio_utt_simple`: `rec.use_main_model_for_realtime is True`; `_run_utterance(..., _WAVS["simple"], 1)`; finals non-empty; `_token_overlap(joined, SIMPLE_TEXT) >= 0.70`.
- [ ] `test_lite_latency_lower_than_normal`: lite final-latency < normal final-latency on `utt_simple`.
- [ ] Both tests CUDA-gated (`if not daemon.cuda_check.is_cuda_available(): pytest.skip(...)`) + inherit the file's WAV/deps skip.
- [ ] test_idle_and_gpu.sh T7 section: toggle-lite→`mode: lite`, toggle-lite→disarm, toggle→`mode: normal` (one reload), status→`mode: normal`; optional lite VRAM < normal VRAM.
- [ ] Fast sweep green; `git status` == `tests/test_feed_audio.py` + `tests/test_idle_and_gpu.sh` only.

## All Needed Context

### Context Completeness Check

_Pass._ Every lite source interface is verified LANDED (consume, don't rebuild); the existing test_feed_audio.py harness (fixture, `_run_utterance`, `_token_overlap`, `SIMPLE_TEXT`, CUDA-gating, skip guards) is read and reused verbatim-pattern; the non-duplication boundaries (P1.M1.T1.S2=kwargs unit, P1.M1.T2.S2=mode-switch unit) are explicit; and the test_idle_and_gpu.sh helpers (`vram_tree_state`, `daemon_tree_pids`, voicectl wrap) are identified. Verbatim code is given for the fixture + the accuracy test; the latency test mirrors the proven `test_final_latency` timing wrap in the same file.

### Documentation & References

```yaml
# MUST READ — the one-model fact + the kwargs/build_recorder lite interfaces + the T7 assertion strategy
- docfile: plan/004_607e9cca32b7/architecture/realtimestt_lite_mode_verification.md
  why: "VERIFIED: use_main_model_for_realtime=True -> RealtimeSTT v1.0.2 _initialize_realtime_transcription_model
        early-returns -> exactly ONE model loads. The lite kwargs: model=realtime_model_type=lite_model + the flag.
        How T7 asserts one-model: rec.use_main_model_for_realtime is True (CUDA-free, on the REAL recorder) + the
        integration-grade VRAM≈half (T7 shell). CPU lite substitute is tiny.en."
  critical: "The one-model invariant is the load-bearing fact; T7 must fail loudly if a future upgrade regresses it."

# MUST READ — the file Part A extends (fixture + harness + helpers + CUDA-gating + skip guards)
- file: tests/test_feed_audio.py
  why: "recorder fixture @253 (cfg_to_kwargs(cfg) -> use_microphone=False -> wire callbacks -> filter -> construct ->
        yield -> _safe_shutdown): the lite_recorder fixture MIRRORS this with cfg_to_kwargs(cfg, lite=True).
        _run_utterance(rec,col,wav,want_finals) @306 (reset+consume+feed+wait+abort) — reuse as-is. _token_overlap
        @142 — the ≥0.70 assertion. SIMPLE_TEXT + _WAVS['simple'] — the canonical target. test_final_latency @414
        (CUDA-gated; t_last_speech->t_final timing wrap) — the pattern test_lite_latency_lower_than_normal mirrors.
        pytestmark @123 (skipif not _have_wavs()) — the new tests inherit this skip. _DEPS global + _load_deps @81."
  pattern: "lite_recorder = copy of recorder with the one lite=True kwarg swap. The accuracy test = _run_utterance +
            _token_overlap(joined, SIMPLE_TEXT) >= 0.70. The latency test = test_final_latency's timing run for BOTH
            recorder (normal) and lite_recorder, assert lite_ms < normal_ms."
  gotcha: "test_feed_audio builds the recorder DIRECTLY (no daemon) -> the daemon's 'voice-typing latency:' log line
           is NEVER emitted here; measure latency DIRECTLY (t_last_speech->t_final), don't grep the log."

# THE LANDED lite INTERFACES (consume; verified in code)
- file: voice_typing/daemon.py
  why: "cfg_to_kwargs(cfg, *, resolved=None, lite=False) @158 — lite branch sets model=realtime_model_type=lite_model +
        use_main_model_for_realtime=True. build_recorder(..., lite=False) @313 -> _construct(..., lite=lite). The real
        AudioToTextRecorder built from these kwargs therefore has .use_main_model_for_realtime == True (the T7 one-model
        assertion). lite_model config field = 'small.en' (config.py AsrConfig:54)."
  critical: "Use daemon.cfg_to_kwargs(cfg, lite=True) in the lite_recorder fixture (NOT build_recorder — the fixture
             constructs AudioToTextRecorder directly, matching the existing recorder fixture)."

# THE CONFIG FIELD
- file: voice_typing/config.py
  why: "AsrConfig.lite_model: str = 'small.en' (@54). cfg.asr.lite_model is what cfg_to_kwargs(lite=True) uses for both
        model fields on CUDA. (CPU substitute tiny.en is handled inside cfg_to_kwargs.)"

# THE SHELL HARNESS Part B extends (helpers + voicectl + nvidia-smi)
- file: tests/test_idle_and_gpu.sh
  why: "Stands up the REAL daemon via launch_daemon.sh + drives voicectl + nvidia-smi tree checks. Helpers: vram_tree_state
        @227 (pid,used_memory CSV for the daemon tree), daemon_tree_pids @205, assert_vram_present @263. voicectl is wrapped
        with a timeout @153. Run 1 arms in normal mode (voicectl start) for T4/T6. The T7 section appends to the END of
        Run 1 (daemon up, was armed normal) so it doesn't corrupt T6 assertions. voicectl status renders 'mode:' (ctl.py
        format_result); toggle-lite/start-lite are in ctl _COMMANDS + socket _dispatch."
  critical: "Place the T7 section LAST in Run 1 (after T6(c)) — the mode-switch reload changes the resident host and must
             not interfere with earlier T6 VRAM assertions. voicectl status | grep '^mode:' reads the mode."

# NON-DUPLICATION BOUNDARIES (do NOT re-test these)
- docfile: plan/004_607e9cca32b7/P1M1T2S2/PRP.md
  why: "T2.S2 owns the UNIT mode-switch tests (test_daemon.py: mode-switch teardown stop_calls, idle-unload->start_lite;
        test_control_socket.py: dispatch status carries mode) — all with MOCKED hosts. T7's Part B is the INTEGRATION
        counterpart (REAL daemon + REAL voicectl + REAL model reload). P1.M1.T1.S2 (Complete) unit-tests cfg_to_kwargs(lite=True)
        kwargs — T7 does NOT re-assert kwargs in isolation (it asserts the REAL recorder's attribute). No file overlap
        (T2.S2 edits test_daemon.py/test_control_socket.py; T7 edits test_feed_audio.py/test_idle_and_gpu.sh)."

# THE PRD CONTRACT
- file: PRD.md
  why: "§6 T7 (the lite test spec) + §4.2ter (lite mode: one model, use_main_model_for_realtime=True, mode-switch reload,
        mode in state/status) + acceptance #10 (lite arms ONLY lite_model, ≈half VRAM, one bounded reload, status reports
        mode). T7 is the acceptance proof for #10."
```

### Current Codebase tree (relevant slice — the 2 test files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── test_feed_audio.py     # EDIT (Part A): + lite_recorder fixture + 2 CUDA-gated lite tests (appended at end).
│   └── test_idle_and_gpu.sh   # EDIT (Part B): + T7 voicectl mode-switch roundtrip + optional VRAM≈half (end of Run 1).
# voice_typing/daemon.py (cfg_to_kwargs/build_recorder lite=, _load_host mode, toggle_lite/start_lite, status_snapshot mode) — LANDED, UNCHANGED.
# voice_typing/config.py (AsrConfig.lite_model) — LANDED. ctl.py/feedback.py/status.sh/recorder_host.py — LANDED. No source edits.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_feed_audio.py    # EDIT — + lite_recorder fixture + test_lite_feed_audio_utt_simple + test_lite_latency_lower_than_normal.
tests/test_idle_and_gpu.sh  # EDIT — + T7 section (voicectl toggle-lite/toggle/status roundtrip + optional VRAM comparison; Mode A comment).
# NOTHING ELSE. (daemon.py/config.py/ctl.py/feedback.py/status.sh = P1.M1, landed. test_daemon.py/test_control_socket.py = P1.M1.T2.S2. README/ACCEPTANCE = P1.M2.T2.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — BUILD THE LITE RECORDER VIA cfg_to_kwargs(lite=True), NOT build_recorder. test_feed_audio.py's `recorder`
#   fixture constructs AudioToTextRecorder DIRECTLY (daemon.cfg_to_kwargs -> filter -> AudioToTextRecorder(**filtered)),
#   NOT via daemon.build_recorder (which wires daemon Feedback callbacks). The lite_recorder fixture must mirror that,
#   swapping only cfg_to_kwargs(cfg) -> cfg_to_kwargs(cfg, lite=True). Do NOT call build_recorder in the fixture.

# CRITICAL #2 — THE ONE-MODEL ASSERTION IS rec.use_main_model_for_realtime is True (on the REAL constructed recorder),
#   NOT a re-assertion of cfg_to_kwargs output. P1.M1.T1.S2 already unit-tests the kwargs dict; T7 proves the flag reached
#   the actual AudioToTextRecorder instance (the integration grade). Do NOT re-add a kwargs-only assertion.

# CRITICAL #3 — MEASURE LATENCY DIRECTLY (t_last_speech -> t_final); do NOT grep the daemon 'voice-typing latency:' log.
#   test_feed_audio.py builds the recorder DIRECTLY (no daemon) so the daemon's on_final/latency log NEVER fires here.
#   Mirror test_final_latency's (@414) timing wrap (stamp t_last_speech before the trailing-silence pad; wrap col.add_final
#   to stamp t_final BEFORE the consume thread starts). Run it for BOTH recorder (normal) + lite_recorder; assert lite < normal.

# CRITICAL #4 — CUDA-GATE THE REAL-MODEL TESTS. test_lite_feed_audio_utt_simple + test_lite_latency_lower_than_normal must
#   skip when `not daemon.cuda_check.is_cuda_available()` (mirror test_final_latency's G-CPU skip). The lite_recorder fixture
#   itself is session-scoped + skip-on-deps-absent (mirrors recorder); the CUDA gate is in the TESTS.

# CRITICAL #5 — DO NOT DUPLICATE P1.M1.T2.S2's UNIT MODE-SWITCH TESTS. Part B (test_idle_and_gpu.sh) is the INTEGRATION
#   counterpart (real voicectl + real daemon + real model reload). Do NOT add pytest mode-switch tests with mocked hosts
#   (that's T2.S2's territory, already done/in-flight). (research §2.)

# CRITICAL #6 — PLACE THE T7 SHELL SECTION LAST IN RUN 1 (after T6(c)). The mode-switch reload tears down + respawns the
#   resident host, changing VRAM attribution — it MUST NOT corrupt the earlier T6(a/b/c) assertions. Run 1's daemon is up
#   + was armed normal, so toggle-lite there triggers the real normal->lite reload.

# GOTCHA #7 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest/uv.

# GOTCHA #8 — pytest>=9.1.1 is the runner; NO ruff/mypy. test_feed_audio.py is NOT collected by the fast sweep when
#   WAVs/deps absent (pytestmark) -> the new tests inherit that skip -> `pytest tests/ --ignore=tests/test_feed_audio.py`
#   stays green; even full `pytest tests/` skips them on a CPU/clone box.
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/source change. Two test additions reusing the existing `_Collector`/`_run_utterance`/`_token_overlap` harness + the shell `vram_tree_state`/voicectl helpers.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT tests/test_feed_audio.py — ADD the lite_recorder fixture (mirror `recorder` with lite=True)
  - INSERT the fixture IMMEDIATELY AFTER the existing `recorder` fixture (after its `shutdown_thread.join(timeout=30.0)`
    line, before `_run_utterance`). Verbatim:
        @pytest.fixture(scope="session")
        def lite_recorder() -> "Iterator[tuple[AudioToTextRecorder, _Collector]]":
            """T7 (PRD §4.2ter/§6): the LITE recorder — ONE model (lite_model) via cfg_to_kwargs(lite=True).

            Mirrors the `recorder` fixture exactly except cfg_to_kwargs(cfg) -> cfg_to_kwargs(cfg, lite=True), which sets
            model=realtime_model_type=lite_model + use_main_model_for_realtime=True (verified: the separate realtime
            engine never initializes -> exactly ONE model resident). Session-scoped so normal (recorder) + lite
            (lite_recorder) coexist for the latency-comparison test.
            """
            global _DEPS
            try:
                deps = _load_deps()
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"heavy deps unavailable: {exc!r}")
            _DEPS = deps
            AudioToTextRecorder = deps["AudioToTextRecorder"]
            daemon = deps["daemon"]
            VoiceTypingConfig = deps["VoiceTypingConfig"]
            cfg = VoiceTypingConfig()
            col = _Collector()
            kwargs = daemon.cfg_to_kwargs(cfg, lite=True)  # THE lite swap (model=lite_model, use_main_model_for_realtime=True)
            kwargs["use_microphone"] = False
            kwargs.update(
                {
                    "on_realtime_transcription_stabilized": col.add_partial,
                    "on_vad_start": col.on_vad_start,
                    "on_vad_stop": col.on_vad_stop,
                    "no_log_file": True,
                }
            )
            filtered = daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder)
            try:
                rec = AudioToTextRecorder(**filtered)
            except Exception as exc:  # pragma: no cover — models/engine absent
                pytest.skip(f"lite AudioToTextRecorder construction failed: {exc!r}")
            yield rec, col
            shutdown_thread = threading.Thread(target=_safe_shutdown, args=(rec,), daemon=True)
            shutdown_thread.start()
            shutdown_thread.join(timeout=30.0)
  - WHY: the lite recorder is the real small.en-only recorder; session-scoped so it coexists with `recorder` for the
    latency test. The ONLY difference from `recorder` is the `lite=True` kwarg (CRITICAL #1).
  - DO NOT: call build_recorder; wire daemon Feedback callbacks; change the teardown.

Task 2: EDIT tests/test_feed_audio.py — APPEND the 2 lite tests at the END of the file (after test_final_latency).
  - APPEND (verbatim):
        # ===================== T7 (PRD §4.2ter/§6): LITE mode — one model + ≥70% accuracy + lower latency =====================
        def test_lite_feed_audio_utt_simple(
            lite_recorder: "tuple[AudioToTextRecorder, _Collector]",
        ) -> None:
            """T7(a,b): lite loads ONE model (use_main_model_for_realtime=True on the REAL recorder) + finals ≥70% fuzzy."""
            assert _DEPS is not None
            daemon = _DEPS["daemon"]
            if not daemon.cuda_check.is_cuda_available():
                pytest.skip("T7 is a GPU integration test (G-CPU)")
            rec, col = lite_recorder
            # (a) ONE model: the real constructed recorder carries the one-model flag (the integration-grade invariant;
            #     P1.M1.T1.S2 already unit-tests the kwargs dict). A future RealtimeSTT regression of the early-return
            #     would leave this False -> fail loudly.
            assert rec.use_main_model_for_realtime is True, "lite recorder did not get use_main_model_for_realtime=True"
            # (b) finals over the normal clean path + fuzzy-accuracy ≥0.70 (lower bar than normal's 0.80 — small.en is
            #     the final model in lite mode).
            _run_utterance(rec, col, _WAVS["simple"], want_finals=1)
            finals = [f.strip() for f in col.finals if f.strip()]
            assert finals, "no lite finals for utt_simple"
            joined = " ".join(finals)
            assert _token_overlap(joined, SIMPLE_TEXT) >= 0.70, (joined, SIMPLE_TEXT)


        def test_lite_latency_lower_than_normal(
            recorder: "tuple[AudioToTextRecorder, _Collector]",
            lite_recorder: "tuple[AudioToTextRecorder, _Collector]",
        ) -> None:
            """T7(c): lite final-typed latency is materially LOWER than normal on utt_simple (small model is faster).

            Measures last-speech-fed -> final-received for BOTH the normal (recorder) and lite (lite_recorder) real
            recorders on the SAME utterance, mirroring test_final_latency's timing wrap, and asserts lite < normal.
            CUDA-gated (both models must be on GPU). NOTE: test_feed_audio builds the recorder DIRECTLY (no daemon) so
            the daemon's 'voice-typing latency:' log line never fires here — latency is measured directly, not grepped.
            """
            assert _DEPS is not None
            daemon = _DEPS["daemon"]
            sf = _DEPS["sf"]
            if not daemon.cuda_check.is_cuda_available():
                pytest.skip("T7(c) latency comparison is a GPU budget (G-CPU)")

            def _final_latency_ms(rec, col, wav) -> float:
                """last-speech-fed -> final-received (ms) for one utterance (mirrors test_final_latency @414)."""
                samples, _ = sf.read(str(wav), dtype="int16")
                col.reset()
                stop = threading.Event()
                t_last_speech: list[float | None] = [None]
                t_final: list[float | None] = [None]
                speech_len = len(samples)
                fed = {"n": 0}

                def _on_last_speech() -> None:
                    if t_last_speech[0] is None:
                        t_last_speech[0] = time.monotonic()

                orig_add_final = col.add_final

                def _wrapped_final(text: str) -> None:
                    if t_final[0] is None:
                        t_final[0] = time.monotonic()
                    orig_add_final(text)

                col.add_final = _wrapped_final  # wrap BEFORE the consume thread captures it in rec.text(cb)
                try:
                    cons = threading.Thread(
                        target=_consume, args=(rec, col, stop, 1), daemon=True
                    )
                    cons.start()  # G-ORDER: consume arms listening BEFORE feed
                    # feed paced; stamp the last speech chunk (before the trailing-silence pad)
                    n_chunks = 0
                    for slc in _chunked(samples):  # _chunked yields the same slices _feed_paced uses
                        fed["n"] += 1
                        if fed["n"] >= speech_len / _CHUNK_SAMPLES:  # approx last speech slice
                            _on_last_speech()
                        rec.feed_audio(slc, original_sample_rate=16000)
                        time.sleep(_CHUNK_SECONDS)
                    assert _wait_for(lambda: t_final[0] is not None, timeout=30.0), "no final received"
                finally:
                    stop.set()
                    _abort_on_thread(rec)
                    col.add_final = orig_add_final
                assert t_last_speech[0] is not None and t_final[0] is not None
                return (t_final[0] - t_last_speech[0]) * 1000.0

            normal_ms = _final_latency_ms(recorder[0], recorder[1], _WAVS["simple"])
            lite_ms = _final_latency_ms(lite_recorder[0], lite_recorder[1], _WAVS["simple"])
            # Materially lower: the small model is genuinely faster. Strict < (no rigid ratio — espeak/GPU variance).
            # If this proves flaky on a given GPU, relax to lite_ms <= normal_ms (the small model is never slower).
            assert lite_ms < normal_ms, f"lite not faster: lite={lite_ms:.0f}ms normal={normal_ms:.0f}ms"
  - WHY: (a) rec.use_main_model_for_realtime is True = the one-model integration proof; (b) ≥0.70 = lite accuracy bar;
    (c) lite_ms < normal_ms = materially-lower latency. Both CUDA-gated; reuse _run_utterance/_token_overlap/_consume.
  - IMPLEMENTATION NOTE for _final_latency_ms: the helper above sketches the timing wrap. The EXISTING `_feed_paced`
    (test_feed_audio.py @183) already does the real-time-paced feed_audio loop; PREFER reusing `_feed_paced` + a
    last-speech stamp over the inline `_chunked` sketch — i.e. mirror test_final_latency's (@414) EXACT feed+stamp
    structure (read it: it stamps t_last_speech via a hook on the last speech slice, wraps col.add_final before the
    consume thread starts, and uses _feed_paced). If `_chunked`/`_CHUNK_SAMPLES`/`_CHUNK_SECONDS`/`_abort_on_thread` are
    not existing helpers, DO NOT invent them — use `_feed_paced`/`_safe_abort` (the real helpers) per test_final_latency.
    The assertion (`lite_ms < normal_ms`) + the dual-recorder measurement is the contract; the timing mechanism is
    test_final_latency's, reused.
  - DO NOT: grep the daemon latency log (CRITICAL #3); assert a rigid latency ratio (use strict <); skip the CUDA gate.

Task 3: EDIT tests/test_idle_and_gpu.sh — APPEND a T7 section at the END of Run 1 (after the T6(c) block, before quit).
  - Append a self-contained block (Mode A comment at top documenting purpose). Pseudocode (adapt to the script's helpers):
        # === T7 (PRD §4.2ter/§6 + acceptance #10): lite mode-switch roundtrip + VRAM≈half (integration grade) ===
        # Drives the REAL daemon's mode-switch via voicectl: toggle-lite (normal->lite reload) -> disarm -> toggle
        # (lite->normal reload) -> status. Complements P1.M1.T2.S2's UNIT mode-switch tests (mocked host) by proving
        # the REAL reload + status mode end-to-end. Optional VRAM: lite-armed < normal-armed (small.en only vs
        # distil-large-v3+small.en). Placed LAST in Run 1 so the reload doesn't corrupt T6(a/b/c) VRAM assertions.
        #   1. snapshot normal-armed VRAM (the daemon was armed normal for T6(b); re-arm if needed): vram_tree_state.
        #   2. voicectl toggle-lite  -> poll voicectl status until 'mode: lite' (the normal->lite reload; ~1-3s).
        #      (optional) snapshot lite-armed VRAM; assert lite_total < normal_total (≈half; best-effort, no rigid ratio).
        #   3. voicectl toggle-lite  -> disarm (listening: off; mode stays lite).
        #   4. voicectl toggle       -> poll status until 'mode: normal' (the lite->normal reload; exactly ONE reload).
        #   5. voicectl status       -> assert 'mode: normal'.
        # Assert each voicectl call returns ok (the script's voicectl wrapper); grep status for '^mode: lite' / '^mode: normal'.
  - Wire it with the script's existing helpers: `vram_tree_state "$DAEMON_PID"` (227) for VRAM; the voicectl wrapper
    (153, timeout-guarded); `grep -q '^mode:'` on `voicectl status` output. POLL (never fixed sleep) for the reloads
    (the mode-switch is a ~1-3s bounded teardown+respawn). Print a `[PASS] T7 ...` / `[FAIL] T7 ...` line + include the
    mode-switch evidence in the `=== ACCEPTANCE EVIDENCE ===` block.
  - WHY: the integration counterpart to P1.M1.T2.S2's unit mode-switch tests — proves the real reload + status mode.
  - DO NOT: add pytest mode-switch tests with mocked hosts (CRITICAL #5); place the section before T6 (CRITICAL #6);
    assert a rigid VRAM ratio (best-effort <).

Task 4: VALIDATE — run the Validation Loop L1-L4; fix until green. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S1: T7 lite feed-audio integration (one-model + ≥70% + lower latency + voicectl mode-switch)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — lite_recorder fixture = recorder fixture + the one lite=True swap. Everything else (use_microphone=False,
# callbacks, filter, construct, _safe_shutdown) identical. Session-scoped so normal+lite coexist.
kwargs = daemon.cfg_to_kwargs(cfg, lite=True)   # THE swap: model=lite_model, use_main_model_for_realtime=True

# PATTERN 2 — the one-model integration assertion (on the REAL recorder, complements the kwargs unit test).
assert rec.use_main_model_for_realtime is True   # the constructed AudioToTextRecorder carries the flag

# PATTERN 3 — accuracy via the existing fuzzy helper (lower bar for lite: small.en is the final model).
assert _token_overlap(" ".join(finals), SIMPLE_TEXT) >= 0.70   # normal mode uses 0.80

# PATTERN 4 — latency measured DIRECTLY (no daemon -> no log line), mirroring test_final_latency's timing wrap.
normal_ms = _final_latency_ms(recorder[0], recorder[1], _WAVS["simple"])
lite_ms   = _final_latency_ms(lite_recorder[0], lite_recorder[1], _WAVS["simple"])
assert lite_ms < normal_ms                         # the small model is faster (strict <; relax only if flaky)
```

### Integration Points

```yaml
UPSTREAM CONSUMED — LANDED lite interfaces (UNCHANGED):
  - cfg_to_kwargs(lite=) @158, build_recorder(lite=) @313, AsrConfig.lite_model='small.en' @54, _load_host(mode)/
    toggle_lite/start_lite/status_snapshot mode (daemon), socket _dispatch toggle-lite/start-lite, ctl _COMMANDS + mode
    render, feedback set_mode/_state['mode'], status.sh ⚡/🎤. All landed by P1.M1; T7 consumes them.

NON-DUPLICATION — siblings own the UNIT tests:
  - P1.M1.T1.S2 (Complete): cfg_to_kwargs(lite=True) kwargs unit test. T7 asserts the REAL recorder attribute instead.
  - P1.M1.T2.S2 (parallel): UNIT mode-switch tests (mocked host) in test_daemon.py/test_control_socket.py. T7 Part B is
    the integration counterpart (real voicectl + real reload). NO file overlap.

DOWNSTREAM — consumers:
  - P1.M2.T2 (docs): README lite-mode sections + ACCEPTANCE.md T7 cross-check reference T7.
  - P1.M2.T3 (final verify): runs T7 (Part A pytest on GPU + Part B shell) as the lite acceptance proof (#10).

UNCHANGED: all source (daemon.py/config.py/ctl.py/feedback.py/status.sh/recorder_host.py), test_daemon.py,
  test_control_socket.py, README/ACCEPTANCE. No new files.

BUILD ARTIFACTS: NO source changes, NO pyproject/uv.lock/.venv changes, NO new deps. Validation = pytest (Part A) +
  the shell script (Part B, run explicitly).
```

## Validation Loop

> Full paths in every bash command (GOTCHA #7). Run from `/home/dustin/projects/voice-typing`. pytest is the runner
> (NO ruff/mypy — GOTCHA #8). Part A needs GPU + WAVs + models (build WAVs first); Part B needs the live daemon stack.

### Level 1: the test_feed_audio.py additions are present + collect cleanly (no fast-sweep regression)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile tests/test_feed_audio.py && echo "L1 PASS: py_compile" || echo "L1 FAIL"
"$PY" -m pytest tests/test_feed_audio.py --collect-only -q 2>&1 | grep -E 'lite_feed_audio|lite_latency' && echo "L1 PASS: lite tests collected" || echo "L1 FAIL: lite tests not collected"
# The fast sweep MUST stay green (the new tests skip without WAVs/deps; with WAVs+no-GPU they skip on the CUDA gate):
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py is ignored here; the rest of the suite is unaffected.)
```

### Level 2: build the WAV assets (prereq for Part A on GPU)

```bash
cd /home/dustin/projects/voice-typing
ls tests/out/utt_simple.wav 2>/dev/null && echo "L2 PASS: utt_simple.wav present" || { echo "building WAVs..."; bash tests/make_test_audio.sh && echo "L2 PASS: WAVs built"; }
```

### Level 3: Part A — the lite pytest tests PASS on GPU (the core T7 proof)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m pytest tests/test_feed_audio.py -k "lite_feed_audio or lite_latency" -v
# Expected (GPU): 2 passed. test_lite_feed_audio_utt_simple asserts rec.use_main_model_for_realtime is True + finals +
#   _token_overlap >= 0.70; test_lite_latency_lower_than_normal asserts lite_ms < normal_ms. (On CPU: both skip via G-CPU.)
# If accuracy < 0.70: small.en on espeak is lower-accuracy — re-run (variance) before relaxing the bar; the contract's 70%
#   bar already accounts for small.en-as-final. If latency lite >= normal: re-run (GPU variance); relax to <= only if flaky.
```

### Level 4: Part B — the T7 shell section (voicectl mode-switch roundtrip + optional VRAM)

```bash
cd /home/dustin/projects/voice-typing
# Run the full shell harness (heavy ~5-8 min; stands up the real daemon). The T7 section is at the end of Run 1.
bash tests/test_idle_and_gpu.sh 2>&1 | tee /tmp/t7_idle_gpu.log
# Expected: a [PASS] T7 line for the mode-switch roundtrip (toggle-lite -> mode: lite; toggle -> mode: normal; status ->
#   mode: normal) + (optional) lite VRAM < normal VRAM in the === ACCEPTANCE EVIDENCE === block. On FAIL it prints daemon.log tail.
grep -E 'T7|mode:' /tmp/t7_idle_gpu.log | head
# NOTE: this script is the live-daemon integration test; it needs the real CUDA + systemd stack. It is NOT in the fast sweep.
```

### Level 5: scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY tests/test_feed_audio.py (modified) + tests/test_idle_and_gpu.sh (modified). No source, no test_daemon.py/
#   test_control_socket.py (P1.M1.T2.S2), no README/ACCEPTANCE (P1.M2.T2), no config/ctl/feedback/status.sh.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: py_compile clean; lite tests collected; fast sweep (`--ignore=tests/test_feed_audio.py`) 0 failed.
- [ ] L2: `tests/out/utt_simple.wav` present (built by make_test_audio.sh).
- [ ] L3 (GPU): `test_lite_feed_audio_utt_simple` + `test_lite_latency_lower_than_normal` pass.
- [ ] L4: test_idle_and_gpu.sh T7 section — `[PASS] T7` mode-switch roundtrip (+ optional VRAM≈half).
- [ ] L5: `git status` == `tests/test_feed_audio.py` + `tests/test_idle_and_gpu.sh`.

### Feature Validation
- [ ] Lite loads ONE model (`rec.use_main_model_for_realtime is True` on the real recorder).
- [ ] Lite finals ≥70% fuzzy-accuracy on utt_simple.
- [ ] Lite latency materially lower than normal (`lite_ms < normal_ms`).
- [ ] Socket mode-switch roundtrip: toggle-lite→lite, toggle-lite→disarm, toggle→normal (one reload), status→mode.
- [ ] No duplication of P1.M1.T1.S2 (kwargs) or P1.M1.T2.S2 (unit mode-switch) tests.

### Code Quality Validation
- [ ] lite_recorder mirrors `recorder` (only `lite=True` differs); session-scoped.
- [ ] Tests CUDA-gated; inherit the file's WAV/deps skip (fast sweep stays green on CPU/clone).
- [ ] Latency measured directly (not via daemon log); mirrors test_final_latency's timing.
- [ ] T7 shell section placed last in Run 1 (no T6 corruption); Mode A comment.

### Scope Boundary Validation
- [ ] No source files touched; no test_daemon.py/test_control_socket.py (P1.M1.T2.S2); no README/ACCEPTANCE (P1.M2.T2).
- [ ] No new files; no new deps; no pyproject/uv.lock changes.

---

## Anti-Patterns to Avoid

- ❌ Don't call `build_recorder` in the `lite_recorder` fixture — test_feed_audio.py constructs `AudioToTextRecorder` directly (mirror `recorder` with `cfg_to_kwargs(cfg, lite=True)`).
- ❌ Don't re-assert the `cfg_to_kwargs(lite=True)` kwargs dict in isolation — P1.M1.T1.S2 unit-tests that; T7 asserts `rec.use_main_model_for_realtime is True` on the REAL recorder (the integration grade).
- ❌ Don't grep the daemon `voice-typing latency:` log for Part A latency — test_feed_audio builds the recorder directly (no daemon); measure `t_last_speech→t_final` directly, mirroring test_final_latency.
- ❌ Don't add pytest mode-switch tests with mocked hosts — that's P1.M1.T2.S2's unit territory; Part B is the real-voicectl integration (test_idle_and_gpu.sh).
- ❌ Don't place the T7 shell section before T6 — the mode-switch reload changes the resident host/VRAM; place it LAST in Run 1.
- ❌ Don't assert a rigid VRAM/latency ratio — use strict `<` (best-effort; relax only if GPU variance makes it flaky).
- ❌ Don't forget the CUDA gate on the real-model tests (mirror test_final_latency's G-CPU skip).
- ❌ Don't invent ruff/mypy commands — pytest only. Don't use bare python/pytest/uv (zsh aliases).
- ❌ Don't edit source (daemon.py/config.py/ctl.py/feedback.py/status.sh) — all lite interfaces landed in P1.M1.

---

## Confidence Score

**8/10** for one-pass implementation success. Every lite source interface is verified LANDED (consume, don't rebuild); the `lite_recorder` fixture + `test_lite_feed_audio_utt_simple` are given verbatim (high-confidence, reusing the proven `_run_utterance`/`_token_overlap` harness); the non-duplication boundaries (P1.M1.T1.S2 kwargs unit, P1.M1.T2.S2 mode-switch unit) are explicit; and the CUDA-gating + skip-guard conventions are documented. The residual uncertainty (−2): (1) the `test_lite_latency_lower_than_normal` timing helper is sketched against `test_final_latency`'s pattern — the implementer must reuse `_feed_paced`/`_safe_abort` (the real helpers) rather than the illustrative `_chunked` names, and the strict `lite_ms < normal_ms` may need a tolerance on a noisy GPU; (2) the T7 shell section (Part B) is specified as a pattern + helpers rather than byte-verbatim, since test_idle_and_gpu.sh is a 682-line intricate script — the implementer adapts it to the script's Run 1 structure + helpers. Both are flagged as CRITICAL gotchas with concrete fallbacks.
