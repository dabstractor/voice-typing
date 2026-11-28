# P1.M1.T4.S4 — native-final routing contracts

## Executive summary

**FACT:** `NativeReservation`, `OfferQueue`, and `NativeRecovery` already provide the native ownership, delivery, and recovery leaves. `voice_typing/daemon.py` has **no matches** for `NativeRecovery`, `_native_recovery`, `OfferQueue`, `_native_queue`, or `_native_offers`, so it does not yet construct/wire them. The accepted-final insertion seam is after `_handoff_context_prompt(cleaned)` (`daemon.py:1642`) and before generic streaming/bulk output (`:1643-1663`). **INFERENCE:** the native route/early return belongs exactly there, after clean/filter and seed handoff but before every generic output path.

No daemon, `voicectl`, or tests were run.

## 1. `voice_typing/editor_session.py`

### Reservation records and transitions

- `Stage` (`:71-76`): `STARTING="starting"`, `LISTENING="listening"`, `DRAINING="draining"`, `ENDED="ended"`; `ACTIVE_STAGES` is the first three (`:78`).
- Frozen `Owner` (`:82-86`): `id: str`, `token: int`, `created_at: float`, `deadline: float`. ID is the client UUIDv4; token is the daemon fence; deadline is `created_at + START_CAP_S`.
- Frozen `EndRecord` (`:90-96`): `owner: Owner`, `stage: Stage`, `reason: str`, `cause: str | None`, `ended_at: float`; fixed codes, never text/frames.
- Frozen `NativeReserveResult` (`:100-103`): `accepted: bool`, `owner: Owner | None`, `error: str | None` (`busy | duplicate_id | invalid_request`).
- `NativeReservation.__init__(self, owner: Owner, conn: object, *, now: float) -> None` (`:111`): starts STARTING with `drain_reason=None`, `end=None`, and per-reservation `end_evt` (`:112-116`). All transitions are pure and caller-lock guarded (`:106-109`).
- `live(self) -> bool` property (`:119-121`): stage is in `ACTIVE_STAGES`.
- `end_reason(self) -> str` property (`:123-126`): drain reason or `"stopped"`.
- `can_commit(self, token: int, now: float) -> bool` (`:128-130`): matching token, STARTING, and `now < deadline`.
- `commit(self, token: int) -> bool` (`:132-137`): STARTING→LISTENING only for matching token; must share capture-opening lock hold.
- `begin_drain(self, reason: str) -> bool` (`:139-145`): LISTENING→DRAINING only for a valid `END_REASONS` code; records reason.
- `terminate(self, reason: str, cause: str | None, *, now: float) -> EndRecord | None` (`:147-155`): any live stage→ENDED; invalid reason raises `ValueError`; terminal calls return `None`.
- `tombstoned(self, token: int) -> bool` (`:157-158`): matching token and ENDED.

### OfferQueue contract

- `ACK_TIMEOUT_S: float = 5.0` (`:163`); `MAX_UNSETTLED: int = 8`, pending plus outstanding (`:164`). Sequence numbers start at 1; each final is ≤4 KiB UTF-8 (`:17-22`).
- `EnqueueOutcome` (`:167-173`): `QUEUED="queued"`, `REVOKED="revoked"`, `CLOSED="closed"`.
- `AckOutcome` (`:176-182`): `SETTLED="settled"`, `DUPLICATE="duplicate"`, `REVOKED="revoked"`, `IGNORED="ignored"`.
- `OfferAttempt` (`:197-207`): `session_id: str`, `seq: int`, `text: str`, absolute `deadline: float`; `event()` returns `{event:"final", id:session_id, seq:seq, text:text}`.
- Constructor (`:241-249`): `OfferQueue(session_id: str, recovery, *, clock=time.monotonic, ack_timeout_s: float=ACK_TIMEOUT_S, max_unsettled: int=MAX_UNSETTLED)`. `recovery` is unannotated but must be `NativeRecovery`-compatible (`retain_final`, `mark_offer_attempted`, `settle_final`); `session_id` is the native/recovery UUID.
- Read-only properties: `session_id` (`:266-268`), `outstanding` (`:270-273`), `revoked` (`:275-277`), `revocation_reason` (`:279-281`), `last_ack_seq` (`:283-285`), `pending_count` (`:287-289`).
- `enqueue(self, text: str) -> EnqueueOutcome` (`:293-320`): retains before queueing; strips text; rejects empty/lone-surrogate/oversize text, recovery refusal, or capacity by sticky `delivery_failed` revoke. Revoked queues retain only; closed queues return CLOSED without retain/seq. Never inserts truncated text.
- `begin_offer(self, now: float | None = None) -> OfferAttempt | None` (`:323-343`): pops oldest pending, marks attempted **before write**, stamps `self._clock()+ack_timeout_s`, validates and installs outstanding/deadline. Returns none when revoked/closed/busy/empty; validation failure revokes. The optional `now` argument is unused.
- `finish_offer(self, ok: bool) -> None` (`:345-351`): failed write revokes `delivery_failed` only while still outstanding; an intervening verified ACK wins.
- `ack(self, obj: object, now: float | None = None) -> AckOutcome` (`:353-383`): exact outstanding ACK settles recovery and clears outstanding; exact last-settled duplicate is harmless; malformed/wrong-id/stale/future ACK revokes; non-applied/post-revoke is IGNORED. `now` is unused.
- `check_deadline(self, now: float | None = None) -> bool` (`:385-394`): at/after absolute deadline revokes `timeout` and returns true.
- `revoke(self, reason: str) -> str | None` (`:397-408`): sticky, first valid `END_REASONS` code wins; later calls return `None`; recovery/uncertainty survive.
- `clear_pending(self) -> int` (`:410-416`): drops/counts unattempted pending only; outstanding and recovery remain.
- `drain_pending(self) -> bool` (`:418-421`): true while pending or outstanding remains.
- `close(self) -> None` (`:423-427`): idempotent; late enqueue returns CLOSED without resurrection.

The module caller pattern (`:230-235`) is:

```python
with d._lock:
    attempt = q.begin_offer(now)
if attempt is not None:                  # write OUTSIDE the lock (2 s cap)
    ok = send_line_capped(conn, encode_line(attempt.event()))
    with d._lock:
        q.finish_offer(ok)
```

Reader `enqueue`, ACK `ack`, and timer `check_deadline` run under the caller's `_lock`; no queue method performs I/O or waits (`:210-239`).

## 2. `voice_typing/session_recovery.py` — NativeRecovery

`NativeRecovery` (`:304`) constructor (`:320-325`): `__init__(max_sessions: int=2, max_session_bytes: int=1<<20, clock: Callable[[], float]=time.monotonic)`. Memory-only leaf lock; no callbacks/I/O/logging; unacknowledged accepted finals only, no partial/seed/tail (`:304-318`).

- `NativeRecoverySnapshot` (`:289-301`): `session_id`, `text`, `truncated`, `possibly_applied`, `final_count`, `end_reason`, `ended_monotonic`. No public `snapshot()` exists; `recover()` returns this immutable snapshot via private `_snapshot_locked()` (`:510-520`).
- `retain_final(self, session_id: str, seq: int, text: str) -> bool` (`:334`): exactly once per `(id,seq)`; refuses invalid UUID/text/seq, duplicate, ended ID, or another active ID without mutation. Enforces 1 MiB including separators while active (`:336-371`).
- `mark_offer_attempted(self, session_id: str, seq: int) -> bool` (`:375`): idempotent pre-write uncertainty flag; only ACK removal clears it (`:377-389`).
- `settle_final(self, session_id: str, seq: int) -> bool` (`:392`): verified ACK removes active final/reclaims budget; unknown/ended/foreign returns false (`:394-406`).
- `end_session(self, session_id: str, reason: str) -> None` (`:409`): unknown/already-ended no-op; frees active slot; discards empty/fully ACKed endings; retains ≤2 nonempty ended sessions (`:411-425`).
- `recover(self, session_id: str | None = None) -> NativeRecoverySnapshot | None` (`:428`): omitted ID selects latest ended; known ended/active ID returns its snapshot; otherwise `None`; wire layer decides `busy` (`:430-445`).
- `active_id(self) -> str | None` (`:448-452`): active UUID or none.
- `counts(self) -> tuple[int, int]` (`:454-461`): `(ended sessions retained, active finals retained)`.
- `clear(self) -> None` (`:463-469`): drops active and ended state; reusable.

## 3. Daemon acceptance and seed handoff

- `textproc.clean(text: str, cfg: FilterConfig) -> str | None` (`textproc.py:41`): normalized text, or `None` for too-short/blocklisted input; never appends a space (`:49-51`, `:58-69`).
- `VoiceTypingDaemon.on_final(self, text: str) -> None` starts at `daemon.py:1463`. Listening/cancel gates precede clean; acceptance/rejection is at `:1587-1588`.
- `_handoff_context_prompt(cleaned)` is called at `:1642`, before `_stream.commit(cleaned)` (`:1653`) and `_backend.type_text(...)` (`:1662`).
- Helper signature (`:2208`): `_handoff_context_prompt(self, accepted: str) -> None`.
- Contract (`:2209-2234`): append every accepted final to `_session_accepted`; first accepted final with `_seed_handoff_pending` replaces seed with accepted-only rolling context or known-empty `""`; rejected finals never consume seed. It runs before typing/commit under `_on_final_lock` (not `_lock`) and catches exceptions.

Exact helper anchor (`daemon.py:2203-2213`):

```python
        stream = getattr(self, "_stream", None)
        freeze = getattr(stream, "freeze", None)
        if callable(freeze):
            freeze(reason, session=True)

    def _handoff_context_prompt(self, accepted: str) -> None:
        """P1.M1.T2.S4 (§4.8.1 "confirmed seed before capture"): replace the seed exactly once.

        Called from on_final at the ACCEPTANCE point (textproc.clean returned non-empty),
        BEFORE any typing/commit — a raising backend, a frozen engine, or a downstream
```

**INFERENCE:** enqueue under `_lock` after `:1642`, then early-return before `:1643`; never write a socket on the recorder reader thread. `OfferQueue.enqueue` already retains, so a separate `retain_final` for the same `(id,seq)` would be a duplicate refusal.

## 4. Exact prior-PRP T4.S4 lines

`P1M1T3S4/PRP.md:56-59`:

```text
**Target User**: implementers of P1.M1.T4.S4 (route native finals before generic output), T4.S5
(stop/cancel/drain — consumes `begin_native_drain` and the parked lifecycle thread), T4.S6 (`ended`
frame + private failure hints — consumes `EndRecord` via `on_end`), T4.S7 (socket activation — calls
`reserve_native` → emits `starting` → `begin_native_start`; maps `on_loss` to `terminate_native`).
```

`P1M1T4S1/PRP.md:91-94`:

```text
- **Scope discipline.** T4.S1 owns ONLY the leaf + its tests. It does NOT wire the daemon (T4.S4 routes
  finals; T4.S6 ends sessions), does NOT touch `editor_protocol.py` (T3.S2 — complete) or
  `editor_session.py`/`daemon.py` (T3.S4 — parallel, in flight), does NOT implement the wire reply
  (T5.S1) or the CLI (T5.S2). Pure stdlib + one leaf import; no socket, no CUDA, no I/O.
```

`P1M1T4S1/PRP.md:468-469`:

```text
  - P1.M1.T4.S4 (route native finals, later): retain_final(id, seq, text) from the reader thread AFTER
    clean/filter, BEFORE any generic output (per system_context) — the store is lock-safe there.
```

`P1M1T2S4/PRP.md:188-190` and `:338-340`:

```text
# CRITICAL #2 — HANDOFF BEFORE TYPING. Place the call right after `self._utterance_finalized = True`
# and before `if self._streaming_now():`. A raising backend, a frozen engine, or a native
# early-return (T4.S4, inserted above the generic branches) must not be able to skip it.
```

```text
DOWNSTREAM — P1.M1.T4.S4 (native finals before generic output): keep the single call
           `self._handoff_context_prompt(cleaned)` above its native branch / early return, so a
           native delivery failure still hands off. The accumulator is the "native committed input".
```

`P1M1T4S2/PRP.md:227-235` gives the same begin/write/finish caller pattern. Exact integration lines `:241-243`:

```text
CONSUMED BY: P1.M1.T4.S4 (enqueue from the reader thread after the gates), P1.M1.T4.S5
  (drain_pending / clear_pending / revoke("cancelled")), P1.M1.T4.S7 (ack via on_command,
  check_deadline via the pump timer, send_line_capped as the write).
```

## 5. Test harness and G1 baseline

`tests/test_daemon.py:1-15`: CPU-only/hermetic; no real RealtimeSTT, model load, CUDA, or real feedback dependency; callbacks/recorder use fakes.

- `_FakeBackend` (`tests/test_daemon.py:739-754`): records `type_text` in `.typed`, optionally raises on an exact payload, and records backspaces as `("bs", n)`; primary zero-generic-output recorder.
- `_FakeHost` (`:783-826` and following methods): CUDA-free RecorderHost stand-in with callbacks, spawn/stop/cancel counters, wrapped stub recorder, controllable liveness/device.
- `_make_daemon(...)` (`:904-921`): hermetic constructor with `_DaemonFakeFeedback`, `_StubRecorder`, `_FakeBackend`, injected mic prober, and optional recorder/host/factory/backend/config; returns `(d, fb, rec, be)`.
- `_make_daemon_with_feedback(tmp_path, monkeypatch, *, cuda=True)` (`:2174`): additional daemon/feedback factory signature for tests needing the feedback fixture rather than the basic `_make_daemon` tuple.
- Supporting feedback recorders: `_FakeFeedback` (`:36-65`) records partials/phases/notifies/modes; `_DaemonFakeFeedback` (`:692-710`) adds finals/listening/toasts. `_PromptRecordingHost` (`:5029-5038`) records `set_prompt` values for handoff assertions.
- No named `tripwire`/`must_not`/`forbidden` or clipboard/evdev-specific tripwire was found. `_FakeBackend` is the generic-injection recorder/raiser; feedback fakes record notifications. `test_daemon_has_no_bulk_surface` (`:2286-2304`) asserts retired bulk/injection surfaces stay absent.

Five-line G1 rule (`tests/G1_BASELINE.md:274-289,336-347`):

1. `test_daemon.py` is CPU-only/hermetic, approximately 16 seconds, not a CUDA suite (`:276-281`).
2. Fresh baseline at `6ca9fee`: **218 passed / 20 failed**, with failure-name set identical to research (`:289`).
3. Legacy reds comprise 15 lazy-separator, 3 compute-type, and 2 status/reseed cases (`:336-340`).
4. Diff **FAILED-name sets**, never pass counts (`:342-347`).
5. A NEW failed name is a regression to investigate; a GONE name is a fix requiring a dated baseline update (`:344-347`).

## 6. PRD §6/§7 native gates

- `prd_snapshot.md:573`: "**T10 — Contextual editor dictation (§4.8.1):** Run T10a–d. Use private sockets, fake ASR/events and isolated editors for automated tests; no mic, CUDA, global key injection, systemd changes, or clipboard/device rebinding. Put controllable barriers at load/seed ACK, final acceptance, edit and ACK to test races deterministically rather than with sleeps. Follow `AGENTS.md` timeouts and the daemon-suite baseline set-diff rule."
- `prd_snapshot.md:575` (T10a): requires warm/cold ACK-before-capture, rejected-first-utterance rolling handoff, prompt privacy, and "Plain start/stop/stream/block retain their keyboard behavior outside owner sessions."
- `prd_snapshot.md:576` (T10b): requires stale/duplicate/identity-less final handling, queue/byte caps, one accepted final per offer, "no transcript in general feedback," "**zero** calls to every global delivery path even on error," recovery without replay, and acknowledged/never-offered/possibly-applied coverage.
- `prd_snapshot.md:596`: "Stream and block use the same generic key injector ... Neither detects the application, routes to tmux, or writes the clipboard. Native one-edit insertion is only offered by explicit application integrations."
- `prd_snapshot.md:597`: native editors use one undoable edit per final, no writes to another target, recovery on target loss, and T10a-c must pass before completion.
- `delta_prd.md:27`: callbacks clean/filter, retain and enqueue; no socket waits or abort/drain under the control lock or on the recorder reader thread; eight-final/4 KiB bounds; overflow recovers without truncated insertion.
- `delta_prd.md:29`: "native mode bypasses all generic injection, bulk acquisition, evdev guards and transcript-bearing desktop/status feedback."
- `delta_prd.md:31`: native recovery is separate from `voicectl session`; no automatic replay/persistence; T10b proves zero global output even on failure.
- `delta_prd.md:55`: native partial writes and automatic handoff are out of scope.

## Residual risks

Static research only; no runtime/test validation. Existing daemon code does not prescribe native field names or owner-selection mechanics. T4.S4 must consume T3.S4 reservation identity and T4.S2's queue rather than create a parallel owner/delivery state machine.
