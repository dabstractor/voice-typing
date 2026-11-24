# PRP — P1.M2.T2.S1: Keep partial dispatch prompt and fail closed under bursts

## Goal

**Feature Goal**: Fix the three code-verified dispatch/backpressure defects in `voice_typing/bulk_controller.py` behind BUG-002's controller half, and make update-granular delivery **provably prompt**: (A) a burst of same-utterance partials against a FULL queue must **coalesce into the queued partial's own slot** (capacity-neutral, newest-wins) instead of spuriously stopping delivery — today the capacity check runs BEFORE the same-key replace-in-place scan; (B) a REAL overflow must **stop exactly once and fire `on_stopped` outside the lock** — today the overflow branches in `on_partial`/`on_final`/`on_final_dropped` `return` inside `with self._cond:`, so the post-lock `_fire_on_stopped()` is unreachable; (C) the **generation re-check must exist at submit AND result time** — today only `active`/epoch are checked, so an `arm()` racing the writer lets a stale-generation op's APPLIED result bump `_expected_revision` and overwrite `_confirmed_visible` for the NEW session. Plus: pin "the first useful partial dispatches before its final" with dedicated tests. All existing invariants are preserved verbatim (mutation-time checks, one writer/one op, zero-diff suppression, the 250 ms deadline, ack-only revision/confirmation, FIFO barriers).

**Deliverable** (2 files edited, no new files, no interface changes):
1. `voice_typing/bulk_controller.py` — reorder `on_partial` (replace-in-place before capacity), restructure the three overflow branches to `arm()`'s fall-through notify shape, add `item.gen != self._session_gen` to `_process_next`'s pre-submit and result discards; Mode A docstring updates.
2. `tests/test_bulk_controller.py` + `tests/test_g2_bulk_gate.py` — 6 new tests (spaced-distinct show-before-final; same-key burst at capacity coalesces without stop; real overflow stops once + notifies outside the lock; pre-submit generation race → zero target calls; stale in-flight result never mutates; writer-thread promptness) + reconcile any existing test that pinned the old capacity-before-replace order.

**Success Definition**:
- (a) Spaced distinct partials for one utterance each dispatch a `show` promptly — before the utterance's `finalize` — under both `drain()` and the real writer thread; no timer defers the first useful partial.
- (b) A full queue + more same-utterance partials → every extra coalesces (`stats["coalesced"]` grows), delivery stays active, no `queue-overflow`; a full queue with NO replaceable slot + one more enqueue → stops ONCE with reason `queue-overflow`, `on_stopped` fired exactly once, provably outside `_cond`.
- (c) An `arm()` landing between pop and submit → ZERO target calls (`discarded_stale`); an `arm()` landing during an in-flight op → its APPLIED result is discarded (revision and `_confirmed_visible` unchanged).
- (d) All preserved invariants re-verified by the existing suites: `timeout 300 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_g2_bulk_gate.py tests/test_bulk_dispatch.py -q` → 0 failed (any flipped expectation is the bug-pinning test, commented); the wider fast sweep stays green.
- (e) No reader slowdown, no `queue_size`/`op_deadline` change, no typing fallback, no second writer; `bulk_delivery.py` untouched; all public signatures unchanged (S2/S3 consume as-is).

## User Persona

Not applicable (internal dispatch semantics; no user/config/API surface — item DOCS: Mode A code docstrings only; the user overview is P1.M2.T3.S2's). Beneficiaries: the bulk-text operator (words paint during speech instead of sentence-end dumps — the R.1 norm), and S2/S3 which build on the verified controller.

## Why

- **BUG-002's controller half.** The G5 evidence (57-word backlog, one commit per utterance) is dominated by the upstream stabilized callback (S2's remediation; S6's diagnosis) — but the three controller defects are real and independently harmful: (A) turns the R.1 burst workload itself into spurious fail-closed stops; (B) silently swallows the one-time stop notification on the most common overflow paths (the daemon's on_stopped disarm wiring never fires); (C) breaks session isolation under an arm/write race. Fixing them makes the controller correct regardless of which stage dominates the measured lag — and (A) is exactly the fail-closed-under-bursts mandate.
- **The promptness mandate needs proof, not hope.** "There is no intentional writer debounce" is currently a docstring claim; the show-before-final property was never pinned by a test. Dedicated tests (drain + real writer) lock it so a future change can't reintroduce wait-for-final semantics invisibly.
- **Fail-closed is the design, spurious fail-closed is a bug.** R.5 mandates stop-on-overflow rather than dropping barriers — but stopping when a legal capacity-neutral coalesce existed converts recoverable bursts into delivery death. The reorder keeps every genuine fail-closed path (barriers, no-slot overflow, deadline, refused/unknown) intact.

## What

Three targeted fixes in `bulk_controller.py` plus tests: (1) `on_partial` tries the same-key replace-in-place scan BEFORE the capacity check (a replace never grows the queue; stop only at capacity with no replaceable slot); (2) the overflow branches in `on_partial`/`on_final`/`on_final_dropped` fall out of the lock before notifying (mirroring `arm()`), so `_fire_on_stopped()` always runs outside `_cond`; (3) `_process_next` adds the generation check (`item.gen != self._session_gen`) to the pre-submit discard and the late-result discard. Docstrings updated to the refined invariants.

### Success Criteria

- [ ] `on_partial`: same-key replace scan precedes the capacity check; capacity+no-slot → single overflow stop + outside-lock notify; finals/boundaries remain append-only.
- [ ] `on_final`/`on_final_dropped`: overflow path exits the lock before `_fire_on_stopped()`.
- [ ] `_process_next`: pre-submit section discards `item.gen != self._session_gen` with ZERO target calls; result section discards stale-generation APPLIED without mutating revision/`_confirmed_visible`.
- [ ] The 6 new tests pass; existing suites green (or the bug-pinning expectation flipped with a comment).
- [ ] Module/method docstrings state the refined dispatch/overflow invariants (Mode A).
- [ ] `git status --short` == `voice_typing/bulk_controller.py` + the two test files.

## All Needed Context

### Context Completeness Check

_Pass._ All three defects are verified against the live code with exact line references (research §1; quoted current text below for byte-exact edits). The promptness analysis (research §2) establishes attribution independence — S1 is required regardless of S6's stage verdict — and the no-debounce/no-cadence-change constraints are explicit. The test plan (research §4) gives the deterministic seams: the existing `_FakeTarget`/`drain()` idiom, the g2 `_controller`/`_no_legacy_backend` helpers, a gated-`show` fake for the in-flight race, and the `_ensure_runner`-override hook (which sits between `_process_next`'s two critical sections — the deterministic arm-race injection point). The parallel S6 PRP's contract (stage diagnosis + candidate criteria) is consumed as context, not duplicated.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S1/research/prompt_dispatch_fail_closed.md
  why: "§1 THE THREE DEFECTS with exact line refs + quoted code (A: capacity-before-replace in on_partial
        :558-565; B: in-lock return skipping _fire_on_stopped in the three overflow branches; C: missing
        item.gen re-check at _process_next's pre-submit ~:712-720 and result ~:756-758 sections — the
        docstring :196-197 already PROMISES generation supersession). §2 promptness analysis (no debounce
        exists; upstream attribution; what S1 must prove). §3 exact edit sites. §4 the 6 tests with their
        deterministic seams (incl. the _ensure_runner override hook). §5 boundaries. §6 commands."
  section: "ALL load-bearing. §1 (defects), §4 (test seams) are the core."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§2 'Feasibility and confirmed seams' is the item's RESEARCH NOTE: names the three edge cases
        ('partial capacity is checked before replacing its own queue slot', 'actual overflow returns skip
        the post-lock stop hook', 'the pre-submit check currently only checks active after leaving the
        first condition critical section') + the constraints (no second writer, no timer deferral, never
        let a final erase a pending valid change, FIFO barriers). §'Gate and evidence handoff' confirms the
        G5 bars S1 must not weaken."
  critical: "The doc's constraint list is binding: do not add a second writer, do not debounce the first
             useful partial, do not let a final replace a partial, preserve barriers."
- file: voice_typing/bulk_controller.py
  why: "The file being edited. Module docstring invariants (:9-90 incl. :46 'ANY enqueue onto a full queue
        stops' — refine), on_partial (:532-569), on_final (:571-601), on_final_dropped (:603-622),
        _process_next (:675-800 — note runner = self._ensure_runner() sits BETWEEN the two critical
        sections), arm (:503-530, the correct fall-through notify template), _stop_locked (:856+, correct —
        never fires under lock), _writer_loop (:810)."
  critical: "Do NOT touch _stop_locked/_fire_on_stopped semantics, the single-worker runner, _note_late,
             zero-diff suppression, the deadline machinery, or any public signature."
- file: voice_typing/bulk_delivery.py
  why: "DeliveryTarget/ShowResult/rendered_equal — READ-ONLY context (the controller's target contract).
        UNTOUCHED by this task."
- file: tests/test_bulk_controller.py
  why: "The drain idiom (deterministic, 'no timing races, no sleeps' per its header) + _FakeTarget (:33).
        Existing tests already cover coalescing (:112-211) and zero-diff — extend, don't rewrite."
- file: tests/test_g2_bulk_gate.py
  why: "The g2 harness idioms: _no_legacy_backend (:77), _controller(fake, gen, queue_size=QSIZE,
        op_deadline=DEADLINE, on_stopped=…) (:240), trace tests (:292+). The burst-at-capacity and
        overflow tests belong here (or in test_bulk_controller.py with the same helpers inlined)."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/PRP.md
  why: "The parallel stage-diagnosis contract (my INPUT): S6 localizes the visible lag and names candidate
        criteria 'for P1.M2.T2.S1 and P1.M2.T2.S2'. S1 is attribution-independent (research §2) — the
        three defects are real regardless of S6's verdict — but consume its diagnosis if landed."
  critical: "Do NOT duplicate S6's measurement work or touch the g5 lab files."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── bulk_controller.py       # EDIT (on_partial reorder + 3 overflow branches + _process_next gen checks + docstrings).
└── bulk_delivery.py         # UNTOUCHED (DeliveryTarget/ShowResult/rendered_equal).
tests/
├── test_bulk_controller.py  # EDIT (+ promptness/race tests; drain idiom).
└── test_g2_bulk_gate.py     # EDIT (+ burst-at-capacity/overflow tests; _controller helper).
```

### Known Gotchas

```python
# CRITICAL #1 — REPLACE-BEFORE-CAPACITY IS FOR PARTIALS ONLY. A final/_SessionBegin/_Boundary is a FIFO
#   barrier: append-only + overflow-stop stays ("never let a final erase a pending valid change"). Only
#   on_partial gets the reorder — a same-key partial replacing its own slot never grows the queue.
# CRITICAL #2 — THE OVERFLOW BRANCHES MUST FALL OUT OF THE LOCK. Mirror arm(): set a local flag inside
#   `with self._cond:`, RETURN AFTER the block, then `if stopped: self._fire_on_stopped()`. The current
#   early `return` inside the lock is the bug (B). _fire_on_stopped must NEVER run under _cond — a user
#   callback that takes the lock must not deadlock (the new outside-lock test proves it).
# CRITICAL #3 — THE GEN CHECK IS ADDITIVE. Keep `not self._active` AND `epoch != self._dispatch_epoch`
#   exactly as-is; ADD `item.gen != self._session_gen` to both the pre-submit and the result discards.
#   arm() does NOT bump the epoch (only stops do) — the gen check is the ONLY guard for the arm race.
# CRITICAL #4 — THE DETERMINISTIC ARM-RACE HOOK IS _ensure_runner. It runs BETWEEN _process_next's two
#   critical sections — a test subclass overriding it to call self.arm(gen+1) then super() injects the
#   race with zero timing. For the in-flight-result race, use a gated _FakeTarget.show (blocks on an
#   Event) + arm(2) while in flight + release, then assert revision/_confirmed_visible unchanged.
# CRITICAL #5 — A FULL-QUEUE EXPECTING OVERFLOW MAY BE A BUG-PIN. If an existing test fills the queue
#   with same-utterance partials and expects "queue-overflow", it encoded defect A — flip it to
#   coalesced/no-stop with a comment. Do NOT weaken any OTHER assertion (barrier overflow, deadline,
#   refused/unknown stops all remain).
# CRITICAL #6 — NO MASKING: do not slow the reader, change queue_size/op_deadline defaults, add sleeps
#   for synchronization in tests (bounded poll/deadline loops only), or add any typing fallback.
# CRITICAL #7 — AGENTS.md: every pytest run under `timeout N` inner + bash-tool timeout outer. Full
#   paths (.venv/bin/python). Never foreground the daemon.
```

## Implementation Blueprint

### Data models and structure

None changed. `_Partial`/`_Final`/`_Boundary`/`_SessionBegin`, the bounded deque + Condition, the single-worker executor, and all public signatures are preserved.

### Implementation Tasks (ordered)

```yaml
Task 1: EDIT on_partial — reorder + restructure (defects A+B)
  - MOVE the same-key replace-in-place scan BEFORE the capacity check; keep the scan's
    coalesced-stat + notify + return semantics verbatim.
  - RESTRUCTURE the overflow branch to arm()'s shape:
    OLD (inside `with self._cond:`): `if len(...)>=size: stopped=_stop_locked(...); if stopped: stats; return`
    NEW: inside the lock — try replace (return on hit); `if len>=size: stopped=...; if stopped: stats+=1`
         else `self._dq.append(...); notify`; AFTER the lock — `if stopped: self._fire_on_stopped()`.
  - Update the method docstring: replace-in-place is capacity-neutral and precedes the stop; overflow
    fires only with no replaceable slot.
Task 2: EDIT on_final + on_final_dropped — restructure only (defect B)
  - Same fall-through shape (append-only unchanged; barriers never replace).
Task 3: EDIT _process_next — the two gen checks (defect C)
  - Pre-submit section: `if not self._active or item.gen != self._session_gen:` → discarded_stale, return True.
  - Result section: `if epoch != self._dispatch_epoch or not self._active or item.gen != self._session_gen:`
    → return True (never mutate).
  - Update the docstring's mutation-time list to include the generation re-check (it already claims it).
Task 4: EDIT the module docstring (:46) — "ANY enqueue onto a full queue stops" → "an enqueue onto a full
  queue with NO replaceable same-key partial slot stops; a same-key partial always replaces its own slot
  first (capacity-neutral); every stop notifies exactly once, outside the lock".
Task 5: ADD the 6 tests (research §4) across the two files; reconcile bug-pinning expectations (Critical #5).
  QA-HARNESS TRAPS (verified live — do not rediscover): (i) the controller is INERT until
  `ctrl.acquire()` returns True — every test must acquire() BEFORE arm() (the file's `_armed()`
  helper already does); (ii) `_FakeTarget.acquire()` permanently records a `Call("acquire",…)`
  in `fake.calls` — assert zero-target-ops via `[c.method for c in fake.calls if c.method != "acquire"] == []`;
  (iii) the pre-submit race test must gate its `_ensure_runner` override on "after the first
  `arm(1)`" (a bare flag makes it fire during acquire(), invalidating the scenario); (iv) a
  real-overflow outside-lock test proves itself by having `on_stopped` itself call a lock-taking
  method (`ctrl.stop(leave=False)`) — under the old in-lock-notify shape it deadlocks (bounded join).
Task 6: VALIDATE (Level 1-2 commands; git status).
```

### Implementation Patterns & Key Details

```python
# on_partial — the corrected core (Task 1); everything above (stale/dup/closed/seq/latest_recognized) verbatim:
            # (1) REPLACE-IN-PLACE FIRST — capacity-neutral: reuses the queued partial's own slot, so a
            # same-utterance burst at a FULL queue coalesces instead of spuriously stopping (BUG-002 A).
            for i, item in enumerate(self._dq):
                if isinstance(item, _Partial) and (item.gen, item.utterance) == key:
                    self._dq[i] = _Partial(gen=gen, utterance=utterance, seq=seq, span=span)
                    self._stats["coalesced"] += 1
                    self._cond.notify_all()
                    return
            # (2) REAL overflow only when NO replaceable slot exists:
            if len(self._dq) >= self._queue_size:
                stopped = self._stop_locked("queue-overflow")
                if stopped:
                    self._stats["overflow"] += 1
            else:
                self._dq.append(_Partial(gen=gen, utterance=utterance, seq=seq, span=span))
                self._cond.notify_all()
        if stopped:                      # OUTSIDE _cond (arm()'s shape — the old in-lock return skipped this)
            self._fire_on_stopped()

# _process_next — the two ADDITIVE gen checks (Task 3); surrounding code verbatim:
        with self._cond:
            if not self._active or item.gen != self._session_gen:      # + gen: the arm-race guard (C)
                self._stats["discarded_stale"] += 1
                return True                                             # ZERO target calls
            epoch = self._dispatch_epoch
        ...
        with self._cond:
            if (epoch != self._dispatch_epoch or not self._active
                    or item.gen != self._session_gen):                  # + gen: stale session never mutates
                return True
```

### Integration Points

```yaml
PRESERVED (verbatim):
  - interfaces: "on_partial/on_final/on_final_dropped/arm/stop/cancel/drain/halt_for_takeover signatures"
  - invariants: "mutation-time gen/closure/cancel/epoch checks (gen now enforced at submit+result), one
                 writer/one op, zero-diff suppression, 250 ms deadline, ack-only revision/confirmation,
                 FIFO barriers, newest-partial-wins per (gen, utterance)"
CHANGED:
  - on_partial: "same-key replace precedes capacity; overflow only with no replaceable slot"
  - overflow paths x3: "notify once, outside the lock"
CONSUMED-BY:
  - P1.M2.T2.S2: "source-to-field remediation builds on the verified prompt controller"
  - P1.M2.T2.S3: "route qualification re-runs G5 against this controller"
```

## Validation Loop

### Level 1–2 (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -v   # all green
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_bulk_contracts.py -q   # neighbors green
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q                    # fast sweep
# Optional: /home/dustin/.local/bin/ruff check voice_typing/bulk_controller.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py
```

### Level 3 (behavioral spot-probe — drain determinism)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python - <<'PY'
from tests.test_bulk_controller import _FakeTarget  # the existing fake (or inline an equivalent)
from voice_typing.bulk_controller import BulkController
fake = _FakeTarget(); ctrl = BulkController(fake, queue_size=4)
ctrl.arm(1)
ctrl.on_partial("hello", utterance="u1", seq=1, gen=1)
assert ctrl.drain() == 2                      # barrier + ONE show — dispatched NOW, no final needed
ctrl.on_partial("hello world", utterance="u1", seq=2, gen=1)
assert ctrl.drain() == 1                      # second show
ctrl.on_final("hello world", utterance="u1", seq=3, gen=1)
assert ctrl.drain() == 1                      # finalize AFTER the shows
print("OK: show-before-final + prompt dispatch verified")
PY
```

### Level 4 (scope guard)

```bash
git status --short   # == voice_typing/bulk_controller.py + the two test files — nothing else
grep -n "typing_backends\|queue_size=\|op_deadline=" voice_typing/bulk_controller.py | head   # defaults untouched
```

## Final Validation Checklist

- [ ] The 6 new tests pass; both edited suites + neighbors + fast sweep green under `timeout`.
- [ ] Same-utterance burst at capacity coalesces (no stop); real overflow stops once + notifies outside the lock.
- [ ] Pre-submit gen race → zero target calls; in-flight stale APPLIED → no state mutation.
- [ ] Spaced distinct partials → shows before the final (drain + real writer thread).
- [ ] Module/method docstrings state the refined invariants; `_stop_locked`/`_fire_on_stopped` untouched.
- [ ] Only the 3 files changed; no interface/deadline/queue-size changes.

## Anti-Patterns to Avoid

- ❌ Don't stop at capacity when a same-key replaceable slot exists — that's defect A, the exact bug (Critical #1).
- ❌ Don't let a final/boundary replace a queued partial, and don't reorder barriers — FIFO is the ordering law.
- ❌ Don't return from inside `with self._cond:` on a stop path — the notify must be outside (Critical #2).
- ❌ Don't replace the existing active/epoch checks — ADD the gen check (Critical #3).
- ❌ Don't add debounce/timers, sleeps-in-tests, bigger queues, longer deadlines, or any typing fallback (Criticals #5/#6).
- ❌ Don't touch `bulk_delivery.py`, the g5 lab files (S6's), or the daemon (S2's wiring).
- ❌ Don't run un-timed commands (Critical #7 / AGENTS.md).
