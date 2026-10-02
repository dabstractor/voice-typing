# PRP — P1.M3.T8.S1: `tests/test_streaming.py` — harness + RecordingTypingBackend + asserts a/b/d

## Goal

**Feature Goal**: Build PRD §6 **T8 (part 1)** — the reusable, no-mic, no-keystroke streaming-dictation test harness (`tests/test_streaming.py`) and its first three asserts: **(a)** typing deltas arrive ≥1 per 500 ms while speech streams and only the DELTA when a partial extends the tail; **(b)** a differing commit rewinds exactly the tail length then types the final text + trailing space; **(d)** the child's decodes carry `initial_prompt` = committed text back to the last sentence boundary, capped — or, when the child reported degraded, the one-time degrade log instead. The harness (double + paced feeding + timing capture) is REUSED by P1.M3.T8.S2 (asserts c/e/f/g).

**Deliverable** (ONE new file):
- `tests/test_streaming.py` — `RecordingTypingBackend` test double (records `(method, arg, monotonic_ts)`, maintains a virtual screen; never a real keystroke), the daemon-equivalent driver (real single-model recorder `use_microphone=False`, fed WAVs via paced `feed_audio`, routed into the daemon's streaming seams), test_feed_audio-style skip guards, and the (a)/(b)/(d) tests.

**Success Definition**:
- (a) During paced feeding of `utt_simple.wav`/`utt_multi.wav`: consecutive `type_text` calls ≤500 ms apart while speech streams; each extend-case call's text is exactly `new_tail[len(old_tail):]` and `screen == old_screen + delta`.
- (b) On a commit whose final differs from the typed tail: exactly `press_backspace(n)` with n == chars typed since the checkpoint, then `type_text(final + " ")`; screen ends `committed_prefix + final + " "`. No differing commit across fixtures → FAIL with diagnostics.
- (d) After ≥1 commit: if T5.S1 reports dynamic prompts → the child's decode prompts equal committed-text-to-last-sentence-boundary (capped); if degraded → the one-time degrade log is asserted instead.
- (e) `timeout 600 .venv/bin/pytest tests/test_streaming.py -q` passes (bash-tool timeout >600, use 900); skips cleanly (not errors) when WAVs/deps/CUDA absent; the rest of the suite is unaffected (skip guards keep sys.modules clean).
- (f) Only `tests/test_streaming.py` created — no source edits; no real subprocess/keystroke anywhere in the file.

## User Persona

**Target User**: The Rev 2 verification pass (P1.M3.T9/T10 + acceptance §7.11) which must demonstrate streaming behavior with real models but zero side effects.

**Use Case**: `timeout 600 .venv/bin/pytest tests/test_streaming.py -q` — proves delta cadence, in-place commit revision, and prompt conditioning on real small.en decodes of espeak fixtures, recorded via a double.

**Pain Points Addressed**: streaming behavior was previously only provable live (real mic, real keystrokes into the focused window — unacceptable in automation). The harness makes it offline, deterministic-ish, and assertable.

## Why

- PRD §6 T8 + acceptance §7.11 mandate it: ≥1 update/500 ms, in-place commits, prompt conditioning — all demonstrable only through this harness.
- S2 (asserts c/e/f/g) consumes this harness verbatim; building it right once (double + feeding + timing capture) unblocks the whole T8 pair.
- test_feed_audio.py already solved the hard parts (paced feeding, skip guards, fuzzy matching, sys.modules purity) — this is reuse, not invention.

## What

One new test file: skip guards copied from test_feed_audio; `RecordingTypingBackend(TypingBackend)` double; a driver constructing the real single-model recorder (`use_microphone=False`, lite kwargs) and routing partial/final callbacks into the daemon's streaming seams with the double injected as backend; paced WAV feeding; fuzzy helpers; tests for (a)/(b)/(d).

### Success Criteria

- [ ] `RecordingTypingBackend` subclasses the real `TypingBackend` ABC; records every `type_text`/`press_backspace` with `time.monotonic()`; maintains `screen` (append / delete-n); contains zero subprocess calls.
- [ ] Skip guards: `pytestmark` skips on missing WAVs without imports; `_load_deps` checks `find_spec("faster_whisper")` before importing RealtimeSTT; TYPE_CHECKING-only type imports.
- [ ] Driver: recorder kwargs = lite construction (`use_main_model_for_realtime=True`, `use_microphone=False`, lite silence gate); feeding is paced incl. trailing silence (~1.6 s of chunked zeros); consume side started before first feed.
- [ ] Tests (a), (b), (d) as specified above; (d) branches on T5.S1's reported mode.
- [ ] `timeout 600 .venv/bin/pytest tests/test_streaming.py -q` → pass (or clean skip on absent prereqs).
- [ ] `git status --short` shows only the new `tests/test_streaming.py`.

## All Needed Context

### Context Completeness Check

_Pass with one gate._ The model patterns (test_feed_audio) are pinned verbatim; the double + asserts are fully specified. The streaming seams come from P1.M2.T6.S2 and the prompt-report from P1.M2.T5.S1 — **not yet landed** (planned before this task). The PRP therefore fixes their BEHAVIOR contract (PRD §4.2quater) and mandates a Task-0 discovery grep; if the seams are absent at implementation time, STOP and report rather than guessing.

### Documentation & References

```yaml
# MUST READ — landed vs not-landed inputs, corrections 1/2, the model patterns, assert semantics, scope
- docfile: plan/007_cfc245548aec/P1M3T1S1/research/test_streaming_harness.md
  why: "§1 landed-vs-not (Task-0 gate). §2 corrections 1+2 (assert d branches on degraded mode; abort
        vs _clear_recorder_audio). §3 the test_feed_audio verbatim patterns (skip guards, _feed_paced,
        G-ORDER, G-FUZZY, fixtures + pinned fuzzy targets). §4 the harness design (double + driver).
        §5 the three asserts' exact semantics. §6 AGENTS.md constraints. §7 scope."
  section: "ALL load-bearing."

- file: tests/test_feed_audio.py
  why: "THE model — copy its skip guards (pytestmark + _have_wavs + _load_deps find_spec ordering),
        _feed_paced (chunked real-time feeding incl. paced trailing silence), consume-before-feed
        ordering, _token_overlap fuzzy helper, pinned fuzzy targets (~L129), WAV loading via soundfile."
  critical: "The find_spec-before-import ordering preserves tests/test_voicectl.py's import-purity
             check when the full suite runs. Trailing silence MUST be fed as paced chunked zeros,
             never one big block (the VAD stop check is wall-clock per 32 ms frame)."

- file: voice_typing/typing_backends.py
  why: "The ABC to subclass: type_text (L58) + press_backspace (L69) — landed by P1.M1.T3.S1."
  critical: "The double subclasses the real ABC; NEVER call make_backend in this file (no real
             keystrokes — inject the double via the daemon's backend= constructor arg)."

- docfile: plan/007_cfc245548aec/architecture/system_context.md
  why: "Correction 2 (rules assert d): with use_main_model_for_realtime=True both decodes go through
        the worker subprocess; T5.S1 dynamism = fork-shared value + monkeypatch + startup probe, else
        degrade-and-log-once — T8d asserts prompts ONLY when dynamic, else the degrade log. Correction
        1 (S2 context): abort() doesn't discard buffers; _clear_recorder_audio does."
  critical: "Assert (d) MUST branch on the reported mode — assuming prompts always exist fails on a
             degraded child."

- docfile: plan/007_cfc245548aec/architecture/substrate_map.md
  why: "§13 the tests inventory (shapes of every sibling suite) + §1 config schema (output.streaming,
        cancel config) + §5 typing_backends map."
  critical: "test_config_repo_default pins exact config keys — this task adds NO config keys."

- file: PRD.md
  why: "§6 T8 (the asserts a–g spec) + §4.2quater (the streaming state machine: committed/tail,
        delta-only extends, rewind+retype on revise/commit, ≥300 ms full-rewind rate limit, trailing
        space at commit, guards). §4.2ter (the lite/single-model construction the driver uses)."
  critical: "READ-ONLY. The behavior contract for the T6 seams this harness drives."

- file: tests/test_daemon.py
  why: "The daemon-injection pattern: _FakeBackend :493-504, _make_lazy_daemon :2859-2867 — how to
        construct the daemon with an injected backend without CUDA."
  critical: "Read-only reference for the injection idiom; heavy CUDA stays OUT of unit-style tests —
             this file's recorder IS the real model (heavy), gated by skip guards."
```

### Current Codebase tree (excerpt)

```bash
tests/
  test_feed_audio.py        # THE model (skip guards, _feed_paced, fuzzy) — copy patterns
  make_test_audio.sh        # generates tests/out/utt_{simple,pause,punct,multi}.wav
  out/                      # the WAV fixtures (may need regen: ./tests/make_test_audio.sh)
  test_streaming.py         # ← CREATE (this task; the only new file)
voice_typing/
  typing_backends.py        # TypingBackend ABC (type_text + press_backspace) — LANDED
  daemon.py                 # streaming seams arrive from P1.M2.T6.S2 (Task-0 gate)
  recorder_host.py          # prompt report arrives from P1.M2.T5.S1 (Task-0 gate)
```

### Desired Codebase tree

```bash
tests/test_streaming.py   # NEW — harness (RecordingTypingBackend + driver + feeding + fuzzy) + asserts a/b/d.
# NOTHING ELSE. No source edits. S2 extends this file with asserts c/e/f/g later.
```

### Known Gotchas

```python
# CRITICAL #1 — TASK-0 GATE: the streaming seams (P1.M2.T6.S2) + prompt-report (P1.M2.T5.S1) are NOT
#   landed at PRP time. First action: grep -nE 'stream|committed|tail' voice_typing/daemon.py and
#   grep the T5.S1 report symbol. Absent → STOP and report (they land before P1.M3 per plan order).
#   Do NOT patch daemon.py to add seams — that's T6's deliverable, not this task's.

# CRITICAL #2 — ASSERT (d) BRANCHES ON THE REPORTED MODE (system_context correction 2). Dynamic →
#   assert prompt values (committed-to-last-boundary, capped); degraded → assert the one-time degrade
#   log. Assuming prompts always exist fails on a degraded child; assuming degradation fails on dynamic.

# CRITICAL #3 — PACED TRAILING SILENCE. feed_audio is non-blocking; the VAD stop threshold is WALL-CLOCK
#   per 32 ms frame. Feed ~1.6 s of trailing silence as chunked paced zeros (copy _feed_paced verbatim),
#   never one big np.zeros block — else no commit ever fires and (b)/(d) cannot be tested.

# CRITICAL #4 — NO REAL KEYSTROKES, EVER. The double is the ONLY backend constructed; never make_backend.
#   Inject via the daemon's backend= arg (test_daemon's _make_lazy_daemon idiom).

# CRITICAL #5 — SKIP, DON'T ERROR. Copy test_feed_audio's guards exactly: pytestmark on WAV presence
#   (import-free), _load_deps with find_spec("faster_whisper") BEFORE importing RealtimeSTT, lazy heavy
#   imports in the fixture. A no-CUDA/no-fixture env must SKIP cleanly; sys.modules must stay clean at
#   collection (test_voicectl's import-purity check).

# GOTCHA #6 — heavy CUDA: timeout 600 wrapper on every pytest invocation; bash-tool timeout ABOVE it
#   (900). Single file runs only; never foreground the daemon (AGENTS.md Rule 2). Don't interrupt mid-run.

# GOTCHA #7 — (b) counts the rewind from the RECORDING (chars typed since the checkpoint), never a
#   precomputed guess; if no commit differs across the fixtures, FAIL with diagnostics (the differing
#   path is the contract under test — espeak+small.en reliably differs).

# GOTCHA #8 — full-path tools (.venv/bin/python; uv at /home/dustin/.local/bin/uv); mypy NOT installed;
#   ruff optional (/home/dustin/.local/bin/ruff).
```

## Implementation Blueprint

### Data models and structure

```python
class RecordingTypingBackend(TypingBackend):
    """Test double: records every call with monotonic ts; keeps a virtual screen. No subprocess."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, float]] = []   # (method, arg, time.monotonic())
        self.screen: str = ""                              # type_text appends; press_backspace(n) deletes n
    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text, time.monotonic())); self.screen += text
    def press_backspace(self, n: int) -> None:
        self.calls.append(("press_backspace", n, time.monotonic())); self.screen = self.screen[:-n] if n else self.screen
```

### Implementation Tasks (ordered)

```yaml
Task 0: PREFLIGHT GATE — discover the T6/T5 seams (no mutation)
  - RUN: ls tests/out/*.wav || ./tests/make_test_audio.sh   # regen fixtures if absent (bounded)
    grep -nE 'stream|committed|tail|StreamingOutput' voice_typing/daemon.py
    grep -nE 'initial_prompt|prompt_report|degrad' voice_typing/recorder_host.py voice_typing/daemon.py
  - EXPECTED: the streaming seams (T6.S2) + the prompt-report symbol (T5.S1) are present.
    ABSENT → STOP and report exactly which contract is missing. DO NOT patch source.

Task 1: CREATE tests/test_streaming.py — scaffold (guards + fixtures + fuzzy)
  - Copy from test_feed_audio: pytestmark skipif on _have_wavs(); _load_deps with find_spec ordering;
    TYPE_CHECKING imports; _token_overlap; pinned fuzzy targets; WAV loading. Module docstring with the
    run command (timeout 600 ...) + the G-* invariant comments.

Task 2: ADD the double + driver
  - RecordingTypingBackend (above). Driver: build cfg (streaming=true), construct the real single-model
    recorder (lite kwargs, use_microphone=False), construct the daemon with backend=the double, route the
    recorder's stabilized-partial + final callbacks into the daemon's streaming seams (the same entry
    points the child IPC dispatch calls — names from Task 0). _feed_paced copy incl. paced trailing silence;
    consume side started before the first feed (G-ORDER).

Task 3: ADD asserts (a)/(b)/(d)
  - test_delta_cadence_while_speaking (utt_simple + utt_multi): consecutive type_text gaps <=500 ms during
    speech; extend-case arg == new_tail[len(old_tail):]; screen reconstruction holds.
  - test_differing_commit_rewinds_tail_then_types_final_plus_space: first differing commit → exactly
    press_backspace(chars_since_checkpoint) then type_text(final + " "); screen check; no-differing-commit
    → fail with diagnostics.
  - test_commit_prompts_conditioned_on_committed_text (utt_multi, after >=1 commit): branch on T5.S1's
    reported mode — dynamic → assert prompt == committed-to-last-boundary capped; degraded → assert the
    one-time degrade log.

Task 4: VALIDATE
  - timeout 600 .venv/bin/pytest tests/test_streaming.py -q        (bash timeout 900)
  - timeout 600 .venv/bin/pytest tests/test_voicectl.py -q          (import purity unaffected)
  - grep -c 'subprocess\|make_backend' tests/test_streaming.py      (expect 0)
```

### Implementation Patterns & Key Details

```python
# Delta check (assert a): the recorded arg is the SUFFIX DELTA, and the screen grew by exactly it:
delta = calls[i].arg; assert calls[i].t - calls[i-1].t <= 0.5
assert old_screen + delta == new_screen and delta == new_tail[len(old_tail):]

# Commit check (assert b): count chars typed since the checkpoint from the RECORDING:
rewinds = [c for c in calls if c.method == "press_backspace"]
# the differing commit's rewind == chars typed since checkpoint; followed by type_text(final + " ")

# Prompt check (assert d): BRANCH (correction 2):
if report.dynamic: assert report.initial_prompt == committed_to_last_boundary(committed)[:cap]
else: assert "degrade" in caplog.text  # the one-time log
```

### Integration Points

```yaml
CONSUMED (must exist at implementation time — Task-0 gate):
  - daemon streaming seams: "P1.M2.T6.S2 — partial path (delta/rewind+retype) + commit path"
  - prompt report: "P1.M2.T5.S1 — dynamic-prompt report + degrade log"
  - TypingBackend ABC: "LANDED — type_text + press_backspace"
REUSED BY: "P1.M3.T8.S2 (asserts c/e/f/g) extends this file's harness"
NO new config keys, no source edits, no socket surface.
```

## Validation Loop

### Level 1: Syntax (immediate)
```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile tests/test_streaming.py && echo OK
grep -cE 'subprocess|make_backend' tests/test_streaming.py   # expect 0
```

### Level 2: The suite (heavy CUDA — the gate)
```bash
timeout 600 .venv/bin/pytest tests/test_streaming.py -q     # bash-tool timeout: 900
# Expected: all pass, or clean skips when fixtures/deps absent. No real keystrokes (grep in L1).
```

### Level 3: No collateral damage
```bash
timeout 120 .venv/bin/pytest tests/test_voicectl.py -q      # import purity unaffected
git status --porcelain                                     # only ?? tests/test_streaming.py
```

### Level 4: Domain
Asserts a/b/d semantics are the test itself; a manual daemon run is FORBIDDEN (AGENTS.md Rule 2).

## Final Validation Checklist

- [ ] Task-0 gate passed (seams found; or STOP reported).
- [ ] `timeout 600 .venv/bin/pytest tests/test_streaming.py -q` green (or clean skip).
- [ ] Double records (method, arg, ts); screen maintained; zero subprocess/make_backend in the file.
- [ ] Asserts a/b/d implemented per §5 of the research note; (d) branches on the reported mode.
- [ ] Skip guards copied verbatim (WAV check + find_spec ordering); test_voicectl still green.
- [ ] Only `tests/test_streaming.py` added.

## Anti-Patterns to Avoid

- ❌ Don't patch daemon.py/recorder_host.py to add missing seams — report and stop (Task-0 gate).
- ❌ Don't assert (d) unconditionally — branch dynamic vs degraded (correction 2).
- ❌ Don't feed trailing silence as one big block — pace it (correction: VAD is wall-clock).
- ❌ Don't construct a real backend or run the daemon foreground — the double only, injected.
- ❌ Don't implement asserts c/e/f/g — S2 owns them.
- ❌ Don't import RealtimeSTT at module top — lazy deps only (sys.modules purity).
- ❌ Don't run pytest without the timeout wrapper / with the bash timeout below 600.

---

**Confidence Score: 8/10** — the model patterns, double design, assert semantics, and constraints are fully pinned; the residual risk is the not-yet-landed T5/T6 seams, mitigated by the Task-0 discovery gate + the fixed PRD behavior contract (this task runs after they land per plan ordering).
