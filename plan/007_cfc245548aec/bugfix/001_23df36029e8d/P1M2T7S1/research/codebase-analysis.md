# Research Notes — P1.M2.T7.S1 (BUG-007: clear `_final_pending` when the cancelled sentinel is consumed)

## Verified current code state (post P1.M1, pre this fix)

All line numbers verified by direct read of the working tree on research day. The PRD's
line refs (daemon.py:1132-1137, :1165) are stale relative to landed P1.M1 fixes — use these:

- `_DRAIN_TIMEOUT_S: float = 5.0` — daemon.py:149
- `on_final()` def — daemon.py:~1104; first line is the `is_listening()` gate
- The `_cancel_suppress_final` suppression branch — daemon.py:~1132-1139:
  ```python
  if self._cancel_suppress_final:
      consume = getattr(self._host, "consume_cancel_mark", None)
      if callable(consume) and consume():
          self._cancel_suppress_final = (
              False  # sentinel seen; pipeline re-armed
          )
      return  # dropped: no clean, no type_text, no record_final
  ```
  **BUG**: the `return` fires with `_final_pending` still True and `_utterance_finalized`
  still False. The other two on_final exits (rejected-final ~:1158, clean final ~:1176)
  BOTH clear `_final_pending` and set `_utterance_finalized=True`.
- `_touch_speech()` — daemon.py:~1370-1396: calls `self._stream.resume()` (BUG-001/002
  lift point, MUST stay before the guard), then `if not self._utterance_finalized:
  self._final_pending = True`.
- `_request_stop()` — daemon.py:~1416-1441: drains iff
  `self._host is not None and self._text_in_flight.is_set() and self._final_pending`;
  else immediate `_disarm()` + `_safe_abort()`.
- Run loop — daemon.py:~1027-1033: on each (re-)entry into `text()`:
  `self._utterance_finalized = False; self._text_in_flight.set(); try: host.text(on_final)
  finally: self._text_in_flight.clear()`. Drain completion (`_complete_drain`) is checked
  BEFORE the listening re-entry.
- `cancel()` — daemon.py:~1636-1666: under `_lock`; backspace compensation; when
  `_text_in_flight.is_set() and self._host is not None` sets `_cancel_suppress_final=True`
  and calls `host.cancel()`; then `_reset_stream_after_cancel()`.
- `_begin_drain` / `_complete_drain` / `_drain_timeout` — daemon.py:~1668-1727.
  `_drain_timeout` also calls `_freeze_stranded_tail(...)` (session-class freeze) before
  `_safe_abort()` — post-fix this path is unreachable from stop-after-cancel (tail is
  empty after cancel anyway, so it was a no-op there, but worth noting).
- `_arm()` (daemon.py:~1268-1283) and `_disarm()` (daemon.py:~1338-1345) both already
  clear `_final_pending` + `_utterance_finalized` (defense in depth; out of the bug window).

## Sentinel machinery (recorder_host.py)

- `RecorderHost.cancel()` (:286-301): sets `_cancel_event` THEN `_abort_event`.
- Child abort-handler thread polls both; a cancel unblocks `text()` AND discards buffered
  audio (`_clear_recorder_audio`) and emits `("final", {"text": "", "cancelled": True})`.
- Host reader thread sets `self._cancel_mark = bool(payload.get("cancelled"))` (:436)
  just before relaying that final to the daemon's `on_final` on its reader thread.
- `consume_cancel_mark()` (:307-317): read-and-clear; per-event semantics (a plain final
  resets the mark to False).
- Legacy `_LegacyRecorderHostAdapter` (plain `recorder=` injection) has NO cancel surface:
  `getattr(self._host, "cancel", None)` → None → `_cancel_suppress_final` never armed
  there; the sentinel branch is host-path-only. Legacy stop-after-cancel behavior is
  pre-existing and OUT OF SCOPE.

## Threading / race analysis for the fix

- `on_final` runs on the host reader thread under `self._on_final_lock` (separate from
  `_lock`); the suppression branch is inside that lock. Plain bool stores are atomic in
  CPython; each writer owns the full transition (same style as `_cancel_suppress_final`
  itself, per the __init__ comment at daemon.py:~654-661).
- Setting `_utterance_finalized=True` on sentinel consumption is REQUIRED, not optional:
  without it, a stray late 'speech'/partial of the cancelled utterance arriving between
  the sentinel and the run loop's re-entry into `text()` re-arms `_final_pending=True`
  (validation Issue 2 semantics — exactly the residual this mirrors for the other two
  on_final exits). The run loop re-entry (`_utterance_finalized = False`) re-enables
  re-arming for genuinely-new speech within one loop iteration (~ms), so a stop
  mid-re-said-utterance still drains. No regression window of practical size.
- Alternative "clear `_final_pending` inside `cancel()`" was REJECTED: at cancel() time
  the sentinel hasn't arrived; stray partials/'speech' events of the dying utterance
  would re-arm the flag before the sentinel lands, recreating the stale drain. The
  sentinel consumption is the single authoritative "cancelled utterance bookended" event.

## Test infrastructure (tests/test_daemon.py — fast, CUDA-free, no threads)

- `_make_daemon(...)` (:682) — legacy-recorder doubles (`_StubRecorder`, `_FakeBackend`,
  `_DaemonFakeFeedback`, `_ok_probe`).
- `_FakeHost` (:560-645) — mirrors real RecorderHost incl. `cancel()` (records +
  rides abort), `consume_cancel_mark()` (read-and-clear of `_cancel_mark`), and the
  TEST SEAM `mark_cancel_sentinel()` (simulates the reader thread having just marked
  the relayed final).
- `_make_cancel_daemon()` (:4451) — armed daemon + resident `_FakeHost` +
  `_text_in_flight` set; tests drive `cancel()`/`on_final()`/`_touch_speech()` directly.
- Existing adjacent tests to keep green:
  - `test_stop_drains_when_utterance_in_flight` (:765), `test_drain_timeout_aborts_blocked_text` (:815),
    `test_on_final_clears_final_pending` (:828), `test_stop_within_session...` (:896, :929)
  - `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` (:4526)
  - `test_cancel_then_next_utterance_streams_live_daemon_level` (:4589) — its docstring
    explicitly notes "P1.M2.T7.S1 will extend the same suppression branch
    (stop-after-cancel) — it must keep this test green."
- Tooling: pytest only (no ruff/mypy configured). `uv run pytest tests/test_daemon.py -q`.
  AGENTS.md mandates inner `timeout` + bash-tool timeout on every non-trivial command;
  test_daemon.py is doubles-only (fast), but always wrap anyway.

## Bug repro sequence (daemon-level, doubles only)

```python
d, _fb = _make_cancel_daemon()      # armed, _text_in_flight set, resident _FakeHost
d._touch_speech()                   # _final_pending = True (utterance in flight)
d.cancel()                          # suppression armed, host.cancel() called
d._host.mark_cancel_sentinel()      # reader marked the sentinel final
d.on_final("")                      # sentinel consumed: window closes...
assert d._final_pending is False    # ...BUT still True before the fix (BUG-007)
d.stop()                            # pre-fix: _begin_drain() -> ~5s hang; post-fix: immediate
```
