# PRP — P1.M3.T8.S2: tests/test_streaming.py asserts c/e/f/g (pause-join, cancel, key-freeze, stranded tail)

name: "T8.S2 — streaming E2E asserts c/e/f/g"
description: "Extend the landed S1 harness (tests/test_streaming.py) with the four remaining PRD §6 T8 assertions: (c) pause-join coherence, (e) Backspace-cancel, (f) user-keypress freeze, (g) stranded-tail freeze. Real small.en decode stream, RecordingTypingBackend, no mic, no daemon process, no real keystrokes."

---

## Goal

**Feature Goal**: PRD §6 T8 asserts (c), (e), (f), (g) pass as real-model E2E tests in `tests/test_streaming.py`, driving the REAL decode stream (small.en via the session-scoped `AudioToTextRecorder`) through the REAL `StreamingOutput` engine and the daemon-equivalent seams (`cancel()`, `note_user_keypress()`, stranded-tail freeze), with every keystroke captured by the in-file `RecordingTypingBackend`. Asserts (a)/(b)/(d) from S1 remain green and untouched in semantics.

**Deliverable**: Four new test functions (`test_c_pause_join`, `test_e_cancel`, `test_f_user_key_freeze`, `test_g_stranded_tail`) + the harness extensions they need (`StreamingHarness.cancel()`, `StreamingHarness.note_user_keypress()`, `StreamingHarness.freeze_stranded_tail()`, the daemon-shape mirror of the rejected-final branch in `on_final`, a mid-utterance action helper in the feed/consume plumbing, and the update of the module docstring's S1→S2 mapping comment). NO production-code changes — this task is verification only; if a production bug surfaces, report it (see "When a test finds a bug" below).

**Success Definition**: `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v` passes all 7 T8 tests (a, b, c, d, e, f, g) on the CUDA box; the fast no-CUDA sweep (`pytest tests/ -q`) still collects/skips cleanly (import purity preserved); every new assert failure dumps the harness diagnostics (`_dump_events`).

## User Persona (if applicable)

**Target User**: The developer/owner of voice-typing (this is a verification task, not a user-facing feature).

**Use Case**: Proving PRD §4.2quater rules 4 (stranded tail freezes), 5 (never type over the user's cursor), Backspace-cancel, and the context-prompt + deterministic-guard join behavior — against the real engine, not just unit doubles.

**Pain Points Addressed**: Unit tests (test_streaming_freeze.py / test_streaming_commit.py / test_daemon.py) pin the seams with synthetic inputs; nothing yet proves the REAL recorder→partials→engine→backend pipeline honors cancel/freeze/join semantics end to end. PRD acceptance #11 (T8c/e/f/g) is unmet without this.

## Why

- Closes P1.M3.T8 (the last Researching subtask of the streaming milestone); P1.M3.T9/T10 (acceptance evidence rows, README sync) depend on T8 being complete.
- The PRD's Rev 2 user guarantees — "typed text is never auto-deleted", "Backspace mid-fragment cancels it, mic still armed", "a mid-paragraph fragment never starts with a capital nor ends with a spurious period" — are exactly rules 4/5/cancel; E2E proof is the acceptance bar (PRD §7 #11–12).

## What

Four tests extending `tests/test_streaming.py` (see "Implementation Blueprint" for exact shapes):

### Success Criteria

- [ ] **(c)** `utt_pause.wav` (PAUSE_A + 3.0 s silence + PAUSE_B) joins into coherent committed text: fuzzy ≥0.80 vs `"I want to test whether this system keeps listening after a pause."`; every commit's typed piece obeys the deterministic guard postconditions relative to the ENGINE's committed truth; the mid-sentence branch (lowercase start + no trailing `.`) is exercised ≥1 time (bounded retry if model punctuation dodges it).
- [ ] **(e)** Cancel while a tail is pending: exactly one compensation `press_backspace(len(tail)−1)`; the simulated screen returns to exactly `committed`; the in-flight utterance's buffered audio is dropped (no commit for it, ever); listening stays on; a second cancel is a no-op (zero backend events); a follow-up utterance commits normally.
- [ ] **(f)** A non-Backspace keypress while a tail is pending: zero further revision keystrokes for that utterance; its commit absorbs the tail with NO keystrokes (no rewind, no retype, no trailing space); the freeze lifts at the boundary and the NEXT utterance types live again.
- [ ] **(g)** Forced drain-timeout with a pending tail: the tail is frozen on screen — no backspace after the freeze stamp, screen keeps `committed + tail`, `frozen` and `frozen_session` both True; a later commit absorbs without keystrokes and the session freeze survives the boundary.
- [ ] Asserts (a)/(b)/(d) unchanged and green; no production file modified.
- [ ] Fast sweep (`pytest tests/ -q`) still skip-guards cleanly — no heavy import at collection.

## All Needed Context

### Context Completeness Check

An implementer who knows nothing about this repo can build this from: the S1 harness (already in the file being extended), the exact production seams quoted below (daemon.cancel / note_user_keypress / _freeze_stranded_tail / on_final rejected-final branch), the StreamingOutput API, and the gotchas (G-tags + suppression semantics + physical-keystroke simulation). All file references below include line anchors from the current tree.

### Documentation & References

```yaml
- file: tests/test_streaming.py
  why: THE file being extended. S1 landed asserts a/b/d + the full harness.
  pattern: |
    - Module docstring L1-95: PRD T8 spec mapping (says c/e/f/g "belong to P1.M3.T8.S2 and
      will extend THIS file (fixtures + helpers are deliberately reusable; do not loosen
      them when S2 lands)") — update this mapping comment when S2 lands.
    - RecordingTypingBackend L~180-230 (screen model; press_backspace(n<=0) NOT recorded).
    - StreamingHarness L~300-420 (on_final = daemon.on_final streaming branch extraction;
      its rejected-final branch is "kept as a plain early return for S1 — S2 owns
      freeze/cancel semantics ... and will mirror the daemon shape exactly").
    - _wait_for / _feed_paced / _run_streamed / _consume L~440-570 (the plumbing; G-PACE,
      G-TRAILING-SILENCE, G-ORDER, G-ABORT invariants documented inline).
    - _dump_events L~575 (EVERY new assert failure must append this diagnostics dump).
    - _assert_commit_invariants L~600 (NOTE check #2 assumes every commit types a trailing
      space — false for frozen-absorb commits; see gotchas).
    - session fixture `stream_recorder` L698 (production build path; ONE recorder for all
      tests; each test calls harness.reset()).
    - test_a/test_b/test_d L~760-939 (naming + oracle discipline to copy).
  gotcha: |
    espeak/model punctuation is nondeterministic (S1 saw small.en ADD a period to PAUSE_A
    in one run). Oracles that depend on punctuation must be CONDITIONAL on the engine's
    committed truth — never on the pinned reference text.

- file: voice_typing/daemon.py
  why: The production seams the harness must mirror VERBATIM (behavior, not import — the
        harness never imports the daemon class, it re-implements these ~10-line bodies).
  pattern: |
    - on_final L1116-1256: gate → _cancel_suppress_final window (L1131-1140) → clean →
      rejected-final branch (L1146-1165: SESSION freeze + reset_boundary) → commit →
      record_final/latency → reset_boundary → _refresh_context_prompt.
    - _pending_tail_len L1421 (defensive gate: 0 when not listening).
    - _reset_stream_after_cancel L1436 (reset_after_cancel + feedback.update_partial("")).
    - note_user_keypress L1448 (gate on _listening → stream.note_user_keypress()).
    - _on_cancel_backspace L1470 (listener entry: cancel() when listening).
    - _freeze_stranded_tail L1532 (streaming gate + pending-tail gate + freeze(session=True)).
    - cancel L1603-1636: under lock — listening gate; n = max(_pending_tail_len()-1, 0);
      self._backend.press_backspace(n) DIRECTLY ON THE BACKEND (bypasses the engine);
      host.cancel() ONLY IF _text_in_flight (audio-discarding abort + sentinel suppression);
      _reset_stream_after_cancel().
    - _drain_timeout L1671-1693: _freeze_stranded_tail("drain timeout: stranded tail")
      THEN _safe_abort() — freeze BEFORE the abort. _DRAIN_TIMEOUT_S = 5.0 (L149).
  gotcha: cancel()'s backspace goes through the daemon's backend reference, NOT through
          StreamingOutput — the engine's tail stays stale-by-design (compensation is by
          subtraction because the physical keystroke is invisible to the engine).

- file: voice_typing/streaming.py
  why: The engine under test; exact state transitions the asserts read.
  pattern: |
    - pending_tail_len() / reset_after_cancel() (sets _suppressed) / reset_boundary()
      (clears tail+suppression, lifts PER-UTTERANCE freeze only) / freeze(session=)
      (promote-only) / note_user_keypress() (per-utterance freeze iff streaming+tail).
    - on_partial: suppressed → mirror raw partial only; frozen → mirror typed tail only.
    - commit() frozen path: absorbs tail into committed WITHOUT keystrokes and WITHOUT the
      trailing space; clears suppression; mirrors committed.
  gotcha: after reset_after_cancel(), the NEXT utterance's partials are mirror-only until
          its commit lands (suppression clears in commit()/reset_boundary, which run at the
          final) — "say the sentence again" types once at commit, live typing resumes for
          the utterance AFTER that. Assert this, don't fight it.

- file: voice_typing/textproc.py
  why: apply_streaming_guards L82-134 — the deterministic postconditions assert (c) checks.
  pattern: |
    context = committed.rstrip(); empty or ends ".!?" → fragment returned VERBATIM
    (case preserved, period kept). Otherwise (mid-sentence): first cased char lowercased
    AND exactly one trailing "." stripped (if present).

- file: tests/test_streaming_freeze.py, tests/test_streaming_commit.py
  why: Unit-level coverage that ALREADY exists (do not duplicate; cite in test docstrings).
  pattern: freeze classes/promotion, note_user_keypress semantics, frozen-commit absorb,
          cancel-adjacent commit mechanics — all pinned with RecordingBackend doubles.

- file: tests/test_key_listener.py
  why: PRD T8 tail note — "the evdev key-event parser is unit-tested separately with
        synthetic events (no real keyboard); real-Backspace behavior stays in the T5
        manual smoke". S2 therefore drives the DAEMON SEAMS (harness.cancel /
        note_user_keypress), never evdev.

- file: plan/007_cfc245548aec/P1M3T8S2/research/seams-and-oracles.md
  why: This PRP's research notes — daemon seam line numbers, suppression timeline,
        physical-keystroke simulation rationale, oracle determinism analysis.
```

### Current Codebase tree (tests/ + voice_typing/ only — the relevant slice)

```bash
tests/
├── test_streaming.py          # ← THE file: S1 harness + asserts a/b/d (939 lines); S2 extends
├── test_streaming_core.py     # engine unit: on_partial paths
├── test_streaming_commit.py   # engine unit: commit paths (incl. frozen absorb)
├── test_streaming_freeze.py   # engine unit: freeze classes, note_user_keypress
├── test_key_listener.py       # evdev parser + KeyListener units
├── test_daemon.py             # daemon wiring units (cancel, drain, freeze seams)
├── test_feed_audio.py         # the G-tag convention source
└── out/                       # utt_{simple,pause,multi,punct}.wav (make_test_audio.sh)
voice_typing/
├── streaming.py               # StreamingOutput (engine under test)
├── daemon.py                  # seam source of truth (mirror, don't import)
├── textproc.py                # apply_streaming_guards (assert-(c) postconditions)
└── typing_backends.py         # TypingBackend ABC (type_text / press_backspace)
```

### Desired Codebase tree with files to be added/changed

```bash
tests/test_streaming.py        # MODIFIED ONLY (asserts c/e/f/g + harness/plumbing extensions)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL — inherited G-tags (documented in the S1 module docstring; they encode REAL
# hangs/flakes that already bit this repo):
#   G-PACE               feed 0.1 s slices, sleep their audio duration (VAD is WALL-CLOCK).
#   G-TRAILING-SILENCE   paced zero slices (already inside _feed_paced — reuse it, never
#                        rewrite it).
#   G-ORDER              consume thread BEFORE first feed.
#   G-ABORT              recorder.abort() blocks on was_interrupted.wait() (set only
#                        INSIDE text()) — ALWAYS from a helper thread, join with timeout.
#   G-SKIP-GUARDS        collection must import no heavy dep (module-level imports stay
#                        stdlib + streaming/typing_backends/prompt_engine/textproc).
#   G-FUZZY              _token_overlap >= 0.80 for model output; EXACT oracles only over
#                        the harness's own event/commit log.

# CRITICAL — the physical Backspace is NOT a backend event in production. The evdev
# listener sees the user's keystroke; the daemon compensates by SUBTRACTION. In the
# simulated screen the test MUST play the user's part: backend.press_backspace(1) BEFORE
# invoking the cancel seam — only then does "screen == committed" come out exact
# (real world: 1 physical + (len-1) compensation deletions; simulated: same two calls).

# CRITICAL — daemon.cancel() reads pending_tail_len() AT CANCEL TIME (after the physical
# keystroke deleted a screen char but while the ENGINE tail is still the full fragment —
# the engine never saw the keystroke). Mirror the order: physical_bs(1) on the backend,
# THEN cancel() which computes n from the engine's still-full tail.

# CRITICAL — frozen-absorb commits type NOTHING (no rewind, no retype, NO trailing
# space). _assert_commit_invariants' check #2 ("every commit typed its trailing space")
# is FALSE for sessions containing frozen commits — write scoped invariants in the new
# tests; do not loosen the S1 helper.

# CRITICAL — abort() drops the in-flight utterance: the consume thread's text() returns
# WITHOUT cb firing (no raw_final, no commit). Count RAW finals (harness.raw_finals) for
# consume-loop targets, never commits. The recorder stays healthy post-abort (abort only
# interrupts the current transcription) — the follow-up utterance in test_e PROVES this.

# GOTCHA — mid-utterance race: the commit may land between "pending_tail_len() > 0" and
# the act. Capture the pre-state, act immediately, and if the tail was already empty at
# act time (raced), re-feed the same WAV once (bounded, in-test) instead of flaking.

# GOTCHA — RealtimeSTT races a final against abort(); the daemon handles this with the
# _cancel_suppress_final sentinel window (daemon.py L1131-1140). In-process there is no
# marked sentinel: mirror with a text()-generation counter (bump per rec.text() call in
# the consume wrapper; cancel records the generation; on_final drops finals while the
# generation is unchanged; the next rec.text() entry clears the window).

# GOTCHA — _DRAIN_TIMEOUT_S is 5.0 s in production but the harness forces the stranded
# path DIRECTLY (freeze + abort) — do not wait 5 s or reproduce the Timer machinery
# (tests/test_daemon.py owns that).

# Repo discipline (AGENTS.md): every non-trivial command under GNU `timeout` + a generous
# bash-tool timeout. Heavy suite: `timeout 900 ... pytest tests/test_streaming.py -v`.
# Never run the daemon/launch_daemon.sh in the foreground (not needed here at all).
```

## Implementation Blueprint

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EXTEND StreamingHarness (tests/test_streaming.py, inside the existing class)
  - ADD `self._text_generation = 0` and `self._cancel_generation: int | None = None`
    to __init__ (+ reset()); ADD the generation bump in a thin consume wrapper (the
    _consume target wraps rec.text(cb) — bump BEFORE each call).
  - REWRITE on_final's rejected-final branch to the daemon shape (daemon.py L1146-1165):
    if cfg.output.streaming: stream.freeze("rejected final (blocklist/min_chars)",
    session=True); stream.reset_boundary() — then return. (S1's docstring explicitly
    reserves this for S2: "mirror the daemon shape exactly".)
  - ADD the cancel-window mirror at the TOP of on_final (daemon.py L1131-1140): while
    _cancel_generation == current _text_generation → drop the final (return). Keep the
    listening gate first, exactly as the daemon keeps its gate outside the lock.
  - ADD `def cancel(self) -> dict:` mirroring daemon.cancel() (L1603-1636), harness
    flavor: listening gate; n = max(stream.pending_tail_len() - 1, 0); if n > 0:
    self.backend.press_backspace(n)  # DIRECT on the backend — NOT via the engine;
    if consume thread is inside rec.text() (generation active): _cancel_generation =
    _text_generation; abort the recorder FROM A HELPER THREAD (G-ABORT);
    stream.reset_after_cancel(); feedback.update_partial(""); return {"ok": True}.
  - ADD `def note_user_keypress(self) -> None:` mirroring daemon.note_user_keypress
    (L1448): gate on listening.is_set(); forward to stream.note_user_keypress().
  - ADD `def freeze_stranded_tail(self, reason: str) -> None:` mirroring
    daemon._freeze_stranded_tail (L1532): if cfg.output.streaming and
    stream.pending_tail_len() > 0: stream.freeze(reason, session=True).
  - NAMING: keep the daemon method names verbatim (cancel / note_user_keypress /
    freeze_stranded_tail) — the mirror is the point.
  - PLACEMENT: inside class StreamingHarness, grouped under a new
    "--- S2: daemon-seam mirrors (asserts c/e/f/g) ---" comment.

Task 2: ADD the mid-utterance action helper to the plumbing section
  - `def _stream_with_mid_action(rec, harness, wav, act, *, want_finals_after_act,
    act_timeout=30.0, settle_s=0.5) -> bool:` — composes the EXISTING _consume/_feed_paced
    (G-ORDER: consume first): start both threads; _wait_for(lambda:
    harness.stream.pending_tail_len() > 0, timeout=act_timeout); snapshot tail BEFORE
    act; invoke act(harness) EXACTLY once; wait for want_finals_after_act RAW finals
    (raw_finals-relative count — the act may drop one); settle; teardown exactly like
    _run_streamed's finally (stop.set → helper-thread abort → joins). Return whether the
    tail was non-empty at act time (False == raced; caller retries once).
  - GOTCHA: for test_e the aborted utterance yields NO raw final — set the wait target to
    the FOLLOW-up phase inside the test instead (see Task 4).

Task 3: ADD test_c_pause_join (assert c)
  - harness.reset(); feed utt_pause.wav want_finals=2 (the 3 s pause > 0.8 s endpointer
    → two finals; test_d precedent).
  - Assert (deterministic, per commit k with typed piece p_k and preceding ENGINE
    committed truth C = committed_state_at(commit_k_stamp) — the S1 helper):
      * if C.rstrip() and C.rstrip()[-1] not in ".!?": first cased char of p_k is
        lowercase AND p_k.rstrip() does not end with "."   # the guard postconditions
      * else: p_k case is whatever the model produced (no case assertion).
  - Assert the join coherence: " ".join(pieces) token-overlap >= 0.80 vs
    PAUSE_A + " " + PAUSE_B (G-FUZZY).
  - Assert the mid-sentence branch FIRED >= 1 time (some commit had non-empty
    terminator-free C). If it did not (model put a period on PAUSE_A — observed in S1
    runs): bounded retry — one more utt_pause pass in the SAME session (test_b retry
    precedent), re-assert; if still not exercised, FAIL with _dump_events (rare;
    diagnostics first, never a silent pass).
  - Assert end-state screen == committed + tail (engine invariant).
  - NAMING/PLACEMENT: after test_b, before test_d; docstring cites PRD §6 T8c +
    textproc.apply_streaming_guards + the engine-truth-conditional oracle rationale.

Task 4: ADD test_e_cancel (assert e)
  - Phase 1 — mid-utterance cancel on utt_pause (long first half = wide window):
    via _stream_with_mid_action with act = lambda h: (h.backend.press_backspace(1),
    h.cancel())  # physical keystroke, THEN the daemon seam
    (order matters: the engine tail must still be full when cancel() computes n).
    * If the helper reports the race (tail empty at act): retry once with a re-feed.
    * Assert: exactly one compensation event; its n == len(tail_before) - 1; screen ==
      committed_before EXACTLY; stream.tail == ""; listening.is_set() still True; no new
      commit_log entry for the dropped utterance (bounded 3 s wait — the audio was
      discarded, text() returned without cb).
  - Phase 2 — idempotence: call harness.cancel() again → ZERO new backend events, no
    state change (PRD: "further Backspaces are plain user edits").
  - Phase 3 — "keep listening, say it again": feed utt_simple.wav want_finals=1 via
    _run_streamed → commit lands, piece fuzzy >= 0.80 vs SIMPLE_TEXT, and the commit
    window contains its typed text (partial typing for THIS utterance is legitimately
    suppressed until the commit — post-cancel suppression; assert >= 1 mirror partial
    arrived during it instead). This also proves the recorder survived the abort.
  - DOCSTRING: cite daemon.cancel() L1603 + the subtraction-compensation rationale.

Task 5: ADD test_f_user_key_freeze (assert f)
  - Mid-utterance on utt_pause via _stream_with_mid_action, act = harness.note_user_keypress.
  - Snapshot events/screen at act time (t_act). Assert: ZERO backend events in
    (t_act, commit_stamp] — no revision keystrokes for that utterance (PRD rule 5);
    screen at commit == screen at t_act (frozen absorb types NOTHING, not even the
    trailing space); commit_log grew by 1 with engine_committed == the absorbed join.
  - Assert freeze lifecycle: stream.frozen True between act and the commit's
    reset_boundary; frozen False after (per-utterance class lifted).
  - Phase 2 — next utterance types live: feed utt_simple want_finals=1 → >= 1 type event
    BEFORE its commit stamp (streaming resumed; no suppression involved here).
  - GOTCHA: do NOT call _assert_commit_invariants on this session (frozen commit has no
    trailing space — check #2 would false-fail). Scoped asserts only.

Task 6: ADD test_g_stranded_tail (assert g)
  - Mid-utterance on utt_pause via _stream_with_mid_action, act = the daemon's
    _drain_timeout sequence (daemon.py L1671-1693), forced (NO 5 s wait):
    h.freeze_stranded_tail("drain timeout: stranded tail") THEN helper-thread abort
    (G-ABORT — freeze BEFORE the abort, exactly as production orders it).
  - Assert: no bs events after the freeze stamp (typed text NEVER rewound — PRD rule 4);
    screen == committed_before + tail_before over a bounded 2 s watch; stream.frozen and
    stream.frozen_session both True.
  - Phase 2 — a late/racing commit absorbs frozen: feed utt_simple want_finals=1 → the
    commit types NOTHING (screen unchanged across its stamp), engine committed absorbs,
    and frozen_session is STILL True after reset_boundary (session freezes survive
    boundaries; only reset_session/fresh arm clears — unit-pinned in
    test_streaming_freeze.py, here proven on the real pipeline).
  - DOCSTRING: cite PRD §4.2quater rule 4 + daemon._drain_timeout.

Task 7: SYNC the module docstring + final checks
  - Update the S1 spec-mapping comment: asserts (c)/(e)/(f)/(g) now landed; note the
    seam-mirror design (daemon bodies re-implemented, not imported) and the
    physical-keystroke simulation for (e).
  - Run the full validation ladder (below). Commit with a message referencing
    P1.M3.T8.S2 / PRD §6 T8 c-e-f-g.
```

### Implementation Patterns & Key Details

```python
# The cancel seam mirror (Task 1) — the ORDER is the spec:
def cancel(self) -> dict:
    if not self.listening.is_set():
        return {"ok": True}
    tail_len = self.stream.pending_tail_len()      # engine truth — STILL the full tail
    n = max(tail_len - 1, 0)                        # subtraction compensation
    if n > 0:
        self.backend.press_backspace(n)             # daemon calls its backend DIRECTLY
    if <consume thread inside rec.text()>:          # generation active
        self._cancel_generation = self._text_generation
        threading.Thread(target=_safe_abort, args=(self._rec,), daemon=True).start()
    self.stream.reset_after_cancel()                # fresh tail + suppressed
    self.feedback.update_partial("")
    return {"ok": True}

# PATTERN: every assert failure ends with + _dump_events(harness) — the S1 discipline.
# PATTERN: oracles conditional on ENGINE truth (committed_state_at) — never on reference
#          punctuation (model output is nondeterministic; S1 precedent in test_d).
# CRITICAL: harness.reset() does NOT clear backend events of prior tests... it DOES
#          (reset() rebuilds backend) — rely on it; per-test state starts clean.
```

### Integration Points

```yaml
NONE in production code. This task touches tests/test_streaming.py only.
- tasks.json / PRD.md / prd_snapshot.md: FORBIDDEN (owned by orchestrator/humans).
- If a new test finds a PRODUCTION bug: do NOT fix production here — write the failing
  evidence into the test docstring as xfail(strict=True) with the diagnosis, and surface
  it in the completion report (the orchestrator re-plans via issue feedback).
```

## Validation Loop

### Level 1: Collection & fast units (no CUDA, seconds)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_streaming.py --collect-only -q
# Expected: 7 T8 tests collected (a,b,c,d,e,f,g); no import errors (G-SKIP-GUARDS).

timeout 120 .venv/bin/python -m pytest tests/test_streaming_core.py tests/test_streaming_commit.py tests/test_streaming_freeze.py tests/test_voicectl.py -q
# Expected: all pass — engine units untouched, import purity intact.

timeout 300 .venv/bin/python -m pytest tests/ -q
# Expected: heavy modules SKIP cleanly (no WAVs/deps guard fires only where intended);
# fast modules pass. (bash tool timeout: 360.)
```

### Level 2: The deliverable (CUDA box; first model load is tens of seconds)

```bash
./tests/make_test_audio.sh    # idempotent; ensures tests/out/*.wav exist
timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v
# (bash tool timeout: 960.) Expected: 7 passed (incl. S1's a/b/d — unchanged semantics).
# Targeted iteration while developing:
timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -v -k "test_c_pause_join or test_e_cancel"
timeout 600 .venv/bin/python -m pytest tests/test_streaming.py -v -k "test_f_user_key_freeze or test_g_stranded_tail"
```

### Level 3: Cross-checks (cheap, after green)

```bash
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q   # seam units still green
# (bash tool timeout: 660.) Expected: pass — proof the mirrors still match the seams.
```

### Level 4: Determinism pass

```bash
# Run the new tests twice more back-to-back; a flake = a race in the TEST (fix the test,
# not the threshold). The bounded retries (c: one re-feed; e: one re-feed on race) absorb
# the known model nondeterminism.
timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v -k "test_c_ or test_e_ or test_f_ or test_g_"
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1–4 all green; `tests/test_streaming.py` = 7 T8 tests passing.
- [ ] `--collect-only` shows no heavy imports at collection (G-SKIP-GUARDS).
- [ ] No production file modified (`git status` → only tests/test_streaming.py).
- [ ] Two consecutive runs of the new tests pass (determinism).

### Feature Validation

- [ ] (c) join fuzzy ≥0.80; guard postconditions hold per engine truth; mid-branch exercised.
- [ ] (e) compensation n exact; screen == committed; audio dropped (no commit, ever); second cancel no-op; follow-up commits.
- [ ] (f) zero keystrokes after the keypress until the commit; absorb without trailing space; freeze lifts; next utterance types live.
- [ ] (g) no rewind after freeze; tail stays on screen; session freeze survives a commit.
- [ ] Every failure path dumps `_dump_events`.

### Code Quality Validation

- [ ] Harness mirrors keep daemon method names + ordering (cancel/note_user_keypress/freeze_stranded_tail).
- [ ] Reused `_feed_paced`/`_consume` unchanged (G-tags intact); no new unbounded loops; all waits bounded via `_wait_for`.
- [ ] New tests follow `test_<letter>_<name>` naming and carry PRD-citing docstrings.

## Anti-Patterns to Avoid

- ❌ Don't drive evdev / real keyboards — PRD T8 keeps that in unit + T5 manual smoke; S2 drives daemon seams.
- ❌ Don't count commits where RAW finals are the contract (abort drops finals silently).
- ❌ Don't reuse `_assert_commit_invariants` on frozen-commit sessions (trailing-space check #2).
- ❌ Don't wait on production timers (`_DRAIN_TIMEOUT_S`) — force the seam directly.
- ❌ Don't call `rec.abort()` from the test thread (G-ABORT).
- ❌ Don't assert model punctuation unconditionally — condition on engine truth.
- ❌ Don't "fix" flaky races by loosening thresholds — use the bounded re-feed retry and diagnose via `_dump_events`.

---

## Confidence Score: 9/10

The harness, engine, seams, and unit precedents all exist and are quoted with line anchors; the only residual risk is real-model nondeterminism in (c) (mitigated by the engine-truth-conditional oracle + bounded retry, exactly the S1 precedent) and abort/restart health of the in-process recorder across cancels (proven in-test by the follow-up utterance; if it proves flaky, the generation-counter window in Task 1 is the tuning point).
