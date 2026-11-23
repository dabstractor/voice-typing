# PRP — P1.M3.T2.S2: BulkController failure handling — 250 ms deadline, disarm-on-unknown, no retries

## Goal

**Feature Goal**: Make `voice_typing/bulk_controller.py` (S1's ordering core) **failure-complete**
per PRD §4.2sexies R.5: every target operation runs under the **250 ms engineering deadline**
(`op_deadline`, default 0.25 s); a **stalled** op (deadline miss), an explicit **UNKNOWN**, a **REFUSED**,
or a **target exception** (child death) → the controller **stops delivery** (disarms bulk delivery at
the controller level; the daemon-side recording disarm consumes the `on_stopped` seam — wiring is
P1.M6.T2.S1), **retains recoverable recognition**, and reports **ONE concise reason** — with **NO retry
ever** of an operation that may already have landed, and **receiver-side deadline validation** so a
late result can never mutate state after give-up. Also implement the **three-value law**: latest
recognized text, filter-accepted final, and last target-CONFIRMED visible text stay distinct and
queryable.

**Deliverable** (TWO files MODIFIED; nothing else changes — both are S1's new files, extended):
1. `voice_typing/bulk_controller.py` — EXTEND `BulkController` with: `op_deadline` ctor kwarg; the
   single-worker op runner + `future.result(timeout=…)` dispatch; the `_dispatch_epoch` give-up guard
   (late-result discard); exception→UNKNOWN handling; the stop-reason vocabulary; the three-value
   accessors; retention across a failure stop; the extended `stats()` counters. (Design pinned in
   research §2.)
2. `tests/test_bulk_controller.py` — APPEND a `# P1.M3.T2.S2 — failure handling` section (~13 tests,
   matrix in research §3) after S1's section. Do NOT touch S1's tests.

**Success Definition**:
- (a) `timeout-after-apply` passes — the core give-up law: a gated `show()` (applies in the field but
  returns after the deadline) → stop, reason `"op-deadline"`, exactly ONE target call (no retry), and
  the late APPLIED result is DISCARDED (revision unchanged, `confirmed_visible()` unchanged,
  `late_results_discarded +1`).
- (b) The six item traces pass: timeout-after-apply; held key; out-of-order results; stop + immediate
  re-arm; child death; focus change mid-operation (research §3 tests 1-6).
- (c) Three-value law: `latest_recognized() / accepted_final() / confirmed_visible()` can all differ
  simultaneously; all retained after a failure stop.
- (d) `timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py -v` → all pass (S1's ~25 +
  the ~13 new); deterministic (Event-bounded fakes, `op_deadline=0.02`, no bare sleeps).
- (e) `timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_bulk_controller.py
  tests/test_zero_diff_rewind.py -q` → 0 failed; `tests/test_streaming_commit.py` shows NO NEW
  failures vs the G1 baseline (10 reds at baseline — pre-existing, not ours).
- (f) Purity law intact: module still imports ONLY stdlib + `voice_typing.bulk_delivery`; no
  `type_text`/`press_backspace`/`make_backend`/`StreamingOutput` (S1's guard tests re-run green).
- (g) `git status --short` shows ONLY the two files (already S1's; modified, not new).

## User Persona

**Target User**: P1.M3.T2.S3 (the G2 gate — runs the full fake-target matrix incl. these failure
traces), P1.M6.T2.S1 (daemon wiring — consumes `on_stopped(reason)` to disarm bulk delivery AND
recording), P1.M3.T3.S2 (status surface — consumes `_stopped_reason`/fault counters).

**Use Case**: The writer thread issues `target.show(...)`; the adapter subprocess stalls (or dies, or
the user grabs the keyboard mid-edit). The controller gives up at 250 ms, marks delivery stopped with
one concise reason, fires `on_stopped` once, keeps the recognized text for recovery — and never
re-sends (the op may have landed; a retry could duplicate visible text).

**Pain Points Addressed**: The Rev 2/3 incident class (a hung editor call wedging the writer; a late
result landing after the daemon already gave up and desyncing `_shown_span`/revision; a retried
unknown op duplicating text). R.5 exists because these were REAL failures.

## Why

- **R.5 mandates it verbatim**: "Any unknown/refused/stalled operation (250 ms engineering deadline)
  disarms bulk delivery AND recording, retains recoverable recognition, and reports one concise
  reason… NEVER retry an operation that may already have landed. Validate deadlines in the RECEIVER so
  a late operation cannot mutate after the daemon has given up." S1's PRP explicitly deferred exactly
  this to S2 ("The 250 ms deadline + daemon disarm are P1.M3.T2.S2's additions — leave the on_stopped
  callback seam").
- **S3's G2 gate asserts these traces** (timeout-after-apply; held key; out-of-order results; stop +
  immediate re-arm; child death; focus change mid-operation) — S2 is what makes them pass.
- **Pure Python + threads** — hermetic, fast, CI-safe; no Wayland/subprocess needed.

## What

Extend `BulkController` (S1's class — assume landed exactly per its PRP):

```python
BulkController(target, *, queue_size=32, on_stopped=None, op_deadline=0.25)   # NEW kwarg (code constant, NOT config)
# NEW behavior:
#   dispatch wraps the ONE target call per item in a single-worker runner:
#     future = runner.submit(fn,...); future.result(timeout=op_deadline)
#   - timeout  -> give-up: _stop("op-deadline"); epoch bumped; future abandoned into the discard path
#   - exception-> UNKNOWN-class: _stop("target-error") (exc name in stats); never re-raised
#   - in-time  -> S1's result branch, applied ONLY if the epoch is still current
#   _dispatch_epoch: int  # increments on EVERY give-up/stop; late results (add_done_callback sees a
#                          stale epoch / not _active) are DISCARDED + counted — never mutate state
#   stop reasons: "queue-overflow"(S1) | "op-deadline" | "refused" | "unknown" | "target-error"
#   on_stopped fires ONCE with the single reason string (the seam the daemon disarm consumes)
#   three-value law + retention:
#     latest_recognized() -> str    # newest span RECEIVED (partial or final; updated at ENQUEUE)
#     accepted_final()    -> str|None  # last filter-accepted final (on_final == accepted; daemon gates pre-entry)
#     confirmed_visible() -> str    # last span CONFIRMED by an in-time APPLIED (only on APPLIED)
#     #   all retained across a failure stop until the next acquire()/arm(gen)
#   stats() += stop_reason, stopped_at_ms, deadline_exceeded, target_errors, late_results_discarded
```

Full design (runner lifecycle, epoch protocol, leave() best-effort wrap, scope boundaries) pinned in
research §2 — follow it exactly.

### Success Criteria

- [ ] timeout-after-apply: stop `"op-deadline"`, ONE target call, late APPLIED discarded (revision + `confirmed_visible()` unchanged, `late_results_discarded +1`).
- [ ] held key → REFUSED → stop `"refused"`, `on_stopped` once, no retry; focus-change mid-op → same path, queued op never dispatched.
- [ ] out-of-order: a stale future's late APPLIED after stop+re-arm cannot touch the new session (epoch+gen).
- [ ] stop + immediate re-arm: leave() once; acquire()→arm(gen2)→gen-2 partial APPLIES; gen-1 straggler discarded.
- [ ] child death: ConnectionError from the target → stop `"target-error"` (name in stats), no raise out of `_process_next`, `stop()`'s leave() on the dead target safe.
- [ ] Explicit UNKNOWN → stop `"unknown"`, no retry.
- [ ] Three-value law: all three accessors can differ simultaneously; retained post-stop.
- [ ] Fast ops unaffected (deadline never fires on instant fakes); S1's tests all still green.
- [ ] `on_stopped` fires exactly once; after ANY failure stop, `drain()`/`_process_next` make ZERO target calls.
- [ ] Purity guards green; only the two files modified.

## All Needed Context

### Context Completeness Check

_Pass._ The research note pins: S1's exact class contract (API/state/dispatch/stop path — §0), the R.5
operative lines (§1), the complete failure design (deadline runner, epoch give-up guard, exception
mapping, reason vocabulary, three values, retention, scope — §2), the ~13-test matrix with exact
assertions and the deterministic-fake recipe (§3), and tooling/coordination (§4). The consumed
contracts (`ShowResult`/`AcquireResult`/`DeliveryTarget`/`rendered_equal`) are LANDED and quoted. A
developer with no prior repo knowledge implements from the research note + the two PRPs (S1's + this).

### Documentation & References

```yaml
# MUST READ — the full failure design + test matrix (this task's spec)
- docfile: plan/008_a47116bb2b79/P1M3T2S2/research/failure_handling_design.md
  why: "§0 S1's exact contract (what you extend). §1 the R.5 operative lines. §2 the pinned design:
        op runner, epoch give-up guard, exception→UNKNOWN, reason vocabulary, three-value law,
        retention, scope boundaries. §3 the test matrix (~13) with the Event-bounded fake recipe.
        §4 tooling/coordination (TDD RED until S1 lands)."
  section: "ALL load-bearing."

# MUST READ — the class being extended (CONTRACT; assume it lands EXACTLY as specified)
- file: plan/008_a47116bb2b79/P1M3T2S1/PRP.md
  why: "BulkController's API/invariants/dispatch/result-branch/stop-path + the seam left for S2
        ('The 250 ms deadline + daemon disarm are P1.M3.T2.S2's additions — leave the on_stopped
        callback seam'). Its research/ordering_core_design.md §2 is the threading/state spec you
        extend; §3 is the test file you APPEND to (never edit S1's tests)."
  critical: "bulk_controller.py is IN PARALLEL and may not exist yet → the appended tests are TDD RED
             until it lands. Verify: ls voice_typing/bulk_controller.py. NEVER vendor S1's class."

# MUST READ — the LANDED contracts consumed (import; never duplicate)
- file: voice_typing/bulk_delivery.py
  why: "ShowResult (APPLIED/UNCHANGED/REFUSED/UNKNOWN; str values), AcquireResult(ok,handle,revision,
        reason), DeliveryTarget Protocol (acquire/show/finalize/leave/cancel), rendered_equal. The
        docstring already pins the taxonomy: 'refused and unknown DISARM delivery — and an operation
        whose outcome is unknown is NEVER retried (R.5)'."
  critical: "READ-ONLY. Branch on the enum members; the str values are the status-surface words."

# MUST READ — the do-not-touch surface (the separation law)
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§3: bulk code must NOT call type_text/press_backspace/make_backend/StreamingOutput.*; the
        three shared-state traps (_on_final_lock; daemon.py:1738 reads _stream.committed; feedback
        mirrors). Encode as guard tests (S1's — keep green), not prose."
  critical: "Never import voice_typing.streaming/typing_backends/daemon. Daemon disarm wiring is
             P1.M6.T2.S1 — S2 only provides on_stopped(reason) + retention."

# MUST READ — the spec source (quote in docstrings)
- docfile: PRD.md
  why: "§4.2sexies R.5 (the failure bullet: 250 ms deadline; disarm both; retain recognition; one
        concise reason; never retry; validate deadlines in the RECEIVER), R.3 ('Bytes sent is not
        applied; unknown is not delivered'), R.1 (counts-and-times logging)."
  critical: "READ-ONLY. Anchor the module docstring's failure section to the R.5 quote."

# STYLE REFS (read for pattern, not coupling)
- file: tests/test_bulk_delivery.py
  why: "The landed test style for this feature area: plain functions, in-process fakes, purity guards."
- file: voice_typing/audio_ducking.py
  why: "Protocol-consumer module precedent (pure stdlib + typing)."
  critical: "READ-ONLY both."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/
  bulk_delivery.py       # LANDED (contracts) — import, never edit
  bulk_controller.py     # ← S1 (IN PARALLEL; may not exist yet) — EXTEND (this task)
  streaming.py typing_backends.py daemon.py   # FORBIDDEN imports (d2 §3)
tests/
  test_bulk_delivery.py  # LANDED — re-run, untouched
  test_bulk_controller.py# ← S1's new file — APPEND the failure section (this task)
  test_zero_diff_rewind.py test_streaming_commit.py  # legacy re-run; G1 baseline had 10 commit reds (pre-existing)
```

### Desired Codebase tree

```bash
voice_typing/bulk_controller.py    # MODIFIED: + op_deadline, op runner, epoch give-up guard,
                                   #   exception→UNKNOWN, reason vocabulary, three-value accessors,
                                   #   retention, extended stats()
tests/test_bulk_controller.py      # MODIFIED: APPEND "# P1.M3.T2.S2 — failure handling" (~13 tests)
# NOTHING ELSE. No daemon/config/feedback/streaming/typing_backends edits.
```

### Known Gotchas

```python
# CRITICAL #1 — S1 IS IN PARALLEL. bulk_controller.py may not exist yet → the appended tests are TDD
#   RED (ImportError/AttributeError) until it lands. Verify with ls; NEVER vendor S1's class or edit
#   its tests — APPEND only, after S1's last test.
# CRITICAL #2 — THE DEADLINE IS RECEIVER-SIDE, IN THE CONTROLLER. The adapter is NOT trusted to
#   self-timeout: the controller submits the ONE op to a single-worker runner and waits
#   future.result(timeout=op_deadline). On timeout: give-up = bump _dispatch_epoch + stop. The
#   abandoned future's eventual result is discarded by the epoch check in add_done_callback — it must
#   NEVER bump revision / update _shown_span / _confirmed_visible (the timeout-after-apply test).
# CRITICAL #3 — NO RETRY IS STRUCTURAL. After a failure stop the writer dispatches nothing; the
#   give-up path never resubmits. At most ONE abandoned future exists per runner (a give-up stops
#   dispatch), preserving one-op-in-flight. Test: after stop, drain() makes ZERO target calls.
# CRITICAL #4 — ONE CONCISE REASON. _stopped_reason is a single short string from the fixed
#   vocabulary ("queue-overflow"|"op-deadline"|"refused"|"unknown"|"target-error"); details (exception
#   name, op kind) live in stats(), not the reason. on_stopped fires EXACTLY once.
# CRITICAL #5 — TARGET EXCEPTIONS ARE UNKNOWN-CLASS, NEVER RAISED. future.result() re-raises the
#   target's exception (child death: ConnectionError/ProcessLookupError) — catch in dispatch →
#   _stop("target-error"); _process_next must never propagate. Wrap stop()'s target.leave() best-effort
#   so a dead target cannot mask the original reason.
# CRITICAL #6 — THREE VALUES, THREE UPDATE POINTS. latest_recognized: at ENQUEUE (partial or final).
#   accepted_final: at ENQUEUE of on_final (the daemon applied textproc gates BEFORE entry — the
#   controller applies none). confirmed_visible: ONLY on an in-time, epoch-valid APPLIED. Never let
#   one stand in for another (the desync class R.5 calls out).
# CRITICAL #7 — op_deadline IS A CODE CONSTANT (0.25), NOT CONFIG. R.5 says "250 ms engineering
#   deadline"; the config surface is P1.M3.T3.S1's. Tests inject via the ctor kwarg (0.01–0.05).
# CRITICAL #8 — RUNNER LIFECYCLE. start() creates the single-worker executor (daemon threads);
#   stop() shuts it down (wait=False); a re-start() after a failure stop gets a FRESH runner — the
#   stop+immediate-re-arm test depends on the old runner's late result being unreachable except via
#   the epoch/done-callback discard.
# CRITICAL #9 — DETERMINISTIC TESTS. Fakes block on threading.Event (wait bounded by 1.0 s timeouts),
#   op_deadline=0.02; NO bare time.sleep waits on the deadline. Drive dispatch via
#   _process_next(blocking=False)/drain() exactly like S1's tests. ONE real-thread assertion only if
#   needed for the runner path; keep it Event-gated.
# GOTCHA #10 — FULL TOOL PATHS (.venv/bin/python; zsh aliases) under `timeout 60`; mypy NOT installed;
#   ruff optional (/home/dustin/.local/bin/ruff).
# GOTCHA #11 — test_streaming_commit.py carries 10 PRE-EXISTING reds from the G1 baseline — do not
#   "fix" or skip them; only assert NO NEW failures.
```

## Implementation Blueprint

### Data models and structure

No new public data model. Internal additions to `BulkController`: `_op_deadline: float`,
`_runner: ThreadPoolExecutor|None`, `_dispatch_epoch: int`, `_latest_recognized: str`,
`_accepted_final: str|None`, `_confirmed_visible: str`, stats fields
(`stop_reason/stopped_at_ms/deadline_exceeded/target_errors/late_results_discarded`). stdlib only
(`concurrent.futures`, existing imports) + `voice_typing.bulk_delivery`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN: ls voice_typing/bulk_controller.py tests/test_bulk_controller.py   # S1 landed?
          grep -n "on_stopped\|_stopped_reason\|def _process_next\|def drain\|def stats" voice_typing/bulk_controller.py
          timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_bulk_delivery.py -q | tail -2
  - EXPECTED: S1 landed (if NOT: stop and report — do not vendor; the tests you append stay RED by design).
    Record S1's pass count as the baseline this task must preserve.

Task 2: IMPLEMENT the failure layer in voice_typing/bulk_controller.py
  - ADD per research §2: op_deadline ctor kwarg; runner lifecycle in start()/stop(); the deadline
    wrapper in the dispatch path (submit + result(timeout) + epoch capture + add_done_callback discard);
    exception→"target-error"; reason vocabulary mapping in the result branch; three-value state updated
    at the pinned points; retention (no erase on stop; reset on acquire/arm); stats() extensions;
    docstring section anchored to the R.5 quote ("Any unknown/refused/stalled operation (250 ms
    engineering deadline) disarms… NEVER retry… Validate deadlines in the RECEIVER…").
  - DO NOT: edit S1's ordering semantics/tests; import streaming/typing_backends/daemon; add config keys;
    touch feedback/daemon (P1.M6.T2.S1/P1.M3.T3.S2 own them).

Task 3: APPEND the failure test section to tests/test_bulk_controller.py
  - APPEND "# P1.M3.T2.S2 — failure handling" after S1's LAST test; implement the ~13-test matrix
    (research §3) with Event-bounded fakes extending S1's _FakeTarget (gated / delayed / raising /
    refusing variants). Re-run S1's purity guards (they cover the module after the edit).

Task 4: VALIDATE — L1 (py_compile), L2 (pytest: S1 baseline preserved + new green), L3 (scope guard),
        L4 (determinism: run the new section 3x). Iterate until green. No commit unless directed.
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the deadline + give-up (research §2.1-2.2). Dispatch path, replacing the direct call:
with self._cond:
    epoch = self._dispatch_epoch            # capture BEFORE submit
future = self._runner.submit(fn, gen, utt, seq, rev, span)
future.add_done_callback(lambda f: self._note_late(f, epoch))   # discard-path counter
try:
    result = future.result(timeout=self._op_deadline)
except FuturesTimeoutError:                 # stalled -> outcome UNKNOWN (may still land!)
    self._stop(reason="op-deadline")        # bumps _dispatch_epoch under _cond; on_stopped once; NO resubmit
    return
except Exception:                           # child death / adapter crash -> UNKNOWN-class
    self._stop(reason="target-error"); return
with self._cond:                            # RECEIVER-side validation (the R.5 law)
    if epoch != self._dispatch_epoch or not self._active:
        return                              # a late op result — NEVER mutate after give-up
    ...S1's result branch (APPLIED -> rev+1 AND _confirmed_visible=span; UNCHANGED -> continue;
       REFUSED -> _stop("refused"); UNKNOWN -> _stop("unknown"))

# PATTERN 2 — _note_late(f, epoch): if f.done() and (epoch stale or not _active):
#   stats["late_results_discarded"] += 1  — nothing else. NEVER revision/_shown_span/_confirmed_visible.

# PATTERN 3 — three-value updates (research §2.5):
#   on_partial/on_final enqueue: _latest_recognized = span          (under _cond, at ENQUEUE)
#   on_final enqueue:            _accepted_final   = span
#   in-time APPLIED only:        _confirmed_visible = span          (epoch-checked)
# PATTERN 4 — retention: _stop() clears _active but NOT the three values / _stopped_reason /
#   stats; acquire()/arm(gen) reset them with the per-gen state.
# PATTERN 5 — deterministic timeout test: FakeTarget.show blocks on self._gate (threading.Event);
#   ctl = BulkController(ft, op_deadline=0.02); enqueue; _process_next(blocking=False) returns fast
#   (deadline fires); assert stop/one-call; then ft._gate.set() + ft._applied.wait(1.0); assert
#   late_results_discarded==1 and revision/confirmed_visible UNCHANGED despite ft.text showing the edit.
```

### Integration Points

```yaml
MODULE:
  - modify: "voice_typing/bulk_controller.py (S1's file): + failure layer per research §2"
TESTS:
  - append to: "tests/test_bulk_controller.py — the failure section AFTER S1's last test"
CONSUMED (read-only): "voice_typing/bulk_delivery (ShowResult/AcquireResult/DeliveryTarget/rendered_equal)"
CONSUMERS (later, not here):
  - P1.M6.T2.S1: "daemon wiring — on_stopped(reason) -> disarm bulk delivery AND recording"
  - P1.M3.T3.S2: "delivery_state/delivery_reason status surface reads _stopped_reason/stats"
  - P1.M3.T2.S3: "the G2 gate runs the full matrix incl. these six traces"
DEPENDENCIES: "none new (stdlib concurrent.futures + existing)."
```

## Validation Loop

### Level 1: Syntax

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/bulk_controller.py tests/test_bulk_controller.py && echo "L1 OK"
# Expected: exit 0.
```

### Level 2: Unit tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py -v -k "deadline or refused or unknown or target_error or late or rearm or re_arm or three_values or retained or no_retry or on_stopped or fast_ops" | tail -20
# Expected: the ~13 new tests pass.
timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py -q | tail -2
# Expected: S1's baseline count + ~13, 0 failed.
timeout 60 .venv/bin/python -m pytest tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py -q | tail -2
# Expected: 0 failed (contracts + legacy untouched).
timeout 60 .venv/bin/python -m pytest tests/test_streaming_commit.py -q | tail -2
# Expected: exactly the G1-baseline reds (10) — NO NEW failures (Gotcha #11).
```

### Level 3: Scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected: ONLY voice_typing/bulk_controller.py + tests/test_bulk_controller.py modified (+ any
#   pre-existing plan/ artifacts). Any daemon/config/feedback/streaming/typing_backends/bulk_delivery
#   change is a SCOPE VIOLATION.
grep -n "import" voice_typing/bulk_controller.py | grep -vE "stdlib|bulk_delivery" && echo "L3 FAIL: forbidden import" || echo "L3 ok"
```

### Level 4: Determinism

```bash
cd /home/dustin/projects/voice-typing
for i in 1 2 3; do timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py -q -k "deadline or late or rearm or three_values or retained" | tail -1; done
# Expected: identical pass counts every run (Event-bounded, no timing races).
```

## Final Validation Checklist

- [ ] L1 py_compile OK; L2 all gates green (new section + S1 baseline + contracts + zero-diff + no-new-commit-reds); L3 only the two files; L4 deterministic ×3.
- [ ] timeout-after-apply: stop `"op-deadline"`, ONE call, late APPLIED discarded (rev + confirmed_visible unchanged, counter +1).
- [ ] held key / focus change → `"refused"` stop, on_stopped once, no retry; queued op never dispatched.
- [ ] out-of-order late result after stop+re-arm cannot touch the new session.
- [ ] stop + immediate re-arm: leave() once; gen-2 flows; gen-1 straggler discarded.
- [ ] child death → `"target-error"`, no raise, leave() safe.
- [ ] Explicit UNKNOWN → `"unknown"` stop.
- [ ] Three-value law + post-stop retention asserted.
- [ ] on_stopped exactly once; post-stop drain() → ZERO target calls; purity guards green.

## Anti-Patterns to Avoid

- ❌ Don't retry or resubmit any op after a give-up/REFUSED/UNKNOWN — structural no-retry (Critical #3).
- ❌ Don't let a late future mutate state — epoch-check EVERY result application (Critical #2).
- ❌ Don't trust the adapter to self-timeout — the deadline lives in the controller (the RECEIVER).
- ❌ Don't conflate the three values or update confirmed_visible on UNCHANGED/late results (Critical #6).
- ❌ Don't add config keys / daemon / feedback edits — out of scope (P1.M3.T3, P1.M6.T2).
- ❌ Don't vendor S1's class or edit its tests — APPEND only; if S1 hasn't landed, report, don't duplicate.
- ❌ Don't use bare sleeps for deadline tests — Event-gated fakes with op_deadline=0.02 (Critical #9).
- ❌ Don't "fix" the 10 pre-existing streaming_commit reds (Gotcha #11).
- ❌ Don't run mypy/bare python — `.venv/bin/python` under `timeout 60` (Gotcha #10).

---

## Confidence Score

**9/10.** The design is a thin, well-bounded layer over S1's pinned class (one executor wait + one
epoch counter + five reason strings + three tracked values), the contracts it branches on are LANDED
and quoted, and every test scenario has a deterministic Event-based recipe pinned in the research
note. The one structural risk — S1 landing slightly differently from its PRP (e.g. a renamed seam) —
is gated by Task 1's preflight (grep the seam names; reconcile before coding) and the TDD-RED
coordination rule. The trickiest semantic (timeout-after-apply discard) is exactly specified: revision
and `confirmed_visible` frozen at give-up even though the field shows the edit — which is WHY no
retry is safe.
