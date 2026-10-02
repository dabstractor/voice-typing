# Research — P1.M3.T8.S1 tests/test_streaming.py harness + RecordingTypingBackend + asserts a/b/d

Ground truth gathered 2026-07-21 from tests/test_feed_audio.py, tests/make_test_audio.sh,
voice_typing/typing_backends.py, plan/007 architecture docs (substrate_map.md §13, system_context.md
corrections), and the plan tree. This is a TEST-ONLY task: build the T8 streaming harness + the
RecordingTypingBackend double + asserts (a) delta cadence, (b) commit rewind/retype, (d) prompt
conditioning. The harness is REUSED by P1.M3.T8.S2 (asserts c/e/f/g).

---

## 1. Landed vs. NOT-landed inputs (decisive)

LANDED (verified):
- `typing_backends.py`: `TypingBackend` ABC with `type_text` (L58) + `press_backspace` (L69); concrete
  wtype/ydotool/null batched impls (P1.M1.T3.S1 Complete).
- Config schema incl. `[output] streaming` + `[cancel]` (P1.M1.T1.S1 Complete). Single-mode collapse
  (P1.M1.T2 Complete). `tests/test_streaming.py` does NOT exist.
- The model test: `tests/test_feed_audio.py` — real-model offline feeding w/ skip guards.

NOT landed (my INPUT contracts; PRPs for P1.M2.T5/T6 do not exist yet — derive from PRD §4.2quater +
substrate_map + system_context):
- **P1.M2.T6.S1/S2/S3** — the StreamingOutput state machine (committed/tail; partial path: diff →
  type delta-only or rewind+retype, full-rewind rate-limit ≥300 ms; commit path: correction pass, if
  differs from tail → rewind len(tail) + retype, then trailing space; freeze rules). Daemon wiring.
- **P1.M2.T5.S1** — child-side dynamic prompt: fork-inherited shared value + monkeypatch before
  recorder construction; startup capability probe; **on probe failure degrade to context-free + log
  ONCE**. Includes a report mechanism (child log/kwargs) the test asserts against.
- **P1.M2.T5.S2** — daemon-side prompt: committed text back to the last sentence boundary (last
  `./!/?`), capped ~200 tokens; `initial_prompt_realtime` (partials) + `initial_prompt` (commits).
→ **Task 0 preflight gate**: grep daemon.py for the streaming seams + the T5.S1 report mechanism;
if absent, STOP and report (they land before P1.M3 per plan ordering — this task runs after).

## 2. system_context.md corrections that shape the asserts (MUST honor)

- **Correction 2 (rules assert (d))**: single-model construction uses
  `use_main_model_for_realtime=True` → BOTH partial and final decodes go through the transcription
  WORKER SUBPROCESS (installed core/transcription.py:93-107 bakes initial_prompt at worker start).
  Dynamism = fork-inherited shared value + monkeypatch pre-construction. **T8d asserts prompts when
  dynamic mode is active, ELSE asserts the degrade log** — the test must branch on T5.S1's
  reported mode, not assume prompts.
- **Correction 1 (context for S2, harness must not misread)**: `RecorderHost.abort()` only unblocks
  `text()`; buffer discard is `_clear_recorder_audio` (recorder_host.py:586-620). Cancel = abort +
  clear + suppress the sentinel final. (S2's assert e depends on this; the S1 harness just records.)

## 3. The model to copy: tests/test_feed_audio.py (verbatim patterns)

- **Skip guards (G-SKIP-GUARDS)**: module-level `pytestmark = pytest.mark.skipif(not _have_wavs(),
  ...)`; `_have_wavs()` checks tests/out/*.wav presence WITHOUT imports; heavy deps lazily loaded in
  a session fixture `_load_deps()` that first checks `importlib.util.find_spec("faster_whisper")`
  BEFORE importing RealtimeSTT (keeps sys.modules clean → test_voicectl's import-purity check stays
  green when the full suite runs). TYPE_CHECKING-only type imports. **Copy these EXACTLY.**
- **Feeding (G-PACE)**: `_feed_paced(rec, samples_int16, stop, chunk_s=0.1, on_last_speech=None)` —
  feeds 16-bit mono @16k slices via `rec.feed_audio(slc, original_sample_rate=16000)`, sleeping each
  slice's wall-clock duration; **trailing silence must ALSO be paced** (fed as chunked zeros, never
  one big block — the VAD stop check is wall-clock per 32 ms frame). ~1.6 s trailing silence.
- **G-ORDER**: start the consume thread (text() arms listening) BEFORE the first feed.
- **Fuzzy (G-FUZZY)**: `_token_overlap` multiset helper (Counter-based, case/punct-insensitive),
  ≥80% bar (T8 keeps the PRD §6 note: espeak is robotic; deltas/commits assert fuzzily, cadence and
  rewind-counts assert EXACTLY).
- WAV loading: `soundfile.read(path, dtype="int16")` (from _load_deps).
- Fixtures: `tests/out/utt_simple.wav` (1 sentence), `utt_pause.wav` (3 s mid-silence),
  `utt_punct.wav`, `utt_multi.wav` (3 sentences @1.5 s gaps) — from `tests/make_test_audio.sh`.
  Fuzzy targets pinned verbatim in test_feed_audio (~L129) — copy.

## 4. The harness design (reusable by S2)

**RecordingTypingBackend(TypingBackend)** — the test double (subclass the real ABC; ~the shape of
test_daemon's `_FakeBackend` :493-504 but richer):
```python
class RecordingTypingBackend(TypingBackend):
    # calls: list[tuple[str, object, float]]  — ("type_text", text, t) / ("press_backspace", n, t)
    # screen: str — virtual screen: type_text appends; press_backspace(n) deletes n chars
    # tail: tracked externally by the driver (typed-since-checkpoint)
```
- records EVERY call with `time.monotonic()`; `type_text` appends to `screen`; `press_backspace(n)`
  deletes exactly n chars from `screen`'s end. `screen` lets any test assert on-screen text at any
  moment; `calls` gives cadence + ordering. NEVER a real subprocess (no subprocess.run at all).

**Driver (daemon-equivalent wiring)**: construct the real single-model recorder in-process
(test_feed_audio's exact kwargs: `model=cfg.asr.lite_model`, `realtime_model_type=lite_model`,
`use_main_model_for_realtime=True`, `use_microphone=False`, lite silence gate) and route its
stabilized-partial + final callbacks into the daemon's streaming seams — the same entry points the
child IPC dispatch calls. Inject `backend=RecordingTypingBackend()` via the daemon constructor
(test_daemon's `_make_lazy_daemon` pattern :2859-2867). Config: streaming=true (explicit), backend
field is irrelevant (injected). The exact seam NAMES come from T6.S2 — discover via Task-0 grep
(`grep -nE 'streaming|committed|tail' voice_typing/daemon.py`); the PRD behavior contract is fixed.

## 5. The three asserts (exact semantics)

- **(a) delta cadence**: while speech streams (during `_feed_paced` of utt_simple/utt_multi),
  consecutive `type_text` calls are ≤500 ms apart; and when a partial EXTENDS the tail, the call's
  text is ONLY the delta: `screen_after == screen_before + delta` and the recorded arg ==
  `new_tail[len(old_tail):]` (reconstruct + compare). (Full rewinds exist too — rate-limited ≥300 ms
  — but assert (a) targets the extend case; a rewind mid-stream is allowed, cadence still holds.)
- **(b) differing commit**: at a commit whose final differs from the typed tail: exactly
  `press_backspace(len(tail_chars))` then `type_text(final_text + " ")` (append_space=true default).
  Assert rewind count == chars typed since the checkpoint (count from the recording, don't guess),
  and screen == committed_prefix + final + " ". If NO commit differs across the fixtures, FAIL with a
  diagnostic (the differing-commit path is the contract under test; espeak+small.en reliably differs).
- **(d) prompt conditioning**: after ≥1 commit (committed non-empty), the child's decodes carry
  `initial_prompt` == committed text truncated at the last sentence boundary, capped ~200 tokens —
  assert via T5.S1's report mechanism (child log/kwargs). **Branch on the reported mode**: dynamic →
  assert the prompt values; degraded → assert the one-time degrade log instead (correction 2).

## 6. Constraints (AGENTS.md, binding)

- Heavy CUDA: `timeout 600 .venv/bin/pytest tests/test_streaming.py -q` and the bash-tool timeout
  set ABOVE 600 (use 700–900). Prefer this single file over suite-wide runs; don't interrupt mid-run.
- NEVER run the daemon in the foreground; no real keystrokes EVER (the RecordingTypingBackend is the
  only backend constructed; never call make_backend in this file).
- Skip cleanly when fixtures/deps absent (copy test_feed_audio's guards — a no-CUDA env must SKIP,
  not error). zsh aliases: full paths (.venv/bin/python; uv at /home/dustin/.local/bin/uv if needed).

## 7. Scope

- S1 = the harness + asserts (a)/(b)/(d) ONLY. Asserts (c) pause-join, (e) cancel, (f) key-freeze,
  (g) stranded tail are P1.M3.T8.S2 — they REUSE this harness; do not implement them here.
- Files: tests/test_streaming.py (NEW) — the ONLY new file. No daemon.py/textproc/backends edits
  (if a seam needed for testing is missing, that's a T6 contract gap → report, don't patch source).
- Parallel tasks (textproc guards T4, evdev listener T7.S2) are disjoint files.
- mypy not installed; ruff optional (/home/dustin/.local/bin/ruff).
