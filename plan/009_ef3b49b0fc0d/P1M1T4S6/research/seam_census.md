# Seam Census — P1.M1.T4.S6: Native-session Termination Complete Map

## 1. voice_typing/daemon.py — Full Symbol Inventory

### _native_* attributes (lines ~1040-1075)
- `self._native` (line 1040): ONE connection-bound `NativeReservation`; `None` when no native session live.
- `self._native_seq` (line 1040): Mints owner tokens (startup fence).
- `self._native_ids` (line 1041): Bounded deque (maxlen=8) of active + recently ended UUIDv4 ids (duplicate_id guard, §4.8.1 B).
- `self._native_timer` (line 1042): 30s Start-cap watchdog `threading.Timer` handle.
- `self._native_worker` (line 1043): `threading.Thread` for native start lifecycle; `None` when idle.
- `self._native_clock` (line 1044): Monotonic clock function (`time.monotonic` by default; injectable).
- `self._native_timers` (line 1045): `ThreadTimers` instance.
- `self._native_end_cb` (line 1046): Receives `EndRecord` once, off-lock (T4.S6/T4.S7 delivery hook).
- `self._native_end_delivered` (line 1047): Idempotent flag — `True` once `on_end` delivered.
- `self._native_drain_boundary` (line 1057): Whole-value `_CaptureBoundary` snapshot (`None` during LISTENING; lock-free reader sentinel).
- `self._native_settle_deadline` (line 1058): `now + NATIVE_SETTLE_TIMEOUT_S` deadline for settlement watchdog.
- `self._native_settle_timer` (line 1059): `_native_timers` handle arming ≤5s ACK-settlement window.
- `self._native_end_facts` (line 1060): `NativeEndFacts(reason, revoked, recoverable)` — T4.S6 reads at `on_end`.

### _native_* methods
- `terminate_native(reason, cause, token)` (line 3369): Ends live reservation; `token` restricts (`None` = any). Called WITHOUT `_lock`. Delivers `on_end` off-lock. Idempotent (`None` if already ended). Returns `EndRecord | None`.
- `_end_native_locked(reason, cause, now)` (line 3310): Core terminator — stores `EndRecord`, clears fence/queue, delivers `on_end` off-lock, resets `_native_end_delivered`. Under `_lock`.
- `_native_owner_live_locked()` (line 3055): `self._native is not None and self._native.live` — caller holds `_lock`.
- `_native_blockers_locked()` (line 3063): Four flags under `_lock`.
- `_native_open_capture_locked()` (line 3068): Latches arm fence + builds `OfferQueue`. Called from `_arm` after `self._host.set_microphone(True)` — host bumps `arm_seq` before cmd put (T4.S3 Critical #4).
- `_native_close_capture_locked()` (line 3109): Clears fence + closes offer queue + clears pump wakeup event. Idempotent; called from `_end_native_locked` so EVERY native end funnels here.
- `_native_final_verdict(ev)` (line 3143): Verdict `"ok" | "missing" | "kind" | "class:X" | "fence" | "drain"` — reader reads ONLY `host.relay_event` snapshot.
- `_native_reject_final(why)` (line 3165): Closes utterance lifecycle for rejected final. Logs CODE only — never text.
- `_native_on_final(text)` (line 3207): THE native acceptance route — verdict → clean → handoff → refresh → enqueue → lifecycle stores → wakeup.
- `_native_mic_closed_locked()` (line 3393): `_disarm` tail for live native owner. Queue revoked → end with revocation reason; nothing unsettled → end now; DRAINING with offers → arm settlement timer; DRAINING with no offers → `_end_native_locked(r.end_reason, None)`.
- `_native_settle_step_locked(now)` (line 3428): One settlement decision under `_lock`. Ends iff delivery revoked, queue fully settled (drain reason), or budget spent with work unsettled. Returns `EndRecord | None`.
- `native_stop(reason, token)` (line 3449): Graceful funnel (§4.8.1 B). STARTING → `'stop-during-start'`. LISTENING → DRAINING(reason): wake pump, snapshot `host.capture_boundary`, THEN either bounded ASR drain (`_DRAIN_TIMEOUT_S`) for the one utterance in flight, OR mic-off now (`_safe_abort`) when nothing in flight. After drain, offers settle ≤ NATIVE_SETTLE_TIMEOUT_S (`_native_mic_closed_locked` arms watchdog; pump kicks `native_settle_kick` after every ack/check_deadline). DRAINING → None (first reason wins).
- `native_cancel(token)` (line 3529): Invalidate FIRST, then abort; NEVER drains. Revoke queue + drop unattempted finals → `_end_native_locked` (tombstone, close fence) → mic off in SAME hold → `[off-lock]` `host.cancel()` (gated on `_text_in_flight`, exactly like `_safe_abort`). Late final neither retained nor typed (fence cleared by end).
- `native_lost(reason, cause, token)` (line 3577): Loss/disconnect — revoke delivery FIRST, then drain for recovery ONLY. STARTING/DRAINING → end at once (no capture/settlement). LISTENING → revoke + DRAINING(reason): at most in-flight utterance drains INTO RECOVERY ONLY (queue revoked, enqueue returns REVOKED, pump never woken — no ACK can arrive); then immediate end, NO settle timer. Loss while starting aborts without capture.
- `_stop_native_start()` (line 3393): Emergency graceful stop — STARTING owner ends here (`'stopped'`, `'stop-during-start'`). False when nothing to stop.
- `_begin_drain_locked()` (line ~3450): Starts bounded ASR drain; returns `True` if drain timer armed (safety net).
- `_arm_drain_watchdog()` (line 2526): Arms drain watchdog timer firing after `_DRAIN_TIMEOUT_S` if no final fired; aborts blocked `text()` so drain ends.

### Status / seed / context_prompt symbols
- `_seed_handoff_pending` (line 1012): `False` = confirmed seed resident AND not yet replaced (set ONLY by fenced seam's hook). Triggers seed handoff on FIRST accepted final of seeded session.
- `_seed_handoff_done` (line 1013): `False` = session replaced seed via accumulator (per-session; reset in `_arm`). `True` after seed applied at first accepted final.
- `_seed_active` (line 1029): `False` = confirmed seed resident in child — PERSISTS ACROSS DISARM (child stays resident with seed; next arm decides: re-prime on seed arm, CONFIRMED clear on plain arm).
- `_session_accepted` (line 1014): `list[str]` — THIS session's accepted finals only — never seed/tail/partial (reset in `_arm`).
- `_context_prompt_active` (line ~after 1075): `bool | None` — `None` = no child loaded; `True` = PromptedExecutor armed; `False` = degraded.
- `_context_prompt_label()` (line 3919): Human label — precedence: config-off > models-not-loaded > degraded > on.
- `_normalize_context(context)` (line ~3689): Normalizes context string for seed usage.

### Ducking symbols
- `self._ducker` (line 1140): `AsyncDucker` instance (`None` if `duck_mode="off"`). `engage()`/`release()` dispatch returns immediately (safe inline under `self._lock` — NEW-2 wedge class).
- `_duck_engage()` (line 1821): Engages media ducking while armed. Calls `self._ducker.engage()` under `_lock`; idempotent, coalesced. Toast: `self._feedback.set_ducked(True)`.
- `_duck_release()` (line 1840): Releases media ducking on EVERY disarm path. Called from `_disarm()`'s toast site, `request_shutdown()` (quit + SIGTERM), and `_handle_dead_host()` (child died while ducked — no `_disarm` ran). NOT from `cancel()` (keeps mic hot). Calls `self._ducker.release()` under `_lock`; idempotent, latest-wins. Toast: `self._feedback.set_ducked(False)`.
- `_duck_flush_at_quit()` (line 4108): Quit path — calls `self._ducker.flush(2.0)` so async release lands before process exit; systemd `ExecStopPost` runs `python -m voice_typing.ducking_heal` on every stop (flag-gated).
- `self._startup_ducked` (line ~86): Read from persisted `ducked` flag BEFORE any Feedback write at boot; crash-safety: when set, spawns one-shot `vt-duck-heal` thread (force=True).

### Feedback public methods + state.json keys
- `set_phase(phase)`: Records VAD phase; always writes; never notifies.
- `set_models_loaded(loaded)`: Records models resident; always writes.
- `set_mode(mode)`: Records armed mode (`"lite"` always; Rev 2 constant).
- `set_ducked(ducked)`: Records DESIRED media-ducking state; always writes; crash-safety signal T3.S2's boot self-heal reads.
- `set_delivery_mode(mode)`: Records bulk-delivery path (`"stream-edit" | "bulk-text"`); written ONLY by bulk wiring.
- `set_delivery_state(state, reason)`: Records bulk-delivery state + concise reason; sanitized via `_sanitize_status_text`.
- `record_confirmed_op(op)`: Records last APPLIED bulk-delivery op descriptor; sanitized same way.
- `record_final(text)`: Records finalized utterance; sets `last_final` AND `partial`; maybe notifies (`✔ <text>`) if `hypr_notify and notify_on_final`.
- `set_listening(listening)`: Sets master listening gate; always writes; notifies start/stop on transition only.
- `snapshot()`: Shallow copy of live in-memory state — for control-socket `status` cmd WITHOUT hitting throttled state.json.
- `_notify(msg)`: Fire-and-forget `hyprctl notify`; gated by `cfg.hypr_notify`; used for `'Loading…'` toast and `'Recording'` / `'Recording Stopped'`.

### _on_final_lock vs _lock interaction
- `self._on_final_lock` (line ~896): Serializes concurrent `on_final` worker threads. Separate from `self._lock`. on_final never takes `self._lock`; `_arm`/`_disarm` never call `on_final` → no lock-ordering deadlock.
- `self._lock` (line ~872): Serializes daemon critical sections. Every method in `NativeReservation`, `OfferQueue`, `NativeRecovery`, and the native end/fence/settlement path runs UNDER this lock.

### _safe_abort (line 2831)
- Gated on `self._text_in_flight` flag. When no thread blocked in `text()`, `abort()` would hang forever → skipped (no-op). When a thread IS blocked in `text()`, calls `self._host.abort()`. Called by `stop()`/`toggle(off)`/`request_shutdown()` AFTER releasing `_lock`.

### _text_in_flight (line ~867)
- `threading.Event` — SET while run loop blocked INSIDE `recorder.text()`, CLEARED the instant it returns. Abort can only safely wake a thread blocked HERE.

### _listening and _shutdown events
- `self._listening` (line ~875): `threading.Event` — cleared → NOT listening at boot. Run loop checks on every iteration; on_final gates on it.
- `self._shutdown` (line ~877): `threading.Event` — cleared → keep looping. Set in `request_shutdown()` → run() loop exits.

### _drain and _drain_timer
- `self._drain` (line ~940): `bool` — True when graceful stop pending and `text()` just returned.
- `self._drain_timer` (line ~942): `threading.Timer | None` — hang safety net: if no final fires within `_DRAIN_TIMEOUT_S` it aborts blocked `text()`.

### _final_pending and _utterance_finalized
- `self._final_pending` (line ~937): `bool` — tracks "utterance in flight" signal. NOT reliable alone (set by every partial via `_touch_speech`). Reset in `_on_final` and `_disarm`. Issue 2: `_utterance_finalized` is the precise counter-signal.
- `self._utterance_finalized` (line ~939): `bool` — set True in `on_final`; reset False when run loop (re-)enters `text()` for next utterance. Stray late partials cannot re-arm `_final_pending` once this is True.

### _rev1_committed (line ~870)
- `str` — daemon-side committed-text accumulator (rollback hatch for `output.streaming=false`). Reset at every `_arm()`.

### _arm_seq, _arming, _stop_seq
- `self._arm_seq` (line ~887): Monotonic arm-reservation generation; newer supersedes older one's commit.
- `self._arming` (line ~889): Outstanding reservation token (or `None`); set under `_lock` in `_start_fenced`.
- `self._stop_seq` (line ~892): Bumped by every disarm (stop/toggle-off/auto-stop). Stop landed between reservation and its commit aborts that commit.

### _load_host / _unload_host / host death
- `_load_host()` (line 1356): Single-flight lazy SPAWN of recorder-host child (PRD §4.2bis). True iff ready. Fast path under `_lock`: resident + alive → instant (ONE mode). Called by `start()`/`toggle()` BEFORE arming — NOT inside `_arm()` (would deadlock).
- `_handle_dead_host()` (line 1421): Recover from unexpected recorder-host child death. Called from `run()` when `self._host.is_alive` is False. Drops dead reference, resets to 'unloaded' lifecycle state UNDER `_lock`. Clears `_listening`, sets `_load_error`, clears both idle clocks. Calls `self._duck_release()` (child died while ducked — no `_disarm` ran). RACE GUARD: if another path already transitioned to unloaded, this is a NO-OP. After lock release: `self.terminate_native("load_failed" if starting else "disconnected", cause="host-died")` (off-lock).
- `_unload_host()` (line ~4046): Idle UNLOAD watchdog teardown. Re-checks `not self._models_loaded` first → no-op if already torn down. Stops host child (`host.stop()` = terminate process group → ALL VRAM released). Resets daemon state: `_host = None`, `_models_loaded = False`, `_context_prompt_active = None`, phase = `"unloaded"`, models_loaded = False, `_load_error = None`, reseeds `_resolved_device_cache` to un-probed config.
- `run()` exit/finally: Ensures `_teardown_done.set()` fires so concurrent `shutdown()` (main-thread finally, SIGTERM path) WAITS rather than starting a second teardown.

### Native start seed/clear policy (in `_start_fenced` and `_arm`)
- Confirmed seed arm: seed IS the prompt; child's bounded acknowledgement confirms it. Seed PERSISTS ACROSS DISARM — child stays resident with seed. NEXT arm decides: re-prime on seed arm, CONFIRMED clear on plain arm.
- Plain arm after seeded session: CONFIRMED clear — child prompt-None; commit step clears child's context before opening capture.
- Plain arm with no prior seed: legacy best-effort clear or skip it (nothing to clear).

### Recovery hooks (session_recovery.py)
- `note_final(text, key)`, `note_rejected()`, `note_tail(text)`, `note_cancel()`, `close_session()`, `latest_completed()`, `clear()`.

### NativeRecovery class — public methods
- `retain_final(session_id, seq, text)` → `bool`, `mark_offer_attempted(session_id, seq)` → `bool`, `settle_final(session_id, seq)` → `bool`, `end_session(session_id, reason)` → `None`, `recover(session_id)` → `NativeRecoverySnapshot | None`, `active_id()` → `str | None`, `counts()` → `tuple[int, int]`, `clear()` → `None`.

### Caps
- `_MAX_NATIVE_SESSIONS = 2`, `_MAX_NATIVE_SESSION_BYTES = 1 << 20`, one active slot, 1 MiB UTF-8 INCLUDING separators while active, fully-ACKed/empty endings discarded never evicted.

### END_REASONS vocabulary (editor_protocol.py line 144)
- `STOPPED`, `IDLE`, `CANCELLED`, `TARGET_LOST`, `DISCONNECTED`, `TIMEOUT`, `DELIVERY_FAILED`, `LOAD_FAILED`, `SHUTDOWN`.

### LossCause vocabulary (editor_protocol.py line 414)
- `EOF`, `IO`, `FRAME`, `REQUEST`, `LEASE`, `WRITE` — each with `end_reason` property mapping to T4.S6 `ended.reason`.

### Frame/event names (editor_protocol.py)
- `'starting'`, `'listening'`, `'pong'`, `'final'`, `'finishing'`, `'ended'` — each with specific fields.

### No 'hint'/'warning' field in protocol
- Warnings through log messages, ProtocolError exceptions, `format_result` returning `"error: <text>"`, and `possibly_applied` flag in `NativeRecoverySnapshot`.

### ThreadTimers API (editor_protocol.py)
- `arm(deadline, fire)`, `cancel(handle)`.

### ENUM Types
- `Stage` (editor_session.py): `STARTING | LISTENING | DRAINING | ENDED`.
- `EndReason` (editor_protocol.py): `STOPPED | IDLE | CANCELLED | TARGET_LOST | DISCONNECTED | TIMEOUT | DELIVERY_FAILED | LOAD_FAILED | SHUTDOWN`.
- `ContextReason` (editor_protocol.py): `EMPTY | DISABLED | UNAVAILABLE`.
- `NativeErrorCode` (editor_protocol.py): `INVALID_REQUEST | TOO_LARGE | UNSUPPORTED_VERSION | BUSY | DUPLICATE_ID`.
- `LossCause` (editor_protocol.py, Pump): `EOF | IO | FRAME | REQUEST | LEASE | WRITE`.

### Feedback state.json keys (full)
```
{"listening": bool, "phase": str, "models_loaded": bool, "mode": "lite",
 "ducked": bool, "delivery_mode": "stream-edit"|"bulk-text",
 "delivery_state": "inactive"|"active"|"unsupported"|"fault",
 "delivery_reason": str, "last_confirmed_op": str, "partial": str,
 "last_final": str, "ts": float}
```

### 'reason', 'delivery_reason', 'recovery', 'native' keys in state.json
- `delivery_reason`: Present — one concise reason (stop/acquire failure), sanitized.
- `delivery_mode`: Present — mirrors configured bulk-delivery path.
- `delivery_state`: Present — R.5 taxonomy.
- `last_confirmed_op`: Present — last APPLIED bulk-delivery op.
- `partial`: Present — realtime partial text; overwritten by `record_final(text)`.
- `last_final`: Present — last finalized utterance text.
- `reason`: NOT a native state.json key. End reasons conveyed through native end flow.
- `recovery`: NOT a native state.json key. Native recovery exposed via `voicectl session` (R.6) or `voicectl recover` (T5.S1).
- `native`: NOT a native state.json key. Native session status through control socket implicit state and native end flow.

### Toast/notify methods
- `notify(msg)`: Fires `hyprctl notify` gated by `cfg.hypr_notify`. Used for: `'Recording'` (False→True), `'Recording Stopped'` (True→False), `'Loading…'` (one-shot before cold first-arm), `'✔ <text>'` (record_final, gated by `cfg.notify_on_final`).
- All other transitions do NOT fire notifications — anti-spam rule.

### ctl.py status rendering
- `status_snapshot()` renders 18 keys.
- `format_result` renders status as multi-line text with listening, mode, output, phase, partial, last, uptime, device, mic, context-prompt, delivery (mode/state/reason/op — only when non-empty), load error (when present).

### Tests covering key symbols
- `test_handle_dead_host_noop_when_host_already_cleared` (test_daemon.py:4637), `test_idle_unload_fires_when_disarmed_beyond_threshold` (test_daemon.py:4206), `test_status_snapshot_keys_and_cuda_values` (test_daemon.py:2196), `test_handle_dead_host` (test_editor_session.py:258), `test_request_shutdown` (test_editor_session.py:261), `test_cancel_is_busy_without_side_effects_under_native_owner` (test_editor_session.py:157), `test_disarm_ends_listening_owner_with_drain_reason_via_parked_worker` (test_editor_session.py:238).

### Fake harness names in tests/test_daemon.py
- `_FakeFeedback` (line 36), `_FakeRecorder` (line 68), `_FakeBackend` (line 739), `_FakeHost` (line 783), `_make_daemon` (line 904), `_FakeProcess` (line 2536), `_FakeSlowRecorder` (line 2549), `_FakeStream` (line 4748), `_FakeKeypressStream` (line 5472).
