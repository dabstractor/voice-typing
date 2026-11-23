# PRP — P1.M3.T2.S1: Bulk-delivery ordering core — bounded queue, barriers, one writer

## Goal

**Feature Goal**: Create `voice_typing/bulk_controller.py` — the **R.5 ordering core** of the Rev 4
bulk-delivery controller (PRD §4.2sexies): event entry points that **enqueue and return** (never
touch the target on the reader thread or under the daemon control lock), a **bounded queue (default
32)** where **overflow STOPS delivery rather than dropping a barrier**, **finals/boundaries as
ordered barriers never overwritten**, **newest-partial-wins coalescing**, the identity state machine
(**session generation, utterance ids, per-utterance seq high-water, expected_revision**), **one
writer thread / one operation in flight per target**, and the controller-side **zero-diff skip**
(zero target calls for render-equal spans). Consumes the contracts module from the parallel
P1.M3.T1.S1 (`bulk_delivery.py`); produces the core that **P1.M3.T2.S2** (failure handling: 250 ms
deadline, disarm-on-unknown, no retries) extends.

**Deliverable** (TWO new files; nothing else changes):
1. `voice_typing/bulk_controller.py` — `class BulkController` per the design in research §2 (API,
   invariants, dispatch rules — all pinned there).
2. `tests/test_bulk_controller.py` — ~25 deterministic tests with an in-process `_FakeTarget`
   (matrix in research §3): the item's five traces (append / first-word change / identical update →
   zero events / retraction / Unicode) + the full ordering-invariant set + purity guards.

**Success Definition**:
- (a) Every R.5 ordering law in research §1 is implemented and pinned by at least one test
  (enqueue-and-return; one writer/one op in flight; newest-wins coalescing; barriers never
  overwritten; overflow stops delivery, drops nothing; gen/seq/closed discards;
  dropped-final-closes-boundary; zero-diff ⇒ zero target calls; REFUSED/UNKNOWN ⇒ stop, no retry).
- (b) `timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py -v` → all pass
  (deterministic — driven via the `_process_next()/drain()` seam, no timing races; one dedicated
  real-thread test proves one-writer serialization).
- (c) `timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_bulk_delivery.py
  tests/test_zero_diff_rewind.py tests/test_streaming_commit.py -q` → 0 failed (legacy untouched;
  `test_bulk_delivery.py` may not exist yet — see Critical #1).
- (d) The module imports ONLY stdlib + `voice_typing.bulk_delivery`; exposes NO
  `type_text`/`press_backspace`/`make_backend`/`StreamingOutput` (d2 §3 law; guard-tested).
- (e) `git status --short` shows exactly the two new files.

## User Persona

**Target User**: P1.M3.T2.S2 (failure handling — extends this core with the 250 ms deadline +
disarm-on-unknown), P1.M3.T3 (config gate + status surface), and P1.M6.T2.S1 (daemon wiring, which
will call the entry methods from the reader thread and `arm()` from the control thread).

**Use Case**: RealtimeSTT partials/finals (with their utterance ids + session generation, P1.M6.T1)
arrive on the daemon's reader thread → `on_partial`/`on_final` coalesce/dedup/enqueue in microseconds
and return → the single writer thread executes at most one `target.show`/`finalize` per item with the
current `expected_revision` → the taxonomy result drives continue/stop.

**Pain Points Addressed**: The Rev 2/3 incident class — whole-string rewrites, dropped-insertion
desync, out-of-order late events overwriting newer text, and blocking the reader thread on editor
I/O — all stem from missing ordering discipline. This core makes each law structural and tested.

## Why

- PRD §4.2sexies R.5 mandates this exact discipline verbatim (the research §1 table quotes each law);
  the controller cannot exist without it, and G2 (P1.M3.T2.S3) asserts these traces against a fake
  target — this task IS the G2 determinism foundation.
- The parallel P1.M3.T1.S1 ships the contract surface (`DeliveryTarget`/`ShowResult`/`rendered_equal`);
  something must *drive* it with correct ordering — that is this task; S2 then adds deadlines/disarm
  on top of the same class.
- It is pure Python + threads (no Wayland, no subprocess) → fast, hermetic, CI-safe tests.

## What

`class BulkController(target, *, queue_size=32, on_stopped=None)`:

```python
# lifecycle
acquire() -> bool                       # target.acquire(); seeds _expected_revision; _active=True
start() -> None                         # launch THE writer thread (one per controller)
stop(*, leave=True) -> None             # halt writer; target.leave() exactly once; post-stop events rejected
# event entries (reader/control-thread safe: bounded-structure ops ONLY, never target I/O, never block)
arm(gen: int) -> bool                   # SESSION_BEGIN barrier: bump _session_gen, reset per-gen state
on_partial(span, *, utterance, seq, gen) -> None
on_final(span, *, utterance, seq, gen) -> None
on_final_dropped(*, utterance, gen) -> None    # BOUNDARY barrier: closes w/o finalize (R.5)
# state
is_active() -> bool
stats() -> dict                         # counters per R.5 ("counts and times, not recognition text")
# deterministic test seams (same handler the thread runs)
_process_next(blocking=False, timeout=None) -> bool
drain(max_items=None) -> int
```

Semantics/invariants (FULL detail in research §2 — follow it exactly):
- `_dq` = `collections.deque` + `threading.Condition`, bounded by `queue_size`. Items:
  `_SESSION_BEGIN(gen)` / `_PARTIAL(gen, utt, seq, span)` / `_FINAL(gen, utt, seq, span)` /
  `_BOUNDARY(gen, utt)`. Barriers append; a partial REPLACES-IN-PLACE a queued partial of the same
  (gen, utt) (newest wins; keeps position before its utterance's final).
- Enqueue-side discards (under `_cond`): `gen != _session_gen` → stale; `(gen,utt) ∈ _closed` →
  late-post-final partial / duplicate final; `seq <= _high_seq[(gen,utt)]` → late. Finals/boundaries
  set `_closed` + high-water at enqueue. ANY enqueue at `len(_dq) >= queue_size` → **stop delivery**
  (reason `"queue-overflow"`; never drop-and-continue).
- Writer dispatch (mutation-time re-checks: gen + closed again): `_PARTIAL` → if
  `rendered_equal(_shown_span[utt], span)` → zero-diff skip (NO target call); else ONE
  `target.show(gen, utt, seq, _expected_revision, span)`. `_FINAL` → ONE
  `target.finalize(...)` with the final span. `_SESSION_BEGIN`/`_BOUNDARY` → state resets only.
- Result branch: APPLIED → `_expected_revision += 1`, continue; UNCHANGED → continue; REFUSED /
  UNKNOWN → **stop** (no retry, no further target calls, `on_stopped` fired once). Overflow → same
  stop path.
- The controller applies NO textproc guards (daemon wiring P1.M6.T2.S1 does, before entry) and
  touches no feedback/`_stream`/backends (d2 §3; delivery-state feedback keys are P1.M3.T3.S2's).

### Success Criteria

- [ ] The five item traces pass: append; first-word change (one show with the NEW complete span); identical update → ZERO target calls; retraction (shorter span); Unicode byte-exact spans.
- [ ] Newest-wins: 3 coalesced partials → exactly ONE show with the seq-3 text.
- [ ] Barriers survive: final + boundary items are never replaced; late post-final partial and duplicate final discarded; dropped-final closes its boundary with NO finalize.
- [ ] Overflow (barrier AND partial variants) stops delivery: `is_active()` False, reason recorded, nothing dropped-and-continued, later events rejected.
- [ ] REFUSED and UNKNOWN each stop delivery with zero retries; UNCHANGED continues with unchanged revision; revision advances only on APPLIED.
- [ ] One-writer: all target calls on a single thread id, strictly serialized.
- [ ] arm(gen) resets per-utterance state; stale-generation events discarded (enqueue AND dispatch re-check).
- [ ] stop() → target.leave() exactly once; no post-stop target calls.
- [ ] Purity guards pass (no forbidden attrs/imports). Only the two new files in git status.

## All Needed Context

### Context Completeness Check

_Pass._ The research note pins: every R.5 law verbatim-anchored (§1), the full design — threading
model, item kinds, state, dispatch rules, scope boundaries (§2), the complete test matrix with exact
assertions (§3), and tooling/baseline (§4). The consumed contract signatures are quoted in the
parallel PRP (§ What) and its L3 probe. A developer with no prior repo knowledge implements from
those two documents + the style refs.

### Documentation & References

```yaml
# MUST READ — the full design: laws table, threading model, items, state, dispatch, test matrix
- docfile: plan/008_a47116bb2b79/P1M3T2S1/research/ordering_core_design.md
  why: "§1 the R.5 laws each mapped to a design consequence; §2 the pinned design (producers/writer,
        deque+Condition, item kinds, coalesce replace-in-place, discards, expected_revision rules,
        stop paths, scope boundaries); §3 the ~25-test matrix with exact assertions; §4 tooling."
  section: "ALL load-bearing."

# MUST READ — the consumed contract (parallel P1.M3.T1.S1; assume it lands EXACTLY as specified)
- file: plan/008_a47116bb2b79/P1M3T1S1/PRP.md
  why: "The signatures this controller programs against: ShowResult (applied|unchanged|refused|
        unknown), AcquireResult(ok, handle, revision, reason), DeliveryTarget(acquire/show/finalize/
        leave/cancel — show/finalize take (session:int, utterance:str, seq:int, expected_revision:int,
        span:str) -> ShowResult), rendered_equal(old,new). Also its L3 probe (the minimal FakeTarget
        shape to mirror in tests)."
  critical: "bulk_delivery.py is IN PARALLEL and may not be landed yet → our tests are TDD RED
             (ImportError) until it lands. Do NOT vendor/duplicate the contracts — import them."

# MUST READ — the do-not-touch surface + the wiring context (who calls us, where)
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§1 the event relay (reader thread invokes _on_partial/_on_final — why entries must enqueue
        and return; the five final-put sites where utterance ids will attach). §3 the law: bulk code
        must NOT call type_text/press_backspace/make_backend/StreamingOutput.* and the three
        shared-state traps (_on_final_lock; daemon.py:1738 reads _stream.committed; feedback mirrors).
        §2 the cancel-intercept site (S2/later — context only)."
  critical: "Encode the no-typing-fallback law as guard tests, not prose. Never import
             streaming/typing_backends/daemon."

# MUST READ — the R.5 source wording (what every docstring must anchor)
- docfile: PRD.md
  why: "§4.2sexies R.1 (event-count law; zero-diff generalization), R.3 (show/finalize semantics),
        R.5 (the ordering/takeover/failure bullet list this core implements)."
  critical: "READ-ONLY. Quote the operative R.5 lines in the module docstring."

# STYLE REFS (read for pattern, not coupling)
- file: voice_typing/streaming.py
  why: "The state-machine style precedent: class docstring enumerating State (all under self._lock),
        clock/seam injection, reset_* lifecycle methods (:180 StreamingOutput)."
  gotcha: "READ-ONLY — never import."
- file: voice_typing/audio_ducking.py
  why: "The protocol-consumer module precedent (pure stdlib + typing; purity guard style)."
- file: tests/test_textproc.py
  why: "Plain-function pytest style (no classes/fixtures beyond monkeypatch)."
  gotcha: "READ-ONLY."
- file: tests/test_zero_diff_rewind.py
  why: "The existing zero-diff characterization (3/3 at baseline) — re-run to prove untouched."
  gotcha: "READ-ONLY."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/
  bulk_delivery.py      # ← parallel P1.M3.T1.S1 (contracts; may not exist yet — TDD RED expected)
  bulk_controller.py    # ← CREATE (this task)
  streaming.py          # SEPARATED-FROM engine — read-only style ref, never imported
  typing_backends.py    # the forbidden surface
tests/
  test_bulk_delivery.py # ← parallel task's (re-run if present)
  test_bulk_controller.py  # ← CREATE (this task)
  test_zero_diff_rewind.py test_streaming_commit.py   # re-run: legacy untouched
```

### Desired Codebase tree

```bash
voice_typing/bulk_controller.py     # NEW — BulkController ordering core (pure stdlib + bulk_delivery)
tests/test_bulk_controller.py       # NEW — ~25 deterministic fake-target tests + purity guards
# NOTHING ELSE. No streaming/typing_backends/daemon/config/feedback edits (daemon wiring is P1.M6.T2).
```

### Known Gotchas

```python
# CRITICAL #1 — TDD RED UNTIL THE PARALLEL CONTRACTS LAND. bulk_delivery.py is being implemented in
#   parallel; until it exists, importing it raises ImportError → our suite is RED by design. Verify
#   with: ls voice_typing/bulk_delivery.py. NEVER vendor the enums/helpers to force green — wait or
#   re-check; the signatures are pinned in the parallel PRP (§ What + L3 probe).
# CRITICAL #2 — ENTRIES MUST BE NON-BLOCKING AND TARGET-FREE. on_partial/on_final/on_final_dropped/
#   arm may be called on the reader thread or under the daemon control lock (R.5). Under _cond they
#   do ONLY dict/deque ops; put-equivalents never block (bounded check → overflow STOP, not wait).
#   The ONLY target calls live on the writer thread's dispatch path (and acquire/stop, which are
#   daemon-lifecycle calls, not reader-thread calls).
# CRITICAL #3 — COALESCE = REPLACE-IN-PLACE, NOT drop-old-append-new. The queued partial keeps its
#   position so it always dispatches before its own utterance's final (ordering law). Scanning the
#   deque for the same (gen, utt) partial is fine (≤ queue_size items, tiny).
# CRITICAL #4 — OVERFLOW NEVER DROPS-AND-CONTINUES. The wrong implementations are (a) blocking
#   put() and (b) dropping the barrier and carrying on (ordering silently corrupted). Correct: STOP
#   delivery, record reason "queue-overflow", reject later events. Uniform for partials too.
# CRITICAL #5 — DOUBLE-CHECK AT MUTATION TIME. The writer re-checks gen + closed before dispatch
#   ("queued operations re-check at mutation time", R.5) — an arm() racing the writer must not let a
#   stale item through.
# CRITICAL #6 — ZERO-DIFF IS A *SKIP*, NOT A show() CALL. rendered_equal(_shown_span, span) → do not
#   call the target at all; count it (zero events is the assertion). Case/punctuation diffs are REAL
#   (rendered_equal never folds them — the contracts module's rule; do not re-normalize here).
# CRITICAL #7 — expected_revision ADVANCES ONLY ON APPLIED (+1). UNCHANGED = no edit landed = no
#   advance. Seed from AcquireResult.revision at acquire().
# CRITICAL #8 — NO RETRY, EVER, on REFUSED/UNKNOWN (an operation that may have landed must never be
#   repeated — R.5). Stop, record, fire on_stopped once. The 250 ms deadline + daemon disarm are
#   P1.M3.T2.S2's additions — leave the on_stopped callback seam (default None).
# CRITICAL #9 — PURITY IS TESTED. Mirror the contracts module's guards: no
#   type_text/press_backspace/make_backend/StreamingOutput attrs on the module; source-scan for
#   imports of voice_typing.streaming/typing_backends/daemon. (d2 §3.)
# CRITICAL #10 — DETERMINISTIC TESTS: drive dispatch via _process_next(blocking=False)/drain() (the
#   SAME handler the thread runs) — no sleeps, no waiting on threads. Exactly ONE test uses the real
#   thread (one-writer serialization) with a thread-aware fake.
# GOTCHA #11 — FULL TOOL PATHS (.venv/bin/python; zsh aliases); timeout 60 wrappers; mypy NOT
#   installed; ruff optional (/home/dustin/.local/bin/ruff).
```

## Implementation Blueprint

### Data models and structure

```python
# voice_typing/bulk_controller.py — stdlib (collections, dataclasses, threading, time, typing)
#   + voice_typing.bulk_delivery (DeliveryTarget, ShowResult, AcquireResult, rendered_equal)

@dataclass(slots=True)  # queue items (module-private)
class _SessionBegin: gen: int
class _Partial:       gen: int; utterance: str; seq: int; span: str
class _Final:         gen: int; utterance: str; seq: int; span: str
class _Boundary:      gen: int; utterance: str

class BulkController:          # full state + rules per research §2
    # state under self._cond: _dq (deque, bounded), _session_gen, _high_seq, _closed,
    # _shown_span, _expected_revision, _active, _stopped_reason, stats counters, _left flag
```

### Implementation Tasks (ordered)

```yaml
Task 1: PREFLIGHT — confirm inputs/style refs; accept TDD RED if the contracts are unlanded
  - RUN: ls voice_typing/bulk_delivery.py tests/test_bulk_delivery.py
      test ! -e voice_typing/bulk_controller.py && echo "ok: target absent"
      grep -n "class StreamingOutput" voice_typing/streaming.py
  - EXPECTED: bulk_delivery.py present or absent (absent → RED until parallel lands; proceed to write
    against the pinned signatures). Nothing else mutated.

Task 2: CREATE voice_typing/bulk_controller.py
  - Module docstring (Mode A): the R.5 laws verbatim-anchored (enqueue-and-return; one writer/one op
    in flight; newest-partial-wins; finals/boundaries are ordered barriers never overwritten; bounded
    queue default 32, overflow stops delivery rather than dropping a barrier; generation/seq/closed
    discards; dropped-final closes its boundary; zero-diff ⇒ zero events; REFUSED/UNKNOWN ⇒ stop,
    never retry). CONSUMES bulk_delivery; CONSUMED BY S2/T3/M6 wiring. No guards, no feedback, no
    backends (d2 §3).
  - Items + BulkController per research §2 EXACTLY: entries non-blocking under _cond; coalesce
    replace-in-place; barrier append; enqueue-side discards + overflow-stop; writer dispatch with
    mutation-time re-checks + zero-diff skip + taxonomy branch; acquire/stop (leave exactly once);
    stats(); the _process_next/drain test seams; on_stopped fired once.
  - FOLLOW pattern: streaming.py state-machine docstring + seams; audio_ducking.py purity.

Task 3: CREATE tests/test_bulk_controller.py (~25 tests, research §3 matrix, plain functions)
  - _FakeTarget (records (method, span, expected_revision) calls; per-call programmable result for
    the REFUSED/UNKNOWN/UNCHANGED tests; thread-id recording for the one-writer test) + a thin
    `_drained(ctrl, fake, events...)` helper.
  - Sections: A delivery traces (1-8) · B ordering invariants (9-23) · C purity guards (24-25).
  - Drive via ctrl.acquire(); ctrl.arm(gen); entries; ctrl.drain(); assert fake.calls + stats().
    NO sleeps. The overflow tests: do NOT start the writer (fill _dq by enqueuing queue_size items
    with the writer stopped, then assert the next enqueue stops delivery).

Task 4: VALIDATE — the Validation Loop below; iterate to green (RED-on-importError is the expected
  pre-parallel state). git status == the two new files. No commit unless directed.
```

### Implementation Patterns & Key Details

```python
# PATTERN — enqueue-and-return entry (reader-thread safe; Critical #2):
def on_partial(self, span, *, utterance, seq, gen):
    with self._cond:
        if not self._active or gen != self._session_gen: return          # stale gen
        key = (gen, utterance)
        if key in self._closed or seq <= self._high_seq.get(key, -1):    # late / dup
            self._stats["discarded_stale"] += 1; return
        self._high_seq[key] = seq
        if len(self._dq) >= self._queue_size:
            self._stop_locked("queue-overflow"); return                  # STOP, never drop (Critical #4)
        for i, it in enumerate(self._dq):                                # coalesce replace-in-place
            if isinstance(it, _Partial) and (it.gen, it.utterance) == key:
                self._dq[i] = _Partial(gen, utterance, seq, span)
                self._stats["coalesced"] += 1; self._cond.notify_all(); return
        self._dq.append(_Partial(gen, utterance, seq, span)); self._cond.notify_all()

# PATTERN — writer dispatch (mutation-time re-checks; zero-diff skip; taxonomy branch):
def _process_next(self, blocking=False, timeout=None) -> bool:
    with self._cond:
        while not self._dq and blocking and self._running:
            if not self._cond.wait(timeout or 1.0): ...
        if not self._dq or not self._active: return False
        item = self._dq.popleft()
        # re-check gen/closed for stale items (Critical #5) → discard counters, return True
    ...  # OUTSIDE _cond: at most ONE target call (one op in flight)
    if isinstance(item, _Partial):
        if rendered_equal(self._shown_span.get(key, ""), item.span):
            self._stats["zero_diff_skipped"] += 1; return True           # ZERO events (Critical #6)
        res = self._target.show(item.gen, item.utterance, item.seq, self._expected_revision, item.span)
    elif isinstance(item, _Final):
        res = self._target.finalize(item.gen, item.utterance, item.seq, self._expected_revision, item.span)
    ...  # _SessionBegin/_Boundary: state resets under _cond; no target call
    # branch: APPLIED → revision+1; UNCHANGED → continue; REFUSED/UNKNOWN → _stop(...) NO retry

# GOTCHA — the zero-diff comparison uses the LAST SHOWN span per utterance (updated on skip AND on
# dispatch), so an identical-after-UNCHANGED update still skips. Unicode spans flow verbatim (the
# controller never normalizes anything it passes to the target).
```

### Integration Points

```yaml
CONSUMED (contracts, from the parallel task):
  - voice_typing/bulk_delivery: "DeliveryTarget, ShowResult, AcquireResult, rendered_equal"
CONSUMED BY (future — zero wiring here):
  - P1.M3.T2.S2: "extends BulkController with the 250 ms deadline + disarm-on-unknown (hook:
    on_stopped callback; the op-in-flight call site is the deadline wrap point)"
  - P1.M3.T2.S3 (G2): "runs the extended fake-target trace matrix on this class"
  - P1.M3.T3.S2 + P1.M6.T2.S1: "daemon wiring: reader thread → on_partial/on_final/on_final_dropped;
    control thread → arm/stop; stats()/is_active() → delivery_state surface"
NO config keys, NO feedback fields, NO daemon/streaming/typing_backends changes (d2 §3).
```

## Validation Loop

### Level 1: Syntax + purity

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/bulk_controller.py tests/test_bulk_controller.py && echo OK
grep -nE 'import (voice_typing\.)?(streaming|typing_backends|daemon)' voice_typing/bulk_controller.py  # expect: no match
```

### Level 2: Unit suite (THE gate)

```bash
timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py -v
# Expected: all pass. ImportError on voice_typing.bulk_delivery → the parallel contracts have not
# landed; STOP and re-check (do not vendor) — they are the pinned contract.
```

### Level 3: Legacy untouched + contract co-existence

```bash
timeout 120 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_bulk_delivery.py \
  tests/test_zero_diff_rewind.py tests/test_streaming_commit.py -q
# Expected: 0 failed (test_bulk_delivery.py included when present).
```

### Level 4: Scope guard

```bash
git status --short   # expect exactly: ?? voice_typing/bulk_controller.py  ?? tests/test_bulk_controller.py
# Any M to streaming.py/typing_backends.py/daemon.py/config.py/feedback.py/bulk_delivery.py = VIOLATION
# (bulk_delivery.py belongs to the parallel task; never co-edit it).
```

## Final Validation Checklist

- [ ] L1–L4 green; the five item traces + every ordering invariant in the Success Criteria pass.
- [ ] Module docstring anchors the R.5 laws; purity guards shipped as tests (not prose).
- [ ] Only the two new files; no forbidden imports/attrs; no vendored contracts.
- [ ] Deterministic suite (no sleeps except none at all; drain()-driven) — re-run 3× stable.

## Anti-Patterns to Avoid

- ❌ Don't vendor the contracts module's enums/helpers to escape the parallel RED — import them (Critical #1).
- ❌ Don't let ANY entry method touch the target or block (Critical #2) — target calls live only on the writer dispatch path (+acquire/stop).
- ❌ Don't drop-old-append-new when coalescing — replace-in-place keeps the partial before its final (Critical #3).
- ❌ Don't respond to overflow with blocking put() or drop-and-continue — STOP (Critical #4).
- ❌ Don't skip the mutation-time re-checks (a racing arm() must not leak a stale item) (Critical #5).
- ❌ Don't implement the zero-diff skip as a show() returning UNCHANGED — it must be ZERO target calls (Critical #6).
- ❌ Don't retry on REFUSED/UNKNOWN, and don't bump expected_revision on UNCHANGED (Critical #7/#8).
- ❌ Don't add config keys / feedback fields / daemon wiring — T3/M6 own those (d2 §4).
- ❌ Don't run mypy (not installed); full paths + timeout wrappers (Gotcha #11).

---

**Confidence Score: 9/10** — the design is fully pinned (research §2: threading model, item kinds,
every discard/stop/revision rule), each law maps to a named test, the consumed signatures are quoted
from the parallel PRP, the repo's state-machine + purity precedents fix the style, and the drain()
seam makes the suite deterministic. −1: the parallel contracts module must land first (TDD RED window)
and its exact enum import names are taken from its PRP rather than landed code — both bounded by the
L2 gate.
