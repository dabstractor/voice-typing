# Research Note — P1.M1.T2.S2: lift post-cancel suppression at next utterance start (daemon)

BUG-002's daemon half. All sites verified against the live tree (S1's engine edits visible in-tree).

## 1. THE HEADLINE: the wiring ALREADY LANDED (T1.S2) — this task is verify + regression test

- `daemon.py:1365 _touch_speech()` → `self._stream.resume()` at **:1389**, with the rationale comment
  **:1382-1388**: "BUG-001 / P1.M1.T1.S2: genuinely-new speech lifts a rejected-final freeze (and **any
  post-cancel suppression, via the engine's resume()**) so the NEW utterance streams live. Idempotent, no
  keystrokes... Must run BEFORE the _final_pending guard... A stray late partial of the rejected
  utterance never reaches this hook — it arrives via _on_partial."
- **ONE wiring point confirmed** (the contract's "pick ONE"): the on_final suppression branch
  (:1131-1138) consumes the sentinel via `host.consume_cancel_mark()` and does NOT call resume() —
  `_touch_speech` is the sole lift point, and the comment records why (speech-start = genuinely-new
  utterance; stray late partials route via _on_partial and never reach the hook, so suppression correctly
  holds for THEM until real speech). The contract's preferred option ("from _touch_speech() — fires on
  real speech start") is what landed.
- The engine seam (S1, in-flight/visible): `streaming.py:274 resume()` clears `_suppressed` ALWAYS
  (:296; docstring :282 cites "P1.M1.T2.S1 / BUG-002 reuses exactly this"). S1's own PRP confirms:
  "T1.S2... _touch_speech() calls self._stream.resume()... **T2.S2 reduces to its regression test**."

⇒ Expected SOURCE delta for T2.S2: ZERO-to-minimal (verify the comment covers the BUG-002 rationale —
it does; strengthen only if a line is missing). The deliverable is the daemon-level regression test.

## 2. The cancel flow (verified, for the test's faithfulness)

`cancel()` (**:1621-1655**, under `_lock`): not-listening → idempotent ok no-op; `tail_len =
_pending_tail_len()`; `n = max(tail_len-1, 0)` (the keystroke already deleted 1 char);
`backend.press_backspace(n)` if n>0; **if `_text_in_flight.is_set()` and `self._host is not None`**:
`_cancel_suppress_final = True` + `host.cancel()`; then `_reset_stream_after_cancel()`.
`_reset_stream_after_cancel()` (**:1454-1463**): `stream.reset_after_cancel()` (engine: clears tail,
sets `_suppressed=True`) + `feedback.update_partial("")`.

⇒ TEST SUBTLETY: the `_cancel_suppress_final=True` + `host.cancel()` leg requires `_text_in_flight`
SET and a real host — the test must set `d._text_in_flight.set()` (no run loop runs) and use a host
double. The stale-window leg (`_on_partial('late partial')` types nothing) rides the ENGINE's
`_suppressed` (set by reset_after_cancel) — independent of `_cancel_suppress_final` (which only gates
on_final).

## 3. The suppression branch (on_final :1126-1157) — read-only for this task

While `_cancel_suppress_final`: EVERY final dropped (the racing real final AND the marked sentinel);
`consume = getattr(self._host, "consume_cancel_mark", None)` — sentinel seen → re-arm. P1.M2.T7.S1
(clear `_final_pending` here) touches this branch AFTER us — sequence noted in the contract OUTPUT.

## 4. The test seam (verified)

- `_make_daemon(*, recorder, recorder_host, host_factory, backend, cfg)` @**test_daemon.py:682** →
  `_DaemonFakeFeedback` + `_StubRecorder` + `_FakeBackend` (+ `mic_prober=_ok_probe` inside).
- Host double with the cancel seam: `_FakeHost.cancel()` @**625**, `_FakeHost.consume_cancel_mark()` @**630**
  ("Read-and-clear the marked-sentinel flag, exactly like RecorderHost.consume_cancel_mark").
- **The existing daemon.cancel() test section @4430+** ("P1.M2.T7.S1 — daemon.cancel()"): includes a
  streaming-seam stand-in @4436 (`pending_tail_len()` + `reset_after_cancel()` @4446) and the note
  @4455 "No threads run; tests call cancel()/on_final() directly." → READ THIS SECTION FIRST and mirror
  its daemon construction; for the REGRESSION test prefer the REAL `self._stream` (StreamingOutput) with
  streaming cfg so deltas actually flow to `_FakeBackend` (the stand-in stubs them away).
- The masking pattern being replaced: **test_streaming_core.py:291** `stream.reset_boundary()  # next
  utterance begins` — manually invoked engine boundary; the daemon never fires it post-cancel (the
  sentinel final is dropped at :1131-1138 BEFORE commit/reset_boundary). The new test drives
  `d._touch_speech()` — the daemon's actual next-utterance-start signal (the host reader calls it on
  the child's 'speech' event; wired at daemon.py:843/853).
- Event order (why _touch_speech-then-partial is faithful): RealtimeSTT fires on_speech (VAD start)
  BEFORE partials; the child's realtime callback → on_speech → `('speech',{})` → reader → `_touch_speech`.
  `_on_partial` does NOT call _touch_speech (deliberate — :1402 comment).

## 5. Scope boundaries

- S1 (parallel): streaming.py docstrings + its engine-level repro test (test_streaming_freeze.py) — no
  overlap (my file is tests/test_daemon.py; daemon.py only if a comment needs strengthening).
- T4.S1 (BUG-004, later): adds the listening gate to _on_partial — my test keeps the daemon ARMED
  throughout so the gate is irrelevant to it (do not gate anything here).
- P1.M2.T7.S1 (later): clears `_final_pending` in the same suppression branch — sequence AFTER this.
- README/ACCEPTANCE: Mode B, P1.M3.T9.
