# PRP — P1.M1.T4.S1: Daemon — gate `_on_partial` on is_listening + stale-partial regression test (BUG-004)

## Goal

**Feature Goal**: Fix bugfix **BUG-004** (Major): `VoiceTypingDaemon._on_partial` (daemon.py ~:1390,
body :1411-1412) routes the host reader thread's partials straight into
`self._stream.on_partial(text)` + `self._latency.note_partial(text)` with **NO listening gate** —
while the sibling `on_final`'s FIRST statement (:1121-1124) is exactly that race guard. RealtimeSTT
emits partials continuously, and `recorder_host._dispatch` relays `'partial'` events ungated (it
gates only `'vad'`), so a partial already computed / in the IPC queue when the user toggles off is
typed into the focused window AFTER the disarm — and because `_disarm` reset the session
(`committed=''`), the stale fragment types case-preserved as a fresh session start. This contradicts
PRD acceptance #4, whose own evidence text in `tests/ACCEPTANCE.md` row 4 (~:35) claims "the
`listening` flag gates BOTH the partial and commit paths" — false against the code until this lands.
The fix: add the same first-line guard on_final has, BEFORE the engine routing AND the latency note
(a stray post-disarm partial must neither type nor count into latency).

**Deliverable** (3 files edited, no new files):
1. `voice_typing/daemon.py` — one guard inserted at the top of `_on_partial` (verbatim below). No
   other change.
2. `tests/test_daemon.py` — one NEW daemon-level regression test (TDD, written FIRST) under a new
   banner at the file's END, using the existing `_make_daemon()` doubles (:684). No existing test
   touched.
3. `tests/ACCEPTANCE.md` — row 4 Evidence text updated to cite the new regression test (Mode A; the
   criterion + Status cells unchanged — the claim is now actually true).

**Success Definition**:
- (a) `d.start(); d._on_partial('hello there')` → backend gains the text; `d.stop(); assert not
  d.is_listening(); d._on_partial('stray words')` → `backend.typed` **UNCHANGED** (this exact repro
  from PRD h3.3 is the new test).
- (b) The guard precedes BOTH `self._stream.on_partial(text)` AND `self._latency.note_partial(text)`.
- (c) The new test is **RED before** the daemon.py edit (TDD) and **GREEN after**.
- (d) `timeout 600 <python> -m pytest tests/test_daemon.py -k "partial or listening" -q` → 0
  failures, plus the new test name passes.
- (e) All other daemon behavior unchanged: `_touch_speech` (the `'speech'` hook) is NOT gated (a
  stray speech event only resets the idle clock / resumes the engine engine-internally — no
  keystrokes; the BUG-001/BUG-002 resume wiring stays intact).
- (f) `git diff --name-only` == `{voice_typing/daemon.py, tests/test_daemon.py, tests/ACCEPTANCE.md}`.

> **VERIFIED DEFECT (this PRP's research):** `_on_partial`'s body is exactly
> `self._stream.on_partial(text); self._latency.note_partial(text)` — no gate (daemon.py :1411-1412,
> read this round). `on_final` gates at :1121-1124. The implementing agent writes the failing test
> first, then inserts the guard below; the test goes red→green.

## User Persona

**Target User**: the end user toggling dictation off (hotkey / `voicectl stop`) immediately after
speaking. RealtimeSTT keeps emitting partials; one can land after the disarm.
**Use Case**: user says a fragment, hits toggle-off, switches to a chat window — a stale partial
from the just-disarmed session types into the chat. After the fix: nothing is ever typed while
toggled off, on either the partial or the commit path (PRD acceptance #4).
**Pain Points Addressed**: BUG-004 — post-disarm keystrokes into whatever window is focused; the
ACCEPTANCE.md row 4 claim being false against the code.

## Why

- **PRD acceptance #4 (h2.2/h3.3) is the spec**: "nothing typed while toggled off (the `listening`
  gates on partial and commit paths are unchanged)". The commit path gates; the partial path does
  not — a plain spec omission, and the PRD h2.5 recommendation says exactly what to do: "Add a
  listening gate to _on_partial (mirror the on_final gate) so stale partials can never type while
  toggled off, then make ACCEPTANCE.md row 4's claim true."
- **The gate belongs at the daemon, not the host.** `recorder_host._dispatch` relays `'partial'`
  ungated (gates only `'vad'`); the engine has no listening awareness. `on_final`'s existing
  first-line guard proves the daemon-level placement — mirror it. (Do NOT touch recorder_host.py.)
- **Why the unit suites missed it.** The Rev 2 tests drive `d._on_partial` only while armed (tests
  at :4601-:4702 all follow `d.start()`); no test drives a partial after `d.stop()`. This task adds
  exactly that regression test.
- **Scope discipline.** T4.S1 owns ONLY the `_on_partial` guard + its daemon test + the ACCEPTANCE
  row 4 evidence text. It does NOT touch streaming.py / test_streaming_* (parallel P1.M1.T3.S1 —
  DISJOINT files), recorder_host.py, `_touch_speech`, on_final, or README (P1.M3.T9's Mode B sweep).

## What

Insert the listening gate as `_on_partial`'s first statement; add one daemon-level TDD regression
test; update ACCEPTANCE.md row 4's evidence sentence.

### Success Criteria

- [ ] daemon.py `_on_partial`: `if not self._listening.is_set(): return` is the first statement,
      before `self._stream.on_partial(text)` and `self._latency.note_partial(text)`.
- [ ] New `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` added under a
      `P1.M1.T4.S1` banner at the END of tests/test_daemon.py (additive; no existing test changed).
- [ ] The new test was run RED against the unedited daemon.py first (TDD), then GREEN after.
- [ ] `_touch_speech` / `on_final` / `_stream.resume()` wiring (BUG-001/BUG-002, complete) untouched.
- [ ] tests/ACCEPTANCE.md row 4 Evidence cites the new test; criterion + Status cells unchanged.
- [ ] `timeout 600 <python> -m pytest tests/test_daemon.py -k "partial or listening" -q` green.
- [ ] `git diff --name-only` == the 3 in-scope files.

## All Needed Context

### Context Completeness Check

_Pass._ The ungated body is quoted verbatim with line numbers (:1411-1412, read this round), the
on_final reference gate is quoted (:1111-1124), the fix block is verbatim, the new test is given
verbatim with its placement convention (the file's Rev 2 streaming section at :4589-:4702 drives
`d._on_partial` via `_make_daemon()` (:684) — the exact pattern mirrored), the RED→GREEN proof is
worked out, and the parallel no-conflict boundary (T3.S1 owns streaming.py + test_streaming_*) is
established. An agent new to this repo can implement from this PRP alone. No CUDA/mic/socket — the
doubles (`_StubRecorder`, `_FakeBackend`, `_DaemonFakeFeedback`, `_ok_probe`) are pure fakes; the
daemon is NEVER run foreground.

### Documentation & References

```yaml
# MUST READ — the verified defect + verbatim fix + the TDD test + the ACCEPTANCE edit (this task's research)
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T4S1/research/bug004_on_partial_gate.md
  why: "§1 quotes the ungated _on_partial body (:1411-1412) + the on_final reference gate (:1119-1124) +
        the upstream context (recorder_host relays 'partial' ungated — daemon-level gate is the fix
        point). §2 is the verbatim guard insertion. §3 is the verbatim TDD test + placement + the
        RED→GREEN proof + the documented side effect (the state.json partial mirror also stops while
        off — intended, mirrors on_final) + why _touch_speech is NOT gated. §4 is the ACCEPTANCE row 4
        old→new evidence text. §5 is the verify commands + scope."
  critical: "The guard must precede BOTH the stream call AND the latency note ('neither type nor count
            into latency' — the contract wording). Do NOT gate _touch_speech — the 'speech' hook only
            resets the idle clock / resumes the engine engine-internally (no keystrokes); gating it
            would break the completed BUG-001/BUG-002 resume wiring."

# THE FILE TO EDIT — voice_typing/daemon.py
- file: voice_typing/daemon.py
  why: "_on_partial (~:1390-1412): docstring then the two ungated calls (:1411-1412). on_final
        (:1119-1124) is the reference gate (read-only). _touch_speech (~:1366-1389) — READ ONLY, its
        self._stream.resume() is the completed BUG-001/BUG-002 wiring; do not touch."
  pattern: "Mirror on_final's first-line guard + comment style. The guard is read-only (outside any
            lock) exactly like on_final's — no locking concerns."
  gotcha: "Insert the guard INSIDE _on_partial only. Do NOT reformat the docstring or touch adjacent
           methods (_request_stop follows). One edit, two lines of code."

# THE TEST FILE — tests/test_daemon.py
- file: tests/test_daemon.py
  why: "_make_daemon() @684 (cfg, _DaemonFakeFeedback, _StubRecorder, _FakeBackend, _ok_probe — the
        :684 construction pattern from the contract). The Rev 2 streaming section @~4589-4702 drives
        d._on_partial with the REAL StreamingOutput on fakes (tests @4601/:4617/:4659/:4671/:4702) —
        the pattern mirrored. File ends @4964 (stranded-tail freeze test) — APPEND the new banner +
        test after it."
  pattern: "Additive banner + one test at EOF (the file's convention). be.typed is a list of typed
            strings; streaming mode may type deltas, so the armed-phase assert uses substring-in-join,
            the stale-phase assert is exact equality (the RED discriminator)."
  critical: "The test must call d._on_partial AFTER d.stop() + assert d.is_listening() is False first
            (the contract's repro sequence). No CUDA, no socket, no foreground daemon (AGENTS.md)."

# THE ACCEPTANCE DOC — tests/ACCEPTANCE.md
- file: tests/ACCEPTANCE.md
  why: "Row 4 (~:35) Evidence cell's first sentence claims the partial gate exists. Update ONLY that
        sentence to cite the new regression test (research §4 has the old→new text). Criterion +
        Status cells UNCHANGED."
  gotcha: "Mode A: this IS the doc update — the claim itself is unchanged (it was always the spec);
           it becomes true. No README edit (P1.M3.T9's Mode B sweep re-verifies)."

# THE SPEC + PARALLEL
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md
  why: "h2.2/h3.3 Issue 3 (BUG-004) — the defect + the exact daemon-level repro this test encodes.
        h2.5 recommendation: 'Add a listening gate to _on_partial (mirror the on_final gate) ... then
        make ACCEPTANCE.md row 4's claim true.'"
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T3S1/PRP.md
  why: "PARALLEL task (in flight): owns voice_typing/streaming.py + tests/test_streaming_commit.py +
        tests/test_streaming_freeze.py. T4.S1 owns daemon.py + test_daemon.py + ACCEPTANCE.md.
        DISJOINT files — no merge conflict. T1.S1/T1.S2/T2.S1/T2.S2 are COMPLETE (their daemon.py/
        test_daemon.py edits are already merged in the tree this PRP was researched against)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py          # _on_partial ~:1390 (body :1411-1412 — UNGATED); on_final :1119-1124 (the reference gate).  ← EDIT (1 guard)
tests/test_daemon.py            # _make_daemon :684; Rev 2 streaming section :4589-4702; EOF :4964.            ← EDIT (additive banner + 1 test)
tests/ACCEPTANCE.md             # row 4 ~:35 — evidence text cites a partial gate that doesn't exist yet.       ← EDIT (1 sentence)
# Parallel T3.S1 (in flight): streaming.py + test_streaming_commit.py + test_streaming_freeze.py — DISJOINT.
```

### Desired Codebase tree with files to be changed

```bash
# (no new files — the 3 edits above only)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TDD: WRITE THE FAILING TEST FIRST. Run the new test against the UNEDITED daemon.py
# (expect RED: the final assert fails — be.typed gains 'stray words'). Then insert the guard → green.
# If it is green before the edit, the assertions are wrong (re-check the repro sequence).

# CRITICAL #2 — THE GUARD PRECEDES BOTH CALLS. 'Neither type nor count into latency' — the return
# must sit BEFORE self._stream.on_partial(text) AND self._latency.note_partial(text). Placing it
# between them still counts the stale partial into the latency log.

# CRITICAL #3 — DO NOT GATE _touch_speech. The 'speech' event hook (~:1366) calls self._stream.resume()
# (the completed BUG-001/BUG-002 wiring) + resets the idle clock. A stray speech event types nothing;
# gating it would break rejected-final recovery + post-cancel live typing. ONLY _on_partial gets the gate.

# CRITICAL #4 — DO NOT TOUCH recorder_host.py or streaming.py. recorder_host relays 'partial' ungated
# by design (the daemon gate covers all callers); streaming.py is the parallel T3.S1's file. Scope =
# the guard + the test + the ACCEPTANCE sentence.

# GOTCHA #5 — SIDE EFFECT IS INTENDED: gating also stops the Feedback partial mirror (state.json's
# 'partial' field) while toggled off, since the mirror lives inside _stream.on_partial. This mirrors
# on_final (no mirror while off) and is more honest status. Note it in the test docstring; do not
# 'compensate' by mirroring outside the gate.

# GOTCHA #6 — USE FULL PATHS + TIMEOUTS (AGENTS.md): invoke .venv/bin/python (or the full uv path
# /home/dustin/.local/bin/uv run) — zsh aliases shadow python3/pip. Wrap pytest in `timeout 600`
# (inner) + the bash-tool timeout above it. NEVER run the daemon foreground; the tests use fakes only.

# GOTCHA #7 — PYTEST ONLY (no ruff/mypy in this project). Validation = pytest + grep. The template's
# ruff/mypy L1 lines are N/A here.

# GOTCHA #8 — THE ARMED-PHASE ASSERT USES SUBSTRING-IN-JOIN. Streaming mode types deltas ('hello',
# ' there'), so assert `"hello there" in "".join(be.typed)` rather than exact membership. The
# STALE-phase assert is exact (`be.typed == before`) — that is the RED discriminator.

# GOTCHA #9 — tests/ACCEPTANCE.md: EDIT ONLY THE ROW-4 EVIDENCE SENTENCE (research §4 old→new). The
# criterion + Status cells are unchanged; other rows untouched. README is P1.M3.T9's (Mode B).
```

## Implementation Blueprint

### Data models and structure

None. One two-line guard + one additive test + one doc sentence.

### Implementation Tasks (ordered by dependencies — TDD: test FIRST, then the fix)

```yaml
Task 1: ADD the failing test FIRST (TDD red) — tests/test_daemon.py
  - PLACE: a new banner + one test at the file's END (after the stranded-tail freeze test, EOF ~:4964).
  - ADD (verbatim; `_make_daemon` is module-level @684 — no new imports):
        # ===========================================================================
        # P1.M1.T4.S1 — _on_partial listening gate (BUG-004): stale post-disarm partials
        # (on_final gates its first line (the race guard); _on_partial did NOT — a partial
        #  already in the IPC queue when the user toggles off typed AFTER the disarm. The
        #  gate also stops the state.json partial mirror + the latency count while off.)
        # ===========================================================================
        def test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing():
            """A stray post-disarm partial neither types nor counts into latency (BUG-004).

            Daemon-level repro (PRD h2.2/h3.3): arm, a partial types through the engine; stop()
            clears the listening flag; a partial already computed/in the IPC queue arrives AFTER
            the disarm — it must NOT reach the backend (case-preserved fresh-session text was
            typed into the focused window before the gate) and must NOT reach the latency log.
            Mirrors on_final's first-line race guard (daemon.py on_final GATE).
            """
            d, _fb, _rec, be = _make_daemon()
            d.start()
            assert d.is_listening() is True
            d._on_partial("hello there")            # armed: routed through the engine
            assert "hello there" in "".join(be.typed)
            d.stop()
            assert d.is_listening() is False
            before = list(be.typed)
            d._on_partial("stray words")            # stale partial AFTER the disarm
            assert be.typed == before, f"stale partial typed while toggled off: {be.typed!r}"
  - RUN (confirm RED before the fix):
      cd /home/dustin/projects/voice-typing
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "stale_partial_after_stop" -q
  - EXPECTED: the test FAILS — be.typed gained 'stray words' (the bug demonstrated). If it PASSES,
    the assertions are wrong (Gotcha #1/#8) — re-check the sequence before proceeding.

Task 2: EDIT voice_typing/daemon.py — insert the gate in _on_partial
  - FIND _on_partial's body (~:1411-1412). Current:
        self._stream.on_partial(text)
        self._latency.note_partial(text)
  - EDIT (insert the guard BEFORE both calls; wrap style may match on_final's or be plain — the
    contract is first-statement placement before BOTH calls):
      OLD:
        self._stream.on_partial(text)
        self._latency.note_partial(text)
      NEW:
        if (
            not self._listening.is_set()
        ):  # GATE: race guard (BUG-004 / P1.M1.T4.S1) — a stray
            return  #   post-disarm partial must neither type nor count into latency
        self._stream.on_partial(text)
        self._latency.note_partial(text)
  - DO NOT: touch the docstring's substance (optionally note the gate in it), _touch_speech,
    on_final, _request_stop, or any other method (Gotcha #3/#4).

Task 3: VERIFY — TDD green + the filtered suite + the full daemon suite
  - RUN:
      cd /home/dustin/projects/voice-typing
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "stale_partial_after_stop" -q
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -k "partial or listening" -q
      timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -3
  - EXPECTED: the new test PASSES; the filtered run is green (the contract's verify command); the
    full daemon suite is green (no regression — esp. the Rev 2 streaming section :4589-4702 and the
    BUG-001/002 resume tests, which all drive _on_partial while ARMED and are unaffected by the gate).

Task 4: EDIT tests/ACCEPTANCE.md row 4 (~:35) — Mode A evidence sync
  - REPLACE the Evidence cell's first sentence (research §4):
      OLD: Disarm gate unchanged by Rev 2: the `listening` flag gates BOTH the partial and commit paths —
           COMPLIANT + mocked **LIVE** (193 daemon tests).
      NEW: Disarm gate: the `listening` flag gates BOTH the partial and commit paths — the commit gate is
           on_final's first line; the partial gate is `_on_partial`'s first line (BUG-004 /
           P1.M1.T4.S1), pinned by `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing`
           (mocked **LIVE** in tests/test_daemon.py).
  - PRESERVE: the criterion cell, the Status cell, and the rest of the Evidence cell (Rev 2 streaming
    typing evidence etc.). No other row changes (Gotcha #9).

Task 5: VALIDATE — the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T4.S1: _on_partial now gates on is_listening (BUG-004) — stale post-disarm
  partials neither type nor count into latency; daemon-level regression test added (TDD red→green);
  ACCEPTANCE row 4 evidence now cites it."
```

### Implementation Patterns & Key Details

```python
# PATTERN — mirror the existing race guard. on_final (:1119-1124) reads the Event OUTSIDE any lock
# (read-only, thread-safe) and returns immediately. _on_partial gets the identical first statement:
if not self._listening.is_set():   # GATE: race guard (BUG-004)
    return                          #   stray post-disarm partial: neither type nor count
self._stream.on_partial(text)
self._latency.note_partial(text)

# WHY THE DAEMON, NOT THE HOST: recorder_host._dispatch relays 'partial' ungated (gates only 'vad');
# the engine has no listening awareness. on_final's placement proves the pattern — one gate at the
# daemon entry covers every caller. _touch_speech stays ungated (its resume() is engine-internal, no
# keystrokes — the completed BUG-001/BUG-002 wiring).
```

### Integration Points

```yaml
DELTA ACCEPTANCE (PRD acceptance #4 / h2.2 Issue 3):
  - The listening flag now gates BOTH paths; ACCEPTANCE row 4's claim becomes true and cites the
    regression test. The PRD h2.5 recommendation ("Add a listening gate to _on_partial ... then make
    ACCEPTANCE.md row 4's claim true") is fully discharged by this subtask.

PARALLEL — P1.M1.T3.S1 (frozen-commit trailing space, in flight):
  - T3.S1 owns voice_typing/streaming.py + tests/test_streaming_commit.py + tests/test_streaming_freeze.py.
    T4.S1 owns voice_typing/daemon.py + tests/test_daemon.py + tests/ACCEPTANCE.md. DISJOINT — clean merge.

DOWNSTREAM:
  - P1.M3.T9.S2 (ACCEPTANCE rows 4/11/12 refresh, Mode B) re-verifies this row after all bugfixes land —
    this task's evidence citation is the row-4 foundation it will sweep.

NO INTERFACE / BEHAVIOR CHANGES BEYOND THE GATE:
  - on_final, _touch_speech, _request_stop, recorder_host, streaming.py: UNCHANGED. Armed-phase
    partial routing (deltas, mirrors, latency) is byte-identical; only the toggled-off path changes.
```

## Validation Loop

> Full paths (zsh aliases shadow python3/pip); inner `timeout` per AGENTS.md Rule 1 on every pytest
> invocation + the bash-tool timeout above it. pytest only (no ruff/mypy). All tests use fakes — no
> CUDA, no socket, no foreground daemon.

### Level 1: The guard is in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- _on_partial body: the gate precedes BOTH calls ---"
sed -n '/def _on_partial/,/note_partial/p' voice_typing/daemon.py
echo "--- py_compile ---"
.venv/bin/python -m py_compile voice_typing/daemon.py && echo "L1 PASS: compiles"
# Expected: the `if not self._listening.is_set(): return` sits BEFORE self._stream.on_partial(text)
# AND self._latency.note_partial(text). No ruff/mypy (N/A here).
```

### Level 2: TDD red→green + the filtered + full daemon suites

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the new test (GREEN after Task 2; was RED before per Task 1) ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -k "stale_partial_after_stop" -q
echo "--- the contract's filter ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -k "partial or listening" -q 2>&1 | tail -3
echo "--- full daemon suite (no regression) ---"
timeout 600 "$PY" -m pytest tests/test_daemon.py -q 2>&1 | tail -3
# Expected: all green (record the pass counts).
```

### Level 3: The regression is dead (empirical) + ACCEPTANCE row 4 truthful

```bash
cd /home/dustin/projects/voice-typing
echo "--- empirical: a post-stop partial types nothing (doubles, no CUDA) ---"
timeout 120 .venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "tests")
from test_daemon import _make_daemon
d, _fb, _rec, be = _make_daemon()
d.start(); d._on_partial("hello there"); d.stop()
assert not d.is_listening()
before = list(be.typed)
d._on_partial("stray words")
assert be.typed == before, f"BUG still present: {be.typed!r}"
print("L3 PASS: stale post-disarm partial typed nothing")
PY
echo "--- ACCEPTANCE row 4 cites the new test ---"
grep -n "stale_partial_after_stop" tests/ACCEPTANCE.md
# Expected: the empirical probe passes; row 4's evidence names the regression test.
```

### Level 4: Scope guards — only the 3 in-scope files changed

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only
# Expected: exactly voice_typing/daemon.py, tests/test_daemon.py, tests/ACCEPTANCE.md
git diff --exit-code -- voice_typing/streaming.py voice_typing/recorder_host.py tests/test_streaming_commit.py tests/test_streaming_freeze.py README.md PRD.md && echo "L4 PASS: parallel/read-only files untouched"
git diff voice_typing/daemon.py | grep -E '^[+-]' | grep -vE '^[+-]{3}|_listening|return|GATE|stray|partial|note_partial|on_partial' || echo "L4 PASS: only gate lines changed in daemon.py"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: the guard precedes BOTH `_stream.on_partial` and `_latency.note_partial`; daemon.py compiles.
- [ ] L2: new test GREEN (RED first per Task 1); `-k "partial or listening"` green; full test_daemon.py green.
- [ ] L3: the empirical post-stop partial probe passes; ACCEPTANCE row 4 cites the new test.
- [ ] L4: exactly the 3 in-scope files in `git diff --name-only`; parallel/read-only files untouched.

### Feature Validation
- [ ] The PRD h3.3 repro (start → partial types → stop → stray partial) leaves backend.typed unchanged.
- [ ] Armed-phase partial routing (deltas + mirrors + latency) unchanged.
- [ ] `_touch_speech` / resume wiring (BUG-001/BUG-002) untouched and their tests still green.
- [ ] ACCEPTANCE row 4: claim unchanged, evidence now true + cited.

### Code Quality / Scope Validation
- [ ] Test is additive (new banner at EOF; no existing test modified).
- [ ] Mirror of on_final's guard style; no new patterns invented.
- [ ] No recorder_host.py / streaming.py / README edits (Gotcha #4/#9).

### Documentation & Deployment
- [ ] [Mode A] ACCEPTANCE row 4 evidence updated; README left to P1.M3.T9.
- [ ] No config/env changes.

---

## Anti-Patterns to Avoid

- ❌ Don't write the fix before the failing test — Task 1's RED run is the proof the test discriminates (Gotcha #1).
- ❌ Don't place the guard after `self._stream.on_partial(text)` or between the two calls — the stale partial must neither TYPE nor COUNT into latency (Gotcha #2).
- ❌ Don't gate `_touch_speech` or remove its `resume()` — that's the completed BUG-001/BUG-002 wiring; a stray speech event types nothing (Gotcha #3).
- ❌ Don't edit recorder_host.py or streaming.py — the daemon gate covers all callers; streaming.py is the parallel T3.S1's file (Gotcha #4).
- ❌ Don't "compensate" for the stopped partial mirror while toggled off — the side effect is intended (mirrors on_final; Gotcha #5).
- ❌ Don't run pytest without `timeout 600` or with bare `python`/`uv` (AGENTS.md Rule 1 + zsh aliases — Gotcha #6).
- ❌ Don't invent ruff/mypy gates (Gotcha #7).
- ❌ Don't loosen the stale-phase assert to substring — exact `be.typed == before` is the RED discriminator (Gotcha #8).
- ❌ Don't rewrite ACCEPTANCE row 4's criterion/Status or other rows — one evidence sentence only (Gotcha #9).

---

## Confidence Score

**9.5/10** for one-pass implementation success. The defect is verified in source this round (the ungated body at :1411-1412; the on_final reference gate at :1119-1124), the fix and the test are given verbatim against the live tree, the RED→GREEN proof is worked out (the current code demonstrably types the stray partial), the test placement and doubles mirror the file's own Rev 2 section (:4589-4702 via `_make_daemon()` @684), and the parallel T3.S1 owns fully disjoint files. The −0.5 residual is the small chance the armed-phase delta typing makes the substring assert environment-sensitive (covered by the join trick, Gotcha #8) or a wrap-style mismatch in the inserted guard (cosmetic; the L1 sed catches it). No CUDA, no socket, no foreground daemon.
