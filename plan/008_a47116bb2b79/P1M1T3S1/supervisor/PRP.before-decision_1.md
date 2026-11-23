# PRP — P1.M1.T3.S1: Replay a sustained-Backspace hold as a regression test + audit trace (D3.2)

## Goal

**Feature Goal**: Close the coverage half of the **D3.2 cancel auto-repeat audit**: no test anywhere replays a sustained-Backspace **hold** — `press(1) + repeats(2)×R + release(0)` — through the daemon's **real wired seams** (listener pump → `_on_cancel_backspace` → `cancel()`) while **armed with a tail in flight**. Add that hold-trace regression test, asserting: (a) exactly **ONE** cancel fires (one compensation burst, one host cancel); (b) the autorepeats **never re-latch or re-stamp the cancel-suppression window** (`_cancel_suppress_since` bit-identical across a second pure-repeat burst); (c) the release is inert. The test docstring carries the **Mode A audit note**: the residual unobservable-deletion window (OS autorepeat deleting real chars the daemon cannot observe during the paced burst) with its bound — the written audit finding S2 (P1.M1.T3.S2) consumes to decide mitigation vs acceptance.

**Deliverable** (1 test file edited, no source change):
1. `tests/test_key_listener.py` — one new banner section at the END: local `_HoldStream`/`_HoldHost` doubles + `test_sustained_backspace_hold_fires_one_cancel_and_never_restamps()` (verbatim body in the Blueprint; **probe-validated live** — the exact scenario was executed as a throwaway probe and passed).

**Success Definition**:
- (a) The test drives `[BS_PRESS] + [BS_REPEAT]*R + [BS_RELEASE, SYN]` through `_pump_events` with the daemon's REAL wired callbacks (`kl.cancel_cb == d._on_cancel_backspace`, `kl._is_active`), on a `_wire_daemon()` daemon that is armed (`_listening.set()`), has a pending tail (`_stream` with `pending_tail_len()==8`), text in flight, and a host.
- (b) Assertions (all probe-verified): `be.calls == [("bs", 7)]` (exactly ONE compensation, n=8−1; repeats+release produce NOTHING); `d._host.cancel_calls == 1`; `d._cancel_suppress_final is True` and `_cancel_suppress_since` not None; `d._stream.reset_calls == 1` and tail now 0; then a SECOND pure-repeat burst leaves `_cancel_suppress_since` **bit-identical**, host still 1, backend unchanged.
- (c) The docstring documents the residual window: total deleted = `n+1+R` vs `n+1` believed (belief-desync); bound `R ≈ repeat_rate × burst_duration` ≈ ≤4–5 chars worst case (30 cps autorepeat × ≤150 ms paced burst on the D3.1 socket path); post-burst repeats are plain user edits (uncompensable by design); S2 owns mitigate-or-record.
- (d) `timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q` → **0 failures** (the suite this file owns). The daemon cancel suite is a **before/after no-regression comparison, not a green gate** — at this PRP's research HEAD, `tests/test_daemon.py` carries **21 pre-existing legacy-separator reds** (full file: 21 failed / 211 passed; e.g. `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` expects the OLD two-call commit shape `['fresh sentence', ' ']` vs the current one-call batched `'fresh sentence '` — the G1 baseline Part A's documented class, already slated for reconciliation). Proven NOT attributable to this task: the reds reproduce in `test_daemon.py`-only runs (this task's test lives in a different file and adds zero source changes). The implementer records the `-k cancel` failure LIST before and after — it must be IDENTICAL.
- (e) `git diff --name-only` == `tests/test_key_listener.py` (ZERO source change — current behavior is correct per design; this task PINS it).

## User Persona

**Target User**: the maintainer (and S2's implementer) who must reason about whether the Backspace-cancel compensation is safe under a held key. **Use Case**: a future change to `parse_key_event` (e.g., someone "fixing" the value≠1 filter to observe autorepeats) would silently re-fire cancels per repeat — re-stamping the suppression window and re-calling `host.cancel()`. This test turns that red, forcing the change to be deliberate. **Pain Points Addressed**: the D3.2 audit found the mechanism but nothing pinned it; the docstring bound is the written finding S2 consumes.

## Why

- **PRD §8 names the defect**: "Cancel compensation assumes one physical Backspace = one character (auto-repeat violates it) → under-compensation manufactures belief-desync." The audit (baseline Part C) traced the exact lines; the remaining work is to (1) pin the intended one-cancel contract with a regression test and (2) record the residual window with its bound. This subtask does both; mitigation is explicitly S2's.
- **The existing coverage tests the filter in isolation, not the hold at the seam.** Parse-level (`:61-65`) and pump-level-with-spies (`:218-228`) tests drop value-2 events, and the daemon cancel suite (`test_daemon.py:4467+`) calls `d.cancel()` directly — no test replays a hold through the listener→daemon wiring with a tail in flight, where a regression would actually bite (re-fired cancels re-stamp the window and re-abort the host).
- **The re-stamp detector is strong and cheap.** `cancel()` stamps `_cancel_suppress_since = time.monotonic()` per press (daemon.py:1789-1791, "refreshed per press") — a re-fired cancel provably changes the float AND re-calls `host.cancel()` (the `_text_in_flight` gate stays satisfied). Both are asserted bit-exact in the probe.
- **Lowest-risk outcome.** No source change — the one-cancel filter is the DESIGN (module docstring: "A held Backspace therefore fires exactly ONE cancel (the press), never autorepeat storms"). The deliverable is the pin + the audit note.
- **Scope discipline.** One test file; no engine/daemon/listener edits; no mitigation (S2); no journal-scraping (parallel T2.S3 owns the typing-backends noise guard — disjoint file).

## What

Add one hold-trace regression test + two local doubles to `tests/test_key_listener.py`. Nothing else.

### Success Criteria

- [ ] `tests/test_key_listener.py` gains the banner section + `_HoldStream`/`_HoldHost` + `test_sustained_backspace_hold_fires_one_cancel_and_never_restamps`.
- [ ] The test uses the daemon's REAL wired callbacks (no monkeypatched `cancel`), armed + tail(8) in flight + `_text_in_flight` set + host installed.
- [ ] Hold `R=6`: `be.calls == [("bs", 7)]`; host cancels == 1; window latched (`_cancel_suppress_final is True`, stamp not None); stream reset once, tail 0.
- [ ] Second pure-repeat burst: stamp bit-identical; host still 1; backend unchanged.
- [ ] The docstring documents the residual window + bound + "S2 owns mitigate-or-record" (the audit finding).
- [ ] `timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q` → 0 failures; `tests/test_daemon.py -k cancel` failure list IDENTICAL before vs after (pre-existing legacy-separator reds unchanged — see Success Definition (d)).
- [ ] `git diff --name-only` == `tests/test_key_listener.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The test body is given **verbatim and was executed as a live probe against the current tree — it passed** (output recorded in the research note §3). The harness (`_wire_daemon`, `_WireBackend`), the pre-existing event tuples (`:190-193`), the exact daemon attributes asserted (`_cancel_suppress_final/_cancel_suppress_since/_host/_stream`), the wiring chain (pump → `kl.cancel_cb` → `_on_cancel_backspace` → `cancel()`), and the residual-window bound are all line-verified. Pure-Python, no devices, no CUDA, no threads.

### Documentation & References

```yaml
# MUST READ — the probe-validated test body + the mechanism + the audit note (this task's own research)
- docfile: plan/008_a47116bb2b79/P1M1T3S1/research/d32_hold_trace_probe.md
  why: "§1 the mechanism with exact lines (filter :81; wiring daemon.py:799-805; compensation :1779;
        window latch+stamp :1788-1791). §2 the coverage gap (what :61-65/:218-228/:4467+ each cover and
        why none is a hold trace). §3 THE PROBE — the exact scenario executed live, PASSED, with its
        output — the test body transcribes it 1:1. §4 the audit-note text for the docstring. §5 scope."
  critical: "§3 is load-bearing: every assertion in the Blueprint was validated against the live tree
            (including that cancel()'s trailing status_snapshot() works with _WireFeedback). If an
            assertion fails at implementation time, the tree drifted — investigate, don't weaken."

# THE AUDIT (the D3.2 closure this task executes)
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: "PART C is the complete audit: the filter, the wiring, the hold walkthrough (press → ONE cancel →
        paced burst; repeats → invisible but OS deletes REAL chars; release → nothing), the belief-desync
        arithmetic (n+1+R vs n+1), the existing-coverage grep, and the note that a SEPARATE press
        re-stamps the window (:1789-1791) while repeats never do."
  critical: "The docstring's residual-window bound comes from here: repeats landing during the paced
            burst interleave; R ≈ repeat_rate × burst_duration (~30 cps × ≤150 ms → ≤4-5 chars worst
            case on the D3.1 socket path's ~12 ms/char); post-burst repeats are plain user edits."

# THE TEST FILE (the only file edited)
- file: tests/test_key_listener.py
  why: "Harness to reuse: _wire_daemon() (:379-389 — real daemon ctor + _WireBackend + default config
        with the listener WIRED), the tuples _BS_PRESS/_BS_RELEASE/_BS_REPEAT/_SYN (:190-193), _pump_events
        (imported :29), and the wiring-section pattern (test_listener_routes_events_into_daemon_seams :427
        — the closest sibling, but it monkeypatches cancel; THIS test drives the REAL cancel)."
  pattern: "New banner section at the END of the file (the file's convention). Local _HoldStream/
            _HoldHost doubles (8 lines each — mirror test_daemon.py's _FakeStream: pending_tail_len()/
            reset_after_cancel(), and a host with cancel() counting). Do NOT monkeypatch d.cancel."
  gotcha: "kl._is_active is the daemon's real gate (reads _listening). _text_in_flight MUST be set and a
           host installed or cancel() skips the window latch entirely (daemon.py:1784 guard)."

# THE MECHANISM SITES (read-only reference — do NOT edit)
- file: voice_typing/key_listener.py
  why: "parse_key_event :74-88 (the value!=1 filter at :81); _pump_events :199-225 (the tested seam —
        the same free function the device threads run); module docstring :18-19 states the one-cancel
        contract this test pins."
- file: voice_typing/daemon.py
  why: "cancel() :1756-1795 — compensation n=max(tail_len-1,0) at :1779; the window latch+stamp at
        :1788-1791 ('refreshed per press'); _pending_tail_len :1554-1568; _reset_stream_after_cancel
        :1569-1580; _on_cancel_backspace :1633-1643."

# THE SIBLING CANCEL SUITE (pattern reference; NOT edited)
- file: tests/test_daemon.py
  why: ":4454-4464 _make_cancel_daemon + _FakeStream(tail_len=8) — the compensation-arithmetic pins this
        test complements (they call d.cancel() directly; the hold trace adds the listener-seam replay)."

# THE SIBLING (parallel) — disjoint files
- docfile: plan/008_a47116bb2b79/P1M1T2S3/PRP.md
  why: "T2.S3 (parallel, implementing) edits ONLY tests/test_typing_backends.py (journal-noise guard).
        DISJOINT from tests/test_key_listener.py. No conflict."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/key_listener.py        # filter :81, pump :199-225 — READ-ONLY here (design is correct).
voice_typing/daemon.py              # cancel() :1756-1795, window :1788-1791 — READ-ONLY here.
tests/test_key_listener.py          # _wire_daemon :379, tuples :190-193, wiring section :334-450.   ← EDIT (banner section at END)
tests/test_daemon.py                # cancel suite :4454-4560 (pattern ref; NOT edited).
plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md   # PART C — the audit (input).
# Parallel T2.S3: tests/test_typing_backends.py — DISJOINT.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_key_listener.py   # ADD: banner section "D3.2 hold trace (P1.M1.T3.S1)" + _HoldStream + _HoldHost +
#                           test_sustained_backspace_hold_fires_one_cancel_and_never_restamps (probe-validated body).
# NO other files. ZERO source change (the deliverable is the pin + the audit note in the docstring).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE TEST BODY IS PROBE-VALIDATED; TRANSCRIBE, DON'T IMPROVISE. Every assertion (incl. the
# bit-identical re-stamp check and that cancel()'s trailing status_snapshot() survives _WireFeedback) ran
# green against the live tree (research §3). If something fails, the tree drifted — investigate first.

# CRITICAL #1b — test_daemon.py HAS PRE-EXISTING REDS AT HEAD — DO NOT "FIX" THEM HERE. The full file
# runs 21 failed / 211 passed at this PRP's research HEAD (the G1 baseline Part A legacy-separator class:
# tests expect the old two-call 'text'+' ' commit shape vs the current one-call batched 'text ' commit).
# They reproduce WITHOUT this task's change (test_daemon.py-only runs fail identically). The gate is a
# before/after FAILURE-LIST comparison (identical), NOT green. Fixing them is out of scope (the G1
# reconciliation work owns it); masking or skipping them is forbidden.

# CRITICAL #2 — _text_in_flight + HOST ARE REQUIRED FOR THE WINDOW. cancel() latches/stamps ONLY under
# `if self._text_in_flight.is_set() and self._host is not None:` (daemon.py:1784). Without both, the
# stamp is None and the re-stamp assertion is vacuous. Set the Event AND install _HoldHost.

# CRITICAL #3 — USE THE REAL cancel, NOT A SPY. The point is the seam replay: pump → kl.cancel_cb
# (== d._on_cancel_backspace) → the REAL cancel(). Monkeypatching cancel (as sibling :427 does) would
# test nothing about the window. Count cancels via side effects: backend ("bs", n), host.cancel_calls.

# CRITICAL #4 — THE RE-STAMP DETECTOR. cancel() stamps time.monotonic() per PRESS; repeats never reach
# it. Assert `_cancel_suppress_since == stamp1` after a SECOND pure-repeat burst (bit-identical — a
# re-fired cancel provably re-stamps AND re-calls host.cancel; both asserted). This is exactly the
# property a future value==2 "fix" would break — the test makes that deliberate and visible.

# GOTCHA #5 — THE DOCSTRING IS THE AUDIT FINDING (Mode A). It must state: total deleted = n+1+R vs n+1
# believed; bound R ≈ repeat_rate × burst_duration (~30 cps × ≤150 ms → ≤4-5 chars during the burst,
# ~12 ms/char pacing on the D3.1 socket path); post-burst repeats are plain user edits (uncompensable
# by design); S2 (P1.M1.T3.S2) owns mitigate-or-record. No separate doc file.

# GOTCHA #6 — FULL PATHS + timeout. timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q.
# pytest only (no ruff/mypy configured). Never bare python/pytest/uv.

# GOTCHA #7 — NO source edits, NO mitigation, NO journal-scraping, NO daemon/test_daemon.py edits (the
# cancel suite is the reference, not the target), NO test_typing_backends.py edits (parallel T2.S3).
```

## Implementation Blueprint

### Data models and structure

None — a pure test addition. The two local doubles (`_HoldStream`, `_HoldHost`) are 8-line test fixtures mirroring `test_daemon.py`'s `_FakeStream` shape (`pending_tail_len()` / `reset_after_cancel()`) plus a host whose `cancel()` counts.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD the banner section + doubles + the hold-trace test — tests/test_key_listener.py, at END of file
  - BANNER:
      # ---------------------------------------------------------------------------
      # D3.2 hold trace (P1.M1.T3.S1): a sustained Backspace hold through the REAL
      # listener→daemon seams — press(1) + repeats(2)×R + release(0), armed, tail in flight.
      # ---------------------------------------------------------------------------
  - DOUBLES (local to the section):
      class _HoldStream:
          """Pending-tail double: 8 chars; reset_after_cancel() zeroes + counts (mirrors _FakeStream)."""
          _len = 8
          reset_calls = 0
          def pending_tail_len(self) -> int:
              return self._len
          def reset_after_cancel(self) -> None:
              self.reset_calls += 1
              self._len = 0

      class _HoldHost:
          """Host double: cancel() counts (the in-flight-utterance discard seam)."""
          def __init__(self) -> None:
              self.cancel_calls = 0
          def cancel(self) -> None:
              self.cancel_calls += 1
  - THE TEST (verbatim — probe-validated, research §3):
      def test_sustained_backspace_hold_fires_one_cancel_and_never_restamps():
          """D3.2 (P1.M1.T3.S1): a HELD Backspace through the real seams — exactly ONE cancel; the
          autorepeats never re-latch/re-stamp the cancel-suppression window; the release is inert.

          AUDIT NOTE (D3.2 residual window — the written finding for S2 / P1.M1.T3.S2):
          the daemon sees ONLY the press (key_listener.py:81 drops value!=1), but the OS autorepeat
          keeps deleting REAL on-screen characters. Repeats landing while the daemon's paced
          press_backspace(n) burst runs (~12 ms/char on the D3.1 socket path; ≤150 ms for ~80 chars)
          interleave with it: total deleted = n+1+R vs n+1 believed → belief-desync of R chars.
          BOUND: R ≈ repeat_rate × burst_duration — at a typical ~30 cps autorepeat, R ≤ ~4-5 chars
          worst case during the burst; repeats after the burst delete committed/user text with the
          accounting already zeroed (plain user edits — uncompensable by design). Mitigation vs
          acceptance is S2's decision; this test pins the CURRENT contract so any change (e.g.
          observing value==2 to compensate holds) is a deliberate, visible red.
          """
          d, _fb = _wire_daemon()
          be = d._backend
          d._stream = _HoldStream()
          d._host = _HoldHost()
          d._listening.set()          # armed (the listener's is_active gate reads this Event)
          d._text_in_flight.set()     # required or cancel() skips the suppression-window latch
          kl = d._key_listener
          assert kl.cancel_cb == d._on_cancel_backspace   # the REAL seam, no monkeypatching

          R = 6   # a realistic short hold; > the ≤5 worst-case during-burst repeats
          _pump_events(
              [_BS_PRESS] + [_BS_REPEAT] * R + [_BS_RELEASE, _SYN],
              cancel_cb=kl.cancel_cb,
              other_key_cb=kl.other_key_cb,
              is_active=kl._is_active,
          )
          # Exactly ONE cancel: one compensation batch (n = 8-1), one host discard, window latched once.
          assert be.calls == [("bs", 7)], be.calls
          assert d._host.cancel_calls == 1
          assert d._cancel_suppress_final is True
          stamp = d._cancel_suppress_since
          assert stamp is not None
          assert d._stream.reset_calls == 1 and d._stream._len == 0

          # Repeats NEVER re-latch/re-stamp: a second pure-repeat burst changes nothing. (A re-fired
          # cancel would re-stamp time.monotonic() — a different float — AND re-call host.cancel().)
          _pump_events(
              [_BS_REPEAT] * R,
              cancel_cb=kl.cancel_cb,
              other_key_cb=kl.other_key_cb,
              is_active=kl._is_active,
          )
          assert d._cancel_suppress_since == stamp, "autorepeats must never re-stamp the window"
          assert d._host.cancel_calls == 1 and be.calls == [("bs", 7)]
  - DO NOT: monkeypatch d.cancel (CRITICAL #3); weaken an assertion without re-probing (CRITICAL #1);
    add source changes, mitigation, or other files.

Task 2: VALIDATE (L1–L3). If committing: "P1.M1.T3.S1: D3.2 — sustained-Backspace hold regression test
  (one cancel, no suppression-window re-stamp) + residual-desync audit note in the docstring".
```

### Implementation Patterns & Key Details

```python
# THE SEAM REPLAY (the whole point — no spies on cancel itself):
_pump_events([BS_PRESS] + [BS_REPEAT]*R + [BS_RELEASE, SYN],
             cancel_cb=kl.cancel_cb,        # == d._on_cancel_backspace (asserted)
             other_key_cb=kl.other_key_cb,
             is_active=kl._is_active)       # reads d._listening — the REAL gate

# THE RE-STAMP DETECTOR (CRITICAL #4): a re-fired cancel re-stamps time.monotonic() (different float)
# AND re-calls host.cancel() (_text_in_flight stays set). Assert BOTH unchanged after a second
# pure-repeat burst — bit-identical, not approximately.
assert d._cancel_suppress_since == stamp and d._host.cancel_calls == 1
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T3.S2 (S2: mitigate or record the residual window):
  - S2 consumes the audit note in this test's docstring (the bound + the by-design post-burst
    semantics) as its input. If S2 lands a mitigation that changes the one-cancel contract (e.g.
    observing holds), THIS test is the deliberate red that flags the contract change.
DOWNSTREAM — P1.M1.T4 (D3.3 suppression-window latch chaining): the re-stamp pin here is per-PRESS
  re-stamping being confined to real presses; T4.S2's incident replay complements it.
PARALLEL — P1.M1.T2.S3 (implementing): tests/test_typing_backends.py ONLY — DISJOINT.
UNCHANGED: key_listener.py, daemon.py, streaming.py, test_daemon.py, every other file. Zero source diff.
```

## Validation Loop

### Level 1: The test exists and is well-formed

```bash
cd /home/dustin/projects/voice-typing
grep -n 'def test_sustained_backspace_hold_fires_one_cancel_and_never_restamps' tests/test_key_listener.py
grep -c 'class _HoldStream\|class _HoldHost' tests/test_key_listener.py   # 2
.venv/bin/python -m py_compile tests/test_key_listener.py && echo "compiles"
```

### Level 2: The suite is green (no regression)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q 2>&1 | tail -3
# Expected: 0 failures (all 33 incl. the new test).
# NO-REGRESSION COMPARISON (not a green gate): the daemon cancel subset carries PRE-EXISTING
# legacy-separator reds at HEAD (21 failed / 211 passed full-file at research time — the G1
# baseline Part A class; e.g. test_cancel_suppression_drops_racing_final_and_clears_on_sentinel
# expects the old ['fresh sentence', ' '] two-call commit vs the current 'fresh sentence ' batch).
# Record the failure list BEFORE applying this task's edit and AFTER — it must be IDENTICAL
# (this task cannot affect it: different file, zero source changes — but verify, don't assume):
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k cancel 2>&1 | grep '^FAILED' | sort
```

### Level 3: The behavioral proof (the new test, isolated)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_key_listener.py -q -k sustained -v 2>&1 | tail -4
# Expected: 1 passed. (If it fails: the tree drifted from the probe — investigate per CRITICAL #1.)
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only   # == tests/test_key_listener.py
git diff --exit-code -- voice_typing/ tests/test_daemon.py tests/test_typing_backends.py && echo "L4 PASS: zero source/out-of-scope changes" || echo "L4 FAIL"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 test + doubles present, compiles; L2 key-listener suite green + the daemon cancel failure list identical before/after; L3 the new test passes isolated; L4 only `tests/test_key_listener.py` changed.

### Feature Validation
- [ ] Hold (press+6 repeats+release) through the REAL wired seams: exactly one `("bs", 7)`, one host cancel, window latched once, stream reset once.
- [ ] Second pure-repeat burst: stamp bit-identical, host still 1, backend unchanged (no re-latch/re-stamp).
- [ ] Docstring carries the audit finding: n+1+R vs n+1; bound ≈ repeat_rate × burst_duration (≤4–5 chars); post-burst repeats uncompensable by design; S2 owns the decision.

### Code Quality / Scope Validation
- [ ] Real `cancel()` driven (no spy); probe-validated assertions transcribed 1:1; doubles local to the section.
- [ ] Zero source change; no test_daemon/test_typing_backends edits (parallel sibling); no mitigation (S2).

### Documentation & Deployment
- [ ] Mode A: the audit note lives in the test docstring (the written finding for S2). No separate doc file.

---

## Anti-Patterns to Avoid

- ❌ Don't monkeypatch `d.cancel` — the test must replay the REAL seam (pump → `_on_cancel_backspace` → `cancel()`); count via backend/host side effects. (CRITICAL #3.)
- ❌ Don't skip `_text_in_flight.set()` + the host — cancel() then never latches the window and the re-stamp assertion is vacuous. (CRITICAL #2.)
- ❌ Don't improvise "improvements" to the probe-validated body — if an assertion fails, the tree drifted; investigate, don't weaken. (CRITICAL #1.)
- ❌ Don't approximate the re-stamp check — assert the float is **bit-identical** (a re-stamp yields a different `time.monotonic()`).
- ❌ Don't edit any source file, add a mitigation, or write a separate audit doc — the pin + the docstring note ARE the deliverable (S2 owns mitigation).
- ❌ Don't touch `tests/test_typing_backends.py` (parallel T2.S3) or `tests/test_daemon.py` (reference only).
- ❌ Don't run pytest without timeout/full paths; don't invent ruff/mypy gates.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The entire test body was **executed as a live probe against the current tree and passed** (research §3 records the exact output) — this is transcription, not authoring. The harness pieces it reuses (`_wire_daemon`, the event tuples, `_pump_events`, the wiring chain) are all line-verified, and the two properties asserted (one cancel; no re-stamp) have two independent detectors each. The −0.5 is purely tree drift between the probe and the implementation run — which CRITICAL #1 + L3 handle by construction (investigate, don't weaken). Pure-Python: no devices, no CUDA, no threads, no daemon startup.
