# Research — prompt partial dispatch + fail-closed bursts (P1.M2.T2.S1 / BUG-002)

The PRP (../PRP.md) is the runbook. This note pins the three code-verified defects, the
design, the test plan, and the boundaries.

## 1. The three defects (architecture/bulk_delivery_gate.md §2 "concrete edge cases" — ALL verified in the live code)

### A. Capacity is checked BEFORE same-key replacement (`on_partial`, ~:558-565)
Current order: `if len(self._dq) >= self._queue_size: stopped=_stop_locked("queue-overflow")…return`
runs BEFORE the `for i, item in enumerate(self._dq)` same-key replace-in-place scan.
So when the queue is FULL **and contains a replaceable partial for this exact
(gen, utterance)**, delivery wrongly stops — even though replacing that partial's own
slot is capacity-neutral. Under a burst of same-utterance partials (the R.1 workload)
a legal newest-wins coalesce becomes a spurious fail-closed stop. Fix: **try the
replace-in-place scan FIRST; only stop when at capacity AND no replaceable slot exists.**
Finals/`_SessionBegin`/`_Boundary` are barriers: append-only, overflow-stop stays
("never let a final erase a pending valid change" — a final must NOT replace a partial).

### B. Real-overflow returns skip the post-lock stop hook (`on_partial`, `on_final`, `on_final_dropped`)
All three overflow branches `return` **inside** `with self._cond:` — the trailing
`if stopped: self._fire_on_stopped()` (outside the lock) is unreachable on those paths.
`arm()` does it correctly: sets `ok = False`, falls out of the lock, then notifies.
Net: on the common overflow paths the one-time `on_stopped("queue-overflow")` never
fires. Fix: restructure all three to arm()'s fall-through shape (local flag → exit lock
→ notify → return). `_stop_locked` itself is correct (fires nothing; callers must
notify outside); `_fire_on_stopped` must remain outside `_cond` (a user callback must
never run under the lock).

### C. The generation re-check is MISSING at submit and result (`_process_next`, ~:712-720 & :756-758)
The module docstring (:196-197) promises an op result dies when "its captured epoch is
stale (or whose generation was superseded)" — but NEITHER the pre-submit critical
section (`if not self._active:`) NOR the result handler (`if epoch !=
self._dispatch_epoch or not self._active:`) checks `item.gen == self._session_gen`.
`arm()` does NOT bump `_dispatch_epoch` (only stops do) and keeps `_active=True`, so an
`arm()` racing the writer between pop and submit submits a STALE-GENERATION op whose
APPLIED result then bumps `_expected_revision` and overwrites `_confirmed_visible` —
session-global fields — for the NEW session. (This is the feasibility doc's "the
pre-submit check currently only checks active after leaving the first condition
critical section".) Fix: add `item.gen != self._session_gen` to BOTH the pre-submit
discard and the late-result discard. Everything else (epoch guard, active guard,
closure re-check, zero-diff, deadline, single-worker runner, `_note_late`) is correct
and MUST be preserved verbatim.

## 2. Promptness analysis (attribution-independent mandate)

The enqueue path is already wake-on-notify (`_cond.notify_all()` on enqueue;
`_writer_loop` → `_process_next(blocking=True, timeout=0.25)`); there is no intentional
debounce, and a queued partial is not replaced by its final (same-key only). The
measured 57-word backlog is therefore dominated UPSTREAM (the stabilized callback —
S6's diagnosis / S2's remediation), NOT by controller coalescing — the item's warning
"confirm stage attribution before calling coalescing the cause" is borne out. S1's job
is to make the controller **provably** prompt and burst-safe regardless of attribution:
(a) fix A removes the one controller behavior that DOES convert bursts into stops;
(b) pin "first useful partial dispatches before its final" with dedicated tests (the
existing suites assert coalescing and zero-diff, but not spaced-distinct-partial →
show-before-final ordering); (c) NO debounce timer may be introduced ("do not let a
timer defer the first useful partial"), and the writer cadence / queue_size /
op_deadline defaults are untouched ("do not slow the reader, increase queue/deadline to
mask lag, or add typing fallback").

## 3. Exact edit sites (bulk_controller.py, 920 lines at research time)

- `on_partial` (:532-569): reorder per §1A + restructure the overflow branch per §1B.
- `on_final` (:571-601): restructure the overflow branch per §1B (append-only unchanged).
- `on_final_dropped` (:603-622): same restructure (its `_Boundary` append-only).
- `_process_next` (:675-800): add the gen re-check at the pre-submit section and the
  result section per §1C. NOTE: `runner = self._ensure_runner()` sits BETWEEN the two
  critical sections — a test subclass overriding `_ensure_runner` is the deterministic
  hook for the arm-race (see §4).
- Module docstring (:46 "ANY enqueue onto a full queue stops delivery") + the two
  method docstrings: Mode A update for the refined invariants.

## 4. Test plan (existing files: tests/test_bulk_controller.py — `_FakeTarget` + `drain()` idiom, "no timing races, no sleeps"; tests/test_g2_bulk_gate.py — `_controller(fake,…)` helper, `_no_legacy_backend`, trace tests, QSIZE/DEADLINE consts)

1. `test_spaced_distinct_partials_show_before_final` (test_bulk_controller.py): partials
   "hello" → "hello world" → "hello world foo" (distinct renders), drain between each →
   each dispatches ONE show; then the final → ONE finalize; assert the fake's op log
   shows 3 shows BEFORE the finalize (ordering) and stats["applied"]==4.
2. `test_same_key_burst_at_capacity_coalesces_no_stop` (g2 or bulk_controller): fill the
   queue to `queue_size` with partials of ONE utterance, then enqueue MORE partials of
   the SAME utterance → every extra coalesces into the queued slot
   (stats["coalesced"] grows), `_active` stays True, NO "queue-overflow", on_stopped
   never fires. Pins §1A.
3. `test_real_overflow_stops_once_and_notifies_outside_lock`: fill the queue with
   non-replaceable items (barriers/finals, or distinct-utterance partials), enqueue one
   more → stops ONCE (reason "queue-overflow", on_stopped exactly once,
   stats["overflow"]==1). Outside-lock proof: the on_stopped callback itself calls a
   lock-taking controller method (e.g. `ctrl.stop(leave=False)`) from the callback —
   run in a helper thread with a bounded join; under the old in-lock-notify shape this
   deadlocks, with the fix it completes. Pins §1B.
4. `test_pre_submit_generation_race_discards_without_target_call`: subclass
   BulkController overriding `_ensure_runner` to first `self.arm(gen+1)` then delegate
   to super() (the deterministic between-sections hook); enqueue partial(gen1);
   `_process_next` → ZERO target calls (fake log empty), stats["discarded_stale"]≥1.
   Pins §1C pre-submit.
5. `test_stale_generation_inflight_result_never_mutates`: gated `_FakeTarget.show`
   (blocks on an Event); start `_process_next` on a thread; while the op is in flight
   `ctrl.arm(2)`; release the gate; the APPLIED result is discarded —
   `_expected_revision` unchanged, `_confirmed_visible` unchanged (not the gen-1 span).
   Pins §1C result-side (ack-only revision/confirmation preserved).
6. Writer-thread promptness (bounded, no bare sleeps): real `_writer_loop` running;
   feed 3 distinct partials; poll (deadline-bounded `_wait_for`-style loop) until the
   fake's show count reaches 3 BEFORE `on_final` is ever called; then final + bounded
   wait for the finalize. Guards against any future "wait for final" regression.
7. Re-run the EXISTING suites: any test that pinned the OLD capacity-before-replace
   order (a full-queue same-key burst expecting "queue-overflow") encoded the bug —
   flip its expectation to coalesced/no-stop with a comment; do NOT weaken any other
   assertion.

## 5. Boundaries

- Interfaces UNCHANGED: `on_partial/on_final/on_final_dropped/arm/stop/cancel/drain/
  halt_for_takeover` signatures intact → S2 (source remediation) and S3 (route
  qualification) consume as-is.
- No changes to: `_writer_loop` cadence, `queue_size`/`op_deadline` defaults, the
  single-worker runner, `_note_late`, zero-diff suppression, `rendered_equal`,
  `bulk_delivery.py` (DeliveryTarget/ShowResult untouched), the daemon/recorder relay,
  any typing backend. No typing fallback.
- S6 (parallel) produces the stage diagnosis; S1 is attribution-independent (the three
  defects are real regardless of which stage dominates the measured lag).
- Mode A docs ride in THIS task (module + method docstrings); the user-facing overview
  is P1.M2.T3.S2's.

## 6. Tooling

pytest under `timeout` (AGENTS.md): `timeout 300 .venv/bin/python -m pytest
tests/test_bulk_controller.py tests/test_g2_bulk_gate.py tests/test_bulk_dispatch.py -q`
(+ the wider fast sweep). Full paths (zsh aliases). ruff optional at
`/home/dustin/.local/bin/ruff`.
