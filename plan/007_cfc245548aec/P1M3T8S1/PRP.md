# PRP — P1.M3.T8.S1: T8 streaming E2E harness + RecordingTypingBackend + asserts a/b/d

## Goal

**Feature Goal**: Create `tests/test_streaming.py` — the PRD §6 **T8** streaming-dictation
end-to-end test (real small.en models, no mic, no real keystrokes): a reusable harness that drives
the REAL decode stream through the REAL `StreamingOutput` engine and the REAL context-prompt
executor, capturing every backend keystroke via a new **RecordingTypingBackend**, and implement
T8's asserts **(a)**, **(b)**, and **(d)**.

**Deliverable**:
1. `tests/test_streaming.py` containing:
   - `RecordingTypingBackend` (timestamped `type_text`/`press_backspace` recording + simulated
     screen reconstruction; subclasses `voice_typing.typing_backends.TypingBackend`);
   - `RecordingPromptedExecutor` + recording factory injected via the existing
     `recorder_host.augment_kwargs_with_executor(..., executor_factory=...)` seam (assert-(d)
     evidence: every decode's prompt recorded);
   - a session-scoped, CUDA-loaded, `use_microphone=False` recorder fixture wired through the
     production path (`daemon.cfg_to_kwargs` → callbacks → executor injection →
     `_filter_kwargs_to_signature`), mirroring `tests/test_feed_audio.py`;
   - a harness glue class replicating `daemon.on_final`'s streaming branch
     (clean → commit → reset_boundary → prompt refresh);
   - passing tests for T8 (a), (b), (d), plus skip-guards so a fast `pytest tests/` sweep stays
     green on a box without WAVs/CUDA/deps;
   - a module structure deliberately extensible for S2 (asserts c/e/f/g land in the SAME file —
     fixtures and helpers must be reusable; do NOT implement c/e/f/g here).
2. Research note already written at `plan/007_cfc245548aec/P1M3T8S1/research/codebase-findings.md`.

**Success Definition**: `timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q` passes
on this machine (bash-tool timeout 900), asserting: (a) typed deltas arrive ≥1 per 500 ms while
speech streams and extends type ONLY the delta; (b) a differing commit rewinds EXACTLY `len(tail)`
chars then types the final (+ trailing space), verified by simulated-screen reconstruction; (d)
the executor's decodes carry `initial_prompt` == `rolling_context_prompt(committed)` at decode time
(empty after sentence-final commits, non-empty mid-paragraph via `utt_pause`), always ≤200 tokens.
The existing fast unit suites (`test_streaming_core/commit/freeze`, `test_prompt_engine`,
`test_recorder_host`, `test_voicectl`) still pass — this file adds NO import pollution.

## Why

- PRD §6 **T8** is the acceptance evidence for streaming (PRD §7 #11): "lite recorder child + a
  RecordingTypingBackend (records `type_text`/`press_backspace` calls; no real keystrokes). Feed
  WAVs via `feed_audio`" with asserts (a)–(g). The whole M2 streaming engine
  (P1.M2.T4–T7, COMPLETE) is currently covered only by synthetic-event unit tests; T8 is the
  first test where the REAL small.en partial/commit stream drives the REAL engine.
- This subtask (S1) owns the harness + asserts a/b/d. S2 (Planned) adds c/e/f/g on top —
  the harness is the deliverable S2 builds on.
- P1.M3.T9.S1 (Planned) will cite T8 output in `tests/ACCEPTANCE.md`; deterministic, non-flaky
  assertions with diagnostic dumps on failure are therefore load-bearing.

## What

A pytest module `tests/test_streaming.py` that:

1. Builds ONE session-scoped `AudioToTextRecorder` in-process via the production wiring with
   `use_microphone=False` and `no_log_file=True`, single model `small.en`
   (`use_main_model_for_realtime=True`), executor-injected for the rolling context prompt.
2. Feeds `tests/out/*.wav` at real-time pacing (feed a 0.1 s slice, sleep its duration, plus
   ~1.6 s paced trailing silence) exactly like `tests/test_feed_audio.py::_feed_paced`.
3. Routes stabilized partials → `StreamingOutput.on_partial`, finals → the daemon-equivalent
  commit glue, and records every backend call with `time.monotonic()` timestamps.
4. Asserts (a), (b), (d) per PRD T8 (details in Implementation Blueprint).

### Success Criteria

- [ ] `tests/test_streaming.py` exists; `timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q` → 0 failed (skips allowed only for genuinely absent WAVs/deps/CUDA).
- [ ] Assert (a): during each utterance's speech window, typed deltas arrive with no gap >500 ms,
      and at least one extend cycle types ONLY a suffix delta (no preceding backspace in that cycle).
- [ ] Assert (b): every commit leaves the simulated screen == committed-so-far (guarded final +
      trailing space); every commit-preceded rewind has `n` exactly equal to the tail length
      reconstructed from prior events; ≥1 revising commit occurs across the session (bounded
      retry via `utt_punct.wav` before failing).
- [ ] Assert (d): for every post-warmup `transcribe()` call where `use_prompt` is true, the
      recorded prompt equals `prompt_engine.rolling_context_prompt(<committed at that time>)`;
      specifically empty after each `utt_multi` sentence-final commit and non-empty (== committed
      first half) for `utt_pause` second-half decodes; every recorded prompt ≤200 whitespace tokens.
- [ ] File collects without importing heavy deps at collection time (skip-guards + lazy
      `_load_deps` like test_feed_audio.py) — `test_voicectl.py` import-purity check unaffected.
- [ ] No real keystrokes: the ONLY backend used is the in-file RecordingTypingBackend (never
      `make_backend`); no daemon process is spawned; no mic is opened.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, could they implement this successfully?" — Yes:
every production seam below lists file + line + exact signature; the harness pattern to copy
(`tests/test_feed_audio.py`) is named with its load-bearing invariants; all asserts have
deterministic formulations that avoid model-output flakiness.

### Documentation & References

```yaml
# MUST READ - Include these in your context window
- file: PRD.md
  why: §6 T8 (the spec for asserts a-g), §4.2quater (streaming output state machine rules 1-5),
       §4.4 (recorder kwargs + streaming path), §7 #11 (acceptance), §8 risks (flakiness rows)
  section: 6 (T8), 4.2quater
  critical: T8 wording is the contract — "RecordingTypingBackend (records type_text/press_backspace
    calls; no real keystrokes)"; a/b/d are THIS task; c/e/f/g belong to S2 (do not implement)

- file: tests/test_feed_audio.py
  why: THE harness skeleton to mirror — session recorder fixture, _load_deps lazy-import namespace,
    _feed_paced, _consume, _wait_for, _safe_abort/_safe_shutdown, skip guards, _token_overlap
  pattern: copy the structure; keep the G-invariant tags (G-PACE, G-ORDER, G-ABORT, G-SHUTDOWN,
    G-TRAILING-SILENCE, G-SKIP-GUARDS, G-REALTIME-CB, G-NOLOGFILE, G-CPU, G-FUZZY)
  gotcha: every one of those tags documents a REAL hang/flake that already bit this repo — read them

- file: voice_typing/streaming.py
  why: the engine under test — StreamingOutput ctor + on_partial/commit/reset_boundary semantics
  pattern: ctor (backend, feedback, streaming, *, append_space=True, rate_limit_s=0.3,
    clock=time.monotonic); props committed/tail/frozen
  gotcha: commit() types the trailing space as a SEPARATE type_text(" ") call; suppressed
    rate-limited revise cycles type NOTHING; press_backspace(0) is a contract no-op

- file: voice_typing/prompt_engine.py
  why: rolling_context_prompt(committed) pure fn (assert-(d) oracle); PromptedExecutor to subclass
  pattern: PromptedExecutor.transcribe(audio, language, use_prompt, **kw) NEVER raises;
    set_prompt trims to 200-token cap; .prompt property
  gotcha: warmup()/probe runs ONE decode with prompt=None at construction — filter it from (d)

- file: voice_typing/recorder_host.py   # lines ~494-812
  why: augment_kwargs_with_executor(kwargs, cfg, *, executor_factory=None) — the factory seam that
    makes assert (d) deterministic; also documents the child build order to mirror
  pattern: factory(model, device, compute_type) -> executor; probe folds failure into RuntimeError
  gotcha: returns None (stock kwargs, no executor) when cfg.asr.context_prompt is false — the test
    cfg must keep context_prompt=true or (d) vacuously passes

- file: voice_typing/daemon.py   # cfg_to_kwargs ~L169; on_final ~L1112-1256; _on_partial L1376;
  #                              _refresh_context_prompt L1555
  why: the production wiring the harness must replicate faithfully (streaming branch of on_final)
  pattern: clean(text, cfg.filter) -> stream.commit(cleaned) -> reset_boundary() ->
    set_prompt(rolling_context_prompt(stream.committed))
  gotcha: keep the listening gate + rejected-final early-return shape so S2 can extend with
    freeze/cancel semantics without rewiring

- file: tests/test_streaming_core.py
  why: existing RecordingBackend/FakeFeedback doubles (no timestamps) + house test style
  pattern: subclass TypingBackend; record ("type", text)/("bs", n); press_backspace(n<=0) NOT recorded
  gotcha: T8's backend ADDS monotonic timestamps + a simulated screen buffer — keep the no-op rule

- file: voice_typing/textproc.py
  why: clean(text, filter_cfg) + apply_streaming_guards(context, delta) — used by the glue
  gotcha: clean returns falsy for blocklist/min_chars rejects — mirror daemon's early return

- file: tests/make_test_audio.sh
  why: regenerates tests/out/*.wav (utt_simple, utt_pause, utt_multi, utt_punct) if absent
  gotcha: espeak audio → fuzzy asserts only (>=80% token overlap); NEVER exact-match model output
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
├── daemon.py            # 2808 L — cfg_to_kwargs, on_final streaming branch, _on_partial, _refresh_context_prompt
├── recorder_host.py     # 1009 L — augment_kwargs_with_executor (L757), _default_prompt_executor_factory (L750)
├── streaming.py         # 499 L  — StreamingOutput (engine under test)
├── prompt_engine.py     # 299 L  — rolling_context_prompt, PromptedExecutor, probe
├── typing_backends.py   # 196 L  — TypingBackend ABC (type_text / press_backspace)
├── textproc.py          # 134 L  — clean, apply_streaming_guards
└── config.py            # 409 L  — asr.{lite_model, lite_post_speech_silence_duration=0.8,
│                                 #   context_prompt, realtime_processing_pause=0.15},
│                                 #   output.{streaming, append_space}, filter.{min_chars, blocklist}
tests/
├── test_feed_audio.py       # 779 L — THE heavy-test harness pattern (mirror this)
├── test_streaming_core.py   # pure StreamingOutput unit tests (RecordingBackend double)
├── test_streaming_commit.py # commit-path unit tests
├── test_streaming_freeze.py # freeze-class unit tests
├── test_prompt_engine.py    # executor unit tests (incl. factory injection)
├── test_recorder_host.py    # child IPC unit tests
├── make_test_audio.sh       # regenerates fixtures
└── out/utt_{simple,pause,multi,punct}.wav   # exist on disk
```

### Desired Codebase tree with files to be added

```bash
tests/
└── test_streaming.py        # NEW (~450-600 L) — T8 harness + RecordingTypingBackend +
                             #   RecordingPromptedExecutor + asserts a/b/d; S2 extends with c/e/f/g
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL (hang vectors — AGENTS.md + test_feed_audio.py G-tags):
# - feed_audio is NON-blocking; VAD/post_speech_silence thresholds are WALL-CLOCK. Feed 0.1 s
#   slices + sleep their duration, INCLUDING ~1.6 s of trailing zero slices, or text() blocks
#   forever (G-PACE / G-TRAILING-SILENCE). lite_post_speech_silence_duration=0.8 → 16 slices
#   of 0.1 s trailing silence is the minimum; use 20 for margin.
# - recorder.abort() blocks on was_interrupted.wait() (set only INSIDE text()) — call it ONLY
#   from a helper thread with a join timeout, never the test thread (G-ABORT).
# - Teardown = recorder.shutdown() on a helper daemon thread, join(30) (G-SHUTDOWN).
# - Start the text()-consume thread BEFORE the first feed_audio (G-ORDER).
# - Heavy imports (RealtimeSTT/torch/numpy/soundfile/daemon) MUST stay lazy inside
#   _load_deps()/fixtures — collecting the module must not pollute sys.modules
#   (tests/test_voicectl.py asserts import purity across the full suite).
# - no_log_file=True on the recorder (keeps the repo clean — RealtimeSTT writes an unbounded
#   realtimesst.log otherwise).

# MODEL-OUTPUT NONDETERMINISM (espeak fixtures):
# - Never exact-assert decode text; use the multiset token-overlap helper copied from
#   test_feed_audio.py (_token_overlap >= 0.80 vs the pinned SIMPLE_TEXT/PAUSE_A/MULTI_TEXTS).
# - Assert (b)'s "differing commit" cannot be forced deterministically with real audio: require
#   >=1 revising commit ACROSS the session and retry once with utt_punct.wav before failing.
# - Assert (d) IS deterministic: the oracle is the harness's OWN committed timeline
#   (rolling_context_prompt of what the harness committed), not the model's text.

# ENGINE SEMANTICS THAT SHAPE THE ASSERTS:
# - A rate-limited (suppressed) revise cycle types NOTHING while partials keep arriving → a
#   >500 ms typing gap is legitimate; assert (a) must consult the FakeFeedback mirror timestamps
#   to distinguish "decoder stalled" from "suppressed cycle" (fail only on the former).
# - commit() emits type_text(guarded_final) then a SEPARATE type_text(" ") when append_space —
#   screen reconstruction must treat them as two appends.
# - press_backspace(n<=0) must NOT be recorded (backend contract: no subprocess, no event).
# - PromptedExecutor probe warmup decodes 1 s of zeros AT CONSTRUCTION with prompt None —
#   filter warmup entries (t before first feed, or prompt is None with use_prompt True) from (d).
# - The executor serves BOTH partial and final decodes (one object, one model) — recorded
#   transcribe() calls interleave; the (d) oracle maps each call to the committed state at its
#   timestamp via the harness's commit event log.

# SHELL (AGENTS.md):
# - python3/pip are aliased interactively — always .venv/bin/python -m pytest or
#   /home/dustin/.local/bin/uv run pytest. Two timeouts on every heavy command
#   (inner `timeout 600`, bash-tool 900). This test spawns NO daemon and opens NO mic.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/test_streaming.py — in-file doubles (no production code changes)

@dataclasses.dataclass
class BackendEvent:            # timestamped keystroke record
    t: float                   # time.monotonic() at the call
    kind: str                  # "type" | "bs"
    text: str = ""             # for kind == "type"
    n: int = 0                 # for kind == "bs"

class RecordingTypingBackend(TypingBackend):
    """Records (t, kind, payload) per call + maintains a simulated screen buffer.

    Screen model: type_text appends; press_backspace(n) deletes exactly n chars
    (min 0). Thread-safe (called from the partial reader thread AND the commit path).
    """
    events: list[BackendEvent]
    def type_text(self, text) -> None: ...
    def press_backspace(self, n) -> None: ...   # n <= 0: no-op, NOT recorded (contract)
    @property def screen(self) -> str: ...      # simulated on-screen text
    def reset(self) -> None: ...                # per-test: clear events + screen

class RecordingPromptedExecutor(prompt_engine.PromptedExecutor):
    """Records (t, prompt, use_prompt) around every transcribe() + every set_prompt()."""
    decodes: list[tuple[float, str | None, bool]]
    prompts_set: list[tuple[float, str | None]]
    def transcribe(self, audio, language=None, use_prompt=True, **kw):  # record -> super()
    def set_prompt(self, text):                                     # record -> super()

class TimestampedFeedback:      # FakeFeedback + monotonic stamps (assert (a) liveness oracle)
    partials: list[tuple[float, str]]
    def update_partial(self, text): ...
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE tests/test_streaming.py — skeleton & guards
  - IMPLEMENT: module docstring citing PRD §6 T8 + the interpretation note ("lite recorder child"
    = the production child build path run in-process: cfg_to_kwargs + augment_kwargs_with_executor,
    same as tests/test_feed_audio.py constructs its recorder; child IPC itself is covered by
    tests/test_recorder_host.py — the factory seam is what makes assert (d) deterministic);
    WAV skip-guard pytestmark (mirror test_feed_audio.py G-SKIP-GUARDS); lazy _load_deps()
    namespace (np, sf, AudioToTextRecorder, daemon, recorder_host, prompt_engine, textproc,
    VoiceTypingConfig); pinned reference texts + _token_overlap helper (copy verbatim shape).
  - PLACEMENT: tests/test_streaming.py (new file).

Task 2: IMPLEMENT in-file doubles (data models above)
  - FOLLOW pattern: tests/test_streaming_core.py RecordingBackend/FakeFeedback (call recording,
    press_backspace(n<=0) not recorded) + ADD timestamps + screen buffer.
  - NAMING: RecordingTypingBackend, RecordingPromptedExecutor, TimestampedFeedback.
  - GOTCHA: backend methods are called from two threads (partial reader + commit glue) — a
    threading.Lock around events/screen appends.

Task 3: IMPLEMENT the recording executor factory + session recorder fixture
  - factory(model, device, compute_type) -> RecordingPromptedExecutor(model, device, compute_type);
    hold the returned instance (augment_kwargs_with_executor returns the armed executor).
  - FIXTURE `stream_recorder` (scope="session"): cfg = VoiceTypingConfig() (defaults already:
    streaming=true, context_prompt=true, lite_model="small.en"); kwargs =
    daemon.cfg_to_kwargs(cfg); kwargs["use_microphone"]=False; kwargs["no_log_file"]=True;
    wire callbacks: on_realtime_transcription_stabilized -> harness.on_partial,
    on_vad_start/on_vad_stop -> collector timestamps; THEN
    recorder_host.augment_kwargs_with_executor(kwargs, cfg, executor_factory=factory)
    (BEFORE the signature filter, mirroring recorder_host._worker_main's build order); finally
    daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder) -> construct.
  - SKIP cleanly (pytest.skip, never error) when: WAVs absent (module pytestmark), deps absent
    (_load_deps ImportError), recorder construction fails, or the executor probe raises
    (RuntimeError from augment) — CPU-only/clone boxes must see skips, not failures.
  - TEARDOWN: _safe_shutdown(recorder) on a helper daemon thread, join(30) — copy
    test_feed_audio.py's helper verbatim.

Task 4: IMPLEMENT the harness glue (daemon.on_final streaming branch, extracted)
  - CLASS StreamingHarness: owns StreamingOutput(backend=RecordingTypingBackend(),
    feedback=TimestampedFeedback(), streaming=True, append_space=True), the executor reference,
    a commit_log [(t, cleaned_text)], and:
      on_partial(text)  -> stream.on_partial(text)
      on_final(text)    -> mirror daemon.py L1112-1256 streaming branch:
                           if not listening: return; cleaned = textproc.clean(text, cfg.filter);
                           if not cleaned: return (keep the rejected-final shape for S2);
                           stream.commit(cleaned); stream.reset_boundary();
                           executor.set_prompt(prompt_engine.rolling_context_prompt(
                             stream.committed)); commit_log.append((monotonic, cleaned))
  - DOCSTRING: "faithful extraction of daemon.on_final's streaming branch — the daemon-level
    wiring itself is unit-tested in tests/test_daemon.py; T8 adds the REAL decode stream".
  - reset() per test: fresh stream/backend/feedback state; executor prompt cleared to None
    (executor.set_prompt(None)) and decodes list truncated after warmup.

Task 5: IMPLEMENT _run_utterance (feed + consume + wait + teardown)
  - FOLLOW pattern: test_feed_audio.py _run_utterance/_feed_paced/_consume/_wait_for verbatim
    shape (threads, stop event, helper-thread abort, joins with timeouts).
  - ADJUST: trailing paced silence 20 x 0.1 s (>= 2x the 0.8 s post_speech_silence_duration);
    want_finals per WAV (simple=1, pause=2 — the 3 s pause commits the first half, multi=3);
    after finals, sleep 0.5 s for in-flight partials to settle.

Task 6: TEST assert (a) — delta cadence + delta-only extends  [test_a_delta_cadence]
  - RUN utt_simple.wav; collect backend events + feedback partials.
  - ASSERT: >=3 "type" events during [first type event, commit]; every gap between consecutive
    type events <= 0.5 s OR a feedback partial arrived in that gap without producing a keystroke
    (suppressed/frozen cycle — legitimate); at least one extend cycle = a "type" event whose
    payload is a pure suffix continuation with NO "bs" event since the previous type event, and
    payload+prior_screen_tail is a prefix of the eventual committed utterance (fuzzy: tokens of
    the concatenated typed text overlap >= 0.80 with SIMPLE_TEXT).
  - ON FAILURE: dump events + partials (timestamps + payloads) — diagnostics are part of the test.

Task 7: TEST assert (b) — commit correction exactness  [test_b_commit_rewind_exact]
  - RUN utt_multi.wav (3 commits), then (conditionally) utt_punct.wav in the SAME session.
  - ASSERT after EVERY commit: harness screen == expected committed reconstruction (join of
    committed pieces with single spaces + trailing space; fuzzy per-piece via _token_overlap
    >= 0.80 against MULTI_TEXTS, but the SCREEN EQUALITY check itself is exact against the
    harness's own commit_log reconstruction).
  - ASSERT: every "bs" event that immediately precedes a commit retype has n == number of chars
    typed since the previous commit (tracked from the event stream); the retype lands the full
    guarded final; a trailing type_text(" ") follows (append_space=True).
  - ASSERT >= 1 revising commit across the run; if zero after utt_multi, feed utt_punct once
    (bounded retry) before failing with a full event dump.

Task 8: TEST assert (d) — rolling context prompt on decodes  [test_d_decode_prompts]
  - RUN utt_pause.wav (first half has NO terminator -> non-empty prompt case) and utt_multi.wav
    (every sentence ends '.' -> empty-prompt boundary case) in one session.
  - ORACLE: for each recorded decode (t, prompt, use_prompt) with use_prompt True and t after
    the first feed: expected = prompt_engine.rolling_context_prompt(committed_state_at(t)),
    where committed_state_at(t) comes from the harness commit_log (the committed string after
    the last commit with timestamp < t). Filter the construction-time warmup decode (prompt
    None before any feed).
  - ASSERT: recorded == expected for every such decode; after utt_pause's FIRST commit the
    second half's decodes carry a NON-EMPTY prompt whose tokens fuzzy-match PAUSE_A (>= 0.80);
    after each utt_multi sentence-final commit the expected (and recorded) prompt is "" ;
    every recorded prompt has <= 200 whitespace tokens (prompt_engine._PROMPT_TOKEN_CAP).
  - NOTE: also assert executor.prompts_set is non-empty (the glue refreshed it) — cheap smoke
    that the set_prompt path ran at all.

Task 9: VALIDATION (see Validation Loop) + fix until green.
```

### Implementation Patterns & Key Details

```python
# The recorder fixture core (mirrors test_feed_audio.py + recorder_host._worker_main order):
kwargs = daemon.cfg_to_kwargs(cfg)                 # single model small.en, use_main_model_for_realtime=True
kwargs["use_microphone"] = False                   # THE feed_audio override (PRD T8 "no mic")
kwargs["no_log_file"] = True
kwargs.update({
    "on_realtime_transcription_stabilized": harness.on_partial,   # G-REALTIME-CB
    "on_vad_start": collector.on_vad_start,                       # speech-window stamps
    "on_vad_stop": collector.on_vad_stop,
})
executor = recorder_host.augment_kwargs_with_executor(            # BEFORE the signature filter
    kwargs, cfg, executor_factory=recording_factory)              # probes (1 decode, prompt None)
assert executor is not None                                       # context_prompt=true -> armed
filtered = daemon._filter_kwargs_to_signature(kwargs, AudioToTextRecorder)
rec = AudioToTextRecorder(**filtered)

# The commit glue (extraction of daemon.on_final streaming branch, daemon.py ~L1112-1256):
def on_final(text: str) -> None:
    if not listening.is_set():                    # gate (kept for S2 parity)
        return
    cleaned = textproc.clean(text, cfg.filter)
    if not cleaned:                               # rejected: blocklist/min_chars — S2 extends
        return
    stream.commit(cleaned)                        # rewind+retype ONLY if final differs from tail
    stream.reset_boundary()                       # utterance boundary (lifts per-utterance freeze)
    executor.set_prompt(prompt_engine.rolling_context_prompt(stream.committed))
    commit_log.append((time.monotonic(), cleaned))

# Screen reconstruction invariant (assert b):
#   screen_after_commit == " ".join(committed_pieces) + " "   (append_space=True)
#   and for each rewind-before-retype: event.n == chars_typed_since_previous_commit
```

### Integration Points

```yaml
NO PRODUCTION CODE CHANGES: this task is test-only. If a seam turns out to be missing, prefer
adapting the TEST over modifying production modules; if a production change is truly unavoidable,
stop and report it (it would belong to a different work item).

PYTEST: tests/test_streaming.py is auto-collected by `pytest tests/`; keep collection cheap
  (no heavy imports at module scope) so fast sweeps and test_voicectl.py's import-purity check
  are unaffected.
GIT: commit the new file (+ nothing else) on main: "Add T8 streaming E2E harness with asserts a/b/d".
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_streaming.py --collect-only -q   # imports + guards OK, 0 errors
timeout 60 .venv/bin/python -c "import ast,pathlib; ast.parse(pathlib.Path('tests/test_streaming.py').read_text())"
# If ruff is configured (grep -n ruff pyproject.toml): timeout 60 /home/dustin/.local/bin/uv run ruff check tests/test_streaming.py --fix
# Expected: collection shows the new tests, no collection errors, no heavy-dep import at collect time.
```

### Level 2: Unit/Component Validation (the deliverable)

```bash
# THE gate for this task (CUDA model load is slow: first construction is tens of seconds):
timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q        # bash-tool timeout: 900
# If tests/out/*.wav are missing: ./tests/make_test_audio.sh first (bounded, ~seconds).
# Expected: 3 passed (test_a_delta_cadence, test_b_commit_rewind_exact, test_d_decode_prompts),
# 0 failed; skips acceptable ONLY for absent WAVs/deps/probe failure on a stripped box.
```

### Level 3: Integration (no regressions to siblings)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_commit.py \
  tests/test_streaming_freeze.py tests/test_prompt_engine.py -q        # fast units stay green
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_voicectl.py -q \
  # import purity + child IPC unaffected by the new file
# Expected: all pass. Any failure here means the new file polluted imports or duplicated coverage — fix.
```

### Level 4: Robustness / Domain-Specific

```bash
# Skip-guard behavior (fast-sweep safety): simulate a missing-fixture box.
mv tests/out /tmp/vt_wavs_stash && timeout 120 .venv/bin/python -m pytest tests/test_streaming.py -q; \
  rc=$?; mv /tmp/vt_wavs_stash tests/out; test $rc -eq 0   # must SKIP, not error, and restore the WAVs
# Flakiness probe (asserts must tolerate real-model nondeterminism): run the file twice more.
timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q && \
timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q
# Expected: green on repeated runs; if a run flakes, tighten the assert formulation (consult the
# G-tags / gotchas) rather than loosening thresholds silently — document any tolerance added.
# NOTE (boundary): full-suite runs, test_feed_audio.py adjustments, and ACCEPTANCE.md evidence
# rows belong to P1.M3.T9.S1 — do not do them here.
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1–4 commands above run with inner `timeout` + bash-tool timeout (AGENTS.md rule 1) — no command wedged, no daemon ever foregrounded.
- [ ] `timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -q` passes (repeatedly).
- [ ] Fast sibling suites (streaming_core/commit/freeze, prompt_engine, recorder_host, voicectl) still pass.
- [ ] Skip-guards verified: missing WAVs → skip, not error; WAVs restored afterwards.

### Feature Validation

- [ ] Assert (a): ≥1 typed delta per 500 ms during speech (suppressed cycles accounted via feedback mirror); at least one delta-only extend.
- [ ] Assert (b): screen == committed reconstruction after every commit; rewind n == exact tail length; trailing space present; ≥1 revising commit (bounded utt_punct retry).
- [ ] Assert (d): recorded decode prompts == `rolling_context_prompt(committed-at-time)`; non-empty mid-paragraph (utt_pause), empty after sentence-final commits (utt_multi); ≤200-token cap.
- [ ] No real keystrokes, no mic, no daemon/child process spawned; `no_log_file=True`.
- [ ] S2-extensibility: fixtures/harness reusable (c/e/f/g will extend THIS file); c/e/f/g NOT implemented here.

### Code Quality Validation

- [ ] Mirrors test_feed_audio.py conventions (G-tags, lazy deps, `_wait_for` house helper, pinned texts, fuzzy matching).
- [ ] Diagnostics: every failing assert dumps the event/partial log (timestamps + payloads).
- [ ] Only `tests/test_streaming.py` added; no production files modified; nothing else written outside this task's plan directory.

### Documentation & Deployment

- [ ] Module docstring documents: the T8 spec mapping (a/b/d), the in-process interpretation of "lite recorder child", and pointers to the G-invariants.
- [ ] Git commit on main with the message above.

## Anti-Patterns to Avoid

- ❌ Don't exact-match model output (espeak fixtures are fuzzy by design — ≥0.80 token overlap).
- ❌ Don't feed audio faster than real-time or skip the paced trailing silence (VAD is wall-clock — text() blocks forever).
- ❌ Don't call `recorder.abort()` from the test thread, or `shutdown()` inline (helper threads only).
- ❌ Don't import RealtimeSTT/torch/numpy at module scope (breaks collection + test_voicectl.py purity).
- ❌ Don't reimplement StreamingOutput/prompt logic in the test — drive the production classes; only the daemon glue is extracted (and documented as such).
- ❌ Don't implement asserts c/e/f/g "while you're there" — S2 owns them; keep the seams open.
- ❌ Don't spawn the daemon, a RecorderHost child, or any typing subprocess — RecordingTypingBackend only.
- ❌ Don't loosen a timing threshold on a flake without root-causing via the event dump (the 500 ms bound is the PRD contract; suppress-aware liveness checking is the correct relaxation).

---

**Confidence Score: 8.5/10** — one-pass success is high: every seam exists and is factory-injectable,
the harness pattern is proven in-repo (test_feed_audio.py), and the asserts have deterministic
oracles (screen reconstruction, harness-owned committed timeline). Residual risk: real-model
partial behavior (stabilized cadence under `use_main_model_for_realtime=True` + external executor)
may occasionally produce long suppressed stretches — the suppress-aware (a) formulation and the
bounded utt_punct retry for (b) are the specified mitigations.
