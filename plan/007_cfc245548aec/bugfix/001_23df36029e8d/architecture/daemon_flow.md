# Daemon flow findings — `voice_typing/daemon.py` (+ recorder_host, key_listener)

All lines verified by direct read.

## Utterance lifecycle & threading

- Partials: host reader thread → `_dispatch("partial")` (recorder_host.py :444-446, UNGATED) → `daemon._on_partial` :1376 → `engine.on_partial` + `_latency.note_partial`. **No `self._listening.is_set()` gate** (BUG-004); `on_final` HAS the gate at :1121-1123 as its first statement (outside `_on_final_lock`).
- Finals: new thread per final → `on_final` :1115 under `_on_final_lock`: (1) listening gate; (2) `_cancel_suppress_final` branch :1130-1137 — consumes the marked sentinel via `self._host.consume_cancel_mark()`, re-arms the flag, and RETURNS EARLY (no clean, no typing, **`_final_pending` NOT cleared** — BUG-007); (3) `textproc.clean` rejection branch :1137-1165 — under streaming: `self._stream.freeze("rejected final (blocklist/min_chars)", session=True)` :1154, then `reset_boundary()` :1157, `_final_pending=False`, `_utterance_finalized=True`; (4) commit path → `engine.commit` + post-commit `reset_boundary()` (~:1243).
- Speech start: child `on_speech` → `("speech", {})` → `daemon._touch_speech()` :1354 → stamps `_last_speech_monotonic`, sets `_final_pending=True` iff not `_utterance_finalized`. **This is the recommended explicit-resume seam for BUG-001/002** (it fires exactly when genuinely new speech begins).
- Cancel: `cancel()` :1603 (control worker, under `self._lock`): idempotent no-op when disarmed; else compensating `press_backspace(max(tail_len-1,0))`, and iff `_text_in_flight` + host: sets `_cancel_suppress_final=True` and `host.cancel()` (audio-DISCARDING), then `_reset_stream_after_cancel()` :1437 → `engine.reset_after_cancel()` + `_feedback.update_partial("")`.
- Stop: `_request_stop` :1391 — drains (`_begin_drain` :1637, `threading.Timer(_DRAIN_TIMEOUT_S=5.0)` watchdog :149,:1644) iff `host is not None and _text_in_flight.is_set() and _final_pending`; else immediate `_disarm()` + `_safe_abort()`. After a cancel, `_final_pending` stayed True (BUG-007) → stop-after-cancel always takes the ~5s drain.
- Evdev: key_listener.py — `KEY_BACKSPACE` → `backspace_cb` (daemon.cancel); every OTHER key (incl. Shift/Ctrl/CapsLock, which insert nothing) → `OTHER_PRESS` → `other_key_cb` (daemon.note_user_keypress :1448 → engine per-utterance freeze) — this is why BUG-003's trigger is "any non-Backspace keypress".

## Control server

`ControlServer._handle` :2444: per-connection readline loop; `line.strip()`; `if not line: continue  # empty line -> skip (no response)` :2453-2454 (**BUG-005** — client hangs; socket has no read timeout, see ctl.py `send_command` + AGENTS.md hazard table). Malformed JSON reply format to mirror: `{"ok": False, "error": f"malformed JSON: {exc}"}` :2496-2497 (docstring behavior table at :2338; unknown command :2537).

## Bug validations (daemon side)

- **BUG-001:** freeze call-site :1154 with the warning comment :1150-1153 ("The landed S2 test pins frozen=True across this call — do not retag to per-utterance") — the fix must add an explicit lift (engine resume) wired at `_touch_speech`, not a class flip.
- **BUG-002:** sentinel dropped at :1130-1137 before any `reset_boundary()` → suppression persists through the whole re-said sentence until its own commit.
- **BUG-004:** `_on_partial` :1376 lacks the gate `on_final` has at :1121. PRD daemon-level repro verified against code: after `d.stop()`, `d._on_partial('stray words')` reaches `engine.on_partial` and types.
- **BUG-005:** as above; PRD live-verified (`printf '\n' | timeout 5 nc -U …/control.sock` gets nothing).
- **BUG-007:** early return at :1130-1137 precedes `_final_pending=False` :1165.

## User-visible warning hook (BUG-001 recommendation)

`freeze()` already logs WARNING. For a user-visible cue check `voice_typing/feedback.py` (264 lines) for an existing notify/toast method (README mentions toasts + optional `feedback.notify_on_final`); do NOT invent a new surface — reuse what exists, else log-only.

## Daemon-level test seam (fast, no CUDA)

`tests/test_daemon.py` doubles: `_FakeFeedback` :33, `_FakeRecorder` :65, `_StrictFakeRecorder` :72, `_DaemonFakeFeedback` :470, `_StubRecorder` :485, `_FakeBackend` :512, `_ok_probe` :530, `_FakeHost` :556. Construction pattern (:684, :1279): `d = daemon.VoiceTypingDaemon(cfg, _DaemonFakeFeedback(), recorder=_StubRecorder(), backend=_FakeBackend(), mic_prober=_ok_probe)`; then `d.start()`; drive `d._on_partial(...)` / `d.on_final(...)` / `d.cancel()` / `d._request_stop()` / `d._touch_speech()` directly and assert on `backend.typed`/`backend.backspaces`. Existing style example: `test_on_final_streaming_false_is_verbatim_rev1_hatch` (test_daemon.py:4510).
