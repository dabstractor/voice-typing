# Research — P1.M6.T3.S1: Bulk-mode prompt source decision + implementation

Verified live at HEAD (daemon.py = 3811 lines; line cites current this session — re-grep before editing).

## 1. The coupling (risk #7, d2_bulk_delivery_map.md §9 row 7)

- `_refresh_context_prompt` (daemon.py:2403) is the ONE prompt-push funnel. Gates:
  `cfg.asr.context_prompt` AND `self._context_prompt_active is True` (child ready flag), then
  defensive `host.set_prompt` getattr, never raises. Source selection (:2436-2440):
  `self._stream.committed if cfg.output.streaming else self._rev1_committed`.
- Bulk requires `streaming=true` (config precondition triple), so today's branch would pick
  `_stream.committed` — which the bulk path NEVER feeds (stays "" all session). Currently moot:
  `_bulk_handle_final` (:1951) RETURNS before the streaming block and its trailing comment says
  "NO prompt refresh ... the decoupling is P1.M6.T3.S1, out of scope here" (~:2025-2028).
  ⇒ In bulk mode NO prompt is pushed after commits today; the child decodes context-free after
  the arm-time clear. This item fixes exactly that.
- Map §9 row 7: "prompt source for bulk mode needs an explicit decision"; map §1 notes
  `_stream.committed` is "the existing committed-text source a bulk controller could mirror for
  its own last-confirmed state — read-only; do not couple". The landed controller instead keeps
  its OWN mirror: `confirmed_visible()`.

## 2. The source: BulkController.confirmed_visible() (bulk_controller.py:650)

- Three-value law value #3: "the last span the target CONFIRMED via an in-time APPLIED
  show/finalize". Thread-safe (under `_cond`). Updated ONLY at `_process_next`'s APPLIED branch
  (:773-776) — including PARTIAL shows, not just finalize.
- Per-utterance span (R.3 "complete rendered span"), NOT cumulative session text.
  `rolling_context_prompt()` then trims to the in-progress sentence — same semantics per
  boundary as stream-edit for the common case; a multi-utterance unpunctuated run conditions
  only on the newest confirmed utterance (accepted divergence; noted in the decision comment).
- `_reset_session_locked` (arm time) clears it ⇒ no cross-session bleed controller-side.
- `stop()`/fault RETAINS the three values ("retains recoverable recognition") — after a fault,
  `is_active()` is False so our trigger sites never fire; stale value never pushed.
- `cancel()` APPLIED branch (:483-487) does NOT update `_confirmed_visible` — after cancelling
  utterance N it transiently holds N's last applied show span (removed from the field). Leak
  window: only if a later accepted final had ZERO shows of its own (enqueue push would read the
  stale fragment). Closed by the post-cancel clear (D4).
- UNCHANGED finalize: `_confirmed_visible` NOT updated, and `on_applied` does NOT fire
  (APPLIED only) ⇒ a finalize-APPLIED-only trigger would MISS the common
  stabilized-partial-equals-final case and fall an utterance behind forever. ⇒ enqueue-time
  trigger (D2) is REQUIRED; at enqueue, confirmed_visible = this utterance's last APPLIED show
  span, which renders equal to the final exactly when the finalize will be UNCHANGED.

## 3. Trigger sites (all pre-existing seams; daemon-only changes)

- **A (enqueue)**: `_bulk_handle_final` accepted path, right after `ctrl.on_final(...)` (~:1987),
  inside the existing `if ctrl is not None and ctrl.is_active():` guard. Reader thread;
  `_refresh_context_prompt` is non-blocking (queue put) — enqueue-and-return law preserved.
- **B (finalize-APPLIED)**: `_on_bulk_applied` (:2153) — add `if kind == "finalize":` refresh
  after the record_confirmed_op block (own try/except). Fires on the writer thread, OUTSIDE
  `_cond` (controller contract), AFTER `_confirmed_visible` was set ⇒ reads the exact final
  span. Corrects the context when the finalize revised the visible text. `kind == "show"` must
  NOT push (mid-utterance self-conditioning; the executor sets condition_on_previous_text=False
  precisely because the daemon owns cross-utterance context).
- **D4 (cancel clear)**: `_bulk_cancel` (~:2196) — after `ctrl.cancel(gen)`, push `set_prompt("")`
  through the same gates. Stream-edit keeps pre-cancel context (committed unchanged); bulk has
  no cumulative mirror, so context-free is the conservative degrade (PRD degrade philosophy) and
  guarantees a cancelled fragment can never become decode context.
- Arm-time clear already exists and is mode-agnostic: `_arm` (:1742-1755) queues `set_prompt("")`
  BEFORE `set_microphone(True)` (FIFO pinned by test_context_prompt_refresh.py) ⇒ warm re-arm
  never conditions on the previous session — works for bulk unchanged.

## 4. Timing safety (why A+B are both timely and never race a decode)

Child reads ("prompt", …) cmds BETWEEN utterances (recorder_host.py:636); `set_prompt` = mp-queue
put (recorder_host.py:304, non-blocking). Silence gate (0.8 s) elapses before the final fires;
finalize applies ≤250 ms (typically ~40 ms); next utterance's first partial decode needs speech
+ ~0.15 s cadence ⇒ both pushes land before the next decode. Pushes during an utterance are
harmless (applied at the next boundary). Refused/deadlined finalize ⇒ fault ⇒ disarm ⇒ no next
utterance (early push moot).

## 5. Thread/lock audit for the new calls

- `_refresh_context_prompt` takes NO daemon locks; reads cfg/flags/`_bulk_ctrl`/`_host`; never
  raises. Safe on reader thread (already called there in stream-edit), writer thread (B), and
  the cancel caller's thread (control socket / evdev — D4).
- `_on_bulk_applied` is exception-wrapped by the controller (a failure can't kill the writer).
- Bulk law "never call ctrl.* under self._lock": D4's refresh happens AFTER the out-of-lock
  `ctrl.cancel(gen)` — `_refresh_context_prompt` itself calls no ctrl mutators (confirmed_visible
  is a read; not even needed for the clear).

## 6. Test landscape

- `tests/test_context_prompt_refresh.py` — the both-modes regression anchor (stream-edit pins:
  commit pushes, arm-clear FIFO, config-off → zero pushes + "disabled" label, degraded child →
  zero pushes + label, Rev 1 accumulator, no-set_prompt host no-op, raising set_prompt
  swallowed, rejected final no push). `_FakeHost` records prompts (:137), ready payload
  `context_prompt` flag (:110-117), `_make_daemon` (:159).
- `tests/test_bulk_dispatch.py` — the bulk-side doubles to mirror: `_FakeHost` :139 (relay_identity),
  `_FakeTarget` :197, `_FakeBundle` :246, `_make_bulk_daemon` :314 (cfg satisfies the delivery
  precondition triple), `_wait_until` :368. Real `BulkController` over `_FakeTarget` ⇒ the writer
  thread drains asynchronously; drive deterministically via `ctrl.drain()` or `_wait_until`.
- `tests/test_prompt_engine.py` pins `rolling_context_prompt` itself (pure) — no changes needed.
- Must stay green untouched: test_bulk_dispatch, test_bulk_controller, test_g2_bulk_gate,
  test_context_prompt_refresh, test_streaming_commit, test_zero_diff_rewind (G1 watch set).

## 7. Parallel-item conflict check

- P1.M6.T2.S3 (implementing in parallel): daemon.py `session_reply()` + `ControlServer._dispatch`
  branch + ctl.py + its own tests. ZERO overlap with :1951/:2153/:2196/:2403 sites. Its PRP warns
  its daemon cites are pre-S2 — re-grep live (Task 0) regardless.
- P1.M6.T2.S1 (INPUT, landed): the dispatch wiring, `_on_bulk_applied`, `_bulk_cancel`,
  `_bulk_wired` — all consumed as-is; this item adds the prompt calls at those sites.
