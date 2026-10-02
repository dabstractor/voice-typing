# PRP — P1.M2.T6.S3: Freeze rules — stranded tail, user typing, utterance boundary

## Goal

**Feature Goal**: Complete the freeze lifecycle of the streaming output engine (PRD §4.2quater rules 4 & 5) so that typed text is NEVER auto-deleted when revision becomes unsafe, and the engine resumes cleanly at the next utterance boundary. Three freeze triggers, two freeze classes:

1. **Stranded tail** (PRD rule 4): when no commit can ever land — drain-watchdog abort (`_drain_timeout`) or recorder-host child death (`_handle_dead_host`) — the on-screen tail FREEZES exactly as last shown. Never rewound, never deleted; only an explicit cancel (T7.S1, landed) deletes.
2. **User-typing protection** (PRD rule 5): any NON-Backspace user keypress observed while a tail is pending → immediately freeze the tail and stop revising that utterance entirely (no further typing until the next utterance boundary). "Never type over the user's cursor."
3. **Utterance boundary lifecycle**: a per-utterance freeze (user-typing class) is LIFTED at the next utterance boundary; a session-class freeze (backend failure, stranded tail) is only lifted by `reset_session()` (fresh arm), which already exists.

**Deliverable**: (a) a freeze-class mechanism in `voice_typing/streaming.py` (freeze reasons → per-utterance vs per-session), with `reset_boundary()` lifting only per-utterance freezes; (b) a daemon seam `note_user_keypress()` in `daemon.py` callable by the future evdev listener (T7.S2 — NOT built here) plus wiring of the stranded-tail freezes into `_drain_timeout`/`_handle_dead_host`; (c) `tests/test_streaming_freeze.py` unit tests (pure, no mic, no CUDA).

**Success Definition**: All three freeze triggers behave per PRD rules 4/5; existing suites (`test_streaming_core.py`, `test_streaming_commit.py`, `test_daemon.py`, `test_textproc.py`, etc.) still pass; T8 asserts f/g (P1.M3.T8.S2) become implementable against this substrate.

## Why

The streaming engine (S1/S2) types live partials and revises in place. Revision correctness assumes "the cursor sits at the end of our typed text and the user has typed nothing since our last keystroke" (PRD §8 risk row). This subtask closes the remaining holes in that assumption: if the commit can never arrive (child death, drain timeout) or the user grabs the cursor (any keypress), continued revision would corrupt text or type over the user. S1 deliberately left `frozen` lifecycle "T6.S3's concern" — `reset_boundary()` currently does NOT clear `frozen`, and no freeze trigger beyond backend failure / rejected-final exists.

## What

### Engine (`streaming.py`) — freeze classes

- `freeze(reason)` gains a class concept. Introduce an internal freeze reason enum/tag or two booleans, e.g. per-utterance freeze vs session freeze. Suggested API (keep the existing public name working — it is load-bearing, see callers below):
  - `freeze(reason, session: bool = False)` — default stays per-utterance? **NO** — decide deliberately: existing callers are (1) `_safe_type`/`_safe_backspace` backend failure (SESSION class — on-screen state unknown, must not resume this session), (2) daemon rejected-final freeze (`daemon.py:994`, PER-UTTERANCE — the next utterance must stream normally), (3) new stranded-tail freezes (SESSION class). Recommended: `freeze(reason, *, session: bool)` explicit at every call site; backend-failure paths pass `session=True`, rejected-final passes `session=False` (or nothing, default False).
  - `reset_boundary()` lifts ONLY per-utterance freezes (`if self._frozen and not self._frozen_session: self._frozen = False`). Session freezes persist until `reset_session()` (already clears frozen — keep).
  - `note_user_keypress()` on the ENGINE: if streaming armed and a tail is pending and not already frozen → `freeze("user keypress", session=False)` (per-utterance: next utterance resumes). If no tail pending → no-op (plain user editing). Idempotent.
  - Frozen semantics in `on_partial`/`commit` are UNCHANGED (mirror-only; commit absorbs the tail into `committed` without keystrokes). Verify the frozen-absorb path in `commit()` (already in S2) still behaves with both classes — it must: a frozen stranded tail whose commit somehow DOES arrive late (race: final fired before the watchdog) should still absorb, not rewind. This is correct per PRD ("freezes as committed").

### Daemon (`daemon.py`) — wiring

- **User keypress seam**: add `note_user_keypress()` on `VoiceTypingDaemon` — defensive `getattr` style matching `_pending_tail_len`/`_reset_stream_after_cancel` (see daemon.py ~1170–1200): if `self._listening.is_set()`, call `self._stream.note_user_keypress()`. MUST be safe to call from an arbitrary thread (the future evdev listener, T7.S2) — the engine's internal lock already serializes. Also log one INFO per freeze (the engine's `freeze()` already logs WARNING — fine).
  - T7.S2 will call this seam; do NOT add any evdev code, device enumeration, or the Backspace special-case here (Backspace-cancel is T7.S1, landed; the listener distinguishes Backspace vs other keys in T7.S2).
- **Stranded tail — drain timeout**: in `_drain_timeout` (Timer thread, daemon.py ~1605): after/before `self._safe_abort()`, if `self._cfg.output.streaming` and a tail is pending, call `self._stream.freeze("drain timeout: stranded tail", session=True)`. Rationale: the abort kills the in-flight final; the typed tail can never be committed — freeze it as screen truth. Guard with the existing defensive `getattr` style. Note: `_complete_drain` → `_disarm` → `reset_session` follows shortly, so the session-class freeze mainly closes the race window between abort and disarm (a late partial/final from the dying utterance must not type or rewind) and documents intent.
- **Stranded tail — child death**: in the run-loop liveness branch (`if self._host is not None and not self._host.is_alive:`, daemon.py ~840) and/or `_handle_dead_host` (~883): if streaming and tail pending → `freeze("recorder-host child died: stranded tail", session=True)` BEFORE `_handle_dead_host()` mutates state. The tail stays on screen (reset_session at next arm does NOT rewind — confirm: `reset_session` only clears engine strings, never sends backspaces — TRUE, verified in streaming.py).
- **Utterance boundary normalization**: `on_final`'s streaming path should call `self._stream.reset_boundary()` on BOTH branches (rejected-final already does at daemon.py:995; add it after the successful `commit()` path too, next to `_refresh_context_prompt()` at ~1049). `commit()` already clears tail/suppression internally, so this is behavior-neutral for the healthy path but makes `reset_boundary` the single, always-hit boundary event that lifts per-utterance freezes (user-typing freeze is lifted exactly once per utterance, at its commit).
  - GOTCHA: a user-keypress-frozen utterance whose final arrives → `commit()` takes the frozen-absorb branch (tail absorbed into committed, no keystrokes) → then `reset_boundary()` lifts the freeze → next utterance streams. That is the desired sequence; do not reorder.

### Config

No new config keys. `output.streaming` remains the master switch; freeze wiring is gated on it only where typing could occur (the engine itself already no-ops when `streaming=False`, so unconditional calls are also safe — prefer defensive `getattr` + engine-internal gating for unit-test friendliness).

### Success Criteria

- [ ] `freeze(reason, session=False)` lifts at the next `reset_boundary()`; `session=True` persists through `reset_boundary()` and clears only at `reset_session()`.
- [ ] Backend-failure freezes (`_safe_type`/`_safe_backspace`) are session-class.
- [ ] `note_user_keypress()` freezes ONLY when a tail is pending; no-op otherwise; idempotent; safe cross-thread.
- [ ] Drain-timeout and child-death paths freeze the tail session-class, never rewind, never type again this session.
- [ ] A frozen (user-keypress) utterance's late commit absorbs without keystrokes; the freeze lifts at the boundary; the next utterance types normally.
- [ ] All existing tests pass unchanged (except deliberate call-site updates to `freeze(...)`).

## All Needed Context

### Context Completeness Check

The implementing agent needs: streaming.py in full (it is the file being extended — 400 lines, read it all), daemon.py's streaming/drain/child-death seams (exact line pointers below), the existing test patterns for the engine, and the PRD rules verbatim. All pointers given below. No external libraries needed — pure stdlib change.

### Documentation & References

```yaml
- file: voice_typing/streaming.py
  why: THE file to modify. StreamingOutput engine landed by S1/S2. Read fully before editing.
  pattern: lock discipline (self._lock guards all state; backend calls while holding it);
    fail-safe _safe_type/_safe_backspace (they already set frozen — retag session=True);
    docstring comment "frozen: NOT auto-cleared by reset_boundary() — T6.S3 owns the freeze
    lifecycle" — UPDATE this comment to describe the class mechanism you add.
  gotcha: commit()'s frozen-absorb branch must keep working for BOTH freeze classes (a stranded
    tail whose final races in late should absorb, not rewind). reset_session() is the ONLY method
    that may clear a session freeze. Do NOT make reset_boundary clear suppression semantics —
    it already lifts _suppressed; keep that.

- file: voice_typing/daemon.py
  why: wiring of freeze triggers + the user-keypress seam.
  sections:
    - ~1170-1198: _pending_tail_len / _reset_stream_after_cancel — COPY this defensive-getattr
      seam style for note_user_keypress().
    - ~1605 _drain_timeout: add session-class freeze before/after _safe_abort(), gated on
      pending tail + cfg.output.streaming.
    - ~840 run-loop liveness branch + ~883 _handle_dead_host: freeze before handling death.
    - ~975-1060 on_final streaming paths: rejected-final freeze at :994 (retag to explicit
      session=False) and add reset_boundary() after the successful commit (~line 1049, next to
      the _refresh_context_prompt call).
    - ~1062-1100 _arm/_disarm reset_session calls — unchanged, just verify.
  gotcha: _drain_timeout runs on a Timer thread; _handle_dead_host is called from the run loop
    under no lock in the liveness branch — the engine's own lock is the serializer, so ordering
    vs a concurrent partial is fine (worst case the freeze lands after one extra partial, which
    the frozen-mirror path handles). NEVER take daemon self._lock inside these additions while
    the engine lock is held in a path that also takes the engine lock from a daemon-_lock holder
    (cancel() does daemon _lock → engine lock; so do NOT call engine methods while holding the
    daemon _lock in new code if the engine might call back — it never does; still, prefer calling
    the engine OUTSIDE self._lock like _complete_drain does with the timer cancel).

- file: tests/test_streaming_core.py
  why: THE test pattern for the engine — fake backend recording type_text/press_backspace,
    fake feedback capturing update_partial, injectable clock.
  pattern: construct StreamingOutput(RecordingBackend(), FakeFeedback(), True); drive
    on_partial/commit; assert exact keystroke sequences. Reuse the same doubles in
    test_streaming_freeze.py (import or copy).
  gotcha: rate-limit tests use a fake clock starting at 0.0 — the _last_full_rewind=None
    sentinel exists because of that; don't "simplify" it.

- file: tests/test_streaming_commit.py
  why: commit-path test pattern incl. the frozen-absorb branch — extend thinking from these.

- file: tests/test_daemon.py
  why: daemon unit-test pattern (fake host, fake stream injected). Any daemon-side freeze wiring
    that is unit-testable goes here; heavy paths (drain timeout, child death) may need only
    targeted tests with fake timers/hosts — follow the existing fakes.

- file: PRD.md §4.2quater rules 4 & 5, and §8 risk rows ("Streaming revision corrupts text...")
  why: verbatim requirements. Rule 4: stranded tail freezes as committed, never auto-deleted.
    Rule 5: any non-Backspace keypress freezes the tail and stops revising that utterance
    entirely — "suppress further partial typing until the next utterance boundary".
  critical: PRD says suppression is "until the next utterance boundary" — hence per-utterance
    class for user-typing; stranded/backend-failure have no such clause — session class.
```

### Current Codebase tree (relevant excerpt)

```
voice_typing/
├── streaming.py        # StreamingOutput — MODIFY (freeze classes, note_user_keypress)
├── daemon.py           # VoiceTypingDaemon — MODIFY (seam + 3 wiring points + boundary call)
└── ...
tests/
├── test_streaming_core.py    # pattern source
├── test_streaming_commit.py  # pattern source
└── test_streaming_freeze.py  # CREATE
```

### Desired Codebase tree with responsibility of file

```
voice_typing/streaming.py   # + freeze classes (session vs per-utterance), engine-side
                            #   note_user_keypress(); reset_boundary lifts per-utterance only
voice_typing/daemon.py      # + daemon.note_user_keypress() seam (T7.S2 consumer);
                            # + freeze wiring in _drain_timeout & child-death path;
                            # + reset_boundary() after successful commit; retag rejected-final freeze
tests/test_streaming_freeze.py  # NEW: all freeze lifecycle unit tests
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: streaming.py is PURE STDLIB by design (imports cleanly on CPU-only test hosts) —
#   do not import daemon/torch/realtimestt there.
# CRITICAL: lock ordering — daemon cancel() takes daemon._lock THEN engine lock. New daemon-side
#   freeze calls must NOT hold daemon._lock while calling into the engine if any engine path can
#   take daemon locks (none do today) — call engine outside daemon._lock, mirroring _complete_drain.
# CRITICAL: reset_session() is called on BOTH _arm and _disarm (daemon.py ~1065, ~1099) — a
#   session-class freeze therefore never survives across a disarm/arm; the stranded tail simply
#   stays typed on screen with NO keystrokes sent at disarm. That is the PRD behavior ("stays on
#   screen exactly as last shown") — do NOT add rewind-on-disarm.
# AGENTS.md: this repo HANGS on untimed commands. Every daemon/voicectl/pytest invocation in the
#   validation loop MUST be double-wrapped: inner `timeout 600`, outer bash-tool timeout above it.
# test_daemon.py / test_recorder_host.py / test_feed_audio.py load real CUDA models (minutes) —
#   prefer -k filters and the streaming unit tests while iterating.
# python3/pip are aliased in the interactive shell — always use /home/dustin/.local/bin/uv or
#   .venv/bin/python explicitly.
```

## Implementation Blueprint

### Data models / structure

No new dataclasses. Internal engine state addition (sketch):

```python
class StreamingOutput:
    # state additions under self._lock:
    #   self._frozen: bool              (exists)
    #   self._frozen_session: bool      (NEW — True when the freeze must survive reset_boundary)
    # freeze(reason, *, session: bool = False)
    # reset_boundary(): lift freeze iff frozen and not frozen_session
    # reset_session(): unchanged (clears both — already clears _frozen; also clear _frozen_session)
    # note_user_keypress(): if streaming and tail and not frozen -> freeze("user keypress")
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/streaming.py — freeze classes
  - IMPLEMENT: _frozen_session flag; freeze(reason, *, session=False); reset_boundary lifts
    per-utterance freezes only; reset_session clears both; _safe_type/_safe_backspace pass
    session=True; add note_user_keypress() (engine-side, idempotent, no-op when no tail).
  - UPDATE: the class docstring "frozen:" entry + the module docstring FAILURE POLICY note
    ("T6.S3 formalizes freeze triggers" → describe the landed mechanism).
  - NAMING: keep freeze()/reset_boundary()/reset_session()/pending_tail_len() names —
    daemon callers and tests reference them (LOAD-BEARING).
  - GOTCHA: on_partial's frozen branch mirrors the typed tail — unchanged. commit()'s
    frozen-absorb branch — unchanged (works for both classes).

Task 2: MODIFY voice_typing/daemon.py — wiring
  - ADD: note_user_keypress() method, defensive-getattr seam style (see _pending_tail_len),
    gated on self._listening.is_set(); docstring notes T7.S2's evdev listener as the caller.
  - MODIFY: _drain_timeout — before _safe_abort(), freeze session-class if streaming and
    pending_tail_len() > 0 (defensive getattr on the freeze call too).
  - MODIFY: run-loop child-death branch — freeze session-class before _handle_dead_host().
  - MODIFY: on_final — retag rejected-final freeze to explicit session=False; add
    self._stream.reset_boundary() after the successful commit path (next to the
    _refresh_context_prompt call).
  - PRESERVE: all existing behavior when cfg.output.streaming is False (engine is a
    pass-through; the new calls are either engine-internal no-ops or harmless).

Task 3: CREATE tests/test_streaming_freeze.py
  - IMPLEMENT: unit tests using the RecordingBackend/FakeFeedback doubles pattern from
    test_streaming_core.py. Cover at minimum:
      1. freeze(session=False) lifted by reset_boundary(); freeze(session=True) survives it,
         cleared by reset_session().
      2. Backend-failure freeze is session-class (fake backend raising in type_text → frozen;
         reset_boundary does not lift).
      3. note_user_keypress: freezes when tail pending (subsequent on_partial mirrors only, no
         keystrokes); no-op with empty tail (later partials still type); idempotent; frozen
         utterance's commit absorbs without keystrokes and lifts at the boundary; the NEXT
         utterance types normally after reset_boundary.
      4. Stranded-tail semantics: freeze(session=True) with pending tail → commit() absorbs
         (race case) OR no further keystrokes ever (late partials mirror-only).
  - NAMING: test_{method}_{scenario} functions; NO pytest markers beyond existing conventions.
  - Also: a daemon-level test in tests/test_daemon.py (follow its fake-host/fake-stream pattern)
    for note_user_keypress() gating on _listening, IF the existing fakes make it cheap; skip if
    they require a real host — the engine tests carry the coverage.

Task 4: RUN validation loop (below); fix until green.
```

### Implementation Patterns & Key Details

```python
# Engine freeze with class (streaming.py) — sketch of the seam, follow existing lock discipline:
def freeze(self, reason: str = "", *, session: bool = False) -> None:
    with self._lock:
        if self._frozen:
            return  # first freeze wins; class cannot be "upgraded" (safe: session freeze is
                    # strictly stronger, and a per-utterance freeze arriving after a session
                    # freeze must NOT weaken it — so also: if frozen and session and not
                    # frozen_session: promote to session)
        ...

def note_user_keypress(self) -> None:
    """PRD §4.2quater rule 5 — never type over the user's cursor."""
    with self._lock:
        if not self._streaming or self._frozen or not self._tail:
            return
        self._frozen = True; self._frozen_session = False
    logger.warning("streaming frozen: user keypress while tail pending")

# Daemon seam (daemon.py) — copy the _pending_tail_len style:
def note_user_keypress(self) -> None:
    """P1.M2.T6.S3 / PRD §4.2quater rule 5. Called by the evdev listener (P1.M2.T7.S2)."""
    if not self._listening.is_set():
        return
    stream = getattr(self, "_stream", None)
    notifier = getattr(stream, "note_user_keypress", None)
    if callable(notifier):
        notifier()
```

Promotion rule: if already frozen per-utterance and a `session=True` freeze arrives, promote. The reverse never demotes.

### Integration Points

```yaml
DAEMON (no config/schema changes):
  - note_user_keypress() seam: consumed by T7.S2 evdev listener (future).
  - reset_boundary() after successful commit: consumed implicitly by the freeze lifecycle;
    T8.S2 asserts (f) key-freeze and (g) stranded tail against this substrate.
TESTS:
  - tests/test_streaming_freeze.py: new file; pure stdlib, fast (<2 s).
NO changes to: config.py, config.toml, ctl.py, recorder_host.py, typing_backends.py, textproc.py.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m ruff check voice_typing/streaming.py voice_typing/daemon.py --fix   # if ruff configured; else skip
.venv/bin/python -c "import voice_typing.streaming, voice_typing.daemon"   # import-clean, no side effects
```

### Level 2: Unit Tests (the primary gate)

```bash
# New freeze tests + both streaming suites (fast, pure):
timeout 120 .venv/bin/python -m pytest tests/test_streaming_freeze.py tests/test_streaming_core.py tests/test_streaming_commit.py -v

# Textproc + typing backends (adjacent, fast):
timeout 120 .venv/bin/python -m pytest tests/test_textproc.py tests/test_typing_backends.py -q

# Daemon unit tests (fake host; heavier — run once at the end, NOT per iteration):
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q
# (bash-tool timeout: set ABOVE the inner timeout, e.g. 700+ — AGENTS.md Rule 1, two layers.)
```

Expected: all pass. If test_daemon.py has failures related only to freeze call-site changes, fix the call sites (explicit `session=` args), not the tests' intent.

### Level 3: Manual smoke (optional, only if a daemon is already running under systemd)

```bash
timeout 15 .venv/bin/voicectl status   # daemon healthy check; NEVER un-timed (AGENTS.md)
# Do NOT spawn a foreground daemon for this task — unit tests are the gate (AGENTS.md Rule 2).
```

### Level 4: NOT applicable (no E2E for this subtask — T8.S2 is the E2E owner)

## Final Validation Checklist

- [ ] Level 2 gates green (streaming triple + textproc + backends + test_daemon.py)
- [ ] Freeze classes: per-utterance lifted by `reset_boundary()`; session survives it, cleared by `reset_session()`
- [ ] Backend-failure freezes are session-class; promotion-only (session never demoted)
- [ ] `note_user_keypress()` daemon seam exists, gated on `_listening`, callable cross-thread, unused-by-design until T7.S2
- [ ] `_drain_timeout` and child-death paths freeze stranded tails session-class; zero keystrokes sent on disarm (no rewind-on-disarm)
- [ ] `reset_boundary()` is called after BOTH final paths in `on_final`
- [ ] `output.streaming=false` (Rev 1 rollback hatch) behavior is keystroke-identical to before this change
- [ ] No new config keys; no new dependencies; streaming.py stays pure stdlib
- [ ] Docstrings in streaming.py updated (the "T6.S3 owns the freeze lifecycle" TODOs resolved)

## Anti-Patterns to Avoid

- ❌ Don't rewind on disarm/session-end — the stranded tail STAYS on screen (PRD rule 4, user decision).
- ❌ Don't clear a session-class freeze in `reset_boundary()` — only `reset_session()`.
- ❌ Don't let a per-utterance freeze arriving later weaken an existing session freeze (promote-only).
- ❌ Don't add evdev/keyboards to this task — that is T7.S2; only the seam lands here.
- ❌ Don't hold daemon `_lock` across new engine calls where a cancel-path ordering could invert (engine lock is innermost — keep it).
- ❌ Don't run any command untimed (AGENTS.md); don't run the daemon in the foreground.
