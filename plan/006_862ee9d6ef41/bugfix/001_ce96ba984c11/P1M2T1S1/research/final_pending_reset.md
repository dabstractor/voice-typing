# Research: reset stale _final_pending on arm/disarm (P1.M2.T1.S1 / bugfix Issue 2)

Target: eliminate the spurious ~5 s drain on stop after a finalized utterance. Root cause:
`_final_pending` (the "utterance in flight" proxy) is set True by `_touch_speech()` on EVERY
realtime partial — including stray/tail-end partials after a final — and is cleared ONLY by
`on_final()`, NEVER by `_arm()`/`_disarm()`. So a stray partial leaves it stale True; the next
stop's `_request_stop()` sees `_text_in_flight and _final_pending` → drains the full
`_DRAIN_TIMEOUT_S = 5.0s` instead of disarming immediately (PRD §4.2 #2 violation). Fix: reset
`_final_pending = False` in `_arm()` + `_disarm()` (cross-session clean slate) + a regression test.

---

## 1. The _final_pending lifecycle (verified in daemon.py)

| Event | Site (daemon.py) | Effect |
|---|---|---|
| init | `__init__` :638 `self._final_pending: bool = False` | boot = False |
| set True | `_touch_speech()` :1059 `self._final_pending = True` | EVERY realtime partial (on_speech) |
| clear False | `on_final()` :973 `self._final_pending = False` | a final landed (utterance finalized) |
| drain check | `_request_stop()` :1084 `if self._host is not None and self._text_in_flight.is_set() and self._final_pending:` → `_begin_drain()` | True ⇒ 5 s drain; False ⇒ immediate disarm + abort |
| **reset in _arm()** | **MISSING** (the bug) | — |
| **reset in _disarm()** | **MISSING** (the bug) | — |

`_DRAIN_TIMEOUT_S = 5.0` (daemon.py:138). So a stale True + `_text_in_flight` True ⇒ a 5 s drain
with no final coming (no real speech) ⇒ the watchdog aborts at 5 s. PRD §4.2 #2: "If nothing is in
flight … it disarms immediately + aborts — responsive." The stale flag makes "nothing in flight"
look like "something in flight."

## 2. The fix (two one-line additions — verbatim anchors verified)

**`_arm()`** — add `self._final_pending = False` right after `self._listening.set()`. Anchor (unique
— `_listening.set()` is only in `_arm`):
```
        self._listening.set()
        self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh
```
→ insert the reset between those two lines. A fresh arm = no utterance in flight yet → clean slate.

**`_disarm()`** — add `self._final_pending = False` right after `self._listening.clear()`. Anchor
(unique — `_listening.clear()` is only in `_disarm`):
```
        self._listening.clear()
        self._last_speech_monotonic = None  # not listening → idle clock is inactive
```
→ insert the reset between those two lines. Defense in depth: a stray partial arriving around the
disarm doesn't leave it stale into the next stop/stop-check.

**Scope:** DO NOT modify `_touch_speech()`, `on_final()`, `_request_stop()`, `_begin_drain()`,
`_complete_drain()`, `_drain_timeout()` — they are correct. The minimal fix is the arm/disarm reset
(cross-session staleness). The within-session deeper fix (VAD-gated `_touch_speech`) is explicitly
out of scope ("a more thorough fix" per the bug report) — do NOT implement VAD detection.

## 3. Why the existing drain tests stay GREEN (verified)

The 6 existing drain/final_pending/stop_aborts/touch_speech tests + the 30 arm/disarm tests all
call `_touch_speech()` (or not) WITHIN the armed session, AFTER `_arm()`:
- `test_stop_drains_when_utterance_in_flight` / `test_toggle_off_drains_when_utterance_in_flight` /
  `test_drain_timeout_aborts_blocked_text`: `start()` → `_touch_speech()`. With the fix, `_arm()`
  resets `_final_pending=False`, then the explicit `_touch_speech()` re-sets it True → the drain
  STILL triggers correctly. ✓
- `test_stop_disarms_immediately_when_idle` / `test_stop_aborts_immediately_when_text_idle_no_speech`:
  never call `_touch_speech()` → `_final_pending` stays False (the `_arm()` reset is redundant but
  harmless) → immediate disarm. ✓
- `test_on_final_clears_final_pending`: `start()` → `_touch_speech()` (True) → `on_final()` (False).
  With the fix, `_arm()` resets False first, `_touch_speech()` re-sets True, `on_final()` clears. ✓

So the fix is purely ADDITIVE for these tests — none regress. (Baseline: 6 passed + 30 passed.)

## 4. The regression test (RED → GREEN) — the uncovered scenario

The existing `test_stop_aborts_immediately_when_text_idle_no_speech` MISSES the bug because it
manually sets `_text_in_flight` WITHOUT setting `_final_pending` (no `_touch_speech()`). The new
test(s) simulate the stray partial that sets `_final_pending=True` in production:

- **test_arm_resets_stale_final_pending_from_prior_session**: `start` → `_touch_speech` →
  `on_final("hello world")` (clears) → `_touch_speech` (STRAY → stale True) → `stop` → re-`start`
  → assert `_final_pending is False` (the `_arm()` reset). FAILS before the fix (still True).
- **test_disarm_clears_final_pending**: `start` → `_touch_speech` (True) → `stop` (→ `_disarm`) →
  assert `_final_pending is False` (the `_disarm()` reset). FAILS before the fix.
- **test_stop_after_stray_partial_in_fresh_session_disarms_immediately** (end-to-end drain proof):
  prior session with a stray partial → `stop` → re-`start` (clean slate) → `_text_in_flight.set()`
  → `stop` → assert immediate disarm (`_drain is False`, `rec.aborts == 1`, NOT a 5 s drain). FAILS
  before the fix (stale True ⇒ drain ⇒ `rec.aborts == 0`, `_drain is True`).

Placement: in the drain test block, after `test_on_final_clears_final_pending` (the last drain test
before the idle-auto-stop section). Reuses `_make_daemon()` (returns `(d, fb, rec, be)`;
`rec.aborts` counts aborts; `be.typed` records typed text) — hermetic, no external services.

## 5. Scope + parallel context

- **Files**: `voice_typing/daemon.py` (2 one-line additions: `_arm` + `_disarm`) + `tests/test_daemon.py`
  (3 new tests in the drain block). No other source, no config, no docs (Mode A: internal lifecycle
  fix; PRD §4.2 #2 already describes the intended immediate-stop behavior).
- **P1.M1.T1.S1 (parallel, Implementing)**: Issue 1 — fixes `_dispatch()` toggle/toggle-lite
  cross-mode-failure response routing + adds 2 dispatch tests. Touches `daemon.py _dispatch()` +
  `test_daemon.py` dispatch tests. **NO overlap** with `_arm()`/`_disarm()`/`_final_pending`/drain
  tests (different methods, different test section). Both edit daemon.py + test_daemon.py but in
  disjoint regions — no conflict.
- pytest>=9.1.1 (NO ruff/mypy). Full paths + functional `timeout` on every command (AGENTS.md).
  Validate: `timeout 120 .venv/bin/pytest tests/test_daemon.py -q -k 'drain or final_pending or
  stop_aborts or touch_speech'` (baseline 6 passed → 9 after adding 3) + `timeout 120 ... -k 'arm or
  disarm'` (baseline 30 passed).