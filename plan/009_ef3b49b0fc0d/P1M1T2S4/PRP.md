# PRP — P1.M1.T2.S4: Hand off the seed only on the first accepted final

## Goal

**Feature Goal**: Make the §4.8.1 initial-prompt seed a **recognition-only, first-utterance**
conditioning input: a confirmed seed installed by a seed arm (S3) stays resident through any
number of rejected finals and is **replaced exactly once, on the first accepted final**, by the
normal rolling context computed **only from this session's accepted finals** — independent of the
rolling-prompt config switch, of typing/commit success, and of the display engine's state. The seed
never reaches displayed text, spacing, logs/latency, status, feedback, recovery, client
persistence, or the next session.

**Deliverable** (2 source files + 1 test file edited; no new files):
1. `voice_typing/daemon.py` — (a) `__init__` state `_seed_handoff_pending`, `_seed_handoff_done`,
   `_session_accepted`; (b) new `_handoff_context_prompt(accepted)`; (c) ONE call in `on_final`
   at the acceptance point; (d) one extra source branch in `_refresh_context_prompt`; (e) resets
   in `_arm`; (f) ONE line beside S3's `self._seed_active = True` in `_start_fenced`;
   (g) Mode A docstrings (seed vs rolling privacy).
2. `voice_typing/prompt_engine.py` — docstring-only: a "seed vs rolling context" privacy paragraph
   (module docstring + `rolling_context_prompt`).
3. `tests/test_daemon.py` — a seed-handoff test section (accepted/rejected finals, config-off,
   typing failure, missing seam, Rev 1 mode, next-session reset, no seed text in logs).

**Success Definition**:
- (a) Seeded session, rejected finals only (blocklist / min_chars): `host.prompts` receives NO
  push from the handoff; `_seed_handoff_pending` stays True; the tail freezes exactly as today.
- (b) First accepted final: exactly ONE handoff push = `rolling_context_prompt(" ".join(accepted))`
  when `asr.context_prompt` is on and the child is capable, else `""`; `_seed_handoff_pending`
  False, `_seed_handoff_done` True. Later commits refresh from the accumulator only.
- (c) The handoff runs BEFORE typing/commit: a backend that raises, a frozen engine, or an early
  native return above the generic branches cannot skip it.
- (d) No seed text is stored on the daemon beyond S3's own `_seed_active` boolean; the
  accumulator contains only dictated finals; logs carry word counts; `status_snapshot`,
  feedback, and `SessionRecovery` inputs are unchanged.
- (e) Non-seeded sessions are byte-identical: every existing `tests/test_daemon.py` test passes
  unedited (including `host.prompts == ["", "second"]`).
- (f) `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q` green;
  `git diff --name-only` == the three files.

## User Persona

**Target User**: the opt-in editor-integration user (§4.8.1) whose pre-caret text seeds the first
decode so a mid-paragraph continuation comes out lower-case and unpunctuated.

**Use Case**: Arm with a seed → dictate. Hallucinated/"thank you" finals are rejected (seed kept,
say it again) → the first real sentence is accepted → from then on the decoder is conditioned on
what was *dictated this session*, never on the editor text again.

**Pain Points Addressed**: the editor text bleeding into later utterances (stale conditioning,
worse accuracy after the first sentence) and into anything the user can see or copy; with the
rolling prompt switched off, the seed silently conditioning a whole session.

## Why

- **Arch mandate** (`architecture/system_context.md`, "Confirmed seed before capture"): "Don't put
  seed in committed text, spacing, latency, logs, feedback, replies or recovery. After first
  accepted final only, reuse rolling logic; rejected final may settle the boundary but doesn't
  consume the seed. Native committed input comes only from the current session's accepted
  finals, not the live draft or other sessions."
- **Today's only replacement path is not a handoff.** `_refresh_context_prompt` is gated on
  `cfg.asr.context_prompt` (off ⇒ the seed would condition the entire session) and sources from
  `StreamingOutput.committed` (absent on the native path T4.S4 adds; can absorb an unaccepted
  frozen tail — `streaming.py:362-384`).
- **Downstream consumes it.** T4.S4 (native finals before any generic output) needs an
  acceptance-only accumulator it can keep feeding before its early return; S5 (focus-based starts)
  and the CLI/CPU verification rely on the seed being first-utterance-only.

## What

- Add the three state fields, the handoff method, its single call site, the accumulator source
  branch, the `_arm` resets, and the one-line hook in S3's seam — exactly as specified in the
  research note §3 (code given verbatim).
- Privacy docstrings in `daemon.py` (`on_final`, `_handoff_context_prompt`,
  `_refresh_context_prompt`, `_arm`) and `prompt_engine.py` (module + `rolling_context_prompt`).

### Success Criteria

- [ ] (a)–(f) under Success Definition hold, demonstrated by test output.
- [ ] `_handoff_context_prompt` never raises and performs no blocking call (queue put only).
- [ ] The seed text is never an argument to any method this task adds.

## All Needed Context

### Context Completeness Check

_Pass._ `on_final` (entry gate → cancel window → clean → rejection → acceptance → typing →
record/log → refresh), `_arm`, `_clear_context_prompt`, `_refresh_context_prompt`,
`prompt_engine.rolling_context_prompt`/`trim_prompt`, `textproc.clean`, and the relevant
`StreamingOutput.committed` lines were read verbatim; the test idiom (`_PromptRecordingHost`,
`_make_daemon(cfg=, recorder_host=)`) is verified; the S3 contract (`_seed_active`, the revalidate
step that sets it, `start_with_seed`) is pinned from its PRP. An agent new to the repo can
implement from this PRP + the research note.

### Documentation & References

```yaml
# MUST READ — the mandate
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Confirmed seed before capture', last paragraph: after the first accepted final only, reuse
        rolling logic; a rejected final may settle the boundary but doesn't consume the seed; native
        committed input = this session's accepted finals only; never in committed text/spacing/
        latency/logs/feedback/replies/recovery."
  critical: "Those two sentences ARE the acceptance spec for this task."

# MUST READ — this task's design with verbatim code + site table
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S4/research/seed_handoff_design.md
  why: "§1 the verbatim site table (acceptance point = after `_utterance_finalized = True`, before
        `if self._streaming_now()`); §2 the three gaps; §3 the settled design with exact code for
        state, _handoff_context_prompt, the _refresh_context_prompt branch, _arm resets, the S3 hook;
        §4 every path the seed must not reach (verified untouched); §5 test idioms; §6 an upstream
        observation about S3's warm plain re-arm clear."
  critical: "§3: do NOT write _seed_active from this task (leave it True after handoff); do NOT reset
            _seed_handoff_pending in _arm."

# INPUT CONTRACT (parallel; assume landed exactly as specified)
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S3/PRP.md
  why: "Defines _seed_active (set True in _start_fenced's revalidation on an APPLIED prime; persists
        across disarm; False only on confirmed clear/isolation), start_with_seed(seed), ArmOutcome.
        Its DOWNSTREAM line: 'S4 reads ArmOutcome.context_seeded to know a seed awaits handoff; S4
        does NOT re-prime.'"
  critical: "The ONE-LINE hook goes beside `self._seed_active = True` (search for it). If S3 is not
            landed when you start, gate per Task 0 and still land everything else (tests drive the
            state directly)."

# INPUT CONTRACT (landed, commit de29942)
- docfile: plan/009_ef3b49b0fc0d/P1M1T2S1/PRP.md
  why: "prompt_engine: fit_initial_prompt (seed), rolling_context_prompt (rolling; cuts at the last
        . ? ! and trims to the token cap) — the function the handoff reuses."
  critical: "rolling_context_prompt('Hello world.') == '' (a final ending a sentence hands off to a
            context-free decode) — intended; assert it, don't 'fix' it."

- file: voice_typing/daemon.py
  why: "on_final ~1364 (acceptance point ~1536); _arm ~1692 (resets beside `_rev1_committed = \"\"`
        @1740); _refresh_context_prompt ~2078 (source selection @2113-2115); __init__ ~921."
  pattern: "Mirror _refresh_context_prompt: defensive getattr on set_prompt, try/except never-raise,
            debug log with a WORD COUNT only, runs under _on_final_lock (not _lock)."
  gotcha: "on_final runs on the reader thread — no blocking, no _lock. The handoff must precede the
           typing branches, not follow them."

- file: voice_typing/prompt_engine.py
  why: "Module docstring (lines 1-36) and rolling_context_prompt docstring (@120) — add the
        seed-vs-rolling privacy paragraph. DOCSTRING-ONLY edits; no code change."
  gotcha: "Import purity: module scope stays stdlib-only (do not add imports)."

- file: tests/test_daemon.py
  why: "_PromptRecordingHost @5028; test_on_final_streaming_pushes_context_prompt_to_host @5231
        (construction idiom to copy); _make_daemon @903; _FakeHost @782."
  pattern: "cfg = VoiceTypingConfig(); host = _PromptRecordingHost(cfg, _DaemonFakeFeedback(),
            daemon.LatencyLog(), None, None, None); host.device['context_prompt'] = True;
            host.spawn(); d, fb, rec, be = _make_daemon(cfg=cfg, recorder_host=host); d.start();
            set d._seed_handoff_pending = True; drive _on_partial/on_final; assert host.prompts."
  critical: "Set the pending flag AFTER d.start(): the legacy arm-time clear pushes '' first
            (prompts[0] == ''), exactly as the existing test shows."

- file: voice_typing/textproc.py
  why: "clean(): rejects len < min_chars (2) and blocklist exact matches ('you', 'bye.', 'thank you.')."
  pattern: "Use 'you' / 'bye' as rejected finals and 'Hello there' as the accepted one."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py          # ← EDIT: +_seed_handoff_pending/_seed_handoff_done/_session_accepted,
                                #   +_handoff_context_prompt, +1 call in on_final, +1 branch in
                                #   _refresh_context_prompt, +2 resets in _arm, +1 hook line in
                                #   _start_fenced (S3's), Mode A docstrings.
voice_typing/prompt_engine.py   # ← EDIT (docstrings only): seed vs rolling privacy.
tests/test_daemon.py            # ← EDIT: + "P1.M1.T2.S4 — seed handoff" test section.
voice_typing/recorder_host.py   # S2's — UNTOUCHED (set_prompt / prime_prompt consumed as-is).
voice_typing/streaming.py       # UNTOUCHED (committed property only read).
voice_typing/textproc.py        # UNTOUCHED.
```

### Desired Codebase tree with files to be changed

```bash
# (same 3 files; no new files)
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — ACCEPTED MEANS textproc.clean RETURNED NON-EMPTY AND THE FINAL WAS NOT DROPPED.
# The cancel-suppression window and the listening gate `return` BEFORE clean — those finals are
# never accepted and must never trigger the handoff. The rejection branch (`if not cleaned:`)
# returns without any push — leave it byte-identical; the seed is simply retained.

# CRITICAL #2 — HANDOFF BEFORE TYPING. Place the call right after `self._utterance_finalized = True`
# and before `if self._streaming_now():`. A raising backend, a frozen engine, or a native
# early-return (T4.S4, inserted above the generic branches) must not be able to skip it.

# CRITICAL #3 — CONFIG-OFF STILL REPLACES. When cfg.asr.context_prompt is false (or
# _context_prompt_active is not True), the replacement text is "" (a known-empty prompt), NOT a
# skip. Skipping is the whole-session seed leak this task exists to close. In the degraded case
# (no executor) the setter is a harmless no-op on a child that has no prompt lane.

# CRITICAL #4 — THE ACCUMULATOR IS ACCEPTED-ONLY AND SESSION-SCOPED. Append `cleaned` only.
# Never append a frozen tail, a partial, the seed, or text from a previous session (_arm resets
# the list). Do NOT route it into SessionRecovery / feedback / latency — those keep their inputs.

# CRITICAL #5 — NEVER WRITE _seed_active. After the handoff the child holds THIS session's rolling
# text; S3's next-arm policy must still see "a prompt is resident" (True) so a plain arm
# confirmed-clears and a seed arm re-primes. This task reads nothing from the seed but the boolean
# hook; the seed string never enters any method added here.

# CRITICAL #6 — DON'T RESET _seed_handoff_pending IN _arm. The seed arm's seam sets it True BEFORE
# calling the arm body; an `_arm` reset would erase it. _arm resets only _session_accepted and
# _seed_handoff_done (both per-session).

# CRITICAL #7 — READER THREAD, NO _lock. on_final runs on the recorder reader thread under
# _on_final_lock. set_prompt is a non-blocking queue put (S2 contract) — keep it that way; never
# take self._lock, never wait, never raise out of the handoff.

# CRITICAL #8 — EXISTING TESTS STAY GREEN UNEDITED. Non-seeded sessions never set
# _seed_handoff_done → _refresh_context_prompt takes its old branches → identical pushes.

# CRITICAL #9 — LOG COUNTS, NOT TEXT. "seed handed off to rolling context (%d words)". The seed
# and dictated text never appear in a new log line, status field, feedback write or reply.

# GOTCHA #10 — AGENTS.md: full paths + inner timeouts (timeout 600 .venv/bin/python -m pytest
# tests/test_daemon.py -q); hermetic fakes only; no daemon in the foreground; no ruff/mypy.
```

## Implementation Blueprint

### Data models and structure

```python
# __init__ (beside self._rev1_committed):
self._seed_handoff_pending = False    # a confirmed seed is resident in the child and not yet replaced
self._seed_handoff_done = False       # this armed session replaced its seed via the accumulator
self._session_accepted: list[str] = []  # THIS session's accepted finals only (never seed / tail text)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE + baseline
  - RUN: cd /home/dustin/projects/voice-typing
         grep -n '_seed_active = True\|def _start_fenced\|def start_with_seed' voice_typing/daemon.py
         timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -1
  - If S3 is NOT landed: proceed with Tasks 1-5 and the state-driven tests; add the Task-3 hook line
    the moment `_seed_active = True` exists (leave a clearly marked TODO otherwise and report it).

Task 1: EDIT voice_typing/daemon.py — state + handoff method
  - ADD the three fields in __init__ (blueprint above).
  - ADD `_handoff_context_prompt(self, accepted: str) -> None` directly ABOVE
    `_refresh_context_prompt` — the verbatim body in research §3: append; if not pending return;
    clear pending / set done; text = rolling_context_prompt(" ".join(accumulator)) when
    cfg.asr.context_prompt and _context_prompt_active is True else ""; defensive setter; debug
    count log; whole body in try/Exception → debug (never raises).
  - Docstring (Mode A): what it replaces, when, the privacy rule, why "" when rolling is off.

Task 2: EDIT voice_typing/daemon.py — call site + refresh branch + _arm resets
  - on_final: INSERT `self._handoff_context_prompt(cleaned)` as the FIRST statement after
    `self._utterance_finalized = (True ...)` and BEFORE `if self._streaming_now():`. Update the
    on_final docstring (one paragraph: seed is recognition-only; replaced on first acceptance).
  - _refresh_context_prompt: replace the 5-line source selection with the 3-way branch
    (accumulator when _seed_handoff_done). Extend its docstring's SOURCE paragraph.
  - _arm: beside `self._rev1_committed = ""` add
    `self._session_accepted = []` and `self._seed_handoff_done = False  # P1.M1.T2.S4 (pending is the seam's)`.

Task 3: EDIT voice_typing/daemon.py — the S3 hook (ONE line)
  - FIND the `self._seed_active = True` assignment inside `_start_fenced` (applied prime branch).
    ADD directly after it: `self._seed_handoff_pending = True  # P1.M1.T2.S4: awaits first accepted final`.
  - Do not change anything else in the seam.

Task 4: EDIT voice_typing/prompt_engine.py — docstrings only
  - Module docstring: add a short "SEED vs ROLLING CONTEXT (§4.8.1)" paragraph — the seed is
    pre-caret editor text installed once by a confirmed prime, used only until the session's
    first accepted final, never mixed into the rolling source; the rolling source is the session's
    accepted finals only; neither is ever logged with content.
  - `rolling_context_prompt` docstring: one sentence naming it as the handoff target.

Task 5: EDIT tests/test_daemon.py — new section (after the T6.S2 prompt tests ~@5270)
  - Helper: `_seeded(cfg=None, *, context_prompt=True, host_cls=_PromptRecordingHost)` building
    the daemon per the idiom, calling `d.start()`, then `d._seed_handoff_pending = True`; return
    (d, fb, rec, be, host).
  - test_seed_handoff_rejected_finals_keep_seed: on_final("you"), on_final("bye") →
    host.prompts == [""] (only the arm-time clear); d._seed_handoff_pending is True; accumulator [].
  - test_seed_handoff_first_accepted_pushes_session_only_rolling: on_final("First one. second") →
    prompts == ["", "second"]; pending False; done True; accumulator == ["First one. second"].
  - test_seed_handoff_is_once_then_refresh_uses_accumulator: first accepted, then
    on_final("Third one") → prompts == ["", "second", "Third one"] (refresh from the accumulator,
    NOT from stream.committed — poke d._stream._committed = "GHOST tail " in between to prove it).
  - test_seed_handoff_with_rolling_disabled_clears_seed: cfg.asr.context_prompt = False →
    prompts == ["", ""] on first acceptance.
  - test_seed_handoff_runs_before_typing_failure: be.type_text raises (monkeypatch the backend) →
    on_final completes; prompts[-1] is the handoff push; pending False.
  - test_seed_handoff_rev1_mode_uses_accumulator: cfg.output.streaming = False →
    prompts == ["", "second"] for on_final("First one. second"); typed unchanged.
  - test_seed_handoff_missing_set_prompt_seam_is_silent: plain _FakeHost path (_make_daemon()),
    set pending, on_final("hello world") → no raise; pending False; done True.
  - test_seed_handoff_does_not_touch_status_feedback_recovery: after handoff,
    status_snapshot()["context_prompt"] label unchanged vs a non-seeded run; fb.finals == [accepted];
    d._session_recovery holds only the accepted final (its existing accessor/attributes).
  - test_seed_handoff_no_text_in_logs (caplog at DEBUG): the seed marker string "SEEDMARK" set via
    d._session_accepted = ["SEEDMARK"] before an accepted final → "SEEDMARK" absent from caplog.text;
    only a "seed handed off" count line is present.
  - test_seed_handoff_resets_next_session: after a handoff, d.start() (fresh arm) →
    d._session_accepted == [] and d._seed_handoff_done is False.
  - test_fenced_seed_arm_marks_handoff_pending (ONLY if S3 landed; else skip with a clear reason):
    drive start_with_seed via the landed seam with a fake prime_prompt returning applied →
    d._seed_handoff_pending is True before any final; a plain arm leaves it False.
  - CONSTRAINTS: reuse _PromptRecordingHost, _make_daemon, _DaemonFakeFeedback, daemon.LatencyLog,
    VoiceTypingConfig, caplog, monkeypatch; no process/CUDA/mic.

Task 6: VALIDATE (below); confirm `git diff --name-only` == the three files. No commit unless asked.
```

### Implementation Patterns & Key Details

```python
# on_final — the inserted line (context shown; everything else byte-identical):
            self._final_pending = False
            self._utterance_finalized = (
                True
            )
            self._handoff_context_prompt(cleaned)   # P1.M1.T2.S4 — BEFORE any typing/commit
            if self._streaming_now():
                ...

# _refresh_context_prompt — the only change:
            if self._seed_handoff_done:                     # P1.M1.T2.S4: accepted-only source
                source = " ".join(self._session_accepted)
            elif self._streaming_now():
                source = self._stream.committed
            else:
                source = self._rev1_committed
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S3 (fenced start seam): sets _seed_active = True on an applied seed arm; this
           task adds the one-line `_seed_handoff_pending = True` beside it. start_with_seed(seed).
UPSTREAM — P1.M1.T2.S2 / S1: host.set_prompt (queue put) and prompt_engine.rolling_context_prompt.
DOWNSTREAM — P1.M1.T4.S4 (native finals before generic output): keep the single call
           `self._handoff_context_prompt(cleaned)` above its native branch / early return, so a
           native delivery failure still hands off. The accumulator is the "native committed input".
DOWNSTREAM — P1.M1.T2.S5 / CLI+CPU verification: a seeded session shows the seed influencing only
           the first accepted utterance.
UNCHANGED: recorder_host.py, streaming.py, textproc.py, feedback.py, session_recovery.py, status
           shape, control-socket protocol, _clear_context_prompt, _disarm, cancel(), drain.
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic fakes only. Run from
> `/home/dustin/projects/voice-typing`. Navigate by symbol — lines shift under S2/S3.

### Level 1: Syntax & static shape

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -c "import ast; [ast.parse(open(f).read()) for f in ('voice_typing/daemon.py','voice_typing/prompt_engine.py')]; print('L1 PASS: parses')"
grep -n '_seed_handoff_pending\|_seed_handoff_done\|_session_accepted\|def _handoff_context_prompt' voice_typing/daemon.py | head -20
grep -c '_handoff_context_prompt(cleaned)' voice_typing/daemon.py      # expect exactly 1
awk '/def on_final/,/def _duck_engage/' voice_typing/daemon.py | grep -n '_handoff_context_prompt(cleaned)\|if self._streaming_now():'   # handoff line number < streaming line number
git diff voice_typing/prompt_engine.py | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' | grep -vE '^[+-]\s*(#|"""|[A-Za-z`(* ].*)$' ; echo "L1 NOTE: prompt_engine diff must be docstring-only (inspect `git diff voice_typing/prompt_engine.py`)"
# Expected: parses; state + method present; exactly one call site; it precedes the typing branches.
```

### Level 2: The handoff tests

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k "seed_handoff or fenced_seed_arm" -v 2>&1 | tail -18
# Expected: all PASSED (fenced_seed_arm may be the only skip if S3 is not landed). Load-bearing:
# rejected-only → prompts == [""] and pending True; first accepted → exactly one push; the GHOST
# tail poke proves the refresh reads the accumulator; config-off → "" push; typing raise does not
# skip; no SEEDMARK in caplog.
```

### Level 3: No regressions

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -2
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_voicectl.py -q 2>&1 | tail -2
# Expected: green. A red in an existing prompt test means the non-seeded path diverged (CRITICAL #8)
# — most likely _seed_handoff_done defaulted True or the refresh branch reordered.
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/daemon.py|voice_typing/prompt_engine.py|tests/test_daemon.py' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS"
git diff --quiet voice_typing/recorder_host.py voice_typing/streaming.py voice_typing/textproc.py voice_typing/feedback.py voice_typing/session_recovery.py voice_typing/ctl.py voice_typing/config.py && echo "L4 PASS: siblings untouched" || echo "L4 NOTE: recorder_host diff is S2's parallel work, not this task's"
git diff --exit-code -- PRD.md plan/009_ef3b49b0fc0d/tasks.json plan/009_ef3b49b0fc0d/prd_snapshot.md .gitignore && echo "L4 PASS: read-only unchanged" || echo "L4 NOTE: orchestrator bookkeeping"
# Expected: diff ⊆ the three files; siblings untouched by this task; read-only unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: parses; three state fields + `_handoff_context_prompt` present; exactly ONE call site, before the typing branches; prompt_engine diff is docstring-only.
- [ ] L2: all seed-handoff tests pass.
- [ ] L3: full daemon suite + control-socket/voicectl suites green.
- [ ] L4: diff == the three files.

### Feature Validation
- [ ] Rejected finals never consume the seed; the first accepted final replaces it exactly once.
- [ ] Replacement is `rolling_context_prompt(accepted finals)` or `""` — never a skip, never the seed.
- [ ] Handoff precedes typing/commit/record; typing failure cannot skip it.
- [ ] The accumulator holds only this session's accepted finals and resets on every arm.
- [ ] Seed text absent from logs/status/feedback/recovery/replies; `_seed_active` never written here.

### Code Quality Validation
- [ ] Mirrors `_refresh_context_prompt` (getattr seam, never-raise, count-only debug log).
- [ ] Mode A docstrings on the new/changed daemon methods and in prompt_engine.
- [ ] No new imports; no blocking calls; no `_lock` on the reader thread.

### Scope Boundary Validation
- [ ] recorder_host/streaming/textproc/feedback/session_recovery/ctl/config untouched.
- [ ] The S3 hook is ONE line; no other seam edits; no S5 focus-start or T3.S4 owner code.
- [ ] PRD.md / tasks.json / prd_snapshot.md / .gitignore not modified.

### Documentation & Deployment
- [ ] prompt_engine + daemon docstrings state the seed-vs-rolling privacy rule.

---

## Anti-Patterns to Avoid

- ❌ Don't hand off from `on_partial`, from a rejected final, from a cancel, or at disarm — acceptance is the only trigger.
- ❌ Don't skip the replacement when the rolling prompt is off — push `""`.
- ❌ Don't source the replacement from `StreamingOutput.committed` (may contain an unaccepted frozen tail; absent on the native path).
- ❌ Don't place the call after the typing branches or inside the `try` around `commit()`/`type_text()`.
- ❌ Don't put the seed string, the accumulator, or dictated text into a new log line, status field, feedback write, or `SessionRecovery`.
- ❌ Don't write `_seed_active`, don't reset `_seed_handoff_pending` in `_arm`, don't re-prime from the handoff.
- ❌ Don't hold `self._lock`, wait on the host, or raise from the handoff (reader thread).
- ❌ Don't edit recorder_host.py / streaming.py / textproc.py, or PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**8.5/10** for one-pass implementation success. Every edit site was read verbatim, the design is a
small, additive, acceptance-point insert plus one source branch, and the non-seeded path is
byte-identical by construction (the existing `["", "second"]` test is the guard). The −1.5 is the
parallel S3 dependency: the one-line hook depends on `_seed_active = True` existing in the landed
seam, and S3's stated "plain arm + channel + no seed ⇒ skip clear" policy looks wrong for a WARM
re-arm after an ordinary rolling session (research §6) — this task stays conservative
(`_seed_active` left True after handoff) and flags it rather than fixing it.
