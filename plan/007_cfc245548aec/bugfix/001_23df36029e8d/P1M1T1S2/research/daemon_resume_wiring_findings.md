# Research Note: daemon wiring for rejected-final recovery (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo (daemon.py, streaming.py, feedback.py, tests/test_daemon.py) + the S1 PRP contract.

## §1. The S1 contract (input) — `resume()` semantics

S1 (parallel, engine) delivers on `StreamingOutput`:
- `resume()` — under `self._lock`: sets `_suppressed = False` **ALWAYS** (also the post-cancel seam); lifts `_frozen`/`_frozen_session` **iff NOT** backend-failure-origin (`_frozen_backend_failure` flag set only by `_safe_type`/`_safe_backspace`); idempotent; sends NO keystrokes; doesn't touch `_committed`/`_tail`.
- The daemon's existing call `self._stream.freeze("rejected final (blocklist/min_chars)", session=True)` (daemon.py:1154) stays **byte-identical** — S1 explicitly forbids retagging to per-utterance (stray late partials of the rejected utterance must not revise the frozen tail).
- **S2 DEPENDS ON S1**: verify `grep -n "def resume" voice_typing/streaming.py` before wiring (RED-until-S1 otherwise).

## §2. The two daemon edit sites (live, line-verified)

**Site A — on_final rejected-final branch (daemon.py:1137-1165).** Current streaming path: `freeze(..., session=True)` (:1154) → `reset_boundary()` → `_final_pending=False` → `_utterance_finalized=True` → `return`. There is **NO logger call** in the branch today (verified) and **NO user cue**. The comment at :1150-1153 pins "do not retag to per-utterance; the landed S2 test pins frozen=True across this call" — that existing daemon test is `test_on_final_streaming_rejected_final_freezes_tail_and_keeps_bookbooking` (tests/test_daemon.py:4621) asserting `be.typed == ["hello world"]`, `frozen is True`, `committed == ""`, bookkeeping flags, `fb.finals == []`. S2 ADDS (inside the `if self._cfg.output.streaming:` block, after the bookkeeping): a `logger.warning(...)` (the contract's "keep a WARNING") + `self._feedback.notify(<short cue>)`. Rev 1 branch (streaming=False, :4639 test) stays byte-for-byte — cue/warning are streaming-only.

**Site B — `_touch_speech()` (daemon.py:1354-1381).** Runs on the host reader thread on the child's ungated `('speech', {})` IPC event (recorder_host.py:447-448), fired when genuinely new speech begins. Current body: `_last_speech_monotonic = time.monotonic()`; `if not self._utterance_finalized: self._final_pending = True`. S2 adds `self._stream.resume()` at the TOP (before the flag logic, so it runs regardless of `_utterance_finalized`). Mirrors `_on_partial`'s direct `self._stream.on_partial(text)` call style — `self._stream` is ALWAYS a real StreamingOutput (constructed unconditionally at daemon.py:754), so no getattr seam needed. Lock safety: resume takes only the engine lock; on_final takes `_on_final_lock` → engine lock (one direction; no cycle).

## §3. The user-visible cue — `feedback.notify(msg)` is the existing fit

feedback.py:206 `notify(msg)`: "ad-hoc hyprctl toast, gated by cfg.hypr_notify (no state change, no disk write)" — the 'Loading…' precedent (daemon.py:829 `self._feedback.notify(_COLD_LOAD_NOTIFY_LOADING)`). One line, self-gated by the master switch, exactly the "existing method that fits" the contract asks for. No new surface invented.

**⚠️ FAKE GAP:** `_DaemonFakeFeedback` (tests/test_daemon.py:470) records phases/partials/finals/listening_states but has **NO `notify` method** — adding the daemon call would AttributeError in every test that reaches the rejected branch (incl. :4621). Fix: additively extend the fake with a `toasts: list[str]` recorder + `def notify(self, msg)`. (The :829 Loading call doesn't hit it in the fast tests; :1154's branch does.)

## §4. Test seams (live-verified)

- `_make_daemon(*, recorder, recorder_host, host_factory, backend, cfg)` @:676 → `(d, fb, rec, be)`; `_DaemonFakeFeedback`@470, `_StubRecorder`@489, `_FakeBackend`, `_ok_probe`; `_FakeHost`@556 **has `consume_cancel_mark`** @:625; `_fake_host_factory`@660. Default cfg → `output.streaming=True` (Rev 2 default) — the :684 pattern needs no cfg override for streaming; override `cfg.filter.blocklist = [...]` to force rejections deterministically.
- Existing tests to keep green: :4621 (rejected-final freeze+bookkeeping — unaffected by the additive notify on the fake), :4639 (Rev1 plain early return), :1876 (`test_on_final_rejected_hallucination_emits_no_latency_line` — caplog; the new WARNING is a different logger/message and must not emit the latency line), :4581/:4593/:4605 (streaming commit/revise/Rev1), plus the whole `_touch_speech` suite (:764-:947 — resume() is a no-op for them since nothing is frozen/suppressed).
- The contract's daemon-level repro: reject → frozen + cue → stray partial mirror-only → `_touch_speech()` → unfrozen → next `_on_partial` TYPES. Assert `fb.toasts` contains the cue.

## §5. Overlap note for P1.M1.T2.S2 (BUG-002)

`_touch_speech()` → `resume()` ALSO clears `_suppressed` at the next speech — which is exactly T2.S2's "lift post-cancel suppression at next utterance start". This is BY DESIGN (S1's resume clears `_suppressed` always; the PRD h2.5 recommendation names the 'speech' event). T2.S2's job reduces to its daemon-level cancel→live-typing regression test + any residual wiring it finds missing. S2 must NOT add extra suppression-clearing elsewhere (no duplication).

## §6. Misc facts

- daemon.py:1553's `freeze(reason, session=True)` lives in a defensive helper (the `_freeze...` seam used by user-keypress paths) — NOT touched by S2.
- `_refresh_context_prompt`'s "Deliberate NO-OPs" list (:1576) already excludes rejected finals — S2 changes nothing there.
- AGENTS.md: two timeouts; `.venv/bin/python -m pytest`; NO live daemon, NO CUDA; mock host via `_StubRecorder`/`_FakeHost`.
