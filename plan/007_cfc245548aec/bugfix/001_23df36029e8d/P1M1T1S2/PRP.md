# PRP — P1.M1.T1.S2: Daemon — wire resume at next speech + user-visible rejected-final cue

## Goal

**Feature Goal**: Finish BUG-001 (Critical) at the daemon level. Consume S1's engine `StreamingOutput.resume()` API: (1) call it from `_touch_speech()` so the next utterance's genuinely-new speech lifts a rejected-final freeze and typed output resumes live; (2) add a WARNING log + a **user-visible cue through the existing `feedback.notify()` surface** in on_final's rejected-final branch (silent output death is the worst failure mode for a dictation tool — PRD h2.5). Add the daemon-level regression test that drives the real daemon flow (the PRD h3.0 repro): reject → frozen + cue → stray partial mirror-only → `_touch_speech()` → next partial **types**.

**Deliverable**: Two files: `voice_typing/daemon.py` (2 edit sites: the rejected-final branch + `_touch_speech()`) and `tests/test_daemon.py` (one additive `notify` recorder on `_DaemonFakeFeedback` + the new daemon-level recovery test). Nothing else — `streaming.py` is S1's, README/ACCEPTANCE are P1.M3.T9.

**Success Definition**: (a) the new daemon test is green: after a blocklisted final, `frozen is True`, the cue fired (`fb.toasts`), a stray late partial types nothing, `d._touch_speech()` unfreezes, and the next `_on_partial` + `on_final` produce real `be.typed` entries; (b) the WARNING is logged on streaming-mode rejection; (c) the daemon's `freeze(..., session=True)` call stays **byte-identical** (no retag — S1's pin); (d) all existing daemon tests stay green (esp. :4621 rejected-final freeze+bookkeeping, :4639 Rev1 plain early return, :1876 no-latency-line); (e) only `daemon.py` + `tests/test_daemon.py` change.

## User Persona

**Target User**: The dictating user who triggers the hallucination filter (a "thank you." on silence). After S1+S2: the next real utterance types normally, and a brief toast tells them a hallucination was filtered (not that the tool died).

**Use Case**: Dictate → Whisper hallucinates a blocked final → (toast: filtered) → keep dictating → words appear again. No retoggle needed.

**Pain Points Addressed**: BUG-001's silent, unrecoverable-without-retoggle loss of output; and the PRD h2.5 "log a user-visible warning when output freezes" recommendation.

## Why

- **BUG-001 daemon half.** S1 ships the engine capability (`resume()`); the PRD h2.5 recommendation names the exact seam: "clear … at the next utterance's first partial/speech". `_touch_speech` IS the daemon's speech hook (the child's ungated `('speech', {})` IPC event, recorder_host.py:447-448) — it fires exactly when genuinely new speech begins, so the freeze is lifted precisely when a new utterance starts, never before (stray late partials of the rejected utterance stay mirror-only).
- **The cue closes the "silent death" failure mode.** A rejected final currently produces zero user feedback. `feedback.notify()` (feedback.py:206) is the existing ad-hoc-toast surface (the 'Loading…' precedent at daemon.py:829), self-gated by `hypr_notify` — the one method that fits without inventing a surface.
- **No re-plumbing.** `resume()` is idempotent, lock-safe (engine lock only; on_final's ordering is `_on_final_lock` → engine lock — no cycle), sends no keystrokes, and no-ops when nothing is frozen/suppressed — so wiring it into `_touch_speech()` cannot perturb any existing `_touch_speech` behavior/test.
- **BUG-002 co-benefit (by design).** S1's `resume()` clears `_suppressed` ALWAYS, so this wiring also lifts post-cancel suppression at next speech — exactly what P1.M1.T2.S2 needs; T2.S2 reduces to its regression test (+ any residual wiring it finds). S2 adds no extra suppression-clearing.

## What

Two daemon edits + test additions. (1) In on_final's rejected-final streaming branch: add `logger.warning(...)` + `self._feedback.notify(<cue>)` after the bookkeeping (streaming-mode ONLY; the Rev 1 branch stays byte-for-byte per its pinned test). (2) In `_touch_speech()`: call `self._stream.resume()` at the top. (3) Extend `_DaemonFakeFeedback` with a `notify` recorder (additive — required, see Gotcha #3). (4) Add the daemon-level recovery test.

### Success Criteria

- [ ] `_touch_speech()` calls `self._stream.resume()` before the `_final_pending` flag logic (runs regardless of `_utterance_finalized`).
- [ ] The rejected-final streaming branch logs a WARNING and calls `self._feedback.notify(...)` (cue text mentions the filter/hallucination); `freeze(..., session=True)` + `reset_boundary()` + bookkeeping stay byte-identical.
- [ ] Rev 1 mode (streaming=False) rejected-final path unchanged (no log/cue/freeze there — :4639 pin).
- [ ] `_DaemonFakeFeedback` gains `toasts: list[str]` + `notify(msg)` (additive).
- [ ] New daemon test green (the PRD h3.0 repro at daemon level, incl. the cue assertion + a still-frozen stray-partial step).
- [ ] `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q` fully green.
- [ ] Only `voice_typing/daemon.py` + `tests/test_daemon.py` changed.

## All Needed Context

### Context Completeness Check

_Pass._ Both daemon edit sites are quoted with live line numbers and surrounding code; S1's `resume()` contract is pinned; the cue surface (`feedback.notify`) and its gating are verified; the test construction pattern (:676 `_make_daemon`), the fake inventory (incl. the notify gap), and every existing test that must stay green are identified with line numbers.

### Documentation & References

```yaml
# THE ENGINE CONTRACT (S1 — this task's INPUT)
- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T1S1/PRP.md
  why: Defines resume() exactly: clears _suppressed ALWAYS; lifts the freeze iff NOT
        backend-failure-origin; idempotent; no keystrokes; self._lock only. AND pins the invariant
        S2 must preserve: the daemon's freeze(..., session=True) call stays byte-identical (never retag).
  critical: "S2 CONSUMES resume(); it must NOT edit streaming.py. Verify S1 landed first:
        grep -n 'def resume' voice_typing/streaming.py (the new daemon test is RED-until-S1 otherwise)."

# THE BUG + THE PRESCRIBED SEAM
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: h2.1/h3.0 BUG-001 (the repro sequence) + h2.5 recommendations ("explicit unfreeze at the next
        utterance's first partial/speech"; "log a user-visible warning when output freezes").
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/daemon_flow.md
  why: §_touch_speech (daemon.py:1354) fed by the child's ungated ('speech', {}) IPC event
        (recorder_host.py:447-448) — fires exactly at genuinely-new speech; §the rejected-final
        branch (daemon.py:1137-1165) with the freeze at :1154.

# EDIT SITE A — the rejected-final branch
- file: voice_typing/daemon.py
  why: :1137-1165. Streaming path today: freeze(session=True) :1154 → reset_boundary() →
        _final_pending=False → _utterance_finalized=True → return. NO logger call, NO cue today
        (verified). The :1150-1153 comment pins "do not retag to per-utterance".
  pattern: "S2 inserts AFTER the bookkeeping, INSIDE `if self._cfg.output.streaming:`:
            logger.warning(...) + self._feedback.notify(...). Rev 1 branch untouched."
  gotcha: "logger is the module logger; match the file's style (see _refresh_context_prompt's
           logger.debug / logger.warning usage)."

# EDIT SITE B — _touch_speech()
- file: voice_typing/daemon.py
  why: :1354-1381. Body: _last_speech_monotonic = time.monotonic(); if not _utterance_finalized:
        _final_pending = True. Runs on the host reader thread; stores atomic; resume() takes only
        the engine lock (no deadlock with _on_final_lock → engine-lock ordering).
  pattern: "Add self._stream.resume() at the TOP (mirrors _on_partial's direct
            self._stream.on_partial(text) style — self._stream is ALWAYS a real StreamingOutput,
            constructed unconditionally at daemon.py:754, so no getattr seam)."
  gotcha: "BEFORE the _final_pending logic, not inside the `if not _utterance_finalized` guard —
           the resume must fire even when the previous on_final already finalized the utterance
           (that is exactly the rejected-final case)."

# THE CUE SURFACE (the existing method that fits)
- file: voice_typing/feedback.py
  why: notify(msg) :206 — ad-hoc hyprctl toast, gated by cfg.hypr_notify, no state change, no disk
        write. Precedent: daemon.py:829 self._feedback.notify(_COLD_LOAD_NOTIFY_LOADING).
  critical: "Do NOT invent a new feedback surface or touch state.json; notify() is the fit.
             Log-only would be acceptable, but notify() exists and matches the PRD recommendation."

# THE TEST FILE + FAKES
- file: tests/test_daemon.py
  why: _make_daemon :676 (the :684 construction pattern — default cfg has output.streaming=True);
        _DaemonFakeFeedback :470 (phases/partials/finals/listening_states — NO notify, the gap);
        _StubRecorder :489; _FakeBackend; _ok_probe; _FakeHost :556 (HAS consume_cancel_mark :625);
        _fake_host_factory :660. Existing tests to keep green: :4621 (rejected-final freeze pins),
        :4639 (Rev1 early return), :1876 (no latency line on rejection), :4581/:4593/:4605
        (streaming commit/revise/Rev1), :764-:947 (_touch_speech suite — resume no-ops for them).
  pattern: "Streaming tests: d.start(); d._on_partial(...); d.on_final(...); assert on be.typed /
            fb.partials / d._stream.frozen. Force rejections with cfg.filter.blocklist = [...]."
  gotcha: "ADD the notify recorder BEFORE adding the daemon call — otherwise :4621 AttributeErrors."

# THIS SUBTASK'S RESEARCH NOTE
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T1S2/research/daemon_resume_wiring_findings.md
  why: §1 S1 resume() semantics; §2 both edit sites live-quoted; §3 the notify surface + THE FAKE GAP;
       §4 test seams incl. every keep-green test; §5 the T2.S2 overlap note; §6 misc.
  section: "§2 (edit sites) and §3 (the fake gap) are load-bearing."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py            # rejected-final branch :1137-1165; _touch_speech :1354-1381  ← EDIT (2 sites)
tests/test_daemon.py              # _DaemonFakeFeedback :470; _make_daemon :676; rejected tests :4621/:4639  ← EDIT (fake + new test)
voice_typing/streaming.py         # S1's resume() (input contract)                             ← READ ONLY (verify it landed)
voice_typing/feedback.py          # notify :206 (the cue surface)                              ← READ ONLY
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py   # MODIFY: +resume() call in _touch_speech; +WARNING +feedback.notify in the rejected streaming branch
tests/test_daemon.py     # MODIFY: +notify/toasts recorder on _DaemonFakeFeedback; +test_rejected_final_recovers_at_next_speech_with_cue
# NOTHING ELSE. streaming.py (S1), feedback.py, config, socket, README untouched.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S2 DEPENDS ON S1. resume() must exist on StreamingOutput before the daemon call
# works. Precheck: grep -n "def resume" voice_typing/streaming.py. If absent, S1 is still in
# flight — STOP (the input contract is unmet) rather than shimming resume() into daemon.py.

# CRITICAL #2 — DO NOT RETAG THE FREEZE. The call freeze("rejected final (blocklist/min_chars)",
# session=True) stays byte-identical (S1's pin + the :1150-1153 comment): a per-utterance freeze
# would be lifted by the very next reset_boundary(), letting stray late partials revise the frozen
# screen tail. The lift is resume() at genuinely-new speech ONLY. Existing test :4621 pins
# frozen=True across the branch — it must stay green UNMODIFIED.

# CRITICAL #3 — THE FAKE GAP (order of operations). _DaemonFakeFeedback has NO notify method.
# Add the daemon's notify call BEFORE extending the fake and every rejected-branch test
# (:4621 etc.) AttributeErrors. EDIT THE FAKE FIRST (additive toasts recorder), then daemon.py.

# CRITICAL #4 — resume() PLACEMENT IN _touch_speech. TOP of the method, BEFORE the
# `if not self._utterance_finalized:` guard. After a rejected final, on_final set
# _utterance_finalized=True — a resume hidden inside the guard would never fire in exactly the
# case that needs it. (It also must not disturb the _final_pending/_utterance_finalized logic.)

# CRITICAL #5 — STREAMING-ONLY CUE/WARNING. The Rev 1 (streaming=False) rejected-final path is
# pinned byte-for-byte by :4639 ("plain early return"). Put logger.warning + feedback.notify
# INSIDE the `if self._cfg.output.streaming:` block only.

# CRITICAL #6 — THE LATENCY-LINE PIN. test_on_final_rejected_hallucination_emits_no_latency_line
# (:1876) asserts the rejected final emits NO latency log line. Your WARNING is a different
# message/level — fine — but do not touch the latency-logging path.

# GOTCHA #7 — NOTIFY IS SELF-GATED. feedback.notify() checks cfg.hypr_notify internally; do NOT
# add a second gate at the call site. Keep the cue message SHORT (toast): mention the filter and
# that dictation continues (e.g. "filtered hallucination — not typed; keep dictating").

# GOTCHA #8 — T2.S2 OVERLAP IS INTENTIONAL. resume() clearing _suppressed at next speech IS the
# BUG-002 daemon fix. Do NOT add any other suppression-clearing (no sentinel-branch edits, no
# _on_partial changes) — T2.S2's regression test will verify; duplication risks new races.

# GOTCHA #9 — AGENTS.md. Two timeouts (inner `timeout 600` for the suite, bash-tool timeout above
# it); `.venv/bin/python -m pytest`; NO live daemon, NO CUDA, NO foreground daemon. Fakes only
# (_StubRecorder/_FakeHost/_FakeBackend/_ok_probe via _make_daemon).

# GOTCHA #10 — THREAD CONTEXT. _touch_speech runs on the host reader thread. resume() is
# thread-safe (engine lock) and non-raising by contract; no try/except needed (matches the
# method's existing bare-store style).
```

## Implementation Blueprint

### Data models and structure

None. Pure wiring + tests; the state machine lives in S1's engine.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECK — S1 landed?
  - RUN: grep -n "def resume" voice_typing/streaming.py
  - EXPECT: a hit (S1's resume()). If none, STOP — the input contract is unmet.

Task 1: EDIT tests/test_daemon.py — extend _DaemonFakeFeedback (BEFORE the daemon edit; Critical #3).
  - In __init__ (after listening_states):  self.toasts: list[str] = []
  - New method (next to record_final):
        def notify(self, msg: str) -> None:
            self.toasts.append(msg)
  - ADDITIVE only; no existing assertion changes.

Task 2: EDIT voice_typing/daemon.py — the rejected-final branch cue + warning.
  - FIND (inside `if self._cfg.output.streaming:` at :1141, after the freeze + reset_boundary +
    _final_pending/_utterance_finalized bookkeeping, before `return`):
                self._stream.freeze(
                    "rejected final (blocklist/min_chars)", session=True
                )
                self._stream.reset_boundary()
                self._final_pending = (
                    False  # finalized-by-rejection: a drain can finish
                )
                self._utterance_finalized = (
                    True  # validation Issue 2: this text() is done
                )
                return
  - INSERT BEFORE the `return` (and after the bookkeeping):
                # BUG-001 / P1.M1.T1.S2: never a silent rejection. The tail is frozen as-is and
                # typing resumes at the next genuinely-new speech (_touch_speech -> resume()).
                logger.warning(
                    "streaming: final rejected by filter (blocklist/min_chars); tail frozen "
                    "as-is, typing resumes at next speech"
                )
                self._feedback.notify(
                    "filtered hallucination — not typed; keep dictating"
                )
                return
  - CONSTRAINTS: freeze/reset_boundary/bookkeeping lines stay byte-identical (Critical #2);
    the call sits INSIDE the streaming branch (Critical #5); notify is un-gated (Critical #7).

Task 3: EDIT voice_typing/daemon.py — _touch_speech() resume wiring.
  - FIND (:1354, first statements of the body):
        self._last_speech_monotonic = time.monotonic()
        if not self._utterance_finalized:
            self._final_pending = True
  - REPLACE WITH:
        # BUG-001 / P1.M1.T1.S2: genuinely-new speech lifts a rejected-final freeze (and any
        # post-cancel suppression) so the NEW utterance streams live. Idempotent, no keystrokes,
        # engine-internal lock only. Must run BEFORE the _final_pending guard: after a rejected
        # final _utterance_finalized is True, and resuming is needed precisely then.
        self._stream.resume()
        self._last_speech_monotonic = time.monotonic()
        if not self._utterance_finalized:
            self._final_pending = True
  - CONSTRAINTS: direct call (self._stream is always real, daemon.py:754 — mirror _on_partial's
    style); TOP placement (Critical #4); nothing else in the method changes.

Task 4: ADD the daemon-level regression test (place after :4639's Rev1 rejected test).
  - CODE (reference — adapt names to the file's actual style):
        def test_rejected_final_recovers_at_next_speech_with_cue(caplog):
            """BUG-001 daemon wiring: a rejected final freezes output + cues the user; the NEXT
            utterance's speech event resumes streaming so words type live again (PRD h2.1/h3.0)."""
            cfg = VoiceTypingConfig()
            cfg.filter.blocklist = ["thank you."]
            d, fb, rec, be = _make_daemon(cfg=cfg)
            d.start()
            d._on_partial("Hello world")
            d.on_final("Hello world")          # commits fine
            d._on_partial("thank you")         # the hallucination's on-screen tail
            d.on_final("thank you")            # rejected -> freeze + boundary + WARNING + cue
            assert d._stream.frozen is True
            assert fb.toasts, "no user-visible cue on rejection"
            assert any("filtered" in t or "hallucin" in t for t in fb.toasts)
            n0 = len(be.typed)
            d._on_partial("ank you")           # stray late partial of the REJECTED utterance
            assert len(be.typed) == n0 and d._stream.frozen is True   # mirror-only, still frozen
            d._touch_speech()                  # the next utterance's ('speech', {}) event
            assert d._stream.frozen is False   # resume() lifted it
            d._on_partial("The next real sentence")
            assert any("The next real sentence" in t for t in be.typed)   # LIVE typing resumes
            d.on_final("The next real sentence")   # and the commit path still works
            assert d._stream.frozen is False and "The next real sentence" in d._stream.committed
        # Optional caplog assert for the WARNING (logger="voice_typing.daemon", match "rejected").
  - CONSTRAINTS: uses the :684 construction pattern (default streaming=True; blocklist override);
    NO real audio/CUDA; fakes only.

Task 5: VALIDATE (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S2: daemon wires resume() at next speech + rejected-final cue (BUG-001 daemon half)".
```

### Implementation Patterns & Key Details

```python
# The wiring is two one-liners + a cue. Correctness rests on:
#  (1) PLACEMENT: resume() at the TOP of _touch_speech (before the _utterance_finalized guard) —
#      the rejected-final case has the flag True, so a guarded resume would never fire.
#  (2) TIMING: the lift happens at genuinely-new SPEECH, never at a stray late partial of the
#      rejected utterance (those arrive via _on_partial, which does NOT resume) — that is the
#      whole reason the freeze stays session-class until here (no retag).
#  (3) THE CUE ORDER: fake first (toasts recorder), then the daemon notify call, or the existing
#      rejected-branch tests AttributeError.
# Locking: resume() = engine lock only; on_final = _on_final_lock → engine lock. One direction,
#  no cycle; _touch_speech takes no daemon lock today and must not gain one.
```

### Integration Points

```yaml
ENGINE (S1 — input): self._stream.resume() semantics per S1's PRP; backend-failure freezes
  refuse to lift inside resume() (logged INFO) — the daemon needs no origin knowledge.

BUG-002 / P1.M1.T2.S2 (overlap, intentional): the _touch_speech→resume() wiring IS the
  post-cancel suppression lift at next utterance start. T2.S2 = its daemon-level cancel
  regression test (+ residual wiring only if missing). S2 adds no other suppression-clearing.

BUG-004 / P1.M1.T4.S1: the listening gate on _on_partial is T4's — do not add one here.

DOCS (P1.M3.T9): the cue text + recovery behavior get README/ACCEPTANCE treatment there
  (Mode B); S2 ships in-code comments only.

FEEDBACK: notify() is self-gated by hypr_notify; no state.json/state-machine interaction.
```

## Validation Loop

> AGENTS.md: two timeouts (inner `timeout N` + bash-tool timeout above); `.venv/bin/python -m pytest`; NO live daemon, NO CUDA. All gates are fake-driven unit tests.

### Level 1: The wiring landed (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- S1 input present ---"
grep -n "def resume" voice_typing/streaming.py && echo "L1a PASS: engine resume() exists" || echo "L1a FAIL: S1 not landed"
echo "--- _touch_speech calls resume BEFORE the guard ---"
sed -n "$(grep -n 'def _touch_speech' voice_typing/daemon.py | cut -d: -f1),+40p" voice_typing/daemon.py | grep -n "resume\|_final_pending = True" | head -4
echo "--- rejected branch has WARNING + notify, freeze byte-identical ---"
sed -n '1140,1175p' voice_typing/daemon.py | grep -n "freeze\|logger.warning\|_feedback.notify"
echo "--- fake has the toasts recorder ---"
grep -n "def notify" tests/test_daemon.py && echo "L1d PASS" || echo "L1d FAIL: fake gap"
# Expected: resume before _final_pending; warning+notify present; freeze(session=True) intact.
```

### Level 2: The new test + every existing daemon test green

```bash
cd /home/dustin/projects/voice-typing
echo "--- the new regression test ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "recovers_at_next_speech" 2>&1 | tail -3
echo "--- the pinned neighbors ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "rejected" 2>&1 | tail -3
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "touch_speech or rejected_hallucination_emits_no_latency" 2>&1 | tail -3
echo "--- full daemon suite ---"
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -4
# Expected: all green. If :4621 fails with AttributeError -> Task 1 ordering (Critical #3).
# If the new test fails at 'frozen is False' -> resume placement (Critical #4).
```

### Level 3: The recovery behavior is real, not test-tautological (one-off probe)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing.config import VoiceTypingConfig
from voice_typing import daemon as D
class F:  # minimal feedback with the notify recorder
    def __init__(self): self.partials=[]; self.toasts=[]
    def update_partial(self,t): self.partials.append(t)
    def set_phase(self,p): pass
    def notify(self,m): self.toasts.append(m)
cfg = VoiceTypingConfig(); cfg.filter.blocklist=["thank you."]
d = D.VoiceTypingDaemon(cfg, F(), recorder=None, recorder_host=None, host_factory=None,
                        backend=None, mic_prober=lambda: (True,None))
PY
# (Construction details vary — the authoritative proof is the Task 4 pytest; use this probe only
#  if you want a live-shaped check. Skip if the daemon ctor needs the full fake set from the test.)
echo "--- authoritative gate remains L2 ---"
```

### Level 4: Scope

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vE 'voice_typing/daemon\.py|tests/test_daemon\.py' | grep -E '\.py$|\.toml$|\.md$' \
  && echo "L4 FAIL: out of scope" || echo "L4 PASS: only daemon.py + test_daemon.py"
git diff voice_typing/streaming.py voice_typing/feedback.py | grep -q . && echo "L4 FAIL: engine/feedback touched (S1's)" || echo "L4 PASS: streaming.py + feedback.py untouched"
git diff voice_typing/daemon.py | grep -E '^\+.*freeze\(' && echo "L4 CHECK: freeze call changed? must stay byte-identical" || echo "L4 PASS: freeze call untouched"
# Expected: only the two files; freeze(...) line not in the + diff.
```

## Final Validation Checklist

### Technical Validation
- [ ] L0/L1a: S1's `resume()` confirmed present before wiring.
- [ ] L1: resume at top of `_touch_speech`; WARNING + notify in the streaming rejected branch; freeze call byte-identical; fake has `toasts`.
- [ ] L2: new test green; `-k rejected` / `-k touch_speech` / no-latency-line green; FULL `tests/test_daemon.py` green under `timeout 600`.
- [ ] L4: only `daemon.py` + `tests/test_daemon.py`; `streaming.py`/`feedback.py` untouched.

### Feature Validation
- [ ] Rejected final → WARNING logged + `notify` cue fired (user-visible, hypr_notify-gated).
- [ ] Stray late partial of the rejected utterance stays mirror-only (still frozen).
- [ ] Next speech (`_touch_speech`) → unfrozen; next partial TYPES; next final COMMITS (checkpoint advances).
- [ ] Rev 1 mode rejected-final behavior unchanged.

### Code Quality Validation
- [ ] Fake extension additive (no existing assertion touched); test names follow file style.
- [ ] Cue message short + user-appropriate; WARNING names the reason + the recovery.
- [ ] No new locks, no getattr shims, no suppression-clearing outside `resume()`.

### Scope Boundary Validation
- [ ] `streaming.py` untouched (S1); no BUG-003 space fix; no BUG-004 listening gate; no T2.S2 duplication.
- [ ] No README/ACCEPTANCE/config/socket edits (P1.M3.T9 / others own them).
- [ ] No live daemon run; fakes only; two-timeout discipline.

### Documentation & Deployment
- [ ] In-code comments cite BUG-001 / P1.M1.T1.S2 / PRD §4.2quater rule 2 where behavior is non-obvious.

---

## Anti-Patterns to Avoid

- ❌ Don't edit `streaming.py` (engine resume is S1's) or retag the freeze to `session=False` — the pin + :4621 exist to prevent exactly that.
- ❌ Don't add the daemon `notify` call before extending `_DaemonFakeFeedback` — the existing rejected tests will AttributeError (Critical #3 ordering).
- ❌ Don't hide `resume()` inside the `if not self._utterance_finalized:` guard — post-rejection the flag is True and the resume must still fire (Critical #4).
- ❌ Don't put the cue/WARNING in the Rev 1 branch — :4639 pins it byte-for-byte.
- ❌ Don't gate `notify()` on `hypr_notify` at the call site — the method self-gates.
- ❌ Don't add a listening gate to `_on_partial` (BUG-004/T4) or any extra suppression-clearing (T2.S2) — one task, one seam.
- ❌ Don't emit a latency line on rejection (:1876 pins its absence) or touch `_refresh_context_prompt`'s no-op list.
- ❌ Don't run the live daemon / real audio / CUDA; don't skip the two-timeout rule.

---

## Confidence Score

**9/10** for one-pass success. Both edit sites are quoted with live line numbers and surrounding code; S1's `resume()` contract is pinned (semantics, lock behavior, the never-retag invariant); the cue surface and its gating are verified against feedback.py + the :829 precedent; the fake inventory, the :684 construction pattern, and every keep-green test are identified by line number; and the reference test encodes the PRD's own repro at daemon level (frozen → cue → stray mirror-only → speech-resume → live typing). The −1: (a) the daemon test's exact interaction with commit's trailing-space/correction keystrokes means the `be.typed` membership assertions must be tolerant (`any(... in t ...)`) — prescribed; (b) standard tree-drift on the cited daemon.py line numbers (S1 edits only streaming.py, so the daemon anchors are stable, but grep-gates are content-based anyway).
