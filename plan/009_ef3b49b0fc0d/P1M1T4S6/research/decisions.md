# P1.M1.T4.S6 — decisions (resolves `contract_chain.md` §F open questions)

Source of truth per question is quoted in `contract_chain.md` (A–D) and `prd_requirements.md`.
Each decision is what the PRP specifies; none contradicts a selected PRD section.

| # | Question | Decision | Why |
|---|---|---|---|
| 1 | Who owns the `finishing` / `ended` frames? (S5 assigns both to S6, its handoff tells S7's pump to emit `finishing`) | S6 **builds** `ended` (`NativeEndState.frame()`, exactly the 4 codec keys) and hands it to T4.S7 via the teardown callback; S7's `OwnerPump.send_event` **writes** it. `finishing` stays S7's (emitted on `_native_offer_evt` wake while DRAINING). | One writer per socket (PRD R.5 / system_context "no writes on daemon control lock"); no duplicate sends. |
| 2 | `recoverable` source: `NativeEndFacts.recoverable` (S4/S5) vs `recover(id)` (S1) | `recover(sid)` **after** `end_session` is the truth; facts are a cross-check only. | A fully-ACKed/empty ending is discarded (`end_session` docstring) → `drain_pending()` could still read True. |
| 3 | Wire code for a host death during STARTING (`load_failed` is not in the PRD's example list) | Emit `EndRecord.reason` verbatim — `editor_protocol.END_REASONS` includes `load_failed` and `validate_event` accepts it. No mapping invented. | PRD silent; codec (T3.S2 shared vectors) is the implemented vocabulary. |
| 4 | `ended` fields beyond the PRD's four; status field names; hint mapping; warning text | Frame = exactly `{event,id,reason,recoverable}`. Status gains `native: {state,id,reason,recoverable,hint}` with hint ∈ `none|recover|recover_maybe_applied`; `cancelled` is never recoverable unless `possibly_applied`. Desktop warning only for `disconnected`/`timeout` (transport gone). Fixed templates in the PRP. | PRD gives the frame, "transcript-free reason + recovery hint in status/log", and the notify-send fallback; the rest are additive codes with no text. |
| 5 | Teardown callback shape | One daemon-level hook `set_native_teardown(cb)`; `cb(NativeEndState)` fires exactly once, off-lock, after `on_end(EndRecord)` (unchanged, per-reservation) and after `end_session`. T5.S1 needs no new API. | `on_end`'s signature is pinned by T3.S4 tests; T5.S1 only needs the snapshot finalised before any reply. |
| 6 | Seed clear on end; buffers at exit; idle-unload vs live owner | Seed: call the existing best-effort `_clear_context_prompt()` off-lock (never write `_seed_*` flags). Exit: `_native_recovery.clear()` beside the generic clear in `request_shutdown` and after `terminate_native` in `shutdown()`. Idle-unload: `_unload_host` adds `or self._native_owner_live_locked()` to its under-lock condition (defer, never kill under a live owner). | system_context "On failure/end clear the prompt"; T4.S1 `clear()` "Daemon exit"; bounded session lifetimes make deferral cost seconds, while killing the child under a starting/draining owner is the race the item names. |

Notes
- `_flush_native_end` currently returns early when no `on_end` is registered — S6 restructures it so cleanup
  never depends on a callback.
- `test_status_snapshot_keys_and_cuda_values` (`tests/test_daemon.py:2211`) pins `set(s)` exactly → add `"native"`.
- `_handle_dead_host` already ends the owner off-lock (`load_failed` if STARTING else `disconnected`, cause
  `host-died`) and releases duck; S6 adds proofs and docstrings, not a second teardown path.
