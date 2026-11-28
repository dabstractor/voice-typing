# Research — P1.M1.T3.S4: Reserve one native owner and fence its startup

Checked at HEAD `6fd5309` (S1 + S2 committed; S3's pump symbols already present on disk in
`voice_typing/editor_protocol.py`: `START_CAP_S` :397, `LossCause` :413, `ThreadTimers` :464).
No command beyond `git`, `grep`, `sed`, `wc`, `ls` was run; nothing was modified.

## 1. The seam as it exists (daemon.py @ HEAD)

| Symbol | Line | Role for this item |
| --- | --- | --- |
| `_START_DEADLINE_S = 30.0`, `_PRIME_BUDGET_S = 5.0` | 247-248 | generic start budget; the native cap reuses `editor_protocol.START_CAP_S` (same value, single client reference) |
| `ArmOutcome` (frozen) | 252 | `.ok`, `.reason` ∈ ok/seed-applied/seed-clear/busy/load-failed/seed-unconfirmed/prompt-unconfirmed/superseded/aborted |
| `VoiceTypingDaemon.__init__` | 764+ | `_lock = threading.Lock()` :836 (**not reentrant**), `_shutdown` Event :847, `_drain: bool` :921, `_arm_seq`/`_arming` :975-976, `_stop_seq` :981 |
| `_load_host()` | 1098 | sets `_loading` under `_lock`, runs `host.spawn()` OUTSIDE `_lock`, can block on the single-flight load — the "caller can block" the item names |
| `_handle_dead_host()` | 1327 | lock block resets `_host=None`, clears `_listening`, phase unloaded |
| `_disarm()` | 1839 | ALWAYS called under `_lock`; clears `_listening`, `set_microphone(False)`, `_duck_release` |
| `_request_stop()` | 1958 | drain (`_begin_drain`) or immediate `with self._lock: self._disarm()` |
| `cancel()` | 2263 | legacy backspace + `host.cancel()` — must become **busy** under a native owner |
| `_maybe_auto_stop()` | 2367 | `with self._lock: self._disarm()` at ~2388 — idle end must carry reason `idle` |
| `_start_fenced(seed, *, streaming, timeout, reject_busy)` | 2631 | T2.S3's reserve→load→prime→**atomic revalidate + commit under `_lock`** seam. `reject_busy=True` (T2.S5) rejects on `_arming/_loading/_listening/_drain` WITHOUT reserving |
| `start_with_seed` / `start_context` | 2799 / ~2808 | both route through `_start_fenced` (context uses `reject_busy=True`) |
| `start()` / `stop()` / `toggle()` | 2866-2906 | discard the `ArmOutcome`; `toggle` disarms iff `_listening` |
| `request_shutdown()` | 2907 | sets `_shutdown` under `_lock`, tears down outside |
| `status_snapshot()` / `is_listening()` | 3069 / 2976 | must stay responsive during a native start |
| `ControlServer(daemon, socket_path=None, on_quit=None)` | 3406 | `_dispatch` :3591 routes toggle*/start*/start-context/stop/cancel/status/quit/session |

The commit block of `_start_fenced` (under `_lock`, right before `self._arm(streaming=...)`) is
**the only place capture opens**, so it is where the native commit hook belongs. T2.S3 already
fences on `_arming/_arm_seq/_stop_seq/_shutdown/_drain/_loading/_host is host/is_alive`; the
native token fence slots into the same boolean expression and the commit branch.

## 2. Contracts consumed

- **S3 (parallel, on disk)**: `OwnerPump(conn, session_id, *, on_command, on_loss, reader, clock,
  timers, lease_s, write_cap_s, queue_max)`; `on_loss(cause: LossCause, detail: str)` exactly once,
  off-lock, socket already shut; `send_event` non-blocking (raises `PumpClosed`); `shutdown(terminal)`
  graceful; `write_reject(conn, code)`; `START_CAP_S=30.0`; `ThreadTimers(clock).arm(deadline, fire)`
  / `.cancel(handle)`; `deadline_after`, `remaining`. The pump does NOT decide busy/duplicate_id.
- **S2 (landed)**: `validate_request` (editor-start{version,id,context}), `is_uuid_v4` :170,
  `native_error_reply(code)`, `NATIVE_ERROR_CODES` incl. `busy`, `duplicate_id`.
- **T2.S3 (landed)**: the seam above + `_abort_start` cleanup/isolation of an installed seed.
- **T2.S5 (landed)**: `start_context` → `_context_reply` maps outcome `busy` to an error reply — it
  gets native-busy for free once the generic guard returns `busy`.

## 3. Design decisions

- **D1 Two modules.** `voice_typing/editor_session.py` = pure reservation state (`Stage`, `Owner`,
  `EndRecord`, `NativeReservation`, `NativeReserveResult`) — no daemon import, no I/O, no lock of its
  own (every method runs under the daemon's `_lock`), injected clock. `daemon.py` = the wiring:
  `_native`, `_native_seq`, `_native_ids`, `_native_timer`, `_native_clock`, `_native_timers`, the
  four hooks (`reserve_native`, `begin_native_start`, `begin_native_drain`, `terminate_native`) and
  the busy predicate. Mirrors system_context.md: "`editor_session.py` owns reservation/ordered
  delivery state".
- **D2 Check-and-reserve is ONE critical section.** `reserve_native` under `_lock` evaluates, in
  order: shutdown → `busy`; id active/tombstoned → `duplicate_id`; native owner live → `busy`; ANY
  generic arm `_arming | _loading | _listening | _drain` → `busy`; else bump `_native_seq`, build
  `Owner(id, token, created_at, deadline=created_at+START_CAP_S)`, install, register id, collect the
  timer handle. Nothing is reserved on rejection (no token, no timer, `_arm_seq` untouched).
- **D3 The owner token is the fence.** `_native_seq` is monotonic; a late worker carrying a
  superseded/tombstoned token can never commit (`_native_can_commit_locked`). Replacing the
  reservation (new reserve after an end) also changes the token, so stale workers fail the check.
- **D4 Two-phase start.** `reserve_native` does not spawn the worker; `begin_native_start(token,
  seed, streaming)` does. T4.S7 emits `starting` between the two, so `starting` provably precedes any
  later event even on a warm host (commit in ms). A reservation whose `begin` never comes still ends
  at the 30 s cap (`timeout`).
- **D5 The 30 s cap is enforced at two points, both under `_lock`, exactly once.** (a) the watchdog
  timer armed at `owner.deadline` (S3's `ThreadTimers` in production; `ManualTimers` in tests);
  (b) the commit hook re-reads the clock — a worker arriving after the deadline terminates the
  reservation itself and aborts. The timer being late can therefore never allow a late arm.
- **D6 End delivery is off-lock and exactly-once.** `threading.Lock` is not reentrant and the
  contract (pump's `on_loss`, system_context "no waits/joins/writes on daemon control lock") forbids
  callbacks under it. Transitions happen under `_lock`; the `EndRecord` is *claimed* once
  (`_claim_native_end_locked` sets `_native_end_delivered`) and delivered by the claiming thread
  after releasing the lock. The ONE under-lock terminator is `_disarm` (always called under
  `_lock`), which transitions + stashes + sets `_native_end_evt`; the session's own worker thread
  (parked on that Event after a successful commit) wakes, claims and delivers. Termination during
  STARTING (stop/timeout/loss/shutdown/host death) is delivered immediately by the terminating
  thread — never deferred behind a blocked load.
- **D7 Busy is symmetric and never queues.** Generic `start`/`toggle`/`start_with_seed`/
  `start_context` return `ArmOutcome(reason="busy")` with nothing reserved while a native owner is
  live (the seam's existing `reject_busy` block is extended by one guard that runs FIRST, so even the
  supersede semantics of plain start/toggle cannot steal the mic); `cancel()` returns a busy dict and
  performs no backspace/host cancel; a second `reserve_native` is `busy`. `stop`/`toggle-off`/`status`/
  `quit` stay usable: `stop` during STARTING aborts the reservation without opening capture; during
  LISTENING it is the emergency graceful stop (drain reason `stopped`).
- **D8 Host lifetime.** `_handle_dead_host` ends a live reservation: STARTING → `load_failed`,
  LISTENING/DRAINING → `disconnected` with cause `host-died` (PRD lists no engine-death code;
  T4.S6 owns the final `ended`/hint mapping and may remap). `request_shutdown` → `shutdown`.
- **D9 Duplicate ids.** A bounded `deque(maxlen=8)` of active + recently ended ids feeds
  `duplicate_id` ("Reject an id already active or retained"); T4.S1's recovery store may refine
  "retained" later via `native_id_known`.
- **D10 Reasons.** Worker post-outcome mapping: load-failed/seed-unconfirmed/prompt-unconfirmed →
  `load_failed`; start-timeout → `timeout`; superseded/aborted → someone already ended us (no second
  end). Idle auto-stop tags the drain `idle` before `_disarm`.

## 4. Test discipline (verification.md T10b: barriers + injected clock, never sleeps)

`_make_daemon(host_factory=...)` (tests/test_daemon.py:904) with a gated `spawn` (Event) is the
"blocked loader" barrier; the recorder's `set_microphone(True)` log is the "capture opened" probe;
`ManualTimers` + `FakeClock` installed on the instance (`d._native_clock`, `d._native_timers`) make
the 30 s cap instantaneous; `ControlServer(d, socket_path=tmp). _dispatch("toggle")` (pattern at
tests/test_control_socket.py:124) checks the wire reply. T2.S3's gated `prime_prompt` fake lives at
tests/test_daemon.py:5955-5978 for the seed-cleanup case.

## 5. Cross-item notes (report, do not fix here)

- Carry-forward from S3: PRD's `starting` frame carries `"ok":true` but S2's `validate_event` for
  `starting` is the closed set {event,id}. T4.S2/T4.S7 must allow an optional `ok` or emit without it.
- `_disarm` is called under `_lock` by every path; any future native work (T4.S5 drain budget) must
  keep running off that lock — the parked worker thread introduced here is the natural home.
- `status_snapshot()` is deliberately unchanged (T4.S6 adds the transcript-free end reason/hint).
