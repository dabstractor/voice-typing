# P1.M6.T2.S2 research — Session recovery memory (R.6)

## 1. Contract inputs (verified this session)

### S1 PRP (plan/008_a47116bb2b79/P1M6T2S1/PRP.md) — lands BEFORE this item; consume, don't re-implement
- `daemon._bulk_handle_final(cleaned, raw, t_final_ready)` — bulk accepted-final path:
  identity gate (drop+count) → `if not cleaned:` rejected branch (`ctrl.on_final_dropped` + notify)
  → `ctrl.on_final(...)` → `self._feedback.record_final(cleaned)` → counts-only log. **S2 hooks
  `note_final(cleaned, key=(gen, uid))` after `record_final`; `note_rejected()` in the rejected branch.**
- `daemon._bulk_handle_partial(text)` — bulk partial path: identity gate → `ctrl.on_partial(...)`
  → `update_partial` → `note_partial`. **S2 hooks `note_tail(text)` after `ctrl.on_partial`.**
- `daemon._bulk_cancel()` — `ctrl.cancel(gen)` out of lock → shared under-lock recognition cancel
  (suppress latch + `host.cancel()`) + `_reset_stream_after_cancel()`. **S2 hooks `note_cancel()`
  after the under-lock block.**
- Lifecycle: `_arm()` bumps `_bulk_gen`/`_bulk_epoch`; `_disarm()` flips `_bulk_delivery_active`,
  schedules epoch-guarded stopper; `_on_bulk_stopped(reason)` fault path → `_disarm()`.
  Acquire failure (unsupported) leaves recording ARMED → session continues (not a "failed arm"
  for recovery). HALT/test-12 → `_disarm()`. All disarm paths funnel through `_disarm()` (its
  docstring: every disarm path).
- `tests/test_bulk_dispatch.py` (S1's new suite): bulk cfg fixture (delivery triple), FakeBundle
  wrapping G2FakeTarget, fake host + settable `relay_identity`, spy backend, `_make`-style daemon
  construction. **Reuse as the daemon-level test template.**

### BulkController (voice_typing/bulk_controller.py — CURRENT, landed)
- Three-value law accessors EXIST (R.5): `latest_recognized()` (:604, newest span RECEIVED,
  updated at enqueue), `accepted_final()` (:611, filter-accepted final or None),
  `confirmed_visible()` (:618, last APPLIED span only). All reset at `_reset_session_locked`
  (:775-790, on arm/stop). Thread-safe via `self._cond`.
- S1's persona names these as the S2/S3 consumption surface. Our design feeds the store from
  the same EVENTS the daemon dispatches (partial/final/cancel) instead of polling the controller
  at close — polling `confirmed_visible()` at close cannot distinguish "last utterance committed"
  from "unfinished tail" without extra state (accepted_final==confirmed comparison is lossy when
  a new partial happens to equal the last final). Event-fed pending_tail is exact.

## 2. Daemon site map (current HEAD pre-S1; S1 adds ~250 lines → re-grep live, Task 0)

| Site | Today | What's there | S2 hook |
|---|---|---|---|
| `on_final` | :1246 | listening gate :1248 → `_on_final_lock` :1257 → suppression window :1262-1359 (early-returns drop cancelled+racing finals) → `cleaned` :1360 → rejected block :1362-1403 (freeze tail + notify, both streaming and Rev1 funnel) → commit/type_text :1418-1449 → **`record_final(cleaned)` :1451** | `note_final(cleaned)` right after :1451 (post-gate ⇒ late/cancelled/rejected excluded by construction) |
| rejected block | :1362 | `if not cleaned:` — freeze, reset_boundary, notify, return | `note_rejected()` at block top (content no-op; explicit + testable) |
| `_on_partial` | :1684 | listening gate :1691 → `self._stream.on_partial(text)` :1697 → `note_partial` | `note_tail(self._stream.tail)` after :1697 (engine tail = VISIBLE text, guards applied; Rev1: tail stays "" → finals-only session) |
| `_disarm` | :1603 | clears listening/flags → `stream_reset()` (=reset_session, clears engine strings) → set_microphone(False) → duck release → phase idle | `close_session()` BEFORE the `stream_reset` block (pure memory; under `_lock` OK — never calls out) |
| `_arm` | :1541 | under `_lock`, bumps gen, host arm cmd | `open_session()` (cheap) |
| `cancel` legacy | :1938 | tail math → `press_backspace` → under-lock suppress latch + host.cancel → `_reset_stream_after_cancel()` :1980 | `note_cancel()` after :1980 |
| `request_shutdown` | :2341 | `_shutdown.set()` → duck release → drain timer clear → bounded teardown | `clear()` after the duck-release line |
| ctor | :661 | injection seams (:843-920 ducker/key-listener blocks) | `self._session_recovery = SessionRecovery()` |

StreamingOutput (streaming.py): `.committed` :287, `.tail` :292 (everything typed since last
checkpoint — post-commit tail is ""), `reset_session()` :387 clears both. Confirms tail = the
unfinished-utterance visible text, and why `close_session` need not read the engine at all
(pending_tail is event-fed).

## 3. Exclusion-rule → existing-gate mapping (the design's core claim)

| R.6 rule | Enforced by | Store-level test |
|---|---|---|
| accepted final exactly once per utterance | store closed-set dedupe on key=(gen,uid); stream-edit: single post-`record_final` funnel, one on_final per text() | dup-key note_final ×2 → 1 entry |
| rejected final retains only shown tail | hook after the `if not cleaned` return; `note_rejected` is a content no-op (pending_tail untouched) | note_tail("abc") → note_rejected → close → text has tail, no final |
| deliberate cancels excluded | suppression-window early-return precedes the hook (cancelled final never reaches store) + `note_cancel()` clears pending_tail | cancel → racing final → close → neither present |
| late finals excluded | listening gate at on_final top precedes the hook | disarm → on_final("late") → store unchanged |
| previous session survives empty/failed arms | empty draft discarded at close; drafts never touch the completed deque | close empty → latest unchanged |
| ≤2 sessions × 1 MiB | deque(maxlen=2); byte cap at close: drop OLDEST finals first (keep newest complete text that fits), hard-truncate a lone oversized item at codepoint boundary, truncated=True | oversized sessions |
| cleared at daemon exit | `clear()` in request_shutdown (the SIGTERM+quit funnel) | clear → latest None |

## 4. Decisions
- D1: NEW module `voice_typing/session_recovery.py` (pure python, no deps, own Lock, never
  calls back into daemon/feedback — deadlock-free by construction).
- D2: Feed from events, not polling (§1 rationale). Tail source: stream-edit = engine
  `.tail` (visible); bulk = partial text (recognized; confirmed lags by design — R.6 "visible/recognized").
- D3: `CompletedSession.text()` = `" ".join(finals + [tail])` — single spaces, no trailing
  space, NO added newline (R.6: S3 copies exactly this text).
- D4: Cap constants in code (`_MAX_SESSIONS=2`, `_MAX_SESSION_BYTES=1<<20`), NOT config. No new
  config keys (S1 G9 precedent; R.6 fixes the numbers).
- D5: No state.json / ctl.py / socket changes (R.5: state file never carries the document;
  S3 owns `voicectl session`). S2 exposes `daemon.session_snapshot()` (dict: text/truncated/
  counts/ended_ts) as the S3 contract point.
- D6: Close-time log = counts/times only: `session recovery: session completed finals=%d
  tail_chars=%d bytes=%d truncated=%d store=%d` — NEVER text (R.6 no transcript-bearing logs).
- D7: close_session under `_lock` is safe: pure memory + bounded string encode (≤ ~2 MiB worst
  case). open/note_* are O(1).
- D8: Bulk hooks are 1-3 line insertions INSIDE S1's `_bulk_*` method bodies (S2 lands after
  S1; the S1 PRP's anti-pattern list says S1 must NOT add recovery logic — the seam is ours).

## 5. Validation commands (verified shapes)
- `timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py -q`
- `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cancel or final or partial or arm or disarm"`
- `timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q` (S1's suite — compose check)
- G1 watch set identical before/after (test_streaming_commit/test_zero_diff_rewind/
  test_key_listener/test_control_socket/test_config) — stream-edit sites gain only post-statement
  lines; behavior byte-identical.
- Import purity: session_recovery must not import torch/RealtimeSTT/ctranslate2.
