# PRP — P1.M1.T1.S1: Engine — utterance-scoped rejected-final freeze + explicit `resume()` API

## Goal

**Feature Goal**: Fix BUG-001 at the ENGINE level: a single blocklist/min_chars-rejected final currently freezes `StreamingOutput` with `session=True`, permanently silencing all typed output until re-arm. Add ONE explicit **`resume()`** API on `StreamingOutput` that clears `_suppressed` and lifts a rejected-final freeze — while backend-failure session freezes (raised internally by `_safe_type`/`__safe_backspace`) remain un-liftable — and make `reset_boundary()` **absorb** a frozen tail into `_committed` (same join discipline as `commit()`'s frozen path) so guards/context/mirror stay truthful. TDD: the failing test is written FIRST from the PRD h3.0 minimal repro.

**Deliverable**: Two files:
1. `voice_typing/streaming.py` — new `resume()` method; a backend-failure freeze-origin flag (so `resume()` can't lift those); `reset_boundary()` frozen-tail absorb; docstring updates (freeze/reset_boundary/resume) stating the new lift semantics.
2. `tests/test_streaming_freeze.py` — the pinned test extended to the NEW contract: frozen survives `reset_boundary()` AND stray late partials, lifts at `resume()`, and the next utterance's `on_partial`+`commit` produce real backend calls; plus backend-failure-survives-`resume()` and boundary-absorb cases.

**Success Definition**: (a) the new test is RED before the engine change (no `resume` → AttributeError) and GREEN after; (b) `resume()` on a rejected-final freeze → `frozen is False`, `_suppressed is False`, and the PRD repro sequence yields real `type_text`/`press_backspace` calls for the next utterance; (c) `resume()` after a backend-failure freeze → STILL frozen (fail-safe preserved); (d) `freeze()` promote-only semantics intact (all existing freeze tests unchanged-green); (e) `reset_boundary()` under freeze absorbs the tail into `committed`; (f) `daemon.py` NOT modified; (g) `tests/test_streaming_freeze.py` + `tests/test_streaming_core.py` green.

## User Persona

**Target User**: The dictating user who triggers the hallucination filter (a "thank you." on silence) — after this fix, the NEXT real utterance types normally instead of the session going permanently silent.

**Use Case**: Dictate → Whisper hallucinates a blocked final → keep dictating → words appear again (S2 wires `resume()` at the next speech event; S1 provides the engine capability).

**Pain Points Addressed**: BUG-001 (Critical): silent, unrecoverable-without-retoggle loss of the core feature triggered by an expected event class; plus the checkpoint-orphaning that makes guards/context/mirror lie after a rejected final.

## Why

- **BUG-001 is Critical and confirmed** (architecture/streaming_engine.md §25): `daemon.py:1154` calls `freeze("rejected final (blocklist/min_chars)", session=True)`; while frozen, `on_partial` (:318) is tail-mirror-only and `commit()`'s frozen-absorb path (:415-425) types nothing; only `reset_session()` (next arm) lifts. PRD §4.2quater rule 2 scopes the freeze to the *tail*, not the session.
- **Why an explicit `resume()` and not a retag**: the in-code comment at daemon.py:1150-1153 pins "frozen=True across this call — do not retag to per-utterance" (a per-utterance freeze would be lifted by the very next `reset_boundary()`, letting stray late partials of the REJECTED utterance revise a frozen screen tail). The architecture fix (§32) is "explicit unfreeze at the next utterance's first partial/speech" — an engine `resume()` the daemon (S2) will call from `_touch_speech()` at genuinely-new speech. Do NOT modify daemon.py in S1.
- **Why an origin flag**: the engine itself raises backend-failure freezes inside `_safe_type`/`_safe_backspace` (:472/:485) — so the engine can tag those internally WITHOUT any daemon change (the daemon's public `freeze(...)` call stays byte-identical). `resume()` must never lift a backend failure: the screen can't be trusted then, fail-safe is the point.
- **Why the boundary absorb**: `reset_boundary()` (:208-224) currently drops `_tail` WITHOUT absorbing it into `_committed` — after a rejected final the on-screen fragment is orphaned from the checkpoint, so the casing guard, the rolling context prompt, and the mirror all go stale. The frozen tail IS real typed text; the checkpoint must own it (same rstrip-join as `commit()`'s frozen path).

## What

Engine-only change (TDD): write the failing test from the PRD h3.0 repro sequence, then (1) add `resume()` — clears `_suppressed`, lifts the freeze iff it was NOT backend-failure-originated; (2) track the freeze origin internally (set only by `_safe_type`/`_safe_backspace`); (3) make `reset_boundary()` absorb a frozen tail into `_committed` before clearing it; (4) update the three docstrings. No daemon/config/socket changes.

### Success Criteria

- [ ] `StreamingOutput.resume()` exists with documented semantics (clears `_suppressed`; lifts non-backend-origin freezes; idempotent; under `self._lock`).
- [ ] Backend-failure freezes (fail_type/fail_backspace doubles) survive `resume()`.
- [ ] `freeze()` remains promote-only (session upgrade never demoted) — existing tests untouched-green.
- [ ] `reset_boundary()` under freeze: `_committed` gains the tail via commit()'s frozen-path join discipline; `_tail` cleared; without freeze, behavior unchanged (commit already absorbed).
- [ ] New test (RED→GREEN): PRD repro — partial, commit, boundary, partial, `freeze(session=True)`, boundary, stray partial (mirror-only), `resume()`, next `on_partial`+`commit` → real backend calls.
- [ ] `tests/test_streaming_freeze.py` + `tests/test_streaming_core.py` green under `timeout 600`.
- [ ] `daemon.py` unmodified.

## All Needed Context

### Context Completeness Check

_Pass._ Every method, line, state flag, locking idiom, test double, and the exact repro sequence is verified below. The one verbatim snippet the implementer must copy in-place (commit()'s frozen join) is pinned by file:line with instructions to read it first.

### Verified Current State (re-verified this session)

**`voice_typing/streaming.py` — `StreamingOutput` (class @100):**
- State under `self._lock`: `_committed`:152 (checkpoint), `_tail`:153, `_frozen`:154, `_frozen_session`:155, `_suppressed`:158, `_last_full_rewind` (300 ms full-rewind rate limit).
- Properties: `committed`:167, `tail`:172, `frozen`:177, `frozen_session`:182, `pending_tail_len`:192.
- `reset_after_cancel()`:197 — `_tail=""`, `_suppressed=True`.
- `reset_boundary()`:208 — `_tail=""`, `_suppressed=False`, lifts per-utterance freeze only (`if self._frozen and not self._frozen_session`). **Drops the tail WITHOUT absorbing** (the orphan bug).
- `reset_session()`:226 — clears everything incl. session freeze; sends NO keystrokes.
- `freeze(reason, *, session=False)`:248 — **PROMOTE-ONLY**: no-op while frozen except session upgrades per-utterance (:264-266); fresh freeze sets `_frozen=True; _frozen_session=bool(session)` (:271-272); logs WARNING.
- `note_user_keypress()`:279 — per-utterance freeze iff tail pending; cannot demote session.
- `on_partial(text)`:301 — order: streaming-off → raw mirror; `_suppressed` → raw mirror (:314); `_frozen` → tail mirror only (:318, `self._feedback.update_partial(self._tail)`); else EXTEND iff `self._tail and text.startswith(self._tail)` (:328, case-sensitive — BUG-008, NOT this task) else rate-limited REVISE.
- `commit()`:377 — frozen path (:415-425): absorbs `committed = join(committed.rstrip(), tail)` (READ the exact expression at :415-425 and copy it verbatim into reset_boundary), clears tail+suppressed, mirror, RETURN, **no keystrokes** (the missing space is BUG-003 — T3's task, do NOT fix here).
- `_safe_type`/`_safe_backspace`:472/:485 — backend exception → **SESSION freeze** + `return False` (fail-safe). These are the ONLY internal freeze origins.

**`voice_typing/daemon.py:1140-1160` (READ-ONLY — do not modify):** rejected-final branch: `if self._cfg.output.streaming:` → `self._stream.freeze("rejected final (blocklist/min_chars)", session=True)` → `self._stream.reset_boundary()`. The comment at :1150-1153 pins "The landed S2 test pins frozen=True across this call — do not retag to per-utterance." S2 (P1.M1.T1.S2) will add the `resume()` call at next speech + the user-visible cue.

**`tests/test_streaming_freeze.py`:** doubles — `RecordingBackend(TypingBackend)` (:29) with `fail_backspace`/`fail_type` ctor flags recording `type_text`/`press_backspace` calls (:40/:45); `FakeFeedback` (:53) recording `update_partial`; `_make_stream(...)` helper (:63). Existing tests (ALL must stay green, unmodified): `test_freeze_default_is_per_utterance_and_lifted_by_reset_boundary`:77, `test_freeze_session_survives_reset_boundary_until_reset_session`:85, `test_freeze_promotes_per_utterance_to_session`:95, `test_freeze_never_demotes_session_to_per_utterance`:106, plus note_user_keypress / backend-failure / late-partials / disarm-zero-keystrokes cases (file docstring :9-15).

**PRD h3.0 minimal repro (the RED test's spine):**
```
stream = StreamingOutput(fake_backend, fake_feedback, streaming=True [, append_space=True])
on_partial('Hello world'); commit('Hello world'); reset_boundary()
on_partial('Thank you'); freeze('rejected final (blocklist/min_chars)', session=True); reset_boundary()
# then: on_partial('The next real sentence'); commit('The next real sentence')
# TODAY: backend receives ZERO calls after the freeze. AFTER: with resume() inserted before
# the next utterance, both produce real calls.
```

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/streaming_engine.md
  why: The verified engine map (state :152-158, lifecycle :197-278, on_partial order :301-328, commit frozen
       path :415-425, _safe_* :472/:485) + §25 BUG-001 confirmation + §32 the prescribed fix (ONE resume API;
       do NOT retag; absorb at boundary). Follow it as the authority on line numbers.
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/system_context.md
  why: Round context + the S1/S2 split (S1 = engine + tests only; daemon wiring + cue = S2).
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: h2.1/h3.0 BUG-001 (the repro sequence) + h2.5 recommendation ("explicit unfreeze at the next
        utterance's first partial/speech" — exactly the resume() seam).
- file: voice_typing/streaming.py
  pattern: "All state mutations under `with self._lock:`; docstring-heavy methods; promote-only freeze.
            Copy commit()'s frozen-join expression verbatim (read :415-425 first)."
- file: tests/test_streaming_freeze.py
  pattern: "_make_stream(...) + RecordingBackend/FakeFeedback doubles; assert on .calls lists and the
            frozen/frozen_session properties. Extend, never weaken, the existing survive-assertions."
- file: tests/test_streaming_core.py
  why: The broader engine suite that must stay green; :292 manually calls reset_boundary() (the masking
        the PRD calls out — fine for unit scope, but the NEW test must follow the daemon's real order:
        freeze BEFORE reset_boundary, stragglers after).
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/streaming.py            # StreamingOutput @100; freeze :248; reset_boundary :208; commit :377; _safe_* :472/:485  ← EDIT
voice_typing/daemon.py               # :1154 freeze(session=True) call site  ← READ-ONLY (S2 owns)
tests/test_streaming_freeze.py       # pinned freeze-lifecycle tests + doubles  ← EDIT (extend + new tests)
tests/test_streaming_core.py         # broader engine suite  ← READ-ONLY gate
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/streaming.py            # MODIFY: +resume(), +backend-failure origin flag, reset_boundary absorb, docstrings
tests/test_streaming_freeze.py       # MODIFY: new RED→GREEN tests + boundary-absorb + backend-survives-resume cases
# NOTHING ELSE — daemon.py is S2's; commit()'s missing space is T3's; suppression-at-speech daemon test is T2.S2's.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT MODIFY daemon.py. The daemon's call `freeze("rejected final
# (blocklist/min_chars)", session=True)` stays byte-identical; the engine distinguishes origins
# INTERNALLY (the backend-failure flag is set only by _safe_type/_safe_backspace). S2 wires resume().

# CRITICAL #2 — ORIGIN-FLAG + PROMOTE-ONLY INTERPLAY. New freeze (was not frozen): clear the backend
# flag. Freeze arriving while ALREADY frozen: promote-only — do NOT clear an existing backend-failure
# flag (a rejected-final freeze on top of a backend failure must stay un-liftable). Only the internal
# _safe_* paths may SET the flag.

# CRITICAL #3 — resume() SEMANTICS. Under self._lock: (1) self._suppressed = False — ALWAYS (this is
# the T2.S1/BUG-002 reuse seam); (2) if self._frozen and not backend-failure-origin: _frozen=False,
# _frozen_session=False. If frozen WITH backend origin: leave frozen (log at INFO why it refused).
# Idempotent; no keystrokes; does NOT touch _committed/_tail/_last_full_rewind.

# CRITICAL #4 — THE PINNED SEQUENCE MUST KEEP frozen=True THROUGH THE BOUNDARY. The daemon order is
# freeze(..., session=True) THEN reset_boundary() THEN stray late partials — the new test must assert
# frozen stays True across ALL of that (that pin is what stops a per-utterance retag), and only
# resume() lifts. Do not weaken the existing survive tests; extend them.

# CRITICAL #5 — reset_boundary ABSORB ONLY UNDER FREEZE. If _frozen: _committed = <commit()'s frozen
# join over (_committed, _tail)> BEFORE clearing _tail. If not frozen: unchanged (commit() already
# absorbed). Post-cancel (_suppressed, _tail=="") is unaffected — nothing to absorb.

# CRITICAL #6 — DON'T FIX BUG-003 HERE. commit()'s frozen path lacking append_space is P1.M1.T3.S1.
# Don't add the space, don't add keystrokes to the boundary, don't touch the rate-limit comparison
# (BUG-008 = T8). One bug per subtask.

# GOTCHA #7 — TEST INVOCATION. Header of test_streaming_freeze.py says
# `timeout 120 .venv/bin/python -m pytest tests/test_streaming_freeze.py -q` — use that form (the
# contract's `uv run pytest` also works; .venv/bin/python is the repo's verified idiom). Set the
# bash-tool timeout ABOVE the inner timeout (AGENTS.md two-timeout rule).

# GOTCHA #8 — RED FIRST. The new test must FAIL before the engine edit (AttributeError: no 'resume').
# Run it once against unmodified streaming.py, confirm the failure mode, then implement.
```

## Implementation Blueprint

### Data models and structure

No schema/config change. New internal state (one bool, e.g. `self._frozen_backend_failure: bool = False` in `__init__` next to `_frozen_session`:155) + one public method. Public surface additions: `resume()` only.

### Implementation Tasks (ordered — TDD: RED first)

```yaml
Task 1: WRITE the failing tests in tests/test_streaming_freeze.py (place after the existing freeze-class tests).
  - Test A (the PRD h3.0 repro, NEW contract):
        def test_rejected_final_freeze_lives_until_resume_then_next_utterance_types():
            """BUG-001 engine contract: a rejected-final SESSION freeze survives the boundary AND
            stray late partials (pin: never retag to per-utterance), lifts ONLY at resume(), and the
            next utterance then streams for real (on_partial types a delta; commit corrects+joins)."""
            stream = _make_stream()                      # streaming=True per the helper's default
            stream.on_partial("Hello world"); stream.commit("Hello world"); stream.reset_boundary()
            assert stream.calls == ...                   # baseline typing happened
            stream.on_partial("Thank you")
            stream.freeze("rejected final (blocklist/min_chars)", session=True)
            stream.reset_boundary()
            assert stream.frozen is True                 # survives the boundary (the pin)
            stream.on_partial("ank you.")                # stray late partial of the REJECTED utterance
            assert stream.frozen is True                 # still frozen; mirror-only (no new typing)
            stream.resume()
            assert stream.frozen is False and stream.frozen_session is False
            stream.on_partial("The next real sentence")  # NEW utterance: real typing resumes
            assert any("The next real sentence" in c for c in <backend type_text calls>)
            stream.commit("The next real sentence")
            assert <commit produced backend calls>       # e.g. a join/space type_text occurred
    (Adapt helper/double access to the file's actual style — see _make_stream :63 and how existing
     tests reach the backend's recorded calls.)
  - Test B (backend failure is NOT liftable):
        def test_resume_cannot_lift_backend_failure_freeze():
            stream = _make_stream(backend=RecordingBackend(fail_type=True))  # per the real ctor flags
            ... drive a partial so a type is attempted -> _safe_type freezes session-class ...
            stream.resume()
            assert stream.frozen is True                 # fail-safe survives
  - Test C (boundary absorb):
        def test_reset_boundary_under_freeze_absorbs_tail_into_committed():
            stream = _make_stream(); stream.on_partial("Hello world")
            stream.freeze("rejected final (blocklist/min_chars)", session=True)
            stream.reset_boundary()
            assert "Hello world" in stream.committed     # absorbed (commit()'s join discipline)
            assert stream.tail == ""
  - Test D (resume also clears post-cancel suppression — the T2.S1 seam):
        def test_resume_clears_suppressed(): stream.reset_after_cancel(); stream.resume();
            then on_partial types (not mirror-only).
  - RUN (expect RED — AttributeError: 'StreamingOutput' object has no attribute 'resume'):
        timeout 120 .venv/bin/python -m pytest tests/test_streaming_freeze.py -q
  - Existing tests must ALREADY pass before your engine edit (they do today) — re-run to confirm.

Task 2: EDIT voice_typing/streaming.py — origin flag.
  - __init__ (~:155, next to _frozen_session): self._frozen_backend_failure: bool = False
  - freeze() :248: on a FRESH freeze (the :271 branch) set self._frozen_backend_failure = False;
    in the already-frozen promote branch (:264-266) DO NOT touch the flag (Critical #2).
  - _safe_type (:472) and _safe_backspace (:485): where they freeze on exception, also set
    self._frozen_backend_failure = True (they freeze session-class already).

Task 3: EDIT voice_typing/streaming.py — resume().
  - Place after reset_session() (:226 block) / before freeze() (:248), matching file order:
        def resume(self) -> None:
            """Lift a rejected-final (non-backend) freeze + clear suppression — the next utterance
            streams for real (BUG-001 engine seam; called by the daemon at genuinely-new speech,
            P1.M1.T1.S2). Clears _suppressed ALWAYS (also the post-cancel seam, P1.M1.T2.S1). Lifts
            the freeze ONLY when it was NOT raised by a backend failure (_safe_type/_safe_backspace
            tag those internally): after a backend failure the on-screen state cannot be trusted, so
            only reset_session() (fresh arm) may recover — resume() logs and leaves it frozen.
            Idempotent; sends NO keystrokes; does not touch _committed/_tail."""
            with self._lock:
                self._suppressed = False
                if self._frozen:
                    if self._frozen_backend_failure:
                        logger.info("resume(): refusing to lift backend-failure freeze")
                    else:
                        self._frozen = False
                        self._frozen_session = False
  - Use the module's existing logger name/style (see freeze()'s WARNING for the idiom).

Task 4: EDIT voice_typing/streaming.py — reset_boundary() frozen absorb.
  - In reset_boundary() (:208), inside the lock, BEFORE `self._tail = ""`: if self._frozen, set
    self._committed = <the EXACT join expression commit()'s frozen path uses at :415-425 — read it
    and copy verbatim (architecture notes describe it as committed = join(committed.rstrip(), tail))>.
    Update the docstring: frozen boundaries ABSORB the tail into the checkpoint (guards/context/
    mirror truthfulness — BUG-001 companion fix); non-frozen boundaries are unchanged.

Task 5: UPDATE the docstrings (Mode A): freeze() (mention resume() as the lift path for
  non-backend session freezes), reset_boundary() (absorb), resume() (Task 3 text).

Task 6: VERIFY (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S1: engine resume() + frozen-boundary absorb (BUG-001 engine half)".
```

### Implementation Patterns & Key Details

```python
# Correctness rests on THREE invariants:
#  (1) Origin truth: ONLY _safe_type/_safe_backspace set _frozen_backend_failure; a fresh public
#      freeze() clears it; a promote-path freeze() never does. => resume() can distinguish.
#  (2) The pin: frozen survives freeze()->reset_boundary()->stray-partials; ONLY resume() (or
#      reset_session()) lifts a non-backend session freeze. A per-utterance retag stays forbidden.
#  (3) Absorb-if-frozen at the boundary uses commit()'s frozen join VERBATIM — one discipline.
# Locking: every mutation under self._lock (file-wide idiom). resume() takes no other locks.
# RED proof: Task 1 run before Tasks 2-4 must fail with AttributeError on 'resume' — that is the
# demonstration the test covers the missing capability (not a tautology).
```

### Integration Points

```yaml
DOWNSTREAM (NOT S1):
  - P1.M1.T1.S2: daemon calls stream.resume() from _touch_speech() at the next utterance's start +
    adds the user-visible rejected-final cue. S1 ships the capability; S2 consumes it.
  - P1.M1.T2.S1 (BUG-002): reuses resume()'s always-clear-_suppressed semantics (Test D pins it).
  - P1.M1.T3.S1 (BUG-003): commit() frozen-path append_space — explicitly NOT touched here.
NO PUBLIC-API CHANGE beyond the additive resume(); frozen/frozen_session semantics unchanged for
  every existing caller; daemon.py byte-identical.
```

## Validation Loop

> AGENTS.md two-timeout rule: inner `timeout N` + bash-tool timeout above it. Use `.venv/bin/python -m pytest` (the repo's verified idiom; the contract's `uv run pytest` is equivalent). No live daemon, no CUDA.

### Level 0: TDD RED (run BEFORE the engine edit)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_streaming_freeze.py -q 2>&1 | tail -5
# Expected: the NEW tests FAIL (AttributeError: ... 'resume') while ALL pre-existing tests pass.
# If an old test fails before any edit, STOP — the tree moved; re-verify anchors before proceeding.
```

### Level 1: The engine landed (static)

```bash
cd /home/dustin/projects/voice-typing
grep -n "def resume" voice_typing/streaming.py && echo ok1
grep -cn "_frozen_backend_failure" voice_typing/streaming.py   # expect >=4: init, freeze fresh, _safe_type, _safe_backspace (+resume read)
grep -n "_frozen_backend_failure = True" voice_typing/streaming.py | wc -l   # expect 2 (both _safe_* sites)
# Expected: ok1 + the flag wired at exactly the internal sites (never in the public freeze fresh-path setter = False there).
```

### Level 2: The owned suites are green

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_streaming_freeze.py tests/test_streaming_core.py -q 2>&1 | tail -5
# Expected: all passed (new + every pre-existing freeze/core test). Also recommended:
timeout 600 .venv/bin/python -m pytest tests/test_streaming_commit.py -q 2>&1 | tail -3
```

### Level 3: One-off repro of the PRD sequence (end-to-end engine proof)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing.streaming import StreamingOutput
class B:
    def __init__(self): self.calls=[]
    def type_text(self,t): self.calls.append(("t",t))
    def press_backspace(self,n): self.calls.append(("b",n))
class F:
    def update_partial(self,t): pass
b=B(); s=StreamingOutput(b,F(),streaming=True,append_space=True)
s.on_partial("Hello world"); s.commit("Hello world"); s.reset_boundary()
n0=len(b.calls)
s.on_partial("Thank you"); s.freeze("rejected final (blocklist/min_chars)", session=True); s.reset_boundary()
s.on_partial("ank you.")                       # stray late partial -> mirror only
assert len(b.calls)==n0 and s.frozen, "still frozen, no typing"
s.resume(); assert not s.frozen
s.on_partial("The next real sentence"); s.commit("The next real sentence")
assert len(b.calls)>n0, "next utterance typed for real"
assert "Hello world" in s.committed or s.committed  # boundary-absorb kept the checkpoint truthful
print("L3 PASS: BUG-001 engine sequence recovered via resume()")
PY
```

### Level 4: Scope

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/streaming\.py|tests/test_streaming_freeze\.py' | grep -E '\.py$|\.toml$|\.md$' && echo "L4 FAIL: out of scope" || echo "L4 PASS: only streaming.py + test_streaming_freeze.py"
git diff voice_typing/daemon.py | grep -q . && echo "L4 FAIL: daemon.py touched (S2 owns)" || echo "L4 PASS: daemon.py untouched"
```

## Final Validation Checklist

### Technical Validation
- [ ] L0: new tests RED pre-edit (AttributeError on resume); pre-existing tests green pre-edit.
- [ ] L1: `resume()` present; `_frozen_backend_failure` set ONLY at the two `_safe_*` sites; cleared on fresh public freezes.
- [ ] L2: `test_streaming_freeze.py` + `test_streaming_core.py` green under `timeout 600` (commit suite too).
- [ ] L3: the PRD repro recovers (frozen → strays mirror-only → resume → next utterance types; checkpoint truthful).
- [ ] L4: only `streaming.py` + `test_streaming_freeze.py` changed; `daemon.py` untouched.

### Feature Validation
- [ ] Rejected-final freeze survives boundary + strays, lifts at `resume()`; next utterance's partial+commit produce real backend calls.
- [ ] Backend-failure freeze survives `resume()` (fail-safe intact); promote-only freeze semantics intact.
- [ ] `reset_boundary()` under freeze absorbs the tail into `committed` (commit's join discipline).
- [ ] `resume()` docstring documents exact semantics; freeze/reset_boundary docstrings updated.

### Code Quality Validation
- [ ] All mutations under `self._lock`; no new locks; no keystrokes from resume()/boundary.
- [ ] Existing freeze tests unmodified and green (the pin extended, never weakened).
- [ ] One bug per subtask: no BUG-003 space fix, no BUG-008 case-normalization, no daemon wiring.

### Scope Boundary Validation
- [ ] `daemon.py`, config, socket, README untouched; S2/T2/T3/T8 own those.

---

## Anti-Patterns to Avoid

- ❌ Don't modify `daemon.py` — the freeze call site + `resume()` wiring + the user cue are P1.M1.T1.S2's.
- ❌ Don't retag the rejected-final freeze to `session=False` — the pinned comment and Test A exist precisely to prevent that (stray late partials would revise the frozen tail).
- ❌ Don't let `resume()` lift backend-failure freezes — set the origin flag only inside `_safe_type`/`_safe_backspace`, and never clear it on the promote path.
- ❌ Don't invent a new join expression for the boundary absorb — copy `commit()`'s frozen-path join verbatim (:415-425).
- ❌ Don't weaken/delete the existing survive-assertions in test_streaming_freeze.py — extend the contract, don't rewrite it.
- ❌ Don't fix BUG-003 (frozen-commit space) or BUG-008 (case-sensitive extend) here — T3/T8 own them.
- ❌ Don't write the implementation before confirming RED — run the new test against unmodified streaming.py first.
- ❌ Don't run unwrapped pytest or the live daemon — inner `timeout` + bash-tool timeout above it (AGENTS.md).

---

## Confidence Score

**9/10** for one-pass success. Every engine anchor (state flags, method lines, lock idiom, promote-only rules, the internal-only origin of backend freezes) is verified against the live file; the fix design follows the architecture doc's prescribed seam exactly and requires NO daemon change (the origin flag exploits the fact that backend failures freeze engine-internally); the RED→GREEN spine is the PRD's own repro. The −1 covers the two copy-in-place dependencies — commit()'s exact join expression (:415-425) and `_make_stream`'s real signature (:63) — which the implementer reads at edit time (both pinned by file:line), plus standard tree-drift risk on the cited line numbers.
