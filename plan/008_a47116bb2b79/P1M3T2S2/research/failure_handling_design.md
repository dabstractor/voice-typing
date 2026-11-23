# Research — P1.M3.T2.S2: failure handling in BulkController (250 ms deadline, disarm-on-unknown, no retries)

Ground truth: the LANDED `voice_typing/bulk_delivery.py` (contracts, P1.M3.T1.S1 Complete), the S1 PRP
(`plan/008_a47116bb2b79/P1M3T2S1/PRP.md` + `research/ordering_core_design.md` — the ordering core,
IN PARALLEL, treated as CONTRACT), `architecture/d2_bulk_delivery_map.md` §3, PRD §4.2sexies R.5.
Verified 2026-11-23. `bulk_controller.py` does NOT exist yet (S1 in flight) — S2 EXTENDS it once landed.

---

## 0. What S1 (the INPUT) provides — assume it lands EXACTLY as its PRP specifies

`voice_typing/bulk_controller.py` — `class BulkController(target, *, queue_size=32, on_stopped=None)`:
- API: `acquire()/start()/stop(*, leave=True)/arm(gen)/on_partial(span,*,utterance,seq,gen)/
  on_final(...)/on_final_dropped(*,utterance,gen)/is_active()/stats()/_process_next(blocking=False,
  timeout=None)/drain(max_items=None)`.
- State (under `_cond`): `_session_gen`, `_high_seq[(gen,utt)]`, `_closed` set, `_expected_revision`
  (seeded from AcquireResult.revision; +1 ONLY on APPLIED), `_shown_span[(gen,utt)]`, `_active`,
  `_stopped_reason`, stats counters.
- Writer dispatch (one thread; one op in flight): `_PARTIAL` → zero-diff skip via `rendered_equal` or
  ONE `target.show(gen,utt,seq,_expected_revision,span)`; `_FINAL` → ONE `target.finalize(...)`; barriers
  → state only. Result branch: APPLIED → revision+1; UNCHANGED → continue; **REFUSED/UNKNOWN → stop**
  (`_active=False`, reason recorded, `on_stopped` fired once, NO retry, no further target calls);
  overflow → stop `"queue-overflow"`.
- **The seam left for THIS task** (S1 PRP verbatim): "NO RETRY, EVER, on REFUSED/UNKNOWN... The 250 ms
  deadline + daemon disarm are **P1.M3.T2.S2's additions** — leave the `on_stopped` callback seam
  (default None)."
- Purity law (d2 §3): imports ONLY stdlib + `voice_typing.bulk_delivery`; NEVER
  `type_text`/`press_backspace`/`make_backend`/`StreamingOutput.*`; never import
  streaming/typing_backends/daemon. Guard-tested.
- Tests: `tests/test_bulk_controller.py`, deterministic via `_process_next(blocking=False)/drain()`
  (same handler the thread runs); ONE real-thread test (one-writer). ~25 tests.

Contracts consumed (landed, `voice_typing/bulk_delivery.py`): `ShowResult` (APPLIED="applied",
UNCHANGED="unchanged", REFUSED="refused", UNKNOWN="unknown"; str-enum), `AcquireResult(ok,handle,
revision,reason)`, `DeliveryTarget` Protocol (`acquire/show/finalize/leave/cancel`; show/finalize take
`(session,utterance,seq,expected_revision,span)`), `rendered_equal`. Docstring pins: "refused and
unknown DISARM delivery — and an operation whose outcome is unknown is NEVER retried (R.5)".

---

## 1. The R.5 failure contract (PRD §4.2sexies R.5, operative lines)

- "Any `unknown`/`refused`/stalled operation (**250 ms engineering deadline**) disarms bulk delivery
  AND recording, retains recoverable recognition, and reports one concise reason via status and the
  configured fault surface."
- "**NEVER retry an operation that may already have landed.**"
- "**Validate deadlines in the RECEIVER so a late operation cannot mutate after the daemon has given
  up.**"
- "Bytes sent is not 'applied'; 'unknown' is not 'delivered'" (R.3).
- Three-value law: "Keep three values distinct: latest recognized text; filter-accepted final; last
  target-CONFIRMED visible text."
- G2 trace list (the failure half is THIS task's unit tests): "timeout-after-apply; held key;
  out-of-order results; stop + immediate re-arm; child death; focus change mid-operation."

## 2. Design (extends S1's class; pinned)

### 2.1 The deadline (stalled ops)
- Ctor kwarg `op_deadline: float = 0.25` (the 250 ms **engineering deadline** — a code constant, NOT
  config; R.5 wording. Config surface belongs to P1.M3.T3.S1; tests inject 0.01–0.05).
- The writer's single target call per item runs through a **single-worker op runner**
  (`concurrent.futures.ThreadPoolExecutor(max_workers=1)`, daemon threads, created in `start()`):
  `future = runner.submit(fn, *args)`; `future.result(timeout=self._op_deadline)`.
  - Result in time → the S1 result branch unchanged.
  - `concurrent.futures.TimeoutError` → **give-up**: the op is outcome-UNKNOWN (it may still land in
    the field — timeout-after-apply) → `_stop(reason="op-deadline")`, NO retry (never resubmit), the
    abandoned future is left to finish into the discard path (§2.2).
- `stop()` shuts the runner down (`shutdown(wait=False)`) so a re-`start()` gets a FRESH runner; at
  most one abandoned future ever exists per runner (after a give-up we stop dispatching — no second
  submit), which keeps "one operation in flight" true by construction.

### 2.2 Receiver-side late-result validation (THE give-up law)
- `self._dispatch_epoch: int` (starts 0; under `_cond`) increments on EVERY give-up/stop.
- The dispatch captures `epoch = self._dispatch_epoch` BEFORE submitting. `future.add_done_callback`
  checks: if `epoch != self._dispatch_epoch` (or not `_active`) → the result is LATE → **discard**
  (count `late_results_discarded`; NEVER bump revision, NEVER update `_shown_span`/`_confirmed_visible`,
  never call the target again) — "a late operation cannot mutate after give-up". The in-time path
  applies the result only through the same epoch check (so a stop racing the result loses cleanly).
- This also covers **out-of-order results**: the only stale future possible is one abandoned by a
  give-up/stop; its late APPLIED must not touch the NEW session after a re-arm (epoch+gen mismatch).

### 2.3 Target exceptions = child death
- `future.result()` re-raises target exceptions (ConnectionError/OSError/ProcessLookupError — adapter
  subprocess dead — or any Exception). Catch in dispatch → outcome unverifiable → treated as UNKNOWN:
  `_stop(reason="target-error")` (stats carry the exception NAME; the reason string stays ONE concise
  word per R.5). Never propagates out of `_process_next`; no retry. `stop()`'s `target.leave()` call is
  wrapped best-effort (a dead target's leave raising must not mask the original reason; count it).

### 2.4 Stop reasons (single `_stopped_reason`, one concise reason; fired via `on_stopped` ONCE)
`"queue-overflow"` (S1) · `"op-deadline"` (250 ms stall) · `"refused"` (target REFUSED — focus change,
held key) · `"unknown"` (explicit UNKNOWN result) · `"target-error"` (exception/child death). S2 maps
S1's raw REFUSED/UNKNOWN branch to these; `stats()` gains `stop_reason`, `stopped_at_ms`, fault counters
(`ops_applied/unchanged/zero_diff_skipped/deadline_exceeded/target_errors/late_results_discarded` —
"counts and times, not recognition text"). The DAEMON disarm (bulk + recording) consumes `on_stopped` —
wiring is P1.M6.T2.S1; THIS task makes the controller failure-complete: reason + callback + retention.

### 2.5 Three distinct values (the three-value law) + retention
- `_latest_recognized: str` — newest recognition span RECEIVED (partial or final), updated at ENQUEUE
  (before dispatch/confirmation).
- `_accepted_final: str | None` — the last FILTER-ACCEPTED final (the daemon applies textproc gates
  BEFORE entry — d2/S1 scope note — so `on_final` IS the accepted final).
- `_confirmed_visible: str` — the last span the target CONFIRMED via an APPLIED show/finalize (updated
  ONLY on APPLIED, in-time, epoch-checked; NEVER on UNCHANGED/late/unknown).
- Accessors `latest_recognized()/accepted_final()/confirmed_visible()`; all three retained (not
  erased) across a failure stop until the next `acquire()`/`arm(gen)` — "retains recoverable
  recognition" (recovery surfacing/session memory is P1.M6.T2.S2; here: retained + queryable).

### 2.6 Scope boundaries
- NO daemon/feedback/config edits (daemon disarm wiring P1.M6.T2.S1; delivery_state/reason surface
  P1.M3.T3.S2; session recovery P1.M6.T2.S2). NO textproc (daemon applies pre-entry). Purity law
  unchanged. Only `voice_typing/bulk_controller.py` + `tests/test_bulk_controller.py` change.

## 3. Test matrix (APPEND to tests/test_bulk_controller.py; deterministic, bounded waits)

Fakes: extend S1's `_FakeTarget` with block-on-Event show() (`_gate`), delayed-result, raising, and
refusing variants. `op_deadline=0.02` in tests; `Event.wait(1.0)` bounds everything (no bare sleeps).

1. **timeout-after-apply** → gate never opens → dispatch returns; `is_active()` False, reason
   `"op-deadline"`, exactly ONE target call (no retry); then open the gate (the op DID apply in the
   fake's field) → late APPLIED is DISCARDED: revision unchanged, `confirmed_visible()` unchanged,
   `late_results_discarded` +1. (The core R.5 give-up law.)
2. **late result after stop** (epoch, direct): give-up on op A, `stop()`, re-`acquire()+arm(gen2)`,
   then A's future completes APPLIED → new session's revision/state untouched (out-of-order across
   re-arm).
3. **held key** → fake returns REFUSED (reason key-held) → stop `"refused"`, `on_stopped` once, no
   retry, recognition retained.
4. **focus change mid-operation** → op in flight returns REFUSED (mutation-time refusal) → same stop
   path; a QUEUED second op never reaches the target (post-stop).
5. **child death** → fake's show raises ConnectionError → stop `"target-error"`, exception name in
   stats, no raise out of `_process_next`, no retry; `stop()`'s leave() on the dead target doesn't
   raise.
6. **stop + immediate re-arm** → stop() → leave() exactly once → acquire() → arm(gen2) → a gen-2
   partial flows and APPLIES; gen-1 straggler discarded (S1 discard + epoch).
7. **explicit UNKNOWN** (adapter returns ShowResult.UNKNOWN) → stop `"unknown"`, no retry (S1 pinned
   the branch; S2 pins the REASON + retention + no-second-call).
8. **three values distinct** (the law): enqueue partial P (latest=P) without dispatching →
   latest_recognized==P, confirmed_visible==""; dispatch APPLIED → confirmed==P; enqueue final F
   (accepted_final==F) undispatched → all three differ simultaneously (P vs F vs P→ then dispatch F).
9. **recognition retained after failure stop**: after test-1's stop, all three accessors still return
   their last values (nothing erased).
10. **fast ops unaffected**: with a normal instant fake, the deadline never fires; full happy-path
    flow still green (S1 tests re-run prove this too).
11. **on_stopped exactly once** with ONE concise reason across double-give-up attempts (no refire on
    later stop()).
12. **no-retry structural**: after any failure stop, `drain()`/`_process_next` make ZERO target calls.
13. **purity guards** (S1's) still pass after the edit (re-run).

## 4. Tooling / baseline
`.venv/bin/python -m pytest` under `timeout 60`; mypy NOT installed; ruff optional
(/home/dustin/.local/bin/ruff). S1 is IN PARALLEL → `bulk_controller.py` may not exist yet: our
appended tests are TDD RED until it lands (verify `ls voice_typing/bulk_controller.py`; NEVER vendor
S1's class). Re-run legacy: `tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py
tests/test_streaming_commit.py` (0 NEW failures; G1 baseline had 10 streaming_commit reds — pre-existing).
