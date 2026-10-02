# PRP — P1.M2.T6.S2: Commit correction pass + rollback hatch + daemon wiring

## Goal

**Feature Goal**: Complete the streaming output state machine by implementing the **commit
(correction pass) path** and **wiring the whole streaming engine into the daemon**: when the
recorder-host child's silence-triggered "final" (the small.en re-decode of the complete
utterance) arrives, the daemon corrects the on-screen tail in place (rewind + retype if the
final differs from what was typed), appends the trailing space, advances the commit checkpoint,
and refreshes the rolling context-prompt seam. The Rev 1 append-only path is preserved verbatim
behind `output.streaming=false` as the rollback hatch.

**Deliverable**:
1. `StreamingOutput.commit(final_text)` (+ `reset_session()`, + `advance_checkpoint_frozen()`
   or equivalent) in `voice_typing/streaming.py`.
2. Daemon wiring in `voice_typing/daemon.py`: `_on_partial` routes through `self._stream`;
   `on_final` branches on `cfg.output.streaming` (streaming commit path vs unchanged Rev 1
   append path); session reset on `_arm`/`_disarm`; a thin defensive context-prompt push.
3. A small `RecorderHost.set_prompt(text)` proxy (the child ALREADY handles the
   `("prompt", {"text": ...})` command — only the daemon-side proxy is missing; P1.M2.T5.S2
   owns the full daemon-side prompt computation).
4. Unit tests: new `tests/test_streaming_commit.py` (pure, RecordingBackend double) +
   daemon-level tests for both output modes.

**Success Definition**: `timeout 120 .venv/bin/python -m pytest tests/test_streaming_commit.py
tests/test_streaming_core.py -q` passes; `timeout 300 .venv/bin/python -m pytest
tests/test_daemon.py -q -k "stream or final or partial"` (or the relevant -k subset) passes;
with `output.streaming=true` a final that matches the typed tail types ONLY the trailing space,
a differing final rewinds exactly `len(tail)` chars and retypes; with `false`, daemon behavior
is byte-for-byte the pre-existing Rev 1 path (no StreamingOutput backend calls at all).

## Why

- PRD §4.2quater rule 2 (**Commit**): "The child's small.en re-decodes the complete utterance
  (the old 'final', now a *correction pass*): if it differs from the typed `tail`, rewind +
  retype; append the trailing space (`output.append_space`); advance the checkpoint; refresh
  the rolling context prompt." S1 (`P1.M2.T6.S1`, COMPLETE) built the partial path and the
  `committed` field but explicitly left commit to this task.
- S1's module docstring names this task: *"commit will come from the on_final thread (T6.S2)"*,
  *"partial routing + commit path land in P1.M2.T6.S2 via on_partial/reset_boundary"*, *"T5.S2
  consumes the `committed` property for the context-prompt refresh"*.
- The rollback hatch is an acceptance criterion: "output.streaming=false restores Rev 1
  append-only behavior" (PRD §7 #11).

## What

### Commit semantics (PRD §4.2quater rule 2, exact)

`StreamingOutput.commit(final_text: str) -> None` — called from the daemon's `on_final` on the
reader/worker thread, while the daemon's `_on_final_lock` is held (same thread serialization as
today). Under the engine's internal `_lock` (same lock discipline as `on_partial` — see S1's
threading note; commit and partials are serialized so no interleaving):

1. Normalize `final_text` the same way `on_partial` does (`" ".join(text.split())`).
2. **If frozen**: do NOT touch the backend (typed text is never auto-deleted — PRD rule 4 and
   S1's failure policy). The frozen typed tail becomes the de-facto committed text for
   on-screen continuity: advance `committed` by the TYPED tail (screen truth), clear the tail
   WITHOUT keystrokes, lift suppression, return. (Freeze lifecycle triggers remain T6.S3's;
   commit only needs to not strand state across the boundary.)
3. **If the final extends the tail** (tail is a prefix of the normalized final): type only the
   guarded delta (`apply_streaming_guards(committed + " " + tail, delta)` — same context shape
   as `_guard_context_delta`). NO rate limit (commits are authoritative, not wobble).
4. **If the final differs** (revise/rewrite/shorter): `press_backspace(len(tail))` then
   `type_text(guarded_final)` — full rewind, NOT rate-limited (a commit is once per utterance;
   the ≥300 ms limiter exists only for wobbly partial cycles).
5. Append the trailing space iff `cfg.output.append_space` — this is the ONLY code that ever
   types a space while the engine is live (pass `append_space: bool` into
   `StreamingOutput.__init__` alongside `streaming`; S1's constructor already takes keyword
   args, extend it).
6. Advance the checkpoint: `committed` gains the final (guarded) text + the space; then clear
   the tail + lift suppression (equivalent of `reset_boundary()` — reuse it or inline).
7. Mirror the final text into `feedback.update_partial(...)` (matches `record_final`'s existing
   behavior of writing the final back into the partial field — see `feedback.py:153` and the
   PRD §4.6 note).
8. Backend failure inside commit: same fail-safe as S1 — log WARNING, freeze, NEVER propagate
   (the tail stays frozen on screen = PRD "stranded tail freezes", T6.S3 formalizes).

### Rejected final (textproc gate) under streaming

In `daemon.on_final`, when `textproc.clean()` returns `None` (blocklist / min_chars): under
streaming mode FREEZE the tail as-is (PRD §4.2quater rule 2: "a rejected final freezes the tail
as-is"), reset the boundary, and STILL run the latency-log/final-pending bookkeeping so drain
and idle logic stay correct. Do not rewind. (Under non-streaming mode, behavior is exactly
today's: plain early return.)

### Daemon wiring

- `_on_partial` (`daemon.py:1088`): replace the direct `self._feedback.update_partial(text)`
  with `self._stream.on_partial(text)` — the engine already mirrors into feedback on every
  path (streaming disabled = verbatim raw-partial mirror, Rev 1 parity). Keep the
  `self._latency.note_partial(text)` call exactly where it is.
- `on_final` (`daemon.py:963`): keep the listening gate, `_on_final_lock`, and the
  `_cancel_suppress_final` window EXACTLY as-is. After `clean()` succeeds and the
  `_final_pending`/`_utterance_finalized` flags are set, branch:
  - `cfg.output.streaming` False → the existing body verbatim (clean → `payload = cleaned +
    space` → `self._backend.type_text(payload)` → `record_final` → latency log). This is the
    rollback hatch; do not route it through `self._stream` (its backend calls must be provably
    absent in this mode).
  - True → `self._stream.commit(cleaned)` → `self._feedback.record_final(cleaned)` → the SAME
    structured latency `logger.info` line (tests parse it) → `self._refresh_context_prompt()`.
    Backend exceptions are already contained inside the engine (fail-safe freeze), so no
    try/except is needed around `commit()` — but wrap defensively to preserve the "on_final
    thread must survive" invariant.
- **Session reset**: add `StreamingOutput.reset_session()` clearing `committed`, `tail`,
  `suppressed`, AND `frozen` (a fresh arm legitimately unfreezes — this is a NEW session; note
  in the docstring that T6.S3 owns freeze triggers, reset_session owns session lifecycle). Call
  it from `_arm()` (`daemon.py:~1029`) and `_disarm()`. On disarm the pending tail simply
  stays typed (stranded-freeze is T6.S3's domain; the strings reset for the next session).
- **Context-prompt push (thin seam)**: `daemon._refresh_context_prompt()` — reads
  `self._stream.committed`, slices back to the last sentence boundary (last `.` `!` `?`), and
  calls `self._host.set_prompt(sliced)` if the host exposes it (defensive `getattr`, mirroring
  the `_pending_tail_len` seam style at `daemon.py:1125`). Slice helper = pure function, put it
  in `voice_typing/streaming.py` (e.g. `context_after_last_boundary(committed)`) so it is
  unit-testable; P1.M2.T5.S2 will formalize/extend the daemon-side computation — keep this
  minimal and documented as the S2 seam.
- **`RecorderHost.set_prompt(text)`** (`voice_typing/recorder_host.py`, next to
  `set_microphone`/`abort` at ~line 252): `self._cmd_q.put(("prompt", {"text": text}))`,
  fire-and-forget, never raises (guard queue-full like `_safe_put`/existing puts). The child's
  command loop ALREADY dispatches `("prompt", ...)` → `prompt_executor.set_prompt`
  (`recorder_host.py:702`, landed in T5.S1). If no executor was armed (degrade path), the child
  ignores it safely — verify/ensure the child's `"prompt"` branch tolerates a `None` executor.

### Success Criteria

- [ ] Commit where tail is a prefix of the final: only the guarded delta + trailing space typed.
- [ ] Commit that differs: exactly `press_backspace(len(tail))` then the guarded final + space.
- [ ] Commits are NOT subject to the ≥300 ms full-rewind rate limit.
- [ ] Checkpoint advances; next utterance's partials diff against the empty tail; casing guard
      uses the new `committed` (mid-paragraph → lowercase first word, stripped spurious period).
- [ ] Rejected final (blocklist/min_chars) under streaming: tail frozen as-is, no rewind, drain
      bookkeeping (`_final_pending`, `_utterance_finalized`) still runs.
- [ ] `frozen` commit: no backend calls, tail absorbed into committed without keystrokes.
- [ ] `output.streaming=false`: daemon on_final path identical to today (assert zero
      StreamingOutput backend calls); `_on_partial` still mirrors raw partials via the engine.
- [ ] `_refresh_context_prompt()` sends committed-text-since-last-sentence-boundary to the host
      seam after every commit; missing host method = silent no-op (logged at DEBUG).
- [ ] All existing suites still pass (`test_streaming_core.py`, `test_daemon.py`, `test_voicectl.py`).

## All Needed Context

### Context Completeness Check

An agent with zero prior knowledge of this repo can implement this from: the exact current
code excerpts and line anchors below, the S1 engine contract (reproduced in summary), the
backend/guards/feedback contracts, and the established test-double patterns. No PRD ambiguity
remains for the commit path.

### Documentation & References

```yaml
- file: voice_typing/streaming.py
  why: THE module being extended — StreamingOutput (S1, COMPLETE). Read fully before editing.
  pattern: lock discipline (one threading.Lock; backend calls held under it, safe because
    cancel() waits at most ~150 ms), fail-safe _safe_type/_safe_backspace (freeze, never
    propagate), feedback mirror on EVERY path, tail stores the GUARDED typed text.
  gotcha: "committed" is currently write-never (property only) — S2 makes commit() advance it.
    reset_boundary() deliberately does NOT clear `frozen` (T6.S3 owns that) — do not change it;
    reset_session() is the new session-lifecycle method that DOES.

- file: voice_typing/daemon.py
  sections: on_final (line ~963-1028), _on_partial (line ~1088), _arm (~1029), _disarm
    (~1050+), __init__ _stream construction (~line 697), _pending_tail_len seam (~1125).
  why: the wiring site. on_final's gate/_on_final_lock/_cancel_suppress_final logic is
    load-bearing (race guards, cancel window) — keep it IDENTICAL and branch only after
    clean() succeeds.
  gotcha: on_final runs on the host READER thread; _on_partial on the same reader thread —
    serialized with _on_final_lock only if you take it; commit() must be called INSIDE the
    _on_final_lock critical section so a racing cancel() cannot interleave rewind keystrokes.
  gotcha: the structured latency logger.info line (prefix _LATENCY_LOG_PREFIX) is parsed by
    tests — emit it on BOTH paths.

- file: voice_typing/recorder_host.py
  sections: set_microphone/abort/cancel (~252-292), _dispatch (~409), child cmd loop "prompt"
    branch (line 702), augment_kwargs_with_executor (~743), _safe_put (~728).
  why: add set_prompt proxy; confirm the child "prompt" branch no-ops safely when the executor
    degraded to None.

- file: voice_typing/prompt_engine.py
  why: T5.S1 (COMPLETE) — PromptedExecutor.set_prompt trims to 200 tokens itself; the daemon
    seam only supplies the boundary-sliced text. trim_prompt is already cap-safe.
  gotcha: do NOT import prompt_engine in daemon.py in a way that pulls CUDA — it is stdlib-only
    at module scope, but you do not need to import it in the daemon at all.

- file: voice_typing/textproc.py
  why: apply_streaming_guards(committed_context, fragment) signature (line 82) and clean() (41).

- file: voice_typing/feedback.py
  why: record_final(cleaned) (~line 153) also writes the final into the partial field (PRD
    §4.6) — under streaming, call record_final(cleaned) AFTER commit() so the state file shows
    the corrected text; the engine's own mirror covers the interim.

- file: tests/test_streaming_core.py
  why: the established test doubles — RecordingBackend (records ("type_text", s) /
    ("press_backspace", n); press_backspace(<=0) NOT recorded), FakeFeedback, FakeClock,
    _make_stream, _typed(backend). REUSE these (import or copy) in test_streaming_commit.py.

- file: tests/test_daemon.py
  why: daemon-level test pattern — _FakeBackend, in-process stub recorder host whose text()
    fires on_final in-process (see daemon.py docstring ~line 464), no CUDA needed when using
    the stub host. Follow the existing fake-host fixtures for the two-mode on_final tests.

- docfile: plan/007_cfc245548aec/architecture/realtimestt_internals.md
  why: verified RealtimeSTT 1.0.2 facts backing the executor/prompt design (already landed).

- docfile: plan/007_cfc245548aec/P1M2T6S1/PRP.md
  why: the S1 contract this PRP builds on (seam names are load-bearing:
    pending_tail_len/reset_after_cancel already called by daemon.cancel()).
```

### Current Codebase tree (relevant excerpt)

```bash
voice_typing/
├── daemon.py            # MODIFY: _on_partial routing, on_final branch, _arm/_disarm reset,
│                        #        _refresh_context_prompt seam
├── streaming.py         # MODIFY: commit(), reset_session(), context_after_last_boundary(),
│                        #        __init__ gains append_space kwarg
├── recorder_host.py     # MODIFY: RecorderHost.set_prompt proxy
tests/
├── test_streaming_commit.py   # CREATE (pure unit tests, S1 double pattern)
└── test_daemon.py             # EXTEND: two-mode on_final/_on_partial tests (stub host)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL repo rule (AGENTS.md): voicectl/pytest can hang — ALWAYS wrap:
#   timeout 120 .venv/bin/python -m pytest tests/test_streaming_commit.py -q
#   timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q   (loads CUDA models)
# and prefer -k subsets over whole suites when iterating. Never run the daemon foreground.

# COMMIT MUST RUN INSIDE daemon._on_final_lock: daemon.cancel() takes _lock then the stream
# lock; a commit rewinding keystrokes must never interleave with cancel's compensation rewind.
# (S1 documented the lock ordering: stream lock never takes the daemon _lock back.)

# The latency log line and record_final(cleaned) must fire on the streaming path too — the
# drain logic keys off _final_pending/_utterance_finalized being set BEFORE typing work.

# press_backspace(0) must remain a no-op (backend contract); commit with empty tail must not
# emit a backspace event (RecordingBackend records only n>0 — keep tests asserting that).

# No trailing space may EVER be typed via on_partial (S1 invariant); ONLY commit appends one,
# and only when cfg.output.append_space — and it is part of the committed text, so the next
# utterance's guard context ("committed + tail") is correctly spaced.

# Do not clear `frozen` in reset_boundary() (T6.S3 owns it); only reset_session() may.
```

## Implementation Blueprint

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EXTEND voice_typing/streaming.py — commit machinery
  - IMPLEMENT: StreamingOutput.commit(final_text) per "Commit semantics" above (prefix-extend
    delta, full-rewind retype, trailing space, checkpoint advance, frozen no-op path,
    fail-safe freeze on backend error, feedback mirror).
  - IMPLEMENT: StreamingOutput.reset_session() (clears committed/tail/suppressed/frozen);
    pure helper context_after_last_boundary(committed: str) -> str (text after the last of
    . ! ? — returns "" if the committed text contains no sentence terminator).
  - MODIFY: __init__ to accept append_space: bool = True (keyword, after `streaming`).
  - NAMING/PLACEMENT: same file, same style (docstring-heavy, section comments).

Task 2: ADD RecorderHost.set_prompt(text) in voice_typing/recorder_host.py
  - FOLLOW pattern: set_microphone (line ~252) — fire-and-forget cmd_q.put, never raises.
  - VERIFY: child cmd loop "prompt" branch (line ~702) no-ops when the executor degraded
    (executor is None) rather than raising in the child.

Task 3: WIRE daemon.py
  - MODIFY _on_partial (~1088): self._stream.on_partial(text) (keep latency.note_partial).
  - MODIFY on_final (~963): add the cfg.output.streaming branch per "Daemon wiring"; rejected
    final under streaming = freeze + boundary reset + bookkeeping, no typing.
  - MODIFY _arm/_disarm: call self._stream.reset_session() (defensive getattr, matching the
    existing seam style).
  - ADD _refresh_context_prompt(): context_after_last_boundary(self._stream.committed) →
    host.set_prompt(...) via defensive getattr.

Task 4: CREATE tests/test_streaming_commit.py
  - REUSE doubles from tests/test_streaming_core.py (RecordingBackend/FakeFeedback/FakeClock).
  - CASES: extend-commit types delta+space only; differing commit rewinds exact len(tail) and
    retypes final+space; commit not rate-limited (two commits back-to-back both rewind);
    checkpoint advance (next partial diffs vs empty tail; casing guard sees new committed);
    append_space=False types no space; frozen commit touches no backend, absorbs tail;
    backend failure inside commit → frozen, no exception escapes; reset_session clears
    everything incl. frozen; context_after_last_boundary slicing cases (no terminator → "",
    terminator mid-text, terminator at very end).
  - NAMING: test_commit_<scenario>.

Task 5: EXTEND tests/test_daemon.py — two-mode on_final tests (stub host, no CUDA)
  - CASES: streaming=True → commit path used, backend.type_text never called directly by the
    daemon for the payload; streaming=False → byte-identical Rev 1 behavior (backend receives
    cleaned+space, StreamingOutput makes zero backend calls); rejected final under streaming
    freezes tail; _on_partial routes through the engine in both modes (feedback still updated);
    _refresh_context_prompt reached after commit (fake host records set_prompt calls).

Task 6: FULL VALIDATION (see Validation Loop) + fix fallout in existing suites.
```

### Implementation Patterns & Key Details

```python
# Commit core (illustrative — follow S1's guarded-call style):
def commit(self, final_text: str) -> None:
    with self._lock:
        if not self._streaming:
            return  # daemon never calls this in Rev 1 mode, but stay safe
        text = " ".join(final_text.split())
        if self._frozen:
            # stranded/frozen tail stays on screen; absorb WITHOUT keystrokes (PRD rule 4)
            self._committed = " ".join(p for p in (self._committed, self._tail) if p)
            self._tail = ""
            self._suppressed = False
            self._feedback.update_partial(self._committed)
            return
        if self._tail and text.startswith(self._tail):
            delta = text[len(self._tail):]
            guarded = textproc.apply_streaming_guards(self._guard_context_delta(), delta) if delta else ""
            if guarded and not self._safe_type(guarded):
                return  # frozen by fail-safe; tail frozen on screen (PRD rule 4)
        else:  # revise or fresh
            guarded = textproc.apply_streaming_guards(self._committed, text)
            if not self._safe_backspace(len(self._tail)):
                return
            if guarded and not self._safe_type(guarded):
                return
        space = " " if self._append_space else ""
        if space and not self._safe_type(space):
            return
        self._committed = " ".join(p for p in (self._committed, text) if p) + space
        self._tail = ""
        self._suppressed = False
        self._feedback.update_partial(self._committed)

# Daemon on_final branch (after clean() + flag bookkeeping, inside _on_final_lock):
if self._cfg.output.streaming:
    try:
        self._stream.commit(cleaned)
    except Exception:
        logger.exception("streaming commit failed for %r", cleaned)
    t_typed = time.monotonic()
    self._feedback.record_final(cleaned)
    self._latency.finalize_utterance(...)  # + the existing structured INFO line
    self._refresh_context_prompt()
else:
    ...existing Rev 1 body verbatim...
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m ruff check voice_typing/streaming.py voice_typing/daemon.py voice_typing/recorder_host.py tests/test_streaming_commit.py --fix
.venv/bin/python -m ruff format voice_typing/ tests/test_streaming_commit.py
# Expected: clean (repo uses ruff; run on the touched files only)
```

### Level 2: Unit Tests

```bash
timeout 120 .venv/bin/python -m pytest tests/test_streaming_commit.py tests/test_streaming_core.py -q
# Heavy suites (CUDA model loads) — targeted subsets, per AGENTS.md:
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k "final or partial or stream"
timeout 300 .venv/bin/python -m pytest tests/test_typing_backends.py tests/test_textproc.py -q
# Expected: all pass; bash-tool timeout set above each inner timeout.
```

### Level 3: Live wiring smoke (daemon already runs under systemd — talk to it, never foreground)

```bash
timeout 15 .venv/bin/voicectl status                      # daemon alive?
# Toggle streaming in config.toml, restart unit, arm, speak one sentence, then:
journalctl --user -u voice-typing -n 50 --no-pager | grep -E "event=final|commit|frozen"
timeout 30 .venv/bin/voicectl stop
# Expected: structured latency line per utterance in BOTH modes; no tracebacks.
```

## Final Validation Checklist

- [ ] `tests/test_streaming_commit.py` + `tests/test_streaming_core.py` green.
- [ ] `test_daemon.py` targeted subset green; both output modes exercised.
- [ ] Commit: prefix-extend = delta+space only; revise = exact-len rewind + retype; no rate
      limit on commits; rejected final freezes tail; frozen commit = zero backend calls.
- [ ] Rollback hatch: `output.streaming=false` → daemon path unchanged, zero engine keystrokes.
- [ ] `_refresh_context_prompt` fires post-commit via the new `host.set_prompt` seam (defensive).
- [ ] Latency INFO line + `record_final` still emitted on the streaming path; drain flags set.
- [ ] ruff clean on touched files; nothing typed while disarmed (listening gate untouched).

## Anti-Patterns to Avoid

- ❌ Don't route the Rev 1 (streaming=false) final through StreamingOutput — the hatch must be
  provably keystroke-identical to today.
- ❌ Don't call `commit()` outside `_on_final_lock`, and don't take the daemon `_lock` from
  inside the engine (S1's documented ordering — violation = deadlock with cancel()).
- ❌ Don't rate-limit commit rewinds (limiter is for wobbly partials only).
- ❌ Don't let any exception escape `commit()`/`on_final` — reader thread must survive.
- ❌ Don't clear `frozen` in `reset_boundary()`; only `reset_session()` may (T6.S3 boundary).
- ❌ Don't run pytest/voicectl without inner `timeout` (AGENTS.md — wedged sockets hang sessions).
