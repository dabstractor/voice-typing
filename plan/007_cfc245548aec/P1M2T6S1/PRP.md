# PRP — P1.M2.T6.S1: StreamingOutput core — partial path (diff/extend/revise, rate limit, guards, feedback mirror)

## Goal

**Feature Goal**: Build the daemon-side streaming output engine ("StreamingOutput") that turns
stabilized realtime partials from the recorder-host child into phone-style typed dictation:
extend the on-screen tail by typing only the delta when a partial extends it, rewind-and-retype
when a partial revises it, with full rewinds rate-limited and the deterministic casing/period
guards applied — while mirroring the live tail into the Feedback partial field.

**Deliverable**: A new class `StreamingOutput` (recommended: new pure-stdlib module
`voice_typing/streaming.py`, imported and wired by daemon.py in T6.S2) plus pure-python unit
tests `tests/test_streaming_core.py` (no CUDA, no mic, no real keystrokes).

**Success Definition**: All new unit tests pass under
`timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -q`; existing suites
(`tests/test_textproc.py tests/test_typing_backends.py tests/test_daemon.py`) still pass;
daemon behavior unchanged in this subtask (wiring into `_on_partial` is T6.S2 — S1 delivers the
engine + its tests only, except the minimal `self._stream` attribute the already-landed
`cancel()` seam probes defensively).

## Why

- PRD §4.2quater rule 1 ("Partial typing"): on each stabilized-partial event, diff against the
  currently typed tail — extend → type only the delta; revise → `press_backspace(len(revised_chars))`
  then type the corrected tail; full rewinds rate-limited ≥300 ms so a wobbling decode cannot
  flicker. This engine is the heart of Rev 2 streaming dictation.
- The `press_backspace(n)` primitive landed in P1.M1.T3.S1 (`typing_backends.py`); the guards
  landed with P1.M2.T4.S1; the `cfg.output.streaming` flag landed in P1.M1.T1.S1. This task is
  the first consumer of all three.
- Downstream: T6.S2 wires `on_partial`/commit into the daemon + rollback hatch; T6.S3 adds the
  freeze rules; T7.S1's already-landed `daemon.cancel()` calls `stream.pending_tail_len()` and
  `stream.reset_after_cancel()` via defensive getattr — **this task must provide those exact
  method names** so the seam snaps in.

## What

A single class owning the per-armed-session output state:

- `committed: str` — finalized text ending at the last commit checkpoint (S1 only maintains the
  field + accessors; T6.S2 advances it on commit).
- `tail: str` — everything typed since that checkpoint (tentative, revisable, **no trailing
  space while tentative**).
- `frozen: bool` — when True, on_partial suppresses ALL typing but still mirrors the tail into
  feedback (T6.S3 extends freeze triggers; S1 provides the mechanism + `freeze()` API).

`on_partial(text)` behavior (PRD §4.2quater rule 1, verbatim intent):
1. If `frozen` or streaming disabled → mirror only (no backend calls).
2. If `text` extends the current `tail` (tail is a prefix of text) → apply
   `apply_streaming_guards(committed, delta)` to the delta and `type_text(guarded_delta)`;
   never a trailing space.
3. If `text` revises the tail → `press_backspace(len(tail_chars))` then `type_text(guarded
   revised_tail)`; **full rewinds are rate-limited ≥300 ms apart (code constant, NOT config)** —
   if a full rewind fired less than 300 ms ago, skip this cycle (keep the current tail on
   screen, update nothing typed) so a wobbling decoder cannot flicker.
4. Every event mirrors the resulting tail into `feedback.update_partial(tail)`.

### Success Criteria

- [ ] Extend path types ONLY the delta (guarded), never re-types the whole tail.
- [ ] Revise path rewinds exactly `len(tail)` then types the corrected tail (guarded).
- [ ] A second full rewind within 300 ms is suppressed (no keystrokes, tail unchanged).
- [ ] No trailing space is ever typed while the tail is tentative.
- [ ] `frozen=True` suppresses typing but keeps the feedback mirror updating.
- [ ] `pending_tail_len()` returns the current tail length; `reset_after_cancel()` clears the
  tail, suppresses partial typing until the next utterance boundary, leaves `committed` intact.
- [ ] Pure stdlib module — importable in CPU-only/test contexts (no torch/ctranslate2/realtimestt
  imports anywhere in the new file).

## All Needed Context

### Context Completeness Check

An agent with zero prior knowledge of this repo can implement this from: the exact seam
descriptions below (with line anchors into the current files), the backend ABC contract, the
guards contract, the config flag, and the test-double pattern already used in
`tests/test_daemon.py`. No PRD ambiguity remains for the partial path.

### Documentation & References

```yaml
- file: voice_typing/typing_backends.py
  why: The backend this engine drives. TypingBackend ABC (:30-58) — type_text(text) exact text,
        press_backspace(n) batched single-subprocess delete, n<=0 no-op. make_backend(cfg.output)
        (:180-196). _WtypeWithFallback retries once via ydotool on (CalledProcessError, OSError).
  pattern: Call backend.type_text / backend.press_backspace directly; exceptions may propagate
        from real backends — the engine must not crash the partial thread (catch + log WARNING,
        see Implementation Patterns).
  gotcha: press_backspace(0) is already a no-op at the backend; still guard n>0 at call sites
        for symmetry with daemon.cancel().

- file: voice_typing/daemon.py (search anchors, current line numbers)
  why: THE seam. _on_partial :1075-1086 — today only feedback.update_partial + latency count;
        T6.S2 will route it to StreamingOutput.on_partial. _pending_tail_len :1108-1122 and
        _reset_stream_after_cancel :1124-1142 call stream.pending_tail_len() /
        stream.reset_after_cancel() via defensive getattr on self._stream — S1's class MUST use
        exactly these method names. cancel() :1143+ computes n = max(tail_len - 1, 0).
  pattern: Constructor-injected collaborators (host, feedback, latency, backend are all injected
        in VoiceTypingDaemon.__init__ ~:595-700); do the same for StreamingOutput.
  gotcha: Do NOT move/rename _on_partial in S1 — S1 delivers the engine; daemon wiring (routing
        _on_partial through it) belongs to T6.S2. The only daemon change in S1 (if any) is
        constructing/holding `self._stream` so cancel()'s getattr seam starts resolving — and it
        must be a safe no-op when cfg.output.streaming is false.

- file: voice_typing/textproc.py
  why: clean() (Rev 1, unchanged) + where the guard function belongs per the T4.S1 contract.
  gotcha: VERIFIED ABSENCE — at the time of this PRP, apply_streaming_guards does NOT yet exist
        in the codebase (grep 'apply_streaming_guards' returns nothing; textproc.py is 70 lines,
        clean() only). The T4 subtask's contract (tasks.json P1.M2.T4.S1 context_scope) defines
        it as: a PURE function alongside clean(),
        `apply_streaming_guards(committed: str, fragment: str) -> str`:
          (a) casing guard — if committed (rstripped of whitespace) does not end with a terminal
              '.' '!' '?', lowercase the fragment's first word's first cased/alphabetic char;
          (b) period guard — if the casing guard fired (joined mid-sentence) and the fragment
              (rstripped) ends with '.', strip exactly ONE trailing '.'.
        Because S1 must consume it NOW: implement apply_streaming_guards in textproc.py in this
        same subtask (small, pure, with its own unit tests in tests/test_textproc.py per the T4
        cases below) if it is still absent when you start. Check first: grep -rn
        apply_streaming_guards voice_typing/ — if present (T4 landed late), consume as-is.

- file: voice_typing/feedback.py
  why: update_partial(text) — already throttled ≥10 Hz internally (feedback.py ~:74-120); the
        engine calls it on every event and does NOT need its own throttle. NEVER triggers
        notifications (toasts are start/final/stop only).
  pattern: Inject the Feedback instance; call update_partial(tail) unconditionally per event.

- file: voice_typing/config.py
  why: OutputConfig.streaming (:135, validated bool, default True). AsrConfig.context_prompt
        exists but is T5.S2's concern — NOT used in S1.
  pattern: StreamingOutput takes the bool (or the OutputConfig) at construction.

- file: tests/test_daemon.py (~:466-632, :2859-2867)
  why: The established fake/test-double pattern to copy: _FakeHost/_StubRecorder/_FakeBackend
        with mic_prober=_ok_probe via _make_lazy_daemon. Reuse the _FakeBackend shape for the
        engine's unit tests (a tiny recording backend — note tests/test_typing_backends.py:274
        already has a no-real-subprocess guard to copy).
  pattern: Pure-python fakes; assert on recorded (method, arg) sequences and timestamps.

- url: https://github.com/KoljaB/RealtimeSTT
  why: upstream of the partial events (on_realtime_transcription_stabilized) — background only;
        S1 never touches RealtimeSTT (engine is fed plain strings by tests/daemon).
  critical: None needed for S1 — engine input is just `str`.
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── config.py          # OutputConfig.streaming landed (P1.M1.T1.S1)
├── daemon.py          # _on_partial seam :1075; cancel() seam :1108-1160 (landed, T7.S1)
├── feedback.py        # update_partial (throttled), record_final, toasts
├── recorder_host.py   # child owning AudioToTextRecorder (feeds partials via evt_q)
├── textproc.py        # clean() — apply_streaming_guards to land here (see gotcha above)
├── typing_backends.py # type_text + press_backspace(n) ABC + wtype/ydotool/null (P1.M1.T3.S1)
tests/
├── test_daemon.py         # fake-host/recorder/backend doubles pattern
├── test_textproc.py       # where guard unit tests belong
├── test_typing_backends.py# argv pins, n=0 no-op, batching, fallback ordering
```

### Desired Codebase tree with files to be added

```bash
voice_typing/
├── streaming.py       # NEW — StreamingOutput engine (pure stdlib; ~150-250 lines incl. docstring)
├── textproc.py        # MODIFIED — add apply_streaming_guards (only if absent at start)
├── daemon.py          # MINIMAL — construct self._stream (safe no-op when streaming=false);
│                      #   full _on_partial wiring is T6.S2, NOT here
tests/
├── test_streaming_core.py  # NEW — engine unit tests (fake backend, fake feedback)
├── test_textproc.py        # EXTENDED — apply_streaming_guards cases (if the fn landed here)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: Real backend subprocess failures (CalledProcessError/OSError) MUST NOT kill the
# partial thread — catch Exception per event, log WARNING, and FREEZE the tail (a failed
# rewind+retype leaves on-screen state unknown; safest is to stop revising that utterance).
# PRD §4.2quater: "typed text is never auto-deleted" — a failed backend call is the
# stranded-tail case; freezing is the S1-appropriate response (T6.S3 formalizes freeze reasons).

# CRITICAL: rate-limit applies to FULL REWINDS only. Delta typing (extends) is never
# rate-limited — it is additive and flicker-free by construction.

# DIFF SEMANTICS: "extends" means the OLD tail is a prefix of the new partial (after whitespace
# collapse). Partials from RealtimeSTT may re-capitalize or re-punctuate earlier words; any
# non-prefix is a revise. Character-level diffing is NOT needed — tail-prefix test + full
# rewind is the prescribed algorithm (PRD: "press_backspace(len(revised_chars)) then type the
# corrected tail"). Compare on the same normalization you type (guards are applied to what you
# TYPE, and tail tracks what you typed — not the raw partial).

# TAIL TRACKS TYPED TEXT, not the raw partial: store what was actually typed (guarded delta
# concatenated), so len(tail) always equals the chars the rewind must delete, and a later
# partial equal to the raw decode can still be a "revise" relative to the guarded tail.

# NO trailing space while tentative — only the commit path (T6.S2) appends
# output.append_space. A tentative delta must never end with ' '.

# Thread context: on_partial is called from the host reader thread (daemon thread); commit
# (T6.S2) from the on_final thread; cancel from the socket thread. Use a single internal
# threading.Lock inside StreamingOutput (short critical sections; never call the backend while
# holding it if avoidable — or accept it, matches daemon._on_final_lock style, but document).

# pending_tail_len()/reset_after_cancel() names are LOAD-BEARING: daemon.cancel() (:1118-1140)
# already calls them via getattr on self._stream. reset_after_cancel must ALSO suppress
# partial typing until the next utterance boundary — provide reset_boundary() (or a
# suppressed flag cleared by reset_boundary) so a stale late partial from the cancelled
# utterance cannot re-type text right after a cancel.
```

## Implementation Blueprint

### Data models and structure

No new config or ORM models. Engine state is internal strings + flags:

```python
@dataclass
class _StreamState:            # or plain attributes on StreamingOutput
    committed: str = ""        # finalized text through the last commit checkpoint
    tail: str = ""             # typed-but-tentative text since the checkpoint (no trailing space)
    frozen: bool = False       # True -> mirror only
    suppressed: bool = False   # True after cancel -> no typing until reset_boundary()
    last_full_rewind_monotonic: float = 0.0
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY/ADD apply_streaming_guards in voice_typing/textproc.py
  - RUN first: grep -rn apply_streaming_guards voice_typing/ tests/
  - IF ABSENT: add the pure function per the contract quoted in the Documentation section
    (casing guard on first alphabetic char of first word when committed doesn't end a sentence;
    strip exactly one trailing '.' when the casing guard fired). Keep clean() byte-identical.
  - ADD unit tests to tests/test_textproc.py: mid-sentence lowercases first word;
    after '.'/'!'/'?' preserves case; fragment already lowercase unchanged; fragment ending
    '...' strips exactly one '.'; empty committed (session start) preserves case; empty
    fragment safe; committed with trailing whitespace handled (rstrip).
  - NAMING: apply_streaming_guards(committed: str, fragment: str) -> str — exact signature
    (consumed by T6.S2 commit path too).

Task 2: CREATE voice_typing/streaming.py — class StreamingOutput
  - IMPLEMENT: __init__(backend: TypingBackend, feedback: Feedback, streaming: bool,
    *, rate_limit_s: float = 0.3, clock=time.monotonic)  # clock injectable for deterministic tests
  - IMPLEMENT API (exact names):
      on_partial(text: str) -> None          # §4.2quater rule 1 (see What section)
      freeze(reason: str = "") -> None       # set frozen (logged); keeps mirror
      reset_boundary() -> None               # new utterance: tail="", suppressed=False
        (frozen is NOT auto-cleared here — T6.S3 owns freeze lifecycle)
      pending_tail_len() -> int              # len(tail) — daemon.cancel() seam
      reset_after_cancel() -> None           # tail="", suppressed=True, committed unchanged
      tail / committed read-only properties  # T5.S2 + T6.S2 consume
  - FOLLOW pattern: voice_typing/typing_backends.py for docstring density + import purity
    (module scope stdlib only: logging, threading, time, dataclasses).
  - NAMING: StreamingOutput, snake_case methods, private attrs _-prefixed.
  - PLACEMENT: own module (NOT inside daemon.py — daemon.py is 2268 lines; keep the engine
    importable/testable without the daemon).

Task 3: MINIMAL daemon.py touch (only what makes the landed cancel seam truthful)
  - ADD in VoiceTypingDaemon.__init__ (near the backend construction ~:685):
        self._stream = streaming.StreamingOutput(backend, self._feedback, cfg.output.streaming)
  - DO NOT route _on_partial through it yet (that is T6.S2). Verify tests/test_daemon.py and
    test_control_socket.py still pass — cancel() with a real _stream must behave identically
    to the pre-T6 defensive path (pending_tail_len 0 when idle, idempotent no-op).
  - PRESERVE: everything else in __init__ ordering; _stream construction must not require
    models loaded (pure python object).

Task 4: CREATE tests/test_streaming_core.py
  - IMPLEMENT a RecordingBackend(TypingBackend) double appending ("type", text) /
    ("bs", n) tuples + a FakeFeedback capturing update_partial args; a fake clock (list of
    monotonic values) for deterministic rate-limit tests.
  - CASES (each a test function, test_<behavior>_<scenario> naming):
    * extend types only the delta: partial "hello wor" then "hello world" -> exactly one
      type_text("ld") (guarded), tail == "hello world"
    * extend with mid-sentence committed lowercases the delta's first word (guards applied
      to the DELTA: committed="Then he said", delta "the" stays lowercase)
    * session-start partial (committed="") preserves capitalization
    * revise rewinds + retypes: tail "hello wrld" then partial "hello world" ->
      press_backspace(10) then type_text("hello world") (guarded)
    * rate limit: two revises at t=0.0 and t=0.1 -> second suppressed (no second
      press_backspace; tail keeps the FIRST partial's text this cycle); at t=0.4 the
      revise goes through
    * no trailing space ever typed while tentative (scan all type_text args)
    * frozen=True: no backend calls at all, but update_partial still receives the tail
    * suppressed (post-cancel): on_partial mirrors only until reset_boundary()
    * pending_tail_len reflects tail; reset_after_cancel zeroes it and keeps committed
    * backend raises (fake backend raising on press_backspace) -> on_partial does not
      propagate; tail freezes (frozen becomes True), WARNING logged (caplog)
    * streaming=False: on_partial is mirror-only (no backend calls)
  - RUN: timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -q

Task 5: FULL AFFECTED-SUITE PASS
  - RUN: timeout 600 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_textproc.py tests/test_typing_backends.py -q
  - RUN (heavier, CUDA-loading): timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q
    (AGENTS.md: always inner timeout + harness timeout above it; never run the whole suite at once)
```

### Implementation Patterns & Key Details

```python
# Core on_partial sketch (adapt, don't copy blindly):
def on_partial(self, text: str) -> None:
    with self._lock:
        if self._suppressed or self._frozen or not self._streaming:
        # NOTE: if not self._streaming, tail stays "" — mirror raw text so voicectl status
        # still shows the Rev 1 partial. Mirror the RAW partial in the disabled/frozen path,
        # the TYPED tail in the streaming path.
            self._feedback.update_partial(text if not self._frozen else self._tail)
            return
        text = " ".join(text.split())                     # stable normalization
        if self._tail and text.startswith(self._tail):
            delta = text[len(self._tail):]
            if not delta:
                self._feedback.update_partial(self._tail); return
            guarded = textproc.apply_streaming_guards(
                self._committed + (" " if self._committed else ""), delta)  # casing context
            # GOTCHA: the guard needs the text preceding the delta for casing decisions —
            # when committed == "" the context is the tail itself (mid-utterance continuation).
            self._safe_type(guarded)
            self._tail += guarded
        else:  # revise (includes fresh start when tail == "")
            now = self._clock()
            if self._tail and now - self._last_full_rewind < self._rate_limit_s:
                self._feedback.update_partial(self._tail)  # keep screen; skip cycle
                return
            guarded = textproc.apply_streaming_guards(self._context(), text)
            self._safe_backspace(len(self._tail))
            self._safe_type(guarded)
            self._tail = guarded
            self._last_full_rewind = now
        self._feedback.update_partial(self._tail)

def _safe_type(self, s):        # backend failure must not kill the reader thread
    try: self._backend.type_text(s)
    except Exception: logger.warning(...); self._frozen = True; raise_tail_freeze
```

Decide the guard-context rule explicitly and test it: the "committed" string passed to
`apply_streaming_guards` for a DELTA mid-utterance is `committed + " " + tail_before_delta`
(its terminal-punctuation state governs casing); for a full revise it is `committed`.
Strip/skip-empty when either side is empty.

### Integration Points

```yaml
DAEMON (minimal, Task 3):
  - voice_typing/daemon.py __init__: self._stream = streaming.StreamingOutput(backend, self._feedback, cfg.output.streaming)
  - PRESERVE the existing getattr defensives in _pending_tail_len/_reset_stream_after_cancel
    (they become live but must behave identically while idle).

NOT in scope (later subtasks — do NOT implement):
  - routing _on_partial through self._stream          -> P1.M2.T6.S2
  - commit/correction pass, append_space, rollback hatch, on_final branch -> P1.M2.T6.S2
  - freeze triggers (stranded tail, user keypress, utterance boundary reset calls) -> P1.M2.T6.S3
  - context prompt refresh from committed             -> P1.M2.T5.S2
  - evdev listener                                    -> P1.M2.T7.S2
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# This repo has no ruff/mypy config — style = existing file conventions. Sanity:
timeout 60 .venv/bin/python -c "import voice_typing.streaming, voice_typing.textproc, voice_typing.daemon"
timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py --collect-only -q
```

### Level 2: Unit Tests

```bash
timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py -v
timeout 120 .venv/bin/python -m pytest tests/test_textproc.py tests/test_typing_backends.py -q
# heavier (loads fakes only but imports daemon machinery):
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py tests/test_control_socket.py -q
```

### Level 3: Integration (light — full wiring is T6.S2)

```bash
# Confirm the daemon still constructs with the stream attached, and cancel stays idempotent:
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k cancel
# No daemon process is started here; never run voice-typing-daemon in the foreground (AGENTS.md).
```

### Level 4: Domain-Specific

Not applicable — real-keystroke behavior is T8/T5 (manual smoke) territory; S1 is pure-python
and must never spawn a real subprocess in its tests (RecordingBackend pattern).

## Final Validation Checklist

### Technical Validation
- [ ] tests/test_streaming_core.py all green; tests/test_textproc.py, test_typing_backends.py,
      test_daemon.py (incl. -k cancel), test_control_socket.py all green
- [ ] `import voice_typing.streaming` works with no CUDA/torch/realtimestt anywhere in its scope
- [ ] apply_streaming_guards exists and is pure (no I/O), with its own unit tests

### Feature Validation
- [ ] Extend → delta-only typing; revise → exact-length rewind + guarded retype
- [ ] Full-rewind rate limit ≥300 ms enforced (code constant, not config)
- [ ] No trailing space while tentative; frozen/suppressed mirror-only; feedback mirror on
      every event; pending_tail_len/reset_after_cancel names match daemon.cancel() seam

### Code Quality
- [ ] Docstring density matches typing_backends.py/prompt_engine.py house style (module header
      explaining PRD mapping, CONSUMES/CONSUMED BY sections)
- [ ] No changes to on_final, drain machinery, or _on_partial body (T6.S2 territory)
- [ ] Nothing typed at import time; no threads started by the engine itself

## Anti-Patterns to Avoid

- ❌ Don't put StreamingOutput inside daemon.py — it must be testable without daemon machinery.
- ❌ Don't rate-limit delta typing (only full rewinds flicker).
- ❌ Don't track the raw partial as the tail — track what you TYPED (guarded), or the rewind
  length and prefix-diff drift apart.
- ❌ Don't let a backend exception escape on_partial — the reader thread dies and streaming
  silently stops; freeze + WARNING instead.
- ❌ Don't add new config keys — the 300 ms rate limit is a code constant per PRD §4.2quater.
- ❌ Don't implement the commit path, freeze triggers, prompt refresh, or _on_partial wiring —
  those are T6.S2/S3 and T5.S2; touching them now creates merge hazards for sibling PRPs.
- ❌ Don't re-derive clean() behavior — Rev 1 rules stay byte-identical.
