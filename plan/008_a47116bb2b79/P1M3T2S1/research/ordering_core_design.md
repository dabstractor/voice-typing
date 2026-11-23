# Research — P1.M3.T2.S1: Bulk-delivery ORDERING CORE design (bounded queue, barriers, one writer)

Verified against the live tree + the parallel contracts PRP (2026-11-23). Authoritative for the PRP.

## 0. Task nature + coordination

Implementation task (first controller code). Consumes the parallel **P1.M3.T1.S1** contracts module
`voice_typing/bulk_delivery.py` (NOT yet landed at research time — our tests are TDD RED until it is):
`ShowResult` (APPLIED/UNCHANGED/REFUSED/UNKNOWN, str-enum), `AcquireResult` (ok/handle/revision/reason),
`DeliveryTarget` Protocol (`acquire/show/finalize/leave/cancel`), `rendered_equal()`.
Produces the ordering core that **P1.M3.T2.S2** (failure handling: 250 ms deadline, disarm-on-unknown,
no retries) extends. Two NEW files: `voice_typing/bulk_controller.py` + `tests/test_bulk_controller.py`.

## 1. The R.5 ordering laws this core implements (PRD §4.2sexies R.5, verbatim-anchored)

| Law | Source | Consequence for the design |
|---|---|---|
| "RecorderHost._dispatch invokes _on_partial/on_final ON the reader thread: bulk mode MUST enqueue and return — no subprocess, editor wait, or display polling there or under the daemon control lock" | item RESEARCH NOTE / R.5 | Event entry methods touch ONLY the bounded structure (non-blocking); ALL target I/O happens on ONE dedicated writer thread |
| "One writer per target; one operation in flight" | R.5 | Single writer thread; at most one target.show/finalize call executing at any instant |
| "newest partial wins for the current utterance; superseded partials coalesce" | R.5 / item | Enqueue-side coalescing: a queued-but-undispatched partial for utterance U is REPLACED IN PLACE by a newer one (same U) — keeps its queue position (before U's final) |
| "finals and boundaries are ordered barriers, never overwritten" | R.5 / item | SESSION_BEGIN / FINAL / BOUNDARY items append to the tail and are never replaced/coalesced |
| "bounded queue, default 32; overflow stops delivery rather than dropping a barrier" | R.5 / item | ANY enqueue onto a full structure → delivery STOPS loudly (state + reason recorded, further events rejected). NOTHING is ever dropped-and-continued. Conservative by design (partials coalesce, so a full queue means the writer is stalled on barriers) |
| "New session generation at every arm" + "a late event keeps its own identity, never relabeled as newer" | R.5 | arm(gen) bumps the generation; events carry their OWN gen; gen≠current → discard at enqueue AND re-check at writer dispatch ("queued operations re-check at mutation time") |
| "Discard late post-final partials, duplicate finals, and canceled-utterance events" | R.5 | Per-utterance closed-set + per-utterance seq high-water mark |
| "a dropped or filtered final still closes its utterance boundary" | R.5 | Explicit `on_final_dropped(utterance, gen)` entry → BOUNDARY barrier (closes; NO finalize call) |
| zero-diff law "two strings that render identically ⇒ zero events" | R.1 | Controller-side skip: `rendered_equal(last_span, new_span)` → do NOT call the target at all (the unit test asserts ZERO target calls) |
| REFUSED/UNKNOWN "…disarms bulk delivery … NEVER retry an operation that may already have landed" | R.5 | Controller STOPS (is_active→False, reason recorded) on REFUSED/UNKNOWN; no retry. The daemon disarm + 250 ms deadline are S2's additions (seam: optional `on_stopped` callback, called once) |

## 2. Design (what the PRP pins)

### Threading model
- **Producers** (daemon reader thread via on_partial/on_final; control thread via arm/stop): take
  `self._cond`, run cheap dict checks (discards/coalesce), append to `self._dq` (collections.deque,
  bounded), notify. NEVER touch the target. NEVER block.
- **One writer thread** (`start()`): loops `_process_next(blocking=True)` — pops one item, re-checks
  gen/closed at mutation time, executes AT MOST ONE target call, updates expected_revision/stats.
  **One operation in flight** by construction.
- **Deterministic test seam**: tests do NOT start the thread; they call `_process_next(blocking=False)`
  / `drain(n)` directly (same handler → identical semantics, zero timing flakiness). One dedicated
  test starts the real thread to prove one-writer serialization.

### Queue items (private dataclasses/slots)
`_SESSION_BEGIN(gen)` — barrier · `_PARTIAL(gen, utt, seq, span)` — coalescible ·
`_FINAL(gen, utt, seq, span)` — barrier · `_BOUNDARY(gen, utt)` — barrier. Order within a deque:
a coalesced partial keeps its original position → always dispatched before its own utterance's final.

### State (all under `_cond`; single-writer for the target side)
- `_session_gen: int | None` — set by arm(); events with a different gen → discard.
- `_high_seq: dict[(gen, utt) -> int]` — per-utterance monotonic high-water; `seq <= high` → discard.
- `_closed: set[(gen, utt)]` — finals/boundaries close; late partials + duplicate finals → discard.
- `_expected_revision: int` — seeded from `AcquireResult.revision`; +1 ONLY on APPLIED (UNCHANGED
  leaves it — no edit landed). Passed to every show/finalize call.
- `_shown_span: dict[(gen, utt) -> str]` — the last span delivered/skipped per utterance; drives the
  zero-diff skip.
- `_active: bool`, `_stopped_reason: str | None`, stats counters (applied/unchanged/zero_diff_skipped/
  discarded_stale/discarded_dup/coalesced/overflow) — R.5: "New bulk-path logs carry counts and times".

### Dispatch rules (writer, per item — after mutation-time re-checks)
- `_PARTIAL`: if `rendered_equal(_shown_span[utt], span)` → zero-diff skip (NO target call; count it).
  Else `target.show(gen, utt, seq, expected_revision, span)` → branch on result.
- `_FINAL`: `target.finalize(gen, utt, seq, expected_revision, span)` → branch; utterance closes
  (closed-set already set at enqueue).
- `_SESSION_BEGIN`: reset per-generation maps (old-gen keys dropped); no target call.
- `_BOUNDARY`: no target call; closes the utterance.
- Result branch: APPLIED → revision+1, continue. UNCHANGED → continue. REFUSED/UNKNOWN → **stop**
  (`_active=False`, reason recorded, `on_stopped` fired once; remaining events discarded by the
  enqueue side; NO retry, NO further target calls).
- Overflow (any enqueue with `len(_dq) >= maxsize`): **stop** with reason `"queue-overflow"` — never
  drop-and-continue.

### Scope boundaries
- The controller does NOT run textproc guards (daemon wiring P1.M6.T2.S1 applies them BEFORE
  on_partial/on_final) and does NOT touch `_stream`/typing backends/feedback (d2 §3; delivery-state
  feedback keys are P1.M3.T3.S2's). It only orders + dedups + zero-diff-skips + tracks revisions.
- `stop()` calls `target.leave()` exactly once (leave = "no post-stop writes anywhere" — R.3).
- Purity: imports ONLY stdlib + `voice_typing.bulk_delivery` (guard-test enforced, same style as the
  contracts module).

## 3. Test matrix (~25, in-process `_FakeTarget`; deterministic via `drain()`)

**A. Delivery traces (the item's five + basics)** — FakeTarget records (method, span) calls:
1. append: first partial → exactly ONE show(span=text), APPLIED, revision+1
2. extend: "hello wor"→"hello world" → one show each (2 calls total), spans exact
3. first-word change: "Hello world"→"Help world" → ONE show with the NEW complete span
4. identical update → ZERO target calls (zero-diff skip counted)
5. render-equal whitespace variant ("a  b" vs "a b") → ZERO calls; case diff ("Hi"/"hi") → IS a call
6. retraction: "hello world"→"hello" → one show with the SHORTER span
7. Unicode: "naïve café 😀" spans byte/char exact through queue+dispatch (no normalization loss)
8. final → ONE finalize(span), utterance closed; APPLIED advances revision

**B. Ordering invariants**:
9. newest-wins: 3 partials same utt (seq 1..3) drained → ONE show, span == seq-3 text
10. coalesced partial keeps position: partial U1 + final U1 + partial U2 → dispatch order show(U1),
    finalize(U1), show(U2)
11. late post-final partial (seq <= final's) discarded
12. duplicate final discarded (one finalize)
13. stale-generation event discarded; current-gen flow unaffected
14. on_final_dropped → NO finalize; boundary closed (subsequent partial for that utt discarded)
15. overflow with barriers pending → STOP (is_active False, reason "queue-overflow"); nothing
    dropped-and-continued; further enqueues rejected
16. overflow on a partial also stops (conservative uniform rule)
17. REFUSED → stop, no retry (later events never reach the target)
18. UNKNOWN → stop, no retry
19. UNCHANGED → delivery continues, revision unchanged
20. expected_revision advances only on APPLIED (sequence: applied, unchanged, applied → r, r, r+1)
21. one-writer: real thread + FakeTarget(thread-aware) — every target call on ONE thread id,
    strictly serialized
22. arm(gen2) resets utterance state; gen-1 stragglers discarded after
23. stop() → leave() called exactly once; post-stop events never reach the target

**C. Purity**: 24. no forbidden attrs (type_text/press_backspace/make_backend/StreamingOutput) on the
module; 25. source-scan: no `voice_typing.streaming/typing_backends/daemon` imports.

## 4. Tooling / baseline (live)

- Run: `.venv/bin/python -m pytest tests/test_bulk_controller.py -v` (zsh aliases → full path;
  timeout 60 wrapper). Fake-target tests are pure + fast (<1 s).
- The contracts file `tests/test_bulk_delivery.py` + `tests/test_zero_diff_rewind.py` (3/3 at
  baseline) + `tests/test_streaming_commit.py` re-run in validation to prove the legacy path
  untouched. `bulk_delivery.py` NOT landed yet → RED until the parallel item lands (TDD, expected).
- mypy NOT installed; ruff optional (`/home/dustin/.local/bin/ruff`).
- Style refs: `voice_typing/streaming.py:180` StreamingOutput (state-machine docstring + clock
  injection + testable seams); `voice_typing/audio_ducking.py` (Protocol-module purity); test style
  = plain functions (test_textproc.py pattern).
